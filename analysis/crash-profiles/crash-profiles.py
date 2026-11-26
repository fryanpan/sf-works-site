#!/usr/bin/env python3
"""A first-cut LADOT-style crash profile analysis for San Francisco, read off the crash-augment tables.

    python3 analysis/crash-profiles/crash-profiles.py                  # YEARS (2018-2025), writes out/crash-augment/profiles/results.json
    python3 analysis/crash-profiles/crash-profiles.py --years 2019 2025

It reads out/crash-augment/tables/{crashes,parties,victims}.csv (built by pipeline/crash-augment/crash-augment.py)
and the street lane's held copies of the street centerlines (3psu-pn9h) and signals (ybh5-27n2), taken through
street_sources.held() so they are the copies the street columns were built from, and writes one JSON file of counts.
pipeline/transportation-update.py reruns it as the build step "crash-profiles" whenever those inputs change.
Standard library only.

WHAT IT COUNTS
  An injury crash is a row of ubvf-ztfx. A KSI crash has collision_severity Fatal or Injury (Severe). A KSI person is
  a victims row (nwes-mmgh) with victim_degree_of_injury Fatal Injury or Severe Injury. A crash's year is the year
  of collision_datetime, not accident_year, which runs a year behind on a few crashes (pipeline check accident_year).

LEVEL 1, THE COARSE GRID. Each crash falls in one cell of movement group x violation group x time band.
  movement   the at-fault party's move_pre_acc, grouped by MOVEMENT. The at-fault party is the crash's party_at_fault
             number; when that is blank, the party with at_fault Yes; when none, party 1. When the at-fault party is
             a pedestrian, the movement is the first Driver party's instead (never a bicyclist or a parked car),
             since a fix acts on the vehicle. The JSON counts how often that happens.
  violation  vz_pcf_group (the primary collision factor), grouped by VIOLATION.
  time       collision_time and day_of_week, grouped by TIME_BANDS.
  A cell is tested only if it holds at least MIN_INJURY_CRASHES injury crashes. The rule reads exposure, never the
  outcome, so a small cell cannot enter the test by being severe by chance. A tested cell is a profile when its KSI
  crash rate (KSI crashes / injury crashes in the cell) is above the citywide rate by a one-sided exact binomial
  test at ALPHA divided by the number of cells tested (Bonferroni). Rate above the citywide rate is the same statement as
  "its share of KSI crashes exceeds its share of injury crashes". Over-representation is reported as the cell's share
  of KSI people divided by its share of injury crashes.

LEVEL 2. Each profile is split by the finer fields in SPLITS. A split is flagged when the KSI rate differs across its
  categories by a chi-square test of homogeneity at ALPHA / (profiles x splits); the doc decides which flagged splits
  point at a different fix.

YEAR WINDOWS. Each profile's rate is given again for the years before 2020 and for 2020 on, alone, and each mode's crashes by
  year and severity, because reported minor-injury crashes fell in 2020 while KSI crashes did not, which raises
  every severity rate after 2020.

CONTEXT PROFILES. For each street-context field, each value's share of KSI people against its share of injury
  crashes, and for street class and corner type its share of the network (block length; intersections). Street
  shares are given over every active block and over surface streets alone (no freeway, ramp or class 0). Each field
  carries the mix of its _basis column, so a reader can see which are current_state_only. The signal share counts
  only signals at a node the corner count holds.

VEHICLE WEIGHT. Pedestrians hurt in crashes with exactly one moving motor vehicle (motor_vehicle_parties, which
  leaves out parked cars), by that vehicle's estimated_vehicle_weight_lb band. Reported for every weighted vehicle
  and for model-matched weights alone (exact_make_model_year, model_10yr_avg), since a body_type_avg weight only
  restates the body type. A Mantel-Haenszel odds ratio of over 5,000 lb against under 3,500 lb, stratified by street
  class and light, is given for both, per pedestrian and per crash (a crash is KSI when any pedestrian in it was);
  the per-crash one is the honest interval, since pedestrians in one crash are not independent. It adjusts for
  nothing else, and buses, heavy trucks and motorcycles have no weight, so it compares light vehicles only.

SIZE. Every group's count of people hurt, whatever its rate, because a group that is not more severe than usual can
  still hold the most people. A person hurt is a victims row with any injury (not No Injury); every tally carries
  people_injured beside ksi_people. size.cells is every movement x violation x time cell (no size floor, nothing
  tested), size.cells_within_mode the same within pedestrian, bicycle and vehicle-only crashes, and
  size.pairs_within_mode mode x movement x violation pooled over time (cells_within_mode lists only cells with
  SIZE_FLOOR_WITHIN_MODE people hurt or more, pooling the rest into one "rest" row so the list still sums to every person in a stated mode), and size.violation_within_mode mode x
  violation alone. Each list is sorted by people hurt, then KSI people, then the key, and each cell gives its people
  by victim_role. size.cells_to_half says how many of the biggest cells it takes to hold half of everyone hurt and
  half of the KSI people. size.chart is the doc's bar chart: the union of the CHART_TOP biggest mode x movement x
  violation groups by people hurt and by KSI people, then one "all other groups" row over every other crash (mode not
  stated included), so the rows add up to the totals.

OTHER BREAKDOWN. other_breakdown says what size.chart's last row holds: its groups by size (SIZE_BINS) and by mode,
  movement and violation, and how many of its people sit in a catch-all value (violation "other" or "not stated",
  movement OTHER_MOVE, mode "not stated") against named kinds of crash. For each catch-all bucket it lists the RAW_TOP
  biggest raw values (vz_pcf_group with DataSF's vz_pcf_description; vz_pcf_group and vz_pcf_code; move_pre_acc and
  the party type) and where the bucket's people land under the finer groups. regroupings compares groupings by the
  share of people hurt in a catch-all group, the bars it takes to reach 80% of people hurt, and the share a
  CHART_BARS-bar chart leaves in its remainder row or in catch-all bars (crash type Other and Not Stated count as
  catch-alls there).

SIZE BY FAMILY. size_families groups crashes by mode x violation family, VIOLATION_FINE: the VIOLATION groups with
  CVC 21703 (following too closely) named, signals and signs split into red light and stop sign or other sign, bike and
  scooter rules and phone use named, and 21209 (motor vehicle in a bike lane) and 22108 put with lane use. When
  vz_pcf_group is blank or Unknown, vz_pcf_code is read if it holds a section number. Each family carries its people
  by movement (MOVEMENT_FINE, which names Ran Off Road), so the movement that points at a fix stays on the bar.
  size_families.chart is the union of the FAMILY_TOP biggest families by people hurt and by KSI people, then one row
  over every other crash; pairs_within_mode is mode x movement x family for the drill-down. The violation is the
  crash's primary collision factor, which the police assign to the party at fault, so each family also carries its
  people by the at-fault party's party_type (by_at_fault_party_type: Driver, Pedestrian, Bicyclist, Parked Vehicle,
  Other), which says whose violation it was.

FAMILY STRESS. family_stress splits the FAMILY_STRESS_TOP biggest families by people hurt by the bike level of
  traffic stress of the crash (crash_stress, as in TRAFFIC STRESS: high is LTS 3 or 4, low 1 or 2) and by street
  class, with the high-stress share among crashes placed on one block as the check on the intersection lean.

GROUPING ALTERNATIVES. grouping_alternatives scores the groupings in GROUPINGS the way other_breakdown.regroupings
  does, each with its top CHART_BARS bars and the remainder: victim role x age band and victim role x violation family
  (counted per person, victims rows with any injury; an age outside 1 to 109 is not stated); traffic stress x street
  class x intersection or midblock; mode x time band x weekday or weekend (the commute and midday bands are weekday by
  definition, so the split adds only evening and late night); vehicle-only crashes by crash type beside pedestrian and
  bike crashes by violation family, alone and with the turn direction; mode x violation family x traffic stress; and
  the crash's posted speed limit, number of lanes, light, Equity Priority Community and heaviest vehicle weight band,
  each alone. fix-groups.py counts every fix's people avoided over the same groupings.

TRAFFIC STRESS. Each crash's blocks (street_block_cnns, the street lane's block rule) are looked up in SFMTA's 2023
  draft Bike Comfort Index layer as the repo holds it (data/extract/sfmta-bci/scores.json, BCI_SCORES): the bike level
  of traffic stress (lts_ft, lts_tf, 1 low to 4 high; the most stressful direction and block), the layer's combined
  bci field (as the layer gives it, which on about 2,000 blocks is the higher direction; a crash is under the Biking
  and Rolling Plan's all ages and abilities line, BCI_AAA, when any of its blocks is) and the traffic category (the
  heaviest). People hurt and KSI people by each, for all crashes and by mode, against each
  value's share of active surface street miles (3psu-pn9h blocks by CNN; freeways, ramps and class 0 left out).
  High stress is LTS 3 or 4. The traffic category read here is checked against the crash table's own
  bci_traffic_category column, which came from the same layer. The layer is today's, so this pools every year. Miles
  are the only denominator: there is no residents' or traffic-volume one, and most people are hurt at intersections,
  so high_stress_by_block_join gives the share among crashes coded to one block, and high_stress_by_street_class the
  share within each street class, since LTS 4 is nearly every arterial and major block.

Every figure is a correlation in police-reported injury crashes. Nothing here says a field causes severity.
"""

import argparse
import collections
import csv
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLES = os.path.join(ROOT, "out", "crash-augment", "tables")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "results.json")
sys.path.insert(0, os.path.join(ROOT, "pipeline", "crash-augment", "street"))
from street_fields import ROAD_CLASS, CLASS_RANK, SIGNAL_TYPES, TRAFFIC, TRAFFIC_RANK, street_key  # noqa: E402
from street_geo import line_coords  # noqa: E402
import street_sources  # noqa: E402

csv.field_size_limit(1 << 24)
# The collision years every figure counts, first and last. A yearly average is a count over the years in this range;
# fix-reach.py, fix-map.py, fix-groups.py and fix-explorer.py read the range from results.json, so it is set only here.
YEARS = (2018, 2025)
MIN_INJURY_CRASHES = 100
ALPHA = 0.05
KSI_CRASH = {"Fatal", "Injury (Severe)"}
KSI_PERSON = {"Fatal Injury", "Severe Injury"}
NOT_HURT = {"No Injury", ""}
BCI_SCORES = os.path.join(ROOT, "data", "extract", "sfmta-bci", "scores.json")
BCI_AAA = 80  # Biking and Rolling Plan: all ages and abilities network is "BCI > 80" (tools/street-safety/street-safety-map.py)
HIGH_STRESS = {"3", "4"}
CHART_TOP = 8  # size.chart: the top groups by people hurt and by KSI people
SIZE_FLOOR_WITHIN_MODE = 20  # size.cells_within_mode lists cells with this many people hurt; the rest is one row

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
    # Mostly CVC 22350, the basic speed law (too fast for conditions), which officers also code on rear-ends.
    ("unsafe speed", ("22350", "22351", "22352", "22356", "23103", "23109")),
    ("dooring", ("22517",)),
    ("unsafe starting or backing", ("22106",)),
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


# The finer violation groups behind size_families. Each name is the vz_pcf_description DataSF prints for its codes;
# the first match wins, so DUI comes before the bike rules (21200.5 is "Bicyclist riding under the influence").
VIOLATION_FINE = [
    ("unsafe speed", ("22350", "22351", "22352", "22356", "23103", "23109")),
    ("following too closely", ("21703",)),
    ("dooring", ("22517",)),
    ("unsafe starting or backing", ("22106",)),
    ("failure to yield to pedestrian", ("21950(a", "21954(b", "21952", "21951")),
    ("vehicle right of way", ("21800", "21801", "21802", "21803", "21804", "21806", "21451")),
    ("red light", ("21453(a", "21453(b", "21453(c")),
    ("stop sign or other sign", ("22450", "21461", "22101", "21457", "21452", "21454")),
    ("pedestrian violation", ("21954(a", "21453(d", "21955", "21950(b", "21456", "21956", "21949", "7.2.10")),
    ("DUI", ("23152", "23153", "21200.5")),
    # 22107 is "Unsafe turn or lane change", so the code alone can't tell a turn from a lane change; the movement can.
    ("unsafe turn or lane use", ("22107", "22108", "22100", "22102", "22103", "22105", "21658", "21460", "21650",
                                 "21651", "21657", "21750", "21751", "21752", "21755", "21760", "21209")),
    ("bike or scooter rules", ("21200", "21201", "21202", "21203", "21205", "21208", "21230", "21235", "21663",
                               "7.2.12", "7.2.13")),
    ("phone use", ("23123", "23124")),
]
MOVEMENT_FINE = dict(MOVEMENT, **{"Ran Off Road": "ran off road"})
CATCH_ALL = {"other", "not stated", OTHER_MOVE, "Other", "Not Stated"}  # values that name no kind of crash
FAMILY_TOP = 12  # size_families.chart: the top mode x violation families by people hurt and by KSI people
FAMILY_STRESS_TOP = 10  # family_stress: the biggest families by people hurt
RAW_TOP = 15  # other_breakdown: raw codes listed per catch-all bucket
CHART_BARS = 12  # other_breakdown.regroupings: the chart size the remainder is measured at
SIZE_BINS = ((500, None), (200, 499), (100, 199), (50, 99), (20, 49), (1, 19), (0, 0))


def violation_fine(group, code):
    """vz_pcf_group to a VIOLATION_FINE group. When the group is blank or Unknown, vz_pcf_code is read instead if it
    holds a section number (a trailing "cvc" or "tc" dropped); a code that names no section stays "not stated"."""
    g = group
    if g in UNKNOWN_VIOL:
        c = (code or "").strip().lower()
        for suffix in ("cvc", "tc"):
            c = c[:-len(suffix)] if c.endswith(suffix) else c
        if not (c and c[0].isdigit()):
            return "not stated"
        g = c
    g = g.lower()
    for name, prefixes in VIOLATION_FINE:
        if any(g.startswith(p.lower()) for p in prefixes):
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
    in_years = lambda r: y0 <= int(r["collision_datetime"][:4] or 0) <= y1  # noqa: E731
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


def first_driver(ps, exclude=None):
    """The lowest-numbered Driver party, never a pedestrian, bicyclist, parked car or "Other" party."""
    for k, p in sorted(ps.items(), key=lambda kv: int(kv[0] or 0)):
        if p is not exclude and p["party_type"] == "Driver":
            return p
    return None


def move_group(v):
    return MOVEMENT.get(v, OTHER_MOVE)


# ---- network denominators ------------------------------------------------------------------------------------

NOT_SURFACE = ("freeway", "ramp", "other")


def block_miles(r):
    """One 3psu-pn9h block's length in miles, from its line."""
    length = 0.0
    for line in line_coords(r.get("line")):
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            dx = (x2 - x1) * math.cos(math.radians((y1 + y2) / 2)) * 69.172
            dy = (y2 - y1) * 69.0
            length += math.hypot(dx, dy)
    return length


def network(rows):
    """(miles by street class, intersections by corner type, the corner nodes) from 3psu-pn9h's active blocks."""
    miles = collections.Counter()
    node_streets = collections.defaultdict(dict)
    for r in rows:
        if r.get("active") not in (True, "True", "true"):
            continue
        cls = ROAD_CLASS.get(r.get("classcode")) or "other"
        miles[cls] += block_miles(r)
        for n in (r.get("f_node_cnn"), r.get("t_node_cnn")):
            n = str(n or "").split(".")[0]
            if n:
                node_streets[n].setdefault(street_key(r.get("streetname")), []).append(cls)
    corners = collections.Counter()
    corner_nodes = set()
    for n, streets in node_streets.items():
        best = {s: min(c, key=CLASS_RANK.get) for s, c in streets.items()}
        surface = {s: c for s, c in best.items() if c not in ("freeway", "ramp")} or best
        cl = sorted(surface.values(), key=CLASS_RANK.get)
        if len(cl) > 1:  # a node on one street is a bend or a dead end, not a corner
            corners["%s_x_%s" % (cl[0], cl[1])] += 1
            corner_nodes.add(n)
    return miles, corners, corner_nodes


def bci_blocks():
    """{cnn: (lts, bci band, traffic)} from the held BCI layer, and the layer's fetch date. lts is the higher of the
    two directions as a string 1 to 4, the band says which side of BCI_AAA the combined score falls on."""
    with open(BCI_SCORES) as f:
        d = json.load(f)
    out = {}
    for r in d["records"]:
        c = str(r.get("cnn") or "").split(".")[0]
        if not c:
            continue
        lts = [x for x in (r.get("lts_ft"), r.get("lts_tf")) if x]
        traffic = [TRAFFIC[x] for x in (r.get("traffic_ft"), r.get("traffic_tf")) if x in TRAFFIC]
        out[c] = (str(max(lts)) if lts else None, bci_band(r.get("bci")),
                  max(traffic, key=TRAFFIC_RANK.get) if traffic else None)
    return out, d["fetched_on"]


def bci_band(v):
    if v is None:
        return None
    return "over %d (all ages and abilities)" % BCI_AAA if v > BCI_AAA else "%d or under" % BCI_AAA


def crash_stress(blocks, bci):
    """A crash's (lts, bci band, traffic) over its blocks: the most stressful LTS, the least comfortable score, the
    heaviest traffic; "unknown" where no block has a value."""
    vals = [bci[b] for b in blocks if b in bci]
    lts = [v[0] for v in vals if v[0]]
    bands = [v[1] for v in vals if v[1]]
    traffic = [v[2] for v in vals if v[2]]
    return (max(lts) if lts else "unknown",
            ("%d or under" % BCI_AAA if "%d or under" % BCI_AAA in bands else bands[0]) if bands else "unknown",
            max(traffic, key=TRAFFIC_RANK.get) if traffic else "unknown")


# ---- analysis ------------------------------------------------------------------------------------------------

def crash_records(crashes, parties, victims, bci):
    """One record per crash with every field the analysis groups by: (records, how the at-fault party was found,
    pedestrian victims by crash). fix-groups.py reads crashes through this too, so its groupings are these."""
    ksi_people = collections.Counter()
    hurt_people = collections.Counter()
    hurt_roles = collections.defaultdict(collections.Counter)
    ksi_roles = collections.defaultdict(collections.Counter)
    ped_victims = collections.defaultdict(list)
    for v in victims:
        role = v["victim_role"] or "not stated"
        if v["victim_degree_of_injury"] in KSI_PERSON:
            ksi_people[v["case_id_pkey"]] += 1
            ksi_roles[v["case_id_pkey"]][role] += 1
        if v["victim_degree_of_injury"] not in NOT_HURT:
            hurt_people[v["case_id_pkey"]] += 1
            hurt_roles[v["case_id_pkey"]][role] += 1
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
            mover = first_driver(ps)
            how["pedestrian_at_fault_used_vehicle_movement"] += 1
        other = first_driver(ps, exclude=mover) if mover is not None else None
        heavy = c["heaviest_vehicle_weight_lb"]
        lts, bci_score, traffic = crash_stress([b for b in c["street_block_cnns"].split(";") if b], bci)
        recs.append({
            "case": cid,
            "at-fault party type": (af["party_type"] or "not stated") if af is not None else "no party",
            "weekend": c["day_of_week"] in WEEKEND,
            "year": int(c["collision_datetime"][:4]),
            "ksi": c["collision_severity"] in KSI_CRASH,
            "people": ksi_people[cid],
            "injured": hurt_people[cid],
            "injured_roles": hurt_roles[cid],
            "ksi_roles": ksi_roles[cid],
            "block join": c["street_block_join"] or "none",
            "bike traffic stress (LTS)": lts,
            "bike comfort (BCI)": bci_score,
            "traffic category (BCI layer)": traffic,
            "movement": move_group(mover["move_pre_acc"]) if mover else OTHER_MOVE,
            "movement substituted": af is not None and af["party_type"] == "Pedestrian",
            "movement (fine)": MOVEMENT_FINE.get(mover["move_pre_acc"], OTHER_MOVE) if mover else OTHER_MOVE,
            "_move_raw": ((mover["move_pre_acc"] or "(blank)"), mover["party_type"]) if mover else ("(no party)", ""),
            "violation": violation_group(c["vz_pcf_group"]),
            "violation (fine)": violation_fine(c["vz_pcf_group"], c["vz_pcf_code"]),
            "_pcf_raw": (c["vz_pcf_group"], c["vz_pcf_code"], c["vz_pcf_description"]),
            "time": time_band(c["collision_time"], c["day_of_week"]),
            "other party movement": move_group(other["move_pre_acc"]) if other else "no other driver",
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

    return recs, how, ped_victims


def stress_band(r):
    lts = r["bike traffic stress (LTS)"]
    return "high (LTS 3-4)" if lts in HIGH_STRESS else ("low (LTS 1-2)" if lts in ("1", "2") else "unknown")


STRESS_BANDS = ("high (LTS 3-4)", "low (LTS 1-2)", "unknown")


def age_band(v):
    a = int(v) if v.lstrip("-").isdigit() else 0
    return "age not stated" if not 0 < a < 110 else ("child under 18" if a < 18 else
                                                     ("adult 18 to 64" if a < 65 else "65 and over"))


ROLE = {"Pedestrian": "pedestrian", "Bicyclist": "bicyclist", "Driver": "driver", "Passenger": "passenger",
        "Other": "scooter or other"}


def role_of(v):
    return ROLE.get(v["victim_role"], "role not stated")


def turn(r):
    m = r["movement (fine)"]
    return {"going straight": "going straight", "left or U-turn": "left or U-turn",
            "right turn": "right turn"}.get(m, "other movement" if m != OTHER_MOVE else OTHER_MOVE)


# Values that name no kind of crash or person, for the catch-all scores.
STATED = ("not stated", "unknown", "other", "Other", "Not Stated", OTHER_MOVE, "age not stated", "time not stated",
          "role not stated", "0 (layer gap)")

# The ways to group everyone hurt, beside size_families' mode x violation family: (id, name, unit, key). A crash
# grouping's key reads a crash record; a person grouping's key reads a victims row and its crash record. fix-groups.py
# counts every fix's people avoided over each of these, so a new grouping here reaches the fix explorer.
GROUPINGS = [
    ("who", "who was hurt: victim role x age band", "person", lambda v, r: (role_of(v), age_band(v["victim_age"]))),
    ("place", "place: traffic stress x street class x intersection or midblock", "crash",
     lambda r: (stress_band(r), r["street class"], r["at intersection"])),
    ("time", "time: mode x time band x weekday or weekend", "crash",
     lambda r: (r["mode"], r["time"], "weekend" if r["weekend"] else "weekday")),
    ("hybrid", "hybrid: vehicles only by crash type, pedestrian and bike by violation family", "crash",
     lambda r: (r["mode"], r["collision type"] if r["mode"] == "vehicles only" else r["violation (fine)"])),
    ("who_what", "who and what: victim role x violation family", "person", lambda v, r: (role_of(v), r["violation (fine)"])),
    ("hybrid_turn", "hybrid with movement: vehicles by crash type, pedestrian and bike by violation family x turn", "crash",
     lambda r: (r["mode"],) + ((r["collision type"],) if r["mode"] == "vehicles only" else (r["violation (fine)"], turn(r)))),
    ("what_where", "what and where: mode x violation family x traffic stress", "crash",
     lambda r: (r["mode"], r["violation (fine)"], stress_band(r))),
    ("speed_limit", "speed limit: posted speed limit of the crash's street", "crash", lambda r: (r["posted limit"],)),
    ("lanes", "lanes: number of lanes on the crash's street", "crash", lambda r: (r["lanes"],)),
    ("light", "light: daylight, dusk or dawn, or dark", "crash", lambda r: (r["light"],)),
    ("epc", "equity: in an Equity Priority Community", "crash", lambda r: (r["EPC"],)),
    ("weight", "vehicle weight: the heaviest vehicle's weight band", "crash", lambda r: (r["heaviest vehicle weight"],)),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", nargs=2, type=int, default=list(YEARS))
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    y0, y1 = a.years
    crashes, parties, victims = load(y0, y1)

    bci, bci_read_on = bci_blocks()
    recs, how, ped_victims = crash_records(crashes, parties, victims, bci)

    N = len(recs)
    K = sum(r["ksi"] for r in recs)
    P = sum(r["people"] for r in recs)
    H = sum(r["injured"] for r in recs)
    p0 = K / N

    def tally(rs):
        n = len(rs)
        k = sum(r["ksi"] for r in rs)
        ppl = sum(r["people"] for r in rs)
        hurt = sum(r["injured"] for r in rs)
        return {"injury_crashes": n, "ksi_crashes": k, "ksi_people": ppl, "people_injured": hurt,
                "ksi_rate": round(k / n, 4) if n else None,
                "share_of_injury_crashes": round(n / N, 4), "share_of_ksi_people": round(ppl / P, 4),
                "share_of_people_injured": round(hurt / H, 4),
                "over_representation": round((ppl / P) / (n / N), 2) if n else None}

    def roles(rs):
        hurt, ksi = collections.Counter(), collections.Counter()
        for r in rs:
            hurt.update(r["injured_roles"])
            ksi.update(r["ksi_roles"])
        return {"people_injured": dict(sorted(hurt.items())), "ksi_people": dict(sorted(ksi.items()))}

    # Level 1
    cells = collections.defaultdict(list)
    for r in recs:
        cells[(r["movement"], r["violation"], r["time"])].append(r)
    tested = {key: rs for key, rs in cells.items() if len(rs) >= MIN_INJURY_CRASHES}
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
                   if len(rs) >= MIN_INJURY_CRASHES]
    mode_cells_possible = sum(len(cs) for md, cs in by_mode.items() if md != "not stated")
    mode_rates = {md: (sum(r["ksi"] for rs in cs.values() for r in rs) / sum(len(rs) for rs in cs.values()))
                  for md, cs in by_mode.items()}
    mode_totals = {md: tally([r for rs in cs.values() for r in rs]) for md, cs in by_mode.items()}
    within_mode = []
    for md, key, rs in mode_tested:
        t = tally(rs)
        t.update({"mode": md, "movement": key[0], "violation": key[1], "time": key[2],
                  "mode_ksi_rate": round(mode_rates[md], 4),
                  "rate_vs_mode": round(t["ksi_rate"] / mode_rates[md], 2)})
        t["p_value"] = binom_sf(t["ksi_crashes"], t["injury_crashes"], mode_rates[md])
        t["p_bonferroni"] = min(1.0, t["p_value"] * len(mode_tested))
        t["profile"] = t["p_bonferroni"] < ALPHA
        t["movement_substituted_crashes"] = sum(r["movement substituted"] for r in rs)
        within_mode.append(t)
    within_mode.sort(key=lambda t: (t["mode"], not t["profile"], -t["ksi_people"]))

    # Year windows: each profile again before 2020 and from 2020 on, alone, against its mode's rate in that window,
    # with the uncorrected p and the p corrected over the same number of cells as the pooled test.
    WINDOWS = [(y0, 2019), (2020, y1)] if y0 <= 2019 < y1 else []

    def by_window(prof, base_of):
        out = []
        for w0, w1 in WINDOWS:
            rs = [r for r in recs if w0 <= r["year"] <= w1 and (r["movement"], r["violation"], r["time"])
                  == (prof["movement"], prof["violation"], prof["time"]) and ("mode" not in prof or r["mode"] == prof["mode"])]
            base = [r for r in recs if w0 <= r["year"] <= w1 and base_of(r)]
            n, k = len(rs), sum(r["ksi"] for r in rs)
            b = sum(r["ksi"] for r in base) / len(base) if base else None
            pv = binom_sf(k, n, b) if n and b else None
            m_ = len(mode_tested) if "mode" in prof else m
            out.append({"years": [w0, w1], "injury_crashes": n, "ksi_crashes": k, "ksi_people": sum(r["people"] for r in rs),
                        "ksi_rate": round(k / n, 4) if n else None, "base_rate": round(b, 4) if b else None,
                        "rate_vs_base": round((k / n) / b, 2) if n and b else None, "p_value": pv,
                        "p_bonferroni": min(1.0, pv * m_) if pv is not None else None})
        return out
    for t in profiles:
        t["by_years"] = by_window(t, lambda r: True)
    for t in within_mode:
        if t["profile"]:
            t["by_years"] = by_window(t, lambda r, md=t["mode"]: r["mode"] == md)

    # Each mode's crashes by year and severity, to date any step change in what gets reported.
    mode_by_year = {}
    for md in sorted(by_mode):
        rows = []
        for yr in range(y0, y1 + 1):
            rs = [r for r in recs if r["mode"] == md and r["year"] == yr]
            sev = collections.Counter(crashes[r["case"]]["collision_severity"] for r in rs)
            rows.append(dict(tally(rs), year=yr, by_severity=dict(sorted(sev.items()))))
        mode_by_year[md] = rows

    # Every movement x violation pair, pooled over time, so a count story such as left turns that fail to yield can
    # be read without the time split.
    pairs = collections.defaultdict(list)
    for r in recs:
        pairs[(r["movement"], r["violation"])].append(r)
    movement_by_violation = [dict(tally(rs), movement=k[0], violation=k[1])
                             for k, rs in sorted(pairs.items(), key=lambda kv: (-len(kv[1]), kv[0]))]

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
    streets_src = street_sources.held("streets")
    miles, corners, corner_nodes = network(streets_src.rows)
    total_miles = sum(miles.values())
    surface_miles = sum(v for k, v in miles.items() if k not in NOT_SURFACE)
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
                if val not in NOT_SURFACE:
                    t["share_of_surface_street_miles"] = round(miles[val] / surface_miles, 4)
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
    # Only signals at a node the corner count holds, so the share's numerator is a subset of its denominator.
    signals_src = street_sources.held("signals")
    all_signal_nodes = {str(r.get("cnn") or "").split(".")[0] for r in signals_src.rows if r.get("type") in SIGNAL_TYPES}
    signal_nodes = all_signal_nodes & corner_nodes
    at_int = [r for r in recs if r["corner type"] != "midblock"]
    g = collections.defaultdict(list)
    for r in at_int:
        g[r["signal present"]].append(r)
    signals = {"intersections_with_signal": len(signal_nodes), "signal_nodes_not_a_corner": len(all_signal_nodes - corner_nodes),
               "intersections": total_corners,
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

    # Pedestrian crashes by time band and light, so time of night and darkness can be told apart
    ped_time_light = []
    g = collections.defaultdict(list)
    for r in recs:
        if r["mode"] == "pedestrian involved":
            g[(r["time"], r["light"])].append(r)
    for (band, light), rs in sorted(g.items()):
        t = tally(rs)
        t.update({"time": band, "light": light})
        ped_time_light.append(t)

    # Vehicle weight: pedestrians struck by a single moving motor vehicle. motor_vehicle_parties leaves out parked cars,
    # and so does this filter, so a parked car's weight is never credited to a pedestrian's injury.
    MODEL_METHODS = {"exact_make_model_year", "model_10yr_avg"}
    BANDS = ("under 3,500 lb", "3,500 to 5,000 lb", "over 5,000 lb", "no weight")
    weight = {"all_weighted": collections.defaultdict(lambda: [0, 0]),
              "model_matched": collections.defaultdict(lambda: [0, 0])}
    coverage = collections.Counter()
    unweighted_body = collections.defaultdict(lambda: [0, 0])
    # strata[set][unit][(street class, light)][side] = [n, ksi]; side heavy (over 5,000 lb) or light (under 3,500)
    strata = {st: {u: collections.defaultdict(lambda: {"heavy": [0, 0], "light": [0, 0]}) for u in ("pedestrian", "crash")}
              for st in ("all_weighted", "model_matched")}
    for cid, peds in sorted(ped_victims.items()):
        c = crashes.get(cid)
        if c is None or c["motor_vehicle_parties"] != "1":
            continue
        mv = [p for p in parties.get(cid, {}).values()
              if p["vehicle_match_method"] != "not_applicable" and p["party_type"] != "Parked Vehicle"]
        if len(mv) != 1:
            continue
        p = mv[0]
        band = weight_band(p["estimated_vehicle_weight_lb"])
        coverage[p["vehicle_match_method"]] += len(peds)
        stratum = (c["street_class"] or "unknown", light_band(c["lighting"]))
        side = "heavy" if band == "over 5,000 lb" else ("light" if band == "under 3,500 lb" else None)
        hurt = [v["victim_degree_of_injury"] in KSI_PERSON for v in peds]
        sets = ["all_weighted"] + (["model_matched"] if p["vehicle_match_method"] in MODEL_METHODS else [])
        for st in sets:
            weight[st][band][0] += len(hurt)
            weight[st][band][1] += sum(hurt)
            if side:
                cell = strata[st]["pedestrian"][stratum][side]
                cell[0] += len(hurt)
                cell[1] += sum(hurt)
                cell = strata[st]["crash"][stratum][side]
                cell[0] += 1
                cell[1] += any(hurt)
        if band == "no weight":
            body = p["vehicle_body_type_clean"] or "not stated"
            unweighted_body[body][0] += len(hurt)
            unweighted_body[body][1] += sum(hurt)

    def odds(n, k):
        return k / (n - k) if n > k else None
    weight_out = {}
    for name, d in weight.items():
        rows = []
        for band in BANDS:
            n, k = d.get(band, [0, 0])
            rows.append({"band": band, "pedestrians_hurt": n, "pedestrians_ksi": k,
                         "ksi_rate": round(k / n, 4) if n else None})
        ors = {}
        for unit, by_stratum in strata[name].items():
            mh = [(s_["heavy"][1], s_["heavy"][0] - s_["heavy"][1], s_["light"][1], s_["light"][0] - s_["light"][1])
                  for _, s_ in sorted(by_stratum.items())]
            hn, hk = sum(s_["heavy"][0] for s_ in by_stratum.values()), sum(s_["heavy"][1] for s_ in by_stratum.values())
            ln, lk = sum(s_["light"][0] for s_ in by_stratum.values()), sum(s_["light"][1] for s_ in by_stratum.values())
            crude = odds(hn, hk) / odds(ln, lk) if odds(hn, hk) and odds(ln, lk) else None
            est, lo, hi = mantel_haenszel(mh)
            ors[unit] = {"heavy": [hn, hk], "light": [ln, lk], "crude": round(crude, 2) if crude else None,
                         "mantel_haenszel": round(est, 2) if est else None,
                         "ci95": [round(lo, 2), round(hi, 2)] if est else None, "strata": len(mh)}
        weight_out[name] = {"bands": rows, "heavy_vs_light_odds_ratio": ors}
    weight_out["compares"] = ("over 5,000 lb vs under 3,500 lb, Mantel-Haenszel stratified by street class and light; "
                              "per pedestrian, and per crash with a crash KSI when any pedestrian in it was")
    weight_out["coverage_by_method"] = dict(sorted(coverage.items()))
    weight_out["no_weight_by_body_type"] = [
        {"body_type": b, "pedestrians_hurt": n, "pedestrians_ksi": k}
        for b, (n, k) in sorted(unweighted_body.items(), key=lambda kv: (-kv[1][0], kv[0]))]

    # Pedestrian profiles: is it just older or drinking pedestrians? Victim age, and the KSI rate split by whether a
    # pedestrian party in the crash had been drinking.
    def ped_profile_facts(rs):
        ages = sorted(int(v["victim_age"]) for r in rs for v in ped_victims.get(r["case"], [])
                      if (v["victim_age"] or "").isdigit() and 0 < int(v["victim_age"]) < 110)
        drank = collections.defaultdict(lambda: [0, 0])
        for r in rs:
            sob = [p["party_sobriety"] for p in parties.get(r["case"], {}).values() if p["party_type"] == "Pedestrian"]
            key = "pedestrian had been drinking" if any(x.startswith("Had Been Drinking") for x in sob) else "no or not stated"
            drank[key][0] += 1
            drank[key][1] += r["ksi"]
        return {"pedestrian_victims_with_age": len(ages),
                "median_age": ages[len(ages) // 2] if ages else None,
                "share_65_plus": round(sum(a >= 65 for a in ages) / len(ages), 4) if ages else None,
                "by_drinking": {k: {"injury_crashes": n, "ksi_crashes": k_, "ksi_rate": round(k_ / n, 4)}
                                for k, (n, k_) in sorted(drank.items())}}
    ped_recs = [r for r in recs if r["mode"] == "pedestrian involved"]
    pedestrian_facts = {"all pedestrian crashes": ped_profile_facts(ped_recs)}
    for t in within_mode:
        if t["profile"] and t["mode"] == "pedestrian involved":
            rs = by_mode[t["mode"]][(t["movement"], t["violation"], t["time"])]
            pedestrian_facts["%s / %s / %s" % (t["movement"], t["violation"], t["time"])] = ped_profile_facts(rs)

    # Size: every group's people hurt and KSI people, whatever its rate. No size floor and no test.
    SIZE_KEYS = ("people_injured", "share_of_people_injured", "ksi_people", "share_of_ksi_people", "injury_crashes",
                 "ksi_crashes")

    def size_list(groups, names, with_roles=True, floor=0):
        """Groups biggest first. A group under `floor` people hurt is pooled into one "rest" row at the end, so the
        list still adds up to every person while the file stays small."""
        out, rest = [], []
        for key, rs in groups.items():
            t = dict(zip(names, key))
            tl = tally(rs)
            t.update({k: tl[k] for k in SIZE_KEYS})
            if with_roles:
                t["by_victim_role"] = roles(rs)
            (out if t["people_injured"] >= floor else rest).append((t, rs))
        out.sort(key=lambda tr: (-tr[0]["people_injured"], -tr[0]["ksi_people"], tuple(tr[0][n] for n in names)))
        out = [t for t, _ in out]
        if rest:
            tl = tally([r for _, rs in rest for r in rs])
            out.append(dict({n: "rest" for n in names}, groups=len(rest), **{k: tl[k] for k in SIZE_KEYS}))
        return out

    def to_half(lst, field, total):
        run, i = 0, 0
        for i, t in enumerate(sorted(lst, key=lambda t: -t[field]), 1):
            run += t[field]
            if run * 2 >= total:
                break
        return {"cells": i, "of_cells": len(lst)}

    g_mode, g_pair, g_viol = (collections.defaultdict(list) for _ in range(3))
    for r in recs:
        if r["mode"] != "not stated":
            g_mode[(r["mode"], r["movement"], r["violation"], r["time"])].append(r)
            g_pair[(r["mode"], r["movement"], r["violation"])].append(r)
            g_viol[(r["mode"], r["violation"])].append(r)
    size_cells = size_list(cells, ("movement", "violation", "time"))
    pairs_list = size_list(g_pair, ("mode", "movement", "violation"))
    shown = {(t["mode"], t["movement"], t["violation"]) for t in pairs_list[:CHART_TOP]} | {
        (t["mode"], t["movement"], t["violation"])
        for t in sorted(pairs_list, key=lambda t: (-t["ksi_people"], t["mode"], t["movement"], t["violation"]))[:CHART_TOP]}
    rest_recs = [r for r in recs if (r["mode"], r["movement"], r["violation"]) not in shown]
    rest_t = tally(rest_recs)
    chart = [{k: t[k] for k in ("mode", "movement", "violation") + SIZE_KEYS} for t in pairs_list
             if (t["mode"], t["movement"], t["violation"]) in shown]
    chart.append(dict({"mode": "all other groups", "movement": "", "violation": "", "groups": len(pairs_list) - len(shown)},
                      **{k: rest_t[k] for k in SIZE_KEYS}))
    size = {
        "about": "people hurt (any injury) and KSI people by group, sorted by people hurt; no size floor, no test",
        "cells": size_cells,
        "cells_within_mode": size_list(g_mode, ("mode", "movement", "violation", "time"), with_roles=False,
                                       floor=SIZE_FLOOR_WITHIN_MODE),
        "pairs_within_mode": pairs_list,
        "chart": chart,
        "violation_within_mode": size_list(g_viol, ("mode", "violation")),
        "cells_to_half": {"people_injured": to_half(size_cells, "people_injured", H),
                          "ksi_people": to_half(size_cells, "ksi_people", P)},
        "by_mode": {md: dict(tally(rs), by_victim_role=roles(rs))
                    for md, rs in sorted(((md, [r for r in recs if r["mode"] == md]) for md in by_mode))},
    }

    # Traffic stress: people hurt by the bike level of traffic stress, the BCI all-ages line and the traffic category
    # of the crash's block, against each value's share of active surface street miles.
    stress_miles = {f: collections.Counter() for f in ("bike traffic stress (LTS)", "bike comfort (BCI)",
                                                       "traffic category (BCI layer)")}
    for r in streets_src.rows:
        if r.get("active") not in (True, "True", "true") or (ROAD_CLASS.get(r.get("classcode")) or "other") in NOT_SURFACE:
            continue
        v = bci.get(str(r.get("cnn") or "").split(".")[0], (None, None, None))
        length = block_miles(r)
        for f, val in zip(stress_miles, v):
            stress_miles[f][val or "unknown"] += length
    stress = {"source": BCI_SCORES.replace(ROOT + os.sep, ""), "fetched_on": bci_read_on, "bci_aaa": BCI_AAA,
              "high_stress": "LTS 3 or 4", "fields": []}
    for f, mi in stress_miles.items():
        total_mi = sum(mi.values())
        vals = []
        for val in sorted({r[f] for r in recs} | set(mi)):
            rs = [r for r in recs if r[f] == val]
            t = dict(tally(rs), value=val, surface_street_miles=round(mi.get(val, 0.0), 1),
                     share_of_surface_street_miles=round(mi.get(val, 0.0) / total_mi, 4))
            t["by_victim_role"] = roles(rs)
            t["by_mode"] = {md: {"people_injured": sum(r["injured"] for r in rs if r["mode"] == md),
                                 "ksi_people": sum(r["people"] for r in rs if r["mode"] == md)}
                            for md in sorted(by_mode)}
            vals.append(t)
        stress["fields"].append({"field": f, "values": vals})
    hi = [r for r in recs if r["bike traffic stress (LTS)"] in HIGH_STRESS]
    hi_mi = sum(v for k, v in stress_miles["bike traffic stress (LTS)"].items() if k in HIGH_STRESS)
    stress["high_stress_total"] = dict(tally(hi), surface_street_miles=round(hi_mi, 1),
                                       share_of_surface_street_miles=round(
                                           hi_mi / sum(stress_miles["bike traffic stress (LTS)"].values()), 4),
                                       by_victim_role=roles(hi))
    # A crash at an intersection takes its most stressful block, which leans toward high stress; crashes on their
    # own block (street_block_join segment) carry no such lean, so their share is the check on it.
    stress["high_stress_by_block_join"] = {
        j: {"people_injured": sum(r["injured"] for r in recs if r["block join"] == j),
            "people_injured_high_stress": sum(r["injured"] for r in hi if r["block join"] == j),
            "people_injured_stress_known": sum(r["injured"] for r in recs if r["block join"] == j
                                               and r["bike traffic stress (LTS)"] != "unknown")}
        for j in sorted({r["block join"] for r in recs})}
    hi_by_class = collections.defaultdict(lambda: [0.0, 0.0])  # street class -> [high-stress miles, all miles]
    for r in streets_src.rows:
        cls = ROAD_CLASS.get(r.get("classcode")) or "other"
        if r.get("active") not in (True, "True", "true") or cls in NOT_SURFACE:
            continue
        length = block_miles(r)
        hi_by_class[cls][1] += length
        if (bci.get(str(r.get("cnn") or "").split(".")[0]) or (None,))[0] in HIGH_STRESS:
            hi_by_class[cls][0] += length
    stress["high_stress_by_street_class"] = {
        cls: {"surface_street_miles": round(m_all, 1), "high_stress_miles": round(m_hi, 1),
              "people_injured": sum(r["injured"] for r in recs if r["street class"] == cls),
              "people_injured_high_stress": sum(r["injured"] for r in hi if r["street class"] == cls)}
        for cls, (m_hi, m_all) in sorted(hi_by_class.items())}
    agree = collections.Counter((r["traffic category (BCI layer)"], r["traffic category (BCI)"]) for r in recs)
    stress["check_traffic_category_matches_crash_column"] = {
        "same": sum(n for (a, b), n in agree.items() if a == b),
        "differ": sorted([[a, b, n] for (a, b), n in agree.items() if a != b])}

    # Other breakdown: what size.chart's "all other groups" row and the catch-all values hold, and how much of it each
    # regrouping leaves in a catch-all or a remainder.
    def grouped(rs, key):
        g = collections.defaultdict(list)
        for r in rs:
            g[key(r)].append(r)
        return g

    def catch_kind(r):
        kinds = [name for name, hit in (("violation other", r["violation"] == "other"),
                                        ("violation not stated", r["violation"] == "not stated"),
                                        ("movement not stated or other", r["movement"] == OTHER_MOVE),
                                        ("mode not stated", r["mode"] == "not stated")) if hit]
        return (" + ".join(kinds) or "named kinds only",)

    def most_common_desc(rs):
        return collections.Counter(r["_pcf_raw"][2] for r in rs).most_common(1)[0][0] if rs else ""

    tail_groups = [t for t in pairs_list if (t["mode"], t["movement"], t["violation"]) not in shown]
    bins = []
    for lo, hi_ in SIZE_BINS:
        s = [t for t in tail_groups if t["people_injured"] >= lo and (hi_ is None or t["people_injured"] <= hi_)]
        bins.append({"people_injured_from": lo, "people_injured_to": hi_, "groups": len(s),
                     "people_injured": sum(t["people_injured"] for t in s), "ksi_people": sum(t["ksi_people"] for t in s)})
    buckets = {"violation other": lambda r: r["violation"] == "other",
               "violation not stated": lambda r: r["violation"] == "not stated",
               "movement not stated or other": lambda r: r["movement"] == OTHER_MOVE}
    raw_keys = {"violation other": (lambda r: (r["_pcf_raw"][0],), ("vz_pcf_group",)),
                "violation not stated": (lambda r: r["_pcf_raw"][:2], ("vz_pcf_group", "vz_pcf_code")),
                "movement not stated or other": (lambda r: r["_move_raw"], ("move_pre_acc", "party_type"))}
    raw = {}
    for name, hit in buckets.items():
        rs = [r for r in recs if hit(r)]
        key, names = raw_keys[name]
        g = grouped(rs, key)
        top = size_list(g, names, with_roles=False)[:RAW_TOP]
        if name != "movement not stated or other":
            for t in top:
                t["vz_pcf_description"] = most_common_desc(g[tuple(t[n] for n in names)])
        fine = "movement (fine)" if name.startswith("movement") else "violation (fine)"
        raw[name] = dict({k: tally(rs)[k] for k in SIZE_KEYS}, distinct_values=len(g), top=top,
                         under_finer_groups=size_list(grouped(rs, lambda r, f=fine: (r[f],)), (fine,), with_roles=False))

    def regroup(fields):
        g = collections.Counter()
        for r in recs:
            g[tuple(r[f] for f in fields)] += r["injured"]
        ranked = sorted(g.items(), key=lambda kv: (-kv[1], kv[0]))
        run, to80 = 0, None
        for i, (_, h) in enumerate(ranked, 1):
            run += h
            if run * 5 >= H * 4:
                to80 = i
                break
        is_catch = lambda k: any(v in CATCH_ALL for v in k)  # noqa: E731
        top = ranked[:CHART_BARS]
        remainder = H - sum(h for _, h in top)
        top_catch = sum(h for k, h in top if is_catch(k))
        return {"fields": list(fields), "groups": len(g),
                "share_of_people_injured_in_catch_all_groups": round(sum(h for k, h in ranked if is_catch(k)) / H, 4),
                "bars_to_80pct_of_people_injured": to80,
                "share_in_remainder_at_chart_bars": round(remainder / H, 4),
                "share_in_catch_all_bars_at_chart_bars": round(top_catch / H, 4),
                "share_left_in_catch_all_or_remainder": round((remainder + top_catch) / H, 4)}
    REGROUPINGS = [
        ("now: mode x movement x violation", ("mode", "movement", "violation")),
        ("finer codes: mode x movement x violation", ("mode", "movement (fine)", "violation (fine)")),
        ("crash type in place of movement: mode x crash type x violation", ("mode", "collision type", "violation (fine)")),
        ("crash type beside movement: mode x crash type x movement", ("mode", "collision type", "movement (fine)")),
        ("family, current violation groups: mode x violation", ("mode", "violation")),
        ("family: mode x violation (finer codes), chosen for size_families", ("mode", "violation (fine)")),
        ("family: mode x crash type", ("mode", "collision type")),
    ]
    other_breakdown = {
        "about": "what size.chart's last row and the catch-all values hold. Catch-all values: violation other and not "
                 "stated, movement not stated or other, mode not stated, and crash type Other and Not Stated",
        "chart_remainder": dict({k: rest_t[k] for k in SIZE_KEYS}, groups=len(tail_groups),
                                mode_not_stated_people_injured=sum(r["injured"] for r in rest_recs if r["mode"] == "not stated"),
                                group_sizes=bins,
                                by_catch_all=size_list(grouped(rest_recs, catch_kind), ("kind",), with_roles=False),
                                by_mode=size_list(grouped(rest_recs, lambda r: (r["mode"],)), ("mode",), with_roles=False),
                                by_movement=size_list(grouped(rest_recs, lambda r: (r["movement"],)), ("movement",), with_roles=False),
                                by_violation=size_list(grouped(rest_recs, lambda r: (r["violation"],)), ("violation",), with_roles=False)),
        "all_crashes_by_catch_all": size_list(grouped(recs, catch_kind), ("kind",), with_roles=False),
        "catch_all_buckets": raw,
        "chart_bars": CHART_BARS,
        "regroupings": [dict(regroup(f), name=n) for n, f in REGROUPINGS],
    }

    # Size by family: mode x finer violation group, each bar carrying its people by movement, so the movement that
    # points at a fix is still on the bar while the chart needs about a dozen bars.
    def by_movement(rs):
        g = grouped(rs, lambda r: r["movement (fine)"])
        return sorted(({"movement": m, "people_injured": sum(r["injured"] for r in sub),
                        "ksi_people": sum(r["people"] for r in sub)} for m, sub in g.items()),
                      key=lambda t: (-t["people_injured"], -t["ksi_people"], t["movement"]))
    g_fam = grouped([r for r in recs if r["mode"] != "not stated"], lambda r: (r["mode"], r["violation (fine)"]))
    families = size_list(g_fam, ("mode", "violation"))
    def by_at_fault(rs):
        hurt, ksi = collections.Counter(), collections.Counter()
        for r in rs:
            hurt[r["at-fault party type"]] += r["injured"]
            ksi[r["at-fault party type"]] += r["people"]
        return {"people_injured": dict(sorted(hurt.items())), "ksi_people": dict(sorted(ksi.items()))}
    for t in families:
        t["catch_all"] = t["violation"] in CATCH_ALL
        t["by_movement"] = by_movement(g_fam[(t["mode"], t["violation"])])
        t["by_at_fault_party_type"] = by_at_fault(g_fam[(t["mode"], t["violation"])])
    fam_shown = {(t["mode"], t["violation"]) for t in families[:FAMILY_TOP]} | {
        (t["mode"], t["violation"])
        for t in sorted(families, key=lambda t: (-t["ksi_people"], t["mode"], t["violation"]))[:FAMILY_TOP]}
    fam_rest = [r for r in recs if (r["mode"], r["violation (fine)"]) not in fam_shown]
    fam_chart = [{k: t[k] for k in ("mode", "violation", "catch_all") + SIZE_KEYS + ("by_movement",)}
                 for t in families if (t["mode"], t["violation"]) in fam_shown]
    fam_chart.append(dict({"mode": "all other families", "violation": "", "catch_all": False,
                           "groups": len(families) - len(fam_shown)},
                          **{k: tally(fam_rest)[k] for k in SIZE_KEYS}, by_movement=by_movement(fam_rest)))
    g_fine = grouped([r for r in recs if r["mode"] != "not stated"],
                     lambda r: (r["mode"], r["movement (fine)"], r["violation (fine)"]))
    size_families = {
        "about": "people hurt and KSI people by mode x violation family (VIOLATION_FINE), each with its people by "
                 "movement; chart is the union of the FAMILY_TOP biggest families by people hurt and by KSI people, then "
                 "one row over every other crash (mode not stated included), so the rows add up to the totals",
        "violation_groups": {name: list(prefixes) for name, prefixes in VIOLATION_FINE},
        "violation_code_fallback": "when vz_pcf_group is blank or Unknown, vz_pcf_code is read if it holds a section number",
        "chart": fam_chart,
        "families": families,
        "pairs_within_mode": size_list(g_fine, ("mode", "movement", "violation"), with_roles=False,
                                       floor=SIZE_FLOOR_WITHIN_MODE),
    }

    # Family by traffic stress: the biggest families' people hurt and KSI people by the crash's bike level of traffic
    # stress (crash_stress, the same rule as traffic_stress) and by street class.

    def stress_split(rs):
        bands = {b: {"people_injured": sum(r["injured"] for r in rs if stress_band(r) == b),
                     "ksi_people": sum(r["people"] for r in rs if stress_band(r) == b)} for b in STRESS_BANDS}
        known = {k: bands[STRESS_BANDS[0]][k] + bands[STRESS_BANDS[1]][k] for k in ("people_injured", "ksi_people")}
        seg = [r for r in rs if r["block join"] == "segment" and stress_band(r) != "unknown"]
        classes = []
        for cls, sub in sorted(grouped(rs, lambda r: r["street class"]).items()):
            hi_sub = [r for r in sub if stress_band(r) == STRESS_BANDS[0]]
            classes.append({"street_class": cls, "people_injured": sum(r["injured"] for r in sub),
                            "ksi_people": sum(r["people"] for r in sub),
                            "people_injured_high_stress": sum(r["injured"] for r in hi_sub),
                            "ksi_people_high_stress": sum(r["people"] for r in hi_sub)})
        return {"people_injured": sum(r["injured"] for r in rs), "ksi_people": sum(r["people"] for r in rs),
                "by_stress": bands,
                "share_high_stress_of_known": {k: round(bands[STRESS_BANDS[0]][k] / known[k], 4) if known[k] else None
                                               for k in known},
                "segment_crashes_share_high_stress_of_known": round(
                    sum(r["injured"] for r in seg if stress_band(r) == STRESS_BANDS[0]) / sum(r["injured"] for r in seg), 4)
                if sum(r["injured"] for r in seg) else None,
                "by_street_class": classes}
    family_stress = {
        "about": "the FAMILY_STRESS_TOP biggest size_families by people hurt, split by the bike level of traffic stress "
                 "of the crash's most stressful block (high is LTS 3 or 4) and by street class; segment_crashes_share "
                 "is the high-stress share among crashes placed on one block, which carry no lean toward the "
                 "intersection's busier street",
        "surface_street_miles_share_high_stress": stress["high_stress_total"]["share_of_surface_street_miles"],
        "all_crashes": stress_split(recs),
        "families": [dict({"mode": t["mode"], "violation": t["violation"], "catch_all": t["catch_all"]},
                          **stress_split(g_fam[(t["mode"], t["violation"])])) for t in families[:FAMILY_STRESS_TOP]],
    }

    # Grouping alternatives: other ways to cut everyone hurt, each scored like other_breakdown.regroupings and given
    # with its top CHART_BARS bars. Crash groupings count a crash's people; the person groupings count victims rows.
    def compare(items, catch):
        """items: (key tuple, people hurt, KSI people), one per crash or person; catch: the values that name no kind."""
        g = collections.defaultdict(lambda: [0, 0])
        for k, h, p in items:
            g[k][0] += h
            g[k][1] += p
        ranked = sorted(g.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        run, to80 = 0, None
        for i, (_, (h, _p)) in enumerate(ranked, 1):
            run += h
            if run * 5 >= H * 4:
                to80 = i
                break
        is_catch = lambda k: any(v in catch for v in k)  # noqa: E731
        top = ranked[:CHART_BARS]
        remainder = H - sum(h for _, (h, _p) in top)
        top_catch = sum(h for k, (h, _p) in top if is_catch(k))
        return {"groups": len(g),
                "share_of_people_injured_in_catch_all_groups": round(sum(h for k, (h, _p) in ranked if is_catch(k)) / H, 4),
                "bars_to_80pct_of_people_injured": to80,
                "share_in_remainder_at_chart_bars": round(remainder / H, 4),
                "share_in_catch_all_bars_at_chart_bars": round(top_catch / H, 4),
                "share_left_in_catch_all_or_remainder": round((remainder + top_catch) / H, 4),
                "top_bars": [{"group": list(k), "catch_all": is_catch(k), "people_injured": h,
                              "share_of_people_injured": round(h / H, 4), "ksi_people": p,
                              "share_of_ksi_people": round(p / P, 4)} for k, (h, p) in top],
                "remainder": {"people_injured": remainder, "ksi_people": P - sum(p for _, (_h, p) in top)}}

    rec_of = {r["case"]: r for r in recs}
    persons = [(v, rec_of[v["case_id_pkey"]]) for v in victims
               if v["victim_degree_of_injury"] not in NOT_HURT and v["case_id_pkey"] in rec_of]

    def items_of(unit, key):
        if unit == "person":
            return [(key(v, r), 1, int(v["victim_degree_of_injury"] in KSI_PERSON)) for v, r in persons]
        return [(key(r), r["injured"], r["people"]) for r in recs]
    grouping_alternatives = {
        "about": "other groupings of everyone hurt, scored as in other_breakdown.regroupings, each with its top "
                 "CHART_BARS bars. A person grouping counts victims rows with any injury (age outside 1 to 109 is not "
                 "stated); a crash grouping counts each crash's people. Catch-all values: not stated, unknown, other, "
                 "Other, Not Stated, the movement and time not-stated values; victim role Other is named as scooter or other",
        "chart_bars": CHART_BARS,
        "recommended_for_comparison": regroup(("mode", "violation (fine)")),
        "groupings": [dict(compare(items_of(u, key), set(STATED)), id=gid, name=n, unit=u) for gid, n, u, key in GROUPINGS],
    }

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
        "totals": {"injury_crashes": N, "ksi_crashes": K, "ksi_people": P, "people_injured": H,
                   "citywide_ksi_rate": round(p0, 4), "by_victim_role": roles(recs)},
        "rules": {"min_injury_crashes": MIN_INJURY_CRASHES, "alpha": ALPHA, "cells_possible": len(cells),
                  "cells_tested": m, "within_mode_cells_possible": mode_cells_possible,
                  "level2_tests": tests,
                  "test": "one-sided exact binomial on KSI crashes vs citywide (or the mode's) KSI crash rate, "
                          "Bonferroni over cells tested; a cell is tested when it holds MIN_INJURY_CRASHES injury crashes"},
        "size": size,
        "traffic_stress": stress,
        "other_breakdown": other_breakdown,
        "size_families": size_families,
        "family_stress": family_stress,
        "grouping_alternatives": grouping_alternatives,
        "profiles": profiles,
        "level1_tested": level1,
        "level1_margins": margins,
        "movement_by_violation": movement_by_violation,
        "mode_totals": mode_totals,
        "level1_within_mode": within_mode,
        "level1_within_mode_cells_tested": len(mode_tested),
        "mode_by_year": mode_by_year,
        "level2": level2,
        "context": context,
        "street_sources_read_on": {"3psu-pn9h": streets_src.read_on, "ybh5-27n2": signals_src.read_on},
        "network": {"miles_by_street_class": {k: round(v, 1) for k, v in sorted(miles.items())},
                    "surface_street_miles": round(surface_miles, 1),
                    "intersections_by_corner_type": dict(sorted(corners.items()))},
        "pedestrian_light_by_posted_limit": ped_light_speed,
        "pedestrian_time_by_light": ped_time_light,
        "signals_at_intersections": signals,
        "vehicle_weight": weight_out,
        "pedestrian_profile_facts": pedestrian_facts,
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
