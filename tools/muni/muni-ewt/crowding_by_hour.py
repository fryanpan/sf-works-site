"""Crowded share of each Muni bus line and direction by hour of day, and buses in service systemwide by hour, from our 511 vehicle-position archive.

Bryan, on the Upgrade a Bus Line tool, 2026-11-16: "Does bus crowding happen on every line at
the same time, or is it possible to do some scheduling magic to shift busses around between lines to help alleviate
crowding?" This answers the data half: when each line is crowded, and how many buses are out at each hour.

Rules are optimizer_crowding.py's, imported from it, not restated: an in-service read has a trip_id and an
occupancy_status; crowded is STANDING_ROOM_ONLY or fuller (CROWDED); lines with no passenger counter (NO_COUNTER: cable
cars, F) and vehicles that read EMPTY at every in-service read are left out; a clock hour counts when the archive holds
at least SNAP_HOUR of its 20 three-minute snapshots, and a service day (the trip's start_date) counts when at least
MIN_GOOD_HOURS of its 21 hours, 04:00 to 01:00 next day Pacific, do (optimizer_crowding.service_hours). Reads in a
counted day's short hours are dropped and the rest of the day kept, so each hour's figures cover the days that have
that hour: the CSV's `days` is the number of counted days of that day type with in-service reads in that hour (every
good hour from 04:00 to 01:00 has them), and buses_avg divides by that hour's snapshots on those days. The JSON's complete_days are the counted days and short_hours each one's short
hours of day. Hours are Pacific wall-clock hours of the snapshot; reads after midnight stay with their service day.

Vehicle type from the vehicle number [inference — mine, from which lines each number series runs on in the archive]:
57xx, 58xx and 72xx run only on overhead-wire lines and are counted as trolley coaches; other four-digit numbers outside
1xxx and 2xxx (light rail and historic cars) are motor coaches. A line is a trolley line when trolley coaches make most of
its in-service reads.

Two steps, both run on the GCP VM (team rule: heavy reads stay off the laptop):
  build DAY...      decode one UTC day of raw spooled snapshots into DIR/DAY.parquet with the archiver's own compact()
                    (for days the daily compaction has not uploaded); needs the rt-archive venv. --out DIR.
  summarise FILE... DuckDB over the day parquets; writes --csv (line x direction x day type x hour) and --json (fleet by
                    hour and per-line peak hours). Sorted, no run stamp.
Checks before writing (a failure exits 1 and writes nothing): at least two counted weekdays; crowded reads <= reads;
every hour 06-21 has buses in service.
Usage: python3 crowding_by_hour.py build 2026-11-13 --out DIR
       python3 crowding_by_hour.py summarise DIR/*.parquet --csv OUT.csv --json OUT.json
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, paths.ROOT)

MIN_LINE_HOUR_READS = 60   # reads in a line-direction-hour, over the window, before its share is used to name a peak
WINDOWS = {"am_peak": range(7, 10), "midday": range(10, 14), "school_pm": range(14, 16), "pm_peak": range(16, 19),
           "evening": range(19, 24), "early": range(4, 7), "night": range(0, 4)}


def vehicle_mode(v):
    if not v or len(v) != 4 or not v.isdigit():
        return "other"
    if v[0] in "12":
        return "rail"
    if v[:2] in ("57", "58", "72"):
        return "trolley"
    return "motor"


# vehicle_mode() as SQL, so DuckDB needs no Python UDF
MODE_SQL = ("CASE WHEN NOT regexp_matches(coalesce(vehicle_id, ''), '^[0-9]{4}$') THEN 'other' "
            "WHEN left(vehicle_id, 1) IN ('1', '2') THEN 'rail' "
            "WHEN left(vehicle_id, 2) IN ('57', '58', '72') THEN 'trolley' ELSE 'motor' END")


def window_of(h):
    for k, r in WINDOWS.items():
        if h in r:
            return k
    return "other"


def build(days, out):
    sys.path.insert(0, os.environ.get("RT_ARCHIVE_SRC", os.path.expanduser("~/rt-archive/bin")))
    import compact  # the archiver's own decoder, so the columns match the uploaded parquets
    os.makedirs(out, exist_ok=True)
    for d in days:
        p = os.path.join(out, d + ".parquet")
        n, rows = compact.compact("vehicle_positions", dt.date.fromisoformat(d), None, p)
        print(f"crowding_by_hour: built {p}: {n} snapshots, {rows} rows")


def summarise(files, csv_path, json_path):
    import duckdb
    from optimizer_crowding import CROWDED, GOOD_SQL, NO_COUNTER, service_hours
    con = duckdb.connect()
    con.execute("SET threads=1")  # one thread, so the fleet means sum in one order and a rerun writes the same bytes
    src = ", ".join(f"'{f}'" for f in sorted(files))
    con.execute(f"""CREATE TABLE v AS SELECT DISTINCT snapshot_time AT TIME ZONE 'America/Los_Angeles' lt, trip_id, start_date,
        route_id, direction_id, vehicle_id, occupancy_status st, hour(snapshot_time AT TIME ZONE 'America/Los_Angeles') hr
      FROM read_parquet([{src}])""")
    complete, short, _ = service_hours(con)
    kind = lambda d: "weekend" if dt.datetime.strptime(d, "%Y%m%d").weekday() >= 5 else "weekday"
    errors = []
    if sum(kind(d) == "weekday" for d in complete) < 2:
        errors.append(f"fewer than two counted weekdays: {complete}")
    inl = ", ".join(f"'{d}'" for d in complete) or "''"
    nc = ", ".join(f"'{c}'" for c in NO_COUNTER)
    cr = ", ".join(f"'{c}'" for c in CROWDED)
    con.execute(f"CREATE TABLE s AS SELECT *, {MODE_SQL} AS vmode, CASE WHEN dayofweek(strptime(start_date, '%Y%m%d')) IN (0, 6) "
                f"THEN 'weekend' ELSE 'weekday' END dtype FROM v WHERE trip_id IS NOT NULL AND st IS NOT NULL AND start_date IN ({inl}) AND {GOOD_SQL}")
    con.execute("CREATE TABLE nocount AS SELECT vehicle_id FROM s GROUP BY 1 HAVING bool_and(st = 'EMPTY')")
    con.execute(f"CREATE TABLE b AS SELECT * FROM s WHERE route_id NOT IN ({nc}) AND vehicle_id NOT IN (SELECT vehicle_id FROM nocount) "
                f"AND vmode IN ('trolley', 'motor')")
    ndays = {k: sum(kind(d) == k for d in complete) for k in ("weekday", "weekend")}
    # a line's type: the vehicle type making most of its in-service reads over the window
    ltype = dict(con.execute("""SELECT route_id, CASE WHEN avg((vmode = 'trolley')::int) > 0.5 THEN 'trolley' ELSE 'motor' END
        FROM b GROUP BY 1""").fetchall())
    # counted days with in-service reads in the hour, by day type and hour of day: the days that have the hour good
    hdays = dict(((k, int(h)), n) for k, h, n in con.execute("SELECT dtype, hr, count(DISTINCT start_date) FROM s GROUP BY 1, 2").fetchall())
    rows = []
    # buses_avg: the line-direction's in-service reads over every snapshot of that hour and day type on the days that
    #   have it good, so a line with one bus at every other snapshot is 0.5
    hour_snaps = {(k, h): n for k, h, n in con.execute("SELECT dtype, hr, count(DISTINCT lt) FROM s GROUP BY 1, 2").fetchall()}
    q = f"""SELECT route_id, direction_id, dtype, hr, count(*) n, sum((st IN ({cr}))::int) c
          FROM b GROUP BY ALL ORDER BY 1, 2, 3, 4"""
    for line, d, dtype, hr, n, c in con.execute(q).fetchall():
        if c > n:
            errors.append(f"{line} {d} {dtype} {hr}: crowded reads over reads")
        rows.append({"line": line, "line_type": ltype.get(line, "motor"), "direction": "" if d is None else int(d),
                     "day_type": dtype, "hour": int(hr), "days": hdays[(dtype, int(hr))], "reads": int(n), "crowded_reads": int(c),
                     "crowded_share": round(c / n, 4), "buses_avg": round(n / hour_snaps[(dtype, hr)], 2)})
    # systemwide buses in service per snapshot, by type, averaged within hour and day type; a bus with no working
    # counter (EMPTY at every read) is still a bus in service, so the nocount exclusion is for crowding only
    fleet = {}
    for dtype, hr, mode, mean_, mx in con.execute(f"""WITH p AS (SELECT dtype, hr, lt, vmode, count(DISTINCT vehicle_id) n
            FROM s WHERE vmode IN ('trolley', 'motor') AND route_id NOT IN ({nc}) GROUP BY ALL)
          SELECT dtype, hr, vmode, avg(n), max(n) FROM p GROUP BY ALL ORDER BY ALL""").fetchall():
        fleet.setdefault(dtype, {}).setdefault(str(hr), {})[mode] = {"mean": round(mean_, 1), "max": int(mx)}
    for dtype in fleet:
        for h in range(6, 22):
            if str(h) not in fleet[dtype]:
                errors.append(f"{dtype}: no buses in service at hour {h}")
    # each line-direction's weekday peak hour, from hours with enough reads
    peaks = []
    by = {}
    for r in rows:
        if r["day_type"] == "weekday" and r["reads"] >= MIN_LINE_HOUR_READS:
            by.setdefault((r["line"], r["direction"]), []).append(r)
    for (line, d), rs in sorted(by.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        top = max(rs, key=lambda r: (r["crowded_share"], -r["hour"]))
        tot_n = sum(r["reads"] for r in rs)
        tot_c = sum(r["crowded_reads"] for r in rs)
        peaks.append({"line": line, "direction": d, "line_type": rs[0]["line_type"], "peak_hour": top["hour"],
                      "peak_window": window_of(top["hour"]), "peak_share": top["crowded_share"],
                      "day_share": round(tot_c / tot_n, 4) if tot_n else 0, "crowded_reads": tot_c})
    if errors:
        for e in errors:
            print(f"crowding_by_hour: FAIL {e}")
        return 1
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"complete_days": complete, "days_by_type": ndays, "short_hours": short, "fleet_by_hour": fleet, "line_peaks": peaks,
                   "no_counter_vehicles": con.execute("SELECT count(*) FROM nocount").fetchone()[0]},
                  f, indent=1, sort_keys=True)
    print(f"crowding_by_hour: {len(complete)} counted days {complete}, short hours {short or 'none'}; {len(rows)} rows to {csv_path}")
    return 0


def main(argv):
    if not argv or argv[0] not in ("build", "summarise"):
        print(__doc__)
        return 2
    if argv[0] == "build":
        out = argv[argv.index("--out") + 1]
        build([a for a in argv[1:] if a[:2] == "20" and a != out], out)
        return 0
    csv_path = argv[argv.index("--csv") + 1]
    json_path = argv[argv.index("--json") + 1]
    files = [a for a in argv[1:] if a.endswith(".parquet")]
    return summarise(files, csv_path, json_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
