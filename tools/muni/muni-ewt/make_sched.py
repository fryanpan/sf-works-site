"""Stand-in schedule for a 511 historic month whose Regional GTFS lacks Muni's trips (2022-08 has 0 Muni trips in
trips.txt and stop_times.txt). Builds trips.csv.gz, stop_times.csv.gz and calendar_dates.csv.gz in the extract
directory, in the 511 layout ewt_month.py reads, from a Muni GTFS that SFMTA itself published and the Internet
Archive captured (~/faster-muni-hist/zips/<capture>.zip). The originals are kept as *.orig.csv.gz.
  route_id   'SF:' + route_short_name (511's own form, e.g. SF:14R)
  trip_id    'SFG:' + Muni trip_id (never matches an observed 511 trip id, so observed direction comes from the
             observation row's own direction_id; ewt_month.py falls back to it)
  stop_id    '1' + Muni stop_id where that is four digits: 511 writes Muni's five-digit stop code (13181), SFMTA's
             GTFS the four-digit stop id (3181). Without the prefix no observed stop matched a scheduled one
             (Fable review 2026-11-09, finding 3); with it 3,184 of the 3,194 stops observed in 2022-09 (after cleaning) match.
  service_id one per trip; calendar_dates lists every date in the month the trip runs (calendar.txt plus
             calendar_dates.txt exceptions), exception_type 1.
Usage: python3 make_sched.py <muni gtfs zip> <YYYY-MM> <extract dir>
"""
import sys, os, io, csv, gzip, zipfile, datetime as dt, collections
zp, month, d = sys.argv[1:4]
Z = zipfile.ZipFile(zp)
rd = lambda n: csv.DictReader(io.TextIOWrapper(Z.open(n), "utf-8-sig"))
y, m = map(int, month.split("-"))
dates = [dt.date(y, m, 1) + dt.timedelta(days=i) for i in range(31) if (dt.date(y, m, 1) + dt.timedelta(days=i)).month == m]
wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
svc = collections.defaultdict(set)
for c in rd("calendar.txt"):
    for x in dates:
        s = x.strftime("%Y%m%d")
        if c["start_date"] <= s <= c["end_date"] and c[wd[x.weekday()]] == "1": svc[c["service_id"]].add(s)
if "calendar_dates.txt" in Z.namelist():
    for e in rd("calendar_dates.txt"):
        if e["date"][:6] == month.replace("-", ""):
            (svc[e["service_id"]].add if e["exception_type"] == "1" else svc[e["service_id"]].discard)(e["date"])
short = {r["route_id"]: r["route_short_name"].strip() for r in rd("routes.txt")}
for f in ("trips", "stop_times", "calendar_dates"):
    p = os.path.join(d, f + ".csv.gz"); o = os.path.join(d, f + ".orig.csv.gz")
    if os.path.exists(p) and not os.path.exists(o): os.rename(p, o)
keep = {}
with gzip.open(os.path.join(d, "trips.csv.gz"), "wt") as g, gzip.open(os.path.join(d, "calendar_dates.csv.gz"), "wt") as h:
    w = csv.writer(g); w.writerow(["route_id", "service_id", "trip_id", "direction_id"])
    v = csv.writer(h); v.writerow(["service_id", "date", "exception_type"])
    for t in rd("trips.txt"):
        ds = svc.get(t["service_id"])
        if not ds: continue
        tid = "SFG:" + t["trip_id"]; keep[t["trip_id"]] = tid
        w.writerow(["SF:" + short[t["route_id"]], tid, tid, t.get("direction_id", "")])
        for s in sorted(ds): v.writerow([tid, s, 1])
n = 0
with gzip.open(os.path.join(d, "stop_times.csv.gz"), "wt") as g:
    w = csv.writer(g); w.writerow(["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"])
    for r in rd("stop_times.txt"):
        if r["trip_id"] in keep:
            sid = r["stop_id"].strip(); sid = "1" + sid if len(sid) == 4 and sid.isdigit() else sid
            w.writerow([keep[r["trip_id"]], sid, r["stop_sequence"], r["arrival_time"].strip(), r["departure_time"].strip()]); n += 1
open(os.path.join(d, "SCHEDULE_SOURCE"), "w").write(os.path.basename(zp) + "\n")
print(month, "trips", len(keep), "stop_times", n, "service ids with dates", sum(1 for s in svc.values() if s))
