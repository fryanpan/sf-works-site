#!/usr/bin/env python3
"""How many unbuilt plan miles other departments' street work will open through 2028, and how often past repaving delivered the bikeway.

    tools/projects/department-overlap.py

Bryan, 2026-09-23: "for planned projects since BRP came into effect, and
planned projects going out through 2028, how many miles overlap with
improvements to the all ages & abilities network in BRP? How many of those
improvements have actually happened from past projects ... Look at this as
just one lever to get the network built faster."

Inputs, all files other scripts wrote:
  site/data/coordination.json        upcoming SFMTA, Public Works and SFPUC
        projects with the plan blocks (CNNs) each covers
        (tools/projects/coordination-projects.py, from the interagency coordination
        feed btxj-k9uh and SFMTA's project layer)
  site/data/north-star/status.json   every plan block, whether it meets what the
        plan draws today, its miles and met miles in the plan's unit (per
        direction of travel), and Appendix L's Upgrade/New flag
        (tools/bike-network/bike-progress.py)
  site/data/repave-lever.json        each year's repaved plan blocks, graded by
        whether the planned bikeway came with the repave (tools/bike-network/repave-lever.py)

Which projects count
  Street work only, as Bryan asked on the Current Projects page ("sewage,
  repaving, etc. are good"; a station elevator or traffic cameras are not).
  A project's kind is the one tools/projects/coordination-projects.py reads from
  its name: repaving, sewer, water and power, streetscape and safety, or spot
  repairs; anything else is left out and listed. Spot and as-needed repair
  contracts are counted apart and kept out of the headline. SFMTA's own
  bike projects (tagged Bike, or bike work in the name or the merged feed
  row's scope) are counted apart, since they are the bike work itself rather
  than a chance to add it; its pedestrian-only projects are not counted. A project counts when it is under way
  now or its published start falls on or before 2028-12-31. Undated and later
  projects are totalled separately.

What counts as overlap
  A plan block the project covers that does not yet meet what the plan draws
  (status none, short or partial; Undecided blocks are left out). Its miles
  are the part that does not meet, in the plan's unit. A block several
  projects cover is counted once.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import json
import os
import re
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
from mile_basis import BASIS  # noqa: E402
COORD = os.path.join(ROOT, "site", "data", "coordination.json")
STATUS = os.path.join(ROOT, "site", "data", "north-star", "status.json")
LEVER = os.path.join(ROOT, "site", "data", "repave-lever.json")
PROGRESS = os.path.join(ROOT, "site", "data", "bike-progress.json")
OUT = os.path.join(ROOT, "site", "data", "department-overlap.json")

MILE = 1609.344
HORIZON = "2028-12-31"
ADOPTED = "2025-03-04"
# The Past stage starts the first of the month after adoption: a repave
# finished in the plan's own month was scheduled before it. The departments
# page reads this back as compare[0].from.
PAST_FROM = f"{ADOPTED[:4]}-{int(ADOPTED[5:7]) + 1:02d}-01" if ADOPTED[5:7] != "12" else f"{int(ADOPTED[:4]) + 1}-01-01"

# Each project's street-work kind comes from coordination.json, where
# tools/projects/coordination-projects.py reads it from the name (work_kind), so the
# Current Projects list and these figures share one rule.


# A start date that has passed does not mean digging has begun: 13 of the 25
# miles first bucketed "under way" were on jobs the feed still calls Design or
# Planning (Opus pipeline review, 2026-09-23). So a passed date splits by phase.
# Public Works' page rows say "In progress", and that is work under way,
# not design (review, 2026-09-29: Beale Street and Page Street Neighborway
# were bucketed "date passed, in design").
BUILDING = re.compile(r"construction|legislated|current|in progress|implementation", re.I)


def start_bucket(p):
    # A row whose published end has passed is neither in construction nor in
    # design by its dates; it is kept apart and out of the window totals.
    if p.get("ended"):
        return "end passed"
    if p["underWay"]:
        return "in construction" if BUILDING.search(p.get("phase") or "") else "date passed, in design"
    s = p["start"]
    if not s:
        return "no date"
    return s[:4] if s[:4] <= HORIZON[:4] else "later"


# SFMTA's Slow Streets entry runs 2020 to 2030 over every Slow Street: a
# program's footprint, not a project that will open these blocks.
# Citywide programs, by the feed's own id: "Slow Streets" is dotmaps:21630.
PROGRAMS = {"dotmaps:21630"}


# SFMTA's rows on the Current Projects list include pedestrian and safety
# projects (No Turn on Red Downtown, community transportation plans) whose
# areas cover hundreds of plan blocks without adding a bikeway. Only its bike
# projects count as the bike work itself; the rest are counted in no group.
def group_of(p):
    if p["kind"] in ("SFMTA bike and safety", "SFMTA transit and parking"):
        return "sfmta" if p.get("bikeScope") else "sfmta, not bike"
    return "spot" if p["kind"] == "spot repairs" else "others"


def main():
    coord = json.load(open(COORD))
    status = {b["cnn"]: b for b in json.load(open(STATUS))["blocks"]}
    lever = json.load(open(LEVER))
    progress = json.load(open(PROGRESS))

    def need(cnn):
        b = status.get(cnn)
        if not b or b["status"] in ("meets", "unrated"):
            return 0
        return b["m"] - b["met_m"]

    blocks = collections.defaultdict(set)          # (group, bucket) -> cnns
    rated = collections.defaultdict(set)           # (group, bucket) -> every rated plan cnn, met or not
    job_of = {}                                    # cnn -> (bucket, project) of its earliest job, for the map readout
    kind_blocks = collections.defaultdict(set)     # kind -> cnns, in window
    projects, left_out = [], []
    for x in coord["notStreetWork"]:
        cnns = [c for c in x["planCnns"] if need(c) > 0]
        if cnns:
            left_out.append({"name": x["name"], "department": x["department"],
                             "miles": round(sum(need(c) for c in cnns) / MILE, 2)})
    for p in coord["projects"]:
        if p["id"] in PROGRAMS:
            continue
        k = p["kind"]
        b = start_bucket(p)
        group = group_of(p)
        for c in p.get("planCnns", []):
            if c in status and status[c]["status"] != "unrated":
                rated[(group, b)].add(c)
                if group == "others":
                    prev = job_of.get(c)
                    if prev is None or (p["start"] or "9999") < (prev[1]["start"] or "9999"):
                        job_of[c] = (b, p)
        cnns = [c for c in p.get("planCnns", []) if need(c) > 0]
        if not cnns:
            continue
        miles = sum(need(c) for c in cnns) / MILE
        blocks[(group, b)].update(cnns)
        if b not in ("later", "no date", "end passed"):
            kind_blocks[k].update(cnns)
        projects.append({"name": p["name"], "department": p["department"], "kind": k, "when": b,
                         "bikeScope": p.get("bikeScope"),
                         "start": p["start"], "miles": round(miles, 2), "slug": p["slug"]})

    def mi(cnns):
        return round(sum(need(c) for c in cnns) / MILE, 1)

    def by_flag(cnns):
        out = collections.Counter()
        for c in cnns:
            out[status[c]["flag"] if status[c]["flag"] in ("upgrade", "new") else "other"] += need(c)
        return {k: round(v / MILE, 1) for k, v in out.items()}

    window = ["in construction", "date passed, in design"] + [str(y) for y in range(2026, int(HORIZON[:4]) + 1)]
    # Each block goes to its earliest start and its strongest kind, so the
    # splits sum to the total rather than counting a shared block twice.
    STRENGTH = ["repaving", "streetscape and safety", "sewer, water and power"]
    summary = {}
    for group in ("others", "sfmta", "spot"):
        inw = set().union(*[blocks[(group, b)] for b in window])
        when = {}
        for b in reversed(window):
            for c in blocks[(group, b)]:
                when[c] = b
        summary[group] = {
            "miles": mi(inw), "blocks": len(inw), "byFlag": by_flag(inw),
            "byWhen": {b: mi({c for c in inw if when[c] == b}) for b in window},
            "laterOrUndated": mi((blocks[(group, "later")] | blocks[(group, "no date")]) - inw),
            "endPassed": mi(blocks[(group, "end passed")] - inw),
            "projects": sum(1 for p in projects if group_of(p) == group and p["when"] in window),
        }
    others_in = set().union(*[blocks[("others", b)] for b in window])
    sfmta_in = set().union(*[blocks[("sfmta", b)] for b in window])
    summary["othersNotSfmta"] = mi(others_in - sfmta_in)
    summary["othersAlsoSfmta"] = mi(others_in & sfmta_in)
    # Shared blocks with no bikeway-layer row read as unbuilt, but the layer
    # cannot see traffic calming, so some may already be calm streets.
    summary["othersSharedNone"] = mi({c for c in others_in
                                      if status[c]["facility"].startswith("Shared") and status[c]["status"] == "none"})
    when = {}
    for b in reversed(window):
        for c in blocks[("others", b)]:
            when[c] = b
    taken, by_kind, grid = set(), {}, {}
    for k in STRENGTH:
        own = (kind_blocks[k] & others_in) - taken
        by_kind[k] = mi(own)
        grid[k] = {b: mi({c for c in own if when[c] == b}) for b in window}
        taken |= own
    summary["byKind"] = by_kind
    summary["grid"] = grid

    # The record: of repaved plan miles that needed the bikeway, how many had it
    # by the end of the next year. Miles that got it two or more years later
    # (repave-lever.py's "later") did not come with the repave, so they count
    # as needed and not received.
    def record(y0, y1):
        rows = [r for r in lever["years"] if y0 <= r["year"] <= y1]
        rec = sum(r["milesReceived"] for r in rows)
        need_ = rec + sum(r["milesShort"] + r["milesLater"] for r in rows)
        return {"years": [y0, y1], "received": round(rec, 1), "needed": round(need_, 1),
                "pct": round(100 * rec / need_, 1) if need_ else None}

    # Bryan, 2026-09-24: "how many miles of improved bikeway might we have
    # built vs how many actually got built or planned to build". One row per
    # stage, each block in its earliest stage only, so the rows add up.
    #   repaved   rated plan blocks repaved on or after adoption (78va-8dhi,
    #             dated to the day, via repave-lever.py). Could have: the block
    #             did not meet the plan's class before the repave (grade short
    #             or received). Got it: received, a row meeting the class dated
    #             the repave year or the next.
    #   under way / by HORIZON   Public Works and SFPUC jobs in the feed. Could
    #             have: the block's unmet miles today. Planned: the job's own
    #             scope names bike work, or an SFMTA bike project in
    #             the same window covers the block.
    # The Past stage starts on the first of the month after adoption (Bryan,
    # 2026-09-28: "Past should only include repaving that ended in Apr 2025"
    # onward), the window the departments page draws its Past bars over. Its
    # miles are status.json's per-direction metres (lib/mile_basis.py),
    # the unit the later stages below and the lever use.
    since = lever["sinceAdoption"]
    past = [r for r in since["blocks"] if r["date"] >= PAST_FROM]
    def block_mi(r):
        return status[r["cnn"]]["m"] / MILE
    done = {r["cnn"]: r for r in past if r["grade"] in ("short", "received")}
    already = sum(block_mi(r) for r in past if r["grade"] == "already")
    undated = sum(block_mi(r) for r in past if r["grade"] == "undated")
    bike_scope = set()
    for p in coord["projects"]:
        if p["id"] in PROGRAMS or group_of(p) != "others" or not p.get("scopeNamesBike"):
            continue
        if start_bucket(p) in window:
            bike_scope.update(p.get("planCnns", []))
    planned_by = sfmta_in | bike_scope
    stages = [("under way", ["in construction", "date passed, in design"]),
              ("to come", [str(y) for y in range(2026, int(HORIZON[:4]) + 1)])]
    seen = set(done) | {r["cnn"] for r in past}
    compare = [{"stage": "repaved", "from": PAST_FROM,
                "to": max((r["date"] for r in past if r["grade"] != "unrated"), default=None),
                "could": round(sum(block_mi(r) for r in done.values()), 1),
                "got": round(sum(block_mi(r) for r in done.values() if r["grade"] == "received"), 1),
                "blocks": len(done),
                "gotStreets": sorted({r["street"] for r in done.values() if r["grade"] == "received"}),
                "alreadyMet": round(already, 1), "undated": round(undated, 1)}]
    # Bryan, 2026-09-28: "Combine the map with the first section and let the
    # user choose between past projects, active projects, and future
    # projects", with bars in "the same categories as below". So each later
    # stage lists its blocks in the repaving map's four categories: will get
    # the plan's bikeway (an SFMTA project or the job's own bike scope), already
    # has it, has less, has none. Miles are whole blocks per direction, as the
    # repaving map counts them.
    def category(c):
        st = status[c]["status"]
        if st == "meets":
            return "already"
        if c in planned_by:
            return "met"
        return "none" if st == "none" else "short"
    # The block's centreline, for the map: the traced plan network the site
    # draws from lacks about one in four of these blocks. Same cached query as
    # pipeline/sources/sf-streets.py, rounded to about a metre.
    import sfdata
    from plan_directions import CENTERLINES, CENTERLINE_SELECT, CENTERLINE_FLOOR
    cl = sfdata.fetch(CENTERLINES, select=CENTERLINE_SELECT, where="active='true'", floor=CENTERLINE_FLOOR)
    line_of = {}
    for r in cl.rows:
        g = r.get("line") or {}
        parts = [g.get("coordinates") or []] if g.get("type") == "LineString" else (g.get("coordinates") or [])
        if parts and parts[0]:
            line_of[str(r["cnn"])] = [[round(x, 5), round(y, 5)] for x, y in parts[0]]
    # What each block has on the ground now, so the page's popover can set it
    # beside what the plan draws (Bryan, 2026-10-02: "The project popovers are
    # mostly not clear about what the bike plan called for on that street").
    # The best class on the block in SFMTA's layer, as tools/bike-network/repave-lever.py
    # reads it; "" is no bikeway.
    import importlib.util
    rl = paths.load("repave-lever.py")
    layer, _ = rl.load_layer()
    LAYER_PLAIN = rl.PLAIN
    for name, buckets in stages:
        cnns = set().union(*[blocks[("others", b)] for b in buckets]) - seen
        every = set().union(*[rated[("others", b)] for b in buckets]) - seen
        seen |= every
        cats = collections.Counter()
        rows = []
        for c in sorted(every):
            cat = category(c)
            cats[cat] += status[c]["m"]
            job = job_of.get(c, (None, {}))[1]
            rows.append({"cnn": c, "cat": cat, "street": status[c]["street"], "wants": status[c]["facility"],
                         "has": LAYER_PLAIN.get(layer.get(rl.cnn_key(c), {"rank": 0})["rank"], ""),
                         "job": job.get("name"), "slug": job.get("slug"), "start": job.get("start"),
                         "line": line_of.get(c)})
        compare.append({"stage": name, "buckets": buckets, "could": mi(cnns), "got": mi(cnns & planned_by),
                        "blocks": len(cnns), "byScope": mi(cnns & bike_scope), "bySfmta": mi(cnns & sfmta_in),
                        "byCategory": {k: round(v / MILE, 2) for k, v in cats.items()}, "segments": rows})

    # Each Public Works or SFPUC job the later stages show, for the map's
    # popover (Bryan, 2026-09-28: "when I click on a segment, highlight the
    # whole segment from the DPW or PUC project ... Miles of new all-ages
    # network this overlaps in the BRP, Miles planned to be built, Links").
    # Miles are per direction, whole blocks, as the bars count them.
    def job_cats(p):
        cats = collections.Counter()
        for c in p.get("planCnns", []):
            if c in status and status[c]["status"] != "unrated":
                cats[category(c)] += status[c]["m"]
        return cats

    jobs = {}
    for p in coord["projects"]:
        if p["id"] in PROGRAMS or group_of(p) != "others" or start_bucket(p) not in window:
            continue
        mine = [c for c in p.get("planCnns", []) if c in status and status[c]["status"] not in ("unrated", "meets")]
        if not mine:
            continue
        jobs[p["slug"]] = {
            "cnns": sorted(p.get("planCnns", [])),
            "overlapMiles": round(sum(status[c]["m"] for c in mine) / MILE, 2),
            "plannedMiles": round(sum(status[c]["m"] for c in mine if c in planned_by) / MILE, 2),
            # The job's own bars, in the stage bars' categories (Bryan,
            # 2026-09-28: "show the same bar chart breakdown in the popover").
            "byCategory": {k: round(v / MILE, 2) for k, v in job_cats(p).items()},
        }

    # Each Past repave's paving job, for the same popover (Bryan, 2026-09-29:
    # "Clicking should bring up a project panel that has key details. And
    # highlight all segments related to the project"). The PCI record names no
    # job, so a repaved block takes the job order of its five-year dig lock
    # (5wbp-dwzt): the lock starting closest to the repave, from 150 days
    # before it to 45 after, since a lock is filed when the job is accepted.
    # The coordination feed carries the same number as peoplesoft_id, which
    # names the job and, where the feed still lists it, gives its project page.
    # Both reads are the cached pulls tools/bike-network/repave-lever.py and
    # tools/projects/coordination-projects.py keep current; nothing is fetched here.
    import datetime as dt
    from sfdata import fetch
    mor = fetch("5wbp-dwzt")
    locks = collections.defaultdict(list)
    for r in mor.rows:
        if r.get("cnn") and r.get("effectivedate") and r.get("jobordernum"):
            locks[str(r["cnn"])].append((r["effectivedate"][:10], r["jobordernum"].strip()))
    slug_of_feed = {p["id"]: p["slug"] for p in coord["projects"]}
    feed_job = {}
    for r in fetch("btxj-k9uh").rows:
        jo = (r.get("peoplesoft_id") or "").split("-")[0].strip()
        if jo and jo not in feed_job:
            feed_job[jo] = {"name": r.get("name"), "slug": slug_of_feed.get("dotmaps:%s" % r.get("dotmapsid"))}
        elif jo and not feed_job[jo]["slug"]:
            feed_job[jo]["slug"] = slug_of_feed.get("dotmaps:%s" % r.get("dotmapsid"))
    past_jobs = {}
    for r in past:
        if r["grade"] == "unrated":
            continue
        d = dt.date.fromisoformat(r["date"])
        near = [(abs((dt.date.fromisoformat(e) - d).days), e, jo) for e, jo in locks.get(r["cnn"], [])
                if -150 <= (dt.date.fromisoformat(e) - d).days <= 45]
        if not near:
            continue
        jo = min(near)[2]
        j = past_jobs.setdefault(jo, {"jobOrder": jo, "cnns": [], "streets": [], "from": r["date"], "to": r["date"],
                                      "feedName": (feed_job.get(jo) or {}).get("name"),
                                      "slug": (feed_job.get(jo) or {}).get("slug")})
        j["cnns"].append(r["cnn"])
        j["from"], j["to"] = min(j["from"], r["date"]), max(j["to"], r["date"])
        if r["street"] not in j["streets"]:
            j["streets"].append(r["street"])
    for j in past_jobs.values():
        j["cnns"].sort()
        j["streets"].sort()
    # Checks: every job block is a Past block, and no block is in two jobs.
    past_rated = {r["cnn"] for r in past if r["grade"] != "unrated"}
    in_jobs = [c for j in past_jobs.values() for c in j["cnns"]]
    assert set(in_jobs) <= past_rated, "a Past job holds a block outside the Past stage"
    assert len(in_jobs) == len(set(in_jobs)), "a Past block is in two paving jobs"
    assert len(in_jobs) >= 0.5 * len(past_rated), f"only {len(in_jobs)} of {len(past_rated)} Past blocks matched a dig lock"

    remaining = progress["network"]["remainingMetres"] / MILE
    rate = record(2010, 2025)
    out = {
        "generated": coord["generated"],
        "horizon": HORIZON, "adopted": ADOPTED,
        "unit": "miles per direction of travel, the plan's unit",
        "mileBasis": BASIS,
        "sources": {
            "feed": coord["feed"], "sfmtaLayer": coord["sfmtaLayer"],
            "plan": json.load(open(STATUS))["plan"], "layer": json.load(open(STATUS))["layer"],
            "pci": lever["sources"]["pci"],
        },
        "remainingMiles": round(remaining, 1),
        "summary": summary,
        "compare": compare,
        "jobs": jobs,
        "pastJobs": dict(sorted(past_jobs.items())),
        # 2026 is left out: a 2026 repave cannot yet show a bikeway by the end
        # of the next year.
        "record": {"long": rate, "recent": record(2021, 2025), "adoptionYear": record(2025, 2025)},
        # The rate is measured on repaves, so it is applied to repaving only.
        "expectedFromRepaving": round(summary["byKind"]["repaving"] * rate["pct"] / 100, 1) if rate["pct"] else None,
        "projects": sorted(projects, key=lambda p: -p["miles"]),
        "leftOut": sorted(left_out, key=lambda p: -p["miles"]),
        "method": __doc__.split("Which projects count")[1].strip(),
    }
    stable.write_json(OUT, out, end="", ensure_ascii=True, indent=1)
    s = summary["others"]
    print(f"Public Works and SFPUC street work, under way or starting by {HORIZON}: {s['miles']} unbuilt plan miles on {s['blocks']} blocks "
          f"({s['projects']} projects) of {remaining:.0f} remaining; by flag {s['byFlag']}; by when {s['byWhen']}; later or undated {s['laterOrUndated']}")
    print(f"  by kind {summary['byKind']}; not also covered by an SFMTA project {summary['othersNotSfmta']}")
    t = summary["sfmta"]
    print(f"SFMTA bike projects in the same window: {t['miles']} mi on {t['blocks']} blocks ({t['projects']} projects); later or undated {t['laterOrUndated']}")
    for k, r in out["record"].items():
        print(f"  record {k} {r['years']}: {r['received']} of {r['needed']} needed mi received ({r['pct']}%)")
    print(f"  expected from repaving at the long-run rate: {out['expectedFromRepaving']} mi")
    print(f"  left out as not street work: {[(x['name'][:40], x['miles']) for x in out['leftOut']]}")
    print(f"  Past blocks with a paving job: {len(in_jobs)} of {len(past_rated)}, in {len(past_jobs)} jobs "
          f"({sum(1 for j in past_jobs.values() if j['slug'])} with a project page)")
    print(f"wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
