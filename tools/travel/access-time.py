#!/usr/bin/env python3
"""Minutes from every populated census block to its k nearest destinations of each type, on foot or riding the all-ages network, today and with the plan built; a changed segment reruns only the blocks it can reach.

    tools/travel/access-time.py                                  # every type, k = 5, out/access/
    tools/travel/access-time.py --types elementary,library --k 3
    tools/travel/access-time.py --add ns:12345 --out DIR         # today's network plus one plan block
    tools/travel/access-time.py --add ns:12345 --base out/access --out DIR   # the same, incrementally
    tools/travel/access-time.py --dests data/full-map/destinations.json --rule protected --nets today --k 1 \
        --out out/full-map/bike                             # the full access map's low-stress minutes

Bryan, 2026-09-30, wants the school model's measure for
many kinds of destination ("the closest 5 doctors, grocery stores, pharmacies,
hospitals, major and minor parks, retail") and scenario runs fast enough to
explore. This script is that generalisation; lib/school-travel-time.py
stays the published school figure. The architecture, and why it is fast, is in
docs/access-model-architecture.md.

THE MEASURE is the school model's (school-travel-time.py): walk at WALK_MPH,
ride at RIDE_MPH on an edge that runs along an all-ages bikeway, and a route to
a destination counts only if it is at most DETOUR x the shortest walk to that
destination. For each block and type it lists the k fastest destinations,
each by its own fastest capped route. Every listed time is exact, and only
destinations reachable in EXACT_MAX_MIN (30 minutes) are listed, so a block may
list fewer than k. The walk list is the k nearest on foot within the model's
9 km radius.

DESTINATION TYPES (TYPES below): the school model's three levels, its school
list and grade rule, and San Francisco Public Library branches open today
(data/extract/libraries/branches.json), with a branch closed for renovation
placed at its temporary site (TEMPORARY_SITE). A new type is a function returning
[{"name", "lon", "lat"}]. --dests FILE adds every type in a destinations file
written by tools/travel/full-map-destinations.py: each point is a destination named
after its feature (a park's edge points all carry the park's name), so with
--k 1 a block lists the fastest point of the type, which is its nearest park,
district or school.

THE RULE FOR TODAY'S NETWORK. By default, the bike explorer's all-ages network
(school-travel-time.all_ages_lines), which counts painted lanes and signed
routes above the Bike Comfort Index line. --rule protected uses School Trips'
rule instead (all_ages_lines(brp_rule=True); Bryan, 2026-10-15, "Protected
only", and 2026-10-18, "Calmed counts"): Class I paths, Class IV separated
lanes and Slow Streets only. The full access map reads it as LTS 1. --rule
furth1 rides that network plus every edge tools/travel/full-map-lts.py rates LTS 1
by Mekuria, Furth and Nixon's tables (quiet residential streets, mostly): the
map's check of its LTS 1 reading, not a figure of its own. --nets today skips
the plan's network.

SCENARIOS. --add KEY puts one plan block (a key such as ns:<cnn> from
site/data/north-star/traced.geojson) on today's network; --drop KEY takes one
off the plan's, unless today's network or another plan block covers the same
walk edge. With --base DIR, a run on another scenario over the same inputs,
only the blocks the change can affect are searched again (AFFECTED below); the
rest are copied. The result is the same file a full run writes.

AFFECTED. A block's list for a type depends on an edge only if a search
could put a label on one of its ends, and every label the search keeps lies in
the detour ellipse of some destination it tries: shortest walk from the
destination to the node, plus from the node to the block, at most the cap. A
destination is tried only if its walk at riding speed is under the 30-minute
limit. Walks do not depend on which edges are ridden. So a block is affected
by a change exactly when, for one of its destinations in reach, one end of a
changed edge lies inside that ellipse (with a 1 m margin for rounding). One
walk search from each changed edge's ends gives both walk distances.

WHAT IT WRITES. out/access/access.json: per block, per type, per network, the
list of [minutes, destination index] (minutes rounded up to 0.1); the
destinations of each type; the scenario; the parameters.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time

import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import rcsp, stable  # noqa: E402

M = paths.load("school-travel-time.py")

OUT = os.path.join(ROOT, "out", "access")
LIMIT_S = M.EXACT_MAX_MIN * 60
# The largest cap any search can use: a destination is tried only if its walk at
# riding speed is under the limit, so its walk is under LIMIT_S / RB.
MAX_CAP_M = M.DETOUR * LIMIT_S / M.RB + M.CAP_TOL
MARGIN_M = 1.0
NETS = ("today", "plan")
# --rule protected or furth1 (see THE RULE FOR TODAY'S NETWORK); the default is the explorer's.
RULE = {"brp": False, "furth1": False}


# -- destination types ---------------------------------------------------------

def schools_for(level):
    def load():
        schools, _dropped, _priv = M.load_schools()
        return [{"name": s["name"], "lon": s["lon"], "lat": s["lat"]} for s in schools if level in s["levels"]]
    return load


# A branch closed for renovation that serves from a temporary site is placed
# there. Mission: sfpl.org/locations/mission, read 2026-09-30, "Now open for
# in-person service at 1234 Valencia Street while the Mission Branch is closed
# for renovation"; point from the Census geocoder.
TEMPORARY_SITE = {"Mission Branch Library": (-122.420832, 37.753127)}


def libraries():
    rows = M.read(ROOT, "data", "extract", "libraries", "branches.json")["records"]
    out = []
    for r in sorted(rows, key=lambda r: r["name"]):
        if not r.get("closed_from"):
            out.append({"name": r["name"], "lon": r["lon"], "lat": r["lat"]})
        elif r["name"] in TEMPORARY_SITE:
            lon, lat = TEMPORARY_SITE[r["name"]]
            out.append({"name": r["name"], "lon": lon, "lat": lat})
    return out


TYPES = {"elementary": schools_for("elementary"), "middle": schools_for("middle"), "high": schools_for("high"),
         "library": libraries}


def add_dest_types(path):
    """Every type in a full-map destinations file, as TYPES entries; returns their names."""
    blob = M.read(path)
    names = []
    for name, t in sorted(blob["types"].items()):
        feats = t["features"]
        rows = [{"name": feats[f]["name"], "lon": lon, "lat": lat} for lon, lat, f in t["points"]]
        TYPES[name] = (lambda rows=rows: [dict(r) for r in rows])
        names.append(name)
    return names


# -- inputs --------------------------------------------------------------------

def networks(net, add=None, drop=None):
    """Ridden edges today and with the plan built, after the scenario."""
    today_lines, plan_lines, _meta = M.all_ages_lines(brp_rule=RULE["brp"])
    line_edges, _weak = M.edges_of(net, today_lines + plan_lines, cache=net.cache)
    n_e = len(net.G.eu)
    today = numpy.zeros(n_e, dtype=numpy.uint8)
    for k, _ in today_lines:
        today[sorted(line_edges.get(k, ()))] = 1
    if RULE["furth1"]:
        # Every edge Mekuria, Furth and Nixon's tables rate LTS 1 from its OSM tags (tools/travel/full-map-lts.py).
        F = paths.load("full-map-lts.py")
        today[F.edge_lts(net.G)[0] == 1] = 1
    plan = today.copy()
    for k, _ in plan_lines:
        plan[sorted(line_edges.get(k, ()))] = 1
    keys = {k for k, _ in today_lines + plan_lines}
    for key in (add, drop):
        if key is not None and key not in keys:
            raise SystemExit("no bikeway or plan block %r" % key)
    if add:
        today[sorted(line_edges.get(add, ()))] = 1
    if drop:
        kept = set()
        for k, _ in plan_lines:
            if k != drop:
                kept |= line_edges.get(k, set())
        es = [e for e in sorted(line_edges.get(drop, ())) if not today[e] and e not in kept]
        plan[es] = 0
    return {"today": today, "plan": plan}


def load_blocks(net):
    pop = {r["geoid"]: r for r in M.read(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    pts = {r["geoid"]: r for r in M.read(ROOT, "data", "extract", "census-blocks", "2020.json")["records"]}
    out = []
    for gid in sorted(pop):
        if pop[gid]["total"] <= 0:
            continue
        p = pts[gid]
        out.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "pop": pop[gid]["total"],
                    "ends": net.ends(p["lon"], p["lat"])})
    return out


class Kind(object):
    """One destination type: its points, their joins, and the walk from each block to each (a dense matrix)."""

    def __init__(self, net, name, dests, blocks):
        self.name, self.dests = name, dests
        for d in dests:
            d["ends"] = net.ends(d["lon"], d["lat"])
        level = M.Level(net, name, dests, blocks)
        self.W = numpy.full((len(blocks), len(dests)), numpy.inf)
        for di, w in enumerate(level.walk):
            if w:
                self.W[numpy.fromiter(w.keys(), dtype=numpy.int64, count=len(w)), di] = numpy.fromiter(
                    w.values(), dtype=numpy.float64, count=len(w))
        self.fast = rcsp.Schools([d["ends"] for d in dests])


# -- the per-block search ----------------------------------------------------------

S = {}


def cell(t):
    return math.ceil(t / 6.0 - 1e-9) / 10.0


def block_row(bi):
    """Every type's k nearest for one block: {type: {"walk"|"today"|"plan": [[minutes, destination]]}}, and seconds per type."""
    net, blocks, kinds, nets, k = S["net"], S["blocks"], S["kinds"], S["nets"], S["k"]
    b = blocks[bi]
    spent = {}
    row = {}
    if not b["ends"]:
        return bi, {kd.name: dict({"walk": []}, **{nk: [] for nk in NETS}) for kd in kinds}, spent
    fe = M.fast_ends(b["ends"])
    net.fast.lazy(0, None, M.RW, M.RB, fe, min(M.WALK_CUTOFF_M, MAX_CAP_M + MARGIN_M))
    for kd in kinds:
        Ws = numpy.ascontiguousarray(kd.W[bi])
        order = numpy.argsort(Ws, kind="stable").astype(numpy.int32)
        near = [int(i) for i in order[:k] if Ws[i] < numpy.inf]
        row[kd.name] = {"walk": [[cell(Ws[i] * M.RW), i] for i in near]}
    for nk in NETS:
        bike = nets[nk]
        net.fast.lazy(1, bike, M.RW, M.RB, fe, LIMIT_S + 1.0)
        for kd in kinds:
            t1 = time.perf_counter()
            Ws = numpy.ascontiguousarray(kd.W[bi])
            order = numpy.argsort(Ws, kind="stable").astype(numpy.int32)
            got = net.fast.topk(bike, M.RW, M.RB, M.DETOUR, M.CAP_TOL, kd.fast, Ws, fe, k, LIMIT_S + 1e-6,
                                M.A_MARGIN, order)
            row[kd.name][nk] = [[cell(t), int(i)] for t, i in got]
            spent[kd.name] = spent.get(kd.name, 0.0) + time.perf_counter() - t1
    return bi, row, spent


# -- which blocks a change can affect -------------------------------------------------

def affected_blocks(net, blocks, kinds, was, now, base_rows, k):
    """Blocks whose lists a change of ridden edges can move (see AFFECTED)."""
    G = net.G
    hit = numpy.zeros(len(blocks), dtype=bool)
    for nk in NETS:
        added = numpy.flatnonzero((was[nk] == 0) & (now[nk] == 1)).tolist()
        removed = numpy.flatnonzero((was[nk] == 1) & (now[nk] == 0)).tolist()
        # From the base run, per type: each block's k-th time (the limit if it
        # lists fewer), and the time of each destination it lists (INF if not).
        # Minutes were rounded up, so both are upper bounds on the true times.
        kth, listed = {}, {}
        for kd in kinds:
            kth[kd.name] = numpy.full(len(blocks), LIMIT_S)
            listed[kd.name] = numpy.full((len(blocks), len(kd.dests)), numpy.inf)
            for bi, r in enumerate(base_rows):
                lst = r[kd.name][nk]
                if len(lst) == k:
                    kth[kd.name][bi] = lst[-1][0] * 60
                for minutes, di in lst:
                    listed[kd.name][bi, di] = minutes * 60
        for edges, speeds_up in ((added, True), (removed, False)):
            for x in sorted({G.eu[e] for e in edges} | {G.ev[e] for e in edges}):
                dist = net.fast.walk([x], [0.0], MAX_CAP_M + MARGIN_M)
                wb = numpy.full(len(blocks), numpy.inf)
                for bi, w in M.block_walks(dist, blocks).items():
                    wb[bi] = w
                for kd in kinds:
                    wd = numpy.full(len(kd.dests), numpy.inf)
                    for di, w in M.block_walks(dist, kd.dests).items():
                        wd[di] = w
                    via = wb[:, None] + wd[None, :]  # shortest walk from the block to the destination through x
                    inside = via <= M.DETOUR * kd.W + M.CAP_TOL + MARGIN_M
                    if speeds_up:
                        # A route through x takes at least via at riding speed; it
                        # can enter or move up the list only if that beats the k-th.
                        inside &= via * M.RB < kth[kd.name][:, None] + 1.0
                    else:
                        # Slowing an edge moves the list only if a listed
                        # destination's route could use it.
                        inside &= numpy.isfinite(listed[kd.name]) & (via * M.RB <= listed[kd.name] + 1.0)
                    hit |= inside.any(axis=1)
    return hit


def fingerprint(nets, parameters):
    """md5 of the ridden-edge arrays and the parameters, so --base can tell a stale run."""
    h = hashlib.md5()
    for nk in NETS:
        h.update(nk.encode())
        h.update(numpy.ascontiguousarray(nets[nk], dtype=numpy.uint8).tobytes())
    h.update(json.dumps(parameters, sort_keys=True).encode())
    return h.hexdigest()


def params_of(a):
    """The run's parameters; the rule and networks are named only when not the default, so a default run's file is unchanged."""
    p = {"walk_mph": M.WALK_MPH, "ride_mph": M.RIDE_MPH, "detour_cap": M.DETOUR,
         "limit_minutes": M.EXACT_MAX_MIN, "walk_cutoff_m": M.WALK_CUTOFF_M}
    if a.rule != "explorer":
        p["rule"] = a.rule
    if NETS != ("today", "plan"):
        p["nets"] = list(NETS)
    return p


def pool_rows(jobs, workers):
    if workers > 1 and len(jobs) > 1:
        with multiprocessing.get_context("fork").Pool(workers) as pool:
            return list(pool.imap_unordered(block_row, jobs, chunksize=8))
    return [block_row(j) for j in jobs]


def main():
    global NETS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--types", default=",".join(TYPES), help="comma-separated, from: %s, or a --dests file's" % ", ".join(TYPES))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--add", help="a plan block key to put on today's network")
    ap.add_argument("--drop", help="a plan block key to take off the plan's network")
    ap.add_argument("--base", help="a previous run's directory: search again only the blocks the change can affect")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=M.MAX_WORKERS, help="parallel workers, at most M.MAX_WORKERS (5)")
    ap.add_argument("--no-cache", action="store_true", help="rebuild the walk network, not load .cache/walknet/")
    ap.add_argument("--sample", type=int, metavar="N", help="N evenly spaced blocks only, for tests")
    ap.add_argument("--dests", help="a destinations file (tools/travel/full-map-destinations.py); its types join TYPES")
    ap.add_argument("--rule", choices=("explorer", "protected", "furth1"), default="explorer",
                    help="today's all-ages network: the explorer's (default), School Trips' protected-only rule, "
                         "or that plus every LTS 1 edge by Furth's tables")
    ap.add_argument("--nets", default=",".join(NETS), help="comma-separated, from: today, plan")
    a = ap.parse_args()
    RULE["brp"] = a.rule in ("protected", "furth1")
    RULE["furth1"] = a.rule == "furth1"
    NETS = tuple(x for x in ("today", "plan") if x in a.nets.split(","))
    if a.dests:
        dest_types = add_dest_types(a.dests)
        if a.types == ",".join(["elementary", "middle", "high", "library"]):
            a.types = ",".join(dest_types)
    # A VM may raise the cap (ACCESS_MAX_WORKERS=N); MAX_WORKERS is this Mac's.
    a.workers = max(1, min(a.workers, int(os.environ.get("ACCESS_MAX_WORKERS") or M.MAX_WORKERS)))
    t0 = time.time()
    if not rcsp.available():
        raise SystemExit("access-time.py needs the compiled searches (a C compiler): %s" % rcsp._err)
    M.FAST["on"] = True
    net = M.Net(cache=not a.no_cache)
    print("  walk network: %s (%.1fs)" % (M.netcache.STATS.get("source"), time.time() - t0))
    blocks = load_blocks(net)
    if a.sample:
        blocks = blocks[::max(1, len(blocks) // a.sample)][:a.sample]
    names = [x for x in a.types.split(",") if x]
    kinds = [Kind(net, x, TYPES[x](), blocks) for x in names]
    nets = networks(net, a.add, a.drop)
    scenario = {"add": a.add, "drop": a.drop}
    print("  %d blocks, %d residents; types %s (%.0fs)" % (
        len(blocks), sum(b["pop"] for b in blocks), {kd.name: len(kd.dests) for kd in kinds}, time.time() - t0))
    S.update(net=net, blocks=blocks, kinds=kinds, nets=nets, k=a.k)

    rows = [None] * len(blocks)
    todo = list(range(len(blocks)))
    if a.base:
        base = M.read(a.base, "access.json")
        same = (base["types"] == {kd.name: [d["name"] for d in kd.dests] for kd in kinds} and base["k"] == a.k
                and [r["geoid"] for r in base["blocks"]] == [b["geoid"] for b in blocks])
        if not same:
            raise SystemExit("--base was run on other blocks, types or k")
        was = networks(net, base["scenario"]["add"], base["scenario"]["drop"])
        params = params_of(a)
        if base.get("inputs") != fingerprint(was, params):
            raise SystemExit("--base was run on other bikeway data or parameters; run it again first")
        changed = sorted(set(numpy.flatnonzero(was["today"] != nets["today"]).tolist())
                         | set(numpy.flatnonzero(was["plan"] != nets["plan"]).tolist()))
        hit = affected_blocks(net, blocks, kinds, was, nets, [r["access"] for r in base["blocks"]], a.k)
        todo = numpy.flatnonzero(hit).tolist()
        for bi, r in enumerate(base["blocks"]):
            if not hit[bi]:
                rows[bi] = r["access"]
        print("  incremental from %s: %d walk edges changed; %d of %d blocks to search (%.0fs)" % (
            os.path.relpath(a.base, ROOT), len(changed), len(todo), len(blocks), time.time() - t0))
    t1 = time.time()
    spent = {}
    for bi, row, sp in pool_rows(todo, a.workers):
        rows[bi] = row
        for x, v in sp.items():
            spent[x] = spent.get(x, 0.0) + v
    print("  searched %d blocks in %.1fs; search CPU seconds by type: %s" % (
        len(todo), time.time() - t1, {x: round(v, 1) for x, v in spent.items()}))
    out = {"note": "Per block and destination type: [minutes, destination index] for the k fastest destinations, "
                   "walking (walk) or riding the all-ages network today (today) or with the plan built (plan). "
                   "Exact, and listed only within %g minutes; walk lists the nearest on foot within %g m."
                   % (M.EXACT_MAX_MIN, M.WALK_CUTOFF_M),
           "k": a.k, "scenario": scenario,
           "parameters": params_of(a),
           "types": {kd.name: [d["name"] for d in kd.dests] for kd in kinds},
           "blocks": [{"geoid": b["geoid"], "pop": b["pop"], "access": rows[bi]} for bi, b in enumerate(blocks)]}
    out["inputs"] = fingerprint(nets, out["parameters"])
    os.makedirs(a.out, exist_ok=True)
    stable.write_json(os.path.join(a.out, "access.json"), out, separators=(",", ":"))
    print("  wrote %s (%.0fs)" % (os.path.relpath(os.path.join(a.out, "access.json"), ROOT), time.time() - t0))


if __name__ == "__main__":
    main()
