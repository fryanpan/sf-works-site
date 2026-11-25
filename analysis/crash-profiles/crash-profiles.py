#!/usr/bin/env python3
"""A first-cut LADOT-style crash profile analysis for San Francisco, read off the crash-augment tables.

    python3 analysis/crash-profiles/crash-profiles.py                  # 2017-2024, writes out/crash-augment/profiles/results.json
    python3 analysis/crash-profiles/crash-profiles.py --years 2018 2024

It reads out/crash-augment/tables/{crashes,parties,victims}.csv (built by pipeline/crash-augment/crash-augment.py)
and the street centerlines the street lane holds (data/socrata-cache/crash-augment-street/3psu-pn9h-*.json), and
writes one JSON file of counts. Standard library only.

WHAT IT COUNTS
  An injury crash is a row of ubvf-ztfx. A KSI crash has collision_severity Fatal or Injury (Severe). A KSI person is
  a victims row (nwes-mmgh) with victim_degree_of_injury Fatal Injury or Severe Injury.

LEVEL 1, THE COARSE GRID. Each crash falls in one cell of movement group x violation group x time band.
  movement   the at-fault party's move_pre_acc, grouped by MOVEMENT. The at-fault party is the crash's party_at_fault
             number; when that is blank, the party with at_fault Yes; when none, party 1. When the at-fault party is
             a pedestrian, the movement is the first vehicle party's instead, since a fix acts on the vehicle.
  violation  vz_pcf_group (the primary collision factor), grouped by VIOLATION.
  time       collision_time and day_of_week, grouped by TIME_BANDS.
  A cell is tested only if it holds at least MIN_KSI_PEOPLE KSI people. A tested cell is a profile when its KSI crash
  rate (KSI crashes / injury crashes in the cell) is above the citywide rate by a one-sided exact binomial test at
  ALPHA divided by the number of cells tested (Bonferroni). Rate above the citywide rate is the same statement as
  "its share of KSI crashes exceeds its share of injury crashes". Over-representation is reported as the cell's share
  of KSI people divided by its share of injury crashes.

LEVEL 2. Each profile is split by the finer fields in SPLITS. A split is flagged when the KSI rate differs across its
  categories by a chi-square test of homogeneity at ALPHA / (profiles x splits); the doc decides which flagged splits
  point at a different fix.

CONTEXT PROFILES. For each street-context field, each value's share of KSI people against its share of injury
  crashes, and for street class and corner type its share of the network (block length; intersections). Each field
  carries the mix of its _basis column, so a reader can see which are current_state_only.

VEHICLE WEIGHT. Pedestrians hurt in crashes with exactly one motor vehicle party, by that vehicle's
  estimated_vehicle_weight_lb band. Reported for every weighted vehicle and for model-matched weights alone
  (exact_make_model_year, model_10yr_avg), since a body_type_avg weight only restates the body type. A Mantel-Haenszel
  odds ratio, stratified by street class and light, checks whether the gap survives the obvious confounders.

Every figure is a correlation in police-reported injury crashes. Nothing here says a field causes severity.
"""

import argparse
import collections
import csv
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLES = os.path.join(ROOT, "out", "crash-augment", "tables")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "results.json")
sys.path.insert(0, os.path.join(ROOT, "pipeline", "crash-augment", "street"))
from street_fields import ROAD_CLASS, CLASS_RANK, SIGNAL_TYPES, street_key  # noqa: E402
from street_geo import line_coords  # noqa: E402

csv.field_size_limit(1 << 24)
MIN_KSI_PEOPLE = 20
ALPHA = 0.05
KSI_CRASH = {"Fatal", "Injury (Severe)"}
KSI_PERSON = {"Fatal Injury", "Severe Injury"}

MOVEMENT = {
    "Proceeding Straight": "going straight",
    "Making Left Turn": "left or U-turn", "Making U Turn": "left or U-turn",
    "Making Right Turn": "right turn",
    "Stopped": "stopped or slowing", "Stopped In Road": "stopped or slowing", "Slowing/Stopping": "stopped or slowing",
    "Changing Lanes": "lane change, merge, pass, entering", "Merging": "lane change, merge, pass, entering",
    "Passing Other Vehicle": "lane change, merge, pass, entering",
    "Entering Traffic": "lane change, merge, pass, entering",
    "Traveling Wrong Way": "wrong way or opposing lane", "Crossed Into Opposing Lane": "wrong way or opposing lane",
    "Crossed Into Opposing Lane - Unplanned": "wrong way or opposing lane",
    "Xing into Opposing Lane": "wrong way or opposing lane",
    "Parked": "parked or parking", "Parking Maneuver": "parked or parking",
    "Backing": "backing",
}
OTHER_MOVE = "not stated or other"  # Not Stated, Other, Ran Off Road, Other Unsafe Turning, blank

# vz_pcf_group prefixes (California Vehicle Code sections) to a violation group.
VIOLATION = [
    ("speeding", ("22350", "22351", "22352", "22356", "23103", "23109")),
    ("failure to yield to pedestrian", ("21950(a", "21954(b", "21952", "21951")),
    ("vehicle right of way", ("21800", "21801", "21802", "21803", "21804", "21806", "21451")),
    ("signals and signs", ("21453(a", "21453(b", "21453(c", "22450", "21461", "22101", "21457", "21452", "21454")),
    ("pedestrian violation", ("21954(a", "21453(d", "21955", "21950(b", "21456", "21956", "21949")),
    ("DUI", ("23152", "23153")),
    ("unsafe turn or lane use", ("22107", "22100", "22102", "22103", "22105", "21658", "21460", "21650", "21651",
                                 "21657", "21750", "21751", "21752", "21755", "21760")),
]
UNKNOWN_VIOL = ("", "Unknown", "Not Stated")


def violation_group(code):
    if code in UNKNOWN_VIOL:
        return "not stated"
    for name, prefixes in VIOLATION:
        if any(code.startswith(p) for p in prefixes):
            return name
    return "other"


TIME_BANDS = ("weekday commute (6-10 am, 4-7 pm)", "weekday midday (10 am-4 pm)", "weekend daytime (6 am-7 pm)",
              "evening (7-11 pm)", "late night (11 pm-6 am)", "time not stated")
WEEKEND = {"Saturday", "Sunday"}


def time_band(t, dow):
    try:
        h = int(t[:2])
    except ValueError:
        return TIME_BANDS[5]
    if h >= 23 or h < 6:
        return TIME_BANDS[4]
    if h >= 19:
        return TIME_BANDS[3]
    if dow in WEEKEND:
        return TIME_BANDS[2]
    return TIME_BANDS[1] if 10 <= h < 16 else TIME_BANDS[0]


def speed_band(v):
    try:
        v = int(v)
    except ValueError:
        return "unknown"
    return "25 or under" if v <= 25 else ("30" if v == 30 else "35 or more")


def lanes_band(v):
    try:
        v = int(v)
    except ValueError:
        return "unknown"
    return "0 (layer gap)" if v == 0 else ("1" if v == 1 else ("2" if v == 2 else "3 or more"))


def weight_band(w):
    try:
        w = float(w)
    except ValueError:
        return "no weight"
    return "under 3,500 lb" if w < 3500 else ("3,500 to 5,000 lb" if w <= 5000 else "over 5,000 lb")


def mode(v):
    """Who was involved, from dph_col_grp_description: pedestrian, bicycle (no pedestrian) or vehicles only."""
    if "Pedestrian" in v:
        return "pedestrian involved"
    if "Bicycle" in v:
        return "bicycle involved"
    return "vehicles only" if v == "Vehicle(s) Only Involved" else "not stated"


def light_band(v):
    return "daylight" if v == "Daylight" else ("dusk or dawn" if v == "Dusk - Dawn" else
                                               ("not stated" if v in ("Not Stated", "") else "dark"))


# ---- statistics, standard library ---------------------------------------------------------------------------

def binom_sf(k, n, p):
    """P(X >= k) for X ~ Binomial(n, p), summed in log space."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    base = math.lgamma(n + 1)
    terms = [base - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq for i in range(k, n + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def _gammq(a, x):
    """Regularized upper incomplete gamma Q(a, x) (Numerical Recipes series and continued fraction)."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(1000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-14:
                break
        return 1.0 - s * math.exp(-x + a * math.log(x) - gln)
    b, c, d = x + 1 - a, 1e300, 1.0 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1) < 1e-14:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_homogeneity(rows):
    """Chi-square test that the KSI rate is the same across categories. rows: [(crashes, ksi_crashes)]."""
    rows = [(n, k) for n, k in rows if n > 0]
    N, K = sum(n for n, _ in rows), sum(k for _, k in rows)
    if len(rows) < 2 or K == 0 or K == N:
        return None, None
    p = K / N
    x2 = sum((k - n * p) ** 2 / (n * p) + ((n - k) - n * (1 - p)) ** 2 / (n * (1 - p)) for n, k in rows)
    df = len(rows) - 1
    return x2, _gammq(df / 2.0, x2 / 2.0)


def mantel_haenszel(strata):
    """Pooled odds ratio of KSI, exposed vs reference, with its 95% interval (Robins, Breslow and Greenland 1986).
    strata: [(a, b, c, d)] with a = exposed KSI, b = exposed not, c = reference KSI, d = reference not."""
    R = S = PR = PS_QR = QS = 0.0
    for a, b, c, d in strata:
        n = a + b + c + d
        if not n:
            continue
        r, s_, p_, q = a * d / n, b * c / n, (a + d) / n, (b + c) / n
        R, S = R + r, S + s_
        PR, PS_QR, QS = PR + p_ * r, PS_QR + p_ * s_ + q * r, QS + q * s_
    if not R or not S:
        return None, None, None
    est = R / S
    se = math.sqrt(PR / (2 * R * R) + PS_QR / (2 * R * S) + QS / (2 * S * S))
    return est, est * math.exp(-1.96 * se), est * math.exp(1.96 * se)


# ---- reading -------------------------------------------------------------------------------------------------

def read(name, keep):
    with open(os.path.join(TABLES, name + ".csv"), newline="") as f:
        for r in csv.DictReader(f):
            if keep(r):
                yield r


def load(y0, y1):
    in_years = lambda r: y0 <= int(r["accident_year"] or 0) <= y1  # noqa: E731
    crashes = {r["case_id_pkey"]: r for r in read("crashes", in_years)}
    parties = collections.defaultdict(dict)
    for r in read("parties", in_years):
        parties[r["case_id_pkey"]][r["party_number_ckey"]] = r
    victims = list(read("victims", in_years))
    return crashes, parties, victims


def at_fault_party(crash, ps):
    """(party row or None, how it was found)."""
    n = crash["party_at_fault"]
    if n and n in ps:
        return ps[n], "party_at_fault"
    yes = [p for k, p in sorted(ps.items(), key=lambda kv: int(kv[0] or 0)) if p["at_fault"] == "Yes"]
    if yes:
        return yes[0], "at_fault_yes"
    if "1" in ps:
        return ps["1"], "party_1"
    return None, "none"


def first_vehicle(ps, exclude=None):
    for k, p in sorted(ps.items(), key=lambda kv: int(kv[0] or 0)):
        if p is not exclude and p["party_type"] not in ("Pedestrian",):
            return p
    return None


def move_group(v):
    return MOVEMENT.get(v, OTHER_MOVE)


# ---- network denominators ------------------------------------------------------------------------------------

def network(path):
    """Block length (miles) by street class, and intersections by corner type, from 3psu-pn9h active blocks."""
    rows = json.load(open(path))["rows"]
    miles = collections.Counter()
    node_streets = collections.defaultdict(dict)
    for r in rows:
        if r.get("active") not in (True, "True", "true"):
            continue
        cls = ROAD_CLASS.get(r.get("classcode")) or "other"
        length = 0.0
        for line in line_coords(r.get("line")):
            for (x1, y1), (x2, y2) in zip(line, line[1:]):
                dx = (x2 - x1) * math.cos(math.radians((y1 + y2) / 2)) * 69.172
                dy = (y2 - y1) * 69.0
                length += math.hypot(dx, dy)
        miles[cls] += length
        for n in (r.get("f_node_cnn"), r.get("t_node_cnn")):
            n = str(n or "").split(".")[0]
            if n:
                node_streets[n].setdefault(street_key(r.get("streetname")), []).append(cls)
    corners = collections.Counter()
    for n, streets in node_streets.items():
        best = {s: min(c, key=CLASS_RANK.get) for s, c in streets.items()}
        surface = {s: c for s, c in best.items() if c not in ("freeway", "ramp")} or best
        cl = sorted(surface.values(), key=CLASS_RANK.get)
        if len(cl) > 1:  # a node on one street is a bend or a dead end, not a corner
            corners["%s_x_%s" % (cl[0], cl[1])] += 1
    return miles, corners


# ---- analysis ------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", nargs=2, type=int, default=[2017, 2024])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    y0, y1 = a.years
    crashes, parties, victims = load(y0, y1)

    ksi_people = collections.Counter()
    ped_victims = collections.defaultdict(list)
    for v in victims:
        if v["victim_degree_of_injury"] in KSI_PERSON:
            ksi_people[v["case_id_pkey"]] += 1
        if v["victim_role"] == "Pedestrian":
            ped_victims[v["case_id_pkey"]].append(v)

    # one record per crash with every field the analysis groups by
    recs, how = [], collections.Counter()
    for cid, c in crashes.items():
        ps = parties.get(cid, {})
        af, method = at_fault_party(c, ps)
        how[method] += 1
        mover = af
        if af is not None and af["party_type"] == "Pedestrian":
            mover = first_vehicle(ps)
            how["pedestrian_at_fault_used_vehicle_movement"] += 1
        other = first_vehicle(ps, exclude=mover) if mover is not None else None
        heavy = c["heaviest_vehicle_weight_lb"]
        recs.append({
            "case": cid,
            "ksi": c["collision_severity"] in KSI_CRASH,
            "people": ksi_people[cid],
            "movement": move_group(mover["move_pre_acc"]) if mover else OTHER_MOVE,
            "violation": violation_group(c["vz_pcf_group"]),
            "time": time_band(c["collision_time"], c["day_of_week"]),
            "other party movement": move_group(other["move_pre_acc"]) if other else "no other vehicle party",
            "pedestrian action": c["ped_action"] or "not stated",
            "collision type": c["type_of_collision"] or "Not Stated",
            "who was involved": c["dph_col_grp_description"] or "not stated",
            "mode": mode(c["dph_col_grp_description"] or ""),
            "street class": c["street_class"] or "unknown",
            "corner type": c["corner_type"] or ("midblock" if c["corner_type_basis"] == "not_applicable" else "unknown"),
            "posted limit": speed_band(c["posted_speed_limit_mph"]),
            "lanes": lanes_band(c["lanes"]),
            "traffic category (BCI)": c["bci_traffic_category"] or "unknown",
            "EPC": {"true": "in EPC", "false": "outside EPC"}.get(c["in_epc"], "unknown"),
            "signal present": {"true": "signal", "false": "no signal"}.get(c["signal_present"], "unknown"),
            "painted safety zone": {"true": "yes", "false": "no"}.get(c["painted_safety_zone"], "unknown"),
            "traffic calming": {"true": "yes", "false": "no"}.get(c["traffic_calming"], "unknown"),
            "light": light_band(c["lighting"]),
            "at intersection": {"Midblock > 20ft": "midblock"}.get(c["intersection"], "intersection"),
            "heaviest vehicle weight": weight_band(heavy),
            "_basis": {k: c[k + "_basis"] for k in ("posted_speed_limit_mph", "street_class", "corner_type", "lanes",
                                                   "bci_traffic_category", "in_epc", "signal_present",
                                                   "painted_safety_zone", "traffic_calming")},
        })

    N = len(recs)
    K = sum(r["ksi"] for r in recs)
    P = sum(r["people"] for r in recs)
    p0 = K / N

    def tally(rs):
        n = len(rs)
        k = sum(r["ksi"] for r in rs)
        ppl = sum(r["people"] for r in rs)
        return {"injury_crashes": n, "ksi_crashes": k, "ksi_people": ppl,
                "ksi_rate": round(k / n, 4) if n else None,
                "share_of_injury_crashes": round(n / N, 4), "share_of_ksi_people": round(ppl / P, 4),
                "over_representation": round((ppl / P) / (n / N), 2) if n else None}

    # Level 1
    cells = collections.defaultdict(list)
    for r in recs:
        cells[(r["movement"], r["violation"], r["time"])].append(r)
    tested = {key: rs for key, rs in cells.items() if sum(r["people"] for r in rs) >= MIN_KSI_PEOPLE}
    m = len(tested)
    level1 = []
    for key, rs in tested.items():
        t = tally(rs)
        t.update({"movement": key[0], "violation": key[1], "time": key[2],
                  "p_value": binom_sf(t["ksi_crashes"], t["injury_crashes"], p0)})
        t["p_bonferroni"] = min(1.0, t["p_value"] * m)
        t["profile"] = t["p_bonferroni"] < ALPHA
        level1.append(t)
    level1.sort(key=lambda t: (not t["profile"], -t["ksi_people"]))
    profiles = [t for t in level1 if t["profile"]]

    # Level 1 within mode: the same grid with each cell compared to its own mode's KSI rate, since a pedestrian hit
    # by a car is far more likely to be badly hurt than a driver in a rear-end, and the all-crash grid mostly
    # rediscovers that. Bonferroni runs over every cell tested in the three modes together.
    by_mode = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in recs:
        by_mode[r["mode"]][(r["movement"], r["violation"], r["time"])].append(r)
    mode_tested = [(md, key, rs) for md, cs in by_mode.items() if md != "not stated" for key, rs in cs.items()
                   if sum(r["people"] for r in rs) >= MIN_KSI_PEOPLE]
    mode_rates = {md: (sum(r["ksi"] for rs in cs.values() for r in rs) / sum(len(rs) for rs in cs.values()))
                  for md, cs in by_mode.items()}
    mode_totals = {md: tally([r for rs in cs.values() for r in rs]) for md, cs in by_mode.items()}
    within_mode = []
    for md, key, rs in mode_tested:
        t = tally(rs)
        t.update({"mode": md, "movement": key[0], "violation": key[1], "time": key[2],
                  "mode_ksi_rate": round(mode_rates[md], 4),
                  "rate_vs_mode": round(t["ksi_rate"] / mode_rates[md], 2)})
        t["p_bonferroni"] = min(1.0, binom_sf(t["ksi_crashes"], t["injury_crashes"], mode_rates[md]) * len(mode_tested))
        t["profile"] = t["p_bonferroni"] < ALPHA
        within_mode.append(t)
    within_mode.sort(key=lambda t: (t["mode"], not t["profile"], -t["ksi_people"]))

    # Level 1 margins: each dimension alone, so a broad category that pops out shows even if its cells are small
    margins = {}
    for dim in ("movement", "violation", "time"):
        g = collections.defaultdict(list)
        for r in recs:
            g[r[dim]].append(r)
        md = len(g)
        out = []
        for val, rs in g.items():
            t = tally(rs)
            t["value"] = val
            t["p_bonferroni"] = min(1.0, binom_sf(t["ksi_crashes"], t["injury_crashes"], p0) * md)
            out.append(t)
        margins[dim] = sorted(out, key=lambda t: -t["ksi_people"])

    # Level 2
    SPLITS = ["other party movement", "pedestrian action", "collision type", "who was involved", "street class",
              "corner type", "posted limit", "EPC", "light", "heaviest vehicle weight"]
    mode_profiles = [t for t in within_mode if t["profile"]]
    tests = max(1, (len(profiles) + len(mode_profiles)) * len(SPLITS))
    level2 = []
    for prof in profiles + mode_profiles:
        rs = cells[(prof["movement"], prof["violation"], prof["time"])]
        if "mode" in prof:
            rs = by_mode[prof["mode"]][(prof["movement"], prof["violation"], prof["time"])]
        splits = []
        for field in SPLITS:
            g = collections.defaultdict(list)
            for r in rs:
                g[r[field]].append(r)
            cats = []
            for val, sub in sorted(g.items(), key=lambda kv: -sum(r["people"] for r in kv[1])):
                n, k = len(sub), sum(r["ksi"] for r in sub)
                cats.append({"value": val, "injury_crashes": n, "ksi_crashes": k,
                             "ksi_people": sum(r["people"] for r in sub), "ksi_rate": round(k / n, 4)})
            x2, p = chi2_homogeneity([(c["injury_crashes"], c["ksi_crashes"]) for c in cats])
            splits.append({"field": field, "chi2": round(x2, 2) if x2 else None, "p_value": p,
                           "flagged": p is not None and p * tests < ALPHA, "categories": cats})
        level2.append({"profile": {k: prof[k] for k in ("mode", "movement", "violation", "time") if k in prof},
                       "splits": splits})

    # Context profiles
    miles, corners = network(sorted(glob.glob(os.path.join(ROOT, "data", "socrata-cache", "crash-augment-street",
                                                        "3psu-pn9h-*.json")))[0])
    total_miles = sum(miles.values())
    total_corners = sum(corners.values())
    CONTEXT = {"street class": "street_class", "corner type": "corner_type", "posted limit": "posted_speed_limit_mph",
               "lanes": "lanes", "traffic category (BCI)": "bci_traffic_category", "EPC": "in_epc",
               "signal present": "signal_present", "painted safety zone": "painted_safety_zone",
               "traffic calming": "traffic_calming", "light": None, "at intersection": None}
    at_int_people = sum(r["people"] for r in recs if r["corner type"] != "midblock")
    context = []
    for field, basis_key in CONTEXT.items():
        g = collections.defaultdict(list)
        for r in recs:
            g[r[field]].append(r)
        vals = []
        for val, rs in sorted(g.items(), key=lambda kv: -sum(r["people"] for r in kv[1])):
            t = tally(rs)
            t["value"] = val
            if field == "street class" and val in miles:
                t["share_of_network_miles"] = round(miles[val] / total_miles, 4)
                t["network_miles"] = round(miles[val], 1)
            if field == "corner type" and val != "midblock":
                t["share_of_intersection_ksi_people"] = round(t["ksi_people"] / at_int_people, 4)
            if field == "corner type" and val in corners:
                t["share_of_intersections"] = round(corners[val] / total_corners, 4)
                t["intersections"] = corners[val]
            vals.append(t)
        basis = collections.Counter(r["_basis"][basis_key] for r in recs) if basis_key else {"crash report": N}
        context.append({"field": field, "basis": dict(basis), "values": vals})

    # Signals at intersections, LADOT's comparison: intersection crashes only, against the share of intersections
    # with a signal in today's inventory (ybh5-27n2, signal types as the street lane counts them).
    sig_path = sorted(glob.glob(os.path.join(ROOT, "data", "socrata-cache", "crash-augment-street", "ybh5-27n2-*.json")))
    signal_nodes = {str(r.get("cnn") or "").split(".")[0] for r in json.load(open(sig_path[0]))["rows"]
                    if r.get("type") in SIGNAL_TYPES} if sig_path else set()
    at_int = [r for r in recs if r["corner type"] != "midblock"]
    g = collections.defaultdict(list)
    for r in at_int:
        g[r["signal present"]].append(r)
    signals = {"intersections_with_signal": len(signal_nodes), "intersections": total_corners,
               "share_of_intersections": round(len(signal_nodes) / total_corners, 4) if total_corners else None,
               "values": [dict(tally(rs), value=v,
                               share_of_intersection_ksi_people=round(sum(r["people"] for r in rs) / at_int_people, 4))
                          for v, rs in sorted(g.items())]}

    # Pedestrian crashes by light and posted limit, one of the expected profiles in the plan
    ped_light_speed = []
    g = collections.defaultdict(list)
    for r in recs:
        if r["mode"] == "pedestrian involved":
            g[(r["light"], r["posted limit"])].append(r)
    for (light, lim), rs in sorted(g.items()):
        t = tally(rs)
        t.update({"light": light, "posted limit": lim})
        ped_light_speed.append(t)

    # Vehicle weight: pedestrians struck by a single motor vehicle
    MODEL_METHODS = {"exact_make_model_year", "model_10yr_avg"}
    weight = {"all_weighted": collections.defaultdict(lambda: [0, 0]),
              "model_matched": collections.defaultdict(lambda: [0, 0])}
    coverage = collections.Counter()
    strata = collections.defaultdict(lambda: {"heavy": [0, 0], "light": [0, 0]})
    for cid, peds in ped_victims.items():
        c = crashes.get(cid)
        if c is None or c["motor_vehicle_parties"] != "1":
            continue
        mv = [p for p in parties.get(cid, {}).values() if p["vehicle_match_method"] != "not_applicable"]
        if len(mv) != 1:
            continue
        p = mv[0]
        band = weight_band(p["estimated_vehicle_weight_lb"])
        coverage[p["vehicle_match_method"]] += len(peds)
        cls = c["street_class"] or "unknown"
        for v in peds:
            hurt = v["victim_degree_of_injury"] in KSI_PERSON
            weight["all_weighted"][band][0] += 1
            weight["all_weighted"][band][1] += hurt
            if p["vehicle_match_method"] in MODEL_METHODS:
                weight["model_matched"][band][0] += 1
                weight["model_matched"][band][1] += hurt
            if band != "no weight":
                side = "heavy" if band == "over 5,000 lb" else ("light" if band == "under 3,500 lb" else None)
                if side:
                    strata[(cls, light_band(c["lighting"]))][side][0] += 1
                    strata[(cls, light_band(c["lighting"]))][side][1] += hurt
    weight_out = {}
    for name, d in weight.items():
        rows = []
        for band in ("under 3,500 lb", "3,500 to 5,000 lb", "over 5,000 lb", "no weight"):
            n, k = d.get(band, [0, 0])
            rows.append({"band": band, "pedestrians_hurt": n, "pedestrians_ksi": k,
                         "ksi_rate": round(k / n, 4) if n else None})
        x2, pv = chi2_homogeneity([(r["pedestrians_hurt"], r["pedestrians_ksi"]) for r in rows
                                   if r["band"] != "no weight"])
        weight_out[name] = {"bands": rows, "chi2": round(x2, 2) if x2 else None, "p_value": pv}
    crude_h, crude_l = [0, 0], [0, 0]
    mh = []
    for s in strata.values():
        hn, hk = s["heavy"]
        ln, lk = s["light"]
        mh.append((hk, hn - hk, lk, ln - lk))
        crude_h = [crude_h[0] + hn, crude_h[1] + hk]
        crude_l = [crude_l[0] + ln, crude_l[1] + lk]

    def odds(n, k):
        return k / (n - k) if n > k else None
    crude_or = (odds(*crude_h) / odds(*crude_l)) if odds(*crude_l) else None
    est, lo, hi = mantel_haenszel(mh)
    weight_out["heavy_vs_light_odds_ratio"] = {
        "compares": "over 5,000 lb vs under 3,500 lb",
        "crude": round(crude_or, 2) if crude_or else None,
        "mantel_haenszel_by_street_class_and_light": round(est, 2) if est else None,
        "ci95": [round(lo, 2), round(hi, 2)] if est else None,
        "strata": len(mh)}
    weight_out["coverage_by_method"] = dict(coverage)

    # Data quality facts the doc reports
    ped_parties = [p for ps in parties.values() for p in ps.values()]
    drivers = [p for p in ped_parties if p["party_type"] == "Driver"]
    quality = {
        "at_fault_party_found_by": dict(how),
        "crashes_with_no_ksi_people_but_ksi_severity": sum(1 for r in recs if r["ksi"] and r["people"] == 0),
        "ksi_people_in_non_ksi_crashes": sum(r["people"] for r in recs if not r["ksi"]),
        "driver_parties": len(drivers),
        "driver_weight_method": dict(collections.Counter(p["vehicle_match_method"] for p in drivers)),
        "driver_model_named": sum(1 for p in drivers if p["vehicle_model_clean"]),
        "violation_not_stated_crashes": sum(1 for r in recs if r["violation"] == "not stated"),
        "movement_not_stated_or_other_crashes": sum(1 for r in recs if r["movement"] == OTHER_MOVE),
    }

    out = {
        "about": "First-cut LADOT-style crash profiles for SF, built by analysis/crash-profiles/crash-profiles.py "
                 "from out/crash-augment/tables (DataSF ubvf-ztfx, 8gtc-pjc6, nwes-mmgh).",
        "years": [y0, y1],
        "inputs_read_on": json.load(open(os.path.join(TABLES, "summary.json")))["tables"]["crashes"]["input"]["read_on"],
        "totals": {"injury_crashes": N, "ksi_crashes": K, "ksi_people": P, "citywide_ksi_rate": round(p0, 4)},
        "rules": {"min_ksi_people": MIN_KSI_PEOPLE, "alpha": ALPHA, "cells_possible": len(cells),
                  "cells_tested": m, "test": "one-sided exact binomial on KSI crashes vs citywide KSI crash rate, "
                                           "Bonferroni over cells tested"},
        "profiles": profiles,
        "level1_tested": level1,
        "level1_margins": margins,
        "mode_totals": mode_totals,
        "level1_within_mode": within_mode,
        "level1_within_mode_cells_tested": len(mode_tested),
        "level2": level2,
        "context": context,
        "network": {"miles_by_street_class": {k: round(v, 1) for k, v in sorted(miles.items())},
                    "intersections_by_corner_type": dict(sorted(corners.items()))},
        "pedestrian_light_by_posted_limit": ped_light_speed,
        "signals_at_intersections": signals,
        "vehicle_weight": weight_out,
        "quality": quality,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1, sort_keys=False, default=float)
        f.write("\n")
    print("%d-%d: %d injury crashes, %d KSI crashes, %d KSI people; %d cells tested, %d profiles -> %s"
          % (y0, y1, N, K, P, m, len(profiles), os.path.relpath(a.out, ROOT)))


if __name__ == "__main__":
    main()
