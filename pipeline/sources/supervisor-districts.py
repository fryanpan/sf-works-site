#!/usr/bin/env python3
"""San Francisco's current Supervisor District boundaries (DataSF cqbw-m5m3, the 2022 redistricting), simplified for the contact-officials block's "Use my location" lookup.

    pipeline/sources/supervisor-districts.py            # rebuild the site file from disk; fetch once if absent
    pipeline/sources/supervisor-districts.py --update   # ask DataSF whether the boundaries changed; re-read only if they did
    pipeline/sources/supervisor-districts.py --refresh  # re-read the boundaries

THE DATA. DataSF "Current Supervisor Districts" (cqbw-m5m3): 11 multipolygons,
one per district, as approved by the Redistricting Task Force in 2022, with the
seated supervisor's name. The geometry is simplified on DataSF's side with
SoQL's simplify_preserve_topology at TOLERANCE degrees (about 30 feet), and
coordinates are rounded to five decimals (about 3 feet), so the whole city is
roughly 35 kB inline. Simplification is per district, so neighbouring
districts can overlap or leave a sliver of a few feet along a shared edge; the
browser treats a point in two districts, or in none, as "near a boundary" and
sends the reader to the city's own lookup rather than guessing.

PRIVACY. The file is bundled into the embed page, and the lookup runs in the
reader's browser. The reader's location never leaves the page.

CHECKS, before anything is written: exactly districts 1 to 11, each once; every
district a non-empty MultiPolygon inside San Francisco's bounding box; and one
landmark per district (City Hall in District 5, and so on) lands in that
district and no other. A failed check raises, and the previous file stays.

INCREMENTAL. --update reads the dataset's rowsUpdatedAt and re-reads the
geometry only when it differs from the one recorded in the file. A failed
re-read keeps the last good copy and records the failure in
data/pipeline-state/sources.json.

Writes site/data/supervisor-districts.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.pip import PolygonIndex  # noqa: E402
from lib.stable import write_json  # noqa: E402

ROOT = paths.ROOT
FXF = "cqbw-m5m3"
MARKER = "socrata:" + FXF
TOLERANCE = 0.0001  # degrees
OUT = os.path.join(ROOT, "site", "data", "supervisor-districts.json")
# San Francisco's bounding box, with the Farallon Islands (District 4) and
# Treasure and Yerba Buena Islands (District 6).
BBOX = (-123.2, 37.6, -122.3, 37.9)
# One point well inside each district, (lon, lat), to prove the lookup.
LANDMARKS = {
    1: ("Clement St and 6th Ave", -122.4645, 37.7830),
    2: ("Marina Green", -122.4400, 37.8045),
    3: ("Portsmouth Square, Chinatown", -122.4053, 37.7948),
    4: ("Sunset Blvd and Taraval St", -122.4945, 37.7425),
    5: ("City Hall", -122.4193, 37.7793),
    6: ("Yerba Buena Gardens", -122.4025, 37.7850),
    7: ("West Portal Station", -122.4660, 37.7406),
    8: ("Castro Theatre", -122.4348, 37.7620),
    9: ("24th St Mission BART", -122.4184, 37.7524),
    10: ("Third St and Palou Ave", -122.3900, 37.7330),
    11: ("Mission St and Geneva Ave", -122.4361, 37.7164),
}


def _round(mp):
    return [[[[round(p[0], 5), round(p[1], 5)] for p in ring] for ring in poly] for poly in mp]


def fetch():
    r = sfdata.fetch(FXF, select="sup_dist,sup_name,simplify_preserve_topology(multipolygon, %s) as geom" % TOLERANCE,
                     refresh=True, floor=11)
    out = []
    for row in r.rows:
        g = row.get("geom") or {}
        if g.get("type") not in ("MultiPolygon", "Polygon"):
            raise ValueError("%s district %r has no polygon" % (FXF, row.get("sup_dist")))
        coords = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        out.append({"district": int(float(row["sup_dist"])), "supervisor": row.get("sup_name"), "coords": _round(coords)})
    out.sort(key=lambda x: x["district"])
    return out


def check(districts):
    """Every reason the boundaries cannot be used; empty when they can."""
    bad = []
    nums = [d["district"] for d in districts]
    if sorted(nums) != list(range(1, 12)):
        bad.append("districts are %s, not 1 to 11 once each" % nums)
    for d in districts:
        pts = [p for poly in d["coords"] for ring in poly for p in ring]
        if not pts:
            bad.append("district %s has no coordinates" % d["district"])
        elif any(not (BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]) for x, y in pts):
            bad.append("district %s reaches outside San Francisco's bounding box" % d["district"])
    idx = PolygonIndex([(d["district"], d["coords"]) for d in districts])
    for n, (name, lon, lat) in sorted(LANDMARKS.items()):
        hits = sorted(set(idx.at(lon, lat)))
        if hits != [n]:
            bad.append("%s should be in district %d alone, found %s" % (name, n, hits))
    return bad


def read_existing():
    if not os.path.exists(OUT):
        return None
    import json
    with open(OUT, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    have = read_existing()
    if have is not None and not (a.update or a.refresh):
        bad = check(have["districts"])
        if bad:
            sys.exit("supervisor-districts: the file on disk fails its checks: " + "; ".join(bad))
        print("  %s: %d districts on disk, read %s" % (FXF, len(have["districts"]), have["read"]))
        return
    try:
        meta = sfdata.metadata(FXF)
        stamp = meta["rows_updated_ts"]
        if not a.refresh and have is not None and have.get("rowsUpdatedTs") == stamp:
            print("  %s unchanged (rowsUpdatedAt %s)" % (FXF, stamp))
            if a.update:
                pipeline_state.record(MARKER, "unchanged", version=str(stamp), detail="11 districts")
            return
        districts = fetch()
        bad = check(districts)
        if bad:
            raise ValueError("; ".join(bad))
    except Exception as exc:  # noqa: BLE001
        if not (a.update and have):
            raise
        pipeline_state.record(MARKER, "failed", detail="re-read failed, copy of %s kept: %s" % (have["read"], exc))
        print("  %s re-read failed (%s); keeping the copy read %s" % (FXF, exc, have["read"]))
        return
    import datetime as dt
    doc = {
        "source": "Current Supervisor Districts (2022 redistricting), DataSF %s" % FXF,
        "dataset": "https://data.sfgov.org/d/" + FXF,
        "rowsUpdatedAt": meta["rows_updated_at"].isoformat() if meta["rows_updated_at"] else None,
        "rowsUpdatedTs": stamp,
        "read": dt.date.today().isoformat(),
        "simplified": "simplify_preserve_topology at %s degrees, coordinates to 5 decimals" % TOLERANCE,
        "districts": districts,
    }
    wrote = write_json(OUT, doc, separators=(",", ":"))
    if a.update:
        pipeline_state.record(MARKER, "changed", version=str(stamp), detail="11 districts")
    print("  %s: %d districts, rowsUpdatedAt %s; %s" % (FXF, len(districts), doc["rowsUpdatedAt"],
                                                     "written" if wrote else "unchanged"))


if __name__ == "__main__":
    main()
