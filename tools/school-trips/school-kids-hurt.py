#!/usr/bin/env python3
"""Kids hurt on SF weekdays and how near a school's grounds, for School Trips' crash charts and its model's injury shares.

    tools/school-trips/school-kids-hurt.py          # writes site/data/school-kids-hurt.json and site/data/school-crossings.json

Bryan, 2026-10-13, on the evidence doc: "Please update to measure using same
definition as state law across all of the things we're working on", "we only
want to look at the 107 kids hurt on SF weekdays", and "can you add this as a
heat map by main street vs. residential and distance (500 ft, 1/4 mile,
farther)".

THE BASE. A victim counts when they were 5 to 18, injured or killed, on a
weekday from 6 am to 6 pm, in school years 2021-22 to 2024-25 (August 1 to May
31, June and July out), in DataSF nwes-mmgh, read through scripts/sfdata.py. Rows without a location
are counted (noLocation) and left out of every share. The window is
lib/school_window.py's, the one definition every count of kids hurt near
schools uses (Bryan, 2026-10-21: "keep it to school hours (6AM to 6PM) on
weekdays during the school year ... make the school year from August to end of
May").

DISTANCE. Feet from the crash to the nearest grounds of the simulation's schools,
public, charter and private (site/data/school-sim/index.json), measured from the edge of the
grounds as California's school-zone law measures it (data/school-sim/grounds.json,
lib/school_grounds.py). Bands: within ZONE_FT (the school zone), ZONE_FT
to a quarter mile, farther.

STREET TYPE. Main when either of the crash's two streets is tertiary or above in
OpenStreetMap, residential when both are residential, living or unclassified,
unmatched when a name has no OpenStreetMap match (tools/school-trips/school-calm-priority.py's
matching).

THE MODEL'S SHARES (model, read by site/src/school-trips-model.mjs through
city.json): near is the share within a quarter mile; walkBike the walking and
biking share of those; lastBlock the share of near walking and biking kids within
LAST_BLOCK_FT of the grounds; reach, for each of safety upgrades' three reaches,
the kids hurt within it by how they travelled and the street intersections within
it (OpenStreetMap's drive network, data/osm-cache/sf-drive.json, each counted at
its nearest school only), which scale the upgrades' cost. Bryan, 2026-10-15: "Keep
all intersections on big enough roads to be a problem." So intersections counts only
those with a main street (a street OpenStreetMap ranks tertiary or above, the same
rule as STREET TYPE, trunk roads such as 19th Avenue included), intersectionsAll counts every one, and a reach credits only
kids hurt off residential-only corners and within X_NEAR_FT of a main intersection
it treats; zoneKidsYear the kids a year within ZONE_FT;
zoneHours the share of those hurt from 7 to 9 am or 2 to 5 pm, when a school
zone limit applies; bellN of bellD is the share of the near kids hurt at their
nearest school's bell hours: 45
minutes before the start bell to 15 after, and 15 minutes before the end bell to
45 after, at the school's SFUSD bell times from out/school-hour-crashes/schools.json
(the latest year's, 8:15 am and 3:15 pm where it has none). The same base as near,
so the model's NEAR x BELL is one population.

SPEED (model.speed). The kids hurt on the blocks tools/school-trips/school-speed-levers.py
picks for 20 mph business districts, speed humps and speed cameras, by school
and mode: on the lever's own street, within LEVER_FT of a district or hump block
(humps only where both streets are residential), within a quarter mile of a
camera. District kids inside a 500 ft zone in its hours are left to the school
zone limits.

BIKEWAYS (model.bikeways). For each new bikeway budget in out/school-sim/segments.json, the kids hurt within
LEVER_FT of its stretches, on the stretch's street, where both streets are residential: the calmed blocks, which the
model cuts by calming's effect (Bryan, 2026-10-18, on the bikeways adding kids hurt: "Are you sure new protected
bikeways or high quality slow streets lead to more injuries??"). A kid hurt near two stretches counts once. Kids hurt
within CALM_FT of any school's grounds, which safety upgrades' calming may reach, and on speed hump blocks are left
out, so no kid is cut twice; that undercounts the bikeways when a plan buys neither.

CROSSINGS (school-crossings.json). For each school, the main street intersections within a quarter mile of its own
grounds and which reach takes them in: 0 within one block, 1 within two, 2 within a quarter mile. The school view
marks the ones the chosen reach would treat (Bryan, 2026-10-13: "in the school tool can you show which
intersections might get some treatment with safer crossings in the school view?").

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build read by the School Trips
pages. It reads the cached query; sfdata.py refetches when its cache is stale.
In pipeline/transportation-update.py after school-speed-levers and school-segments (its bikeways read
out/school-sim/segments.json), and before school-sim.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata
from lib import school_grounds, school_points, school_window

YEARS = school_window.years(2021, 2024)
ZONE_FT, NEAR_FT, LAST_BLOCK_FT = 500, 1320, 350
UPGRADE_FT = (350, 660, 1320)   # one block, two blocks (an eighth of a mile), a quarter mile
X_NEAR_FT = 150   # a kid hurt this close to a treated intersection is credited with its upgrades
LEVERS = os.path.join(ROOT, "data", "school-sim", "speed-levers.json")
SEGMENTS = os.path.join(ROOT, "out", "school-sim", "segments.json")
LEVER_FT = 100    # a crash this close to a business district or hump block, on its street, is on that block
CALM_FT = 660     # safety upgrades' calming reaches residential streets this far from a school's grounds
MERGE_FT = 60   # intersection nodes closer than this are one crossing
DRIVE = os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")
NOT_STREET = {"motorway", "motorway_link", "trunk_link", "service", "track", "path", "footway", "cycleway", "steps", "pedestrian"}
OUT = os.path.join(ROOT, "site", "data", "school-kids-hurt.json")
CROSS_OUT = os.path.join(ROOT, "site", "data", "school-crossings.json")
SUMMARY = os.path.join(ROOT, "out", "school-hour-crashes", "summary.json")
BELLS = os.path.join(ROOT, "out", "school-hour-crashes", "schools.json")
DEFAULT_BELL = (495, 495, 915, 915)   # 8:15 am and 3:15 pm, as school-hour-crashes.py takes them
BANDS = ["Within 500 ft", "500 ft to 1/4 mile", "Farther"]
STREETS = ["Main street", "Residential street", "Street not matched"]
MODES = {"Pedestrian": "Walking", "Bicyclist": "Biking", "Driver": "In a car", "Passenger": "In a car", "Other": "Scooter or other"}

calm = paths.load("school-calm-priority.py", "calm")


def intersections():
    """Street intersections, nodes where three or more named street ends meet, from the drive network, with a divided
    street's two carriageway nodes and its median cuts merged into one point."""
    els = json.load(open(DRIVE))["elements"]
    at = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
    deg, names = collections.Counter(), collections.defaultdict(set)
    for e in els:
        t = e.get("tags", {}) if e["type"] == "way" else {}
        hw = t.get("highway")
        # Named alleys count, since SoMa's and the Mission's are crossed on the walk to school. Unnamed ways (median
        # cut-throughs) and ramps (*_link) don't.
        if e["type"] != "way" or not t.get("name") or (hw in NOT_STREET and not (hw == "service" and t.get("service") == "alley")) \
                or (hw or "").endswith("_link"):
            continue
        ns = e["nodes"]
        for i, n in enumerate(ns):
            deg[n] += 1 if i in (0, len(ns) - 1) else 2
            names[n].add(t["name"])
    # Two or more street names meet, so a one-way split of one street isn't a crossing.
    nodes = [n for n, c in deg.items() if c >= 3 and len(names[n]) >= 2 and n in at]
    pts = [at[n] for n in nodes]
    import numpy as np
    from scipy.spatial import cKDTree
    xy = np.array([((lo - pts[0][0]) * school_grounds.FT_LON, (la - pts[0][1]) * school_grounds.FT_LAT) for lo, la in pts])
    parent = list(range(len(pts)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in cKDTree(xy).query_pairs(MERGE_FT):
        parent[root(i)] = root(j)
    groups = collections.defaultdict(list)
    for i in range(len(pts)):
        groups[root(i)].append(i)
    # A main street intersection is one where at least one of its streets is a main street, by the rule each kid's
    # crash is labelled by: OpenStreetMap ranks the street tertiary or above anywhere in SF (calm.street_ranks), the
    # rule tools/school-trips/school-speed-levers.py uses too. Bryan, 2026-10-15: "Keep all intersections on big enough roads to
    # be a problem." Where both streets are residential, calming covers it.
    ranks = calm.street_ranks()
    out = sorted((round(sum(pts[i][0] for i in g) / len(g), 6), round(sum(pts[i][1] for i in g) / len(g), 6),
                  any(ranks.get(calm.norm(n), 0) >= 2 for i in g for n in names[nodes[i]])) for g in groups.values())
    assert 4000 < len(out) < 9000, "%d intersections: the drive network read is off" % len(out)
    main = [m for _, _, m in out]
    assert 0.2 < sum(main) / len(main) < 0.8, "%d of %d intersections on a main street: the rank join is off" % (sum(main), len(main))
    return out


def speed_kids(rows):
    """The kids hurt each of the three speed changes acts on, by the school whose block or camera it is and how they
    travelled, from data/school-sim/speed-levers.json (tools/school-trips/school-speed-levers.py).

    Business districts: within LEVER_FT of a district block and on its street (one of the crash's two roads), all
    hours, but not inside a 500 ft school zone in the hours its limit applies, which the school zone speed limits
    cover. Humps: within LEVER_FT of a hump block, on its street, where both streets are residential. Cameras: on the
    camera's street within a quarter mile of it, NYC's camera corridor. A crash near two goes to the nearest."""
    from shapely import LineString, Point, STRtree
    L = json.load(open(LEVERS))
    FX, FY = school_grounds.FT_LON, school_grounds.FT_LAT
    out = {}
    for kind, blocks, ok in (("bad", L["bad"]["blocks"], lambda r: not (r["band"] == 0 and r["hours"])),
                             ("humps", L["humps"]["blocks"], lambda r: r["street"] == 1)):
        lines = [LineString([(x * FX, y * FY) for x, y in b["pts"]]) for b in blocks]
        tree, kids = STRtree(lines), {}
        for r in rows:
            if not ok(r):
                continue
            p = Point(r["lo"] * FX, r["la"] * FY)
            hit = min(((lines[k].distance(p), k) for k in tree.query(p, predicate="dwithin", distance=LEVER_FT)
                       if blocks[k]["street"] in r["rd"]), default=None)
            if hit:
                r["on_" + kind] = True
                m = kids.setdefault(blocks[hit[1]]["cds"], {})
                m[r["mode"]] = m.get(r["mode"], 0) + 1
        out[kind] = {"kids": kids}
    out["bad"]["corridors"] = {}
    for c in sorted({(b["cds"], b["corridor"]) for b in L["bad"]["blocks"]}):
        out["bad"]["corridors"][c[0]] = out["bad"]["corridors"].get(c[0], 0) + 1
    out["humps"]["humps"] = {}
    for b in L["humps"]["blocks"]:
        out["humps"]["humps"][b["cds"]] = out["humps"]["humps"].get(b["cds"], 0) + b["humps"]
    cams, kids = L["cameras"]["new"], {}
    for r in rows:
        hit = min(((math.hypot((r["lo"] - c["lon"]) * FX, (r["la"] - c["lat"]) * FY), c["cds"]) for c in cams if c["street"] in r["rd"]), default=None)
        if hit and hit[0] <= NEAR_FT:
            m = kids.setdefault(hit[1], {})
            m[r["mode"]] = m.get(r["mode"], 0) + 1
    out["cameras"] = {"kids": kids, "sites": {c["cds"]: 1 for c in cams}}
    for k in out:
        out[k]["total"] = {m: sum(x.get(m, 0) for x in out[k]["kids"].values()) for m in sorted(set(MODES.values()))}
    # Quality: each change finds kids, and none finds more than the base.
    assert all(0 < sum(out[k]["total"].values()) < len(rows) for k in out), {k: out[k]["total"] for k in out}
    return out


def bikeway_kids(rows):
    """The kids hurt on each new bikeway budget's calmed blocks, by how they travelled: within LEVER_FT of one of its
    stretches, on that stretch's street, where both streets are residential."""
    from shapely import MultiLineString, Point, STRtree
    sg = json.load(open(SEGMENTS))
    FX, FY = school_grounds.FT_LON, school_grounds.FT_LAT
    by = {c["id"]: c for c in sg["chunks"]}
    out = {}
    for b in sg["budgets"]:
        cs = [by[i] for i in b["chunks"]]
        lines = [MultiLineString([[(x * FX, y * FY) for x, y in ln] for ln in c["pts"]]) for c in cs]
        names = [calm.norm(c["street"]) for c in cs]
        tree, kids = STRtree(lines), {}
        for r in rows:
            if r["street"] != 1 or r["ft"] <= CALM_FT or r.get("on_humps"):
                continue
            p = Point(r["lo"] * FX, r["la"] * FY)
            if any(names[k] in r["rd"] for k in tree.query(p, predicate="dwithin", distance=LEVER_FT)):
                kids[r["mode"]] = kids.get(r["mode"], 0) + 1
        out[str(b["budgetM"])] = dict(sorted(kids.items()))
    # Quality: the biggest budget finds some kids, and fewer than the base.
    tot = [sum(out[str(b["budgetM"])].values()) for b in sg["budgets"]]
    assert 0 < tot[-1] < len(rows), tot
    return out


def main():
    sch = school_points.index_schools()
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,"
                     "collision_datetime,collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd", floor=80000)
    ranks = calm.street_ranks()
    rows, no_loc = [], 0
    for v in V.rows:
        kh = school_window.kid_hurt(v)
        if kh is None or kh["year"] not in YEARS:
            continue
        age, h = kh["age"], kh["hour"]
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            no_loc += 1
            continue
        a, b = (ranks.get(calm.norm(v.get(k)).replace("BAY SHORE", "BAYSHORE")) for k in ("primary_rd", "secondary_rd"))
        street = 2 if a is None or b is None else 0 if max(a, b) >= 2 else 1
        hours = 7 <= h < 9 or 14 <= h < 17
        role = v.get("victim_role")
        # A driver under 16 can't hold a licence, so the record is most likely a scooter or a bike miscoded.
        mode = "Scooter or other" if role == "Driver" and age < 16 else MODES.get(role, "Scooter or other")
        rows.append({"lo": lo, "la": la, "street": street, "mode": mode, "rd": (calm.norm(v.get("primary_rd")), calm.norm(v.get("secondary_rd"))),
                     "hours": hours, "min": h * 60 + kh["minute"]})
    bells = {}
    for b in json.load(open(BELLS)):
        yrs = sorted(b.get("bell") or {})
        y = (b["bell"] or {}).get(yrs[-1]) if yrs else None
        bells[school_grounds.key(b["lon"], b["lat"])] = (y["start_min"], y["start_max"], y["end_min"], y["end_max"]) if y else DEFAULT_BELL
    sb = [bells.get(school_grounds.key(s["lon"], s["lat"]), DEFAULT_BELL) for s in sch]
    near_j, dist = school_grounds.nearest([(s["lon"], s["lat"]) for s in sch], [r["lo"] for r in rows], [r["la"] for r in rows], 5280)
    for r, dd, j in zip(rows, dist, near_j):
        r["ft"] = float(dd) if dd == dd else 1e9
        a0, a1, p0, p1 = sb[j] if j >= 0 else DEFAULT_BELL
        r["bell"] = a0 - 45 <= r["min"] < a1 + 15 or p0 - 15 <= r["min"] < p1 + 45
        r["band"] = 0 if r["ft"] <= ZONE_FT else 1 if r["ft"] <= NEAR_FT else 2
    # Safety upgrades go to TK-8 schools only, so their reaches are measured to the nearest TK-8 school's grounds.
    k8 = [s for s in sch if s.get("ranges") and (s["ranges"].get("K-5") or s["ranges"].get("6-8"))]
    _, kdist = school_grounds.nearest([(s["lon"], s["lat"]) for s in k8], [r["lo"] for r in rows], [r["la"] for r in rows], 5280)
    for r, dd in zip(rows, kdist):
        r["ftK8"] = float(dd) if dd == dd else 1e9
    X = intersections()
    _, xdist = school_grounds.nearest([(s["lon"], s["lat"]) for s in k8], [x[0] for x in X], [x[1] for x in X], NEAR_FT + 100)
    # Each reach treats the main street intersections within it, and credits the kids hurt within it, within X_NEAR_FT
    # of one of them, on a main street or a street not matched. Kids hurt where both streets are residential are
    # calming's.
    import numpy as np
    from scipy.spatial import cKDTree
    lo0, la0 = X[0][0], X[0][1]
    fxy = lambda lo, la: ((lo - lo0) * school_grounds.FT_LON, (la - la0) * school_grounds.FT_LAT)
    rxy = np.array([fxy(r["lo"], r["la"]) for r in rows])
    for f in UPGRADE_FT:
        tp = [fxy(x[0], x[1]) for x, d in zip(X, xdist) if x[2] and d == d and d <= f]
        dx, _ = cKDTree(np.array(tp)).query(rxy, distance_upper_bound=X_NEAR_FT + 1)
        for r, d in zip(rows, dx):
            r.setdefault("x", {})[f] = bool(r["ftK8"] <= f and r["street"] != 1 and d <= X_NEAR_FT)
    n = len(rows)
    grid = [[sum(1 for r in rows if r["street"] == i and r["band"] == j) for j in range(3)] for i in range(3)]
    near = [r for r in rows if r["band"] < 2]
    wb = [r for r in near if r["mode"] in ("Walking", "Biking")]
    zone = [r for r in rows if r["band"] == 0]
    S = json.load(open(SUMMARY))["city"]["600ft"]
    bell_n, bell_d = sum(r["bell"] for r in near), len(near)
    model = {"base": n, "years": len(YEARS), "near": len(near), "walkBike": len(wb),
             "lastBlock": sum(1 for r in wb if r["ft"] <= LAST_BLOCK_FT), "zone": len(zone),
             "zoneKidsYear": round(len(zone) / len(YEARS), 2), "zoneHours": round(sum(r["hours"] for r in zone) / max(1, len(zone)), 3),
             "bellN": bell_n, "bellD": bell_d,
             # The near kids by the street they were hurt on: main, residential, not matched (Bryan, 2026-10-14: "If high
             # injury schools are beside main streets then reducing school traffic won't reduce traffic that much on the
             # Main Street").
             "nearByStreet": [sum(1 for r in near if r["street"] == i) for i in range(3)],
             # Safety upgrades' three reaches (Bryan, 2026-10-13: "1 block from school, within 1/8 mi, and within 1/4 mi"):
             # the kids walking or biking hurt within each, all streets and at a main street.
             "walkBikeWithin": {str(f): {"all": sum(1 for r in wb if r["ft"] <= f), "main": sum(1 for r in wb if r["ft"] <= f and r["street"] == 0)}
                                for f in UPGRADE_FT}, "zoneFt": ZONE_FT,
             # Each reach: the kids hurt within it by how they travelled, and its street intersections (Bryan, 2026-10-13:
             # "Offer three levels. One block from school, two blocks from school and quarter mile. And model injuries
             # prevented on bikes, walking and cars").
             # Counted at TK-8 schools, and split into school-travel hours (7 to 9 am and 2 to 5 pm), the hours
             # the studies measured, and the rest of the school day.
             # Only main street intersections are treated (Bryan, 2026-10-15: "Keep all intersections on big enough roads
             # to be a problem"), and only the kids hurt near them are credited. allModes counts every kid hurt within
             # the reach, and intersectionsAll every named crossing, the count the $200,000 one-block price was set on.
             "reach": {str(f): {"modes": {m: sum(1 for r in rows if r["x"][f] and r["mode"] == m) for m in sorted(set(MODES.values()))},
                                "hours": {m: sum(1 for r in rows if r["x"][f] and r["mode"] == m and r["hours"]) for m in sorted(set(MODES.values()))},
                                "allModes": {m: sum(1 for r in rows if r["ftK8"] <= f and r["mode"] == m) for m in sorted(set(MODES.values()))},
                                "intersections": sum(1 for x, d in zip(X, xdist) if x[2] and d == d and d <= f),
                                "intersectionsAll": sum(1 for d in xdist if d == d and d <= f)} for f in UPGRADE_FT},
             "xNearFt": X_NEAR_FT, "k8Schools": len(k8), "nearFt": NEAR_FT, "lastBlockFt": LAST_BLOCK_FT}
    mode_n = collections.Counter(r["mode"] for r in rows)
    out = {
        "note": "Written by tools/school-trips/school-kids-hurt.py. Kids 5 to 18 injured or killed on SF weekdays, 6 am to 6 pm, August "
                "to May, school years %s to %s, from DataSF nwes-mmgh. Distances run to the nearest grounds of the tool's %d schools, "
                "measured from the edge of the grounds as California's school-zone law measures it." % (YEARS[0], YEARS[-1], len(sch)),
        "source": V.tag,
        "byDistance": {"what": "Kids aged 5 to 18 hurt on SF weekdays, 6 am to 6 pm, August to May, school years %s to %s, by street type and "
                               "distance from the crash to the nearest school's grounds" % (YEARS[0], YEARS[-1]),
                       "years": len(YEARS), "noLocation": no_loc, "bands": BANDS, "streets": STREETS, "grid": grid,
                       "rows": [{"band": BANDS[j], "n": sum(grid[i][j] for i in range(3))} for j in range(3)]},
        "byMode": {"what": "The same kids, by how they were travelling", "years": len(YEARS),
                   "rows": [{"mode": m, "n": c} for m, c in sorted(mode_n.items(), key=lambda x: (-x[1], x[0]))]},
        "bellRate": {"what": "Crashes hurting a child walking or biking within 600 ft of a school's grounds, per 1,000 hours, on "
                             "school days 2022-23 to 2025-26 at %d schools. Bell hours run from 45 minutes before the start bell to "
                             "15 after, and 15 minutes before the end bell to 45 after, at each school's own SFUSD bell times "
                             "(8:15 am and 3:15 pm where SFUSD lists none). Counts are summed over schools, so a crash near two "
                             "schools counts twice." % S["schools"],
                     "source": "out/school-hour-crashes/summary.json, city.600ft, written by tools/school-trips/school-hour-crashes.py",
                     "rows": [{"when": "Bell hours", "per1000h": S["child_ped_bike_per_1000h_window"], "n": bell_n, "hours": S["hours"]["window"]},
                              {"when": "Other daytime", "per1000h": S["child_ped_bike_per_1000h_other_daytime"],
                               "n": S["other_daytime_child_ped_bike"], "hours": S["hours"]["other_daytime"]},
                              {"when": "Bell hours, no school", "per1000h": S["child_ped_bike_per_1000h_window_no_school"],
                               "n": S["window_no_school_child_ped_bike"], "hours": S["hours"]["window_no_school"]}],
                     "vsCityClock": S["child_window_vs_city_clock"]},
        "model": model,
    }
    # Quality: a plausible base, the grid sums to it, the shares are shares.
    assert 300 < n < 700, "%d kids in four years: the read is off" % n
    assert sum(map(sum, grid)) == n and sum(mode_n.values()) == n
    assert 0 < model["lastBlock"] <= model["walkBike"] <= model["near"] <= n and 0 < model["zone"] <= model["near"]
    assert 0 < bell_n < bell_d and len(sb) == len(sch)
    rc = [model["reach"][str(f)] for f in UPGRADE_FT]
    assert all(a["intersections"] < b["intersections"] and all(a["modes"][m] <= b["modes"][m] for m in a["modes"]) for a, b in zip(rc, rc[1:]))
    # Each school's own intersections, by its own distance, so one near two schools shows at both.
    import numpy as np
    xl, xa, xm = np.array([x[0] for x in X]), np.array([x[1] for x in X]), np.array([x[2] for x in X])
    cross, cross_all = {}, {}
    for s in sch:
        box = np.hypot((xl - s["lon"]) * school_grounds.FT_LON, (xa - s["lat"]) * school_grounds.FT_LAT) <= NEAR_FT + 5280
        d = np.full(xl.shape, np.inf)
        d[box] = school_grounds.dist_ft(s["lon"], s["lat"], xl[box], xa[box])
        cross[s["cds"]] = [[round(float(xl[i]), 5), round(float(xa[i]), 5), next(k for k, f in enumerate(UPGRADE_FT) if d[i] <= f)]
                           for i in np.flatnonzero((d <= NEAR_FT) & xm)]
        cross_all[s["cds"]] = int(np.sum(d <= UPGRADE_FT[0]))
    assert len(cross) == len(sch) and sum(map(len, cross.values())) >= model["reach"]["1320"]["intersections"]
    # Each school's own kids hurt, for plans that fund one school at a time: inside its 500 ft zone in the hours the
    # school zone limit applies (nearest of all schools, as the speed limit signs go to every school), and within each
    # reach of a TK-8 school by how they travelled, [in school-travel hours, all] (nearest TK-8 school).
    k8set = {s["cds"] for s in k8}
    zj, _ = school_grounds.nearest([(s["lon"], s["lat"]) for s in sch], [r["lo"] for r in rows], [r["la"] for r in rows], ZONE_FT)
    kj, _ = school_grounds.nearest([(s["lon"], s["lat"]) for s in k8], [r["lo"] for r in rows], [r["la"] for r in rows], NEAR_FT)
    sk = {s["cds"]: {"zone": 0} for s in sch}
    for r, j in zip(rows, zj):
        if j >= 0 and r["band"] == 0 and r["hours"]:
            sk[sch[j]["cds"]]["zone"] += 1
    for r, j in zip(rows, kj):
        if j < 0:
            continue
        d = sk[k8[j]["cds"]].setdefault("reach", {str(f): {} for f in UPGRADE_FT})
        for f in UPGRADE_FT:
            if r["x"][f]:
                hn = d[str(f)].setdefault(r["mode"], [0, 0])
                hn[0] += int(r["hours"])
                hn[1] += 1
    for cds in k8set:
        sk[cds].setdefault("reach", {str(f): {} for f in UPGRADE_FT})
    model["schoolKids"] = sk
    model["speed"] = speed_kids(rows)
    model["bikeways"] = bikeway_kids(rows)
    for f in UPGRADE_FT:
        assert sum(sum(v[1] for v in x["reach"][str(f)].values()) for x in sk.values() if "reach" in x) == sum(model["reach"][str(f)]["modes"].values())
    # Each TK-8 school's own intersections within each reach, so the school view prices its own upgrades.
    model["k8Counts"] = {s["cds"]: [sum(1 for x in cross[s["cds"]] if x[2] <= k) for k in range(len(UPGRADE_FT))] for s in k8}
    # The average TK-8 school's one-block count of every named crossing, the base the $200,000 a school is priced on,
    # so a reach's price scales with the main street intersections it treats.
    model["k8OneBlockAll"] = round(sum(cross_all[s["cds"]] for s in k8) / len(k8), 3)
    k8n = [len(cross[s["cds"]]) for s in k8]
    # A school among residential streets can have no main street crossing within a quarter mile.
    assert sum(1 for x in k8n if x == 0) <= 3 and sorted(k8n)[len(k8n) // 2] < 120, "TK-8 schools' quarter-mile main street intersections look off: %s" % sorted(k8n)
    with open(CROSS_OUT, "w") as f:
        json.dump({"note": "Written by tools/school-trips/school-kids-hurt.py. For each school's cds, the street intersections within a "
                           "quarter mile of its grounds as [lon, lat, reach], reach 0 within %d ft, 1 within %d ft, 2 within %d ft, "
                           "from OpenStreetMap's drive network." % UPGRADE_FT, "reachFt": list(UPGRADE_FT), "schools": cross},
                  f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("school-kids-hurt: %d kids (%d no location); near %d, walk/bike near %d, last block %d, zone %d (%.0f%% in school-zone hours); bell %d of %d"
          % (n, no_loc, len(near), len(wb), model["lastBlock"], len(zone), 100 * model["zoneHours"], bell_n, bell_d))
    for i, s in enumerate(STREETS):
        print("  %-20s %s" % (s, grid[i]))
    print("  modes", dict(mode_n))
    for f in UPGRADE_FT:
        R = model["reach"][str(f)]
        print("  within %4d ft: credited %s, %d main street intersections of %d" % (f, R["modes"], R["intersections"], R["intersectionsAll"]))
    for k, v in model["speed"].items():
        print("  %s: %s kids in %d years, at %d schools" % (k, v["total"], len(YEARS), len(v["kids"])))
    for k, v in model["bikeways"].items():
        print("  bikeways $%sM calmed blocks: %s kids in %d years" % (k, v, len(YEARS)))


if __name__ == "__main__":
    main()
