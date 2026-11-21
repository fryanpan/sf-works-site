#!/usr/bin/env python3
"""Share of San Francisco residents within 1 block, 2 blocks and a quarter mile of a Muni stop, for the bike explorer's distance control.

Bryan, 2026-09-23, on the explorer's "Within reach means" control: "Add
context here -- ... 98% (check on this) are within 2 blocks of a muni stop."
The check is this script. It measures the same way the explorer does, so the
two figures compare: walking distance along the street network
(lib/walknet.py) from each census block's interior point, the explorer's distances (site/data/bike-history/history.json
reach_thresholds), and the explorer's residents (reach.json pop_latest).

Any stop in DataSF's Muni Stops (i28k-bkz6) counts, whatever its frequency or
hours. Writes site/data/bike-history/muni-reach.json.
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
DATASET = "i28k-bkz6"
LAT0 = math.radians(37.76)
R = 6371008.8


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * R, math.radians(lat) * R)


def median_feet(dists, total):
    """Resident-weighted median of the distances, in feet, rounded to 10."""
    seen = 0
    for d, pop in sorted(dists):
        seen += pop
        if seen >= total / 2:
            return int(round(d / 0.3048, -1))


def main():
    # Through the dated DataSF cache, so a rerun reads no network and a refresh
    # (pipeline/refresh-socrata.py) re-reads only when the dataset changed.
    read = fetch(DATASET, floor=1000)
    stops = read.rows
    pts = [xy(float(s["longitude"]), float(s["latitude"])) for s in stops if s.get("longitude") and s.get("latitude")]
    as_of = max((s.get("data_as_of") or "")[:10] for s in stops)
    thresholds = json.load(open(os.path.join(BIKE, "history.json")))["reach_thresholds"]
    reach = json.load(open(os.path.join(BIKE, "reach.json")))["blocks"]
    col = {c: i for i, c in enumerate(reach["columns"])}
    walk = WalkReach([[(float(st["longitude"]), float(st["latitude"]))] for st in stops if st.get("longitude") and st.get("latitude")],
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
        "source": {"name": "DataSF Muni Stops", "id": DATASET, "url": "https://data.sf.gov/d/" + DATASET,
                   "data_as_of": as_of, "queried": read.fetched_on.isoformat(), "stops": len(pts)},
        "residents": total,
        "share": {t["id"]: round(100 * within[t["id"]] / total, 1) for t in thresholds},
        # The distance half of residents live within, for the explorer's note
        # comparing the plan's quarter mile with it.
        "median_feet": median_feet(dists, total),
        "method": "Walking distance along the street network (lib/walknet.py) from each census block's interior point to the nearest stop; any stop counts.",
    }
    stable.write_json(os.path.join(BIKE, "muni-reach.json"), out, end="", ensure_ascii=True, indent=1)
    print("  %d stops (as of %s); residents within: %s" % (len(pts), as_of, out["share"]))


if __name__ == "__main__":
    main()
