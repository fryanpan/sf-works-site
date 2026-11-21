#!/usr/bin/env python3
"""How far the bike network has come since the plan was adopted, and how far it is from the North Star.

    tools/bike-network/bike-progress.py             # build from the tracked extract
    tools/bike-network/bike-progress.py --refetch   # re-read SFMTA's bikeway layer first

Bryan, 2026-09-22: one chart that "celebrates highlights recent projects",
"plots the rate of progress on upgrading existing bike infra vs. North Star"
and "plots rate of progress on new bike infra vs. North Star to give people a
sense for % of the way we are to the goal after roughly one year".

Inputs, all read from disk:
  data/extract/sfmta-bikeway/network.json   SFMTA's own bikeway layer (5,457
        rows). Used instead of the DataSF copy (ygmz-vaxd) because only this
        copy carries UPDATE_YR/UPDATE_MO — the date a segment's facility was
        changed — and an upgrade is exactly a change without a new install.
  site/data/north-star/traced.geojson       the plan's 2,870 network segments
        with the facility the plan draws on each.
  site/data/north-star/segments.geojson     Appendix L's corridors, each
        flagged New or Upgrade, spread to their segments.

Miles are counted per direction of travel, the plan's unit (its 472 miles,
printed p. 20, is the bikeway layer's row sum), by lib/plan_directions.py:
a plan block's miles are its layer rows' own lengths, or where the layer lacks
it its centerline length times its directions of travel, times the share of
the block the plan's line covers (lib/mile_basis.py). Centerline totals
are kept in the JSON beside them.

A plan block's met miles are the own lengths of its rows whose class
satisfies what the plan draws (Separated: Class I or IV; Shared and Shared
L3: anything above Class III; the rest: any class), times the same share: the
same per-row count the overview uses for all-ages miles. A block with one row
meeting and one short is credited for one. Met miles count as progress since adoption when
a row on the block was installed or updated on or after 2025-03. Everything else that meets was already there when the plan was
adopted. Segments Appendix L flags neither New nor Upgrade, and the 1,044 it
does not list, are reported as their own group and kept out of both rates.

Writes site/data/bike-progress.json (the page reads it) and
out/bike-progress/progress.md.
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
import urllib.parse
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import bikeway_departed, stable  # noqa: E402
from extract import Extract  # noqa: E402
from plan_directions import Directions  # noqa: E402
from bikeway_snap import rekeyed_layer, shared_snapper  # noqa: E402
from mile_basis import BASIS, row_metres  # noqa: E402

SERVICE = "https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0"
FIELDS = ("OBJECTID,CNN,STREETNAME,FROM_ST,TO_ST,FACILITY_T,DIRECT,BARRIER,NOTES,FY,QTR,"
          "LENGTH,LENGTH_FT,INSTALL_YR,INSTALL_MO,UPDATE_YR,UPDATE_MO,CREATED_DATE,"
          "LAST_EDITED_DATE,SYMBOLOGY,BUFFERED,RAISED,CONTRAFLOW,BIKE_NTWK_SEG_ID,INROW")
TRACE = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
INDEX = os.path.join(ROOT, "site", "data", "north-star", "segments.geojson")
# Every SFMTA project with its published geometry matched to city blocks, from
# scripts/project-record.py. Used to say which project's record covers the
# blocks a highlight touched. Coverage is place, not authorship: an area
# project covers every block inside it, so the page prints the count and
# links the record rather than crediting the miles.
PROJECTS = os.path.join(ROOT, "out", "project-record", "projects.json")
SITE_OUT = os.path.join(ROOT, "site", "data", "bike-progress.json")
OUT = os.path.join(ROOT, "out", "bike-progress")
ADOPTED = "2025-03"  # SFMTA Board adopted the plan on 2025-03-04
METRE = 1609.344

SEPARATED = {"CLASS IV", "CLASS I"}
RANK = {"CLASS III": 1, "CLASS II": 2, "CLASS IV": 3, "CLASS I": 4}
REPORTED = os.path.join(ROOT, "site", "data", "bike-history", "reported.json")
CALMED = {"Shared", "Shared L3"}
PLAIN = {"CLASS I": "path", "CLASS II": "painted lane", "CLASS III": "sharrow", "CLASS IV": "separated lane"}


def fetch_layer():
    """Every row of SFMTA's bikeway layer, attributes only, paged by 2,000."""
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": FIELDS, "returnGeometry": "false",
                                    "orderByFields": "OBJECTID", "resultOffset": offset,
                                    "resultRecordCount": 2000, "f": "json"})
        with urllib.request.urlopen(f"{SERVICE}/query?{q}", timeout=120) as fh:
            d = json.load(fh)
        rows = [f["attributes"] for f in d.get("features", [])]
        # SFMTA's layer carries a few empty records (three on 2026-11-10: OBJECTID 7361, 8011, 14410) with no street,
        # no CNN, no facility type and no line. They are no bikeway; fetch_geometry in bike-network-history.py skips
        # them too, and a record missing only its line still fails the network~geometry join.
        out += [r for r in rows if not (r.get("CNN") is None and r.get("STREETNAME") is None
                                        and r.get("FACILITY_T") is None)]
        if not d.get("exceededTransferLimit") or not rows:
            break
        offset += len(rows)
    if len(out) < 5000:
        raise RuntimeError(f"bikeway layer returned {len(out)} rows; expected about 5,457")
    return out


def ym(y, m):
    """'2025-06' from a year and month field, or None when the year is missing."""
    try:
        y = int(y or 0)
    except (TypeError, ValueError):
        return None
    if y < 1900:
        return None
    try:
        m = int(m or 0)
    except (TypeError, ValueError):
        m = 0
    return f"{y:04d}-{m:02d}" if 1 <= m <= 12 else f"{y:04d}-00"


def row_dates(r):
    """The install month and the update month of one layer row."""
    return ym(r.get("INSTALL_YR"), r.get("INSTALL_MO")), ym(r.get("UPDATE_YR"), r.get("UPDATE_MO"))


def row_meets(facility, cls):
    """Does one direction row of class `cls` satisfy what the plan draws?"""
    if facility == "Separated":
        return cls in SEPARATED
    if facility in CALMED:
        return cls != "CLASS III"
    return True


def status(facility, rows):
    """('meets' | 'partial' | 'short' | 'none' | 'unrated', rows that meet).

    Counted per direction row, as the overview counts all-ages miles: a
    block with a protected lane one way and a painted lane the other meets
    the plan on one of its two rows, and its miles are credited by that row.
    """
    rows = [r for r in rows if r.get("FACILITY_T")]
    if facility == "Undecided":
        return "unrated", 0
    if not rows:
        return "none", 0
    met = sum(1 for r in rows if row_meets(facility, r["FACILITY_T"]))
    return ("meets" if met == len(rows) else "partial" if met else "short"), met


def months(a, b):
    """['2025-03', ..., b] inclusive."""
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def plan_read():
    """The day the plan's map PDF was read, as the trace recorded it in georeference.json."""
    with open(os.path.join(os.path.dirname(TRACE), "georeference.json")) as fh:
        return json.load(fh)["map_read"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    # A refetch replaces the extract, so the rows it no longer has are kept first, as pipeline/refresh-extracts.py
    # does (lib/bikeway_departed.py).
    old_net, old_geo = (Extract("sfmta-bikeway").read("network"), Extract("sfmta-bikeway").read("geometry")) \
        if args.refetch else (None, None)
    ex = Extract("sfmta-bikeway").fetch_or_read(
        "network", fetch_layer, refresh=args.refetch,
        meta={"service": SERVICE, "note": "SFMTA's own copy of the bikeway layer; carries UPDATE_YR/UPDATE_MO "
                                          "and edit dates that DataSF ygmz-vaxd drops"})
    if old_net is not None:
        bikeway_departed.record(old_net.records, ex.records, old_geo.records if old_geo else [], ex.fetched_on.isoformat())
    # Each row keyed by the centerline block it lies on, not the CNN SFMTA
    # typed, which is wrong on 144 rows (lib/bikeway_snap.py).
    layer = rekeyed_layer(ex.records)
    tag = f"[SFMTA ArcGIS Bicycle/bicycle layer 0 — queried {ex.fetched_on.isoformat()}]"
    print(f"  {tag}: {len(ex.records)} rows, {len(layer)} after re-keying")

    by_cnn = collections.defaultdict(list)
    for r in layer:
        if r.get("CNN"):
            by_cnn[str(int(float(r["CNN"])))].append(r)

    # Work SFMTA's project pages report as built, which the layer has not
    # caught up with (Bryan, 2026-09-28: "use the extended data that includes
    # projects only in project pages"). tools/bike-network/bike-reported-work.py lists
    # each project's class and blocks, as bike-network-history.py applies
    # them: a block's weaker rows are upgraded to the project's class, and a
    # block the layer lacks gains that class on every direction row. The
    # month is the one the page was last edited, when it reported the work.
    reported = json.load(open(REPORTED))["projects"] if os.path.exists(REPORTED) else []
    reported_log = []
    # Rows the project pages add where the layer has none. They join `by_cnn`
    # for scoring and the highlights below, so the rate and the list of
    # streets count the same work.
    added_rows = []

    plan = {str(f["properties"]["cnn"]): f["properties"]
            for f in json.load(open(TRACE))["features"]}
    # Plan miles per block, the plan's unit (lib/mile_basis.py): the
    # block's layer rows, or its centerline times its directions, times the
    # share of the block the plan's line covers.
    D = Directions(refetch=args.refetch)
    for cnn, p in plan.items():
        p["directions"], p["directions_basis"] = D.count(cnn)
        p["length_cl_m"] = p.get("length_m", 0)
        p["share"] = p.get("share", 1.0)
        p["length_m"] = D.plan_metres(cnn, p["length_cl_m"], p["share"])
    for proj in reported:
        cls, mo = proj["class"], (proj.get("page_edited") or f"{proj['year']}-01")[:7]
        up, add = 0, 0
        for blk in proj["blocks"]:
            c = str(blk["cnn"])
            rows = [r for r in by_cnn.get(c, []) if r.get("FACILITY_T")]
            if rows:
                for r in rows:
                    if RANK.get(r["FACILITY_T"], 0) < RANK[cls]:
                        r["FACILITY_T"], r["UPDATE_YR"], r["UPDATE_MO"] = cls, int(mo[:4]), int(mo[5:7])
                        up += 1
            elif c in plan:
                for _ in range(plan[c]["directions"]):
                    row = {"CNN": c, "FACILITY_T": cls, "INSTALL_YR": int(mo[:4]), "INSTALL_MO": int(mo[5:7]),
                           "STREETNAME": plan[c].get("street"), "LENGTH": plan[c]["length_cl_m"] / 1609.344}
                    by_cnn[c].append(row)
                    added_rows.append(row)
                    add += 1
        reported_log.append({"name": proj["name"], "page": proj["page"], "class": cls, "month": mo,
                             "rows_upgraded": up, "rows_added": add})
        print(f"  reported: {proj['name']} -> {up} rows upgraded, {add} added, as {cls} in {mo}")
    flags = {}
    for f in json.load(open(INDEX))["features"]:
        pr = f["properties"]
        for c in pr.get("cnns", []):
            flags[str(c)] = "new" if pr["new"] == "Y" else "upgrade" if pr["upgrade"] == "Y" else "neither"

    # The window: adoption to the last install or update month the layer records.
    dated = [d for rs in by_cnn.values() for r in rs for d in row_dates(r) if d and d >= ADOPTED and not d.endswith("-00")]
    last = max(dated) if dated else ADOPTED
    window = months(ADOPTED, last)
    edited = max((r.get("LAST_EDITED_DATE") or 0) for r in layer)
    last_edit = dt.datetime.utcfromtimestamp(edited / 1000).date().isoformat() if edited else None

    # The archived captures of the layer (tools/bike-network/bike-network-history.py), under the live layer's keys. A block's
    # met rows count as progress only for what they add over the capture before their month: a row SFMTA re-stamps
    # with a new UPDATE_YR while its class stays the same is not an upgrade (lead's ruling, 2026-11-10; 20 Folsom
    # Street rows already Class IV since 2018 and 2021 carried UPDATE_YR 2026-10 after an edit to their notes).
    captures = []
    snaps = Extract("bikeway-snapshots")
    for name in sorted(os.listdir(snaps.dir)):
        key = name[:-5] if name.endswith(".json") else None
        r = snaps.read(key) if key else None
        if r is None:
            continue
        rows_by = collections.defaultdict(list)
        for row in shared_snapper().snapshot_rows(r.records):
            if row.get("cnn") and row.get("cls"):
                rows_by[str(row["cnn"])].append(row["cls"])
        captures.append((f"{key[:4]}-{key[4:6]}-{key[6:8]}", rows_by))

    def met_before(cnn, facility, month):
        """Rows on the block that met the plan in the latest capture taken before `month`, or None with no capture."""
        prior = [c for d, c in captures if d < month + "-01"]
        if not prior:
            return None
        return sum(1 for cls in prior[-1].get(cnn, []) if row_meets(facility, cls))

    restamped = []

    # Score every plan segment.
    groups = {"upgrade": [], "new": [], "other": []}
    status_rows = []  # one row per plan block, for the overview's explorer
    partial_blocks, partial_short_m = 0, 0.0
    single_2w = 0
    for cnn, p in plan.items():
        rows = [r for r in by_cnn.get(cnn, []) if r.get("FACILITY_T")]
        st, met_rows = status(p["facility"], rows)
        # Met metres: the own lengths of the rows that meet the plan, times
        # the share of the block the plan covers, so a block's met metres
        # and its metres are counted from the same rows (lib/mile_basis.py).
        # A block meets the plan only when every row does; the Embarcadero at
        # the Ferry Building (two protected rows and a painted one) is partial,
        # and its painted row is the miles short.
        met_m = 0.0
        if rows and st != "unrated":
            met_m = min(p["length_m"], p["share"] * sum(row_metres(r) for r in rows if row_meets(p["facility"], r["FACILITY_T"])))
            if st == "meets":
                met_m = p["length_m"]
        if st == "partial":
            partial_blocks += 1
            partial_short_m += p["length_m"] - met_m
        if len(rows) == 1 and (rows[0].get("DIRECT") or "").upper() == "2W":
            single_2w += 1
        since = None
        if met_rows:
            # Dated from the rows that meet the plan only: a Class II row
            # painted after adoption beside a Class IV row from 2018 does not
            # date the block's met metres (pipeline review finding 9).
            ds = [d for r in rows if row_meets(p["facility"], r["FACILITY_T"])
                  for d in row_dates(r) if d and d >= ADOPTED]
            # A month of 00 means the year is known and the month is not; it
            # is placed in the adoption month so it counts, and is flagged.
            ds = [ADOPTED if d.endswith("-00") else d for d in ds]
            since = min(ds) if ds else None
        met_base_m = 0.0
        if since:
            before = met_before(cnn, p["facility"], since)
            if before is not None and before >= met_rows:
                restamped.append({"cnn": cnn, "street": p["street"], "month": since, "rows": met_rows,
                                  "metres": round(met_m)})
                since = None
            elif before:
                met_base_m = met_m * before / met_rows
        kind = flags.get(cnn)
        g = kind if kind in ("upgrade", "new") else "other"
        status_rows.append({"cnn": cnn, "street": p["street"], "facility": p["facility"], "status": st,
                            "m": round(p["length_m"]), "met_m": round(met_m), "flag": kind or "unlisted"})
        groups[g].append({"cnn": cnn, "street": p["street"], "facility": p["facility"],
                          "m": p.get("length_m", 0), "cl_m": p.get("length_cl_m", 0), "met_m": met_m,
                          "met_base_m": met_base_m, "met_rows": met_rows,
                          "met_cl_m": p["length_cl_m"] if met_rows else 0.0,
                          "status": st, "since": since, "flag": kind or "unlisted"})

    def series(segs):
        rated = [s for s in segs if s["status"] != "unrated"]
        total = sum(s["m"] for s in rated)
        meets = [s for s in rated if s["met_m"] > 0]
        baseline = sum(s["met_m"] if not s["since"] else s["met_base_m"] for s in meets)
        cum, run = [], baseline
        for mo in window:
            run += sum(s["met_m"] - s["met_base_m"] for s in meets if s["since"] == mo)
            cum.append({"month": mo, "metres": round(run), "pct": round(100 * run / total, 1) if total else 0})
        added = run - baseline
        return {
            "segments": len(rated), "unrated": len(segs) - len(rated),
            "totalMetres": round(total),
            # Centerline metres, one length per block, for About the Data.
            "totalCenterlineMetres": round(sum(s["cl_m"] for s in rated)),
            "metCenterlineMetres": round(sum(s["met_cl_m"] for s in meets)),
            "baselineMetres": round(baseline), "baselinePct": round(100 * baseline / total, 1) if total else 0,
            "addedMetres": round(added), "addedPct": round(100 * added / total, 1) if total else 0,
            "addedSegments": sum(1 for s in meets if s["since"]),
            "partialSegments": sum(1 for s in rated if s["status"] == "partial"),
            "nowPct": round(100 * run / total, 1) if total else 0,
            "remainingMetres": round(total - run),
            "milesPerMonth": round(added / METRE / max(len(window), 1), 2),
            "cumulative": cum,
            "addedStreets": sorted(collections.Counter(s["street"] for s in meets if s["since"]).items(),
                                   key=lambda kv: -kv[1]),
        }

    # Check: no block counted as progress met the plan on as many rows in the capture before its month.
    counted_restamps = [s for g in groups.values() for s in g if s["since"]
                        and (met_before(s["cnn"], s["facility"], s["since"]) or 0) >= s["met_rows"]]
    if counted_restamps:
        raise SystemExit("bike-progress: re-stamped blocks counted as progress: %s"
                         % ", ".join("%s %s" % (s["street"], s["cnn"]) for s in counted_restamps[:20]))
    upgrade, new, other = series(groups["upgrade"]), series(groups["new"]), series(groups["other"])

    # Which SFMTA project's published geometry covers each block: bike-tagged
    # projects with a page on sfmta.com, keyed by CNN.
    covering = collections.defaultdict(list)
    if os.path.exists(PROJECTS):
        for p in json.load(open(PROJECTS))["projects"]:
            if not p.get("bike") or "sfmta.com" not in (p.get("page") or ""):
                continue
            for c in p.get("cnns", []):
                covering[str(c)].append({"name": p["name"], "page": p["page"], "phase": p.get("phase")})

    # Highlights: every row installed or updated since adoption, by street.
    hi = collections.defaultdict(lambda: {"rows": 0, "miles": 0.0, "classes": collections.Counter(),
                                          "months": set(), "onPlan": 0, "planCalls": collections.Counter(),
                                          "kinds": collections.Counter(), "notes": collections.Counter(),
                                          "projects": {}, "projectRows": collections.Counter()})
    restamped_cnns = {x["cnn"] for x in restamped}
    for r in layer + added_rows:
        inst, upd = row_dates(r)
        when = [d for d in (inst, upd) if d and d >= ADOPTED and not d.endswith("-00")]
        if not when:
            continue
        # A re-stamped block's rows are not work since adoption, unless the row itself was installed since.
        if r.get("CNN") and str(int(float(r["CNN"]))) in restamped_cnns and not (inst and inst >= ADOPTED):
            continue
        h = hi[r.get("STREETNAME") or "?"]
        h["rows"] += 1
        h["miles"] += float(r.get("LENGTH") or 0)
        h["classes"][PLAIN.get(r.get("FACILITY_T"), r.get("FACILITY_T") or "?")] += 1
        h["months"].update(when)
        h["kinds"]["installed" if inst and inst >= ADOPTED else "upgraded"] += 1
        cnn = str(int(float(r["CNN"]))) if r.get("CNN") else None
        if cnn in plan:
            h["onPlan"] += 1
            h["planCalls"][plan[cnn]["facility"]] += 1
        if (r.get("NOTES") or "").strip():
            h["notes"][r["NOTES"].strip()] += 1
        for pj in covering.get(cnn, ()):
            h["projects"][pj["name"]] = pj
            h["projectRows"][pj["name"]] += 1
    highlights = []
    for street, h in hi.items():
        highlights.append({
            "street": street, "segments": h["rows"], "miles": round(h["miles"], 2),
            "classes": [c for c, _ in h["classes"].most_common()],
            "from": min(h["months"]), "to": max(h["months"]),
            "kind": h["kinds"].most_common(1)[0][0],
            "onPlan": h["onPlan"], "planCalls": [c for c, _ in h["planCalls"].most_common()],
            "note": h["notes"].most_common(1)[0][0] if h["notes"] else None,
            # Projects whose geometry covers the rows, most coverage first.
            "projects": [dict(h["projects"][name], rows=k)
                         for name, k in h["projectRows"].most_common()],
        })
    highlights.sort(key=lambda x: (x["to"], x["miles"]), reverse=True)

    # The undated share: rows with no install year, overall and on the plan.
    # Counted on SFMTA's own rows, before re-keying splits any of them.
    undated_rows = [r for r in ex.records if not row_dates(r)[0]]
    undated_miles = sum(float(r.get("LENGTH") or 0) for r in undated_rows)
    all_miles = sum(float(r.get("LENGTH") or 0) for r in layer)

    out = {
        "generated": dt.date.today().isoformat(),
        "adopted": "2025-03-04",
        "window": {"from": ADOPTED, "to": last, "months": len(window)},
        "reported": reported_log,
        # Blocks whose rows carry an install or update month since adoption but met the plan on as many rows in the
        # capture before that month: re-stamped, so counted in the baseline, not as progress.
        "restamped": sorted(restamped, key=lambda x: (x["street"] or "", x["cnn"])),
        "layer": {"tag": tag, "queried": ex.fetched_on.isoformat(), "rows": len(ex.records),
                  "lastEdited": last_edit, "service": SERVICE,
                  # The newest install month the layer itself dates, so the
                  # overview can say how far the layer runs without typing it.
                  # Read before reported work is applied, which adds no install
                  # month to `layer` rows. SFMTA's own rows, before re-keying.
                  # Capped at the month the layer was read, never today's.
                  "latestInstall": max((i for i in (row_dates(r)[0] for r in ex.records)
                                        if i and not i.endswith("-00") and i <= ex.fetched_on.isoformat()[:7]),
                                       default=None),
                  "undatedRows": len(undated_rows), "undatedRowsPct": round(100 * len(undated_rows) / len(ex.records), 1),
                  "undatedMilesPct": round(100 * undated_miles / all_miles, 1) if all_miles else None},
        "plan": {"segments": len(plan), "flagged": {k: len(v) for k, v in groups.items()},
                 "tag": "[Biking and Rolling Plan, March 2025, Appendix L and North Star map — read %s]" % plan_read(),
                 # The same date as a field of its own: lib/stable.py masks a
                 # "read <date>" phrase as a run stamp, so without it a new read
                 # of the plan would leave the tag's old date in place.
                 "planRead": plan_read(),
                 "milesUnit": "per direction row, as the plan's 472 miles (printed p. 20) are counted",
                 "metRule": ("A block's met miles are its centerline length per direction row whose class satisfies what the plan draws, "
                             "the same per-row count the overview uses for all-ages miles; a block with one row meeting and one short is credited for one."),
                 "partialBlocks": partial_blocks, "partialShortMetres": round(partial_short_m),
                 "singleRowTwoWayBlocks": single_2w,
                 "directions": D.summary()},
        "upgrade": upgrade, "new": new, "other": other,
        # The whole rated network in one row, for the page that asks when the
        # North Star is reached: the three groups summed, and the rate as a
        # straight line through the window.
        "network": (lambda t, met, add, tcl, mcl: {
            "totalMetres": t, "metMetres": met, "remainingMetres": t - met,
            "nowPct": round(100 * met / t, 1) if t else 0,
            "addedMetres": add,
            "milesPerYear": round(add / METRE * 12 / max(len(window), 1), 2),
            "yearsToGo": round((t - met) / METRE / (add / METRE * 12 / max(len(window), 1)), 1) if add else None,
            "totalCenterlineMetres": tcl, "metCenterlineMetres": mcl,
        })(sum(s["totalMetres"] for s in (upgrade, new, other)),
           sum(s["totalMetres"] - s["remainingMetres"] for s in (upgrade, new, other)),
           sum(s["addedMetres"] for s in (upgrade, new, other)),
           sum(s["totalCenterlineMetres"] for s in (upgrade, new, other)),
           sum(s["metCenterlineMetres"] for s in (upgrade, new, other))),
        "highlights": highlights,
    }
    stable.write_json(SITE_OUT, dict(out, mileBasis=BASIS), end="", ensure_ascii=True, indent=1)
    # Per-block status, so the overview's definition explorer can draw the
    # plan's network over today's and count what finishing it would add.
    stable.write_json(os.path.join(os.path.dirname(SITE_OUT), "north-star", "status.json"),
              {"generated": out["generated"], "mileBasis": BASIS, "plan": out["plan"]["tag"], "layer": tag,
               "statuses": "met: every direction row carries what the plan draws; partial: some rows do; short: none do; unrated: the plan draws Undecided",
               "metres": "m is the block's miles per direction of travel (its bikeway layer rows' own lengths, or its centerline times its directions where the layer lacks it) times the share of the block the plan draws, in metres; met_m the part of m on rows that meet the plan",
               "blocks": status_rows},
              end="", ensure_ascii=True, separators=(",", ":"))

    mi = lambda m: f"{m / METRE:.1f}"
    L = [
        "# The bike network since the plan: how far it has come, how far to the North Star", "",
        f"Bikeway layer {tag}, last edited {last_edit}; plan network {out['plan']['tag']}. "
        f"Window: {ADOPTED} to {last}, {len(window)} months. Miles are per direction row, the plan's unit: "
        f"{out['network']['totalMetres'] / METRE:.1f} miles of rated plan network, {out['network']['totalCenterlineMetres'] / METRE:.1f} once per block "
        f"({', '.join('%d blocks by %s' % (v, k) for k, v in sorted(D.summary()['blocks_by_basis'].items()))}).", "",
        "| Series | Segments | Miles in plan | Met at adoption | Added since | Now | Rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in (("Upgrade existing", upgrade), ("Build new", new), ("Not flagged by Appendix L", other)):
        L.append(f"| {name} | {s['segments']} | {mi(s['totalMetres'])} | {mi(s['baselineMetres'])} ({s['baselinePct']}%) | "
                 f"{mi(s['addedMetres'])} ({s['addedPct']}%, {s['addedSegments']} segments) | **{s['nowPct']}%** | "
                 f"{s['milesPerMonth']} mi/month |")
    L += ["", f"{len(undated_rows)} of {len(ex.records)} layer rows ({out['layer']['undatedRowsPct']}%) carry no install year, "
          f"{out['layer']['undatedMilesPct']}% of the layer's miles, so every rate above is a floor.", "",
          "## Installed or upgraded since adoption, by street", "",
          "| Street | When | What | Segments | Miles | On the plan | Plan calls for |", "|---|---|---|---|---|---|---|"]
    for h in highlights:
        L.append(f"| {h['street'].title()} | {h['from']}{' to ' + h['to'] if h['to'] != h['from'] else ''} | "
                 f"{h['kind']}: {', '.join(h['classes'])} | {h['segments']} | {h['miles']} | {h['onPlan']} | {', '.join(h['planCalls']) or '—'} |")
    stable.write_text(os.path.join(OUT, "progress.md"), "\n".join(L) + "\n")
    print(f"bike-progress: upgrade {upgrade['nowPct']}% (was {upgrade['baselinePct']}%), new {new['nowPct']}% "
          f"(was {new['baselinePct']}%), {len(highlights)} streets touched since adoption → site/data/bike-progress.json")


if __name__ == "__main__":
    main()
