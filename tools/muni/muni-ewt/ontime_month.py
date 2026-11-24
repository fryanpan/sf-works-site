"""On-time departures at timepoints on SFMTA's Connector and Owl lines (freq_rule.py), for one month.

Bryan, 2026-11-09: on-time for the lines and hours excess wait doesn't cover, with "X% left early" under it, because
"for lines that don't come very often, the really annoying thing is when the bus comes early."

Windows: two, counted on the same departures. SFMTA's, 1 minute early to 4 late (its on-time definition; Bryan,
2026-11-14: hours a line runs less often than every 10 minutes are scored on on-time departures
in SFMTA's window), as early_sf and late_sf; the line optimizer reads these. And TfL's for low-frequency routes,
"percent on time (2 minutes early to 5 late)". A departure is early when it leaves more than 2 minutes before its
scheduled time (the window's early edge), late when more than 5 minutes after, and on time otherwise. 511 gives one
observed time per stop (its departure equals its arrival), so this is arrival-based.

Scheduled time: the timetable's own time for the trip at that stop, from the GTFS 511 bundles with the month (its
trip ids carry the feed date, and every observed trip id is in it, so it is the version in force on each date). Not
511's scheduled_departure_time: in some periods (2023-01 to 2024-06, and from 2026-08-30) 511 numbers a trip's
observations 1, 2, 3 ... by position and looks the schedule up by that number, so where the trip's GTFS stop_sequence
skips a number, every stop after the gap carries the scheduled time of the stop before it (or none). In other periods
(2024-08, 2026-07) the same gaps exist but 511 numbers by stop_sequence and its times are right. The bad periods hit
about 5% of rows; from 2026-08-30 they fall on the J, K, L, M, N, 9, 14R, 15, 30, 56 and T, and moved those lines'
late share by up to 17 points. A trip that visits a stop twice takes the visit nearest 511's time (or, with no 511
time, is unmatched).
A stand-in timetable month (make_sched.py, 2022-08 to 2022-12) keeps 511's own time, as before: its timetable is an
SFMTA capture that may not be the one in force, and 511's times there equal the stand-in's exactly in 2022-08 to 10.

Which departures count: observed departures at the stops the timetable marks as timepoints (stop_times.timepoint = 1,
at the matched visit), 5 am to 11 pm by scheduled time, in a stop-hour block of hourly/<YYYY-MM>.parquet
(ewt_month.py) on an infrequent line, SFMTA's Connector and Owl lines (freq_rule.py; Bryan, 2026-11-17, "SFMTA's line
types", replacing the per stop-hour 10-minute switch; the same split as excess wait, ewt_aggregate.py --frequent) and not excluded there for a feed or line-day outage. Each trip's first stop is dropped (511's
sequence 1, and the timetable's first stop, which 511 numbers 2 in periods it numbers by stop_sequence), and so is its
last. SFMTA counts "vehicle timepoint departures", origin terminals included (sfmta.com, Muni On-Time Performance, archived
2025-10-16, read 2026-11-15: its departure-based method "allows for better measurement of on-time performance at the
beginnings of trips as vehicles depart from their origin terminals"), but 511 doesn't time a departure there: at first
stops it is never more than a minute early and 45% of rows equal the timetable to the second (July 2024 to October
2026, 6.0 million rows; check.json "first_stops"), so its time there is held to the schedule and can't be scored. A
last stop has no departure, and 511's time there is the arrival: 40% of them over 4 minutes late against 19% at the
stops between (5.5 million rows, same months; "last_stops"), the recovery time built into the schedule read as
lateness. Leaving last stops out raised our systemwide figure 1.8 points for FY2024-25 and 2.1 for July to December
2025. The observations are cleaned as ewt_month.py cleans them (dedupe nearest the schedule, out-of-order rows dropped). Rows
with no timetable time are left out and counted. A stand-in month has no timepoint flags, so every stop counts; a
month where no observed trip matches its stand-in falls back to every observed stop, and the summary line says so.

Checks, before any CSV is written (exit 1 with the reasons in <m>-check.json; post_all.sh stops before its stamp, and
vm_local.sh exits before copying, so the repo keeps its last good CSVs):
  - every service date with observations has trips in the timetable's calendar. A date without is left out and listed
    (2026-08-29: 511's bundle carries the feed ending 08-28 and the one starting 08-30, and neither runs that
    Saturday; 2023-09-11 to 13 likewise). Over a fifth of the month's dates without one means the month is being
    scored against no timetable, and fails.
  - the share of observation rows (first stops out) whose trip and stop are in the timetable: at least 98% over the
    month and 90% on every date, calendar or not (a missing feed shows as low matching, not only as no calendar).
    A timetable that isn't the one in force fails this, since its trip ids carry another feed date. Good months sit at 98.6% (2022-12, a stand-in) to 100%.

Output, into <outdir>/ontime/: <YYYY-MM>-stops.csv (route, dir, stop: n, early, late, early_sf, late_sf over the month),
<YYYY-MM>-days.csv (route, sdate, hr: n, early, late, early_sf, late_sf; kept on the VM for trends within a period, not copied to the
repo), <YYYY-MM>-lines.csv (route, sdate, freq: n, early_sf, late_sf, every timepoint departure 5 am to 11 pm, frequent
hours too with freq 1, so the month can be set against SFMTA's systemwide figure and a day type picked; the optimizer
reads it), sorted, routes renamed as ewt_daily.py renames them, and <YYYY-MM>-check.json: the checks above, the feed dates
of the timetable and of the observed trip ids, the share of scored departures where 511's own time differs from the
timetable's, the month scored both ways on the same departures (the standing version of the 2026-11-10 check), first
and last stops scored as they would be ("first_stops", "last_stops"), the timepoint rows the join to the stop-hour
blocks loses ("hourly_join": no block for the stop and hour, or a block excluded for an outage), and every hour in
SFMTA's window ("all_hours_sf").
Usage: PYTHONPATH=pylib python3 ontime_month.py <extract dir> <ewt dir> <YYYY-MM>
"""
import os, sys, json, duckdb
from freq_rule import frequent_sql  # the one frequent-service rule (freq_rule.py)

d, E, month = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(f"{E}/ontime", exist_ok=True)
con = duckdb.connect()
con.execute("SET threads=5; SET memory_limit='16GB'; SET preserve_insertion_order=false")
T = lambda c: (f"(CASE WHEN contains({c}, ':') THEN TRY_CAST(split_part({c},':',1) AS INT)*3600+TRY_CAST(split_part({c},':',2) AS INT)*60"
               f"+TRY_CAST(split_part({c},':',3) AS INT) ELSE TRY_CAST({c} AS INT) END)")
rd = lambda f: f"read_csv('{d}/{f}', header=true, all_varchar=true)"
one = lambda s, p=None: con.execute(s, p or []).fetchone()
REN = "CASE r WHEN 'LBUS' THEN 'L' WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE r END"
EARLY, LATE = 120, 300
SF_EARLY, SF_LATE = 60, 240  # SFMTA's on-time window, 1 minute early to 4 late (see docstring)
MONTH_FLOOR, DATE_FLOOR, NOCAL_MAX = 0.98, 0.90, 0.2
STANDIN = os.path.exists(f"{d}/SCHEDULE_SOURCE")
KEY = "'SFG:' || split_part(split_part(o.trip_id, ':', 2), '_', 1)" if STANDIN else "o.trip_id"
ym = month.replace("-", "")

con.execute(f"CREATE TABLE trips AS SELECT trip_id, service_id, direction_id dir FROM {rd('trips.csv.gz')}")
cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rd('stop_times.csv.gz')}").fetchall()]
TP = "timepoint = '1'" if "timepoint" in cols else "true"
con.execute(f"""CREATE TABLE st AS SELECT trip_id, stop_id stop, {T("coalesce(nullif(departure_time,''), arrival_time)")} t,
  coalesce({TP}, false) tp, CAST(stop_sequence AS INT) = min(CAST(stop_sequence AS INT)) OVER (PARTITION BY trip_id) AS is_first,
  CAST(stop_sequence AS INT) = max(CAST(stop_sequence AS INT)) OVER (PARTITION BY trip_id) AS is_last
  FROM {rd('stop_times.csv.gz')}""")
con.execute(f"""CREATE TABLE cd AS SELECT service_id, date sdate FROM {rd('calendar_dates.csv.gz')} GROUP BY 1, 2
  HAVING bool_or(exception_type = '1') AND NOT bool_or(exception_type = '2')""")
con.execute(f"""CREATE TABLE o00 AS SELECT row_number() OVER () rid, o.trip_id, o.service_date sdate, CAST(o.stop_sequence AS INT) seq,
  o.to_stop_id stop, replace(o.route_id, 'SF:', '') r, coalesce(t.dir, nullif(o.direction_id,'')) dir,
  {T("coalesce(nullif(o.observed_departure_time,''), o.observed_arrival_time)")} a,
  {T("coalesce(nullif(o.scheduled_departure_time,''), o.scheduled_arrival_time)")} s511
  FROM {rd('stop_observations.csv.gz')} o LEFT JOIN trips t USING (trip_id) WHERE o.service_date LIKE ? || '%'""", [ym])
# each observation's own trip and stop in the timetable; where the trip visits the stop twice, the visit nearest 511's time
con.execute(f"""CREATE TABLE m AS SELECT o.rid, count(st.t) nvis,
  CASE WHEN count(st.t) = 1 OR o.s511 IS NOT NULL THEN arg_min(st.t, abs(st.t - coalesce(o.s511, st.t))) END gt,
  CASE WHEN count(st.t) = 1 OR o.s511 IS NOT NULL THEN arg_min(st.tp, abs(st.t - coalesce(o.s511, st.t))) END gtp,
  CASE WHEN count(st.t) = 1 OR o.s511 IS NOT NULL THEN arg_min(st.is_first, abs(st.t - coalesce(o.s511, st.t))) END gfirst,
  CASE WHEN count(st.t) = 1 OR o.s511 IS NOT NULL THEN arg_min(st.is_last, abs(st.t - coalesce(o.s511, st.t))) END glast
  FROM o00 o LEFT JOIN st ON st.trip_id = {KEY} AND st.stop = o.stop AND st.t IS NOT NULL GROUP BY o.rid, o.s511""")
con.execute("CREATE TABLE o0 AS SELECT o.*, m.gt, coalesce(m.gtp, false) gtp, coalesce(m.gfirst, false) gfirst, coalesce(m.glast, false) glast, CASE WHEN ? THEN o.s511 ELSE m.gt END s FROM o00 o LEFT JOIN m USING (rid)", [STANDIN])

# --- checks ---
chk = {"month": month, "timetable": open(f"{d}/SCHEDULE_SOURCE").read().strip() if STANDIN else "511 bundled GTFS",
       "scheduled_time": "511 scheduled_departure_time (stand-in month)" if STANDIN else "timetable stop_times at the trip and stop"}
chk["timetable_feed_dates"] = [r[0] for r in con.execute("SELECT DISTINCT split_part(trip_id, ':', 3) FROM trips ORDER BY 1").fetchall()]
chk["observed_feed_dates"] = [list(r) for r in con.execute("""SELECT split_part(trip_id, ':', 3) f, min(sdate), max(sdate), count(*)
  FROM o00 GROUP BY 1 ORDER BY 1""").fetchall()]
bydate = con.execute("""SELECT o.sdate, count(*) n, count(o.gt) k, (SELECT count(*) FROM trips t JOIN cd USING (service_id) WHERE cd.sdate = o.sdate) ntrips
  FROM o0 o WHERE o.seq > 1 GROUP BY 1 ORDER BY 1""").fetchall()
n_all, k_all = sum(r[1] for r in bydate), sum(r[2] for r in bydate)
chk["rows_first_stops_out"], chk["rows_matched"] = n_all, k_all
chk["matched_share"] = round(k_all / max(n_all, 1), 4)
chk["matched_share_by_date"] = [[r[0], round(r[2] / max(r[1], 1), 4), r[3]] for r in bydate]
# a date the timetable's calendar has no service on is left out (ewt_month.py builds no blocks for it either) and listed
nocal = [r[0] for r in bydate if r[3] == 0]
chk["dates_without_timetable"] = nocal
fails = [f"{len(nocal)} of {len(bydate)} dates have no trips in the timetable's calendar ({', '.join(nocal[:5])})"] if len(nocal) > NOCAL_MAX * len(bydate) else []
fails += [f"{r[0]}: {r[2] / max(r[1], 1):.1%} of rows matched, under {DATE_FLOOR:.0%}" for r in bydate if r[2] < DATE_FLOOR * r[1]]
if chk["matched_share"] < MONTH_FLOOR:
    fails.append(f"month: {chk['matched_share']:.1%} of rows matched, under {MONTH_FLOOR:.0%}")
if not bydate:
    fails.append("no observations in the month")
chk["fails"] = fails
if fails:
    json.dump(chk, open(f"{E}/ontime/{month}-check.json", "w"), indent=1, default=str)
    print(f"{month}: ontime check FAILED, nothing written:", "; ".join(fails[:5]), file=sys.stderr)
    sys.exit(1)

# the same cleaning as ewt_month.py, rules 1 to 3, on the scheduled time chosen above
for x in nocal:
    con.execute("DELETE FROM o0 WHERE sdate = ?", [x])
con.execute("UPDATE o0 SET a = a + 86400 WHERE s IS NOT NULL AND a < s - 43200")
# a trip's first and last stops, as 511 times them, against the timetable: the docstring's reasons for leaving them out
for k, w in (("first_stops", "(seq = 1 OR gfirst)"), ("last_stops", "seq > 1 AND NOT gfirst AND glast")):
    r_ = one(f"""SELECT count(*), avg(CASE WHEN a < s - {SF_EARLY} THEN 1 ELSE 0 END), avg(CASE WHEN a > s + {SF_LATE} THEN 1 ELSE 0 END),
      avg(CASE WHEN a = s THEN 1 ELSE 0 END) FROM o0 WHERE {w} AND gtp AND dir IS NOT NULL AND a IS NOT NULL AND s // 3600 BETWEEN 5 AND 22""")
    chk[k] = {"n": r_[0], "early_sf": round(r_[1] or 0, 4), "late_sf": round(r_[2] or 0, 4), "exactly_on_schedule": round(r_[3] or 0, 4)}
con.execute("CREATE TABLE o2 AS SELECT * FROM o0 WHERE seq > 1 AND NOT gfirst AND NOT glast AND dir IS NOT NULL AND a IS NOT NULL QUALIFY row_number() OVER (PARTITION BY trip_id, sdate, stop ORDER BY abs(a - coalesce(s, a)), a) = 1")
con.execute("""CREATE TABLE o3 AS SELECT *, (pm IS NOT NULL AND a < pm - 60) ff, (nm IS NOT NULL AND a > nm + 60) bf FROM
  (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm,
             min(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) nm FROM o2)""")
con.execute("""CREATE TABLE o4 AS SELECT o3.* EXCLUDE (pm, nm, ff, bf) FROM o3 JOIN (SELECT trip_id, sdate, count(*) FILTER (WHERE bf) < count(*) FILTER (WHERE ff) useb
  FROM o3 GROUP BY 1, 2) k USING (trip_id, sdate) WHERE NOT (CASE WHEN k.useb THEN bf ELSE ff END)""")
con.execute("""CREATE TABLE obs AS SELECT * EXCLUDE (pm) FROM (SELECT *, max(a) OVER (PARTITION BY trip_id, sdate ORDER BY seq
  ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pm FROM o4) WHERE pm IS NULL OR a >= pm - 60""")
# timepoints, then the infrequent, unexcluded stop-hours of ewt_month.py's blocks
con.execute("CREATE TABLE ot AS SELECT *, s // 3600 hr FROM obs WHERE gtp AND s IS NOT NULL AND s // 3600 BETWEEN 5 AND 22")
chk["unmatched_dropped_after_cleaning"] = one("SELECT count(*) FROM obs WHERE gt IS NULL")[0]
fallback = STANDIN and one("SELECT count(*) FROM ot")[0] == 0
if fallback:
    con.execute("CREATE OR REPLACE TABLE ot AS SELECT *, s // 3600 hr FROM obs WHERE s IS NOT NULL AND s // 3600 BETWEEN 5 AND 22")
# the rows the join to the stop-hour blocks loses: no block for the stop and hour, or a block excluded for an outage
j = one(f"""SELECT count(*), count(h.route), count(h.route) FILTER (WHERE h.excl IS NULL) FROM ot LEFT JOIN
  (SELECT DISTINCT route, CAST(dir AS VARCHAR) dir, stop, sdate, hr, excl FROM read_parquet('{E}/hourly/{month}.parquet')) h
  ON h.route = ot.r AND h.dir = CAST(ot.dir AS VARCHAR) AND h.stop = ot.stop AND h.sdate = ot.sdate AND h.hr = ot.hr""")
chk["hourly_join"] = {"timepoint_rows": j[0], "no_block": j[0] - j[1], "excluded_block": j[1] - j[2], "kept": j[2]}
con.execute(f"""CREATE TABLE x AS SELECT {REN} route, ot.dir, ot.stop, ot.sdate, ot.hr, ot.s511, ot.gt, ot.a,
  CASE WHEN a < s - {EARLY} THEN 1 ELSE 0 END early, CASE WHEN a > s + {LATE} THEN 1 ELSE 0 END late,
  CASE WHEN a < s - {SF_EARLY} THEN 1 ELSE 0 END early_sf, CASE WHEN a > s + {SF_LATE} THEN 1 ELSE 0 END late_sf,
  {frequent_sql('h.')} freq
  FROM ot JOIN read_parquet('{E}/hourly/{month}.parquet') h
  ON h.route = ot.r AND CAST(h.dir AS VARCHAR) = CAST(ot.dir AS VARCHAR) AND h.stop = ot.stop AND h.sdate = ot.sdate AND h.hr = ot.hr
  WHERE h.excl IS NULL""")
# every timepoint departure, frequent hours too, by line, date and how the hour is run: the systemwide check against
#   SFMTA's published on-time figure, which counts every hour (docstring, "Output")
con.execute(f"""COPY (SELECT route, sdate, CAST(freq AS INT) freq, count(*) n, sum(early_sf) early_sf, sum(late_sf) late_sf
  FROM x GROUP BY ALL ORDER BY ALL) TO '{E}/ontime/{month}-lines.csv.tmp' (HEADER)""")
f_ = one("SELECT count(*), sum(early_sf), sum(late_sf) FROM x")
chk["all_hours_sf"] = {"n": f_[0], "early_sf": f_[1], "late_sf": f_[2]}
con.execute("DELETE FROM x WHERE freq")
# the month scored both ways, on the departures that carry both times
b = one(f"""SELECT count(*), count(*) FILTER (WHERE s511 <> gt),
  count(*) FILTER (WHERE a BETWEEN gt - {EARLY} AND gt + {LATE}), count(*) FILTER (WHERE a > gt + {LATE}), count(*) FILTER (WHERE a < gt - {EARLY}),
  count(*) FILTER (WHERE a BETWEEN s511 - {EARLY} AND s511 + {LATE}), count(*) FILTER (WHERE a > s511 + {LATE}), count(*) FILTER (WHERE a < s511 - {EARLY})
  FROM x WHERE s511 IS NOT NULL AND gt IS NOT NULL""")
pc = lambda v: round(100 * v / max(b[0], 1), 2)
chk["scored_both"] = {"n": b[0], "s511_differs_share": round(b[1] / max(b[0], 1), 4),
                      "vs_timetable": {"on_time": pc(b[2]), "late": pc(b[3]), "early": pc(b[4])},
                      "vs_511": {"on_time": pc(b[5]), "late": pc(b[6]), "early": pc(b[7])}}
con.execute(f"""COPY (SELECT route, dir, stop, count(*) n, sum(early) early, sum(late) late, sum(early_sf) early_sf,
  sum(late_sf) late_sf FROM x GROUP BY ALL ORDER BY ALL)
  TO '{E}/ontime/{month}-stops.csv.tmp' (HEADER)""")
con.execute(f"""COPY (SELECT route, sdate, hr, count(*) n, sum(early) early, sum(late) late, sum(early_sf) early_sf,
  sum(late_sf) late_sf FROM x GROUP BY ALL ORDER BY ALL)
  TO '{E}/ontime/{month}-days.csv.tmp' (HEADER)""")
n, e, l, esf, lsf = one("SELECT count(*), sum(early), sum(late), sum(early_sf), sum(late_sf) FROM x")
chk["scored"] = {"n": n, "early": e, "late": l, "early_sf": esf, "late_sf": lsf}
json.dump(chk, open(f"{E}/ontime/{month}-check.json", "w"), indent=1, default=str)
for f in ("stops", "days", "lines"):
    os.replace(f"{E}/ontime/{month}-{f}.csv.tmp", f"{E}/ontime/{month}-{f}.csv")
print(f"{month}: {n} timepoint departures in infrequent hours, {100 * e / max(n, 1):.1f}% early, {100 * l / max(n, 1):.1f}% late"
      f", on time {100 * (n - e - l) / max(n, 1):.1f}%; {chk['matched_share']:.2%} of rows in the timetable"
      f", 511's time differs on {100 * chk['scored_both']['s511_differs_share']:.1f}%"
      f"{' (stand-in timetable: every stop, no timepoints matched)' if fallback else ''}")
