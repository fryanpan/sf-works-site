#!/usr/bin/env python3
"""Through traffic on every San Francisco street block the SF-CHAMP network carries: the share of car trips on the block whose trip neither starts nor ends within half a mile of the block (and at a quarter, three quarters and one mile for the map's slider), from MTC Travel Model 1.6's 2023 trip table (every purpose) routed on SF-CHAMP's network for each time of day, averaged over jittered routing runs, with a low-confidence flag where the runs disagree.

    ~/.venvs/sf-works-geo/bin/python tools/street-safety/through-traffic.py prep     # laptop: network, zones and trips -> routing.npz
    python3 tools/street-safety/through-traffic.py route --npz F --out F --workers 15  # VM (numpy and scipy only): every origin, bin, run
    ~/.venvs/sf-works-geo/bin/python tools/street-safety/through-traffic.py blocks   # laptop: links.json -> street blocks
    ~/.venvs/sf-works-geo/bin/python tools/street-safety/through-traffic.py near     # laptop: only the near sets (every distance), into an existing routing.npz
    scripts/through-traffic-vm.sh                                        # prep, route on the cloud VM, blocks
    TT_PREP=near scripts/through-traffic-vm.sh                           # the same without rereading the MTC trip table

Bryan, 2026-11-19: "can we add a layer that shows fraction of each street segment
is carrying through traffic as a percentage? I just want to show all of the streets where we are sending motorists
mixed messages." Then: "we want also however the main streets to stand out, like why does every single street downtown
need to carry through traffic?" And: "I was assuming you would use the champ model to understand distribution of trips
going from one place to another." SFCTA publishes SF-CHAMP's network and loaded volumes but not its trip table, so the
trips are MTC's (research/sources/mtc-travel-model-1-6-trip-tables.md). Prior work:
research/notes/low-traffic-cells-2026-11/2026-11-19-network-flows-prior-work.md (select-link is the standard method).

DEFINITION
  Through car on a block: a car whose trip neither starts nor ends within half a mile of the block. Bryan, 2026-11-20
  (docs/decisions/street-safety.md): "Default to half mile", with a slider over a quarter, half, three quarters and one
  mile. That replaced one mile (2026-11-19), which replaced "neither end in the block's Analysis
  Neighborhood", which read near 0% on most of Bayview's blocks, Third Street included, because a big neighborhood
  holds most trips that use its main streets.
  Measured as: a trip end is the representative point of its SF-CHAMP zone (in SF a zone is a few blocks across; MTC's
  zones are split over them, see trips), and the block is the SF-CHAMP link the block takes (median 321 ft, 90th
  percentile 680 ft long), so the distance is from the point to the link's drawn line in UTM 10N, at most each of
  NEARS. Both directions of a street take one line's answer. Zones outside SF are measured the same way, so the San
  Mateo zones whose point lies within the distance of an SF street count as near those streets and no others; every
  other outside zone is never near. A block matched to several links (a divided road) takes each link's own answer.

METHOD (scripts/network-flows-prototype.py's routing, citywide)
  network   SF-CHAMP hwynet_links and hwynet_weekday from api.sfcta.org (sources/sfcta-champ-hwynet.md): an undated run
            of mid-2019 or earlier. Bike paths (ft 13) and the Upper Great Highway, Lincoln to Sloat (closed to cars by
            Proposition K) are left out. Centroids may start or end a path, never sit inside one. HOV links are open to
            every car.
  trips     MTC Travel Model 1.6, run 2023_TM161_IPA_35: every simulated person trip and joint trip by car (drive
            alone, shared ride, taxi, TNC), as cars (shared ride 2 a half, 3+ 1/3.25, a joint trip one), times
            1/sampleRate. Drive-to-transit trips are left out. Pairs that may cross SF only: an end in SF, or North Bay
            or East Bay to the Peninsula. Outside SF an MTC zone is one SF-CHAMP zone (the systems share zones there);
            in SF each MTC zone is split over the SF-CHAMP zones inside it by their LODES 2024 homes plus jobs.
  periods   MTC's departure hour, binned to the map's time-of-day filter (BINS), each bin routed on the nearest
            SF-CHAMP period's congested times. A block's day is the sum of its bins.
  routing   All-or-nothing fastest path from every origin TAZ (scipy Dijkstra). Pairs over 90 minutes' drive
            are left out. Each link's flow is the demand under it in the origin's
            shortest-path tree. Local = all of it when the origin is within the distance of the link, else the demand to
            destinations within the distance of the link whose path uses it (a destination is under the link's head in the
            tree, tested by preorder number); through = flow - local.
  runs      The base run plus len(SEEDS) runs with every link's time multiplied by its own seeded random factor in
            JITTER. The published share and volume average all the runs, a crude split of each pair over near-equal
            routes (the prior-work note's "route split"). A block is low confidence when the runs split in two halves
            (alternate runs), each averaged, put it in different classes, or when its routed car trips exceed
            SF-CHAMP's all-purpose daily volume on the same links.
  closed    Links closed to private cars since the model's run: the Upper Great Highway (CLOSED), Market Street east of
            Van Ness and JFK Drive in Golden Gate Park (CAR_FREE, by name and longitude).
  hood      A link's neighborhood is the one holding its node pair's centreline midpoint, so both directions agree.
            It names the block's neighborhood for the map's area filter and no longer enters the share.
  blocks    A street block (DataSF 3psu-pn9h, the Street Safety map's traffic rows in
            data/extract/residential-traffic/blocks.json, residential and main) takes every same-named parallel SF-CHAMP
            link beside it on a main street (hin-cut-through.py modelled_main(): 60 ft, or 150 ft projecting inside
            the link, 20 degrees, then beside(): only the links the block's midpoint projects inside, never the next
            one along the street), the one link within 60 ft on a residential street (modelled()), both directions
            summed. Most residential blocks are not on the model's network and get no figure.

OUTPUTS
  data/extract/through-traffic/links.json    per directed SF link a_b: [cars, through cars] for the base run and each
                                             jitter run, with the link's neighborhood index
  data/extract/through-traffic/blocks.json   per block cnn: share, volume, low-confidence flag; class counts by road

Checks (stop on failure): 62,689 links, 377,274 link-period rows, 2,245 TAZs, every SF TAZ in one neighborhood, every
routable SF zone within a mile of an SF street, zones outside SF near one only in San Mateo, Alameda or Marin,
1,454 MTC zones, every SF MTC zone split, every departure hour in a bin, under 1% of car trips unplaced, >= 5,000 SF links
with flow, a link's through never above its flow, >= 3,000 blocks with a figure, every block's share in 0..1, every traffic
block with a centerline, every block's bins adding to its day, and no block over 10,000 cars a day under 1% through
within half a mile of a block over 50% (the old neighborhood rule's failure). The route stage's second run on the VM must match the first byte for byte (through-traffic-vm.sh).

One trip table, no update: MTC's 2023 run and SF-CHAMP's network are both fixed, so the pipeline step is MANUAL.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
SCR = ROOT / "scratch"
if not (SCR / "runs/trip-flows").exists():
    # A worktree reads the main checkout's scratch; on the VM (no repo) route takes every path as an argument.
    _git = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    if _git.returncode == 0:
        SCR = Path(_git.stdout.strip()).parent / "scratch"
RUNS = SCR / "runs/through-traffic"
PROTO = SCR / "runs/network-flows-2026-11-19"   # the prototype's cached SF-CHAMP tables, same queries
LODES = SCR / "runs/trip-flows/raw"
MTC = RUNS / "mtc-2023"   # MTC Travel Model 1.6, 2023 run 2023_TM161_IPA_35 (Box, PBA50plus-travelModelData)
NHOODS = ROOT / "data/extract/neighborhoods/analysis-neighborhoods.geojson"
BLOCKS_IN = ROOT / "data/extract/residential-traffic/blocks.json"
OUT = ROOT / "data/extract/through-traffic"
API = "https://api.sfcta.org/api/"

BAY = {"06001": "East Bay", "06013": "East Bay", "06041": "North Bay", "06055": "North Bay", "06075": "San Francisco",
       "06081": "Peninsula and South Bay", "06085": "Peninsula and South Bay", "06095": "North Bay", "06097": "North Bay"}
CAR = {"San Francisco": 92581 / 239753, "East Bay": 52813 / 113499, "Peninsula and South Bay": 50987 / 71238,
       "North Bay": 22308 / 30151}
MAXC = 2454
CAP_MIN = 90
CLOSED = {(27942, 32904), (32904, 27942)}
# Streets closed to private cars after the network's run, by name and longitude span [model knowledge -- verify]:
# Market Street, 10th Street / Van Ness to Steuart (Better Market Street, car-free from January 2020), and JFK Drive
# in Golden Gate Park, Kezar Drive to Transverse Drive (JFK Promenade, 2022).
CAR_FREE = [("MARKET", -122.4192, -122.3940), ("JOHN F KENNEDY", -122.4770, -122.4545), ("JFK", -122.4770, -122.4545)]
# Each run multiplies every link's time by its own random factor in this range. The published share is the sum of
# through cars over the sum of cars across all runs, a crude split of each pair over near-equal routes; one fastest
# path alone piles a corridor's traffic onto whichever street wins by seconds.
JITTER = (0.75, 1.25)
SEEDS = tuple(range(1, 11))
# The map's time-of-day filter (site/src/pages/transportation-street-safety.mjs TIMES), as MTC departure hours (5 is
# 5 to 6 am; the trip table has no hour before 5), each routed on the nearest SF-CHAMP period's congested times.
BINS = [("am", "AM", range(6, 9)), ("midday", "MD", range(9, 15)), ("pm", "PM", range(15, 19)),
        ("evening", "EV", range(19, 22)), ("night", "EA", (22, 23, 5))]

# Through-share classes for the map: under a quarter, a quarter to half, half to three quarters, three quarters and up.
CLASSES = [0.25, 0.5, 0.75]
MIN_CARS = 100   # a block with fewer routed car trips a day than this gets no class: too few trips to share out
MIN_BIN = 25     # the same floor for one hour bin
# Bryan (docs/decisions/street-safety.md): a car is through a block when neither end of its trip is within a distance of
# the block, chosen on a slider, over a quarter, half, three quarters and one mile (2026-11-20),
# opening on half a mile ("Default to half mile", 2026-11-20). Every distance is routed in the same run. NEARS runs
# shortest first and NEAR_M is the longest, the one the near sets are found in; a block's top-level figures are
# DEFAULT_NEAR's.
NEARS = [("quarter", 402.336), ("half", 804.672), ("3q", 1207.008), ("mile", 1609.344)]
NEAR_M = NEARS[-1][1]
DEFAULT_NEAR = "half"
# Third Street, Ingerson to Jamestown, at midday read 93.3%, 66.6%, 52.1% and 42.5% through on 2026-11-20; each floor
# sits about 13 points under its figure, so a real change trips it and rounding does not.
THIRD_FLOOR = {"quarter": 0.8, "half": 0.55, "3q": 0.4, "mile": 0.3}
SAN_MATEO_NEAR = {"quarter": 2, "half": 5, "3q": 7, "mile": 9}
BUSY = 10_000    # cars a day on a block for the busy-block guard in blocks()
GUARD_FT = 2640  # and the half mile it looks for a mostly-through block in


def fetch(table, select, order, cache, page=50000):
    """A cached api.sfcta.org table: the prototype's copy when there is one, else a fresh paged read."""
    for p in (RUNS / cache, PROTO / cache):
        if p.exists():
            return json.loads(p.read_text())
    import urllib.request
    rows, off = [], 0
    while True:
        req = urllib.request.Request(f"{API}{table}?select={select}&order={order}&limit={page}&offset={off}", headers={"User-Agent": "curl/8"})
        chunk = json.load(urllib.request.urlopen(req, timeout=300))
        rows += chunk
        if len(chunk) < page:
            break
        off += page
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / cache).write_text(json.dumps(rows))
    return rows


def check(ok, msg):
    if not ok:
        sys.exit("CHECK FAILED: " + msg)
    print("ok  " + msg, file=sys.stderr)


# ---------------------------------------------------------------------------------------------------------- near
def near_sets(links, tazr, link_hood, routable):
    """The SF links within each distance of NEARS of each SF-CHAMP zone's representative point, as {name: (ptr, idx)},
    CSR over zone id (ptr has MAXC + 2 entries; zone t's links are idx[ptr[t]:ptr[t + 1]], sorted link indices). Distances are
    measured in UTM 10N metres from the point to the street link's line; both directions of a street take the answer
    for one drawn line (the lower node id's direction first), so they agree. Zones outside SF are measured the same way,
    so a Daly City or Brisbane zone near the county line is near the SF blocks it really is near, and no others."""
    import geopandas as gpd
    import shapely
    from shapely.geometry import shape
    sfi = [int(i) for i in np.nonzero(link_hood >= 0)[0]]
    rep_of, members = {}, collections.defaultdict(list)
    drawn = {i: shape(json.loads(links[i]["geometry"])) for i in sfi}
    # A direction drawn with no line (five in SF) takes the other direction's.
    for i in sorted(sfi, key=lambda i: (drawn[i].is_empty, links[i]["a"] > links[i]["b"], i)):
        k = (min(links[i]["a"], links[i]["b"]), max(links[i]["a"], links[i]["b"]))
        rep_of.setdefault(k, i)
        members[k].append(i)
    keys = sorted(rep_of)
    geo = gpd.GeoSeries([drawn[rep_of[k]] for k in keys], crs=4326).to_crs(26910)
    check(not geo.is_empty.any(), f"every SF street link has a drawn line ({int(geo.is_empty.sum())} empty)")
    ft = geo.length.values / 0.3048
    print(f"SF street link length, feet: median {np.median(ft):,.0f}, 90th percentile {np.percentile(ft, 90):,.0f}, "
          f"99th {np.percentile(ft, 99):,.0f}, longest {ft.max():,.0f}", file=sys.stderr)
    tz = sorted(tazr, key=lambda t: t["taz"])
    pts = gpd.GeoSeries([shape(json.loads(t["geometry"])).representative_point() for t in tz], crs=4326).to_crs(26910)
    zi, gi = shapely.STRtree(geo.values).query(pts.values, predicate="dwithin", distance=NEAR_M)
    dist = shapely.distance(pts.values[zi], geo.values[gi])
    sets = {}
    for name, metres in NEARS:
        near = collections.defaultdict(set)
        for z, g, dd in zip(zi, gi, dist):
            if dd <= metres:
                near[int(tz[z]["taz"])].update(members[keys[g]])
        sf_z = [int(t["taz"]) for t in tz if t["county"] == 1 and int(t["taz"]) in routable]
        sizes = [len(near[t]) for t in sf_z]
        print(f"{name}: SF zones' directed SF links within {metres:,.0f} m, median {np.median(sizes):,.0f}, max {max(sizes):,}; "
              f"SF zones with none {sum(1 for t in sf_z if not near[t])}", file=sys.stderr)
        outside = collections.Counter(t["county"] for t in tz if t["county"] != 1 and near[int(t["taz"])])
        print(f"{name}: zones outside SF near an SF street, by SF-CHAMP county code: {dict(sorted(outside.items()))}", file=sys.stderr)
        check(set(outside) <= {2, 4, 9}, f"{name}: zones outside SF near an SF street are only in San Mateo, Alameda (Bay Bridge) or Marin (Golden Gate)")
        # The San Mateo zones on the county line that count as near, exactly, so a change in the zones or the distance
        # shows. At a quarter mile one of the two, zone 1206, is near by only 35 ft.
        check(outside[2] == SAN_MATEO_NEAR[name], f"{name}: {outside[2]} San Mateo zones near an SF street, expected {SAN_MATEO_NEAR[name]}")
        if name == "mile":
            # Four SF zones have no centroid on the network and no street within a mile (the Farallones, Alcatraz, two
            # on the water); no trip starts or ends there.
            check(all(near[t] for t in sf_z), f"every routable SF zone has an SF street within one mile ({sum(1 for t in sf_z if near[t])} of {len(sf_z)})")
        else:
            # A zone with no street within the shorter distance is fine (a zone on the water's edge): its trips are
            # local nowhere at that distance, which is what the distance says.
            check(sum(1 for t in sf_z if near[t]) >= 0.95 * len(sf_z), f"{name}: at least 95% of routable SF zones have an SF street within {metres:,.0f} m")
        ptr = np.zeros(MAXC + 2, dtype=np.int64)
        idx = []
        for t in range(MAXC + 1):
            idx += sorted(near.get(t, ()))
            ptr[t + 1] = len(idx)
        sets[name] = (ptr, np.array(idx, dtype=np.int32))
    # A shorter distance's set sits inside a longer one's for every zone.
    for (n0, _), (n1, _) in zip(NEARS, NEARS[1:]):
        p0, i0 = sets[n0]; p1, i1 = sets[n1]
        check(all(set(i0[p0[t]:p0[t + 1]]) <= set(i1[p1[t]:p1[t + 1]]) for t in range(MAXC + 1)), f"every zone's {n0} set is inside its {n1} set")
    return sets


def near_arrays(sets):
    """The near sets as routing.npz arrays: near_ptr_<name> and near_idx_<name> for each of NEARS."""
    out = {}
    for name, (ptr, idx) in sets.items():
        out[f"near_ptr_{name}"], out[f"near_idx_{name}"] = ptr, idx
    return out


def add_near(a):
    """Write the near sets into an existing routing.npz without rereading the MTC trip table (prep's slow, memory-heavy
    part). The npz's link order must be hwynet_links' order, which the check below confirms."""
    links = fetch("hwynet_links", "a,b,ft,streetname,geometry", "a,b", "links.json")
    tazr = fetch("taz_boundaries", "taz,county,nhood,geometry", "taz", "taz.json")
    Z = dict(np.load(a.npz))
    check(len(links) == len(Z["link_a"]) and all(l["a"] == x and l["b"] == y for l, x, y in zip(links, Z["link_a"], Z["link_b"])),
          "routing.npz's links are hwynet_links in order")
    for k in ("near_ptr", "near_idx"):
        Z.pop(k, None)   # the single-mile sets from before the distance slider
    Z.update(near_arrays(near_sets(links, tazr, Z["link_hood"], set(int(c) for c in Z["cent"][:, 0]))))
    np.savez_compressed(a.npz, **Z)
    print(f"wrote near sets into {a.npz}: " + ", ".join(f"{n} {len(Z['near_idx_' + n]):,}" for n, _ in NEARS) + " zone-link pairs", file=sys.stderr)


# ---------------------------------------------------------------------------------------------------------- prep
def prep(a):
    import csv
    import gzip
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import shape, Point, LineString

    links = fetch("hwynet_links", "a,b,ft,streetname,geometry", "a,b", "links.json")
    perf = fetch("hwynet_weekday", "a,b,time_period,time_1,v_1", "a,b,time_period", "weekday.json")
    tazr = fetch("taz_boundaries", "taz,county,nhood,geometry", "taz", "taz.json")
    check(len(links) == 62689, f"hwynet_links rows == 62,689 ({len(links):,})")
    check(len(perf) == 377274, f"hwynet_weekday rows == 377,274 ({len(perf):,})")
    check(len(tazr) == 2245, f"taz_boundaries rows == 2,245 ({len(tazr):,})")
    check(len({(r["a"], r["b"]) for r in links}) == len(links), "link keys unique")

    H = json.loads(NHOODS.read_text())["features"]
    H = sorted(H, key=lambda f: f["properties"]["nhood"])
    check(len(H) == 41, f"41 analysis neighborhoods ({len(H)})")
    hoods = gpd.GeoDataFrame({"h": range(41), "name": [f["properties"]["nhood"] for f in H]},
                             geometry=[shape(f["geometry"]) for f in H], crs=4326)

    # TAZ -> neighborhood: an SF zone's representative point; zones outside SF are -1 (outside every neighborhood).
    taz = gpd.GeoDataFrame([{"taz": t["taz"], "county": t["county"], "geometry": shape(json.loads(t["geometry"]))} for t in tazr], crs=4326)
    sf = taz[taz.county == 1].copy()
    sf["geometry"] = sf.geometry.representative_point()
    j = gpd.sjoin(sf, hoods[["h", "geometry"]], predicate="within", how="left")
    # A representative point that lands in no neighborhood (a zone on the water's edge): the nearest one.
    miss = j[j.h.isna()]
    if len(miss):
        near = gpd.sjoin_nearest(sf[sf.taz.isin(miss.taz)].to_crs(26910), hoods.to_crs(26910)[["h", "geometry"]], how="left")
        j = pd.concat([j[~j.h.isna()], near[["taz", "h"]]])
    taz_hood = {int(t): int(h) for t, h in zip(j.taz, j.h)}
    check(len(taz_hood) == len(sf), f"every SF TAZ in one neighborhood ({len(taz_hood)} of {len(sf)}, {len(miss)} by nearest)")

    # Nodes and links, as the prototype builds them.
    lk = pd.DataFrame([{"a": l["a"], "b": l["b"], "ft": l["ft"], "name": (l.get("streetname") or "").upper(),
                        "geom": json.loads(l["geometry"])} for l in links])
    geoms = [shape(g) for g in lk.geom]
    # A link's neighborhood: the one holding the midpoint of its node pair's centreline. Each direction is drawn offset a
    # few feet, so the two directions' midpoints are averaged first and both directions of a street share one
    # neighborhood; otherwise a boundary street's block would mix two neighborhoods' definitions.
    mx = np.array([g.interpolate(0.5, normalized=True).x if not g.is_empty else np.nan for g in geoms])
    my = np.array([g.interpolate(0.5, normalized=True).y if not g.is_empty else np.nan for g in geoms])
    key = [(min(x, y), max(x, y)) for x, y in zip(lk.a, lk.b)]
    acc = collections.defaultdict(list)
    for k, x, y in zip(key, mx, my):
        if x == x:
            acc[k].append((x, y))
    cen = {k: (float(np.mean([p[0] for p in v])), float(np.mean([p[1] for p in v]))) for k, v in acc.items()}
    mids = gpd.GeoDataFrame(geometry=[Point(*cen[k]) if k in cen else Point(0, 0) for k in key], crs=4326)
    mj = gpd.sjoin(mids, hoods[["h", "geometry"]], predicate="within", how="left")
    mj = mj[~mj.index.duplicated()]
    link_hood = mj.h.fillna(-1).astype(int).reindex(range(len(lk))).values
    link_hood = np.where((lk.ft.values == 6) | (lk.ft.values == 13), -1, link_hood)
    pair_hoods = collections.defaultdict(set)
    for k, h in zip(key, link_hood):
        if h >= 0:
            pair_hoods[k].add(int(h))
    check(all(len(v) == 1 for v in pair_hoods.values()), "both directions of every SF street link share one neighborhood")

    nodes = np.array(sorted(set(lk.a) | set(lk.b)))
    N = len(nodes)
    ai = np.searchsorted(nodes, lk.a.values)
    bi = np.searchsorted(nodes, lk.b.values)
    bi_sink = np.where(lk.b.values <= MAXC, N + lk.b.values, bi)
    closed = np.array([(x, y) in CLOSED for x, y in zip(lk.a, lk.b)])
    for name, lo, hi in CAR_FREE:
        hit = lk.name.str.startswith(name).values & (mx >= lo) & (mx <= hi) & (lk.ft.values != 6)
        closed |= hit
        print(f"closed to cars: {name}, {int(hit.sum())} directed links", file=sys.stderr)
    check(closed.sum() >= 40, f"Market Street and JFK Drive closures found ({int(closed.sum())} links)")
    usable = (lk.ft.values != 13) & ~closed
    pf = pd.DataFrame(perf)
    T = {}
    for p in sorted({c for _, c, _ in BINS}):
        t = pf[pf.time_period == p].set_index(["a", "b"]).time_1.reindex(list(zip(lk.a, lk.b))).values
        ok = usable & ~np.isnan(t) & (t >= 0)
        T[p] = np.where(ok, np.maximum(np.nan_to_num(t), 1e-4), np.nan)
    cent = {int(c): int(np.searchsorted(nodes, c)) for c in nodes if c <= MAXC}
    pairs = ai[usable].astype(np.int64) * (N + MAXC + 1) + bi_sink[usable]
    check(len(np.unique(pairs)) == len(pairs), "no two routable links share both ends")

    # MTC zones -> SF-CHAMP zones. Outside SF the two systems share their zones (same count per county), so a zone's
    # representative point finds its one CHAMP zone. In SF each of MTC's 190 zones holds about five of CHAMP's 981; a
    # trip end is split over the CHAMP zones whose representative point lies in it, by their LODES homes plus jobs.
    mz = gpd.read_file(MTC / "taz1454.geojson")[["taz1454", "county", "geometry"]].rename(columns={"county": "mcounty"}).to_crs(4326)
    check(len(mz) == 1454, f"MTC TAZ1454 zones == 1,454 ({len(mz)})")
    cpt = taz.copy()
    cpt["geometry"] = cpt.geometry.representative_point()
    cj = gpd.sjoin(cpt, mz, predicate="within", how="left").drop_duplicates("taz")
    act = collections.Counter()
    xw = pd.read_csv(LODES / "ca_xwalk.csv.gz", usecols=["tabblk2020", "blklatdd", "blklondd", "cty"], dtype={"tabblk2020": str, "cty": str})
    xw = xw[xw.cty == "06075"]
    pts = gpd.GeoDataFrame(xw, geometry=gpd.points_from_xy(xw.blklondd, xw.blklatdd), crs=4326)
    jb = gpd.sjoin(pts, taz[["taz", "geometry"]], predicate="within", how="inner")
    blk = dict(zip(jb.tabblk2020, jb.taz))
    with gzip.open(LODES / "ca_od_main_JT01_2024.csv.gz", "rt") as f:
        for r in csv.DictReader(f):
            for g in (r["h_geocode"], r["w_geocode"]):
                if g in blk:
                    act[int(blk[g])] += int(r["S000"])
    W = collections.defaultdict(list)
    for t, cc, z in zip(cj.taz, cj.county, cj.taz1454):
        if z == z and t <= MAXC and int(t) in cent:
            W[int(z)].append((int(t), act[int(t)] + 1 if cc == 1 else 1))
    sf_mtc = set(mz.taz1454[mz.mcounty == "San Francisco"].astype(int))
    for z in list(W):
        if z not in sf_mtc and len(W[z]) > 1:      # outside SF the zones match one to one; a rare second: the lower id
            W[z] = [min(W[z])]
        tot = sum(w for _, w in W[z])
        W[z] = [(t, w / tot) for t, w in W[z]]
    check(len(W) >= 1440, f"MTC zones with a routable CHAMP zone >= 1,440 ({len(W)} of 1,454)")
    check(sum(1 for z in W if z in sf_mtc) == 190, f"all 190 SF MTC zones split over CHAMP zones ({sum(1 for z in W if z in sf_mtc)})")
    county = dict(zip(mz.taz1454.astype(int), mz.mcounty))

    # MTC trips -> vehicles by hour bin. Individual trips: drive alone 1 car, shared ride 2 half a car each, shared
    # ride 3+ 1/3.25 (MTC's own factor, travel-model-one PrepAssign.job), taxi and single TNC 1, shared TNC 1/2. Joint trips are
    # one row per party: one car. Drive-to-transit modes (14-18) are left out: their car leg ends at a station the trip
    # table does not name. Every row stands for 1/sampleRate trips.
    veh = {"indiv": {1: 1, 2: 1, 3: 0.5, 4: 0.5, 5: 1 / 3.25, 6: 1 / 3.25, 19: 1, 20: 1, 21: 0.5},
           "joint": {m: 1 for m in (1, 2, 3, 4, 5, 6, 19, 20, 21)}}
    hour_bin = np.full(24, -1)
    for k, (_, _, hours) in enumerate(BINS):
        hour_bin[list(hours)] = k
    agg = collections.defaultdict(float)
    rows_read = vtot = sf_any = 0.0
    bad_mode = bad_hour = 0
    import zipfile
    for kind, name in (("indiv", "indivTripData"), ("joint", "jointTripData")):
        with zipfile.ZipFile(MTC / f"{name}.zip") as zf, zf.open(f"{name}_3.csv") as fh:
            for ch in pd.read_csv(fh, usecols=["orig_taz", "dest_taz", "depart_hour", "trip_mode", "sampleRate"], chunksize=2_000_000):
                rows_read += len(ch)
                bad_mode += int((~ch.trip_mode.between(1, 21)).sum())
                bad_hour += int((~ch.depart_hour.between(5, 23)).sum())
                fac = ch.trip_mode.map(veh[kind]).fillna(0).values / ch.sampleRate.values
                ch = ch.assign(v=fac, b=hour_bin[ch.depart_hour.clip(0, 23).values])
                ch = ch[(ch.v > 0)]
                vtot += ch.v.sum()
                g = ch.groupby(["b", "orig_taz", "dest_taz"]).v.sum()
                for (b, o, d), v in g.items():
                    agg[(int(b), int(o), int(d))] += v
    check(bad_mode == 0, f"every trip_mode in 1..21 ({bad_mode} outside)")
    check(bad_hour == 0, f"every depart_hour in 5..23, so in a bin ({bad_hour} outside)")
    print(f"MTC trip rows read {rows_read:,.0f}, car trips a day {vtot:,.0f}", file=sys.stderr)
    NORTH, SOUTH, EAST = {"Marin", "Sonoma", "Napa", "Solano"}, {"San Mateo", "Santa Clara"}, {"Alameda", "Contra Costa"}

    def may_cross(o, d):
        """A pair whose fastest path may run through SF: an end in SF, the North Bay or East Bay to the Peninsula, the
        North Bay to the East Bay (Bay Bridge and Golden Gate), or within San Mateo County (a fastest path that clips
        SF's southern edge). Tested against the with-and-without-SF fastest times in the 2026-11-19 pipeline review."""
        a, b = county.get(o), county.get(d)
        if a == "San Francisco" or b == "San Francisco":
            return True
        if a == b == "San Mateo":
            return True
        return bool({a, b} & SOUTH) and bool({a, b} & (NORTH | EAST)) or bool({a, b} & NORTH) and bool({a, b} & EAST)
    od, lost, kept, sfv = {}, 0.0, 0.0, 0.0
    for (b, o, d), v in sorted(agg.items()):
        if not may_cross(o, d):
            continue
        if county.get(o) == "San Francisco" or county.get(d) == "San Francisco":
            sfv += v
        if o not in W or d not in W:
            lost += v
            continue
        kept += v
        for co, wo in W[o]:
            for cd, wd in W[d]:
                od.setdefault(b, collections.defaultdict(float))[(co, cd)] += v * wo * wd
    check(lost / (lost + kept) < 0.01, f"car trips with an unplaced end < 1% ({lost:,.0f} of {lost + kept:,.0f})")
    print(f"car trips with an end in SF a day {sfv:,.0f}; pairs that may cross SF {kept:,.0f}", file=sys.stderr)
    hood_of_taz = np.full(MAXC + 1, -1, dtype=np.int16)
    for t, h in taz_hood.items():
        hood_of_taz[t] = h
    RUNS.mkdir(parents=True, exist_ok=True)
    arrs = {f"od_{k}": np.array([[o, d, v] for (o, d), v in sorted(od[k].items()) if v > 1e-6], dtype=np.float64)
            for k in range(len(BINS))}
    times = {f"t_{c}": T[c] for c in T}
    nears = near_arrays(near_sets(links, tazr, link_hood, set(cent)))
    np.savez_compressed(a.npz, ai=ai, bi_sink=bi_sink, N=N, link_a=lk.a.values, link_b=lk.b.values, link_hood=link_hood,
                        hood_of_taz=hood_of_taz, cent=np.array(sorted(cent.items()), dtype=np.int64),
                        trips=round(kept), **nears, **arrs, **times)
    print(f"wrote {a.npz}: {N:,} nodes, {len(lk):,} links ({int((link_hood >= 0).sum()):,} in SF neighborhoods), "
          + ", ".join(f"{BINS[k][0]} {len(arrs[f'od_{k}']):,} pairs {arrs[f'od_{k}'][:, 2].sum():,.0f} cars" for k in range(len(BINS))),
          file=sys.stderr)


# --------------------------------------------------------------------------------------------------------- route
G_ = {}


def _init(npz):
    from scipy.sparse import csr_matrix
    Z = np.load(npz)
    G_["Z"] = {k: Z[k] for k in Z.files}
    G_["csr"] = csr_matrix


def _graph(times):
    Z, ok = G_["Z"], ~np.isnan(times)
    M = int(Z["N"]) + MAXC + 1
    return G_["csr"]((times[ok], (Z["ai"][ok], Z["bi_sink"][ok])), shape=(M, M)), ok


def _work(job):
    """Every origin in `job` for one hour bin and one time vector: per link, flow and a local flow for each distance
    of NEARS. Local flow on a link is the flow from an origin within that distance of the link, plus, from any other
    origin, the flow to destinations within that distance of it (the near sets); the rest is through."""
    from scipy.sparse.csgraph import dijkstra
    period, run, origins = job
    Z = G_["Z"]
    times = Z["t_" + BINS[period][1]]
    if run:
        f = np.random.default_rng(SEEDS[run - 1]).uniform(*JITTER, size=times.shape)
        times = times * f
    G, ok = _graph(times)
    N, M = int(Z["N"]), G.shape[0]
    ai, bs, lh = Z["ai"], Z["bi_sink"], Z["link_hood"]
    L = len(ai)
    sf = np.nonzero(ok & (lh >= 0))[0]                       # the SF links we report
    tail, head = ai[sf], bs[sf]
    flow = np.zeros(L)
    local = [np.zeros(L) for _ in NEARS]
    cent = dict(map(tuple, Z["cent"]))
    od = Z[f"od_{period}"]
    for o_taz, rows in origins:
        o = cent[o_taz]
        dist, pred = dijkstra(G, indices=o, return_predecessors=True)
        dz = od[rows]
        d_taz = dz[:, 1].astype(np.int64)
        sink = N + d_taz
        keep = np.isfinite(dist[sink]) & (dist[sink] <= CAP_MIN)
        # Column 0: demand under each node of the shortest-path tree; column 1: the node count of its subtree.
        S = np.zeros((M, 2))
        np.add.at(S, (sink[keep], 0), dz[keep, 2])
        S[:, 1] = pred >= 0
        S[o, 1] = 1
        par = pred
        depth = _depths(par, o)
        order = np.argsort(-depth, kind="stable")
        dsorted = depth[order]
        starts = np.flatnonzero(np.diff(np.concatenate(([-1], dsorted))) != 0)
        bounds = list(starts) + [len(order)]
        levels = [order[bounds[k]:bounds[k + 1]] for k in range(len(starts)) if dsorted[starts[k]] > 0]
        for v in levels:                                     # deepest first: subtree sums
            np.add.at(S, par[v], S[v])
        tot, size = S[:, 0], S[:, 1].astype(np.int64)
        # Preorder number of every reached node, so x is under y when tin[y] <= tin[x] < tin[y] + size[y]: siblings in
        # node order, each after its parent and its earlier siblings' subtrees, filled in from the root down.
        v = np.nonzero(depth > 0)[0]
        srt = np.lexsort((v, par[v]))
        vs, ps = v[srt], par[v[srt]]
        ex = np.cumsum(size[vs]) - size[vs]
        first = np.concatenate(([True], ps[1:] != ps[:-1]))
        off = np.zeros(M, dtype=np.int64)
        off[vs] = ex - ex[first][np.cumsum(first) - 1]
        tin = np.zeros(M, dtype=np.int64)
        for v in reversed(levels):
            tin[v] = tin[par[v]] + 1 + off[v]
        # Flow to destinations within each distance of NEARS of each link that runs over the link: the link is the
        # tree edge into its head and the destination's sink sits in the head's subtree.
        dk, dem = d_taz[keep], dz[keep, 2]
        on = par[head] == tail                               # a link carries flow when it is the tree edge into its head
        t = tot[head]
        flow[sf[on]] += t[on]
        for q, (name, _) in enumerate(NEARS):
            ptr, nidx = Z["near_ptr_" + name], Z["near_idx_" + name]
            n = ptr[dk + 1] - ptr[dk]
            near_d = np.zeros(L)
            if n.sum():
                r = np.repeat(np.arange(len(dk)), n)
                pos = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n) + np.repeat(ptr[dk], n)
                ln = nidx[pos].astype(np.int64)
                hd, st = bs[ln], tin[N + dk][r]
                c = ok[ln] & (par[hd] == ai[ln]) & (tin[hd] <= st) & (st < tin[hd] + size[hd])
                near_d = np.bincount(ln[c], weights=dem[r][c], minlength=L)
            near_o = np.zeros(L, dtype=bool)
            near_o[nidx[ptr[o_taz]:ptr[o_taz + 1]]] = True
            loc = np.where(near_o[sf], t, near_d[sf])
            local[q][sf[on]] += loc[on]
    return period, run, flow, local


def _depths(par, root):
    """Depth of every node in the tree par (predecessor, -9999 unreached), root at 0, by pointer doubling."""
    n = len(par)
    reach = par >= 0
    depth = np.where(reach, 1, 0).astype(np.int64)
    anc = np.where(reach, par, root)
    anc[root] = root
    # Invariant: depth[v] = edges from v up to anc[v]; jump until every ancestor is the root.
    for _ in range(64):
        if (anc == root).all():
            break
        depth = depth + np.where(anc != root, depth[anc], 0)
        anc = np.where(anc != root, anc[anc], root)
    else:
        raise RuntimeError("tree deeper than 2^64")
    depth[~reach] = -1
    depth[root] = 0
    return depth


def route(a):
    import multiprocessing as mp
    Z = np.load(a.npz)
    jobs = []
    for period in range(len(BINS)):
        od = Z[f"od_{period}"]
        by = collections.defaultdict(list)
        for i, t in enumerate(od[:, 0].astype(int)):
            by[t].append(i)
        cent = set(int(c) for c, _ in Z["cent"])
        origins = sorted((t, np.array(r)) for t, r in by.items() if t in cent)
        if a.origins:
            origins = origins[:a.origins]
        chunks = [origins[i::a.workers * 4] for i in range(a.workers * 4)]
        for run in range(1 + len(SEEDS)):
            jobs += [(period, run, c) for c in chunks if c]
    t0 = time.time()
    L = len(Z["ai"])
    acc = {(p, r): [np.zeros(L) for _ in range(1 + len(NEARS))] for p in range(len(BINS)) for r in range(1 + len(SEEDS))}
    with mp.get_context("fork").Pool(a.workers, initializer=_init, initargs=(a.npz,)) as pool:
        for k, (p, r, f, ls) in enumerate(pool.imap(_work, jobs)):
            acc[(p, r)][0] += f
            for q, l in enumerate(ls):
                acc[(p, r)][1 + q] += l
            if k % 20 == 0:
                print(f"{k + 1}/{len(jobs)} jobs, {time.time() - t0:.0f}s", file=sys.stderr)
    lh = Z["link_hood"]
    out = {}
    for i in np.nonzero(lh >= 0)[0]:
        row = []
        for p in range(len(BINS)):
            for h in (0, 1):      # the runs in two halves, alternate runs, each summed
                f = sum(acc[(p, r)][0][i] for r in range(1 + len(SEEDS)) if r % 2 == h)
                row.append(round(f, 1))
                for q in range(len(NEARS)):
                    l = sum(acc[(p, r)][1 + q][i] for r in range(1 + len(SEEDS)) if r % 2 == h)
                    row.append(round(f - l, 1))
        if any(row):
            out[f"{int(Z['link_a'][i])}_{int(Z['link_b'][i])}"] = [int(lh[i])] + row
    np.seterr(all="ignore")
    W = 1 + len(NEARS)
    bad = [k for k, v in out.items() if any(v[1 + W * g + 1 + q] > v[1 + W * g] + 0.05 for g in range(2 * len(BINS)) for q in range(len(NEARS)))]
    check(not bad, f"no link's through above its flow, at every distance ({len(bad)} bad)")
    # A longer distance counts more trip ends as near, so its through can only be smaller.
    mono = [k for k, v in out.items() if any(v[1 + W * g + 1 + q] + 0.05 < v[1 + W * g + 2 + q] for g in range(2 * len(BINS)) for q in range(len(NEARS) - 1))]
    check(not mono, f"every link's through falls as the distance grows ({len(mono)} bad)")
    nf = sum(1 for v in out.values() if v[1] > 0)
    check(nf >= 5000, f">= 5,000 SF links with flow ({nf:,})")
    doc = {"about": "Per directed SF-CHAMP link (a_b) in an SF Analysis Neighborhood: neighborhood index (name order), "
                    "then for each hour bin (bins) [car trips summed over the even runs, their through cars at each "
                    "distance of nears, the same over the odd runs]; run 0 is the base, runs 1.. jitter every link's time "
                    "by its own factor in jitter. MTC Travel Model 1.6 2023 car trips. scripts/through-traffic.py.",
           "bins": [b[0] for b in BINS], "nears": [[n, m] for n, m in NEARS], "runs": 1 + len(SEEDS), "jitter": list(JITTER), "trips": int(Z["trips"]),
           "links": dict(sorted(out.items()))}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"wrote {a.out}: {len(out):,} links in {time.time() - t0:.0f}s", file=sys.stderr)


# -------------------------------------------------------------------------------------------------------- blocks
def blocks(a):
    import importlib.util
    sys.path.insert(0, str(HERE))
    hct = paths.load("hin-cut-through.py")
    from lib.stable import write_text

    L = json.loads((OUT / "links.json").read_text())
    links = L["links"]
    T = json.loads(BLOCKS_IN.read_text())["blocks"]
    road = {r["cnn"]: r["road"] for r in T}
    B, _, tag = hct.read_blocks()
    want = {c: B[c] for c in road if c in B}
    check(len(want) == len(road), f"every traffic block has a centerline ({len(want)} of {len(road)})")
    items = hct.champ_links()
    # Main blocks take every same-named parallel link beside them (a divided road's two halves, never the link before or
    # after along the street: hin-cut-through.py beside()); residential blocks only the one link within 60 ft, as the
    # traffic rows do, so a frontage road doesn't take the arterial beside it.
    match = hct.modelled_main({c: b for c, b in want.items() if road[c] == "main"}, items)
    for c, m in hct.modelled({c: b for c, b in want.items() if road[c] == "res"}, items).items():
        match[c] = {"a_b": m["a_b"], "daily": m["daily"]}
    daily = {(int(it["a_b"].split("_")[0]), int(it["a_b"].split("_")[1])): it["daily"] for _, it in items}
    names = sorted(f["properties"]["nhood"] for f in json.loads(NHOODS.read_text())["features"])
    bins, n_runs = L["bins"], L["runs"]
    check(bins == [x[0] for x in BINS], f"links.json's hour bins are BINS ({bins})")
    n_half = [len(range(0, n_runs, 2)), len(range(1, n_runs, 2))]
    rows = {}

    def cnn_name(c):
        b = want[c]
        return f"{c} {b['name']}, {b['fname']} to {b['tname']}"

    def klass(share, cars, floor):
        return -1 if cars < floor else int(sum(share >= c for c in CLASSES))

    def figure(fe, te, fo, to, floor):
        """One bin's figure from its two half sums: the average over every run, and whether each half alone, averaged,
        lands in the same class. Each run alone is all-or-nothing, so its class scatters around the average by
        design; what matters is whether the average is settled."""
        fe, te, fo, to = (float(x) for x in (fe, te, fo, to))
        F, Tt = (fe + fo) / n_runs, (te + to) / n_runs
        if F <= 0:
            return {"share": 0, "cars": 0, "through": 0, "cls": -1, "low": 0, "halves": [-1, -1]}
        share = Tt / F
        k = klass(share, F, floor)
        hk = [klass(t / f, f / n, floor) if f else -1 for f, t, n in ((fe, te, n_half[0]), (fo, to, n_half[1]))]
        return {"share": round(share, 4), "cars": round(F), "through": round(Tt), "cls": k,
                "low": int(not hk[0] == hk[1] == k), "halves": hk}
    W = 1 + len(NEARS)
    check(L.get("nears", [["mile", NEAR_M]]) == [[n, m] for n, m in NEARS], f"links.json's distances are NEARS ({L.get('nears')})")
    nofig = collections.Counter()
    for cnn in sorted(match, key=int):
        sums = np.zeros(2 * W * len(bins))
        hood, model = None, 0
        for ab in match[cnn]["a_b"].split("+"):
            model += daily.get(tuple(int(z) for z in ab.split("_")), 0)
            x, y = ab.split("_")
            for k in (f"{x}_{y}", f"{y}_{x}"):
                v = links.get(k)
                if not v:
                    continue
                hood = v[0] if hood is None else hood
                sums += np.array(v[1:])
        q = sums.reshape(len(bins), 2, W)          # bin, half (even runs, odd runs), [cars, through at each distance]
        if q[:, :, 0].sum() <= 0:
            nofig["no routed flow (closed to cars, or outside the reported links)" if hood is None else "zero flow"] += 1
            continue
        day_q = q.sum(axis=0)

        def fig(arr, d, floor):
            """One figure at distance index d from a [half][cars, through...] array."""
            return figure(arr[0, 0], arr[0, 1 + d], arr[1, 0], arr[1, 1 + d], floor)
        D0 = [n for n, _ in NEARS].index(DEFAULT_NEAR)
        day = fig(day_q, D0, MIN_CARS)
        # Routed car trips above SF-CHAMP's own all-day volume on the same links: the routing piled a corridor onto it.
        over = bool(model) and day["cars"] > model
        day["low"] = int(day["low"] or over)
        by = {"all": day}
        for i, name in enumerate(bins):
            by[name] = fig(q[i], D0, MIN_BIN)
            by[name]["low"] = int(by[name]["low"] or over)
        # Each distance's share, through cars, class and low flag, whole day and each bin (the slider's figures).
        near = {}
        for d, (nname, _) in enumerate(NEARS):
            near[nname] = {}
            for key, arr, floor in [("all", day_q, MIN_CARS)] + [(n, q[i], MIN_BIN) for i, n in enumerate(bins)]:
                f = fig(arr, d, floor)
                near[nname][key] = {"share": f["share"], "through": f["through"], "cls": f["cls"], "low": int(f["low"] or over)}
        rows[cnn] = {**day, "bins": by, "near": near, "over_model": int(over), "model_daily": round(model),
                     "hood": names[hood] if hood is not None else "", "road": road[cnn]}
    print(f"matched blocks with no figure: {dict(nofig)}", file=sys.stderr)
    check(len(rows) >= 3000, f">= 3,000 blocks with a figure ({len(rows):,})")
    check(all(abs(sum(r["bins"][n]["cars"] for n in bins) - r["cars"]) <= len(bins) for r in rows.values()),
          "every block's hour bins add up to its day")
    check(all(r["near"][DEFAULT_NEAR][k]["share"] == r["bins"][k]["share"] for r in rows.values() for k in ["all"] + bins if k != "all")
          and all(r["near"][DEFAULT_NEAR]["all"]["share"] == r["share"] for r in rows.values()), f"the {DEFAULT_NEAR} figures match the block's own")
    for nname, metres in NEARS:
        # Named blocks the neighborhood rule read at 0%: Third Street, Ingerson to Jamestown, in Bayview.
        third = rows.get("230101", {}).get("near", {}).get(nname, {}).get("midday", {}).get("share", 0)
        check(third >= THIRD_FLOOR[nname], f"{nname}: Third St, Ingerson to Jamestown, reads at least {THIRD_FLOOR[nname]:.0%} through at midday ({third:.1%})")
        check(all(0 <= f["share"] <= 1 for r in rows.values() for f in r["near"][nname].values()), f"{nname}: every share within 0 to 1")
        # A regression test for the neighborhood rule's failure, where Bayview's Third Street read 0% because a big area
        # holds nearly every trip that uses it: a busy block (over BUSY cars a day) reading almost no through traffic
        # (under 1%) within half a mile of a block reading mostly through (over half). At a half mile or less it can't
        # fire on today's figures (no busy block reads under 1%); it stays as the tripwire for the neighborhood rule's
        # return, which is a change of rule, not of distance. The old output fails it on three
        # Bayview blocks. It is a tripwire, not a law: a local street meeting a through arterial can legitimately sit at
        # 0% beside it (Holloway Avenue at Junipero Serra, 5,000 to 10,000 cars), so the thresholds are the ones the old
        # failure trips. Two miles is too wide: downtown streets and Geary in the Outer Richmond read 0% correctly.
        busy = [c for c, r in rows.items() if r["cars"] > BUSY and r["near"][nname]["all"]["share"] < 0.01]
        thru = [c for c, r in rows.items() if r["near"][nname]["all"]["cls"] >= 0 and r["near"][nname]["all"]["share"] > 0.5]
        bad = []
        if busy and thru:
            xy = np.array([want[c]["mid"] for c in thru])
            for c in busy:
                d = np.hypot(*(xy - np.array(want[c]["mid"])).T)
                if (d <= GUARD_FT).any():
                    bad.append(f"{cnn_name(c)} ({rows[c]['cars']:,} cars, {rows[c]['near'][nname]['all']['share']:.1%})")
        check(not bad, f"{nname}: no block over {BUSY:,} cars a day under 1% through within half a mile of one over 50% ({len(bad)}: {bad[:5]})")
    # A shorter distance counts fewer trip ends as near, so a block's through share can only rise as it shrinks.
    for (n0, _), (n1, _) in zip(NEARS, NEARS[1:]):
        check(all(r["near"][n0][k]["through"] + 1 >= r["near"][n1][k]["through"] for r in rows.values() for k in r["near"][n0]),
              f"every block's through cars at {n0} are at least those at {n1}")
        check(all(r["near"][n0][k]["share"] is None or r["near"][n1][k]["share"] is None or r["near"][n0][k]["share"] + 0.001 >= r["near"][n1][k]["share"]
                  for r in rows.values() for k in r["near"][n0]), f"every block's through share at {n0} is at least its share at {n1}")

    summary = {}
    for name in ["all"] + bins:
        summary[name] = {}
        for rd in ("res", "main"):
            rs = [r["bins"][name] for r in rows.values() if r["road"] == rd]
            summary[name][rd] = {"blocks_total": sum(1 for v in road.values() if v == rd), "with_figure": len(rs),
                                 "by_class": [sum(1 for r in rs if r["cls"] == k) for k in range(len(CLASSES) + 1)],
                                 "under_min_cars": sum(1 for r in rs if r["cls"] < 0),
                                 "mostly_through": sum(1 for r in rs if r["cls"] >= 2),
                                 "low_confidence": sum(1 for r in rs if r["cls"] >= 0 and r["low"])}
    summary_near = {}
    for nname, _ in NEARS:
        summary_near[nname] = {}
        for rd in ("res", "main"):
            rs = [r["near"][nname]["all"] for r in rows.values() if r["road"] == rd]
            summary_near[nname][rd] = {"by_class": [sum(1 for r in rs if r["cls"] == k) for k in range(len(CLASSES) + 1)],
                                       "mostly_through": sum(1 for r in rs if r["cls"] >= 2)}
    by_hood = collections.defaultdict(lambda: [0, 0])
    for r in rows.values():
        if r["cls"] >= 0:
            by_hood[r["hood"]][0] += 1
            by_hood[r["hood"]][1] += r["cls"] >= 2
    doc = {"about": "Per street block (cnn) on SF-CHAMP's network: share of routed car trips passing through: neither "
                    "trip end within half a mile of the block (Bryan, 2026-11-20), car trips a weekday (MTC Travel Model 1.6, 2023, every "
                    "purpose, both directions), through cars, low-confidence flag and each half's class, for the whole "
                    "day and for each hour bin (bins), with neighborhood and road (res or main, hin-cut-through.py); "
                    "near holds the share, through cars, class and flag at each distance of nears (the map's slider: "
                    "a quarter, half a mile, three quarters, a mile). scripts/through-traffic.py.",
           "classes": CLASSES, "min_cars": MIN_CARS, "min_cars_bin": MIN_BIN, "bins": bins, "jitter": list(JITTER),
           "centerlines": tag, "summary": summary, "summary_near": summary_near, "runs": n_runs,
           "nears": [[n, m] for n, m in NEARS], "default_near": DEFAULT_NEAR, "trips": L["trips"], "blocks": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    # One line per block, so a rerun's diff reads block by block without running to hundreds of thousands of lines.
    head = json.dumps({k: v for k, v in doc.items() if k != "blocks"}, indent=1, sort_keys=True)
    body = ",\n".join(f"{json.dumps(c)}:{json.dumps(r, sort_keys=True, separators=(',', ':'))}" for c, r in sorted(rows.items()))
    write_text(OUT / "blocks.json", head[:-2] + ',\n "blocks": {\n' + body + "\n}}\n")
    check(json.loads((OUT / "blocks.json").read_text())["blocks"].keys() == rows.keys(), "blocks.json reads back whole")
    print(json.dumps(summary["all"], indent=1), file=sys.stderr)
    top = sorted(by_hood.items(), key=lambda kv: -kv[1][1] / max(kv[1][0], 1))[:8]
    print("neighborhoods by share of blocks mostly through:", [(k, v) for k, v in top], file=sys.stderr)


# ---------------------------------------------------------------------------------------------------------- zones
# Where traffic comes from (Bryan, 2026-11-19): for an area, the cars on its
# streets by where they start and where they end. The select stage below is a select-link run over the same routed
# trips: each SF Analysis Neighborhood's street links are a selection, and each Supervisor district's. Freeways, freeway connectors and ramps are not
# an area's streets (SF-CHAMP ft 1, 2 and 5, the ft 3 links named HWY or I-, and at any ft the links named as a highway,
# a ramp or a junction: FREEWAY_NAME), so a car on US 101 through Bayview or on the Bay Bridge over Treasure Island
# doesn't count as that neighborhood's traffic.
# A trip end outside SF is grouped by MTC superdistrict (tazData.csv's SD, 5 to 34; 1 to 4 are San Francisco), the
# unit tools/street-safety/where-traffic-comes-from.py merges into the map's regions, so a change to the regions needs no new run.
SUPERDISTRICTS = list(range(5, 35))
N_DIST = 11      # Supervisor districts (site/data/supervisor-districts.json), each a selection like a neighborhood
DISTRICTS = ROOT / "site/data/supervisor-districts.json"
FREEWAY_FT = (1, 2, 5)
FREEWAY_NAME = re.compile(r"^(HWY|HWT|I-\d)|RAMP\b|JUNCTION")   # "I-80 EASTBOUND" is ft 15, "HWY 101 S OFF-RAMP" ft 7 or 11
# Extra selections reported beside the neighborhoods (in the select output and the where stage's printout, not on the
# map): [label, neighborhood, SF-CHAMP street name].
EXTRA = [("Third Street in Bayview Hunters Point", "Bayview Hunters Point", "3RD")]


def add_zones(a):
    """Write the select stage's inputs into routing.npz: each SF-CHAMP zone's MTC zone (zone_mtc, 1..1454) and group
    (zone_group: the 41 neighborhoods in name order, then SUPERDISTRICTS), which links are an area's streets
    (link_street), each SF link's and SF zone's Supervisor district (link_dist, dist_of_taz, by the rules prep uses
    for neighborhoods: a link by the midpoint of its node pair's centreline, a zone by its representative point), and
    EXTRA's links (extra_mask, extra_hood). Outside SF an MTC zone is one SF-CHAMP zone and in SF it is split over
    the SF-CHAMP zones whose representative point lies in it (prep), so summing SF-CHAMP zones back to MTC zones
    undoes the split exactly."""
    import geopandas as gpd
    from shapely.geometry import shape
    links = fetch("hwynet_links", "a,b,ft,streetname,geometry", "a,b", "links.json")
    tazr = fetch("taz_boundaries", "taz,county,nhood,geometry", "taz", "taz.json")
    Z = dict(np.load(a.npz))
    check(len(links) == len(Z["link_a"]) and all(l["a"] == x and l["b"] == y for l, x, y in zip(links, Z["link_a"], Z["link_b"])),
          "routing.npz's links are hwynet_links in order")
    names = sorted(f["properties"]["nhood"] for f in json.loads(NHOODS.read_text())["features"])
    check(len(names) == 41, "41 analysis neighborhoods")
    mz = gpd.read_file(MTC / "taz1454.geojson")[["taz1454", "county", "geometry"]].rename(columns={"county": "mcounty"}).to_crs(4326)
    taz = gpd.GeoDataFrame([{"taz": t["taz"], "county": t["county"], "geometry": shape(json.loads(t["geometry"]))} for t in tazr], crs=4326)
    cpt = taz.copy()
    cpt["geometry"] = cpt.geometry.representative_point()
    cj = gpd.sjoin(cpt, mz, predicate="within", how="left").drop_duplicates("taz")
    cent = set(int(c) for c in Z["cent"][:, 0])
    sf_mtc = set(mz.taz1454[mz.mcounty == "San Francisco"].astype(int))
    members = collections.defaultdict(list)
    for t, z in zip(cj.taz, cj.taz1454):
        if z == z and t <= MAXC and int(t) in cent:
            members[int(z)].append(int(t))
    zone_mtc = np.full(MAXC + 1, -1, dtype=np.int32)
    zone_group = np.full(MAXC + 1, -1, dtype=np.int16)
    mcounty = dict(zip(mz.taz1454.astype(int), mz.mcounty))
    import csv
    with open(MTC / "tazData.csv") as fh:
        sd = {int(r["ZONE"]): int(r["SD"]) for r in csv.DictReader(fh)}
    check(len(sd) == 1454 and all((sd[z] <= 4) == (mcounty[z] == "San Francisco") for z in sd),
          "tazData.csv gives each of the 1,454 MTC zones a superdistrict, 1 to 4 for San Francisco's and no others")
    check(sorted(set(sd.values())) == list(range(1, 35)), "34 superdistricts")
    hood_of_taz = Z["hood_of_taz"]
    for z, ts in members.items():
        if z not in sf_mtc:
            ts = [min(ts)]          # prep's rule: outside SF the lower id of a rare second zone takes the MTC zone
        for t in ts:
            zone_mtc[t] = z
            zone_group[t] = hood_of_taz[t] if z in sf_mtc else 41 + SUPERDISTRICTS.index(sd[z])
    used = set()
    for k in range(len(BINS)):
        od = Z[f"od_{k}"]
        used |= set(od[:, 0].astype(int)) | set(od[:, 1].astype(int))
    miss = sorted(t for t in used if zone_mtc[t] < 0 or zone_group[t] < 0)
    check(not miss, f"every SF-CHAMP zone a trip starts or ends in has an MTC zone and a group ({len(miss)} without: {miss[:5]})")
    check(all(zone_group[t] < 41 for t in used if hood_of_taz[t] >= 0) and all(zone_group[t] >= 41 for t in used if hood_of_taz[t] < 0),
          "SF zones take their neighborhood and zones outside SF their superdistrict")
    # Supervisor districts: each SF link by the midpoint of its node pair (both directions averaged, as prep does for
    # neighborhoods) and each SF zone by its representative point; one that lands in no district takes the nearest.
    dj = json.loads(DISTRICTS.read_text())["districts"]
    check(sorted(d["district"] for d in dj) == list(range(1, N_DIST + 1)), "11 Supervisor districts")
    dg = gpd.GeoDataFrame({"d": [d["district"] - 1 for d in dj]}, geometry=[shape({"type": "MultiPolygon", "coordinates": d["coords"]}) for d in dj], crs=4326)

    def district_of(points):
        g = gpd.GeoDataFrame({"i": range(len(points))}, geometry=gpd.points_from_xy([p[0] for p in points], [p[1] for p in points]), crs=4326)
        j = gpd.sjoin(g, dg, predicate="within", how="left").drop_duplicates("i").set_index("i").d
        miss = [int(i) for i in j[j.isna()].index]
        if len(miss):
            near = gpd.sjoin_nearest(g.loc[miss].to_crs(26910), dg.to_crs(26910), how="left").drop_duplicates("i").set_index("i").d
            j.loc[miss] = near
        return j.reindex(range(len(points))).astype(int).values, len(miss)
    geoms = [shape(json.loads(l["geometry"])) for l in links]
    pair = collections.defaultdict(list)
    for l, g in zip(links, geoms):
        if not g.is_empty:
            m = g.interpolate(0.5, normalized=True)
            pair[(min(l["a"], l["b"]), max(l["a"], l["b"]))].append((m.x, m.y))
    sfl = [i for i in np.nonzero(Z["link_hood"] >= 0)[0] if (min(links[i]["a"], links[i]["b"]), max(links[i]["a"], links[i]["b"])) in pair]
    check(len(sfl) == int((Z["link_hood"] >= 0).sum()), "every SF link has a midpoint")
    mids = [tuple(np.mean(pair[(min(links[i]["a"], links[i]["b"]), max(links[i]["a"], links[i]["b"]))], axis=0)) for i in sfl]
    ld, lmiss = district_of(mids)
    link_dist = np.full(len(links), -1, dtype=np.int16)
    link_dist[sfl] = ld
    sft = [int(t) for t in taz.taz[taz.county == 1] if t <= MAXC]
    rp = taz.set_index("taz").geometry.representative_point()
    td, tmiss = district_of([(rp[t].x, rp[t].y) for t in sft])
    dist_of_taz = np.full(MAXC + 1, -1, dtype=np.int16)
    dist_of_taz[sft] = td
    check(all((dist_of_taz[t] >= 0) == (hood_of_taz[t] >= 0) for t in used), "a zone trips use is in a district exactly when it is in a neighborhood")
    check(lmiss <= 0.02 * len(sfl) and tmiss <= 0.02 * len(sft), f"few links and zones take the nearest district ({lmiss} links, {tmiss} zones)")
    print("links by district: " + ", ".join(f"D{d + 1} {int((link_dist == d).sum()):,}" for d in range(N_DIST)), file=sys.stderr)
    ft = np.array([l["ft"] for l in links])
    nm = [(l.get("streetname") or "").upper() for l in links]
    hwy = np.array([n.startswith("HWY") or n.startswith("I-") for n in nm])
    named = np.array([bool(FREEWAY_NAME.search(n)) for n in nm])
    street = (Z["link_hood"] >= 0) & ~np.isin(ft, FREEWAY_FT) & ~((ft == 3) & hwy) & ~named
    nfwy = int(((Z["link_hood"] >= 0) & ~street).sum())
    check(200 <= nfwy <= 500, f"freeway links left out of the areas' streets ({nfwy})")
    check(not any(nm[i] in ("I-80 EASTBOUND", "I-80 WESTBD") for i in np.nonzero(street)[0]), "the Bay Bridge isn't Treasure Island's street")
    mask = np.zeros((len(EXTRA), len(links)), dtype=bool)
    ehood = np.zeros(len(EXTRA), dtype=np.int64)
    for e, (label, hood, name) in enumerate(EXTRA):
        ehood[e] = names.index(hood)
        mask[e] = street & (Z["link_hood"] == ehood[e]) & np.array([n == name for n in nm])
        check(mask[e].sum() >= 20, f"{label}: {int(mask[e].sum())} directed links")
    Z.update(zone_mtc=zone_mtc, zone_group=zone_group, link_street=street, extra_mask=mask, extra_hood=ehood, link_dist=link_dist, dist_of_taz=dist_of_taz)
    np.savez_compressed(a.npz, **Z)
    print(f"wrote zones into {a.npz}: {len(members)} MTC zones, {int(street.sum()):,} street links", file=sys.stderr)


# --------------------------------------------------------------------------------------------------------- select
def _tree(par, o, M):
    """The shortest-path tree's node counts under each node (size) and preorder numbers (tin), as _work builds them."""
    depth = _depths(par, o)
    order = np.argsort(-depth, kind="stable")
    dsorted = depth[order]
    starts = np.flatnonzero(np.diff(np.concatenate(([-1], dsorted))) != 0)
    bounds = list(starts) + [len(order)]
    levels = [order[bounds[k]:bounds[k + 1]] for k in range(len(starts)) if dsorted[starts[k]] > 0]
    size = (par >= 0).astype(np.int64)
    size[o] = 1
    for v in levels:
        np.add.at(size, par[v], size[v])
    v = np.nonzero(depth > 0)[0]
    srt = np.lexsort((v, par[v]))
    vs, ps = v[srt], par[v[srt]]
    ex = np.cumsum(size[vs]) - size[vs]
    first = np.concatenate(([True], ps[1:] != ps[:-1]))
    off = np.zeros(M, dtype=np.int64)
    off[vs] = ex - ex[first][np.cumsum(first) - 1]
    tin = np.zeros(M, dtype=np.int64)
    for v in reversed(levels):
        tin[v] = tin[par[v]] + 1 + off[v]
    return size, tin


def _select_work(job):
    """Every origin in the job, over every hour bin and run: the select-link sums (see select)."""
    from scipy.sparse.csgraph import dijkstra
    origins = job
    Z = G_["Z"]
    N = int(Z["N"])
    ai, bs, lh = Z["ai"], Z["bi_sink"], Z["link_hood"]
    zm, zg, hot = Z["zone_mtc"].astype(np.int64) - 1, Z["zone_group"].astype(np.int64), Z["hood_of_taz"].astype(np.int64)
    sl = np.nonzero(Z["link_hood"] >= 0)[0]   # every SF link, freeways and ramps too, for the cordon table
    spos = np.full(len(ai), -1)
    spos[sl] = np.arange(len(sl))
    is_street = Z["link_street"]
    emask, ehood = Z["extra_mask"], Z["extra_hood"]
    ldist, dot = Z["link_dist"].astype(np.int64), Z["dist_of_taz"].astype(np.int64)
    # The selections, in rows: the 41 neighborhoods, the 11 Supervisor districts, then EXTRA (a street in a neighborhood,
    # whose trip ends are in it when they are in that neighborhood).
    E0 = 41 + N_DIST
    A, NZ, NG, NB = E0 + len(ehood), 1454, 41 + len(SUPERDISTRICTS), len(BINS)
    r41, r11 = np.arange(41)[:, None], np.arange(N_DIST)[:, None]

    def ends_in(t):
        """For zones t (an array), a rows-by-zones table: is the zone in the row's area."""
        return np.concatenate((hot[t][None, :] == r41, dot[t][None, :] == r11, hot[t][None, :] == ehood[:, None]))
    acc = {k: np.zeros((A, NZ)) for k in ("from_arr", "from_thr", "to_dep", "to_thr")}
    acc.update({"g" + k: np.zeros((A, NG)) for k in ("from_arr", "from_thr", "to_dep", "to_thr")})
    acc["inside"] = np.zeros(A)
    acc["users"] = np.zeros(A)
    acc["bins"] = np.zeros((A, NB, 4))   # per hour bin: arriving, leaving, through, inside
    acc["flow_o"] = np.zeros((NG, len(sl)))
    acc["flow_d"] = np.zeros((len(sl), NG))
    acc["flow"] = np.zeros(len(sl))
    cent = dict(map(tuple, Z["cent"]))
    for period in range(len(BINS)):
        od = Z[f"od_{period}"]
        rows_of = G_.setdefault(("rows", period), _rows_by_origin(od))
        for run in range(1 + len(SEEDS)):
            times = Z["t_" + BINS[period][1]]
            if run:
                times = times * np.random.default_rng(SEEDS[run - 1]).uniform(*JITTER, size=times.shape)
            G, ok = _graph(times)
            M = G.shape[0]
            for o_taz in origins:
                rows = rows_of.get(o_taz)
                if rows is None:
                    continue
                o = cent[o_taz]
                dist, par = dijkstra(G, indices=o, return_predecessors=True)
                dz = od[rows]
                d_taz = dz[:, 1].astype(np.int64)
                keep = np.isfinite(dist[N + d_taz]) & (dist[N + d_taz] <= CAP_MIN)
                if not keep.any():
                    continue
                size, tin = _tree(par, o, M)
                dk, dem = d_taz[keep], dz[keep, 2]
                st = tin[N + dk]
                order = np.argsort(st, kind="stable")
                st, dk, dem = st[order], dk[order], dem[order]
                n = len(dk)
                on = ok[sl] & (par[bs[sl]] == ai[sl])
                li = sl[on]
                h = bs[li]
                lo = np.searchsorted(st, tin[h], "left")
                hi = np.searchsorted(st, tin[h] + size[h], "left")
                cum = np.concatenate(([0.0], np.cumsum(dem)))
                fl = cum[hi] - cum[lo]
                nz = fl > 0
                li, lo, hi, fl = li[nz], lo[nz], hi[nz], fl[nz]
                pos = spos[li]
                go, gd = zg[o_taz], zg[dk]
                acc["flow"][pos] += fl
                acc["flow_o"][go, pos] += fl
                C = np.zeros((n + 1, NG))
                C[np.arange(1, n + 1), gd] = dem
                C = np.cumsum(C, axis=0)
                acc["flow_d"][pos] += C[hi] - C[lo]
                # Which destinations' paths use each area's streets: every destination under the head of an area link
                # on the tree, as intervals in preorder.
                m = is_street[li]
                li, lo, hi = li[m], lo[m], hi[m]
                diff = np.zeros((A, n + 1))
                np.add.at(diff, (lh[li], lo), 1)
                np.add.at(diff, (lh[li], hi), -1)
                np.add.at(diff, (41 + ldist[li], lo), 1)
                np.add.at(diff, (41 + ldist[li], hi), -1)
                for e in range(len(ehood)):
                    m = emask[e, li]
                    np.add.at(diff, (E0 + e, lo[m]), 1)
                    np.add.at(diff, (E0 + e, hi[m]), -1)
                cov = np.cumsum(diff[:, :n], axis=1) > 0
                V = cov * dem[None, :]
                din = ends_in(dk)
                vin, vout = (V * din).sum(1), (V * ~din).sum(1)
                oin = ends_in(np.array([o_taz]))[:, 0]
                acc["users"] += V.sum(1)
                acc["inside"] += np.where(oin, vin, 0)
                acc["bins"][:, period, :] += np.stack((np.where(oin, 0, vin), np.where(oin, vout, 0), np.where(oin, 0, vout), np.where(oin, vin, 0)), axis=1)
                zo = zm[o_taz]
                acc["from_arr"][:, zo] += np.where(oin, 0, vin)
                acc["from_thr"][:, zo] += np.where(oin, 0, vout)
                acc["gfrom_arr"][:, go] += np.where(oin, 0, vin)
                acc["gfrom_thr"][:, go] += np.where(oin, 0, vout)
                Wt = V * ~din
                ridx = np.arange(A)[:, None]
                for key, w in (("to_thr", Wt * ~oin[:, None]), ("to_dep", Wt * oin[:, None])):
                    acc[key] += np.bincount((ridx * NZ + zm[dk][None, :]).ravel(), weights=w.ravel(), minlength=A * NZ).reshape(A, NZ)
                    acc["g" + key] += np.bincount((ridx * NG + gd[None, :]).ravel(), weights=w.ravel(), minlength=A * NG).reshape(A, NG)
    return acc


def _rows_by_origin(od):
    by = collections.defaultdict(list)
    for i, t in enumerate(od[:, 0].astype(int)):
        by[t].append(i)
    return {t: np.array(r) for t, r in by.items()}


def select(a):
    """Select-link sums over every hour bin and run, averaged over the runs, for each SF neighborhood, each Supervisor
    district and EXTRA: cars whose route uses the area's streets, by the MTC zone and the group (neighborhood, or MTC
    superdistrict outside SF) they start and end in, the same four totals for each hour bin, split into arriving (ends in the area, starts outside), leaving (starts in it, ends outside), through (neither
    end in it) and inside (both); and for each SF street link, its cars by origin group and by destination group (the
    page's cordon count for a drawn area). A trip end is in an area when its SF-CHAMP zone's representative point is.
    numpy and scipy only, for the VM."""
    import multiprocessing as mp
    Z = np.load(a.npz)
    for k in ("zone_mtc", "zone_group", "link_street", "extra_mask", "link_dist", "dist_of_taz"):
        check(k in Z.files, f"routing.npz has {k} (run the zones stage first)")
    cent = set(int(c) for c, _ in Z["cent"])
    origins = sorted({int(t) for k in range(len(BINS)) for t in np.unique(Z[f"od_{k}"][:, 0])} & cent)
    if a.origins:
        origins = origins[:a.origins]
    n_jobs = a.workers * 2
    jobs = [origins[i::n_jobs] for i in range(n_jobs) if origins[i::n_jobs]]
    t0 = time.time()
    tot = None
    with mp.get_context("fork").Pool(a.workers, initializer=_init, initargs=(a.npz,)) as pool:
        for k, acc in enumerate(pool.imap(_select_work, jobs)):
            tot = acc if tot is None else {key: tot[key] + acc[key] for key in tot}
            print(f"{k + 1}/{len(jobs)} jobs, {time.time() - t0:.0f}s", file=sys.stderr)
    runs = 1 + len(SEEDS)
    tot = {k: v / runs for k, v in tot.items()}
    np.seterr(all="ignore")
    # Every area car is in exactly one of the four groups, and the zone and group sums agree.
    parts = tot["from_arr"].sum(1) + tot["to_dep"].sum(1) + tot["from_thr"].sum(1) + tot["inside"]
    check(np.allclose(parts, tot["users"], rtol=1e-9, atol=1e-6), "arriving + leaving + through + inside = every car on the area's streets")
    check(np.allclose(tot["from_thr"].sum(1), tot["to_thr"].sum(1), rtol=1e-9, atol=1e-6), "through cars sum the same by origin and by destination")
    day = np.stack((tot["from_arr"].sum(1), tot["to_dep"].sum(1), tot["from_thr"].sum(1), tot["inside"]), axis=1)
    check(np.allclose(tot["bins"].sum(1), day, rtol=1e-9, atol=1e-6), "each area's hour bins add to its day: arriving, leaving, through and inside")
    for k in ("from_arr", "from_thr", "to_dep", "to_thr"):
        check(np.allclose(tot[k].sum(1), tot["g" + k].sum(1), rtol=1e-9, atol=1e-6), f"{k}: MTC zones and groups sum the same")
    check(np.allclose(tot["flow_o"].sum(0), tot["flow"], rtol=1e-9, atol=1e-6) and np.allclose(tot["flow_d"].sum(1), tot["flow"], rtol=1e-9, atol=1e-6),
          "every street link's cars sum the same by origin group and by destination group")
    if not a.origins:
        check((tot["users"][:41] > 0).all(), "every neighborhood's streets carry cars")
    sl = np.nonzero(Z["link_hood"] >= 0)[0]
    r1 = lambda x: [round(float(v), 1) for v in x]
    doc = {"about": "Select-link sums per SF Analysis Neighborhood (name order), then Supervisor district 1 to 11, then "
                    "EXTRA, a weekday's cars averaged over the routing runs, every hour bin: from_* by the MTC zone "
                    "(1..1454, index z-1) or group (g*, the 41 neighborhoods then MTC superdistricts 5 to 34) a car starts "
                    "in, to_* where it ends; arr ends in the area, dep starts in it, thr neither; inside both. area_bins: "
                    "per area and hour bin (bins: name and MTC departure hours), [arr, dep, thr, inside]. links: per SF link (a_b), cars by origin group (o) and by "
                    "destination group (d); freeway: the links among them that aren't an area's streets (freeways, "
                    "connectors, ramps). origins: 0 for a full run, else the smoke test's origin count. "
                    "tools/street-safety/through-traffic.py select.",
           "runs": runs, "origins": int(a.origins),
           "freeway": sorted(f"{int(Z['link_a'][i])}_{int(Z['link_b'][i])}" for j, i in enumerate(sl) if not Z["link_street"][i] and tot["flow"][j] > 0), "superdistricts": SUPERDISTRICTS, "districts": N_DIST, "extra": [e[0] for e in EXTRA], "trips": int(Z["trips"]),
           "bins": [[b[0], list(b[2])] for b in BINS], "area_bins": [[r1(b) for b in row] for row in tot["bins"]],
           "areas": {k: [r1(row) for row in tot[k]] for k in ("from_arr", "from_thr", "to_dep", "to_thr", "gfrom_arr", "gfrom_thr", "gto_dep", "gto_thr")},
           "inside": r1(tot["inside"]), "users": r1(tot["users"]),
           "links": {f"{int(Z['link_a'][i])}_{int(Z['link_b'][i])}": {"o": r1(tot["flow_o"][:, j]), "d": r1(tot["flow_d"][j])}
                     for j, i in enumerate(sl) if tot["flow"][j] > 0}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"wrote {a.out}: {len(doc['links']):,} links in {time.time() - t0:.0f}s", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--npz", default=str(RUNS / "routing.npz"))
    r = sub.add_parser("route")
    r.add_argument("--npz", default=str(RUNS / "routing.npz"))
    r.add_argument("--out", default=str(OUT / "links.json"))
    r.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    r.add_argument("--origins", type=int, default=0, help="route only the first N origins of each period (a smoke test)")
    n = sub.add_parser("near", help="add the near sets for every distance to an existing routing.npz (no MTC reread)")
    n.add_argument("--npz", default=str(RUNS / "routing.npz"))
    sub.add_parser("blocks")
    z = sub.add_parser("zones", help="add the select stage's zone, group and street arrays to routing.npz")
    z.add_argument("--npz", default=str(RUNS / "routing.npz"))
    s = sub.add_parser("select", help="select-link sums per neighborhood and per street link (VM)")
    s.add_argument("--npz", default=str(RUNS / "routing.npz"))
    s.add_argument("--out", default=str(RUNS / "select.json"))
    s.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    s.add_argument("--origins", type=int, default=0, help="only the first N origins (a smoke test)")
    a = ap.parse_args()
    {"prep": prep, "near": add_near, "route": route, "blocks": blocks, "zones": add_zones, "select": select}[a.cmd](a)


if __name__ == "__main__":
    main()
