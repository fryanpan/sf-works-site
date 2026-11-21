#!/usr/bin/env python3
"""Read the 2025 North Star network off SFMTA's map PDF, as geometry.

Appendix L of the Biking and Rolling Plan lists the network as 393 rows of
street-and-cross-streets, and `north-star-index.py` places 344 of them on the
city's centerline file by name. The other 49 are park paths, developments, and
cross streets the index names in a form the centerline file does not carry.

The map itself is the authority the index defers to, and SFMTA published it as
a vector PDF -- every line in it is real geometry, not pixels. So this script
skips the names entirely: it converts the PDF to SVG, pulls the coloured
network strokes out by legend colour, fits a georeference against the city's
own centerline file, and snaps the drawn lines back onto centerline segments.

    tools/bike-network/north-star-map-trace.py [--map <northstar-map.pdf>]

Requires pdftocairo (poppler). Reads the map from .cache/north-star-map/,
fetching it from sfmta.com when missing. Writes out/north-star/map-trace/;
pipeline/transportation-update.py runs it as the north-star-trace step.

Which blocks are the plan's. Appendix L calls itself "an index of roadway
segments that appear on the North Star map" and says "If discrepancies
between this index and the map occur, defer to the map" (read 2026-09-29).
So the map decides: a block is on the plan's network when the map draws a
line along it. The index helps only where the hand-drawn line sits off the
street it names: a block Appendix L names (tools/bike-network/north-star-index.py's
placement, with a North Star facility other than "None") takes the map's
line within NAMED_TOL_M, any other block within TOL_M.

The georeference is fitted, not declared. The map's basemap IS the centerline
file drawn small, so the fit is basemap-to-centerlines by iterative closest
point over a 4-parameter transform (scale and offset per axis, no rotation).
Two checks say whether to trust a run: the x and y scales must agree to about
four digits, since the map is north-up and unrotated, and the residual must sit
well under a city block. A run that fails either is not usable and says so.

How a block is measured. Every drawn line is walked in 5 m steps and each
point is projected onto every block it runs along (direction within MIN_COS)
within the block's tolerance. A block is kept when the drawn line spans half
of it, first point to last with an end within END_SNAP_M counting as reached,
and runs along half its length. Each traced block carries `coverage`, the
part of its length the line runs along, `named`, whether Appendix L names it,
and `share`, how much of the block the plan draws: the span, reaching an end
where another plan block meets it there, so 1 except where the plan's line
stops partway along the block, short of its end and of any other plan block.
Every plan mile on the site is a block's miles times `share`
(lib/mile_basis.py). The transportation audit's F1 measures the same
definition from the same PDF with its own code.

Trap: the drawn stroke is 2.916pt wide, which is 33 metres on the ground. A
tolerance larger than about half a block will pick up the parallel street.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse, collections, datetime, hashlib, json, math, os, re, subprocess, sys, random

sys.path.insert(0, paths.LIB)
import stable  # noqa: E402

# SFMTA's North Star map, the plan's pages 68-69 as a vector PDF. The
# transportation audit reads the same file (pipeline/transportation-audit.py).
MAP_URL = "https://www.sfmta.com/media/41812/download"
MAP_PDF = ".cache/north-star-map/northstar-map.pdf"

# Legend, read off the map's own key (page coords x1150-1186, y1524-1615).
LEGEND = {
    "rgb(27.398682%, 49.598694%, 44.499207%)": "teal",       # solid Car-free / dashed Shared-use Path
    "rgb(14.299011%, 35.798645%, 57.899475%)": "Separated",
    "rgb(32.199097%, 70.498657%, 83.299255%)": "Shared",
    "rgb(58.299255%, 81.898499%, 89.698792%)": "Shared L3",
    "rgb(50.299072%, 51.098633%, 51.998901%)": "Undecided",
}
BASEMAP = "rgb(94.499207%, 94.099426%, 94.099426%)"
# The citywide map draws the network at 2.916pt, and the Shared Level 3 class
# at 1.75. Everything at 9.332 belongs to the enlarged insets in the margins,
# which redraw parts of the city at about 3.2x -- tracing those as if they were
# the citywide map puts their lines kilometres from where they belong.
NET_WIDTHS = ("2.916", "1.75")
INSET_WIDTH = "9.332"
BASE_WIDTH = "1.166"

# Snapping tolerance in metres. Half the drawn stroke is 16m and the narrowest
# SF block is about 80m, so 20 keeps the parallel street out.
TOL_M = 20.0
STEP_M = 5.0         # step along each drawn line
CELL_M = 50.0        # grid cell for the centerline lookup
# A gap this short in a drawn line is the map's, not the plan's: a callout
# marker on Polk at Francisco breaks the dotted Undecided line for 68 m.
DASH_GAP_M = 70.0
COVER = 0.5          # the drawn line must span, and run along, half a block
# A block Appendix L names is the plan's where the map draws a line along it
# within this. The plan says its index lists "roadway segments that appear on
# the North Star map" and, "If discrepancies between this index and the map
# occur, defer to the map" (Appendix L, read 2026-09-29), so the map still
# decides; but the map is drawn by hand, and in the Sunset and along Lake
# Merced, Skyline and Mansell its line runs 20-40 m off the street the index
# names (34th Ave Lincoln-Sloat at 24-29 m). Half the narrowest block, so a
# named street never borrows its neighbour's line.
NAMED_TOL_M = 40.0
# A drawn line that stops within this of a block's end reaches that end: the
# snapping tolerance, since registration error alone moves a line end that far.
END_SNAP_M = TOL_M
# A drawn line only counts for a centerline it runs ALONG. Without this, a
# bikeway captures every street it crosses and every freeway it runs beside.
MIN_COS = 0.85

# A bikeway is never on a freeway, and the centerline file's freeway geometry
# runs within a few metres of real waterfront and Bayshore bikeways.
NOT_A_STREET = re.compile(r"\bI-\d|HWY \d|HIGHWAY|RAMP|FWY|FREEWAY")

NUM = re.compile(r"-?\d*\.?\d+")
LON_M, LAT_M = 88000.0, 111000.0   # metres per degree at SF latitude
# The block test measures in metres on a sphere of the Earth's mean radius at
# the city's latitude, as the transportation audit does. The rounded pair above
# stays for the fit and its scale check, which were calibrated with it.
Y_M = math.radians(1) * 6371008.8
X_M = Y_M * math.cos(math.radians(37.76))


def svg_from_pdf(pdf, out):
    if not os.path.exists(out):
        subprocess.run(["pdftocairo", "-svg", pdf, out], check=True,
                       stderr=subprocess.DEVNULL)
    return open(out).read()


def polylines(d, transform):
    """Flatten one path's d= into polylines in page coordinates.

    Curves are reduced to their endpoints. At 11 metres per point a bezier
    control arm is under a metre of error, and every network line in this map
    is drawn as short segments anyway.
    """
    m = re.search(r"matrix\(([^)]*)\)", transform or "")
    a, b, c, dd, e, f = ([float(x) for x in NUM.findall(m.group(1))] if m
                         else (1, 0, 0, 1, 0, 0))
    T = lambda x, y: (a * x + c * y + e, b * x + dd * y + f)
    out, cur = [], []
    for tok in re.finditer(r"([MLCZ])([^A-Za-z]*)", d):
        cmd, nums = tok.group(1), [float(x) for x in NUM.findall(tok.group(2))]
        if cmd == "M":
            if len(cur) > 1:
                out.append(cur)
            cur = [T(nums[0], nums[1])] if len(nums) >= 2 else []
            for i in range(2, len(nums) - 1, 2):
                cur.append(T(nums[i], nums[i + 1]))
        elif cmd == "L":
            for i in range(0, len(nums) - 1, 2):
                cur.append(T(nums[i], nums[i + 1]))
        elif cmd == "C":
            for i in range(0, len(nums) - 5, 6):
                cur.append(T(nums[i + 4], nums[i + 5]))
        elif cmd == "Z" and cur:
            cur.append(cur[0])
    if len(cur) > 1:
        out.append(cur)
    return out


def read_map(svg):
    """Split the map into network lines by facility class, plus the basemap."""
    net, base, inset = collections.defaultdict(list), [], []
    attr = lambda a, n: (re.search(n + r'="([^"]*)"', a).group(1)
                         if re.search(n + r'="([^"]*)"', a) else None)
    for m in re.finditer(r"<path([^>]*?)/>", svg, re.S):
        a = m.group(1)
        stroke, width, d = attr(a, "stroke"), attr(a, "stroke-width"), attr(a, "d")
        if not d or not stroke:
            continue
        tr, dash = attr(a, "transform"), attr(a, "stroke-dasharray")
        if stroke in LEGEND and width in NET_WIDTHS:
            cls = LEGEND[stroke]
            if cls == "teal":
                cls = "Shared-use Path" if dash else "Car-free"
            net[cls].extend(polylines(d, tr))
        elif stroke in LEGEND and width == INSET_WIDTH:
            inset.extend(polylines(d, tr))
        elif stroke == BASEMAP and width == BASE_WIDTH:
            base.extend(polylines(d, tr))
    return net, base, inset


class Grid:
    """Point lookup on a lon/lat grid. Stands in for a spatial index."""

    def __init__(self, pts, cell=0.0015):
        self.pts, self.cell, self.g = pts, cell, {}
        for i, (x, y) in enumerate(pts):
            self.g.setdefault((int(x / cell), int(y / cell)), []).append(i)

    def near(self, x, y, radius_cells=1):
        cx, cy = int(x / self.cell), int(y / self.cell)
        for dx in range(-radius_cells, radius_cells + 1):
            for dy in range(-radius_cells, radius_cells + 1):
                for i in self.g.get((cx + dx, cy + dy), ()):
                    yield i

    def nearest(self, x, y):
        best, bd = None, 1e18
        for i in self.near(x, y):
            px, py = self.pts[i]
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                bd, best = d, i
        return best, math.sqrt(bd) if best is not None else None


def densify(coords, step_m):
    out = []
    for i in range(len(coords) - 1):
        (x0, y0), (x1, y1) = coords[i], coords[i + 1]
        d = math.hypot((x1 - x0) * LON_M, (y1 - y0) * LAT_M)
        n = max(1, int(d / step_m))
        for k in range(n + 1):
            out.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    return out


def drawn_along(ats):
    """How much of a block the drawn line runs along, in metres, from the
    positions along the block of the points projected onto it: runs of points
    no more than DASH_GAP_M apart, each counted from its first point to its
    last plus one step. The map breaks some drawn lines where it places a
    callout marker or a label, and counting points alone read Polk from Bay
    to North Point, drawn end to end but for 68 m under the marker at
    Francisco, as running along 38% of itself (Fable review, 2026-09-29)."""
    ats = sorted(ats)
    total, start = 0.0, ats[0]
    for a, b in zip(ats, ats[1:]):
        if b - a > DASH_GAP_M:
            total += a - start + STEP_M
            start = b
    return total + ats[-1] - start + STEP_M


def seg_dist2_m(p, a, b):
    """Squared distance in metres from lon/lat point p to the segment a-b."""
    px, py = p[0] * LON_M, p[1] * LAT_M
    ax, ay, bx, by = a[0] * LON_M, a[1] * LAT_M, b[0] * LON_M, b[1] * LAT_M
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return (px - ax - t * vx) ** 2 + (py - ay - t * vy) ** 2


def fit_georeference(base, centerlines, rounds=12, seed=0):
    """ICP the basemap onto the centerline file. Returns (a0,a1,a2,a3, report).

    page_x = a0*lon + a1 ; page_y = a2*lat + a3
    """
    target = []
    for r in centerlines:
        target.extend(densify(r["line"]["coordinates"], 20.0))
    grid = Grid(target)
    pts = [p for P in base for p in P]
    random.seed(seed)
    samp = random.sample(pts, min(8000, len(pts)))

    def quantile(a, f):
        a = sorted(a)
        return a[int(f * (len(a) - 1))]

    bx0, bx1 = quantile([p[0] for p in pts], .002), quantile([p[0] for p in pts], .998)
    by0, by1 = quantile([p[1] for p in pts], .002), quantile([p[1] for p in pts], .998)
    tx0, tx1 = quantile([p[0] for p in target], .002), quantile([p[0] for p in target], .998)
    ty0, ty1 = quantile([p[1] for p in target], .002), quantile([p[1] for p in target], .998)
    a = [(bx1 - bx0) / (tx1 - tx0), 0.0, -abs((by1 - by0) / (ty1 - ty0)), 0.0]
    a[1] = bx0 - a[0] * tx0
    a[3] = by1 - a[2] * ty0

    def linfit(u, v):
        mu, mv = sum(u) / len(u), sum(v) / len(v)
        num = sum((ui - mu) * (vi - mv) for ui, vi in zip(u, v))
        den = sum((ui - mu) ** 2 for ui in u)
        s = num / den
        return s, mv - s * mu

    report = {}
    for _ in range(rounds):
        pairs = []
        for px, py in samp:
            lon, lat = (px - a[1]) / a[0], (py - a[3]) / a[2]
            i, d = grid.nearest(lon, lat)
            if i is not None and d < 0.0012:
                pairs.append((px, py, target[i][0], target[i][1]))
        if len(pairs) < 200:
            break
        a[0], a[1] = linfit([p[2] for p in pairs], [p[0] for p in pairs])
        a[2], a[3] = linfit([p[3] for p in pairs], [p[1] for p in pairs])
        res = sorted(math.hypot(p[0] - (a[0] * p[2] + a[1]),
                                p[1] - (a[2] * p[3] + a[3])) for p in pairs)
        report = {"matched": len(pairs),
                  "median_resid_pt": round(res[len(res) // 2], 3),
                  "p90_resid_pt": round(res[int(.9 * len(res))], 3)}
    m_per_pt_x, m_per_pt_y = LON_M / abs(a[0]), LAT_M / abs(a[2])
    report.update(m_per_pt_x=round(m_per_pt_x, 3), m_per_pt_y=round(m_per_pt_y, 3),
                  scale_agreement=round(abs(m_per_pt_x - m_per_pt_y) / m_per_pt_x, 5),
                  median_resid_m=round(report.get("median_resid_pt", 0) * m_per_pt_x, 1),
                  p90_resid_m=round(report.get("p90_resid_pt", 0) * m_per_pt_x, 1))
    return a, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=MAP_PDF,
                    help="North Star Map PDF (fetched from sfmta.com when missing)")
    ap.add_argument("--centerlines", default="out/north-star/cache/centerlines.json")
    ap.add_argument("--segments", default="out/north-star/segments.geojson",
                    help="Appendix L rows placed by name (tools/bike-network/north-star-index.py)")
    ap.add_argument("--out", default="out/north-star/map-trace")
    ap.add_argument("--work", default=None, help="where to keep the converted SVG")
    args = ap.parse_args()

    if not os.path.exists(args.map):
        import urllib.request
        req = urllib.request.Request(MAP_URL, headers={"User-Agent": "Mozilla/5.0 (sf-works; +https://sf-works.org)"})
        with urllib.request.urlopen(req, timeout=120) as fh:
            body = fh.read()
        if not body.startswith(b"%PDF"):
            sys.exit("%s did not return a PDF" % MAP_URL)
        os.makedirs(os.path.dirname(os.path.abspath(args.map)), exist_ok=True)
        with open(args.map, "wb") as fh:
            fh.write(body)
    if args.work:
        work = args.work
    else:
        import atexit, shutil, tempfile
        work = tempfile.mkdtemp(prefix="north-star-trace-")
        atexit.register(shutil.rmtree, work, True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    svg = svg_from_pdf(args.map, os.path.join(work, "northstar-map.svg"))
    net, base, inset = read_map(svg)
    cl = json.load(open(args.centerlines))
    print("map: %d basemap polylines, %d inset polylines ignored, network %s" %
          (len(base), len(inset),
           ", ".join("%s %d" % (k, len(v)) for k, v in sorted(net.items()))))

    # Fitted to the streets alone: the centerline file's freeways and ramps
    # are not the plan's, and the audit fits to the same rows.
    a, report = fit_georeference(base, [r for r in cl if not NOT_A_STREET.search(r["streetname"])])
    print("georeference: %s" % json.dumps(report))
    if report["scale_agreement"] > 0.002:
        sys.exit("x and y scales disagree by %.3f%% -- the map may be rotated or "
                 "reprojected; the fit is not usable." % (report["scale_agreement"] * 100))
    if report["median_resid_m"] > 20:
        sys.exit("median residual %.1f m is too large to snap on." % report["median_resid_m"])

    # Every drawn line, in metres on a flat projection, each piece carrying
    # its facility class and direction. The block test below walks along it.
    drawn_m = collections.Counter()
    pieces = []
    for cls in sorted(net):
        for P in net[cls]:
            ll = [(((x - a[1]) / a[0]) * X_M, ((y - a[3]) / a[2]) * Y_M) for x, y in P]
            for p, q in zip(ll, ll[1:]):
                seg = math.dist(p, q)
                if seg < 1e-6:
                    continue
                drawn_m[cls] += seg
                pieces.append((cls, p, q, seg))
    print("drawn on the citywide map: %.1f miles of line" %
          (sum(drawn_m.values()) / 1609.34))

    # Blocks Appendix L names, from tools/bike-network/north-star-index.py's placement
    # by street and cross-street name. A row whose North Star facility is
    # "None" names a street to say the plan puts nothing there.
    placed, named = set(), set()
    if os.path.exists(args.segments):
        for f in json.load(open(args.segments))["features"]:
            for c in f["properties"]["cnns"]:
                placed.add(str(c))
                if (f["properties"].get("north_star") or "").strip() != "None":
                    named.add(str(c))
    # Of a divided street's two carriageways that run between the same two
    # nodes, a row that names one names both.
    by_ends = collections.defaultdict(set)
    for r in cl:
        ends = frozenset((r.get("f_node_cnn"), r.get("t_node_cnn")))
        by_ends[(r["streetname"], ends)].add(str(r["cnn"]))
    for twins in by_ends.values():
        if len(twins) > 1 and twins & named:
            named |= twins

    # Each block's centerline in metres, with the distance along it at every
    # vertex, and a 50 m grid of its pieces.
    blocks, cells, skipped = {}, collections.defaultdict(list), 0
    for r in cl:
        if NOT_A_STREET.search(r["streetname"]):
            skipped += 1
            continue
        coords = r["line"]["coordinates"]
        pts = [(x * X_M, y * Y_M) for x, y in coords]
        if len(pts) < 2:
            continue
        cum = [0.0]
        for u, v in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(u, v))
        c = r["cnn"]
        blocks[c] = (pts, cum)
        for i, (u, v) in enumerate(zip(pts, pts[1:])):
            for gx in range(int(min(u[0], v[0]) // CELL_M), int(max(u[0], v[0]) // CELL_M) + 1):
                for gy in range(int(min(u[1], v[1]) // CELL_M), int(max(u[1], v[1]) // CELL_M) + 1):
                    cells[(gx, gy)].append((c, i))
    print("%d freeway and ramp centerlines excluded before snapping" % skipped)

    # Walk every drawn line in STEP_M steps and project each point onto every
    # block it runs along (direction within MIN_COS) within NAMED_TOL_M,
    # keeping its distance along the block. A point past either end of a
    # block belongs to the next block. So for each block and each tolerance
    # there is the span of the plan's line along it (first to last point)
    # and where along it each point fell. Walking the drawn line, not the
    # centerline, measures a 35 m intersection piece as well as a long block:
    # sampling the centerline every 15 m gave a short block two or three
    # samples, and one miss dropped it (Potrero at 23rd St, F1, 2026-09-29).
    ext = {TOL_M: {}, NAMED_TOL_M: {}}
    cls_hits = collections.defaultdict(collections.Counter)
    for cls, p, q, L in pieces:
        u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
        n = max(1, int(L / STEP_M))
        for j in range(n + 1):
            s = (p[0] + (q[0] - p[0]) * j / n, p[1] + (q[1] - p[1]) * j / n)
            gx, gy = int(s[0] // CELL_M), int(s[1] // CELL_M)
            near = {}
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for c, i in cells.get((gx + dx, gy + dy), ()):
                        A, B = blocks[c][0][i], blocks[c][0][i + 1]
                        sl = math.dist(A, B)
                        if sl < 1e-6:
                            continue
                        v = ((B[0] - A[0]) / sl, (B[1] - A[1]) / sl)
                        if abs(u[0] * v[0] + u[1] * v[1]) <= MIN_COS:
                            continue
                        t = (s[0] - A[0]) * v[0] + (s[1] - A[1]) * v[1]
                        if (i == 0 and t < 0) or (i == len(blocks[c][0]) - 2 and t > sl):
                            continue
                        t = max(0.0, min(sl, t))
                        d = math.dist(s, (A[0] + v[0] * t, A[1] + v[1] * t))
                        if d <= NAMED_TOL_M and (c not in near or d < near[c][0]):
                            near[c] = (d, blocks[c][1][i] + t)
            for c, (d, at) in near.items():
                for tol, e in ext.items():
                    if d <= tol:
                        x = e.setdefault(c, [at, at, []])
                        x[0], x[1] = min(x[0], at), max(x[1], at)
                        x[2].append(at)
                if d <= (NAMED_TOL_M if str(c) in named else TOL_M):
                    cls_hits[c][cls] += 1

    # A block is the plan's when the drawn line spans half of it (from its
    # first point to its last, an end within END_SNAP_M counting as reached)
    # and runs along half its length (drawn_along). A block Appendix
    # L names is measured at NAMED_TOL_M throughout, membership and span
    # alike, so a named block whose line sits 20-21 m off is not cut to the
    # part that happens to fall inside 20 m (12th Ave, Lincoln to Irving).
    drawn, per_class_len = {}, collections.Counter()
    by_cnn = {r["cnn"]: r for r in cl}
    for c in sorted(blocks, key=str):
        e = ext[NAMED_TOL_M if str(c) in named else TOL_M].get(c)
        if not e:
            continue
        whole = blocks[c][1][-1]
        if whole <= 0:
            continue
        first, last, ats = e
        lo = 0.0 if first <= END_SNAP_M else first
        hi = whole if whole - last <= END_SNAP_M else last
        span, along = (hi - lo) / whole, min(1.0, drawn_along(ats) / whole)
        if span < COVER or along < COVER:
            continue
        r = by_cnn[c]
        # The facility is the class that drew most of the block's points; a
        # tie goes to the class first in name order.
        best = sorted(cls_hits[c].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        coords = r["line"]["coordinates"]
        length = sum(math.hypot((coords[i + 1][0] - coords[i][0]) * LON_M,
                                (coords[i + 1][1] - coords[i][1]) * LAT_M)
                     for i in range(len(coords) - 1))
        drawn[c] = {"cnn": c, "street": r["streetname"], "facility": best,
                    "coverage": round(along, 2), "named": str(c) in named,
                    "length_m": round(length, 1), "line": coords,
                    "_on": (lo, hi, whole), "_nodes": (r.get("f_node_cnn"), r.get("t_node_cnn"))}
        per_class_len[best] += length

    # How much of each block the plan draws (`share`): the span above, from
    # the plan's first point on the block to its last, and reaching an end of
    # the block where another plan block meets it there. So a block counts
    # less than whole only where the plan's line stops partway along it,
    # short of its end and of any other plan block: at the end of a corridor,
    # or a stub. About the data states this rule (#directions).
    at_node = collections.defaultdict(set)
    for c, d in drawn.items():
        for nd in d["_nodes"]:
            if nd:
                at_node[nd].add(c)
    for c, d in drawn.items():
        lo, hi, whole = d.pop("_on")
        f_node, t_node = d.pop("_nodes")
        if at_node.get(f_node, set()) - {c}:
            lo = 0.0
        if at_node.get(t_node, set()) - {c}:
            hi = whole
        d["share"] = round(max(0.0, hi - lo) / whole, 3) if whole > 0 else 1.0
    partial = [d for d in drawn.values() if d["share"] < 1]
    print("the plan's line stops partway along %d blocks; they count %.1f of their %.1f miles"
          % (len(partial), sum(d["length_m"] * d["share"] for d in partial) / 1609.34,
             sum(d["length_m"] for d in partial) / 1609.34))

    total_m = sum(v["length_m"] for v in drawn.values())
    print("traced onto centerlines: %d segments, %.1f miles" % (len(drawn), total_m / 1609.34))
    for cls, m in per_class_len.most_common():
        print("   %-16s %6.1f mi  (drawn %.1f mi)" % (cls, m / 1609.34, drawn_m[cls] / 1609.34))

    traced = set(drawn)
    print("the map confirms %d of the %d segments placed by name (%.0f%%)"
          % (len(placed & traced), len(placed), 100.0 * len(placed & traced) / max(1, len(placed))))
    print("Appendix L names %d blocks with a North Star facility; the map draws %d of them"
          % (len(named), len(named & traced)))
    new = traced - placed
    print("the map adds %d segments the name matching never placed, %.1f miles"
          % (len(new), sum(drawn[c]["length_m"] for c in new) / 1609.34))

    stable.write_json(os.path.join(args.out, "traced.geojson"), {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: v for k, v in d.items() if k != "line"},
         "geometry": {"type": "LineString", "coordinates": d["line"]}}
        for d in drawn.values()]}, end="", ensure_ascii=True)
    stable.write_json(os.path.join(args.out, "georeference.json"), {"transform": a, "report": report, "tolerance_m": TOL_M,
               "named_tolerance_m": NAMED_TOL_M,
               "named_blocks": len(named), "named_on_map": len(named & set(drawn)),
               "min_cos": MIN_COS, "step_m": STEP_M,
               "coverage_threshold": COVER, "end_snap_m": END_SNAP_M,
               "partial_blocks": len(partial),
               # Which PDF this is, so a check that reads the map can tell
               # whether SFMTA has published a different one since.
               "map_sha256": hashlib.sha256(open(args.map, "rb").read()).hexdigest(),
               # The day this copy of the PDF was fetched from sfmta.com, from
               # the cached file's own date, so a page citing the plan dates
               # its read without a hand-typed date (tools/bike-network/bike-progress.py).
               "map_read": datetime.date.fromtimestamp(os.path.getmtime(args.map)).isoformat(),
               "drawn_miles": {k: round(v / 1609.34, 2) for k, v in drawn_m.items()},
               "traced_miles": {k: round(v / 1609.34, 2) for k, v in per_class_len.items()},
               "confirmed_of_named": len(placed & traced), "named_total": len(placed),
               "added_by_map": len(new)}, end="", ensure_ascii=True, indent=1)

    # What the map draws that no centerline explains: park paths, the Presidio
    # and Treasure Island roads the city's street file does not carry, the
    # Wiggle, the Hairball. Appendix L names 29 such rows and places none of
    # them. Kept as raw geometry, with no CNN, because there is nothing to
    # snap them to.
    accepted = Grid([p for d in drawn.values()
                     for p in densify(d["line"], 10.0)], cell=0.0006)
    off = []
    for cls, polys in net.items():
        for P in polys:
            ll = [((x - a[1]) / a[0], (y - a[3]) / a[2]) for x, y in P]
            S = densify(ll, 12.0)
            if len(S) < 2:
                continue
            on = 0
            for lon, lat in S:
                for i in accepted.near(lon, lat):
                    px, py = accepted.pts[i]
                    if ((px - lon) * LON_M) ** 2 + ((py - lat) * LAT_M) ** 2 < TOL_M ** 2:
                        on += 1
                        break
            if on / len(S) < 0.5:
                length = sum(math.hypot((ll[i + 1][0] - ll[i][0]) * LON_M,
                                        (ll[i + 1][1] - ll[i][1]) * LAT_M)
                             for i in range(len(ll) - 1))
                if length >= 40:
                    off.append({"facility": cls, "length_m": round(length, 1),
                                "line": [[round(x, 6), round(y, 6)] for x, y in ll]})
    off_m = sum(o["length_m"] for o in off)
    print("off-street: %d drawn lines, %.1f miles, on nothing in the centerline file"
          % (len(off), off_m / 1609.34))
    stable.write_json(os.path.join(args.out, "off-street.geojson"), {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"facility": o["facility"], "length_m": o["length_m"],
                        "source": "map geometry, no centerline"},
         "geometry": {"type": "LineString", "coordinates": o["line"]}} for o in off]}, end="", ensure_ascii=True)

    agg = collections.defaultdict(lambda: [0, 0.0, collections.Counter()])
    for c in sorted(new):  # sorted: a tie in most_common goes to the first class counted
        d = drawn[c]
        agg[d["street"]][0] += 1
        agg[d["street"]][1] += d["length_m"]
        agg[d["street"]][2][d["facility"]] += 1
    stable.write_text(os.path.join(args.out, "new-from-map.csv"), "street,facility,segments,miles\n" + "".join(
        '"%s",%s,%d,%.2f\n' % (street, fac.most_common(1)[0][0], n, m / 1609.34)
        for street, (n, m, fac) in sorted(agg.items(), key=lambda kv: (-kv[1][1], kv[0]))))
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
