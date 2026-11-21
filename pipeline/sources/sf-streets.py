#!/usr/bin/env python3
"""Every active San Francisco street centerline, thinned, as the base the site's maps draw under the plan network.

    pipeline/sources/sf-streets.py             # from the cached read
    pipeline/sources/sf-streets.py --refetch   # re-read DataSF first

Bryan, 2026-09-28, on a project map: "This is so dim it's completely unclear
that this is a map of SF. It just looks like a random set of grey chicken
scratch." The plan network alone is a scatter of corridors; the whole street
grid gives the city its shape (the coast, Golden Gate Park, the grid turning
at Market) so a reader can place a project.

Input: DataSF 3psu-pn9h, Streets – Active and Retired, active rows only, the
same cached query lib/plan_directions.py makes. Output:
site/data/sf-streets.json, one polyline per street segment, [lon, lat] at five
decimals (about a metre), dropping points closer than about 15 m to the last
one kept, which no map on the site can show.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import sfdata  # noqa: E402
from lib import stable  # noqa: E402
from plan_directions import CENTERLINES, CENTERLINE_SELECT, CENTERLINE_FLOOR  # noqa: E402

OUT = os.path.join(ROOT, "site", "data", "sf-streets.json")
MIN_M = 15
KX = 111320 * math.cos(math.radians(37.76))
KY = 110540


def thin(coords):
    out = []
    for lon, lat in coords:
        if out and abs(lon - out[-1][0]) * KX < MIN_M and abs(lat - out[-1][1]) * KY < MIN_M:
            continue
        out.append([round(lon, 5), round(lat, 5)])
    last = [round(coords[-1][0], 5), round(coords[-1][1], 5)]
    if out[-1] != last:
        out.append(last)
    return out if len(out) > 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()
    cl = sfdata.fetch(CENTERLINES, select=CENTERLINE_SELECT, where="active='true'", floor=CENTERLINE_FLOOR, refresh=args.refetch)
    lines = []
    for r in cl.rows:
        g = r.get("line") or {}
        parts = g.get("coordinates") or []
        if g.get("type") == "LineString":
            parts = [parts]
        for part in parts:
            if len(part) > 1:
                t = thin(part)
                if t:
                    lines.append(t)
    out = {"source": "DataSF 3psu-pn9h, Streets – Active and Retired, active rows",
           "url": "https://data.sf.gov/d/3psu-pn9h", "queried": cl.fetched_on.isoformat(),
           "tag": cl.tag, "segments": len(lines), "lines": lines}
    stable.write_text(OUT, json.dumps(out, separators=(",", ":")))
    print(f"sf-streets: {len(lines)} segments, {os.path.getsize(OUT) // 1024}KB -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
