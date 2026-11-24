"""Excess wait at each stop of each frequent Muni line by clock hour, for one month: ewt_stops.py split by hour.

For the line pages' heat maps of excess wait by hour of day and tenth of the route (Bryan, 2026-11-17, on the
38R: "Perhaps it's better if we have an inbound and outbound by time and along route heat map").
The blocks kept and dropped, and the weights, are ewt_stops.py's exactly: frequent lines by SFMTA's line types
(freq_rule.py), hours 05:00 to 22:59, the excl set, service-date hours where Muni's observed departures are under half
its scheduled ones, blocks whose actual wait runs more than 30 minutes over the scheduled wait, and blocks with no
scheduled wait (hswt null), which would count scheduled departures toward swt's weight with nothing behind them. At a stop-hour,
scheduled wait is weighted by scheduled departures and actual wait by observed departures (TfL's Step I). Summed over
hours, eb, ob and blocks equal ewt_stops.py's row for the stop, which the check below asserts when that file is given.

Input: one month's hourly/<YYYY-MM>.parquet (ewt_month.py). Output: gzipped CSV, one row per route, direction, stop and
hour: eb, ob (scheduled and observed departures), swt, awt (minutes) and blocks (stop-hours, here service dates).
Runs on the VM after ewt_month.py (post_all.sh); reads no network.
Usage: python3 ewt_stop_hours.py <hourly YYYY-MM.parquet> <out.csv.gz> [stops YYYY-MM.csv to check against]
"""
import sys, duckdb
from freq_rule import frequent_sql  # the one frequent-service rule (freq_rule.py)

src, out = sys.argv[1:3]
check = sys.argv[3] if len(sys.argv) > 3 else None
con = duckdb.connect()
AW = "sum(hawt*ob) FILTER (WHERE hawt IS NOT NULL)/nullif(sum(ob) FILTER (WHERE hawt IS NOT NULL), 0)"
con.execute(f"""COPY (
WITH a0 AS (SELECT * FROM read_parquet('{src}') WHERE hr BETWEEN 5 AND 22),
dh AS (SELECT sdate, hr FROM a0 GROUP BY 1,2 HAVING sum(ob) < 0.5*sum(eb)),
b AS (SELECT * FROM a0 WHERE excl IS NULL AND {frequent_sql()}
        AND hswt IS NOT NULL AND NOT coalesce(hawt - hswt > 30, false)
        AND NOT EXISTS (SELECT 1 FROM dh WHERE dh.sdate = a0.sdate AND dh.hr = a0.hr))
SELECT CASE route WHEN 'LBUS' THEN 'L' WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE route END route, dir, stop, hr,
  sum(eb) eb, sum(ob) ob, round(sum(hswt*eb)/sum(eb), 3) swt, round({AW}, 3) awt, count(*) blocks
FROM b GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4) TO '{out}' (HEADER, COMPRESSION gzip)""")
n = con.execute(f"SELECT count(*), count(DISTINCT route) FROM read_csv('{out}', header=true)").fetchone()
if check:
    bad = con.execute(f"""SELECT count(*) FROM (SELECT route, dir, stop, sum(eb) eb, sum(ob) ob, sum(blocks) blocks
        FROM read_csv('{out}', header=true) GROUP BY 1, 2, 3) h FULL JOIN read_csv('{check}', header=true) s
        USING (route, dir, stop) WHERE h.eb IS DISTINCT FROM s.eb OR h.ob IS DISTINCT FROM s.ob OR h.blocks IS DISTINCT FROM s.blocks""").fetchone()[0]
    if bad:
        sys.exit(f"{out}: {bad} route-stops whose hours don't add up to {check}")
print(f"wrote {out}: {n[0]} route-stop-hours on {n[1]} lines{', hours add up to ' + check if check else ''}")
