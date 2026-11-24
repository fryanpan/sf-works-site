#!/usr/bin/env python3
"""Every destination the full access map times a trip to, as points a walker reaches: schools by level, library branches, groceries, parks, major parks and neighborhood commercial districts.

    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map-destinations.py      # write data/full-map/destinations.json
    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map-destinations.py --check

Builds from what is on disk and fetches nothing new: the
two DataSF datasets below are read through lib/sfdata.py's dated cache,
which pipeline/refresh-socrata.py keeps current (both ids are in SOCRATA in
pipeline/transportation-quality.py, with their checks).

TYPES.
  elementary, middle, high   lib/school-travel-time.py's school list and
                             grade rule, as tools/travel/access-time.py uses them.
  library                    access-time.py's open branches (Mission at its
                             temporary site).
  grocery                    OpenStreetMap shop=supermarket, grocery or
                             greengrocer (data/extract/access/groceries.json,
                             scripts/access-inputs.py).
  park                       Recreation and Parks Properties (DataSF
                             gtr9-ntp6) of PARK_TYPES, inside San Francisco,
                             plus every open-access unit of public open space
                             the California Protected Areas Database lists in
                             the county that isn't mostly inside a Rec and
                             Park property (CPAD_DUPLICATE_SHARE;
                             data/extract/cpad/sf-units.json,
                             pipeline/sources/cpad-sf.py): the Presidio, the GGNRA's
                             units (Ocean Beach, Lands End and Fort Funston
                             are its "Golden Gate National Recreation Area"
                             unit), Candlestick Point, the Port's parks,
                             Mount Sutro, and city parks Rec and
                             Park's dataset doesn't list (Yerba Buena
                             Gardens, South Beach Park). Non-profit and
                             homeowners' holdings, community gardens,
                             Alcatraz (ferry only), BLM's offshore rocks and
                             an unnamed city lot are left out (CPAD_SKIP).
                             Ruling: the coordinator, 2026-10-23, on Fable
                             finding 2 (docs/decisions/access-map.md).
  major_park                 the same, MAJOR_ACRES (10) acres or more by the
                             holder's own acres, less Park Presidio Blvd
                             (property id NOT_MAJOR_IDS), a 20-acre highway
                             median a Richmond block would otherwise reach as
                             a "major park". Sunset Dunes (50 acres), the
                             other Parkway, counts. Acres include water and
                             golf (Lake Merced, Lincoln Park), as the
                             department counts.
  commercial                 SF Planning's zoning districts (DataSF
                             3i4a-hu95) in COMMERCIAL_SIM: every zone where
                             neighborhood retail is principally permitted.
                             That is Planning Code Article 7's neighborhood
                             commercial family (NC-1, NC-2, NC-3, NC-S,
                             NCT-1 to 3, every named NCD and NCT),
                             Chinatown's three commercial districts, C-2,
                             every C-3 district, the mixed-use districts (UMU,
                             MUR, MUG, MUO, WMUG, WMUO, CMUO, RCD) and Mission
                             Bay (MB-RA, MB-O). PDR and industrial zones are
                             out. Ruling: the coordinator, 2026-10-23, on
                             Fable finding 1 (docs/decisions/access-map.md).
                             A district is one (class, name) pair, its
                             polygons merged; its name is Title Case
                             (title_case: "Hayes NCT", "24th Street").
                             Planning's map was picked over OEWD's Invest in
                             Neighborhoods corridors (DataSF 667d-aah6)
                             because the zoning is citywide and current
                             (rows updated 2026-10-22), where the corridor
                             layer was last updated in 2016 and covers only
                             the program's 25 corridors.

A PARK OR DISTRICT IS REACHED AT ITS EDGE. Its outline (each outer ring of the
property, or of the district's zoning polygons merged) is sampled every
SAMPLE_M metres; the samples are thinned to one per CELL_M grid cell, and a
sample is kept only if a street or path of the walk network lies within
EDGE_M of it, so a park's shoreline or a cliff is not a door. A trip to the
type ends at whichever kept point is fastest. A point-like destination (a
school, a branch, a store) is its own point.

Writes data/full-map/destinations.json: per type, the source, the rule, the
features (name, acres where it has them) and the points [lon, lat, feature].
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import stable  # noqa: E402
from lib.quality import Each, Table, read_json, run  # noqa: E402

OUT_REL = "data/full-map/destinations.json"
PARKS_ID = "gtr9-ntp6"
ZONING_ID = "3i4a-hu95"
# Rec and Park's own property types that are open space a family would go to.
# Left out: Library, Other Non-Park Property, Concession, Family Camp (Camp
# Mather, in Tuolumne County), Zoological Garden (paid entry) and Community
# Garden (plots, not public play space).
PARK_TYPES = {"Neighborhood Park or Playground", "Mini Park", "Regional Park", "Civic Plaza or Square", "Parkway"}
MAJOR_ACRES = 10.0
# Rec and Park property ids that are parks but not major parks: 101 is Park Presidio Blvd, a highway median.
NOT_MAJOR_IDS = {"101"}
CPAD_REL = "data/extract/cpad/sf-units.json"
# CPAD units that are not open space a San Francisco resident walks into: Alcatraz is reached only by a paid ferry,
# BLM's California Coastal National Monument here is offshore rocks, and "San Francisco, City and County of 1" is an
# unnamed city lot.
CPAD_SKIP = {"Alcatraz Island", "California Coastal National Monument", "San Francisco, City and County of 1"}
CPAD_PRIVATE_LEVELS = {"Non Profit", "Home Owners Association"}
# A CPAD unit at least this share inside a Rec and Park property's outline is that property, already counted.
CPAD_DUPLICATE_SHARE = 0.5
# Plots, not public play space: Rec and Park's Community Garden type is left out (PARK_TYPES), so CPAD's are too.
GARDEN = re.compile(r"\bgarden\b(?!s\b)", re.I)
# Every zone where neighborhood retail is principally permitted (the coordinator's ruling, 2026-10-23).
COMMERCIAL_SIM = {"NC-1", "NC-2", "NC-3", "NC-S", "NCD", "NCT", "NCT-1", "NCT-2", "NCT-3",
                  "CCB", "CVR", "CRNC",
                  "C-2", "C-3-G", "C-3-O", "C-3-O(SD)", "C-3-R", "C-3-S",
                  "UMU", "MUR", "MUG", "MUO", "WMUG", "WMUO", "CMUO", "RCD", "MB-RA", "MB-O"}
UPPER = {"NC", "NCT", "NCD", "MU", "UMU", "MUG", "MUO", "MUR", "RCD", "SD"}
SAMPLE_M = 25.0
CELL_M = 50.0
EDGE_M = 30.0
SF_SOUTH_LAT = 37.7081  # the county line, as scripts/access-inputs.py cuts groceries
LAT0 = math.radians(37.76)
R = 6371008.8

# The orchestrator's interpreter, which has no numpy, imports this file only for checks(); the
# analysis virtualenv runs the build (pipeline/venv-step.py).
A = None


def _access_time():
    global A
    if A is None:
        A = paths.load("access-time.py")
    return A


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * R, math.radians(lat) * R)


def lonlat(x, y):
    return (math.degrees(x / (math.cos(LAT0) * R)), math.degrees(y / R))


def rings_of(geom):
    """Outer rings of a GeoJSON Polygon or MultiPolygon, as lists of (lon, lat)."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    return []


def edge_points(rings, G):
    """Where a walker reaches a polygon: samples of its rings every SAMPLE_M, one per CELL_M cell, near a walk edge."""
    cells = {}
    for ring in rings:
        pts = [xy(*p[:2]) for p in ring]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            n = max(1, int(L // SAMPLE_M))
            for i in range(n):
                t = i / n
                x, y = ax + t * (bx - ax), ay + t * (by - ay)
                c = (int(x // CELL_M), int(y // CELL_M))
                # A cell keeps its first sample near a walk edge, whichever sample of the cell that is.
                if c in cells:
                    continue
                if any(G.joinable[e] for e, _t, _d in G.edges_near(x, y, EDGE_M)):
                    cells[c] = (x, y)
    out = []
    for c in sorted(cells):
        lon, lat = lonlat(*cells[c])
        out.append([round(lon, 6), round(lat, 6)])
    return out


def parks(G):
    r = sfdata.fetch(PARKS_ID, floor=200)
    feats, pts = [], []
    for row in sorted(r.rows, key=lambda x: (x.get("property_name") or "", x.get("property_id") or "")):
        if row.get("propertytype") not in PARK_TYPES or not row.get("shape"):
            continue
        if (row.get("city") or "San Francisco").strip().lower() != "san francisco":
            continue
        rings = rings_of(row["shape"])
        if not rings or min(p[1] for ring in rings for p in ring) < SF_SOUTH_LAT - 0.01:
            continue
        acres = round(float(row.get("acres") or 0), 2)
        got = edge_points(rings, G)
        if not got:
            continue
        fi = len(feats)
        feats.append({"name": row["property_name"], "id": row.get("property_id"), "type": row["propertytype"],
                      "acres": acres})
        pts.extend([p[0], p[1], fi] for p in got)
    return feats, pts, r


def title_case(name):
    """Planning's upper-case district name in Title Case: 'HAYES NCT' -> 'Hayes NCT', '24TH STREET- NOE VALLEY ...'
    -> '24th Street Noe Valley ...', 'SOMA' -> 'SoMa'."""
    t = re.sub(r"\s*-\s+", " ", name.strip()).title()
    t = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)
    t = re.sub(r"\b([A-Za-z]+)\b", lambda m: m.group(1).upper() if m.group(1).upper() in UPPER else m.group(1), t)
    return t.replace("Wsoma", "Western SoMa").replace("Soma", "SoMa")


def cpad_parks(G, rpd_rows):
    """Open-access public open space CPAD lists in San Francisco beyond Rec and Park's own properties.

    A unit counts unless it is mostly (CPAD_DUPLICATE_SHARE) inside a property of Rec and Park's dataset, any type,
    which is the same land counted already or deliberately left out (a zoo, a camp)."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from shapely.prepared import prep
    rpd = unary_union([shape(r["shape"]).buffer(0) for r in rpd_rows if r.get("shape")])
    blob = json.load(open(os.path.join(ROOT, CPAD_REL)))
    feats, pts = [], []
    for u in sorted(blob["records"], key=lambda u: (u["name"], u["unit_id"])):
        if u["access"] != "Open Access" or u["agency_level"] in CPAD_PRIVATE_LEVELS or u["name"] in CPAD_SKIP:
            continue
        if GARDEN.search(u["name"]) or not u.get("geometry"):
            continue
        g = shape(u["geometry"]).buffer(0)
        if g.area == 0 or g.intersection(rpd).area / g.area >= CPAD_DUPLICATE_SHARE:
            continue
        rings = rings_of(u["geometry"]) if u.get("geometry") else []
        if not rings or min(p[1] for ring in rings for p in ring) < SF_SOUTH_LAT - 0.01:
            continue
        got = edge_points(rings, G)
        if not got:
            continue
        fi = len(feats)
        feats.append({"name": u["name"], "id": "cpad:%s" % u["unit_id"], "type": "CPAD: %s" % u["agency"],
                      "acres": u["acres"]})
        pts.extend([p[0], p[1], fi] for p in got)
    return feats, pts, blob


def commercial(G):
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union
    r = sfdata.fetch(ZONING_ID, floor=5000)
    groups = collections.defaultdict(list)
    for row in r.rows:
        if row.get("zoning_sim") in COMMERCIAL_SIM and row.get("the_geom"):
            groups[(row["zoning_sim"], row.get("districtna") or "")].append(shape(row["the_geom"]).buffer(0))
    feats, pts = [], []
    for (sim, name) in sorted(groups):
        merged = unary_union(groups[(sim, name)])
        rings = rings_of(mapping(merged))
        got = edge_points(rings, G)
        if not got:
            continue
        fi = len(feats)
        feats.append({"name": title_case(name), "zoning": sim, "polygons": len(groups[(sim, name)])})
        pts.extend([p[0], p[1], fi] for p in got)
    return feats, pts, r


def points_type(rows):
    feats = [{"name": d["name"]} for d in rows]
    return feats, [[round(d["lon"], 6), round(d["lat"], 6), i] for i, d in enumerate(rows)]


def groceries():
    blob = json.load(open(os.path.join(ROOT, "data", "extract", "access", "groceries.json")))
    rows = sorted(blob["records"], key=lambda r: (r.get("name") or "", r["osm"]))
    return [{"name": r.get("name") or r["shop"], "lon": r["lon"], "lat": r["lat"]} for r in rows], blob["fetched_on"]


def build():
    from lib import netcache
    _access_time()
    G = netcache.graph()
    out = {"note": "Points a walker reaches each destination at; a trip to a type ends at its fastest point. "
                   "Polygon types are sampled along their edges (see the script's docstring).",
           "parameters": {"sample_m": SAMPLE_M, "cell_m": CELL_M, "edge_m": EDGE_M, "major_acres": MAJOR_ACRES},
           "types": {}}
    for level in ("elementary", "middle", "high"):
        f, p = points_type(A.TYPES[level]())
        out["types"][level] = {"source": "lib/school-travel-time.py load_schools, the access model's list",
                               "features": f, "points": p}
    f, p = points_type(A.libraries())
    out["types"]["library"] = {"source": "data/extract/libraries/branches.json, open branches (tools/travel/access-time.py)",
                               "features": f, "points": p}
    g, fetched = groceries()
    f, p = points_type(g)
    out["types"]["grocery"] = {"source": "OpenStreetMap shop=supermarket|grocery|greengrocer, "
                                         "data/extract/access/groceries.json, fetched %s" % fetched,
                               "features": f, "points": p}
    pf, pp, pr = parks(G)
    cf_, cp_, cb = cpad_parks(G, pr.rows)
    base = len(pf)
    pf = pf + cf_
    pp = pp + [[x, y, i + base] for x, y, i in cp_]
    src = ("DataSF %s Recreation and Parks Properties, queried %s; California Protected Areas Database (%s), "
           "%s, fetched %s" % (PARKS_ID, pr.fetched_on.isoformat(), cb["meta"]["release"].rstrip("."), CPAD_REL,
                               cb["fetched_on"]))
    out["types"]["park"] = {"source": src, "rule": "Rec and Park propertytype in %s, in San Francisco; and every "
                                                   "open-access CPAD unit there less than %g inside a Rec and Park "
                                                   "property, less non-profit and homeowners' holdings, community "
                                                   "gardens and %s" % (sorted(PARK_TYPES), CPAD_DUPLICATE_SHARE,
                                                                       sorted(CPAD_SKIP)),
                            "features": pf, "points": pp}
    keep = {i for i, f in enumerate(pf) if f["acres"] >= MAJOR_ACRES and f["id"] not in NOT_MAJOR_IDS}
    remap = {i: j for j, i in enumerate(sorted(keep))}
    out["types"]["major_park"] = {"source": src, "rule": "a park above with %g acres or more by its holder's own "
                                                         "acres, less Park Presidio Blvd (property id %s)" % (
                                                             MAJOR_ACRES, ", ".join(sorted(NOT_MAJOR_IDS))),
                                  "features": [pf[i] for i in sorted(keep)],
                                  "points": [[x, y, remap[i]] for x, y, i in pp if i in keep]}
    cf, cp, cr = commercial(G)
    out["types"]["commercial"] = {"source": "DataSF %s Zoning Map - Zoning Districts, queried %s" % (
        ZONING_ID, cr.fetched_on.isoformat()), "rule": "zoning_sim in %s" % sorted(COMMERCIAL_SIM),
        "features": cf, "points": cp}
    os.makedirs(os.path.join(ROOT, os.path.dirname(OUT_REL)), exist_ok=True)
    stable.write_json(os.path.join(ROOT, OUT_REL), out, separators=(",", ":"))
    return out


# Floors under the 2026-10-23 build's counts, so a dropped dataset or a broken filter fails.
FLOORS = {"elementary": 100, "middle": 60, "high": 30, "library": 25, "grocery": 120, "park": 200, "major_park": 45,
          "commercial": 70}


def checks(root=ROOT):
    def per_type(r):
        d = read_json(r, OUT_REL)
        if d is None:
            return None
        return [{"type": k, "features": len(v["features"]), "points": len(v["points"]),
                 "floor": FLOORS.get(k, 1)} for k, v in sorted(d["types"].items())]

    def points(r):
        d = read_json(r, OUT_REL)
        if d is None:
            return None
        return [{"type": k, "i": i, "lon": p[0], "lat": p[1], "f": p[2], "n": len(v["features"])}
                for k, v in sorted(d["types"].items()) for i, p in enumerate(v["points"])]

    return [
        Table("full-map-destinations", per_type, floor=len(FLOORS), max_drop=0.0, key="type",
              required=["type", "features", "points"]),
        Each("full-map-destinations/floors", per_type,
             lambda t: None if t["features"] >= t["floor"] else "%s has %d features, floor %d" % (
                 t["type"], t["features"], t["floor"]), "every type keeps at least its floor of features"),
        Each("full-map-destinations/every-feature-reached", per_type,
             lambda t: None if t["points"] >= t["features"] else "%s: %d points for %d features" % (
                 t["type"], t["points"], t["features"]), "every feature has a point"),
        Each("full-map-destinations/in-sf", points,
             lambda p: None if -122.53 <= p["lon"] <= -122.35 and SF_SOUTH_LAT - 0.01 <= p["lat"] <= 37.83
             else "%s point %d at %s,%s" % (p["type"], p["i"], p["lon"], p["lat"]), "every point inside San Francisco"),
        Each("full-map-destinations/feature-index", points,
             lambda p: None if 0 <= p["f"] < p["n"] else "%s point %d names feature %d" % (p["type"], p["i"], p["f"]),
             "every point names a feature of its type"),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        out = build()
        for k, v in out["types"].items():
            print("  %-11s %4d features, %5d points" % (k, len(v["features"]), len(v["points"])))
    results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
