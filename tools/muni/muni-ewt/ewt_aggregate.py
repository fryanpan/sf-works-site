"""Aggregate the hourly excess-wait blocks from ewt_month.py to line x month x day type x clock hour, TfL's way.

TfL "iBus Data Aggregation for QSIs" v2.1, section 2.12:
  Step I   for one route and one hour, combine stops (QSI points, both directions): hSWT weighted by scheduled
           departures ("Expected Buses", eb), hAWT by observed departures ("Observed Buses", ob), section 2.3;
  Step II  combine hours, weighting by passenger journeys. Muni publishes no boardings by line and hour that we
           have, so each service-date hour gets equal weight: within a line x month x day type x hour cell this is
           the plain mean over dates. The cell carries n_swt / n_awt (date-hours) so later steps can re-weight.
  Step III (in ewt_analyze.py) combine routes, SWT by eb and AWT by ob, as at Step I (section 2.12.3).
EWT = aggregated AWT - aggregated SWT (TfL example 1, 3.2.3).
Decomposition: htswt (ewt_month.py) is the scheduled wait of the buses that were tracked, from their own scheduled
times. It is carried twice: tswt_eb weighted like SWT and tswt_ob weighted like AWT. Then, with every step's weights
matched on each side,
  missing   = tswt_eb - swt     timetabled buses absent from the feed (missed or untracked), SWT's weights
  spacing   = awt - tswt_ob     tracked buses unevenly spaced, AWT's weights
  weighting = tswt_ob - tswt_eb what TfL's observed-bus weights for AWT do on their own: a stop or line that lost
                                buses counts for less, so this is usually negative
and the three add up to EWT. --eb weights AWT and tswt by eb at every step (the scheduled-bus sensitivity check);
weighting is then zero.
Blocks with excl set are left out on both sides, and so is every block in a service-date hour where all of Muni's
observed departures are under half its scheduled ones: a feed outage measured against the schedule, which still
works when a whole month is thin (from 2024-11-09 the feed carries about a seventh of its usual rows, so
ewt_month.py's rule, measured against the month's own median, can't see it). A stop-hour block whose actual wait
exceeds its scheduled wait by more than 30 minutes is also left out on both sides: a stop the line's buses skipped for
hours (a diversion, or a stop pattern the feed doesn't match) leaves one observed gap of several hours that no
timetable explains. TfL likewise ignores stops near a curtailment (Aggregation 2.2). These blocks hold 0.03% to 0.05%
of observed buses a year from 2023 (0.11% in 2022); dropping them lowers the yearly citywide figure by 0.03
to 0.04 minute from 2023 and 0.08 in 2022 (summary_noguard against summary, TfL weights). --no-guard keeps them, for the sensitivity check.
lowfreq: mean scheduled departures per stop-direction hour block in the cell under 5, TfL's high-frequency line
(QSI Statistics Explained 1.6); TfL would score those hours on punctuality instead.
--frequent keeps only the blocks of frequent lines: every line but SFMTA's Connector and Owl lines (freq_rule.py;
Bryan, 2026-11-17, "SFMTA's line types"). This is the switch ewt_stops.py, ewt_daily.py and ontime_month.py make, so the site's
excess-wait figures (site_data.py, from extract_freq.csv) and its stop, trend, map and on-time files share one rule.
Its eb_per_block and lowfreq describe the kept blocks only.
Output: CSV with one row per route, month, daytype, hr, and <out>_months.csv with each month's kept share.
Usage: PYTHONPATH=pylib python3 ewt_aggregate.py <ewt dir> <out.csv> [min line-day coverage, e.g. 0.95] [--no-guard] [--eb] [--frequent]
"""
import sys, os, glob, json, duckdb
from freq_rule import frequent_sql  # the one frequent-service rule (freq_rule.py)
args = [x for x in sys.argv[1:] if not x.startswith("--")]
d, out = args[0], args[1]
mincov = float(args[2]) if len(args) > 2 else 0  # optional: keep only line-days with linecov >= this
GUARD = "" if "--no-guard" in sys.argv else "AND NOT coalesce(hawt - hswt > 30, false)"  # see docstring
W = "eb" if "--eb" in sys.argv else "ob"  # AWT's weight at Step I (TfL: ob)
FREQ = f"AND {frequent_sql()}" if "--frequent" in sys.argv else ""  # see docstring: frequent lines only, by SFMTA's line types
con = duckdb.connect(); con.execute("SET threads=6; SET memory_limit='24GB'")
con.execute(f"""COPY (
WITH a0 AS (SELECT * FROM read_parquet('{d}/hourly/*.parquet', union_by_name=true)),
dh AS (SELECT sdate, hr FROM a0 GROUP BY 1,2 HAVING sum(ob) < 0.5*sum(eb)),
b AS (SELECT route, sdate, substr(sdate,1,4)||'-'||substr(sdate,5,2) AS month, daytype, hr, eb, ob, hswt, hawt, htswt
           FROM a0 WHERE excl IS NULL AND coalesce(linecov, 1) >= {mincov} {GUARD} {FREQ}
             AND NOT EXISTS (SELECT 1 FROM dh WHERE dh.sdate = a0.sdate AND dh.hr = a0.hr)),
s1 AS (SELECT route, month, daytype, hr, sdate,
         sum(hswt*eb) FILTER (WHERE hswt IS NOT NULL) / nullif(sum(eb) FILTER (WHERE hswt IS NOT NULL),0) swt,
         sum(hawt*{W}) FILTER (WHERE hawt IS NOT NULL) / nullif(sum({W}) FILTER (WHERE hawt IS NOT NULL),0) awt,
         sum(htswt*eb) FILTER (WHERE htswt IS NOT NULL) / nullif(sum(eb) FILTER (WHERE htswt IS NOT NULL),0) tswt_eb,
         sum(htswt*{W}) FILTER (WHERE htswt IS NOT NULL) / nullif(sum({W}) FILTER (WHERE htswt IS NOT NULL),0) tswt_ob,
         sum(eb) eb, sum(ob) ob, count(*) FILTER (WHERE eb > 0) nblk_s
       FROM b GROUP BY ALL)
SELECT route, month, daytype, hr, count(DISTINCT sdate) dates, count(swt) n_swt, count(awt) n_awt,
  round(avg(swt),4) swt, round(avg(awt),4) awt, round(avg(awt)-avg(swt),4) ewt, round(avg(tswt_eb),4) tswt_eb, round(avg(tswt_ob),4) tswt_ob, count(tswt_ob) n_tswt,
  sum(eb) eb, sum(ob) ob, round(sum(eb)/nullif(sum(nblk_s),0),2) eb_per_block,
  sum(eb)/nullif(sum(nblk_s),0) < 5 lowfreq
FROM s1 GROUP BY ALL ORDER BY route, month, daytype, hr) TO '{out}' (HEADER)""")
# per month: share of scheduled departures 05:00-23:00 (the hours ewt_analyze.py counts) that sit in blocks kept above
con.execute(f"""COPY (WITH a0 AS (SELECT *, substr(sdate,1,4)||'-'||substr(sdate,5,2) AS month FROM read_parquet('{d}/hourly/*.parquet', union_by_name=true) WHERE hr BETWEEN 5 AND 22),
  dh AS (SELECT sdate, hr FROM a0 GROUP BY 1,2 HAVING sum(ob) < 0.5*sum(eb))
  SELECT month, round(sum(eb) FILTER (WHERE excl IS NULL AND NOT EXISTS (SELECT 1 FROM dh WHERE dh.sdate=a0.sdate AND dh.hr=a0.hr)) / sum(eb), 4) kept_share,
    count(DISTINCT (sdate, hr)) FILTER (WHERE EXISTS (SELECT 1 FROM dh WHERE dh.sdate=a0.sdate AND dh.hr=a0.hr)) thin_date_hours,
    round(sum(ob)/sum(eb),4) obs_over_sched_raw
  FROM a0 GROUP BY 1 ORDER BY 1) TO '{out[:-4]}_months.csv' (HEADER)""")
# standing checks from each month's diag: share of rows the out-of-order rule drops (flagged above 2%) and the share
# of tracked buses' scheduled times that match the timetable used within 60 s (flagged below 90%, except on stand-in
# months, where ewt_month.py substitutes the timetable's times)
chk = {}
for f in sorted(glob.glob(f"{d}/diag/*.json")):
    j = json.load(open(f)); m = os.path.basename(f)[:7]
    # on a stand-in month 511's own times are replaced by the timetable's, so the match there is reported, not flagged
    chk[m] = (j.get("out_of_order_share"), None if "standin_times_substituted" in j else (j.get("sched_time_match") or {}).get("within_60s"))
rows = open(f"{out[:-4]}_months.csv").read().splitlines()
with open(f"{out[:-4]}_months.csv", "w") as fh:
    fh.write(rows[0] + ",out_of_order_share,sched_within_60s,check\n")
    for r in rows[1:]:
        m = r.split(",")[0]; oo, sm = chk.get(m, (None, None))
        flag = ";".join(x for x in ("out_of_order" if oo is not None and oo > 0.02 else "", "sched_match" if sm is not None and sm < 0.9 else "") if x)
        if flag: print("CHECK", m, flag, oo, sm)
        fh.write(f"{r},{'' if oo is None else oo},{'' if sm is None else sm},{flag or 'ok'}\n")
print(con.execute(f"SELECT count(*), count(DISTINCT route), min(month), max(month) FROM read_csv('{out}')").fetchone())
