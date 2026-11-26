#!/usr/bin/env python3
"""Merge the crash-fix lanes into one map of SF crash groups to fixes, with people hurt and KSI avoided, cost per injury avoided and stacked packages.

Reads analysis/crash-profiles/fixes/lanes/*.json (critique.json is read for gaps
only; fill.json is applied last and overrides by id), merges records that are
the same treatment under different names (ALIASES), validates every record
against the schema in analysis/crash-profiles/fixes/README.md, joins SF counts
from out/crash-augment/profiles/results.json, and writes
out/crash-augment/profiles/fix-map.json.

Counting rules (each one is also in the README):

- People hurt and KSI people are 2017 to 2024, eight years, from
  size_families.families. A year is the eight-year count over 8.
- An effect is normalised to a fraction r of the target crashes removed
  (positive is fewer): "% fewer" is r = v/100; "% change" is r = -v/100;
  a CMF, rate ratio, odds ratio or RR is r = 1 - v. Low, mid and high are
  re-sorted so low is the smallest cut.
- An effect is applied only where its applies_to matches: its unit must name a
  crash or injury outcome (not speeding, violations, yielding, an exponent or
  elasticity, or a risk factor); an effect on fatal or serious outcomes only is
  applied to KSI and not to all people hurt; an effect that names one road user
  (pedestrian, cyclist) is applied only to that mode's groups. An effect on all
  injuries or all crashes is applied to both people hurt and KSI.
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
  ratio (20 mph blocks 1.27, so a low of a 27% rise). Each pair records it.
- Avoided a year = group count a year x target share x r.
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
  ranked on its own. Stacks count sequentially (TRL PPR844): within a group,
  remaining = product over the package of (1 - share x r), and the package
  total sums over the 45 mode x family groups, which partition everyone hurt.
  "all other families" entries are applied to each family outside the chart,
  unless a fix maps that family itself. Cross-cut groups ("place |", "who |",
  "time |", crash types) overlap the families and are reported, not stacked.
- CONFLICTS lists fixes that are versions of one another; a stack takes the
  first of a conflicting pair and skips the other.

Standard library only. Deterministic: sorted keys and lists, no wall clock.

    python3 analysis/crash-profiles/fix-map.py
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LANES = os.path.join(ROOT, "analysis", "crash-profiles", "fixes", "lanes")
RESULTS = os.path.join(ROOT, "out", "crash-augment", "profiles", "results.json")
OUT = os.path.join(ROOT, "out", "crash-augment", "profiles", "fix-map.json")

YEARS = 8  # 2017 to 2024
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
_TWENTY = {"ratio": 1.27, "lo": 1.20, "hi": 1.34, "modes": None, "what": "821 dated 20 mph blocks: injury crashes 1.27 (1.20 to 1.34); the method leans up 6% to 16% on these blocks (selection), and after either correction crashes still ran 10% to 20% above expected"}
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
        return sh, sk, basis

    def units(self, cid):
        c = self.cfg.get(cid) or {}
        key = c.get("units")
        if not key or self.data is None:
            return None
        u = self.data["units"].get(key)
        if not u or u.get("value") is None:
            return None
        n = u["value"] * c.get("units_scale", 1)
        note = "%s %s (%s; %s)" % (("{:,.1f}" if isinstance(u["value"], float) else "{:,}").format(u["value"]),
                                   key.replace("_", " "), u["how"], u["tag"])
        if c.get("units_scale"):
            note += " x %s (%s)" % (c["units_scale"], c.get("scale_basis", ""))
        return (n, n, note)

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
CRASH_WORDS = re.compile(r"crash|injur|casualt|collision|accident|death|killed|fatal|ksi|^cmf|cmf\b|^rr\b|rate ratio|odds ratio|risk|incidence", re.I)
KSI_WORDS = re.compile(r"\bksi\b|killed|fatal|death|serious|severe", re.I)


def ratio_unit(u):
    u = u.strip().lower()
    return u in ("cmf", "odds ratio", "rate ratio", "fatality risk") or u.startswith("rr")


def normalise_effect(e, group_mode):
    """Return (dict with low/mid/high fractions and scope) or (None, reason)."""
    unit = (e.get("unit") or "").strip()
    vals = [e.get(k) for k in ("low", "mid", "high")]
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None, "no effect size"
    if not unit:
        return None, "effect has no unit"
    if NON_CRASH.search(unit) and not (re.search(r"injur|crash|casualt", unit, re.I) and not re.search(
            r"not crashes|exponent|elasticity|worse outcome|hazard|tracks present|block with construction|wearing rate|association", unit, re.I)):
        return None, "effect is not a crash or injury outcome (%s)" % unit[:80]
    if not CRASH_WORDS.search(unit) and not unit.startswith("%"):
        return None, "effect unit does not name a crash outcome (%s)" % unit[:80]
    if ratio_unit(unit):
        conv = [None if v is None else 1 - v for v in vals]
    elif "fewer" in unit.lower():
        conv = [None if v is None else v / 100 for v in vals]
    elif "%" in unit or unit.lower().startswith("% "):
        conv = [None if v is None else -v / 100 for v in vals]
    else:
        return None, "effect unit not recognised (%s)" % unit[:80]
    present = [v for v in conv if v is not None]
    mid = conv[1]
    if mid is None:
        mid = sum(present) / len(present)
    lo, hi = min(present + [mid]), max(present + [mid])
    if lo < -5 or hi > 1.0001:
        return None, "effect outside a plausible range after normalising (%s)" % unit[:60]
    u = unit.lower()
    u_strip = re.sub(r"seriously injured|serious injur\w*|severely injured", "", u)
    if KSI_WORDS.search(u) and not re.search(r"injur|casualt|all severities|every severity|fatal and|fatal or", u_strip):
        scope = "ksi"
    else:
        scope = "all"
    # road-user match
    names_ped = re.search(r"pedestrian", u)
    names_bike = re.search(r"cyclist|bicycl|bike", u)
    if names_ped and not names_bike and group_mode not in ("pedestrian involved", "pedestrian", "who"):
        if group_mode in ("vehicles only", "bicycle involved"):
            return None, "effect is for pedestrians, group is %s" % group_mode
    if names_bike and not names_ped and group_mode in ("vehicles only", "pedestrian involved"):
        if not re.search(r"vehicle-bicycle|vehicle and bicycle|cyclist-car", u):
            return None, "effect is for cyclists, group is %s" % group_mode
    return {"low": round(lo, 6), "mid": round(mid, 6), "high": round(hi, 6), "scope": scope}, None


# ---------------------------------------------------------------- target share

DISQUALIFY = re.compile(
    r"not computed|not in results\.json|not split|not known|unknown|not linkable|not measured|is not coded|"
    r"\bonly (?:on|at|in|inside|where|blocks|treated|camera|crashes|the part|miles|approaches|the zone)\b|"
    r"\bonly\b[^.;]{0,30}\b(?:blocks|streets|corridors?|sites|corners|zone|cells)\b", re.I)
WHOLE = re.compile(r"whole group|all in reach|every crash in the group|the whole family|group in reach|\ball\s+" + NUM + r"\s+people hurt", re.I)


def parse_share(text, tot_h, tot_k, movement, movements):
    """Return (share_hurt, share_ksi, basis) or (None, None, reason).

    An explicit "N% of the group" wins. Text that says the reachable share is
    not computed, unknown, or limited to some blocks, corridors or sites leaves
    the pair not computable, because the street-class or movement counts beside
    such a caveat overstate the reach."""
    t = text or ""
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
        if sh is None and tot_h and abs(b - tot_h) < 0.5 and a <= b:
            sh = a / b
        elif sk is None and tot_k and abs(b - tot_k) < 0.5 and a <= b:
            sk = a / b
    if sh is not None:
        if sk is None:
            m2 = re.search(r"\(\s*" + NUM + r"\s+(?:of\s+" + NUM + r"\s+)?KSI", t)
            if m2 and tot_k and num(m2.group(1)) <= tot_k:
                sk = num(m2.group(1)) / tot_k
        if sk is None:
            return sh, sh, "people-hurt share from text; KSI share taken equal"
        return sh, sk, "shares from text"
    if WHOLE.search(t):
        return 1.0, 1.0, "text says the whole group is in reach"
    if not re.search(r"group total", t, re.I):
        m3 = re.match(r"\s*" + NUM + r"\s*(?:people hurt)?\s*[,/(]\s*" + NUM + r"\s*(?:KSI)?", t)
        if m3 and tot_h and abs(num(m3.group(1)) - tot_h) < 0.5 and tot_k is not None and abs(num(m3.group(2)) - tot_k) < 0.5:
            return 1.0, 1.0, "text gives the whole group's counts as the reach"
    if movement and movement in movements:
        mh, mk = movements[movement]
        if tot_h:
            return mh / tot_h, (mk / tot_k if tot_k else mh / tot_h), "movement share from size_families"
    return None, None, "target share not parseable from text"


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


def main():
    res = load(RESULTS)
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
        if name in fam:
            return fam[name]["people_hurt"], fam[name]["ksi"], fam[name]["mode"], fam[name]["movements"], "family"
        if name == "all other families":
            return other_row["people_injured"], other_row["ksi_people"], "all", {}, "remainder"
        for key, (h, k) in cross_totals.items():
            if name.endswith(key) or key in name:
                mode = "pedestrian" if "pedestrian" in name else ("who" if name.startswith("who") else "cross")
                return h, k, mode, {}, "cross-cut"
        m = re.search(NUM + r"\s+(?:people\s+)?hurt\s*/\s*" + NUM + r"\s+KSI", text or "")
        if m:
            mode = "pedestrian" if "pedestrian" in name else "cross"
            return num(m.group(1)), num(m.group(2)), mode, {}, "cross-cut (count from target_share text)"
        return None, None, None, {}, "cross-cut, no count found"

    out_fixes, not_computable, pair_rows = [], [], {}
    for cid in sorted(merged):
        rec = merged[cid]
        cost, cost_reason = annual_cost(rec)
        pairs = []
        chosen = {}
        last_share = {}
        for g in rec.get("groups") or []:
            name = g.get("group") or ""
            if "status" in g and "remove" in str(g["status"]).lower():
                continue
            h, k, mode, movements, kind = group_totals(name, g.get("target_share"))
            e = g.get("effect") or {}
            eff, ereason = normalise_effect(e, mode if mode != "all" else None)
            sh = sk = None
            sbasis = None
            ts = str(g.get("target_share") or "")
            reach_row = None
            if h is not None and cid in reach.cfg and kind in ("family", "remainder"):
                tsh = None
                if reach.text_mode(cid, name) == "multiply":
                    a, b, _ = parse_share(ts, h, k, g.get("movement"), movements)
                    tsh = (a, b) if a is not None else None
                sh, sk, sbasis = reach.share(cid, name, g.get("movement"), tsh)
                reach_row = {"place": reach.place_of(cid, name), "text_share": tsh}
                last_share[(name, g.get("movement") or "")] = (sh, sk, sbasis)
            elif h is not None:
                if re.match(r"\s*same (reach|basis)", ts, re.I) and (name, g.get("movement") or "") in last_share:
                    sh, sk, sbasis = last_share[(name, g.get("movement") or "")]
                    sbasis = "same reach as the entry before: " + str(sbasis)
                else:
                    sh, sk, sbasis = parse_share(ts, h, k, g.get("movement"), movements)
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
                    if eff["low"] > lowest + 1e-9:
                        eff = dict(eff, low=round(lowest, 6))
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
                "group": name, "movement": g.get("movement"), "kind": kind, "from": g.get("from"),
                "mechanism": g.get("mechanism"), "target_share_text": g.get("target_share"),
                "effect": e, "group_people_hurt": h, "group_ksi": k,
            }
            if reach_row:
                row["reach_place"] = reach_row["place"]
                row["_text_share"] = reach_row["text_share"]
            if sf_note:
                row["sf_evidence"] = sf_note
            if reason:
                row["computable"] = False
                row["reason"] = reason
            else:
                hy, ky = h / YEARS, k / YEARS
                rh = eff if eff["scope"] == "all" else None
                ah = None if rh is None else {q: hy * sh * rh[q] for q in ("low", "mid", "high")}
                ak = {q: ky * sk * eff[q] for q in ("low", "mid", "high")}
                row.update({
                    "computable": True, "share_hurt": r0(sh, 4), "share_ksi": r0(sk, 4), "share_basis": sbasis,
                    "effect_fraction": eff, "effect_scope": eff["scope"],
                    "hurt_avoided_per_year": None if ah is None else {q: r0(v) for q, v in ah.items()},
                    "ksi_avoided_per_year": {q: r0(v, 3) for q, v in ak.items()},
                })
                if eff["scope"] == "ksi":
                    row["note"] = "effect measured on fatal or serious outcomes only, so applied to KSI and not to all people hurt"
                gk = (name, g.get("movement") or "")
                # one entry per group and movement: the first computable in lane order
                if gk not in chosen:
                    chosen[gk] = row
                    row["used"] = True
                else:
                    row["used"] = False
                    row["note"] = (row.get("note", "") + "; " if row.get("note") else "") + "alternate estimate; the first computable entry for this group is used"
            pairs.append(row)
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
                            mrows.append(r2)
                        expanded[member] = mrows
            else:
                expanded[gname] = rows
        stack_terms = {}
        for gname, rows in sorted(expanded.items()):
            terms = []
            for row in rows:
                eff = row["effect_fraction"]
                sh, sk = row["share_hurt"], row["share_ksi"]
                terms.append({q: (sh * eff[q] if eff["scope"] == "all" else 0.0, sk * eff[q]) for q in ("low", "mid", "high")})
            stack_terms[gname] = terms
        tot = {q: [0.0, 0.0] for q in ("low", "mid", "high")}
        for gname, terms in stack_terms.items():
            hy, ky = fam[gname]["people_hurt"] / YEARS, fam[gname]["ksi"] / YEARS
            for q in tot:
                rem_h = rem_k = 1.0
                for t in terms:
                    rem_h *= 1 - t[q][0]
                    rem_k *= 1 - t[q][1]
                tot[q][0] += hy * (1 - rem_h)
                tot[q][1] += ky * (1 - rem_k)
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
        rec_out["groups"] = pairs
        rec_out["validation_errors"] = validation.get(cid, [])
        rec_out["avoided_basis"] = basis if any_pair else None
        rec_out["hurt_avoided_per_year"] = {q: r0(v) for q, v in hurt.items()} if any_pair else None
        rec_out["ksi_avoided_per_year"] = {q: r0(v, 3) for q, v in ksi.items()} if any_pair else None
        rec_out["annual_cost"] = None if cost is None else {k: (r0(v, 0) if isinstance(v, float) else v) for k, v in cost.items()}
        reasons = []
        if cid in ENABLERS:
            reasons.append("enabler: its benefit comes from building %s, which carries the cost and is ranked instead" % ENABLERS[cid])
        if not any_pair:
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
                rec_out_note = "no people hurt avoided at mid (effect zero, harmful, or measured on KSI only); ranked by KSI only"
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
        rec_out["_stack_terms"] = stack_terms
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

    def build_stack(cands, metric, q="mid", cq=None):
        cq = cq or q
        rem = {g: [1.0, 1.0] for g in fam}
        added, steps = set(), []
        cum_cost = cum_h = cum_k = 0.0
        pool = sorted(cands, key=lambda f: f["id"])
        while True:
            best = None
            for f in pool:
                if f["id"] in added or any((f["id"], a) in CONFLICTS for a in added):
                    continue
                dh = dk = 0.0
                for g, terms in f["_stack_terms"].items():
                    hy, ky = fam[g]["people_hurt"] / YEARS, fam[g]["ksi"] / YEARS
                    nh, nk = rem[g]
                    for t in terms:
                        nh *= 1 - t[q][0]
                        nk *= 1 - t[q][1]
                    dh += hy * (rem[g][0] - nh)
                    dk += ky * (rem[g][1] - nk)
                gain = dh if metric == "hurt" else dk
                if gain <= 1e-9:
                    continue
                c = f["annual_cost"][cq]
                key = (c / gain, -gain, f["id"])
                if best is None or key < best[0]:
                    best = (key, f, dh, dk)
            if best is None:
                break
            _, f, dh, dk = best
            for g, terms in f["_stack_terms"].items():
                for t in terms:
                    rem[g][0] *= 1 - t[q][0]
                    rem[g][1] *= 1 - t[q][1]
            added.add(f["id"])
            cum_cost += f["annual_cost"][cq]
            cum_h += dh
            cum_k += dk
            steps.append({
                "step": len(steps) + 1, "id": f["id"], "scope": f["scope"], "annual_cost": r0(f["annual_cost"][cq], 0),
                "marginal_hurt_avoided": r0(dh), "marginal_ksi_avoided": r0(dk, 3),
                "marginal_cost_per_person_hurt": r0(f["annual_cost"][cq] / dh, 0) if dh > 0 else None,
                "marginal_cost_per_ksi": r0(f["annual_cost"][cq] / dk, 0) if dk > 0 else None,
                "cumulative_annual_cost": r0(cum_cost, 0), "cumulative_hurt_avoided": r0(cum_h),
                "cumulative_ksi_avoided": r0(cum_k, 3),
                "share_of_people_hurt_avoided": r0(cum_h / year_h, 4), "share_of_ksi_avoided": r0(cum_k / year_k, 4),
            })
        skipped = sorted(f["id"] for f in pool if f["id"] not in added)
        return {"steps": steps, "not_added": skipped}

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
        st.update(summarise(st))
        st["ranked_by"] = "cost per %s avoided on what remains, mid" % ("person hurt" if metric == "hurt" else "KSI person")
        st["candidates"] = len(cands)
        stacks[name] = st
    for label, eq, cq in (("optimistic", "high", "low"), ("pessimistic", "low", "high")):
        st = build_stack(stackable, "hurt", eq, cq)
        sm = summarise(st)
        stacks["greedy_by_people_hurt_" + label] = {
            "end": sm["end"], "at_budgets": sm["at_budgets"], "steps": st["steps"],
            "note": "same greedy stack with every effect at its %s value and every cost at its %s value" % (eq, cq)}
    stacks["about"] = (
        "Sequential counting (TRL PPR844): within each of the 45 mode x family groups, each added fix acts only on the "
        "people left after the fixes before it, remaining = product of (1 - share x r); the package total sums over the "
        "groups. It assumes the fixes' effects are independent, the standard conservative rule. Only fixes with an "
        "annual cost and at least one computable family pair are stacked; CONFLICTS keeps one version of a fix. "
        "Shares are of %d people hurt and %d KSI people a year (2017-2024 over 8). Annual cost mixes dollar years." % (round(year_h), round(year_k)))

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
        f.pop("_stack_terms", None)
        for row in f["groups"]:
            row.pop("_text_share", None)
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
