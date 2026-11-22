#!/usr/bin/env python3
"""Every person severely injured or killed on SF streets in 2022 to 2024 as one icon each, with the alternative High Injury Network layers as switches, for ::scratch{block="hin-people"} in the Part 1.2 Data and Notes doc. A working prototype; not published to sf-works.org.

    python3 tools/street-safety/hin-people-map.py             # writes scratch/embeds/hin-people/index.html, areas.json and screenshots
    python3 tools/street-safety/hin-people-map.py --no-shot   # the embed and areas.json only

build() is what tools/street-safety/street-safety-map.py publishes, on the daily scheduled run; main() still writes
the scratch embed by hand.

INPUTS (each read as it stands; nothing here fetches new data except through sfdata's cache):
  people   scratch/runs/hin-injuries/points.geojson from tools/street-safety/hin-injury-kinds.py: 922 of 923 people severely
           injured or killed in DataSF nwes-mmgh, 2022 to 2024, with severity, road user, age band, cause, place, kind.
  streets  DataSF 3psu-pn9h active centerlines, the same query hin-injury-kinds.py makes (so the same cache entry).
  stress   data/extract/sfmta-bci/scores.json: SFMTA and Toole Design's 2023 draft Bike Comfort Index, which carries a
           level of traffic stress (LTS 1 to 4) per direction per centerline block (CNN). A block takes the higher of
           its two directions. LTS is a bike measure; it is the only traffic-stress layer the repo holds.
  HIN      data/extract/access/hin-2024.json, the 2024 High Injury Network (the default line, and the one every rule
           here uses). hin-2022.json and hin-2017.json (from tools/street-safety/hin-versions.py) are drawn as switchable
           lines only.
  areas    data/extract/neighborhoods/analysis-neighborhoods.geojson (SF's 41 analysis neighborhoods).
  crime    data/extract/sfpd-person-crimes/incidents.json: citywide SFPD incident reports (DataSF wg3w-h783) of person
           crimes over the newest 12 months, from tools/street-safety/sfpd-person-crimes.py (run it with --update first). "Person
           crimes" are the categories Assault, Robbery, Rape, Weapons Offense and Weapons Carrying Etc. The map's crime
           view draws all-places.json from the same script: every report of any category, counted per report location
           and split into five groups (sfpd-person-crimes.py GROUPS), as a heatmap and, zoomed in, one dot per location.
  stops    .cache/muni-gtfs/feed/stops.txt, SFMTA's GTFS feed held by tools/muni/muni-gtfs.py.
  traffic  data/extract/residential-traffic/blocks.json from tools/street-safety/hin-cut-through.py: peak-hour cars on each residential
           and main-street block, measured (SFMTA counts, or residents' Telraam counters from tools/street-safety/telraam-sf.py),
           modelled (SF-CHAMP) or estimated (residential only).

RULES.
  Nearest street: a person takes the nearest surface centerline block within NEAR_FT (60 ft, the HIN rule in
  hin-injury-kinds.py); that block gives the street name and LTS. Further than 60 ft: no street.
  On a main street: the point's `place` from hin-injury-kinds.py starts "main" (a main street, class 2 to 4, at the
  corner or midblock); residential places start "residential".
  High-injury areas: the TOP_AREAS analysis neighborhoods with the most people hurt (point in polygon). For each, the
  candidate boundary is its main streets (centerline class 2 to 4) and HIN blocks: the through-traffic network the
  homes inside would be sealed from. Their names are ranked by people hurt within 60 ft.
  Placement: every person sits at the crash report's own geocoded point (tb_longitude, tb_latitude), which DataSF
  puts on the centerline at the report's recorded distance and direction from the secondary road, so it is not moved.
  People within GROUP_FT (3 ft, the same geocoded point) share one spot. The heat map gives way to the icons at zoom
  14.1; a shared spot draws its icons as a small stack, each a few pixels up and right of the last, and a click on
  any of them opens a carousel of the spot's crashes.
  Crash cards: tools/street-safety/hin_crash_cards.py joins each person's crash report (crashes, parties, victims) into a plain
  account, a details list and a diagram, drawn by site/src/safety-map/crash-cards.js.
  Crime near stops: person-crime reports within STOP_FT (300 ft, about one block) of any Muni stop in the GTFS feed,
  against the same share for every SFPD report of any category (all-places.json), since SFPD snaps reports to
  intersections and most of the city's reports are near a stop. A report with several person crimes takes the most
  serious for its label (SEVERITY).

Checks: the people within street_safety_reads.PEOPLE_BAND of the 922 read, 2022's severe injuries within
SEVERE_2022_TOLERANCE of SFDPH's published 282, unique victim ids, every person in at most one neighborhood, LTS found for most people, area
counts summing within the total, and the crime and stop reads non-empty.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import csv
import json
import math
import re
import subprocess
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402
from lib import street_safety_reads  # noqa: E402

# The gitignored scratch/ folder, or $SF_WORKS_SCRATCH: hin-injury-kinds.py's points and this prototype's own output.
SCR = Path(os.environ.get("SF_WORKS_SCRATCH") or ROOT / "scratch")
POINTS = SCR / "runs/hin-injuries/points.geojson"
EMBED = SCR / "embeds/hin-people/index.html"
RUNS = SCR / "runs/hin-people-map"
BCI = ROOT / "data/extract/sfmta-bci/scores.json"
HIN = ROOT / "data/extract/access/hin-2024.json"
HIN_OLDER = {"2022": ROOT / "data/extract/access/hin-2022.json", "2017": ROOT / "data/extract/access/hin-2017.json"}
NHOODS = ROOT / "data/extract/neighborhoods/analysis-neighborhoods.geojson"
POLICE = ROOT / "data/extract/sfpd-person-crimes/incidents.json"
NEWS = ROOT / "data/extract/vz-deaths/news.json"
POLICE_META = ROOT / "data/extract/sfpd-person-crimes/meta.json"
STOPS = ROOT / ".cache/muni-gtfs/feed/stops.txt"
RES_TRAFFIC = ROOT / "data/extract/residential-traffic/blocks.json"   # from tools/street-safety/hin-cut-through.py
RES_SUMMARY = ROOT / "out/hin-cut-through/summary.json"
NEAR_FT, GROUP_FT, STOP_FT, CELL, TOP_AREAS, MATCH_FT = 60, 3, 300, 500, 6, 300
MAIN = {"2", "3", "4"}
PERSON_CRIMES = {"Assault", "Robbery", "Rape", "Weapons Offense", "Weapons Carrying Etc"}
SEVERITY = ["Rape", "Robbery", "Assault", "Weapons Offense", "Weapons Carrying Etc"]
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
STEP = 1e5
BOUNDS = [[-122.514, 37.707], [-122.357, 37.822]]


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


class Grid(object):
    """Polylines in feet, bucketed on a CELL grid, for the nearest line within a reach."""

    def __init__(self, items):
        self.items, self.g = items, collections.defaultdict(set)
        for k, (P, _) in enumerate(items):
            for a, b in zip(P, P[1:]):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.g[(cx, cy)].add(k)

    def nearest(self, p, reach):
        cx, cy, best = int(p[0] // CELL), int(p[1] // CELL), None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self.g.get((cx + dx, cy + dy), ()):
                    P = self.items[k][0]
                    d = min(seg_dist(p, a, b) for a, b in zip(P, P[1:]))
                    if d <= reach and (best is None or d < best[0] or (d == best[0] and k < best[1])):
                        best = (d, k)
        return None if best is None else self.items[best[1]][1]

    def near(self, p, reach):
        """Every item within reach, nearest first, as (distance, item)."""
        cx, cy, out = int(p[0] // CELL), int(p[1] // CELL), {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self.g.get((cx + dx, cy + dy), ()):
                    P = self.items[k][0]
                    d = min(seg_dist(p, a, b) for a, b in zip(P, P[1:]))
                    if d <= reach:
                        out[k] = d
        return [(d, self.items[k][1]) for k, d in sorted(out.items(), key=lambda kv: (kv[1], kv[0]))]


def inside(pt, poly):
    """Ray casting over a GeoJSON Polygon's rings (holes flip it back out)."""
    x, y, c = pt[0], pt[1], False
    for ring in poly:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
    return c


def in_nhood(pt, geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return any(inside(pt, p) for p in polys)


def q(v):
    return int(round(v * STEP))


def enc_runs(runs):
    """sfMap.decode() input: {n: points per run, d: deltas carried across runs}."""
    n, d, x, y = [], [], 0, 0
    for r in runs:
        n.append(len(r))
        for lo, la in r:
            a, b = q(lo), q(la)
            d += [a - x, b - y]
            x, y = a, b
    return {"n": n, "d": d}


def thin(run, tol=2e-5):
    """Douglas-Peucker in degrees (2e-5 is about 6 ft), so curved blocks keep their shape and straight ones lose
    their midpoints."""
    if len(run) < 3:
        return run
    a, b = run[0], run[-1]
    best, k = 0, 0
    for i in range(1, len(run) - 1):
        d = seg_dist(run[i], a, b)
        if d > best:
            best, k = d, i
    if best <= tol:
        return [a, b]
    return thin(run[:k + 1], tol)[:-1] + thin(run[k:], tol)


SHORT_CAUSE = {"Unsafe speed": "Speed", "Red light": "Red light", "Not yielding in crosswalk": "Didn't yield",
               "Left turn, not yielding": "Left turn", "Stop sign": "Ran stop sign", "Unsafe turn or lane change": "Unsafe turn",
               "Following too closely": "Tailgating", "DUI": "DUI", "Pedestrian violation": "Walker violation"}
KIND_GROUP = [("Late night", "Late night"), ("Downtown main streets", "Downtown main streets"),
              ("Residential streets off the HIN", "Residential side streets"), ("Main streets", "Main streets elsewhere")]


def street_name(s):
    """Centerline names read as people write them: '05TH ST' to '5th St', 'BAY SHORE' to 'Bayshore'."""
    s = re.sub(r"\b0+(\d)", r"\1", (s or "").replace("BAY SHORE", "BAYSHORE")).title()
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)


def thin_geom(g, tol=1e-4):
    """A neighborhood outline thinned to about 30 ft, enough for a dashed line at city zoom."""
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    out = [[[[round(x, 5), round(y, 5)] for x, y in thin([tuple(p) for p in ring], tol)] for ring in poly] for poly in polys]
    return {"type": "MultiPolygon", "coordinates": out}


def short_label(p):
    """The map's label under an icon, one to three words: "Died" for a death, else the short cause, else none."""
    lab = "Died" if p["severity"] == "Killed" else SHORT_CAUSE.get(p["cause"], "")
    assert len(lab.split()) <= 3, lab
    return lab


def kind_group(k):
    for pre, g in KIND_GROUP:
        if (k or "").startswith(pre):
            return g
    return "Other"


def residential_traffic(rows):
    """The "Traffic stress" view: every residential and main-street block from tools/street-safety/hin-cut-through.py as
    encoded runs plus one row per run [class, style, peak, daily, year, low, high, source, block name, pandemic, road].
    class -1 has no figure, else 0 to 6 on the doubling scale (under 1.5 cars a minute, 1.5, 3, 6, 12, 24, 48 and up).
    style 0 measured, 1 modelled, 2 estimated, 3 grey. source 0 SFMTA count, 1 Slow Streets 2023, 2 SF-CHAMP,
    3 carried along the street, 4 main-street share, 5 Telraam counter, 6 SFMTA's figure (a count or the Slow Streets
    evaluation) with a Telraam counter beside it. road 0 residential, 1 main street. Which of a block's two counts it
    uses is hin-cut-through.py's choose_count(); this only encodes the answer.
    Source 5 carries twelve more: [segment id, valid days, first day, last day, SFMTA's peak on the block (0 none), its
    year, 1 if the day figure rests on days counted all 24 hours, 1 if SFMTA's figure is the Slow Streets day count,
    SFMTA's day figure (0 none), 1 if SFMTA's count is from the pandemic, the counter's valid April to September days,
    its last valid day in any month]. Source 6 carries ten: [segment id, valid days, first day, last day, the counter's
    peak, its day figure, 1 if counted all 24 hours, 1 if SFMTA's figure is the Slow Streets day count, the counter's
    valid April to September days, its last valid day in any month]. The season days are what hin-cut-through.py's
    override gate tests (overrides()), with the threshold in `rule`.
    `cav` lists the card caveats hin-cut-through.py's caveats() sets, one [run index, code] per run, with the lowest
    and highest day figure after counts_disagree; `telMain` is the median Telraam/model ratio behind tel_main and its
    block count."""
    T = json.loads(RES_TRAFFIC.read_text())
    geo = {}
    for r in rows:
        if r.get("line"):
            g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
            geo[str(int(float(r["cnn"])))] = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
    SRC = {"measured": 0, "modelled": 2, "carried": 3, "estimated": 4}
    STY = {"measured": 0, "modelled": 1, "carried": 2, "estimated": 2}
    names, runs, props, cnns, cav = {}, [], [], [], []
    nid = lambda v: names.setdefault(v, len(names))  # noqa: E731
    for b in sorted(T["blocks"], key=lambda b: (b.get("cls", -1), int(b["cnn"]))):
        k = b["kind"]
        cls = b["cls"] if k in SRC else -1
        sty = STY[k] if k in SRC and cls > 0 else 3
        choice = b.get("count_choice")
        src = (5 if choice == "telraam" else 6 if choice == "sfmta" else 1 if "Slow Streets" in b["src"] else SRC[k]) \
            if k in SRC else -1
        for ln in geo.get(b["cnn"], []):
            runs.append(thin([tuple(p) for p in ln]))
            cnns.append(int(b["cnn"]))
            props.append([cls, sty, b.get("peak", 0), b.get("daily", 0), b.get("year") or 0, b.get("low", 0), b.get("high", 0), src,
                          # a main-street share is a guess for the area, not a figure for the block, so it is never named
                          nid("" if src in (-1, 4) else "%s, %s to %s" % (b["street"].title(), b["from"].title(), b["to"].title())),
                          b.get("pandemic", 0), 1 if b.get("road") == "main" else 0]
                         + ([b["telraam"], b["tel_days"], b["tel_first"], b["tel_last"], b.get("sfmta_peak", 0),
                             b.get("sfmta_year", 0), b["tel_allday"], b.get("sfmta_slow", 0), b.get("sfmta_daily", 0), b.get("sfmta_pandemic", 0),
                             b["tel_season_days"], b["tel_last_valid"]]
                            if src == 5 else
                            [b["telraam"], b["tel_days"], b["tel_first"], b["tel_last"], b["tel_peak"], b["tel_daily"],
                             b["tel_allday"], b.get("sfmta_slow", 0), b["tel_season_days"], b["tel_last_valid"]] if src == 6 else []))
            for code in filter(None, (b.get("caveat") or "").split(",")):
                cav.append([len(props) - 1, code] + ([b["disagree_low"], b["disagree_high"]] if code == "counts_disagree" else []))
    assert len(runs) > 13000, f"traffic stress layer: only {len(runs)} blocks drawn"
    assert sum(1 for p in props if p[10]) > 3500, "traffic stress layer: main streets missing"
    tel = {b["cnn"] for b in T["blocks"] if b.get("telraam")}
    assert len(tel) >= 5, f"traffic stress layer: only {len(tel)} Telraam blocks"
    S = json.loads(RES_SUMMARY.read_text())
    tm = S["telraam"]["main_vs_next_model_blocks"]
    return {"runs": enc_runs(runs), "p": props, "cnn": cnns, "tel": len(tel), "rule": T["count_rule"], "names": sorted(names, key=names.get), "k": T["k"], "spill": T["spill"],
            "cav": cav, "telMain": [tm["median_ratio"], tm["blocks"]],
            # main-street blocks with both a counter and an SFMTA count, for the tel_main caveat: [name, counter, SFMTA, year]
            "telMainSfmta": [["%s, %s to %s" % (t["street"].title(), t["from"].title(), t["to"].title()), t["telraam_value"],
                              t["sfmta_value"], t["sfmta_year"]] for t in S["telraam"]["main_vs_sfmta_same_block"]],
            "scale": T["champ_scale"], "champ": S["champ_vs_count"]["median_ratio"], "champN": S["champ_vs_count"]["blocks"],
            "mchamp": S["main_streets"]["champ_vs_count"]["median_ratio"],
            "mchampN": S["main_streets"]["champ_vs_count"]["blocks"],
            "agree": [S["calibration"]["class_agree"], S["calibration"]["blocks"]],
            "floor": [S["carried_validation"]["floor_held_90_plus"], S["carried_validation"]["pairs_floor_90_plus"]]}


def build():
    """Everything the map draws, as {"data", "stats", "feats", "people", "hin_runs", "hin_older"}; main() writes the
    scratch embed from it and tools/street-safety/street-safety-map.py the site's copy."""
    if not POINTS.exists():
        sys.exit(f"{POINTS} is missing: run tools/street-safety/hin-injury-kinds.py first, which writes it")
    G = json.loads(POINTS.read_text())
    feats = sorted(G["features"], key=lambda f: f["properties"]["victim"])
    bad = street_safety_reads.people_in_band(len(feats)) or street_safety_reads.severe_2022_matches(
        sum(1 for f in feats if f["properties"]["severity"] == "Severe" and f["properties"]["date"].startswith("2022")))
    assert not bad, f"hin-injury-kinds.py's points.geojson: {bad}"
    assert len({f["properties"]["victim"] for f in feats}) == len(feats), "duplicate victim ids"

    C = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                     where="active='true'", floor=15000)
    B = json.loads(BCI.read_text())
    lts = {}
    for r in B["records"]:
        v = max(r.get("lts_ft") or 0, r.get("lts_tf") or 0)
        if v:
            lts[int(float(r["cnn"]))] = v
    H = json.loads(HIN.read_text())
    hin_runs = [r["pts"] for r in H["records"] if len(r.get("pts") or []) > 1]
    hin_grid = Grid([([xy(*p) for p in r], True) for r in hin_runs])

    surf, lts_runs = [], {3: [], 4: []}
    for r in C.rows:
        if not r.get("line"):
            continue
        layer = r.get("layer") or ""
        if layer.startswith(("FREEWAYS", "PAPER", "PSEUDO")):
            continue
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        cnn = int(float(r["cnn"]))
        s = {"cnn": cnn, "street": (r.get("streetname") or "").strip(), "cls": r.get("classcode") or "0", "lts": lts.get(cnn)}
        for ln in lines:
            surf.append(([xy(*p) for p in ln], dict(s, ll=ln)))
            if s["lts"] in (3, 4):
                lts_runs[s["lts"]].append(thin([tuple(p) for p in ln]))
    grid = Grid(surf)

    N = json.loads(NHOODS.read_text())["features"]
    people = []
    for f in feats:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        P = xy(lon, lat)
        nb = grid.near(P, NEAR_FT)
        s = dict(nb[0][1]) if nb else None
        if s:
            # At a corner several blocks tie for nearest: the person counts on every street meeting there, and the
            # block's stress is the worst of the blocks within 60 ft (the doc's "within 60 ft of an LTS 4 block").
            s["lts"] = max((it["lts"] or 0) for _, it in nb) or None
            s["main_near"] = any(it["cls"] in MAIN for _, it in nb)
            s["streets"] = sorted({it["street"] for d, it in nb if d <= nb[0][0] + 5 and it["street"]})
        hoods = [n["properties"]["nhood"] for n in N if in_nhood((lon, lat), n["geometry"])]
        assert len(hoods) <= 1, f"{p['victim']} in {hoods}"
        people.append({"p": p, "lon": lon, "lat": lat, "xy": P, "seg": s, "hood": hoods[0] if hoods else None,
                       "on_hin": hin_grid.nearest(P, NEAR_FT) is not None})
    with_lts = sum(1 for x in people if x["seg"] and x["seg"]["lts"])
    assert with_lts > 0.85 * len(people), f"only {with_lts} people matched to a block with an LTS"

    # Deaths: the Vision Zero fatality log, 2022 to its newest row, matched to the police-report people by date and place.
    extra, death_stats = load_deaths(people)
    allp = people + extra

    # Shared spots: union allp within GROUP_FT (the same geocoded point), each spot's people in date order.
    parent = list(range(len(allp)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    buckets = collections.defaultdict(list)
    for i, x in enumerate(allp):
        buckets[(int(x["xy"][0] // GROUP_FT), int(x["xy"][1] // GROUP_FT))].append(i)
    for (bx, by), idx in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in buckets.get((bx + dx, by + dy), ()):
                    for i in idx:
                        if i < j and math.dist(allp[i]["xy"], allp[j]["xy"]) <= GROUP_FT:
                            parent[find(i)] = find(j)
    spots = collections.defaultdict(list)
    for i in range(len(allp)):
        spots[find(i)].append(i)
    out_people, biggest = [], 0
    for root in sorted(spots, key=lambda r: min(allp[i]["p"]["victim"] for i in spots[r])):
        idx = sorted(spots[root], key=lambda i: (allp[i]["p"]["date"], allp[i]["p"]["hour"] if allp[i]["p"]["hour"] is not None else -1, allp[i]["p"]["victim"]))
        biggest = max(biggest, len(idx))
        clon = sum(allp[i]["lon"] for i in idx) / len(idx)
        clat = sum(allp[i]["lat"] for i in idx) / len(idx)
        for si, i in enumerate(idx):
            x, p = allp[i], allp[i]["p"]
            seg = x["seg"]
            walk = p["user"] == "Walking"
            band = {"Kid (0-17)": "kid", "Senior (65+)": "senior"}.get(p.get("band"), "adult")
            icon = ("walk-" + band) if walk else {"Biking": "bike", "Motorcycle or moped": "moto", "Car or truck": "car",
                                                  "Scooter or board": "scooter"}.get(p["user"], "car")
            out_people.append({
                "c": [round(x["lon"], 6), round(x["lat"], 6)], "s": [round(clon, 6), round(clat, 6)], "n": len(idx), "si": si,
                "cs": p.get("case") or x.get("lcs", ""),
                # DataSF nwes-mmgh victim_id, which tools/street-safety/street-safety-map.py reads for the other party and drops.
                "vid": p.get("victim", ""),
                "k": 1 if p["severity"] == "Killed" else 0, "i": icon, "cause": p["cause"], "lab": short_label(p),
                # The Vehicle Code subcause under the cause (hin-injury-kinds.py subcauses()): its key and its label.
                "sk": p.get("subcause_key", ""), "sc": p.get("subcause", ""),
                "d": p["date"], "h": p["hour"], "u": p["user"], "b": p.get("band") or "Age not stated", "pl": p["place"],
                "x": p.get("crossing") or "", "at": 1 if p.get("at") == "intersection" else 0, "kind": kind_group(p["kind"]), "trip": p["trip"],
                "st": street_name(seg["street"]) if seg else "",
                "res": 1 if p["place"].startswith("residential") and not x["on_hin"] else 0, "lts": (seg or {}).get("lts") or 0, "hood": x["hood"] or "",
                "lg": 1 if x.get("extra") else 0, "dl": x.get("dl", ""), "lid": x.get("lid", ""), "loc": x.get("loc", ""),
                "nu": x.get("nu", ""), "no": x.get("no", ""), "nt": x.get("nt", "")})

    # High-injury areas.
    by_hood = collections.defaultdict(list)
    for x in people:
        by_hood[x["hood"]].append(x)
    ranked = sorted((h for h in by_hood if h), key=lambda h: (-len(by_hood[h]), h))[:TOP_AREAS]
    areas = []
    for h in ranked:
        xs = by_hood[h]
        geom = next(n["geometry"] for n in N if n["properties"]["nhood"] == h)
        on_main = [x for x in xs if x["p"]["place"].startswith("main") or x["on_hin"]]
        resid = [x for x in xs if x["p"]["place"].startswith("residential") and not x["on_hin"]]
        streets = collections.Counter(street_name(n) for x in on_main if x["seg"] for n in x["seg"]["streets"])
        bound = [it[1]["ll"] for it in surf if it[1]["cls"] in MAIN and in_nhood(it[1]["ll"][len(it[1]["ll"]) // 2], geom)]
        bound += [r for r in hin_runs if in_nhood(r[len(r) // 2], geom)]   # the ring is main streets and HIN blocks
        areas.append({
            "name": h, "people": len(xs), "killed": sum(x["p"]["severity"] == "Killed" for x in xs),
            "on_main_or_hin": len(on_main),
            "near_main_class": sum(1 for x in xs if x["seg"] and x["seg"]["main_near"]), "residential_off_hin": len(resid),
            "late_night": sum(x["p"]["kind"].startswith("Late night") for x in xs),
            "walking": sum(x["p"]["user"] == "Walking" for x in xs),
            "seniors_walking": sum(x["p"]["user"] == "Walking" and x["p"].get("band") == "Senior (65+)" for x in xs),
            "on_lts4": sum(1 for x in xs if x["seg"] and x["seg"]["lts"] == 4),
            "causes": collections.Counter(x["p"]["cause"] for x in xs).most_common(4),
            "top_streets": streets.most_common(5),
            "kinds": collections.Counter(kind_group(x["p"]["kind"]) for x in xs).most_common(),
            "boundary_blocks": len(bound),
            "_bound": bound, "_geom": geom})
    top = {a["name"] for a in areas}
    for o in out_people:
        o["ar"] = 1 if o["hood"] in top else 0
    assert sum(a["people"] for a in areas) <= len(people)
    for a in areas:
        assert a["on_main_or_hin"] + a["residential_off_hin"] <= a["people"], a["name"]

    # Crime near Muni stops, citywide.
    police = json.loads(POLICE.read_text())
    pmeta = json.loads(POLICE_META.read_text())
    assert len(police) > 5000, f"only {len(police)} person-crime incidents citywide"
    with open(STOPS, newline="") as fh:
        stops = sorted({(round(float(r["stop_lon"]), 6), round(float(r["stop_lat"]), 6), r["stop_name"]) for r in csv.DictReader(fh)})
    assert len(stops) > 3000, f"only {len(stops)} Muni stops"
    sgrid = collections.defaultdict(list)
    for s in stops:
        X = xy(*s[:2])
        sgrid[(int(X[0] // CELL), int(X[1] // CELL))].append(X)
    person = [r for r in police if PERSON_CRIMES & set(r[1])]
    assert len(person) == len(police), "the citywide extract should hold person crimes only"

    def near_stop(lon, lat):
        X = xy(lon, lat)
        cx, cy = int(X[0] // CELL), int(X[1] // CELL)
        return any(math.dist(X, S) <= STOP_FT for dx in (-1, 0, 1) for dy in (-1, 0, 1) for S in sgrid.get((cx + dx, cy + dy), ()))
    worst = lambda cats: min(cats, key=SEVERITY.index)   # an assault-and-robbery report is labelled robbery
    crime = sorted([[r[2], r[3], worst(PERSON_CRIMES & set(r[1])), r[0]] for r in person if near_stop(r[2], r[3])])
    allp = json.loads((POLICE.parent / "all-places.json").read_text())   # every report, any category: the baseline
    all_n = sum(p[2] for p in allp)
    all_near = sum(p[2] for p in allp if near_stop(p[0], p[1]))
    assert crime, "no person crimes near stops"
    pplaces = {(r[2], r[3]) for r in person}
    crime_stats = {"person_crimes": len(person), "near_stops": len(crime), "stops": len(stops),
                   "all_reports": all_n, "all_near_stops": all_near,
                   "all_places": len(allp), "all_places_near_stops": sum(1 for p in allp if near_stop(p[0], p[1])),
                   "person_places": len(pplaces), "person_places_near_stops": sum(1 for pl in pplaces if near_stop(*pl)),
                   "from": pmeta["from"], "to": pmeta["to"], "fetched_on": pmeta["fetched_on"], "all_by_group": pmeta["all_by_group"], "all_unlocated": pmeta["all_unlocated"],
                   "by_type": collections.Counter(c[2] for c in crime).most_common()}

    crashes, card_stats = crash_cards(out_people)
    hin_bits(out_people)

    lts_people = collections.Counter(x["seg"]["lts"] if x["seg"] and x["seg"]["lts"] else 0 for x in people)
    stats = {"people": len(people), "killed": sum(x["p"]["severity"] == "Killed" for x in people), "biggest_spot": biggest,
             "spots_shared": sum(1 for v in spots.values() if len(v) > 1), "people_in_shared_spots": sum(len(v) for v in spots.values() if len(v) > 1),
             "lts_people": {str(k): v for k, v in sorted(lts_people.items())},
             "lts_blocks": {str(k): len(v) for k, v in lts_runs.items()},
             "surface_blocks_rated": len({it[1]["cnn"] for it in surf if it[1]["lts"]}),
             "surface_blocks_lts4": len({it[1]["cnn"] for it in surf if it[1]["lts"] == 4}),
             "kinds": collections.Counter(p["kind"] for p in out_people if not p["lg"]).most_common(),
             "crime": crime_stats, "deaths": death_stats, "cards": card_stats, "sources": {"people": G.get("sources"), "centerlines": C.tag, "bci_fetched": B["fetched_on"],
                                                "hin_fetched": H["fetched_on"]},
             "areas": [{k: v for k, v in a.items() if not k.startswith("_")} for a in areas]}
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "areas.json").write_text(json.dumps(stats, indent=1, sort_keys=True) + "\n")

    hin_older = {}
    for v, path in HIN_OLDER.items():
        Ho = json.loads(path.read_text())
        runs = [thin([tuple(p) for p in r["pts"]]) for r in Ho["records"] if len(r.get("pts") or []) > 1]
        assert len(runs) > 100, f"only {len(runs)} lines in {path.name}"
        hin_older[v] = enc_runs(runs)
    data = {
        "people": out_people, "bounds": BOUNDS, "hin": enc_runs(hin_runs), "hinOlder": hin_older,
        "lts3": enc_runs(lts_runs[3]), "lts4": enc_runs(lts_runs[4]), "traffic": residential_traffic(C.rows),
        "areas": [{"name": a["name"], "n": a["people"], "k": a["killed"], "geom": thin_geom(a["_geom"]),
                   "bound": enc_runs([thin([tuple(p) for p in r]) for r in a["_bound"]])} for a in areas],
        # Crime view (Bryan, 2026-11-18): every Muni stop, and every SFPD report of any category as a count per report
        # location by group; SFPD snaps reports to intersections, so a location dot is what single reports look like anyway.
        # all-places.json rows end in the day and time cells (sfpd-person-crimes.py); they travel as crimeDays, so every
        # crimeAll row stays [lon, lat, n, groups...].
        "crashes": crashes, "crimeAll": [p[:3 + len(pmeta["groups"])] for p in allp], "crimeDays": [p[3 + len(pmeta["groups"])] for p in allp],
        "crimeGroups": pmeta["groups"], "stops": [[s[0], s[1], s[2]] for s in stops],
        "stats": {k: stats[k] for k in ("people", "killed", "lts_people", "lts_blocks")}, "crimeStats": crime_stats, "deathStats": death_stats,
    }
    return {"data": data, "stats": stats, "feats": feats, "people": people, "hin_runs": hin_runs, "hin_older": hin_older}


def main():
    B = build()
    data, stats, feats, people, hin_runs, hin_older = (B[k] for k in ("data", "stats", "feats", "people", "hin_runs", "hin_older"))
    map_head = subprocess.run(
        ["node", "--input-type=module", "-e", f"const m = await import({json.dumps(str(ROOT / 'site/src/maplibre.mjs'))}); process.stdout.write(m.MAP_HEAD);"],
        check=True, capture_output=True, text=True).stdout
    html = PAGE.replace("__MAP_HEAD__", map_head).replace("__CRASH_JS__", CRASH_JS).replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("<", "\\u003c"))
    EMBED.parent.mkdir(parents=True, exist_ok=True)
    EMBED.write_text(html)
    print(json.dumps({k: stats[k] for k in ("people", "killed", "biggest_spot", "spots_shared", "people_in_shared_spots", "lts_people", "lts_blocks")}),
          file=sys.stderr)
    print(f"wrote {EMBED.relative_to(ROOT)} ({len(html) // 1024} KB) and {(RUNS / 'areas.json').relative_to(ROOT)}", file=sys.stderr)
    panel_pages = write_panels(feats, people, hin_runs, hin_older, map_head)
    if "--no-shot" in sys.argv:
        return
    for blk in panel_pages:
        for name, w, phone in ((blk + "-1366.png", 1366, False), (blk + "-390.png", 390, True)):
            if phone:
                (SCR / "embeds" / blk / "_phone.html").write_text('<!doctype html><html><body style="margin:0"><iframe src="index.html" '
                                                                          'style="width:390px;height:1400px;border:0"></iframe></body></html>')
            shoot("_phone.html" if phone else "index.html", RUNS / name, w, 1400 if phone else 1100, SCR / "embeds" / blk)
            print("wrote", (RUNS / name).relative_to(ROOT), file=sys.stderr)
    shots = [("desktop-1366.png", "", 1366, 900, False), ("phone-390.png", "", 390, 900, True),
             ("people-z15-1366.png", "people-z15", 1366, 900, False), ("people-z17-1366.png", "people-z17", 1366, 900, False),
             ("people-z17-390.png", "people-z17", 390, 900, True), ("people-z14-1366.png", "people-z14", 1366, 900, False),
             ("people-z14-390.png", "people-z14", 390, 900, True), ("card-1366.png", "people-z17-open", 1366, 900, False),
             ("card-390.png", "people-z17-open", 390, 1500, True)]
    shots += [(f"{m}-1366.png", m, 1366, 900, False) for m in ("kind", "stress", "bike", "crime", "areas")]
    shots += [(f"{m}-z{z}-{w}.png", f"{m}-z{z}", w, 900, w < 500) for m in ("stress", "bike", "crime") for z in (13, 15) for w in (1366, 390)]
    for name, hsh, w, h, phone in shots:
        page = "index.html#" + hsh
        if phone:   # headless Chrome ignores window widths under ~500px, so the phone view is the page in a 390px iframe
            (EMBED.parent / "_phone.html").write_text('<!doctype html><html><body style="margin:0"><iframe src="index.html#%s" '
                                                      'style="width:390px;height:%dpx;border:0"></iframe></body></html>' % (hsh, h))
            page = "_phone.html"
        shoot(page, RUNS / name, w, h)
        print("wrote", (RUNS / name).relative_to(ROOT), file=sys.stderr)
    # No change blindness (Bryan, 2026-11-18): flipping views at zoom 12 and 15 must leave the camera, the map frame and
    # the page height exactly as they were, with no blank frame drawn in between.
    for w in (1366, 390):
        subprocess.run(["node", paths.script("hin-map-switch-check.mjs"), str(EMBED), str(w)], check=True)


MODE = {"Pedestrian": ("walking", "Walking"), "Bicyclist": ("biking", "Biking"), "Driver": ("driving", "Car or truck"),
        "Passenger": ("a passenger", "Car or truck"), "Motorcyclist": ("on a motorcycle", "Motorcycle or moped"),
        "Moped": ("on a moped", "Motorcycle or moped"), "Standup Powered Device Rider": ("on a scooter", "Scooter or board")}
NEWS_MODE = {"walking": "Walking", "biking": "Biking", "driving": "Car or truck", "passenger": "Car or truck",
             "motorcycle": "Motorcycle or moped", "scooter": "Scooter or board"}


def how(row):
    """A plain phrase for how the person died, from the log's collision_type."""
    t, d = (row.get("collision_type") or "").lower(), row.get("deceased")
    if "muni" in t or "lrv" in t:
        return "hit by a Muni train" if "lrv" in t else "hit by a Muni vehicle"
    if "solo" in t or (t in ("bicycle collision", "e-scooter collision", "motorcycle collision") and d != "Passenger"):
        return "in a solo crash" if "solo" in t else "in a crash"
    if d == "Pedestrian":
        return "hit by a scooter rider" if "scooter" in t else ("hit by a motorcyclist" if "motorcycle" in t else "hit by a driver")
    if d == "Motorcyclist" and "pedestrian" in t:
        return "in a crash with a pedestrian"
    if "vs" in t or "&" in t:
        return "hit by a driver" if d in ("Bicyclist", "Standup Powered Device Rider", "Moped", "Motorcyclist") else "in a crash"
    return "in a crash"


def fmt_date(d):
    import datetime as dt
    x = dt.date.fromisoformat(d)
    return x.strftime("%b ") + str(x.day) + x.strftime(", %Y")


def death_label(age, mode, phrase, date):
    who = (f"{age}-year-old" if age else "Age not stated")
    return f"{who}, {mode}, {phrase}, {fmt_date(date)}"


def age_band(age):
    if age is None:
        return None
    return "Kid (0-17)" if age < 18 else "Senior (65+)" if age >= 65 else "Adult (18-64)"


def crash_cards(out_people):
    """The crash card for every person with a police case number (tools/street-safety/hin_crash_cards.py), keyed by case, and which
    High Injury Network editions each crash's point is on: every data/extract/access/hin-<year>.json held, within NEAR_FT."""
    import hin_crash_cards
    nets = []
    for f in sorted((ROOT / "data/extract/access").glob("hin-[0-9][0-9][0-9][0-9].json")):
        recs = json.loads(f.read_text())["records"]
        nets.append((f.stem[4:], Grid([([xy(*q) for q in r["pts"]], True) for r in recs if len(r.get("pts") or []) > 1])))
    assert any(y == "2024" for y, _ in nets), "the 2024 HIN file is missing"
    where = {}
    for o in out_people:
        if o["cs"]:
            where.setdefault(o["cs"], tuple(o["c"]))
    cards, stats = hin_crash_cards.build(where, lambda lon, lat: [y for y, g in nets if g.nearest(xy(lon, lat), NEAR_FT)])
    with_case = sum(1 for o in out_people if o["cs"])
    stats.update(people=len(out_people), people_with_case=with_case, people_without_case=len(out_people) - with_case,
                 hin_editions=[y for y, _ in nets])
    police = {o["cs"] for o in out_people if o["cs"] and not o["lg"]}
    assert police <= set(cards), f"police-report people with no crash row: {sorted(police - set(cards))[:5]}"
    for o in out_people:   # a fatality-log case DataSF has not published yet keeps the log's card
        if o["cs"] and o["cs"] not in cards:
            o["cs"] = ""
    return cards, stats


def hin_bits(out_people):
    """Each person's `hy`: which High Injury Network editions run within NEAR_FT of their point, as bits (1 for 2017,
    2 for 2022, 4 for 2024), the same 60 ft rule as hin-injury-kinds.py's hin2024 and the crash cards' editions."""
    nets = []
    for bit, y in ((1, "2017"), (2, "2022"), (4, "2024")):
        recs = json.loads((ROOT / f"data/extract/access/hin-{y}.json").read_text())["records"]
        nets.append((bit, Grid([([xy(*q) for q in r["pts"]], True) for r in recs if len(r.get("pts") or []) > 1])))
    for o in out_people:
        P = xy(*o["c"])
        o["hy"] = sum(bit for bit, g in nets if g.nearest(P, NEAR_FT))


def load_deaths(people):
    """The Vision Zero fatality log (DataSF dau3-4s8f) from 2022 on, plus news-only deaths newer than the log.

    A log death is the police-report person (nwes-mmgh, Killed) whose collision date is within one day and whose point
    is within MATCH_FT; it then carries the log's age, mode and how. A log death with no such person (2025 on, or a
    miss) becomes its own figure. Articles come from data/extract/vz-deaths/news.json, each checked by hand on date
    and place; a news-only death without a point is counted but not drawn."""
    import datetime as dt
    F = street_safety_reads.read("people-map-deaths")
    news = json.loads(NEWS.read_text()) if NEWS.exists() else {"matches": [], "news_only": []}
    art = {m["unique_id"]: m for m in news.get("matches", [])}
    by_year = collections.Counter(r["collision_datetime"][:4] for r in F.rows)
    for y, n in (("2022", 39), ("2023", 26), ("2024", 42)):   # the counts read 2026-11-18; a revision of a death or two is fine
        assert abs(by_year[y] - n) <= 2, f"fatality log {y} has {by_year[y]} deaths, read as {n}: look before trusting the match"
    assert len({r["unique_id"] for r in F.rows}) == len(F.rows), "duplicate unique_id in the fatality log"
    killed = [x for x in people if x["p"]["severity"] == "Killed"]
    used, extra, matched = set(), [], 0
    for r in sorted(F.rows, key=lambda r: (r["collision_datetime"], r["unique_id"])):
        date = r["collision_datetime"][:10]
        try:
            lon, lat = float(r["longitude"]), float(r["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        P = xy(lon, lat)
        d0 = dt.date.fromisoformat(date)
        def close(x):
            days, ft = abs((dt.date.fromisoformat(x["p"]["date"]) - d0).days), math.dist(x["xy"], P)
            return (days <= 1 and ft <= MATCH_FT) or (days == 0 and ft <= 2000) or (days <= 5 and ft <= 50)
        cand = [x for x in killed if id(x) not in used and close(x)]
        mode, user = MODE.get(r.get("deceased"), ("travelling", "Car or truck"))
        age = int(float(r["age"])) if r.get("age") else None
        lband = age_band(age)
        info = {"dl": death_label(age, mode, how(r), date), "lid": r["unique_id"], "loc": r.get("location") or "",
                "lcs": r.get("case_id_fkey") or ""}
        a = art.get(r["unique_id"])
        if a:
            info.update(nu=a["url"], no=a["outlet"], nt=a.get("title", ""))
        if cand:
            # A crash that killed several people: pair by mode and age band first, then by distance.
            x = min(cand, key=lambda x: (x["p"]["user"] != user, x["p"].get("band") != lband, math.dist(x["xy"], P)))
            used.add(id(x))
            x.update(info)
            matched += 1
            continue
        band = age_band(age)
        hour = int(r["collision_datetime"][11:13]) if len(r["collision_datetime"]) > 12 else None
        extra.append(dict(info, extra=True, lon=lon, lat=lat, xy=P, seg=None, hood=None, on_hin=False,
                          p={"victim": "log-" + r["unique_id"], "severity": "Killed", "user": user, "band": band, "cause": "Not in the 2022-24 police extract",
                             "date": date, "hour": hour, "place": "", "crossing": None, "kind": "", "trip": "", "src": "log"}))
    for i, nrow in enumerate(sorted(news.get("news_only", []), key=lambda n: (n["date"], n.get("location") or ""))):
        if nrow.get("lat") is None or nrow.get("lon") is None:
            continue
        age, mode = nrow.get("age"), nrow.get("mode") or "travelling"
        band = age_band(age)
        extra.append({"extra": True, "lon": nrow["lon"], "lat": nrow["lat"], "xy": xy(nrow["lon"], nrow["lat"]), "seg": None, "hood": None,
                      "on_hin": False, "dl": death_label(age, mode, nrow.get("how") or "killed", nrow["date"]), "lid": "", "loc": nrow.get("location") or "",
                      "nu": nrow["url"], "no": nrow["outlet"], "nt": nrow.get("title", ""),
                      "p": {"victim": "news-%03d" % i, "severity": "Killed", "user": NEWS_MODE.get(mode, "Car or truck"), "band": band,
                            "cause": "Not yet in the city's records", "date": nrow["date"], "hour": None, "place": "", "crossing": None,
                            "kind": "", "trip": "", "src": "news"}})
    stats = {"log_rows": len(F.rows), "log_by_year": dict(sorted(by_year.items())), "log_newest": max(r["collision_datetime"] for r in F.rows)[:10],
             "matched_to_police_people": matched, "police_killed": len(killed), "log_only_drawn": sum(1 for e in extra if e["p"]["src"] == "log"),
             "news_only_drawn": sum(1 for e in extra if e["p"]["src"] == "news"), "news_only_total": len(news.get("news_only", [])),
             "with_article": len(art), "log_tag": F.tag, "published_totals": news.get("published_totals", [])}
    assert matched >= 0.9 * len([x for x in killed]), f"only {matched} of {len(killed)} police-report deaths matched the log"
    return extra, stats


def time_window(date, hour):
    """Our time-of-week window: late night first (10 pm to 4 am, any day), then weekend, then weekday peak or off-peak."""
    if hour is None:
        return None
    if hour >= 22 or hour < 4:
        return "Late night, 10 pm to 4 am"
    import datetime as dt
    if dt.date.fromisoformat(date).weekday() >= 5:
        return "Weekend, 4 am to 10 pm"
    if 6 <= hour <= 9 or 15 <= hour <= 18:
        return "Weekday commute peaks, 6 to 10 am and 3 to 7 pm"
    return "Weekday off-peak, 4 to 6 am, 10 am to 3 pm, 7 to 10 pm"


def hull(pts):
    """Convex hull, Andrew's monotone chain, closed ring."""
    P = sorted(set(pts))
    if len(P) < 3:
        return P

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(P), half(reversed(P))
    ring = lo[:-1] + up[:-1]
    return ring + ring[:1]


def top_kind(k, seen):
    """The kind a panel shows: the `kind` label as hin-injury-kinds.py writes it, or, while that script writes fine
    buckets ("Late night: walking"), the part before the colon, so the panels stay at about eight."""
    if len(seen) <= 10 or not k:
        return k
    return k.split(":")[0]


def write_panels(feats, people, hin_runs, hin_older, map_head):
    """Small-multiple pages, one small map per group, for the doc's sections 3 to 5 (blocks hin-people-<view>).

    Each page carries the 2024, 2022 and 2017 High Injury Networks once (the main map's encoded lines), and one row of
    checkboxes switches them on every small map at once."""
    tpl = (HERE / "hin-people-panels.html").read_text()
    SCHOOL = "School trips: kids 5 to 18 on weekdays, 6 am to 6 pm"
    TIME = [SCHOOL, "Late night, 10 pm to 4 am", "Weekday commute peaks, 6 to 10 am and 3 to 7 pm",
            "Weekday off-peak, 4 to 6 am, 10 am to 3 pm, 7 to 10 pm", "Weekend, 4 am to 10 pm"]

    def time_panel(p):
        """School trips first (hin-injury-kinds.py's trip, lib/school_window.py's rule), taken out of the other windows."""
        return SCHOOL if (p.get("trip") or "").startswith("School") else time_window(p["date"], p["hour"])
    views = {
        "hin-people-kind": (lambda p: top_kind(p["kind"], kinds_seen), None, "One small map per kind of crash in section 3, with its rules; a person is in the first kind whose rule matches."),
        "hin-people-time": (time_panel, TIME, "By the hour and day of the crash, late night first. Weekday peaks are 6 to 10 am and 3 to 7 pm. "
                            "School trips are kids 5 to 18 hurt on weekdays between 6 am and 6 pm, August to May (the School Trips rule); "
                            "they are taken out of the other windows."),
        "hin-people-user": (lambda p: p["user"], None, "By how the person hurt was travelling, from the police report."),
        "hin-people-trip": (lambda p: p["trip"], None, "By time window, our guess at the trip; the school-run panel shows the zones within about a quarter mile of a school's grounds (school points and grounds from the School Trips data)."),
    }
    kinds_seen = {f["properties"]["kind"] for f in feats}
    zones = []
    sch = json.loads((ROOT / "site/data/school-sim/index.json").read_text())["schools"]
    grounds = json.loads((ROOT / "data/school-sim/grounds.json").read_text())["schools"]
    for s in sch:
        g = grounds.get("%.5f,%.5f" % (s["lon"], s["lat"])) or {}
        verts = [tuple(q) for ring in (g.get("rings") or []) for q in thin([tuple(v) for v in ring], 3e-5)] or [(s["lon"], s["lat"])]
        pts = [(lo + 1320 * math.cos(t) / FT_LON, la + 1320 * math.sin(t) / FT_LAT)
               for lo, la in verts for t in (2 * math.pi * i / 24 for i in range(24))]
        zones.append([[round(x, 5), round(y, 5)] for x, y in hull(pts)])   # the grounds' hull grown by 1,320 ft
    assert len(zones) > 150, f"only {len(zones)} schools"
    out = []
    for blk, (fn, order, cap) in views.items():
        groups = collections.Counter(fn(f["properties"]) for f in feats)
        groups.pop(None, None)
        groups.pop("Time not stated", None)
        fam = [g for _, g in KIND_GROUP] + ["Other"]
        rank = (lambda kv: (fam.index(kind_group(kv[0])), -kv[1], kv[0])) if blk == "hin-people-kind" else (lambda kv: (-kv[1], kv[0]))
        names = order or [g for g, _ in sorted(groups.items(), key=rank)]
        assert set(names) == set(groups), (blk, set(names) ^ set(groups))
        idx = {g: i for i, g in enumerate(names)}
        pts, cats = [], [{"name": g, "n": 0, "k": 0} for g in names]
        for f, x in zip(feats, people):
            g = fn(f["properties"])
            ci = idx.get(g, -1)
            killed = 1 if f["properties"]["severity"] == "Killed" else 0
            pts.append([round(x["lon"], 5), round(x["lat"], 5), killed, ci])
            if ci >= 0:
                cats[ci]["n"] += 1
                cats[ci]["k"] += killed
        if blk in ("hin-people-trip", "hin-people-time"):
            for c in cats:
                c["zones"] = c["name"].startswith("School")
        data = {"pts": pts, "cats": cats, "hin": enc_runs(hin_runs), "hinOlder": hin_older, "bounds": BOUNDS, "total": len(feats), "cap": cap,
                "zones": zones if blk in ("hin-people-trip", "hin-people-time") else None}
        html = tpl.replace("__MAP_HEAD__", map_head).replace("__BLOCK__", blk).replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("<", "\\u003c"))
        d = SCR / "embeds" / blk
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
        print(f"wrote scratch/embeds/{blk}/index.html: " + "; ".join(f"{c['name']} {c['n']}" for c in cats), file=sys.stderr)
        out.append(blk)
    return out


def shoot(page, out, w, h, root=None):
    js = r"""
import { spawn } from "node:child_process";
import fs from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";
const [url, out, w, h, profile] = process.argv.slice(1);
const port = 9700 + Math.floor(Math.random() * 100);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run", "--hide-scrollbars",
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
try {
  let t;
  for (let i = 0; i < 50 && !t; i++) { await sleep(200); try { t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((x) => x.type === "page"); } catch {} }
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let seq = 0; const p = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && p.has(m.id)) { p.get(m.id)(m); p.delete(m.id); } else if (m.method === "Runtime.consoleAPICalled") console.error("  console:", m.params.args.map((a) => a.value).join(" ")); else if (m.method === "Runtime.exceptionThrown") console.error("  error:", JSON.stringify(m.params.exceptionDetails).slice(0, 400)); };
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; p.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  await send("Page.enable"); await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: 2, mobile: false });
  await send("Page.navigate", { url });
  const ready = "(window.__ready || (document.querySelector('iframe') && document.querySelector('iframe').contentWindow.__ready)) === 2";
  for (let i = 0; i < 80; i++) { await sleep(500); if ((await send("Runtime.evaluate", { expression: ready, returnByValue: true })).result.result.value) break; }
  await sleep(3500);
  const s = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(out, Buffer.from(s.result.data, "base64"));
  ws.close();
} finally { chrome.kill(); }
"""
    import socket
    with socket.socket() as so:   # a free port, so two runs can't serve each other's pages
        so.bind(("127.0.0.1", 0))
        port = str(so.getsockname()[1])
    srv = subprocess.Popen([sys.executable, "-m", "http.server", port, "--bind", "127.0.0.1", "--directory", str(root or EMBED.parent)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.8)
        import shutil
        import tempfile
        prof = tempfile.mkdtemp(prefix="chrome-shot-hin-people-")
        try:
            subprocess.run(["node", "--input-type=module", "-e", js, f"http://127.0.0.1:{port}/{page}", str(out), str(w), str(h), prof], check=True)
        finally:
            shutil.rmtree(prof, ignore_errors=True)
    finally:
        srv.terminate()


CRASH_JS = (ROOT / "site/src/safety-map/crash-cards.js").read_text()   # one copy, shared with the site's Street Safety map
PAGE = (HERE / "hin-people-map.html").read_text() if (HERE / "hin-people-map.html").exists() else ""

if __name__ == "__main__":
    assert PAGE, "scripts/hin-people-map.html is missing"
    main()
