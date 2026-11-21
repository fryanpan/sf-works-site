#!/usr/bin/env python3
"""Rank the Biking and Rolling Plan's unbuilt all-ages segments citywide by students they bring within a safe bike trip.

School Trips' bike network switch. Bryan, 2026-10-09: candidates are the plan's all-ages segments only; the baseline is today's
all-ages network plus every upcoming SFMTA bikeway (site/data/bike-history/planned.json); every other case adds
segments to that baseline.

CANDIDATES. The plan blocks lib/school-travel-time.py's all_ages_lines() draws (Separated, Car-free,
Shared-use Path, Shared) whose north-star status is none, short or partial (site/data/north-star/status.json:
"met: every direction row carries what the plan draws"), less any block an upcoming SFMTA project builds. Each
street's touching blocks are joined into chunks of about CHUNK_MI centerline miles.

COST. Each block costs its plan facility's central figure per centerline mile in data/school-budget/unit-costs.json
(Separated 1.5, Shared 0.25 as calmed, Shared-use Path 0.72, Car-free 0.8, $M a mile). Those rates come from
SFMTA budgets that already include design, so no per-project design cost is added (Bryan, 2026-10-11: "I think the
$150k double counts. Let's drop it from all costs."). A chunk shorter than MIN_COST_MI is priced as MIN_COST_MI,
so a one-block leftover is not nearly free. Bryan, 2026-10-09: rank per dollar.

SCORE. A chunk's gain is the students who drive today (the sim's expected count times today's car share, every
grade, so gain per dollar ranks students out of cars per dollar) whose trip to a school within
NEAR_MI of the chunk newly passes the bike switch test when the chunk is added: the bike within 5 minutes of the
car and the route's total gap off the network at most 1,000 ft, as tools/school-trips/school-sim.py's switch_ok. Gain per
dollar ranks the chunks; the list stops once it holds both MAX_MI (50) centerline miles and MAX_COST_M ($40M),
and is scored at 10, 25 and 50 miles and at $5M, $10M, $20M and $40M (the chunks that fit in each budget). Each round adds the best chunk to the network, and every later chunk is scored
on the network holding all chunks above it, so a student counts once.

SPEED. Routes use school-sim.py's _bike with its route tree vectorised (_tree_fast, checked equal to _tree on
every run's first school) and, while ranking, two of its four gap weights (RANK_GAP_K). Only students within
the near-miss band (bike within 5 minutes of the car on today's route plus DETOUR slack, gap over 1,000 ft)
can gain, so a school with none is skipped. Ranking is lazy: a chunk's gain only falls as others are added
(apart from a pair that only helps together), so each round rescores only the chunks at the top of the list.
The ranked networks at 10, 25 and 50 miles are then scored again with the full _bike.

Four more cuts, the first three exact. (1) Every search with k > 0 stops at the weighted cost a route of
SEARCH_MAX_MIN (30) minutes' riding at bike_minutes()'s speed can have and still be a candidate, (1 + k) x DETOUR x its
metres (Bryan, 2026-10-14): a student whose shortest bike route is under 30 minutes gets the same answer, checked on
three schools every run. (2) The k = 0 search reads no all-ages network (its weight is Lw x (1 + 0 x unsafe)), so each
worker runs it once per school and reuses it for every chunk. (3) The baseline's answer at a school depends only on
the chunks already added, so each worker keeps it per (school, chunks added) through the lazy rescoring. (4), not
exact: a school scores only the chunks with an edge within SEGMENTS_CORRIDOR_FT (1,000 ft) of some near-miss student's
best route on the baseline, as its search tree draws it. The environment variable of that name overrides it.

PARALLEL RULE. With SEGMENTS_OFFPLAN=1, an off-plan block is dropped when an all-ages street, built (today's network
and the upcoming SFMTA bikeways) or on the plan, runs parallel to it one block over (Bryan, 2026-10-14): an all-ages
walk edge within PARALLEL_DEG (20) degrees of the block's bearing, between PARALLEL_MIN_FT and ONE_BLOCK_FT off its
line, the edges together covering PARALLEL_OVERLAP of its length. "One block over" is measured on each side of each block
(next_street_reach()): the reach is NEXT_STREET_X (1.5) times the offset of the nearest parallel street of another name
on that side, at least ONE_BLOCK_FT (500) and at most NEXT_STREET_MAX_FT (1,000), so it passes the next street and stops
short of the one after on a regular grid. A side with no parallel street within 1,000 ft reaches 500 ft. A fixed 500 ft
missed the Richmond and Sunset's east-west streets, about 700 ft apart, and let Balboa through beside the plan's Cabrillo
(Bryan, 2026-10-18: "When we pick streets like Balboa but not Cabrillo which is immediately one block over and parallel
that looks wrong."). Offsets from 3psu-pn9h centerlines, parallel within 20 degrees, overlapping half the length.

Run by tools/school-trips/school-sim.py --segments, which passes the sim's cells and trip times."""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import math
import os
import time

import numpy as np

CHUNK_MI = 1.0
NEAR_MI = 2.0
RANK_GAP_K = (0.0, 4.0)
MAX_MI = 50.0
MAX_COST_M = 40.0
BUDGETS_M = (5, 10, 20, 40)
MIN_COST_MI = 0.25  # the shortest length a chunk is priced at; our assumption
MILESTONES = (10, 25, 50)
STATUS_TODO = ("none", "short", "partial")
# SEGMENTS_OFFPLAN=1 adds every street block the plan does not draw as all-ages to the candidates (Bryan, 2026-10-14: "are there
# street segments not in BrP"), written to out/school-sim/segments-offplan.json beside the plan-only ranking.
OFFPLAN = os.environ.get("SEGMENTS_OFFPLAN") == "1"
# What a chunk is ranked on, per dollar. "gapfeet" (Bryan, 2026-10-14: "give streets credit for the number of people
# feet of gap closed"): over students who drive today and pass the switch test's time half but not its gap half,
# the feet the chunk removes from their route's excess gap, its total off the network beyond the 1,000 ft limit, so a
# stretch that closes part of a route's gap counts while the route still misses (Bryan, 2026-10-14: "each segment might
# bring no students on board but if it's a critical bridge or articulation point then it's important"). "passing": students newly passing the whole test. Milestones are scored on the
# whole test either way.
SCORE = os.environ.get("SEGMENTS_SCORE", "gapfeet")
OFF_CALMED, OFF_SEPARATED = "Off-plan calmed", "Off-plan separated"
# A plan block drawn as Shared on a collector or arterial (3psu-pn9h classcode 2, 3 or 4) is priced and built as a
# separated lane: a calmed shared street isn't all-ages on a fast multi-lane road (Bryan, 2026-10-14: "you can upgrade
# unprotected infra on roads with a lot of traffic to fully separated"). On a residential street it stays calmed.
PLAN_UPGRADED = "Plan shared, upgraded to separated"
PLAN_UPGRADE_CLASSES = {"2", "3", "4"}
OFF_RESIDENTIAL = {"5", "0"}
OFF_SKIP = {"1", "6"}
# 3psu-pn9h's layer for a street the city runs as a street. The others are stairs and pedestrian ways (STREETS_PEDESTRI),
# paper and unaccepted rights of way (PAPER, PAPER_FWYS, PAPER_WATER, UPROW), private roads (PRIVATE, PRIVATE_PARKING),
# park roads (PARKS, PARKS_NPS_*), freeways and the islands; none of them is a street SFMTA can calm or stripe for a ride
# to school, so none is an off-plan candidate.
OFF_LAYERS = {"STREETS"}
# Bryan, 2026-10-18, "Fix all three" on the report's self-review: a street a Muni line runs along is priced and built as
# a separated lane, on the plan or off it, since calming a bus or rail street with diverters isn't an option; and a
# block steeper than MAX_GRADE_PCT is no candidate at all (his slope rule, 2026-10-14, ignores grade "unless the grade
# is extreme"). data/muni-streets/blocks.json and data/street-grades/grades.json, from tools/muni/muni-streets.py and
# scripts/street-grades.py.
MAX_GRADE_PCT = 20.0
SEARCH_MAX_MIN = 30.0
SEGMENTS_CORRIDOR_FT = float(os.environ.get("SEGMENTS_CORRIDOR_FT", "1000"))
PARALLEL_DEG = 20.0
ONE_BLOCK_FT = 500.0     # the reach on a side with no parallel street of another name within NEXT_STREET_MAX_FT
NEXT_STREET_X = 1.5      # a side's reach is this times its nearest parallel street's offset: past the next street, short of the one after
NEXT_STREET_MAX_FT = 1000.0
PARALLEL_MIN_FT = 40.0   # nearer than this is the block's own street (a side path), not the next one over: our assumption
PARALLEL_OVERLAP = 0.5   # our assumption
# Switches for the timing runs only; every one is on in a real run.
OPT = {"cap": True, "k0": True, "base": True, "corridor": True}


def dijkstra_limited(sim):
    """sim._dijkstra with scipy's limit: nodes costing more than it come back unreached (dist inf)."""

    def _dijkstra(w_edge, seeds, seed_cost, limit=np.inf):
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        W = sim._W
        n, eu, ev = W["n"], W["eu"], W["ev"]
        ok = np.isfinite(w_edge)
        eid = np.flatnonzero(ok)
        rows = np.concatenate([eu[ok], ev[ok], np.full(len(seeds), n)])
        cols = np.concatenate([ev[ok], eu[ok], np.asarray(seeds, dtype=np.int64)])
        data = np.concatenate([w_edge[ok], w_edge[ok], np.asarray(seed_cost, dtype=float)]) + 1e-6
        ref = np.concatenate([eid, eid, -1 - np.arange(len(seeds))])
        key = rows * (n + 1) + cols
        o = np.lexsort((data, key))
        key, rows, cols, data, ref = key[o], rows[o], cols[o], data[o], ref[o]
        first = np.r_[True, key[1:] != key[:-1]]
        key, rows, cols, data, ref = key[first], rows[first], cols[first], data[first], ref[first]
        M = csr_matrix((data, (rows, cols)), shape=(n + 1, n + 1))
        dist, pred = dijkstra(M, directed=True, indices=n, return_predecessors=True, limit=limit)
        return dist, pred, (key, ref)
    return _dijkstra


def bike_fast(sim):
    """sim._bike, plus: k0 (bike_k0's search, reused), cap_m (each k > 0 search stops at (1 + k) x DETOUR x cap_m, the
    most a candidate route of cap_m metres can cost), and trace (each block's chosen tree and join node). Same outputs
    as sim._bike for every block whose shortest route is at most cap_m; checked in rank()."""
    dij = dijkstra_limited(sim)
    pick_fast = block_pick_fast(sim)

    def door_of(door):
        steps = sim._W["steps"]
        return [d for d in door if not steps[d[3]]] or door

    def bike_k0(door):
        bd = door_of(door)
        return dij(np.where(sim._W["steps"], np.inf, sim._W["Lw"]), [d[0] for d in bd], [d[1] + d[2] for d in bd])

    def _bike(safe, door, walk, k0=None, cap_m=None, trace=False, gap=None):
        """With gap (metres), the result carries a fourth item whose "ex" is each block's excess gap (m) on its chosen
        route: its total off the network (sim._route_off) beyond gap."""
        W = sim._W
        steps, F = W["steps"], W["flat"]
        bd = door_of(door)
        un_e = ~safe
        cand, trees, exs = [], [], []
        assert sim.GAP_K[0] == 0.0
        for k in sim.GAP_K:
            s_len = [d[1] + d[2] for d in bd]
            s_un = [bool(un_e[d[3]]) for d in bd]
            if k == 0 and k0 is not None:
                dist, pred, lk = k0
            else:
                w = np.where(steps, np.inf, W["Lw"] * (1 + k * un_e))
                s_cost = [d[1] * (1 + k) + d[2] * (1 + k * u) for d, u in zip(bd, s_un)]
                lim = np.inf if cap_m is None or k == 0 else (1 + k) * sim.DETOUR * cap_m * (1 + 1e-6) + 1.0
                dist, pred, lk = dij(w, [d[0] for d in bd], s_cost, lim)
            s_run = [sl if u else 0.0 for sl, u in zip(s_len, s_un)]
            s_max = [sl if u else d[1] for sl, u, d in zip(s_len, s_un, bd)]
            ln, run, mx = sim._tree(dist, pred, lk, s_len, s_run, s_max, safe)[:3]
            ue = un_e[F["e"]] | steps[F["e"]]
            w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
            pick = pick_fast(F, dist[:-1], w_end)
            pi = np.maximum(pick, 0)
            nd = F["node"][pi]
            m = np.where(pick >= 0, ln[nd] + F["c"][pi] + F["al"][pi], np.inf)
            g = np.where(pick >= 0, sim._route_off(dist, pred, lk, bd, un_e, F, pi, nd, ue), np.inf)
            if gap is not None:
                exs.append(np.where(pick >= 0, np.maximum(g - gap, 0.0), np.inf))
            cand.append((m, g))
            if trace:
                trees.append((pred, np.where(pick >= 0, nd, -1)))
        m0 = cand[0][0]
        best_m, best_g = m0.copy(), cand[0][1].copy()
        which = np.zeros(len(m0), dtype=np.int64)
        for i, (m, g) in enumerate(cand[1:], 1):
            with np.errstate(invalid="ignore"):
                ok = np.isfinite(m) & (m <= sim.DETOUR * m0 + 1e-6) & ((g < best_g - 1e-6) | ((np.abs(g - best_g) <= 1e-6) & (m < best_m)))
            best_m = np.where(ok, m, best_m)
            best_g = np.where(ok, g, best_g)
            which = np.where(ok, i, which)
        nobike = ~np.isfinite(best_m)
        out = (np.where(nobike, walk, best_m), np.where(nobike, walk, best_g), int(nobike.sum()))
        if trace or gap is not None:
            info = {"which": which, "trees": trees, "m0": m0}
            if gap is not None:
                xs = np.choose(which, exs) if len(exs) > 1 else exs[0]
                info["ex"] = np.where(nobike, np.maximum(walk - gap, 0.0), xs)
            return out + (info,)
        return out
    return _bike, bike_k0


def next_street_reach():
    """{cnn: (ux, uy, reach_left, reach_right)} in feet for every active 3psu-pn9h street block: the block's unit direction,
    first point to last, and how far "one block over" reaches on its left (the side of (-uy, ux)) and its right (the
    PARALLEL RULE in the docstring). Cached on the function."""
    if getattr(next_street_reach, "cache", None) is not None:
        return next_street_reach.cache
    import sfdata
    from scipy.spatial import cKDTree
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,classcode,layer,line", where="active='true'", floor=15000)
    lat0 = math.radians(37.76)
    fx, fy = 364320.0 * math.cos(lat0), 364320.0
    C, A, B, N = [], [], [], []
    for row in r.rows:
        c = str(row.get("cnn") or "").split(".")[0].lstrip("0")
        g = row.get("line")
        if not c or not isinstance(g, dict) or str(row.get("classcode") or "") in OFF_SKIP or row.get("layer") not in OFF_LAYERS:
            continue
        parts = [g.get("coordinates")] if g.get("type") == "LineString" else (g.get("coordinates") or [])
        pts = max((q for q in parts if q and len(q) >= 2), key=len, default=None)
        if not pts:
            continue
        C.append(c)
        A.append((pts[0][0] * fx, pts[0][1] * fy))
        B.append((pts[-1][0] * fx, pts[-1][1] * fy))
        N.append((row.get("street") or row.get("streetname") or "").strip().upper())
    A, B, N = np.array(A), np.array(B), np.array(N)
    L = np.hypot(*(B - A).T)
    L[L < 1.0] = 1.0
    U = (B - A) / L[:, None]
    M = (A + B) / 2
    tree = cKDTree(M)
    cos_lim = math.cos(math.radians(PARALLEL_DEG))
    out = {}
    for k in range(len(C)):
        u, nrm = U[k], np.array([-U[k][1], U[k][0]])
        reach = [ONE_BLOCK_FT, ONE_BLOCK_FT]
        if L[k] >= 30.0:
            ix = np.array(tree.query_ball_point(M[k], L[k] / 2 + NEXT_STREET_MAX_FT), dtype=np.int64)
            ix = ix[(N[ix] != N[k]) & (np.abs(U[ix] @ u) >= cos_lim)]
            if len(ix):
                off = (M[ix] - A[k]) @ nrm
                t0, t1 = (A[ix] - A[k]) @ u, (B[ix] - A[k]) @ u
                cov = np.minimum(np.maximum(t0, t1), L[k]) - np.maximum(np.minimum(t0, t1), 0.0)
                ok = (cov >= PARALLEL_OVERLAP * min(L[k], 400.0)) & (np.abs(off) >= PARALLEL_MIN_FT) & (np.abs(off) <= NEXT_STREET_MAX_FT)
                for side, sel in ((0, off > 0), (1, off < 0)):
                    o = np.abs(off[ok & sel])
                    if len(o):
                        reach[side] = float(min(NEXT_STREET_MAX_FT, max(ONE_BLOCK_FT, NEXT_STREET_X * o.min())))
        out[C[k]] = (float(u[0]), float(u[1]), reach[0], reach[1])
    next_street_reach.cache = out
    return out


def parallel_drop(sim, stt, cand, e_c, plan):
    """The off-plan keys an all-ages street runs parallel to one block over (the PARALLEL RULE in the docstring)."""
    from scipy.spatial import cKDTree
    W = sim._W
    net = W["net"]
    e_plan = stt.edges_of(net, plan, cache=True)[0]
    aa = W["safe"].copy()
    for es in e_plan.values():
        aa[list(es)] = True
    ae = np.flatnonzero(aa)
    X, Y = np.asarray(W["x"], dtype=float), np.asarray(W["y"], dtype=float)
    pa = np.c_[X[W["eu"][ae]], Y[W["eu"][ae]]]
    pb = np.c_[X[W["ev"][ae]], Y[W["ev"][ae]]]
    el = np.hypot(*(pb - pa).T)
    keep = el > 1.0
    ae, pa, pb, el = ae[keep], pa[keep], pb[keep], el[keep]
    eu_ = (pb - pa) / el[:, None]
    tree = cKDTree((pa + pb) / 2)
    cos_lim = math.cos(math.radians(PARALLEL_DEG))
    lo, hi = PARALLEL_MIN_FT * sim.FT, NEXT_STREET_MAX_FT * sim.FT
    nsr = next_street_reach()
    drop = {}
    for k, pts in cand:
        if not k.startswith("op:"):
            continue
        P = np.array([W["walknet"].xy(*q[:2]) for q in pts])
        a, b = P[0], P[-1]
        Lb = float(np.hypot(*(b - a)))
        if Lb < 10.0:
            continue
        u = (b - a) / Lb
        nrm = np.array([-u[1], u[0]])
        ix = np.array(tree.query_ball_point((a + b) / 2, Lb / 2 + hi), dtype=np.int64)
        if not len(ix):
            continue
        own = e_c.get(k, set())
        ix = ix[[ae[i] not in own for i in ix]]
        if not len(ix):
            continue
        par = np.abs(eu_[ix] @ u) >= cos_lim
        soff = (((pa[ix] + pb[ix]) / 2) - a) @ nrm
        off = np.abs(soff)
        r = nsr.get(k.split(":")[-1].lstrip("0"))
        if r is None:
            rl = rr = ONE_BLOCK_FT
        else:
            # the walk network's x, y and the lon/lat feet frame share their handedness, so a reversed block swaps sides
            rl, rr = (r[2], r[3]) if np.dot(u, r[:2]) >= 0 else (r[3], r[2])
        ix = ix[par & (off >= lo) & (off <= np.where(soff > 0, rl, rr) * sim.FT)]
        if not len(ix):
            continue
        t = np.sort(np.c_[(pa[ix] - a) @ u, (pb[ix] - a) @ u], axis=1).clip(0.0, Lb)
        t = t[np.argsort(t[:, 0])]
        cov, end = 0.0, 0.0
        for t1, t2 in t:
            t1 = max(t1, end)
            if t2 > t1:
                cov += t2 - t1
                end = t2
        if cov >= PARALLEL_OVERLAP * Lb:
            off_all = np.abs((((pa[ix] + pb[ix]) / 2) - a) @ nrm)
            drop[k] = round(float(off_all.min()) / sim.FT)
    return drop


def tree_fast(sim):
    """sim._tree, vectorised by pointer doubling over the shortest-path tree. Same outputs."""

    def _tree(dist, pred, lookup, seed_len, seed_run, seed_max, safe, gap=None, seed_ex=None):
        W = sim._W
        n, L = W["n"], W["L"]
        key, ref = lookup
        reach = np.flatnonzero(np.isfinite(dist[:n]))
        p = pred[reach].astype(np.int64)
        k = np.searchsorted(key, p * (n + 1) + reach)
        r = ref[k]
        idx = np.full(n, -1, dtype=np.int64)
        idx[reach] = np.arange(len(reach))
        m = len(reach)
        seed = r < 0
        par = np.where(seed, np.arange(m), idx[np.where(seed, 0, p)])
        le = np.where(seed, 0.0, L[np.maximum(r, 0)])
        un = np.where(seed, True, ~safe[np.maximum(r, 0)])
        tot = le.copy()
        allu = un.copy()
        top = np.where(un, le, 0.0)
        bot = top.copy()
        mx = top.copy()
        ex = np.zeros(m)   # excess beyond gap of the runs closed on both sides inside the stretch
        exf = (lambda v: np.maximum(v - gap, 0.0)) if gap is not None else (lambda v: 0.0)
        anc = par.copy()
        for _ in range(64):
            if np.array_equal(anc, anc[anc]) and np.all(seed[anc]):
                break
            Ut, Ua, Utop, Ubot, Umx, Uex = tot[anc], allu[anc], top[anc], bot[anc], mx[anc], ex[anc]
            # combine upper (towards the door) with lower (this node's own stretch)
            nbot = np.where(allu, tot + Ubot, bot)
            ntop = np.where(Ua, Ut + top, Utop)
            nmx = np.maximum(np.maximum(Umx, mx), Ubot + top)
            if gap is not None:
                ex = np.where(Ua, ex, np.where(allu, Uex, Uex + ex + exf(Ubot + top)))
            tot, allu, top, bot, mx = Ut + tot, Ua & allu, ntop, nbot, nmx
            anc = anc[anc]
        s = -1 - r[anc]
        sl, sr, sm = (np.asarray(x, dtype=float)[s] for x in (seed_len, seed_run, seed_max))
        ln_o = np.full(n, np.inf)
        run_o = np.zeros(n)
        mx_o = np.zeros(n)
        ln_o[reach] = sl + tot
        run_o[reach] = np.where(allu, sr + tot, bot)
        mx_o[reach] = np.maximum(np.maximum(sm, mx), sr + top)
        if gap is None:
            return ln_o, run_o, mx_o
        se = np.asarray(seed_ex, dtype=float)[s]
        ex_o = np.zeros(n)
        ex_o[reach] = se + np.where(allu, 0.0, ex + exf(sr + top))
        return ln_o, run_o, mx_o, ex_o

    return _tree


def tree_excess_slow(sim, dist, pred, lookup, seed_len, seed_run, seed_ex, safe, gap):
    """Reference for tree_fast's excess, node by node in distance order: the closed off-network runs' feet beyond gap."""
    n, L = sim._W["n"], sim._W["L"]
    key, ref = lookup
    reach = np.flatnonzero(np.isfinite(dist[:n]))
    order = reach[np.argsort(dist[reach], kind="stable")]
    p = pred[order]
    r = ref[np.searchsorted(key, p.astype(np.int64) * (n + 1) + order)]
    run, ex = np.zeros(n).tolist(), np.zeros(n).tolist()
    for v, pv, rv in zip(order.tolist(), p.tolist(), r.tolist()):
        if rv < 0:
            run[v], ex[v] = seed_run[-1 - rv], seed_ex[-1 - rv]
        elif not safe[rv]:
            run[v], ex[v] = run[pv] + L[rv], ex[pv]
        else:
            run[v], ex[v] = 0.0, ex[pv] + max(run[pv] - gap, 0.0)
    return np.array(ex)


def block_pick_fast(sim):
    """sim._block_pick for the student blocks' joins, by a minimum over each block's contiguous joins instead of a sort.
    Same answer: the first join, in F's order, at the block's least cost."""
    F = sim._W["flat"]
    own = F["own"]
    assert np.all(np.diff(own) >= 0)
    starts = np.flatnonzero(np.r_[True, own[1:] != own[:-1]])
    gid = np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, len(own)]))

    def _block_pick(F2, node_cost, w_end):
        if F2 is not F:
            return sim._block_pick(F2, node_cost, w_end)
        k = node_cost[F["node"]] + w_end
        mn = np.minimum.reduceat(k, starts)
        pos = np.flatnonzero(k == mn[gid])
        g = gid[pos]
        first = pos[np.r_[True, g[1:] != g[:-1]]]
        first = first[np.isfinite(k[first])]
        out = np.full(F["n"], -1, dtype=np.int64)
        out[own[first]] = first
        return out
    return _block_pick


def muni_streets():
    """{cnn: [route names]} for every street block a Muni route runs along."""
    return json.load(open(os.path.join(paths.ROOT, "data", "muni-streets", "blocks.json")))["blocks"]


def steep_blocks():
    """The CNNs steeper than MAX_GRADE_PCT, on the block's steepest stretch where the grades file carries one."""
    g = json.load(open(os.path.join(paths.ROOT, "data", "street-grades", "grades.json")))["blocks"]
    return {str(c).lstrip("0") for c, v in g.items() if (max(v) if isinstance(v, list) else v) > MAX_GRADE_PCT}


def street_classes():
    """3psu-pn9h's classcode for every active street block, by CNN: the rule offplan_lines() and the plan's Shared
    upgrade both read."""
    import sfdata
    r = sfdata.fetch("3psu-pn9h", select="cnn,classcode", where="active='true'", floor=15000)
    return {str(row.get("cnn") or "").split(".")[0].lstrip("0"): str(row.get("classcode") or "") for row in r.rows}


def brp_unprotected_alternates(stt, cls, have, pl_cnn, meta):
    """[(key, pts)] for plan blocks on classcode 2, 3 or 4 whose existing bikeway is unprotected and not all-ages (no
    Class I or IV, and not a Slow Street, which counts whatever its BCI: painted and signed lanes never count, Bryan 2026-10-15), not already a
    candidate and not built by an upcoming SFMTA project; each is added to meta as PLAN_UPGRADED."""
    seg = stt.read(stt.BIKE, "segments.json")
    comp = stt.read(stt.BIKE, "components.json")["blocks"]
    last = len(seg["years"]) - 1
    lane = {}
    for s in seg["segments"]:
        if s["y"][last] == "0":
            continue
        c = comp.get(s["key"])
        if not c:
            continue
        codes = set(c["m"]) | ({"S"} if c.get("s") is not None else set())
        lane[str(s["key"]).lstrip("0")] = (codes, s.get("bci"))
    out = []
    for f in stt.read(stt.NS, "traced.geojson")["features"]:
        p = f["properties"]
        cnn = str(p["cnn"])
        key = "ns:%s" % cnn
        got = lane.get(cnn.lstrip("0"))
        if key in have or cnn in pl_cnn or not got or cls.get(cnn.lstrip("0")) not in PLAN_UPGRADE_CLASSES:
            continue
        codes, bci = got
        if codes & stt.PROTECTED_CODES or not codes & {"2b", "2c", "3b", "3c", "S"}:
            continue
        if "S" in codes:
            continue   # a Slow Street counts as all ages today (Bryan 2026-10-18), so it has nothing to upgrade
        if len(f["geometry"]["coordinates"]) < 2:
            continue
        meta[key] = {"cnn": cnn, "street": p["street"], "facility": PLAN_UPGRADED, "status": "not all-ages"}
        out.append((key, f["geometry"]["coordinates"]))
        have.add(key)
    return out


def offplan_lines(sim, stt, meta, pl_cnn, muni=()):
    """Every street block the plan does not draw as all-ages, as [(key, pts)], with its meta added to meta. Residential blocks
    (3psu-pn9h classcode 5 or 0) are calmed; collectors and arterials (2, 3, 4) get a separated lane. Freeways and
    ramps (1, 6) are left out, and so is every block outside the STREETS layer (OFF_LAYERS). A block already all-ages today simply adds nothing when it is scored."""
    import sfdata
    # Blocks the plan draws as all-ages are already candidates. A block it draws as a painted lane, or not at all,
    # is beyond the plan.
    plan_cnn = {m["cnn"] for m in meta.values()}
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,classcode,layer,line", where="active='true'", floor=15000)
    out = []
    for row in r.rows:
        c = str(row.get("cnn") or "").split(".")[0].lstrip("0")
        cls, g = str(row.get("classcode") or ""), row.get("line")
        if (not c or c in plan_cnn or c in pl_cnn or cls in OFF_SKIP or row.get("layer") not in OFF_LAYERS
                or not isinstance(g, dict)):
            continue
        parts = [g.get("coordinates")] if g.get("type") == "LineString" else (g.get("coordinates") or [])
        pts = max((q for q in parts if q and len(q) >= 2), key=len, default=None)
        if not pts:
            continue
        key = "op:%s" % c
        name = (row.get("streetname") or "%s %s" % (row.get("street") or "", row.get("st_type") or "")).strip()
        meta[key] = {"cnn": c, "street": name, "facility": OFF_CALMED if cls in OFF_RESIDENTIAL and c not in muni else OFF_SEPARATED,
                     "status": None}
        out.append((key, pts))
    print("  segments: %d off-plan blocks added as candidates" % len(out))
    return out


def chunks(sim, stt):
    """The candidate chunks: [{id, street, cnns, mi, edges, x, y}], and the planned projects' edges."""
    W = sim._W
    net = W["net"]
    _today, plan, meta = stt.all_ages_lines(brp_rule=True)
    planned = json.load(open(os.path.join(sim.ROOT, "site", "data", "bike-history", "planned.json")))
    pl_cnn = set()
    pl_lines = []
    for pr in planned["projects"]:
        for b in pr["blocks"]:
            pl_cnn.add(str(b["cnn"]))
            if len(b.get("pts") or []) >= 2:
                pl_lines.append(("pl:%s" % b["cnn"], b["pts"]))
    cand = [(k, pts) for k, pts in plan if meta[k]["status"] in STATUS_TODO and meta[k]["cnn"] not in pl_cnn]
    cls = street_classes()
    muni = set(muni_streets())
    up = [k for k, _p in cand if meta[k]["facility"] == "Shared" and (cls.get(meta[k]["cnn"].lstrip("0")) in PLAN_UPGRADE_CLASSES
                                                                    or meta[k]["cnn"].lstrip("0") in muni)]
    for k in up:
        meta[k] = dict(meta[k], facility=PLAN_UPGRADED)
    chunks.upgraded = sorted(meta[k]["cnn"] for k in up)
    print("  segments: %d plan Shared blocks on collectors or arterials priced as separated lanes" % len(up))
    # Bryan, 2026-10-14: "If there's bikeways in BrP that are not AAA on a busy street then we can consider building
    # separated bikeways there instead as an alternate." A plan block of any drawn type, Undecided included, on a
    # collector or arterial whose existing lane is unprotected and fails the all-ages test (BCI 80 or under, or a Slow
    # Street under it) gets a build-separated option. These are plan keys, so the off-plan parallel rule never drops them.
    have = {k for k, _p in cand}
    alt = brp_unprotected_alternates(stt, cls, have, pl_cnn, meta)
    cand += alt
    chunks.alternates = sorted(meta[k]["cnn"] for k, _p in alt)
    print("  segments: %d plan blocks with a non-all-ages lane on a collector or arterial added as separated lanes" % len(alt))
    if OFFPLAN:
        cand += offplan_lines(sim, stt, meta, pl_cnn, muni)
    steep = steep_blocks()
    n0 = len(cand)
    cand = [(k, pts) for k, pts in cand if meta[k]["cnn"].lstrip("0") not in steep]
    chunks.steep = n0 - len(cand)
    chunks.muni = sum(1 for k, _p in cand if meta[k]["cnn"].lstrip("0") in muni)
    print("  segments: %d candidate blocks over %.0f%% grade left out; %d candidates on a Muni street priced as separated"
          % (chunks.steep, MAX_GRADE_PCT, chunks.muni))
    e_c = stt.edges_of(net, cand)[0]
    if OFFPLAN:
        # an off-plan block whose walk edges are all-ages today has nothing to build
        safe = W["safe"]
        cand = [(k, pts) for k, pts in cand if not k.startswith("op:") or any(not safe[e] for e in e_c.get(k, ()))]
        n_op = sum(k.startswith("op:") for k, _p in cand)
        drop = parallel_drop(sim, stt, cand, e_c, plan)
        cand = [(k, pts) for k, pts in cand if k not in drop]
        chunks.parallel = {"offplanBlocks": n_op, "dropped": len(drop), "steep": chunks.steep, "muniSeparated": chunks.muni,
                           "droppedBlocks": sorted([meta[k]["street"], meta[k]["cnn"], ft] for k, ft in drop.items())}
        print("  segments: parallel rule drops %d of %d off-plan blocks (an all-ages street one block over)" % (len(drop), n_op))
    e_p = stt.edges_of(net, pl_lines)[0]
    planned_edges = np.array(sorted(set().union(*e_p.values())) if e_p else [], dtype=np.int64)
    cpts = dict(cand)
    xy = {k: np.array([W["walknet"].xy(*q) for q in pts]) for k, pts in cand}
    length = {k: float(np.hypot(*np.diff(a, axis=0).T).sum()) for k, a in xy.items()}
    by_street = {}
    for k, _pts in cand:
        by_street.setdefault(meta[k]["street"], []).append(k)
    out = []
    for street, keys in sorted(by_street.items()):
        # touching blocks (an end within 30 m of another's end) form a corridor
        ends = {k: (xy[k][0], xy[k][-1]) for k in keys}
        parent = {k: k for k in keys}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if min(np.hypot(*(p - q)) for p in ends[a] for q in ends[b]) <= 30.0:
                    parent[find(a)] = find(b)
        comps = {}
        for k in keys:
            comps.setdefault(find(k), []).append(k)
        for comp in comps.values():
            pts = np.vstack([xy[k] for k in comp])
            c = pts.mean(axis=0)
            u = np.linalg.svd(pts - c, full_matrices=False)[2][0] if len(pts) > 1 else np.array([1.0, 0.0])
            comp.sort(key=lambda k: float(((xy[k].mean(axis=0) - c) @ u)))
            tot = sum(length[k] for k in comp) / sim.MI
            n_chunks = max(1, int(round(tot / CHUNK_MI)))
            per = tot / n_chunks
            cur, acc = [], 0.0
            for k in comp:
                cur.append(k)
                acc += length[k] / sim.MI
                if acc >= per - 1e-9:
                    out.append((street, cur, acc))
                    cur, acc = [], 0.0
            if cur:
                out.append((street, cur, acc))
    ucj = json.load(open(os.path.join(sim.ROOT, "data", "school-budget", "unit-costs.json")))
    uc = ucj["types"]
    # The per-mile rates already include design. A chunk under MIN_COST_MI is priced as MIN_COST_MI of its blocks'
    # average rate; without a floor a single leftover block costs a few thousand dollars and tops the per-dollar
    # list (Fable review 2026-10-09: Corbett 0.04 mi, Diamond 0.02 mi).
    fac = {"Separated": "separated", "Shared": "calmed", "Shared-use Path": "path", "Car-free": "car_free",
           OFF_CALMED: "calmed", OFF_SEPARATED: "separated", PLAN_UPGRADED: "separated"}
    res = []
    for i, (street, ks, mi) in enumerate(out):
        es = np.array(sorted(set().union(*(e_c.get(k, set()) for k in ks))), dtype=np.int64)
        if not len(es) or mi <= 0:
            continue
        a = np.vstack([xy[k] for k in ks]).mean(axis=0)
        cost = sum(length[k] / sim.MI * uc[fac[meta[k]["facility"]]]["central"] for k in ks)
        if 0 < mi < MIN_COST_MI:
            cost *= MIN_COST_MI / mi
        calm = sum(length[k] for k in ks if meta[k]["facility"] == OFF_CALMED) / sim.MI
        res.append({"id": "c%03d" % len(res), "street": street, "cnns": [meta[k]["cnn"] for k in ks], "mi": round(mi, 3),
                    "calmMi": round(calm, 3),
                    "costM": round(cost, 3), "facilities": sorted(set(meta[k]["facility"] for k in ks)),
                    "edges": es, "x": float(a[0]), "y": float(a[1]), "pts": [cpts[k] for k in ks]})
    return res, planned_edges


_S = {}
_K0 = {}     # per worker: school -> its k = 0 search, the last K0_KEEP schools
_BASE = {}   # per worker: (school, chunks added) -> the baseline's (ok, gap ft)
K0_KEEP = 24


def _k0(j):
    if not OPT["k0"]:
        return None
    if j not in _K0:
        if len(_K0) >= K0_KEEP:
            _K0.pop(next(iter(_K0)))
        _K0[j] = _S["bike_k0"](_S["doors"][j])
    return _K0[j]


def _cap():
    return _S["cap_m"] if OPT["cap"] else None


def _school_job(args):
    """One school: students newly passing the switch test for each listed chunk, given the added edges."""
    j, chunk_ids, added = args
    sim, S = _S["sim"], _S
    door = S["doors"][j]
    base = S["base"].copy()
    if len(added):
        base[added] = True
    nm = S["near"][j]
    if not nm.any():
        return j, {c: (0.0, 0.0, 0.0) for c in chunk_ids}, 0.0
    walk = S["walk"][:, j]
    car = S["car"][:, j]
    n = S["w"][:, j]

    gap_ft = sim.CHANGES["bike_switch"]["gap_total_ft"]
    k0, cap = _k0(j), _cap()

    def ok(safe):
        bm, bg, _nb, info = S["bike"](safe, door, walk, k0, cap, gap=gap_ft * sim.FT)
        return (sim.bike_minutes(bm) - car <= sim.CHANGES["bike_switch"]["within_min"]) & (bg / sim.FT <= gap_ft), info["ex"] / sim.FT

    def excess(x):
        # feet of the route's total excess gap (every run's feet beyond the switch test's limit), near-miss students only
        return np.where(nm, x, 0.0)
    bkey = (j, len(added))
    if OPT["base"] and bkey in _BASE:
        ok0, g0 = _BASE[bkey]
    else:
        ok0, g0 = ok(base)
        if OPT["base"]:
            for kk in [kk for kk in _BASE if kk[1] != len(added)]:
                del _BASE[kk]
            _BASE[bkey] = (ok0, g0)
    x0 = excess(g0)
    out = {}
    for c in chunk_ids:
        sf = base.copy()
        sf[S["chunk_edges"][c]] = True
        ok1, g1 = ok(sf)
        passing = float((n * (ok1 & ~ok0)).sum())
        feet = float((n * np.maximum(x0 - excess(g1), 0.0)).sum())
        out[c] = (feet if SCORE == "gapfeet" else passing, passing, feet)
    return j, out, float((n * ok0).sum())


def _milestone_job(args):
    """One school, full GAP_K: students, and expected drivers, newly passing the switch test on each milestone network."""
    j, nets = args
    sim, S = _S["sim"], _S
    sim.GAP_K = S["full_k"]   # a worker forked while ranking still holds RANK_GAP_K
    door = S["doors"][j]
    walk, car = S["walk"][:, j], S["car"][:, j]
    k0 = S["bike_k0"](door) if OPT["k0"] else None
    cap = _cap()

    def ok(safe):
        bm, bg, _nb = S["bike"](safe, door, walk, k0, cap)
        return (sim.bike_minutes(bm) - car <= sim.CHANGES["bike_switch"]["within_min"]) & (bg / sim.FT <= sim.CHANGES["bike_switch"]["gap_total_ft"])
    ok0 = ok(S["base"])
    res = []
    for added in nets:
        sf = S["base"].copy()
        sf[added] = True
        new = ok(sf) & ~ok0
        res.append((float((S["n"][:, j] * new).sum()), float((S["w"][:, j] * new).sum())))
    return j, res


def _corridor_job(j):
    """One school: the chunks with a point within SEGMENTS_CORRIDOR_FT of a near-miss student's best route on the baseline."""
    from scipy.spatial import cKDTree
    sim, S = _S["sim"], _S
    W = sim._W
    nm = S["near"][j]
    bm, _bg, _nb, tr = S["bike"](S["base"], S["doors"][j], S["walk"][:, j], _k0(j), _cap(), trace=True)
    blocks = np.flatnonzero(nm & np.isfinite(tr["m0"]))
    n = W["n"]
    seen = np.zeros(n, dtype=bool)
    for ti, (pred, nd) in enumerate(tr["trees"]):
        f = np.unique(nd[blocks[tr["which"][blocks] == ti]])
        f = f[f >= 0]
        while len(f):
            seen[f] = True
            p = pred[f].astype(np.int64)
            p = p[(p >= 0) & (p < n)]
            f = np.unique(p[~seen[p]])
    xy = np.c_[np.asarray(W["x"], dtype=float)[seen], np.asarray(W["y"], dtype=float)[seen]]
    if not len(xy):
        return j, []
    cp, owner = S["chunk_pts"]
    d, _i = cKDTree(xy).query(cp, distance_upper_bound=SEGMENTS_CORRIDOR_FT * sim.FT)
    return j, sorted(set(owner[np.isfinite(d)].tolist()))


def check_fast(sim, sch, doors, walk, near_n, cap_m, n_schools=3):
    """The ranking's _bike (k0 reused, searches capped) against sim._bike on n_schools schools, on the baseline and on a
    network with every candidate edge added: identical for every block with students whose shortest route is at most
    cap_m. Returns the seconds each took."""
    t_old = t_new = 0.0
    S = _S
    for j in range(min(n_schools, len(sch))):
        k0 = S["bike_k0"](doors[j])
        for safe in (S["base"], S["all_cand"]):
            t = time.time()
            a = sim._bike(safe, doors[j], walk[:, j])
            t_old += time.time() - t
            t = time.time()
            b = S["bike"](safe, doors[j], walk[:, j], k0, cap_m, trace=True)
            t_new += time.time() - t
            sel = near_n[:, j] & (b[3]["m0"] <= cap_m)
            for x, y in zip(a[:2], b[:2]):
                assert np.array_equal(x[sel], y[sel]), "fast _bike differs from sim._bike at school %d" % j
    return t_old, t_new


def check_excess(sim, door, safe, gap):
    """tree_fast's total excess against the node-by-node reference, on one school's k = 4 tree."""
    W = sim._W
    steps = W["steps"]
    bd = [d for d in door if not steps[d[3]]] or door
    un_e = ~safe
    k = 4.0
    w = np.where(steps, np.inf, W["Lw"] * (1 + k * un_e))
    s_un = [bool(un_e[d[3]]) for d in bd]
    s_len = [d[1] + d[2] for d in bd]
    dist, pred, lk = sim._dijkstra(w, [d[0] for d in bd], [d[1] * (1 + k) + d[2] * (1 + k * u) for d, u in zip(bd, s_un)])
    s_run = [sl if u else 0.0 for sl, u in zip(s_len, s_un)]
    s_max = [sl if u else d[1] for sl, u, d in zip(s_len, s_un, bd)]
    s_ex = [0.0 if u else max(d[1] - gap, 0.0) for u, d in zip(s_un, bd)]
    fast = sim._tree(dist, pred, lk, s_len, s_run, s_max, safe, gap, s_ex)[3]
    slow = tree_excess_slow(sim, dist, pred, lk, s_len, s_run, s_ex, safe, gap)
    fin = np.isfinite(dist[:W["n"]])
    assert np.allclose(fast[fin], slow[fin], atol=1e-6), "tree_fast's excess differs from the reference"
    return int((slow[fin] > 0).sum())


def rank(sim, stt, C, T, mins, sch, blks, workers):
    """Greedy lazy ranking up to MAX_MI; returns the ranked list and the milestone scores."""
    import multiprocessing
    t0 = time.time()
    sim.network(blks, {})
    W = sim._W
    fast = tree_fast(sim)
    # check the vectorised tree on one school before trusting it
    door0 = [d for d in W["net"].ends(sch[0][2], sch[0][3]) if W["walkable"][d[3]]]
    dist, pred, lk = sim._dijkstra(W["Lw"].copy(), [d[0] for d in door0], [d[1] + d[2] for d in door0])
    sl = [d[1] + d[2] for d in door0]
    un = [bool(~W["safe"][d[3]]) for d in door0]
    a = getattr(sim, "_tree_slow", sim._tree)(dist, pred, lk, sl, [x if u else 0.0 for x, u in zip(sl, un)], [x if u else d[1] for x, u, d in zip(sl, un, door0)], W["safe"])
    b = fast(dist, pred, lk, sl, [x if u else 0.0 for x, u in zip(sl, un)], [x if u else d[1] for x, u, d in zip(sl, un, door0)], W["safe"])
    for x, y in zip(a, b):
        fin = np.isfinite(x)
        assert np.array_equal(fin, np.isfinite(y)) and np.allclose(x[fin], y[fin], atol=1e-6), "tree_fast differs from _tree"
    sim._tree = fast
    print("  segments: network and tree check (%.0fs)" % (time.time() - t0))
    ch, planned_edges = chunks(sim, stt)
    base = W["safe"].copy()
    if len(planned_edges):
        base[planned_edges] = True
    print("  segments: %d chunks, %.1f centerline miles; baseline adds %d planned edges" % (
        len(ch), sum(c["mi"] for c in ch), int(len(planned_edges))))
    ns, nb = len(sch), len(blks)
    dense_n = np.zeros((nb, ns))
    np.add.at(dense_n, (C["b"], C["school"]), C["n"])
    # The ranking's gain is students who drive today and newly have a safe trip: the City view moves
    # switch rate x those, so ranking on them ranks students out of cars per dollar.
    dense_w = np.zeros((nb, ns))
    np.add.at(dense_w, (C["b"], C["school"]), C["n"] * C["pr"][:, sim.CAR])
    sxy = np.array([W["walknet"].xy(s[2], s[3]) for s in sch])
    cxy = np.array([[c["x"], c["y"]] for c in ch])
    near_c = {j: [i for i in np.flatnonzero(np.hypot(*(cxy - sxy[j]).T) <= NEAR_MI * sim.MI)] for j in range(ns)}
    # the near-miss band on the baseline: passes the time test with slack, fails the gap
    car = mins["car"]
    walk = T["walk"]
    bm_b = mins["bike_today"]
    gap_b = T["gap_today"]
    near = (dense_n > 0) & (bm_b - car <= sim.CHANGES["bike_switch"]["within_min"] + (sim.DETOUR - 1) * (bm_b - sim.BIKE_FIXED_MIN)) \
        & (gap_b > sim.CHANGES["bike_switch"]["gap_total_ft"])
    doors = []
    for s in sch:
        d = W["net"].ends(s[2], s[3])
        doors.append([q for q in d if W["walkable"][q[3]]] or d)
    bike, bike_k0 = bike_fast(sim)
    cap_m = sim.bike_miles(SEARCH_MAX_MIN) * sim.MI
    all_cand = base.copy()
    all_cand[np.concatenate([c["edges"] for c in ch])] = True
    X, Y = np.asarray(W["x"], dtype=float), np.asarray(W["y"], dtype=float)
    cp, owner = [], []
    for i, c in enumerate(ch):
        for e in c["edges"]:
            a = np.array([X[W["eu"][e]], Y[W["eu"][e]]])
            b = np.array([X[W["ev"][e]], Y[W["ev"][e]]])
            for t in (0.0, 0.5, 1.0):
                cp.append(a + t * (b - a))
                owner.append(i)
    _S.update(sim=sim, doors=doors, base=base, near=[near[:, j] for j in range(ns)], walk=walk, car=car, n=dense_n, w=dense_w,
              chunk_edges=[c["edges"] for c in ch], bike=bike, bike_k0=bike_k0, cap_m=cap_m, all_cand=all_cand,
              chunk_pts=(np.array(cp), np.array(owner, dtype=np.int64)))
    full_k = sim.GAP_K
    _S["full_k"] = full_k
    nx = check_excess(sim, doors[0], base, sim.CHANGES["bike_switch"]["gap_total_ft"] * sim.FT)
    print("  segments: total-excess tree equals the node-by-node reference (%d nodes with excess)" % nx)
    for kk, label in ((full_k, "full"), (RANK_GAP_K, "ranking")):
        sim.GAP_K = kk
        t_old, t_new = check_fast(sim, sch, doors, walk, dense_n > 0, cap_m)
        print("  segments: fast _bike equals sim._bike on 3 schools, %s gap weights, for every student whose route is under "
              "%g min (%.1fs vs %.1fs)" % (label, SEARCH_MAX_MIN, t_old, t_new))
    sim.GAP_K = RANK_GAP_K
    by_school = {j: [i for i in near_c[j]] for j in range(ns) if near[:, j].any() and near_c[j]}
    print("  segments: %d schools with near-miss students, %d school-chunk pairs" % (len(by_school), sum(len(v) for v in by_school.values())))
    pool = multiprocessing.get_context("fork").Pool(workers) if workers > 1 else None
    imap = pool.imap_unordered if pool else map
    if OPT["corridor"]:
        tc = time.time()
        corr = dict(imap(_corridor_job, sorted(by_school)))
        by_school = {j: sorted(set(v) & set(corr[j])) for j, v in by_school.items()}
        by_school = {j: v for j, v in by_school.items() if v}
        print("  segments: corridor of %g ft keeps %d school-chunk pairs at %d schools (%.0fs)" % (
            SEGMENTS_CORRIDOR_FT, sum(len(v) for v in by_school.values()), len(by_school), time.time() - tc))

    def score(pairs, added):
        g = {}
        jobs = [(j, cs, added) for j, cs in pairs.items() if cs]
        for j, out, _ok0 in imap(_school_job, jobs):
            for c, v in out.items():
                o = g.get(c, (0.0, 0.0, 0.0))
                g[c] = tuple(a + b for a, b in zip(o, v))
        return g
    t1 = time.time()
    gain = score(by_school, np.zeros(0, dtype=np.int64))
    print("  segments: first pass %.0fs" % (time.time() - t1))
    ub = {c: gain.get(c, (0.0,))[0] for c in range(len(ch))}
    parts = {c: gain.get(c, (0.0, 0.0, 0.0)) for c in range(len(ch))}
    chosen, added, miles, evals = [], np.zeros(0, dtype=np.int64), 0.0, 0
    schools_of = {c: [j for j in by_school if c in by_school[j]] for c in range(len(ch))}
    fresh = set(ub)
    spent = 0.0
    while (miles < MAX_MI or spent < MAX_COST_M) and ub:
        c = max(ub, key=lambda k: (ub[k] / ch[k]["costM"], -k))
        if ub[c] <= 0:
            break
        if c not in fresh:
            g = score({j: [c] for j in schools_of[c]}, added)
            evals += 1
            parts[c] = g.get(c, (0.0, 0.0, 0.0))
            ub[c] = parts[c][0]
            fresh.add(c)
            continue
        chosen.append({"id": ch[c]["id"], "street": ch[c]["street"], "mi": ch[c]["mi"], "facilities": ch[c]["facilities"],
                       "drivers": round(parts[c][1], 1), "driverFeet": round(parts[c][2]), "costM": ch[c]["costM"],
                       "perMillion": round(ub[c] / ch[c]["costM"], 1), "cnns": ch[c]["cnns"]})
        added = np.r_[added, ch[c]["edges"]]
        miles += ch[c]["mi"]
        spent += ch[c]["costM"]
        del ub[c]
        fresh = set()
        print("    %2d. %-24s %.2f mi  +%.0f drivers  %.0f driver-ft  (%.1f mi, $%.1fM, %.0fs)" % (
            len(chosen), ch[c]["street"][:24], ch[c]["mi"], chosen[-1]["drivers"], chosen[-1]["driverFeet"], miles,
            spent, time.time() - t1), flush=True)
    sim.GAP_K = full_k
    # Each milestone network scored exactly, with the full gap test, at every school (not only the near-miss ones).
    nets, marks = [], []
    for m in MILESTONES:
        acc, es = 0.0, []
        for r in chosen:
            if acc >= m - 1e-9:
                break
            acc += r["mi"]
            es.append(ch[next(i for i, c in enumerate(ch) if c["id"] == r["id"])]["edges"])
        nets.append(np.unique(np.concatenate(es)) if es else np.zeros(0, dtype=np.int64))
        marks.append({"miles": m, "chunks": len(es), "centerlineMi": round(acc, 2), "costM": round(sum(r["costM"] for r in chosen[:len(es)]), 2)})
    for b in BUDGETS_M:
        acc, mi, n_in = 0.0, 0.0, 0
        for r in chosen:
            if acc + r["costM"] > b + 1e-9:
                break
            acc += r["costM"]
            mi += r["mi"]
            n_in += 1
        es = [ch[next(i for i, c in enumerate(ch) if c["id"] == r["id"])]["edges"] for r in chosen[:n_in]]
        nets.append(np.unique(np.concatenate(es)) if es else np.zeros(0, dtype=np.int64))
        marks.append({"budgetM": b, "chunks": n_in, "centerlineMi": round(mi, 2), "costM": round(acc, 2)})
    t2 = time.time()
    tot = [[0.0, 0.0] for _ in marks]
    for j, res in imap(_milestone_job, [(j, nets) for j in range(ns)]):
        for i, (a, b) in enumerate(res):
            tot[i][0] += a
            tot[i][1] += b
    for mk, (a, b) in zip(marks, tot):
        mk["students"], mk["drivers"] = round(a, 1), round(b, 1)
        print("  segments: %s milestone: %d chunks, %.1f mi, $%.1fM, %.0f students newly safe, %.0f of them drive today" % (
            "%d mi" % mk["miles"] if "miles" in mk else "$%dM" % mk["budgetM"], mk["chunks"], mk["centerlineMi"], mk["costM"], a, b))
    print("  segments: milestones %.0fs" % (time.time() - t2))
    if pool:
        pool.close()
    out = {"chunks": [{k: v for k, v in c.items() if k != "edges"} for c in ch], "ranked": chosen,
           "milestones": [m for m in marks if "miles" in m], "budgetMilestones": [m for m in marks if "budgetM" in m],
           "secondsRanking": round(time.time() - t1), "lazyEvals": evals,
           "speed": {"searchMaxMin": SEARCH_MAX_MIN, "corridorFt": SEGMENTS_CORRIDOR_FT if OPT["corridor"] else None}}
    if OFFPLAN:
        out["parallelRule"] = dict(getattr(chunks, "parallel", {}), oneBlockFt=ONE_BLOCK_FT, nextStreetX=NEXT_STREET_X,
                                   maxFt=NEXT_STREET_MAX_FT, degrees=PARALLEL_DEG,
                                   minFt=PARALLEL_MIN_FT, overlap=PARALLEL_OVERLAP)
    return out
