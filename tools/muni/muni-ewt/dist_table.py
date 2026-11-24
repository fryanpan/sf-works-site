"""One distance and timepoint table for every Muni month, built from every 511 month that carries shape distances.

Speed needs miles between consecutive timepoints. 511's stop_times carry shape_dist_traveled (miles) from 2023-01 but
not in 2022 or in the stand-in months, and before this table each kind of month measured distance its own way, which
read about 2% to 3% apart (Fable review 3, item 4). So every month now takes its distances from here:
  stop_pairs.parquet  route_id, dir, s0, s1, dist: for each route, direction and pair of consecutive stops, the median
                      over months of the month's median shape_dist_traveled difference; n_months beside it
  timepoints.parquet  route_id, stop, tp: a stop is a timepoint on a route if any 511 month flags it as one
  route_types.csv     route (without 'SF:'), route_type (GTFS: 0 tram, 3 bus, 5 cable car), from the newest month
                      that carries the route, over every month 2022 on
Keyed on direction, so a stop served by both directions keeps a distance in each.
Usage: PYTHONPATH=pylib python3 dist_table.py <history dir> <outdir>
"""
import sys, os, glob, duckdb
hist, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=5; SET memory_limit='16GB'; SET preserve_insertion_order=false")
rd = lambda dd, f: f"read_csv('{dd}/{f}', header=true, all_varchar=true)"
months = sorted(glob.glob(f"{hist}/regional-20??-??-so-sf"))
con.execute("CREATE TABLE pm (route_id VARCHAR, dir VARCHAR, s0 VARCHAR, s1 VARCHAR, dist DOUBLE, m VARCHAR)")
con.execute("CREATE TABLE tpm (route_id VARCHAR, stop VARCHAR, tp BOOLEAN)")
con.execute("CREATE TABLE rt (route VARCHAR, route_type VARCHAR, m VARCHAR)")
for d in months:
    m = os.path.basename(d)[9:16]
    if not os.path.exists(f"{d}/stop_times.csv.gz"): continue
    con.execute(f"INSERT INTO rt SELECT replace(route_id,'SF:',''), route_type, '{m}' FROM {rd(d, 'routes.csv.gz')}")
    c = {x[0] for x in con.execute(f"SELECT * FROM {rd(d, 'stop_times.csv.gz')} LIMIT 0").description}
    if "timepoint" in c:
        con.execute(f"""INSERT INTO tpm SELECT t.route_id, s.stop_id, bool_or(s.timepoint = '1') FROM {rd(d, 'stop_times.csv.gz')} s
          JOIN {rd(d, 'trips.csv.gz')} t USING (trip_id) GROUP BY 1, 2""")
    if "shape_dist_traveled" not in c: continue
    con.execute(f"""INSERT INTO pm SELECT route_id, dir, s0, s1, median(dd), '{m}' FROM (
        SELECT t.route_id, t.direction_id dir, lag(s.stop_id) OVER w s0, s.stop_id s1,
          TRY_CAST(nullif(s.shape_dist_traveled,'') AS DOUBLE) - lag(TRY_CAST(nullif(s.shape_dist_traveled,'') AS DOUBLE)) OVER w dd
        FROM {rd(d, 'stop_times.csv.gz')} s JOIN {rd(d, 'trips.csv.gz')} t USING (trip_id)
        WINDOW w AS (PARTITION BY s.trip_id ORDER BY CAST(s.stop_sequence AS INT)))
      WHERE s0 IS NOT NULL AND dd IS NOT NULL AND dd >= 0 GROUP BY 1, 2, 3, 4""")
    print(m, flush=True)
con.execute(f"""COPY (SELECT route_id, dir, s0, s1, round(median(dist), 5) dist, count(*) n_months FROM pm GROUP BY ALL ORDER BY ALL)
  TO '{out}/stop_pairs.parquet' (FORMAT parquet)""")
con.execute(f"COPY (SELECT route_id, stop, bool_or(tp) tp FROM tpm GROUP BY ALL ORDER BY ALL) TO '{out}/timepoints.parquet' (FORMAT parquet)")
con.execute(f"COPY (SELECT route, arg_max(route_type, m) route_type FROM rt GROUP BY 1 ORDER BY 1) TO '{out}/route_types.csv' (HEADER)")
print(con.execute(f"SELECT count(*), count(DISTINCT route_id) FROM '{out}/stop_pairs.parquet'").fetchone(),
      con.execute(f"SELECT count(*) FILTER (WHERE tp) FROM '{out}/timepoints.parquet'").fetchone())
