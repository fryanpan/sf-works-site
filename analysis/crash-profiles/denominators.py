#!/usr/bin/env python3
"""Feasibility of exposure denominators for SF's police-reported injury crashes (traffic, walking and biking counts, modelled volumes, residents), how many crash blocks each covers, and people hurt per 1,000 residents by analysis neighborhood and by Equity Priority Community.

    python3 analysis/crash-profiles/denominators.py                 # 2017-2024, writes out/crash-augment/profiles/denominators.json
    python3 analysis/crash-profiles/denominators.py --years 2018 2024

Standard library only. A feasibility pass, not an updater: three outside sources are read once and held in
.cache/crash-augment/denominators/ (gitignored), and a run with the copies held makes no request and writes the same
bytes. Delete a copy to read it again. The read date is the copy's, not the run's.

INPUTS
  crashes, victims   out/crash-augment/tables/ (pipeline/crash-augment), crashes 2017-2024 by collision_datetime.
                     A crash's blocks are street_block_cnns (segment CNNs); its intersection is cnn_intrsctn_fkey.
  residents          data/extract/census-blocks/2020.json: Census 2020 P1 population per block (DataSF p2fw-hsrv), with
                     each block's interior point. Checked against the Census 2020 county total, 873,965.
  neighborhoods      data/extract/neighborhoods/analysis-neighborhoods.geojson (DataSF's 41 analysis neighborhoods).
                     A block's people go to the neighborhood holding its interior point.
  EPC                each crash's in_epc and epc_tract (MTC Equity Priority Communities, PBA 2050 Plus, 2020 tracts). A
                     tract's flag is read off the crashes in it; residents of a tract with no crash are reported, not
                     guessed.
  residential-traffic data/extract/residential-traffic/blocks.json (tools/street-safety/hin-cut-through.py): peak-hour
                     vehicles per residential and main-street block, by how found (measured, carried, modelled,
                     estimated, none).
  through-traffic    data/extract/through-traffic/blocks.json (tools/street-safety/through-traffic.py): MTC Travel
                     Model 1.6 (2023) weekday car trips per block on SF-CHAMP's network.
  corridor counts    SFMTA Corridor Counts CSV, https://www.sfmta.com/media/40635/download: one row per direction, block
                     and day, VOLUME_ADT and peak volumes, keyed by segment CNN.
  ped volume model   SFMTA ArcGIS MTA.pedvolumemodel, https://services.sfmta.com/arcgis/rest/services/Pedestrian/pedestrian/MapServer/2:
                     modelled pedestrian volume (MODEL6_VOL) per intersection CNN, from 2011 transportation data and
                     2000 Census data; the layer says "Updated: Never".
  bike manual counts DataSF v4v2-5x7s: PM peak bike counts, 2006-2017 (2012 missing), 119 rows of which 89 hold a
                     count; its cnn column holds latitudes, so a location is matched to crashes within 150 feet.
  telraam            data/extract/telraam/segments.json (tools/street-safety/telraam-sf.py), counted only.

COVERAGE
  A crash is covered when any of its blocks (street_block_cnns) has the source's value; all_blocks requires every
  block. Most crashes sit at an intersection and their blocks are the primary road's (street_block_join
  node_primary_rd), so the cross street's volume is never tested. Intersection sources count only crashes coded at an
  intersection. Corridor-count rows with no CNN are left out of the CNN match, and the JSON says how many.

PER-RESIDENT RATES
  People hurt (any injury) and KSI people per 1,000 residents per year, by the neighborhood or EPC status of the crash
  location, over the 2020 census population. This is crashes where people live, not the risk a resident runs:
  downtown neighborhoods draw workers and visitors whom no residents' count holds, so their rate is high for that
  reason. A rate is printed for every neighborhood; none is left out for being small.
"""

import argparse
import collections
import csv
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from lib.fetch import read as http_read  # noqa: E402
from lib.pip import PolygonIndex  # noqa: E402

TABLES = os.path.join(ROOT, "out", "crash-augment", "tables")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "denominators.json")
CACHE = os.path.join(ROOT, ".cache", "crash-augment", "denominators")
csv.field_size_limit(1 << 24)

KSI_PERSON = {"Fatal Injury", "Severe Injury"}
NOT_HURT = {"No Injury", ""}
FEW_RESIDENTS = 5000  # a neighborhood under this is flagged: its rate divides by almost no one (parks, the Presidio)
SF_POP_2020 = 873965  # Census 2020 P1, San Francisco County [model knowledge — verify]; the check below tests it

CORRIDOR_URL = "https://www.sfmta.com/media/40635/download"
PEDVOL_URL = "https://services.sfmta.com/arcgis/rest/services/Pedestrian/pedestrian/MapServer/2/query"
BIKEMAN_URL = "https://data.sfgov.org/resource/v4v2-5x7s.json"


# ---- held outside copies -------------------------------------------------------------------------------------

def held(name, fetch):
    """The held copy of one outside source, read once. {"read_on": date, "rows": [...]}."""
    path = os.path.join(CACHE, name + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    import datetime
    rows = fetch()
    d = {"read_on": datetime.date.today().isoformat(), "rows": rows}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)
    return d


def fetch_corridor():
    raw = http_read(CORRIDOR_URL, timeout=180)
    text = raw.decode("latin-1") if isinstance(raw, bytes) else raw
    keep = ("CNN", "PRIMARY_STREET", "DIRECTION", "DATE", "YEAR", "VOLUME_ADT", "VOLUME_AM_PEAK", "VOLUME_PM_PEAK")
    rows = [{k: (r.get(k) or "").strip() for k in keep} for r in csv.DictReader(text.splitlines())]
    if len(rows) < 5000:
        raise SystemExit("corridor counts: %d rows, expected over 5,000" % len(rows))
    return rows


def fetch_pedvol():
    rows, offset = [], 0
    while True:
        q = {"where": "1=1", "outFields": "CNN,MODEL6_VOL,SIGNALIZED", "returnGeometry": "false",
             "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": 2000, "f": "json"}
        d = json.loads(http_read(PEDVOL_URL + "?" + urllib.parse.urlencode(q), timeout=180))
        feats = d.get("features", [])
        rows += [f["attributes"] for f in feats]
        if len(feats) < 2000:
            break
        offset += 2000
    if len(rows) < 8000:
        raise SystemExit("ped volume model: %d rows, expected 8,135" % len(rows))
    return rows


def fetch_bikeman():
    rows = json.loads(http_read(BIKEMAN_URL + "?$limit=5000&$order=objectid", timeout=180))
    if len(rows) < 100:
        raise SystemExit("bike manual counts: %d rows, expected 119" % len(rows))
    # The cnn column holds latitudes on DataSF (read 2026-11-25), so the point is kept for a distance match instead.
    return [dict({k: v for k, v in r.items() if k in ("loc_id", "location") or k.startswith("yr")},
                 lon=r["shape"]["coordinates"][0], lat=r["shape"]["coordinates"][1]) for r in rows]


def cnn(v):
    return str(v or "").split(".")[0].strip()


# ---- crashes -------------------------------------------------------------------------------------------------

def load(y0, y1):
    def rows(name):
        with open(os.path.join(TABLES, name + ".csv"), newline="") as f:
            for r in csv.DictReader(f):
                if y0 <= int(r["collision_datetime"][:4] or 0) <= y1:
                    yield r
    hurt, ksi, roles = collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    for v in rows("victims"):
        if v["victim_degree_of_injury"] not in NOT_HURT:
            hurt[v["case_id_pkey"]] += 1
            roles[v["case_id_pkey"]][v["victim_role"]] += 1
        if v["victim_degree_of_injury"] in KSI_PERSON:
            ksi[v["case_id_pkey"]] += 1
    crashes = []
    for c in rows("crashes"):
        cid = c["case_id_pkey"]
        crashes.append({"id": cid, "blocks": [b for b in c["street_block_cnns"].split(";") if b],
                        "node": cnn(c["cnn_intrsctn_fkey"]), "join": c["street_block_join"],
                        "at_node": c["intersection"].startswith("Intersection"),
                        "lat": float(c["tb_latitude"] or 0), "lon": float(c["tb_longitude"] or 0),
                        "nhood": c["analysis_neighborhood"], "tract": c["epc_tract"], "in_epc": c["in_epc"],
                        "hurt": hurt[cid], "ksi": ksi[cid], "ped": roles[cid]["Pedestrian"],
                        "bike": roles[cid]["Bicyclist"]})
    return crashes


def coverage(crashes, covered, by="blocks", who="hurt"):
    """Share of crashes, people hurt and KSI people whose block (any of them) or intersection is in covered."""
    def hit(c):
        if by == "near":
            return covered(c)
        if by == "all_blocks":
            return bool(c["blocks"]) and all(b in covered for b in c["blocks"])
        return any(b in covered for b in c["blocks"]) if by == "blocks" else c["node"] in covered
    base = [c for c in crashes if (c[who] if who in ("ped", "bike") else True) and (by != "node" or c["at_node"])]
    got = [c for c in base if hit(c)]
    n, k = sum(c[who] if who in ("ped", "bike") else c["hurt"] for c in base), sum(c["ksi"] for c in base)
    gn, gk = sum(c[who] if who in ("ped", "bike") else c["hurt"] for c in got), sum(c["ksi"] for c in got)
    return {"crashes": len(base), "crashes_covered": len(got),
            "share_crashes": round(len(got) / len(base), 4) if base else None,
            "people_hurt" if who not in ("ped", "bike") else who + "_people_hurt": n,
            "people_hurt_covered" if who not in ("ped", "bike") else who + "_people_hurt_covered": gn,
            "ksi_people": k, "ksi_people_covered": gk}


# ---- main ----------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", nargs=2, type=int, default=[2017, 2024])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    y0, y1 = a.years
    nyears = y1 - y0 + 1
    crashes = load(y0, y1)

    # residents per neighborhood and per tract
    with open(os.path.join(ROOT, "data", "extract", "census-blocks", "2020.json")) as f:
        cb = json.load(f)
    with open(os.path.join(ROOT, "data", "extract", "neighborhoods", "analysis-neighborhoods.geojson")) as f:
        gj = json.load(f)
    items = []
    for feat in gj["features"]:
        g = feat["geometry"]
        items.append((feat["properties"]["nhood"], g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]))
    idx = PolygonIndex(items)
    pop_nh, pop_tract = collections.Counter(), collections.Counter()
    unplaced = {"blocks": 0, "people": 0}
    total_pop = 0
    for b in cb["records"]:
        p = b["pop"] or 0
        total_pop += p
        pop_tract[b["geoid"][:11]] += p
        hits = sorted(set(idx.at(b["lon"], b["lat"])))
        if len(hits) == 1:
            pop_nh[hits[0]] += p
        elif p:
            unplaced["blocks"] += 1
            unplaced["people"] += p

    # people hurt per 1,000 residents per year, by crash neighborhood
    nh = collections.defaultdict(lambda: [0, 0, 0])
    for c in crashes:
        r = nh[c["nhood"] or "not stated"]
        r[0] += 1
        r[1] += c["hurt"]
        r[2] += c["ksi"]
    by_nh = []
    for name in sorted(set(nh) | set(pop_nh)):
        n, h, k = nh.get(name, [0, 0, 0])
        p = pop_nh.get(name, 0)
        by_nh.append({"neighborhood": name, "residents_2020": p, "few_residents": p < FEW_RESIDENTS,
                      "injury_crashes": n, "people_hurt": h,
                      "ksi_people": k,
                      "people_hurt_per_1000_residents_per_year": round(h / nyears / p * 1000, 2) if p else None,
                      "ksi_per_1000_residents_per_year": round(k / nyears / p * 1000, 3) if p else None})
    by_nh.sort(key=lambda r: (-(r["people_hurt_per_1000_residents_per_year"] or -1), r["neighborhood"]))

    # by EPC status of the crash's tract
    tract_flag = {}
    conflicts = set()
    for c in crashes:
        if c["tract"]:
            if c["tract"] in tract_flag and tract_flag[c["tract"]] != c["in_epc"]:
                conflicts.add(c["tract"])
            tract_flag[c["tract"]] = c["in_epc"]
    epc = collections.defaultdict(lambda: [0, 0, 0, 0])
    for t, p in pop_tract.items():
        epc[tract_flag.get(t, "no crash in tract")][0] += p
    for c in crashes:
        r = epc[c["in_epc"] if c["tract"] else "no tract"]
        r[1] += 1
        r[2] += c["hurt"]
        r[3] += c["ksi"]
    by_epc = []
    for flag in sorted(epc):
        p, n, h, k = epc[flag]
        label = {"true": "in an EPC tract", "false": "not in an EPC tract"}.get(flag, flag)
        by_epc.append({"area": label, "residents_2020": p, "injury_crashes": n, "people_hurt": h, "ksi_people": k,
                       "people_hurt_per_1000_residents_per_year": round(h / nyears / p * 1000, 2) if p and h else None,
                       "ksi_per_1000_residents_per_year": round(k / nyears / p * 1000, 3) if p and k else None})

    # coverage of each count or model source
    corridor = held("sfmta-corridor-counts", fetch_corridor)
    pedvol = held("sfmta-ped-volume-model", fetch_pedvol)
    bikeman = held("datasf-v4v2-5x7s", fetch_bikeman)
    with open(os.path.join(ROOT, "data", "extract", "residential-traffic", "blocks.json")) as f:
        res = json.load(f)["blocks"]
    with open(os.path.join(ROOT, "data", "extract", "through-traffic", "blocks.json")) as f:
        thr = json.load(f)["blocks"]
    with open(os.path.join(ROOT, "data", "extract", "telraam", "segments.json")) as f:
        tel = json.load(f)

    corr_cnns = {cnn(r["CNN"]) for r in corridor["rows"] if cnn(r["CNN"]) and r["VOLUME_ADT"]}
    corr_years = sorted({r["YEAR"] for r in corridor["rows"] if r["YEAR"].isdigit() and r["VOLUME_ADT"]})
    corr_in_window = {cnn(r["CNN"]) for r in corridor["rows"]
                      if cnn(r["CNN"]) and r["VOLUME_ADT"] and r["YEAR"].isdigit() and y0 <= int(r["YEAR"]) <= y1}
    res_any = {b["cnn"] for b in res if b["kind"] != "none"}
    res_measured = {b["cnn"] for b in res if b["kind"] == "measured"}
    res_not_estimated = {b["cnn"] for b in res if b["kind"] not in ("none", "estimated")}
    corr_no_cnn = sum(1 for r in corridor["rows"] if not cnn(r["CNN"]))
    thr_cnns = {k for k, v in thr.items() if (v.get("bins", {}).get("all") or {}).get("cars")}
    ped_nodes = {cnn(r["CNN"]) for r in pedvol["rows"] if r.get("MODEL6_VOL") not in (None, "")}
    bike_pts = [(r["lon"], r["lat"]) for r in bikeman["rows"]
                if any(float(v) >= 0 for k, v in r.items() if k.startswith("yr") and k.endswith("_pm"))]

    def near_bike_count(c, feet=150):
        dx_ft, dy_ft = 288200.0, 364000.0  # feet per degree of longitude and latitude at 37.77 N
        return any(((c["lon"] - x) * dx_ft) ** 2 + ((c["lat"] - y) * dy_ft) ** 2 <= feet * feet for x, y in bike_pts)
    bike_years = sorted(k[2:6] for k in bikeman["rows"][0] if k.startswith("yr") and k.endswith("_pm"))

    feasibility = [
        {"source": "Census 2020 block population (P1)", "url": "https://data.sfgov.org/d/p2fw-hsrv",
         "held_as": "data/extract/census-blocks/2020.json", "measures": "residents", "years": "2020 (ACS block groups 2015-2024 also held)",
         "coverage": {"blocks": len(cb["records"]), "residents": total_pop,
                      "share_crashes_with_a_neighborhood": round(sum(1 for c in crashes if c["nhood"]) / len(crashes), 4)},
         "supports": "per-neighborhood and per-tract rate (residents, not exposure); not a per-block crash rate, since census blocks and street blocks differ",
         "built": True},
        {"source": "SFMTA Corridor Counts (tube counts)", "url": CORRIDOR_URL, "read_on": corridor["read_on"],
         "measures": "vehicles, 24-hour and peak, one direction, one day", "years": corr_years,
         "coverage": dict(coverage(crashes, corr_cnns), counted_blocks=len(corr_cnns),
                          counted_blocks_in_window=len(corr_in_window), rows=len(corridor["rows"]),
                          rows_without_cnn=corr_no_cnn,
                          in_window=coverage(crashes, corr_in_window)),
         "supports": "per-block vehicle rate on counted blocks only; counts are one or two days, so a street-class rate needs the class mix of counted blocks",
         "built": False},
        {"source": "Residential and main-street peak-hour volumes (hin-cut-through.py)",
         "url": "tools/street-safety/hin-cut-through.py", "held_as": "data/extract/residential-traffic/blocks.json",
         "measures": "two-way peak-hour vehicles: SFMTA counts, Telraam, Slow Streets evaluation, SF-CHAMP, and estimates",
         "years": "counts 2014-2023, SF-CHAMP run of mid-2019 or earlier, Telraam to 2026-11",
         "coverage": {"any_volume": dict(coverage(crashes, res_any), blocks=len(res_any)),
                      "any_volume_all_blocks": coverage(crashes, res_any, by="all_blocks"),
                      "not_estimated": dict(coverage(crashes, res_not_estimated), blocks=len(res_not_estimated)),
                      "not_estimated_all_blocks": coverage(crashes, res_not_estimated, by="all_blocks"),
                      "measured_only": dict(coverage(crashes, res_measured), blocks=len(res_measured)),
                      "measured_only_all_blocks": coverage(crashes, res_measured, by="all_blocks")},
         "supports": "per-block or per-street-class vehicle rate where measured or modelled; the estimated kind is a guess from the parallel street and should not divide a crash count",
         "built": False},
        {"source": "MTC Travel Model 1.6 (2023) car trips per block (through-traffic.py)",
         "url": "tools/street-safety/through-traffic.py", "held_as": "data/extract/through-traffic/blocks.json",
         "measures": "modelled weekday car trips routed over the block", "years": "2023 model year",
         "coverage": dict(coverage(crashes, thr_cnns), blocks=len(thr_cnns)),
         "supports": "per-block or per-street-class vehicle-trip rate on the modelled network (arterials and collectors; few residential blocks)",
         "built": False},
        {"source": "SFMTA pedestrian intersection volume model (MTA.pedvolumemodel)", "url": PEDVOL_URL.rsplit("/query", 1)[0],
         "read_on": pedvol["read_on"], "measures": "modelled pedestrian volume per intersection (MODEL6_VOL)",
         "years": "2011 transportation data, 2000 Census; never updated",
         "coverage": {"pedestrian_crashes_coded_at_an_intersection": dict(coverage(crashes, ped_nodes, by="node", who="ped"),
                                                           intersections=len(ped_nodes))},
         "supports": "per-intersection pedestrian rate, citywide, but from a model built on 2011 and 2000 data; the layer calls MODEL6_VOL an estimated yearly pedestrian volume, and its method document sits on an SFMTA internal drive",
         "built": False},
        {"source": "SFMTA manual bike counts (DataSF v4v2-5x7s)", "url": "https://data.sfgov.org/d/v4v2-5x7s",
         "read_on": bikeman["read_on"], "measures": "PM peak bicycles at intersections", "years": bike_years,
         "coverage": {"bicyclists_at_intersections_within_150_ft": dict(
             coverage(crashes, near_bike_count, by="near", who="bike"), locations=len(bike_pts),
             note="the dataset's cnn column holds latitudes, so locations are matched by distance to the crash point")},
         "supports": "neither: 89 counted locations, last count 2017, one PM peak a year",
         "built": False},
        {"source": "SFMTA bicycle loop counters (DataSF 7j2t-hunp)", "url": "https://data.sfgov.org/d/7j2t-hunp",
         "measures": "locations of 12 automated counters; DataSF holds no counts", "years": "installed 2009-2016",
         "coverage": "12 locations; counts not published on DataSF (SFMTA page says email BikeCounters@sfmta.com)",
         "supports": "neither", "built": False},
        {"source": "Telraam residents' window counters", "url": "https://telraam-api.net",
         "held_as": "data/extract/telraam/segments.json", "measures": "cars, bikes, pedestrians per segment",
         "years": tel.get("window"),
         "coverage": "%d segments kept of %d found; already folded into residential-traffic where they sit on a block" % (tel.get("kept", 0), tel.get("found", 0)),
         "supports": "neither on its own", "built": False},
        {"source": "SFCTA Congestion Management Program counts", "url": "https://www.sfcta.org/reports/congestion-management-program-2025",
         "measures": "vehicles at 29 mid-block locations; vehicles, bikes and pedestrians at 14 intersections, biennial April-May",
         "years": "2015-2025", "coverage": "43 locations; not joined",
         "supports": "trend check, not a rate", "built": False},
        {"source": "Caltrans Traffic Census AADT", "url": "https://dot.ca.gov/programs/traffic-operations/census",
         "measures": "AADT, peak hour and truck volumes", "years": "2013-2024",
         "coverage": "state highway system only (in SF: freeways and the state routes on city streets); not joined",
         "supports": "per-segment rate on state routes only", "built": False},
        {"source": "Caltrans PeMS", "url": "https://pems.dot.ca.gov", "measures": "freeway detector volumes",
         "years": "not checked", "coverage": "not opened this session; freeway detectors only, and DataSF's crash table description says crashes on highways are excluded",
         "supports": "neither for city streets", "built": False},
        {"source": "StreetLight", "url": "https://www.streetlightdata.com/",
         "measures": "modelled vehicle, bike and pedestrian volumes from location data", "years": "not checked",
         "coverage": "paid licence arranged with the company; no public download found", "supports": "per-block rate if licensed",
         "built": False},
    ]

    checks = {
        "census_total_matches_2020_county_count": total_pop == SF_POP_2020, "census_total": total_pop,
        "residents_placed_in_a_neighborhood": sum(pop_nh.values()), "unplaced": unplaced,
        "tracts_with_conflicting_epc_flag": sorted(conflicts),
        "people_hurt_by_neighborhood_sum": sum(r["people_hurt"] for r in by_nh),
        "people_hurt_total": sum(c["hurt"] for c in crashes),
    }
    out = {"about": __doc__.split("\n")[0], "years": [y0, y1],
           "counting": "people hurt: victims rows with any injury; KSI: Fatal or Severe Injury; by crash location",
           "per_resident_caveat": ("Crash location over residents: neighborhoods and EPC tracts that draw workers and "
                                   "visitors (downtown, SoMa, the Tenderloin) read high. Not a resident's risk and not an "
                                   "exposure rate. A crash on a tract boundary goes to the tract its geocoded point is in."),
           "feasibility": feasibility,
           "per_1000_residents": {"by_neighborhood": by_nh, "by_epc": by_epc},
           "checks": checks}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(json.dumps(checks))
    for r in by_epc:
        print(r)
    for r in by_nh[:6] + by_nh[-4:]:
        print(r["neighborhood"], r["residents_2020"], r["people_hurt"], r["people_hurt_per_1000_residents_per_year"],
              r["ksi_people"], r["ksi_per_1000_residents_per_year"])
    for s in feasibility:
        print(s["source"], "|", json.dumps(s["coverage"])[:300])


if __name__ == "__main__":
    main()
