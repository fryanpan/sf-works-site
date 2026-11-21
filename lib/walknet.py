#!/usr/bin/env python3
"""Walking distance along San Francisco's streets, stairways and paths from a point to the nearest of a set of lines.

A drop-in for the straight-line `Reach` in tools/bike-network/bike-network-history.py:
`WalkReach(lines, metres)` answers `within(lon, lat)` and `nearest(lon, lat)`
the same way, measured along the walk network tools/travel/osm-walk-network.py
fetches (OSMnx's walk filter plus cycle paths).

HOW A DISTANCE IS MEASURED.
  * The network is every OSM way in data/osm-cache/sf-walk.json, split at each
    of its nodes; an edge's length is the great-circle length of that piece.
  * A bikeway line is sampled every SAMPLE_M metres. Each sample attaches to
    every edge within SOURCE_SNAP_M of it (the street it runs on, and its
    sidewalks where those are mapped as their own ways), at the point on the
    edge nearest the sample. That point is where a walker reaches the bikeway.
    A sample with no edge that close (SFMTA draws some park and beach paths up
    to 60 m from where OpenStreetMap has them: the Great Highway, Lake
    Merced) attaches to its nearest edge within FALLBACK_SNAP_M instead, with
    the gap added to the distance.
  * One multi-source Dijkstra runs from every attachment of every line at
    once, stopping at CUTOFF_M, and keeps for each node its distance and the
    line it came from.
  * A point (a census block's interior point, a school, a branch) joins the
    network in a straight line at the nearest edge, or at any edge no more than
    TARGET_SLACK_M farther than that, whichever gives the shorter walk; the
    connector is added to its distance. So a census block leaves by whichever
    of its streets is best, not only by the one its interior point happens to
    sit nearest. Only edges in a connected piece of the network with at least
    MIN_COMPONENT nodes count: a driveway or courtyard path mapped with no link
    to a street would otherwise strand the block on it. On its edge the point
    walks either way to the edge's two nodes, or along the edge to an
    attachment on it.
  * A census block with an outline registered (use_census_outlines()) joins
    the network along its frontage instead: its outline is sampled every
    SAMPLE_M metres and every joinable edge within FRONTAGE_SNAP_M of a sample
    is a way out, with that gap as the connector. Census blocks are bounded by
    street centerlines, so a block facing a bikeway is at the bikeway (Bryan,
    2026-09-29: blocks "right on a bikeway don't show up
    as connected ... at 1 block"). A block whose outline meets no edge (one
    bounded by water or a park's edge) falls back to its interior point.

Distances above CUTOFF_M are not computed, so `distance()` returns None past it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import heapq
import json
import math
import os

ROOT = paths.ROOT
CACHE = os.path.join(ROOT, "data", "osm-cache", "sf-walk.json")
LAT0 = math.radians(37.76)
EARTH = 6371008.8
SAMPLE_M = 10.0
SOURCE_SNAP_M = 20.0
FALLBACK_SNAP_M = 60.0
TARGET_SLACK_M = 40.0
MIN_COMPONENT = 1000
FRONTAGE_SNAP_M = 15.0
CELL_M = 50.0
CUTOFF_M = 420.0  # just past a quarter mile (402.3 m), the largest distance the pages offer


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * EARTH, math.radians(lat) * EARTH)


class Graph(object):
    """The walk network, as flat arrays: node coordinates in metres, and edges (u, v, length)."""

    def __init__(self, path=CACHE):
        blob = json.load(open(path))
        self.osm_base = blob.get("osm3s", {}).get("timestamp_osm_base")
        coords = {}
        ways = []
        for e in blob["elements"]:
            if e["type"] == "node":
                coords[e["id"]] = (e["lon"], e["lat"])
            elif e["type"] == "way":
                ways.append(e)
        idx = {}
        self.x, self.y = [], []
        self.eu, self.ev, self.elen = [], [], []
        self.ehw = []  # each edge's OSM highway tag
        self.adj = []
        self.ways = len(ways)
        missing = 0
        for w in ways:
            nds = [n for n in w.get("nodes", ()) if n in coords]
            missing += len(w.get("nodes", ())) - len(nds)
            prev = None
            for n in nds:
                if n not in idx:
                    idx[n] = len(self.x)
                    px, py = xy(*coords[n])
                    self.x.append(px)
                    self.y.append(py)
                    self.adj.append([])
                i = idx[n]
                if prev is not None and prev != i:
                    L = math.hypot(self.x[i] - self.x[prev], self.y[i] - self.y[prev])
                    e = len(self.eu)
                    self.eu.append(prev)
                    self.ev.append(i)
                    self.elen.append(L)
                    self.ehw.append(w.get("tags", {}).get("highway"))
                    self.adj[prev].append((i, L))
                    self.adj[i].append((prev, L))
                prev = i
        self.missing_nodes = missing
        # Connected pieces; a point may join only a piece of MIN_COMPONENT nodes or more.
        comp = [-1] * len(self.x)
        sizes = []
        for s0 in range(len(self.x)):
            if comp[s0] >= 0:
                continue
            stack, comp[s0], n = [s0], len(sizes), 0
            while stack:
                u = stack.pop()
                n += 1
                for v, _ in self.adj[u]:
                    if comp[v] < 0:
                        comp[v] = len(sizes)
                        stack.append(v)
            sizes.append(n)
        self.component_sizes = sorted(sizes, reverse=True)
        self.joinable = [sizes[comp[u]] >= MIN_COMPONENT for u in self.eu]
        self.cells = collections.defaultdict(list)
        for e in range(len(self.eu)):
            u, v = self.eu[e], self.ev[e]
            x0, x1 = sorted((self.x[u], self.x[v]))
            y0, y1 = sorted((self.y[u], self.y[v]))
            for cx in range(int(x0 // CELL_M), int(x1 // CELL_M) + 1):
                for cy in range(int(y0 // CELL_M), int(y1 // CELL_M) + 1):
                    self.cells[(cx, cy)].append(e)
        self._snap = {}

    def _project(self, e, px, py):
        u, v = self.eu[e], self.ev[e]
        ax, ay, bx, by = self.x[u], self.y[u], self.x[v], self.y[v]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2)) if L2 else 0.0
        return t, math.hypot(ax + t * dx - px, ay + t * dy - py)

    def edges_near(self, px, py, r):
        """[(edge, t, metres)] for every edge within r metres of (px, py)."""
        out, seen = [], set()
        for cx in range(int((px - r) // CELL_M), int((px + r) // CELL_M) + 1):
            for cy in range(int((py - r) // CELL_M), int((py + r) // CELL_M) + 1):
                for e in self.cells.get((cx, cy), ()):
                    if e in seen:
                        continue
                    seen.add(e)
                    t, d = self._project(e, px, py)
                    if d <= r:
                        out.append((e, t, d))
        return out

    def snap(self, lon, lat):
        """[(edge, t, connector metres)]: where a point joins the network; cached.

        With an outline registered for the point, every joinable edge along the
        outline; otherwise the nearest joinable edge and every one within
        TARGET_SLACK_M of it."""
        k = (lon, lat)
        if k in self._snap:
            return self._snap[k]
        rings = OUTLINES.get((round(lon, 5), round(lat, 5)))
        if rings:
            best = {}
            for ring in rings:
                for px, py in samples(ring):
                    for e, t, d in self.edges_near(px, py, FRONTAGE_SNAP_M):
                        if not self.joinable[e]:
                            continue
                        # Per edge: the closest join, and the joins nearest each end.
                        cur = best.setdefault(e, [])
                        cur.append((t, d))
            out = []
            for e, ts in best.items():
                keep = {min(ts, key=lambda a: a[1]), min(ts, key=lambda a: a[0]), max(ts, key=lambda a: a[0])}
                out.extend((e, t, d) for t, d in sorted(keep))
            if out:
                self._snap[k] = sorted(out, key=lambda c: (c[2], c[0], c[1]))
                return self._snap[k]
        px, py = xy(lon, lat)
        best = None
        r = CELL_M
        while True:
            cand = [c for c in self.edges_near(px, py, r) if self.joinable[c[0]]]
            if cand:
                best = min(c[2] for c in cand)
                if best + TARGET_SLACK_M <= r:
                    break
            if r > 5000:
                break
            r *= 2
        out = sorted((c for c in cand if c[2] <= best + TARGET_SLACK_M), key=lambda c: (c[2], c[0])) if best is not None else []
        self._snap[k] = out
        return out


_GRAPH = None
# (round(lon, 5), round(lat, 5)) of a census block's interior point -> its outline rings (lon/lat).
OUTLINES = {}


def use_census_outlines():
    """Register every 2010 and 2020 census block's outline under its interior point
    (data/extract/census-blocks/, from pipeline/sources/census-block-outlines.py)."""
    base = os.path.join(ROOT, "data", "extract", "census-blocks")
    for v in ("2010", "2020"):
        pts = {r["geoid"]: r for r in json.load(open(os.path.join(base, "%s.json" % v)))["records"]}
        for o in json.load(open(os.path.join(base, "outlines-%s.json" % v)))["records"]:
            p = pts.get(o["geoid"])
            if p and o["rings"]:
                OUTLINES[(round(p["lon"], 5), round(p["lat"], 5))] = o["rings"]
    if _GRAPH is not None:
        _GRAPH._snap.clear()
    return len(OUTLINES)


def graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = Graph()
    return _GRAPH


def samples(pts):
    """Points every SAMPLE_M metres along a lon/lat polyline, ends included, in metres."""
    P = [xy(lon, lat) for lon, lat in pts]
    out = [P[0]] if P else []
    for a, b in zip(P, P[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / SAMPLE_M)))
        for i in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
    return out


_ATTACH = {}


def attachments(G, pts):
    """[(edge, t, metres)] where a line meets the network; cached per line."""
    k = tuple(map(tuple, pts))
    if k not in _ATTACH:
        best = {}
        for px, py in samples(pts):
            near = G.edges_near(px, py, SOURCE_SNAP_M)
            if not near:
                far = G.edges_near(px, py, FALLBACK_SNAP_M)
                near = [min(far, key=lambda c: (c[2], c[0]))] if far else []
            for e, t, d in near:
                # Keep, per edge, the attachments that matter: the nearest to
                # each end and the shallowest.
                best.setdefault(e, []).append((t, d))
        out = []
        for e, ts in best.items():
            ts.sort()
            keep = {min(ts, key=lambda a: a[1] + a[0]), min(ts, key=lambda a: a[1] + (1 - a[0])), min(ts, key=lambda a: a[1])}
            out.extend((e, t, d) for t, d in sorted(keep))
        _ATTACH[k] = out
    return _ATTACH[k]


class WalkReach(object):
    """Is a point within `reach_m` walking metres of any line? Same interface as the straight-line Reach.

    `lines` is a list of lon/lat point lists, or of (key, points) pairs; the
    key is what nearest() hands back. Runs that share the same lines share one
    Dijkstra, so asking at three distances costs one search."""

    _memo = {}

    def __init__(self, lines, reach_m):
        assert reach_m <= CUTOFF_M, "reach %.1f m is past the search cutoff %.1f m" % (reach_m, CUTOFF_M)
        self.r = reach_m
        self.G = graph()
        items = [item if isinstance(item, tuple) else (None, item) for item in (lines or [])]
        sig = tuple((k, tuple(map(tuple, p))) for k, p in items)
        memo = WalkReach._memo
        if sig not in memo:
            if len(memo) > 64:
                memo.clear()
            memo[sig] = self._search(items)
        self.dist, self.origin, self.on_edge = memo[sig]

    def _search(self, items):
        G = self.G
        dist, origin = {}, {}
        on_edge = collections.defaultdict(list)
        heap = []
        for key, pts in items:
            if not pts or len(pts) < 1:
                continue
            for e, t, d in attachments(G, pts):
                on_edge[e].append((t, d, key))
                L = G.elen[e]
                for n, dd in ((G.eu[e], d + t * L), (G.ev[e], d + (1 - t) * L)):
                    if dd <= CUTOFF_M and dd < dist.get(n, float("inf")):
                        dist[n], origin[n] = dd, key
        heap = [(d, n) for n, d in dist.items()]
        heapq.heapify(heap)
        done = set()
        while heap:
            d, n = heapq.heappop(heap)
            if n in done or d > dist.get(n, float("inf")):
                continue
            done.add(n)
            for m, L in G.adj[n]:
                nd = d + L
                if nd <= CUTOFF_M and nd < dist.get(m, float("inf")):
                    dist[m], origin[m] = nd, origin[n]
                    heapq.heappush(heap, (nd, m))
        return dist, origin, dict(on_edge)

    def distance(self, lon, lat):
        """(metres, key) to the nearest line along the network, or (None, None) past the cutoff."""
        best, key = None, None
        for e, t, c in self.G.snap(lon, lat):
            L = self.G.elen[e]
            for n, along in ((self.G.eu[e], t * L), (self.G.ev[e], (1 - t) * L)):
                if n in self.dist:
                    d = c + along + self.dist[n]
                    if best is None or d < best:
                        best, key = d, self.origin[n]
            for ts, sd, k in self.on_edge.get(e, ()):
                d = c + abs(t - ts) * L + sd
                if best is None or d < best:
                    best, key = d, k
        if best is not None and best > CUTOFF_M:
            return None, None
        return best, key

    def within(self, lon, lat):
        d, _ = self.distance(lon, lat)
        return d is not None and d <= self.r

    def nearest(self, lon, lat):
        d, k = self.distance(lon, lat)
        return (k, d) if d is not None and d <= self.r else (None, None)
