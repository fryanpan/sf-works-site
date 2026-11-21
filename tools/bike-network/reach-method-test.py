#!/usr/bin/env python3
"""Tests which change of method brings our residents-within-reach share to the Biking and Rolling Plan's printed 80%: calming on Class III, dropping Class III, or measuring along streets.

Bryan chose "Match the method" on 2026-09-23 after asking why the overview's
86% for 2024 does not match the plan's 80% (printed p. 24; Appendix G, Toole
Design's connectivity memo of 2024-02-13). This script recomputes the 2024
share, and the latest year's, under three all-ages definitions and two ways
of measuring a quarter mile, and writes out/reach-method/reach-method.json.

Inputs are the history script's own outputs, so the baseline cell reproduces
the overview's figure: site/data/bike-history/segments.json (each block's
class by year, its 2023 Draft Bike Comfort Index score and its line) and
reach.json (each census block's interior point and its population on the
2020-2024 American Community Survey basis, which is the 2024 basis).

Definitions:
  plan      the overview's: Class I, IV and Slow Streets, plus Class II and III
            where the comfort score is over 80 (the calming condition on Class
            III cannot be applied, because no dataset records calming)
  calmed-III  the plan's written test with a proxy for its calming condition:
            a Class III route counts when its score is over 80 and the city
            records traffic calming built on it by that year -- a mid-block
            measure on the block (abhw-ffzx) or an intersection device at
            either end (bp3t-bd4t), status Complete or Existing
  no-III    the same without any Class III route
  strict    Class I, IV and Slow Streets only

Distances, both a quarter mile (402 m):
  straight  as the bird flies from the census block's interior point to the
            nearest qualifying line, as the overview measures
  network   along the walkable street network: straight to the nearest
            walkable centerline (or any within 5 m of it), then along centerlines to the nearest street
            corner within 20 m of a qualifying line, or 0 more when the
            street reached is itself a qualifying block. Walkable is every
            active centerline except freeways and paper streets, from DataSF
            street centerlines (3psu-pn9h). Off-street paths join the network
            only where they pass within 20 m of a street corner.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import datetime as dt
import heapq
import json
import math
import os
import sys

import sfdata  # noqa: E402  (lib/, on the path through lib/paths.py)

ROOT = paths.ROOT
BIKE = os.path.join(ROOT, "site", "data", "bike-history")
OUT = os.path.join(ROOT, "out", "reach-method", "reach-method.json")
QUARTER = 402.336
SNAP = 20.0
TIE = 5.0
PLAN_SHARE_2024 = 0.80
LAT0 = math.radians(37.76)
R = 6371008.8
NOT_WALKABLE = {"FREEWAYS", "PAPER", "PAPER_FWYS", "PAPER_WATER"}


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * R, math.radians(lat) * R)


def seg_proj(px, py, ax, ay, bx, by):
    """(distance, t in 0..1) from a point to a segment."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


class Grid(object):
    """Segments bucketed in square cells, for nearest-segment queries."""

    def __init__(self, cell):
        self.cell = cell
        self.cells = collections.defaultdict(list)

    def add(self, item, a, b):
        c = self.cell
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for i in range(int(x0 // c), int(x1 // c) + 1):
            for j in range(int(y0 // c), int(y1 // c) + 1):
                self.cells[(i, j)].append((item, a, b))

    def near(self, p, radius):
        c, r = self.cell, int(math.ceil(radius / self.cell))
        i0, j0 = int(p[0] // c), int(p[1] // c)
        seen = set()
        for i in range(i0 - r, i0 + r + 1):
            for j in range(j0 - r, j0 + r + 1):
                for e in self.cells.get((i, j), ()):
                    k = id(e)
                    if k not in seen:
                        seen.add(k)
                        yield e


def qualifies(defn, code, bci, calmed=False):
    if code in ("1", "4", "S"):
        return True
    if defn == "strict":
        return False
    calm = bci is not None and bci > 80
    if code == "2":
        return calm
    if code == "3":
        return calm and (defn == "plan" or (defn == "calmed-III" and calmed))
    return False


def main():
    seg = json.load(open(os.path.join(BIKE, "segments.json")))
    years = seg["years"]
    reach = json.load(open(os.path.join(BIKE, "reach.json")))["blocks"]
    col = {c: i for i, c in enumerate(reach["columns"])}
    blocks = [(xy(r[col["lon"]], r[col["lat"]]), r[col["pop_latest"]]) for r in reach["rows"] if r[col["pop_latest"]]]
    total = sum(p for _, p in blocks)

    cl = sfdata.fetch("3psu-pn9h")
    edges = []  # (cnn, u, v, pts, length)
    node_xy = {}
    for r in cl.rows:
        if not r.get("active") or r.get("layer") in NOT_WALKABLE or not r.get("line"):
            continue
        pts = [xy(*c) for c in r["line"]["coordinates"]]
        u, v = r.get("f_node_cnn"), r.get("t_node_cnn")
        if not u or not v:
            continue
        node_xy.setdefault(u, pts[0])
        node_xy.setdefault(v, pts[-1])
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        edges.append((r["cnn"], u, v, pts, length))
    ends = {r["cnn"]: (str(r.get("f_node_cnn") or "").replace(".0", ""), str(r.get("t_node_cnn") or "").replace(".0", ""))
            for r in cl.rows}
    mid = sfdata.fetch("abhw-ffzx")
    node = sfdata.fetch("bp3t-bd4t")

    def built_by(r, Y):
        if (r.get("current_status") or "") not in ("Complete", "Existing"):
            return False
        try:
            y = int(float(r.get("install_yr") or 0))
        except ValueError:  # the file writes a missing year as "<Null>"
            y = 0
        if 0 < y < 100:  # one row writes 2024 as "24"
            y += 2000
        return y == 0 or y <= Y  # an undated device counts; the file dates few of them

    def calmed_cnns(Y):
        blocks_ = {str(r["cnn"]) for r in mid.rows if r.get("cnn") and built_by(r, Y)}
        nodes_ = {str(r["cnn"]).replace(".0", "") for r in node.rows if r.get("cnn") and built_by(r, Y)}
        return blocks_ | {c for c, (f, t) in ends.items() if f in nodes_ or t in nodes_}

    adj = collections.defaultdict(list)
    street = Grid(100.0)
    for k, (cnn, u, v, pts, length) in enumerate(edges):
        adj[u].append((v, length))
        adj[v].append((u, length))
        for a, b in zip(pts, pts[1:]):
            street.add(k, a, b)

    def run(Y):
        yi = years.index(Y)
        out = {}
        calmed = calmed_cnns(Y)
        for defn in ("plan", "calmed-III", "no-III", "strict"):
            lines = [s for s in seg["segments"] if qualifies(defn, s["y"][yi], s.get("bci"), str(s.get("cnn")) in calmed)]
            g = Grid(200.0)
            q_cnns = set()
            for s in lines:
                pts = [xy(*c) for c in s["pts"]]
                for a, b in zip(pts, pts[1:]):
                    g.add(None, a, b)
                if s.get("cnn"):
                    q_cnns.add(str(s["cnn"]))

            def near_line(p, radius):
                return min((seg_proj(p[0], p[1], a[0], a[1], b[0], b[1])[0] for _, a, b in g.near(p, radius)), default=math.inf)

            # Multi-source Dijkstra from every street corner on a qualifying line.
            dist = {}
            heap = []
            for n, p in node_xy.items():
                if near_line(p, SNAP) <= SNAP:
                    dist[n] = 0.0
                    heap.append((0.0, n))
            heapq.heapify(heap)
            while heap:
                d, n = heapq.heappop(heap)
                if d > dist.get(n, math.inf) or d > QUARTER:
                    continue
                for m, w in adj[n]:
                    nd = d + w
                    if nd < dist.get(m, math.inf) and nd <= QUARTER:
                        dist[m] = nd
                        heapq.heappush(heap, (nd, m))

            straight = network = 0.0
            pairs = []
            for p, pop in blocks:
                ds = near_line(p, QUARTER)
                if ds <= QUARTER:
                    straight += pop
                # The walk starts on the nearest street: every street piece
                # within TIE metres of the nearest one, so a point at a
                # corner may leave by either street. Starting from any street
                # in range would let the walk cut across blocks.
                cands = [(seg_proj(p[0], p[1], a[0], a[1], b[0], b[1]), k, a, b) for k, a, b in street.near(p, 200.0)]
                if not cands:
                    cands = [(seg_proj(p[0], p[1], a[0], a[1], b[0], b[1]), k, a, b) for k, a, b in street.near(p, QUARTER)]
                nearest = min((c[0][0] for c in cands), default=math.inf)
                best = math.inf
                for (access, t), k, a, b in cands:
                    if access > nearest + TIE:
                        continue
                    cnn, u, v, pts, length = edges[k]
                    if str(cnn) in q_cnns:
                        best = min(best, access)
                        continue
                    # offset of the snap point along the whole edge
                    along = 0.0
                    for c, e in zip(pts, pts[1:]):
                        if (c, e) == (a, b):
                            along += t * math.hypot(b[0] - a[0], b[1] - a[1])
                            break
                        along += math.hypot(e[0] - c[0], e[1] - c[1])
                    best = min(best, access + min(along + dist.get(u, math.inf), (length - along) + dist.get(v, math.inf)))
                if best <= QUARTER:
                    network += pop
                if ds <= QUARTER:
                    pairs.append((ds, best, pop))
            # How much longer the walk is than the straight line, for blocks the
            # straight line reaches: the check that the routing is doing work.
            walk = sorted(b / a for a, b, _ in pairs if a >= 50 and b < math.inf)
            shorter = sum(pop for a, b, pop in pairs if b < a - SNAP)
            out[defn] = {"lines": len(lines), "straight": round(straight / total, 4), "network": round(network / total, 4),
                         "walk_over_straight": {"median": round(walk[len(walk) // 2], 3), "p90": round(walk[int(len(walk) * 0.9)], 3)} if walk else None,
                         "residents_walk_shorter_by_more_than_snap": round(shorter)}
        return out

    result = {
        "generated": dt.date.today().isoformat(),
        "plan_share_2024": PLAN_SHARE_2024,
        "residents": total,
        "centerlines": {"id": "3psu-pn9h", "url": "https://data.sf.gov/d/3psu-pn9h", "fetched_on": str(cl.fetched_on), "walkable_edges": len(edges)},
        "quarter_mile_m": QUARTER,
        "calming": {"mid_block": {"id": "abhw-ffzx", "fetched_on": str(mid.fetched_on)},
                    "intersection": {"id": "bp3t-bd4t", "fetched_on": str(node.fetched_on)}},
        "years": {str(Y): run(Y) for Y in (2023, 2024, years[-1])},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(result, open(OUT, "w"), indent=1)
    for Y, r in result["years"].items():
        print(Y)
        for defn, v in r.items():
            print("  %-7s straight %5.1f%%  network %5.1f%%  (%d blocks)  walk/straight median %s p90 %s  shorter %d" % (
                defn, 100 * v["straight"], 100 * v["network"], v["lines"], v["walk_over_straight"]["median"], v["walk_over_straight"]["p90"], v["residents_walk_shorter_by_more_than_snap"]))
    print("wrote", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
