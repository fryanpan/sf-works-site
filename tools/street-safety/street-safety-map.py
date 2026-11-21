#!/usr/bin/env python3
"""The Street Safety map's data for sf-works.org (site/data/street-safety/): every person severely injured or killed, the High Injury Networks, traffic stress, bike stress and crime layers, from tools/street-safety/hin-people-map.py's build().

    python3 tools/street-safety/street-safety-map.py

Writes
  site/data/street-safety/map.json      everything the map draws but the crash cards, plus `meta`: the date the data
                                        was read and the counts the story and the figures panel print
  (the crash cards are tools/street-safety/street-safety-cards.py's, one file per year and map cell under cards/; this script
  checks that every person here with a case number has one)
  site/data/street-safety/people-2005-2020.json  the people without cards from 2005 to 2020, in the same columns as
                                        map.json `light`, loaded when the Years slider reaches back before 2021
  site/data/street-safety/crime.json    every SFPD report since 2018 by place, year, kind, day and time, loaded when a
                                        reader first opens the crime view

Every input is public: DataSF nwes-mmgh, 8gtc-pjc6 and the crash rows behind the cards (police crash reports),
dau3-4s8f (Vision Zero fatality log), wg3w-h783 (SFPD incident reports), 3psu-pn9h (centerlines), the HIN editions,
SFMTA's traffic counts and Bike Comfort Index, SF-CHAMP, Telraam's public counters, SFMTA's GTFS stops, and news
articles already published. The page reads both files from the site build; nothing here fetches anything that
hin-people-map.py does not.

The read date is the newest date the people (points.geojson's own source tags) or the crime reports were queried,
so a rebuild with the same extracts writes the same bytes. Output is compact JSON with sorted keys.

Traffic stress: where a block has both an SFMTA count and a resident's Telraam counter, which one colours it is
tools/street-safety/hin-cut-through.py's COUNT_RULE (choose_count) and its override gate, which Bryan's answer sets. This
script only reads that choice, checks every block with both obeys it (count_rule_holds), and copies the rule's wording
into meta.countRule for the About page.

Bike stress is SFMTA's Bike Comfort Index (BCI), the 2023 draft layer SFMTA and Toole Design built for every street
(ArcGIS Bike_Comfort_Index_Score/FeatureServer/4, read through data/extract/sfmta-bci/scores.json), in five classes on
the combined `bci` field split at the Biking and Rolling Plan's all ages and abilities line, a score over 80 (BCI_AAA).
They are the layer's published renderer classes (4 - 30, 31 - 60, 61 - 81, 82 - 120, 121 - 146; read 2026-11-19) with
81 moved up a class, since 81 passes the plan's test and the renderer's 61 - 81 class straddles it (203 blocks score
exactly 81). The page draws the classes on each side of the line in a different hue (Bryan, 2026-11-19, thread
wpc01c92qm90: "There's a pretty hard cutoff where people won't ride any more"). Blocks are drawn from the active
street centerlines.

Through traffic: tools/street-safety/through-traffic.py's share of routed car trips on each block whose trip neither starts nor
ends within half a mile of the block, or the slider's quarter, three quarters or one mile (data/extract/through-traffic/blocks.json), keyed to the traffic rows.

Cause filter: each police-report person's cause (hin-injury-kinds.py cause(), the primary collision factor) as `ck`, a
slug of the cause's name, and under it `sk`, the Vehicle Code subcause key (hin-injury-kinds.py subcauses(): code_key()
of the section, or "other" for codes under 3 people). map.json `causes` is the tree the filter and the chart draw:
causes biggest first with Other and Unknown last, each with its subcauses biggest first and the pooled rest last. The
keys are what a link holds, so they stay put when a label is reworded.

Other party filter: each police-report person's `op`, one of tools/street-safety/street-safety-light.py OTHERS (no other vehicle,
a person on foot, one car or truck, one motorcycle, one bike or scooter, only parked vehicles, several moving vehicles, or one vehicle of unknown type), read there
from the crash's other party rows in DataSF 8gtc-pjc6. The people with cards take theirs from that extract's
`card_other` by victim id; map.json `others` is the count per option, which adds up to the police-report people.

Crime by year, kind, day and time of day: sfpd-person-crimes.py's all-years.json, every located, non-supplement report
from 2018 (the dataset's first year) by place, with its cells (((year - 2018) * 5 + group) * 7 + weekday) * 6 + period,
Sunday 0, period in the map's TIMES with 5 for no time. crime.json holds the places, each place's neighborhood, and
each place's cells as [cell gap, reports, ...], the gap from the place's previous cell (from -1 for the first), which
keeps the file under a megabyte gzipped. So the Years, Kind of crime, day and time filters all apply to the crime view
(Bryan, 2026-11-19) and its charts still split by any of them.

HIN worst to best: the 2024 HIN's segments (DataSF enwt-3u8m) in 10-mile groups from out/hin-densest/hin-groups.json,
which tools/street-safety/hin-densest-stretches.py ranks by DPH's own rule: each block's highest severe and fatal injuries per mile
on a corridorized quarter-mile section, police reports 2020 to 2024. A segment sits in the group its first foot falls in.

Area filter: SF's 41 Analysis Neighborhoods (data/extract/neighborhoods/analysis-neighborhoods.geojson), thinned to about 30 ft.
Crime view context: Muni's frequent lines, drawn from the Muni dashboard's own site/data/muni-map.json shapes and
colours, for the lines site/data/muni.json lists as frequent.

Checks: 922 police-report people, every one with a HIN bit set field, each figure the story quotes recomputed and
printed, crash cards for every police person with a case number, and no staff e-mail address anywhere in the output.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
OUT = ROOT / "site/data/street-safety"

sys.path.insert(0, str(HERE))
hpm = paths.load("hin-people-map.py")


def newest_date(*texts):
    dates = sorted(d for t in texts for d in re.findall(r"20\d\d-\d\d-\d\d", json.dumps(t)))
    return dates[-1] if dates else None


def peak_class(peak):
    """hin-cut-through.py's classes: under 90 cars an hour, then doubling from 90 (1.5 a minute) to 2,880 and up."""
    return 0 if peak < 90 else min(6, 1 + int(math.floor(math.log2(peak / 90))))


def count_rule_holds(T):
    """Every counted block's class is its own peak's, and every block with both counts uses the one the rule picks:
    source 6 (SFMTA's figure, Telraam beside) only where the rule picks SFMTA, source 5 with an SFMTA figure only where
    it picks the counter. Under the "telraam" rule the counter is picked when it passes hin-cut-through.py's override
    gate, recomputed here from the row: the rule's minimum of valid April to September days. Returns how many blocks
    have both."""
    rule = T["rule"]["rule"]
    gate = lambda days: days >= T["rule"]["min_season_days"]  # noqa: E731
    both = 0
    for i, p in enumerate(T["p"]):
        if p[7] in (0, 1, 5, 6) and p[0] >= 0:
            assert peak_class(p[2]) == p[0], f"class rule disagrees on row {i}: peak {p[2]} class {p[0]}"
        if p[7] == 6:
            both += 1
            assert (rule == "sfmta" and not p[9]) or (rule == "telraam" and not gate(p[19])), \
                f"row {i} uses SFMTA's count where COUNT_RULE {rule!r} picks the counter"
        elif p[7] == 5 and p[15]:
            both += 1
            assert (rule == "sfmta" and p[20]) or (rule == "telraam" and gate(p[21])), \
                f"row {i} uses the counter where COUNT_RULE {rule!r} picks SFMTA's {p[16]} count"
    return both


# The all ages and abilities line. SFMTA's Biking and Rolling Plan counts a Class II lane or a calmed Class III route in
# its all ages and abilities network only with "BCI > 80" (plan, https://www.sfmta.com/media/41810/download, PDF p. 13),
# and its appendix says "BCI scores over 80 indicate that ... the facility is comfortable to ride for most users"
# (appendix G, https://www.sfmta.com/media/41946/download, PDF p. 155). [primary — read 2026-11-19]
BCI_AAA = 80
BCI_AAA_SOURCE = "https://www.sfmta.com/media/41810/download"
# Classes for the combined BCI: each class's top value and label, higher more comfortable. SFMTA's renderer breaks
# (classBreaks on `bci`, read 2026-11-19) are 30, 60, 81, 120, 146; the third break is moved to BCI_AAA so no class
# straddles the line.
BCI_URL = "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4"
BCI_CLASSES = [(30, "4 - 30"), (60, "31 - 60"), (BCI_AAA, "61 - 80"), (120, "81 - 120"), (146, "121 - 146")]


def decode(enc):
    """sfMap.decode() in Python: the runs enc_runs() wrote, as the page reads them back."""
    out, x, y, k = [], 0, 0, 0
    for n in enc["n"]:
        run = []
        for _ in range(n):
            x += enc["d"][k]
            y += enc["d"][k + 1]
            k += 2
            run.append((x / hpm.STEP, y / hpm.STEP))
        out.append(run)
    return out


def midpoint(run):
    """The point halfway along a run by length (feet-scaled degrees), the one point that decides a block's area.
    map.js midpoint() is the same rule, so a drawn area counts the same blocks on the map and in the chart."""
    k = math.cos(math.radians(37.76))
    seg = [math.hypot((b[0] - a[0]) * k, b[1] - a[1]) for a, b in zip(run, run[1:])]
    half, total = sum(seg) / 2, 0.0
    for (a, b), d in zip(zip(run, run[1:]), seg):
        if d and total + d >= half:
            t = (half - total) / d
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        total += d
    return run[0]


class Hoods:
    """SF's 41 Analysis Neighborhoods from the unthinned outlines, in name order: hood(point) is the index of the one
    that holds it, or -1. The thinned outlines are for drawing only; their shared edges no longer meet."""

    def __init__(self):
        N = json.loads(hpm.NHOODS.read_text())["features"]
        assert len(N) == 41, f"{len(N)} analysis neighborhoods, expected 41"
        self.feats = sorted(N, key=lambda f: f["properties"]["nhood"])
        self.names = [f["properties"]["nhood"] for f in self.feats]
        self.zero = self.two = 0

    def hood(self, pt):
        hit = [i for i, f in enumerate(self.feats) if hpm.in_nhood(pt, f["geometry"])]
        if not hit:
            self.zero += 1
        if len(hit) > 1:
            self.two += 1
        return hit[0] if hit else -1


def bci_layer(C, H):
    """Every active surface block with a BCI score, as runs grouped by SFMTA's class, with each run's neighborhood."""
    B = json.loads(hpm.BCI.read_text())
    score = {int(float(r["cnn"])): r["bci"] for r in B["records"] if r.get("bci") is not None}
    assert len(score) > 14000, f"only {len(score)} BCI scores"
    runs = [[] for _ in BCI_CLASSES]
    counts = [0] * len(BCI_CLASSES)
    active, matched = set(), set()
    for r in sorted(C.rows, key=lambda r: int(float(r["cnn"]))):
        if not r.get("line") or (r.get("layer") or "").startswith(("FREEWAYS", "PAPER", "PSEUDO")):
            continue
        active.add(int(float(r["cnn"])))
        v = score.get(int(float(r["cnn"])))
        if v is None:
            continue
        matched.add(int(float(r["cnn"])))
        k = next(i for i, (top, _) in enumerate(BCI_CLASSES) if v <= top)
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            runs[k].append(hpm.thin([tuple(p) for p in ln]))
        counts[k] += 1
    assert len(matched) >= 15000, f"only {len(matched)} centerline blocks matched a BCI score"
    assert max(score.values()) <= BCI_CLASSES[-1][0], "a BCI score above SFMTA's top class"
    below = sum(1 for top, _ in BCI_CLASSES if top <= BCI_AAA)
    assert BCI_CLASSES[below - 1][0] == BCI_AAA, "no class ends at the all-ages line"
    enc = [hpm.enc_runs(r) for r in runs]
    # Each run's neighborhood by its midpoint, from the runs as the page decodes them.
    hood = [[H.hood(midpoint(r)) for r in decode(e)] for e in enc]
    return {"runs": enc, "hood": hood, "blocks": counts, "labels": [l for _, l in BCI_CLASSES], "source": BCI_URL, "fetched_on": B["fetched_on"],
            "aaa": {"score": BCI_AAA, "below": below, "source": BCI_AAA_SOURCE},
            "matched": len(matched), "unmatched": len(set(score) - active), "unscored": len(active - matched)}


def neighborhoods(H):
    """SF's Analysis Neighborhoods, name and thinned outline (for drawing), in name order."""
    return [{"name": n, "geom": hpm.thin_geom(f["geometry"])} for n, f in zip(H.names, H.feats)]


def muni_lines():
    """Muni's frequent lines as the Muni dashboard draws them: shape, SFMTA colour, text colour and GTFS route type."""
    M = json.loads((ROOT / "site/data/muni-map.json").read_text())["lines"]
    freq = json.loads((ROOT / "site/data/muni.json").read_text())["frequency"]["frequentLines"]
    out, dropped = {}, []
    for r in sorted(freq):
        L = M.get(r)
        if not L or not L.get("shape"):
            dropped.append(r)
            continue
        out[r] = {"s": [[[round(x, 5), round(y, 5)] for x, y in hpm.thin([tuple(p) for p in ln])] for ln in L["shape"]],
                  "c": L["color"], "t": L["text"], "y": int(L["type"])}
    # The two express lines have no shape in the Muni map data; any other line missing is a break to look at.
    assert set(dropped) <= {"1X", "30X"}, f"frequent Muni lines with no shape: {dropped}"
    print(f"Muni: {len(out)} of {len(freq)} frequent lines drawn; no shape for {', '.join(dropped) or 'none'}", file=sys.stderr)
    return out, {"drawn": len(out), "frequent": len(freq), "dropped": dropped}


HIN_CASES = ROOT / "out/hin-densest/hin-case-segments.json"   # from tools/street-safety/hin-densest-stretches.py
HIN_GROUPS = ROOT / "out/hin-densest/hin-groups.json"   # from tools/street-safety/hin-densest-stretches.py
# Each HIN edition the groups chart and layer follow (Bryan, 2026-11-19): its DataSF id, its
# published length (2024: Health Commission deck, 2026-08-17; 2022: the 2022 methodology, Table 1), the ranking and
# case files tools/street-safety/hin-densest-stretches.py writes for it, and the person field that holds a person's segment.
# 2017 has no block-level geometry, so it has no groups (that script's docstring says why).
HIN_EDITIONS = {"2024": ("enwt-3u8m", 132.9, HIN_GROUPS, HIN_CASES, "hs"),
                "2022": ("8vtn-qytr", 121.5, ROOT / "out/hin-densest/hin-groups-2022.json", ROOT / "out/hin-densest/hin-case-segments-2022.json", "hs22")}
WORST = ROOT / "out/hin-densest/worst-by-year.json"     # from tools/street-safety/hin-densest-stretches.py
LIGHT = ROOT / "data/extract/street-safety/light-injuries.json"   # from tools/street-safety/street-safety-light.py
INLINE_FROM = 2021   # Bryan (2026-11-19): "By default, please show 2021-current day"


def hin_groups_layer(people, edition="2024"):
    """A HIN edition's segments (HIN_EDITIONS) in 10-mile groups, worst to best, as tools/street-safety/hin-densest-stretches.py
    ranks them (DPH's corridorized injuries-per-mile rule on police reports), for each ranking window it writes. Lines
    are the edition's own DataSF rows, the query that script makes (the same cache entry); each run carries its
    segment's index `s`, and `g[window][s]` is that segment's group. Each person gets the edition's segment field
    (`hs` for 2024, `hs22` for 2022): their case's segment from the ranking, else the nearest within 60 ft (the map's
    on-the-network rule), or -1. Checks: every HIN row ranked in every window, the groups' miles add to the rows' miles
    and to DPH's published length, every group has segments, the group miles match the ranking's, and each group's
    people on the map match the ranking's count."""
    fxf, published, groups_file, cases_file, field = HIN_EDITIONS[edition]
    W = json.loads(groups_file.read_text())["windows"]
    H = hpm.sfdata.fetch(fxf, floor=1000)
    rows = {}
    for x in H.rows:
        rows.setdefault(str(int(float(x["cnn_sgmt_pkey"]))), x)
    segs = sorted(rows, key=int)
    miles = sum(float(rows[c]["corrected_length_miles"]) for c in segs)
    assert abs(miles - published) < 0.1, f"{edition} HIN rows add to {miles:.2f} mi, DPH publishes {published}"
    g_out, groups = {}, {}
    for w, G in sorted(W.items()):
        group = {s["cnn"]: s["group"] for s in G["segments_ranked"]}
        assert set(group) == set(rows), f"{edition} {w}: {len(set(rows) ^ set(group))} HIN rows differ between {fxf} and {groups_file.name}"
        by = collections.defaultdict(float)
        for c in segs:
            by[group[c]] += float(rows[c]["corrected_length_miles"])
        n = max(by)
        assert sorted(by) == list(range(1, n + 1)), f"{w}: a group has no segments"
        assert abs(sum(by.values()) - miles) < 1e-6, f"{w}: group miles {sum(by.values()):.2f}, HIN {miles:.2f}"
        for g in G["groups"]:
            assert abs(by[g["group"]] - g["miles"]) < 0.01, f"{w} group {g['group']}: {by[g['group']]:.2f} mi here, {g['miles']} in hin-groups.json"
        g_out[w] = [group[c] for c in segs]
        groups[w] = [{"g": g["group"], "miles": g["miles"], "from": g["from_mi"], "to": g["to_mi"]} for g in G["groups"]]
    runs, si, items = [], [], []
    for i, c in enumerate(segs):
        geo = rows[c]["geom"] if isinstance(rows[c]["geom"], dict) else json.loads(rows[c]["geom"].replace("'", '"'))
        for ln in ([geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]):
            if len(ln) > 1:
                runs.append(hpm.thin([tuple(p) for p in ln]))
                si.append(i)
                items.append(([hpm.xy(*q) for q in ln], i))
    # A police-reported person takes the segment tools/street-safety/hin-densest-stretches.py assign_people() gave their case (the
    # primary road's segment first, else the nearest, within 60 ft), the one the ranking's group counts read, so the
    # chart and the ranking count the same people. People with no police case here (the less severe levels, which
    # carry no primary road, and fatality-log deaths) take the nearest segment within 60 ft.
    seg_of = json.loads(cases_file.read_text())
    index = {c: i for i, c in enumerate(segs)}
    assert all(c in index for c in seg_of.values()), f"{cases_file.name} names a segment {fxf} lacks"
    grid = hpm.Grid(items)
    by_case = 0
    for p in people:
        cs = p.get("cs")
        if p.get("np"):
            p[field] = -1   # no place, so on no segment
        elif cs and not p.get("lg") and not p.get("mi"):
            p[field] = index[seg_of[cs]] if cs in seg_of else -1
            by_case += 1
        else:
            k = grid.nearest(hpm.xy(*p["c"]), hpm.NEAR_FT)
            p[field] = -1 if k is None else k
    # The chart and the ranking count the same people: each window's severe and fatal police-reported people per group
    # here match hin-groups.json's counts, which read the same case assignment.
    for w, G in sorted(W.items()):
        lo, hi = w.split("-")
        n = collections.Counter(g_out[w][p[field]] for p in people
                                if p[field] >= 0 and not p.get("lg") and p.get("sv", 0 if p.get("k") else 1) <= 1 and lo <= p["d"][:4] <= hi)
        for g in G["groups"]:
            assert n[g["group"]] == g["people"], f"{edition} {w} group {g['group']}: {n[g['group']]} people on the map, {g['people']} in the ranking"
        # Groups in rank order: each group's lowest score is at least the next group's highest.
        assert all(a["low_score"] >= b["top_score"] for a, b in zip(G["groups"], G["groups"][1:])), f"{edition} {w}: groups out of rank order"
    on = sum(1 for p in people if p[field] >= 0)
    print(f"{edition} HIN groups: windows {sorted(W)}, {len(segs)} segments, {len(runs)} runs; {on} of {len(people)} people within 60 ft of one", file=sys.stderr)
    return {"runs": hpm.enc_runs(runs), "s": si, "g": g_out, "groups": groups, "source": H.tag, "windows": sorted(W)}


def worst_layer(C):
    """Each year's worst 10 miles of street (tools/street-safety/hin-densest-stretches.py worst_by_year()), as centerline runs with a
    bit per year (bit 0 is 2020) and the per-year summary the corner chart draws. Checks: every block is an active
    centerline with a line, and every year has its miles."""
    Wb = json.loads(WORST.read_text())
    years = sorted(Wb["years"], key=int)
    bits = collections.defaultdict(int)
    for k, y in enumerate(years):
        for c in Wb["years"][y]["cnns"]:
            bits[c] |= 1 << k
    geo = {}
    for r in C.rows:
        if r.get("line") and r["cnn"] in bits:
            g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
            geo[r["cnn"]] = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
    missing = set(bits) - set(geo)
    assert not missing, f"{len(missing)} worst-year blocks have no centerline line"
    runs, yb = [], []
    for c in sorted(bits, key=lambda c: int(float(c))):
        for ln in geo[c]:
            if len(ln) > 1:
                runs.append(hpm.thin([tuple(p) for p in ln]))
                yb.append(bits[c])
    summ = [Wb["years"][y]["summary"] for y in years]
    assert all(9.5 < s["miles"] < 10.5 for s in summ), "a year's worst miles are not about 10"
    return {"runs": hpm.enc_runs(runs), "y": yb, "years": [int(y) for y in years], "summary": summ}


LIGHT_D0 = "2005-01-01"


def near_hood(Hd, lon, lat):
    """The neighborhood a point is in, or for a report geocoded just outside every outline (a pier, the shoreline), the
    first one found stepping out to 1,000 ft in eight directions, so every person counts in one neighborhood."""
    h = Hd.hood((lon, lat))
    for ft in (100, 250, 500, 1000):
        if h >= 0:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)):
            h = Hd.hood((lon + dx * ft / hpm.FT_LON, lat + dy * ft / hpm.FT_LAT))
            if h >= 0:
                break
    return h


def light_people(Hd, tree):
    """The people drawn without a crash card (tools/street-safety/street-safety-light.py): every level in every year, less the
    2022-2024 severe injuries and deaths the cards cover. Each gets the fields the filters read: point, day since
    LIGHT_D0, hour (-1 unknown), level (0 Fatal Injury to 3 Complaint of Pain), road user, cause and subcause keys (the
    cause tree's; a subcause the tree doesn't list becomes "other"), at an intersection (1, 0, -1), neighborhood index,
    and later HIN bits and HIN segment. A severe or fatal person from 2015 on keeps their case id (`cs`), so
    hin_groups_layer() puts them on the segment the ranking assigned the case.

    A person with no place (`np`) counts and is not drawn: the report has no point (the extract's null lon and lat), or
    its point is past the city line, in no neighborhood. They have no point, neighborhood, intersection, HIN bits or
    HIN segment, so the page keeps them in every figure that needs no place and out of the place filters."""
    M = json.loads(LIGHT.read_text())
    import datetime as _dt
    d0 = _dt.date.fromisoformat(LIGHT_D0)
    known = {(t["key"], s["key"]) for t in tree for s in t["subs"]}
    ppl = []
    pooled = outside = nopoint = 0
    for lon, lat, d, h, lv, u, cause, sk, at, case, other in M["people"]:
        ck = slug(cause)
        if (ck, sk) not in known:
            sk = "other"
            pooled += 1
        hd = -1 if lon is None else near_hood(Hd, lon, lat)
        if lon is None:
            nopoint += 1
        elif hd < 0:
            outside += 1   # geocoded past the city line (south of Geneva Ave), not on a San Francisco street
        p = {"c": [lon, lat], "d": d, "dd": (_dt.date.fromisoformat(d) - d0).days, "h": h, "sv": lv, "u": M["users"][u], "ck": ck, "sk": sk,
             "cause": cause, "at": at, "hood": hd, "cs": case if lv <= 1 and d >= "2015-01-01" else "", "lg": 0, "op": M["others"][other]}
        if hd < 0:
            p.update(c=None, at=-1, cs="", np=1)
        ppl.append(p)
    assert nopoint == M["unplaced"], f"{nopoint} light people with no point, the extract says {M['unplaced']}"
    assert outside <= 0.001 * len(M["people"]), f"{outside} light people in no neighborhood"
    assert len(ppl) == len(M["people"]) == M["rows"], "a light person was dropped"
    print(f"light people: {len(ppl)} ({nopoint} with no point and {outside} outside every neighborhood counted and not drawn), {pooled} with a subcause the severe tree doesn't list (pooled to 'other')", file=sys.stderr)
    return ppl, M


def light_columns(ppl, M):
    """People in columns: point (degrees x 1e5), day since LIGHT_D0, and the rest as light_people() names them. The
    lookup lists (users, cause and subcause keys) are M's and the whole tree's, so the inline and the older file share
    one coding. `np` lists the rows with no place, whose x and y are 0."""
    return {"n": len(ppl), "d0": LIGHT_D0, "x": [round(p["c"][0] * 1e5) if p["c"] else 0 for p in ppl], "y": [round(p["c"][1] * 1e5) if p["c"] else 0 for p in ppl],
            "np": [i for i, p in enumerate(ppl) if p.get("np")],
            "dd": [p["dd"] for p in ppl], "h": [p["h"] for p in ppl], "sv": [p["sv"] for p in ppl],
            "users": M["users"], "u": [M["users"].index(p["u"]) for p in ppl], "cks": M["cks"], "ck": [M["cks"].index(p["ck"]) for p in ppl],
            "sks": M["sks"], "sk": [M["sks"].index(p["sk"]) for p in ppl], "at": [p["at"] for p in ppl], "hood": [p["hood"] for p in ppl],
            "hy": [p["hy"] for p in ppl], "hs": [p["hs"] for p in ppl], "hs22": [p["hs22"] for p in ppl],
            "ops": M["others"], "op": [M["others"].index(p["op"]) for p in ppl]}


def log_deaths(people, light, tree, hoods):
    """One person per death: a fatality-log death (`lg`, from tools/street-safety/hin-people-map.py load_deaths(), with the log's
    card) that the police also reported takes the police row's place among the counted people, and the police row
    leaves `light`. Returns the light people left and the number of deaths joined.

    The police row is the Fatal Injury row with the log's own case number (dau3-4s8f case_id_fkey), or, for a log death
    with no case number or a case the rows don't hold, the one within a day and 400 ft; each row joins one death, and
    a death with two rows to choose from stops the run. The joined person keeps what the log gives and the police row
    doesn't (the point the icon is drawn at, the age, the log's record and news links) and takes every field a filter
    reads from the police row: road user, date, hour, cause and subcause (keys and labels), other party, at an
    intersection, neighborhood, HIN bits and HIN segments. `lg` becomes 0, so the page counts and heats the person it
    draws, once, under every filter (Bryan, 2026-11-20: with Walking, killed and one cause picked the heat map showed
    deaths with no icon, because the icon was the log's person, who had no cause, and the count was the police row's).

    A death with no police row (the log's newest, the news-only ones, and any the police rows don't hold or can't
    place) stays `lg`: drawn, in no count, chart or heat map, and with no cause or other party, so those two filters
    take it off the map. It is not filed under "Unknown or not stated": that bar counts police reports whose officer
    stated no cause, and a death with no report yet would be counted a second time when its report arrives."""
    import datetime as _dt
    label = {(t["key"], x["key"]): x["label"] for t in tree for x in t["subs"]}
    # A light row's subcause the tree doesn't list is pooled as "other" (light_people), under a cause that may have no
    # pooled bar of its own: it takes the label hin-injury-kinds.py gives a pooled subcause.
    sub_label = lambda r: label.get((r["ck"], r["sk"])) or ("Other codes" if r["ck"] == "other" else "Other " + (r["cause"] if r["cause"].isupper() else r["cause"][0].lower() + r["cause"][1:]))   # noqa: E731
    fatal = [r for r in light if r["sv"] == 0 and r["c"]]
    by_case = collections.defaultdict(list)
    for r in fatal:
        by_case[r["cs"]].append(r)
    used, joined, near = set(), 0, 0
    logs = [p for p in people if p["lg"]]
    pairs = []
    for p in logs:   # by case number first, so a nearby death can't take another death's row
        rows = by_case.get(p["cs"], []) if p["cs"] else []
        if rows:
            # A crash that killed two: the same road user first, then the nearer row.
            r = min((r for r in rows if id(r) not in used), key=lambda r: (r["u"] != p["u"], math.dist(hpm.xy(*r["c"]), hpm.xy(*p["c"]))), default=None)
            if r is not None:
                used.add(id(r))
                pairs.append((p, r))
    paired = {id(p) for p, _ in pairs}
    for p in logs:
        if id(p) in paired:
            continue
        d, q = _dt.date.fromisoformat(p["d"]), hpm.xy(*p["c"])
        rows = [r for r in fatal if id(r) not in used and abs((d - _dt.date.fromisoformat(r["d"])).days) <= 1 and math.dist(q, hpm.xy(*r["c"])) <= 400]
        assert len(rows) <= 1, f"fatality-log death {p['lid'] or p['d']} is within a day and 400 ft of {len(rows)} police deaths: match it by hand"
        if rows:
            used.add(id(rows[0]))
            pairs.append((p, rows[0]))
            near += 1
    for p, r in pairs:
        # The light rows leave out the 2022 to 2024 deaths (hin-people-map.py joins those to the log itself), so a
        # joined death is from 2025 on and the 2022-2024 figures don't move.
        assert r["d"][:4] == p["d"][:4] and r["d"] >= "2025", f"fatality-log death {p['lid']} ({p['d']}) and police case {r['cs']} ({r['d']}) don't pair"
        p.update(lg=0, u=r["u"], d=r["d"], h=None if r["h"] < 0 else r["h"], ck=r["ck"], sk=r["sk"], cause=r["cause"], sc=sub_label(r),
                 op=r["op"], at=r["at"], hood=hoods[r["hood"]], hy=r["hy"], hs=r["hs"], hs22=r["hs22"], cs=p["cs"] or r["cs"])
        joined += 1
    left = [r for r in light if id(r) not in used]
    assert len(left) + joined == len(light) and joined == len(pairs) == len(used)
    still = [p for p in people if p["lg"]]
    assert all(not p["ck"] and not p["op"] for p in still), "a death with no police row carries a cause or an other party"
    print(f"fatality log: {joined} deaths joined to their police row ({joined - near} by case number, {near} by day and place); "
          f"{len(still)} with no police row drawn and not counted; {sum(1 for r in left if r['sv'] == 0 and r['d'] >= '2022')} police deaths from 2022 on not in the log", file=sys.stderr)
    return left, joined


def check_one_person_per_death(people, light):
    """Stops the run unless the deaths the page draws and the deaths it counts are the same people under any one cause
    and any one other party. The page draws every carded person and every light person, and counts the ones not `lg`
    (site/src/safety-map/map.js shownFor() and applyFilters()); site/tests/safety-map-test.mjs runs the same comparison
    through the page's own filter. `people` are the carded people, `light` the rest."""
    for key in ("ck", "op"):
        drawn = collections.Counter(p[key] for p in people + light if p.get("sv", 0 if p.get("k") else 1) == 0 and p[key] and p.get("c"))
        counted = collections.Counter(p[key] for p in people + light if p.get("sv", 0 if p.get("k") else 1) == 0 and p[key] and p.get("c") and not p["lg"])
        assert drawn == counted, f"deaths drawn and counted differ by {key}: {sorted((drawn - counted).items()) + sorted((counted - drawn).items())}"
    return True


THROUGH = ROOT / "data/extract/through-traffic/blocks.json"   # from tools/street-safety/through-traffic.py


def through_layer(T):
    """Through traffic per traffic row (tools/street-safety/through-traffic.py): row index, share in tenths of a percent, car trips
    a weekday, through cars and low-confidence flag. Rows the model doesn't carry are left out and drawn grey."""
    X = json.loads(THROUGH.read_text())
    at = {str(c): i for i, c in enumerate(T["cnn"])}
    rows = sorted((at[c], b) for c, b in X["blocks"].items() if c in at)
    assert len(rows) == len(X["blocks"]), f"{len(X['blocks']) - len(rows)} through-traffic blocks are not traffic rows"
    out = {"i": [i for i, _ in rows], "s": [round(b["share"] * 1000) for _, b in rows], "v": [b["cars"] for _, b in rows],
           "t": [b["through"] for _, b in rows], "l": [b["low"] for _, b in rows],
           "c": [b["cls"] for _, b in rows], "classes": X["classes"], "minCars": X["min_cars"], "runs": X["runs"],
           "jitter": X["jitter"], "minBin": X["min_cars_bin"],
           # The same figures for each hour bin, keyed by the map's time-of-day filter values.
           "bins": {n: {"s": [round(b["bins"][n]["share"] * 1000) for _, b in rows], "v": [b["bins"][n]["cars"] for _, b in rows],
                        "l": [b["bins"][n]["low"] for _, b in rows], "c": [b["bins"][n]["cls"] for _, b in rows]}
                    for n in X["bins"]},
           # The distance slider's figures (Bryan, 2026-11-19): each distance's share, flag and
           # class for the whole day and each bin; car trips are the same at every distance.
           "nears": [n for n, _ in X.get("nears", [["mile", 0]])], "defaultNear": X.get("default_near", "mile"),
           "near": {d: {"s": [round(b["near"][d]["all"]["share"] * 1000) for _, b in rows], "l": [b["near"][d]["all"]["low"] for _, b in rows],
                        "c": [b["near"][d]["all"]["cls"] for _, b in rows],
                        "bins": {n: {"s": [round(b["near"][d][n]["share"] * 1000) for _, b in rows], "l": [b["near"][d][n]["low"] for _, b in rows],
                                     "c": [b["near"][d][n]["cls"] for _, b in rows]} for n in X["bins"]}}
                    for d, _ in X.get("nears", [])}}
    # The map's road (res or main) is the traffic row's own (p[10]); the extract carries the same split.
    for i, b in rows:
        assert (T["p"][i][10] == 0) == (b["road"] == "res"), f"row {i}: road differs between the traffic rows and through-traffic"
    return out, X["summary"]


def other_parties(people, light, LM):
    """Give each person with a card their other party (`op`) from the light extract's `card_other` by victim id, drop the
    id, and return the count per option over every police-report person. Deaths from the fatality log or the news start
    with `op` "": log_deaths() gives the ones the police also reported their police row's, and the filter takes the
    rest off the map, as the cause filter does. Checks the options
    are the page's (state.js OTHERS), and that every police-report person has exactly one."""
    keys = LM["others"]
    state = (ROOT / "site/src/safety-map/state.js").read_text()
    page = re.findall(r'\["([a-z]+)", "[^"]+"\]', state.split("var OTHERS = ")[1].split(";")[0])
    assert page == keys, f"state.js OTHERS {page} differ from street-safety-light.py's {keys}"
    for p in people:
        vid = p.pop("vid", "")
        if p["lg"]:
            p["op"] = ""
            continue
        assert vid in LM["card_other"], f"card person {vid or p['cs']} is not in light-injuries.json card_other: rerun street-safety-light.py"
        p["op"] = keys[LM["card_other"][vid]]
    n = collections.Counter(p["op"] for p in people + light if not p["lg"])
    total = sum(1 for p in people + light if not p["lg"])
    assert set(n) <= set(keys) and sum(n.values()) == total, "a police-report person has no other-party option"
    print("other party: " + ", ".join(f"{k} {n[k]}" for k in keys) + f"; sum {sum(n.values())} of {total} police-report people", file=sys.stderr)
    # The About page says when the unknown vehicles are from: the count in 2005 to 2012, before the types were stated.
    early = sum(1 for p in light if p["op"] == "unknown" and p["d"] < "2013-01-01")
    return {k: n[k] for k in keys}, early


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


LAST = ("Other", "Unknown or not stated")
# A few words for each subcause, for the corner chart's bars, which have room for about 25 characters on a phone; the
# filter's list and the bar's tooltip carry the full label from hin-injury-kinds.py SUBCAUSE. A key with no entry here
# uses its full label without the section number.
SHORT_SUB = {
    "22350": "Unsafe speed", "21453(a)": "Ran a red light", "21954(a)": "Outside a crosswalk", "21955": "Mid-block between signals",
    "21453(d)": "Against a red light", "21950(b)": "Stepped into traffic", "21456": "Against the walk signal",
    "22107": "Unsafe turn or lane change", "21658(a)": "Left a lane unsafely", "21804(a)": "Out of a driveway or alley",
    "21755(a)": "Passed on the right", "22100": "Turned from the wrong lane", "22101(d)": "Ignored a turn sign",
    "22102": "Mid-block U-turn", "21950(a)": "Didn't yield in a crosswalk", "23152(a)": "Alcohol", "23153(a)": "Alcohol, injuring someone",
    "23152(g)": "Alcohol and drugs", "23153(f)": "Drugs, injuring someone", "21801(a)": "Left turn, not yielding",
    "22450(a)": "Ran a stop sign", "21703": "Following too closely", "22517": "Opened a door into traffic",
    "22106": "Started or backed unsafely", "21663": "Drove on the sidewalk", "21657": "Wrong way on a one-way",
    "21650": "Not keeping right", "21800(a)": "Didn't yield at a junction", "21460(a)": "Crossed double yellow lines",
    "21650.1": "Biked against traffic", "21750": "Passed on the left", "21461(a)": "Ignored a sign or signal",
    "21802(a)": "Didn't yield after a stop", "21954(b)": "No care for a pedestrian", "21235(g)": "Scooter on the sidewalk",
    "21651(b)": "Left of a median", "none": "No code recorded", "UNKNOWN": "Recorded as unknown",
}   # drawn after the named causes, whatever their size


def cause_tree(people):
    """Each police-report person's cause key `ck`, and the tree of causes and their subcauses with labels and counts."""
    police = [p for p in people if not p["lg"]]
    assert all(p["sk"] and p["sc"] for p in police), "a police-report person has no subcause: rerun hin-injury-kinds.py"
    for p in people:
        p["ck"] = slug(p["cause"]) if not p["lg"] else ""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in police:
        by[p["cause"]][p["sk"]].append(p)
    labels = {}
    for p in police:
        assert labels.setdefault((p["cause"], p["sk"]), p["sc"]) == p["sc"], f"two labels for {p['cause']} {p['sk']}"
    tree = []
    for c in sorted(by, key=lambda c: (c in LAST, LAST.index(c) if c in LAST else 0, -sum(map(len, by[c].values())), c)):
        subs = sorted(by[c], key=lambda k: (k == "other", -len(by[c][k]), k))
        tree.append({"key": slug(c), "label": c, "n": sum(len(v) for v in by[c].values()),
                     "subs": [{"key": k, "label": labels[(c, k)], "n": len(by[c][k]),
                               "short": "Other codes" if k == "other" else SHORT_SUB.get(k, re.sub(r" \(VC [^)]*\)$", "", labels[(c, k)]))}
                              for k in subs]})
    assert len({t["key"] for t in tree}) == len(tree), "two causes share a key"
    long = [s["short"] for t in tree for s in t["subs"] if len(s["short"]) > 28]
    assert not long, f"subcause bar labels over 28 characters, add them to SHORT_SUB: {long}"
    assert sum(t["n"] for t in tree) == len(police) and all(sum(s["n"] for s in t["subs"]) == t["n"] for t in tree)
    return tree


CRIME_DIR = ROOT / "data/extract/sfpd-person-crimes"
# The Kind of crime filter's keys (site/src/safety-map/state.js CRIME_KINDS), in sfpd-person-crimes.py GROUPS order.
CRIME_KINDS = ["Violence and weapons", "Theft, burglary and fraud", "Vandalism and arson", "Drugs", "Other"]


def crime_layer(H):
    """crime.json: every report since 2018 by place, from sfpd-person-crimes.py's all-years.json, with each place's
    neighborhood and its cells gap-encoded. Checks the cells add up to each place's groups and the years to meta's."""
    meta = json.loads((CRIME_DIR / "meta.json").read_text())
    rows = json.loads((CRIME_DIR / "all-years.json").read_text())
    G, years = len(meta["groups"]), meta["years"]
    assert meta["groups"] == CRIME_KINDS, f"crime groups {meta['groups']} differ from the map's kinds {CRIME_KINDS}"
    assert years == list(range(2018, years[-1] + 1)), f"crime years {years}"
    # The map's state module must offer the same years and times of day the cells encode.
    state = (ROOT / "site/src/safety-map/state.js").read_text()
    newest = int(re.search(r"NEWEST_YEAR = (\d{4})", state).group(1))
    assert newest == years[-1], f"state.js NEWEST_YEAR {newest}, the crime data runs to {years[-1]}: move NEWEST_YEAR"
    times = re.findall(r'\["(\w+)", "[^"]+", \d+, \d+\]', state.split("var TIMES = ")[1].split(";")[0])
    assert times == [p[0] for p in meta["periods"]], f"state.js TIMES {times} differ from the cells' periods {meta['periods']}"
    span = G * 7 * 6
    by_year, cells_out = [0] * len(years), []
    for r in rows:
        cells, by_g, gap, prev = r[3 + G], [0] * G, [], -1
        for cell, n in zip(cells[::2], cells[1::2]):
            assert cell > prev and n > 0, f"crime place {r[:3]}: cells out of order"
            by_g[cell // 42 % G] += n
            by_year[cell // span] += n
            gap += [cell - prev, n]
            prev = cell
        assert by_g == r[3:3 + G] and sum(by_g) == r[2], f"crime place {r[:3]}: cells don't add up"
        cells_out.append(gap)
    assert by_year == [meta["years_by_year"][str(y)] for y in years], "crime reports by year differ from the extract's"
    H.zero = H.two = 0
    hood = [H.hood((r[0], r[1])) for r in rows]
    assert H.two == 0, f"{H.two} crime places in two neighborhoods"
    print(f"crime: {len(rows)} places, {sum(by_year)} reports {meta['years_from']} to {meta['years_to']}, {H.zero} places in no neighborhood", file=sys.stderr)
    return {"groups": meta["groups"], "years": years, "from": meta["years_from"], "to": meta["years_to"], "fetched_on": meta["years_fetched_on"],
            "byYear": by_year, "x": [round(r[0] * 1e5) for r in rows], "y": [round(r[1] * 1e5) for r in rows], "hood": hood, "cells": cells_out}


def figures(data):
    """The counts the story and the figures panel quote, recomputed from the map's own rows."""
    police = [p for p in data["people"] if not p["lg"]]
    walk = [p for p in police if p["u"] == "Walking"]
    corner = lambda p: p["at"] == 1   # noqa: E731  hin-injury-kinds.py's `at`: the report puts the crash at the intersection
    T = data["traffic"]
    blocks = {}
    for cnn, p in zip(T["cnn"], T["p"]):
        if p[10] == 0:   # residential
            blocks[cnn] = p
    with_fig = [p for p in blocks.values() if p[0] >= 0]
    measured = [p for p in with_fig if p[7] in (0, 1, 5, 6)]   # SFMTA count, Slow Streets count or Telraam counter
    return {
        "people": len(police), "killed": sum(p["k"] for p in police),
        "off_hin_2024": sum(1 for p in police if not p["hy"] & 4),
        "on_hin_2022": sum(1 for p in police if p["hy"] & 2),
        "on_hin_2024": sum(1 for p in police if p["hy"] & 4),
        "at_intersection": sum(1 for p in police if corner(p)),
        "walking": len(walk), "walking_at_intersection": sum(1 for p in walk if corner(p)),
        "residential_blocks": len(blocks), "residential_with_figure": len(with_fig),
        "residential_measured": len(measured),
        "residential_measured_90_plus": sum(1 for p in measured if p[0] >= 1),
        "residential_any_90_plus": sum(1 for p in with_fig if p[0] >= 1),
        "deaths_outside_police_reports": sum(1 for p in data["people"] if p["lg"]),
    }


def main():
    B = hpm.build()
    data = dict(B["data"])
    data.pop("crashes")   # the scratch map's copy; the site's cards are tools/street-safety/street-safety-cards.py's files
    stats = B["stats"]
    police = [p for p in data["people"] if not p["lg"]]
    assert len(police) == 922, f"{len(police)} police-report people, expected 922"
    assert all("hy" in p for p in data["people"]), "a person has no HIN bits"
    cased = {p["cs"] for p in police if p["cs"]}
    carded = set()
    for f in (OUT / "cards").glob("*/*.json"):
        carded.update(json.loads(f.read_text())["cards"])
    assert cased <= carded, f"{len(cased - carded)} people with a case number have no crash card (run tools/street-safety/street-safety-cards.py)"
    assert len(data["traffic"]["cnn"]) == len(data["traffic"]["p"]), "traffic block ids and rows differ in length"
    # Deaths from the fatality log or the news have no police location type, so neither place filter shows them.
    for p in data["people"]:
        if p["lg"]:
            p["at"] = -1
    both = count_rule_holds(data["traffic"])
    print(f"{both} traffic rows have both an SFMTA figure and a Telraam counter; COUNT_RULE {data['traffic']['rule']['rule']!r}",
          file=sys.stderr)
    # The date the people, the crime reports and the Telraam counters were read, from the extracts themselves (Telraam's
    # window ends on the day it was read): the sfdata cache date of a re-read centerline would move it with no new data.
    read = newest_date(stats["sources"]["people"], data["crimeStats"]["fetched_on"],
                       json.loads((ROOT / "data/extract/telraam/segments.json").read_text())["window"][1])
    assert read, "no read date in the sources"
    H = Hoods()
    C = hpm.sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                         where="active='true'", floor=15000)
    data["bci"] = bci_layer(C, H)
    data["hoods"] = neighborhoods(H)
    data["muni"], muni_meta = muni_lines()
    # The area filter by neighborhood: people by their own `hood` (hin-people-map.py, the unthinned outlines), and every
    # crime place and traffic block by the index of the neighborhood holding its point or its run's midpoint.
    idx = {n: i for i, n in enumerate(H.names)}
    assert all(not p["hood"] or p["hood"] in idx for p in data["people"]), "a person's neighborhood is not one of the 41"
    # The crime view's places travel in crime.json (crime_layer), loaded when the view first opens; map.json keeps only
    # the person-crime figures (crimeStats) and the Muni stops.
    for k in ("crimeAll", "crimeDays", "crimeGroups"):
        data.pop(k, None)
    crime = crime_layer(H)
    H.zero = H.two = 0
    data["traffic"]["hood"] = [H.hood(midpoint(r)) for r in decode(data["traffic"]["runs"])]
    assert len(data["traffic"]["hood"]) == len(data["traffic"]["p"]), "traffic runs and rows differ in length"
    assert H.two == 0, f"{H.two} traffic blocks in two neighborhoods"
    police_by = collections.Counter(p["hood"] for p in data["people"] if not p["lg"])
    print(f"neighborhoods: police people {sum(v for k, v in police_by.items() if k)} in one, {police_by.get('', 0)} in none", file=sys.stderr)
    # The fixed High-injury areas and the LTS layers are replaced by the area filter and the BCI classes.
    for k in ("areas", "lts3", "lts4"):
        data.pop(k, None)
    data["through"], through_sum = through_layer(data["traffic"])
    data["causes"] = cause_tree(data["people"])
    light, LM = light_people(H, data["causes"])
    hpm.hin_bits([p for p in light if not p.get("np")])
    for p in light:
        if p.get("np"):
            p["hy"] = 0
    # Every 2022 to 2024 severe or fatal row is counted once: with a card here, or with no point in the light extract.
    assert len(police) == len(LM["card_other"]), f"{len(police)} people with cards, {len(LM['card_other'])} rows with a point in light-injuries.json"
    data["others"], data["othersUnknownTo2012"] = other_parties(data["people"], light, LM)
    data["hinGroups"] = hin_groups_layer(data["people"] + light)
    data["hinGroups22"] = hin_groups_layer(data["people"] + light, "2022")
    LM["cks"] = sorted({p["ck"] for p in light})
    LM["sks"] = sorted({p["sk"] for p in light})
    # The 2022-2024 figures are taken before the fatality log's deaths join their police rows, which are from 2025 on.
    F = figures(data)
    light, joined = log_deaths(data["people"], light, data["causes"], H.names)
    check_one_person_per_death(data["people"], light)
    F["deaths_outside_police_reports"] = sum(1 for p in data["people"] if p["lg"])
    F["log_deaths_with_police_report"] = joined
    recent = [p for p in light if p["d"] >= "%d-01-01" % INLINE_FROM]
    older = [p for p in light if p["d"] < "%d-01-01" % INLINE_FROM]
    assert len(recent) + len(older) == len(light) and recent and older
    print(f"light people: {len(recent)} inline from {INLINE_FROM}, {len(older)} in the older file", file=sys.stderr)
    data["light"] = dict(light_columns(recent, LM), levels=LM["levels"], sources=LM["sources"], newest=LM["newest_row"],
                         by_level_year=LM["by_level_year"], older={"file": "people-2005-2020.json", "n": len(older), "from": 2005, "to": INLINE_FROM - 1})
    older_cols = light_columns(older, LM)
    data["worst"] = worst_layer(C)
    F["through"] = through_sum
    # The police-report people counted and not drawn (no place in the record), for the About page.
    F["no_place"] = sum(1 for p in light if p.get("np"))
    data["meta"] = {"read": read, "figures": F, "sources": stats["sources"], "countRule": data["traffic"]["rule"]["text"],
                    "k": data["traffic"]["k"], "muni": muni_meta,
                    "bci": {k: data["bci"][k] for k in ("matched", "unmatched", "unscored")}}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, obj in (("map.json", data), ("people-2005-2020.json", older_cols), ("crime.json", crime)):
        text = json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n"
        # Staff addresses are the city's to publish; institutional inboxes would be fine, but none belong here.
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f"{name}: an e-mail address reached the site data"
        path = OUT / name
        if not path.exists() or path.read_text() != text:
            # Written beside the target and swapped in, so the dev server never serves a half-written file.
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(text)
            os.replace(tmp, path)
        print(f"{path.relative_to(ROOT)}: {len(text) // 1024} KB", file=sys.stderr)
    print(json.dumps({"read": read, **F}, indent=1), file=sys.stderr)


if __name__ == "__main__":
    main()
