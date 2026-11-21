"""How full Muni buses are, by occupancy level: each line and direction by hour of day and by tenth of the route, from our 511 vehicle-position archive.

Bryan, 2026-11-16 on a line's page: "Do we have a sense of where the
crowding is along the line too?", then "Can we show the live crowding level instead as an area chart showing all four
types, and use a separate chart for inbound vs. outbound". The line pages and the overview draw these as stacked areas.

Levels. Every occupancy_status SFMTA's feed can send is its own column, unmerged (Bryan, 2026-11-16, thread
1b9on6wr4q9i: "is there a separate rating for full? Please keep all of the original categories"): empty, many_seats,
few_seats, standing_room, crushed, full, not_accepting. On 8 to 16 November 2026 the feed sent EMPTY, MANY_SEATS,
FEW_SEATS and STANDING_ROOM_ONLY for nearly every read, FULL and NOT_ACCEPTING_PASSENGERS a few hundred times, and
CRUSHED_STANDING_ROOM_ONLY never. A read with any other level stops the run.

Rules are crowding_by_hour.py's and optimizer_crowding.py's, imported, not restated: an in-service read has a trip_id
and an occupancy_status; lines with no passenger counter (NO_COUNTER) and vehicles that read EMPTY at every in-service
read are left out; only buses (trolley and motor coaches, MODE_SQL); a clock hour counts when the archive holds SNAP_HOUR
of its 20 snapshots, a service day when MIN_GOOD_HOURS of its 21 hours 04:00 to 01:00 do, and a counted day's short
hours are dropped with the rest of the day kept (optimizer_crowding.service_hours). Hours are Pacific wall-clock hours.
The hours CSV's `days` is the counted days of that day type with in-service reads in that hour, as crowding_by_hour.py's;
the along CSV's is the counted weekdays, and its tenths hold the reads of their good hours.
crowding_by_hour.csv stays as it is for the optimizer; this writes its own files.

Position along the route (weekdays only): a read's current_stop_sequence over the trip's highest in the archive, as
optimizer_crowding.py reads it, rescaled so the first stop is 0 and the last 1, (seq - 1) / (max - 1), and binned into
tenths 0 to 9 (1.0 in tenth 9), the bins the line page's other along-the-line charts use. A trip is one (trip_id,
start_date, vehicle_id) with at least MIN_READS reads and a highest sequence above 1, both taken over all its in-service
reads, short hours included, so a trip that crosses a short hour keeps its true length. [inference — mine] The highest
sequence seen stands in for the trip's last stop; a trip whose last reads were lost is stretched a little.

Run on the GCP VM (team rule: heavy reads stay off the laptop), over the day parquets the archive and its backfill hold.
Outputs, sorted, no run stamp: --hours CSV (line, direction, day_type, hour), --along CSV (line, direction, tenth), each
with days, reads and a count at each level; --json, the counted days by day type (complete_days, the name the quality
check reads) and each one's short hours of day (short_hours).
Checks before writing (a failure exits 1 and writes nothing): at least two counted weekdays; no level outside the
seven above; the level counts add up to reads on every row; every tenth 0 to 9.
Usage: python3 crowding_levels.py DIR/*.parquet --hours H.csv --along A.csv --json OUT.json
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, paths.ROOT)  # for optimizer_crowding.py's lib import

MIN_READS = 4  # optimizer_crowding.py's trip floor
LEVELS = {"EMPTY": "empty", "MANY_SEATS_AVAILABLE": "many_seats", "FEW_SEATS_AVAILABLE": "few_seats", "STANDING_ROOM_ONLY": "standing_room",
          "CRUSHED_STANDING_ROOM_ONLY": "crushed", "FULL": "full", "NOT_ACCEPTING_PASSENGERS": "not_accepting"}


def write(path, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())


def summarise(files, hours_path, along_path, json_path):
    import duckdb
    from optimizer_crowding import CROWDED, GOOD_SQL, NO_COUNTER, service_hours
    from crowding_by_hour import MODE_SQL
    con = duckdb.connect()
    con.execute("SET threads=1")
    src = ", ".join(f"'{f}'" for f in sorted(files))
    con.execute(f"""CREATE TABLE v AS SELECT DISTINCT snapshot_time AT TIME ZONE 'America/Los_Angeles' lt, trip_id, start_date,
        route_id, direction_id, vehicle_id, current_stop_sequence seq, occupancy_status st,
        hour(snapshot_time AT TIME ZONE 'America/Los_Angeles') hr
      FROM read_parquet([{src}])""")
    complete, short, _ = service_hours(con)
    kind = lambda d: "weekend" if dt.datetime.strptime(d, "%Y%m%d").weekday() >= 5 else "weekday"
    ndays = {k: sum(kind(d) == k for d in complete) for k in ("weekday", "weekend")}
    errors = []
    if ndays["weekday"] < 2:
        errors.append(f"fewer than two counted weekdays: {complete}")
    inl = ", ".join(f"'{d}'" for d in complete) or "''"
    nc = ", ".join(f"'{c}'" for c in NO_COUNTER)
    if set(CROWDED) - set(LEVELS):
        errors.append(f"optimizer_crowding.CROWDED has levels this script doesn't count: {set(CROWDED) - set(LEVELS)}")
    known = ", ".join(f"'{c}'" for c in LEVELS)
    # each trip's read count and highest stop over all its in-service reads, short hours included
    con.execute(f"""CREATE TABLE trips AS SELECT trip_id, start_date, vehicle_id, count(*) n_trip, max(seq) mx FROM v
        WHERE trip_id IS NOT NULL AND st IS NOT NULL AND start_date IN ({inl}) GROUP BY ALL""")
    con.execute(f"""CREATE TABLE s AS SELECT *, {MODE_SQL} AS vmode, CASE WHEN dayofweek(strptime(start_date, '%Y%m%d')) IN (0, 6)
        THEN 'weekend' ELSE 'weekday' END dtype FROM v WHERE trip_id IS NOT NULL AND st IS NOT NULL AND start_date IN ({inl})
        AND {GOOD_SQL}""")
    hdays = dict(((k, int(h)), n) for k, h, n in con.execute("SELECT dtype, hr, count(DISTINCT start_date) FROM s GROUP BY 1, 2").fetchall())  # as crowding_by_hour.py's
    other = con.execute(f"SELECT DISTINCT st FROM s WHERE st NOT IN ({known})").fetchall()
    if other:
        errors.append(f"occupancy levels this script doesn't know: {other}")
    con.execute("CREATE TABLE nocount AS SELECT vehicle_id FROM s GROUP BY 1 HAVING bool_and(st = 'EMPTY')")
    con.execute(f"""CREATE TABLE b AS SELECT s.*, trips.n_trip, trips.mx FROM s JOIN trips USING (trip_id, start_date, vehicle_id)
        WHERE route_id NOT IN ({nc}) AND vehicle_id NOT IN (SELECT vehicle_id FROM nocount) AND vmode IN ('trolley', 'motor')""")
    cols = ", ".join(f"sum((st = '{k}')::int) AS \"{v}\"" for k, v in LEVELS.items())
    counts = f"count(*) n, {cols}"

    def rows_of(q, key, nd):
        out = []
        for r in con.execute(q).fetchall():
            line, d, *rest = r
            k, n, lv = rest[:len(key)], rest[len(key)], [int(x) for x in rest[len(key) + 1:]]
            if sum(lv) != n:
                errors.append(f"{line} {d} {k}: levels add to {sum(lv)}, reads {n}")
            out.append({"line": line, "direction": "" if d is None else int(d), **dict(zip(key, (int(x) if isinstance(x, (int, float)) else x for x in k))),
                        "days": nd(k), "reads": int(n), **dict(zip(LEVELS.values(), lv))})
        return out

    hours = rows_of(f"SELECT route_id, direction_id, dtype, hr, {counts} FROM b GROUP BY ALL ORDER BY 1, 2, 3, 4",
                    ("day_type", "hour"), lambda k: hdays[(k[0], int(k[1]))])
    along = rows_of(f"""SELECT route_id, direction_id, least(9, floor(10 * (seq - 1) / (mx - 1)))::int tenth, {counts} FROM b
          WHERE dtype = 'weekday' AND seq IS NOT NULL AND seq >= 1 AND n_trip >= {MIN_READS} AND mx > 1 GROUP BY ALL ORDER BY 1, 2, 3""",
                    ("tenth",), lambda k: ndays["weekday"])
    for r in along:
        if not 0 <= r["tenth"] <= 9:
            errors.append(f"{r['line']} {r['direction']}: tenth {r['tenth']}")
    if not hours or not along:
        errors.append("no rows")
    if errors:
        for e in errors:
            print(f"crowding_levels: FAIL {e}")
        return 1
    hours.sort(key=lambda r: (r["line"], str(r["direction"]), r["day_type"], r["hour"]))
    along.sort(key=lambda r: (r["line"], str(r["direction"]), r["tenth"]))
    write(hours_path, hours)
    write(along_path, along)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"complete_days": {k: [d for d in complete if kind(d) == k] for k in ("weekday", "weekend")}, "short_hours": short},
                  f, indent=1, sort_keys=True)
        f.write("\n")
    tot = {v: sum(r[v] for r in hours) for v in LEVELS.values()}
    print(f"crowding_levels: counted days {complete}, short hours {short or 'none'}; {len(hours)} hour rows, {len(along)} tenth rows; reads by level {tot}")
    return 0


def main(argv):
    if any(k not in argv for k in ("--hours", "--along", "--json")):
        print(__doc__)
        return 2
    arg = lambda k: argv[argv.index(k) + 1]
    return summarise([a for a in argv if a.endswith(".parquet")], arg("--hours"), arg("--along"), arg("--json"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
