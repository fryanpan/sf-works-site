"""Observed and scheduled seconds between each pair of consecutive stops of every Muni line, by period, one 511 month.

Question (Bryan, 2026-11-10, on the excess-wait note): are speed and excess wait better at peak on segments with bus
lanes, and which levers buy the most? trip_time.py measures whole timepoint-to-timepoint stretches; this script keeps
every stop-to-stop pair so a segment can be tagged as in or out of a transit-only lane (stop_pair_lanes.py).

A pair is two stops a trip visits one after the other on one service date, both observed. "One after the other" is by
rank in the trip's own timetable (stop_times ordered by stop_sequence), not stop_sequence n and n+1: some timetables
skip a sequence number (the N and 56 jump from 10 to 12 between stops 16996 and 14447, Fable review 2026-11-10) while
511's observations of the same trips number 9 and 10, so the two numberings can't be mixed; and an
observation is placed in the timetable by its trip and stop, the visit nearest its scheduled time where a trip
passes a stop twice. On a stand-in month (make_sched.py) the timetable trip is 'SFG:' + the Muni trip id, as in
trip_time.py. Observations with no timetable match can't be paired (diag 'obs_no_schedule_match').
Each pair carries two flags. final: its second stop is the trip's last scheduled stop. The last stop's 511 time is not
an arrival there: final pairs run a mean 164 s over schedule (90th percentile 537 s) against 2 s for other pairs in
2026-10 (Fable review), so speed users should leave them out. inwin: both stops lie between the trip's first and
last interior timepoints (second stop to second-to-last, stop_times.timepoint, or dist_table.py's timepoints where the
month has no flags, as trip_time.py), the stretch trip_time.py measures line speed over.
Its time is observed departure at the second stop minus observed departure at the first, so it holds the running
time between the stops PLUS the dwell at the second stop: 511 carries one time per stop (arrival = departure on every
Muni row; dwell_time_secs is 0 throughout, checked on 2022-03, 2024-03 and 2026-09), so dwell can't be split out.
Cleaning of observations (first stop dropped, by sequence 1 and by the timetable's first stop; duplicate visit nearest
its scheduled time; out-of-order rows) is trip_time.py's. Day types, feed-outage hours and line-day outages come from the month's
hourly/<m>.parquet, as in trip_time.py. A pair is dropped when obs_s <= 0, sch_s <= 0, obs_s > 3 x sch_s + 600 (a
stop matched to the wrong visit), or its distance gives over 60 mph.
Period is from the scheduled departure at the first stop: am (07:00-08:59), mid (09:00-15:59), pm (16:00-18:59),
eve (19:00-22:59), early (05:00-06:59); other hours are dropped. Distance is the median miles for that ordered pair
from dist_table.py's stop_pairs.parquet (an ordered pair belongs to one direction, so no direction id is needed).
Output: <ewt>/pairs/<m>.parquet, one row per route, s0, s1, daytype, period, final, inwin: n, obs_s and sch_s (sums), obs_p50,
obs_p90 (seconds), dist (miles, one pair); and <ewt>/pairs/<m>.json (counts at each step).
Usage (on the VM, from ~/muni-511): PYTHONPATH=pylib python3 stop_pair_time.py <extract dir> <ewt dir> <YYYY-MM> --tables <dir>
"""
import sys, os, json, duckdb
args = sys.argv[1:]
opt = lambda k: args[args.index(k) + 1] if k in args else None
d, ewt, month = args[0], args[1], args[2]
tables = opt("--tables") or sys.exit("pass --tables <dir> (dist_table.py output)")
os.makedirs(f"{ewt}/pairs", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=4; SET memory_limit='12GB'; SET preserve_insertion_order=false")
T = lambda c: (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
               f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")
rd = lambda f: f"read_csv('{d}/{f}', header=true, all_varchar=true)"
one = lambda s: con.execute(s).fetchone()
M = month.replace("-", "")
diag = {"month": month}
cols = {x[0] for x in con.execute(f"SELECT * FROM {rd('stop_times.csv.gz')} LIMIT 0").description}
TP = "CASE WHEN timepoint = '1' THEN true WHEN timepoint = '0' THEN false END" if "timepoint" in cols else "NULL::BOOLEAN"
con.execute(f"""CREATE TABLE st0 AS SELECT s.trip_id, t.route_id, CAST(s.stop_sequence AS INT) seq, s.stop_id stop,
  {T("coalesce(nullif(s.departure_time,''), s.arrival_time)")} t, {TP} tp
  FROM {rd('stop_times.csv.gz')} s JOIN {rd('trips.csv.gz')} t USING (trip_id)""")
diag["own_timepoints"] = one("SELECT count(tp) > 0.5 * count(*) FROM st0")[0]
if not diag["own_timepoints"]:
    con.execute(f"UPDATE st0 SET tp = coalesce(x.tp, false) FROM read_parquet('{tables}/timepoints.parquet') x WHERE x.route_id = st0.route_id AND x.stop = st0.stop")
    con.execute("UPDATE st0 SET tp = false WHERE tp IS NULL")
con.execute("""CREATE TABLE st AS SELECT trip_id, stop, t, tp, row_number() OVER (PARTITION BY trip_id ORDER BY seq) r,
  count(*) OVER (PARTITION BY trip_id) nr FROM st0""")
con.execute("""CREATE TABLE win AS SELECT trip_id, min(r) FILTER (WHERE tp AND r > 1 AND r < nr) ra,
  max(r) FILTER (WHERE tp AND r > 1 AND r < nr) rb FROM st GROUP BY 1""")
# each trip's first stop and its sequence number (a later visit to the same stop on a loop trip numbers higher and stays)
con.execute("CREATE TABLE fst AS SELECT trip_id, arg_min(stop, CAST(seq AS INT)) stop, min(CAST(seq AS INT)) mn FROM st0 GROUP BY 1")
con.execute("DROP TABLE st0")
STANDIN = os.path.exists(f"{d}/SCHEDULE_SOURCE")
KEY = "'SFG:' || split_part(split_part(o.trip_id, ':', 2), '_', 1)" if STANDIN else "o.trip_id"

H = f"read_parquet('{ewt}/hourly/{month}.parquet')"
con.execute(f"CREATE TABLE dt AS SELECT DISTINCT sdate, daytype FROM {H}")
con.execute(f"CREATE TABLE xld AS SELECT DISTINCT 'SF:' || route route_id, sdate FROM {H} WHERE excl = 'line_day_outage'")
con.execute(f"""CREATE TABLE xh AS SELECT DISTINCT sdate, hr FROM {H} WHERE excl = 'feed_outage'
  UNION SELECT sdate, hr FROM {H} GROUP BY 1,2 HAVING sum(ob) < 0.5 * sum(eb)""")

# observations, cleaned as in ewt_month.py / trip_time.py
con.execute(f"""CREATE TABLE o0 AS SELECT o.trip_id, {KEY} skey, o.route_id, o.service_date sdate, CAST(o.stop_sequence AS INT) seq, o.to_stop_id stop,
  {T("coalesce(nullif(o.observed_departure_time,''), o.observed_arrival_time)")} a,
  {T("coalesce(nullif(o.scheduled_departure_time,''), o.scheduled_arrival_time)")} s
  FROM {rd('stop_observations.csv.gz')} o WHERE o.service_date LIKE '{M}%'""")
diag["obs_raw"] = one("SELECT count(*) FROM o0")[0]
con.execute("UPDATE o0 SET a = a + 86400 WHERE s IS NOT NULL AND a < s - 43200")
# the first stop goes by the feed's sequence 1 and by the timetable's first stop: 511 numbers a short trip's stops
# along the full pattern (a J from Embarcadero starts at 2) and gives that stop's observation 1 in some months and the
# timetable's number in others, so a pair out of the terminal would come and go by month (as trip_time.py)
con.execute("""CREATE TABLE o2 AS SELECT * FROM o0 WHERE seq > 1 AND a IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM fst WHERE fst.trip_id = o0.skey AND fst.stop = o0.stop AND o0.seq <= fst.mn)
  QUALIFY row_number() OVER (PARTITION BY trip_id, sdate, stop ORDER BY abs(a - coalesce(s, a)), a) = 1""")
con.execute("DROP TABLE o0")
con.execute("""CREATE TABLE o3 AS SELECT *, (pm IS NOT NULL AND a < pm - 60) ff, (nm IS NOT NULL AND a > nm + 60) bf FROM
  (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm,
             min(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) nm FROM o2)""")
con.execute("""CREATE TABLE o4 AS SELECT o3.* EXCLUDE (pm, nm, ff, bf) FROM o3 JOIN (SELECT trip_id, sdate, count(*) FILTER (WHERE bf) < count(*) FILTER (WHERE ff) useb
  FROM o3 GROUP BY 1, 2) k USING (trip_id, sdate) WHERE NOT (CASE WHEN k.useb THEN bf ELSE ff END)""")
con.execute("""CREATE TABLE obs AS SELECT * EXCLUDE (pm) FROM (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq
  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm FROM o4) WHERE pm IS NULL OR a >= pm - 60""")
con.execute("DROP TABLE o2; DROP TABLE o3; DROP TABLE o4")
diag["obs_clean"] = one("SELECT count(*) FROM obs")[0]

# each observation's rank in its trip's timetable
con.execute("""CREATE TABLE obr AS SELECT o.trip_id, o.sdate, o.seq, arg_min(st.r, abs(st.t - coalesce(o.s, st.t))) r, any_value(st.nr) nr
  FROM obs o JOIN st ON st.trip_id = o.skey AND st.stop = o.stop GROUP BY 1, 2, 3""")
diag["obs_no_schedule_match"] = diag["obs_clean"] - one("SELECT count(*) FROM obr")[0]
con.execute("""CREATE TABLE ob AS SELECT o.*, b.r, b.nr FROM obs o JOIN obr b USING (trip_id, sdate, seq)""")
con.execute("""CREATE TABLE pr AS SELECT p.trip_id, p.route_id, p.sdate, p.stop s0, n.stop s1, p.s t0, n.a - p.a obs_s, n.s - p.s sch_s,
    n.r = n.nr final, coalesce(p.r >= w.ra AND n.r <= w.rb, false) inwin
  FROM ob p JOIN ob n ON n.trip_id = p.trip_id AND n.sdate = p.sdate AND n.r = p.r + 1
  LEFT JOIN win w ON w.trip_id = p.skey
  QUALIFY row_number() OVER (PARTITION BY p.trip_id, p.sdate, p.stop ORDER BY n.a, n.stop) = 1""")
diag["pairs_seq_not_consecutive"] = one("""SELECT count(*) FROM ob p JOIN ob n ON n.trip_id = p.trip_id AND n.sdate = p.sdate
  AND n.r = p.r + 1 WHERE n.seq <> p.seq + 1""")[0]
# a handful of trip-days a month (0 to 12) have two observations at the same timetable rank (a stop id the
# timetable lists twice); the pair keeps the earlier one. Counted here, and the key checked unique after.
diag["pairs_second_match_dropped"] = one("""SELECT count(*) FROM ob p JOIN ob n ON n.trip_id = p.trip_id AND n.sdate = p.sdate
  AND n.r = p.r + 1""")[0] - one("SELECT count(*) FROM pr")[0]
k = one("SELECT count(*) - count(DISTINCT (trip_id, sdate, s0)) FROM pr")[0]
if k: sys.exit(f"pairing duplicated {k} trip-day-stop rows")
diag["pairs_both_observed"] = one("SELECT count(*) FROM pr")[0]
con.execute(f"""CREATE TABLE dist AS SELECT s0, s1, median(dist) dist FROM read_parquet('{tables}/stop_pairs.parquet') GROUP BY 1, 2""")
PER = """CASE WHEN h BETWEEN 7 AND 8 THEN 'am' WHEN h BETWEEN 9 AND 15 THEN 'mid' WHEN h BETWEEN 16 AND 18 THEN 'pm'
  WHEN h BETWEEN 19 AND 22 THEN 'eve' WHEN h BETWEEN 5 AND 6 THEN 'early' END"""
con.execute(f"""CREATE TABLE ok AS SELECT z.*, x.dist, dt.daytype, (z.t0 // 3600) % 24 h FROM pr z JOIN dt USING (sdate)
  LEFT JOIN dist x USING (s0, s1)
  WHERE z.t0 IS NOT NULL AND z.obs_s > 0 AND z.sch_s > 0 AND z.obs_s <= 3 * z.sch_s + 600
    AND (x.dist IS NULL OR x.dist / z.obs_s * 3600 <= 60)
    AND NOT EXISTS (SELECT 1 FROM xh WHERE xh.sdate = z.sdate AND xh.hr = z.t0 // 3600)
    AND NOT EXISTS (SELECT 1 FROM xld WHERE xld.route_id = z.route_id AND xld.sdate = z.sdate)""")
diag["pairs_kept"] = one("SELECT count(*) FROM ok")[0]
diag["pairs_kept_no_distance"] = one("SELECT count(*) FROM ok WHERE dist IS NULL")[0]
con.execute(f"""COPY (SELECT CASE replace(route_id,'SF:','') WHEN 'LBUS' THEN 'L' WHEN 'C' THEN 'CA' ELSE replace(route_id,'SF:','') END route,
    s0, s1, daytype, {PER} period, final, inwin, count(*) n, sum(obs_s) obs_s, sum(sch_s) sch_s,
    median(obs_s) obs_p50, quantile_cont(obs_s, 0.9) obs_p90, any_value(dist) dist
  FROM ok WHERE {PER} IS NOT NULL GROUP BY ALL ORDER BY ALL)
  TO '{ewt}/pairs/{month}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
diag["rows_out"] = one(f"SELECT count(*) FROM '{ewt}/pairs/{month}.parquet'")[0]
json.dump(diag, open(f"{ewt}/pairs/{month}.json", "w"), indent=1, default=str)
print(json.dumps(diag, default=str))
