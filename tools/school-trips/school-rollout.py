#!/usr/bin/env python3
"""Citywide school rollout strategies year by year: children within 15 minutes of school on all-ages streets, cost and miles, for SFMTA's Safe School Connections order, kids per dollar, repave-aligned plan corridors, and SF Bike's Phase 1 school zones.

    pipeline/venv-step.py tools/school-trips/school-rollout.py      # writes site/data/school-rollout.json
    pipeline/venv-step.py tools/school-trips/school-rollout.py --reuse-zones   # take the zones run from the last output

Bryan, 2026-10-07: "have a way to do scenario building on a system-wide
level. To consider different ways of rolling stuff out and which types of
changes to prioritize first."

WHAT IS REUSED. Three of the four strategies come straight from
out/school-budget/strategies.json (scripts/school-budget-strategies.py), which
already gives, for each way of spending street miles, the children it brings
within 15 minutes of the nearest school of their level, counted once:
  * sfmta     SFMTA's draft Safe School Connections order, "SFMTA's criteria
              first, then cheapest link" (variant sfmta-criteria), at 5, 10,
              20 and 40 miles, with the number of school links each buys.
  * dollar    kids per dollar: the open pool ranked per central dollar
              (open/dollar/ej1x), item by item.
  * repave    the plan's corridors built as the paving crews reach them. The
              order is the paving schedule's, not chosen for children, so it
              gets the whole plan's average: children brought under 15 minutes
              with the whole plan built (scenario "plan") per centerline mile.
              [inference — mine]
The fourth is computed here:
  * sfbike    SF Bike's Phase 1 school zones (proposal p. 9: "car-free school
              streets and rigorously calmed school zones around all SFUSD
              schools"): every residential street edge within a quarter mile
              of every SFUSD-run school (public, not charter) made all-ages,
              with school-travel-time.py's model, pass 1 only, on both
              networks so the difference is like for like. Phase 1's other
              half, a "base grid" of at least three north-south and three
              east-west protected crosstown routes (p. 9), is not modelled:
              SF Bike names only examples, "Embarcadero to Ocean Beach, Fort
              Mason to Daly City" (p. 5), and drawing the rest would be ours.

PACE, the miles each strategy builds a year, each from a published figure:
  * sfmta     SFMTA gives Safe School Connections "up to 10 years" for all
              249 schools (SFMTA Board 2026-09-01, item 12, slide 8): 25
              school links a year.
  * dollar    the same dollars a year as the sfmta line, so the two compare at
              one budget: miles interpolated linearly inside the item that
              crosses the budget, so the line never spends more than SFMTA's.
  * repave    the larger of SFMTA's measured plan build rate (4.25 miles a
              year newly meeting the plan 2021-2026) and the repave lever's
              mid-recent 6.43 miles a year (out/repave-lever/lever.json), not
              their sum: plan miles built with a repave sit in both, and the
              overlap isn't measured. Both are per direction of travel, so
              halved to centerline miles, since a two-way street counts twice
              per direction. [inference — mine]
  * sfbike    Phase 1 is "Years 1-5 (2025-2029)" (p. 9): a fifth of the zones
              a year from 2026, finishing in 2030 since 2025 has passed.
Between the strategy's own points, children are interpolated linearly in
miles; past its last point a line holds flat.

COST: central (low, high) dollars per centerline mile by facility from
data/school-budget/unit-costs.json, as school-budget-value.py prices them;
zones at the full-toolkit calmed rate: central and high $0.65M, the UNC
high; low $0.25M, SFMTA's 2022 Slow Streets average of $0.2M with 2022 to
2026 prices (unit-costs.json's calmed central). No published figure sits above
the UNC high, so central and high are the same. [inference — mine]

THE MEASURE: children 5-17 within 15 minutes of the nearest school of their
level on all-ages streets, out of 78,337 (out/school-travel/summary.json),
and the same for 5-9 against SF Bike's goal of "at least 80% of
elementary-aged families" able "to ride to school" (p. 5). Walking counts in
our 15 minutes, so the two aren't the same measure; the page says so.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import importlib.util
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402

stt = paths.load("school-travel-time.py")
walknet = stt.walknet

OUT = os.path.join(ROOT, "site", "data", "school-rollout.json")
MI = 1609.344
ZONE_M = 1320 * 0.3048
ZONE_HW = {"residential", "living_street", "unclassified"}
YEARS = list(range(2026, 2037))
SSC_SCHOOLS, SSC_YEARS = 249, 10


def read(*p):
    return json.load(open(os.path.join(ROOT, *p)))


def interp(points, x):
    """Children at x miles from [(miles, children)], linear, flat past the last point."""
    pts = [(0.0, 0.0)] + sorted(points)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 > x0 else y1
    return pts[-1][1]


REUSE = {"on": False}


def miles_at_cost(dol, budget):
    """Miles the per-dollar order builds for exactly `budget`, from [(cumulative miles, children, cumulative $M)]: linear inside the item that crosses it."""
    if budget <= 0:
        return 0.0
    prev = (0.0, 0, 0.0)
    for d in dol:
        if d[2] >= budget:
            span = d[2] - prev[2]
            f = (budget - prev[2]) / span if span > 0 else 1.0
            return prev[0] + f * (d[0] - prev[0])
        prev = d
    return dol[-1][0]


def zones_run():
    """Children 5-17 and 5-9 over 15 minutes today and with every SFUSD school's quarter-mile zone calmed, pass 1 on both."""
    t0 = time.time()
    stt.FAST["on"] = stt.rcsp.available()
    assert stt.FAST["on"], "needs the compiled searches (lib/rcsp.c)"
    net = stt.Net(cache=True)
    G = net.G
    kids = {r["geoid"]: r for r in read("data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    pts = {r["geoid"]: r for r in read("data", "extract", "census-blocks", "2020.json")["records"]}
    blocks = []
    for gid in sorted(kids):
        k = kids[gid]
        if k["a5_9"] + k["a10_14"] + k["a15_17"] == 0:
            continue
        p = pts[gid]
        blocks.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "a5_9": k["a5_9"], "a10_14": k["a10_14"],
                       "a15_17": k["a15_17"], "ends": net.ends(p["lon"], p["lat"])})
    schools, _dropped, _priv = stt.load_schools()
    for s in schools:
        s["ends"] = net.ends(s["lon"], s["lat"])
    today_lines, plan_lines, _meta = stt.all_ages_lines()
    line_edges, _weak = stt.edges_of(net, today_lines + plan_lines, cache=True)
    n_e = len(G.eu)
    today = [False] * n_e
    for k, _ in today_lines:
        for e in line_edges.get(k, ()):
            today[e] = True
    cde = {r["school"]: r for r in read("data", "extract", "schools", "cde-sf.json")["records"]}
    sfusd = [s for s in schools if not s["private"] and cde.get(s["name"], {}).get("charter") == "N"]
    cells = collections.defaultdict(list)
    for s in sfusd:
        x, y = walknet.xy(s["lon"], s["lat"])
        cells[(int(x // ZONE_M), int(y // ZONE_M))].append((x, y))
    zone = [False] * n_e
    for e in range(n_e):
        if G.ehw[e] not in ZONE_HW or today[e]:
            continue
        u, v = G.eu[e], G.ev[e]
        mx, my = (G.x[u] + G.x[v]) / 2, (G.y[u] + G.y[v]) / 2
        cx, cy = int(mx // ZONE_M), int(my // ZONE_M)
        if any(math.hypot(mx - a, my - b) <= ZONE_M for dx in (-1, 0, 1) for dy in (-1, 0, 1) for a, b in cells.get((cx + dx, cy + dy), ())):
            zone[e] = True
    zone_mi = sum(net.L[e] for e in range(n_e) if zone[e]) / MI
    withz = [a or b for a, b in zip(today, zone)]
    out = {}
    for name, bk in (("today", today), ("zones", withz)):
        over = collections.Counter()
        for band, lvl, label in stt.BANDS:
            L = stt.Level(net, lvl, [s for s in schools if lvl in s["levels"]], blocks)
            res = stt.level_times(net, bk, L, blocks)
            for b, r in zip(blocks, res):
                if r is None or r[0] > stt.TARGET_MIN * 60 + 1e-9:
                    over[label] += b[band]
        out[name] = dict(over)
        print("  %s: over 15 minutes %s (%.0fs)" % (name, dict(over), time.time() - t0))
    return {"sfusd_schools": len(sfusd), "zone_mi": round(zone_mi, 2), "over_pass1": out}


def main():
    REUSE["on"] = "--reuse-zones" in sys.argv[1:]
    st = read("out", "school-budget", "strategies.json")
    summary = read("out", "school-travel", "summary.json")
    costs = read("data", "school-budget", "unit-costs.json")["types"]
    total = summary["children"]
    over_today = summary["over_target"]["today"]
    within0 = {"5-17": total["5-17"] - over_today["5-17"], "5-9": total["5-9"] - over_today["5-9"]}

    def price(mby):
        return {c: sum(costs[t][c] * m for t, m in mby.items()) for c in ("low", "central", "high")}

    # SFMTA's order: its own four budget points.
    ssc = sorted((s for s in st["scenarios"] if s["variant"] == "sfmta-criteria"), key=lambda s: s["budget_mi"])
    ssc_pts = [(s["spent_mi"], s["brought_under_15"], s["brought_under_15_by_band"]["a5_9"], s["links"], price(s["miles_by_type"])["central"]) for s in ssc]
    per_year_links = SSC_SCHOOLS / SSC_YEARS

    def ssc_at_links(n):
        pts = [(0, 0, 0, 0, 0.0)] + ssc_pts
        for a, b in zip(pts, pts[1:]):
            if n <= b[3]:
                f = (n - a[3]) / (b[3] - a[3]) if b[3] > a[3] else 1
                return tuple(a[i] + f * (b[i] - a[i]) for i in range(5))
        return pts[-1]

    # Kids per dollar, item by item.
    order = st["orders"]["open/dollar/ej1x"]
    dol, cum_mi, cum_usd = [], 0.0, 0.0
    for it in order:
        cum_mi += it["cost_mi"]
        cum_usd += it["cost_musd"]
        dol.append((cum_mi, it["cumulative_children"], cum_usd))
    dol_scen = sorted((s for s in st["scenarios"] if s["variant"] == "open/dollar/ej1x"), key=lambda s: s["budget_mi"])
    dol_young = [(s["spent_mi"], s["brought_under_15_by_band"]["a5_9"]) for s in dol_scen]

    plan = next(s for s in st["scenarios"] if s["key"] == "plan")
    plan_cost = price(plan["miles_by_type"])
    plan_per_mi = plan["brought_under_15"] / plan["spent_mi"]
    plan_young_per_mi = plan["brought_under_15_by_band"]["a5_9"] / plan["spent_mi"]
    lever = read("out", "repave-lever", "lever.json")
    assert lever["mileBasis"] == "per direction of travel", lever["mileBasis"]
    BUILT_DIR = lever["builtRate"]["milesPerYear"]
    LEVER_DIR = next(r["milesPerYear"] for r in lever["lever"] if r["reading"] == "mid-recent")
    repave_pace = max(BUILT_DIR, LEVER_DIR) / 2

    if REUSE["on"] and os.path.exists(OUT):
        prev = read("site", "data", "school-rollout.json")["zones"]
        z = {"sfusd_schools": prev["sfusd_schools"], "zone_mi": prev["miles"], "over_pass1": prev["pass1_over"]}
        print("  zones: reused from %s" % os.path.relpath(OUT, ROOT))
    else:
        z = zones_run()
    zo = z["over_pass1"]
    zone_gain = {"5-17": sum(zo["today"].values()) - sum(zo["zones"].values()),
                 "5-9": zo["today"].get("5-9", 0) - zo["zones"].get("5-9", 0)}
    zone_cost = {"low": costs["calmed"]["central"] * z["zone_mi"], "central": costs["calmed"]["high"] * z["zone_mi"],
                 "high": costs["calmed"]["high"] * z["zone_mi"]}

    lines = {k: [] for k in ("sfmta", "dollar", "repave", "sfbike")}
    for i, y in enumerate(YEARS):
        n_years = i + 1
        links = min(per_year_links * n_years, ssc_pts[-1][3])
        mi, kids, young, _l, usd = ssc_at_links(links)
        lines["sfmta"].append({"year": y, "miles": round(mi, 1), "kids": round(kids), "young": round(young), "cost": round(usd, 1)})
        # Same dollars as SFMTA's line that year.
        budget = usd
        mi2 = miles_at_cost(dol, budget)
        kids2 = interp([(d[0], d[1]) for d in dol], mi2)
        lines["dollar"].append({"year": y, "miles": round(mi2, 1), "kids": round(kids2), "young": round(interp(dol_young, mi2)),
                                "cost": round(min(budget, dol[-1][2]), 1)})
        mi3 = min(repave_pace * n_years, plan["spent_mi"])
        lines["repave"].append({"year": y, "miles": round(mi3, 1), "kids": round(plan_per_mi * mi3), "young": round(plan_young_per_mi * mi3),
                                "cost": round(plan_cost["central"] * mi3 / plan["spent_mi"], 1)})
        f = min(1.0, n_years / 5)
        lines["sfbike"].append({"year": y, "miles": round(z["zone_mi"] * f, 1), "kids": round(zone_gain["5-17"] * f),
                                "young": round(zone_gain["5-9"] * f), "cost": round(zone_cost["central"] * f, 1)})
    out = {
        "years": YEARS,
        "children": {"5-17": total["5-17"], "5-9": total["5-9"]},
        "within_today": within0,
        "lines": lines,
        "pace": {"sfmta_links_per_year": per_year_links, "repave_centerline_mi_per_year": round(repave_pace, 2),
                 "built_dir_mi_per_year": BUILT_DIR, "lever_dir_mi_per_year": LEVER_DIR},
        "zones": {"sfusd_schools": z["sfusd_schools"], "miles": z["zone_mi"], "gain": zone_gain, "pass1_over": zo,
                  "cost": {k: round(v, 1) for k, v in zone_cost.items()}},
        "dollar_pool": {"miles": round(dol[-1][0], 1), "kids": dol[-1][1], "cost": round(dol[-1][2], 1)},
        "sfmta_last": {"miles": round(ssc_pts[-1][0], 1), "links": ssc_pts[-1][3]},
        "plan": {"miles": round(plan["spent_mi"], 1), "kids": plan["brought_under_15"], "cost": {k: round(v, 1) for k, v in plan_cost.items()}},
        "sources": {"strategies": "out/school-budget/strategies.json", "travel": "out/school-travel/summary.json",
                    "costs": "data/school-budget/unit-costs.json", "repave": "out/repave-lever/lever.json"},
    }
    stable.write_json(OUT, out, indent=1)
    for k, v in lines.items():
        print("  %-7s 2030: %s; 2035: %s" % (k, v[4], v[9]))
    print("  wrote %s" % os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
