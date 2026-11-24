"""Excess wait at each stop of each Muni line for one month, frequent hours only, from ewt_month.py's hourly blocks.

Input: one month's hourly/<YYYY-MM>.parquet (one row per route, direction, stop, service date and clock hour).
Output: CSV, one row per route, direction and stop: eb and ob (scheduled and observed departures counted), swt and
awt (minutes), ewt = awt - swt, and blocks (stop-hours counted).

Frequent: a block counts when it is on a frequent line by SFMTA's line types, every line but Connector and Owl (freq_rule.py; Bryan, 2026-11-17); ewt_aggregate.py --frequent. The same blocks are dropped as in ewt_aggregate.py: excl set (feed or
line-day outage), service-date hours where all of Muni's observed departures are under half its scheduled ones,
blocks whose actual wait runs more than 30 minutes over the scheduled wait (a skipped stop), blocks with no
scheduled wait (hswt null: the stop's first scheduled bus of the service period, or none scheduled, which would count
scheduled departures toward swt's weight with no wait behind them; Fable pipeline review, 2026-11-17), and hours outside
05:00 to 22:59. A stop-hour where no bus was seen stays in (its scheduled wait and departures), as in extract_freq.csv. At a stop, scheduled wait is weighted by scheduled departures and actual wait by observed
departures, TfL's Step I (iBus Data Aggregation for QSIs 2.3).
Runs on the VM after ewt_month.py, or anywhere with the month's Parquet; reads no network.
Usage: python3 ewt_stops.py <hourly YYYY-MM.parquet> <out.csv>
"""
import sys, duckdb
from freq_rule import frequent_sql  # the one frequent-service rule (freq_rule.py)

src, out = sys.argv[1:3]
con = duckdb.connect()
# actual wait over the stop-hours where a bus was seen; one with none keeps its scheduled wait and departures
AW = "sum(hawt*ob) FILTER (WHERE hawt IS NOT NULL)/nullif(sum(ob) FILTER (WHERE hawt IS NOT NULL), 0)"
con.execute(f"""COPY (
WITH a0 AS (SELECT * FROM read_parquet('{src}') WHERE hr BETWEEN 5 AND 22),
dh AS (SELECT sdate, hr FROM a0 GROUP BY 1,2 HAVING sum(ob) < 0.5*sum(eb)),
b AS (SELECT * FROM a0 WHERE excl IS NULL AND {frequent_sql()}
        AND hswt IS NOT NULL AND NOT coalesce(hawt - hswt > 30, false)
        AND NOT EXISTS (SELECT 1 FROM dh WHERE dh.sdate = a0.sdate AND dh.hr = a0.hr))
SELECT CASE route WHEN 'LBUS' THEN 'L' WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE route END route, dir, stop,
  sum(eb) eb, sum(ob) ob, round(sum(hswt*eb)/sum(eb), 3) swt, round({AW}, 3) awt,
  round({AW} - sum(hswt*eb)/sum(eb), 3) ewt, count(*) blocks
FROM b GROUP BY 1, 2, 3 ORDER BY 1, 2, 3) TO '{out}' (HEADER)""")
n = con.execute(f"SELECT count(*), count(DISTINCT route) FROM read_csv('{out}', header=true)").fetchone()
print(f"wrote {out}: {n[0]} route-stops on {n[1]} lines")
