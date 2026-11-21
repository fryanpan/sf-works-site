#!/usr/bin/env python3
"""Door-to-door minutes by Muni or walking, whichever is faster, from every populated census block's street frontage to the nearest destination of each type, at a weekday 8 AM departure on SFMTA's late-August 2026 schedule, with r5py (Conveyal R5) on SFMTA's GTFS and OpenStreetMap.

    python tools/travel/full-map-transit.py --origins                                 # data/full-map/transit-origins.json (Mac, sf-works-geo venv)
    python tools/travel/full-map-transit.py --osm sf.osm.pbf --gtfs muni.zip          # out/full-map/transit.json (sim VM)
    python tools/travel/full-map-transit.py --osm sf.osm.pbf --gtfs muni.zip --sample 50 --out DIR
    python tools/travel/full-map-transit.py --check                                   # checks on the output on disk

Heavy: the matrix runs on a sim VM
(scripts/full-map-transit-vm.sh through scripts/sim-vm.py), never on the Mac.
The tool choice is in notes/full-map/2026-10-23-routing-tools.md.

ORIGINS. A block's walk minutes (tools/travel/access-time.py) are measured from
wherever its street frontage joins lib/walknet.py's network, the nearest
of every join, so a large block's minutes start at its edge, not its middle.
R5 starts from the same places: --origins writes, per block, the points where
it joins the walk network (school-travel-time.py's Net.ends(), the snap along
the census outline), thinned so no two kept points are closer than
ORIGIN_SPACING_M (60 m, 1.1 minutes on foot), into
data/full-map/transit-origins.json. A block with no join keeps its 2020
interior point. A block's time to a type is its fastest origin's. The file is
built on the Mac, where the walk network is, and committed for the VM.

THE TRIP. R5's travel time matrix, transit and walking (a walk-only route
counts when it is faster, as a rider would choose), from each origin to every
point in data/full-map/destinations.json, and the type's time is its fastest
point. Every point goes in, the 50 m edge samples included: thinning them to
one per 150 m cell put a point up to 100 m (2 minutes on foot) from the true
edge and made Muni slower than walking at 41% of blocks.
  * Schedule: SFMTA's GTFS zip, whose SHA-256 must match the one
    out/full-map/muni-stops.json was built from. That feed's calendar runs
    2026-07-23 to 2026-08-28, so the minutes are the late-August 2026
    schedule. The run records the fetch date and the calendar range, and
    stops unless R5's transit layer has service on the departure date
    (TransitLayer.covers): a date outside the feed gives a walk-only matrix
    that looks like a transit one.
  * Departure: DEPART_HHMM (8:00 AM) on the service day tools/muni/muni-frequency.py
    used (out/full-map/muni-stops.json feed.serviceDate, the last Wednesday in
    SFMTA's feed), over a WINDOW_MIN (60) minute window: R5 routes a departure
    every minute from 8:00 to 8:59 and reports the median, so the wait for the
    bus is counted as an average rider meets it, not at its best or worst.
  * Walking at WALK_MPH (2 mph), the pace the school and access models use
    (lib/school-travel-time.py, Bryan 2026-09-29: "assume walking ... at
    2mph"), for the walk to the stop, transfers and the walk from the stop.
  * Up to MAX_MIN (60) minutes door to door; a block with no trip that short
    gets null for the type. R5 reports whole minutes, rounded down.
R5 snaps each point to its own street network; its walk routes are OSM's,
read from the --osm extract, so they can differ a little from
lib/walknet.py's. R5 drops a point it cannot snap. A block is listed under
missing_origins when every one of its origins was dropped, or when R5 finds no
trip to a type the walk column reaches in MISSING_WALK_MIN (45) minutes or
less (a walk-only route would do); more than MAX_MISSING (5) fails the run.

Writes out/full-map/transit.json: parameters, the inputs' markers, the type
names, the missing origins, and per block [geoid, minutes per type] in the
types' order.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.quality import Each, Table, read_json, run  # noqa: E402
from lib.stable import write_json  # noqa: E402
from lib.full_map_dests import points_sha  # noqa: E402

OUT_REL = "out/full-map/transit.json"
DEST_REL = "data/full-map/destinations.json"
STOPS_REL = "out/full-map/muni-stops.json"
ORIGINS_REL = "data/full-map/transit-origins.json"
WALK_REL = "out/full-map/bike/access.json"
DEPART_HHMM = (8, 0)
WINDOW_MIN = 60
WALK_MPH = 2.0
MAX_MIN = 60
KMH_PER_MPH = 1.609344
ORIGIN_SPACING_M = 60.0
CHUNK = 250  # origins per matrix call: small enough to share out among workers, big enough to amortise
MAX_MISSING = 5
MISSING_WALK_MIN = 45.0
ROW_FLOOR = 5000
# Muni beats walking for a large share of blocks to the sparse types; a run where it does not is a walk-only run.
BEAT_TYPES = ("high", "library")
BEAT_SHARE = 0.20


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return json.load(f)


def blocks():
    """Populated 2020 blocks, as tools/travel/access-time.py lists them: [(geoid, lon, lat, pop)]."""
    pop = {r["geoid"]: r for r in read("data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    pts = {r["geoid"]: r for r in read("data", "extract", "census-blocks", "2020.json")["records"]}
    return [(g, pts[g]["lon"], pts[g]["lat"], pop[g]["total"]) for g in sorted(pop) if pop[g]["total"] > 0]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def schedule_label(day):
    """'late-August 2026' for 2026-08-26."""
    part = "early" if day.day <= 10 else "mid" if day.day <= 20 else "late"
    return "%s-%s %d" % (part, day.strftime("%B"), day.year)


def walk_minutes(root=ROOT):
    """{geoid: {type: walk minutes or None}} from access-time's walk list, the map's walk column."""
    d = read_json(root, WALK_REL)
    if d is None:
        return None
    return {b["geoid"]: {t: (a["walk"][0][0] if a["walk"] else None) for t, a in b["access"].items()}
            for b in d["blocks"]}


# -- origins (Mac) ------------------------------------------------------------------

def write_origins():
    """Each block's joins to the walk network, thinned to ORIGIN_SPACING_M, into ORIGINS_REL."""
    M = paths.load("school-travel-time.py")
    walknet = M.walknet
    net = M.Net(cache=True)
    G = net.G
    rows, interior = [], 0
    for g, lon, lat, _p in blocks():
        keep = []
        for e, t, _c in sorted(G.snap(lon, lat), key=lambda z: (z[2], z[0], z[1])):
            u, v = G.eu[e], G.ev[e]
            q = (G.x[u] + t * (G.x[v] - G.x[u]), G.y[u] + t * (G.y[v] - G.y[u]))
            if all(math.hypot(q[0] - k[0], q[1] - k[1]) >= ORIGIN_SPACING_M for k in keep):
                keep.append(q)
        if keep:
            pts = [[round(math.degrees(x / (math.cos(walknet.LAT0) * walknet.EARTH)), 6),
                    round(math.degrees(y / walknet.EARTH), 6)] for x, y in keep]
        else:
            pts = [[lon, lat]]
            interior += 1
        rows.append([g, pts])
    out = {"note": "R5's origins for tools/travel/full-map-transit.py: per populated 2020 census block, the points where "
                   "its street frontage joins lib/walknet.py's network (school-travel-time.py Net.ends()), no two "
                   "closer than spacing_m; a block with no join keeps its interior point (interior_fallback).",
           "spacing_m": ORIGIN_SPACING_M, "walk_network_osm_base": getattr(G, "osm_base", None),
           "interior_fallback": interior, "points": sum(len(p) for _g, p in rows), "blocks": rows}
    write_json(os.path.join(ROOT, ORIGINS_REL), out, separators=(",", ":"))
    print("  %d blocks, %d origins (%d on the interior point) -> %s" % (len(rows), out["points"], interior, ORIGINS_REL))


def origins_checks(root=ROOT):
    def per_block(r):
        d = read_json(r, ORIGINS_REL)
        return None if d is None else [{"geoid": g, "points": p} for g, p in d["blocks"]]

    def ok(b):
        bad = [p for p in b["points"] if not (-122.62 < p[0] < -122.28 and 37.69 < p[1] < 37.84)]
        if not b["points"] or bad:
            return "%s: %s" % (b["geoid"], "no origin" if not b["points"] else "origin outside SF %s" % bad[:2])
        return None

    def same_blocks(r):
        d = read_json(r, ORIGINS_REL)
        if d is None:
            return None
        got = [g for g, _p in d["blocks"]]
        want = [g for g, _x, _y, _p in blocks()]
        return [] if got == want else [{"problem": "%d blocks against the census list's %d, or another order" % (
            len(got), len(want))}]

    return [
        Table("full-map-transit-origins", per_block, floor=ROW_FLOOR, max_drop=0.02, key="geoid",
              required=["geoid", "points"]),
        Each("full-map-transit-origins/points", per_block, ok, "every block has an origin, inside San Francisco"),
        Each("full-map-transit-origins/blocks", same_blocks, lambda x: x["problem"],
             "the populated 2020 blocks, in access-time's order"),
    ]


# -- the matrix (VM) ----------------------------------------------------------------

def gtfs_calendar(path):
    """(first, last) service date in the GTFS zip's calendar.txt and calendar_dates.txt (additions)."""
    days = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "calendar.txt" in names:
            for r in csv.DictReader(io.TextIOWrapper(z.open("calendar.txt"), "utf-8-sig")):
                days += [r["start_date"], r["end_date"]]
        if "calendar_dates.txt" in names:
            for r in csv.DictReader(io.TextIOWrapper(z.open("calendar_dates.txt"), "utf-8-sig")):
                if r.get("exception_type") == "1":
                    days.append(r["date"])
    if not days:
        raise SystemExit("%s has no calendar" % path)
    f = lambda s: "%s-%s-%s" % (s[:4], s[4:6], s[6:])  # noqa: E731
    return f(min(days)), f(max(days))


W = {}


def _init(osm, gtfs, dcoords, owner, ntypes, depart, coords, net=None):
    """A matrix worker: its own network (one JVM per process) and the destinations."""
    import geopandas
    import r5py
    import shapely
    W.update(net=net or r5py.TransportNetwork(osm, [gtfs]), owner=owner, ntypes=ntypes, depart=depart,
             coords=coords, ndest=len(dcoords),
             destinations=geopandas.GeoDataFrame({"id": ["d%d" % j for j in range(len(dcoords))]},
                                                 geometry=[shapely.Point(x, y) for x, y in dcoords], crs="EPSG:4326"))


def _chunk(ids):
    """Per origin in ids, the fastest minutes to each type by transit-and-walk and by walk alone."""
    import geopandas
    import numpy
    import r5py
    import shapely
    origins = geopandas.GeoDataFrame({"id": ["o%d" % k for k in ids]},
                                     geometry=[shapely.Point(*W["coords"][k]) for k in ids], crs="EPSG:4326")
    pos = {k: i for i, k in enumerate(ids)}
    best = numpy.full((len(ids), W["ntypes"]), numpy.inf)
    walk = numpy.full((len(ids), W["ntypes"]), numpy.inf)
    seen_from = numpy.zeros(len(ids), dtype=bool)
    seen_to = numpy.zeros(W["ndest"], dtype=bool)
    pairs = 0
    # Transit-and-walk, then walk alone on R5's own network: a block where the first is no faster than the
    # second has no Muni trip worth taking, whatever R5's walk is against the walk column.
    for modes, into in (([r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK], best),
                        ([r5py.TransportMode.WALK], walk)):
        try:
            ttm = r5py.TravelTimeMatrix(
                W["net"], origins=origins, destinations=W["destinations"], departure=W["depart"],
                departure_time_window=dt.timedelta(minutes=WINDOW_MIN), transport_modes=modes,
                speed_walking=WALK_MPH * KMH_PER_MPH, max_time=dt.timedelta(minutes=MAX_MIN),
                max_time_walking=dt.timedelta(minutes=MAX_MIN), percentiles=[50], snap_to_network=True)
        except ValueError as e:
            # r5py raises when no origin in the call snaps; those origins are simply missing, as in a bigger chunk.
            if "no valid origin points remain" not in str(e):
                raise
            continue
        tt = ttm["travel_time"].to_numpy(dtype=float, na_value=numpy.nan)
        fr = numpy.array([pos[int(x[1:])] for x in ttm["from_id"]], dtype=numpy.int64)
        to = numpy.array([int(x[1:]) for x in ttm["to_id"]], dtype=numpy.int64)
        if into is best:
            seen_from[fr] = True
            seen_to[to] = True
            pairs = len(ttm)
        ok = numpy.isfinite(tt)
        numpy.minimum.at(into, (fr[ok], W["owner"][to[ok]]), tt[ok])
    return ids, best, walk, seen_from, seen_to, pairs


def scenario(a):
    """None for the published feed; for a scenario, its name, the published feed's hash and the zip's scenario.json."""
    if not a.scenario:
        return None
    with zipfile.ZipFile(a.gtfs) as z:
        spec = json.loads(z.read("scenario.json")) if "scenario.json" in z.namelist() else None
    return {"name": a.scenario, "made_from_gtfs_sha256": sha256(a.scenario_of)[:16] if a.scenario_of else None,
            "spec": spec}


def compute(a):
    import geopandas
    import numpy
    import r5py
    import shapely

    dests = read(DEST_REL)
    types = sorted(dests["types"])
    day = dt.date.fromisoformat(a.date or read(STOPS_REL)["feed"]["serviceDate"])
    depart = dt.datetime.combine(day, dt.time(*DEPART_HHMM))
    cal = gtfs_calendar(a.gtfs)
    if not cal[0] <= day.isoformat() <= cal[1]:
        raise SystemExit("departure %s is outside the GTFS calendar %s to %s" % (day, cal[0], cal[1]))
    org = read(ORIGINS_REL)
    bl = blocks()
    if [g for g, _p in org["blocks"]] != [b[0] for b in bl]:
        raise SystemExit("%s does not list the populated blocks in order; rerun --origins on the Mac" % ORIGINS_REL)
    pts_of = dict((g, p) for g, p in org["blocks"])
    if a.sample:
        bl = bl[::max(1, len(bl) // a.sample)][:a.sample]
    ob, geoms, coords = [], [], []  # origin point -> block index
    for bi, b in enumerate(bl):
        for lon, lat in pts_of[b[0]]:
            ob.append(bi)
            geoms.append(shapely.Point(lon, lat))
            coords.append((lon, lat))
    ob = numpy.asarray(ob, dtype=numpy.int64)
    # Origin and destination ids must not overlap: r5py sets a pair whose from_id equals its to_id to 0 minutes
    # (r5py 1.1.7, travel_time_matrix.py: "R5 always routes to the next street segment"). So "o<k>" and "d<j>".
    owner, dgeoms, dcoords = [], [], []  # destination point index -> type index
    for ti, t in enumerate(types):
        for lon, lat, _f in dests["types"][t]["points"]:
            owner.append(ti)
            dgeoms.append(shapely.Point(lon, lat))
            dcoords.append((lon, lat))
    owner = numpy.asarray(owner, dtype=numpy.int64)
    destinations = geopandas.GeoDataFrame({"id": ["d%d" % j for j in range(len(dgeoms))]}, geometry=dgeoms,
                                          crs="EPSG:4326")
    t0 = time.time()
    net = r5py.TransportNetwork(a.osm, [a.gtfs])
    if not net.transit_layer.covers(day):
        raise SystemExit("R5's transit layer has no service on %s (GTFS calendar %s to %s): the matrix would be "
                         "walk-only" % (day, cal[0], cal[1]))
    print("  network built (%.0fs); service on %s; %d blocks, %d origins, %d destination points, departing %s, "
          "%d-minute window" % (time.time() - t0, day, len(bl), len(geoms), len(destinations), depart.isoformat(),
                                WINDOW_MIN), flush=True)
    best_pt = numpy.full((len(geoms), len(types)), numpy.inf)
    walk_pt = numpy.full((len(geoms), len(types)), numpy.inf)
    seen_from = numpy.zeros(len(geoms), dtype=bool)
    seen_to = numpy.zeros(len(dgeoms), dtype=bool)
    pairs = 0
    tasks = [list(range(c0, min(c0 + a.chunk, len(geoms)))) for c0 in range(0, len(geoms), a.chunk)]
    init = (a.osm, a.gtfs, dcoords, owner, len(types), depart, coords)
    # r5py routes one origin at a time on one core, so the chunks go to separate processes, each with its own JVM
    # and network. Each origin's times don't depend on which chunk it is in.
    # A worker that dies or can't start raises BrokenProcessPool here rather than leaving the run waiting.
    if a.workers > 1:
        import concurrent.futures
        import multiprocessing
        pool = concurrent.futures.ProcessPoolExecutor(a.workers, mp_context=multiprocessing.get_context("spawn"),
                                                      initializer=_init, initargs=init)
        results = (f.result() for f in concurrent.futures.as_completed([pool.submit(_chunk, t) for t in tasks]))
    else:
        _init(*init, net=net)
        pool, results = None, map(_chunk, tasks)
    for done, (ids, b, w, sf, stt, n) in enumerate(results, 1):
        best_pt[ids] = b
        walk_pt[ids] = w
        seen_from[ids] = sf
        seen_to |= stt
        pairs += n
        print("  chunk %d of %d: origins %d-%d, %d pairs (%.0fs)" % (done, len(tasks), ids[0], ids[-1], n,
                                                                     time.time() - t0), flush=True)
    if pool is not None:
        pool.shutdown()
    best = numpy.full((len(bl), len(types)), numpy.inf)
    numpy.minimum.at(best, ob, best_pt)
    walk_best = numpy.full((len(bl), len(types)), numpy.inf)
    numpy.minimum.at(walk_best, ob, walk_pt)
    whole = lambda a: [None if not numpy.isfinite(v) else int(v) for v in a]  # noqa: E731
    rows = [[bl[i][0], whole(best[i])] for i in range(len(bl))]

    walk = walk_minutes()
    missing = []
    snapped = numpy.bincount(ob, weights=seen_from, minlength=len(bl))
    for bi, (g, mins) in enumerate(rows):
        if not snapped[bi]:
            missing.append({"geoid": g, "reason": "no origin snapped to R5's network",
                            "origins": pts_of[g]})
            continue
        lost = [t for t, m in zip(types, mins) if m is None and walk.get(g, {}).get(t) is not None
                and walk[g][t] <= MISSING_WALK_MIN]
        if lost:
            missing.append({"geoid": g, "reason": "no trip to %s, which the walk column reaches in %d minutes or less"
                            % (", ".join(lost), MISSING_WALK_MIN), "origins": pts_of[g]})
    print("  matrix: %d pairs; %d of %d origins and %d of %d destination points dropped by R5's snap; %d blocks "
          "missing (%.0fs)" % (pairs, int((~seen_from).sum()), len(geoms), int((~seen_to).sum()), len(dgeoms),
                               len(missing), time.time() - t0), flush=True)
    return {
        "note": "Median door-to-door minutes by Muni or walking, whichever is faster, on SFMTA's %s schedule (GTFS "
                "calendar %s to %s, departures %s 8:00 to 8:59 AM), from each populated 2020 census block's street "
                "frontage (its fastest origin in %s) to the nearest destination point of each type; whole minutes, "
                "rounded down; null past max_minutes." % (schedule_label(day), cal[0], cal[1], day, ORIGINS_REL),
        "parameters": {"engine": "r5py %s (Conveyal R5)" % r5py.__version__, "departure": depart.isoformat(),
                       "window_minutes": WINDOW_MIN, "percentile": 50, "walk_mph": WALK_MPH,
                       "max_minutes": MAX_MIN, "modes": ["TRANSIT", "WALK"], "sample": a.sample or None,
                       "service_on_departure": True, "origin_spacing_m": org["spacing_m"]},
        "inputs": {"gtfs_sha256": sha256(a.gtfs)[:16], "gtfs_fetched": a.gtfs_fetched,
                   "gtfs_calendar": list(cal), "schedule": schedule_label(day),
                   "osm": os.path.basename(a.osm), "osm_timestamp": a.osm_timestamp,
                   "destinations_points_sha256": points_sha(dests),
                   "origins_sha256": sha256(os.path.join(ROOT, ORIGINS_REL))[:16]},
        "origins": {"points": len(geoms), "dropped_by_snap": int((~seen_from).sum()),
                    "destination_points_dropped_by_snap": int((~seen_to).sum())},
        "missing_origins": missing,
        "scenario": scenario(a),
        "types": types,
        "blocks": rows,
        "walk_only": {"note": "R5's walk-only minutes over the same origins and network, per block in blocks' "
                              "order: a block's Muni trip is real only where blocks' minutes are below these.",
                      "minutes": [whole(walk_best[i]) for i in range(len(bl))]},
    }


def checks(root=ROOT, rel=OUT_REL):
    def per_block(r):
        d = read_json(r, rel)
        if d is None:
            return None
        return [dict({"geoid": g}, **dict(zip(d["types"], m))) for g, m in d["blocks"]]

    def in_range(row):
        bad = [k for k, v in row.items() if k != "geoid" and v is not None and not 0 <= v <= MAX_MIN]
        return ("%s: %s out of 0..%d" % (row["geoid"], bad, MAX_MIN)) if bad else None

    def coverage(r):
        rows = per_block(r)
        if rows is None:
            return None
        n = len(rows)
        return [{"type": t, "reached": sum(1 for x in rows if x[t] is not None), "n": n}
                for t in sorted(k for k in rows[0] if k != "geoid")] if rows else []

    def beats(r):
        """Per BEAT_TYPES type, the blocks where a real Muni trip (faster than R5's walk alone) beats the walk column on
        the same whole-minute basis."""
        d, walk = read_json(r, rel), walk_minutes(r)
        if d is None or walk is None:
            return None
        if "walk_only" not in d:
            return [{"type": t, "beats": 0, "n": len(d["blocks"])} for t in BEAT_TYPES]
        out = []
        for t in BEAT_TYPES:
            ti = d["types"].index(t)
            n = 0
            for (g, m), wo in zip(d["blocks"], d["walk_only"]["minutes"]):
                v, w, w5 = m[ti], walk.get(g, {}).get(t), wo[ti]
                if v and (w5 is None or v < w5) and (w is None or w >= v + 1):
                    n += 1
            out.append({"type": t, "beats": n, "n": len(d["blocks"])})
        return out

    def run_state(r):
        d = read_json(r, rel)
        if d is None:
            return None
        bad = []
        if not d["parameters"].get("service_on_departure"):
            bad.append("no record that R5's transit layer had service on the departure date")
        if len(d.get("missing_origins", [None] * (MAX_MISSING + 1))) > MAX_MISSING:
            bad.append("%s blocks missing from the matrix (most %d)" % (
                len(d["missing_origins"]) if "missing_origins" in d else "unrecorded", MAX_MISSING))
        if len(d.get("walk_only", {}).get("minutes", [])) != len(d["blocks"]):
            bad.append("walk_only minutes missing or not one row per block")
        for k in ("gtfs_fetched", "gtfs_calendar", "origins_sha256"):
            if not d["inputs"].get(k):
                bad.append("inputs.%s missing" % k)
        return [{"problem": "; ".join(bad) or None}]

    return [
        Table("full-map-transit", per_block, floor=ROW_FLOOR, max_drop=0.0, key="geoid", required=["geoid"]),
        Each("full-map-transit/range", per_block, in_range, "every time in 0..%d minutes or null" % MAX_MIN),
        # Every type is within the hour by Muni for nearly every block: a type
        # most blocks cannot reach means a broken network or a bad date.
        Each("full-map-transit/coverage", coverage,
             lambda c: None if c["reached"] >= 0.9 * c["n"] else "%s reached from %d of %d blocks" % (
                 c["type"], c["reached"], c["n"]), "every type reached within the hour from 90% of blocks"),
        # A run with no transit passes the checks above, since its walk-only routes reach everything. Muni beat
        # walking to the nearest high school and library at 29% and 31% of blocks in the 2026-10-23 run.
        Each("full-map-transit/beats-walk", beats,
             lambda c: None if c["beats"] >= BEAT_SHARE * c["n"] else "%s: Muni beats walking at %d of %d blocks" % (
                 c["type"], c["beats"], c["n"]),
             "Muni beats the walk column at %d%% of blocks or more for %s" % (100 * BEAT_SHARE, ", ".join(BEAT_TYPES))),
        Each("full-map-transit/run", run_state, lambda x: x["problem"],
             "service on the departure date, at most %d blocks missing, the feed's fetch date and calendar and the "
             "origins file recorded" % MAX_MISSING),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--origins", action="store_true", help="write %s from the walk network (Mac)" % ORIGINS_REL)
    ap.add_argument("--osm", help="an OpenStreetMap .osm.pbf covering San Francisco")
    ap.add_argument("--osm-timestamp", help="the extract's OSM timestamp, recorded in the output")
    ap.add_argument("--gtfs", help="SFMTA's GTFS zip (tools/muni/muni-gtfs.py's copy, or the same URL)")
    ap.add_argument("--gtfs-fetched", help="the date the GTFS zip was fetched, YYYY-MM-DD, recorded in the output")
    ap.add_argument("--date", help="service date, YYYY-MM-DD (default: out/full-map/muni-stops.json's)")
    ap.add_argument("--sample", type=int, metavar="N", help="N evenly spaced blocks only, for tests")
    ap.add_argument("--workers", type=int, default=1, help="matrix processes, each with its own JVM (default 1)")
    ap.add_argument("--chunk", type=int, default=CHUNK, help="origins per matrix call (default %d)" % CHUNK)
    # r5py reads --max-memory from sys.argv itself (r5py/util/memory_footprint.py), in the workers too, since a
    # spawned process gets the parent's argv; without it every JVM may grow to 80% of RAM.
    ap.add_argument("--max-memory", help="each JVM's heap limit, read by r5py from the command line (e.g. 16G)")
    ap.add_argument("--scenario", help="a scenario name recorded in the output (the --gtfs is a modified feed)")
    ap.add_argument("--scenario-of", help="the published GTFS zip the scenario feed was made from")
    ap.add_argument("--out", default=os.path.join(ROOT, OUT_REL))
    ap.add_argument("--check", action="store_true", help="run the output checks only")
    a = ap.parse_args()
    too_many = False
    if a.scenario and not (a.scenario_of and os.path.exists(a.scenario_of)):
        ap.error("--scenario needs --scenario-of, the published GTFS zip it was made from")
    if a.origins:
        write_origins()
        results = run(origins_checks(), root=ROOT)
    else:
        if not a.check:
            if not (a.osm and a.gtfs and a.gtfs_fetched):
                ap.error("--osm, --gtfs and --gtfs-fetched are required")
            out = compute(a)
            path = os.path.abspath(a.out)
            # The fetch date is the first fetch of this feed: a rerun on the same zip keeps it, so the file only
            # changes when the result does.
            prev = read_json(os.path.dirname(path), os.path.basename(path))
            if prev and prev.get("inputs", {}).get("gtfs_sha256") == out["inputs"]["gtfs_sha256"] \
                    and prev["inputs"].get("gtfs_fetched"):
                out["inputs"]["gtfs_fetched"] = prev["inputs"]["gtfs_fetched"]
            for m in out["missing_origins"]:
                print("  missing: %s (%s)" % (m["geoid"], m["reason"]))
            old = open(path, "rb").read() if os.path.exists(path) else None
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_json(path, out, separators=(",", ":"))
            rel = os.path.relpath(path, ROOT)
            # A --sample run keeps every check but the row floor.
            results = run([c for c in checks(rel=rel) if not (a.sample and isinstance(c, Table))], root=ROOT)
            if len(out["missing_origins"]) > MAX_MISSING:
                print("  FAILED: %d blocks missing from the matrix, most %d" % (len(out["missing_origins"]), MAX_MISSING))
            too_many = len(out["missing_origins"]) > MAX_MISSING
            ok = all(r.ok for r in results) and not too_many
            if not ok:
                # The failed result goes beside the output and the last good copy stays.
                os.replace(path, path[:-5] + ".failed.json" if path.endswith(".json") else path + ".failed")
                if old is not None:
                    with open(path, "wb") as f:
                        f.write(old)
            print("  %s %s" % ("wrote" if ok else "kept the previous", a.out))
        else:
            results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad or too_many else 0


if __name__ == "__main__":
    sys.exit(main())
