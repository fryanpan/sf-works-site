#!/usr/bin/env python3
"""Street grade for every active San Francisco street block, from the USGS 3DEP 1 m lidar DEM sampled along the 3psu-pn9h centerlines.

    tools/school-trips/street-grades.py            # build data/street-grades/grades.json; fetch the DEM tiles once if absent
    tools/school-trips/street-grades.py --refresh  # re-read the DEM tiles whatever is cached
    tools/school-trips/street-grades.py --check    # run the quality checks on the file on disk

WHY. Bryan, 2026-10-18, accepted a rule to drop blocks steeper than 20% from
the School Trips bikeway candidates; his standing rule is to ignore slope
unless the grade is extreme. This file is the grade that rule reads.

SOURCES.
  * Street blocks: DataSF 3psu-pn9h (active street centerlines), through
    lib/sfdata.py, one row per CNN. CNN keys are str(cnn) without its
    decimal part and leading zeros, as in scripts/school-segments.py.
  * Elevation: the USGS 3DEP Bare Earth DEM dynamic service,
    https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer.
    Over San Francisco its top-priority source is the USGS 1 m DEM from the
    CA_SanFrancisco_B23 lidar project, flown 2023-04-20, NAVD 88 (the
    service's identify call, read 2026-10-18). The script asks exportImage for
    float32 GeoTIFF tiles in UTM 10N (EPSG:26910) at RES_M metres a pixel with
    bilinear resampling, 4 km tiles of TILE_PX pixels, cached under
    .cache/street-grades/ (gitignored). PIL reads the uncompressed float TIFF;
    rasterio is not needed. The tile's GeoTIFF tie point and pixel scale place
    it. sources/usgs-3dep-elevation.md has the source and the published-grade check.

WHAT IS MEASURED. Each block's centerline is sampled every STEP_M metres
(bilinear). Two numbers, in percent, one decimal:
  [avg_grade, max_grade_100ft]
  avg_grade        |elevation(last point) - elevation(first point)| / centerline length.
  max_grade_100ft  the steepest 100 ft stretch: max over every window of 100 ft
                   along the line of |rise| / 100 ft. A block shorter than
                   100 ft gets its avg_grade.
The published grades this is checked against (Bureau of Engineering's list,
as printed by 7x7, 2016) are a block's maximum, so the rule should read the
second number.

WHERE THE DEM DOES NOT DESCRIBE THE ROAD. A bare-earth DEM has bridges,
viaducts and tunnels removed, so a freeway viaduct or a block through a tunnel
(Broadway, Stockton, the Sunset tunnel portal) takes the ground or hill
surface under or over it. Those blocks still get a number; it is the ground's
grade, not the deck's. classcode 1 (freeway) and layers FREEWAYS and
PAPER_FWYS are not candidates for a bikeway; the checks' 0-45% range covers
the remaining street layers and lists what falls outside it.

CHECKS (run on every build, and with --check). Any failure exits 1 and the
previous file stays in place:
  * row count at least ROW_FLOOR, and at least 98% of active blocks graded;
  * keys unique, both values present and non-negative;
  * on street layers (STREETS, STREETS_TI, STREETS_YBI, STREETS_HUNTERSP,
    PRIVATE, UPROW) with classcode not 1: max_grade_100ft within 0-45%, except
    at most OUTLIER_SHARE of them (tunnels, ramps and DEM artefacts), each
    listed;
  * the famous steep blocks from the Bureau of Engineering list come out over
    25% on max_grade_100ft: Filbert (Hyde-Leavenworth), 22nd (Church-
    Vicksburg), Jones (Union-Filbert), Duboce (Buena Vista-Alpine);
  * a flat control, Lake St (6th-8th Ave), comes out under 5%.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import math
import os
import sys
import time
import urllib.request
from collections import defaultdict, deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.stable import write_json  # noqa: E402

OUT = os.path.join(ROOT, "data", "street-grades", "grades.json")
CACHE = os.path.join(ROOT, ".cache", "street-grades")
SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
RES_M = 2.0
TILE_PX = 2000
STEP_M = 2.0
WINDOW_M = 30.48  # 100 ft
ROW_FLOOR = 15000
OUTLIER_SHARE = 0.01
STREET_LAYERS = {"STREETS", "STREETS_TI", "STREETS_YBI", "STREETS_HUNTERSP", "PRIVATE", "UPROW"}
STEEP = [("FILBERT ST", "HYDE ST", "LEAVENWORTH ST", 31.5),
         ("22ND ST", "CHURCH ST", "VICKSBURG ST", 31.5),
         ("JONES ST", "UNION ST", "FILBERT ST", 29.0),
         ("DUBOCE AVE", "BUENA VISTA AVE EAST", "ALPINE TER", 27.9)]
FLAT = [("LAKE ST", "06TH AVE", "08TH AVE")]


def key(cnn):
    return str(cnn or "").split(".")[0].lstrip("0")


def blocks():
    """[(cnn, streetname, layer, classcode, [(lon, lat), ...])] for every active centerline."""
    import sfdata
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,classcode,layer,line",
                     where="active='true'", floor=15000)
    out = []
    for row in r.rows:
        g = row.get("line")
        c = key(row.get("cnn"))
        if not c or not isinstance(g, dict):
            continue
        parts = [g["coordinates"]] if g.get("type") == "LineString" else g.get("coordinates") or []
        pts = [p for part in parts for p in part]
        if len(pts) < 2:
            continue
        out.append((c, (row.get("streetname") or "").strip().upper(), row.get("layer") or "",
                    str(row.get("classcode") or ""), pts))
    return out, r


# ---- the DEM ---------------------------------------------------------------------

def tile_grid(xmin, ymin, xmax, ymax):
    span = RES_M * TILE_PX
    x0 = math.floor(xmin / 1000.0) * 1000.0 - 200
    y0 = math.floor(ymin / 1000.0) * 1000.0 - 200
    nx = int(math.ceil((xmax + 200 - x0) / span))
    ny = int(math.ceil((ymax + 200 - y0) / span))
    return [(x0 + i * span, y0 + j * span, x0 + (i + 1) * span, y0 + (j + 1) * span)
            for j in range(ny) for i in range(nx)]


def fetch_tile(bbox, refresh):
    os.makedirs(CACHE, exist_ok=True)
    name = "dem_%dm_%d_%d.tif" % (RES_M, bbox[0], bbox[1])
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and not refresh:
        return path
    q = ("bbox=%d,%d,%d,%d&bboxSR=26910&imageSR=26910&size=%d,%d&format=tiff&pixelType=F32"
         "&noDataInterpretation=esriNoDataMatchAny&interpolation=RSP_BilinearInterpolation"
         "&compression=None&f=image") % (bbox + (TILE_PX, TILE_PX))
    url = SERVICE + "/exportImage?" + q
    tmp = path + ".part"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as fh:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
            with open(tmp, "rb") as fh:
                head = fh.read(4)
            if head not in (b"II*\x00", b"MM\x00*"):
                raise IOError("not a TIFF: %r" % open(tmp, "rb").read(300))
            os.replace(tmp, path)
            print("  fetched %s (%d MB)" % (name, os.path.getsize(path) >> 20))
            return path
        except Exception as e:  # noqa: BLE001 - retry politely, then keep whatever is cached
            print("  tile %s attempt %d failed: %s" % (name, attempt + 1, e))
            time.sleep(10 * (attempt + 1))
    if os.path.exists(tmp):
        os.remove(tmp)
    raise SystemExit("DEM tile %s could not be read; nothing written" % name)


class Tile:
    def __init__(self, path):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path)
        tie = im.tag_v2.get(33922)   # ModelTiepoint: (i, j, k, x, y, z)
        scale = im.tag_v2.get(33550)  # ModelPixelScale: (sx, sy, sz)
        if not tie or not scale:
            raise SystemExit("%s has no GeoTIFF tie point" % path)
        self.x0, self.y0 = tie[3] - tie[0] * scale[0], tie[4] + tie[1] * scale[1]
        self.sx, self.sy = scale[0], scale[1]
        a = np.asarray(im, dtype=np.float32).copy()
        a[(a < -200) | (a > 2000)] = np.nan
        self.z = a
        self.h, self.w = a.shape

    def sample(self, x, y):
        """Bilinear elevation at UTM points (pixel centres at x0 + (i + 0.5) sx); NaN outside."""
        c = (x - self.x0) / self.sx - 0.5
        r = (self.y0 - y) / self.sy - 0.5
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        ok = (c0 >= 0) & (r0 >= 0) & (c0 < self.w - 1) & (r0 < self.h - 1)
        out = np.full(len(x), np.nan)
        if ok.any():
            cc, rr, fc, fr = c0[ok], r0[ok], (c - c0)[ok], (r - r0)[ok]
            z = self.z
            out[ok] = (z[rr, cc] * (1 - fc) * (1 - fr) + z[rr, cc + 1] * fc * (1 - fr)
                       + z[rr + 1, cc] * (1 - fc) * fr + z[rr + 1, cc + 1] * fc * fr)
        return out


def sample_all(tiles, x, y):
    z = np.full(len(x), np.nan)
    for t in tiles:
        need = np.isnan(z)
        if not need.any():
            break
        z[need] = t.sample(x[need], y[need])
    return z


# ---- grades ----------------------------------------------------------------------

def densify(xy):
    """Points every STEP_M along a polyline, with their distance along it."""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    if total <= 0:
        return None, None, 0.0
    n = max(2, int(math.ceil(total / STEP_M)) + 1)
    d = np.linspace(0.0, total, n)
    return np.interp(d, s, xy[:, 0]), np.interp(d, s, xy[:, 1]), d


def grade(tiles, xy):
    x, y, d = densify(xy)
    if x is None:
        return None
    z = sample_all(tiles, x, y)
    if np.isnan(z).any():
        good = ~np.isnan(z)
        if good.sum() < 2:
            return None
        z = np.interp(d, d[good], z[good])
    L = d[-1]
    avg = abs(z[-1] - z[0]) / L * 100.0
    if L <= WINDOW_M:
        return [round(float(avg), 1), round(float(avg), 1)]
    zw = np.interp(d + WINDOW_M, d, z)
    ok = d + WINDOW_M <= L + 1e-9
    mx = float(np.max(np.abs(zw[ok] - z[ok]))) / WINDOW_M * 100.0
    return [round(float(avg), 1), round(float(max(mx, avg)), 1)]


# ---- named blocks, for the checks ------------------------------------------------

def between(rows, street, a, b):
    """CNNs of `street` running from its crossing with street `a` to its crossing with street `b`:
    a path over the street's own blocks between end points shared with each cross street."""
    def node(p):
        return (round(p[0], 6), round(p[1], 6))
    ends = defaultdict(set)
    for c, name, _l, _k, pts in rows:
        ends[name].update([node(pts[0]), node(pts[-1])])
    adj = defaultdict(list)
    for c, name, _l, _k, pts in rows:
        if name == street:
            u, v = node(pts[0]), node(pts[-1])
            adj[u].append((v, c))
            adj[v].append((u, c))
    starts = [n for n in adj if n in ends[a]]
    goals = {n for n in adj if n in ends[b]}
    for s in starts:
        seen, q = {s: []}, deque([s])
        while q:
            u = q.popleft()
            if u in goals:
                return seen[u]
            for v, c in adj[u]:
                if v not in seen:
                    seen[v] = seen[u] + [c]
                    q.append(v)
    return []


# ---- checks ----------------------------------------------------------------------

def checks(doc, rows):
    fails, notes = [], []
    g = doc["blocks"]
    if len(g) < ROW_FLOOR:
        fails.append("row count %d under floor %d" % (len(g), ROW_FLOOR))
    if len(g) < 0.98 * len(rows):
        fails.append("only %d of %d active blocks graded" % (len(g), len(rows)))
    if len({c for c, *_ in rows}) != len(rows):
        fails.append("duplicate CNNs in the centerlines")
    bad = [c for c, v in g.items() if not (isinstance(v, list) and len(v) == 2 and all(
        isinstance(t, (int, float)) and t >= 0 for t in v))]
    if bad:
        fails.append("%d blocks with a missing or negative grade, e.g. %s" % (len(bad), bad[:5]))
    street = [(c, n) for c, n, layer, k, _p in rows if layer in STREET_LAYERS and k != "1" and c in g]
    out = sorted(((g[c][1], c, n) for c, n in street if g[c][1] > 45.0), reverse=True)
    if len(out) > OUTLIER_SHARE * len(street):
        fails.append("%d street blocks over 45%% (limit %d)" % (len(out), OUTLIER_SHARE * len(street)))
    notes.append("street blocks over 45%%: %d of %d: %s" % (
        len(out), len(street), ", ".join("%s %s %.1f%%" % (n, c, v) for v, c, n in out[:15])))
    for st, a, b, pub in STEEP:
        cs = between(rows, st, a, b)
        if not cs:
            fails.append("could not find %s between %s and %s" % (st, a, b))
            continue
        vals = [g.get(c) for c in cs]
        mx = max((v[1] for v in vals if v), default=None)
        notes.append("%s %s-%s cnn %s: avg/max100 %s, published %.1f%%" % (st, a, b, ",".join(cs), vals, pub))
        if mx is None or mx <= 25.0:
            fails.append("%s between %s and %s is %s, not over 25%%" % (st, a, b, mx))
    for st, a, b in FLAT:
        cs = between(rows, st, a, b)
        vals = [g.get(c) for c in cs]
        notes.append("%s %s-%s cnn %s: %s" % (st, a, b, ",".join(cs), vals))
        if not cs or max(v[1] for v in vals if v) >= 5.0:
            fails.append("flat control %s %s-%s is %s" % (st, a, b, vals))
    hist = np.histogram([v[1] for c, v in g.items()], bins=[0, 5, 10, 15, 20, 25, 30, 45, 1e9])[0]
    notes.append("max100 distribution 0-5/5-10/10-15/15-20/20-25/25-30/30-45/45+: %s" % [int(h) for h in hist])
    notes.append("blocks over 20%% (max100): %d; on street layers: %d" % (
        sum(1 for v in g.values() if v[1] > 20), sum(1 for c, _n in street if g[c][1] > 20)))
    return fails, notes


def build(refresh):
    from pyproj import Transformer
    rows, r = blocks()
    tr = Transformer.from_crs(4326, 26910, always_xy=True)
    proj = {}
    for c, _n, _l, _k, pts in rows:
        a = np.array(pts, dtype=float)
        x, y = tr.transform(a[:, 0], a[:, 1])
        proj[c] = np.column_stack([x, y])
    allxy = np.vstack(list(proj.values()))
    grid = tile_grid(*allxy.min(axis=0), *allxy.max(axis=0))
    paths = []
    for bb in grid:
        paths.append(fetch_tile(bb, refresh))
        time.sleep(1)
    tiles = [Tile(p) for p in paths]
    out = {}
    for c in sorted(proj):
        v = grade(tiles, proj[c])
        if v is not None:
            out[c] = v
    doc = {
        "note": ("Grade of each active street block, in percent, as [avg_grade, max_grade_100ft]: avg is the "
                 "absolute elevation difference between the block's two end points over its centerline length; "
                 "max is the steepest 100 ft stretch along the centerline. Elevation is the USGS 3DEP bare-earth "
                 "DEM (1 m lidar, CA_SanFrancisco_B23, 2023) resampled to %g m and sampled every %g m. Bridges, "
                 "viaducts and tunnels take the ground's grade, not the deck's. Built by tools/school-trips/street-grades.py; "
                 "source and check in sources/usgs-3dep-elevation.md." % (RES_M, STEP_M)),
        "source": {"blocks": "DataSF 3psu-pn9h, active street centerlines, fetched %s" % r.fetched_on,
                   "elevation": SERVICE + " (exportImage, EPSG:26910, %g m bilinear)" % RES_M},
        "blocks": out,
    }
    return doc, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        doc = json.load(open(OUT, encoding="utf-8"))
        rows, _r = blocks()
    else:
        doc, rows = build(args.refresh)
    fails, notes = checks(doc, rows)
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
