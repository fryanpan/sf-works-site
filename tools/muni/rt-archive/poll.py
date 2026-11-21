"""Poll Muni's 511 GTFS-realtime feeds that are due this minute, save each raw to the spool, then upload what's pending.

Run every minute by rt-archive-poll.timer. Trip Updates are due on even minutes (every 120 s) and Vehicle Positions
on minutes divisible by 3 (every 180 s): 50 requests an hour. Before each request the script counts its own requests
in the last 3,540 s (state/requests.log) and skips the poll at 50, or when its own and pull_all.py's together
reach 58 (that script logs to ~/muni-511/history/requests.log), so the token stays under 511's 60 an hour however
the timer misfires. An HTTP 429 pauses all polling for 15 minutes. A failed or unparseable fetch saves
nothing and is logged in state/polls/. The poll is validated before it is written: it must parse as a complete
GTFS-realtime FeedMessage with a header timestamp.

After polling, every spool file that isn't yet in the bucket is uploaded with if-generation-match 0, so a retry
can't overwrite and a 412 means it is already there. Uploads stop after 40 s and resume next minute, so a bucket
outage only builds a backlog. Spool files older than 7 days are deleted only once their upload is recorded.

The token is read from ~/.511token and never printed; neither is the URL.
Usage: poll.py                  # what the timer runs
       poll.py --feed trip_updates   # poll one feed now (still counted against the hourly cap)
       poll.py --upload-only
"""

import argparse
import fcntl
import gzip
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtarchive as R  # noqa: E402

REQLOG = os.path.join(R.STATE, "requests.log")
PAUSE = os.path.join(R.STATE, "pause-until")
UPLOAD_SECONDS = 40


def read_times(path):
    try:
        with open(path) as f:
            return [float(x) for x in f.read().split()]
    except (OSError, ValueError):
        return []


def budget_ok(now):
    ts = read_times(REQLOG)
    # 3,540 s, not 3,600: polls on a 60 s grid that start a second or two late would otherwise still count the poll
    # from an hour before and skip one. At most one of ours falls between 3,540 and 3,600 s, so ours never pass 51.
    recent = [t for t in ts if now - t < 3540]
    others = sum(1 for p in R.OTHER_REQLOGS for t in read_times(p) if now - t < 3600)
    if len(recent) >= R.MAX_PER_HOUR or len(recent) + others >= R.SHARED_MAX:
        return False
    with open(REQLOG + ".tmp", "w") as f:
        f.write("".join("%d\n" % t for t in recent + [now]))
    os.replace(REQLOG + ".tmp", REQLOG)
    return True


def poll(feed, now):
    endpoint = R.FEEDS[feed][0]
    t = R.utcnow()
    rec = {"t": t.isoformat(), "feed": feed}
    if os.path.exists(PAUSE) and float(open(PAUSE).read() or 0) > now:
        rec["status"] = "paused-after-429"
        return R.append_jsonl("polls", rec, t)
    if not budget_ok(now):
        rec["status"] = "skipped-hourly-cap"
        return R.append_jsonl("polls", rec, t)
    with open(R.TOKEN_FILE) as f:
        tok = f.read().strip()
    url = "https://api.511.org/transit/%s?agency=SF&api_key=%s" % (endpoint, tok)
    try:
        with urllib.request.urlopen(url, timeout=20) as r:  # two fetches must fit the unit's 58 s
            raw = r.read()
    except urllib.error.HTTPError as e:
        rec["status"] = "http-%d" % e.code
        if e.code == 429:
            with open(PAUSE, "w") as f:
                f.write("%d" % (now + 900))
        return R.append_jsonl("polls", rec, t)
    except Exception as e:  # the message of a URLError can carry the URL, so only its type is kept
        rec["status"] = "error-" + type(e).__name__
        return R.append_jsonl("polls", rec, t)
    try:
        m = R.decode(raw)
        if not m.IsInitialized() or not m.header.timestamp:
            raise ValueError("empty feed")
    except Exception as e:
        rec.update(status="unparseable-" + type(e).__name__, bytes=len(raw))
        return R.append_jsonl("polls", rec, t)
    name = R.rel_path(feed, t)
    path = os.path.join(R.SPOOL, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gz = gzip.compress(raw, mtime=0)
    with open(path + ".tmp", "wb") as f:
        f.write(gz)
    os.replace(path + ".tmp", path)
    rec.update(status="ok", name=name, bytes=len(raw), gz=len(gz), feed_ts=m.header.timestamp,
               entities=len(m.entity))
    R.append_jsonl("polls", rec, t)


def uploaded_names():
    days = [(R.utcnow() - R.dt.timedelta(days=i)).date() for i in range(R.KEEP_LOCAL_DAYS + 2)]
    return {u["name"] for u in R.read_jsonl("uploads", days)}


def spool_files():
    for d, _, files in os.walk(R.SPOOL):
        for fn in files:
            if fn.endswith(".pb.gz"):
                yield os.path.relpath(os.path.join(d, fn), R.SPOOL)


def upload_pending(start):
    done = uploaded_names()
    # Newest first, so after an outage the freshest snapshots land at once and the backlog follows.
    pending = sorted((n for n in spool_files() if n not in done), key=lambda n: (R.time_of(n), n), reverse=True)
    if not pending:
        return 0, 0
    from google.api_core import exceptions as gex
    import requests
    b = R.bucket()
    n = 0
    for name in pending:
        if time.time() - start > UPLOAD_SECONDS:
            break
        try:
            b.blob(name).upload_from_filename(os.path.join(R.SPOOL, name), content_type="application/gzip",
                                              if_generation_match=0, timeout=20, retry=None)
            how = "uploaded"
        except gex.PreconditionFailed:
            how = "already-there"
        except gex.Forbidden as e:
            # An account without overwrite may get 403, not 412, for an object that's already there.
            try:
                exists = b.blob(name).exists(timeout=10)
            except Exception:
                exists = False
            if not exists:
                R.append_jsonl("upload-errors", {"t": R.utcnow().isoformat(), "name": name, "error": type(e).__name__})
                break
            how = "already-there"
        except (gex.Unauthorized, gex.ServerError, gex.TooManyRequests, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout, ConnectionError, TimeoutError) as e:
            R.append_jsonl("upload-errors", {"t": R.utcnow().isoformat(), "name": name, "error": type(e).__name__})
            break  # the bucket is unreachable or refusing; try again next minute
        except Exception as e:  # one bad file mustn't hold up the rest; it is retried next minute
            R.append_jsonl("upload-errors", {"t": R.utcnow().isoformat(), "name": name, "error": type(e).__name__})
            continue
        lag = (R.utcnow() - R.time_of(name)).total_seconds()
        R.append_jsonl("uploads", {"name": name, "t": R.utcnow().isoformat(), "how": how, "lag_s": round(lag)})
        n += 1
    return n, len(pending) - n


def prune():
    """Delete spool files older than KEEP_LOCAL_DAYS whose upload is recorded; keep anything not yet in the bucket."""
    cutoff = R.utcnow() - R.dt.timedelta(days=R.KEEP_LOCAL_DAYS)
    done = uploaded_names()
    for name in spool_files():
        if R.time_of(name) < cutoff and name in done:
            os.remove(os.path.join(R.SPOOL, name))
    for d, dirs, files in os.walk(R.SPOOL, topdown=False):
        if d != R.SPOOL and not dirs and not files:
            os.rmdir(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", choices=sorted(R.FEEDS))
    ap.add_argument("--upload-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(R.STATE, exist_ok=True)
    lock = open(os.path.join(R.STATE, "poll.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another poll is still running; this minute is skipped", flush=True)
        return
    start = time.time()
    if not a.upload_only:
        minute = int(start // 60)
        due = [a.feed] if a.feed else [f for f, (_, iv) in sorted(R.FEEDS.items()) if minute % (iv // 60) == 0]
        for feed in due:
            poll(feed, start)
    n, left = upload_pending(start)
    if n or left:
        print("uploaded %d, %d still pending" % (n, left), flush=True)
    if time.gmtime(start).tm_min == 7:  # once an hour
        prune()


if __name__ == "__main__":
    main()
