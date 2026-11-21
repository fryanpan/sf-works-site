"""Write site/data/muni-map.json, the stops, line shapes and stop order behind sf-works.org/transportation/muni/lines.

Reads SFMTA's own GTFS feed (muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip, cached at .cache/muni-gtfs/) for
line names, modes, shapes, stop positions and the order of stops along each line, data/muni-ewt/ref/retired_lines.json
(retired_lines.py) for a listed line today's feed no longer carries (the KT), and data/muni-ewt/stops/<month>.csv
(ewt_stops.py) for each stop's excess wait in frequent hours. 511 writes Muni's five-digit stop code, which is
SFMTA's stop_code.

--update re-downloads the feed only when its Last-Modified header differs from the cached copy's; a failed download
keeps the cached copy and says so. Checks, before writing: at least 60 lines in routes.txt, at least 95% of the
stop rows in the month's CSV matched to a stop position, every frequent line site_data.py lists has a shape and a name
(a less frequent one needs a name; one with no shape is named on stderr and in noShape), no stop listed twice.
Idempotent: no run date in the output, everything sorted, coordinates rounded to 5 decimals (about 3 feet).
Usage: python3 tools/muni/muni-ewt/muni_map.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, io, json, math, os, re, sys, urllib.request, zipfile


def hav(lon1, lat1, lon2, lat2):
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(a))
from collections import Counter, defaultdict
from shapely.geometry import LineString

ROOT = paths.ROOT
URL = "https://muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip"
CACHE = os.path.join(ROOT, ".cache", "muni-gtfs")
ZIP = os.path.join(CACHE, "muni_gtfs-current.zip")
OUT = os.path.join(ROOT, "site", "data", "muni-map.json")
SITE = json.load(open(os.path.join(ROOT, "site", "data", "muni.json")))
errors = []

def fetch():
    os.makedirs(CACHE, exist_ok=True)
    stamp = os.path.join(CACHE, "last-modified.txt")
    old = open(stamp).read().strip() if os.path.exists(stamp) else ""
    try:
        head = urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=60)
        lm = head.headers.get("Last-Modified", "")
        if lm and lm == old and os.path.exists(ZIP):
            print("feed unchanged:", lm)
            return
        body = urllib.request.urlopen(URL, timeout=120).read()
        zipfile.ZipFile(io.BytesIO(body)).testzip()
        open(ZIP, "wb").write(body)
        open(stamp, "w").write(lm)
        print("fetched feed:", lm, len(body), "bytes")
    except Exception as e:  # keep the last good copy
        print("feed fetch failed, keeping cached copy:", e, file=sys.stderr)

if "--update" in sys.argv or not os.path.exists(ZIP):
    fetch()
z = zipfile.ZipFile(ZIP)
read = lambda f: list(csv.DictReader(io.TextIOWrapper(z.open(f), "utf-8-sig")))

routes = read("routes.txt")
if len(routes) < 60:
    errors.append(f"routes.txt has {len(routes)} lines")
stops = {s["stop_id"]: s for s in read("stops.txt")}

# SFMTA's stop_name is written for its own systems ("Metro Civic Center Station/Downtn", "Mcallister St",
# "Right Of Way/Ocean Ave", "Laguna Honda Blvd/opp Forest Hill"). The map popups show it to riders, so it is spelled
# out: abbreviations expanded, a subway platform named by its direction, slashes spaced, "Mc" names capitalised.
# The stop code stays the key; only the label changes.
WORDS = {"Downtn": "Downtown", "Outbd": "Outbound", "Sta": "Station", "Br": "Bridge", "opp": "opposite",
         "Bart": "BART", "GoeThe": "Goethe", "StW": "St"}
def stop_name(n):
    n = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), n.strip())
    n = re.sub(r"\s+[A-Z]{2}-[A-Z]{2}/\s*[A-Z]{2}$", "", n)  # "SE-FS/ BZ": SFMTA's corner and bus-zone code
    n = re.sub(r"^Right Of Way/", "", n)
    n = " ".join(WORDS.get(w, w) for w in n.split(" "))
    n = re.sub(r"\b(\w+)/(Downtn|Outbd|Downtown|Outbound)$", lambda m: m.group(1) + "/" + WORDS.get(m.group(2), m.group(2)), n)
    n = re.sub(r"/(Sta|Br|opp|Bart)\b", lambda m: "/" + WORDS[m.group(1)], n)
    n = re.sub(r"\bopp\b", "opposite", n)
    m = re.match(r"^Metro (.+ Station)/(Downtown|Outbound)$", n)
    if m:
        n = f"{m.group(1)}, {'toward downtown' if m.group(2) == 'Downtown' else 'outbound'}"
    n = re.sub(r"^Metro ", "", n)
    n = re.sub(r"Station (Northbound|Southbound|Outbound|Inbound)$", lambda m: "Station, " + m.group(1).lower(), n)
    n = re.sub(r"\s*/\s*", " / ", n)
    return n
by_code = {s["stop_code"]: s for s in stops.values() if s["stop_code"]}
RETIRED = json.load(open(os.path.join(ROOT, "data", "muni-ewt", "ref", "retired_lines.json")))
for code, s_ in RETIRED["stops"].items():  # a retired line's stops that today's feed has dropped
    by_code.setdefault(code, {"stop_code": code, "stop_name": s_["name"], "stop_lon": s_["lon"], "stop_lat": s_["lat"]})

def span(a, b):
    out, (y, m) = [], (int(a[:4]), int(a[5:]))
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out
WIN = {w: x.get("monthList") or span(*x["months"]) for w, x in SITE["windows"].items()}
# the period of the same length just before each one, for a stop's change; none where site_data.py found none
PREV = {f"prev{w}": span(*x["before"]) for w, x in SITE["windows"].items() if x["before"]}
rows = []
for m in sorted(set().union(*WIN.values(), *PREV.values())):
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "muni-ewt", "stops", f"{m}.csv"))):
        r["month"] = m
        rows.append(r)
matched = [r for r in rows if r["stop"] in by_code]
for m in sorted({r["month"] for r in rows}):  # per month, so one bad month can't hide in the pool
    n = sum(1 for r in rows if r["month"] == m)
    k = sum(1 for r in matched if r["month"] == m)
    # 94%: the rows that don't match are stops removed or renumbered since, about 100 to 120 rows in early 2022 (the
    #   29 Sunset's 21 removed stops both ways, the 49's Van Ness BRT stops, the 9R, 9 and 8). The 10-minute rule of
    #   pre-send gate round 4 left those rows as they were and cut the month's frequent rows by about 15%, which put
    #   January, February and April 2022 at 94.5% to 94.9%; a broken join drops far more
    if k < 0.94 * n:
        errors.append(f"{m}: only {k} of {n} stop rows matched a stop position")
ranked = set(SITE["lines"])
# The less frequent lines (frequent: false in muni.json) get a shape, stop order, length and left-early stops for their
# own page and the Lines page, but no stop excess wait: their hours are judged on time, and the map's stops pool the
# frequent lines only. One with no shape in today's feed or retired_lines.json (the S shuttle) is drawn without a map.
frequent = {l for l, v in SITE["lines"].items() if v.get("frequent", True)}

# Representative pattern per line and direction: the shape and stop list the most trips use
trips = read("trips.txt")
pat = Counter((t["route_id"], t["direction_id"], t["shape_id"]) for t in trips)
top = {}
for (r, d, s), n in sorted(pat.items()):
    if (r, d) not in top or n > top[(r, d)][1]:
        top[(r, d)] = (s, n)
want_shapes = {s for (r, d), (s, n) in top.items() if r in ranked}
trip_of = {}
for t in trips:
    k = (t["route_id"], t["direction_id"])
    if k in top and t["shape_id"] == top[k][0] and k not in trip_of:
        trip_of[k] = t["trip_id"]
order = defaultdict(list)
want_trips = {v: k for k, v in trip_of.items()}
for st in read("stop_times.txt"):
    k = want_trips.get(st["trip_id"])
    if k:
        order[k].append((int(st["stop_sequence"]), st["stop_id"]))
pts = defaultdict(list)
for p in read("shapes.txt"):
    if p["shape_id"] in want_shapes:
        pts[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"])))

rd = lambda v: round(v, 5)
lines = {}
for r in routes:
    rid = r["route_short_name"]
    if rid not in ranked:
        continue
    geom, miles = [], []
    for d in ("0", "1"):
        if (rid, d) not in top:
            continue
        p = sorted(pts.get(top[(rid, d)][0], []))
        if len(p) < 2:
            errors.append(f"line {rid} direction {d}: shape {top[(rid, d)][0]} has under two points in shapes.txt")
            continue
        ls = LineString([(x, y) for _, x, y in p]).simplify(0.00008)
        geom.append([[rd(x), rd(y)] for x, y in ls.coords])
        # Route length in miles over the full, unsimplified shape (haversine per vertex pair), for the Lines page's
        # end-to-end trip time by hour, length over average speed (Bryan, 2026-11-10).
        miles.append(round(sum(hav(p[i][1], p[i][2], p[i + 1][1], p[i + 1][2]) for i in range(len(p) - 1)), 2))
    if not geom:
        errors.append(f"line {rid} has no shape")
    seq = {d: [by_id["stop_code"] for _, sid in sorted(order[(rid, d)]) if (by_id := stops.get(sid))] for d in ("0", "1")}
    # SFMTA's own colour for the line (GTFS route_color / route_text_color), which its maps draw it in.
    col = {"color": "#" + r["route_color"].strip().upper(), "text": "#" + r["route_text_color"].strip().upper(), "type": int(r["route_type"])}
    if not re.fullmatch(r"#[0-9A-F]{6}", col["color"]) or not re.fullmatch(r"#[0-9A-F]{6}", col["text"]):
        errors.append(f"line {rid} has no route colour")
    lines[rid] = {"shape": geom, "order": seq, "miles": miles, **col}
    if not all(0.5 < m < 40 for m in miles):
        errors.append(f"line {rid}: route length {miles} miles is out of range")
noshape = []
for rid in sorted(ranked - set(lines)):
    R_ = RETIRED["lines"].get(rid)
    if not R_ and rid not in frequent:
        noshape.append(rid)
        continue
    if not R_:
        errors.append(f"line {rid} is listed but in neither today's GTFS nor retired_lines.json")
        continue
    geom = [[[rd(x), rd(y)] for x, y in LineString(sh).simplify(0.00008).coords] for sh in R_["shape"]]
    miles = [round(sum(hav(*sh[i], *sh[i + 1]) for i in range(len(sh) - 1)), 2) for sh in R_["shape"]]
    lines[rid] = {"shape": geom, "order": R_["order"], "miles": miles, "color": R_["color"].strip().upper(), "text": R_["text"].strip().upper(), "type": R_["type"]}
    if not all(len(g) >= 2 for g in geom) or not geom:
        errors.append(f"retired line {rid} has an empty shape")
    if not re.fullmatch(r"#[0-9A-F]{6}", lines[rid]["color"]) or not re.fullmatch(r"#[0-9A-F]{6}", lines[rid]["text"]):
        errors.append(f"retired line {rid} has no route colour")

# Each line's stops (for highlighting and the along-the-route strip), and each stop with every line pooled (the map),
# for each period. Months pool the same way as stop-hours: scheduled wait by scheduled departures, actual by observed.
MINEB = 150  # scheduled departures in frequent hours per month of the period: about five a day
acc = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
pool = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
on = defaultdict(set)
for r in matched:
    eb, ob = float(r["eb"]), float(r["ob"])
    if r["route"] not in frequent or not r["awt"] or not r["swt"] or ob == 0:
        continue  # a stop with one bus an hour (the 714, a bus substitute's lone trip) has no scheduled wait to compare
    for w, ms in {**WIN, **PREV}.items():
        if r["month"] not in ms:
            continue
        for p in (acc[(w, r["route"], r["dir"], r["stop"])], pool[(w, r["stop"])]):
            p[0] += float(r["swt"]) * eb; p[1] += eb; p[2] += float(r["awt"]) * ob; p[3] += ob
        if w in WIN:
            on[r["stop"]].add(r["route"])
ewt_of = lambda p, n: round(p[2] / p[3] - p[0] / p[1], 2) if p[1] >= MINEB * n and p[3] > 0 else None
stop_out = []
for code in sorted(on):
    e = {w: ewt_of(pool[(w, code)], len(ms)) for w, ms in WIN.items() if (w, code) in pool}
    e = {w: v for w, v in e.items() if v is not None}
    if not e:
        continue
    s_ = by_code[code]
    stop_out.append({"stop": code, "name": stop_name(s_["stop_name"]), "lon": rd(float(s_["stop_lon"])), "lat": rd(float(s_["stop_lat"])),
                     "ewt": e, "lines": sorted(on[code], key=lambda l: (len(l), l))})
if len({s_["stop"] for s_ in stop_out}) != len(stop_out):
    errors.append("a stop appears twice")
pos = {s_["stop"]: i for i, s_ in enumerate(stop_out)}
for rid in lines:
    per = defaultdict(dict)
    for (w, route, d, code), p in acc.items():
        if route == rid and code in pos and (v := ewt_of(p, len({**WIN, **PREV}[w]))) is not None:
            per[(d, code)][w] = v
    lines[rid]["stops"] = [{"stop": c, "dir": d, "ewt": {w: v for w, v in per[(d, c)].items() if w in WIN},
                            "prev": {w[4:]: v for w, v in per[(d, c)].items() if w in PREV}}
                           for d, c in sorted(per) if any(w in WIN for w in per[(d, c)])]

# Departures that left a timepoint more than 1 minute early, SFMTA's window (ontime_month.py's early_sf; Bryan,
# 2026-11-17), in each line's hours with a bus less often than every 10 minutes, by stop and period: the stops where buses run early. A stop needs MINTP timepoint
# departures a month of the period to be shown.
MINTP = 20
early = defaultdict(lambda: [0, 0])
def standin(m):
    """A month 511 carried no timetable for: ontime_month.py fell back to every stop, so it isn't comparable."""
    dg = os.path.join(ROOT, "data", "muni-ewt", "diag", f"{m}.json")
    return os.path.exists(dg) and json.load(open(dg)).get("schedule_source", "511 historic GTFS") != "511 historic GTFS"
for m in sorted(set().union(*WIN.values())):
    if standin(m):
        continue
    f = os.path.join(ROOT, "data", "muni-ewt", "ontime", f"{m}-stops.csv")
    if not os.path.exists(f):
        errors.append(f"no on-time stops file for {m}")
        continue
    for r in csv.DictReader(open(f)):
        if r["route"] in lines and r["stop"] in by_code:
            for w, ms in WIN.items():
                if m in ms:
                    a = early[(r["route"], r["dir"], r["stop"], w)]; a[0] += int(r["n"]); a[1] += int(r["early_sf"])
for rid in lines:
    per = defaultdict(dict)
    for (route, d, code, w), (n, e) in early.items():
        if route == rid and n >= MINTP * len([m for m in WIN[w] if not standin(m)]):
            per[(d, code)][w] = round(e / n, 3)
    lines[rid]["early"] = [{"stop": c, "dir": d, "name": stop_name(by_code[c]["stop_name"]), "lon": rd(float(by_code[c]["stop_lon"])),
                            "lat": rd(float(by_code[c]["stop_lat"])), "share": per[(d, c)]} for d, c in sorted(per)]

def title(n):
    w = " ".join(x.capitalize() for x in n.lower().split())
    return w.replace("O'shaughnessy", "O'Shaughnessy").replace("-", "-")
names = {r["route_short_name"]: "-".join(title(p) for p in r["route_long_name"].split("-")) for r in routes}
for rid, R_ in RETIRED["lines"].items():
    names.setdefault(rid, "-".join(title(p) for p in R_["name"].split("-")))
if missing := sorted(l for l in frequent if not (names.get(l) or "").strip() or not lines.get(l, {}).get("shape")):
    errors.append(f"listed lines with no name or shape: {missing}")
if missing := sorted(l for l in ranked - frequent - set(noshape) if not (names.get(l) or "").strip()):
    errors.append(f"less frequent lines with no name: {missing}")
if noshape:
    print(f"less frequent lines with no shape in today's GTFS or retired_lines.json, drawn without a map: {noshape}", file=sys.stderr)
out = {"minScheduled": MINEB, "stops": stop_out, "lines": lines, "names": names, "noShape": noshape}
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
text = json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n"
old = open(OUT).read() if os.path.exists(OUT) else None
if text != old:
    open(OUT, "w").write(text)
    print("wrote", OUT, len(text), "bytes")
else:
    print("unchanged", OUT)
print(f"{len(stop_out)} stops, {len(lines)} lines")
