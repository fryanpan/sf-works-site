"""Distance to a school measured from the edge of its grounds, as California's school-zone law measures it.

Every School Trips script that asks "how far from a school" asks it here, so one rule holds across them.
data/school-sim/grounds.json (tools/school-trips/school-grounds.py) holds each school's grounds, keyed by its point.
A point on the grounds is 0 ft away. A school with no outline falls back to its point.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json, math, os

import numpy as np

ROOT = paths.ROOT
PATH = os.path.join(ROOT, "data", "school-sim", "grounds.json")
FT_LAT = 364000.0
FT_LON = 364000.0 * math.cos(math.radians(37.76))
_G = None


def key(lon, lat):
    return "%.5f,%.5f" % (lon, lat)


def load():
    global _G
    if _G is None:
        _G = json.load(open(PATH))["schools"]
    return _G


def rings(lon, lat):
    """The grounds' outer rings for the school at (lon, lat), or [] when it has none."""
    g = load().get(key(lon, lat))
    if g is None:
        raise KeyError("no grounds row for the school at %s: rerun tools/school-trips/school-grounds.py" % key(lon, lat))
    return g["rings"]


def _segments(rs):
    a = np.array([p for r in rs for p in r], float)
    b = np.array([p for r in rs for p in (r[1:] + r[:1])], float)
    return a, b


def dist_ft(lon, lat, plon, plat):
    """Feet from each point (plon, plat; scalars or arrays) to the grounds of the school at (lon, lat)."""
    plon, plat = np.asarray(plon, float), np.asarray(plat, float)
    rs = rings(lon, lat)
    if not rs:
        return np.hypot((plon - lon) * FT_LON, (plat - lat) * FT_LAT)
    a, b = _segments(rs)
    px, py = plon.reshape(-1, 1), plat.reshape(-1, 1)
    ax, ay, bx, by = a[:, 0], a[:, 1], b[:, 0], b[:, 1]
    vx, vy = (bx - ax) * FT_LON, (by - ay) * FT_LAT
    wx, wy = (px - ax) * FT_LON, (py - ay) * FT_LAT
    L = vx * vx + vy * vy
    t = np.clip(np.where(L > 0, (wx * vx + wy * vy) / np.where(L > 0, L, 1), 0), 0, 1)
    d = np.hypot(wx - t * vx, wy - t * vy).min(axis=1)
    # Inside test per ring (even-odd), so a point on the grounds is 0 ft away.
    inside = np.zeros(px.shape[0], bool)
    for r in rs:
        q = np.array(r, float)
        x1, y1 = q[:, 0], q[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        cross = ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / np.where(y2 != y1, y2 - y1, 1) + x1)
        inside ^= (cross.sum(axis=1) % 2 == 1)
    d = np.where(inside, 0.0, d)
    return d.reshape(plon.shape) if plon.shape else float(d[0])


def dist_xy_ft(lon, lat, x_ft, y_ft, x0_lon, y0_lat):
    """The same for points in a local feet grid centred at (x0_lon, y0_lat), y north."""
    return dist_ft(lon, lat, x0_lon + np.asarray(x_ft) / FT_LON, y0_lat + np.asarray(y_ft) / FT_LAT)


def nearest(schools, plon, plat, max_ft):
    """For points (plon, plat), the index into schools [(lon, lat), ...] of the school whose grounds are nearest within
    max_ft, or -1, and that distance in feet. Ties go to the earlier school."""
    plon, plat = np.asarray(plon, float), np.asarray(plat, float)
    best = np.full(plon.shape, -1, int)
    bd = np.full(plon.shape, np.inf)
    for j, (lon, lat) in enumerate(schools):
        # Only points that could be within max_ft of a campus up to a mile across are measured exactly.
        near = np.hypot((plon - lon) * FT_LON, (plat - lat) * FT_LAT) <= max_ft + 5280
        if not near.any():
            continue
        d = np.full(plon.shape, np.inf)
        d[near] = dist_ft(lon, lat, plon[near], plat[near])
        take = (d <= max_ft) & (d < bd)
        best[take], bd[take] = j, d[take]
    return best, np.where(best >= 0, bd, np.nan)
