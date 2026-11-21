#!/usr/bin/env python3
"""Choose the street stretches, on or off the Biking and Rolling Plan, that remove the most family-car trips to school at year 10 (central case) at $5M, $10M, $20M, $40M, $80M and $100M, by integer program checked against the real route search.

School Trips' City view bike network buttons (design, Bryan 2026-10-14; objective and loop, Bryan 2026-10-18). Imports
tools/school-trips/school-segments.py for its network, candidate chunks and route search.

CANDIDATES (school-segments.py's chunks(), with OFFPLAN on). On the plan: every unbuilt all-ages plan block no upcoming
SFMTA project builds, priced per facility. Off the plan: every other street block, residential priced as calming,
collector or arterial as a separated lane, freeways and ramps out. The parallel rule drops an off-plan block when an
all-ages street (built, upcoming or on the plan) runs within PARALLEL_DEG of its bearing and within ONE_BLOCK_FT along
most of its length. Two exemptions (Bryan, 2026-10-14): a cross street that meets a plan street stays in (the angle test
keeps it, since a cross street is not parallel), and a block that continues an all-ages street past its end stays in
(same street name, an end within CONTINUE_M of the all-ages block's end). Touching blocks on one street are joined into
chunks of about a mile; chunk ids are their rank in a sorted construction, so they are stable across runs. Two
off-plan chunks one block apart and parallel can't both be built.

The baseline is today's all-ages network plus every upcoming SFMTA bikeway.

THE BENEFIT (school-sim.py's model). A cell (block, school, grade) whose route's on-network share rises by gain over
today has its bike logit moved by lambda[central] x caseD x gain, the other modes scaled in proportion, so it removes
n x car share x (P_bike after - P_bike today) / (1 - P_bike today) family-car trips at year 10, everything else at
baseline. A route's benefit is that summed over its pair's cells.

STEPS. (1) A route menu, cached in .cache/school-sim/segments-menu-<hash>.npz and rebuilt only when the network, the
candidates or the rules change: for every (block, school) pair with students, today's routes at every gap weight, the
same with every candidate safe, and the best route through each chunk within SEGMENTS_CORRIDOR_FT of the school's
routes, each stored as its metres, its feet off the network on the baseline and the feet each cover holds. A cover is
the chunk an edge lies in, or the set of chunks when two or more hold it, and a piece on it is safe once any of them is
built. A route through an unsignalled busy crossing stays in for a pair whose shortest route crosses one too (then
every candidate may cross, and the scorer takes one); for any other pair the scorer never picks it. (2) The route table:
the menu's routes within DETOUR x the pair's shortest, each pair keeping ROUTES_EFF by value per $ and ROUTES_VAL by
value (both with all the route's chunks built), plus every real route the check traced. A route's value under a build
set is its pair's benefit at the on-network share the whole build set gives it, counted once it rides on a built cover;
a pair's value is its best route's (evaluate, the promise). (3) The program, one per budget, OR-Tools CP-SAT: build
per chunk; per route one or two linear lower bounds on its value (build_program: exact with one cover built, and with
all or all but one), each a use that counts with one of its covers built; pairs with matching uses merge into groups
whose coefficients are the members' sums; a group takes at most one use; maximise under the budget, to MIP_REL_GAP or
TIME_LIMIT_S, on linearization level CPSAT_LIN, started from the greedy plan or the last round's, whichever is worth
more and feasible, and that start is kept when a solve stopped early ends below it (startKept). Each solve stops on
TIME_LIMIT_S or on its own footprint guard (stoppedOn); each plan is the best found, not proven best, and
greedyCarTrips is kept beside it. Budgets are nested, smallest first. (4) The check, one real route pass (the sim's
scorer) over every budget's network at once, counting the car trips removed, the students whose route's on-network
share rises and the drivers among them. (5) The loop: every pair whose real benefit and promise differ by more than
CHECK_TOL of the larger adds its real route to the table; a promised route the real search served under UNSERVED_FRAC
of its value (a shortfall over CHECK_TOL) is dropped (unserved_routes: by UNSERVED_RULE: on one such budget, or for a traced
route only when it falls short at every budget that promised it; tools/school-trips/school-segments-ip-test.py); and all budgets are
solved again, warm-started from the last round's plans (AddHint). It stops when each budget's promise and check agree
within CHECK_TOL, or after MAX_ROUNDS rounds. SEGMENTS_RESUME starts at a given round from a checked round's table.

A chosen chunk on no served pair's route (an early-stopped solve's pick) is dropped from the output (unusedDropped). A
chunk no served pair rides on alone is a bridge. Each budget reports its chosen pieces that touch no baseline network
(isolated), by cause: kept by nesting, on a chosen route (the gap rule lets a short calmed street serve a school on its
own), or neither.

Output out/school-sim/segments.json: chunks (id, street, cnns, mi, costM, facilities, pts) and budgets, each with its
chunk ids, cost, miles, carTripsRemoved (the checked year-10 car trips removed), students and drivers (checked: the
students whose route's on-network share rises on that network, and the expected drivers among them today), the
program's promise, the gap reached, rounds and isolated; loop holds each round's promise against check. Written with
scripts/lib/stable.py. Run by tools/school-trips/school-sim.py --segments; SEGMENTS_OFFPLAN=0 keeps the candidates to the plan,
SEGMENTS_OUT names another output path, SEGMENTS_CHECK=0 skips the check (one round), SEGMENTS_ROUNDS sets MAX_ROUNDS,
SEGMENTS_ONLY=menu stops once the menu is built, SEGMENTS_REPLAY values given build sets in place of the solves."""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import hashlib
import json
import math
import os
import sys
import time

import numpy as np

ALL_BUDGETS_M = (5, 10, 20, 40, 80, 100)   # the published segments.json carries every one of these
BUDGETS_M = ALL_BUDGETS_M
# SEGMENTS_BUDGETS=5 solves only those budgets (a memory trial, or one budget per process); each solve's result is
# cached under its own name, so a later full run reuses it. A narrowed run must write to SEGMENTS_OUT: run() refuses
# before any work otherwise, and check_output holds the published file to every budget in ALL_BUDGETS_M.
if os.environ.get("SEGMENTS_BUDGETS"):
    BUDGETS_M = tuple(int(x) for x in os.environ["SEGMENTS_BUDGETS"].split(","))
SOLVER = os.environ.get("SEGMENTS_SOLVER", "cpsat")   # cpsat (OR-Tools CP-SAT, all cores) or highs (scipy's MILP, one core each)
THREADS = int(os.environ.get("SEGMENTS_THREADS", "3"))   # one heavy job at a time on this machine: 3 workers at most, CP-SAT's included
MIP_REL_GAP = 0.05
# CP-SAT's limit a solve, seconds; a comma list gives one per round, the last repeating, and the output records the
# limit each round ran under (program.timeLimitsS). Each solve starts from the greedy plan or the last round's and keeps
# it unless CP-SAT finds better within the limit. None of the 40 solves of 2026-10-21 (300 s and 20 s; their result files,
# not segments.json, show it) ended more than 0.01 car trips above its start, so the default is short.
TIME_LIMITS = [float(x) for x in os.environ.get("SEGMENTS_TIME_LIMIT", "20").split(",")]
TIME_LIMIT_S = TIME_LIMITS[0]
RESUME = os.environ.get("SEGMENTS_RESUME")    # "<round>:<segments-round-*.npz>": start at that round from a checked round's table
CHECK_TOL = 0.02           # promise and check agree within this; a pair whose real benefit and promise differ by more
                           # has its real route traced. The solve's bound gap is not used: its relaxation is weak
CONTINUE_M = 30.0          # an end within this of an all-ages block's end continues its street: as chunks() joins blocks
MENU_K = (1.0, 4.0, 16.0)  # the safety-weighted searches on the everything-built network
THROUGH_K = 4.0            # the weight of the through-chunk searches
OFFPLAN = os.environ.get("SEGMENTS_OFFPLAN", "1") == "1"
OUT_PATH = os.environ.get("SEGMENTS_OUT")
DO_CHECK = os.environ.get("SEGMENTS_CHECK", "1") == "1"
# Each pair keeps, of its menu routes, the ROUTES_EFF most valuable per $ of their chunks and the ROUTES_VAL most
# valuable, both with all the route's chunks built; every route the real search was traced on stays besides.
ROUTES_EFF = int(os.environ.get("SEGMENTS_ROUTES_EFF", "3"))
ROUTES_VAL = int(os.environ.get("SEGMENTS_ROUTES_VAL", "3"))
PROG_MIN_SHARE = float(os.environ.get("SEGMENTS_PROG_MIN_SHARE", "0.01"))   # see build_program
# The objective (plan section 7, Fix 2): year-10 family-car trips removed in the central case. Pairs merge into groups
# when their uses match to BIN of the pair's best value; the group's coefficients are the members' exact sums.
CASE = "central"
BIN = 0.05
# The loop (Fix 1): at most MAX_ROUNDS solve-and-check rounds. A pair's promised route counts as unserved when the real
# search gives the pair less than its promise by more than CHECK_TOL: the check traced that pair's real route, so the
# pair keeps a route for this network. At 0.5 a $5M run held a 2.6% over-promise after three rounds, all of it pairs
# the real search served at 50-98% of the promised route (2026-10-21).
MAX_ROUNDS = int(os.environ.get("SEGMENTS_ROUNDS", "4"))
UNSERVED_FRAC = 1.0 - CHECK_TOL
# The menu's smallest today-route gap equals the scorer's gap for 86.3% of pairs (422,940 of 490,175, 2026-10-21). Of
# the rest, 36,800 (7.5%) are the scorer's routes over an unsignalled busy crossing, whose gap carried BREAK_FT; the
# check now takes that off. The other 30,435 (6.2%) have a menu best gap longer than the scorer's, median 7,545 ft:
# the menu lacks the scorer's own today route there, not yet explained. A share under this floor stops the step.
MENU_GAP_FLOOR = 0.80
# Which promised routes a round drops (unserved_routes). Live, 2026-10-21, six budgets: "budget" brought round 4 within
# 2% at five budgets (0.0-1.7%, $100M 2.2%); "every", resumed from that round, held the same build sets through rounds 5
# and 6 and left every budget over-promised by 3.2-5.1%, because a route real on one budget's network kept its value on
# networks where the real search takes another.
UNSERVED_RULE = os.environ.get("SEGMENTS_UNSERVED", "budget")
SOLVE_WORKERS = int(os.environ.get("SEGMENTS_SOLVE_WORKERS", "2"))   # a cloud VM may raise it; every full-run solve: the round 1 $5M child alone reached 9.3 GB in 600 s on 2 workers and 6.4 GB in 360 s (2026-10-19)
CPSAT_LIN = int(os.environ.get("SEGMENTS_CPSAT_LIN", "2"))   # CP-SAT's linearization_level
# A solve stops its own search once its process footprint (what the watchdog reads) passes this many MB and keeps the
# best plan found. CP-SAT's memory varies run to run (the round 1 $5M child on 2 workers peaked at 6.4 GB in one 360 s
# solve and passed 9.4 GB by 6 minutes in another, 2026-10-19), and its own max_memory_in_mb did not fire on this Mac.
CPSAT_MEM_MB = int(os.environ.get("SEGMENTS_CPSAT_MEM_MB", "7000"))
RUN_CAP_MB = int(os.environ.get("SEGMENTS_RUN_CAP_MB", "10300"))   # a cloud VM may raise it; parent plus solve, under the run's 11 GB watchdog with room for the guard's 5 s poll


def _footprint_mb():
    """This process's physical footprint in MB, from proc_pid_rusage (macOS); None where that is unavailable."""
    import ctypes
    try:
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
    except OSError:
        try:   # Linux (a cloud VM): resident set size
            for line in open("/proc/self/status"):
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
        except OSError:
            pass
        return None
    buf = (ctypes.c_uint64 * 40)()
    if lib.proc_pid_rusage(os.getpid(), 2, ctypes.byref(buf)) != 0:   # RUSAGE_INFO_V2
        return None
    return buf[9] / 2 ** 20   # after the 16-byte uuid: user, system, idle wakeups, interrupt wakeups, pageins, wired, resident, footprint
# Each budget must hold every chunk the next smaller one built, so the maps read as phases (Bryan, 2026-10-18, "Fix all
# three", on a review finding that $40M kept only 70 of $20M's 97 pieces). The budgets are solved smallest first, each
# forced to keep the chunks the one before shows (its chunks on a chosen route, and those it kept itself) and started
# from them.
NESTED = os.environ.get("SEGMENTS_NESTED", "1") == "1"
# The most miles of new calmed off-plan street any budget may buy; unset, no limit. Bryan, 2026-10-18, on counting calmed
# streets as all ages: "there's probably some limit to how many of these streets people accept."
CALM_CAP_MI = float(os.environ["SEGMENTS_CALM_CAP_MI"]) if os.environ.get("SEGMENTS_CALM_CAP_MI") else None
ONLY_B = os.environ.get("SEGMENTS_ONLY")          # "program": build and save the first round's program, then stop
# SEGMENTS_SEED=<an older segments.json>: each budget's round 1 hint is that file's plan at the same budget, mapped onto
# today's chunks (seed_map) and trimmed to the budget, the calming cap and the conflict pairs with the forced chunks
# (seed_trim). The solve starts from the better of that and the greedy plan and keeps it if it stops below it (startKept).
SEED_PATH = os.environ.get("SEGMENTS_SEED")
SEED_FRAC = 0.5   # a chunk of today's maps onto an old plan when more than half its CNNs are in that plan's CNNs
# SEGMENTS_REPLAY=<json {round: {budget: {"build": [...], "forced": [...]}}}>: each round values those build sets in place
# of solving, so an earlier run's plans can be checked against this code's promise.
REPLAY = os.environ.get("SEGMENTS_REPLAY")

_S = {}


def _seg():
    return sys.modules["school_segments"]


# -- candidates ---------------------------------------------------------------------------------------------------

def bike_fast(sim, seg):
    """school-segments.py's bike_fast (k0 reused, searches capped, trace) with the sim's busy-crossing rule: the weighted
    searches charge the approach edges, and a route through an unsignalled busy node carries BREAK_FT on its gap. The gap is the total off the network
    (sim._route_off)."""
    dij = seg.dijkstra_limited(sim)
    pick_fast = seg.block_pick_fast(sim)

    def door_of(door):
        steps = sim._W["steps"]
        return [d for d in door if not steps[d[3]]] or door

    def bike_k0(door):
        bd = door_of(door)
        return dij(np.where(sim._W["steps"], np.inf, sim._W["Lw"]), [d[0] for d in bd], [d[1] + d[2] for d in bd])

    def _bike(safe, door, walk, k0=None, cap_m=None, trace=False, gap=None):
        W = sim._W
        steps, F = W["steps"], W["flat"]
        bd = door_of(door)
        un_e = ~safe
        cand, trees = [], []
        assert sim.GAP_K[0] == 0.0 and gap is None
        for k in sim.GAP_K:
            s_len = [d[1] + d[2] for d in bd]
            s_un = [bool(un_e[d[3]]) for d in bd]
            if k == 0 and k0 is not None:
                dist, pred, lk = k0
            else:
                w = np.where(steps, np.inf, W["Lw"] * (1 + k * un_e) + k * W["xpen"])
                s_cost = [d[1] * (1 + k) + d[2] * (1 + k * u) for d, u in zip(bd, s_un)]
                lim = np.inf if cap_m is None or k == 0 else (1 + k) * sim.DETOUR * cap_m * (1 + 1e-6) + 1.0
                dist, pred, lk = dij(w, [d[0] for d in bd], s_cost, lim)
            s_run = [sl if u else 0.0 for sl, u in zip(s_len, s_un)]
            s_max = [sl if u else d[1] for sl, u, d in zip(s_len, s_un, bd)]
            ln, run, mx = sim._tree(dist, pred, lk, s_len, s_run, s_max, safe)
            ue = un_e[F["e"]] | steps[F["e"]]
            w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
            pick = pick_fast(F, dist[:-1], w_end)
            pi = np.maximum(pick, 0)
            nd = F["node"][pi]
            m = np.where(pick >= 0, ln[nd] + F["c"][pi] + F["al"][pi], np.inf)
            g = np.where(pick >= 0, sim._route_off(dist, pred, lk, bd, un_e, F, pi, nd, ue), np.inf)
            g = np.where(sim._broken(pred, lk, nd, F["e"][pi]), g + sim.BREAK_FT * sim.FT, g)
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
        if trace:
            return out + ({"which": which, "trees": trees, "m0": m0},)
        return out
    return _bike, bike_k0


def continuation_exemption(sim, stt, seg, meta, dropped, cand_all, plan, pl_lines):
    """The dropped off-plan keys that continue an all-ages street past its end: the same street name as a built, upcoming
    or plan block, and an end within CONTINUE_M of that block's end."""
    import sfdata
    W = sim._W
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type", where="active='true'", floor=15000)
    name_of = {}
    for row in r.rows:
        c = str(row.get("cnn") or "").split(".")[0].lstrip("0")
        name_of[c] = (row.get("streetname") or "%s %s" % (row.get("street") or "", row.get("st_type") or "")).strip().upper()
    today, _plan, _meta = stt.all_ages_lines()
    aa = []   # (name, pts) of every all-ages block with a name
    for k, pts in today:
        nm = name_of.get(str(k).lstrip("0"))
        if nm and len(pts) >= 2:
            aa.append((nm, pts))
    for k, pts in plan:
        nm = (meta[k]["street"] or "").upper() or name_of.get(meta[k]["cnn"])
        if nm and len(pts) >= 2:
            aa.append((nm, pts))
    for k, pts in pl_lines:
        nm = name_of.get(k.split(":")[1].lstrip("0"))
        if nm and len(pts) >= 2:
            aa.append((nm, pts))
    ends = {}
    for nm, pts in aa:
        for q in (pts[0], pts[-1]):
            ends.setdefault(nm, []).append(W["walknet"].xy(*q[:2]))
    ends = {nm: np.array(v) for nm, v in ends.items()}
    cpts = dict(cand_all)
    back = []
    for k in sorted(dropped):
        nm = (meta[k]["street"] or "").upper()
        if nm not in ends:
            continue
        pts = cpts[k]
        for q in (pts[0], pts[-1]):
            p = np.array(W["walknet"].xy(*q[:2]))
            if np.hypot(*(ends[nm] - p).T).min() <= CONTINUE_M:
                back.append(k)
                break
    return back


def candidates(sim, stt, seg):
    """school-segments.py's chunks(), with the continuation exemption folded into its parallel rule. Returns the chunks,
    the planned edges and the candidate counts."""
    seg.OFFPLAN = OFFPLAN
    counts = {"offplan": OFFPLAN}
    if not OFFPLAN:
        ch, planned_edges = seg.chunks(sim, stt)
        counts["planBlocks"] = sum(len(c["cnns"]) for c in ch)
        counts["steep"], counts["muniSeparated"] = seg.chunks.steep, seg.chunks.muni
        return ch, planned_edges, counts
    # Re-run chunks()'s candidate selection with the exemption: wrap parallel_drop so the keys it drops lose the
    # continuations before chunks() filters on them.
    orig = seg.parallel_drop
    rec = {}

    def wrapped(sim_, stt_, cand, e_c, plan):
        drop = orig(sim_, stt_, cand, e_c, plan)
        planned = json.load(open(os.path.join(sim.ROOT, "site", "data", "bike-history", "planned.json")))
        pl_lines = [("pl:%s" % b["cnn"], b["pts"]) for pr in planned["projects"] for b in pr["blocks"] if len(b.get("pts") or []) >= 2]
        meta = wrapped.meta
        back = continuation_exemption(sim_, stt_, seg, meta, drop, cand, plan, pl_lines)
        rec["dropped"] = len(drop)
        rec["continued"] = len(back)
        rec["offplanBlocks"] = sum(k.startswith("op:") for k, _p in cand)
        rec["planBlocks"] = sum(not k.startswith("op:") for k, _p in cand)
        rec["continuedBlocks"] = sorted([meta[k]["street"], meta[k]["cnn"]] for k in back)
        for k in back:
            del drop[k]
        print("  segments: parallel rule drops %d of %d off-plan blocks; the continuation exemption keeps %d of them" % (
            rec["dropped"], rec["offplanBlocks"], rec["continued"]))
        return drop
    # offplan_lines() adds each off-plan key's meta to the dict all_ages_lines() returned; capture that dict.
    orig_lines = seg.offplan_lines

    def lines_wrapped(sim_, stt_, meta, pl_cnn, muni=()):
        wrapped.meta = meta
        return orig_lines(sim_, stt_, meta, pl_cnn, muni)
    seg.parallel_drop, seg.offplan_lines = wrapped, lines_wrapped
    try:
        ch, planned_edges = seg.chunks(sim, stt)
    finally:
        seg.parallel_drop, seg.offplan_lines = orig, orig_lines
    counts.update(rec)
    counts["steep"], counts["muniSeparated"] = getattr(seg.chunks, "steep", None), getattr(seg.chunks, "muni", None)
    return ch, planned_edges, counts


# -- route menu ---------------------------------------------------------------------------------------------------

def _parent_edges(sim, pred, lookup):
    """Per node: the tree edge to its parent (>= 0), -1 - seed index at a seed, -2 unreached."""
    n = sim._W["n"]
    key, ref = lookup
    reach = np.flatnonzero((pred[:n] >= 0))
    p = pred[reach].astype(np.int64)
    r = ref[np.searchsorted(key, p * (n + 1) + reach)]
    pe = np.full(n, -2, dtype=np.int64)
    pe[reach] = r
    return pe


def _chase(pred, pe, targets):
    """The tree edges from each target up to its seed: (route index, step from the target, edge), and each route's seed."""
    cur = targets.astype(np.int64).copy()
    rid = np.arange(len(targets))
    out_r, out_s, out_e = [], [], []
    step = 0
    seed = np.full(len(targets), -1, dtype=np.int64)
    while len(cur):
        e = pe[cur]
        at_seed = e < 0
        seed[rid[at_seed]] = -1 - e[at_seed]
        keep = ~at_seed
        if not keep.any():
            break
        out_r.append(rid[keep])
        out_s.append(np.full(int(keep.sum()), step))
        out_e.append(e[keep])
        cur = pred[cur[keep]].astype(np.int64)
        rid = rid[keep]
        step += 1
    if out_r:
        return np.concatenate(out_r), np.concatenate(out_s), np.concatenate(out_e), seed
    z = np.zeros(0, dtype=np.int64)
    return z, z, z, seed


def _assemble(sim, S, n_routes, parts):
    """parts: list of (route ids, order, lengths m, unsafe, owner) arrays. Returns per route total metres and the flat
    run table (route, run, feet, owner) over unsafe pieces, consecutive same-owner pieces merged, runs split by a
    safe piece."""
    r = np.concatenate([p[0] for p in parts])
    o = np.concatenate([p[1] for p in parts]).astype(float)
    ln = np.concatenate([p[2] for p in parts]).astype(float)
    un = np.concatenate([p[3] for p in parts]).astype(bool)
    ow = np.concatenate([p[4] for p in parts]).astype(np.int64)
    idx = np.lexsort((o, r))
    r, ln, un, ow = r[idx], ln[idx], un[idx], ow[idx]
    total = np.bincount(r, weights=ln, minlength=n_routes)
    # run ids: a new run starts at an unsafe piece whose previous piece (same route) is safe or missing
    new_route = np.r_[True, r[1:] != r[:-1]]
    prev_un = np.r_[False, un[:-1]] & ~new_route
    start = un & ~prev_un
    run = np.cumsum(start) - 1
    keep = un
    r, ln, ow, run = r[keep], ln[keep], ow[keep], run[keep]
    # merge consecutive pieces of one run with the same owner
    same = np.r_[False, (run[1:] == run[:-1]) & (ow[1:] == ow[:-1])]
    grp = np.cumsum(~same) - 1
    ln = np.bincount(grp, weights=ln)
    first = np.flatnonzero(~same)
    return total, (r[first], run[first], ln / sim.FT, ow[first])


def _aggregate(n_routes, runs):
    """A run table (route, run, feet, cover) as what the program reads: per route its feet off the network on the
    baseline (every unsafe piece) and its gap, which under the total-gap rule (sim.GAP_RULE) is those same feet, and
    per (route, cover) the feet that cover holds."""
    r, run, ft, own = (np.asarray(x) for x in runs)
    r = r.astype(np.int64)
    ft = ft.astype(np.float64)
    off = np.bincount(r, weights=ft, minlength=n_routes)
    gap = off.copy()
    has = own >= 0
    M = int(own.max()) + 1 if has.any() else 1
    key, inv = np.unique(r[has] * M + own[has].astype(np.int64), return_inverse=True)
    eft = np.bincount(inv, weights=ft[has]) if len(key) else np.zeros(0)
    return off, gap, ((key // M).astype(np.int32), (key % M).astype(np.int32), eft.astype(np.float32))


def _edge_parts(sim, S, rr, ss, ee, order_base):
    """Tree edges as route pieces, ordered door to block: the chase runs from the block (or the chunk node) towards the
    seed, so the largest step comes first."""
    W = sim._W
    if not len(rr):
        z = np.zeros(0, dtype=np.int64)
        return (z, z, z.astype(float), z.astype(bool), z)
    smax = np.zeros(rr.max() + 1, dtype=np.int64)
    np.maximum.at(smax, rr, ss)
    order = order_base + (smax[rr] - ss)
    return (rr, order, W["L"][ee], ~S["base"][ee], np.where(S["base"][ee], -1, S["owner"][ee]))


def _door_seed_parts(S, j, seed, rids):
    """The door's two pieces: the connector (off any street) and the along-edge part, per route (seed index per route)."""
    bd = S["bdoor"][j]
    c = np.array([bd[s][1] for s in seed])
    al = np.array([bd[s][2] for s in seed])
    e = np.array([bd[s][3] for s in seed], dtype=np.int64)
    un_al = ~S["base"][e]
    own_al = np.where(un_al, S["owner"][e], -1)
    r2 = np.r_[rids, rids]
    return (r2, np.r_[np.full(len(rids), -2), np.full(len(rids), -1)], np.r_[c, al], np.r_[np.ones(len(rids), bool), un_al],
            np.r_[np.full(len(rids), -1), own_al])


def _join_parts(sim, S, pi, rids, order_hi):
    """The block's two pieces: the along-edge part of its join and the connector."""
    W = sim._W
    F = W["flat"]
    e = F["e"][pi]
    ue = ~S["base"][e] | W["steps"][e]
    own = np.where(ue & ~W["steps"][e], S["owner"][e], -1)
    r2 = np.r_[rids, rids]
    return (r2, np.r_[np.full(len(rids), order_hi), np.full(len(rids), order_hi + 1)], np.r_[F["al"][pi], F["c"][pi]], np.r_[ue, np.ones(len(rids), bool)],
            np.r_[own, np.full(len(rids), -1)])


def _search(sim, S, safe, bd, k, cap=True):
    """One capped safety-weighted search from a door on `safe`: (dist, pred, lookup, w_end for the joins)."""
    W = sim._W
    steps, F = W["steps"], W["flat"]
    un_e = ~safe
    w = np.where(steps, np.inf, W["Lw"] * (1 + k * un_e) + k * W["xpen"])
    s_un = [bool(un_e[d[3]]) for d in bd]
    s_cost = [d[1] * (1 + k) + d[2] * (1 + k * u) for d, u in zip(bd, s_un)]
    lim = np.inf if (not cap or k == 0) else (1 + k) * sim.DETOUR * S["cap_m"] * (1 + 1e-6) + 1.0
    dist, pred, lk = S["dij"](w, [d[0] for d in bd], s_cost, lim)
    ue = un_e[F["e"]] | steps[F["e"]]
    w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
    return dist, pred, lk, w_end


def _menu_school_job(j):
    """One school: its pairs, their shortest-route metres, whether that shortest route crosses a busy street unsignalled
    (brk0), and every door-rooted menu route (today's at each gap weight, everything-built at MENU_K), aggregated per
    cover. Also the school's THROUGH_K baseline tree. A route through an unsignalled busy crossing is kept only for a
    pair whose shortest route crosses one too: the shortest route is the scorer's k = 0 candidate on every network, so
    for any other pair a crossing route is never the one it picks."""
    sim, S = _S["sim"], _S
    W = sim._W
    F = W["flat"]
    bd = S["bdoor"][j]
    pick = S["pick"]
    cand_b = np.flatnonzero(S["near"][:, j])
    if not len(cand_b):
        return j, None
    # the shortest route: fixes m0 and the exact pair set
    dist0, pred0, lk0, w_end0 = _search(sim, S, S["base"], bd, 0.0)
    p0 = pick(F, dist0[:-1], w_end0)
    ln0 = sim._tree(dist0, pred0, lk0, [d[1] + d[2] for d in bd], [0.0] * len(bd), [0.0] * len(bd), S["base"])[0]
    pi0 = np.maximum(p0, 0)
    m0 = np.where(p0 >= 0, ln0[F["node"][pi0]] + F["c"][pi0] + F["al"][pi0], np.inf)
    blocks = cand_b[np.isfinite(m0)[cand_b]]
    if not len(blocks):
        return j, None
    brk0 = np.zeros(len(blocks), dtype=bool)
    pb0 = p0[blocks]
    brk0[pb0 >= 0] = sim._broken(pred0, lk0, F["node"][pb0[pb0 >= 0]], F["e"][pb0[pb0 >= 0]])
    routes = []   # (blocks, kind, metres, aggregate)
    through_tree = None
    nets = [("today", S["base"], k) for k in S["full_k"]] + [("all", S["all_cand"], k) for k in MENU_K]
    for kind, net, k in nets:
        if k == 0:
            dist, pred, lk, w_end = dist0, pred0, lk0, w_end0
        else:
            dist, pred, lk, w_end = _search(sim, S, net, bd, k)
        p = pick(F, dist[:-1], w_end)
        pb = p[blocks]
        got = pb >= 0
        if got.any():
            got[got] &= brk0[got] | ~sim._broken(pred, lk, F["node"][pb[got]], F["e"][pb[got]])
        pe = _parent_edges(sim, pred, lk)
        if kind == "today" and k == THROUGH_K:
            through_tree = (pred.astype(np.int32), pe.astype(np.int32), sim._broken(pred, lk))
        if not got.any():
            continue
        b, pi = blocks[got], pb[got]
        rr, ss, ee, seed = _chase(pred, pe, F["node"][pi])
        rids = np.arange(len(b))
        parts = [_door_seed_parts(S, j, seed, rids), _edge_parts(sim, S, rr, ss, ee, 0), _join_parts(sim, S, pi, rids, 10 ** 7)]
        total, runs = _assemble(sim, S, len(b), parts)
        routes.append((b, "%s%g" % (kind, k), total, _aggregate(len(b), runs)))
    return j, {"blocks": blocks, "m0": m0[blocks].astype(np.float32), "brk0": brk0, "routes": routes, "tree": through_tree}


def _menu_chunk_job(ci):
    """One chunk: for every school within whose (doubled) corridor it lies, the route through it for each of that school's
    candidate blocks: the school's THROUGH_K tree to the chunk's nearest node, then the chunk-seeded search to the block."""
    sim, S = _S["sim"], _S
    W = sim._W
    F = W["flat"]
    schools = S["corr_of"].get(ci, [])
    if not schools:
        return ci, []
    es = S["chunk_edges"][ci]
    safe = S["base"].copy()
    safe[es] = True
    nodes = np.unique(np.r_[W["eu"][es], W["ev"][es]])
    un_e = ~safe
    k = THROUGH_K
    w = np.where(W["steps"], np.inf, W["Lw"] * (1 + k * un_e) + k * W["xpen"])
    lim = (1 + k) * sim.DETOUR * S["cap_m"] * (1 + 1e-6) + 1.0
    dist, pred, lk = S["dij"](w, nodes, np.zeros(len(nodes)), lim)
    ue = un_e[F["e"]] | W["steps"][F["e"]]
    w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
    p = S["pick"](F, dist[:-1], w_end)
    pe = _parent_edges(sim, pred, lk)
    # the tree's crossings once, each school's block joins below (sim._broken with join nodes, without redoing the tree)
    brk_t = sim._broken(pred, lk)
    xnode, xedge = W["xnode"], W["xedge"]
    out = []
    for j in schools:
        m = S["menu"][j]
        if m is None or m["tree"] is None:
            continue
        blocks = m["blocks"]
        pb = p[blocks]
        got = pb >= 0
        if got.any():
            jn, je = F["node"][pb[got]], F["e"][pb[got]]
            jp = pe[jn]
            brk_j = brk_t[jn] | (xnode[jn] & ~xedge[je] & (jp >= 0) & ~xedge[np.maximum(jp, 0)])
            got[got] &= m["brk0"][got] | ~brk_j
        if not got.any():
            continue
        b, pi, m0, bk0 = blocks[got], pb[got], m["m0"][got], m["brk0"][got]
        tpred, tpe, brk_d = m["tree"]
        tpred = tpred.astype(np.int64)
        tpe = tpe.astype(np.int64)
        # block to chunk node on the chunk tree
        rr1, ss1, ee1, seed1 = _chase(pred, pe, F["node"][pi])
        u = nodes[seed1]
        # chunk node to the door on the school's tree; drop routes whose chunk node the door tree never reached, or
        # whose door side crosses a busy street unsignalled (unless the pair's shortest route does too)
        reach = (tpe[u] != -2) & (bk0 | ~brk_d[u])
        if not reach.any():
            continue
        b, pi, m0, u = b[reach], pi[reach], m0[reach], u[reach]
        keep1 = reach[rr1]
        rr1 = np.cumsum(reach)[rr1[keep1]] - 1
        ss1, ee1 = ss1[keep1], ee1[keep1]
        rr2, ss2, ee2, seed2 = _chase(tpred, tpe, u)
        rids = np.arange(len(b))
        parts = [_door_seed_parts(S, j, seed2, rids), _edge_parts(sim, S, rr2, ss2, ee2, 0),
                 _edge_parts(sim, S, rr1, ss1, ee1, 10 ** 6), _join_parts(sim, S, pi, rids, 10 ** 7)]
        total, runs = _assemble(sim, S, len(b), parts)
        ok = total <= sim.DETOUR * m0 + 1e-6
        off, gap, (er, ek, eft) = _aggregate(len(b), runs)
        # a route "through" the chunk must ride on it (a cover holding it); one that only touches its end is some other
        # route
        uses = np.zeros(len(b), dtype=bool)
        uses[er[np.isin(ek, S["cov_of"][ci])]] = True
        ok &= uses
        if not ok.any():
            continue
        rmap = np.full(len(b), -1, dtype=np.int64)
        rmap[ok] = np.arange(int(ok.sum()))
        sel = rmap[er] >= 0
        out.append((j, b[ok], total[ok].astype(np.float32), (off[ok], gap[ok], (rmap[er[sel]].astype(np.int32), ek[sel], eft[sel]))))
    return ci, out


def _corridor_job(j):
    """One school: each chunk's nearest distance (ft) to a candidate block's best route on the baseline, within twice
    the corridor."""
    from scipy.spatial import cKDTree
    sim, S = _S["sim"], _S
    seg = _seg()
    W = sim._W
    m = S["menu"][j]
    if m is None:
        return j, {}
    bm, _bg, _nb, tr = S["bike"](S["base"], S["doors"][j], S["walk"][:, j], None, S["cap_m"], trace=True)
    blocks = m["blocks"][np.isfinite(tr["m0"][m["blocks"]])]
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
        return j, {}
    cp, owner = S["chunk_pts"]
    d, _i = cKDTree(xy).query(cp, distance_upper_bound=2 * seg.SEGMENTS_CORRIDOR_FT * sim.FT)
    out = {}
    for ci, ft in zip(owner[np.isfinite(d)].tolist(), (d[np.isfinite(d)] / sim.FT).tolist()):
        out[ci] = min(out.get(ci, np.inf), ft)
    return j, out


def menu_hash(sim, seg, ch, S):
    h = hashlib.sha256()
    src = open(os.path.abspath(__file__)).read()
    h.update(src[src.index("# -- route menu"):src.index("# -- the benefit")].encode())
    h.update(json.dumps([sim.GAP_RULE, list(sim.GAP_K), sim.DETOUR, seg.SEARCH_MAX_MIN, seg.SEGMENTS_CORRIDOR_FT, list(MENU_K), THROUGH_K,
                         sim.CHANGES["bike_switch"]["within_min"], sim.BIKE_MPH, sim.BIKE_GOOGLE_MIN, sim.BIKE_FIXED_MIN,
                         OFFPLAN]).encode())
    h.update(np.packbits(S["base"]).tobytes())
    # the busy-crossing rule shapes every route
    h.update(json.dumps([sim.XING_LANES, sim.XING_MPH, sim.XING_SIGNAL_M, sim.XING_PEN_M, sim.BREAK_FT]).encode())
    h.update(np.packbits(sim._W["xnode"]).tobytes())
    h.update(np.packbits(sim._W["xapp"]).tobytes())
    for c in ch:
        h.update(("%s|%s|%s" % (c["id"], c["street"], ",".join(c["cnns"]))).encode())
        h.update(np.asarray(c["edges"], dtype=np.int64).tobytes())
    h.update(b"covers-1")
    h.update(np.asarray(S["cov_c"], dtype=np.int64).tobytes())
    h.update(np.packbits(S["near"]).tobytes())
    h.update(S["car"].astype(np.float32).tobytes())
    h.update(np.asarray(S["school_ids"]).astype(str).tobytes() if len(S["school_ids"]) else b"")
    return h.hexdigest()[:16]


def pmap(workers, fn, jobs):
    """Map over a fresh fork pool (its workers see everything _S holds now), or in-process with one worker."""
    import multiprocessing
    jobs = list(jobs)
    if workers <= 1 or len(jobs) <= 1:
        return list(map(fn, jobs))
    pool = multiprocessing.get_context("fork").Pool(min(workers, len(jobs)))
    try:
        return list(pool.imap_unordered(fn, jobs))
    finally:
        pool.close()
        pool.join()


def pmap_iter(workers, fn, jobs):
    """pmap, yielding each result as it arrives, so the caller can write it out before the next."""
    import multiprocessing
    jobs = list(jobs)
    if workers <= 1 or len(jobs) <= 1:
        yield from map(fn, jobs)
        return
    pool = multiprocessing.get_context("fork").Pool(min(workers, len(jobs)))
    try:
        yield from pool.imap_unordered(fn, jobs)
    finally:
        pool.close()
        pool.join()


def ROOT_OF(sim):
    return paths.ROOT


def build_menu(sim, seg, ch, workers, S, path):
    """Step 1. Returns the flat menu: pairs, routes (pair index, metres, kind, chunk, corridor ft) and run pieces."""
    t0 = time.time()
    ns = len(S["doors"])
    S["menu"] = [None] * ns
    for j, m in pmap(workers, _menu_school_job, range(ns)):
        S["menu"][j] = m
    n_pairs = sum(len(m["blocks"]) for m in S["menu"] if m)
    print("  menu: %d schools, %d (block, school) pairs that could newly pass (%.0fs)" % (
        sum(m is not None for m in S["menu"]), n_pairs, time.time() - t0), flush=True)
    t1 = time.time()
    corr = dict(pmap(workers, _corridor_job, [j for j in range(ns) if S["menu"][j]]))
    corr_of = {}
    for j, d in corr.items():
        for ci, ft in d.items():
            corr_of.setdefault(ci, []).append(j)
    S["corr_of"] = corr_of
    ft_of = {(j, ci): ft for j, d in corr.items() for ci, ft in d.items()}
    n1 = sum(ft <= seg.SEGMENTS_CORRIDOR_FT for ft in ft_of.values())
    print("  menu: corridor of %g ft keeps %d (school, chunk) pairs, twice it %d (%.0fs)" % (
        seg.SEGMENTS_CORRIDOR_FT, n1, len(ft_of), time.time() - t1), flush=True)
    # the flat tables: per route its pair, metres, kind, chunk (through routes), corridor feet, feet off the network on
    # the baseline and its gap (the same feet, the total-gap rule); per (route, cover) entry the feet that cover holds. The pieces themselves are
    # not kept: on the full off-plan menu they were 2.1 billion (2026-10-20).
    pair_b, pair_j, pair_m0, pair_brk0 = [], [], [], []
    pair_ix = {}
    r_pair, r_m, r_kind, r_chunk, r_ft, r_off, r_gap = [], [], [], [], [], [], []
    e_route, e_cov, e_ft = [], [], []
    n_routes = 0
    for j, m in enumerate(S["menu"]):
        if m:
            for bb, m0, k0 in zip(m["blocks"].tolist(), m["m0"].tolist(), m["brk0"].tolist()):
                pair_ix[(bb, j)] = len(pair_b)
                pair_b.append(bb)
                pair_j.append(j)
                pair_m0.append(m0)
                pair_brk0.append(k0)

    def add_routes(j, b, total, kind, ci, ft, agg):
        nonlocal n_routes
        off, gap, (er, ek, eft) = agg
        r_pair.append(np.array([pair_ix[(bb, j)] for bb in b.tolist()], dtype=np.int64))
        r_m.append(np.asarray(total, dtype=np.float32))
        r_kind.append(np.full(len(b), kind))
        r_chunk.append(np.full(len(b), ci, dtype=np.int32))
        r_ft.append(np.full(len(b), ft, dtype=np.float32))
        r_off.append(np.asarray(off, dtype=np.float32))
        r_gap.append(np.asarray(gap, dtype=np.float32))
        e_route.append((np.asarray(er, dtype=np.int64) + n_routes).astype(np.int32))
        e_cov.append(np.asarray(ek, dtype=np.int32))
        e_ft.append(np.asarray(eft, dtype=np.float32))
        n_routes += len(b)
    for j, m in enumerate(S["menu"]):
        if not m:
            continue
        for b, kind, total, agg in m["routes"]:
            add_routes(j, b, total, kind, -1, 0.0, agg)
    t2 = time.time()
    n_through = 0
    # Each chunk search is written to <menu path>.parts/ as it finishes, so a run stopped mid-menu (a preemption, a move
    # to another machine) resumes from the searches already done. The parts sit under the menu's own hash, so a change
    # to the network, the candidates or the rules never reads them; they are removed once the menu is written.
    import pickle
    parts = path + ".parts"
    os.makedirs(parts, exist_ok=True)
    part = lambda ci: os.path.join(parts, "chunk-%d.pkl" % ci)
    done = {ci: pickle.load(open(part(ci), "rb")) for ci in sorted(corr_of) if os.path.exists(part(ci))}
    if done:
        print("  menu: %d of %d chunk searches read from %s" % (len(done), len(corr_of), os.path.relpath(parts, ROOT_OF(sim))), flush=True)

    def save(ci, out):
        tmp = part(ci) + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(out, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, part(ci))
    results = dict(done)
    for ci, out in pmap_iter(workers, _menu_chunk_job, [ci for ci in sorted(corr_of) if ci not in done]):
        save(ci, out)
        results[ci] = out
    for ci in sorted(results):
        for j, b, total, agg in results[ci]:
            add_routes(j, b, total, "through", ci, ft_of[(j, ci)], agg)
            n_through += len(b)
    del results
    print("  menu: %d through-chunk routes from %d chunk searches (%.0fs)" % (n_through, len(corr_of), time.time() - t2), flush=True)
    cat = lambda xs, dt: np.concatenate(xs).astype(dt, copy=False) if xs else np.zeros(0, dtype=dt)
    menu = {"pair_b": np.array(pair_b, dtype=np.int64), "pair_j": np.array(pair_j, dtype=np.int64), "pair_m0": np.array(pair_m0, dtype=np.float32),
            "pair_brk0": np.array(pair_brk0, dtype=bool),
            "r_pair": cat(r_pair, np.int32), "r_m": cat(r_m, np.float32), "r_kind": cat(r_kind, "U8"),
            "r_chunk": cat(r_chunk, np.int32), "r_ft": cat(r_ft, np.float32), "r_off": cat(r_off, np.float32), "r_gap": cat(r_gap, np.float32),
            "e_route": cat(e_route, np.int32), "e_cov": cat(e_cov, np.int32), "e_ft": cat(e_ft, np.float32),
            "seconds": np.array([time.time() - t0])}
    for m in S["menu"]:
        if m:
            m["tree"] = None
            m["routes"] = None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, **menu)
    import shutil
    shutil.rmtree(parts, ignore_errors=True)
    return menu


def check_menu_gaps(sim, S, menu, T):
    """The menu's today-route gaps against the scorer's: for every pair, the smallest gap over the menu's today routes
    within the detour equals T['gap_today'] where the scorer's chosen route is one of them. Reports the share equal."""
    tg = T["gap_today"]
    r_pair, r_m, r_kind = menu["r_pair"], menu["r_m"], menu["r_kind"]
    today = np.flatnonzero(np.char.startswith(r_kind, "today") & (r_m <= menu["pair_m0"][r_pair] * sim.DETOUR + 1e-3))
    best = np.full(len(menu["pair_b"]), np.inf)
    np.minimum.at(best, r_pair[today], menu["r_gap"][today].astype(np.float64))
    has = np.isfinite(best)
    tgp = tg[menu["pair_b"][has], menu["pair_j"][has]]
    return int((np.abs(best[has] - tgp) <= 1.0).sum()), int(has.sum())


# -- the benefit --------------------------------------------------------------------------------------------------

def cell_table(sim, C, lam, ns):
    """The sim's cells (block, school, grade), sorted by pair key b x ns + school, with what a route's benefit reads:
    students n, today's bike and family-car shares, lambda x caseD (the case's full logit shift per unit of on-network
    gain) and today's on-network share."""
    key = C["b"].astype(np.int64) * ns + C["school"].astype(np.int64)
    o = np.argsort(key, kind="stable")
    return {"key": key[o], "b": C["b"][o].astype(np.int64), "j": C["school"][o].astype(np.int64), "n": C["n"][o].astype(float),
            "p": C["pr"][o, sim.BIKE].astype(float), "car": C["pr"][o, sim.CAR].astype(float),
            "D": lam * C["caseD"][o].astype(float), "on0": C["on_today"][o].astype(float), "ns": ns}


def cell_benefit(ct, idx, gain):
    """Family-car trips removed at year 10 on each listed cell when its route's on-network share rises by gain, with
    everything else at baseline: n x car x (P_bike after - P_bike today) / (1 - P_bike today). This is school-sim.py's
    shift_bike (the bike logit moves by lambda x caseD x gain, the other modes scale in proportion), so the car falls by
    the same fraction as every other non-bike mode."""
    p = ct["p"][idx]
    ok = (gain > 0) & (p > 0) & (p < 1)
    pc = np.where(ok, p, 0.5)
    p2 = 1.0 / (1.0 + np.exp(-np.clip(np.log(pc) - np.log1p(-pc) + ct["D"][idx] * np.where(ok, gain, 0.0), -700, 700)))
    return np.where(ok, ct["n"][idx] * ct["car"][idx] * (p2 - pc) / (1.0 - pc), 0.0)


def pair_benefit(ct, pkey, on):
    """Per item (a pair key and the on-network share its route reaches), the pair's benefit summed over its cells."""
    lo = np.searchsorted(ct["key"], pkey, "left")
    hi = np.searchsorted(ct["key"], pkey, "right")
    cnt = hi - lo
    if not cnt.sum():
        return np.zeros(len(pkey))
    item = np.repeat(np.arange(len(pkey)), cnt)
    idx = np.repeat(lo, cnt) + (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt))
    gain = np.maximum(on[item] - ct["on0"][idx], 0.0)
    return np.bincount(item, weights=cell_benefit(ct, idx, gain), minlength=len(pkey))


# -- the route table ----------------------------------------------------------------------------------------------

def _hash_keys(n):
    """Two fixed random 64-bit keys per cover; a route's signature is a wrapping sum over its entries."""
    rng = np.random.default_rng(20261018)
    return (rng.integers(1, 2 ** 63, size=n, dtype=np.int64).astype(np.uint64),
            rng.integers(1, 2 ** 63, size=n, dtype=np.int64).astype(np.uint64))


ROUTE_KEYS = ("pair", "m", "off", "ptr", "k", "ft", "tag")


def _rt_empty():
    return {"pair": np.zeros(0, np.int64), "m": np.zeros(0), "off": np.zeros(0), "ptr": np.zeros(1, np.int64),
            "k": np.zeros(0, np.int32), "ft": np.zeros(0, np.float32), "tag": np.zeros(0, np.int16)}


def rt_take(R, idx):
    """Rows idx of a route table, their entries gathered."""
    idx = np.asarray(idx, dtype=np.int64)
    ln = np.diff(R["ptr"])[idx]
    st = R["ptr"][:-1][idx]
    pos = np.repeat(st, ln) + (np.arange(int(ln.sum())) - np.repeat(np.cumsum(ln) - ln, ln))
    return {"pair": R["pair"][idx], "m": R["m"][idx], "off": R["off"][idx], "ptr": np.r_[0, np.cumsum(ln)].astype(np.int64),
            "k": R["k"][pos], "ft": R["ft"][pos], "tag": R["tag"][idx]}


def rt_concat(Rs):
    Rs = [R for R in Rs if len(R["pair"])]
    if not Rs:
        return _rt_empty()
    out = {k: np.concatenate([R[k] for R in Rs]) for k in ("pair", "m", "off", "k", "ft", "tag")}
    ptrs, off = [np.zeros(1, np.int64)], 0
    for R in Rs:
        ptrs.append(R["ptr"][1:] + off)
        off += int(R["ptr"][-1])
    out["ptr"] = np.concatenate(ptrs)
    return out


def rt_er(R):
    """Each entry's route."""
    return np.repeat(np.arange(len(R["pair"]), dtype=np.int64), np.diff(R["ptr"]))


def menu_routes(sim, menu, corridor):
    """The menu's routes as route rows (pair, metres, feet off the network on the baseline, per cover the feet it holds),
    keeping those within DETOUR x the pair's shortest route (the scorer never takes a longer one) and within the
    corridor. Returns the table and the count left out."""
    rp = menu["r_pair"].astype(np.int64)
    alive = (menu["r_m"] <= sim.DETOUR * menu["pair_m0"][rp] + 1e-3) & (menu["r_ft"] <= corridor)
    cnt = np.bincount(menu["e_route"], minlength=len(rp))
    R = {"pair": rp, "m": menu["r_m"].astype(np.float64), "off": menu["r_off"].astype(np.float64),
         "ptr": np.r_[0, np.cumsum(cnt)].astype(np.int64), "k": menu["e_cov"].astype(np.int32), "ft": menu["e_ft"].astype(np.float32),
         "tag": np.zeros(len(rp), np.int16)}
    # the menu's route order follows its pool's arrival order; sort so the table (and every hash and tie on it) is the
    # same run to run
    kind = np.unique(menu["r_kind"], return_inverse=True)[1]
    keep = np.flatnonzero(alive)
    keep = keep[np.lexsort((menu["r_m"][keep], menu["r_chunk"][keep], kind[keep], rp[keep]))]
    return rt_take(R, keep), int((~alive).sum())


def cover_built(cov_ptr, cov_c, built):
    """Per cover, whether any of its chunks is built."""
    return np.logical_or.reduceat(built[cov_c], cov_ptr[:-1]) if len(cov_c) else np.zeros(0, dtype=bool)


def route_on(sim, R, cb=None, er=None):
    """Each route's on-network share with the covers cb (bool per cover; None: every one) built, and whether it rides on
    at least one built cover."""
    er = rt_er(R) if er is None else er
    n = len(R["pair"])
    ft = R["ft"].astype(np.float64)
    if cb is None:
        bft = np.bincount(er, weights=ft, minlength=n)
        anyb = np.diff(R["ptr"]) > 0
    else:
        hit = cb[R["k"]]
        bft = np.bincount(er, weights=np.where(hit, ft, 0.0), minlength=n)
        anyb = np.bincount(er[hit], minlength=n) > 0
    return np.clip(1.0 - (R["off"] - bft) * sim.FT / np.maximum(R["m"], 1.0), 0.0, 1.0), anyb


def route_values(sim, ct, R, pkey, cb=None, batch=4000000):
    """Each route's value with the covers cb built: its pair's year-10 family-car trips removed at the route's on-network
    share (pair_benefit), counted only when the route rides on a built cover. With none of its covers built the scorer
    keeps the pair on today's route, whatever this route's own share."""
    on, anyb = route_on(sim, R, cb)
    v = np.zeros(len(on))
    idx = np.flatnonzero(anyb)
    for lo in range(0, len(idx), batch):
        i = idx[lo:lo + batch]
        v[i] = pair_benefit(ct, pkey[R["pair"][i]], on[i])
    return v


def pair_best(R, v, n_pairs):
    """Per pair, its most valuable route's value and index (-1 where none is worth anything)."""
    best = np.zeros(n_pairs)
    arg = np.full(n_pairs, -1, dtype=np.int64)
    pos = np.flatnonzero(v > 0)
    if len(pos):
        o = pos[np.lexsort((-v[pos], R["pair"][pos]))]
        p = R["pair"][o]
        first = np.r_[True, p[1:] != p[:-1]]
        best[p[first]] = v[o[first]]
        arg[p[first]] = o[first]
    return best, arg


def _rank_in_pair(pair, score, mask):
    """Each masked route's rank within its pair by score, highest first; a large number elsewhere."""
    rank = np.full(len(pair), 1 << 30, dtype=np.int64)
    idx = np.flatnonzero(mask)
    if not len(idx):
        return rank
    o = idx[np.lexsort((-score[idx], pair[idx]))]
    p = pair[o]
    st = np.r_[True, p[1:] != p[:-1]]
    first = np.maximum.accumulate(np.where(st, np.arange(len(o)), 0))
    rank[o] = np.arange(len(o)) - first
    return rank


def rt_dedupe(R):
    """One row per (pair, route): identical routes (the same metres, feet off the network and feet per cover) kept once,
    a traced one before a menu one."""
    n = len(R["pair"])
    if not n:
        return R
    H1, H2 = _hash_keys(int(R["k"].max()) + 2 if len(R["k"]) else 2)
    q = np.rint(R["ft"].astype(np.float64)).astype(np.int64).astype(np.uint64)
    with np.errstate(over="ignore"):
        cs = np.r_[np.uint64(0), np.cumsum(H1[R["k"]] * (q + np.uint64(1)), dtype=np.uint64)]
        h = cs[R["ptr"][1:]] - cs[R["ptr"][:-1]]
        h = h + H2[0] * np.rint(R["off"]).astype(np.int64).astype(np.uint64) + H2[1] * np.rint(R["m"]).astype(np.int64).astype(np.uint64)
    o = np.lexsort((-R["tag"].astype(np.int64), h, R["pair"]))
    p, hh = R["pair"][o], h[o]
    first = np.r_[True, (p[1:] != p[:-1]) | (hh[1:] != hh[:-1])]
    return rt_take(R, np.sort(o[first]))


def prune_menu(sim, ct, R, pkey, cost_cov):
    """Each pair's menu routes cut to the ROUTES_EFF most valuable per $ of their chunks and the ROUTES_VAL most valuable,
    both with all of the route's chunks built, after dropping duplicates and routes worth nothing. Returns the table and
    the counts."""
    R = rt_dedupe(R)
    n0 = len(R["pair"])
    v = route_values(sim, ct, R, pkey)
    er = rt_er(R)
    price = np.bincount(er, weights=cost_cov[R["k"]], minlength=n0)
    live = v > 1e-9
    keep = live & ((_rank_in_pair(R["pair"], v / np.maximum(price, 1e-3), live) < ROUTES_EFF) |
                   (_rank_in_pair(R["pair"], v, live) < ROUTES_VAL))
    return rt_take(R, np.flatnonzero(keep)), {"deduped": n0, "worthNothing": int((~live).sum()), "kept": int(keep.sum())}


# -- the program --------------------------------------------------------------------------------------------------

def build_program(sim, ct, R, pkey, pw, pn, nc, cost, cov_ptr, cov_c):
    """The program from a route table. Each route's value is supermodular in which of its covers are built (the benefit
    is convex in the on-network share), so two linear functions bound it from below: "A" exact with one cover built
    (c the route's value at its baseline share, w_k its value with cover k alone built less c), "B" exact with all and
    with all but one built (w_k its value with all built less with all but k, c the rest). A route with one cover gets A,
    two B (exact at every built subset), three or more both. A use is one such function; it counts only with one of the
    route's covers built, and never above the route's value with all built. Pairs whose uses match (the same covers and
    every coefficient within BIN of the pair's best value) merge into one group, the group's coefficients the members'
    sums, and a group takes at most one use. Returns the program and each group's pairs."""
    n = len(R["pair"])
    er = rt_er(R)
    a = R["ft"].astype(np.float64) * sim.FT / np.maximum(R["m"][er], 1.0)
    # a route's covers holding under PROG_MIN_SHARE of its cover feet are left out of its uses (counted as never built,
    # so each use stays a lower bound): a median menu route crosses 26 covers, most of them a few feet of a cross
    # street's chunk
    tot = np.bincount(er, weights=a, minlength=n)
    ke = a >= PROG_MIN_SHARE * tot[er]
    R = {"pair": R["pair"], "m": R["m"], "off": R["off"], "k": R["k"][ke],
         "ptr": np.r_[0, np.cumsum(np.bincount(er[ke], minlength=n))].astype(np.int64)}
    er, a = er[ke], a[ke]
    nent = np.diff(R["ptr"])
    base = np.clip(1.0 - R["off"] * sim.FT / np.maximum(R["m"], 1.0), 0.0, 1.0)
    full = np.clip(base + np.bincount(er, weights=a, minlength=n), 0.0, 1.0)
    pk = pkey[R["pair"]]
    f0 = pair_benefit(ct, pk, base)
    vf = pair_benefit(ct, pk, full)
    vs = pair_benefit(ct, pk[er], np.clip(base[er] + a, 0.0, 1.0))
    vm = pair_benefit(ct, pk[er], np.clip(full[er] - a, 0.0, 1.0))
    wa = np.maximum(vs - f0[er], 0.0)
    wb = np.maximum(vf[er] - vm, 0.0)
    cb_ = vf - np.bincount(er, weights=wb, minlength=n)
    has_a = (nent == 1) | (nent >= 3)
    has_b = nent >= 2
    # the uses, route by route: (route, kind, c, U)
    u_r = np.r_[np.flatnonzero(has_a), np.flatnonzero(has_b)]
    u_kind = np.r_[np.zeros(int(has_a.sum()), np.int8), np.ones(int(has_b.sum()), np.int8)]
    u_c = np.r_[f0[has_a], cb_[has_b]]
    u_U = vf[u_r]
    live = u_U > 1e-9
    u_r, u_kind, u_c, u_U = u_r[live], u_kind[live], u_c[live], u_U[live]
    o = np.lexsort((u_kind, u_r, R["pair"][u_r]))
    u_r, u_kind, u_c, u_U = u_r[o], u_kind[o], u_c[o], u_U[o]
    u_p = R["pair"][u_r]
    ptr, kk = R["ptr"], R["k"]
    vmax = np.zeros(int(u_p.max()) + 1 if len(u_p) else 0)
    if len(u_p):
        np.maximum.at(vmax, u_p, u_U)
    # group pairs by their use lists
    st = np.flatnonzero(np.r_[True, u_p[1:] != u_p[:-1]]) if len(u_p) else np.zeros(0, np.int64)
    en = np.r_[st[1:], len(u_p)]
    groups = {}
    for s_, e_ in zip(st.tolist(), en.tolist()):
        p = int(u_p[s_])
        unit = BIN * vmax[p]
        key = []
        for u in range(s_, e_):
            r = int(u_r[u])
            w = (wa if u_kind[u] == 0 else wb)[ptr[r]:ptr[r + 1]]
            key.append((int(u_kind[u]), tuple(kk[ptr[r]:ptr[r + 1]].tolist()), int(np.rint(u_c[u] / unit)),
                        tuple(np.rint(w / unit).astype(np.int64).tolist())))
        o2 = sorted(range(e_ - s_), key=lambda i: key[i])
        groups.setdefault(tuple(key[i] for i in o2), []).append((p, [s_ + i for i in o2]))
    grp = sorted(groups.values(), key=lambda m: m[0][0])
    del groups
    use_g, uc, uU, use_ptr, use_k, use_w, g_pairs, g_ptr, wn, sn = [], [], [], [0], [], [], [], [0], [], []
    for gi, members in enumerate(grp):
        g_pairs.extend(m[0] for m in members)
        g_ptr.append(len(g_pairs))
        wn.append(float(sum(pw[m[0]] for m in members)))
        sn.append(float(sum(pn[m[0]] for m in members)))
        for i in range(len(members[0][1])):
            us = [m[1][i] for m in members]
            r0 = int(u_r[us[0]])
            ws = np.zeros(int(ptr[r0 + 1] - ptr[r0]))
            for u in us:
                r = int(u_r[u])
                ws += (wa if u_kind[u] == 0 else wb)[ptr[r]:ptr[r + 1]]
            use_g.append(gi)
            uc.append(float(u_c[us].sum()))
            uU.append(float(u_U[us].sum()))
            use_k.extend(kk[ptr[r0]:ptr[r0 + 1]].tolist())
            use_w.extend(ws.tolist())
            use_ptr.append(len(use_k))
    use_k = np.array(use_k, dtype=np.int32)
    used = np.zeros(nc, dtype=bool)
    if len(use_k):
        used[cov_c[np.concatenate([np.arange(cov_ptr[k], cov_ptr[k + 1]) for k in np.unique(use_k)])]] = True
    P = {"nc": nc, "cost": cost, "cov_ptr": cov_ptr, "cov_c": cov_c, "usedChunks": np.flatnonzero(used), "ng": len(grp),
         "wn": np.array(wn), "sn": np.array(sn), "nu": len(use_g), "use_g": np.array(use_g, dtype=np.int32), "uc": np.array(uc),
         "uU": np.array(uU), "use_ptr": np.array(use_ptr, dtype=np.int64), "use_k": use_k, "use_w": np.array(use_w)}
    P["stats"] = {"routes": int(n), "pairs": int(len(st)), "groups": len(grp), "uses": len(use_g), "useEntries": int(len(use_k)),
                  "chunksUsed": int(used.sum()), "driversInProgram": round(float(np.sum(wn)), 1),
                  "carTripsInProgram": round(float(vmax.sum()), 1), "binPct": 100 * BIN, "routesEff": ROUTES_EFF, "routesVal": ROUTES_VAL,
                  "minCoverShare": PROG_MIN_SHARE}
    aux = {"g_pairs": np.array(g_pairs, dtype=np.int64), "g_ptr": np.array(g_ptr, dtype=np.int64)}
    return P, aux


def _group_use_ranges(use_g):
    """(first, end) use index of each group; a group's uses are contiguous."""
    if not len(use_g):
        return []
    st = np.flatnonzero(np.r_[True, use_g[1:] != use_g[:-1]])
    return list(zip(st.tolist(), np.r_[st[1:], len(use_g)].tolist()))


def use_values(P, built, q=None):
    """Each use's value under the built chunks (bool per chunk): min(U, c + the w of its built covers), 0 when none of
    its covers is built or that is negative. With q (the solver's integer coefficients), in those units."""
    cb = cover_built(P["cov_ptr"], P["cov_c"], built)
    nu = P["nu"]
    ue = np.repeat(np.arange(nu), np.diff(P["use_ptr"]))
    c, w, U = (P["uc"], P["use_w"], P["uU"]) if q is None else q
    hit = cb[P["use_k"]]
    L = c + np.bincount(ue, weights=np.where(hit, w, 0), minlength=nu)
    ok = np.bincount(ue[hit], minlength=nu) > 0
    return np.where(ok, np.clip(L, 0, U), 0)


def group_values(P, val):
    cur = np.zeros(P["ng"])
    if len(val):
        np.maximum.at(cur, P["use_g"], val)
    return cur


def best_uses(P, built, q=None):
    """Each group's most valuable use under the built chunks; -1 where none is worth anything."""
    v = use_values(P, built, q)
    out = np.full(P["ng"], -1, dtype=np.int64)
    pos = np.flatnonzero(v > 0)
    if len(pos):
        o = pos[np.lexsort((-v[pos], P["use_g"][pos]))]
        g = P["use_g"][o]
        first = np.r_[True, g[1:] != g[:-1]]
        out[g[first]] = o[first]
    return out


def offplan_conflicts(seg, stt, ch):
    """Pairs of chunks that can't both be built: the parallel rule run between off-plan picks (Bryan, 2026-10-18: "any off
    plan pick must satisfy the same one block away rules vs other off plan picks as we applied to off plan vs on plan. I
    see too many streets where multiple parallel streets are picked."). An off-plan block of one chunk conflicts with an
    off-plan block of another when their bearings are within PARALLEL_DEG, the other runs PARALLEL_MIN_FT to that side's
    one-block reach (seg.next_street_reach()) to the side, and it covers at least PARALLEL_OVERLAP of the block's length, as parallel_drop() tests a block against
    an all-ages street. Two chunks conflict when any of their blocks do. A block is off the plan when its CNN is not in
    the plan's network (north-star traced.geojson)."""
    from scipy.spatial import cKDTree
    plan_cnn = {str(f["properties"]["cnn"]).lstrip("0") for f in stt.read(stt.NS, "traced.geojson")["features"]}
    lat0 = math.radians(37.76)
    fx, fy = 364320.0 * math.cos(lat0), 364320.0   # feet a degree of longitude and of latitude
    nsr = seg.next_street_reach()
    A, B, owner, R = [], [], [], []
    for i, c in enumerate(ch):
        for cnn, pts in zip(c["cnns"], c["pts"]):
            if str(cnn).lstrip("0") in plan_cnn or len(pts) < 2:
                continue
            A.append((pts[0][0] * fx, pts[0][1] * fy))
            B.append((pts[-1][0] * fx, pts[-1][1] * fy))
            owner.append(i)
            R.append(nsr.get(str(cnn).lstrip("0"), (0.0, 0.0, seg.ONE_BLOCK_FT, seg.ONE_BLOCK_FT)))
    if not owner:
        return np.zeros((0, 2), dtype=np.int64)
    A, B, owner, R = np.array(A), np.array(B), np.array(owner), np.array(R)
    L = np.hypot(*(B - A).T)
    ok = L > 30.0
    A, B, owner, L, R = A[ok], B[ok], owner[ok], L[ok], R[ok]
    U = (B - A) / L[:, None]
    M = (A + B) / 2
    tree = cKDTree(M)
    cos_lim = math.cos(math.radians(seg.PARALLEL_DEG))
    pairs = set()
    for k in range(len(L)):
        u, nrm = U[k], np.array([-U[k][1], U[k][0]])
        ix = np.array(tree.query_ball_point(M[k], L[k] / 2 + seg.NEXT_STREET_MAX_FT), dtype=np.int64)
        ix = ix[owner[ix] != owner[k]]
        if not len(ix):
            continue
        rl, rr = (R[k][2], R[k][3]) if np.dot(u, R[k][:2]) >= 0 else (R[k][3], R[k][2])
        soff = (M[ix] - A[k]) @ nrm
        off = np.abs(soff)
        ix = ix[(np.abs(U[ix] @ u) >= cos_lim) & (off >= seg.PARALLEL_MIN_FT) & (off <= np.where(soff > 0, rl, rr))]
        for j in ix:
            t = sorted(((A[j] - A[k]) @ u, (B[j] - A[k]) @ u))
            if min(t[1], L[k]) - max(t[0], 0.0) >= seg.PARALLEL_OVERLAP * L[k]:
                pairs.add((min(owner[k], owner[j]), max(owner[k], owner[j])))
    return np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)



# -- the solve ----------------------------------------------------------------------------------------------------

PROG_KEYS = ("nc", "cost", "cov_ptr", "cov_c", "usedChunks", "ng", "wn", "sn", "nu", "use_g", "uc", "uU", "use_ptr", "use_k", "use_w")
SCALE = 1e5   # the solver's units: car trips x SCALE, so a use worth 1e-5 car trips is still counted


def save_program(P, path):
    np.savez(path, **{k: np.asarray(P[k]) for k in PROG_KEYS}, stats=np.array(json.dumps(P["stats"])),
             conflicts=np.asarray(P.get("conflicts", np.zeros((0, 2), dtype=np.int64))),
             calm=np.asarray(P.get("calm", np.zeros(P["nc"]))))


def load_program(path):
    z = np.load(path)
    P = {k: z[k] for k in PROG_KEYS}
    for k in ("nc", "ng", "nu"):
        P[k] = int(P[k])
    P["stats"] = json.loads(str(z["stats"]))
    P["conflicts"] = z["conflicts"] if "conflicts" in z.files else np.zeros((0, 2), dtype=np.int64)
    P["calm"] = z["calm"] if "calm" in z.files else np.zeros(P["nc"])
    return P


def _quant(P):
    """The solver's integer coefficients (c, w, U) of every use."""
    return (np.rint(P["uc"] * SCALE), np.rint(P["use_w"] * SCALE), np.rint(P["uU"] * SCALE))


def _pack(r):
    return dict(r, build=np.asarray(r["build"]).tolist()) if r else None


def _unpack(r):
    return dict(r, build=np.array(r["build"], dtype=np.int64)) if r else None


def greedy_plan(P, budget, forced=None):
    """The greedy plan: starting from the forced chunks, repeatedly build the chunks that add the most program value per $,
    within the budget, the conflict pairs and the calming cap where one is set (CP-SAT keeps this plan when it stops below
    it, so it must be one the solver could return). Each step adds the best chunk and, while it is far from the budget,
    up to a tenth as many again of the next best, each judged on the plan before the step. Returns the built chunks and
    the plan's program value."""
    nc, cost = P["nc"], P["cost"]
    cov_ptr, cov_c = P["cov_ptr"], P["cov_c"].astype(np.int64)
    nu = P["nu"]
    conf = P.get("conflicts", np.zeros((0, 2), dtype=np.int64))
    calm = P.get("calm", np.zeros(nc))
    built = np.zeros(nc, dtype=bool)
    built[np.asarray(forced or [], dtype=np.int64)] = True
    banned = np.zeros(nc, dtype=bool)

    def ban():
        if len(conf):
            banned[conf[:, 1][built[conf[:, 0]]]] = True
            banned[conf[:, 0][built[conf[:, 1]]]] = True
    ban()
    # each (use, entry) once per chunk of its cover
    ue = np.repeat(np.arange(nu), np.diff(P["use_ptr"]))
    k = P["use_k"].astype(np.int64)
    clen = np.diff(cov_ptr)[k]
    x_u = np.repeat(ue, clen)
    x_w = np.repeat(P["use_w"], clen)
    x_k = np.repeat(k, clen)
    x_c = cov_c[np.repeat(cov_ptr[:-1][k], clen) + (np.arange(int(clen.sum())) - np.repeat(np.cumsum(clen) - clen, clen))]
    del ue, k, clen
    spent = float(cost[built].sum())
    calm_spent = float(calm[built].sum())
    while True:
        cb = cover_built(cov_ptr, P["cov_c"], built)
        val = use_values(P, built)
        cur = group_values(P, val)
        hit = cb[P["use_k"]]
        uen = np.repeat(np.arange(nu), np.diff(P["use_ptr"]))
        L = P["uc"] + np.bincount(uen, weights=np.where(hit, P["use_w"], 0), minlength=nu)
        live = ~cb[x_k] & ~built[x_c] & ~banned[x_c] & (spent + cost[x_c] <= budget + 1e-9)
        if CALM_CAP_MI is not None:
            live &= calm_spent + calm[x_c] <= CALM_CAP_MI + 1e-9
        if not live.any():
            break
        key, inv = np.unique(x_u[live] * nc + x_c[live], return_inverse=True)
        dw = np.bincount(inv, weights=x_w[live])
        u, c = key // nc, key % nc
        g = P["use_g"][u].astype(np.int64)
        gain = np.maximum(np.minimum(L[u] + dw, P["uU"][u]) - cur[g], 0.0)
        pos = gain > 0
        if not pos.any():
            break
        k2, inv2 = np.unique(g[pos] * nc + c[pos], return_inverse=True)
        mg = np.zeros(len(k2))
        np.maximum.at(mg, inv2, gain[pos])
        gc = np.bincount(k2 % nc, weights=mg, minlength=nc)
        ratio = np.where(gc > 0, gc / np.maximum(cost, 1e-6), -1.0)
        order = np.argsort(-ratio, kind="stable")
        n_take = max(1, int(0.1 * built.sum())) if spent < 0.8 * budget else 1
        took = 0
        for ci in order.tolist():
            if ratio[ci] <= 0 or took >= n_take:
                break
            if built[ci] or banned[ci] or spent + cost[ci] > budget + 1e-9:
                continue
            if CALM_CAP_MI is not None and calm_spent + calm[ci] > CALM_CAP_MI + 1e-9:
                continue
            built[ci] = True
            spent += float(cost[ci])
            calm_spent += float(calm[ci])
            ban()
            took += 1
        if not took:
            break
    return np.flatnonzero(built), float(group_values(P, use_values(P, built)).sum())


def seed_map(ch, path):
    """{budget: today's chunk indexes, in seed order}, and the coverage per budget. An old plan is the CNNs of its chosen
    chunks; today's chunk maps onto it when more than SEED_FRAC of its CNNs are in that set. Seed order puts first the
    chunks that map onto the smallest old budget (old budgets are nested phases), then by share mapped, then by id."""
    old = json.load(open(path))
    ocnn = {c["id"]: c["cnns"] for c in old["chunks"]}
    first, frac, cov = {}, {}, {}
    sets = {}
    for ob in sorted(old["budgets"], key=lambda r: r["budgetM"]):
        sets[ob["budgetM"]] = set(x for cid in ob["chunks"] for x in ocnn[cid])
    for b in sorted(sets):
        S = sets[b]
        hit = []
        for i, c in enumerate(ch):
            cn = c["cnns"]
            f = sum(x in S for x in cn) / float(max(len(cn), 1))
            if f > SEED_FRAC:
                hit.append(i)
                first.setdefault(i, b)
                frac[(b, i)] = f
        covered = set(x for i in hit for x in ch[i]["cnns"]) & S
        cov[b] = {"oldChunks": len(next(r for r in old["budgets"] if r["budgetM"] == b)["chunks"]), "oldCnns": len(S),
                  "chunks": len(hit), "cnnsCovered": len(covered), "coveredPct": round(100 * len(covered) / max(len(S), 1), 1),
                  "costM": round(sum(ch[i]["costM"] for i in hit), 2), "mi": round(sum(ch[i]["mi"] for i in hit), 2),
                  "calmMi": round(sum(ch[i].get("calmMi", 0.0) for i in hit), 2), "_hit": hit}
    out = {}
    for b in BUDGETS_M:
        # an old file without this budget seeds from its largest budget under it
        ob = max([x for x in sets if x <= b], default=None)
        if ob is None:
            continue
        hit = cov[ob]["_hit"]
        out[b] = sorted(hit, key=lambda i: (first[i], -frac[(ob, i)], ch[i]["id"]))
    for v in cov.values():
        del v["_hit"]
    return out, cov


def seed_trim(order, budget, cost, calm, conf, forced):
    """The seed as a feasible start: the forced chunks, then each seed chunk in order while it fits the budget and the
    calming cap and conflicts with nothing already in."""
    built = set(forced or [])
    spent = float(sum(cost[i] for i in built))
    cspent = float(sum(calm[i] for i in built))
    partner = {}
    for a_, b_ in (conf.tolist() if len(conf) else []):
        partner.setdefault(a_, set()).add(b_)
        partner.setdefault(b_, set()).add(a_)
    dropped = 0
    for i in order:
        if i in built:
            continue
        if spent + cost[i] > budget + 1e-9 or (CALM_CAP_MI is not None and cspent + calm[i] > CALM_CAP_MI + 1e-9) \
                or partner.get(i, set()) & built:
            dropped += 1
            continue
        built.add(i)
        spent += float(cost[i])
        cspent += float(calm[i])
    return sorted(built), {"chunks": len(built), "costM": round(spent, 2), "calmMi": round(cspent, 2), "seedDropped": dropped}


def _plan_value(P, chunks):
    built = np.zeros(P["nc"], dtype=bool)
    built[np.asarray(chunks, dtype=np.int64)] = True
    return float(group_values(P, use_values(P, built)).sum())


def _feasible(P, chunks, budget, forced=None):
    """Whether a chunk list is a plan the solver could return: within the budget, holding every forced chunk, no
    conflict pair both built, and within the calming cap where one is set."""
    built = np.zeros(P["nc"], dtype=bool)
    built[np.asarray(chunks, dtype=np.int64)] = True
    if forced is not None and not built[np.asarray(forced, dtype=np.int64)].all():
        return False
    if float(P["cost"][built].sum()) > budget + 1e-6:
        return False
    conf = P.get("conflicts", np.zeros((0, 2), dtype=np.int64))
    if len(conf) and (built[conf[:, 0]] & built[conf[:, 1]]).any():
        return False
    return CALM_CAP_MI is None or float(P["calm"][built].sum()) <= CALM_CAP_MI + 1e-6


def _peak_gb():
    """This process's peak resident memory in GB: VmHWM on Linux (ru_maxrss there carries a parent's peak across exec),
    ru_maxrss elsewhere."""
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 2 ** 20
    except OSError:
        pass
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (2 ** 30 if sys.platform == "darwin" else 2 ** 20)


def _solve_isolated(prog_path, budget, tag, solver, path, hint=None, forced=None):
    """One solve in a fresh Python process that reads only the saved program, so it holds nothing of the sim and frees
    its memory when it exits. The result is cached at path, so a restart picks up where it stopped. The process's
    peak resident memory is kept with the result."""
    if os.path.exists(path):
        d = json.load(open(path))
        r = _unpack(d["r"])
        if r is not None:
            r["peakGB"] = d.get("peakGB")
        return r
    import subprocess
    cmd = [sys.executable, os.path.abspath(__file__), "--solve", prog_path, str(budget), tag, solver, path, hint or "-", forced or "-"]
    # the child's footprint stop leaves room for this process beside it under the watchdog's cap
    pf = _footprint_mb() or 0.0
    env = dict(os.environ, SEGMENTS_CPSAT_MEM_MB=str(int(min(CPSAT_MEM_MB, RUN_CAP_MB - pf))))
    subprocess.run(cmd, check=True, env=env)
    d = json.load(open(path))
    print("  solve %s (%s, $%gM): peak %.2f GB in its process, %ss" % (tag, solver, budget, d["peakGB"], d["r"]["seconds"] if d["r"] else "?"), flush=True)
    r = _unpack(d["r"])
    if r is not None:
        r["peakGB"] = d["peakGB"]
    return r


def _solve_main(prog_path, budget, tag, solver, path, hint=None, forced=None):
    P = load_program(prog_path)
    t0 = time.time()
    h = json.load(open(hint)) if hint and hint != "-" else None
    f = json.load(open(forced)) if forced and forced != "-" else None
    g_build, g_val = greedy_plan(P, budget, f)
    assert _feasible(P, g_build, budget, f), "greedy plan breaks the budget, a conflict pair or the calming cap"
    h_val = _plan_value(P, h) if h and _feasible(P, h, budget, f) else 0.0
    start = "greedy" if g_val >= h_val else ("seed" if SEED_PATH and tag.startswith("r1-") else "last round")
    if g_val >= h_val:
        h = g_build.tolist()
    s_val = max(g_val, h_val)
    t_greedy = round(time.time() - t0, 1)
    r = solve_highs(P, budget, h, f) if solver == "highs" else solve_cpsat(P, budget, h, f)
    kept = False
    if r is None or _plan_value(P, np.flatnonzero(r[0])) < s_val - 1e-9:
        # CP-SAT does not promise to return its hint: a solve stopped early (on time or memory) can end below the
        # feasible plan it started from, and then that plan is the answer
        hb = np.zeros(P["nc"], dtype=bool)
        hb[np.asarray(h, dtype=np.int64)] = True
        r = (hb, None, "NO SOLUTION, start kept" if r is None else r[2] + ", start kept", 0 if r is None else r[3],
             "time" if r is None else r[4], None if r is None else r[5])
        kept = True
    build, gap, status, nodes, stop, bound = r
    val = use_values(P, build)
    gv = group_values(P, val)
    served = gv > 0
    obj = float(gv.sum())
    if kept and bound is not None:
        gap = (bound - obj) / max(obj, 1e-9)
    out = {"build": np.flatnonzero(build), "carTrips": obj, "drivers": float(P["wn"][served].sum()),
           "students": float(P["sn"][served].sum()), "gap": gap, "status": status, "message": "%s: %s" % (solver, status),
           "seconds": round(time.time() - t0, 1), "greedySeconds": t_greedy, "nodes": nodes, "solver": solver,
           "greedyCarTrips": round(g_val, 2), "startedFrom": start, "startCarTrips": round(s_val, 2),
           "timeLimitHit": stop == "time", "stoppedOn": stop, "startKept": kept, "modelStats": P["stats"]}
    tmp = path + ".tmp"
    json.dump({"r": _pack(out), "peakGB": round(_peak_gb(), 2)}, open(tmp, "w"))
    os.replace(tmp, path)


def solve_highs(P, budget, hint=None, forced=None):
    """scipy.optimize.milp (HiGHS) on the same program: build and select binary, cover share and use value continuous.
    Rows: a cover is built only as far as its chunks are; a use's value is at most U x select and at most c + w . covers
    (with c < 0, relaxed by -c when not selected); a selected use needs a built cover; a group selects at most one; the
    budget, the conflict pairs and the calming cap. Returns (build, gap, status, nodes, stop, bound)."""
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import coo_matrix
    nc, nu, ng = P["nc"], P["nu"], P["ng"]
    cov_ptr, cov_c = P["cov_ptr"], P["cov_c"].astype(np.int64)
    ncov = len(cov_ptr) - 1
    # variables: x (nc), v (ncov), s (nu), y (nu)
    X, V, Sv, Y = 0, nc, nc + ncov, nc + ncov + nu
    nv = Y + nu
    rows, cols, vals, lo, hi = [], [], [], [], []
    r0 = 0

    def add(rr, cc, vv, l, h):
        nonlocal r0
        rows.append(np.asarray(rr) + r0)
        cols.append(np.asarray(cc))
        vals.append(np.asarray(vv, dtype=float))
        lo.append(np.asarray(l, dtype=float))
        hi.append(np.asarray(h, dtype=float))
        r0 += len(l)
    # v_k - sum of its chunks <= 0
    clen = np.diff(cov_ptr)
    add(np.r_[np.arange(ncov), np.repeat(np.arange(ncov), clen)], np.r_[V + np.arange(ncov), X + cov_c],
        np.r_[np.ones(ncov), -np.ones(len(cov_c))], np.full(ncov, -np.inf), np.zeros(ncov))
    ue = np.repeat(np.arange(nu), np.diff(P["use_ptr"]))
    k = P["use_k"].astype(np.int64)
    # y - U s <= 0
    add(np.r_[np.arange(nu), np.arange(nu)], np.r_[Y + np.arange(nu), Sv + np.arange(nu)], np.r_[np.ones(nu), -P["uU"]],
        np.full(nu, -np.inf), np.zeros(nu))
    # y - w . v + M s <= c + M, M = max(0, -c)
    M = np.maximum(0.0, -P["uc"])
    add(np.r_[np.arange(nu), ue, np.arange(nu)], np.r_[Y + np.arange(nu), V + k, Sv + np.arange(nu)],
        np.r_[np.ones(nu), -P["use_w"], M], np.full(nu, -np.inf), P["uc"] + M)
    # s - sum of its covers <= 0
    add(np.r_[np.arange(nu), ue], np.r_[Sv + np.arange(nu), V + k], np.r_[np.ones(nu), -np.ones(len(k))], np.full(nu, -np.inf), np.zeros(nu))
    # a group selects at most one
    add(P["use_g"], Sv + np.arange(nu), np.ones(nu), np.full(ng, -np.inf), np.ones(ng))
    add(np.zeros(nc, dtype=np.int64), X + np.arange(nc), P["cost"], [-np.inf], [budget])
    cf = P.get("conflicts", np.zeros((0, 2), dtype=np.int64))
    if len(cf):
        add(np.repeat(np.arange(len(cf)), 2), X + cf.reshape(-1), np.ones(2 * len(cf)), np.full(len(cf), -np.inf), np.ones(len(cf)))
    if CALM_CAP_MI is not None:
        add(np.zeros(nc, dtype=np.int64), X + np.arange(nc), P["calm"], [-np.inf], [CALM_CAP_MI])
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(r0, nv)).tocsr()
    c = np.zeros(nv)
    c[Y:] = -1.0
    integrality = np.zeros(nv)
    integrality[X:X + nc] = 1
    integrality[Sv:Sv + nu] = 1
    xlb, xub = np.zeros(nv), np.ones(nv)
    xub[Y:] = np.maximum(P["uU"], 0)
    unused = np.ones(nc, dtype=bool)
    unused[P["usedChunks"]] = False
    xub[X:X + nc][unused] = 0.0
    if forced:
        xlb[np.asarray(forced, dtype=np.int64)] = 1.0
        xub[np.asarray(forced, dtype=np.int64)] = 1.0
    res = milp(c, constraints=LinearConstraint(A, np.concatenate(lo), np.concatenate(hi)), integrality=integrality,
               bounds=Bounds(xlb, xub), options={"disp": False, "time_limit": TIME_LIMIT_S, "mip_rel_gap": MIP_REL_GAP, "presolve": True})
    if res.x is None:
        return None
    gap = float(res.mip_gap) if res.mip_gap is not None else None
    obj = -float(res.fun)
    return (res.x[:nc] > 0.5, gap, str(res.message), int(res.mip_node_count or 0),
            "optimal" if res.status == 0 else "time", obj * (1 + gap) if gap is not None else None)


def gap_words(gap):
    """The solver's relative gap, (best bound - objective) / objective, in words: 4.5 means the proven ceiling is 5.5
    times the plan's promise, so the solve stopped at its time limit far from MIP_REL_GAP and proves little about how
    close to the best plan it is."""
    if gap is None:
        return "bound gap unknown"
    return "bound gap %.0f%% (proven ceiling %.1fx the promise; target %.0f%%)" % (100 * gap, 1 + gap, 100 * MIP_REL_GAP)


def solve_cpsat(P, budget, hint=None, forced=None):
    """OR-Tools CP-SAT on THREADS workers. Booleans: build per chunk, built per shared cover (only when one of its chunks
    is), select per use. Integers: each use's value y, at most U x select and at most c + w . built covers (enforced by
    select where c < 0); a selected use needs one of its covers built; a group selects at most one; costs in $1K, the
    objective sum(y) in car trips x SCALE, to MIP_REL_GAP. With hint (a chunk list: the greedy plan or the last round's),
    the search starts from it and the use it values most in each group. Returns (build, gap, status, nodes, stop,
    bound in car trips)."""
    from ortools.sat.python import cp_model
    nc, nu = P["nc"], P["nu"]
    cov_ptr, cov_c = P["cov_ptr"], P["cov_c"]
    m = cp_model.CpModel()
    used = set(P["usedChunks"].tolist()) | set(forced or [])
    build = [m.NewBoolVar("b%d" % i) if i in used else None for i in range(nc)]
    cq, wq, Uq = _quant(P)
    ukeys = np.unique(P["use_k"]).tolist()
    cvar = {}
    for k in ukeys:
        if k < nc:
            cvar[k] = build[k]
        else:
            v = m.NewBoolVar("v%d" % k)
            m.AddBoolOr([v.Not()] + [build[c] for c in cov_c[cov_ptr[k]:cov_ptr[k + 1]].tolist()])
            cvar[k] = v
    up = P["use_ptr"].tolist()
    uk, ucq, uwq, uUq = P["use_k"].tolist(), cq.tolist(), wq.tolist(), Uq.tolist()
    sel = [None] * nu
    ys = []
    for u in range(nu):
        U = int(uUq[u])
        if U <= 0:
            continue
        s = m.NewBoolVar("s%d" % u)
        sel[u] = s
        xs = [cvar[uk[i]] for i in range(up[u], up[u + 1])]
        m.AddBoolOr([s.Not()] + xs)
        y = m.NewIntVar(0, U, "y%d" % u)
        ys.append(y)
        m.Add(y <= U * s)
        lin = sum(int(uwq[i]) * cvar[uk[i]] for i in range(up[u], up[u + 1]) if uwq[i]) + int(ucq[u])
        if ucq[u] >= 0:
            if ucq[u] < U:
                m.Add(y <= lin)
        else:
            m.Add(y <= lin).OnlyEnforceIf(s)
    for a_, b_ in _group_use_ranges(P["use_g"]):
        ss = [sel[u] for u in range(a_, b_) if sel[u] is not None]
        if len(ss) > 1:
            m.AddAtMostOne(ss)
    cost_k = [int(round(c * 1000)) for c in P["cost"]]
    for i in forced or ():
        # a chunk the smaller budget built stays built (NESTED)
        m.Add(build[i] == 1)
    live = [i for i in range(nc) if build[i] is not None]
    m.Add(sum(cost_k[i] * build[i] for i in live) <= int(round(budget * 1000)))
    for a_, b_ in P.get("conflicts", np.zeros((0, 2), dtype=np.int64)).tolist():
        if build[a_] is not None and build[b_] is not None:
            m.AddBoolOr([build[a_].Not(), build[b_].Not()])
    if CALM_CAP_MI is not None:
        calm_k = [int(round(c * 1000)) for c in P["calm"]]
        m.Add(sum(calm_k[i] * build[i] for i in live if calm_k[i]) <= int(round(CALM_CAP_MI * 1000)))
    m.Maximize(sum(ys))
    if hint is not None:
        hb = np.zeros(nc, dtype=bool)
        hb[np.asarray(hint, dtype=np.int64)] = True
        bu = best_uses(P, hb, (cq, wq, Uq))
        qv = use_values(P, hb, (cq, wq, Uq))
        hs = np.zeros(nu, dtype=bool)
        hs[bu[bu >= 0]] = True
        cb = cover_built(cov_ptr, cov_c, hb)
        for i in live:
            m.AddHint(build[i], bool(hb[i]))
        for k, v in cvar.items():
            if k >= nc:
                m.AddHint(v, bool(cb[k]))
        yi = 0
        for u in range(nu):
            if sel[u] is None:
                continue
            m.AddHint(sel[u], bool(hs[u]))
            m.AddHint(ys[yi], int(qv[u]) if hs[u] else 0)
            yi += 1
    sv = cp_model.CpSolver()
    sv.parameters.num_search_workers = THREADS
    sv.parameters.relative_gap_limit = MIP_REL_GAP
    if CPSAT_LIN is not None:
        sv.parameters.linearization_level = CPSAT_LIN
    sv.parameters.max_time_in_seconds = TIME_LIMIT_S
    sv.parameters.log_search_progress = os.environ.get("SEGMENTS_CPSAT_LOG") == "1"
    # no presolve: on a two-school program presolve alone took 57 s of a 60 s limit, and 37 s with probing, symmetry and
    # repeated passes off (2026-10-20)
    sv.parameters.cp_model_presolve = os.environ.get("SEGMENTS_CPSAT_PRESOLVE") == "1"
    import threading
    hit, done = [], threading.Event()

    def guard():
        while not done.wait(5):
            f = _footprint_mb()
            if f is not None and f > CPSAT_MEM_MB:
                hit.append(f)
                sv.StopSearch()
                return
    threading.Thread(target=guard, daemon=True).start()
    st = sv.Solve(m)
    done.set()
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    b = np.array([bool(sv.Value(v)) if v is not None else False for v in build])
    obj, bound = sv.ObjectiveValue(), sv.BestObjectiveBound()
    gap = float((bound - obj) / max(abs(obj), 1e-9))
    stop = "optimal" if st == cp_model.OPTIMAL else ("memory" if hit else "time")
    return b, gap, sv.StatusName(st), int(sv.NumBranches()), stop, bound / SCALE


def evaluate(sim, ct, R, pkey, pw, pn, cov_ptr, cov_c, nc, build_set):
    """The promise for a build set: per pair its most valuable route at the on-network share the whole build set gives
    it (route_values), summed; the students and drivers of the pairs it serves; the chunks on a served pair's route
    (built chunks of the route's built covers); and per built chunk how many served pairs ride on it alone (the only
    built chunk on their route). The program's objective is a lower bound on this, exact where a route has one or all
    (or all but one) of its covers built."""
    built = np.zeros(nc, dtype=bool)
    built[np.asarray(build_set, dtype=np.int64)] = True
    cb = cover_built(cov_ptr, cov_c, built)
    v = route_values(sim, ct, R, pkey, cb)
    best, arg = pair_best(R, v, len(pw))
    served = arg >= 0
    alone = {int(c): 0 for c in np.flatnonzero(built)}
    rs = arg[served]
    ln = np.diff(R["ptr"])[rs]
    pos = np.repeat(R["ptr"][:-1][rs], ln) + (np.arange(int(ln.sum())) - np.repeat(np.cumsum(ln) - ln, ln))
    own = np.repeat(np.arange(len(rs)), ln)
    k = R["k"][pos].astype(np.int64)
    hk = cb[k]
    own, k = own[hk], k[hk]
    clen = np.diff(cov_ptr)[k]
    cc = cov_c[np.repeat(cov_ptr[:-1][k], clen) + (np.arange(int(clen.sum())) - np.repeat(np.cumsum(clen) - clen, clen))]
    oc = np.repeat(own, clen)
    bc = built[cc]
    pr = np.unique(oc[bc].astype(np.int64) * nc + cc[bc])
    on_route = set(np.unique(pr % nc).tolist())
    npc = np.bincount(pr // nc, minlength=len(rs))
    one = npc[pr // nc] == 1
    for c, n_ in zip(*np.unique(pr[one] % nc, return_counts=True)):
        alone[int(c)] = int(n_)
    return {"best": best, "arg": arg, "served": served, "carTrips": float(best.sum()), "students": float(pn[served].sum()),
            "drivers": float(pw[served].sum()), "onRoute": on_route, "alone": alone}


# -- the real route search ----------------------------------------------------------------------------------------

def real_search(sim, S, safe, j, k0):
    """The scorer's route choice (school-sim.py's _bike, with segments' capped searches and k0 reused) for school j on
    `safe`: per block the route metres and its metres on the network (the sim's on-network share is their ratio), the
    tree each block's route came from, and whether the route crosses a busy street unsignalled. Also each tree's
    (pred, lookup, pick), so a route can be traced."""
    W = sim._W
    F, L, steps = W["flat"], W["L"], W["steps"]
    bd = S["bdoor"][j]
    un_e = ~safe
    s_len = [d[1] + d[2] for d in bd]
    s_un = [bool(un_e[d[3]]) for d in bd]
    s_run = [sl if u else 0.0 for sl, u in zip(s_len, s_un)]
    s_max = [sl if u else d[1] for sl, u, d in zip(s_len, s_un, bd)]
    ev_ = np.where(un_e, L, 0.0)[:, None]
    sv_ = [[d[1] + (d[2] if u else 0.0)] for d, u in zip(bd, s_un)]
    cand, trees = [], []
    for k in sim.GAP_K:
        if k == 0 and k0 is not None:
            dist, pred, lk = k0
        else:
            dist, pred, lk, _w = _search(sim, S, safe, bd, k)
        ln, run, mx = sim._tree(dist, pred, lk, s_len, s_run, s_max, safe)
        ue = un_e[F["e"]] | steps[F["e"]]
        w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
        pick = S["pick"](F, dist[:-1], w_end)
        pi = np.maximum(pick, 0)
        nd = F["node"][pi]
        m = np.where(pick >= 0, ln[nd] + F["c"][pi] + F["al"][pi], np.inf)
        Ssum = sim._tree_sums(dist, pred, lk, ev_, sv_)
        off = Ssum[nd, 0] + F["c"][pi] + np.where(ue[pi], F["al"][pi], 0.0)
        g = np.where(pick >= 0, off, np.inf)   # the total gap (sim.GAP_RULE), as sim._route_off sums it
        brk = sim._broken(pred, lk, nd, F["e"][pi])
        g = np.where(brk, g + sim.BREAK_FT * sim.FT, g)
        cand.append((m, g, np.maximum(m - off, 0.0), brk))
        trees.append((pred, lk, pick))
    m0 = cand[0][0]
    best_m, best_g, best_on, best_brk = m0.copy(), cand[0][1].copy(), cand[0][2].copy(), cand[0][3].copy()
    which = np.zeros(len(m0), dtype=np.int64)
    for i, (m, g, on, brk) in enumerate(cand[1:], 1):
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(m) & (m <= sim.DETOUR * m0 + 1e-6) & ((g < best_g - 1e-6) | ((np.abs(g - best_g) <= 1e-6) & (m < best_m)))
        best_m = np.where(ok, m, best_m)
        best_g = np.where(ok, g, best_g)
        best_on = np.where(ok, on, best_on)
        best_brk = np.where(ok, brk, best_brk)
        which = np.where(ok, i, which)
    nob = ~np.isfinite(best_m)
    return {"m": np.where(nob, np.inf, best_m), "on": np.where(nob, 0.0, best_on), "which": which, "trees": trees,
            "broken": best_brk | nob}


def on_share(r, walk):
    """The sim's on-network share (on_share): the route's metres on the network over its length, 0 with no route."""
    bm = np.where(np.isfinite(r["m"]), r["m"], walk)
    return np.clip(r["on"] / np.maximum(bm, 1.0), 0.0, 1.0)


def trace_routes(sim, S, j, r, blocks):
    """The listed blocks' chosen routes on a real search r, aggregated as the menu's are: (blocks kept, metres, (feet off
    the network on the baseline, gap (the same total), (route, cover, feet) entries))."""
    W = sim._W
    F = W["flat"]
    keep_b, tot_l, off_l, gap_l, ent_l, n_r = [], [], [], [], [], 0
    for k in range(len(r["trees"])):
        b = blocks[r["which"][blocks] == k]
        if not len(b):
            continue
        pred, lk, pick = r["trees"][k]
        pi = pick[b]
        pe = _parent_edges(sim, pred, lk)
        rr, ss, ee, seed = _chase(pred, pe, F["node"][pi])
        rids = np.arange(len(b))
        parts = [_door_seed_parts(S, j, seed, rids), _edge_parts(sim, S, rr, ss, ee, 0), _join_parts(sim, S, pi, rids, 10 ** 7)]
        total, runs = _assemble(sim, S, len(b), parts)
        off, gap, (er, ek, eft) = _aggregate(len(b), runs)
        keep_b.append(b)
        tot_l.append(total)
        off_l.append(off)
        gap_l.append(gap)
        ent_l.append((er.astype(np.int64) + n_r, ek, eft))
        n_r += len(b)
    if not keep_b:
        z = np.zeros(0, dtype=np.int64)
        return z, np.zeros(0), (np.zeros(0), np.zeros(0), (z, z.astype(np.int32), np.zeros(0, np.float32)))
    return (np.concatenate(keep_b), np.concatenate(tot_l).astype(np.float64),
            (np.concatenate(off_l), np.concatenate(gap_l), tuple(np.concatenate([x[i] for x in ent_l]) for i in range(3))))


def _check_job(j):
    """One school, every round network at once (the six budgets' chosen chunks): on each, the scorer's route for every
    block with students, the year-10 family-car trips removed over the baseline (central case), the students and
    drivers whose route's on-network share rises, each block's benefit, and the traced routes of the blocks whose real
    benefit and the program's promise for that network differ by more than CHECK_TOL of the larger, whatever the route
    crosses (a crossing route is the scorer's pick when every candidate crosses)."""
    sim, S = _S["sim"], _S
    ct = S["ct"]
    idx = S["cells_of"][j]
    if not len(idx):
        return j, None
    walk = S["walk"][:, j]
    k0 = S["bike_k0"](S["doors"][j])
    cb = ct["b"][idx]
    blocks, inv = np.unique(cb, return_inverse=True)
    r0 = real_search(sim, S, S["base"], j, k0)
    on0 = on_share(r0, walk)
    out = []
    mb = S["mbest"][j]
    for i, add in enumerate(S["nets"]):
        sf = S["base"].copy()
        sf[add] = True
        r = real_search(sim, S, sf, j, k0)
        on = on_share(r, walk)
        gain = np.maximum(on[cb] - on0[cb], 0.0)
        bene = cell_benefit(ct, idx, gain)
        real = np.bincount(inv, weights=bene, minlength=len(blocks))
        up = gain > 1e-9
        tot = (float(bene.sum()), float(ct["n"][idx][up].sum()), float((ct["n"][idx] * ct["car"][idx])[up].sum()))
        want = (np.abs(real - mb[i]) > CHECK_TOL * np.maximum(real, mb[i]) + 1e-6) & np.isfinite(r["m"][blocks]) & S["trace"]
        tb = trace_routes(sim, S, j, r, blocks[want]) if want.any() else None
        out.append({"tot": tot, "real": real.astype(np.float32), "traced": tb})
        del r
    return j, {"blocks": blocks, "nets": out}


# -- isolated pieces ----------------------------------------------------------------------------------------------

def isolated(sim, S, ch, chosen, forced, on_route):
    """The chosen chunks in connected pieces that touch neither the baseline network nor each other's piece that does,
    each piece's miles, and why it is there: inherited from the smaller budget (all its chunks forced by nesting), on a
    chosen use (a route the gap rule passes, the short calmed street that serves a school on its own), or neither (a
    pick no route needs, which only an early-stopped solve leaves; the output drops those already)."""
    W = sim._W
    if not chosen:
        return {"pieces": 0, "mi": 0.0, "byCause": {}}
    nodes = {c: set(np.r_[W["eu"][ch[c]["edges"]], W["ev"][ch[c]["edges"]]].tolist()) for c in chosen}
    base_nodes = set(np.r_[W["eu"][S["base"]], W["ev"][S["base"]]].tolist())
    parent = {c: c for c in chosen}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c
    owner = {}
    for c in sorted(chosen):
        for v in nodes[c]:
            if v in owner:
                a_, b_ = find(c), find(owner[v])
                if a_ != b_:
                    parent[max(a_, b_)] = min(a_, b_)
            else:
                owner[v] = c
    comps = {}
    for c in chosen:
        comps.setdefault(find(c), []).append(c)
    by = {"nested": [0, 0.0], "onRoute": [0, 0.0], "neither": [0, 0.0]}
    n_iso = 0
    for cs in comps.values():
        if any(nodes[c] & base_nodes for c in cs):
            continue
        n_iso += 1
        mi = sum(ch[c]["mi"] for c in cs)
        cause = "nested" if all(c in forced for c in cs) else ("onRoute" if any(c in on_route for c in cs) else "neither")
        by[cause][0] += 1
        by[cause][1] += mi
    return {"pieces": n_iso, "of": len(comps), "mi": round(sum(v[1] for v in by.values()), 2),
            "byCause": {k: {"pieces": v[0], "mi": round(v[1], 2)} for k, v in by.items()}}


# -- main ---------------------------------------------------------------------------------------------------------

def covers(ch, n_edges):
    """Each edge's cover: the chunk holding it, or for an edge two or more chunks hold, len(ch) + the index of that
    chunk set (sets sorted, so ids are stable). A route piece on a cover is on the network once any chunk of the cover is
    built. Returns the per-edge cover (-1 on no chunk), every cover's chunks as (ptr, chunks) over ids 0..n_cov-1 (a
    single chunk below len(ch)), and the number of shared sets."""
    nc = len(ch)
    owner = np.full(n_edges, -1, dtype=np.int64)
    if not nc:
        return owner, np.zeros(1, np.int64), np.zeros(0, np.int32), 0
    e = np.concatenate([np.asarray(c["edges"], dtype=np.int64) for c in ch])
    c_ = np.concatenate([np.full(len(c["edges"]), i, dtype=np.int64) for i, c in enumerate(ch)])
    u = np.unique(e * nc + c_)
    e, c_ = u // nc, u % nc
    start = np.flatnonzero(np.r_[True, e[1:] != e[:-1]])
    cnt = np.diff(np.r_[start, len(e)])
    one = cnt == 1
    owner[e[start[one]]] = c_[start[one]]
    multi = {}
    for s, n in zip(start[~one].tolist(), cnt[~one].tolist()):
        multi.setdefault(tuple(c_[s:s + n].tolist()), []).append(int(e[s]))
    sets = sorted(multi)
    for k, t in enumerate(sets):
        owner[np.array(multi[t], dtype=np.int64)] = nc + k
    lens = np.r_[np.ones(nc, dtype=np.int64), np.array([len(t) for t in sets], dtype=np.int64)]
    cov_c = np.r_[np.arange(nc), np.array([c for t in sets for c in t], dtype=np.int64)].astype(np.int32)
    return owner, np.r_[0, np.cumsum(lens)].astype(np.int64), cov_c, len(sets)


def setup(sim, stt, seg, C, T, mins, sch, blks):
    """school-segments.py's rank() preamble: network, chunks, baseline, weights, doors, the fast search. Fills seg._S too,
    so its _milestone_job runs the check."""
    t0 = time.time()
    sim.network(blks, {})
    W = sim._W
    sim._tree = seg.tree_fast(sim)
    ch, planned_edges, counts = candidates(sim, stt, seg)
    base = W["safe"].copy()
    if len(planned_edges):
        base[planned_edges] = True
    print("  segments: %d chunks, %.1f centerline miles, $%.0fM in all; baseline adds %d planned edges (%.0fs)" % (
        len(ch), sum(c["mi"] for c in ch), sum(c["costM"] for c in ch), int(len(planned_edges)), time.time() - t0))
    ns, nb = len(sch), len(blks)
    dense_n = np.zeros((nb, ns))
    np.add.at(dense_n, (C["b"], C["school"]), C["n"])
    dense_w = np.zeros((nb, ns))
    np.add.at(dense_w, (C["b"], C["school"]), C["n"] * C["pr"][:, sim.CAR])
    car, walk = mins["car"], T["walk"]
    within, gap_ft = sim.CHANGES["bike_switch"]["within_min"], sim.CHANGES["bike_switch"]["gap_total_ft"]
    # every pair with students: the objective is the rise in each route's on-network share, which has no pass line, so
    # a pair already passing today or slower than the old time test still gains when its route moves onto new bikeway.
    # Leaving them out made the program's promise 13% to 23% below the checked count.
    near = dense_n > 0
    doors, bdoor = [], []
    for s in sch:
        d = W["net"].ends(s[2], s[3])
        d = [q for q in d if W["walkable"][q[3]]] or d
        doors.append(d)
        bdoor.append([q for q in d if not W["steps"][q[3]]] or d)
    bike, bike_k0 = bike_fast(sim, seg)
    cap_m = sim.bike_miles(seg.SEARCH_MAX_MIN) * sim.MI
    all_cand = base.copy()
    for c in ch:
        all_cand[c["edges"]] = True
    owner, cov_ptr, cov_c, n_multi = covers(ch, len(W["L"]))
    cov_of = [[] for _ in ch]   # per chunk, the cover ids holding it
    for k in range(len(cov_ptr) - 1):
        for c in cov_c[cov_ptr[k]:cov_ptr[k + 1]].tolist():
            cov_of[c].append(k)
    cov_of = [np.array(x, dtype=np.int32) for x in cov_of]
    if n_multi:
        print("  segments: %d edges lie in two or more chunks, in %d chunk sets; a piece there is on the network once any "
              "of its chunks is built" % (int((owner >= len(ch)).sum()), n_multi))
    X, Y = np.asarray(W["x"], dtype=float), np.asarray(W["y"], dtype=float)
    cp, own = [], []
    for i, c in enumerate(ch):
        for e in c["edges"]:
            a = np.array([X[W["eu"][e]], Y[W["eu"][e]]])
            b = np.array([X[W["ev"][e]], Y[W["ev"][e]]])
            for t in (0.0, 0.5, 1.0):
                cp.append(a + t * (b - a))
                own.append(i)
    S = dict(sim=sim, doors=doors, bdoor=bdoor, base=base, near=near, walk=walk, car=car, n=dense_n, w=dense_w,
             chunk_edges=[c["edges"] for c in ch], bike=bike, bike_k0=bike_k0, cap_m=cap_m, all_cand=all_cand, owner=owner,
             cov_ptr=cov_ptr, cov_c=cov_c, cov_of=cov_of,
             chunk_pts=(np.array(cp), np.array(own, dtype=np.int64)), full_k=sim.GAP_K, within=within, gap_ft=gap_ft,
             dij=seg.dijkstra_limited(sim), pick=seg.block_pick_fast(sim), school_ids=[s[0] for s in sch])
    _S.update(S)
    seg._S.update(sim=sim, doors=doors, base=base, near=[near[:, j] for j in range(ns)], walk=walk, car=car, n=dense_n, w=dense_w,
                  chunk_edges=S["chunk_edges"], bike=bike, bike_k0=bike_k0, cap_m=cap_m, all_cand=all_cand,
                  chunk_pts=S["chunk_pts"], full_k=sim.GAP_K)
    print("  segments: %d schools with %d (block, school) pairs in the near-miss band; %.0f students, %.0f of them driven" % (
        int(near.any(axis=0).sum()), int(near.sum()), float(dense_n[near].sum()), float(dense_w[near].sum())))
    return ch, counts


def unserved_routes(n_routes, tag, per_budget, rule=None):
    """The routes the loop drops as unserved. per_budget holds, for each budget's checked network, (arg, short): each
    served pair's promised route and whether the real search gave that pair less than its promise by more than
    CHECK_TOL. Rule "budget" (UNSERVED_RULE's default) drops a route short at any budget. Rule "every" drops a menu
    route (tag 0) short at any budget, but a traced route (tag > 0, the real route of some network) only when it is
    short at every budget where it is a promised route, so a route real at one budget and short at another stays."""
    rule = rule or UNSERVED_RULE
    short = np.zeros(n_routes, dtype=bool)
    ok = np.zeros(n_routes, dtype=bool)
    for arg, sh in per_budget:
        short[arg[sh]] = True
        ok[arg[~sh]] = True
    return short if rule == "budget" else short & ((tag == 0) | ~ok)


def check_output(out, cost_by_id, budgets=None, published=False):
    """The checks segments.json must pass before it is written; a failure stops the step and the last file stays.
    Every budget in budgets (BUDGETS_M) is there; every chosen chunk id exists; each budget's chosen chunks cost at most
    the budget; each budget carries its checked carTripsRemoved; and each budget holds every chunk of the one below,
    always for the published file (published) and otherwise when the run is nested. Returns the failures, empty when
    all pass."""
    bad, prev = [], None
    have = {b["budgetM"] for b in out["budgets"]}
    for m in sorted(set(budgets or ()) - have):
        bad.append("$%gM: missing" % m)
    for b in sorted(out["budgets"], key=lambda x: x["budgetM"]):
        ids = b["chunks"]
        missing = [c for c in ids if c not in cost_by_id]
        if missing:
            bad.append("$%gM: %d chosen chunk ids not in the chunk list (%s)" % (b["budgetM"], len(missing), missing[:3]))
        cost = sum(cost_by_id.get(c, 0.0) for c in ids)
        if cost > b["budgetM"] + 1e-6:
            bad.append("$%gM: chosen chunks cost $%.3fM, over the budget" % (b["budgetM"], cost))
        if b.get("carTripsRemoved") is None:
            bad.append("$%gM: no checked carTripsRemoved" % b["budgetM"])
        if (published or out.get("nested")) and prev is not None and not set(prev["chunks"]) <= set(ids):
            bad.append("$%gM: drops %d chunks of $%gM, not nested" % (b["budgetM"], len(set(prev["chunks"]) - set(ids)), prev["budgetM"]))
        prev = b
    return bad


def loop_version():
    """The round cache's code version: a hash of the source of the functions a checked round's table depends on (the
    loop in run, the unserved rule, the promise and the check), so editing any of them retires the cached rounds."""
    import inspect
    return source_hash([inspect.getsource(f) for f in (run, unserved_routes, evaluate, _check_job, trace_routes)])


def source_hash(sources):
    """A 16-character hash of the given source texts, in order: loop_version's hash."""
    return hashlib.sha256("".join(sources).encode()).hexdigest()[:16]


def _plain(x):
    """numpy scalars and arrays as plain Python, so the output writes as JSON."""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x



def check_real(sim, S, sch, n_schools=3):
    """real_search against sim._bike(extra=True) on n_schools schools, on the baseline and with every candidate built:
    the same route metres and on-network metres for every block with students whose shortest route is at most cap_m."""
    for j in range(min(n_schools, len(sch))):
        k0 = S["bike_k0"](S["doors"][j])
        for safe in (S["base"], S["all_cand"]):
            a = sim._bike(safe, S["doors"][j], S["walk"][:, j], extra=True)
            r = real_search(sim, S, safe, j, k0)
            sel = (S["n"][:, j] > 0) & (r["m"] <= S["cap_m"]) & np.isfinite(r["m"])
            assert np.allclose(a[0][sel], r["m"][sel], rtol=1e-9, atol=1e-6), "real_search's metres differ from sim._bike at school %d" % j
            assert np.allclose(a[3][sel], r["on"][sel], rtol=1e-9, atol=1e-3), "real_search's on-network metres differ from sim._bike at school %d" % j


def _mem(tag):
    """This process's footprint (macOS footprint), logged at each stage so a run near the watchdog's cap shows where."""
    import subprocess
    try:
        o = subprocess.run(["footprint", "-p", str(os.getpid())], capture_output=True, text=True, timeout=30).stdout
        line = next((x for x in o.splitlines() if "Footprint:" in x), "")
        print("  memory %s: %s" % (tag, line.split("Footprint:")[-1].strip()), flush=True)
    except Exception:
        pass


def _table_hash(T, extra):
    h = hashlib.sha256(json.dumps(extra).encode())
    for k in ROUTE_KEYS:
        h.update(np.ascontiguousarray(T[k]).tobytes())
    return h.hexdigest()[:16]


def run(sim, stt, seg, C, T, mins, sch, blks, workers):
    global TIME_LIMIT_S
    if OUT_PATH is None and set(BUDGETS_M) != set(ALL_BUDGETS_M):
        raise SystemExit("segments: SEGMENTS_BUDGETS=%s narrows the budgets, so set SEGMENTS_OUT; the published "
                         "segments.json carries every budget in %s" % (",".join(map(str, BUDGETS_M)), ALL_BUDGETS_M))
    t_all = time.time()
    timings = {}
    _mem("at start")
    ch, counts = setup(sim, stt, seg, C, T, mins, sch, blks)
    S = _S
    ns = len(sch)
    timings["setup"] = round(time.time() - t_all, 1)
    lam, _info = sim.case_lambdas(C)
    lam_c = float(lam[CASE])
    ct = cell_table(sim, C, lam_c, ns)
    print("  benefit: year-10 family-car trips removed, %s case (lambda %.5f), %d cells" % (CASE, lam_c, len(ct["n"])), flush=True)
    # The sim's per-variant columns (about 170 over 3M cells) and trip tables are not read past here; --segments returns
    # after this run, so they are dropped to keep the process under the 11 GB watchdog.
    import gc
    for k in [k for k in C if k not in ("b", "school", "n", "pr")]:
        del C[k]
    for k in [k for k in T if k not in ("walk", "gap_today")]:
        del T[k]
    for k in [k for k in mins if k not in ("car", "bike_today")]:
        del mins[k]
    gc.collect()
    _mem("after setup")
    t = time.time()
    t_old, t_new = seg.check_fast(sim, sch, S["doors"], S["walk"], S["n"] > 0, S["cap_m"])
    check_real(sim, S, sch)
    print("  segments: fast _bike and real_search equal sim._bike on 3 schools (%.1fs vs %.1fs)" % (t_old, t_new))
    mpath = os.path.join(sim.CACHE, "segments-menu-%s.npz" % menu_hash(sim, seg, ch, S))
    corridor = seg.SEGMENTS_CORRIDOR_FT
    conf = offplan_conflicts(seg, stt, ch)
    counts["offplanConflicts"] = int(len(conf))
    print("  program: %d pairs of off-plan chunks run parallel one block apart; at most one of each pair is built" % len(conf))
    nc = len(ch)
    cost = np.array([c["costM"] for c in ch])
    calm = np.array([c.get("calmMi", 0.0) for c in ch])
    cov_ptr, cov_c = S["cov_ptr"], S["cov_c"].astype(np.int64)
    cost_cov = np.minimum.reduceat(cost[cov_c], cov_ptr[:-1])
    ct_sha = hashlib.sha256(b"".join(np.ascontiguousarray(ct[k]).tobytes() for k in ("key", "n", "p", "car", "D", "on0"))).hexdigest()[:12]
    tkey = hashlib.sha256(json.dumps([os.path.basename(mpath), corridor, ROUTES_EFF, ROUTES_VAL, ct_sha, "routes-1",
                                      [c["costM"] for c in ch]]).encode()).hexdigest()[:16]
    tpath = os.path.join(sim.CACHE, "segments-routes-%s.npz" % tkey)
    t = time.time()
    if os.path.exists(tpath):
        # The pruned route table holds everything the loop needs from the menu, so the menu isn't read at all.
        z = np.load(tpath)
        Tab = {k: z[k] for k in ROUTE_KEYS}
        sstats = json.loads(str(z["stats"]))
        meta = json.loads(str(z["meta"]))
        pair_b, pair_j, pair_m0 = z["pair_b"].astype(np.int64), z["pair_j"].astype(np.int64), z["pair_m0"].astype(np.float64)
        timings["menu"], timings["menuCold"] = 0.0, meta["menuCold"]
        del z
        print("  routes: read from the cache (%s), the menu not read" % tkey)
    else:
        if os.path.exists(mpath):
            menu = dict(np.load(mpath))
            print("  menu: read from %s (%d routes)" % (os.path.relpath(mpath, sim.ROOT), len(menu["r_m"])))
            timings["menu"] = round(time.time() - t, 1)
            timings["menuCold"] = round(float(menu["seconds"][0]), 1)
        else:
            menu = build_menu(sim, seg, ch, workers, S, mpath)
            timings["menu"] = timings["menuCold"] = round(time.time() - t, 1)
        if ONLY_B == "menu":
            print("  menu: saved %s; stopping (SEGMENTS_ONLY=menu)" % mpath, flush=True)
            raise SystemExit(0)
        # the scorer's gap carries BREAK_FT on top for a route over an unsignalled busy crossing and the menu's doesn't
        # (the menu marks those routes apart), so it comes off before the comparison
        g0 = T["gap_today"]
        gaps_same, gaps_tot = check_menu_gaps(sim, S, menu, dict(T, gap_today=np.where(g0 >= sim.BREAK_FT, g0 - sim.BREAK_FT, g0)))
        meta = {"pairs": int(len(menu["pair_b"])), "routes": int(len(menu["r_m"])), "todayGapsEqual": [int(gaps_same), int(gaps_tot)],
                "menuCold": timings["menuCold"], "pairsShortestCrossing": int(menu["pair_brk0"].sum())}
        pair_b = menu["pair_b"].astype(np.int64)
        pair_j = menu["pair_j"].astype(np.int64)
        pair_m0 = menu["pair_m0"].astype(np.float64)
        Tab, n_out = menu_routes(sim, menu, corridor)
        del menu
        gc.collect()
        Tab, sstats = prune_menu(sim, ct, Tab, pair_b * ns + pair_j, cost_cov)
        sstats.update(routes=meta["routes"], routesOut=n_out)
        os.makedirs(sim.CACHE, exist_ok=True)
        np.savez(tpath, **Tab, stats=np.array(json.dumps(sstats)), meta=np.array(json.dumps(meta)), pair_b=pair_b, pair_j=pair_j,
                 pair_m0=pair_m0)
    print("  menu: the today routes' total gap equals the scorer's for %d of %d pairs" % tuple(meta["todayGapsEqual"]))
    gaps_same, gaps_tot = meta["todayGapsEqual"]
    if gaps_same < MENU_GAP_FLOOR * gaps_tot:
        raise SystemExit("menu check failed: today's gaps equal the scorer's for %d of %d pairs, under the %.0f%% floor"
                         % (gaps_same, gaps_tot, 100 * MENU_GAP_FLOOR))
    n_menu_pairs, n_menu_routes = meta["pairs"], meta["routes"]
    gc.collect()
    timings["routes"] = round(time.time() - t, 1)
    _mem("after routes")
    print("  routes: %d kept over %d pairs, from %d menu routes (%d out of the detour or corridor, %d worth nothing) (%.0fs)" % (
        len(Tab["pair"]), len(np.unique(Tab["pair"])), sstats["routes"], sstats["routesOut"], sstats["worthNothing"], timings["routes"]), flush=True)
    # the check's cells, by school, and each school's blocks with students
    order_j = np.argsort(ct["j"], kind="stable")
    bounds = np.searchsorted(ct["j"][order_j], np.arange(ns + 1))
    S["ct"] = ct
    S["cells_of"] = [order_j[bounds[j]:bounds[j + 1]] for j in range(ns)]
    blocks_of = [np.unique(ct["b"][S["cells_of"][j]]) for j in range(ns)]
    pkey_sorted = None

    def pair_ids(keys):
        """Each pair key's id, -1 where the pair is in no route yet."""
        nonlocal pkey_sorted
        if pkey_sorted is None:
            ks = pair_b * ns + pair_j
            o = np.argsort(ks, kind="stable")
            pkey_sorted = (ks[o], o)
        ks, o = pkey_sorted
        i = np.searchsorted(ks, keys)
        i = np.minimum(i, len(ks) - 1)
        return np.where((len(ks) > 0) & (ks[i] == keys), o[i], -1)
    pw_all = lambda: S["w"][pair_b, pair_j]
    pn_all = lambda: S["n"][pair_b, pair_j]
    rounds_log = []
    limits_used = {}
    seed_hash = hashlib.sha256(open(SEED_PATH, "rb").read()).hexdigest()[:16] if SEED_PATH else None
    loop_ver = loop_version()
    hint_prev = {}
    final = {}
    seed, seed_cov, seed_used = None, None, {}
    replay = json.load(open(REPLAY)) if REPLAY else None
    if SEED_PATH and replay is None:
        seed, seed_cov = seed_map(ch, SEED_PATH)
        print("  seed: %s mapped onto today's chunks: %s" % (SEED_PATH, "; ".join(
            "$%dM %d of %d old CNNs (%.1f%%) in %d chunks, $%.1fM, %.1f calmed mi" % (
                b, v["cnnsCovered"], v["oldCnns"], v["coveredPct"], v["chunks"], v["costM"], v["calmMi"]) for b, v in sorted(seed_cov.items()))),
              flush=True)
    t_solve = t_check = 0.0
    P = None
    start = 1
    if RESUME:
        # a checked round's saved table, read back to go on from the next round under changed loop rules
        start, rp0 = int(RESUME.split(":", 1)[0]), RESUME.split(":", 1)[1]
        z = np.load(rp0, allow_pickle=False)
        st = json.loads(str(z["state"]))
        rounds_log.extend(st.get("logs") or [st["log"]])
        rounds_log[-1] = dict(rounds_log[-1], resumedFrom=os.path.basename(rp0))
        Tab = {k: z[k] for k in ROUTE_KEYS}
        pair_b, pair_j, pair_m0 = z["pair_b"], z["pair_j"], z["pair_m0"]
        pkey_sorted = None
        hint_prev = {int(k): v for k, v in st["hint"].items()}
        del z
        print("  resume: round %d from %s (%d routes)" % (start, os.path.basename(rp0), len(Tab["pair"])), flush=True)
    for rnd in range(start, (MAX_ROUNDS if DO_CHECK else 1) + 1):
        t = time.time()
        TIME_LIMIT_S = TIME_LIMITS[min(rnd, len(TIME_LIMITS)) - 1]
        limits_used[rnd] = TIME_LIMIT_S
        os.environ["SEGMENTS_TIME_LIMIT"] = "%g" % TIME_LIMIT_S   # the solve's own process reads it
        pkey = pair_b * ns + pair_j
        pw, pn = pw_all(), pn_all()
        phash = _table_hash(Tab, [tkey, BIN, PROG_MIN_SHARE, conf.tolist(), calm.tolist(), "prog-1"])
        ppath = os.path.join(sim.CACHE, "segments-prog-%s.npz" % phash)
        if replay is None:
            P, aux = build_program(sim, ct, Tab, pkey, pw, pn, nc, cost, cov_ptr, cov_c)
            P["conflicts"], P["calm"] = conf, calm
            if not os.path.exists(ppath):
                save_program(P, ppath)
        print("  round %d program: %s (%.0fs)" % (rnd, P["stats"] if P is not None else "-", time.time() - t), flush=True)
        _mem("round %d before solves" % rnd)
        os.environ["SEGMENTS_THREADS"] = str(min(THREADS, SOLVE_WORKERS))
        if ONLY_B == "program" or (ONLY_B == "program2" and rnd == 2):
            print("  program: saved %s; stopping before the solves (SEGMENTS_ONLY=program)" % ppath, flush=True)
            raise SystemExit(0)
        skey = hashlib.sha256(json.dumps([phash, MIP_REL_GAP, SOLVER, os.environ["SEGMENTS_THREADS"], TIME_LIMIT_S, CALM_CAP_MI, CPSAT_LIN, CPSAT_MEM_MB,
                                      "greedy-start" if CALM_CAP_MI is None else "greedy-start-capped",
                                      replay.get(str(rnd)) if replay else None]).encode()).hexdigest()[:16]
        t = time.time()
        sols, prev_chosen = {}, None
        for b in sorted(BUDGETS_M):
            forced = sorted(prev_chosen) if NESTED and prev_chosen is not None else None
            if replay is not None:
                # a given build set in place of the solve (SEGMENTS_REPLAY), to value an earlier run's plans
                rb = replay[str(rnd)][str(b)]
                r = {"build": np.array(rb["build"], dtype=np.int64), "gap": None, "message": "replayed", "seconds": 0}
                forced = rb.get("forced")
            else:
                # always a hint: with none, CP-SAT on the full program found no solution in 60 s; the empty plan is feasible
                hint = sorted(set(hint_prev.get(b, [])) | set(forced or []))
                if rnd == 1 and seed is not None and b in seed:
                    # the union of the forced chunks (the budget below's picks, which nesting keeps) and the mapped seed,
                    # trimmed to the budget and the calming cap; a start the solver couldn't return is dropped
                    sh, st = seed_trim(seed[b], b, cost, calm, conf, forced)
                    st["feasible"] = bool(_feasible(P, sh, b, forced))
                    seed_used[b] = st
                    if st["feasible"]:
                        hint = sh
                    print("  seed $%dM: start of %d chunks, $%.2fM, %.1f calmed mi (%d seed chunks did not fit)%s" % (
                        b, st["chunks"], st["costM"], st["calmMi"], st["seedDropped"],
                        "" if st["feasible"] else "; NOT FEASIBLE with the forced chunks, dropped: this budget starts unseeded"), flush=True)
                tag = "r%d-%d" % (rnd, b)
                fpath = hpath = None
                suf = ""
                if forced is not None:
                    fsha = hashlib.sha256(json.dumps(forced).encode()).hexdigest()[:12]
                    fpath = os.path.join(sim.CACHE, "segments-forced-%s-%s.json" % (phash, fsha))
                    json.dump(forced, open(fpath, "w"))
                    suf += "-n" + fsha
                if hint is not None:
                    hsha = hashlib.sha256(json.dumps(hint).encode()).hexdigest()[:12]
                    hpath = os.path.join(sim.CACHE, "segments-hint-%s-%s.json" % (phash, hsha))
                    json.dump(hint, open(hpath, "w"))
                    suf += "-h" + hsha
                r = _solve_isolated(ppath, b, tag, SOLVER, os.path.join(sim.CACHE, "segments-solve-%s-%s-%s%s.json" % (skey, tag, SOLVER, suf)),
                                    hpath, fpath)
                if r is None:
                    # no solution within the time limit: keep the forced chunks (the smaller budget's plan) and say so
                    r = {"build": np.array(forced or [], dtype=np.int64), "gap": None,
                         "message": "%s: no solution in %gs, the smaller budget's plan kept" % (SOLVER, TIME_LIMIT_S), "seconds": TIME_LIMIT_S}
            ev = evaluate(sim, ct, Tab, pkey, pw, pn, cov_ptr, cov_c, nc, sorted(set(r["build"].tolist()) | set(forced or [])))
            keep_all = set(forced or [])
            chosen = sorted(set(ev["onRoute"]) | keep_all)
            sols[b] = {"r": r, "ev": ev, "chosen": chosen, "forced": keep_all, "raw": [int(c) for c in r["build"]]}
            print("  round %d $%dM: %d chunks built, %d on a chosen route or kept; promise %.1f car trips (%.0f students), program %.1f, %s, %ss, %s" % (
                rnd, b, len(r["build"]), len(chosen), ev["carTrips"], ev["students"], r.get("carTrips", float("nan")),
                gap_words(r["gap"]), r["seconds"], r["message"]), flush=True)
            prev_chosen = chosen
        t_solve += time.time() - t
        final = sols
        if not DO_CHECK:
            break
        bl = sorted(BUDGETS_M)
        # A round already checked and turned into the next round's table is read back, so a restart resumes there with
        # none of the check's traced routes in memory.
        # keyed on the budgets checked and the loop's rules too: a round traced over one budget is not another run's round
        rkey = hashlib.sha256(json.dumps([skey, bl, UNSERVED_FRAC, CHECK_TOL, NESTED, seed_hash, UNSERVED_RULE, loop_ver]).encode()).hexdigest()[:16]
        rpath = os.path.join(sim.CACHE, "segments-round-%s-%s.npz" % (phash, rkey))
        if rnd < MAX_ROUNDS and os.path.exists(rpath):
            z = np.load(rpath, allow_pickle=False)
            st = json.loads(str(z["state"]))
            rounds_log[:] = st.get("logs") or rounds_log + [st["log"]]
            print("  round %d: read from the cache (%s); %s" % (rnd, os.path.basename(rpath), "agreed" if st["log"]["agree"] else "not agreed"), flush=True)
            if st["log"]["agree"]:
                break
            Tab = {k: z[k] for k in ROUTE_KEYS}
            pair_b, pair_j, pair_m0 = z["pair_b"], z["pair_j"], z["pair_m0"]
            pkey_sorted = None
            hint_prev = {int(k): v for k, v in st["hint"].items()}
            del z
            gc.collect()
            continue
        # one real route pass over every budget's network, the promise per pair beside it
        t = time.time()
        S["nets"] = []
        best = []
        for b in bl:
            es = [ch[i]["edges"] for i in sols[b]["chosen"]]
            S["nets"].append(np.unique(np.concatenate(es)) if es else np.zeros(0, dtype=np.int64))
            # the promise on the checked network (the chosen chunks)
            evc = evaluate(sim, ct, Tab, pkey, pw, pn, cov_ptr, cov_c, nc, sols[b]["chosen"])
            sols[b]["evc"] = evc
            best.append(evc["best"])
        S["mbest"] = []
        for j in range(ns):
            pid = pair_ids(blocks_of[j] * ns + j)
            S["mbest"].append(np.array([np.where(pid >= 0, bb[np.maximum(pid, 0)], 0.0) for bb in best]))
        del best
        # the last round's routes would go nowhere, so it traces none
        S["trace"] = rnd < MAX_ROUNDS
        tot = np.zeros((len(bl), 3))
        real_pid = np.zeros((len(bl), len(pair_b)))
        new_parts = []
        n_new_routes = new_pairs = 0
        # in school order, so new pair ids and the traced routes' order are the same run to run
        for j, res in sorted(pmap(workers, _check_job, range(ns)), key=lambda x: x[0]):
            if res is None:
                continue
            pid = pair_ids(res["blocks"] * ns + j)
            for i, o in enumerate(res["nets"]):
                tot[i] += o["tot"]
                real_pid[i, pid[pid >= 0]] = o["real"][pid >= 0]
            tr = [(i, o["traced"]) for i, o in enumerate(res["nets"]) if o["traced"] is not None and len(o["traced"][0])]
            del res
            if not tr:
                continue
            keys = np.concatenate([x[0] for _i, x in tr]) * ns + j
            miss = pair_ids(keys) < 0
            if miss.any():
                nk = np.unique(keys[miss])
                pair_b = np.r_[pair_b, nk // ns]
                pair_j = np.r_[pair_j, nk % ns]
                pair_m0 = np.r_[pair_m0, np.full(len(nk), np.inf)]
                new_pairs += len(nk)
                pkey_sorted = None
                real_pid = np.c_[real_pid, np.zeros((len(bl), len(nk)))]
            rid = pair_ids(keys)
            off_l, m_l, cnt_l, k_l, f_l = [], [], [], [], []
            for _i, (b_, tot_m, (off, _gap, (er, ek, eft))) in tr:
                m_l.append(tot_m)
                off_l.append(off)
                cnt_l.append(np.bincount(er.astype(np.int64), minlength=len(b_)))
                k_l.append(ek.astype(np.int32))
                f_l.append(eft.astype(np.float32))
            cnt = np.concatenate(cnt_l)
            new_parts.append({"pair": rid.astype(np.int64), "m": np.concatenate(m_l).astype(np.float64), "off": np.concatenate(off_l).astype(np.float64),
                              "ptr": np.r_[0, np.cumsum(cnt)].astype(np.int64), "k": np.concatenate(k_l), "ft": np.concatenate(f_l),
                              "tag": np.full(len(rid), rnd, np.int16)})
            n_new_routes += len(rid)
            del tr
        S["mbest"] = None
        t_check += time.time() - t
        # promise against check, budget by budget
        rows, agree_all = [], True
        per_budget = []
        for i, b in enumerate(bl):
            evc, r = sols[b]["evc"], sols[b]["r"]
            prom, chk = evc["carTrips"], tot[i][0]
            rel = abs(chk - prom) / max(prom, 1e-9)
            ok = rel <= CHECK_TOL
            agree_all &= ok
            # the promised routes the real search didn't take: a pair whose real benefit is under UNSERVED_FRAC of its
            # promised route's value loses that route (its real route was traced above, so the pair keeps one for
            # this network)
            rp = real_pid[i, :len(evc["best"])]
            short = rp < UNSERVED_FRAC * evc["best"]
            bad = evc["served"] & short
            per_budget.append((evc["arg"][evc["served"]], short[evc["served"]]))
            sols[b]["check"] = {"carTrips": chk, "students": tot[i][1], "drivers": tot[i][2]}
            rows.append({"round": rnd, "budgetM": b, "promiseCarTrips": round(prom, 2), "checkedCarTrips": round(chk, 2),
                         "relDiff": round(rel, 4), "tolerance": CHECK_TOL, "agree": bool(ok),
                         "programCarTrips": round(r["carTrips"], 2) if r.get("carTrips") is not None else None,
                         "unservedPairs": int(bad.sum()), "checkedStudents": round(tot[i][1], 1), "checkedDrivers": round(tot[i][2], 1),
                         "promiseUnder": round(float(np.maximum(rp - evc["best"], 0).sum()), 2),
                         "promiseOver": round(float(np.maximum(evc["best"] - rp, 0).sum()), 2)})
            print("  round %d $%dM: promise %.1f car trips, checked %.1f (%.1f%% apart, tolerance %.1f%%; per pair %.1f under, %.1f over)%s; %d promised pairs unserved" % (
                rnd, b, prom, chk, 100 * rel, 100 * CHECK_TOL, rows[-1]["promiseUnder"], rows[-1]["promiseOver"], "" if ok else ", not agreed", int(bad.sum())), flush=True)
        del real_pid
        unserved = (unserved_routes(len(Tab["pair"]), Tab["tag"], per_budget) if S["trace"]
                    else np.zeros(len(Tab["pair"]), dtype=bool))
        del per_budget
        log = {"round": rnd, "budgets": rows, "agree": bool(agree_all), "unservedRoutes": int(unserved.sum()),
               "realRoutesAdded": n_new_routes if not agree_all and rnd < MAX_ROUNDS else 0,
               "pairsAdded": new_pairs if not agree_all and rnd < MAX_ROUNDS else 0}
        rounds_log.append(log)
        print("  round %d: %s; %d routes unserved, %d real routes added (%d new pairs)" % (
            rnd, "promise and check agree" if agree_all else "not agreed", log["unservedRoutes"], log["realRoutesAdded"],
            log["pairsAdded"]), flush=True)
        if agree_all or rnd == MAX_ROUNDS:
            break
        Tab = rt_dedupe(rt_concat([rt_take(Tab, np.flatnonzero(~unserved))] + new_parts))
        del new_parts
        hint_prev = {b: sols[b]["chosen"] for b in bl}
        np.savez(rpath, **Tab, pair_b=pair_b, pair_j=pair_j, pair_m0=pair_m0,
                 state=np.array(json.dumps(_plain({"log": log, "logs": rounds_log, "hint": {str(k): v for k, v in hint_prev.items()}}))))
        gc.collect()
    timings["solve"] = round(t_solve, 1)
    timings["check"] = round(t_check, 1)
    results = []
    for b in sorted(BUDGETS_M):
        s = final[b]
        r, ev, chosen = s["r"], s["ev"], s["chosen"]
        unused = [int(c) for c in s["raw"] if c not in set(chosen)]
        rows = []
        for c in chosen:
            rows.append({"id": ch[c]["id"], "street": ch[c]["street"], "mi": ch[c]["mi"], "costM": ch[c]["costM"],
                         "facilities": ch[c]["facilities"], "bridge": ev["alone"].get(c, 0) == 0, "servesAlone": int(ev["alone"].get(c, 0))})
        iso = isolated(sim, S, ch, chosen, s["forced"], ev["onRoute"])
        iso_raw = isolated(sim, S, ch, sorted(set(s["raw"]) | s["forced"]), s["forced"], ev["onRoute"])
        res = {"budgetM": b, "chunks": [x["id"] for x in rows], "nChunks": len(rows), "centerlineMi": round(sum(ch[c]["mi"] for c in chosen), 2),
               "costM": round(sum(ch[c]["costM"] for c in chosen), 2),
               "promise": {"carTrips": round(ev["carTrips"], 2), "students": round(ev["students"], 1), "drivers": round(ev["drivers"], 1)},
               "greedyCarTrips": r.get("greedyCarTrips"),
               "startedFrom": r.get("startedFrom"),
               "bridges": [x["id"] for x in rows if x["bridge"]], "unusedDropped": [ch[c]["id"] for c in unused], "pieces": rows,
               "rounds": len(rounds_log) if rounds_log else 1, "isolated": iso, "isolatedBeforeDrop": iso_raw}
        if "check" in s:
            chk = s["check"]
            res["carTripsRemoved"] = round(chk["carTrips"], 2)
            res["students"], res["drivers"] = round(chk["students"], 1), round(chk["drivers"], 1)
            res["checkedOverPromise"] = round(chk["carTrips"] / ev["carTrips"], 4) if ev["carTrips"] else None
            res["promiseCheckGap"] = round(abs(chk["carTrips"] - ev["carTrips"]) / max(ev["carTrips"], 1e-9), 4)
        results.append(res)
        print("  $%dM: %d chunks, %.1f mi, $%.2fM, promise %.1f car trips%s, %d bridges, %d isolated pieces (%s), %s" % (
            b, res["nChunks"], res["centerlineMi"], res["costM"], ev["carTrips"],
            ", checked %.1f car trips, %.0f students / %.0f drivers" % (res["carTripsRemoved"], res["students"], res["drivers"]) if "check" in s else "",
            len(res["bridges"]), iso["pieces"], json.dumps(iso["byCause"]), gap_words(r["gap"])), flush=True)
    timings["total"] = round(time.time() - t_all, 1)
    json.dump(timings, open(os.path.join(sim.CACHE, "segments-timings.json"), "w"), indent=1)
    print("  segments: timings %s" % json.dumps(timings))
    out = {"note": "Written by tools/school-trips/school-segments-ip.py through tools/school-trips/school-sim.py --segments. budgets[i].chunks are the chunk "
                   "ids chosen at that budget by the integer program, which maximises year-10 family-car trips removed (central "
                   "case, everything else at baseline). carTripsRemoved, students and drivers are the checked figures from the "
                   "full route search on that budget's network: the car trips removed, and the students (and expected drivers "
                   "among them) whose route's on-network share rises. promise is the program's own count on its route menu. "
                   "A bridge is a chunk no chosen route needs alone. Each plan is the best found, not proven best: the solve "
                   "starts from the greedy plan (greedyCarTrips, its binned value on the same program) or the last round's, and "
                   "keeps it unless CP-SAT finds better within the round's limit (program.timeLimitsS). rounds is how many "
                   "solve-and-check rounds ran (loop holds each round's promise and check); "
                   "isolated counts the chosen pieces touching no baseline network, by cause.",
           "chunks": [{k: v for k, v in c.items() if k != "edges"} for c in ch], "budgets": results,
           "candidates": counts, "menu": {"pairs": n_menu_pairs, "routes": n_menu_routes, "corridorFt": corridor,
                                          "todayGapsEqual": [gaps_same, gaps_tot]},
           "objective": {"case": CASE, "lambda": lam_c, "binPct": 100 * BIN, "unservedFrac": UNSERVED_FRAC, "checkTol": CHECK_TOL,
                         "maxRounds": MAX_ROUNDS, "routes": sstats},
           "program": {"stats": P["stats"] if P is not None else None, "mipRelGap": MIP_REL_GAP,
                       "timeLimitsS": [limits_used[k] for k in sorted(limits_used)], "cpsatLinearization": CPSAT_LIN, "cpsatWorkers": SOLVE_WORKERS, "cpsatMemoryMB": CPSAT_MEM_MB},
           "loop": rounds_log, "solver": SOLVER}
    out["nested"], out["calmCapMi"] = NESTED, CALM_CAP_MI
    bad = check_output(out, {c["id"]: c["costM"] for c in out["chunks"]}, ALL_BUDGETS_M if OUT_PATH is None else BUDGETS_M,
                       published=OUT_PATH is None)
    for line in bad:
        print("  FAIL segments: %s" % line, flush=True)
    if bad:
        raise SystemExit("segments: %d output checks failed; segments.json not written" % len(bad))
    print("  pass segments: every budget, chunk ids exist, each budget within its cost and checked%s" % (
        ", budgets nested" if NESTED or OUT_PATH is None else ""), flush=True)
    if seed is not None:
        out["seed"] = {"path": SEED_PATH, "mapRule": "today's chunk maps onto an old plan when over %g of its CNNs are in it" % SEED_FRAC,
                       "coverage": {str(k): v for k, v in sorted(seed_cov.items())},
                       "round1Start": {str(k): v for k, v in sorted(seed_used.items())}}
    if OFFPLAN:
        out["parallelRule"] = {"oneBlockFt": seg.ONE_BLOCK_FT, "nextStreetX": seg.NEXT_STREET_X, "maxFt": seg.NEXT_STREET_MAX_FT,
                               "degrees": seg.PARALLEL_DEG, "minFt": seg.PARALLEL_MIN_FT,
                               "overlap": seg.PARALLEL_OVERLAP, "continueM": CONTINUE_M}
    return _plain(out)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--solve":
    _solve_main(sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7] if len(sys.argv) > 7 else None,
                sys.argv[8] if len(sys.argv) > 8 else None)
