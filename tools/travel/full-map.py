#!/usr/bin/env python3
"""The full access map's per-block table: how often Muni comes near each census block, how far its stops are, and the minutes to the nearest school, library, grocery, park, major park and commercial district on foot, on low-stress bike routes, by Muni and by car.

    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map.py           # out/full-map/blocks.json and summary.json
    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map.py --check   # the checks on the output on disk

Bryan's question, from his public comment: "Has anyone
mapped out in other parts of the city how often does muni come? How far away
is the nearest stop? How easy is it to get to commercial district, nearest
park, major park, grocery store, school, library by transit, walking, biking
or driving? Are the routes low stress enough?" His goals: transport within
about 5 minutes, daily trips under 30 minutes and ideally under 15, kids able
to travel alone, trips low stress.

INPUTS, all built by other steps; this one fetches nothing.
  out/full-map/muni-stops.json   scheduled departures per hour at every stop
                                 (tools/muni/muni-frequency.py, SFMTA's GTFS).
  data/full-map/destinations.json  every destination's points
                                 (tools/travel/full-map-destinations.py).
  out/full-map/bike/access.json  walk and low-stress bike minutes to each
                                 type's nearest point (tools/travel/access-time.py
                                 --dests ... --rule protected --nets today --k 1).
  out/full-map/transit.json      Muni minutes (tools/travel/full-map-transit.py, on
                                 a sim VM). Optional: without it, the transit
                                 columns are null and the summary says so.
  out/full-map/transit-tthird.json  the same run on the faster T Third
                                 scenario feed (scripts/full-map-gtfs-tthird.py,
                                 TTHIRD=1 on the VM). Optional: summary.json's
                                 scenarios.tthird, beside the base map.
  data/extract/census-zcta/sf-2020.json  ZIP areas, to say where a scenario's
                                 gains fall.
  data/osm-cache/sf-drive.json   OpenStreetMap's drivable streets
                                 (tools/travel/osm-drive-network.py).

THE MEASURES, per populated 2020 census block, residents from the 2020 DHC.
  stops     walking distance in feet, along lib/walknet.py's network from
            the block's street frontage, to the nearest Muni stop with any
            service on the day, and to the nearest where one route departs
            every 10 minutes or better and every 5 minutes or better in the
            morning peak (7 to 9 AM; 6 and 12 departures an hour), then the
            same two with every route at the stop counted together. Whole
            feet, rounded to nearest, except that a stop past a quarter mile
            never shows as 1,320 or less: 1,320.3 ft is written 1,321, so the
            feet agree with the headway below, which compares the metres.
  headway   the best headway, in minutes, at any stop within a quarter mile
            (1,320 ft) on foot, in each of SFMTA's periods: the busiest single
            route there first, then every route at the stop together. Null
            when no stop that close has service then.
  One route is the default wherever "Muni every 5 minutes" is counted:
  Bryan, 2026-10-23, "One route" (docs/decisions/access-map.md).
  All routes together stays as a secondary field.
  walk      minutes on foot at 2 mph to the type's nearest point, from
            access-time's walk list (exact; listed to 9 km).
  bike      minutes riding only School Trips' all-ages network (Class I paths,
            Class IV separated lanes and Slow Streets) at 10 mph and walking
            the bike at 2 mph everywhere else, the route at most 25% longer
            than the shortest walk: access-time's "today" list under --rule
            protected. Listed only to 30 minutes; null past it. This is the
            low-stress (LTS 1) measure; tools/travel/full-map-lts.py checks the
            network against a published LTS method.
  transit   "Muni or walking, whichever is faster": door-to-door minutes on
            SFMTA's late-August 2026 schedule (the feed's calendar runs
            2026-07-23 to 2026-08-28), the median over 8:00 to 8:59 AM
            departures on 2026-08-26 (full-map-transit.py), or the walk column
            when walking is faster (muni()). R5 reports whole minutes rounded
            down, so walking wins when it is under R5's minute plus one. Null
            past 60 minutes.
  car       minutes by car: the shortest drive along OpenStreetMap's drivable
            streets (every street two-way; one-way streets and turns not
            modelled), with School Trips' car rule (tools/school-trips/school-sim.py):
            SFCTA's 13.4 mph morning median, the moving time re-timed as
            CAR_GOOGLE_A + CAR_GOOGLE_B x it to match Google Routes at the
            school bell, plus CAR_FIXED_MIN (3 minutes) for parking and the
            walk in. The block and the destination join the drive network at
            their nearest drivable node, the straight gap driven.

Every walk, bike and transit time starts at the block's street frontage,
the nearest of the points where its outline joins the walk network, so the
minutes from a large block are measured from its edge, not its middle.

SUMMARY. For each type and mode, the share of residents within 15 and 30
minutes, and the residents counted; per type, the residents for whom Muni
beats walking and gets them there within 15 and 30 minutes; the share within
a quarter mile of a stop with 5-minute and 10-minute service in each period.
Counts of people come first (Bryan, 2026-10-08).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import importlib.util
import json
import math
import os
import sys

# The orchestrator's interpreter, which has no numpy, imports this file only for checks(); the
# analysis virtualenv runs the build (pipeline/venv-step.py).
try:
    import numpy
except ImportError:
    numpy = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
from lib.quality import Each, Join, Table, read_json, run  # noqa: E402
from lib.full_map_dests import points_sha  # noqa: E402


def _load(name, file):
    return paths.load(file, name)


M = SIM = rcsp = None


def load_models():
    """school-travel-time.py (the walk network and its searches), school-sim.py (the car rule) and the compiled searches."""
    global M, SIM, rcsp
    from lib import rcsp as _rcsp
    rcsp = _rcsp
    M = _load("school_travel_time", "school-travel-time.py")
    SIM = _load("school_sim", "school-sim.py")

OUT = os.path.join(ROOT, "out", "full-map")
BIKE_REL = "out/full-map/bike/access.json"
FURTH_REL = "out/full-map/bike-furth1/access.json"
STOPS_REL = "out/full-map/muni-stops.json"
DEST_REL = "data/full-map/destinations.json"
TRANSIT_REL = "out/full-map/transit.json"
# Scenarios: a second Muni run on a modified feed, reported beside the base map, never in place of it.
SCENARIOS = {"tthird": {"file": "out/full-map/transit-tthird.json",
                        "label": "T Third every 5 minutes, Sunnydale to Chinatown in about 35 minutes (assumed)",
                        "ruling": "Bryan, 2026-10-23: \"Add it\" (docs/decisions/access-map.md)"}}
ZCTA_REL = "data/extract/census-zcta/sf-2020.json"
ORIGINS_REL = "data/full-map/transit-origins.json"
TRANSIT_MAX_MIN = 60
BLOCKS_REL = "out/full-map/blocks.json"
SUMMARY_REL = "out/full-map/summary.json"
FT = 0.3048
QUARTER_MILE_FT = 1320
QUARTER_MILE_M = QUARTER_MILE_FT * FT
STOP_CUTOFF_M = 5000.0
TPH_5, TPH_10 = 12.0, 6.0
TARGETS_MIN = (15, 30)
PERIODS = ("am", "midday", "evening")
MODES = ("walk", "bike", "transit", "car")
MODE_LABELS = {"walk": "Walking", "bike": "Low-stress bike", "transit": "Muni or walking, whichever is faster",
               "car": "Car"}
LAT0 = math.radians(37.76)
R = 6371008.8


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * R, math.radians(lat) * R)


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return json.load(f)


# -- stops -------------------------------------------------------------------------

def stop_seeds(net, stops):
    """Per stop, its joins to the walk network: arrays (node, metres to it, stop index)."""
    nodes, ds, owner = [], [], []
    for si, s in enumerate(stops):
        for node, c, along, _e in net.ends(s["lon"], s["lat"]):
            nodes.append(node)
            ds.append(c + along)
            owner.append(si)
    return numpy.array(nodes, dtype=numpy.int64), numpy.array(ds), numpy.array(owner, dtype=numpy.int64)


def nearest_walk(net, blocks, seeds, keep):
    """Walking metres from each block to the nearest stop with keep[stop]; inf past STOP_CUTOFF_M."""
    nodes, ds, owner = seeds
    m = keep[owner]
    dist = net.fast.walk(nodes[m].tolist(), ds[m].tolist(), STOP_CUTOFF_M)
    w = M.block_walks(dist, blocks)
    out = numpy.full(len(blocks), numpy.inf)
    for bi, v in w.items():
        out[bi] = v
    return out


def best_within(net, blocks, seeds, tph, route_tph):
    """Per block and period, the most departures an hour at any stop within a quarter mile on foot."""
    nodes, ds, owner = seeds
    n = len(blocks)
    best = {p: numpy.zeros(n) for p in PERIODS}
    best_r = {p: numpy.zeros(n) for p in PERIODS}
    for bi, b in enumerate(blocks):
        if not b["ends"]:
            continue
        dist = net.fast.walk([e[0] for e in b["ends"]], [e[1] + e[2] for e in b["ends"]], QUARTER_MILE_M)
        v = dist[nodes] + ds
        near = numpy.unique(owner[v <= QUARTER_MILE_M])
        if not len(near):
            continue
        for p in PERIODS:
            best[p][bi] = tph[p][near].max()
            best_r[p][bi] = route_tph[p][near].max()
    return best, best_r


# -- car ---------------------------------------------------------------------------

def drive_graph():
    """OpenStreetMap's drivable streets as an undirected scipy graph, its largest connected piece, and a node index."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    blob = json.load(open(SIM.DRIVE_CACHE))
    coords, ways = {}, []
    for e in blob["elements"]:
        if e["type"] == "node":
            coords[e["id"]] = (e["lon"], e["lat"])
        elif e["type"] == "way" and e.get("tags", {}).get("highway") in SIM.DRIVE_HW:
            ways.append(e)
    idx, X, Y, us, vs, ls = {}, [], [], [], [], []
    for w in ways:
        prev = None
        for nd in w.get("nodes", ()):
            if nd not in coords:
                continue
            if nd not in idx:
                idx[nd] = len(X)
                x, y = xy(*coords[nd])
                X.append(x)
                Y.append(y)
            i = idx[nd]
            if prev is not None and prev != i:
                us.append(prev)
                vs.append(i)
                ls.append(math.hypot(X[i] - X[prev], Y[i] - Y[prev]))
            prev = i
    n = len(X)
    A = coo_matrix((ls + ls, (us + vs, vs + us)), shape=(n, n)).tocsr()
    _k, lab = connected_components(A, directed=False)
    big = numpy.bincount(lab).argmax()
    keep = numpy.flatnonzero(lab == big)
    pts = numpy.column_stack([numpy.array(X)[keep], numpy.array(Y)[keep]])
    return {"A": A, "keep": keep, "tree": cKDTree(pts), "pts": pts, "osm_base": blob.get("osm3s", {}).get("timestamp_osm_base"),
            "nodes": n, "edges": len(us)}


def car_minutes(metres):
    moving = metres / 1609.344 / SIM.CAR_MPH * 60.0
    return SIM.CAR_FIXED_MIN + SIM.CAR_GOOGLE_A + SIM.CAR_GOOGLE_B * moving


def car_times(D, block_pts, dest_pts):
    """Minutes by car from each block to its nearest destination point."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    dd, di = D["tree"].query(dest_pts)
    nodes = D["keep"][di]
    # One search from a virtual source joined to every destination's node at its connector's length, so each
    # destination starts at the gap it is driven to its node, not at 0. Several on one node keep the shortest.
    best = {}
    for nd, c in zip(nodes.tolist(), dd.tolist()):
        if c < best.get(nd, numpy.inf):
            best[nd] = c
    n = D["A"].shape[0]
    src_n = sorted(best)
    # A connector of exactly 0 is stored as a tiny weight, since a sparse matrix drops explicit zeros.
    w = [max(best[x], 1e-9) for x in src_n]
    S = coo_matrix((w, ([n] * len(src_n), src_n)), shape=(n + 1, n + 1)).tocsr()
    A = D["A"].tocoo()
    G = coo_matrix((A.data, (A.row, A.col)), shape=(n + 1, n + 1)).tocsr() + S
    dist = dijkstra(G, directed=True, indices=n)[:n]
    bd, bi = D["tree"].query(block_pts)
    m = dist[D["keep"][bi]] + bd
    return numpy.array([car_minutes(x) if numpy.isfinite(x) else numpy.inf for x in m])


# -- build -------------------------------------------------------------------------

def file_sha(root, rel):
    """The first 16 hex of a file's SHA-256, as tools/travel/full-map-transit.py records it; None when it is missing."""
    import hashlib
    try:
        with open(os.path.join(root, rel), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except FileNotFoundError:
        return None


def dest_sha(root):
    """The destinations' points fingerprint (lib/full_map_dests.py), as full-map-transit.py records it."""
    with open(os.path.join(root, DEST_REL)) as f:
        return points_sha(json.load(f))


def transit_mismatch(tr, geoids, types, sha, origins_sha=None):
    """Why a transit.json can't be merged into this build, or None: it must be a full run (not --sample) over the
    same blocks in the same order, the same destination types by name, the same destinations file, and the same
    frontage origins (data/full-map/transit-origins.json)."""
    if tr["parameters"].get("sample"):
        return "a --sample %s run" % tr["parameters"]["sample"]
    if "sample" not in tr["parameters"]:
        return "no sample field, so it may be a sample run"
    if len(tr.get("walk_only", {}).get("minutes", [])) != len(tr["blocks"]):
        return "no walk_only minutes, so a Muni trip can't be told from R5's walk"
    got = [g for g, _m in tr["blocks"]]
    if got != geoids:
        return "%d blocks against this build's %d, or in another order" % (len(got), len(geoids))
    if list(tr["types"]) != list(types):
        return "types %s against %s" % (tr["types"], types)
    if tr["inputs"].get("destinations_points_sha256") != sha:
        return "destination points %s against the current file's %s" % (tr["inputs"].get("destinations_points_sha256"), sha)
    if origins_sha is None or tr["inputs"].get("origins_sha256") != origins_sha:
        return "origins %s against %s's %s" % (tr["inputs"].get("origins_sha256"), ORIGINS_REL, origins_sha)
    return None


def cell(v):
    return None if v is None or not numpy.isfinite(v) else round(float(v), 1)


def feet(m):
    """Whole feet from metres, on the same side of a quarter mile as the metres are.

    best_within() counts a stop as within a quarter mile when its metres are <= QUARTER_MILE_M. Rounding to the
    nearest foot alone would write a stop at 1,320.3 ft as 1,320, which reads as within; it is written 1,321."""
    if not math.isfinite(m):
        return None
    ft = int(round(m / FT))
    return max(ft, QUARTER_MILE_FT + 1) if m > QUARTER_MILE_M else min(ft, QUARTER_MILE_FT)


def first(lst):
    return lst[0][0] if lst else None


def muni(r5, walk, r5_walk=None):
    """The transit minutes shown, "Muni or walking, whichever is faster": R5's time, or this repo's walk time when
    that is faster. R5 walks OSM's network, not walknet.py's, so its walk-only option is not quite this map's walk;
    a rider who can walk there in less time than Muni takes walks. R5 floors to whole minutes (an 8 means 8.0 to
    8.99) and the walk is to 0.1 minute, so walking wins when it is under r5 + 1. An R5 time of 0 is a snap
    artefact (the origin and destination on one street segment) and falls back to the walk. An R5 time no faster
    than R5's own walk-only time (r5_walk) is a walk, not a Muni trip, so it falls back to the walk column too."""
    if r5 == 0 or (r5 is not None and r5_walk is not None and r5 >= r5_walk):
        r5 = None
    if walk is not None and walk <= TRANSIT_MAX_MIN and (r5 is None or walk < r5 + 1):
        return walk
    return r5


def muni_beats_walk(tr, walk):
    """True when the shown transit minutes came from Muni: present, and faster than walking (or no walk listed)."""
    return tr is not None and (walk is None or tr < walk)


def build():
    load_models()
    if not rcsp.available():
        raise SystemExit("full-map.py needs the compiled searches (a C compiler): %s" % rcsp._err)
    M.FAST["on"] = True
    net = M.Net(cache=True)
    bike = read(BIKE_REL)
    if bike["parameters"].get("rule") != "protected" or bike["k"] != 1:
        raise SystemExit("%s is not a --rule protected --k 1 run" % BIKE_REL)
    stops_blob = read(STOPS_REL)
    cols = stops_blob["columns"]
    stops = [dict(zip(cols, s)) for s in stops_blob["stops"]]
    dests = read(DEST_REL)
    types = sorted(dests["types"])
    pts = {r["geoid"]: r for r in read("data/extract/census-blocks/2020.json")["records"]}
    blocks = []
    for b in bike["blocks"]:
        p = pts[b["geoid"]]
        blocks.append({"geoid": b["geoid"], "pop": b["pop"], "lon": p["lon"], "lat": p["lat"],
                       "ends": net.ends(p["lon"], p["lat"])})
    seeds = stop_seeds(net, stops)
    tph = {p: numpy.array([s["tph"][p] for s in stops]) for p in PERIODS}
    rtph = {p: numpy.array([s["route_tph"][p] for s in stops]) for p in PERIODS}
    any_stop = nearest_walk(net, blocks, seeds, numpy.ones(len(stops), dtype=bool))
    s10 = nearest_walk(net, blocks, seeds, rtph["am"] >= TPH_10)
    s5 = nearest_walk(net, blocks, seeds, rtph["am"] >= TPH_5)
    s10_all = nearest_walk(net, blocks, seeds, tph["am"] >= TPH_10)
    s5_all = nearest_walk(net, blocks, seeds, tph["am"] >= TPH_5)
    best, best_r = best_within(net, blocks, seeds, tph, rtph)

    D = drive_graph()
    bxy = numpy.array([xy(b["lon"], b["lat"]) for b in blocks])
    car = {t: car_times(D, bxy, numpy.array([xy(x, y) for x, y, _f in dests["types"][t]["points"]])) for t in types}

    def load_transit(rel):
        """{geoid: {type: (r5 minutes, r5 walk-only minutes)}} and the run's metadata, or ({}, None)."""
        if not os.path.exists(os.path.join(ROOT, rel)):
            return {}, None
        tr = read(rel)
        problem = transit_mismatch(tr, [b["geoid"] for b in blocks], types, dest_sha(ROOT), file_sha(ROOT, ORIGINS_REL))
        if problem:
            raise SystemExit("%s does not belong to this build: %s. Rerun scripts/full-map-transit-vm.sh on the "
                             "current destinations and blocks, or remove the file." % (rel, problem))
        meta = {"label": MODE_LABELS["transit"], "note": tr["note"], "parameters": tr["parameters"],
                "inputs": tr["inputs"], "blocks": len(tr["blocks"]),
                "missing_origins": [m["geoid"] for m in tr["missing_origins"]]}
        if tr.get("scenario"):
            meta["scenario"] = tr["scenario"]
        got = {}
        for (g, mins), wo in zip(tr["blocks"], tr["walk_only"]["minutes"]):
            got[g] = {t: (m, w) for t, m, w in zip(tr["types"], mins, wo)}
        return got, meta

    transit, tmeta = load_transit(TRANSIT_REL)
    scen = {}
    if transit:
        for name, sc in SCENARIOS.items():
            got, meta = load_transit(sc["file"])
            if got:
                problem = scenario_base_mismatch(read(sc["file"]), read(TRANSIT_REL), name)
                if problem:
                    raise SystemExit("%s: %s. Rerun the VM job with TTHIRD=1, or remove the file." % (sc["file"], problem))
                scen[name] = (got, meta)

    def headway(v):
        return round(60.0 / v, 1) if v > 0 else None

    rows = []
    for bi, b in enumerate(blocks):
        acc = bike["blocks"][bi]["access"]
        t = transit.get(b["geoid"], {})
        rows.append([
            b["geoid"], b["pop"],
            [feet(any_stop[bi]), feet(s10[bi]), feet(s5[bi]), feet(s10_all[bi]), feet(s5_all[bi])],
            {p: [headway(best_r[p][bi]), headway(best[p][bi])] for p in PERIODS},
            {ty: [first(acc[ty]["walk"]), first(acc[ty]["today"]),
                  muni(t.get(ty, (None, None))[0], first(acc[ty]["walk"]), t.get(ty, (None, None))[1]) if transit else None, cell(car[ty][bi])] for ty in types},
        ])
    out = {
        "note": "Per populated 2020 census block: walking feet to the nearest Muni stop, the nearest with 10-minute "
                "and 5-minute morning service; the best headway within a quarter mile on foot by period; and "
                "minutes to each destination type's nearest point by mode. See scripts/full-map.py.",
        "columns": ["geoid", "pop", "stop_ft", "headway_min", "minutes"],
        "stop_ft": ["any", "every_10_min_am", "every_5_min_am", "every_10_min_am_all_routes",
                    "every_5_min_am_all_routes"],
        "stop_ft_note": "every_N_min_am: one route at the stop departs every N minutes or better from 7 to 9 AM "
                        "(Bryan, 2026-10-23: \"One route\"); _all_routes: every route at the stop "
                        "counted together.",
        "headway_min": {"periods": stops_blob["periods"], "values": ["busiest_route", "all_routes"]},
        "minutes": {"types": types, "modes": list(MODES), "labels": MODE_LABELS,
                    "values": "[walk, bike, transit, car] minutes; walk, bike and transit from the block's street "
                              "frontage, car from the drivable node nearest its interior point; transit is Muni or "
                              "walking, whichever is faster%s; null where none is listed (walk past 9 km, bike past "
                              "30 minutes, transit past 60 minutes or not run)" % schedule_text(tmeta)},
        "sources": {
            "stops": {"file": STOPS_REL, "feed": stops_blob["feed"], "notice": stops_blob["notice"]},
            "walk_bike": {"file": BIKE_REL, "parameters": bike["parameters"], "inputs": bike["inputs"]},
            "transit": tmeta or "not run yet: out/full-map/transit.json is missing (scripts/full-map-transit-vm.sh)",
            "car": {"network": "data/osm-cache/sf-drive.json", "osm_base": D["osm_base"], "mph": SIM.CAR_MPH,
                    "google_a": SIM.CAR_GOOGLE_A, "google_b": SIM.CAR_GOOGLE_B, "fixed_min": SIM.CAR_FIXED_MIN},
            "destinations": {t: {"source": dests["types"][t]["source"], "features": len(dests["types"][t]["features"]),
                                 "points": len(dests["types"][t]["points"])} for t in types},
        },
        "blocks": rows,
    }
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(os.path.join(ROOT, BLOCKS_REL), out, separators=(",", ":"))
    summary = summarise(out)
    if scen:
        summary["scenarios"] = {name: scenario_summary(name, out, got, meta, blocks, bike)
                                for name, (got, meta) in sorted(scen.items())}
    if os.path.exists(os.path.join(ROOT, FURTH_REL)):
        summary["bike_check_furth_lts1"] = furth_check(out, read(FURTH_REL))
    stable.write_json(os.path.join(ROOT, SUMMARY_REL), summary, indent=1)
    return out, summary


def schedule_text(tmeta):
    """', on SFMTA's late-August 2026 schedule (departures 2026-08-26 ...)' from transit.json's inputs; '' without it."""
    if not tmeta:
        return ""
    return ", on SFMTA's %s schedule (departures %s, 60-minute window)" % (
        tmeta["inputs"].get("schedule", "?"), tmeta["parameters"]["departure"])


def zip_of(blocks):
    """Each block's 2020 ZIP Code Tabulation Area, by its interior point (data/extract/census-zcta/sf-2020.json)."""
    import shapely
    from shapely.geometry import shape
    from shapely.prepared import prep
    zs = [(z, prep(shape(g))) for z, g in sorted(read(ZCTA_REL)["zctas"].items())]
    out = []
    for b in blocks:
        p = shapely.Point(b["lon"], b["lat"])
        out.append(next((z for z, g in zs if g.covers(p)), None))
    return out


def scenario_summary(name, out, got, meta, blocks, bike):
    """A scenario's shares within 15 and 30 minutes by type, and the residents and blocks it speeds up."""
    rows = out["blocks"]
    total = sum(r[1] for r in rows)
    types, modes = out["minutes"]["types"], out["minutes"]["modes"]
    ti = modes.index("transit")
    zips = zip_of(blocks)

    def share(n):
        return {"residents": n, "share": round(100.0 * n / total, 1)}

    within, gains, by_zip = {}, {}, {}
    for ty in types:
        new = []
        for bi, r in enumerate(rows):
            m, w5 = got[r[0]][ty]
            new.append(muni(m, first(bike["blocks"][bi]["access"][ty]["walk"]), w5))
        within[ty] = {"%d" % t: share(sum(r[1] for r, v in zip(rows, new) if v is not None and v <= t))
                      for t in TARGETS_MIN}
        g = {"faster": [0, 0], "slower": [0, 0], "newly_within_15": [0, 0], "newly_within_30": [0, 0]}
        for bi, (r, v) in enumerate(zip(rows, new)):
            old = r[4][ty][ti]
            faster = v is not None and (old is None or v < old)
            if faster:
                by_zip.setdefault(zips[bi], {}).setdefault(ty, [0, 0])
                by_zip[zips[bi]][ty][0] += r[1]
                by_zip[zips[bi]][ty][1] += 1
            for key, hit in (("faster", faster), ("slower", old is not None and (v is None or v > old)),
                             ("newly_within_15", v is not None and v <= 15 and (old is None or old > 15)),
                             ("newly_within_30", v is not None and v <= 30 and (old is None or old > 30))):
                if hit:
                    g[key][0] += r[1]
                    g[key][1] += 1
        gains[ty] = {k: {"residents": a, "blocks": b} for k, (a, b) in g.items()}
    zip_rows = {z: {ty: {"residents": a, "blocks": b} for ty, (a, b) in sorted(v.items())}
                for z, v in sorted(by_zip.items(), key=lambda kv: (kv[0] is None, kv[0] or ""))}
    sc = SCENARIOS[name]
    return {"label": sc["label"], "ruling": sc["ruling"], "file": sc["file"],
            "note": "Muni or walking, whichever is faster, with the scenario's feed in place of SFMTA's; every number "
                    "in assumptions is assumed, not measured. within: residents within N minutes. gains: per type, "
                    "residents and blocks whose time is lower than the base map's (faster), higher (slower), or newly "
                    "within 15 or 30 minutes. faster_by_zip: the faster residents and blocks per type by 2020 ZIP "
                    "Code Tabulation Area (by the block's interior point; null for the few blocks whose point falls in no "
                    "ZCTA).",
            "assumptions": ((meta.get("scenario") or {}).get("spec") or {}).get("assumptions"),
            "within": within, "gains": gains, "faster_by_zip": zip_rows}


def summarise(out):
    rows = out["blocks"]
    total = sum(r[1] for r in rows)
    types, modes = out["minutes"]["types"], out["minutes"]["modes"]
    within = {}
    for ty in types:
        within[ty] = {}
        for mi, mode in enumerate(modes):
            have = [r for r in rows if r[4][ty][mi] is not None]
            within[ty][mode] = {}
            if mode == "transit" and not any(r[4][ty][mi] is not None for r in rows):
                within[ty][mode] = None
                continue
            for target in TARGETS_MIN:
                n = sum(r[1] for r in have if r[4][ty][mi] <= target)
                within[ty][mode]["%d" % target] = {"residents": n, "share": round(100.0 * n / total, 1)}
    def within_headway(p, vi, cap):
        n = sum(r[1] for r in rows if r[3][p][vi] is not None and r[3][p][vi] <= cap + 1e-9)
        return {"residents": n, "share": round(100.0 * n / total, 1)}

    # One route first (Bryan, 2026-10-23: "One route"); every route together is the secondary field.
    freq = {p: {"5": within_headway(p, 0, 5.0), "10": within_headway(p, 0, 10.0),
                "all_routes": {"5": within_headway(p, 1, 5.0), "10": within_headway(p, 1, 10.0)}} for p in PERIODS}
    beats = None
    if any(r[4][ty][modes.index("transit")] is not None for r in rows for ty in types):
        ti, wi = modes.index("transit"), modes.index("walk")
        beats = {}
        for ty in types:
            won = [r for r in rows if muni_beats_walk(r[4][ty][ti], r[4][ty][wi])]
            beats[ty] = {"%d" % target: {"residents": n, "share": round(100.0 * n / total, 1)} for target, n in (
                (target, sum(r[1] for r in won if r[4][ty][ti] <= target)) for target in TARGETS_MIN)}
    n = sum(r[1] for r in rows if r[2][0] is not None and r[2][0] <= QUARTER_MILE_FT)
    stop = {"residents": n, "share": round(100.0 * n / total, 1)}
    return {"note": "Residents of populated 2020 census blocks. within: residents whose nearest destination of the "
                    "type is at most N minutes away by the mode (walk, bike and transit from the block's street "
                    "frontage); transit is Muni or walking, whichever is faster%s. "
                    "muni_beats_walking: residents for whom Muni is faster than walking to the type's nearest "
                    "point and gets them there in N minutes or less. muni_within_quarter_mile: residents with a stop "
                    "within 1,320 ft on foot where one route comes every N minutes or better in the period (Bryan, "
                    "2026-10-23: \"One route\"); its all_routes field counts every route at the stop together. "
                    "any_stop_within_quarter_mile: a stop with any service on the day." % schedule_text(
                        out["sources"]["transit"] if isinstance(out["sources"]["transit"], dict) else None),
            "residents": total, "blocks": len(rows),
            "transit": out["sources"]["transit"] if isinstance(out["sources"]["transit"], str) else "included",
            "mode_labels": MODE_LABELS, "within": within, "muni_beats_walking": beats,
            "muni_within_quarter_mile": freq, "any_stop_within_quarter_mile": stop}


def furth_check(out, furth):
    """The low-stress bike shares again with every edge Furth's tables rate LTS 1 ridden too (access-time --rule furth1)."""
    if furth["parameters"].get("rule") != "furth1":
        raise SystemExit("%s is not a --rule furth1 run" % FURTH_REL)
    total = sum(r[1] for r in out["blocks"])
    res = {"note": "Residents within N minutes riding School Trips' all-ages network plus every street and path "
                   "Mekuria, Furth and Nixon's tables rate LTS 1 from OSM tags (tools/travel/full-map-lts.py). A check on "
                   "the LTS 1 reading, not a figure of its own.", "within": {}}
    for ty in out["minutes"]["types"]:
        res["within"][ty] = {}
        for target in TARGETS_MIN:
            n = sum(b["pop"] for b in furth["blocks"] if b["access"][ty]["today"]
                    and b["access"][ty]["today"][0][0] <= target)
            res["within"][ty]["%d" % target] = {"residents": n, "share": round(100.0 * n / total, 1)}
    return res


# -- checks ------------------------------------------------------------------------

def checks(root=ROOT):
    def blocks(r):
        d = read_json(r, BLOCKS_REL)
        if d is None:
            return None
        return [{"geoid": b[0], "pop": b[1], "stop_ft": b[2], "headway": b[3], "minutes": b[4]} for b in d["blocks"]]

    def ordered(b):
        if len(b["stop_ft"]) != 5:
            return "%s: stop_ft has the old layout %s (rerun full-map.py)" % (b["geoid"], b["stop_ft"])
        a, s10, s5, s10a, s5a = b["stop_ft"]
        if a is None:
            return "%s: no stop within %d m" % (b["geoid"], STOP_CUTOFF_M)

        def worse(x, y):  # a stop meeting a stricter test can't be nearer than one meeting a looser one
            return x is not None and (y is None or x < y)
        # One route every N minutes is stricter than every route together; 5 is stricter than 10.
        if worse(s10, s10a) or worse(s5, s5a) or worse(s10a, a) or worse(s5, s10) or worse(s5a, s10a):
            return "%s: a better-served stop is nearer than a less-served one (%s)" % (b["geoid"], b["stop_ft"])
        return None

    def modes(b):
        bad = []
        for ty, (w, bk, tr, car) in b["minutes"].items():
            # Walk is null only when no point of the type lies within 9 km on foot (Treasure Island has no school,
            # branch or district it can walk to: the Bay Bridge has no path to the city). A car always arrives.
            if car is None:
                bad.append("%s missing car" % ty)
            # Riding can only beat or equal walking: the route may walk the whole way.
            if bk is not None and w is not None and bk > w + 0.11:
                bad.append("%s bike %s > walk %s" % (ty, bk, w))
            if tr is not None and not 0 <= tr <= TRANSIT_MAX_MIN:
                bad.append("%s transit %s" % (ty, tr))
            # The transit trip may walk the whole way, so it is never slower than walking.
            if tr is not None and w is not None and tr > w + 1e-9:
                bad.append("%s transit %s > walk %s" % (ty, tr, w))
            if car is not None and not 0 < car < 120:
                bad.append("%s car %s" % (ty, car))
        return ("%s: %s" % (b["geoid"], "; ".join(bad[:3]))) if bad else None

    def headways(b):
        bad = [p for p, (hr, h) in b["headway"].items() if (h is None) != (hr is None) or (h is not None and h > hr + 1e-9)]
        return ("%s: all-routes headway above the busiest route's in %s" % (b["geoid"], bad)) if bad else None

    return [
        Table("full-map-blocks", blocks, floor=5000, max_drop=0.02, key="geoid", required=["geoid", "pop", "minutes"]),
        Join("full-map-blocks~access", left=lambda r: None if blocks(r) is None else [b["geoid"] for b in blocks(r)],
             right=lambda r: None if read_json(r, BIKE_REL) is None else [b["geoid"] for b in read_json(r, BIKE_REL)["blocks"]]),
        Each("full-map-blocks/stops-ordered", blocks, ordered,
             "every block has a stop within 5 km, and a better-served stop is never nearer than the nearest stop"),
        Each("full-map-blocks/modes", blocks, modes, "car present, bike never slower than walk, times in range"),
        Each("full-map-blocks/headways", blocks, headways, "a stop's all-route headway never above its busiest route's"),
        Each("full-map-blocks/scenarios-match", scenario_state, lambda t: t["problem"],
             "each scenario's transit file, when present, is a full run over this build's blocks, types, "
             "destinations and origins, and summary.json reports it"),
        Each("full-map-blocks/transit-matches", transit_state, lambda t: t["problem"],
             "out/full-map/transit.json, when present, is a full run over this build's blocks, types and "
             "destinations, and blocks.json carries its minutes"),
    ]


def scenario_base_mismatch(tr, base, name):
    """Why a scenario run can't be compared with the base run, or None: it must name the scenario and be made from
    the base run's feed on the same OSM extract and departure."""
    sc = tr.get("scenario") or {}
    if sc.get("name") != name:
        return "it does not say it is the %s scenario" % name
    if sc.get("made_from_gtfs_sha256") != base["inputs"].get("gtfs_sha256"):
        return "made from GTFS %s, the base run read %s" % (sc.get("made_from_gtfs_sha256"), base["inputs"].get("gtfs_sha256"))
    for k in ("osm_timestamp",):
        if tr["inputs"].get(k) != base["inputs"].get(k):
            return "%s %s against the base run's %s" % (k, tr["inputs"].get(k), base["inputs"].get(k))
    if tr["parameters"].get("departure") != base["parameters"].get("departure"):
        return "departure %s against the base run's %s" % (tr["parameters"].get("departure"), base["parameters"].get("departure"))
    return None


def scenario_state(root):
    """One row per scenario file present: whether it fits this build and summary.json carries it."""
    out, summ = read_json(root, BLOCKS_REL), read_json(root, SUMMARY_REL)
    if out is None or summ is None:
        return None
    res = []
    for name, sc in sorted(SCENARIOS.items()):
        tr = read_json(root, sc["file"])
        if tr is None:
            continue
        problem = transit_mismatch(tr, [b[0] for b in out["blocks"]], out["minutes"]["types"], dest_sha(root),
                                   file_sha(root, ORIGINS_REL))
        base = read_json(root, TRANSIT_REL)
        if not problem:
            problem = "no base transit.json" if base is None else scenario_base_mismatch(tr, base, name)
        if not problem and name not in summ.get("scenarios", {}):
            problem = "summary.json has no %s scenario (rerun full-map.py)" % name
        res.append({"problem": problem})
    return res


def transit_state(root):
    """One row saying whether transit.json fits blocks.json and destinations.json; [] when there is no transit.json."""
    tr = read_json(root, TRANSIT_REL)
    out = read_json(root, BLOCKS_REL)
    if out is None:
        return None
    if tr is None:
        return []
    problem = transit_mismatch(tr, [b[0] for b in out["blocks"]], out["minutes"]["types"], dest_sha(root),
                               file_sha(root, ORIGINS_REL))
    if not problem:
        modes = out["minutes"]["modes"]
        ti, wi = modes.index("transit"), modes.index("walk")
        merged = {b[0]: b[4] for b in out["blocks"]}
        off = [g for (g, m), wo in zip(tr["blocks"], tr["walk_only"]["minutes"]) if g not in merged or any(
            merged[g][t][ti] != muni(v, merged[g][t][wi], w5) for t, v, w5 in zip(tr["types"], m, wo))]
        if off:
            problem = "blocks.json's transit minutes differ from transit.json at %d blocks (rerun full-map.py)" % len(off)
    return [{"problem": problem}]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        _out, s = build()
        print("  %d blocks, %d residents; transit: %s" % (s["blocks"], s["residents"], s["transit"]))
        for ty, by in s["within"].items():
            print("  %-11s within 15 min: %s" % (ty, ", ".join(
                "%s %s%%" % (m, v["15"]["share"]) for m, v in by.items() if v)))
        if s["muni_beats_walking"]:
            print("  Muni beats walking, within 15 / 30 min: %s" % ", ".join("%s %s / %s" % (
                ty, v["15"]["residents"], v["30"]["residents"]) for ty, v in s["muni_beats_walking"].items()))
        print("  Muni every 5 min within a quarter mile, one route: %s; all routes: %s" % (
            {p: v["5"]["share"] for p, v in s["muni_within_quarter_mile"].items()},
            {p: v["all_routes"]["5"]["share"] for p, v in s["muni_within_quarter_mile"].items()}))
    results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
