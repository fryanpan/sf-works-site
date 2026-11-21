#!/usr/bin/env python3
"""The densest High Injury Network stretches: miles of street at 30 and 40 or more people killed or severely injured per mile, rebuilt with DPH's corridor method from police reports, for Whitepaper Part 1.2 section 1.

    python3 tools/street-safety/hin-densest-stretches.py            # cached DataSF rows
    python3 tools/street-safety/hin-densest-stretches.py --refresh  # re-read nwes-mmgh and the centerlines

Writes out/hin-densest/summary.json, and out/hin-densest/hin-groups.json: the 2024 HIN's segments ranked worst to best
by the same section scores and cut into 10-mile groups, for the Street Safety map (tools/street-safety/street-safety-map.py); and
the same for the 2022 HIN in hin-groups-2022.json and hin-case-segments-2022.json (Bryan, 2026-11-19, thread
pw5fy849duld: "The 'By 10 miles of HIN' should change depending on which HIN I choose"). The 2017 HIN is left out: its
only public geometry is SFDPH's ArcGIS layer of 135 whole corridors with no block ids, some drawn on both sides of a
divided street (tools/street-safety/hin-versions.py), so its miles can't be put on blocks without spreading a corridor's length
over its drawn feet, which would be a guess. One-off analysis behind a notes page
(research/notes/whitepaper-2026-11/part-1/2026-11-18-densest-hin-stretches.md); no page reads it on a schedule.

WHERE THE FIGURES COME FROM. Supervisors at the 2026-11-17 SFCTA hearing cited "8.8 miles of streets" with "40 plus"
killed or severely injured (KSI), and Walk SF "30 or more ... per mile on two dozen miles" for 2020 to 2024. Both are
the cutoff tiers of DPH's HIN method. The 2022 methodology's Table 8 lists, for 2017-2021, the share of KSI and of
street miles captured at ">=40", 35, 30 ... 10 KSI per mile "by corridorized section": about 5 miles at 40, about 14
at 30, about 130 at 10. The 2024 edition of that table was not found in public; 8.8 and ~24 miles read as its 2024
values.

DPH'S METHOD, AS THE 2022 METHODOLOGY DESCRIBES IT (pp. 19-23). Each block is grown into a ~0.25 mile "corridorized"
section by adding adjacent blocks of the same street until the section is at least 0.25 miles; sections overlap.
Severe and fatal injuries are counted on a section when they intersect it and their primary street is the section's
street, then divided by the section's length. Data are linked police, hospital (ZSFG trauma registry) and ambulance
records ("TISS"), 5 years.

WHAT WE DO.
  Blocks   DataSF 3psu-pn9h active centerlines, surface layers only (STREETS, STREETS_TI/YBI/HUNTERSP, PARKS), grouped
           by street name with the suffix dropped (the name rule of tools/street-safety/hin-versions.py). Blocks of one street are
           adjacent when they share a node.
  Length   A divided street is drawn as two carriageways. Each block is cut into PIECE_FT pieces and a piece is dropped
           when it runs parallel (within PARALLEL_DEG) to an already-kept piece of the same street, within DUP_FT
           sideways and inside that piece's extent. So a divided street's miles count once, as DPH's corrected
           length does.
  Sections Each block grows ring by ring through same-street neighbours until its de-duplicated length reaches
           0.25 miles; streets that never reach it are left out, as in DPH's method.
  People   DataSF nwes-mmgh, victim_degree_of_injury Severe or Fatal, deduplicated on (case_id_pkey, victim_id). A
           person counts on a block when the report's primary_rd names the block's street and the person lies within
           ON_FT of the block, projecting no more than END_FT past its ends. ON_FT is wider than the repo's usual 60 ft
           so a crash on one carriageway of a divided street counts on the other too.
  Tiers    A section qualifies at threshold T when its people / miles >= T. The stretch at T is the union of every
           qualifying section's blocks; its miles are the de-duplicated length of that union.

POLICE REPORTS ARE NOT TISS. The public data lack the hospital-only cases, so police-only rates are lower than DPH's.
For 2017-2021 DPH counted 2,627 KSI (2022 methodology, Table 2); police reports hold 1,477, a ratio of 0.56. So DPH's
40 per mile is roughly 22 per mile in police counts. Rather than assume a ratio, the script sweeps the threshold and
CALIBRATES on 2017-2021: the police threshold that gives DPH's published ~5 and ~14 miles is then applied to
2020-2024. It also reports the literal reading (40 and 30 police-reported people per mile) and the supervisors'
literal words (a stretch with 40 or more people in four years, 2021-2024).

FIXES FROM THE FABLE PIPELINE REVIEW (2026-11-18). The parallel test is 70 degrees, so a divided street's tapers into
each node are dropped with the rest of its second carriageway. A section's length is the larger of its de-duplicated
length and its straight-line span, which stops Junipero Serra (main roadway beside same-name frontage roads) from
reading as a quarter mile while spanning a mile. Projects need the street's whole name, or a third of the stretch's
blocks, so one crossing of a divided street no longer lists the cross street's project.

WHY THE TIER IS THE WRONG QUESTION (Whitepaper Part 1.2, section 1). `regression`: the same police threshold on
2015-2019 and 2020-2024, which don't overlap: share of earlier top-tier miles still in the later tier, and the earlier
stretches' rate in both. `shares_2020_2024`: the tiers' share of all KSI against the share off the 2024 HIN (60 ft
rule). `crash_groups_2020_2024` and `crash_groups_by_stretch`: tools/street-safety/hin-who-hit-whom.py's groups (its mode() and
group() copied in), with parties from DataSF 8gtc-pjc6.

Checks stop the run: centerline and person row counts, unique person ids, at least 97% of people placed with a
primary road, every year in range present, and the calibration's 10-per-mile tier within 25% of DPH's 130 miles.
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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib.stable import write_json  # noqa: E402

OUT = os.path.join(ROOT, "out", "hin-densest")
ACCESS = os.path.join(ROOT, "data", "extract", "access")
ON_FT, END_FT, PIECE_FT, DUP_FT, CELL = 100, 30, 25, 160, 500
# 70 degrees, not a tight parallel test, so the diagonal tapers where a divided street's second carriageway meets
# the node are dropped too (at 20 degrees they kept about 80 ft a block; Fable review, 2026-11-18).
PARALLEL_DEG = 70
SECTION_FT = 0.25 * 5280
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
LAYERS = {"STREETS", "STREETS_TI", "STREETS_YBI", "STREETS_HUNTERSP", "PARKS"}
# DPH 2022 methodology, Table 8 (2017-2021, TISS): KSI per mile cutoff -> share of street miles. The text gives
# "only 5 miles" at about 40, "roughly 14 miles" at about 30 and "roughly 130 miles" at 10.
DPH_2022_TIERS = {40: 5.0, 30: 14.0, 10: 130.0}
DPH_2022_TISS_KSI = 2627
# SFDPH Health Commission deck, 2026-08-17, slide 11: from the 2022 HIN window to the 2024 one, "Severe & fatal
# injuries citywide increased 10%".
TISS_GROWTH = 1.10
PERIODS = {"2015-2019": ("2015-01-01", "2019-12-31"), "2017-2021": ("2017-01-01", "2021-12-31"),
           "2020-2024": ("2020-01-01", "2024-12-31"), "2021-2024": ("2021-01-01", "2024-12-31")}
SWEEP = [round(x * 0.5, 1) for x in range(8, 101)]  # 4.0 to 50.0 police-reported people per mile

SUFFIX = {"ST", "AVE", "AV", "BLVD", "BL", "WAY", "DR", "RD", "TER", "PL", "LN", "CT", "HWY", "EXPY", "CIR", "ALY", "PLZ"}


def name_key(s):
    s = (s or "").upper().replace("'", "").replace(".", "").strip()
    s = re.sub(r"\b0+(\d)", r"\1", s).replace("BAY SHORE", "BAYSHORE")
    return tuple(w for w in s.split() if w not in SUFFIX)


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


def proj(p, a, b):
    """(distance to the segment, t along it unclamped in feet, segment length)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L == 0:
        return math.dist(p, a), 0.0, 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L
    tc = max(0.0, min(L, t))
    q = (a[0] + dx * tc / L, a[1] + dy * tc / L)
    return math.dist(p, q), t, L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    C = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                     where="active='true'", floor=15000, refresh=a.refresh)
    blocks = {}
    for r in C.rows:
        if r.get("layer") not in LAYERS or not r.get("line"):
            continue
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        P = [[xy(*p) for p in ln] for ln in lines if len(ln) > 1]
        if not P:
            continue
        blocks[r["cnn"]] = {"cnn": r["cnn"], "name": name_key(r["streetname"]), "label": r["streetname"],
                            "f_st": r.get("f_st") or "", "t_st": r.get("t_st") or "",
                            "nodes": (r.get("f_node_cnn"), r.get("t_node_cnn")), "P": P}
    assert len(blocks) > 14000, len(blocks)

    by_street = collections.defaultdict(list)
    for c in sorted(blocks):
        by_street[blocks[c]["name"]].append(c)

    # ---- de-duplicated length per block (a divided street counts once)
    for nm, cs in by_street.items():
        kept = collections.defaultdict(list)   # cell -> (a, b, unit dir) of kept pieces of this street
        # longest blocks first is arbitrary but stable; sort by cnn for determinism
        for c in cs:
            b = blocks[c]
            dl = 0.0
            for P in b["P"]:
                for a0, b0 in zip(P, P[1:]):
                    d = math.dist(a0, b0)
                    if d == 0:
                        continue
                    k = max(1, int(math.ceil(d / PIECE_FT)))
                    u = ((b0[0] - a0[0]) / d, (b0[1] - a0[1]) / d)
                    for i in range(k):
                        p1 = (a0[0] + (b0[0] - a0[0]) * i / k, a0[1] + (b0[1] - a0[1]) * i / k)
                        p2 = (a0[0] + (b0[0] - a0[0]) * (i + 1) / k, a0[1] + (b0[1] - a0[1]) * (i + 1) / k)
                        m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        cx, cy = int(m[0] // CELL), int(m[1] // CELL)
                        dup = False
                        for ddx in (-1, 0, 1):
                            for ddy in (-1, 0, 1):
                                for q1, q2, w, owner in kept.get((cx + ddx, cy + ddy), ()):
                                    if owner == c:
                                        continue
                                    if abs(u[0] * w[0] + u[1] * w[1]) < math.cos(math.radians(PARALLEL_DEG)):
                                        continue
                                    dist, t, L = proj(m, q1, q2)
                                    if 0 <= t <= L and dist <= DUP_FT:
                                        dup = True
                                        break
                                if dup:
                                    break
                            if dup:
                                break
                        if not dup:
                            kept[(cx, cy)].append((p1, p2, u, c))
                            dl += d / k
            b["ft"] = dl
            b["raw_ft"] = sum(math.dist(p, q) for P in b["P"] for p, q in zip(P, P[1:]))

    # ---- adjacency within a street
    node_blocks = collections.defaultdict(list)
    for c, b in blocks.items():
        for n in b["nodes"]:
            if n:
                node_blocks[(b["name"], n)].append(c)
    adj = {c: sorted({o for n in b["nodes"] if n for o in node_blocks[(b["name"], n)] if o != c}) for c, b in blocks.items()}

    # ---- sections: each block grown ring by ring to >= 0.25 mi de-duplicated length
    # A section's length is the larger of its de-duplicated length and its straight-line span (the farthest two
    # block ends). Where a street's main roadway is drawn beside same-name frontage roads (Junipero Serra), the
    # de-duplication can strip the main roadway to almost nothing, so a section would span a mile while "measuring"
    # a quarter mile; the span stops that (Fable review, 2026-11-18).
    ends_of = {c: [P[0] for P in b["P"]] + [P[-1] for P in b["P"]] for c, b in blocks.items()}

    def span(sec):
        pts = [p for x in sec for p in ends_of[x]]
        return max((math.dist(p, q) for i, p in enumerate(pts) for q in pts[i + 1:]), default=0.0)
    sections, short = {}, {}
    for c in sorted(blocks):
        sec, ring, ft = {c}, [c], blocks[c]["ft"]
        while max(ft, span(sec)) < SECTION_FT and ring:
            nxt = sorted({o for x in ring for o in adj[x] if o not in sec})
            sec.update(nxt)
            ft += sum(blocks[o]["ft"] for o in nxt)
            ring = nxt
        L = max(ft, span(sec))
        if L >= SECTION_FT:
            sections[c] = (frozenset(sec), L)
        elif not ring:
            # A whole street shorter than a quarter mile (Richardson Ave, 1,306 ft). The HIN ranking and each year's
            # worst miles treat it as one section measured as a quarter mile, so its rate is no higher than a full
            # section's would be (Fable review, 2026-11-19: it scored zero and ranked near the bottom of the HIN with
            # about 48 severe or fatal injuries per mile). The densest-stretch tiers keep quarter-mile sections only,
            # so their published figures stand.
            short[c] = (frozenset(sec), SECTION_FT)
    ranked_sections = {**sections, **short}

    # ---- people
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,collision_datetime,victim_degree_of_injury,tb_latitude,tb_longitude,primary_rd,supervisor_district,victim_role,party_number_ckey",
                     where="victim_degree_of_injury in ('Severe Injury','Fatal Injury') and collision_datetime >= '2015-01-01T00:00:00'",  # through the newest row
                     floor=3000, refresh=a.refresh)
    ppl = {}
    for v in V.rows:
        ppl[(v["case_id_pkey"], v["victim_id"])] = v
    assert len(ppl) == len(V.rows), "duplicate (case, victim) rows"
    years = collections.Counter(v["collision_datetime"][:4] for v in ppl.values())
    assert all(years.get(str(y), 0) > 200 for y in range(2015, 2025)), years

    grid = collections.defaultdict(list)
    for c, b in blocks.items():
        for P in b["P"]:
            for a0, b0 in zip(P, P[1:]):
                for cx in range(int(min(a0[0], b0[0]) // CELL), int(max(a0[0], b0[0]) // CELL) + 1):
                    for cy in range(int(min(a0[1], b0[1]) // CELL), int(max(a0[1], b0[1]) // CELL) + 1):
                        grid[(cx, cy)].append((a0, b0, c))
    people, unplaced = [], 0
    for k in sorted(ppl):
        v = ppl[k]
        try:
            lo, la = float(v["tb_longitude"]), float(v["tb_latitude"])
            P = xy(lo, la) if -122.53 < lo < -122.35 and 37.70 < la < 37.84 else None
        except (TypeError, ValueError, KeyError):
            P = None
        rd = name_key(v.get("primary_rd"))
        on = set()
        if P:
            cx, cy = int(P[0] // CELL), int(P[1] // CELL)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for a0, b0, c in grid.get((cx + dx, cy + dy), ()):
                        if blocks[c]["name"] != rd:
                            continue
                        dist, t, L = proj(P, a0, b0)
                        if dist <= ON_FT and -END_FT <= t <= L + END_FT:
                            on.add(c)
        if not on:
            unplaced += 1
        people.append({"case": v["case_id_pkey"], "party": v.get("party_number_ckey"), "role": v.get("victim_role"), "P": P,
                       "id": "%s/%s" % k, "date": v["collision_datetime"][:10], "killed": v["victim_degree_of_injury"] == "Fatal Injury",
                       "district": v.get("supervisor_district"), "blocks": on, "rd": " ".join(rd)})
    placed_share = 1 - unplaced / len(people)
    assert placed_share >= 0.97, placed_share
    on_block = collections.defaultdict(list)
    for i, p in enumerate(people):
        for c in p["blocks"]:
            on_block[c].append(i)

    def ppl_in(sec, lo, hi):
        return {i for c in sec for i in on_block.get(c, ()) if lo <= people[i]["date"] <= hi}

    def tier(lo, hi, T, total_floor=None):
        """Union of sections at >= T people per mile (or, with total_floor, >= that many people in the section)."""
        union, who = set(), set()
        for c, (sec, ft) in sections.items():
            n = ppl_in(sec, lo, hi)
            ok = (len(n) >= total_floor) if total_floor else (len(n) / (ft / 5280.0) >= T)
            if ok:
                union |= sec
                who |= n
        return union, who

    def miles(union):
        return sum(blocks[c]["ft"] for c in union) / 5280.0

    S = {"sources": {"nwes-mmgh": V.tag, "3psu-pn9h": C.tag},
         "rules": {"on_ft": ON_FT, "end_ft": END_FT, "piece_ft": PIECE_FT, "dup_ft": DUP_FT, "section_mi": 0.25},
         "people_by_year": {y: years[y] for y in sorted(years)}, "placed_on_named_block_pct": round(100 * placed_share, 1),
         "sections": len(sections), "city_dedup_miles": round(sum(b["ft"] for b in blocks.values()) / 5280.0, 1),
         "periods": {}}

    for pname, (lo, hi) in PERIODS.items():
        tot = sum(1 for p in people if lo <= p["date"] <= hi)
        rates = {}
        for c, (sec, ft) in sections.items():
            rates[c] = len(ppl_in(sec, lo, hi)) / (ft / 5280.0)
        sweep = []
        for T in SWEEP:
            union = {x for c, r in rates.items() if r >= T for x in sections[c][0]}
            who = {i for c, r in rates.items() if r >= T for i in ppl_in(sections[c][0], lo, hi)}
            sweep.append({"per_mile": T, "miles": round(miles(union), 2), "people": len(who),
                          "people_pct": round(100.0 * len(who) / tot, 1)})
        S["periods"][pname] = {"police_ksi": tot, "sweep": sweep}

    # ---- calibration on 2017-2021 against DPH's Table 8 miles
    sw = S["periods"]["2017-2021"]["sweep"]
    cal = {}
    for dph_T, dph_mi in DPH_2022_TIERS.items():
        best = min(sw, key=lambda r: (abs(r["miles"] - dph_mi), r["per_mile"]))
        cal[dph_T] = {"dph_miles": dph_mi, "police_per_mile": best["per_mile"], "our_miles": best["miles"],
                      "police_people_pct": best["people_pct"], "ratio": round(best["per_mile"] / dph_T, 3)}
    S["calibration_2017_2021"] = cal
    S["police_to_tiss_ratio_2017_2021"] = round(S["periods"]["2017-2021"]["police_ksi"] / DPH_2022_TISS_KSI, 3)
    c10 = cal[10]
    assert abs(c10["our_miles"] - 130) / 130 < 0.25, c10

    # ---- the stretches, 2020-2024, at the calibrated thresholds and at the literal ones
    lo, hi = PERIODS["2020-2024"]

    def stretches(union):
        """Connected runs of one street within the union, each with miles, people, deaths and districts."""
        seen, out = set(), []
        for c in sorted(union):
            if c in seen:
                continue
            comp, stack = set(), [c]
            while stack:
                x = stack.pop()
                if x in comp:
                    continue
                comp.add(x)
                stack.extend(o for o in adj[x] if o in union and o not in comp)
            seen |= comp
            n = ppl_in(comp, lo, hi)
            ends = collections.Counter()
            for x in comp:
                ends[blocks[x]["f_st"]] += 1
                ends[blocks[x]["t_st"]] += 1
            label = blocks[min(comp)]["label"]
            # Ends: order the blocks along the run's main axis and take, at each extreme block, the cross street
            # that appears least often in the run (the outer one).
            mids = {x: (sum(p[0] for P in blocks[x]["P"] for p in P) / sum(len(P) for P in blocks[x]["P"]),
                        sum(p[1] for P in blocks[x]["P"] for p in P) / sum(len(P) for P in blocks[x]["P"])) for x in comp}
            xs = [m[0] for m in mids.values()]
            ys = [m[1] for m in mids.values()]
            ax = 0 if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else 1
            order = sorted(comp, key=lambda x: (mids[x][ax], x))

            def outer(x):
                cands = [s for s in (blocks[x]["f_st"], blocks[x]["t_st"]) if s]
                return min(cands, key=lambda s: (ends[s], s)) if cands else ""
            cross = [outer(order[0]), outer(order[-1])]
            dist = collections.Counter(people[i]["district"] for i in n if people[i]["district"])
            out.append({"street": label, "from_to": cross,
                        "blocks": len(comp), "miles": round(miles(comp), 2), "people": len(n),
                        "killed": sum(1 for i in n if people[i]["killed"]),
                        "per_mile": round(len(n) / miles(comp), 1) if miles(comp) else None,
                        "districts": {k: dist[k] for k in sorted(dist, key=lambda k: (-dist[k], k))},
                        "cnns": sorted(comp)})
        out.sort(key=lambda s: (-s["miles"], s["street"]))
        return out

    # SFMTA projects on each stretch: out/project-record/project-blocks.json (SFMTA's ArcGIS project layer placed on
    # centerline blocks by tools/projects/project-blocks.py) with phase and page from projects.json. A project counts when
    # names the stretch's street and shares a block, or shares max(4, a third of the stretch's) blocks. Area-wide programmes (over
    # AREA_WIDE blocks: calming zones, plans, citywide signal contracts) are listed apart, not as corridor work.
    PB = json.load(open(os.path.join(ROOT, "out", "project-record", "project-blocks.json")))
    PR = {p["id"]: p for p in json.load(open(os.path.join(ROOT, "out", "project-record", "projects.json")))["projects"]}
    S["sources"]["project-blocks"] = "out/project-record/project-blocks.json, generated %s" % PB["generated"]
    AREA_WIDE = 250

    def projects_on(cnns, street):
        cn, out = set(cnns), []
        word = " ".join(name_key(street)).lower()
        for k in sorted(PB["projects"]):
            v = PB["projects"][k]
            shared = len(cn & set(v["cnns"]))
            # the street's whole name as words (so "south van ness" is not "van ness"), and a shared-block floor of
            # a third of the stretch: one crossing of a divided street shares up to 4 blocks
            named = re.search(r"\b%s\b" % re.escape(word), re.sub(r"\b0+(\d)", r"\1", v["name"].lower())) is not None
            if (named and shared >= 1) or shared >= max(4, math.ceil(len(cn) / 3.0)):
                p = PR.get("sfmta:" + k, {})
                out.append({"id": "sfmta:" + k, "name": v["name"], "phase": p.get("phase"), "page": p.get("page"),
                            "shared_blocks": shared, "area_wide": len(v["cnns"]) > AREA_WIDE})
        return out

    S["stretches_2020_2024"] = {}
    # "calibrated": the 2017-2021 police threshold as is. "adjusted": divided by TISS_GROWTH, because DPH's linked
    # count rose 10% from the 2022 to the 2024 window while police reports stayed flat (1,477 both), so the same
    # TISS cutoff sits about 10% lower in police counts.
    for key, T in (("dph40_calibrated", cal[40]["police_per_mile"]), ("dph40_adjusted", round(cal[40]["police_per_mile"] / TISS_GROWTH, 2)),
                   ("dph30_calibrated", cal[30]["police_per_mile"]), ("dph30_adjusted", round(cal[30]["police_per_mile"] / TISS_GROWTH, 2)),
                   ("literal40", 40.0), ("literal30", 30.0)):
        union, who = tier(lo, hi, T)
        S["stretches_2020_2024"][key] = {"police_per_mile": T, "miles": round(miles(union), 2), "people": len(who),
                                         "killed": sum(1 for i in who if people[i]["killed"]),
                                         "stretches": [dict(s, projects=projects_on(s["cnns"], s["street"])) for s in stretches(union) if s["miles"] >= 0.05]}
    # The supervisors' literal words: a stretch where 40 or more people were hurt in four years (2021-2024).
    l4, h4 = PERIODS["2021-2024"]
    union, who = tier(l4, h4, None, total_floor=40)
    top = max(sections.items(), key=lambda kv: (len(ppl_in(kv[1][0], l4, h4)), kv[0]))
    S["literal_40_people_in_a_quarter_mile_2021_2024"] = {
        "miles": round(miles(union), 2), "people": len(who),
        "most_in_one_section": len(ppl_in(top[1][0], l4, h4)), "that_section": blocks[top[0]]["label"],
        "that_section_miles": round(top[1][1] / 5280.0, 2)}

    # ---- does the top tier hold still? (a) 2017-2021's top tier against 2020-2024's, by shared miles; (b) people
    # per mile per year on 2020-2024's top tier, during the window and after it (2025 to the newest row), against
    # the rest of the 2020-2024 10-per-mile tier. The after-period is short and police reports for recent months
    # may still be coming in, so (b) is a first look, not a test.
    newest = max(p["date"] for p in people)
    T40 = cal[40]["police_per_mile"]
    u17, _ = tier(*PERIODS["2017-2021"], T40)
    u20, _ = tier(lo, hi, T40)
    u20a, _ = tier(lo, hi, round(T40 / TISS_GROWTH, 2))
    u10, _ = tier(lo, hi, round(cal[10]["police_per_mile"] / TISS_GROWTH, 2))

    def rate(union, a0, a1, years_):
        n = len(ppl_in(union, a0, a1))
        m = miles(union)
        return {"miles": round(m, 2), "people": n, "per_mile_year": round(n / m / years_, 2) if m else None}
    after_years = ((int(newest[:4]) - 2025) * 12 + int(newest[5:7])) / 12.0
    S["persistence"] = {
        "top_2017_2021_miles": round(miles(u17), 2), "top_2020_2024_miles": round(miles(u20), 2),
        "shared_miles": round(miles(u17 & u20), 2),
        "newest_row": newest, "after_years": round(after_years, 2),
        "top_adjusted_2020_2024": {"during": rate(u20a, lo, hi, 5.0), "after": rate(u20a, "2025-01-01", newest, after_years)},
        "rest_of_10_tier": {"during": rate(u10 - u20a, lo, hi, 5.0), "after": rate(u10 - u20a, "2025-01-01", newest, after_years)},
    }

    # ---- (1) regression to the mean, on windows that do not overlap. The same police threshold in 2015-2019 and
    # 2020-2024 (police counts 1,491 and 1,477, so no growth adjustment between them). For each tier: what share of
    # the earlier window's miles meet it again in the later one, and the earlier stretches' rate in each window.
    # Also 2017-2021's top tier in 2022-2024, the three years after its data.
    reg = {}
    for name, T in (("40", T40), ("30", cal[30]["police_per_mile"])):
        e, _ = tier(*PERIODS["2015-2019"], T)
        l, _ = tier(lo, hi, T)
        e17, _ = tier(*PERIODS["2017-2021"], T)
        reg[name] = {"police_per_mile": T, "miles_2015_2019": round(miles(e), 2), "miles_2020_2024": round(miles(l), 2),
                     "miles_both": round(miles(e & l), 2),
                     "share_of_earlier_still_in": round(100.0 * miles(e & l) / miles(e), 1) if miles(e) else None,
                     "earlier_stretches_rate": {"2015-2019": rate(e, "2015-01-01", "2019-12-31", 5.0),
                                                "2020-2024": rate(e, lo, hi, 5.0)},
                     "top_2017_2021_in_2022_2024": {"2017-2021": rate(e17, "2017-01-01", "2021-12-31", 5.0),
                                                    "2022-2024": rate(e17, "2022-01-01", "2024-12-31", 3.0)}}
    S["regression"] = reg

    # ---- (2) shares of all people killed or severely injured, 2020-2024: the top tiers against off the 2024 HIN
    # (a person is on the HIN within 60 ft of its lines, the rule of tools/street-safety/hin-injury-kinds.py and hin-versions.py,
    # which give 1,132 of 1,476 on it for 2020-2024).
    H = sfdata.fetch("enwt-3u8m", floor=1000, refresh=a.refresh)
    hgrid = collections.defaultdict(list)
    for x in H.rows:
        g = x["geom"] if isinstance(x["geom"], dict) else json.loads(x["geom"])
        for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            Q = [xy(*p) for p in ln]
            for a0, b0 in zip(Q, Q[1:]):
                for cx in range(int(min(a0[0], b0[0]) // CELL), int(max(a0[0], b0[0]) // CELL) + 1):
                    for cy in range(int(min(a0[1], b0[1]) // CELL), int(max(a0[1], b0[1]) // CELL) + 1):
                        hgrid[(cx, cy)].append((a0, b0))

    def on_hin(P):
        cx, cy = int(P[0] // CELL), int(P[1] // CELL)
        return any(proj(P, a0, b0)[0] <= 60 for dx in (-1, 0, 1) for dy in (-1, 0, 1) for a0, b0 in hgrid.get((cx + dx, cy + dy), ()))
    base = [i for i, p in enumerate(people) if lo <= p["date"] <= hi]
    placed = [i for i in base if people[i]["P"]]
    off = [i for i in placed if not on_hin(people[i]["P"])]
    S["shares_2020_2024"] = {
        "all": len(base), "placed": len(placed),
        "off_2024_hin": {"people": len(off), "pct_of_placed": round(100.0 * len(off) / len(placed), 1),
                         "killed": sum(1 for i in off if people[i]["killed"])},
        "on_2024_hin": len(placed) - len(off),
    }
    for key in ("dph40_calibrated", "dph40_adjusted", "dph30_adjusted"):
        st = S["stretches_2020_2024"][key]
        S["shares_2020_2024"][key] = {"miles": st["miles"], "people": st["people"], "killed": st["killed"],
                                      "pct_of_all": round(100.0 * st["people"] / len(base), 1)}
    S["shares_2020_2024"]["all_killed"] = sum(1 for i in base if people[i]["killed"])

    # ---- (3) crash types on the top tier against everywhere: the groups of tools/street-safety/hin-who-hit-whom.py (its mode()
    # and group(), copied below because that script is not on this branch), parties from DataSF 8gtc-pjc6.
    BIKE = {"Bicycle", "Electric Bicycle", "Motorized Bicycle", "Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
    MOTO = {"Motorcycle", "Motor Driven Cycle/Scooter", "Police Motorcycle"}

    def mode(pt):
        t, vt = pt.get("party_type"), pt.get("stwd_vehicle_type") or ""
        if t == "Pedestrian":
            return "walk"
        if t == "Parked Vehicle":
            return "parked"
        if vt in BIKE:
            return "bike"
        if vt in MOTO:
            return "moto"
        if vt == "Misc. Non-Motor Vehicle":
            return "other"
        return "car"

    def group(me, others):
        motor = bool(others & {"car", "moto"})
        if me in ("car", "parked"):
            return "Car occupant, " + ("with another motor vehicle" if motor else "single vehicle")
        if me == "moto":
            return "Motorcyclist, " + ("with another motor vehicle" if motor else "solo")
        if me == "walk":
            return "Walking, hit by a motor vehicle" if motor else "Other"
        if me == "bike":
            return "Biking or scooting, " + ("with a motor vehicle" if motor else "no moving motor vehicle")
        return "Other"
    cases = sorted({people[i]["case"] for i in base})
    parties = collections.defaultdict(dict)
    for j in range(0, len(cases), 250):
        chunk = cases[j:j + 250]
        Pr = sfdata.fetch("8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,stwd_vehicle_type",
                          where="case_id_pkey in (%s)" % ",".join("'%s'" % c for c in chunk), floor=len(chunk), refresh=a.refresh)
        for pt in Pr.rows:
            parties[pt["case_id_pkey"]][pt["party_number_ckey"]] = pt
    assert all(c in parties for c in cases), "cases with no party rows"

    def person_group(i):
        p = people[i]
        ps = parties[p["case"]]
        me = "walk" if p["role"] == "Pedestrian" else mode(ps.get(p["party"], {}))
        others = {mode(q) for k, q in ps.items() if k != p["party"]} - {"parked"}
        return group(me, others)
    G = {i: person_group(i) for i in base}
    top_people = set()
    for key in ("dph40_adjusted",):
        u, who = tier(lo, hi, round(T40 / TISS_GROWTH, 2))
        top_people = who
    allc = collections.Counter(G[i] for i in base)
    topc = collections.Counter(G[i] for i in top_people)
    offc = collections.Counter(G[i] for i in off)
    S["crash_groups_2020_2024"] = {
        g: {"all": allc[g], "all_pct": round(100.0 * allc[g] / len(base), 1),
            "top40_adjusted": topc[g], "top_pct": round(100.0 * topc[g] / len(top_people), 1) if top_people else None,
            "off_hin": offc[g], "off_pct": round(100.0 * offc[g] / len(off), 1) if off else None}
        for g in sorted(allc, key=lambda g: (-allc[g], g))}
    # per stretch: how many groups, and the largest group's share
    per = []
    for st in S["stretches_2020_2024"]["dph40_adjusted"]["stretches"]:
        ids = ppl_in(set(st["cnns"]), lo, hi)
        c = collections.Counter(G[i] for i in ids)
        top = min(c.items(), key=lambda kv: (-kv[1], kv[0])) if c else ("", 0)
        per.append({"street": st["street"], "from_to": st["from_to"], "people": len(ids), "groups": len(c),
                    "largest_group": top[0], "largest_share_pct": round(100.0 * top[1] / len(ids), 1) if ids else None,
                    "counts": dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))})
    S["crash_groups_by_stretch"] = per

    # Two ranking windows: DPH's own for the 2024 HIN (2020-2024), and the map's people window (2022-2024, Bryan's story
    # on ). Both rank the same HIN segments.
    seg_of = assign_people(H, people)
    write_json(os.path.join(OUT, "hin-case-segments.json"), dict(sorted(seg_of.items())))
    G = {w: hin_groups(H, blocks, ranked_sections, people, ppl_in, name_key, S, *RANK_WINDOWS[w], seg_of=seg_of) for w in RANK_WINDOWS}
    write_json(os.path.join(OUT, "hin-groups.json"), {"windows": G})
    S["hin_groups"] = {w: {k: v for k, v in g.items() if k != "segments_ranked"} for w, g in G.items()}
    # The 2022 HIN, ranked the same way on the same windows, with its own case assignment and published length.
    for ed, (fxf, published) in sorted(EDITIONS.items()):
        He = sfdata.fetch(fxf, floor=1000, refresh=a.refresh)
        seg_e = assign_people(He, people)
        write_json(os.path.join(OUT, "hin-case-segments-%s.json" % ed), dict(sorted(seg_e.items())))
        Ge = {w: hin_groups(He, blocks, ranked_sections, people, ppl_in, name_key, S, *RANK_WINDOWS[w], seg_of=seg_e, published=published, edition=ed) for w in RANK_WINDOWS}
        write_json(os.path.join(OUT, "hin-groups-%s.json" % ed), {"edition": ed, "source": fxf, "windows": Ge})
        S["hin_groups_%s" % ed] = {w: {k: v for k, v in g.items() if k != "segments_ranked"} for w, g in Ge.items()}
    S["worst_by_year"] = worst_by_year(blocks, ranked_sections, people, ppl_in, newest)
    write_json(os.path.join(OUT, "summary.json"), S)
    for k, v in S["calibration_2017_2021"].items():
        print("DPH %s/mi (%s mi) -> police %s/mi gives %s mi" % (k, v["dph_miles"], v["police_per_mile"], v["our_miles"]))
    for k, v in S["stretches_2020_2024"].items():
        print(k, v["police_per_mile"], v["miles"], "mi", v["people"], "people")
    print("literal 40 people in a section, 2021-2024:", S["literal_40_people_in_a_quarter_mile_2021_2024"])
    print("placed:", S["placed_on_named_block_pct"], "%  sections:", S["sections"], " city miles:", S["city_dedup_miles"])


RANK_WINDOWS = {"2020-2024": ("2020-01-01", "2024-12-31"), "2022-2024": ("2022-01-01", "2024-12-31")}
GROUP_MI = 10.0      # Bryan (2026-11-19): "10 mile buckets from worst to best"
MATCH_FT = 110       # tools/street-safety/hin-versions.py's MATCH_FT: the 2024 layer draws some divided streets once, down the middle
HIN_2024_MILES = 132.9   # DPH's published total (Health Commission deck, 2026-08-17: 93 kept plus 39.9 added)
# The other editions ranked for the map: DataSF id and DPH's published length. 2022: 121.5 miles, SFDPH, Vision Zero
# High Injury Network 2022 Update methodology, Table 1 (the figure tools/street-safety/hin-versions.py reproduces from the same rows).
EDITIONS = {"2022": ("8vtn-qytr", 121.5)}


def hin_groups(H, blocks, sections, people, ppl_in, name_key, S, lo, hi, seg_of=None, published=HIN_2024_MILES, edition="2024"):
    """A HIN edition's segments (2024 unless `edition` says) ranked worst to best the way DPH ranks streets, and cut
    into GROUP_MI-mile groups. `published` is that edition's published length, which its rows must add to.

    DPH's rule (2022 methodology, pp. 19-23): every block is grown into overlapping ~0.25 mile corridorized sections,
    each section scores its severe and fatal injuries per mile (no weight on deaths), and a block is in the network at
    a cutoff when any section holding it reaches that cutoff. So a block's rank is its highest section score: the
    cutoff at which it would first enter the network, the order Table 8's tiers sweep through. Here the scores are
    police-reported people, 2020 to 2024 (DPH uses linked police, trauma-registry and EMS records the public lacks).

    Segments are DataSF enwt-3u8m's rows, deduplicated on cnn_sgmt_pkey, with DPH's corrected_length_miles, so the
    groups add to DPH's own 132.9 miles. A row whose id is a centerline block takes that block's score; a row with a
    dual-carriageway id takes the best score of the same-name blocks its line runs along (within MATCH_FT, projecting
    inside the block). Order: score, worst first; ties by the section that set the score, then segment id, so a tied
    section's blocks stay together. A segment goes to the group its first foot falls in: group k holds every segment
    whose cumulative start is in [10(k-1), 10k) miles, so no segment is split and a group runs a little over or under
    10 miles."""
    # each block's best section, 2020-2024
    best = {}
    for c in sorted(sections):
        sec, ft = sections[c]
        r = len(ppl_in(sec, lo, hi)) / (ft / 5280.0)
        for x in sec:
            if x not in best or r > best[x][0]:
                best[x] = (r, c)
    rows = {}
    for x in H.rows:
        rows.setdefault(str(int(float(x["cnn_sgmt_pkey"]))), x)
    miles_total = sum(float(x["corrected_length_miles"]) for x in rows.values())
    assert abs(miles_total - published) < 0.1, f"{edition} HIN rows add to {miles_total:.2f} mi, DPH publishes {published}"
    # same-name block lines for the geometric match
    grid = collections.defaultdict(list)
    for c, b in blocks.items():
        for P in b["P"]:
            for a0, b0 in zip(P, P[1:]):
                for cx in range(int(min(a0[0], b0[0]) // CELL), int(max(a0[0], b0[0]) // CELL) + 1):
                    for cy in range(int(min(a0[1], b0[1]) // CELL), int(max(a0[1], b0[1]) // CELL) + 1):
                        grid[(cx, cy)].append((a0, b0, c))
    segs, how = [], collections.Counter()
    for cnn in sorted(rows, key=int):
        x = rows[cnn]
        nm = name_key(x.get("full_street_name") or x.get("street_name"))
        g = x["geom"] if isinstance(x["geom"], dict) else json.loads(x["geom"].replace("'", '"'))
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        if cnn in blocks:
            on, kind = {cnn}, "block id"
            if blocks[cnn]["name"] != nm:
                how["block id, other street name"] += 1
        else:
            # Pieces of the row's line, each matched to the blocks it runs along. A row with no street name (some
            # dual-carriageway rows) takes the name most of its pieces run along.
            hits, kind = collections.defaultdict(set), "dual-carriageway id, by geometry" if nm else "by geometry, no name on the row"
            for ln in lines:
                Q = [xy(*p) for p in ln]
                for a0, b0 in zip(Q, Q[1:]):
                    k = max(1, int(math.ceil(math.dist(a0, b0) / PIECE_FT)))
                    for i in range(k):
                        m = (a0[0] + (b0[0] - a0[0]) * (i + 0.5) / k, a0[1] + (b0[1] - a0[1]) * (i + 0.5) / k)
                        cx, cy = int(m[0] // CELL), int(m[1] // CELL)
                        for dx in (-1, 0, 1):
                            for dy in (-1, 0, 1):
                                for s0, s1, c in grid.get((cx + dx, cy + dy), ()):
                                    if nm and blocks[c]["name"] != nm:
                                        continue
                                    dist, t, L = proj(m, s0, s1)
                                    if dist <= MATCH_FT and -10 <= t <= L + 10:
                                        hits[blocks[c]["name"]].add((c, m))
            if not nm and hits:
                nm = max(hits, key=lambda n: (len({m for _, m in hits[n]}), n))
            on = {c for c, _ in hits.get(nm, ())}
            if not on:
                kind = "unmatched"
        how[kind] += 1
        sc = max((best[c] for c in on if c in best), default=(0.0, ""))
        segs.append({"cnn": cnn, "street": x.get("full_street_name") or x.get("street_name") or "", "miles": float(x["corrected_length_miles"]),
                     "score": sc[0], "section": sc[1], "blocks": sorted(on), "lines": lines})
    assert how["unmatched"] <= 0.01 * len(segs), how
    segs.sort(key=lambda s: (-s["score"], s["section"], int(s["cnn"])))
    cum = 0.0
    for i, s in enumerate(segs):
        s["rank"] = i + 1
        s["start_mi"] = cum
        s["group"] = int(cum // GROUP_MI) + 1
        cum += s["miles"]
    n = max(s["group"] for s in segs)
    # Each person counts once, on the one segment assign_people() gives their case, the same assignment the map's chart reads.
    group_of = {s["cnn"]: s["group"] for s in segs}
    in_group = collections.defaultdict(list)
    for i, p in enumerate(people):
        c = (seg_of or {}).get(p["case"])
        if c is not None and lo <= p["date"] <= hi:
            in_group[group_of[c]].append(i)
    groups = []
    for k in range(1, n + 1):
        gs = [s for s in segs if s["group"] == k]
        who = in_group.get(k, [])
        groups.append({"group": k, "segments": len(gs), "miles": round(sum(s["miles"] for s in gs), 2),
                       "from_mi": round(gs[0]["start_mi"], 2), "to_mi": round(gs[-1]["start_mi"] + gs[-1]["miles"], 2),
                       "top_score": round(gs[0]["score"], 1), "low_score": round(gs[-1]["score"], 1),
                       "people": len(who), "killed": sum(1 for i in who if people[i]["killed"])})
    assert abs(sum(g["miles"] for g in groups) - miles_total) < 0.01, "group miles don't add to the HIN's"
    assert all(g["miles"] > 0 for g in groups)
    # A segment that scores zero has nobody hurt on its blocks in the window; one with people there is a missed section.
    zero_hurt = [s["cnn"] for s in segs if s["score"] == 0 and ppl_in(set(s["blocks"]), lo, hi)]
    assert not zero_hurt, f"{len(zero_hurt)} HIN segments score zero with people hurt on their blocks: {zero_hurt[:5]}"
    assert all(a["low_score"] >= b["top_score"] for a, b in zip(groups, groups[1:])), "groups out of rank order"
    # The densest-stretch map's top tier (dph40_adjusted, a 2020-2024 threshold) and how much of it heads the ranking.
    T = S["stretches_2020_2024"]["dph40_adjusted"]["police_per_mile"]
    top = [s for s in segs if s["score"] >= T]
    out = {"group_miles": GROUP_MI, "hin_miles": round(miles_total, 2), "segments": len(segs), "matched_by": dict(sorted(how.items())),
           "boundary_rule": "a segment goes to the group its first foot falls in; segments are never split",
           "top_tier_threshold": T, "top_tier_hin_miles": round(sum(s["miles"] for s in top), 2), "top_tier_segments": len(top),
           "groups": groups,
           "segments_ranked": [{k: (round(s[k], 3) if isinstance(s[k], float) else s[k]) for k in ("rank", "cnn", "street", "miles", "score", "group")} for s in segs]}
    # The groups' people counts are the ranking's own: each group's people are the cases assigned to its segments.
    assert sum(g["people"] for g in groups) == sum(1 for p in people if (seg_of or {}).get(p["case"]) in group_of and lo <= p["date"] <= hi)
    print("%s HIN groups %s to %s: %d of %s mi, matched %s; top tier %.2f HIN mi" % (edition, lo[:4], hi[:4], n, out["hin_miles"], out["matched_by"], out["top_tier_hin_miles"]))
    for g in groups:
        print("  group %(group)d: %(from_mi).1f-%(to_mi).1f mi (%(miles).2f), %(segments)d segs, score %(top_score)s-%(low_score)s, %(people)d people, %(killed)d killed" % g)
    return out


WORST_YEARS = list(range(2020, 2026))
NEAR_FT = 60         # the Street Safety map's on-the-network rule (tools/street-safety/hin-people-map.py NEAR_FT)


def assign_people(H, people):
    """Each police-reported case on one segment of the HIN edition `H` (2024 or 2022), once: of the HIN lines within NEAR_FT of the report's point,
    the nearest one on the report's primary road, else the nearest of any, ties to the lower segment id. Returns
    {case_id: cnn_sgmt_pkey}; a case with no HIN line within reach is left out. Every victim in a case shares its
    point and primary road, so a case has one segment. The ranking's group counts and the Street Safety map's group
    chart both read this (Fable review, 2026-11-19: the map's nearest-segment rule and the block match counted group 1
    as 141 and 156)."""
    rows = {}
    for x in H.rows:
        rows.setdefault(str(int(float(x["cnn_sgmt_pkey"]))), x)
    grid = collections.defaultdict(list)
    for cnn in sorted(rows, key=int):
        x = rows[cnn]
        nm = name_key(x.get("full_street_name") or x.get("street_name"))
        g = x["geom"] if isinstance(x["geom"], dict) else json.loads(x["geom"].replace("'", '"'))
        for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            Q = [xy(*q) for q in ln]
            for a0, b0 in zip(Q, Q[1:]):
                for cx in range(int(min(a0[0], b0[0]) // CELL), int(max(a0[0], b0[0]) // CELL) + 1):
                    for cy in range(int(min(a0[1], b0[1]) // CELL), int(max(a0[1], b0[1]) // CELL) + 1):
                        grid[(cx, cy)].append((a0, b0, cnn, nm))
    out = {}
    for p in people:
        if not p["P"] or p["case"] in out:
            continue
        P, rd = p["P"], tuple(p["rd"].split())
        cx, cy = int(P[0] // CELL), int(P[1] // CELL)
        near = {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a0, b0, cnn, nm in grid.get((cx + dx, cy + dy), ()):
                    d = proj(P, a0, b0)[0]
                    if d <= NEAR_FT and (cnn not in near or d < near[cnn][0]):
                        near[cnn] = (d, nm == rd and bool(rd))
        if near:
            out[p["case"]] = min(near, key=lambda c: (not near[c][1], near[c][0], int(c)))
    return out


def worst_by_year(blocks, sections, people, ppl_in, newest):
    """Each year's worst GROUP_MI miles of street, by DPH's corridor rule on that one year's police reports.

    Bryan (2026-11-19), on "worst segments shift every year": "show people worst segments in 2020
    through 2025 as they scroll". Every surface street block in the city is a candidate, not only the HIN's, so a year's
    worst isn't limited to the current network, and every year uses the same blocks and sections, so overlap between
    years is like for like. A block's score in a year is its highest section's people per mile that year; blocks are
    taken worst first (ties by the section's people, then the section's id) until GROUP_MI de-duplicated miles, a block
    counting when its first foot falls inside them, as hin_groups() does. One year holds one to three people a section,
    so many sections tie at the cutoff: `tied_at_cutoff_miles` says how many miles share the last score taken, and the
    pick among them is by section id, which is arbitrary. That noise is the point of the figure.

    Writes out/hin-densest/worst-by-year.json (each year's blocks) and returns the per-year summary with the overlap:
    of each year's worst miles, how many were in the year before's worst."""
    out, prev = {}, None
    for y in WORST_YEARS:
        a, b = "%d-01-01" % y, "%d-12-31" % y
        best = {}
        for c in sorted(sections):
            sec, ft = sections[c]
            n = len(ppl_in(sec, a, b))
            if not n:
                continue
            r = n / (ft / 5280.0)
            for x in sec:
                if x not in best or (r, n) > best[x][:2]:
                    best[x] = (r, n, c)
        order = sorted(best, key=lambda x: (-best[x][0], -best[x][1], best[x][2], x))
        cum, took = 0.0, []
        for x in order:
            if cum >= GROUP_MI:
                break
            took.append(x)
            cum += blocks[x]["ft"] / 5280.0
        last = best[took[-1]][0]
        tied = sum(blocks[x]["ft"] for x in order if abs(best[x][0] - last) < 1e-9) / 5280.0
        who = ppl_in(set(took), a, b)
        tot = sum(1 for p in people if a <= p["date"] <= b)
        row = {"year": y, "miles": round(cum, 2), "blocks": len(took), "people": len(who), "people_pct": round(100.0 * len(who) / tot, 1),
               "people_in_year": tot, "cutoff_per_mile": round(last, 1), "tied_at_cutoff_miles": round(tied, 2),
               "complete": newest >= "%d-04-01" % (int(y) + 1),  # a quarter past year end, for late reports
               "newest_row": newest if b > newest else None}
        if prev is not None:
            row["miles_also_in_prior_year"] = round(sum(blocks[x]["ft"] for x in set(took) & prev) / 5280.0, 2)
        out[y] = (row, sorted(took))
        prev = set(took)
    write_json(os.path.join(OUT, "worst-by-year.json"), {
        "group_miles": GROUP_MI, "rule": "all surface street blocks; score = highest corridorized section's police-reported severe and fatal injuries per mile in the year",
        "years": {str(y): {"summary": r, "cnns": t} for y, (r, t) in out.items()}})
    for y, (r, _) in out.items():
        print("worst %d: %.2f mi, %d people (%.1f%%), cutoff %.1f/mi (%.2f mi tied), also prior year %s mi" % (
            y, r["miles"], r["people"], r["people_pct"], r["cutoff_per_mile"], r["tied_at_cutoff_miles"], r.get("miles_also_in_prior_year")))
    return [r for r, _ in out.values()]


if __name__ == "__main__":
    main()
