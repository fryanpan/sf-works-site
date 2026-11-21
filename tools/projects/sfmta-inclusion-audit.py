#!/usr/bin/env python3
"""Measure which SFMTA projects the Current Projects list takes and leaves out, and draw a seeded sample of the left-out ones to check by hand.

    tools/projects/sfmta-inclusion-audit.py              # counts, as markdown
    tools/projects/sfmta-inclusion-audit.py --sample 30  # plus 30 left-out projects to read

Reads out/coordination/sfmta-decisions.json (every SFMTA project on the layer
and in the sitemap, with tools/projects/coordination-projects.py's decision and
reason), site/data/coordination.json, out/project-record/project-blocks.json
and the plan's traced network. Prints the measures behind
notes/transportation-audit-2026-09/sfmta-inclusion.md. The sample is drawn
with a fixed seed, so the same run reads the same projects.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import json
import os
import random
import re

ROOT = paths.ROOT
DECISIONS = os.path.join(ROOT, "out", "coordination", "sfmta-decisions.json")
COORD = os.path.join(ROOT, "site", "data", "coordination.json")
BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")
TRACED = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
FINISHED = ("Completed", "Project Evaluation", "test")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    args = ap.parse_args()
    dec = json.load(open(DECISIONS))
    rows = dec["decisions"]
    coord = json.load(open(COORD))
    plan = {f["properties"]["cnn"] for f in json.load(open(TRACED))["features"]}
    blocks = json.load(open(BLOCKS))["projects"]
    listed_ids = {p["id"] for p in coord["projects"]}
    # A layer project merged into a listed feed row, or the reverse, is listed.
    for p in coord["projects"]:
        for l in p["links"]:
            m = re.search(r"sfmta\.com/node/(\d+)", l["url"])
            if m:
                listed_ids.add("sfmta:" + m.group(1))

    print("Rule: " + dec["rule"])
    print()
    layer = [r for r in rows if r["onLayer"]]
    pages = [r for r in rows if not r["onLayer"]]
    print(f"- Considered: {len(rows)} SFMTA projects, {len(layer)} on the layer and {len(pages)} pages SFMTA does not map.")
    print(f"- Listed: {sum(r['listed'] for r in rows)} ({sum(r['listed'] for r in layer)} on the layer, "
          f"{sum(r['listed'] for r in pages)} unmapped pages). SFMTA rows on the list: "
          f"{sum(1 for p in coord['projects'] if p['department'] == 'SFMTA')}.")
    reasons = collections.Counter(re.sub(r"\s*\(.*$|:.*$", "", r["reason"]) for r in rows if not r["listed"])
    print("- Left out, by reason:")
    for k, n in reasons.most_common():
        print(f"  - {k}: {n}")

    # The first audit's two measures, rerun.
    def on_plan(r):
        node = r["id"].split(":", 1)[1]
        return bool(set(blocks.get(node, {}).get("cnns", ())) & plan)

    active_nonbike = [r for r in layer if r["layerPhase"] not in FINISHED and "Bike" not in r["tags"] and on_plan(r)]
    got = [r for r in active_nonbike if r["id"] in listed_ids]
    print(f"- Active layer projects not tagged Bike whose line runs on plan blocks (15 m): {len(active_nonbike)}; "
          f"listed {len(got)}; left out {len(active_nonbike) - len(got)}:")
    for r in active_nonbike:
        if r["id"] not in listed_ids:
            print(f"  - {r['name']} ({r['layerPhase'] or 'no phase'}): {r['reason']}")
    nophase = [r for r in layer if "Bike" in r["tags"] and not r["layerPhase"]]
    got = [r for r in nophase if r["id"] in listed_ids]
    print(f"- Bike-tagged layer projects with no phase: {len(nophase)}; listed {len(got)}; left out:")
    for r in nophase:
        if r["id"] not in listed_ids:
            print(f"  - {r['name']}: {r['reason']}")
    shown = [p for p in coord["projects"] if p["department"] == "SFMTA"]
    print(f"- SFMTA rows with no phase from the layer or the page, shown as \"phase not published\": "
          f"{sum(1 for p in shown if not p['phase'])} of {len(shown)}; phase taken from the page: "
          f"{sum(1 for p in shown if (p.get('phaseBasis') or '').startswith('the project'))}.")

    if args.sample:
        out = [r for r in rows if not r["listed"]]
        random.seed(20260928)
        print()
        print(f"Sample of {args.sample} left-out projects (seed 20260928):")
        for r in sorted(random.sample(out, args.sample), key=lambda r: r["name"]):
            print(f"| [{r['name']}]({r['page']}) | {'layer' if r['onLayer'] else 'page only'} | "
                  f"{', '.join(r['tags']) or '—'} | {r['layerPhase'] or r['pagePhase'] or '—'} | {r['reason']} |")


if __name__ == "__main__":
    main()
