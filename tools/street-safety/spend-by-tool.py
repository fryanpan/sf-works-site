#!/usr/bin/env python3
"""SFMTA street-safety capital budgets FY2022 to FY2026 by tool, set against each tool's unit cost, area of effect and graded evidence on speed, volume and injuries.

    python3 tools/street-safety/spend-by-tool.py                       # read the tracked line extract, write out/spend-by-tool/
    python3 tools/street-safety/spend-by-tool.py --rebuild-extract \
        --scratch /path/to/sf-works/scratch/runs           # rebuild the extract from the parsed CIP PDFs first

What it measures: ADOPTED two-year capital budgets, the first two years of each
Capital Improvement Program, not money spent. SFMTA publishes no actual spending
by line. FY21-22 come from the FY2021-2025 CIP, FY23-24 from the FY2023-2027 CIP
(both "Capital Projects by Phase & Funding Source", parsed from word positions by
scratch/runs/top-spot-fixes-2026-11-12/cip_bbox_years.py), FY25-26 from the
FY2025-2029 CIP, Enclosure 2 "Two-Year Capital Budget Projects" (pdftotext
-layout, scratch/runs/sfmta-scale/cip-fy25-29.txt). Names come from
scratch/runs/sfmta-scale/cip-summary.csv. Those inputs are gitignored; the
rebuilt per-line table is tracked at data/extract/sfmta-cip-lines/fy21-26-lines.json.

Steps:
  1. Lines -> tools. Every ST/SG line is mapped to one tool group in TOOL_OF. A
     line that mixes devices (quick-build, school walk audits, community
     response) stays a mixed group: the CIP cannot split it, and we don't guess.
  2. Devices: Complete raised devices (DataSF abhw-ffzx) by install date in the
     same fiscal years, by type and program, and the residential blocks they sit
     on. Budgets and installs are different cohorts, so no unit cost is derived
     from them, and the hump money is not split by device type.
  3. Each tool is joined to its evidence in TOOLS below: unit cost (with what
     kind of figure it is, since they are not like for like), area of effect,
     and only effects that have a graded row in data/evidence/studies.json. The
     script fails if an id has no row. The chart carries no evidence shading.

Quality checks (stop the run): FY25 and FY26 lines sum to the printed program
totals exactly; FY21-24 parsed totals sit within 10% of SFMTA's own program
totals (the shortfall is reported as "not attributed to a line"); every line is
mapped; no line id is counted twice in a year; every cited study id has a row.
Outputs are sorted and carry only data dates.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.stable import write_text  # noqa: E402

ROOT = pathlib.Path(paths.ROOT)
EXTRACT = ROOT / "data" / "extract" / "sfmta-cip-lines" / "fy21-26-lines.json"
OUT = ROOT / "out" / "spend-by-tool"
STUDIES = ROOT / "data" / "evidence" / "studies.json"
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
FIVE = [2022, 2023, 2024, 2025, 2026]

# SFMTA's own program totals, $M (FY21-22 FY2021-22 budget book; FY23-24 FY2023-2027 CIP;
# FY25-26 FY2025-2029 CIP Table 1 and Enclosure 2 totals). notes/street-safety-2026-10 decade note.
PROGRAM_TOTAL = {
    "Streets": {2021: 77.94, 2022: 80.00, 2023: 53.3, 2024: 37.3, 2025: 42.760416, 2026: 51.724662},
    "Signals": {2021: 18.48, 2022: 24.08, 2023: 16.5, 2024: 13.2, 2025: 10.861350, 2026: 5.110056},
}
DOCS = {
    "FY2021-2025 CIP": "https://www.sfmta.com/media/21935/download",
    "FY2023-2027 CIP": "https://www.sfmta.com/media/33065/download?inline",
    "FY2025-2029 CIP": "https://www.sfmta.com/media/39080/download",
}

# ---------------------------------------------------------------- line -> tool
G = {
    "humps": "New speed humps, cushions, tables",
    "point_other": "Other point devices (hump replacement after paving, roundabouts, left-turn calming, radar signs)",
    "beacons": "Flashing beacons (RRFB)",
    "ped_mixed": "WalkFirst pedestrian program (mixed)",
    "daylighting": "Daylighting",
    "bulbs": "Bulb-outs and painted safety zones",
    "retiming": "Signal retiming",
    "signals": "New and upgraded signals",
    "bikeways": "Bikeway projects (separated lanes, bike signals, spot fixes)",
    "bike_other": "Other bike programs",
    "slow": "Slow Streets and neighborways",
    "quickbuild": "Quick-build programs (mixed)",
    "schools": "School walk audits (mixed)",
    "community": "Community Response (mixed)",
    "corridors": "Corridor and streetscape projects",
    "area": "Area plans (CBTPs)",
    "other": "Other (TDM, education, evaluation, enforcement, signs)",
    "reserve": "Reserves (left out)",
}
# Point fixes: a device or treatment at one place. The floor counts only these
# groups; mixed programs (quick-build, WalkFirst, school audits, Community
# Response) also buy point fixes but can't be split.
POINT = ("humps", "point_other", "beacons", "daylighting", "bulbs", "retiming")
TOOL_OF = {
    "ST028": "humps", "ST264": "humps", "ST043": "humps",
    "ST203": "point_other", "ST272": "point_other", "STNew Roundabout Enhancements": "point_other",
    "ST037": "point_other",
    "ST122": "beacons",
    "ST040": "ped_mixed",
    "ST185": "daylighting",
    "ST115": "bulbs", "ST100": "bulbs",
    "SG104": "retiming",
    "SG011": "signals", "SG015": "signals", "SG017": "signals", "SG060": "signals", "SG062": "signals",
    "SG063": "signals", "SG072": "signals", "SG089": "signals", "SG106": "signals", "SG111": "signals",
    "SG133": "signals", "SG105": "signals", "SG107": "signals", "ST201": "signals",
    "SGNew Accessible Pedestrian Signals": "signals", "SGNew Tenderloin Conduits": "signals",
    "ST165": "bikeways", "ST169": "bikeways", "ST177": "bikeways", "ST193": "bikeways", "ST295": "bikeways",
    "ST045": "bikeways", "ST026": "bikeways", "ST266": "bikeways",
    "STNew Active Communities Bikeway": "bikeways", "STNew Active Communities": "bikeways",
    "STNew Active Communities Plan": "bikeways", "STNew Active Communities Spot": "bikeways",
    "STNew Active Communities Plan 7th": "bikeways", "STNew Market Street Cycling": "bikeways",
    "ST041": "bike_other", "ST048": "bike_other", "ST245": "bike_other", "ST250": "bike_other",
    "ST253": "bike_other",
    "ST025": "slow", "ST071": "slow", "ST088": "slow", "ST031": "slow", "ST262": "slow",
    "ST240": "quickbuild", "ST241": "quickbuild", "ST238": "quickbuild",
    "ST042": "schools", "STNew Mission Bay School Access": "schools",
    "ST038": "community",
    "ST052": "corridors", "ST053": "corridors", "ST059": "corridors", "ST080": "corridors",
    "ST084": "corridors", "ST094": "corridors", "ST097": "corridors", "ST157": "corridors",
    "ST158": "corridors", "ST181": "corridors", "ST183": "corridors", "ST200": "corridors",
    "ST235": "corridors", "ST239": "corridors", "ST273": "corridors", "ST314": "corridors",
    "ST315": "corridors", "ST316": "corridors", "STNew 5th Street Streetscape": "corridors",
    "STNew Golden Gate Greenway": "corridors", "STNew SoMa Arterial Traffic Calming": "corridors",
    "STNew Cesar Chavez/Bayshore/Potrero": "corridors",
    "ST195": "area", "ST197": "area", "ST246": "area",
    "ST039": "other", "ST155": "other", "ST236": "other", "ST237": "other", "ST256": "other",
    "ST243": "other", "ST244": "other", "ST248": "other", "ST249": "other", "ST251": "other",
    "ST252": "other", "ST254": "other", "ST255": "other", "ST257": "other", "ST270": "other",
    "SG018": "other", "SG103": "other", "STNew Side Show Deterrence": "other",
    "STNew Vision Zero Education and": "other",
    "ST000": "reserve", "SG000": "reserve", "ST247": "reserve",
}

SHORT = {"corridors": "Corridor projects", "signals": "New, upgraded signals", "bikeways": "Bikeway projects",
         "quickbuild": "Quick-build (mixed)", "slow": "Slow Streets", "area": "CBTP projects",
         "humps": "New humps, cushions, tables", "schools": "School walk audits (mixed)",
         "beacons": "Flashing beacons", "ped_mixed": "WalkFirst (mixed)", "point_other": "Other point devices",
         "community": "Community Response (mixed)", "retiming": "Signal retiming", "daylighting": "Daylighting",
         "bulbs": "Bulb-outs", "cells": "Low-traffic cells, 20 mph zones"}

# ---------------------------------------------------------------- evidence per tool
# Each effect is a graded study's own number, in its own units, from its row in
# data/evidence/studies.json (the ids in `studies`). A claim with no graded row
# is left out. Unit costs come from different kinds of source and are NOT like
# for like: `cost_kind` says which.
TOOLS = [
    dict(key="hump", group="humps", tool="Speed hump (round top)",
         unit_cost="$15,517 to $37,169 a device all-in",
         cost_kind="Two SFCTA requests: the Visitacion Valley proactive engineer's estimate (2021) and the FY22 application cycle allocation; the gap is design, outreach and program overhead",
         cost_src="notes/street-safety-2026-10/2026-10-22-calming-costs.md",
         area="Speeds fall at the device and for about 400 ft past it, not before it (Iowa 2002, SMS 2)",
         speed="See area",
         volume="About 24% less traffic on humped or cushioned UK roads (TRL 312, SMS 2)",
         injury="New York, 1,226 sites against later-treated sites: pedestrians hurt OR 0.91 (0.80 to 1.02). CMF 134: 0.5, 3 stars",
         studies=["roberts-2025-nyc-speed-humps", "iowa-2002-temporary-humps", "layfield-parry-1998-trl312", "fhwa-cmf-134-speed-humps"]),
    dict(key="cushion", group="humps", tool="Speed cushion",
         unit_cost="As a hump", cost_kind="Same SFCTA requests; they price humps, cushions and tables alike",
         cost_src="calming-costs note",
         area="As a hump",
         speed="Mean and 85th percentile 17 and 22 mph at cushions, 2 to 7 mph above humps (TRL 312, SMS 2)",
         volume="About 24% less traffic (2% to 48%), as humps (TRL 312)",
         injury="No graded crash study of cushions",
         studies=["layfield-parry-1998-trl312"]),
    dict(key="table", group="humps", tool="Speed table or raised crosswalk",
         unit_cost="As a hump", cost_kind="Same SFCTA requests",
         cost_src="calming-costs note",
         area="Its own block, or one crossing",
         speed="No graded study separates tables from humps",
         volume="No graded study",
         injury="No graded study separates tables from humps",
         studies=[]),
    dict(key="crosswalk", group="ped_mixed", tool="Ladder (continental) crosswalk",
         unit_cost="$4,000 to $6,000 a crosswalk", cost_kind="Planning estimate",
         cost_src="SFCTA Vision Zero Quick-Build Pre-Planning Study, 2023, Table 4",
         area="One crossing", speed="Not a speed tool", volume="None",
         injury="SF school crosswalks repainted yellow ladder: 37% fewer collisions (13% to 60%), CMF 0.63, 4 stars",
         studies=["feldman-2010-sf-school-crosswalks"]),
    dict(key="rrfb", group="beacons", tool="Flashing beacon (RRFB)",
         unit_cost="$50,000 a beacon", cost_kind="One SF allocation request (Monterey Blvd, FY2024/25)",
         cost_src="notes/school-crossing-beacons-signs-2026-10",
         area="One crossing", speed="Not a speed tool", volume="None",
         injury="FHWA 2025: not significant against uncontrolled crossings except a possible rise in rear-end crashes (unrated)",
         studies=["fhwa-2025-rrfb"]),
    dict(key="daylight", group="daylighting", tool="Daylighting",
         unit_cost="$1,072 to $2,605 an intersection in paint and signs",
         cost_kind="Planning estimate. No published SF cost for hardening with posts",
         cost_src="SFCTA Pre-Planning Study Table 4",
         area="One corner, the 20 ft before the crosswalk", speed="Not measured", volume="None",
         injury="New York, 189 hardened intersections: 0.14 fewer pedestrians hurt per intersection a year (about 32%). Signs only, 567 intersections: no change",
         studies=["nycdot-2025-daylighting"]),
    dict(key="bulb", group="bulbs", tool="Concrete bulb-out",
         unit_cost="$50,000 to $300,000 a corner", cost_kind="SFMTA published range",
         cost_src="notes/curb-extensions-2026-10 What We Know",
         area="One corner", speed="Not measured", volume="None",
         injury="Philadelphia, 94 against 269 planned: 13% fewer crashes (35% fewer to 18% more); pedestrians about no change",
         studies=["guerra-2026-philadelphia-bulbouts"]),
    dict(key="lpi", group="retiming", tool="Early walk signal (LPI)",
         unit_cost="$5,000 a signal", cost_kind="Planning estimate",
         cost_src="SFCTA Pre-Planning Study Table 4",
         area="One intersection", speed="Not a speed tool", volume="None",
         injury="CMF 0.86 on injury crashes (unrated; Clearinghouse page not opened)",
         studies=["fhwa-cmf-9911-lpi"]),
    dict(key="bikeway", group="bikeways", tool="Separated bikeway",
         unit_cost="$0.89M to $2.39M a mile as quick-build", cost_kind="Five SFMTA Board project budgets",
         cost_src="data/school-budget/unit-costs.json",
         area="A corridor, and the network it completes", speed="Not a speed tool", volume="Not graded",
         injury="Cycle tracks: about one ninth the injury odds of a major street with parking (OR 0.11)",
         studies=["teschke-2012"]),
    dict(key="slow", group="slow", tool="Slow Street",
         unit_cost="$200,000 to $238,000 a mile permanent", cost_kind="SFMTA Board staff report and a Prop L request",
         cost_src="calming-costs note",
         area="A corridor of 1 to 2 miles", speed="No graded study", volume="No graded study",
         injury="No graded study", studies=[]),
    dict(key="quickbuild", group="quickbuild", tool="Quick-build corridor",
         unit_cost="$400,000 a mile for one treatment; $1.71M a mile for the full bundle", cost_kind="Planning estimate",
         cost_src="SFCTA Pre-Planning Study Table 7",
         area="A corridor", speed="Not graded", volume="Not graded",
         injury="SFMTA 2024: all collisions -2%, pedestrian -32%, no comparison (unrated). New York road diets: injuries -17% (unrated)",
         studies=["sfmta-2024-safe-streets-evaluation", "nycdot-2023-vision-zero-sips"]),
    dict(key="cell", group="cells", tool="Low-traffic cell or 20 mph zone (area-wide)",
         unit_cost="About $0.75M a square kilometer (0.39 sq mi) cell", cost_kind="Planning estimate from the circulation plans What We Know doc",
         cost_src="notes/circulation-plans-2026-10 What We Know",
         area="A neighborhood of about 0.4 square miles, and its boundary streets", speed="Not graded", volume="Not graded",
         injury="London LTNs: injuries inside -35% (29% to 40%), boundary -2% (read from the abstract). London 20 mph zones: casualties -42%. European cost-benefit: area-wide calming not cost-effective at European build costs",
         studies=["furlong-2025-ltn-injuries", "grundy-2009", "daniels-2019-safetycube-cba"]),
]
DEVICE_TOOL = {"Speed Hump": "hump", "Speed Bump": "hump", "Speed Table": "table", "Raised Crosswalk": "table"}


def tool_of(i):
    """Tool group for a line id. New FY25-26 lines carry their name; the Active
    Communities Plan lines are the Biking and Rolling Plan's bikeway build-out."""
    if i in TOOL_OF:
        return TOOL_OF[i]
    if i.startswith("STNew Active Communities"):
        return "bikeways"
    for k, g in TOOL_OF.items():
        if k.startswith(("STNew ", "SGNew ")) and i.startswith(k):
            return g
    return None


class CheckFailed(SystemExit):
    pass


def check(ok, msg, log):
    log.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        print("\n".join(log), file=sys.stderr)
        raise CheckFailed("quality check failed: " + msg)


# ---------------------------------------------------------------- extract

def rebuild_extract(scratch, log):
    scratch = pathlib.Path(scratch)
    names = {}
    for r in csv.DictReader(open(scratch / "sfmta-scale" / "cip-summary.csv")):
        if r["id"][:2] in ("ST", "SG") and not r["id"].endswith("New"):
            # Prefer the newest book's name; the parse sometimes caught a description line.
            nm = r["name"].strip()
            if len(nm) < 70 and not nm[0].islower():
                names[r["id"]] = nm
    amt = collections.defaultdict(lambda: {y: 0 for y in YEARS})
    src = {}
    for f, ys, book in (("a2125.json", (2021, 2022), "FY2021-2025 CIP"), ("a2327.json", (2023, 2024), "FY2023-2027 CIP")):
        for r in json.load(open(scratch / "top-spot-fixes-2026-11-12" / f)):
            if r["col"] in ys:
                amt[r["id"]][r["col"]] += r["amt"]
                src.setdefault(r["id"], set()).add(book)
    # FY25-26: Enclosure 2, two columns, "-" for none.
    txt = (scratch / "sfmta-scale" / "cip-fy25-29.txt").read_text().splitlines()
    pat = re.compile(r"^(Signals|Streets)\s+((?:ST|SG)\d{3}|STNew|SGNew)\s+(.+?)\s{2,}([\d,]+|-)\s+([\d,]+|-)\s*$")
    printed = {}
    seen25 = set()
    block = txt[690:900]  # Signals and Streets sections of Enclosure 2
    for n, ln in enumerate(block):
        m = re.match(r"^(Signals|Streets)\s+Total\s+([\d,]+)\s+([\d,]+)\s*$", ln)
        if m:
            printed[m.group(1)] = (int(m.group(2).replace(",", "")), int(m.group(3).replace(",", "")))
            continue
        m = pat.match(ln)
        if not m:
            continue
        prog, i, nm, a, b = m.groups()
        nxt = block[n + 1] if n + 1 < len(block) else ""
        if re.match(r"^\s{15,}[A-Za-z]", nxt) and not re.search(r"\d", nxt):
            nm = nm.strip() + " " + nxt.strip()  # a name wrapped onto the next line
        key = i if i not in ("STNew", "SGNew") else "%s %s" % (i, nm.strip())
        base, k = key, 2
        while key in seen25 and i in ("STNew", "SGNew"):
            key = "%s (%d)" % (base, k)
            k += 1
        check(key not in seen25, "FY25-26 line %s appears once" % key, log)
        seen25.add(key)
        amt[key][2025] += 0 if a == "-" else int(a.replace(",", ""))
        amt[key][2026] += 0 if b == "-" else int(b.replace(",", ""))
        src.setdefault(key, set()).add("FY2025-2029 CIP")
        if i not in ("STNew", "SGNew"):
            names.setdefault(i, nm.strip())
        else:
            names[key] = nm.strip()
    for prog in ("Signals", "Streets"):
        got = [sum(v[y] for k, v in amt.items() if k.startswith(prog[:2].upper().replace("SI", "SG")))
               for y in (2025, 2026)]
        check(prog in printed and all(abs(g - p) <= 5 for g, p in zip(got, printed[prog])),
              "FY25-26 %s lines sum to the printed totals %s within $5 of rounding (got %s)" % (prog, printed.get(prog), got), log)
    # Names the summary parse missed (it caught a description line), from the CIP text.
    names.update({"ST028": "Program: Annual Application-Based Traffic Calming", "ST031": "Program: Citywide Neighborway",
                  "ST197": "Bayview CBTP Near Term Implementation", "SG072": "3rd Street Video Detection Replacement",
                  "ST201": "Geneva Avenue Traffic Signals", "ST200": "Alemany Interchange Improvement",
                  "ST041": "Program: Bike Facility Maintenance", "SG011": "Program: City Coordination Opportunities: New Traffic Signals",
                  "SG103": "Automated Photo Enforcement", "ST203": "Program: Annual Traffic Calming Removal and Replacement",
                  "ST059": "Cesar Chavez/Bayshore/Potrero", "ST155": "Move Western Addition Mid-Term",
                  "ST249": "Existing Residents Transportation Demand Management", "ST251": "Engineering Technical Feasibility and Cost",
                  "ST238": "Embarcadero Quick-Build", "ST245": "Citywide Bike Plan", "ST247": "Other Reserve",
                  "ST248": "Vision Zero SF Motorcycle Safety Program", "ST250": "Bike to Work Day",
                  "ST254": "Travel Decision Survey", "ST255": "Place Based Planning Program",
                  "ST257": "Comprehensive Employee TDM Program"})
    rows = []
    for k in sorted(amt):
        rows.append({"id": k, "name": names.get(k, ""), "program": "Signals" if k.startswith("SG") else "Streets",
                     "budget": {str(y): amt[k][y] for y in YEARS}, "books": sorted(src.get(k, []))})
    EXTRACT.parent.mkdir(parents=True, exist_ok=True)
    write_text(EXTRACT, json.dumps({
        "about": "SFMTA Streets (ST) and Signals (SG) capital lines, adopted budget by fiscal year, FY2021-FY2026. "
                 "Built by tools/street-safety/spend-by-tool.py --rebuild-extract from the parsed CIP PDFs.",
        "documents": DOCS, "lines": rows}, indent=1, sort_keys=True) + "\n")
    return rows


# ---------------------------------------------------------------- devices

def fiscal_year(r):
    try:
        y, m = int(r.get("install_yr") or 0), int(r.get("install_mo") or 0)
    except ValueError:
        return None
    if y < 1990:
        return None
    return y + 1 if 1 <= m <= 12 and m >= 7 else (y if 1 <= m <= 12 else None)


def devices(log):
    """Complete raised devices installed in FY2022-FY2026 (by install date, not the
    `fiscal_yr` field, which is the application cycle), by type and program, and
    the blocks they sit on against active, accepted residential blocks."""
    from sfdata import fetch
    dev = fetch("abhw-ffzx", select="row_id,cnn,tc_measure,units,install_mo,install_yr,install_datetime,fiscal_yr,"
                "program,current_status,data_as_of", floor=1500)
    check(len({r["row_id"] for r in dev.rows}) == len(dev.rows), "abhw-ffzx row_id unique (%d rows)" % len(dev.rows), log)
    by = collections.defaultdict(collections.Counter)
    prog = collections.Counter()
    blocks = set()
    no_month = 0
    for r in dev.rows:
        if r.get("current_status") != "Complete":
            continue
        m = r.get("tc_measure") or ""
        t = "cushion" if "Cushion" in m else DEVICE_TOOL.get(m)
        if not t:
            continue
        fy = fiscal_year(r)
        if fy is None:
            if (r.get("install_yr") or "0") in {str(y) for y in range(2021, 2027)}:
                no_month += 1
            continue
        if fy not in FIVE:
            continue
        try:
            u = int(r.get("units") or 0)
        except ValueError:
            u = 0
        u = max(u, 1)
        by[fy]["raised_crosswalk" if m == "Raised Crosswalk" else t] += u
        prog["App-Based" if r.get("program") == "App-Based" else "other programs"] += u
        blocks.add(r.get("cnn"))
    log.append("INFO Complete raised rows in 2021-2026 with no install month, left out: %d" % no_month)
    seg = {r["cnn"]: r for r in fetch("3psu-pn9h", select="cnn,classcode,active,accepted", floor=15000).rows}
    live = lambda r: r.get("active") in (True, "true") and r.get("accepted") in (True, "true")  # noqa: E731
    res_live = sum(1 for r in seg.values() if r.get("classcode") == "5" and live(r))
    check(res_live > 5000, "active, accepted residential blocks (classcode 5) counted: %d" % res_live, log)
    by_cls = collections.Counter(str(seg.get(c, {}).get("classcode")) for c in blocks)
    treated_res_live = sum(1 for c in blocks if seg.get(c, {}).get("classcode") == "5" and live(seg[c]))
    return {"by_fiscal_year": {str(y): dict(sorted(by[y].items())) for y in FIVE},
            "total": dict(sorted(sum((by[y] for y in FIVE), collections.Counter()).items())),
            "by_program": dict(sorted(prog.items())),
            "blocks_treated": len(blocks),
            "blocks_treated_by_classcode": dict(sorted(by_cls.items())),
            "blocks_treated_residential_active_accepted": treated_res_live,
            "residential_blocks_active_accepted": res_live,
            "data_as_of": max((r.get("data_as_of") or "") for r in dev.rows)[:10],
            "note": ("Complete raised devices by state fiscal year of install (July to June), counting `units`; FY2026 "
                     "runs to the data date. Blocks: centerline classcode 5 (residential), active and accepted; "
                     "treated blocks on other classes (mostly 4, collectors) are counted in blocks_treated_by_classcode "
                     "and left out of the residential share. Budgets and installs are different cohorts (a budget year "
                     "pays for devices built later), so dividing one by the other is not a unit cost.")}


def plotchart(a):
    """The <PlotChart> block for the board's Data and Notes page."""
    marks = [{"mark": "barX", "data": "a", "options": {"y": "k", "x": "v", "fill": "#4269d0"}},
             {"mark": "text", "data": "a", "options": {"y": "k", "x": "v", "text": "lab", "dx": 6, "textAnchor": "start",
                                                       "fontSize": 12, "fill": "#15181c"}},
             {"mark": "ruleX", "data": "z", "options": {"x": "_v"}}]
    opts = {"style": {"fontFamily": "inherit", "color": "#59626f"}, "width": 460, "height": 400, "marginLeft": 190,
            "marginRight": 80, "marginTop": 8, "marginBottom": 36, "fontSize": 12,
            "x": {"label": "FY2022 to FY2026 adopted budget ($ millions)", "labelAnchor": "left", "labelArrow": False,
                  "domain": [0, 100], "ticks": [0, 50, 100], "grid": True, "tickSize": 0},
            "y": {"label": None, "domain": [c["k"] for c in a], "tickSize": 0}}
    return ('<PlotChart\n  title="SFMTA street-safety capital budget by tool, FY2022 to FY2026 (adopted budgets, '
            'lines we could name)"\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n'
            % (json.dumps({"z": [{"_v": 0}], "a": a}), json.dumps(marks), json.dumps(opts)))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-extract", action="store_true")
    ap.add_argument("--scratch", default=str(ROOT / "scratch" / "runs"))
    args = ap.parse_args()
    log = []
    if args.rebuild_extract:
        rlog = []
        rebuild_extract(args.scratch, rlog)
        print("\n".join(rlog))
    ext = json.load(open(EXTRACT))
    lines = ext["lines"]

    unmapped = [l["id"] for l in lines if tool_of(l["id"]) is None]
    check(not unmapped, "every CIP line maps to a tool group (unmapped: %s)" % unmapped, log)
    check(len({l["id"] for l in lines}) == len(lines), "line ids unique", log)

    # Program totals against SFMTA's own.
    recon = {}
    for prog in ("Streets", "Signals"):
        for y in YEARS:
            got = sum(l["budget"][str(y)] for l in lines if l["program"] == prog) / 1e6
            want = PROGRAM_TOTAL[prog][y]
            recon["%s %d" % (prog, y)] = {"parsed": round(got, 3), "sfmta": want, "gap": round(want - got, 3)}
            if y > 2022:
                check(abs(got - want) <= 0.10 * want, "%s FY%d parsed $%.2fM within 10%% of SFMTA's $%.2fM" % (prog, y, got, want), log)
        # FY21 and FY22 come from one table whose year columns the word-position
        # parse can confuse (Signals: +$6.0M in FY21, -$4.0M in FY22), so they are
        # checked together; the FY22 shortfall is reported, not hidden.
        got2 = sum(l["budget"][str(y)] for l in lines if l["program"] == prog for y in (2021, 2022)) / 1e6
        want2 = PROGRAM_TOTAL[prog][2021] + PROGRAM_TOTAL[prog][2022]
        check(abs(got2 - want2) <= 0.10 * want2, "%s FY21+FY22 parsed $%.2fM within 10%% of SFMTA's $%.2fM" % (prog, got2, want2), log)

    # Group sums.
    grp = collections.defaultdict(lambda: {y: 0 for y in YEARS})
    members = collections.defaultdict(list)
    for l in lines:
        g = tool_of(l["id"])
        for y in YEARS:
            grp[g][y] += l["budget"][str(y)]
        if any(l["budget"][str(y)] for y in FIVE):
            members[g].append("%s %s" % (l["id"], l["name"]) if not l["id"].startswith(("STNew", "SGNew")) else l["id"])
    five = {g: sum(v[y] for y in FIVE) for g, v in grp.items()}
    counted = sum(v for g, v in five.items() if g != "reserve")
    sfmta_five = sum(PROGRAM_TOTAL[p][y] for p in PROGRAM_TOTAL for y in FIVE) * 1e6
    check(counted > 0.75 * sfmta_five, "non-reserve lines hold %.0f%% of SFMTA's FY22-26 total" % (100 * counted / sfmta_five), log)

    dv = devices(log)

    # Studies.
    st = {s["id"] for s in json.load(open(STUDIES))["studies"]}
    missing = sorted({i for t in TOOLS for i in t["studies"]} - st)
    check(not missing, "every cited study has a row in studies.json (missing: %s)" % missing, log)
    tools = [dict(t, group_budget_fy22_26=five.get(t["group"], 0)) for t in TOOLS]

    groups = []
    amounts = {l["id"]: sum(l["budget"][str(y)] for y in FIVE) for l in lines}
    for g in G:
        top = sorted(((amounts[l["id"]], l["id"], l["name"]) for l in lines if tool_of(l["id"]) == g and amounts[l["id"]]),
                     reverse=True)
        groups.append({"key": g, "label": G[g], "fy22_26": five.get(g, 0),
                       "by_year": {str(y): grp[g][y] for y in YEARS},
                       "lines": [{"id": i, "name": n, "fy22_26": v} for v, i, n in top]})
    groups.sort(key=lambda r: (-r["fy22_26"], r["key"]))

    point = sum(five.get(g, 0) for g in POINT)
    ride_hail = 11160000
    res = {
        "about": "SFMTA Streets and Signals capital lines, adopted budgets FY2022-FY2026 (five fiscal years), by tool. "
                 "Budgets, not spending. Built by tools/street-safety/spend-by-tool.py.",
        "documents": DOCS,
        "fy22_26_attributed_to_named_lines": counted,
        "fy22_26_reserves": five.get("reserve", 0),
        "fy22_26_sfmta_program_total": round(sfmta_five),
        "fy22_26_not_attributed_to_a_line": round(sfmta_five - counted - five.get("reserve", 0)),
        "reconciliation_musd": recon,
        "footnotes": [
            "Signals: the parse puts $6.0M too much in FY21 and $4.0M too little in FY22 against SFMTA's totals; "
            "the fund codes on SG060 and SG063 rows say FY21, so the misplaced line is not found. If the $4.0M belongs "
            "in FY22, Signals FY22-26 is about $60.7M, not $56.7M.",
            "Streets FY23 and FY24 parse $2.2M and $2.5M under SFMTA's totals; the missing lines are not located.",
            "SG106 Tenderloin Signal Upgrade parses about $1.9M above its FY23-24 figure in the CIP text.",
        ],
        "point_fixes_floor": {
            "usd": point, "groups": [G[g] for g in POINT],
            "share_of_attributed": round(point / counted, 3), "share_of_sfmta_total": round(point / sfmta_five, 3),
            "with_ride_hail_usd": point + ride_hail,
            "with_ride_hail_share_of_sfmta_total": round((point + ride_hail) / (sfmta_five + ride_hail), 3),
            "note": "A floor: quick-build, WalkFirst, school audits and Community Response also buy point fixes but "
                    "can't be split. The ride-hail money may overlap the CIP's hump lines; unchecked."},
        "groups": groups,
        "hump_devices_fy22_26": dv,
        "ride_hail_hump_money_outside_cip": {
            "usd": ride_hail,
            "note": "SFCTA ride-hail tax list (July 2025 board) allocates $11.16M to the application-based calming program, "
                    "FY21-FY25 cycles; not in the CIP's ST028/ST264 rows, which list Prop K and Prop B only. Overlap unchecked. "
                    "Per notes/street-safety-2026-11/2026-11-12-top-spot-fixes.md."},
        "tools": tools,
        "quality_log": log,
    }
    # Chart rows: five-year budget by tool group, plus the area-wide tools that
    # have no line at all. No evidence shading: each group's evidence is in TOOLS.
    chart = []
    for r in groups:
        if r["key"] in ("reserve", "other", "bike_other"):
            continue
        chart.append({"k": SHORT[r["key"]], "v": round(r["fy22_26"] / 1e6, 1),
                      "lab": "$%.1fM" % (r["fy22_26"] / 1e6)})
    chart.append({"k": SHORT["cells"], "v": 0.0, "lab": "$0, no line"})
    res["chart"] = chart
    OUT.mkdir(parents=True, exist_ok=True)
    write_text(OUT / "results.json", json.dumps(res, indent=1, sort_keys=True) + "\n")
    write_text(OUT / "plotchart.mdx", plotchart(chart))
    print("\n".join(log))
    for r in groups:
        print("%8.2f  %s" % (r["fy22_26"] / 1e6, r["label"]))
    print("point floor", res["point_fixes_floor"], "devices", dv["total"], dv["by_program"])


if __name__ == "__main__":
    main()
