#!/usr/bin/env python3
"""Population-weighted typical San Francisco block length, by census tract, for the bike explorer's "1 block" and "2 blocks".

    pipeline/sources/sf-block-length.py            # from the cached centerlines
    pipeline/sources/sf-block-length.py --refresh  # re-read DataSF 3psu-pn9h first

Bryan, 2026-09-29: use "~440 feet
for 1 block and ~880 feet for 2 blocks ... the average block size in SF if you
population weight across census tracts ... You can redo the calculation
yourself".

DEFINITION. One block is the distance along a street from one intersection to
the next, measured on the street centerline (DataSF 3psu-pn9h, active rows).
That is the distance a resident walks to "go one block". The city's centerline
rows break at more than intersections (a name change, a district line), so
rows are chained through every node that joins exactly two street rows; a
block runs between two nodes where three or more street rows meet. Dead-end
stubs (a node with one row) are not blocks and are left out. Only street
layers count: STREETS, STREETS_TI, STREETS_YBI, STREETS_HUNTERSP and
STREETS_PEDESTRI. Freeways, ramps, paper streets, park roads and private
streets are not blocks a resident walks.

WEIGHTING. Each block is placed in the census tract of the Census 2020 block
whose interior point is nearest its midpoint (DataSF p2fw-hsrv, mirrored in
data/extract/census-blocks/2020.json by tools/bike-network/bike-network-history.py). A
tract's typical block is the mean length of its blocks; the city figure is the
mean over tracts weighted by each tract's 2020 population. The median and a
resident-level weighting (each census block takes its own nearest blocks) are
printed beside it as checks.

Writes out/block-length/summary.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import json
import math
import os
import statistics
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import sfdata  # noqa: E402
from lib import stable  # noqa: E402

CENTERLINE = "3psu-pn9h"
LAYERS = {"STREETS", "STREETS_TI", "STREETS_YBI", "STREETS_HUNTERSP", "STREETS_PEDESTRI"}
FT = 0.3048
LAT0 = math.radians(37.76)
OUT = os.path.join(ROOT, "out", "block-length", "summary.json")
BRYAN_FT = 440


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * 6371008.8, math.radians(lat) * 6371008.8)


def length_m(coords):
    pts = [xy(*c[:2]) for c in coords]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def lines(geom):
    if geom["type"] == "LineString":
        return [geom["coordinates"]]
    return geom["coordinates"]


def point_at_half(coords):
    """The point halfway along a polyline, as (x, y) metres."""
    pts = [xy(*c[:2]) for c in coords]
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    run = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a, b)
        if run + d >= total / 2 and d > 0:
            t = (total / 2 - run) / d
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        run += d
    return pts[0]


def blocks_from(rows):
    """Chain centerline rows through two-way nodes; return [(length_m, (x, y) midpoint)]."""
    segs = []
    for r in rows:
        if r.get("layer") not in LAYERS or not r.get("line"):
            continue
        a, b = r.get("f_node_cnn"), r.get("t_node_cnn")
        if not a or not b:
            continue
        coords = [c for part in lines(r["line"]) for c in part]
        segs.append({"cnn": r["cnn"], "a": a, "b": b, "coords": coords, "len": length_m(coords)})
    deg = collections.Counter()
    at = collections.defaultdict(list)
    for i, s in enumerate(segs):
        deg[s["a"]] += 1
        deg[s["b"]] += 1
        at[s["a"]].append(i)
        at[s["b"]].append(i)
    used = set()
    out = []
    stats = collections.Counter()
    for i, s in enumerate(segs):
        if i in used:
            continue
        # Walk both ways from segment i through degree-2 nodes.
        chain = [i]
        used.add(i)
        ends = []
        for start in (s["a"], s["b"]):
            node, prev = start, i
            while deg[node] == 2:
                nxt = [j for j in at[node] if j != prev]
                if not nxt or nxt[0] in used:
                    break
                j = nxt[0]
                used.add(j)
                chain.append(j)
                node = segs[j]["b"] if segs[j]["a"] == node else segs[j]["a"]
                prev = j
            ends.append(node)
        total = sum(segs[j]["len"] for j in chain)
        if deg[ends[0]] < 3 or deg[ends[1]] < 3:
            stats["dead_end_or_loop"] += 1
            continue
        if ends[0] == ends[1]:
            stats["loop"] += 1
            continue
        # Midpoint: take the middle of the longest piece, close enough for tract placement.
        longest = max(chain, key=lambda j: segs[j]["len"])
        out.append((total, point_at_half(segs[longest]["coords"])))
        stats["blocks"] += 1
    stats["street_rows"] = len(segs)
    return out, stats


class Nearest:
    def __init__(self, pts, cell=400.0):
        self.cell = cell
        self.grid = collections.defaultdict(list)
        for i, (x, y) in enumerate(pts):
            self.grid[(int(x // cell), int(y // cell))].append(i)
        self.pts = pts

    def __call__(self, x, y):
        cx, cy = int(x // self.cell), int(y // self.cell)
        for r in range(0, 20):
            best, bd = None, None
            for gx in range(cx - r, cx + r + 1):
                for gy in range(cy - r, cy + r + 1):
                    for i in self.grid.get((gx, gy), ()):
                        d = math.dist((x, y), self.pts[i])
                        if bd is None or d < bd:
                            best, bd = i, d
            if best is not None and bd <= r * self.cell:
                return best
        return best


def weighted_median(pairs):
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    run = 0
    for v, w in pairs:
        run += w
        if run >= total / 2:
            return v


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    res = sfdata.fetch(CENTERLINE, select="cnn,layer,f_node_cnn,t_node_cnn,line",
                       where="active='true'", order=":id", refresh=args.refresh, floor=15000)
    blocks, bstats = blocks_from(res.rows)
    cb = json.load(open(os.path.join(ROOT, "data", "extract", "census-blocks", "2020.json")))
    cblocks = cb["records"]
    cpts = [xy(b["lon"], b["lat"]) for b in cblocks]
    near = Nearest(cpts)

    tract_len = collections.defaultdict(list)
    cblock_len = collections.defaultdict(list)
    for L, (x, y) in blocks:
        i = near(x, y)
        tract_len[cblocks[i]["geoid"][:11]].append(L)
        cblock_len[i].append(L)
    tract_pop = collections.Counter()
    for b in cblocks:
        tract_pop[b["geoid"][:11]] += b["pop"]

    # Tract-level: mean block length per tract, weighted by tract population.
    rows = []
    for t, ls in tract_len.items():
        rows.append({"tract": t, "pop": tract_pop[t], "blocks": len(ls),
                     "mean_ft": statistics.mean(ls) / FT, "median_ft": statistics.median(ls) / FT})
    rows.sort(key=lambda r: r["tract"])
    popsum = sum(r["pop"] for r in rows)
    pw_mean = sum(r["pop"] * r["mean_ft"] for r in rows) / popsum
    pw_median_of_tract_means = weighted_median([(r["mean_ft"], r["pop"]) for r in rows])
    pw_mean_of_tract_medians = sum(r["pop"] * r["median_ft"] for r in rows) / popsum
    unweighted = statistics.mean(L for L, _ in blocks) / FT
    unweighted_median = statistics.median(L for L, _ in blocks) / FT

    # Resident-level: every census block with people takes the mean of the
    # street blocks assigned to it or, if none, to its nearest neighbour that has some.
    have = [i for i in cblock_len]
    hnear = Nearest([cpts[i] for i in have])
    num = den = 0.0
    for i, b in enumerate(cblocks):
        if b["pop"] <= 0:
            continue
        j = i if i in cblock_len else have[hnear(*cpts[i])]
        num += b["pop"] * statistics.mean(cblock_len[j]) / FT
        den += b["pop"]
    resident_mean = num / den

    missing_pop = sum(p for t, p in tract_pop.items() if t not in tract_len)
    summary = {
        "question": "Population-weighted typical San Francisco block length (intersection to intersection, on the street centerline)",
        "centerline": {"dataset": CENTERLINE, "url": "https://data.sfgov.org/d/%s" % CENTERLINE,
                       "queried": res.fetched_on.isoformat(), "rows": len(res.rows), "layers": sorted(LAYERS)},
        "census": {"dataset": "p2fw-hsrv", "url": "https://data.sfgov.org/d/p2fw-hsrv", "fetched_on": cb.get("fetched_on"),
                   "blocks": len(cblocks), "population": sum(b["pop"] for b in cblocks)},
        "chain": dict(sorted(bstats.items())),
        "tracts": len(rows),
        "population_in_tracts_without_blocks": missing_pop,
        "pop_weighted_mean_ft": round(pw_mean),
        "pop_weighted_median_of_tract_means_ft": round(pw_median_of_tract_means),
        "pop_weighted_mean_of_tract_medians_ft": round(pw_mean_of_tract_medians),
        "resident_weighted_mean_ft": round(resident_mean),
        "unweighted_mean_ft": round(unweighted),
        "unweighted_median_ft": round(unweighted_median),
        "bryan_ft": BRYAN_FT,
        "difference_from_bryan_pct": round(100 * (pw_mean - BRYAN_FT) / BRYAN_FT, 1),
        "by_tract": [{k: (round(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rows],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stable.write_json(OUT, summary)
    for k, v in summary.items():
        if k != "by_tract":
            print("%s: %s" % (k, v))


if __name__ == "__main__":
    main()
