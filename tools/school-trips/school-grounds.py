#!/usr/bin/env python3
"""Each School Trips school's grounds as a polygon, so every zone is measured from the edge of the grounds, as state law measures it.

    tools/school-trips/school-grounds.py            # writes data/school-sim/grounds.json
    tools/school-trips/school-grounds.py --refresh  # re-read OpenStreetMap's school outlines first

It also writes site/data/school-zones.json, the School Trips maps' layer: each of
the simulation's schools' grounds and the ZONE_FT school zone round them, the
grounds grown by ZONE_FT (Bryan, 2026-10-13: "Please show this slow zone around
each school in the city map and per-school map").

Bryan, 2026-10-13, on the evidence doc: "Please update to measure using same
definition as state law across all of the things we're working on". California
Vehicle Code §22352(b)(2) sets the school limit "When approaching or passing a
school building or the grounds thereof" and lets the signs stand "at any
distance up to 500 feet away from school grounds"; §22358.4(b)(5) measures the
15 mph signs "up to 500 feet away from school grounds" and the 25 mph ones
"between 500 and 1,000 feet away from the school grounds" (read 2026-10-13 on
california.public.law). So a distance to a school is a distance to its grounds,
and a point on the grounds is 0 ft away.

INPUTS. The schools and their points are site/data/school-sim/index.json's (the
simulation's, private schools marked) and lib/school-travel-time.py's load_schools() (the 207,
private schools too, that the crash counts use), keyed by point.
Outlines come from OpenStreetMap ways and relations tagged amenity=school,
cached at data/osm-cache/sf-schools.json, and from DataSF's parcels, acdm-wktn,
read through scripts/sfdata.py.

THE MATCH. A school takes the OpenStreetMap outline that shares a distinctive
word of its name (not "elementary", "school" and the like) and whose edge is
within MATCH_FT of its door. A school with no such outline takes a city lot touching a PARCEL_FT circle
round its door (parcel() says which), marked "parcel" so a reader can see which
grounds are the city's lot rather than a mapped campus. Lots zoned open space
are never grounds, so a park across the street can't be taken for the campus. A school with
neither keeps its door as a point, marked "door".

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build read by the
simulation and the injury counts. In pipeline/transportation-update.py before
school-sim; it reads the tracked site/data/school-sim/index.json, so it uses the
previous run's school list, and a school new to the simulation stops school-sim
at its grounds check until this step runs again. --refresh re-reads
OpenStreetMap; there is no edited-since check.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import importlib.util, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata
from lib import school_grounds
from lib import school_points

MATCH_FT = 400
PARCEL_FT = 150
PARCEL_MAX_SQFT = 650000   # about 15 acres: a bigger lot by a door is a park, as McLaren Park is by June Jordan
PARCEL_MIN_SQFT = 8000     # smaller is a house or a shop, not a campus
PUBLIC_P_FT = 75
TIE_FT = 5
CACHE = os.path.join(ROOT, "data", "osm-cache", "sf-schools.json")
OUT = os.path.join(ROOT, "data", "school-sim", "grounds.json")
ZONES = os.path.join(ROOT, "site", "data", "school-zones.json")
ZONE_FT = 500   # §22358.4(b)(5)(B): the 15 mph signs stand "up to 500 feet away from school grounds"
FT_LAT = 364000.0
FT_LON = 364000.0 * math.cos(math.radians(37.76))
COMMON = {"elementary", "school", "schools", "middle", "high", "academy", "the", "of", "san", "francisco", "sf",
          "charter", "alternative", "early", "education", "jr", "k", "8", "public", "traditional", "and", "for",
          "international", "community", "center", "campus", "st", "street", "at", "a"}


def words(name):
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in COMMON and len(w) > 1}


def osm_outlines(refresh):
    if refresh or not os.path.exists(CACHE):
        o = paths.load("osm-sfmta-compare.py", "osm_compare")
        d = o.overpass(o.AREA.format(t=180) + '(way["amenity"="school"](area.sf);relation["amenity"="school"](area.sf););\nout geom;', 180)
        d = json.loads(d) if isinstance(d, (str, bytes)) else d
        assert len(d["elements"]) > 200, "fewer than 200 school outlines: the read is short"
        # `out geom tags` drops a relation's members; `out geom` keeps them, so a multipolygon campus has its rings.
        assert all(any(m.get("role") == "outer" for m in e.get("members", [])) for e in d["elements"] if e["type"] == "relation"), \
            "a school relation came back with no outer members"
        with open(CACHE, "w") as f:
            json.dump(d, f)
    out = []
    for e in json.load(open(CACHE))["elements"]:
        if e["type"] == "way":
            rings = [e.get("geometry") or []]
        else:
            rings = stitch([[(p["lon"], p["lat"]) for p in m.get("geometry") or []]
                            for m in e.get("members", []) if m.get("role") == "outer"])
            rings = [[{"lon": x, "lat": y} for x, y in r] for r in rings]
        rings = [[[round(p["lon"], 6), round(p["lat"], 6)] for p in r] for r in rings if len(r) >= 4]
        if rings:
            out.append({"name": e.get("tags", {}).get("name", ""), "id": "%s/%d" % (e["type"], e["id"]), "rings": rings})
    return out


def stitch(parts):
    """A relation's outer ways joined end to end into closed rings. A ring split over several ways is one campus edge."""
    parts = [list(q) for q in parts if len(q) >= 2]
    rings = []
    while parts:
        cur = parts.pop(0)
        while cur[0] != cur[-1]:
            for i, q in enumerate(parts):
                if q[0] == cur[-1]:
                    cur += q[1:]
                elif q[-1] == cur[-1]:
                    cur += q[::-1][1:]
                else:
                    continue
                parts.pop(i)
                break
            else:
                break    # an open piece that joins nothing: keep what closes, drop the rest
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur[:-1])
    return rings


def seg_ft(p, a, b):
    px, py = (p[0] - a[0]) * FT_LON, (p[1] - a[1]) * FT_LAT
    bx, by = (b[0] - a[0]) * FT_LON, (b[1] - a[1]) * FT_LAT
    L = bx * bx + by * by
    t = 0.0 if L == 0 else max(0.0, min(1.0, (px * bx + py * by) / L))
    return math.hypot(px - t * bx, py - t * by)


def inside(p, ring):
    x, y, c = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def dist_ft(p, rings):
    """Feet from point p (lon, lat) to the grounds: 0 on or inside them."""
    if any(inside(p, r) for r in rings):
        return 0.0
    return min(seg_ft(p, a, b) for r in rings for a, b in zip(r, r[1:] + r[:1]))


def area_sqft(ring):
    xy = [((x - ring[0][0]) * FT_LON, (y - ring[0][1]) * FT_LAT) for x, y in ring]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xy, xy[1:] + xy[:1]))) / 2


def parcel(s, public):
    """The school's lot: the nearest active lot of PARCEL_MIN_SQFT to PARCEL_MAX_SQFT to the door, not open space, a lot
    within TIE_FT of the nearest going to the bigger one. A public school takes the nearest P (public) lot within
    PUBLIC_P_FT first, since SFUSD's campuses are zoned P and a shop or flat can sit closer to the door."""
    r = PARCEL_FT
    circ = ", ".join("%.6f %.6f" % (s["lon"] + r * math.cos(t) / FT_LON, s["lat"] + r * math.sin(t) / FT_LAT)
                     for t in [2 * math.pi * k / 16 for k in range(17)])
    V = sfdata.fetch("acdm-wktn", select="blklot,zoning_code,shape",
                     where="active='True' AND intersects(shape, 'POLYGON((%s))')" % circ)
    door, cand = [s["lon"], s["lat"]], []
    for v in V.rows:
        g = v.get("shape") or {}
        polys = g.get("coordinates", []) if g.get("type") == "MultiPolygon" else [g.get("coordinates", [])]
        rings = [[[round(x, 6), round(y, 6)] for x, y in p[0]] for p in polys if p]
        a = sum(area_sqft(q) for q in rings)
        z = v.get("zoning_code") or ""
        if rings and PARCEL_MIN_SQFT <= a <= PARCEL_MAX_SQFT and "OS" not in z:
            cand.append((dist_ft(door, rings), a, v["blklot"], z, rings))
    pz = [c for c in cand if public and c[3].split("|")[0] == "P" and c[0] <= PUBLIC_P_FT]
    pool = pz or cand
    if not pool:
        return None, V.tag
    near = min(c[0] for c in pool)
    d, a, blklot, z, rings = max((c for c in pool if c[0] <= near + TIE_FT), key=lambda c: (c[1], c[2]))
    return (a, blklot, z, rings), V.tag


def write_zones(rows):
    """The grounds and the ZONE_FT zone round them, for the simulation's schools, as GeoJSON in [lon, lat]."""
    from shapely.geometry import Polygon, mapping
    from shapely.ops import unary_union
    from shapely import affinity
    idx = school_points.index_schools()
    feats = []
    for s in idx:
        r = rows[school_grounds.key(s["lon"], s["lat"])]
        to_ft = lambda ring: [((x - s["lon"]) * FT_LON, (y - s["lat"]) * FT_LAT) for x, y in ring]
        if r["rings"]:
            g = unary_union([Polygon(to_ft(q)).buffer(0) for q in r["rings"]])
        else:
            from shapely.geometry import Point
            g = Point(0, 0).buffer(1)
        z = g.buffer(ZONE_FT, quad_segs=6).simplify(8)
        back = lambda geom: affinity.translate(affinity.scale(geom, 1 / FT_LON, 1 / FT_LAT, origin=(0, 0)), s["lon"], s["lat"])
        rnd = lambda m: json.loads(json.dumps(m), parse_float=lambda v: round(float(v), 5))
        for kind, geom in (("zone", z), ("grounds", g.simplify(3))):
            feats.append({"type": "Feature", "properties": {"cds": s["cds"], "kind": kind, "source": r["source"]},
                          "geometry": rnd(mapping(back(geom)))})
    assert len(feats) == 2 * len(idx)
    with open(ZONES, "w") as f:
        json.dump({"type": "FeatureCollection", "zoneFt": ZONE_FT,
                   "note": "Written by tools/school-trips/school-grounds.py: each school's grounds and the area within %d ft of them." % ZONE_FT,
                   "features": feats}, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print("school-grounds: wrote %s, %d KB" % (os.path.relpath(ZONES, ROOT), os.path.getsize(ZONES) // 1024))


def main():
    outl = osm_outlines("--refresh" in sys.argv)
    sch = {}
    # index.json's rows carry no private flag; data/school-sim/private-schools.json lists the private ones.
    priv = {r["cds"] for r in json.load(open(os.path.join(ROOT, "data", "school-sim", "private-schools.json")))["schools"]}
    for s in school_points.index_schools():
        sch[school_grounds.key(s["lon"], s["lat"])] = {"name": s["name"], "lon": s["lon"], "lat": s["lat"],
                                                       "public": not s.get("private") and s["cds"] not in priv}
    stt = paths.load("school-travel-time.py", "stt")
    for s in stt.load_schools()[0]:
        sch.setdefault(school_grounds.key(s["lon"], s["lat"]),
                       {"name": s["name"], "lon": s["lon"], "lat": s["lat"], "public": not s["private"]})
    rows, tags = {}, set()
    for k, s in sorted(sch.items()):
        door, w = [s["lon"], s["lat"]], words(s["name"])
        cand = sorted((dist_ft(door, o["rings"]), o["id"], o) for o in outl if w & words(o["name"]))
        if cand and cand[0][0] <= MATCH_FT:
            d, _i, o = cand[0]
            rows[k] = {"name": s["name"], "public": s["public"], "source": "osm", "ref": o["id"], "label": o["name"],
                              "doorFt": round(d), "rings": o["rings"]}
            continue
        best, tag = parcel(s, s["public"])
        tags.add(tag)
        if best:
            rows[k] = {"name": s["name"], "public": s["public"], "source": "parcel", "ref": best[1], "label": best[2] or "",
                              "doorFt": round(dist_ft(door, best[3])), "rings": best[3]}
        else:
            rows[k] = {"name": s["name"], "public": s["public"], "source": "door", "ref": "", "label": "", "doorFt": 0, "rings": []}
    n = {k: sum(r["source"] == k for r in rows.values()) for k in ("osm", "parcel", "door")}
    # Quality: every school present, most on a mapped campus, the door near its grounds, the grounds a campus in size.
    assert len(rows) == len(sch)
    pub = [r for r in rows.values() if r["public"]]
    assert sum(r["source"] == "osm" for r in pub) >= 0.75 * len(pub), "fewer than three quarters of public schools on an OpenStreetMap outline: %s" % n
    far = [r["name"] for r in rows.values() if r["doorFt"] > MATCH_FT]
    assert not far, "door far from its grounds: %s" % far
    for k, r in rows.items():
        if r["rings"]:
            a = sum(area_sqft(q) for q in r["rings"])
            assert 1000 < a < 3e6, "%s grounds are %d sq ft" % (r["name"], a)
            # school_grounds.nearest() only measures points within 5,280 ft of the school's point plus the cap.
            lon, lat = map(float, k.split(","))
            far = max(math.hypot((x - lon) * FT_LON, (y - lat) * FT_LAT) for q in r["rings"] for x, y in q)
            assert far < 2500, "%s grounds reach %d ft from its point" % (r["name"], far)
    out = {"note": "Written by tools/school-trips/school-grounds.py. rings: [lon, lat] outer rings of each school's grounds, keyed by the school's point "
                   "(lon,lat to 5 places); a distance to a school is a distance to these, 0 inside.",
           "law": "California Vehicle Code §22352(b)(2) and §22358.4(b)(5) measure from the school grounds",
           "source": {"osm": "OpenStreetMap amenity=school, data/osm-cache/sf-schools.json",
                      "parcel": sorted(tags)[0] if tags else ""},
           "counts": n, "schools": dict(sorted(rows.items()))}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    write_zones(rows)
    for r in sorted(rows.values(), key=lambda r: r["source"]):
        if r["source"] != "osm":
            look = "  <- look: a P lot with the door %d ft off" % r["doorFt"] if r["label"].startswith("P") and r["doorFt"] > 60 else ""
            print("  %-7s %-40s %s %s door %d ft%s" % (r["source"], r["name"], r["ref"], r["label"], r["doorFt"], look))
    print("school-grounds: %s of %d schools; wrote %s" % (n, len(sch), os.path.relpath(OUT, ROOT)))


if __name__ == "__main__":
    main()
