#!/usr/bin/env python3
"""Check the transportation pages' map geometry against audit criteria E1-E3; exit 1 on any failure.

    python3 pipeline/transportation-geometry-check.py
    python3 pipeline/transportation-geometry-check.py --dist site/dist   # also count drawn blocks in built pages

The criteria are in pipeline/transportation-data-audit-criteria.md:

  E1  no empty, zero-length, self-intersecting or out-of-city shape in a file
      the site draws.
  E2  a segment keyed by a CNN lies on that block of the city's centerline
      (DataSF 3psu-pn9h): its farthest vertex within 50 ft, and the block
      active, not retired. A re-keyed segment is drawn on its new block, so
      the distance test cannot fail for it; a second test compares SFMTA's
      typed cross streets with the centerline's and fails when SFMTA's name
      and both cross streets agree on a block the row was moved off.
  E3  a project's map draws every block it holds.

Each generator guards its own output (bike-network-history.py for E2,
coordination-projects.py for E3) and the site build checks E1 and E3 from
site/data alone (site/scripts/check-geometry.mjs). This script is the whole
audit in one run, with the centerline, and with --dist it reads the built
project pages and counts the subpaths each map draws.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import glob
import json
import math
import os
import re
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from bikeway_snap import Centerline, TOLERANCE_M, proj  # noqa: E402

DATA = os.path.join(ROOT, "site", "data")
# The audit's box around San Francisco, Treasure Island included.
LON, LAT = (-122.53, -122.35), (37.70, 37.835)
FT = 3.28084


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersect(p1, p2, p3, p4):
    d1, d2 = _cross(p3, p4, p1), _cross(p3, p4, p2)
    d3, d4 = _cross(p1, p2, p3), _cross(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4


def self_intersects(pts):
    q = [proj(p) for p in pts]
    closed = len(q) > 3 and q[0] == q[-1]
    segs = list(zip(q, q[1:]))
    for i in range(len(segs)):
        for j in range(i + 2, len(segs)):
            if closed and i == 0 and j == len(segs) - 1:
                continue
            if _intersect(*segs[i], *segs[j]):
                return True
    return False


def length_m(pts):
    q = [proj(p) for p in pts]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:]))


def e1(name, lines, points=()):
    """Counts of bad shapes among lines (lists of [lon, lat]) and points."""
    bad = {"empty": 0, "outside": 0, "zero-length": 0, "self-intersecting": 0}
    for pts in lines:
        if not pts or len(pts) < 2:
            bad["empty"] += 1
            continue
        if any(not (LON[0] <= x <= LON[1] and LAT[0] <= y <= LAT[1]) for x, y in pts):
            bad["outside"] += 1
        if length_m(pts) < 0.1:
            bad["zero-length"] += 1
        elif self_intersects(pts):
            bad["self-intersecting"] += 1
    for x, y in points:
        if not (LON[0] <= x <= LON[1] and LAT[0] <= y <= LAT[1]):
            bad["outside"] += 1
    return {"file": name, "lines": len(lines), "points": len(points), **bad}


def load(rel):
    return json.load(open(os.path.join(DATA, rel)))


def geojson_lines(fc):
    out = []
    for f in fc["features"]:
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            out.append(g["coordinates"])
        elif g.get("type") == "MultiLineString":
            out.extend(g["coordinates"])
        else:
            out.append([])
    return out


def cross_street_counts(cl=None):
    """The cross-street test below, without printing: (counts, contradictions,
    old-only rows). pipeline/transportation-audit.py (E2) calls it too.
    `cl` is a bikeway_snap.Centerline; the process's shared one when None."""
    from bikeway_snap import cnn_key, name_key, rekeyed_layer, shared_snapper, Snapper  # noqa: F401
    net = json.load(open(os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "network.json")))
    snap = shared_snapper() if cl is None else Snapper(centerline=cl)
    cl = snap.cl
    rekeyed_layer(net["records"], snap)
    counts = {"new": 0, "one of two new": 0, "old only": 0, "neither": 0, "no cross streets": 0}
    contra, old_only = [], []
    for e in snap.log:
        sf = {k for k in (name_key(e["from"]), name_key(e["to"])) if k}
        new = [c for c in e["to_cnns"] if c]
        new_x = set().union(*[cl.cross.get(c, set()) for c in new]) if new else set()
        old_x = cl.cross.get(e["cnn"], set())
        if not sf:
            counts["no cross streets"] += 1
            continue
        if new and sf <= new_x:
            counts["new"] += 1
        elif sf <= old_x:
            counts["old only"] += 1
            old_only.append(e)
        elif sf & new_x:
            # SFMTA's other label is a row end the centerline names differently
            # ("END: SOUTH", "HWY 101 OFF-RAMP", a mid-block crossing).
            counts["one of two new"] += 1
        else:
            counts["neither"] += 1
        # A divided street's two carriageways share their cross streets, so a
        # row moved to the other carriageway still matches: not a contradiction.
        if (e["cnn"] in cl.active and e["cnn"] not in new and sf <= old_x and not sf <= new_x
                and name_key(e["street"]) and name_key(e["street"]) == cl.name.get(e["cnn"])):
            contra.append(e)
    return counts, contra, old_only


def cross_streets(cl):
    """E2 by a second route. A re-keyed segment's line is drawn on the block
    the snapper chose, so the distance test above passes by construction for
    it. This test ignores geometry: it compares the cross streets SFMTA typed
    on each re-keyed row (FROM_ST, TO_ST) with the cross streets the
    centerline gives the row's new blocks and its old one.

    It fails on a contradiction: a row whose street name and both cross
    streets all describe the active block SFMTA typed, moved off that block
    entirely. Three of SFMTA's own fields would then agree against the
    snapper. Rows whose labels match neither block (the Presidio, the Bay
    Trail) or only the old one (John F Kennedy Drive rows carrying the
    Richmond avenues of the Cabrillo CNN they were typed with) are counted
    and listed, not failed. Returns True on failure."""
    counts, contra, old_only = cross_street_counts(cl)
    n = sum(counts.values())
    print("E2  cross streets of the %d re-keyed rows, against the centerline's (no geometry used)" % n)
    print("  both match the new blocks %d  one of two matches the new blocks %d  both match the old block only %d  neither %d  no cross streets typed %d"
          % (counts["new"], counts["one of two new"], counts["old only"], counts["neither"], counts["no cross streets"]))
    for e in old_only:
        print("    old only: oid %s %s (%s -> %s), typed %s, now %s"
              % (e["oid"], (e["street"] or "").strip() or "(no name)", e["from"], e["to"], e["cnn"],
                 ", ".join(c or h for c, _, h in e["pieces"])))
    print("  contradictions (name and both cross streets describe the typed active block, row moved off it): %d  %s"
          % (len(contra), "ok" if not contra else "FAIL"))
    for e in contra[:20]:
        print("    oid %s %s %s -> %s: typed %s, moved to %s" % (e["oid"], e["street"], e["from"], e["to"], e["cnn"],
                                                              ", ".join(c or "unkeyed" for c in e["to_cnns"])))
    return bool(contra)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", help="a built site/dist to count each project map's drawn subpaths")
    ap.add_argument("--data", help="read the site data from this directory instead of site/data")
    args = ap.parse_args()
    global DATA
    if args.data:
        DATA = args.data
    failed = False

    traced = load("north-star/traced.geojson")
    segs = load("bike-history/segments.json")["segments"]
    aa = load("bike-history/all-ages.geojson")
    streets = load("sf-streets.json")
    coord = load("coordination.json")
    overlap = load("department-overlap.json")
    ov_segs = [s for c in overlap["compare"] for s in c.get("segments", []) if s.get("line")]

    print("E1  valid shapes")
    rows = [
        e1("north-star/traced.geojson", geojson_lines(traced)),
        e1("north-star/segments.geojson", geojson_lines(load("north-star/segments.geojson"))),
        e1("bike-history/segments.json", [s["pts"] for s in segs]),
        e1("bike-history/all-ages.geojson", geojson_lines(aa)),
        e1("sf-streets.json", streets["lines"]),
        # A project with nothing to draw at all is an empty shape too, except
        # a page SFMTA publishes but does not map: it holds no blocks
        # (geometryKind "none") and its page says no geometry is published.
        e1("coordination.json projects", [ln for p in coord["projects"] for ln in p["geometry"]]
           + [[] for p in coord["projects"] if not p["geometry"] and not p.get("nodes")
              and not (p.get("geometryKind") == "none" and p["blocks"] == 0)],
           [pt for p in coord["projects"] for pt in p.get("nodes", [])]),
        e1("department-overlap.json compare", [s["line"] for s in ov_segs]),
    ]
    for r in rows:
        n = r["empty"] + r["outside"] + r["zero-length"] + r["self-intersecting"]
        failed |= n > 0
        print("  %-34s %6d lines %5d points  empty %d  outside %d  zero-length %d  self-intersecting %d  %s"
              % (r["file"], r["lines"], r["points"], r["empty"], r["outside"], r["zero-length"],
                 r["self-intersecting"], "ok" if n == 0 else "FAIL"))

    print("E2  on the CNN's centerline block, within 50 ft")
    cl = Centerline()
    keyed = [
        ("north-star/traced.geojson", [(f["properties"]["cnn"], f["geometry"]["coordinates"]) for f in traced["features"]]),
        ("bike-history/segments.json", [(s["cnn"], s["pts"]) for s in segs if s["cnn"]]),
        ("bike-history/all-ages.geojson", [(f["properties"]["cnn"], f["geometry"]["coordinates"]) for f in aa["features"] if f["properties"]["cnn"]]),
        ("department-overlap.json compare", [(s["cnn"], s["line"]) for s in ov_segs]),
    ]
    for name, items in keyed:
        over, over330, retired, missing, worst = 0, 0, 0, 0, (0.0, "")
        for cnn, pts in items:
            if cnn not in cl.line:
                missing += 1
                continue
            if cnn not in cl.active:
                retired += 1
            d = cl.max_dist(pts, cnn)
            over += d > TOLERANCE_M
            over330 += d > 100.584
            worst = max(worst, (d, cnn))
        n = over + retired + missing
        failed |= n > 0
        print("  %-34s %6d keyed  over 50 ft %d  over 330 ft %d  retired %d  not on centerline %d  farthest %.0f ft (%s)  %s"
              % (name, len(items), over, over330, retired, missing, worst[0] * FT, worst[1], "ok" if n == 0 else "FAIL"))
    print("  centerline %s" % cl.tag)
    failed |= cross_streets(cl)

    print("E3  every held block drawn")
    held = sum(p["blocks"] for p in coord["projects"])
    drawn = sum(len(p["geometry"]) + len(p.get("nodes", [])) for p in coord["projects"])
    short = [p for p in coord["projects"] if len(p["geometry"]) + len(p.get("nodes", [])) < p["blocks"]]
    failed |= bool(short)
    print("  coordination.json  %d of %d held blocks and intersections drawn; %d of %d projects short  %s"
          % (drawn, held, len(short), len(coord["projects"]), "ok" if not short else "FAIL"))
    for p in short[:10]:
        print("    %s: %d of %d" % (p["name"], len(p["geometry"]) + len(p.get("nodes", [])), p["blocks"]))

    if args.dist:
        by_slug = {p["slug"]: p for p in coord["projects"]}
        pages = glob.glob(os.path.join(args.dist, "transportation", "bike", "projects", "*", "index.html"))
        bad, n = [], 0
        for f in pages:
            slug = os.path.basename(os.path.dirname(f))
            p = by_slug.get(slug)
            if not p:
                continue
            html = open(f, encoding="utf-8").read()
            # The map's data (site/src/pages/transportation-projects.mjs): per
            # category against the plan, one encoded run per block ("l", its
            # point counts in "n") and one point per intersection ("p", two
            # offsets each).
            sub = 0
            for blob in re.findall(r'<script type="application/json" class="coord-data">(.*?)</script>', html, re.S):
                for c in json.loads(blob)["cats"]:
                    sub += len(c["l"]["n"]) + len(c["p"]) // 2
            n += 1
            if sub != p["blocks"]:
                bad.append((p["name"], sub, p["blocks"]))
        failed |= bool(bad) or n != len(coord["projects"])
        print("  built pages: %d of %d project pages read; %d draw fewer subpaths than held blocks  %s"
              % (n, len(coord["projects"]), len(bad), "ok" if not bad and n == len(coord["projects"]) else "FAIL"))
        for b in bad[:10]:
            print("    %s: %d of %d" % b)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
