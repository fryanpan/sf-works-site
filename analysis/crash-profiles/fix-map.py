#!/usr/bin/env python3
"""Merge the crash-fix lanes into one map of SF crash groups to fixes, with people hurt and KSI avoided, cost per injury avoided and stacked packages.

Reads analysis/crash-profiles/fixes/lanes/*.json (critique.json is read for gaps
only; fill.json is applied last and overrides by id), merges records that are
the same treatment under different names (ALIASES), validates every record
against the schema in analysis/crash-profiles/fixes/README.md, joins SF counts
from out/crash-augment/profiles/results.json, and writes
out/crash-augment/profiles/fix-map.json.

Counting rules (each one is also in the README):

- People hurt and KSI people are the collision years results.json counts
  (crash-profiles.py's YEARS, 2018 to 2025), from size_families.families. A
  year is the count over the number of years.
- The lanes' target_share texts quote 2017 to 2024 counts, the window they
  were researched on. fixes/lane-counts.json holds those counts (written once
  from the 2017 to 2024 results.json with --freeze-lane-counts), so an "A of
  B" text whose B is a 2017 to 2024 group total is still read as the share
  A / B, and that share is applied to the current window's counts.
- An effect is normalised to a fraction r of the target crashes removed
  (positive is fewer): "% fewer" is r = v/100; "% change" is r = -v/100;
  a CMF, rate ratio, odds ratio or RR is r = 1 - v. Low, mid and high are
  re-sorted so low is the smallest cut.
- An effect is applied only where it is a crash or injury reduction: its unit
  must name a crash or injury outcome (not speeding, violations, yielding, an
  exponent or elasticity, a hazard, a share of crashes, or a per-trip injury
  odds ratio, NOT_A_REDUCTION), its applies_to must not say it is not one to use
  here (an emergency department sample, a rural design, DO_NOT_APPLY), and an
  effect that names one road user (pedestrian, cyclist) is applied only to that
  mode's groups. A fix whose rows left after that are all harmful, while a
  row was dropped for its unit, counts only a side effect of what its studies
  measured, and is not computable (side_effect_only). EFFECT_FROM_GROUP gives an entry the record's own value where
  its lane value is a manual one that is not about the group.
- Severity is read per value (value_scope): from the unit, and from the
  applies_to and source where they tie a value to a severity ("Mid: London KSI
  -12%", "(high: killed)", "pedestrian severe injuries (0.67)"). A value on
  killed or seriously injured only ("fatal and serious", "KSI", "killed", "crash
  deaths") applies to KSI people; an all-injury value applies to everyone hurt.
  For people hurt, a KSI-only value is replaced by the nearest smaller all-injury
  value of the same record; an effect with no all-injury value removes KSI
  people only, who are counted as people hurt avoided too.
- Reach: a fix listed in analysis/crash-profiles/fixes/reach.json takes each
  family pair's share from out/crash-augment/profiles/fix-reach.json (written
  by fix-reach.py): the group's people hurt (and KSI people) in the place the
  fix goes, within the entry's movement if it names one, over the group's
  total. reach.json can keep the lane's own share where it names a party or
  crash type and multiply it by the place's fraction ("text": "multiply"). Its
  units name SF's count of those places, which replaces UNITS for that fix, and
  its life_years fills a record that has none (Caltrans LRSM Expected Life).
- Target share, for every other fix, is read from the record's target_share text: an explicit
  "N% of the group" wins; else "A of B" where B is the group's people hurt (or
  KSI people) total; else the whole group where the text says so; else the
  movement's share from size_families when the entry names a movement. Text
  that matches none of these leaves the pair not computable.
- SF's own evidence (SF_EVIDENCE, from the whitepaper's outcomes section and
  methods-by-intervention note, 2026-11-24) sets the low end where a lane's low
  is more hopeful: no effect where SF's 95% range includes 1, else 1 - SF's
  ratio (20 mph blocks, corrected for selection, 1.10, so a low of a 10% rise).
  Each pair records it.
- reach.json also nets out sites SF has already treated (treated: a fraction of
  the crashes reached and the units priced, or an exclusion in the place); a
  placed fix with no count says "most it could reach". Its cost replaces a
  lane's labour-only signal price, and its upkeep adds a yearly cost per unit.
- Counted crash by crash (Crashes, on fix-reach.py's crash records): each
  family entry reaches a set of crashes (a placed fix's place and movements; a
  text share's crashes the text names where a crash field records them, such as
  the at-fault party, the collision type, solo crashes or the street class, else
  the entry's movement, else the whole family, text_reach) and removes rho =
  share x r / f on each, f the fraction of the family's people those crashes
  hold, rho at most RHO_MAX (1, all of them) and with no floor, so a study's
  rise in crashes is applied in full. Each crash's KSI people and other people hurt
  are kept apart: a fix's people hurt avoided are its KSI people avoided plus
  its other people hurt avoided. A row's own avoided a year is group count a
  year x share x r, for the groups listing.
- Each fix's stack_terms in fix-map.json give, for every family it reaches,
  the share, the effect, the crashes it reaches (place and movements, and how
  they were picked) and its rho, so fix-groups.py can recount it.
- Annual cost: a per-year cost is used as is; a one-time cost is divided by
  life_years. A per-unit cost (per corner, mile, signal, camera) is multiplied
  by the SF unit count in UNITS, taken from the record's own text or from
  results.json; with no count, or with no life_years for a one-time cost, the
  fix's cost per injury is not computable. Dollar years are as the records give
  them and are not converted.
- Cost per person hurt avoided low = cost low / avoided high, mid = cost mid /
  avoided mid, high = cost high / avoided low.
- Value of injuries avoided: SF Budget and Legislative Analyst, Economic Costs
  and Fiscal Impacts of Traffic Collisions (2025), Exhibit 8: $36,949 an injury
  and $1,604,902 a death in 2019 dollars, $2,135,839,973 to $2,524,990,016
  from 2019 to 2024 dollars (economic cost only, no quality of life). Also USDOT
  BCA 2026 comprehensive values, per KSI person and per other person hurt,
  weighted by SF's 2022-2024 grade mix (2026-11-18 injury-costs note).
- Overlap: fixes on the same group are not summed in the ranking; each fix is
  ranked on its own. Stacks count sequentially (TRL PPR844) crash by crash: each
  crash keeps the fraction of its KSI people and of its other people hurt that
  the fixes before left, and an added fix removes rho of what is left on every
  crash it reaches, so fixes reaching the same crashes or nested places are
  never credited with more people than those crashes hold. What a crash keeps
  is never below 0 and has no ceiling, so harm is counted in full. The families include mode not
  stated, so they hold everyone hurt. "all other families" entries are applied
  to each family outside the chart, unless a fix maps that family itself.
  Cross-cut groups ("place |", "who |", "time |", crash types) overlap the
  families and are reported, not stacked. Every stack is checked: no crash or
  family has more people avoided than it holds.
- CONFLICTS lists fixes that are versions of one another, or alternatives at
  one place (the left-turn treatments at an arterial corner, a raised or a
  high-visibility crosswalk at an unsignalized crossing); a stack takes the
  first of a conflicting set and skips the others.
- Each stack's steps carry the cumulative figures with every effect at its low
  and at its high (same order and costs). The optimistic and pessimistic stacks
  replay greedy_by_people_hurt's fixes in its order with every effect at its
  high (costs low) and its low (costs high), harmful lows included.

Standard library only. Deterministic: sorted keys and lists, no wall clock.

    python3 analysis/crash-profiles/fix-map.py
    python3 analysis/crash-profiles/fix-map.py --freeze-lane-counts RESULTS_2017_2024.json   # once, see above
"""

import collections
import glob
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LANES = os.path.join(ROOT, "analysis", "crash-profiles", "fixes", "lanes")
RESULTS = os.path.join(ROOT, "out", "crash-augment", "profiles", "results.json")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "fix-map.json")

YEARS = None  # the number of collision years in results.json, set in main()
Q = ("low", "mid", "high")
LANE_COUNTS = os.path.join(ROOT, "analysis", "crash-profiles", "fixes", "lane-counts.json")
LANE_YEARS = [2017, 2024]  # the window the lanes' target_share texts were researched on
LEVERS = [
    "street design", "signals", "speed management", "traffic volume and filtering",
    "pricing", "vehicles and fleets", "automated enforcement", "behaviour programs",
    "transit and land use", "policy and law",
]
LANE_ORDER = ["area", "junction", "pedestrian", "speed", "bike", "crosscut"]
BUDGETS = [10e6, 50e6, 100e6, 500e6]

# BLA 2025, Exhibit 8 (read 2026-11-25): 2019 dollars, scaled to 2024 by the
# exhibit's own totals.
BLA_TO_2024 = 2524990016 / 2135839973
BLA_PER_INJURY_2024 = 36949 * BLA_TO_2024
BLA_SOURCE = {
    "title": "SF Budget and Legislative Analyst, Economic Costs and Fiscal Impacts of Traffic Collisions, 2025-04-23, Exhibit 8",
    "url": "https://sfbos.archive.sf.gov/sites/default/files/BLA.Traffic_Crash_Costs.042325.pdf",
    "tag": "[primary — read 2026-11-25]",
    "note": "Economic cost only: $36,949 an injury and $1,604,902 a death (2019 dollars), x %.4f to 2024 dollars from the exhibit's totals. The BLA also scales police counts by 1.47 for unreported injuries; that multiplier is not applied here, so the value is a floor." % BLA_TO_2024,
}
# USDOT BCA 2026 Table A-1 (2024 dollars), weighted by SF police grades
# 2022-2024 (108 K, 815 A, 2,771 B, 7,465 C), from the 2026-11-18 note.
USDOT_PER_KSI = (108 * 13_700_000 + 815 * 1_302_300) / 923
USDOT_PER_OTHER_HURT = (2771 * 256_300 + 7465 * 122_400) / 10236
USDOT_SOURCE = {
    "title": "USDOT Benefit-Cost Analysis Guidance 2026, Table A-1, via research/notes/whitepaper-2026-11/part-1/2026-11-18-injury-costs-and-burden.md",
    "url": "research/notes/whitepaper-2026-11/part-1/2026-11-18-injury-costs-and-burden.md",
    "tag": "[secondary — verify] (the note read the table as primary on 2026-11-18); grade weighting is [inference — mine]",
}

# Same treatment under different names: alias id -> canonical id.
ALIASES = {
    "congestion-pricing": "area-cordon-congestion-charge",
    "congestion-pricing-cordon": "area-cordon-congestion-charge",
    "low-traffic-neighbourhood": "ltn-cell-program-citywide",
    "low-traffic-neighbourhoods": "ltn-cell-program-citywide",
    "through-traffic-filters": "ltn-cell-program-citywide",
    "superblocks": "superblock-and-car-free-centre-program",
    "school-streets": "school-streets-citywide-program",
    "filtered-bike-routes": "slow-streets-network",
    "hardened-daylighting": "daylighting-hardened",
    "daylighting-state-rule-ab413": "citywide-daylighting-every-corner",
    "corner-sight-lines": "citywide-daylighting-every-corner",
    "area-traffic-calming": "vertical-calming-residential",
    "speed-humps-area-calming": "vertical-calming-residential",
    "road-diet": "lane-reduction-road-diet",
    "road-diet-four-to-three": "lane-reduction-road-diet",
    "raised-median-corridor": "curbed-median",
    "raised-median-urban": "curbed-median",
    "hardened-centerline-turn-calming": "left-turn-calming-hardened-centerline",
    "left-turn-ban": "left-turn-restrictions",
    "left-turn-lane-and-phase": "protected-left-turn-phase",
    "speed-cameras": "fixed-speed-cameras",
    "speed-safety-cameras": "fixed-speed-cameras",
    "mobile-speed-cameras": "rotating-mobile-camera-coverage",
    "isa-new-vehicle-mandate": "isa-new-vehicles-mandate",
    "pedestrian-aeb": "aeb-fleet-and-mandate",
    "aeb-cyclist-detection-fleet": "aeb-fleet-and-mandate",
    "junction-aeb-fleet-rules": "aeb-fleet-and-mandate",
    "rear-cameras-sensors-and-rear-aeb": "rear-visibility",
    "automated-vehicles": "automated-vehicle-fleets",
    "raised-intersection": "raised-crosswalk-or-intersection",
    "intersection-lighting": "street-lighting-upgrade",
    "crossing-lighting": "street-lighting-upgrade",
    "signal-progression-at-safe-speed": "citywide-signal-retiming-safe-speed",
    "signal-progression-low-speed": "citywide-signal-retiming-safe-speed",
    "bike-speed-signal-timing": "citywide-signal-retiming-safe-speed",
    "lower-limit-signs-only": "lower-speed-limits",
    "signal-at-unsignalized-or-all-way-stop": "new-traffic-signal",
    "direct-vision-large-vehicles": "direct-vision-standard-trucks",
    "truck-direct-vision": "direct-vision-standard-trucks",
    "protected-bike-lane-corner": "quick-build-separated-lane",
    "fewer-car-miles-volume": "mode-shift-safety-in-numbers",
    "front-end-and-weight-rules": "pedestrian-protecting-front-ends",
}

# Versions of one another: a stack takes only one of each pair.
_CONFLICT_SETS = [
    ["citywide-default-20mph", "neighbourhood-signed-20mph-zones", "lower-speed-limits"],
    ["area-wide-engineered-20mph-zones", "vertical-calming-residential"],
    ["citywide-speed-camera-network", "fixed-speed-cameras", "lift-camera-cap", "rotating-mobile-camera-coverage"],
    ["ltn-cell-program-citywide", "street-hierarchy-through-network", "superblock-and-car-free-centre-program", "slow-streets-network"],
    ["citywide-daylighting-every-corner", "daylighting-hardened", "parking-removal-near-junctions-and-on-bike-routes"],
    ["curb-protected-bike-lane", "quick-build-separated-lane", "connected-network-plan"],
    ["roundabout-conversion", "mini-roundabout-traffic-circle", "all-way-stop-conversion", "new-traffic-signal"],
    ["midblock-pedestrian-signal", "pedestrian-hybrid-beacon", "rectangular-rapid-flashing-beacon"],
    ["leading-pedestrian-interval", "exclusive-pedestrian-phase"],
    ["school-streets-citywide-program", "school-zone-measures"],
    ["longer-crossing-time-older-pedestrians", "safe-streets-for-seniors-program"],
    ["curb-extension-tighter-corner", "daylighting-hardened"],
    ["red-light-cameras", "civil-red-light-penalty-opt-in"],
    ["aeb-fleet-and-mandate", "fleet-purchasing-safety-rating-rule"],
    ["publicized-sobriety-checkpoints", "mass-media-with-dui-enforcement"],
    # Alternatives at one place, each costed at every place of its kind: one left-turn treatment per arterial corner,
    # and one crosswalk treatment per unsignalized crossing.
    ["left-turn-restrictions", "curbed-median", "left-turn-lane-channelisation", "left-turn-calming-hardened-centerline",
     "protected-left-turn-phase"],
    ["raised-crosswalk-or-intersection", "high-visibility-crosswalk"],
]
_BUNDLES = {
    "systemic-hin-intersection-program": ["leading-pedestrian-interval", "daylighting-hardened", "citywide-daylighting-every-corner", "protected-left-turn-phase"],
    "dui-checkpoints-and-limits": ["bac-limit-0-05", "publicized-sobriety-checkpoints", "ignition-interlocks-all-offenders", "late-night-transit"],
    "community-area-safety-plans": [],
}
CONFLICTS = set()
for s in _CONFLICT_SETS:
    for a in s:
        for b in s:
            if a != b:
                CONFLICTS.add((a, b))
for a, members in _BUNDLES.items():
    for b in members:
        CONFLICTS.add((a, b))
        CONFLICTS.add((b, a))

# SF unit counts for per-unit costs. Each count is quoted from the merged
# record's own unit or cost text, or from results.json; nothing here is a guess.
SIGNALS_NOTE = "1,249 signalized intersections (results.json signals_at_intersections); assumes every signal is treated"
# Counts that are only part of the stock the target_share text describes: for
# these a pair needs an explicit "N% of the group" share, or it is not computed.
PARTIAL_UNITS = {"fixed-speed-cameras", "slow-streets-network", "school-crossing-guards"}
# Fixes whose reach no record gives, so a whole-group share in the text overstates it.
REACH_UNKNOWN = {
    "automated-vehicle-fleets": "reach is the share of SF vehicle miles moved to driverless cars, which no record gives (critique misfit)",
    "micromobility-speed-and-night-limits": "reach is the shared-scooter share of the group, which no record gives",
}
UNITS = {
    "ltn-cell-program-citywide": (152, 152, "SF's 152 candidate cells (record unit, out/low-traffic-cells/candidates.json)"),
    "area-wide-engineered-20mph-zones": (887, 887, "887 unposted SF street miles (record unit)"),
    "citywide-speed-camera-network": (320, 740, "about 320 to 740 locations for a network design test (record unit)"),
    "fixed-speed-cameras": (33, 33, "SF's 33 camera locations under AB 645 (record name and cost text)"),
    "citywide-daylighting-every-corner": (8900, 8900, "8,900 SF intersections (record unit; 'paint everywhere $4.45M' in the cost text)"),
    "slow-streets-network": (30, 85, "the repo's first 30 miles to the plan's 85 miles of Shared streets (record unit)"),
    "systemic-hin-intersection-program": (1249, 1249, "1,249 signalized intersections (record unit, results.json)"),
    "citywide-signal-retiming-safe-speed": (1249, 1249, "1,249 signalized intersections (record unit, results.json)"),
    "school-streets-citywide-program": (230, 230, "more than 230 schools named for safety work by 2028 (record unit)"),
    "school-crossing-guards": (90, 97, "about 90 to 97 schools with guards (record cost text)"),
}
SIGNAL_TIMING_IDS = [
    "leading-pedestrian-interval", "all-red-clearance", "yellow-change-interval-standard",
    "no-late-night-signal-flash", "exclusive-pedestrian-phase", "leading-bike-interval",
    "longer-crossing-time-older-pedestrians", "shorter-pedestrian-waits",
]
for _i in SIGNAL_TIMING_IDS:
    UNITS[_i] = (1249, 1249, SIGNALS_NOTE)
# Cost text that gives a total over several years rather than a unit price.
COST_TOTAL_OVER_YEARS = {"pedestrian-education": 5}  # "FY27 to 31 total"

# SF's own before-and-after results, which set the low end where an outside effect is more hopeful. ratio is the
# change in injury crashes on treated streets (1 is no change), lo and hi its 95% range (hi None: no upper bound).
# modes limits a result to the groups of those modes. The low becomes no effect where the range includes 1, else
# 1 - ratio; it is changed only where the lane's own low is more hopeful than that.
_SF_SRC = ("SF Works whitepaper Part 1, outcomes section and methods-by-intervention note, 2026-11-24, from DataSF "
           "ubvf-ztfx and the treatment datasets named there. [DataSF ubvf-ztfx — queried 2026-11-24] [inference — mine]")
# The 20 mph result uses the corrected reading: the raw 1.27 (1.20 to 1.34) carries a 6 to 16 point selection lean
# on these blocks, and after either correction crashes still ran 10% to 20% above expected, unexplained.
_TWENTY = {"ratio": 1.10, "lo": 1.10, "hi": 1.20, "modes": None, "what": "821 dated 20 mph blocks, corrected reading: injury crashes ran 10% to 20% above expected (1.10 to 1.20), unexplained; the raw 1.27 (1.20 to 1.34) includes 6 to 16 points of selection lean (methods-by-intervention note). The low is the 10% rise"}
_QUICK = {"ratio": 1.02, "lo": 0.95, "hi": 1.09, "modes": None, "what": "31 quick-build corridors, Empirical Bayes with traffic volumes: 1.02 (0.95 to 1.09), about no change"}
_HUMPS = {"ratio": 1.04, "lo": 0.51, "hi": None, "modes": None, "what": "818 hump blocks: 0.82 (0.60 to 1.20) against waiting blocks, about no change (1.04, 0.51 with no upper bound) after their pre-trend"}
_CAMS = [{"ratio": 0.80, "lo": 0.53, "hi": 1.20, "modes": ["pedestrian involved"], "what": "33 camera locations, crashes involving someone walking after the matched-street check: 0.80 (0.53 to 1.20)"},
         {"ratio": 0.91, "lo": 0.77, "hi": 1.08, "modes": None, "what": "33 camera locations, all injury crashes after the matched-street check: 0.91 (0.77 to 1.08)"}]
SF_EVIDENCE = {
    "citywide-default-20mph": [_TWENTY], "neighbourhood-signed-20mph-zones": [_TWENTY], "lower-speed-limits": [_TWENTY],
    "lane-reduction-road-diet": [{"ratio": 1.01, "lo": 0.92, "hi": 1.09, "modes": None, "what": "16 road diet corridors with traffic volumes in the model: 1.01 (0.92 to 1.09)"}],
    "corridor-traffic-calming-through-roads": [_QUICK], "quick-build-separated-lane": [_QUICK],
    "citywide-daylighting-every-corner": [{"ratio": 1.07, "lo": 0.86, "hi": 1.30, "modes": ["pedestrian involved"], "what": "249 painted safety zones: pedestrians hurt 1.07 (0.86 to 1.30) against nearby unpainted corners"}],
    "vertical-calming-residential": [_HUMPS], "area-wide-engineered-20mph-zones": [_HUMPS],
    "fixed-speed-cameras": _CAMS, "citywide-speed-camera-network": _CAMS, "rotating-mobile-camera-coverage": _CAMS,
    "slow-streets-network": [{"ratio": 0.73, "lo": 0.58, "hi": 0.88, "modes": None, "what": "19 Slow Streets: injury crashes 0.73 (0.58 to 0.88); 15 opened in 2020-2021, and SFMTA's counts show traffic at 0.38 of before, so the fall looks like less traffic"}],
}


def sf_low(ev):
    """The low effect (fraction removed) SF's result sets: none where its range includes 1, else 1 - ratio."""
    if ev["hi"] is None or ev["lo"] <= 1 <= ev["hi"]:
        return 0.0
    return 1 - ev["ratio"]


# ---------------------------------------------------------------- reach (fix-reach.json, reach.json)

REACH_FILE = os.path.join(ROOT, "analysis", "crash-profiles", "fixes", "reach.json")
FIX_REACH = os.path.join(ROOT, "out", "crash-augment", "profiles", "fix-reach.json")
TIME_SUFFIX = {"late night (11 pm-6 am)": "late_night"}


def parse_movements(mv, known):
    """An entry's movement text as (movements, extra place) or raises ValueError. Pieces are split on ';'."""
    if not mv:
        return None, None
    out, extra = [], None
    for piece in [p.strip() for p in mv.split(";") if p.strip()]:
        for suf, tag in TIME_SUFFIX.items():
            if piece.endswith(", " + suf):
                piece, extra = piece[: -len(suf) - 2].strip(), tag
        if piece not in known:
            raise ValueError("movement %r not in size_families" % piece)
        out.append(piece)
    return out, extra


class Reach(object):
    """Shares of a group in a kind of place, from fix-reach.json, for the fixes reach.json maps."""

    def __init__(self, fam, remainder):
        self.cfg = load(REACH_FILE)["fixes"] if os.path.exists(REACH_FILE) else {}
        self.data = load(FIX_REACH) if os.path.exists(FIX_REACH) else None
        self.fam, self.remainder = fam, remainder
        self.known = sorted({m for f in fam.values() for m in f["movements"]})

    def place_of(self, cid, gname):
        c = self.cfg[cid]
        return ((c.get("by_group") or {}).get(gname) or {}).get("place") or c["place"]

    def text_mode(self, cid, gname):
        return ((self.cfg[cid].get("by_group") or {}).get(gname) or {}).get("text", "replace")

    def counts(self, gname, place, mvs):
        """(place hurt, place ksi, group hurt, group ksi, movement hurt, movement ksi) for a family or the remainder."""
        members = self.remainder if gname == "all other families" else [gname]
        tot = [0, 0, 0, 0, 0, 0]
        for m in members:
            g = self.data["groups"].get(m)
            if g is None:
                raise KeyError("group %r not in fix-reach.json" % m)
            P = g["places"].get(place)
            if P is None:
                raise KeyError("place %r not in fix-reach.json; run fix-reach.py after editing reach.json" % place)
            tot[2] += g["people_hurt"]
            tot[3] += g["ksi"]
            if mvs:
                for mv in mvs:
                    v = P["by_movement"].get(mv, [0, 0])
                    tot[0] += v[0]
                    tot[1] += v[1]
                    fm = self.fam[m]["movements"].get(mv, (0, 0))
                    tot[4] += fm[0]
                    tot[5] += fm[1]
            else:
                tot[0] += P["people_hurt"]
                tot[1] += P["ksi"]
                tot[4] += g["people_hurt"]
                tot[5] += g["ksi"]
        return tot

    def share(self, cid, gname, movement, text_share):
        """(share hurt, share ksi, basis) or (None, None, reason)."""
        if self.data is None:
            return None, None, "out/crash-augment/profiles/fix-reach.json missing; run fix-reach.py"
        place = self.place_of(cid, gname)
        try:
            mvs, extra = parse_movements(movement, self.known)
            if extra:
                place = "%s&%s" % (place, extra) if "|" not in place else None
                if place is None:
                    raise KeyError("an or-place with a time movement is not supported")
            ph, pk, gh, gk, mh, mk = self.counts(gname, place, mvs)
        except (KeyError, ValueError) as e:
            return None, None, "reach: %s" % e.args[0]
        if not gh:
            return None, None, "reach: group has nobody hurt"
        scale = self.cfg[cid].get("share_scale", 1.0)
        left = self.left(cid)
        mode = self.text_mode(cid, gname)
        if mode == "multiply" and text_share is not None:
            th, tk = text_share
            fh = ph / mh if mh else 0.0
            fk = pk / mk if mk else fh
            sh, sk = th * fh, tk * fk
            basis = "lane share x %s fraction of %s (fix-reach.json)" % (place, "the movement" if mvs else "the group")
        else:
            sh = ph / gh
            sk = pk / gk if gk else sh
            basis = "%s share of the group%s (fix-reach.json)" % (place, " within " + "; ".join(mvs) if mvs else "")
        if scale != 1.0:
            sh, sk = sh * scale, sk * scale
            basis += ", x %s (%s)" % (scale, self.cfg[cid].get("scale_basis", ""))
        if left != 1.0:
            sh, sk = sh * left, sk * left
            basis += ", x %s not yet treated" % round(left, 4)
        return sh, sk, basis

    def reach_set(self, cid, gname, movement):
        """(place expression, movements) of the crashes a placed fix reaches in a family, as share() counts them."""
        place = self.place_of(cid, gname)
        mvs, extra = parse_movements(movement, self.known)
        if extra:
            place = "%s&%s" % (place, extra)
        return place, mvs

    def left(self, cid):
        """The fraction of sites not yet treated, where reach.json gives SF's count of what is done."""
        t = (self.cfg.get(cid) or {}).get("treated") or {}
        return 1.0 - t["fraction"] if "fraction" in t else 1.0

    def net_note(self, cid):
        t = (self.cfg.get(cid) or {}).get("treated") or {}
        if t.get("fraction") == 0:
            return "nothing to net out: " + t["basis"]
        if "fraction" in t:
            return "already treated netted out: %s%% of sites (%s)" % (round(100 * t["fraction"]), t["basis"])
        if "by_place" in t:
            return "already treated netted out by place: " + t["by_place"]
        return "most it could reach: SF has no count of the sites already treated, so none are netted out"

    def units(self, cid):
        c = self.cfg.get(cid) or {}
        key = c.get("units")
        if not key or self.data is None:
            return None
        u = self.data["units"].get(key)
        if not u or u.get("value") is None:
            return None
        n = u["value"] * c.get("units_scale", 1) * self.left(cid)
        note = "%s %s (%s; %s)" % (("{:,.1f}" if isinstance(u["value"], float) else "{:,}").format(u["value"]),
                                   key.replace("_", " "), u["how"], u["tag"])
        if c.get("units_scale"):
            note += " x %s (%s)" % (c["units_scale"], c.get("scale_basis", ""))
        if self.left(cid) != 1.0:
            note += " x %s not yet treated" % round(self.left(cid), 4)
        return (n, n, note)

    def upkeep(self, cid):
        """(low, high, basis) a year, or None."""
        k = (self.cfg.get(cid) or {}).get("upkeep")
        if not k or self.data is None:
            return None
        u = self.data["units"].get(k["units"]) or {}
        if u.get("value") is None:
            return None
        n = u["value"]
        return (k["low_per_unit"] * n, k["high_per_unit"] * n,
                "upkeep $%s to $%s a year per %s x %s (%s)" % ("{:,}".format(k["low_per_unit"]), "{:,}".format(k["high_per_unit"]),
                                                             k["units"].replace("_", " ").rstrip("s"), u["value"], k["basis"]))

# Laws that only allow another fix: the benefit and the cost sit with that fix.
ENABLERS = {
    "camera-enforced-filters-state-law": "ltn-cell-program-citywide",
    "lift-camera-cap": "citywide-speed-camera-network",
    "civil-red-light-penalty-opt-in": "red-light-cameras",
}

NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
CROSS_PREFIXES = ("place |", "who |", "time |", "pedestrian |")


def num(s):
    return float(s.replace(",", ""))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def lane_name(path):
    return os.path.splitext(os.path.basename(path))[0]


# ---------------------------------------------------------------- merging

def read_lanes():
    lanes = {}
    for path in sorted(glob.glob(os.path.join(LANES, "*.json"))):
        name = lane_name(path)
        if name == "critique":
            continue
        lanes[name] = load(path)
    return lanes


def group_key(g):
    return (g.get("group") or "", g.get("movement") or "")


def apply_fill(records, fill):
    """records: {(lane, id): record}. Applies fill.json actions in file order."""
    log = []
    for x in fill.get("fixes", []):
        act = x.get("fill_action")
        ext = x.get("extends") or ""
        if ":" in ext:
            lane, tid = ext.split(":", 1)
            lane = lane.replace(".json", "")
        else:
            lane, tid = None, x["id"]
        key = (lane, tid) if lane else None
        if key not in records:
            cands = sorted(k for k in records if k[1] == tid)
            key = cands[0] if cands else None
        body = {k: v for k, v in x.items() if k not in ("fill_action", "extends")}
        if act == "new" or key is None:
            records[("fill", x["id"])] = body
            log.append({"action": act or "new", "id": x["id"], "target": "fill"})
            continue
        tgt = records[key]
        if act == "add_groups":
            have = {json.dumps(g, sort_keys=True) for g in tgt.get("groups") or []}
            for g in x.get("groups") or []:
                if json.dumps(g, sort_keys=True) not in have:
                    tgt.setdefault("groups", []).append(g)
            for k, v in body.items():
                if k not in ("groups", "id") and tgt.get(k) in (None, "", []) and v not in (None, "", []):
                    tgt[k] = v
        elif act == "misfit_corrected":
            new_groups = x.get("groups") or []
            names = {g.get("group") for g in new_groups}
            if new_groups:
                tgt["groups"] = [g for g in tgt.get("groups") or [] if g.get("group") not in names] + new_groups
            for k, v in body.items():
                if k not in ("groups", "id") and v not in (None, "", []):
                    tgt[k] = v
        elif act == "cost_added":
            if x.get("cost"):
                tgt["cost"] = x["cost"]
            if x.get("unit") and not tgt.get("unit"):
                tgt["unit"] = x["unit"]
            if x.get("life_years") is not None:
                tgt["life_years"] = x["life_years"]
        log.append({"action": act, "id": x["id"], "target": "%s:%s" % key})
    return log


def cost_known(c):
    return isinstance(c, dict) and (c.get("low") is not None or c.get("high") is not None)


def merge(records):
    """Merge by canonical id. The canonical id's own record leads; aliases add groups and fill gaps."""
    order = {n: i for i, n in enumerate(LANE_ORDER + ["fill"])}
    by = {}
    for (lane, rid), rec in records.items():
        cid = ALIASES.get(rid, rid)
        by.setdefault(cid, []).append((0 if rid == cid else 1, order.get(lane, 99), lane, rid, rec))
    merged = {}
    for cid, items in by.items():
        items.sort(key=lambda t: (t[0], t[1], t[3]))
        base = json.loads(json.dumps(items[0][4]))
        base["id"] = cid
        base["merged_from"] = sorted({"%s:%s" % (t[2], t[3]) for t in items})
        groups, seen = [], set()
        for _, _, lane, rid, rec in items:
            for g in rec.get("groups") or []:
                sig = json.dumps(g, sort_keys=True)
                if sig in seen:
                    continue
                seen.add(sig)
                g = dict(g)
                g["from"] = "%s:%s" % (lane, rid)
                groups.append(g)
            for k, v in rec.items():
                if k in ("groups", "id"):
                    continue
                if k == "cost":
                    if not cost_known(base.get("cost")) and cost_known(v):
                        base["cost"] = v
                        if rec.get("life_years") is not None:
                            base["life_years"] = rec["life_years"]
                    continue
                if base.get(k) in (None, "", []) and v not in (None, "", []):
                    base[k] = v
            if k == "sources":
                pass
        srcs, sseen = [], set()
        for _, _, _, _, rec in items:
            for s in rec.get("sources") or []:
                sig = (s.get("title"), s.get("url"))
                if sig not in sseen:
                    sseen.add(sig)
                    srcs.append(s)
        base["sources"] = srcs
        base["groups"] = groups
        merged[cid] = base
    return merged


# ---------------------------------------------------------------- validation

def validate(rec, family_names):
    errs = []
    for k in ("id", "name", "lever", "how_it_works", "groups", "unit", "cost",
              "life_years", "sf_now", "sf_evidence", "who_decides", "evidence_grade", "sources"):
        if k not in rec:
            errs.append("missing field %s" % k)
    if rec.get("lever") not in LEVERS:
        errs.append("lever not in list: %r" % rec.get("lever"))
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", rec.get("id") or ""):
        errs.append("id not kebab-case")
    c = rec.get("cost")
    if not isinstance(c, dict) or any(k not in c for k in ("low", "high", "year", "unit", "source", "tag")):
        errs.append("cost missing low/high/year/unit/source/tag")
    for i, g in enumerate(rec.get("groups") or []):
        for k in ("group", "mechanism", "target_share", "effect"):
            if k not in g:
                errs.append("group %d missing %s" % (i, k))
        e = g.get("effect")
        if not isinstance(e, dict) or any(k not in e for k in ("low", "mid", "high", "unit", "applies_to", "source", "tag")):
            errs.append("group %d effect missing keys" % i)
        name = g.get("group") or ""
        if name not in family_names and not name.startswith(CROSS_PREFIXES) and name != "all other families" \
                and " | crash type " not in name and "(cross-cut" not in name:
            errs.append("group %d not a size_families row or cross-cut: %r" % (i, name))
    for s in rec.get("sources") or []:
        if not all(k in s for k in ("title", "url", "tag")):
            errs.append("source missing title/url/tag")
            break
    return errs


# ---------------------------------------------------------------- effects

NON_CRASH = re.compile(
    r"speeding incid|drivers going|share of|yielding|close calls|restraint use|exponent|elasticity|"
    r"behaviour odds|^count$|association|rate of crossing|not crashes|worse outcome|hazard|"
    r"tracks present|block with construction|^direction only$|see components|wearing rate|"
    r"no measured|no crash effect|no effect", re.I)
# Units that are never a crash or injury reduction, whatever crash word they also carry: a share of crashes rather
# than a change ("% of track crashes ... (none found)"), and a per-trip injury odds ratio from emergency department
# case-control studies, which measures a rider's risk on a facility, not the crashes a fix removes.
NOT_A_REDUCTION = re.compile(
    r"not crashes|exponent|elasticity|worse outcome|hazard|tracks present|block with construction|wearing rate|"
    r"association|none found|^%\s+of\b|per trip", re.I)
# applies_to text that says the effect is not one to use here: an emergency department sample (the per-trip odds
# ratios above), a rural design the handbook says to credit through the power model instead, a rural clear zone.
DO_NOT_APPLY = re.compile(r"emergency department|rural design|not urban streets", re.I)
CRASH_WORDS = re.compile(r"crash|injur|casualt|collision|accident|death|killed|fatal|ksi|^cmf|cmf\b|^rr\b|rate ratio|odds ratio|incidence", re.I)
# A record's own other value replaces one entry's effect: (fix, group) -> (group whose effect is used, why).
EFFECT_FROM_GROUP = {
    ("lane-reduction-road-diet", "vehicles only | red light"): (
        "vehicles only | vehicle right of way",
        "the entry's 35% is the LRSM's manual CRF for all crashes and not red-light specific; the record's own corridor "
        "value (FHWA-HRT-10-053, CMF 0.81, with SF's 16 corridors as the low) is used, as on its other groups"),
}

# ---- severity: which values measure every injury and which killed or seriously injured (KSI) only
ALL_SEV = re.compile(
    r"fatal\w*\s*(?:and|or|&|\+)\s*(?:all\s+|minor\s+)?injur\w*|injur\w*\s+(?:and|or)\s+fatal\w*|fatal and non-?fatal|"
    r"all severities|every severity|\bkabc\b|any injur\w*|serious\w*\s+(?:and|or)\s+minor|minor\s+(?:and|or)\s+serious|"
    r"\bslight", re.I)
_KQ = r"(?:\bksi\b|\bk\+a\b|killed|fatal\w*|serious\w*|severe\w*|deaths?\b)"
KSI_NP = re.compile(
    r"\b(?:crash|collision|traffic|road)\w*\s+(?:deaths?|fatalit\w*)\b|" + _KQ + r"(?:\s*(?:and|or|,|&)\s*" + _KQ +
    r")*(?:\s+[\w\-]+){0,3}?\s+(?:crash\w*|injur\w*|casualt\w*|collision\w*|accident\w*|victims?\b|outcomes?\b|"
    r"people\b|involvements?\b)|" + _KQ, re.I)
GENERIC = re.compile(r"injur|casualt|crash|collision|accident|\bhurt\b", re.I)
QLABEL = re.compile(r"\b(low|mid|high)\b(?:\s+and\s+(low|mid|high)\b)?(?:\s*\([^()]*\))?\s*:", re.I)
LABELLED_PAREN = re.compile(r"\([^()]*\b(?:low|mid|high)\b[^()]*:[^()]*\)", re.I)
NUMTOK = re.compile(r"(?<![\w.])[-+−]?(\d+(?:\.\d+)?)\s*(%)?")
# Values whose severity the record's text gives only by naming the study: fix -> [(r, scope, why)].
SEVERITY_BY_VALUE = {
    "midblock-pedestrian-signal": [(0.446, "ksi", "CMF 0.554 is Fitzpatrick et al. 2024 (CMF Clearinghouse 11753), "
                                                  "the FHWA value applies_to calls fatal and serious vehicle-pedestrian crashes")],
}


def classify(text):
    """'all', 'ksi' or None: whether a phrase measures every injury severity, killed or seriously injured only, or
    names no outcome. An every-severity phrase ("fatal and injury", "injuries and fatalities") is all; otherwise a
    killed or serious qualifier with its noun ("fatal crashes", "KSI casualties", "fatal and serious crashes",
    "crash deaths") is taken out, and the phrase is all if an unqualified outcome word is left, KSI if not."""
    t = text or ""
    if ALL_SEV.search(t):
        return "all"
    s = KSI_NP.sub(" ", t)
    if GENERIC.search(s):
        return "all"
    return "ksi" if s != t else None


def segments(text):
    """{'low' | 'mid' | 'high': text} from 'Low: ... Mid: ... High: ...' labels in a unit or applies_to."""
    out, ms = {}, list(QLABEL.finditer(text or ""))
    for i, m in enumerate(ms):
        seg = text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        for g in (m.group(1), m.group(2)):
            if g:
                out.setdefault(g.lower(), seg)
    return out


def decimals(v):
    t = repr(float(v))
    return 0 if t.endswith(".0") else len(t.split(".")[1])


def number_scope(raw, ratio, text):
    """The scope of the clauses in text where the effect's own number appears, as a percent or as a ratio, matched at
    the lane value's precision (a lane 46 matches a text 46.3%, a lane 11.1 does not match 10.8%); None when it does
    not appear or its clauses disagree."""
    r = 1 - raw if ratio else raw / 100
    if abs(r) < 0.005:
        return None
    d = max(0, decimals(raw) - 2) if ratio else decimals(raw)
    want = round(abs(r) * 100, d)
    found = set()
    for m in NUMTOK.finditer(text or ""):
        n = float(m.group(1))
        p = n if m.group(2) else ((1 - n) * 100 if "." in m.group(1) and n < 3 else None)
        if p is None or abs(round(abs(p), d) - want) > 1e-9:
            continue
        start = max(text.rfind(c, 0, m.start()) for c in (";", ":", ",", ". ", ")"))
        sc = classify(text[start + 1:m.start()])
        if sc:
            found.add(sc)
    return found.pop() if len(found) == 1 else None


def value_scope(cid, q, raw, ratio, e):
    """'all' or 'ksi' for one of an effect's values (q its low, mid or high field, raw its value, ratio whether it is a
    ratio rather than a percent). The record's measure is the unit without its labelled parentheses, else its
    applies_to; when that measure is killed or seriously injured only, so is every value. Otherwise a value is KSI only
    when SEVERITY_BY_VALUE says so, or the unit's or applies_to's segment labelled with q ("Mid: London KSI -12%",
    "(high: killed)") reads so by the clause holding the value's number or as a whole, or the clause holding the
    value's number anywhere in applies_to, unit or source reads so."""
    r = 1 - raw if ratio else None
    for r0_, sc, _why in SEVERITY_BY_VALUE.get(cid, []):
        if r is not None and abs(abs(r) - r0_) < 0.0005:
            return sc
    unit, app, src = e.get("unit") or "", e.get("applies_to") or "", e.get("source") or ""
    base = classify(LABELLED_PAREN.sub(" ", unit)) or classify(app) or "all"
    if base == "ksi":
        return "ksi"
    seg = segments(unit).get(q) or segments(app).get(q)
    spec = None
    if seg is not None:
        spec = number_scope(raw, ratio, seg) or classify(seg)
    if spec is None:
        spec = number_scope(raw, ratio, app + " ; " + unit + " ; " + src)
    return spec or base


def ratio_unit(u):
    u = u.strip().lower()
    return u in ("cmf", "odds ratio", "rate ratio", "fatality risk") or u.startswith("rr")


def normalise_effect(e, group_mode, cid=None):
    """Return (effect, None) or (None, reason). effect has low, mid and high as fractions removed (every value, for
    KSI people), hurt (the values for people hurt, or None when every value is KSI only), scopes (each of low, mid
    and high: all or ksi) and scope (all, mixed or ksi)."""
    unit = (e.get("unit") or "").strip()
    vals = [e.get(k) for k in ("low", "mid", "high")]
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None, "no effect size"
    if not unit:
        return None, "effect has no unit"
    if NOT_A_REDUCTION.search(unit):
        return None, "effect is not a crash or injury reduction (%s)" % unit[:80]
    if NON_CRASH.search(unit) and not re.search(r"injur|crash|casualt", unit, re.I):
        return None, "effect is not a crash or injury outcome (%s)" % unit[:80]
    if not CRASH_WORDS.search(unit) and not unit.startswith("%"):
        return None, "effect unit does not name a crash outcome (%s)" % unit[:80]
    d = DO_NOT_APPLY.search(e.get("applies_to") or "")
    if d:
        return None, "the effect's own applies_to says it is not one to use here ('%s')" % d.group(0)
    if ratio_unit(unit):
        conv = [None if v is None else 1 - v for v in vals]
    elif "fewer" in unit.lower():
        conv = [None if v is None else v / 100 for v in vals]
    elif "%" in unit or unit.lower().startswith("% "):
        conv = [None if v is None else -v / 100 for v in vals]
    else:
        return None, "effect unit not recognised (%s)" % unit[:80]
    sc_raw = [None if v is None else value_scope(cid, q, v, ratio_unit(unit), e) for q, v in zip(("low", "mid", "high"), vals)]
    present = [(v, s) for v, s in zip(conv, sc_raw) if v is not None]
    if conv[1] is None:
        mid = sum(v for v, _ in present) / len(present)
        mid_s = "all" if all(s == "all" for _, s in present) else "ksi"
    else:
        mid, mid_s = conv[1], sc_raw[1]
    vs = present + [(mid, mid_s)]
    lo, hi = min(v for v, _ in vs), max(v for v, _ in vs)
    if lo < -5 or hi > 1.0001:
        return None, "effect outside a plausible range after normalising (%s)" % unit[:60]
    k = {"low": lo, "mid": mid, "high": hi}
    sc = {"low": "all" if any(s == "all" for v, s in vs if v == lo) else "ksi", "mid": mid_s,
          "high": "all" if any(s == "all" for v, s in vs if v == hi) else "ksi"}
    all_vals = sorted(v for v, s in vs if s == "all")
    hurt = None if not all_vals else {
        q: k[q] if sc[q] == "all" else max([a for a in all_vals if a <= k[q] + 1e-12] or [all_vals[0]]) for q in k}
    u = unit.lower()
    names_ped = re.search(r"pedestrian", u)
    names_bike = re.search(r"cyclist|bicycl|bike", u)
    if names_ped and not names_bike and group_mode not in ("pedestrian involved", "pedestrian", "who"):
        if group_mode in ("vehicles only", "bicycle involved"):
            return None, "effect is for pedestrians, group is %s" % group_mode
    if names_bike and not names_ped and group_mode in ("vehicles only", "pedestrian involved"):
        if not re.search(r"vehicle-bicycle|vehicle and bicycle|cyclist-car", u):
            return None, "effect is for cyclists, group is %s" % group_mode
    out = {q: round(v, 6) for q, v in k.items()}
    out["hurt"] = None if hurt is None else {q: round(v, 6) for q, v in hurt.items()}
    out["scopes"] = sc
    out["scope"] = "all" if all(s == "all" for s in sc.values()) else ("ksi" if hurt is None else "mixed")
    return out, None


# ---------------------------------------------------------------- target share

DISQUALIFY = re.compile(
    r"not computed|not in results\.json|not split|not known|unknown|not linkable|not measured|is not coded|"
    r"\bonly (?:on|at|in|inside|where|blocks|treated|camera|crashes|the part|miles|approaches|the zone)\b|"
    r"\bonly\b[^.;]{0,30}\b(?:blocks|streets|corridors?|sites|corners|zone|cells)\b", re.I)
WHOLE = re.compile(r"whole group|all in reach|every crash in the group|the whole family|group in reach|\ball\s+" + NUM + r"\s+people hurt", re.I)


def parse_share(text, tot_h, tot_k, movement, movements, lane=None):
    """Return (share_hurt, share_ksi, basis) or (None, None, reason).

    An explicit "N% of the group" wins. Text that says the reachable share is
    not computed, unknown, or limited to some blocks, corridors or sites leaves
    the pair not computable, because the street-class or movement counts beside
    such a caveat overstate the reach. lane is the group's (people hurt, KSI
    people) in LANE_YEARS, the counts the text quotes; a total matches either
    those or the current window's."""
    t = text or ""
    lh, lk = lane if lane else (None, None)

    def is_h(b):
        return any(x and abs(b - x) < 0.5 for x in (lh, tot_h))

    def is_k(b):
        return any(x is not None and x and abs(b - x) < 0.5 for x in (lk, tot_k))
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s+of\s+(?:the|each|every)\s+group", t)
    if m:
        s = float(m.group(1)) / 100
        return s, s, "stated %s%% of the group" % m.group(1)
    d = DISQUALIFY.search(t)
    if d:
        return None, None, "text says the reachable share is not computed or narrower than the counts given ('%s')" % d.group(0)
    sh = sk = None
    for a, b in re.findall(NUM + r"\s+of\s+(?:the\s+)?" + NUM, t):
        a, b = num(a), num(b)
        if sh is None and is_h(b) and a <= b:
            sh = a / b
        elif sk is None and is_k(b) and a <= b:
            sk = a / b
    if sh is not None:
        if sk is None:
            m2 = re.search(r"\(\s*" + NUM + r"\s+(?:of\s+" + NUM + r"\s+)?KSI", t)
            base_k = lk if lk else tot_k
            if m2 and base_k and num(m2.group(1)) <= base_k:
                sk = num(m2.group(1)) / base_k
        if sk is None:
            return sh, sh, "people-hurt share from text; KSI share taken equal"
        return sh, sk, "shares from text"
    if WHOLE.search(t):
        return 1.0, 1.0, "text says the whole group is in reach"
    if not re.search(r"group total", t, re.I):
        m3 = re.match(r"\s*" + NUM + r"\s*(?:people hurt)?\s*[,/(]\s*" + NUM + r"\s*(?:KSI)?", t)
        if m3 and any(x and abs(num(m3.group(1)) - x) < 0.5 and y is not None and abs(num(m3.group(2)) - y) < 0.5
                      for x, y in ((lh, lk), (tot_h, tot_k))):
            return 1.0, 1.0, "text gives the whole group's counts as the reach"
    if movement and movement in movements:
        mh, mk = movements[movement]
        if tot_h:
            return mh / tot_h, (mk / tot_k if tot_k else mh / tot_h), "movement share from size_families"
    return None, None, "target share not parseable from text"


# Reasons that drop a row because its unit is not a crash count: the rows a side effect may be left beside.
NON_CRASH_UNIT = ("effect is not a crash or injury reduction", "effect is not a crash or injury outcome",
                  "effect unit does not name a crash outcome", "the effect's own applies_to says")


def side_effect_only(pairs):
    """The reason a fix is not computable when every row with a crash effect is harmful and at least one row was
    dropped for a non-crash unit (the benefit its studies measured some other way), else None."""
    kept = [r for r in pairs if r["computable"]]
    dropped = [r for r in pairs if not r["computable"] and (r.get("reason") or "").startswith(NON_CRASH_UNIT)]
    if not kept or not dropped or any(r["effect_fraction"]["mid"] >= 0 for r in kept):
        return None
    if any("per trip" in ((r.get("effect") or {}).get("unit") or "") for r in dropped):
        return "side effect only: per trip: its studies measure injury risk per trip, not crashes"
    return "side effect only: its studies measure the benefit in something other than crashes"


# ---------------------------------------------------------------- crash by crash

RHO_MAX = 1.0  # one entry removes at most all the people in a crash it reaches; a harmful entry (rho < 0) has no floor
TEXT_FIT = 0.15           # a text share fits a set of crashes holding at least share / (1 + TEXT_FIT) of the family
# A lane's target_share text that names a kind of crash a crash field records: (start of the text, the crash-type tag
# fix-reach.py puts on those crashes, the movements it names).
SUBSET_TEXT = [
    (r"driver at fault turning left", "driver_at_fault", ["left or U-turn"]),
    (r"driver at fault turning", "driver_at_fault", ["left or U-turn", "right turn"]),
    (r"driver at fault", "driver_at_fault", None),
    (r"bicyclist at fault", "bicyclist_at_fault", None),
    (r"pedestrian at fault", "pedestrian_at_fault", None),
    (r"sideswipes?\b", "sideswipe", None),
    (r"broadside", "broadside", None),
    (r"rear[- ]ends?\b", "rear_end", None),
    (r"head[- ]on", "head_on", None),
    (r"solo\b", "solo", None),
    (r"left-turn share", None, ["left or U-turn"]),
    (r"going-straight share", None, ["going straight"]),
]
PLACED = "the places the fix goes (reach.json)"


def rho_clamp(x):
    return min(RHO_MAX, x)


class Crashes(object):
    """Every crash in the window with its family, movement, place tags, KSI people and other people hurt, from
    fix-reach.py's compute(), the records the reach shares are counted with. A fix's people avoided are counted on
    these crashes: each crash keeps the fraction of its KSI people and of its other people hurt that the fixes
    before have left."""

    def __init__(self):
        spec = importlib.util.spec_from_file_location("fix_reach", os.path.join(os.path.dirname(__file__), "fix-reach.py"))
        fr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fr)
        self.fr = fr
        _out, recs, _ = fr.compute()
        self.case, self.fam, self.mv, self.tags, self.k, self.o = [], [], [], [], [], []
        self.by_fam = collections.defaultdict(list)
        for r in recs:
            i = len(self.case)
            name = "%s | %s" % (r["mode"], r["violation"])
            self.case.append(r["case"])
            self.fam.append(name)
            self.mv.append(r["movement"])
            self.tags.append(r["tags"])
            self.k.append(r["ksi"])
            self.o.append(r["hurt"] - r["ksi"])
            self.by_fam[name].append(i)
        self.n = len(self.case)
        self._fam_tot = {g: (sum(self.k[i] + self.o[i] for i in ix), sum(self.k[i] for i in ix)) for g, ix in self.by_fam.items()}

    def totals(self, gname):
        return self._fam_tot.get(gname, (0, 0))

    def reached(self, gname, place, mvs):
        ev = self.fr.evaluate
        return [i for i in self.by_fam.get(gname, ()) if (not mvs or self.mv[i] in mvs) and (not place or ev(place, self.tags[i]))]

    def frac(self, gname, idx):
        H, K = self.totals(gname)
        return (sum(self.k[i] + self.o[i] for i in idx) / H if H else 0.0,
                sum(self.k[i] for i in idx) / K if K else 0.0)

    def rho(self, gname, t):
        """What a term removes on each crash it reaches: rho = share x r / f, where f is the fraction of the family's
        people (people hurt for the other-hurt pool, KSI people for the KSI pool) those crashes hold, so a placed fix
        removes r there and a text share is spread over the crashes it names. KSI people take every value of the effect
        and the others only its all-injury values (effect.hurt), so a KSI-only effect removes KSI people alone. When
        the crashes reached hold no KSI people, the term's KSI share is spread over the family's crashes with KSI
        people in its movements (all of them, if none). rho is at most RHO_MAX, with no floor."""
        idx = self.reached(gname, t["place"], t["movements"])
        fh, fk = self.frac(gname, idx)
        eff = t["effect"]
        kidx, fallback = idx, False
        if not fk and t["share_ksi"] and any(eff[q] for q in Q):
            kidx = [i for i in self.by_fam[gname] if self.k[i] and (not t["movements"] or self.mv[i] in t["movements"])] \
                or [i for i in self.by_fam[gname] if self.k[i]]
            fk, fallback = self.frac(gname, kidx)[1], True
        raw_o = {q: t["share_hurt"] * eff["hurt"][q] / fh if eff["hurt"] and fh else 0.0 for q in Q}
        raw_k = {q: t["share_ksi"] * eff[q] / fk if fk else 0.0 for q in Q}
        return {"rho_other": {q: round(rho_clamp(v), 9) for q, v in raw_o.items()},
                "rho_ksi": {q: round(rho_clamp(v), 9) for q, v in raw_k.items()},
                "rho_clamped": any(rho_clamp(v) != v for v in list(raw_o.values()) + list(raw_k.values())),
                "ksi_fallback": fallback, "crashes_reached": len(idx),
                "_idx": idx, "_kidx": kidx}

    def factors(self, term_sets):
        """{q: (crash indexes, KSI factor, other factor)}: on each crash the fix reaches, the fraction of its KSI people
        and of its other people hurt it leaves, the product over its terms of (1 - rho), at least 0."""
        out = {}
        for q in Q:
            fk, fo = {}, {}
            for ts in term_sets.values():
                for t in ts:
                    for i in t["_idx"]:
                        fo[i] = fo.get(i, 1.0) * (1 - t["rho_other"][q])
                    for i in t["_kidx"]:
                        fk[i] = fk.get(i, 1.0) * (1 - t["rho_ksi"][q])
            ix = sorted(set(fk) | set(fo))
            out[q] = (ix, [max(0.0, fk.get(i, 1.0)) for i in ix], [max(0.0, fo.get(i, 1.0)) for i in ix])
        return out

    def avoided(self, fac):
        """(people hurt, KSI people) avoided a year by one fix alone: KSI people avoided plus other people hurt avoided."""
        ix, fk, fo = fac
        dk = sum(self.k[i] * (1 - a) for i, a in zip(ix, fk))
        do = sum(self.o[i] * (1 - b) for i, b in zip(ix, fo))
        return (dk + do) / YEARS, dk / YEARS


def text_reach(crashes, gname, text, entry_mvs, share, known):
    """(place expression, movements, how) for an entry whose share comes from its target_share text: the crashes the
    text names where a crash field records them (SUBSET_TEXT, the street classes of a "residential ... + collector ...
    = A of B" text, a movement the text opens with, "in the dark"), within the entry's movement when they hold the
    share there; else the entry's movement; else the whole family. A set is used only if it holds at least the share
    (within TEXT_FIT), so the share is spread over crashes that can carry it."""
    low = (text or "").strip().lower()
    tag, tmvs = None, None
    for pat, tg, mv in SUBSET_TEXT:
        if re.match(r"\W*" + pat, low):
            tag, tmvs = tg, mv
            break
    if tag is None and tmvs is None:
        m = re.match(r"\s*((?:residential|collector|arterial)\b.*?)=\s*[\d,]+\s+of\b", low)
        if m:
            cls = sorted(set(re.findall(r"(?:^|\+)\s*(arterial|collector|residential)\b", m.group(1))))
            tag = "|".join(cls) or None
    if tag is None and tmvs is None:
        tmvs = next(([mv] for mv in sorted(known, key=lambda x: (-len(x), x)) if low.startswith(mv.lower())), None)
    if tag is None and re.search(r"\bin the dark\b", low):
        tag = "dark"
    cands = []
    if tag:
        cands.append((tag, tmvs or entry_mvs, "the crashes the text names"))
        if tmvs is None and entry_mvs:
            cands.append((tag, None, "the crashes the text names"))
    if tmvs or entry_mvs:
        cands.append((None, tmvs or entry_mvs, "the movement the entry names"))
    cands.append((None, None, "the whole family"))
    for place, mvs, how in cands:
        fh = crashes.frac(gname, crashes.reached(gname, place, mvs))[0]
        if how == "the whole family" or fh * (1 + TEXT_FIT) >= share:
            return place, mvs, how


# ---------------------------------------------------------------- cost

def first_clause(u):
    return re.split(r"[;(]", u or "", maxsplit=1)[0].strip().lower()


def annual_cost(rec):
    """Return ({low, mid, high, basis}, None) or (None, reason)."""
    c = rec.get("cost") or {}
    lo, hi = c.get("low"), c.get("high")
    if lo is None and hi is None:
        return None, "no cost"
    one_bound = lo is None or hi is None
    lo = hi if lo is None else lo
    hi = lo if hi is None else hi
    unit = c.get("unit") or ""
    fc = first_clause(unit)
    life = rec.get("life_years")
    note = []
    if one_bound:
        note.append("one cost bound only")
    if lo == 0 and hi == 0:
        return {"low": 0.0, "mid": 0.0, "high": 0.0, "basis": "public cost about 0 (%s)" % fc[:80], "public_cost_zero": True}, None
    rid = rec["id"]
    annual = bool(re.search(r"\b(a|per) year\b|annual", fc))
    per_unit = bool(re.search(r"\bper (?!year\b)\w+", fc)) and not re.search(r"^per year", fc)
    mult_lo = mult_hi = 1
    if rid in COST_TOTAL_OVER_YEARS:
        n = COST_TOTAL_OVER_YEARS[rid]
        return {"low": lo / n, "mid": (lo + hi) / 2 / n, "high": hi / n,
                "basis": "program total over %d years (%s)" % (n, fc[:60])}, None
    if per_unit:
        if rid not in UNITS:
            return None, "per-unit cost (%s) and the record gives no SF unit count to reach the target share" % fc[:70]
        mult_lo, mult_hi, ub = UNITS[rid]
        note.append("units: " + ub)
    if annual:
        a_lo, a_hi = lo * mult_lo, hi * mult_hi
        note.insert(0, "per-year cost")
    else:
        if not life:
            return None, "one-time cost (%s) with no life_years" % fc[:70]
        a_lo, a_hi = lo * mult_lo / life, hi * mult_hi / life
        note.insert(0, "one-time cost over %s years" % life)
    return {"low": a_lo, "mid": (a_lo + a_hi) / 2, "high": a_hi, "basis": "; ".join(note)}, None


# ---------------------------------------------------------------- scope

AREA_IDS = {
    "ltn-cell-program-citywide", "street-hierarchy-through-network", "circulation-plan-sectors",
    "superblock-and-car-free-centre-program", "citywide-default-20mph", "neighbourhood-signed-20mph-zones",
    "area-wide-engineered-20mph-zones", "citywide-speed-camera-network", "rotating-mobile-camera-coverage",
    "school-streets-citywide-program", "citywide-daylighting-every-corner", "slow-streets-network",
    "citywide-signal-retiming-safe-speed", "area-cordon-congestion-charge", "community-area-safety-plans",
    "camera-enforced-filters-state-law", "lift-camera-cap", "connected-network-plan",
}
SPOT_LEVERS = {"street design", "signals"}


SCOPE_OVERRIDE = {}  # from reach.json "scope", for street-by-street fixes whose lever is not street design or signals


def scope_of(rec):
    if rec["id"] in SCOPE_OVERRIDE:
        return SCOPE_OVERRIDE[rec["id"]]
    if rec["id"] in AREA_IDS or any(m.startswith("area:") for m in rec.get("merged_from", [])):
        return "area-wide"
    if rec.get("lever") in SPOT_LEVERS or rec["id"] in ("fixed-speed-cameras", "red-light-cameras",
                                                       "stop-and-turn-cameras", "failure-to-yield-cameras",
                                                       "section-control-corridor-cameras", "bike-lane-parking-cameras"):
        return "corner or corridor"
    return "citywide policy, fleet or program"


# ---------------------------------------------------------------- main

def r0(x, n=2):
    return None if x is None else round(x, n)


def group_counts(res):
    """{group name: [people hurt, KSI people]} for every family, the chart's "all other families" row and every
    cross-cut bar in grouping_alternatives, keyed as group_totals() matches them."""
    out = {}
    for f in res["size_families"]["families"]:
        out["%s | %s" % (f["mode"], f["violation"])] = [f["people_injured"], f["ksi_people"]]
    other = next(c for c in res["size_families"]["chart"] if c["mode"] == "all other families")
    out["all other families"] = [other["people_injured"], other["ksi_people"]]
    for g in res["grouping_alternatives"]["groupings"]:
        for b in g["top_bars"]:
            out.setdefault(" | ".join(b["group"]), [b["people_injured"], b["ksi_people"]])
    return dict(sorted(out.items()))


def freeze_lane_counts(path):
    """Write LANE_COUNTS from a results.json counted over LANE_YEARS, the counts the lanes' texts quote."""
    res = load(path)
    if res["years"] != LANE_YEARS:
        raise SystemExit("--freeze-lane-counts needs a results.json for %s, got %s" % (LANE_YEARS, res["years"]))
    out = {"about": "People hurt and KSI people by group, %d to %d, the counts the lanes' target_share texts quote. "
                    "Written once by fix-map.py --freeze-lane-counts from crash-profiles.py --years %d %d; fix-map.py "
                    "reads an 'A of B' text whose B is one of these totals as the share A / B." % tuple(LANE_YEARS * 2),
           "years": LANE_YEARS, "inputs_read_on": res.get("inputs_read_on"), "groups": group_counts(res)}
    with open(LANE_COUNTS, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print("wrote %s (%d groups)" % (os.path.relpath(LANE_COUNTS, ROOT), len(out["groups"])), file=sys.stderr)


def main():
    global YEARS
    if sys.argv[1:2] == ["--freeze-lane-counts"]:
        return freeze_lane_counts(sys.argv[2])
    res = load(RESULTS)
    YEARS = res["years"][1] - res["years"][0] + 1
    lane_counts = load(LANE_COUNTS)
    if lane_counts["years"] != LANE_YEARS:
        raise SystemExit("%s is for %s, not %s" % (LANE_COUNTS, lane_counts["years"], LANE_YEARS))
    lane_counts = lane_counts["groups"]
    fams = res["size_families"]["families"]
    fam = {}
    for f in fams:
        name = "%s | %s" % (f["mode"], f["violation"])
        fam[name] = {
            "people_hurt": f["people_injured"], "ksi": f["ksi_people"], "mode": f["mode"],
            "movements": {m["movement"]: (m["people_injured"], m["ksi_people"]) for m in f.get("by_movement", [])},
        }
    chart_names = {"%s | %s" % (c["mode"], c["violation"]) for c in res["size_families"]["chart"] if c["mode"] != "all other families"}
    remainder = sorted(n for n in fam if n not in chart_names)
    other_row = next(c for c in res["size_families"]["chart"] if c["mode"] == "all other families")
    tot_h, tot_k = res["totals"]["people_injured"], res["totals"]["ksi_people"]
    stress = {}
    for row in res["family_stress"].get("families", []) if isinstance(res["family_stress"].get("families"), list) else []:
        stress["%s | %s" % (row.get("mode"), row.get("violation"))] = row
    cross_totals = {}
    for g in res["grouping_alternatives"]["groupings"]:
        for b in g["top_bars"]:
            key = " | ".join(b["group"])
            cross_totals[key] = (b["people_injured"], b["ksi_people"])

    lanes = read_lanes()
    fill = lanes.pop("fill", {"fixes": [], "gaps": []})
    records = {}
    for ln in sorted(lanes):
        for x in lanes[ln].get("fixes", []):
            records[(ln, x["id"])] = json.loads(json.dumps(x))
    fill_log = apply_fill(records, fill)
    merged = merge(records)
    critique = load(os.path.join(LANES, "critique.json"))

    family_names = set(fam)
    reach = Reach(fam, remainder)
    crashes = Crashes()
    for g in fam:
        if crashes.totals(g) != (fam[g]["people_hurt"], fam[g]["ksi"]):
            raise SystemExit("fix-map: %s holds %s in fix-reach.py's crashes and %s in results.json"
                             % (g, crashes.totals(g), (fam[g]["people_hurt"], fam[g]["ksi"])))
    if sum(crashes.totals(g)[0] for g in fam) != tot_h or sum(crashes.totals(g)[1] for g in fam) != tot_k:
        raise SystemExit("fix-map: the families do not add to everyone hurt")
    spread_log = []
    reach_log = {}
    for cid in sorted(reach.cfg):
        if cid not in merged:
            reach_log[cid] = {"error": "fix id not in the lanes"}
            continue
        c = reach.cfg[cid]
        entry = {"place": c["place"], "why": c.get("why")}
        if c.get("scope"):
            SCOPE_OVERRIDE[cid] = c["scope"]
            entry["scope"] = c["scope"]
        u = reach.units(cid)
        if u is not None:
            UNITS[cid] = u
            entry["units"] = u[2]
        elif c.get("units"):
            entry["units_error"] = "unit %r not in fix-reach.json" % c["units"]
        elif cid in UNITS and reach.left(cid) != 1.0:
            lo_, hi_, nb = UNITS[cid]
            UNITS[cid] = (lo_ * reach.left(cid), hi_ * reach.left(cid), nb + " x %s not yet treated" % round(reach.left(cid), 4))
            entry["units"] = UNITS[cid][2]
        if c.get("cost"):
            entry["cost_replaced"] = {"lane": merged[cid].get("cost"), "why": "the lane priced timing labour only"}
            merged[cid]["cost"] = dict(c["cost"])
        if c.get("reach_confidence"):
            entry["reach_confidence"] = c["reach_confidence"]
        entry["treated"] = reach.net_note(cid)
        if merged[cid].get("life_years") in (None, "") and c.get("life_years"):
            merged[cid]["life_years"] = c["life_years"]
            entry["life_years"] = "%s (%s)" % (c["life_years"], c.get("life_basis", ""))
        PARTIAL_UNITS.discard(cid)
        reach_log[cid] = entry
    validation = {}
    for cid in sorted(merged):
        errs = validate(merged[cid], family_names)
        if errs:
            validation[cid] = errs

    def group_totals(name, text):
        """(people hurt, KSI people, mode, movements, kind, the LANE_YEARS counts or None)."""
        if name in fam:
            return (fam[name]["people_hurt"], fam[name]["ksi"], fam[name]["mode"], fam[name]["movements"], "family",
                    lane_counts.get(name))
        if name == "all other families":
            return other_row["people_injured"], other_row["ksi_people"], "all", {}, "remainder", lane_counts.get(name)
        for key, (h, k) in cross_totals.items():
            if name.endswith(key) or key in name:
                mode = "pedestrian" if "pedestrian" in name else ("who" if name.startswith("who") else "cross")
                return h, k, mode, {}, "cross-cut", lane_counts.get(key)
        m = re.search(NUM + r"\s+(?:people\s+)?hurt\s*/\s*" + NUM + r"\s+KSI", text or "")
        if m:
            mode = "pedestrian" if "pedestrian" in name else "cross"
            return num(m.group(1)), num(m.group(2)), mode, {}, "cross-cut (count from target_share text)", None
        return None, None, None, {}, "cross-cut, no count found", None

    out_fixes, not_computable, pair_rows = [], [], {}
    for cid in sorted(merged):
        rec = merged[cid]
        cost, cost_reason = annual_cost(rec)
        if cid in reach.cfg:
            up = reach.upkeep(cid)
            if cost is not None and up is not None:
                cost = {"low": cost["low"] + up[0], "mid": cost["mid"] + (up[0] + up[1]) / 2, "high": cost["high"] + up[1],
                        "basis": cost["basis"] + "; plus " + up[2]}
        pairs = []
        chosen = {}
        last_share = {}
        for g in rec.get("groups") or []:
            name = g.get("group") or ""
            if "status" in g and "remove" in str(g["status"]).lower():
                continue
            h, k, mode, movements, kind, lane = group_totals(name, g.get("target_share"))
            e = g.get("effect") or {}
            borrowed = EFFECT_FROM_GROUP.get((cid, name))
            if borrowed:
                src_g = next((x for x in rec.get("groups") or [] if x.get("group") == borrowed[0] and x.get("effect")), None)
                if src_g is None:
                    raise SystemExit("EFFECT_FROM_GROUP: %s has no group %r" % (cid, borrowed[0]))
                e = dict(src_g["effect"])
            eff, ereason = normalise_effect(e, mode if mode != "all" else None, cid)
            sh = sk = None
            sbasis = None
            ts = str(g.get("target_share") or "")
            reach_row = None
            if h is not None and cid in reach.cfg and kind in ("family", "remainder"):
                tsh = None
                if reach.text_mode(cid, name) == "multiply":
                    a, b, _ = parse_share(ts, h, k, g.get("movement"), movements, lane)
                    tsh = (a, b) if a is not None else None
                sh, sk, sbasis = reach.share(cid, name, g.get("movement"), tsh)
                reach_row = {"place": reach.place_of(cid, name), "text_share": tsh}
                last_share[(name, g.get("movement") or "")] = (sh, sk, sbasis)
            elif h is not None:
                if re.match(r"\s*same (reach|basis)", ts, re.I) and (name, g.get("movement") or "") in last_share:
                    sh, sk, sbasis = last_share[(name, g.get("movement") or "")]
                    sbasis = "same reach as the entry before: " + str(sbasis)
                else:
                    sh, sk, sbasis = parse_share(ts, h, k, g.get("movement"), movements, lane)
                last_share[(name, g.get("movement") or "")] = (sh, sk, sbasis)
            reason = None
            if sh is not None and cid in REACH_UNKNOWN:
                sh = sk = None
                sbasis = REACH_UNKNOWN[cid]
            elif sh is not None and cid in PARTIAL_UNITS and not str(sbasis).startswith("stated"):
                sh = sk = None
                sbasis = "the SF unit count covers only part of the reach the text describes (%s)" % UNITS[cid][2]
            sf_note = None
            if eff is not None and cid in SF_EVIDENCE:
                ev = next((x for x in SF_EVIDENCE[cid] if x["modes"] is None or mode in x["modes"]), None)
                if ev is not None:
                    lowest = sf_low(ev)
                    sf_note = {"sf_result": ev["what"], "sf_low": round(lowest, 4), "lane_low": eff["low"], "source": _SF_SRC}
                    hurt_hopeful = bool(eff["hurt"]) and eff["hurt"]["low"] > lowest + 1e-9
                    if eff["low"] > lowest + 1e-9 or hurt_hopeful:
                        eff = dict(eff, low=round(min(eff["low"], lowest), 6))
                        if hurt_hopeful:
                            eff["hurt"] = dict(eff["hurt"], low=round(lowest, 6))
                        sf_note["applied"] = "low set to SF's result (lane low was more hopeful)"
                    else:
                        sf_note["applied"] = "no change: the lane's low is already at or below SF's result"
            if h is None:
                reason = "group has no SF count"
            elif eff is None:
                reason = ereason
            elif sh is None:
                reason = sbasis
            row = {
                "_i": len(pairs),
                "group": name, "movement": g.get("movement"), "kind": kind, "from": g.get("from"),
                "mechanism": g.get("mechanism"), "target_share_text": g.get("target_share"),
                "effect": e, "group_people_hurt": h, "group_ksi": k,
            }
            if reach_row:
                row["reach_place"] = reach_row["place"]
                row["_text_share"] = reach_row["text_share"]
            if sf_note:
                row["sf_evidence"] = sf_note
            if borrowed:
                row["effect_from"] = {"group": borrowed[0], "why": borrowed[1]}
            if reason:
                row["computable"] = False
                row["reason"] = reason
            else:
                if reach_row:
                    row["_set"] = reach.reach_set(cid, name, g.get("movement"))
                else:
                    row["_set"] = None  # a text share: text_reach() picks the crashes per family
                hy, ky = h / YEARS, k / YEARS
                rh = eff["hurt"]
                ak = {q: ky * sk * eff[q] for q in Q}
                ah = {q: (hy - ky) * sh * rh[q] + ak[q] if rh else ak[q] for q in Q}
                row.update({
                    "computable": True, "share_hurt": r0(sh, 4), "share_ksi": r0(sk, 4), "share_basis": sbasis,
                    "effect_fraction": eff, "effect_scope": eff["scope"],
                    "hurt_avoided_per_year": {q: r0(v) for q, v in ah.items()},
                    "ksi_avoided_per_year": {q: r0(v, 3) for q, v in ak.items()},
                })
                if eff["scope"] == "ksi":
                    row["note"] = ("effect measured on killed or seriously injured only: it removes KSI people, who are "
                                   "counted as people hurt avoided too, and no one else")
                elif eff["scope"] == "mixed":
                    row["note"] = ("some of the effect's values are on killed or seriously injured only: those apply to "
                                   "KSI people, and people hurt take the nearest smaller all-injury value (effect_fraction.hurt)")
                gk = (name, g.get("movement") or "")
                # one entry per group and movement: the first computable in lane order
                if gk not in chosen:
                    chosen[gk] = row
                    row["used"] = True
                else:
                    row["used"] = False
                    row["note"] = (row.get("note", "") + "; " if row.get("note") else "") + "alternate estimate; the first computable entry for this group is used"
            pairs.append(row)
        # A fix whose benefit rows were all dropped as non-crash units, leaving only a harmful side effect, is not
        # computable: its count would be the side effect alone.
        side = side_effect_only(pairs)
        if side:
            for row in pairs:
                if row["computable"]:
                    row["computable"], row["used"], row["reason"] = False, False, side
            chosen = {}
        # A fix that maps one group several times with different movements: those add.
        # A group mapped both without movement and with movements: keep the no-movement entry only.
        by_group = {}
        for (gname, mv), row in chosen.items():
            by_group.setdefault(gname, {})[mv] = row
        use = {}
        for gname, mvs in by_group.items():
            if "" in mvs and len(mvs) > 1:
                for mv, row in mvs.items():
                    if mv:
                        row["used"] = False
                        row["note"] = (row.get("note", "") + "; " if row.get("note") else "") + "covered by this fix's whole-group entry"
                use[gname] = [mvs[""]]
            else:
                use[gname] = [mvs[mv] for mv in sorted(mvs)]
        # effects per family for stacking: (share_h*r, share_k*r) per quantile
        fam_effects = {}
        cross_effects = {}
        for gname, rows in use.items():
            for row in rows:
                if row["kind"] == "family":
                    fam_effects.setdefault(gname, []).append(row)
                elif row["kind"] == "remainder":
                    fam_effects.setdefault("__remainder__", []).append(row)
                else:
                    cross_effects.setdefault(gname, []).append(row)
        # expand remainder to member families not mapped directly
        expanded = {}
        for gname, rows in fam_effects.items():
            if gname == "__remainder__":
                for member in remainder:
                    if member not in fam_effects:
                        mrows = []
                        for r in rows:
                            r2 = dict(r, remainder_applied=True)
                            if r.get("reach_place"):
                                a, b, _ = reach.share(cid, member, r["movement"], r.get("_text_share"))
                                r2["share_hurt"], r2["share_ksi"] = r0(a or 0.0, 4), r0(b or 0.0, 4)
                                r2["_set"] = reach.reach_set(cid, member, r["movement"])
                            mrows.append(r2)
                        expanded[member] = mrows
            else:
                expanded[gname] = rows
        # each family term reaches a set of crashes and removes rho of the people in each, crash by crash
        term_sets = {}
        for gname, rows in sorted(expanded.items()):
            sets = []
            for row in rows:
                if row["_set"] is None:
                    try:
                        emv, extra = parse_movements(row["movement"], reach.known)
                    except ValueError:
                        emv, extra = None, None
                    place, mvs, how = text_reach(crashes, gname, row["target_share_text"], None if extra else emv,
                                                 row["share_hurt"], reach.known)
                else:
                    (place, mvs), how = row["_set"], PLACED
                t = {"share_hurt": row["share_hurt"], "share_ksi": row["share_ksi"], "effect": row["effect_fraction"],
                     "place": place, "movements": mvs, "row": row["_i"], "reach": how}
                t.update(crashes.rho(gname, t))
                sets.append(t)
            term_sets[gname] = sets
        factors = crashes.factors(term_sets)
        tot = {q: list(crashes.avoided(factors[q])) for q in Q}
        for gname, sets in term_sets.items():  # each row's own reach, for the text-share report
            for t in sets:
                spread_log.append({"fix": cid, "family": gname, "row": t["row"], "reach": t["reach"],
                                   "text_share": t["reach"] != PLACED and t["share_hurt"] < 0.9999})
        stack_terms = term_sets
        basis = "families"
        if not stack_terms and cross_effects:
            basis = "cross-cut groups only (not stacked)"
            for gname, rows in cross_effects.items():
                for row in rows:
                    for q in tot:
                        if row.get("hurt_avoided_per_year"):
                            tot[q][0] += row["hurt_avoided_per_year"][q]
                        tot[q][1] += row["ksi_avoided_per_year"][q]
        hurt = {q: tot[q][0] for q in tot}
        ksi = {q: tot[q][1] for q in tot}
        any_pair = bool(stack_terms or cross_effects)
        rec_out = {k: rec.get(k) for k in ("id", "name", "lever", "how_it_works", "unit", "cost", "life_years",
                                          "sf_now", "sf_evidence", "who_decides", "evidence_grade", "sources",
                                          "merged_from", "notes", "displacement")}
        rec_out["scope"] = scope_of(rec)
        if cid in reach.cfg:
            rec_out["reach_treated"] = reach.net_note(cid)
            rec_out["reach_confidence"] = reach.cfg[cid].get("reach_confidence", {"level": "as mapped"})
            if reach.cfg[cid].get("cost"):
                rec_out["cost_replaced_by_reach_json"] = True
        rec_out["groups"] = pairs
        rec_out["validation_errors"] = validation.get(cid, [])
        rec_out["avoided_basis"] = basis if any_pair else None
        rec_out["hurt_avoided_per_year"] = {q: r0(v) for q, v in hurt.items()} if any_pair else None
        rec_out["ksi_avoided_per_year"] = {q: r0(v, 3) for q, v in ksi.items()} if any_pair else None
        rec_out["annual_cost"] = None if cost is None else {k: (r0(v, 0) if isinstance(v, float) else v) for k, v in cost.items()}
        reasons = []
        if cid in ENABLERS:
            reasons.append("enabler: its benefit comes from building %s, which carries the cost and is ranked instead" % ENABLERS[cid])
        if side:
            reasons.append(side)
        elif not any_pair:
            reasons.append("no computable fix x group pair")
        if cost is None:
            reasons.append(cost_reason)
        cph = cpk = None
        rec_out_note = None
        if any_pair and cost is not None:
            def per(av, q_cost, q_av):
                a = av[q_av]
                if a is None or a <= 0:
                    return None
                return cost[q_cost] / a
            cph = {"low": per(hurt, "low", "high"), "mid": per(hurt, "mid", "mid"), "high": per(hurt, "high", "low")}
            cpk = {"low": per(ksi, "low", "high"), "mid": per(ksi, "mid", "mid"), "high": per(ksi, "high", "low")}
            if cph["mid"] is None and hurt["mid"] <= 0:
                rec_out_note = "no people hurt avoided at mid (effect zero or harmful); ranked by KSI only"
            else:
                rec_out_note = None
        rec_out["cost_per_person_hurt_avoided"] = None if cph is None else {q: r0(v, 0) for q, v in cph.items()}
        rec_out["cost_per_ksi_avoided"] = None if cpk is None else {q: r0(v, 0) for q, v in cpk.items()}
        if any_pair:
            other_h = {q: max(hurt[q] - ksi[q], 0) for q in hurt}
            v_bla = {q: hurt[q] * BLA_PER_INJURY_2024 for q in hurt}
            v_us = {q: ksi[q] * USDOT_PER_KSI + other_h[q] * USDOT_PER_OTHER_HURT for q in hurt}
            rec_out["value_avoided_per_year"] = {
                "bla_economic_2024": {q: r0(v, 0) for q, v in v_bla.items()},
                "usdot_comprehensive_2024": {q: r0(v, 0) for q, v in v_us.items()},
            }
            if cost is not None and cost["mid"] > 0:
                rec_out["benefit_cost_ratio_mid"] = {
                    "bla_economic": r0(v_bla["mid"] / cost["mid"], 2),
                    "usdot_comprehensive": r0(v_us["mid"] / cost["mid"], 2),
                }
            else:
                rec_out["benefit_cost_ratio_mid"] = None
        rec_out["computable"] = not reasons
        if any_pair and cost is not None and rec_out_note:
            rec_out["note"] = rec_out_note
        rec_out["not_computable_reasons"] = reasons
        rec_out["_factors"] = factors if stack_terms else None
        rec_out["stack_terms"] = {g: [{k: v for k, v in t.items() if not k.startswith("_")} for t in ts]
                                  for g, ts in term_sets.items()} if any_pair else None
        out_fixes.append(rec_out)
        for row in pairs:
            if not row["computable"]:
                not_computable.append({"fix": cid, "group": row["group"], "movement": row["movement"], "reason": row["reason"]})
        if any_pair and cost is None:
            not_computable.append({"fix": cid, "group": "(cost)", "movement": None, "reason": cost_reason})

    # ---------------------------------------------------------------- ranking
    ranked = [f for f in out_fixes if f["computable"] and f["cost_per_person_hurt_avoided"]
              and f["cost_per_person_hurt_avoided"]["mid"] is not None and f["avoided_basis"] == "families"]
    ranked.sort(key=lambda f: (f["cost_per_person_hurt_avoided"]["mid"], -f["hurt_avoided_per_year"]["mid"], f["id"]))
    ranking = [{
        "rank": i + 1, "id": f["id"], "name": f["name"], "lever": f["lever"], "scope": f["scope"],
        "cost_per_person_hurt_avoided_mid": f["cost_per_person_hurt_avoided"]["mid"],
        "cost_per_ksi_avoided_mid": f["cost_per_ksi_avoided"]["mid"] if f["cost_per_ksi_avoided"] else None,
        "hurt_avoided_per_year_mid": f["hurt_avoided_per_year"]["mid"],
        "ksi_avoided_per_year_mid": f["ksi_avoided_per_year"]["mid"],
        "annual_cost_mid": f["annual_cost"]["mid"], "evidence_grade": f.get("evidence_grade"),
        "public_cost_zero": bool(f["annual_cost"].get("public_cost_zero")),
        "reach_confidence": (f.get("reach_confidence") or {}).get("level"),
        "most_it_could_reach": str(f.get("reach_treated", "")).startswith("most it could reach"),
    } for i, f in enumerate(ranked)]
    ksi_ranked = [f for f in out_fixes if f["computable"] and f["cost_per_ksi_avoided"]
                  and f["cost_per_ksi_avoided"]["mid"] is not None and f["avoided_basis"] == "families"]
    ksi_ranked.sort(key=lambda f: (f["cost_per_ksi_avoided"]["mid"], -f["ksi_avoided_per_year"]["mid"], f["id"]))
    ranking_ksi = [{"rank": i + 1, "id": f["id"], "cost_per_ksi_avoided_mid": f["cost_per_ksi_avoided"]["mid"],
                    "ksi_avoided_per_year_mid": f["ksi_avoided_per_year"]["mid"]} for i, f in enumerate(ksi_ranked)]

    # ---------------------------------------------------------------- stacks
    stackable = [f for f in out_fixes if f["computable"] and f["avoided_basis"] == "families"
                 and f["annual_cost"] is not None]
    year_h, year_k = tot_h / YEARS, tot_k / YEARS
    K, O = crashes.k, crashes.o

    def apply(f, q, remk, remo):
        """(people hurt, KSI people) a year the fix avoids on what remK, remO leave, and the new remainders."""
        ix, fk, fo = f["_factors"][q]
        dk = do = 0.0
        nk, no = [], []
        for i, a, b in zip(ix, fk, fo):
            rk, ro = remk[i], remo[i]
            x, y = rk * a, ro * b
            dk += K[i] * (rk - x)
            do += O[i] * (ro - y)
            nk.append(x)
            no.append(y)
        return (dk + do) / YEARS, dk / YEARS, (ix, nk, no)

    def step_row(n, f, c, dh, dk, cum_cost, cum_h, cum_k):
        return {
            "step": n, "id": f["id"], "scope": f["scope"], "annual_cost": r0(c, 0),
            "marginal_hurt_avoided": r0(dh), "marginal_ksi_avoided": r0(dk, 3),
            "marginal_cost_per_person_hurt": r0(c / dh, 0) if dh > 0 else None,
            "marginal_cost_per_ksi": r0(c / dk, 0) if dk > 0 else None,
            "cumulative_annual_cost": r0(cum_cost, 0), "cumulative_hurt_avoided": r0(cum_h),
            "cumulative_ksi_avoided": r0(cum_k, 3),
            "share_of_people_hurt_avoided": r0(cum_h / year_h, 4), "share_of_ksi_avoided": r0(cum_k / year_k, 4),
        }

    def check_remaining(remk, remo, label):
        """Allocation check: no crash has more avoided than it holds (remaining at least 0), and no family has more
        KSI people or other people hurt avoided than it holds. Harm added has no ceiling."""
        by = collections.defaultdict(lambda: [0.0, 0.0])
        for i in range(crashes.n):
            if not (remk[i] >= -1e-12 and remo[i] >= -1e-12):
                raise SystemExit("fix-map: %s leaves crash %s at %s, %s" % (label, crashes.case[i], remk[i], remo[i]))
            by[crashes.fam[i]][0] += K[i] * (1 - remk[i]) + O[i] * (1 - remo[i])
            by[crashes.fam[i]][1] += K[i] * (1 - remk[i])
        for g, (h, k) in by.items():
            fk_, fo_ = fam[g]["ksi"], fam[g]["people_hurt"] - fam[g]["ksi"]
            if not (k <= fk_ + 1e-6 and h - k <= fo_ + 1e-6):
                raise SystemExit("fix-map: %s avoids %.3f hurt and %.3f KSI in %s, which holds %s and %s"
                                 % (label, h, k, g, fam[g]["people_hurt"], fam[g]["ksi"]))

    def build_stack(cands, metric, q="mid", cq=None):
        """Greedy: add the fix with the lowest cost per person avoided on what the fixes before it left, crash by crash."""
        cq = cq or q
        remk, remo = [1.0] * crashes.n, [1.0] * crashes.n
        added, steps = set(), []
        cum_cost = cum_h = cum_k = 0.0
        pool = sorted(cands, key=lambda f: f["id"])
        while True:
            best = None
            for f in pool:
                if f["id"] in added or any((f["id"], a) in CONFLICTS for a in added):
                    continue
                dh, dk, new = apply(f, q, remk, remo)
                gain = dh if metric == "hurt" else dk
                if gain <= 1e-9:
                    continue
                c = f["annual_cost"][cq]
                key = (c / gain, -gain, f["id"])
                if best is None or key < best[0]:
                    best = (key, f, dh, dk, new)
            if best is None:
                break
            _, f, dh, dk, (ix, nk, no) = best
            for i, x, y in zip(ix, nk, no):
                remk[i], remo[i] = x, y
            added.add(f["id"])
            cum_cost += f["annual_cost"][cq]
            cum_h += dh
            cum_k += dk
            steps.append(step_row(len(steps) + 1, f, f["annual_cost"][cq], dh, dk, cum_cost, cum_h, cum_k))
        check_remaining(remk, remo, "a stack")
        skipped = sorted(f["id"] for f in pool if f["id"] not in added)
        return {"steps": steps, "not_added": skipped}

    by_id = {f["id"]: f for f in out_fixes}

    def replay(order, q, cq):
        """The same fixes in the same order with every effect at q and every cost at cq, harmful effects included."""
        remk, remo = [1.0] * crashes.n, [1.0] * crashes.n
        steps, cum_cost, cum_h, cum_k = [], 0.0, 0.0, 0.0
        for fid in order:
            f = by_id[fid]
            dh, dk, (ix, nk, no) = apply(f, q, remk, remo)
            for i, x, y in zip(ix, nk, no):
                remk[i], remo[i] = x, y
            cum_cost += f["annual_cost"][cq]
            cum_h += dh
            cum_k += dk
            steps.append(step_row(len(steps) + 1, f, f["annual_cost"][cq], dh, dk, cum_cost, cum_h, cum_k))
        check_remaining(remk, remo, "a replay")
        return steps

    def add_band(st):
        """Each step's cumulative people avoided with every effect at its low and at its high, same order and costs."""
        order = [x["id"] for x in st["steps"]]
        for qq in ("low", "high"):
            for s_, r_ in zip(st["steps"], replay(order, qq, "mid")):
                for k_ in ("cumulative_hurt_avoided", "cumulative_ksi_avoided", "share_of_people_hurt_avoided",
                           "share_of_ksi_avoided"):
                    s_[k_ + "_" + qq] = r_[k_]

    def at_budget(stack, budget):
        last = None
        for s in stack["steps"]:
            if s["cumulative_annual_cost"] <= budget:
                last = s
            else:
                break
        if last is None:
            return {"budget": budget, "fixes": 0, "annual_cost": 0, "hurt_avoided": 0, "ksi_avoided": 0,
                    "share_of_people_hurt_avoided": 0, "share_of_ksi_avoided": 0}
        return {"budget": budget, "fixes": last["step"], "annual_cost": last["cumulative_annual_cost"],
                "hurt_avoided": last["cumulative_hurt_avoided"], "ksi_avoided": last["cumulative_ksi_avoided"],
                "share_of_people_hurt_avoided": last["share_of_people_hurt_avoided"],
                "share_of_ksi_avoided": last["share_of_ksi_avoided"]}

    def summarise(stack):
        end = stack["steps"][-1] if stack["steps"] else None
        return {"at_budgets": [at_budget(stack, b) for b in BUDGETS],
                "end": None if end is None else {k: end[k] for k in (
                    "step", "cumulative_annual_cost", "cumulative_hurt_avoided", "cumulative_ksi_avoided",
                    "share_of_people_hurt_avoided", "share_of_ksi_avoided")}}

    stacks = {}
    for name, cands, metric in [
        ("greedy_by_people_hurt", stackable, "hurt"),
        ("greedy_by_ksi", stackable, "ksi"),
        ("area_wide_only", [f for f in stackable if f["scope"] == "area-wide"], "hurt"),
        ("corner_and_corridor_only", [f for f in stackable if f["scope"] == "corner or corridor"], "hurt"),
        ("area_wide_and_corner_corridor", [f for f in stackable if f["scope"] in ("area-wide", "corner or corridor")], "hurt"),
    ]:
        st = build_stack(cands, metric)
        add_band(st)
        st.update(summarise(st))
        st["ranked_by"] = "cost per %s avoided on what remains, mid" % ("person hurt" if metric == "hurt" else "KSI person")
        st["candidates"] = len(cands)
        stacks[name] = st
    order = [x["id"] for x in stacks["greedy_by_people_hurt"]["steps"]]
    for label, eq, cq in (("optimistic", "high", "low"), ("pessimistic", "low", "high")):
        st = {"steps": replay(order, eq, cq)}
        sm = summarise(st)
        stacks["greedy_by_people_hurt_" + label] = {
            "end": sm["end"], "at_budgets": sm["at_budgets"], "steps": st["steps"],
            "note": "greedy_by_people_hurt's fixes in its order, every effect at its %s value (harmful ones included) "
                    "and every cost at its %s value" % (eq, cq)}
    stacks["about"] = (
        "Sequential counting (TRL PPR844), crash by crash: each added fix acts only on the people the fixes before it "
        "left in each crash it reaches, so fixes that reach the same crashes, or nested places, are never credited "
        "with more people than those crashes hold. A crash keeps the fraction of its KSI people and of its other "
        "people hurt still there; a fix removes rho of each on every crash it reaches (rho at most %s, so a crash "
        "never drops below none, and a study's rise in crashes is applied in full). The package total sums over the %d mode x family groups, which hold "
        "everyone hurt. It assumes the fixes' effects are independent. Only fixes with an annual cost and at least one "
        "computable family pair are stacked; CONFLICTS keeps one version of a fix, or one of the alternatives at one "
        "place. Each step also carries the cumulative figures with every effect at its low and at its high. Shares are "
        "of %d people hurt and %d KSI people a year (%d-%d over %d). Annual cost mixes dollar years."
        % (RHO_MAX, len(fam), round(year_h), round(year_k), res["years"][0],
           res["years"][1], YEARS))

    # ---------------------------------------------------------------- groups
    fix_by_group = {}
    for f in out_fixes:
        for row in f["groups"]:
            fix_by_group.setdefault(row["group"], []).append({
                "id": f["id"], "movement": row["movement"], "computable": row["computable"],
                "used": row.get("used", False),
                "effect": row["effect"], "effect_fraction": row.get("effect_fraction"),
                "share_hurt": row.get("share_hurt"), "share_ksi": row.get("share_ksi"),
                "hurt_avoided_per_year": row.get("hurt_avoided_per_year"),
                "ksi_avoided_per_year": row.get("ksi_avoided_per_year"),
                "reason": row.get("reason"),
            })
    fs = res["family_stress"]
    stress_rows = {}
    for key in ("families", "by_family", "groups"):
        if isinstance(fs.get(key), list):
            for row in fs[key]:
                stress_rows["%s | %s" % (row.get("mode"), row.get("violation"))] = row
    groups_out = []
    for name in sorted(fam):
        st = stress_rows.get(name)
        groups_out.append({
            "group": name, "people_hurt": fam[name]["people_hurt"], "ksi": fam[name]["ksi"],
            "in_chart": name in chart_names,
            "movement_split": [{"movement": m, "people_hurt": v[0], "ksi": v[1]} for m, v in sorted(fam[name]["movements"].items(), key=lambda kv: (-kv[1][0], kv[0]))],
            "stress_split": None if st is None else {k: st[k] for k in ("by_stress", "by_street_class") if k in st},
            "fixes": sorted(fix_by_group.get(name, []), key=lambda r: (r["id"], r["movement"] or "")),
        })
    cross_out = []
    for name in sorted(n for n in fix_by_group if n not in fam):
        cross_out.append({"group": name, "fixes": sorted(fix_by_group[name], key=lambda r: (r["id"], r["movement"] or ""))})

    # ---------------------------------------------------------------- gaps
    gaps = ["fill: " + g for g in fill.get("gaps", [])]
    for ln in sorted(lanes):
        gaps += ["%s: %s" % (ln, g if isinstance(g, str) else json.dumps(g, sort_keys=True)) for g in lanes[ln].get("gaps", [])]
    corrected = {(x["id"]) for x in fill.get("fixes", []) if x.get("fill_action") == "misfit_corrected"}
    for m in critique.get("misfits", []):
        if ALIASES.get(m["fix"], m["fix"]) not in corrected and m["fix"] not in corrected:
            gaps.append("critique misfit not corrected: %s on %s: %s" % (m["fix"], m["group"], m["issue"]))
    for n in critique.get("no_cost", []):
        cid = ALIASES.get(n["fix"], n["fix"])
        if cid in merged and not cost_known(merged[cid].get("cost")):
            gaps.append("critique no_cost still uncosted: %s (%s)" % (n["fix"], n.get("unit")))
    mapped = {(row["group"]) for f in out_fixes for row in f["groups"]}
    for m in critique.get("missing", []):
        if m["group"] not in mapped:
            gaps.append("critique missing, group still has no fix: %s: %s" % (m["group"], m["fix"]))

    for f in out_fixes:
        f.pop("_factors", None)
        for row in f["groups"]:
            row.pop("_text_share", None)
            row.pop("_set", None)
            row.pop("_i", None)
    reasons_count = {}
    for n in not_computable:
        key = re.sub(r"\(.*", "", n["reason"]).strip()
        reasons_count[key] = reasons_count.get(key, 0) + 1
    n_pairs = sum(len(f["groups"]) for f in out_fixes)
    out = {
        "about": __doc__.split("\n")[0],
        "inputs": {
            "lanes": sorted(lanes) + ["fill"], "results": "out/crash-augment/profiles/results.json",
            "years": res["years"], "people_hurt_total": tot_h, "ksi_total": tot_k,
            "value_sources": [BLA_SOURCE, USDOT_SOURCE],
            "value_per_person_hurt_bla_economic_2024": round(BLA_PER_INJURY_2024),
            "value_per_ksi_usdot_2024": round(USDOT_PER_KSI), "value_per_other_hurt_usdot_2024": round(USDOT_PER_OTHER_HURT),
        },
        "summary": {
            "fixes": len(out_fixes), "fixes_computable": sum(f["computable"] for f in out_fixes),
            "fix_group_pairs": n_pairs, "pairs_not_computable": sum(1 for n in not_computable if n["group"] != "(cost)"),
            "fixes_without_annual_cost": sum(1 for n in not_computable if n["group"] == "(cost)"),
            "families_with_a_fix": sum(1 for g in groups_out if g["fixes"]),
            "families_with_a_computable_fix": sum(1 for g in groups_out if any(x["computable"] for x in g["fixes"])),
            "not_computable_by_reason": dict(sorted(reasons_count.items())),
            "records_with_validation_errors": len(validation),
            "fixes_placed_by_reach": sum(1 for v in reach_log.values() if "error" not in v),
        },
        "groups": groups_out,
        "cross_cut_groups": cross_out,
        "fixes": out_fixes,
        "ranking": ranking,
        "ranking_by_ksi": ranking_ksi,
        "stacks": stacks,
        "not_computable": sorted(not_computable, key=lambda n: (n["fix"], n["group"], n["movement"] or "")),
        "validation": validation,
        "fill_log": fill_log,
        "aliases": dict(sorted(ALIASES.items())),
        "conflicts": sorted([list(p) for p in CONFLICTS if p[0] < p[1]]),
        "units": {k: {"low": v[0], "high": v[1], "basis": v[2]} for k, v in sorted(UNITS.items())},
        "reach": {
            "about": "fixes placed by analysis/crash-profiles/fixes/reach.json: each family pair's share is the group's "
                     "share in the named place (out/crash-augment/profiles/fix-reach.json), and a per-unit cost is "
                     "multiplied by SF's count of those places",
            "fixes": reach_log,
            "not_placed": (load(REACH_FILE).get("not_placed") if os.path.exists(REACH_FILE) else {}),
        },
        "sf_evidence": {k: [dict(ev, low_it_sets=round(sf_low(ev), 4)) for ev in v] for k, v in sorted(SF_EVIDENCE.items())},
        "counting": {
            "rho_max": RHO_MAX, "text_fit": TEXT_FIT,
            "text_share_reach_about": "entries whose share of a family (under 1) comes from their target_share text, by the crashes it is spread over",
            "text_share_reach": dict(sorted(collections.Counter(x["reach"] for x in spread_log if x["text_share"]).items())),
            "text_share_whole_family": sorted({(x["fix"], x["family"]) for x in spread_log
                                               if x["text_share"] and x["reach"] == "the whole family"}),
            "terms_with_rho_clamped": sorted({(f["id"], g) for f in out_fixes for g, ts in (f.get("stack_terms") or {}).items()
                                              for t in ts if t["rho_clamped"]}),
            "severity_by_value": {k: [{"r": r_, "scope": sc_, "why": w_} for r_, sc_, w_ in v] for k, v in sorted(SEVERITY_BY_VALUE.items())},
            "effect_from_group": {"%s | %s" % k: {"group": v[0], "why": v[1]} for k, v in sorted(EFFECT_FROM_GROUP.items())},
        },
        "gaps": gaps,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    text = json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
    if text != old:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(text)
    print("fixes %d (computable %d), pairs %d, not computable pairs %d, wrote %s%s" % (
        out["summary"]["fixes"], out["summary"]["fixes_computable"], n_pairs,
        out["summary"]["pairs_not_computable"], os.path.relpath(OUT, ROOT), "" if text != old else " (unchanged)"),
        file=sys.stderr)


if __name__ == "__main__":
    main()
