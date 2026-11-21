#!/usr/bin/env python3
"""City data by San Francisco analysis neighborhood for whitepaper Part 1: modeled car miles per resident, commute mode, commute time, cars per household, people hurt in traffic per 1,000 residents, and the City Survey's Muni grade.

Run with ~/.venvs/sf-works-geo/bin/python scripts/neighborhood-city-data.py. A one-off
analysis for research/notes/whitepaper-2026-11/2026-11-12-whitepaper-part-1.mdx, not a
pipeline step. Writes data/neighborhood-city-data/neighborhoods.csv and charts.mdx (the
PlotChart blocks pasted into the doc) and prints its checks.

Inputs, reused where they already exist:
  * Modeled car miles: out.json from tools/travel/vmt-by-neighborhood.py (MTC 2023 home-based
    VMT per resident, zones split by tract land area and ACS population). Read, not rerun.
  * ACS 2020-24 5-year tract tables B01003, B25044, B08301: cr.json in the same cache.
  * Tract to neighborhood map, DataSF sevw-6tgi: tracts.geojson in the same cache. Every
    2020 tract sits in exactly one analysis neighborhood, so tracts are summed, never split.
  * New: ACS B08303 (workers who did not work at home) from Census Reporter and B08013
    (aggregate minutes to work) from data.census.gov, both by tract, cached under
    scratch/runs/neighborhood-city-data/. Mean commute = sum B08013 / sum B08303_001, the
    Census Bureau's own definition (S0801 "mean travel time to work").
  * People hurt: DataSF nwes-mmgh (one row per injured person) through lib/sfdata.py,
    2021-01-01 to 2025-12-31, the last five complete years, 'No Injury' rows dropped. Each
    person is placed by the crash point in the same tract polygons the population comes
    from, so numerator and denominator share one boundary (the dataset's own
    analysis_neighborhood field disagrees for about 4% of people, most on boundary streets,
    and fills in only where a point is missing). For Visitacion Valley and Portola it also
    prints the count within 50 ft outside the boundary, the crashes on edge streets.
  * City Survey: summarise() imported from tools/travel/city-survey-by-district.py on the same
    raw file, 2023 only, neighborhoods with 30 or more graded answers. 2026 is left out: the
    citywide grade moved 3.35 to 3.54 between waves, each neighborhood's year mix differs,
    and 2026's nhood coding looks different (Seacliff 51 respondents against 4 in 2023).
Neighborhoods under 3,000 residents are left off the charts, as in the VMT note.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, importlib.util, json, math, os, sys, urllib.request, collections
import geopandas as gpd, pandas as pd
from shapely.geometry import Point

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import sfdata

VMT = os.environ.get("VMT_CACHE", os.path.join(ROOT, "scratch", "runs", "vmt-neighborhood-cache"))
RUN = os.path.join(ROOT, "scratch", "runs", "neighborhood-city-data")
OUT = os.path.join(ROOT, "data", "neighborhood-city-data")
os.makedirs(RUN, exist_ok=True); os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "sf-works-neighborhood-city-data/1.0"}
START, END = "2021-01-01", "2025-12-31"
MIN_POP = 3000
HL = {"Visitacion Valley", "Portola"}  # edge-street counts printed for these two
BLUE, GREY = "#4269d0", "#59626f"


def get(url, name):
    p = os.path.join(RUN, name)
    if not os.path.exists(p):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            open(p, "wb").write(r.read())
    return json.load(open(p))


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        sys.exit(1)


# ---- ACS by tract ---------------------------------------------------------------
cr = json.load(open(os.path.join(VMT, "cr.json")))["data"]
b08303 = get("https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B08303&geo_ids=140|05000US06075", "cr_B08303.json")["data"]
b08013 = get("https://data.census.gov/api/access/data/table?id=ACSDT5Y2024.B08013&g=050XX00US06075$1400000", "b08013_tracts.json")["response"]["data"]
county = get("https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B01003,B08301,B08303,B08013,B25044&geo_ids=05000US06075", "cr_county.json")["data"]["05000US06075"]
s0801 = get("https://data.census.gov/api/access/data/table?id=ACSST5Y2024.S0801&g=050XX00US06075", "s0801_county.json")["response"]["data"]
s0801 = dict(zip(s0801[0], s0801[1]))
# Suppressed tracts carry the Bureau's -666666666 sentinel or nothing; all have 0 to 8 workers.
agg = {r[b08013[0].index("GEO_ID")][-11:]: max(0.0, float(r[b08013[0].index("B08013_001E")] or 0)) for r in b08013[1:]}

rows = []
for g, t in cr.items():
    e = lambda tb, k: t[tb]["estimate"].get(k) or 0
    gid = g[-11:]
    rows.append(dict(geoid=gid, pop=e("B01003", "B01003001"), hh=e("B25044", "B25044001"),
        veh=sum(n * (e("B25044", "B25044%03d" % (3 + n)) + e("B25044", "B25044%03d" % (10 + n))) for n in range(1, 6)),
        hh0=e("B25044", "B25044003") + e("B25044", "B25044010"),
        wk=e("B08301", "B08301001"), da=e("B08301", "B08301003"), cp=e("B08301", "B08301004"),
        transit=e("B08301", "B08301010"), bike=e("B08301", "B08301018"), walk=e("B08301", "B08301019"),
        other=e("B08301", "B08301016") + e("B08301", "B08301017") + e("B08301", "B08301020"),
        wfh=e("B08301", "B08301021"),
        nwfh=(b08303.get(g, {}).get("B08303", {}).get("estimate", {}).get("B08303001") or 0),
        mins=agg.get(gid, 0.0)))
acs = pd.DataFrame(rows)
ce = lambda tb, k: county[tb]["estimate"][k]
check(len(acs) == len(agg) == len(b08303), "tract counts agree: B01003 %d, B08013 %d, B08303 %d" % (len(acs), len(agg), len(b08303)))
for col, tb, k in (("pop", "B01003", "B01003001"), ("hh", "B25044", "B25044001"), ("wk", "B08301", "B08301001"),
                   ("nwfh", "B08303", "B08303001"), ("mins", "B08013", "B08013001")):
    check(abs(acs[col].sum() - ce(tb, k)) <= max(1, 0.001 * ce(tb, k)), "tracts sum to the county's %s %s: %d vs %d" % (tb, k, acs[col].sum(), ce(tb, k)))
mode_sum = acs[["da", "cp", "transit", "bike", "walk", "other", "wfh"]].sum(axis=1)
check((mode_sum == acs.wk).all(), "commute modes add up to all workers in every tract")
mean_cty = ce("B08013", "B08013001") / ce("B08303", "B08303001")
for k, num, label in (("S0801_C01_002E", ("da", "cp"), "car, truck or van"), ("S0801_C01_009E", ("transit",), "transit")):
    ours = 100 * acs[list(num)].sum().sum() / acs.wk.sum()
    check(abs(ours - float(s0801[k])) <= 0.1, "county %s share %.1f%% reproduces S0801's published %s%%" % (label, ours, s0801[k]))
check(round(mean_cty, 1) == float(s0801["S0801_C01_046E"]), "county mean commute %.2f min reproduces S0801's published %s" % (mean_cty, s0801["S0801_C01_046E"]))

tr = gpd.read_file(os.path.join(VMT, "tracts.geojson"))[["geoid", "neighborhoods_analysis_boundaries", "geometry"]]
tr = tr.rename(columns={"neighborhoods_analysis_boundaries": "hood"})
check(tr.geoid.is_unique, "each tract appears once in sevw-6tgi, so it belongs to one neighborhood")
miss = acs[~acs.geoid.isin(tr.geoid)]
print("ACS tracts not in the map:", miss[["geoid", "pop", "wk"]].to_dict("records"))
check(miss["pop"].sum() == 0, "every ACS tract with residents is in the neighborhood map")
t = tr.merge(acs, on="geoid", how="left").fillna(0)
H = t.drop(columns="geometry").groupby("hood").sum(numeric_only=True)
check(abs(H["pop"].sum() - ce("B01003", "B01003001")) < 1, "neighborhood population sums to the county's %d" % ce("B01003", "B01003001"))

# ---- modeled car miles ----------------------------------------------------------
v = pd.DataFrame(json.load(open(os.path.join(VMT, "out.json")))).set_index("hood")
check(abs(v["pop"].sum() - H["pop"].sum()) < 1, "VMT script used the same ACS population")
H["vmt"] = v["mtc"]
vmt_city = (v.mtc * v["pop"]).sum() / v.loc[v.mtc.notna(), "pop"].sum()

# ---- people hurt ------------------------------------------------------------------
V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_degree_of_injury,collision_datetime,tb_latitude,tb_longitude,analysis_neighborhood",
                 where="collision_datetime between '%sT00:00:00' and '%sT23:59:59'" % (START, END), floor=15000)
hurt = [r for r in V.rows if r.get("victim_degree_of_injury") not in (None, "No Injury")]
keys = collections.Counter((r["case_id_pkey"], r["victim_id"]) for r in hurt)
check(max(keys.values()) == 1, "case and victim id unique across %d people hurt" % len(hurt))
years = collections.Counter(r["collision_datetime"][:4] for r in hurt)
print("people hurt by year", sorted(years.items()))
check(sorted(years) == ["2021", "2022", "2023", "2024", "2025"] and min(years.values()) > 2500, "five whole years, none thin")
pts, fallback, nowhere = [], 0, 0
for r in hurt:
    try:
        la, lo = float(r["tb_latitude"]), float(r["tb_longitude"])
        if 37.6 < la < 37.85 and 122.35 < lo < 122.53:
            lo = -lo
        ok = 37.6 < la < 37.85 and -122.53 < lo < -122.35
    except (KeyError, TypeError, ValueError):
        ok = False
    pts.append((Point(lo, la) if ok else None, r.get("analysis_neighborhood"), r["victim_degree_of_injury"]))
P = gpd.GeoDataFrame({"field": [p[1] for p in pts], "sev": [p[2] for p in pts]},
                     geometry=[p[0] for p in pts], crs=4326)
has = P[P.geometry.notna()]
J = gpd.sjoin(has, tr[["hood", "geometry"]].to_crs(4326), how="left", predicate="within")
J = J[~J.index.duplicated()]
P["poly"] = None
P.loc[J.index, "poly"] = J["hood"]
agree = (P.poly == P.field)[P.poly.notna() & P.field.notna()].mean()
print("tract polygon agrees with the dataset's analysis_neighborhood for %.1f%% of people with both" % (100 * agree))
# Same boundary as the population: our polygon join; the dataset's field only fills missing points.
P["hood"] = P.poly
fallback = int((P.hood.isna() & P.field.notna()).sum())
P.loc[P.hood.isna(), "hood"] = P.loc[P.hood.isna(), "field"]
nowhere = int(P.hood.isna().sum())
print("people with no usable point placed by the dataset's field: %d; with neither: %d of %d" % (fallback, nowhere, len(P)))
unknown_h = set(P.hood.dropna()) - set(tr.hood)
check(not unknown_h, "every analysis_neighborhood value is a neighborhood in the tract map %s" % sorted(unknown_h))
check(nowhere / len(P) < 0.01, "under 1% of people hurt left unplaced")
hoods_ft = tr.to_crs(2227).dissolve(by="hood")
Pft = P[P.geometry.notna()].to_crs(2227)
for h in sorted(HL):
    edge = Pft[(Pft.hood != h) & Pft.distance(hoods_ft.loc[h, "geometry"]).le(50)]
    print("%s: %d people hurt inside, %d more within 50 ft outside (credited to %s)" % (
        h, int((P.hood == h).sum()), len(edge), dict(collections.Counter(edge.hood).most_common(3))))
H["hurt5"] = P.groupby("hood").size()
H["ksi5"] = P[P.sev.isin(["Fatal Injury", "Severe Injury"])].groupby("hood").size()
H[["hurt5", "ksi5"]] = H[["hurt5", "ksi5"]].fillna(0)
H["hurt_yr"] = H.hurt5 / 5
H["hurt_per_k"] = H.hurt_yr / H["pop"] * 1000

# ---- City Survey ------------------------------------------------------------------
csd = paths.load("city-survey-by-district.py", "csd")
srows = json.load(open(csd.RAW))
both = [r for r in srows if r["year"] == "2023" and r.get("nhood")]
names = set(H.index)
unknown = sorted({r["nhood"] for r in both} - names)
print("City Survey neighborhoods not in the analysis map (left out):", unknown, sum(1 for r in both if r["nhood"] in unknown), "respondents")
for name in names:
    sub = [r for r in both if r["nhood"] == name]
    if sub:
        s = csd.summarise(sub)
        n = sum(1 for r in sub if csd.grade(r, "muni_rate") is not None)
        H.loc[name, "muni"], H.loc[name, "muni_moe"], H.loc[name, "muni_n"] = s["muni_rate"], s["muni_rate_moe"], n
        # Unsafe at night: 1 or 2 on safe_night, the same rule as the district chart already in the doc.
        H.loc[name, "night"], H.loc[name, "night_moe"] = s["unsafe_night_pct"], s["unsafe_night_moe"]
        H.loc[name, "night_n"] = sum(1 for r in sub if csd.grade(r, "safe_night") is not None)
cs = csd.summarise([r for r in srows if r["year"] == "2023"])
muni_city = cs["muni_rate"]
night_city = cs["unsafe_night_pct"]

# ---- derived ----------------------------------------------------------------------
H["veh_hh"] = H.veh / H.hh
H["zero_car"] = H.hh0 / H.hh
H["commute_min"] = H.mins / H.nwfh
for m in ("da", "cp", "transit", "bike", "walk", "other", "wfh"):
    H["s_" + m] = H[m] / H.wk
C = dict(pop=H["pop"].sum(), veh_hh=H.veh.sum() / H.hh.sum(), zero_car=H.hh0.sum() / H.hh.sum(), hh0=H.hh0.sum(),
         commute_min=mean_cty, hurt_yr=len(P) / 5, hurt_per_k=len(P) / 5 / H["pop"].sum() * 1000,
         vmt=vmt_city, muni=muni_city, night=night_city, **{"s_" + m: H[m].sum() / H.wk.sum() for m in ("da", "cp", "transit", "bike", "walk", "other", "wfh")},
         wk=H.wk.sum(), da=H.da.sum())
cols = ["pop", "hh", "hh0", "veh", "wk", "da", "cp", "transit", "bike", "walk", "other", "wfh", "nwfh", "mins", "vmt", "veh_hh",
        "zero_car", "commute_min", "hurt5", "ksi5", "hurt_yr", "hurt_per_k", "muni", "muni_moe", "muni_n", "night", "night_moe", "night_n"] + ["s_" + m for m in ("da", "cp", "transit", "bike", "walk", "other", "wfh")]
out = H[cols].copy()
city = H[["hh", "veh", "transit", "cp", "bike", "walk", "other", "wfh", "nwfh", "mins", "ksi5"]].sum()
out.loc["San Francisco"] = pd.concat([city, pd.Series(C)])
out.loc["San Francisco", "hurt5"] = len(P)   # includes the people no neighborhood could be given
out.loc["San Francisco", "ksi5"] = int(P.sev.isin(["Fatal Injury", "Severe Injury"]).sum())
out = out.round(4).sort_index()
out.to_csv(os.path.join(OUT, "neighborhoods.csv"), index_label="neighborhood")
print("\ncitywide:", {k: round(v, 3) for k, v in C.items()})
for h in sorted(HL):
    print(h, out.loc[h, ["pop", "vmt", "s_da", "s_transit", "commute_min", "veh_hh", "zero_car", "hurt_yr", "hurt_per_k", "muni", "muni_moe", "muni_n", "night", "night_moe", "night_n"]].round(3).to_dict())

# ---- charts -----------------------------------------------------------------------
B = H[H["pop"] >= MIN_POP].copy()
print("charted neighborhoods:", len(B), "left off:", sorted(set(H.index) - set(B.index)))
J_ = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))  # compact: the board caps one insert at 20,000 characters


def fmt_int(x):
    return "{:,}".format(int(round(x)))


def ranked(key, title, xlabel, lab, city_val, city_lab, sub=None, domain=None):
    d = (sub if sub is not None else B).dropna(subset=[key]).sort_values(key, ascending=False)
    a = [{"k": h, "v": round(float(r[key]), 3), "lab": lab(h, r)} for h, r in d.iterrows()]
    order = list(d.index)
    xmax = domain or [0, float(d[key].max()) * 1.32]
    marks = [{"mark": "barX", "data": "a", "options": {"y": "k", "x": "v", "fill": BLUE}},
             {"mark": "ruleX", "data": "c", "options": {"x": "v", "stroke": GREY, "strokeDasharray": "4 3"}},
             {"mark": "text", "data": "a", "options": {"y": "k", "x": "v", "text": "lab", "dx": 5, "textAnchor": "start", "fontSize": 10.5, "fill": "#15181c"}},
             {"mark": "text", "data": "c", "options": {"x": "v", "frameAnchor": "top", "text": "t", "dy": -14, "fontSize": 11, "fill": GREY}}]
    opts = {"style": {"fontFamily": "inherit", "color": GREY}, "width": 600, "height": 16 * len(order) + 70,
            "marginLeft": 196, "marginRight": 20, "marginTop": 30, "marginBottom": 36, "fontSize": 11,
            "x": {"label": xlabel, "labelAnchor": "left", "labelArrow": False, "domain": xmax, "grid": True, "tickSize": 0},
            "y": {"label": None, "domain": order, "tickSize": 0}}
    data = {"a": a, "c": [{"v": round(city_val, 3), "t": city_lab}]}
    return '<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>' % (J_(title), J_(data), J_(marks), J_(opts))


charts = {}
charts["vmt"] = ranked("vmt", "Car Miles per Resident Range From 1.5 to 10.9 a Weekday by Neighborhood, Modeled, 2023",
                       "Vehicle miles per resident per weekday (MTC model). Dashed: citywide", lambda h, r: "%.1f" % r.vmt,
                       vmt_city, "Citywide %.1f" % vmt_city)

MODES = [("s_da", "Drive alone"), ("s_cp", "Carpool"), ("s_transit", "Transit"), ("s_walk", "Walk"), ("s_bike", "Bike"),
         ("s_other", "Taxi, motorcycle, other"), ("s_wfh", "Work from home")]
COLORS = ["#4269d0", "#97bbf5",
          "#ff725c", "#6cc5b0", "#3ca951", "#a463f2", "#9498a0"]
d = B.sort_values("s_da", ascending=False)
order = list(d.index)
segs, labs = [], []
for h, r in d.iterrows():
    x = 0.0
    for k, name in MODES:
        w = 100 * float(r[k])
        segs.append({"k": h, "m": name, "v": round(w, 1)})   # Plot stacks bars in input order
        if k in ("s_da", "s_transit", "s_wfh") and w >= 7:
            labs.append({"k": h, "c": round(x + w / 2, 1), "l": "%d" % round(w)})
        x += w
data = {"s": segs, "t": labs}
marks = [{"mark": "barX", "data": "s", "options": {"y": "k", "x": "v", "fill": "m", "stroke": "white", "strokeWidth": 0.5}},
         {"mark": "text", "data": "t", "options": {"y": "k", "x": "c", "text": "l", "fontSize": 9.5, "fill": "white", "stroke": "none"}}]
opts = {"style": {"fontFamily": "inherit", "color": GREY}, "width": 640, "height": 16 * len(order) + 90, "marginLeft": 196,
        "marginRight": 22, "marginTop": 50, "marginBottom": 36, "fontSize": 11,
        "color": {"domain": [n for _, n in MODES], "range": COLORS, "legend": True},
        "x": {"label": "Share of working residents, how they usually get to work (%)", "labelAnchor": "left", "labelArrow": False,
              "domain": [0, 100], "ticks": [0, 25, 50, 75, 100], "tickSize": 0},
        "y": {"label": None, "domain": order, "tickSize": 0}}
charts["mode"] = '<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>' % (
    J_("Between 10% and 55% of Workers Drive Alone to Work, by Neighborhood, 2020 to 2024"), J_(data), J_(marks), J_(opts))

charts["commute"] = ranked("commute_min", "Commutes Take 25 to 34 Minutes in Every Neighborhood, 2020 to 2024",
                           "Mean minutes to work, workers who don't work from home. Dashed: citywide",
                           lambda h, r: "%.0f min" % r.commute_min, mean_cty, "Citywide %.0f min" % mean_cty, domain=[0, 48])
charts["cars"] = ranked("veh_hh", "Households Average 0.29 to 1.74 Cars, by Neighborhood, 2020 to 2024",
                        "Vehicles per household. Dashed: citywide", lambda h, r: "%.2f, %d%% none" % (r.veh_hh, round(100 * r.zero_car)),
                        C["veh_hh"], "Citywide %.2f, %d%% none" % (C["veh_hh"], round(100 * C["zero_car"])), domain=[0, 2.4])
charts["hurt"] = ranked("hurt_per_k", "People Hurt in Traffic Range From 0.5 to 12.5 a Year per 1,000 Residents, by Neighborhood, 2021 to 2025",
                        "People hurt a year per 1,000 residents. Dashed: citywide",
                        lambda h, r: "%s a year, %.1f" % (fmt_int(r.hurt_yr), r.hurt_per_k), C["hurt_per_k"],
                        "Citywide %.1f" % C["hurt_per_k"])
S = B[B.muni_n >= 30].copy().sort_values("muni", ascending=False)
pt = lambda h, r: {"k": h, "v": round(float(r.muni), 3), "lo": round(float(r.muni - r.muni_moe), 3), "hi": round(float(r.muni + r.muni_moe), 3),
                   "lab": "%.2f (%d)" % (r.muni, r.muni_n)}
data = {"a": [pt(h, r) for h, r in S.iterrows()],
        "c": [{"v": round(muni_city, 3), "t": "Citywide %.2f" % muni_city}]}
marks = []
for key, col in (("a", BLUE),):
    marks += [{"mark": "ruleY", "data": key, "options": {"y": "k", "x1": "lo", "x2": "hi", "stroke": col, "strokeOpacity": 0.4, "strokeWidth": 5}},
              {"mark": "dot", "data": key, "options": {"y": "k", "x": "v", "r": 4, "fill": col}},
              {"mark": "text", "data": key, "options": {"y": "k", "x": "hi", "text": "lab", "dx": 5, "textAnchor": "start", "fontSize": 10.5,
                                                         "fill": "#15181c"}}]
marks += [{"mark": "ruleX", "data": "c", "options": {"x": "v", "stroke": GREY, "strokeDasharray": "4 3"}},
          {"mark": "text", "data": "c", "options": {"x": "v", "frameAnchor": "top", "text": "t", "dy": -14, "fontSize": 11, "fill": GREY}}]
opts = {"style": {"fontFamily": "inherit", "color": GREY}, "width": 600, "height": 16 * len(S) + 70, "marginLeft": 196, "marginRight": 20,
        "marginTop": 30, "marginBottom": 36, "fontSize": 11,
        "x": {"label": "Average grade, F = 1 to A = 5; bar shows 95% margin; (respondents). Dashed: citywide", "labelAnchor": "left",
              "labelArrow": False, "domain": [2.4, 4.4], "grid": True, "tickSize": 0},
        "y": {"label": None, "domain": list(S.index), "tickSize": 0}}
mc = '<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>' % (
    J_("Residents Grade Muni About the Same in Nearly Every Neighborhood, 2023"), J_(data), J_(marks), J_(opts))
charts["muni"] = mc
print("survey neighborhoods charted (30+ grading Muni):", len(S), "left off:", sorted(set(B.index) - set(S.index)))

N = B[B.night_n >= 30].copy()
charts["night"] = ranked("night", "Between 12% and 64% Feel Unsafe Walking Alone at Night, by Neighborhood, 2023",
                         "Share rating night safety 1 or 2 out of 5 (respondents). Dashed: citywide",
                         lambda h, r: "%d%% (%d)" % (round(r.night), r.night_n), night_city, "Citywide %d%%" % round(night_city),
                         sub=N, domain=[0, 75])
print("night chart neighborhoods (30+ answers):", len(N), "citywide %.1f" % night_city)
with open(os.path.join(OUT, "charts.mdx"), "w") as f:
    for k, c in charts.items():
        f.write("{/* chart: %s */}\n%s\n\n" % (k, c))
print("wrote", os.path.join(OUT, "neighborhoods.csv"), "and charts.mdx")
