#!/usr/bin/env python3
"""Every San Francisco street block a Muni bus, trolley, rail or cable car route runs along, from SFMTA's GTFS shapes matched to the 3psu-pn9h centerlines.

    tools/muni/muni-streets.py          # build data/muni-streets/blocks.json from the cached feed (fetch it once if absent)
    tools/muni/muni-streets.py --check  # run the quality checks on the file on disk

SOURCES.
  * Routes: SFMTA's GTFS feed, the copy tools/muni/muni-gtfs.py holds at
    .cache/muni-gtfs/muni_gtfs-current.zip (gitignored). When that copy is
    absent this script calls muni-gtfs.py's own refresh(), which downloads
    and checks the feed and writes only the cache. Updating the feed is
    muni-gtfs.py --update's job. Every shape in shapes.txt is used, joined to its
    route through trips.txt and routes.txt (route_short_name, any route_type).
  * Street blocks: DataSF 3psu-pn9h (active street centerlines) through
    lib/sfdata.py; CNN keys as in scripts/school-segments.py.

THE MATCH. Shapes and blocks are projected to UTM 10N. A block is sampled every
STEP_FT along its centerline, leaving out END_FT at each end, where every
crossing route passes. A shape runs along the block when at least
SHARE of those samples lie within NEAR_FT of the shape AND the shape's
direction at the nearest point is within PARALLEL_DEG of the block's direction.
A route that crosses the block touches only its end samples, so it can't
reach the share. A block shorter than 2 x END_FT + STEP_FT is sampled at its
midpoint only.

WHAT IT CANNOT TELL. GTFS shapes have no layer, so rail running in a subway
(Muni Metro under Market St, the Central Subway under 4th and Stockton, the
Twin Peaks and Sunset tunnels) matches the street above it. Those blocks are
listed with their rail routes. A route on a divided street drawn on the far
roadway, or on a street wider than about 80 ft, can sit outside NEAR_FT of the
centerline; the checks below cover Geary and Mission.

CHECKS (every build, and --check; a failure exits 1 and leaves the old file):
  * at least BLOCK_FLOOR blocks matched and at least ROUTE_FLOOR routes seen;
  * every matched CNN is an active 3psu-pn9h block, every route list sorted
    and non-empty;
  * named Muni streets have a matched block: Mission St, Geary Blvd, Judah St
    (N), Powell St (Powell cable cars), Stockton St, 3rd St (T), each with the
    route the check names;
  * Lake St between 6th and 8th Ave, which no route runs on, is not matched.
Prints the miles of centerline matched.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import csv
import importlib.util
import io
import json
import math
import os
import sys
import zipfile
from collections import defaultdict, deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.stable import write_json  # noqa: E402

OUT = os.path.join(ROOT, "data", "muni-streets", "blocks.json")
FT = 0.3048
NEAR_FT = 40.0
STEP_FT = 20.0
END_FT = 60.0
SHARE = 0.6
PARALLEL_DEG = 25.0
BLOCK_FLOOR = 2000
ROUTE_FLOOR = 50
MUST = [("MISSION ST", "14"), ("GEARY BLVD", "38"), ("JUDAH ST", "N"), ("POWELL ST", "PM"),
        ("STOCKTON ST", "30"), ("03RD ST", "T")]
NONE = [("LAKE ST", "06TH AVE", "08TH AVE")]


def muni_gtfs():
    m = paths.load("muni-gtfs.py")
    return m


def key(cnn):
    return str(cnn or "").split(".")[0].lstrip("0")


def blocks():
    import sfdata
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,classcode,layer,line",
                     where="active='true'", floor=15000)
    out = []
    for row in r.rows:
        g, c = row.get("line"), key(row.get("cnn"))
        if not c or not isinstance(g, dict):
            continue
        parts = [g["coordinates"]] if g.get("type") == "LineString" else g.get("coordinates") or []
        pts = [p for part in parts for p in part]
        if len(pts) >= 2:
            out.append((c, (row.get("streetname") or "").strip().upper(), pts))
    return out, r


def read_shapes(m):
    """({shape_id: [(lon, lat), ...]}, {shape_id: set(route_short_name)}, feed description)."""
    path = m.zip_path()
    if not os.path.exists(path):
        print("  no held feed; fetching through muni-gtfs.py refresh()")
        m.refresh(False)
    with zipfile.ZipFile(path) as zf:
        routes = {r["route_id"]: r["route_short_name"] or r["route_id"] for r in m.rows(zf, "routes.txt")}
        names = defaultdict(set)
        for t in m.rows(zf, "trips.txt"):
            if t.get("shape_id"):
                names[t["shape_id"]].add(routes.get(t["route_id"], t["route_id"]))
        pts = defaultdict(list)
        for s in m.rows(zf, "shapes.txt"):
            pts[s["shape_id"]].append((int(s["shape_pt_sequence"]), float(s["shape_pt_lon"]), float(s["shape_pt_lat"])))
    shapes = {k: [(x, y) for _q, x, y in sorted(v)] for k, v in pts.items() if len(v) >= 2}
    meta = m.read_meta() or {}
    feed = {"url": m.FEED_URL, "lastModified": meta.get("lastModified"), "sha256": meta.get("sha256"),
            "shapes": len(shapes), "routes": len({n for v in names.values() for n in v})}
    return shapes, names, feed


def densify(xy, step):
    seg = np.hypot(*np.diff(xy, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(2, int(math.ceil(s[-1] / step)) + 1)
    d = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(d, s, xy[:, 0]), np.interp(d, s, xy[:, 1])]), d, s[-1]


def match(rows, shapes, names):
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    tr = Transformer.from_crs(4326, 26910, always_xy=True)

    def proj(pts):
        a = np.array(pts, dtype=float)
        x, y = tr.transform(a[:, 0], a[:, 1])
        return np.column_stack([x, y])

    # Every shape segment, with its owner and unit direction, indexed by midpoint.
    P0, P1, OWN = [], [], []
    sids = sorted(shapes)
    for i, sid in enumerate(sids):
        xy = proj(shapes[sid])
        keep = np.r_[True, np.hypot(*np.diff(xy, axis=0).T) > 0.01]
        xy = xy[keep]
        if len(xy) < 2:
            continue
        P0.append(xy[:-1]); P1.append(xy[1:]); OWN.append(np.full(len(xy) - 1, i))
    P0, P1, OWN = np.vstack(P0), np.vstack(P1), np.concatenate(OWN)
    D = P1 - P0
    SL = np.hypot(*D.T)
    U = D / SL[:, None]
    tree = cKDTree((P0 + P1) / 2)
    reach = NEAR_FT * FT + SL.max() / 2
    near_m, cos_lim = NEAR_FT * FT, math.cos(math.radians(PARALLEL_DEG))

    out, length = {}, {}
    for c, _n, pts in rows:
        xy = proj(pts)
        dense, d, L = densify(xy, STEP_FT * FT)
        length[c] = L
        inner = (d >= END_FT * FT) & (d <= L - END_FT * FT)
        if inner.sum() == 0:
            mid, _dd, _L = densify(xy, max(L / 2, 0.01))
            dense, inner = mid[1:2], np.array([True])
        S = dense[inner]
        # block direction at each sample: the segment it falls on
        seg = np.hypot(*np.diff(xy, axis=0).T)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        dd = d[inner] if len(d) == len(inner) else np.array([L / 2])
        k = np.clip(np.searchsorted(cum, dd, side="right") - 1, 0, len(seg) - 1)
        bu = np.diff(xy, axis=0)[k] / np.maximum(seg[k], 1e-9)[:, None]
        hits = defaultdict(int)
        for j, p in enumerate(S):
            cand = np.array(tree.query_ball_point(p, reach), dtype=np.int64)
            if not len(cand):
                continue
            a, u, sl = P0[cand], U[cand], SL[cand]
            t = np.clip(((p - a) * u).sum(1), 0, sl)
            dist = np.hypot(*(a + u * t[:, None] - p).T)
            ok = (dist <= near_m) & (np.abs(u @ bu[j]) >= cos_lim)
            for sh in set(OWN[cand[ok]].tolist()):
                hits[sh] += 1
        need = SHARE * len(S)
        rts = set()
        for sh, h in hits.items():
            if h >= need:
                rts |= names.get(sids[sh], set())
        if rts:
            out[c] = sorted(rts)
    return out, length


def between(rows, street, a, b):
    def node(p):
        return (round(p[0], 6), round(p[1], 6))
    ends = defaultdict(set)
    for c, name, pts in rows:
        ends[name].update([node(pts[0]), node(pts[-1])])
    adj = defaultdict(list)
    for c, name, pts in rows:
        if name == street:
            u, v = node(pts[0]), node(pts[-1])
            adj[u].append((v, c)); adj[v].append((u, c))
    goals = {n for n in adj if n in ends[b]}
    for s in [n for n in adj if n in ends[a]]:
        seen, q = {s: []}, deque([s])
        while q:
            u = q.popleft()
            if u in goals:
                return seen[u]
            for v, c in adj[u]:
                if v not in seen:
                    seen[v] = seen[u] + [c]; q.append(v)
    return []


def checks(doc, rows, length):
    fails, notes = [], []
    b = doc["blocks"]
    active = {c for c, _n, _p in rows}
    name = {c: n for c, n, _p in rows}
    if len(b) < BLOCK_FLOOR:
        fails.append("%d blocks matched, floor %d" % (len(b), BLOCK_FLOOR))
    routes = {r for v in b.values() for r in v}
    if len(routes) < ROUTE_FLOOR:
        fails.append("%d routes seen, floor %d" % (len(routes), ROUTE_FLOOR))
    stray = [c for c in b if c not in active]
    if stray:
        fails.append("%d matched CNNs not in the active centerlines: %s" % (len(stray), stray[:5]))
    if any(not v or v != sorted(v) for v in b.values()):
        fails.append("an empty or unsorted route list")
    for st, rt in MUST:
        on = [c for c in b if name.get(c) == st]
        with_rt = [c for c in on if rt in b[c]]
        allb = [c for c in active if name[c] == st]
        mi = sum(length[c] for c in on) / FT / 5280
        notes.append("%s: %d of %d blocks matched (%.1f mi), %d carry %s; routes %s" % (
            st, len(on), len(allb), mi, len(with_rt), rt, sorted({r for c in on for r in b[c]})))
        if not with_rt:
            fails.append("%s has no block matched to route %s" % (st, rt))
    for st, a, z in NONE:
        cs = between(rows, st, a, z)
        hit = {c: b[c] for c in cs if c in b}
        notes.append("%s %s-%s cnn %s: %s" % (st, a, z, ",".join(cs), hit or "no route"))
        if not cs or hit:
            fails.append("control %s %s-%s: %s" % (st, a, z, hit or "not found"))
    mi = sum(length[c] for c in b) / FT / 5280
    total = sum(length.values()) / FT / 5280
    notes.append("matched %d of %d blocks, %.1f of %.1f centerline miles; %d routes" % (
        len(b), len(active), mi, total, len(routes)))
    return fails, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    rows, r = blocks()
    if args.check:
        doc = json.load(open(OUT, encoding="utf-8"))
        from pyproj import Geod
        g = Geod(ellps="WGS84")
        length = {c: g.line_length([p[0] for p in pts], [p[1] for p in pts]) for c, _n, pts in rows}
    else:
        m = muni_gtfs()
        shapes, names, feed = read_shapes(m)
        out, length = match(rows, shapes, names)
        doc = {
            "note": ("Street blocks (3psu-pn9h CNN) a Muni route runs along, with the GTFS route_short_names: a shape "
                     "within %g ft of the centerline and within %g degrees of parallel for at least %d%% of the block "
                     "away from its %g ft ends. Crossings don't count. Rail in a subway or tunnel matches the street "
                     "above it. Built by tools/muni/muni-streets.py." % (NEAR_FT, PARALLEL_DEG, SHARE * 100, END_FT)),
            "feed": dict(feed, blocks_source="DataSF 3psu-pn9h, active street centerlines, fetched %s" % r.fetched_on),
            "blocks": out,
        }
    fails, notes = checks(doc, rows, length)
    for n in notes:
        print("  " + n)
    if fails:
        for f in fails:
            print("FAIL " + f)
        print("checks failed; %s left as it was" % os.path.relpath(OUT, ROOT))
        return 1
    if not args.check:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        wrote = write_json(OUT, doc, separators=(",", ":"), sort_keys=True)
        print("%s %s: %d blocks" % ("wrote" if wrote else "unchanged", os.path.relpath(OUT, ROOT), len(doc["blocks"])))
    print("all checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
