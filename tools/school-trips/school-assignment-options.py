#!/usr/bin/env python3
"""Straight-line home-to-school distance for children 5-9 under SFUSD's three elementary assignment options, with the year-by-year phase-in.

    tools/school-trips/school-assignment-options.py      # writes out/school-assignment/options.json

Bryan, 2026-10-01, on the Safe School Connections doc:
"If you can model it please try." No routing: every distance is the straight
line from a census block's centroid to a school's point, in miles. Light enough
to run anywhere; no heavy-job wrapper needed.

INPUTS (all already in the repo, nothing fetched):
  * out/school-travel/blocks.json   children 5-9 per census block (Census 2020
    DHC P12) and each block's SFUSD elementary attendance area (DataSF e6tr-sxwg).
  * out/school-travel/summary.json  attendance area -> its school (name match).
  * site/data/bike-history/reach.json  school points (CDE directory, DataSF 7e7j-59qk).

THE OPTIONS, as modelled:
  * neighborhood: every child at their attendance-area school. This is also
    the "guaranteed school" half of options B and C.
  * citywide: a child in a citywide program goes to one of the SFUSD
    elementary schools that have no attendance area (CITYWIDE below), each
    equally likely: again an upper bound. Newcomer-only schools and charters are left out.
  * C, neighborhood + citywide programs: (1 - c) neighborhood + c citywide,
    c in CITYWIDE_SHARES.
  * A, small zones: the 58 attendance-area schools grouped into zones of
    nearby schools by average-linkage clustering of their points, with a size
    cap (ZONINGS). A zone child goes to each of the zone's schools with equal
    chance: the no-preference case, an upper bound on distance, since real
    choosers lean to nearer schools. The neighborhood figure is the best case (every family gets its
    nearest). Zone sizes: ZONINGS gives each zoning's smallest and largest. Then the same citywide share c as C. SFUSD has not published a
    zone map, so these zones are ours.
  * B, neighborhood + any school with open seats: p stay at their
    attendance-area school and 1 - p go where today's choosers go. "Where
    today's choosers go" is solved from the SFCTA K-5 bands (TODAY) and the
    share of K-5 students at their attendance-area school, from SFUSD's Board
    study session of 2026-08-18 (TODAY_AA_SHARE): today = a0 x neighborhood + (1 - a0) x elsewhere.

PHASE-IN: the new system takes the entering grades (TK and K) in its first
year and one more grade each year after, with every continuing student keeping
their school. Grades are weighted by SFUSD's 2024-25 district-run enrollment
(CDE, read from data/school-car-share/inputs.json, the same figures the lever
model uses), where TK is about a third the size of the other grades. Share
under the new system in year n (n = 0 first year) = enrollment in the first
n + 2 grades of TK-5 / TK-5 enrollment; the blended distance bands
are share x option + (1 - share) x today. Sibling priority for a school
outside the new rules would slow this; it is not modelled.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402

OUT = os.path.join(ROOT, "out", "school-assignment", "options.json")

# SFCTA School Access Plan (May 2023), Fig. 5: K-5 SFUSD home-to-school distance.
TODAY = {"under_1": 0.506, "1_to_2": 0.215, "over_2": 0.278}
# SFUSD Board study session 1 (2026-08-18), slide 40: "6K (30%) attend their
# attendance area school" of K-5 students; 15% attend a citywide school.
TODAY_AA_SHARE = 0.30
CITYWIDE_SHARES = (0.0, 0.15, 0.30)
STAY_SHARES = (0.4, 0.6, 0.8)
ZONINGS = {"zones_of_2_to_3": (2, 3), "zones_of_3_to_5": (3, 5)}
FIRST_YEAR = 2028  # 2028-29: first entering class under the new system
TK5_ORDER = ["TK", "K", "1", "2", "3", "4", "5"]
ENTRY_GRADES = 2   # TK and K
ENROLLMENT = os.path.join(ROOT, "data", "school-car-share", "inputs.json")
CHARTERS = {"Mission Preparatory", "Thomas Edison Charter Academy", "Creative Arts Charter",
            "The New School of San Francisco", "KIPP Bayview Elementary"}
NEWCOMER = {"Lee (Edwin and Anita) Newcomer", "Mission Education Center"}
MI = 3958.8
# No two schools in one zone more than this far apart, so a zone never spans
# Golden Gate Park or Lake Merced. A school with no neighbour in reach stays in
# a smaller zone than ZONINGS asks for.
MAX_ZONE_MILES = 2.0


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return json.load(f)


def miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * MI * math.asin(math.sqrt(h))


def bands(pairs):
    """pairs: (weight, miles). Share of weight in each band, and the weighted mean."""
    tot = sum(w for w, _ in pairs)
    out = {"under_1": 0.0, "1_to_2": 0.0, "over_2": 0.0}
    mean = 0.0
    for w, d in pairs:
        out["under_1" if d < 1 else "1_to_2" if d <= 2 else "over_2"] += w
        mean += w * d
    res = {k: v / tot for k, v in out.items()}
    res["mean_miles"] = mean / tot
    return res


def mix(parts):
    """parts: (share, bands). Weighted blend of band dicts."""
    keys = ("under_1", "1_to_2", "over_2")
    out = {k: sum(s * b[k] for s, b in parts) for k in keys}
    if all("mean_miles" in b for _, b in parts):
        out["mean_miles"] = sum(s * b["mean_miles"] for s, b in parts)
    return out


def rnd(b):
    return {k: round(v, 3) for k, v in b.items()}


def cluster(points, lo, hi):
    """Average-linkage agglomeration of school points into zones of lo to hi schools, none wider than MAX_ZONE_MILES.

    Merges the closest pair that fits until the mean zone reaches
    (lo + hi) / 2 schools, then folds every zone smaller than lo into its
    nearest neighbour that still fits; one with none stays small."""
    groups = [[i] for i in range(len(points))]

    def link(g, h):
        return sum(miles(points[i], points[j]) for i in g for j in h) / (len(g) * len(h))
    def diameter(g):
        return max([miles(points[i], points[j]) for i in g for j in g] + [0.0])

    def fits(g, h):
        return len(g) + len(h) <= hi and diameter(g + h) <= MAX_ZONE_MILES
    target = (lo + hi) / 2.0
    while len(points) / float(len(groups)) < target:
        best = None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                if fits(groups[a], groups[b]):
                    d = link(groups[a], groups[b])
                    if best is None or d < best[0]:
                        best = (d, a, b)
        if best is None:
            break
        _, a, b = best
        groups[a] = sorted(groups[a] + groups[b])
        del groups[b]
    stuck = []
    while True:
        small = sorted((len(g), g) for g in groups if len(g) < lo and g not in stuck)
        if not small:
            break
        g = small[0][1]
        room = [h for h in groups if h is not g and fits(g, h)]
        if not room:
            stuck.append(g)  # no neighbour within MAX_ZONE_MILES has room: stays small
            continue
        h = min(room, key=lambda h: (link(g, h), h))
        groups = [x for x in groups if x is not g and x is not h] + [sorted(g + h)]
    return sorted(groups)


def main():
    blocks = read("out", "school-travel", "blocks.json")["blocks"]
    summary = read("out", "school-travel", "summary.json")
    reach = read("site", "data", "bike-history", "reach.json")
    pts = {s["name"]: (s["lon"], s["lat"]) for s in reach["schools"] if not s["closed"] and not s["private"]}
    area_school = {m["area"]: m["school"] for m in summary["attendance_area"]["matches"]}
    aa_schools = sorted(set(area_school.values()))
    sfusd_elem = sorted(s["name"] for s in summary["schools"]["list"]
                        if not s["private"] and "elementary" in s["levels"] and s["name"] not in CHARTERS)
    citywide = [n for n in sfusd_elem if n not in aa_schools and n not in NEWCOMER]
    missing = [n for n in aa_schools + citywide if n not in pts]
    assert not missing, missing

    kids = [(b["a5_9"], (b["lon"], b["lat"]), b["attendance"]["area"]) for b in blocks
            if b["a5_9"] and b.get("attendance")]
    total = sum(k for k, _, _ in kids)
    assert total == summary["attendance_area"]["children_5_9_in_areas"], total

    nb = bands([(k, miles(p, pts[area_school[a]])) for k, p, a in kids])
    cw = bands([(k / float(len(citywide)), miles(p, pts[s])) for k, p, _ in kids for s in citywide])

    zonings = {}
    for label, (lo, hi) in ZONINGS.items():
        groups = cluster([pts[s] for s in aa_schools], lo, hi)
        zone_of = {aa_schools[i]: [aa_schools[j] for j in g] for g in groups for i in g}
        zb = bands([(k / float(len(zone_of[area_school[a]])), miles(p, pts[s]))
                    for k, p, a in kids for s in zone_of[area_school[a]]])
        sizes = sorted(len(g) for g in groups)
        zonings[label] = {"zones": len(groups), "schools_per_zone": sizes, "zone_only": rnd(zb),
                          "with_citywide": {str(c): rnd(mix([(1 - c, zb), (c, cw)])) for c in CITYWIDE_SHARES},
                          "zones_list": [[aa_schools[i] for i in g] for g in groups]}

    a0 = TODAY_AA_SHARE
    elsewhere = {k: (TODAY[k] - a0 * nb[k]) / (1 - a0) for k in TODAY}
    assert all(v >= 0 for v in elsewhere.values()), elsewhere
    opt_b = {str(p): rnd(mix([(p, nb), (1 - p, elsewhere)])) for p in STAY_SHARES}
    opt_c = {str(c): rnd(mix([(1 - c, nb), (c, cw)])) for c in CITYWIDE_SHARES}

    def phase(target):
        rows = []
        with open(ENROLLMENT) as fh:
            enr = json.load(fh)["measured"]["enrollment_2024_25_noncharter"]["by_grade"]
        tk5 = sum(enr[g] for g in TK5_ORDER)
        for n in range(len(TK5_ORDER) - ENTRY_GRADES + 2):
            share = sum(enr[g] for g in TK5_ORDER[:n + ENTRY_GRADES]) / float(tk5)
            rows.append({"year": "%d-%02d" % (FIRST_YEAR + n, (FIRST_YEAR + n + 1) % 100),
                         "share_tk5_new": round(share, 3), "bands": rnd(mix([(share, target), (1 - share, TODAY)]))})
            if share >= 1:
                break
        return rows

    out = {
        "note": "Straight-line miles, census block centroid to school point, children 5-9 (Census 2020) "
                "weighted by block. Bands: under 1 mile, 1 to 2 miles, over 2 miles. Method in the script's docstring.",
        "children_5_9": total,
        "sfusd_elementary_schools": len(sfusd_elem),
        "attendance_area_schools": len(aa_schools),
        "citywide_schools": citywide,
        "citywide_share_by_school_count": round(len(citywide) / float(len(sfusd_elem) - len(NEWCOMER)), 3),
        "today_sfcta": TODAY,
        "today_assigned_to_attendance_area_school": round(a0, 3),
        "today_elsewhere_solved": rnd(elsewhere),
        "neighborhood_only": rnd(nb),
        "citywide_school_trip": rnd(cw),
        "option_a_small_zones": zonings,
        "option_b_neighborhood_plus_open_seats": opt_b,
        "option_c_neighborhood_plus_citywide": opt_c,
        "phase_in": {
            "first_year": "%d-%02d" % (FIRST_YEAR, (FIRST_YEAR + 1) % 100),
            "option_a_zones_of_2_to_3_c0.15": phase(mix([(0.85, read_z(zonings)), (0.15, cw)])),
            "option_b_p0.6": phase(mix([(0.6, nb), (0.4, elsewhere)])),
            "option_c_c0.15": phase(mix([(0.85, nb), (0.15, cw)])),
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stable.write_json(OUT, out, indent=1, sort_keys=True)
    print("wrote %s" % os.path.relpath(OUT, ROOT))
    print("children 5-9: %d; SFUSD elementary %d; attendance-area %d; citywide %d" % (
        total, len(sfusd_elem), len(aa_schools), len(citywide)))
    show = [("today (SFCTA)", TODAY), ("neighborhood only", nb), ("citywide trip", cw)]
    show += [("C c=%s" % c, v) for c, v in opt_c.items()]
    show += [("A %s c=0.15" % l, z["with_citywide"]["0.15"]) for l, z in zonings.items()]
    show += [("B p=%s" % p, v) for p, v in opt_b.items()]
    for name, b in show:
        print("  %-28s <1 %5.1f%%  1-2 %5.1f%%  >2 %5.1f%%  mean %s" % (
            name, 100 * b["under_1"], 100 * b["1_to_2"], 100 * b["over_2"],
            "%.2f mi" % b["mean_miles"] if "mean_miles" in b else "-"))


def read_z(zonings):
    z = zonings["zones_of_2_to_3"]["zone_only"]
    return {k: z[k] for k in ("under_1", "1_to_2", "over_2", "mean_miles")}


if __name__ == "__main__":
    main()
