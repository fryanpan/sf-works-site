"""Pre-pandemic baseline: hourly excess wait (TfL QSI method) for every Muni line, September 2019, in the same
hour-block schema as ewt_month.py, so ewt_aggregate.py treats it as month 2019-09.

Inputs differ from the 511 months, and the differences matter when comparing:
  observed  OpenTransit's public stop-arrivals archive (opentransit-stop-arrivals S3 bucket, v4, sf-muni), which
            infers a stop arrival time 't' from NextBus GPS positions. One file per route per service day
            (03:00 to 03:00 Pacific). The archive holds 2019-06 to 2019-10-02 only; September 2019 is the last full
            month. Arrival 't' is used (the 511 months use departure, which equals arrival on every 511 row checked).
            There is no trip id, so the 511 cleaning rules 1 to 3 (first stop, duplicate visit, out of order)
            can't run as written. Rule 1 is approximated by dropping every stop that is the first stop of any
            scheduled trip on that route; rules 4 and 5 (line-day and feed outages) run as in ewt_month.py, with
            line-day coverage measured as observed arrivals over scheduled departures at the matched stops.
  scheduled Muni's GTFS of 2019-10-09 (~/muni-ewt/g20191009.zip), whose service period runs 2019-08-26 to
            2019-10-11, so it covers every September date. Direction from trips.txt.
Two dates are left out ('schedule_anomaly'): 2019-09-02, Labor Day, which the GTFS schedules as a normal weekday
(observed/scheduled 0.70 against about 0.90 on other weekdays), and Saturday 2019-09-07, on which calendar_dates.txt
adds the Sunday service on top of the Saturday one (observed/scheduled 0.45).
Stops are matched by id (OpenTransit stop ids are Muni GTFS stop_ids); only stops present on both sides are kept,
and headways on both sides are taken per route and stop, ignoring direction: OpenTransit splits a direction into
branch variants (e.g. '1____I_F00'), which would wrongly split one stop's headways; a stop almost always serves one
direction of a route (diag 'stop_dirs_multi' counts the exceptions).
Service breaks as in ewt_month.py: a scheduled gap over 60 minutes at a route and stop starts a new service period
with no headway on either side. With no scheduled time on an OpenTransit arrival, an observed bus takes the period of
the latest scheduled departure at or before its observed time.
Usage (on the VM): PYTHONPATH=pylib python3 ewt_2019.py <outdir>     (downloads to ~/muni-511/ot2019/, cached)
"""
import os, sys, io, csv, json, gzip, zipfile, datetime as dt, urllib.request, collections, duckdb

outdir = sys.argv[1]
CACHE = os.path.expanduser("~/muni-511/ot2019"); os.makedirs(CACHE, exist_ok=True)
Z = zipfile.ZipFile(os.path.expanduser("~/muni-ewt/g20191009.zip"))
rd = lambda n: csv.DictReader(io.TextIOWrapper(Z.open(n), "utf-8-sig"))
B = "https://opentransit-stop-arrivals.s3.amazonaws.com/v4/sf-muni/2019/09/{d:02d}/arrivals_v4_sf-muni_2019-09-{d:02d}_{r}.json.gz"
PT = dt.timezone(dt.timedelta(hours=-7))  # September 2019 is PDT

routes = {r["route_id"]: r["route_short_name"] for r in rd("routes.txt")}
cal = list(rd("calendar.txt")); cdx = list(rd("calendar_dates.txt"))
days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
def services(date):
    s = date.strftime("%Y%m%d")
    out = {c["service_id"] for c in cal if c["start_date"] <= s <= c["end_date"] and c[days[date.weekday()]] == "1"}
    for x in cdx:
        if x["date"] == s: (out.add if x["exception_type"] == "1" else out.discard)(x["service_id"])
    return out
trips = {t["trip_id"]: (routes[t["route_id"]], t.get("direction_id") or "0", t["service_id"]) for t in rd("trips.txt")}
first = set(); sched_by_trip = collections.defaultdict(list)
for r in rd("stop_times.txt"):
    t = trips.get(r["trip_id"])
    if not t: continue
    hh, mm, ss = map(int, (r["departure_time"] or r["arrival_time"]).split(":"))
    sched_by_trip[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"], hh * 3600 + mm * 60 + ss))
for tid, v in sched_by_trip.items():
    first.add((trips[tid][0], min(v)[1]))

srows, orows = [], []
for d in range(1, 31):
    date = dt.date(2019, 9, d); sd = date.strftime("%Y%m%d"); sv = services(date)
    for tid, v in sched_by_trip.items():
        rt, di, s = trips[tid]
        if s in sv:
            srows += [(rt, di, stop, sd, t) for _, stop, t in v if (rt, stop) not in first]
    midnight = dt.datetime(2019, 9, d, tzinfo=PT).timestamp()
    for rt in sorted(set(routes.values())):
        f = os.path.join(CACHE, f"{sd}_{rt}.json.gz")
        if not os.path.exists(f):
            try:
                with urllib.request.urlopen(B.format(d=d, r=rt), timeout=60) as u: b = u.read()
            except Exception:
                b = b""
            open(f, "wb").write(b)
        if os.path.getsize(f) == 0: continue
        j = json.load(io.TextIOWrapper(gzip.open(f), "utf-8"))
        for stop, sdict in j.get("stops", {}).items():
            if (rt, stop) in first: continue
            for di, arr in sdict.get("arrivals", {}).items():
                orows += [(rt, di, stop, sd, int(a["t"] - midnight)) for a in arr]
    print(sd, len(srows), len(orows), flush=True)

con = duckdb.connect(); con.execute("SET threads=4; SET memory_limit='16GB'")
con.execute("CREATE TABLE sch(route VARCHAR, dir VARCHAR, stop VARCHAR, sdate VARCHAR, t INT)")
con.execute("CREATE TABLE ob0(route VARCHAR, dir VARCHAR, stop VARCHAR, sdate VARCHAR, t INT)")
for name, rows in (("sch", srows), ("ob0", orows)):
    tmp = os.path.join(CACHE, f"_{name}.csv")
    with open(tmp, "w", newline="") as f: csv.writer(f).writerows(rows)
    con.execute(f"INSERT INTO {name} SELECT * FROM read_csv('{tmp}', header=false, columns={{'route':'VARCHAR','dir':'VARCHAR','stop':'VARCHAR','sdate':'VARCHAR','t':'INT'}})")
    os.remove(tmp)
diag = {"month": "2019-09", "sched_rows": len(srows), "obs_rows": len(orows)}
# keep stops on both sides, per route
con.execute("""CREATE TABLE both_ AS SELECT DISTINCT route, stop FROM sch INTERSECT SELECT DISTINCT route, stop FROM ob0""")
con.execute("CREATE TABLE obs AS SELECT o.* FROM ob0 o JOIN both_ USING (route, stop)")
con.execute("CREATE TABLE sch2 AS SELECT s.* FROM sch s JOIN both_ USING (route, stop)")
diag["obs_rows_matched_stops"] = con.execute("SELECT count(*) FROM obs").fetchone()[0]
diag["sched_rows_matched_stops"] = con.execute("SELECT count(*) FROM sch2").fetchone()[0]
con.execute("""CREATE TABLE dt AS WITH c AS (SELECT sdate, count(*) n, dayofweek(strptime(sdate,'%Y%m%d')) w FROM sch GROUP BY 1),
  k AS (SELECT *, CASE WHEN w=0 THEN 'sunday' WHEN w=6 THEN 'saturday' ELSE 'weekday' END k0 FROM c),
  m AS (SELECT k0, median(n) mn FROM k GROUP BY 1)
  SELECT sdate, CASE WHEN k0<>'sunday' AND n < 0.9*mn THEN 'sunday' ELSE k0 END daytype FROM k JOIN m USING (k0)""")
con.execute("""CREATE TABLE cov AS SELECT s.route, s.sdate, s.n nsch, coalesce(o.n,0) nobs FROM
  (SELECT route, sdate, count(*) n FROM sch2 GROUP BY 1,2) s LEFT JOIN (SELECT route, sdate, count(*) n FROM obs GROUP BY 1,2) o USING (route, sdate)""")
diag["line_days_dropped"] = con.execute("SELECT count(*) FROM cov WHERE nobs < 0.5*nsch").fetchone()[0]
con.execute("CREATE TABLE binc AS SELECT sdate, t//600 b, count(*) n FROM ob0 GROUP BY 1,2")
con.execute("""CREATE TABLE outage AS WITH g AS (SELECT DISTINCT d.sdate, d.daytype, b FROM dt d, range(30,144) r(b)),
  x AS (SELECT g.*, coalesce(c.n,0) n FROM g LEFT JOIN binc c USING (sdate, b)),
  m AS (SELECT daytype, b, median(n) mn FROM x GROUP BY 1,2) SELECT sdate, b FROM x JOIN m USING (daytype, b) WHERE n < 0.5*mn""")
diag["outage_bins"] = con.execute("SELECT sdate, min(b), max(b), count(*) FROM outage GROUP BY 1 ORDER BY 1").fetchall()
con.execute("CREATE TABLE outh AS SELECT DISTINCT sdate, hr FROM outage, range(0,36) r(hr) WHERE b*600 >= hr*3600-1800 AND b*600 < (hr+1)*3600")
BREAK = 3600
con.execute(f"""CREATE TABLE schp AS SELECT route, dir, stop, sdate, t,
    sum(CASE WHEN pt IS NULL OR t - pt > {BREAK} THEN 1 ELSE 0 END) OVER (PARTITION BY route, stop, sdate ORDER BY t ROWS UNBOUNDED PRECEDING) per
  FROM (SELECT *, lag(t) OVER (PARTITION BY route, stop, sdate ORDER BY t) pt FROM sch2)""")
con.execute("""CREATE TABLE obsp AS SELECT o.*, coalesce(p.per, 1) per FROM obs o ASOF LEFT JOIN
  (SELECT route, stop, sdate, t, max(per) per FROM schp GROUP BY ALL) p ON o.route = p.route AND o.stop = p.stop AND o.sdate = p.sdate AND o.t >= p.t""")
def blocks(tbl, p):
    return f"""SELECT route, dir, stop, sdate, t//3600 hr, count(*) {p}b,
      sum(h*h) FILTER (WHERE h IS NOT NULL) {p}h2, sum(h) FILTER (WHERE h IS NOT NULL) {p}h
      FROM (SELECT route, dir, stop, sdate, t, CAST(t - lag(t) OVER (PARTITION BY route, stop, sdate, per ORDER BY t) AS DOUBLE) h FROM {tbl})
      GROUP BY 1,2,3,4,5"""
con.execute(f"CREATE TABLE bs AS {blocks('schp', 's')}")
con.execute(f"CREATE TABLE bo AS {blocks('obsp', 'o')}")
os.makedirs(f"{outdir}/hourly", exist_ok=True); os.makedirs(f"{outdir}/diag", exist_ok=True)
con.execute(f"""COPY (SELECT route, coalesce(s.dir, o.dir) dir, stop, sdate, hr, dt.daytype, coalesce(sb,0) eb, coalesce(ob,0) ob,
    sh2 ssh2, sh ssh, oh2 soh2, oh soh, CASE WHEN sh>0 THEN sh2/(2*sh)/60 END hswt, CASE WHEN oh>0 THEN oh2/(2*oh)/60 END hawt,
    CASE WHEN sdate IN ('20190902','20190907') THEN 'schedule_anomaly'
      WHEN c.nobs < 0.5*c.nsch OR c.nsch IS NULL THEN 'line_day_outage' WHEN x.hr IS NOT NULL THEN 'feed_outage' END excl,
    round(c.nobs/c.nsch, 3) linecov
  FROM (SELECT route, stop, sdate, hr, any_value(dir) dir, sum(sb) sb, sum(sh2) sh2, sum(sh) sh FROM bs GROUP BY 1,2,3,4) s
  FULL JOIN (SELECT route, stop, sdate, hr, any_value(dir) dir, sum(ob) ob, sum(oh2) oh2, sum(oh) oh FROM bo GROUP BY 1,2,3,4) o
    USING (route, stop, sdate, hr)
  JOIN dt USING (sdate) LEFT JOIN cov c USING (route, sdate) LEFT JOIN outh x USING (sdate, hr)
  ORDER BY route, stop, sdate, hr) TO '{outdir}/hourly/2019-09.parquet' (FORMAT parquet, COMPRESSION zstd)""")
diag["stop_dirs_multi"] = con.execute("""SELECT count(*) FROM (SELECT route, stop FROM sch2 GROUP BY 1,2 HAVING count(DISTINCT dir) > 1)""").fetchone()[0]
diag["routes_sched"] = con.execute("SELECT count(DISTINCT route) FROM sch").fetchone()[0]
diag["routes_obs"] = con.execute("SELECT count(DISTINCT route) FROM ob0").fetchone()[0]
diag["routes_both"] = con.execute("SELECT count(DISTINCT route) FROM both_").fetchone()[0]
json.dump(diag, open(f"{outdir}/diag/2019-09.json", "w"), indent=1, default=str)
print(json.dumps(diag, default=str))
