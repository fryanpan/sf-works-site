"""Each Muni line's excess wait (frequent hours) and speed for each service date of one month, from the VM's Parquet.

Inputs: one month's hourly/<YYYY-MM>.parquet (ewt_month.py), seg/<YYYY-MM>.parquet and trip/<YYYY-MM>.parquet
(trip_time.py; the trip file is found beside seg/).
Output: CSV, one row per route and service date: eb, ob (scheduled and observed departures in frequent hours),
eba (the scheduled departures in the hours where a bus was seen, the weight awt carries when rows are pooled),
swt, awt and ewt (minutes), and miles, obs_hr, sch_hr (the measured stretches between timepoints, 05:00 to 22:59).
Excess wait uses the blocks ewt_stops.py uses (frequent lines only, every line but Connector and Owl,
freq_rule.py, ewt_aggregate.py --frequent; the same
outage, thin-hour and skipped-stop rules), pooled the way the overview pools them (ewt_aggregate.py, site_data.py):
within each clock hour across the line's stops, scheduled wait by scheduled departures and actual wait by observed
departures (TfL Step I); then across hours, both by scheduled departures (Step II). A stop-hour where no bus was seen
stays in, with its scheduled wait and departures, as it does in extract_freq.csv; it adds no actual wait. Pooling
observed departures across hours instead let the hours that lost buses, which wait longest, count least, and put
every line's figure 0.1 minute under the overview's (Fable review, 2026-11-10).
A date with no frequent hours, or no measured stretch, leaves those fields blank.
Spread (Bryan, 2026-11-09: the median and the 10th to 90th percentile on every trend chart): ewt_p10/p50/p90 are
percentiles across the line's stops (each stop-direction's excess wait over the row's hours, weighted by its
scheduled departures, as the line figure is); mph_p10/p50/p90 are percentiles across the row's trips (each trip's
measured miles over its observed time, trips with a measured stretch of at least 0.5 mile).
--by-hour adds the clock hour to the key (one row per route, service date and hour), and --by-6h the 6-hour block
of the service day (hours 5-10, 11-16, 17-22, keyed by its first hour), both for the newest three months only. The
blocks start at 5 am, when the hours counted start, so each holds six hours; clock-aligned blocks (0-5, 6-11, ...)
left the first block of every day holding the 5 am hour alone, a jagged point every fourth step on the 90-day chart.
Causes (ewt_aggregate.py's split, pooled the same way as the line's figure): mis, the scheduled wait of the tracked
buses (htswt) minus the scheduled wait, the timetabled buses absent from the feed; wgt, htswt weighted by observed
minus by scheduled departures; spacing is ewt - mis - wgt. Both cover the hours that carry htswt.
--by-week keys rows by the week's Monday (sdate holds that Monday), run once over every month with globs.
Usage: python3 ewt_daily.py <hourly YYYY-MM.parquet> <seg YYYY-MM.parquet> <out.csv> [--by-hour | --by-6h | --by-week]
"""
import sys, duckdb
from freq_rule import frequent_sql  # the one frequent-service rule (freq_rule.py)

import os
hourly, seg, out = [a for a in sys.argv[1:] if not a.startswith("--")][:3]
trip = os.path.join(os.path.dirname(os.path.dirname(seg)), "trip", os.path.basename(seg))
# --by-week keys each row by the Monday that starts its week, so a week isn't split at a month's end: run it once over
# every month, with globs for <hourly> and <seg>.
WEEK = "--by-week" in sys.argv
WK = "strftime(date_trunc('week', strptime(CAST(sdate AS VARCHAR), '%Y%m%d')), '%Y%m%d')"
SD = f"{WK} AS sdate" if WEEK else "sdate"
K = ", hr" if ("--by-hour" in sys.argv or "--by-6h" in sys.argv) else ""
SEL = ", ((hr - 5) // 6) * 6 + 5 AS hr" if "--by-6h" in sys.argv else K
con = duckdb.connect()
REN = "CASE route WHEN 'LBUS' THEN 'L' WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE route END"
con.execute(f"""COPY (
WITH a0 AS (SELECT * FROM read_parquet('{hourly}') WHERE hr BETWEEN 5 AND 22),
dh AS (SELECT sdate, hr FROM a0 GROUP BY 1,2 HAVING sum(ob) < 0.5*sum(eb)),
b0 AS (SELECT * FROM a0 WHERE excl IS NULL AND {frequent_sql()}
        AND NOT coalesce(hawt - hswt > 30, false)
        AND NOT EXISTS (SELECT 1 FROM dh WHERE dh.sdate = a0.sdate AND dh.hr = a0.hr)),
b AS (SELECT * REPLACE ({SD.replace(' AS sdate', '') if WEEK else 'sdate'} AS sdate) FROM b0),
st AS (SELECT {REN} route, sdate{SEL}, dir, stop, sum(eb) wt,
      sum(hawt*ob) FILTER (WHERE hawt IS NOT NULL)/nullif(sum(ob) FILTER (WHERE hawt IS NOT NULL), 0) - sum(hswt*eb)/sum(eb) e
      FROM b GROUP BY ALL),
stq AS (SELECT *, sum(wt) OVER (PARTITION BY route, sdate{K} ORDER BY e ROWS UNBOUNDED PRECEDING) cw,
      sum(wt) OVER (PARTITION BY route, sdate{K}) tw FROM st WHERE e IS NOT NULL),
sp AS (SELECT route, sdate{K}, min(e) FILTER (WHERE cw >= 0.1*tw) ewt_p10, min(e) FILTER (WHERE cw >= 0.5*tw) ewt_p50,
      min(e) FILTER (WHERE cw >= 0.9*tw) ewt_p90 FROM stq GROUP BY ALL),
tr AS (SELECT {REN} route, sdate{SEL}, quantile_cont(dist/obs_s*3600, 0.1) mph_p10, quantile_cont(dist/obs_s*3600, 0.5) mph_p50,
      quantile_cont(dist/obs_s*3600, 0.9) mph_p90 FROM (SELECT * REPLACE ({SD.replace(' AS sdate', '') if WEEK else 'sdate'} AS sdate) FROM read_parquet('{trip}')) WHERE hr BETWEEN 5 AND 22 AND dist >= 0.5 AND obs_s > 0 GROUP BY ALL),
h AS (SELECT {REN} route, sdate{SEL}, b.hr AS chr, sum(eb) eb, sum(ob) ob, sum(hswt*eb)/sum(eb) swt,
      sum(hawt*ob) FILTER (WHERE hawt IS NOT NULL)/nullif(sum(ob) FILTER (WHERE hawt IS NOT NULL), 0) awt,
      sum(htswt*eb) FILTER (WHERE htswt IS NOT NULL)/nullif(sum(eb) FILTER (WHERE htswt IS NOT NULL), 0) teb,
      sum(htswt*ob) FILTER (WHERE htswt IS NOT NULL)/nullif(sum(ob) FILTER (WHERE htswt IS NOT NULL), 0) tob
      FROM b GROUP BY ALL),
w AS (SELECT route, sdate{K}, sum(eb) eb, sum(ob) ob, sum(eb) FILTER (WHERE awt IS NOT NULL) eba, sum(swt*eb)/sum(eb) swt,
      sum(awt*eb) FILTER (WHERE awt IS NOT NULL)/nullif(sum(eb) FILTER (WHERE awt IS NOT NULL), 0) awt,
      sum((teb-swt)*eb) FILTER (WHERE tob IS NOT NULL)/nullif(sum(eb) FILTER (WHERE tob IS NOT NULL), 0) mis,
      sum((tob-teb)*eb) FILTER (WHERE tob IS NOT NULL)/nullif(sum(eb) FILTER (WHERE tob IS NOT NULL), 0) wgt
      FROM h GROUP BY ALL),
s AS (SELECT {REN} route, sdate{SEL}, sum(dist) miles, sum(obs_s)/3600 obs_hr, sum(sch_s)/3600 sch_hr
      FROM (SELECT * REPLACE ({SD.replace(' AS sdate', '') if WEEK else 'sdate'} AS sdate) FROM read_parquet('{seg}')) WHERE hr BETWEEN 5 AND 22 GROUP BY ALL)
SELECT route, sdate{K}, w.eb, w.ob, w.eba, round(w.swt, 3) swt, round(w.awt, 3) awt, round(w.awt - w.swt, 3) ewt, round(w.mis, 3) mis, round(w.wgt, 3) wgt,
  round(s.miles, 2) miles, round(s.obs_hr, 3) obs_hr, round(s.sch_hr, 3) sch_hr,
  round(sp.ewt_p10, 3) ewt_p10, round(sp.ewt_p50, 3) ewt_p50, round(sp.ewt_p90, 3) ewt_p90,
  round(tr.mph_p10, 2) mph_p10, round(tr.mph_p50, 2) mph_p50, round(tr.mph_p90, 2) mph_p90
FROM w FULL JOIN s USING (route, sdate{K}) LEFT JOIN sp USING (route, sdate{K}) LEFT JOIN tr USING (route, sdate{K}) ORDER BY ALL) TO '{out}' (HEADER)""")
n = con.execute(f"SELECT count(*), count(DISTINCT route), count(DISTINCT sdate) FROM read_csv('{out}', header=true)").fetchone()
print(f"wrote {out}: {n[0]} line-days, {n[1]} lines, {n[2]} dates")
