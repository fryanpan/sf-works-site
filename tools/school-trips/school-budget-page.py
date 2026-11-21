#!/usr/bin/env python3
"""Write the school bikeway budget page's data (site/data/school-budget.json) from scripts/school-budget-value.py's output.

    tools/school-trips/school-budget-page.py

The page is site/src/pages/transportation-schools-budget.mjs, served at
/transportation/bike/schools/budget and hidden in production
(site/src/features.mjs). It compares, at 5, 10, 20 and 40 miles of street,
the best version of each bikeway strategy by children brought within 15
minutes of school per $1M, against SFMTA's Safe School Connections order
(link each school to the network, cheapest link first). This script copies
only the figures that page and About the Data print, out of
out/school-budget/value.json, so the site never reads outside site/.

Each strategy at a budget is its family's best variant by children per $1M,
counted plainly (value.json by_budget[b].families[f].w1). The ratio to SFMTA's
order is recomputed here and asserted equal to value.json's own winner ratio,
so the page cannot print a ratio the data does not support. A run with no new
input leaves the file byte-identical.

Miles here are street (centerline) miles, the unit the budgets and the unit
costs are set in, not the per-direction miles the rest of the site counts.
The file says so in `mileBasis`, and the page says so in words.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
from decimal import Decimal, ROUND_HALF_UP
import json
import os
import re
import sys

ROOT = paths.ROOT
SRC = os.path.join(ROOT, "out", "school-budget", "value.json")
OUT = os.path.join(ROOT, "site", "data", "school-budget.json")

# The date value.json was last regenerated: 2026-10-04, by commit 2b9f406
# (the traffic re-pricing test). value.json carries no run stamp of its own
# (its only date is the Bike Comfort Index read date), and the wall clock is
# not the data's date, so it is set here and moved when value.json is
# regenerated. If value.json gains a run stamp, main() reads it instead.
MODEL_RUN = "2026-10-04"
FULL_SPEND = 0.95  # as scripts/school-budget-value.py picks its winners

BUDGETS = ("5", "10", "20", "40")
# value.json family name -> page id, label. Ordered as the page lists them.
FAMILIES = (
    ("Mix", "mix", "Best mix of all three"),
    ("Off-plan calmed streets", "offplan", "Quiet side streets not in the bike plan"),
    ("Plan corridors", "plan", "Streets in SFMTA's bike plan"),
    ("School links chosen by children", "links", "School links picked by kids reached"),
    ("SFMTA last block (cheapest link first)", "sfmta", "SFMTA's order, cheapest link first"),
)


def r0(v):
    # Half up, as the write-up and value.md readers round: 170.5 is 171.
    # Python's round() goes to even and would print 170.
    return int(Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def r1(v):
    return float(Decimal(str(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def main():
    with open(SRC) as f:
        v = json.load(f)
    by_key = {s["key"]: s for s in v["scenarios"]}
    u = v["assumptions"]["unit_costs_musd_per_mi"]

    budgets = []
    for b in BUDGETS:
        bb = v["by_budget"][b]
        rows = {}
        for fam, fid, _ in FAMILIES:
            s = by_key[bb["families"][fam]["w1"]]
            rows[fid] = {
                "miles": r1(s["spent_mi"]),
                "fullSpend": s["full_spend"],
                "cost": {k: s["cost_musd"][k] for k in ("low", "central", "high")},
                "kids": s["children"],
                "kidsEj": s["children_ej"],
                "perM": r0(s["per_musd"]["w1"]),
                "perMEj2": r0(s["per_musd"]["w2"]),
            }
        win = bb["winners"]["w1"]
        winner = by_key[win["key"]]
        sf = rows["sfmta"]["perM"]
        ratio = win["per_musd"] / win["sfmta_per_musd"]
        if abs(ratio - win["ratio_to_sfmta"]) > 0.01:
            sys.exit(f"school-budget-page: {b} mi ratio {ratio:.2f} != value.json {win['ratio_to_sfmta']}")
        if winner["family"] != "Mix" or r0(win["per_musd"]) != rows["mix"]["perM"]:
            sys.exit(f"school-budget-page: {b} mi winner is {win['key']}, not the mix row the page draws")
        worst = bb["winner_vs_sfmta_worst_case"]
        if abs(sum(m * u[t]["high"] for t, m in winner["miles_by_type"].items()) - winner["cost_musd"]["high"]) > 0.02:
            sys.exit(f"school-budget-page: {b} mi winner's high cost isn't every type at its high unit cost")
        cost_path_central = sum(m * u[t]["central" if t == "path" else "high"] for t, m in winner["miles_by_type"].items())
        path_mi = winner["miles_by_type"].get("path", 0)
        links_full = max((s for s in v["scenarios"] if s["family"] == "School links chosen by children"
                          and s["budget_mi"] == int(b) and s["spent_mi"] >= FULL_SPEND * int(b)),
                         key=lambda s: s["per_musd"]["w1"])
        sens = bb["sensitivity_best_w1"]
        most = by_key[bb["most_children"]]
        budgets.append({
            "budget": int(b),
            "rows": rows,
            "ratio": r1(ratio),
            # Like for like: the best links variant that spent the budget, by
            # the same rule value.py uses for winners.
            "linksRatio": r1(links_full["per_musd"]["w1"] / by_key[bb["sfmta"]]["per_musd"]["w1"]),
            "linksKey": links_full["key"],
            # The winner was picked with Environmental Justice kids counted
            # twice, though it is also the best counted plainly.
            "winnerEj2": winner["weight"] == 2,
            # Mix miles by where they come from: plan, off-plan, link.
            "mixKinds": {k: r1(m) for k, m in sorted(winner["miles_by_kind"].items())},
            "ratioEj2": r1(bb["winners"]["w2"]["per_musd"] / bb["winners"]["w2"]["sfmta_per_musd"]),
            "mostKids": {"kids": most["children"], "cost": most["cost_musd"]["central"]},
            "mixPath": {"miles": round(path_mi, 3), "highCost": round(path_mi * u["path"]["high"], 2)},
            # Best strategy against SFMTA's order under each cost test, as
            # [best per $1M, SFMTA per $1M].
            "tests": {
                "costEnds": [r0(worst["winner_children_per_musd_at_high_cost"]), r0(worst["sfmta_children_per_musd_at_low_cost"])],
                # The same, but off-street paths at their central cost: the
                # path high ($6.43M a mile) is a peer maximum, not an SF figure.
                "costEndsPathCentral": [r0(winner["children"] / cost_path_central), r0(worst["sfmta_children_per_musd_at_low_cost"])],
                "busyCalmed": [r0(sens["busy_calmed_as_separated"]["per_musd"]), r0(sens["busy_calmed_as_separated"]["sfmta_per_musd"])],
                "sharedOnBusy": [r0(sens["not_residential_as_separated"]["per_musd"]), r0(sens["not_residential_as_separated"]["sfmta_per_musd"])],
                "perProject": [r0(sens["per_project_fixed"]["per_musd"]), r0(sens["per_project_fixed"]["sfmta_per_musd"])],
            },
        })

    a = v["assumptions"]
    base = v["baseline"]
    traffic_read = re.search(r"read (\d{4}-\d{2}-\d{2})", v["grade_and_traffic"]["traffic"])
    ej5 = {w: by_key[f"open/dollar/{w}/5"]["children_ej"] for w in ("ej1x", "ej2x")}
    # Picks in the 5-mile winner that aren't side streets at all, though the
    # centerline file classes them residential: freeway ramps and Alemany Blvd.
    # (value.json flags any name with Ramp, Hwy, Fwy or Blvd; Font Blvd is a
    # residential street by SF State and stays.) About the Data names them.
    w5 = by_key[v["by_budget"]["5"]["winners"]["w1"]["key"]]
    not_quiet = [
        {"street": s["street"], "kids": s["children"]}
        for s in v["off_plan_streets"][w5["variant"]]
        if s["not_a_quiet_street"] and s["first_pick_mi"] <= w5["spent_mi"] and re.search(r"Ramp|Alemany", s["street"])
    ]
    out = {
        "notQuiet5": not_quiet,
        "note": "Written by tools/school-trips/school-budget-page.py from the school bikeway budget model. Do not edit by hand.",
        "mileBasis": "centerline",
        "modelRun": v.get("run_date") or v.get("generated") or MODEL_RUN,
        "trafficRead": traffic_read.group(1) if traffic_read else None,
        "families": [{"id": fid, "label": lab} for _, fid, lab in FAMILIES],
        "budgets": budgets,
        "scenarios": len(v["scenarios"]),
        "kids": sum(base["children_by_band"].values()),
        "kidsOverToday": base["over_15_today"],
        "kidsOverToday15to17": base["over_15_today_by_band"]["a15_17"],
        "kidsEj": base["children_ej"],
        "ejReached5": {"once": ej5["ej1x"], "twice": ej5["ej2x"]},
        "unitCosts": {k: a["unit_costs_musd_per_mi"][k] for k in ("separated", "calmed", "path", "car_free")},
        "perProjectFixed": a["per_link_fixed_musd"],
        "carEffect": a["effect_pp"],
        "carFraction": a["car_fraction"]["central"],
        "carPointsMax": max(s["car_points"]["high"] for s in v["scenarios"]),
    }
    text = json.dumps(out, indent=1, sort_keys=True) + "\n"
    try:
        with open(OUT) as f:
            if f.read() == text:
                print(f"school-budget-page: {os.path.relpath(OUT, ROOT)} unchanged")
                return
    except FileNotFoundError:
        pass
    with open(OUT, "w") as f:
        f.write(text)
    print(f"school-budget-page: wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
