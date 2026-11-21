"""Point-in-polygon lookup over a set of scored (multi)polygons, pure Python.

    idx = PolygonIndex([(value, multipolygon_coords), ...])
    idx.at(lon, lat)   # -> [value, ...] of every polygon part containing the point

Each part of a multipolygon is indexed on its own, so one multipolygon whose
parts are spread across the city (y6ci-vpnb's parks, score 999) does not land
in every grid cell. A part is tested by the even-odd rule over its rings, so
holes are holes. A coarse grid of bounding boxes keeps a lookup to the few
parts near the point. A point exactly on a shared edge can land in two parts
or none; callers decide what to do with zero or two hits.
"""

import collections

CELL = 0.005  # degrees, about 1,800 by 1,400 feet at San Francisco's latitude


def _inside(x, y, ring):
    c = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


class PolygonIndex(object):
    def __init__(self, items):
        self.parts = []
        self.grid = collections.defaultdict(list)
        for value, mp in items:
            for poly in mp:
                rings = [ring for ring in poly if len(ring) >= 4]
                if not rings:
                    continue
                xs = [p[0] for p in rings[0]]
                ys = [p[1] for p in rings[0]]
                box = (min(xs), min(ys), max(xs), max(ys))
                k = len(self.parts)
                self.parts.append((value, box, rings))
                for gx in range(int(box[0] // CELL), int(box[2] // CELL) + 1):
                    for gy in range(int(box[1] // CELL), int(box[3] // CELL) + 1):
                        self.grid[(gx, gy)].append(k)

    def at(self, lon, lat):
        out = []
        for k in self.grid.get((int(lon // CELL), int(lat // CELL)), ()):
            value, box, rings = self.parts[k]
            if not (box[0] <= lon <= box[2] and box[1] <= lat <= box[3]):
                continue
            inside = False
            for r in rings:
                if _inside(lon, lat, r):
                    inside = not inside
            if inside:
                out.append(value)
        return out


def pick_score(hits, special=999):
    """The score a point takes from its hits: the highest ordinary score, else the special one, else None."""
    ordinary = [h for h in hits if h != special]
    if ordinary:
        return max(ordinary)
    return special if hits else None
