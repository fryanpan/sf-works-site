#!/usr/bin/env python3
"""Give every project one record, with the city's own documents linked in.

Bryan, 2026-09-21: "Ultimately architecture wise we want to have a concept of a
project and that can be created from meeting notes or from maps or datasf
datasets, and then all related information linked in." And on trusting it:
"We'll need to be careful about the link."

Two kinds of project, because an advocate meets both:

  tools/projects/sfmta-projects.py    SFMTA's own projects — the bikeways themselves
  tools/projects/street-work-list.py  Public Works coordinated jobs — the repaving
                               and utility work that opens a street

And three records the city writes about a street, linked into them:

  tools/meetings/sfmta-hearings.py       engineering hearing orders and their decisions
  tools/meetings/sfmta-board-records.py  SFMTA Board items and their votes
  tools/meetings/bos-street-records.py   Board of Supervisors files naming a street

Care is the whole design. A street name on its own is not evidence: one board
item about the Bayview Community Pathway names Third Street, and 22 projects
mention Third Street somewhere on their page. So each link is graded and only
exact, strong and probable are ever counted.

What a link MEANS also differs by which kind of project it lands on. An order
authorises an SFMTA project; beside a paving job the same order says only that
the city has legislated a bikeway on a street that job will dig up. Each link
carries which of the two it is.

    tools/projects/project-record.py
    tools/projects/project-record.py --min-district-agreement 0   # ignore districts
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import datetime as dt
import json
import os
import re
import sys

ROOT = paths.ROOT
PROJECTS = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
HEARINGS = os.path.join(ROOT, "out", "sfmta-hearings", "hearings.json")
BOARD = os.path.join(ROOT, "out", "sfmta-board", "meetings.json")
NORTH_STAR = os.path.join(ROOT, "out", "north-star", "segments.geojson")
DOTMAPS = os.path.join(ROOT, "out", "street-work", "street-work.csv")
# Public Works publishes NO page for a coordinated project. DataSF says the
# rows are "extracted from the DotMaps system via API" and DotMaps itself is
# internal — dotmaps.sfgov.org does not resolve (checked 2026-09-21). The
# dataset row is the whole published record, so that is what a reader gets, and
# the absence is the finding rather than something to paper over with a link.
DOTMAPS_PAGE = ("https://data.sf.gov/resource/btxj-k9uh.json?dotmapsid={}")
CLASSES = os.path.join(ROOT, "out", "north-star", "class-definitions.json")
SUPERVISORS = os.path.join(ROOT, "out", "bos-records", "street-items.json")
# SFPUC Commission items naming a city street, from scripts/sfpuc-commission.py.
# A water-main or sewer contract is the decision that opens a street; the
# transport bodies' records never carry it.
SFPUC = os.path.join(ROOT, "out", "sfpuc-commission", "items.json")

# Street names come out of every source the same way, so the parser is shared:
# scripts/streetnames.py. A second implementation would be a second set of
# misses, and nothing would say the two disagreed.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import seasons, stable  # noqa: E402
from streetnames import streets, streets_in_order  # noqa: E402
from streetindex import BlockIndex, canon  # noqa: E402
from sfdata import fetch  # noqa: E402

PROJECT_BLOCKS = os.path.join(ROOT, "out", "project-record", "project-blocks.json")
PROJECT_PAGES = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")
DPW_PAGES = os.path.join(ROOT, "data", "extract", "dpw-projects", "projects.json")  # tools/projects/dpw-projects.py
# SFPUC's own project list, written by tools/projects/department-project-pages.py,
# which runs after this step and reads its output; this step reads the list
# that step last wrote (tracked), so a page new to SFPUC's site meets the
# mirrors on the run after the one that first reads it.
PUC_PAGES = os.path.join(ROOT, "data", "extract", "sfpuc-projects", "projects.json")
FEED = "btxj-k9uh"
BLOCKS = None  # the BlockIndex, built once in main()


def districts(value):
    """Supervisor districts as a set of ints, from either source's spelling."""
    if not value:
        return set()
    return {int(d) for d in re.findall(r"\d{1,2}", str(value))
            if 1 <= int(d) <= 11}


def load_projects():
    d = json.load(open(PROJECTS, encoding="utf-8"))
    # tools/projects/project-blocks.py: the blocks under each project's ArcGIS shape.
    pblocks = (json.load(open(PROJECT_BLOCKS))["projects"]
               if os.path.exists(PROJECT_BLOCKS) else {})
    out = []
    for p in d["projects"]:
        text = " ".join(x for x in (p.get("name"), p.get("cipTitle"),
                                    p.get("teaser"), p.get("pageText")) if x)
        out.append({
            "id": f"sfmta:{p['node']}",
            "name": p.get("name"),
            "phase": p.get("phase"),
            "bike": bool(p.get("bike")),
            "districts": sorted(districts(p.get("districts"))),
            "page": p.get("page"),
            "lastEdited": p.get("lastEdited"),
            "inDataSfMirror": p.get("inDataSfMirror"),
            "source": "SFMTA, live from its ArcGIS project layer",
            "onPlan": None,
            "plannedFacility": None,
            "scope": None,
            # A project's streets come from its NAME first: the page text names
            # every cross street it lists, and those are landmarks rather than
            # the corridor the project is on.
            "streets": sorted(streets(p.get("name") or "")),
            "streetsFromText": sorted(streets(text)),
            # Bike projects only: project-blocks.py now places every layer
            # project, for the Current Projects list, but the record join
            # grades a hearing on a shared block as ambiguous, so adding the
            # transit and parking projects would move grades that nothing
            # here has re-checked. tools/projects/coordination-projects.py reads the
            # other projects' blocks from project-blocks.json itself.
            "cnns": sorted(pblocks.get(str(p.get("node")), {}).get("cnns", ())) if p.get("bike") else [],
            "records": [],
        })
    return out, d.get("mirrorAsOf")


def load_page_projects(layer):
    """SFMTA project pages that SFMTA does not map, as projects in their own right.

    tools/projects/coordination-projects.py lists some of these (a page with no
    shape on the layer, such as a signal contract), and without a place here
    they never met the body mirrors: their only records were the page's own.
    They carry no blocks, so they link by name and contract number only.
    """
    if not os.path.exists(PROJECT_PAGES):
        return []
    have = {norm_name(p["name"]) for p in layer}
    out = []
    for key, pg in sorted(json.load(open(PROJECT_PAGES, encoding="utf-8"))["pages"].items()):
        if pg.get("on_layer") or not key.startswith("slug:"):
            continue
        name = pg.get("title") or pg.get("name")
        if not name or norm_name(name) in have:
            continue
        out.append({
            "id": "sfmta-page:" + key.split(":", 1)[1], "name": name, "phase": pg.get("phase"),
            "bike": False, "districts": [], "page": pg.get("page"), "lastEdited": None,
            "inDataSfMirror": False, "source": "SFMTA, a project page not on its map",
            "onPlan": None, "plannedFacility": None, "scope": None,
            "streets": sorted(streets(name)), "streetsFromText": [], "cnns": [], "records": [],
        })
    return out


def load_dpw_pages(have):
    """Public Works project pages in progress, as projects matched by name and contract number only.

    tools/projects/coordination-projects.py lists a Public Works page no feed job
    carries (Page Street Neighborway, Islais Creek Bridge Replacement) as a
    row of its own. Without a place here those rows never met the body
    mirrors and carried no record at all, though the SFCTA approved $1 million
    for the Page Street Neighborway Project by name on 2020-12-08. They carry
    no blocks here, so a street alone never reaches them. A page whose name is
    already a project here is left to that project.
    """
    if not os.path.exists(DPW_PAGES):
        return []
    names = {norm_name(p["name"]) for p in have}
    out = []
    for r in sorted(json.load(open(DPW_PAGES, encoding="utf-8"))["records"], key=lambda r: r["id"]):
        if (r.get("status") or "").lower() not in ("in progress", "active", "under construction", "construction"):
            continue
        if not r.get("name") or norm_name(r["name"]) in names:
            continue
        out.append({
            "id": r["id"], "name": r["name"], "phase": r.get("status"), "bike": False,
            "districts": [], "page": r.get("url"), "lastEdited": None, "inDataSfMirror": False,
            "source": "Public Works project page", "onPlan": None, "plannedFacility": None,
            "scope": None, "scopeText": None,
            "streets": sorted(streets(r["name"])), "streetsFromText": [], "cnns": [], "records": [],
        })
    return out


def load_puc_pages(have):
    """SFPUC project pages no feed job carries, as projects matched by name only.

    tools/projects/coordination-projects.py lists such a page as a row of its own
    (Channel Force Main Intertie, in construction with no coordination-feed
    job); without a place here the SFPUC Commission's items that name it
    (contract WW-723R, 2025-02-25 and 2026-04-28) never reached it. A page the
    feed carries (feedJobs) is that job's, and a page whose name is already a
    project here is left to that project.
    """
    if not os.path.exists(PUC_PAGES):
        return []
    names = {norm_name(p["name"]) for p in have}
    out = []
    for r in sorted(json.load(open(PUC_PAGES, encoding="utf-8"))["records"], key=lambda r: r["id"]):
        if (r.get("status") or "").lower() != "in progress" or r.get("feedJobs"):
            continue
        if not r.get("name") or norm_name(r["name"]) in names:
            continue
        out.append({
            "id": r["id"], "name": r["name"], "phase": r.get("phase") or r.get("status"), "bike": False,
            "districts": [], "page": r.get("url"), "lastEdited": None, "inDataSfMirror": False,
            "source": "SFPUC project page", "onPlan": None, "plannedFacility": None,
            "scope": None, "scopeText": None,
            "streets": sorted(streets(r["name"])), "streetsFromText": [], "cnns": [], "records": [],
        })
    return out


def load_dotmaps():
    """The Public Works coordinated projects the streets page is built from.

    A second source of projects, and the one an advocate meets first: these are
    the repaving and sewer jobs that will open a street the plan wants a bikeway
    on. They carry no document of their own beyond the DotMaps entry, which is
    exactly the gap this join is meant to close.
    """
    if not os.path.exists(DOTMAPS):
        return []
    out = []
    for r in csv.DictReader(open(DOTMAPS, encoding="utf-8")):
        named = [x.strip() for x in (r.get("Streets") or "").split(",")
                 if x.strip()]
        out.append({
            "id": f"dotmaps:{r['DotMaps id']}",
            "name": r.get("Project"),
            "phase": r.get("Phase"),
            "bike": r.get("Ask about this one", "").strip().lower()
                    in ("yes", "true", "1"),
            "districts": [],
            "page": DOTMAPS_PAGE.format(r["DotMaps id"]),
            "lastEdited": r.get("Start"),
            "inDataSfMirror": True,
            "source": "Public Works, via DotMaps",
            "onPlan": (r.get("On the 2025 North Star network") or "")
                      .startswith("YES"),
            "plannedFacility": r.get("Planned facility") or None,
            "scope": r.get("What the record says about scope"),
            "streets": sorted(streets(r.get("Project") or "")),
            "streetsFromText": sorted({x for st in named
                                       for x in streets_(st)}),
            "records": [],
        })
    return out


def streets_(one):
    """Normalise one already-isolated street name, e.g. "Burnett Ave"."""
    return streets(one) or ({one.strip().lower()} if one.strip() else set())


# Where a record says it applies, as city blocks. Bryan, 2026-09-22, after the
# street-name join offered him pages that had nothing to do with each other:
# "make sure the matches are valid in time and space." A hearing item writes its
# place in one of two shapes, and both resolve through the centreline:
#
#   an extent   "Valencia Street, from Cesar Chavez Street to Duboce Avenue"
#               → the blocks of Valencia between those two cross streets
#   a point     "Post Street, north side, from Baker Street to 88 feet easterly"
#               "Brannan Street, south side, 262 feet east of 6th Street"
#               → the blocks of Post that meet Baker; of Brannan that meet 6th
#
# A record whose place cannot be resolved gets NO blocks, and the grader then
# falls back to the street-name rules — it does not get the whole street, which
# is the failure this exists to stop.
_FROM_TO = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:\s*\(|,|;|$)", re.I)
_AT = re.compile(r"\b(?:of|at|and|near)\s+([A-Z][\w.' -]+?(?:Street|St|Avenue|Ave|Boulevard|Blvd|Way|Drive|Dr|Road|Rd|Place|Pl|Terrace|Alley|Lane|Ln|Court|Ct|Highway|Hwy))\b")


def record_blocks(head, corridor):
    """CNNs a record's own words place it on, or an empty set."""
    if not corridor or BLOCKS is None:
        return set()
    m = _FROM_TO.search(head or "")
    if m:
        a = streets_in_order(m.group(1))
        b = streets_in_order(m.group(2))
        if a and b:
            ext = BLOCKS.extent(corridor, a[0], b[0])
            if ext:
                return ext
        # "from Baker Street to 88 feet easterly": one real cross street.
        for side in (a, b):
            if side:
                blk = _meeting(corridor, side[0])
                if blk:
                    return blk
    for m in _AT.finditer(head or ""):
        cross = streets_in_order(m.group(1))
        if cross and canon(cross[0]) != canon(corridor):
            blk = _meeting(corridor, cross[0])
            if blk:
                return blk
    return set()


def _meeting(corridor, cross):
    """The blocks of `corridor` that start or end at `cross`."""
    k = canon(cross)
    return {b["cnn"] for b in BLOCKS._by_street.get(canon(corridor), ())
            if b["from"] == k or b["to"] == k}


def _feed_cnns(value):
    """The feed puts a Python list literal in `cnn` when a row spans blocks."""
    raw = str(value or "").strip()
    if raw.startswith("["):
        try:
            return {str(int(float(x))) for x in json.loads(raw.replace("'", '"'))}
        except (ValueError, TypeError):
            return set()
    try:
        return {str(int(float(raw)))} if raw else set()
    except ValueError:
        return set()


_PART_TAIL = re.compile(r"\s*(?:\(Supervisor District|\bProposal\b|\bPublic Comments?\b|\bDecision\b).*", re.S)
_OTHER_PARTS = re.compile(r"\b(?:the )?(?:remaining|all other|other) items?\b", re.I)


def hearing_parts(no, text, decision):
    """An engineering-hearing item's lettered parts, each with its own outcome, or None.

    Item 10 of the 2020-12-04 hearing is 10(a) a Class IV bikeway on Evans
    Avenue, 10(b) raised crosswalks on Hunters Point Boulevard, 10(c) and
    10(d) more on Evans, and its one decision line reads "Items 10(b)
    withdrawn due to San Francisco Fire Department concerns. The remaining
    items to be approved ...". Shown whole, a project on Evans read as held
    up by a withdrawal on another street (Bryan, 2026-09-28: "this decision
    was relevant, but the subtitle is irrelevant"). So a decision that names
    a part is split: a sentence naming parts goes to those parts, one about
    "the remaining items" to the parts no sentence names, and any other to
    every part. None when the item has no lettered parts or its decision
    names none, since then one outcome covers the whole item."""
    if not text or not decision or not no:
        return None
    no = re.escape(str(no))
    marks, seen = [], set()
    for m in re.finditer(r"^[ \t]*%s\s*\(([a-z])\)\s*\.\s*" % no, text, re.M):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            marks.append(m)
    if len(marks) < 2:
        return None
    letters = [m.group(1) for m in marks]
    sentences = [s for s in re.split(r"(?<=\.)\s+", decision.strip()) if s]
    named = {}
    for s in sentences:
        hit = set(re.findall(r"%s\s*\(([a-z])\)" % no, s))
        # "Items 10(a) through 10(f)": every letter in the range.
        for a, b in re.findall(r"%s\s*\(([a-z])\)\s*(?:through|to|-|\u2013)\s*(?:%s\s*)?\(([a-z])\)" % (no, no), s):
            hit |= {chr(c) for c in range(ord(a), ord(b) + 1)}
        named[s] = hit & set(letters)
    if not any(named.values()):
        return None
    said = set().union(*named.values())
    out = []
    for i, m in enumerate(marks):
        body = text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        body = re.sub(r"\s+", " ", _PART_TAIL.sub("", body)).strip()
        dec = []
        for s in sentences:
            if named[s]:
                if m.group(1) in named[s]:
                    dec.append(s)
            elif _OTHER_PARTS.search(s):
                if m.group(1) not in said:
                    t = _OTHER_PARTS.sub("", s, count=1).strip()
                    t = re.sub(r"^(?:are |is )?to be\b", "To be", t)
                    dec.append(t[:1].upper() + t[1:])
            else:
                dec.append(s)
        out.append({"label": "%s(%s)" % (no.replace("\\", ""), m.group(1)), "head": body,
                    "decision": dec, "streets": streets_in_order(body)})
    return out


def own_parts(project, record):
    """The record as it concerns this project: only the parts naming its streets.

    A record without parts, or whose parts all or none name the project's
    streets, is returned unchanged."""
    parts = record.get("parts")
    names = set(project.get("streets") or ()) | set(project.get("streetsFromText") or ())
    if not parts or not names:
        return record
    mine = [x for x in parts if names & set(x["streets"])]
    if not mine or len(mine) == len(parts):
        return record
    decisions = []
    for x in mine:
        decisions += [d for d in x["decision"] if d not in decisions]
    title = " ".join(x["head"] if len(mine) == 1 else "%s. %s" % (x["label"], x["head"]) for x in mine)
    return {**record, "title": title[:600], "decision": " ".join(decisions) or None,
            "parts": ["%s of item %s" % (", ".join(x["label"] for x in mine), record["item"])]}


def load_records(meeting_days=frozenset()):
    """Every record a city body wrote, from the keyword extracts and the full meeting mirrors.

    meeting_days: {(kind, date)} of the hearings and Board meetings some
    project's own page says it went to (page_meetings). The mirror's items of
    those meetings are read for their streets and blocks too, so the item on
    the project's street can be found (link, the page-meeting route)."""
    out = []
    h = json.load(open(HEARINGS, encoding="utf-8"))
    for m in h["matches"]:
        out.append({
            "kind": "hearing",
            "date": m["date"],
            "item": m["no"],
            "title": m["head"],
            "districts": sorted(districts(m.get("district"))),
            "decision": m.get("decision"),
            "approver": m.get("approver"),
            "url": m.get("results") or m.get("page"),
            "streets": streets_in_order(m["head"]),
            "blob": flatten(m["head"] + " " + (m.get("text") or "")),
            "parts": hearing_parts(m["no"], m.get("text"), m.get("decision")),
            # The item's own text, for the lettered-part rule of the page-meeting
            # route (page_meeting_match); kept only for a meeting some project's
            # page lists, and never written out.
            **({"partsText": m.get("text")} if ("hearing", m["date"]) in meeting_days else {}),
        })
        out[-1]["cnns"] = sorted(record_blocks(m["head"], (out[-1]["streets"] or [None])[0]))
    b = json.load(open(BOARD, encoding="utf-8"))
    for m in b["matches"]:
        # A procedural point is nobody's decision. Granicus folded the
        # 2019-05-21 consent calendar into item 9, "Public Comment", so the
        # keyword extract read the 6th Street resolution as public comment;
        # the mirror now carries it as item 10.3 from the minutes.
        if (PROCEDURE.match(m.get("parent") or "") or PROCEDURE.match(m.get("title") or "")
                or CALENDAR_HEAD.match(m.get("title") or "")):
            continue
        title = " ".join(x for x in (m.get("parent"), m.get("title")) if x)
        out.append({
            "kind": "board",
            "date": m["date"],
            "item": m.get("no"),
            "title": title,
            "districts": [],
            "decision": m.get("disposition"),
            "approver": "SFMTA Board of Directors",
            "url": m.get("minutes") or m.get("agenda"),
            "streets": streets_in_order(title),
            "blob": flatten(title),
        })
        out[-1]["cnns"] = sorted(record_blocks(title, (out[-1]["streets"] or [None])[0]))
    if os.path.exists(SUPERVISORS):
        s = json.load(open(SUPERVISORS, encoding="utf-8"))
        for m in s["matches"]:
            out.append({
                "kind": "supervisors",
                "date": m.get("date") or "",
                "item": m.get("item"),
                "title": m["title"],
                "districts": [],
                "decision": m.get("decision") or m.get("status"),
                "approver": "Board of Supervisors",
                "url": m["url"],
                "streets": m["streets"],
                "cnns": [],
                # The title only. A Board file's BODY is full of addresses from
                # unrelated attachments, and a blob built from it would name a
                # street on every project in the city.
                "blob": flatten(m["title"]),
            })
    if os.path.exists(SFPUC):
        u = json.load(open(SFPUC, encoding="utf-8"))
        for m in u["streetItems"]:
            out.append({
                "kind": "sfpuc",
                "date": m["date"],
                "item": m["item"],
                "title": m["title"],
                "districts": [],
                "decision": m.get("decision"),
                "approver": "SFPUC Commission",
                "url": m["url"],
                "streets": m["streets"],
                # The blocks of every street the item names. A contract title
                # lists the streets a job runs on and, usually, the cross
                # streets bounding it; the extent read is not attempted here.
                "cnns": m.get("cnns", []),
                # The extract's title runs on into the minutes' discussion;
                # only the formal text is what the Commission decided.
                "blob": flatten(formal_text(m["title"])), "nblob": norm_name(formal_text(m["title"])),
                # A contract award here is an award, as it is when read from
                # the mirror (load_mirror_records), and links by street, scope
                # and date together (award_grade). Without the flag the
                # 2025-05-13 award of WW-757R ("Laguna, Howard, and Mission
                # Creek Combined Sewer Discharge Improvements") read as other
                # work on the Laguna and Howard CSD job's streets (audit C4).
                **({"award": True} if AWARD.search(formal_text(m["title"]) or "") else {}),
            })
    return out + load_delegated() + load_mirror_records(out, meeting_days)


# The Public Works Commission's delegated contract reports, read by
# tools/meetings/fetch-public-works-commission.py: contracts the Director approved
# under the Commission's Contract Approval Delegation Policy without a
# Commission vote, one row per contract. The reports read so far (2024-12 to
# 2026-09) list only changes to contracts already awarded (time extensions,
# rate escalations, added subcontractors), and each is labelled for what it
# is, never as a Commission vote. The project list carries no Public Works
# ten-digit contract ID, so a row links by the project's name only (EXACT),
# or, for an award, by streets, scope and dates as a Commission award does.
DELEGATED = os.path.join(ROOT, "data", "public-works-commission", "delegated.json")
DELEGATED_APPROVER = "Director of Public Works, under the Public Works Commission's delegation"


def load_delegated():
    if not os.path.exists(DELEGATED):
        return []
    out = []
    reports = sorted(json.load(open(DELEGATED, encoding="utf-8"))["reports"], key=lambda r: (r["date"], r["url"]))
    # Every title a contract ID carries across the reports: the ID is one
    # contract however a report spells its name ("Western Addition Traffic
    # Signals Phase 1" on 2024-12-20, "Western Addition Area Traffic Signal
    # Upgrades: Phase 1" on 2025-09-01), so each row matches on all of them.
    names = collections.defaultdict(set)
    for rep in reports:
        for x in rep["rows"]:
            names[x["contract"]].add(x["title"])
    seen = set()
    for rep in reports:
        for x in rep["rows"]:
            # A later report can reprint an earlier one's rows (2025-02-10
            # repeats all seven of 2024-12-20): one approval, kept at the
            # earliest report that lists it.
            key = (x["contract"], re.sub(r"[^a-z0-9]+", " ", x["request"].lower()).strip())
            if key in seen:
                continue
            seen.add(key)
            title = "%s: %s" % (x["title"], x["request"].rstrip("."))
            award = x["action"] == "award"
            out.append({
                "kind": "pwdelegated", "date": rep["date"], "item": x["contract"],
                "title": title[:600], "districts": [],
                "decision": ("Awarded by the Director" if award else "Contract change approved by the Director"),
                "approver": DELEGATED_APPROVER, "url": rep["url"],
                # Matched on the project title alone: the request ("Extend
                # contract duration by 200 calendar days") names no project.
                "streets": streets_in_order(x["title"]) if award else [], "cnns": [],
                "blob": flatten(x["title"]),
                # The spellings are kept apart by a word no name holds, so a
                # name phrase cannot run from one spelling into the next.
                "nblob": " qqq ".join(norm_name(t) for t in sorted(names[x["contract"]])),
                "fromMirror": "public-works-delegated",
                **({"award": True} if award else {}),
            })
    return out


# Every item of every meeting each deciding body's fetch script mirrored under
# data/<body>/meetings/ (scripts/fetch-*.py through lib/mirror.py).
# The records above are the keyword and street-name subsets; these are the
# whole record, so a contract award or a program item that names a project
# without a bike word or a street can still reach it. They carry no streets
# and no blocks, so they link only by name or contract number (EXACT), never
# by shared ground: an unfiltered parking order on a project's street is
# place, not the project.
MIRRORS = [
    ("sfmta-hearings", "hearing", "SFMTA engineering hearing"),
    ("sfmta-board", "board", "SFMTA Board of Directors"),
    ("bos-meetings", "supervisors", "Board of Supervisors"),
    ("sfpuc-commission", "sfpuc", "SFPUC Commission"),
    ("public-works-commission", "pwc", "Public Works Commission"),
    ("sfcta-board", "sfcta", "SFCTA Board"),
    ("rec-park-commission", "recpark", "Recreation and Park Commission"),
]
# Agenda furniture that names no project: roll call, minutes, comment.
PROCEDURE = re.compile(
    r"^(roll call|call to order|approv\w* (of )?(the )?minutes|minutes\b|adopt\w* minutes|general public comment|public comment"
    r"|communications|adjournment|announcements?|closed session|consent calendar|regular calendar|new business"
    r"|chair|president|director|executive director|general manager|introduction of new)", re.I)
# A consent calendar's heading ("All matters listed hereunder constitute a
# Consent Calendar ...") is the calendar, not an item; its items are read one
# by one. Its text runs through every item, so it matched any project any item
# named (SFMTA Board 2024-12-03 item 10). Only the heading itself is skipped:
# an item read with the heading as its parent is a real item.
CALENDAR_HEAD = re.compile(r"^\s*all matters listed hereunder", re.I)


BOARD_APPROVES = re.compile(
    r"^\s*(approv\w*|adopt\w*)\b.*\b(modifications?|improvements?|project|bikeway|bike lanes?"
    r"|lane reconfiguration|streetscape|safety)\b", re.I)


# Where an item's formal text ends and the minutes' account of the discussion
# begins: a staff member introduced by name and title, a commissioner, public
# comment. A project named in the discussion is not what the item decided:
# the SFPUC's 2022-02-08 increase to contract WW-712 (a Mission Street brick
# sewer) matched Better Market Street because the project manager said Better
# Market Street would start that spring.
_DISCUSSION = re.compile(
    r"(?<=[.;])\s+(?:[A-Z][a-z]+ ){1,3}[A-Z][a-z’'\-]+, (?:Acting |Interim |Deputy |Assistant |Senior |Principal )*"
    r"(?:Project Manager|Manager|Director|General Manager|Engineer|Analyst|Planner|Chief|Supervisor|Administrator)"
    r"|(?<=[.;])\s+(?:Public Comment|Commissioner [A-Z]|President [A-Z]|Vice President [A-Z]|Director [A-Z][a-z]+ (?:asked|said|noted))")


def formal_text(text):
    """An item's text up to where the minutes start recording the discussion."""
    if not text:
        return text
    m = _DISCUSSION.search(text)
    return text[:m.start()] if m else text


# Meetings not yet held, from tools/meetings/upcoming-meetings.py: each posted agenda's
# items, and the events themselves. Kept apart from a project's "records"
# (decisions) as its "upcoming" list, so nothing that counts decisions counts
# an agenda that has not been heard.
UPCOMING = os.path.join(ROOT, "data", "upcoming-meetings", "meetings.json")
PROJECT_PAGES_URL = re.compile(r"https://www\.sfmta\.com/(?:node/\d+|projects/[a-z0-9-]+)")


DEPT_NAMED = re.compile(r"Municipal Transportation|SFMTA|Public Works|Public Utilities|SFPUC|"
                        r"County Transportation Authority|Recreation and Park", re.I)


def load_upcoming():
    """(agenda-item records, meetings) for meetings not yet held."""
    if not os.path.exists(UPCOMING):
        return [], []
    d = json.load(open(UPCOMING, encoding="utf-8"))
    recs = []
    for m in d["meetings"]:
        for it in m["items"]:
            title = it.get("title") or ""
            if not title or PROCEDURE.match(title) or CALENDAR_HEAD.match(title):
                continue
            # A contract award is linked the way a held one is: streets, kind
            # of work and dates together (award_grade), never by street alone.
            award = m["kind"] in ("pwc", "sfpuc") and bool(AWARD.search(title))
            recs.append({"kind": m["kind"], "date": m["date"], "item": it.get("no"),
                         "title": re.sub(r"\s+", " ", title)[:600], "districts": [], "decision": None,
                         "approver": m["body"], "url": it.get("url") or m["url"],
                         "streets": streets_in_order(title) if award else [], "cnns": [],
                         "blob": flatten(title), "nblob": norm_name(title), "fromMirror": "upcoming-meetings",
                         "meetingId": m["id"], **({"award": True} if award else {})})
    return recs, d["meetings"]


def link_upcoming(projects, recs, meetings, require_district):
    """Each project's meetings not yet held: agenda items naming it, and events its page and theirs link.

    Three routes, each named on the entry:
      agenda   an item on a posted agenda names the project (link(), graded as
               a held record is; only exact, strong and probable are kept)
      event    the event's own sfmta.com page links the project's page
      listed   the project's own page lists the event
    """
    by_id = {m["id"]: m for m in meetings}
    saved = {p["id"]: p["records"] for p in projects}
    for p in projects:
        p["records"] = []
    link(projects, recs, require_district)
    found = {}
    for p in projects:
        got = [r for r in p["records"] if r["grade"] in TRUSTED]
        p["records"] = saved[p["id"]]
        for r in got:
            m = by_id[r["meetingId"]]
            # A Board of Supervisors file names every department's business; a
            # name match there counts only when the item names the project's
            # department (an Airport "parking access and revenue control
            # system" is not SFMTA's), and never for a finished project.
            if r["kind"] == "supervisors" and (not DEPT_NAMED.search(r["title"]) or
                                               re.search(r"complet", p.get("phase") or "", re.I)):
                continue
            found.setdefault(p["id"], []).append({
                "date": m["date"], "time": m.get("time"), "body": m["body"], "kind": m["kind"],
                "meeting": m["title"], "meetingUrl": m["url"], "agenda": m.get("agenda"),
                "item": r["item"], "title": r["title"], "url": r["url"], "route": "agenda",
                "grade": r["grade"], "matchedOn": r["matchedOn"]})
    # Events, by the pages that link them. An SFMTA project is keyed by its
    # /node/ address; its page's canonical /projects/ address is the one an
    # event links, and its page's own list of meetings names the event's URL.
    pages = {}
    if os.path.exists(PROJECT_PAGES):
        pages = json.load(open(PROJECT_PAGES, encoding="utf-8")).get("pages", {})
    url_to_ids, listed = collections.defaultdict(set), collections.defaultdict(set)
    for p in projects:
        page = p.get("page") or ""
        if not PROJECT_PAGES_URL.match(page):
            continue
        url_to_ids[page].add(p["id"])
        node = re.search(r"/node/(\d+)$", page)
        pg = pages.get(node.group(1)) if node else None
        if pg:
            if pg.get("canonical"):
                url_to_ids[pg["canonical"]].add(p["id"])
            for ev in pg.get("meetings") or ():
                listed[ev.get("url")].add(p["id"])
    for m in meetings:
        routes = [(pid, "event", "the event's page links this project's page")
                  for u in m.get("projectPages") or () for pid in sorted(url_to_ids.get(u, ()))]
        routes += [(pid, "listed", "this project's page lists the event") for pid in sorted(listed.get(m["url"], ()))]
        for pid, route, why in routes:
            have = found.setdefault(pid, [])
            if any(x["meetingUrl"] == m["url"] for x in have):
                continue
            have.append({"date": m["date"], "time": m.get("time"), "body": m["body"], "kind": m["kind"],
                         "meeting": m["title"], "meetingUrl": m["url"], "agenda": m.get("agenda"),
                         "item": None, "title": m["title"], "url": m["url"], "route": route,
                         "grade": EXACT, "matchedOn": [why]})
    for p in projects:
        p["upcoming"] = sorted(found.get(p["id"], []), key=lambda x: (x["date"], x["body"], str(x["item"])))
    return sum(1 for p in projects if p["upcoming"])


def load_mirror_records(existing, meeting_days=frozenset()):
    from lib.mirror import load as load_mirror
    have = {}
    for r in existing:
        have.setdefault((r["kind"], r["date"], str(r["item"]).lower()), []).append(r)
    out, n = [], collections.Counter()
    for body, kind, approver in MIRRORS:
        for m in load_mirror(body):
            src = m.get("sources") or {}
            meeting_url = (src.get("minutes") or src.get("results") or src.get("agenda")
                           or src.get("meeting") or src.get("page"))
            for it in m["items"]:
                title = it.get("title") or ""
                if not title or PROCEDURE.match(title) or CALENDAR_HEAD.match(title):
                    continue
                no = it.get("file") or it.get("no")
                if (kind, m["date"], str(no).lower()) in have:
                    # The same item, already read from a keyword extract under
                    # the minutes' title. The mirror's title is the agenda's
                    # ("Folsom Area Stormwater Improvements Project within the
                    # neighborhood around 17th Street and Folsom Street", SFPUC
                    # 2021-11-09 item 10, where the extract has "Approve
                    # Project No. CWWSIPFCDB14, ..."): kept as the item's
                    # other title, so a search by either finds it (audit C3b).
                    t = re.sub(r"\s+", " ", title).strip()
                    for r in have[(kind, m["date"], str(no).lower())]:
                        if t and t != r["title"] and t not in r.get("alsoTitles", ()):
                            r["alsoTitles"] = sorted(set(r.get("alsoTitles", ())) | {t})
                        # The mirror's text for the lettered-part rule, where
                        # the extract kept none (page_meeting_match).
                        if (kind in ("hearing", "board") and (kind, m["date"]) in meeting_days
                                and not r.get("partsText")):
                            r["partsText"] = formal_text(it.get("text"))
                    continue
                full = " ".join(x for x in (title, formal_text(it.get("text"))) if x)
                # An SFMTA Board item that approves the changes along a street
                # is a project's decision even when it names no bike word and
                # not the project: "Approving various parking and traffic
                # modifications along Beach Street between Van Ness Avenue and
                # The Embarcadero" (2024-12-17) is the Beach Street Quick-Build.
                # Those items, and only those, also go through the street and
                # block rules. Single hearing items stay name-only: a traffic
                # signal on a project's block is as often other work.
                # So are the items of a hearing or Board meeting a project's own
                # page says it went to (meeting_days), but only for that
                # project: link() keeps such an item from every other project
                # on the street unless it names them ("pageDay").
                streets_, cnns_ = [], []
                approves = kind == "board" and bool(BOARD_APPROVES.search(title))
                page_day = not approves and (kind, m["date"]) in meeting_days
                if approves or page_day:
                    streets_ = streets_in_order(title)
                    cnns_ = sorted(record_blocks(title, (streets_ or [None])[0]))
                # A contract award at the Public Works or SFPUC Commission
                # names the streets it opens; it links by street, scope and
                # date together (award_grade), never by street alone.
                award = kind in ("pwc", "sfpuc") and bool(AWARD.search(title))
                if award:
                    streets_ = streets_in_order(title)
                out.append({
                    "kind": kind, "date": m["date"], "item": no,
                    "title": re.sub(r"\s+", " ", title)[:600],
                    "districts": sorted(districts(it.get("district"))),
                    "decision": it.get("decision"), "approver": m.get("committee") or approver,
                    "url": it.get("url") or meeting_url, "streets": streets_, "cnns": cnns_,
                    "blob": flatten(full), "nblob": norm_name(full), "fromMirror": body,
                    **({"parts": hearing_parts(no, it.get("text"), it.get("decision"))}
                       if kind == "hearing" else {}),
                    **({"award": True} if award else {}),
                    **({"pageDay": True} if page_day else {}),
                    **({"partsText": formal_text(it.get("text"))}
                       if kind in ("hearing", "board") and (kind, m["date"]) in meeting_days else {}),
                    # Severed from its consent calendar: the calendar's vote is not its vote.
                    **({"severed": True} if it.get("severed") else {}),
                })
                n[body] += 1
    print("  mirrored items read for name matching: " + ", ".join("%s %d" % kv for kv in sorted(n.items())))
    return out


# ---- names and contract numbers ---------------------------------------------
# A project is named several ways across the city's records: "Folsom-Howard
# Streetscape Project" on SFMTA's page, "Folsom Howard Streetscape" in a
# hearing order; "Various Locations Pavement Renovation No 68" in the feed,
# "Various Locations Pavement Renovation No. 68 - Contract Award" at the
# Public Works Commission; "WD-2923 (formerly WD-2764): 24-inch Water Main
# Rehabilitation" in the feed, "Award Contract No. WD-2923" at the SFPUC
# Commission. norm_name() makes those spellings one, and name_keys() gives
# the phrases that identify a project: its core name and any contract code.
def norm_name(t):
    t = (t or "").lower().replace("&", " and ")
    t = re.sub(r"#\s*", " no ", t)
    t = re.sub(r"\bno\.\s*", "no ", t)
    t = re.sub(r"\bnumber\b", "no", t)
    t = re.sub(r"\b(w[dw]|cs|db|hh|sww)-\s*(\d{3,4}[a-z]?)\b", r"\1\2", t)
    t = re.sub(r"\bpro\.\s*(\d{4})\b", r"pro\1", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    # "8th Street, Clay Street, and Leavenworth Street Pavement Renovation"
    # at the Public Works Commission is the feed's "8th St, Clay St and
    # Leavenworth St Pavement Renovation": one spelling of each suffix.
    t = _SUFFIX.sub(lambda m: SUFFIXES[m.group(1)], t)
    return re.sub(r"\s+", " ", t).strip()


SUFFIXES = {"street": "st", "avenue": "ave", "av": "ave",
            "boulevard": "blvd", "drive": "dr", "road": "rd", "terrace": "ter", "highway": "hwy"}
_SUFFIX = re.compile(r"\b(%s)\b" % "|".join(SUFFIXES))

# Project names that are also the names of places. "Treasure Island and Yerba
# Buena Island Project" matched 31 records about the islands (Park Code
# amendments, advisory-board bylaws, street names, power contracts), and the
# audit's hand-graded sample (data/audit/grades/c3-links.csv) found every one it
# drew to be about the place, not the project. For these names the record has
# to say "<name> Project" to be the project's; a bare mention of the place is
# kept, graded PLACE, and never counted. A list, not a word test: a test for
# "has no work word" also caught Better Market Street, Active Beale Street and
# the Octavia Boulevard Enhancement Program, whose records are their own.
PLACE_KEYS = {"treasure island and yerba buena island", "candlestick point hunters point shipyard"}


def is_place_key(key):
    return key in PLACE_KEYS


# What makes a mention of such a place the project's: "<place> Project", or an
# act on the development itself (its streets, its infrastructure, its maps and
# its special use district). The hand grades agree: the islands' street names
# and the amended development agreement are the project's; the Park Code rules
# for the island parks and the power contracts are not.
_PLACE_OWN = re.compile(r"\b(development|st|streets|infrastructure|transportation|final (?:transfer )?map"
                        r"|subdivision|special use district)\b")


def place_is_project(pat, text):
    """True when a text naming a place-named project is about the project, not the place (normalised text)."""
    return bool(re.search(pat.pattern + r" project", text) or _PLACE_OWN.search(text))


_PREFIX = re.compile(r"^(pw|sfmta|joint (?:\w+ )?lead|joint)\s+")
_JV = re.compile(r"\bjv (?:w |with )?vl pr no (\d+\w?)\b")
# Contract numbers: SFPUC water (WD), wastewater (WW), Hetch Hetchy (HH),
# design-build (DB), sewer (SWW), consultant (PRO.0101); Public Works' CS-.
_CODE = re.compile(r"\b((?:w[dw]|cs|db|hh|sww)\d{3,4}[a-z]?|pro\d{4})\b")
_GENERIC_ONLY = re.compile(r"^(various locations?|citywide|city wide|as needed)[a-z ]*$")


def name_keys(name):
    """The phrases that identify a project in another body's record: core name, contract codes."""
    raw = name or ""
    n = norm_name(re.sub(r"\([^)]*\)", " ", raw))
    n = re.sub(r"\b\d{6,}\b", " ", n)  # an internal job number, "Folsom St 10032072"
    while _PREFIX.match(n):
        n = _PREFIX.sub("", n)
    n = re.sub(r"\s+(project|projects|program)$", "", n.strip())
    n = re.sub(r"\s+", " ", n).strip()
    keys = []
    # Two words and twelve letters: "slow streets" is exactly twelve, and the
    # rule before this one needed thirteen, which is how the Slow Streets row
    # counted 2 of its 14 dated mentions. A generic stem with no contract
    # number ("various locations sewer replacement") names a kind of job,
    # not a job, and is never a key.
    if len(n) >= 12 and len(n.split()) >= 2 and not (_GENERIC_ONLY.match(n) and not re.search(r"\bno \d", n)):
        keys.append(n)
    # "Contract 36 Traffic Signal Modifications" is awarded as "Traffic
    # Signal Modifications No. 36".
    m = re.match(r"^contract (\d+[a-z]?) (.{12,})$", n)
    if m:
        keys.append("%s no %s" % (m.group(2), m.group(1)))
        # A signal contract's last word changes between SFMTA's page and the
        # award: "Contract 35 Traffic Signal Modifications" was awarded by the
        # Public Works Commission as "Contract No. 35 Traffic Signal Upgrades"
        # (2026-04-30). The number and "traffic signal" name the contract.
        if m.group(2).startswith("traffic signal"):
            keys.append("contract no %s traffic signal" % m.group(1))
    # The head of a name that carries a phase or a second part after a dash or
    # an "and": "Lower Alemany Stormwater Improvements - Alemany Shaft" is the
    # Lower Alemany Area Stormwater Improvement Project's shaft; "FASIP
    # Harrison/Treat Box Sewer and Connecting Auxiliary Sewers" is the
    # Harrison/Treat box sewer. A head is a key only with three words or more
    # and a word for the kind of work, so a street pair ("Broad Street and
    # Randolph Street ...") never becomes one.
    body = re.sub(r"^[A-Z]{3,6}\s+", "", re.sub(r"\([^)]*\)", " ", raw).strip())
    for part in re.split(r"\s+[-–—:]\s+|\s+and\s+", body)[:1]:
        h = norm_name(part)
        while _PREFIX.match(h):
            h = _PREFIX.sub("", h)
        if h != n and len(h) >= 15 and len(h.split()) >= 3 and families(h) and not _GENERIC_ONLY.match(h):
            keys.append(h)
    full = norm_name(raw)
    keys += _CODE.findall(full)
    for m in _JV.finditer(full):
        keys.append("various locations pavement renovation no %s" % m.group(1))
    # "8th, Beale, Clay, Leavenworth and Main Streets Sewer Replacement (JV w
    # 8th St, Clay St and Leavenworth St Pavement Renovation)": the feed says
    # the sewer job is let jointly with the named paving job, and the Public
    # Works Commission awarded that one contract as "8th Street, Clay Street,
    # and Leavenworth Street Pavement Renovation and Sewer Replacement"
    # (2024-10-28). The joint job's name is a key, as the VL PR number is above.
    keys += joint_keys(raw)
    return sorted(set(keys), key=len, reverse=True)


def joint_keys(name):
    """The name of the job a feed row says it is let jointly with: "(JV w <name>)"."""
    out = []
    for m in re.finditer(r"\(\s*JV\s+(?:w|with)\.?\s+([^)]{12,})\)", name or "", re.I):
        k = norm_name(m.group(1))
        if not re.match(r"vl pr no\b", k) and len(k.split()) >= 3 and families(k):
            out.append(k)
    return out


_PATTERNS = {}  # project id -> compiled name pattern, built once
_PLACE = {}  # project id -> True when every key of its name names only a place


def contract_keys(text):
    """Contract numbers a project's scope names ("WD-2921 ..."), as name keys."""
    return sorted(set(_CODE.findall(norm_name(text or ""))))


def name_pattern(name, extra=()):
    keys = sorted(set(name_keys(name)) | set(extra), key=len, reverse=True)
    # Each word may take a plural "s": the feed says "Folsom Area Stormwater
    # Improvement Project" where the SFPUC awarded "Folsom Area Stormwater
    # Improvements".
    # And "area" may sit inside it: the "Lower Alemany Area Stormwater
    # Improvement Project" is the feed's "Lower Alemany Stormwater Improvements".
    def word(w):
        return re.escape(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w) + "s?"

    # An "and" between two names may be a slash in the record: the Board of
    # Supervisors titles the development "Treasure Island/Yerba Buena Island",
    # which norm_name reads as "treasure island yerba buena island".
    def phrase(k):
        out, words = "", k.split(" ")
        for i, w in enumerate(words):
            if w == "and" and 0 < i < len(words) - 1:
                out += r"(?:and\ )?"
                continue
            # A slash in the name may be an "and" in the record: the Board of
            # Supervisors' 2019-07-23 transfer map names "Candlestick Point and
            # Hunters Point Shipyard", the project "Candlestick Point/Hunters
            # Point Shipyard" (audit C3b).
            out += word(w) + (r"\ (?:area\ )?(?:and\ )?" if i < len(words) - 1 else "")
        return out
    alts = [phrase(k) for k in keys]
    return re.compile(r"\b(?:%s)\b" % "|".join(alts)) if keys else None


# How far a link can be trusted. Bryan, 2026-09-21: "We'll need to be careful
# about the link." A street name on its own is not careful — one board item
# about the Bayview Community Pathway names Third Street, and 22 projects
# mention Third Street somewhere on their page.
EXACT = "exact"        # the record names the project, in words
STRONG = "strong"      # street match; counted only when the record names a program this project is by name
PROBABLE = "probable"  # street match; counted only for an award agreeing on streets, work and dates
AMBIGUOUS = "ambiguous"  # a good match, but to more than one project
COLOCATED = "co-located"  # on this project's blocks, about different work
WEAK = "weak"          # the corridor street only, somewhere in the page text
SAMESTREET = "same street"  # on the project's street, about a different kind of work
PLACE = "place"        # names the place a place-named project is in, not the project

# Hand-grading 40 block-matched links on 2026-09-22 found 7 that were the same
# piece of work, 1 wrong, and 32 that shared a block and nothing else — a
# bike-share dock or a parking rule landing on a project's street. Shared
# ground is real evidence about PLACE and none about WORK. So a block match
# is only the project's own record when the record's action is the kind of
# thing that project does; otherwise it is co-located, reported and never
# counted as the project's document. These are the action words that make a
# hearing or board item plausibly a street project's own decision.
_PROJECT_ACTIONS = re.compile(
    r"BIKEWAY|BIKE LANE|PROTECTED|QUICK[- ]BUILD|SPEED (HUMP|TABLE|CUSHION|LIMIT)"
    r"|TRAFFIC SIGNAL|SIGNAL|TURN (RESTRICTION|ON RED|LANE)|NO (LEFT|RIGHT) TURN"
    r"|TRANSIT (LANE|ONLY|BOARDING)|BUS (ZONE|STOP|BULB)|BOARDING ISLAND"
    r"|SLOW STREET|TRAFFIC DIVERTER|DAYLIGHT|CROSSWALK|PEDESTRIAN|ROAD DIET"
    r"|ONE[- ]WAY|TOW[- ]AWAY, NO STOPPING|STREETSCAPE|PARKING PROTECTED"
    r"|CLASS I{1,3}V?\b|CLASS IV", re.I)
# Things the hearing legislates block by block that are nobody's project:
# a dock, a corral, a coloured curb, a time limit.
_FURNITURE = re.compile(
    r"BIKE ?SHARE|BIKESHARE|BIKE CORRAL|RED ZONE|BLUE ZONE|YELLOW ZONE|WHITE ZONE"
    r"|GREEN ZONE|METERED|TIME LIMIT|HOUR PARKING|RESIDENTIAL PERMIT|LOADING ZONE"
    r"|MOTORCYCLE PARKING|PASSENGER LOADING", re.I)


def is_project_work(title):
    t = title or ""
    return bool(_PROJECT_ACTIONS.search(t)) and not (
        _FURNITURE.search(t) and not re.search(r"BIKEWAY|BIKE LANE|CLASS I", t, re.I))


# Above this many blocks a project's shape is a study area, not a corridor.
STUDY_AREA_BLOCKS = 120

GENERIC_TAIL = re.compile(r"\s+(project|projects|program)$")


def flatten(t):
    return re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())


def grade(project, record):
    """How good a link is, or None. Returns (grade, the evidence)."""
    # An order or a minute that names the project in words settles it: "as part
    # of the Bayview Community Pathway project". Nothing else is as good, and
    # it is the only route that works for a project whose name is not a street.
    if project["id"] not in _PATTERNS:
        # The feed's scope often carries the contract number its name lacks:
        # "8 & 12-Inch Ductile Iron Water Main Replacement on Palou, Quesada
        # and Revere" is WD-2921 only in its scope, and WD-2921 is what the
        # SFPUC Commission awarded.
        _PATTERNS[project["id"]] = name_pattern(project["name"], contract_keys(project.get("scopeText")))
        keys = name_keys(project["name"])
        _PLACE[project["id"]] = bool(keys) and all(is_place_key(k) for k in keys)
    pat = _PATTERNS[project["id"]]
    nblob = record.get("nblob")
    if nblob is None:
        nblob = record["nblob"] = norm_name(record.get("title", "") + " " + record.get("blob", ""))
    if pat is not None:
        hit = pat.search(nblob)
        if hit and _PLACE.get(project["id"]) and not place_is_project(pat, nblob):
            return PLACE, [project["name"], "names the place “%s”, not the project" % hit.group(0)]
        if hit:
            return EXACT, [project["name"], "named as “%s”" % hit.group(0)]
    if record.get("award"):
        g, where = award_grade(project, record)
        if g or record.get("fromMirror"):
            return g, where
        # An SFPUC award read from the street extract still shows beside a job
        # it shares ground with, as it did before it was read as an award, but
        # only as context: it is not this job's award.
        g, where = street_grade(project, record)
        if g in (STRONG, PROBABLE):
            return SAMESTREET, where + ["an award that does not agree with this job on streets, work and dates"]
        return g, where
    g, where = street_grade(project, record)
    # A street is only half a match. The rule for this file (2026-09-28): a
    # record attaches to a project by its name, its contract number, or its
    # street AND its scope. So a match on the street alone is kept, labelled
    # as other work on the same street, and never counted: the Valencia
    # Bikeway's orders are not a record of "18th St and Valencia St Pavement
    # Renovation", and a bikeshare dock is not a record of a quick-build.
    if g in (STRONG, PROBABLE) and not scope_agrees(project, record):
        return SAMESTREET, where + ["about other work"]
    # A contract on a job's street for its kind of work is the job's only
    # while the job is live: a 2021 water-main award on Page Street is not the
    # award of a Page Street water main the feed starts in 2025.
    if (g in (STRONG, PROBABLE) and record["kind"] in ("sfpuc", "pwc") and project["source"].startswith("Public Works")
            and not in_window(project, record)):
        return SAMESTREET, where + ["dated outside this project's window"]
    return g, where


# How far before a job's start its contract can be awarded and still be its
# own, and how far after the start when the feed gives no end. A Public Works
# paving contract is awarded about a year before work; the SFPUC's water-main
# awards run up to two. Four years is the outer edge, not the norm.
AWARD_LEAD_DAYS = 4 * 365
AWARD_LAG_DAYS = 2 * 365


def in_window(project, record):
    """True when a record's date falls where a contract for this job could: before its start, not after its end."""
    start, d = project.get("start"), (record.get("date") or "")[:10]
    if not start or len(d) < 10:
        return False
    s = dt.date.fromisoformat(start[:10])
    end = project.get("end")
    e = dt.date.fromisoformat(end[:10]) if end else s + dt.timedelta(days=AWARD_LAG_DAYS)
    return s - dt.timedelta(days=AWARD_LEAD_DAYS) <= dt.date.fromisoformat(d) <= e


# An item that awards, advertises or approves the plans for a construction
# contract. Such an item names the streets the contract opens, which is how a
# job the feed names differently ("Various Locations Pavement Renovation No 81
# and Sewer Replacement" against "PW Various Locations Sewer Replacement (JV VL
# PR No 81)") is found.
AWARD = re.compile(r"\b(award|contract award|approve the plans and specifications|advertise)\b", re.I)


def award_grade(project, record):
    """A contract award that names the project's streets and its kind of work, in its window: PROBABLE.

    The rule is street AND scope AND time, all three. At least two of the
    streets the project is named for (or its only one) must be in the award,
    the award must be for the kind of work the project does (paving, sewer and
    water, street design), and it must be dated inside the project's window.
    One street, or another kind of work, or another year, is other work on the
    same street and is kept as SAMESTREET, never counted.
    """
    if not project["source"].startswith("Public Works") or not record["streets"]:
        return None, []
    mine = set(project["streets"])
    shared = mine & set(record["streets"])
    if not mine:
        # A feed name with no street suffix ("Laguna and Howard CSD
        # Improvements", "Mariposa, Lake Merced and Evans CSD Improvements")
        # parses to no street. Its words still name them: an award street
        # whose bare name is a phrase of the job's name counts, and two are
        # needed, never one (audit C4: the WW-757R and WW-790 awards).
        name = norm_name(project.get("name"))
        shared = {s for s in record["streets"]
                  if (lambda bare: bare and re.search(r"\b%s\b" % re.escape(bare), name))(
                      re.sub(r"\s+(st|ave|blvd|dr|rd|ter|hwy|way|pl|ct|ln)$", "", s))}
        if len(shared) < 2:
            return None, []
    elif len(shared) < min(2, len(mine)):
        return None, []
    want = families(" ".join(x for x in (project.get("name"), project.get("scope")) if x))
    kinds = want & families(record.get("title"))
    where = sorted(shared)
    if not kinds:
        return SAMESTREET, where + ["an award for other work"]
    # The contract number says whose award it is. A job that carries its own
    # (WD-2936) is not awarded under another (WW-743), and an SFPUC water
    # contract (WD-) is not a sewer job's award, nor a wastewater one (WW-) a
    # water main's: "sewer and water" is one family for streets, two for
    # contracts.
    theirs = set(_CODE.findall(norm_name(record.get("title"))))
    ours = set(_CODE.findall(norm_name(" ".join(x for x in (project.get("name"), project.get("scopeText")) if x))))
    if theirs and ours and not theirs & ours:
        return SAMESTREET, where + ["an award under another contract number"]
    job = norm_name(" ".join(x for x in (project.get("name"), project.get("scope"), project.get("scopeText")) if x))
    prefixes = {c[:2] for c in theirs}
    if prefixes == {"wd"} and not re.search(r"\bwater\b", job):
        return SAMESTREET, where + ["a water contract; this job is not a water main"]
    if prefixes == {"ww"} and not re.search(r"sewer|\bcsd\b|stormwater|outfall|wastewater", job):
        return SAMESTREET, where + ["a wastewater contract; this job is not a sewer"]
    if not in_window(project, record):
        return SAMESTREET, where + ["an award dated outside this project's window"]
    return PROBABLE, where + ["an award for %s work" % " and ".join(sorted(kinds))]


def street_grade(project, record):
    if not record["streets"]:
        return None, []
    corridor = record["streets"][0]
    # Blocks before names. When both sides know their blocks, shared ground is
    # the evidence and a shared street name with no shared block is a
    # coincidence of geography: two projects on 4th Street are told apart here,
    # and a record about Third and Cargo does not reach a project at Third and
    # King. A record that resolved to blocks but shares none with a project
    # whose blocks are known is NOT the same place, whatever the names say.
    rb, pb = set(record.get("cnns") or ()), set(project.get("cnns") or ())
    if rb and pb:
        shared = rb & pb
        if shared:
            # A project drawn as a study area of hundreds of blocks contains
            # every record on every street inside it. Shared ground there is
            # real but weak, so it is PROBABLE rather than STRONG, and the
            # rival rule below lets a tighter project take the record.
            where = [f"{len(shared)} shared block{'s' if len(shared) > 1 else ''} on {corridor}"]
            # For a Public Works or SFPUC job, the SFPUC's own contract on its
            # blocks is its kind of work when the kinds agree (a water main for
            # a water-main job); the time window is applied in grade().
            utility = (project["source"].startswith("Public Works") and record["kind"] in ("sfpuc", "pwc")
                       and families(" ".join(x for x in (project.get("name"), project.get("scope")) if x))
                       & families(record.get("title")))
            if not is_project_work(record.get("title")) and not utility:
                return COLOCATED, where
            g = PROBABLE if len(pb) > STUDY_AREA_BLOCKS else STRONG
            return g, where
        if corridor in set(project["streets"]) | set(project["streetsFromText"]):
            return WEAK, [f"{corridor}, but no shared block"]
        return None, []
    crosses = set(record["streets"][1:])
    name = set(project["streets"])
    text = set(project["streetsFromText"])

    if corridor in name:
        # A Public Works job is NAMED for the corridors it renovates, but the
        # name is a headline, not an extent: "Broadway, Pacific Ave and Vallejo
        # St Pavement Renovation" matched a bikeshare dock at Vallejo and
        # Stockton, which is a different stretch of Vallejo from the one this
        # job touches. Its street list is the extent, so the corridor has to be
        # in that too. An SFMTA project's name IS its corridor, so it stands.
        if not project["source"].startswith("Public Works") or corridor in text:
            return STRONG, [corridor]
    if corridor in text:
        shared = crosses & (name | text)
        if shared:
            return PROBABLE, sorted({corridor} | shared)
        return WEAK, [corridor]
    # The corridor did not match, so a cross-street hit is a coincidence of
    # geography rather than evidence this record is about this project.
    return None, []


FAMILIES = [
    ("paving", re.compile(r"paving|pavement|resurfac", re.I)),
    ("sewer and water", re.compile(r"sewer|water main|\bwater\b|stormwater|outfall|pipe|\bcsd\b|auxiliary water"
                                   r"|\bawss\b|\befws\b|combined sewer", re.I)),
    ("street design", re.compile(r"streetscape|safety|quick[- ]build|bike|bicycl|pedestrian|signal|muni forward"
                                 r"|transit|traffic calming|slow street|multimodal", re.I)),
]


def families(text):
    return {name for name, rx in FAMILIES if rx.search(text or "")}


def scope_agrees(project, record):
    """True when a record on a project's street is about the kind of work the project does."""
    title = record.get("title") or ""
    legislates = is_project_work(title) or bool(BOARD_APPROVES.search(title))
    if not project["source"].startswith("Public Works"):
        return legislates
    want = families(" ".join(x for x in (project.get("name"), project.get("scope")) if x))
    have = families(title)
    if legislates and record["kind"] in ("hearing", "board"):
        have.add("street design")
    return bool(want & have)


# What a link MEANS depends on which kind of project it is attached to, and
# conflating the two would be the worst thing this file could do. An order
# about Valencia Street's bikeway authorises the SFMTA project that built it.
# The same order beside "18th St and Valencia St Pavement Renovation" says only
# that Public Works will open a street the city has legislated a bikeway on —
# which is worth reading before the paving starts, and is not evidence the
# paving job includes the bikeway.
#
# A Board of Supervisors file is a third thing again. The Board does not
# legislate bikeway geometry — that is the City Traffic Engineer's job, and the
# 58-to-14 split between the hearing record and the SFMTA Board record is the
# measure of it. What the Board does to a street is vacate it, permit an
# encroachment on it, rename it, set its speed limit or appropriate money for
# it. So its link never authorises a project; it says the Board has acted on
# this street, which is context a reader wants and is not the same claim.
OWNPAGE = "listed on this project's own page"
AUTHORISES = "authorises this project"
SHARES = "concerns a street this project will open"
LEGISLATES = "the Board of Supervisors has legislated on this street"
OPENS = "the SFPUC Commission has awarded work that opens this street"


ONBLOCK = "was decided on a block this project covers"
NAMESPLACE = "names the place this project is in, not the project"
OTHERWORK = "is about other work on a street this project is on"
STREETONLY = "is on a street this project is on and does not name the project"
AWARDED = "%s awarded a contract for this kind of work on this project's streets, in its dates"
WHO = {"pwc": "the Public Works Commission", "sfpuc": "the SFPUC Commission",
       "pwdelegated": "the Director of Public Works, under the Public Works Commission's delegation,"}


# How a record is named in the page, by kind; hearings carry their item number.
WHERE = {"board": "SFMTA Board", "supervisors": "Board of Supervisors",
         "sfpuc": "SFPUC Commission item {item}",
         "pwc": "Public Works Commission item {item}",
         "sfcta": "SFCTA Board item {item}",
         "recpark": "Recreation and Park Commission item {item}",
         "pwdelegated": "Director of Public Works, delegated approval of contract {item}",
         "project-page": "the project's own page"}


ACTED = {"supervisors": "the Board of Supervisors acted on this project by name",
         "sfpuc": "the SFPUC Commission acted on this project by name",
         "pwc": "the Public Works Commission acted on this project by name",
         "sfcta": "the SFCTA Board acted on this project by name",
         "recpark": "the Recreation and Park Commission acted on this project by name"}


# An update, a presentation or a Mayor's question-time topic names a project
# without deciding anything. The C3c round-5 sample (seed 20261001) graded
# three such items wrong for reading "acted on": Better Market Street
# 2020-10-27, Folsom Streetscape 2025-02-27, Slow Streets 2022-01-11.
INFORMATIONAL = re.compile(r"(?i)^\s*(?:\[?information(?:al)?\]?\s*[-:–]?\s*)?"
                           r"(?:(?:major\s+)?capital\s+project\s+update|project\s+update|"
                           r"(?:status\s+)?update\s+on\b|presentation\b|informational\b)"
                           r"|the mayor shall discuss")


def relation(project, record, grade=None):
    if grade == EXACT and record["kind"] == "pwdelegated":
        return ("the Director of Public Works %s this project's contract under the Public Works Commission's "
                "delegation, and reported it to the Commission"
                % ("awarded" if record.get("award") else "approved a change to"))
    if (grade == EXACT and record["kind"] in ACTED
            and INFORMATIONAL.search(record.get("title") or "")):
        body = ACTED[record["kind"]].split(" acted on", 1)[0]
        return "%s heard an item naming this project, with no decision on it" % body
    if grade == COLOCATED:
        return ONBLOCK
    if grade == PLACE:
        return NAMESPLACE
    if grade == SAMESTREET:
        return OTHERWORK
    if grade == PROBABLE and record.get("award"):
        return AWARDED % WHO.get(record["kind"], "a city body")
    if grade == EXACT and record["kind"] == "supervisors":
        body = ("the Board of Supervisors' " + record["approver"]
                if re.search(r"\bCommittee\b", record.get("approver") or "") else "the Board of Supervisors")
        # An item with no action is one introduced and referred (the tail of
        # a Board agenda, 2023-12-12 item 55): on the agenda, not acted on.
        if not record.get("decision"):
            return "%s had an item naming this project on its agenda, with no action that day" % body
        # A committee recommends or amends; the Board acts later, as its own record.
        return "%s acted on this project by name" % body
    if grade == EXACT and record["kind"] in ACTED:
        return ACTED[record["kind"]]
    if grade == EXACT and project["source"].startswith("Public Works"):
        return "the record names this project"
    if record["kind"] == "supervisors":
        return LEGISLATES
    if record["kind"] == "sfpuc":
        return OPENS
    return (SHARES if project["source"].startswith("Public Works")
            else AUTHORISES)


def attach_page_records(projects):
    """The project's own record, off its sfmta.com page — no inference.

    tools/projects/sfmta-project-pages.py reads five blocks the department itself
    attaches to a project: a dated timeline, the project's own hearing and
    street-change notices, its Board and public meetings, its updates and its
    documents. The department has already said these belong to THIS project,
    so each is graded EXACT and carries its own relation. This is the record
    the block join could not tell from a bike-share dock on the same street.
    """
    if not os.path.exists(PROJECT_PAGES):
        return 0
    pages = json.load(open(PROJECT_PAGES, encoding="utf-8"))["pages"]
    n = 0
    for p in projects:
        node = (p["id"].split(":", 1)[1] if p["id"].startswith("sfmta:")
                else "slug:" + p["id"].split(":", 1)[1] if p["id"].startswith("sfmta-page:") else None)
        pg = pages.get(str(node)) if node else None
        if not pg:
            continue
        for t in pg["timeline"]:
            p["records"].append({
                "kind": "project-page", "date": _season_date(t["when"]) or "",
                "when": t["when"], "item": None, "title": t["what"],
                "decision": t.get("status"), "approver": "SFMTA project page",
                "pageBlock": "timeline",
                "url": pg["page"], "matchedOn": ["the project's own page"],
                "grade": EXACT, "relation": OWNPAGE, "recordBlocks": 0})
            n += 1
        # The page's notices and meetings stay page records. The "meetings"
        # block lists open houses, tabling events and walking tours beside
        # any Board date, and labelling all of them "SFMTA Board" showed 25
        # community events as votes (audit C3, 2026-09-28). The body's own
        # record of a hearing or a Board vote comes from its mirror instead.
        for block, rows, approver in (("notice", pg["notices"], "notice on the project page"),
                                      ("event", pg["meetings"], "event on the project page")):
            for r in rows:
                p["records"].append({
                    "kind": "project-page", "pageBlock": block, "date": r.get("date") or "", "item": None,
                    "title": r["title"], "decision": None, "approver": approver,
                    "url": r["url"], "matchedOn": ["the project's own page"],
                    "grade": EXACT, "relation": OWNPAGE, "recordBlocks": 0})
                if r.get("end"):
                    p["records"][-1]["end"] = r["end"]  # an event over several days (a virtual open house)
                n += 1
        p["pageDocuments"] = pg["documents"]
        p["pageUpdates"] = pg["updates"]
    return n


_SEASON = {"winter": "01", "spring": "04", "summer": "07", "fall": "10", "autumn": "10"}
_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_WORD = "|".join(_MONTHS + list(_SEASON))
# The first date the text names, with the season or month in front of its
# year: "Winter-spring 2027" (a range of seasons in one year), "Winter
# 2025/26" (a winter that runs over the new year), "Early 2018 - Spring 2019".
# Reading the season nearest the year instead took each range's end: the
# D2 hand grade (2026-09-29) found Bosworth/Monterey's "Winter-spring 2027"
# dated April, Contract 35's "Winter 2025/26" dated January 2025 and Third
# Street Bridge's "Early 2018 - Spring 2019" dated April 2019.
_FIRST_WHEN = re.compile(
    r"(?:\b(early|mid|late)[- ]*)?(?:\b(%s)\b(?:\s*[-–/]\s*(?:%s)\b)?(?:\s+\d{1,2}(?:st|nd|rd|th)?)?,?\s+(?:of\s+)?)?"
    r"\b((?:19|20)\d\d)\b(?:\s*/\s*(\d{2}(?:\d{2})?)\b)?" % (_WORD, _WORD))


def _season_date(when):
    """"Fall 2022" → 2022-10; "Late spring 2026" → 2026-05; "February 2024" → 2024-02; a range takes its start:
    "Winter-spring 2027" → 2027-01, "Early 2018 - Spring 2019" → 2018; "Winter 2025/26" → 2025-12."""
    m = _FIRST_WHEN.search((when or "").lower())
    if not m:
        return None
    q, word, y, over = m.groups()
    if word in _MONTHS:
        return f"{y}-{_MONTHS.index(word) + 1:02d}"
    if word:
        if q:
            # "Late spring 2026" starts in May, not April (lib/seasons.py).
            return f"{y}-{seasons.months(q, word)[0]:02d}"
        if word == "winter" and over:
            return f"{y}-12"  # "Winter 2025/26" starts in December 2025
        return f"{y}-{_SEASON[word]}"
    return y


def _stems(text):
    out = set()
    for w in norm_name(text).split():
        w = w[:-1] if len(w) > 3 and w.endswith("s") else w
        out.add(SUFFIXES.get(w, w))
    return out


def _stem_list(text):
    out = []
    for w in norm_name(text).split():
        w = w[:-1] if len(w) > 3 and w.endswith("s") else w
        out.append(SUFFIXES.get(w, w))
    return out


def is_program(name):
    """A program is named for no street: "Slow Streets", "Slow Streets Program".

    A name that carries a street ("5th Street Improvement Project", "13th
    Street Safety Project") is a project, and a record naming it in words is
    that project's own, whatever other project shares its words."""
    return not streets(name or "")


def is_instance(name, evidence):
    """True when a project's name carries, in order, the whole program name an EXACT match found, and more.

    In order, as a phrase: "Cayuga Avenue Slow Street" carries "slow street";
    "5th St Safety Improvement Project" holds every word of "5th st
    improvement" but not the phrase, and is not an instance of it (audit C3,
    round-5 review: the 2019-09-17 SFMTA Board approval of the 5th Street
    Improvement Project's bike lanes went to a 2029 Public Works job)."""
    named = [s for s in evidence if s.startswith("named as")]
    if not named:
        return False
    words = _stem_list(re.sub(r"^named as “|”$", "", named[0]))
    own = _stem_list(name)
    if not words or len(own) <= len(words):
        return False
    return any(own[i:i + len(words)] == words for i in range(len(own) - len(words) + 1))


def acronym(name):
    """A program's initials: "Folsom Area Stormwater Improvement Project" -> "fasip"."""
    words = re.findall(r"[a-z]+", re.sub(r"^pw\s+", "", (name or "").lower()))
    return "".join(w[0] for w in words) if len(words) >= 3 else ""


def names_program(name, program):
    """True when a project's own name carries another project's full initials as a word ("FASIP Harrison/Treat Box
    Sewer" inside the Folsom Area Stormwater Improvement Project)."""
    a = acronym(program)
    return len(a) >= 3 and re.search(r"\b%s\b" % a, (name or "").lower()) is not None


# An SFMTA Board item that lists hearing orders one by one ("Approving the
# following traffic modifications ... A. ESTABLISH – TOW-AWAY ...") approves
# each order, not a project.
_ITEMISED = re.compile(r"\b(ESTABLISH|RESCIND)\b")
# The approval of a street's changes, not any item that opens "Approving":
# "Approving parking regulations and amending the Transportation Code ... on
# Turk Street near 1011 Turk Street to support ... public safety agencies"
# (2025-12-02) is a permit-parking rule, not the Turk Street Safety Project's.
_APPROVES_CHANGES = re.compile(r"^\s*approv\w*\b[^.;]{0,120}?\b(modifications?|improvements?|bikeways?|bike lanes?"
                               r"|bicycle lanes?|lane reconfiguration|streetscape)\b", re.I)
# An item that names the project it belongs to names it: "... along Mission
# Street associated with the Mission Street Excelsior Safety Project"
# (2019-09-17) is that project's, not Mission Street SoMa Transit's.
_NAMES_ITS_PROJECT = re.compile(r"\b(?:associated with|as part of|part of|for) the ([a-z0-9 /&'’.-]{3,80}?) "
                                r"(?:project|program|quick[- ]build)\b", re.I)
# Words a street project's name carries beside its street that say nothing
# about which work it is. The rest ("New Traffic Signals", "SoMa Transit")
# must be in the item too.
_NAME_FILLER = {"project", "projects", "program", "phase", "quick", "build", "safety", "improvement", "improvements",
                "streetscape", "implementation", "the", "and", "of", "one", "two", "1", "2", "formerly", "st", "ave", "blvd", "way"}


def board_approves_named(project, record):
    """True when an SFMTA Board item approves the work along the street an SFMTA project is named for.

    "Approving various parking and traffic modifications along Beach Street
    between Van Ness Avenue and The Embarcadero" (2024-12-17) is the Beach
    Street Quick-Build Project's approval; "Approving transit accessibility and
    active transportation safety improvements on Frida Kahlo Way" (2024-05-07)
    is the Frida Kahlo Way Quick-Build's. That is street AND scope: the Board
    approving a street's changes, for the project whose name is that street.
    A Public Works job named for a street is not included: the Board does not
    approve its paving or sewers. The caller has already required the two to
    share the street's blocks (or, with no blocks, the street): street_grade's
    STRONG or PROBABLE."""
    title = record.get("title") or ""
    if record.get("kind") != "board" or not _APPROVES_CHANGES.search(title) or _ITEMISED.search(title):
        return False
    if project["source"].startswith("Public Works") or not record.get("streets"):
        return False
    name = re.sub(r"\([^)]*\)", " ", project["name"] or "")
    corridor = record["streets"][0]
    if corridor not in streets(name):
        return False
    # The item names another project as its own.
    m = _NAMES_ITS_PROJECT.search(title)
    if m and not (_stem_list(m.group(1)) and set(_stem_list(m.group(1))) <= set(_stem_list(name))):
        return False
    # The name's words beyond its street and the filler are in the item.
    rest = set(_stem_list(name)) - set(_stem_list(corridor)) - _NAME_FILLER
    return rest <= set(_stem_list(title))


_PAGE_MEETING = (("hearing", re.compile(r"engineering (public )?hearing|public hearing", re.I)),
                 ("board", re.compile(r"board of directors|sfmta board", re.I)))


def title_date(title):
    """The "Month D, YYYY" date a title carries, as YYYY-MM-DD, or None."""
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
                  r"\s+(\d{1,2}),?\s+(\d{4})\b", title or "")
    if not m:
        return None
    return dt.datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat()


def page_meetings(project):
    """The body meetings a project's own sfmta.com page says it went to, by exact date: {(kind, YYYY-MM-DD)}.

    "Engineering Public Hearing Meeting, June 16, 2023" on the Sloat Boulevard
    Quick-Build's page is the department saying the project was heard that
    day. Only events with a whole date; a timeline month ("2025-11 SFMTA Board
    Approved") does not say which meeting."""
    out = set()
    for r in project.get("records") or ():
        if r.get("kind") != "project-page" or r.get("pageBlock") not in ("event", "notice"):
            continue
        d = r.get("date") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            continue
        # A notice counts when its title dates the meeting to the notice's own
        # day: the Brotherhood-Alemany Quick-Build's page files "Engineering
        # Public Hearing Meeting, May 22, 2026" under notices, not events (audit
        # C2, 2026-09-29). A notice dated when it was posted names another day.
        if r.get("pageBlock") == "notice" and title_date(r.get("title")) != d:
            continue
        for kind, rx in _PAGE_MEETING:
            if rx.search(r.get("title") or ""):
                out.add((kind, d))
    return out


# The page-meeting route, widened (audit C4, 2026-09-29). A project's own page
# saying "Board of Directors meeting, June 6, 2023" dates the decision; what the
# route still needs is which item of that meeting is the project's. The street
# rule above finds it when the project is named for a street and the item's
# scope agrees. Three more ways the item shows it is this project's, each
# checked against that one meeting only, never the whole record:
#   - it names the project's own phrase: "29 Sunset" (the Board's 2023-06-06
#     approval "along the western segment of Muni Route 29 Sunset", for the 29
#     Sunset Improvement Project), "no turn on red" (the 2024-03-22 hearing's
#     item for the No Turn on Red Downtown Expansion Project);
#   - it names a project that the page's own events call it by: the Mission /
#     Geneva Safety Project's page lists a "Mission Street Excelsior Safety
#     Project - Open House", and the Board's 2019-09-17 item approves changes
#     "associated with the Mission Street Excelsior Safety Project";
#   - it legislates street work (not a dock, a zone or a meter) on the street
#     the project is named for, whatever the kind: a Slow Street is named for
#     its street ("Page Slow Street" is Page Street), and the 2023-08-18
#     hearing's transit and turn changes on San Jose Avenue are the J Church
#     project on San Jose Avenue's, which its page lists.
# A bike-share dock or a red zone on the street at the same hearing is still
# other work, and an item on some other street is never the project's.
_PAGE_WORK = re.compile(_PROJECT_ACTIONS.pattern + r"|TURN ONLY|FLASHING BEACON|SIDEWALK (WIDENING|EXTENSION)"
                        r"|TRAFFIC ISLAND|MEDIAN|DO NOT ENTER|TRAFFIC MODIFICATIONS"
                        r"|TRAFFIC CALMING|U-TURN|MUST TURN", re.I)
# Words that say what kind of thing a project is rather than which one.
_PHRASE_FILLER = {"project", "projects", "program", "improvement", "improvements", "safety", "phase", "one", "two",
                  "quick", "build", "and", "the", "of", "on", "for", "study", "planning", "plan", "transit",
                  "st", "ave", "blvd", "street", "avenue", "boulevard", "implementation", "refresh", "i", "ii"}
_PAGE_PROJECT = re.compile(r"([A-Z0-9][\w/&'’-]*(?: [A-Z0-9/&][\w/&'’-]*){1,7} (?:Safety |Improvement |Streetscape )?Project)")


def page_phrases(project):
    """Phrases that name this project in another body's item: its own distinctive words, and projects its page's events name."""
    out = set()
    words = norm_name(re.sub(r"\([^)]*\)", " ", project.get("name") or "")).split()
    # The longest run of the name's words that is not filler: "29 sunset",
    # "no turn on red downtown expansion". Two words with a digit (a route)
    # or three words; a single street name is the street rule's business.
    run, runs = [], []
    for w in words + ["project"]:
        if w in _PHRASE_FILLER and not (run and w in ("on", "and") and run[-1] in ("turn", "slow")):
            if run:
                runs.append(run)
            run = []
        else:
            run.append(w)
    for run in runs:
        if len(run) >= 3 or (len(run) == 2 and any(c.isdigit() for c in run[0])):
            out.add(" ".join(run))
            # "no turn on red downtown expansion": the action is its first
            # four words, which is how an order names it.
            if run[:4] == ["no", "turn", "on", "red"]:
                out.add("no turn on red")
        # A Muni route leads a run: "8 bayshore visitacion valley stop" is the
        # 8 Bayshore's, and the Board's 2026-03-17 item approves changes "along
        # the 8 Bayshore Muni route in Visitation Valley" (audit C2). The route
        # is its number and its name, never a number alone.
        if len(run) >= 2 and re.fullmatch(r"\d+[a-z]?", run[0]):
            out.add(" ".join(run[:2]))
    # A project the page's events name counts only when it shares a
    # distinctive word with this project's own name ("mission" in the Mission
    # / Geneva page's "Mission Street Excelsior Safety Project"). Pages list
    # neighbours' events too: the Golden Gate Avenue Quick-Build's page lists
    # the Jones Street Quick-Build's, and that is not its name.
    own = set(words) - _PHRASE_FILLER
    for r in project.get("records") or ():
        if r.get("kind") == "project-page" and r.get("pageBlock") == "event":
            for m in _PAGE_PROJECT.finditer(r.get("title") or ""):
                ph = norm_name(m.group(1))
                if len(ph.split()) >= 3 and ph != norm_name(project.get("name")) and own & set(ph.split()):
                    out.add(ph)
    return out


def named_streets(project):
    """The streets a project is named for, reading "<X> Slow Street" as X Street."""
    s = set(project.get("streets") or ())
    m = re.match(r"^(.+?)\s+slow streets?\b", project.get("name") or "", re.I)
    if m:
        s |= set(streets(m.group(1) + " Street"))
    return s


def named_for(project, street):
    """True when a project is named for this street (a canonical name, "alemany blvd").

    A name can give a street without its suffix: "Brotherhood-Alemany
    Quick-Build Project" is on Brotherhood Way and Alemany Boulevard, "Arguello
    Safety Project" on Arguello Boulevard (audit C2, 2026-09-29). So the street
    also counts when its name without the suffix is the project name's words,
    whole; the suffix then comes from the city's own item, not a guess. A bare
    number ("3rd", "19th") names a street only with its suffix."""
    if street in named_streets(project):
        return True
    parts = street.split()
    base = " ".join(parts[:-1]) if len(parts) > 1 else ""
    if not base or re.fullmatch(r"\d+(st|nd|rd|th)?", base) or base == "the":
        return False
    toks = re.findall(r"[a-z0-9]+", re.sub(r"\([^)]*\)", " ", (project.get("name") or "").lower()))
    want, suffix = base.split(), parts[-1]
    for i in range(len(toks) - len(want) + 1):
        if toks[i:i + len(want)] != want:
            continue
        prv = toks[i - 1] if i else None
        nxt = toks[i + len(want)] if i + len(want) < len(toks) else None
        # A Muni route is not its street: "8 Bayshore" is the bus, not
        # Bayshore Boulevard.
        if prv and re.fullmatch(r"\d{1,2}", prv):
            continue
        # A neighbourhood or place is not its street: "8 Bayshore: Visitacion
        # Valley Stop Improvements" is not named for Visitacion Avenue.
        if nxt in _PLACE_AFTER:
            continue
        # Nor is a longer street that starts or ends with this one's name:
        # "Lake Merced Quick-Build" is Lake Merced Boulevard's, not Lake
        # Street's; "Mission Bay Blvd" is not Bay Street's (Fable review,
        # 2026-09-30).
        if (nxt and longer_street(base + " " + nxt, street)) or (prv and longer_street(prv + " " + base, street)):
            continue
        # A name that is also a neighbourhood's or a place's is the street's
        # only with its suffix written: "Bay Street Road Diet" is Bay
        # Street's, "Bay Corridor" and "Bayview Multimodal" are not.
        if base in _PLACE_NAMES and not (nxt == suffix or SUFFIXES.get(nxt) == suffix):
            continue
        return True
    return False


_PLACE_AFTER = {"valley", "bay", "heights", "park", "district", "hill", "village", "terrace", "point", "shipyard",
                "beach", "island", "square", "plaza", "station", "center", "centre", "yard", "creek", "lake"}
# Street names that are also a neighbourhood's, a district's or a body of water's.
_PLACE_NAMES = {"bay", "bayview", "lake", "sunset", "richmond", "marina", "presidio", "excelsior", "portola",
                "bernal", "glen", "visitacion", "hunters", "candlestick", "treasure", "parkside", "ingleside",
                "merced", "forest", "dogpatch", "central", "hill", "potrero", "tenderloin", "chinatown", "north",
                "south", "east", "west", "outer", "inner", "upper", "lower", "golden"}
_STREET_KEYS = None


def longer_street(words, street):
    """True when a street in the city's centreline other than `street` has a name that starts with `words`
    ("lake merced" -> Lake Merced Boulevard), so a project name holding them is that street's."""
    global _STREET_KEYS
    if _STREET_KEYS is None:
        _STREET_KEYS = sorted((BLOCKS or BlockIndex())._by_street)
    k, own = canon(words), canon(street)
    return any(x.startswith(k) and x != own for x in _STREET_KEYS)


# An engineering hearing item or an SFMTA Board consent item in lettered parts:
# "13(a). ESTABLISH – SPEED HUMP\nSagamore Street, ..." at a hearing, "D.
# ESTABLISH – 15 MPH SPEED LIMIT, Cayuga Avenue between ..." in a Board item's
# text. Each part is its own action on its own places.
_PART_MARK = re.compile(r"(?m)^[ \t]*\d+[A-Za-z]?\s*\([a-z]\)\s*\.\s*"
                        r"|(?<![A-Za-z])[A-Z]\.\s+(?=(?:ESTABLISH|RESCIND|APPROVE|EXTEND|AMEND|REVOKE|DESIGNATE)\b)")
_PART_ACTION = re.compile(r"^\s*(?:ESTABLISH|RESCIND|APPROVE|EXTEND|AMEND|REVOKE|DESIGNATE)\b")


def item_parts(text):
    """An item's lettered parts as [(action, [place, ...])], from its own text; [] when it has none.

    The action is the part's capitalised heading; each place is a line that
    starts a new location ("Alemany Boulevard at Sagamore Street (eastbound
    leg)"), so its first street is the street the part legislates."""
    if not text:
        return []
    chunks = _PART_MARK.split(text)
    out = []
    for c in chunks[1:]:
        m = re.search(r"\b[A-Z][a-z]", c)
        if not m or not _PART_ACTION.match(c[:m.start()]):
            continue
        # A place may carry its own sub-point letter ("B. Cayuga Avenue, ...").
        places = [re.sub(r"^[A-Z]\.\s+", "", x.strip()) for x in re.split(r"\n(?=[A-Z])", c[m.start():]) if x.strip()]
        # A heading can end in the first sub-point's letter ("... (for sidewalk
        # widening) A. Cayuga Avenue"), which is not part of the action.
        action = re.sub(r"\s+[A-Z]\.$", "", re.sub(r"\s+", " ", c[:m.start()]).strip(" ,"))
        out.append((action, places))
    return out


def page_meeting_match(project, record):
    """Evidence that an item of a meeting this project's page lists is the project's own, or None."""
    nblob = record.get("nblob")
    if nblob is None:
        nblob = record["nblob"] = norm_name(record.get("title", "") + " " + record.get("blob", ""))
    # (The route itself, "the project's own page lists this ... on this
    # date", is added to the evidence by link() for every page-meeting match.)
    for ph in sorted(page_phrases(project), key=len, reverse=True):
        if re.search(r"\b%s\b" % re.escape(ph), nblob):
            return ["the item names “%s”" % ph]
    title = record.get("title") or ""
    # The street the item legislates is the first it names; the rest are the
    # cross streets that bound it. "TOW-AWAY, NO STOPPING ANYTIME Townsend
    # Street, south side, from 3rd Street" is Townsend Street's, not 3rd's.
    order = streets_in_order(title)
    if order and named_for(project, order[0]) and page_work(title):
        return ["street work on %s, the street this project is named for" % order[0]]
    # The same rule, part by part, for an item in lettered parts: the item's
    # heading is its first part only ("ESTABLISH – SPEED HUMP Sagamore Street"
    # heads the 2026-05-22 hearing's item 13, whose parts (c) and (e) put
    # flashing beacons and a turn rule on Alemany Boulevard for the
    # Brotherhood-Alemany Quick-Build), and a Board consent item's heading
    # names no street at all ("Approving various routine parking and traffic
    # modifications", 2026-07-21, whose part D is the Cayuga Avenue Slow
    # Street's 15 mph limit). A part counts when its own action is street work
    # and one of its places starts with the street the project is named for.
    for action, places in item_parts(record.get("partsText")):
        if not page_work(action):
            continue
        for place in places:
            o = streets_in_order(place)
            if o and named_for(project, o[0]) and place.lower().startswith(o[0].split()[0]):
                return ["part “%s” is street work on %s, the street this project is named for" % (action, o[0])]
    return None


def phase_base(name):
    """A project's name without its phase: "29 Sunset Improvement Project – Phase Two" is "29 Sunset Improvement Project"."""
    return re.sub(r"[^A-Za-z0-9]+$", "", re.split(r"\bphase\b", name or "", flags=re.I)[0])


def page_work(action):
    """True when an item's action is street work, not a dock, a zone or a meter."""
    return bool(_PAGE_WORK.search(action)) and not (
        _FURNITURE.search(action) and not re.search(r"BIKEWAY|BIKE LANE|CLASS I|TRANSIT|TURN|SPEED", action, re.I))


def link(projects, records, require_district):
    """Attach each record to the projects it plausibly belongs to."""
    heard = {p["id"]: page_meetings(p) for p in projects}
    for r in records:
        rd = set(r["districts"])
        found = []
        for p in projects:
            g, shared = grade(p, r)
            if g not in (EXACT, STRONG, PROBABLE) and (r["kind"], r["date"]) in heard.get(p["id"], ()):
                ev = page_meeting_match(p, r)
                if ev:
                    g, shared = PROBABLE, ev
            if not g:
                continue
            if r.get("pageDay") and g != EXACT and (r["kind"], r["date"]) not in heard.get(p["id"], ()):
                continue
            if require_district and rd and p["districts"]:
                if not (rd & set(p["districts"])):
                    continue
            found.append((p, g, shared))
        # A Public Works page (load_dpw_pages) takes a record that names it,
        # but never away from a feed or SFMTA project that the record also
        # names: the page and the feed row are often one job under two names
        # ("Various Locations Pavement Renovation No. 90 and Sewer
        # Replacement"), and the longer-name rule below would otherwise hand
        # the feed row's award to the page.
        page_ids = ("dpw:", "sfpuc-page:")  # SFPUC's pages (load_puc_pages) the same way
        pages = [x for x in found if x[0]["id"].startswith(page_ids) and x[1] == EXACT]
        if pages and any(g == EXACT for q, g, _ in found if not q["id"].startswith(page_ids)):
            found = [x for x in found if not x[0]["id"].startswith(page_ids)]
        else:
            pages = []
        # A record that names its project in words is about THAT project. The
        # Bayview Community Pathway board item names Third Street, so without
        # this it also links to the 3rd Street Quick-Build and the 3rd Street
        # Transit and Safety Project, which it has nothing to do with.
        # A program named in a record about one of its own projects: "Slow
        # Street treatments on Cayuga Avenue ... Slow Streets-branded signs"
        # names the Slow Streets program and is the Cayuga Avenue Slow
        # Street's own order. When a project on the record's street carries
        # the program's name inside its own, that project is the one.
        # Only a program's: a record that names a project in words goes to
        # that project first. "5th Street Improvement Project" is a project
        # (it is named for a street), so the Board's 2019-09-17 approval of its
        # bike lanes stays with it rather than passing to a Public Works job
        # whose longer name shares its words.
        # A later phase whose own page lists this meeting takes an item that
        # names the project without its phase, when the earlier phase's page
        # does not list it: the SFMTA Board's 2026-05-19 approval names the "29
        # Sunset Improvement Project", which Phase Two's page lists as its
        # "Board of Directors Meeting, May 19, 2026" and Phase One's page (its
        # Board meeting was 2023-06-06) does not (audit C2, 2026-09-29).
        day = (r["kind"], r["date"])
        phased = [x for x in found if x[1] == PROBABLE and day in heard.get(x[0]["id"], ())
                  and any(e[1] == EXACT and day not in heard.get(e[0]["id"], ())
                          and norm_name(phase_base(x[0]["name"])) == norm_name(phase_base(e[0]["name"]))
                          and phase_base(x[0]["name"]) != x[0]["name"] for e in found)]
        if phased:
            found = [(p, g, shared + ["the item names this project without its phase; the earlier phase's page "
                                      "does not list this meeting"]) for p, g, shared in phased]
        instances = [x for x in found if x[1] == STRONG and any(
            is_instance(x[0]["name"], e[2]) for e in found if e[1] == EXACT and is_program(e[0]["name"]))]
        named_ids = {x[0]["id"] for x in instances}
        if instances:
            found = instances
        elif any(g == EXACT for _, g, _ in found):
            found = [x for x in found if x[1] == EXACT]
            # A record naming both a program and one of its projects is about the
            # project: a Harrison/Treat Box Sewer contract names the Folsom Area
            # Stormwater Improvement Project it belongs to, and the project's
            # own name carries the program's initials ("FASIP ...").
            # Only when the record's own title names the project: a contract
            # for the whole program that mentions the project in its text stays
            # with the program.
            head = norm_name(r.get("title"))
            sub = [x for x in found
                   if any(y is not x and names_program(x[0]["name"], y[0]["name"]) for y in found)
                   and any(k in head for k in name_keys(x[0]["name"]))]
            if sub:
                found = sub
            # "Howard Streetscape" is inside "Folsom Howard Streetscape": when
            # one project's name is found only inside another's, the longer
            # name is the one the record is about. Two names found apart are
            # both the record's: the 2023 ordinance on "two agreements ... for
            # the Lower Alemany Area and Folsom Area stormwater projects" is
            # each project's (audit C3b).
            def phrase(x):
                named = [s for s in x[2] if s.startswith("named as")]
                return named[0][len("named as “"):].rstrip("”") if named else ""

            def matched_len(x):
                inside = any(phrase(y) != phrase(x) and phrase(x) and phrase(x) in phrase(y) for y in found)
                return 0 if inside else len(phrase(x)) or 0
            best_ids = {id(x) for x in found if matched_len(x)}
            # Two feed rows for one job ("PW Various Locations Sewer
            # Replacement No 16" and "Joint - Sewer Lead - Various Locations
            # Sewer Replacement No 16 (WW-727)") share their core name. Which
            # of them matched the longer phrase depends only on which carries
            # the contract number, so the record goes to both, and the one
            # the site lists has it.
            def core(x):
                keys = [k for k in name_keys(x[0]["name"]) if not _CODE.fullmatch(k)]
                return keys[0] if keys else None
            cores = {core(x) for x in found if id(x) in best_ids} - {None}
            # A job let jointly with another ("... Sewer Replacement (JV w 8th
            # St, Clay St and Leavenworth St Pavement Renovation)") is named in
            # the record by its partner's name, which the partner's own longer
            # name contains; the one award is both rows'.
            found = [x for x in found if id(x) in best_ids or core(x) in cores
                     or phrase(x) in joint_keys(x[0]["name"])]
        # Two projects can be named after one street — 4th Street Pedestrian
        # Safety and 4th Street Transit Improvement both are — so a hearing
        # item on that street matches both and at most one is right. Nothing
        # in either record can separate them, so both are marked ambiguous
        # rather than one being picked.
        # With blocks on both sides the tie can be broken: the project that
        # shares MORE of the record's blocks is the one it is about, and the
        # others drop to weak. Two projects sharing the same count stay
        # ambiguous, because nothing in the record separates them. Without
        # blocks the name-based rule stands as before.
        found += pages
        rc = set(r.get("cnns") or ())
        by_source = collections.defaultdict(list)
        for x in found:
            if x[1] in (STRONG, PROBABLE):
                by_source[x[0]["source"]].append(x)
        demote = set()
        for src, xs in by_source.items():
            if len(xs) < 2:
                continue
            scored = [(len(rc & set(x[0].get("cnns") or ())), x[0]["id"]) for x in xs]
            best = max(n for n, _ in scored)
            if rc and best > 0 and sum(1 for n, _ in scored if n == best) == 1:
                demote.update(pid for n, pid in scored if n < best)
            else:
                demote.update(pid for _, pid in scored)
                demote.add(("tie", src))
        found2 = []
        for p, g, shared in found:
            # A fourth: the project's own page says it went to this body's
            # meeting that day, and this is that meeting's item on its street
            # for its kind of work (street, scope and the department's date).
            # The page's word settles a tie with another project on the street.
            on_page = (g in (STRONG, PROBABLE) and (r["kind"], r["date"]) in heard.get(p["id"], ()))
            if g in (STRONG, PROBABLE) and p["id"] in demote and not on_page:
                g = WEAK if ("tie", p["source"]) not in demote else AMBIGUOUS
            # A street is not a name. The C3c sample of 2026-09-29 (seed
            # 20260930) graded 0 of 10 street-matched links right: every one was
            # other work on a shared street (Kirkham speed cushions at 20th-46th
            # Aves on the 9th-10th Ave neckdown; a recycled-water rules hearing
            # on a sewer job). So a match on the street alone, however many
            # blocks it shares, is shown as "same street" and never counted as
            # the project's own. Four routes still count: a record naming a
            # program whose instance this project is by name (the instance
            # rule above), a contract award that agrees on streets, kind of
            # work and dates (award_grade), the SFMTA Board approving the work
            # along the street an SFMTA project is named for
            # (board_approves_named), and an item of a meeting the project's
            # own page says it went to (page_meetings).
            # A third: the SFMTA Board approving the work along a street, for
            # the SFMTA project named for that street (board_approves_named).
            if g in (STRONG, PROBABLE) and board_approves_named(p, r):
                shared = shared + ["the SFMTA Board approving work along the street this project is named for"]
            if on_page:
                shared = shared + ["the project's own page lists this %s on this date"
                                   % ("hearing" if r["kind"] == "hearing" else "Board meeting")]
            street_only = (g in (STRONG, PROBABLE) and p["id"] not in named_ids and not r.get("award")
                           and not board_approves_named(p, r) and not on_page)
            if street_only:
                g = SAMESTREET
            found2.append((p, g, shared + (["the street only; the record does not name this project"]
                                           if street_only else []), street_only))
        found = found2
        for p, g, shared, street_only in found:
            # A hearing item in lettered parts shows only the parts naming this
            # project's streets, each with its own outcome (hearing_parts).
            rp = own_parts(p, r)
            p["records"].append({**{k: v for k, v in rp.items()
                                    if k not in ("streets", "blob", "cnns", "nblob", "pageDay", "partsText")
                                    and not (k == "parts" and not (v and isinstance(v[0], str)))},
                                 "recordBlocks": len(r.get("cnns") or ()),
                                 "matchedOn": shared, "grade": g,
                                 "relation": STREETONLY if street_only else relation(p, r, g)})
    for p in projects:
        p["records"] = one_per_vote(p["records"])
        p["records"].sort(key=lambda x: (x["date"], str(x["item"])),
                          reverse=True)
    return projects


GRADE_ORDER = {EXACT: 0, STRONG: 1, PROBABLE: 2}


def vote_key(r):
    """One key per vote: an SFMTA Board item 11 and its sub-items 11A and 11I are one vote.

    The mirror holds the parent item and the keyword extract its lettered
    sub-items, so the 13th Street Safety page listed the 2022-10-18 approval
    three times. Hearing orders and Board of Supervisors files are separate
    acts even on one date, so they keep their own item.
    """
    item = str(r.get("item") or "")
    # An item severed from a consent calendar was not decided by the
    # calendar's single vote, so it is its own vote (SFPUC 2021-07-13 8h).
    if r["kind"] in ("hearing", "supervisors") or r.get("severed"):
        return (r["kind"], r["date"], item.lower(), r.get("title", "")[:80] if not item else "")
    m = re.match(r"^(\d{1,2})(?:[a-z]|\.\d+)?$", item, re.I)
    return (r["kind"], r["date"], m.group(1) if m else item.lower() or r.get("title", "")[:80])


def one_per_vote(records):
    """Keep the best-graded record of each vote; the others' item numbers go in `alsoItems`."""
    groups = collections.OrderedDict()
    for r in records:
        if r["kind"] == "project-page":
            groups[("page", id(r))] = [r]
            continue
        groups.setdefault(vote_key(r), []).append(r)
    out = []
    for rs in groups.values():
        rs.sort(key=lambda r: (GRADE_ORDER.get(r["grade"], 9), 0 if r.get("decision") else 1,
                               0 if not r.get("fromMirror") else 1, -len(r.get("title") or "")))
        best = rs[0]
        others = sorted({str(r.get("item")) for r in rs[1:] if str(r.get("item")) != str(best.get("item"))})
        if others:
            best = dict(best, alsoItems=others)
        # The same vote under another title (the mirror's parent item beside
        # the keyword extract's sub-item): kept so a search for either title
        # finds the vote attached (audit C3b).
        titles = sorted(({r["title"] for r in rs[1:] if r.get("title")}
                         | {t for r in rs for t in r.get("alsoTitles") or ()}) - {best.get("title")})
        if titles:
            best = dict(best, alsoTitles=titles)
        out.append(best)
    return out


TRUSTED = (EXACT, STRONG, PROBABLE)
# Co-located records are reported beside the project, labelled for what they
# are, and never counted toward "this project has its document".


def rate(projects, pred):
    """How many matching projects carry a link worth trusting, and of how many."""
    sel = [p for p in projects if pred(p)]
    got = [p for p in sel
           if any(r["grade"] in TRUSTED for r in p["records"])]
    return len(got), len(sel)


ACTION = [
    ("a bikeshare dock", r"BIKESHARE"),
    ("a bikeway class change", r"CLASS I{1,3}V? BIKEWAY|CLASS IV|BIKE LANE"),
    ("a red or coloured zone", r"RED ZONE|BLUE ZONE|GREEN METERED|YELLOW"),
    ("a parking or stopping rule", r"NO PARKING|NO STOPPING|TOW-AWAY|METERED|LOADING"),
    ("a turn or closure rule", r"DEAD END|TURN|CONTRAFLOW"),
    ("a signal, crossing or hump", r"SIGNAL|CROSSWALK|BEACON|SPEED HUMP|RRFB"),
]


def action_kind(title):
    up = (title or "").upper()
    for label, pat in ACTION:
        if re.search(pat, up):
            return label
    return "something else"


def report(projects, records, unlinked, since, out):
    """Write the markdown a person reads."""
    today = dt.date.today().isoformat()
    graded = collections.Counter(r["grade"] for p in projects
                                 for r in p["records"])
    kinds = collections.Counter(action_kind(r["title"]) for r in unlinked)

    sfmta = [p for p in projects if p["source"].startswith("SFMTA, live")]
    works = [p for p in projects if p["source"].startswith("Public Works, via DotMaps")]
    ask = [p for p in works if p["bike"]]
    onplan = [p for p in works if p["onPlan"]]

    def trusted(ps):
        return [p for p in ps if any(r["grade"] in TRUSTED
                                     for r in p["records"])]

    classes = {}
    if os.path.exists(CLASSES):
        classes = json.load(open(CLASSES, encoding="utf-8")).get("classes", {})
    # `Planned facility` is comma-joined when a job crosses several classes —
    # "Separated, Shared" — so an exact lookup silently scores every one of
    # those as undefined. Split it, and separate "every class it names has a
    # definition" from "some do".
    def facilities(p):
        return [x.strip() for x in (p["plannedFacility"] or "").split(",")
                if x.strip()]

    full, partial, undefined = [], [], collections.Counter()
    for p in onplan:
        fs = facilities(p)
        if not fs:
            continue
        have = [f for f in fs if f in classes]
        for f in fs:
            if f not in classes:
                undefined[f] += 1
        if len(have) == len(fs):
            full.append(p)
        elif have:
            partial.append(p)
    with_quote = full

    def share(got, of):
        return f"**{len(got)} of {len(of)}**" + (
            f" ({100 * len(got) / len(of):.0f}%)" if of else "")

    L = [
        "# Projects, with the city record that documents them",
        "",
        f"Generated {today} by `tools/projects/project-record.py`. **Do not edit this "
        "file by hand — the next run overwrites it.**",
        "",
        "This gives a project one place to stand, whichever record it came "
        "from, and links in what the city has published about it. Two kinds of "
        "project, because an advocate meets both:",
        "",
        f"- **{len(sfmta)} SFMTA projects**, live from its ArcGIS project "
        "layer. These are the bikeways themselves.",
        f"- **{len(works)} Public Works coordinated projects**, the repaving "
        "and utility jobs that will open a street. Public Works publishes no "
        "page for these — the rows come out of an internal system called "
        "DotMaps, which has no public address — so the dataset row is the "
        "whole published record, and that is what the link below reaches. "
        f"{len(ask)} of them sit on the plan's network with nothing published "
        "about bike scope.",
        "",
        "Also matched, by name and contract number only: "
        f"{sum(1 for p in projects if p['source'] == 'SFMTA, a project page not on its map')} SFMTA project "
        f"pages not on its map and {sum(1 for p in projects if p['id'].startswith('dpw:'))} Public Works "
        "project pages in progress, so a row the site lists from one of them carries its record.",
        "",
        "Linked in are the two records that legislate a bikeway: "
        "[engineering hearing orders](../sfmta-hearings/bike-items.md) and "
        "[SFMTA Board items](../sfmta-board/bike-items.md), both read from "
        f"**{since}**, the day the [Biking and Rolling Plan]"
        "(https://www.sfmta.com/projects/biking-and-rolling-plan) was adopted.",
        "",
        "## What a link means depends on which project it is on",
        "",
        "| On | The link says | Why it differs |",
        "| --- | --- | --- |",
        f"| an SFMTA project | *{AUTHORISES}* | the order or minute is the act that built it |",
        f"| a Public Works job | *{SHARES}* | the city has legislated a bikeway on a street this job will dig up. That is worth reading before the paving starts. It is **not** evidence the paving includes the bikeway |",
        "",
        "## How far each link can be trusted",
        "",
        "A street name on its own is not enough. One board item about the "
        "Bayview Community Pathway names Third Street, and 22 projects mention "
        "Third Street somewhere on their page. So every link is graded, and "
        "only the first three grades are counted anywhere in this file. A "
        "match on the street alone is shown as same street and never counted: "
        "a hand-checked sample on 2026-09-29 found none of ten such links "
        "was about its project.",
        "",
        "| Grade | What matched | Links |",
        "| --- | --- | --- |",
        f"| **exact** | the record names the project in words | {graded.get(EXACT, 0)} |",
        f"| **strong** | the record names a program and this project's street, and the project is that program's by name | {graded.get(STRONG, 0)} |",
        f"| **probable** | a contract award on the project's streets for its kind of work, in its dates | {graded.get(PROBABLE, 0)} |",
        f"| *same street, not counted* | the record is on the project's street and does not name the project | {graded.get(SAMESTREET, 0)} |",
        f"| *ambiguous, not counted* | as good as strong, but it matched more than one project of the same kind | {graded.get(AMBIGUOUS, 0)} |",
        f"| *weak, not counted* | the corridor street appears somewhere on the page | {graded.get(WEAK, 0)} |",
        "",
        "Ambiguous is the honest limit. 4th Street Pedestrian Safety and 4th "
        "Street Transit Improvement are both projects on 4th Street, so an "
        "order on 4th Street matches both and at most one is right. Separating "
        "them needs the order's extent geocoded against each project's "
        "geometry, which is the next thing to build.",
        "",
        "## How much of the record a reader can actually reach",
        "",
        "| Question | Answer |",
        "| --- | --- |",
        f"| SFMTA projects carrying a record worth trusting | {share(trusted(sfmta), sfmta)} |",
        f"| Public Works jobs worth asking about that carry one | {share(trusted(ask), ask)} |",
        f"| Every project here that carries a document link of any kind | {share(trusted(projects), projects)} |",
        f"| On-plan jobs where every planned facility has the plan's own written definition | {share(full, onplan)} |",
        f"| On-plan jobs where only some of them do | {share(partial, onplan)} |",
        "",
        "The last two rows are the plan's side rather than the city's. "
        "Separated, Shared and Shared L3 carry a quotable definition. These do "
        "not, and a job that crosses one of them cannot be scored against the "
        "plan at all:",
        "",
        "| Undefined facility | On-plan jobs naming it |",
        "| --- | --- |",
    ] + [f"| {k} | {v} |" for k, v in undefined.most_common()] + [
        "",
        "The plan uses **Undecided** on 32 of Appendix L's 393 rows and never "
        "defines it — the word appears only as a map-legend label. **Car-free** "
        "is one the plan's own Action 2.7.1 promises to define and has not.",
        "",
        "## What the records that match no project are",
        "",
        f"{len(unlinked)} of {len(records)} records attach to no project, and "
        "that is mostly correct rather than a miss: a bikeshare dock or a red "
        "curb is legislated on its own and belongs to no project.",
        "",
        "| The record authorises | Count |",
        "| --- | --- |",
    ]
    for k, v in kinds.most_common():
        L.append(f"| {k} | {v} |")
    L += [
        "",
        "## What this cannot tell you",
        "",
        "- **Whether a completed project was legislated inside this window.** "
        "SFMTA publishes no construction or completion date — the only date on "
        "a project is when somebody last edited its web page, which moves when "
        "a webmaster fixes a typo. So a project finished in 2021 and a project "
        "finished last month are indistinguishable here, and any \"share of "
        "completed projects carrying a record\" computed from this data would "
        "be measuring page edits. That date is the missing input.",
        "- **Whether a linked record is the whole authorisation.** A project is "
        "legislated in several items across several hearings. This finds the "
        "ones it can; it does not know when it has them all.",
        "- **Anything before " + since + ".** Both readers start there.",
        "",
    ]

    amb = {}
    for pr in projects:
        for r in pr["records"]:
            if r["grade"] == AMBIGUOUS:
                amb.setdefault((r["kind"], r["date"], str(r["item"])),
                               {"r": r, "ps": []})["ps"].append(pr["name"])
    if amb:
        L += [
            "## The ambiguous links, to settle by hand",
            "",
            f"{len(amb)} records each match more than one project of the same "
            "kind on the same street. Reading the order's extent against the "
            "projects' limits settles each one in a minute; nothing in the "
            "data does.",
            "",
        ]
        for (_, date, item), v in sorted(amb.items()):
            r = v["r"]
            where = WHERE.get(r["kind"], "hearing item {item}").format(item=item)
            L.append(f"- **{date} — {where}.** [{r['title'][:150]}]({r['url']})")
            L.append("  <br>Matches: " + "; ".join(sorted(v["ps"])))
        L.append("")

    for heading, group, note in (
        ("The SFMTA projects", sfmta,
         "The record below is the act that authorised the project."),
        ("The Public Works jobs", works,
         "The record below is about a street this job will open. Read it "
         "before the paving starts; it does not say the job includes the "
         "bikeway."),
    ):
        got = trusted(group)
        if not got:
            continue
        L += [f"## {heading}", "", note, ""]
        for p in sorted(got, key=lambda x: (x["name"] or "").lower()):
            good = [r for r in p["records"] if r["grade"] in TRUSTED]
            d = ", ".join(str(x) for x in p["districts"])
            L.append(f"### [{p['name']}]({p['page']})")
            L.append("")
            bits = [x for x in (p["phase"], f"District {d}" if d else None,
                                p["plannedFacility"] and
                                f"plan wants {p['plannedFacility']}",
                                p["scope"]) if x]
            if bits:
                L.append(" · ".join(bits))
                L.append("")
            for r in good:
                where = WHERE.get(r["kind"], "hearing item {item}").format(item=r["item"])
                L.append(f"- **{r['date']} — {where}.** "
                         f"[{r['title'][:170]}]({r['url']})")
                line = []
                if r.get("decision"):
                    line.append(r["decision"][:160])
                line.append(f"*{r['grade']} link, on "
                            f"{', '.join(r['matchedOn'])}*")
                L.append("  <br>" + " ".join(line))
            L.append("")

    path = os.path.join(out, "projects.md")
    stable.write_text(path, "\n".join(L) + "\n")
    return path


def site_data(projects, records, unlinked, since, windows, out):
    """A compact file the public site reads, keyed by the id its rows carry.

    The site cannot run this join itself — it would have to parse 33 hearing
    PDFs at build time — so the join is done here and the answer copied across,
    the same way class-definitions.json already is.
    """
    by_id = {}
    for p in projects:
        if not p["id"].startswith("dotmaps:"):
            continue
        good = [r for r in p["records"] if r["grade"] in TRUSTED]
        if not good:
            continue
        by_id[p["id"].split(":", 1)[1]] = [
            {"date": r["date"], "kind": r["kind"], "item": r["item"],
             "title": r["title"][:200], "url": r["url"],
             "decision": (r["decision"] or "")[:160] or None,
             "grade": r["grade"], "matchedOn": r["matchedOn"],
             # Per link, not per file: an engineering order beside a paving job
             # means something different from a Board vacation ordinance, and
             # one sentence at the top of the file cannot say both.
             "means": r["relation"]}
            for r in good]
    payload = {
        "generated": dt.date.today().isoformat(),
        "since": since,
        # One window per source, because they differ and a single date would be
        # wrong for two of the three. The hearings and the SFMTA Board are read
        # from the plan's adoption; the Board of Supervisors is swept by year
        # and reaches further back.
        "windows": windows,
        # Said here so the page cannot render these as authorisation.
        "means": {SHARES: SHARES, LEGISLATES: LEGISLATES},
        "grades": {
            EXACT: "the record names the project in words",
            STRONG: "the record names a program and this project's street, and the project is that program's by name",
            PROBABLE: "a contract award on the project's streets for its kind of work, in its dates",
        },
        "counts": {
            "records": len(records),
            "unmatched": len(unlinked),
            "jobsWithRecord": len(by_id),
        },
        "byDotmapsId": by_id,
    }
    path = os.path.join(out, "site-project-records.json")
    stable.write_json(path, payload, end="", ensure_ascii=True, indent=1)
    # The site builds from site/data alone, so the same bytes go there too;
    # a hand copy fell behind this file (the pipeline rule forbids them).
    if os.path.abspath(out) == os.path.join(ROOT, "out", "project-record"):
        stable.write_json(os.path.join(ROOT, "site", "data", "project-records.json"), payload, end="",
                          ensure_ascii=True, indent=1)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "project-record"))
    ap.add_argument("--min-district-agreement", type=int, default=1,
                    help="0 to link on street name alone")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    global BLOCKS
    BLOCKS = BlockIndex()
    projects, mirror_as_of = load_projects()
    dotmaps = load_dotmaps()
    # A coordinated job's blocks come straight from the feed, which keys on CNN.
    # The whole feed, the same cached pull tools/projects/coordination-projects.py
    # reads: its blocks, its dates, and the description that carries a job's
    # contract number when its name does not ("WD-2921" for the Palou,
    # Quesada and Revere water main).
    feed, rows_by = {}, collections.defaultdict(list)
    for r in fetch(FEED).rows:
        pid = str(r.get("dotmapsid") or "").strip()
        if pid:
            feed.setdefault(pid, set()).update(_feed_cnns(r.get("cnn")))
            rows_by[pid].append(r)
    day = lambda v: str(v or "")[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", str(v or "")) else None
    for d in dotmaps:
        pid = d["id"].split(":", 1)[1]
        rows = rows_by.get(pid, [])
        d["cnns"] = sorted(feed.get(pid, ()))
        d["scopeText"] = " ".join(sorted({(r.get("description") or "").strip() for r in rows} - {"", "NONE", "N/A"}))
        d["start"] = min((day(r.get("start_date")) for r in rows if day(r.get("start_date"))), default=None)
        d["end"] = max((day(r.get("end_date")) for r in rows if day(r.get("end_date"))), default=None)
    projects = projects + load_page_projects(projects) + dotmaps
    projects = projects + load_dpw_pages(projects)
    projects = projects + load_puc_pages(projects)
    own = attach_page_records(projects)
    records = load_records(set().union(*(page_meetings(p) for p in projects)))
    print(f"{own} records taken from the projects' own pages")
    placed = sum(1 for r in records if r.get("cnns"))
    print(f"{placed} of {len(records)} records resolve to blocks; "
          f"{sum(1 for p in projects if p.get('cnns'))} of {len(projects)} projects carry blocks")
    link(projects, records, args.min_district_agreement)
    up_recs, up_meetings = load_upcoming()
    n_up = link_upcoming(projects, up_recs, up_meetings, args.min_district_agreement)
    print(f"{n_up} projects have a meeting not yet held, from {len(up_meetings)} meetings "
          f"and {len(up_recs)} agenda items")

    since =json.load(open(HEARINGS, encoding="utf-8"))["since"]
    windows = {"engineering order": f"since {since}",
               "SFMTA Board": f"since {since}"}
    if os.path.exists(SUPERVISORS):
        years = json.load(open(SUPERVISORS, encoding="utf-8"))["years"]
        windows["Board of Supervisors"] = years
    if os.path.exists(SFPUC):
        rng = json.load(open(SFPUC, encoding="utf-8"))["range"]
        windows["SFPUC Commission"] = f"{rng[0]} to {rng[1]}" if rng else "none"
    # The full mirrors, read by name: each body's own window.
    from lib.mirror import index as mirror_index
    for body, kind, approver in MIRRORS:
        idx = mirror_index(body)
        if idx and idx.get("range"):
            windows[approver + " (every item, by name)"] = f"{idx['range'][0]} to {idx['range'][1]}"


    linked = sum(len(p["records"]) for p in projects)
    print(f"{len(projects)} projects, {len(records)} legislative records, "
          f"{linked} links")
    graded = collections.Counter(r["grade"] for p in projects
                                 for r in p["records"])
    trusted = [p for p in projects
               if any(r["grade"] in TRUSTED for r in p["records"])]
    print(f"  {graded.get(COLOCATED, 0)} co-located — on the project's blocks, about other work; reported, never counted")
    print(f"  {graded.get(EXACT, 0)} exact, {graded.get(STRONG, 0)} strong, "
          f"{graded.get(PROBABLE, 0)} probable — counted; "
          f"{graded.get(AMBIGUOUS, 0)} ambiguous, {graded.get(WEAK, 0)} weak "
          f"— reported, never counted")
    print(f"  {len(trusted)} projects carry a record worth trusting")

    # Only the bike-keyword records are listed when they match nothing. The
    # body mirrors hold every agenda item since 2019 (about 45,000), nearly
    # all of which belong to no street project, and listing them made
    # projects.json 70 MB; they are counted instead.
    linked = {(x["kind"], x["date"], str(x["item"]))
              for p in projects for x in p["records"]}
    keyword = [r for r in records if not r.get("fromMirror")]
    unlinked = [r for r in keyword
                if (r["kind"], r["date"], str(r["item"])) not in linked]
    mirror_unlinked = sum(1 for r in records if r.get("fromMirror")
                          and (r["kind"], r["date"], str(r["item"])) not in linked)
    print(f"  {len(unlinked)} of {len(keyword)} bike-keyword records match no project; "
          f"{mirror_unlinked} of {len(records) - len(keyword)} body-mirror items match none")
    records = keyword

    today = dt.date.today().isoformat()
    stable.write_json(os.path.join(args.out, "projects.json"), {"generated": today, "mirrorAsOf": mirror_as_of,
                   "requireDistrict": bool(args.min_district_agreement),
                   "projects": projects, "unlinkedRecords": unlinked},
                  end="", ensure_ascii=True, indent=1)
    site = site_data(projects, records, unlinked, since, windows, args.out)
    print(f"→ {site}")
    path = report(projects, records, unlinked, since, args.out)
    print(f"→ {path}")


if __name__ == "__main__":
    main()
