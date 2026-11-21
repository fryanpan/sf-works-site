#!/usr/bin/env python3
"""Which city blocks each SFMTA project sits on, from its published geometry.

    tools/projects/project-blocks.py     # → out/project-record/project-blocks.json

A hearing order names a place as a street and an extent: "Valencia Street,
from Cesar Chavez Street to Duboce Avenue", or "Post Street, north side, from
Baker Street to 88 feet easterly". streetindex.BlockIndex turns that into the
city's own block ids. For the same test to run on the OTHER side of the join,
each project needs its blocks too — and SFMTA publishes a project as a shape
on its ArcGIS layer, not as a block list.

So this walks every block of the centreline past every project's shape, bike
tag or not, and keeps the blocks that touch it. Every project, because the
Current Projects list takes any SFMTA project that touches biking or walking
infrastructure, and SFMTA's Bike tag misses some (Bryan, 2026-09-28: "We
should never miss an SFMTA project that has something to do with biking or
pedestrian infrastructure"). Scripts that want only bike projects filter on the
layer's own tag themselves. Three shapes, three tests, because the
layer mixes them: a point marks a block if it lies within 25 m of it; a line
marks the blocks it runs along, within 15 m; a polygon marks the blocks whose
midpoint it contains. The tolerances are metres on the ground, not degrees,
via the same flat projection tools/travel/osm-sfmta-compare.py uses at this
latitude.

The output is a measurement of geometry, not a claim about scope. A polygon
drawn as a project's study area marks every block in it, including the ones
the project never touched — which is why the join that reads this still asks
for the record to name the street as well.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
from streetindex import BlockIndex  # noqa: E402

ROOT = paths.ROOT
PROJECTS = os.path.join(ROOT, "out", "sfmta-projects", "projects.geojson")
OUT = os.path.join(ROOT, "out", "project-record", "project-blocks.json")

# Flat projection at San Francisco's latitude, as tools/travel/osm-sfmta-compare.py
# does it: metres per degree, so distances below are metres.
K_LAT = 111_320.0
K_LON = 111_320.0 * math.cos(math.radians(37.76))
POINT_M, LINE_M, RING_M = 25.0, 15.0, 10.0
CELL = 100.0


def proj(lon, lat):
    return (lon * K_LON, lat * K_LAT)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def inside(p, ring):
    """Ray cast: is projected point p inside the projected ring."""
    x, y, hit = p[0], p[1], False
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            hit = not hit
    return hit


class Grid:
    """Every block's segments on a metre grid, so a shape only meets its neighbours."""

    def __init__(self, idx):
        self.cells = collections.defaultdict(list)
        self.mid = {}
        for cnn, b in idx.blocks.items():
            pts = [proj(x, y) for x, y in b["line"]]
            if len(pts) < 2:
                continue
            self.mid[cnn] = pts[len(pts) // 2]
            for a, c in zip(pts, pts[1:]):
                for gx in range(int(min(a[0], c[0]) // CELL), int(max(a[0], c[0]) // CELL) + 1):
                    for gy in range(int(min(a[1], c[1]) // CELL), int(max(a[1], c[1]) // CELL) + 1):
                        self.cells[(gx, gy)].append((a, c, cnn))

    def near(self, p, tol):
        gx, gy = int(p[0] // CELL), int(p[1] // CELL)
        out = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a, c, cnn in self.cells.get((gx + dx, gy + dy), ()):
                    if seg_dist(p, a, c) <= tol:
                        out.add(cnn)
        return out

    def along(self, pts, tol):
        """Blocks within tol of a polyline: test its vertices and midpoints."""
        out = set()
        for a, c in zip(pts, pts[1:]):
            for p in (a, ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2), c):
                out |= self.near(p, tol)
        return out

    def within(self, ring):
        """Blocks whose midpoint a polygon contains, or that touch its edge."""
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        out = set()
        for cnn, m in self.mid.items():
            if min(xs) - RING_M <= m[0] <= max(xs) + RING_M and min(ys) - RING_M <= m[1] <= max(ys) + RING_M:
                if inside(m, ring):
                    out.add(cnn)
        return out | self.along(ring + ring[:1], RING_M)


def blocks_for(geom, grid):
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return grid.near(proj(*c), POINT_M), "point"
    if t == "LineString":
        return grid.along([proj(*p) for p in c], LINE_M), "line"
    if t == "MultiLineString":
        out = set()
        for ln in c:
            out |= grid.along([proj(*p) for p in ln], LINE_M)
        return out, "line"
    if t == "Polygon":
        out = set()
        for ring in c:
            out |= grid.within([proj(*p) for p in ring])
        return out, "polygon"
    return set(), "none"


def main():
    idx = BlockIndex()
    grid = Grid(idx)
    fc = json.load(open(PROJECTS))
    by_node = {}
    for f in fc["features"]:
        pr = f["properties"]
        if not f.get("geometry"):
            continue
        cnns, how = blocks_for(f["geometry"], grid)
        rec = by_node.setdefault(str(pr["node"]), {"name": pr.get("name"), "cnns": set(), "methods": set()})
        rec["cnns"] |= cnns
        rec["methods"].add(how)

    out = {}
    for node, r in by_node.items():
        streets = sorted({idx.blocks[c]["street"] for c in r["cnns"] if c in idx.blocks})
        out[node] = {"name": r["name"], "cnns": sorted(r["cnns"]),
                     "streets": streets, "methods": sorted(r["methods"])}

    sizes = sorted(len(v["cnns"]) for v in out.values())
    empty = sum(1 for s in sizes if s == 0)
    print(f"{len(out)} projects; blocks per project median {sizes[len(sizes)//2]}, "
          f"max {sizes[-1]}, {empty} with none")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stable.write_json(OUT, {"generated": dt.date.today().isoformat(),
                            "tolerancesM": {"point": POINT_M, "line": LINE_M, "ring": RING_M},
                            "projects": out}, end="", ensure_ascii=True, indent=1)
    print(f"→ {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
