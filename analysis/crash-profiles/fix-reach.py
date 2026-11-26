#!/usr/bin/env python3
"""Where SF's injury crashes happen, by the kind of place a fix acts on: each size_families group's people hurt and KSI people at signalized and unsignalized corners, all-way stops, the High Injury Network, each street class and stress level, school zones, Slow Streets, 20 mph blocks, speed camera corridors, candidate low-traffic cells, night and day, by turn movement, and SF's count of each kind of place.

    python3 analysis/crash-profiles/fix-reach.py      # 2017-2024, writes out/crash-augment/profiles/fix-reach.json

fix-map.py reads it to give a fix the share of a group that sits where the fix goes, and to multiply a per-unit cost
by SF's count of those places. Standard library only. A run with every source held makes no request and writes the
same bytes. One-off analysis behind the fix map; no page reads it on a schedule, so the incremental-updater rule does
not apply yet.

INPUTS
  crashes, parties, victims  out/crash-augment/tables/ (pipeline/crash-augment), 2017-2024 by collision_datetime,
                     read and grouped exactly as crash-profiles.py does (its load(), at-fault party, mode,
                     VIOLATION_FINE family and MOVEMENT_FINE movement are imported from it), so every family total
                     here equals size_families.families in results.json; the run stops if one does not.
  streets, signals, speed limits, Slow Streets, cameras   the street lane's held copies (street_sources.held()) of
                     DataSF 3psu-pn9h, ybh5-27n2, 3t7b-gebn, hkz3-itiu and d5uh-bk84, the copies the crash table's
                     street columns were built from.
  lanes              the street lane's held SFMTA MTA.CTA_trafficlanes layer (.cache/crash-augment/street/lanes.json).
  bike stress        data/extract/sfmta-bci/scores.json (SFMTA 2023 draft Bike Comfort Index), crash-profiles' rule.
  HIN                DataSF enwt-3u8m (2024 High Injury Network) and 8vtn-qytr (2022), one row per block repeated up
                     to five times, deduplicated on cnn_sgmt_pkey; miles are the agency's corrected_length_miles.
  stop signs         DataSF 4542-gpa3, one row per sign with the intersection CNN it stands at and the direction of
                     traffic it stops (st_facing). Rows with status L (legislated, not yet installed) are left out.
  schools            DataSF 7e7j-59qk (Schools, 2026), status Active, every entity type but Preschool.
  DataSF reads go through lib/sfdata.py into data/socrata-cache/ (gitignored) and carry their read date.

PLACE CLASSES (one crash can be in several). A crash is at an intersection when the police code it "Intersection"
  (within 20 ft, or a rear end within 150 ft), else midblock. Its node is cnn_intrsctn_fkey; its blocks are the street
  lane's street_block_cnns. Every class is today's state of the street, not the state on the crash date, because a
  fix's reach is the crashes at the places it would go now.
  signalized         at an intersection whose node has a signal in ybh5-27n2 today (types as the street lane counts).
  unsignalized       at an intersection with no signal.
  all_way_stop       unsignalized, and the node's stop signs face at least as many directions as there are blocks
                     meeting at the node (active surface blocks of 3psu-pn9h). A one-way street needs no sign on its
                     outgoing side, so this misses some all-way stops on one-way streets: a floor.
  stop_controlled    unsignalized with at least one stop sign; uncontrolled: unsignalized with none.
  arterial_corner    at an intersection where an arterial or major street meets (corner_type).
  arterial, collector, residential   the crash's street_class (major counts as arterial).
  high_stress, low_stress   the crash's most stressful block is LTS 3-4, or 1-2 (crash-profiles' crash_stress).
  multilane          the crash's blocks carry 2 or more lanes off-peak (the crash table's lanes column; on two-way
                     streets the layer counts one direction).
  hin, hin2022       on the 2024 (or 2022) HIN: a midblock crash on a HIN block, or a crash at an intersection whose
                     node ends a HIN block. Blocks are matched by CNN; the 2024 layer's dual-carriageway rows, whose id
                     is not a centerline CNN and whose street name is blank, take every centerline block whose midpoint
                     and both ends are within HIN_MATCH_FT (120 ft) of the row's line. A node counts only as the end
                     of a matched block.
  school_zone        the crash point (tb_latitude, tb_longitude) within SCHOOL_FT (500 ft) of a school's point.
  slow_street        one of the crash's blocks is an Implemented Slow Street block (hkz3-itiu, any date).
  limit20            one of the crash's blocks is posted 20 mph today (3t7b-gebn speedlimit 20, status not L).
  unposted           every block the crash is on is unposted today (3t7b-gebn speedlimit 0, the 25 mph default).
  camera_corridor    the crash is in a speed camera corridor, the street lane's rule (the site's block and the next
                     block of the same street each way, and their intersections), any date.
  ltn_cell           inside a candidate low-traffic cell: every block it is on is residential or collector and LTS 1
                     or 2 (a block with no BCI score counts only if residential), and, at an intersection, no block
                     meeting the node is a boundary block. A cell is a connected set of such blocks joined at nodes no
                     boundary block touches, where a boundary block is any other active surface block (an arterial,
                     major, freeway or high-stress street). Only cells with at least CELL_MIN_MILES of street count.
  dark, daylight, dusk   the crash's lighting (Dark - *, Daylight, Dusk - Dawn).
  late_night, evening    crash-profiles' time bands, 11 pm-6 am and 7-11 pm.
  Compound classes: reach.json beside the lanes may name a place as an expression over the classes, "&" for and, "|"
  for or (and binds first), "!" for not, e.g. "signalized&hin" or "residential|collector". Each expression it names is
  computed here too, so after editing reach.json this script runs before fix-map.py.

OUTPUT, out/crash-augment/profiles/fix-reach.json
  groups[family]       people hurt and KSI people, then for each place class (and each reach.json expression) its
                       people hurt, KSI people and shares of the group, and by_movement: the same by MOVEMENT_FINE
                       movement (movements with nobody hurt are left out).
  units                SF's count of each kind of place, with its source and how it was counted.
  checks               family totals against results.json, and how many crashes each class could be read for.
Every figure is a count of police-reported injury crashes and the people in them.
"""

import collections
import importlib.util
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "crash-augment", "street"))

_spec = importlib.util.spec_from_file_location("crash_profiles", os.path.join(HERE, "crash-profiles.py"))
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)

import sfdata  # noqa: E402
import street_sources  # noqa: E402
from street_fields import Context, ROAD_CLASS, SIGNAL_TYPES, street_key, day  # noqa: E402
from street_geo import feet_to_line, line_coords  # noqa: E402

OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "fix-reach.json")
RESULTS = os.path.join(ROOT, "out", "crash-augment", "profiles", "results.json")
REACH = os.path.join(HERE, "fixes", "reach.json")
LANES = os.path.join(ROOT, ".cache", "crash-augment", "street", "lanes.json")
YEARS = (2017, 2024)
SCHOOL_FT = 500
CELL_MIN_MILES = 0.5
HIN_MATCH_FT = 120  # a divided street's two sides sit about 40 to 100 ft from its centerline
FT_PER_DEG_LAT = 364000.0
SURFACE = ("arterial", "major", "collector", "residential")

BASE = ["intersection", "midblock", "signalized", "unsignalized", "all_way_stop", "stop_controlled", "uncontrolled",
        "arterial_corner", "arterial", "collector", "residential", "high_stress", "low_stress", "multilane", "hin",
        "hin2022", "school_zone", "slow_street", "limit20", "unposted", "camera_corridor", "ltn_cell", "dark", "daylight", "dusk",
        "late_night", "evening"]


def cnn(v):
    s = str(v or "").split(".")[0].strip()
    return s or None


# ---- place expressions ---------------------------------------------------------------------------------------

def evaluate(expr, tags):
    """expr over tag names: '|' or, '&' and (binds first), '!' not."""
    for alt in expr.split("|"):
        ok = True
        for term in alt.split("&"):
            term = term.strip()
            neg = term.startswith("!")
            name = term[1:] if neg else term
            if name not in BASE:
                raise ValueError("unknown place class %r in %r" % (name, expr))
            if (name in tags) == neg:
                ok = False
                break
        if ok:
            return True
    return False


def reach_expressions():
    if not os.path.exists(REACH):
        return []
    with open(REACH, encoding="utf-8") as f:
        d = json.load(f)
    ex = set()
    for k, v in d.get("fixes", {}).items():
        for p in [v.get("place")] + [g.get("place") for g in (v.get("by_group") or {}).values()]:
            if p and p not in BASE:
                ex.add(p)
    return sorted(ex)


# ---- network ------------------------------------------------------------------------------------------------

def miles_of(lines):
    length = 0.0
    for line in lines:
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            dx = (x2 - x1) * math.cos(math.radians((y1 + y2) / 2)) * 69.172
            dy = (y2 - y1) * 69.0
            length += math.hypot(dx, dy)
    return length


class Net(object):
    """Active surface blocks and the intersections where two or more streets meet, from 3psu-pn9h."""

    def __init__(self, rows):
        self.seg, self.node_segs = {}, collections.defaultdict(list)
        for r in rows:
            c = cnn(r.get("cnn"))
            if c is None:
                continue
            f, t = cnn(r.get("f_node_cnn")), cnn(r.get("t_node_cnn"))
            lines = line_coords(r.get("line"))
            self.seg[c] = {"street": street_key(r.get("streetname")), "cls": ROAD_CLASS.get(r.get("classcode")),
                           "f": f, "t": t, "active": r.get("active") in (True, "true", "True"), "lines": lines,
                           "miles": miles_of(lines)}
            for n in (f, t):
                if n:
                    self.node_segs[n].append(c)
        for n in self.node_segs:
            self.node_segs[n].sort()
        self.surface = {c for c, s in self.seg.items() if s["active"] and s["cls"] in SURFACE}
        self.corners = {}
        for n, segs in self.node_segs.items():
            live = [c for c in segs if c in self.surface]
            if len({self.seg[c]["street"] for c in live}) > 1:
                self.corners[n] = live

    def cls(self, c):
        k = self.seg[c]["cls"]
        return "arterial" if k == "major" else k


# ---- per crash ---------------------------------------------------------------------------------------------

def crash_records(crashes, parties, victims):
    hurt, ksi = collections.Counter(), collections.Counter()
    for v in victims:
        if v["victim_degree_of_injury"] in cp.KSI_PERSON:
            ksi[v["case_id_pkey"]] += 1
        if v["victim_degree_of_injury"] not in cp.NOT_HURT:
            hurt[v["case_id_pkey"]] += 1
    out = []
    for cid in sorted(crashes, key=lambda x: (len(x), x)):
        c = crashes[cid]
        ps = parties.get(cid, {})
        af, _ = cp.at_fault_party(c, ps)
        mover = af
        if af is not None and af["party_type"] == "Pedestrian":
            mover = cp.first_driver(ps)
        out.append({
            "case": cid, "c": c, "hurt": hurt[cid], "ksi": ksi[cid],
            "mode": cp.mode(c["dph_col_grp_description"] or ""),
            "violation": cp.violation_fine(c["vz_pcf_group"], c["vz_pcf_code"]),
            "movement": cp.MOVEMENT_FINE.get(mover["move_pre_acc"], cp.OTHER_MOVE) if mover else cp.OTHER_MOVE,
        })
    return out


def midpoint(lines):
    pts = [p for ln in lines for p in ln]
    return pts[len(pts) // 2] if pts else None


def hin_layer(fxf, net):
    r = sfdata.fetch(fxf, select="cnn_sgmt_pkey,full_street_name,f_node_cnn_intrsctn_fkey,t_node_cnn_intrsctn_fkey,"
                                  "corrected_length_miles,geom", floor=1000)
    by = {}
    for x in r.rows:
        by.setdefault(cnn(x["cnn_sgmt_pkey"]), x)
    blocks, nodes, miles = set(), set(), 0.0
    unmatched = []
    for c, x in sorted(by.items()):
        miles += float(x["corrected_length_miles"] or 0)
        if c in net.seg:
            blocks.add(c)
            for n in (cnn(x.get("f_node_cnn_intrsctn_fkey")), cnn(x.get("t_node_cnn_intrsctn_fkey"))):
                if n:
                    nodes.add(n)
        else:
            unmatched.append((street_key(x.get("full_street_name")), line_coords(x.get("geom"))))
    # A dual-carriageway row (its id is not a centerline CNN, and its street name is blank): every centerline block
    # whose midpoint and both ends lie within HIN_MATCH_FT of the row's line, and that block's end nodes. The ends
    # test keeps out a cross street, whose far end is a block away.
    grid = collections.defaultdict(list)
    for c in sorted(net.surface):
        m = midpoint(net.seg[c]["lines"])
        if m:
            grid[(round(m[0], 3), round(m[1], 3))].append((c, m))
    dual_hit = 0
    for st, lines in unmatched:
        pts = [p for ln in lines for p in ln]
        if not pts:
            continue
        keys = {(round(x, 3) + dx, round(y, 3) + dy) for x, y in pts for dx in (-0.001, 0, 0.001) for dy in (-0.001, 0, 0.001)}
        hit = False
        for k in sorted(keys):
            for c, m in grid.get((round(k[0], 3), round(k[1], 3)), ()):
                ends = [ln[i] for ln in net.seg[c]["lines"] for i in (0, -1)] or [m]
                if all(min(feet_to_line(p[0], p[1], ln) for ln in lines) <= HIN_MATCH_FT for p in [m] + ends):
                    blocks.add(c)
                    nodes.update(n for n in (net.seg[c]["f"], net.seg[c]["t"]) if n)
                    hit = True
        dual_hit += hit
    return {"blocks": blocks, "nodes": nodes, "miles": miles, "rows": len(by), "unmatched": len(unmatched),
            "dual_matched": dual_hit, "tag": r.tag, "read_on": r.fetched_on}


def ltn_cells(net, lts):
    """Candidate cells: eligible blocks joined at nodes no boundary block touches."""
    def eligible(c):
        k = net.cls(c)
        v = lts.get(c)
        if v is None:
            return k == "residential"
        return k in ("residential", "collector") and v in ("1", "2")
    elig = {c for c in net.surface if eligible(c)}
    boundary_nodes = set()
    for c in net.surface - elig:
        for n in (net.seg[c]["f"], net.seg[c]["t"]):
            if n:
                boundary_nodes.add(n)
    parent = {c: c for c in elig}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for n, segs in sorted(net.node_segs.items()):
        if n in boundary_nodes:
            continue
        live = [c for c in segs if c in elig]
        for a, b in zip(live, live[1:]):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    comp = collections.defaultdict(list)
    for c in elig:
        comp[find(c)].append(c)
    cells = []
    for root, members in comp.items():
        m = sum(net.seg[c]["miles"] for c in members)
        if m >= CELL_MIN_MILES:
            cells.append({"root": root, "blocks": sorted(members), "miles": m,
                          "residential_miles": sum(net.seg[c]["miles"] for c in members if net.cls(c) == "residential")})
    cells.sort(key=lambda x: (-x["miles"], x["root"]))
    in_cell = {c for x in cells for c in x["blocks"]}
    return cells, in_cell, boundary_nodes, len(comp)


def main():
    res = json.load(open(RESULTS, encoding="utf-8"))
    crashes, parties, victims = cp.load(*YEARS)
    recs = crash_records(crashes, parties, victims)

    streets = street_sources.held("streets")
    net = Net(streets.rows)
    signals_src = street_sources.held("signals")
    signal_nodes = {cnn(r.get("cnn")) for r in signals_src.rows if r.get("type") in SIGNAL_TYPES} - {None}
    speed_src = street_sources.held("speed_limits")
    limit20 = {cnn(r.get("cnn")) for r in speed_src.rows if r.get("speedlimit") == "20" and r.get("status") != "L"}
    unposted = {cnn(r.get("cnn")) for r in speed_src.rows if r.get("speedlimit") == "0"}
    slow_src = street_sources.held("slow_streets")
    slow = {cnn(r.get("cnn")) for r in slow_src.rows if r.get("status") == "Implemented"}
    cam_src = street_sources.held("cameras")
    ctx = Context.__new__(Context)
    ctx.seg, ctx.node_segs = net.seg, net.node_segs
    cameras, cam_unplaced = Context._place_cameras(ctx, cam_src.rows)
    cam_segs = set().union(*[s["segs"] for s in cameras]) if cameras else set()
    cam_nodes = set().union(*[s["nodes"] for s in cameras]) if cameras else set()

    with open(LANES, encoding="utf-8") as f:
        lanes_layer = json.load(f)
    lanes = {}
    for ft in lanes_layer["features"]:
        a = ft["attributes"]
        c = cnn(a.get("CNN"))
        if c:
            lanes[c] = max(lanes.get(c, 0), a.get("LANES_OP") or 0)

    bci, bci_read_on = cp.bci_blocks()
    lts = {c: v[0] for c, v in bci.items() if v[0]}

    hin24 = hin_layer("enwt-3u8m", net)
    hin22 = hin_layer("8vtn-qytr", net)

    stops = sfdata.fetch("4542-gpa3", select="cnn,st_facing,status", floor=10000)
    facing = collections.defaultdict(set)
    for r in stops.rows:
        if r.get("status") == "L":
            continue
        n = cnn(r.get("cnn"))
        if n:
            facing[n].add((r.get("st_facing") or "?").strip().upper())

    schools_r = sfdata.fetch("7e7j-59qk", select="cds_code,school,status,entity_type,latitude,longitude", floor=200)
    schools = []
    for r in schools_r.rows:
        if r.get("status") != "Active" or r.get("entity_type") == "Preschool":
            continue
        try:
            schools.append((float(r["latitude"]), float(r["longitude"])))
        except (KeyError, TypeError, ValueError):
            continue
    schools.sort()

    cells, in_cell, boundary_nodes, n_components = ltn_cells(net, lts)

    def node_class(n):
        if n in signal_nodes:
            return "signalized"
        segs = net.corners.get(n) or [c for c in net.node_segs.get(n, ()) if c in net.surface]
        f = facing.get(n, set())
        if not f:
            return "uncontrolled"
        return "all_way_stop" if len(f) >= len(segs) else "stop_controlled"

    def near_school(lat, lon):
        dlat = SCHOOL_FT / FT_PER_DEG_LAT
        kx = FT_PER_DEG_LAT * math.cos(math.radians(lat))
        lo, hi = 0, len(schools)
        # schools are sorted by latitude: scan the band
        import bisect
        i = bisect.bisect_left(schools, (lat - dlat, -999))
        while i < len(schools) and schools[i][0] <= lat + dlat:
            slat, slon = schools[i]
            if math.hypot((slat - lat) * FT_PER_DEG_LAT, (slon - lon) * kx) <= SCHOOL_FT:
                return True
            i += 1
        return False

    unread = collections.Counter()
    for r in recs:
        c = r["c"]
        tags = set()
        at_int = str(c["intersection"]).startswith("Intersection")
        node = cnn(c["cnn_intrsctn_fkey"])
        blocks = [b for b in c["street_block_cnns"].split(";") if b]
        tags.add("intersection" if at_int else "midblock")
        if at_int:
            k = node_class(node) if node else None
            if k is None:
                unread["node control"] += 1
            elif k == "signalized":
                tags.add("signalized")
            else:
                tags.add("unsignalized")
                tags.add(k)
                if k == "all_way_stop":
                    tags.add("stop_controlled")
            ct = c["corner_type"] or ""
            if "arterial" in ct or "major" in ct:
                tags.add("arterial_corner")
        sc = c["street_class"]
        if sc in ("arterial", "major"):
            tags.add("arterial")
        elif sc in ("collector", "residential"):
            tags.add(sc)
        s_lts = [lts[b] for b in blocks if b in lts]
        if s_lts:
            tags.add("high_stress" if max(s_lts) in ("3", "4") else "low_stress")
        else:
            unread["bike stress"] += 1
        try:
            if int(c["lanes"]) >= 2:
                tags.add("multilane")
        except ValueError:
            unread["lanes"] += 1
        for name, h in (("hin", hin24), ("hin2022", hin22)):
            if (at_int and node in h["nodes"]) or (not at_int and any(b in h["blocks"] for b in blocks)):
                tags.add(name)
        try:
            if near_school(float(c["tb_latitude"]), float(c["tb_longitude"])):
                tags.add("school_zone")
        except ValueError:
            unread["point"] += 1
        if any(b in slow for b in blocks):
            tags.add("slow_street")
        if any(b in limit20 for b in blocks):
            tags.add("limit20")
        if blocks and all(b in unposted for b in blocks):
            tags.add("unposted")
        seg = cnn(c["cnn_sgmt_fkey"])
        if (seg and seg in cam_segs) or (node and (at_int or not seg) and node in cam_nodes):
            tags.add("camera_corridor")
        if blocks and all(b in in_cell for b in blocks) and not (at_int and node in boundary_nodes):
            tags.add("ltn_cell")
        lt = c["lighting"]
        if lt.startswith("Dark"):
            tags.add("dark")
        elif lt == "Daylight":
            tags.add("daylight")
        elif lt == "Dusk - Dawn":
            tags.add("dusk")
        tb = cp.time_band(c["collision_time"], c["day_of_week"])
        if tb == cp.TIME_BANDS[4]:
            tags.add("late_night")
        elif tb == cp.TIME_BANDS[3]:
            tags.add("evening")
        r["tags"] = tags

    exprs = reach_expressions()
    classes = BASE + exprs

    # ---- tallies by family
    fam = collections.defaultdict(lambda: {"h": 0, "k": 0, "p": collections.defaultdict(lambda: [0, 0]),
                                           "m": collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))})
    for r in recs:
        if r["mode"] == "not stated":
            continue
        g = fam["%s | %s" % (r["mode"], r["violation"])]
        g["h"] += r["hurt"]
        g["k"] += r["ksi"]
        for cl in classes:
            if (cl in r["tags"]) if cl in BASE else evaluate(cl, r["tags"]):
                g["p"][cl][0] += r["hurt"]
                g["p"][cl][1] += r["ksi"]
                g["m"][cl][r["movement"]][0] += r["hurt"]
                g["m"][cl][r["movement"]][1] += r["ksi"]

    # ---- check: family totals equal results.json size_families
    want = {"%s | %s" % (f["mode"], f["violation"]): (f["people_injured"], f["ksi_people"])
            for f in res["size_families"]["families"]}
    got = {k: (v["h"], v["k"]) for k, v in fam.items()}
    bad = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    assert not bad, "family totals differ from results.json: %s" % bad[:5]

    def sh(a, b):
        return round(a / b, 4) if b else None

    groups = {}
    for name in sorted(fam):
        g = fam[name]
        places = {}
        for cl in classes:
            h, k = g["p"][cl] if cl in g["p"] else (0, 0)
            places[cl] = {"people_hurt": h, "ksi": k, "share_hurt": sh(h, g["h"]), "share_ksi": sh(k, g["k"]),
                          "by_movement": {m: v for m, v in sorted(g["m"][cl].items()) if v[0] or v[1]} if cl in g["m"] else {}}
        groups[name] = {"people_hurt": g["h"], "ksi": g["k"], "places": places}

    # ---- everyone, for the class shares across all groups
    allp = {}
    for cl in classes:
        h = sum(r["hurt"] for r in recs if ((cl in r["tags"]) if cl in BASE else evaluate(cl, r["tags"])))
        k = sum(r["ksi"] for r in recs if ((cl in r["tags"]) if cl in BASE else evaluate(cl, r["tags"])))
        allp[cl] = {"people_hurt": h, "ksi": k}
    tot_h, tot_k = sum(r["hurt"] for r in recs), sum(r["ksi"] for r in recs)
    for cl in allp:
        allp[cl]["share_hurt"] = sh(allp[cl]["people_hurt"], tot_h)
        allp[cl]["share_ksi"] = sh(allp[cl]["ksi"], tot_k)

    # ---- units
    corners = net.corners
    ctrl = collections.Counter(node_class(n) for n in corners)
    art_corner = {n for n, segs in corners.items() if any(net.cls(c) == "arterial" for c in segs)}
    miles = collections.Counter()
    for c in net.surface:
        miles[net.cls(c)] += net.seg[c]["miles"]
    multilane_ac = sum(net.seg[c]["miles"] for c in net.surface
                       if net.cls(c) in ("arterial", "collector") and lanes.get(c, 0) >= 2)
    st_src = "DataSF 3psu-pn9h, active surface blocks, read %s" % streets.read_on
    sig_tag = "DataSF ybh5-27n2, types %s, read %s" % (", ".join(sorted(SIGNAL_TYPES)), signals_src.read_on)
    stop_tag = "DataSF 4542-gpa3 (stop signs, status L left out), read %s" % stops.fetched_on

    def u(v, how, src, tag):
        return {"value": round(v, 1) if isinstance(v, float) else v, "how": how, "source": src, "tag": tag}
    q = "[DataSF %s — queried %s]"
    units = {
        "intersections": u(len(corners), "nodes where two or more named streets meet", st_src, q % ("3psu-pn9h", streets.read_on)),
        "signalized_intersections": u(ctrl["signalized"], "intersections with a signal today", sig_tag, q % ("ybh5-27n2", signals_src.read_on)),
        "unsignalized_intersections": u(len(corners) - ctrl["signalized"], "intersections with no signal", st_src + "; " + sig_tag, q % ("3psu-pn9h, ybh5-27n2", streets.read_on)),
        "unsignalized_arterial_intersections": u(sum(1 for n in art_corner if node_class(n) != "signalized"),
                                                 "intersections an arterial or major street meets, with no signal", st_src + "; " + sig_tag, q % ("3psu-pn9h, ybh5-27n2", streets.read_on)),
        "signalized_arterial_intersections": u(sum(1 for n in art_corner if node_class(n) == "signalized"),
                                               "intersections an arterial or major street meets, with a signal", st_src + "; " + sig_tag, q % ("3psu-pn9h, ybh5-27n2", streets.read_on)),
        "stop_controlled_intersections": u(ctrl["all_way_stop"] + ctrl["stop_controlled"], "unsignalized intersections with at least one stop sign", stop_tag, q % ("4542-gpa3", stops.fetched_on)),
        "arterial_intersections": u(len(art_corner), "intersections an arterial or major street meets", st_src, q % ("3psu-pn9h", streets.read_on)),
        "all_way_stops": u(ctrl["all_way_stop"], "unsignalized intersections whose stop signs face every block meeting there (a floor: one-way streets miss)", stop_tag, q % ("4542-gpa3", stops.fetched_on)),
        "two_way_or_partial_stops": u(ctrl["stop_controlled"], "unsignalized intersections with some but not all approaches stopped", stop_tag, q % ("4542-gpa3", stops.fetched_on)),
        "uncontrolled_intersections": u(ctrl["uncontrolled"], "intersections with no signal and no stop sign", stop_tag, q % ("4542-gpa3", stops.fetched_on)),
        "hin_miles": u(hin24["miles"], "sum of corrected_length_miles over the 2024 HIN's blocks", "DataSF enwt-3u8m", hin24["tag"]),
        "hin_corners": u(len(hin24["nodes"] & set(corners)), "intersections at an end of a 2024 HIN block", "DataSF enwt-3u8m, 3psu-pn9h", hin24["tag"]),
        "hin_signalized_corners": u(len(hin24["nodes"] & set(corners) & signal_nodes), "2024 HIN corners with a signal", "DataSF enwt-3u8m, ybh5-27n2", hin24["tag"]),
        "hin_unsignalized_corners": u(len((hin24["nodes"] & set(corners)) - signal_nodes), "2024 HIN corners with no signal", "DataSF enwt-3u8m, ybh5-27n2", hin24["tag"]),
        "hin2022_miles": u(hin22["miles"], "sum of corrected_length_miles over the 2022 HIN's blocks", "DataSF 8vtn-qytr", hin22["tag"]),
        "arterial_miles": u(miles["arterial"], "arterial and major street miles (classcode 2, 3)", st_src, q % ("3psu-pn9h", streets.read_on)),
        "collector_miles": u(miles["collector"], "collector street miles (classcode 4)", st_src, q % ("3psu-pn9h", streets.read_on)),
        "arterial_collector_miles": u(miles["arterial"] + miles["collector"], "arterial, major and collector miles", st_src, q % ("3psu-pn9h", streets.read_on)),
        "residential_miles": u(miles["residential"], "residential street miles (classcode 5)", st_src, q % ("3psu-pn9h", streets.read_on)),
        "residential_collector_miles": u(miles["residential"] + miles["collector"], "residential and collector miles", st_src, q % ("3psu-pn9h", streets.read_on)),
        "surface_miles": u(sum(miles.values()), "every active surface street mile (no freeway, ramp or class 0)", st_src, q % ("3psu-pn9h", streets.read_on)),
        "multilane_arterial_collector_miles": u(multilane_ac, "arterial, major and collector miles with 2 or more off-peak lanes (SFMTA MTA.CTA_trafficlanes LANES_OP)",
                                                st_src + "; SFMTA MTA.CTA_trafficlanes read %s" % lanes_layer.get("read_on"), "[primary — read %s] [inference — mine]" % lanes_layer.get("read_on")),
        "schools": u(len(schools), "active schools, every entity type but Preschool; a 500 ft zone each", "DataSF 7e7j-59qk", schools_r.tag),
        "ltn_cells": u(len(cells), "candidate low-traffic cells of at least %.1f miles of street (this script's rule)" % CELL_MIN_MILES,
                       st_src + "; SFMTA 2023 draft BCI (data/extract/sfmta-bci/scores.json, read %s)" % bci_read_on, "[inference — mine]"),
        "ltn_cell_miles": u(sum(x["miles"] for x in cells), "street miles inside those cells", st_src, "[inference — mine]"),
        "ltn_cell_residential_miles": u(sum(x["residential_miles"] for x in cells), "residential street miles inside those cells", st_src, "[inference — mine]"),
        "slow_street_miles": u(sum(net.seg[c]["miles"] for c in slow if c in net.seg), "miles of Implemented Slow Street blocks (hkz3-itiu, last edited 2024-01-18)", "DataSF hkz3-itiu", q % ("hkz3-itiu", slow_src.read_on)),
        "limit20_miles": u(sum(net.seg[c]["miles"] for c in limit20 if c in net.seg), "miles posted 20 mph today", "DataSF 3t7b-gebn", q % ("3t7b-gebn", speed_src.read_on)),
        "unposted_25_miles": u(sum(net.seg[c]["miles"] for c in net.surface if c in unposted),
                               "surface miles with speedlimit 0, the 25 mph default", "DataSF 3t7b-gebn", q % ("3t7b-gebn", speed_src.read_on)),
        "speed_camera_sites": u(len(cameras), "speed camera sites placed on a block (the street lane's rule)", "DataSF d5uh-bk84", q % ("d5uh-bk84", cam_src.read_on)),
        "speed_camera_corridor_miles": u(sum(net.seg[c]["miles"] for c in cam_segs if c in net.seg), "miles of camera corridor blocks", "DataSF d5uh-bk84, 3psu-pn9h", q % ("d5uh-bk84", cam_src.read_on)),
        "slip_lanes": {"value": None, "how": "no city dataset of slip lanes (channelized right turns) was found in the DataSF catalog on 2026-11-25", "source": None, "tag": "[unretrieved — verify]"},
    }

    coverage = {cl: allp[cl] for cl in BASE}
    checks = {
        "family_totals_match_results_json": True,
        "crashes": len(recs), "people_hurt": tot_h, "ksi": tot_k,
        "unread": dict(sorted(unread.items())),
        "hin2024": {k: hin24[k] for k in ("rows", "unmatched", "dual_matched")},
        "hin2022": {k: hin22[k] for k in ("rows", "unmatched", "dual_matched")},
        "camera_sites_unplaced": sorted(cam_unplaced),
        "ltn_components_before_size_floor": n_components,
        "results_json_signals_at_intersections": res.get("signals_at_intersections", {}).get("intersections_with_signal"),
    }
    out = {
        "about": __doc__.split("\n")[0],
        "years": list(YEARS),
        "place_classes": BASE,
        "expressions": exprs,
        "all_groups": coverage | {e: allp[e] for e in exprs},
        "groups": groups,
        "units": units,
        "checks": checks,
        "sources": {
            "3psu-pn9h": streets.read_on, "ybh5-27n2": signals_src.read_on, "3t7b-gebn": speed_src.read_on,
            "hkz3-itiu": slow_src.read_on, "d5uh-bk84": cam_src.read_on, "enwt-3u8m": hin24["read_on"],
            "8vtn-qytr": hin22["read_on"], "4542-gpa3": stops.fetched_on, "7e7j-59qk": schools_r.fetched_on,
            "bci": bci_read_on, "lanes": lanes_layer.get("read_on"),
        },
    }
    text = json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
    if text != old:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
    print("crashes %d, %d groups, %d place classes; wrote %s%s" % (len(recs), len(groups), len(classes),
          os.path.relpath(OUT, ROOT), "" if text != old else " (unchanged)"), file=sys.stderr)


if __name__ == "__main__":
    main()
