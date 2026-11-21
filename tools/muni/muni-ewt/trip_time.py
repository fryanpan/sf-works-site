"""Bus speed and excess trip time for every Muni line, one month of 511 historic stop observations.

Runs after ewt_month.py on the same month (it reads that month's hourly/<m>.parquet for day types and for the hours
and line-days the excess-wait run excluded, so all three measures drop the same outages).
A segment is the stretch between two consecutive timepoints of one trip on one service date (the stops the timetable
times; 511's stop_times.txt flags them). It counts only when BOTH ends were observed, so a trip that started late
from mid-route, was cut short, or lost its tracker part-way contributes only the segments it fully covered:
  dist   miles between the two timepoints along the route (from the distance table, below)
  obs_s  observed seconds between departing the first and the second timepoint
  sch_s  scheduled seconds between the same two timepoints, from the timetable used for SWT
A segment is dropped if either end's clock hour, or its line-day, is excluded in hourly/<m>.parquet, or if
obs_s <= 0, sch_s <= 0, dist <= 0, obs_s > 3 x sch_s + 600 (a stop matched to the wrong visit) or the observed speed
is over 60 mph. The trip's first and last stops are left out: the first as in ewt_month.py (its time is the
terminal departure, often far off), taken as the trip's lowest stop_sequence in the timetable, not sequence 1, because
511 numbers a short trip's stops along the full pattern (a J from Embarcadero starts at 2, a short-turn 8 at 7) and
reports that first stop's observation as 1 in some months (2023-01 to 2024-05, 2026-09 on) and as the timetable's
number in others; the last because until the end of 2022 the feed seldom records it (a trip's last stop is observed
on 18% of trips in 2022-03, its second-to-last on 90%; 89% to 95% from 2023), so a trip measured to its last stop
would not be comparable across years. Cleaning of observations (duplicate visit nearest its scheduled time,
out-of-order rows) is ewt_month.py's, and so is dropping the first stop by the timetable as well as by sequence 1.
Distances and timepoints: from dist_table.py's tables (--tables), the same for every month: a stop's position along a
trip is the running sum of the median miles between consecutive stops for its route over every 511 month from
2023-01 (an ordered stop pair belongs to one direction, so the join needs no direction id, which the stand-in
months number SFMTA's way), and a segment whose stretch holds a stop pair with no distance is dropped (diag
'seg_no_distance'). Timepoint flags are the month's own where it has them, else any 511 month's for that route.
A trip counts for excess trip time only when its first and last interior timepoints are observed and at least 75% of
its interior timepoints are; the window, first to last interior timepoint, is about 70% of the scheduled trip.
Scheduled bus-miles count trips whose first stop is scheduled from 05:00 to 22:59, the hours the speeds cover.
Output, into <outdir>: seg/<m>.parquet (route, sdate, daytype, hr of the segment's scheduled start: nseg, dist,
obs_s, sch_s), trip/<m>.parquet (one row per complete trip: route, dir, sdate, daytype, hr, ntp, dist, obs_s, sch_s),
seg/<m>-busmiles.csv (scheduled bus-miles by route and day type, every scheduled trip from its second stop to its
last, the citywide weight), seg/<m>.json (counts at each step).
Usage: PYTHONPATH=pylib python3 trip_time.py <extract dir> <ewt dir> <YYYY-MM> --tables <dist_table dir>
"""
import sys, os, json, duckdb
args = sys.argv[1:]
opt = lambda k: args[args.index(k) + 1] if k in args else None
d, ewt, month = args[0], args[1], args[2]
tables = opt("--tables")
if not tables: sys.exit("pass --tables <dir> (dist_table.py output)")
os.makedirs(f"{ewt}/seg", exist_ok=True); os.makedirs(f"{ewt}/trip", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=5; SET memory_limit='16GB'; SET preserve_insertion_order=false")
T = lambda c: (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
               f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")
rd = lambda dd, f: f"read_csv('{dd}/{f}', header=true, all_varchar=true)"
one = lambda s: con.execute(s).fetchone()
cols = lambda dd: {x[0] for x in con.execute(f"SELECT * FROM {rd(dd, 'stop_times.csv.gz')} LIMIT 0").description}
M = month.replace("-", "")
diag = {"month": month}

con.execute(f"CREATE TABLE trips AS SELECT trip_id, route_id, direction_id dir, service_id FROM {rd(d, 'trips.csv.gz')}")
con.execute(f"""CREATE TABLE cd AS SELECT service_id, date sdate FROM {rd(d, 'calendar_dates.csv.gz')} GROUP BY 1,2
  HAVING bool_or(exception_type='1') AND NOT bool_or(exception_type='2')""")
c = cols(d)
TP = "CASE WHEN timepoint = '1' THEN true WHEN timepoint = '0' THEN false END" if "timepoint" in c else "NULL::BOOLEAN"
con.execute(f"""CREATE TABLE st0 AS SELECT s.trip_id, t.route_id, t.dir, CAST(s.stop_sequence AS INT) seq, s.stop_id stop,
  {T("coalesce(nullif(s.departure_time,''), s.arrival_time)")} t, {TP} tp
  FROM {rd(d, 'stop_times.csv.gz')} s JOIN trips t USING (trip_id)""")
diag["own_timepoints"] = one("SELECT count(tp) > 0.5 * count(*) FROM st0")[0]
if not diag["own_timepoints"]:
    con.execute(f"UPDATE st0 SET tp = coalesce(x.tp, false) FROM read_parquet('{tables}/timepoints.parquet') x WHERE x.route_id = st0.route_id AND x.stop = st0.stop")
    con.execute("UPDATE st0 SET tp = false WHERE tp IS NULL")
# position along the trip: running sum of the distance table's stop-pair miles; npm counts pairs with no distance so
# far, and a segment has a distance only when no pair between its ends is missing
con.execute(f"""CREATE TABLE st AS SELECT z.trip_id, z.route_id, z.seq, z.stop, z.t, z.tp,
    sum(coalesce(p.dist, 0)) OVER w dist, sum(CASE WHEN z.prev IS NOT NULL AND p.dist IS NULL THEN 1 ELSE 0 END) OVER w npm
  FROM (SELECT s.*, lag(s.stop) OVER (PARTITION BY s.trip_id ORDER BY s.seq) prev FROM st0 s) z
  LEFT JOIN (SELECT route_id, s0, s1, avg(dist) dist FROM read_parquet('{tables}/stop_pairs.parquet') GROUP BY ALL) p
    ON p.route_id = z.route_id AND p.s0 = z.prev AND p.s1 = z.stop
  WINDOW w AS (PARTITION BY z.trip_id ORDER BY z.seq ROWS UNBOUNDED PRECEDING)""")
con.execute("DROP TABLE st0")
diag["stop_pairs_with_distance"] = round(one("SELECT 1 - sum(m) / sum(n - 1) FROM (SELECT trip_id, max(npm) m, count(*) n FROM st GROUP BY 1)")[0] or 0, 4)

# day types and exclusions from the excess-wait run of the same month
H = f"read_parquet('{ewt}/hourly/{month}.parquet')"
con.execute(f"CREATE TABLE dt AS SELECT DISTINCT sdate, daytype FROM {H}")
con.execute(f"CREATE TABLE xld AS SELECT DISTINCT 'SF:' || route route_id, sdate FROM {H} WHERE excl = 'line_day_outage'")
con.execute(f"""CREATE TABLE xh AS SELECT DISTINCT sdate, hr FROM {H} WHERE excl = 'feed_outage'
  UNION SELECT sdate, hr FROM {H} GROUP BY 1,2 HAVING sum(ob) < 0.5 * sum(eb)""")

# scheduled bus-miles: every scheduled trip-day, second stop to last
con.execute("""CREATE TABLE tl AS SELECT trip_id, any_value(route_id) route_id, max(dist) FILTER (WHERE seq > mn) - min(dist) FILTER (WHERE seq > mn) miles,
  min(t) // 3600 hr0 FROM (SELECT *, min(seq) OVER (PARTITION BY trip_id) mn FROM st) GROUP BY 1""")
con.execute(f"""COPY (SELECT replace(t.route_id,'SF:','') route, dt.daytype, count(*) sched_trips, round(sum(tl.miles), 2) sched_miles,
    count(tl.miles) trips_with_miles
  FROM trips t JOIN cd USING (service_id) JOIN dt USING (sdate) LEFT JOIN tl USING (trip_id)
  WHERE cd.sdate LIKE '{M}%' AND tl.hr0 BETWEEN 5 AND 22 GROUP BY ALL ORDER BY 1,2) TO '{ewt}/seg/{month}-busmiles.csv' (HEADER)""")

# observations, cleaned as in ewt_month.py, with the first stop also dropped by the timetable (above)
STANDIN = os.path.exists(f"{d}/SCHEDULE_SOURCE")
KEY = "'SFG:' || split_part(split_part(o.trip_id, ':', 2), '_', 1)" if STANDIN else "o.trip_id"
con.execute(f"""CREATE TABLE o0 AS SELECT o.trip_id, {KEY} skey, o.service_date sdate, CAST(o.stop_sequence AS INT) seq, o.to_stop_id stop,
  {T("coalesce(nullif(o.observed_departure_time,''), o.observed_arrival_time)")} a,
  {T("coalesce(nullif(o.scheduled_departure_time,''), o.scheduled_arrival_time)")} s
  FROM {rd(d, 'stop_observations.csv.gz')} o WHERE o.service_date LIKE '{M}%'""")
con.execute("UPDATE o0 SET a = a + 86400 WHERE s IS NOT NULL AND a < s - 43200")
# the first stop goes by the feed's sequence 1 and by the timetable's first stop, whichever number the feed gives it
# (a later visit to the same stop on a loop trip, 17 to 192 trips in 9 of the months from 2022, carries a higher number and stays)
con.execute("CREATE TABLE fst AS SELECT trip_id, arg_min(stop, seq) stop, min(seq) mn FROM st GROUP BY 1")
con.execute("""CREATE TABLE o2 AS SELECT * FROM o0 WHERE seq > 1 AND a IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM fst WHERE fst.trip_id = o0.skey AND fst.stop = o0.stop AND o0.seq <= fst.mn)
  QUALIFY row_number() OVER (PARTITION BY trip_id, sdate, stop ORDER BY abs(a - coalesce(s, a)), a) = 1""")
# rule 3 both ways, as in ewt_month.py: drop the smaller of the forward-flagged and backward-flagged sets per trip-day
con.execute("""CREATE TABLE o3 AS SELECT *, (pm IS NOT NULL AND a < pm - 60) ff, (nm IS NOT NULL AND a > nm + 60) bf FROM
  (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm,
             min(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) nm FROM o2)""")
con.execute("""CREATE TABLE o4 AS SELECT o3.* EXCLUDE (pm, nm, ff, bf) FROM o3 JOIN (SELECT trip_id, sdate, count(*) FILTER (WHERE bf) < count(*) FILTER (WHERE ff) useb
  FROM o3 GROUP BY 1, 2) k USING (trip_id, sdate) WHERE NOT (CASE WHEN k.useb THEN bf ELSE ff END)""")
con.execute("""CREATE TABLE obs AS SELECT * EXCLUDE (pm) FROM (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq
  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm FROM o4) WHERE pm IS NULL OR a >= pm - 60""")
con.execute("DROP TABLE o3; DROP TABLE o4")
diag["obs_clean"] = one("SELECT count(*) FROM obs")[0]

# each observed trip-day's scheduled timepoints (second stop on), with the observed time where the stop was seen;
# where a trip visits a stop twice, the visit nearest the observation's own scheduled time is taken
con.execute("""CREATE TABLE otd AS SELECT DISTINCT trip_id, skey, sdate FROM obs""")
con.execute("CREATE TABLE mxs AS SELECT trip_id, min(seq) mn, max(seq) mx FROM st GROUP BY 1")
con.execute("""CREATE TABLE tps AS SELECT o.trip_id, o.skey, o.sdate, st.route_id, st.seq, st.stop, st.t, st.dist, st.npm,
    row_number() OVER (PARTITION BY o.trip_id, o.sdate ORDER BY st.seq) k, count(*) OVER (PARTITION BY o.trip_id, o.sdate) ntp
  FROM otd o JOIN st ON st.trip_id = o.skey JOIN mxs ON mxs.trip_id = st.trip_id WHERE st.tp AND st.seq > mxs.mn AND st.seq < mxs.mx AND st.t IS NOT NULL""")
con.execute("""CREATE TABLE tpo AS SELECT p.*, x.a FROM tps p LEFT JOIN (
    SELECT p2.trip_id, p2.sdate, p2.k, arg_min(o.a, abs(o.s - p2.t)) a FROM tps p2 JOIN obs o
      ON o.trip_id = p2.trip_id AND o.sdate = p2.sdate AND o.stop = p2.stop GROUP BY ALL) x USING (trip_id, sdate, k)""")
con.execute("""CREATE TABLE trip_dir AS SELECT trip_id, any_value(dir) dir FROM trips GROUP BY 1""")
diag["timepoints_scheduled"] = one("SELECT count(*) FROM tpo")[0]
diag["timepoints_observed"] = one("SELECT count(a) FROM tpo")[0]
OK = lambda h: f"NOT EXISTS (SELECT 1 FROM xh WHERE xh.sdate = z.sdate AND xh.hr = {h}) "
con.execute(f"""CREATE TABLE seg AS SELECT * FROM (
    SELECT p.trip_id, p.sdate, p.route_id, p.t t0, n.t t1, p.a a0, n.a a1, CASE WHEN n.npm = p.npm THEN n.dist - p.dist END dist, n.t - p.t sch_s, n.a - p.a obs_s
    FROM tpo p JOIN tpo n ON n.trip_id = p.trip_id AND n.sdate = p.sdate AND n.k = p.k + 1) z
  WHERE a0 IS NOT NULL AND a1 IS NOT NULL""")
diag["seg_both_ends"] = one("SELECT count(*) FROM seg")[0]
diag["seg_one_end_missing"] = one("SELECT count(*) FROM tpo p JOIN tpo n ON n.trip_id=p.trip_id AND n.sdate=p.sdate AND n.k=p.k+1 WHERE (p.a IS NULL) <> (n.a IS NULL)")[0]
diag["seg_no_distance"] = one("SELECT count(*) FROM seg WHERE dist IS NULL OR dist <= 0")[0]
BOUNDS = "dist > 0 AND sch_s > 0 AND obs_s > 0 AND obs_s <= 3 * sch_s + 600 AND dist / obs_s * 3600 <= 60"
diag["seg_out_of_bounds"] = one(f"SELECT count(*) FROM seg WHERE dist > 0 AND NOT ({BOUNDS})")[0]
WHERE_OK = (f"{OK('z.t0 // 3600')} AND {OK('z.t1 // 3600')} AND NOT EXISTS (SELECT 1 FROM xld WHERE xld.route_id = z.route_id AND xld.sdate = z.sdate)")
diag["seg_excluded_outage"] = one(f"SELECT count(*) FROM seg z WHERE {BOUNDS} AND NOT ({WHERE_OK})")[0]
con.execute(f"""COPY (SELECT replace(z.route_id,'SF:','') route, z.sdate, dt.daytype, z.t0 // 3600 hr, count(*) nseg,
    round(sum(dist), 6) dist, sum(obs_s) obs_s, sum(sch_s) sch_s
  FROM seg z JOIN dt USING (sdate) WHERE {BOUNDS} AND {WHERE_OK} GROUP BY ALL ORDER BY ALL)
  TO '{ewt}/seg/{month}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
diag["seg_kept"] = one(f"SELECT sum(nseg) FROM '{ewt}/seg/{month}.parquet'")[0]

# whole trips: first and last scheduled timepoint (after the first stop) both observed
con.execute("CREATE TABLE nobs AS SELECT trip_id, sdate, count(a) nob FROM tpo GROUP BY 1, 2")
con.execute(f"""CREATE TABLE tr AS SELECT f.trip_id, f.skey, f.sdate, f.route_id, f.ntp, f.t t0, l.t t1, f.a a0, l.a a1,
    CASE WHEN l.npm = f.npm THEN round(l.dist - f.dist, 6) END dist, l.t - f.t sch_s, l.a - f.a obs_s, nobs.nob
  FROM tpo f JOIN tpo l ON l.trip_id = f.trip_id AND l.sdate = f.sdate AND f.k = 1 AND l.k = f.ntp
  JOIN nobs ON nobs.trip_id = f.trip_id AND nobs.sdate = f.sdate WHERE f.ntp >= 2""")
diag["trips_observed"] = one("SELECT count(*) FROM otd")[0]
diag["trips_both_ends"] = one("SELECT count(*) FROM tr WHERE a0 IS NOT NULL AND a1 IS NOT NULL")[0]
diag["trips_both_ends_under_75pct"] = one("SELECT count(*) FROM tr WHERE a0 IS NOT NULL AND a1 IS NOT NULL AND nob < 0.75 * ntp")[0]
TB = "sch_s > 0 AND obs_s > 0 AND obs_s <= 3 * sch_s + 600 AND nob >= 0.75 * ntp"
con.execute(f"""COPY (SELECT replace(z.route_id,'SF:','') route, td.dir, z.sdate, dt.daytype, z.t0 // 3600 hr, z.ntp, z.dist, z.obs_s, z.sch_s
  FROM tr z JOIN dt USING (sdate) LEFT JOIN trip_dir td ON td.trip_id = z.skey
  WHERE a0 IS NOT NULL AND a1 IS NOT NULL AND {TB} AND {WHERE_OK} ORDER BY ALL)
  TO '{ewt}/trip/{month}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
diag["trips_kept"] = one(f"SELECT count(*) FROM '{ewt}/trip/{month}.parquet'")[0]
json.dump(diag, open(f"{ewt}/seg/{month}.json", "w"), indent=1, default=str)
print(json.dumps(diag, default=str))
