#!/usr/bin/env python3
"""The walk and drive network the school simulation routes on, shrunk for the browser, so the School Trips page can route one reader's trip to school by each way, today and with the changes.

    pipeline/venv-step.py tools/school-trips/school-trip-graph.py           # writes site/data/school-trip-graph.json
    pipeline/venv-step.py tools/school-trips/school-trip-graph.py --check   # the quality checks on the written file

Bryan, 2026-10-08, on the mockup's Your Trip: "This should show maybe on two
separate maps your before and after commute times, and safe miles by mode."
The simulation (tools/school-trips/school-sim.py) keeps each block's minutes but not the
routes, and a reader's home is an address, not a block. So the page routes the
trip itself, in the reader's browser, on the same network with the same rules:

  THE NETWORK is school-sim's: lib/school-travel-time.py's OpenStreetMap
  walk network (data/osm-cache/sf-walk.json) joined with the drivable streets
  (data/osm-cache/sf-drive.json, school-sim's joined_graph), flagged for its
  edges on today's all-ages network, the drivable streets a car trip uses,
  the edges no one may walk (a car's street whose sidewalks are mapped apart,
  a busway), and stairs. A
  run of edges joined end to end through nodes of degree two, all with the
  same flags, becomes one chain, with its exact length and its shape
  simplified to SIMPLIFY_M for drawing. Edges outside the pieces a point may
  join (walknet.MIN_COMPONENT) are dropped.
  EACH SCHOOL'S CHANGES are school-sim's, found the way its trips_one finds
  them: Calm Streets, the residential edges whose midpoint is within ZONE_FT of
  the door; the School Street, the residential block nearest the door (a tertiary
  one where no residential block is near), from corner to corner, at most SS_MAX_FT from it and SS_LONG_FT long (the sim's
  School Street moves students, not a street, so this is our pick for the map);
  the Protected School Connector, the shortest walk from the door to
  a safe run at least CONNECT_MIN_MI long; and at the case-study schools, the
  ranked bikeway blocks. Chains split wherever any school's change starts or
  stops, so each change is a list of whole chains.

The page then runs school-sim's rules: walking at 2 mph; the car on drivable
streets at 13.4 / 0.955 mph plus 4.68 minutes (school-sim's CAR_FIXED_MIN plus
the Google fit's CAR_GOOGLE_A + CAR_GOOGLE_B x the moving time), never
shorter than the walk; the bike at 8.5 mph plus 2.1 minutes (BIKE_FIXED_MIN +
BIKE_GOOGLE_MIN), so the rules' fixed minutes carry the Google calibration; on the route with the smallest total gap off the safe
network among routes at most 25% longer than the shortest, from searches that
charge each metre off the network 1 + k times, k in GAP_K; and Muni as the
simulation's placeholder, 10 minutes plus the walk at 8 mph.

CHECKS (--check, and after every build): chains and vertices above floors;
every chain's ends are vertices; lengths not negative; the chains' total length
within 0.1% of the kept edges'; every school present with a door inside San
Francisco; every change's chain ids in range; and a School Street at 90% of schools or more.

Writes site/data/school-trip-graph.json.
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

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

OUT = os.path.join(ROOT, "site", "data", "school-trip-graph.json")
SIM_SITE = os.path.join(ROOT, "site", "data", "school-sim")
SIMPLIFY_M = 2.0
SS_HW = ("residential", "living_street", "unclassified")
SS_MAX_FT, SS_LONG_FT = 300, 700   # School Street: block midpoint within 300 ft of the door, at most 700 ft long
BBOX = (-122.53, 37.70, -122.35, 37.84)
SAFE, STEPS, DRIVE, NOWALK = 1, 2, 4, 8


def _load(name, path):
    """Run the script at `path` as module `name`; a path under this repo goes through lib/paths.py."""
    if os.path.dirname(os.path.abspath(path)).startswith(paths.ROOT + os.sep):
        return paths.load(os.path.basename(path), name)
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dp(pts, tol):
    """Douglas-Peucker on [(x, y)] metres; keeps both ends."""
    if len(pts) <= 2:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


# The browser router's rough transit time, walking distance at 8 mph after a 10-minute fixed cost. The sim
# dropped its own TRANSIT_MPH when it began reading transit times from its travel-time matrix; this keeps
# the router's estimate where it was. Our assumption.
ROUTER_TRANSIT_MPH = 8.0

def build():
    sim = _load("school_sim", paths.script("school-sim.py"))
    ix = json.load(open(os.path.join(SIM_SITE, "index.json")))
    schools = [(s["cds"], s["lon"], s["lat"]) for s in ix["schools"]]
    tops = {}
    for cds, _x, _y in schools:
        f = json.load(open(os.path.join(SIM_SITE, "%s.json" % cds)))
        if f.get("topBlocks"):
            tops[cds] = [(k, line) for k, line in f["topBlocks"]]
    sim.network([], tops)
    W = sim._W
    G, net, walknet = W["G"], W["net"], W["walknet"]
    n = W["n"]
    eu, ev, L = W["eu"], W["ev"], W["L"]
    safe, steps, drive = W["safe"], W["steps"], W["drive_seed"]
    joinable, walkable = W["joinable"], W["walkable"]
    x, y = W["x"], W["y"]

    # The School Street's candidates: residential streets a car may drive, and each node's count of drivable edges,
    # so a block grows from corner to corner.
    # The drive edges carry their own highway tags (school-sim's joined_graph, rebuilt here in the same order), since
    # zone_hw keeps only walkable edges and a street whose sidewalks are mapped apart isn't one.
    hw = sim.joined_graph(G, walknet)[5]
    assert len(hw) == len(L)
    hw = np.asarray(hw)
    ss_res = drive & np.isin(hw, list(SS_HW))
    ss_ter = drive & (hw == "tertiary")
    ss_ok = ss_res | ss_ter
    ddeg = np.bincount(eu[drive], minlength=n) + np.bincount(ev[drive], minlength=n)
    ss_at = {}
    for e in np.flatnonzero(ss_ok):
        ss_at.setdefault(int(eu[e]), []).append(int(e))
        ss_at.setdefault(int(ev[e]), []).append(int(e))

    def school_street(dx, dy, mx_, my_):
        # A residential street first; a tertiary one only when no residential block is near the door.
        e0 = None
        for ok in (ss_res, ss_ter):
            cand = np.flatnonzero(ok)
            d = np.hypot(mx_[cand] - dx, my_[cand] - dy)
            if len(cand) and d.min() <= SS_MAX_FT * sim.FT:
                e0 = int(cand[np.argmin(d)])
                break
        if e0 is None:
            return []
        got, length = {e0}, float(L[e0])
        for v in (int(eu[e0]), int(ev[e0])):
            e = e0
            while ddeg[v] == 2 and length < SS_LONG_FT * sim.FT:
                nxt = [f for f in ss_at.get(v, []) if f not in got]
                if not nxt:
                    break
                e = nxt[0]
                got.add(e)
                length += float(L[e])
                v = int(ev[e]) if int(eu[e]) == v else int(eu[e])
        return sorted(got)

    # Each school's changes, as school-sim's trips_one finds them.
    tags = {}
    per = []
    for j, (cds, lon, lat) in enumerate(schools):
        door = net.ends(lon, lat)
        door = [d for d in door if walkable[d[3]]] or door
        wdist, wpred, wlk = sim._dijkstra(W["Lw"].copy(), [d[0] for d in door], [d[1] + d[2] for d in door])
        dx, dy = walknet.xy(lon, lat)
        mx_, my_ = (x[eu] + x[ev]) / 2, (y[eu] + y[ev]) / 2
        zone = W["zone_hw"] & (np.hypot(mx_ - dx, my_ - dy) <= sim.ZONE_FT * sim.FT) & ~safe
        conn = np.zeros(len(L), dtype=bool)
        tgt = W["run_ok"]
        nodes = np.unique(np.r_[eu[tgt], ev[tgt]])
        if len(nodes):
            t = int(nodes[np.argmin(wdist[nodes])])
            if np.isfinite(wdist[t]):
                key, ref = wlk
                v = t
                while v != n and v >= 0:
                    pv = int(wpred[v])
                    if pv < 0:
                        break
                    r = ref[np.searchsorted(key, pv * (n + 1) + v)]
                    if r >= 0:
                        conn[r] = True
                    v = pv
                conn &= ~safe
        for e in np.flatnonzero(zone):
            tags.setdefault(int(e), []).append(("z", j))
        for e in school_street(dx, dy, mx_, my_):
            tags.setdefault(e, []).append(("s", j))
        for e in np.flatnonzero(conn):
            tags.setdefault(int(e), []).append(("c", j))
        tb = W.get("top_edges", {}).get(cds) or []
        for b, es in enumerate(tb):
            for e in es:
                tags.setdefault(int(e), []).append(("t", j, b))
        per.append({"cds": cds, "door": [round(lon, 5), round(lat, 5)], "blocks": len(tb)})

    keep = joinable & (eu != ev)
    flags = (safe * SAFE) | (steps * STEPS) | (drive * DRIVE) | (~walkable * NOWALK)
    ekey = {}
    for e in np.flatnonzero(keep):
        ekey[int(e)] = (int(flags[e]), tuple(sorted(tags.get(int(e), ()))))
    inc = [[] for _ in range(n)]
    for e in ekey:
        inc[eu[e]].append(e)
        inc[ev[e]].append(e)
    is_vertex = np.zeros(n, dtype=bool)
    for v in range(n):
        es = inc[v]
        if es and (len(es) != 2 or ekey[es[0]] != ekey[es[1]]):
            is_vertex[v] = True

    seen = set()
    chains = []   # (u, v, [nodes], length, flags, tags)

    def walk(start, e0):
        nodes, length, e, v = [start], 0.0, e0, start
        while True:
            seen.add(e)
            length += float(L[e])
            w = int(ev[e]) if int(eu[e]) == v else int(eu[e])
            nodes.append(w)
            if is_vertex[w]:
                return nodes, length
            nxt = [f for f in inc[w] if f != e]
            if not nxt or nxt[0] in seen:
                is_vertex[w] = True
                return nodes, length
            e, v = nxt[0], w

    for v in np.flatnonzero(is_vertex):
        for e in inc[v]:
            if e not in seen:
                k = ekey[e]
                nodes, length = walk(int(v), e)
                chains.append((nodes, length, k))
    for e in sorted(ekey):   # loops of degree-two nodes only
        if e not in seen:
            v = int(eu[e])
            is_vertex[v] = True
            nodes, length = walk(v, e)
            chains.append((nodes, length, ekey[e]))

    vid = {}
    vx = []
    inv = lambda px, py: (math.degrees(px / (math.cos(walknet.LAT0) * walknet.EARTH)), math.degrees(py / walknet.EARTH))
    for nodes, _l, _k in chains:
        for v in (nodes[0], nodes[-1]):
            if v not in vid:
                vid[v] = len(vx)
                lo, la = inv(x[v], y[v])
                vx.append((round(lo * 1e5), round(la * 1e5)))
    out_c = []
    chain_tags = {}
    for ci, (nodes, length, k) in enumerate(chains):
        pts = _dp([(float(x[v]), float(y[v])) for v in nodes], SIMPLIFY_M)
        mid = []
        prev = vx[vid[nodes[0]]]
        for px, py in pts[1:-1]:
            lo, la = inv(px, py)
            q = (round(lo * 1e5), round(la * 1e5))
            mid += [q[0] - prev[0], q[1] - prev[1]]
            prev = q
        out_c.append([vid[nodes[0]], vid[nodes[-1]], round(length * 10), k[0], mid])
        for t in k[1]:
            chain_tags.setdefault(t, []).append(ci)
    for j, p in enumerate(per):
        p["calm"] = sorted(chain_tags.get(("z", j), []))
        p["schoolStreet"] = sorted(chain_tags.get(("s", j), []))
        p["connector"] = sorted(chain_tags.get(("c", j), []))
        p["topBlocks"] = [sorted(chain_tags.get(("t", j, b), [])) for b in range(p.pop("blocks"))]
    cols = {"from": [], "to": [], "dm": [], "flags": [], "mid": []}
    last = 0
    for a, b, dm, fl, mid in out_c:
        cols["from"].append(a - last)
        cols["to"].append(b - a)
        cols["dm"].append(dm)
        cols["flags"].append(fl)
        cols["mid"].append(mid)
        last = a
    flat_v = []
    px_, py_ = 0, 0
    for a, b in vx:
        flat_v += [a - px_, b - py_]
        px_, py_ = a, b
    doc = {
        "note": "Written by tools/school-trips/school-trip-graph.py from school-sim's network. vertices: lon and lat x 1e5, "
                "delta-encoded pairs. chains, one column each: from (the vertex, less the previous chain's), to (less "
                "this chain's from), dm (length in decimetres), flags (1 safe today, 2 stairs, 4 drivable, 8 not walkable: a street a car uses whose sidewalks are their own ways, or a busway), mid (interior "
                "points as lon and lat x 1e5 deltas from the previous point). schools: each door and the chains each "
                "change makes safe.",
        "flags": {"safe": SAFE, "steps": STEPS, "drive": DRIVE, "noWalk": NOWALK},
        "rules": {"walkMph": sim.WALK_MPH, "bikeMph": sim.BIKE_MPH, "bikeFixedMin": sim.BIKE_FIXED_MIN + sim.BIKE_GOOGLE_MIN,
                  # The sim's car is CAR_FIXED_MIN + A + B x the routed moving time, which is the router's
                  # distance / speed + fixed with the speed divided by B and A in the fixed minutes.
                  "carMph": round(sim.CAR_MPH / sim.CAR_GOOGLE_B, 4), "carFixedMin": sim.CAR_FIXED_MIN + sim.CAR_GOOGLE_A,"transitFixedMin": sim.TRANSIT_FIXED_MIN, "transitMph": ROUTER_TRANSIT_MPH,
                  "detour": sim.DETOUR, "gapK": list(sim.GAP_K), "slackM": walknet.TARGET_SLACK_M,
                  "busExtraMin": getattr(sim, "BUS_EXTRA_MIN", None), "busOverMi": sim.CHANGES["yellow_bus"]["over_mi"]},
        "edgeLengthM": round(float(L[keep].sum()), 1),
        "vertices": flat_v,
        "chains": cols,
        "schools": per,
    }
    return doc


def check(doc):
    bad = []
    nv = len(doc["vertices"]) // 2
    c0 = doc["chains"]
    fr, k = [], 0
    for d in c0["from"]:
        k += d
        fr.append(k)
    ch = [(a, a + t, dm) for a, t, dm in zip(fr, c0["to"], c0["dm"])]
    if nv < 10000 or len(ch) < 15000:
        bad.append("%d vertices and %d chains, below the floors 10,000 and 15,000" % (nv, len(ch)))
    if any(not (0 <= c[0] < nv and 0 <= c[1] < nv) for c in ch):
        bad.append("a chain ends off the vertex list")
    if any(c[2] < 0 for c in ch):
        bad.append("%d chains with a negative length" % sum(1 for c in ch if c[2] < 0))
    tot = sum(c[2] for c in ch) / 10
    if abs(tot - doc["edgeLengthM"]) > 0.001 * doc["edgeLengthM"]:
        bad.append("chains total %.0f m against %.0f m of edges" % (tot, doc["edgeLengthM"]))
    sch = doc["schools"]
    if len(sch) < 100 or len(set(s["cds"] for s in sch)) != len(sch):
        bad.append("%d schools, or a school twice" % len(sch))
    for s in sch:
        x, y = s["door"]
        if not (BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]):
            bad.append("%s's door is outside San Francisco" % s["cds"])
        ids = s["calm"] + s["schoolStreet"] + s["connector"] + [i for b in s["topBlocks"] for i in b]
        if any(not (0 <= i < len(ch)) for i in ids):
            bad.append("%s names a chain out of range" % s["cds"])
    if sum(1 for s in sch if s["calm"]) < 0.8 * len(sch):
        bad.append("Calm Streets found at only %d of %d schools" % (sum(1 for s in sch if s["calm"]), len(sch)))
    if sum(1 for s in sch if s["schoolStreet"]) < 0.9 * len(sch):
        bad.append("A School Street found at only %d of %d schools" % (sum(1 for s in sch if s["schoolStreet"]), len(sch)))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        bad = check(json.load(open(OUT)))
        if bad:
            sys.exit("school-trip-graph: " + "; ".join(bad))
        print("  school-trip-graph: checks pass")
        return
    doc = build()
    bad = check(doc)
    if bad:
        sys.exit("school-trip-graph: not written: " + "; ".join(bad))
    wrote = stable.write_json(OUT, doc, separators=(",", ":"))
    print("  school-trip-graph: %d vertices, %d chains, %d schools; %s" % (
        len(doc["vertices"]) // 2, len(doc["chains"]["dm"]), len(doc["schools"]), "written" if wrote else "unchanged"))


if __name__ == "__main__":
    main()
