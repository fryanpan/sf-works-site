#!/usr/bin/env python3
"""School-age children per 2020 census block (ages 5-9, 10-14, 15-17), from the Census 2020 DHC table P12.

    tools/school-trips/census-children.py            # read the extract, fetching it once if absent
    tools/school-trips/census-children.py --update   # the same: see INCREMENTAL
    tools/school-trips/census-children.py --refresh  # re-read the table

Bryan, 2026-09-29: travel time from each block to the
nearest school, counted in children. P12 is "Sex by Age for Selected Age
Categories"; the columns read are P12_001N (total), P12_004N/P12_028N (male
and female 5 to 9 years), P12_005N/P12_029N (10 to 14) and P12_006N/P12_030N
(15 to 17), labels confirmed against api.census.gov's variable pages for
2020/dec/dhc on 2026-09-29. The table comes from data.census.gov's keyless
table API (api.census.gov now needs a key for data; its variable metadata does
not).

INCREMENTAL. The 2020 DHC is a final release: its block counts never change,
so there is no change marker to ask, and --update re-reads nothing once the
extract is on disk and holds every 2020 block in
data/extract/census-blocks/2020.json. An extract missing any block is
re-read whole (the table is one request). A failed read keeps the copy on
disk. The check is recorded in data/pipeline-state/sources.json. The checks in pipeline/transportation-quality.py
(census-children) run after every update: one row per 2020 block, unique
GEOIDs, the block set equal to data/extract/census-blocks/2020.json's, and
each block's DHC total equal to its PL 94-171 count there (the Census Bureau
holds block total population invariant between the two products).

Writes data/extract/census-dhc/p12-blocks.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from extract import Extract  # noqa: E402
from lib import pipeline_state  # noqa: E402

URL = "https://data.census.gov/api/access/data/table?id=DECENNIALDHC2020.P12&g=050XX00US06075$1000000"
UA = "Mozilla/5.0 (sf-works research; census-children.py)"
BANDS = {"a5_9": ("P12_004N", "P12_028N"), "a10_14": ("P12_005N", "P12_029N"), "a15_17": ("P12_006N", "P12_030N")}
MARKER = "census:dhc2020-p12"
FLOOR = 5900


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as fh:
        rows = json.load(fh)["response"]["data"]
    head, body = rows[0], rows[1:]
    col = {c: i for i, c in enumerate(head)}
    out = []
    for r in body:
        gid = r[col["GEO_ID"]]
        assert gid.startswith("1000000US"), gid
        rec = {"geoid": gid[len("1000000US"):], "total": int(r[col["P12_001N"]])}
        for band, cols in BANDS.items():
            rec[band] = sum(int(r[col[c]]) for c in cols)
        out.append(rec)
    out.sort(key=lambda x: x["geoid"])
    # A short read must never replace a good copy: San Francisco has 5,986 blocks.
    if len(out) < FLOOR:
        raise ValueError("P12 read returned %d blocks, under the floor of %d" % (len(out), FLOOR))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    ex = Extract("census-dhc")
    have = ex.read("p12-blocks")
    blocks = {x["geoid"] for x in Extract("census-blocks").read("2020").records}
    missing = sorted(blocks - {x["geoid"] for x in have.records}) if have else sorted(blocks)
    if have and missing:
        print("  P12 extract lacks %d of %d blocks (e.g. %s); re-reading the table" % (len(missing), len(blocks), missing[0]))
    refresh = a.refresh or bool(missing)
    try:
        r = ex.fetch_or_read("p12-blocks", fetch, refresh=refresh,
                             meta={"source": "Census 2020 Demographic and Housing Characteristics (DHC), table P12, "
                                             "San Francisco County blocks, via data.census.gov's table API (no key)",
                                   "url": URL})
    except Exception as exc:  # noqa: BLE001
        if not (a.update and have):
            raise
        # Keep the last good copy and say so; the orchestrator names the failure.
        pipeline_state.record(MARKER, "failed", detail="re-read failed, copy of %s kept: %s" % (have.fetched_on, exc))
        print("  P12 re-read failed (%s); keeping the copy read %s" % (exc, have.fetched_on))
        return
    if a.update:
        pipeline_state.record(MARKER, "changed" if refresh else "unchanged", version="2020 DHC",
                              detail="a final decennial release; re-read only when the copy lacks a block"
                              + (" (lacked %d)" % len(missing) if have and missing else ""))
    kids = sum(x["a5_9"] + x["a10_14"] + x["a15_17"] for x in r.records)
    print("  P12 blocks: %d (read %s); total %d; aged 5-17 %d" % (
        len(r.records), r.fetched_on, sum(x["total"] for x in r.records), kids))


if __name__ == "__main__":
    main()
