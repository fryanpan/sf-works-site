#!/usr/bin/env python3
"""Add the street context of each injury crash, as of its crash date, to DataSF's crash table (ubvf-ztfx): EPC, posted speed limit, street class and corner type, lanes, BCI traffic, and dated flags for painted safety zones, speed cameras, traffic calming, Slow Streets and signals.

    python3 pipeline/crash-augment/street/crash-street-context.py            # build from held copies (no network once held)
    python3 pipeline/crash-augment/street/crash-street-context.py --update   # ask each source for changes first

Reads the crash table (DataSF ubvf-ztfx) from ../crash_tables.py's held copy, and the other inputs through
street_sources.py (DataSF 3psu-pn9h, 3t7b-gebn, vtn2-q8ky, d5uh-bk84,
abhw-ffzx, hkz3-itiu, ybh5-27n2; ArcGIS layers for MTC's Equity Priority Communities, SFMTA's traffic lanes and
the Bike Comfort Index), applies the rules in street_fields.py, and writes:

  out/crash-augment/street/crash-street.csv   one row per crash, keyed case_id_pkey, sorted by it (gitignored)
  out/crash-augment/street/summary.json       row counts, each source's read date and size, the block-join mix,
                                              and each field's coverage by basis for all crashes and KSI crashes

Both are written to a staging name first. street_checks.py runs on the staged table against the previous summary;
if any check fails the held files stay, the failures are printed and the exit status is 1. A file whose content
has not changed is not rewritten, and neither file carries a run date, so a rerun with no new data changes nothing.
Interval: weekly at most, with the crash table's own refresh (DataSF updates ubvf-ztfx about daily).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import street_checks  # noqa: E402
import street_fields  # noqa: E402
import street_paths  # noqa: E402
import street_sources  # noqa: E402


def cell(v):
    if v is True:
        return "true"
    if v is False:
        return "false"
    return "" if v is None else str(v)


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=street_fields.COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: cell(r.get(k)) for k in street_fields.COLUMNS})
    return buf.getvalue()


def summarize(str_rows, crashes, src, ctx):
    ksi_keys = {c["case_id_pkey"] for c in crashes if c.get("collision_severity") in street_fields.KSI}
    groups = {"all": str_rows, "ksi": [r for r in str_rows if r["case_id_pkey"] in ksi_keys]}
    cov = {}
    for f in street_fields.FIELDS:
        cov[f] = {}
        for g, rows in groups.items():
            n = len(rows) or 1
            by = collections.Counter(r[f + "_basis"] for r in rows)
            nn = collections.Counter(r[f + "_basis"] for r in rows if r[f] != "")
            cov[f][g] = {"non_null": round(street_checks.coverage(rows, f), 4),
                         "by_basis": {b: {"rows": by[b], "with_value": nn[b], "share": round(by[b] / n, 4)}
                                      for b in sorted(by)},
                         "values": dict(sorted(collections.Counter(r[f] for r in rows).items()))}
    return {
        "about": "Street context of each crash in DataSF ubvf-ztfx as of its crash date; built by "
                 "pipeline/crash-augment/street/crash-street-context.py. Rules in that folder's README.",
        "rows": len(str_rows),
        "ksi_rows": len(groups["ksi"]),
        "sources": {k: {"id": s.ref, "read_on": s.read_on, "rows": len(s.rows)} for k, s in sorted(src.items())},
        "street_block_join": dict(sorted(collections.Counter(r["street_block_join"] for r in str_rows).items())),
        "camera_sites": {"placed": len(ctx.cameras), "unplaced": ctx.camera_unplaced,
                         "sites": {s["site"]: {"start": s["start"], "block": s["home"], "snap_ft": s["snap_ft"],
                                               "corridor_blocks": sorted(s["segs"])} for s in ctx.cameras},
                         "first_day": min((s["start"] for s in ctx.cameras), default=None)},
        "coverage": cov,
    }


def write_if_changed(path, text):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="ask each source whether it changed and re-read what moved")
    args = ap.parse_args()

    src = street_sources.load_all(update=args.update)
    crashes = sorted(src["crashes"].rows, key=lambda c: (len(c["case_id_pkey"]), c["case_id_pkey"]))
    ctx = street_fields.Context({k: s.rows for k, s in src.items()})
    rows = street_fields.augment(crashes, ctx)
    assert len(rows) == len(crashes), "row count changed: %d crashes in, %d rows out" % (len(crashes), len(rows))

    text = to_csv(rows)
    str_rows = list(csv.DictReader(io.StringIO(text)))
    summary = summarize(str_rows, crashes, src, ctx)
    prev = None
    if os.path.exists(street_paths.OUT_SUMMARY):
        prev = json.load(open(street_paths.OUT_SUMMARY, encoding="utf-8"))

    floors = {k: v[2] for k, v in street_sources.SOCRATA.items()}
    floors["crashes"] = street_sources.CRASH_FLOOR
    floors.update({k: v[2] for k, v in street_sources.ARCGIS.items()})
    results = street_checks.run(str_rows, [c["case_id_pkey"] for c in crashes], prev_summary=prev,
                                source_counts={k: len(s.rows) for k, s in src.items()}, source_floors=floors,
                                cameras_unplaced=ctx.camera_unplaced)
    if not street_checks.report(results):
        print("checks failed: the held table and summary are kept")
        return 1

    os.makedirs(street_paths.OUT_DIR, exist_ok=True)
    a = write_if_changed(street_paths.OUT_CSV, text)
    b = write_if_changed(street_paths.OUT_SUMMARY, json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print("  %d crashes, %s; %s" % (len(rows), "table written" if a else "table unchanged",
                                    "summary written" if b else "summary unchanged"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
