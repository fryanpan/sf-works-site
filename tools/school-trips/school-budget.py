#!/usr/bin/env python3
"""Where a fixed budget of bike-network miles brings the most children within 15 minutes of school: plan corridors chosen by children per mile, the same chosen in Environmental Justice Communities first, against SFMTA's last-block school connections.

    tools/school-trips/school-budget.py                 # build out/school-budget/
    tools/school-trips/school-budget.py --workers 3     # parallel searches (default 5)
    tools/school-trips/school-budget.py --extra out/growbikenet/order.json   # also score another tool's order

Bryan, 2026-09-30: "let's say you have different fixed
budgets for miles of bike infrastructure you can improve. Where do you put that
budget? Let's say that number is 5, 10 or 20 or 40." And on what to report:
"Time and safety are what people care about."

THE MODEL is lib/school-travel-time.py's, imported from it unchanged: ride
10 mph on the all-ages network, walk 2 mph elsewhere, a route at most 25%
longer than the shortest walk, 15-minute target, children 5-17 by census block
(2020 DHC P12), each to the nearest school of their level, public and private.

MILES. Every mile here is centerline miles: the length of the block's line
on the plan's traced map (site/data/north-star/traced.geojson), one count per
block whatever the number of travel directions. SFMTA's plan counts miles per
direction of travel, so a two-way street is about twice as many plan miles. A
budget of N miles is N centerline miles of street made all-ages.

STRATEGY 1, CORRIDORS. Candidates are the plan's North Star blocks not all-ages
today, joined into runs on one street (school-travel-time.py's gaps), each run
cut into contiguous chunks of about CHUNK_MI, so every pick is a buildable
stretch and not a lone block. A run is walked block to block along its
touching ends; where it branches, a new stretch starts, and no chunk spans two
stretches. Greedy: pick the chunk with the most children
newly brought under 15 minutes per mile, add it to the network,
recompute every other chunk's gain on the block-levels the pick touched
(gains interact: two chunks on one route can each be worth nothing alone),
repeat until the budget is spent or no chunk brings anyone under. Only the
block-levels over 15 minutes today and under it with the whole plan built can
change (the plan network contains every pick), and a chunk can change one
only if a node of it lies inside that block's detour ellipse for a school, on
a route that could make 15 minutes on the finished plan's network; the exact
search is rerun only for those pairs, as in the gap ranking. The greedy
optimises one measure, children brought under 15 minutes; the trip-time and
exposure figures are reported beside it and are not what it chose on.

FILLING A BUDGET, the same for both strategies: items are taken in their
strategy's order, and a budget stops at the first item that does not fit what
is left of it. So every budget is a prefix of one order, and can go up to one
item unspent.

STRATEGY 3, EQUITY FIRST. The corridor greedy run lexicographically: first
it counts only children living in San Francisco's Environmental Justice
Communities (SF Planning's map, DataSF y6ci-vpnb, score 21 to 30; Bryan's
choice of definition, 2026-10-01), picking the
chunk that brings the most EJ children under 15 minutes per mile; when no
chunk brings another EJ child under, it carries on as STRATEGY 1, counting
every child. Picking within the EJ set first, rather than weighting EJ
children by some factor, because the ask is to show progress in those
communities first, and no published source gives a weight to use; a weight
would be our number. A block is EJ when its interior point lies in an EJ
polygon (pipeline/sources/ej-communities.py). Children elsewhere brought under by an
EJ pick count toward the totals as usual.

STRATEGY 2, LAST BLOCK (SFMTA's Safe School Connections draft). Repeatedly,
the school with the cheapest link to the all-ages network as it then stands
(today's plus the links already chosen) is connected next. A link follows the
shortest walk (never a stairway) from the school's frontage to that network;
every city block (CNN, DataSF 3psu-pn9h) the walk runs along is made all-ages
whole, both sides and the roadway, as a plan chunk is, and charged its
centerline length; a stretch of path on no street centerline is charged its
own length. So both strategies are priced in centerline miles of street.
Cheapest link first is our reading of the draft, not a sequence it publishes:
the draft's first strategy is the 36 schools within one block of today's
network, and it lists prioritisation criteria with no weights
(topics/sfmta-safe-school-connections.md). Once every school is linked the
strategy has nothing left to buy, so a larger budget goes unspent.

WHAT EACH SCENARIO REPORTS, weighted by children 5-17 (each child timed to the
nearest school of their age band, as school-travel-time.py does):
  * children over 15 minutes, and the change from today;
  * trip time p25, p50, p75, p90, and a histogram in 5-minute bins to 30+;
  * exposure: miles of the route, door to door, not on the all-ages network
    (walked, since the model walks every other street), p50, p75, p90; the
    first and last block count, since the last-block strategy changes them.
    And the share of children whose entire route is on the network: every
    street or path it uses is all-ages, and the only walking is the short
    connector from the block's frontage and to the school's door (counted
    strictly: the walked metres may not exceed the shortest connector at each
    end, so a route joining by a longer connector counts as off the network);
  * schools newly reached within 15 minutes by most of their nearby children
    (a school's nearby children: those of its levels whose shortest walk to
    any school of their level ends at it; a child counts when the fastest
    route under 15 minutes goes to that same school);
  * by area, EJ Communities and the rest of the city (a child by their
    block, a school by its own point): children, those within 15 minutes,
    the median trip, the average share of each child's route (by length)
    that is on the all-ages network (a child with no route under
    METRIC_MAX_MIN counts as 0, a child whose route has no length is left
    out), schools reached as above, and schools whose door is on the
    all-ages network (any edge at its frontage all-ages).
THE SEARCHES run on the compiled engine (lib/rcsp.c) when a C
compiler is present, as school-travel-time.py's do; --pure forces the Python
ones, which give the same answers about 400 times slower.

Times are exact up to METRIC_MAX_MIN (the label-setting search in
school-travel-time.py, pruned by an A* bound from the largest network any
scenario builds). A child with no route under METRIC_MAX_MIN falls in the
30+ bin, and the exposure counted for them is the shortest walk's, an upper
bound; the count of such children is reported beside the percentiles. Bins
are closed on the right: exactly 15.0 minutes is in 10-15, as it is under the
target.

THE NEAREST SCHOOL. The model sends each child to the nearest school of their
level. SFUSD assigns by choice, so many children attend a farther school, and
the absolute counts overstate the trips a network change could shift. The
ranking between strategies is the robust output.

OTHER ORDERS (--extra). A file of scenarios, each a budget and the lines it
makes all-ages (scripts/growbikenet-order.py writes one), is scored beside the
two strategies: its lines are matched to walk edges by school-travel-time.py's
edges_of, as the plan's are, and the metrics above are computed for them in
the same run. Its miles are the file's own, and the file says how it counts
them.

Reads out/school-travel/blocks.json (each block's today and plan-built time
at 15 minutes, which fixes the greedy's candidates) and writes
out/school-budget/budget.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import importlib.util
import math
import multiprocessing
import os
import sys
import time

import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
import sfdata  # noqa: E402
import walknet  # noqa: E402
from lib.pip import PolygonIndex, pick_score  # noqa: E402

ST = paths.load("school-travel-time.py")

OUT = os.path.join(ROOT, "out", "school-budget")
BASE = os.path.join(ROOT, "out", "school-travel", "blocks.json")
EJ_BLOCKS = os.path.join(ROOT, "data", "extract", "ej-communities", "blocks.json")
EJ_POLYS = os.path.join(ROOT, "data", "extract", "ej-communities", "polygons.json")
EJ_MIN, EJ_MAX = 21, 30
AREAS = ("ej", "rest")
MILE = 1609.344
BUDGETS = [5, 10, 20, 40]
CHUNK_MI = 0.25
METRIC_MAX_MIN = 30.0
CONNECTOR_TOL_M = 1.0
BIN_MIN = 5
CENTERLINES = "3psu-pn9h"
CENTERLINE_SELECT = "cnn,street,st_type,streetname,f_st,t_st,f_node_cnn,t_node_cnn,line,oneway"  # plan_directions.py's query
RW, RB, INF = ST.RW, ST.RB, ST.INF
TARGET_S = ST.TARGET_MIN * 60


def cnn_key(v):
    return str(v or "").split(".")[0].lstrip("0")


def seg_len(pts):
    P = [walknet.xy(*p) for p in pts]
    return sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(P, P[1:]))


# -- candidates ------------------------------------------------------------------

def stretches(g, plan_pts):
    """A run's blocks in order along it: walked end to end from its first end
    block; where it branches, the walk backs up and a new stretch starts."""
    ends = {k: [walknet.xy(*plan_pts[k][0]), walknet.xy(*plan_pts[k][-1])] for k in g}
    nb = {k: sorted(j for j in g if j != k and any(math.hypot(a[0] - b[0], a[1] - b[1]) <= 8.0
                                                    for a in ends[k] for b in ends[j])) for k in g}
    seen, out = set(), []
    while len(seen) < len(g):
        rest = [k for k in g if k not in seen]
        start = min(rest, key=lambda k: (len([j for j in nb[k] if j not in seen]), k))
        cur, stack = [], [start]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            if cur and k not in nb[cur[-1]]:
                out.append(cur)
                cur = []
            seen.add(k)
            cur.append(k)
            stack += [j for j in reversed(nb[k]) if j not in seen]
        if cur:
            out.append(cur)
    return out


def title(name):
    """'03RD ST' -> '3rd St', 'MCKINNON AVE' -> 'McKinnon Ave'."""
    words = []
    for w in name.split():
        w = w.lstrip("0") or w
        if w[:1].isdigit():
            words.append(w.lower())
        elif w.upper().startswith("MC") and len(w) > 2:
            words.append("Mc" + w[2:].capitalize())
        else:
            words.append(w.capitalize())
    return " ".join(words)


def chunk_runs(groups, plan_pts, plan_meta, line_edges, bike_today, cross):
    """Each gap run cut into contiguous chunks of about CHUNK_MI, ordered along the run."""
    chunks = []
    for g in groups:
        mids, lens = {}, {}
        for k in g:
            P = [walknet.xy(*p) for p in plan_pts[k]]
            mids[k] = (sum(x for x, _ in P) / len(P), sum(y for _, y in P) / len(P))
            lens[k] = seg_len(plan_pts[k])
        parts = []
        for stretch in stretches(g, plan_pts):
            total = sum(lens[k] for k in stretch)
            n = max(1, int(round(total / (CHUNK_MI * MILE))))
            size = total / n
            cut = [[] for _ in range(n)]
            acc = 0.0
            for k in stretch:
                cut[min(n - 1, int((acc + lens[k] / 2) / size))].append(k)
                acc += lens[k]
            parts += cut
        for part in parts:
            if not part:
                continue
            edges = set()
            for k in part:
                edges |= {e for e in line_edges.get(k, ()) if not bike_today[e]}
            names = collections.Counter()
            for k in part:
                for nm in cross.get(plan_meta[k]["cnn"], ()):
                    names[nm] += 1
            ends = [nm for nm in (cross.get(plan_meta[part[0]]["cnn"], ()) + cross.get(plan_meta[part[-1]]["cnn"], ()))
                    if names[nm] == 1]
            ends = list(dict.fromkeys(ends))
            street = plan_meta[part[0]]["street"]
            chunks.append({"street": street, "cnns": [plan_meta[k]["cnn"] for k in part], "keys": part,
                           "m": sum(lens[k] for k in part), "block_m": {plan_meta[k]["cnn"]: lens[k] for k in part},
                           "edges": sorted(edges), "from_to": ends[:2],
                           "facilities": sorted({plan_meta[k]["facility"] for k in part})})
    chunks.sort(key=lambda c: (c["street"], c["cnns"][0]))
    for i, c in enumerate(chunks):
        c["id"] = i
    return chunks


def school_links(net, bike_today, schools, cnn_edges, cnn_m, edge_cnn, priority=None):
    """Schools in the order the last-block strategy connects them: each time, the
    school with the cheapest link to the network as it stands, today's plus the
    links already chosen. With priority (school index -> sort key), the school
    with the lowest key goes next, and link length only breaks ties. A link is the shortest walk (no stairway) from the
    school's frontage to that network, widened to every city block it runs
    along; see STRATEGY 2.

    Returns [(school index, link metres charged, [edges upgraded], [cnns])] in
    order, the indices on today's network, and those with no link."""
    import heapq
    G, adj, L = net.G, net.adj, net.L
    n = len(adj)
    dist, pred = [INF] * n, [-1] * n
    on = [bool(x) for x in bike_today]

    def grow(edges):
        h = []
        for e in edges:
            for u in (G.eu[e], G.ev[e]):
                if dist[u] > 0.0:
                    dist[u], pred[u] = 0.0, -1
                    h.append((0.0, u))
        heapq.heapify(h)
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u]:
                continue
            for v, e in adj[u]:
                if G.ehw[e] == "steps":
                    continue
                nd = d + L[e]
                if nd < dist[v]:
                    dist[v], pred[v] = nd, e
                    heapq.heappush(h, (nd, v))

    def widen(path):
        cnns = sorted({edge_cnn[e] for e in path if e in edge_cnn})
        es = set(e for e in path if e not in edge_cnn and not on[e])
        m = sum(L[e] for e in es)
        for c in cnns:
            new = [e for e in cnn_edges[c] if not on[e]]
            if new:
                es.update(new)
                m += cnn_m[c]
        return m, sorted(es), cnns

    def link(s):
        best = None
        for node, _c, _along, e in s["ends"]:
            if on[e]:
                return (0.0, [], [])
            if G.ehw[e] == "steps" or dist[node] == INF:
                continue
            path, u = [e], node
            while pred[u] != -1:
                pe = pred[u]
                path.append(pe)
                u = G.ev[pe] if G.eu[pe] == u else G.eu[pe]
            w = widen(path)
            if best is None or w[0] < best[0]:
                best = w
        return best

    grow([e for e in range(len(on)) if on[e]])
    connected = [i for i, s in enumerate(schools) if link(s) == (0.0, [], [])]
    left = [i for i in range(len(schools)) if i not in set(connected)]
    order = []
    while left:
        cands = [(link(schools[i]), i) for i in left]
        cands = [((priority(i),) if priority else ()) + (x[0], schools[i]["name"], i, x[1], x[2])
                 for x, i in cands if x is not None]
        if not cands:
            break
        m, _nm, i, es, cnns = min(cands)[-5:]
        order.append((i, m, es, cnns))
        left.remove(i)
        if not es:
            continue
        for e in es:
            on[e] = True
        grow(es)
        # A school the new link now touches is connected at no cost.
        for j in list(left):
            if link(schools[j]) == (0.0, [], []):
                order.append((j, 0.0, [], []))
                left.remove(j)
    return order, connected, left


# -- worker state (fork inherits it) -------------------------------------------------

W = {}


def school_arrays(si):
    s = W["schools"][si]
    return si, ST.walk_array(W["net"], s["ends"]), ST.time_array(W["net"], W["tb_net"], s["ends"])


def cand_block(bi):
    """Phase A, per candidate block: its arrays on the plan network, and the chunks inside each candidate level's ellipses."""
    net, blocks = W["net"], W["blocks"]
    ends = blocks[bi]["ends"]
    wb, tb = ST.walk_array(net, ends), ST.time_array(net, W["tb_net"], ends)
    hits = {}
    for lvl in W["cand_levels"][bi]:
        L = W["levels"][lvl]
        mask = numpy.zeros(len(net.adj), dtype=bool)
        for si, sc in enumerate(L.schools):
            Ws = L.walk[si].get(bi)
            if Ws is None or Ws * RB > TARGET_S:
                continue
            ws, ts = W["sarr"][id(sc)]
            mask |= ((wb + ws) <= ST.DETOUR * Ws + ST.CAP_TOL) & ((tb + ts) <= TARGET_S + 1e-3)
        pn, pc = W["pair_nodes"], W["pair_chunks"]
        hits[lvl] = sorted(set(pc[mask[pn]].tolist()))
    return bi, wb, tb, hits


def eval_pairs(job):
    """Phase A: for one block-level, whether each chunk brings it under the target on top of the picks so far."""
    bi, lvl, picked, chunk_ids = job
    if W.get("_picked") != picked:
        bike = W["today"].copy()
        for c in picked:
            for e in W["chunk_edges"][c]:
                bike[e] = True
        W["_picked"], W["_bike"] = picked, bike
    bike = W["_bike"]
    b = W["blocks"][bi]
    wb, hb = W["wbA"][bi], W["tbA"][bi]
    out = []
    for c in chunk_ids:
        new = [e for e in W["chunk_edges"][c] if not bike[e]]
        for e in new:
            bike[e] = 1
        r = ST.exact_best(W["net"], bike, W["levels"][lvl], bi, b["ends"], wb, TARGET_S + 1e-6, hb)
        for e in new:
            bike[e] = 0
        out.append((c, r is not None))
    return bi, lvl, picked, out


def metric_block(bi):
    """Phase B, per block: for each level and scenario, (seconds, metres) of the fastest capped route under METRIC_MAX_MIN, or None."""
    net, blocks = W["net"], W["blocks"]
    b = blocks[bi]
    ends = b["ends"]
    wb = ST.walk_array(net, ends)
    tb = ST.time_array(net, W["tb_net"], ends)
    cap_s = METRIC_MAX_MIN * 60 + 1e-6
    conn_b = min((c for _n, c, _a, _e in ends), default=0.0)

    def pack(r, L):
        # (seconds, metres, whole route on the network, school): walked no more
        # than the shortest connector at each end, the block's and the school's.
        if r is None:
            return None
        t, si, m = r
        walked = max(0.0, min(m, (t - m * RB) / (RW - RB)))
        conn_s = min((c for _n, c, _a, _e in L.schools[si]["ends"]), default=0.0)
        return (round(t, 2), round(m, 1), walked <= conn_b + conn_s + CONNECTOR_TOL_M, W["school_ix"][id(L.schools[si])])
    out = {}
    for band, lvl, _ in ST.BANDS:
        if not b[band]:
            continue
        L = W["levels"][lvl]
        base = ST.exact_best(net, W["today"], L, bi, ends, wb, cap_s, tb)
        mask = numpy.zeros(len(net.adj), dtype=bool)
        for si, sc in enumerate(L.schools):
            Ws = L.walk[si].get(bi)
            if Ws is None or Ws * RB > cap_s:
                continue
            ws, ts = W["sarr"][id(sc)]
            mask |= ((wb + ws) <= ST.DETOUR * Ws + ST.CAP_TOL) & ((tb + ts) <= cap_s + 1e-3)
        row = {}
        for sk, (bike, nodes) in W["scen"].items():
            r = base
            if len(nodes) and mask[nodes].any():
                up = min(base[0] - 1e-6, cap_s) if base else cap_s
                ex = ST.exact_best(net, bike, L, bi, ends, wb, up, tb)
                if ex:
                    r = ex
            row[sk] = pack(r, L)
        row["today"] = pack(base, L)
        out[lvl] = row
    return bi, out


def pool_map(fn, jobs, workers, label, t0, every=500):
    out = []
    if POOL and len(jobs) > 1:
        for i, r in enumerate(POOL[0].imap_unordered(fn, jobs, chunksize=1)):
            out.append(r)
            if every and i % every == 0:
                print("    %s %d/%d (%.0fs)" % (label, i, len(jobs), time.time() - t0), flush=True)
    elif workers > 1 and len(jobs) > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(fn, jobs, chunksize=1)):
                out.append(r)
                if every and i % every == 0:
                    print("    %s %d/%d (%.0fs)" % (label, i, len(jobs), time.time() - t0), flush=True)
    else:
        out = [fn(j) for j in jobs]
    return out


POOL = []  # a pool kept open across the greedy's rounds, forked once with its state


# -- greedy ------------------------------------------------------------------------

def greedy(chunks, cost, phases, pairs_of_chunk, chunks_of_bl, first_terms, workers, t0, max_budget, label):
    """Children per mile of cost, recomputed after each pick on the block-levels it touched.

    phases: one or more {block-level: children} weightings, used in turn. A
    pick is ranked by the current phase's children per mile; when no chunk
    has a positive gain under it, the next phase takes over. The last phase
    is every candidate child, and is what the totals count."""
    term = dict(first_terms)  # (chunk, bl) -> brings bl under on top of the picks
    cand_kids = phases[-1]
    under = set()
    picked, spent, got, seq = [], 0.0, 0, []
    avail = {c["id"] for c in chunks if c["edges"] and pairs_of_chunk.get(c["id"])}
    ph = 0

    def gain(c):
        w = phases[ph]
        return sum(w.get(bl, 0) for bl in pairs_of_chunk[c] if bl not in under and term.get((c, bl)))
    gains = {c: gain(c) for c in avail}
    while True:
        best = None
        for c in sorted(avail):
            g = gains[c]
            if g <= 0:
                continue
            r = g / cost[c] if cost[c] > 0 else float("inf")
            if best is None or r > best[0] + 1e-12:
                best = (r, c)
        if best is None and ph + 1 < len(phases) and spent < max_budget - 1e-9:
            ph += 1
            gains = {c: gain(c) for c in avail}
            print("    %s: phase %d from pick %d, %.2f mi" % (label, ph, len(seq) + 1, spent), flush=True)
            continue
        if best is None or spent >= max_budget - 1e-9:
            break
        c = best[1]
        newly = [bl for bl in pairs_of_chunk[c] if bl not in under and term.get((c, bl))]
        picked.append(c)
        avail.discard(c)
        spent += cost[c]
        got += sum(cand_kids[bl] for bl in newly)
        under.update(newly)
        seq.append({"chunk": c, "cost_mi": round(cost[c], 4), "spent_mi": round(spent, 4), "gain_per_mi": round(best[0], 2), "children": sum(cand_kids[bl] for bl in newly),
                    "cumulative_children": got})
        if len(phases) > 1:
            seq[-1]["phase"] = ph
        # Re-evaluate every other chunk on the block-levels this pick touched and left over.
        tup = tuple(picked)
        jobs = []
        for bl in pairs_of_chunk[c]:
            if bl in under:
                continue
            others = sorted(d for d in chunks_of_bl[bl] if d in avail)
            if others:
                jobs.append((bl[0], bl[1], tup, others))
        for bi, lvl, _p, res in pool_map(eval_pairs, jobs, workers, label, t0, every=0):
            for d, ok in res:
                term[(d, (bi, lvl))] = ok
        touched = {d for bl in pairs_of_chunk[c] for d in chunks_of_bl[bl] if d in avail}
        for d in touched:
            gains[d] = gain(d)
        if len(seq) % 10 == 0:
            print("    %s: %d picks, %.2f mi, %d children (%.0fs)" % (label, len(seq), spent, got, time.time() - t0), flush=True)
    return picked, seq


# -- metrics ------------------------------------------------------------------------

def wquant(pairs, qs):
    """Weighted quantiles of (value, weight) pairs; INF allowed."""
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    out = []
    for q in qs:
        need, acc, val = q * tot, 0, None
        for v, w in pairs:
            acc += w
            if acc >= need - 1e-9:
                val = v
                break
        out.append(val)
    return out


def main():
    global BUDGETS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--sample", type=int, default=0, help="development: time only every Nth block in the metrics")
    ap.add_argument("--extra", action="append", default=[], help="a scenario file (scripts/growbikenet-order.py's) to score beside the strategies")
    ap.add_argument("--skip-greedy", action="store_true", help="development: no greedy search, so no corridor scenarios")
    ap.add_argument("--pure", action="store_true", help="use the pure-Python searches, not lib/rcsp.c (same answers, about 400 times slower)")
    ap.add_argument("--budgets", default=None, help="development: comma-separated budgets in miles instead of %s" % BUDGETS)
    ap.add_argument("--out", default=None, help="development: write here instead of out/school-budget/budget.json")
    a = ap.parse_args()
    t0 = time.time()
    if a.budgets:
        BUDGETS = [float(x) if "." in x else int(x) for x in a.budgets.split(",")]
    ST.FAST["on"] = not a.pure and ST.rcsp.available()
    print("  searches: %s" % ("compiled (lib/rcsp.c)" if ST.FAST["on"] else "pure Python"), flush=True)

    net = ST.Net()
    G = net.G
    n_e = len(G.eu)
    kids = {r["geoid"]: r for r in ST.read(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    pts = {r["geoid"]: r for r in ST.read(ROOT, "data", "extract", "census-blocks", "2020.json")["records"]}
    blocks = []
    for gid in sorted(kids):
        k = kids[gid]
        if k["a5_9"] + k["a10_14"] + k["a15_17"] == 0:
            continue
        p = pts[gid]
        blocks.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "a5_9": k["a5_9"], "a10_14": k["a10_14"],
                       "a15_17": k["a15_17"], "ends": net.ends(p["lon"], p["lat"])})
    base_rows = ST.read(BASE)["blocks"]
    if [r["geoid"] for r in base_rows] != [b["geoid"] for b in blocks]:
        raise SystemExit("out/school-travel/blocks.json is out of step with the census blocks; run lib/school-travel-time.py first")
    # EJ Communities: each block's flag from pipeline/sources/ej-communities.py, each school's from its own point.
    ej_rows = {r["geoid"]: r for r in ST.read(EJ_BLOCKS)["records"]}
    missing = [b["geoid"] for b in blocks if b["geoid"] not in ej_rows]
    if missing:
        raise SystemExit("%d blocks lack an EJ flag (e.g. %s); run pipeline/sources/ej-communities.py first" % (len(missing), missing[0]))
    for b in blocks:
        b["ej"] = bool(ej_rows[b["geoid"]]["ej"])
    ej_index = PolygonIndex([(p["score"], p["coords"]) for p in ST.read(EJ_POLYS)["records"]])
    schools, _dropped, _priv = ST.load_schools()
    for s in schools:
        s["ends"] = net.ends(s["lon"], s["lat"])
        sc = pick_score(ej_index.at(s["lon"], s["lat"]))
        s["ej"] = sc is not None and EJ_MIN <= sc <= EJ_MAX
    today_lines, plan_lines, plan_meta = ST.all_ages_lines()
    line_edges, _weak = ST.edges_of(net, today_lines + plan_lines)
    today_keys = {k for k, _ in today_lines}
    bike_today = [False] * n_e
    for k, _ in today_lines:
        for e in line_edges.get(k, ()):
            bike_today[e] = True
    bike_plan = list(bike_today)
    for k, _ in plan_lines:
        for e in line_edges.get(k, ()):
            bike_plan[e] = True
    # The compiled searches cache a list by identity; arrays are passed as they are.
    bike_today_a = numpy.array(bike_today, dtype=numpy.uint8)
    bike_plan_a = numpy.array(bike_plan, dtype=numpy.uint8)
    levels = {lvl: ST.Level(net, lvl, [s for s in schools if lvl in s["levels"]], blocks) for lvl in ST.LEVEL_SERVES}
    print("  %d blocks, %d schools, levels ready (%.0fs)" % (len(blocks), len(schools), time.time() - t0), flush=True)

    # Street names at each block's ends, for naming chunks.
    cl = sfdata.fetch(CENTERLINES, select=CENTERLINE_SELECT, where="active='true'", floor=15000)
    cross = {}
    for r in cl.rows:
        c = cnn_key(r.get("cnn"))
        if c:
            cross[c] = [title(x.strip()) for x in (r.get("f_st"), r.get("t_st")) if x and x.strip()]

    # Candidates: plan chunks and school links.
    groups = ST.group_gaps(plan_lines, plan_meta, today_keys)
    plan_pts = dict(plan_lines)
    chunks = chunk_runs(groups, plan_pts, plan_meta, line_edges, bike_today, cross)
    # Every walk edge along each city block's centerline, for the last-block links.
    cl_lines, cnn_m = [], {}
    for r in cl.rows:
        c, g = cnn_key(r.get("cnn")), r.get("line")
        if not c or not isinstance(g, dict):
            continue
        parts = [g.get("coordinates")] if g.get("type") == "LineString" else (
            g.get("coordinates") or [] if g.get("type") == "MultiLineString" else [])
        for part in parts:
            if part and len(part) >= 2:
                cl_lines.append((c, part))
                cnn_m[c] = cnn_m.get(c, 0.0) + seg_len(part)
    cnn_edges, _w = ST.edges_of(net, sorted(cl_lines, key=lambda x: x[0]))
    edge_cnn = {}
    for c in sorted(cnn_edges):
        for e in cnn_edges[c]:
            edge_cnn.setdefault(e, c)
    link_order, on_today, unlinked = school_links(net, bike_today, schools, cnn_edges, cnn_m, edge_cnn)
    print("  %d gap runs cut into %d chunks (%.1f mi; %d with no walk edge); %d schools, %d on today's network, "
          "%d linked in order, %d with no link (%.0fs)" % (
              len(groups), len(chunks), sum(c["m"] for c in chunks) / MILE, sum(1 for c in chunks if not c["edges"]),
              len(schools), len(on_today), len(link_order), len(unlinked), time.time() - t0), flush=True)

    band_of = {lvl: band for band, lvl, _ in ST.BANDS}

    def under15(row, lvl, nk):
        v = row[lvl][nk]
        return v is not None and v <= ST.TARGET_MIN + 1e-9

    cand = [(bi, lvl) for _, lvl, _ in ST.BANDS for bi, r in enumerate(base_rows)
            if blocks[bi][band_of[lvl]] and not under15(r, lvl, "today") and under15(r, lvl, "plan")]
    cand_kids = {bl: blocks[bl[0]][band_of[bl[1]]] for bl in cand}
    cand_kids_ej = {bl: n for bl, n in cand_kids.items() if blocks[bl[0]]["ej"]}
    cand_levels = collections.defaultdict(list)
    for bi, lvl in cand:
        cand_levels[bi].append(lvl)
    today_over = sum(blocks[bi][band] for band, lvl, _ in ST.BANDS for bi, r in enumerate(base_rows)
                     if blocks[bi][band] and not under15(r, lvl, "today"))
    print("  block-levels over 15 min today and under it with the plan built: %d (%d children); over today: %d children" % (
        len(cand), sum(cand_kids.values()), today_over), flush=True)

    # Phase A: arrays on the plan network, school ellipses, chunk hits.
    chunk_edges = [c["edges"] for c in chunks]
    pn, pc = [], []
    for c in chunks:
        for e in c["edges"]:
            for nd in (G.eu[e], G.ev[e]):
                pn.append(nd)
                pc.append(c["id"])
    W.update(net=net, blocks=blocks, levels=levels, schools=schools, tb_net=bike_plan_a, today=bike_today_a,
             school_ix={id(sc): i for i, sc in enumerate(schools)},
             chunk_edges=chunk_edges, pair_nodes=numpy.array(pn, dtype=numpy.int64),
             pair_chunks=numpy.array(pc, dtype=numpy.int64), cand_levels=dict(cand_levels))
    need = sorted({si for lvl in levels for si, sc in enumerate(schools) if lvl in sc["levels"]})
    sarr = {}
    for si, ws, ts in pool_map(school_arrays, need, a.workers, "school arrays (plan)", t0, every=100):
        sarr[id(schools[si])] = (ws, ts)
    W["sarr"] = sarr
    wbA, tbA, first = {}, {}, {}
    pairs_of_chunk, chunks_of_bl = collections.defaultdict(list), collections.defaultdict(list)
    if not a.skip_greedy:
        for bi, wb, tb, hits in pool_map(cand_block, sorted(cand_levels), a.workers, "candidate blocks", t0, every=200):
            wbA[bi], tbA[bi] = wb, tb
            for lvl, cs in hits.items():
                for c in cs:
                    pairs_of_chunk[c].append((bi, lvl))
                    chunks_of_bl[(bi, lvl)].append(c)
        for c in pairs_of_chunk:
            pairs_of_chunk[c].sort()
        W.update(wbA=wbA, tbA=tbA)
        print("  chunk/block-level pairs: %d, over %d chunks (%.0fs)" % (
            sum(len(v) for v in pairs_of_chunk.values()), len(pairs_of_chunk), time.time() - t0), flush=True)
        jobs = [(bl[0], bl[1], (), sorted(cs)) for bl, cs in sorted(chunks_of_bl.items())]
        if a.workers > 1:
            POOL.append(multiprocessing.get_context("fork").Pool(a.workers))
        for bi, lvl, _p, res in pool_map(eval_pairs, jobs, a.workers, "first gains", t0, every=200):
            for c, ok in res:
                first[(c, (bi, lvl))] = ok

    cost = {c["id"]: c["m"] / MILE for c in chunks}
    picked, seq = greedy(chunks, cost, [cand_kids], pairs_of_chunk, chunks_of_bl, first, a.workers, t0, max(BUDGETS), "greedy")
    print("  greedy: %d picks, %.2f mi, %d children (%.0fs)" % (
        len(seq), seq[-1]["spent_mi"] if seq else 0, seq[-1]["cumulative_children"] if seq else 0, time.time() - t0), flush=True)
    eq_picked, eq_seq = greedy(chunks, cost, [cand_kids_ej, cand_kids], pairs_of_chunk, chunks_of_bl, first, a.workers, t0,
                               max(BUDGETS), "equity-first")
    print("  equity-first: %d picks, %.2f mi, %d children (%.0fs)" % (
        len(eq_seq), eq_seq[-1]["spent_mi"] if eq_seq else 0, eq_seq[-1]["cumulative_children"] if eq_seq else 0,
        time.time() - t0), flush=True)
    if POOL:
        POOL.pop().close()
    W.pop("wbA", None)
    W.pop("tbA", None)
    del wbA, tbA

    # Last-block: schools in link_order, each link charged whole edges; a
    # budget stops at the first link that does not fit.
    def last_block(budget):
        have, spent, chosen = set(), 0.0, []
        for i, m, es, _c in link_order:
            if spent + m / MILE > budget + 1e-9:
                break
            spent += m / MILE
            have.update(es)
            chosen.append(i)
        return chosen, have, spent

    # Scenarios.
    scen_edges = {"plan": {e for e in range(n_e) if bike_plan[e] and not bike_today[e]}}
    scen_meta = {}
    for B in BUDGETS:
        for strat, pk, sq in (("corridor", picked, seq), ("equity-first", eq_picked, eq_seq)):
            n = 0
            while n < len(sq) and sq[n]["spent_mi"] <= B + 1e-9:
                n += 1
            es = set()
            for c in pk[:n]:
                es.update(chunk_edges[c])
            key = "%s/%g" % (strat, B)
            scen_edges[key] = es
            scen_meta[key] = {"strategy": strat, "budget_mi": B, "picks": pk[:n],
                              "spent_mi": sq[n - 1]["spent_mi"] if n else 0.0,
                              "greedy_children": sq[n - 1]["cumulative_children"] if n else 0}
        chosen, es2, spent = last_block(B)
        key = "last-block/%g" % B
        scen_edges[key] = es2
        scen_meta[key] = {"strategy": "last-block", "budget_mi": B, "schools": chosen, "spent_mi": round(spent, 4)}
    # Other tools' orders, matched to walk edges as the plan's lines are.
    extra_lines = collections.OrderedDict()
    extras = []
    for path in a.extra:
        blob = ST.read(path)
        for sc in blob["scenarios"]:
            extras.append((path, sc))
            for k, pts in sc["lines"]:
                extra_lines[k] = pts
    if extra_lines:
        extra_edges, _weak = ST.edges_of(net, list(extra_lines.items()))
        for path, sc in extras:
            es = set()
            for k, _pts in sc["lines"]:
                es.update(e for e in extra_edges.get(k, ()) if not bike_today[e])
            scen_edges[sc["key"]] = es
            scen_meta[sc["key"]] = {"strategy": sc["strategy"], "budget_mi": sc["budget_mi"], "spent_mi": sc["spent_mi"],
                                    "streets": sc["streets"], "file": os.path.relpath(path, ROOT)}
        print("  %d scenarios from %s, %d lines matched to %d walk edges" % (
            len(extras), ", ".join(a.extra), len(extra_lines), len(set().union(*extra_edges.values())) if extra_edges else 0), flush=True)
    link_mi = {i: m / MILE for i, m, _es, _c in link_order}
    universe = bike_plan_a.copy()
    for path, sc in extras:
        for e in scen_edges[sc["key"]]:
            universe[e] = 1
    for _i, _m, es, _c in link_order:
        for e in es:
            universe[e] = 1
    # Scenarios with the same edges are timed once.
    alias, seen = {}, {}
    for k in sorted(scen_edges):
        sig = tuple(sorted(scen_edges[k]))
        alias[k] = seen.setdefault(sig, k)
    print("  %d scenarios, %d distinct networks" % (len(scen_edges), len(seen)), flush=True)
    scen = {}
    for k, es in scen_edges.items():
        if alias[k] != k:
            continue
        bk = bike_today_a.copy()
        for e in es:
            bk[e] = 1
        nodes = numpy.array(sorted({x for e in es for x in (G.eu[e], G.ev[e])}), dtype=numpy.int64)
        scen[k] = (bk, nodes)
    W.update(scen=scen, tb_net=universe)
    sarr = {}
    for si, ws, ts in pool_map(school_arrays, need, a.workers, "school arrays (universe)", t0, every=100):
        sarr[id(schools[si])] = (ws, ts)
    W["sarr"] = sarr
    jobs = list(range(0, len(blocks), a.sample or 1))
    res = dict(pool_map(metric_block, jobs, a.workers, "metrics", t0, every=250))
    W.pop("sarr")

    # Catchments: each block-level's shortest-walk nearest school of its level.
    catch = {}
    for band, lvl, _ in ST.BANDS:
        L = levels[lvl]
        for bi in jobs:
            best = None
            for si, w in enumerate(L.walk):
                d = w.get(bi)
                if d is not None and (best is None or d < best[0]):
                    best = (d, si)
            if best:
                catch[(bi, lvl)] = schools.index(L.schools[best[1]])

    keys = ["today"] + sorted(scen_edges)
    metrics = {}
    reached = {}
    total_kids = sum(blocks[bi][band] for bi in jobs for band, _, _ in ST.BANDS)
    by_area = {}
    for k in keys:
        tpairs, xpairs, over, ends_ok, noroute, over30 = [], [], 0, 0, 0, 0
        hist = collections.Counter()
        per_school = collections.defaultdict(lambda: [0, 0])
        ar = {g: {"children": 0, "over_15": 0, "tpairs": [], "share_sum": 0.0, "share_n": 0} for g in AREAS}
        for bi in jobs:
            g = ar["ej" if blocks[bi]["ej"] else "rest"]
            for band, lvl, _ in ST.BANDS:
                n = blocks[bi][band]
                if not n:
                    continue
                r = res[bi][lvl]["today" if k == "today" else alias[k]]
                if r is None:
                    t = INF
                    over30 += n
                    walk_m = min((w[bi] for w in levels[lvl].walk if bi in w), default=None)
                    if walk_m is None:
                        noroute += n
                    else:
                        xpairs.append((walk_m / MILE, n))
                    g["share_n"] += n
                else:
                    t, m = r[0], r[1]
                    walked = max(0.0, min(m, (t - m * RB) / (RW - RB)))
                    xpairs.append((walked / MILE, n))
                    if r[2]:
                        ends_ok += n
                    if m > 0:
                        g["share_sum"] += n * (m - walked) / m
                        g["share_n"] += n
                tpairs.append((t / 60.0, n))
                g["children"] += n
                g["tpairs"].append((t / 60.0, n))
                if not t <= TARGET_S + 1e-6:
                    over += n
                    g["over_15"] += n
                top = int(METRIC_MAX_MIN // BIN_MIN)
                hist[top if t == INF else min(top, max(0, int(math.ceil(t / 60.0 / BIN_MIN - 1e-9)) - 1))] += n
                if (bi, lvl) in catch:
                    ps = per_school[catch[(bi, lvl)]]
                    ps[0] += n
                    if t <= TARGET_S + 1e-6 and r[3] == catch[(bi, lvl)]:
                        ps[1] += n
        q = wquant(tpairs, [0.25, 0.5, 0.75, 0.9])
        xq = wquant(xpairs, [0.5, 0.75, 0.9])
        nb = int(METRIC_MAX_MIN // BIN_MIN)
        metrics[k] = {
            "over_15": over,
            "trip_min": {p: (None if v is None or v == INF else round(v, 1)) for p, v in zip(("p25", "p50", "p75", "p90"), q)},
            "trip_min_over_30": {p: v == INF for p, v in zip(("p25", "p50", "p75", "p90"), q)},
            "histogram": [{"bin": ("%d-%d" % (i * BIN_MIN, (i + 1) * BIN_MIN)) if i < nb else "%d+" % (nb * BIN_MIN),
                           "children": hist.get(i, 0)} for i in range(nb + 1)],
            "exposure_mi": {p: round(v, 3) for p, v in zip(("p50", "p75", "p90"), xq)},
            "share_entire_route_on_network": round(ends_ok / float(total_kids), 4),
            "no_route_children": noroute,
            "over_30_children": over30,
        }
        reached[k] = {si for si, (n, u) in per_school.items() if n and u * 2 > n}
        bk = bike_today_a if k == "today" else scen[alias[k]][0]
        on_net = {i for i, sc in enumerate(schools) if any(bk[e] for _n, _c, _a, e in sc["ends"])}
        by_area[k] = {}
        for gname in AREAS:
            g = ar[gname]
            mine = [i for i in range(len(schools)) if schools[i]["ej"] == (gname == "ej")]
            p50 = wquant(g["tpairs"], [0.5])[0] if g["tpairs"] else None
            by_area[k][gname] = {
                "children": g["children"], "over_15": g["over_15"], "within_15": g["children"] - g["over_15"],
                "trip_min_p50": None if p50 is None or p50 == INF else round(p50, 1),
                "mean_share_of_route_on_network": round(g["share_sum"] / g["share_n"], 4) if g["share_n"] else None,
                "schools": len(mine),
                "schools_reached": sum(1 for i in mine if i in reached[k]),
                "schools_on_network": sum(1 for i in mine if i in on_net),
            }
    base_reached = reached["today"]

    # Named streets.
    def street_list(picks):
        by = collections.OrderedDict()
        for c in picks:
            ch = chunks[c]
            s = by.setdefault(ch["street"], {"street": ch["street"], "miles": 0.0, "chunks": []})
            s["miles"] += ch["m"] / MILE
            s["chunks"].append({"from_to": ch["from_to"], "miles": round(ch["m"] / MILE, 2), "cnns": ch["cnns"]})
        for s in by.values():
            s["miles"] = round(s["miles"], 2)
        return list(by.values())

    out_rows = []
    for k in keys:
        m = dict(metrics[k])
        m["key"] = k
        m["brought_under_15"] = metrics["today"]["over_15"] - metrics[k]["over_15"]
        m["share_of_today_over"] = round(m["brought_under_15"] / float(metrics["today"]["over_15"]), 4) if metrics["today"]["over_15"] else None
        new = sorted(reached[k] - base_reached)
        m["schools_newly_reached"] = [schools[i]["name"] for i in sorted(new, key=lambda i: schools[i]["name"])]
        m["by_area"] = by_area[k]
        for gname in AREAS:
            m["by_area"][gname]["brought_under_15"] = by_area["today"][gname]["over_15"] - by_area[k][gname]["over_15"]
        meta = scen_meta.get(k)
        if meta:
            m.update({x: meta[x] for x in ("strategy", "budget_mi", "spent_mi")})
            if meta["strategy"] in ("corridor", "equity-first"):
                m["streets"] = street_list(meta["picks"])
                m["chunks"] = meta["picks"]
                m["greedy_children"] = meta["greedy_children"]
            elif meta["strategy"] == "last-block":
                m["schools_connected"] = len(meta["schools"])
                m["all_schools_linked"] = len(meta["schools"]) == len(link_order)
                m["links"] = [{"school": schools[i]["name"], "link_mi": round(link_mi[i], 3)} for i in meta["schools"]]
            else:
                m["streets"] = meta["streets"]
                m["file"] = meta["file"]
        out_rows.append(m)

    # The greedy order with names.
    greedy_out = [dict(s, street=chunks[s["chunk"]]["street"], from_to=chunks[s["chunk"]]["from_to"],
                       cnns=chunks[s["chunk"]]["cnns"]) for s in seq]
    equity_out = [dict(s, street=chunks[s["chunk"]]["street"], from_to=chunks[s["chunk"]]["from_to"],
                       cnns=chunks[s["chunk"]]["cnns"]) for s in eq_seq]
    pos = {i: k for k, (i, _m, _es, _c) in enumerate(link_order)}
    link_cnns = {i: c for i, _m, _es, c in link_order}
    link_rows = [{"school": schools[i]["name"], "private": schools[i]["private"], "cnns": link_cnns.get(i, []),
                  "order": pos.get(i), "link_mi": 0.0 if i in on_today else (round(link_mi[i], 3) if i in link_mi else None),
                  "on_network_today": i in on_today} for i in range(len(schools))]
    link_rows.sort(key=lambda r: (r["order"] is None, r["order"] if r["order"] is not None else 0, r["school"]))
    summary = {
        "model": {"target_minutes": ST.TARGET_MIN, "walk_mph": ST.WALK_MPH, "ride_mph": ST.RIDE_MPH, "detour_cap": ST.DETOUR,
                  "metric_exact_to_minutes": METRIC_MAX_MIN, "connector_tolerance_m": CONNECTOR_TOL_M,
                  "miles": "centerline: each block's traced line length, one count per block whatever its directions",
                  "chunk_target_mi": CHUNK_MI, "budgets_mi": BUDGETS, "sampled_every": a.sample or 1,
                  "greedy_optimises": "children brought under 15 minutes per mile; trip time and exposure are reported, not optimised"},
        "baseline": {"children": total_kids, "over_15_today": metrics["today"]["over_15"],
                     "over_15_today_school_travel_time": today_over, "candidate_block_levels": len(cand),
                     "candidate_children": sum(cand_kids.values()),
                     "candidate_children_ej": sum(cand_kids_ej.values()),
                     "ej": "SF Planning's Environmental Justice Communities map (DataSF y6ci-vpnb), score %d to %d" % (EJ_MIN, EJ_MAX)},
        "candidates": {"gap_runs": len(groups), "chunks": len(chunks), "chunk_miles": round(sum(c["m"] for c in chunks) / MILE, 2),
                       "chunks_without_walk_edges": sum(1 for c in chunks if not c["edges"]),
                       "chunks_touching_a_candidate": len(pairs_of_chunk),
                       "chunk_block_level_pairs": sum(len(v) for v in pairs_of_chunk.values()),
                       "schools": len(schools), "schools_on_network_today": sum(1 for r in link_rows if r["on_network_today"]),
                       "schools_without_link": sum(1 for r in link_rows if r["link_mi"] is None),
                       "last_block_miles_all_schools": round(sum(m for _i, m, _es, _c in link_order) / MILE, 2)},
        "scenarios": out_rows,
        "greedy_order": greedy_out,
        "equity_first_order": equity_out,
        "school_links": link_rows,
        "sources": {
            "model": "lib/school-travel-time.py (imported)",
            "base_times": "out/school-travel/blocks.json",
            "plan": "site/data/north-star/traced.geojson and status.json",
            "ej_communities": {"dataset": "https://data.sfgov.org/d/y6ci-vpnb", "blocks": "data/extract/ej-communities/blocks.json",
                               "read": ST.read(EJ_POLYS)["fetched_on"]},
            "cross_streets": {"dataset": "https://data.sfgov.org/d/" + CENTERLINES, "queried": cl.fetched_on.isoformat()},
        },
    }
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(a.out or os.path.join(OUT, "budget.json"), summary, indent=1)
    for r in out_rows:
        e, o = r["by_area"]["ej"], r["by_area"]["rest"]
        print("  %-24s over15 %6d  under+ %5d  p50 %s p90 %s  exp p50 %.2f  ends %.1f%%  schools+ %d | EJ under+ %d share %.3f "
              "reached %d on %d | rest under+ %d share %.3f reached %d on %d" % (
                  r["key"], r["over_15"], r["brought_under_15"], r["trip_min"]["p50"], r["trip_min"]["p90"],
                  r["exposure_mi"]["p50"], 100 * r["share_entire_route_on_network"], len(r["schools_newly_reached"]),
                  e["brought_under_15"], e["mean_share_of_route_on_network"] or 0, e["schools_reached"], e["schools_on_network"],
                  o["brought_under_15"], o["mean_share_of_route_on_network"] or 0, o["schools_reached"], o["schools_on_network"]))
    print("  wrote out/school-budget/budget.json (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
