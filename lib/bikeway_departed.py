"""Rows SFMTA has deleted from its live bikeway layer, kept with their last attributes and line, grow-only.

The bike network history (tools/bike-network/bike-network-history.py) measures a block in an archived capture from the live
layer's line, because the captures keep no line for a block that was live when they were extracted. A row SFMTA
deletes would then lose its line, and every closed year it was in would lose its miles: SFMTA deleted Palou Avenue's
18 Class III rows (9 blocks, 2.0 miles) between 2026-10-20 and 2026-11-10, and 2015-2020 each fell by 2.0 miles.
A deletion does not un-build what was on the street in a closed year, so pipeline/refresh-extracts.py records each
deleted row here, before its re-read of the layer replaces the extract, and the history reads the line from here.

data/extract/sfmta-bikeway/departed.json: {"note", "records": [{"oid", "departed", "row", "pts"}]}, sorted by oid. A
row is never removed. `departed` is the date of the read that no longer had it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import os

from lib import stable

ROOT = paths.ROOT
PATH = os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "departed.json")
NOTE = ("Rows SFMTA deleted from its live bikeway layer, with their last attributes and line. Written by "
        "pipeline/refresh-extracts.py (lib/bikeway_departed.py); read by tools/bike-network/bike-network-history.py so a "
        "deletion does not change a closed year. Grow-only.")


def load():
    try:
        return json.load(open(PATH, encoding="utf-8"))["records"]
    except FileNotFoundError:
        return []


def record(old_rows, new_rows, old_geometry, day):
    """Add every row of `old_rows` (network.json records) with a facility type that `new_rows` lacks by OBJECTID.

    A read that returns under 90% of the rows on disk is a short read, not deletions, and records nothing (the
    re-read itself then fails in pipeline/refresh-extracts.py). Returns the OBJECTIDs added."""
    if len(new_rows) < 0.9 * len(old_rows):
        return []
    have = {r["OBJECTID"] for r in new_rows}
    pts = {g["oid"]: g["pts"] for g in old_geometry}
    kept = {r["oid"]: r for r in load()}
    added = []
    for r in old_rows:
        oid = r.get("OBJECTID")
        if oid in have or oid in kept or not r.get("FACILITY_T"):
            continue
        kept[oid] = {"oid": oid, "departed": day, "row": r, "pts": pts.get(oid)}
        added.append(oid)
    if added:
        stable.write_json(PATH, {"note": NOTE, "records": [kept[k] for k in sorted(kept)]}, indent=1)
    return added
