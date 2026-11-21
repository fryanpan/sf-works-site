#!/usr/bin/env python3
"""Where School Trips' three speed changes on the streets near each school would go: 20 mph business districts on main streets, speed humps on residential side streets, and new speed cameras on main streets.

    tools/school-trips/school-speed-levers.py       # writes data/school-sim/speed-levers.json

Bryan, 2026-10-15, on the evidence doc: "BAD with lower speed limit, humps separately, and cameras with raised limit
separately too". tools/school-trips/school-kids-hurt.py reads this file and counts the kids hurt each change acts on, school by
school; site/src/school-trips-model.mjs prices and credits them.

MAIN AND RESIDENTIAL STREETS. One rule for every piece of School Trips that splits main from residential: a street
is a main street when OpenStreetMap ranks it tertiary or above anywhere in SF, by name (tools/school-trips/school-calm-priority.py's
street_ranks), the rule tools/school-trips/school-kids-hurt.py labels each kid's crash by. DataSF's own classcode in 3psu-pn9h
(Streets, active blocks) leaves Valencia, Clement, Polk and Post as residential (5), so it can't be the test while
the kids are labelled from OpenStreetMap. Blocks come from 3psu-pn9h, classcode 2 to 5 (city streets; 0 is private and
paper streets, 1 and 6 freeways and ramps). A main street block is one of those on a main street; a residential block
is classcode 5 on a street OpenStreetMap ranks residential, living or unclassified.

DISTANCE. Feet from a block's line to a school's grounds, measured from the edge of the grounds as California's
school-zone law measures it (lib/school_grounds.py), at the schools in site/data/school-sim/index.json (public, charter and private).
Each block goes to its nearest school, so no block is counted twice.

BUSINESS ACTIVITY DISTRICTS (Vehicle Code 22358.9, AB 43). A main street block at least HUMP_MIN_FT long within a quarter mile of a
school, and outside its ZONE_FT school zone, is a candidate when it has at least BAD_PER_100FT retail or dining business addresses per 100 ft of its length,
each address point counted once, so a mall's or a stadium's dozens of registrations at one point count as one. Businesses are
DataSF g8m3-pdis (Registered Business Locations), open (no location or DBA end date, not administratively closed), in
San Francisco, with a self-reported NAICS code in retail (44, 45) or food service (722), whose address is on the
block's own street and lies within BIZ_FT of its line ("S VAN NESS" read as SOUTH VAN NESS, a street with no suffix
as that street). One of the statute's tests is half the frontage in retail or dining; the
registry can't measure frontage, so the floor is set where SF's own lowered blocks sit: the share of the main street
blocks SFMTA has posted at 20 mph since 2022 that reach it is printed and kept. A block already posted at 20 mph or
lower, or above 25 mph (the statute lets a 20 mph district follow only a 25 mph limit), in DataSF 3t7b-gebn, is left
out. Contiguous candidate blocks on one street at one school are one corridor, the unit SFMTA prices its signs by. The
statute's other tests (at most four lanes, parking, signals every 600 ft) aren't checked here.

SPEED HUMPS. Residential blocks within LAST_BLOCK_FT (one block) of a school's grounds, without a speed hump, cushion,
table or bump already built or awaiting construction in DataSF abhw-ffzx (Mid-Block Traffic Calming Areas), get one
hump per HUMP_SPACING_FT of length, at least one. Tunnels and ramps (3psu st_type TUNL, RAMP) and blocks longer than
HUMP_MAX_FT (Twin Peaks Boulevard's) are left out.

SPEED CAMERAS. Schools with none of SF's existing camera locations within ZONE_FT of their grounds (DataSF d5uh-bk84,
Automated Speed Enforcement Citations, its sites, two directions at one place counted as one location: within
CAM_SAME_FT, or on the same street within CAM_PAIR_FT) and a main
street within ZONE_FT get one camera: on the main street within ZONE_FT whose blocks there carry the most length,
at the point of that street nearest the grounds. tools/school-trips/school-kids-hurt.py credits it with the kids hurt on that
street within a quarter mile of the camera, NYC's camera corridor.

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build read by the School Trips pages through school-kids-hurt.py. It reads
cached DataSF queries through lib/sfdata.py, which refetches when its cache is stale. In
pipeline/transportation-update.py before school-kids-hurt.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata
from lib import school_grounds
from lib import school_points

import numpy as np
from shapely import LineString, Point, STRtree

OUT = os.path.join(ROOT, "data", "school-sim", "speed-levers.json")
ZONE_FT, NEAR_FT, LAST_BLOCK_FT = 500, 1320, 350
CITY_CLASS = {"2", "3", "4", "5"}   # 3psu classcodes for city streets
BAD_PER_100FT = 1.0     # retail or dining businesses per 100 ft of block, both sides
BIZ_FT = 150            # a business's point to its block's line
HUMP_SPACING_FT = 300   # one hump per this many feet of block, at least one
CAM_SAME_FT = 200       # camera sites closer than this are one location
CAM_PAIR_FT = 800       # two directions' sites on one street closer than this are one location
HUMP_MAX_FT = 1000      # a block longer than this isn't a side street block (Twin Peaks Boulevard)
HUMP_KINDS = ("hump", "cushion", "table", "bump")
HUMP_MIN_FT = 150       # a block shorter than this is a stub, with no room for a hump
CAM_SPACING_FT = 660    # a new camera this close to another on the same street shares it
OSM_FT = 70             # a block's midpoint to the OpenStreetMap ways it is matched to
DRIVE = os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")
FX, FY = school_grounds.FT_LON, school_grounds.FT_LAT

calm = paths.load("school-calm-priority.py", "calm")

BIZ_WHERE = ("location_end_date IS NULL AND dba_end_date IS NULL AND administratively_closed IS NULL AND location IS NOT "
             "NULL AND city='San Francisco' AND (starts_with(self_reported_naics_code,'44') OR "
             "starts_with(self_reported_naics_code,'45') OR starts_with(self_reported_naics_code,'722'))")


def cnn_of(v):
    return str(v or "").split(".")[0].lstrip("0")


def blocks():
    """Every active block as {cnn, name, cls, pts (lon, lat), ls (feet)}."""
    r = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,classcode,line", where="active='true'", floor=15000)
    out = []
    for row in r.rows:
        g, c = row.get("line"), cnn_of(row.get("cnn"))
        if not c or not isinstance(g, dict):
            continue
        parts = [g.get("coordinates")] if g.get("type") == "LineString" else (g.get("coordinates") or [])
        pts = max((q for q in parts if q and len(q) >= 2), key=len, default=None)
        if not pts:
            continue
        name = (row.get("streetname") or "%s %s" % (row.get("street") or "", row.get("st_type") or "")).strip()
        out.append({"cnn": c, "name": calm.norm(name), "label": name, "cls": str(row.get("classcode") or ""),
                    "type": str(row.get("st_type") or "").upper(),
                    "pts": [(round(x, 6), round(y, 6)) for x, y in pts], "ls": LineString([(x * FX, y * FY) for x, y in pts])})
    return out, r.tag


def osm_mains():
    """OpenStreetMap's named main street ways (tertiary and above, no ramps) as (name, highway, lanes or None, oneway,
    line in feet), from the drive network, for the two statute tests the city's block file can't answer: whether a
    block is a state highway (trunk), and its lanes."""
    out = []
    els = json.load(open(DRIVE))["elements"]
    at = {e["id"]: (e["lon"], e["lat"]) for e in els if e["type"] == "node"}
    for e in els:
        t = e.get("tags", {}) if e["type"] == "way" else {}
        hw = t.get("highway") or ""
        if hw not in ("trunk", "primary", "secondary", "tertiary") or not t.get("name"):
            continue
        pts = [at[n] for n in e["nodes"] if n in at]
        if len(pts) < 2:
            continue
        try:
            L = int(str(t.get("lanes", "")).split(";")[0])
        except ValueError:
            L = None
        # A state route mapped below trunk (Van Ness Avenue carries US 101 as a primary) is still Caltrans's.
        state = hw == "trunk" or bool(re.match(r"^(US|CA|SR|I)[ -]?\d", t.get("ref") or ""))
        out.append((calm.norm(t["name"]), "trunk" if state else hw, L, t.get("oneway") == "yes", LineString([(x * FX, y * FY) for x, y in pts])))
    return out


def block_osm(osm, tree, b):
    """(state highway, lanes or None) for a block: OpenStreetMap's same-named main ways within OSM_FT of its midpoint.
    A divided street is two one-way ways, so one-way lanes add up; a two-way way gives its own count."""
    m = b["ls"].interpolate(0.5, normalized=True)
    hits = [osm[k] for k in tree.query(m, predicate="dwithin", distance=OSM_FT) if osm[k][0] == b["name"]]
    state = any(h[1] == "trunk" for h in hits)
    two = [h[2] for h in hits if not h[3] and h[2] is not None]
    one = [h[2] for h in hits if h[3] and h[2] is not None]
    lanes = max(two) if two else (sum(one) if one else None)
    return state, lanes


DIRS = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}


def osm_form(name):
    """A 3psu street name in OpenStreetMap's spelling, for its rank: 3psu spells Bayshore Boulevard BAY SHORE."""
    return name.replace("BAY SHORE", "BAYSHORE")


def street_of(addr):
    """The street of a business address, in calm.norm's form, without its house number, with a leading N, S, E or W
    spelled out as 3psu spells it (S VAN NESS AVE is SOUTH VAN NESS AVE) and BAYSHORE as 3psu's BAY SHORE."""
    w = calm.norm(addr).split()
    while w and re.match(r"^\d+[A-Z]?$", w[0]):
        w = w[1:]
    if len(w) > 1 and w[0] in DIRS:
        w[0] = DIRS[w[0]]
    return " ".join(w).replace("BAYSHORE", "BAY SHORE")


def on_street(s, name):
    """A business street s is on block street name: the same, the same plus a unit, or name without its suffix."""
    return s == name or s.startswith(name + " ") or (" " in name and s == name.rsplit(" ", 1)[0])


def nearest_schools(sch, B, idx):
    """{block index: (school index, feet)} for the blocks in idx whose line comes within a quarter mile of a school's
    grounds, by points every 50 ft along the line."""
    xs, ys, own = [], [], []
    for i in idx:
        ls = B[i]["ls"]
        for t in np.linspace(0, 1, max(2, int(ls.length // 50) + 2)):
            p = ls.interpolate(t, normalized=True)
            xs.append(p.x / FX); ys.append(p.y / FY); own.append(i)
    j, d = school_grounds.nearest([(s["lon"], s["lat"]) for s in sch], xs, ys, NEAR_FT)
    out = {}
    for i, jj, dd in zip(own, j, d):
        if jj >= 0 and (i not in out or dd < out[i][1]):
            out[i] = (int(jj), float(dd))
    return out


def main():
    sch = school_points.index_schools()
    B, tag_st = blocks()
    ranks = calm.street_ranks()
    rank = lambda b: ranks.get(osm_form(b["name"]), 0)
    is_main = lambda b: b["cls"] in CITY_CLASS and rank(b) >= 2
    is_res = lambda b: b["cls"] == "5" and rank(b) == 1
    SL = sfdata.fetch("3t7b-gebn", select="cnn,speedlimit,schoolzone,mtab_date", floor=3000)
    lim = {cnn_of(r.get("cnn")): r for r in SL.rows}
    BZ = sfdata.fetch("g8m3-pdis", select="uniqueid,full_business_address,self_reported_naics_code,location", where=BIZ_WHERE, floor=3000)
    TC = sfdata.fetch("abhw-ffzx", select="cnn,tc_measure,current_status", floor=500)
    CAM = sfdata.fetch("d5uh-bk84", select="distinct site_id, location, latitude, longitude", order="site_id", floor=30)

    # Each block's nearest school, for blocks within a quarter mile of one.
    # A cheap box first: blocks with a point within about a third of a mile of a school's point.
    sxy = np.array([(s["lon"] * FX, s["lat"] * FY) for s in sch])
    from scipy.spatial import cKDTree
    st = cKDTree(sxy)
    cand_i = [i for i, b in enumerate(B) if b["cls"] in CITY_CLASS
              and st.query(np.array(b["ls"].coords), distance_upper_bound=NEAR_FT + 2000)[0].min() < np.inf]
    near = nearest_schools(sch, B, cand_i)

    # ---- business activity districts ----
    mains = [i for i, b in enumerate(B) if is_main(b)]
    tree = STRtree([B[i]["ls"] for i in mains])
    biz = collections.defaultdict(set)
    matched = 0
    for row in BZ.rows:
        x, y = row["location"]["coordinates"]
        p, s = Point(x * FX, y * FY), street_of(row.get("full_business_address") or "")
        hit = None
        for k in tree.query(p, predicate="dwithin", distance=BIZ_FT):
            b = B[mains[k]]
            if on_street(s, b["name"]):
                d = b["ls"].distance(p)
                if hit is None or d < hit[0]:
                    hit = (d, mains[k])
        if hit:
            biz[hit[1]].add((round(x, 5), round(y, 5)))
            matched += 1
    dens = lambda i: 100 * len(biz[i]) / max(B[i]["ls"].length, 1)
    posted = lambda i: (lim.get(B[i]["cnn"]) or {}).get("speedlimit") or "0"
    # SF's own lowered main street blocks: posted 20 mph since 2022, outside school zones.
    lowered = [i for i in mains if posted(i) == "20" and ((lim.get(B[i]["cnn"]) or {}).get("mtab_date") or "")[:4] >= "2022"
               and (lim.get(B[i]["cnn"]) or {}).get("schoolzone") != "YES"]
    lowered_pass = sum(1 for i in lowered if dens(i) >= BAD_PER_100FT) / max(1, len(lowered))
    # Posted 0 is unposted, the 25 mph default.
    # A block inside a school zone is left out (Bryan, 2026-10-15: "BAD are only needed outside of the 500 ft school
    # zone"): within ZONE_FT of the grounds, or flagged in SFMTA's speed limits as a school zone.
    in_zone = lambda i: near[i][1] <= ZONE_FT or (lim.get(B[i]["cnn"]) or {}).get("schoolzone") == "YES"
    dense_all = [i for i in mains if i in near and B[i]["ls"].length >= HUMP_MIN_FT and dens(i) >= BAD_PER_100FT
                 and posted(i) in ("0", "25")]
    dense = [i for i in dense_all if not in_zone(i)]
    # The statute's lane cap and state highways (Caltrans sets their limits), from OpenStreetMap.
    osm = osm_mains()
    otree = STRtree([o[4] for o in osm])
    ox = {i: block_osm(osm, otree, B[i]) for i in mains if i in near}
    cand = [i for i in dense if not ox[i][0] and (ox[i][1] is None or ox[i][1] <= 4)]
    bad_drop = {"schoolZone": len(dense_all) - len(dense), "stateHighway": sum(1 for i in dense if ox[i][0]),
                "overFourLanes": sum(1 for i in dense if not ox[i][0] and ox[i][1] is not None and ox[i][1] > 4),
                "lanesUnknown": sum(1 for i in cand if ox[i][1] is None)}
    # Corridors: contiguous candidate blocks on one street at one school (ends within 30 ft).
    parent = {i: i for i in cand}
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    ends = {i: [B[i]["ls"].coords[0], B[i]["ls"].coords[-1]] for i in cand}
    by = collections.defaultdict(list)
    for i in cand:
        by[(B[i]["name"], near[i][0])].append(i)
    for grp in by.values():
        for a in grp:
            for b in grp:
                if a < b and min(np.hypot(p[0] - q[0], p[1] - q[1]) for p in ends[a] for q in ends[b]) <= 30:
                    parent[root(a)] = root(b)
    cors = collections.defaultdict(list)
    for i in cand:
        cors[root(i)].append(i)
    corridors = sorted(([B[i]["cnn"] for i in sorted(g, key=lambda i: B[i]["cnn"])] for g in cors.values()))
    cor_of = {c: n for n, g in enumerate(corridors) for c in g}
    bad_blocks = [{"cnn": B[i]["cnn"], "street": B[i]["name"], "label": B[i]["label"], "cds": sch[near[i][0]]["cds"],
                   "ft": round(B[i]["ls"].length), "biz": len(biz[i]), "posted": int(posted(i)) or 25, "corridor": cor_of[B[i]["cnn"]],
                   "lanes": ox[i][1], "pts": B[i]["pts"]} for i in sorted(cand, key=lambda i: B[i]["cnn"])]

    # ---- speed humps ----
    calmed = collections.defaultdict(set)
    for r in TC.rows:
        m, st = (r.get("tc_measure") or "").lower(), (r.get("current_status") or "").lower()
        if any(k in m for k in HUMP_KINDS) and ("complete" in st or "construction" in st):
            calmed[cnn_of(r.get("cnn"))].add(m)
    hump_blocks, has_hump = [], 0
    for i, b in enumerate(B):
        # Residential (5) only: classcode 0 is private and paper streets, which the City doesn't build on.
        # Not tunnels or ramps (the Broadway tunnel is a 3psu class 5 block), and not a mile of Twin Peaks Boulevard.
        if not is_res(b) or b["type"] in ("TUNL", "RAMP") or i not in near or near[i][1] > LAST_BLOCK_FT \
                or not HUMP_MIN_FT <= b["ls"].length <= HUMP_MAX_FT:
            continue
        if b["cnn"] in calmed:
            has_hump += 1
            continue
        L = b["ls"].length
        hump_blocks.append({"cnn": b["cnn"], "street": b["name"], "label": b["label"], "cds": sch[near[i][0]]["cds"],
                            "ft": round(L), "humps": max(1, int(round(L / HUMP_SPACING_FT))), "pts": b["pts"]})
    hump_blocks.sort(key=lambda h: h["cnn"])

    # ---- speed cameras ----
    sites = []
    for r in CAM.rows:
        try:
            lo, la = float(r["longitude"]), float(r["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        sites.append((lo, la, re.sub(r"^(NB|SB|EB|WB)\s+", "", r.get("location") or "")))
    locs = []
    for lo, la, nm in sorted(sites):
        g = lambda a, b: np.hypot((lo - a) * FX, (la - b) * FY)
        if not any(g(a, b) <= CAM_SAME_FT or (street_of(n) == street_of(nm) and g(a, b) <= CAM_PAIR_FT) for a, b, n in locs):
            locs.append((lo, la, nm))
    cam_near = set()
    for lo, la, nm in locs:
        for s in sch:
            if school_grounds.dist_ft(s["lon"], s["lat"], lo, la) <= ZONE_FT:
                cam_near.add(s["cds"])
    zone_main = collections.defaultdict(lambda: collections.defaultdict(float))
    for i in mains:
        # State highways are Caltrans's, so a camera there isn't the City's to place.
        if i in near and near[i][1] <= ZONE_FT and not ox[i][0]:
            zone_main[sch[near[i][0]]["cds"]][B[i]["name"]] += B[i]["ls"].length
    cameras, shared, by_existing = [], [], []
    ex_street = [(lo, la, street_of(nm)) for lo, la, nm in locs]
    for s in sorted(sch, key=lambda s: s["cds"]):
        if s["cds"] in cam_near or not zone_main[s["cds"]]:
            continue
        zm = zone_main[s["cds"]]
        street = max(sorted(zm), key=lambda n: zm[n])
        best = None
        for i in mains:
            if B[i]["name"] != street or i not in ox or ox[i][0]:
                continue
            xs = np.array([p[0] for p in B[i]["pts"]]); ys = np.array([p[1] for p in B[i]["pts"]])
            # Sample the line every 25 ft so the point nearest the grounds isn't only a block end.
            n = max(2, int(B[i]["ls"].length // 25) + 1)
            q = [B[i]["ls"].interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
            qx, qy = np.array([p.x / FX for p in q]), np.array([p.y / FY for p in q])
            d = school_grounds.dist_ft(s["lon"], s["lat"], qx, qy)
            k = int(np.argmin(d))
            if best is None or d[k] < best[0]:
                best = (float(d[k]), round(float(qx[k]), 6), round(float(qy[k]), 6))
        cam = {"cds": s["cds"], "street": street, "lon": best[1], "lat": best[2], "ft": round(best[0])}
        gap = lambda a, b: float(np.hypot((a[0] - b[0]) * FX, (a[1] - b[1]) * FY))
        # An existing camera on the same street within its quarter-mile corridor already covers this stretch, and a
        # new one within CAM_SPACING_FT of another school's new camera on the same street is that camera.
        if any(st_ == street and gap((lo, la), (cam["lon"], cam["lat"])) <= NEAR_FT for lo, la, st_ in ex_street):
            by_existing.append(s["cds"])
            continue
        if any(c["street"] == street and gap((c["lon"], c["lat"]), (cam["lon"], cam["lat"])) <= CAM_SPACING_FT for c in cameras):
            shared.append(s["cds"])
            continue
        cameras.append(cam)

    # Quality: the reads are whole, the floor sits inside SF's own lowered blocks, each output is plausible.
    assert matched > 2000, "%d businesses matched a main street block: the address match is off" % matched
    assert len(lowered) > 200 and 0.3 < lowered_pass < 0.9, "lowered blocks %d, pass %.2f" % (len(lowered), lowered_pass)
    assert 28 <= len(locs) <= 35, "%d camera locations: AB 645 allows 33" % len(locs)
    assert 50 < len(bad_blocks) < 1500 and 50 < len(hump_blocks) < 3000 and 20 < len(cameras) <= len(sch)
    assert len({b["cnn"] for b in bad_blocks}) == len(bad_blocks) and len({h["cnn"] for h in hump_blocks}) == len(hump_blocks)
    out = {
        "note": "Written by tools/school-trips/school-speed-levers.py. Where School Trips' 20 mph business districts, speed humps and new "
                "speed cameras would go near the %d schools: main street blocks (OpenStreetMap tertiary or above, DataSF 3psu-pn9h) with "
                "retail or dining businesses (g8m3-pdis) within a quarter mile, not already at 20 mph or above 25 mph (3t7b-gebn); "
                "residential blocks (classcode 5, OpenStreetMap residential) within %d ft without a hump (abhw-ffzx); one camera on the longest main "
                "street within %d ft of each school with no camera location (d5uh-bk84) within %d ft. Each block at its nearest "
                "school's grounds." % (len(sch), LAST_BLOCK_FT, ZONE_FT, ZONE_FT),
        "sources": {"streets": tag_st, "limits": SL.tag, "business": BZ.tag, "calming": TC.tag, "cameras": CAM.tag},
        "bad": {"perHundredFt": BAD_PER_100FT, "loweredBlocks": len(lowered), "loweredPass": round(lowered_pass, 3),
                "businessesMatched": matched, "corridors": len(corridors), "dropped": bad_drop, "blocks": bad_blocks},
        "humps": {"spacingFt": HUMP_SPACING_FT, "reachFt": LAST_BLOCK_FT, "alreadyHumped": has_hump, "blocks": hump_blocks},
        "cameras": {"existing": [{"lon": round(a, 6), "lat": round(b, 6), "location": n} for a, b, n in locs],
                    "schoolsNearExisting": sorted(cam_near), "coveredByExisting": sorted(by_existing),
                    "sharedWithNeighbour": sorted(shared), "new": cameras},
    }
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print("school-speed-levers: business districts %d blocks in %d corridors at %d schools (floor %.1f a 100 ft, %.0f%% of %d "
          "lowered blocks pass); humps %d on %d blocks at %d schools (%d blocks already humped); cameras %d new, %d existing "
          "locations, %d schools beside one" % (len(bad_blocks), len(corridors), len({b["cds"] for b in bad_blocks}), BAD_PER_100FT,
          100 * lowered_pass, len(lowered), sum(h["humps"] for h in hump_blocks), len(hump_blocks), len({h["cds"] for h in hump_blocks}),
          has_hump, len(cameras), len(locs), len(cam_near)))
    print("  business districts dropped: %s; cameras: %d schools covered by an existing camera's corridor, %d sharing a "
          "neighbour's" % (bad_drop, len(by_existing), len(shared)))


if __name__ == "__main__":
    main()
