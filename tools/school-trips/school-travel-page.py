#!/usr/bin/env python3
"""Write the school travel page's data (site/data/school-travel.json) from lib/school-travel-time.py's output.

    tools/school-trips/school-travel-page.py

The aim: "Bryan can see, for every block, whether a child can
reach the nearest school in 15 minutes." The page itself is
site/src/pages/transportation-schools.mjs, drawn on the site's standard map
(site/src/maplibre.mjs). This script reads out/school-travel/blocks.json and
summary.json and writes only what that page and About the Data print: one
point per block with its children and its minutes to the nearest public
school, the headline counts, and the plan streets that bring the most
children within 15 minutes. The gap lines are drawn from the traced plan
network the site already carries (site/data/north-star/traced.geojson), by
CNN.

Every headline figure is recomputed here from blocks.json and asserted equal
to summary.json, so the page cannot print a count the data does not support.
A run with no new input leaves the file byte-identical.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import os
import sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "site", "data", "school-travel.json")

BANDS = (("a5_9", "elementary", "5-9"), ("a10_14", "middle", "10-14"), ("a15_17", "high", "15-17"))
SCEN = ("walk", "today", "plan")
TARGET = 15.0
TOP_GAPS = 10


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return json.load(f)


def street_name(s):
    """HOLLOWAY AVE -> Holloway Ave, 41ST AVE -> 41st Ave."""
    return " ".join(w.lower() if w[:1].isdigit() else w.capitalize() for w in s.split())


def tenths(v):
    """Minutes as whole tenths; -1 where no walking route reaches any school."""
    return -1 if v is None else int(round(v * 10))


def over(blocks, sc, sub=None, band=None):
    """Children in blocks over the target for one scenario, nearest school of any kind or public only."""
    n = 0
    for b in blocks:
        for key, lvl, lab in BANDS:
            if band and lab != band:
                continue
            t = b[lvl][sub][sc] if sub else b[lvl][sc]
            if t is None or t > TARGET:
                n += b[key]
    return n


def main():
    blocks = read("out", "school-travel", "blocks.json")["blocks"]
    summ = read("out", "school-travel", "summary.json")
    traced = {str(c) for f in read("site", "data", "north-star", "traced.geojson")["features"] for c in [f["properties"]["cnn"]]}

    # Recompute every printed figure from the blocks and check it against the summary.
    kids = {lab: sum(b[key] for b in blocks) for key, _, lab in BANDS}
    total = sum(kids.values())
    assert total == summ["children"]["5-17"], (total, summ["children"])
    counts = {"public": {}, "any": {}}
    for sc in SCEN:
        counts["public"][sc] = over(blocks, sc, "public")
        counts["any"][sc] = over(blocks, sc)
        assert counts["public"][sc] == summ["over_target_public_schools_only"][sc]["5-17"], sc
        assert counts["any"][sc] == summ["over_target"][sc]["5-17"], sc
        for _, _, lab in BANDS:
            assert over(blocks, sc, "public", lab) == summ["over_target_public_schools_only"][sc][lab], (sc, lab)
    no_route = sum(b[key] for b in blocks for key, lvl, _ in BANDS if b[lvl]["walk"] is None)
    assert no_route == summ["no_walking_route_to_any_school"]["5-17"], no_route

    # The school names the map's popup prints, public schools only, in one list
    # the blocks point into.
    names = [s["name"] for s in summ["schools"]["list"]]
    used = sorted({b[lvl]["public"][k] for b in blocks for _, lvl, _ in BANDS
                   for k in ("school_today", "school_plan") if b[lvl]["public"][k] is not None})
    index = {s: i for i, s in enumerate(used)}

    # One row per block with children: lon, lat, the three age bands'
    # children, then for each band its minutes walking, today and with the
    # plan built, then its school today and with the plan built. Public
    # schools only, the basis the page leads with.
    rows = []
    for b in sorted(blocks, key=lambda b: b["geoid"]):
        k = [b[key] for key, _, _ in BANDS]
        if not sum(k):
            continue
        rec = [round(b["lon"], 5), round(b["lat"], 5)] + k
        for _, lvl, _ in BANDS:
            p = b[lvl]["public"]
            rec += [tenths(p[sc]) for sc in SCEN]
            rec += [-1 if p[s] is None else index[p[s]] for s in ("school_today", "school_plan")]
        rows.append(rec)

    # The plan streets that bring the most children within 15 minutes if
    # built alone (lib/school-travel-time.py ranks them against public and
    # private schools).
    gaps = []
    for i, g in enumerate(summ["gaps"]["rows"][:TOP_GAPS]):
        cnns = [str(c) for c in g["cnns"]]
        assert all(c in traced for c in cnns), (g["street"], [c for c in cnns if c not in traced])
        gaps.append({"n": i + 1, "street": street_name(g["street"]), "cnns": cnns, "miles": g["miles"],
                     "alone": g["children_brought_under_alone"], "centre": g["centre"]})

    slist = summ["schools"]["list"]
    att = summ["attendance_area"]
    data = {
        "note": "Written by tools/school-trips/school-travel-page.py from lib/school-travel-time.py's output. Do not edit.",
        "target": TARGET,
        "walkMph": summ["walk_mph"], "rideMph": summ["ride_mph"], "detourCap": summ["detour_cap"],
        "children": summ["children"],
        "overPublic": summ["over_target_public_schools_only"],
        "overAny": {sc: summ["over_target"][sc]["5-17"] for sc in SCEN},
        "noRoute": summ["no_walking_route_to_any_school"],
        "attendance": {"children": att["children_5_9_in_areas"], "areas": att["areas"], "over": att["over_target"]},
        "schools": {
            "counted": summ["schools"]["counted"],
            "public": sum(1 for s in slist if not s["private"]),
            "private": sum(1 for s in slist if s["private"]),
            "middle": summ["schools"]["by_level"]["middle"],
            "middlePublic": summ["schools"]["by_level"]["middle/public"],
            "leftOut": sum(summ["schools"]["left_out"].values()),
        },
        "gapCount": summ["gaps"]["count"],
        "osmDate": summ["network"]["walk"]["osm_base"][:10],
        "schoolsRead": summ["sources"]["private_schools_queried"],
        "areasRead": summ["sources"]["attendance_areas"]["queried"],
        "names": [names[i] for i in used],
        "blocks": rows,
        "gaps": gaps,
    }
    text = json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n"
    old = open(OUT).read() if os.path.exists(OUT) else None
    if old != text:
        with open(OUT, "w") as f:
            f.write(text)
    print("%s %s (%.0f KB, %d blocks, %d gaps)" % ("wrote" if old != text else "unchanged",
          os.path.relpath(OUT, ROOT), len(text) / 1024, len(rows), len(gaps)))


if __name__ == "__main__":
    sys.exit(main())
