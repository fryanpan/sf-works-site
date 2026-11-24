"""Each Muni line's measured miles and hours by month, from trip_time.py's seg/*.parquet, for the spread across lines on the citywide speed chart.

Same scope as trip_analyze.py: hours 05:00 to 22:59, the L's bus substitute kept apart, owl codes renamed. Writes
<out.csv>: route, month, miles, obs_hr, sch_hr. --by-hour adds hr, the clock hour of each stretch's scheduled start
(trip_time.py's seg hr), for each line's speed by hour of day in every period of the Lines page (site_data.py pools
the months of a period as miles over hours). All day types, as the line pages' speed.
Usage (on the VM): python3 speed_line_month.py <ewt dir> <out.csv> [--by-hour]
"""
import sys, duckdb
ewt, out = sys.argv[1:3]
HR = ", hr" if "--by-hour" in sys.argv else ""
REN = "CASE route WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' ELSE route END"
duckdb.connect().execute(f"""COPY (SELECT {REN} route, substr(sdate,1,4)||'-'||substr(sdate,5,2) AS month{HR}, round(sum(dist), 2) miles,
  round(sum(obs_s)/3600, 3) obs_hr, round(sum(sch_s)/3600, 3) sch_hr FROM read_parquet('{ewt}/seg/20*.parquet')
  WHERE hr BETWEEN 5 AND 22 GROUP BY ALL ORDER BY ALL) TO '{out}' (HEADER)""")
print("wrote", out)
