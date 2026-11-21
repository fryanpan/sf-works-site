#!/usr/bin/env python3
"""Checks access-time.py's k-nearest lists with the plain searches in school-travel-check.py: a random sample of blocks and hand-picked edge cases, every destination type.

    tools/travel/access-time-check.py                       # check out/access/, write out/access-check/check.json
    tools/travel/access-time-check.py --dir DIR --sample 200

The searches are the textbook ones in tools/school-trips/school-travel-check.py (Dijkstra
for the walk, Martins' label-setting for the fastest route under a length
cap), from the block outward; none of access-time.py's search code is used.
The inputs are the model's: the walk network and joins, each destination
type's points (access-time.py TYPES), and the ridden edges for the run's
scenario (access-time.py networks).

Per sampled block, type and network:
  walk          the listed destinations and minutes are the k nearest on foot
                within 9 km.
  today, plan   the list is the k destinations with the fastest capped routes
                of 30 minutes or less, in order, each at its listed minutes;
                a list shorter than k means no other destination is within 30
                minutes. A destination at exactly the same time as another may
                stand in for it.
The reference search is bounded by the listed k-th time plus a second (by 30
minutes when fewer than k are listed); a quicker route to any destination
would lie inside that bound and be found. That search is slow in plain Python
when the k-th destination is far, so the whole list is checked on --full
blocks of the sample (20 by default) and the nearest destination on the rest.
Edge cases: every block on Treasure Island or Yerba Buena Island, every
block with an empty list, and the listed time nearest to 30 minutes.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import importlib.util
import multiprocessing
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402


def _load(name, file):
    return paths.load(file, name)


C = _load("school_travel_check", "school-travel-check.py")
A = _load("access_time", "access-time.py")
M = C.M
TOL_S = C.TOL_S
W = {}


def compare_list(tname, nk, fast, ref, k):
    """fast: [[minutes, i]]; ref: {i: seconds}. One verdict for the list."""
    order = sorted(ref.items(), key=lambda x: (x[1], x[0]))[:k]
    if len(order) != len(fast):
        return (tname, nk, "FAIL", "model lists %d, reference %d: %s vs %s" % (
            len(fast), len(order), fast, [[round(t, 3), i] for i, t in order]))
    for pos, ((minutes, i), (ri, rt)) in enumerate(zip(fast, order)):
        if C.cell(rt) != minutes and not C.near_boundary(rt):
            return (tname, nk, "FAIL", "position %d: model %s min, reference %.6f s" % (pos, minutes, rt))
        if i != ri and abs(ref.get(i, float("inf")) - rt) > TOL_S:
            return (tname, nk, "FAIL", "position %d: model names %s, reference %s (%.6f s; model's at %s)" % (
                pos, i, ri, rt, ref.get(i)))
    return (tname, nk, "ok", len(fast))


def check_one(bi):
    adj, length, rides, net, kinds, rows, blocks, k = (W[x] for x in (
        "adj", "length", "rides", "net", "kinds", "rows", "blocks", "k"))
    b = blocks[bi]
    row = rows[bi]
    out = []
    dist = C.shortest_walk(adj, length, b["ends"])
    for name, dests in kinds.items():
        walks = {}
        for i, d in enumerate(dests):
            w = C.walk_to(dist, d["ends"])
            if w is not None and w <= M.WALK_CUTOFF_M:
                walks[i] = w
        out.append(compare_list(name, "walk", row[name]["walk"], {i: w * M.RW for i, w in walks.items()}, k))
        for nk in A.NETS:
            fast = row[name][nk]
            depth = k if W["full"].get(bi) else 1  # how much of the list to check
            fast = fast[:depth]
            t_limit = min(C.LIMIT_S, fast[-1][0] * 60 + 1.0) if len(fast) == depth else C.LIMIT_S
            targets = {i: (dests[i]["ends"], M.DETOUR * w + M.CAP_TOL) for i, w in walks.items() if w * M.RB <= t_limit}
            best = C.fastest_capped(adj, length, rides[nk], b["ends"], targets, t_limit) if targets else {}
            best = {i: t for i, t in best.items() if t <= C.LIMIT_S}
            if len(fast) == depth:
                # Past the last checked time the reference was not searched; keep that span only.
                best = {i: t for i, t in best.items() if t <= fast[-1][0] * 60 + 1.0}
            out.append(compare_list(name, nk + ("" if depth == k else " (nearest)"), fast, best, depth))
    return bi, out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=A.OUT)
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--report")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--full", type=int, default=20,
                    help="blocks of the sample whose whole lists are checked; the rest check the nearest only")
    a = ap.parse_args()
    t0 = time.time()
    run = M.read(a.dir, "access.json")
    M.FAST["on"] = True
    net = M.Net()
    blocks = {b["geoid"]: b for b in A.load_blocks(net)}
    blocks = [blocks[r["geoid"]] for r in run["blocks"]]
    kinds = {}
    for name, listed in run["types"].items():
        dests = A.TYPES[name]()
        assert [d["name"] for d in dests] == listed, "%s: destinations differ from the run's" % name
        for d in dests:
            d["ends"] = net.ends(d["lon"], d["lat"])
        kinds[name] = dests
    nets = A.networks(net, run["scenario"]["add"], run["scenario"]["drop"])
    rides = {nk: [bool(x) for x in nets[nk]] for nk in A.NETS}
    rows = [r["access"] for r in run["blocks"]]
    k = run["k"]

    rng = random.Random(a.seed)
    picks = {i: "sample" for i in sorted(rng.sample(range(len(rows)), min(a.sample, len(rows))))}
    for i, b in enumerate(blocks):
        if b["lat"] > 37.805 and b["lon"] > -122.38:
            picks.setdefault(i, "Treasure Island / Yerba Buena Island")
        if any(not rows[i][x][nk] for x in kinds for nk in A.NETS):
            picks.setdefault(i, "an empty list")
    near30 = min((abs(t - M.EXACT_MAX_MIN), i) for i, r in enumerate(rows) for x in kinds for nk in A.NETS
                 for t, _d in r[x][nk])
    picks.setdefault(near30[1], "nearest to 30 minutes")
    empty = [i for i, why in picks.items() if why == "an empty list"]
    if len(empty) > 20:  # outlying blocks can all have empty lists; check a spread of them
        for i in empty[1::max(2, len(empty) // 20)]:
            del picks[i]

    sampled = [i for i, why in sorted(picks.items()) if why == "sample"]
    full = {i: True for i in sampled[::max(1, len(sampled) // max(1, a.full))][:a.full]}
    W.update(full=full, adj=C.plain_adjacency(net.G), length=net.G.elen, rides=rides, net=net, kinds=kinds, rows=rows,
             blocks=blocks, k=k)
    jobs = sorted(picks)
    if a.workers > 1:
        with multiprocessing.get_context("fork").Pool(a.workers) as pool:
            done = dict(pool.imap_unordered(check_one, jobs, chunksize=2))
    else:
        done = dict(check_one(i) for i in jobs)
    verdicts = collections.Counter()
    results = []
    for i in jobs:
        for tname, nk, verdict, detail in done[i]:
            verdicts[verdict] += 1
            if verdict != "ok":
                results.append({"geoid": blocks[i]["geoid"], "why": picks[i], "type": tname, "network": nk,
                                "verdict": verdict, "detail": str(detail)})
    report = {"dir": os.path.relpath(a.dir, ROOT), "seed": a.seed, "k": k, "blocks_checked": len(picks),
              "blocks_whole_list_checked": len(full),
              "why": dict(collections.Counter(picks.values())), "checks": dict(sorted(verdicts.items())),
              "not_ok": results}
    path = a.report or os.path.join(ROOT, "out", "access-check", "check.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stable.write_json(path, report, indent=1)
    print("  checked %d blocks (%s): %s (%.0fs)" % (len(picks), report["why"], report["checks"], time.time() - t0))
    for x in results:
        print("   ", x)
    sys.exit(1 if verdicts["FAIL"] else 0)


if __name__ == "__main__":
    main()
