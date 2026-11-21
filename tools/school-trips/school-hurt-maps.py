#!/usr/bin/env python3
"""Kids hurt near SF schools and the $20M bikeway set, drawn as static maps for the board's school embeds (site/data/school-hurt-maps.json, from DataSF nwes-mmgh).

    tools/school-trips/school-hurt-maps.py      # writes site/data/school-hurt-maps.json

Bryan, 2026-10-21, on the board doc: live maps of the schools where the most
kids are hurt, built from the maps we already have, the "Main Streets Around
Schools" mockup's street maps (grounds, the 500 ft zone, the quarter mile, main
streets dark and residential ones pale). And, on the ranking, "if you click on a
school in the top 20 bar, it opens up the recent injury map from the last 10
years", since widened to the top 40. The pages are
site/src/school-hurt-blocks.mjs, served at /embed/school/<block>/.

THE BASE is tools/school-trips/school-kids-hurt.py's: a victim 5 to 18, injured or killed,
on a weekday from 6 am to 6 pm, August 1 to May 31, with a location, in DataSF
nwes-mmgh (read through lib/sfdata.py). The window is lib/
school_window.py's (Bryan, 2026-10-21: "please use this same definition
throughout the whole post"). Each goes to the nearest of the simulation's
schools (site/data/school-sim/index.json), measured from the edge of its grounds
as state law measures a school zone (lib/school_grounds.py nearest), and
counts there within NEAR_FT, a quarter mile. ZONE_FT is the school zone. A kid
between two schools counts once. Ties in the ranking are listed by name.

THE FOUR single-school maps count school years 2021-22 to 2024-25 (school-kids-hurt.json's
model.base). THE TOP 40 chart and the maps it opens count school years 2015-16 to
2024-25. A school year runs August to May and is labelled by its August.

PHASE, for the top 40 chart, from index.json: first phase when the school is one
block from today's network (blocksToNetwork), second when one block from the plan
(blocksToPlan) and not first, later otherwise.

THE BIKEWAY MAP is the $20M set of out/school-sim/segments.json (scripts/
school-segments-ip.py), drawn over today's all-ages network
(site/data/bike-history/all-ages.geojson, blocks with no `until`).

STREETS are OpenStreetMap's drive network (data/osm-cache/sf-drive.json): main
when tertiary or above (tools/school-trips/school-calm-priority.py's RANK), freeway when
motorway, residential otherwise.

OUTPUT keeps one row per kid: lon, lat, how they were travelling, school year
and distance band. No case or victim ids, no dates and no other personal fields.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import school_points  # noqa: E402
skh = paths.load("school-kids-hurt.py", "skh")
calm, sfdata, sg, sw = skh.calm, skh.sfdata, skh.school_grounds, skh.school_window

OUT = os.path.join(ROOT, "site", "data", "school-hurt-maps.json")
ZONE_FT, NEAR_FT = skh.ZONE_FT, skh.NEAR_FT
FT_LON, FT_LAT = sg.FT_LON, sg.FT_LAT
YEARS4 = skh.YEARS
YEARS10 = sw.years(2015, 2024)
TOP = 40
BUDGET_M = 20
# The four single-school blocks: block name, CDS code, and the name the title uses.
FOUR = [
    ("balboa", "38684783830288", "Balboa High"),
    ("drew", "38684786104673", "Charles Drew College Prep"),
    ("carmichael", "38684786040752", "Bessie Carmichael/FEC"),
    ("kipp-bayview", "38684780101337", "KIPP Bayview Academy"),
]
BANDS = (("zone", ZONE_FT), ("quarter", NEAR_FT))
VIEW = 300.0  # each school map's square viewBox
LABELS = 3  # main streets named on each school map


def kids(years):
    """Every kid hurt on a school-year weekday, 6 am to 6 pm, in these school years, with a location."""
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,"
                     "collision_datetime,collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd", floor=80000)
    rows = []
    for v in V.rows:
        k = sw.kid_hurt(v)
        if k is None or k["year"] not in years:
            continue
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        role = v.get("victim_role")
        mode = "Scooter or other" if role == "Driver" and k["age"] < 16 else skh.MODES.get(role, "Scooter or other")
        rows.append({"lat": la, "lon": lo, "mode": mode, "year": k["year"], "date": k["date"].isoformat()})
    return rows, V.tag


def attribute(rows, sch):
    nj, nd = sg.nearest([(s["lon"], s["lat"]) for s in sch], [r["lon"] for r in rows], [r["lat"] for r in rows], 5280)
    per = collections.defaultdict(list)
    for r, j, dd in zip(rows, nj, nd):
        ft = float(dd) if dd == dd else 1e9
        if j >= 0 and ft <= NEAR_FT:
            per[sch[int(j)]["cds"]].append(dict(r, ft=ft))
    return per


def areas_ft(s, rings):
    """The grounds, and the grounds grown by ZONE_FT and NEAR_FT, as shapely shapes in feet from the school's point."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    to_ft = lambda ring: [((x - s["lon"]) * FT_LON, (y - s["lat"]) * FT_LAT) for x, y in ring]
    g = unary_union([Polygon(to_ft(q)).buffer(0) for q in rings]) if rings else Point(0, 0).buffer(30)
    return {"grounds": g.simplify(3), "zone": g.buffer(ZONE_FT, quad_segs=8).simplify(6), "quarter": g.buffer(NEAR_FT, quad_segs=12).simplify(8)}


def poly_d(geom, xy):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    out = []
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            out.append("M" + "L".join("%.1f,%.1f" % xy(x, y) for x, y in ring.coords[:-1]) + "Z")
    return "".join(out)


def line_d(pts):
    return "M" + "L".join("%.1f,%.1f" % p for p in pts)


def keep_near(pts, lo, hi):
    """Runs of a line inside the box, each with one point beyond at either end so it reaches the edge."""
    inb = [lo <= x <= hi and lo <= y <= hi for x, y in pts]
    out, cur = [], []
    for i, p in enumerate(pts):
        near = inb[i] or (i > 0 and inb[i - 1]) or (i + 1 < len(pts) and inb[i + 1])
        if near:
            cur.append(p)
        elif cur:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [c for c in out if len(c) > 1]


class Streets:
    def __init__(self):
        osm = json.load(open(os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")))["elements"]
        node = {e["id"]: (e["lon"], e["lat"]) for e in osm if e["type"] == "node"}
        self.ways = []
        for e in osm:
            hw = e.get("tags", {}).get("highway") if e["type"] == "way" else None
            if hw not in calm.RANK:
                continue
            kind = "fwy" if hw.startswith("motorway") else ("main" if calm.RANK[hw] >= 2 else "res")
            pts = [node[n] for n in e["nodes"] if n in node]
            if len(pts) > 1:
                self.ways.append((kind, pts, e["tags"].get("name", "")))

    def around(self, lon0, lat0, ext, xy):
        lim = ext * 1.02
        out = {"res": [], "main": [], "fwy": []}
        for kind, pts, _name in self.ways:
            ft = [((x - lon0) * FT_LON, (y - lat0) * FT_LAT) for x, y in pts]
            if not any(abs(a) <= lim + 400 and abs(b) <= lim + 400 for a, b in ft):
                continue
            for run in keep_near([(a, -b) for a, b in ft], -lim, lim):
                out[kind].append(line_d([xy(a, b) for a, b in run]))
        return {k: sorted(v) for k, v in out.items()}

    def labels(self, lon0, lat0, quarter, xy, n=LABELS):
        """The n main streets with the most length inside the quarter mile, each named once along its longest piece there."""
        from shapely.geometry import LineString
        from shapely.ops import linemerge, unary_union
        pieces = collections.defaultdict(list)
        for kind, pts, name in self.ways:
            if kind != "main" or not name:
                continue
            line = LineString([((x - lon0) * FT_LON, (y - lat0) * FT_LAT) for x, y in pts])
            if not line.intersects(quarter):
                continue
            cut = line.intersection(quarter)
            for g in (getattr(cut, "geoms", None) or [cut]):
                if g.geom_type == "LineString" and g.length > 0:
                    pieces[name].append(g)
        ranked = sorted(pieces, key=lambda k: (-sum(g.length for g in pieces[k]), k))
        out = []
        for name in ranked:
            # OpenStreetMap splits a street into many ways; join them before picking the longest stretch.
            u = unary_union(pieces[name])
            m = linemerge(u) if u.geom_type == "MultiLineString" else u
            g = max(getattr(m, "geoms", None) or [m], key=lambda g: g.length)
            if g.length < 400:
                continue
            for f in (0.5, 0.3, 0.7):
                a, c, b = (g.interpolate(f + d, normalized=True) for d in (-0.04, 0, 0.04))
                (x0, y0), (x, y), (x1, y1) = xy(a.x, a.y), xy(c.x, c.y), xy(b.x, b.y)
                if all(math.hypot(x - o["x"], y - o["y"]) > 45 for o in out):
                    break
            else:
                continue
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
            ang = ang - 180 if ang > 90 else ang + 180 if ang <= -90 else ang
            out.append({"name": short(name), "x": round(x, 1), "y": round(y, 1), "angle": round(ang, 1)})
            if len(out) == n:
                break
        return out


def short(name):
    """'Geneva Avenue' as 'Geneva Ave', the way SF's street signs print it."""
    for a, b in ((" Street", " St"), (" Avenue", " Ave"), (" Boulevard", " Blvd"), (" Drive", " Dr"), (" Road", " Rd"), (" Place", " Pl")):
        name = re.sub(a + r"\b", b, name)
    return name


def school_map(s, g, ks, streets):
    """One school's map: streets, grounds, zone and quarter mile in a VIEW-wide square, and its kids as rows."""
    A = areas_ft(s, g["rings"])
    b = A["quarter"].bounds
    ext = max(abs(v) for v in b) + 60
    S = (VIEW / 2) / ext
    xy = lambda x, y: (VIEW / 2 + x * S, VIEW / 2 - y * S)
    xy_down = lambda x, y: (VIEW / 2 + x * S, VIEW / 2 + y * S)
    ks = sorted(ks, key=lambda k: (k["ft"], k["date"], k["lon"], k["lat"]))
    band = lambda ft: next(name for name, lim in BANDS if ft <= lim)
    return {
        "lon": s["lon"], "lat": s["lat"], "ftPerUnit": round(1 / S, 4),
        "streets": streets.around(s["lon"], s["lat"], ext, xy_down),
        "grounds": poly_d(A["grounds"], xy), "zone": poly_d(A["zone"], xy), "quarter": poly_d(A["quarter"], xy),
        "labels": streets.labels(s["lon"], s["lat"], A["quarter"], xy),
        "kids": len(ks), "zoneKids": sum(k["ft"] <= ZONE_FT for k in ks),
        "byMode": dict(sorted(collections.Counter(k["mode"] for k in ks).items())),
        "rows": [[round(k["lon"], 5), round(k["lat"], 5), k["mode"], k["year"], band(k["ft"])] for k in ks],
    }


def display(name):
    """'Drew (Charles) College Preparatory Academy' as 'Charles Drew College Preparatory Academy'."""
    m = re.match(r"^(\S+(?: Jr\.)?) \(([^)]+)\)(.*)$", name)
    return re.sub(r" ?/ ?", "/", "%s %s%s" % (m.group(2), m.group(1), m.group(3)) if m else name)


# Names the chart shortens past display()'s reordering, by CDS code.
SHORT = {
    "38684786040752": "Bessie Carmichael/FEC",
    "38684786059885": "Martin Luther King Jr. Middle",
    "38684786062046": "Buena Vista Horace Mann K-8",
    "38684780119958": "AcademySF @McAteer",
    "38684783830254": "Phillip and Sala Burton High",
    "38684786104673": "Charles Drew College Prep",
}


def phase(s):
    if s.get("blocksToNetwork") == "1 block":
        return "first"
    return "second" if s.get("blocksToPlan") == "1 block" else "later"


def bikeways():
    """The $20M set over today's all-ages network, with the schools, in a city-wide viewBox."""
    from shapely.geometry import shape, box
    from shapely.ops import unary_union
    W, E, Sth, N = -122.5155, -122.3555, 37.7065, 37.8335
    k = math.cos(math.radians(37.76))
    width = 600.0
    S = width / ((E - W) * k)
    height = round((N - Sth) * S, 1)
    xy = lambda lon, lat: ((lon - W) * k * S, (N - lat) * S)
    seg = json.load(open(os.path.join(ROOT, "out", "school-sim", "segments.json")))
    bud = next(b for b in seg["budgets"] if b["budgetM"] == BUDGET_M)
    chosen = set(bud["chunks"])
    chunks = sorted((c for c in seg["chunks"] if c["id"] in chosen), key=lambda c: c["id"])
    assert len(chunks) == len(chosen), "a chosen chunk is missing from segments.json"
    picked = [line_d([xy(*p) for p in part]) for c in chunks for part in c["pts"]]
    net = json.load(open(os.path.join(ROOT, "site", "data", "bike-history", "all-ages.geojson")))
    today = []
    for f in net["features"]:
        if f["properties"].get("until"):
            continue
        gm = f["geometry"]
        for line in ([gm["coordinates"]] if gm["type"] == "LineString" else gm["coordinates"]):
            today.append(line_d([xy(*p) for p in line]))
    dist = json.load(open(os.path.join(ROOT, "site", "data", "supervisor-districts.json")))
    land = unary_union([shape({"type": "MultiPolygon", "coordinates": d["coords"]}) for d in dist["districts"]]).intersection(box(W, Sth, E, N))
    land = land.simplify(0.0002)
    sch = school_points.index_schools()
    return {
        "budgetM": BUDGET_M, "stretches": len(chunks), "centerlineMi": round(bud["centerlineMi"], 1), "costM": round(bud["costM"], 2),
        "width": width, "height": height, "land": poly_d(land, xy),
        "today": sorted(today), "picked": sorted(picked),
        "schools": sorted([round(v, 1) for v in xy(s["lon"], s["lat"])] for s in sch),
        "sources": {"segments": "out/school-sim/segments.json", "network": net["sources"]["network"]["url"], "districts": dist["dataset"]},
    }


def main():
    sch = school_points.index_schools()
    by_cds = {s["cds"]: s for s in sch}
    grounds = json.load(open(os.path.join(ROOT, "data", "school-sim", "grounds.json")))["schools"]
    g_of = lambda s: grounds[sg.key(s["lon"], s["lat"])]
    streets = Streets()

    rows4, tag = kids(YEARS4)
    # The same base as tools/school-trips/school-kids-hurt.py, which runs first in the pipeline.
    base = json.load(open(os.path.join(ROOT, "site", "data", "school-kids-hurt.json")))["model"]["base"]
    assert len(rows4) == base, "base is %d kids, school-kids-hurt.json has %d" % (len(rows4), base)
    per4 = attribute(rows4, sch)
    rank = sorted(per4, key=lambda c: (-len(per4[c]), by_cds[c]["name"]))
    counts = [len(per4[c]) for c in rank]

    four = []
    for i, (slug, cds, title) in enumerate(FOUR):
        n = len(per4[cds])
        # The first three are the top three; the fourth ties for fourth.
        assert (i < 3 and rank[i] == cds) or (i == 3 and n == counts[3]), (slug, n, counts[:6])
        s = by_cds[cds]
        four.append(dict(block="school-hurt-" + slug, cds=cds, title=title, **school_map(s, g_of(s), per4[cds], streets)))

    rows10, _ = kids(YEARS10)
    per10 = attribute(rows10, sch)
    rank10 = sorted(per10, key=lambda c: (-len(per10[c]), by_cds[c]["name"]))
    counts10 = [len(per10[c]) for c in rank10]
    top = []
    for i, cds in enumerate(rank10[:TOP]):
        s = by_cds[cds]
        top.append({"rank": i + 1, "cds": cds, "name": SHORT.get(cds, display(s["name"])), "kids": len(per10[cds]), "phase": phase(s),
                    "map": school_map(s, g_of(s), per10[cds], streets)})
    tied = sum(1 for c in counts10[TOP:] if c == counts10[TOP - 1])
    ph = collections.Counter()
    for c in per10:
        ph[phase(by_cds[c])] += len(per10[c])

    doc = {
        "note": "Written by tools/school-trips/school-hurt-maps.py from DataSF nwes-mmgh: kids 5 to 18 hurt on weekdays 6 am to 6 pm, August to May, "
                "each counted at the nearest school's grounds within %d ft (%d ft is the school zone). Map units are a %d-wide viewBox."
                % (NEAR_FT, ZONE_FT, VIEW),
        "source": {"id": "nwes-mmgh", "url": "https://data.sfgov.org/d/nwes-mmgh", "tag": tag},
        "zoneFt": ZONE_FT, "nearFt": NEAR_FT, "ftLon": FT_LON, "ftLat": FT_LAT, "view": VIEW,
        "rowFields": ["lon", "lat", "mode", "schoolYear", "band"],
        "years4": [YEARS4[0], YEARS4[-1]], "years10": [YEARS10[0], YEARS10[-1]],
        "four": four,
        "top40": {"schools": top, "tiedPast": tied, "kidsByPhaseAllSchools": dict(sorted(ph.items())), "kidsAllSchools": sum(ph.values())},
        "bikeways": bikeways(),
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    for s in four:
        print("%-24s %2d kids, %d in the zone %s" % (s["block"], s["kids"], s["zoneKids"], s["byMode"]))
    for s in top:
        print("%2d %2d %-7s 10y %2d  %s" % (s["rank"], s["kids"], s["phase"], s["map"]["kids"], s["name"]))
    print("kids by phase, all schools", dict(ph), "ties past the top:", tied)
    print("school-hurt-maps: wrote %s, %d KB" % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT) // 1024))


if __name__ == "__main__":
    main()
