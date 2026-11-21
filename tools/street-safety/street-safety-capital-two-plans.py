#!/usr/bin/env python3
"""SFMTA street safety capital by type in two adopted plans, FY25-29 and FY27-31, grouped by one rule so they compare.

    tools/street-safety/street-safety-capital-two-plans.py          # writes the two CSVs below and prints the totals
    tools/street-safety/street-safety-capital-two-plans.py --list   # also prints every line with its type

Bryan, on which plan the white paper's spending chart should show (2026-11-18):
"Show both".

Which lines count is the rule the FY27-31 breakdown used: every Streets and
Signals line of the plan, reserves left out (ST000, SG000). Both plans' line
lists are read from files already checked against the plan's printed totals:

  FY27-31  research/notes/budget-2026-10/2026-11-05-street-safety-capital-lines.csv
           52 lines, $316,429,447, from Enclosure 3 of the FY27-31 CIP
           (https://www.sfmta.com/media/44860/download?inline). With the two
           reserves (ST000 $17,518,631, SG000 $2,100,000) these reproduce the
           Streets ($265,958,450, $1 over: see PUBLISHED) and Signals
           ($70,089,627) totals its "FY27-31 CIP Programming Summary" prints.
  FY25-29  out/sfmta-project-scale/past-budgets.csv, series "planned", period
           FY25-29: 66 lines, $234,940,154, parsed by scripts/sfmta-past-budgets.py
           from Enclosure 4 of SFMTA Board item 15A, 2024-04-16
           (https://www.sfmta.com/media/39080/download). With the Streets
           reserve (ST000 $17,747,957; this plan has no Signals reserve) these
           reproduce Table 1's Streets $221.2M and Signals $31.4M, and to the
           dollar the "Grand Total" rows Enclosure 4 prints for each program
           (Streets $221,249,187, Signals $31,438,924).

The two plans are rolling five-year windows that share three fiscal years
(FY26-27 to FY28-29), so a project whose money slips appears in both (SG106,
Tenderloin Signal Upgrade, is one) and the two totals must not be added. The
FY27-31 staff report (the same PDF, p. 6, read by OCR because pp. 1-12 have no
text layer) says its sources include "carryforward funds from prior years";
Enclosure 3's Signals lines name funds of earlier years (FHWA_SS4A_FY22 on
SG115, GOBOND(PropB)Streets2024 on SG060), and Enclosure 4 of FY25-29 names
no general obligation bond fund on any Streets or Signals line. A difference between
the plans is a difference in what each programmed for its own window, not a
change in yearly spending.

The type is the FY27-31 file's own "type_mine" column. A FY25-29 line takes
it when the same ID names the same project in FY27-31 (CARRY); every other
FY25-29 line is typed in HAND from its name and the plan's description, with
the reason. Five-year dollars are the plan's "CIP Total": money planned for
the five years, not money spent.

Checks, stop the run on failure: each plan's line count and dollar total
match the figures above; each plan's Streets (ST) and Signals (SG) lines plus
that program's reserve come to the program total the plan prints, to the
dollar except FY27-31 Streets, which is $1 over (PUBLISHED); no line sits
outside those two programs; every line has a type; every
type is one of the eight the FY27-31 chart uses; every HAND entry matches a
line, so a stale entry can't sit unseen.

Output (sorted, no run stamps):
  out/sfmta-project-scale/capital-by-type-two-plans.csv          one row per plan and line
  out/sfmta-project-scale/capital-by-type-two-plans-totals.csv   dollars and lines by plan and type
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import os

ROOT = paths.ROOT
FY2731 = os.path.join(ROOT, "research/notes/budget-2026-10/2026-11-05-street-safety-capital-lines.csv")
PAST = os.path.join(ROOT, "out/sfmta-project-scale/past-budgets.csv")
OUT = os.path.join(ROOT, "out/sfmta-project-scale/capital-by-type-two-plans.csv")
OUT_TOTALS = os.path.join(ROOT, "out/sfmta-project-scale/capital-by-type-two-plans-totals.csv")

EXPECT = {"FY25-29": (66, 234_940_154), "FY27-31": (52, 316_429_447)}

# Program totals each plan prints, and the reserve this script leaves out:
# FY25-29 from Enclosure 4's "Grand Total" rows, FY27-31 from Enclosure 3's
# "FY27-31 CIP Programming Summary". Lines by ID prefix plus the reserve must
# come to the printed total plus the third figure, which is 0 everywhere but
# FY27-31 Streets: Enclosure 3 prints ST040's years as $5,751,855 and its
# total as $5,751,854, and the lines file keeps the sum of the years.
PUBLISHED = {
    "FY25-29": {"ST": (221_249_187, 17_747_957, 0), "SG": (31_438_924, 0, 0)},
    "FY27-31": {"ST": (265_958_450, 17_518_631, 1), "SG": (70_089_627, 2_100_000, 0)},
}

# The FY27-31 file's types, with the short label the chart prints.
TYPES = {
    "Corridor and streetscape projects": "Corridors",
    "Signals and signs": "Signals and signs",
    "Traffic calming, Slow Streets, speed": "Calming, Slow Streets",
    "Bike network and bike programs": "Bike programs",
    "Quick-build programs": "Quick-build",
    "Crossings and daylighting": "Crossings, daylighting",
    "Schools": "Schools",
    "Planning, evaluation, education, other": "Planning, other",
}

# FY25-29 IDs that carry over to FY27-31 as the same project (the names match
# or one is a rename of the other: ST040 "WalkFirst" became "Citywide
# Crosswalks", ST042 "School Walk Audit" became "School Traffic Calming").
CARRY = {
    "SG011", "SG015", "SG017", "SG018", "SG106", "SG133",
    "ST025", "ST038", "ST040", "ST041", "ST042", "ST048", "ST071", "ST080", "ST122",
    "ST177", "ST240", "ST241", "ST244", "ST246", "ST253", "ST256", "ST266", "ST270",
    "ST271", "ST272", "ST273", "ST295", "ST297", "ST310", "ST314", "ST315", "ST316",
}

C, S, K, B, Q, X, SCH, P = (
    "Corridor and streetscape projects", "Signals and signs", "Traffic calming, Slow Streets, speed",
    "Bike network and bike programs", "Quick-build programs", "Crossings and daylighting", "Schools",
    "Planning, evaluation, education, other")

# FY25-29 lines with no same-project ID in FY27-31, keyed by (id, name)
# because the plan reuses STNEW-23 for two lines.
HAND = {
    ("SG103", "Automated Photo Enforcement - Phase 2 Expansion"): (S, "red-light cameras at signals, a Signals program line"),
    ("SG111", "Contract 67: New Traffic Signals"): (S, "new signals; FY27-31 carries it as SG111A, Signals and signs"),
    ("SGNEW", "Accessible Pedestrian Signals FY25"): (S, "same program as SG142 and SG143"),
    ("SGNEW", "Accessible Pedestrian Signals FY27"): (S, "same program as SG142 and SG143"),
    ("SGNEW", "Accessible Pedestrian Signals FY29"): (S, "same program as SG142 and SG143"),
    ("SGNew1", "Automated Photo Enforcement - Phase 3 Expansion"): (S, "red-light cameras at signals, as SG103"),
    ("SGNew2", "Tenderloin Conduits"): (S, "conduits for the SG106 signal upgrade"),
    ("ST203", "Program: Annual Traffic Calming Removal and Replacement"): (K, "removes and replaces speed humps"),
    ("ST236", "Business Transportation Demand Management (TDM)"): (P, "demand management, which builds nothing on a street"),
    ("ST239", "Ocean Beach Master Plan"): (C, "the Great Highway, Skyline to Sloat, one street"),
    ("ST243", "Residents Transportation Demand Management (TDM)"): (P, "demand management"),
    ("ST252", "Transportation Demand Management (TDM) for Tourists"): (P, "demand management"),
    ("ST262", "District 4 Neighborways"): (K, "a network of calmed side streets, as Slow Streets"),
    ("ST264", "Application-Based Residential Traffic Calming Program"): (K, "resident-requested humps and cushions"),
    ("STNEW-10", "Active Communities Bikeway Enhancements"): (B, "became ST336, Bike network and bike programs"),
    ("STNEW-12", "Side Show Deterrence"): (K, "\"traffic calming devices\" against sideshows"),
    ("STNEW-13", "Bike Share Expansion"): (B, "became ST334, Bike network and bike programs"),
    ("STNEW-14", "Roundabout Enhacements"): (K, "\"traffic calming, bike, and pedestrian measures\" at existing roundabouts"),
    ("STNEW-15", "Active Communities Implementation Sloat Enhancements"): (C, "bike and pedestrian work along one street, as 5th Street"),
    ("STNEW-16", "Active Communities Plan Lake Merced Upgrades"): (C, "bike and pedestrian work along one street, as 5th Street"),
    ("STNEW-17", "Active Communities Plan Mansell Streetscape"): (C, "a streetscape on one street, as 5th Street"),
    ("STNEW-18", "Mission Bay School Access"): (SCH, "access to new school sites"),
    ("STNEW-19", "Active Communities Plan Golden Gate Park Access"): (B, "a protected bikeway link, as the 7th Avenue link"),
    ("STNEW-2", "Active Communities Plan Implementation Program"): (B, "became ST332, Bike network and bike programs"),
    ("STNEW-22", "SoMa Arterial Traffic Calming"): (C, "signals, crosswalks and boarding islands along arterials"),
    ("STNEW-23", "Active Communities Spot Improvements"): (B, "replaces ST261, bike spot improvements"),
    ("STNEW-23", "Cesar Chavez/Bayshore/Potrero Long-Term"): (C, "one complex junction, as Tenderloin Protected Intersections"),
    ("STNEW-24", "Market Street Cycling Improvements"): (C, "as 1950 Market Cycling Improvements"),
    ("STNEW-3", "Active Communities Plan 7th Ave Bikeway Link"): (B, "became ST349, Bike network and bike programs"),
    ("STNEW-4", "Valencia Longterm"): (C, "the Valencia Street bikeway, one street"),
    ("STNEW-5", "Vision Zero Education and Communications"): (P, "became ST343, Planning, evaluation, education, other"),
    ("STNEW-7", "5th Street Streetscape"): (C, "became ST333, Corridor and streetscape projects"),
    ("STNEW-9", "Golden Gate Greenway (Tenderloin)"): (C, "a road diet and shared space on one block of Golden Gate Avenue"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    rows, by_id = [], {}
    with open(FY2731, newline="") as fh:
        for r in csv.DictReader(fh):
            by_id[r["cip_id"]] = r["type_mine"]
            rows.append({"plan": "FY27-31", "id": r["cip_id"], "name": r["project"],
                         "dollars": int(float(r["five_year_total"])), "type": r["type_mine"],
                         "basis": "FY27-31 file", "reason": ""})
    with open(PAST, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["series"] != "planned" or r["period"] != "FY25-29":
                continue
            key = (r["id"], r["name"])
            if r["id"] in CARRY:
                typ, basis, reason = by_id[r["id"]], "same ID in FY27-31", ""
            elif key in HAND:
                typ, reason = HAND[key]
                basis = "hand"
            else:
                raise SystemExit(f"FY25-29 line with no type: {key}")
            rows.append({"plan": "FY25-29", "id": r["id"], "name": r["name"], "dollars": int(r["dollars"]),
                         "type": typ, "basis": basis, "reason": reason})

    used = {(r["id"], r["name"]) for r in rows if r["plan"] == "FY25-29" and r["basis"] == "hand"}
    stale = sorted(set(HAND) - used)
    if stale:
        raise SystemExit(f"HAND entries that match no FY25-29 line: {stale}")
    bad = [r for r in rows if r["type"] not in TYPES]
    if bad:
        raise SystemExit(f"type outside the chart's eight: {bad}")
    for plan, (n, total) in EXPECT.items():
        got = [r for r in rows if r["plan"] == plan]
        if len(got) != n or sum(r["dollars"] for r in got) != total:
            raise SystemExit(f"{plan}: {len(got)} lines, ${sum(r['dollars'] for r in got):,}; expected {n}, ${total:,}")

    for plan, progs in PUBLISHED.items():
        for pre, (printed, reserve, over) in progs.items():
            got = sum(r["dollars"] for r in rows if r["plan"] == plan and r["id"][:2].upper() == pre)
            if got + reserve - printed != over:
                raise SystemExit(f"{plan} {pre}: lines ${got:,} + reserve ${reserve:,} is not the printed ${printed:,}")
        loose = [r["id"] for r in rows if r["plan"] == plan and r["id"][:2].upper() not in progs]
        if loose:
            raise SystemExit(f"{plan}: lines outside Streets and Signals: {loose}")

    rows.sort(key=lambda r: (r["plan"], list(TYPES).index(r["type"]), -r["dollars"], r["id"], r["name"]))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["plan", "id", "name", "dollars", "type", "basis", "reason"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    tot = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        tot[(r["plan"], r["type"])][0] += r["dollars"]
        tot[(r["plan"], r["type"])][1] += 1
    with open(OUT_TOTALS, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["type", "label", "plan", "dollars", "lines", "share"])
        for t, lab in TYPES.items():
            for plan in EXPECT:
                d, n = tot[(plan, t)]
                w.writerow([t, lab, plan, d, n, f"{d / EXPECT[plan][1]:.4f}"])

    for t, lab in TYPES.items():
        print(f"  {lab:24s} " + "  ".join(f"{p} ${tot[(p, t)][0] / 1e6:6.1f}M {tot[(p, t)][1]:2d}" for p in EXPECT))
    for p, (n, total) in EXPECT.items():
        print(f"  {p} total ${total / 1e6:.1f}M in {n} lines")
    if args.list:
        for r in rows:
            print(f"{r['plan']}  {r['id']:9s} {r['dollars'] / 1e6:7.2f}  {TYPES[r['type']]:22s} {r['name']}  [{r['basis']}{': ' + r['reason'] if r['reason'] else ''}]")


if __name__ == "__main__":
    main()
