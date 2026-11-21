"""Count each Muni line's crowded trips a day from SFMTA's own crowding levels in our 511 vehicle-position archive, for the line optimizer.

Bryan, 2026-11-14: "use SFMTA's crowding figures but mention
we'll have more accurate ones in a few weeks". The figures here are SFMTA's per-vehicle `occupancy_status`, which SFMTA
sends to 511 in GTFS-Realtime VehiclePositions and our VM saves every 3 minutes to the archive bucket (tools/muni/rt-archive/,
RT_ARCHIVE_BUCKET; one parquet a UTC day under sf/parquet/vehicle_positions/YYYY/MM/).

Crowded trip. SFMTA counts a trip as crowded when it is above capacity at 10% or more of its stops ("Percent of daily
Muni trips crowded by route and month", sfmta.com/reports/percent-daily-muni-trips-crowded-route-and-month; its 2024
deck and 2026 equity update say 5%, a conflict the prior-work note prints). We apply the 10% rule to SFMTA's live
levels: a trip is crowded when STANDING_ROOM_ONLY or fuller (CRUSHED_STANDING_ROOM_ONLY, FULL,
NOT_ACCEPTING_PASSENGERS) at 10% or more of its in-service reads. A read every 3 minutes stands in for a stop; the
standing-room level is SFMTA's feed's, not its crowding capacity, so this counts more trips than SFMTA's report does
(38R: 72% of trips here against 8% in SFMTA's March to May 2026 figure) [inference — mine]. A trip is one
(trip_id, start_date, vehicle_id) with four or more reads.

"EMPTY" reads (Bryan asked whether 44% of in-service reads saying EMPTY means no reading). Checked on 8 to 12 November
2026, 841,549 in-service reads: EMPTY is 89% of reads in a trip's first tenth of stops and 57% in its last, but 3% to 5%
in its middle on the busiest lines in the daytime, and a trip almost never goes from a seated or standing level to EMPTY
and back (23 of 229,000 EMPTY reads sit between two non-EMPTY reads of another level). So on buses and trains EMPTY is a
real reading of a bus near its terminal, and is kept as empty. The exceptions are vehicles with no counter: every cable
car (PM, PH, CA) and historic streetcar (F) read reports EMPTY, and so do 71 vehicles at every in-service read. Those
lines are left out (NO_COUNTER) and a vehicle that reads EMPTY at every in-service read over the window is treated as
missing, not empty. MID_EMPTY_MAX below fails the step if mid-route EMPTY on the busy lines rises past 15%, because
that would mean the field's meaning changed.

Service day and good hours: a trip's own start_date is its service day, which runs 04:00 to 01:00 the next day (Pacific),
21 clock hours. A clock hour is good when the archive holds at least SNAP_HOUR (15) of its 20 three-minute snapshots;
reads in a short hour are dropped, and the rest of the day is kept. A service day is counted when the archive spans its
whole window (a snapshot at or before 04:00 and one at or after 01:00 next day, so a day still running or cut off by the
window's edge is never counted) and at least MIN_GOOD_HOURS (16) of its 21 hours are good. Why 16: a 511 outage
overnight takes one or two hours (13 and 15 Nov 2026 sent empty feeds for an hour or two and each lost the whole day
under the old every-hour rule), and allowing up to five short hours keeps such a day while one with a quarter or more
of its hours gone, which would tilt its totals toward whatever hours remain, stays out. service_hours() is the one
test; crowding_by_hour.py and crowding_levels.py import it.

Per-day totals here (trips, crowded trips, reads, crowded reads) cover the day's good hours only; hours_short names the
day's short hours (blank on a whole day), and a trip that crosses one keeps its reads in the good hours.

Incremental (--update): lists the bucket's daily parquet files with their sizes and downloads only those missing from
.cache/rt-archive/vehicle_positions/ or whose size changed (the newest day's file grows until the day closes). A failed
download keeps the cached copy. Then every cached day in the newest WINDOW_DAYS complete days is summarised again from
the local files, which is cheap (DuckDB over parquet), so the output is the same bytes when nothing new arrived.

Output: data/muni-ewt/optimizer/crowding_days.csv, one row a line and service day: trips, crowded trips, in-service
reads, crowded reads, the hours (06 to 21) with no in-service read, and the day's short hours. Sorted, no run stamp.
Checks, run before writing; a failure exits 1 and keeps the old file: at least one counted day; crowded <= trips;
mid-route EMPTY on the busy lines under MID_EMPTY_MAX; every optimizer line (data/muni-ewt/lever/out/car_miles_lines.csv)
present on every counted day with reads in every one of its own good hours from 06 to 21 (its own hours: those it has
reads on in most of the same day type's days that have that hour good).
Usage: ~/.venvs/sf-works-geo/bin/python -I tools/muni/muni-ewt/optimizer_crowding.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, glob, io, os, subprocess, sys

import duckdb

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402

CACHE = os.environ.get("RT_VP_CACHE") or os.path.join(ROOT, ".cache", "rt-archive", "vehicle_positions")
OUT = os.path.join(ROOT, "data", "muni-ewt", "optimizer", "crowding_days.csv")
LINES = os.path.join(ROOT, "data", "muni-ewt", "lever", "out", "car_miles_lines.csv")
WINDOW_DAYS = 28
CROWDED = ("STANDING_ROOM_ONLY", "CRUSHED_STANDING_ROOM_ONLY", "FULL", "NOT_ACCEPTING_PASSENGERS")
TRIP_SHARE = 0.10   # SFMTA's report rule: crowded at 10% or more of stops
MIN_READS = 4
NO_COUNTER = ("PM", "PH", "CA", "F")
HOURS = list(range(6, 22))
SNAP_HOUR = 15      # of the 20 snapshots an hour, for the hour to be good
MIN_GOOD_HOURS = 16  # of a service day's 21 hours (04:00 to 01:00 next day), for the day to count; see the docstring
MID_EMPTY_MAX = 0.15
BUSY = ("1", "14R", "22", "30", "38R", "49", "5R", "N")
FIELDS = ["line", "day", "trips", "crowded_trips", "reads", "crowded_reads", "hours_missing", "hours_short"]


RT_PY = os.environ.get("RT_PY") or os.path.expanduser("~/.venvs/rt-archive/bin/python")
RT_LIB = os.path.dirname(paths.script("rtarchive.py"))
PREFIX = "sf/parquet/vehicle_positions"  # the object prefix inside the bucket (RT_ARCHIVE_BUCKET, read by rtarchive.py)


def gcs(code, *args):
    """Run `code` in the rt-archive venv, which has the GCS client (this venv doesn't), with `B` bound to the archive
    bucket, as rt_daily.py does. Not gsutil: the daily timer's PATH has no /snap/bin, and gsutil failed the
    muni-crowding step there on 2026-11-17 with FileNotFoundError. Returns the CompletedProcess, or None if the
    rt-archive venv is missing."""
    if not os.path.exists(RT_PY):
        return None
    pre = "import sys; sys.path.insert(0, sys.argv[1]); import rtarchive as R; B = R.bucket(); "
    return subprocess.run([RT_PY, "-c", pre + code, RT_LIB, *args], capture_output=True, text=True)


def fetch():
    """Download the bucket's daily files that are new or whose size changed. Returns (fetched, failed)."""
    os.makedirs(CACHE, exist_ok=True)
    ls = gcs("[print(b.size, b.name) for b in B.list_blobs(prefix=sys.argv[2]) if b.name.endswith('.parquet')]",
             PREFIX + "/")
    if ls is None or ls.returncode != 0:
        why = f"no rt-archive venv at {RT_PY}" if ls is None else ls.stderr.strip()[-200:]
        print(f"optimizer_crowding: listing the archive failed, keeping the cached days: {why}")
        return 0, 1
    got = fail = 0
    for line in ls.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].endswith(".parquet"):
            continue
        size, name = int(parts[0]), parts[1]
        local = os.path.join(CACHE, os.path.basename(name))
        if os.path.exists(local) and os.path.getsize(local) == size:
            continue
        tmp = local + ".part"
        r = gcs("B.blob(sys.argv[2]).download_to_filename(sys.argv[3])", name, tmp)
        if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) != size:
            print(f"optimizer_crowding: {name} failed to download, keeping the cached copy")
            fail += 1
            if os.path.exists(tmp):
                os.remove(tmp)
            continue
        os.replace(tmp, local)
        got += 1
    return got, fail


def day_type(d):
    return "weekend" if dt.datetime.strptime(d, "%Y%m%d").weekday() >= 5 else "weekday"


def clock_hour(d, h):
    """The clock hour 'YYYY-MM-DD HH' that hour of day `h` of service day `d` (YYYYMMDD) falls in: hours 0 to 3 are the
    next morning's."""
    day = dt.datetime.strptime(d, "%Y%m%d") + dt.timedelta(days=1 if h < 4 else 0)
    return day.replace(hour=h).strftime("%Y-%m-%d %H")


GOOD_SQL = "strftime(lt, '%Y-%m-%d %H') IN (SELECT h FROM goodh)"  # a read in a good clock hour (table from service_hours)


def service_hours(con, snap_hour=SNAP_HOUR, min_hours=MIN_GOOD_HOURS):
    """(counted, short, good) over table v (lt: Pacific wall time; start_date): the counted service days, sorted; each
    counted day's short hours of day, {day: ['00', ...]}, whole days left out; and every good clock hour
    'YYYY-MM-DD HH'. Also creates table goodh(h) of the good clock hours, for GOOD_SQL."""
    per = con.execute("SELECT strftime(lt, '%Y-%m-%d %H'), count(DISTINCT lt) FROM v GROUP BY 1").fetchall()
    good = sorted(h for h, n in per if n >= snap_hour)
    con.execute("CREATE OR REPLACE TABLE goodh (h VARCHAR)")
    if good:
        con.executemany("INSERT INTO goodh VALUES (?)", [(h,) for h in good])
    good = set(good)
    first, last = con.execute("SELECT min(lt), max(lt) FROM v").fetchone()
    days = sorted(r[0] for r in con.execute("SELECT DISTINCT start_date FROM v WHERE start_date IS NOT NULL").fetchall())
    counted, short = [], {}
    for d in days:
        a = dt.datetime.strptime(d, "%Y%m%d").replace(hour=4)
        if first is None or first > a or last < a + dt.timedelta(hours=21):
            continue  # the archive doesn't span the whole service day
        hrs = [(a + dt.timedelta(hours=i)).strftime("%Y-%m-%d %H") for i in range(21)]
        bad = [h[-2:] for h in hrs if h not in good]
        if 21 - len(bad) >= min_hours:
            counted.append(d)
            if bad:
                short[d] = bad
    return counted, short, good


def days_with_hour(counted, good):
    """{(day type, hour of day): counted days of that type whose clock hour for that hour of day is good}."""
    out = {}
    for d in counted:
        for h in range(24):
            if clock_hour(d, h) in good:
                out[(day_type(d), h)] = out.get((day_type(d), h), 0) + 1
    return out


def summarise(files, lines_wanted):
    """(rows, errors, stats) for the newest WINDOW_DAYS complete service days in `files`."""
    errors = []
    con = duckdb.connect()
    con.execute("SET threads=1")
    src = ", ".join(f"'{f}'" for f in files)
    # local (Pacific) wall time as a plain timestamp, so nothing here depends on the process's time zone
    con.execute(f"""CREATE TABLE v AS SELECT DISTINCT snapshot_time AT TIME ZONE 'America/Los_Angeles' lt, trip_id, start_date,
        route_id, vehicle_id, current_stop_sequence seq, occupancy_status st,
        hour(snapshot_time AT TIME ZONE 'America/Los_Angeles') hr
      FROM read_parquet([{src}])""")
    complete, short, good = service_hours(con)
    complete = complete[-WINDOW_DAYS:]
    if not complete:
        return [], ["no counted service day in the archive"], {}
    inl = ", ".join(f"'{d}'" for d in complete)
    con.execute(f"CREATE TABLE s AS SELECT * FROM v WHERE trip_id IS NOT NULL AND st IS NOT NULL AND start_date IN ({inl}) AND {GOOD_SQL}")
    # a vehicle with no counter reads EMPTY at every in-service read
    con.execute("CREATE TABLE nocount AS SELECT vehicle_id FROM s GROUP BY 1 HAVING bool_and(st = 'EMPTY')")
    crowded = ", ".join(f"'{c}'" for c in CROWDED)
    nc = ", ".join(f"'{c}'" for c in NO_COUNTER)
    con.execute(f"""CREATE TABLE t AS SELECT route_id line, start_date sday, trip_id, vehicle_id, count(*) n,
        sum((st IN ({crowded}))::int) c
      FROM s WHERE route_id NOT IN ({nc}) AND vehicle_id NOT IN (SELECT vehicle_id FROM nocount)
      GROUP BY ALL""")
    rows = {}
    for line, day, trips, ct, reads, cr in con.execute(f"""SELECT line, sday, count(*) FILTER (WHERE n >= {MIN_READS}),
          count(*) FILTER (WHERE n >= {MIN_READS} AND c >= {TRIP_SHARE} * n), sum(n), sum(c) FROM t GROUP BY 1, 2""").fetchall():
        rows[(line, day)] = {"line": line, "day": f"{day[:4]}-{day[4:6]}-{day[6:]}", "trips": int(trips), "crowded_trips": int(ct),
                             "reads": int(reads), "crowded_reads": int(cr), "hours_missing": "",
                             "hours_short": " ".join(short.get(day, []))}
    have = {}
    for line, day, hr in con.execute(f"""SELECT DISTINCT route_id, start_date, hr FROM s
          WHERE route_id NOT IN ({nc}) AND vehicle_id NOT IN (SELECT vehicle_id FROM nocount)""").fetchall():
        have.setdefault((line, day), set()).add(hr)
    # a line's own hours, by weekday or weekend: those with reads on most of that day type's counted days that have the
    #   hour good (a Rapid that stops at 7pm and doesn't run weekends has no evening or weekend hours to miss)
    kind = day_type
    own = {}
    for (line, day), hrs in have.items():
        for h in hrs:
            k = own.setdefault((line, kind(day)), {})
            k[h] = k.get(h, 0) + 1
    ndays = days_with_hour(complete, good)
    for (line, day), r in rows.items():
        hrs = [h for h in HOURS if own.get((line, kind(day)), {}).get(h, 0) * 2 > ndays.get((kind(day), h), 0)
               and clock_hour(day, h) in good]
        r["hours_missing"] = " ".join(f"{h:02d}" for h in hrs if h not in have.get((line, day), set()))
    # mid-route EMPTY on the busy lines in the daytime: the check that EMPTY still means a real empty bus
    busy = ", ".join(f"'{b}'" for b in BUSY)
    mid = con.execute(f"""WITH p AS (SELECT st, hr, route_id, seq::double / max(seq) OVER (PARTITION BY trip_id, start_date, vehicle_id) pos
          FROM s WHERE route_id IN ({busy}))
        SELECT avg((st = 'EMPTY')::int) FROM p WHERE pos > 0.2 AND pos <= 0.8 AND hr BETWEEN 7 AND 18""").fetchone()[0]
    stats = {"complete_days": complete, "short_hours": {d: short[d] for d in complete if d in short}, "mid_empty": mid,
             "no_counter_vehicles": con.execute("SELECT count(*) FROM nocount").fetchone()[0]}
    if mid is None or mid > MID_EMPTY_MAX:
        errors.append(f"mid-route EMPTY on the busy lines is {mid}, over {MID_EMPTY_MAX}: check what EMPTY means now")
    out = [rows[k] for k in sorted(rows)]
    for r in out:
        if r["crowded_trips"] > r["trips"] or r["crowded_reads"] > r["reads"]:
            errors.append(f"{r['line']} {r['day']}: more crowded than counted")
    for ln in lines_wanted:
        for d in complete:
            r = rows.get((ln, d))
            if not r or r["trips"] == 0:
                errors.append(f"line {ln} has no counted trip on {d}")
            elif r["hours_missing"]:
                errors.append(f"line {ln} on {d} has no in-service read at hours {r['hours_missing']}")
    return out, errors, stats


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv):
    if "--update" in argv:
        got, fail = fetch()
        print(f"optimizer_crowding: {got} day file(s) fetched, {fail} failed")
    files = sorted(glob.glob(os.path.join(CACHE, "*.parquet")))
    if not files:
        print("optimizer_crowding: no cached day files; run with --update")
        return 1
    with open(LINES, encoding="utf-8") as f:
        wanted = sorted(r["line"] for r in csv.DictReader(f))
    rows, errors, stats = summarise(files, wanted)
    if errors:
        for e in errors:
            print(f"optimizer_crowding: FAIL {e}")
        print("optimizer_crowding: kept the previous crowding_days.csv")
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    changed = stable.write_text(OUT, to_csv(rows))
    print(f"optimizer_crowding: {len(stats['complete_days'])} counted days {stats['complete_days'][0]} to {stats['complete_days'][-1]} "
          f"(short hours {stats['short_hours'] or 'none'}), "
          f"{len(rows)} line-days, mid-route EMPTY {stats['mid_empty']:.3f}, {stats['no_counter_vehicles']} vehicles with no counter; "
          f"{'wrote' if changed else 'unchanged'} {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
