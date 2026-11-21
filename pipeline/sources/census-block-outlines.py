#!/usr/bin/env python3
"""Census 2010 and 2020 block outlines for San Francisco, so walking distance is measured from a block's street frontage.

    pipeline/sources/census-block-outlines.py            # fetch any vintage not on disk
    pipeline/sources/census-block-outlines.py --update   # the same: see INCREMENTAL
    pipeline/sources/census-block-outlines.py --refresh  # re-read both vintages

Bryan, 2026-09-29, on the explorer: "In the sunset, a
bunch of blocks that are right on a bikeway don't show up as connected (e.g.
along Kirkham) at 1 block distance". Measured from a census block's interior
point, a block facing Kirkham starts about 90 m from it. lib/walknet.py
measures from the block's outline instead, where it meets the street network,
so the residents on a bikeway's frontage are at the bikeway.

SOURCE. TIGERweb's Census Blocks layers (tigerWMS_Census2010 layer 18,
tigerWMS_Census2020 layer 10), San Francisco County, in WGS84, generalised to
about a metre (maxAllowableOffset) and rounded to 5 decimals (about a metre),
with GEOID only. The same service already supplies the 2010 block points
(tools/bike-network/bike-network-history.py).

INCREMENTAL. A decennial census's block outlines never change after release,
so a vintage on disk is kept and --update re-reads nothing; each run checks the
copies against the block points' GEOIDs (pipeline/transportation-quality.py).
Writes data/extract/census-blocks/outlines-2010.json and outlines-2020.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from extract import Extract  # noqa: E402

LAYERS = {
    "2010": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/18/query",
    "2020": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10/query",
}
FLOOR = {"2010": 7000, "2020": 5500}
PAGE = 1000


def get(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "sf-works-research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.loads(fh.read())


def fetch(vintage):
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "STATE='06' AND COUNTY='075'", "outFields": "GEOID", "returnGeometry": "true",
                                    "outSR": "4326", "maxAllowableOffset": "0.00001", "orderByFields": "GEOID",
                                    "resultOffset": offset, "resultRecordCount": PAGE, "f": "json"})
        d = get(LAYERS[vintage] + "?" + q)
        if "error" in d:
            raise RuntimeError("TIGERweb %s: %s" % (vintage, d["error"]))
        feats = d.get("features") or []
        for f in feats:
            rings = [[[round(x, 5), round(y, 5)] for x, y in ring] for ring in (f.get("geometry") or {}).get("rings", [])]
            out.append({"geoid": f["attributes"]["GEOID"], "rings": rings})
        offset += len(feats)
        if not feats or not d.get("exceededTransferLimit") and len(feats) < PAGE:
            break
    geoids = [r["geoid"] for r in out]
    if len(set(geoids)) != len(geoids):
        raise RuntimeError("TIGERweb %s returned duplicate GEOIDs" % vintage)
    if len(out) < FLOOR[vintage]:
        raise RuntimeError("TIGERweb returned %d %s block outlines; expected at least %d" % (len(out), vintage, FLOOR[vintage]))
    return sorted(out, key=lambda r: r["geoid"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    ex = Extract("census-blocks")
    for v in ("2010", "2020"):
        r = ex.fetch_or_read("outlines-" + v, lambda v=v: fetch(v), refresh=a.refresh,
                             meta={"source": "TIGERweb Census Blocks, San Francisco County, GEOID and outline", "url": LAYERS[v]})
        print("  %s block outlines: %d (read %s)" % (v, len(r.records), r.fetched_on))


if __name__ == "__main__":
    main()
