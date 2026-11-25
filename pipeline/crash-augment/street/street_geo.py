"""Plain-Python geometry for the crash street-context build: which census tract holds a point, and how far a point is from a street centerline.

    from street_geo import TractIndex, feet_to_line
    T = TractIndex([(geoid, rings), ...])   # rings in lon/lat, as ArcGIS returns them with outSR=4326
    T.find(lon, lat)                        # the geoid of the tract holding the point, or None
    feet_to_line(lon, lat, [[lon, lat], ...])

Point in polygon is the even-odd rule over every ring of a tract, so holes are handled. A bounding-box test runs
first. A point that two tracts both claim (a boundary drawn twice) goes to the lower geoid, so the answer does not
depend on read order. Distances use an equirectangular projection at San Francisco's latitude, which is good to well
under a foot over the city's few miles.
"""

import math

LAT0 = 37.76
FT_PER_DEG_LAT = 364_000.0
FT_PER_DEG_LON = FT_PER_DEG_LAT * math.cos(math.radians(LAT0))


def _inside(x, y, rings):
    c = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
    return c


class TractIndex(object):
    def __init__(self, tracts):
        self.tracts = []
        for geoid, rings in sorted(tracts, key=lambda t: t[0]):
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            self.tracts.append((geoid, rings, (min(xs), min(ys), max(xs), max(ys))))

    def find(self, lon, lat):
        for geoid, rings, (x0, y0, x1, y1) in self.tracts:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, rings):
                return geoid
        return None


def feet_to_line(lon, lat, coords):
    """Shortest distance in feet from a point to a polyline of [lon, lat] pairs."""
    px, py = lon * FT_PER_DEG_LON, lat * FT_PER_DEG_LAT
    best = float("inf")
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        ax, ay, bx, by = ax * FT_PER_DEG_LON, ay * FT_PER_DEG_LAT, bx * FT_PER_DEG_LON, by * FT_PER_DEG_LAT
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def line_coords(geom):
    """The vertex lists of a GeoJSON LineString or MultiLineString."""
    if not geom:
        return []
    if geom.get("type") == "LineString":
        return [geom["coordinates"]]
    if geom.get("type") == "MultiLineString":
        return list(geom["coordinates"])
    return []
