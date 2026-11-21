"""Hourly excess wait (TfL QSI method) for every Muni line, one month of 511 historic stop observations.

Input: a directory written by extract_sf.py (stop_observations, trips, stop_times, calendar_dates; Muni rows only).
Output, into <outdir>:
  hourly/<YYYY-MM>.parquet  one row per route, direction, stop, service date and clock hour (an "hour block"), with
      eb, ob          scheduled and observed departures in the hour (TfL "Expected Buses" and "Observed Buses")
      ssh2, ssh       sum of squared scheduled headways and sum of scheduled headways, seconds (TfL 3.4)
      soh2, soh       the same for observed headways (TfL 3.10)
      hswt, hawt      ssh2 / (2 ssh) and soh2 / (2 soh), minutes; null where the hour holds only a first bus
      tb, tsh2, tsh   the tracked buses' own SCHEDULED times (each observation row carries one): count, sums
      htswt           tsh2 / (2 tsh), minutes. It splits excess wait in two: htswt - hswt rises only when a
                      timetabled bus is absent from the feed (missed or untracked), hawt - htswt only when the
                      tracked buses run unevenly spaced
      excl            null if the block counts; else why it doesn't ('feed_outage' or 'line_day_outage')
      linecov         observed over scheduled trips for that route and date (a tracking-coverage check)
      daytype         weekday, saturday or sunday (a weekday or Saturday whose scheduled Muni trips are under
                      90% of that day type's median in the month is a holiday and counted as sunday: 511's
                      timetable carries holiday service at 83% of a weekday's trips, while ordinary weekdays sit
                      at 97% or more of the median, checked on every month of 2025-05 to 2026-02)
  diag/<YYYY-MM>.json       counts at each cleaning step, outage bins, dropped line-days, route list, stops
  diag/<YYYY-MM>-route.csv  per route: scheduled and observed trip-hours (for the service-delivered intake check; the _x
                            columns leave out whole-day feed outages, dates with 57 or more of 114 bins out) and
                            SFMTA headway-adherence numerator and denominator (observed gap <= scheduled gap + 5 min)

Method, TfL "QSI Statistics Explained" v2.0 sections 3.1-3.15: at each stop (TfL's QSI point), route and direction,
a headway is the gap between a bus's departure and the preceding bus's departure, scheduled or observed. Each headway
belongs to the clock hour in which the bus that ends it departs. A day's first bus has no headway. hSWT and hAWT are
computed per hour block; aggregation across stops and hours happens in ewt_aggregate.py.
Service breaks: a scheduled gap of more than 60 minutes (BREAK) at a stop, route and direction is a break in service,
not a headway, and the bus after it starts a new service period exactly as a day's first bus does, with no headway
on either side. Without this the first local bus of the evening on a line whose local skips a segment all day (the
5 and 9 while the 5R and 9R run) carries a 10 to 13 hour "headway", and that one block outweighs the whole hour's
scheduled wait (line 5 at 7 pm: 376-minute hSWT). No Muni line is timetabled less often than hourly between 05:00
and 23:00 except across such breaks, so 60 minutes separates the two cases; diag 'sched_breaks' counts them by route.
The observed side follows the schedule's periods: each observed bus belongs to the period of the latest scheduled
departure at or before its own scheduled time (its observed time where it has none), and observed headways are taken
within a period. So a long observed gap inside a period, from missed or untracked buses, still counts in full.
Departures: observed_departure_time where present, else observed_arrival_time; scheduled departure_time, else arrival.

Cleaning of the observations, in order (all from notes/muni-reliability-2026-11/2026-11-08-511-data-access.md):
  1. Drop each trip's first stop, on both sides: the terminal time is often far off. The first stop is the timetable's
     lowest stop_sequence for the trip as well as the feed's sequence 1, because 511 numbers a short trip's stops along
     the full pattern (a J from Embarcadero starts at 2, a short-turn 8 at 7) and gives that first stop's observation 1
     in some months (2023-01 to 2024-05, 2026-09 on) and the timetable's number in others (as trip_time.py). A later
     visit to the same stop on a loop trip carries a higher number and stays. The schedule side drops the same stop.
  2. Deduplicate (trip, service_date, stop): keep the observation nearest its own scheduled time (the earliest on a
     tie). About 1% of rows repeat a trip-day-stop, mostly as a second complete run of the same trip id 50 minutes
     later (Fable review 2026-11-09, G1 and Q5); the run nearer the timetable is taken to be the trip.
  3. Out of order: within a trip-day ordered by stop_sequence, flag rows more than 60 s earlier than the latest time at
     any earlier stop, and separately rows more than 60 s later than the earliest time at any later stop; drop the
     smaller set (the first on a tie), then any row still out of order. diag 'out_of_order_share' is the share of
     deduplicated rows this drops; ewt_aggregate.py writes it to <extract>_months.csv and flags a month above 2%.
  4. Whole line-day outages: a route-date with observed trips under 50% of scheduled trips: every block excluded.
  5. Partial outages: count all Muni observations per date and 10-minute bin (05:00-24:00); a bin under half the
     median count for that bin across the month's dates of the same day type is a feed outage. Every hour block
     whose hour, or the 30 minutes before it, holds an outage bin is excluded on both sides (TfL excludes whole
     hour blocks, never partial hours: QSI Statistics Explained 2.3).
Timetable check (diag 'sched_time_match', every month): share of observation rows whose own trip and stop are in
the schedule used, and of those the share whose 511 scheduled time equals it exactly and within 60 s. On a stand-in
month a matched row takes the stand-in's time (see the code); diag 'sched_time_match_by_date' shows where the two differ.
Trips are keyed on trip_id plus service_date (trip_id carries the feed date). Direction comes from trips.txt, else from
the observation row's direction_id (needed where make_sched.py has replaced a missing schedule).
Usage: PYTHONPATH=pylib python3 ewt_month.py <extract dir> <outdir> <YYYY-MM>
"""
import sys, os, json, duckdb
BREAK = 3600  # seconds: a longer scheduled gap is a break in service (see docstring)

d, outdir, month = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(f"{outdir}/hourly", exist_ok=True); os.makedirs(f"{outdir}/diag", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=5; SET memory_limit='16GB'; SET preserve_insertion_order=false")
# Times come as HH:MM:SS through 2022 and as whole seconds after midnight (e.g. 60060 = 16:41:00) from 2023-01 in
# stop_observations; both forms are read.
T = lambda c: (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
               f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")
rd = lambda f: f"read_csv('{d}/{f}', header=true, all_varchar=true)"
one = lambda s: con.execute(s).fetchone()
diag = {"month": month, "schedule_source": open(f"{d}/SCHEDULE_SOURCE").read().strip() if os.path.exists(f"{d}/SCHEDULE_SOURCE") else "511 historic GTFS"}

con.execute(f"CREATE TABLE trips AS SELECT trip_id, route_id, service_id, direction_id dir FROM {rd('trips.csv.gz')}")
con.execute(f"""CREATE TABLE cd AS SELECT service_id, date sdate FROM {rd('calendar_dates.csv.gz')} GROUP BY 1,2
  HAVING bool_or(exception_type='1') AND NOT bool_or(exception_type='2')""")
con.execute(f"""CREATE TABLE st AS SELECT trip_id, CAST(stop_sequence AS INT) seq, stop_id stop,
  {T("coalesce(nullif(departure_time,''), arrival_time)")} t FROM {rd('stop_times.csv.gz')}""")
# scheduled trip-days, keyed like the observations
con.execute("""CREATE TABLE schtrip AS SELECT t.trip_id, t.route_id, t.dir, cd.sdate FROM trips t JOIN cd USING (service_id)
  WHERE cd.sdate LIKE ? || '%'""", [month.replace("-", "")])
# day type: weekday / saturday / sunday, holidays by scheduled volume
con.execute("""CREATE TABLE dt AS WITH c AS (SELECT sdate, count(*) n, dayofweek(strptime(sdate,'%Y%m%d')) w FROM schtrip GROUP BY 1),
  k AS (SELECT *, CASE WHEN w=0 THEN 'sunday' WHEN w=6 THEN 'saturday' ELSE 'weekday' END k0 FROM c),
  m AS (SELECT k0, median(n) mn FROM k GROUP BY 1)
  SELECT sdate, CASE WHEN k0<>'sunday' AND n < 0.9*mn THEN 'sunday' ELSE k0 END daytype FROM k JOIN m USING (k0)""")
diag["holidays"] = [r[0] for r in con.execute("""SELECT sdate FROM dt JOIN (SELECT sdate, dayofweek(strptime(sdate,'%Y%m%d')) w FROM dt) USING (sdate)
  WHERE daytype='sunday' AND w<>0 ORDER BY 1""").fetchall()]
# each trip's first stop by the timetable (rule 1): its stop and its lowest stop_sequence
con.execute("CREATE TABLE fst AS SELECT trip_id, arg_min(stop, seq) stop, min(seq) mn FROM st GROUP BY 1")
con.execute("""CREATE TABLE sch AS SELECT s.route_id, s.dir, st.stop, s.sdate, s.trip_id, st.t FROM schtrip s JOIN st USING (trip_id)
  JOIN fst USING (trip_id) WHERE st.seq > fst.mn AND st.t IS NOT NULL""")
diag["sched_rows"] = one("SELECT count(*) FROM sch")[0]

# --- observations, cleaned ---
# On a stand-in month (make_sched.py) the schedule trip is 'SFG:' + the Muni trip id inside 511's
# ('SF:11121705_M21:20221220' -> 'SFG:11121705'); on a 511-schedule month the trip ids are the same in both.
STANDIN = os.path.exists(f"{d}/SCHEDULE_SOURCE")
KEY = "'SFG:' || split_part(split_part(o.trip_id, ':', 2), '_', 1)" if STANDIN else "o.trip_id"
con.execute(f"""CREATE TABLE o0 AS SELECT o.trip_id, {KEY} skey, o.service_date sdate, CAST(o.stop_sequence AS INT) seq, o.to_stop_id stop,
  o.route_id, coalesce(t.dir, nullif(o.direction_id,'')) dir, {T("coalesce(nullif(o.observed_departure_time,''), o.observed_arrival_time)")} a,
  {T('o.observed_arrival_time')} aa, {T("coalesce(nullif(o.scheduled_departure_time,''), o.scheduled_arrival_time)")} s
  FROM {rd('stop_observations.csv.gz')} o LEFT JOIN trips t USING (trip_id) WHERE o.service_date LIKE ? || '%'""", [month.replace("-", "")])
diag["obs_rows"] = one("SELECT count(*) FROM o0")[0]
diag["obs_time_seconds_form"] = one(f"SELECT count(*) FROM {rd('stop_observations.csv.gz')} WHERE NOT contains(observed_arrival_time, ':')")[0]
diag["obs_rows_other_month"] = one(f"SELECT count(*) FROM {rd('stop_observations.csv.gz')} WHERE service_date NOT LIKE '{month.replace('-', '')}%'")[0]
diag["obs_no_direction"] = one("SELECT count(*) FROM o0 WHERE dir IS NULL")[0]
diag["obs_departure_differs"] = one("SELECT count(*) FROM o0 WHERE a <> aa")[0]
diag["obs_no_sched_time"] = one("SELECT count(*) FROM o0 WHERE s IS NULL")[0]
diag["raw_direction_blank"] = one(f"SELECT count(*) FROM {rd('stop_observations.csv.gz')} WHERE coalesce(direction_id,'') = ''")[0]
diag["obs_uncertainty_nonzero"] = one(f"SELECT count(*) FROM {rd('stop_observations.csv.gz')} WHERE coalesce(uncertainty,'0') <> '0'")[0]
diag["obs_per_day"] = [list(r) for r in con.execute("SELECT sdate, count(*) FROM o0 GROUP BY 1 ORDER BY 1").fetchall()]
# Standing check on the timetable: for each observation row (first stops out) with a scheduled time, find its own trip
# and stop in the schedule we use (keyed as above), and compare 511's scheduled time with it. The nearest time wins
# where a trip visits a stop twice.
con.execute(f"""CREATE TABLE tm AS SELECT o.trip_id, o.sdate, o.seq, o.stop, o.s, arg_min(st.t, abs(st.t - o.s)) gt
  FROM o0 o LEFT JOIN st ON st.trip_id = o.skey AND st.stop = o.stop WHERE o.seq > 1 AND o.s IS NOT NULL GROUP BY ALL""")
r = one("""SELECT count(*), count(gt), count(*) FILTER (WHERE gt = s), count(*) FILTER (WHERE abs(gt - s) <= 60),
  round(avg(gt - s), 1), round(median(abs(gt - s)), 1) FROM tm""")
diag["sched_time_match"] = {"rows": r[0], "trip_stop_found": round(r[1] / max(r[0], 1), 4),
  "exact": round(r[2] / max(r[1], 1), 4), "within_60s": round(r[3] / max(r[1], 1), 4), "mean_sched_minus_511_s": r[4], "median_abs_s": r[5]}
diag["sched_time_match_by_date"] = [list(x) for x in con.execute("""SELECT sdate, count(*), round(count(*) FILTER (WHERE gt = s) / greatest(count(gt), 1), 4),
  round(avg(gt - s), 1) FROM tm GROUP BY 1 ORDER BY 1""").fetchall()]
# On a stand-in month 511's scheduled times can differ from the stand-in timetable for the same trip (late November to
# mid-December 2022: same trip ids, times about a minute earlier). The tracked buses' scheduled times (htswt, the
# service periods, the dedupe) must come from the same timetable as hSWT, or the missing-bus part compares two
# timetables; so a matched row takes the stand-in time, and an unmatched row keeps 511's.
if STANDIN:
    con.execute("""UPDATE o0 SET s = tm.gt FROM tm WHERE tm.gt IS NOT NULL AND o0.trip_id = tm.trip_id AND o0.sdate = tm.sdate
      AND o0.seq = tm.seq AND o0.stop = tm.stop AND o0.s = tm.s""")
    diag["standin_times_substituted"] = r[1]
con.execute("UPDATE o0 SET a = a + 86400 WHERE s IS NOT NULL AND a < s - 43200")  # past-midnight times written as 00:xx
con.execute("""CREATE TABLE o1 AS SELECT * EXCLUDE (skey) FROM o0 WHERE seq > 1 AND dir IS NOT NULL AND a IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM fst WHERE fst.trip_id = o0.skey AND fst.stop = o0.stop AND o0.seq <= fst.mn)""")
diag["first_stop_by_timetable"] = one("""SELECT count(*) FROM o0 WHERE seq > 1 AND dir IS NOT NULL AND a IS NOT NULL
    AND EXISTS (SELECT 1 FROM fst WHERE fst.trip_id = o0.skey AND fst.stop = o0.stop AND o0.seq <= fst.mn)""")[0]
diag["after_first_stop_and_nulls"] = one("SELECT count(*) FROM o1")[0]
con.execute("CREATE TABLE o2 AS SELECT * FROM o1 QUALIFY row_number() OVER (PARTITION BY trip_id, sdate, stop ORDER BY abs(a - coalesce(s, a)), a) = 1")
diag["after_dedupe"] = one("SELECT count(*) FROM o2")[0]
# rule 3, both directions: a forward pass flags rows more than 60 s earlier than the latest earlier time, a backward pass
# flags rows more than 60 s later than the earliest later time, and each trip-day drops the smaller set (forward on a
# tie). From December 2022 to June 2023 511 gives the first stops after the terminal times 12-17 minutes late; a
# forward-only rule kept those and dropped the correct rest of the trip (Fable review 3, item 3). A forward pass over
# what is left then guarantees order.
con.execute("""CREATE TABLE o3 AS SELECT *, (pm IS NOT NULL AND a < pm - 60) ff, (nm IS NOT NULL AND a > nm + 60) bf FROM
  (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm,
             min(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) nm FROM o2)""")
con.execute("""CREATE TABLE o4 AS SELECT o3.* EXCLUDE (pm, nm, ff, bf) FROM o3 JOIN (SELECT trip_id, sdate, count(*) FILTER (WHERE bf) < count(*) FILTER (WHERE ff) useb
  FROM o3 GROUP BY 1, 2) k USING (trip_id, sdate) WHERE NOT (CASE WHEN k.useb THEN bf ELSE ff END)""")
diag["out_of_order_backward_trip_days"] = one("SELECT count(*) FROM (SELECT trip_id, sdate FROM o3 GROUP BY 1, 2 HAVING count(*) FILTER (WHERE bf) < count(*) FILTER (WHERE ff))")[0]
con.execute("""CREATE TABLE obs AS SELECT * EXCLUDE (pm) FROM (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq
  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm FROM o4) WHERE pm IS NULL OR a >= pm - 60""")
con.execute("DROP TABLE o3; DROP TABLE o4")
diag["after_out_of_order"] = one("SELECT count(*) FROM obs")[0]
diag["out_of_order_share"] = round(1 - diag["after_out_of_order"] / max(diag["after_dedupe"], 1), 4)
con.execute("DROP TABLE o1; DROP TABLE o2")

# rule 4: line-day coverage
con.execute("""CREATE TABLE cov AS SELECT s.route_id, s.sdate, s.n nsch, coalesce(o.n,0) nobs FROM
  (SELECT route_id, sdate, count(*) n FROM schtrip GROUP BY 1,2) s LEFT JOIN
  (SELECT route_id, sdate, count(DISTINCT trip_id) n FROM obs GROUP BY 1,2) o USING (route_id, sdate)""")
diag["line_days"] = one("SELECT count(*) FROM cov")[0]
diag["line_days_dropped"] = [list(r) for r in con.execute(
    "SELECT route_id, sdate, nsch, nobs FROM cov WHERE nobs < 0.5*nsch ORDER BY 2,1").fetchall()]
# rule 5: feed outage bins, all Muni rows as read (before cleaning), 05:00-24:00
con.execute(f"""CREATE TABLE binc AS SELECT sdate, a//600 b, count(*) n FROM o0 WHERE a IS NOT NULL GROUP BY 1,2""")
con.execute("""CREATE TABLE outage AS WITH g AS (SELECT DISTINCT d.sdate, d.daytype, b FROM dt d, range(30,144) r(b)),
  x AS (SELECT g.*, coalesce(c.n,0) n FROM g LEFT JOIN binc c USING (sdate, b)),
  m AS (SELECT daytype, b, median(n) mn FROM x GROUP BY 1,2)
  SELECT sdate, b FROM x JOIN m USING (daytype, b) WHERE n < 0.5*mn""")
diag["outage_bins"] = [[r[0], f"{r[1]//6:02d}:{r[1]%6*10:02d}", f"{(r[2]+1)//6:02d}:{(r[2]+1)%6*10:02d}", r[3]] for r in con.execute(
    "SELECT sdate, min(b), max(b), count(*) FROM outage GROUP BY 1 ORDER BY 1").fetchall()]
# hour h is excluded if any outage bin lies in [h*3600-1800, (h+1)*3600)
con.execute("CREATE TABLE outh AS SELECT DISTINCT sdate, hr FROM outage, range(0,36) r(hr) WHERE b*600 >= hr*3600-1800 AND b*600 < (hr+1)*3600")

# --- hour blocks ---
# service periods (see docstring): a scheduled gap over BREAK starts a new period; observed buses take the period of the
# latest scheduled departure at or before their own scheduled time
con.execute(f"""CREATE TABLE schp AS SELECT route_id, dir, stop, sdate, trip_id, t,
    sum(CASE WHEN pt IS NULL OR t - pt > {BREAK} THEN 1 ELSE 0 END) OVER (PARTITION BY route_id, dir, stop, sdate ORDER BY t, trip_id
      ROWS UNBOUNDED PRECEDING) per, t - pt gap
  FROM (SELECT *, lag(t) OVER (PARTITION BY route_id, dir, stop, sdate ORDER BY t, trip_id) pt FROM sch)""")
diag["sched_breaks"] = [list(r) for r in con.execute(f"""SELECT replace(route_id,'SF:','') r, count(*) n,
    round(median(gap)/3600, 1) median_hours FROM schp WHERE gap > {BREAK} AND t//3600 BETWEEN 5 AND 22 GROUP BY 1 ORDER BY 2 DESC""").fetchall()]
con.execute("""CREATE TABLE obsp AS SELECT o.route_id, o.dir, o.stop, o.sdate, o.a, o.s, coalesce(p.per, 1) per
  FROM obs o ASOF LEFT JOIN (SELECT route_id, dir, stop, sdate, t, max(per) per FROM schp GROUP BY ALL) p
  ON o.route_id = p.route_id AND o.dir = p.dir AND o.stop = p.stop AND o.sdate = p.sdate AND coalesce(o.s, o.a) >= p.t""")
diag["obs_service_period_gt1"] = one("SELECT count(*) FROM obsp WHERE per > 1")[0]
def blocks(tbl, p):
    return f"""SELECT route_id, dir, stop, sdate, t//3600 hr, count(*) {p}b,
      sum(h*h) FILTER (WHERE h IS NOT NULL) {p}h2, sum(h) FILTER (WHERE h IS NOT NULL) {p}h
      FROM (SELECT route_id, dir, stop, sdate, t, CAST(t - lag(t) OVER (PARTITION BY route_id, dir, stop, sdate, per ORDER BY t) AS DOUBLE) h FROM {tbl})
      GROUP BY 1,2,3,4,5"""
con.execute(f"CREATE TABLE bs AS {blocks('schp', 's')}")
con.execute(f"CREATE TABLE bo AS {blocks('(SELECT route_id, dir, stop, sdate, per, a t FROM obsp)', 'o')}")
con.execute(f"CREATE TABLE bt AS {blocks('(SELECT route_id, dir, stop, sdate, per, s t FROM obsp WHERE s IS NOT NULL)', 't')}")
con.execute(f"""COPY (SELECT replace(route_id,'SF:','') route, dir, stop, sdate, hr, dt.daytype,
    coalesce(sb,0) eb, coalesce(ob,0) ob, coalesce(tb,0) tb, sh2 ssh2, sh ssh, oh2 soh2, oh soh, th2 tsh2, th tsh,
    CASE WHEN sh > 0 THEN sh2/(2*sh)/60 END hswt, CASE WHEN oh > 0 THEN oh2/(2*oh)/60 END hawt,
    CASE WHEN th > 0 THEN th2/(2*th)/60 END htswt,
    CASE WHEN c.nobs < 0.5*c.nsch OR c.nsch IS NULL THEN 'line_day_outage' WHEN x.hr IS NOT NULL THEN 'feed_outage' END excl,
    round(c.nobs/c.nsch, 3) linecov
  FROM bs FULL JOIN bo USING (route_id, dir, stop, sdate, hr) FULL JOIN bt USING (route_id, dir, stop, sdate, hr) JOIN dt USING (sdate)
  LEFT JOIN cov c USING (route_id, sdate) LEFT JOIN outh x USING (sdate, hr)
  ORDER BY route, dir, stop, sdate, hr) TO '{outdir}/hourly/{month}.parquet' (FORMAT parquet, COMPRESSION zstd)""")
diag["blocks"] = one(f"SELECT count(*), count(*) FILTER (WHERE excl IS NULL) FROM '{outdir}/hourly/{month}.parquet'")
diag["routes"] = [r[0] for r in con.execute("SELECT DISTINCT replace(route_id,'SF:','') FROM cov ORDER BY 1").fetchall()]
diag["stops_sched"] = one("SELECT count(DISTINCT stop) FROM sch")[0]
diag["stops_obs"] = one("SELECT count(DISTINCT stop) FROM obs")[0]
diag["stops_obs_not_in_sched"] = one("SELECT count(DISTINCT stop) FROM obs WHERE stop NOT IN (SELECT stop FROM sch)")[0]

# --- per-route checks for the intake step ---
# service delivered: scheduled trip-hours (first to last scheduled time of each trip-day) and those of observed trip-days
con.execute("""CREATE TABLE tdur AS SELECT trip_id, (max(t) - min(t))/3600.0 hrs, count(*) nst FROM st GROUP BY 1""")
con.execute("""CREATE TABLE seen AS SELECT trip_id, sdate, count(*) n FROM obs GROUP BY 1,2""")
# headway adherence: each observed departure, its observed gap and its trip's scheduled gap at the same stop
con.execute("""CREATE TABLE sgap AS SELECT trip_id, sdate, stop, t - lag(t) OVER (PARTITION BY route_id, dir, stop, sdate ORDER BY t) sg FROM sch""")
con.execute("""CREATE TABLE ogap AS SELECT trip_id, sdate, stop, route_id, a,
  a - lag(a) OVER (PARTITION BY route_id, dir, stop, sdate ORDER BY a) og FROM obs""")
con.execute(f"""COPY (WITH sd AS (SELECT s.route_id, s.sdate, sum(d.hrs) sched_hrs,
      sum(d.hrs) FILTER (WHERE x.n IS NOT NULL) obs_hrs, sum(d.hrs) FILTER (WHERE x.n >= 0.5*(d.nst-1)) obs_hrs_half,
      bool_or(s.sdate IN (SELECT sdate FROM outage GROUP BY 1 HAVING count(*) >= 57)) outage_day
    FROM schtrip s JOIN tdur d USING (trip_id) LEFT JOIN seen x USING (trip_id, sdate) GROUP BY 1,2),
  ha AS (SELECT o.route_id, o.sdate, count(*) ha_n, count(*) FILTER (WHERE o.og <= g.sg + 300) ha_ok,
      count(*) FILTER (WHERE o.a//3600 BETWEEN 5 AND 23) ha_n_day, count(*) FILTER (WHERE o.og <= g.sg + 300 AND o.a//3600 BETWEEN 5 AND 23) ha_ok_day
    FROM ogap o JOIN sgap g USING (trip_id, sdate, stop) WHERE o.og IS NOT NULL AND g.sg IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM outh x WHERE x.sdate=o.sdate AND x.hr=o.a//3600) GROUP BY 1,2),
  tc AS (SELECT route_id, sdate, count(*) sched_trips FROM schtrip GROUP BY 1,2),
  oc AS (SELECT route_id, sdate, count(DISTINCT trip_id) obs_trips FROM obs GROUP BY 1,2),
  od AS (SELECT DISTINCT sdate FROM outage GROUP BY 1 HAVING count(*) >= 57)
  SELECT replace(route_id,'SF:','') route, sum(sched_hrs) sched_hrs,
    sum(tc.sched_trips) sched_trips, sum(oc.obs_trips) obs_trips,
    sum(tc.sched_trips) FILTER (WHERE sdate NOT IN (SELECT sdate FROM od)) sched_trips_x,
    sum(oc.obs_trips) FILTER (WHERE sdate NOT IN (SELECT sdate FROM od)) obs_trips_x, sum(obs_hrs) obs_hrs, sum(obs_hrs_half) obs_hrs_half,
    sum(sched_hrs) FILTER (WHERE NOT outage_day) sched_hrs_x, sum(obs_hrs) FILTER (WHERE NOT outage_day) obs_hrs_x,
    count(DISTINCT sdate) FILTER (WHERE outage_day) outage_days,
    sum(ha_n) ha_n, sum(ha_ok) ha_ok, sum(ha_n_day) ha_n_day, sum(ha_ok_day) ha_ok_day, count(*) dates
  FROM sd LEFT JOIN ha USING (route_id, sdate) LEFT JOIN tc USING (route_id, sdate) LEFT JOIN oc USING (route_id, sdate)
  GROUP BY 1 ORDER BY 1) TO '{outdir}/diag/{month}-route.csv' (HEADER)""")
json.dump(diag, open(f"{outdir}/diag/{month}.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in diag.items() if k not in ("routes", "line_days_dropped")}, default=str))
print("line-days dropped:", len(diag["line_days_dropped"]))
