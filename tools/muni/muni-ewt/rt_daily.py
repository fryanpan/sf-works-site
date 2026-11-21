"""Muni's daily excess wait, speed and running time for the days 511's monthly stop records don't cover yet, rebuilt from our realtime archive.

Bryan, 2026-11-12 ("How often should the Muni dashboard's figures update?"): "Daily. And
use 511's historical stop time API if DataSF is out of date". 511 posts a month of observed stop arrivals (the -so
historic files, pull_all.py) a few days after the month ends, so the newest days always come from the realtime
archive (tools/muni/rt-archive/: vehicle positions every 3 minutes, trip updates every 2, in a Cloud Storage bucket).

Which days. Every service date from the day after the newest month 511 has posted (history/regional-<m>-so-sf/DONE)
through the newest complete one, and not before ARCHIVE_FIRST. A service date D is complete once the clock passes
12:30 UTC on D+1, after the last bus counted (the hours counted end at 22:59, and a trip that starts then ends before
02:00) has run; the daily timer fires at 13:15 UTC, so each morning's run adds yesterday. A month 511 has posted
is never rebuilt from the archive again; its archive days stay on disk and in data/muni-ewt/rt/ for the comparison.

How a day is built, on the cloud VM (heavy work never runs on the laptop):
  1. Inputs: the two UTC days the service date spans (D and D+1), each feed, as decoded Parquet
     (tools/muni/rt-archive/day_parquet.py): the bucket's compacted file where compact.py has written it, cached under
     rt/parquet/ since it can't change, else decoded straight from the raw snapshots (not cached).
  2. Timetable: 511's own Muni GTFS (fetch_gtfs_511.py), the edition whose feed_info dates cover D with the latest
     start, since its trip and stop ids are the realtime feeds'. A new download is tried when the newest check is over
     GTFS_RECHECK_DAYS old, or once per run when a day's positions match under REFETCH_MATCH of its scheduled trips.
  3. Arrivals: snapshot_vs_hist.py rebuild, positions placed on each trip's shape and interpolated to each stop
     (vp_arr), trip updates' last prediction alongside (tu_arr). The published column is vp_arr, the method tested on 9
     November 2026 against 90-second positions (median 9 s, 90th percentile 38 s per stop visit, 0.13% of visits lost,
     citywide excess wait 1.199 against 1.201 minutes).
  4. Extract: written in extract_sf.py's layout, as 511's own records are, with trip ids 'SF:<trip>:<YYYYMMDD>' and
     each trip's stops numbered from 1, so ewt_month.py's first-stop rule drops the same stop on both sides.
A day whose positions rebuild under OUTAGE_SHARE of its scheduled stop visits is kept with status 'outage' and left
out of the figures; ewt_month.py's own outage rules handle a partial loss inside a day.

The metrics are the monthly pipeline's own scripts, run the way rerun_all.py and post_all.sh run them (system python3
with ~/muni-511/pylib): ewt_month.py (excess wait, TfL QSI method) and trip_time.py (speed and running time against
the timetable, with the monthly run's distance and timepoint tables, ~/muni-511/ewt/ref) over all of a month's
archive days at once, so the month-level rules (holiday day types, partial feed outages against the month's median)
work as they do on 511's months; then ewt_daily.py writes each line by service date, the same columns as
data/muni-ewt/daily/<m>.csv.

Incremental and idempotent. A day is rebuilt only when its stamp (rt/days/<D>/stamp: the hash of snapshot_vs_hist.py
and this file's EXTRACT_VERSION, the timetable edition, and whether each input was final) no longer matches, or when
it was built from raw snapshots and the compacted Parquet has since appeared (a bounded re-read: each day is read at
most twice, the second time from the final copy). A month is recomputed only when its stamp (the hashes of
ewt_month.py, trip_time.py and ewt_daily.py and every day stamp in it) changes. A run with nothing new rebuilds
nothing and writes the same bytes. A day's "read" date is the date its inputs were read, not the run date.

Comparison with 511's month (set up 2026-11-12 to fire on its own): when 511 posts a month that has archive days
(December 2026 for November) and the monthly pipeline has built its daily file, every archive day is scored against
511's record, arrival by arrival (snapshot_vs_hist.py compare: share of 511's visits we rebuilt, median and 90th
percentile error, for vp_arr, tu_arr and arr) and figure by figure (each day's citywide and each line's month figures
from both). Written to data/muni-ewt/rt/compare-<m>.json for the dashboard's About page; rerun only when its inputs change.

Outputs (repo): data/muni-ewt/rt/days.csv (one row per archive day: status, read date, timetable edition, coverage),
rt/daily/<m>.csv (ewt_daily.py), rt/compare-<m>.json. Off the VM (no ~/muni-511/history) it says so and exits 0, and
the builds use the copy in the repo. A failed rebuild or metric run exits 1 before anything in the repo is written.
511 usage: the timetable download is the only 511 request, counted in pull_all.py's log under the shared 58 an hour.
Usage: rt_daily.py [--update] [--now ISO-UTC]   (--update is accepted for the orchestrator; every run is incremental)
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse, csv, datetime as dt, glob, hashlib, io, json, os, shutil, subprocess, sys, zipfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
H = os.path.expanduser(os.environ.get("MUNI_511_ROOT", "~/muni-511"))
W = os.path.join(H, "rt")
OUT = os.path.join(ROOT, "data", "muni-ewt", "rt")
TZ = ZoneInfo("America/Los_Angeles")
ARCHIVE_FIRST = dt.date(2026, 11, 10)  # the first service day with positions all day (9 Nov has none before 07:15) and trip updates
TU_FIRST = dt.date(2026, 11, 10)       # trip updates from 10 Nov 06:14 UTC
READY_UTC = dt.time(12, 30)            # a service date is complete at this time on the next day, UTC
EXTRACT_VERSION = "2"                  # bump when the extract below changes what it writes
GTFS_RECHECK_DAYS, REFETCH_MATCH, OUTAGE_SHARE = 7, 0.70, 0.50
RT_PY = os.path.expanduser("~/.venvs/rt-archive/bin/python")
METRIC_ENV = dict(os.environ, PYTHONPATH=os.path.join(H, "pylib"), PYTHONHASHSEED="0")
METRIC_ENV.pop("NET_LOG", None); METRIC_ENV.pop("TRACE_LOG", None)
SYS_PY = "/usr/bin/python3"
DAY_FIELDS = ["sdate", "status", "source", "read", "gtfs", "trips_scheduled", "trips_with_positions", "visits_scheduled",
              "visits_rebuilt", "visits_tu", "inputs"]


def sha(*paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(open(p, "rb").read())
    return h.hexdigest()[:16]


def log(*a):
    print(*a, flush=True)


def run(cmd, env=None, quiet=False):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError("%s exited %d: %s" % (os.path.basename(cmd[1] if len(cmd) > 1 else cmd[0]), r.returncode,
                                                 (r.stdout + r.stderr)[-800:]))
    return r.stdout


def newest_511_month():
    done = sorted(os.path.basename(os.path.dirname(p))[9:16] for p in glob.glob(f"{H}/history/regional-20??-??-so-sf/DONE"))
    return done[-1] if done else None


def month_after(m):
    y, mo = int(m[:4]), int(m[5:])
    return dt.date(y + (mo == 12), mo % 12 + 1, 1)


def complete_through(now):
    """The newest service date whose buses have all run by `now` (UTC)."""
    d = now.date() - dt.timedelta(days=1)
    return d if now.time() >= READY_UTC else d - dt.timedelta(days=1)


# ---- timetables ---------------------------------------------------------------------------------------------------
def editions():
    """[(feed_start, feed_end, version, path)] of every 511 Muni timetable on disk."""
    out = []
    for p in sorted(glob.glob(os.path.join(W, "gtfs", "sf-*.zip"))):
        with zipfile.ZipFile(p) as z:
            rows = list(csv.DictReader(io.TextIOWrapper(z.open("feed_info.txt"), "utf-8-sig")))
        r = rows[0]
        out.append((dt.date.fromisoformat(r["feed_start_date"][:4] + "-" + r["feed_start_date"][4:6] + "-" + r["feed_start_date"][6:]),
                    dt.date.fromisoformat(r["feed_end_date"][:4] + "-" + r["feed_end_date"][4:6] + "-" + r["feed_end_date"][6:]),
                    r["feed_version"], p))
    return out


FETCHED = []


def fetch_timetable(why):
    if FETCHED:
        return
    FETCHED.append(why)
    log("timetable: fetching 511's Muni GTFS (%s)" % why)
    env = dict(os.environ); env.pop("NET_LOG", None); env.pop("PYTHONPATH", None)
    r = subprocess.run([SYS_PY, paths.script("fetch_gtfs_511.py"), H], capture_output=True, text=True, env=env)
    log("timetable:", (r.stdout + r.stderr).strip().splitlines()[-2:] if (r.stdout + r.stderr).strip() else "(no output)")


def timetable_for(d):
    chk = os.path.join(W, "gtfs", "checked")
    age = (dt.datetime.now().timestamp() - json.load(open(chk))["t"]) / 86400 if os.path.exists(chk) else None
    if age is None or age > GTFS_RECHECK_DAYS:
        fetch_timetable("last check %s days ago" % (None if age is None else round(age, 1)))
    cov = [e for e in editions() if e[0] <= d <= e[1]]
    if not cov:
        fetch_timetable("no edition on disk covers %s" % d)
        cov = [e for e in editions() if e[0] <= d <= e[1]]
    return max(cov) if cov else None


# ---- archive inputs ------------------------------------------------------------------------------------------------
def utc_day(feed, day, probe_only=False):
    """(path, final) for one UTC day of one feed; probe_only returns (None, final) without downloading."""
    cache = os.path.join(W, "parquet", feed, f"{day}.parquet")
    if os.path.exists(cache):
        return cache, True
    tmp = os.path.join(W, "parquet-tmp", feed, f"{day}.parquet")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if probe_only:
        r = subprocess.run([RT_PY, "-c", "import sys; sys.path.insert(0, %r); import rtarchive as R, datetime as dt; "
                            "print(R.bucket().blob(R.parquet_name(%r, dt.date.fromisoformat(%r))).exists())"
                            % (os.path.dirname(paths.script("rtarchive.py")), feed, str(day))], capture_output=True, text=True)
        return None, r.stdout.strip() == "True"
    info = json.loads(run([RT_PY, paths.script("day_parquet.py"), "--feed", feed,
                           "--day", str(day), "--out", tmp]).strip().splitlines()[-1])
    if info["final"]:
        os.replace(tmp, cache)
        return cache, True
    return tmp, False


# ---- one day -------------------------------------------------------------------------------------------------------
def day_dir(d):
    return os.path.join(W, "days", str(d))


def day_stamp(version, finals):
    return " ".join([sha(paths.script("snapshot_vs_hist.py")), EXTRACT_VERSION, version,
                     "final" if all(finals) else "raw"])


def needs_build(d):
    """None when day d is current, else why it must be (re)built."""
    sf, mf = os.path.join(day_dir(d), "stamp"), os.path.join(day_dir(d), "meta.json")
    if not (os.path.exists(sf) and os.path.exists(mf)):
        return "not built"
    old = open(sf).read().split()
    # A built day keeps the timetable edition it was built on while that edition is on disk and covers it, so a new
    # edition (whose trip ids may differ before its own start of service) never rebuilds days it wasn't made for.
    # Only a rebuild whose positions match under REFETCH_MATCH of its trips may move to a newer edition (build_day).
    if not any(e[2] == old[2] and e[0] <= d <= e[1] for e in editions()):
        return "its timetable edition %s is gone" % old[2]
    if old[:2] != [sha(paths.script("snapshot_vs_hist.py")), EXTRACT_VERSION]:
        return "script changed"
    if old[3] == "raw":
        feeds = ["vehicle_positions"] + (["trip_updates"] if d >= TU_FIRST else [])
        if all(utc_day(f, u, probe_only=True)[1] for f in feeds for u in (d, d + dt.timedelta(days=1))):
            return "built from raw snapshots; the compacted Parquet is now in the bucket"
    return None


def build_day(d, version=None):
    ed = next((e for e in editions() if e[2] == version and e[0] <= d <= e[1]), None) if version else timetable_for(d)
    if ed is None:
        raise RuntimeError(f"{d}: no 511 Muni timetable covers it")
    days = (d, d + dt.timedelta(days=1))
    vp = [utc_day("vehicle_positions", u) for u in days]
    tu = [utc_day("trip_updates", u) for u in days] if d >= TU_FIRST else []
    dd = day_dir(d); tmpd = dd + ".tmp"
    shutil.rmtree(tmpd, ignore_errors=True); os.makedirs(tmpd)
    arr = os.path.join(tmpd, "arrivals.parquet")
    cmd = [sys.executable, "-I", paths.script("snapshot_vs_hist.py"), "rebuild", "--date", str(d), "--gtfs", ed[3],
           "--vp", *[p for p, _ in vp], "--out", arr]
    if tu:
        cmd[cmd.index("--out"):cmd.index("--out")] = ["--tu", *[p for p, _ in tu]]
    run(cmd)
    diag = json.load(open(arr.replace(".parquet", ".json")))
    match = diag.get("trips_with_positions", 0) / max(diag["trips_scheduled"], 1)
    if match < REFETCH_MATCH and not FETCHED:
        fetch_timetable(f"{d}: positions matched {match:.0%} of scheduled trips")
        if timetable_for(d)[2] != ed[2]:
            shutil.rmtree(tmpd)
            return build_day(d)
    write_extract(arr, ed[3], d, os.path.join(tmpd, "extract"))
    share = (diag["vp_rebuilt"] or 0) / max(diag["visits_scheduled"], 1)
    meta = {"sdate": d.strftime("%Y%m%d"), "status": "ok" if share >= OUTAGE_SHARE else "outage", "source": "rt-archive",
            "read": dt.datetime.now(TZ).date().isoformat(), "gtfs": ed[2], "trips_scheduled": diag["trips_scheduled"],
            "trips_with_positions": diag.get("trips_with_positions", 0), "visits_scheduled": diag["visits_scheduled"],
            "visits_rebuilt": diag["vp_rebuilt"], "visits_tu": diag["tu_rebuilt"],
            "inputs": "+".join(("parquet" if f else "raw") for _, f in vp + tu)}
    json.dump(meta, open(os.path.join(tmpd, "meta.json"), "w"), indent=1, sort_keys=True)
    open(os.path.join(tmpd, "stamp"), "w").write(day_stamp(ed[2], [f for _, f in vp + tu]) + "\n")
    shutil.rmtree(dd, ignore_errors=True)
    os.replace(tmpd, dd)
    for p, f in vp + tu:
        if not f and os.path.exists(p):
            os.remove(p)
    log(f"day {d}: rebuilt ({meta['status']}, {share:.1%} of {meta['visits_scheduled']} stop visits, timetable {ed[2]}, inputs {meta['inputs']})")


def write_extract(arrivals, gtfs_zip, d, out):
    """One service date as an extract_sf.py directory: trip ids 'SF:<trip>:<YYYYMMDD>', stops numbered from 1 per trip."""
    sys.path.insert(0, HERE)
    import duckdb
    import snapshot_vs_hist as S
    os.makedirs(out, exist_ok=True)
    ymd = d.strftime("%Y%m%d")
    con = duckdb.connect()
    con.execute("SET threads=4")
    gd = S.gtfs_dir(gtfs_zip)
    S.load_sched(con, gd, str(d))
    con.execute(f"""CREATE TABLE tp AS SELECT trip_id, CAST(stop_sequence AS INT) seq, timepoint
      FROM read_csv('{gd}/stop_times.txt', header=true, all_varchar=true) WHERE trip_id IN (SELECT trip_id FROM gtrips)""")
    con.execute("""CREATE TABLE g AS SELECT gst.*, tp.timepoint, row_number() OVER (PARTITION BY gst.trip_id ORDER BY gst.seq) n
      FROM gst LEFT JOIN tp USING (trip_id, seq)""")
    hms = lambda c: f"printf('%02d:%02d:%02d', CAST({c} AS BIGINT)//3600, (CAST({c} AS BIGINT)%3600)//60, CAST({c} AS BIGINT)%60)"
    tid = f"'SF:' || trip_id || ':{ymd}'"
    con.execute(f"""COPY (SELECT 'SF:' || route_id route_id, 'D{ymd}' service_id, {tid} trip_id, dir direction_id
      FROM gtrips ORDER BY trip_id) TO '{out}/trips.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT 'D{ymd}' service_id, '{ymd}' date, '1' exception_type)
      TO '{out}/calendar_dates.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT {tid} trip_id, {hms('sched_arr')} arrival_time, {hms('sched_dep')} departure_time, stop_id,
        n stop_sequence, timepoint FROM g ORDER BY trip_id, n) TO '{out}/stop_times.csv.gz' (HEADER, COMPRESSION gzip)""")
    con.execute(f"""COPY (SELECT {tid.replace('trip_id', 'a.trip_id')} trip_id, NULL trip_start_time, NULL schedule_relationship,
        '{ymd}' service_date, NULL vehicle_id, g.n stop_sequence, CAST(round(a.vp_arr) AS BIGINT) observed_arrival_time,
        CAST(round(a.vp_arr) AS BIGINT) observed_departure_time, '0' uncertainty, NULL dwell_time_secs,
        NULL scheduled_dwell_time_secs, 'SF:' || a.route_id route_id, 'SF' agency_id, CAST(a.dir AS VARCHAR) direction_id,
        NULL from_stop_id, a.stop_id to_stop_id, a.sched_arr scheduled_arrival_time, a.sched_dep scheduled_departure_time,
        a.vp_fill rt_fill
      FROM read_parquet('{arrivals}') a JOIN g ON g.trip_id = a.trip_id AND g.seq = a.seq
      WHERE a.vp_arr IS NOT NULL ORDER BY a.trip_id, g.n) TO '{out}/stop_observations.csv.gz' (HEADER, COMPRESSION gzip)""")


# ---- one month -----------------------------------------------------------------------------------------------------
METRIC_SCRIPTS = ("ewt_month.py", "trip_time.py", "ewt_daily.py")


def month_days(m):
    return sorted(p for p in glob.glob(os.path.join(W, "days", m + "-??")) if os.path.exists(os.path.join(p, "stamp")))


def ok_days(m):
    return [p for p in month_days(m) if os.path.basename(p) >= str(ARCHIVE_FIRST)
            and json.load(open(os.path.join(p, "meta.json")))["status"] == "ok"]


def month_stamp(m):
    parts = [sha(*[os.path.join(HERE, s) for s in METRIC_SCRIPTS]), sha(os.path.join(H, "ewt", "ref", "stamp"))]
    parts += [os.path.basename(p) + "=" + open(os.path.join(p, "stamp")).read().strip().replace(" ", "/") for p in ok_days(m)]
    return " ".join(parts)


def build_month(m):
    e = os.path.join(W, "ewt")
    sf = os.path.join(e, "stamps", m)
    want = month_stamp(m)
    if os.path.exists(sf) and open(sf).read().strip() == want and os.path.exists(os.path.join(e, "daily", m + ".csv")):
        log(f"month {m}: unchanged ({len(ok_days(m))} days)")
        return False
    import duckdb
    ex = os.path.join(W, "months", m)
    shutil.rmtree(ex, ignore_errors=True); os.makedirs(ex)
    con = duckdb.connect()
    con.execute("SET threads=4")
    days = ok_days(m)
    if not days:
        raise RuntimeError(f"month {m}: no archive day with status ok")
    for f in ("trips.csv.gz", "stop_times.csv.gz", "calendar_dates.csv.gz", "stop_observations.csv.gz"):
        src = ", ".join(f"'{p}/extract/{f}'" for p in days)
        con.execute(f"COPY (SELECT * FROM read_csv([{src}], header=true, all_varchar=true, union_by_name=true)) TO '{ex}/{f}' (HEADER, COMPRESSION gzip)")
    for sub in ("hourly", "diag", "seg", "trip", "daily", "stamps"):
        os.makedirs(os.path.join(e, sub), exist_ok=True)
    run([SYS_PY, paths.script("ewt_month.py"), ex, e, m], env=METRIC_ENV)
    # Speed and running time leave out the trip-end fills (snapshot_vs_hist.py fill_vp 'end'): a stop the positions
    # bracket on one side only takes the schedule's running time from its neighbour, so a segment ending there would
    # measure the timetable, not the bus (Fable review 2026-11-13: 14% of timepoint times on 10 Nov). Excess wait
    # keeps them, as the 9 November test did, since they hold the bus's passage within one 3-minute ping.
    tt = ex + "-tt"
    shutil.rmtree(tt, ignore_errors=True); os.makedirs(tt)
    for f in ("trips.csv.gz", "stop_times.csv.gz", "calendar_dates.csv.gz"):
        os.symlink(os.path.join(ex, f), os.path.join(tt, f))
    con.execute(f"""COPY (SELECT * EXCLUDE (rt_fill) FROM read_csv('{ex}/stop_observations.csv.gz', header=true, all_varchar=true)
      WHERE coalesce(rt_fill, '') <> 'end') TO '{tt}/stop_observations.csv.gz' (HEADER, COMPRESSION gzip)""")
    run([SYS_PY, paths.script("trip_time.py"), tt, e, m, "--tables", os.path.join(H, "ewt", "ref")], env=METRIC_ENV)
    run([SYS_PY, paths.script("ewt_daily.py"), f"{e}/hourly/{m}.parquet", f"{e}/seg/{m}.parquet", f"{e}/daily/{m}.csv"],
        env=METRIC_ENV)
    shutil.rmtree(ex); shutil.rmtree(tt)
    open(sf, "w").write(want + "\n")
    log(f"month {m}: recomputed from {len(days)} archive days")
    return True


# ---- comparison with 511's month -----------------------------------------------------------------------------------
def compare_month(m):
    """Score the archive days of month m against 511's record of the same days, once 511 has posted it."""
    ref = os.path.join(H, "history", f"regional-{m}-so-sf")
    ref_daily = os.path.join(H, "ewt", "daily", m + ".csv")
    rt_daily = os.path.join(W, "ewt", "daily", m + ".csv")
    out = os.path.join(W, "ewt", f"compare-{m}.json")
    if not (os.path.exists(os.path.join(ref, "DONE")) and os.path.exists(ref_daily) and os.path.exists(rt_daily)):
        return None
    # The scripts that score, every archive day's stamp, 511's month, and both daily files' contents. Not the
    # distance-table stamp month_stamp carries, which moves each time 511 posts any month; a change it makes to the
    # figures reaches this stamp through the daily files.
    want = " ".join([sha(paths.script("snapshot_vs_hist.py"), os.path.abspath(__file__)), *month_stamp(m).split()[2:],
                     open(os.path.join(ref, "DONE")).read().strip(), sha(ref_daily, rt_daily)])
    sf = out + ".stamp"
    if os.path.exists(out) and os.path.exists(sf) and open(sf).read().strip() == want:
        return out
    days = ok_days(m)
    per_day = []
    tmp = os.path.join(W, "cmp-tmp.json")
    for p in days:
        d = os.path.basename(p)
        row = {"date": d}
        for col in ("vp_arr", "tu_arr", "arr"):
            if col != "vp_arr" and dt.date.fromisoformat(d) < TU_FIRST:
                continue
            run([sys.executable, "-I", paths.script("snapshot_vs_hist.py"), "compare", "--test",
                 os.path.join(p, "arrivals.parquet"), "--col", col, "--ref511", ref, "--date", d, "--from", "05:00",
                 "--to", "23:00", "--out", tmp])
            a = json.load(open(tmp))["all"]
            row[col] = dict(zip(["visits_511", "not_rebuilt", "med_abs_s", "p90_abs_s", "med_signed_s"], a))
        per_day.append(row)
    if os.path.exists(tmp):
        os.remove(tmp)

    def rows(f):
        return [r for r in csv.DictReader(open(f))]

    def pool(rs):
        n = lambda v: float(v) if v not in ("", None) else 0.0
        a = [0.0] * 7  # swt*eb, eb, awt*eba, eba, miles, obs_hr, sch_hr
        for r in rs:
            if r["swt"] and n(r["eb"]) > 0:
                a[0] += n(r["swt"]) * n(r["eb"]); a[1] += n(r["eb"])
            if r["awt"] and n(r["eba"]) > 0:
                a[2] += n(r["awt"]) * n(r["eba"]); a[3] += n(r["eba"])
            if r["miles"] and n(r["obs_hr"]) > 0:
                a[4] += n(r["miles"]); a[5] += n(r["obs_hr"]); a[6] += n(r["sch_hr"])
        return {"ewt": round(a[2] / a[3] - a[0] / a[1], 3) if a[1] and a[3] else None,
                "mph": round(a[4] / a[5], 2) if a[5] else None,
                "run_over_timetable": round(a[5] / a[6] - 1, 4) if a[6] else None}
    ref_rows, rt_rows = rows(ref_daily), rows(rt_daily)
    # Only the (line, date) pairs both sources hold: the archive has no cable cars (511's realtime feed carries almost
    # none), and a line one side lacks would read as method error (Fable review 2026-11-13).
    both = {(r["route"], r["sdate"]) for r in rt_rows if r["eb"]} & {(r["route"], r["sdate"]) for r in ref_rows if r["eb"]}
    only = sorted({r["route"] for r in rt_rows + ref_rows} - {k[0] for k in both})
    ref_rows = [r for r in ref_rows if (r["route"], r["sdate"]) in both]
    rt_rows = [r for r in rt_rows if (r["route"], r["sdate"]) in both]
    dates = sorted({r["sdate"] for r in rt_rows} & {r["sdate"] for r in ref_rows})
    figs = []
    for sd in dates:
        a, b = pool([r for r in rt_rows if r["sdate"] == sd]), pool([r for r in ref_rows if r["sdate"] == sd])
        figs.append({"sdate": sd, "archive": a, "511": b,
                     "diff": {k: (round(a[k] - b[k], 4) if a[k] is not None and b[k] is not None else None) for k in a}})
    lines = {}
    for route in sorted({r["route"] for r in rt_rows} | {r["route"] for r in ref_rows}):
        a = pool([r for r in rt_rows if r["route"] == route and r["sdate"] in dates])
        b = pool([r for r in ref_rows if r["route"] == route and r["sdate"] in dates])
        lines[route] = {"archive": a, "511": b}
    whole_a = pool([r for r in rt_rows if r["sdate"] in dates])
    whole_b = pool([r for r in ref_rows if r["sdate"] in dates])
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    res = {"month": m, "days_compared": len(dates), "method": "vp_arr", "lines_in_one_source_only": only,
           "summary": {"archive": whole_a, "511": whole_b,
                       "ewt_diff": None if whole_a["ewt"] is None or whole_b["ewt"] is None else round(whole_a["ewt"] - whole_b["ewt"], 3),
                       "mph_diff": None if whole_a["mph"] is None or whole_b["mph"] is None else round(whole_a["mph"] - whole_b["mph"], 2),
                       "median_abs_daily_ewt_diff": med([abs(f["diff"]["ewt"]) for f in figs if f["diff"]["ewt"] is not None]),
                       "median_arrival_error_s": med([r["vp_arr"]["med_abs_s"] for r in per_day if r.get("vp_arr") and r["vp_arr"]["med_abs_s"] is not None]),
                       "median_share_not_rebuilt": med([r["vp_arr"]["not_rebuilt"] for r in per_day if r.get("vp_arr")])},
           "arrivals_by_day": per_day, "figures_by_day": figs, "lines": lines}
    json.dump(res, open(out, "w"), indent=1, sort_keys=True, default=float)
    open(sf, "w").write(want + "\n")
    log(f"compare {m}: {len(dates)} days against 511's record, citywide excess wait {whole_a['ewt']} (archive) vs {whole_b['ewt']} (511)")
    return out


# ---- repo outputs --------------------------------------------------------------------------------------------------
def write_if_changed(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and open(path, encoding="utf-8").read() == text:
        return False
    with open(path + ".tmp", "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(path + ".tmp", path)
    return True


def publish():
    first = ARCHIVE_FIRST.strftime("%Y%m%d")
    metas = {}  # a day's last good build, else its failure record
    for p in sorted(glob.glob(os.path.join(W, "days", "20??-??-??"))):
        if os.path.exists(os.path.join(p, "stamp")):
            r = json.load(open(os.path.join(p, "meta.json"))); metas[r["sdate"]] = r
    for p in sorted(glob.glob(os.path.join(W, "days", "20??-??-??.failed.json"))):
        r = json.load(open(p)); metas.setdefault(r["sdate"], r)
    metas = [r for k, r in metas.items() if k >= first]
    buf = io.StringIO()
    w = csv.DictWriter(buf, DAY_FIELDS, lineterminator="\n")
    w.writeheader()
    for r in sorted(metas, key=lambda x: x["sdate"]):
        w.writerow({k: r.get(k) for k in DAY_FIELDS})
    changed = [p for p, t in [(os.path.join(OUT, "days.csv"), buf.getvalue())] if write_if_changed(p, t)]
    for f in sorted(glob.glob(os.path.join(W, "ewt", "daily", "20??-??.csv"))):
        if write_if_changed(os.path.join(OUT, "daily", os.path.basename(f)), open(f).read()):
            changed.append(os.path.join(OUT, "daily", os.path.basename(f)))
    for f in sorted(glob.glob(os.path.join(W, "ewt", "compare-20??-??.json"))):
        if write_if_changed(os.path.join(OUT, os.path.basename(f)), open(f).read()):
            changed.append(os.path.join(OUT, os.path.basename(f)))
    log("rt: %s" % ("wrote " + ", ".join(os.path.relpath(p, ROOT) for p in changed) if changed else "no file changed"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--now", help="as if run at this UTC time (ISO), for tests")
    a = ap.parse_args()
    if not os.path.isdir(os.path.join(H, "history")):
        log(f"muni-rt-daily: not on the VM ({H}/history missing); last good data/muni-ewt/rt kept")
        return 0
    now = dt.datetime.fromisoformat(a.now).replace(tzinfo=dt.timezone.utc) if a.now else dt.datetime.now(dt.timezone.utc)
    last = newest_511_month()
    first = max(ARCHIVE_FIRST, month_after(last) if last else ARCHIVE_FIRST)
    end = complete_through(now)
    log(f"muni-rt-daily: 511 has posted through {last}; archive days {first} to {end}")
    d, months = first, set()
    while d <= end:
        why = needs_build(d)
        if why:
            log(f"day {d}: {why}")
            sf = os.path.join(day_dir(d), "stamp")
            pinned = open(sf).read().split()[2] if os.path.exists(sf) and "is gone" not in why else None
            failed = os.path.join(W, "days", f"{d}.failed.json")
            try:
                build_day(d, pinned)
                if os.path.exists(failed):
                    os.remove(failed)
            except Exception as e:  # noqa: BLE001 - any error in one day, not only a failed subprocess
                # One bad day (no timetable covers it, a snapshot that won't decode) is recorded and retried next run;
                # it doesn't hold back the days after it. A day with an earlier good build keeps it. The newest-day
                # check fails if no day has figures for over two days. The record keeps its first date, so a day
                # that stays failed doesn't rewrite days.csv every morning.
                log(f"day {d}: FAILED, {type(e).__name__}: {str(e)[:300]}")
                if not os.path.exists(failed):
                    json.dump({"sdate": d.strftime("%Y%m%d"), "status": "failed", "source": "rt-archive",
                               "read": dt.datetime.now(TZ).date().isoformat(), "error": str(e)[:300]},
                              open(failed, "w"), indent=1, sort_keys=True)
        months.add(d.strftime("%Y-%m"))
        d += dt.timedelta(days=1)
    for m in sorted(months):
        if ok_days(m):
            build_month(m)
    for m in sorted({os.path.basename(p)[:7] for p in glob.glob(os.path.join(W, "days", "20??-??-??"))}):
        try:
            compare_month(m)
        except Exception as e:  # noqa: BLE001 - the comparison is a report; it never stops the daily figures
            log(f"compare {m}: FAILED, {type(e).__name__}: {str(e)[:300]}; retried next run")
    publish()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        log("muni-rt-daily FAILED:", e)
        sys.exit(1)
