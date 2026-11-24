"""Bus speed for every Muni line in September 2019, from OpenTransit's stop arrivals, in the form trip_time.py writes.

The 2019 baseline has no trip ids and no timetable on the observation rows (ewt_2019.py explains the feed). An
OpenTransit arrival does carry a vehicle id 'v', a run index 'i' and a direction variant, and one (route, v, i,
variant, service date) is one bus trip: on the 38 on 2019-09-10 the longest such runs hold 42 stops over 42 to 50
minutes. Segments are taken between consecutive timepoints a run was observed at, in time order, both ends observed,
as in trip_time.py. Timepoint flags are any 511 month's (dist_table.py's timepoints.parquet, --tables), and
distances are stop positions on the longest trip of each route and direction in --ref, since SFMTA's 2019 GTFS
stop_times has no distances; a segment whose ends aren't both positioned, or that runs backwards, is dropped. Stops
are matched by prefixing '1' to the four-digit GTFS stop id (511's stop code). Every stop that is the first or last
stop of a scheduled trip on the route is left out (trip_time.py drops a trip's end stops), and so are the
dates, hours and line-days ewt_2019.py excluded (read from hourly/2019-09.parquet). Bounds as trip_time.py, except
that there is no scheduled time per observed segment: obs_s > 0, observed speed <= 60 mph, obs_s <= 3 hours.
Scheduled speed for 2019 comes from the GTFS itself: every scheduled trip-day's consecutive timepoints on the dates
with kept segments, same flags and distances, so it covers the whole timetable rather than the observed segments only.
This position method reads speed about 3% apart from trip_time.py's on the same 511 month (Fable review 3, item 4),
so a 2019 comparison is good to about 3% only. No excess trip time for 2019.
Output, into <ewt dir>/seg/: 2019-09.parquet (route, sdate, daytype, hr, nseg, dist, obs_s, sch_s null) and
<ewt dir>/sched-2019-09.parquet (route, daytype, hr, nseg, dist, sch_s), 2019-09.json.
Usage (on the VM): PYTHONPATH=pylib python3 trip_time_2019.py <ewt dir> --ref <extract dir> --tables <dist_table dir>
"""
import os, sys, io, csv, json, gzip, zipfile, datetime as dt, duckdb
args = sys.argv[1:]
opt = lambda k: args[args.index(k) + 1]
ewt, ref, tables = args[0], opt("--ref"), opt("--tables")
CACHE = os.path.expanduser("~/muni-511/ot2019")
Z = zipfile.ZipFile(os.path.expanduser("~/muni-ewt/g20191009.zip"))
rdz = lambda n: csv.DictReader(io.TextIOWrapper(Z.open(n), "utf-8-sig"))
PT = dt.timezone(dt.timedelta(hours=-7))
os.makedirs(f"{ewt}/seg", exist_ok=True)
con = duckdb.connect(); con.execute("SET threads=4; SET memory_limit='16GB'")
rd = lambda dd, f: f"read_csv('{dd}/{f}', header=true, all_varchar=true)"
one = lambda s: con.execute(s).fetchone()
diag = {"month": "2019-09"}

# stop positions and timepoint flags from 511 months (see trip_time.py)
con.execute(f"""CREATE TABLE rs AS SELECT s.trip_id, t.route_id, t.direction_id dir, s.stop_id stop,
  TRY_CAST(nullif(s.shape_dist_traveled,'') AS DOUBLE) dist FROM {rd(ref, 'stop_times.csv.gz')} s JOIN {rd(ref, 'trips.csv.gz')} t USING (trip_id)""")
con.execute("""CREATE TABLE pos AS WITH n AS (SELECT route_id, dir, trip_id, max(dist) len FROM rs GROUP BY ALL),
  k AS (SELECT route_id, dir, trip_id FROM n QUALIFY row_number() OVER (PARTITION BY route_id, dir ORDER BY len DESC, trip_id) = 1)
  SELECT rs.route_id, rs.stop, min(rs.dist) pos FROM rs JOIN k USING (route_id, dir, trip_id) GROUP BY ALL""")
con.execute("CREATE TABLE pos1 AS SELECT replace(route_id,'SF:','') route, stop, any_value(pos) pos FROM pos GROUP BY ALL HAVING count(*) = 1")
con.execute(f"""CREATE TABLE tpf AS SELECT replace(route_id,'SF:','') route, stop FROM read_parquet('{tables}/timepoints.parquet') WHERE tp""")

# 2019 GTFS: routes, scheduled trips by date, first stops
routes = {r["route_id"]: r["route_short_name"] for r in rdz("routes.txt")}
cal = list(rdz("calendar.txt")); cdx = list(rdz("calendar_dates.txt"))
days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
def services(date):
    s = date.strftime("%Y%m%d")
    out = {c["service_id"] for c in cal if c["start_date"] <= s <= c["end_date"] and c[days[date.weekday()]] == "1"}
    for x in cdx:
        if x["date"] == s: (out.add if x["exception_type"] == "1" else out.discard)(x["service_id"])
    return out
trips = {t["trip_id"]: (routes[t["route_id"]], t["service_id"]) for t in rdz("trips.txt")}
st = []
for r in rdz("stop_times.txt"):
    if r["trip_id"] not in trips: continue
    hh, mm, ss = map(int, (r["departure_time"] or r["arrival_time"]).split(":"))
    st.append((r["trip_id"], trips[r["trip_id"]][0], int(r["stop_sequence"]), "1" + r["stop_id"].strip() if len(r["stop_id"].strip()) == 4 else r["stop_id"].strip(), hh * 3600 + mm * 60 + ss))
tdays = [(tid, dt.date(2019, 9, d).strftime("%Y%m%d")) for d in range(1, 31) for tid, (rt, sv) in trips.items() if sv in services(dt.date(2019, 9, d))]
def load(name, rows, cols):
    tmp = os.path.join(CACHE, f"_{name}.csv")
    with open(tmp, "w", newline="") as f: csv.writer(f).writerows(rows)
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv('{tmp}', header=false, columns={cols})"); os.remove(tmp)
load("gst", st, "{'trip_id':'VARCHAR','route':'VARCHAR','seq':'INT','stop':'VARCHAR','t':'INT'}")
load("gtd", tdays, "{'trip_id':'VARCHAR','sdate':'VARCHAR'}")
con.execute("""CREATE TABLE first_ AS SELECT DISTINCT route, arg_min(stop, seq) stop FROM gst GROUP BY trip_id, route
  UNION SELECT DISTINCT route, arg_max(stop, seq) stop FROM gst GROUP BY trip_id, route""")

# observed runs
orows = []
for d in range(1, 31):
    sd = dt.date(2019, 9, d).strftime("%Y%m%d"); midnight = dt.datetime(2019, 9, d, tzinfo=PT).timestamp()
    for rt in sorted(set(routes.values())):
        f = os.path.join(CACHE, f"{sd}_{rt}.json.gz")
        if not os.path.exists(f) or os.path.getsize(f) == 0: continue
        j = json.load(io.TextIOWrapper(gzip.open(f), "utf-8"))
        for stop, sdict in j.get("stops", {}).items():
            s1 = "1" + stop if len(stop) == 4 else stop
            for di, arr in sdict.get("arrivals", {}).items():
                orows += [(rt, f"{a['v']}|{a['i']}|{di}", s1, sd, int(a["t"] - midnight)) for a in arr]
load("ob", orows, "{'route':'VARCHAR','run':'VARCHAR','stop':'VARCHAR','sdate':'VARCHAR','t':'INT'}")
diag["obs_rows"] = len(orows)

H = f"read_parquet('{ewt}/hourly/2019-09.parquet')"
con.execute(f"CREATE TABLE dt AS SELECT DISTINCT sdate, daytype FROM {H}")
con.execute(f"CREATE TABLE xld AS SELECT DISTINCT route, sdate FROM {H} WHERE excl = 'line_day_outage'")
con.execute(f"""CREATE TABLE xh AS SELECT DISTINCT sdate, hr FROM {H} WHERE excl IS NOT NULL AND excl <> 'line_day_outage'
  UNION SELECT sdate, hr FROM {H} GROUP BY 1,2 HAVING sum(ob) < 0.5 * sum(eb)""")
OK = (" NOT EXISTS (SELECT 1 FROM xh WHERE xh.sdate = z.sdate AND xh.hr = z.t0 // 3600)"
      " AND NOT EXISTS (SELECT 1 FROM xh WHERE xh.sdate = z.sdate AND xh.hr = z.t1 // 3600)"
      " AND NOT EXISTS (SELECT 1 FROM xld WHERE xld.route = z.route AND xld.sdate = z.sdate)")
con.execute("""CREATE TABLE otp AS SELECT o.*, p.pos, row_number() OVER (PARTITION BY o.route, o.run, o.sdate ORDER BY o.t, o.stop) k
  FROM ob o JOIN tpf USING (route, stop) LEFT JOIN pos1 p USING (route, stop)
  WHERE NOT EXISTS (SELECT 1 FROM first_ f WHERE f.route = o.route AND f.stop = o.stop)""")
con.execute("""CREATE TABLE seg AS SELECT p.route, p.sdate, p.t t0, n.t t1, n.pos - p.pos dist, n.t - p.t obs_s
  FROM otp p JOIN otp n ON n.route = p.route AND n.run = p.run AND n.sdate = p.sdate AND n.k = p.k + 1 AND n.stop <> p.stop""")
diag["seg_both_ends"] = one("SELECT count(*) FROM seg")[0]
diag["seg_no_distance"] = one("SELECT count(*) FROM seg WHERE dist IS NULL OR dist <= 0")[0]
B = "dist > 0 AND obs_s > 0 AND obs_s <= 10800 AND dist / obs_s * 3600 <= 60"
con.execute(f"""COPY (SELECT z.route, z.sdate, dt.daytype, z.t0 // 3600 hr, count(*) nseg, round(sum(dist), 6) dist, sum(obs_s) obs_s, NULL::DOUBLE sch_s
  FROM seg z JOIN dt USING (sdate) WHERE {B} AND {OK} GROUP BY ALL ORDER BY ALL) TO '{ewt}/seg/2019-09.parquet' (FORMAT parquet)""")
diag["seg_kept"] = one(f"SELECT sum(nseg) FROM '{ewt}/seg/2019-09.parquet'")[0]
# scheduled: every scheduled trip-day's consecutive timepoints (first stop out), on the kept dates
con.execute("""CREATE TABLE gtp AS SELECT g.trip_id, g.route, g.seq, g.t, p.pos, row_number() OVER (PARTITION BY g.trip_id ORDER BY g.seq) k
  FROM gst g JOIN tpf USING (route, stop) LEFT JOIN pos1 p USING (route, stop)
  WHERE g.seq > (SELECT min(seq) FROM gst x WHERE x.trip_id = g.trip_id) AND g.seq < (SELECT max(seq) FROM gst x WHERE x.trip_id = g.trip_id)""")
con.execute(f"""COPY (SELECT a.route, dt.daytype, a.t // 3600 hr, count(*) nseg, round(sum(b.pos - a.pos), 6) dist, sum(b.t - a.t) sch_s
  FROM gtp a JOIN gtp b ON b.trip_id = a.trip_id AND b.k = a.k + 1 JOIN gtd ON gtd.trip_id = a.trip_id JOIN dt USING (sdate)
  WHERE b.pos - a.pos > 0 AND b.t > a.t AND gtd.sdate IN (SELECT DISTINCT sdate FROM '{ewt}/seg/2019-09.parquet')
  GROUP BY ALL ORDER BY ALL) TO '{ewt}/sched-2019-09.parquet' (FORMAT parquet)""")
json.dump(diag, open(f"{ewt}/seg/2019-09.json", "w"), indent=1)
print(json.dumps(diag))
