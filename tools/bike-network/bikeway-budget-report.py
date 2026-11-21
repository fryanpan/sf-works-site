#!/usr/bin/env python3
"""The data behind the bikeway budget report: which street blocks School Trips' integer program picks at each budget, on
or off the Biking and Rolling Plan, and the checks that say how far to trust the picks.

    tools/bike-network/bikeway-budget-report.py     # writes out/bikeway-report/data.json; scripts/bikeway-budget-report.mjs draws it

Bryan, 2026-10-17: "give me a comprehensive report and map of what the BrP and off plan routes analysis lead to and why
are you sure it's correct and show me the maps at different budget levels".

INPUTS. out/school-sim/segments.json (tools/school-trips/school-segments-ip.py: every candidate chunk with its blocks, and each
budget's chosen chunks, checked counts, the program's promise and the solver's gap); today's all-ages network and the
plan's unbuilt all-ages blocks exactly as the sim reads them (lib/school-travel-time.py all_ages_lines with
brp_rule, Bryan 2026-10-15: "Protected only."); SFMTA's upcoming bikeways (site/data/bike-history/planned.json), which
the sim counts as built; the school doors (site/data/school-sim/index.json). With --planonly PATH (out/school-sim/segments-planonly.json), a second
segments.json from the same program run with SEGMENTS_OFFPLAN=0 adds the plan-only comparison.

A block is on the plan when it is in the plan's network (north-star traced.geojson), whether the plan draws it as
all-ages or as a shared lane the program upgrades to separated; every other chosen block is off the plan. Car trips removed are the program's checked count, carTripsRemoved: the sim's
rebuilt mode choice over the full route search on each budget's network, year 10, central case (Bryan, 2026-10-18,
replacing the 10/20/30% switch rates), the same figure the loop tests its promise against. Reads committed outputs only, so it is exempt from the incremental-updater
rule; rerun it after tools/school-trips/school-sim.py --segments."""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

OUT = os.path.join(ROOT, "out", "bikeway-report")
TOUCH_FT = 60.0   # blocks this close count as joined, and a piece this close to a bikeway counts as connected: our assumption


def _stt():
    m = paths.load("school-travel-time.py")
    return m


def miles(pts):
    lat0 = math.radians(37.76)
    return sum(math.hypot(math.radians(b[0] - a[0]) * math.cos(lat0), math.radians(b[1] - a[1])) * 3958.8
               for a, b in zip(pts, pts[1:]))


def street(name):
    """'34TH AVE' as '34th Ave', '01ST ST' as '1st St'."""
    return " ".join((w.lstrip("0") or w).lower() if w[:1].isdigit() else w.capitalize() for w in name.split())


def rnd(lines):
    return [[[round(x, 5), round(y, 5)] for x, y in ln] for ln in lines]


def islands(seg, b, net_pts):
    """Miles and count of a budget's connected pieces (blocks whose ends meet within TOUCH_FT) that come nowhere within
    TOUCH_FT of today's or an upcoming all-ages bikeway. They serve schools nearby under the 1,000 ft gap rule but connect
    to no network."""
    from scipy.spatial import cKDTree
    import numpy as np
    by_id = {c["id"]: c for c in seg["chunks"]}
    lat0 = math.radians(37.76)
    fx, fy = 364320.0 * math.cos(lat0), 364320.0
    blk = [pts for cid in b["chunks"] for pts in by_id[cid]["pts"]]
    if not blk:
        return 0, 0.0
    ends = np.array([[(q[0] * fx, q[1] * fy) for q in (pts[0], pts[-1])] for pts in blk]).reshape(-1, 2)
    par = list(range(len(blk)))
    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i, j in cKDTree(ends).query_pairs(TOUCH_FT):
        par[find(i // 2)] = find(j // 2)
    nt = cKDTree(net_pts)
    touch = {}
    for k, pts in enumerate(blk):
        r = find(k)
        hit = any(nt.query_ball_point((q[0] * fx, q[1] * fy), TOUCH_FT) for q in pts)
        touch[r] = touch.get(r, False) or hit
    lone = {r for r, t in touch.items() if not t}
    return len(lone), round(sum(miles(pts) for k, pts in enumerate(blk) if find(k) in lone), 1)


def slow_keys(stt):
    """Today's all-ages keys that are Slow Streets."""
    comp = stt.read(stt.BIKE, "components.json")["blocks"]
    return {k for k, c in comp.items() if c.get("s") is not None}


NEEDS = {"top": ("chunks", "budgets", "candidates", "menu", "program"),
         "budget": ("budgetM", "chunks", "centerlineMi", "costM", "carTripsRemoved", "promise"),
         "chunk": ("id", "street", "cnns", "pts", "mi")}


def require(seg, path):
    """Stop with the fields a segments.json lacks, before any is read, so an old or partial file names what is missing."""
    miss = ["top-level %s" % k for k in NEEDS["top"] if k not in seg]
    for b in seg.get("budgets", []):
        miss += ["$%sM %s" % (b.get("budgetM", "?"), k) for k in NEEDS["budget"] if b.get(k) is None]
        if "promise" in b and b["promise"].get("carTrips") is None:
            miss.append("$%sM promise.carTrips" % b.get("budgetM", "?"))
    for c in seg.get("chunks", [])[:1]:
        miss += ["chunk %s" % k for k in NEEDS["chunk"] if k not in c]
    if miss:
        sys.exit("bikeway-budget-report: %s lacks %s; rerun tools/school-trips/school-sim.py --segments" % (path, ", ".join(miss[:8])))


def budgets_of(seg, plan_cnn, net_pts=None):
    """Each budget's chosen blocks split on and off the plan, with the program's checks."""
    by_id = {c["id"]: c for c in seg["chunks"]}
    out = []
    prev = None
    for b in sorted(seg["budgets"], key=lambda x: x["budgetM"]):
        on = off = calm = 0.0
        on_cost = off_cost = 0.0
        streets = {}
        for cid in b["chunks"]:
            c = by_id[cid]
            for cnn, pts in zip(c["cnns"], c["pts"]):
                m = miles(pts)
                if cnn.lstrip("0") in plan_cnn:
                    on += m
                else:
                    off += m
            streets[c["street"]] = streets.get(c["street"], 0.0) + c["mi"]
            calm += c.get("calmMi", 0.0)
        mi_of = lambda ids: sum(miles(p) for cid in ids for p in by_id[cid]["pts"])
        kept = round(mi_of(set(prev["chunks"]) & set(b["chunks"])) / mi_of(prev["chunks"]), 3) if prev and prev["chunks"] else None
        n_lone, lone_mi = islands(seg, b, net_pts) if net_pts is not None else (None, None)
        prev = b
        out.append({"budgetM": b["budgetM"], "chunks": len(b["chunks"]), "mi": round(b["centerlineMi"], 1),
                    "costM": round(b["costM"], 2), "onPlanMi": round(on, 1), "offPlanMi": round(off, 1),
                    "carTrips": round(b["carTripsRemoved"]), "promiseCarTrips": round(b["promise"]["carTrips"]),
                    "checkedOverPromise": round(b["carTripsRemoved"] / b["promise"]["carTrips"], 3) if b["promise"]["carTrips"] else None,
                    "keptFromSmaller": kept, "calmMi": round(calm, 1), "lonePieces": n_lone, "loneMi": lone_mi,
                    "topStreets": [[street(s), round(m, 2)] for s, m in sorted(streets.items(), key=lambda kv: (-kv[1], kv[0]))[:8]]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--planonly", help="a segments.json run with SEGMENTS_OFFPLAN=0, for the plan-only comparison")
    a = ap.parse_args()
    stt = _stt()
    today, plan, _meta = stt.all_ages_lines(brp_rule=True)
    plan_cnn = {str(f["properties"]["cnn"]).lstrip("0") for f in stt.read(stt.NS, "traced.geojson")["features"]}
    planned = json.load(open(os.path.join(ROOT, "site", "data", "bike-history", "planned.json")))
    upcoming = [b["pts"] for pr in planned["projects"] for b in pr["blocks"] if len(b.get("pts") or []) >= 2]
    seg_path = os.path.join(ROOT, "out", "school-sim", "segments.json")
    seg = json.load(open(seg_path))
    require(seg, seg_path)
    lat0 = math.radians(37.76)
    net_pts = [(q[0] * 364320.0 * math.cos(lat0), q[1] * 364320.0) for pts in [p for _, p in today] + upcoming for q in pts]
    by_id = {c["id"]: c for c in seg["chunks"]}
    chosen = sorted({cid for b in seg["budgets"] for cid in b["chunks"]})
    first = {}
    for b in sorted(seg["budgets"], key=lambda x: x["budgetM"]):
        for cid in b["chunks"]:
            first.setdefault(cid, b["budgetM"])
    blocks = []
    for cid in chosen:
        c = by_id[cid]
        ins = [b["budgetM"] for b in seg["budgets"] if cid in b["chunks"]]
        for cnn, pts in zip(c["cnns"], c["pts"]):
            blocks.append({"chunk": cid, "street": street(c["street"]), "onPlan": cnn.lstrip("0") in plan_cnn,
                           "budgets": ins, "line": rnd([pts])[0]})
    idx = json.load(open(os.path.join(ROOT, "site", "data", "school-sim", "index.json")))
    schools = [[round(s["lon"], 5), round(s["lat"], 5)] for s in idx["schools"] if s.get("lon")]
    doc = {"note": "Written by tools/bike-network/bikeway-budget-report.py from out/school-sim/segments.json; drawn by scripts/bikeway-budget-report.mjs.",
           "candidates": {k: seg["candidates"].get(k) for k in ("offplanBlocks", "planBlocks", "dropped", "continued", "offplanConflicts", "steep", "muniSeparated")},
           "nested": seg.get("nested", False), "calmCapMi": seg.get("calmCapMi"),
           "slowStreetMi": round(sum(miles(p) for k, p in today if k in slow_keys(stt)), 1),
           "program": {"pairs": seg["menu"]["pairs"], "routes": seg["menu"]["routes"]},
           "menuDoubling": seg.get("menuDoubling"), "parallelRule": seg.get("parallelRule"),
           "budgets": budgets_of(seg, plan_cnn, net_pts),
           "network": {"todayMi": round(sum(miles(p) for _, p in today), 1), "upcomingMi": round(sum(miles(p) for p in upcoming), 1),
                       "planUnbuiltMi": round(sum(miles(p) for _, p in plan), 1)},
           "lines": {"today": rnd([p for _, p in today]), "upcoming": rnd(upcoming), "planUnbuilt": rnd([p for _, p in plan])},
           "blocks": blocks, "schools": schools}
    if a.planonly:
        po = json.load(open(a.planonly))
        require(po, a.planonly)
        doc["planOnly"] = budgets_of(po, plan_cnn)
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(os.path.join(OUT, "data.json"), doc, separators=(",", ":"))
    for b in doc["budgets"]:
        print("  $%sM: %.1f mi (%.1f on plan, %.1f off), %d car trips checked (%d promised)"
              % (b["budgetM"], b["mi"], b["onPlanMi"], b["offPlanMi"], b["carTrips"], b["promiseCarTrips"]))


if __name__ == "__main__":
    main()
