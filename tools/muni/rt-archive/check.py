"""Quality and freshness checks on the 511 realtime archive, read from the bucket itself.

For each feed over a window, from the bucket's own listing and the archived bytes:
  count    snapshots in the bucket >= 90% of the window over the poll interval
  gaps     no gap between snapshots (or from either end of the window) over 3x the interval
  advance  the data in each snapshot moves on: the median vehicle timestamp (Vehicle Positions) or trip_update
           timestamp (Trip Updates) is later than the snapshot before's in >= 90% of pairs, never the same for 3
           snapshots running, and its median age at fetch is under 180 s. 511 stamps the feed header at request
           time, so the header can't show a frozen feed; the entity timestamps can.
  entities a snapshot is usable when it has a non-zero header and 10 to 3,000 entities. 511 sometimes answers with an
           empty or near-empty feed (0 to 5 entities) for a while: 2026-11-13 lost 17:48-18:45 UTC on both feeds. A
           day with such snapshots still passes, and its record carries empty_snapshots, the runs of them and
           max_gap_good_s (the longest stretch, window ends included, with no usable snapshot). It fails only when
           usable snapshots fall under 90% of the window over the interval (GOOD_SHARE, the same floor the count
           check holds the files to: 432 of 480 Vehicle Positions, 648 of 720 Trip Updates, so a feed down for
           more than about 2.4 hours of a day fails), or when over 5% of the usable snapshots hold under half the
           median of the 10 usable ones around them
  lag      bucket write time minus fetch time under 15 minutes for every snapshot, and no spool file older than
           15 minutes still waiting to upload
  parquet  a compacted day's Parquet holds every usable snapshot the bucket holds in the window (an empty one has
           no rows to hold); a day 2 or more days old with no Parquet fails
With no window given (the daily timer), it checks every finished day of the last 7 that isn't compacted yet, plus
any compacted day not yet checked against its Parquet, one record per day. The window starts no earlier than
state/started-at, the first poll after the VM could write to the bucket.
--freshness checks only that each feed's newest object is no older than 3x its interval plus a minute.

A failure records itself in state/checks/, opens or comments on the GitHub issue labelled data-refresh (as
pipeline/site-refresh/refresh.py does) and exits 1; compact.py won't compact a day that failed. A pass updates the
rt-archive label's description, which .github/workflows/refresh-watch.yml watches for a VM that has stopped.

Usage: check.py [--day 2026-11-10 | --since 2026-11-10T08:00 --until 2026-11-10T10:00] [--no-alert]
       check.py --freshness
       check.py --since ... --until ... --feed-dir DIR   # check snapshot files in DIR instead (to watch one fail)
"""

import argparse
import datetime as dt
import gzip
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtarchive as R  # noqa: E402

COUNT_SHARE, GAP_X, ADVANCE_SHARE, MAX_DATA_AGE, MAX_LAG, DIP, DIP_SHARE = 0.90, 3, 0.90, 180, 900, 0.5, 0.05
GOOD_SHARE = 0.90  # usable snapshots, of the window over the interval, below which a day is broken rather than gappy
MAX_RUNS = 20  # runs of unusable snapshots kept in a day's record


def utc(s):
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def listing(b, feed, since, until):
    """(name, bucket write time) for every snapshot in [since, until)."""
    out, h = [], since.replace(minute=0, second=0, microsecond=0)
    while h < until:
        pre = "%s/%s/%s/" % (R.AGENCY, feed, h.strftime("%Y/%m/%d/%H"))
        out += [(x.name, x.time_created) for x in b.list_blobs(prefix=pre) if x.name.endswith(".pb.gz")]
        h += dt.timedelta(hours=1)
    return sorted(o for o in out if since <= R.time_of(o[0]) < until)


def check_feed(feed, snaps, read, since, until):
    """snaps: [(name, write time or None)]; read(name) -> raw bytes. Returns (failures, stats, usable names)."""
    iv = R.FEEDS[feed][1]
    fails = []
    expected = (until - since).total_seconds() / iv
    if len(snaps) < COUNT_SHARE * expected:
        fails.append("count: %d snapshots, expected about %d" % (len(snaps), expected))
    times = [since] + [R.time_of(n) for n, _ in snaps] + [until]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    worst = max(range(len(gaps)), key=gaps.__getitem__)
    if gaps[worst] > GAP_X * iv:
        fails.append("gap: %.0f s with no snapshot after %s (limit %d s)" % (
            gaps[worst], times[worst].strftime("%Y-%m-%dT%H:%M:%SZ"), GAP_X * iv))
    datas, ages, ents, good, bad = [], [], [], [], []
    for n, _ in snaps:
        try:
            m = R.decode(read(n))
        except Exception as e:  # compact.py can't decode it either, so this one still fails the day
            fails.append("decode: %s doesn't parse (%s)" % (n, type(e).__name__))
            continue
        if not m.header.timestamp or not R.ENTITY_RANGE[0] <= len(m.entity) <= R.ENTITY_RANGE[1]:
            bad.append((R.time_of(n), len(m.entity)))
            continue
        good.append(n)
        ents.append(len(m.entity))
        ts = R.entity_times(m)
        if ts:
            datas.append(statistics.median(ts))
            ages.append(R.time_of(n).timestamp() - datas[-1])
    gtimes = [since] + [R.time_of(n) for n in good] + [until]
    ggaps = [(b - a).total_seconds() for a, b in zip(gtimes, gtimes[1:])]
    runs = []  # consecutive unusable snapshots: [first, last, how many, fewest entities]
    for t, e in bad:
        if runs and (t - runs[-1][1]).total_seconds() <= 1.5 * iv:
            runs[-1][1:] = [t, runs[-1][2] + 1, min(runs[-1][3], e)]
        else:
            runs.append([t, t, 1, e])
    if bad:
        print("%s: %d unusable snapshots (empty or outside %d-%d entities), longest stretch with none usable %.0f s"
              % (feed, len(bad), *R.ENTITY_RANGE, max(ggaps)), flush=True)
    if len(good) < GOOD_SHARE * expected:
        fails.append("entities: %d usable snapshots, under %d (%.0f%% of about %d); %d empty or outside %d-%d" % (
            len(good), math.ceil(GOOD_SHARE * expected), 100 * GOOD_SHARE, expected, len(bad), *R.ENTITY_RANGE))
    dips = [i for i in range(len(ents))
            if ents[i] < DIP * statistics.median(ents[max(0, i - 5):i] + ents[i + 1:i + 6] or [ents[i]])]
    if ents and len(dips) > DIP_SHARE * len(ents):
        fails.append("entities: %d of %d snapshots hold under half their neighbours' count" % (len(dips), len(ents)))
    if len(datas) > 1:
        pairs = list(zip(datas, datas[1:]))
        up = sum(b > a for a, b in pairs) / len(pairs)
        run = best = 1
        for a, b in pairs:
            run = run + 1 if a == b else 1
            best = max(best, run)
        if up < ADVANCE_SHARE:
            fails.append("advance: the data moved forward in only %.0f%% of consecutive snapshots" % (100 * up))
        if best >= 3:
            fails.append("advance: the same data timestamp on %d snapshots running" % best)
        if statistics.median(ages) > MAX_DATA_AGE:
            fails.append("advance: the data is a median %.0f s old at fetch" % statistics.median(ages))
    elif snaps:
        fails.append("advance: no entity timestamps to check")
    lags = [(w - R.time_of(n)).total_seconds() for n, w in snaps if w is not None]
    if lags and max(lags) > MAX_LAG:
        fails.append("lag: %d snapshots reached the bucket over %d s after fetch (worst %.0f s)" % (
            sum(x > MAX_LAG for x in lags), MAX_LAG, max(lags)))
    hm = lambda t: t.strftime("%H:%MZ")
    return fails, {"snapshots": len(snaps), "expected": round(expected), "max_gap_s": round(max(gaps)),
                   "usable": len(good), "empty_snapshots": len(bad), "max_gap_good_s": round(max(ggaps)),
                   "empty_runs": [[hm(a), hm(b), k, e] for a, b, k, e in runs[:MAX_RUNS]],
                   "entities": [min(ents), round(statistics.median(ents)), max(ents)] if ents else None,
                   "dips": len(dips) if ents else None,
                   "data_age_s": round(statistics.median(ages)) if ages else None,
                   "max_lag_s": round(max(lags)) if lags else None}, good


def pending_uploads():
    days = [(R.utcnow() - dt.timedelta(days=i)).date() for i in range(R.KEEP_LOCAL_DAYS + 2)]
    done = {u["name"] for u in R.read_jsonl("uploads", days)}
    old = R.utcnow() - dt.timedelta(seconds=MAX_LAG)
    n = 0
    for d, _, files in os.walk(R.SPOOL):
        for f in files:
            if f.endswith(".pb.gz"):
                name = os.path.relpath(os.path.join(d, f), R.SPOOL)
                n += name not in done and R.time_of(name) < old
    return n


def parquet_check(b, feed, day, good):
    """The day's Parquet holds every usable snapshot the bucket holds in the window; missing is a failure from day 2."""
    import pyarrow.parquet as pq
    blob = b.blob(R.parquet_name(feed, day))
    if not blob.exists():
        if (R.utcnow().date() - day).days >= 2:
            return ["parquet: none for %s, two or more days on (compact.py --day %s, after fixing what failed)" % (
                day, day)], False
        return [], False
    os.makedirs(os.path.join(R.ROOT, "parquet"), exist_ok=True)
    p = os.path.join(R.ROOT, "parquet", "check-%s-%s.parquet" % (feed, day))
    blob.download_to_filename(p)
    got = {int(t.timestamp()) for t in pq.read_table(p, columns=["snapshot_time"]).column(0).unique().to_pylist()}
    os.remove(p)
    want = {int(R.time_of(n).timestamp()) for n in good}
    missing = want - got
    return ([] if not missing else ["parquet: %d of the bucket's %d snapshots are not in the Parquet" % (
        len(missing), len(want))]), True


def freshness(b):
    fails, now = [], R.utcnow()
    for feed, (_, iv) in sorted(R.FEEDS.items()):
        snaps = listing(b, feed, now - dt.timedelta(hours=2), now + dt.timedelta(minutes=1))
        limit = 3 * iv + 60
        age = (now - R.time_of(snaps[-1][0])).total_seconds() if snaps else None
        print("%s newest %s" % (feed, "none in 2 h" if age is None else "%.0f s old" % age), flush=True)
        if age is None or age > limit:
            fails.append("freshness: %s newest snapshot %s (limit %d s)" % (
                feed, "over 2 h old" if age is None else "%.0f s old" % age, limit))
    return fails


def archive_start():
    """The minute the poll timer was first installed (state/started-at, written by vm-setup.sh), if known."""
    p = os.path.join(R.STATE, "started-at")
    if os.path.exists(p):
        with open(p) as f:
            return utc(f.read().strip())
    return None


def days_to_check(b):
    """Finished days of the last 7 with a feed not compacted, or compacted and not yet checked against it."""
    today = R.utcnow().date()
    recs = R.read_jsonl("checks", [today - dt.timedelta(days=i) for i in range(9)])
    verified = {r["day"] for r in recs if r.get("ok") and r.get("parquet_checked")}
    out = []
    for i in range(7, 0, -1):
        d = today - dt.timedelta(days=i)
        if d.isoformat() not in verified:
            out.append(d)
    return out


def check_window(a, b, day, since, until):
    """Check one window (one day, or --since/--until) for both feeds; record it when it is a day."""
    rec = {"t": R.utcnow().isoformat(), "day": day.isoformat() if day else None}
    start = archive_start()
    if start and since < start:
        since = start  # nothing before the bucket could be written is held to its interval
    fails, checked = [], []
    if since < until:
        rec.update(since=since.isoformat(), until=until.isoformat(), feeds={})
        for feed in sorted(R.FEEDS):
            if a.feed_dir:
                base = os.path.join(a.feed_dir, feed)
                names = sorted(os.path.relpath(os.path.join(p, f), a.feed_dir)
                               for p, _, fs in os.walk(base) for f in fs if f.endswith(".pb.gz"))
                snaps = [(n, None) for n in names if since <= R.time_of(n) < until]

                def read(n):
                    with open(os.path.join(a.feed_dir, n), "rb") as f:
                        return gzip.decompress(f.read())
            else:
                snaps = listing(b, feed, since, until)

                def read(n):
                    p = os.path.join(R.SPOOL, n)
                    try:
                        with open(p, "rb") as f:
                            return gzip.decompress(f.read())
                    except FileNotFoundError:
                        return gzip.decompress(b.blob(n).download_as_bytes())
            f, stats, good = check_feed(feed, snaps, read, since, until)
            if b is not None and day:
                pf, had = parquet_check(b, feed, day, good)
                f += pf
                checked.append(had)
            fails += ["%s %s" % (feed, x) for x in f]
            rec["feeds"][feed] = stats
            print("%s %s: %s" % (day or "", feed, stats), flush=True)
    else:
        rec["note"] = "before the archive started"
        print("%s: before the archive started" % day, flush=True)
    rec.update(ok=not fails, fails=fails, parquet_checked=bool(checked) and all(checked),
               data_ok=not [x for x in fails if " parquet: none for " not in x])
    if day and not a.feed_dir:  # a check of files outside the bucket never gates compaction
        R.append_jsonl("checks", rec)
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--freshness", action="store_true")
    ap.add_argument("--feed-dir", help="read snapshots from DIR/<feed>/... instead of the bucket")
    ap.add_argument("--no-alert", action="store_true")
    a = ap.parse_args()
    b = R.bucket() if not a.feed_dir else None
    rec = {"t": R.utcnow().isoformat()}
    if a.freshness:
        fails, what = freshness(b), "freshness check"
        rec["kind"] = "freshness"
    else:
        if a.since:
            if not a.until:
                ap.error("--since needs --until")
            windows = [(None, utc(a.since), utc(a.until))]
        else:
            if a.day and dt.date.fromisoformat(a.day) >= R.utcnow().date():
                ap.error("--day must be a finished UTC day; use --since and --until for part of today")
            days = [dt.date.fromisoformat(a.day)] if a.day else days_to_check(b)
            windows = [(d, dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc), None) for d in days]
        fails, what = [], "daily check"
        for day, since, until in windows:
            until = until or since + dt.timedelta(days=1)
            f = check_window(a, b, day, since, until)
            fails += ["%s %s" % (day or "", x) for x in f]
        if not a.feed_dir:
            n = pending_uploads()
            if n:
                fails.append("lag: %d spool files older than %d s are not in the bucket" % (n, MAX_LAG))
        if not windows:
            print("nothing to check: every finished day of the last 7 is compacted and checked", flush=True)
    if a.freshness:
        rec.update(ok=not fails, fails=fails)
        R.append_jsonl("checks", rec)
    if fails:
        print("\n".join("FAIL " + x for x in fails), flush=True)
        if not a.no_alert:
            R.alert("511 realtime archive %s failed" % what, "\n".join(fails))
        sys.exit(1)
    print("ok: %s passed" % what, flush=True)
    if not a.no_alert and not a.feed_dir:
        R.heartbeat(what)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # a bucket that can't be listed or read is itself a failure to report
        R.append_jsonl("checks", {"t": R.utcnow().isoformat(), "ok": False, "fails": ["crash: %s" % type(e).__name__]})
        if "--no-alert" not in sys.argv:
            R.alert("511 realtime archive check could not run", "%s: %s" % (type(e).__name__, str(e)[:2000]))
        raise
