#!/usr/bin/env python3
"""Walking distance from every census block, school and library branch to each bikeway type, today and on the North Star network, for the bike explorer.

Bryan, 2026-09-29: "connected" is measured along
walkable streets, precomputed here and looked up in the browser. For each of
the explorer's facility codes, one multi-source walk (lib/walknet.py) runs
from every block carrying that code: once over today's bikeway blocks, once
over the North Star plan's blocks. The browser takes, for each point, the
smallest level among the codes the reader has ticked, which is exact: the
nearest bikeway of any ticked type is the nearest of the nearest of each type.

The blocks each code covers are chosen exactly as site/src/bike-explorer.mjs
payload() chooses them: today's are the latest year's segments
(site/data/bike-history/segments.json) with the codes components.json gives
them, plus "S" where the block is a Slow Street; the plan's are the traced
North Star blocks (site/data/north-star/traced.geojson) that status.json rates,
coded by facility as PLAN_CODE maps them, with any block under a metre of plan
length left out, as the page leaves it out. Codes 2b and 3b (painted lanes and
signed routes below the comfort line) are not computed, since the explorer
never counts them.

ENCODING. Each (network, code) pair is one string with a character per point:
census blocks in site/data/bike-history/reach.json row order, then its schools,
then its libraries. The character is the index of the first distance in
`thresholds` (ascending) the walk is within, or the number of thresholds when
it is within none. Levels are all the page needs, since it compares with those
distances only, and one character per point gzips to about 2 KB a string
(the alternatives, measured, are in the task status).

Writes site/data/bike-history/walk-reach.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
import walknet  # noqa: E402
# Census blocks are measured from their street frontage (lib/walknet.py).
walknet.use_census_outlines()

BIKE = os.path.join(ROOT, "site", "data", "bike-history")
NS = os.path.join(ROOT, "site", "data", "north-star")
OUT = os.path.join(BIKE, "walk-reach.json")
TODAY_CODES = ["1", "4", "S", "2c", "3c", "L"]
# site/src/bike-explorer.mjs PLAN_CODE.
PLAN_CODE = {"Separated": "4", "Car-free": "1", "Shared-use Path": "1", "Shared": "S", "Shared L3": "L"}


def read(*p):
    return json.load(open(os.path.join(*p)))


def main():
    history = read(ROOT, "out", "bike-network-history", "history.json")
    thresholds = sorted(({"id": t["id"], "metres": round(t["metres"], 3)} for t in history["reach_thresholds"]), key=lambda t: t["metres"])
    segments = read(BIKE, "segments.json")
    components = read(BIKE, "components.json")
    reach = read(BIKE, "reach.json")
    traced = read(NS, "traced.geojson")
    status = {str(b["cnn"]): b for b in read(NS, "status.json")["blocks"]}

    today = {c: [] for c in TODAY_CODES}
    last = len(segments["years"]) - 1
    for s in segments["segments"]:
        if s["y"][last] == "0" or len(s["pts"]) < 2:
            continue
        comp = components["blocks"].get(s["key"])
        if not comp:
            continue
        codes = set(comp["m"])
        if comp.get("s") is not None:
            codes.add("S")
        for c in codes & set(TODAY_CODES):
            today[c].append((s["key"], s["pts"]))
    plan = {c: [] for c in sorted(set(PLAN_CODE.values()))}
    for f in traced["features"]:
        st = status.get(str(f["properties"]["cnn"]))
        code = PLAN_CODE.get(f["properties"]["facility"])
        if not st or not code or round(st["m"] / 1.609344) == 0 or len(f["geometry"]["coordinates"]) < 2:
            continue
        plan[code].append((str(f["properties"]["cnn"]), f["geometry"]["coordinates"]))

    col = {c: i for i, c in enumerate(reach["blocks"]["columns"])}
    points = [(r[col["lon"]], r[col["lat"]]) for r in reach["blocks"]["rows"]]
    points += [(s["lon"], s["lat"]) for s in reach["schools"]]
    points += [(lb["lon"], lb["lat"]) for lb in reach["libraries"]]
    top = thresholds[-1]["metres"]

    def levels(lines):
        if not lines:
            return str(len(thresholds)) * len(points)
        R = walknet.WalkReach(lines, top)
        out = []
        for lon, lat in points:
            d, _ = R.distance(lon, lat)
            out.append(str(next((i for i, t in enumerate(thresholds) if d is not None and d <= t["metres"]), len(thresholds))))
        return "".join(out)

    G = walknet.graph()
    doc = {
        "note": ("Per point, the first distance in `thresholds` within which a bikeway of the code lies by walking (lib/walknet.py); "
                 "len(thresholds) means none. Points: reach.json's census block rows, then its schools, then its libraries, in order."),
        "network": {"source": "OpenStreetMap via Overpass, OSMnx 2.1.1's walk filter plus cycle paths (tools/travel/osm-walk-network.py)",
                    "fetched_on": G.osm_base, "ways": G.ways, "nodes": len(G.x), "edges": len(G.eu),
                    "largest_component_share": round(G.component_sizes[0] / len(G.x), 4)},
        "method": {"sample_m": walknet.SAMPLE_M, "source_snap_m": walknet.SOURCE_SNAP_M, "fallback_snap_m": walknet.FALLBACK_SNAP_M,
                   "target_slack_m": walknet.TARGET_SLACK_M, "min_component": walknet.MIN_COMPONENT},
        "thresholds": thresholds,
        "counts": {"blocks": len(reach["blocks"]["rows"]), "schools": len(reach["schools"]), "libraries": len(reach["libraries"])},
        "lines": {"today": {c: len(v) for c, v in today.items()}, "plan": {c: len(v) for c, v in plan.items()}},
        "today": {c: levels(v) for c, v in today.items()},
        "plan": {c: levels(v) for c, v in plan.items()},
    }
    stable.write_json(OUT, doc, separators=(",", ":"))
    for net in ("today", "plan"):
        for c, s in doc[net].items():
            print("  %s %s: %d blocks of bikeway; %s" % (net, c, doc["lines"][net][c],
                  ", ".join("%s %d" % (t["id"], sum(1 for ch in s if int(ch) <= i)) for i, t in enumerate(thresholds))))
    print("  wrote %s (%.1f KB)" % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
