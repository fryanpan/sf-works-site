#!/usr/bin/env python3
"""Where traffic comes from, for the Street Safety map: each SF neighborhood's and Supervisor district's car trips by the neighborhood or Bay Area region they start and end in and by time of day, where each one's bubble sits, and every SF street link's cars by origin and destination group for a drawn area's cordon count, from tools/street-safety/through-traffic.py's select stage.

    ~/.venvs/sf-works-geo/bin/python -I tools/street-safety/where-traffic-comes-from.py --select scratch/runs/through-traffic/select.json

Bryan, 2026-11-19: "Add another layer that shows where traffic comes from.
That layer requires choosing an area to focus on (e.g. a neighborhood, or arbitrary drawn area) And then you can see
where the traffic comes from around the bay area for the chosen area". Then: "please let the user choose which group to
include -- where traffic is coming from, where is it going to, and both". 2026-11-20, on the zone shading that first
shipped: "give one bubble per neighborhood that shows by area the number of cars. And merge areas outside of SF even
more aggressively, but in a way where you could assess alternative modes by region"; "I want to see time of day
breakdown for from / to so there's a sense of morning vs evening"; "I want us to think about fractions". Prior work:
research/notes/low-traffic-cells-2026-11/2026-11-19-network-flows-prior-work.md (select-link is the standard method)
and scripts/network-flows-prototype.py (the Sunset-only LODES prototype this replaces with every car trip).

WHAT THE SELECT STAGE COUNTS (tools/street-safety/through-traffic.py select)
  A car counts for an area when its fastest route uses at least one of the area's streets (a link whose midpoint is in
  the neighborhood or district, freeways and ramps left out). Its trip ends are SF-CHAMP zones; an end is in the area
  when its zone's representative point is. arr: ends in the area, starts outside. dep: starts in it, ends outside.
  thr: neither end in it. inside: both. A weekday, every hour bin, averaged over the routing runs; the same four per
  hour bin (the map's five times of day, by MTC departure hour).

THE UNITS (REGIONS below)
  Inside SF a trip end is grouped by Analysis Neighborhood, outside it by MTC superdistrict (5 to 34), and this script
  folds the superdistricts into six regions. A change to the regions needs no new routing run.

THE PAGE'S THREE CHOICES (the map's toggle)
  Coming from  every car on the area's streets, at the group it starts in; the cars that start in the area (dep +
               inside) are the area's own ring.
  Going to     the same cars at the group they end in; the ring is arr + inside.
  Both         each car at both of its ends, so a share is of trip ends.
  A drawn area can't be precomputed. The page counts the cars getting onto its streets (links whose head is a street
  node inside and whose tail isn't, by origin group; the reverse, by destination group) from links.json here: a
  cordon count, which counts a car each time it crosses and can't split through cars from arriving ones. Freeway
  and ramp links are in the table so a car coming off a ramp inside the area counts: at each street node inside it
  that touches one, the cars its street links carry away beyond those they bring in, by origin group (cordon() below,
  the same rule as the page's). Traffic staying on the freeway, or on the Bay Bridge over Treasure Island, doesn't.

OUTPUTS (site/data/street-safety/where-from/, lazy-loaded by the page)
  units.json         the 47 groups (41 neighborhoods, 6 regions), each one's bubble point, the districts' points, each
                     region's superdistricts, places and outline, the nine counties' bounds, the times of day
  area-<slug>.json   per neighborhood and per Supervisor district: totals, cars by group, cars by time of day
  links.json         per SF link with cars: its two nodes, cars by origin and destination group, and a freeway flag

Checks (stop on failure): a full select run (not a smoke test), 41 neighborhoods, 11 districts and 30 superdistricts,
the regions taking each superdistrict once, every neighborhood and district with cars arriving, leaving and passing
through, at least 20,000 links, every area's group sums within rounding of the unrounded total and its times of day of
its day, no car from outside a neighborhood placed in it, the cordon table within 3%, links.json under 3 MB gzipped,
each neighborhood's cordon count inbound within a factor of the select-link count of cars coming in (the cordon counts
re-entries and the edge streets differ, so they never match exactly), and few of the cars entering a neighborhood
starting in it (a link table read backwards would make most of them). Fixed inputs (MTC's 2023 run, one SF-CHAMP
network), so the pipeline step is manual, as through-traffic is.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
from lib.stable import write_text  # noqa: E402

SCR = ROOT / "scratch"
if not (SCR / "runs/through-traffic").exists():
    _git = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    if _git.returncode == 0:
        SCR = Path(_git.stdout.strip()).parent / "scratch"
RUNS = SCR / "runs/through-traffic"
PROTO = SCR / "runs/network-flows-2026-11-19"
NHOODS = ROOT / "data/extract/neighborhoods/analysis-neighborhoods.geojson"
OUT = ROOT / "site/data/street-safety/where-from"
MAX_GZ = 3_000_000


def check(ok, msg):
    if not ok:
        sys.exit("CHECK FAILED: " + msg)
    print("ok  " + msg, file=sys.stderr)


def warn(ok, msg):
    if not ok:
        print("SMOKE, would fail: " + msg, file=sys.stderr)


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def dump(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n"


def cached(name):
    for d in (RUNS, PROTO):
        if (d / name).exists():
            return json.loads((d / name).read_text())
    sys.exit(f"no cached {name} in {RUNS} or {PROTO} (tools/street-safety/through-traffic.py fetches it)")


def cordon(rows, n_nodes, inside, G):
    """A drawn area's cordon count from links.json's rows, the rule the page's cordon() in map.js runs: cars by origin
    group onto the area's street nodes (inside it, with a street link) by a street link from outside them, plus at
    each such node touching a freeway or ramp link, its street links' cars out beyond their cars in; and by
    destination group the reverse."""
    street, fw = np.zeros(n_nodes, bool), np.zeros(n_nodes, bool)
    for r in rows:
        (fw if len(r) > 4 else street)[[r[0], r[1]]] = True
    on = street & np.array(inside)
    inG, outG = np.zeros(G), np.zeros(G)
    net_o, net_d = collections.defaultdict(lambda: np.zeros(G)), collections.defaultdict(lambda: np.zeros(G))
    for r in rows:
        if len(r) > 4:
            continue
        a, b = r[0], r[1]
        o, d = np.zeros(G), np.zeros(G)
        o[r[2][0::2]] = r[2][1::2]
        d[r[3][0::2]] = r[3][1::2]
        if not on[a] and on[b]:
            inG += o
        elif on[a] and not on[b]:
            outG += d
        for n, sgn in ((a, 1), (b, -1)):
            if on[n] and fw[n]:
                net_o[n] += sgn * o
                net_d[n] -= sgn * d
    for v in net_o.values():
        inG += np.maximum(v, 0)
    for v in net_d.values():
        outG += np.maximum(v, 0)
    return inG, outG


# The regions outside San Francisco, each a set of MTC superdistricts (tazData.csv's SD; names from MTC's
# superdistrict-county.csv), drawn by the way into SF that isn't a car, so each can be judged for its alternatives
# (Bryan, 2026-11-20: "merge areas outside of SF even more aggressively, but in a way where you could assess alternative
# modes by region"). [name, superdistricts, the non-car way in].
REGIONS = [
    ("Peninsula North", [5], "BART to Millbrae, Caltrain and SamTrans"),
    ("Peninsula South and South Bay", [6, 7, 8, 9, 10, 11, 12, 13, 14], "Caltrain"),
    ("East Bay Inner", [18, 19, 20], "BART, Transbay buses and ferries across the bay"),
    ("East Bay Outer", [15, 16, 17, 21, 22, 23, 24], "BART's outer lines"),
    ("Marin and Sonoma", [29, 30, 31, 32, 33, 34], "Golden Gate Transit buses and ferries over the Golden Gate"),
    ("Solano and Napa", [25, 26, 27, 28], "the Vallejo ferry, and Capitol Corridor trains to BART"),
]
SD_NAMES = {5: "Daly City and San Bruno", 6: "San Mateo and Burlingame", 7: "Redwood City and Menlo Park", 8: "Palo Alto and Los Altos",
            9: "Sunnyvale and Mountain View", 10: "Cupertino and Saratoga", 11: "Central San Jose", 12: "Milpitas and East San Jose",
            13: "South San Jose", 14: "Gilroy and Morgan Hill", 15: "Livermore and Pleasanton", 16: "Fremont and Union City",
            17: "Hayward and San Leandro", 18: "Oakland and Alameda", 19: "Berkeley and Albany", 20: "Richmond and El Cerrito",
            21: "Concord and Martinez", 22: "Walnut Creek", 23: "Danville and San Ramon", 24: "Antioch and Pittsburg",
            25: "Vallejo and Benicia", 26: "Fairfield and Vacaville", 27: "Napa", 28: "St Helena", 29: "Petaluma and Rohnert Park",
            30: "Santa Rosa and Sebastopol", 31: "Healdsburg and Cloverdale", 32: "Novato", 33: "San Rafael", 34: "Mill Valley and Sausalito"}
NG = 41 + len(REGIONS)
KEYS = (("fa", "from_arr"), ("ft", "from_thr"), ("td", "to_dep"), ("tt", "to_thr"))


def main():
    import csv
    import geopandas as gpd
    from shapely.geometry import Point, mapping, shape
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", default=str(RUNS / "select.json"))
    ap.add_argument("--smoke", action="store_true", help="accept a smoke-test select run and skip the floors (never commit its output)")
    a = ap.parse_args()
    raw = Path(a.select).read_bytes()
    S = json.loads(raw)
    check(a.smoke or S.get("origins", 1) == 0, f"a full select run, not a smoke test of {S.get('origins')} origins (--smoke to try one)")
    H = sorted(json.loads(NHOODS.read_text())["features"], key=lambda f: f["properties"]["nhood"])
    names = [f["properties"]["nhood"] for f in H]
    check(len(names) == 41, "41 analysis neighborhoods")
    sds = S["superdistricts"]
    check(sds == list(range(5, 35)) and sorted(x for r in REGIONS for x in r[1]) == sds, "the regions take each superdistrict outside SF (5 to 34) exactly once")
    check(set(SD_NAMES) == set(sds), "a name for every superdistrict")
    # Select groups (41 neighborhoods, then superdistricts 5 to 34) -> page groups (41 neighborhoods, then REGIONS).
    fold = np.zeros((41 + len(sds), NG))
    fold[np.arange(41), np.arange(41)] = 1
    for ri, (_, members, _) in enumerate(REGIONS):
        for x in members:
            fold[41 + sds.index(x), 41 + ri] = 1
    check((fold.sum(1) == 1).all(), "every select group folds into one page group")
    groups = names + [r[0] for r in REGIONS]
    A = S["areas"]
    nd = S["districts"]
    area_names = names + [f"District {d + 1}" for d in range(nd)] + S["extra"]
    check(nd == 11 and len(A["gfrom_arr"]) == len(area_names) and all(len(row) == 41 + len(sds) for row in A["gfrom_arr"]),
          "the select run has 41 neighborhoods, 11 Supervisor districts and the extras, by 41 neighborhoods and 30 superdistricts")
    bins = S["bins"]
    check([b[0] for b in bins] == ["am", "midday", "pm", "evening", "night"], "the map's five times of day")
    if not a.smoke:
        for k in ("gfrom_arr", "gto_dep", "gfrom_thr"):
            # Treasure Island's streets lead nowhere but the island, so no car passes through them.
            low = [area_names[i] for i in range(41 + nd) if sum(A[k][i]) <= 0 and not (k == "gfrom_thr" and area_names[i] == "Treasure Island")]
            check(not low, f"every neighborhood and district has {k} cars ({low[:3]})")
        check(len(S["links"]) >= 20000, f"at least 20,000 links with cars ({len(S['links']):,})")
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- units: where each bubble sits, the regions' membership and outlines
    mz = gpd.read_file(RUNS / "mtc-2023/taz1454.geojson")[["taz1454", "county", "geometry"]].to_crs(4326)
    check(len(mz) == 1454 and mz.taz1454.is_unique, "1,454 MTC zones")
    with open(RUNS / "mtc-2023/tazData.csv") as fh:
        td = {int(r["ZONE"]): (int(r["SD"]), float(r["TOTPOP"])) for r in csv.DictReader(fh)}
    mz["sd"] = [td[int(z)][0] for z in mz.taz1454]
    mz["pop"] = [td[int(z)][1] for z in mz.taz1454]
    check(((mz.sd <= 4) == (mz.county == "San Francisco")).all(), "superdistricts 1 to 4 are San Francisco's zones and no others")
    rnd = lambda g, nd_=4: json.loads(json.dumps(mapping(g)), parse_float=lambda x: round(float(x), nd_))
    # A neighborhood's bubble sits at a point inside it; a region's at the middle of its people (each zone's
    # representative point weighted by tazData's TOTPOP), moved to the nearest point of the region if that lands in water.
    pts = []
    for f in H:
        q = shape(f["geometry"]).representative_point()
        pts.append([round(q.x, 4), round(q.y, 4)])
    rf, regions = [], []
    for ri, (rname, members, how) in enumerate(REGIONS):
        zz = mz[mz.sd.isin(members)]
        rp = zz.geometry.representative_point()
        x, y = float(np.average(rp.x, weights=zz["pop"])), float(np.average(rp.y, weights=zz["pop"]))
        whole = zz.geometry.union_all() if hasattr(zz.geometry, "union_all") else zz.geometry.unary_union
        q = Point(x, y)
        if not whole.contains(q):
            from shapely.ops import nearest_points
            q = nearest_points(whole, q)[0]
        pts.append([round(q.x, 4), round(q.y, 4)])
        rf.append({"type": "Feature", "properties": {"g": 41 + ri}, "geometry": rnd(whole.buffer(0.0005).buffer(-0.0005).simplify(0.003), 3)})
        regions.append({"name": rname, "superdistricts": members, "places": [SD_NAMES[x] for x in members],
                        "counties": sorted(set(zz.county)), "people": int(round(zz["pop"].sum()))})
        print(f"region {rname}: superdistricts {members}, {len(zz)} zones, {zz['pop'].sum():,.0f} people, bubble at {pts[-1]}", file=sys.stderr)
    b = mz.total_bounds
    dj = {d["district"]: d for d in json.loads((ROOT / "site/data/supervisor-districts.json").read_text())["districts"]}
    dpts = []
    for d in range(1, nd + 1):
        q = shape({"type": "MultiPolygon", "coordinates": dj[d]["coords"]})
        # The district's part on the city's land: District 4 takes in the Farallon Islands' water, whose polygon is
        # its biggest, so the piece holding the most neighborhood points is the one the ring sits in.
        q = max(q.geoms, key=lambda g: (sum(g.contains(Point(*p)) for p in pts[:41]), g.area)).representative_point()
        dpts.append([round(q.x, 4), round(q.y, 4)])
    check(all(-122.52 < p[0] < -122.35 and 37.70 < p[1] < 37.84 for p in dpts), "every district's point is on the city's land")
    units = {"about": "The Street Safety map's where-from view: its groups (41 SF neighborhoods in name order, then the regions "
                      "outside SF), the point each group's bubble sits at, each Supervisor district's point, each region's MTC "
                      "superdistricts and outline, the nine counties' bounds, and the times of day (name, MTC departure hours). "
                      "scripts/where-traffic-comes-from.py.",
             "groups": groups, "points": pts, "district_points": dpts, "regions": regions, "bounds": [round(float(x), 3) for x in b],
             "bins": bins, "outlines": {"type": "FeatureCollection", "features": rf}}
    write_text(OUT / "units.json", dump(units))

    # ---- one file per neighborhood and per Supervisor district
    sizes = {}
    worked = {}
    files = set()
    for i, name in enumerate(area_names):
        r = {k: np.array(A[k][i]) @ fold for k in A if k.startswith("g")}
        tot = {"arr": float(r["gfrom_arr"].sum()), "dep": float(r["gto_dep"].sum()), "thr": float(r["gfrom_thr"].sum()), "inside": S["inside"][i]}
        check(abs(tot["arr"] + tot["dep"] + tot["thr"] + tot["inside"] - S["users"][i]) <= 1 + 1e-4 * S["users"][i], f"{name}: the four groups add to its cars")
        ab = np.array(S["area_bins"][i])            # hour bin by [arr, dep, thr, inside]
        check(np.allclose(ab.sum(0), [tot["arr"], tot["dep"], tot["thr"], tot["inside"]], rtol=1e-4, atol=1), f"{name}: its times of day add to its day")
        doc = {"name": name, "tot": {k: round(v) for k, v in tot.items()},
               "g": {k: np.round(r["g" + k2]).astype(int).tolist() for k, k2 in KEYS},
               "bins": {k: np.round(ab[:, j]).astype(int).tolist() for j, k in enumerate(("arr", "dep", "thr", "inside"))}}
        for k, k2 in KEYS:
            exact = float(r["g" + k2].sum())
            gap = abs(sum(doc["g"][k]) - exact)
            (warn if a.smoke else check)(gap <= NG / 2 + 1, f"{name}: {k} by group ({sum(doc['g'][k]):,}) within rounding of {exact:,.0f}")
        for k in ("arr", "dep", "thr", "inside"):
            (warn if a.smoke else check)(abs(sum(doc["bins"][k]) - doc["tot"][k]) <= len(bins), f"{name}: {k} by time of day ({sum(doc['bins'][k]):,}) within rounding of {doc['tot'][k]:,}")
        if i < 41:
            check(doc["g"]["fa"][i] == 0 and doc["g"]["ft"][i] == 0 and doc["g"]["td"][i] == 0 and doc["g"]["tt"][i] == 0, f"{name}: no car from outside it starts or ends in it")
        if i >= 41 + nd:
            worked[name] = doc
            continue
        if name in ("Bayview Hunters Point", "Sunset/Parkside", "District 4"):
            worked[name] = doc
        t = dump(doc)
        fn = f"area-{slug(name)}.json"
        files.add(fn)
        write_text(OUT / fn, t)
        sizes[name] = len(t)
    check(len(sizes) == 41 + nd, "a file for every neighborhood and Supervisor district")
    # modes-*.json are tools/street-safety/where-traffic-modes.py's.
    stale = sorted(p.name for p in OUT.glob("*.json") if p.name not in files | {"units.json", "links.json"} and not p.name.startswith("modes-"))
    for p in stale:
        (OUT / p).unlink()
    print(f"area files: {min(sizes.values()):,} to {max(sizes.values()):,} bytes; removed {stale}", file=sys.stderr)

    # ---- the cordon table: every SF street link's two nodes and its cars by origin and destination group
    links = cached("links.json")
    geo = {(l["a"], l["b"]): shape(json.loads(l["geometry"])) for l in links}
    # One position per node. Link geometry is drawn from b to a, and each direction is offset from the centreline, so a
    # node's position is the mean of the last coordinate of links leaving it and the first of links entering it
    # (network-flows-prototype.py).
    acc = collections.defaultdict(list)
    for (na, nb), g in geo.items():
        if g.is_empty:
            continue
        parts = list(g.geoms) if hasattr(g, "geoms") else [g]
        acc[nb].append(parts[0].coords[0])
        acc[na].append(parts[-1].coords[-1])
    pos = {n: (float(np.mean([c[0] for c in cs])), float(np.mean([c[1] for c in cs]))) for n, cs in acc.items()}
    L = S["links"]
    keys = sorted(L, key=lambda k: tuple(int(x) for x in k.split("_")))
    node_ids = sorted({int(x) for k in keys for x in k.split("_")})
    check(all(n in pos for n in node_ids), "every link's nodes have a position")
    nix = {n: i for i, n in enumerate(node_ids)}

    def sparse(v):
        out = []
        for g, x in enumerate(np.array(v) @ fold):
            x = round(x)
            if x:
                out += [g, x]
        return out
    fwy = set(S["freeway"])   # freeways, connectors and ramps: not an area's streets
    check(len(fwy) >= 100, f"the cordon table has the freeway and ramp links ({len(fwy)})")
    rows = [[nix[int(k.split("_")[0])], nix[int(k.split("_")[1])], sparse(L[k]["o"]), sparse(L[k]["d"])] + ([1] if k in fwy else []) for k in keys]
    full = sum(sum(L[k]["o"]) for k in keys)
    rows = [r for r in rows if r[2] or r[3]]    # a link under half a car a day by every group adds nothing to a count
    kept = sum(r[2][j + 1] for r in rows for j in range(0, len(r[2]), 2))
    check(abs(kept - full) <= 0.03 * full, f"the cordon table keeps its cars after rounding ({kept:,} of {full:,.0f})")
    ldoc = {"about": "Per SF link with cars: tail and head node (index into nodes, lon/lat), a weekday's cars by origin group "
                     "and by destination group as [group, cars, ...] (groups in units.json), and a 1 for a freeway, connector or "
                     "ramp link. The page's cordon count for a drawn area: the street links onto its street nodes from "
                     "outside, plus, at each of its street nodes touching a freeway or ramp, the cars its street links carry "
                     "away beyond those they bring in (and the reverse, by destination). scripts/where-traffic-comes-from.py.",
            "select_sha256": hashlib.sha256(raw).hexdigest(),
            "nodes": [[round(pos[n][0], 5), round(pos[n][1], 5)] for n in node_ids], "links": rows}
    lt = dump(ldoc)
    gz = len(gzip.compress(lt.encode(), 9))
    print(f"links.json: {len(rows):,} links, {len(lt):,} bytes, {gz:,} gzipped", file=sys.stderr)
    check(gz <= MAX_GZ, f"links.json under {MAX_GZ:,} bytes gzipped ({gz:,})")
    write_text(OUT / "links.json", lt)
    ut = dump(units)
    print(f"units.json: {len(ut):,} bytes, {len(gzip.compress(ut.encode(), 9)):,} gzipped", file=sys.stderr)

    # ---- each neighborhood's cordon count against its select-link count
    polys = [shape(f["geometry"]) for f in H]
    node_hood = {}
    import shapely
    npts = [Point(pos[n]) for n in node_ids]
    tree = shapely.STRtree(npts)
    for h, poly in enumerate(polys):
        for j in tree.query(poly, predicate="contains"):
            node_hood[node_ids[j]] = h
    ratios, own, outside = {}, {}, {}
    hood_of = [node_hood.get(n, -1) for n in node_ids]
    gsum = lambda k, h: np.array(A[k][h]) @ fold
    for h, name in enumerate(names):
        inG, outG = cordon(rows, len(node_ids), [x == h for x in hood_of], NG)
        inbound, outbound = float(inG.sum()), float(outG.sum())
        own[name] = inG[h] / inbound if inbound else 0
        sel_out = gsum("gfrom_arr", h)[41:].sum() + gsum("gfrom_thr", h)[41:].sum()
        outside[name] = float(inG[41:].sum()) / sel_out if sel_out else 1
        sel_in = gsum("gfrom_arr", h).sum() + gsum("gfrom_thr", h).sum()
        sel_o = gsum("gto_dep", h).sum() + gsum("gto_thr", h).sum()
        ratios[name] = (inbound / sel_in if sel_in else 0, outbound / sel_o if sel_o else 0)
    rin = sorted(r[0] for r in ratios.values())
    print("cordon inbound / select-link coming in, by neighborhood: median %.2f, range %.2f to %.2f" % (np.median(rin), rin[0], rin[-1]), file=sys.stderr)
    check(0.8 <= np.median(rin) <= 1.6, f"the median neighborhood's cordon count is within 0.8 to 1.6 of its select-link count ({np.median(rin):.2f})")
    cty = sorted(outside.values())
    for n, v in sorted(outside.items(), key=lambda kv: kv[1])[:5]:
        print(f"   from outside SF, {n}: {v:.2f}", file=sys.stderr)
    print("cordon inbound / select-link coming in from outside SF: median %.2f, range %.2f to %.2f" % (np.median(cty), cty[0], cty[-1]), file=sys.stderr)
    # Without the ramps Treasure Island read 0.00 and the Presidio 0.04. The lowest left is Oceanview/Merced/Ingleside at
    # about half: at an at-grade junction with 19th Avenue and Junipero Serra (HWY 1, not a street here) a car turning
    # off and one of the same group turning on cancel in the node's net count [inference: not checked per node].
    check(cty[0] >= 0.4, f"every neighborhood's cordon count keeps the cars from outside SF (lowest ratio {cty[0]:.2f}): ramps inside the area count")
    check(np.median(list(own.values())) <= 0.25, f"few cars entering a neighborhood start in it (median share {np.median(list(own.values())):.2f}); more means the links read backwards")

    for name, d in worked.items():
        t = d["tot"]
        users = t["arr"] + t["dep"] + t["thr"] + t["inside"]
        top = sorted(range(NG), key=lambda g: -(d["g"]["fa"][g] + d["g"]["ft"][g]))[:4]
        print(f"WORKED {name}: {users:,} cars on its streets; coming from outside {t['arr'] + t['thr']:,} (ends here {t['arr']:,}, through {t['thr']:,}); "
              f"going outside {t['dep'] + t['thr']:,}; inside {t['inside']:,}; top origins: "
              + ", ".join(f"{groups[g]} {d['g']['fa'][g] + d['g']['ft'][g]:,}" for g in top)
              + "; regions from: " + ", ".join(f"{groups[g]} {d['g']['fa'][g] + d['g']['ft'][g]:,}" for g in range(41, NG))
              + "; by time coming in " + str([x + y for x, y in zip(d["bins"]["arr"], d["bins"]["thr"])])
              + ", going out " + str([x + y for x, y in zip(d["bins"]["dep"], d["bins"]["thr"])]), file=sys.stderr)


if __name__ == "__main__":
    main()
