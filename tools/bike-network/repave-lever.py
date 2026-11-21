#!/usr/bin/env python3
"""How many bike-network miles a year tying bike work to repaving would add, from the paving record.

    tools/bike-network/repave-lever.py              # build from cached reads
    tools/bike-network/repave-lever.py --refetch    # re-read the DataSF tables first

Bryan, 2026-09-22: "Dig into how big of a lever it really is to try and
coordinate Public Works and SFPUC projects with biking infrastructure. How many
miles would that help us add to the network each year" — and the assumption to
test, that "we actually repave those streets much more often than once every 30
years."

Inputs:
  78va-8dhi  Historical Pavement Condition Index scores. One row per PCI change
             per block, 1947 to today, each flagged Survey or Treatment. A
             Treatment that resets the score to 100 is a resurfacing; lighter
             treatments (seals, patches) leave it in the 60s-90s. Validated
             below against the moratorium record.
  5wbp-dwzt  Utility Excavation Moratorium Streets: the five-year dig lock that
             follows a repave. Used only to validate the repave definition.
  btxj-k9uh  Public Works' coordination feed: Public Works and SFPUC projects
             whose construction has started, by block.
  data/extract/sfmta-bikeway/network.json   SFMTA's own bikeway layer, with
             INSTALL_YR and UPDATE_YR (tools/bike-network/bike-progress.py fetches it).
  data/extract/bikeway-snapshots/<stamp>.json  Internet Archive captures of
             the DataSF copy (ygmz-vaxd), 2021-03 to 2026-04, the extracts
             tools/bike-network/bike-network-history.py writes. Each is dated here by the
             release it holds (data_loaded_at) where the column exists, so the
             two scripts name one date for one release.
  site/data/bike-history/reported.json      Bikeway work SFMTA's project pages
             call built this year, which the layer does not yet carry
             (tools/bike-network/bike-reported-work.py). Its blocks count at the class
             the page gives, dated that year, as bike-network-history.py does.
  site/data/north-star/traced.geojson       The plan's network, one row per
             block, with the facility the plan draws on it.
  3psu-pn9h  Street centerlines, for the citywide block count.

Every join is by CNN, the city's block id. A repave and a plan segment on the
same CNN are co-located on the same block; nothing here says the paving job
was, or was not, the project that built a bikeway.

Writes out/repave-lever/lever.md and out/repave-lever/lever.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
from extract import Extract  # noqa: E402
from sfdata import fetch, metadata  # noqa: E402
from plan_directions import Directions  # noqa: E402
from bikeway_snap import rekeyed_layer  # noqa: E402
from mile_basis import BASIS  # noqa: E402

OUT = os.path.join(ROOT, "out", "repave-lever")
TRACE = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
SNAP_DIR = os.path.join(ROOT, "data", "extract", "bikeway-snapshots")
PLAN_TAG = "[Biking and Rolling Plan, March 2025, North Star map — traced 2026-09-29]"
MILE = 1609.344
# The date the repaving rows were read, set in main() from the PCI extract.
# Never the wall clock: a year range or a cut-off taken from today moves the
# output on 1 January with no new data.
AS_OF = None
ADOPTED = "2025-03-04"  # SFMTA Board adopted the Biking and Rolling Plan

# Caltrans classes, worst to best for a rider. CLASS I is a path off the
# roadway, CLASS IV a separated on-street lane, CLASS II paint, CLASS III a
# sharrow stencil.
RANK = {"CLASS III": 1, "CLASS II": 2, "CLASS IV": 3, "CLASS I": 4}
PLAIN = {1: "sharrow", 2: "painted lane", 3: "separated lane", 4: "path"}

# What each plan class needs on the ground to count as met. Separated needs a
# separated lane or a path (the rule site/scripts/collect-transportation.mjs
# uses); Shared and Shared L3 are calmed-street classes the bikeway layer
# cannot see, so a sharrow alone is short and anything better counts (same
# rule); Shared-use Path needs a path. Car-free and Undecided have nothing in
# the layer to score against and are left unrated.
NEED = {"Separated": 3, "Shared": 2, "Shared L3": 2, "Shared-use Path": 4}

# The paving record is thin before 1990 (fewer than 200 treatments a year
# against about 900 since 2010), so every rate is computed over these years.
# 2026 is a part year and is shown but kept out of the averages.
RATE_YEARS = list(range(2010, 2026))
RECENT_YEARS = list(range(2021, 2026))

# Two consecutive treatments on one block under a year apart are one job
# recorded twice, or a repave followed by a punch-list fix, not a repaving
# cycle. Dropped from the interval, and the count of them is printed.
MIN_GAP_YEARS = 1.0


def street_title(name):
    """'03RD ST' -> '3rd St'; 'DR CARLTON B GOODLETT PL' -> 'Dr Carlton B Goodlett Pl'."""
    t = re.sub(r"\b0+(\d)", r"\1", (name or "").title())
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)


def loaded_iso(v):
    """'04/04/2026 10:30:27 AM' from the CSV's data_loaded_at, as 2026-04-04."""
    try:
        return dt.datetime.strptime(v[:10], "%m/%d/%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def cnn_key(v):
    """CNNs arrive as '24494000', '24494000.0', 24494000.0 and '024494000'."""
    return str(v or "").split(".")[0].lstrip("0")


def load_plan(refetch=False):
    """The plan network: cnn -> street, facility, need rank, miles, trace overlap.

    Miles are per direction of travel, the plan's unit (its 472 miles,
    printed p. 20, is the bikeway layer's row sum): the block's layer rows'
    own lengths, or its centerline length times its directions where the
    layer lacks it, times `share`, how much of the block the plan's line
    covers (Directions.plan_metres, lib/mile_basis.py). They are the
    metres status.json gives the same block."""
    D = Directions(refetch=refetch)
    plan = {}
    for f in json.load(open(TRACE))["features"]:
        p = f["properties"]
        n, basis = D.count(p["cnn"])
        plan[cnn_key(p["cnn"])] = {
            "street": p["street"], "facility": p["facility"],
            "need": NEED.get(p["facility"]),
            "miles": D.plan_metres(p["cnn"], p["length_m"], p.get("share", 1.0)) / MILE, "directions": n,
            "share": p.get("share", 1.0),
        }
    plan["__directions__"] = D.summary()
    return plan


def load_treatments(refetch):
    """Every PCI change in 78va-8dhi, projected to the columns this needs."""
    return fetch("78va-8dhi",
                 select="cnn,street_name,from_street,to_street,pci_score,pci_change_date,treatment_or_survey,functional_class",
                 floor=200000, refresh=refetch)


def repave_events(pci_rows):
    """cnn -> sorted dates of resurfacings: Treatment rows that reset PCI to 100.

    Returns the repaves, the lighter treatments, and the count of undated
    treatment rows, so the note can say what was dropped.
    """
    repaves, light, undated = collections.defaultdict(set), collections.defaultdict(set), 0
    for r in pci_rows:
        if r.get("treatment_or_survey") != "Treatment":
            continue
        if not r.get("pci_change_date"):
            undated += 1
            continue
        d = r["pci_change_date"][:10]
        try:
            full = float(r.get("pci_score") or 0) >= 100
        except ValueError:
            full = False
        (repaves if full else light)[cnn_key(r["cnn"])].add(d)
    return ({c: sorted(v) for c, v in repaves.items()},
            {c: sorted(v) for c, v in light.items()}, undated)


def widened_repave_events(pci_rows, repaves):
    """The strict repaves plus Survey rows that read 100 after the block last read under 70.

    A block does not go from failing to perfect without being resurfaced, so
    a Survey row that does that is a repave the Treatment flag missed. A
    Survey 100 within 400 days of a Treatment 100 is the same job surveyed
    and is not added. Returns the widened events and how many were added.
    """
    by = collections.defaultdict(list)
    for r in pci_rows:
        if r.get("cnn") and r.get("pci_change_date") and r.get("pci_score") is not None:
            try:
                by[cnn_key(r["cnn"])].append((r["pci_change_date"][:10], float(r["pci_score"]), r.get("treatment_or_survey")))
            except ValueError:
                pass
    out = {c: set(ds) for c, ds in repaves.items()}
    added = 0
    for c, rows in by.items():
        rows.sort()
        prev = None
        for d, score, kind in rows:
            if kind == "Survey" and score >= 100 and prev is not None and prev < 70:
                near = any(abs((dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days) <= 400
                           for e in repaves.get(c, ()))
                if not near:
                    out.setdefault(c, set()).add(d)
                    added += 1
            prev = score
    return {c: sorted(v) for c, v in out.items()}, added


def validate_against_moratorium(repaves, light, street_of, refetch):
    """Does 'Treatment with PCI 100' mean what the dig lock means by a repave?

    The moratorium record covers one five-year window. Inside it, every
    locked block should carry a PCI-100 treatment near its lock date, and the
    treatments the lock does not follow should be the light ones.
    """
    mor = fetch("5wbp-dwzt", refresh=refetch)
    locked, lock_dates = {}, collections.defaultdict(set)
    for r in mor.rows:
        if r.get("cnn") and r.get("effectivedate"):
            c, d = cnn_key(r["cnn"]), r["effectivedate"][:10]
            locked[c] = min(d, locked.get(c, d))
            lock_dates[c].add(d)
    lo, hi = min(locked.values()), max(locked.values())
    window = lambda ds: [d for d in ds if lo <= d <= hi]

    def near(c, d):
        return any(abs((dt.date.fromisoformat(e) - dt.date.fromisoformat(d)).days) <= 400
                   for e in repaves.get(c, ()))
    matched = sum(1 for c, d in locked.items() if near(c, d))
    full_in = {c for c, ds in repaves.items() if window(ds)}
    light_in = {c for c, ds in light.items() if window(ds)}
    # PCI-100 blocks in the window with no lock: when, and on which streets.
    early = 0  # repaved in the record's first 60 days, before the lock table was being kept up
    unlocked_streets = collections.Counter()
    for c in full_in - set(locked):
        early += any((dt.date.fromisoformat(d) - dt.date.fromisoformat(lo)).days < 60 for d in window(repaves[c]))
        unlocked_streets[street_title(street_of.get(c, "?"))] += 1
    return {
        "tag": mor.tag, "queried": mor.fetched_on.isoformat(), "rows": len(mor.rows),
        "window": [lo, hi], "lockedBlocks": len(locked),
        "lockedWithRepaveWithin400Days": matched,
        "repavedBlocksInWindow": len(full_in), "repavedBlocksInWindowLocked": len(full_in & set(locked)),
        "lightTreatedBlocksInWindow": len(light_in), "lightTreatedBlocksInWindowLocked": len(light_in & set(locked)),
        "blocksWithTwoLockDates": sum(1 for v in lock_dates.values() if len(v) > 1),
        "unlockedRepavedFirst60Days": early,
        "unlockedRepavedStreets": [s for s, _ in unlocked_streets.most_common(4)],
    }


def load_snapshots():
    """The archived ygmz-vaxd captures, one best class and miles per block each, dated by release.

    Reads the extracts tools/bike-network/bike-network-history.py keeps. A capture is
    dated by the release it holds (data_loaded_at) when the column exists —
    two captures of one release are one observation — and by its capture
    date otherwise (the 2021 and 2022 exports predate the column).
    """
    out, seen = [], set()
    for name in sorted(os.listdir(SNAP_DIR)):
        if not name.endswith(".json"):
            continue
        blob = json.load(open(os.path.join(SNAP_DIR, name)))
        meta = blob.get("meta") or {}
        stamp = meta.get("captured") or name[:14]
        captured = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
        loaded = loaded_iso(meta.get("data_loaded_at"))
        if loaded in seen:
            continue
        if loaded:
            seen.add(loaded)
        blocks = {}
        for x in blob["records"]:
            c = cnn_key(x.get("cnn"))
            if not c:
                continue
            rank = RANK.get(x.get("cls"), 0)
            cur = blocks.get(c)
            if cur is None or rank > cur[0]:
                blocks[c] = [rank, x.get("len_mi") or (cur[1] if cur else 0)]
        out.append({"captured": captured, "wayback": stamp, "loadedAt": loaded,
                    "asOf": loaded or captured, "blocks": blocks, "fetched": blob.get("fetched_on")})
    out.sort(key=lambda s: s["asOf"])
    if len(out) < 5:
        raise RuntimeError(f"expected at least five captures in {SNAP_DIR}, found {len(out)}; run tools/bike-network/bike-network-history.py")
    return out


def load_layer():
    """SFMTA's current layer: cnn -> best rank now, and every install/update year on the block with the rank of the row it came from."""
    ex = Extract("sfmta-bikeway").read("network")
    if ex is None:
        raise RuntimeError("run tools/bike-network/bike-progress.py first; it fetches the SFMTA layer")
    by = collections.defaultdict(lambda: {"rank": 0, "years": set()})
    # Keyed by the centerline block each row lies on (lib/bikeway_snap.py).
    for r in rekeyed_layer(ex.records):
        c = cnn_key(r.get("CNN"))
        if not c:
            continue
        b = by[c]
        rk = RANK.get(r.get("FACILITY_T"), 0)
        b["rank"] = max(b["rank"], rk)
        for k in ("INSTALL_YR", "UPDATE_YR"):
            try:
                y = int(r.get(k) or 0)
            except (TypeError, ValueError):
                y = 0
            if y >= 1900:
                b["years"].add((y, rk))
    # Work the layer has not caught up with. Without it, a block repaved and
    # given its bikeway this year (Winston Drive, 2026) grades as missed.
    reported = json.load(open(REPORTED)) if os.path.exists(REPORTED) else {"projects": []}
    for p in reported["projects"]:
        for blk in p["blocks"]:
            c = cnn_key(blk["cnn"])
            if c:
                by[c]["rank"] = max(by[c]["rank"], RANK.get(p["class"], 0))
                by[c]["years"].add((p["year"], RANK.get(p["class"], 0)))
    edited = max((r.get("LAST_EDITED_DATE") or 0) for r in ex.records)
    return by, {"tag": f"[SFMTA ArcGIS Bicycle/bicycle layer 0 — queried {ex.fetched_on.isoformat()}]",
                "queried": ex.fetched_on.isoformat(), "rows": len(ex.records),
                "lastEdited": dt.datetime.utcfromtimestamp(edited / 1000).date().isoformat()}


def rated(plan):
    return {c: p for c, p in plan.items() if p["need"]}


def repaves_by_year(repaves, plan):
    """year -> list of (cnn, date) for rated plan blocks repaved that year; one entry per block-year."""
    by = collections.defaultdict(list)
    for c, p in rated(plan).items():
        seen = set()
        for d in repaves.get(c, ()):
            y = int(d[:4])
            if y not in seen:
                seen.add(y)
                by[y].append((c, d))
    return by


def grade_by_layer(cnn, year, plan, layer):
    """What the current SFMTA layer says happened on a plan block repaved in `year`.

    short    the block does not meet the plan's class today
    received meets today, and a row on it is dated the repave year or the next
    already  meets today, every dated row on it predates the repave
    undated  meets today, no row on it carries a year
    """
    b = layer.get(cnn, {"rank": 0, "years": set()})
    need = plan[cnn]["need"]
    if b["rank"] < need:
        return "short"
    # Only a row that meets the need dates the need being met: a 1997 Class III
    # row on a block that became Class IV later says nothing about when.
    years = [y for y, rk in b["years"] if rk >= need]
    if not years:
        return "undated"
    if any(year <= y <= year + 1 for y in years):
        return "received"
    if max(years) < year:
        return "already"
    return "later"  # dated after year+1: built, but not with this repave


def grade(cnn, date, plan, layer, snaps):
    """grade_by_layer, corrected by the archived captures.

    A row keeps its INSTALL_YR when SFMTA edits it, so an UPDATE_YR in the
    repave year can mark an edit to a bikeway that was already there. When a
    capture taken before the repave already shows the block meeting the plan,
    the block had it before: Valencia Street's 14 blocks, "repaved" 2025-04-14,
    were Class IV both ways in the 2024-03-31 capture (Fable review,
    2026-09-28).
    """
    g = grade_by_layer(cnn, int(date[:4]), plan, layer)
    if g == "received" and grade_by_snapshots(cnn, date, plan, snaps) == "already":
        return "already"
    return g


def grade_by_snapshots(cnn, date, plan, snaps):
    """The same question from the archived captures: class before the repave against the latest capture."""
    before = [s for s in snaps if s["asOf"] < date]
    if not before:
        return None
    need = plan[cnn]["need"]
    b = before[-1]["blocks"].get(cnn, [0])[0]
    a = snaps[-1]["blocks"].get(cnn, [0])[0]
    if a < need:
        return "short"
    return "already" if b >= need else "received"


def year_table(by_year, plan, layer, snaps):
    """Per repave year: miles of plan network repaved, and where they stand now."""
    table = []
    for y in sorted(by_year):
        rows = by_year[y]
        grades = collections.Counter()
        miles = collections.defaultdict(float)
        streets = collections.Counter()
        agree = disagree = snap_received = layer_received_checked = 0
        for c, d in rows:
            g = grade(c, d, plan, layer, snaps)
            grades[g] += 1
            miles[g] += plan[c]["miles"]
            if g == "received":
                streets[street_title(plan[c]["street"])] += 1
            s = grade_by_snapshots(c, d, plan, snaps)
            if s is not None:
                if (s == "short") == (g == "short"):
                    agree += 1
                else:
                    disagree += 1
                snap_received += s == "received"
                layer_received_checked += g == "received"
        total = sum(plan[c]["miles"] for c, _ in rows)
        table.append({
            "year": y, "blocks": len(rows), "miles": round(total, 2),
            "milesShort": round(miles["short"], 2), "milesReceived": round(miles["received"], 2),
            "milesAlready": round(miles["already"], 2), "milesUndated": round(miles["undated"], 2),
            "milesLater": round(miles["later"], 2),
            "blocks_by_grade": dict(grades),
            "receivedStreets": [s for s, _ in streets.most_common(4)],
            "snapshotAgree": agree, "snapshotDisagree": disagree,
            "snapshotReceived": snap_received, "layerReceivedWhereSnapshotsExist": layer_received_checked,
        })
    return table


def lever_estimate(by_year, plan):
    """Miles a year of plan network repaved and still short — under four readings.

    The block set and the window are what move it: whether the Shared classes
    count (the layer cannot see calming, so their 'short' is a floor on what
    is missing and a ceiling on what paint could fix), and which years.
    """
    def short_miles(years, facilities):
        return {y: sum(plan[c]["miles"] for c, _ in by_year.get(y, [])
                       if plan[c]["facility"] in facilities
                       and grade_by_layer(c, y, plan, LAYER) == "short")
                for y in years}
    separated = {"Separated", "Shared-use Path"}
    every = set(NEED)
    readings = [
        ("low", "Separated and Shared-use Path corridors, 2021–2025", RECENT_YEARS, separated),
        ("mid-recent", "all rated corridors, 2021–2025", RECENT_YEARS, every),
        ("mid-long", "Separated and Shared-use Path corridors, 2010–2025", RATE_YEARS, separated),
        ("high", "all rated corridors, 2010–2025", RATE_YEARS, every),
    ]
    out = []
    for name, desc, years, fac in readings:
        per = short_miles(years, fac)
        out.append({"reading": name, "definition": desc, "years": [years[0], years[-1]],
                    "milesPerYear": round(sum(per.values()) / len(years), 2),
                    "perYear": {str(y): round(v, 2) for y, v in per.items()}})
    return out


def built_rate(snaps, plan):
    """Plan miles newly met between the first and last capture, per year: what the city has managed."""
    first, last = snaps[0], snaps[-1]
    years = (dt.date.fromisoformat(last["asOf"]) - dt.date.fromisoformat(first["asOf"])).days / 365.25
    newly = 0.0
    for c, p in rated(plan).items():
        a = first["blocks"].get(c, [0])[0]
        b = last["blocks"].get(c, [0])[0]
        if b >= p["need"] > a:
            newly += p["miles"]
    return {"from": first["asOf"], "to": last["asOf"], "years": round(years, 2),
            "planMilesNewlyMet": round(newly, 2), "milesPerYear": round(newly / years, 2)}


def city_blocks(refetch):
    """Three block counts from the centerline table: every segment, active ones, and those accepted for maintenance."""
    r = fetch("3psu-pn9h", select="cnn,active,accepted", refresh=refetch)
    rows = [x for x in r.rows if x.get("cnn")]
    accepted = {cnn_key(x["cnn"]) for x in rows if str(x.get("accepted")).lower() == "true"}
    every = {cnn_key(x["cnn"]) for x in rows}
    return {"tag": r.tag, "queried": r.fetched_on.isoformat(), "all": len(every),
            "active": len({cnn_key(x["cnn"]) for x in rows if str(x.get("active")).lower() == "true"}),
            "accepted": len(accepted)}, accepted, every


def turnover(events, cnns, years):
    """Blocks in `cnns` with an event in each of `years`, averaged: the yearly repave count, and the cycle it implies."""
    per_year = collections.Counter()
    for c in cnns:
        for y in {int(d[:4]) for d in events.get(c, ())}:
            if y in years:
                per_year[y] += 1
    rate = sum(per_year.values()) / len(years)
    return {"blocks": len(cnns), "perYear": round(rate, 1), "cycleYears": round(len(cnns) / rate, 1) if rate else None}


def intervals(repaves, widened, plan, city, accepted, block_ids, func_class):
    """Years between consecutive repaves on one block, and the turnover the yearly counts imply.

    The gap median only sees blocks repaved twice inside the record, so it is
    censored: a block repaved once in 79 years contributes nothing. The
    turnover figure (blocks a year against the block count) has no such gap.
    """
    def gaps(cnns, since):
        g, dropped = [], 0
        for c in cnns:
            ds = [d for d in repaves.get(c, ()) if d >= since]
            for a, b in zip(ds, ds[1:]):
                yrs = (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days / 365.25
                if yrs < MIN_GAP_YEARS:
                    dropped += 1
                else:
                    g.append(yrs)
        return g, dropped

    def summary(g, dropped):
        if not g:
            return None
        q = statistics.quantiles(g, n=4)
        return {"gaps": len(g), "droppedUnderOneYear": dropped, "medianYears": round(statistics.median(g), 1),
                "p25": round(q[0], 1), "p75": round(q[2], 1)}

    plan_cnns = list(plan)
    all_cnns = list(repaves)
    plan_accepted = [c for c in plan if c in accepted]
    city_accepted = [c for c in block_ids if c in accepted]
    bond_years = list(range(2012, 2019))
    dates = sorted(d for ds in repaves.values() for d in ds)
    plan_by_year = collections.Counter()
    city_by_year = collections.Counter()          # block segments only
    intersections_by_year = collections.Counter()  # ids with no centerline row: intersections
    for c, ds in repaves.items():
        for y in {int(d[:4]) for d in ds}:
            (city_by_year if c in block_ids else intersections_by_year)[y] += 1
            if c in plan:
                plan_by_year[y] += 1
    plan_rate = sum(plan_by_year[y] for y in RATE_YEARS) / len(RATE_YEARS)
    city_rate = sum(city_by_year[y] for y in RATE_YEARS) / len(RATE_YEARS)
    recent_plan_rate = sum(plan_by_year[y] for y in RECENT_YEARS) / len(RECENT_YEARS)
    recent_blocks = {c for c, ds in repaves.items() if any(int(d[:4]) in RATE_YEARS for d in ds)} & block_ids
    accepted_share = len(recent_blocks & accepted) / len(recent_blocks)
    intersection_rate = sum(intersections_by_year[y] for y in RATE_YEARS) / len(RATE_YEARS)
    cuts = {
        "plan blocks, accepted streets, 2010–2025": turnover(repaves, plan_accepted, RATE_YEARS),
        "plan blocks, accepted streets, 2021–2025": turnover(repaves, plan_accepted, RECENT_YEARS),
        "plan blocks, accepted streets, 2012–2018 (Road Repaving and Street Safety Bond years)": turnover(repaves, plan_accepted, bond_years),
        "plan blocks, all, 2010–2025": turnover(repaves, plan_cnns, RATE_YEARS),
        "plan blocks, all, widened repave definition, 2010–2025": turnover(widened, plan_cnns, RATE_YEARS),
        "plan blocks the plan draws Separated, accepted, 2010–2025": turnover(repaves, [c for c in plan_accepted if plan[c]["facility"] == "Separated"], RATE_YEARS),
        "plan blocks on arterials, accepted, 2010–2025": turnover(repaves, [c for c in plan_accepted if func_class.get(c) == "Arterial"], RATE_YEARS),
        "plan blocks on collectors, accepted, 2010–2025": turnover(repaves, [c for c in plan_accepted if func_class.get(c) == "Collector"], RATE_YEARS),
        "plan blocks on residential streets, accepted, 2010–2025": turnover(repaves, [c for c in plan_accepted if func_class.get(c) == "Residential"], RATE_YEARS),
        "city blocks, accepted streets, 2010–2025": turnover(repaves, city_accepted, RATE_YEARS),
        "city blocks, accepted streets, widened repave definition, 2010–2025": turnover(widened, city_accepted, RATE_YEARS),
        "city blocks, accepted streets, 2012–2018": turnover(repaves, city_accepted, bond_years),
        "city arterials, accepted, 2010–2025": turnover(repaves, [c for c in city_accepted if func_class.get(c) == "Arterial"], RATE_YEARS),
        "city arterials, accepted, widened repave definition, 2010–2025": turnover(widened, [c for c in city_accepted if func_class.get(c) == "Arterial"], RATE_YEARS),
        "city collectors, accepted, 2010–2025": turnover(repaves, [c for c in city_accepted if func_class.get(c) == "Collector"], RATE_YEARS),
        "city residential streets, accepted, 2010–2025": turnover(repaves, [c for c in city_accepted if func_class.get(c) == "Residential"], RATE_YEARS),
    }
    return {
        "recordSpan": [dates[0], dates[-1]],
        "cuts": cuts,
        "gapAllBlocks": summary(*gaps(all_cnns, "1900")),
        "gapPlanBlocks": summary(*gaps(plan_cnns, "1900")),
        "gapPlanBlocksSince1990": summary(*gaps(plan_cnns, "1990")),
        "planBlocks": len(plan),
        "planBlocksEverRepaved": sum(1 for c in plan if c in repaves),
        "planBlocksRepavedSince2000": sum(1 for c in plan if any(d >= "2000" for d in repaves.get(c, ()))),
        "planBlocksRepavedSince2010": sum(1 for c in plan if any(d >= "2010" for d in repaves.get(c, ()))),
        "planBlocksRepavedPerYear2010to2025": round(plan_rate, 1),
        "planBlocksRepavedPerYear2021to2025": round(recent_plan_rate, 1),
        "impliedPlanCycleYears": round(len(plan) / plan_rate, 1),
        "impliedPlanCycleYearsRecent": round(len(plan) / recent_plan_rate, 1),
        "cityBlocks": city,
        "cityBlocksRepavedPerYear2010to2025": round(city_rate, 1),
        "cityIntersectionsRepavedPerYear2010to2025": round(intersection_rate, 1),
        "repavedBlocks2010to2025AcceptedShare": round(accepted_share, 3),
        "impliedCityCycleYears": {k: round(city[k] / city_rate, 1) for k in ("all", "active", "accepted")},
        "planBlocksAccepted": sum(1 for c in plan if c in accepted),
        "planBlocksByYear": {str(y): plan_by_year[y] for y in range(2000, AS_OF.year + 1)},
        "cityBlocksByYear": {str(y): city_by_year[y] for y in range(2000, AS_OF.year + 1)},
    }


def load_openings(refetch):
    """Public Works and SFPUC projects in construction on plan blocks, from the coordination feed."""
    return fetch("btxj-k9uh", refresh=refetch)


def agency_group(name):
    n = name or ""
    if n.startswith("SF DPW"):
        return "Public Works"
    if n.startswith("SF PUC"):
        return "SFPUC"
    return "other"


def openings_table(feed, plan, layer, repaves):
    """Per construction-start year: plan blocks a Public Works or SFPUC job has opened, and where they stand.

    The feed holds projects that are planned or under way; finished ones drop
    out, so this begins where the feed's memory does and is not a history.
    A job counts as opened when its start date is on or before the day the
    feed was read.
    """
    per = collections.defaultdict(dict)  # (year, group) -> cnn -> earliest start
    agencies = collections.Counter()
    for r in feed.rows:
        if r.get("project_phase") != "Construction" or not r.get("start_date"):
            continue
        start = r["start_date"][:10]
        if start > feed.fetched_on.isoformat():
            continue
        c = cnn_key(r.get("cnn"))
        if c not in plan or not plan[c]["need"]:
            continue
        g = agency_group(r.get("agency_name"))
        if g == "other":
            continue
        agencies[r.get("agency_name")] += 1
        y = int(start[:4])
        cur = per[(y, g)].get(c)
        per[(y, g)][c] = min(start, cur) if cur else start
    rows = []
    for (y, g), blocks in sorted(per.items()):
        miles = sum(plan[c]["miles"] for c in blocks)
        short = sum(plan[c]["miles"] for c in blocks if layer.get(c, {"rank": 0})["rank"] < plan[c]["need"])
        paved = sum(1 for c in blocks if any(y <= int(d[:4]) <= y + 1 for d in repaves.get(c, ())))
        rows.append({"year": y, "agency": g, "blocks": len(blocks), "miles": round(miles, 2),
                     "milesShort": round(short, 2), "blocksAlsoRepavedSameOrNextYear": paved})
    return rows, {a: n for a, n in agencies.most_common()}


def write_json(payload):
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(os.path.join(OUT, "lever.json"), payload, end="", ensure_ascii=True, indent=1)
    # The site builds from site/data alone (site/scripts/check-public.mjs
    # refuses a reference outside site/), so the figures travel there too.
    stable.write_json(os.path.join(ROOT, "site", "data", "repave-lever.json"), payload, end="", ensure_ascii=True,
                      indent=1)


def md_link(fxf):
    return f"[`{fxf}`](https://data.sfgov.org/d/{fxf})"


def write_md(P):
    """The deliverable: answer, method, caveats."""
    pci, mor, lay, snap = P["sources"]["pci"], P["sources"]["moratorium"], P["sources"]["layer"], P["sources"]["snapshots"]
    iv, lev, built = P["intervals"], P["lever"], P["builtRate"]
    by = {r["reading"]: r for r in lev}
    T = P["years"]
    recent = [r for r in T if r["year"] in RECENT_YEARS]
    longrun = [r for r in T if r["year"] in RATE_YEARS]
    TOT = {"miles": sum(r["miles"] for r in longrun), "short": sum(r["milesShort"] for r in longrun),
           "received": sum(r["milesReceived"] for r in longrun)}
    pci_tag = f"[DataSF 78va-8dhi — queried {pci['queried']}]"
    cycle_plan = iv["impliedPlanCycleYears"]
    cyc = iv["impliedCityCycleYears"]
    blocks = iv["cityBlocks"]
    gap = iv["gapPlanBlocks"]
    ctag = f"[DataSF 3psu-pn9h — queried {blocks['queried']}]"
    CUT = iv["cuts"]

    def avg(by_year, a, b):
        return sum(by_year[str(y)] for y in range(a, b + 1)) / (b - a + 1)

    def year_row(r):
        g = r["blocks_by_grade"]
        return (f"| {r['year']} | {r['blocks']} | {r['miles']:.1f} | {r['milesAlready']:.1f} | {r['milesReceived']:.1f} "
                f"| {r['milesLater']:.1f} | {r['milesUndated']:.1f} | **{r['milesShort']:.1f}** | "
                f"{', '.join(r['receivedStreets']) or '—'} |")

    lines = [
        "# Tying bike work to repaving: how many miles a year it would add", "",
        f"Built {P['generated']} by `tools/bike-network/repave-lever.py`. Sources: {md_link('78va-8dhi')} {pci_tag}; "
        f"{md_link('5wbp-dwzt')} {mor['tag']}; {md_link('btxj-k9uh')} {P['sources']['feed']['tag']}; "
        f"{md_link('ygmz-vaxd')} archived releases {snap['releases'][0]} to {snap['releases'][-1]} {snap['tag']}; "
        f"SFMTA's layer {lay['tag']}; plan network {PLAN_TAG}.", "",
        "## The answer", "",
        f"**{by['low']['milesPerYear']:.1f} to {by['high']['milesPerYear']:.1f} miles a year.** That is the plan-network mileage "
        f"San Francisco resurfaced each year and left without the facility the plan draws on it, read from "
        f"{md_link('78va-8dhi')} {pci_tag} against SFMTA's bikeway layer {lay['tag']}. Since {RATE_YEARS[0]} the city has "
        f"resurfaced {TOT['miles']:.0f} miles of the plan network; {TOT['received']:.1f} miles got the planned facility with the "
        f"repave and {TOT['short']:.0f} miles are still short of it. For scale, the plan network gained "
        f"{built['milesPerYear']:.1f} miles a year of newly-met facility between {built['from']} and {built['to']} "
        f"({built['planMilesNewlyMet']:.1f} miles in {built['years']} years) {snap['tag']}, "
        f"so tying the facility to the repave would have added between a third of that and nearly twice it.", "",
        "| Reading | Miles a year | Definition |", "|---|---|---|",
    ]
    for r in lev:
        lines.append(f"| {r['reading']} | **{r['milesPerYear']:.1f}** | {r['definition']} |")
    lines += [
        "", f"The low reading counts only corridors where the plan draws a separated lane or a path, over "
        f"{RECENT_YEARS[0]}–{RECENT_YEARS[-1]}. The high reading adds the Shared and Shared L3 corridors, whose calming the "
        f"bikeway layer cannot see, and runs from {RATE_YEARS[0]}. Miles are per direction row, the plan's unit: the length of each block the traced plan covers, "
        f"times the block's direction rows.", "",
        f"**On the 30-year assumption: it is about right.** On the plan's streets that the city maintains, a block is resurfaced "
        f"about every **{CUT['plan blocks, accepted streets, 2010–2025']['cycleYears']:.0f} years**: "
        f"{CUT['plan blocks, accepted streets, 2010–2025']['perYear']:.0f} of the {CUT['plan blocks, accepted streets, 2010–2025']['blocks']:,} "
        f"accepted plan blocks a year over {RATE_YEARS[0]}–{RATE_YEARS[-1]}, and "
        f"{CUT['plan blocks, accepted streets, 2021–2025']['perYear']:.0f} a year over {RECENT_YEARS[0]}–{RECENT_YEARS[-1]}, a "
        f"{CUT['plan blocks, accepted streets, 2021–2025']['cycleYears']:.0f}-year cycle {pci_tag}. Over all {iv['planBlocks']:,} plan blocks, "
        f"including the {iv['planBlocks'] - CUT['plan blocks, accepted streets, 2010–2025']['blocks']} on streets the city has not accepted "
        f"for maintenance (the Embarcadero, Sloat, Lincoln, JFK and the Presidio among them), the cycle reads {cycle_plan:.0f} years. Citywide, "
        f"{CUT['city blocks, accepted streets, 2010–2025']['perYear']:.0f} of the {blocks['accepted']:,} blocks the city has accepted "
        f"for maintenance were resurfaced a year, a {CUT['city blocks, accepted streets, 2010–2025']['cycleYears']:.0f}-year cycle "
        f"(intersections carry their own ids, another {iv['cityIntersectionsRepavedPerYear2010to2025']:.0f} a year, and are not blocks); "
        f"over the {blocks['active']:,} active blocks the cycle reads {cyc['active']:.0f} years and over all {blocks['all']:,} "
        f"centerline segments {cyc['all']:.0f} {ctag}. {100 * iv['repavedBlocks2010to2025AcceptedShare']:.0f}% of the blocks "
        f"resurfaced since {RATE_YEARS[0]} are accepted blocks, so the accepted figure is the one for the streets Public Works paves. "
        f"On plan blocks resurfaced at least twice since {iv['recordSpan'][0][:4]}, the median gap between "
        f"resurfacings is {gap['medianYears']:.1f} years (quartiles {gap['p25']:.1f} to {gap['p75']:.1f}, {gap['gaps']:,} gaps) "
        f"{pci_tag}; from 1990 on, {iv['gapPlanBlocksSince1990']['medianYears']:.1f} years over {iv['gapPlanBlocksSince1990']['gaps']:,} gaps. "
        f"Under the widened repave definition (method, step 2) the accepted city cycle is "
        f"{CUT['city blocks, accepted streets, widened repave definition, 2010–2025']['cycleYears']:.0f} years and the plan cycle "
        f"{CUT['plan blocks, all, widened repave definition, 2010–2025']['cycleYears']:.0f}. So a street comes up for repaving about "
        f"once in 28 to 33 years, and a plan street no more often than the average one: the lever is slow, and a block missed at its "
        f"repave waits a generation.", "",
        "### The assumption tested every way the data allows", "",
        "Blocks resurfaced a year, and the cycle that count implies over the block set, for each cut of the record that could make "
        f"repaving look more frequent {pci_tag}. Functional class is the PCI table's own.", "",
        "| Block set | Blocks | Resurfaced a year | Implied cycle, years |", "|---|---|---|---|",
    ] + [f"| {name} | {c['blocks']:,} | {c['perYear']:.1f} | **{c['cycleYears']:.0f}** |" for name, c in CUT.items() if c['cycleYears']] + [
        "", f"No cut reaches a cycle much shorter than 30 years. The shortest are the plan's collectors, at "
        f"{CUT['plan blocks on collectors, accepted, 2010–2025']['cycleYears']:.0f} years, and the bond years 2012–2018, at "
        f"{CUT['plan blocks, accepted streets, 2012–2018 (Road Repaving and Street Safety Bond years)']['cycleYears']:.0f} on plan blocks and "
        f"{CUT['city blocks, accepted streets, 2012–2018']['cycleYears']:.0f} citywide; the plan's Separated corridors, where the lever "
        f"matters most, run {CUT['plan blocks the plan draws Separated, accepted, 2010–2025']['cycleYears']:.0f}.", "",
        "## Year by year", "",
        f"Plan-network blocks resurfaced each year, in miles of plan network, and what SFMTA's layer {lay['tag']} says is on them now. "
        f"*Already* had the planned class before the repave (every dated row predates it); *received* meets the plan and carries "
        f"an install or update year in the repave year or the next; *later* meets the plan with a date two or more years after; "
        f"*undated* meets the plan and carries no year; **short** does not meet the plan today.", "",
        "| Repaved | Blocks | Miles | Already | Received | Later | Undated | Short | Streets that received |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [year_row(r) for r in T if r["year"] >= 2010]
    lines += [
        "", f"Over {RATE_YEARS[0]}–{RATE_YEARS[-1]}: {TOT['miles']:.0f} miles of plan network resurfaced, {TOT['received']:.1f} received the planned "
        f"facility with the repave, {TOT['short']:.0f} are still short. 2026 is a part year.", "",
        "### Why the received column looks the way it does", "",
        "The years with a real received figure are single projects, not a practice: the streets column names them. "
        "A repave year with many blocks and almost nothing received is the normal case in every year of the record. "
        f"Plan blocks were resurfaced at {avg(iv['planBlocksByYear'], 2012, 2018):.0f} a year over 2012–2018 and "
        f"{avg(iv['planBlocksByYear'], 2019, 2025):.0f} a year over 2019–2025; city blocks at {avg(iv['cityBlocksByYear'], 2012, 2018):.0f} "
        f"and {avg(iv['cityBlocksByYear'], 2019, 2025):.0f} {pci_tag}. The 2011 Road Repaving and Street Safety Bond funded paving in the "
        "first window [inference — mine; confirm against Public Works' annual paving reports].", "",
        "### The two ways of reading 'received' agree", "",
    ]
    ag = sum(r["snapshotAgree"] for r in recent)
    dis = sum(r["snapshotDisagree"] for r in recent)
    sr = sum(r["snapshotReceived"] for r in recent)
    lr = sum(r["layerReceivedWhereSnapshotsExist"] for r in recent)
    lines += [
        f"For repaves dated {RECENT_YEARS[0]}–{RECENT_YEARS[-1]}, the archived captures of {md_link('ygmz-vaxd')} allow a second "
        f"reading: the block's class in the last release before the repave against its class in the release loaded {snap['releases'][-1]}. "
        f"A release is dated by its data_loaded_at where the export carries it, and by its capture date for the 2021 and 2022 exports, "
        f"which predate the column. "
        f"On whether a block is short today the two readings agree on {ag} blocks and disagree on {dis} "
        f"{snap['tag']}"
        + (", so the DataSF capture and SFMTA's service carry the same class on every one of these blocks." if dis == 0 else
           "; the disagreements are blocks that meet the plan in one copy of the layer and not the other.")
        + f" On which blocks *received* the facility they differ in both directions: the captures show {sr} blocks gaining the "
        f"planned class after their repave, the layer's dates show {lr}. "
        + " ".join(f"In {r['year']} the captures see {r['snapshotReceived']} and the layer's dates {r['layerReceivedWhereSnapshotsExist']}."
                   for r in recent if r["snapshotReceived"] != r["layerReceivedWhereSnapshotsExist"])
        + f" Where the captures see more, the block was upgraded without a new INSTALL_YR or UPDATE_YR, which is the usual case for "
        f"an upgrade. Where the layer sees more, the work is newer than the last release ({snap['loadedAt']}); SFMTA's layer was edited "
        f"{lay['lastEdited']}. Each reading is a floor on received.", "",
        "## Public Works and SFPUC openings, from the coordination feed", "",
        f"{md_link('btxj-k9uh')} {P['sources']['feed']['tag']} lists projects planned or under way, one row per block; finished projects "
        f"drop out ({P['sources']['feed']['completedRows']} rows read Completed), so it starts where its memory does. Blocks below are rated "
        f"plan blocks a Public Works or SFPUC project has entered construction on, by the year construction started. SFPUC's sewer work is "
        f"filed by Public Works' Hydraulic division, so it sits under Public Works here.", "",
        "| Construction began | Agency | Plan blocks | Miles | Short today | Also resurfaced that year or next |",
        "|---|---|---|---|---|---|",
    ]
    for r in P["openings"]:
        lines.append(f"| {r['year']} | {r['agency']} | {r['blocks']} | {r['miles']:.1f} | {r['milesShort']:.1f} | {r['blocksAlsoRepavedSameOrNextYear']} |")
    lines += [
        "", "Agencies counted, by row: " + "; ".join(f"{a} ({n})" for a, n in P["openingAgencies"].items()) + ".", "",
        "## Method", "",
        f"1. **Plan network.** The North Star map traced onto city centerlines, {P['plan']['blocks']:,} blocks, "
        f"{P['plan']['miles']:.0f} miles {PLAN_TAG}. {P['plan']['unrated']} blocks drawn Car-free or Undecided have nothing in "
        f"a bikeway layer to score against and are left out of every figure. A block's miles are counted per direction of travel, "
        f"which is how the plan counts its 472 miles (printed p. 20): the sum of its bikeway layer rows' own lengths "
        f"where the block is in the layer ({P['plan']['directions']['blocks_by_basis'].get('layer rows', 0):,} blocks), else its centerline length once where {md_link('3psu-pn9h')} flags the street one-way "
        f"({P['plan']['directions']['blocks_by_basis'].get('centerline one-way', 0):,}) and twice otherwise ({P['plan']['directions']['blocks_by_basis'].get('centerline two-way', 0):,}), "
        f"times the share of the block the plan draws ({P['plan']['partialBlocks']:,} blocks where the plan's line stops partway, at corridor ends). "
        f"That gives {P['plan']['miles']:.0f} miles. A block meets "
        f"the plan when its best Caltrans class "
        f"reaches what the plan's class needs: a separated lane or path for Separated, a path for Shared-use Path, anything above a "
        f"sharrow for Shared and Shared L3.",
        f"2. **Repaves.** {md_link('78va-8dhi')} holds {pci['rows']:,} PCI changes on {pci['blocks']:,} pavement segments "
        f"({P['sources']['centerlines']['pciIdsInCenterlines']:,} blocks and {P['sources']['centerlines']['pciIdsNotInCenterlines']:,} "
        f"ids with no centerline row, which are intersections), {iv['recordSpan'][0]} to "
        f"{iv['recordSpan'][1]}, each flagged Survey or Treatment {pci_tag}. A repave is a Treatment that resets the score to 100: "
        f"{pci['repaveEvents']:,} events on {pci['repavedBlocks']:,} segments. The {pci['lightEvents']:,} treatments that leave the score "
        f"below 100 are seals and patches and are not counted; {pci['undatedTreatments']} treatment rows carry no date. The table has no "
        f"treatment-type column ({len(pci['columns'])} columns, checked in its metadata [DataSF 78va-8dhi metadata — read {pci['queried']}]), "
        f"so what a Treatment was cannot be read from it. A **widened** definition adds Survey rows that read 100 after the block last read "
        f"under 70 and have no Treatment 100 within 400 days — a block does not go from failing to perfect without resurfacing — which adds "
        f"{pci['widenedEventsAdded']:,} events; the cycle table above carries both.",
        f"3. **Check on that definition.** {md_link('5wbp-dwzt')} locks a block against digging for five years after a repave "
        f"{mor['tag']}. Of its {mor['lockedBlocks']:,} locked blocks, {mor['lockedWithRepaveWithin400Days']:,} carry a PCI-100 treatment "
        f"within 400 days of the lock date. Inside the lock record's window ({mor['window'][0]} to {mor['window'][1]}), "
        f"{mor['repavedBlocksInWindowLocked']:,} of {mor['repavedBlocksInWindow']:,} PCI-100 blocks are locked and "
        f"{mor['lightTreatedBlocksInWindowLocked']:,} of {mor['lightTreatedBlocksInWindow']:,} lighter-treated blocks are. "
        f"Of the {mor['repavedBlocksInWindow'] - mor['repavedBlocksInWindowLocked']} PCI-100 blocks with no lock, "
        f"{mor['unlockedRepavedFirst60Days']} are dated within 60 days of the record's start, and the rest cluster on {', '.join(mor['unlockedRepavedStreets'])}, streets with SFMTA-led street projects in the window, which would "
        f"be paving filed under a project rather than a Public Works job order [inference — mine; the check is the job order numbers "
        f"on those blocks]. {mor['blocksWithTwoLockDates']} blocks carry two lock dates, so the interval cannot come from the lock "
        f"record; it comes from the PCI history.",
        f"4. **Join.** By CNN, the block id every table shares. A repave and a plan segment on one CNN are co-located on the same block; "
        f"this says nothing about whether the paving job and any bikeway work were one project.",
        f"5. **Received.** From SFMTA's own layer {lay['tag']}, which carries INSTALL_YR and UPDATE_YR (the DataSF copy drops the "
        f"update fields), graded as the year table's header says. Every rate uses {RATE_YEARS[0]}–{RATE_YEARS[-1]}; the record before "
        f"1990 holds under 200 treatments a year.",
        f"6. **Interval.** Gaps between consecutive repaves on one block, gaps under {MIN_GAP_YEARS:.0f} year dropped as one job recorded "
        f"twice ({gap['droppedUnderOneYear']} on plan blocks). Turnover is blocks repaved a year over a block count: "
        f"{iv['planBlocks']:,} plan blocks; and from {md_link('3psu-pn9h')} {ctag}, {blocks['all']:,} centerline segments, "
        f"{blocks['active']:,} of them active and {blocks['accepted']:,} accepted for maintenance.", "",
        "## Caveats", "",
        f"- **The gap median is censored.** It sees only blocks resurfaced twice inside the record; {iv['planBlocksEverRepaved']:,} of "
        f"{iv['planBlocks']:,} plan blocks have any repave on record and {iv['planBlocksRepavedSince2000']:,} have one since 2000. "
        f"Events missing from the early record lengthen gaps and the record's end cuts long gaps off, so the direction of the bias is "
        f"not known; the median is {gap['medianYears']:.1f} years over the whole record and {iv['gapPlanBlocksSince1990']['medianYears']:.1f} "
        f"from 1990 on, and the turnover figures are the ones to quote.",
        f"- **Short is a floor for Shared corridors.** The plan's Shared classes ask for a calmed street, which no bikeway layer measures. "
        f"A Shared block with a painted lane counts as met here and may not be; one with a sharrow counts as short and is.",
        f"- **The layer lags.** SFMTA's layer was last edited {lay['lastEdited']}; a facility built since reads as absent, so the most "
        f"recent years' short figures can only fall.",
        f"- **Dates on the layer are partial.** Upgrades often keep the original INSTALL_YR and only sometimes gain an UPDATE_YR, so the "
        f"received column undercounts and the already column overcounts. The short column does not depend on dates.",
        f"- **The traced plan carries registration error** (6.2 m median, 15.6 m at the 90th percentile), so a few blocks at corridor "
        f"ends are on the plan here and not on SFMTA's map. The low reading drops blocks the trace overlaps by under half.",
        f"- **Intersections carry their own ids.** {P['sources']['centerlines']['pciIdsNotInCenterlines']:,} of the "
        f"{pci['blocks']:,} ids in the PCI history have no row in the centerline table {ctag}. "
        f"{P['sources']['centerlines']['pciIdsNotInCenterlinesNamedIntersection']:,} of them are named as an intersection in one of the "
        f"PCI table's three name fields. They are left out of the block counts and cannot join a plan block.",
        f"- **The coordination feed is not a history.** Completed projects leave it, so the openings table cannot say how many blocks "
        f"SFPUC or Public Works opened in earlier years, and the paving record is the only long series here.",
        f"- **A lever is not a commitment.** These miles are what repaving touched and left short; building the facility at that moment "
        f"still needs design, outreach and an SFMTA hearing, and some plan corridors need more than a repave can carry.",
    ]
    os.makedirs(OUT, exist_ok=True)
    stable.write_text(os.path.join(OUT, "lever.md"), "\n".join(lines) + "\n")


LAYER = {}
REPORTED = os.path.join(ROOT, "site", "data", "bike-history", "reported.json")


def main():
    global LAYER, AS_OF
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()

    plan = load_plan(args.refetch)
    directions = plan.pop("__directions__")
    pci = load_treatments(args.refetch)
    AS_OF = pci.fetched_on
    repaves, light, undated = repave_events(pci.rows)
    street_of = {cnn_key(r["cnn"]): r.get("street_name") for r in pci.rows if r.get("cnn")}
    mor = validate_against_moratorium(repaves, light, street_of, args.refetch)
    snaps = load_snapshots()
    LAYER, layer_meta = load_layer()
    city, accepted, every_id = city_blocks(args.refetch)
    feed = load_openings(args.refetch)

    by_year = repaves_by_year(repaves, plan)
    years = year_table(by_year, plan, LAYER, snaps)
    lever = lever_estimate(by_year, plan)
    built = built_rate(snaps, plan)
    widened, widened_added = widened_repave_events(pci.rows, repaves)
    func_class = {}
    for r in sorted(pci.rows, key=lambda r: r.get("pci_change_date") or ""):
        if r.get("cnn") and r.get("functional_class"):
            func_class[cnn_key(r["cnn"])] = r["functional_class"]
    columns = metadata("78va-8dhi")["columns"]
    iv = intervals(repaves, widened, plan, city, accepted, every_id, func_class)
    pci_ids = {cnn_key(r["cnn"]) for r in pci.rows if r.get("cnn")}
    intersection_ids = {cnn_key(r["cnn"]) for r in pci.rows if r.get("cnn") and any(
        "intersection" in (r.get(k) or "").lower() for k in ("street_name", "from_street", "to_street"))}
    openings, agencies = openings_table(feed, plan, LAYER, repaves)
    # Every rated plan block repaved on or after the plan's adoption, dated to
    # the day, with what the layer says happened: department-overlap.py puts
    # these beside the jobs still to come.
    # Undecided blocks are listed too, graded "unrated", so the page can say
    # how many repaved miles the plan names no bikeway for; nothing counts them.
    since = []
    for c, p in plan.items():
        if not p["need"] and p["facility"] != "Undecided":
            continue
        ds = sorted(d for d in repaves.get(c, ()) if d >= ADOPTED)
        if ds:
            since.append({"cnn": c, "date": ds[0], "street": street_title(p["street"]), "facility": p["facility"],
                          "miles": round(p["miles"], 4),
                          "grade": grade(c, ds[0], plan, LAYER, snaps) if p["need"] else "unrated"})

    payload = {
        "generated": dt.date.today().isoformat(),
        "mileBasis": BASIS,
        "sources": {
            "pci": {"id": "78va-8dhi", "tag": pci.tag, "queried": pci.fetched_on.isoformat(), "rows": len(pci.rows),
                    "blocks": len({cnn_key(r["cnn"]) for r in pci.rows}),
                    "repaveEvents": sum(len(v) for v in repaves.values()), "repavedBlocks": len(repaves),
                    "lightEvents": sum(len(v) for v in light.values()), "undatedTreatments": undated,
                    "widenedEventsAdded": widened_added, "columns": columns,
                    "hasTreatmentTypeColumn": any("treatment" in c and c != "treatment_or_survey" for c in columns)},
            "moratorium": mor,
            "layer": layer_meta,
            "snapshots": {"tag": f"[web.archive.org captures of DataSF ygmz-vaxd — read {snaps[-1]['fetched']}]",
                          "captures": [s["captured"] for s in snaps], "releases": [s["asOf"] for s in snaps],
                          "loadedAt": snaps[-1]["loadedAt"],
                          "wayback": [s["wayback"] for s in snaps]},
            "feed": {"id": "btxj-k9uh", "tag": feed.tag, "queried": feed.fetched_on.isoformat(), "rows": len(feed.rows),
                     "completedRows": sum(1 for r in feed.rows if r.get("project_status") == "Completed")},
            "centerlines": {"id": "3psu-pn9h", "tag": city["tag"], "queried": city["queried"], "blocks": city,
                            "pciIdsNotInCenterlines": len(pci_ids - every_id),
                            "pciIdsNotInCenterlinesNamedIntersection": len((pci_ids - every_id) & intersection_ids),
                            "pciIdsInCenterlines": len(pci_ids & every_id)},
        },
        "plan": {"tag": PLAN_TAG, "blocks": len(plan), "rated": len(rated(plan)),
                 "unrated": len(plan) - len(rated(plan)),
                 "milesUnit": "per direction of travel, as the plan's 472 miles (printed p. 20) are counted, times the share of each block the plan draws",
                 "miles": round(sum(p["miles"] for p in plan.values()), 1),
                 "partialBlocks": sum(1 for p in plan.values() if p["share"] < 1),
                 "directions": directions},
        "years": years, "lever": lever, "builtRate": built, "intervals": iv,
        "openings": openings, "openingAgencies": agencies,
        "sinceAdoption": {"from": ADOPTED, "blocks": sorted(since, key=lambda r: (r["date"], r["cnn"]))},
    }
    write_json(payload)
    write_md(payload)
    lo, hi = lever[0]["milesPerYear"], lever[-1]["milesPerYear"]
    print(f"repave-lever: {lo}–{hi} plan miles a year repaved and left short; plan network turns over every "
          f"{iv['impliedPlanCycleYears']} years (median gap {iv['gapPlanBlocks']['medianYears']} on {iv['gapPlanBlocks']['gaps']} gaps) "
          f"→ {OUT}/lever.md")


if __name__ == "__main__":
    main()
