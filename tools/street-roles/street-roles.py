#!/usr/bin/env python3
"""The Street Roles Map's data: a role for every San Francisco street block (through, local, bike or walk), its bike level of traffic stress today and with the roles and the Biking and Rolling Plan network built, and how many SF residents' short commutes are connected at stress level 2 or better each way.

    python3 tools/street-roles/street-roles.py prepare --lodes <ca_od_main_JT00_2023.csv.gz>
    python3 tools/street-roles/street-roles.py route        # on the VM: tools/street-roles/street-roles-vm.sh
    python3 tools/street-roles/street-roles.py check        # the quality checks alone

prepare writes site/data/street-roles/streets.json (blocks, roles, stress inputs, geometry) and
site/data/street-roles/commutes.json (block groups, where each meets the street network, commuters between them).
route adds each commute pair's shortest distance on every street (the yardstick for detour) to commutes.json and
writes the default figures to out/street-roles/summary.json. The page recomputes the "with the network" figure in
the browser when a reader changes a street's role, with the same rules (site/src/street-roles.mjs), and
tools/street-roles/parity.mjs checks the two agree on the default roles.

INPUTS, all held copies read by the scripts named, none refetched here except the lane layer on a cold cache:
  DataSF 3psu-pn9h   street centerlines, active rows: CNN, street name, end node CNNs, classcode, layer, line.
  DataSF 3t7b-gebn   posted speed limits by CNN. 0 is the 25 mph default, 99 a freeway (read as 45 here).
  SFMTA MTA.CTA_trafficlanes  LANES_OP by CNN, through pipeline/crash-augment/street/street_sources.py. On a
                     two-way street the count reads as one direction (street_fields.py), so a two-way block's
                     total is twice it. A block with no count, or 0, takes 1 a direction.
  SFMTA Bike Comfort Index, 2023 draft  data/extract/sfmta-bci/scores.json: lts_ft and lts_tf, 1 to 4. A block's
                     stress is the higher direction's, as analysis/crash-profiles/crash-profiles.py reads it.
  Bikeways today     site/data/bike-history/components.json (the extended bikeway data: SFMTA's layer plus
                     the work only its project pages report). A block with a Class I path, a Class IV separated
                     lane or a Slow Street is stress 1 today, as School Trips counts it.
  The plan network   site/data/north-star/traced.geojson, the 2025 Biking and Rolling Plan's North Star map
                     traced onto CNNs, with the plan's facility per block.
  Muni streets       data/muni-streets/blocks.json, blocks a Muni route runs along.
  Census blocks      data/extract/census-blocks/2020.json, each 2020 block's interior point.
  LODES 8 OD 2023    lehd.ces.census.gov/data/lodes/LODES8/ca/od/ca_od_main_JT00_2023.csv.gz, all jobs (S000),
                     home and work block both in San Francisco, summed to block group pairs. Passed as --lodes.

ROLES, the default, in this order (ROLE_RULES below carries the sentence the page shows for each):
  walk     a pedestrian street (layer STREETS_PEDESTRI, as the centerlines spell it). Not ridden in the stress network.
  through  an arterial or major street in the city's classification (classcode 3 or 2), unless the plan routes
           bikes on it without a separated bikeway, which makes it a bike street. "Separated" is the plan's own
           group: "Separated facilities are those that provide some kind of vertical separation between people
           biking and rolling and cars" (Biking and Rolling Plan, March 2025, printed pp. 74-75), and its
           Separated, Car-free and Shared-use Path facilities are that group. Shared, Shared L3 and Undecided
           are not.
  bike     any other block on the plan's network.
  local    every other surface street: collectors (4) and residential streets (5).
Freeways (1), ramps (6) and class 0 rows (paper, private and unaccepted streets) are left out.

STRESS WITH THE NETWORK, by role (stress_with below), with Mekuria, Furth and Nixon's Table 4 for mixed traffic
(MTI Report 11-19, 2012, mixed() below) read at each block's posted speed and lanes. The table's lower value needs
fewer than 3 lanes and low traffic, and "LTS 2 can be achieved with mixed traffic only on streets with one lane per
direction" (p. 21):
  through  today's stress, or 1 where the plan puts a separated bikeway on the block.
  local    the table with low traffic, since we assume a local street's filters keep through drivers off it
           [inference -- mine]. A two-lane 25 mph street is 1, a 30 mph one 2, and two lanes a direction 3 or more.
  bike     a separated plan facility 1. Shared, off a Muni line and one lane a direction, a Slow Street with
           filters, 1 (the plan calls its Level I and II shared streets "All Ages and Abilities"). Other Shared, and
           Shared L3 ("manage motor vehicle speed not volume"), the table without the low-traffic value. Undecided as
           a local street.
  walk     not ridden.
A block is never rated worse than today. A block the Bike Comfort Index leaves unrated takes the table today, with
the low-traffic value on residential streets, as the report does in San Jose.

CONNECTED, Mekuria, Furth and Nixon's own definition (MTI Report 11-19, p. 14): a trip is connected at stress k
when a path using only blocks of stress k or less is less than 25% longer than the shortest path on every
street, or less than 1,760 ft longer. Trips counted: jobs held by SF residents in SF (LODES counts jobs, so a
person with two jobs counts twice), whose home and work block groups differ and whose shortest path on every
street is 0.5 to 6 miles, the report's own window ("not more than six miles ... not less than 0.5 miles", p. 3).
A block group's trips start at the street corner nearest its residents' centre (2020 block populations) and end at
the corner nearest its jobs' centre (LODES work blocks), as the report attaches demand to one point per zone
[inference -- mine]. The street network is two-way for bikes, and crossings are not rated, as the Bike Comfort
Index rates blocks, not crossings, so both figures are the upper end of what the method gives.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import gzip
import heapq
import json
import math
import os

from lib import stable  # noqa: E402

ROOT = paths.ROOT
SITE_DATA = os.path.join(ROOT, "site", "data", "street-roles")
STREETS = os.path.join(SITE_DATA, "streets.json")
COMMUTES = os.path.join(SITE_DATA, "commutes.json")
OUT = os.path.join(ROOT, "out", "street-roles")
SUMMARY = os.path.join(OUT, "summary.json")
BCI = os.path.join(ROOT, "data", "extract", "sfmta-bci", "scores.json")
COMPONENTS = os.path.join(ROOT, "site", "data", "bike-history", "components.json")
TRACED = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
MUNI = os.path.join(ROOT, "data", "muni-streets", "blocks.json")
BLOCKS = os.path.join(ROOT, "data", "extract", "census-blocks", "2020.json")

CENTERLINE_SELECT = "cnn,streetname,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,analysis_neighborhood,line"
SF = "06075"
FT_PER_M = 3.28084
MILE = 5280
TRIP_MIN_FT, TRIP_MAX_FT = 0.5 * MILE, 6 * MILE
DETOUR_RATIO, DETOUR_FT = 1.25, 1760
LOW = 2                     # the stat's stress level: LTS 2, "tolerated by the mainstream adult population"
SEPARATED = ("Separated", "Car-free", "Shared-use Path")
# The plan's facility per block, as one letter the page reads.
PLAN_CODE = {"Separated": "S", "Car-free": "C", "Shared-use Path": "P", "Shared": "H", "Shared L3": "L", "Undecided": "U"}
ROLES = ("through", "local", "bike", "walk")
# Why the default rule gave a block its role, the sentence its card shows.
ROLE_RULES = {
    "art": "An arterial or major street in the city's street classification, so it carries through traffic.",
    "art-sep": "An arterial in the city's street classification, where the Biking and Rolling Plan puts a separated "
               "bikeway. It carries through traffic, with bikes kept apart.",
    "art-brp": "An arterial in the city's street classification, but the Biking and Rolling Plan routes bikes on it "
               "without a separated bikeway, so we make it a bike street.",
    "brp": "On the Biking and Rolling Plan's North Star network.",
    "loc": "A collector or residential street in the city's street classification, so it serves local trips.",
    "walk": "A pedestrian street in the city's street centerlines.",
}
SURFACE = {"2", "3", "4", "5"}


def haversine_ft(a, b):
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h)) * FT_PER_M


def mixed(mph, total, per_dir, low):
    """Mekuria, Furth and Nixon, Table 4, mixed traffic. Up to 25 mph: 2-3 lanes LTS 1 (the lower value) or 2, 4-5
    lanes 3, 6+ 4. 30 mph: 2-3 lanes 2 or 3, 4+ 4. 35+ mph: 4. The lower value only with fewer than 3 lanes and low
    traffic (the table's note), and "LTS 2 can be achieved with mixed traffic only on streets with one lane per
    direction" (p. 21), so 2 or more lanes a direction is at least 3."""
    if mph > 30 or total >= 6:
        return 4
    if total >= 4:
        return 3 if mph <= 25 else 4
    lower = low and total < 3
    v = (1 if lower else 2) if mph <= 25 else (2 if lower else 3)
    return max(v, 3) if per_dir >= 2 else v


def stress_with(role, b):
    """A block's stress with the roles and the plan network built (module docstring, STRESS WITH THE NETWORK).
    b: {"t": today's stress, "l": total lanes, "d": lanes a direction, "s": posted mph, "p": plan code or "",
    "m": 1 on a Muni line}. None: not ridden."""
    t, p = b["t"], b["p"]
    sep = p in ("S", "C", "P")
    if role == "walk":
        return None
    if role == "through":
        return 1 if sep else t
    if role == "bike" and p and p != "U":
        if sep:
            v = 1
        elif p == "H" and not b["m"] and b["d"] < 2:
            v = 1
        else:
            v = mixed(b["s"], b["l"], b["d"], False)
    else:
        v = mixed(b["s"], b["l"], b["d"], True)
    return min(t, v)


def default_role(cls, layer, plan):
    if layer.startswith("STREETS_PEDESTRI"):
        return "walk", "walk"
    arterial = cls in ("2", "3")
    if plan:
        if arterial:
            return ("through", "art-sep") if plan in SEPARATED else ("bike", "art-brp")
        return "bike", "brp"
    if arterial:
        return "through", "art"
    return "local", "loc"


def encode_runs(runs):
    """Lines as {n: points per run, d: offsets in 1e-5 degrees}, as site/src/maplibre.mjs encodeRuns writes them
    (tol 0), so the page decodes them with sfMap.decode."""
    n, d = [], []
    cx = cy = 0
    for run in runs:
        pts = []
        for c in run:
            p = (int(round(c[0] * 1e5)), int(round(c[1] * 1e5)))
            if not pts or pts[-1] != p:
                pts.append(p)
        n.append(len(pts))
        for x, y in pts:
            d += [x - cx, y - cy]
            cx, cy = x, y
    return {"n": n, "d": d}


# ---- prepare ------------------------------------------------------------------------------------------------------

def centerlines():
    import sfdata  # lib/, on the path paths puts there
    r = sfdata.fetch("3psu-pn9h", select=CENTERLINE_SELECT, where="active='true'", floor=15000)
    return r.rows, r.fetched_on.isoformat()


def speed_limits():
    import sfdata
    r = sfdata.fetch("3t7b-gebn", floor=15000)
    out = {}
    for row in r.rows:
        c = str(row.get("cnn") or "").split(".")[0]
        try:
            v = int(float(row.get("speedlimit") or 0))
        except ValueError:
            continue
        # 99 marks a freeway with no limit. On a surface block (ramps the centerlines class as streets) it reads as
        # 45 mph, the highest posted limit in the layer, so the table rates it 4 [inference -- mine].
        out[c] = max(out.get(c, 0), 25 if v == 0 else 45 if v == 99 else v)
    return out, r.fetched_on.isoformat()


def lanes():
    sys.path.insert(0, os.path.join(ROOT, "pipeline", "crash-augment", "street"))
    import street_sources
    src = street_sources._arcgis("lanes", False)
    out = {}
    for f in src.rows:
        a = f.get("attributes", f)
        c = str(a.get("CNN") or "").split(".")[0]
        v = a.get("LANES_OP")
        if c and v is not None:
            out[c] = max(out.get(c, 0), int(v))
    return out, src.read_on


def bci():
    d = json.load(open(BCI, encoding="utf-8"))
    out = {}
    for r in d["records"]:
        v = [x for x in (r.get("lts_ft"), r.get("lts_tf")) if x]
        if v:
            out[str(r["cnn"]).split(".")[0]] = max(int(x) for x in v)
    return out, d["fetched_on"]


def all_ages_today():
    """CNNs with a Class I path, a Class IV separated lane or a Slow Street in the latest year of the extended data."""
    d = json.load(open(COMPONENTS, encoding="utf-8"))
    out = set()
    for k, v in d["blocks"].items():
        if set(v.get("m", {})) & {"1", "4"} or v.get("s") is not None:
            out.add(str(k).split(".")[0])
    return out, d["year"]


def plan_blocks():
    d = json.load(open(TRACED, encoding="utf-8"))
    out = {}
    rank = {f: i for i, f in enumerate(("Separated", "Car-free", "Shared-use Path", "Shared L3", "Shared", "Undecided"))}
    for f in d["features"]:
        p = f["properties"]
        c, fac = str(p["cnn"]), p["facility"]
        if fac not in PLAN_CODE:
            continue
        # A block the trace gave two facilities keeps the more separated one.
        if c not in out or rank[fac] < rank[out[c]]:
            out[c] = fac
    return out


def read_lodes(path):
    """({(home bg, work bg): jobs}, SF-to-SF jobs, {work block: jobs}) for SF home and SF work blocks, S000."""
    pairs = collections.Counter()
    work = collections.Counter()
    total = 0
    with gzip.open(path, "rt", newline="") as fh:
        for row in csv.DictReader(fh):
            h, w = row["h_geocode"], row["w_geocode"]
            if not (h.startswith(SF) and w.startswith(SF)):
                continue
            n = int(row["S000"])
            total += n
            work[w] += n
            pairs[(h[:12], w[:12])] += n
    return pairs, total, work


def prepare(args):
    rows, cl_read = centerlines()
    speed, speed_read = speed_limits()
    lane, lane_read = lanes()
    lts, bci_read = bci()
    aa, aa_year = all_ages_today()
    plan = plan_blocks()
    muni = set(json.load(open(MUNI, encoding="utf-8"))["blocks"])

    blocks = []
    for r in rows:
        cls, layer = r.get("classcode") or "0", r.get("layer") or ""
        walk = layer.startswith("STREETS_PEDESTRI")
        if not walk and (cls not in SURFACE or not (layer.startswith("STREETS") or layer.startswith("PARKS"))):
            continue
        g = r.get("line") or {}
        if g.get("type") != "LineString" or len(g.get("coordinates") or []) < 2:
            continue
        a, b = str(r.get("f_node_cnn") or "").split(".")[0], str(r.get("t_node_cnn") or "").split(".")[0]
        if not a or not b:
            continue
        blocks.append((str(r["cnn"]).split(".")[0], r, cls, layer, a, b, g["coordinates"]))
    blocks.sort(key=lambda x: int(x[0]))
    if len({b[0] for b in blocks}) != len(blocks):
        raise SystemExit("prepare: duplicate CNNs among the kept blocks")

    node_ix, node_xy = {}, []
    for _, _, _, _, a, b, co in blocks:
        for n, pt in ((a, co[0]), (b, co[-1])):
            if n not in node_ix:
                node_ix[n] = len(node_xy)
                node_xy.append(pt)

    cols = {k: [] for k in ("cnn", "name", "cls", "role", "why", "today", "lanes", "dir", "mph", "plan", "muni", "a", "b", "ft", "rated")}
    runs = []
    for cnn, r, cls, layer, a, b, co in blocks:
        p = plan.get(cnn, "")
        role, why = default_role(cls, layer, p)
        two_way = (r.get("oneway") or "B") == "B"
        per = lane.get(cnn) or 1
        mph = speed.get(cnn, 25)
        total_lanes = per * 2 if two_way else per
        rated = cnn in lts
        if rated:
            t = lts[cnn]
        else:
            t = mixed(mph, total_lanes, per, cls == "5")
        if cnn in aa:
            t = 1
        ft = sum(haversine_ft(co[i], co[i + 1]) for i in range(len(co) - 1))
        cols["cnn"].append(cnn)
        cols["name"].append(r.get("streetname") or "")
        cols["cls"].append(int(cls))
        cols["role"].append(ROLES.index(role))
        cols["why"].append(why)
        cols["today"].append(t)
        cols["lanes"].append(total_lanes)
        cols["dir"].append(per)
        cols["mph"].append(mph)
        cols["plan"].append(PLAN_CODE.get(p, ""))
        cols["muni"].append(1 if cnn in muni else 0)
        cols["a"].append(node_ix[a])
        cols["b"].append(node_ix[b])
        cols["ft"].append(round(ft))
        cols["rated"].append(1 if rated else 0)
        runs.append(co)

    # The nodes any ridden block touches, gridded for the nearest-corner search below.
    ridden = set()
    for i in range(len(cols["cnn"])):
        if cols["role"][i] != ROLES.index("walk"):
            ridden.add(cols["a"][i])
            ridden.add(cols["b"][i])
    grid = collections.defaultdict(list)
    CELL = 0.004
    for n in sorted(ridden):
        x, y = node_xy[n]
        grid[(int(x / CELL), int(y / CELL))].append(n)
    cb = json.load(open(BLOCKS, encoding="utf-8"))
    pairs, lodes_total, work_jobs = read_lodes(args.lodes)
    # Each block group meets the network at one corner for homes and one for jobs: the corner nearest its
    # residents' centre (Census 2020 block populations) and the one nearest its jobs' centre (LODES work blocks).
    centre = {"home": collections.defaultdict(lambda: [0.0, 0.0, 0.0]), "work": collections.defaultdict(lambda: [0.0, 0.0, 0.0])}
    for rec in cb["records"]:
        g = rec["geoid"][:12]
        for side, w in (("home", rec["pop"]), ("work", work_jobs.get(rec["geoid"], 0))):
            c = centre[side][g]
            c[0] += w * rec["lon"]; c[1] += w * rec["lat"]; c[2] += w
    def nearest(pt):
        gx, gy = int(pt[0] / CELL), int(pt[1] / CELL)
        best, bd, found_at = None, 1e18, None
        for rad in range(0, 12):
            for dx in range(-rad, rad + 1):
                for dy in range(-rad, rad + 1):
                    if max(abs(dx), abs(dy)) != rad:
                        continue
                    for n in grid.get((gx + dx, gy + dy), ()):
                        d = haversine_ft(pt, node_xy[n])
                        if d < bd:
                            best, bd = n, d
            # One ring past the first hit, so a nearer node just over a cell edge is not missed.
            if best is not None and found_at is None:
                found_at = rad
            elif found_at is not None:
                break
        return best, bd
    access = {"home": {}, "work": {}}
    far = 0
    for side in ("home", "work"):
        for g, (x, y, w) in centre[side].items():
            if w <= 0:
                continue
            n, d = nearest((x / w, y / w))
            if n is not None:
                access[side][g] = n
                far += d > 1000

    bgs = sorted({h for h, _ in pairs} | {w for _, w in pairs})
    bgs = [g for g in bgs if g in access["home"] or g in access["work"]]
    bix = {g: i for i, g in enumerate(bgs)}
    lodes_missing = 0
    by_origin = collections.defaultdict(list)
    for (h, w), n in sorted(pairs.items()):
        if h not in access["home"] or w not in access["work"]:
            lodes_missing += n
        elif h != w:
            by_origin[bix[h]].append([bix[w], n])

    meta = {
        "centerlines": "[DataSF 3psu-pn9h — queried %s]" % cl_read,
        "speed": "[DataSF 3t7b-gebn — queried %s]" % speed_read,
        "lanes": "[SFMTA MTA.CTA_trafficlanes — queried %s]" % lane_read,
        "bci": "[SFMTA Bike Comfort Index 2023 draft — queried %s]" % bci_read,
        "bikeways": "extended bikeway data, %s" % aa_year,
        "plan": "Biking and Rolling Plan, March 2025, North Star map traced to CNNs",
        "data_read": max(cl_read, bci_read, lane_read, speed_read),
    }
    streets = {"about": "Street Roles Map blocks, by tools/street-roles/street-roles.py. Columns are parallel lists; "
                        "role indexes roles; a and b index the network's nodes.",
               "roles": list(ROLES), "rules": ROLE_RULES, "plan_codes": {v: k for k, v in PLAN_CODE.items()},
               "nodes": len(node_xy), "meta": meta, "blocks": cols, "lines": encode_runs(runs)}
    commutes = {"about": "SF residents who work in SF, LEHD LODES 8 OD 2023 (S000), by home and work 2020 block "
                         "group. home[g] and work[g]: the network node a block group's homes and jobs meet "
                         "(null where it has none). pairs[o]: [work bg, commuters, shortest feet on every street "
                         "from o's home node to the work bg's work node] (feet added by route).",
                "lodes": {"file": "ca_od_main_JT00_2023.csv.gz", "sf_to_sf_jobs": lodes_total,
                          "jobs_in_unplaced_block_groups": lodes_missing},
                "bg": bgs, "home": [access["home"].get(g) for g in bgs], "work": [access["work"].get(g) for g in bgs],
                "pairs": [by_origin.get(i, []) for i in range(len(bgs))]}
    os.makedirs(SITE_DATA, exist_ok=True)
    stable.write_json(STREETS, streets, separators=(",", ":"))
    stable.write_json(COMMUTES, commutes, separators=(",", ":"))
    print("prepare: %d blocks, %d nodes, %d block groups, %d SF-to-SF commuters (%d in unplaced block groups), "
          "%d block group centres over 1,000 ft from a corner" % (len(cols["cnn"]), len(node_xy), len(bgs), lodes_total,
                                                                    lodes_missing, far))
    check()


# ---- route --------------------------------------------------------------------------------------------------------

def adjacency(streets, keep):
    n = streets["nodes"]
    B = streets["blocks"]
    adj = [[] for _ in range(n)]
    for i in range(len(B["cnn"])):
        if keep(i):
            a, b, w = B["a"][i], B["b"][i], max(1, B["ft"][i])
            adj[a].append((b, w))
            adj[b].append((a, w))
    return adj


def dijkstra(adj, sources, limit):
    dist = {}
    h = [(0, s) for s in sources]
    heapq.heapify(h)
    while h:
        d, u = heapq.heappop(h)
        if u in dist:
            continue
        dist[u] = d
        if d > limit:
            break
        for v, w in adj[u]:
            if v not in dist:
                heapq.heappush(h, (d + w, v))
    return dist


def figure(streets, commutes, stress):
    """(commuters connected at LOW, commuters in the window) for a list of block stress values (None: not ridden)."""
    adj = adjacency(streets, lambda i: stress[i] is not None and stress[i] <= LOW)
    conn = tot = 0
    for o, row in enumerate(commutes["pairs"]):
        if not any(r[2] is not None and TRIP_MIN_FT <= r[2] <= TRIP_MAX_FT for r in row):
            continue
        dist = dijkstra(adj, [commutes["home"][o]], TRIP_MAX_FT * DETOUR_RATIO + DETOUR_FT)
        for d, n, l4 in row:
            if l4 is None or not (TRIP_MIN_FT <= l4 <= TRIP_MAX_FT):
                continue
            tot += n
            lk = dist.get(commutes["work"][d])
            if lk is not None and (lk < DETOUR_RATIO * l4 or lk - l4 < DETOUR_FT):
                conn += n
    return conn, tot


def route(args):
    streets = json.load(open(STREETS, encoding="utf-8"))
    commutes = json.load(open(COMMUTES, encoding="utf-8"))
    B = streets["blocks"]
    walk = ROLES.index("walk")
    all_adj = adjacency(streets, lambda i: B["role"][i] != walk)
    for o, row in enumerate(commutes["pairs"]):
        dist = dijkstra(all_adj, [commutes["home"][o]], TRIP_MAX_FT * 2) if row else {}
        for r in row:
            l4 = dist.get(commutes["work"][r[0]])
            r[2:] = [None if l4 is None else int(round(l4))]
    stable.write_json(COMMUTES, commutes, separators=(",", ":"))

    n = len(B["cnn"])
    today = [None if B["role"][i] == walk else B["today"][i] for i in range(n)]
    net = [stress_with(ROLES[B["role"][i]], {"t": B["today"][i], "l": B["lanes"][i], "d": B["dir"][i], "s": B["mph"][i],
                                             "p": B["plan"][i], "m": B["muni"][i]}) for i in range(n)]
    c0, tot = figure(streets, commutes, today)
    c1, tot1 = figure(streets, commutes, net)
    assert tot == tot1
    miles = collections.Counter()
    for i in range(n):
        miles[ROLES[B["role"][i]]] += B["ft"][i] / MILE
    stress_miles = {"today": collections.Counter(), "network": collections.Counter()}
    for i in range(n):
        if today[i] is not None:
            stress_miles["today"][str(today[i])] += B["ft"][i] / MILE
            stress_miles["network"][str(net[i])] += B["ft"][i] / MILE
    why = collections.Counter()
    for i in range(n):
        why[B["why"][i]] += B["ft"][i] / MILE
    summary = {
        "about": "Street Roles Map default figures, by tools/street-roles/street-roles.py route.",
        "data_read": streets["meta"]["data_read"],
        "commuters_in_window": tot,
        "connected_today": c0, "connected_network": c1,
        "share_today": round(c0 / tot, 4), "share_network": round(c1 / tot, 4),
        "sf_to_sf_jobs": commutes["lodes"]["sf_to_sf_jobs"],
        "miles_by_role": {k: round(miles[k], 1) for k in ROLES},
        "miles_by_rule": {k: round(why[k], 1) for k in sorted(why)},
        "miles_by_stress": {k: {s: round(v[s], 1) for s in sorted(v)} for k, v in stress_miles.items()},
        "blocks": n,
        "unrated_blocks": n - sum(B["rated"]),
    }
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(SUMMARY, summary, indent=1)
    print(json.dumps(summary, indent=1))
    check()


# ---- checks -------------------------------------------------------------------------------------------------------

def check():
    """Row counts, required fields, key uniqueness and joins. Raises on a failure, so a bad build stops here."""
    s = json.load(open(STREETS, encoding="utf-8"))
    c = json.load(open(COMMUTES, encoding="utf-8"))
    B = s["blocks"]
    n = len(B["cnn"])
    fails = []
    if n < 14000:
        fails.append("only %d blocks, below the floor of 14,000" % n)
    for k, v in B.items():
        if len(v) != n:
            fails.append("column %s has %d rows, not %d" % (k, len(v), n))
    if len(set(B["cnn"])) != n:
        fails.append("CNNs are not unique")
    if any(t not in (1, 2, 3, 4) for t in B["today"]):
        fails.append("a block's stress today is outside 1 to 4")
    if any(not (0 <= a < s["nodes"]) for a in B["a"] + B["b"]):
        fails.append("a block names a node outside the node list")
    if sum(s["lines"]["n"]) < 2 * n or len(s["lines"]["n"]) != n:
        fails.append("geometry runs don't match the blocks")
    joins = {"plan": sum(1 for v in B["plan"] if v), "muni": sum(B["muni"])}
    if joins["plan"] < 2800 or joins["muni"] < 4000:
        fails.append("too few blocks joined the plan network (%d) or the Muni streets (%d)" % (joins["plan"], joins["muni"]))
    if any(v < 1 for v in B["dir"]) or any(not (5 <= v <= 65) for v in B["mph"]):
        fails.append("a block's lanes a direction or speed limit is out of range")
    rated = sum(B["rated"]) / n
    if rated < 0.9:
        fails.append("only %.0f%% of blocks have a Bike Comfort Index rating" % (100 * rated))
    if len(c["bg"]) < 500 or len(c["bg"]) != len(c["home"]) or len(c["bg"]) != len(c["work"]) or len(c["bg"]) != len(c["pairs"]):
        fails.append("block group lists disagree or are short (%d)" % len(c["bg"]))
    placed = c["lodes"]["sf_to_sf_jobs"] - c["lodes"]["jobs_in_unplaced_block_groups"]
    paired = sum(r[1] for row in c["pairs"] for r in row)
    if c["lodes"]["sf_to_sf_jobs"] < 200000:
        fails.append("only %d SF-to-SF commuters in LODES" % c["lodes"]["sf_to_sf_jobs"])
    if paired > placed:
        fails.append("pairs hold more commuters (%d) than LODES placed (%d)" % (paired, placed))
    if os.path.exists(SUMMARY):
        m = json.load(open(SUMMARY, encoding="utf-8"))
        if m["commuters_in_window"] < 150000:
            fails.append("only %d commuters in the half-mile to 6-mile window" % m["commuters_in_window"])
        if not (0 < m["connected_today"] <= m["connected_network"] <= m["commuters_in_window"] <= placed):
            fails.append("figures out of order: today %d, network %d, window %d, placed %d" % (
                m["connected_today"], m["connected_network"], m["commuters_in_window"], placed))
    if fails:
        raise SystemExit("street-roles check failed:\n  " + "\n  ".join(fails))
    print("street-roles check: %d blocks, %d block groups, %d commuters paired, all checks pass" % (n, len(c["bg"]), paired))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--lodes", required=True, help="ca_od_main_JT00_2023.csv.gz")
    sub.add_parser("route")
    sub.add_parser("check")
    a = ap.parse_args()
    {"prepare": prepare, "route": route, "check": lambda _a: check()}[a.cmd](a)


if __name__ == "__main__":
    main()
