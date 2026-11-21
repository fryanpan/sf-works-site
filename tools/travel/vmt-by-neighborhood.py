#!/usr/bin/env python3
"""Vehicle miles per resident by San Francisco neighborhood: two model series (SF-CHAMP 2012, MTC 2023) with Census car ownership, commute mode and LODES job distance.

Run with ~/.venvs/sf-works-geo/bin/python scripts/vmt-by-neighborhood.py. Every input is
fetched once into the folder VMT_CACHE names (default sf-works-scratch/vmt/neighborhood-cache) and read from there afterwards. Writes
out.json in that folder and prints the checks. A one-off analysis for
research/mobility-plan-2026-11/2026-11-06-vmt-and-mode-share.mdx, not a pipeline step.

Weights. Each model zone is cut by 2020 census tracts. A piece's population is the tract's
ACS 2020-24 population times the piece's share of the tract's land. A zone's VMT rate is
applied to its pieces, then pieces are summed to analysis neighborhoods, so a zone that
spans two neighborhoods is split. Zones a model marks as holding no residents (rate 0 in
SF-CHAMP) drop out and the tract's population is spread over its other pieces.
"""
import json, os, sys, urllib.request, zipfile, math, csv
import numpy as np, pandas as pd, geopandas as gpd

C = os.environ.get("VMT_CACHE", os.path.expanduser("~/sf-works-scratch/vmt/neighborhood-cache"))
os.makedirs(C, exist_ok=True)

def get(url, name):
    p = os.path.join(C, name)
    if not os.path.exists(p):
        urllib.request.urlretrieve(url, p)
    return p

mtc = gpd.read_file(get("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/mtc_vmt_home_work_pba2050p/FeatureServer/0/query?where=county%3D%27San+Francisco%27&outFields=*&returnGeometry=true&outSR=4326&f=geojson", "mtc_sf.geojson"))
z = get("https://sfplanninggis.s3.amazonaws.com/VehiclesMilesTravelled.zip", "champ.zip")
gdb = os.path.join(C, "VehiclesMilesTravelled.gdb")
if not os.path.exists(gdb):
    zipfile.ZipFile(z).extractall(C)
champ = gpd.read_file(gdb, layer="VMT_TAZ_RESIDENTIAL")
tracts_p = os.path.join(C, "tracts.geojson")
if not os.path.exists(tracts_p):
    urllib.request.urlretrieve("https://data.sf.gov/resource/sevw-6tgi.geojson?$limit=400", tracts_p)
tr = gpd.read_file(tracts_p)[["geoid", "neighborhoods_analysis_boundaries", "sup_dist_2022", "geometry"]]
tr = tr.rename(columns={"neighborhoods_analysis_boundaries": "hood"})
cr = json.load(open(get("https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B01003,B25044,B08301&geo_ids=140|05000US06075", "cr.json")))

rows = []
for g, t in cr["data"].items():
    e = lambda tb, k: t[tb]["estimate"].get(k) or 0
    hh = e("B25044", "B25044001")
    veh = sum(n * (e("B25044", f"B25044{o+n:03d}") + e("B25044", f"B25044{r+n:03d}")) for n in range(1, 6) for o, r in [(3, 10)])
    rows.append(dict(geoid=g[-11:], pop=e("B01003", "B01003001"), hh=hh, veh=veh,
        hh0=e("B25044", "B25044003") + e("B25044", "B25044010"),
        wk=e("B08301", "B08301001"), car=e("B08301", "B08301002"), da=e("B08301", "B08301003"),
        cp=e("B08301", "B08301004"), wfh=e("B08301", "B08301021"), transit=e("B08301", "B08301010")))
acs = pd.DataFrame(rows)
print("ACS tracts", len(acs), "pop", acs["pop"].sum(), "hh", acs.hh.sum(), "veh", acs.veh.sum(), "zero-car", round(acs.hh0.sum() / acs.hh.sum(), 4))
miss = set(tr.geoid) ^ set(acs.geoid)
print("tract ids unmatched either way:", len(miss), sorted(miss)[:6])
tr = tr.merge(acs, on="geoid", how="left")
print("tracts in map", len(tr), "null pop", tr["pop"].isna().sum())

# LODES: mean straight-line miles from home tract to job, and share of jobs outside SF.
cent = tr.to_crs(2227).geometry.representative_point()
tr_xy = dict(zip(tr.geoid, zip(cent.x, cent.y)))
od = pd.concat([pd.read_csv(f"{C}/lodes_main.csv", dtype=str), pd.read_csv(f"{C}/lodes_aux.csv", dtype=str)])
od["jobs"] = od.jobs.astype(int)
print("LODES rows", len(od), "jobs", od.jobs.sum(), "work in SF", od[od.w_tract.str.startswith("06075")].jobs.sum(), "live in SF", od[od.h_tract.str.startswith("06075")].jobs.sum())
cb_p = os.path.join(C, "ca_tract_centroids.csv")
home = od[od.h_tract.str.startswith("06075")].copy()
print("SF residents' jobs in SF", home[home.w_tract.str.startswith("06075")].jobs.sum())
od.groupby(od.h_tract.str[:5]).jobs.sum().sort_values(ascending=False).head(12).to_csv(os.path.join(C, "in_commute_home_county.csv"))
xy = np.array([tr_xy.get(t, (np.nan, np.nan)) for t in home.h_tract])
home["hx"], home["hy"] = xy[:, 0], xy[:, 1]
print("home tracts missing from map:", int(home.hx.isna().sum()), "rows,", home[home.hx.isna()].jobs.sum(), "jobs")

# Job location: tract centroid in SF; for other counties, the Gazetteer county point is too coarse,
# so read Census 2020 tract internal points once.
gaz = get("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_tracts_06.txt", "gaz06.txt")
gz = pd.read_csv(gaz, sep="\t", dtype={"GEOID": str})
gz.columns = [c.strip() for c in gz.columns]
gz["GEOID"] = gz.GEOID.str.zfill(11)
la, lo = gz.set_index("GEOID").INTPTLAT.to_dict(), gz.set_index("GEOID").INTPTLONG.to_dict()
home["wlat"], home["wlon"] = home.w_tract.map(la), home.w_tract.map(lo)
home["hlat"], home["hlon"] = home.h_tract.map(la), home.h_tract.map(lo)
print("jobs with no work point:", home[home.wlat.isna()].jobs.sum(), "of", home.jobs.sum())
R = 3958.8
a = np.radians(home.wlat); b = np.radians(home.hlat)
d = 2 * R * np.arcsin(np.sqrt(np.sin((a - b) / 2) ** 2 + np.cos(a) * np.cos(b) * np.sin(np.radians(home.wlon - home.hlon) / 2) ** 2))
home["mi"] = d
h2 = home.dropna(subset=["mi"])
# Out-of-state rows (aux) are capped out of the mean: a job at a Seattle head office is not a commute.
near = h2[h2.mi <= 75]
g = near.groupby("h_tract")
tj = pd.DataFrame({"jobs": g.jobs.sum(), "jm": g.apply(lambda x: (x.jobs * x.mi).sum(), include_groups=False)})
out = h2.groupby("h_tract").apply(lambda x: x[~x.w_tract.str.startswith("06075")].jobs.sum(), include_groups=False).rename("jobs_out")
allj = h2.groupby("h_tract").jobs.sum().rename("jobs_all")
tr = tr.merge(tj, left_on="geoid", right_index=True, how="left").merge(out, left_on="geoid", right_index=True, how="left").merge(allj, left_on="geoid", right_index=True, how="left")
print("citywide mean job miles, straight line, under 75 mi:", round(tj.jm.sum() / tj.jobs.sum(), 2), " share of jobs outside SF:", round(out.sum() / allj.sum(), 4), " jobs over 75 mi:", h2[h2.mi > 75].jobs.sum())

# Zone weights.
t = tr.to_crs(2227)
t["t_area"] = t.area
def weigh(zones, rate):
    zz = zones[[rate, "geometry"]].to_crs(2227)
    zz = zz[zz[rate].notna() & (zz[rate] > 0)]
    p = gpd.overlay(t[["geoid", "hood", "pop", "t_area", "geometry"]], zz, how="intersection", keep_geom_type=True)
    p["a"] = p.area
    p["w"] = p["a"] / p.groupby("geoid")["a"].transform("sum")
    p["ppop"] = p["pop"] * p["w"]
    return p
pc = weigh(champ, "TAZVMT_perCap"); pm = weigh(mtc, "home_vmt_2023by")
print("pop in CHAMP pieces", round(pc.ppop.sum()), "MTC pieces", round(pm.ppop.sum()), "of", acs["pop"].sum())
wm = lambda d, r: (d[r] * d.ppop).sum() / d.ppop.sum()
print("citywide, ACS tract weights: CHAMP 2012", round(wm(pc, "TAZVMT_perCap"), 2), "MTC 2023", round(wm(pm, "home_vmt_2023by"), 2))
print("MTC, own zone population:", round((mtc.home_totpop_2023by * mtc.home_vmt_2023by).sum() / mtc.home_totpop_2023by.sum(), 3))
def wq(d, r, q):
    s = d.sort_values(r); c = s.ppop.cumsum() / s.ppop.sum()
    return float(s[r].iloc[int(np.searchsorted(c, q))])
for nm, d, r in (("CHAMP", pc, "TAZVMT_perCap"), ("MTC", pm, "home_vmt_2023by")):
    print(nm, "person-weighted p10,p50,p90", [round(wq(d, r, q), 2) for q in (.1, .5, .9)], "zones", d[r].min().round(2), d[r].max().round(2))

hc = pc.groupby("hood").apply(lambda x: (x.TAZVMT_perCap * x.ppop).sum() / x.ppop.sum(), include_groups=False).rename("champ")
hm = pm.groupby("hood").apply(lambda x: (x.home_vmt_2023by * x.ppop).sum() / x.ppop.sum(), include_groups=False).rename("mtc")
ag = tr.groupby("hood").agg(pop=("pop", "sum"), hh=("hh", "sum"), veh=("veh", "sum"), hh0=("hh0", "sum"), wk=("wk", "sum"), car=("car", "sum"), wfh=("wfh", "sum"), transit=("transit", "sum"), jobs=("jobs", "sum"), jm=("jm", "sum"), jobs_out=("jobs_out", "sum"), jobs_all=("jobs_all", "sum"))
df = ag.join(hc).join(hm)
df["veh_hh"] = df.veh / df.hh; df["zero_car"] = df.hh0 / df.hh
df["car_commute"] = df.car / (df.wk - df.wfh); df["job_mi"] = df.jm / df.jobs; df["job_out"] = df.jobs_out / df.jobs_all
df["mi_day_mtc"] = df.mtc * df["pop"]; df["share_mtc"] = df.mi_day_mtc / df.mi_day_mtc.sum()
df["pop_share"] = df["pop"] / df["pop"].sum()
df = df.sort_values("mtc", ascending=False)
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 60)
print(df[["pop", "mtc", "champ", "veh_hh", "zero_car", "car_commute", "job_mi", "job_out", "share_mtc"]].round(3).to_string())
b = df[df["pop"] >= 3000]
print("neighborhoods with 3000+ residents:", len(b), "of", len(df))
print("corr with mtc:", b[["champ", "veh_hh", "zero_car", "car_commute", "job_mi", "job_out"]].corrwith(b.mtc).round(3).to_dict())
print("corr with champ:", b[["mtc", "veh_hh", "zero_car", "car_commute", "job_mi", "job_out"]].corrwith(b.champ).round(3).to_dict())
tot = df.mi_day_mtc.sum()
top = df.sort_values("mi_day_mtc", ascending=False)
print("resident weekday VMT, MTC x ACS pop:", round(tot), "top 10 hoods share", round(top.mi_day_mtc.head(10).sum() / tot, 3), "their pop share", round(top["pop"].head(10).sum() / df["pop"].sum(), 3))
print(top[["pop", "mtc", "mi_day_mtc", "share_mtc", "pop_share"]].head(10).round(3).to_string())
hi = df[df.mtc >= 9]; lo = df[df.mtc < 5]
print(">=9:", len(hi), round(hi["pop"].sum()), round(hi.mi_day_mtc.sum() / tot, 3), " <5:", len(lo), round(lo["pop"].sum()), round(lo.mi_day_mtc.sum() / tot, 3))
# Car-household view: the same miles over households with a car.
sf_veh_hh = df.veh.sum() / df.hh.sum()
print("citywide vehicles per household", round(sf_veh_hh, 3), "vehicles per person", round(df.veh.sum() / df["pop"].sum(), 3))
df.reset_index().to_json(os.path.join(C, "out.json"), orient="records", indent=0)
