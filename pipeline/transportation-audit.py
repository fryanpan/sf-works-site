#!/usr/bin/env python3
"""Audit the data behind the biking pages against every measurable check in pipeline/transportation-data-audit-criteria.md; writes out/transportation-audit/report.md and exits 1 on any FAIL.

    pipeline/transportation-audit.py                # run every check
    pipeline/transportation-audit.py --only A1 E2   # run the checks whose id starts with these
    pipeline/transportation-audit.py --refresh      # re-fetch the network caches first
    pipeline/transportation-audit.py --no-build     # skip building the site (F checks read no pages)
    pipeline/transportation-audit.py --strict       # also exit 1 on NOT GRADED / NOT MEASURED
    pipeline/transportation-audit.py --explain      # list the rows behind each check that does not pass

What it reads. Files other scripts wrote: site/data/*.json, out/*, the
tracked extracts under data/extract/, and the Socrata cache under
data/socrata-cache/ (gitignored; symlink it into a worktree). One source it
reads itself: SFMTA's North Star map PDF, cached in .cache/north-star-map/ and
fetched from sfmta.com when missing, which F1 and C2 measure plan miles from
(needs pdftocairo). It runs under PYTHONHASHSEED=0, re-executing itself when
started without it, as the pipeline does. The F checks
read the rendered pages, so the audit builds a copy of site/ into a
temporary directory (astro build, with site/node_modules linked in, a few
seconds) and never touches site/dist, which the dev server owns.

What a check prints. Each check is one small function below, registered with
@check. It returns the measured value, its denominator, the pass line quoted
from the criteria doc, and PASS, FAIL, NOT GRADED or NOT MEASURED, plus the
rows behind the number. A pipeline fix flips a check by changing the data the
check reads; nothing in the audit needs to change with it.

Hand-graded checks. D2 (dates against the department's page) and the sample
in C3 (is a matched record about the project) read grades from
data/audit/grades/*.csv. The first run writes each file as a template: a
seeded random sample with our values filled in and the grade columns blank.
A check reports NOT GRADED until every row carries a grade. The column
meanings are in data/audit/README.md.

Explanations. Several pass lines say "every miss explained". An explanation
is a row in data/audit/explanations.csv (check, key, explanation). The key is
what the check prints for the row, usually the project name. A row with an
explanation still counts in the measured number; the check passes only when
the number is within the line and every counted row is explained.

Network. Two checks compare against what a department publishes: A1 against
SFMTA's sitemap and B1 against the department pages our links point at. They
read data/audit/cache/*.json. --refresh re-fetches the sitemap and the status
of every department link; without --refresh, only links the status cache has
never checked are read and added to it. Without the cache, the sitemap is seeded from
data/extract/sfmta-pages/sitemap.json and no link status is assumed. A2
reads the coordination feed from data/socrata-cache/ only, and says whether
that pull is the one site/data/coordination.json was built from; with no
cached pull it reports NOT MEASURED rather than fetch today's rows, unless
--refresh is given.

Discussion corpus. C2 and C3b search every item of the deciding bodies'
meeting mirrors (data/<body>/meetings/, the bodies in project-record.py's
MIRRORS). The Board of Supervisors' meeting files are gitignored; when a
mirror's files fall short of its tracked index.json, both checks report NOT
MEASURED rather than search less.

Adding a discussion body (C1). A mirror script for a body can write
out/<slug>/coverage.json with {"body", "first", "last", "meetings",
"missing": [...], "fullTitles": bool, "script"}; every such file is read and
replaces the built-in reading for that body, so a new mirror flips its C1 row
without an edit here. tools/projects/record-coverage.py --json out/record-coverage/coverage.json
writes every body at once, as a "C1" list of rows; that form is read too.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import datetime as dt
import glob
import hashlib
import html
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import record_dates  # noqa: E402

AUDIT_DIR = os.path.join(ROOT, "data", "audit")
GRADES_DIR = os.path.join(AUDIT_DIR, "grades")
CACHE_DIR = os.path.join(AUDIT_DIR, "cache")
EXPLANATIONS = os.path.join(AUDIT_DIR, "explanations.csv")
TYPED_FIGURES = os.path.join(AUDIT_DIR, "typed-figures.csv")
OUT_DIR = os.path.join(ROOT, "out", "transportation-audit")
REPORT = os.path.join(OUT_DIR, "report.md")
RESULTS = os.path.join(OUT_DIR, "results.json")
CRITERIA = "pipeline/transportation-data-audit-criteria.md"
BASELINE_DOC = "research/transportation-audit-2026-09/data-quality.md"

MILE = 1609.344
FT = 0.3048
LAT0 = math.radians(37.76)
SF_BBOX = (-122.53, 37.70, -122.35, 37.835)  # the city incl. Treasure Island, not the Farallones
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
INSTITUTIONAL = re.compile(r"^(bos|boardofappeals|mtaboard|info|sfpuc|dpw)@", re.I)

OWN_GRADES = {"exact", "strong", "probable"}
OWN_PAGE = "listed on this project's own page"
# Every city body tools/projects/project-record.py attaches records from (the kinds in its MIRRORS).
BODY_KINDS = {"hearing", "board", "supervisors", "sfpuc", "pwc", "pwdelegated", "sfcta", "recpark"}
DONE_PHASES = {"Completed", "Project Evaluation", "test"}
# Bryan, 2026-09-29: "Don't include projects that were done before the BRP came
# into effect." A project whose own page gives a construction end before the
# plan's adoption is finished for A1, whatever phase or status the page still
# shows. The date is the plan's, from site/data/bike-progress.json "adopted".
PLAN_ADOPTED = "2025-03-04"
# Where the bike section's pages render since 2026-09-29 (Bryan: "All of the
# pages should nest under /transportation/bike"). The old addresses hold
# redirect pages only.
BIKE = "transportation/bike"

# SFMTA's layer tags a project with the modes it serves. Bike or pedestrian
# infrastructure (criterion A1, Bryan 2026-09-28: "We should never miss an
# SFMTA project that has something to do with biking or pedestrian
# infrastructure") is any of these tags, or these words in the name.
BIKEPED_TYPES = {"Bike", "Walk", "Quick-Build", "Vision Zero"}
BIKEPED_WORDS = re.compile(
    r"\bbik|\bbicycl|bikeway|slow street|quick.?build|pedestrian|\bwalk|crosswalk|sidewalk|"
    r"streetscape|traffic calming|safety|neighborway|greenway|complete street|vision zero", re.I)

STATUS = ("PASS", "FAIL", "NOT GRADED", "NOT MEASURED")


# ---------------------------------------------------------------------------
# Small geometry kit, metres on a flat projection at the city's latitude.

def xy(p):
    return (math.radians(p[0]) * math.cos(LAT0) * 6371008.8, math.radians(p[1]) * 6371008.8)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def line_length(pts):
    P = [xy(p) for p in pts]
    return sum(math.dist(a, b) for a, b in zip(P, P[1:]))


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def self_intersects(pts):
    """True when two non-adjacent segments of a line cross; None when too long to test cheaply."""
    P = [xy(p) for p in pts]
    S = list(zip(P, P[1:]))
    if len(S) > 400:
        return None
    for i in range(len(S)):
        for j in range(i + 2, len(S)):
            if i == 0 and j == len(S) - 1 and P[0] == P[-1]:
                continue  # a closed ring meets itself at its start
            a, b = S[i]
            c, d = S[j]
            if _ccw(c, d, a) * _ccw(c, d, b) < 0 and _ccw(a, b, c) * _ccw(a, b, d) < 0:
                return True
    return False


def max_offset(pts, ref):
    """Largest distance in metres from any vertex of pts to the polyline ref."""
    Q = [xy(p) for p in ref]
    S = list(zip(Q, Q[1:])) or [(Q[0], Q[0])]
    return max(min(seg_dist(xy(p), a, b) for a, b in S) for p in pts)


def lines_of(geom):
    """Every line (or ring) of a GeoJSON geometry, as coordinate lists."""
    if not geom:
        return []
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "LineString":
        return [c]
    if t == "MultiLineString" or t == "Polygon":
        return c
    if t == "MultiPolygon":
        return [r for poly in c for r in poly]
    if t == "Point":
        return [[c]]
    if t == "MultiPoint":
        return [c]
    return []


# ---------------------------------------------------------------------------
# Names. One fuzzy rule for "the same project under nearly the same name",
# used by A1, A3, B1 and B3 alike so they cannot disagree.

from lib.samename import (  # noqa: E402  one rule for the pipeline and the audit
    ABBR, GENERIC, KIND, STOP, STREET_WORDS, _same_name, name_tokens, same_name)


def core_regex(name):
    """A search pattern for a project's name in a free-text record: its tokens in order, loosely joined."""
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in STOP]
    alt = {"street": "(?:st|street)", "st": "(?:st|street)", "avenue": "(?:ave?|avenue)", "ave": "(?:ave?|avenue)",
           "boulevard": "(?:blvd|boulevard)", "blvd": "(?:blvd|boulevard)"}
    if len(words) < 2:
        return None
    return re.compile(r"\b" + r"[\s\-/&,.]+(?:and\s+|the\s+)?".join(alt.get(w, re.escape(w)) for w in words) + r"\b", re.I)


# ---------------------------------------------------------------------------
# Results and the registry.

class Result:
    def __init__(self, cid, title, pass_line):
        self.cid, self.title, self.pass_line = cid, title, pass_line
        self.status = "NOT MEASURED"
        self.measured = None
        self.denominator = None
        self.details = []
        self.baseline = BASELINE.get(cid)
        self.vs_baseline = None
        self.failing = []  # (key, why) for each row that counts against the pass line; --explain prints them
        self.facts = {}    # figures the "Against the first run" text quotes, computed here

    def fail(self, key, why=""):
        self.failing.append((str(key), str(why or "")))

    def line(self, s=""):
        self.details.append(s)

    def table(self, header, rows, limit=None):
        rows = list(rows)
        # A table directly under a line of text is read as part of that
        # paragraph, not as a table, so it always starts after a blank line.
        if self.details and self.details[-1] != "":
            self.details.append("")
        self.details.append("| " + " | ".join(header) + " |")
        self.details.append("| " + " | ".join("---" for _ in header) + " |")
        for r in rows[:limit] if limit else rows:
            self.details.append("| " + " | ".join(md_cell(c) for c in r) + " |")
        if limit and len(rows) > limit:
            self.details.append(f"\n{len(rows) - limit} more rows not shown.")
        self.details.append("")

    def verdict(self, ok):
        self.status = "PASS" if ok else "FAIL"


def md_cell(c):
    return str(c if c is not None else "—").replace("|", "\\|").replace("\n", " ")


CHECKS = []


def check(cid, title, pass_line):
    def wrap(fn):
        CHECKS.append((cid, title, pass_line, fn))
        return fn
    return wrap


# The first run's numbers, from research/transportation-audit-2026-09/data-quality.md
# (measured 2026-09-28), so the report can say where this run differs.
BASELINE = {
    "A1-SFMTA": "fail: 25 active non-Bike projects on plan blocks missing, 23 Bike-tagged no-phase dropped (21 on plan), 196 sitemap pages not on the layer",
    "A1-PW": "gap: 104 in-progress pages, 38 with blocks, 29 on plan, 9 cover plan blocks no listed project covers",
    "A1-SFPUC": "not measured: no SFPUC project list read",
    "A2": "gap: 9 active other-agency jobs on plan blocks, none named on About",
    "A3": "gap: 1 name twice; 9 pairs ≥ 50% block overlap; 3 cross-source pairs not merged",
    "B1": "fail: Public Works 0 of 129, SFPUC 0 of 24, SFMTA 29 of 41; 7 of the other 12 SFMTA have a page",
    "B2": "gap: start missing 7 of 194, end 21; scope on feed rows only; 2 with no geometry",
    "B3": "gap: 6 of 17 same-name SFMTA/Public Works projects disagree; neither page shows the other",
    "C1": "fail: hearings from 2019-08 with 23 of 144 unread; Board bike items only; BoS 24 terms, titles; SFPUC from 2021; PW Commission, SFCTA not read",
    "C2": "fail: 2 of 43 major projects have 3 or more dated city-body records",
    "C3a": "fail: 156 of 213 items under City decisions come from the project's own page; 25 events labelled SFMTA Board",
    "C3b": "fail: contract awards naming the job's contract number are missed (3 found)",
    "C3c": "not run: no hand-check of a link sample",
    "C4": "not in the first run (criterion added 2026-09-28)",
    "D1": "fail: 0 end-before-start; 2 past-end rows current; 44 Planning/Design with start passed; 8 start after 2032; 1 future city-body record",
    "D2": "not in the first run (criterion added 2026-09-28)",
    "E1": "pass for drawn files (plan, bikeway, all-ages); project geometry 2 empty; raw layer 6 self-intersecting, 5 zero-length",
    "E2": "fail: 51 of 3,017 bikeway segments > 15 m, 21 > 100 m; 21 retired CNNs (+12 all-ages); 153 split-block CNNs",
    "E3": "fail: 2,257 of 8,414 blocks drawn (27%); 152 of 194 maps draw under half",
    "F1": "gap: 0 metric units; 'mi' is centerline on Current Projects, per direction on Better Coordination (47.5 vs 78.3 for 91 jobs)",
    "F2": "gap: 830,235 (ACS) on the overview, 873,965 (2020 census) in reach; not labelled",
    "F3": "pass, 1 gap: all inside horizon; typed 'updated only through December 2025' disagrees with layer edit 2026-05-21",
    "F4": "gap: 3 of 3 traced figures reach a row; 3 figures typed into prose",
    "F5": "gap: 0 in site data; 2 in out/sfmta-board/meetings.json; 1 SFMTA name with â€“",
    "S1": "not in the first run (criterion added 2026-09-28)",
}


# ---------------------------------------------------------------------------
# Inputs, each read once.

def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def load_module(name, path):
    return paths.load(os.path.basename(path), name)


class Ctx:
    def __init__(self, today, dist, refresh=False):
        self.refresh = refresh
        self.today = today
        self.today_s = today.isoformat()
        self.dist = dist  # the rendered site's dist/ or None
        self._cache = {}

    def once(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # -- the list and its sources
    @property
    def coord(self):
        return self.once("coord", lambda: load("site/data/coordination.json"))

    @property
    def projects(self):
        return self.coord["projects"]

    @property
    def record(self):
        return self.once("record", lambda: {p["id"]: p for p in load("out/project-record/projects.json")["projects"]})

    @property
    def layer(self):
        return self.once("layer", lambda: load("out/sfmta-projects/projects.json")["projects"])

    @property
    def layer_geo(self):
        return self.once("layer_geo", lambda: load("out/sfmta-projects/projects.geojson")["features"])

    @property
    def sitemap(self):
        return self.once("sitemap", load_sitemap)

    @property
    def sitemap_pages(self):
        return self.once("sitemap_pages", lambda: load("data/extract/sfmta-pages/sitemap.json")["records"])

    @property
    def page_dates(self):
        """out/sfmta-page-dates/dates.json by sitemap node: each SFMTA page's Project Status field and the
        construction end TypeSafe's Jev read from its text. A reading of the page, not a pipeline decision."""
        return self.once("page_dates", lambda: load("out/sfmta-page-dates/dates.json")["pages"]
                         if os.path.exists(os.path.join(ROOT, "out/sfmta-page-dates/dates.json")) else {})

    @property
    def dept_page_dates(self):
        """out/dept-page-dates/dates.json by page URL: the construction dates a model read off each Public Works and
        SFPUC project page's text. A reading of the page, not a pipeline decision."""
        return self.once("dept_page_dates", lambda: load("out/dept-page-dates/dates.json")["pages"]
                         if os.path.exists(os.path.join(ROOT, "out/dept-page-dates/dates.json")) else {})

    @property
    def dpw(self):
        return self.once("dpw", lambda: load("data/extract/dpw-projects/projects.json")["records"])

    @property
    def feed(self):
        def read():
            # The feed is read from the Socrata cache the pipeline wrote, never
            # live unless --refresh asked for it: a clean checkout would
            # otherwise pull today's rows and measure against a different feed
            # than coordination.json was built from.
            if not self.refresh and not glob.glob(os.path.join(ROOT, "data", "socrata-cache", "btxj-k9uh-*.json")):
                return None
            from sfdata import fetch
            r = fetch("btxj-k9uh", refresh=self.refresh)
            jobs = collections.defaultdict(list)
            for row in r.rows:
                pid = str(row.get("dotmapsid") or "").strip()
                if pid:
                    jobs[pid].append(row)
            return {"fetched_on": r.fetched_on, "jobs": jobs}
        return self.once("feed", read)

    @property
    def plan(self):
        def read():
            out = {}
            for f in load("site/data/north-star/traced.geojson")["features"]:
                out[f["properties"]["cnn"]] = f
            return out
        return self.once("plan", read)

    @property
    def centerline(self):
        def read():
            best = None
            for f in glob.glob(os.path.join(ROOT, "data", "socrata-cache", "3psu-pn9h-*.json")):
                if os.path.getsize(f) < 5_000_000:
                    continue
                with open(f) as fh:
                    d = json.load(fh)
                if d.get("params", {}).get("$select"):
                    continue
                if best is None or d["fetched_on"] > best["fetched_on"]:
                    best = d
            if best is None:
                return None
            lines, active, oneway, street, nodes = {}, {}, {}, {}, {}
            for r in best["rows"]:
                g = r.get("line")
                if g and g.get("coordinates"):
                    lines[r["cnn"]] = g["coordinates"]
                    active[r["cnn"]] = r.get("active")
                    oneway[r["cnn"]] = r.get("oneway")
                    street[r["cnn"]] = r.get("streetname") or r.get("street")
                    nodes[r["cnn"]] = (r.get("f_node_cnn"), r.get("t_node_cnn"))
            return {"fetched_on": best["fetched_on"], "lines": lines, "active": active, "oneway": oneway, "street": street,
                    "nodes": nodes}
        return self.once("centerline", read)

    @property
    def appendix_l(self):
        return self.once("appendix_l", lambda: appendix_l_reference(self))

    @property
    def plan_map(self):
        return self.once("plan_map", lambda: plan_map_reference(self))

    @property
    def miles_ref(self):
        return self.once("miles_ref", lambda: mile_reference(self))

    @property
    def cp(self):
        return self.once("cp", lambda: load_module("coordination_projects", "tools/projects/coordination-projects.py"))

    # -- the rendered site
    def page_text(self, rel):
        """Visible text of a rendered page, or None when the site was not built."""
        if not self.dist:
            return None
        path = os.path.join(self.dist, rel)
        if not os.path.exists(path):
            return None
        return self.once("page:" + rel, lambda: visible_text(open(path, encoding="utf-8").read()))

    def project_detail(self, slug):
        """The text of a project page's own detail section, without the list beside it."""
        if not self.dist:
            return None
        path = os.path.join(self.dist, BIKE, "projects", slug, "index.html")
        if not os.path.exists(path):
            return None

        def read():
            h = open(path, encoding="utf-8").read()
            m = re.search(r'<section class="coord-detail".*?</section>', h, re.S)
            return visible_text(m.group(0) if m else "")
        return self.once("detail:" + slug, read)

    def project_detail_html(self, slug):
        """The markup of a project page's own detail section, for its links' addresses."""
        if not self.dist:
            return None
        path = os.path.join(self.dist, BIKE, "projects", slug, "index.html")
        if not os.path.exists(path):
            return None

        def read():
            h = open(path, encoding="utf-8").read()
            m = re.search(r'<section class="coord-detail".*?</section>', h, re.S)
            return html.unescape(m.group(0) if m else "")
        return self.once("detailhtml:" + slug, read)

    def notice_pages(self):
        """{slug: (heading, visible text)} for every rendered project address that is a notice, not a listed project.

        Read from the built site, not from the list's data: a notice page is
        any /transportation/bike/projects/<slug>/ page with a heading and no
        project detail section (a redirect page has neither).
        """
        def read():
            out = {}
            listed = {p["slug"] for p in self.projects}
            for path in sorted(glob.glob(os.path.join(self.dist or "", BIKE, "projects", "*", "index.html"))):
                slug = os.path.basename(os.path.dirname(path))
                if slug in listed:
                    continue
                h = open(path, encoding="utf-8").read()
                m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
                if m and 'class="coord-detail"' not in h:
                    out[slug] = (html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip(), visible_text(h))
            return out
        return self.once("notice_pages", read) if self.dist else {}

    def rendered_pages(self):
        if not self.dist:
            return []
        return sorted(glob.glob(os.path.join(self.dist, "transportation", "**", "*.html"), recursive=True))


def cnn_key(v):
    return str(v or "").split(".")[0].lstrip("0")


NORTH_STAR_MAP_URL = "https://www.sfmta.com/media/41812/download"
NORTH_STAR_MAP = os.path.join(ROOT, ".cache", "north-star-map", "northstar-map.pdf")
# A drawn point belongs to a block when it lies within this of the block's line
# and runs along it (|cos| above PLAN_COS); an end of the block is reached when
# the drawn extent comes within PLAN_TOL_M of it. Half the drawn stroke is 16 m.
PLAN_TOL_M, PLAN_COS, PLAN_STEP_M = 20.0, 0.85, 5.0
# A gap in a drawn line up to this long is the map's, not the plan's: the
# dotted Undecided line on Polk breaks for 68 m under a callout marker at
# Francisco (rendered and checked 2026-09-29).
PLAN_DASH_GAP_M = 70.0
# A block is the plan's when the drawn line spans half of it and runs, point by
# point, along at least half its length.
PLAN_MIN_EXTENT, PLAN_MIN_DRAWN = 0.5, 0.5
NOT_A_STREET = re.compile(r"\bI-\d|HWY \d|HIGHWAY|RAMP|FWY|FREEWAY")


NORTH_STAR_APPENDIX_URL = "https://www.sfmta.com/media/41946/download"
NORTH_STAR_APPENDIX = os.path.join(ROOT, ".cache", "north-star-appendix", "appendix.pdf")
# Appendix L's own sentence on which of the two decides, read 2026-09-29.
APPENDIX_L_DEFERS = ("The following is an index of roadway segments that appear on the North Star map "
                     "(pages 68–69). If discrepancies between this index and the map occur, defer to the map.")
# A block Appendix L names is on the map where the map draws a line along it
# within this: half the narrowest block, so a named street never takes its
# neighbour's line. The map is drawn by hand, and along the Sunset's avenues
# its line sits 20-40 m off the street the index names.
NAMED_TOL_M = 40.0
# Appendix L's walk. A cross street that stops short of the street still ends
# the row within END_NEAR_M: Point Lobos's row runs "48th Ave" to "Balboa", and
# Point Lobos ends at the Great Highway 195 m from Balboa's nearest node. Two of
# a street's own nodes within BRIDGE_M are one place (a break in the graph; San
# Jose Ave's breaks by 45 m at the I-280 ramps).
END_NEAR_M, BRIDGE_M = 250.0, 50.0
_OPEN_END = {"", "-", "---", "—"}
_TYPES = {"ST", "AVE", "BLVD", "DR", "WAY", "RD", "LN", "PL", "CT", "TER", "HWY", "PKWY", "CIR", "ALY", "PATH",
          "STWY", "PLZ", "LOOP", "ROW", "WALK", "EXPY", "STREET", "AVENUE", "BOULEVARD", "DRIVE", "ROAD", "LANE",
          "PLACE", "TERRACE", "HIGHWAY", "PARKWAY", "CIRCLE", "ALLEY"}
_DIRS = {"EB", "WB", "NB", "SB", "N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"}
_NAME_ALIASES = {"JFK": "JOHN F KENNEDY", "MLK": "MARTIN LUTHER KING JR", "MARTIN LUTHER KING": "MARTIN LUTHER KING JR",
                 "BAYSHORE": "BAY SHORE", "MT VERNON": "MOUNT VERNON", "UPPER MARKET": "MARKET",
                 "EMBARCADERO": "THE EMBARCADERO", "MISSISSIPI": "MISSISSIPPI", "FANCISCO": "FRANCISCO",
                 "HARROLD": "HAROLD", "UPPER GREAT": "GREAT"}


def street_key(name):
    """A street name reduced to what Appendix L and the centerline file share:
    '34th Ave' and '34TH AVE' -> '34', 'Alemany EB' -> 'ALEMANY'."""
    s = re.sub(r"[.,'’]", "", (name or "").upper())
    toks = s.split()
    while len(toks) > 1 and toks[-1] in _DIRS:
        toks.pop()
    if len(toks) > 1 and toks[-1] in _TYPES:
        toks.pop()
    toks = [re.sub(r"^0*(\d+)(ST|ND|RD|TH)$", r"\1", t) for t in toks]
    k = " ".join(toks)
    return _NAME_ALIASES.get(k, k)


def appendix_l_rows(text):
    """The rows of Appendix L's table, read by column position from each page's header line."""
    rows, cols, inside = [], None, False
    for ln in text.split("\n"):
        if "Appendix L" in ln and "North Star Index" in ln:
            inside = True
            continue
        if not inside:
            continue
        if re.match(r"\s*Appendix [M-Z]\b", ln):
            break
        if re.match(r"\s*Street\s+From\s+To\s+Existing Facility\s+North Star Facility\s+New\?", ln):
            cols = [ln.index(w) for w in ("Street", "From", "To ", "Existing Facility", "North Star Facility", "New?", "Upgrade?")]
            continue
        if cols is None or not ln.strip():
            continue
        cells = [ln[a:b].strip() for a, b in zip(cols, cols[1:] + [len(ln) + 1])]
        if len(cells) == 7 and cells[0] and cells[5][:1] in ("Y", "N") and cells[6][:1] in ("Y", "N"):
            rows.append(dict(zip(("street", "from", "to", "existing", "north_star", "new", "upgrade"), cells)))
    return rows


def appendix_l_reference(ctx):
    """Which blocks Appendix L names, read here from the plan's appendix PDF.

    Fetches the appendix (sfmta.com, cached in .cache/north-star-appendix/),
    reads Appendix L's table with pdftotext, and places each row on today's
    street centerline (DataSF 3psu-pn9h) by this function's own walk: the
    street's blocks from the node it shares with the From street to the node
    it shares with the To street, by the shortest run of the street's own
    blocks; an open end runs to the street's end. A row whose North Star
    facility is "None" names no network block. The pipeline's placement
    (tools/bike-network/north-star-index.py, segments.geojson) is not read.

    Returns {"named": {cnn: row}, "rows", "placed", "unplaced", "defers", "sha256"} or {"missing": why}.
    """
    import heapq
    cl = ctx.centerline
    if not cl:
        return {"missing": "no full street centerline pull in data/socrata-cache/"}
    if not shutil.which("pdftotext"):
        return {"missing": "pdftotext (poppler) is not installed"}
    if not os.path.exists(NORTH_STAR_APPENDIX):
        try:
            req = urllib.request.Request(NORTH_STAR_APPENDIX_URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as fh:
                body = fh.read()
            if not body.startswith(b"%PDF"):
                return {"missing": "the plan appendix URL did not return a PDF"}
            os.makedirs(os.path.dirname(NORTH_STAR_APPENDIX), exist_ok=True)
            with open(NORTH_STAR_APPENDIX, "wb") as fh:
                fh.write(body)
        except Exception as e:  # noqa: BLE001
            return {"missing": "the plan appendix could not be fetched: %s" % str(e)[:80]}
    text = subprocess.run(["pdftotext", "-layout", NORTH_STAR_APPENDIX, "-"], check=True,
                          capture_output=True).stdout.decode("utf-8", "replace")
    rows = appendix_l_rows(text)
    if len(rows) < 300:
        return {"missing": "only %d Appendix L rows read from the appendix" % len(rows)}
    defers = " ".join(APPENDIX_L_DEFERS.split()) in " ".join(text.split())
    by_street, node_xy, node_streets, length = collections.defaultdict(list), {}, collections.defaultdict(set), {}
    for c, p in sorted(cl["lines"].items()):
        if str(cl["active"].get(c)).lower() != "true" or len(p) < 2:
            continue
        f, t = cl["nodes"].get(c) or (None, None)
        if not f or not t:
            continue
        k, key = cnn_key(c), street_key(cl["street"].get(c))
        by_street[key].append((k, f, t))
        node_xy.setdefault(f, xy(p[0]))
        node_xy.setdefault(t, xy(p[-1]))
        node_streets[f].add(key)
        node_streets[t].add(key)
        length[k] = line_length(p)

    def place(r):
        blocks = [b for part in r["street"].split("/") for b in by_street.get(street_key(part), [])]
        if not blocks:
            return None
        own = {n for _, f, t in blocks for n in (f, t)}
        adj = collections.defaultdict(list)
        for k, f, t in blocks:
            adj[f].append((t, k))
            adj[t].append((f, k))
        # The centerline file breaks some streets' graphs at an offset
        # intersection: Plymouth between Monterey and Sagamore by 33 m,
        # Junipero Serra between Portola and Holloway by 18-22 m, San Jose
        # between Monterey and Guerrero by 45 m (checked 2026-09-29). Two of the street's own nodes within BRIDGE_M are one
        # place, joined by a link of no length that names no block.
        near_own = sorted(n for n in own if n in node_xy)
        for i, n in enumerate(near_own):
            for m in near_own[i + 1:]:
                if math.dist(node_xy[n], node_xy[m]) <= BRIDGE_M and not any(q == m for q, _ in adj[n]):
                    adj[n].append((m, None))
                    adj[m].append((n, None))

        def end(label):
            if label.strip() in _OPEN_END:
                return "open", set()
            got = set()
            for part in label.split("/"):
                x = street_key(part)
                hit = {n for n in own if x in node_streets[n]}
                if not hit:
                    far = [node_xy[n] for n, ks in sorted(node_streets.items()) if x in ks and n in node_xy]
                    best = min(((min(math.dist(node_xy[n], q) for q in far), n) for n in sorted(own) if n in node_xy),
                               default=None) if far else None
                    if best and best[0] <= END_NEAR_M:
                        hit = {best[1]}
                got |= hit
            return ("ok" if got else "missing"), got

        fa, A = end(r["from"])
        ta, B = end(r["to"])
        if "missing" in (fa, ta):
            return None
        if fa == "open" and ta == "open":
            return {k for k, _, _ in blocks}
        if "open" in (fa, ta):
            start = A or B
            seen, todo, out = set(start), sorted(start), set()
            while todo:
                n = todo.pop()
                for m, k in adj[n]:
                    if k:
                        out.add(k)
                    if m not in seen:
                        seen.add(m)
                        todo.append(m)
            return out
        # The street's blocks on a run from A to B no more than a quarter
        # longer than the shortest, by the street's own blocks: a divided
        # street's two carriageways, and two roads of one name side by side
        # (the upper and lower Great Highway), are both the row's. The map
        # then says which of them the plan draws.
        def reach(starts):
            dist, heap = {}, []
            for n in sorted(starts):
                dist[n] = 0.0
                heapq.heappush(heap, (0.0, n))
            while heap:
                d, n = heapq.heappop(heap)
                if d > dist.get(n, 1e18):
                    continue
                for m, k in adj[n]:
                    nd = d + length.get(k, 0.0)
                    if nd < dist.get(m, 1e18):
                        dist[m] = nd
                        heapq.heappush(heap, (nd, m))
            return dist
        da, db = reach(A), reach(B)
        best = min((da[n] for n in B if n in da and n not in A), default=None)
        if best is None:
            return None
        lim = 1.25 * best + 50.0

        def through(k, x, y):
            # A run A..x, the block, y..B that does not double back over the
            # block. Without the test, a dead-end stub past an end (McCoppin
            # west of Valencia, on the Otis / McCoppin row that runs from
            # Valencia) fit inside the 50 m allowance.
            L = length.get(k, 0.0)
            ax, by_ = da.get(x, 1e18), db.get(y, 1e18)
            return (ax + L + by_ <= lim and by_ < db.get(x, 1e18) + L - 1e-6
                    and ax < da.get(y, 1e18) + L - 1e-6)
        return {k for k, f, t in blocks if through(k, f, t) or through(k, t, f)}

    named, unplaced, placed = {}, [], 0
    for r in rows:
        got = place(r)
        if not got:
            unplaced.append(r)
            continue
        placed += 1
        if r["north_star"].strip().lower() == "none":
            continue
        for k in sorted(got):
            named.setdefault(k, r)
    return {"named": named, "rows": len(rows), "placed": placed, "unplaced": unplaced, "defers": defers,
            "sha256": hashlib.sha256(open(NORTH_STAR_APPENDIX, "rb").read()).hexdigest()}


def plan_map_reference(ctx):
    """How much of each block the plan's map draws, measured here from the map.

    Reads SFMTA's North Star map PDF (the plan's own geometry; fetched to
    .cache/north-star-map/ when missing), pulls the network strokes out by
    legend colour and fits the map to today's street centerline (DataSF
    3psu-pn9h, the Socrata cache), with the PDF readers and the fit in
    tools/bike-network/north-star-map-trace.py. The measure is this function's own code:
    every drawn point, every 5 m, is projected onto each block it runs along
    within 20 m, and a block's drawn part is the span of those projections,
    snapped to an end within 20 m or where another plan block meets it (About
    the data's rule). The trace's output (traced.geojson) is not read. A block
    Appendix L names (appendix_l_reference, read here from the appendix) is
    measured within NAMED_TOL_M instead of PLAN_TOL_M.

    Returns {"blocks": {cnn: {"L", "share", "drawn", "member", "by"}}, "fit", "sha256"}
    or {"missing": why}.
    """
    cl = ctx.centerline
    if not cl:
        return {"missing": "no full street centerline pull in data/socrata-cache/"}
    if "missing" in ctx.appendix_l:
        return ctx.appendix_l
    if not shutil.which("pdftocairo"):
        return {"missing": "pdftocairo (poppler) is not installed"}
    if not os.path.exists(NORTH_STAR_MAP):
        try:
            req = urllib.request.Request(NORTH_STAR_MAP_URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as fh:
                body = fh.read()
            if not body.startswith(b"%PDF"):
                return {"missing": "the North Star map URL did not return a PDF"}
            os.makedirs(os.path.dirname(NORTH_STAR_MAP), exist_ok=True)
            with open(NORTH_STAR_MAP, "wb") as fh:
                fh.write(body)
        except Exception as e:  # noqa: BLE001
            return {"missing": "the North Star map could not be fetched: %s" % str(e)[:80]}
    sha = hashlib.sha256(open(NORTH_STAR_MAP, "rb").read()).hexdigest()
    T = load_module("north_star_map_trace", "tools/bike-network/north-star-map-trace.py")
    tmp = tempfile.mkdtemp(prefix="sfw-audit-map-")
    try:
        net, base, _ = T.read_map(T.svg_from_pdf(NORTH_STAR_MAP, os.path.join(tmp, "map.svg")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    names = cl.get("street") or {}
    rows = [{"line": {"coordinates": p}} for c, p in sorted(cl["lines"].items())
            if str(cl["active"].get(c)).lower() == "true" and len(p) >= 2 and not NOT_A_STREET.search(names.get(c) or "")]
    a, fit = T.fit_georeference(base, rows)
    cell = 50.0
    blocks, cells, key_cnn = {}, collections.defaultdict(list), {}
    for c, p in sorted(cl["lines"].items()):
        if str(cl["active"].get(c)).lower() != "true" or len(p) < 2 or NOT_A_STREET.search(names.get(c) or ""):
            continue
        k = cnn_key(c)
        key_cnn[k] = c
        pts = [xy(q) for q in p]
        cum = [0.0]
        for u, v in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(u, v))
        blocks[k] = (pts, cum)
        for i, (u, v) in enumerate(zip(pts, pts[1:])):
            for gx in range(int(min(u[0], v[0]) // cell), int(max(u[0], v[0]) // cell) + 1):
                for gy in range(int(min(u[1], v[1]) // cell), int(max(u[1], v[1]) // cell) + 1):
                    cells[(gx, gy)].append((k, i))
    ext, ext_named = {}, {}
    for cls in sorted(net):
        for P in net[cls]:
            ll = [xy(((x - a[1]) / a[0], (y - a[3]) / a[2])) for x, y in P]
            for p, q in zip(ll, ll[1:]):
                L = math.dist(p, q)
                if L < 1e-6:
                    continue
                u = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
                n = max(1, int(L / PLAN_STEP_M))
                for j in range(n + 1):
                    s = (p[0] + (q[0] - p[0]) * j / n, p[1] + (q[1] - p[1]) * j / n)
                    gx, gy = int(s[0] // cell), int(s[1] // cell)
                    near = {}
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            for k, i in cells.get((gx + dx, gy + dy), ()):
                                A, B = blocks[k][0][i], blocks[k][0][i + 1]
                                sl = math.dist(A, B)
                                if sl < 1e-6:
                                    continue
                                v = ((B[0] - A[0]) / sl, (B[1] - A[1]) / sl)
                                if abs(u[0] * v[0] + u[1] * v[1]) <= PLAN_COS:
                                    continue
                                t = (s[0] - A[0]) * v[0] + (s[1] - A[1]) * v[1]
                                # A point past either end of the block is on
                                # the next block, not this one.
                                if (i == 0 and t < 0) or (i == len(blocks[k][0]) - 2 and t > sl):
                                    continue
                                t = max(0.0, min(sl, t))
                                d = math.dist(s, (A[0] + v[0] * t, A[1] + v[1] * t))
                                if d <= NAMED_TOL_M and (k not in near or d < near[k][0]):
                                    near[k] = (d, blocks[k][1][i] + t)
                    for k, (d, at) in near.items():
                        for e, lim in ((ext, PLAN_TOL_M), (ext_named, NAMED_TOL_M)):
                            if d <= lim:
                                x = e.setdefault(k, [at, at, []])
                                x[0], x[1] = min(x[0], at), max(x[1], at)
                                x[2].append(at)

    def along(ats):
        # Runs of points no more than PLAN_DASH_GAP_M apart, first to last
        # plus a step. A count of points read Polk, Bay to North Point, drawn
        # end to end but for a marker, as 38% (checked 2026-09-29).
        ats = sorted(ats)
        tot, start = 0.0, ats[0]
        for a, b in zip(ats, ats[1:]):
            if b - a > PLAN_DASH_GAP_M:
                tot += a - start + PLAN_STEP_M
                start = b
        return tot + ats[-1] - start + PLAN_STEP_M

    def measure(k, lo, hi, ats):
        L = blocks[k][1][-1]
        lo = 0.0 if lo <= PLAN_TOL_M else lo
        hi = L if L - hi <= PLAN_TOL_M else hi
        share, drawn = max(0.0, hi - lo) / L, min(1.0, along(ats) / L)
        return share, drawn, share >= PLAN_MIN_EXTENT and drawn >= PLAN_MIN_DRAWN, lo, hi

    # The plan's network is what its map draws (Appendix L: "defer to the
    # map"). A block Appendix L names is on the map where the map draws a line
    # along it within NAMED_TOL_M, since the hand-drawn line sits 20-40 m off
    # some named streets; any other block needs the line within PLAN_TOL_M.
    # A named block is measured at NAMED_TOL_M for its span too, not only for
    # membership: measured at 20 m first, 12th Ave from Lincoln to Irving,
    # whose line runs 20.1-21.1 m off the whole block, counted 61% of itself,
    # and would have counted all of it had the line sat a metre further off
    # (checked 2026-09-29).
    named = ctx.appendix_l.get("named") or {}
    out, span = {}, {}
    for k in sorted(set(ext) | set(ext_named)):
        L = blocks[k][1][-1]
        if L <= 0:
            continue
        near = measure(k, *ext[k]) if k in ext else (0.0, 0.0, False, 0.0, 0.0)
        if k in named and k in ext_named:
            share, drawn, member, lo, hi = measure(k, *ext_named[k])
            by = ("map" if near[2] else "Appendix L and the map") if member else None
        else:
            share, drawn, member, lo, hi = near
            by = "map" if member else None
        out[k] = {"L": L, "share": share, "drawn": drawn, "member": member, "by": by}
        span[k] = (lo, hi)
    # About the data (#directions): "Where the plan's line stops partway
    # along a block, short of its end and of any other plan block there, the
    # block counts the part the line reaches; a block the line runs through
    # counts whole." So an end of a plan block where another plan block meets
    # it is reached, wherever the drawn line stops.
    by_node = collections.defaultdict(set)
    for k, r in out.items():
        if r["member"]:
            for nd in cl["nodes"].get(key_cnn[k]) or ():
                if nd:
                    by_node[nd].add(k)
    for k, r in out.items():
        if not r["member"]:
            continue
        lo, hi = span[k]
        f, t = cl["nodes"].get(key_cnn[k]) or (None, None)
        if f and by_node[f] - {k}:
            lo = 0.0
        if t and by_node[t] - {k}:
            hi = r["L"]
        r["share"] = max(0.0, hi - lo) / r["L"]
    return {"blocks": out, "fit": fit, "sha256": sha}


def mile_reference(ctx):
    """Each block's miles per direction of travel, measured here from the sources.

    The plan's definition (About the data, "Network miles"): its 472 miles
    (printed p. 20) are the sum of SFMTA's bikeway layer rows' own lengths. So
    a block's metres are the lengths of the layer rows on it, measured here
    from the tracked geometry extract (data/extract/sfmta-bikeway/, SFMTA's
    own layer) with this file's own line_length. Rows are placed on blocks by
    lib/bikeway_snap.py, whose placement E2 audits; a CNN-less path whose
    two ends lie within 25 m of a block's centerline ends is that block's. A
    block the layer lacks counts its centerline length (DataSF 3psu-pn9h) once
    where the centerline's oneway flag is F or T and twice otherwise. A plan
    block counts that times the share of it the plan's map draws, measured
    here from the map PDF (plan_map_reference); which blocks are the plan's
    is decided there too. Nothing here reads a pipeline output's miles or the
    trace. Returns {"missing": why} when the centerline or the map cannot be read.
    """
    from extract import Extract
    from bikeway_snap import rekeyed_layer
    net = Extract("sfmta-bikeway").read("network")
    geo = Extract("sfmta-bikeway").read("geometry")
    if net is None or geo is None:
        return {"missing": "data/extract/sfmta-bikeway/ is missing"}
    pm = ctx.plan_map
    if "missing" in pm:
        return pm
    whole = {g["oid"]: line_length(g["pts"]) for g in geo.records if g.get("pts")}
    cl = ctx.centerline
    ends = {cnn_key(c): (xy(p[0]), xy(p[-1])) for c, p in cl["lines"].items() if p}
    rows_m, rows_n, total, unkeyed = collections.defaultdict(float), collections.Counter(), 0.0, []
    for r in rekeyed_layer(net.records):
        if not r.get("FACILITY_T"):
            continue
        m = whole[r["OBJECTID"]] * (r.get("_share") or 1.0) if r["OBJECTID"] in whole else float(r.get("LENGTH") or 0) * MILE
        total += m
        c = cnn_key(r.get("CNN"))
        if c:
            rows_m[c] += m
            rows_n[c] += 1
        elif r.get("_pts"):
            unkeyed.append((r["_pts"], m))
    aliased = 0
    for pts, m in unkeyed:
        a, b = xy(pts[0]), xy(pts[-1])
        for c, (ea, eb) in sorted(ends.items()):
            if c in rows_m and (max(math.dist(a, ea), math.dist(b, eb)) <= 25 or max(math.dist(a, eb), math.dist(b, ea)) <= 25):
                rows_m[c] += m
                aliased += 1
                break
    plan = {}
    by_key = {cnn_key(c): c for c in cl["lines"]}
    for k, b in pm["blocks"].items():
        if k in rows_m:
            whole_m, how = rows_m[k], "layer rows"
        else:
            ow = cl["oneway"].get(by_key.get(k))
            whole_m, how = b["L"] * (1 if ow in ("F", "T") else 2), "centerline one-way" if ow in ("F", "T") else "centerline"
        share = b["share"] if b["member"] else 0.0
        plan[k] = {"whole": whole_m, "share": share, "m": whole_m * share, "how": how, "L": b["L"],
                   "member": b["member"], "extent": b["share"], "drawn": b["drawn"], "by": b.get("by")}
    return {"rows_m": dict(rows_m), "rows_n": dict(rows_n), "layer_total_m": total, "aliased": aliased,
            "plan": plan, "layer_queried": net.fetched_on.isoformat(), "fit": pm["fit"], "map_sha256": pm["sha256"]}


def project_plan_miles(ctx, p, basis="per direction"):
    """A project's plan miles from the source reference, on the stated basis."""
    ref = ctx.miles_ref
    tot = 0.0
    for c in p.get("planCnns") or []:
        b = ref["plan"].get(cnn_key(c))
        if b is None:
            continue
        if basis == "centerline":
            tot += b["L"] * b["share"]
        else:
            tot += b["m"]
    return tot / MILE


def stated_basis(ctx):
    """The mile basis About the data states, from the rendered page, or None."""
    about = ctx.page_text("transportation/bike/about/index.html") or ""
    if re.search(r"counted per direction of travel", about, re.I):
        return "per direction"
    if re.search(r"centerline miles|each block once|once per block", about, re.I):
        return "centerline"
    return None


def visible_text(h, charts=False):
    """A page's visible text; with charts=True, also the labels drawn inside its SVG charts."""
    drop = r"<script.*?</script>|<style.*?</style>" + ("" if charts else r"|<svg.*?</svg>")
    h = re.sub(drop, " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


# ---------------------------------------------------------------------------
# Tracked hand inputs: explanations, grades, typed-figure verdicts.

def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]


def explanations():
    out = collections.defaultdict(dict)
    for r in read_csv(EXPLANATIONS):
        out[r["check"].strip()][r["key"].strip().lower()] = r["explanation"].strip()
    return out


EXPLAINED = None


def explained(cid, key):
    """The explanation recorded for this row of this check, or None."""
    global EXPLAINED
    if EXPLAINED is None:
        EXPLAINED = explanations()
    return EXPLAINED.get(cid, {}).get((key or "").strip().lower())


# ---------------------------------------------------------------------------
# Network caches.

UA = "Mozilla/5.0 (sf-works transportation audit; +https://sf-works.org)"


def http_get(url, method="GET", timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return fh.status, fh.read().decode("utf-8", "replace") if method == "GET" else ""


def load_sitemap():
    """SFMTA's /projects/ pages: the cached sitemap, seeded from the pages extract when no cache exists."""
    path = os.path.join(CACHE_DIR, "sfmta-sitemap.json")
    if os.path.exists(path):
        return json.load(open(path))
    ex = load("data/extract/sfmta-pages/sitemap.json")
    urls = sorted({r["canonical"] for r in ex["records"] if r.get("canonical")})
    return {"fetched_on": ex["fetched_on"], "source": "data/extract/sfmta-pages/sitemap.json (seed)", "urls": urls}


def refresh_sitemap():
    status, index = http_get("https://www.sfmta.com/sitemap.xml")
    urls = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", index):
        _, part = http_get(loc.replace("&amp;", "&"))
        urls += re.findall(r"<loc>(https://www\.sfmta\.com/projects/[^<]+)</loc>", part)
    out = {"fetched_on": dt.date.today().isoformat(), "source": "https://www.sfmta.com/sitemap.xml",
           "urls": sorted(set(urls))}
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump(out, open(os.path.join(CACHE_DIR, "sfmta-sitemap.json"), "w"), indent=1)
    print(f"  sitemap: {len(out['urls'])} project pages")


def dept_link(url):
    """True when a link goes to a department's own page for a project, not a dataset row."""
    u = (url or "").lower()
    if "data.sf.gov" in u or "data.sfgov.org" in u:
        return False
    return bool(re.match(r"https?://(www\.)?(sfmta\.com/(node|projects)/|sfpublicworks\.org/|sfpuc\.gov/"
                          r"|bidopportunities\.apps\.sfdpw\.org/caseload/details/|webapps\.sfpuc\.org/bids/biddetail)", u))


BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def browser_read(url):
    """(status, <title>) for a URL read as a browser reads it: its user agent and Accept headers, GET."""
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml",
                                               "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            status, body = fh.status, fh.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - any failure is the finding
        return str(e)[:60], None
    m = re.search(r"<title>([^<]*)</title>", body, re.I)
    return status, html.unescape(m.group(1).strip()) if m else None


def refresh_links():
    """HEAD every department link and closest official source the list shows; re-read any that is not 200 as a browser.

    A page that answers the script and a browser alike with an error is gone,
    and its title says what the site answers ("Content Not Found | SFMTA"). A
    page that answers only the browser blocks robots, and the browser's 200 is
    the evidence it is live; B1 counts it then, and says so.
    """
    coord = load("site/data/coordination.json")
    out, browser = {}, {}
    for p in coord["projects"]:
        for l in p["links"]:
            if (dept_link(l["url"]) or l.get("kind") == "program") and l["url"] not in out:
                try:
                    status, _ = http_get(l["url"], method="HEAD", timeout=30)
                except Exception as e:  # noqa: BLE001 - any failure is the finding
                    status = getattr(e, "code", None) or str(e)[:60]
                out[l["url"]] = status
                if status != 200:
                    b, title = browser_read(l["url"])
                    browser[l["url"]] = {"status": b, "title": title}
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump({"fetched_on": dt.date.today().isoformat(), "status": out, "browser": browser},
              open(os.path.join(CACHE_DIR, "link-status.json"), "w"), indent=1, sort_keys=True)
    print(f"  links: {len(out)} checked, {sum(1 for s in out.values() if s != 200)} not 200, "
          f"{sum(1 for b in browser.values() if b['status'] == 200)} of those answer a browser")


def update_links():
    """Check only the links the list shows that the link-status cache has never checked, and add them to it.

    The incremental half of refresh_links, run on every audit without
    --refresh. Without it, a link the list gained since the last full read (a
    newly matched department page) counts as dead in B1 until somebody runs
    --refresh. Each added link records the day it was read under "added";
    fetched_on keeps the day of the last full read. A link that gets no HTTP
    status at all from either read (the machine is offline, say) is left out
    rather than written down as dead, so an offline run changes nothing, and
    with nothing new the file is not rewritten.
    """
    path = os.path.join(CACHE_DIR, "link-status.json")
    if not os.path.exists(path):
        return
    ls = json.load(open(path))
    coord = load("site/data/coordination.json")
    new = []
    for p in coord["projects"]:
        for l in p["links"]:
            u = l["url"]
            if (dept_link(u) or l.get("kind") == "program") and u not in ls.get("status", {}) and u not in new:
                new.append(u)
    added = 0
    for url in new:
        try:
            status, _ = http_get(url, method="HEAD", timeout=30)
        except Exception as e:  # noqa: BLE001 - any failure is the finding
            status = getattr(e, "code", None) or str(e)[:60]
        b = None
        if status != 200:
            bs, title = browser_read(url)
            b = {"status": bs, "title": title}
        # A server error, timeout or rate limit says nothing about the page, and
        # a URL once written here is not read again without --refresh, so only
        # a definite answer is recorded.
        definite = lambda s: isinstance(s, int) and s not in (408, 429) and s < 500
        if not definite(status) and not definite((b or {}).get("status")):
            print(f"  links: {url} gave no definite answer ({status}); not recorded, read again next run")
            continue
        ls.setdefault("status", {})[url] = status
        if b:
            ls.setdefault("browser", {})[url] = b
        ls.setdefault("added", {})[url] = dt.date.today().isoformat()
        added += 1
    if added:
        with open(path + ".tmp", "w") as fh:
            json.dump(ls, fh, indent=1, sort_keys=True)
        os.replace(path + ".tmp", path)
        print(f"  links: {added} new link(s) checked and added to {os.path.relpath(path, ROOT)}")


def browser_note(ls, url):
    b = ((ls or {}).get("browser") or {}).get(url)
    if not b:
        return "not read"
    return "%s%s" % (b.get("status"), (", “%s”" % b["title"]) if b.get("title") else "")


def link_live(ls, url):
    """True when the link-status cache shows the URL answers: 200 to the script, or 200 to a browser read."""
    ls = ls or {}
    return ls.get("status", {}).get(url) == 200 or (ls.get("browser", {}).get(url) or {}).get("status") == 200


def link_status():
    path = os.path.join(CACHE_DIR, "link-status.json")
    return json.load(open(path)) if os.path.exists(path) else None


# ---------------------------------------------------------------------------
# Helpers the checks share.

def listed_ids(ctx):
    return {p["id"] for p in ctx.projects}


def feed_ids_of(p):
    """Every coordination-feed job id a listed project carries, including one merged into an SFMTA row."""
    ids = set()
    if p["id"].startswith("dotmaps:"):
        ids.add(p["id"].split(":")[1])
    for l in p["links"]:
        m = re.search(r"dotmapsid=(\d+)", l["url"])
        if m:
            ids.add(m.group(1))
    return ids


def all_cnns(ctx, p):
    """Every block a listed project holds: its own record's blocks plus a merged feed job's."""
    out = set(ctx.record.get(p["id"], {}).get("cnns") or [])
    for fid in feed_ids_of(p):
        out |= set(ctx.record.get("dotmaps:" + fid, {}).get("cnns") or [])
    return out


def is_listed_name(ctx, name):
    return next((p for p in ctx.projects if same_name(p["name"], name)), None)


def feed_job_dates(rows):
    day = lambda v: str(v or "")[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", str(v or "")) else None
    start = min((day(r.get("start_date")) for r in rows if day(r.get("start_date"))), default=None)
    end = max((day(r.get("end_date")) for r in rows if day(r.get("end_date"))), default=None)
    return start, end


def iso_date(s):
    """'9/30/2026' or '2026-09-30…' as '2026-09-30'; None otherwise."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None


def pct(n, d):
    return "%.1f%%" % (100.0 * n / d) if d else "—"


def city_body_records(p):
    """A listed project's records that come from a city body and are graded as its own."""
    return [r for r in p["records"] if r.get("grade") in OWN_GRADES and r.get("relation") != OWN_PAGE
            and r.get("kind") in BODY_KINDS]


def start_key(s):
    """A start or end of any precision as its first day, for comparing with today."""
    if not s:
        return None
    s = str(s)
    return s + "-01-01" if len(s) == 4 else s + "-01" if len(s) == 7 else s[:10]


def end_key(s):
    """An end of any precision as its last day."""
    if not s:
        return None
    s = str(s)
    if len(s) == 4:
        return s + "-12-31"
    if len(s) == 7:
        y, m = int(s[:4]), int(s[5:7])
        return (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
    return s[:10]


# ===========================================================================
# A. Which projects we hold

@check("A1-SFMTA", "Completeness: SFMTA",
       "Zero missing. Every active SFMTA project on the plan's blocks is listed, and so is every SFMTA project that "
       "touches bike or pedestrian infrastructure, whether or not SFMTA tags it Bike and whether or not its block is "
       "on the plan.")
def a1_sfmta(ctx, res):
    # Two populations, as the criteria doc's A1 sets them: the What/Measure
    # lines (every active project on the plan's blocks) and Bryan's pass line
    # (every bike or pedestrian project, on the plan or not). A project in
    # either is a candidate; each filter that drops one is listed below.
    listed = listed_ids(ctx)
    layer_nodes = {str(p["node"]) for p in ctx.layer}
    plan_blocks = a1_on_plan(ctx)

    def bikeped(p):
        return bool(set(p.get("types") or []) & BIKEPED_TYPES) or bool(BIKEPED_WORDS.search(p.get("name") or ""))

    # A listed row that links the page counts, as A1-PW counts one: SFMTA
    # splits a project's page into sections with pages of their own (Folsom
    # Street Implementation under the Folsom-Howard Streetscape Project).
    linked_by = {}
    for p in ctx.projects:
        for l in p.get("links") or []:
            linked_by.setdefault((l.get("url") or "").rstrip("/"), p)

    def reached(name, node, url=None):
        if "sfmta:%s" % node in listed:
            return "listed"
        hit = is_listed_name(ctx, name)
        if hit:
            return "as “%s”" % hit["name"]
        hit = linked_by.get((url or "").rstrip("/"))
        return ("linked from “%s”" % hit["name"]) if hit else None

    FINISHED = "layer: phase Completed, Project Evaluation or test"
    PAGE_FINISHED = ("layer: its own page says it is finished (a Completed phase or Project Status field, every "
                     "milestone marked "
                     "Completed and dated before this year, or “the project is now / was … complete”), whatever "
                     "phase the layer gives")
    NOT_STREET_F = "layer: not street work by name (studies, plans, fleets, stations, tunnels, programmes)"
    NEITHER = "layer: active, but neither bike or pedestrian nor on a plan block"
    STALE = ("layer: on plan blocks only (no bike or pedestrian scope), and its page shows no sign of work in the "
             "last year or still to come")
    STALE_OFF_PLAN = ("layer: no bike or pedestrian scope and on no plan block, and its page shows no sign of work in "
                      "the last year or still to come")
    ENDED = ("layer: no phase on the layer or its page, every milestone on its page's timeline is dated before "
             "last year, and nothing on the page dates work since")
    # Bryan, 2026-09-29: past-end work its department does not list as active
    # leaves the list. The end is the one the page's text gives, as TypeSafe's
    # Jev read it (out/sfmta-page-dates/dates.json), when no schedule row on
    # the page runs past today.
    TEXT_ENDED = ("layer: no phase on the layer, its page's phase field or its Project Status field, and the "
                  "construction end its page's text gives has passed, with no schedule row on the page after today")
    PRE_PLAN = ("layer: the construction end its page's text gives is before the plan's adoption on %s, and no "
                "stage on its timeline is dated after that, whatever phase the page still shows" % PLAN_ADOPTED)
    removed = collections.OrderedDict((k, []) for k in (FINISHED, PAGE_FINISHED, PRE_PLAN, ENDED, TEXT_ENDED,
                                                        NOT_STREET_F, NEITHER, STALE))

    def pre_plan_end(node):
        """The construction end the page's text gives, when it falls before the plan's adoption and no timeline
        stage runs past that (5th Street's text says Fall 2023, its timeline runs to 2027), else None. A timeline
        stage alone is not an end: a planning stage dated 2018 does not finish a project."""
        jd = ctx.page_dates.get(str(node)) or {}
        end = ((jd.get("fields") or {}).get("construction_end") or {}).get("iso")
        if end and end < PLAN_ADOPTED and (jd.get("latestStageDate") or "") < PLAN_ADOPTED:
            return end
        return None
    # Each layer project's own page, read here from the pages extract, never
    # from the pipeline's decision file: the layer's phase is stale for old
    # projects, so what the page says is the test (review, 2026-09-29).
    page_of = {str(r.get("node")): r for r in ctx.sitemap_pages if r.get("node")}
    cands, missing = [], []
    for p in ctx.layer:
        node = str(p["node"])
        bp, op = bikeped(p), node in plan_blocks
        pg = page_of.get(node) or {}
        if p["phase"] in DONE_PHASES:
            removed[FINISHED].append(p["name"])
            continue
        # The page's Project Status field's last ticked item counts as its
        # phase field does (Frida Kahlo Way: Legislated, Completed).
        ps_last = ((ctx.page_dates.get(node) or {}).get("projectStatus") or [None])[-1]
        if sfmta_page_finished(pg, ctx.today) or AUDIT_DONE_PHASE.search(ps_last or ""):
            removed[PAGE_FINISHED].append(p["name"])
            continue
        if pre_plan_end(node):
            removed[PRE_PLAN].append("%s (%s)" % (p["name"], pre_plan_end(node)))
            continue
        if not p["phase"] and not pg.get("phase") and timeline_ended(pg, ctx.today) \
                and not page_activity(pg, ctx.today):
            removed[ENDED].append(p["name"])
            continue
        jd = ctx.page_dates.get(node) or {}
        jend = ((jd.get("fields") or {}).get("construction_end") or {}).get("iso")
        if not p["phase"] and not pg.get("phase") and not jd.get("projectStatus") and jend \
                and jend < ctx.today_s and (jd.get("latestStageDate") or "") <= ctx.today_s:
            removed[TEXT_ENDED].append(p["name"])
            continue
        if not_street_work(ctx, p["name"]):
            removed[NOT_STREET_F].append(p["name"])
            continue
        if not bp and not op:
            removed[NEITHER].append(p["name"])
            continue
        # Work with no bike or pedestrian scope counts only while its page
        # shows it is going on: the same activity test the sitemap pages below
        # get. A layer phase alone is not activity.
        if not bp and not page_activity(pg, ctx.today):
            removed[STALE].append(p["name"])
            continue
        pops = " and ".join(x for x, y in (("bike/ped", bp), ("on plan", op)) if y)
        cands.append((p, bp, op))
        if not reached(p["name"], node):
            why_bp = ("Bike" if p.get("bike") else ", ".join(sorted(set(p.get("types") or []) & BIKEPED_TYPES)) or "name") \
                if bp else "—"
            missing.append((p["name"], "phase not published" if p["phase"] is None else p["phase"], why_bp, pops,
                            plan_blocks.get(node, 0), "layer", p["page"]))

    # Sitemap pages the layer does not carry. They carry no geometry, so only the
    # bike or pedestrian population can be tested: a page counts when its own
    # text names bike or pedestrian street work and page_activity() finds a sign
    # of work in the last year or still to come.
    NO_WORDS = "sitemap page off the layer: no bike or pedestrian words in its text"
    NOT_STREET_P = "sitemap page off the layer: not street work by name"
    INACTIVE = "sitemap page off the layer: no sign of work in the last year or still to come"
    # The layer's TEXT_ENDED rule, for a page the layer does not carry: its
    # page gives no phase or Project Status, and the construction end Jev read
    # off its text has passed with no schedule row after today (Kirkham Street
    # Neckdown: "in March 2026, we installed other safety treatments").
    TEXT_ENDED_P = ("sitemap page off the layer: no phase or Project Status field on its page, and the construction "
                    "end its page's text gives has passed, with no schedule row on the page after today")
    PRE_PLAN_P = ("sitemap page off the layer: the construction end its page's text gives is before the plan's "
                  "adoption on %s, and no stage on its timeline is dated after that" % PLAN_ADOPTED)
    for k in (NO_WORDS, NOT_STREET_P, PRE_PLAN_P, TEXT_ENDED_P, INACTIVE):
        removed[k] = []
    by_url = {r.get("canonical"): r for r in ctx.sitemap_pages}
    off_layer_active, unread = [], []
    for url in ctx.sitemap["urls"]:
        r = by_url.get(url)
        if r is None:
            unread.append(url)
            continue
        if r.get("node") in layer_nodes or r.get("on_layer"):
            continue
        name = r.get("name") or r.get("title") or ""
        text = name + " " + (r.get("pageText") or "")
        if not SITEMAP_BIKEPED.search(text):
            removed[NO_WORDS].append(name)
            continue
        if not_street_work(ctx, name):
            removed[NOT_STREET_P].append(name)
            continue
        if r.get("node") and pre_plan_end(r["node"]):
            removed[PRE_PLAN_P].append("%s (%s)" % (name, pre_plan_end(r["node"])))
            continue
        jd = ctx.page_dates.get(str(r.get("node"))) or {}
        jend = ((jd.get("fields") or {}).get("construction_end") or {}).get("iso")
        if not r.get("phase") and not jd.get("projectStatus") and jend \
                and jend < ctx.today_s and (jd.get("latestStageDate") or "") <= ctx.today_s:
            removed[TEXT_ENDED_P].append(name)
            continue
        act = page_activity(r, ctx.today)
        if not act:
            removed[INACTIVE].append(name)
            continue
        off_layer_active.append(name)
        if not reached(name, r.get("node"), url):
            missing.append((name, "active: " + act, "page text", "bike/ped", "—", "sitemap only", url))

    # Every SFMTA row the list shows as current, read by the same rules as the
    # candidates above and nothing the pipeline decided: its layer phase, its
    # own page, and the coordination feed's own dates for a feed job it
    # carries. A row these rules call finished, ended or inactive is listed
    # as current work when the audit's reading says it is not (review,
    # 2026-09-29: six such rows were invisible to a completeness count).
    layer_by_node = {str(p["node"]): p for p in ctx.layer}
    by_slug = {(r.get("canonical") or "").rstrip("/").rsplit("/", 1)[-1]: r for r in ctx.sitemap_pages}
    feed = ctx.feed
    listed_read, not_current = 0, []
    for row in ctx.projects:
        rid = row["id"]
        if rid.startswith("sfmta:"):
            node = rid.split(":", 1)[1]
            lp, pg = layer_by_node.get(node) or {}, page_of.get(node) or {}
        elif rid.startswith("sfmta-page:"):
            pg = by_slug.get(rid.split(":", 1)[1]) or {}
            lp = layer_by_node.get(str(pg.get("node"))) or {} if pg.get("on_layer") else {}
        else:
            continue
        listed_read += 1
        why = None
        pg_node = node if rid.startswith("sfmta:") else pg.get("node")
        if lp.get("phase") in DONE_PHASES:
            why = FINISHED
        elif pg_node and pre_plan_end(pg_node):
            why = PRE_PLAN + " (%s)" % pre_plan_end(pg_node)
        elif sfmta_page_finished(pg, ctx.today):
            why = PAGE_FINISHED + ": " + sfmta_page_finished(pg, ctx.today)
        elif not lp.get("phase") and not pg.get("phase") and timeline_ended(pg, ctx.today) \
                and not page_activity(pg, ctx.today):
            why = ENDED + " (its last milestone is dated %d)" % timeline_ended(pg, ctx.today)
        elif lp and not bikeped(lp) and not page_activity(pg, ctx.today):
            why = STALE if node in plan_blocks else STALE_OFF_PLAN
        elif not lp and not page_activity(pg, ctx.today):
            why = INACTIVE
        if why is None:
            continue
        # A feed job the row carries that the feed itself still dates ahead
        # of today, and does not mark complete, is current work.
        active_feed = []
        for fid in sorted(feed_ids_of(row)) if feed else []:
            rows_ = feed["jobs"].get(fid) or []
            _, end = feed_job_dates(rows_)
            phase = next((r.get("project_phase") for r in rows_ if r.get("project_phase")), None)
            if end and end >= ctx.today_s and not re.search(r"complete", phase or "", re.I):
                active_feed.append("feed job %s (%s, ends %s)" % (fid, phase or "no phase", end))
        if active_feed:
            continue
        not_current.append((row["name"], lp.get("phase") or pg.get("phase") or "no phase", why,
                            row["links"][0]["url"] if row["links"] else "—"))

    n_bp = sum(1 for _, bp, _ in cands if bp)
    n_op = sum(1 for _, _, op in cands if op)
    n_both = sum(1 for _, bp, op in cands if bp and op)
    miss_bp = sum(1 for m in missing if "bike/ped" in m[3])
    miss_op = sum(1 for m in missing if "on plan" in m[3])
    res.facts.update(cands=len(cands), bikeped=n_bp, on_plan=n_op, both=n_both, off_layer=len(off_layer_active),
                     miss_bikeped=miss_bp, miss_on_plan=miss_op,
                     removed={k: len(v) for k, v in removed.items()})
    den = len(cands) + len(off_layer_active)
    res.measured = f"{len(missing)} missing ({miss_op} of {n_op} on plan blocks, {miss_bp} of " \
                   f"{n_bp + len(off_layer_active)} bike or pedestrian); {len(not_current)} of {listed_read} listed " \
                   f"SFMTA rows not current by the audit's own reading"
    res.denominator = f"{den} SFMTA street projects not marked finished: {len(cands)} on the layer ({n_bp} bike or " \
                      f"pedestrian, {n_op} on plan blocks, {n_both} both) and {len(off_layer_active)} active bike or " \
                      f"pedestrian pages the layer does not carry; {listed_read} SFMTA rows on the list"
    seeded = "(seed)" in ctx.sitemap["source"]
    res.line(f"SFMTA's sitemap lists {len(ctx.sitemap['urls'])} /projects/ pages ({ctx.sitemap['source']}, "
             f"{ctx.sitemap['fetched_on']}); its project layer carries {len(ctx.layer)}. "
             + (f"The sitemap here is seeded from the pages extract, so every page is in the extract by construction; "
                f"run --refresh to compare the extract with SFMTA's live sitemap."
                if seeded else f"{len(unread)} sitemap pages are not in the pages extract and were not read."))
    res.line(f"On plan blocks means the project's published line runs on a plan block by tools/projects/project-blocks.py's "
             f"test (line within 15 m (50 ft)). Missing: {miss_op} of the {n_op} active projects on plan blocks and "
             f"{miss_bp} of the {n_bp + len(off_layer_active)} bike or pedestrian ones; "
             f"{sum(1 for m in missing if m[1] == 'phase not published')} of the missing publish no phase.")
    res.line()
    res.table(["Project", "Phase", "Why bike/ped", "Population", "Plan blocks", "Source", "Page"],
              sorted(missing, key=lambda m: (m[5], "on plan" not in m[3], m[0] or "")))
    res.line("What each filter removed before counting:")
    res.line()
    res.table(["Filter", "Removed", "Names"], [(k, len(v), "; ".join(sorted(set(v)))) for k, v in removed.items()])
    res.line()
    res.line(f"Every SFMTA row on the list, read by the same filters and nothing the pipeline decided (its layer "
             f"phase, its own page, and the coordination feed's dates for a feed job it carries): {listed_read} read, "
             f"{len(not_current)} that the filters would not call current work.")
    res.line()
    res.table(["Listed SFMTA row", "Phase", "The audit's reading", "Page"], sorted(not_current))
    for m in missing:
        res.fail(m[0], f"{m[3]}, {m[1]}, not on the list ({m[6]})")
    for n, ph, why, url in sorted(not_current):
        res.fail(n, f"listed as current work, but {why} ({url})")
    res.verdict(len(missing) == 0 and not not_current)


SITEMAP_BIKEPED = re.compile(
    r"\bbik(e|es|eway|ing)\b|\bbicycl|slow street|quick.?build|neighborway|greenway|pedestrian|crosswalk|"
    r"sidewalk|traffic calming|speed hump|daylighting|bulb.?out", re.I)
# Not street work, on top of the pipeline's own SFMTA_NOT_BUILT (studies, plans
# without "Implementation", development agreements, signal contracts are kept
# here though: a signal is pedestrian infrastructure). Muni stations, fleets,
# budgets and programmes are not construction on a street.
NOT_STREET = re.compile(
    r"\bStudy\b|\bPlan\b(?!.*Implementation)|Treasure Island|Parkmerced|Candlestick|station accessibility|subway|"
    r"light rail|vehicle|fleet|\byard\b|budget|internship|project reports|project updates|permit program|pilot|"
    r"shuttle|roadmap|transportation 2050|equity strategy|charging|hov lanes|loading evaluation|bus program|"
    r"shared spaces|walk audit program|elevator|escalator|\bfacilit(y|ies)\b|"
    # Work inside a Muni tunnel or a bus terminal (Twin Peaks Tunnel
    # Improvements, Salesforce Transit Center); a tunnel's street safety
    # project (West Broadway Tunnel Safety Project) is street work.
    r"\btunnel\b(?! safety)|transit center", re.I)


def not_street_work(ctx, name):
    return bool(NOT_STREET.search(name or ""))


# The audit's own reading of an SFMTA page for "finished". It is written here
# rather than imported from tools/projects/coordination-projects.py so the check does
# not agree with the pipeline by construction.
AUDIT_DONE_PHASE = re.compile(r"^(?:completed?|substantially complete|project is substantially complete)\b", re.I)
AUDIT_DONE_TEXT = re.compile(r"\bproject\s+(?:is\s+now|was|has\s+been)\s+(?:successfully\s+|substantially\s+|fully\s+)?"
                             r"complete", re.I)
AUDIT_PART = re.compile(r"\b(?:phase|stage|segment|first|portion|part|survey|planning|design|outreach|evaluation|"
                        r"quick.?build)\b", re.I)


def sfmta_page_finished(r, today):
    """Why an SFMTA page says its project is finished, or None."""
    if AUDIT_DONE_PHASE.search(r.get("phase") or ""):
        return "phase field “%s”" % r["phase"]
    if r.get("phase"):
        return None  # a live phase on the page itself outranks its timeline and prose
    tl = r.get("timeline") or []
    years = [int(y) for t in tl for y in re.findall(r"\b(20\d\d)\b", t.get("when") or "")]
    if tl and all((t.get("status") or "").lower() == "completed" for t in tl) and years and max(years) < today.year:
        return "every milestone Completed, the last in %d" % max(years)
    for s in re.split(r"(?<=[.!?])\s+", " ".join((r.get("pageText") or "").split())):
        if AUDIT_DONE_TEXT.search(s) and not AUDIT_PART.search(s):
            return "its text: “%s”" % s[-160:]
    return None


def timeline_ended(r, today):
    """The last year an SFMTA page's timeline names, when every milestone is dated before last year; else None."""
    tl = r.get("timeline") or []
    years = [[int(y) for y in re.findall(r"\b(20\d\d)\b", t.get("when") or "")] for t in tl]
    if not tl or not all(years):
        return None
    last = max(max(y) for y in years)
    return last if last < today.year - 1 else None


def page_activity(r, today):
    """Why an SFMTA page reads as active, or None: a timeline stage still to come, a dated update or meeting in the last year."""
    # A milestone dated this year or later is work in the last year or still
    # to come, whatever its status says: sfmta.com marks some future stages
    # Completed (the J Church and M Ocean View page's "Construction Continues,
    # Summer 2026 - Winter 2028", District 2 Safety Study's "Quick-Build
    # Implementation, 2027"; read 2026-09-29).
    for t in r.get("timeline") or []:
        years = [int(y) for y in re.findall(r"\b(20\d\d)\b", t.get("when") or "")]
        if years and max(years) >= today.year:
            return "timeline “%s: %s”" % (t.get("what"), t.get("when"))
    cutoff = (today - dt.timedelta(days=365)).isoformat()
    for m in r.get("meetings") or []:
        if (m.get("date") or "") >= cutoff:
            return "meeting %s" % m["date"]
    text = " ".join([r.get("pageText") or ""] + [u.get("title") or "" for u in r.get("updates") or []])
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+(20\d\d)\b[^.]{0,12}\bupdate", text, re.I):
        ym = "%s-%02d" % (m.group(2), MONTHS.index(m.group(1).lower()) + 1)
        if ym >= cutoff[:7]:
            return "“%s”" % m.group(0)
    # A sentence of the page's own prose that dates work to a month or season:
    # a month in the last year, or any month, season or early/mid/late of this
    # year or later ("Fall 2026: SFMTA Board Legislation", "in March 2026, we
    # installed", "will complete its detailed design phase in Early 2027").
    # A bare year is not read: a plan's horizon or a crash-data range is not
    # work. Pages with no timeline block carry their schedule only here.
    for s in re.split(r"(?<=[.!?])\s+", " ".join((r.get("pageText") or "").split())):
        for m in re.finditer(r"\b(?:(" + "|".join(MONTHS) + r")|winter|spring|summer|fall|autumn|early|mid|late)"
                             r"[- ]+(20\d\d)\b", s, re.I):
            y = int(m.group(2))
            ym = "%d-%02d" % (y, MONTHS.index(m.group(1).lower()) + 1) if m.group(1) else None
            if y >= today.year or (ym and ym >= cutoff[:7]):
                return "its text: “%s”" % s[:160]
    return None


def a1_on_plan(ctx):
    """{layer node: plan blocks its published line runs on}, by project-blocks.py's own test; only nodes on at least one."""
    def read():
        try:
            pb = load_module("project_blocks", "tools/projects/project-blocks.py")
            from streetindex import BlockIndex
            grid = ctx.once("grid", lambda: pb.Grid(BlockIndex()))
        except Exception as e:  # noqa: BLE001
            print("  (on-plan test skipped: %s)" % e)
            return {}
        plan = set(ctx.plan)
        held = collections.defaultdict(set)
        for f in ctx.layer_geo:
            if f.get("geometry"):
                cnns, _ = pb.blocks_for(f["geometry"], grid)
                held[str(f["properties"]["node"])] |= set(cnns) & plan
        return {n: len(c) for n, c in held.items() if c}
    return ctx.once("a1_on_plan", read)


# Street work by name, beyond coordination-projects.py's work kinds: a project
# named for a street, an interchange or a sidewalk digs up a street; a health
# centre, a call centre or a rock slope does not.
STREETY = re.compile(r"\b(street|st|avenue|ave|boulevard|blvd|drive|way|road|interchange|alley|plaza|sidewalk|"
                     r"curb ramps?|streetscape|bridge)\b", re.I)


def dept_list_completeness(ctx, res, records, dept, label, source):
    """A1 for a department that publishes a project list with blocks: in-progress projects on plan blocks, not listed."""
    plan = set(ctx.plan)
    listed_plan = set()
    for p in ctx.projects:
        listed_plan |= set(p["planCnns"])
    active = [r for r in records if (r.get("status") or "").lower() in ("in progress", "active", "under construction", "construction")]
    # A page's blocks are read from its own Location field: the corridor
    # between the limits it names, or the corridor alone when it names none
    # (lib/pw_extent.py). The extract's `cnns` holds every block of
    # every street the field names, cross streets included, which put
    # Beale Street Improvement Project on every block of Market and Folsom.
    if any(r.get("location") for r in active):
        from lib.pw_extent import Extents
        ext = ctx.once("pw_extents", Extents)
        active = [dict(r, cnns=sorted(ext.of(r["location"]).cnns)) if r.get("location") else r for r in active]
    # Every in-progress page whose blocks touch the plan counts, whatever its
    # name says: a joint project named "Transit U Improvement Project" digs up
    # the same blocks as one named for a street. The street-word test is only
    # printed beside each row.
    # Bryan, 2026-09-29: a project done before the plan's adoption is off the
    # list, whatever status its page still shows (Masonic: "In progress",
    # "Construction phase: July 2016 to Spring 2018"). The end is the one the
    # page's own text gives (out/dept-page-dates/dates.json).
    def page_end(r):
        f = ((ctx.dept_page_dates.get(r.get("url") or "") or {}).get("fields") or {}).get("construction_end") or {}
        return f.get("iso")
    # A page the list carries anyway (a feed job dates the same work later)
    # stays in the count: the rule takes projects off, it does not excuse rows.
    linked_pages = {l["url"] for p in ctx.projects for l in p["links"] if l.get("kind") != "program"}
    pre_plan = [r for r in active if page_end(r) and page_end(r) < PLAN_ADOPTED
                and is_listed_name(ctx, r["name"]) is None and r.get("url") not in linked_pages]
    active = [r for r in active if r not in pre_plan]
    no_blocks = [r for r in active if not r.get("cnns")]
    with_blocks = [r for r in active if r.get("cnns")]
    off_plan = [r for r in with_blocks if not set(r["cnns"]) & plan]
    on_plan = [r for r in with_blocks if set(r["cnns"]) & plan]
    streety = lambda name: "yes" if (ctx.cp.work_kind(name, dept) or STREETY.search(name)) else "no"
    missing = []
    # A listed row that links the department's page for the project is that
    # project under the feed's name ("Chinatown Public Health Center" links
    # "... Renovation Project").
    linked_pages = {l["url"] for p in ctx.projects for l in p["links"] if l.get("kind") != "program"}
    # Out of scope: a project About the data names as not street work (a
    # building, a plant, equipment), which is not named for street work and
    # whose own page this check's explanations record as such. All three, so a
    # street job cannot leave the count by being named on About alone. About
    # is read as rendered; with --no-build, as the names its template renders
    # from site/data/coordination.json's notStreetWork.
    # The name must be one of those rows exactly, not a substring of the page.
    nsw = {j["name"].lower() for j in ctx.coord.get("notStreetWork") or [] if j.get("planCnns")}
    rendered = (ctx.page_text("transportation/bike/about/index.html") or "").lower()
    about = {n for n in nsw if not rendered or n in rendered}
    out_of_scope = []
    for r in on_plan:
        pb = set(r["cnns"]) & plan
        uncovered = pb - listed_plan
        if is_listed_name(ctx, r["name"]) is None and r.get("url") not in linked_pages:
            why = explained(res.cid, r["name"])
            if why and streety(r["name"]) == "no" and r["name"].lower() in about:
                out_of_scope.append((r["name"], len(pb), why))
                continue
            missing.append((r["name"], len(pb), len(uncovered), streety(r["name"]), why, r.get("url")))
    res.measured = len(missing)
    in_scope = len(on_plan) - len(out_of_scope)
    res.denominator = (f"{in_scope} in-progress {label} projects on plan blocks"
                       + (f" ({len(out_of_scope)} more named on About the data as not street work)" if out_of_scope else ""))
    res.facts.update(published=len(records), active=len(active), no_blocks=len(no_blocks), off_plan=len(off_plan),
                     on_plan=len(on_plan), missing=len(missing), out_of_scope=len(out_of_scope),
                     not_street_on_plan=sum(1 for r in on_plan if streety(r["name"]) == "no"))
    share = len(missing) / in_scope if in_scope else 0
    unexplained = [m for m in missing if not m[4]]
    res.line(f"{label} publishes {len(records)} projects ({source}); {len(active)} are in progress, {len(with_blocks)} "
             f"of those carry block data and {len(on_plan)} touch plan blocks. Every one of the {len(on_plan)} counts, "
             f"whatever its name, unless it is out of scope as below; {res.facts['not_street_on_plan']} of them are not "
             f"named for street work (coordination-projects.py's work kinds, or a street, interchange, sidewalk or "
             f"bridge in the name).")
    res.line(f"A project counts as missing when no listed project has the same or nearly the same name or links its page. The blocks "
             f"column says how many of its plan blocks no listed project covers. Missing: {len(missing)} "
             f"({pct(len(missing), in_scope)} of the {in_scope} not out of scope); unexplained: {len(unexplained)}. Out of scope: "
             f"{len(out_of_scope)}, each not named for street work, named on About the data as not street work, and "
             f"explained below from its own page.")
    res.line()
    res.table(["Project", "Plan blocks", "Not covered by a listed project", "Named for street work", "Explanation", "Page"],
              sorted(missing, key=lambda m: -m[2]))
    if out_of_scope:
        res.line("Out of scope:")
        res.line()
        res.table(["Project", "Plan blocks", "Explanation"], sorted(out_of_scope))
    res.line("What was left out before counting:")
    res.line()
    res.table(["Filter", "Removed", "Names"], [
        ("not in progress on the department's page", len(records) - len(active) - len(pre_plan), "(every Completed page)"),
        ("in progress and not listed, but its page's text gives a construction end before the plan's adoption on %s"
         % PLAN_ADOPTED,
         len(pre_plan), "; ".join(sorted("%s (%s)" % (r["name"], page_end(r)) for r in pre_plan))),
        ("in progress, no block data, so it cannot be placed", len(no_blocks), "; ".join(sorted(r["name"] for r in no_blocks))),
        ("in progress, blocks off the plan", len(off_plan), "; ".join(sorted(r["name"] for r in off_plan))),
    ])
    for m in missing:
        if not m[4]:
            res.fail(m[0], f"{m[1]} plan blocks, {m[2]} not covered by any listed project; no row names it and no explanation ({m[5]})")
    if share > 0.05 and not res.failing:
        res.fail(f"{len(missing)} of {in_scope} missing", "over 5% although every miss is explained")
    res.verdict(share <= 0.05 and not unexplained)


@check("A1-PW", "Completeness: Public Works",
       "No more than 5% of active on-plan projects missing, and every miss explained.")
def a1_pw(ctx, res):
    dept_list_completeness(ctx, res, ctx.dpw, "Public Works", "Public Works", "sfpublicworks.org/projects, data/extract/dpw-projects/projects.json")


@check("A1-SFPUC", "Completeness: SFPUC",
       "No more than 5% of active on-plan projects missing, and every miss explained.")
def a1_sfpuc(ctx, res):
    paths = sorted(glob.glob(os.path.join(ROOT, "data", "extract", "sfpuc-projects", "*.json")))
    if not paths:
        res.status = "NOT MEASURED"
        res.line("No SFPUC project list is read: data/extract/sfpuc-projects/ does not exist. The coordination feed is "
                 f"the only SFPUC source ({sum(1 for p in ctx.projects if p['department'] == 'SFPUC')} listed rows).")
        return
    records = [r for path in paths for r in json.load(open(path)).get("records", [])]
    dept_list_completeness(ctx, res, records, "SFPUC", "SFPUC", os.path.relpath(paths[0], ROOT))


@check("A2", "Other agencies",
       "Each active other-agency job on plan blocks is either listed or named on About the data as out of scope.")
def a2(ctx, res):
    if ctx.feed is None:
        res.status = "NOT MEASURED"
        res.line("No cached pull of the coordination feed (btxj-k9uh) in data/socrata-cache/. Symlink the cache into "
                 "this checkout, or run with --refresh to read the feed live.")
        return
    plan = set(ctx.plan)
    listed = listed_ids(ctx)
    about = (ctx.page_text("transportation/bike/about/index.html") or
             open(os.path.join(ROOT, "site/content/transportation-about.md"), encoding="utf-8").read()).lower()
    rows, all_other = [], 0
    for pid, jrows in ctx.feed["jobs"].items():
        agency = jrows[0].get("agency_name") or ""
        if ctx.cp.department(agency):
            continue
        all_other += 1
        _, end = feed_job_dates(jrows)
        if end and end < ctx.today_s:
            continue
        cnns = set(ctx.record.get("dotmaps:" + pid, {}).get("cnns") or [])
        blocks = cnns & plan
        if not blocks:
            continue
        name = jrows[0].get("name") or ""
        named = name.lower() in about
        why = "listed" if "dotmaps:" + pid in listed else "named on About" if named else explained("A2", name)
        rows.append((agency, name, len(blocks), why))
    bad = [r for r in rows if not r[3]]
    res.measured = len(bad)
    res.denominator = f"{len(rows)} active other-agency jobs on plan blocks ({all_other} other-agency jobs in the feed)"
    built = ctx.coord["feed"].get("queried")
    res.line(f"Coordination feed queried {ctx.feed['fetched_on']}"
             + (", the same pull site/data/coordination.json was built from." if str(ctx.feed["fetched_on"])[:10] == built
                else f"; site/data/coordination.json was built from the {built} pull, so a job listed since or dropped "
                     f"since may read wrongly here.")
             + " A job is active when its latest end date is today or later, or it has none.")
    for r in bad:
        res.fail(r[1], f"{r[0]}, {r[2]} plan blocks: not listed, not named on About, not explained")
    res.line()
    res.table(["Agency", "Job", "Plan blocks", "Listed, named or explained"], sorted(rows, key=lambda r: -r[2]))
    res.verdict(not bad)


@check("A3", "Duplicates",
       "Zero same-name rows. Every high-overlap pair is either merged or shown on the page as related. (The measure's "
       "pairs are Jaccard ≥ 0.5 on blocks, and two sources' rows for the same project that were not merged.)")
def a3(ctx, res):
    P = ctx.projects
    names = collections.Counter(re.sub(r"\s+", " ", p["name"].strip().lower()) for p in P)
    same = {n: c for n, c in names.items() if c > 1}
    related = {p["id"]: {r["id"] for r in p.get("related") or []} for p in P}
    blocks = {p["id"]: all_cnns(ctx, p) for p in P}
    pairs = []
    for i, a in enumerate(P):
        for b in P[i + 1:]:
            A, B = blocks[a["id"]], blocks[b["id"]]
            if not A or not B:
                continue
            j = len(A & B) / len(A | B)
            if j >= 0.5:
                shown = b["id"] in related[a["id"]] or a["id"] in related[b["id"]]
                pairs.append((a["name"], b["name"], "%.2f" % j, "shown as related" if shown else None))
    # Two sources, one project: a listed feed row and an SFMTA layer project of nearly the same name.
    # A listed feed row was not merged by construction (a merged one is not a row
    # of its own), so any SFMTA project of nearly the same name is a pair left apart.
    cross = []
    for a in P:
        if a["source"] != "dotmaps":
            continue
        for s in ctx.layer:
            if not same_name(a["name"], s["name"]):
                continue
            sid = "sfmta:%s" % s["node"]
            shown = sid in related[a["id"]] or a["id"] in related.get(sid, set())
            cross.append((a["name"], s["name"], "listed" if sid in related else "not listed",
                          "shown as related" if shown else None))
    bad_pairs = [p for p in pairs if not p[3]]
    bad_cross = [c for c in cross if not c[3]]
    extra = sum(c - 1 for c in same.values())
    res.measured = extra + len(bad_pairs) + len(bad_cross)
    res.denominator = f"{len(P)} listed rows: {extra} extra same-name rows, {len(bad_pairs)} of {len(pairs)} " \
                      f"high-overlap pairs not shown as related, {len(bad_cross)} of {len(cross)} cross-source pairs not merged or related"
    res.line("Blocks are every block a row holds (its record's blocks plus a merged feed job's), not only plan blocks.")
    res.line()
    if same:
        res.table(["Name listed more than once", "Rows"], sorted(same.items()))
    res.table(["Row", "Row", "Block overlap (Jaccard)", "On the page"], sorted(pairs, key=lambda p: p[2], reverse=True))
    res.table(["Feed row", "SFMTA layer project", "SFMTA project on the list", "On the page"], cross)
    for n, c in sorted(same.items()):
        res.fail(n, f"listed {c} times")
    for a, b, j, _ in bad_pairs:
        res.fail(f"{a} / {b}", f"block overlap {j}, not merged or shown as related")
    for a, b, l, _ in bad_cross:
        res.fail(f"{a} / {b}", f"feed row and SFMTA layer project ({l}), not merged or shown as related")
    res.verdict(res.measured == 0)


# ===========================================================================
# B. Project details

# Public Works and SFPUC give a job a page once construction starts, and none
# before (tools/projects/department-project-pages.py searched their sites, bid portals
# and project lists). Bryan, 2026-09-29: B1's 90% counts
# only jobs a department publishes pages for, and every other job shows the
# closest official source. SFMTA publishes pages for projects in every phase.
PAGE_PHASES = {"Public Works": re.compile(r"construction|in progress|implementation", re.I),
               "SFPUC": re.compile(r"construction", re.I)}


@check("B1", "Link to the department's own page",
       "Over 90% of the listed projects a department publishes pages for, overall and within each department. That "
       "is every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. Every "
       "other job shows the closest official source, and About the data says why.")
def b1(ctx, res):
    # Bryan, 2026-09-30 ("Log as issues"): the jobs with no
    # page and no closest official source anywhere searched are logged as a
    # top issue on About the data, and B1 passes on that issue while it prints
    # their count. Every other row still needs the 90% lines.
    ls = link_status()
    # A link counts only when the link-status cache holds a 200 for it: a
    # link the cache never checked is not taken as live (review, 2026-09-29:
    # with no cache every department link was taken as live).
    status = (ls or {}).get("status", {})
    # listed, counted, counted with a page, counted with no page, set aside
    # with a closest source, set aside with none
    by = collections.defaultdict(lambda: {"listed": 0, "counted": 0, "ok": 0, "missing": [], "closest": 0, "bare": [],
                                          "closest_kinds": collections.Counter()})
    sitemap_names = [r.get("name") or r.get("title") for r in ctx.sitemap_pages]
    dpw_names = [r["name"] for r in ctx.dpw]
    broken, unshown = [], []
    for p in ctx.projects:
        # A "program" link is a programme page or the paving map, offered as
        # the closest official source when the department publishes no page
        # for the job. It is shown, and it does not count as the job's page.
        links = [l["url"] for l in p["links"] if dept_link(l["url"]) and l.get("kind") != "program"]
        closest_all = [l for l in p["links"] if l.get("kind") == "program"]
        ok = [u for u in links if link_live(ls, u)]
        broken += [(p["name"], u, status.get(u, "not checked"), browser_note(ls, u)) for u in links if u not in ok]
        # A closest source counts when it answers and the rendered page
        # carries its address (read from the page, not the list's data).
        page_html = ctx.project_detail_html(p["slug"])
        closest = []
        for l in closest_all:
            live = link_live(ls, l["url"])
            shown = page_html is not None and ('href="%s"' % l["url"]) in page_html
            if live and shown:
                closest.append(l)
            else:
                unshown.append((p["name"], l["url"], "not on the rendered page" if not shown else
                                "returned %s" % status.get(l["url"], "not checked")))
        dept = p["department"]
        d = by[dept]
        d["listed"] += 1
        phases = PAGE_PHASES.get(dept)
        if ok or phases is None or phases.search(p["phase"] or ""):
            d["counted"] += 1
            if ok:
                d["ok"] += 1
            else:
                pool = sitemap_names if dept == "SFMTA" else dpw_names if dept == "Public Works" else []
                near = next((n for n in pool if n and same_name(n, p["name"])), None)
                d["missing"].append((p["name"], near, bool(closest)))
        elif closest:
            d["closest"] += 1
            d["closest_kinds"][closest[0].get("label", "").split("closest official source: ")[-1]] += 1
        else:
            d["bare"].append((p["name"], p["phase"]))
    tot_ok = sum(v["ok"] for v in by.values())
    tot = sum(v["counted"] for v in by.values())
    bare = sum(len(v["bare"]) for v in by.values())
    res.measured = tot_ok
    res.denominator = f"{tot} jobs a department publishes pages for, of {sum(v['listed'] for v in by.values())} listed; " \
                      f"{bare} of the rest show no closest official source"
    res.line("A department page is the job's own page or its contract's bid page on sfmta.com (/node or /projects), "
             "sfpublicworks.org, sfpuc.gov, Public Works' bid portal or SFPUC Bids On Line. A DataSF row, a programme "
             "page and the Public Works paving map are not one; the last two are shown as the closest official source. "
             "Counted: every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. "
             + (f"Link status from data/audit/cache/link-status.json ({ls['fetched_on']}"
                + (f", plus {len(ls['added'])} new link(s) read since, the latest on {max(ls['added'].values())}"
                   if ls.get("added") else "") + "); a link that did not return 200, "
                f"or that the cache never checked, does not count, unless a browser read of it (a browser's user "
                f"agent, GET) returned 200, which is evidence the site blocks robots rather than the page being "
                f"gone. A closest official source counts only when it answers and the rendered project page "
                f"carries its address."
                if ls else "No link-status cache, so no link can be counted as live: run --refresh to check them."))
    res.line()
    res.table(["Department", "Listed", "Counted", "With a department page", "Share of counted",
               "Not counted; closest source shown", "Not counted; no closest source",
               "Counted, no page, a page under nearly the same name"],
              [(d, v["listed"], v["counted"], v["ok"], pct(v["ok"], v["counted"]), v["closest"], len(v["bare"]),
                sum(1 for _, n, _ in v["missing"] if n)) for d, v in sorted(by.items())])
    try:
        pub = load("out/department-pages/matches.json").get("published") or {}
    except FileNotFoundError:
        pub = {}
    if pub:
        res.line()
        res.line("What each department publishes, from tools/projects/department-project-pages.py:")
        for dept, notes in sorted(pub.items()):
            for k, v in sorted(notes.items()):
                res.line(f"- {dept}, {k}: {v}")
    kinds = [(d, k, n) for d, v in sorted(by.items()) for k, n in sorted(v["closest_kinds"].items())]
    if kinds:
        res.line()
        res.table(["Department", "Closest official source shown", "Jobs"], kinds)
    bare_rows = [(d, n, ph or "not published") for d, v in sorted(by.items()) for n, ph in v["bare"]]
    if bare_rows:
        res.table(["Department", "Job with no page and no closest official source", "Phase"], bare_rows)
    if unshown:
        res.table(["Project", "Closest official source", "Not counted because"], unshown)
    rest = [(d, n, near) for d, v in sorted(by.items()) for n, near, _ in v["missing"] if near]
    if rest:
        res.table(["Department", "Counted row with no department link", "Department page under nearly the same name"], rest)
    if broken:
        res.table(["Project", "Department link", "Status", "Read as a browser"], broken)
    for d, v in sorted(by.items()):
        for n, near, cl in v["missing"]:
            res.fail(n, f"{d}: no department page linked"
                     + ("; closest official source shown" if cl else "")
                     + (f"; the department publishes “{near}”" if near else ""))
        for n, ph in v["bare"]:
            res.fail(n, f"{d}, phase {ph or 'not published'}: no page published and no closest official source shown")
    for n, u, s, b in broken:
        res.fail(n, f"department link {u} returned {s}; as a browser, {b}")
    # Bryan cut the top issues to six on 2026-09-30 (95fb589, "six issues, one
    # sentence each"), which dropped the item that logged these jobs. They are
    # now said where the page explains its links: the "Dates and links"
    # paragraph of the method, with their count. Either place counts.
    no_source = lambda t: ("no department page, program page or paving map" in t
                           or re.search(r"could(n['’]t| not) find any official page", t))
    issue = logged_issue(ctx, no_source, count=bare) if bare else None
    if bare and not (issue and issue[2]):
        issue = about_note(ctx, no_source, count=bare) or issue
    if bare:
        res.line()
        if issue and issue[2]:
            res.line(f"The {bare} jobs with no page and no closest official source are said on About the data "
                     f"({issue[0]}: “{issue[1]}”), per Bryan's decision of 2026-09-30 to log them there.")
        elif issue:
            res.line(f"About the data names the jobs with no official source ({issue[0]}), but "
                     + ("the site was not built, so its count was not read." if issue[2] is None else
                        f"it does not print their count, {bare}."))
        elif not ctx.dist:
            res.line("The site was not built, so About the data's method was not read for the jobs with no official "
                     "source.")
        else:
            res.line("About the data says nothing of the jobs with no official source.")
    ok = (tot and tot_ok / tot > 0.9 and (bare == 0 or bool(issue and issue[2]))
          and all(v["ok"] / v["counted"] > 0.9 for v in by.values() if v["counted"]))
    res.facts.update(b1_no_source=bare, b1_issue=issue[0] if issue else None)
    if ls is None:
        res.status = "NOT MEASURED"
        return
    res.verdict(bool(ok))


NOT_PUBLISHED = re.compile(r"not published|none published|no [a-z ]{0,20}published|unpublished", re.I)


@check("B2", "Key fields present",
       "Start and phase on 95% of rows. Every missing value shows as “not published” on the page, never as a blank.")
def b2(ctx, res):
    # Bryan, 2026-09-30 ("Log as issues"): below the 95% line,
    # the missing start dates are logged as a top issue on About the data and
    # the start line passes on that issue while it prints their count. Phase
    # keeps its line, and every blank value still fails on its own.
    fields = {
        "name": lambda p: p["name"], "department": lambda p: p["department"], "phase": lambda p: p["phase"],
        "start": lambda p: p["start"], "end": lambda p: p["end"], "streets": lambda p: p["streets"],
        "geometry": lambda p: p["geometry"], "scope": lambda p: (p["scopeText"] or "").strip(),
    }
    depts = sorted({p["department"] for p in ctx.projects})
    miss = {f: collections.Counter() for f in fields}
    blank = collections.Counter()
    blank_rows = []
    for p in ctx.projects:
        detail = ctx.project_detail(p["slug"])
        for f, get in fields.items():
            if not get(p):
                miss[f][p["department"]] += 1
                if f in ("start", "end", "scope") and detail is not None:
                    shown = {"start": re.search(r"no start date published|start[^.]{0,20}not published", detail, re.I),
                             "end": re.search(r"no end date published|end[^.]{0,20}not published|finish[^.]{0,20}not published", detail, re.I),
                             "scope": re.search(r"Scope \S? ?None published|Scope[^.]{0,10}not published", detail, re.I)}[f]
                    if not shown:
                        blank[f] += 1
                        blank_rows.append((p["name"], f))
    n = len(ctx.projects)
    coarse = sum(1 for p in ctx.projects if p["start"] and len(p["start"]) < 10)
    start_ok = (n - sum(miss["start"].values())) / n
    phase_ok = (n - sum(miss["phase"].values())) / n
    res.measured = f"start {pct(n - sum(miss['start'].values()), n)}, phase {pct(n - sum(miss['phase'].values()), n)}; " \
                   f"{sum(blank.values())} missing values not shown as not published"
    res.denominator = n
    res.table(["Field"] + depts + ["All"],
              [(f,) + tuple(miss[f][d] for d in depts) + (sum(miss[f].values()),) for f in fields])
    res.line(f"Start given only as a month, season or year: {coarse}.")
    if ctx.dist is None:
        res.line("The site was not built, so whether a missing value shows as “not published” was not checked.")
    else:
        res.line(f"Missing values the project page does not show as “not published”: start {blank['start']}, "
                 f"end {blank['end']}, scope {blank['scope']}.")
        res.table(["Project", "Field shown blank"], blank_rows, limit=30)
    for name, f in blank_rows:
        res.fail(name, f"no {f} published, and the page does not say so")
    no_start = sum(miss["start"].values())
    issue = logged_issue(ctx, lambda t: "no published start date" in t, count=no_start) if start_ok < 0.95 else None
    start_logged = bool(issue and issue[2])
    if start_ok < 0.95:
        res.line()
        if start_logged:
            res.line(f"Start is under the 95% line. The {no_start} rows with no start are logged as a top issue on "
                     f"About the data ({issue[0]}: “{issue[1]}”), per Bryan's decision of 2026-09-30 to log them as "
                     f"issues.")
        elif issue:
            res.line(f"Start is under the 95% line. About the data's top issues log it ({issue[0]}), but "
                     + ("the site was not built, so its count was not read." if issue[2] is None else
                        f"it does not print the count, {no_start}."))
        else:
            res.line("Start is under the 95% line, and About the data's top issues carry no item for it.")
        res.fail("start", f"present on {pct(n - no_start, n)} of rows, under 95%"
                 + (f"; logged as {issue[0]}" if start_logged else ""))
    if phase_ok < 0.95:
        res.fail("phase", f"present on {pct(n - sum(miss['phase'].values()), n)} of rows, under 95%")
    res.facts.update(b2_no_start=no_start, b2_issue=issue[0] if issue else None)
    ok = (start_ok >= 0.95 or start_logged) and phase_ok >= 0.95 and ctx.dist is not None and not blank
    res.verdict(ok)


def stage(phase):
    """A phase in one vocabulary: done, construction, design, planning, or unknown."""
    p = (phase or "").lower()
    if not p:
        return "unknown"
    if p in ("completed", "project evaluation") or "complete" in p:
        return "done"
    if "construct" in p or p == "current" or "implement" in p or "progress" in p:
        return "construction"
    if "design" in p or "legislat" in p:
        return "design"
    if "plan" in p:
        return "planning"
    return p


@check("B3", "Status agrees across sources",
       "Every disagreement is printed with both values.")
def b3(ctx, res):
    rows, unplaced = [], []
    for s in ctx.layer:
        for d in ctx.dpw:
            if not same_name(s["name"], d["name"]):
                continue
            a = "done" if stage(s["phase"]) == "done" else "unknown" if s["phase"] is None else "active"
            b = "done" if (d.get("status") or "").lower() == "completed" else "active"
            if a == b:
                rows.append((s["name"], d["name"], s["phase"], d.get("status"), "agree"))
                continue
            listed = [p for p in ctx.projects if p["id"] == "sfmta:%s" % s["node"] or same_name(p["name"], s["name"])
                      or same_name(p["name"], d["name"])]
            # Shown means the page that carries the job prints Public Works'
            # status and SFMTA's phase: a listed project's page, which also
            # links Public Works' page, or the notice page an address keeps
            # once its project leaves the list (read from the built site).
            both = lambda t: (d.get("status") or "").lower() in t.lower() and (s["phase"] or "no phase").lower() in t.lower()
            shown, carried = None, bool(listed)
            for p in listed:
                t = ctx.project_detail(p["slug"]) or ""
                links = {l["url"] for l in p["links"]}
                if d.get("url") in links and both(t):
                    shown = "both shown"
            for slug, (h1, t) in sorted(ctx.notice_pages().items()):
                if same_name(h1, s["name"]) or same_name(h1, d["name"]):
                    carried = True
                    if both(t) and not shown:
                        shown = "both shown on its notice page"
            # A job on neither list nor notice page may still be shown as a
            # neighbour ("other projects on these blocks") on a listed page;
            # there the one line naming it must print both values.
            for p in ctx.projects:
                if not any(same_name(r["name"], d["name"]) for r in p.get("related") or []):
                    continue
                carried = True
                h = ctx.project_detail_html(p["slug"]) or ""
                for li in re.findall(r"<li>.*?</li>", h, re.S):
                    if same_name(visible_text(re.sub(r'<span class="small">.*', "", li, flags=re.S)), d["name"]) \
                            and both(visible_text(li)) and not shown:
                        shown = "both shown where it is a neighbour on %s's page" % p["name"]
            if not shown and not carried:
                unplaced.append(s["name"])
            rows.append((s["name"], d["name"], s["phase"] or "no phase", d.get("status"), shown))
    merged = [(p["name"], p["phase"], p["feedPhase"]) for p in ctx.projects if p.get("feedPhase")]
    disagree = [m for m in merged if stage(m[1]) != stage(m[2])]

    def both_shown(m):
        # Shown means the project page prints SFMTA's phase and the feed's.
        p = next(x for x in ctx.projects if x["name"] == m[0] and x.get("feedPhase") == m[2])
        t = (ctx.project_detail(p["slug"]) or "").lower()
        return (m[1] or "no phase").lower() in t and m[2].lower() in t and "coordination feed" in t
    merged_diff = [m for m in disagree if not both_shown(m)]
    bad = [r for r in rows if r[4] is None]
    # Two populations with two denominators, printed apart so neither reads as a rate of the other.
    res.measured = f"{len(bad)} of {len(rows)} SFMTA/Public Works pairs disagree unshown; " \
                   f"{len(merged_diff)} of {len(merged)} merged rows disagree unshown ({len(disagree)} disagree)"
    res.denominator = f"{len(rows)} projects both SFMTA's layer and Public Works' pages publish, and {len(merged)} merged SFMTA/feed rows"
    res.facts.update(pairs=len(rows), pairs_bad=len(bad), merged=len(merged), merged_bad=len(merged_diff))
    for r in bad:
        res.fail(r[0], f"SFMTA phase {r[2]}, Public Works status {r[3]}; "
                       + ("no page on the site carries it, listed or notice" if r[0] in unplaced
                          else "the page does not show both"))
    for m in merged_diff:
        res.fail(m[0], f"merged row: SFMTA phase {m[1]}, feed phase {m[2]}; the page shows one")
    res.line("A layer phase of Completed or Project Evaluation is done, none is unknown, any other is active; "
             "a Public Works page status of Completed is done, any other is active. A disagreement counts as shown "
             "when the page that carries the job prints both values: its listed project page, the notice page "
             "its address keeps after it leaves the list, or, for a job on neither, the line naming it among another "
             "listed project's neighbours, all read from the built site.")
    if unplaced:
        res.line(f"Carried by no page on the site, listed or notice: {'; '.join(sorted(unplaced))}.")
    res.line()
    res.table(["SFMTA layer", "Public Works page", "SFMTA phase", "Public Works status", "Result"],
              sorted(rows, key=lambda r: r[4] or ""))
    res.table(["Merged row", "SFMTA phase", "Feed phase", "Same stage"],
              [(m[0], m[1], m[2], "yes" if m not in disagree else "no, both shown" if m not in merged_diff else "no, and the page shows one") for m in merged])
    res.verdict(not bad and not merged_diff)


# ===========================================================================
# C. Discussion record

C1_BODIES = ["SFMTA engineering hearings", "SFMTA Board", "Board of Supervisors", "SFPUC Commission",
             "Public Works Commission", "SFCTA Board"]


def c1_builtin(ctx):
    out = {}
    h = load("data/extract/sfmta-hearings/since-2010-01-01.json")["records"][0]
    missing = h["unreachable"] + h["unparsed"] + h["noresults"]
    items = sum(x.get("itemCount") or 0 for x in h["all"])
    out["SFMTA engineering hearings"] = {
        "first": min(x["date"] for x in h["all"]), "last": max(x["date"] for x in h["all"]),
        "meetings": len(h["all"]), "missing": missing,
        "fullTitles": False, "titlesNote": f"{len(h['matches'])} bike-matched items of {items} kept",
        "script": "tools/meetings/sfmta-hearings.py"}
    b = load("data/extract/sfmta-board/since-2019-01-01.json")["records"][0]
    items = sum(a.get("itemCount") or 0 for a in b["agendas"])
    out["SFMTA Board"] = {
        "first": min(a["date"] for a in b["agendas"]), "last": max(a["date"] for a in b["agendas"]),
        "meetings": len(b["agendas"]), "missing": b["failed"] + b["unparsed"],
        "fullTitles": False, "titlesNote": f"{len(b['matches'])} bike-keyword items of {items} kept; "
                                           f"minutes index from {min(b['minutesIndex'])}",
        "script": "tools/meetings/sfmta-board-records.py"}
    s = load("out/bos-records/street-items.json")
    meets = sorted(glob.glob(os.path.join(ROOT, "data", "legistar", "meetings", "*.json")))
    mdates = []
    for m in meets:
        try:
            d = iso_date(json.load(open(m))["meeting"]["date"])
            if d:
                mdates.append(d)
        except Exception:  # noqa: BLE001
            pass
    out["Board of Supervisors"] = {
        "first": s["years"][:4] + "-01-01" if s.get("years") else None,
        "last": max((d for d in mdates if d <= ctx.today_s), default=s["generated"][:10]),
        "meetings": None, "missing": [],
        "fullTitles": False, "titlesNote": f"titles returned by {len(s['terms'])} search terms; "
                                           f"{len(meets)} meetings mirrored in full ({min(mdates) if mdates else '—'} to {max(mdates) if mdates else '—'}), not an input to the record",
        "script": "tools/meetings/bos-street-records.py"}
    m = load("data/extract/sfpuc-commission/minutes.json")["records"][0]
    dates = [x.get("date") for x in m["meetings"] if x.get("date")]
    out["SFPUC Commission"] = {
        "first": min(dates), "last": max(dates), "meetings": len(m["meetings"]),
        "missing": m["failed"] + m["unparsed"], "fullTitles": True, "titlesNote": "every minutes item",
        "script": "tools/meetings/sfpuc-commission.py"}
    return out


@check("C1", "Source coverage",
       "Each deciding body read from 2019 or earlier to within a month of today, with less than 5% of meetings "
       "missing, and full item titles kept. Each body has its own fetch script that mirrors meetings to disk, "
       "re-fetches drafts, and can be rerun without re-downloading what it holds.")
def c1(ctx, res):
    bodies = c1_builtin(ctx)
    for path in glob.glob(os.path.join(ROOT, "out", "*", "coverage.json")):
        c = json.load(open(path))
        rel = os.path.relpath(path, ROOT)
        if "C1" in c:
            # tools/projects/record-coverage.py writes one row per body under "C1",
            # from the meeting mirrors: "held" meetings and a count missing.
            for b in c["C1"]:
                bodies[b["body"]] = {
                    "first": b.get("first"), "last": b.get("last"), "meetings": b.get("held"),
                    "missing": [None] * int(b.get("missing") or 0), "fullTitles": b.get("fullTitles"),
                    "titlesNote": f"{b.get('items')} items, from {rel}",
                    "established": b.get("established"), "establishedSource": b.get("establishedSource"),
                    "script": b.get("script") or f"scripts/fetch-{b['mirror']}.py"}
            continue
        c.setdefault("titlesNote", "from " + rel)
        bodies[c["body"]] = c
    cutoff = (ctx.today - dt.timedelta(days=31)).isoformat()
    rows, passing = [], 0
    for name in sorted(set(C1_BODIES) | set(bodies)):
        b = bodies.get(name)
        if not b:
            rows.append((name, "—", "—", "—", "—", "nothing read", "no", "FAIL"))
            res.fail(name, "nothing read")
            continue
        fails = []
        est = b.get("established")
        if est and b.get("first") and (dt.date.fromisoformat(b["first"]) - dt.date.fromisoformat(est)).days <= 60:
            # A body created after 2019 is read from its first meeting.
            b["titlesNote"] = f"{b.get('titlesNote')}; established {est} ({b.get('establishedSource')}), read from its first meeting"
        elif not b.get("first") or b["first"] > "2019-12-31":
            fails.append("starts after 2019")
        if not b.get("last") or b["last"] < cutoff:
            fails.append("last read before " + cutoff)
        miss = len(b.get("missing") or [])
        if b.get("meetings") is None:
            fails.append("no meeting list")
        elif b["meetings"] and miss / b["meetings"] >= 0.05:
            fails.append("%s missing" % pct(miss, b["meetings"]))
        if not b.get("fullTitles"):
            fails.append("titles not kept in full")
        script = b.get("script")
        if not script or not os.path.exists(os.path.join(ROOT, script)):
            fails.append("no fetch script")
        elif not re.search(r"from lib(\.mirror)? import|lib\.mirror|\bMirror\(",
                           open(os.path.join(ROOT, script), encoding="utf-8").read()):
            # lib/mirror.py is what re-fetches drafts and skips settled meetings on a rerun.
            fails.append("fetch script does not write through lib/mirror.py (drafts re-fetched, reruns cheap)")
        passing += not fails
        if fails:
            res.fail(name, "; ".join(fails))
        rows.append((name, b.get("first"), b.get("last"), b.get("meetings"), miss, b.get("titlesNote"), script or "—",
                     "; ".join(fails) or "PASS"))
    res.measured = passing
    res.denominator = f"{len(rows)} deciding bodies"
    res.table(["Body", "First", "Last", "Meetings held", "Missing", "Titles kept", "Script", "Result"], rows)
    res.verdict(passing == len(rows))


def corpus(ctx):
    """Every item of every deciding body's meeting mirror (data/<body>/meetings/), read the same way in any checkout.

    Returns {"items": [(kind, body label, date, title, text)], "inventory": rows, "incomplete": [body]}. The bodies
    are tools/projects/project-record.py's MIRRORS, so the audit searches exactly the bodies the matcher reads. A body
    whose meeting files on disk fall short of what its tracked index.json says were mirrored is incomplete: the
    Board of Supervisors' files are gitignored and rebuilt by tools/meetings/fetch-bos-meetings.py, so a fresh checkout
    has the index and none of the meetings. The checks that search the corpus say so rather than search less."""
    def read():
        from lib import mirror
        pr = ctx.once("pr", lambda: load_module("project_record", "tools/projects/project-record.py"))
        items, inventory, incomplete = [], [], []
        for body, kind, label in pr.MIRRORS:
            idx = mirror.index(body) or {}
            meetings = mirror.load(body, strict=False)
            n = 0
            for m in meetings:
                for it in m.get("items") or []:
                    title = re.sub(r"\s+", " ", it.get("title") or "").strip()
                    if not title or pr.PROCEDURE.match(title):
                        continue
                    items.append((kind, label, m.get("date") or "", title, it.get("text") or ""))
                    n += 1
            want = idx.get("mirrored")
            short = want is None or len(meetings) < want
            if short:
                incomplete.append(label)
            inventory.append((label, f"data/{body}/meetings/", want if want is not None else "no index",
                              len(meetings), n, "INCOMPLETE" if short else "complete"))
        return {"items": items, "inventory": inventory, "incomplete": incomplete}
    return ctx.once("corpus", read)


def corpus_lines(ctx, res):
    """Print what the corpus holds; True when it is complete enough to search."""
    c = corpus(ctx)
    res.line(f"Searched: every non-procedural item of the {len(c['inventory'])} deciding bodies' meeting mirrors "
             f"({len(c['items'])} items), the same bodies tools/projects/project-record.py matches against.")
    res.line()
    res.table(["Body", "Mirror", "Meetings its index says are mirrored", "Meeting files read", "Items searched", "State"],
              c["inventory"])
    if c["incomplete"]:
        res.status = "NOT MEASURED"
        res.line(f"Not measured: the mirror of {', '.join(c['incomplete'])} is not all on disk in this checkout, so a "
                 f"search would find less than the matcher had. Rebuild it (data/bos-meetings/README.md says how) and "
                 f"run the audit again.")
        return False
    return True
C2_DROP = {"the", "a", "an", "of", "project", "projects", "program", "programme", "pw", "sfmta", "mta", "joint", "lead"}
C2_ALT = {"street": "(?:st|street)", "st": "(?:st|street)", "avenue": "(?:ave?|avenue)", "ave": "(?:ave?|avenue)",
          "boulevard": "(?:blvd|boulevard)", "blvd": "(?:blvd|boulevard)", "improvements": "improvements?",
          "improvement": "improvements?"}


C2_SERIES_WORDS = {"various", "locations", "location", "sewer", "replacement", "pavement", "renovation", "as", "needed",
                   "citywide", "city", "wide", "spot", "main", "water", "and", "no", "improvements", "improvement"}


def c2_hits(ctx, p, docs, keep=lambda d: True):
    """Dated items of the mirrors that C2's name search finds for a project, as (body label, date).

    An item that a longer listed project's name also finds, holding this one's name ("Folsom-Howard Streetscape"
    for "Howard Streetscape"), is that project's and is left out."""
    words = " ".join(c2_words(p["name"]))
    longer = [c2_name_patterns(q, loose=True) for q in ctx.projects
              if q["name"] != p["name"] and words and len(c2_words(q["name"])) > len(c2_words(p["name"]))
              and words in " ".join(c2_words(q["name"]))]
    rxs = c2_name_patterns(p)
    out = []
    if not rxs:
        return out
    pr = ctx.once("pr", lambda: load_module("project_record", "tools/projects/project-record.py"))
    for _, label, d, title, text in docs:
        if not d or not keep(d):
            continue
        # The item's own text, not the minutes' account of the discussion
        # after it: a project manager listing WW-719D while the SFPUC amends
        # PRO.0101 (2023-06-13) is not a record of WW-719D.
        t, x = title.lower(), (pr.formal_text(text) or "").lower()
        if any(rx.search(t) or (x and rx.search(x)) for rx in rxs):
            if any(any(rx.search(t) or (x and rx.search(x)) for rx in q) for q in longer):
                continue
            out.append((label, d))
    return out


def c2_words(name):
    name = re.sub(r"\(.*?\)", " ", name or "").lower()
    name = re.sub(r"\b\d{6,}\b", " ", name)
    return [w for w in re.findall(r"[a-z0-9]+", name) if w not in C2_DROP]


def c2_name_patterns(p, loose=False):
    """C2's independent name search: the whole name in order (not a street alone), and any contract number.

    Written apart from tools/projects/project-record.py's name keys, so a miss in one is not a miss in both. Words may be
    joined by punctuation or an "and" ("Candlestick Point/Hunters Point Shipyard" is "Candlestick Point and Hunters
    Point Shipyard" at the Board of Supervisors); a bracket is dropped. A phase stays in: "29 Sunset Improvement
    Project – Phase Two" is not the phase-one project's items."""
    words = c2_words(p["name"])
    if loose:
        words = [w for w in words if w not in ("improvement", "improvements")]
    out = []
    streetish = STREET_WORDS | {"st", "ave", "blvd", "and"}
    # A series name with its number only in brackets ("PW Various Locations
    # Sewer Replacement (JV VL PR No 82)") names a kind of job, not a job.
    if not set(words) - C2_SERIES_WORDS:
        words = []
    if len(words) >= 2 and any(not re.fullmatch(r"\d+(st|nd|rd|th)?", w) and w not in streetish for w in words[1:]):
        out.append(re.compile(r"\b" + r"[\s\-/&,.:]+(?:and\s+|the\s+)?".join(C2_ALT.get(w, re.escape(w)) for w in words)
                              + r"\b"))
    for c in CONTRACT.findall(" ".join([p["name"], p.get("scopeText") or ""])):
        code = re.sub(r"[\s-]", "", c.lower())
        out.append(re.compile(r"\b%s-?\s?%s\b" % (re.escape(code[:2] if code[:2] != "pr" else code[:3]),
                                                  re.escape(code[2:] if code[:2] != "pr" else code[3:]))))
    return out


# The mirrors of the bodies that decide each department's projects (the labels
# corpus() gives their items), for rule PRE-MIRROR.
DECIDING_MIRRORS = {"SFMTA": ("SFMTA engineering hearing", "SFMTA Board of Directors", "SFCTA Board"),
                    "SFPUC": ("SFPUC Commission",),
                    "Public Works": ("Public Works Commission",)}


def mirror_first(ctx, dept):
    """The earliest meeting date held in any mirror of the bodies that decide dept's projects, or None."""
    firsts = ctx.once("c2_mirror_first", lambda: {
        label: min(d for _, lb, d, _, _ in corpus(ctx)["items"] if lb == label and d)
        for label in {lb for _, lb, _, _, _ in corpus(ctx)["items"]}})
    dates = [firsts[b] for b in DECIDING_MIRRORS.get(dept, ()) if b in firsts]
    return min(dates) if dates else None


def c2_reason(ctx, p):
    """A reason code for a major project's real gap, with the evidence that supports it, or None.

    Each code is assigned by a rule over the data, never by hand; a project no rule fits stays unexplained.
    NOT-DUE, "work starts later": the published start is after today, or no start is published and the phase
      is planning, so the award or legislation that decides it has not come up (evidence: the start or phase).
    PRE-MIRROR, "started before the mirrors": the start is earlier, at its own precision, than the first
      meeting any mirror of the bodies that decide its department's projects holds (DECIDING_MIRRORS).
    UNMIRRORED, "hearing not in any mirror": the project's own page dates a public hearing or SFMTA Board
      meeting on a day no mirror holds (evidence: those dates).
    A department's usual process is not a reason: it is true of every project of that department."""
    start = p.get("start") or ""
    if start and start_key(start) > ctx.today_s:
        return f"NOT-DUE: work starts {start}, after {ctx.today_s}"
    if not start and stage(p.get("phase")) == "planning":
        return f"NOT-DUE: no start published and the phase is {p.get('phase')}, so work has not started"
    first = mirror_first(ctx, p.get("department"))
    if start and first and record_dates.before_start(start, first):
        return f"PRE-MIRROR: work started {start}, before the deciding bodies' mirrors begin on {first}"
    unheld = page_meetings_unmirrored(ctx, p)
    if unheld:
        return "UNMIRRORED: its own page dates " + ", ".join(unheld[:3]) + ", which no meeting mirror holds"
    return None


def c2_reading(ctx, p, reading, found, have):
    """What the record shows for a major project under three: the finding behind the number, from the sources."""
    start = p.get("start") or ""
    future = bool(start) and start_key(start) > ctx.today_s
    page_items = sum(1 for r in p["records"] if r.get("relation") == OWN_PAGE)
    closest = next((l.get("label") for l in p.get("links") or () if "closest official source" in (l.get("label") or "")), None)
    if reading == "matching miss":
        return f"matching miss: the name is in {len(found)} more dated item(s) the list does not attach ({', '.join(found[:4])})"
    if reading == "partly":
        return f"the name is in {len(found)} more dated item(s) the list does not attach ({', '.join(found[:4])}); still under three"
    bits = ["no item of the seven bodies names it" + (" beyond the dates attached" if have else "")]
    # Why a real gap is under three, from what the record holds.
    dept = p.get("department")
    if dept in ("Public Works", "SFPUC"):
        body = "Public Works Commission" if dept == "Public Works" else "SFPUC Commission"
        bits.append(f"a construction contract reaches the {body} at its award and at later changes to the contract, "
                    f"not at each stage of design the way an SFMTA project reaches the hearing and the Board")
    if future:
        bits.append(f"work starts {start}, so its contract award, the usual deciding record, is not due yet")
    other = {r.get("date") for r in p["records"] if r.get("kind") in BODY_KINDS and r.get("relation") != OWN_PAGE
             and r.get("grade") in ("co-located", "same street", "weak", "ambiguous") and r.get("date")} - set(have)
    if dept == "SFMTA":
        bits.append("the engineering hearing and the SFMTA Board itemise work by street and action, not by project "
                    "name" + (f"; {len(other)} more dated item(s) on its streets are other work there (a dock, a zone, "
                              f"another project) or match more than one project, so they are shown and not counted"
                              if other else ""))
    unheld = page_meetings_unmirrored(ctx, p)
    if unheld:
        bits.append("its own page lists " + ", ".join(unheld[:3]) + ", which no meeting mirror holds (the hearing "
                    "mirror holds the biweekly engineering hearings, not a project's own virtual hearing)")
    if page_items:
        bits.append(f"its own page lists {page_items} item(s), which C2 does not count")
    if closest:
        bits.append(closest[0].lower() + closest[1:])
    return "; ".join(bits)


_PAGE_HEARING = re.compile(r"public hearing|engineering hearing", re.I)
_PAGE_BOARD = re.compile(r"board of directors|sfmta board", re.I)


def page_meetings_unmirrored(ctx, p):
    """Hearings and Board meetings a project's own page dates, that no meeting mirror holds for that day."""
    held = ctx.once("c2_held", lambda: {(label, d) for _, label, d, _, _ in corpus(ctx)["items"]})
    out = []
    for r in p["records"]:
        d = r.get("date") or ""
        if r.get("kind") != "project-page" or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            continue
        t = r.get("title") or ""
        if re.search(r"tree|results|office hours|open house", t, re.I):
            continue
        if _PAGE_HEARING.search(t) and ("SFMTA engineering hearing", d) not in held:
            out.append(f"a public hearing on {d}")
        elif _PAGE_BOARD.search(t) and ("SFMTA Board of Directors", d) not in held:
            out.append(f"a Board meeting on {d}")
    return sorted(set(out))


def major(ctx):
    """Outlined, or at least 1 mi of plan network, in the basis About the data
    states (per direction of travel when the page is not built), measured from
    the sources (mile_reference), not the planMiles the pipeline wrote."""
    basis = stated_basis(ctx) or "per direction"
    return [p for p in ctx.projects if p.get("highlight") or project_plan_miles(ctx, p, basis) >= 1]


@check("C2", "Mentions per major project",
       "Every major project with fewer than three distinct dated records from city bodies has its reason printed; the share with three or more is reported.")
def c2(ctx, res):
    if "missing" in ctx.miles_ref:
        res.status = "NOT MEASURED"
        res.line("Not measured: which projects are major needs plan miles measured from the sources, and "
                 + ctx.miles_ref["missing"] + ".")
        return
    M = major(ctx)
    rows, three = [], 0
    for p in M:
        dates = {r["date"] for r in city_body_records(p) if r.get("date")}
        if len(dates) >= 3:
            three += 1
            continue
        rows.append([p["department"], p["name"], len(dates), None, None, explained("C2", p["name"]), dates])
    res.measured = three
    basis = stated_basis(ctx)
    res.denominator = (f"{len(M)} major projects (outlined, or at least 1 mi of plan network, counted "
                       + (f"{basis} miles as About the data states" if basis else "per direction of travel; About the data states no basis")
                       + ", measured from the bikeway layer and the plan's map)")
    res.facts.update(major=len(M), three=three)
    res.line(f"{pct(three, len(M))} have three or more. A record counts when it comes from a city body (not the project's own page) "
             f"and is graded exact, strong or probable. For each one below three, the project's name was searched in every "
             f"deciding body's meeting mirror; dates found there that the matcher did not attach make it a matching miss.")
    complete = corpus_lines(ctx, res)
    res.line("The name search takes the project's whole name, its words in order with only articles, “project” "
             "and “program” dropped, never a street alone: “5th Street Improvement Project” is searched as "
             "“5th Street Improvement”, not “5th Street”. A contract number the name or scope carries is searched too. "
             "It reads each item's title and its own text, not the minutes' account of the discussion after it.")
    res.line("An item that names a longer listed project holding this one's name (“Folsom-Howard Streetscape” for "
             "“Howard Streetscape”) is that project's, and is not counted here.")
    by_name = {p["name"]: p for p in M}
    if complete:
        docs = corpus(ctx)["items"]
        for row in rows:
            p = by_name[row[1]]
            hits = collections.defaultdict(set)
            for label, d in c2_hits(ctx, p, docs):
                hits[label].add(d)
            found = sorted({d for v in hits.values() for d in v if d} - row[6])
            row[3] = ", ".join("%s %d" % (k, len(v)) for k, v in sorted(hits.items())) or "none"
            row[4] = "matching miss" if len(found) + len(row[6]) >= 3 else "gap" if not found else "partly"
            row.append(c2_reading(ctx, p, row[4], found, row[6]))
            # A real gap is explained only by data: a written explanation in
            # data/audit/explanations.csv, or a reason code whose evidence is
            # in the record (c2_reason). A gap with neither fails, as does a
            # matching miss without a written explanation or a fix (Fable
            # review, 2026-09-30: a default string here explained every row).
            if not row[5] and row[4] == "gap":
                row[5] = c2_reason(ctx, p)
        readings = collections.Counter(r[4] for r in rows)
        future = sum(1 for r in rows if (by_name[r[1]].get("start") or "") and
                     start_key(by_name[r[1]]["start"]) > ctx.today_s)
        contract = sum(1 for r in rows if r[0] in ("Public Works", "SFPUC"))
        res.line()
        res.line(f"Of the {len(rows)} under three: {readings.get('gap', 0)} real gaps, {readings.get('partly', 0)} partly "
                 f"missed and {readings.get('matching miss', 0)} matching misses by the independent name search. "
                 f"{contract} are Public Works or SFPUC construction contracts, which reach a commission at award and "
                 f"at later contract changes, and {future} have not started.")
    res.line()
    res.table(["Department", "Major project", "City-body dates", "Name found by date (body: dates)", "Reading",
               "What the record shows", "Explanation"],
              sorted(([r[0], r[1], r[2], r[3], r[4], r[7] if len(r) > 7 else "", r[5]] for r in rows),
                     key=lambda r: (r[0], r[1])))
    for r in rows:
        if not r[5]:
            res.fail(r[1], f"{r[2]} city-body dates; {r[4] or 'not searched'}" + (f" (name found: {r[3]})" if r[3] else ""))
    if not complete:
        return
    # Bryan, 2026-09-30: pass when explained. Most Public Works
    # jobs never go before a body by name, so no share line is reachable; the
    # share is reported, and every project under three must carry its reason.
    res.verdict(bool(M) and not [r for r in rows if not r[5]])


def is_body_meeting(label, title):
    t = (title or "").lower()
    if label == "SFMTA Board":
        return bool(re.search(r"board of directors|sfmta board", t))
    if label == "Engineering hearing":
        return bool(re.search(r"engineering (public )?hearing|public hearing", t))
    return False


@check("C3a", "Labels: project-page items under City decisions",
       "No mislabelled kinds: nothing from a project's own page shows under “City decisions naming this project”.")
def c3a(ctx, res):
    # What the page shows under City decisions: site/src/pages/transportation-projects.mjs
    # ownRecords() takes the own grades and leaves every project-page item to
    # its own fold ("milestones and events from the project's own page").
    graded = [(p, r) for p in ctx.projects for r in p["records"] if r.get("grade") in OWN_GRADES]
    shown = [(p, r) for p, r in graded if r.get("kind") != "project-page"]
    page = [(p, r) for p, r in shown if r.get("relation") == OWN_PAGE]
    folded = [r for _, r in graded if r.get("kind") == "project-page"]
    res.line(f"{len(folded)} project-page items are shown apart, in the page's own fold, not under City decisions: "
             + ", ".join(f"{k} {v}" for k, v in collections.Counter(r["label"] for r in folded).most_common()) + ".")
    by_label = collections.Counter(r["label"] for _, r in page)
    events = [(p["name"], r["date"], r["label"], r["title"]) for p, r in page
              if r["label"] in ("SFMTA Board", "Engineering hearing") and not is_body_meeting(r["label"], r["title"])]
    res.measured = len(page)
    res.denominator = f"{len(shown)} items under City decisions"
    if by_label:
        res.line("Project-page items under City decisions, by the label they show: "
                 + ", ".join(f"{k} {v}" for k, v in by_label.most_common()) + ".")
    res.line(f"Of those labelled as a city body, {len(events)} are not a meeting of that body (open houses, tabling, walks, advisory committees):")
    res.line()
    res.table(["Project", "Date", "Label shown", "Title"], sorted(events, key=lambda e: e[1] or ""), limit=40)
    for p, r in page:
        res.fail(p["name"], f"{r.get('date')} {r.get('label')}: project-page item under City decisions: {(r.get('title') or '')[:80]}")
    res.verdict(not page)


def full_name_tokens(name):
    """The words of a project's name outside brackets, when they are distinctive enough to find it by: three or more, not all generic."""
    t = name_tokens(re.sub(r"\(.*?\)", " ", name or ""))
    if len(t) < 3 or not (t - GENERIC - KIND - {"no", "as", "needed", "spot"}):
        return None
    return t


NUMBERED = re.compile(r"(?:\bno\.?|#)\s*(\d+[a-z]?)\b", re.I)


def names_project(name, full, title):
    """True when a title names the project: its words in order, and its number (No 47, #21) as a number."""
    rx = core_regex(re.sub(r"\(.*?\)", " ", name))
    if not rx or not rx.search(title) or not full <= name_tokens(title):
        return False
    want = {n.lower() for n in NUMBERED.findall(re.sub(r"\(.*?\)", " ", name))}
    return not want or bool(want & {n.lower() for n in NUMBERED.findall(title)})


CONTRACT = re.compile(r"\b(?:WD|WW|CS|DB|HH|PRO|SWW)-?\s?\d{3,4}[A-Z]?\b", re.I)


def title_key(t):
    """A title with case, punctuation and spacing folded, whole (not cut to a prefix)."""
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def same_title(a, b):
    """True when two folded titles are one item's: equal, or one the other's opening of 40 characters or more.

    The mirror often holds an agenda heading ("Award Contract No. WW-793,
    Brannan Street Outfall Improvements") where the attached record holds the
    minutes' full title, which opens with the same words and runs on."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 40 and long_.startswith(short)


class TitleSet(object):
    """Attached titles, and the contract numbers attached on each date, for C3b's "is it attached" test."""

    def __init__(self):
        self.titles, self.nums = set(), set()

    def add(self, title, date=None):
        k = title_key(title)
        if k:
            self.titles.add(k)
        for n in CONTRACT.findall(title or ""):
            self.nums.add((date, re.sub(r"[\s-]", "", n.upper())))

    def holds(self, title, date=None):
        k = title_key(title)
        if k in self.titles or any(same_title(k, t) for t in self.titles):
            return True
        # The same contract number on the same date is the same award.
        return any((date, re.sub(r"[\s-]", "", n.upper())) in self.nums for n in CONTRACT.findall(title or ""))


@check("C3b", "Records naming a project's contract number or full name",
       "Every item naming the project's name or contract number is counted as the project's own.")
def c3b(ctx, res):
    res.line("An item counts when its title carries the project's contract number (WD-, WW-, CS-… read from the name "
             "or scope) or its full name (three or more distinctive words, in order), and the project shows it under "
             "anything weaker than its own record or does not attach it at all. The search covers each project's "
             "attached records and every item of the deciding bodies' meeting mirrors.")
    if not corpus_lines(ctx, res):
        return
    docs = corpus(ctx)["items"]
    key = title_key
    nums_of = lambda t: {re.sub(r"[\s-]", "", n.upper()) for n in CONTRACT.findall(t or "")}
    # Index the mirror once: contract numbers and words per item.
    by_num, by_tok = collections.defaultdict(list), collections.defaultdict(set)
    for i, (kind, label, d, title, _) in enumerate(docs):
        for n in CONTRACT.findall(title):
            by_num[re.sub(r"[\s-]", "", n.upper())].append(i)
        for t in name_tokens(title):
            by_tok[t].add(i)
    pr = ctx.once("pr", lambda: load_module("project_record", "tools/projects/project-record.py"))
    # Which projects carry each title as their own record: an item that names
    # a program and one of its projects is attached to the project, whose name
    # carries the program's initials (FASIP Harrison/Treat Box Sewer), and
    # counts for the program too.
    own_by_title = collections.defaultdict(set)
    for q in ctx.projects:
        for r in q["records"]:
            if r.get("grade") in OWN_GRADES:
                own_by_title[key(r.get("title"))].add(q["name"])

    def owners(title):
        k = key(title)
        return set().union(*([v for t, v in own_by_title.items() if same_title(k, t)] or [set()]))
    rows = []
    for p in ctx.projects:
        text = " ".join([p["name"], p.get("scopeText") or ""])
        nums = {re.sub(r"[\s-]", "", n.upper()) for n in CONTRACT.findall(text)}
        full = full_name_tokens(p["name"])
        # A project named for a place (Treasure Island and Yerba Buena Island)
        # is named by an item about the development ("<place> Project", its
        # streets, its maps); the place alone is the place.
        # tools/projects/project-record.py grades those PLACE by the same rule.
        keys = pr.name_keys(p["name"])
        place_pat = pr.name_pattern(p["name"]) if keys and all(pr.is_place_key(k) for k in keys) else None
        own_titles = TitleSet()
        attached = TitleSet()
        for r in p["records"]:
            attached.add(r.get("title"), r.get("date"))
            if r.get("grade") in OWN_GRADES:
                own_titles.add(r.get("title"), r.get("date"))
        # One vote can carry two titles (the mirror's parent item and the
        # keyword extract's sub-item); project-record keeps the other in
        # alsoTitles, and the vote is attached under either.
        for rid in {p["id"]} | {"dotmaps:" + f for f in feed_ids_of(p)}:
            for r in ctx.record.get(rid, {}).get("records", []):
                for t in r.get("alsoTitles") or ():
                    attached.add(t, r.get("date"))
        # Attached records graded weaker than the project's own.
        for r in p["records"]:
            if (r.get("kind") not in BODY_KINDS or r.get("relation") == OWN_PAGE
                    or own_titles.holds(r.get("title"), r.get("date"))):
                continue
            title = r.get("title") or ""
            tnums = {re.sub(r"[\s-]", "", n.upper()) for n in CONTRACT.findall(title)}
            why = ("contract " + ", ".join(sorted(nums & tnums)) if nums & tnums
                   else "full name" if full and names_project(p["name"], full, title)
                   and (place_pat is None or pr.place_is_project(place_pat, pr.norm_name(title))) else None)
            if why:
                rows.append((p["name"], r.get("date"), r.get("label") or r.get("kind"), why, r.get("grade") or "—", title[:120]))
        # Mirror items the project does not carry at all.
        cand = {i for n in nums for i in by_num.get(n, [])}
        if full:
            cand |= set.intersection(*(by_tok.get(t, set()) for t in full))
        for i in sorted(cand):
            kind, label, d, title, _ = docs[i]
            if attached.holds(title, d) or any(pr.names_program(q, p["name"]) for q in owners(title)):
                continue
            tnums = {re.sub(r"[\s-]", "", n.upper()) for n in CONTRACT.findall(title)}
            why = ("contract " + ", ".join(sorted(nums & tnums)) if nums & tnums
                   else "full name" if full and names_project(p["name"], full, title)
                   and (place_pat is None or pr.place_is_project(place_pat, pr.norm_name(title))) else None)
            if why:
                rows.append((p["name"], d, label, why, "not attached", title[:120]))
    seen, uniq = set(), []
    for r in rows:
        k = (r[0], r[1], key(r[5]))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    res.measured = len(uniq)
    res.denominator = f"{len(ctx.projects)} listed projects, searched in their attached records and {len(docs)} mirror items"
    res.facts.update(found=len(uniq), projects=len({r[0] for r in uniq}), items=len(docs))
    res.line()
    res.table(["Project", "Date", "Body", "Names", "Graded", "Title"], sorted(uniq, key=lambda r: (r[0], r[1] or "")), limit=60)
    for r in uniq:
        res.fail(f"{r[0]} / {r[1]} {r[2]}", f"names the {r[3]}; {r[4]}: {r[5]}")
    res.verdict(not uniq)


@check("C3c", "Matching accuracy: hand-checked sample",
       "Every link in a seeded random sample of at least 40 is about its project and carries the right kind label.")
def c3c(ctx, res):
    path = os.path.join(GRADES_DIR, "c3-links.csv")
    rows = read_csv(path)
    if not rows:
        res.status = "NOT GRADED"
        res.line(f"No sample at {os.path.relpath(path, ROOT)}; run the audit once to write the template.")
        return
    graded = [r for r in rows if (r.get("about_project") or "").strip() and (r.get("label_correct") or "").strip()]
    wrong = [r for r in graded if r["about_project"].strip().lower() != "yes" or r["label_correct"].strip().lower() != "yes"]
    if len(graded) < len(rows):
        res.measured = len(graded) - len(wrong)
        res.denominator = f"{len(graded)} graded of {len(rows)} sampled links"
        res.status = "NOT GRADED"
        res.line(f"{len(rows) - len(graded)} of {len(rows)} rows in {os.path.relpath(path, ROOT)} carry no grade yet.")
        return

    # The grades are fixed; the matcher is not. A graded link the list no
    # longer counts as the project's own (dropped, or relabelled "same street",
    # "place" or "co-located") has left the list, so it is shown as such
    # rather than scored again. A link still counted is scored as graded.
    by_slug = {p["slug"]: p for p in ctx.projects}

    def still_counted(r):
        p = by_slug.get(r["slug"])
        if not p:
            return False
        head = (r.get("record_title") or "")[:60].lower()
        return any(x.get("grade") in OWN_GRADES and x.get("kind") in BODY_KINDS and x.get("relation") != OWN_PAGE
                   and (x.get("date") or "") == r["record_date"] and (x.get("title") or "")[:60].lower() == head
                   for x in p["records"])

    counted = [r for r in graded if still_counted(r)]
    gone = [r for r in graded if not still_counted(r)]
    wrong_counted = [r for r in counted if r in wrong]
    res.measured = len(counted) - len(wrong_counted)
    res.denominator = (f"{len(counted)} graded links the list still counts, of {len(graded)} graded "
                       f"({len(gone)} no longer counted: {sum(1 for r in gone if r in wrong)} graded wrong, "
                       f"{sum(1 for r in gone if r not in wrong)} graded right)")
    res.facts.update(graded=len(graded), counted=len(counted), gone=len(gone), wrong_gone=sum(1 for r in gone if r in wrong))
    res.line("A graded link the list no longer counts as the project's own is shown apart. When most of the sample "
             "has left the list, draw a new one: delete the grade columns' contents and run the audit.")
    res.line()
    res.table(["Project", "Date", "Label", "About project", "Label correct", "Note", "Now"],
              [(r["project"], r["record_date"], r["record_label"], r["about_project"], r["label_correct"], r.get("note"),
                "counted" if r in counted else "no longer counted") for r in wrong]
              + [(r["project"], r["record_date"], r["record_label"], r["about_project"], r["label_correct"], r.get("note"),
                  "no longer counted") for r in gone if r not in wrong])
    for r in wrong_counted:
        res.fail(f"{r['project']} / {r['record_date']}", f"about project {r['about_project']}, label correct "
                 f"{r['label_correct']}: {r.get('note') or ''}")
    # Bryan's pass line (criteria doc, C3 thread): every link in a sample of
    # at least 40. Links the list no longer counts do not count towards the 40.
    if len(counted) < 40:
        res.line(f"The list still counts {len(counted)} of the graded links; the pass line needs a sample "
                 "of at least 40, so a new sample must be drawn and graded.")
    res.verdict(not wrong_counted and len(counted) >= 40)


def body_for(p):
    """The body that should carry a dated decision on this project, by who runs it and when it starts."""
    dept = p["department"]
    if dept == "SFMTA":
        return "SFMTA engineering hearing or Board (legislation); SFCTA Board if Prop K/L funds it"
    if dept == "SFPUC":
        return "SFPUC Commission (contract award)"
    if dept == "Public Works":
        if (p.get("start") or "") < "2022-07":
            # The Public Works Commission first met 2022-07-28; before it the
            # Director awarded contracts by order, and no online archive of
            # those orders has been found.
            return "Director of Public Works (order; not published online)"
        return "Public Works Commission (contract award)"
    return "?"


@check("C4", "A record before work starts",
       "Over 90% of listed projects with a start date have a city-body record dated before that start, or the "
       "shortfall is logged as a top issue on About the data (Bryan, 2026-09-29: \"Let's just log this as a problem "
       "and add to the list of issues. That we have most projects in the shared feed that don't have a project page.\").")
def c4(ctx, res):
    withstart = [p for p in ctx.projects if p["start"]]
    rows, ok = [], 0
    tally = collections.defaultdict(lambda: [0, 0, 0, 0])  # started, started ok, future, future ok
    for p in withstart:
        # One rule for "before the start", shared with tools/projects/record-coverage.py.
        before = record_dates.records_before_start(p)
        started = start_key(p["start"]) <= ctx.today_s
        t = tally[p["department"]]
        t[0 if started else 2] += 1
        if before:
            ok += 1
            t[1 if started else 3] += 1
        else:
            rows.append((p["department"], p["name"], p["start"], "started" if started else "not yet",
                         body_for(p), p))
    res.measured = ok
    res.denominator = len(withstart)
    res.line(f"{pct(ok, len(withstart))} have one. A record counts when it comes from a city body, is graded exact, strong "
             f"or probable, and is dated before the project's start at the start's own precision. A job that has "
             f"not started is usually not yet awarded, so its deciding record may not exist yet; the two are "
             f"counted apart.")
    res.line()
    trows = []
    for dep in sorted(tally):
        s0, s1, f0, f1 = tally[dep]
        trows.append((dep, f"{s1} of {s0}", f"{f1} of {f0}", f"{s1 + f1} of {s0 + f0}"))
    s0, s1, f0, f1 = (sum(t[k] for t in tally.values()) for k in range(4))
    trows.append(("All", f"{s1} of {s0}", f"{f1} of {f0}", f"{s1 + f1} of {s0 + f0}"))
    res.table(["Department", "Started, with a record before", "Not yet started, with one", "All"], trows)
    # Why each of the rest has none, from the sources: its kind of work, the
    # dates of the city-body records it does carry, and a name search of every
    # deciding body's mirror (C2's, written apart from the matcher) for an item
    # before its start that the list does not attach.
    docs = corpus(ctx)["items"] if not corpus(ctx)["incomplete"] else None
    causes = collections.Counter()
    detail = []
    for d, n, s, st, b, p in sorted(rows, key=lambda r: r[:5]):
        kind = c4_kind(p)
        after = [r for r in city_body_records(p) if r.get("date")]
        found = []
        if docs is not None:
            have = {r.get("date") for r in after}
            found = sorted({f"{label} {dd}" for label, dd in
                            c2_hits(ctx, p, docs, keep=lambda dd: record_dates.before_start(dd, s) and dd not in have)})
        if found:
            cause = "name found before the start in an item the list does not attach"
        elif st == "not yet":
            cause = "not started; no city-body item names it yet"
        elif s < "2019":
            cause = "started before 2019, before the mirrors begin"
        elif after:
            cause = "started; its city-body records all date from after the start"
        elif d == "Public Works" and s < "2022-07":
            cause = "started before the Public Works Commission existed (2022-07); no city-body item names it"
        else:
            cause = "started; no city-body item names it"
        causes[(d, kind, cause)] += 1
        plan_only = kind == "paving" and any("Public Works paving map" in (l.get("label") or "") for l in p.get("links") or ())
        detail.append((d, n, s, st, kind, cause + (f": {', '.join(sorted(found)[:3])}" if found else ""),
                       "yes" if plan_only else "", b))
    res.line()
    res.line("Why the rest have none, by department and kind of work. “No city-body item names it” means a search of "
             "every item of the seven deciding bodies' mirrors for the project's whole name and any contract number "
             "found nothing dated before its start; for a job that has not started, the award that would decide it "
             "is not due yet.")
    res.table(["Department", "Kind", "Cause", "Projects"],
              [(d, k, c, v) for (d, k, c), v in sorted(causes.items(), key=lambda kv: (-kv[1], kv[0]))])
    plan = [x for x in detail if x[6]]
    res.line()
    res.line(f"{len(plan)} of them are Public Works paving jobs whose only published source before work is Public "
             f"Works' paving map, the five-year paving plan (the row links it as the closest official source). The "
             f"criterion's record is a dated record from a city body: the plan is a department's schedule, not a "
             f"body's decision, and gives no decision date, so it is not counted.")
    res.line()
    res.table(["Department", "Project", "Start", "Started", "Kind", "Cause", "Only the paving plan", "Body that should have decided it"],
              detail, limit=80)
    for d, n, s, st, kind, cause, _, b in detail:
        res.fail(n, f"{d}, start {s} ({st}): no city-body record before it; {cause}; {b}")
    res.facts.update(c4_causes={" / ".join(k): v for k, v in causes.items()}, c4_plan_only=len(plan))
    share_ok = bool(withstart) and ok / len(withstart) > 0.9
    in_scope = [x for x in rows if not has_own_page(x[5])]
    out_scope = [x for x in rows if has_own_page(x[5])]
    issue = c4_logged_issue(ctx, paged=len(out_scope))
    # The logged issue covers feed jobs with no project page. Bryan widened it
    # on 2026-09-30 ("Widen the issue") to the misses that
    # have a page too, so once the issue prints their count they need no
    # explanation each. Otherwise a miss with a page passes only with its own
    # row in data/audit/explanations.csv; the rows already written stay.
    covers_paged = bool(issue and issue[2])
    unexplained = [] if covers_paged else [x for x in out_scope if not explained("C4", x[1])]
    res.line()
    res.line(f"Of the {len(rows)} without one, {len(in_scope)} are coordination-feed jobs with no project page of their "
             f"own and {len(out_scope)} have a project page; "
             f"{sum(1 for x in out_scope if explained('C4', x[1]))} of those have a written explanation. "
             + ("The logged issue covers both and prints the count of those with a page." if covers_paged else
                "The site was not built, so whether the logged issue prints the count of those with a page was not "
                "read." if issue and issue[2] is None else
                "The logged issue covers only the feed jobs with no page." if issue else ""))
    if share_ok:
        res.line("The share is over the 90% line.")
    elif issue:
        # Bryan, 2026-09-29: "Let's just log this as a problem and add to the
        # list of issues. That we have most projects in the shared feed that
        # don't have a project page." So below the line the check passes only
        # while About the data's top issues carry that gap, and every miss
        # the issue does not describe is explained on its own.
        res.line(f"Below the 90% line. The shortfall is logged as a top issue on About the data "
                 f"({issue[0]}: “{issue[1]}”), per Bryan's decision of 2026-09-29: “Let's just log this as a problem "
                 f"and add to the list of issues. That we have most projects in the shared feed that don't have a "
                 f"project page.” He widened it on 2026-09-30 to the misses that have a page, with counts by "
                 f"department.")
    else:
        res.line("Below the 90% line, and About the data's top issues carry no item saying that coordination-feed jobs "
                 "have no project page and so no city-body decision found before work starts.")
    if not share_ok and out_scope:
        res.line()
        res.line("The misses that have a project page:")
        res.table(["Department", "Project", "Start", "Explanation"],
                  [(x[0], x[1], x[2], explained("C4", x[1]) or "none written") for x in out_scope])
    res.facts.update(c4_issue=issue[0] if issue else None, c4_misses_no_page=len(in_scope),
                     c4_misses_with_page=len(out_scope), c4_misses_with_page_unexplained=len(unexplained),
                     c4_issue_covers_paged=covers_paged)
    res.verdict(share_ok or (bool(issue) and not unexplained))


def has_own_page(p):
    """True when a listed project links a project page of its own (SFMTA's, Public Works' or SFPUC's), not only the
    coordination feed's row or a programme page standing in as the closest official source."""
    if p.get("source") in ("sfmta", "sfmta-page", "puc-page", "dpw-page"):
        return True
    return any(l.get("kind") == "project" for l in p.get("links") or ())


def about_issues(ctx):
    """About the data's top issues as [(id, bold lead, plain text)], from the <ol class="issues"> list.

    Reads the rendered page when the site was built, else site/content/transportation-about.md, where the
    figures are still {{ template }} names."""
    path = os.path.join(ctx.dist or "", BIKE, "about", "index.html")
    if ctx.dist and os.path.exists(path):
        src = open(path, encoding="utf-8").read()
    else:
        src = open(os.path.join(ROOT, "site/content/transportation-about.md"), encoding="utf-8").read()
    ol = re.search(r'<ol class="issues">(.*?)</ol>', src, re.S)
    out = []
    for m in re.finditer(r'<li id="([^"]+)">(.*?)</li>', ol.group(1) if ol else "", re.S):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        lead = re.search(r"<strong>(.*?)</strong>", m.group(2), re.S)
        out.append((m.group(1), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", lead.group(1))).strip() if lead else "",
                    text))
    return out


def states(ctx, text, count):
    """Whether an issue's text prints count as a figure: True or False on a built page, None on an unbuilt one,
    whose figures are still template names."""
    if not ctx.dist:
        return None
    return bool(re.search(r"(?<![\d.,])%d(?![\d.,])" % count, text))


def logged_issue(ctx, test, count=None):
    """The first top issue whose lower-cased text passes test, as (id, lead, states_count), or None.

    states_count is states(ctx, text, count), or True when count is None."""
    for iid, lead, text in about_issues(ctx):
        if test(text.lower()):
            return iid, lead, True if count is None else states(ctx, text, count)
    return None


def about_note(ctx, test, count=None):
    """The first method paragraph on About the data whose lower-cased text passes test, as
    ("method: <bold lead>", sentence, states_count), or None. Reads the rendered page only."""
    path = os.path.join(ctx.dist or "", BIKE, "about", "index.html")
    if not (ctx.dist and os.path.exists(path)):
        return None
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", open(path, encoding="utf-8").read(), re.S):
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
        if not test(text.lower()):
            continue
        lead = re.search(r"<strong>(.*?)</strong>", m.group(1), re.S)
        lead = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", lead.group(1))).strip() if lead else "untitled"
        sent = next((s for s in re.split(r"(?<=\.)\s+", text) if test(s.lower())), text)
        return "method: " + lead, sent, True if count is None else states(ctx, sent, count)
    return None


def c4_logged_issue(ctx, paged=None):
    """The About the data top issue that logs C4's gap, as (id, lead, covers_paged), or None.

    The issue must say coordination-feed jobs lack a project page and that a city-body decision (a board or
    commission item) before work starts cannot be found. Bryan widened it on 2026-09-30 ("Widen the issue") to the misses
    that do have a project page, with their count by department: covers_paged is True when the issue speaks of
    projects that "have one" (a project page) and, given paged (the number of such misses), prints it on the built
    page; None when the page was not built, so the figure could not be read."""
    for iid, lead, text in about_issues(ctx):
        t = text.lower()
        if (re.search(r"coordination[- ]feed", t) and "project page" in t
                and re.search(r"(decision|item)[^.]*before (work starts|that start)", t)):
            covers = bool(re.search(r"\bhave (one|a project page)\b", t))
            if covers and paged is not None:
                covers = states(ctx, text, paged)
            return iid, lead, covers
    return None


def c4_kind(p):
    """The kind of work a listed job is, from its name and scope: paving, sewer, water, street design or other."""
    name = (p.get("name") or "").lower()
    text = name + " " + (p.get("scopeText") or "").lower()
    if re.search(r"pavement|paving|resurfac", name):
        return "paving"
    if re.search(r"sewer|\bcsd\b|stormwater|trash capture|outfall", name):
        return "sewer"
    if re.search(r"water main|ductile|\bpews\b|\bpefws\b|\befws\b|\bawss\b|\bwater\b|pipe", name):
        return "water"
    if re.search(r"streetscape|safety|quick[- ]build|slow street|muni|transit|signal|bike|multimodal|traffic calm"
                 r"|turn on red|neighborway|road diet|pedestrian", text):
        return "street design"
    return "other"


# ===========================================================================
# D. Dates

PHASE_CONFLICT_SHOWN = re.compile(r"start date (has )?passed|past its (published )?start|still (in|listed as|shows?) "
                                  r"(planning|design)|phase (has )?not (been )?updated|date passed, in (design|planning)", re.I)


AUDIT_FINISHED_STATUS = re.compile(r"^(?:completed?|finished|closed|substantially complete|project evaluation)\b", re.I)


def department_status(ctx, p):
    """{"active": [...], "finished": [...]}: (source, status) pairs the row's own department publishes today.

    Read from the department's own source for the row: SFMTA's layer and
    project page for an SFMTA row, the coordination feed's rows for a feed
    job (and Public Works' page when the row links one), Public Works' page
    for a page row. Never from the row's notes."""
    out = {"active": [], "finished": []}

    def put(src, st):
        if st:
            out["finished" if AUDIT_FINISHED_STATUS.search(st) else "active"].append((src, st))

    dept = p["department"]
    if p["source"] == "sfmta":
        node = p["id"].split(":", 1)[1]
        lay = next((x for x in ctx.layer if str(x["node"]) == node), None)
        if lay:
            put("SFMTA layer", lay.get("phase"))
        pg = next((r for r in ctx.sitemap_pages if str(r.get("node")) == node
                   or (r.get("canonical") or "").rstrip("/").endswith("/" + node)), None) or {}
        put("SFMTA page", pg.get("phase"))
        if not pg.get("phase"):
            # The page's "Project Status" field, where its phase field is empty.
            put("SFMTA page Project Status", ((ctx.page_dates.get(str(pg.get("node"))) or {}).get("projectStatus")
                                              or [None])[-1])
        done = sfmta_page_finished(pg, ctx.today)
        if done:
            out["finished"].append(("SFMTA page", done))
    elif p["source"] == "dotmaps" and ctx.feed is not None:
        for pid in sorted(feed_ids_of(p)):
            for row in ctx.feed["jobs"].get(pid, [])[:1]:
                put("feed row %s status" % pid, row.get("project_status"))
                put("feed row %s phase" % pid, row.get("project_phase"))
    dpw_by_url = ctx.once("dpw_by_url", lambda: {r["url"]: r for r in ctx.dpw})
    if dept == "Public Works":
        for l in p["links"]:
            r = dpw_by_url.get(l["url"])
            if r:
                put("Public Works page", r.get("status"))
    # SFPUC's page for the row: its Project Phase line, as SFPUC's own list
    # (data/extract/sfpuc-projects/projects.json) read it. Bay Corridor
    # Transmission and Distribution Phase 4 prints "Construction End: Winter
    # 2026" and "Project Phase: Construction" (read 2026-09-29).
    puc_by_url = ctx.once("puc_by_url", lambda: {r["url"]: r for path in sorted(glob.glob(os.path.join(
        ROOT, "data", "extract", "sfpuc-projects", "*.json"))) for r in json.load(open(path)).get("records", [])})
    for l in p["links"]:
        r = puc_by_url.get(l["url"])
        if r:
            put("SFPUC page Project Phase", r.get("phase"))
    return out


PAST_END_SHOWN = re.compile(r"published end date, [^;]{4,40}, has passed", re.I)


@check("D1", "Missing, impossible, inconsistent dates",
       "Zero end-before-start. Zero past-end rows on a “current” list, apart from work the department still lists "
       "as active, on its page, its project layer or the coordination feed, which stays listed with its passed end date shown. Every phase-date conflict shown on the page.")
def d1(ctx, res):
    P = ctx.projects
    t = ctx.today_s
    end_before = [(p["name"], p["start"], p["end"]) for p in P if p["start"] and p["end"] and end_key(p["end"]) < start_key(p["start"])]
    past_all = [p for p in P if p["end"] and end_key(p["end"]) < t]
    # Every past-end row on the list counts. The audit reads each one's
    # department's current status itself, from the department's own source
    # (SFMTA's layer and page, the feed row, Public Works' page), never from
    # the note the pipeline writes on the row, and splits the count in two:
    # rows the department still lists active, which stay failures until
    # Bryan decides whether they belong on a current list, and rows it does
    # not, which should not be listed at all. Bryan decided on 2026-09-29
    # that the first kind stays listed, so it passes
    # when its page prints the passed end date and fails when it does not.
    past_active, past_end, past_active_hidden = [], [], []
    for p in past_all:
        st = department_status(ctx, p)
        row = (p["name"], p["department"], p["end"], "; ".join("%s: %s" % s for s in st["active"] + st["finished"])
               or "no status published")
        if st["active"] and not st["finished"]:
            past_active.append(row)
            if not PAST_END_SHOWN.search(ctx.project_detail(p["slug"]) or ""):
                past_active_hidden.append(row)
        else:
            past_end.append(row)
    conflict = [p for p in P if re.search(r"planning|design", p["phase"] or "", re.I) and p["start"] and start_key(p["start"]) < t]
    conflict_hidden = []
    for p in conflict:
        d = ctx.project_detail(p["slug"])
        if d is None or not PHASE_CONFLICT_SHOWN.search(d):
            conflict_hidden.append((p["name"], p["phase"], p["start"]))
    horizon = (ctx.today.replace(year=ctx.today.year + 8)).isoformat()
    far = [(p["name"], p["start"], p["end"]) for p in P
           if (p["start"] and start_key(p["start"]) > horizon) or (p["end"] and end_key(p["end"]) > horizon)]
    after_2032 = sum(1 for p in P if p["start"] and p["start"][:4] > "2032")
    future = [(p["name"], r["date"], r["label"], r["title"][:80]) for p in P for r in city_body_records(p)
              if r.get("date") and r["date"] > t]
    future_page = sum(1 for p in P for r in p["records"] if r.get("relation") == OWN_PAGE and (r.get("date") or "") > t)
    undated = sum(1 for p in P for r in p["records"] if not r.get("date"))
    nrec = sum(len(p["records"]) for p in P)
    res.measured = len(end_before) + len(past_active_hidden) + len(past_end) + len(conflict_hidden)
    res.denominator = f"{len(P)} listed rows: {len(end_before)} end before start, {len(past_all)} past end still " \
                      f"listed ({len(past_active)} the department still lists active, {len(past_active_hidden)} of " \
                      f"them without the passed end shown; {len(past_end)} it does not list active), " \
                      f"{len(conflict_hidden)} of {len(conflict)} phase-date conflicts not shown"
    res.facts.update(past_end=len(past_all), past_end_active=len(past_active), past_end_not_active=len(past_end))
    res.table(["Check", "Count"], [
        ("Missing start", sum(1 for p in P if not p["start"])),
        ("Missing end", sum(1 for p in P if not p["end"])),
        ("End before start", len(end_before)),
        ("End already passed, still listed; the department still lists it active", len(past_active)),
        ("… of those, the page does not show the passed end date", len(past_active_hidden)),
        ("End already passed, still listed; the department does not list it active", len(past_end)),
        ("Phase Planning or Design with start passed", len(conflict)),
        ("… of those, not shown as a conflict on the page", len(conflict_hidden)),
        (f"A date more than eight years out (after {horizon})", len(far)),
        ("Start after 2032 (the first run's cut)", after_2032),
        ("City-body record dated in the future", len(future)),
        ("Project-page item dated in the future", future_page),
        (f"Undated records, of {nrec}", undated),
    ])
    if past_end:
        res.table(["Past end, still listed, not active by its department", "Department", "End", "Department's status"],
                  past_end)
    if past_active:
        res.line(f"{len(past_active)} rows are past their published end while their department still lists them "
                 f"active. They stay listed, and pass when the page shows the passed end date (Bryan, 2026-09-29).")
        res.line()
        res.table(["Past end, department still lists active", "Department", "End", "Department's status"], past_active)
    if end_before:
        res.table(["End before start", "Start", "End"], end_before)
    res.table(["Phase-date conflict not shown", "Phase", "Start"], sorted(conflict_hidden, key=lambda r: r[2]), limit=15)
    if far:
        res.table(["More than eight years out", "Start", "End"], far)
    if future:
        res.table(["City-body record in the future", "Date", "Label", "Title"], future)
    for n, s, e in end_before:
        res.fail(n, f"end {e} before start {s}")
    for n, d, e, st in past_end:
        res.fail(n, f"end {e} passed, still listed; {d} does not list it active ({st})")
    for n, d, e, st in past_active_hidden:
        res.fail(n, f"end {e} passed, still listed as {d} lists it active ({st}), but the page does not show the passed end")
    for n, ph, s in conflict_hidden:
        res.fail(n, f"phase {ph} with start {s} passed; the page does not show the conflict")
    res.verdict(res.measured == 0)


D2_FIELDS = ["construction start", "construction end", "consultation start", "consultation end"]
D2_UNGRADABLE = {"no page", "not on page"}


@check("D2", "Dates are right (hand-graded)",
       "Over 95% correct on each of construction start, construction end, public consultation start and end, "
       "and over 95% on all other dates shown, over a random sample of at least 60 listed projects. The share is of "
       "dates a department page states; rows marked 'no page' or 'not on page' are left out.")
def d2(ctx, res):
    path = os.path.join(GRADES_DIR, "d2-dates.csv")
    rows = read_csv(path)
    if not rows:
        res.status = "NOT GRADED"
        res.line(f"No sample at {os.path.relpath(path, ROOT)}; run the audit once to write the template.")
        return
    # A sampled project no longer listed shows no dates to grade; its rows
    # stay in the file with their grades and are left out here, and the
    # template writer tops the sample up with listed projects.
    listed = {p["slug"] for p in ctx.projects}
    gone = sorted({r["project"] for r in rows if r["slug"] not in listed})
    rows = [r for r in rows if r["slug"] in listed]
    projects = {r["slug"] for r in rows}
    graded = [r for r in rows if (r.get("grade") or "").strip()]
    res.denominator = f"{len(graded)} graded of {len(rows)} dates on {len(projects)} listed projects"
    if gone:
        res.line(f"Sampled projects no longer listed, left out with their rows: {len(gone)} ({', '.join(gone)}).")
    by_dept = collections.defaultdict(lambda: [set(), set()])
    for r in rows:
        by_dept[r["department"]][0].add(r["slug"])
        if (r.get("department_page") or NO_DEPT_PAGE) == NO_DEPT_PAGE or not dept_link(r.get("department_page")):
            by_dept[r["department"]][1].add(r["slug"])
    res.line("Sampled projects with no department page to grade against (the date can only be checked against the "
             "row it was read from): " + ", ".join(f"{d} {len(v[1])} of {len(v[0])}" for d, v in sorted(by_dept.items())) + ".")
    if len(graded) < len(rows) or len(projects) < 60:
        res.status = "NOT GRADED"
        res.measured = f"{len(graded)} of {len(rows)} graded"
        res.line(f"{len(rows) - len(graded)} rows in {os.path.relpath(path, ROOT)} carry no grade yet. "
                 "Grade each row correct or wrong against the department's page; a correct “not published” is correct.")
        return
    # "no page" and "not on page" rows have nothing to grade against, so they sit
    # outside the shares and are counted beside them. "sources disagree" counts
    # as not correct: the date we show is not the one the department's page gives.
    kind = lambda r: r["grade"].strip().lower()
    ungradable = collections.Counter(kind(r) for r in graded if kind(r) in D2_UNGRADABLE)
    by = collections.defaultdict(lambda: [0, 0])
    for r in graded:
        if kind(r) in D2_UNGRADABLE:
            continue
        f = r["field"] if r["field"] in D2_FIELDS else "other dates"
        by[f][1] += 1
        by[f][0] += kind(r) == "correct"
    res.table(["Field", "Correct", "Graded", "Share"], [(f, v[0], v[1], pct(v[0], v[1])) for f, v in sorted(by.items())])
    res.line("Left out of the shares: " + ", ".join(f"{n} {k}" for k, n in sorted(ungradable.items()))
             + " (`no page`: the department publishes no page for the project; `not on page`: its page gives no date "
               "for that milestone, so the shown date came from a feed row).")
    for r in graded:
        if kind(r) not in D2_UNGRADABLE and kind(r) != "correct":
            res.fail(f"{r['project']} / {r['field']}",
                     f"{kind(r)}: shown {r['shown']}, department says {r.get('department_says')}")
    res.measured = ", ".join(f"{f} {pct(v[0], v[1])}" for f, v in sorted(by.items()))
    res.verdict(all(v[0] / v[1] > 0.95 for v in by.values()) and all(f in by for f in D2_FIELDS))


# ===========================================================================
# E. Geometry

def geom_counts(items, has_cnn, cl):
    """items: (id, cnn or None, lines). Counts the E1 and E2 defects."""
    c = collections.Counter()
    ex = collections.defaultdict(list)
    for iid, cnn, L in items:
        if not L or all(len(l) == 0 for l in L):
            c["empty"] += 1
            ex["empty"].append(iid)
            continue
        pts = [p for l in L for p in l]
        if not all(SF_BBOX[0] <= p[0] <= SF_BBOX[2] and SF_BBOX[1] <= p[1] <= SF_BBOX[3] for p in pts):
            c["outside SF"] += 1
            ex["outside SF"].append(iid)
        for l in L:
            if len(l) >= 2 and line_length(l) < 1:
                c["zero-length"] += 1
                ex["zero-length"].append(iid)
            if len(l) >= 4 and self_intersects(l):
                c["self-intersecting"] += 1
                ex["self-intersecting"].append(iid)
        if has_cnn and cl and not cnn:
            # Drawn but keyed to no block: it joins to no plan status and no reach.
            c["no CNN"] += 1
            ex["no CNN"].append(iid)
        elif has_cnn and cl and cnn:
            c["keyed"] += 1
            if cnn not in cl["lines"]:
                c["CNN not in centerline"] += 1
                ex["CNN not in centerline"].append(iid)
            else:
                if cl["active"].get(cnn) is False:
                    c["retired CNN"] += 1
                    ex["retired CNN"].append(iid)
                d = max_offset([p for l in L for p in l], cl["lines"][cnn])
                if d > 15:
                    c["over 15 m (50 ft)"] += 1
                    ex["over 15 m (50 ft)"].append((iid, round(d)))
                if d > 100:
                    c["over 100 m (330 ft)"] += 1
    return c, ex


def drawn_files(ctx):
    """The geometry the site draws, as (label, items, has_cnn)."""
    T = load("site/data/north-star/traced.geojson")["features"]
    S = load("site/data/bike-history/segments.json")["segments"]
    A = load("site/data/bike-history/all-ages.geojson")["features"]
    ST = load("site/data/sf-streets.json")
    return [
        ("site/data/north-star/traced.geojson (plan)", [(f["properties"]["cnn"], f["properties"]["cnn"], lines_of(f["geometry"])) for f in T], True),
        ("site/data/bike-history/segments.json (bikeway layer)", [(s["key"], s.get("cnn"), [s["pts"]]) for s in S], True),
        ("site/data/bike-history/all-ages.geojson", [(f["properties"].get("key"), f["properties"].get("cnn"), lines_of(f["geometry"])) for f in A], True),
        ("site/data/sf-streets.json (base map)", [(i, None, [l]) for i, l in enumerate(ST["lines"])], False),
        # A project drawn only as intersection points (`nodes`) is not an empty
        # shape, and a page SFMTA publishes but does not map holds no blocks
        # (geometryKind "none") and says so on its page; neither is tested here.
        ("site/data/coordination.json project geometry",
         [(p["name"], None, p["geometry"]) for p in ctx.projects
          if p["geometry"] or not (p.get("nodes") or (p.get("geometryKind") == "none" and p["blocks"] == 0))], False),
    ]


@check("E1", "Valid shapes",
       "Zero empty, zero-length, self-intersecting or out-of-city shapes in files the site draws.")
def e1(ctx, res):
    rows, total_bad = [], 0
    keys = ["empty", "outside SF", "zero-length", "self-intersecting"]
    for label, items, _ in ctx.once("drawn", lambda: drawn_files(ctx)):
        c, ex = geom_counts(items, False, None)
        bad = sum(c[k] for k in keys)
        total_bad += bad
        rows.append((label, len(items)) + tuple(c[k] for k in keys) + ("; ".join(str(x) for k in keys for x in ex[k][:3]) or "",))
        for k in keys:
            for x in ex[k]:
                res.fail(f"{label.split(' ')[0]}: {x}", k)
    G = ctx.layer_geo
    c, _ = geom_counts([(f["properties"]["node"], None, lines_of(f["geometry"])) for f in G], False, None)
    rows.append(("out/sfmta-projects/projects.geojson (raw layer, not drawn)", len(G)) + tuple(c[k] for k in keys) + ("",))
    res.measured = total_bad
    res.denominator = f"{sum(r[1] for r in rows[:-1])} features in {len(rows) - 1} drawn files"
    res.line(f"Outside SF means a vertex outside {SF_BBOX[0]} to {SF_BBOX[2]}, {SF_BBOX[1]} to {SF_BBOX[3]}. "
             "Zero-length is under 1 m (3 ft). Lines over 400 segments are not tested for self-intersection.")
    res.line()
    res.table(["File", "Features"] + keys + ["Examples"], rows)
    res.verdict(total_bad == 0)


@check("E2", "Lines up with the street grid",
       "Zero segments more than 15 m (50 ft) from their CNN's centerline in files the site draws.")
def e2(ctx, res):
    cl = ctx.centerline
    if cl is None:
        res.status = "NOT MEASURED"
        res.line("No full centerline pull (3psu-pn9h) in data/socrata-cache/.")
        return
    rows, over, keyed, nocnn = [], 0, 0, 0
    worst, unkeyed = [], []
    for label, items, has_cnn in ctx.once("drawn", lambda: drawn_files(ctx)):
        if not has_cnn:
            continue
        c, ex = geom_counts(items, True, cl)
        over += c["over 15 m (50 ft)"]
        keyed += c["keyed"]
        nocnn += c["no CNN"]
        f = label.split(" ")[0]
        worst += [(f, i, d) for i, d in ex["over 15 m (50 ft)"]]
        unkeyed += [(f, i) for i in ex["no CNN"]]
        rows.append((label, len(items), c["keyed"], c["no CNN"], c["over 15 m (50 ft)"], c["over 100 m (330 ft)"],
                     c["retired CNN"], c["CNN not in centerline"]))
        for i, d in ex["over 15 m (50 ft)"]:
            res.fail(f"{f}: {i}", f"{d} m ({fmt_dist(d)}) from its CNN's centerline")
    # Project CNNs that miss a plan block because the block was split into new CNNs.
    plan = set(ctx.plan)
    by_base = collections.defaultdict(set)
    for c in plan:
        by_base[int(c) // 1000].add(c)
    split_all = {c for p in ctx.record.values() for c in p.get("cnns") or []
                 if c not in plan and c.isdigit() and by_base.get(int(c) // 1000)}
    split_listed, split = set(), set()
    for p in ctx.projects:
        held = all_cnns(ctx, p)
        for c in held - plan:
            if not c.isdigit() or not by_base.get(int(c) // 1000):
                continue
            split_listed.add(c)
            if by_base[int(c) // 1000] - held:
                split.add(c)
    res.measured = f"{over} over 15 m (50 ft); {nocnn} drawn features carry no CNN"
    res.denominator = f"{keyed} keyed features in {len(rows)} drawn files ({keyed + nocnn} drawn; the {nocnn} with no CNN " \
                      f"cannot be tested and are not in the denominator)"
    res.facts.update(over=over, keyed=keyed, nocnn=nocnn)
    res.line(f"Centerline: DataSF 3psu-pn9h, cache fetched {cl['fetched_on']}. The distance is the largest from any vertex "
             "to the CNN's centerline.")
    res.line(f"{nocnn} drawn features carry no CNN. They draw on the map but join to no plan block and no reach figure, "
             "so the pass line cannot test them; they are listed below rather than counted as aligned.")
    res.line()
    res.table(["File", "Features", "Keyed", "No CNN", "Over 15 m (50 ft)", "Over 100 m (330 ft)", "Retired CNN",
               "CNN not in centerline"], rows)
    res.table(["File", "Feature", "Largest distance"],
              [(f, i, "%d m (%s)" % (d, fmt_dist(d))) for f, i, d in sorted(worst, key=lambda w: -w[2])], limit=15)
    res.table(["File", "Drawn feature with no CNN"], unkeyed, limit=40)
    # The distance test passes by construction for a row the snapper moved,
    # because its line is redrawn on the block it chose. A second route that
    # uses no geometry: SFMTA's own street name and both typed cross streets
    # against the centerline's (pipeline/transportation-geometry-check.py).
    import importlib.util
    gc = paths.load("transportation-geometry-check.py", "geomcheck")
    xc, contra, _ = gc.cross_street_counts()
    res.facts.update(cross_contradictions=len(contra))
    res.line(f"Cross streets of the {sum(xc.values())} re-keyed bikeway rows, no geometry used: {xc['new']} match the new "
             f"blocks, {xc['one of two new']} match on one of two, {xc['old only']} match only the typed block, "
             f"{xc['neither']} match neither, {xc['no cross streets']} have none. Contradictions (street name and both cross "
             f"streets describe the typed active block the row was moved off): {len(contra)}.")
    for e in contra:
        res.fail(f"bikeway row {e['oid']}", f"{e['street']} {e['from']} -> {e['to']} typed {e['cnn']}, moved to "
                 + ", ".join(c or "unkeyed" for c in e["to_cnns"]))
    res.line(f"Split blocks: {len(split_all)} distinct CNNs across all {len(ctx.record)} project records are not plan "
             f"blocks but share a base number with one (e.g. 300000 against plan blocks 300001–300003). {len(split_listed)} "
             f"are held by listed projects, and for {len(split)} of those the project does not also hold the plan block, "
             f"so that block drops out of its plan miles.")
    res.verdict(over == 0 and not contra)


def fmt_dist(m):
    ft = m / FT
    return "%.1f mi" % (m / MILE) if ft >= 2640 else "%d ft" % round(ft, -1)


@check("E3", "The map shows the whole project",
       "Every block held is drawn, on every project.")
def e3(ctx, res):
    held = drawn = 0
    under_half, short = 0, []
    for p in ctx.projects:
        # Blocks are drawn as lines and intersections as points (`nodes`).
        h, d = p["blocks"], len(p["geometry"] or []) + len(p.get("nodes") or [])
        held += h
        drawn += min(d, h)
        if d < h:
            short.append((p["name"], d, h, pct(d, h)))
            if d * 2 < h:
                under_half += 1
    res.measured = f"{drawn} of {held} blocks drawn ({pct(drawn, held)}); {under_half} maps under half, {len(short)} short of any block"
    res.denominator = f"{len(ctx.projects)} project maps"
    res.line(f"{under_half} of {len(ctx.projects)} maps draw fewer than half their blocks. A block is drawn when the "
             "project's geometry carries a line for it, and an intersection when it carries a point.")
    res.line()
    res.table(["Project", "Drawn", "Held", "Share"], sorted(short, key=lambda s: s[1] / s[2] if s[2] else 1), limit=20)
    for n, d, h, s in short:
        res.fail(n, f"draws {d} of {h} blocks ({s})")
    res.verdict(not short)


# ===========================================================================
# F. Across pages

# A metric distance: a number with a metric unit, or the word metres or
# kilometres. "Meter" alone is a parking meter ("GENERAL METER PARKING").
# The abbreviations are lower case only: "2023 M Ocean View" is a Muni line.
METRIC = re.compile(r"\b\d[\d,.]*\s?(?:m|km|[Mm]etres?|[Mm]eters?|[Kk]ilometres?|[Kk]ilometers?)\b|\b[Mm]etres\b|\b[Kk]ilomet")


# A length in miles on a rendered page. Not a walking distance ("1/4 mile")
# and not a quoted travel figure ("12.4 miles a person a day").
MI_FIGURE = re.compile(r"(?<![\d/.])(\d[\d,]*(?:\.\d+)?)\s?(?:mi|miles?)\b(?!\s+(?:a person|traveled))", re.I)
# Which data file each page's mile figures come from (the page modules under
# site/src/pages/). f1 measures each file's miles against the bikeway layer
# and the plan's map (mile_reference); a "mileBasis" label decides nothing.
# About the data is where the basis is explained, so its own figures are not
# counted.
MILE_PAGES = [
    (r"^transportation/bike/index\.html$", "Overview", "site/data/bike-history/history.json", None),
    (r"^transportation/bike/departments/index\.html$", "Better Coordination", "site/data/department-overlap.json", None),
    (r"^transportation/bike/projects/", "Current Projects and project pages", "site/data/coordination.json", None),
]


@check("F1", "Units",
       "Zero metric units shown. One mile basis across every page and chart, and the About page says which.")
def f1(ctx, res):
    pages = ctx.rendered_pages()
    metric, figures = [], collections.defaultdict(list)
    for path in pages:
        rel = os.path.relpath(path, ctx.dist)
        h = open(path, encoding="utf-8").read()
        t = visible_text(h, charts=True)
        for m in METRIC.finditer(t):
            metric.append((rel, t[max(0, m.start() - 40):m.end() + 20]))
        if rel.startswith("transportation/bike/about/"):
            continue
        # A project page repeats the whole list beside its own detail (each row
        # printing its plan miles since 2026-09-29), so only its detail section
        # is counted there; the list's figures count once, on the list page.
        if re.match(r"^transportation/bike/projects/[^/]+/index\.html$", rel):
            d = re.search(r'<section class="coord-detail".*?</section>', h, re.S)
            t = visible_text(d.group(0), charts=True) if d else ""
        for m in MI_FIGURE.finditer(t):
            group = next((g for rx, g, _, _ in MILE_PAGES if re.match(rx, rel)), "unmapped: " + rel)
            figures[group].append((rel, m.group(0)))

    # Measured, not declared. Every file a page takes miles from is compared,
    # block for block, with miles measured here from the bikeway layer and the
    # plan's map (mile_reference). A file counting centerline miles, two rows
    # where the layer holds three, or a whole block where the plan covers part
    # of it disagrees; a label in the file decides nothing.
    ref = ctx.miles_ref
    if "missing" in ref:
        res.status = "NOT MEASURED"
        res.line("Not measured: " + ref["missing"] + ", so there is no source to measure against.")
        return
    tol = lambda want: max(2.0, 0.01 * want)  # noqa: E731

    def plan_tol(r):
        """A plan block's metres carry two measures of where the plan's line
        stops, the pipeline's and this one, each good to PLAN_TOL_M at an end."""
        return tol(r["m"]) + 2 * PLAN_TOL_M * (r["whole"] / r["L"] if r["L"] else 1)

    def plan_want(c):
        r = ref["plan"].get(c)
        return r if r and r["member"] else None

    def not_drawn(c):
        r = ref["plan"].get(c)
        return ("0 ft: the map's line spans %.0f%% of the block and runs along %.0f%% of it" % (100 * r["extent"], 100 * r["drawn"])
                if r else "0 ft: the map draws no line along the block")
    rows, disagree = [], collections.defaultdict(list)

    # Overview: history's per-block row miles (components.json) against the layer.
    comp = load("site/data/bike-history/components.json")
    n = 0
    for c, e in comp["blocks"].items():
        got = sum((e.get("m") or {}).values()) * MILE
        if not got or cnn_key(c) not in ref["rows_m"]:
            continue
        n += 1
        want = ref["rows_m"][cnn_key(c)]
        if abs(got - want) > tol(want):
            disagree["Overview"].append((f"block {c}", "%.0f ft" % (got / FT), "%.0f ft" % (want / FT)))
    hist = load("site/data/bike-history/history.json")
    latest = next((r for r in hist["rows"] if r["year"] == comp["year"]), {})
    rows.append(("Overview", "history.json, components.json", n, len(disagree["Overview"]),
                 "%s mi in %s; the layer's rows measure %.1f mi (the rest is work SFMTA's project pages report built)"
                 % (latest.get("network_miles"), comp["year"], ref["layer_total_m"] / MILE)))

    # Plan blocks: status.json (the explorer and Better Coordination read it) and the repave lever.
    # Which blocks are the plan's, and how much of each, is measured here from
    # the map PDF (plan_map_reference), not read from the trace.
    st = {cnn_key(b["cnn"]): b for b in load("site/data/north-star/status.json")["blocks"]}
    members = {c for c, r in ref["plan"].items() if r["member"]}
    bad_share, bad_absent, bad_extra = [], [], []
    for c, b in sorted(st.items()):
        r = plan_want(c)
        if r is None:
            bad_absent.append((f"status.json block {c} {b['street']}", "%.0f ft" % (b["m"] / FT), not_drawn(c)))
        elif abs(b["m"] - r["m"]) > plan_tol(r):
            bad_share.append((f"status.json block {c} {b['street']}", "%.0f ft" % (b["m"] / FT),
                              "%.0f ft (the map draws %.0f%% of it)" % (r["m"] / FT, 100 * r["share"])))
    names = (ctx.centerline or {}).get("street") or {}
    street_of = {cnn_key(k): v for k, v in names.items()}
    for c in sorted(members - set(st)):
        r = ref["plan"][c]
        bad_extra.append((f"block {c} {street_of.get(c) or ''}".strip(), "not in status.json",
                          "%.0f ft (the map draws %.0f%% of it)" % (r["m"] / FT, 100 * r["share"])))
    disagree["Better Coordination"] += bad_share + bad_absent + bad_extra
    st_total = sum(b["m"] for b in st.values())
    ref_total = sum(ref["plan"][c]["m"] for c in members)
    partial = sum(1 for c in members if ref["plan"][c]["share"] < 1)
    res.facts.update(plan_status_mi=round(st_total / MILE, 1), plan_map_mi=round(ref_total / MILE, 1),
                     plan_share_bad=len(bad_share), plan_absent=len(bad_absent), plan_extra=len(bad_extra))
    rows.append(("Plan blocks, how much of each", "north-star/status.json", len(set(st) & members), len(bad_share),
                 "the map's line stops partway along %d blocks" % partial))
    rows.append(("Plan blocks the map does not draw", "north-star/status.json", len(st), len(bad_absent), ""))
    rows.append(("Blocks the map draws that status.json lacks", "north-star/status.json", len(members), len(bad_extra), ""))
    rows.append(("Plan network, in all", "north-star/status.json", "%d blocks" % len(st), "%+.1f mi" % ((st_total - ref_total) / MILE),
                 "status.json %.1f mi; the map measures %.1f mi on %d blocks" % (st_total / MILE, ref_total / MILE, len(members))))
    lever = load("site/data/repave-lever.json")["sinceAdoption"]["blocks"]
    n, bad = 0, 0
    for x in lever:
        c = cnn_key(x["cnn"])
        r = plan_want(c)
        n += 1
        if r is None or abs(x["miles"] * MILE - r["m"]) > plan_tol(r):
            bad += 1
            disagree["Better Coordination"].append((f"repave-lever.json block {x['cnn']} {x['street']}", "%.0f ft" % (x["miles"] * MILE / FT),
                                                    not_drawn(c) if r is None else "%.0f ft (the map draws %.0f%% of it)" % (r["m"] / FT, 100 * r["share"])))
    rows.append(("Repave lever", "repave-lever.json", n, bad, "repaved plan blocks since adoption"))

    # Current Projects: each project's plan miles against its blocks measured here.
    n, bad = 0, 0
    for p in ctx.projects:
        if not p.get("planCnns"):
            continue
        n += 1
        want = project_plan_miles(ctx, p)
        slack = sum(plan_tol(r) for r in (plan_want(cnn_key(c)) for c in p["planCnns"]) if r) / MILE
        shown = p.get("planMiles") or 0
        if not (abs(shown - want) <= max(0.051 * want, 0.006, slack) or shown == float("%.2g" % want)):
            bad += 1
            disagree["Current Projects and project pages"].append((p["name"], "%s mi" % shown, "%.2f mi" % want))
    rows.append(("Current Projects", "coordination.json planMiles", n, bad, "projects with plan blocks"))

    groups = {"Overview": "Overview", "Better Coordination": "Better Coordination",
              "Current Projects and project pages": "Current Projects and project pages"}
    in_use = collections.Counter()
    for group, figs in figures.items():
        if not figs:
            continue
        # Every mapped page's file is written per direction (mile_basis.BASIS);
        # what varies is whether its figures agree with the source measure.
        if group.startswith("unmapped"):
            in_use["unmapped: " + group] += len(figs)
        elif disagree.get(groups.get(group, group)):
            in_use["per direction, but the file disagrees with the layer and the map: " + group] += len(figs)
        else:
            in_use["per direction"] += len(figs)
    about = ctx.page_text("transportation/bike/about/index.html") or ""
    says = stated_basis(ctx)
    names_share = bool(re.search(r"stops partway along a block", about, re.I))
    nfig = sum(len(v) for v in figures.values())
    nbad = sum(len(v) for v in disagree.values())
    bases = {"per direction" if k.startswith("per direction") else k for k in in_use}
    off = sum(v for k, v in in_use.items() if k != "per direction")
    res.facts.update(bases=len(bases), figures=nfig, metric=len(metric), disagree=nbad, figures_off=off)
    res.measured = (f"{len(metric)} metric units; {len(bases)} mile basis{'' if len(bases) == 1 else 'es'} "
                    f"({', '.join(sorted(bases))}); {off} of {nfig} mi figures on pages whose file disagrees with the "
                    f"layer and the map; {nbad} blocks or projects off")
    res.denominator = f"{len(pages)} rendered pages" if pages else "site not built"
    fit = ref["fit"]
    res.line("Every file a page takes miles from is measured, block for block, against the bikeway layer's own row lengths "
             "(data/extract/sfmta-bikeway/, measured here) and the street centerline where the layer has no row. Plan "
             "blocks are measured from SFMTA's North Star map PDF itself: its drawn lines, fitted here to today's street "
             "centerline (%.1f m median registration error), projected onto every block they run along within %.0f m. A "
             "block is the plan's when the drawn line spans half of it and runs along half its length, and it counts the "
             "part the line spans, reaching an end within %.0f m. The trace the pipeline uses is not read. A tolerance of "
             "1%% or 2 m per block, plus %.0f m of block where the two measures place the line's end; two significant "
             "figures per project. Every “N mi” on a rendered page takes the verdict of its page's file. About the data "
             "explains the basis, so its own figures are not counted."
             % (fit.get("median_resid_m", 0), PLAN_TOL_M, PLAN_TOL_M, 2 * PLAN_TOL_M))
    try:
        traced_sha = load("site/data/north-star/georeference.json").get("map_sha256")
    except FileNotFoundError:
        traced_sha = None
    res.line("Map PDF read here: sha256 %s…; %s." % (ref["map_sha256"][:12],
             "the same file the pipeline's trace read" if traced_sha == ref["map_sha256"] else
             "the pipeline's trace records no hash" if not traced_sha else "NOT the file the pipeline's trace read (%s…)" % traced_sha[:12]))
    ap = ctx.appendix_l
    named = ap["named"]
    by_name = sum(1 for c in members if ref["plan"][c].get("by") == "Appendix L and the map")
    named_drawn = sum(1 for c in named if c in members)
    res.line("The plan's own definition of its network: Appendix L says “%s” (%s in the appendix read here, sha256 %s…). "
             "So which blocks are the plan's is decided by the map. Appendix L is read here from the appendix PDF (%d rows, "
             "%d placed on the centerline by this audit's own walk, %d not placed), and a block it names with a facility "
             "counts where the map draws a line along it within %.0f m (%d ft) instead of %.0f m, since the hand-drawn line "
             "sits off some named streets: %d of the %d plan blocks here come in that way. Of the %d blocks Appendix L names "
             "with a facility, the map draws %d; the other %d are left out, as the plan says."
             % (APPENDIX_L_DEFERS, "still printed" if ap["defers"] else "NOT found", ap["sha256"][:12], ap["rows"],
                ap["placed"], len(ap["unplaced"]), NAMED_TOL_M, round(NAMED_TOL_M / FT), PLAN_TOL_M, by_name, len(members),
                len(named), named_drawn, len(named) - named_drawn))
    res.facts.update(appendix_rows=ap["rows"], appendix_named=len(named), appendix_named_drawn=named_drawn,
                     plan_by_name=by_name)
    res.line()
    res.table(["What", "File", "Compared", "Disagree", "Note"], rows)
    res.table(["Basis in use", "mi figures"], in_use.most_common())
    res.line(f"About the data states the basis: {says or 'no'}; says a block counts only its part where the plan's line stops partway: {'yes' if names_share else 'no'}. "
             f"{ref['aliased']} CNN-less path rows were placed on a block by their ends.")
    for group, items in sorted(disagree.items()):
        res.table(["%s: block or project" % group, "Shown", "Measured from the layer and the map"], items, limit=25)
    if metric:
        res.table(["Page", "Context"], metric, limit=20)
    for rel, ctxt in metric:
        res.fail(rel, "metric unit: " + ctxt)
    for group, items in disagree.items():
        for what, got, want in items:
            res.fail(what, f"shows {got}; the layer and the map measure {want}")
    for label in in_use:
        if label != "per direction":
            res.fail(label, f"{in_use[label]} mi figures")
    if says != "per direction":
        res.fail("About the data", "does not state that miles are counted per direction of travel")
    if not names_share:
        res.fail("About the data", "does not say a plan block counts only its part where the plan's line stops partway along it")
    if not ap["defers"]:
        res.fail("Appendix L", "no longer says to defer to the map, so the map may not define the network")
    if not pages:
        res.status = "NOT MEASURED"
        return
    res.verdict(not metric and not nbad and list(in_use) == ["per direction"] and says == "per direction" and names_share
                and ap["defers"])


@check("F2", "Denominators",
       "One resident total, or each one labelled with its source where it is used.")
def f2(ctx, res):
    # The totals, from the census extracts themselves: the 2020 census block
    # count, and each American Community Survey five-year release summed over
    # its block groups. A figure on a page equal to one of them is that total.
    from extract import Extract
    b20 = Extract("census-blocks").read("2020")
    acs = Extract("census-blocks").read("acs5-bg")
    totals = {}
    if b20 is not None:
        totals[int(round(sum(r["pop"] for r in b20.records)))] = ("2020 census", r"\b2020 census\b|\bcensus\b")
    if acs is not None:
        by_year = collections.Counter()
        for r in acs.records:
            by_year[r["year"]] += r["pop"]
        for y, v in by_year.items():
            totals.setdefault(int(round(v)), ("%d–%d American Community Survey" % (y - 4, y), r"American Community Survey|\bACS\b"))
    if not ctx.dist:
        res.status = "NOT MEASURED"
        res.measured, res.denominator = "—", "site not built"
        return
    # Every use of a total on a rendered transportation page, and the sentence
    # it sits in. A sentence that names the right source labels it; one that
    # calls an ACS estimate a year's population, or names no source, does not.
    uses = collections.defaultdict(list)  # total -> [(page, sentence, ok)]
    for path in ctx.rendered_pages():
        rel = os.path.relpath(path, ctx.dist)
        t = ctx.page_text(rel) or ""
        for v, (label, rx) in totals.items():
            for m in re.finditer(r"(?<![\d,])%s(?![\d,])" % re.escape("{:,}".format(v)), t):
                a = max(t.rfind(". ", 0, m.start()), t.rfind("? ", 0, m.start()), 0)
                e = t.find(". ", m.end())
                sent = t[a:e if e > 0 else m.end() + 200].strip(". ")
                ok = bool(re.search(rx, sent, re.I))
                if ok and "American Community Survey" in label and re.search(r"\b\d{4} population\b", sent) \
                        and not re.search(r"American Community Survey|\bACS\b", sent):
                    ok = False
                uses[v].append((rel, sent[:220], ok))
    # Project pages count residents reached against 2020 census blocks; each
    # count must say so, since the page names no total.
    reach_pages = [(os.path.relpath(p, ctx.dist), ctx.page_text(os.path.relpath(p, ctx.dist)) or "")
                   for p in ctx.rendered_pages() if "/projects/" in p]
    reach_pages = [(rel, t) for rel, t in reach_pages if re.search(r"[\d,]+ residents", t)]
    reach_bad = [rel for rel, t in reach_pages if not re.search(r"[\d,]+ residents \(2020 census\)", t)]
    used = {v for v, u in uses.items() if u}
    bad = [(v, rel, sent) for v, u in uses.items() for rel, sent, ok in u if not ok]
    res.measured = len({totals[v][0] for v in used} | ({"2020 census"} if reach_pages else set()))
    res.denominator = "resident totals used as a denominator, found on %d rendered pages" % len(ctx.rendered_pages())
    res.line("Each resident total is summed here from the census extracts (data/extract/census-blocks/), and every "
             "place a rendered transportation page prints one, About the data included, must name that total's "
             "source in the same sentence.")
    res.table(["Total", "Source (summed from the extract)", "Printed", "Labelled"],
              [("{:,}".format(v), totals[v][0], len(uses[v]), sum(1 for _, _, ok in uses[v] if ok)) for v in sorted(used)]
              + [("counts of residents reached", "2020 census blocks", len(reach_pages), len(reach_pages) - len(reach_bad))])
    if bad:
        res.table(["Page", "Sentence", "Should name"], [(rel, sent, totals[v][0]) for v, rel, sent in bad], limit=20)
    for v, rel, sent in bad:
        res.fail(f"{rel}: {v:,}", f"does not name the {totals[v][0]}")
    for rel in reach_bad:
        res.fail(rel, "residents reached without “(2020 census)”")
    # Project pages count against the 2020 census blocks, so the census is a
    # total in use wherever a page gives residents reached, printed or not.
    in_use = {totals[v][0] for v in used} | ({"2020 census"} if reach_pages else set())
    res.verdict(len(in_use) <= 1 or (not bad and not reach_bad))


DOC_SOURCES = {"sfmta-hearings", "sfmta-board", "sfpuc-commission", "sfmta-pages", "dpw-projects"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
TYPED_ASOF = re.compile(r"(updated|as of|through|current to|last edited)\s+(?:only\s+)?(?:through\s+)?(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I)


@check("F3", "Freshness",
       "Every source within its horizon (90 days for a live dataset, 180 for a document), and no hard-coded “as of” "
       "text that disagrees with the data.")
def f3(ctx, res):
    rows = []
    # The date each source was last checked, by pipeline/transportation-update.py
    # and the refreshers it runs. An incremental read keeps the old "read" date
    # while the data is unchanged, so the read date alone would expire a source
    # that was confirmed current yesterday. Age runs from the later of the two.
    from lib import pipeline_state
    checks = pipeline_state.load()

    def add(name, kind, date, key=None, horizon=None):
        if not date:
            return
        c = checks.get(key or "", {})
        failed = c.get("status") == "failed"
        # A failed check does not count; the last one that succeeded does.
        checked = (c.get("last_good") or "" if failed else c.get("checked", ""))[:10]
        if failed:
            # The refresh did not reach everything it is bound to re-read. The
            # file may still have been rewritten with what it did reach, so its
            # read date says nothing about the rest: age from the last check
            # that succeeded, or from the read date when none ever did.
            basis = checked or date[:10]
        else:
            basis = max(date[:10], checked) if checked else date[:10]
        age = (ctx.today - dt.date.fromisoformat(basis)).days
        horizon = horizon or (180 if kind == "document" else 90)
        rows.append((name, kind, date[:10], (checked or "—") + (" (last refresh failed)" if failed else ""),
                     age, horizon, "ok" if age <= horizon else "EXPIRED"))

    def fxf_key(s):
        m = re.search(r"/d/([a-z0-9]{4}-[a-z0-9]{4})", s.get("dataset") or s.get("url") or "")
        return "socrata:" + m.group(1) if m else None
    add("Coordination feed btxj-k9uh", "dataset", ctx.coord["feed"]["queried"], "socrata:btxj-k9uh")
    for k, s in ctx.coord["reach"]["sources"].items():
        add("Reach: " + k, "dataset", s.get("queried"), fxf_key(s) or {"schools": "release:cde-schools"}.get(k))
    add("Bikeway layer (reach network)", "dataset", ctx.coord["reach"].get("networkQueried"), "arcgis:sfmta-bikeway")
    tr = load("site/data/transportation.json")
    add("transportation.json collector", "dataset", tr.get("queriedAt"), "step:collect-transportation")
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "extract", "*", "*.json"))):
        src = os.path.basename(os.path.dirname(f))
        try:
            fo = json.load(open(f)).get("fetched_on")
        except Exception:  # noqa: BLE001
            continue
        add("data/extract/%s/%s" % (src, os.path.basename(f)), "document" if src in DOC_SOURCES else "dataset", fo,
            "extract:" + src)
    if ctx.centerline:
        add("Centerline 3psu-pn9h (full pull)", "dataset", ctx.centerline["fetched_on"], "socrata:3psu-pn9h")
    # The Street Safety map and the injury pages' crash reads (tools/street-safety/street-safety-crashes.py) and the map's own read
    # date, on the daily interval the scheduled run keeps. A crash
    # table's date is its last good rowsUpdatedAt check; the map's is its meta.read, aged from the map step's last run,
    # since a rebuild with no new rows keeps the read date by design.
    # Only on a host that runs the pipeline (sources.json present); a marker missing there reads as never checked.
    if checks:
        for fxf in ("nwes-mmgh", "8gtc-pjc6", "ubvf-ztfx", "dau3-4s8f"):
            c = checks.get("crashes:" + fxf) or {}
            add("Street Safety crash reads " + fxf, "dataset", c.get("last_good") or c.get("checked") or "2000-01-01",
                "crashes:" + fxf, horizon=1)
        ssm = load("site/data/street-safety/map.json").get("meta", {})
        # A map build skipped because its inputs were unchanged records nothing of its own; the scheduled run that
        # skipped it checked it, as pipeline/refresh-freshness.py counts it. A failed map build ages from its last good run.
        step, run = checks.get("step:street-safety-map") or {}, checks.get("run:scheduled") or {}
        key = ("run:scheduled" if step.get("status") != "failed" and run.get("checked", "") > step.get("checked", "")
               else "step:street-safety-map")
        add("Street Safety map (site/data/street-safety/map.json)", "dataset", ssm.get("read") or "2000-01-01", key,
            horizon=1)
    expired = [r for r in rows if r[6] != "ok"]
    # Typed "as of" text in the prose the pages render.
    layer_asof = tr.get("bikewayLayerAsOf") or tr.get("validThrough")
    typed = []
    for f in CONTENT_FILES:
        text = open(os.path.join(ROOT, f), encoding="utf-8").read()
        for m in TYPED_ASOF.finditer(text):
            ym = "%s-%02d" % (m.group(3), MONTHS.index(m.group(2).lower()) + 1)
            ctxt = text[max(0, m.start() - 120):m.end()]
            about_layer = bool(re.search(r"layer|bikeway", ctxt, re.I))
            agrees = (layer_asof or "")[:7] == ym if about_layer else None
            typed.append((f, m.group(0), ym, layer_asof if about_layer else "—",
                          "agrees" if agrees else "DISAGREES" if about_layer else "typed, no data date to compare"))
    disagree = [t for t in typed if t[4] == "DISAGREES"]
    meta = os.path.join(CACHE_DIR, "metadata.json")
    res.measured = len(expired) + len(disagree)
    res.denominator = f"{len(rows)} source dates and {len(typed)} typed “as of” phrases"
    res.table(["Source", "Kind", "Read", "Last checked", "Days old", "Horizon", "Result"],
              sorted(rows, key=lambda r: r[4], reverse=True))
    if not checks:
        res.line("No source checks recorded (data/pipeline-state/sources.json is absent): ages run from "
                 "the read date. Run pipeline/transportation-update.py to record them.")
    newer = sorted((k, v.get("detail")) for k, v in checks.items() if v.get("status") == "newer-release")
    for k, d in newer:
        res.line("Newer release not adopted: %s — %s" % (k, d))
    # A source whose own data has run out (a transit feed past its calendar's
    # end) and that has published nothing later: the copy is current with the
    # source and still out of date.
    for k, d in sorted((k, v.get("detail")) for k, v in checks.items() if v.get("status") == "stale"):
        res.line("Source past its own end date, nothing newer published: %s — %s" % (k, d))
    res.table(["Content file", "Typed text", "Says", "Data says", "Result"], typed)
    if os.path.exists(meta):
        m = json.load(open(meta))
        res.line("Publisher's own last update (data/audit/cache/metadata.json, %s): %s" %
                 (m.get("fetched_on"), ", ".join("%s %s" % (k, v) for k, v in m.get("updated", {}).items())))
    else:
        res.line("The publisher's own last-updated dates were not read (run --refresh).")
    for r in expired:
        res.fail(r[0], f"{r[1]} read {r[2]}, last checked {r[3]}, {r[4]} days old, past its {r[5]}-day horizon")
    for t in disagree:
        res.fail(f"{t[0]}: {t[1]}", f"says {t[2]}, the data says {t[3]}")
    res.verdict(not expired and not disagree)


# The departments page was folded into the overview in be38ab2; its content
# file is gone.
CONTENT_FILES = ["site/content/transportation.md", "site/content/transportation-about.md",
                 "site/content/transportation-projects.md"]
FIGURE = re.compile(r"(?<![\w{.$/#-])(\d[\d,]*(?:\.\d+)?\s?%|\d[\d,]*(?:\.\d+)?\s(?:mi\b|miles?|residents|projects|project pages|"
                    r"jobs|feed jobs|blocks|streets|hearings|meetings|items|schools|branches)|"
                    r"only \d+ of|\d+ of the \d+)", re.I)


def typed_figures():
    """Figures typed into the rendered pages' prose: outside {{ placeholders }}, link targets and tags."""
    out = []
    for f in CONTENT_FILES:
        raw = open(os.path.join(ROOT, f), encoding="utf-8").read()
        text = re.sub(r"\{\{.*?\}\}", " ", raw)
        text = re.sub(r"\]\([^)]*\)", "]", text)
        text = re.sub(r"<[^>]+>", " ", text)
        for m in FIGURE.finditer(text):
            out.append((f, m.group(0).strip(), re.sub(r"\s+", " ", text[max(0, m.start() - 60):m.end() + 40]).strip()))
    return out


@check("F4", "Traceability",
       "Every headline figure reaches a source row. Zero typed figures that the data could supply.")
def f4(ctx, res):
    verdicts = read_csv(TYPED_FIGURES)

    def verdict(f, fig, context):
        for r in verdicts:
            if r["file"].strip() == f and r["figure"].strip() == fig and r["context"].strip().lower() in context.lower():
                return r["verdict"].strip().lower(), (r.get("note") or "").strip()
        return None, ""
    typed = typed_figures()
    rows, bad = [], 0
    for f, fig, context in typed:
        v, note = verdict(f, fig, context)
        if v != "external":
            bad += 1
        rows.append((f.replace("site/content/", ""), fig, v or "UNCLASSIFIED", note or context[:100]))
    traces = f4_traces(ctx)
    unreached = [t for t in traces if t[3] != "reaches"]
    traced = {(TRACE_PAGE[t[0]], t[1].rstrip("%")) for t in traces}
    heads = headline_figures(ctx)
    untraced = [h for h in heads if (h[0], h[1].rstrip("%")) not in traced]
    res.measured = (f"{bad} typed figures the data could supply or unclassified; {len(unreached)} of {len(traces)} "
                    f"traces fail; {len(untraced)} of {len(heads)} headline figures untraced")
    res.denominator = (f"{len(typed)} typed figures in {len(CONTENT_FILES)} content files; {len(heads)} headline "
                       f"figures on the section pages")
    res.line("A typed figure is classified in data/audit/typed-figures.csv (file, figure, a few words of its context, "
             "verdict, note) as external (a quote of a source the data does not hold) or data (the data could supply "
             "it). Only external passes; an unclassified figure fails until someone classifies it.")
    res.line()
    res.table(["Traced figure", "Page shows", "Data says", "Result"], traces)
    res.table(["Content file", "Typed figure", "Verdict", "Note or context"], rows)
    for f, fig, v, note in rows:
        if v != "external":
            res.fail(f"{f}: {fig}", f"{v}: {note}")
    for t in unreached:
        res.fail(t[0], f"page shows {t[1]}, data says {t[2]}")
    res.line("A headline figure is a number between a section page's h1 and its first subheading, list, table or chart, "
             "years and dates left out. "
             "One with no trace in f4_traces fails until a trace is written for it.")
    res.table(["Page", "Headline figure", "Context"], untraced)
    for pg, fig, context in untraced:
        res.fail(f"{pg}: {fig}", f"untraced: {context}")
    if not ctx.dist:
        res.status = "NOT MEASURED"
        return
    res.verdict(bad == 0 and not unreached and not untraced)


# Which rendered page each trace in f4_traces reads its figure from.
TRACE_PAGE = {"Current Projects count": "transportation/bike/projects/index.html",
              "About: feed jobs": "transportation/bike/about/index.html"}
HEADLINE_NUM = re.compile(r"(?<![\w/.:-])\d[\d,]*(?:\.\d+)?%?(?![\w/:-])")


def headline_figures(ctx):
    """Every number between a section page's h1 and its first subheading, list, table or chart: the page's finding."""
    if not ctx.dist:
        return []
    pages = [os.path.join(ctx.dist, BIKE, "index.html")]
    pages += sorted(glob.glob(os.path.join(ctx.dist, BIKE, "*", "index.html")))
    out = []
    for path in pages:
        if not os.path.exists(path):
            continue
        m = re.search(r"<h1.*?(?=<(?:h2|table|ul|ol|details|form|svg)\b|$)", open(path, encoding="utf-8").read(),
                      re.S | re.I)
        seg = visible_text(m.group(0)) if m else ""
        seg = re.sub(r"§\s*[\w.()]+|Ordinance \S+", " ", seg)  # a citation is not a figure
        rel = os.path.relpath(path, ctx.dist)
        seen = set()
        for n in HEADLINE_NUM.finditer(seg):
            v = n.group(0).rstrip(".,")
            if re.fullmatch(r"(19|20)\d\d", v) or v in seen:
                continue
            seen.add(v)
            out.append((rel, v, seg[max(0, n.start() - 50):n.end() + 50]))
    return out


def f4_traces(ctx):
    """Headline figures followed from the rendered page to the data file to the source."""
    out = []
    c = ctx.coord
    pj = ctx.page_text("transportation/bike/projects/index.html") or ""
    m = re.search(r"(\d+) street projects", pj)
    n = c["counts"]["listed"]
    rows_ok = (n == len(c["projects"]) == c["counts"]["fromFeed"] + c["counts"]["fromSfmtaLayer"] + c["counts"].get("fromDpwPages", 0)
               + c["counts"].get("fromPucPages", 0))
    out.append(("Current Projects count", m.group(1) if m else "not found",
                f"counts.listed {n}; {c['counts']['fromFeed']} feed jobs + {c['counts']['fromSfmtaLayer']} layer projects + {c['counts'].get('fromDpwPages', 0)} Public Works pages + {c['counts'].get('fromPucPages', 0)} SFPUC pages",
                "reaches" if m and int(m.group(1)) == n and rows_ok else "FAILS"))
    # The type-of-work filter's counts: each option's figure against the rendered
    # list rows of that kind, and against the coordination.json rows, each of
    # which names its source (a feed job, a layer project or a Public Works page).
    ppath = os.path.join(ctx.dist or "", BIKE, "projects", "index.html")
    phtml = open(ppath, encoding="utf-8").read() if ctx.dist and os.path.exists(ppath) else ""
    sel = re.search(r"<select[^>]*data-filter-kind[^>]*>(.*?)</select>", phtml, re.S)
    li_kinds = collections.Counter(html.unescape(k) for k in re.findall(r'<li data-kind="([^"]*)"', phtml))
    by_row = collections.Counter(p.get("kind") for p in c["projects"])
    sourced = collections.Counter(p.get("kind") for p in c["projects"]
                                  if p.get("id") and p.get("source") in ("dotmaps", "sfmta", "dpw-page", "puc-page"))
    for k, label, fig in re.findall(r'<option value="([^"]+)">([^<]*?) \((\d+)\)</option>', sel.group(1) if sel else ""):
        k = html.unescape(k)
        name = f"Current Projects: {html.unescape(label)}"
        TRACE_PAGE[name] = "transportation/bike/projects/index.html"
        ok = (int(fig) == li_kinds[k] == by_row[k] == c["counts"].get("byKind", {}).get(k)
              and sourced[k] == by_row[k])
        out.append((name, fig, f"{li_kinds[k]} list rows of kind {k!r}; {by_row[k]} coordination.json rows, "
                               f"{sourced[k]} naming their source; counts.byKind {c['counts'].get('byKind', {}).get(k)}",
                    "reaches" if ok else "FAILS"))
    # The plan filter's counts (added 2026-09-29): each option's figure against
    # the rendered rows carrying that category, and against the coordination.json
    # rows in that band of the plan rating.
    sel = re.search(r"<select[^>]*data-filter-plan[^>]*>(.*?)</select>", phtml, re.S)
    li_plan = collections.Counter(re.findall(r'<li data-kind="[^"]*" data-plan="([^"]*)"', phtml))

    # Since 2026-09-29 the filter offers the plan rating's bands
    # (planRating.band, tools/projects/coordination-projects.py plan_rating), per
    # Bryan's "rating from 100% to 0%".
    def plan_cat(p):
        return (p.get("planRating") or {}).get("band")
    by_cat = collections.Counter(plan_cat(p) for p in c["projects"])
    for k, label, fig in re.findall(r'<option value="([^"]+)">([^<]*?) \((\d+)\)</option>', sel.group(1) if sel else ""):
        name = f"Current Projects: {html.unescape(label)}"
        TRACE_PAGE[name] = BIKE + "/projects/index.html"
        out.append((name, fig, f"{li_plan[k]} list rows in category {k!r}; {by_cat[k]} coordination.json rows",
                    "reaches" if int(fig) == li_plan[k] == by_cat[k] else "FAILS"))
    about = ctx.page_text("transportation/bike/about/index.html") or ""
    m = re.search(r"coordination feed \((\d[\d,]*) jobs", about)
    out.append(("About: feed jobs", m.group(1) if m else "not found", f"feed.jobs {c['feed']['jobs']}",
                "reaches" if m and int(m.group(1).replace(",", "")) == c["feed"]["jobs"] else "FAILS"))
    # The overview's lede (Bryan's wording, 2026-09-29): "we've gone from 61% to
    # 80% of residents connected". The two figures are the first and last
    # years' resident_share in history.json.
    ov = ctx.page_text(BIKE + "/index.html") or ""
    m = re.search(r"gone from (\d+(?:\.\d+)?)% to (\d+(?:\.\d+)?)% of residents connected", ov)
    H = load("site/data/bike-history/history.json")
    for i, (label, row) in enumerate((("first year", H["rows"][0]), ("latest year", H["rows"][-1]))):
        share = row.get("resident_share")
        shown = m.group(i + 1) if m else None
        name = "Overview: share of residents within a quarter mile, %s" % label
        TRACE_PAGE[name] = BIKE + "/index.html"
        out.append((name, (shown + "%") if shown else "not found",
                    ("%.0f%% (history.json %s resident_share)" % (share * 100, row.get("year"))) if share
                    else "no field in history.json rows",
                    "reaches" if shown and share and round(share * 100) == float(shown) else "FAILS"))
    return out


DEBRIS = re.compile(r"[A-Za-z0-9] \? [A-Za-z0-9]|â€|Ã[\x80-\xbf]|Ã|\ufffd")


@check("F5", "Clean text",
       "Zero `?` in place of dashes, `â€`, `Ã` or U+FFFD in shown names and titles.")
def f5(ctx, res):
    shown = []

    def scan(label, strings):
        for s in strings:
            if s and DEBRIS.search(s):
                shown.append((label, s[:100]))
    P = ctx.projects
    scan("coordination.json names", [p["name"] for p in P])
    scan("coordination.json record titles", [r.get("title") for p in P for r in p["records"]])
    scan("coordination.json related names", [r.get("name") for p in P for r in p.get("related") or []])
    ov = load("site/data/department-overlap.json")
    scan("department-overlap.json project names", [p.get("name") for p in ov.get("projects", [])])
    pr = load("site/data/project-records.json")
    scan("project-records.json", [s for s in re.findall(r'"(?:name|title)": "([^"]*)"', json.dumps(pr, ensure_ascii=False))])
    rendered = 0
    for path in ctx.rendered_pages():
        t = visible_text(open(path, encoding="utf-8").read())
        for m in DEBRIS.finditer(t):
            rendered += 1
            shown.append((os.path.relpath(path, ctx.dist), t[max(0, m.start() - 40):m.end() + 40]))
    upstream = []
    b = load("out/sfmta-board/meetings.json")
    upstream += [("out/sfmta-board/meetings.json", m["title"]) for m in b["matches"] if DEBRIS.search(m.get("title") or "")]
    upstream += [("out/project-record/projects.json", p["name"]) for p in ctx.record.values() if DEBRIS.search(p.get("name") or "")]
    res.measured = len(shown)
    res.denominator = "names and titles in site/data and on the rendered pages"
    res.table(["Where", "Text"], shown, limit=20)
    res.line(f"Upstream, not shown today: {len(upstream)}.")
    res.table(["File", "Text"], upstream)
    for where, text in shown:
        res.fail(where, text)
    res.verdict(not shown)


def git_json(rev_path):
    p = subprocess.run(["git", "show", rev_path], cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(p.stdout) if p.returncode == 0 else None
    except ValueError:
        return None


@check("S1", "Stable project addresses",
       "Every project address published at HEAD still answers: it is in data/project-ids.json, points at the same "
       "project or names the old id in formerIds, and the site builds a page or a redirect for it.")
def s1(ctx, res):
    reg = load("data/project-ids.json") or {}
    head_reg = git_json("HEAD:data/project-ids.json") or {}
    head_coord = git_json("HEAD:site/data/coordination.json") or {}
    published = {sl: e for sl, e in head_reg.items()}
    for p in head_coord.get("projects", []):
        published.setdefault(p["slug"], {"id": p["id"], "name": p["name"]})
    listed = {p["slug"]: p for p in ctx.coord["projects"]}
    retired = {r["slug"]: r for r in ctx.coord.get("retired", [])}
    problems = []
    for sl, old in sorted(published.items()):
        now = reg.get(sl)
        if now is None:
            problems.append((sl, old.get("name", ""), "lost: not in data/project-ids.json"))
            continue
        if "alias" in old and now.get("alias") != old["alias"]:
            problems.append((sl, old.get("name", ""), "alias moved from %s to %s" % (old["alias"], now.get("alias"))))
        if "id" in old and "id" in now and now["id"] != old["id"] and old["id"] not in now.get("formerIds", ()):
            problems.append((sl, old.get("name", ""), "points at %s, was %s, with no formerIds entry" % (now["id"], old["id"])))
        if sl not in listed and sl not in retired:
            problems.append((sl, old.get("name", ""), "no page: neither listed nor retired in coordination.json"))
    for sl, p in listed.items():
        e = reg.get(sl)
        if not e or e.get("id") != p["id"]:
            problems.append((sl, p["name"], "listed project's id %s does not match the registry" % p["id"]))
    res.measured = len(problems)
    res.denominator = "%d addresses published at HEAD, %d in the registry (%d listed, %d redirect, %d notice)" % (
        len(published), len(reg), len(listed), sum(1 for r in retired.values() if r["redirect"]),
        sum(1 for r in retired.values() if not r["redirect"]))
    res.table(["Slug", "Project", "Problem"], problems, limit=40)
    for sl, name, why in problems:
        res.fail(sl, why)
    res.verdict(not problems)


# ===========================================================================
# Hand-grade templates.

D2_HEADER = ["slug", "project", "department", "field", "shown", "department_page", "source_row", "department_says",
             "grade", "note"]
C3_HEADER = ["slug", "project", "record_date", "record_label", "relation", "record_title", "record_url",
             "route", "seed", "about_project", "label_correct", "note"]
NO_DEPT_PAGE = "none found"
D2_TOPUP_SEED = 20260929  # draws the projects that replace sampled ones no longer listed


def d2_pages(ctx, p):
    """(department page, the row the shown date was read from) for a listed project.

    The department page is what a grader checks the date against: the page the
    list links, or one the department publishes under nearly the same name. A
    DataSF row is never one, since it is the very row the shown date came from
    and grading against it only confirms the copy."""
    pages = ctx.once("d2_pages", lambda: [(r.get("name") or r.get("title"), r.get("canonical")) for r in ctx.sitemap_pages]
                     + [(r["name"], r["url"]) for r in ctx.dpw])
    page = next((l["url"] for l in p["links"] if dept_link(l["url"]) and l.get("kind") != "program"), None) \
        or next((u for n, u in pages if n and u and same_name(n, p["name"])), None)
    source = next((l["url"] for l in p["links"] if not dept_link(l["url"])), None)
    return page or NO_DEPT_PAGE, source or ""


def graded_rows(rows, cols):
    return [r for r in rows if any((r.get(c) or "").strip() for c in cols)]


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_templates(ctx, seed=20260928):
    """Write the hand-grade samples. A file nobody has graded yet is rewritten from the current data each run (the
    sample is seeded, so it only moves when the list does); once any row carries a grade the file is left alone."""
    os.makedirs(GRADES_DIR, exist_ok=True)
    d2p = os.path.join(GRADES_DIR, "d2-dates.csv")

    def d2_rows(sample):
        rows = []
        for p in sorted(sample, key=lambda p: p["name"]):
            page, source = d2_pages(ctx, p)
            base = [p["slug"], p["name"], p["department"]]
            for field, shown in (("construction start", p["start"]), ("construction end", p["end"]),
                                 ("consultation start", p.get("consultationStart")),
                                 ("consultation end", p.get("consultation"))):
                rows.append(base + [field, shown or "not published", page, source, "", "", ""])
            for r in [r for r in p["records"] if r.get("grade") in OWN_GRADES][:2]:
                rows.append(base + ["other: " + (r.get("label") or r.get("kind")),
                                    "%s %s" % (r.get("date"), (r.get("title") or "")[:60]), page, r.get("url") or "",
                                    "", "", ""])
        return rows

    held = read_csv(d2p)
    if not graded_rows(held, ("department_says", "grade")):
        rnd = random.Random(seed)
        write_csv(d2p, D2_HEADER, d2_rows(rnd.sample(ctx.projects, min(60, len(ctx.projects)))))
    else:
        # A graded sample keeps its grades. When sampled projects leave the
        # list (six did on 2026-09-29, when programme pages and finished Slow
        # Streets came off), the sample is topped up to 60 listed projects
        # with ones drawn from the rest of the list, their rows added blank,
        # so D2 reads NOT GRADED until someone grades them.
        listed = {p["slug"] for p in ctx.projects}
        have = {r["slug"] for r in held}
        short = 60 - len(have & listed)
        if short > 0:
            rest = sorted((p for p in ctx.projects if p["slug"] not in have), key=lambda p: p["slug"])
            add = random.Random(D2_TOPUP_SEED).sample(rest, min(short, len(rest)))
            write_csv(d2p, D2_HEADER, [[r.get(h) or "" for h in D2_HEADER] for r in held] + d2_rows(add))
    c3p = os.path.join(GRADES_DIR, "c3-links.csv")
    if not graded_rows(read_csv(c3p), ("about_project", "label_correct")):
        sample = c3_sample(ctx)
        write_csv(c3p, C3_HEADER, [
            [p["slug"], p["name"], r.get("date"), r.get("label"), r.get("relation"),
             EMAIL.sub("[email removed]", (r.get("title") or "")[:200]), r.get("url"), path, C3_SEED, "", "", ""]
            for p, r, path in sorted(sample, key=lambda x: (x[0]["name"], x[1].get("date") or ""))])


# The C3c sample's seed, written into every row of the sample it drew. A new
# sample takes a new seed: 20260929 drew the 2026-09-28 sample and 20260930
# the round-4 sample of 2026-09-29, drawn while street-only matches still
# counted.
C3_SEED = 20261001
# Each way project-record.py can count a record as a project's own gets up to
# this many links in the sample, so a route that attaches few records is still
# graded; the rest of the 40 are drawn at random from the whole pool.
C3_PER_PATH = 4


def match_path(pr, p, ev, grade):
    """Which of project-record.py's routes attached a record: from its grade and its "named as" evidence."""
    # project-record.py counts a street match only as a named program's
    # instance (strong) or a contract award agreeing on streets, work and
    # dates (probable); a street alone is "same street" and never sampled.
    # A street match that the project's page backs (strong for two shared
    # blocks, probable for streets alone) came by the page's meeting list.
    if grade in ("strong", "probable") and any("own page lists" in e for e in ev or ()):
        return "a meeting its own page lists, an item on its street"
    if grade == "strong":
        if any("SFMTA Board approving work along" in e for e in ev or ()):
            return "Board approval along the street it is named for"
        return "program named, project on its street"
    if grade == "probable":
        return "contract award on its streets"
    named = next((e for e in ev or () if e.startswith("named as")), None)
    if not named:
        return "other"
    phrase = named[len("named as “"):].rstrip("”")
    keys = pr.name_keys(p["name"])
    codes = set(pr._CODE.findall(pr.norm_name(p["name"])))
    for k in keys + pr.contract_keys(p.get("scopeText")):
        pat = pr.name_pattern("", [k])
        if pat is not None and pat.fullmatch(phrase):
            if pr._CODE.fullmatch(k):
                return "contract number, in the name" if k in codes else "contract number, from the feed's scope"
            if pr.is_place_key(k):
                return "place-named project"
            full = [x for x in keys if not pr._CODE.fullmatch(x)]
            return "full name" if full and k == full[0] else "head of the name"
    return "name, other key"


# A second draw, added to a sample already graded: links the first draw did
# not take, from the matcher as it stands, so the routes added since (Board
# approvals along a named street, meetings a project's page lists, awards
# read from the SFPUC extract) are graded too. Its own seed, written into
# each row it adds.
C3_EXTRA_SEED = 20261002


def c3_pool(ctx, pr):
    """Every record a city body published that a listed project counts as its own, with the route that attached it."""
    pool = []
    for p in ctx.projects:
        ev_by = {}
        for rid in [p["id"]] + ["dotmaps:" + f for f in feed_ids_of(p)]:
            for x in ctx.record.get(rid, {}).get("records", []):
                ev_by.setdefault((x.get("kind"), x.get("date"), title_key(x.get("title"))[:60]), x.get("matchedOn"))
        for r in p["records"]:
            if r.get("grade") in OWN_GRADES and r.get("kind") in BODY_KINDS and r.get("relation") != OWN_PAGE:
                ev = ev_by.get((r.get("kind"), r.get("date"), title_key(r.get("title"))[:60]))
                pool.append((p, r, match_path(pr, p, ev, r.get("grade"))))
    pool.sort(key=lambda x: (x[0]["slug"], x[1].get("date") or "", title_key(x[1].get("title"))))
    return pool


def c3_draw_more(ctx, n):
    """Append n more seeded links to the graded C3c sample: up to C3_PER_PATH per route, the rest at random.

    Links already in the file (same project, date and title) are not drawn again. Rows are added ungraded."""
    pr = ctx.once("pr", lambda: load_module("project_record", "tools/projects/project-record.py"))
    path = os.path.join(GRADES_DIR, "c3-links.csv")
    rows = read_csv(path)
    have = {(r["slug"], r["record_date"], title_key(r["record_title"])[:60]) for r in rows}
    pool = [x for x in c3_pool(ctx, pr)
            if (x[0]["slug"], x[1].get("date") or "", title_key(x[1].get("title"))[:60]) not in have]
    rnd = random.Random(C3_EXTRA_SEED)
    by_path = collections.defaultdict(list)
    for x in pool:
        by_path[x[2]].append(x)
    chosen = []
    for route in sorted(by_path):
        if route == "full name":
            continue
        chosen += rnd.sample(by_path[route], max(0, min(C3_PER_PATH, len(by_path[route]), n - len(chosen))))
    rest = [x for x in pool if x not in chosen]
    chosen += rnd.sample(rest, max(0, min(n - len(chosen), len(rest))))
    new = [[p["slug"], p["name"], r.get("date"), r.get("label"), r.get("relation"),
            EMAIL.sub("[email removed]", (r.get("title") or "")[:200]), r.get("url"), route, C3_EXTRA_SEED, "", "", ""]
           for p, r, route in sorted(chosen, key=lambda x: (x[0]["name"], x[1].get("date") or ""))]
    write_csv(path, C3_HEADER, [[r.get(c, "") for c in C3_HEADER] for r in rows] + new)
    return len(new)


def c3_sample(ctx):
    """A seeded sample of 40 links the matcher counts now, with every attach route represented.

    Returns (project, record, route) triples. The pool is every record a city
    body published that a listed project counts as its own; items from the
    project's own page are C3a's question. Each route (contract number, head
    of the name, place-named project, street legislation...) gets up to
    C3_PER_PATH links drawn at random from its own records, and the rest are
    drawn at random from what is left."""
    pr = ctx.once("pr", lambda: load_module("project_record", "tools/projects/project-record.py"))
    rnd = random.Random(C3_SEED)
    pool = c3_pool(ctx, pr)
    by_path = collections.defaultdict(list)
    for x in pool:
        by_path[x[2]].append(x)
    chosen = []
    for path in sorted(by_path):
        if path == "full name":
            continue
        xs = by_path[path]
        chosen += rnd.sample(xs, min(C3_PER_PATH, len(xs)))
    rest = [x for x in pool if x not in chosen]
    chosen += rnd.sample(rest, max(0, min(40 - len(chosen), len(rest))))
    return chosen


# ===========================================================================
# The site build, the run and the report.

def build_site():
    """Build a copy of site/ into a temp directory and return its dist/, or None when node is missing or the build fails."""
    node = shutil.which("node")
    if not node:
        print("  node not found: F checks read no rendered pages")
        return None, None
    tmp = tempfile.mkdtemp(prefix="sfw-audit-site-")
    for part in ("astro", "astro.config.mjs", "content", "data", "scripts", "src", "package.json"):
        src = os.path.join(ROOT, "site", part)
        dst = os.path.join(tmp, part)
        if os.path.isdir(src):
            shutil.copytree(src, dst, symlinks=True)
        elif os.path.exists(src):
            shutil.copy2(src, dst)
    # The build runs Astro and imports Observable Plot and linkedom; link the installed copies rather than copy them.
    modules = os.path.join(ROOT, "site", "node_modules")
    if os.path.isdir(modules):
        os.symlink(modules, os.path.join(tmp, "node_modules"))
    env = dict(os.environ)
    env.pop("SITE_BASE_PATH", None)
    env["ASTRO_TELEMETRY_DISABLED"] = "1"
    r = subprocess.run([node, "node_modules/astro/bin/astro.mjs", "build"], cwd=tmp, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print("  site build failed:", (r.stdout + r.stderr)[-500:])
        return None, tmp
    return os.path.join(tmp, "dist"), tmp


def scrub(s):
    return EMAIL.sub(lambda m: m.group(0) if INSTITUTIONAL.match(m.group(0)) else "[email removed]", s)


# The pass lines in @check above are copied from the criteria doc. This is a
# hash of the doc's own "Pass:" lines when they were last copied; when the doc
# changes, the report says so, so the copies cannot drift without notice.
CRITERIA_PASS_HASH = "f6650990c2494d05"


def criteria_pass_hash():
    path = os.path.join(ROOT, CRITERIA)
    if not os.path.exists(path):
        return None
    cur, out = None, []
    for line in open(path, encoding="utf-8").read().split("\n"):
        m = re.match(r"^### (\w+)\.", line)
        if m:
            cur = m.group(1)
        m = re.match(r"^- \*\*Pass:\*\*\s*(.*)", line)
        if m:
            out.append(f"{cur}: {m.group(1).strip()}")
    return hashlib.sha256("\n".join(out).encode()).hexdigest()[:16]


def doc_link(path):
    return f"[{path}](../../{path})" if os.path.exists(os.path.join(ROOT, path)) else f"{path} (not in this checkout)"


def render_report(ctx, results, argv):
    counts = collections.Counter(r.status for r in results)
    out = io.StringIO()
    w = out.write
    w("# Transportation data audit\n\n")
    w(f"Run {ctx.today_s} by [`pipeline/transportation-audit.py`](../../pipeline/transportation-audit.py) against "
      f"{doc_link(CRITERIA)}. Generated: edit the script or the data, never this file. "
      f"The first run, by hand, is {doc_link(BASELINE_DOC)}.\n\n")
    h = criteria_pass_hash()
    if h != CRITERIA_PASS_HASH:
        w(f"**The criteria doc's pass lines have changed since this script's were copied from them** (hash {h}, "
          f"script has {CRITERIA_PASS_HASH}). Check each pass line below against the doc, then update "
          f"CRITERIA_PASS_HASH.\n\n")
    w("Result: " + ", ".join(f"{counts[s]} {s}" for s in STATUS if counts[s]) + ".\n\n")
    w("| Check | Status | Measured | Denominator | Pass line |\n| --- | --- | --- | --- | --- |\n")
    for r in results:
        w(f"| [{r.cid}](#{anchor(r)}) {md_cell(r.title)} | **{r.status}** | {md_cell(r.measured)} | {md_cell(r.denominator)} | {md_cell(r.pass_line)} |\n")
    w("\n## Against the first run\n\n")
    w("Each difference from the hand-run numbers in the first audit, and why.\n\n")
    w("| Check | First run | This run | Why they differ |\n| --- | --- | --- | --- |\n")
    for r in results:
        w(f"| {r.cid} | {md_cell(r.baseline)} | {md_cell(r.status)}: {md_cell(r.measured)} | {md_cell(difference(r))} |\n")
    for r in results:
        w(f"\n## {r.cid}. {r.title}\n\n")
        w(f"**{r.status}.** Measured {r.measured} of {r.denominator}.\n\n")
        w(f"Pass line: {r.pass_line}\n\n")
        for d in r.details:
            w(d + "\n")
    w("\n## How to read and extend this\n\n")
    w("- `pipeline/transportation-audit.py --explain` prints, under each check that does not pass, the rows that count "
      "against its pass line; `results.json` carries the same rows under `failing`.\n")
    w("- Hand grades: `data/audit/grades/d2-dates.csv` and `c3-links.csv`. Column meanings in `data/audit/README.md`.\n")
    w("- Explanations for “every miss explained”: `data/audit/explanations.csv` (check, key, explanation).\n")
    w("- Typed-figure verdicts for F4: `data/audit/typed-figures.csv` (file, figure, verdict external or data, note).\n")
    w("- Network caches: `data/audit/cache/`; `--refresh` re-fetches SFMTA's sitemap, every department link's status and DataSF metadata.\n")
    w("- A new body's mirror flips its C1 row by writing `out/<slug>/coverage.json`.\n")
    return scrub(out.getvalue())


def explain(res):
    """The rows behind a check's failure, one per line, for --explain."""
    if not res.failing:
        why = {"NOT GRADED": "rows wait on a hand grade", "NOT MEASURED": "the input it needs was not read"}.get(res.status)
        return f"  {res.cid}: no failing rows recorded" + (f" ({why})" if why else "") + "\n"
    out = [f"  {res.cid}: {len(res.failing)} failing row{'s' if len(res.failing) != 1 else ''}"]
    out += [f"    - {k}" + (f": {w}" if w else "") for k, w in res.failing]
    return "\n".join(out) + "\n"


def anchor(r):
    return re.sub(r"[^a-z0-9 -]", "", (r.cid + ". " + r.title).lower()).replace(" ", "-")


# Why this run's numbers differ from the first run's. Each entry says what
# changed in the measure or the data; every figure in it is read from this
# run's result (r.facts, r.measured), never typed, so the text cannot outlive
# the numbers beside it.
def _f(r, k, default="—"):
    return r.facts.get(k, default)


DIFFERENCES = {
    "A1-SFMTA": lambda r: (
        "The first run counted non-Bike projects on plan blocks and sitemap pages of any kind. This run counts both "
        "populations the criteria set: every active layer project on plan blocks "
        f"({_f(r, 'on_plan')}, {_f(r, 'miss_on_plan')} missing) and every bike or pedestrian project, on the plan or "
        f"not ({_f(r, 'bikeped')} on the layer and {_f(r, 'off_layer')} active sitemap pages, {_f(r, 'miss_bikeped')} "
        "missing). A project counts as finished when the layer says so or its own page does (read from the pages "
        "extract, whatever phase the layer gives), and a project with no bike or pedestrian scope counts only while "
        "its page shows work in the last year or to come. What each filter removed is listed under the check."),
    "A1-PW": lambda r: (
        "The first run counted plan blocks no listed project covers. This run counts in-progress Public Works pages on "
        f"plan blocks that no listed row names, whatever the page's name ({_f(r, 'on_plan')} pages, "
        f"{_f(r, 'not_street_on_plan')} of them not named for street work), so a page whose blocks another project "
        "happens to cover still counts. A page's blocks are read from its Location field as the corridor between "
        "the limits it names (lib/pw_extent.py), not every block of every street it names. Pages with no "
        "block data or off the plan are listed under the check."),
    "A2": "Same measure. The feed is read from the cached pull, and the check says whether it is the pull "
          "coordination.json was built from.",
    "A3": "Overlap pairs are measured on every block a row holds, not only plan blocks; pairs shown as related do "
          "not count, and cross-source pairs arrive merged into one row.",
    "B1": "The list now takes every SFMTA bike or pedestrian project, and rows link the page their department publishes "
          "where one matches (tools/projects/department-project-pages.py). The table under the check gives each department's share.",
    "B2": "This run also checks whether each missing start, end or scope says \"not published\" on the page, which is "
          "what the pass line asks.",
    "B3": lambda r: (
        f"The name rule finds {_f(r, 'pairs')} SFMTA/Public Works pairs, and 'shown' requires the listed page to link "
        "Public Works' page and print its status. Merged SFMTA/feed rows are a second population "
        f"({_f(r, 'merged_bad')} of {_f(r, 'merged')} disagree), counted apart."),
    "C1": "Each body is now read from its own meeting mirror (out/record-coverage/coverage.json), and a fetch script "
          "counts only when it writes through lib/mirror.py, which re-fetches drafts and skips settled meetings.",
    "C2": lambda r: (
        f"The list has {_f(r, 'major')} major projects, and records come from every item of the deciding bodies' "
        "mirrors, matched by name, where the first run read only bike-keyword items. The independent name search "
        "covers the same mirrors, listed under the check."),
    "C3a": "Project-page items now show in their own fold on each project page, apart from City decisions, and carry "
           "their page's label (timeline, notice, event) rather than a city body's.",
    "C3b": lambda r: (
        "The first run spot-checked three contract awards. This run searches every attached record and every item of "
        f"the deciding bodies' meeting mirrors ({_f(r, 'items')} items) for the job's contract number or full name."),
    "C3c": "Not graded yet. The sample (data/audit/grades/c3-links.csv) draws only records a city body published.",
    "C4": "New criterion (2026-09-28); no first-run number.",
    "D1": "Every past-end row on the list counts, split by what its own department publishes today: still active "
          "(counted until Bryan decides whether such rows belong on a current list) or not. Starts after 2032 and "
          "future-dated records are reported as information, not counted, since the pass line names only the three "
          "conflicts.",
    "D2": "New criterion (2026-09-28). The sample (data/audit/grades/d2-dates.csv) points each row at the "
          "department's page, or says none was found.",
    "E1": "The project geometry is a drawn file, so an empty project shape fails it. A project drawn as intersection "
          "points, or a page SFMTA publishes but does not map (which says so), is not an empty shape. The raw layer's "
          "faults are reported as information.",
    "E2": lambda r: (
        "Bikeway rows are now keyed to the centerline block they lie on (lib/bikeway_snap.py). Drawn features with "
        f"no CNN ({_f(r, 'nocnn')}) are listed and left out of the denominator, not counted as aligned."),
    "E3": "Each project map now draws every block and intersection it holds, from the plan's trace, the bikeway layer "
          "or the centerline; retired CNNs go to the blocks that replaced them.",
    "F1": lambda r: (
        f"Every mi figure on the rendered pages ({_f(r, 'figures')}) takes the verdict of its data file, and every "
        "file is measured against the bikeway layer and, for plan blocks, against the North Star map PDF read and "
        "measured here: which blocks the map draws and how much of each. The pipeline's trace is not read, so its "
        f"share cannot pass by construction. Plan network: status.json {_f(r, 'plan_status_mi')} mi, the map "
        f"{_f(r, 'plan_map_mi')} mi; {_f(r, 'plan_share_bad')} blocks disagree on how much, {_f(r, 'plan_absent')} "
        f"plan blocks the map does not draw, {_f(r, 'plan_extra')} drawn blocks the plan network lacks."),
    "F3": "The overview's layer date is now filled from the layer's own latest install month, so no typed date is left.",
    "F4": "Each typed figure is classified in data/audit/typed-figures.csv; the About page's feed-job count is filled "
          "from the feed.",
    "F5": "The Public Works Commission mirror carries a ? for the dash in contract-award titles, and those titles reach "
          "project pages. Debris in out/sfmta-board/meetings.json is upstream and reported as information.",
}


DIFFERENCES["S1"] = ("New criterion (2026-09-28). Project addresses are kept in data/project-ids.json, which also "
                     "holds the 223 name-based addresses published between 2026-09-22 and 09-24.")


def difference(r):
    d = DIFFERENCES.get(r.cid, "Same measure, same data.")
    return d(r) if callable(d) else d


def refresh_metadata():
    from sfdata import metadata
    out = {}
    for fxf in ("btxj-k9uh", "3psu-pn9h", "p2fw-hsrv", "nc68-ngbr"):
        try:
            # sfdata.metadata() returns the publisher's rowsUpdatedAt as a
            # date under rows_updated_at; None when DataSF publishes neither
            # rowsUpdatedAt nor viewLastModified.
            d = metadata(fxf).get("rows_updated_at")
            out[fxf] = d.isoformat() if d else "not published"
        except Exception as e:  # noqa: BLE001
            out[fxf] = "unread: %s" % str(e)[:60]
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump({"fetched_on": dt.date.today().isoformat(), "updated": out},
              open(os.path.join(CACHE_DIR, "metadata.json"), "w"), indent=1)
    print("  metadata:", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", nargs="*", help="run only checks whose id starts with one of these")
    ap.add_argument("--refresh", action="store_true", help="re-fetch the sitemap, link status and DataSF metadata first")
    ap.add_argument("--no-build", action="store_true", help="do not build the site; F checks that read pages report NOT MEASURED")
    ap.add_argument("--strict", action="store_true", help="exit 1 on NOT GRADED or NOT MEASURED too")
    ap.add_argument("--today", help="audit as of this date (YYYY-MM-DD)")
    ap.add_argument("--show", action="store_true", help="print each check's rows as well as its line")
    ap.add_argument("--explain", action="store_true",
                    help="after each check that does not pass, list the rows that count against its pass line")
    ap.add_argument("--c3-draw-more", type=int, metavar="N",
                    help="append N more seeded links (seed C3_EXTRA_SEED) to the graded C3c sample, ungraded, and stop")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    if args.refresh:
        print("refreshing network caches")
        for fn in (refresh_sitemap, refresh_links, refresh_metadata):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                print(f"  {fn.__name__} failed: {e}")
    else:
        try:
            update_links()
        except Exception as e:  # noqa: BLE001 - the audit runs on the cache as it stands
            print(f"  update_links failed: {e}")

    dist, tmp = (None, None) if args.no_build else build_site()
    ctx = Ctx(today, dist, refresh=args.refresh)
    if args.c3_draw_more:
        print(f"added {c3_draw_more(ctx, args.c3_draw_more)} links to "
              f"{os.path.relpath(os.path.join(GRADES_DIR, 'c3-links.csv'), ROOT)}")
        return
    write_templates(ctx)
    results = []
    try:
        for cid, title, pass_line, fn in CHECKS:
            if args.only and not any(cid.startswith(o) for o in args.only):
                continue
            res = Result(cid, title, pass_line)
            fn(ctx, res)
            results.append(res)
            print(f"{cid:9} {res.status:12} {res.measured} / {res.denominator}")
            if args.show:
                print(scrub("\n".join(res.details)) + "\n")
            if args.explain and res.status != "PASS":
                print(scrub(explain(res)))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    report = render_report(ctx, results, sys.argv[1:])
    if not args.only:
        with open(REPORT, "w", encoding="utf-8") as fh:
            fh.write(report)
        json.dump([{"check": r.cid, "title": r.title, "status": r.status, "measured": r.measured,
                    "denominator": r.denominator, "passLine": r.pass_line,
                    "failing": [{"key": k, "why": w} for k, w in r.failing]} for r in results],
                  open(RESULTS, "w"), indent=1, default=str)
        print(f"→ {os.path.relpath(REPORT, ROOT)}")
    bad = [r for r in results if r.status == "FAIL" or (args.strict and r.status in ("NOT GRADED", "NOT MEASURED"))]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    # The audit runs with the hash seed the pipeline uses, whoever starts it,
    # so set iteration in the modules it imports breaks ties as the pipeline's
    # own run did (pipeline/transportation-update.py pins 0).
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable] + sys.argv, dict(os.environ, PYTHONHASHSEED="0"))
    main()
