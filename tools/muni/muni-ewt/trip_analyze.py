"""Summaries of Muni bus speed and running time against the timetable, from trip_time.py and trip_time_2019.py.

Buses only: a route counts when its GTFS route_type is 3 (<ewt>/ref/route_types.csv from dist_table.py), so Muni
Metro, the F and the cable cars are out, and the L's bus substitute (LBUS) stays a line of its own. Same scope as the
excess-wait summaries otherwise: segments and trips whose scheduled start is 05:00 to 22:59, every day type, months
whose feed kept 60% or more of scheduled departures (<extract>_months.csv). C/L-OWL/N-OWL renamed.
Speed: a line's speed is its measured miles over its observed hours, summed over every kept segment, and its
timetable speed is the same miles over their scheduled hours. Citywide speed is miles over hours: the line speeds
combined harmonically with each line's scheduled bus-miles (trip_time.py's busmiles files, trips starting 05:00 to
22:59) as weights, which is the same as weighting by scheduled bus-hours. Lines scheduled but never measured drop
out; speed_system_*.csv carry the measured lines' share of scheduled bus-miles.
Running time against the timetable (main figure): over every kept segment, observed minus scheduled seconds as a
share of scheduled seconds; a line's share is pooled over its segments, citywide weights lines by scheduled bus-hours.
It uses every observed trip and needs no trip ends. min_per_hr is the same as minutes over the timetable per hour
of scheduled running.
Per trip (the distribution): trips whose first and last interior timepoints and 75% of interior timepoints were
observed (trip_time.py), observed minus scheduled running time over about 70% of the trip; mean per line, citywide
weighted by scheduled trips, and the share within 5 minutes either side of the timetable.
Periods (system_period.csv): the first 12 and latest 12 usable months, March to October of 2025 and of 2026 (the same
months), and September 2019 against the latest 12 on the bus lines measured in both with the 2019 weights held
fixed (2019's distances come from a different method and are good to about 3%; trip_time_2019.py).
Outputs into <outdir>: speed_line_year.csv, speed_system_year.csv, speed_system_month.csv, run_line_year.csv,
run_system_year.csv, run_system_month.csv, system_period.csv, trip_rank.csv (each bus line: 2019, first 12, latest 12).
Usage: python3 trip_analyze.py <ewt dir> <extract_months.csv> <outdir>
"""
import sys, os, duckdb
ewt, mcsv, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
con = duckdb.connect()
REN = "CASE route WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE route END"
con.execute(f"CREATE TABLE bus AS SELECT DISTINCT {REN} route FROM read_csv('{ewt}/ref/route_types.csv', header=true, all_varchar=true) WHERE route_type = '3'")
con.execute(f"CREATE TABLE mk AS SELECT month FROM read_csv('{mcsv}', header=true) WHERE kept_share >= 0.6 AND month <> '2019-09'")
ms = [r[0] for r in con.execute("SELECT month FROM mk ORDER BY 1").fetchall()]
f12, l12 = ms[:12], ms[-12:]
inl = lambda xs: ",".join(repr(m) for m in xs)
con.execute(f"""CREATE TABLE seg AS SELECT * FROM (SELECT {REN} route, substr(sdate,1,4)||'-'||substr(sdate,5,2) AS month, CAST(left(sdate,4) AS INT) yr,
    daytype, hr, nseg, dist, obs_s, sch_s FROM read_parquet('{ewt}/seg/20*.parquet') WHERE hr BETWEEN 5 AND 22)
  WHERE route IN (SELECT route FROM bus) AND (month = '2019-09' OR month IN (SELECT month FROM mk))""")
con.execute(f"""CREATE TABLE trip AS SELECT * FROM (SELECT {REN} route, substr(sdate,1,4)||'-'||substr(sdate,5,2) AS month, CAST(left(sdate,4) AS INT) yr,
    daytype, hr, dist, obs_s, sch_s FROM read_parquet('{ewt}/trip/*.parquet') WHERE hr BETWEEN 5 AND 22)
  WHERE route IN (SELECT route FROM bus) AND month IN (SELECT month FROM mk)""")
con.execute(f"""CREATE TABLE bm AS SELECT * FROM (SELECT {REN} route, regexp_extract(filename, '(\\d{{4}}-\\d{{2}})-busmiles', 1) AS month, sum(sched_miles) miles,
    sum(sched_trips) trips FROM read_csv('{ewt}/seg/*-busmiles.csv', header=true, filename=true) GROUP BY ALL)
  WHERE route IN (SELECT route FROM bus) AND month IN (SELECT month FROM mk)""")
con.execute(f"""CREATE TABLE s19 AS SELECT route, sum(dist) miles, sum(dist) / sum(sch_s) * 3600 mph_sch FROM read_parquet('{ewt}/sched-2019-09.parquet')
  WHERE hr BETWEEN 5 AND 22 AND route IN (SELECT route FROM bus) GROUP BY 1""")

# a line's figures over any grouping of months; g is the grouping column
def lines(g, where="true"):
    return f"""SELECT s.route, {g} g, sum(s.dist) / sum(s.obs_s) * 3600 mph, sum(s.dist) / sum(s.sch_s) * 3600 mph_sch,
        sum(s.obs_s - s.sch_s) / sum(s.sch_s) run_share, sum(s.dist) miles_measured, count(DISTINCT s.month) AS months
      FROM seg s WHERE s.month <> '2019-09' AND {where} GROUP BY ALL"""
def weights(g, where="true"):
    return f"SELECT route, {g} g, sum(miles) miles, sum(trips) trips FROM bm WHERE {where} GROUP BY ALL"
# citywide: harmonic in speed with scheduled miles (= weighting by scheduled hours); running share by scheduled hours
CITY = """round(sum(w.miles) / sum(w.miles / l.mph), 2) mph, round(sum(w.miles) / sum(w.miles / l.mph_sch), 2) mph_sch,
    round(sum(l.run_share * w.miles / l.mph_sch) / sum(w.miles / l.mph_sch), 4) run_share,
    round(60 * sum(l.run_share * w.miles / l.mph_sch) / sum(w.miles / l.mph_sch), 2) min_per_hr,
    count(*) lines, round(sum(l.miles_measured) / sum(w.miles), 3) measured_share_of_sched_miles"""
con.execute(f"CREATE TABLE ly AS {lines('s.yr')}")
con.execute(f"CREATE TABLE wy AS {weights('CAST(left(month,4) AS INT)')}")
con.execute(f"""COPY (SELECT l.route, l.g yr, round(l.mph, 2) mph, round(l.mph_sch, 2) mph_sch, round(l.run_share, 4) run_share, round(l.miles_measured, 0) miles_measured,
    round(w.miles, 0) sched_miles, l.months FROM ly l LEFT JOIN wy w USING (route, g) ORDER BY 1, 2) TO '{out}/speed_line_year.csv' (HEADER)""")
con.execute(f"""COPY (SELECT l.g yr, {CITY}, max(l.months) AS months FROM ly l JOIN wy w USING (route, g) GROUP BY 1 ORDER BY 1) TO '{out}/speed_system_year.csv' (HEADER)""")
con.execute(f"CREATE TABLE lm AS {lines('s.month')}")
con.execute(f"CREATE TABLE wm AS {weights('month')}")
con.execute(f"""COPY (SELECT l.g AS month, {CITY} FROM lm l JOIN wm w USING (route, g) GROUP BY 1 ORDER BY 1) TO '{out}/speed_system_month.csv' (HEADER)""")

# periods
P = (f"CASE WHEN s.month IN ({inl(f12)}) THEN 'first12' WHEN s.month IN ({inl(l12)}) THEN 'latest12' END",
     f"CASE WHEN month IN ({inl(f12)}) THEN 'first12' WHEN month IN ({inl(l12)}) THEN 'latest12' END")
S = ("CASE WHEN substr(s.month,6,2) BETWEEN '03' AND '10' AND s.yr IN (2025, 2026) THEN 'mar_oct_' || s.yr END",
     "CASE WHEN substr(month,6,2) BETWEEN '03' AND '10' AND left(month,4) IN ('2025', '2026') THEN 'mar_oct_' || left(month,4) END")
con.execute(f"CREATE TABLE lp AS {lines(P[0])} UNION ALL {lines(S[0])}")
con.execute(f"CREATE TABLE wp AS {weights(P[1])} UNION ALL {weights(S[1])}")
con.execute(f"""CREATE TABLE l19 AS SELECT s.route, sum(s.dist) / sum(s.obs_s) * 3600 mph FROM seg s WHERE s.month = '2019-09' GROUP BY 1""")
con.execute(f"""COPY (SELECT l.g AS period, {CITY} FROM lp l JOIN wp w USING (route, g) WHERE l.g IS NOT NULL GROUP BY 1
  UNION ALL SELECT 'sep2019_like_for_like', round(sum(s19.miles) / sum(s19.miles / a.mph), 2), round(sum(s19.miles) / sum(s19.miles / s19.mph_sch), 2),
    NULL, NULL, count(*), NULL FROM l19 a JOIN s19 USING (route) JOIN lp b ON b.route = a.route AND b.g = 'latest12'
  UNION ALL SELECT 'latest12_like_for_like', round(sum(s19.miles) / sum(s19.miles / b.mph), 2), round(sum(s19.miles) / sum(s19.miles / b.mph_sch), 2),
    NULL, NULL, count(*), NULL FROM l19 a JOIN s19 USING (route) JOIN lp b ON b.route = a.route AND b.g = 'latest12'
  ORDER BY 1) TO '{out}/system_period.csv' (HEADER)""")

# running time by line, year and month
con.execute(f"""COPY (SELECT route, g yr, round(run_share, 4) run_share, round(60 * run_share, 2) min_per_hr FROM ly ORDER BY 1, 2) TO '{out}/run_line_year.csv' (HEADER)""")
# per trip, the distribution
con.execute("""CREATE TABLE ty AS SELECT route, yr, count(*) trips_measured, avg(obs_s - sch_s) / 60 trip_min,
    avg(CASE WHEN abs(obs_s - sch_s) <= 300 THEN 1.0 ELSE 0 END) within_5min, avg(sch_s) / 60 sched_min FROM trip GROUP BY ALL""")
con.execute(f"""COPY (SELECT l.g yr, {CITY}, round(sum(t.trip_min * w.trips) / sum(w.trips), 2) trip_min, round(sum(t.within_5min * w.trips) / sum(w.trips), 3) within_5min,
    round(sum(t.sched_min * w.trips) / sum(w.trips), 1) trip_window_sched_min, round(sum(t.trips_measured) / sum(w.trips), 3) trips_measured_share
  FROM ly l JOIN wy w USING (route, g) LEFT JOIN ty t ON t.route = l.route AND t.yr = l.g GROUP BY 1 ORDER BY 1) TO '{out}/run_system_year.csv' (HEADER)""")
con.execute(f"""COPY (SELECT l.g AS month, round(sum(l.run_share * w.miles / l.mph_sch) / sum(w.miles / l.mph_sch), 4) run_share
  FROM lm l JOIN wm w USING (route, g) GROUP BY 1 ORDER BY 1) TO '{out}/run_system_month.csv' (HEADER)""")

# per line: 2019, first 12 and latest 12 usable months
con.execute(f"""CREATE TABLE tp AS SELECT route, {P[1]} per, avg(obs_s - sch_s) / 60 trip_min, avg(CASE WHEN abs(obs_s - sch_s) <= 300 THEN 1.0 ELSE 0 END) w5, count(*) n
  FROM trip GROUP BY ALL""")
con.execute(f"""COPY (SELECT l.route, round(y.mph, 2) mph_2019, round(f.mph, 2) mph_first12, round(l.mph, 2) mph_latest12, round(l.mph_sch, 2) mph_sched_latest12,
    round(f.run_share, 4) run_share_first12, round(l.run_share, 4) run_share_latest12, round(60 * l.run_share, 2) min_per_hr_latest12,
    round(t.trip_min, 2) trip_min_latest12, round(t.w5, 3) within_5min_latest12, t.n trips_latest12, round(w.miles, 0) sched_miles_latest12
  FROM lp l LEFT JOIN lp f ON f.route = l.route AND f.g = 'first12' LEFT JOIN l19 y ON y.route = l.route
    LEFT JOIN tp t ON t.route = l.route AND t.per = 'latest12' LEFT JOIN wp w ON w.route = l.route AND w.g = 'latest12'
  WHERE l.g = 'latest12' ORDER BY l.route) TO '{out}/trip_rank.csv' (HEADER)""")
for f in ("speed_system_year", "system_period", "run_system_year"):
    print("==", f); print(con.sql(f"SELECT * FROM read_csv('{out}/{f}.csv')"))
