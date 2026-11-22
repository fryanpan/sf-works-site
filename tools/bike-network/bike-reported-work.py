#!/usr/bin/env python3
"""Bikeway work SFMTA's own project pages report as built in 2026, which tools/bike-network/bike-network-history.py adds to the latest year.

Bryan, 2026-09-23, asked "Were there really no improvements in 2026?" SFMTA's
bikeway layer carries dated work only through February 2026, so the map showed
almost nothing new that year. He chose to add the work SFMTA's pages call
built, and then asked that it be counted as ordinary data rather than drawn
apart: "Just integrate the data. Don't explain how we got it except in about
the data page." bike-network-history.py upgrades the bikeway blocks along each
project's line to the class given here, for this year only.

The list is hand-curated, because whether a sentence on a project page means
"built" is a judgement. Each entry carries the page's own words, and the
script fails if those words are no longer in the mirrored page text
(out/sfmta-projects/projects.json), so a page that changes cannot leave a stale
claim on the map. Only pages saying the work is complete or substantially
complete qualify; "anticipated", "in progress" and "expected" do not.

Geometry is SFMTA's published project line (out/sfmta-projects/projects.geojson).
A project can carry several features there (node 381, Folsom-Howard, has five),
and the layer returns them in no fixed order, so every line feature of a node is
used together. Taking one of them let the 2026-11-21 refresh pick a different
line for 381 and match none of Folsom Street's blocks.
Writes site/data/bike-history/reported.json.

Quality check, before anything is written: every reported and planned project
must match at least one block, and every block must carry a line of at least two
points. A project that matches nothing fails the step, so the orchestrator keeps
the last good files rather than shipping a project the site cannot draw.

It also writes site/data/bike-history/planned.json: bikeway work SFMTA's pages
say is still to come, with the year each page gives for finishing it (Bryan,
2026-09-24: "include planned projects for 2027 and beyond, as much as MTA has
available"). The year is the end of the construction window the page states,
or its start when that is all it gives. A project whose page names no bikeway
type, or no date, is listed without miles.

A page's words are checked against its text in out/sfmta-projects/projects.json,
or, where that file holds no text (it keeps text only for Bike-tagged
projects), against out/sfmta-projects/pages.json, which holds every page in
SFMTA's sitemap.

The same check covers site/data/bike-history/project-summaries.json, the
hand-written two- or three-sentence summaries the overview's project cards
show. Every phrase a summary quotes (split at an ellipsis or a bracketed
edit) must still be in its page's teaser or text, so a page that changes
after its summary was written fails this step until the summary is re-read.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
import sfdata  # noqa: E402

ROOT = paths.ROOT
PROJECTS = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
GEOMETRY = os.path.join(ROOT, "out", "sfmta-projects", "projects.geojson")
OUT = os.path.join(ROOT, "site", "data", "bike-history", "reported.json")

YEAR = 2026
# Each entry: node, the page's words that say the work is done, the class it
# built, and which city blocks (CNNs in DataSF 3psu-pn9h) it covers: either
# ("streets", [...]) -- blocks of those streets lying along the project's
# published line -- or ("cnns", [...]) where the page names the stretch and the
# published line runs past it.
REPORTED = [
    # Read 2026-11-10: "The project adds a separated bikeway".
    ("45035", "This project has been completed as of October 2026",
     "CLASS IV", ("streets", ["WINSTON"])),
    ("1110", "Implementation was completed in early 2026", "CLASS IV",
     # "Two-way bikeway on Bayshore Boulevard separated by concrete barriers",
     # in work "along Bayshore Boulevard between Marin Street and Jerrold
     # Avenue": one block. The page's work on Cesar Chavez under Highway 101 is
     # "Road diet and striping modifications", which names no bikeway class,
     # so those blocks are not upgraded.
     ("cnns", ["2799102"])),
    ("28896", "Construction for the Beach Street Quick-Build Project is substantially complete", "CLASS IV",
     # "Two-Way Separated Bikeway on the north side of Beach Street between
     # Van Ness Avenue and Columbus Avenue": the four Beach St blocks from the
     # Van Ness end to Columbus. The page dates neither the completion nor the
     # update; the layer (read 2026-09-22) has no Beach St row, and the page's
     # timeline still lists construction for winter 2025, so it is counted in 2026.
     ("cnns", ["2848000", "2847000", "2846000", "2845000"])),
]
# Every Bike-tagged page in the mirror was searched on 2026-09-23 for a 2026
# sentence saying work was done, and every Completed or under-construction
# Bike page edited in 2026 was read. Left out, with the words that fell short:
#   24472 Lake Merced Quick-Build: "Fall 2023-Spring 2026 Construction Completed", but
#         its Lake Merced Blvd blocks already carry a Class I path in the layer,
#         so the only blocks it would change are its neighborway side streets
#   939   Better Market Street: "anticipate reaching final completion in early 2026" (page edited 2025-06)
#   2403  Mission / Geneva Safety: "Fall 2022 - Early 2026 Full Project Construction Pending"
#   26728 Sloat Blvd Quick-Build: "Fall 2025 Implementation Completed" (2025, not 2026)
#   15731 Valencia Bikeway: "Construction on the bike lane will begin on February 10, 2025" (2025)
#   27617 Noe Slow Street: "Summer - fall 2025 Traffic calming ... implemented" (2025)
#   44135 Mission Bay Blvd Quick-Build: "This project is complete as of as of August 2026" (posts only)
#   381   Folsom-Howard Streetscape: "construction across the entire corridor is about 75% complete"
#   27467 Frida Kahlo Way Quick-Build: final elements "expected in summer 2026"
#   28565 Oak Street Quick-Build: "Summer 2026 - early 2027 Implementation (with street repaving) Pending"

# Each entry: node, the part of the project as the page names it (or None), the page's words that
# give the date, the year work ends, the class, which blocks -- ("streets",
# [...]) along the project's line, or ("cnns", [...]) where the page names a
# shorter stretch than its line -- and the direction rows the finished bikeway
# has on a block: 2 for two-way, 1 for one-way. The plan counts miles per
# direction row, so a one-way row becoming two-way adds a row.
# Read 2026-09-24 from every Bike-tagged page with construction still pending.
PLANNED = [
    ("20936", None, "2025 - 2026 Construction Pending", 2026, "CLASS IV", ("streets", ["13TH", "DUBOCE"]), 2),  # "protected bike lanes"
    # Read 2026-11-20. Two phases: this one, Indiana to Illinois, and "The
    # western half of the project will be implemented beginning in 2028",
    # which is not listed here. The page gives each phase a start and no end
    # (its timeline row for both is "2027-2029 Construction Pending"), so the
    # year is this phase's start.
    ("30111", None, "beginning in 2027 with the section of Cesar Chavez Street between Indiana Street and Illinois Street", 2027, "CLASS IV",
     ("cnns", ["2467000", "2468000", "2469000", "2470000"]), 2),  # "a physically-protected, two-way bikeway"
    ("27339", None, "Predicted Completion 2027", 2027, "CLASS IV", ("streets", ["MAIN"]), 1),  # "A protected northbound bike lane"
    ("28565", None, "Summer 2026 - early 2027 Implementation", 2027, "CLASS IV", ("streets", ["OAK"]), 1),  # "a physically-protected eastbound bikeway"
    ("24302", None, "2026 - 2028 Construction", 2028, "CLASS IV", ("streets", ["HOWARD"]), 2),  # "a two-way, parking-protected bike lane"
    # "Extend the protected bikeway, from Folsom south to Brannan Street"; the
    # Broadway-Folsom bikeway is already in the layer. The layer puts these
    # rows on the 2xx half of each paired Embarcadero block.
    ("752", None, "2026-2028 Construction Pending", 2028, "CLASS IV",
     ("cnns", ["12548201", "12549201", "12550202"]), 2),
    # "Two-way bikeways". The page gives Folsom and Howard separate schedules:
    # "Folsom Streetscape Project ... Construction: 2024 to 2026" and "Howard
    # Streetscape Project ... Construction: 2026 to 2029", 4th to 11th.
    ("381", "Folsom Streetscape Project", "Construction: 2024 to 2026", 2026, "CLASS IV", ("streets", ["FOLSOM"]), 2),
    ("381", "Howard Streetscape Project", "Construction: 2026 to 2029", 2029, "CLASS IV",
     ("cnns", ["7039001", "7041000", "7042000", "7043000", "7044000", "7045000", "7046000", "7047000", "7048000",
               "7049000", "7050000", "7051000", "7052000", "7053000", "7054000", "7055000", "7056000"]), 2),
]
# The structured timeline (out/sfmta-projects/pages.json) marks each dated
# row Pending or Completed. A planned row must read Pending, except where the
# page contradicts itself; those are listed with what each part says.
TIMELINE_CONFLICTS = {
    # Read 2026-09-24: the timeline row "2026 - 2028 Construction" is marked
    # Completed, while the page's text describes the work as future. Counted
    # as planned for 2028; the conflict is printed in planned.json.
    "24302": "the page's timeline marks \"2026 - 2028 Construction\" Completed; its text describes the bikeway as still to be built",
}
# Named on the page with a date but no bikeway type, or with no date: listed, no miles.
PLANNED_UNCOUNTED = [
    # "Installing safe-hit posts on the existing bike lane on Mission Bay Drive
    # west of the roundabout": the page gives no cross streets for the stretch.
    ("44135", "This project is complete as of as of August 2026", 2026, "posts on an existing lane; the page gives no cross streets"),
    ("2403", "Fall 2022 - Early 2026 Full Project Construction Pending", 2026, "\"bike lane connectivity upgrades\" on Geneva, no bikeway type named"),
    ("1146", "once funding is secured", None, "separated bikeway named, no date: construction \"once funding is secured\""),
    ("21212", "Summer 2021 Construction Pending", None, "date passed, page not updated"),
    ("18897", "Summer & Winter 2020 Construction Pending", None, "date passed, page not updated"),
    ("44134", "Late 2027 Construction Pending", 2027, "no bikeway type named"),
    ("44133", "2027 Final Construction Pending", 2027, "no bikeway type named"),
    ("29974", "2028 Construction Pending", 2028, "no bikeway type named"),
    ("19953", "2027+ Construction Pending", None, "improvements to be decided"),
    # Read 2026-11-11 (https://www.sfmta.com/projects/arguello-safety-project):
    # status "Planning", open house December 9, 2026, timeline "Spring 2027
    # Implementation Pending". The page proposes "targeted improvements at key
    # locations" (paint, safety zones, signals, turn restrictions, calming) and
    # rules out center-running and curbside bikeways for this budget.
    ("28373", "Spring 2027 Implementation Pending", 2027, "targeted intersection work on the existing bike lanes; no new bikeway named"),
    ("28582", "the SFMTA has decided to pause the project", None, "paused"),
    # Read 2026-09-29 from every SFMTA project in site/data/coordination.json
    # with bike scope and an end date of 2026 or later, or none.
    # "Improve connections for people riding bikes" at the intersection.
    ("43636", "2026 Implementation Pending", 2026, "no bikeway type named"),
    # "Enhance safety and comfort for people using the existing bike lanes".
    ("45074", "Project Implementation Late 2026 - 2027 Pending", 2027, "work on existing bike lanes; no new bikeway named"),
    # The city's coordination feed gives a two-way bikeway to Shrader Street
    # ending 2028; the page names no bikeway type and dates nothing after 2022.
    ("24645", "Spring 2022 Implementation & Evaluation Pending", None, "no bikeway type named on the page; its only date has passed"),
    ("917", "Bike Lanes between Mansell and Dwight (future date to be determined)", None, "bike lanes named, no date"),
    # "Geneva Avenue & Santos Street: One full-length boarding island with
    # protected bike lane": one stop, and the page's timeline gives no dates.
    ("44339", "A boarding island on Geneva Avenue with a protected bike lane would also be added", None, "protected bike lane at one boarding island named, no date"),
]
PLANNED_OUT = os.path.join(ROOT, "site", "data", "bike-history", "planned.json")
PAGES = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")


SUMMARIES = os.path.join(ROOT, "site", "data", "bike-history", "project-summaries.json")


def _norm(t):
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2013", "-"),
                 ("\u2014", "-"), ("\u00a0", " ")):
        t = t.replace(a, b)
    return " ".join(t.split()).lower()


def stale_summaries(pages, sitemap):
    """(node, phrase) for every phrase a hand-written summary quotes that its page no longer carries."""
    out = []
    for node, text in sorted(json.load(open(SUMMARIES, encoding="utf-8"))["summaries"].items()):
        p = pages.get(node) or {"node": node}
        page = _norm("%s %s" % (p.get("teaser") or "", page_text(p, sitemap)))
        for q in re.findall(r'"([^"]+)"', text):
            for frag in re.split(r"\s*(?:\.\.\.|\u2026|\[[^\]]*\])\s*", q):
                frag = _norm(frag).strip(" .,;:")
                if len(frag) >= 4 and frag not in page:
                    out.append((node, frag))
    return out


def page_text(p, sitemap):
    """The page's text from projects.json, or from pages.json where projects.json holds none."""
    return " ".join((p.get("pageText") or (sitemap.get(p["node"]) or {}).get("pageText") or "").split())
LAYER = os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "network.json")

LAT0 = math.radians(37.76)


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * 6371008.8, math.radians(lat) * 6371008.8)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1.0)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def along(block, lines, tol=25.0):
    """True when at least 90% of a block's vertices lie within tol metres of the
    project's line, and the block is at least 20 m long: the block runs along
    the line rather than crossing it."""
    q = [xy(*c) for c in block]
    if sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:])) < 20:
        return False
    L = [[xy(*c) for c in line] for line in lines]
    if not L:
        return False
    near = sum(1 for p in q if min(seg_dist(p, a, b) for l in L for a, b in zip(l, l[1:])) <= tol)
    return near >= 0.9 * len(q)


def project_lines(features):
    """Every line of each node's features, in a fixed order. The layer holds several features for some projects and
    returns them in no stable order, so keeping only one (the last read) made the matched blocks depend on that
    order. A polygon counts as its rings, points carry no line and are left out, and a repeated line is kept once."""
    out = {}
    for f in features:
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            ls = [g["coordinates"]]
        elif g.get("type") in ("MultiLineString", "Polygon"):
            ls = g["coordinates"]  # a polygon's rings are its outline
        elif g.get("type") == "MultiPolygon":
            ls = [ring for poly in g["coordinates"] for ring in poly]
        else:
            continue
        out.setdefault(str(f["properties"]["node"]), []).extend(l for l in ls if len(l) >= 2)
    return {n: [json.loads(x) for x in sorted({json.dumps(l) for l in ls})] for n, ls in out.items()}


def check_blocks(listname, projects):
    """Fail the step when a project matched no block or a block has no line: the site labels each project at a point
    on its blocks, and a project with none breaks the page rather than dropping out of it."""
    bad = ["%s (%s): %d blocks" % (p["node"], p["name"], len(p["blocks"])) for p in projects if not p["blocks"]]
    bad += ["%s (%s): block %s has %d points" % (p["node"], p["name"], b["cnn"], len(b["pts"]))
            for p in projects for b in p["blocks"] if len(b["pts"]) < 2]
    if bad:
        raise SystemExit("%s: a project matched no city blocks or a block has no line; check its geometry in %s and "
                         "its entry in %s:\n  %s" % (listname, os.path.relpath(GEOMETRY, ROOT), listname,
                                                      "\n  ".join(bad)))


def main():
    pages = {p["node"]: p for p in json.load(open(PROJECTS))["projects"]}
    timelines = json.load(open(PAGES))["pages"]
    geoms = project_lines(json.load(open(GEOMETRY))["features"])
    cl = sfdata.fetch("3psu-pn9h", select="cnn,street,st_type,streetname,f_st,t_st,f_node_cnn,t_node_cnn,line,oneway",
                      where="active='true'")
    by_cnn = {r["cnn"]: r for r in cl.rows if r.get("line")}
    stale = stale_summaries(pages, timelines)
    if stale:
        raise SystemExit("project-summaries.json quotes words its page no longer carries; re-read the page and "
                         "rewrite the summary:\n" + "\n".join("  %s: %r" % s for s in stale))
    out = []
    for node, words, cls, (how, which) in REPORTED:
        p = pages[node]
        text = page_text(p, timelines)
        if words not in text:
            raise SystemExit("%s (%s): the page no longer says %r; re-read it and update REPORTED" % (node, p["name"], words))
        lines = geoms.get(node) or []
        if how == "cnns":
            blocks = [by_cnn[c] for c in which]
        else:
            blocks = [r for r in by_cnn.values()
                      if any((r.get("street") or "").upper().startswith(w) for w in which)
                      and "RAMP" not in ("%s %s" % (r.get("street") or "", r.get("st_type") or "")).upper()
                      and along(r["line"]["coordinates"], lines)]
        out.append({"node": node, "name": p["name"], "page": p["page"], "phase": p.get("phase"), "page_edited": p.get("lastEdited"),
                    "year": YEAR, "quote": words, "class": cls, "matched_by": how,
                    "blocks": [{"cnn": r["cnn"], "street": "%s %s" % (r.get("street") or "", r.get("st_type") or ""),
                                "from": r.get("f_st"), "to": r.get("t_st"),
                                "pts": [[round(x, 6), round(y, 6)] for x, y in r["line"]["coordinates"]]} for r in blocks],
                    "lines": [[[round(x, 6), round(y, 6)] for x, y in line] for line in lines]})
    check_blocks("REPORTED", out)
    stable.write_json(OUT, {"generated": dt.date.today().isoformat(), "year": YEAR,
                   "source": "SFMTA project pages and project layer, as mirrored in out/sfmta-projects",
                   "centerlines": {"dataset": "https://data.sf.gov/d/3psu-pn9h", "queried": cl.fetched_on.isoformat()},
                   "projects": out}, end="", ensure_ascii=True, indent=1)
    for r in out:
        print("  %s: %d blocks (%s) %s" % (r["name"], len(r["blocks"]), r["matched_by"],
                                          ["%s %s-%s" % (b["street"].strip(), b["from"], b["to"]) for b in r["blocks"]]))

    planned, uncounted = [], []
    layer = {}
    for r in json.load(open(LAYER))["records"]:
        layer.setdefault(str(int(r["CNN"] or 0)), []).append(r["DIRECT"])
    for node, part, words, year, cls, (how, which), dirs in PLANNED:
        p = pages[node]
        text = page_text(p, timelines)
        if words not in text:
            raise SystemExit("%s (%s): the page no longer says %r; re-read it and update PLANNED" % (node, p["name"], words))
        tl = [t for t in (timelines.get(node) or {}).get("timeline", []) if ("%s %s" % (t["when"], t["what"])) in words or words.startswith("%s %s" % (t["when"], t["what"]))]
        status = tl[0]["status"] if tl else None
        if status not in (None, "Pending") and node not in TIMELINE_CONFLICTS:
            raise SystemExit("%s (%s): the timeline row %r now reads %s; re-read the page" % (node, p["name"], words, status))
        lines = geoms.get(node) or []
        if how == "cnns":
            blocks = [by_cnn[c] for c in which]
        else:
            blocks = [r for r in by_cnn.values()
                      if any((r.get("street") or "").upper() == w for w in which)
                      and along(r["line"]["coordinates"], lines)]
        # A divided street is two centreline halves, 1xx and 2xx, each one
        # direction. When the layer already holds the street's rows on one
        # half, the other half is the same street, not a second bikeway.
        twin = lambda c: c[:-3] if len(c) >= 6 and c[-3] in "12" and not c.endswith("000") else None
        held = {twin(r["cnn"]) for r in blocks if twin(r["cnn"]) and layer.get(r["cnn"])}
        blocks = [r for r in blocks if layer.get(r["cnn"]) or twin(r["cnn"]) not in held]
        halves = {}
        for r in blocks:
            if twin(r["cnn"]):
                halves.setdefault(twin(r["cnn"]), set()).add(r["cnn"][-3])

        def target(c):
            # Direction rows on the block once the project is built.
            rows = layer.get(c) or []
            if rows:
                return max(len(rows), dirs if all(d == "1W" for d in rows) else len(rows))
            return 1 if twin(c) and len(halves.get(twin(c), ())) == 2 else dirs
        name = part or p["name"]  # the page names each part as its own project
        planned.append({"node": node, "name": name, "page": p["page"], "phase": p.get("phase"), "page_edited": p.get("lastEdited"),
                        "year": year, "quote": words, "timeline_status": status, "conflict": TIMELINE_CONFLICTS.get(node),
                        "class": cls, "directions": dirs,
                        "blocks": [{"cnn": r["cnn"], "street": "%s %s" % (r.get("street") or "", r.get("st_type") or ""),
                                    "from": r.get("f_st"), "to": r.get("t_st"), "rows": target(r["cnn"]),
                                    "pts": [[round(x, 6), round(y, 6)] for x, y in r["line"]["coordinates"]]} for r in blocks]})
        print("  planned %d: %s: %d blocks, %d rows" % (year, name, len(blocks), sum(target(r["cnn"]) for r in blocks)))
    for node, words, year, why in PLANNED_UNCOUNTED:
        p = pages[node]
        text = page_text(p, timelines)
        if words not in text:
            raise SystemExit("%s (%s): the page no longer says %r; re-read it and update PLANNED_UNCOUNTED" % (node, p["name"], words))
        uncounted.append({"node": node, "name": p["name"], "page": p["page"], "year": year, "quote": words, "why": why})
    check_blocks("PLANNED", planned)
    stable.write_json(PLANNED_OUT, {"generated": dt.date.today().isoformat(),
                   "source": "SFMTA project pages and project layer, as mirrored in out/sfmta-projects",
                   "centerlines": {"dataset": "https://data.sf.gov/d/3psu-pn9h", "queried": cl.fetched_on.isoformat()},
                   "projects": planned, "uncounted": uncounted}, end="", ensure_ascii=True, indent=1)


if __name__ == "__main__":
    main()
