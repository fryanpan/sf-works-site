#!/usr/bin/env python3
"""Which SFMTA projects added the most all-ages bikeway miles, and brought the most residents and schools within reach.

    tools/bike-network/bike-network-projects.py

Reads what tools/bike-network/bike-network-history.py wrote for the site (the all-ages
blocks with the year each became one, and the census blocks, schools and
branches with the year each came within reach) and the project geometry
matching in out/project-record/project-blocks.json (tools/projects/project-blocks.py),
and attributes each block that became all-ages after the first year to the
one SFMTA project whose published line geometry covers it.

The rule is deliberately narrow, because a block match is a place and not a
project — 32 of 40 block matches checked on 2026-09-21 were other work on the
same street. So a block is attributed only when:

  - exactly one project's geometry covers it;
  - that project's geometry is a line (an area project — a traffic-calming
    zone, a community-based transportation plan — is excluded, since a
    polygon over a neighbourhood says nothing about which street it built);
  - SFMTA tags the project Bike, or the project's own page lists "Bicycle
    Infrastructure Improvements" among its improvements;
  - the project could have built it: a project in Planning or Detailed Design
    counts only when its own page says the work is complete (SFMTA's phase
    field lags its pages).

When several projects cover a block, the one named for the block's street
wins; if that namesake's page dates its work to other years, the one project
whose page dates work to the block's year wins instead.

A block with no such project, or with more than one, is reported as
unattributed with the reason, and its miles are never handed to a project.
A resident, school or branch is attributed to the project of the block that
first brought it within reach; when that block is unattributed, so is the
reach.

Writes site/data/bike-history/projects.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import re
import datetime as dt
import json
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
from mile_basis import BASIS  # noqa: E402
BIKE = os.path.join(ROOT, "site", "data", "bike-history")
ALL_AGES = os.path.join(BIKE, "all-ages.geojson")
REACH = os.path.join(BIKE, "reach.json")
PROJECT_BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")
PROJECTS = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
PAGES = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")  # tools/projects/sfmta-project-pages.py
SEGMENTS = os.path.join(ROOT, "site", "data", "bike-history", "segments.json")
COMPONENTS = os.path.join(BIKE, "components.json")  # per-block miles by facility code, from bike-network-history.py
OUT = os.path.join(BIKE, "projects.json")

MILE = 1609.344
LAT0 = math.radians(37.76)


def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * 6371008.8, math.radians(lat) * 6371008.8)


def line_miles(coords):
    P = [xy(*c) for c in coords]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(P, P[1:])) / MILE


UNBUILT_PHASES = {"Planning", "Detailed Design"}

SUFFIX = {"ST": "Street", "AVE": "Avenue", "BLVD": "Boulevard", "DR": "Drive", "WAY": "Way", "PL": "Place", "TER": "Terrace", "CT": "Court", "LN": "Lane", "RD": "Road"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


NOT_A_BUILDER = re.compile(r"\b(Study|Plan|Program|Programme)\b|^\d+[A-Z]?\s")  # a leading number is a Muni route ("8 Bayshore")


PHONE = re.compile(r"\b\d{3}[.\-]\d{3}[.\-]\d{4}\b")  # "415.646.2005" is not the year 2005


def page_text(p):
    """The page's prose on one line, with phone numbers removed so their digits are never read as a year."""
    return PHONE.sub(" ", " ".join((p.get("pageText") or "").split()))


def timeline_start(p):
    """The first year in the page's Project Timeline, or None when the page has none."""
    text = page_text(p)
    i = text.find("Project Timeline")
    years = [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", text[i:i + 600])] if i >= 0 else []
    return min(years) if years else None


BUILD_WORD = re.compile(r"install|implement|construct|complet|built|striped|opened|finish|quick-build|repav", re.I)
SLOW_STREETS_BEGAN = 2020  # the COVID-19 Slow Streets program; its pages date the permanent programme, not the first barricades


def build_window(p):
    """The years the project's own page dates its building to, widened by one on each side for when the layer records the work; None when the page gives no such year.

    A year counts when it sits within about a sentence of a word that dates
    work on the ground (installed, implemented, construction, completed, repaved,
    built). Bryan, 2026-09-28, on the Folsom-Howard card: "Why does
    Folsom-Howard Streetscape project show Built in 2018-2019 but the source
    project page doesn't say that ... check all of these projects".
    """
    text = page_text(p)
    years = set()
    for m in BUILD_WORD.finditer(text):
        years.update(int(y) for y in re.findall(r"\b(20[0-3]\d)\b", text[max(0, m.start() - 60):m.end() + 90]))
    # A dated photo of the bikeway shows it on the ground by then ("Clipper
    # Street looking uphill with protected bikeway - February 2020").
    years.update(int(y) for y in re.findall(r"(?:bikeway|bike lanes?|cycle ?track)\s*[-\u2013\u2014]\s*(?:[A-Z][a-z]+\s+)?(20[0-3]\d)\b", text))
    if years and "slow street" in (p.get("name") or "").lower():
        years.add(SLOW_STREETS_BEGAN)
        years = {y for y in years if y >= SLOW_STREETS_BEGAN}
    if not years:
        return None
    return min(years) - 1, max(years) + 1


def street_title(name):
    """'20TH ST' -> '20th Street'; 'GOLDEN GATE AVE' -> 'Golden Gate Avenue'."""
    words = name.split()
    if words and words[-1].upper() in SUFFIX:
        words[-1] = SUFFIX[words[-1].upper()]
    return " ".join(w.lower() if re.match(r"^\d+(ST|ND|RD|TH)$", w.upper()) else w.capitalize() for w in words)


def street_in_name(street, project_name):
    """True when the project's name carries the block's street, without its suffix: 'howardst' -> 'howard' in 'folsomhowardstreetscape'."""
    words = (street or "").lower().split()
    if words and words[-1] in ("st", "ave", "blvd", "dr", "way", "pl", "ter", "ct", "ln", "rd"):
        words = words[:-1]
    if not words:
        return False
    # Whole words only: '7th' must not match '17th', nor 'bay' 'Transbay'.
    return re.search(r"(?<![a-z0-9])" + r"[\s/-]+".join(map(re.escape, words)) + r"(?![a-z0-9])", project_name.lower()) is not None


# A sentence in which the page says the work itself is finished: "Installation
# ... began in October 2025 and was completed in mid-December 2025" (Sloat Blvd
# Quick-Build, https://www.sfmta.com/node/26728, whose phase field still reads
# Detailed Design), "construction is substantially complete as of 11/1/2024".
BUILT_SAID = re.compile(r"\b(?:construction|installation|implementation|improvements|project)\b[^.]{0,160}?"
                        r"\b(?:was|were|is|are|has\s+been|have\s+been)\s+(?:now\s+)?(?:successfully\s+|substantially\s+|fully\s+)?"
                        r"complete(?:d)?\b", re.I)
# A sentence about one phase or step of the project is not the project ("the
# near-term phase was completed in 2019", "outreach is complete").
BUILT_PART = re.compile(r"\b(?:phase|stage|segment|first|portion|part|survey|planning|design|outreach|evaluation|"
                        r"legislation|environmental|study|interim|half|pending|team|school\s+signage)\b", re.I)
# Nor is a sentence about work still to come ("The remaining improvements will
# be installed after utility work and paving are completed").
# Nor a sentence about other work: "Construction on the Embarcadero 2020
# Quick-Build Projects ... was completed" on the Central Embarcadero Safety
# Project's page, "a SF Public Works repaving project, which has been completed".
BUILT_OTHER = re.compile(r"\bProjects\b|Public\s+Works|repaving|PG&E|utility")
BUILT_NOT_YET = re.compile(r"\b(?:will|after|once|until|when|expected|anticipated|scheduled|remaining|underway|ongoing)\b", re.I)


def page_says_built(p):
    """The sentence in which the project's own page says its construction or installation is complete, or None."""
    text = " ".join((p.get("pageText") or "").split())
    # The page header runs into its first sentence with no full stop.
    text = re.sub(r"^.*?\bLinkedIn\s+(?:SFMTA\.com/\S+\s+)?", "", text)
    # A street abbreviation's full stop does not end the sentence ("on Sloat Blvd. was completed").
    text = re.sub(r"\b(Blvd|St|Ave|Dr|Pl|Ter|Ct|Ln|Rd|No)\.", r"\1", text)
    for s in re.split(r"(?<=[.!?])\s+", text):
        m = BUILT_SAID.search(s)
        if m and not BUILT_PART.search(s) and not BUILT_NOT_YET.search(s) and not BUILT_OTHER.search(s):
            return s
    return None


def could_have_built(p):
    """False when SFMTA's own page says the project has not been built.

    The phase field lags the page: SFMTA's Sloat Blvd Quick-Build still reads
    Detailed Design while its page says the work finished in December 2025, so
    a planning or design phase is overruled by the page saying the work is
    complete. The page's own sentence outweighs a stale "Pending" in its
    timeline too (Anza Street Bike Lanes: every stage "Pending", and "Project
    Update 06/11/2021: The project is now substantially complete!").
    """
    if p.get("phase") in UNBUILT_PHASES:
        return page_says_built(p) is not None
    if p.get("phase") in (None, "Current") and re.search(r"Construction\s+Pending", p.get("pageText") or ""):
        return False
    return True


def main():
    aa = json.load(open(ALL_AGES))
    reach = json.load(open(REACH))
    pblocks = json.load(open(PROJECT_BLOCKS))
    sfmta = json.load(open(PROJECTS))
    components = json.load(open(COMPONENTS))["blocks"] if os.path.exists(COMPONENTS) else {}
    # Each block's best class per year, one character per year from
    # seg_years[0], "0" for no bikeway. A block that carried a lesser bikeway
    # the year before it became all-ages was upgraded; one that carried none
    # was added (Bryan, 2026-09-24: "Miles added <x> mi <type> ... Miles
    # upgraded: ditto"). A block all-ages in the first year has no year before
    # it to read, so it counts as added.
    seg = json.load(open(SEGMENTS))
    seg_years, seg_class = seg["years"], {}
    for sg in seg["segments"]:
        if sg.get("cnn"):
            prev = seg_class.get(sg["cnn"])
            seg_class[sg["cnn"]] = sg["y"] if prev is None else "".join(max(a, b) for a, b in zip(prev, sg["y"]))
    years = aa["years"]
    first_year = years[0]

    projects = {str(p["node"]): dict(p) for p in sfmta["projects"]}
    # The page's text from projects.json, or from pages.json where projects.json
    # holds none (104 of 224 rows on 2026-09-29, Bayshore Boulevard
    # Quick-Build's among them), as tools/bike-network/bike-reported-work.py reads it.
    pages_json = json.load(open(PAGES))["pages"] if os.path.exists(PAGES) else {}
    for node, p in projects.items():
        if not p.get("pageText") and (pages_json.get(node) or {}).get("pageText"):
            p["pageText"] = pages_json[node]["pageText"]
        # A project SFMTA does not tag Bike whose own page lists "Bicycle
        # Infrastructure Improvements" among its improvements built a bikeway
        # (Bayshore Boulevard Quick-Build, https://www.sfmta.com/node/22025,
        # tagged only Quick-Build and Vision Zero).
        if not p.get("bike") and re.search(r"\bImprovements\b.{0,120}\b(?:Bicycle|Bike|Bikeway)(?: Infrastructure)? Improvements\b",
                                           " ".join((p.get("pageText") or "").split())):
            p["bike"] = True
            p["bike_from_page"] = True
    by_norm_name = {norm(p["name"]): str(p["node"]) for p in sfmta["projects"]}
    # A project still in planning or design, or whose page says construction
    # is pending, has built nothing, so it cannot be the project that made a
    # block all-ages, however much of the block its line covers. Bryan,
    # 2026-09-23, on the Central Embarcadero Safety Project (construction
    # expected 2027) being credited with the 2018-2020 Embarcadero bikeway:
    # "Incorrect link ... The quick build project, not the higher quality
    # embarcadero safety project."
    excluded = []
    for node, pb in pblocks["projects"].items():
        p = projects.get(node)
        if p and p.get("bike") and "line" in pb.get("methods", ()) and not could_have_built(p):
            excluded.append({"node": node, "name": p["name"], "phase": p.get("phase"), "page": p["page"]})
    # CNN -> the projects whose LINE geometry covers it, which SFMTA tags Bike,
    # and which could have built something.
    cover = collections.defaultdict(list)
    for node, pb in pblocks["projects"].items():
        p = projects.get(node)
        if not p or not p.get("bike") or "line" not in pb.get("methods", ()) or not could_have_built(p):
            continue
        for cnn in pb["cnns"]:
            cover[cnn].append(node)

    per = collections.defaultdict(lambda: {"miles": 0.0, "segments": 0, "years": set(), "residents": 0,
                                           "schools": [], "libraries": [], "streets": collections.Counter(),
                                           # the blocks themselves, and their miles by facility code, so the
                                           # overview map can outline a project and say what it built when a
                                           # reader clicks it (Bryan, 2026-09-23: "click on the map and get a
                                           # project outline (type of infra, miles, photo, when it happened...)")
                                           "blocks": [], "facilities": collections.Counter(),
                                           "added": collections.Counter(), "upgraded": collections.Counter(),
                                           # per year: miles, and a mile-weighted mean of the blocks' midpoints,
                                           # which the overview map uses to place the project's label in the
                                           # year it appears (Bryan, 2026-09-23: "mark down the new projects on
                                           # the map with a label").
                                           "by_year": collections.defaultdict(lambda: {"miles": 0.0, "lon": 0.0, "lat": 0.0})})
    # street (normalised) -> built Bike projects with line geometry on it, for the name fallback below.
    street_projects = collections.defaultdict(list)
    for node, pb in pblocks["projects"].items():
        p = projects.get(node)
        if p and p.get("bike") and "line" in pb.get("methods", ()) and could_have_built(p) \
                and not NOT_A_BUILDER.search(p["name"]):
            for st in pb.get("streets", ()):
                street_projects[norm(st)].append(node)
    name_fallback = collections.Counter()
    # Each page's headline image address, read by scripts/sfmta-project-pages.py.
    # The site loads the image from sfmta.com; nothing is copied.
    images, thumbs = {}, {}
    if pages_json:
        images = {k: v.get("image") for k, v in pages_json.items() if v.get("image")}
        # A full-size original is several megabytes: fine behind a click on
        # the card, too heavy for a thumbnail every visitor loads.
        thumbs = {k: v.get("image") for k, v in pages_json.items() if v.get("image") and not v.get("image_full_size")}
    year_refused = collections.Counter()
    window_refused = collections.defaultdict(list)

    def before_start(node, year, name_rule=False):
        """True when the block predates the project: its page's timeline start, or, for a credit by name alone on a page with no timeline, the year the page was created."""
        p = projects.get(node) or {}
        if p.get("stand_in"):
            return False
        start = timeline_start(p)
        if start is None and name_rule and p.get("created"):
            start = int(p["created"][:4])
        return start is not None and year < start

    def dates_fit(node, year):
        """True when the project's page dates work to within a year of `year`, False when it dates work only to other years, None when it dates none."""
        p = projects.get(node) or {}
        w = None if p.get("stand_in") else build_window(p)
        return None if w is None else w[0] <= year <= w[1]
    attributed_key = {}  # block key -> node
    un = {"none": {"miles": 0.0, "segments": 0}, "multi": {"miles": 0.0, "segments": 0, "projects": collections.Counter()}}
    baseline = {"miles": 0.0, "segments": 0}
    gained = {"miles": 0.0, "segments": 0}
    for f in aa["features"]:
        pr = f["properties"]
        # Row miles, the plan's unit, written by bike-network-history.py; the
        # line's own length (once per block) is the fallback for an older file.
        mi = pr.get("miles") if pr.get("miles") is not None else line_miles(f["geometry"]["coordinates"])
        if pr["first"] == first_year:
            baseline["miles"] += mi
            baseline["segments"] += 1
            continue
        gained["miles"] += mi
        gained["segments"] += 1
        cands = cover.get(pr["cnn"] or "", [])
        if len(cands) > 1:
            # Several project lines over one block, which is the norm in SoMa.
            # The one whose name is the block's street is the one that built
            # it (Folsom-Howard on Howard, 7th and 8th Street on 8th); when
            # none or several name it, the block stays unattributed. One
            # narrow exception follows, for a namesake whose page dates its
            # work to other years.
            named = [n for n in cands if street_in_name(pr.get("name"), projects[n]["name"]) and not NOT_A_BUILDER.search(projects[n]["name"])]
            if len(named) == 1 and not before_start(named[0], pr["first"], name_rule=True) \
                    and dates_fit(named[0], pr["first"]) is not False:
                cands = named
            elif len(named) == 1 and not before_start(named[0], pr["first"], name_rule=True):
                # The street's namesake does not fit the block's year: the
                # block goes to the one project whose own page dates work to
                # that year. Dr. Carlton B. Goodlett Place continues Polk
                # Street, so its 2024 block is POLK ST in the layer, where Polk
                # Streetscape (built 2019) won the name and then failed its years.
                dated = [n for n in cands if n != named[0] and not NOT_A_BUILDER.search(projects[n]["name"])
                         and street_in_name(pr.get("name"), page_text(projects[n]))
                         and not before_start(n, pr["first"], name_rule=True) and dates_fit(n, pr["first"])]
                if len(dated) == 1:
                    cands = dated
                else:
                    cands = named  # reported below as outside the namesake's build years
        if not cands and pr.get("name") and not components.get(pr["key"], {}).get("s"):
            # No project line over the block at all. A built project named for
            # the block's street, whose own blocks include that street, is
            # credited when it is the only one (the 2023 Valencia centre-running
            # bikeway sits outside Valencia Bikeway Improvements' published
            # line). Studies, plans and programmes never build, so never count.
            named = [n for n in street_projects.get(norm(pr["name"]), ()) if street_in_name(pr["name"], projects[n]["name"])]
            if len(named) == 1 and not before_start(named[0], pr["first"], name_rule=True):
                cands = named
                name_fallback[projects[named[0]]["name"]] += mi
        if not cands and pr.get("name") and components.get(pr["key"], {}).get("s"):
            # A Slow Street with no project line over it. SFMTA's Slow Streets
            # pages are one per street, and several have no geometry at all,
            # so the block is credited to the page whose name is the street's,
            # or to a stand-in named from the Slow Streets dataset when no
            # page exists (Bryan, 2026-09-23: "a number of major projects have
            # no label. Please reconcile").
            title = street_title(pr["name"])
            # SFMTA names the pages both ways: "Shotwell Slow Street", "12th Avenue Slow Street".
            bare = " ".join(title.split()[:-1]) if title.split()[-1] in SUFFIX.values() else title
            node = by_norm_name.get(norm(title + " Slow Street")) or by_norm_name.get(norm(bare + " Slow Street"))
            # A page still in planning or design describes the next change to
            # the street, not the Slow Street already on it.
            if node is not None and not could_have_built(projects[node]):
                node = None
            if node is None:
                node = "slow:" + norm(title)
                projects.setdefault(node, {"node": node, "name": title + " Slow Street", "phase": None, "teaser": None, "types": ["Bike"],
                                           "page": "https://data.sf.gov/d/hkz3-itiu", "stand_in": True})
            cands = [node]
        if len(cands) == 1 and before_start(cands[0], pr["first"]):
            # The project's own timeline starts after the block was built, so
            # it cannot be what built it (Valencia Bikeway Improvements, whose
            # timeline starts in 2022, on a block built in 2017).
            year_refused[projects[cands[0]]["name"]] += mi
            cands = []
        if len(cands) == 1 and not projects[cands[0]].get("stand_in"):
            w = build_window(projects[cands[0]])
            if w and not (w[0] <= pr["first"] <= w[1]):
                # The block became all-ages in a year the project's page does
                # not date any work to: another project on the same street
                # (the Arguello block on the Clay Slow Street, Sanchez on the
                # 17th Street project), or a later change to it.
                window_refused[projects[cands[0]]["name"]].append((pr["name"], pr["first"], round(mi, 2)))
                cands = []
        if len(cands) == 1:
            node = cands[0]
            attributed_key[pr["key"]] = node
            d = per[node]
            d["miles"] += mi
            d["segments"] += 1
            d["years"].add(pr["first"])
            coords = f["geometry"]["coordinates"]
            mid = coords[len(coords) // 2]
            by = d["by_year"][pr["first"]]
            by["miles"] += mi
            by["lon"] += mi * mid[0]
            by["lat"] += mi * mid[1]
            if pr.get("name"):
                d["streets"][pr["name"]] += 1
            d["blocks"].append(pr["key"])
            comp = components.get(pr["key"])
            ys, i = seg_class.get(pr["cnn"]), seg_years.index(pr["first"]) if pr["first"] in seg_years else 0
            how = d["upgraded"] if ys and i > 0 and ys[i - 1] != "0" else d["added"]
            if comp:
                for code, code_mi in comp["m"].items():
                    d["facilities"][code] += code_mi
                    how[code] += code_mi
                if comp.get("s") is not None:
                    d["facilities"]["S"] += comp["s"]
                    how["S"] += comp["s"]
        elif not cands:
            un["none"]["miles"] += mi
            un["none"]["segments"] += 1
        else:
            un["multi"]["miles"] += mi
            un["multi"]["segments"] += 1
            un["multi"]["projects"][" / ".join(sorted(projects[n]["name"] for n in cands))] += 1

    # Runs no project record names, by street and year, so the overview map can
    # still name a large one (the Bay Trail, Anza Street) in its own quieter
    # style. They stay unattributed: no miles, residents or schools go to them.
    runs = collections.defaultdict(lambda: {"miles": 0.0, "lon": 0.0, "lat": 0.0})
    for f in aa["features"]:
        pr = f["properties"]
        if pr["first"] == first_year or pr["key"] in attributed_key or not pr.get("name"):
            continue
        mi = pr.get("miles") if pr.get("miles") is not None else line_miles(f["geometry"]["coordinates"])
        coords = f["geometry"]["coordinates"]
        mid = coords[len(coords) // 2]
        r = runs[(pr["name"], pr["first"])]
        r["miles"] += mi
        r["lon"] += mi * mid[0]
        r["lat"] += mi * mid[1]
    unnamed_runs = [{"name": street_title(name), "year": yr, "miles": round(r["miles"], 2),
                     "lon": round(r["lon"] / r["miles"], 5), "lat": round(r["lat"] / r["miles"], 5)}
                    for (name, yr), r in sorted(runs.items(), key=lambda kv: -kv[1]["miles"]) if r["miles"] >= 0.5]

    # Reach: the point goes to the project of the block that first reached it.
    un_reach = {"residents": 0, "schools": [], "libraries": []}
    base_reach = {"residents": 0, "schools": 0, "libraries": 0}
    for lon, lat, pop, y, near, *_ in reach["blocks"]["rows"]:  # later columns hold the other distances
        if not y:
            continue
        if y == first_year:
            base_reach["residents"] += pop
        elif near in attributed_key:
            per[attributed_key[near]]["residents"] += pop
        else:
            un_reach["residents"] += pop
    for kind in ("schools", "libraries"):
        for s in reach[kind]:
            if not s["reach"]:
                continue
            if s["reach"] == first_year:
                base_reach[kind] += 1
            elif s.get("near") in attributed_key:
                per[attributed_key[s["near"]]][kind].append(s["name"])
            else:
                un_reach[kind].append(s["name"])

    rows = []
    for node, d in per.items():
        p = projects[node]
        rows.append({"node": node, "name": p["name"], "page": p["page"], "phase": p.get("phase"), "stand_in": bool(p.get("stand_in")),
                     # SFMTA's own one-line summary of the project, quoted on the card as its words.
                     "teaser": (p.get("teaser") or "").strip() or None, "image": images.get(node), "thumb": thumbs.get(node), "types": p.get("types") or [], "bike_from_page": bool(p.get("bike_from_page")),
                     "blocks": sorted(d["blocks"]),
                     "facilities": {code: round(m, 2) for code, m in sorted(d["facilities"].items()) if m > 0},
                     "added": {code: round(m, 2) for code, m in sorted(d["added"].items()) if m > 0},
                     "upgraded": {code: round(m, 2) for code, m in sorted(d["upgraded"].items()) if m > 0},
                     "miles": round(d["miles"], 2), "segments": d["segments"],
                     "years": [min(d["years"]), max(d["years"])],
                     # Whether the project's own page dates its building, or only the bikeway layer does.
                     "dated_by": "page" if not p.get("stand_in") and build_window(p) else "layer",
                     "residents": int(d["residents"]), "schools": sorted(d["schools"]), "libraries": sorted(d["libraries"]),
                     "streets": [s for s, _ in d["streets"].most_common(4)],
                     "by_year": [{"year": y, "miles": round(b["miles"], 2),
                                  "lon": round(b["lon"] / b["miles"], 5), "lat": round(b["lat"] / b["miles"], 5)}
                                 for y, b in sorted(d["by_year"].items()) if b["miles"] > 0]})
    rows.sort(key=lambda r: -r["miles"])

    out = {
        "excluded_unbuilt": sorted(excluded, key=lambda e: e["name"]),
        "generated": dt.date.today().isoformat(),
        "years": years,
        "rule": ("A block that became all-ages after %d is attributed to an SFMTA project when exactly one project's published line geometry "
                 "covers the block and SFMTA tags the project Bike or its page lists bicycle infrastructure improvements; when several cover it, "
                 "the one whose name is the block's street, or, when that project's page dates its work to other years, the one whose page dates work to the block's year. "
                 "A project SFMTA lists in planning or design counts only when its page says the work is complete. "
                 "The block's year must fall within a year of the years the project's own page dates its construction or installation to. "
                 "A Slow Street with no project line goes to SFMTA's page for that street, or to a stand-in named from the Slow Streets dataset. "
                 "Area (polygon) projects are excluded. A resident, school or branch is "
                 "attributed to the project of the block that first brought it within %.2f miles." % (first_year, reach["reach_miles"])),
        "residents_basis": "Census 2020 block population (pop20), at the block's interior point",
        "miles_basis": "Row miles per direction row, the Biking and Rolling Plan's unit, as written by tools/bike-network/bike-network-history.py",
        "baseline": {"miles": round(baseline["miles"], 1), "segments": baseline["segments"],
                     "residents": base_reach["residents"], "schools": base_reach["schools"], "libraries": base_reach["libraries"]},
        "gained": {"miles": round(gained["miles"], 1), "segments": gained["segments"]},
        "attributed": {"miles": round(sum(r["miles"] for r in rows), 1), "segments": sum(r["segments"] for r in rows), "projects": len(rows)},
        "unattributed": {
            "miles": round(un["none"]["miles"] + un["multi"]["miles"], 1),
            "segments": un["none"]["segments"] + un["multi"]["segments"],
            "no_project_on_block": {"miles": round(un["none"]["miles"], 1), "segments": un["none"]["segments"]},
            "more_than_one_project_on_block": {"miles": round(un["multi"]["miles"], 1), "segments": un["multi"]["segments"],
                                               "pairs": un["multi"]["projects"].most_common(8)},
            "residents": int(un_reach["residents"]), "schools": len(un_reach["schools"]), "libraries": len(un_reach["libraries"]),
        },
        "outside_build_years": {name: [{"street": b[0], "year": b[1], "miles": b[2]} for b in blocks]
                                for name, blocks in sorted(window_refused.items())},
        "mileBasis": BASIS,
        "projects": rows,
        "unnamed_runs": unnamed_runs,
        "sources": {
            "project_geometry": {"name": "SFMTA project layer, live from its ArcGIS service, matched to blocks by tools/projects/project-blocks.py",
                                 "generated": pblocks["generated"], "tolerances_m": pblocks["tolerancesM"]},
            "network": aa["sources"]["network"],
            "reach": {k: reach["sources"][k] for k in ("schools", "libraries", "blocks")},
        },
    }
    stable.write_json(OUT, out, end="", indent=1, ensure_ascii=False)
    print("  %d blocks / %.1f mi became all-ages after %d; %.1f mi attributed to %d projects, %.1f mi unattributed (%.1f no project, %.1f more than one)"
          % (gained["segments"], gained["miles"], first_year, out["attributed"]["miles"], len(rows),
             out["unattributed"]["miles"], un["none"]["miles"], un["multi"]["miles"]))
    for r in rows[:12]:
        print("  %5.2f mi  %7d residents  %2d schools  %d libs  %s (%s) %s" % (r["miles"], r["residents"], len(r["schools"]), len(r["libraries"]), r["name"], r["phase"], r["years"]))
    for name, m in year_refused.most_common():
        print("  refused, block predates the project's timeline: %5.2f mi  %s" % (m, name))
    for name, blocks in sorted(window_refused.items()):
        print("  refused, outside the page's build years: %s: %s" % (name, ", ".join("%s %d (%.2f mi)" % b for b in blocks)))
    for name, m in name_fallback.most_common():
        print("  name fallback: %5.2f mi  %s" % (m, name))
    print("  unattributed reach: %d residents, %d schools, %d libraries" % (un_reach["residents"], len(un_reach["schools"]), len(un_reach["libraries"])))
    print("  wrote %s" % OUT)


if __name__ == "__main__":
    main()
