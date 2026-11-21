#!/usr/bin/env python3
"""San Francisco's Environmental Justice Communities map (SF Planning, DataSF y6ci-vpnb), and each 2020 census block's score on it.

    pipeline/sources/ej-communities.py            # read the extract, fetching it once if absent; rebuild the block join
    pipeline/sources/ej-communities.py --update   # ask DataSF whether the map changed; re-read only if it did
    pipeline/sources/ej-communities.py --refresh  # re-read the map

Bryan chose this map on 2026-10-01 as the one definition of which neighborhoods count when the
bikeway budget is spent equity-first. sources/sf-environmental-justice-communities.md
says what it is.

THE MAP. 2,702 multipolygons, each with a score from 0 to 30, or 999 for the
major parks and the Islais Creek industrial area. SF Planning built it as a
raster: a weighted average of CalEnviroScreen 4.0 (60%), the Air Pollution
Exposure Zone (20%), DPH's Areas of Vulnerability (10%) and HCD income limits
(10%), in cells, then vectorised. So a polygon is a patch of equal score, not a
census tract or block group. Scores 21 to 30 are the "EJ Communities", the top
one-third of burden (the map's Technical Documentation, March 2023).

THE JOIN. Each 2020 census block (data/extract/census-blocks/2020.json) takes
the score of the polygon holding its interior point, the Census Bureau's
INTPTLAT/INTPTLON. A point in no polygon (on the water, or in a sliver
between polygons) has score null and is not EJ; a point on a shared edge that
lands in two polygons takes the higher score of 0-30, and 999 only when
nothing else holds it (none did on 2026-10-01). A block is EJ when its score is
21 to 30. 999 is not: the map greys those areas out, and the user guide
treats them as outside the gradient.

INCREMENTAL. --update asks DataSF for the dataset's rowsUpdatedAt (one small
request) and re-reads the polygons only when it differs from the one recorded
with the extract. The join is recomputed every run from what is on disk; it is
cheap, and a run that changes nothing leaves both files byte for byte as they
were (lib/extract.py keeps a file whose records did not change). A failed
re-read keeps the last good copy and records the failure in
data/pipeline-state/sources.json. The checks in pipeline/transportation-quality.py
(ej-communities) run after every update: a polygon floor and scores in range,
one row per census block, the block set equal to the census extract's, the
share of children in EJ blocks within a band around the map's one-third.

Writes data/extract/ej-communities/polygons.json and blocks.json.
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
from extract import Extract  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.pip import PolygonIndex, pick_score  # noqa: E402

FXF = "y6ci-vpnb"
MARKER = "socrata:" + FXF
FLOOR = 2500  # 2,702 polygons on 2026-10-01
EJ_MIN, EJ_MAX = 21, 30
PARKS = 999
NAME = "San Francisco Environmental Justice Communities Map"


def is_ej(score):
    return score is not None and EJ_MIN <= score <= EJ_MAX


def _round(mp):
    return [[[[round(p[0], 6), round(p[1], 6)] for p in ring] for ring in poly] for poly in mp]


def fetch():
    r = sfdata.fetch(FXF, select="the_geom,score", refresh=True, floor=FLOOR)
    out = []
    for row in r.rows:
        g = row.get("the_geom") or {}
        if g.get("type") != "MultiPolygon" or row.get("score") in (None, ""):
            raise ValueError("%s row without a MultiPolygon and a score: %r" % (FXF, {k: row.get(k) for k in ("score",)}))
        out.append({"score": int(float(row["score"])), "coords": _round(g["coordinates"])})
    # Sorted on the whole geometry, so the file's order does not follow the upload's.
    out.sort(key=lambda x: (x["score"], x["coords"]))
    return out


def join(polys, blocks):
    idx = PolygonIndex([(p["score"], p["coords"]) for p in polys])
    out = []
    for b in sorted(blocks, key=lambda x: x["geoid"]):
        hits = idx.at(b["lon"], b["lat"])
        score = pick_score(hits, PARKS)
        out.append({"geoid": b["geoid"], "score": score, "ej": is_ej(score), "hits": len(hits)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    ex = Extract("ej-communities")
    have = ex.read("polygons")
    stamp, changed = None, False
    if have is not None and not (a.update or a.refresh):
        polys = have  # no network: the copy on disk, as the docstring says
    else:
        try:
            meta = sfdata.metadata(FXF)
            stamp = meta["rows_updated_ts"]
            if a.refresh or have is None or have.meta.get("rows_updated_ts") != stamp:
                polys = ex.write("polygons", fetch(), meta={
                    "source": "%s, SF Planning, DataSF %s" % (NAME, FXF),
                    "dataset": "https://data.sfgov.org/d/" + FXF,
                    "rows_updated_at": meta["rows_updated_at"].isoformat() if meta["rows_updated_at"] else None,
                    "rows_updated_ts": stamp})
                changed = not polys.from_disk
            else:
                polys = have
        except Exception as exc:  # noqa: BLE001
            if not (a.update and have):
                raise
            pipeline_state.record(MARKER, "failed", detail="re-read failed, copy of %s kept: %s" % (have.fetched_on, exc))
            print("  %s re-read failed (%s); keeping the copy read %s" % (FXF, exc, have.fetched_on))
            polys = have
        else:
            if a.update:
                pipeline_state.record(MARKER, "changed" if changed else "unchanged", version=str(stamp),
                                      detail="rowsUpdatedAt %s; %d polygons" % (stamp, len(polys.records)))

    blocks = Extract("census-blocks").read("2020")
    rows = join(polys.records, blocks.records)
    ex.write("blocks", rows, fetched_on=polys.fetched_on, meta={
        "source": "Each 2020 census block's interior point placed in %s (DataSF %s)" % (NAME, FXF),
        "ej": "score %d to %d" % (EJ_MIN, EJ_MAX),
        "blocks": "data/extract/census-blocks/2020.json"})
    pop = {b["geoid"]: b["pop"] for b in blocks.records}
    ej_pop = sum(pop[r["geoid"]] for r in rows if r["ej"])
    none = [r for r in rows if r["score"] is None]
    print("  %s: %d polygons (read %s, %s); %d blocks, %d EJ; %d blocks in no polygon (pop %d); %d on a shared edge; "
          "population in EJ blocks %d of %d (%.1f%%)" % (
              FXF, len(polys.records), polys.fetched_on, "changed" if changed else "unchanged", len(rows),
              sum(1 for r in rows if r["ej"]), len(none), sum(pop[r["geoid"]] for r in none),
              sum(1 for r in rows if r["hits"] > 1), ej_pop, sum(pop.values()), 100.0 * ej_pop / max(1, sum(pop.values()))))


if __name__ == "__main__":
    main()
