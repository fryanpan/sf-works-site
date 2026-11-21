#!/usr/bin/env python3
"""Read SFMTA's Safe School Connections school map and compare it, school by school, with the bike explorer's counts.

SFMTA published its five school groups only as a picture (the Draft Approach's
"School Connectivity Map", 2550x2714 JPEG) and publishes no school list or
network layer, so this script reads the picture:

  1. Finds the school icons by colour (purple = existing network, orange =
     potential, grey = beyond one block) and tells "on" from "within one
     block" by the dark ring the map draws round the second.
  2. Georeferences the picture by iterative closest point between the icon
     centres and our own school points (site/data/bike-history/reach.json),
     fitting a 6-parameter affine. Median residual about 30 m.
  3. Pulls SFMTA's drawn network off the picture: solid dark green (existing)
     and dashed lighter green (potential).
  4. For each of our open schools: the nearest SFMTA icon and its group; our
     walking level against today's network and the North Star as the explorer
     counts it (walk-reach.json); and straight-line distance to SFMTA's drawn
     network, to our counted network, and to our Shared L3 and Undecided lines.

Writes out/ssc-school-map/compare.csv and out/ssc-school-map/summary.json.
A one-off exploratory read (pipeline/README.md): no page reads it on
a schedule, so it has no --update.

Needs numpy, scipy and pillow:
    uv run --with numpy --with scipy --with pillow python tools/school-trips/ssc-school-map-compare.py
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, json, math, os, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

ROOT = paths.ROOT
MAP_URL = "https://www.sfmta.com/files/images/2026-08/School%20Connectivity%20Map.jpg"
CACHE = os.path.join(ROOT, ".cache", "ssc-map", "school-connectivity-map.jpg")
OUT = os.path.join(ROOT, "out", "ssc-school-map")
LAT0 = 37.76
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540
ICON_AREA = 365          # pixels of one unoccluded icon's fill
MATCH_M = 120            # an icon this close to one of our schools is taken as the same school
RING = 0.12              # share of dark pixels in the ring annulus that marks "within one block"
LINE_TOL_M = 40          # SFMTA's dashed pixel counts as one of our lines within this


def m(lon, lat):
    return np.array([(lon + 122.44) * KX, (lat - LAT0) * KY])


def load_map():
    if not os.path.exists(CACHE):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        req = urllib.request.Request(MAP_URL, headers={"User-Agent": "Mozilla/5.0"})
        open(CACHE, "wb").write(urllib.request.urlopen(req).read())
    return np.array(Image.open(CACHE).convert("RGB")).astype(int)


def icons_of(im):
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    legend = np.zeros_like(R, bool); legend[0:560, 830:1500] = True
    masks = {
        "purple": (R > 95) & (R < 185) & (G < 110) & (B > 120) & (B - G > 50) & (R - G > 30),
        "orange": (R > 190) & (G > 40) & (G < 150) & (B < 100) & (R - G > 80),
        "gray": (abs(R - G) < 10) & (abs(G - B) < 10) & (R > 105) & (R < 150),
    }
    dark = (R < 100) & (G < 100) & (B < 110) & (abs(R - G) < 25) & (abs(G - B) < 30)
    out = []
    for colour, mk in masks.items():
        mk = ndi.binary_opening(mk & ~legend, iterations=1)
        lab, n = ndi.label(ndi.binary_closing(mk, iterations=3))
        sizes = ndi.sum(mk, lab, range(1, n + 1))
        for i, s in enumerate(sizes):
            if s <= 60:
                continue
            cy, cx = ndi.center_of_mass(mk, lab, i + 1)
            y0, x0 = max(0, int(cy) - 32), max(0, int(cx) - 32)
            sub = dark[y0:int(cy) + 32, x0:int(cx) + 32]
            yy, xx = np.ogrid[y0 - cy:y0 - cy + sub.shape[0], x0 - cx:x0 - cx + sub.shape[1]]
            r = np.sqrt(xx ** 2 + yy ** 2)
            ring = float(sub[(r > 17) & (r < 28)].mean())
            group = {"purple": "existing", "orange": "potential", "gray": "beyond"}[colour]
            if colour != "gray":
                group = ("one-block-" if ring > RING else "on-") + group
            out.append({"x": cx, "y": cy, "group": group, "ring": ring, "n": max(1, round(s / ICON_AREA))})
    return out


def fit(icons, P):
    """Affine pixel -> metres by ICP from a north-up first guess over the city's extent."""
    I = np.array([[o["x"], o["y"]] for o in icons])
    sx = (m(-122.357, LAT0)[0] - m(-122.511, LAT0)[0]) / 2480
    A = np.array([[sx, 0], [0, -sx]]); t = np.array([m(-122.511, LAT0)[0] - sx * 60, m(-122.44, 37.708)[1] + sx * 2680])
    tree = cKDTree(P)
    for it in range(60):
        d, j = tree.query(I @ A.T + t)
        ok = d < (max(60, np.percentile(d, 70)) if it < 30 else 60)
        X = np.hstack([I[ok], np.ones((ok.sum(), 1))])
        sol, *_ = np.linalg.lstsq(X, P[j[ok]], rcond=None)
        A, t = sol[:2].T, sol[2]
    return A, t, float(np.median(d[ok])), int(ok.sum())


def sample(features, pred, step=5.0):
    pts = []
    for f in features:
        if not pred(f["properties"]):
            continue
        g = f["geometry"]
        for L in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            P = [m(*c) for c in L]
            for a, b in zip(P[:-1], P[1:]):
                n = max(1, int(np.linalg.norm(b - a) / step))
                pts.extend(a + (b - a) * k / n for k in range(n + 1))
    return np.array(pts)


def main():
    im = load_map()
    data = os.path.join(ROOT, "site", "data")
    reach = json.load(open(os.path.join(data, "bike-history", "reach.json")))
    walk = json.load(open(os.path.join(data, "bike-history", "walk-reach.json")))
    traced = json.load(open(os.path.join(data, "north-star", "traced.geojson")))["features"]
    allages = json.load(open(os.path.join(data, "bike-history", "all-ages.geojson")))["features"]
    nb = len(reach["blocks"]["rows"])
    open_idx = [i for i, s in enumerate(reach["schools"]) if not s["closed"] and (not s["open"] or int(s["open"][:4]) <= 2026)]
    P = np.array([m(reach["schools"][i]["lon"], reach["schools"][i]["lat"]) for i in open_idx])

    icons = icons_of(im)
    A, t, resid, nfit = fit(icons, P)
    Ai = np.linalg.inv(A)
    I = np.array([[o["x"], o["y"]] for o in icons])

    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    legend = np.zeros_like(R, bool); legend[0:560, 830:1500] = True
    solid = (R < 75) & (G > 80) & (G < 140) & (B < 45) & (G - R > 45) & ~legend
    dashed = (R >= 70) & (R < 130) & (G > 110) & (G < 170) & (B > 25) & (B < 100) & (G - R > 30) & (G - B > 50) & ~legend
    dashed &= ~ndi.binary_dilation(solid, iterations=3)
    to_m = lambda mask: (lambda ys, xs: np.c_[xs, ys].astype(float) @ A.T + t)(*np.nonzero(mask))
    Pd, Ps = to_m(dashed), to_m(solid)
    core = lambda p: p["facility"] in ("Separated", "Car-free", "Shared-use Path", "Shared")
    today_pts = sample(allages, lambda p: not p.get("until"))
    trees = {
        "sfmta_drawn": cKDTree(np.vstack([Pd, Ps])),
        "ours_counted": cKDTree(np.vstack([sample(traced, core), today_pts])),
        "ours_L3_undecided": cKDTree(sample(traced, lambda p: p["facility"] in ("Shared L3", "Undecided"))),
    }
    d_dash, _ = trees["ours_counted"].query(Pd)
    d_dash_all, _ = cKDTree(np.vstack([sample(traced, lambda p: True), today_pts])).query(Pd)

    def lv(group, codes, i):
        v = [int(walk[group][c][nb + i]) for c in codes if c in walk[group]]
        return min(v) if v else len(walk["thresholds"])

    # The table keeps its three bands; a level at a distance it does not name
    # (1,000 feet) reads as the next band out that it does.
    ids = [t["id"] for t in walk["thresholds"]]
    names = {"block": "1 block", "2blocks": "2 blocks", "quarter": "quarter mile"}
    band = lambda level: next((names[t] for t in ids[level:] if t in names), "beyond")

    rows = []
    for k, i in enumerate(open_idx):
        s = reach["schools"][i]
        q = Ai @ (P[k] - t)
        dpx = np.sqrt(((I - q) ** 2).sum(1)); j = int(dpx.argmin())
        today = lv("today", ["1", "4", "S", "2c", "3c"], i)
        plan = min(today, lv("plan", ["1", "4", "S"], i))
        dist = {n: round(float(tr.query(P[k])[0])) for n, tr in trees.items()}
        rows.append({
            "school": s["name"], "private": s["private"], "lon": s["lon"], "lat": s["lat"],
            "sfmta_group": icons[j]["group"] if dpx[j] * 5.4 < MATCH_M else "",
            "icon_offset_m": round(float(dpx[j]) * 5.4),
            "our_walk_today": band(today),
            "our_walk_plan": band(plan),
            "our_walk_plan_with_L3": band(min(plan, lv("plan", ["L"], i))),
            "m_to_sfmta_drawn_network": dist["sfmta_drawn"],
            "m_to_our_counted_network": dist["ours_counted"],
            "m_to_our_L3_or_undecided": dist["ours_L3_undecided"],
        })
    os.makedirs(OUT, exist_ok=True)
    rows.sort(key=lambda r: r["school"])
    with open(os.path.join(OUT, "compare.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    n = len(rows)
    within = lambda key, th: sum(r[key] <= th for r in rows)
    matched = [r for r in rows if r["sfmta_group"]]
    agree = {}
    for th in range(100, 241, 20):
        agree[th] = round(sum((r["m_to_sfmta_drawn_network"] <= th) == (r["sfmta_group"] != "beyond") for r in matched) / len(matched), 3)
    groups = {}
    for o in icons:
        groups[o["group"]] = groups.get(o["group"], 0) + o["n"]
    summary = {
        "map": MAP_URL, "icons_read": groups, "icons_read_total": sum(groups.values()),
        "georeference": {"median_residual_m": round(resid, 1), "pairs": nfit},
        "our_open_schools": n, "matched_to_an_sfmta_icon": len(matched),
        "sfmta_dashed_pixels_with_none_of_our_counted_lines_within_40m": round(float((d_dash > LINE_TOL_M).mean()), 3),
        "sfmta_dashed_pixels_with_none_of_our_lines_within_40m": round(float((d_dash_all > LINE_TOL_M).mean()), 3),
        "straight_line_threshold_agreement_with_sfmta_groups": agree,
        "steps_on_our_221": {
            "walk_440ft_our_counted_network": sum(r["our_walk_plan"] == "1 block" for r in rows),
            "straight_134m_our_counted_network": within("m_to_our_counted_network", 134),
            "straight_160m_our_counted_network": within("m_to_our_counted_network", 160),
            "straight_160m_plus_L3_undecided": sum(min(r["m_to_our_counted_network"], r["m_to_our_L3_or_undecided"]) <= 160 for r in rows),
            "straight_160m_sfmta_drawn_network": within("m_to_sfmta_drawn_network", 160),
        },
    }
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
