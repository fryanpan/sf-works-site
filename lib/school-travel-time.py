#!/usr/bin/env python3
"""Travel time from every census block to the nearest school of its children's level, riding only the all-ages network, today and with the plan built.

    lib/school-travel-time.py                 # build out/school-travel/
    lib/school-travel-time.py --workers 3     # fewer parallel workers (default and most: MAX_WORKERS, 5)
    lib/school-travel-time.py --no-cache      # rebuild the walk network instead of loading .cache/walknet/

Bryan, 2026-09-29: "For streets let's say they can
safely ride just those all ages network ... From each block you could instead
plot travel time to nearest school. And we set a target of 15min and assume
walking for all unsafe blocks at 2mph. And biking at 10mph for safe blocks
otherwise. Detour rule sounds reasonable." The detour rule on the task: a route
may run up to 25% longer than the shortest walk.

THE MODEL.
  * Network: OpenStreetMap's walk network (lib/walknet.py,
    data/osm-cache/sf-walk.json). A walk edge is ridden at RIDE_MPH when it
    runs along an all-ages bikeway: its midpoint lies within EDGE_SNAP_M of the
    bikeway line and its bearing is within EDGE_ANGLE_DEG of the line's there.
    Every other edge, every stairway (highway=steps), and the straight
    connectors from a block's frontage or a school's point to the network, are
    walked at WALK_MPH. A line under half matched this way (SFMTA draws some
    park paths well off OSM's) is matched again at LINE_FALLBACK_M, but only to
    off-street ways (OFF_STREET), so the fallback never rides a parallel
    street. Mode changes are
    free and unlimited along a route.
  * All-ages network, exactly as the bike explorer defines it
    (tools/bike-network/walk-reach.py): today, the latest year's segments
    (site/data/bike-history/segments.json) coded 1, 4, S, 2c or 3c in
    components.json (paths, separated lanes, Slow Streets, and painted lanes or
    signed routes above the 2023 Bike Comfort Index line); the plan built,
    today's plus every rated North Star block (site/data/north-star/) drawn as
    Separated, Car-free, Shared-use Path or Shared. Traffic-calmed "Shared L3"
    blocks count in neither, as the explorer leaves them off by default.
  * Detour cap: a route from block b to school s counts only if its length is
    at most DETOUR x the shortest walk from b to s.
  * The time for a block and level is the fastest capped route to any school of
    that level. A school serves a level when a child can enter at its start and
    stay through it (LEVEL_SERVES): children 5-9 go to schools starting at K or
    1, 10-14 to schools starting by grade 7 and running through 8, 15-17 to
    schools starting by grade 9 and running through 11 (grade spans from CDE for
    public schools and DataSF 7e7j-59qk for private). The explorer's school list is used
    (site/data/bike-history/reach.json, schools open today), without the
    schools it files as 'other' (court, county community, opportunity,
    special education, and alternative schools that admit by audition or only
    newcomers or teach by independent study; OPEN_ALTERNATIVE keeps the two that
    enrol by the ordinary lottery), continuation high schools, the two Five Keys
    charters listed under the SF Sheriff's, which a family does not choose as a
    neighbourhood school, and three private registrations at one office suite
    (OFFICE_SUITE). Life Learning Academy is placed at its Treasure Island
    address (RELOCATED); DataSF's coordinates put it in SoMa. A public-only figure is computed beside the headline.
  * A block joins the network along its frontage (walknet.use_census_outlines),
    as the explorer measures it.

THE SEARCH. The fastest route under a length cap is a resource-constrained
shortest path, found in two passes.
  1. Upper bound, by Lagrangian relaxation: for each weight in LAMBDAS, one
     multi-source Dijkstra from every school of the level minimises
     time + lambda x (length at walking pace), and each block keeps the fastest
     of those routes that meets its cap against the school it reached. The
     largest weight is the shortest walk, which always meets the cap.
  2. Exact, wherever the time is under EXACT_MAX_MIN: from each school whose
     shortest walk could still beat min(pass 1, EXACT_MAX_MIN),
     a label-setting search over (time, length) labels, pruned by time against
     the best so far and by the ellipse length + shortest walk to the block >
     cap, and keeping per node only labels no other label beats on both. It
     returns the true fastest capped route. So every time under
     EXACT_MAX_MIN is exact, and a time over it is pass 1's, an upper bound
     (a real route; the fastest may be quicker, but not under EXACT_MAX_MIN). The summary reports how many
     block-level times pass 2 improved on pass 1, and by how much.
The walk-only time is the shortest walk, which pass 1 finds exactly.

THE GAP RANKING. A gap is a run of plan blocks on one street, touching end to
end, not all-ages today. Only a block-level that is over TARGET_MIN today and
under it with the whole plan built can change status when one gap is added to
today's network or left out of the plan. For each such block-level, a gap can
matter only if one of its nodes lies inside the block's detour ellipse for a
school within reach (shortest walk from the block + shortest walk to the
school <= cap, and fastest time from the block + fastest time to the school
on the finished plan's network <= TARGET_MIN), so the exact search, guided
by that plan time as an A* lower bound, is rerun only for those, with the gap
added (children brought under) and with it left out of the plan (children
lost).

WHAT IT WRITES.
  out/school-travel/blocks.json   per block: children by band, minutes to the
                                  nearest school of each level, today and plan
                                  built, and to its SFUSD elementary
                                  attendance-area school (DataSF e6tr-sxwg).
  out/school-travel/summary.json  children in blocks over TARGET_MIN, by band,
                                  walking only, today and plan built; the
                                  attendance-area figure; the plan's gaps
                                  ranked by the children each brings under
                                  TARGET_MIN when built alone on today's
                                  network, and by the children lost if it alone
                                  were left out of the finished plan; method
                                  and sources.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import heapq
import json
import math
import multiprocessing
import os
import re
import sys
import time

import numpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import netcache, rcsp, stable  # noqa: E402
import sfdata  # noqa: E402
import walknet  # noqa: E402

walknet.use_census_outlines()

BIKE = os.path.join(ROOT, "site", "data", "bike-history")
NS = os.path.join(ROOT, "site", "data", "north-star")
OUT = os.path.join(ROOT, "out", "school-travel")

WALK_MPH, RIDE_MPH = 2.0, 10.0
MPS = 1609.344 / 3600.0
RW = 1.0 / (WALK_MPH * MPS)  # seconds per metre walking
RB = 1.0 / (RIDE_MPH * MPS)  # seconds per metre riding
TARGET_MIN = 15.0
# Pass 2 is exact up to this, so the map's 5-minute bands above the target are true times.
EXACT_MAX_MIN = 30.0
DETOUR = 1.25
LAMBDAS = [0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.5, 5.0, 1000.0]
EDGE_SNAP_M = 15.0
EDGE_ANGLE_DEG = 30.0
LINE_FALLBACK_M = 60.0  # walknet.FALLBACK_SNAP_M: park paths SFMTA draws off OSM's line
OFF_STREET = {"footway", "path", "cycleway", "pedestrian", "track", "bridleway", "corridor"}
# The source geocode is in SoMa; CDE gives the campus as "651 Eighth St., Bldg. 229 Treasure Island"
# (sd.cde.ca.gov, CDS 38684783830429, read 2026-09-30), placed by the Census geocoder.
RELOCATED = {"Life Learning Academy Charter": (-122.36770, 37.82498)}
# CDE "Alternative Schools of Choice" are dropped with the court and special-education
# schools unless named here: these two enrol by the ordinary SFUSD high school lottery.
# The rest are not a nearest school a family can choose: SOTA admits by audition,
# S.F. International enrols newcomers only, Independence is independent study.
OPEN_ALTERNATIVE = {"Jordan (June) School for Equity", "Academy (The)- SF @McAteer"}
# Three private registrations share one office suite (166 Geary St Ste 1500), not a campus.
OFFICE_SUITE = {"Aloha Micro Academy", "Bloomington Pre-University Education", "Enlighten Academy"}
WALK_CUTOFF_M = 9000.0  # per-school shortest-walk search radius
# Pass 2 prunes nodes beyond the walk radius, which is safe only while the whole
# exact range could not be ridden past it.
assert EXACT_MAX_MIN * 60 < WALK_CUTOFF_M * RB, "raise WALK_CUTOFF_M with EXACT_MAX_MIN"
TODAY_CODES = {"1", "4", "S", "2c", "3c"}
PLAN_CODE = {"Separated": "4", "Car-free": "1", "Shared-use Path": "1", "Shared": "S"}
ATTENDANCE_ID = "e6tr-sxwg"
SCHOOLS_ID = "7e7j-59qk"
BANDS = [("a5_9", "elementary", "5-9"), ("a10_14", "middle", "10-14"), ("a15_17", "high", "15-17")]
# A school serves a level when a child can enter it at that level's start and stay
# through it, not when one grade overlaps: a 5-8 school is not an elementary school
# for a five-year-old, and a K-9 school is not a high school for a sixteen-year-old.
LEVEL_SERVES = {"elementary": lambda lo, hi: lo <= 1,
                "middle": lambda lo, hi: lo <= 7 and hi >= 8,
                "high": lambda lo, hi: lo <= 9 and hi >= 11}
INF = float("inf")
# Bryan, 2026-10-01 on docs/access-model-architecture.md: "allow up to 5 workers".
MAX_WORKERS = 5
# The compiled searches (lib/rcsp.c) when a C compiler is present; --pure forces the Python ones.
FAST = {"on": False}


def read(*p):
    return json.load(open(os.path.join(*p)))


# -- the graph ---------------------------------------------------------------

class Net(object):
    def __init__(self, cache=True):
        """The walk network; with cache, loaded from .cache/walknet/ when its inputs are unchanged (lib/netcache.py)."""
        self.cache = cache
        G = netcache.graph(use_cache=cache)
        self.G = G
        n = len(G.x)
        self.adj = [[] for _ in range(n)]
        for e, (u, v) in enumerate(zip(G.eu, G.ev)):
            self.adj[u].append((v, e))
            self.adj[v].append((u, e))
        self.L = G.elen
        self.fast = rcsp.Graph(self.adj, self.L) if FAST["on"] else None
        self._bike = {}

    def bike_array(self, bike):
        """A ridden-edge list as a uint8 array for the compiled searches, cached by identity."""
        if isinstance(bike, numpy.ndarray):
            return bike
        hit = self._bike.get(id(bike))
        if hit is None or hit[0] is not bike:
            hit = (bike, numpy.array(bike, dtype=numpy.uint8))
            if len(self._bike) >= 8:  # the gap ranking makes two lists per gap; keep only recent ones
                self._bike.pop(next(iter(self._bike)))
            self._bike[id(bike)] = hit
        return hit[1]

    def ends(self, lon, lat):
        """[(node, connector m, along-edge m, edge)] for a point's joins to the network."""
        out = []
        for e, t, c in self.G.snap(lon, lat):
            L = self.L[e]
            out.append((self.G.eu[e], c, t * L, e))
            out.append((self.G.ev[e], c, (1 - t) * L, e))
        return out


def bearing(ax, ay, bx, by):
    return math.atan2(by - ay, bx - ax)


def angle_ok(a, b, lim):
    d = abs(a - b) % math.pi
    return min(d, math.pi - d) <= math.radians(lim)


class LineIndex(object):
    """Line segments of a set of bikeway lines, gridded, for the edge test."""

    CELL = 50.0

    def __init__(self, lines):
        self.segs = []
        self.cells = collections.defaultdict(list)
        for key, pts in lines:
            P = [walknet.xy(lon, lat) for lon, lat in pts]
            for a, b in zip(P, P[1:]):
                if a == b:
                    continue
                i = len(self.segs)
                self.segs.append((key, a[0], a[1], b[0], b[1]))
                for cx in range(int(min(a[0], b[0]) // self.CELL) - 1, int(max(a[0], b[0]) // self.CELL) + 2):
                    for cy in range(int(min(a[1], b[1]) // self.CELL) - 1, int(max(a[1], b[1]) // self.CELL) + 2):
                        self.cells[(cx, cy)].append(i)

    def near(self, px, py, r):
        out = set()
        for cx in range(int((px - r) // self.CELL), int((px + r) // self.CELL) + 1):
            for cy in range(int((py - r) // self.CELL), int((py + r) // self.CELL) + 1):
                out.update(self.cells.get((cx, cy), ()))
        return out


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2)) if L2 else 0.0
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def edges_of(net, lines, cache=False):
    """{line key: set(edge)}: edges_of_built's answer; with cache, kept in .cache/walknet/ (lib/netcache.py).

    Only callers that use the sets order-free pass cache: a loaded set holds the
    same edges but may iterate in a different order from a built one."""
    return netcache.edges(edges_of_built, net, lines, netcache.source_of(edges_of_built, LineIndex.__init__, LineIndex.near, seg_dist, angle_ok, bearing) + [
        EDGE_SNAP_M, EDGE_ANGLE_DEG, LINE_FALLBACK_M, sorted(OFF_STREET)], use_cache=cache)


def edges_of_built(net, lines):
    """{line key: set(edge)}: the walk edges each line's all-ages riding covers.

    An edge rides a line when its midpoint is within EDGE_SNAP_M of one of the
    line's segments and runs within EDGE_ANGLE_DEG of it. A line with under
    half its length matched this way (SFMTA draws some park paths well off
    OSM's) is matched again at LINE_FALLBACK_M."""
    G = net.G
    idx = LineIndex(lines)
    out = collections.defaultdict(set)

    def match(radius, keys=None):
        for e in range(len(G.eu)):
            if G.ehw[e] == "steps" or (keys is not None and G.ehw[e] not in OFF_STREET):
                continue
            u, v = G.eu[e], G.ev[e]
            mx, my = (G.x[u] + G.x[v]) / 2, (G.y[u] + G.y[v]) / 2
            be = bearing(G.x[u], G.y[u], G.x[v], G.y[v])
            for i in idx.near(mx, my, radius):
                key, ax, ay, bx, by = idx.segs[i]
                if keys is not None and key not in keys:
                    continue
                if seg_dist(mx, my, ax, ay, bx, by) <= radius and angle_ok(be, bearing(ax, ay, bx, by), EDGE_ANGLE_DEG):
                    out[key].add(e)

    match(EDGE_SNAP_M)
    weak = set()
    for key, pts in lines:
        m = sum(net.L[e] for e in out.get(key, ()))
        length = sum(math.hypot(*(a - b for a, b in zip(walknet.xy(*p), walknet.xy(*q)))) for p, q in zip(pts, pts[1:]))
        if length > 0 and m < 0.5 * length:
            weak.add(key)
    if weak:
        match(LINE_FALLBACK_M, weak)
    return out, weak


# -- searches ------------------------------------------------------------------

def walk_search(net, seeds, cutoff):
    """Shortest walk (metres) from seed ends, to every node within cutoff: {node: m}.

    With the compiled searches, an array over all nodes instead, INF past the cutoff."""
    if net.fast is not None:
        return net.fast.walk([x[0] for x in seeds], [c + along for _n, c, along, _e in seeds], cutoff)
    dist = {}
    h = []
    for node, c, along, _e in seeds:
        d = c + along
        if d < dist.get(node, INF):
            dist[node] = d
            h.append((d, node))
    heapq.heapify(h)
    adj, L = net.adj, net.L
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for v, e in adj[u]:
            nd = d + L[e]
            if nd <= cutoff and nd < dist.get(v, INF):
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def lagrange_search(net, bike, seeds, lam, cutoff=INF, targets=None):
    """Multi-source search minimising time + lam x length at walking pace.

    seeds: [(node, connector m, along m, edge, school)]. Returns per-node
    arrays (cost, time, length, school), with cost INF where not reached.
    With targets (a set of nodes), the search stops once every one is settled."""
    n = len(net.adj)
    L, adj = net.L, net.adj
    lw = lam * RW
    if net.fast is not None:
        key = id(seeds)
        if FAST.get("seeds_key") != key or FAST.get("seeds_ref") is not seeds:
            FAST.update(seeds_key=key, seeds_ref=seeds,
                        seeds=rcsp.Ends([x[:4] for x in seeds], school=[x[4] for x in seeds]))
        mask = None
        if targets is not None:
            mask = numpy.zeros(n, dtype=numpy.uint8)
            mask[list(targets)] = 1
        arr = net.fast.lagrange(net.bike_array(bike), RW, RB, lw, cutoff, FAST["seeds"], mask)
        return tuple(a.tolist() for a in arr)
    cost, tm, ln, src = [INF] * n, [0.0] * n, [0.0] * n, [-1] * n
    h = []
    for node, c, along, e, s in seeds:
        t = c * RW + along * (RB if bike[e] else RW)
        m = c + along
        k = t + lw * m
        if k < cost[node]:
            cost[node], tm[node], ln[node], src[node] = k, t, m, s
    for node in range(n):
        if cost[node] < INF:
            h.append((cost[node], node))
    heapq.heapify(h)
    left = set(targets) if targets is not None else None
    while h:
        k, u = heapq.heappop(h)
        if k > cost[u]:
            continue
        if left is not None:
            left.discard(u)
            if not left:
                break
        tu, lu, su = tm[u], ln[u], src[u]
        for v, e in adj[u]:
            le = L[e]
            te = le * (RB if bike[e] else RW)
            nk = k + te + lw * le
            if nk < cost[v] and nk <= cutoff:
                cost[v], tm[v], ln[v], src[v] = nk, tu + te, lu + le, su
                heapq.heappush(h, (nk, v))
    return cost, tm, ln, src


def block_best(ends, bike, lam, arr):
    """(time s, length m, school) of the least-cost join of a block to the search tree."""
    cost, tm, ln, src = arr
    lw = lam * RW
    best = None
    for node, c, along, e in ends:
        if cost[node] == INF:
            continue
        te = c * RW + along * (RB if bike[e] else RW)
        m = c + along
        k = cost[node] + te + lw * m
        if best is None or k < best[0]:
            best = (k, tm[node] + te, ln[node] + m, src[node])
    return None if best is None else best[1:]


class Level(object):
    """Everything fixed for one school level: its schools' seeds and the shortest walk from each block to each."""

    def __init__(self, net, name, schools, blocks):
        self.name, self.schools = name, schools
        self.seeds = [(node, c, along, e, i) for i, s in enumerate(schools) for node, c, along, e in s["ends"]]
        self.walk = []  # per school: {block index: shortest walk m}
        for s in schools:
            if "_walk" in s:
                self.walk.append(s["_walk"])
                continue
            dist = walk_search(net, s["ends"], WALK_CUTOFF_M)
            w = {}
            if net.fast is not None:
                w = block_walks(dist, blocks)
                s["_walk"] = w
                self.walk.append(w)
                continue
            for bi, b in enumerate(blocks):
                best = INF
                for node, c, along, _e in b["ends"]:
                    d = dist.get(node)
                    if d is not None and d + c + along < best:
                        best = d + c + along
                if best < INF:
                    w[bi] = best
            s["_walk"] = w
            self.walk.append(w)


def block_walks(dist, blocks):
    """{block index: shortest walk m} from a node-distance array: min over the block's ends of dist + connector + along."""
    cache = FAST.setdefault("ends", {})
    hit = cache.get(id(blocks))
    if hit is None or hit[0] is not blocks:
        if len(cache) >= 8:
            cache.clear()
        nodes, cs, alongs, owner = [], [], [], []
        for bi, b in enumerate(blocks):
            for node, c, along, _e in b["ends"]:
                nodes.append(node)
                cs.append(c)
                alongs.append(along)
                owner.append(bi)
        hit = cache[id(blocks)] = (blocks, (numpy.array(nodes, dtype=numpy.int64), numpy.array(cs),
                                            numpy.array(alongs), numpy.array(owner, dtype=numpy.int64)))
    nodes, cs, alongs, owner = hit[1]
    if not len(nodes):
        return {}
    # Same order of addition as the Python loop: (d + c) + along.
    v = dist[nodes] + cs + alongs
    starts = numpy.flatnonzero(numpy.r_[True, owner[1:] != owner[:-1]])
    mins = numpy.minimum.reduceat(v, starts)
    bis = owner[starts]
    ok = mins < INF
    return dict(zip(bis[ok].tolist(), mins[ok].tolist()))


def level_times(net, bike, level, blocks, cutoff_s=None, stop_early=False):
    """Per block: (seconds, school index, metres, rode) of the fastest capped route to a school of the level.

    With cutoff_s, searches stop once no route could come in under it, and a
    block with no such route gets None (used for the gap ranking, which only
    asks whether a block is under the target)."""
    if net.fast is not None:
        return level_times_fast(net, bike, level, blocks, cutoff_s, stop_early)
    best = [None] * len(blocks)
    lmax = cutoff_s / RB if cutoff_s else None
    targets = {node for b in blocks for node, _c, _a, _e in b["ends"]} if stop_early else None
    for lam in LAMBDAS:
        cut = cutoff_s + lam * RW * lmax if cutoff_s else INF
        arr = lagrange_search(net, bike, level.seeds, lam, cut, targets)
        for bi, b in enumerate(blocks):
            r = block_best(b["ends"], bike, lam, arr)
            if r is None:
                continue
            t, m, s = r
            w = level.walk[s].get(bi)
            if w is None or m > DETOUR * w + 1e-6:
                continue
            if cutoff_s and t > cutoff_s:
                continue
            if best[bi] is None or t < best[bi][0]:
                best[bi] = (t, s, m, t < m * RW - 1e-6)
    return best


def level_times_fast(net, bike, level, blocks, cutoff_s=None, stop_early=False):
    """level_times with the compiled search and block_best done over arrays: the same result, value for value.

    Every block's ends are laid out flat; for each weight, each end's join cost
    is computed with the same operations in the same order as block_best, the
    block keeps its first end of least cost (block_best's strict <), and the
    fastest capped route is kept across weights with the same strict <."""
    nb = len(blocks)
    fe = [fast_ends(b["ends"]) for b in blocks]
    owner = numpy.repeat(numpy.arange(nb, dtype=numpy.int64), [len(x.node) for x in fe])
    node = numpy.concatenate([x.node for x in fe]).astype(numpy.int64) if nb else numpy.zeros(0, dtype=numpy.int64)
    c = numpy.concatenate([x.c for x in fe]) if nb else numpy.zeros(0)
    along = numpy.concatenate([x.along for x in fe]) if nb else numpy.zeros(0)
    e = numpy.concatenate([x.e for x in fe]).astype(numpy.int64) if nb else numpy.zeros(0, dtype=numpy.int64)
    bk = net.bike_array(bike)
    R = numpy.where(bk[e] != 0, RB, RW)
    te = c * RW + along * R
    m = c + along
    # Shortest walk from each block to each school, INF where the level's dict has none.
    Wm = numpy.full((len(level.walk), nb), INF)
    for si, w in enumerate(level.walk):
        if w:
            ks = numpy.fromiter(w.keys(), dtype=numpy.int64, count=len(w))
            vs = numpy.fromiter(w.values(), dtype=numpy.float64, count=len(w))
            keep = ks < nb
            Wm[si, ks[keep]] = vs[keep]
    mask = None
    if stop_early:
        mask = numpy.zeros(len(net.adj), dtype=numpy.uint8)
        mask[node] = 1
    key = id(level.seeds)
    if FAST.get("seeds_key") != key or FAST.get("seeds_ref") is not level.seeds:
        FAST.update(seeds_key=key, seeds_ref=level.seeds,
                    seeds=rcsp.Ends([x[:4] for x in level.seeds], school=[x[4] for x in level.seeds]))
    # Ends are grouped by block, blocks in order: each group's first index.
    newgrp = numpy.r_[True, owner[1:] != owner[:-1]] if len(owner) else numpy.zeros(0, dtype=bool)
    starts = numpy.flatnonzero(newgrp)
    seg = numpy.cumsum(newgrp) - 1  # each end's group
    bt = numpy.full(nb, INF)
    bs = numpy.zeros(nb, dtype=numpy.int64)
    bm = numpy.zeros(nb)
    have = numpy.zeros(nb, dtype=bool)
    lmax = cutoff_s / RB if cutoff_s else None
    for lam in LAMBDAS:
        lw = lam * RW
        cut = cutoff_s + lam * RW * lmax if cutoff_s else INF
        cost, tm, ln, src = net.fast.lagrange(bk, RW, RB, lw, cut, FAST["seeds"], mask)
        cn = cost[node]
        k = cn + te + lw * m
        k[cn == INF] = INF
        if not len(k):
            continue
        # Per block, the first end of least cost (block_best keeps the first on a tie).
        low = numpy.minimum.reduceat(k, starts)
        hit = numpy.flatnonzero(k == low[seg])
        first = hit[numpy.r_[True, owner[hit][1:] != owner[hit][:-1]]]
        first = first[k[first] < INF]
        bi = owner[first]
        nd = node[first]
        t = tm[nd] + te[first]
        mm = ln[nd] + m[first]
        s = src[nd].astype(numpy.int64)
        w = Wm[s, bi]
        ok = (w < INF) & ~(mm > DETOUR * w + 1e-6)
        if cutoff_s:
            ok &= ~(t > cutoff_s)
        better = ok & (~have[bi] | (t < bt[bi]))
        bi, t, mm, s = bi[better], t[better], mm[better], s[better]
        bt[bi], bm[bi], bs[bi] = t, mm, s
        have[bi] = True
    out = [None] * nb
    for bi, t, s, m1 in zip(numpy.flatnonzero(have).tolist(), bt[have].tolist(), bs[have].tolist(), bm[have].tolist()):
        out[bi] = (t, s, m1, t < m1 * RW - 1e-6)
    return out


CAP_TOL = 0.05  # metres: slack for float32 walk distances
# Seconds taken off the A* bound in refine_block. The bound and a route's time
# are both sums of the same edge times, added in opposite orders, so they can
# differ by rounding (about 1e-10 s here); a margin far above that means a label
# is never dropped when it could still win, so the answer is the same as with no
# bound at all.
A_MARGIN = 1e-3


def walk_array(net, ends):
    """Shortest walk from a point's ends to every node, as a float32 array (INF past WALK_CUTOFF_M)."""
    d = walk_search(net, ends, WALK_CUTOFF_M)
    if net.fast is not None:
        return d.astype(numpy.float32)
    a = numpy.full(len(net.adj), INF, dtype=numpy.float32)
    if d:
        a[numpy.fromiter(d.keys(), dtype=numpy.int64, count=len(d))] = numpy.fromiter(d.values(), dtype=numpy.float32, count=len(d))
    return a


def time_array(net, bike, ends):
    """Fastest uncapped time (s) from a point's ends to every node over a network, as a float32 array."""
    n = len(net.adj)
    if net.fast is not None:
        return net.fast.time(net.bike_array(bike), RW, RB, fast_ends(ends)).astype(numpy.float32)
    dist = [INF] * n
    h = []
    for node, c, along, e in ends:
        t = c * RW + along * (RB if bike[e] else RW)
        if t < dist[node]:
            dist[node] = t
            h.append((t, node))
    heapq.heapify(h)
    adj, L = net.adj, net.L
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for v, e in adj[u]:
            nd = d + L[e] * (RB if bike[e] else RW)
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return numpy.array(dist, dtype=numpy.float32)


def exact_best(net, bike, level, bi, b_ends, wb, upper, hb=None, hd=None, lazy=False):
    """(seconds, school index, metres) of the fastest capped route from block bi to a school of the level, if one beats upper; else None.

    wb: shortest walk from the block to each node (indexable). hb, optional: a
    lower bound on the time from each node to the block on this network (the
    uncapped time on a network that contains it), which orders the search and
    prunes it (A*). Labels run from each school toward the block; see THE SEARCH.
    hd, compiled searches only: the same kind of bound as a float64 array, for
    refine_block, where it changes how much is searched but never the answer
    (see A_MARGIN). lazy, compiled searches only: wb and hd are read from the
    block's lazy searches (rcsp lazy slots 0 and 1) instead of arrays."""
    if net.fast is not None:
        fs = getattr(level, "_fast_schools", None)
        if fs is None:
            fs = level._fast_schools = rcsp.Schools([s["ends"] for s in level.schools])
        Ws = numpy.array([w.get(bi, INF) for w in level.walk], dtype=numpy.float64)
        # hb comes only from gap_eval, which passes wb and hb as float32 arrays;
        # refine_block passes wb as a list of Python floats and no hb.
        f32 = hb is not None
        assert not f32 or isinstance(wb, numpy.ndarray)
        if lazy:
            return net.fast.exact(net.bike_array(bike), RW, RB, DETOUR, CAP_TOL, fs, Ws, fast_ends(b_ends), None,
                                  None, False, None, upper, lazy=3, margin=A_MARGIN)
        wba = wb if isinstance(wb, numpy.ndarray) else numpy.array(wb, dtype=numpy.float32)
        return net.fast.exact(net.bike_array(bike), RW, RB, DETOUR, CAP_TOL, fs, Ws, fast_ends(b_ends), wba,
                              hb, f32, None if f32 else hd, upper)
    best, found = upper, None
    target = collections.defaultdict(list)
    for node, c, along, e in b_ends:
        target[node].append((c * RW + along * (RB if bike[e] else RW), c + along))
    adj, L = net.adj, net.L
    for si, s in enumerate(level.schools):
        Ws = level.walk[si].get(bi)
        if Ws is None or Ws * RB >= best:
            continue
        cap = DETOUR * Ws + CAP_TOL
        front = collections.defaultdict(list)
        h = []
        for node, c, along, e in s["ends"]:
            t0 = c * RW + along * (RB if bike[e] else RW)
            h.append((t0 + (hb[node] if hb is not None else 0.0), t0, c + along, node))
        heapq.heapify(h)
        while h:
            key, t, m, u = heapq.heappop(h)
            if key >= best:
                break
            if m + wb[u] > cap:
                continue
            fu = front[u]
            if any(t2 <= t and m2 <= m for t2, m2 in fu):
                continue
            front[u] = [(t2, m2) for t2, m2 in fu if not (t <= t2 and m <= m2)] + [(t, m)]
            for tt, mm in target.get(u, ()):
                if m + mm <= cap and t + tt < best:
                    best, found = t + tt, (t + tt, si, m + mm)
            for v, e in adj[u]:
                le = L[e]
                nt, nm = t + le * (RB if bike[e] else RW), m + le
                nk = nt + (hb[v] if hb is not None else 0.0)
                if nk < best and nm + wb[v] <= cap:
                    heapq.heappush(h, (nk, nt, nm, v))
    return found


_ENDS = {}


def fast_ends(ends):
    """A point's ends as rcsp.Ends, cached by identity (the lists live for the whole run)."""
    hit = _ENDS.get(id(ends))
    if hit is None or hit[0] is not ends:
        hit = _ENDS[id(ends)] = (ends, rcsp.Ends(ends))
    return hit[1]


# -- inputs --------------------------------------------------------------------

def grade_set(lo, hi):
    def g(v):
        v = (v or "").strip().upper()
        if v in ("K", "TK", "P", "PK"):
            return 0
        return int(v) if v.isdigit() else None
    a, b = g(lo), g(hi)
    return set(range(a, b + 1)) if a is not None and b is not None else set()


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()


def load_schools():
    """The explorer's open schools, with the grades each teaches and the levels it serves."""
    reach = read(BIKE, "reach.json")
    cde = read(ROOT, "data", "extract", "schools", "cde-sf.json")["records"]
    cde_by = {(c["school"], round(c["lon"], 5) if c["lon"] else None, round(c["lat"], 5) if c["lat"] else None): c for c in cde}
    priv = sfdata.fetch(SCHOOLS_ID, where="public_yesno=false and status='Active'", order=":id", floor=80)
    priv_by = {r["school"]: r for r in priv.rows}
    out, dropped = [], collections.Counter()
    for s in reach["schools"]:
        if s["closed"]:
            continue
        if s["level"] == "other" and s["name"] not in OPEN_ALTERNATIVE:
            dropped["other (court, community, special education, audition or newcomer-only alternative)"] += 1
            continue
        if s["name"] in OFFICE_SUITE:
            dropped["private registration at an office suite"] += 1
            continue
        if "Sheriff" in s["name"]:
            dropped["in-custody (SF Sheriff's) charter"] += 1
            continue
        if s["name"] in RELOCATED:
            s = dict(s, lon=RELOCATED[s["name"]][0], lat=RELOCATED[s["name"]][1])
        if s["private"]:
            r = priv_by.get(s["name"])
            grades = grade_set(r.get("low_grade"), r.get("high_grade")) if r else set()
            soc = r.get("entity_type") if r else None
        else:
            c = cde_by.get((s["name"], s["lon"], s["lat"]))
            if c is None:
                c = next((x for x in cde if x["school"] == s["name"] and x["status"] == "Active"), None)
            grades = grade_set(*c["grades"].split("-")) if c and "-" in (c["grades"] or "") else set()
            soc = c["soc_type"] if c else None
            if soc and soc.startswith("Continuation"):
                dropped["continuation high school"] += 1
                continue
        if not grades:
            # No grade span on record: fall back to the explorer's level.
            grades = {"elementary": set(range(0, 6)), "middle": {6, 7, 8}, "high": {9, 10, 11, 12},
                      "k12": set(range(0, 13))}[s["level"]]
            dropped["no grade span; explorer level used"] += 1
        levels = sorted(l for l, ok in LEVEL_SERVES.items() if ok(min(grades), max(grades)))
        out.append({"name": s["name"], "private": s["private"], "lon": s["lon"], "lat": s["lat"],
                    "grades": "%s-%s" % (("K" if min(grades) == 0 else min(grades)), max(grades)), "levels": levels, "soc": soc})
    return out, dropped, priv


PROTECTED_CODES = {"1", "4"}
BCI_MIN = 80


def all_ages_lines(brp_rule=False):
    """(today lines, plan lines not already all-ages today) as [(key, pts)], exactly as tools/bike-network/walk-reach.py picks them.

    With brp_rule (School Trips, Bryan 2026-10-14: "Only count the all ages and abilities infra from bRP where any
    unprotected bikeways must have BCI > 80"), a block counts today when it has a Class I path or Class IV separated
    lane anywhere, as before, or is a Slow Street, on the plan or off it, whatever its Bike Comfort Index (Bryan
    2026-10-18: a calmed street counts, as a new one would). Painted lanes and signed routes never
    count (Bryan 2026-10-15, choosing "Protected only" once the BCI was found untested against rider stress), so
    the optimizer can buy their upgrade."""
    segments = read(BIKE, "segments.json")
    components = read(BIKE, "components.json")
    traced = read(NS, "traced.geojson")
    status = {str(b["cnn"]): b for b in read(NS, "status.json")["blocks"]}
    today = []
    last = len(segments["years"]) - 1
    for s in segments["segments"]:
        if s["y"][last] == "0" or len(s["pts"]) < 2:
            continue
        comp = components["blocks"].get(s["key"])
        if not comp:
            continue
        codes = set(comp["m"])
        if comp.get("s") is not None:
            codes.add("S")
        if not codes & TODAY_CODES:
            continue
        if brp_rule and not codes & PROTECTED_CODES:
            # protected only (Bryan 2026-10-15, after the BCI review found no test of it against rider stress: "Protected
            # only."): a painted lane or signed route never counts, whatever its BCI. A Slow Street counts wherever it is,
            # as a newly calmed street does (Bryan 2026-10-18, choosing "Calmed counts": "Assume we apply same usual slow
            # street construction and diverters").
            if "S" not in codes:
                continue
        today.append((s["key"], s["pts"]))
    plan, plan_meta = [], {}
    for f in traced["features"]:
        p = f["properties"]
        st = status.get(str(p["cnn"]))
        if not st or p["facility"] not in PLAN_CODE or st["m"] <= 0 or len(f["geometry"]["coordinates"]) < 2:
            continue
        key = "ns:%s" % p["cnn"]
        plan.append((key, f["geometry"]["coordinates"]))
        plan_meta[key] = {"cnn": str(p["cnn"]), "street": p["street"], "facility": p["facility"], "status": st["status"]}
    return today, plan, plan_meta


def attendance_areas():
    r = sfdata.fetch(ATTENDANCE_ID, order=":id", floor=50)
    areas = []
    for row in r.rows:
        g = row["the_geom"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        areas.append({"name": row.get("sch_lng_na") or row.get("aaname"), "short": row.get("aaname"),
                      "synergy": row.get("synergy_na"), "polys": polys})
    return areas, r


def in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_poly(x, y, polys):
    for poly in polys:
        if poly and in_ring(x, y, poly[0]) and not any(in_ring(x, y, hole) for hole in poly[1:]):
            return True
    return False


STOP = {"elementary", "school", "es", "the", "of", "and", "academy", "k", "8", "sch", "ctr", "center", "dr", "college",
        "preparatory", "alternative", "community", "early", "education"}


def match_area_school(area, schools):
    """The public elementary school an attendance area is drawn around: the best name match, preferring one inside the area."""
    want = set(norm(area["name"])) | set(norm(area["short"])) | set(norm(area["synergy"]))
    want -= STOP
    best, score = None, 0.0
    for i, s in enumerate(schools):
        if s["private"] or "elementary" not in s["levels"]:
            continue
        have = set(norm(s["name"])) - STOP
        if not have:
            continue
        sc = len(want & have) / float(len(have))
        if in_poly(s["lon"], s["lat"], area["polys"]):
            sc += 0.5
        if sc > score:
            best, score = i, sc
    return best, score


# -- gaps ----------------------------------------------------------------------

def group_gaps(plan, plan_meta, today_keys):
    """Plan blocks not all-ages today, joined into runs: same street, touching end to end."""
    todo = [(k, pts) for k, pts in plan if plan_meta[k]["cnn"] not in today_keys]
    parent = {k: k for k, _ in todo}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    ends = collections.defaultdict(list)
    for k, pts in todo:
        for p in (pts[0], pts[-1]):
            x, y = walknet.xy(*p)
            ends[(plan_meta[k]["street"], int(x // 10), int(y // 10))].append((k, x, y))
    for (street, cx, cy), items in list(ends.items()):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k2, x2, y2 in ends.get((street, cx + dx, cy + dy), ()):
                    for k1, x1, y1 in items:
                        if k1 != k2 and math.hypot(x1 - x2, y1 - y2) <= 8.0:
                            parent[find(k1)] = find(k2)
    groups = collections.defaultdict(list)
    for k, _ in todo:
        groups[find(k)].append(k)
    return [sorted(v) for v in groups.values()]


# -- worker state for the gap ranking (fork inherits it) -----------------------

W = {}


def refine_block(bi):
    """Pass 2 for one block: the exact time wherever it beats pass 1."""
    net, blocks, levels, nets, res = W["net"], W["blocks"], W["levels"], W["nets"], W["res"]
    b = blocks[bi]
    out = {}
    if not b["ends"]:
        return bi, out
    # Exact below EXACT_MAX_MIN; above it, pass 1's time stands as an upper bound.
    cap_s = EXACT_MAX_MIN * 60 + 1e-6
    if net.fast is None:
        wb = walk_array(net, b["ends"]).tolist()
    else:
        # The searches below can only find a time under the largest of their
        # starting bounds, U. So no school farther than U at riding speed is
        # tried, no cap exceeds DETOUR x U / RB, and no node farther than U from
        # the block can be on a winning route: both per-block searches stop
        # there. A node past either stop gets INF, and would have been pruned
        # anyway (its shortest walk exceeds every cap by the 1 m margin, or its
        # time to the block exceeds every bound).
        ups = {nk: [min(r[0] - 1e-6, cap_s) for r in [res[(nk, lvl)][bi] for lvl in levels] + [W["area_res"][nk].get(bi)]
                    if r is not None] for nk in ("today", "plan")}
        U = max(ups["today"] + ups["plan"] + [0.0])
        # Both per-block searches are lazy: they settle nodes only as far as
        # the exact searches ask (lib/rcsp.c, lazy_get).
        wb = None
        net.fast.lazy(0, None, RW, RB, fast_ends(b["ends"]), min(WALK_CUTOFF_M, DETOUR * U / RB + CAP_TOL + 1.0))
    lazy = net.fast is not None
    for nk in ("today", "plan"):
        hd = None
        if net.fast is not None:
            if not ups[nk]:
                continue
            # A* bound: the uncapped fastest time from each node to the block on this network.
            net.fast.lazy(1, net.bike_array(nets[nk]), RW, RB, fast_ends(b["ends"]), max(ups[nk]) + 1.0)
        for lvl, L in levels.items():
            r = res[(nk, lvl)][bi]
            if r is not None:
                ex = exact_best(net, nets[nk], L, bi, b["ends"], wb, min(r[0] - 1e-6, cap_s), hd=hd, lazy=lazy)
                if ex:
                    out[(nk, lvl)] = ex
        one = W["area_level"].get(bi)
        r = W["area_res"][nk].get(bi)
        if one is not None and r is not None:
            ex = exact_best(net, nets[nk], one, bi, b["ends"], wb, min(r[0] - 1e-6, cap_s), hd=hd, lazy=lazy)
            if ex:
                out[("area", nk)] = ex
    return bi, out


def gap_eval(gi):
    """Children brought under the target by this gap alone, and lost if it alone is left out of the plan."""
    net, blocks, levels, gap_edges = W["net"], W["blocks"], W["levels"], W["gap_edges"]
    base_today, base_plan, owners = W["today"], W["plan"], W["plan_edge_owners"]
    if net.fast is not None:
        add_bike, drop_bike = net.bike_array(base_today).copy(), net.bike_array(base_plan).copy()
        es = sorted(gap_edges[gi])
        add_bike[es] = 1
        drop_bike[[e for e in es if not base_today[e] and owners[e] <= {gi}]] = 0
    else:
        add_bike, drop_bike = list(base_today), list(base_plan)
        for e in gap_edges[gi]:
            add_bike[e] = True
            # An edge stays ridden if today's network or another plan block covers it.
            if not base_today[e] and owners[e] <= {gi}:
                drop_bike[e] = False
    target = TARGET_MIN * 60 + 1e-6
    add = drop = 0
    for bi, lvl in W["affected"].get(gi, ()):
        b = blocks[bi]
        n = b[W["band_of"][lvl]]
        wb, hb = W["wb"][bi], W["tb"][bi]
        if exact_best(net, add_bike, levels[lvl], bi, b["ends"], wb, target, hb):
            add += n
        if not exact_best(net, drop_bike, levels[lvl], bi, b["ends"], wb, target, hb):
            drop += n
    return gi, add, drop


def pool_map(fn, jobs, workers, label, t0):
    out = []
    if workers > 1:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(fn, jobs, chunksize=4)):
                out.append(r)
                if i % 500 == 0:
                    print("    %s %d/%d (%.0fs)" % (label, i, len(jobs), time.time() - t0), flush=True)
    else:
        out = [fn(j) for j in jobs]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help="parallel workers, at most MAX_WORKERS (5)")
    ap.add_argument("--no-cache", action="store_true", help="rebuild the walk network, not load .cache/walknet/")
    ap.add_argument("--no-gaps", action="store_true", help="skip the gap ranking")
    ap.add_argument("--sample", type=int, metavar="N",
                    help="run on N evenly spaced blocks only, for profiling and equivalence tests (use with --out)")
    ap.add_argument("--out", default=OUT, help="output directory (default out/school-travel)")
    ap.add_argument("--pure", action="store_true", help="use the pure-Python searches, not lib/rcsp.c")
    a = ap.parse_args()
    a.workers = max(1, min(a.workers, MAX_WORKERS))
    FAST["on"] = not a.pure and rcsp.available()
    print("  searches: %s" % ("compiled (lib/rcsp.c)" if FAST["on"] else "pure Python"))
    t0 = time.time()
    net = Net(cache=not a.no_cache)
    G = net.G
    print("  walk network: %s (%.1fs)" % (netcache.STATS.get("source"), time.time() - t0))

    # Blocks with school-age children.
    kids = {r["geoid"]: r for r in read(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    pts = {r["geoid"]: r for r in read(ROOT, "data", "extract", "census-blocks", "2020.json")["records"]}
    blocks = []
    for gid in sorted(kids):
        k = kids[gid]
        if k["a5_9"] + k["a10_14"] + k["a15_17"] == 0:
            continue
        p = pts[gid]
        blocks.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "a5_9": k["a5_9"], "a10_14": k["a10_14"],
                       "a15_17": k["a15_17"], "ends": net.ends(p["lon"], p["lat"])})
    if a.sample:
        step = max(1, len(blocks) // a.sample)
        blocks = blocks[::step][:a.sample]
    unjoined = [b["geoid"] for b in blocks if not b["ends"]]
    print("  %d blocks with children 5-17 (%d children); %d with no join to the network" % (
        len(blocks), sum(b["a5_9"] + b["a10_14"] + b["a15_17"] for b in blocks), len(unjoined)))

    schools, dropped, priv = load_schools()
    for s in schools:
        s["ends"] = net.ends(s["lon"], s["lat"])
    print("  %d schools; left out: %s" % (len(schools), dict(dropped)))

    today_lines, plan_lines, plan_meta = all_ages_lines()
    line_edges, weak = edges_of(net, today_lines + plan_lines, cache=net.cache)
    today_keys = {k for k, _ in today_lines}
    n_e = len(G.eu)
    bike_today = [False] * n_e
    for k, _ in today_lines:
        for e in line_edges.get(k, ()):
            bike_today[e] = True
    bike_plan = list(bike_today)
    for k, _ in plan_lines:
        for e in line_edges.get(k, ()):
            bike_plan[e] = True
    no_bike = [False] * n_e

    def line_len(lines):
        return sum(math.hypot(*(p - q for p, q in zip(walknet.xy(*a1), walknet.xy(*b1))))
                   for _, pts_ in lines for a1, b1 in zip(pts_, pts_[1:]))
    rid = lambda bk: sum(net.L[e] for e in range(n_e) if bk[e])  # noqa: E731
    unmatched = sorted(k for k, _ in today_lines + plan_lines if not line_edges.get(k))
    print("  all-ages lines: today %d (%.0f km of line, %.0f km of walk edges ridden); plan built adds %d plan blocks "
          "(%.0f km ridden); %d lines matched at the %g m fallback; %d lines matched no edge" % (
              len(today_lines), line_len(today_lines) / 1000, rid(bike_today) / 1000, len(plan_lines),
              rid(bike_plan) / 1000, len(weak), LINE_FALLBACK_M, len(unmatched)))

    levels = {}
    for lvl in LEVEL_SERVES:
        levels[lvl] = Level(net, lvl, [s for s in schools if lvl in s["levels"]], blocks)
        # The same level, public schools only (shares each school's walks).
        levels[lvl + "/public"] = Level(net, lvl, [s for s in schools if lvl in s["levels"] and not s["private"]], blocks)
        far = sum(1 for bi in range(len(blocks)) if not any(bi in w for w in levels[lvl].walk))
        print("  %s: %d schools; %d blocks beyond %d m of every one (%.0fs)" % (
            lvl, len(levels[lvl].schools), far, WALK_CUTOFF_M, time.time() - t0))

    nets = {"walk": no_bike, "today": bike_today, "plan": bike_plan}
    res = {}
    lifted = collections.Counter()
    for nk, bk in nets.items():
        for key in levels:
            res[(nk, key)] = level_times(net, bk, levels[key], blocks)
        print("  %s network timed (%.0fs)" % (nk, time.time() - t0))
    target_s = TARGET_MIN * 60

    def over(nk, suffix="", none_only=False):
        out = {}
        for band, lvl, label in BANDS:
            r = res[(nk, lvl + suffix)]
            out[label] = sum(b[band] for b, x in zip(blocks, r)
                             if x is None or (not none_only and x[0] > target_s + 1e-9))
        out["5-17"] = sum(out[l] for _, _, l in BANDS)
        return out
    total = {label: sum(b[band] for b in blocks) for band, _, label in BANDS}
    total["5-17"] = sum(total.values())

    # SFUSD elementary attendance areas: ages 5-9, to the area's own school.
    areas, area_src = attendance_areas()
    elem = levels["elementary"]
    area_rows, block_area = [], {}
    for ai, ar in enumerate(areas):
        si, sc = match_area_school(ar, elem.schools)
        area_rows.append({"area": ar["name"], "school": elem.schools[si]["name"] if si is not None else None,
                          "match_score": round(sc, 2), "_si": si})
    for bi, b in enumerate(blocks):
        hit = [ai for ai, ar in enumerate(areas) if in_poly(b["lon"], b["lat"], ar["polys"])]
        if hit:
            block_area[bi] = hit[0]
    area_res = {}
    by_school = collections.defaultdict(list)
    for bi, ai in block_area.items():
        si = area_rows[ai]["_si"]
        if si is not None:
            by_school[si].append(bi)
    for nk in ("walk", "today", "plan"):
        bk = nets[nk]
        out = {}
        for si, bis in by_school.items():
            one = Level.__new__(Level)
            one.schools = [elem.schools[si]]
            one.seeds = [(node, c, along, e, 0) for node, c, along, e in elem.schools[si]["ends"]]
            one.walk = [elem.walk[si]]
            sub = [blocks[bi] for bi in bis]
            # level_times indexes walk by block position: map through a view.
            one.walk = [{j: elem.walk[si][bi] for j, bi in enumerate(bis) if bi in elem.walk[si]}]
            r = level_times(net, bk, one, sub, stop_early=True)
            for j, bi in enumerate(bis):
                out[bi] = r[j]
        area_res[nk] = out
    in_area_kids = sum(blocks[bi]["a5_9"] for bi in block_area if area_rows[block_area[bi]]["_si"] is not None)
    print("  attendance areas: %d; blocks in one %d; children 5-9 in them %d (%.0fs)" % (
        len(areas), len(block_area), in_area_kids, time.time() - t0))
    for r in area_rows:
        print("    area %-40s -> %s (%.2f)" % (r["area"], r["school"], r["match_score"]))

    # Pass 2: the exact search, for every block, level and network.
    area_level = {}
    for bi, ai in block_area.items():
        si = area_rows[ai]["_si"]
        if si is not None:
            one = Level.__new__(Level)
            one.schools, one.walk = [elem.schools[si]], [elem.walk[si]]
            area_level[bi] = one
    W.update(net=net, blocks=blocks, levels=levels, nets=nets, res=res, area_level=area_level, area_res=area_res)
    improved = collections.Counter()
    gain = collections.defaultdict(float)
    for bi, out in pool_map(refine_block, list(range(len(blocks))), a.workers, "exact", t0):
        for (k1, k2), ex in out.items():
            t, si, m = ex
            if k1 == "area":
                old = area_res[k2][bi]
                area_res[k2][bi] = (t, 0, m, t < m * RW - 1e-6)
                key = "attendance " + k2
            else:
                old = res[(k1, k2)][bi]
                res[(k1, k2)][bi] = (t, si, m, t < m * RW - 1e-6)
                key = "%s %s" % (k1, k2)
            improved[key] += 1
            gain[key] = max(gain[key], old[0] - t)
    print("  exact pass improved: %s (%.0fs)" % (dict(improved), time.time() - t0))
    # Each network contains the one before it, so its time can be no slower;
    # count any block where that fails (it would mean a search fault).
    # Pass 1's times over EXACT_MAX_MIN are upper bounds, so this can happen
    # only above it; below it pass 2 is exact, and a slower time there is a fault.
    lifted = collections.Counter()
    for small, big in (("walk", "today"), ("today", "plan")):
        for key in levels:
            rs, rb = res[(small, key)], res[(big, key)]
            for bi in range(len(blocks)):
                if rs[bi] is not None and (rb[bi] is None or rs[bi][0] < rb[bi][0] - 1e-6):
                    assert rs[bi][0] > EXACT_MAX_MIN * 60, "block %s %s: %s %.1fs under EXACT_MAX_MIN but %s slower" % (
                        blocks[bi]["geoid"], key, small, rs[bi][0], big)
                    rb[bi] = rs[bi]
                    lifted["%s %s" % (big, key)] += 1
    print("  blocks slower on the larger network (kept the smaller's route): %s" % dict(lifted))
    counts = {nk: over(nk) for nk in nets}
    counts_public = {nk: over(nk, "/public") for nk in nets}
    no_route = over("plan", none_only=True)
    for nk in nets:
        print("  %-5s children over %g min: %s of %s; public schools only %s" % (
            nk, TARGET_MIN, counts[nk], total, counts_public[nk]))
    print("  of which with no walking route to any school: %s" % no_route)
    area_counts = {}
    for nk in area_res:
        area_counts[nk] = sum(blocks[bi]["a5_9"] for bi, r in area_res[nk].items() if r is None or r[0] > target_s + 1e-9)
    print("  attendance areas, children 5-9 over %g min: %s" % (TARGET_MIN, area_counts))
    validation = {"exact_improved_block_levels": dict(sorted(improved.items())),
                  "largest_improvement_s": {k: round(v, 1) for k, v in sorted(gain.items())},
                  "slower_on_larger_network": dict(sorted(lifted.items()))}

    # Gaps.
    gaps_out = None
    if not a.no_gaps:
        groups = group_gaps(plan_lines, plan_meta, today_keys)
        gap_edges = []
        for g in groups:
            es = set()
            for k in g:
                es |= line_edges.get(k, set())
            gap_edges.append(es)
        owners = [set() for _ in range(n_e)]
        for gi, es in enumerate(gap_edges):
            for e in es:
                owners[e].add(gi)
        in_gap = {k for g in groups for k in g}
        for k, _ in plan_lines:
            if k not in in_gap:
                for e in line_edges.get(k, ()):
                    owners[e].add(-1)  # a plan block already all-ages today
        band_of = {lvl: band for band, lvl, _ in BANDS}

        def under(nk, lvl, bi):
            r = res[(nk, lvl)][bi]
            return r is not None and r[0] <= target_s + 1e-9
        cand = [(bi, lvl) for _, lvl, _ in BANDS for bi in range(len(blocks))
                if blocks[bi][band_of[lvl]] and not under("today", lvl, bi) and under("plan", lvl, bi)]
        cand_blocks = sorted({bi for bi, _ in cand})
        print("  gaps: %d; block-levels that can change: %d on %d blocks (%.0fs)" % (
            len(groups), len(cand), len(cand_blocks), time.time() - t0))
        # Per candidate block: shortest walk to every node, and the uncapped time
        # on the finished plan's network, a lower bound for both gap searches
        # since each runs on a network the plan's contains.
        if net.fast is None:
            wbA = {bi: walk_array(net, blocks[bi]["ends"]) for bi in cand_blocks}
            tbA = {bi: time_array(net, bike_plan, blocks[bi]["ends"]) for bi in cand_blocks}
        else:
            # Both are read only by the searches and filters below, which drop any
            # node whose walk exceeds the largest cap they use (no school past the
            # target at riding speed is tried) or whose time exceeds the target.
            # So the searches stop there, with a margin: a node past a stop gets
            # INF, and its true value would have been dropped by the same test.
            wb_stop = DETOUR * (target_s + 1e-6) / RB + CAP_TOL + 1.0
            t_stop = target_s + 10.0
            bplan = net.bike_array(bike_plan)
            wbA = {bi: net.fast.walk([x[0] for x in blocks[bi]["ends"]], [c + al for _n, c, al, _e in blocks[bi]["ends"]],
                                     min(WALK_CUTOFF_M, wb_stop)).astype(numpy.float32) for bi in cand_blocks}
            tbA = {bi: net.fast.time(bplan, RW, RB, fast_ends(blocks[bi]["ends"]), t_stop).astype(numpy.float32)
                   for bi in cand_blocks}
        print("  per-block walks and plan times (%.0fs)" % (time.time() - t0))
        wsA, tsA = {}, {}
        pair_nodes, pair_gaps = [], []
        for gi, es in enumerate(gap_edges):
            for e in es:
                for nd in (G.eu[e], G.ev[e]):
                    pair_nodes.append(nd)
                    pair_gaps.append(gi)
        pair_nodes = numpy.array(pair_nodes, dtype=numpy.int64)
        pair_gaps = numpy.array(pair_gaps, dtype=numpy.int64)
        if net.fast is not None:
            # The filter reads these arrays only at the gaps' nodes, elementwise.
            wbP = {bi: a_[pair_nodes] for bi, a_ in wbA.items()}
            tbP = {bi: a_[pair_nodes] for bi, a_ in tbA.items()}
        affected = collections.defaultdict(list)
        for bi, lvl in cand:
            L = levels[lvl]
            hits = set()
            for si, sc in enumerate(L.schools):
                Ws = L.walk[si].get(bi)
                if Ws is None or Ws * RB > target_s:
                    continue
                if net.fast is not None:
                    if id(sc) not in wsA:
                        wsA[id(sc)] = net.fast.walk([x[0] for x in sc["ends"]], [c + al for _n, c, al, _e in sc["ends"]],
                                                    min(WALK_CUTOFF_M, wb_stop)).astype(numpy.float32)[pair_nodes]
                        tsA[id(sc)] = net.fast.time(bplan, RW, RB, fast_ends(sc["ends"]), t_stop).astype(numpy.float32)[pair_nodes]
                    inside = ((wbP[bi] + wsA[id(sc)]) <= DETOUR * Ws + CAP_TOL) & ((tbP[bi] + tsA[id(sc)]) <= target_s + 1e-3)
                    hits.update(pair_gaps[inside].tolist())
                    continue
                if id(sc) not in wsA:
                    wsA[id(sc)] = walk_array(net, sc["ends"])
                    tsA[id(sc)] = time_array(net, bike_plan, sc["ends"])
                # Inside the detour ellipse, and on a route that could make the
                # target even on the whole plan's network.
                inside = ((wbA[bi] + wsA[id(sc)]) <= DETOUR * Ws + CAP_TOL) & ((tbA[bi] + tsA[id(sc)]) <= target_s + 1e-3)
                hits.update(pair_gaps[inside[pair_nodes]].tolist())
            for gi in hits:
                affected[gi].append((bi, lvl))
        print("  detour ellipses: %d gaps touch at least one; %d gap/block-level pairs to search (%.0fs)" % (
            len(affected), sum(len(v) for v in affected.values()), time.time() - t0))
        W.update(gap_edges=gap_edges, plan_edge_owners=owners, today=bike_today, plan=bike_plan, affected=dict(affected),
                 band_of=band_of, wb=wbA, tb=tbA)
        out = {gi: (add, drop) for gi, add, drop in pool_map(gap_eval, sorted(affected), a.workers, "gaps", t0)}
        rows = []
        for gi, g in enumerate(groups):
            gset = set(g)
            meta = [plan_meta[k] for k in g]
            m = sum(line_len([(k, pts_)]) for k, pts_ in plan_lines if k in gset)
            add, drop = out.get(gi, (0, 0))
            xs = [walknet.xy(*p) for k, pts_ in plan_lines if k in gset for p in pts_]
            cx = sum(x for x, _ in xs) / len(xs)
            cy = sum(y for _, y in xs) / len(xs)
            lon = math.degrees(cx / (math.cos(walknet.LAT0) * walknet.EARTH))
            lat = math.degrees(cy / walknet.EARTH)
            rows.append({"street": meta[0]["street"], "facilities": sorted({x["facility"] for x in meta}),
                         "blocks": len(g), "cnns": [x["cnn"] for x in meta], "miles": round(m / 1609.344, 2),
                         "children_brought_under_alone": add, "children_lost_if_left_out": drop,
                         "centre": [round(lon, 5), round(lat, 5)], "edges": len(gap_edges[gi])})
        rows.sort(key=lambda r: (-r["children_brought_under_alone"], -r["children_lost_if_left_out"], r["street"], r["cnns"][0]))
        gaps_out = {"count": len(rows), "no_edges": sum(1 for r in rows if not r["edges"]),
                    "block_levels_that_can_change": len(cand), "children_that_can_change": sum(blocks[bi][band_of[l]] for bi, l in cand),
                    "rows": rows}
        for r in rows[:15]:
            print("    %-24s %3d blocks %5.2f mi  +%d under alone, -%d if left out" % (
                r["street"], r["blocks"], r["miles"], r["children_brought_under_alone"], r["children_lost_if_left_out"]))

    # Write.
    def cell(r):
        # Rounded up to 0.1 minute, so a printed 15.0 is at or under the target
        # and anything over it prints above 15.0, as the counts class it.
        return None if r is None else math.ceil(r[0] / 6.0 - 1e-9) / 10.0

    school_ix = {id(s): i for i, s in enumerate(schools)}

    def sch(lvl, r):
        return None if r is None else school_ix[id(levels[lvl].schools[r[1]])]
    rows_out = []
    for bi, b in enumerate(blocks):
        row = {"geoid": b["geoid"], "lon": round(b["lon"], 5), "lat": round(b["lat"], 5),
               "a5_9": b["a5_9"], "a10_14": b["a10_14"], "a15_17": b["a15_17"]}
        for _, lvl, _ in BANDS:
            row[lvl] = {nk: cell(res[(nk, lvl)][bi]) for nk in nets}
            row[lvl]["school_today"] = sch(lvl, res[("today", lvl)][bi])
            row[lvl]["school_plan"] = sch(lvl, res[("plan", lvl)][bi])
            row[lvl]["public"] = {nk: cell(res[(nk, lvl + "/public")][bi]) for nk in nets}
            row[lvl]["public"]["school_today"] = sch(lvl + "/public", res[("today", lvl + "/public")][bi])
            row[lvl]["public"]["school_plan"] = sch(lvl + "/public", res[("plan", lvl + "/public")][bi])
        if bi in block_area and area_rows[block_area[bi]]["_si"] is not None:
            row["attendance"] = {"area": area_rows[block_area[bi]]["area"], **{nk: cell(area_res[nk].get(bi)) for nk in nets}}
        rows_out.append(row)
    G_meta = {"source": "OpenStreetMap via Overpass (tools/travel/osm-walk-network.py)", "osm_base": G.osm_base,
              "nodes": len(G.x), "edges": n_e}
    summary = {
        "target_minutes": TARGET_MIN, "exact_max_minutes": EXACT_MAX_MIN, "walk_mph": WALK_MPH, "ride_mph": RIDE_MPH, "detour_cap": DETOUR,
        "children": total, "over_target": counts, "over_target_public_schools_only": counts_public,
        "no_walking_route_to_any_school": no_route,
        "attendance_area": {"areas": len(areas), "areas_matched": sum(1 for r in area_rows if r["_si"] is not None),
                            "children_5_9_in_areas": in_area_kids, "over_target": area_counts,
                            "matches": [{k: v for k, v in r.items() if k != "_si"} for r in area_rows]},
        "schools": {"counted": len(schools), "by_level": {l: len(levels[l].schools) for l in levels},
                    "left_out": dict(dropped),
                    "list": [{k: s[k] for k in ("name", "private", "grades", "levels", "soc")} for s in schools]},
        "network": {"walk": G_meta, "today_lines": len(today_lines), "plan_lines": len(plan_lines),
                    "ridden_km": {"today": round(rid(bike_today) / 1000, 1), "plan": round(rid(bike_plan) / 1000, 1)},
                    "lines_matched_at_fallback": len(weak), "lines_matching_no_edge": unmatched},
        "method": {"edge_snap_m": EDGE_SNAP_M, "edge_angle_deg": EDGE_ANGLE_DEG, "line_fallback_m": LINE_FALLBACK_M,
                   "lambdas": LAMBDAS, "walk_cutoff_m": WALK_CUTOFF_M, "blocks_unjoined": unjoined},
        "validation": validation,
        "gaps": gaps_out,
        "sources": {
            "children": {"source": "Census 2020 DHC table P12, blocks", "extract": "data/extract/census-dhc/p12-blocks.json",
                         "url": "https://data.census.gov/table/DECENNIALDHC2020.P12?g=050XX00US06075$1000000"},
            "blocks": "data/extract/census-blocks/2020.json (DataSF p2fw-hsrv) and outlines-2020.json (TIGERweb)",
            "schools": "site/data/bike-history/reach.json (CDE directory and DataSF 7e7j-59qk), grades from CDE and DataSF",
            "private_schools_queried": priv.fetched_on.isoformat(),
            "attendance_areas": {"dataset": "https://data.sfgov.org/d/" + ATTENDANCE_ID, "queried": area_src.fetched_on.isoformat()},
            "all_ages_today": "site/data/bike-history/segments.json and components.json (latest year)",
            "plan": "site/data/north-star/traced.geojson and status.json",
        },
    }
    os.makedirs(a.out, exist_ok=True)
    stable.write_json(os.path.join(a.out, "blocks.json"), {"note": "Minutes to the nearest school of each level (exact up to 30 minutes; above it, the time of a real route, which the fastest may beat but not below 30): walk = no bikeway ridden; today; plan = the North Star network built. None: no route within the search. school_today / school_plan index summary.json's schools.list.", "blocks": rows_out}, separators=(",", ":"))
    stable.write_json(os.path.join(a.out, "summary.json"), summary, indent=1)
    print("  wrote %s (%.0fs)" % (os.path.relpath(a.out, ROOT), time.time() - t0))


if __name__ == "__main__":
    main()
