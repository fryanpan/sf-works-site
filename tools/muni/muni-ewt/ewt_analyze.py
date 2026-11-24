"""Summaries of Muni excess wait, January 2022 onward, from the line x month x day type x hour extract of ewt_aggregate.py.

Weighting is TfL's ("iBus Data Aggregation for QSIs" v2.1, 2.3 and 2.12): stops are combined in ewt_aggregate.py
(Step I); within a line, hours are combined weighting each line-month-daytype-hour cell by its scheduled departures
(eb), standing in for TfL's passenger journeys, which Muni doesn't publish by line and hour (Step II); across lines,
SWT is weighted by scheduled departures and AWT by observed departures (Step III, 2.12.3). --eb weights AWT by
scheduled departures at Step III too; with ewt_aggregate.py --eb that is the scheduled-bus sensitivity check.
EWT = AWT - SWT after aggregation. Hours counted: 05:00 to 23:00. TfL's day period runs to
midnight, but in every 511 year the feed loses 18% to 26% of observed buses between 23:20 and 23:59 (observed over
scheduled 0.74 to 0.83 at hour 23 against 0.96 to 0.98 either side; Fable review 2026-11-09, J1 and J2), so hour 23
is left out; owl hours are left out too.
Decomposition (ewt_aggregate.py): ewt_missing = tswt_eb - swt (timetabled buses absent from the feed, missed or
untracked), ewt_weighting = tswt_ob - tswt_eb (TfL's observed-bus weights for AWT on their own), ewt_spacing = the rest,
which is awt - tswt_ob (tracked buses unevenly spaced). The first two are taken over the cells that carry tswt (all
but a handful whose observation rows lack a scheduled time), so the three parts add up to ewt exactly. At every step
tswt_eb takes SWT's weights and tswt_ob AWT's.
Yearly and 12-month figures (system_year.csv) are means of the usable months weighted by each month's scheduled
departures; 2024, 2025 and 2026 have ten usable months each.
Line ids: LBUS (the L Taraval run by buses, in the feed through 2024) is counted as the L. ewt_equal_hours in system_month.csv is the sensitivity check
that gives every service-date hour of a line equal weight in Step II instead. "High-frequency" keeps only cells with 5 or more scheduled departures
per stop-direction hour (TfL 1.6); "all" keeps every cell.
Inputs: <extract.csv> <diag dir> (the per-month JSON and -route.csv from ewt_month.py) <scorecard dir> (DataSF
kc49-udxn JSON). Outputs, into <outdir>: line_year.csv, system_year.csv, line_month.csv (with 12-month rolling, shown where 9 or more of the 12 months
are usable, and year-over-year),
system_month.csv, heat_line_hour.csv (weekday, first 12 vs last 12 months), intake_service_delivered.csv,
intake_headway_adherence.csv. Usage: python3 ewt_analyze.py <extract.csv> <diag dir> <scorecard dir> <outdir>
"""
import sys, os, json, glob, duckdb

ext, diag, scd, out = [x for x in sys.argv[1:] if not x.startswith("--")][:4]
AW = "eb" if "--eb" in sys.argv else "ob"  # AWT's weight across lines (TfL: ob)
os.makedirs(out, exist_ok=True)
con = duckdb.connect()
# route ids renamed in the feed: C became CA (cable car), L-OWL and N-OWL became LOWL and NOWL. KT (one line until
# the K and T were split) is kept as its own line. LBUS, the L run by buses, is counted as the L.
REN = "CASE route WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' WHEN 'LBUS' THEN 'L' ELSE route END"
# Months whose feed kept under 60% of scheduled departures (05:00-23:00) after the outage rules are left out of every
# summary: from 2024-11-09 the feed thins to about a seventh of its rows (see the month table, <extract>_months.csv).
MINKEEP = 0.6
con.execute(f"CREATE TABLE mk AS SELECT * FROM read_csv('{ext[:-4]}_months.csv', header=true)")
con.execute(f"""CREATE TABLE c AS SELECT * REPLACE ({REN} AS route), CAST(left(month,4) AS INT) yr FROM read_csv('{ext}', header=true)
  WHERE hr BETWEEN 5 AND 22 AND swt IS NOT NULL AND awt IS NOT NULL AND month <> '2019-09'
    AND month IN (SELECT month FROM mk WHERE kept_share >= {MINKEEP})""")
# LBUS and L in the same month become one line: merge their cells as stops are merged at Step I (n_* summed)
con.execute(f"""CREATE TABLE c2 AS SELECT route, month, daytype, hr, any_value(yr) yr, sum(dates) dates, sum(n_swt) n_swt, sum(n_awt) n_awt,
  sum(swt*eb)/sum(eb) swt, sum(awt*{AW})/sum({AW}) awt, sum(tswt_eb*eb) FILTER (WHERE tswt_eb IS NOT NULL)/sum(eb) FILTER (WHERE tswt_eb IS NOT NULL) tswt_eb,
  sum(tswt_ob*{AW}) FILTER (WHERE tswt_ob IS NOT NULL)/sum({AW}) FILTER (WHERE tswt_ob IS NOT NULL) tswt_ob,
  sum(eb) eb, sum(ob) ob, sum(eb_per_block*eb)/sum(eb) eb_per_block, sum(eb_per_block*eb)/sum(eb) < 5 lowfreq FROM c GROUP BY ALL""")
con.execute("DROP TABLE c; ALTER TABLE c2 RENAME TO c")
con.execute(f"""CREATE TABLE c19 AS SELECT * REPLACE ({REN} AS route) FROM read_csv('{ext}', header=true)
  WHERE hr BETWEEN 5 AND 22 AND swt IS NOT NULL AND awt IS NOT NULL AND month = '2019-09'""")

# Step II within a line: weight cells by eb. Returns per-group swt, awt, eb, ob
def line_agg(where, group):
    return f"""SELECT {group}, sum(swt*eb)/sum(eb) swt, sum(awt*eb)/sum(eb) awt, sum(eb) eb, sum(ob) ob,
      sum((tswt_eb-swt)*eb) FILTER (WHERE tswt_ob IS NOT NULL) / sum(eb) FILTER (WHERE tswt_ob IS NOT NULL) mis,
      sum((tswt_ob-tswt_eb)*eb) FILTER (WHERE tswt_ob IS NOT NULL) / sum(eb) FILTER (WHERE tswt_ob IS NOT NULL) wgt
      FROM c WHERE {where} GROUP BY ALL"""
def fmt(sel):
    return f"""SELECT *, round(awt - swt, 3) ewt FROM ({sel})"""

# line x year, all and high-frequency hours, all day types and weekday only
con.execute(f"""CREATE TABLE ly AS
  SELECT a.route, a.yr, round(a.awt-a.swt,2) ewt_all, round(w.awt-w.swt,2) ewt_weekday,
    round(h.awt-h.swt,2) ewt_hf, round(a.mis,2) ewt_missing, round(a.awt-a.swt-a.mis-a.wgt,2) ewt_spacing, round(a.wgt,2) ewt_weighting, round(a.swt,2) swt_all, round(a.awt,2) awt_all, round(h.eb/a.eb,3) hf_share_of_sched,
    a.eb sched_departures, round(a.ob/a.eb,3) obs_over_sched,
    (SELECT count(DISTINCT month) FROM c x WHERE x.route=a.route AND x.yr=a.yr) AS months
  FROM ({line_agg('true','route, yr')}) a LEFT JOIN ({line_agg("daytype='weekday'",'route, yr')}) w USING (route, yr)
  LEFT JOIN ({line_agg('NOT lowfreq','route, yr')}) h USING (route, yr) ORDER BY 1,2""")
con.execute(f"COPY ly TO '{out}/line_year.csv' (HEADER)")

# line x month with rolling 12 and year over year
con.execute(f"""CREATE TABLE lm AS WITH m AS ({line_agg('true','route, month')}),
  h AS ({line_agg('NOT lowfreq','route, month')})
  SELECT m.route, m.month, round(m.awt-m.swt,3) ewt_all, round(h.awt-h.swt,3) ewt_hf, m.eb, m.ob, m.swt, m.awt,
    (SELECT round(sum(x.awt*x.eb)/sum(x.eb) - sum(x.swt*x.eb)/sum(x.eb),3) FROM m x WHERE x.route=m.route
      AND strptime(x.month,'%Y-%m') BETWEEN strptime(m.month,'%Y-%m') - INTERVAL 11 MONTH AND strptime(m.month,'%Y-%m')) ewt_roll12,
    (SELECT count(*) FROM m x WHERE x.route=m.route
      AND strptime(x.month,'%Y-%m') BETWEEN strptime(m.month,'%Y-%m') - INTERVAL 11 MONTH AND strptime(m.month,'%Y-%m')) roll_n
  FROM m LEFT JOIN h USING (route, month)""")
con.execute(f"""COPY (SELECT a.route, a.month, a.ewt_all, a.ewt_hf, CASE WHEN a.roll_n>=9 THEN a.ewt_roll12 END ewt_roll12, a.roll_n roll_months,
    round(a.ewt_all - b.ewt_all,3) ewt_yoy, a.eb sched_departures, a.ob obs_departures
  FROM lm a LEFT JOIN lm b ON b.route=a.route AND strptime(b.month,'%Y-%m') = strptime(a.month,'%Y-%m') - INTERVAL 12 MONTH
  ORDER BY 1,2) TO '{out}/line_month.csv' (HEADER)""")

# systemwide by month: Step III across lines, SWT and AWT by eb
def sysm(where, name, src="c"):
    # Step III: per line (Step II by eb), then across lines SWT and tswt_eb by eb, AWT and tswt_ob by AW
    return f"""SELECT month, sum(swt*eb)/sum(eb) swt_{name}, sum(awt*{AW})/sum({AW}) awt_{name},
      sum(awt*{AW})/sum({AW}) - sum(swt*eb)/sum(eb) ewt_{name},
      sum(mis*eb) FILTER (WHERE mis IS NOT NULL)/sum(eb) FILTER (WHERE mis IS NOT NULL) ewt_missing_{name},
      sum(tob*{AW}) FILTER (WHERE tob IS NOT NULL)/sum({AW}) FILTER (WHERE tob IS NOT NULL)
        - sum(teb*eb) FILTER (WHERE teb IS NOT NULL)/sum(eb) FILTER (WHERE teb IS NOT NULL) ewt_weighting_{name},
      sum(eb) eb_{name} FROM (
      SELECT route, month, sum(swt*eb)/sum(eb) swt, sum(awt*eb)/sum(eb) awt, sum(eb) eb, sum(ob) ob,
        sum((tswt_eb-swt)*eb) FILTER (WHERE tswt_ob IS NOT NULL)/sum(eb) FILTER (WHERE tswt_ob IS NOT NULL) mis,
        sum(tswt_eb*eb) FILTER (WHERE tswt_ob IS NOT NULL)/sum(eb) FILTER (WHERE tswt_ob IS NOT NULL) teb,
        sum(tswt_ob*eb) FILTER (WHERE tswt_ob IS NOT NULL)/sum(eb) FILTER (WHERE tswt_ob IS NOT NULL) tob
        FROM {src} WHERE {where} GROUP BY ALL) GROUP BY 1"""
for src in ("c", "c19"):
    con.execute(f"""CREATE TABLE sm_{src} AS SELECT * FROM ({sysm('true','all',src)}) JOIN ({sysm('NOT lowfreq','hf',src)}) USING (month)
      JOIN ({sysm("daytype='weekday'",'weekday',src)}) USING (month) JOIN ({sysm("daytype='weekday' AND NOT lowfreq",'weekday_hf',src)}) USING (month)
      JOIN (SELECT month, sum(awt*{AW})/sum({AW}) - sum(swt*eb)/sum(eb) ewt_equal_hours FROM (SELECT route, month, sum(swt*n_swt)/sum(n_swt) swt,
              sum(awt*n_swt)/sum(n_swt) awt, sum(eb) eb, sum(ob) ob FROM {src} GROUP BY ALL) GROUP BY 1) USING (month)
      JOIN (SELECT month, sum(ob)/sum(eb) obs_over_sched, count(DISTINCT route) lines FROM {src} GROUP BY 1) USING (month)""")
con.execute(f"""COPY (SELECT *, ewt_all - ewt_missing_all - ewt_weighting_all ewt_spacing_all FROM (SELECT * FROM sm_c19 UNION ALL BY NAME SELECT * FROM sm_c)
  ORDER BY month) TO '{out}/system_month.csv' (HEADER)""")
# by year: usable months weighted by their scheduled departures
con.execute(f"""COPY (SELECT CAST(left(month,4) AS INT) yr, count(*) AS months, round(sum(ewt_all*eb_all)/sum(eb_all),3) ewt_all,
    round(sum(ewt_missing_all*eb_all)/sum(eb_all),3) ewt_missing, round(sum((ewt_all-ewt_missing_all-ewt_weighting_all)*eb_all)/sum(eb_all),3) ewt_spacing,
    round(sum(ewt_weighting_all*eb_all)/sum(eb_all),3) ewt_weighting,
    round(avg(ewt_all),3) ewt_unweighted_mean, round(sum(ewt_hf*eb_hf)/sum(eb_hf),3) ewt_hf, round(sum(ewt_weekday*eb_weekday)/sum(eb_weekday),3) ewt_weekday,
    round(sum(obs_over_sched*eb_all)/sum(eb_all),4) obs_over_sched, string_agg(month, ' ' ORDER BY month) month_list
  FROM sm_c GROUP BY 1 ORDER BY 1) TO '{out}/system_year.csv' (HEADER)""")

# heat map: weekday, line x hour, first 12 months vs last 12 months
ms = [r[0] for r in con.execute("SELECT DISTINCT month FROM c ORDER BY 1").fetchall()]
first12, last12 = ms[:12], ms[-12:]
con.execute(f"""COPY (WITH x AS (SELECT route, hr, CASE WHEN month IN ({','.join(repr(m) for m in first12)}) THEN 'first12'
      WHEN month IN ({','.join(repr(m) for m in last12)}) THEN 'last12' END per, swt, awt, eb, lowfreq FROM c WHERE daytype='weekday')
  SELECT route, hr, per, round(sum(awt*eb)/sum(eb) - sum(swt*eb)/sum(eb),2) ewt, round(sum(swt*eb)/sum(eb),2) swt,
    sum(eb) eb, round(avg(CAST(lowfreq AS INT)),2) lowfreq_share
  FROM x WHERE per IS NOT NULL GROUP BY ALL ORDER BY 1,2,3) TO '{out}/heat_line_hour.csv' (HEADER)""")

# hour of day by year, weekdays: per line (Step II over months within the hour) and systemwide (Step III: SWT by eb, AWT by AW)
con.execute(f"""COPY (SELECT route, yr, hr, round(sum(awt*eb)/sum(eb) - sum(swt*eb)/sum(eb),3) ewt, round(sum(swt*eb)/sum(eb),3) swt,
    sum(eb) eb, round(avg(CAST(lowfreq AS INT)),2) lowfreq_share, count(DISTINCT month) AS months
  FROM c WHERE daytype='weekday' GROUP BY ALL ORDER BY 1,2,3) TO '{out}/line_year_hour.csv' (HEADER)""")
con.execute(f"""COPY (SELECT yr, hr, round(sum(awt*{AW})/sum({AW}) - sum(swt*eb)/sum(eb),3) ewt FROM (
    SELECT route, yr, hr, sum(swt*eb)/sum(eb) swt, sum(awt*eb)/sum(eb) awt, sum(eb) eb, sum(ob) ob FROM c WHERE daytype='weekday' GROUP BY ALL)
  GROUP BY ALL ORDER BY 1,2) TO '{out}/system_year_hour.csv' (HEADER)""")
# ranked lines: first 12 usable months against the latest 12, all hours 05-24, all day types
con.execute(f"""COPY (WITH x AS (SELECT *, CASE WHEN month IN ({','.join(repr(m) for m in first12)}) THEN 'f'
      WHEN month IN ({','.join(repr(m) for m in last12)}) THEN 'l' END per FROM c),
  g AS (SELECT route, per, sum(awt*eb)/sum(eb) - sum(swt*eb)/sum(eb) ewt, sum(eb) eb, avg(CAST(lowfreq AS INT)) lf,
      count(DISTINCT month) AS months FROM x WHERE per IS NOT NULL GROUP BY ALL)
  SELECT l.route, round(f.ewt,2) ewt_first12, round(l.ewt,2) ewt_last12, round(l.ewt - f.ewt,2) change, l.eb sched_departures_last12,
    round(l.lf,2) lowfreq_share_last12, f.months months_first, l.months months_last
  FROM g l LEFT JOIN g f ON f.route=l.route AND f.per='f' WHERE l.per='l' ORDER BY l.eb DESC) TO '{out}/rank.csv' (HEADER)""")
open(f"{out}/periods.txt", "w").write(f"first12 {first12[0]}..{first12[-1]}\nlast12 {last12[0]}..{last12[-1]}\n")

# intake: service delivered and headway adherence against the Controller's scorecard (DataSF kc49-udxn)
con.execute(f"""CREATE TABLE rt AS SELECT regexp_extract(filename, '(\\d{{4}}-\\d{{2}})-route', 1) AS month, *
  FROM read_csv('{diag}/*-route.csv', header=true, filename=true, union_by_name=true)""")
def sc(f):
    rows = json.load(open(os.path.join(scd, f)))
    return {r["calendar_month"][:7]: float(r["actual"]) for r in rows if r.get("actual") not in (None, "-9999")}
sd, ha = sc("sc-Percentage_of_scheduled_service_hours_delivered.json"), sc("sc-Headway_adherence.json")
con.execute("CREATE TABLE scsd(month VARCHAR, published DOUBLE)"); con.executemany("INSERT INTO scsd VALUES (?,?)", list(sd.items()))
con.execute("CREATE TABLE scha(month VARCHAR, published DOUBLE)"); con.executemany("INSERT INTO scha VALUES (?,?)", list(ha.items()))
con.execute(f"""COPY (SELECT month, round(sum(obs_hrs)/sum(sched_hrs),4) ours_any_obs, round(sum(obs_hrs_half)/sum(sched_hrs),4) ours_half_stops,
    round(sum(obs_hrs_x)/sum(sched_hrs_x),4) ours_no_outage_days, max(outage_days) outage_days,
    round(sum(obs_trips)/sum(sched_trips),4) ours_trips, round(sum(obs_trips_x)/sum(sched_trips_x),4) ours_trips_no_outage_days,
    round(sum(obs_trips_x)/sum(sched_trips_x) - s.published,4) diff_trips_no_outage_days,
    s.published, round(sum(obs_hrs)/sum(sched_hrs) - s.published,4) diff_any,
    round(sum(obs_hrs_x)/sum(sched_hrs_x) - s.published,4) diff_no_outage_days
  FROM rt LEFT JOIN scsd s USING (month) WHERE month <> '2019-09' GROUP BY month, s.published ORDER BY 1) TO '{out}/intake_service_delivered.csv' (HEADER)""")
# Owl lines and owl hours out; Connector lines: SFMTA's category list wasn't found, so two proxies are shown
OWL = "('90','91','L-OWL','N-OWL','LOWL','NOWL','714')"
CABLE = "('C','CA','PH','PM')"
con.execute(f"""COPY (SELECT month,
    round(sum(ha_ok_day)/sum(ha_n_day),4) ours_all_routes,
    round(sum(ha_ok_day) FILTER (WHERE route NOT IN {OWL}) / sum(ha_n_day) FILTER (WHERE route NOT IN {OWL}),4) ours_no_owl,
    round(sum(ha_ok_day) FILTER (WHERE route NOT IN {OWL} AND route NOT IN {CABLE}) / sum(ha_n_day) FILTER (WHERE route NOT IN {OWL} AND route NOT IN {CABLE}),4) ours_no_owl_cable,
    round(sum(ha_ok_day) FILTER (WHERE route IN (SELECT route FROM freq WHERE freq.month=rt.month)) /
          sum(ha_n_day) FILTER (WHERE route IN (SELECT route FROM freq WHERE freq.month=rt.month)),4) ours_10min_lines,
    s.published
  FROM rt LEFT JOIN scha s USING (month) WHERE month <> '2019-09' GROUP BY month, s.published ORDER BY 1) TO '{out}/intake_headway_adherence.csv' (HEADER)""".replace(
    "FROM rt LEFT JOIN scha", "FROM rt LEFT JOIN scha").replace("COPY (SELECT month,", "COPY (WITH freq AS (SELECT route, month FROM c WHERE daytype='weekday' AND hr BETWEEN 10 AND 15 GROUP BY 1,2 HAVING sum(swt*eb)/sum(eb) <= 5.0) SELECT month,", 1))
for f in ("line_year", "system_year", "system_month", "intake_service_delivered", "intake_headway_adherence"):
    print("==", f); print(con.sql(f"SELECT * FROM read_csv('{out}/{f}.csv') LIMIT 80"))
