#!/usr/bin/env python3
"""Each case study school's per-block inputs as one reusable file: the gravity model's share of the school's students on every census block in the city, and for the blocks within reach the walk, drive, bike and foot time today and the feet off safe streets.

    pipeline/venv-step.py tools/school-trips/school-block-inputs.py

The input stage for the one-simulation school tool: assignment draws
from `p`, and trip options read the per-block times, so nothing downstream
reads the page's JSON.

READS site/data/school-case/<id>.json (tools/school-trips/school-case.py), whose blocks
are matched back to their census 2020 block by point; and the gravity model
(tools/school-trips/school-gravity.py's Model), rerun for each school with the levels,
door and charter or private flag school-case.py recorded, so the citywide
shares are the same ones the page's expected students came from.

WRITES data/school-case/blocks/<id>.json, columns rather than rows:
  p            {geoid: share of the school's students}, every block with a
               share of at least 1e-6, summing to 1 within rounding
  geoid, walkFt, carMin   the blocks within 2.5 miles by street, in the page's order
  today.brp / today.sfbike  [minutes, % of distance ridden on safe streets,
               feet off safe streets] per block, or null where no route counts
Feet off safe streets is the route's distance not ridden on a safe edge: its
total length from the minutes and the share ridden, at 2 mph walking and
10 mph riding, times the share walked. It is the total, not the longest gap.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

grav = paths.load("school-gravity.py")

CASE = os.path.join(ROOT, "site", "data", "school-case")
OUT = os.path.join(ROOT, "data", "school-case", "blocks")
WALK_FT_MIN, RIDE_FT_MIN = 2 * 5280 / 60.0, 10 * 5280 / 60.0


def off_safe_ft(r):
    if r is None:
        return None
    s, t = r[1] / 100.0, r[0] / 10.0
    total = t / ((1 - s) / WALK_FT_MIN + s / RIDE_FT_MIN)
    return int(round(total * (1 - s)))


def main():
    model = grav.Model()
    by_pt = {(round(b["lon"], 5), round(b["lat"], 5)): b["geoid"] for b in model.blks}
    enrol = json.load(open(os.path.join(ROOT, "data", "school-case", "enrolment.json")))["schools"]
    os.makedirs(OUT, exist_ok=True)
    for f in sorted(os.listdir(CASE)):
        if not f.endswith(".json"):
            continue
        d = json.load(open(os.path.join(CASE, f)))
        geo = [by_pt.get((b[0], b[1])) for b in d["blocks"]]
        assert all(geo), "%s: %d blocks match no census point" % (d["id"], sum(1 for g in geo if not g))
        st = d.get("students")
        p = {}
        if st:
            cds = (enrol.get(d["id"]) or {}).get("cds")
            arr, _how = model.spread(cds, d["door"]["lon"], d["door"]["lat"], st["byLevel"], st["choice"])
            tot = float(arr.sum())
            p = {b["geoid"]: round(float(v) / tot, 7) for b, v in zip(model.blks, arr) if v / tot >= 1e-6}
        out = {
            "id": d["id"], "name": d["name"], "students": st["total"] if st else None,
            "how": st["how"] if st else None, "pSource": "tools/school-trips/school-gravity.py, data/school-case/gravity.json",
            "p": p,
            "geoid": geo, "walkFt": [b[3] for b in d["blocks"]], "carMin": [b[5] / 10.0 for b in d["blocks"]],
            "today": {k: [None if r is None else [r[0] / 10.0, r[1], off_safe_ft(r)] for r in rows] for k, rows in sorted(d["today"].items())},
            "model": {k: d["model"].get(k) for k in ("walkMph", "rideMph", "targetMin", "detour", "reachMi", "carMph", "carFixedMin", "carSpeedSrc")},
        }
        stable.write_json(os.path.join(OUT, f), out, separators=(",", ":"))
        print("  %s: %d blocks in reach, %d blocks with a share" % (d["id"], len(geo), len(p)))


if __name__ == "__main__":
    main()
