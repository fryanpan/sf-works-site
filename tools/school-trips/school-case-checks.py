#!/usr/bin/env python3
"""The school case study model's checks for its About the Model page: kids within 15 minutes at 8, 10 and 12 mph riding speed, per shown school, plus the hand-collected Google Maps route spot check.

    pipeline/venv-step.py tools/school-trips/school-case-checks.py

Bryan, 2026-10-07: "think about how you'll document the model and show it's
accurate enough or at least based in common practice." This writes the two
checks that need the routing model, so the page reads figures from a script
rather than from a hand edit.

  * Speed sensitivity. tools/school-trips/school-case.py's World and the first half of
    its build(): the same blocks, door and network, timed today on both
    definitions of a safe street with the riding speed set to 8, 10 and 12 mph
    (walking stays 2 mph). Only today's network is timed, not the options, so
    a run of every school takes seconds. The 10 mph run must reproduce the
    within-15 counts in site/data/school-case/<id>.json exactly; the script
    stops if it doesn't, since that would mean this harness drifted from the
    build. The reach pool grows with the speed (15 minutes at that speed, at
    least build()'s 2.5 miles), so at 12 mph a block between 2.5 and 3 miles
    that rides nearly the whole way is counted. Each school's counts must not
    fall as the speed rises, and somewhere in the run they must rise, or the
    speed override did nothing.
  * Route spot check. data/school-case/route-spot-check.json, read by hand in
    Google Maps (walking and cycling directions, no API) on the date it
    records. This script only joins each row to the model's block (its
    shortest walk in feet, minutes and safe share) so the page prints both
    sides from one file.

WRITES site/data/school-case-checks.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

OUT = os.path.join(ROOT, "site", "data", "school-case-checks.json")
SPOT = os.path.join(ROOT, "data", "school-case", "route-spot-check.json")
SPEEDS = (6.0, 8.0, 10.0, 12.0)


def load_case():
    sc = paths.load("school-case.py")
    return sc


def pool_of(sc, world, s, reach_mi):
    """build()'s blocks for one school: the door, its seeds and the kids within reach by street."""
    G, net = world.G, world.net
    door = s["door"]
    dx, dy = sc.walknet.xy(door["lon"], door["lat"])
    bands = sc.band_of_grades(s["grades"])
    radius = reach_mi * sc.MI
    sub = sc.Sub(world, dx, dy, radius + sc.SUB_PAD_M)
    seeds = sc.door_ends(net, door["lon"], door["lat"])
    walk_arr = sub.search([False] * len(G.eu), seeds, 0.0)
    blocks = []
    for b in world.blocks:
        k = sum(b[sc.BAND_KEYS[x]] for x in bands)
        if not k:
            continue
        bx, by = sc.walknet.xy(b["lon"], b["lat"])
        if math.hypot(bx - dx, by - dy) > radius:
            continue
        ends = net.ends(b["lon"], b["lat"])
        w = sc.INF
        for node, c, along, _e in ends:
            u = sub.ix.get(node)
            if u is not None and walk_arr[2][u] < sc.INF:
                w = min(w, walk_arr[2][u] + c + along)
        if w > radius:
            continue
        blocks.append({"kids": k, "ends": ends, "walk": w})
    return sub, seeds, blocks


def main():
    sc = load_case()
    stt = sc.stt
    drop = sc.read("data", "school-case", "dropoff.json")
    shown = [s for s in drop["schools"] if s["id"] not in sc.HELD
             and os.path.exists(os.path.join(sc.OUT, "%s.json" % s["id"]))]
    world = sc.World()
    rb10 = stt.RB
    speed = {}
    for s in shown:
        shipped = sc.read("site", "data", "school-case", "%s.json" % s["id"])
        want = {d: sum(b[2] for b, r in zip(shipped["blocks"], shipped["today"][d]) if r and r[0] <= 150)
                for d in shipped["today"]}
        runs, pool = {}, None
        for mph in SPEEDS:
            reach = max(sc.REACH_MI, 15.0 / 60.0 * mph)
            sub, seeds, blocks = pool_of(sc, world, s, reach)
            walk = [b["walk"] for b in blocks]
            flat = sc.flat_ends(blocks)
            if mph == 10.0:
                pool = sum(b["kids"] for b in blocks)
            stt.RB = rb10 * 10.0 / mph
            runs[str(int(mph))] = {
                d: sum(b["kids"] for b, x in zip(blocks, sc.times_to(world, sub, seeds, bike, blocks, walk, flat))
                       if x and x[0] <= 150)
                for d, bike in (("brp", world.brp), ("sfbike", world.sfb))}
            stt.RB = rb10
        for d in ("brp", "sfbike"):
            seq = [runs[str(int(m))][d] for m in SPEEDS]
            assert seq == sorted(seq), "%s %s falls as speed rises: %s" % (s["id"], d, seq)
        if runs["10"] != want:
            sys.exit("school-case-checks: %s at 10 mph gives %s, the page's data says %s; rerun tools/school-trips/school-case.py"
                     % (s["id"], runs["10"], want))
        speed[s["id"]] = {"pool": pool, "within": runs}
        print("  %s: %s" % (s["id"], runs))
    if not any(len({v["within"][str(int(m))]["brp"] for m in SPEEDS}) > 1 for v in speed.values()):
        sys.exit("school-case-checks: every school gives the same count at every speed; the speed override did nothing")
    spot = None
    if os.path.exists(SPOT):
        spot = json.load(open(SPOT))
        kb = sc.read("site", "data", "school-case", "%s.json" % spot["school"])
        for row in spot["routes"]:
            b, r = kb["blocks"][row["block"]], kb["today"]["brp"][row["block"]]
            assert [b[0], b[1]] == row["from"], "spot check block %d moved; re-pick it" % row["block"]
            row["model"] = {"walkFt": b[3], "kids": b[2], "min": r[0] / 10.0 if r else None, "safePct": r[1] if r else None}
    stable.write_json(OUT, {"rideMph": list(SPEEDS), "walkMph": stt.WALK_MPH, "speed": speed, "spotCheck": spot},
                      indent=1, sort_keys=True)
    print("  wrote %s" % os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
