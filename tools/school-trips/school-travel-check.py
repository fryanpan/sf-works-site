#!/usr/bin/env python3
"""Checks school-travel-time.py's minutes with a separate, plain search: a random sample of blocks and hand-picked edge cases, every destination type.

    tools/school-trips/school-travel-check.py                    # check out/school-travel/, write out/school-travel-check/check.json
    tools/school-trips/school-travel-check.py --dir DIR --sample 200 --seed 20260930

WHY. school-travel-time.py is fast because of a compiled label-setting search
with A* bounds, lazy searches and early stops (docs/access-model-architecture.md).
Every one of those is a place a bug could hide. This script does not use any of
them. It re-derives each checked answer with the textbook method, written for
reading rather than speed, and fails if the two disagree.

WHAT IS SHARED, AND WHAT IS NOT. The inputs are the model's own: the walk
network and each point's joins to it (lib/walknet.py), the school list
and the edges each network rides (load_schools, all_ages_lines and edges_of in
school-travel-time.py). Those are the model's definition, not its search. The
searches here are written from scratch:
  * shortest walk: Dijkstra's algorithm from the block, over a plain adjacency
    dict, no cutoff other than the model's 9 km school radius;
  * fastest route under a length cap: Martins' multi-criteria label-setting
    (Martins 1984), from the block, labels (time, length) ordered by time, a
    label kept at a node unless another there is no slower and no longer. No
    A* bound, no detour-ellipse pruning, no pass-1 upper bound. The search
    stops at the model's answer plus one second (or at 30 minutes when the
    model's answer is over 30), which is what keeps it small: any quicker
    route, if there were one, would be inside that limit and found.
It searches from the block outward, where the model searches from each school
inward, so a time is summed in the opposite order; agreement is judged to
1e-6 s, and a 0.1-minute cell that rounds differently only because the time
sits within 1e-6 s of a 6-second boundary is reported, not failed.

WHAT IS CHECKED, per sampled block, for each level (elementary, middle, high),
each public-only level, and the attendance-area school, on each network:
  walk          the model's minutes equal the shortest walk to the nearest
                school within 9 km, at 2 mph.
  today, plan   when the model's time is 30 minutes or less, it equals the
                fastest capped route, and the school it names is one that
                route can reach in that time. When it is over 30 minutes (or
                none), no capped route of 30 minutes or less exists. (Over 30
                minutes the model reports a real route's time, an upper bound;
                this script does not check that bound.)
Edge cases: every block on Treasure Island or Yerba Buena Island, every block
the model gives no route for some level, and the block-level whose time is
nearest to 30 minutes.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import heapq
import importlib.util
import json
import math
import multiprocessing
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

M = paths.load("school-travel-time.py")

TOL_S = 1e-6
LIMIT_S = M.EXACT_MAX_MIN * 60


# -- the reference searches ----------------------------------------------------

def plain_adjacency(G):
    """{node: [(neighbour, edge)]} from the walk network's edge list."""
    adj = collections.defaultdict(list)
    for e in range(len(G.eu)):
        adj[G.eu[e]].append((G.ev[e], e))
        adj[G.ev[e]].append((G.eu[e], e))
    return adj


def shortest_walk(adj, length, joins):
    """Dijkstra: metres from a point (its joins: node, connector m, along-edge m, edge) to every node."""
    dist = {}
    queue = [(c + along, node) for node, c, along, _e in joins]
    heapq.heapify(queue)
    while queue:
        d, u = heapq.heappop(queue)
        if u in dist:
            continue
        dist[u] = d
        for v, e in adj[u]:
            if v not in dist:
                heapq.heappush(queue, (d + length[e], v))
    return dist


def walk_to(dist, joins):
    """Metres from the search's start to a point, over its joins; None if unreached."""
    best = None
    for node, c, along, _e in joins:
        if node in dist:
            d = dist[node] + c + along
            if best is None or d < best:
                best = d
    return best


def seconds(metres_walked, metres_ridden):
    return metres_walked / (M.WALK_MPH * M.MPS) + metres_ridden / (M.RIDE_MPH * M.MPS)


def edge_seconds(length, ridden):
    return seconds(0.0, length) if ridden else seconds(length, 0.0)


def join_seconds(ride, c, along, e):
    """A connector is walked; the part of the joined edge is ridden if the edge is."""
    return seconds(c, 0.0) + edge_seconds(along, ride[e])


def fastest_capped(adj, length, ride, start, targets, t_limit):
    """Martins' label-setting from a block: {target key: fastest seconds} over routes within each target's length cap.

    start: the block's joins. targets: {key: (joins, cap metres)}. Only
    routes of at most t_limit seconds are explored."""
    arrive = collections.defaultdict(list)  # node -> [(key, extra s, extra m)]
    for key, (joins, _cap) in targets.items():
        for node, c, along, e in joins:
            arrive[node].append((key, join_seconds(ride, c, along, e), c + along))
    m_limit = max(cap for _j, cap in targets.values())
    kept = collections.defaultdict(list)  # node -> [(t, m)] non-dominated labels
    queue = []
    for node, c, along, e in start:
        heapq.heappush(queue, (join_seconds(ride, c, along, e), c + along, node))
    best = {}
    while queue:
        t, m, u = heapq.heappop(queue)
        if t > t_limit:
            break
        if any(t2 <= t and m2 <= m for t2, m2 in kept[u]):
            continue
        kept[u] = [(t2, m2) for t2, m2 in kept[u] if not (t <= t2 and m <= m2)] + [(t, m)]
        for key, dt, dm in arrive.get(u, ()):
            if m + dm <= targets[key][1] and t + dt < best.get(key, math.inf):
                best[key] = t + dt
        for v, e in adj[u]:
            nt, nm = t + edge_seconds(length[e], ride[e]), m + length[e]
            if nt <= t_limit and nm <= m_limit:
                heapq.heappush(queue, (nt, nm, v))
    return best


# -- the model's inputs (its definition, not its search) -------------------------

def model_inputs():
    net = M.Net()
    G = net.G
    schools, _dropped, _priv = M.load_schools()
    for s in schools:
        s["ends"] = net.ends(s["lon"], s["lat"])
    today_lines, plan_lines, _meta = M.all_ages_lines()
    line_edges, _weak = M.edges_of(net, today_lines + plan_lines)
    n_e = len(G.eu)
    ride_today = [False] * n_e
    for k, _ in today_lines:
        for e in line_edges.get(k, ()):
            ride_today[e] = True
    ride_plan = list(ride_today)
    for k, _ in plan_lines:
        for e in line_edges.get(k, ()):
            ride_plan[e] = True
    return net, schools, {"walk": [False] * n_e, "today": ride_today, "plan": ride_plan}


def cell(t):
    return None if t is None else math.ceil(t / 6.0 - 1e-9) / 10.0


def near_boundary(t):
    x = t / 6.0 - 1e-9
    return abs(x - round(x)) * 6.0 < TOL_S * 10


def check_block(adj, length, rides, row, joins, types):
    """Every (type, network) of one block: [(type, network, verdict, detail)]."""
    out = []
    dist = shortest_walk(adj, length, joins)
    for tname, (dest, fast_row) in types.items():
        walks = {}
        for i, d in dest.items():
            w = walk_to(dist, d["ends"])
            if w is not None and w <= M.WALK_CUTOFF_M:
                walks[i] = w
        # walk: the nearest school on foot.
        fast = fast_row.get("walk")
        ref = min(walks.values()) * M.RW if walks else None
        out.append(compare_exact(tname, "walk", fast, ref, None, None))
        for nk in ("today", "plan"):
            fast = fast_row.get(nk)
            fast_school = fast_row.get("school_" + nk)
            t_limit = LIMIT_S if fast is None or fast > M.EXACT_MAX_MIN else min(LIMIT_S, fast * 60 + 1.0)
            targets = {i: (dest[i]["ends"], M.DETOUR * w + M.CAP_TOL) for i, w in walks.items() if w * M.RB <= t_limit}
            best = fastest_capped(adj, length, rides[nk], joins, targets, t_limit) if targets else {}
            ref = min(best.values()) if best else None
            out.append(compare_capped(tname, nk, fast, ref, best, fast_school))
    return out


def compare_exact(tname, nk, fast, ref, _best, _school):
    if fast is None and ref is None:
        return (tname, nk, "ok", "no school within 9 km")
    if fast is None or ref is None:
        return (tname, nk, "FAIL", "model %s, reference %s" % (fast, ref))
    if cell(ref) == fast:
        return (tname, nk, "ok", fast)
    return (tname, nk, "boundary" if near_boundary(ref) else "FAIL", "model %s, reference %.6f s (%s)" % (fast, ref, cell(ref)))


def compare_capped(tname, nk, fast, ref, best, fast_school):
    over = fast is None or fast > M.EXACT_MAX_MIN
    if ref is None or ref > LIMIT_S:
        return (tname, nk, "ok" if over else "FAIL", "model %s; reference: no route of 30 minutes or less" % fast)
    if over:
        return (tname, nk, "FAIL", "model %s; reference finds %.3f s" % (fast, ref))
    if cell(ref) != fast:
        return (tname, nk, "boundary" if near_boundary(ref) else "FAIL", "model %s, reference %.6f s (%s)" % (fast, ref, cell(ref)))
    if fast_school is not None and not (fast_school in best and best[fast_school] <= ref + TOL_S):
        return (tname, nk, "FAIL", "model names school %s, which the reference reaches in %s s, not %.6f" % (
            fast_school, best.get(fast_school), ref))
    return (tname, nk, "ok", fast)


W = {}


def check_one(i):
    """All checks for block i of blocks.json (forked workers read the state in W)."""
    adj, length, rides, net, names, by_name, summary, pts = (W[k] for k in (
        "adj", "length", "rides", "net", "names", "by_name", "summary", "pts"))
    r = W["blocks_out"][i]
    p = pts[r["geoid"]]
    joins = net.ends(p["lon"], p["lat"])
    types = {}
    for lvl in ("elementary", "middle", "high"):
        dest = {j: by_name[n] for j, n in enumerate(names) if lvl in by_name[n]["levels"]}
        types[lvl] = (dest, r[lvl])
        pub = {j: d for j, d in dest.items() if not d["private"]}
        types[lvl + "/public"] = (pub, r[lvl]["public"])
    if "attendance" in r:
        area = next(x for x in summary["attendance_area"]["matches"] if x["area"] == r["attendance"]["area"])
        j = names.index(area["school"])
        row = dict(r["attendance"], school_today=None, school_plan=None)
        types["attendance"] = ({j: by_name[area["school"]]}, row)
    return i, check_block(adj, length, rides, r, joins, types)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=M.OUT, help="the model's output directory")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--report", help="where to write the report (default out/school-travel-check/check.json)")
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()
    t0 = time.time()
    blocks_out = M.read(a.dir, "blocks.json")["blocks"]
    summary = M.read(a.dir, "summary.json")
    names = [s["name"] for s in summary["schools"]["list"]]
    net, schools, rides = model_inputs()
    by_name = {s["name"]: s for s in schools}
    assert [s["name"] for s in schools] == names, "school list differs from the model's summary"
    G = net.G
    adj = plain_adjacency(G)
    length = G.elen
    pts = {r["geoid"]: r for r in M.read(ROOT, "data", "extract", "census-blocks", "2020.json")["records"]}

    # Which blocks.
    rng = random.Random(a.seed)
    picks = {i: "sample" for i in sorted(rng.sample(range(len(blocks_out)), min(a.sample, len(blocks_out))))}
    for i, r in enumerate(blocks_out):
        if r["lat"] > 37.805 and r["lon"] > -122.38:
            picks.setdefault(i, "Treasure Island / Yerba Buena Island")
        if any(r[lvl][nk] is None for lvl in ("elementary", "middle", "high") for nk in ("walk", "today", "plan")):
            picks.setdefault(i, "no route for a level")
    near30 = min(((abs(r[lvl][nk] - M.EXACT_MAX_MIN), i) for i, r in enumerate(blocks_out)
                  for lvl in ("elementary", "middle", "high") for nk in ("today", "plan") if r[lvl][nk] is not None))
    picks.setdefault(near30[1], "nearest to 30 minutes")

    W.update(adj=adj, length=length, rides=rides, net=net, names=names, by_name=by_name, summary=summary, pts=pts,
             blocks_out=blocks_out)
    jobs = sorted(picks)
    if a.workers > 1:
        with multiprocessing.get_context("fork").Pool(a.workers) as pool:
            done = dict(pool.imap_unordered(check_one, jobs, chunksize=2))
    else:
        done = dict(check_one(i) for i in jobs)
    results = []
    verdicts = collections.Counter()
    for i in jobs:
        r = blocks_out[i]
        for tname, nk, verdict, detail in done[i]:
            verdicts[verdict] += 1
            if verdict != "ok":
                results.append({"geoid": r["geoid"], "why": picks[i], "type": tname, "network": nk,
                                "verdict": verdict, "detail": str(detail)})
    report = {"dir": os.path.relpath(a.dir, ROOT), "seed": a.seed, "blocks_checked": len(picks),
              "why": dict(collections.Counter(picks.values())), "checks": dict(sorted(verdicts.items())),
              "not_ok": results}
    path = a.report or os.path.join(ROOT, "out", "school-travel-check", "check.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stable.write_json(path, report, indent=1)
    print("  checked %d blocks (%s): %s (%.0fs)" % (len(picks), report["why"], report["checks"], time.time() - t0))
    for x in results:
        print("   ", x)
    sys.exit(1 if verdicts["FAIL"] else 0)


if __name__ == "__main__":
    main()
