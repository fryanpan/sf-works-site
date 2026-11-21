#!/usr/bin/env python3
"""The data behind "How Residents Travel: One City, Many Neighborhoods": every San Francisco census tract's outline and residents, with how its working residents get to work, cars, car miles, injuries, night safety, Muni wait, the High Injury Network, grocery walks, bike network gaps and minutes to City Hall, in site/data/neighborhood-travel.json.

    ~/.venvs/sf-works-geo/bin/python tools/travel/neighborhood-travel.py          # writes site/data/neighborhood-travel.json
    ~/.venvs/sf-works-geo/bin/python tools/travel/neighborhood-travel.py --check  # the checks on the file on disk

The unit is the 2020 census tract (DataSF sevw-6tgi, which also names each tract's Analysis Neighborhood). The
Farallon Islands tract is left off. Every per-resident or per-household figure uses the ACS 2020-24 5-year tract
estimates. Inputs, all read from caches after their first fetch (scratch/runs/neighborhood-travel/ for the web
reads, data/socrata-cache/ through lib/sfdata.py for DataSF):

  * Mode to work: ACS B08301 (means of transportation to work, workers 16 and over), as Census Reporter serves it.
    Car = drove alone + carpooled (B08301_002); transit = B08301_010; bike = _018; walk = _019; work from home =
    _021. Taxi, motorcycle and other (about 3%) are not drawn, so the five shares do not add to 100.
  * Households without a car: ACS B25044 (tenure by vehicles available), owner and renter "no vehicle available"
    (_003 + _010) over all households (_001). sources/acs-b25044-vehicles-available.md reproduces the
    county total the Bureau publishes.
  * Car miles per resident: MTC's 2023 home-based VMT per resident (ArcGIS layer mtc_vmt_home_work_pba2050p, field
    home_vmt_2023by), the same series and the same weighting as tools/travel/vmt-by-neighborhood.py: each MTC zone is cut
    by tracts and a piece takes its tract's residents by its share of the tract's land, so a tract's figure is its
    zones' rates weighted by area.
  * People hurt in traffic: DataSF nwes-mmgh, one row per person injured or killed (victim_degree_of_injury not null
    and not "No Injury"), in the five years to the data's last full month (the injury heat map's window and rule: a
    month is full when it has rows in its last three days), placed in the tract holding the crash point (split equally among tracts within EDGE_FT, since
    tract lines run down the streets crashes are geocoded to), a year,
    per 1,000 ACS residents. Freeway crashes are not in the city's data.
  * Felt unsafe walking alone at night: the 2023 City Survey by Analysis Neighborhood, rated 1 or 2 of 5
    (data/neighborhood-city-data/neighborhoods.csv, tools/travel/neighborhood-city-data.py), neighborhoods with 30 or
    more answers. A neighborhood figure, so every tract in a neighborhood carries the same value.
  * Muni excess wait: each populated 2020 block's nearest stop on site/data/muni-map.json (stops with frequent
    hours, six or more buses an hour), that stop's average excess wait over the last 365 days, and the tract's
    resident-weighted mean over blocks within EWT_MAX_FT of the stop; no figure where most residents have none.
  * High Injury Network: SFMTA and SFDPH's 2024 network (ArcGIS layer MTA.DPH_vz_hgh_injry_ntwrk_2024). Share =
    feet of network line within EDGE_FT of the tract over feet of DataSF street centerline (3psu-pn9h) within it, active city
    streets of class 2 to 5 (freeways, ramps, private and paper streets left out). Measured by geometry, not by
    CNN: a quarter of the layer's CNN_SGMT_P values (471 of 1,917 on 2026-11-17, such as 52 and 734) match no
    centerline block.
  * Walk to the nearest grocery store: the Daily Trips map's whole minutes per block (site/data/daily-trips.json,
    walking at 2 mph), resident-weighted per tract.
  * Bike network gaps: out/neighborhood-travel/bike-gaps.json (scripts/neighborhood-bike-gaps.py).
  * Minutes to City Hall: out/neighborhood-travel/city-hall.json (scripts/city-hall-transit.py), when present.

Tracts under MIN_POP residents get null for every per-resident or per-household rate (people hurt, car miles,
households without a car, mode shares), since a handful of residents makes a rate that means nothing.

Checks before writing (a failure exits 1 and leaves the old file): the tracts sum to the county's ACS totals for
population, households and workers; ACS county shares reproduce the Bureau's published S0801 and B25044 figures;
every tract is in exactly one neighborhood; people hurt reproduce the five-year total; every value is in range.
Idempotent: no run date is written, rows are in tract order and every float is rounded.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime
import json
import os
import sys
import urllib.request

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point, shape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib.stable import write_json  # noqa: E402

RUN = os.path.join(ROOT, "scratch", "runs", "neighborhood-travel")
OUT_REL = "site/data/neighborhood-travel.json"
UA = {"User-Agent": "sf-works-research/1.0"}
FARALLONES = "06075980401"
MIN_POP = 500
EDGE_FT = 40       # a crash or street this close to a tract line counts in every tract it touches
EWT_MAX_FT = 1320  # a quarter mile: no Muni wait figure for a block farther than this from a frequent stop
STEP = 1e5
CR = "https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B01003,B25044,B08301&geo_ids=%s"
S0801 = "https://data.census.gov/api/access/data/table?id=ACSST5Y2024.S0801&g=050XX00US06075"
MTC = ("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/mtc_vmt_home_work_pba2050p/FeatureServer/0/"
       "query?where=county%3D%27San+Francisco%27&outFields=*&returnGeometry=true&outSR=4326&f=geojson")
HIN = "https://services.arcgis.com/Zs2aNLFN00jrS4gG/arcgis/rest/services/HIN/FeatureServer/0"
INJ_SELECT = ("case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,collision_datetime,"
              "collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd,intersection,distance,ped_action,"
              "street_of_travel,move_pre_acc,party_type,party_number_ckey,type_of_collision,vz_pcf_code")
MAX_AGE_DAYS = 35


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        raise SystemExit(1)


def get(url, name):
    os.makedirs(RUN, exist_ok=True)
    p = os.path.join(RUN, name)
    if not os.path.exists(p):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
            open(p, "wb").write(r.read())
    return p


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return json.load(f)


def r3(v, nd=3):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


# ---- tracts ---------------------------------------------------------------------------------------------------

def tracts():
    rows = sfdata.fetch("sevw-6tgi", floor=240)
    g = gpd.GeoDataFrame(
        {"geoid": [r["geoid"] for r in rows.rows], "hood": [r["neighborhoods_analysis_boundaries"] for r in rows.rows]},
        geometry=[shape(r["the_geom"]) for r in rows.rows], crs=4326)
    check(g.geoid.is_unique and g.hood.notna().all(), "sevw-6tgi: %d tracts, each in one neighborhood" % len(g))
    return g[g.geoid != FARALLONES].sort_values("geoid").reset_index(drop=True), str(rows.fetched_on)


# ---- ACS ------------------------------------------------------------------------------------------------------

def acs(geoids):
    cr = json.load(open(get(CR % "140|05000US06075", "cr_tracts.json")))["data"]
    county = json.load(open(get(CR % "05000US06075", "cr_county.json")))["data"]["05000US06075"]
    s = json.load(open(get(S0801, "s0801_county.json")))["response"]["data"]
    s = dict(zip(s[0], s[1]))
    rows = []
    for gid, t in cr.items():
        e = lambda tb, k: t[tb]["estimate"].get(k) or 0  # noqa: E731
        rows.append(dict(geoid=gid[-11:], pop=e("B01003", "B01003001"), hh=e("B25044", "B25044001"),
                         hh0=e("B25044", "B25044003") + e("B25044", "B25044010"), wk=e("B08301", "B08301001"),
                         car=e("B08301", "B08301002"), transit=e("B08301", "B08301010"),
                         bike=e("B08301", "B08301018"), walk=e("B08301", "B08301019"), wfh=e("B08301", "B08301021")))
    a = pd.DataFrame(rows).set_index("geoid")
    ce = lambda tb, k: county[tb]["estimate"][k]  # noqa: E731
    for col, tb, k in (("pop", "B01003", "B01003001"), ("hh", "B25044", "B25044001"), ("wk", "B08301", "B08301001")):
        check(abs(a[col].sum() - ce(tb, k)) <= max(1, 0.001 * ce(tb, k)),
              "ACS tracts sum to the county's %s: %d vs %d" % (k, a[col].sum(), ce(tb, k)))
    car = 100 * a.car.sum() / a.wk.sum()
    check(abs(car - float(s["S0801_C01_002E"])) <= 0.1, "county car share %.1f%% matches S0801's published %s%%" % (
        car, s["S0801_C01_002E"]))
    hh0c = ce("B25044", "B25044003") + ce("B25044", "B25044010")
    check(a.hh0.sum() == hh0c, "tracts sum to the county's households with no vehicle: %d vs %d" % (a.hh0.sum(), hh0c))
    zc = 100 * (ce("B25044", "B25044003") + ce("B25044", "B25044010")) / ce("B25044", "B25044001")
    print("county households without a car: %.1f%% (%d of %d)" % (
        zc, ce("B25044", "B25044003") + ce("B25044", "B25044010"), ce("B25044", "B25044001")))
    missing = sorted(set(geoids) - set(a.index))
    check(not missing, "every map tract has ACS figures %s" % missing[:5])
    extra = a.loc[sorted(set(a.index) - set(geoids)), "pop"].sum()
    check(extra == 0, "no ACS residents outside the map's tracts (Farallones: %d)" % extra)
    return a.reindex(geoids), {"county_zero_car_pct": round(zc, 1), "county_car_pct": round(car, 1),
                               "county_pop": int(ce("B01003", "B01003001"))}


# ---- MTC car miles --------------------------------------------------------------------------------------------

def vmt(tr, pop):
    z = gpd.read_file(get(MTC, "mtc_sf.geojson"))[["home_vmt_2023by", "geometry"]].to_crs(2227)
    z = z[z.home_vmt_2023by.notna() & (z.home_vmt_2023by > 0)]
    t = tr[["geoid", "geometry"]].to_crs(2227)
    p = gpd.overlay(t, z, how="intersection", keep_geom_type=True)
    p["a"] = p.area
    out = p.groupby("geoid").apply(lambda x: (x.home_vmt_2023by * x.a).sum() / x.a.sum(), include_groups=False)
    covered = p.groupby("geoid").a.sum() / t.set_index("geoid").area
    v = out.reindex(tr.geoid)
    city = (v * pop.values).sum() / pop[v.notna().values].sum()
    print("MTC VMT: %d tracts with a rate; citywide %.2f miles per resident (neighborhoods.csv: 7.02)"
          % (v.notna().sum(), city))
    cov = covered.reindex(tr.geoid).values
    check(np.nanmin(cov[pop.values >= MIN_POP]) > 0.75, "MTC zones cover at least 75%% of every tract with %d+ residents (least %.0f%%)"
          % (MIN_POP, 100 * np.nanmin(cov[pop.values >= MIN_POP])))
    check(v[pop.values >= MIN_POP].notna().all(), "every tract with %d+ residents has an MTC rate" % MIN_POP)
    return v.values, city


# ---- people hurt ----------------------------------------------------------------------------------------------

def injuries(tr):
    V = sfdata.fetch("nwes-mmgh", select=INJ_SELECT, floor=80000, max_age_days=MAX_AGE_DAYS)
    rows = [v for v in V.rows if v.get("victim_degree_of_injury") not in (None, "No Injury")
            and len(v.get("collision_datetime") or "") >= 10]
    days = collections.defaultdict(set)
    for v in rows:
        days[v["collision_datetime"][:7]].add(v["collision_datetime"][:10])
    full = []
    for m in sorted(days):
        y, mo = int(m[:4]), int(m[5:7])
        last = (datetime.date(y + mo // 12, mo % 12 + 1, 1) - datetime.timedelta(days=1)).day
        if all("%s-%02d" % (m, d) in days[m] for d in (last - 2, last - 1, last)):
            full.append(m)
    end = full[-1]
    y, mo = int(end[:4]), int(end[5:7])
    start = "%04d-%02d" % (y - 5 + (mo // 12), mo % 12 + 1)
    win = [v for v in rows if start <= v["collision_datetime"][:7] <= end]
    keys = collections.Counter((v["case_id_pkey"], v["victim_id"]) for v in win)
    check(max(keys.values()) == 1, "case and victim id unique across %d people hurt %s to %s" % (len(win), start, end))
    pts = []
    for v in win:
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            pts.append(None)
            continue
        if 37.6 < la < 37.85 and 122.35 < lo < 122.53:
            lo = -lo   # a dropped sign, as the heat map flips it back
        pts.append(Point(lo, la) if 37.6 < la < 37.85 and -122.53 < lo < -122.35 else None)
    P = gpd.GeoDataFrame({"i": range(len(pts))}, geometry=pts, crs=4326)
    have = P[P.geometry.notna()]
    # Tract lines run down street centerlines and crashes are geocoded onto them, so a third of people hurt sit
    # within a foot of a tract line. A crash within EDGE_FT of more than one tract is split equally among them.
    tb = tr[["geoid", "geometry"]].to_crs(2227)
    tb["geometry"] = tb.buffer(EDGE_FT)
    J = gpd.sjoin(have.to_crs(2227), tb, how="inner", predicate="within")
    J["w"] = 1.0 / J.groupby(level=0).geoid.transform("size")
    placed = J.index.nunique()
    print("people hurt: %d in the window, %d with a point, %d inside a map tract" % (len(win), len(have), placed))
    check(placed / len(win) > 0.97, "at least 97%% of people hurt are placed in a tract (%.1f%%)" % (100 * placed / len(win)))
    n = J.groupby("geoid").w.sum().reindex(tr.geoid).fillna(0).values
    check(abs(n.sum() - placed) < 1e-6, "split crashes add back to the %d people placed" % placed)
    return n, {"from": start, "to": end, "people": len(win), "placed": int(placed), "read": str(V.fetched_on)}


# ---- night safety (neighborhood) ------------------------------------------------------------------------------

def night(tr):
    d = pd.read_csv(os.path.join(ROOT, "data", "neighborhood-city-data", "neighborhoods.csv")).set_index("neighborhood")
    ok = d[(d.night_n >= 30)]
    v = tr.hood.map(ok.night)
    unknown = sorted(set(tr.hood) - set(d.index))
    check(not unknown, "every tract's neighborhood is in the City Survey table %s" % unknown)
    return v.values, float(d.loc["San Francisco", "night"])


# ---- blocks: Muni wait and grocery walk -----------------------------------------------------------------------

def block_metrics(geoids):
    dt_ = read("site/data/daily-trips.json")
    pts = {r["geoid"]: r for r in read("data/extract/census-blocks/2020.json")["records"]}
    mm = read("site/data/muni-map.json")["stops"]
    st = [(s["lon"], s["lat"], s["ewt"]["365"]) for s in mm if s["ewt"].get("365") is not None]
    sx = np.array([s[0] for s in st]) * np.cos(np.radians(37.76))
    sy = np.array([s[1] for s in st])
    se = np.array([s[2] for s in st])
    from scipy.spatial import cKDTree
    kd = cKDTree(np.c_[sx, sy])
    acc = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0])
    groc = dt_["min"]["grocery"]["walk"]
    for i, g in enumerate(dt_["geoid"]):
        p = dt_["pop"][i]
        b = pts[g]
        dist, j = kd.query([b["lon"] * np.cos(np.radians(37.76)), b["lat"]])
        a = acc[g[:11]]
        a[0] += p
        if dist * 364000 <= EWT_MAX_FT:   # degrees of latitude to feet
            a[4] += p
            a[1] += p * se[j]
        a[2] += p * groc[i]
        a[3] += p * dist * 364000   # degrees of latitude to feet
    # A tract's wait averages the residents within a quarter mile of a frequent stop; a tract where most residents
    # have none gets no figure.
    ewt = np.array([acc[g][1] / acc[g][4] if acc[g][4] and acc[g][4] >= 0.5 * acc[g][0] else np.nan for g in geoids])
    gro = np.array([acc[g][2] / acc[g][0] if acc[g][0] else np.nan for g in geoids])
    far = np.array([acc[g][3] / acc[g][0] if acc[g][0] else np.nan for g in geoids])
    check(sum(a[0] for a in acc.values()) == dt_["residents"], "Daily Trips blocks hold all %d residents" % dt_["residents"])
    near = sum(a[4] for a in acc.values())
    print("Muni: %d frequent stops with a 365-day excess wait; tract mean distance to it %.0f ft median; %d residents "
          "(%.1f%%) more than %d ft from one; %d tracts with no figure" % (len(st), np.nanmedian(far), dt_["residents"] - near,
          100 * (1 - near / dt_["residents"]), EWT_MAX_FT, int(np.isnan(ewt).sum())))
    return ewt, gro, len(st)


# ---- High Injury Network --------------------------------------------------------------------------------------

def hin(tr):
    p = os.path.join(RUN, "hin-2024.geojson")
    if not os.path.exists(p):
        feats, off = [], 0
        while True:
            url = HIN + "/query?where=1%3D1&outFields=OBJECTID,CNN_SGMT_P&returnGeometry=true&outSR=4326&f=geojson" \
                + "&resultOffset=%d&resultRecordCount=1000&orderByFields=OBJECTID" % off
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))
            f = d.get("features", [])
            feats += f
            off += len(f)
            if not f or not (d.get("properties") or {}).get("exceededTransferLimit", d.get("exceededTransferLimit")):
                if len(f) < 1000:
                    break
        json.dump({"type": "FeatureCollection", "read": datetime.date.today().isoformat(), "features": feats}, open(p, "w"))
    H = gpd.read_file(p).to_crs(2227)
    H = H[H.geometry.notna()]
    check(len(H) >= 1500, "HIN 2024: %d lines (layer count 1,917 on 2026-11-17)" % len(H))
    C = sfdata.fetch("3psu-pn9h")
    keep = [r for r in C.rows if r.get("active") in (True, "True", "true") and r.get("classcode") in ("2", "3", "4", "5")
            and r.get("line")]
    g = gpd.GeoDataFrame(geometry=[shape(r["line"]) for r in keep], crs=4326).to_crs(2227)
    t = tr[["geoid", "geometry"]].to_crs(2227)
    # Tract lines run down street centerlines, so each tract is widened by EDGE_FT before the cut: a street on a tract
    # line counts in both tracts, in the street miles and the network miles alike. The citywide share uses the
    # uncut layers.
    t["geometry"] = t.buffer(EDGE_FT)
    gl = gpd.overlay(g, t, how="intersection", keep_geom_type=True)
    hl = gpd.overlay(H[["geometry"]], t, how="intersection", keep_geom_type=True)
    tot = gl.assign(ft=gl.length).groupby("geoid").ft.sum()
    onl = hl.assign(ft=hl.length).groupby("geoid").ft.sum()
    share = (onl / tot).reindex(tr.geoid).fillna(0).clip(upper=1.0).values
    city = float(H.length.sum() / g.length.sum())
    print("HIN: %.0f miles of network, %.0f miles of city streets (class 2 to 5); %.1f%% citywide; tracts over 100%%: %d"
          % (H.length.sum() / 5280, g.length.sum() / 5280, 100 * city, int(((onl / tot) > 1).sum())))
    read_on = json.load(open(p)).get("read")
    return share, city, read_on, str(C.fetched_on)


# ---- outlines -------------------------------------------------------------------------------------------------

def outlines(tr):
    geoms = shapely.coverage_simplify(np.array(tr.to_crs(2227).geometry.values), 30.0)   # 30 ft, shared edges kept
    geoms = gpd.GeoSeries(geoms, crs=2227).to_crs(4326)
    n, d, shp = [], [], []
    cx = cy = 0
    for gm in geoms:
        polys = list(gm.geoms) if gm.geom_type == "MultiPolygon" else [gm]
        shp.append([1 + len(p.interiors) for p in polys])
        for p in polys:
            for ring in [p.exterior] + list(p.interiors):
                pts = [(int(round(x * STEP)), int(round(y * STEP))) for x, y in ring.coords]
                n.append(len(pts))
                for x, y in pts:
                    d += [x - cx, y - cy]
                    cx, cy = x, y
    return {"n": n, "d": d, "shape": shp}


def build():
    tr, tr_read = tracts()
    geoids = list(tr.geoid)
    a, acs_meta = acs(geoids)
    pop = a["pop"].astype(int)
    small = (pop < MIN_POP).values
    v, vmt_city = vmt(tr, pop)
    hurt5, inj = injuries(tr)
    nt, night_city = night(tr)
    ewt, gro, nstops = block_metrics(geoids)
    hshare, hin_city, hin_read, cl_read = hin(tr)
    gaps = read("out/neighborhood-travel/bike-gaps.json")
    gt = {r[0]: r for r in gaps["tracts"]}
    gkeys = [x["key"] for x in gaps["destinations"]]
    ch_path = os.path.join(ROOT, "out", "neighborhood-travel", "city-hall.json")
    ch = json.load(open(ch_path)) if os.path.exists(ch_path) else None
    cht = {r[0]: r for r in ch["tracts"]} if ch else {}

    def rate(num, den, scale=1.0):
        out = []
        for i, (x, y) in enumerate(zip(num, den)):
            out.append(None if small[i] or not y else r3(scale * x / y, 4))
        return out

    M = {}
    for k in ("car", "transit", "bike", "walk", "wfh"):
        M["mode_" + k] = rate(a[k].values, a.wk.values)
    M["zero_car"] = rate(a.hh0.values, a.hh.values)
    M["vmt"] = [None if small[i] else r3(x, 2) for i, x in enumerate(v)]
    M["hurt"] = rate(hurt5 / 5, pop.values, 1000.0)
    M["night"] = [r3(x, 1) for x in nt]
    M["ewt"] = [r3(x, 2) for x in ewt]
    M["hin"] = [r3(x, 3) for x in hshare]
    M["grocery"] = [r3(x, 1) for x in gro]
    for j, k in enumerate(gkeys):
        M["gap_" + k] = [gt[g][2 + j] if g in gt else None for g in geoids]
    if ch:
        M["cityhall_muni"] = [cht[g][1] if g in cht else None for g in geoids]
        M["cityhall_walk"] = [cht[g][2] if g in cht else None for g in geoids]
    hood_names = sorted(set(tr.hood))
    city = {
        "pop": int(pop.sum()), "vmt": r3(vmt_city, 2), "night": r3(night_city, 1), "hin": r3(hin_city, 3),
        "hurt": r3(inj["placed"] / 5 / pop.sum() * 1000, 2), "zero_car": r3(a.hh0.sum() / a.hh.sum(), 4),
        **{"mode_" + k: r3(a[k].sum() / a.wk.sum(), 4) for k in ("car", "transit", "bike", "walk", "wfh")},
    }
    out = {
        "note": "Per 2020 census tract (Farallones left off), in geoid order: residents (ACS 2020-24), Analysis "
                "Neighborhood, and every metric the page draws. See tools/travel/neighborhood-travel.py for each one's "
                "definition. Null: too few residents for a rate (under %d), too few City Survey answers, or no "
                "route. Outlines as site/src/maplibre.mjs's encodeRuns; shape gives each tract's rings per polygon."
                % MIN_POP,
        "asof": {
            "acs": "2020-2024", "tracts_read": tr_read, "injuries": {k: inj[k] for k in ("from", "to", "read")},
            "city_survey": "2023", "muni_wait": read("site/data/muni.json")["windows"]["365"]["months"],
            "hin_read": hin_read, "centerlines_read": cl_read, "mtc": "2023 base year",
            "bike_network": "today's all-ages network (School Trips' rule)",
            "city_hall": ({"departure": ch["parameters"]["departure"], "gtfs_calendar": ch["inputs"]["gtfs_calendar"],
                           "osm_timestamp": ch["inputs"]["osm_timestamp"]} if ch else None),
        },
        "min_pop": MIN_POP,
        "frequent_stops": nstops,
        "people_hurt": inj["people"],
        "city": city,
        "hoods": hood_names,
        "geoid": geoids,
        "hood": [hood_names.index(h) for h in tr.hood],
        "pop": [int(x) for x in pop],
        "metrics": M,
        "outline": outlines(tr),
    }
    return out


# Plausible bounds per measure, by key prefix: a value outside one is a pipeline fault, not a finding.
RANGES = {"nigh": (0, 100), "vmt": (0, 40), "hurt": (0, 200), "ewt": (0, 15), "city": (0, 400), "groc": (0, 120),
          "gap_": (0, 60000)}


def checks(d):
    bad = []
    n = len(d["geoid"])
    if not 238 <= n <= 245:
        bad.append("%d tracts" % n)
    for k, vals in d["metrics"].items():
        if len(vals) != n:
            bad.append("%s: %d values for %d tracts" % (k, len(vals), n))
            continue
        lo, hi = (0, 1) if k.startswith("mode_") or k in ("zero_car", "hin") else RANGES.get(k[:4], (0, 1e6))
        bad += ["%s %s = %s" % (k, g, x) for g, x in zip(d["geoid"], vals) if x is not None and not lo <= x <= hi][:3]
        have = sum(1 for x in vals if x is not None)
        if have < 0.85 * n:
            bad.append("%s: only %d of %d tracts have a value" % (k, have, n))
    if sum(len(s) for s in d["outline"]["shape"]) == 0 or len(d["outline"]["shape"]) != n:
        bad.append("outlines missing")
    if sum(d["pop"]) < 800000:
        bad.append("residents %d" % sum(d["pop"]))
    for b in bad[:20]:
        print("  FAIL", b)
    print("  checks: %s" % ("passed" if not bad else "%d failed" % len(bad)))
    return not bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return 0 if checks(read(OUT_REL)) else 1
    out = build()
    if not checks(out):
        print("  kept the previous", OUT_REL)
        return 1
    write_json(os.path.join(ROOT, OUT_REL), out, separators=(",", ":"))
    print("  wrote %s (%.0f KB)" % (OUT_REL, os.path.getsize(os.path.join(ROOT, OUT_REL)) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
