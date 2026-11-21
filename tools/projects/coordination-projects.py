#!/usr/bin/env python3
"""Upcoming SFMTA, Public Works and SFPUC projects on the plan's network, with what each would enable and what its scope leaves out.

    tools/projects/coordination-projects.py
    tools/projects/coordination-projects.py --today 2026-11-29   # as if run that day: the output must not change

Reads what other scripts in this repo already built and writes
site/data/coordination.json for the site's /transportation/bike/projects pages.
Nothing here reaches the network: the Public Works feed comes from the
Socrata cache (lib/sfdata.py) and every other input is a file.

Inputs
  out/project-record/projects.json      one record per project, SFMTA and
                                        Public Works, with the city's own
                                        documents linked in (project-record.py)
  out/project-record/project-blocks.json which blocks an SFMTA shape covers,
                                        and whether the shape is a line or
                                        an area (project-blocks.py)
  data/socrata-cache btxj-k9uh          the interagency coordination feed, for
                                        each job's dates, streets, owner
                                        agency and published scope
  site/data/north-star/traced.geojson   the plan's network, one line per block,
                                        with the facility the plan names
  site/data/bike-history/all-ages.geojson  blocks already built to the
                                        all-ages standard
  site/data/bike-history/reach.json     census blocks, schools and branches
                                        with the year each came within walking
                                        reach of that network at each of the
                                        overview's distances, and the years
                                        out of reach after; 0 = never
  data/osm-cache/sf-walk.json and data/extract/census-blocks/outlines-*.json
                                        the walk network and block frontages
                                        the walk is measured along and from
                                        (lib/walknet.py)
  site/data/bike-history/segments.json  bikeway-layer geometry, for SFMTA
                                        blocks the plan does not draw
  site/data/north-star/status.json      each plan block's metres on direction
                                        rows that meet the plan's type today
  site/data/bike-history/projects.json  blocks the bikeway history credits to
                                        each SFMTA project
  site/data/bike-history/planned.json,  blocks and bikeway class SFMTA's pages
    reported.json                       name for work to come or reported
                                        this year; these three feed the plan
                                        rating (plan_rating, "The plan rating")
  out/sfmta-page-dates/dates.json       construction and consultation dates
                                        TypeSafe's Jev read off each SFMTA
                                        page (sfmta-page-dates.py); used
                                        where the page's timeline, event
                                        cards and construction sentences
                                        give none (with_page_dates)

Which projects are listed
  A project is listed when its owner is SFMTA, Public Works or the SFPUC, it
  has not finished, either its blocks touch the plan's network or its
  published scope names bike work, and its name reads as street work
  (work_kind below): repaving, sewer, water and power, streetscape and
  safety, spot repairs, or SFMTA's own bike and safety construction. The rest
  are kept by name in notStreetWork. A programme page is not a project: a row
  whose name and SFMTA page title name no place, on a page with no timeline
  and no phase, is kept in programmes instead (Slow Streets).

  SFMTA projects come from every project on SFMTA's project layer and every
  /projects/ page in sfmta.com's sitemap (Bryan, 2026-09-28: "We should never
  miss an SFMTA project that has something to do with biking or pedestrian
  infrastructure"). One is listed when its own scope touches biking or
  walking: SFMTA tags it Bike, Walk, Vision Zero or Quick-Build, or its name
  uses a bike or pedestrian word (SCOPE_FAMILIES), or its page text uses
  words from two of those families, or one that is itself a change to a
  street (quick-build, slow street, traffic calming, crossing), and its name
  places it on a street, a Muni line or in a neighbourhood. It is left off
  when it is finished (the layer's phase, or its page says complete), when a
  page SFMTA does not map shows no dated activity since the start of last
  year, or when it is station or facility work with no Bike or Quick-Build
  tag and no bike or pedestrian word in its name. A
  project the layer gives no phase takes its page's "Current Phase or Stage",
  and shows "phase not published" when the page has none. Every decision and
  its reason is written to out/coordination/sfmta-decisions.json.

  An SFMTA project and a feed row for the same project are one row: same
  name, or the feed row matched to the project's page by
  scripts/department-project-pages.py.

Department pages
  Each row links its department's own project page where
  tools/projects/department-project-pages.py matched one at high or medium
  confidence (out/department-pages/matches.json), before the DataSF row.

Reach
  The same test tools/bike-network/bike-network-history.py uses for the overview: a
  census block, a school (public or private K-12) or a branch is within reach
  when the walk along OpenStreetMap's walk network to one of the project's
  lines is at most the distance, measured from a block's street frontage and
  from a school's or branch's own point (lib/walknet.py). The distances
  are the overview's, from reach.json's `thresholds`: one block (440 ft), two
  blocks (880 ft) and the plan's quarter mile, which is the default and fills
  the top-level figures. Only points not already within that distance of
  today's all-ages network are counted, so the figure is what the project
  would add; "today" is reach.json's latest year, in which a point is within
  reach when 0 < reach <= year and the year is not in its `off` list, exactly
  as the overview's map lights it. Each distance is measured against what is
  already within that distance today, so the three figures need not nest: a
  block with an all-ages bikeway three blocks off counts at one block and not
  at the quarter mile. The project's lines are the plan's traced blocks (else
  the bikeway layer's), where the overview walks from the layer's own lines;
  both attach to OSM edges within 20 m, so the method is the same. For a Public Works or SFPUC
  job the lines are its blocks on the plan's network; for an SFMTA project
  they are every block its published line covers. A project published as an
  area rather than a line gets no reach figure.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import seasons, stable  # noqa: E402
from sfdata import fetch  # noqa: E402
from bikeway_snap import shared_snapper  # noqa: E402
from mile_basis import BASIS  # noqa: E402
from plan_directions import Directions  # noqa: E402
from streetnames import streets as streets_of  # noqa: E402
from streetindex import StreetIndex, canon  # noqa: E402
from lib.pw_extent import Extents  # noqa: E402
from lib import project_ids  # noqa: E402
from lib.samename import same_name  # noqa: E402
import walknet  # noqa: E402

RECORD = os.path.join(ROOT, "out", "project-record", "projects.json")
BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")
TRACED = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
ALL_AGES = os.path.join(ROOT, "site", "data", "bike-history", "all-ages.geojson")
REACH = os.path.join(ROOT, "site", "data", "bike-history", "reach.json")
WALK_REACH = os.path.join(ROOT, "site", "data", "bike-history", "walk-reach.json")
SEGMENTS = os.path.join(ROOT, "site", "data", "bike-history", "segments.json")
OUT = os.path.join(ROOT, "site", "data", "coordination.json")

FEED = "btxj-k9uh"
FEED_URL = "https://data.sf.gov/d/btxj-k9uh"
ROW_URL = "https://data.sf.gov/resource/btxj-k9uh.json?dotmapsid={}"

MILE = 1609.344
REACH_MILES = 0.25

# The same words tools/projects/street-work-list.py and the site's collector read a
# scope with, so the two pages cannot disagree about whether a job names bike
# work.
BIKE_WORDS = re.compile(
    r"\bbike|\bbicycl|bikeway|cycle ?track|cycletrack|sharrow|greenway|slow street|quick.?build|protected lane|buffered lane",
    re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

DEPARTMENTS = (
    ("SF MTA", "SFMTA"),
    ("SF DPW", "Public Works"),
    ("SF PUC", "SFPUC"),
)

# How far a phase is from a shovel, for the projects that publish no date.
PHASE_ORDER = {
    "Construction": 0, "Implementation / Construction": 0,
    "Legislated": 1,
    "Design": 2, "Detailed Design": 2,
    "Current": 3,
    "Planning": 4,
}


# Feed jobs with no department page and no closest official source, with what
# was searched (read from the department-page matches in main()).
no_source = {}


def phase_rank(phase):
    """PHASE_ORDER for the layer's and the feed's words, and a page's own ("Planning & Outreach")."""
    if phase in PHASE_ORDER:
        return PHASE_ORDER[phase]
    for rx, n in ((r"construct|implement", 0), (r"legislat", 1), (r"design", 2), (r"current|progress", 3),
                  (r"plan|outreach|listening", 4)):
        if re.search(rx, phase or "", re.I):
            return n
    return 9


# The inclusion rule for SFMTA projects, in one sentence, for About the data.
# The SFMTA Board adopted the Biking and Rolling Plan on this day (site/data/bike-progress.json "adopted").
PLAN_ADOPTED = "2025-03-04"

SFMTA_RULE = ("An SFMTA project is listed when SFMTA tags it Bike, Walk, Vision Zero or Quick-Build, or its name "
              "or page names bike, slow street, quick-build, pedestrian, crossing, signal, traffic calming, safety or "
              "streetscape work, and it is not finished (by the layer's phase or its own page), not station, fleet or "
              "parking work, and, if SFMTA does not map it, its page shows something dated this year or last. A "
              "mapped project with no phase on the layer or its page whose timeline ends before last year, or one "
              "whose only walking or safety scope is in its page's words, is listed while its page dates work in the last year or to come, or the "
              "coordination feed carries its job. Any "
              "other project SFMTA maps on a plan block (transit, parking or wiring work on the same streets) is "
              "listed too, as transit or parking work, while its page dates a milestone, notice or construction date "
              "in the last two years or to come, or the coordination feed carries its job, unless it is a study, a "
              "plan, a pilot or work inside a station, tunnel, transit center, yard or vehicle.")

KIND_LABEL = {
    "hearing": "Engineering hearing",
    "board": "SFMTA Board",
    "supervisors": "Board of Supervisors",
    "sfpuc": "SFPUC Commission",
    "pwc": "Public Works Commission",
    "sfcta": "SFCTA Board",
    "recpark": "Recreation and Park Commission",
    "project-page": "SFMTA project page",
}
# A project page's own items say which block of the page they came from, so a
# community open house reads as one and never as a body's vote.
# The relation tools/projects/project-record.py gives an item off the project's own
# page; the audit (C3a, C4) reads this exact string.
OWN_PAGE_RELATION = "listed on this project's own page"
PAGE_LABEL = {"timeline": "Project page timeline", "notice": "Project page notice",
              "event": "Project page event"}


def record_label(r):
    if r["kind"] == "project-page":
        return PAGE_LABEL.get(r.get("pageBlock") or "timeline", KIND_LABEL["project-page"])
    # A Board of Supervisors committee's action (a recommendation, an
    # amendment in committee) is not the Board's: the label names the
    # committee, which is how the Legistar record reads.
    if r["kind"] == "supervisors" and re.search(r"\bCommittee\b", r.get("approver") or ""):
        return "Board of Supervisors, " + r["approver"]
    # A contract the Director approved under the Public Works Commission's
    # delegation, listed in the report to the Commission: the Director's act,
    # never labelled as a Commission vote.
    if r["kind"] == "pwdelegated":
        return "Delegated award (Public Works)" if r.get("award") else "Delegated contract change (Public Works)"
    return KIND_LABEL.get(r["kind"], r["kind"])

# What kind of street work a project is, read from its name. Bryan,
# 2026-09-23, on Current Projects: "Can we filter on projects that might have
# some relationship with work near a bike path? Like sewage, repaving, etc. are
# good. Projects like Castro's new station elevator, or upgrading traffic
# cameras doesn't have anything to do with bikeways." The first pattern that
# matches wins, so a spot sewer contract is a spot repair, not a sewer job.
WORK_KINDS = [
    # Spot and as-needed contracts repair points along a street rather than
    # whole blocks, so a block they list is a weaker chance than a repave.
    ("spot repairs", re.compile(r"as[ -]needed|\bspot\b|trash capture", re.I)),
    ("repaving", re.compile(r"paving|pavement|resurfac", re.I)),
    ("sewer, water and power", re.compile(
        # A force main is a pressurised sewer pipe (SFPUC's Channel Force
        # Main Intertie, under Cesar Chavez Street, read 2026-09-29).
        r"sewer|\bwater\b|stormwater|outfall|pipe|\bCSD\b|irrigation|electrical|\bEFWS\b|manifold|force main", re.I)),
    ("streetscape and safety", re.compile(
        r"streetscape|safety|multimodal|muni forward|rapid|sidewalk|curb ramp|quick-build|\bbike\b|bicycl|"
        # Street work named for its street or its junction (Public Works'
        # "Beale Street Improvement Project", "Alemany Interchange Improvement
        # Project", "Page Street Neighborway Project").
        r"neighborway|intersection|traffic signal|\bbridge\b|interchange|"
        # The Bay Trail is the plan's shared path along the shore; Public
        # Works' "Marina Bay Trail Planning" redesigns it on Marina Boulevard
        # from Scott to Baker (its page, read 2026-09-28).
        r"\bbay trail\b|"
        r"\b(?:street|avenue|boulevard|st|ave|blvd)\b (?:infrastructure )?improvement", re.I)),
]
SFMTA_PAGES = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")  # tools/projects/sfmta-project-pages.py --sitemap
DEPT_MATCHES = os.path.join(ROOT, "out", "department-pages", "matches.json")  # tools/projects/department-project-pages.py
DEPT_PAGES = os.path.join(ROOT, "out", "department-pages", "pages.json")  # the same, every page read
DPW_PROJECTS = os.path.join(ROOT, "data", "extract", "dpw-projects", "projects.json")  # tools/projects/dpw-projects.py
PUC_PROJECTS = os.path.join(ROOT, "data", "extract", "sfpuc-projects", "projects.json")  # department-project-pages.py
# Meetings not yet held, from tools/meetings/upcoming-meetings.py; tools/projects/project-record.py
# matches them to projects as each project's "upcoming" list.
UPCOMING = os.path.join(ROOT, "data", "upcoming-meetings", "meetings.json")
# How far ahead the list's "meeting coming up" group looks (Bryan, 2026-09-29:
# "highlight projects with upcoming meetings").
MEETING_DAYS = 60
# "Early enough to change" (Bryan, 2026-09-29: "highlight other projects that
# might be early enough to do something about them"): the department's own
# current phase is planning, design or outreach. A phase that names
# construction, implementation, legislation or completion is past that point.
EARLY_PHASE = re.compile(r"plan|design|outreach|listening|study", re.I)
LATE_PHASE = re.compile(r"construct|implement|complet|legislat", re.I)


# The bodies that decide street projects, for the line naming their next
# meetings whose agendas are not yet posted.
DECIDING = re.compile(r"^(SFMTA Board of Directors|SFMTA engineering public hearing|Board of Supervisors"
                      r"|Land Use and Transportation Committee|Public Works Commission|SFPUC Commission)$")


def upcoming_summary(today):
    """What the meetings file read, and each deciding body's next meeting with no agenda posted yet."""
    if not os.path.exists(UPCOMING):
        return None
    with open(UPCOMING, encoding="utf-8") as fh:
        u = json.load(fh)
    horizon = (dt.date.fromisoformat(today) + dt.timedelta(days=MEETING_DAYS)).isoformat()
    pending = {}
    for m in u["meetings"]:
        if (DECIDING.match(m["body"]) and not m["agendaPosted"] and today < m["date"] <= horizon
                and m["body"] not in pending):
            pending[m["body"]] = {"body": m["body"], "date": m["date"], "time": m.get("time"), "url": m["url"],
                                  "special": bool(re.search(r"\bspecial\b", m.get("title") or "", re.I))}
    return {"days": MEETING_DAYS, "read": u["generated"],
            "sources": [{k: x.get(k) for k in ("id", "name", "listing", "status")} for x in u["sources"]],
            "gaps": u["gaps"],
            "agendaPending": sorted(pending.values(), key=lambda x: (x["date"], x["body"]))}


def is_early(phase):
    return bool(phase and EARLY_PHASE.search(phase) and not LATE_PHASE.search(phase))
PW_ACTIVE = ("in progress", "active", "under construction", "construction")
DECISIONS = os.path.join(ROOT, "out", "coordination", "sfmta-decisions.json")
# Each candidate's outcome at the published-end step, which a row whose end is
# an unchecked model read keeps (see "Past their published end" in main()).
HELD_LISTING = os.path.join(ROOT, "data", "coordination", "held-listing.json")
# Each department's own website, for counting rows linked to their own project page.
DEPT_SITE = {"SFMTA": r"^https?://(?:www\.)?sfmta\.com/",
             "Public Works": r"^https?://(?:www\.)?(?:sfpublicworks\.org|bidopportunities\.apps\.sfdpw\.org)/",
             "SFPUC": r"^https?://(?:www\.|webapps\.)?sfpuc\.(?:gov|org)/"}

# Which SFMTA projects touch biking or walking. SFMTA's own layer tags are the
# first test; its name and page are the second, because the Bike tag alone
# missed 25 of 29 active on-plan projects (data-quality.md A1, 2026-09-28):
# Innes Avenue Quick-Build and Cayuga Avenue Slow Street carry no Bike tag.
SFMTA_TAGS = ("Bike", "Walk", "Vision Zero", "Quick-Build")
SCOPE_FAMILIES = {
    "bike": r"\bbike|\bbicycl|bikeway|cycle ?track|sharrow",
    "slow street": r"slow streets?|neighborway|greenway|play streets?",
    "quick-build": r"quick.?build",
    "pedestrian": r"pedestrian|sidewalk|walk(?:ing)? (?:safety|route)",
    "crossing": r"crosswalk|bulb.?outs?|curb extension|curb ramps?|daylight|refuge island|boarding island|pedestrian island",
    "signal": r"traffic signal|new signals?|signal (?:upgrade|modification|retiming)|leading pedestrian interval|"
              r"rectangular rapid|flashing beacon",
    "traffic calming": r"traffic calming|speed humps?|speed cushions?|speed tables?|road diet|lane reduction|raised crosswalk|neckdown",
    "safety project": r"safety project|safety improvement|vision zero|high.injury|safe streets|safe school|street safety",
    "streetscape": r"streetscape|promenade|\bplaza\b",
}
SCOPE_RX = {k: re.compile(v, re.I) for k, v in SCOPE_FAMILIES.items()}
# Transit stations, yards and vehicles: SFMTA tags some of them Walk for their
# accessibility work, and none of them is a street.
SFMTA_FACILITY = re.compile(
    r"\bstation\b|elevator|escalator|\byard\b|facilit|tunnel|substation|overhead wiring|train control|"
    r"fuel tank|fleet|garage|traction power|irrigation|\bbus wash|charging|light rail vehicle|streetcar|trolley coach|cable car|"
    r"\bart\b|budget|\bfares?\b|parking|permit|curb management|loading", re.I)
# A Muni line in a project's name ("5 Fulton", "K Ingleside", "29 Sunset")
# places it on a corridor as a street name would.
MUNI_ROUTE = re.compile(r"(?:^|\s)(?:\d{1,2}[RX]?|[A-Z]) (?!Street|Avenue)[A-Z][a-z]+")
_STREET_BASES = None
# San Francisco's neighbourhoods by name, which place a project as a street
# does ("Tenderloin Speed Limits", "Bayview Community Based Transportation Plan").
NEIGHBOURHOOD = re.compile(
    r"\b(?:tenderloin|soma|south of market|bayview|hunters point|excelsior|chinatown|japantown|nob hill|"
    r"russian hill|north beach|marina|cow hollow|pacific heights|western addition|fillmore|hayes valley|"
    r"haight|castro|noe valley|glen park|bernal heights|potrero hill|dogpatch|mission bay|visitacion valley|"
    r"portola|oceanview|ingleside|outer mission|crocker.amazon|sunnydale|lakeshore|parkside|outer sunset|"
    r"inner sunset|inner richmond|outer richmond|sea ?cliff|presidio|treasure island|west of twin peaks|"
    r"district \d{1,2}|civic center|financial district|union square)\b", re.I)
# Street names that are also everyday words in a programme's title.
_NOT_A_PLACE = {"park", "lake", "central", "city", "bay", "hill", "view", "point", "west", "east", "north",
                "south", "school", "transit", "access", "safety", "project", "program", "plan", "light", "rail",
                "service", "street", "streets", "slow", "shared", "art", "bus", "express", "loop", "all",
                "san", "francisco", "san francisco", "forest hill"}
SUFFIX_TYPES = {"st", "ave", "blvd", "dr", "rd", "way", "pl", "ct", "ln", "ter", "aly", "cir", "hwy", "plz",
                "pkwy", "path", "stwy", "walk", "row", "hl", "tunl", "ramp"}


def names_a_place(name):
    """Does a project's name put it on a street, a Muni line or in a neighbourhood, as a programme or report page's does not?"""
    global _STREET_BASES
    if streets_of(name) or MUNI_ROUTE.search(name) or NEIGHBOURHOOD.search(name):
        return True
    if _STREET_BASES is None:
        # The centreline's street names without their type: "embarcadero", "geary", "twin peaks".
        idx = StreetIndex()
        _STREET_BASES = set()
        for k in idx._cnns:
            parts = re.sub(r"^the ", "", idx.display(k)).split()
            if len(parts) > 1 and parts[-1] in SUFFIX_TYPES:
                parts = parts[:-1]
            _STREET_BASES.add(" ".join(parts))
    ws = re.findall(r"[A-Za-z]+", name)
    grams = {w.lower() for w in ws} | {" ".join(ws[i:i + 2]).lower() for i in range(len(ws) - 1)}
    return bool({g for g in grams if g not in _NOT_A_PLACE} & _STREET_BASES)


FINISHED_PHASES = ("Completed", "Project Evaluation", "test")
# One of these in a page is enough on its own: each is a change to a street.
STREET_WORK_FAMILIES = {"quick-build", "slow street", "traffic calming", "crossing"}
PAGE_DONE = re.compile(r"^(?:completed?\b|substantially complete|project is substantially complete|"
                       r"planning process complete)", re.I)


def unmangle(s):
    """Undo UTF-8 read as Latin-1 in SFMTA's layer: "Project \u00e2\u0080\u0093 Phase Two" is "Project \u2013 Phase Two"."""
    if s and "\u00e2" in s:
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


def bike_named(name):
    """Does a project's name say bike or slow street work?"""
    return bool({"bike", "slow street"} & set(scope_families(name)))


# Studies, area plans and development agreements: listed when they touch
# walking or biking, but not bike work on the blocks their areas cover.
SFMTA_NOT_BUILT = re.compile(
    r"\bStudy\b|\bPlan\b(?!.*Implementation)|Treasure Island|Parkmerced|Candlestick", re.I)


def scope_families(text):
    return sorted(k for k, rx in SCOPE_RX.items() if rx.search(text or ""))


def page_activity(pg):
    """The latest dated thing on an SFMTA page: timeline, notices, meetings, else a year in its prose."""
    dates = []
    for t in pg.get("timeline") or ():
        d = season_date(t.get("when"))
        if d:
            dates.append(d[:4])
    dates += [x["date"][:4] for x in (pg.get("notices") or []) + (pg.get("meetings") or []) if x.get("date")]
    if dates:
        return max(dates), "its dated timeline, notices and meetings"
    years = [y for y in re.findall(r"\b(20[0-4]\d)\b", pg.get("pageText") or "") if int(y) <= data_today().year + 10]
    return (max(years), "the latest year its text names") if years else (None, None)


PROSE_DONE = re.compile(r"\bproject\s+(?:is\s+now|was|has\s+been)\s+(?:successfully\s+|substantially\s+|fully\s+)?"
                        r"complete(?:d)?\b", re.I)
# A sentence about one phase, stretch or step of a project is not the project
# ("The Quick-Build portion of the 6th Street Pedestrian Safety Project was
# completed in September 2019").
PROSE_PART = re.compile(r"\b(?:phase|stage|segment|first|portion|part|survey|planning|design|outreach|evaluation|"
                        r"quick.?build)\b", re.I)


def prose_done(text):
    """The sentence in which an SFMTA page says the project itself is complete, or None."""
    for s in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        m = PROSE_DONE.search(s)
        if m and not PROSE_PART.search(s):
            # The page's header runs into its first sentence with no full
            # stop ("... Share this: Facebook Twitter LinkedIn SFMTA.com/X
            # Project Update 06/11/2021: The project is now ..."); keep the
            # sentence from the update heading on.
            s = re.sub(r"^.*?\bLinkedIn\s+(?:SFMTA\.com/\S+\s+)?", "", s)
            m = PROSE_DONE.search(s)
            head = s.lower().rfind("project update", 0, m.start())
            if head < 0:
                head = s.rfind(" ", 0, max(0, m.start() - 90)) + 1  # a whole word, about 90 characters back
            return s[head:].strip()
    return None


def page_evidence(pg):
    """The latest year-month an SFMTA page dates anything to: a timeline stage's start or end, a notice, or a
    construction start or finish in its prose. Meetings are left out: the page's events block also carries
    unrelated calendar items (Twin Peaks Tunnel Improvements lists a 2026 Bloomsday event)."""
    dates = []
    for t in pg.get("timeline") or ():
        dates += [d[:7] for d in (season_date(t.get("when")), stage_end(t.get("when"))) if d]
    dates += [x["date"][:7] for x in pg.get("notices") or [] if x.get("date")]
    s, e, _ = prose_dates(pg.get("pageText"))
    dates += [d[:7] for d in (s, e) if d]
    return max(dates) if dates else None


def evidence_cutoff(today=None, years=2):
    """`years` before today's month: a page dated nothing since is not evidence of current work."""
    t = today or data_today()
    return "%04d-%02d" % (t.year - years, t.month)


# A month or season with its year, anywhere in a page's prose ("will complete
# its detailed design phase in Early 2027", "in March 2026, we installed").
PROSE_WHEN = re.compile(r"\b(?:(?:early|mid|late|end of)[- ]|(?:january|february|march|april|may|june|july|august|"
                        r"september|october|november|december|winter|spring|summer|fall|autumn)\s+)(20\d\d)\b", re.I)


def current_evidence(pg):
    """The latest year-month an SFMTA page dates anything to: page_evidence(), or a month or season with its year
    in its prose. A bare year is not read: it is as often a plan's horizon or a crash-data range as a date of work."""
    dates = [page_evidence(pg) or ""]
    for m in PROSE_WHEN.finditer(" ".join((pg.get("pageText") or "").split())):
        if int(m.group(1)) <= data_today().year + 10:
            dates.append(season_date(m.group(0)) or "")
    return max(dates) or None


def timeline_ended(pg):
    """The last year an SFMTA page's timeline names, when every milestone is dated before last year; else None.
    A page with no timeline has not ended: a Slow Street's page is a standing programme page with no milestones."""
    tl = pg.get("timeline") or []
    years = [[int(y) for y in re.findall(r"\b(20\d\d)\b", t.get("when") or "")] for t in tl]
    if not tl or not all(years):
        return None
    last = max(max(y) for y in years)
    return last if last < data_today().year - 1 else None


def page_done(pg):
    """Does the SFMTA page itself say the project is finished?"""
    if PAGE_DONE.search(pg.get("phase") or ""):
        return "its Current Phase field says “%s”" % pg["phase"]
    if pg.get("phase"):
        # A phase field that names a live stage outranks a timeline that
        # lists only the early milestones (J Church Safety and Accessibility
        # Project: San Jose Avenue, phase Construction, timeline ending with
        # the Board proposal in Fall 2023, all Completed).
        return None
    said = prose_done(pg.get("pageText"))
    if said:
        return "its page says “%s”" % said
    tl = pg.get("timeline") or []
    if tl and all(t.get("status") == "Completed" for t in tl):
        # SFMTA marks some future milestones Completed ("Summer 2026 - Winter
        # 2028: Construction Continues", J Church and M Ocean View, read
        # 2026-09-28), so a timeline that runs past today is not finished.
        ends = [stage_end(t.get("when")) or season_date(t.get("when")) for t in tl]
        if all(e and e[:7] <= data_today().isoformat()[:7] for e in ends):
            return "every milestone on its timeline is marked Completed and dated in the past"
    return None


# An sfmta.com project page that is a section of a mapped project's page, not
# a project of its own: the parent page lists it under its own name, and it
# describes one street of the parent's work. Linked from the parent's row.
SFMTA_SECTION_PAGES = {
    "folsom-street-implementation": (
        "381", "read 2026-09-29: the Folsom-Howard Streetscape Project page lists “Folsom Street Implementation” and "
               "“Howard Street Implementation” as its sections, and both pages give the same May 2026 construction "
               "update for Folsom from 8th to 11th Street"),
}

# A layer project whose sfmta.com page no longer answers: the layer still
# names the page (PROJECTPAGE, WEBPAGEPUBLISHED "Yes", read 2026-09-29), but
# the page returns HTTP 403 with the title "Content Not Found | SFMTA" to a
# browser as well as to this script, while other nodes answer 301 to both.
# The dead link is not shown; the closest official source is, labelled so and
# not counted as the project's page. A node that fails and is not here keeps
# its link, and the audit's B1 counts it against the list.
SFMTA_GONE_CLOSEST = {
    "761": ("https://sfocii.org/projects/hunters-point-shipyard/overview",
            "OCII, Hunters Point Shipyard Phase 1 and 2/Candlestick Point",
            "the Office of Community Investment and Infrastructure's page for the development the layer maps (read "
            "2026-09-29)"),
    "762": ("https://sfplanning.org/project/parkmerced", "SF Planning, Parkmerced",
            "the Planning Department's page for the development, a partner the layer names (read 2026-09-29)"),
    "29724": ("https://www.sfmta.com/projects/sloat-blvd-quick-build-project", "SFMTA, Sloat Blvd Quick-Build Project",
              "the page names the “traffic-signal upgrades at ... Sloat Blvd & Great Highway (by SFMTA)” it was "
              "coordinated with (read 2026-09-29)"),
}

PLAN_ONLY = "no bike or pedestrian scope; listed because its line runs on a plan block"
# Signal contracts and bus-stop work share streets with bike work but add no
# bikeway, whatever tag SFMTA gives them (Contract 36, Contract 65, 8 Bayshore
# Visitacion Valley Stop Improvements).
# Work inside stations, yards and vehicles is not on a street, plan block or not.
OFF_STREET = re.compile(r"\bstations?\b|subway|\btunnel\b(?!.*safety)|transit center|elevator|escalator|\byards?\b|"
                        r"fleet|vehicle|facilit|budget|\bpilot\b", re.I)
SFMTA_NOT_BIKEWAY = re.compile(r"\bsignals?\b|\bstop improvements?\b|\bbus stops?\b", re.I)


def sfmta_decision(name, tags, layer_phase, pg, on_layer):
    """(listed, reason, phase, phaseBasis) for one SFMTA project."""
    pg = pg or {}
    tagged = [t for t in tags if t in SFMTA_TAGS]
    named = scope_families(name)
    texted = scope_families(pg.get("pageText"))
    if tagged:
        scope = "SFMTA tags it %s" % ", ".join(tagged)
    elif named:
        scope = "its name says %s" % ", ".join(named)
    elif (len(texted) >= 2 or set(texted) & STREET_WORK_FAMILIES) and names_a_place(name):
        scope = "its page names %s" % ", ".join(texted)
    else:
        scope = None
    if scope is None and on_layer and not SFMTA_NOT_BUILT.search(name) and not OFF_STREET.search(name):
        # Criterion A1 counts every active project SFMTA maps on the plan's
        # blocks, bike or not: transit lanes, parking programmes and wiring
        # dig up the same streets. Listed only if its line is on a plan block
        # (the selection checks), and never counted as bike work.
        scope = PLAN_ONLY
    if scope is None:
        why =("its page names only %s" % texted[0] if len(texted) == 1 else
               "its page names %s but its name is no street or Muni line, so it is a programme or "
               "document page rather than a project on a street" % ", ".join(texted) if texted else "")
        return False, "no bike or pedestrian scope" + (" (%s)" % why if why else ""), None, None
    if layer_phase in FINISHED_PHASES:
        return False, "finished: the layer's phase is %s" % layer_phase, layer_phase, "SFMTA's project layer"
    # The page is read whatever phase the layer gives: the layer's phase is
    # stale for old projects (Upper Market Street Safety Project,
    # "Implementation / Construction" on the layer: "the Upper Market Safety
    # Project was substantially completed" in summer 2023, per its page;
    # review of 2026-09-29).
    done = page_done(pg)
    if done:
        return False, "finished: " + done, None, None
    # A Bike or Quick-Build tag is street work even at a station: West Portal
    # Station Safety and Community Space Improvements is a quick-build on the
    # streets around the station.
    if scope != PLAN_ONLY and not {"Bike", "Quick-Build"} & set(tagged) and not named and SFMTA_FACILITY.search(name):
        if not on_layer or SFMTA_NOT_BUILT.search(name) or OFF_STREET.search(name):
            return False, "transit facility, fleet or parking work, not a street (%s)" % scope, None, None
        # Wiring, irrigation or parking work SFMTA maps on a street is not
        # bike or walking work, but it digs up the same blocks (criterion A1).
        scope = PLAN_ONLY
    if layer_phase:
        phase, basis = layer_phase, "SFMTA's project layer"
    elif pg.get("phase"):
        phase, basis = pg["phase"], "the project's page (Current Phase or Stage)"
    else:
        phase, basis = None, None
    if not on_layer:
        latest, how = page_activity(pg)
        since = str(data_today().year - 1)
        if latest is None or latest < since:
            return False, "not on SFMTA's project map and nothing dated %s or later on its page (latest %s, from %s)" % (
                since, latest or "none", how or "nothing dated"), phase, basis
    return True, scope, phase, basis


def work_kind(name, department):
    """The street-work kind of a project, or None when it is not street work."""
    if department == "SFMTA":
        # Which SFMTA projects are in is decided by sfmta_decision, from their scope.
        return "SFMTA bike and safety"
    for kind, rx in WORK_KINDS:
        if rx.search(name):
            return kind
    for rx, kind, _ in READ_STREET_WORK:
        if rx.search(name):
            return kind
    return None


# Projects whose name says nothing of the street but whose own page, read by
# hand, describes street work. Each carries the words that make it so.
READ_STREET_WORK = [
    (re.compile(r"^Ocean Beach Climate (?:Change )?Adaptation Project$", re.I), "streetscape and safety",
     "SFPUC's page (sfpuc.gov/construction-contracts/construction-projects/oceanbeach, read 2026-09-29): "
     "“rerouting Great Highway traffic between Sloat Blvd and Skyline Drive away from the narrowest part of the "
     "beach, building a multi-use public trail with sweeping Pacific Ocean views where the highway is now”"),
]


TOP_N = 10  # rows outlined: the ten highest by residents and by plan miles


def thin(coords):
    """A centerline block at five decimals (about a metre), repeats dropped."""
    out = []
    for x, y in coords:
        p = [round(x, 5), round(y, 5)]
        if not out or out[-1] != p:
            out.append(p)
    # A block shorter than the rounding stays at full precision, never a point.
    return out if len(out) > 1 else [list(c) for c in coords]


def title(s):
    """'VALENCIA ST' and 'valencia st' both to 'Valencia St'."""
    if not s:
        return s
    out = re.sub(r"\b[a-z]", lambda m: m.group(0).upper(), s.lower())
    # The centreline pads ordinals ("03RD ST"); a reader writes "3rd St".
    return re.sub(r"\b0*(\d+)(st|nd|rd|th)\b", lambda m: m.group(1) + m.group(2).lower(), out, flags=re.I)


def norm_name(s):
    """'PW Main St Streetscape Project' and 'Main Street Streetscape Project' to one key."""
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
    s = re.sub(r"\b(st)\b", "street", s)
    s = re.sub(r"\b(ave)\b", "avenue", s)
    s = re.sub(r"\b(blvd)\b", "boulevard", s)
    s = re.sub(r"\b(pw|sfmta|mta|project|projects|the|program|programme|improvement|improvements)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def day(v):
    s = str(v or "")[:10]
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def department(agency):
    for prefix, name in DEPARTMENTS:
        if (agency or "").startswith(prefix):
            return name
    return None


def other_agency_on_plan(rows_by_job, by_id, plan, today):
    """Feed jobs of no listed department, unfinished (latest end today or later, or none), on plan blocks."""
    out = []
    for pid, rows in rows_by_job.items():
        agency = rows[0].get("agency_name") or ""
        if department(agency):
            continue
        end = max((day(r.get("end_date")) for r in rows if day(r.get("end_date"))), default=None)
        if end and end < today:
            continue
        blocks = set(by_id.get("dotmaps:%s" % pid, {}).get("cnns") or ()) & set(plan)
        if blocks:
            out.append({"id": "dotmaps:%s" % pid, "agency": agency, "name": (rows[0].get("name") or "").strip(),
                        "planBlocks": len(blocks), "end": end})
    return sorted(out, key=lambda x: (x["name"], x["id"]))


# ---- The plan rating ----------------------------------------------------------
# Bryan, 2026-09-29, on the "Does not meet the plan" chip: "Give the project a
# rating from 100% to 0% for how much of the planned infra it builds or
# upgrades." Agreed on the projects mockup the same day.
#
# The base is the plan miles on the project's blocks that lack an all-ages
# bikeway today (missingMiles), plus any plan block this project itself has
# already brought to the plan's type (bikeway-history credit), since those
# lacked it before the project and are what it built. The rating is the share
# of the base the project builds or upgrades to the plan's type, per direction
# of travel. Where it is read from depends on the project:
#   SFMTA, built work: blocks site/data/bike-history/projects.json credits to
#     the project, counted by the direction rows that meet the plan's type
#     today (site/data/north-star/status.json met_m).
#   SFMTA, work to come: the blocks and bikeway class SFMTA's own page names,
#     as tools/bike-network/bike-network-history.py (planned.json) and
#     tools/bike-network/bike-reported-work.py (reported.json) read them.
#   Public Works and SFPUC jobs, and SFMTA pages that name no bike work: the
#     published scope; one that names no bike work gives "0% in published scope".
#   Anything else: "Not stated". No number is guessed.
#   missingMiles 0 and no credit: "Already built".
BH_PROJECTS = os.path.join(ROOT, "site", "data", "bike-history", "projects.json")
BH_PLANNED = os.path.join(ROOT, "site", "data", "bike-history", "planned.json")
BH_REPORTED = os.path.join(ROOT, "site", "data", "bike-history", "reported.json")
PLAN_STATUS = os.path.join(ROOT, "site", "data", "north-star", "status.json")
BIKEWAY_LAYER_URL = "https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0"
PLAN_URL = "https://www.sfmta.com/projects/biking-and-rolling-plan"
# Plan facilities an all-ages bikeway of any kind satisfies (a Slow Street on a
# street the plan draws as shared).
CALM_OK = ("Shared", "Shared L3", "Car-free", "Undecided")
# An SFMTA page's words for bike work: BIKE_WORDS plus the ones a page uses
# for people ("biking", "cyclists"), so a page naming none is "0% in published
# scope" only when it truly names none.
PAGE_BIKE_WORDS = re.compile(BIKE_WORDS.pattern + r"|\bbiking|\bcyclist|\bcycling", re.I)
RATING_STATES = ("percent", "scope-none", "already-built", "not-stated", "no-overlap")
# tools/bike-network/bike-progress.py row_meets: which bikeway class satisfies what the plan draws.
SEPARATED_CLASSES = {"CLASS IV", "CLASS I"}


def slow_key(name):
    """A Slow Street's name without its street type ("Page Street Slow Street" is "Page Slow Street")."""
    return " ".join(re.sub(r"\b(street|st|avenue|ave)\b", " ", norm_name(name)).split())


def code_meets(facility, code):
    """Does a block whose best class in segments.json is `code` ('0' absent, '1' path, '2' painted,
    '3' sharrow, '4' separated, 'S' Slow Street, '?' unknown) meet the plan's facility? class_meets on
    the history's codes, with a Slow Street meeting the streets the plan draws as shared."""
    if facility == "Separated":
        return code in ("1", "4")
    if facility in ("Shared", "Shared L3"):
        return code in ("1", "2", "4", "S")
    if facility in ("Car-free", "Undecided"):
        return code in ("1", "4", "S")
    return code not in ("0", "?")


def class_meets(facility, cls):
    """Does a direction row of class `cls` meet the plan's facility? tools/bike-network/bike-progress.py row_meets,
    plus Undecided, which the plan leaves unrated: there a separated lane or a path counts."""
    if facility == "Separated":
        return cls in SEPARATED_CLASSES
    if facility in ("Shared", "Shared L3"):
        return cls != "CLASS III"
    if facility == "Undecided":
        return cls in SEPARATED_CLASSES
    return True


def pct(built, base):
    """A whole percent that reads 0 or 100 only when it is exactly that."""
    if base <= 0:
        return None
    v = 100.0 * built / base
    if 0 < v < 1:
        return 1
    if 99 < v < 100:
        return 99
    return int(round(v))


def rating_band(r):
    """The filter's band for a rating."""
    if r["state"] != "percent" and r["state"] != "scope-none":
        return r["state"]
    v = r["value"]
    return "all" if v == 100 else "most" if v >= 50 else "some" if v > 0 else "none"


SFMTA_PAGES_TEXT = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")  # each page's prose, as pageText
_DATE = (r"((?:(?:early|mid|late)[- ])?(?:(?:january|february|march|april|may|june|july|august|september|october|"
         r"november|december|winter|spring|summer|fall|autumn)\s+)?20\d\d)")
PROSE_START = re.compile(r"construction[^.]{0,60}?\b(?:begin|began|start|started|starting)\b[^.]{0,30}?\b" + _DATE, re.I)
PROSE_END = re.compile(r"(?:(?:finish|complete)\s+construction|construction[^.]{0,40}?\b(?:complete|completed|finished))"
                       r"[^.]{0,20}?\b(?:in|by)\s+" + _DATE, re.I)


# An SFMTA page's own words for a phase or a start, where its fields give none.
TIMELINE_STAGE = re.compile(r"plan|design|engineer|construct|implement|legislat|outreach", re.I)
SLOW_STREET_BOARD = re.compile(r"was approved as a Slow Street by the San Francisco Municipal Transportation Agency "
                               r"\(SFMTA\) Board on [A-Z][a-z]+ \d{1,2}, 20\d\d|"
                               r"On [A-Z][a-z]+ \d{1,2}, 20\d\d, the SFMTA Board affirmed [^.]{0,60}?Slow Streets? program")
SLOW_STREET_START = re.compile(r"initially (?:designated|implemented) as a COVID-19 Response Slow Street in "
                               r"((?:[A-Z][a-z]+ )?20\d\d)")
STRIPING_START = re.compile(r"\b(?:striping|installation|construction)\b[^.]{0,80}?\bstarting\s+"
                            r"((?:(?:early|mid|late)\s+)?(?:January|February|March|April|May|June|July|August|"
                            r"September|October|November|December) 20\d\d)")


def prose_dates(text):
    """Construction start and finish from a page that has no timeline block, from its own sentences.

    The first match is used: SFMTA lists updates newest first, so it is the
    latest estimate ("We expect to finish construction in early 2025",
    Better Market Street, read 2026-09-28). Returns (start, end, quote).
    """
    text = " ".join((text or "").split())
    s, e = PROSE_START.search(text), PROSE_END.search(text)
    start = season_date(s.group(1)) if s else None
    end = stage_end("x to " + e.group(1)) if e else None
    quote = " … ".join(m.group(0) for m in (s, e) if m)
    return start, end, quote


# ---- Dates read off SFMTA's page text by TypeSafe's Jev -----------------------
# tools/projects/sfmta-page-dates.py asks Jev for each page's construction start and
# end and its latest public consultation. The page's own timeline, event
# cards, or a sentence prose_dates finds come first; Jev's date fills a field
# they leave empty, and where both give one and they disagree, the row prints
# both (dateNotes). Every date the row shows is listed in dateSources with the
# page it was read from.
PAGE_DATES = os.path.join(ROOT, "out", "sfmta-page-dates", "dates.json")
OUTREACH = re.compile(r"outreach|engagement|open house|community meeting|workshop|webinar|survey|office hours|"
                      r"tabling|pop-up|listening session|town hall|stakeholder meeting|public meeting", re.I)
JEV = "the project page's text"
_page_dates = None


def page_dates(node, url=None):
    """Jev's answer for an SFMTA page, by node ("1136"), page id ("sfmta-page:x" is "slug:x") or URL; None if none."""
    global _page_dates
    if _page_dates is None:
        held = json.load(open(PAGE_DATES))["pages"] if os.path.exists(PAGE_DATES) else {}
        _page_dates = dict(held)
        _page_dates.update({e["url"].rstrip("/"): e for e in held.values() if e.get("url")})
    key = str(node).split(":", 1)[-1]
    e = _page_dates.get(key) or _page_dates.get("slug:" + key) or _page_dates.get((url or "").rstrip("/"))
    return e if e and e.get("status") == "answered" else None


def agrees(j, date):
    """Jev's pick agrees with a date when the date falls in the period Jev's span names, at month precision."""
    d = (date or "")[:7]
    return j["first"][:len(d)] <= d <= j["last"][:len(d)]


_SEASONS_MONTHS = (r"(?:(?:early|mid|late)[- ]*)?(?:(?:january|february|march|april|may|june|july|august|september|"
                   r"october|november|december|winter|spring|summer|fall|autumn)(?:\s*[-–]\s*[a-z]+)?,?\s+)?")
_YEAR = r"(?:19|20)\d\d"
# An outreach step the page dates in its own words, outside the timeline and
# event-card blocks the scraper reads: a text timeline's "Winter 2013 - Open
# House Meeting #1" (6th Street), a document list's "Public Outreach
# Documents Round 1: May 2011" (Better Market Street), or "From 2014 to 2018,
# the ... team held dozens of in-person meetings" (Central Embarcadero). Each
# one is where the D2 hand grade (2026-09-29) found the page's first public
# consultation earlier than the first event card or stage.
TEXT_OUTREACH = [
    re.compile(r"(%s%s)(?:\s*(?:to|-|–)\s*%s%s)?\s*[-–—:]\s*(?=[^.;]{0,15}?(?:%s))"
               % (_SEASONS_MONTHS, _YEAR, _SEASONS_MONTHS, _YEAR, OUTREACH.pattern), re.I),
    re.compile(r"(?:outreach|engagement)[^.]{0,60}?\bround\s*1\s*:\s*(%s%s)" % (_SEASONS_MONTHS, _YEAR), re.I),
    re.compile(r"\bfrom\s+(%s%s)\s+(?:to|through|until)\s+%s%s,?[^.]{0,200}?\b(?:held|hosted|conducted)\b[^.]{0,120}?"
               r"\b(?:meetings|open houses?|workshops|outreach)\b" % (_SEASONS_MONTHS, _YEAR, _SEASONS_MONTHS, _YEAR),
               re.I),
]


def text_outreach_start(text):
    """(date, words) of the earliest public consultation a page's prose dates, or (None, None)."""
    text = " ".join((text or "").replace("​", " ").split())
    found = []
    for rx in TEXT_OUTREACH:
        for m in rx.finditer(text):
            d = season_date(m.group(1))
            if d:
                found.append((d, " ".join(m.group(0).split())[:120]))
    return min(found) if found else (None, None)


REPORTED_START = re.compile(r"\b(?:construction|work|installation|crews?)\b[^.]{0,40}?\b(?:started|began|begun|"
                            r"commenced|got under ?way)\b|\b(?:started|began|commenced)\s+construction\b", re.I)
NOT_STARTED = re.compile(r"\b(?:not|before|until|once|after|when)\b[^.]{0,30}?\b(?:started|began|begun|commenced)\b", re.I)


def reports_start(j, start):
    """Jev's start comes from a sentence reporting that construction has started, dated before today and before
    the start the page's timeline gives."""
    return bool(REPORTED_START.search(j.get("line") or "")) and not NOT_STARTED.search(j.get("line") or "") \
        and j["first"] <= data_today().isoformat() \
        and j["first"][:7] < (start or "")[:7]


def range_start(when):
    """The first date of a stage's range: "Spring - summer 2026" -> 2026-04, "Fall 2022 - Winter 2023" -> 2022-10."""
    when = re.sub(r"\b(20\d\d)\s*[-–—]\s*(?=(?:[A-Za-z]+\s+)?20\d\d\b)", r"\1 - ", spell_range(when))
    parts = re.split(r"\s+(?:to|through|-|–|—)\s+", when)
    if len(parts) < 2:
        return None
    head = parts[0] if re.search(r"\b20\d\d\b", parts[0]) else "%s %s" % (
        parts[0], (re.findall(r"\b20\d\d\b", parts[-1]) or [""])[0])
    return season_date(head)


def with_page_dates(row, node, records, prose=None):
    """Fill an SFMTA row's empty date fields from Jev's reading of its page, and list where each date came from.

    `prose` is the page's text, read for the first public consultation it dates in its own words."""
    url = row["links"][0]["url"]
    jd = (page_dates(node, url) or {}).get("fields", {})
    js, je, jc, jcs = (jd.get(f) or {} for f in ("construction_start", "construction_end", "consultation",
                                                 "consultation_start"))
    basis = row["startBasis"] or ""
    own = ("the project page's timeline" if basis.startswith("the project page's timeline") else
           "a sentence on the project page (“%s”)" % row["startText"] if row["start"] or row["end"] else None)
    notes, sources = row.setdefault("dateNotes", []), []

    def jev(f):
        return "%s (“%s”, %s)" % (JEV, f["span"], f["label"].split(" / ")[0][:80])

    def unchecked(f, name, shown):
        # tools/projects/sfmta-page-dates.py flags a pick for a person to check and
        # lists it, with why, in out/sfmta-page-dates/review.md until someone
        # does; the reader gets the date as the row shows it and no reasons.
        # The note is not a disagreement, so it goes under its own label.
        if f.get("flags"):
            row.setdefault("uncheckedNotes", []).append(
                "The %s shown, %s, was read from the words “%s” on SFMTA's project page by a model, and a person "
                "has not confirmed it." % (name, shown, f["span"]))
            if name == "construction end":
                row["endUnchecked"] = shown  # held_listing: this end may not move the row on or off the list

    def checked(f):
        # A date a person checked against the page (data/sfmta-page-dates/confirmed.csv) stands over
        # every other reading of it: the timeline, the event cards and Jev's.
        return "the project page, checked by hand on %s" % f["confirmed"]["date"]

    def sure(f):
        return bool(f.get("confirmed") and f.get("iso"))

    if sure(js):
        row["start"], row["startText"], row["startBasis"] = js["value"], js["value"], checked(js)
    elif row["start"]:
        if js.get("value") and not agrees(js, row["start"]) and reports_start(js, row["start"]):
            # The page reports that construction has started, earlier than
            # its timeline's stage says it will (Contract 35: "Construction
            # started at two of the 17 project locations in August 2026"
            # under a Pending "Fall 2026" stage). What happened stands over
            # the plan it replaced.
            notes.append("%s gives construction starting %s; the page's text reports it started %s (“%s”), which "
                         "is shown." % (own[0].upper() + own[1:], row["start"], js["value"], js["span"]))
            row["start"], row["startText"], row["startBasis"] = js["value"], js["span"], jev(js)
            unchecked(js, "construction start", row["start"])
        elif js.get("value") and not agrees(js, row["start"]):
            notes.append("%s gives construction starting %s; the page's text gives %s (“%s”)."
                         % (own[0].upper() + own[1:], row["start"], js["value"], js["span"]))
    elif js.get("value"):
        row["start"], row["startText"], row["startBasis"] = js["value"], js["span"], jev(js)
        unchecked(js, "construction start", row["start"])
    if row["start"]:
        sources.append({"field": "construction start", "date": row["start"], "text": row["startText"],
                        "from": row["startBasis"], "url": url})
    if sure(je):
        row["end"] = je["iso"]
        sources.append({"field": "construction end", "date": je["iso"], "text": je["value"], "from": checked(je),
                        "url": url})
    elif row["end"]:
        if je.get("iso") and not agrees(je, row["end"]):
            notes.append("%s gives construction ending %s; the page's text gives %s (“%s”)."
                         % (own[0].upper() + own[1:], row["end"], je["value"], je["span"]))
        sources.append({"field": "construction end", "date": row["end"], "text": None, "from": basis, "url": url})
    elif je.get("iso"):
        latest = (page_dates(node, url) or {}).get("latestStageDate") or ""
        if row["start"] and je["iso"] < (row["start"] + "-01-01")[:10]:
            notes.append("The project page's text gives the construction end as %s (“%s”), "
                         "before the start of %s, so it is not shown." % (je["value"], je["span"], row["start"]))
        elif je["iso"] < data_today().isoformat() < latest:
            # The definitions count any phase's end, so a passed end on a page
            # that dates work still to come is an earlier phase's, not the
            # project's (5th Street: quick-build to Fall 2023, long-term
            # design to Early 2027).
            notes.append("SFMTA's page gives an earlier phase's construction end, %s (“%s”), "
                         "and dates later work to %s with no construction end, so no end is shown."
                         % (je["value"], je["span"], latest[:7]))
        else:
            row["end"] = je["iso"]
            unchecked(je, "construction end", row["end"])
            sources.append({"field": "construction end", "date": je["iso"],
                            "text": je["span"] + (" – " + je["closes"] if je.get("closes") else ""), "from": jev(je),
                            "url": url})

    # Public consultation: from the page's own outreach stages and event
    # cards, the first one's start and the latest one's end; else the latest
    # Jev reads, whose start is known only when its span closes a timeline
    # stage's range ("Fall 2022 - Winter 2023" starts Fall 2022).
    mine = []  # (end, start, text, basis, url)
    for r in records:
        if r["kind"] != "project-page" or not r.get("date") or not OUTREACH.search(r.get("title") or ""):
            continue
        block = r.get("pageBlock") or "timeline"
        if block == "timeline" and not re.search(r"hearing|board", r["title"], re.I):
            mine.append((stage_end(r.get("when")) or r["date"], range_start(r.get("when")) or r["date"], r.get("when"),
                         "the project page's timeline (“%s”)" % r["title"][:80], r["url"]))
        elif block == "event":
            # An event over several days ends on its last: 13th Street's
            # virtual open house ran April 18–30, 2022 (Fable review, 2026-09-30).
            end = r.get("end") or r["date"]
            mine.append((end, r["date"], r["date"] + (" – " + end if end != r["date"] else ""),
                         "the project page's event card (“%s”)" % r["title"][:80], r["url"]))
    date = first = None
    if mine:
        _, first, ftext, fbasis, fsrc = min(mine, key=lambda m: m[1])
    if sure(jc):
        date, text, cbasis, src = jc["iso"], jc["value"], checked(jc), url
    elif mine:
        date, _, text, cbasis, src = max(mine)
        if jc.get("value") and not agrees(jc, date):
            notes.append("The project page's timeline and event cards give the latest public consultation as %s; "
                         "the page's text gives %s (“%s”)." % (date, jc["value"], jc["span"]))
    elif jc.get("iso"):
        # The last day of Jev's span, as a timeline stage's end is.
        end = stage_end(jc.get("stage"))
        date, text, cbasis, src = jc["iso"], jc["span"] + (" – " + jc["closes"] if jc.get("closes") else ""), jev(jc), url
        unchecked(jc, "latest public consultation", date)
        first = range_start(jc["stage"]) if end and agrees(jc, end) else None
        if first:
            ftext, fbasis, fsrc = jc["stage"], cbasis, url
    tfirst, twords = text_outreach_start(prose)
    if date and tfirst and tfirst <= date[:len(tfirst)] and (not first or tfirst < first[:len(tfirst)]):
        first, ftext, fbasis, fsrc = tfirst, twords, "the project page's text (“%s”)" % twords, url
    if sure(jcs):
        # The first workshop or meeting, checked by hand: the span runs from it to the latest.
        first, ftext, fbasis, fsrc = jcs["iso"], jcs["value"], checked(jcs), url
    if first:
        sources.append({"field": "first public consultation", "date": first, "text": ftext, "from": fbasis,
                        "url": fsrc})
    row["consultation"], row["consultationStart"] = date, first
    if date:
        sources.append({"field": "latest public consultation", "date": date, "text": text, "from": cbasis,
                        "url": src})
    row["dateSources"] = sources
    return row


# ---- Dates read off Public Works' and SFPUC's page text -------------------------
# tools/projects/sfmta-page-dates.py --pages departments asks the same questions of
# every Public Works and SFPUC project page. The feed's dates, or a Public
# Works page's Start and Completion fields, come first; the page text's fills
# a field they leave empty, and where both give one and they disagree, the
# row prints both (dateNotes). Bryan, 2026-09-29, on the Masonic Avenue
# Streetscape row: "How come this project is missing dates? ... The web page
# ... clearly has dates in it".
DEPT_PAGE_DATES = os.path.join(ROOT, "out", "dept-page-dates", "dates.json")
PAGE_OWNER = {"Public Works": "Public Works'", "SFPUC": "SFPUC's"}
_dept_dates = None


def dept_page_dates(url):
    """The answer for a Public Works or SFPUC project page, by its address; None if none."""
    global _dept_dates
    if _dept_dates is None:
        held = json.load(open(DEPT_PAGE_DATES))["pages"] if os.path.exists(DEPT_PAGE_DATES) else {}
        _dept_dates = dict(held)
        _dept_dates.update({k.rstrip("/"): v for k, v in held.items()})
    e = _dept_dates.get(url or "") or _dept_dates.get((url or "").rstrip("/"))
    return e if e and e.get("status") == "answered" else None


_dept_fields = None
_dept_words = None


def dept_page_fields(url):
    """A Public Works page's own Start, Completion and Status fields, as tools/projects/department-project-pages.py read
    them ({"start": "Winter, 2026", "completion": None, "status": ...}); {} for a page it did not read."""
    global _dept_fields
    if _dept_fields is None:
        pages = json.load(open(DEPT_PAGES))["pages"] if os.path.exists(DEPT_PAGES) else []
        _dept_fields = {p["url"].rstrip("/"): p for p in pages}
    return _dept_fields.get((url or "").rstrip("/")) or {}


def dept_page_description(url):
    """(description, status) of a Public Works page (tools/projects/dpw-projects.py) or an SFPUC construction-project
    page (its Project Phase and status, from department-project-pages.py's extract); ("", "") for any other."""
    global _dept_words
    if _dept_words is None:
        recs = json.load(open(DPW_PROJECTS))["records"] if os.path.exists(DPW_PROJECTS) else []
        _dept_words = {r["url"].rstrip("/"): (r.get("description") or "", r.get("status") or "") for r in recs}
        puc = json.load(open(PUC_PROJECTS))["records"] if os.path.exists(PUC_PROJECTS) else []
        _dept_words.update({r["url"].rstrip("/"): (r.get("description") or "", r.get("phase") or r.get("status") or "")
                            for r in puc})
    return _dept_words.get((url or "").rstrip("/"), ("", ""))


def with_dept_page_dates(row):
    """Fill a Public Works or SFPUC row's empty construction dates, and its consultation dates, from the text of
    its own department's project page, and list where each date came from."""
    owner = PAGE_OWNER.get(row["department"])
    link = next((l for l in row["links"] if owner and l.get("department") == row["department"]
                 and l.get("kind") == "project" and dept_page_dates(l["url"])), None)
    # A row the feed files under one department can be another's project by
    # name: "PW FOLSOM AREA STORMWATER IMPROVEMENT PROJECT" is SFPUC's Folsom
    # Area Stormwater Improvement Project, whose page is the one the row links
    # (D2 hand grade, 2026-09-29). A page carrying the row's own name is its
    # page, whichever department publishes it.
    named = link is None and next((l for l in row["links"] if l.get("department") in PAGE_OWNER
                                   and l.get("kind") == "project" and dept_page_dates(l["url"])
                                   and same_name(row["name"], dept_page_dates(l["url"]).get("title") or "")), None)
    if named:
        link, owner = named, PAGE_OWNER[named["department"]]
    if link is None:
        return row
    url, e = link["url"], dept_page_dates(link["url"])
    js, je, jc = (e["fields"].get(f) or {} for f in ("construction_start", "construction_end", "consultation"))
    feed = row["source"] == "dotmaps"
    if "dateSources" not in row:
        row["dateSources"] = [
            {"field": f, "date": v, "text": row.get("startText") if f == "construction start" else None,
             "from": "the coordination feed" if feed else row["startBasis"],
             "url": ROW_URL.format(row["id"].split(":", 1)[1]) if feed else row["record"]["page"]}
            for f, v in (("construction start", row["start"]), ("construction end", row["end"])) if v]
    sources, notes = row["dateSources"], row.setdefault("dateNotes", [])

    def own(field):
        return "The coordination feed" if feed else "%s project page's %s field" % (owner, field)

    def one_line(s):
        return " ".join((s or "").split())  # a span can run over a line break ("Spring,\n 2026")

    def spans(f):
        return one_line(f["span"]) + (" – " + one_line(f["closes"]) if f.get("closes") else "")

    def basis(f):
        return "%s project page text (“%s”)" % (owner, spans(f))

    def unchecked(f, name, shown):
        # Flagged picks are listed, with why, in out/dept-page-dates/review.md
        # until a person checks them; the reader gets the date and no reasons.
        if f.get("flags"):
            row.setdefault("uncheckedNotes", []).append(
                "The %s shown, %s, was read from the words “%s” on %s project page by a model, and a person "
                "has not confirmed it." % (name, shown, one_line(f["span"]), owner))
            if name == "construction end":
                row["endUnchecked"] = shown  # held_listing: this end may not move the row on or off the list

    # A Public Works page is the department's own word on its job, so where it
    # and the coordination feed disagree the page's date is shown and the
    # feed's printed beside it (the D2 criterion grades against the page;
    # hand grade of 2026-09-29: VL78's page says construction continues
    # "through March 2027" while the row showed the feed's 2027-06-12). An
    # SFPUC page is left as it was, unless it carries the row's own name: its
    # pages are programmes that date several contracts at once (Westside
    # Fire's "2027" against Contracts B to G).
    page_first = feed and (row["department"] == "Public Works" or bool(named))
    today = data_today().isoformat()

    # A Public Works page's own Start and Completion fields come before its
    # prose, which is often the sentence written when the contract was let
    # and never revised: VL68's text says completion "April 2025" while its
    # Completion field says "Spring, 2026"; VL79's text says "Winter 2025"
    # while its Start field says "Winter, 2026" (Fable review, 2026-09-30).
    # Where the two name the same year the prose, the finer, is read.
    fld = dept_page_fields(url) if owner == PAGE_OWNER["Public Works"] else {}

    def field_pick(name, j, fvalue, fiso, ftext):
        """The page's date for one field, as (value, iso, text, basis, j-or-None), or None."""
        if ftext and fiso:
            if j.get("iso") and (j.get("value") or "")[:4] == fvalue[:4]:
                return (j["value"], j["iso"], spans(j) if name == "Completion" else one_line(j["span"]),
                        "%s project page (%s “%s”; text “%s”)" % (owner, name, ftext, spans(j)), j)
            if j.get("iso") and not (j["first"][:7] <= fiso[:7] <= j["last"][:7]):
                notes.append("%s project page's %s field gives %s (“%s”); its text gives %s (“%s”), so the field "
                             "is read." % (owner, name, fvalue, ftext, j["value"], spans(j)))
            return fvalue, fiso, ftext, "%s project page (%s “%s”)" % (owner, name, ftext), None
        if j.get("iso"):
            return (j["value"], j["iso"], spans(j) if name == "Completion" else one_line(j["span"]),
                    basis(j), j)
        return None

    fs = fld.get("start")
    fsv = season_date(fs) if fs else None
    fe = fld.get("completion")
    fev = stage_end("x - " + fe) if fe else None
    ps = field_pick("Start", js, fsv, {4: "%s-01-01", 7: "%s-01"}.get(len(fsv), "%s") % fsv if fsv else None, fs)
    pe = field_pick("Completion", je, fev[:7] if fev else None, fev, fe)

    def period_end(v):
        return v if len(v) == 10 else stage_end("x - " + v) if len(v) == 4 else \
            (dt.date(int(v[:4]) + (v[5:7] == "12"), int(v[5:7]) % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()

    def page_agrees(p, date):
        if p[4] is not None:
            return agrees(p[4], date)
        d = (date or "")[:7]
        return p[1][:len(d)] <= d <= period_end(p[0])[:len(d)]

    # The work is under way when the page says it is In progress and shows
    # it now: crews scheduled this month or later (Howard Streetscape's
    # Sept–Oct 2026 work schedule), the page's own words that work has
    # begun, or the feed's Construction phase. A page that says the job is
    # still in pre-construction shows it is not.
    # SFPUC's page gives a Project Phase instead: Folsom Area Stormwater's
    # "Construction" (its text: "In late 2023, the SFPUC began construction").
    words, listed_status = dept_page_description(url)
    status = (e.get("pageStatus") or fld.get("status") or listed_status or "").lower()
    underway = status in ("in progress", "construction") and not re.search(r"pre-?construction", words, re.I) and (
        (e.get("latestStageDate") or "") >= today or row.get("phase") == "Construction"
        or bool(re.search(r"\bhas (?:begun|started)\b|\bunder ?way\b|\bcrews (?:are|have)\b", words, re.I)))

    def swap(field, key, shown, p):
        sources[:] = [s for s in sources if s["field"] != field] + [
            {"field": field, "date": p[1] if field == "construction end" else p[0], "text": p[2], "from": p[3],
             "url": url}]
        notes.append("The coordination feed gives construction %s %s; %s, %s, which is shown."
                     % (key, shown, p[3], p[1] if field == "construction end" else p[0]))

    def kept(key, shown, p, why):
        notes.append("The coordination feed gives construction %s %s, which is shown; %s gives %s, %s."
                     % (key, shown, p[3], p[1] if key == "ending" else p[0], why))

    if row["start"] and page_first and ps and not page_agrees(ps, row["start"]):
        # Page text or a field that dates a start which has passed, earlier
        # than the feed's, on a job the page does not show under way, is a
        # plan the department has not revised: VL79's text "Winter 2025"
        # against the feed's 2025-09-04, on a page that says the job is still
        # in pre-construction, would be one without its Start field.
        stale = period_end(ps[0]) < today and row["start"] > ps[1][:len(row["start"])] and not underway
        if stale:
            kept("starting", row["start"], ps, "a start that has passed while the page does not show the work under "
                 "way")
        else:
            swap("construction start", "starting", row["start"], ps)
            row["start"], row["startText"], row["startBasis"] = ps[0], ps[2], ps[3]
            if ps[4] is not None:
                unchecked(ps[4], "construction start", row["start"])
    elif row["start"]:
        if ps and ps[4] is not None and not agrees(js, row["start"]):
            notes.append("%s gives construction starting %s; %s project page text gives %s (“%s”)."
                         % (own("Start"), row["start"], owner, js["value"], one_line(js["span"])))
        elif ps and ps[4] is None and not page_agrees(ps, row["start"]):
            notes.append("%s gives construction starting %s; %s gives %s." % (own("Start"), row["start"], ps[3], ps[0]))
    elif ps:
        row["start"], row["startText"], row["startBasis"] = ps[0], ps[2], ps[3]
        sources.append({"field": "construction start", "date": row["start"], "text": row["startText"],
                        "from": ps[3], "url": url})
        if ps[4] is not None:
            unchecked(ps[4], "construction start", row["start"])
    if row["end"] and page_first and pe and not page_agrees(pe, row["end"]) \
            and pe[1] >= ((row["start"] or "") + "-01-01")[:10]:
        # An end that has passed, earlier than the feed's, on a job the page
        # does not call completed, is a plan overtaken: VL68's text gives
        # "April 2025" and its field "Spring, 2026", and the page still says
        # In progress, so the feed's 2026-09-30 is shown.
        stale = pe[1] < today and row["end"] > pe[1] and status != "completed"
        if stale:
            kept("ending", row["end"], pe, "an end that has passed while the page still gives the job as %s"
                 % (status.capitalize() or "not completed"))
        else:
            swap("construction end", "ending", row["end"], pe)
            row["end"] = pe[1]
            if pe[4] is not None:
                unchecked(pe[4], "construction end", row["end"])
    elif row["end"]:
        if pe and pe[4] is not None and not agrees(je, row["end"]):
            notes.append("%s gives construction ending %s; %s project page text gives %s (“%s”)."
                         % (own("Completion"), row["end"], owner, je["value"], spans(je)))
        elif pe and pe[4] is None and not page_agrees(pe, row["end"]):
            notes.append("%s gives construction ending %s; %s gives %s." % (own("Completion"), row["end"], pe[3], pe[1]))
    elif pe and pe[4] is None:
        row["end"] = pe[1]
        sources.append({"field": "construction end", "date": pe[1], "text": pe[2], "from": pe[3], "url": url})
    elif je.get("iso"):
        latest = e.get("latestStageDate") or ""
        if row["start"] and je["iso"] < (row["start"] + "-01-01")[:10]:
            notes.append("%s project page text gives the construction end as %s (“%s”), before the start of %s, so "
                         "it is not shown." % (owner, je["value"], spans(je), row["start"]))
        elif je["iso"] < data_today().isoformat() < latest:
            notes.append("%s project page gives an earlier phase's construction end, %s (“%s”), and dates later "
                         "work to %s with no construction end, so no end is shown."
                         % (owner, je["value"], spans(je), latest[:7]))
        else:
            row["end"] = je["iso"]
            sources.append({"field": "construction end", "date": je["iso"], "text": spans(je), "from": basis(je),
                            "url": url})
            unchecked(je, "construction end", row["end"])
    if jc.get("iso") and not row.get("consultation"):
        # The last day of the span, as for SFMTA's; its first date is known
        # only when the span closes a range the page gives on one line.
        # A span that names one day is one meeting, which starts and ends the
        # consultation the page dates (the Folsom Area webinar, 2025-12-02).
        first = jc["first"][:7] if jc.get("closes") else jc["iso"] if len(jc.get("value") or "") == 10 else None
        row["consultation"], row["consultationStart"] = jc["iso"], first
        if first:
            sources.append({"field": "first public consultation", "date": first, "text": one_line(jc["span"]),
                            "from": "%s project page text (“%s”)" % (owner, one_line(jc["span"])), "url": url})
        sources.append({"field": "latest public consultation", "date": jc["iso"], "text": spans(jc),
                        "from": basis(jc), "url": url})
        unchecked(jc, "latest public consultation", jc["iso"])
    return row


_SEASON_WORDS = r"winter|spring|summer|fall|autumn"


def spell_range(when):
    """Two range forms the stage readers split on spaced dashes miss, written out as ranges:
    "Summer-Fall 2021" and "Spring/Summer 2027" -> "Summer 2021 - Fall 2021"; "Winter 2023/2024" and
    "Winter 2025/26" -> "December 2023 - February 2024". A winter over the new year is the one season whose
    two years a page names (Clarendon, California Street; D2 hand grade, 2026-09-29)."""
    # A winter second ("Starting Fall/Winter 2024", Arguello) runs into the next year, which the page does not
    # name, so that form is left as it is.
    w = re.sub(r"\b(%s)\s*[-–/]\s*(spring|summer|fall|autumn)\s+(20\d\d)\b" % _SEASON_WORDS,
               lambda m: "%s %s - %s %s" % (m.group(1), m.group(3), m.group(2), m.group(3)), when or "", flags=re.I)
    return re.sub(r"\bwinter\s+(20\d\d)\s*/\s*(?:20)?(\d\d)\b",
                  lambda m: "December %s - February 20%s" % (m.group(1), m.group(2)), w, flags=re.I)


def season_date(when):
    """"Fall 2022" -> 2022-10; "Late spring 2026" -> 2026-05 (lib/seasons.py); "January 2023" -> 2023-01;
    "2023" -> 2023. A range gives its first date (spell_range)."""
    w = spell_range(when).lower()
    months = ("january", "february", "march", "april", "may", "june", "july", "august",
              "september", "october", "november", "december")
    y = re.search(r"\b(20\d\d)\b", w)
    if not y:
        return None
    # Only the words up to the first year, and the first of them: "December
    # 2023 - February 2024" is December, "Early 2018 - Spring 2019" is 2018.
    w = w[:y.end()]
    word = re.search(r"\b(%s|%s)\b" % ("|".join(months), _SEASON_WORDS), w)
    m = None
    if word and word.group(1) in months:
        m = months.index(word.group(1)) + 1
    elif seasons.first_qualified(w):
        m = seasons.first_qualified(w)[0]
    elif word:
        m = {"winter": 1, "spring": 4, "summer": 7, "fall": 10, "autumn": 10}[word.group(1)]
    return "%s-%02d" % (y.group(1), m) if m else y.group(1)


def stage_end(when):
    """The last day of a timeline stage's range: "2026 to 2029" -> 2029-12-31, "Spring 2027 - Fall 2028" -> 2028-11-30; None for a single date."""
    # "2026-2028" is a range too (29 Sunset, read 2026-09-28).
    when = re.sub(r"^\s*(20)(\d\d)\s*[-–]\s*(\d\d)\s*$", r"\1\2 - \1\3", spell_range(when))  # "2024-25" (Powell Promenade)
    when = re.sub(r"\b(20\d\d)\s*[-–—]\s*(?=(?:[A-Za-z]+\s+)?20\d\d\b)", r"\1 - ", when)
    parts = re.split(r"\s+(?:to|through|-|–|—)\s+", when)
    if len(parts) < 2:
        return None
    last = parts[-1].lower()
    y = re.search(r"\b(20\d\d)\b", last)
    if not y:
        return None
    month = next((i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"), 1) if m in last), None)
    if month is None and seasons.last_qualified(last):
        month = seasons.last_qualified(last)[1]  # "Late spring 2026" ends in June (lib/seasons.py)
    if month is None and re.search(r"\b(early|mid|late)\b", last):
        month = {"early": 4, "mid": 8, "late": 12}[re.search(r"\b(early|mid|late)\b", last).group(1)]
    # A bare "Winter 2026" at the end of a range is either the winter that ends early in 2026 or the one that starts
    # in December 2026. The later reading is taken: SFPUC's Bay Corridor Phase 4 page gives Construction End "Winter
    # 2026" and, updated October 2026, says the work lasts "through the end of 2026" (read 2026-11-10), so the
    # earlier reading took a project still under construction off the list. Straight after a fall of the year
    # before ("Fall 2025 - Winter 2026") it is the winter that follows, ending in February.
    if month is None:
        word = next((w for w in ("winter", "spring", "summer", "fall", "autumn") if w in last), "")
        month = {"winter": 12, "spring": 5, "summer": 8, "fall": 11, "autumn": 11}.get(word, 12)
        prev = parts[-2].lower()
        if word == "winter" and re.search(r"\b(fall|autumn)\s+%d\b" % (int(y.group(1)) - 1), prev):
            month = 2
    nxt = dt.date(int(y.group(1)) + (month == 12), month % 12 + 1, 1)
    return (nxt - dt.timedelta(days=1)).isoformat()


def sig2(x):
    if x == 0:
        return 0
    return float("%.2g" % x)


def retired(registry, status_notes=None):
    """Every address no longer listed: where it redirects, or, for a notice page, what the sources still say.

    `status_notes` maps a project id to the sentence that gives both SFMTA's
    and Public Works' status for a project both publish (criterion B3). A
    notice page carries it, so a project taken off the list still shows the
    disagreement (Upper Market Street Safety Project: Implementation /
    Construction on SFMTA's layer, Completed on Public Works' page).
    """
    status_notes = status_notes or {}
    out = []
    for slug, e in sorted(registry.items()):
        if e.get("listed"):
            continue
        pid = e.get("id")
        to, seen = e.get("alias") or e.get("redirect"), {slug}
        while to and to not in seen and registry.get(to, {}).get("listed") is not True:
            seen.add(to)
            nxt = registry.get(to, {})
            pid = pid or nxt.get("id")
            to = nxt.get("alias") or nxt.get("redirect")
        row = {"slug": slug, "name": e["name"],
               "redirect": to if to and registry.get(to, {}).get("listed") else None}
        if row["redirect"] is None and status_notes.get(pid):
            row["statusNote"] = status_notes[pid]
        out.append(row)
    return out


# The day every window in this script is measured from: the day its data was
# read, never the wall clock (pipeline/README.md, rule 3). A run on a later
# day over the same data must write the same files; with the wall clock, a run
# two months on dropped 15 rows and rewrote three tracked files (review of
# 2026-09-29). Set once in main() by data_date().
DATA_TODAY = None


def data_today():
    if DATA_TODAY is None:
        raise RuntimeError("data_today() before main() read the inputs' dates")
    return DATA_TODAY


def data_date(feed, record):
    """The newest date any input was read: the coordination feed's pull, SFMTA's layer and pages, Public Works' pages.

    Each is the source's own read date as the script that fetched it wrote
    it, and each moves only when that fetch brought something new (the
    Socrata cache keeps its pull date until the dataset changes; the extracts
    and out/ files are written through lib/stable.py, so a stamp alone never
    changes). So the date moves when the data does, and not otherwise.
    """
    dates = [feed.fetched_on.isoformat(), str(record.get("generated") or "")[:10]]
    for path, key in ((SFMTA_PAGES, "generated"), (SFMTA_PAGES_TEXT, "generated"), (DPW_PROJECTS, "fetched_on"),
                      (UPCOMING, "generated")):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                dates.append(str(json.load(fh).get(key) or "")[:10])
    return dt.date.fromisoformat(max(d for d in dates if re.match(r"^\d{4}-\d{2}-\d{2}$", d)))


def pretend_clock(day):
    """--today: run as if the wall clock read this day, to prove no output depends on it.

    Replaces datetime.date for this process, so a stray date.today() anywhere
    in this script or a library it calls returns the pretend day. The data's
    own date, not this, is what every window is measured from."""
    real = dt.date

    class PretendDate(real):
        @classmethod
        def today(cls):
            return real.fromisoformat(day)
    dt.date = PretendDate


def main():
    global DATA_TODAY
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--today", help="pretend the wall clock reads this day (YYYY-MM-DD); the output must not change")
    args = ap.parse_args()
    if args.today:
        pretend_clock(args.today)

    record = json.load(open(RECORD, encoding="utf-8"))
    by_id = {p["id"]: p for p in record["projects"]}
    pblocks = json.load(open(BLOCKS))["projects"]

    feed = fetch(FEED)  # the cached pull; never refreshed from here
    DATA_TODAY = data_date(feed, record)
    today = DATA_TODAY.isoformat()
    rows_by_job = collections.defaultdict(list)
    for r in feed.rows:
        pid = str(r.get("dotmapsid") or "").strip()
        if pid:
            rows_by_job[pid].append(r)

    traced = json.load(open(TRACED))
    # Plan miles are per direction of travel, the plan's own unit (its 472
    # miles, printed p. 20, sum the bikeway layer's direction rows): a block's
    # layer rows, or its centerline times its directions, times the share of
    # the block the plan's line covers (lib/mile_basis.py), the same
    # metres site/data/north-star/status.json gives the block.
    D = Directions()
    plan = {}
    for f in traced["features"]:
        pr = f["properties"]
        plan[pr["cnn"]] = {
            "facility": pr["facility"], "street": pr.get("street") or "",
            "dir_m": D.plan_metres(pr["cnn"], pr.get("length_m"), pr.get("share", 1.0)),
            "pts": [[round(x, 5), round(y, 5)] for x, y in f["geometry"]["coordinates"]],
        }
    # All-ages today: a block that later stopped being one carries `until`.
    all_ages = {f["properties"]["cnn"] for f in json.load(open(ALL_AGES))["features"]
                if "until" not in f["properties"]}
    seg_pts = {s["cnn"]: s["pts"] for s in json.load(open(SEGMENTS))["segments"]}

    # For the plan rating: each plan block's metres on direction rows that
    # meet the plan today, the blocks the bikeway history credits to each
    # SFMTA project, and the blocks and class SFMTA's pages name for work to
    # come (planned.json, reported.json) or say why none can be read
    # (planned.json's uncounted).
    status_src = json.load(open(PLAN_STATUS))
    met_m = {b["cnn"]: b["met_m"] for b in status_src["blocks"]}
    bh_src = json.load(open(BH_PROJECTS))
    credited = collections.defaultdict(set)
    # A Slow Street the history names from the Slow Streets dataset
    # ("slow:cayugaavenue") joins its SFMTA row by name.
    credited_by_name = collections.defaultdict(set)
    first_year = {}  # node or slow_key name -> the first year the history credits the project with
    for bp in bh_src["projects"]:
        key = str(bp["node"])
        credited[key] |= set(bp.get("blocks") or ())
        if bp.get("years"):
            first_year[key] = min(first_year.get(key, 9999), bp["years"][0])
        if key.startswith("slow:"):
            credited_by_name[slow_key(bp["name"])] |= set(bp.get("blocks") or ())
            if bp.get("years"):
                first_year[slow_key(bp["name"])] = min(first_year.get(slow_key(bp["name"]), 9999), bp["years"][0])
    # Each block's best bikeway class year by year (segments.json `y`, one
    # character per year), for what a credited project's blocks had before it.
    seg_src = json.load(open(SEGMENTS))
    seg_years = seg_src["years"] if isinstance(seg_src["years"], list) else seg_src["series"]["years"]
    seg_code = {x["cnn"]: x["y"] for x in seg_src["segments"] if x.get("cnn")}
    planned_src = json.load(open(BH_PLANNED))
    reported_src = json.load(open(BH_REPORTED))
    to_come = collections.defaultdict(list)  # node -> [(source label, url, quote, class, directions, blocks)]
    for src, label in ((planned_src, "SFMTA's project page"), (reported_src, "SFMTA's project page, work reported this year")):
        for bp in src["projects"]:
            to_come[str(bp["node"])].append((label, bp["page"], bp.get("quote"), bp["class"], bp.get("directions"),
                                             bp["blocks"]))
    uncounted = {str(u["node"]): u["why"] for u in planned_src.get("uncounted") or ()}

    # Census blocks are measured from their street frontage, as on the overview.
    walknet.use_census_outlines()
    reach_src = json.load(open(REACH))
    assert reach_src["reach_miles"] == REACH_MILES
    cols = reach_src["blocks"]["columns"]
    bi = {c: i for i, c in enumerate(cols)}
    # The overview's distances, shortest first; the default is the plan's
    # quarter mile.
    thresholds = sorted(reach_src["thresholds"], key=lambda t: t["metres"])
    default_reach = reach_src["default_reach"]
    assert default_reach == thresholds[-1]["id"], "the default must be the longest distance, which the walk is cut off past"
    assert thresholds[-1]["metres"] <= walknet.CUTOFF_M
    top_m = thresholds[-1]["metres"]
    latest = reach_src["years"][-1]

    # Only what today's all-ages network does not already reach can be added.
    # reach.json carries, per point and distance, the first year a point was
    # walked within reach and the later years it was out again; the overview's
    # map lights it in year Y when 0 < reach <= Y and Y is not in `off`. A
    # point unlit in the latest year is unreached today at that distance.
    def lit(first, off):
        return bool(first) and first <= latest and latest not in (off or ())

    def block_lit(r, tid):
        sfx = "" if tid == default_reach else "_" + tid
        return lit(r[bi["reach" + sfx]], r[bi["off" + sfx]])

    def point_lit(x, tid):
        if tid == default_reach:
            return lit(x["reach"], x.get("off"))
        return lit(x["reach_by"][tid], x["off_by"][tid])

    all_blocks = [(r[bi["lon"]], r[bi["lat"]], r[bi["pop2020"]], {t["id"]: block_lit(r, t["id"]) for t in thresholds})
                  for r in reach_src["blocks"]["rows"]]
    # The schools and branches the overview counts in the latest year:
    # schools_in() and libs_in() in scripts/bike-network-history.py. A school
    # opens by the count date and has not closed by it; a branch closed for
    # works (Mission, from 2020) is not counted until it reopens.
    count_day = "%d-%s" % (latest, reach_src["count_date"])
    all_schools = [(s, {t["id"]: point_lit(s, t["id"]) for t in thresholds})
                   for s in reach_src["schools"]
                   if s["open"] <= count_day and (not s.get("closed") or s["closed"] >= count_day)]
    all_libraries = [(l, {t["id"]: point_lit(l, t["id"]) for t in thresholds}) for l in reach_src["libraries"]
                     if not (l.get("closed_from") and latest >= l["closed_from"]
                             and (l.get("reopens") is None or latest < l["reopens"]))]
    # The overview's walk-reach.json is written from the same walk network in
    # the same pipeline run; a network refetched since would measure the
    # project and the network it adds to on different streets.
    walk_doc = json.load(open(WALK_REACH))
    assert walk_doc["network"]["fetched_on"] == walknet.graph().osm_base, (
        "data/osm-cache/sf-walk.json (%s) is not the network the overview was walked on (%s); rerun the bike steps"
        % (walknet.graph().osm_base, walk_doc["network"]["fetched_on"]))
    # Points unreached today at one distance or more: the only ones a project can add.
    cand_blocks = [b for b in all_blocks if not all(b[3].values())]
    cand_schools = [s for s in all_schools if not all(s[1].values())]
    cand_libraries = [l for l in all_libraries if not all(l[1].values())]
    unreached_by = {t["id"]: {"blocks": sum(1 for b in all_blocks if not b[3][t["id"]]),
                              "residents": int(round(sum(b[2] for b in all_blocks if not b[3][t["id"]]))),
                              "schools": sum(1 for _, k in all_schools if not k[t["id"]]),
                              "libraries": sum(1 for _, k in all_libraries if not k[t["id"]])}
                    for t in thresholds}

    # ---- Public Works feed jobs --------------------------------------------
    jobs = {}
    for pid, rows in rows_by_job.items():
        r0 = rows[0]
        agency = r0.get("agency_name") or ""
        dept = department(agency)
        if dept is None:
            continue
        rec = by_id.get("dotmaps:%s" % pid)
        if rec is None:
            continue
        start = min((day(r.get("start_date")) for r in rows if day(r.get("start_date"))), default=None)
        end = max((day(r.get("end_date")) for r in rows if day(r.get("end_date"))), default=None)
        if end and end < today:
            continue  # finished; nothing left to coordinate
        desc = " ".join(sorted({(r.get("description") or "").strip() for r in rows} - {"", "NONE", "N/A"}))
        text = "%s %s" % (r0.get("name") or "", desc)
        streets = sorted({title(str(r.get("on_street")).strip()) for r in rows if r.get("on_street")})
        jobs[pid] = {
            "source": "dotmaps", "id": "dotmaps:%s" % pid, "name": r0.get("name") or "",
            "department": dept, "agency": agency, "phase": r0.get("project_phase") or "",
            "start": start, "end": end, "startBasis": "the coordination feed's start date" if start else None,
            "streets": streets, "cnns": set(rec["cnns"]),
            "scopeText": EMAIL.sub("[email removed]", desc),
            "scopeNamesBike": bool(BIKE_WORDS.search(text)),
            "record": rec,
            "links": [{"label": "Interagency coordination feed record (DataSF row)", "url": ROW_URL.format(pid), "department": dept}],
            "geometryKind": "line",
        }

    # ---- One job the feed carries twice -----------------------------------------
    # The same department and the same name is one job entered twice
    # ("Broad Street and Randolph Street Sewer Replacement", rows 61050 and
    # 61339, both contract WW-734, read 2026-09-28). The lowest row id keeps
    # the row, so its page address holds; the other's address redirects to it
    # (lib/project_ids.py, alsoIds). Both rows' dates are printed when
    # they differ, since neither is more right than the other.
    # A shared name alone is not enough (review, 2026-09-29): two rows fold
    # only when they share a contract or project number the feed carries
    # (PeopleSoft id, client contract id, external id, or one written in the
    # description: 61339's description "2300i, WW-734" is 61050's contract;
    # 31167's PeopleSoft id 10038465 is 25702's external id) or hold mostly
    # the same blocks (Jaccard 0.5 or more). Same-name rows that do neither
    # stay two rows.
    def contract_ids(rows):
        ids = set()
        for r in rows:
            for k in ("peoplesoft_id", "client_contract_id", "external_id"):
                v = str(r.get(k) or "").strip().upper()
                if v and v not in ("_NA", "NA", "N/A", "NONE", "0"):
                    ids.add(v)
            ids |= {t.upper() for t in re.findall(r"\b(?:\d{4}[A-Z]|[A-Z]{2,3}-\d{3,4}[A-Z]?|\d{8})\b",
                                                  r.get("description") or "", re.I)}
        return ids

    def same_job(a, b):
        ja, jb = jobs[a], jobs[b]
        shared = contract_ids(rows_by_job[a]) & contract_ids(rows_by_job[b])
        if shared:
            return "shares %s %s" % ("number" if len(shared) == 1 else "numbers", " and ".join(sorted(shared)))
        union = ja["cnns"] | jb["cnns"]
        if union and len(ja["cnns"] & jb["cnns"]) / len(union) >= 0.5:
            return "holds %d%% of the same blocks" % round(100 * len(ja["cnns"] & jb["cnns"]) / len(union))
        return None

    twins = collections.defaultdict(list)
    for pid, j in jobs.items():
        twins[(j["department"], norm_name(j["name"]))].append(pid)
    groups, foldwhy = [], {}
    for key, pids in sorted(twins.items()):
        pids.sort(key=int)
        # Fold each row into the first earlier row it is the same job as.
        heads = []
        for pid in pids:
            for g in heads:
                why = same_job(g[0], pid)
                if why:
                    g.append(pid)
                    g_why = foldwhy.setdefault(g[0], [])
                    g_why.append("row %s %s with row %s" % (pid, why, g[0]))
                    break
            else:
                heads.append([pid])
        groups += [g for g in heads if len(g) > 1]
    for pids in groups:
        keep = jobs[pids[0]]
        keep["alsoIds"] = []
        spans = [(pids[0], keep["phase"], keep["start"], keep["end"])]
        for pid in pids[1:]:
            j = jobs.pop(pid)
            keep["alsoIds"].append(j["id"])
            keep["cnns"] |= j["cnns"]
            keep["streets"] = sorted(set(keep["streets"]) | set(j["streets"]))
            keep["links"] += [l for l in j["links"] if l["url"] not in {x["url"] for x in keep["links"]}]
            keep["scopeNamesBike"] = keep["scopeNamesBike"] or j["scopeNamesBike"]
            keep["mergedRecords"] = keep.get("mergedRecords", []) + j["record"]["records"]
            spans.append((pid, j["phase"], j["start"], j["end"]))
        if len({s[1:] for s in spans}) > 1:
            keep.setdefault("dateNotes", []).append(
                "The coordination feed carries this job as %d rows (%s) that disagree: %s. The dates "
                "shown are row %s's." % (
                    len(spans), "; ".join(foldwhy.get(pids[0], [])),
                    "; ".join("row %s, %s, %s to %s" % (pid, ph or "no phase", s or "no start", e or "no end")
                              for pid, ph, s, e in spans), pids[0]))

    # ---- Department pages matched to feed jobs --------------------------------
    # A match to the job's own project page, or to its department's page for
    # the job's contract (a bid page), is the job's page and goes first. A
    # programme page that lists the contract, or Public Works' paving map, is
    # the closest official source for a job with no page of its own; it is
    # labelled so, goes after the feed row, and is not counted as the job's
    # page (kind "program").
    dept_match, closest = {}, {}
    if os.path.exists(DEPT_MATCHES):
        for m in json.load(open(DEPT_MATCHES))["matches"]:
            if m.get("confidence") in ("high", "medium") and m.get("pageKind", "project") in ("project", "contract"):
                dept_match[m["id"]] = m
            elif m.get("closest"):
                closest[m["id"]] = m["closest"]
            elif m.get("noSource"):
                # Searched for and on no official page: the row says so
                # (tools/projects/department-project-pages.py, NO_SOURCE).
                no_source[m["id"]] = m["noSource"]
    for pid, j in jobs.items():
        m = dept_match.get(j["id"])
        if m:
            j["links"].insert(0, {
                "label": ("%s contract page (%s)" % (m["pageDepartment"], m["title"])
                          if m.get("pageKind") == "contract" else "%s project page" % m["pageDepartment"]),
                "url": m["url"], "department": m["pageDepartment"], "match": m["method"],
                "confidence": m["confidence"], "kind": m.get("pageKind", "project")})
            if m.get("fallback"):
                # A bid page goes when the contract is awarded; the paving
                # map stays (tools/projects/department-project-pages.py, fallback).
                f = m["fallback"]
                j["links"].append({
                    "label": "When the bid page closes at award, the closest official source: %s" % f["title"],
                    "url": f["url"], "department": f["department"], "kind": "program", "why": f["why"]})
        elif j["id"] in closest:
            c = closest[j["id"]]
            j["links"].append({
                "label": "No %s page for this job; closest official source: %s" % (j["department"], c["title"]),
                "url": c["url"], "department": c["department"], "kind": "program", "why": c["why"]})

    # ---- SFMTA projects ------------------------------------------------------
    # Every project on the layer and every /projects/ page in the sitemap, each
    # decided by sfmta_decision from its own scope.
    sfmta = {}
    decisions = []
    no_phase = 0
    page_text = {str(p["node"]): p.get("pageText") for p in json.load(open(SFMTA_PAGES_TEXT))["projects"]}
    layer_meta = {str(p["node"]): p for p in json.load(open(SFMTA_PAGES_TEXT))["projects"]}
    spages = json.load(open(SFMTA_PAGES))["pages"]
    # Layer nodes whose own page failed to load when last read (403, 404, 410).
    gone = {str(n): re.sub(r"^HTTP Error ", "HTTP ", why) for n, why in json.load(open(SFMTA_PAGES)).get("failed") or []
            if re.search(r"\b(?:403|404|410)\b", why)}

    def page_records(pg):
        """An SFMTA page's own timeline, notices and meetings, as tools/projects/project-record.py reads them."""
        # Labelled exactly as project-record.py's attach_page_records labels a
        # layer project's page: every item is a project-page item, with the
        # block it came from. A "meetings" row is an open house or a tabling
        # table as often as a Board date (N Judah's farmers-market tabling
        # showed as "SFMTA Board"), and the body's own record of a vote comes
        # from its mirror, so nothing here is labelled as a city body.
        out = []
        for t in pg.get("timeline") or ():
            out.append({"kind": "project-page", "pageBlock": "timeline", "date": season_date(t["when"]) or "",
                        "when": t["when"], "title": t["what"], "decision": t.get("status"), "url": pg["page"],
                        "grade": "exact", "relation": OWN_PAGE_RELATION})
        for block, rows_ in (("notice", pg.get("notices") or []), ("event", pg.get("meetings") or [])):
            for r in rows_:
                out.append({"kind": "project-page", "pageBlock": block, "date": r.get("date") or "",
                            "title": r["title"], "url": r["url"], "grade": "exact", "relation": OWN_PAGE_RELATION})
        return out

    def sfmta_row(p, node, text, methods, phase, phase_basis, bike):
        pg = spages.get(str(node).split(":", 1)[-1]) or spages.get("slug:" + str(node).split(":", 1)[-1]) or {}
        return with_page_dates(_sfmta_row(p, node, text, methods, phase, phase_basis, bike), node, p["records"],
                               (text or "") + " " + (pg.get("pageText") or ""))

    def _sfmta_row(p, node, text, methods, phase, phase_basis, bike):
        # The project page's own timeline, for when construction starts.
        cons = [r for r in p["records"] if r["kind"] == "project-page"
                and (r.get("pageBlock") or "timeline") == "timeline"
                # the milestone, not the stage group in brackets after it
                # ("Detailed Design (… - Detailed Design/Construction)")
                and re.search(r"construct|implement", (r["title"] or "").split(" (")[0], re.I) and r.get("date")]
        cons.sort(key=lambda r: r["date"])
        # A page with several construction stages (Folsom-Howard: Folsom 2024
        # to 2026, Howard 2026 to 2029) spans the first stage's start to the
        # last stage's end.
        # "Summer - fall 2025" starts in summer (range_start), not at the
        # month project-record.py dates the stage by (Fable review, 2026-09-29).
        start = min(range_start(r["when"]) or r["date"] for r in cons) if cons else None
        ends = [e for e in (stage_end(r["when"]) for r in cons) if e]
        end = max(ends) if ends else None
        when_text = "; ".join(r["when"] for r in cons) if cons else None
        basis = ("the project page's timeline (“%s”)" % when_text) if cons else None
        if not cons:
            start, end, quote = prose_dates(text)
            # An end before the start is an earlier phase's (San Bruno Avenue:
            # "first phase ... completed in August 2017", full construction
            # "began in early 2019"), not this one's.
            if start and end and end < start:
                end = None
            if start or end:
                when_text = quote
                basis = "the project page's text (“%s”)" % quote
        return {
            "source": "sfmta", "id": p["id"], "name": p["name"], "department": "SFMTA",
            "agency": "SFMTA", "phase": phase, "phaseBasis": phase_basis, "start": start, "end": end,
            "startBasis": basis,
            "startText": when_text,
            "streets": [title(s) for s in p["streets"] or p["streetsFromText"][:4]],
            "cnns": set(p["cnns"]) | set(pblocks.get(node, {}).get("cnns", ())), "scopeText": None, "scopeNamesBike": True,
            "record": p, "bikeScope": bike, "pageText": text,
            "links": [{"label": "SFMTA project page", "url": p["page"], "department": "SFMTA"}],
            "geometryKind": ("none" if not methods else
                             "area" if "polygon" in methods and "line" not in methods else "line"),
        }

    layer_names = set()
    for p in record["projects"]:
        if not p["id"].startswith("sfmta:"):
            continue
        node = p["id"].split(":")[1]
        meta = layer_meta.get(node, {})
        pg = spages.get(node) or {}
        p["name"] = unmangle(p["name"])
        layer_names.add(norm_name(p["name"]))
        if p["bike"] and p["phase"] is None:
            no_phase += 1
        ok, reason, phase, phase_basis = sfmta_decision(p["name"], meta.get("types") or [], p["phase"], pg, True)
        decisions.append({"id": p["id"], "name": p["name"], "page": p["page"], "onLayer": True,
                          "tags": meta.get("types") or [], "layerPhase": p["phase"], "pagePhase": pg.get("phase"),
                          "listed": ok, "reason": reason})
        if not ok:
            continue
        methods = pblocks.get(node, {}).get("methods", [])
        plan_only = reason == PLAN_ONLY
        sfmta[node] = sfmta_row(p, node, page_text.get(node) or pg.get("pageText"), methods, phase, phase_basis,
                                not plan_only and ("Bike" in (meta.get("types") or []) or bike_named(p["name"])))
        sfmta[node]["planOnly"] = plan_only
        sfmta[node]["decision"] = decisions[-1]
        sfmta[node]["evidence"] = page_evidence(pg)
        sfmta[node]["current"] = current_evidence(pg)
        sfmta[node]["ended"] = timeline_ended(pg)
        if node in gone and node in SFMTA_GONE_CLOSEST:
            url, what, why = SFMTA_GONE_CLOSEST[node]
            sfmta[node]["links"] = [{
                "label": "No SFMTA page for this project (sfmta.com answers “Content Not Found”, %s, though its "
                         "project layer still lists one); closest official source: %s" % (gone[node], what),
                "url": url, "department": "SFMTA", "kind": "program", "why": why}]

    # Pages SFMTA publishes but does not map: no geometry, so no blocks.
    for key, pg in sorted(spages.items()):
        if pg.get("on_layer"):
            continue
        name = pg.get("title") or pg.get("name")
        section = SFMTA_SECTION_PAGES.get(key.split(":", 1)[-1])
        if section:
            node, evidence = section
            decisions.append({"id": "sfmta-page:" + key.split(":", 1)[-1], "name": name, "page": pg["page"],
                              "onLayer": False, "tags": [], "layerPhase": None, "pagePhase": pg.get("phase"),
                              "listed": False, "reason": "a section of sfmta:%s's page, linked from its row (%s)"
                                                         % (node, evidence)})
            if node in sfmta:
                sfmta[node]["links"].append({"label": "SFMTA project page (%s)" % name, "url": pg["page"],
                                             "department": "SFMTA"})
            continue
        if norm_name(name) in layer_names:
            decisions.append({"id": "sfmta-page:" + key.split(":", 1)[-1], "name": name, "page": pg["page"],
                              "onLayer": False, "tags": [], "layerPhase": None, "pagePhase": pg.get("phase"),
                              "listed": False, "reason": "the same project as one on SFMTA's layer"})
            continue
        ok, reason, phase, phase_basis = sfmta_decision(name, [], None, pg, False)
        pid = "sfmta-page:" + key.split(":", 1)[-1]
        decisions.append({"id": pid, "name": name, "page": pg["page"], "onLayer": False, "tags": [],
                          "layerPhase": None, "pagePhase": pg.get("phase"), "listed": ok, "reason": reason})
        if not ok:
            continue
        # tools/projects/project-record.py matches these pages against every body's
        # mirror by name and contract number (they have no blocks), so the
        # District 2 Safety Study's SFCTA adoption reaches its row. The page's
        # own items are read here, as for every SFMTA row.
        matched = [r for r in (by_id.get(pid) or {}).get("records", []) if r["kind"] != "project-page"]
        p = {"id": pid, "name": name, "phase": phase, "page": pg["page"], "records": page_records(pg) + matched,
             "pageDocuments": pg.get("documents") or [], "cnns": [],
             "streets": sorted(streets_of(name)), "streetsFromText": []}
        if pid in by_id:
            record["projects"] = [p if x["id"] == pid else x for x in record["projects"]]
        else:
            record["projects"].append(p)
        by_id[pid] = p
        sfmta[pid] = sfmta_row(p, pid, pg.get("pageText"), [], phase, phase_basis, bike_named(name))

    # ---- One project where both publish it ------------------------------------
    # Same name, or the feed row matched to the SFMTA project's page.
    by_norm = {norm_name(s["name"]): s for s in sfmta.values()}
    by_page = {}
    for s in sfmta.values():
        by_page[s["record"]["page"].rstrip("/")] = s
        pg = spages.get(s["id"].split(":", 1)[1]) or spages.get("slug:" + s["id"].split(":", 1)[1]) or {}
        if pg.get("canonical"):
            by_page[pg["canonical"].rstrip("/")] = s
    merged_pairs = 0
    for pid, j in list(jobs.items()):
        s = by_norm.get(norm_name(j["name"]))
        m = dept_match.get(j["id"])
        if not s and m and j["department"] == "SFMTA" and m["pageDepartment"] == "SFMTA":
            s = by_page.get(m["url"].rstrip("/"))
        if not s:
            continue
        if j["links"][0].get("department") == "SFMTA" and j["links"][0].get("match"):
            j["links"].pop(0)  # the SFMTA row already links its own page
        s["links"] += [l for l in j["links"] if l["url"] not in {x["url"] for x in s["links"]}]
        if j["department"] != "SFMTA":
            s.setdefault("partners", []).append(j["department"])
        if s["geometryKind"] == "none" and j["cnns"]:
            s["geometryKind"] = "line"  # a page SFMTA does not map, placed by the feed's blocks
        s["cnns"] |= j["cnns"]
        s["feedId"] = pid
        s["feedPhase"] = j["phase"]
        # SFMTA's own page dates the project; the feed's row fills a date the
        # page leaves empty, and where both give one and they disagree, the
        # row prints both. The feed used to replace the page's dates outright,
        # so Contract 35 showed the feed's 2026-04-02 while its page says
        # construction started in August 2026 (D2 hand grade, 2026-09-29).
        feed_src = lambda f, v: {"field": f, "date": v, "text": None, "from": "the coordination feed",
                                 "url": ROW_URL.format(pid)}
        for key, field, word in (("start", "construction start", "starting"), ("end", "construction end", "ending")):
            if not j[key]:
                continue
            page = next((d for d in s.get("dateSources", []) if d["field"] == field), {})
            # A page date that has passed, from a timeline stage the page
            # still marks Pending, is a plan the department has not updated;
            # the feed's later date is shown and the page's printed beside
            # it (Beach Street's "Anticipated Winter 2025" against the feed's
            # 2026-04-01; Fable review, 2026-09-29).
            pend = [r["when"] for r in (s.get("record") or {}).get("records", []) if r.get("when")
                    and (r.get("pageBlock") or "timeline") == "timeline" and (r.get("decision") or "").lower() == "pending"]
            said = (page.get("from") or "") + " " + (page.get("text") or "")
            stale = bool(s[key]) and ("(pending)" in said.lower() or any("“%s”" % w in said for w in pend)) \
                and (s[key] + "-12-31"[len(s[key]) - 4:] if len(s[key]) < 10 else s[key]) < data_today().isoformat() \
                and j[key] > s[key]
            # A page that gives only the year the feed's day falls in agrees
            # with it, and the feed's day is the more precise (Cayuga "2026
            # - 2029" against the feed's 2026-10-01).
            finer = bool(s[key]) and len(s[key]) == 4 and j[key].startswith(s[key])
            if not s[key] or stale or finer:
                if stale:
                    s.setdefault("dateNotes", []).append(
                        "SFMTA's project page gives construction %s %s, a stage it still marks Pending; the "
                        "coordination feed gives %s, which is shown." % (word, s[key], j[key]))
                s[key] = j[key]
                if key == "start":
                    s["startBasis"], s["startText"] = j["startBasis"], None
                s["dateSources"] = [d for d in s.get("dateSources", []) if d["field"] != field] + [feed_src(field, j[key])]
            elif j[key][:7] != s[key][:7]:
                s.setdefault("dateNotes", []).append(
                    "The coordination feed gives construction %s %s; SFMTA's project page gives %s, which is shown."
                    % (word, j[key], s[key]))
        s["scopeText"] = j["scopeText"]
        s["bikeScope"] = s["bikeScope"] or j["scopeNamesBike"]
        s["mergedRecords"] = s.get("mergedRecords", []) + j["record"]["records"]
        del jobs[pid]
        merged_pairs += 1

    # ---- Public Works pages no feed job carries -----------------------------------
    # Public Works publishes projects in progress that the coordination feed
    # has no row for, or whose row ended (Junipero Serra, Beale Street,
    # Masonic Avenue, read 2026-09-28). Each one whose blocks touch the plan is
    # a row of its own, dated by its page's Start and Completion fields.
    dpw_records = json.load(open(DPW_PROJECTS))["records"] if os.path.exists(DPW_PROJECTS) else []
    dept_pages = {p["url"]: p for p in json.load(open(DEPT_PAGES))["pages"]} if os.path.exists(DEPT_PAGES) else {}
    pw_pages = {}
    taken_urls = {l["url"] for c in list(sfmta.values()) + list(jobs.values()) for l in c["links"]}
    taken_names = [c["name"] for c in list(sfmta.values()) + list(jobs.values())]
    # A page's blocks are the corridor between the limits its Location field
    # names (lib/pw_extent.py), never every block of every street it
    # names: Beale Street Improvement Project, three blocks of Beale, held
    # every block of Market and Folsom that way (review, 2026-09-29).
    extents = None
    for r in sorted(dpw_records, key=lambda r: r["id"]):
        if (r.get("status") or "").lower() not in PW_ACTIVE:
            continue
        if r["url"] in taken_urls or any(same_name(r["name"], n) for n in taken_names):
            continue
        extents = extents or Extents()
        ext = extents.of(r.get("location"))
        cnns = sorted(ext.cnns)
        place_note = None
        if ext.flag and cnns:
            place_note = ("Public Works' page names no limits the city's street centreline has (Location: “%s”), so "
                          "the map shows all of %s." % (r.get("location"), title(ext.corridor_name)))
        if not cnns:
            # A page that names no blocks is placed by SFMTA's map of the same
            # project when SFMTA maps one (Upper Haight Transit Improvement
            # and Pedestrian Realm Project, read 2026-09-28); the row links
            # SFMTA's page below.
            twin = next((q for q in record["projects"] if q["id"].startswith("sfmta:") and q.get("cnns")
                         and same_name(r["name"], q["name"])), None)
            if twin is None:
                continue
            cnns = list(twin["cnns"])
        pg = dept_pages.get(r["url"]) or {}
        start = season_date(pg.get("start")) if pg.get("start") else None
        end = stage_end("x - " + pg["completion"]) if pg.get("completion") else None
        pid = r["id"]
        # The streets the row names are the ones its blocks lie on, not the
        # cross streets that bound it.
        streets_named = [s for s in (r.get("streets") or []) if canon(s) in {extents.bi.blocks[x]["street"]
                                                                           for x in cnns if x in extents.bi.blocks}]
        # tools/projects/project-record.py matches in-progress Public Works pages
        # against every body's mirror by name and contract number
        # (load_dpw_pages), so the SFCTA's 2020 allocation reaches the Page
        # Street Neighborway row.
        matched = [x for x in (by_id.get(pid) or {}).get("records", []) if x["kind"] != "project-page"]
        rec = {"id": pid, "name": r["name"], "phase": r["status"], "page": r["url"], "records": matched,
               "pageDocuments": [{"title": d["label"], "url": d["url"]} for d in r.get("documents") or []],
               "cnns": cnns, "streets": streets_named or r.get("streets") or [], "streetsFromText": []}
        if pid in by_id:
            record["projects"] = [rec if x["id"] == pid else x for x in record["projects"]]
        else:
            record["projects"].append(rec)
        by_id[pid] = rec
        pw_pages[pid] = {
            "source": "dpw-page", "id": pid, "name": r["name"], "department": "Public Works",
            "agency": "Public Works", "phase": r["status"],
            "phaseBasis": "Public Works' project page (Status)",
            "start": start, "end": end,
            "startBasis": ("Public Works' project page (Start “%s”, Completion “%s”)" % (pg.get("start"), pg.get("completion"))
                           if start else None),
            "startText": pg.get("start"),
            "streets": sorted({title(s) for s in streets_named or r.get("streets") or []}), "cnns": set(cnns),
            "placeNote": place_note,
            "extentBasis": ext.basis if ext.cnns else "SFMTA's map of the same project",
            "scopeText": EMAIL.sub("[email removed]", r.get("description") or "")[:600] or None,
            "scopeNamesBike": bool(BIKE_WORDS.search("%s %s" % (r["name"], r.get("description") or ""))),
            "record": rec, "needsPlan": True,
            "links": [{"label": "Public Works project page", "url": r["url"], "department": "Public Works",
                       "kind": "project"}],
            "geometryKind": "line",
        }

    # ---- SFPUC pages no feed job carries -----------------------------------------
    # SFPUC's own project list (data/extract/sfpuc-projects/projects.json, from
    # tools/projects/department-project-pages.py) holds jobs in construction that the
    # coordination feed has no row for: San Bruno Avenue & Blanken Avenue Water
    # Main Replacement, in construction June 2025 to November 2026 (read
    # 2026-09-29). Each one not finished whose blocks touch the plan is a row of
    # its own, as a Public Works page is above. Its blocks are the ones the
    # extract read from the page's text.
    puc_records = json.load(open(PUC_PROJECTS))["records"] if os.path.exists(PUC_PROJECTS) else []
    taken_names += [c["name"] for c in pw_pages.values()]
    for r in sorted(puc_records, key=lambda r: r["id"]):
        if (r.get("status") or "").lower() not in PW_ACTIVE or not r.get("cnns") or r.get("feedJobs"):
            continue
        if r["url"] in taken_urls or any(same_name(r["name"], n) for n in taken_names):
            continue
        pid = r["id"]
        cnns = sorted(r["cnns"])
        # The corridors the page's text names ("San Bruno Avenue between Paul
        # and Campbell" names San Bruno Avenue).
        streets_named = sorted({c.split(" between ")[0].strip() for c in (r.get("location") or "").split("; ") if c})
        start = season_date(r.get("constructionStart")) if r.get("constructionStart") else None
        end = stage_end("x - " + r["constructionEnd"]) if r.get("constructionEnd") else None
        matched = [x for x in (by_id.get(pid) or {}).get("records", []) if x["kind"] != "project-page"]
        rec = {"id": pid, "name": r["name"], "phase": r.get("phase") or r["status"], "page": r["url"],
               "records": matched, "pageDocuments": [], "cnns": cnns, "streets": streets_named, "streetsFromText": []}
        if pid in by_id:
            record["projects"] = [rec if x["id"] == pid else x for x in record["projects"]]
        else:
            record["projects"].append(rec)
        by_id[pid] = rec
        pw_pages[pid] = {
            "source": "puc-page", "id": pid, "name": r["name"], "department": "SFPUC", "agency": "SFPUC",
            "phase": r.get("phase") or r["status"],
            "phaseBasis": "SFPUC's project page (Project Phase)" if r.get("phase") else "SFPUC's project page (no phase given)",
            "start": start, "end": end,
            "startBasis": ("SFPUC's project page (Construction Start “%s”, Construction End “%s”)"
                           % (r.get("constructionStart"), r.get("constructionEnd")) if start else None),
            "startText": r.get("constructionStart"),
            "streets": streets_named, "cnns": set(cnns),
            "placeNote": None, "extentBasis": r.get("cnnsBasis"),
            "scopeText": EMAIL.sub("[email removed]", r.get("description") or "")[:600] or None,
            "scopeNamesBike": bool(BIKE_WORDS.search("%s %s" % (r["name"], r.get("description") or ""))),
            "record": rec, "needsPlan": True,
            "links": [{"label": "SFPUC project page", "url": r["url"], "department": "SFPUC", "kind": "project"}],
            "geometryKind": "line",
        }

    # ---- Where SFMTA and Public Works both publish one project ----------------------
    # Each links the other's page and prints the other's status beside its own,
    # so a disagreement ("Completed" on one, "In progress" on the other) is on
    # the page with both values rather than settled silently (criterion B3).
    layer_phase = {p["id"]: p.get("phase") for p in record["projects"] if p["id"].startswith("sfmta:")}
    for s in sfmta.values():
        for r in dpw_records:
            if not same_name(s["name"], r["name"]):
                continue
            if r["url"] not in {l["url"] for l in s["links"]}:
                s["links"].append({"label": "Public Works project page (%s)" % r["name"], "url": r["url"],
                                   "department": "Public Works", "kind": "project"})
            s.setdefault("dateNotes", []).append(
                "Public Works' page gives its status as %s; SFMTA's project layer gives %s." % (
                    r.get("status") or "no status", layer_phase.get(s["id"]) or s["phase"] or "no phase"))
    sfmta_layer = [p for p in record["projects"] if p["id"].startswith("sfmta:")]
    for c in pw_pages.values():
        for p in sfmta_layer:
            if not same_name(c["name"], p["name"]):
                continue
            c["links"].append({"label": "SFMTA project page (%s)" % p["name"], "url": p["page"], "department": "SFMTA"})
            c.setdefault("dateNotes", []).append(
                "SFMTA's project layer gives its phase as %s; Public Works' page gives %s." % (
                    p.get("phase") or "no phase", c["phase"]))

    # ---- SFMTA rows with no phase or start from the layer or the page's fields --------
    # Each fallback is a record SFMTA publishes for the project, taken in this
    # order, and the row names which one it used (phaseBasis, startBasis).
    # The phase read here is shown on the row only (shownPhase): which rows
    # are listed, and whether a row past its end is still active, is decided
    # from the layer's and the page's phase fields as before, so a stale
    # timeline stage cannot keep a finished project on the list.
    for s in sfmta.values():
        node = s["id"].split(":", 1)[1]
        pg = spages.get(node) or {}
        text = " ".join((page_text.get(node) or pg.get("pageText") or "").split())
        if not s["phase"]:
            ps = [x for x in (page_dates(node, s["record"]["page"]) or {}).get("projectStatus") or [] if x]
            tl = pg.get("timeline") or []
            done = [i for i, t in enumerate(tl) if t.get("status") == "Completed"]
            nxt = next((t for t in tl[done[-1] + 1:] if t.get("status") != "Completed"), None) if done else None
            board = SLOW_STREET_BOARD.search(text)
            # The Project Status field is used only when it ticks one stage:
            # several ticked items ("Planning", "Implementation /
            # Construction", "Current" on Sutter Street Safety, whose Current
            # Phase field says Planning) do not say which is current, and
            # "Current" alone names no stage (Fable review, 2026-09-29).
            one = [x for x in ps if x != "Current"]
            if len(ps) == 1 and len(one) == 1:
                # (Powell Street Safety Project: "Implementation / Construction").
                s["shownPhase"] = (one[0], "the project page's Project Status field")
            elif nxt and TIMELINE_STAGE.search(nxt.get("what") or ""):
                # The first stage after the last one the page marks Completed
                # (Central Embarcadero: Planning and Preliminary Engineering
                # Completed, "2023-2025 Design" Pending). The page's own
                # timeline outranks the feed: Oak Street Quick-Build's feed
                # row says Design while its page marks the approvals and
                # pre-work Completed and Implementation next.
                s["shownPhase"] = (nxt["what"], "the project page's timeline (the stage after the last one marked "
                                   "Completed: “%s %s”)" % (nxt.get("when") or "", nxt["what"]))
            elif s.get("feedPhase"):
                s["shownPhase"] = (s["feedPhase"], "the coordination feed")
            elif board:
                # A Slow Street's page gives its SFMTA Board approval; SFMTA's
                # own word for that stage is Legislated (Minnesota Slow Street
                # on the project layer).
                s["shownPhase"] = ("Legislated", "the project page's text (“%s”)" % board.group(0))
        if not s["start"]:
            m = SLOW_STREET_START.search(text) or STRIPING_START.search(text)
            d = season_date(re.sub(r"^(?:early|mid|late)\s+", "", m.group(1), flags=re.I)) if m else None
            if d:
                s["start"], s["startText"] = d, m.group(0)
                s["startBasis"] = "the project page's text (“%s”)" % m.group(0)
                s["dateSources"] = [x for x in s.get("dateSources", []) if x["field"] != "construction start"] + [
                    {"field": "construction start", "date": d, "text": m.group(0), "from": s["startBasis"],
                     "url": s["record"]["page"]}]

    # Public Works and SFPUC rows: dates from their own project page's text.
    for c in list(jobs.values()) + list(pw_pages.values()):
        with_dept_page_dates(c)
    candidates = list(sfmta.values()) + list(jobs.values()) + list(pw_pages.values())

    # ---- Past their published end -----------------------------------------------
    # A row whose published end has passed stays on a list of current work
    # only while its own department still gives it an active status. It goes
    # when its own department's page says it is finished, or, with nothing
    # from its own department either way, when a partner's page says so or no
    # source read this run gives any active phase (criterion D1; review of
    # 2026-09-29: Third Street Bridge Rehabilitation, 2019, Public Works'
    # page "Completed"; Divisadero Intersection Improvements, 2020, no phase
    # anywhere). What stays carries a note naming the source that still calls
    # it active; whether such rows belong on the list is Bryan's call (thread
    # z65vm5s32cp3 on the audit criteria review).
    dept_status = {}
    for r in dpw_records:
        if r.get("status"):
            dept_status[r["url"]] = ("Public Works", r["status"])
    for u, p in dept_pages.items():
        if p.get("status") and p.get("kind", "project") == "project":
            dept_status.setdefault(u, (p["department"], p["status"]))
    for s in sfmta.values():
        pg = spages.get(s["id"].split(":", 1)[1]) or {}
        # The page's "Current Phase or Stage" field, else its "Project Status"
        # field's last ticked item (Powell Street Safety Project:
        # "Implementation / Construction"), read by scripts/sfmta-page-dates.py.
        ps = ((page_dates(s["id"].split(":", 1)[1], s["record"]["page"]) or {}).get("projectStatus") or [None])[-1]
        for u in {s["record"]["page"], pg.get("canonical")} - {None}:
            if pg.get("phase") or ps:
                dept_status[u] = ("SFMTA", pg.get("phase") or ps)
            else:
                dept_status.pop(u, None)
    possessive = {"Public Works": "Public Works'", "SFMTA": "SFMTA's", "SFPUC": "SFPUC's"}

    def finished_status(st):
        return bool(re.match(r"(?:completed?|finished|closed|substantially complete)\b", st or "", re.I)) \
            or st in FINISHED_PHASES

    def statuses(c):
        """[(department, source, status)] every source read this run gives the row, finished or not."""
        out = []
        if c["phase"]:
            out.append((c["department"], c.get("phaseBasis") or "the coordination feed", c["phase"]))
        if c.get("feedPhase"):
            out.append((c["department"], "the coordination feed", c["feedPhase"]))
        for l in c["links"]:
            d, st = dept_status.get(l["url"], (None, None))
            if st and l.get("kind") != "program":
                out.append((d, "%s page" % possessive.get(d, d + "'s"), st))
        if c["source"] == "sfmta" and page_done(spages.get(c["id"].split(":", 1)[1]) or {}):
            out.append(("SFMTA", "SFMTA's page", "Completed"))
        # One entry per department and status: the phase a row shows is often
        # the same page's status read a second way.
        seen = set()
        return [x for x in out if (x[0], x[2]) not in seen and not seen.add((x[0], x[2]))]

    # Bryan, 2026-11-09: the current projects are "based on today's date, with no finished projects showing". So a
    # published end is judged against the later of the data's read date and the day the step runs. Everything else
    # (phases, the early and later groups, every figure) stays on the read date, so a rerun with no new data writes
    # the same file unless an end has passed since; pipeline/site-refresh/refresh.py reruns this step on that day.
    listing_day = max(today, os.environ.get("SF_REFRESH_TODAY") or dt.date.today().isoformat())

    def end_rule(c):
        """(reason the row comes off, or None; the sources that keep a row past its end active) from its end."""
        # Bryan, 2026-09-29: "Don't include projects that were done before the
        # BRP came into effect." A published end before adoption drops the row
        # whatever phase a source still shows (Masonic's page says In progress
        # and gives construction ending Spring 2018).
        if c["end"] and c["end"] < PLAN_ADOPTED:
            return ("finished before the plan: its published end, %s, is before the Biking and Rolling Plan's "
                    "adoption on %s" % (c["end"], PLAN_ADOPTED)), None
        if not c["end"] or c["end"] >= listing_day:
            return None, None
        sts = statuses(c)
        own = [x for x in sts if x[0] == c["department"]]
        own_done = [x for x in own if finished_status(x[2])]
        own_active = [x for x in own if not finished_status(x[2])]
        other_done = [x for x in sts if x[0] != c["department"] and finished_status(x[2])]
        any_active = [x for x in sts if not finished_status(x[2])]
        why = None
        # SFMTA's page outranks its layer, whose phase goes stale: Frida Kahlo
        # Way's page ticks Completed while the layer still says Legislated.
        on_page = [x for x in own_done if x[1] == "SFMTA's page"]
        if own_done and (not own_active or on_page):
            why = "%s gives its status as %s" % ((on_page or own_done)[0][1], (on_page or own_done)[0][2])
        elif not own_active and other_done:
            why = "%s gives its status as %s, and %s gives none" % (other_done[0][1], other_done[0][2], c["department"])
        elif not any_active:
            why = "no source read gives it an active phase"
        if why:
            return "finished: its published end, %s, has passed and %s" % (c["end"], why), None
        # Bryan, 2026-11-09: the current projects are "based on today's date, with no finished projects showing".
        # A published end that has passed takes the row off even when a source still gives an active phase; the
        # retired page keeps the phase it gave, and a later end from any source brings the row back.
        active = own_active or any_active
        return ("finished: its published end, %s, has passed, though %s still gives its status as %s"
                % (c["end"], active[0][1], active[0][2])), None

    # A construction end a model read and a person has not confirmed (flagged
    # in out/*-page-dates/review.md: low confidence, a start and end that
    # cannot both hold, a phase it contradicts) never moves a row on or off
    # the list (lead, 2026-09-30, after Lyon Slow Street left on a mural's
    # completion read at confidence 0.45). Such a row keeps the outcome it had
    # the last time this step ran, recorded in HELD_LISTING, and the date
    # still shows under "Not yet checked". A row seen for the first time is
    # judged without the unchecked end. Once the date is confirmed, or a
    # source nobody need check gives the end, the row is judged on it.
    previous = json.load(open(HELD_LISTING)) if os.path.exists(HELD_LISTING) else None
    if previous is None:
        print("coordination-projects: %s is missing, so this run records each row's outcome as found, unchecked "
              "ends included" % os.path.relpath(HELD_LISTING, ROOT))
    listing = {}
    past_end_dropped = []
    kept = []
    held_rows = []
    for c in candidates:
        reason, active = end_rule(c)
        held_off = False
        if previous is not None and c.get("endUnchecked") and c["endUnchecked"] == c["end"]:
            before = previous.get(c["id"])
            if before is None:
                shown, c["end"] = c["end"], None
                before = {"listed": end_rule(c)[0] is None, "reason": end_rule(c)[0]}
                c["end"] = shown
            if (reason is None) != before["listed"]:
                held_rows.append("%s (%s)" % (c["name"], "kept on" if before["listed"] else "kept off"))
                note = ("The construction end shown, %s, was read by a model and a person has not confirmed it, so "
                        "it does not change whether the project is listed" % c["end"])
                if before["listed"]:
                    if c["start"] and c["end"] < (c["start"] + "-01-01")[:10]:
                        # A row kept on over an end that falls before its start
                        # (Beach Street Quick-Build: 2025-02-28 against a
                        # Spring 2026 start) shows no end rather than a span
                        # that runs backwards; the note keeps it for review.
                        note = ("A model read the construction end as %s, before the start of %s, and a person has not "
                                "confirmed it, so it is not shown and does not change whether the project is listed"
                                % (c["end"], c["start"]))
                        c["dateSources"] = [x for x in c.get("dateSources", []) if x["field"] != "construction end"]
                        c["uncheckedNotes"] = [n for n in c.get("uncheckedNotes", [])
                                               if not n.startswith("The construction end shown")]
                        c["end"] = None
                    c.setdefault("uncheckedNotes", []).append(
                        note + "; on it alone the project would come off the list (%s)." % reason)
                    reason = None
                else:
                    c.setdefault("uncheckedNotes", []).append(note + "; it stays off the list, as before.")
                    reason = before["reason"] or "off the list before its unchecked construction end was read"
                    held_off = True
        if reason is None and c["end"] and c["end"] < listing_day:
            # Kept on over an unchecked end that has passed: the row stays, as above, but shows no end, so no
            # listed project ends before the date its data was read (the coordination/no-finished check).
            c["dateSources"] = [x for x in c.get("dateSources", []) if x["field"] != "construction end"]
            c["uncheckedNotes"] = [n for n in c.get("uncheckedNotes", []) if not n.startswith("The construction end shown")]
            c.setdefault("uncheckedNotes", []).append(
                "A model read the construction end as %s, which has passed, and a person has not confirmed it, so it "
                "is not shown and does not change whether the project is listed" % c["end"])
            c["end"] = None
        listing[c["id"]] = {"listed": reason is None, "reason": reason}
        if held_off:
            reason +=" (held: the construction end now read, %s, is not yet confirmed)" % c["end"]
        if reason:
            past_end_dropped.append({"id": c["id"], "name": c["name"], "department": c["department"], "end": c["end"],
                                     "reason": reason})
            if c.get("decision"):
                c["decision"].update(listed=False, reason=reason)
            continue
        if active:
            c["activeSources"] = active
        kept.append(c)
    candidates = kept
    # A row no longer among the candidates keeps its entry, so one that
    # returns finds the outcome it left with.
    os.makedirs(os.path.dirname(HELD_LISTING), exist_ok=True)
    stable.write_json(HELD_LISTING, dict(sorted({**(previous or {}), **listing}.items())), indent=1)
    if held_rows:
        print("coordination-projects: %d rows kept their previous listing over an unchecked end: %s"
              % (len(held_rows), "; ".join(sorted(held_rows))))

    # ---- Held blocks, on today's centerline ----------------------------------
    # A project holds the CNNs its source gives it: SFMTA's shape walked over
    # the centerline, or the feed's rows. Some are blocks the centerline has
    # retired and split (300000 into 300001-300003), which then miss the plan
    # blocks that replaced them; those go to their successors. Most of the
    # rest are intersections: the feed keys work at a corner by the node's
    # CNN, which is not a block and is drawn as a point. A CNN the centerline
    # does not carry at all is counted and dropped.
    cl = shared_snapper().cl
    unknown_cnns = set()

    def held(cnns):
        out = set()
        for x in cnns:
            if x in cl.active or x in cl.node:
                out.add(x)
            elif x in cl.line:
                out |= set(cl.successors(x)) or {x}
            else:
                unknown_cnns.add(x)
        return out

    retired_before = sum(1 for c in candidates for x in c["cnns"] if x in cl.line and x not in cl.active)
    for c in candidates:
        c["cnns"] = held(c["cnns"])

    # ---- Selection ------------------------------------------------------------
    listed, not_street_work, programmes = [], [], []
    cutoff = evidence_cutoff(dt.date.fromisoformat(today))
    # A programme page is not a project. Bryan, 2026-09-29, on the Slow
    # Streets row: "'Slow Streets' is a top level directory page that links to
    # other post-pandemic slow streets projects. So it's not a project in
    # itself." The rule: a row whose name names no street, Muni line or
    # neighbourhood, and whose SFMTA page has no timeline and no phase and a
    # title that names no place either, is the programme's page, and the
    # projects it points to are listed on their own pages. On 2026-09-29 it
    # names two: the coordination feed's citywide "Slow Streets" job, matched
    # to sfmta.com/projects/post-pandemic-slow-streets, which it takes off the
    # list, and "Muni Gets You to Downtown", a service page already off as not
    # current. Every listed row on a page with no timeline and no phase names
    # its street.
    page_by_url = {}
    for pg in spages.values():
        for u in (pg.get("page"), pg.get("canonical")):
            if u:
                page_by_url[u.rstrip("/")] = pg

    def programme_page(c):
        if names_a_place(c["name"]):
            return None
        for l in c["links"]:
            pg = page_by_url.get((l.get("url") or "").rstrip("/"))
            if (l.get("kind") != "program" and pg and not pg.get("timeline") and not pg.get("phase")
                    and not names_a_place(pg.get("title") or "")):
                return l["url"]
        return None

    for c in candidates:
        on_plan = sorted(c["cnns"] & plan.keys())
        if not on_plan and not c["scopeNamesBike"]:
            continue
        prog = programme_page(c)
        if prog:
            reason = ("a programme, not a project: its name names no street, and its SFMTA page (%s) has no "
                      "timeline or phase of its own" % prog)
            programmes.append({"id": c["id"], "name": c["name"], "department": c["department"], "page": prog,
                               "reason": reason})
            if c.get("decision"):
                c["decision"].update(listed=False, reason=reason)
            continue
        if c.get("needsPlan") and not on_plan:
            continue
        if c.get("planOnly") and not on_plan:
            c["decision"].update(listed=False, reason="no bike or pedestrian scope, and its line runs on no plan block")
            continue
        # Transit, parking and wiring work is listed only while something
        # shows it is current: the coordination feed still carries its job,
        # or its page dates a milestone, notice or construction date in the
        # last two years or to come. The layer's phase alone is not that: it
        # still says Current or Implementation for work finished in 2018-2020
        # (Forest Hill Irrigation, Parking Management for Northern Potrero
        # Hill), and a service page with no dates at all ("Muni Gets You to
        # Downtown") is not a project.
        if c.get("planOnly") and not c.get("feedId") and (c.get("evidence") or "") < cutoff:
            c["decision"].update(listed=False, reason=(
                "not current: no bike or pedestrian scope, and its page dates nothing since %s (latest %s) and the "
                "coordination feed carries no job for it" % (cutoff, c.get("evidence") or "nothing dated")))
            continue
        # A mapped project whose phase neither the layer nor its page gives,
        # or one listed only because its page's words name walking or safety
        # work (no Bike, Walk, Vision Zero or Quick-Build tag, nothing in its
        # name), is listed only while its page dates work in the last year or
        # still to come, or the coordination feed carries its job. Such pages
        # go years without an edit: Active Beale Street's timeline ends in
        # 2020 and every stage is still Pending; the Muni Forward 5 Fulton
        # and 9 San Bruno Rapid Proposal pages date nothing after 2014 (read
        # 2026-09-29). A dated prose sentence counts ("will complete its
        # detailed design phase in Early 2027", 5th Street Improvement Project).
        dec = c.get("decision") or {}
        if c["source"] == "sfmta" and dec.get("onLayer") and not c.get("planOnly") and not c.get("feedId"):
            phaseless = not dec.get("layerPhase") and not dec.get("pagePhase")
            words_only = (dec.get("reason") or "").startswith("its page names")
            recent = evidence_cutoff(dt.date.fromisoformat(today), years=1)
            ended = c.get("ended")
            if ((phaseless and ended) or words_only) and (c.get("current") or "") < recent:
                dec.update(listed=False, reason=(
                    "not current: %s, and its page dates no work since %s (latest %s) and the coordination feed "
                    "carries no job for it" % (
                        "no phase on SFMTA's layer or its page and every milestone on its timeline dated %s or "
                        "earlier" % ended if phaseless and ended else
                        "listed only because its page's words name %s" % dec["reason"][len("its page names "):],
                        recent, c.get("current") or "nothing dated")))
                continue
        c["planCnns"] = on_plan
        c["kind"] = "SFMTA transit and parking" if c.get("planOnly") else work_kind(c["name"], c["department"])
        if c["kind"] is None:
            not_street_work.append({"name": c["name"], "department": c["department"],
                                    "planCnns": on_plan})
            continue
        listed.append(c)

    # ---- Every project's blocks, for co-location -----------------------------
    cnn_owner = collections.defaultdict(set)
    all_projects = {}
    for p in record["projects"]:
        all_projects[p["id"]] = p
        for c in held(p["cnns"]):
            cnn_owner[c].add(p["id"])
    listed_ids = {c["id"] for c in listed}
    feed_to_sfmta = {("dotmaps:%s" % c["feedId"]): c["id"] for c in listed if c.get("feedId")}

    # ---- The plan rating, per project (see "The plan rating" above) ---------------
    # Each block rated against the plan's type as tools/bike-network/bike-progress.py rates it.
    layer_src = {"label": "SFMTA's bikeway layer", "url": BIKEWAY_LAYER_URL}

    def plan_rating(c, plan_blocks):
        def out(state, value, label, sources, built=0.0, base=0.0, note=None):
            r = {"state": state, "value": value, "label": label,
                 "builtMiles": sig2(built / MILE), "baseMiles": sig2(base / MILE), "sources": sources}
            if note:
                r["note"] = note
            r["band"] = rating_band(r)
            return r

        if c["geometryKind"] == "none" or not plan_blocks:
            why = ("no map of the project is published" if c["geometryKind"] == "none"
                   else "none of the project's blocks is on the plan's network")
            return out("no-overlap", None, "No known overlap",
                       [{"label": "the Biking and Rolling Plan's network against the project's published blocks",
                         "url": PLAN_URL}], note="Nothing to rate: %s." % why)
        node = c["id"].split(":", 1)[1] if c["source"] == "sfmta" else None
        # What each plan block lacks today, on the one definition both sides
        # of the fraction use: its metres on direction rows that do not meet
        # the plan's type (status.json m - met_m). On a block the plan draws
        # as a shared, calmed or car-free street, or leaves Undecided, an
        # all-ages bikeway today counts as meeting it: a Slow Street is not a
        # bikeway-layer row, so status.json rates it none.
        def done_today(cnn):
            m = plan[cnn]["dir_m"]
            if plan[cnn]["facility"] in CALM_OK and cnn in all_ages:
                return m
            return min(m, met_m.get(cnn, 0))
        short = {cnn: plan[cnn]["dir_m"] - done_today(cnn) for cnn in plan_blocks}
        short = {cnn: v for cnn, v in short.items() if v > 0.5}
        mine = credited.get(node) or credited_by_name.get(slow_key(c["name"])) or set()
        mine = set(plan_blocks) & mine
        built = {}
        if mine:
            # Finished or under-way work the bikeway history credits: the base
            # is the plan blocks that lacked the plan's type the year before
            # the project's first credited year, and what it built is the
            # credited blocks among them, by the part that meets the type today.
            year = first_year.get(node) or first_year.get(slow_key(c["name"]))
            k = seg_years.index(year) - 1 if year in seg_years else -1
            before = {cnn: (seg_code.get(cnn) or "0" * len(seg_years))[max(k, 0)] if k >= 0 else "0"
                      for cnn in plan_blocks}
            lacked = {cnn for cnn in plan_blocks if not code_meets(plan[cnn]["facility"], before[cnn])}
            if not lacked:
                return out("already-built", None, "Already built", [layer_src],
                           note="Every plan block the project covers had the plan's bikeway type before %d, "
                                "the first year the bikeway history credits to it." % year)
            for cnn in sorted(mine & lacked):
                if done_today(cnn) > 0:
                    built[cnn] = done_today(cnn)
            short = {cnn: v for cnn, v in short.items() if cnn in lacked}
            base = sum(plan[cnn]["dir_m"] for cnn in lacked)
        else:
            # Work to come: the base is what the project's plan blocks lack
            # today. Nothing short reads "Already built", as agreed on the thread.
            if not short:
                return out("already-built", None, "Already built", [layer_src],
                           note="Every plan block the project covers already has the plan's bikeway type.")
            base = sum(short.values())
        # To come: the blocks and bikeway class SFMTA's own page names, up to
        # what each block lacks today.
        credit = dict(built)
        sources = [dict(layer_src, label="SFMTA's bikeway layer, street segments the bikeway history credits to this project")] if built else []
        named_on_plan = False
        for label, url, quote, cls, dirs, blocks in to_come.get(node, ()):
            sources.append({"label": label + (" (“%s”)" % quote if quote else ""), "url": url, "class": cls})
            for b in blocks:
                cnn = b["cnn"]
                if cnn not in plan:
                    continue
                named_on_plan = named_on_plan or cnn in plan_blocks
                if cnn not in short or not class_meets(plan[cnn]["facility"], cls):
                    continue
                n = D.count(cnn)[0]
                rows = b.get("rows") or dirs or n
                add = min(short[cnn], plan[cnn]["dir_m"] * min(1.0, rows / n))
                credit[cnn] = max(credit.get(cnn, 0), built.get(cnn, 0) + add)
        got = sum(credit.values())
        if sources:
            v = pct(got, base)
            note = None
            if to_come.get(node) and not built and not named_on_plan:
                note = ("SFMTA's page names its bikeway on blocks off the plan's network, and none of the "
                        "plan's blocks this project covers.")
            return out("percent", v, "Builds %d%%" % v if (v or not note) else "0%: its bikeway is off the plan",
                       sources, got, base, note=note)
        # A feed job's scope is its feed description; a page row's, its page.
        links = c.get("links") or [{}]
        own = (next((l for l in links if FEED in (l.get("url") or "")), links[0]) if c["source"] == "dotmaps"
               else links[0])
        where = ("the coordination feed's description of the job" if c["source"] == "dotmaps"
                 else "%s project page" % ("Public Works'" if c["department"] == "Public Works" else c["department"] + "'s"))
        if c["source"] == "sfmta":
            if c.get("pageText") and not PAGE_BIKE_WORDS.search("%s %s" % (c["name"], c["pageText"])):
                return out("scope-none", 0, "0% in published scope",
                           [{"label": "SFMTA's project page, which names no bike work", "url": c["record"]["page"]}],
                           0.0, base)
            return out("not-stated", None, "Not stated",
                       [{"label": "SFMTA's project page", "url": c["record"]["page"]}], 0.0, base,
                       note="SFMTA's page does not say which blocks get which bikeway%s." % (
                           ": %s" % uncounted[node] if node in uncounted else ""))
        if not c["scopeNamesBike"]:
            return out("scope-none", 0, "0% in published scope",
                       [{"label": "%s, which names no bike work" % where, "url": own.get("url")}], 0.0, base)
        return out("not-stated", None, "Not stated",
                   [{"label": where, "url": own.get("url")}],
                   0.0, base, note="The published scope names bike work but not which blocks or which bikeway type.")

    # ---- Per project ------------------------------------------------------------
    # A page's address comes from data/project-ids.json, which keeps every
    # address ever published (lib/project_ids.py says how an id that
    # moves keeps its page). A new project gets a short hash of its id.
    registry = project_ids.assign(listed)
    project_ids.save(registry)
    out = []

    for c in listed:
        plan_blocks = c["planCnns"]
        if c["source"] == "sfmta":
            # The centreline's own names for the blocks, not the parser's
            # reading of the page text, which turns "Biking on Page St" into
            # a street.
            named = collections.Counter()
            for cnn in plan_blocks:
                named[title(plan[cnn]["street"])] += plan[cnn]["dir_m"]
            if named:
                c["streets"] = [n for n, _ in named.most_common(6)]
        fac = collections.defaultdict(lambda: {"metres": 0.0, "streets": collections.Counter()})
        for cnn in plan_blocks:
            b = plan[cnn]
            fac[b["facility"]]["metres"] += b["dir_m"]
            fac[b["facility"]]["streets"][title(b["street"])] += b["dir_m"]
        facilities = sorted(
            ({"facility": k, "miles": sig2(v["metres"] / MILE),
              "streets": [s for s, _ in v["streets"].most_common(4)]} for k, v in fac.items()),
            key=lambda f: -f["miles"])
        plan_m = sum(v["metres"] for v in fac.values())

        # Plan blocks this project covers that lack an all-ages bikeway today.
        missing_blocks = [cnn for cnn in plan_blocks if cnn not in all_ages]

        # Which blocks count for reach: the ones where building what the plan
        # draws would add an all-ages bikeway, for every department alike. A
        # safety project's whole line is not a bikeway (Bryan, 2026-09-28, on
        # Mission / Geneva Safety Project's 8,729 residents: "How are you
        # calculating would reach?").
        reach_blocks = missing_blocks
        basis = "the project's plan blocks that lack an all-ages bikeway, as if it built the plan's bikeway on them"
        lines, missing = [], 0
        for cnn in reach_blocks:
            if cnn in plan:
                lines.append(plan[cnn]["pts"])
            elif cnn in seg_pts:
                lines.append(seg_pts[cnn])
            else:
                missing += 1
        reach = None
        if c["geometryKind"] == "line" and lines:
            # One walk from the project's lines, cut off past the longest
            # distance, read at each of the three (lib/walknet.py).
            W = walknet.WalkReach(lines, top_m)
            by = {t["id"]: {"residents": 0.0, "schools": [], "libraries": []} for t in thresholds}
            for lon, lat, pop, lit_now in cand_blocks:
                d, _ = W.distance(lon, lat)
                if d is None:
                    continue
                for t in thresholds:
                    if d <= t["metres"] and not lit_now[t["id"]]:
                        by[t["id"]]["residents"] += pop
            for kind, cands in (("schools", cand_schools), ("libraries", cand_libraries)):
                for x, lit_now in cands:
                    d, _ = W.distance(x["lon"], x["lat"])
                    if d is None:
                        continue
                    for t in thresholds:
                        if d <= t["metres"] and not lit_now[t["id"]]:
                            by[t["id"]][kind].append(x["name"])
            by = {tid: {"residents": int(round(v["residents"])), "schools": sorted(v["schools"]),
                        "libraries": sorted(v["libraries"])} for tid, v in by.items()}
            reach = dict(by[default_reach])
            reach.update({"byThreshold": {t["id"]: by[t["id"]] for t in thresholds if t["id"] != default_reach},
                          "blocksCounted": len(lines), "blocksWithoutGeometry": missing, "basis": basis})

        # Geometry for the small map: every block the project holds, from the
        # plan's trace, else the bikeway layer, else the centerline, and every
        # intersection as a point. Criterion E3: the map draws all of it.
        # Each drawn block and intersection also carries where it stands
        # against the plan, so the map can colour it (Bryan, 2026-09-28: "no
        # planned bikeway; planned bikeway, has it already; needs better
        # bikeway"): "none", not a plan block; "has", a plan block with an
        # all-ages bikeway today; "needs", a plan block without one.
        geometry, nodes, geometry_cats, node_cats = [], [], [], []
        plan_set, missing_set = set(plan_blocks), set(missing_blocks)
        block_cat = lambda cnn: "none" if cnn not in plan_set else "needs" if cnn in missing_set else "has"
        for cnn in sorted(c["cnns"]):
            if cnn in plan:
                geometry.append(plan[cnn]["pts"])
                geometry_cats.append(block_cat(cnn))
            elif cnn in seg_pts:
                geometry.append(seg_pts[cnn])
                geometry_cats.append(block_cat(cnn))
            elif cnn in cl.lonlat:
                geometry.append(thin(cl.lonlat[cnn]))
                geometry_cats.append(block_cat(cnn))
            elif cnn in cl.node:
                nodes.append([round(v, 5) for v in cl.node[cnn]])
                node_cats.append(block_cat(cnn))
        if len(geometry) + len(nodes) != len(c["cnns"]):
            raise SystemExit("E3: %s holds %d blocks and intersections but %d are drawn"
                             % (c["name"], len(c["cnns"]), len(geometry) + len(nodes)))

        # The gap: a Public Works or SFPUC job on plan blocks that still lack
        # an all-ages bikeway, with nothing published saying bike work is in
        # scope. A block that already has one is not missing anything.
        gap = None
        if c["department"] != "SFMTA" and missing_blocks:
            gap = not c["scopeNamesBike"]

        rating = plan_rating(c, plan_blocks)

        # Co-located projects: other work on the same blocks. A shared block is
        # a place, not the same project, and the page says so.
        shared = collections.Counter()
        for cnn in c["cnns"]:
            for oid in cnn_owner.get(cnn, ()):
                if oid == c["id"] or oid == ("dotmaps:%s" % c.get("feedId")) or oid in c.get("alsoIds", ()):
                    continue
                shared[feed_to_sfmta.get(oid, oid)] += 1
        related = []
        for oid, n in shared.most_common(8):
            if oid == c["id"]:
                continue
            o = all_projects.get(oid) or next((x["record"] for x in listed if x["id"] == oid), None)
            if o is None:
                continue
            row = {"id": oid, "name": o["name"], "sharedBlocks": n,
                   "phase": o.get("phase"),
                   "department": "SFMTA" if oid.startswith("sfmta") else "Public Works" if oid.startswith("dpw:") else
                   "SFPUC" if oid.startswith("sfpuc-page:") else (department(rows_by_job.get(oid.split(":")[1], [{}])[0].get("agency_name")) or "other"),
                   "url": o["page"]}
            lc = next((x for x in listed if x["id"] == oid), None)
            if lc:
                row["slug"] = lc["slug"]
            elif oid.startswith("sfmta"):
                # An SFMTA neighbour not listed here links to its page's own
                # address, not the /node/ one. A node the sitemap read never
                # reached (Parkmerced, node 762, answers 403) gets no link
                # rather than a dead one (Bryan, 2026-09-28: "Link didn't work?").
                pg = spages.get(oid.split(":", 1)[1]) or spages.get("slug:" + oid.split(":", 1)[1])
                row["url"] = (pg or {}).get("canonical") or (pg or {}).get("page")
            related.append(row)
        # A job both SFMTA's layer and Public Works' pages publish, shown here
        # as two neighbours, may carry two statuses that disagree (Upper Haight:
        # SFMTA Completed, Public Works In progress). Where they do, the Public
        # Works line prints both, since this list may be the only place on the
        # site that shows the job.
        for pw in related:
            if not pw["id"].startswith("dpw:"):
                continue
            twin = next((s for s in related if s["id"].startswith("sfmta:") and same_name(s["name"], pw["name"])), None)
            if twin is None:
                continue
            s_done = (twin.get("phase") or "") in ("Completed", "Project Evaluation")
            p_done = (pw.get("phase") or "").lower() == "completed"
            if s_done != p_done:
                pw["statusNote"] = ("Public Works' page gives its status as %s; SFMTA's project layer gives its "
                                    "phase as %s." % (pw.get("phase") or "no status", twin.get("phase") or "no phase"))

        # The dated record, one link per document.
        recs = list(c["record"]["records"]) + list(c.get("mergedRecords", []))
        seen = set()
        records = []
        for r in recs:
            key = (r.get("url"), r.get("date"), (r.get("title") or "")[:60])
            if key in seen or not r.get("url"):
                continue
            seen.add(key)
            t = EMAIL.sub("[email removed]", r.get("title") or "")
            records.append({
                "date": r.get("date") or "", "when": r.get("when"),
                "kind": r["kind"], "label": record_label(r),
                "cityBody": r["kind"] != "project-page",
                "title": t[:220] + ("…" if len(t) > 220 else ""),
                "url": r["url"], "decision": r.get("decision"),
                "relation": r.get("relation"), "grade": r.get("grade"),
            })
        records.sort(key=lambda r: r["date"], reverse=True)
        documents = [{"title": d["title"], "url": d["url"]} for d in (c["record"].get("pageDocuments") or [])]

        # A start the project page gives as "2025" or "2025-06" is read as the
        # first day of that period, so a project whose page says construction
        # began in 2025 reads as under way rather than as starting on a date.
        days = None
        if c["start"]:
            full = (c["start"] + "-01-01")[:10] if len(c["start"]) == 4 else (c["start"] + "-01")[:10]
            days = (dt.date.fromisoformat(full) - dt.date.fromisoformat(today)).days
        days_to_end = None
        if c["end"]:
            days_to_end = (dt.date.fromisoformat(c["end"]) - dt.date.fromisoformat(today)).days

        # Dates that disagree with each other or with the phase, printed on
        # the page with both values (criteria B3 and D1). Which one is right
        # is the department's to say; the page says they do not agree.
        notes = list(c.get("dateNotes", []))
        phase_from = c.get("phaseBasis") or ("the coordination feed" if c["phase"] else None)
        # The phase the row shows, which for an SFMTA row with no phase field
        # is the one read from its page or the feed (shownPhase).
        shown, shown_from = (c["phase"], phase_from) if c["phase"] else (c.get("shownPhase") or (None, None))
        if shown and re.search(r"planning|design", shown, re.I) and days is not None and days < 0:
            notes.append("The start date has passed (%s) while the phase is still %s, per %s." % (
                c["start"], shown, shown_from))
        if days_to_end is not None and days_to_end < 0 and c.get("activeSources"):
            # Only rows some source still calls active get here (see "Past
            # their published end" above); the note names that source.
            notes.append("The published end date, %s, has passed; %s." % (c["end"], "; ".join(
                "%s still gives it as %s" % (src, st) for _, src, st in sorted(set(c["activeSources"])))))
        if c.get("feedPhase") and c["phase"] and c["feedPhase"] != c["phase"]:
            notes.append("SFMTA gives the phase as %s; the coordination feed gives %s." % (c["phase"], c["feedPhase"]))
        elif c.get("feedPhase") and not c["phase"]:
            notes.append("SFMTA gives no phase; the coordination feed gives %s." % c["feedPhase"])

        # Meetings in the next MEETING_DAYS days that name the project or that
        # its page and the event's link, from every id the row holds.
        horizon = (dt.date.fromisoformat(today) + dt.timedelta(days=MEETING_DAYS)).isoformat()
        meetings, seen_m = [], set()
        for oid in [c["id"]] + (["dotmaps:%s" % c["feedId"]] if c.get("feedId") else []) + list(c.get("alsoIds") or []):
            for u in (by_id.get(oid) or {}).get("upcoming") or ():
                key = (u["meetingUrl"], str(u.get("item")))
                if key in seen_m or not (today < u["date"] <= horizon):
                    continue
                seen_m.add(key)
                meetings.append({k: u.get(k) for k in ("date", "time", "body", "meeting", "meetingUrl", "agenda",
                                                        "item", "title", "url", "route")})
        meetings.sort(key=lambda u: (u["date"], u["body"], str(u["item"])))
        out.append({
            "slug": c["slug"], "id": c["id"], "source": c["source"], "name": c["name"], "kind": c["kind"],
            "department": c["department"], "partners": sorted(set(c.get("partners", []))),
            "agency": c["agency"], "phase": c["phase"] or (c.get("shownPhase") or (None, None))[0],
            "phaseBasis": (c.get("phaseBasis") or ("the coordination feed" if c["phase"] else None)) if c["phase"]
            else (c.get("shownPhase") or (None, None))[1],
            "feedPhase": c.get("feedPhase"),
            "start": c["start"], "startText": c.get("startText"), "startBasis": c["startBasis"],
            "end": c["end"],
            "consultation": c.get("consultation"), "consultationStart": c.get("consultationStart"),
            # Where each date shown was read, with a link (tools/projects/sfmta-page-dates.py for Jev's).
            "dateSources": c["dateSources"] if "dateSources" in c else [
                {"field": f, "date": v, "text": c.get("startText") if f == "construction start" else None,
                 "from": "the coordination feed" if c["source"] == "dotmaps" else c["startBasis"],
                 "url": ROW_URL.format(c["id"].split(":", 1)[1]) if c["source"] == "dotmaps" else c["record"]["page"]}
                for f, v in (("construction start", c["start"]), ("construction end", c["end"])) if v],
            "dateNotes": notes,
            # Other notes on the row's dates, each group under the label the
            # page prints for it.
            "noteGroups": ([{"label": "Not yet checked", "notes": c["uncheckedNotes"]}]
                           if c.get("uncheckedNotes") else [])
            + [{"label": "Official source", "notes": ["No %s page for this job, and no closest official source found: %s." % (
                c["department"], no_source[i])]}
               for i in [c["id"]] + (c.get("alsoIds") or []) if i in no_source
               and not any(l.get("kind") == "program" or l.get("match") for l in c["links"])][:1],
            "alsoIds": c.get("alsoIds") or [],
            # Flags, not day counts: a count changes every day with no new
            # data, and every reader only asks which side of today a date is on.
            "underWay": days is not None and days < 0,
            "ended": days_to_end is not None and days_to_end < 0,
            "streets": c["streets"][:6],
            # Set when the department names no limits for the work, so the
            # map holds the whole corridor street (lib/pw_extent.py).
            "placeNote": c.get("placeNote"),
            "links": c["links"],
            "onPlan": bool(plan_blocks), "planBlocks": len(plan_blocks),
            "planCnns": sorted(plan_blocks),  # for tools/projects/department-overlap.py
            "planMiles": sig2(plan_m / MILE), "planFacilities": facilities,
            "alreadyAllAges": len(plan_blocks) - len(missing_blocks),
            "missingBlocks": len(missing_blocks),
            "missingMiles": sig2(sum(plan[cnn]["dir_m"] for cnn in missing_blocks) / MILE),
            "blocks": len(c["cnns"]),
            "intersections": len(nodes),
            "scopeNamesBike": c["scopeNamesBike"], "scopeText": c["scopeText"],
            # SFMTA rows only: bike work on the blocks it covers. SFMTA tags it
            # Bike, its name names bike or slow street work, or its feed row
            # (merged, or SFMTA's own job in the feed) names bike work; and it is drawn as a line, not a
            # study area, and is no study, area plan or development agreement.
            # The list takes pedestrian and safety projects too; the overlap
            # figures (tools/projects/department-overlap.py) count only these as
            # adding a bikeway.
            "bikeScope": (bool(c["bikeScope"] if "bikeScope" in c else (c["scopeNamesBike"] or bike_named(c["name"])))
                          and c["geometryKind"] == "line"
                          and not SFMTA_NOT_BUILT.search(c["name"])
                          and not (SFMTA_NOT_BIKEWAY.search(c["name"]) and not bike_named(c["name"])))
            if c["department"] == "SFMTA" else None,
            "gap": gap,
            # Share of the plan's missing bikeway on the project's blocks that
            # it builds or upgrades to the plan's type (plan_rating).
            "planRating": rating,
            "reach": reach, "geometryKind": c["geometryKind"],
            "related": related, "records": records, "documents": documents,
            # Early: planning or design by the department's phase, and its
            # published start not yet passed (Bryan's "construction not started").
            "meetings": meetings, "early": is_early(c["phase"]) and not (days is not None and days < 0)
            and not (days_to_end is not None and days_to_end < 0),
            "geometry": geometry, "geometryCats": geometry_cats,
            "nodes": nodes, "nodeCats": node_cats,
        })

    # ---- The streetscape half of a joint SFMTA project ----------------------------
    # The feed carries Public Works' share of a joint streetscape as its own
    # job with no bike words ("PW Folsom Streetscape Project", "Joint -
    # Streetscape Lead - Folsom St"), while SFMTA's page for the same project
    # names the bikeway. Such a row shows the joint project's rating, with a
    # note, rather than "0% in published scope". The link is read from the
    # data: both names say Streetscape and share a street name, and the SFMTA
    # project holds enough of the job's blocks (below).
    by_slug = {p["slug"]: p for p in out}
    generic = {"pw", "joint", "streetscape", "project", "projects", "lead", "st", "street", "improvement",
               "improvements", "the", "and", "phase"}

    def name_words(name):
        return {w for w in re.findall(r"[a-z]+", name.lower()) if w not in generic}
    for p in out:
        r = p["planRating"]
        if p["department"] == "SFMTA" or r["state"] != "scope-none" or not re.search(r"streetscape", p["name"], re.I):
            continue
        # A job the feed names as joint or as Public Works' share ("Joint -
        # Streetscape Lead", "PW Folsom Streetscape") needs a quarter of its
        # blocks under the SFMTA project; any other, half.
        joint_named = bool(re.match(r"\s*(joint|pw)\b", p["name"], re.I))
        for rel in p["related"]:
            s = by_slug.get(rel.get("slug"))
            if (s is None or s["department"] != "SFMTA" or s["planRating"]["state"] != "percent"
                    or not re.search(r"streetscape", s["name"], re.I)
                    or not (name_words(p["name"]) & name_words(s["name"]))
                    or rel["sharedBlocks"] * (4 if joint_named else 2) < p["blocks"]):
                continue
            p["planRating"] = dict(s["planRating"], sources=s["planRating"]["sources"] + r["sources"],
                note="Public Works' share of the joint %s; the rating is the joint project's, from SFMTA's "
                     "page and bikeway layer. This job's own feed description names no bike work." % s["name"],
                jointWith=s["slug"])
            break

    # ---- Order: soonest construction start first --------------------------------
    def sort_key(p):
        # Under way: the time left is the window in which drawings can still
        # change, so the least time left comes first. Not started: soonest
        # start first. No date: by phase.
        if p["underWay"]:
            return (0, p["end"] or "9999", p["name"])
        if p["start"]:
            return (1, p["start"].ljust(10, "0"), p["name"])
        return (2, phase_rank(p["phase"]), p["name"])
    out.sort(key=sort_key)

    # ---- Highlight: the ten highest by residents and by plan miles -------------
    by_res = sorted((p for p in out if p["reach"] and p["reach"]["residents"] > 0),
                    key=lambda p: -p["reach"]["residents"])[:TOP_N]
    by_miles = sorted((p for p in out if p["planMiles"] > 0), key=lambda p: -p["planMiles"])[:TOP_N]
    res_floor = by_res[-1]["reach"]["residents"] if by_res else None
    miles_floor = by_miles[-1]["planMiles"] if by_miles else None
    hi = {p["slug"] for p in by_res} | {p["slug"] for p in by_miles}
    for p in out:
        p["highlight"] = p["slug"] in hi
        p["highlightWhy"] = [w for w, ok in (
            ("residents", p["slug"] in {q["slug"] for q in by_res}),
            ("miles", p["slug"] in {q["slug"] for q in by_miles})) if ok]

    def dept_linked(p):
        return any(l.get("kind") != "program" and any(re.search(rx, l.get("url") or "") for rx in DEPT_SITE.values())
                   for l in p["links"])

    counts = {
        "listed": len(out),
        "byKind": dict(collections.Counter(p["kind"] for p in out)),
        "notStreetWork": len(not_street_work),
        "programmes": len(programmes),
        "byDepartment": dict(collections.Counter(p["department"] for p in out)),
        "fromFeed": sum(1 for p in out if p["source"] == "dotmaps"),
        "fromSfmtaLayer": sum(1 for p in out if p["source"] == "sfmta"),
        "fromDpwPages": sum(1 for p in out if p["source"] == "dpw-page"),
        "fromPucPages": sum(1 for p in out if p["source"] == "puc-page"),
        "mergedPairs": merged_pairs,
        "onPlan": sum(1 for p in out if p["onPlan"]),
        "scopeNamesBikeOffPlan": sum(1 for p in out if not p["onPlan"]),
        "gap": sum(1 for p in out if p["gap"]),
        "gapByDepartment": dict(collections.Counter(p["department"] for p in out if p["gap"])),
        # The plan rating's bands, as the list's filter offers them.
        "planRatingByBand": dict(sorted(collections.Counter(p["planRating"]["band"] for p in out).items())),
        "dpwPucOnPlan": sum(1 for p in out if p["department"] != "SFMTA" and p["onPlan"]),
        "withStart": sum(1 for p in out if p["start"]),
        "underWay": sum(1 for p in out if p["underWay"]),
        "withReach": sum(1 for p in out if p["reach"]),
        "areaProjects": sum(1 for p in out if p["geometryKind"] == "area"),
        "withRecord": sum(1 for p in out if p["records"]),
        "withMeeting": sum(1 for p in out if p["meetings"]),
        "early": sum(1 for p in out if p["early"]),
        "records": sum(len(p["records"]) for p in out),
        "sfmtaBikeNoPhase": no_phase,
        "retiredCnnsReplaced": retired_before,
        "cnnsNotOnCenterline": len(unknown_cnns),
        "sfmtaConsidered": len(decisions),
        "sfmtaConsideredOnLayer": sum(1 for d in decisions if d["onLayer"]),
        "sfmtaListed": sum(1 for d in decisions if d["listed"]),
        "sfmtaNoGeometry": sum(1 for p in out if p["department"] == "SFMTA" and not p["geometry"]),
        "sfmtaPhaseNotPublished": sum(1 for p in out if p["department"] == "SFMTA" and not p["phase"]),
        "sfmtaExcludedByReason": dict(collections.Counter(
            re.sub(r"\s*\(.*$|:.*$", "", d["reason"]) for d in decisions if not d["listed"])),
        # A row counts as linked when one of its links is a department's own
        # page for the job: a project or contract page on SFMTA's, Public
        # Works' or SFPUC's site, whichever department publishes it (a joint
        # job's page is often its partner's: Main Street Streetscape is a
        # Public Works row whose page is SFMTA's). Not the feed's DataSF row,
        # a programme page or the paving map. The audit's B1 counts the same
        # thing from the rendered links.
        "departmentPageLinks": {d: {"listed": sum(1 for p in out if p["department"] == d),
                                    "linked": sum(1 for p in out if p["department"] == d and dept_linked(p)),
                                    "closestOnly": sum(1 for p in out if p["department"] == d and not dept_linked(p)
                                                       and any(l.get("kind") == "program" for l in p["links"])),
                                    # The coordination feed's own jobs alone, for the About page's
                                    # issue that feed rows carry no page link.
                                    "feedListed": sum(1 for p in out if p["department"] == d and p["source"] == "dotmaps"),
                                    "feedLinked": sum(1 for p in out if p["department"] == d and p["source"] == "dotmaps"
                                                      and dept_linked(p))}
                                for d in ("SFMTA", "Public Works", "SFPUC")},
        "feedJobsConsidered": len(rows_by_job),
        "feedJobsFromDepartments": sum(1 for pid, rows in rows_by_job.items()
                                       if department(rows[0].get("agency_name"))),
    }

    # ---- Both statuses, for a project off the list that both publish -------------
    # SFMTA's layer phase and Public Works' page status for every SFMTA layer
    # project Public Works also publishes (same name, or its page among the
    # registry entry's pages), and the other way round for a Public Works page
    # row. retired() puts the sentence on the project's notice page.
    status_notes = {x["id"]: "SFMTA's page for it (%s) is a programme page that points to other projects' pages, "
                             "not a project of its own." % x["page"] for x in programmes}
    layer_by_id = {p["id"]: p for p in record["projects"] if p["id"].startswith("sfmta:")}
    pw_by_page = {project_ids.same_page(r["url"]): r for r in dpw_records}
    for slug, e in sorted(registry.items()):
        pid = e.get("id") or ""
        if e.get("listed") or not pid:
            continue
        if pid.startswith("sfmta:") and pid in layer_by_id:
            lp = layer_by_id[pid]
            pw = [pw_by_page[project_ids.same_page(u)] for u in e.get("pages") or []
                  if project_ids.same_page(u) in pw_by_page]
            pw += [r for r in dpw_records if same_name(lp["name"], r["name"]) and r not in pw]
            if pw:
                status_notes[pid] = "SFMTA's project layer gives its phase as %s; Public Works' page (%s) gives its " \
                                    "status as %s." % (layer_phase.get(pid) or "no phase", pw[0]["name"],
                                                       pw[0].get("status") or "no status")
        elif pid.startswith("dpw:"):
            r = next((r for r in dpw_records if r["id"] == pid), None)
            twin = next((p for p in layer_by_id.values() if r and same_name(r["name"], p["name"])), None)
            if r and twin:
                status_notes[pid] = "Public Works' page gives its status as %s; SFMTA's project layer (%s) gives " \
                                    "its phase as %s." % (r.get("status") or "no status", twin["name"],
                                                          layer_phase.get(twin["id"]) or "no phase")

    result = {
        "generated": today,
        # Every mile figure below (planMiles, missingMiles, planFacilities).
        "mileBasis": BASIS,
        # Addresses no longer listed: the site builds a redirect or a
        # "no longer in the city's records" page for each, so none breaks.
        "retired": retired(registry, status_notes),
        "today": today,
        "feed": {"dataset": FEED, "url": FEED_URL, "queried": feed.fetched_on.isoformat(),
                 "rows": len(feed.rows), "jobs": len(rows_by_job)},
        "sfmtaLayer": {"name": "SFMTA project layer, live from its ArcGIS service",
                       "url": "https://www.sfmta.com/projects", "generated": record["generated"]},
        "records": {"generated": record["generated"]},
        "centerline": {"dataset": "3psu-pn9h", "url": "https://data.sfgov.org/d/3psu-pn9h", "queried": cl.queried,
                       "note": "draws held blocks the plan and the bikeway layer do not, and intersections as points"},
        "plan": {"name": "SFMTA Biking and Rolling Plan (March 2025), North Star network as traced",
                 "url": "https://www.sfmta.com/projects/biking-and-rolling-plan", "blocks": len(plan)},
        "reach": {
            "miles": REACH_MILES,
            "method": ("A census block, a school (public or private K-12) or a library branch is within reach when "
                       "the walk along OpenStreetMap's walkable streets, paths and stairways to one of the project's "
                       "lines is at most the distance, measured from a block's street frontage and from a school's or "
                       "branch's own point, as on the overview (lib/walknet.py). Only points not already within "
                       "that walk of today's all-ages network are counted."),
            "thresholds": [{"id": t["id"], "metres": t["metres"], "label": t["label"], "short": t["short"]}
                           for t in thresholds],
            "default": default_reach,
            "unreached": unreached_by[default_reach],
            "unreachedByThreshold": {k: v for k, v in unreached_by.items() if k != default_reach},
            "walkNetwork": {"source": "OpenStreetMap via Overpass (tools/travel/osm-walk-network.py)",
                            "fetchedOn": walknet.graph().osm_base},
            "sources": reach_src["sources"],
            "networkQueried": reach_src["sources"].get("blocks", {}).get("queried"),
        },
        "ranking": {
            "rule": ("Work already under way comes first, soonest to finish at the top, "
                     "because bike work has to go in before the street is restriped. "
                     "Then the rest by construction start, soonest first. A project with no published "
                     "start date follows, ordered by phase: construction, legislated, design, planning."),
            "highlight": ("Outlined rows are the %d projects that would bring the most residents within a quarter-mile "
                          "walk of the all-ages network, and the %d with the most plan-network miles on their blocks." % (TOP_N, TOP_N)),
            "topN": TOP_N, "residentsFloor": res_floor, "milesFloor": miles_floor,
        },
        "sfmtaRule": SFMTA_RULE,
        "upcoming": upcoming_summary(today),
        "counts": counts,
        "projects": out,
        "notStreetWork": sorted(not_street_work, key=lambda x: x["name"]),
        "programmes": sorted(programmes, key=lambda x: x["id"]),
        # Unfinished feed jobs by agencies other than the three departments
        # the list covers (PG&E, the Port, Transbay, ...) whose blocks touch
        # the plan: out of scope, and named on About the data as such.
        "otherAgencyOnPlan": other_agency_on_plan(rows_by_job, by_id, plan, today),
        # Rows taken off because their published end passed and their
        # department's page, or every source, says they are not active.
        "pastEndDropped": sorted(past_end_dropped, key=lambda x: (x["name"], x["id"])),
    }
    stable.write_json(OUT, result, end="", indent=0, ensure_ascii=False)
    os.makedirs(os.path.dirname(DECISIONS), exist_ok=True)
    stable.write_json(DECISIONS, {"generated": today, "rule": SFMTA_RULE,
                                  "decisions": sorted(decisions, key=lambda d: d["name"])},
                      end="", indent=1, ensure_ascii=False)
    print("%d projects listed (%d from the feed, %d from SFMTA's layer and pages, %d from Public Works' pages, %d from SFPUC's, %d merged pairs); %d Public Works/SFPUC "
          "jobs on the plan with no bike scope published; reach computed for %d; feed queried %s -> %s"
          % (len(out), counts["fromFeed"], counts["fromSfmtaLayer"], counts["fromDpwPages"], counts["fromPucPages"], merged_pairs, counts["gap"],
             counts["withReach"], feed.fetched_on, os.path.relpath(OUT, ROOT)))


if __name__ == "__main__":
    main()
