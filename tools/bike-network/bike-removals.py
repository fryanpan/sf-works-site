#!/usr/bin/env python3
"""Which bikeways and Slow Streets were removed, and when, for the bike history map and its removals table.

    tools/bike-network/bike-removals.py            # build site/data/bike-history/removed.json
    tools/bike-network/bike-removals.py --check    # also print every corridor's resolved blocks

Bryan, 2026-09-29, on the history map: "Did we account for slow streets in 2020
that were added and then partly or fully removed a few years later? How do we
track and show bike infrastructure removals throughout this report?"

Two kinds of removal, from two kinds of record.

Bikeway blocks. tools/bike-network/bike-network-history.py writes each block's facility
class per year (site/data/bike-history/segments.json), reconstructed from
SFMTA's live layer and six Internet Archive captures of DataSF ygmz-vaxd. A
block is REMOVED when it carries a class in some year and none in the latest.
Its removal is dated by the two captures either side of it: the last capture
whose year it was counted in, and the first that lacks it. A block that is
missing from one capture and back in a later one is a capture gap, not a
removal, and is not listed. A block whose line lies along a block the latest
layer still carries (REKEY_COVER of its length within REKEY_M) was renumbered,
not removed, and is not listed either. Removals before the first capture
(2021-03-25) cannot be seen.

Pandemic Slow Streets. DataSF hkz3-itiu lists only the corridors the permanent
program kept. The corridors SFMTA installed in 2020-21 and later dropped are
named in three SFMTA Board staff reports, entered below as CORRIDORS with the
reports' own words:

  7-21-20 MTAB Item 12 (Resolution 200721-069): the 16 corridors already
    implemented, with their extents, and 17 more approved.
  4-6-21 MTAB Item 12: nine Phase 4 corridors approved.
  12-6-22 MTAB Item 14 (Slow Streets Program, Resolution 221206-116): the
    corridors kept, and the ones removed "for reasons including low use,
    resident feedback overwhelmingly in opposition of the Slow Street, and
    conflicts with other uses"; "Any remaining COVID Response Slow Streets
    materials on the Phase 1 through 4 streets noted above will be removed in
    the Winter 2023."

Each corridor's extent is resolved to centerline blocks (DataSF 3psu-pn9h, read
from the sfdata cache): the chain of blocks of the named street between the
nodes it shares with the two cross streets. A block of a corridor that is not
in hkz3-itiu today was removed. One that is in hkz3-itiu with an install date
of 2023 or later was dropped with the pandemic program and re-adopted (part of
20th Street, and a Cabrillo Street block). Chenery Street's re-adopted Slow
Street (Elk Street to Diamond Street, 2023) is not the pandemic stretch
(Burnside Avenue to Lippard Avenue), which stays removed. The reports give no month for
any single removal: the 2022 report dropped or shortened the corridors on
2022-12-06 and scheduled what materials remained for removal "in the Winter
2023". So every pandemic removal is dated to that report: a block not kept is
all-ages through 2021 and out from 2022 (DROPPED_YEAR, written as
`dropped_year`); the report says some came out earlier. The corridor table and
the kept/readopted test live in lib/slow_corridors.py, which
bike-network-history.py also reads to count the dropped corridors' reach.

Corridors the 2020 and 2021 reports approved that the 2022 report neither
keeps nor removes are listed as `unaccounted` and drawn nowhere.

Two lengths are written for every removal. `street_miles` (or
`removed_street_miles`) is street length counted once, which the page's
removals table and headline print, since that is the length SFMTA and
advocates quote. `miles` (or `removed_miles`) is per direction, the unit of
the all-ages figures: a Slow Street counts twice, as bike-network-history.py
counts the kept ones, and a bikeway block once per direction row it had in
its last capture.

This step fetches nothing. The staff reports are fixed documents, read on
2026-09-29 and entered by hand; the other inputs are other steps' outputs.
Checks run at the end and exit 1 on failure, and pipeline/transportation-quality.py
runs the same checks after the pipeline step.

Writes site/data/bike-history/removed.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import json
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
# The corridors, their resolution to centerline blocks and the kept/readopted
# test are shared with tools/bike-network/bike-network-history.py, which counts the
# dropped corridors in the years they stood.
from lib.slow_corridors import (CENTERLINES, DIRECTIONS, DROPPED_YEAR, MI, KEPT_M, KEPT_COVER, PROGRAM_PAGE,  # noqa: E402
                                READOPTED_FROM, REPORT_2020, REPORT_2021, REPORT_2022, REPORTS, UNACCOUNTED,
                                Grid, centerline_miles, corridor_blocks, line_m)

SITE = os.path.join(ROOT, "site", "data", "bike-history")
OUT = os.path.join(SITE, "removed.json")
SNAPSHOTS = os.path.join(ROOT, "data", "extract", "bikeway-snapshots")

# A removed bikeway block whose line lies this close to a block the latest
# layer still carries, over this share of its length, was renumbered.
REKEY_M = 15.0
REKEY_COVER = 0.8
# A separated lane redrawn on a new CNN can sit a curb's width off its old
# line, so a block on the same street gets a wider tolerance.
REKEY_SAME_STREET_M = 30.0
FACILITY = {"1": "off-street path", "2": "painted lane", "3": "signed route", "4": "separated lane", "S": "Slow Street", "?": "bikeway"}


def read(path):
    with open(path) as f:
        return json.load(f)


# ---- bikeway removals -------------------------------------------------------------

def capture_dates(segments):
    """The capture date behind each year's state: (earlier, later) as bike-network-history.py's state_in_year picks them."""
    caps = sorted(dt.date.fromisoformat(s["captured"]) for s in segments["sources"]["snapshots"])
    out = {}
    for y in segments["years"]:
        end = dt.date(y, 12, 31)
        later = next((d for d in caps if d > end), caps[-1])
        earlier = next((d for d in reversed(caps) if d <= end), None)
        out[y] = (earlier, later)
    return out


_CAPTURES = {}


def capture_rows(date, cnn):
    """The rows a capture holds for one CNN (one per direction of travel)."""
    path = os.path.join(SNAPSHOTS, date.strftime("%Y%m%d") + ".json")
    if not os.path.exists(path):
        return []
    if path not in _CAPTURES:
        by = collections.defaultdict(list)
        for r in read(path)["records"]:
            by[r.get("cnn")].append(r)
        _CAPTURES[path] = by
    return _CAPTURES[path].get(cnn, [])


def bikeway_removals(segments):
    years, segs = segments["years"], segments["segments"]
    lat0 = 37.76
    live_segs = [s for s in segs if s["y"][-1] != "0" and len(s["pts"]) > 1]
    live = Grid([s["pts"] for s in live_segs], lat0)
    by_name = collections.defaultdict(list)
    for s in live_segs:
        by_name[s["name"]].append(s["pts"])
    caps = capture_dates(segments)
    out, renumbered, gaps = [], [], 0
    for s in segs:
        y = s["y"]
        present = [i for i, ch in enumerate(y) if ch != "0"]
        if not present:
            continue
        # Gaps inside the record (present, missing, present) are captures that
        # dropped a block; bike-network-history.py fills what it can.
        if any(y[i] == "0" for i in range(present[0], present[-1])):
            gaps += 1
        if y[-1] != "0":
            continue
        last = present[-1]
        if len(s["pts"]) < 2:
            continue
        share = live.cover(s["pts"], REKEY_M)
        if share < REKEY_COVER and s["name"] in by_name:
            share = max(share, Grid(by_name[s["name"]], lat0).cover(s["pts"], REKEY_SAME_STREET_M))
        if share >= REKEY_COVER:
            renumbered.append({"key": s["key"], "name": s["name"], "cover": round(share, 2)})
            continue
        ly = years[last]
        seen, gone = caps[ly]
        if seen is None:
            continue
        code = y[last]
        rows = capture_rows(seen, s["cnn"]) if s.get("cnn") else []
        n_rows = len(rows) or 1
        m = line_m(s["pts"])
        out.append({"key": s["key"], "cnn": s.get("cnn"), "name": s["name"], "code": code, "facility": FACILITY.get(code, "bikeway"),
                    "from": rows[0].get("from") if rows else None, "to": rows[0].get("to") if rows else None,
                    "last_year": ly, "gone_year": ly + 1, "seen": seen.isoformat(), "gone_by": gone.isoformat(),
                    "rows": n_rows, "street_miles": round(m / MI, 4), "miles": round(n_rows * m / MI, 4),
                    "bci": s.get("bci"), "pts": s["pts"]})
    out.sort(key=lambda r: (r["gone_year"], r["name"] or "", r["key"]))
    return out, renumbered, gaps


# ---- pandemic Slow Streets ---------------------------------------------------------

def all_ages_today(segments):
    """The blocks all-ages in the latest year, keyed by CNN, with the grid of their lines and the code each carries.

    Bryan, 2026-09-29: "for "dropped" only drop it if it's no longer part of the
    all ages network after no longer being a Slow Street". all-ages.geojson is
    bike-network-history.py's own list, so a Class II or III block that passes
    the plan's comfort test counts here exactly as it does in the miles."""
    feats = read(os.path.join(SITE, "all-ages.geojson"))["features"]
    code = {s["cnn"]: s["y"][-1] for s in segments["segments"] if s.get("cnn")}
    now = [f for f in feats if not f["properties"].get("until")]
    by_cnn = {f["properties"]["cnn"]: (f["properties"]["first"], code.get(f["properties"]["cnn"])) for f in now}
    return by_cnn, Grid([f["geometry"]["coordinates"] for f in now], 37.76), [f["properties"] for f in now]


def all_ages_years(years):
    """Block key -> the years all-ages.geojson counts it all-ages (first through until, or the latest year)."""
    out = {}
    for f in read(os.path.join(SITE, "all-ages.geojson"))["features"]:
        p = f["properties"]
        out[p["key"]] = set(range(p["first"], (p.get("until") or years[-1]) + 1))
    return out


def dropped_miles(corridors, aa_years):
    """The pandemic miles that left the all-ages total in DROPPED_YEAR, as
    bike-network-history.py counts them: every block the program did not keep
    (removed, replaced or readopted), per direction, unless it was already
    all-ages in DROPPED_YEAR - 1."""
    y = DROPPED_YEAR - 1
    return sum(DIRECTIONS * centerline_miles(b["pts"]) for c in corridors if c["installed"] <= y
               for b in c["blocks"] if b["status"] != "kept" and y not in aa_years.get(b["cnn"], ()))


def slow_street_removals(check, segments):
    resolved, cl_date, ss_date = corridor_blocks()
    aa_cnn, aa_grid, _ = all_ages_today(segments)
    corridors = []
    for r in resolved:
        c, why = r["c"], r["unresolved"]
        row = {"id": c.id, "words": c.words, "street": c.street, "phase": c.phase, "installed": c.year, "fate": c.fate,
               "source": REPORTS[c.report]["url"], "blocks": [], "unresolved": why}
        for b in r["blocks"]:
            k, status, back = b["cnn"], b["status"], b["back"]
            if status == "out":
                if k in aa_cnn or aa_grid.cover(b["pts"], KEPT_M) >= KEPT_COVER:
                    # No longer a Slow Street, but all-ages today as something else.
                    status, back = "replaced", aa_cnn.get(k, (None, None))[0]
                else:
                    status = "removed"
            row["blocks"].append({"cnn": k, "street": b["street"], "status": status, "back": back,
                                  "street_miles": round(b["m"] / MI, 4), "pts": b["pts"]})
        gone = [b for b in row["blocks"] if b["status"] == "removed"]
        back = [b for b in row["blocks"] if b["status"] == "readopted"]
        row["removed_street_miles"] = round(sum(b["street_miles"] for b in gone), 3)
        row["removed_miles"] = round(2 * row["removed_street_miles"], 3)
        row["readopted_street_miles"] = round(sum(b["street_miles"] for b in back), 3)
        row["readopted_year"] = min((b["back"] for b in back), default=None)
        row["kept_street_miles"] = round(sum(b["street_miles"] for b in row["blocks"] if b["status"] == "kept"), 3)
        row["replaced_street_miles"] = round(sum(b["street_miles"] for b in row["blocks"] if b["status"] == "replaced"), 3)
        if check:
            print("  %-18s %-7s %2d blocks  removed %.2f  readopted %.2f  kept %.2f  %s"
                  % (c.id, c.fate, len(row["blocks"]), row["removed_street_miles"], row["readopted_street_miles"],
                     row["kept_street_miles"], why or ""), file=sys.stderr)
        corridors.append(row)
    return corridors, cl_date, ss_date


# ---- checks -------------------------------------------------------------------------

def checks(doc, aa_years=None):
    """The step's quality checks; each returns an error string or None. transportation-quality.py runs the same."""
    errs = []
    # A replaced block is drawn on the map only as the bikeway it became
    # (all-ages.geojson), never as a pandemic Slow Street, so it must be
    # all-ages in every year its corridor stood; otherwise the history counts
    # pandemic miles there that the map does not draw.
    for c in doc["slow_streets"] if aa_years is not None else []:
        for b in c["blocks"]:
            if b["status"] == "replaced":
                gap = [y for y in range(c["installed"], DROPPED_YEAR) if y not in aa_years.get(b["cnn"], ())]
                if gap:
                    errs.append("%s block %s is replaced but not all-ages in %s, so its pandemic years are not drawn" % (c["id"], b["cnn"], gap))
    sl = doc["slow_streets"]
    ids = [c["id"] for c in sl]
    if len(ids) != len(set(ids)):
        errs.append("corridor ids repeat")
    cnns = [b["cnn"] for c in sl for b in c["blocks"]]
    if len(cnns) != len(set(cnns)):
        errs.append("a block is in two corridors")
    for c in sl:
        if c["unresolved"] and c["id"] != "lombard":
            errs.append("%s did not resolve: %s" % (c["id"], c["unresolved"]))
        if c["blocks"] and not 0 < sum(b["street_miles"] for b in c["blocks"]) < 4:
            errs.append("%s resolves to %.2f street miles" % (c["id"], sum(b["street_miles"] for b in c["blocks"])))
        # A corridor the 2022 report kept is still mostly in the program; one
        # it removed is mostly not.
        total = sum(b["street_miles"] for b in c["blocks"]) or 1
        if c["fate"] == "kept" and c["blocks"] and c["kept_street_miles"] + c["readopted_street_miles"] <= 0:
            errs.append("%s is kept by the 2022 report but none of it is in hkz3-itiu" % c["id"])
        if c["fate"] == "removed" and c["blocks"] and c["kept_street_miles"] / total > 0.2:
            errs.append("%s is removed by the 2022 report but %.0f%% of it is in hkz3-itiu from before %d" % (c["id"], 100 * c["kept_street_miles"] / total, READOPTED_FROM))
    removed = doc["summary"]["slow_street_removed_miles"]
    if not 5 <= removed <= 60:
        errs.append("pandemic Slow Street miles removed %.1f outside 5-60" % removed)
    bw = doc["bikeways"]
    keys = [b["key"] for b in bw]
    if len(keys) != len(set(keys)):
        errs.append("bikeway removal keys repeat")
    for b in bw:
        if not b["seen"] < b["gone_by"]:
            errs.append("%s: seen %s is not before gone %s" % (b["key"], b["seen"], b["gone_by"]))
        if not 0 < b["miles"] < 3:
            errs.append("%s: %.2f miles" % (b["key"], b["miles"]))
    if len(bw) > 60:
        errs.append("%d bikeway blocks removed; a capture probably lost rows" % len(bw))
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="print each corridor's resolved blocks")
    args = ap.parse_args()
    segments = read(os.path.join(SITE, "segments.json"))
    bikeways, renumbered, gaps = bikeway_removals(segments)
    corridors, cl_date, ss_date = slow_street_removals(args.check, segments)
    aa_years = all_ages_years(segments["years"])
    ss_removed = sum(c["removed_miles"] for c in corridors)
    doc = {
        "generated": dt.date.today().isoformat(),
        "mileBasis": "street_miles: street length counted once (the page prints these); miles: per direction of travel, a Slow Street counting both directions",
        # dropped_year: the year the 2022 report dropped the pandemic corridors;
        # a block not kept is all-ages through the year before it.
        # readopted_from: an hkz3-itiu install year from which a covered block
        # counts as re-adopted rather than kept.
        "dropped_year": DROPPED_YEAR, "readopted_from": READOPTED_FROM,
        "sources": {
            "reports": [REPORT_2020, REPORT_2021, REPORT_2022, PROGRAM_PAGE],
            "slow_streets": {"dataset": "https://data.sf.gov/d/hkz3-itiu", "queried": ss_date},
            "centerlines": {"dataset": "https://data.sf.gov/d/" + CENTERLINES, "queried": str(cl_date)},
            "captures": [s["captured"] for s in segments["sources"]["snapshots"]],
        },
        "summary": {
            "bikeway_blocks_removed": len(bikeways),
            "bikeway_removed_miles": round(sum(b["miles"] for b in bikeways), 2),
            "bikeway_blocks_renumbered": len(renumbered),
            "bikeway_blocks_with_capture_gaps": gaps,
            "slow_street_corridors_removed": sum(1 for c in corridors if c["removed_miles"] > 0 and c["fate"] == "removed"),
            "slow_street_corridors_shortened": sum(1 for c in corridors if c["removed_miles"] > 0 and c["fate"] == "kept"),
            "slow_street_removed_miles": round(ss_removed, 2),
            "slow_street_readopted_street_miles": round(sum(c["readopted_street_miles"] for c in corridors), 2),
            "slow_street_replaced_street_miles": round(sum(c["replaced_street_miles"] for c in corridors), 2),
            # What left the all-ages miles in dropped_year, per direction:
            # removed and readopted blocks (and any replaced one not yet
            # all-ages), not already all-ages the year before. The page prints
            # this; slow_street_removed_miles counts removed blocks only.
            "slow_street_dropped_miles": round(dropped_miles(corridors, aa_years), 2),
            "slow_street_removed_street_miles": round(sum(c["removed_street_miles"] for c in corridors), 2),
        },
        "method": __doc__.split("\n\n", 2)[2].split("\nWrites")[0].strip(),
        "bikeways": bikeways,
        "renumbered": renumbered,
        "slow_streets": corridors,
        "unaccounted": [dict(u, source=REPORTS[u["report"]]["url"]) for u in UNACCOUNTED],
    }
    errs = checks(doc, aa_years)
    if errs:
        print("bike-removals: %d check(s) failed, nothing written:\n  %s" % (len(errs), "\n  ".join(errs)), file=sys.stderr)
        return 1
    stable.write_json(OUT, doc, end="\n", indent=None, separators=(",", ":"))
    s = doc["summary"]
    print("bike-removals: %d bikeway blocks removed (%.1f mi), %d renumbered; %d Slow Street corridors removed and %d shortened (%.1f mi); wrote %s"
          % (s["bikeway_blocks_removed"], s["bikeway_removed_miles"], s["bikeway_blocks_renumbered"],
             s["slow_street_corridors_removed"], s["slow_street_corridors_shortened"], s["slow_street_removed_miles"],
             os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
