#!/usr/bin/env python3
"""Share of San Francisco residents within 1 block, 2 blocks and a quarter mile of a street block with on-street parking, beside the Muni yardstick in the bike explorer.

Bryan, 2026-09-23, on the explorer's Muni comparison line: "Also cite how
many residents can park their car within 1 block of where they live."

Measured as tools/muni/muni-stop-reach.py measures Muni, so the two figures
compare: walking distance along the street network (lib/walknet.py) from
each census block's interior point, the
explorer's distances (site/data/bike-history/history.json reach_thresholds),
and the explorer's residents (reach.json pop_latest). The target is the
nearest point on any street segment in SFMTA's On-Street Parking Census
(DataSF 9ivs-nf5y) with one or more spaces. The census was surveyed from 2008
to 2014; rows coded 5555 are left out, as the dataset's description says to
do when aggregating. Writes site/data/bike-history/parking-reach.json.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import datetime as dt
import json
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
from sfdata import fetch  # noqa: E402
from walknet import WalkReach  # noqa: E402
import walknet  # noqa: E402
# Census blocks are measured from their street frontage (lib/walknet.py).
walknet.use_census_outlines()
BIKE = os.path.join(ROOT, "site", "data", "bike-history")
DATASET = "9ivs-nf5y"
LAT0 = math.radians(37.76)
R = 6371008.8


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * R, math.radians(lat) * R)


def lines(shape):
    if shape["type"] == "LineString":
        return [shape["coordinates"]]
    if shape["type"] == "MultiLineString":
        return shape["coordinates"]
    return []


def median_feet(dists, total):
    """Resident-weighted median of the distances, in feet, rounded to 10."""
    seen = 0
    for d, pop in sorted(dists):
        seen += pop
        if seen >= total / 2:
            return int(round(d / 0.3048, -1))


def main():
    # Through the dated DataSF cache, which pages to exhaustion and asserts the
    # read was complete, so a rerun reads no network.
    read = fetch(DATASET, floor=1000)
    rows = read.rows
    kept = [r for r in rows if r.get("shape") and r.get("prkg_sply") not in (None, "5555") and float(r["prkg_sply"]) > 0]
    spaces = sum(float(r["prkg_sply"]) for r in kept)
    years = sorted({r.get("year") for r in kept if r.get("year")})
    as_of = max((r.get("data_as_of") or "")[:10] for r in rows)

    thresholds = json.load(open(os.path.join(BIKE, "history.json")))["reach_thresholds"]
    reach = json.load(open(os.path.join(BIKE, "reach.json")))["blocks"]
    col = {c: i for i, c in enumerate(reach["columns"])}
    walk = WalkReach([[c[:2] for c in line] for r in kept for line in lines(r["shape"]) if len(line) >= 1],
                     max(t["metres"] for t in thresholds))
    total, within, dists = 0, collections.Counter(), []
    for row in reach["rows"]:
        pop = row[col["pop_latest"]]
        total += pop
        d, _ = walk.distance(row[col["lon"]], row[col["lat"]])
        best = math.inf if d is None else d
        dists.append((best, pop))
        for t in thresholds:
            if best <= t["metres"]:
                within[t["id"]] += pop
    out = {
        "generated": dt.date.today().isoformat(),
        "source": {"name": "SFMTA On-Street Parking Census", "id": DATASET, "url": "https://data.sf.gov/d/" + DATASET,
                   "data_as_of": as_of, "queried": read.fetched_on.isoformat(), "rows": len(rows),
                   "segments": len(kept), "spaces": round(spaces), "surveyed": [years[0], years[-1]] if years else None},
        "residents": total,
        "share": {t["id"]: round(100 * within[t["id"]] / total, 1) for t in thresholds},
        # The distance half of residents live within, for the explorer's note
        # comparing the plan's quarter mile with it.
        "median_feet": median_feet(dists, total),
        "method": "Walking distance along the street network (lib/walknet.py) from each census block's interior point to the nearest street segment with one or more on-street spaces.",
    }
    stable.write_json(os.path.join(BIKE, "parking-reach.json"), out, end="", ensure_ascii=True, indent=1)
    print("  %d rows, %d segments with spaces, %d spaces, surveyed %s; residents within: %s"
          % (len(rows), len(kept), spaces, out["source"]["surveyed"], out["share"]))


if __name__ == "__main__":
    main()
