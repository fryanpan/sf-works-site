#!/usr/bin/env python3
"""Each coordination-feed job's own page on its department's website, matched by contract number, contract series number or name, with the method and a confidence for every match.

    tools/projects/department-project-pages.py            # harvest (cached) and match
    tools/projects/department-project-pages.py --offline  # match from the cache only
    tools/projects/department-project-pages.py --update   # sitemaps now, pages once a week old
    tools/projects/department-project-pages.py --sample 20  # print a hand-check sample

Writes out/department-pages/pages.json (every department page read) and
out/department-pages/matches.json (one row per feed job, with the page it
matched, how and how sure). tools/projects/coordination-projects.py reads the
matches and links each listed project to its department's page. It also
writes data/extract/sfpuc-projects/projects.json, SFPUC's own project list
(one record per construction-project page, with its phase, dates and blocks),
which tools/projects/coordination-projects.py lists from and the audit's A1-SFPUC
compares the list against.

Why. The Current Projects list linked Public Works jobs 0 of 129 times and
SFPUC jobs 0 of 24 times to a department page, only to the DataSF row
(research/transportation-audit-2026-09/data-quality.md, B1, 2026-09-28). The
earlier join (scripts/dpw-project-join.py) matched on blocks plus shared words
and found that a shared place does not identify a job. This one matches on
what the two records share by construction: a contract number, a contract
series number, or the job's name.

Where each department publishes a page.
  Public Works  https://sfpublicworks.org/projects lists 269 pages
                (data/extract/dpw-projects/projects.json). It publishes more
                than it lists: a contract series has an alias page
                (/VL77 "Various Locations #77 Paving and Sewer Renovations")
                that is not on the list, found by the site's own search
                (/search/node?keys=...) and by trying the alias.
                Its bid portal (https://bidopportunities.apps.sfdpw.org/)
                has a Details page for each contract out to bid, gone once
                awarded. Its paving map (on /street-resurfacing, from
                maps.sfdpw.org Capital_Projects/Paving/MapServer) names every
                paving contract from planning to construction. Paving and
                sewer contracts in design get no page of their own.
  SFPUC         https://www.sfpuc.gov/sitemap.xml lists each page under
                /construction-contracts/construction-projects/. SFPUC Bids On
                Line (https://webapps.sfpuc.org/bids/bidList.aspx) keeps a
                bidDetail page for every construction contract bid since 2013,
                awarded or not; only bids for a contract a feed job carries
                are read.
  SFMTA         every /projects/ page in https://www.sfmta.com/sitemap.xml,
                already read by tools/projects/sfmta-project-pages.py
                (out/sfmta-projects/pages.json).

Kinds of page. "project" is the job's own page; "contract" is its
department's bid page for the job's contract; "program" is a programme page
or as-needed contract that lists many jobs. Only project and contract pages
count as the job's page. A job with neither gets its closest official source
(a programme page, or the paving map's entry for its contract) as `closest`,
labelled as such on the list and never counted as linked.

Methods, strongest first. A match is used for a link only at confidence high
or medium; low ones are written out for review and not linked. At equal
confidence a project page beats a contract page beats a programme page, and
a closer name beats a looser one.
  url        the feed row's own description carries the page's address. high
  contract   a contract number the feed row carries (2410I, WD-2921, WW-779)
             is in the page's address, title or text; a bid page matches
             only its own contract. high
  bid-title  an SFPUC bid page is titled with the job's own numbered
             contract ("As-Needed Spot Sewer Replacement No. 47"), due in the
             three years before the job starts. high
  manager    a Public Works bid page names the feed row's project manager and
             a street the job's name names. high
  series     both are the same numbered contract series ("Various Locations
             Pavement Renovation No 85" and "... No. 85 and Sewer
             Replacement"), and the page names one of the job's streets.
             high. The same number with no shared street is not a match:
             Public Works reuses series numbers across decades.
  section    an SFPUC page has a section headed for the job's place and the
             same kind of work (the Outfall Rehabilitation Projects page's
             "Laguna, Howard, and Mission Creek" section). medium
  name       the job's name and the page's title, with department prefixes
             and filler words taken out, are the same (high), or share at
             least 60% of their distinctive words and a street, and neither
             names a place the other lacks (medium), or share at least half
             their words (low).
A name, series or section match drops to low when the page's latest date is
years before the job starts, or when the page marks its project Completed and
the job has not started.

Incremental. --update re-reads the sitemaps and any cached page over a week
old; it pages through the SFPUC bid list newest first and stops at the first
page that brings nothing new. A failed or short read keeps the last good copy.

Quality checks, run after every fetch; a failure writes nothing, records the
failure in data/pipeline-state/sources.json and exits 2: page floors per
department, at least 250 feed jobs, one row per job, no match without an
address, no row with both a page and a closest source, no page address read
twice, a non-empty paving map when online, and no department's linked count
below 80% of the last run's.

Pages are cached under data/dept-pages-cache/ (gitignored). Staff email
addresses are removed from every text this writes.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from sfdata import fetch  # noqa: E402
from streetnames import streets_in_order  # noqa: E402
from streetindex import canon  # noqa: E402
from lib import pipeline_state, stable  # noqa: E402

CACHE = os.path.join(ROOT, "data", "dept-pages-cache")
OUT = os.path.join(ROOT, "out", "department-pages")
DPW_LIST = os.path.join(ROOT, "data", "extract", "dpw-projects", "projects.json")
SFMTA_PAGES = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")
RECORD = os.path.join(ROOT, "out", "project-record", "projects.json")
FEED = "btxj-k9uh"
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
DPW = "https://sfpublicworks.org"
PUC = "https://www.sfpuc.gov"
SITE_MTA = "https://www.sfmta.com"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

DEPARTMENTS = (("SF MTA", "SFMTA"), ("SF DPW", "Public Works"), ("SF PUC", "SFPUC"))


def department(agency):
    for prefix, name in DEPARTMENTS:
        if (agency or "").startswith(prefix):
            return name
    return None


# ---- fetching -----------------------------------------------------------------

OFFLINE = False
# --update: a sitemap is re-read on every run, so a page the department has
# just published is found the same day; any other copy (a page, or a cached
# 404 that may since have been published) is re-read once it is a week old.
# Neither Public Works nor SFPUC sends Last-Modified or ETag, so age is the
# only change test available.
MAX_AGE_DAYS = None


def get(url):
    """(status, body) for a URL, from the cache unless it is not there yet. A 404 is cached too."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".html")
    stale = (MAX_AGE_DAYS is not None and not OFFLINE and os.path.exists(path)
             and (url.endswith("sitemap.xml") or time.time() - os.path.getmtime(path) > MAX_AGE_DAYS * 86400))
    old = None
    if os.path.exists(path):
        raw = open(path, encoding="utf-8", errors="replace").read()
        status, _, body = raw.partition("\n")
        old = (int(status), body)
        if not stale:
            return old
    # tools/projects/dpw-projects.py already holds the listed Public Works pages,
    # and keeps them current itself under its own --update.
    legacy = os.path.join(ROOT, "data", "dpw-cache", re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".html")
    if os.path.exists(legacy):
        return 200, open(legacy, encoding="utf-8", errors="replace").read()
    if OFFLINE:
        return 0, ""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    status, body = 0, ""
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                status, body = fh.status, fh.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (i + 1))
    time.sleep(1)  # one uncached request a second, to be polite
    if not status and old:
        # The re-read failed; the copy we had is still the best we know.
        return old
    if status:
        open(path, "w", encoding="utf-8").write("%d\n%s" % (status, body))
    return status, body


def flat(markup):
    t = re.sub(r"(?s)<(script|style|nav|header|footer)\b.*?</\1>", " ", markup)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return EMAIL.sub("", re.sub(r"\s+", " ", t)).strip()


def main_text(markup):
    m = re.search(r"(?s)<main\b.*?</main>", markup)
    return flat(m.group(0) if m else markup)


def page_title(markup, suffix):
    h1 = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", markup)
    if h1 and flat(h1.group(1)):
        return flat(h1.group(1))
    t = re.search(r"(?s)<title>(.*?)</title>", markup)
    return flat(t.group(1)).replace(suffix, "").strip(" |") if t else None


# ---- keys a record carries ------------------------------------------------------

CONTRACT = re.compile(r"\b(\d{4}[IJ])\b|\b(W[DW]-\d{3,4}(?:[A-Z]{1,2}\d?)?)\b", re.I)
# A re-advertised contract keeps its number with an R ("WW-727R", and
# "WW-719CR2", the second re-bid of WW-719C); SFPUC's Sewer Upgrades page
# lists WW-727R as WW-727, and Public Works' paving map names the same job
# "... Sewer Replacement No 16 (WW-727)". So a re-bid also carries its base.
REBID = re.compile(r"^(W[DW]-\d{3,4}[A-Z]?)R\d?$")
# A contract let in parts adds a letter ("WD-2922A", part A of WD-2922).
PART = re.compile(r"^(W[DW]-\d{3,4})([A-Z])$")
SERIES_KIND = (
    ("pavement", r"pavement|paving|resurfac"),
    ("sewer", r"sewer"),
    ("curb ramps", r"curb ramp"),
)
SERIES_NUM = re.compile(r"(?:\bNo\.?|#)\s*(\d{1,3}[A-Z]?)\b", re.I)


def contracts(*texts):
    out = set()
    for t in texts:
        for a, b in CONTRACT.findall(t or ""):
            c = (a or b).upper()
            out.add(c)
            if REBID.match(c):
                out.add(REBID.match(c).group(1))
    return out


def series(name):
    """("pavement", "85") for "Various Locations Pavement Renovation No 85"; JV sewer jobs name the paving contract they ride on."""
    out = set()
    n = name or ""
    jv = re.search(r"JV VL PR No\.?\s*(\d{1,3}[A-Z]?)", n, re.I)
    if jv:
        return {("pavement", jv.group(1).upper())}
    if not re.search(r"various locations|\bVL\b", n, re.I):
        return out
    m = SERIES_NUM.search(n)
    if not m:
        return out
    for kind, rx in SERIES_KIND:
        if re.search(rx, n, re.I):
            out.add((kind, m.group(1).upper()))
    return out


FILLER = {"the", "and", "of", "on", "in", "at", "from", "to", "a", "pw", "sfmta", "mta", "sfpuc", "puc",
          "project", "projects", "program", "improvement", "improvements", "phase", "joint", "lead",
          "various", "locations", "location", "no", "contract", "inch", "st", "street", "ave", "avenue",
          "blvd", "boulevard", "dr", "drive", "streets", "avenues", "ductile", "iron", "cast", "for", "with"}


# Words that name a kind of work, not a place, for the name match's place test.
WORK_WORDS = {"new", "traffic", "signal", "signals", "upgrade", "upgrades", "modification", "modifications",
              "sewer", "sewers", "replacement", "replace", "pavement", "paving", "renovation", "rehabilitation",
              "water", "main", "mains", "stormwater", "safety", "streetscape", "pedestrian", "bike", "bicycle",
              "repair", "repairs", "spot", "needed", "as", "large", "diameter", "welded", "steel", "pipe", "pipeline",
              "curb", "ramps", "ramp", "sidewalk", "lighting", "transit", "rapid", "quickbuild", "slow",
              "renewal", "installation", "citywide", "city", "wide", "preservation", "resurfacing"}


def words(s):
    s = (s or "").lower()
    # Contract ids are matched on their own, and pipe sizes ("8-, 12- and
    # 16-inch") say nothing about which project: neither is a name word.
    s = re.sub(r"\(?formerly[^)]*\)?|\bw[dw]-?\d{3,4}\b|\b\d{4}[ij]\b|\b\d{4}-\d{3}\b", " ", s)
    s = re.sub(r"(?:\b\d{1,2}\s*-?\s*(?:,|and|&)?\s*)+-?\s*inch\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bquick build\b", "quickbuild", s)
    return {w for w in s.split() if w not in FILLER}


def street_keys(*texts):
    out = set()
    for t in texts:
        for n in streets_in_order(t or ""):
            k = canon(n)
            if k:
                out.add(k)
    return out


# ---- the three corpora ---------------------------------------------------------

def dpw_page(url, listed=None):
    status, raw = get(url)
    if status != 200 or not raw:
        return None
    title = page_title(raw, "| Public Works")
    if not title or title.lower().startswith(("page not found", "search")):
        return None
    if re.search(r"\bclone\b|^test\b", title, re.I):
        return None  # a CMS placeholder page ("test"), no project's
    text = main_text(raw)
    loc = re.search(r"Location\s+(.{3,160}?)\s+(?:Districts?|Budget|Project Manager|Status)\b", text)
    st = re.search(r"Status\s+(Completed|In progress|In Progress|Planning|Design|Construction)", text)
    # The page's own schedule fields: "Start Summer, 2026 Completion Spring,
    # 2029" (Chinatown Public Health Center, read 2026-09-28).
    # Each is read on its own: VL79's page has a Start ("Winter, 2026") and
    # no Completion (Fable review, 2026-09-30). The fields sit after the
    # page's Districts list, each a season and year followed by the next
    # field's label (Completion, Client, Budget, Project Manager).
    field = r"\b%s\s+([A-Za-z]*,?\s*20\d\d)(?=\s+[A-Z]|\s*$)"
    start, done = re.search(field % "Start", text), re.search(field % "Completion", text)
    return {"department": "Public Works", "url": url, "title": title,
            "start": start.group(1).strip() if start else None, "completion": done.group(1).strip() if done else None,
            "status": (listed or {}).get("status") or (st.group(1) if st else None),
            "location": (listed or {}).get("location") or (loc.group(1) if loc else None),
            "text": text[:6000], "listed": bool(listed), "program": is_program(url, title)}


def dpw_search(keys):
    """Result links from Public Works' own site search."""
    url = DPW + "/search/node?keys=" + urllib.parse.quote(keys)
    status, raw = get(url)
    if status != 200:
        return []
    m = re.search(r"(?s)<main.*?</main>", raw)
    return [(u, flat(t)) for u, t in re.findall(r'(?s)<h3[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', m.group(0) if m else "")]


def puc_pages():
    status, raw = get(PUC + "/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", raw)
    out = []
    for loc in locs:
        path = urllib.parse.urlparse(loc).path
        # A few project pages sit at the site's root rather than under
        # /construction-contracts/ ("Irving Street and Lincoln Way Water
        # Improvements Project - East", read 2026-09-28); those are kept when
        # their title names a project and is not the project's FAQ.
        root = re.match(r"^/[^/]+/?$", path)
        if not root and not re.match(r"^/(construction-contracts/(construction-projects/.+|water-infrastructure-improvements|"
                                     r"sewer-upgrades-renewal-replacement-program|sewer-system-improvement-program)|"
                                     r"projects/.+)$", path):
            continue
        url = PUC + path
        status, body = get(url)
        if status != 200:
            continue
        title = page_title(body, "| SFPUC") or ""
        # The sitemap carries a CMS placeholder ("Clone-project-test", which
        # copies a real page's contract numbers); it is no project's page.
        if re.search(r"\bclone\b|\btest\b", title, re.I):
            continue
        if root and (not re.search(r"\bproject\b", title, re.I) or re.search(r"frequently asked|\bFAQ\b|draft", title, re.I)):
            continue
        out.append({"department": "SFPUC", "url": url, "title": title,
                    "status": None, "location": None, "text": main_text(body)[:6000], "listed": True,
                    "program": is_program(url, title)})
    return out


# ---- SFPUC's own project list ---------------------------------------------------
# data/extract/sfpuc-projects/projects.json: one record per SFPUC
# construction-project page, in the shape of Public Works' list
# (data/extract/dpw-projects/projects.json), so the audit's A1-SFPUC reads it
# the way A1-PW reads Public Works'. Each page prints "Construction Start:",
# "Construction End:" and "Project Phase:" lines (21st Street Water Main
# Replacement Project: October 2026, Summer 2028, Bid & Award; read
# 2026-09-29), and names its streets in its prose ("20th Street from Eureka to
# Collingwood streets"). A page's blocks are the corridors between the limits
# its text names (lib/pw_extent.py); a page naming none takes the
# blocks of the feed jobs matched to it; one with neither is left unplaced.
PUC_EXTRACT = os.path.join(ROOT, "data", "extract", "sfpuc-projects", "projects.json")
# Pages under /construction-projects/ that describe a standing service rather
# than one project, by title: the weekly night-work schedule, sewer cleaning
# and repair, and water main breaks.
PUC_SERVICE_TITLES = {"night work", "sewer cleaning", "sewer repair", "water main breaks"}
PUC_FIELD = re.compile(r"^(Construction Start|Construction End|Project Phase):\s*(.*)$")
# A sentence about another phase or another project is not this page's scope:
# Geary Phase 2's page recounts Phase 1 "from 48th to 32nd avenues", completed
# in 2021; Irving Street East's names the separate project west of Sunset
# (both read 2026-09-29).
PUC_OTHER_WORK = re.compile(r"\bcompleted\b|\bfirst phase\b|\bphase (?:one|1)\b|\bthat phase\b|\bseparate\b|"
                            r"\bfuture project|\bupon completion\b", re.I)
PUC_PLURAL = {"streets": "Street", "avenues": "Avenue", "boulevards": "Boulevard", "ways": "Way", "drives": "Drive"}
_WORD = r"[A-Za-z0-9][\w'’.]*"
PUC_PAREN = re.compile(r"((?:%s[^\S\n]+){0,4}%s)[^\S\n]*\(([^()]+?)[^\S\n]+(?:to|through|-|–)[^\S\n]+([^()]+?)\)" % (_WORD, _WORD))


def puc_limits(lines, ext):
    """The "<street> between/from <a> and/to <b>" clauses a page's lines name that the centreline places.

    Each line is read on its own, so a clause never runs across two. The
    corridor is the fewest words before "between" or "from" that place a
    corridor between the limits (so "Cesar Chavez from Evans Avenue to
    Indiana Street" and "Geary Boulevard between ..." both read); a list
    ending in a plural type ("Palou, Quesada, and Revere avenues between 3rd
    Street and Griffith Street") is one corridor per name; "Howard Street
    (8th Street to 9th Street)" is read as written."""
    out = []

    def named(head):
        """A street name as written: every word capitalised or a number, and a street the centreline has."""
        return bool(head) and all(re.match(r"^[A-Z0-9&]", w) for w in head.split()) and bool(ext.street_key(head))

    def place(clause):
        e = ext.of(clause)
        return e.cnns and e.basis != "corridor only" and "corridor only" not in e.basis

    for line in lines:
        for s in re.split(r"(?<=[.!?])\s+", line):
            if PUC_OTHER_WORK.search(s):
                continue
            for m in PUC_PAREN.finditer(s):
                words = m.group(1).split()
                for k in range(1, len(words) + 1):
                    head = " ".join(words[-k:])
                    c = "%s (%s to %s)" % (head, m.group(2).strip(), m.group(3).strip())
                    if named(head) and place(c):
                        out.append(c)
                        break
            for m in re.finditer(r"\b(?:between|from)\b", s):
                tail = re.split(r"[.;,()]|\s[-–]\s|\s(?:where|with|will|in order)\s", s[m.start():])[0].strip()
                tail = re.sub(r"\s+(?:streets?|avenues?|boulevards?)\s*$", "", tail, flags=re.I)
                if not re.search(r"\b(?:and|to|through)\b", tail):
                    continue
                words = s[:m.start()].rstrip(" ,:").split()
                if words and words[-1].lower() in PUC_PLURAL:
                    # The whole list before a plural type: "Palou, Quesada,
                    # and Revere avenues", not "Revere avenues" alone.
                    j = len(words) - 1
                    while j > 0 and (re.match(r"^[A-Z0-9]", words[j - 1]) or words[j - 1] in ("and", "&")):
                        j -= 1
                    words = words[:j] + [" ".join(words[j:])] if j < len(words) - 1 else words
                for k in range(1, min(8, len(words)) + 1):
                    head = " ".join(words[-k:]).strip(" ,:–-(")
                    plural = re.match(r"^(.*?)\s+(%s)$" % "|".join(PUC_PLURAL), head, re.I)
                    if plural:
                        names = [n.strip() for n in re.split(r",|\band\b", plural.group(1)) if n.strip()]
                        cs = ["%s %s %s" % (n, PUC_PLURAL[plural.group(2).lower()], tail) for n in names]
                        if names and all(re.match(_WORD, n) for n in names) and any(place(c) for c in cs):
                            out += [c for c in cs if place(c)]
                            break
                        continue
                    c = "%s %s" % (head, tail)
                    if named(head) and place(c):
                        out.append(c)
                        # "Lincoln Way and Irving Street between 19th Avenue
                        # and Sunset Boulevard": each street of a pair.
                        rest = words[:-k]
                        if rest and rest[-1].lower() in ("and", "&"):
                            for j in range(1, min(4, len(rest) - 1) + 1):
                                h2 = " ".join(rest[-1 - j:-1]).strip(" ,")
                                if named(h2) and place("%s %s" % (h2, tail)):
                                    out.append("%s %s" % (h2, tail))
                                    break
                        break
    seen = set()
    return [c for c in out if not (c in seen or seen.add(c))]


def page_lines(markup):
    """A page's main text, one line per paragraph, list item or cell."""
    m = re.search(r"(?s)<main\b.*?</main>", markup)
    t = m.group(0) if m else markup
    t = re.sub(r"(?s)<(script|style|nav)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|li|div|h\d|td|tr)>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return [EMAIL.sub("", re.sub(r"\s+", " ", x)).strip() for x in t.split("\n") if x.strip()]


def puc_project_list(pages, matches, record):
    """SFPUC's construction-project pages as a project list with status and blocks."""
    from lib.pw_extent import Extents
    ext = Extents()
    rec_cnns = {p["id"]: set(p.get("cnns") or []) for p in record["projects"]}
    jobs_of = collections.defaultdict(set)
    for m in matches:
        if m.get("url") and m.get("confidence") in ("high", "medium"):
            jobs_of[m["url"]].add(m["id"])
    out = []
    for p in sorted(pages, key=lambda p: p["url"]):
        if p.get("bid") or page_kind(p) != "project" or (p["title"] or "").strip().lower() in PUC_SERVICE_TITLES:
            continue
        status, body = get(p["url"])
        if status != 200:
            continue
        lines = page_lines(body)
        fields = {}
        for i, l in enumerate(lines):
            m = PUC_FIELD.match(l)
            if m:
                fields.setdefault(m.group(1), (m.group(2) or (lines[i + 1] if i + 1 < len(lines) else "")).strip())
        placed = puc_limits(lines, ext)
        jobs = sorted(jobs_of.get(p["url"], ()))
        if placed:
            cnns, basis = sorted(ext.of("; ".join(placed)).cnns), "the corridors between the limits its text names"
        elif jobs:
            cnns = sorted(set().union(*(rec_cnns.get(j, set()) for j in jobs)))
            basis = "the blocks of the coordination-feed jobs matched to it" if cnns else None
        else:
            cnns, basis = [], None
        phase = fields.get("Project Phase") or None
        # The page's own words on what the work is: from "Overview" (or the
        # title) to the first date field, without the contact block.
        start = next((i + 1 for i, l in enumerate(lines) if l == "Overview"), 1)
        words_ = []
        for l in lines[start:]:
            if PUC_FIELD.match(l) or l in ("Details", "Project Background"):
                break
            if not re.match(r"^(contact:|phone\b|mail_outline\b|-->)", l, re.I):
                words_.append(l)
        overview = " ".join(words_)[:600] or None
        slug = urllib.parse.urlparse(p["url"]).path.rstrip("/").rsplit("/", 1)[-1].lower()
        out.append({
            "id": "sfpuc-page:" + slug, "name": p["title"], "url": p["url"], "phase": phase,
            # A page SFPUC keeps under construction projects with no phase is
            # read as in progress; only a phase that says so finishes it.
            "status": "Completed" if phase and re.match(r"^complete", phase, re.I) else "In progress",
            "constructionStart": fields.get("Construction Start") or None,
            "constructionEnd": fields.get("Construction End") or None,
            "location": "; ".join(placed) or None, "cnns": cnns, "cnnsBasis": basis, "feedJobs": jobs,
            "description": overview,
        })
    return out


def is_program(url, title):
    """A page for a programme that lists many contracts, not a page for one project.

    SFPUC's "Sewer Upgrades: Renewal & Replacement Program" lists each sewer
    contract in construction by street and number; it is the closest page
    SFPUC publishes for those contracts, but it is not the job's own page.
    """
    return bool(re.search(r"\bprogram\b", title or "", re.I) or re.search(r"-program\b|water-infrastructure-improvements", url)
                or (title or "").strip().lower() in PROGRAM_TITLES)


# Pages for a whole system or bond, titled without the word "program".
# Public Works' "Emergency Firefighting Water System" page (read 2026-09-28)
# describes the ESER bonds' cisterns, pipelines, tanks and pump stations, so
# it lists "EFWS Fort Mason Manifold Relocation" among many; it is not that
# job's page.
PROGRAM_TITLES = {"emergency firefighting water system",
                  # SFPUC's page on how it replaces water mains each year; it
                  # names no contract (read 2026-09-29).
                  "water main replacement process"}


# ---- Public Works' bid portal ----------------------------------------------------
# Linked from https://sfpublicworks.org/services/contractor-resources as
# "Contracts, Bid Opportunities and Payments Portal". It lists only the
# contracts out to bid now; a contract's Details page is gone once it is
# awarded (Details/2000 to /2600 all 404, read 2026-09-28).
BIDS = "https://bidopportunities.apps.sfdpw.org"


def bid_pages():
    status, raw = get(BIDS + "/")
    if status != 200:
        return []
    out = []
    for path in sorted(set(re.findall(r'href="(/CaseLoad/Details/\d+)"', raw))):
        st, body = get(BIDS + path)
        if st != 200:
            continue
        text = flat(body)
        m = re.search(r"Contract No:\s*(\S+).*?Title:\s*(.*?)\s+(?:Request for|Estimated|Bid Due)", text)
        if not m:
            continue
        out.append({"department": "Public Works", "url": BIDS + path, "title": m.group(2).strip(),
                    "status": "Out to bid", "location": None, "text": text[:6000], "listed": False,
                    "bid": True, "kind": "contract", "bidContract": m.group(1)})
    return out


def page_kind(p):
    """project: the job's own page. contract: the department's page for its contract (a bid page).
    program: a programme page that lists the contract among many."""
    return p.get("kind") or ("program" if p.get("program") else "project")


# ---- SFPUC's Bids On Line ----------------------------------------------------------
# https://www.sfpuc.gov/construction-contracts/contract-opportunities-payments
# links "Contracting Opportunities" to webapps.sfpuc.org/bids. Its construction
# list carries every construction bid SFPUC has posted since 2013 (532 on
# 2026-09-28, oldest DB-124 of 2013), each at bidDetail.aspx?bidid=N with the
# contract number, its title and a project description. Unlike Public Works'
# bid portal, an awarded contract keeps its page. It is a page for one
# contract, so it is the job's page when the feed row carries that number.
PUC_BIDS = "https://webapps.sfpuc.org/bids"
PUC_BID_LIST = os.path.join(CACHE, "sfpuc-bids.json")


def puc_bid_list():
    """[{bidid, contract, title}] for SFPUC's construction bids, newest first.

    The list is paged by ASP.NET postback, ten a page, most recently modified
    first. --update reads from the first page until a page brings nothing new,
    so a run with no new bid reads one page; the listing is the change marker.
    A failed read keeps the copy held.
    """
    held = []
    if os.path.exists(PUC_BID_LIST):
        held = json.load(open(PUC_BID_LIST, encoding="utf-8"))["bids"]
    if OFFLINE or (held and MAX_AGE_DAYS is None):
        return held
    import http.cookiejar
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(data=None):
        req = urllib.request.Request(PUC_BIDS + "/bidList.aspx?bidtype=1",
                                     data=urllib.parse.urlencode(data).encode() if data else None,
                                     headers={"User-Agent": UA})
        with opener.open(req, timeout=60) as fh:
            return fh.read().decode("utf-8", "replace")

    known = {(b["bidid"], b["title"]) for b in held}
    seen, total = {}, None
    try:
        body = post()
        for _ in range(80):
            rows = []
            for bid, inner in re.findall(r'(?s)href="bidDetail\.aspx\?bidid=(\d+)"[^>]*>(.*?)</a>', body):
                title = re.sub(r"\s+Cost:.*$", "", flat(inner)).strip()
                m = re.match(r"^(?:RF[QPB] for\s+)?([A-Z]{2,4}-\d{2,4}(?:\.[A-Z])?(?:[A-Z]{1,2}\d?)?)\b", title)
                rows.append({"bidid": int(bid), "contract": m.group(1) if m else None, "title": title})
            c = re.search(r"(\d+)-(\d+) of (\d+)", flat(body))
            total = int(c.group(3)) if c else total
            fresh = [r for r in rows if (r["bidid"], r["title"]) not in known and r["bidid"] not in seen]
            for r in rows:
                seen[r["bidid"]] = r
            if not rows or (held and not fresh) or (c and c.group(2) == c.group(3)):
                break
            hidden = {n: html.unescape(v) for n, v in
                      re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', body)}
            hidden.update({"__EVENTTARGET": "ctl00$ContentPlaceHolder1$DataPager1$ctl00$NextButton",
                           "__EVENTARGUMENT": ""})
            time.sleep(1)
            body = post(hidden)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print("SFPUC bid list: read failed (%s); keeping the %d bids held" % (e, len(held)), file=sys.stderr)
        return held
    merged = {b["bidid"]: b for b in held}
    new = sorted(set(seen) - set(merged))
    merged.update(seen)
    out = sorted(merged.values(), key=lambda b: -b["bidid"])
    print("SFPUC bid list: %d listed rows read, %d new (%s)" % (len(seen), len(new), ", ".join(map(str, new)) or "none"))
    if total and len(out) < 0.9 * total:
        print("SFPUC bid list: %d read of %d listed; keeping the %d held" % (len(out), total, len(held)), file=sys.stderr)
        return held or out
    stable.write_json(PUC_BID_LIST, {"source": PUC_BIDS + "/bidList.aspx?bidtype=1", "listed": total, "bids": out},
                      indent=0)
    return out


def numbered(name):
    """("as needed spot sewer replacement", "47") for a numbered contract's name or bid title, else None."""
    # The bid list cuts long titles ("... [BID TABULATIO..."); an unclosed
    # bracket is dropped too, so the list's title keys as the detail page's.
    name = re.sub(r"\[[^\]]*$", "", name or "")
    key, num = series_key(name), SERIES_NUM.search(name)
    return (key, num.group(1).upper()) if key and num else None


def puc_bid_pages(job_contracts, job_numbered=()):
    """The bid page of every SFPUC bid whose contract number, or its base, a feed job carries, or whose title is
    the same numbered contract a feed job's name is ("As-Needed Spot Sewer Replacement No. 47")."""
    wanted = set(job_contracts)
    named = set(job_numbered)
    out = []
    for b in puc_bid_list():
        c = (b.get("contract") or "").upper()
        base = {c}
        if REBID.match(c):
            base.add(REBID.match(c).group(1))
        if PART.match(c):
            base.add(PART.match(c).group(1))
        if not (base & wanted) and numbered(b.get("title")) not in named:
            continue
        url = "%s/bidDetail.aspx?bidid=%d" % (PUC_BIDS, b["bidid"])
        st, body = get(url)
        if st != 200:
            continue
        text = flat(body)
        m = re.search(r"Bid Details\s+(.*?)\s+(?:\[|Bid due|Type Construction)", text)
        title = m.group(1).strip() if m else b["title"]
        d = re.search(r"Project Description\s+(.*)", text)
        due = re.search(r"Bid due\s+(\d\d)/(\d\d)/(\d{4})", text)
        out.append({"department": "SFPUC", "url": url, "title": title, "status": "Bid posted", "location": None,
                    "text": (d.group(1) if d else text)[:6000], "listed": False, "bid": True, "kind": "contract",
                    "bidContract": c, "bidDue": "%s-%s-%s" % (due.group(3), due.group(1), due.group(2)) if due else None})
    return out


# ---- Public Works' paving map ------------------------------------------------------
# https://sfpublicworks.org/street-resurfacing embeds "San Francisco Public
# Works Paving Projects" (ArcGIS web map 7c21cacff57c4482a6d435623a186cd2),
# drawn from this service. One row per block or intersection, carrying the
# contract's name, its JO number (the feed's peoplesoft_id), its phase, the
# fiscal year it is projected for and an estimated construction season.
PAVING_PAGE = "https://sfpublicworks.org/street-resurfacing"
PAVING_MAP = "https://maps.sfdpw.org/arcgis/rest/services/Capital_Projects/Paving/MapServer"


def paving_map():
    """One record per contract on Public Works' paving map, with the blocks and intersections it lists."""
    contracts_ = {}
    for layer in (1, 0):  # street segments, then intersections
        st, raw = get("%s/%d/query?where=1%%3D1&returnCountOnly=true&f=json" % (PAVING_MAP, layer))
        n = json.loads(raw).get("count", 0) if st == 200 and raw else 0
        lo = 0
        while lo < n + 1000:
            # The service ignores resultOffset, so it is read in FID windows.
            q = urllib.parse.urlencode({"where": "FID >= %d AND FID < %d" % (lo, lo + 1000), "outFields": "*",
                                        "returnGeometry": "false", "f": "json"})
            st, raw = get("%s/%d/query?%s" % (PAVING_MAP, layer, q))
            lo += 1000
            if st != 200 or not raw:
                continue
            for f in json.loads(raw).get("features", []):
                a = f["attributes"]
                name = (a.get("Project_Na") or "").strip()
                if not name:
                    continue
                jo = (a.get("jo") or "").split("-")[0].strip()
                k = contracts_.setdefault((name, jo), {
                    "contract": name, "jo": jo if jo not in ("_NA", "") else None,
                    "phase": (a.get("Phase") or "").strip() or None,
                    "projectedYear": (a.get("Projected_") or "").strip() or None,
                    "estStart": (a.get("Est_Const_") or "").strip() or None,
                    "estEnd": (a.get("Est_Const1") or "").strip() or None, "cnns": set()})
                if a.get("CNN"):
                    k["cnns"].add(str(a["CNN"]))
    out = []
    for k in sorted(contracts_.values(), key=lambda k: (k["contract"], k["jo"] or "")):
        k["cnns"] = sorted(k["cnns"])
        out.append(k)
    return out


# What each department publishes for a job, read 2026-09-28, for the
# matches file: where a class of job has no page, the closest official source.
PUBLISHED = {
    "Public Works": {
        "projectPages": "https://sfpublicworks.org/projects lists 269 pages, and its search and /VL{n} and "
                        "/{contract} aliases reach more. Paving and sewer contracts get a page only once they are "
                        "in construction; none is published for the paving series in design or planning or for "
                        "Sewer Replacement Nos. 19 to 40.",
        "bidPortal": BIDS + "/ lists only the contracts out to bid now; each has a Details page until it is awarded.",
        "pavingMap": PAVING_PAGE + " embeds Public Works' paving map (" + PAVING_MAP + "), which names every "
                     "paving contract from planning to construction with its JO number, phase, projected fiscal "
                     "year and estimated construction season. It is the closest official source for a paving job "
                     "with no page, and it is a programme map, not the job's page.",
        "projectMap": "https://sfpublicworks.org/project-map shows the same pages as the project list. "
                      "maps.sfdpw.org's Capital_Projects/PW_Projects service was last edited in 2020 and points "
                      "nearly every project at the /projects list.",
    },
    "SFPUC": {
        "projectPages": "https://www.sfpuc.gov/sitemap.xml lists about 68 construction-project pages, the same set "
                        "as the Construction Project Map on /construction-contracts/construction-projects. None is "
                        "published for the WD water-main contracts in design (WD-2877, 2918, 2919, 2934, 2935, "
                        "2936, 2937, the west half of WD-2922) or for the Page Street and Diamond Street mains.",
        "sewerProgram": PUC + "/construction-contracts/sewer-upgrades-renewal-replacement-program lists the sewer "
                        "contracts in construction by street and WW number (WW-709, 720, 727, 729, 730 on "
                        "2026-09-28); a WW contract in design is on no SFPUC page, so this programme page is its "
                        "closest official source, and the same for a Public Works sewer replacement contract in "
                        "the WW series.",
        "waterMains": PUC + "/construction-contracts/construction-projects/water-main-installation-process describes "
                      "the water main replacement SFPUC does each year and names no contract; it is the closest "
                      "official source for a water-main contract in design.",
    },
}


# ---- pages read by hand -----------------------------------------------------------
# A feed job whose own page the matchers above cannot reach, because the page
# names it differently and carries no contract number the feed gives. Each is
# a page read on the date given, with the words on it that make it this job's;
# the page must still be in the harvest, or the row is not linked.
READ_PAGES = {
    # J Muni Forward: Church & Market (TO211 | 10035351). The feed's scope:
    # "a permanent transit island, new 'mini-platform' accessible boarding
    # ramps, pedestrian bulbs ... between the intersections of Duboce
    # Avenue/Church Street and 15th Street/Church Street".
    "61340": ("https://www.sfmta.com/projects/church-and-market-street-intersection-improvements",
              "read 2026-09-29: the page's plan is to “upgrade the transit boarding platform and wheelchair-accessible "
              "platform with permanent materials” at Church and Market and “build a wheelchair-accessible platform on "
              "the existing inbound J Church boarding island at Church and Duboce”, the feed job's scope and blocks"),
    # PW - M & J Lines - Muni Forward Project (TO213), Public Works' contract
    # for the J Church and M Ocean View work on San Jose Avenue and 19th Avenue.
    "25702": ("https://www.sfmta.com/projects/j-church-and-m-ocean-view-transit-and-safety-improvements",
              "read 2026-09-29: the page says “this project will build elements from two approved projects, the J "
              "Church Safety and Accessibility Project and the M Ocean View Transit and Safety Project” and that "
              "“the construction phase of these projects will be combined”, which is this job's M and J lines work"),
    # Joint - Streetscape Lead - Folsom St 10032072, in construction
    # 2024-03-11 to 2026-10-16 on Folsom from 3rd to 10th Street.
    # WD-2921, entered by SFPUC (25811) and by Public Works (36768), "8- and
    # 12-inch Ductile Iron Water Main Replacement on Palou, Quesada, and
    # Revere Ave from 3rd St to Griffith St". Its bid page matched by contract
    # number; SFPUC's project page names no contract number.
    "25811": ("https://www.sfpuc.gov/construction-contracts/construction-projects/palou",
              "read 2026-09-29: SFPUC's Palou, Quesada, and Revere Avenues Water and Sewer Improvements Project page "
              "plans water main upgrades on “Palou, Quesada, and Revere avenues between 3rd Street and Griffith "
              "Street”, the job's contract and limits"),
    "36768": ("https://www.sfpuc.gov/construction-contracts/construction-projects/palou",
              "read 2026-09-29: SFPUC's Palou, Quesada, and Revere Avenues Water and Sewer Improvements Project page "
              "plans water main upgrades on “Palou, Quesada, and Revere avenues between 3rd Street and Griffith "
              "Street”, the job's contract and limits"),
    "8181": ("https://sfpublicworks.org/FolsomSOMA",
             "read 2026-09-29: Public Works' Folsom Streetscape/SOMA page, Location “Folsom Street (2nd St. to 11th "
             "St.)”, in construction; the feed's other Public Works job for the same streetscape (7991, the same "
             "dates) links this page"),
}

# ---- closest official sources read by hand ------------------------------------------
# A Public Works or SFPUC job with no page of its own that programme_source()
# does not reach, and the page each was read against on the date given. Each
# is a programme page, shown as the closest official source and never counted
# as the job's page; the page must be in this run's harvest.
SSIP = PUC + "/construction-contracts/sewer-system-improvement-program"
OUTFALLS = PUC + "/construction-contracts/construction-projects/outfallprojects"
SSIP_LARGE = ("SFPUC's Sewer System Upgrades page (its Sewer System Improvement Program), the programme its sewer capital work is reported under. "
              "It names no large-diameter sewer contract in design; the Wastewater CIP quarterly report it links "
              "(Q4 FY2025-26, read 2026-09-29) counts 25 “R&R Collection Systems - Large Diameter” projects, 15 in "
              "design, without naming them. It does not name this job")
SEWER_RR_DESIGN = ("SFPUC's programme page for sewer renewal and replacement. It lists contracts only once they are in "
                   "construction, by street and WW number, and does not list this one (read 2026-09-29)")
CLOSEST_READ = {
    # Mariposa, Lake Merced and Evans CSD Improvements (2312I)
    "31716": (OUTFALLS, "SFPUC's page for its combined sewer discharge outfall rehabilitation projects. Its section "
                        "“Evans and Mariposa Outfall Improvement Project” (“Status : In construction”, read "
                        "2026-09-29) covers two of this job's three structures. It does not name Lake Merced, which "
                        "SFPUC's Wastewater CIP quarterly report (Q4 FY2025-26) lists with Mariposa and Evans under "
                        "“CSD Structure Rehab & Upgrades - Part 1”"),
    "31497": (SSIP, SSIP_LARGE),  # Various Locations Large Diameter Sewer Improvements No 1 (2500I)
    "52910": (SSIP, SSIP_LARGE),  # Mission District Sewer Rehabilitation (VLLD2B, 2652I)
    "50818": (SSIP, SSIP_LARGE),  # Chinatown and SOMA Large Diameter Sewer Improvements (WW-812, 2620I)
    "61436": (SSIP, SSIP_LARGE),  # Sutter St and Post St Large Diameter Sewer Rehabilitation (2682I)
    "46511": (PUC + "/construction-contracts/sewer-upgrades-renewal-replacement-program", SEWER_RR_DESIGN),  # San Bruno Sewer Replacement and Rehab (2635I)
    "36981": (PUC + "/construction-contracts/sewer-upgrades-renewal-replacement-program", SEWER_RR_DESIGN),  # Monterey Blvd Sewer Replacement (2553I)
    # Westside Force Main Spot Repair: "Replace 50 feet of 48-inch diameter
    # sewer force main at Great Highway/Zoo" (the feed's description).
    "53071": (SSIP, "SFPUC's Sewer System Upgrades page (its Sewer System Improvement Program), the programme its sewer capital work is reported "
                    "under. It does not name this job; the Wastewater CIP quarterly report it links (Q4 FY2025-26, "
                    "read 2026-09-29) names a separate “Westside Force Main Reliability Project”, not this spot "
                    "repair"),
}
# Jobs searched for and found on no official page, with what was searched.
# Written into the matches as `noSource`, so the list says so rather than
# leaving it blank.
NO_SOURCE = {
    "22859": "Public Works' site search for “Sickles” and for its contract 2360I returned no page for this job "
             "(2026-09-29)",
    "52909": "Public Works' site search for “Havelock” returned no page (2026-09-29)",
    "31447": "Public Works' site search for “bike traffic signal” returned only other projects' pages, and no "
             "sfmta.com project page names a bike signal upgrade programme (2026-09-29)",
    "63312": "Public Works' site search for “Bayview Multimodal” returned only the Bayview Transportation "
             "Improvements Project, a different network plan whose environmental review ran from 2004 to 2014, not "
             "this job's bulbouts and signals (2026-09-29)",
    "34913": "Public Works' site search for “trash capture” returned no page, and SFPUC's Sewer System Upgrades "
             "Improvement Program page does not name trash capture; the job is in Port jurisdiction (2026-09-29)",
    "52357": "Public Works' site search for “trash capture” returned no page, and SFPUC's Sewer System Upgrades "
             "Improvement Program page does not name trash capture; the job is in Port jurisdiction (2026-09-29)",
    "11336": "SFPUC's sitemap lists no page for the Northern Waterfront Electrical Improvements (read 2026-09-29), and "
             "its site search answers only in a browser",
}


# ---- programme pages, the closest official source -------------------------------------
# For a Public Works or SFPUC job its department publishes no page for, the
# page of the programme the job belongs to, when the programme's page names or
# maps its contracts. Only these two are used; a job neither covers is left
# with no closest source and listed as such.
#
# SFPUC's Sewer Upgrades: Renewal & Replacement Program lists the sewer
# contracts in construction by street and WW contract number (WW-709, 720,
# 727, 729, 730, read 2026-09-28). Public Works designs and builds these
# contracts: its paving map names "Various Locations Sewer Replacement No 13
# (WW-709)" and "No 16 (WW-727)", and SFPUC's own bid pages title WW-709
# "Various Locations Sewer Replacement No. 13". So the page covers a sewer
# replacement job that carries a WW number, or that belongs to a numbered
# series whose other contracts carry one. Large-diameter sewer, stormwater,
# outfall and CSD work is a different programme and is not covered.
SEWER_PROGRAM = PUC + "/construction-contracts/sewer-upgrades-renewal-replacement-program"
SEWER_WORK = re.compile(r"\bsewer replacement\b|\bsewer re(?:hab|newal)|\bmain sewer\b", re.I)
NOT_SEWER_RR = re.compile(r"large diameter|\bcsd\b|stormwater|trash|outfall|tunnel|pavement|paving", re.I)
# SFPUC's "Water Main Replacement Process" page describes the water main
# replacement it does every year and names no contract; it is the closest page
# SFPUC publishes for a water-main contract in design (WD-2918, 2934, 2936 and
# the rest: no page of their own, read 2026-09-28).
WATER_MAINS = PUC + "/construction-contracts/construction-projects/water-main-installation-process"
WATER_MAIN_WORK = re.compile(r"\bwater main\b", re.I)
WW = re.compile(r"\bWW-\d{3}\b", re.I)
# SFPUC's Westside Enhanced Water Recycling Project brings recycled water from
# the Westside treatment facility to "Golden Gate Park, Lincoln Park Golf
# Course, and other landscaped areas for irrigation" (read 2026-09-29). It is
# the closest page SFPUC publishes for a recycled-water irrigation job with no
# page of its own (Public Works' "Sunset Irrigation Recycled Water", in design).
WESTSIDE_RECYCLED = PUC + "/construction-contracts/construction-projects/westside-enhanced-water-recycling-project"
RECYCLED_WORK = re.compile(r"\brecycled water\b", re.I)


def series_key(name):
    """A numbered contract series without its number, prefix or contract ids: "various locations sewer replacement"."""
    n = re.sub(r"^\s*(?:PW|Joint)\b[^A-Za-z0-9]*(?:[-\w ]+ Lead - )?", "", name or "", flags=re.I)
    # A bid title's bracketed note ("[BID TABULATION]") is not part of the name.
    n = re.sub(r"\([^)]*\)|\[[^\]]*\]|\bW[DW]-\d{3,4}\w*|\b\d{4}[IJ]\b", " ", n, flags=re.I)
    if not SERIES_NUM.search(n):
        return None
    n = SERIES_NUM.sub(" ", n).lower().replace("location ", "locations ")
    return " ".join(re.findall(r"[a-z]+", n)) or None


def programme_source(job, pages, ww_series):
    """(url, title, why) of the programme page that covers a job with no page of its own, or None."""
    name = job["name"]
    if SEWER_WORK.search(name) and not NOT_SEWER_RR.search(name):
        page = pages.get(SEWER_PROGRAM)
        listed = sorted(set(m.upper() for m in WW.findall(page["text"]))) if page else []
        if listed:
            mine = sorted(c for c in job["contracts"] if c.startswith("WW-"))
            kin = ww_series.get(series_key(name)) or []
            # The series' own evidence, preferring a contract the page lists.
            kin = sorted(kin, key=lambda k: (k[1] not in listed, k[1]))
            if mine:
                how = "this job is contract %s" % mine[0]
            elif kin:
                how = "this job is in the same contract series as %s, which is %s%s" % (
                    kin[0][0], kin[0][1], " on that page" if kin[0][1] in listed else "")
            else:
                how = None
            if how:
                return (SEWER_PROGRAM, page["title"],
                        "SFPUC's programme page for sewer replacement contracts. It lists the ones in construction by "
                        "WW number (%s), and not this one yet: %s" % (", ".join(listed[:6]), how))
    if WATER_MAIN_WORK.search(name) and (job["department"] == "SFPUC" or any(c.startswith("WD-") for c in job["contracts"])):
        page = pages.get(WATER_MAINS)
        if page:
            return (WATER_MAINS, page["title"],
                    "SFPUC's page on the water main replacement it does each year; it names no contract, and "
                    "SFPUC publishes no page for this one")
    if RECYCLED_WORK.search(name):
        page = pages.get(WESTSIDE_RECYCLED)
        said = page and re.search(r"[^.]*\brecycled water\b[^.]*\birrigation\b[^.]*\.", page["text"], re.I)
        if said:
            return (WESTSIDE_RECYCLED, page["title"],
                    "SFPUC's page for the programme that brings recycled water to the west side's irrigation: “%s” "
                    "It does not name this job" % " ".join(said.group(0).split()))
    return None


def sfmta_pages():
    pages = json.load(open(SFMTA_PAGES))["pages"]
    out, seen = [], set()
    # Two layer projects can share one page (nodes 1138 and 27619 are both
    # /projects/shotwell-slow-street); the page is matched once.
    for r in sorted(pages.values(), key=lambda r: int(r["node"]) if str(r["node"]).isdigit() else 0):
        if (r.get("canonical") or r["page"]) in seen:
            continue
        seen.add(r.get("canonical") or r["page"])
        # A page whose canonical is another department's (Better Market Street
        # names sfpublicworks.org/bettermarketstreet, which Public Works began
        # listing in September 2026) keeps its sfmta.com address here, so the
        # one address is not read as two departments' pages.
        url = r.get("canonical") or r["page"]
        if not url.startswith(SITE_MTA):
            url = r["page"]
        out.append({"department": "SFMTA", "url": url, "alt": r["page"],
                    "title": r.get("title") or r.get("name"), "status": r.get("phase"), "location": None,
                    "text": (r.get("pageText") or "")[:6000], "listed": True, "node": r["node"],
                    "onLayer": r.get("on_layer")})
    return out


# ---- matching ------------------------------------------------------------------

DATA_YEAR = None  # the year the coordination feed was read; set in main()

def match_job(job, pages):
    """The best page for one feed job, as (page, method, confidence, detail), or None."""
    best = None

    def offer(p, method, conf, detail, kind=None, score=0.0):
        nonlocal best
        # A page whose every date is years before the job starts is an earlier
        # project on the same street: "Bush Street Pavement Renovation Project,
        # Phase One" was built in 2010. A contract number or a URL the feed
        # gives still holds; a name or series match drops to low.
        if method in ("name", "series", "section") and conf != "low" and job.get("startYear") and p["department"] != "SFMTA":
            years = [int(y) for y in re.findall(r"\b(20[0-4]\d)\b", p["text"]) if int(y) <= DATA_YEAR + 10]
            if years and max(years) < job["startYear"] - 2:
                conf, detail = "low", detail + "; but the page's latest date, %d, is years before the job's start, %d" % (
                    max(years), job["startYear"])
            # A page Public Works marks Completed is not the page for a job
            # that has not started: "Chinatown Health Center" (Completed,
            # accessibility work) is not the feed's future job at the clinic.
            elif (p.get("status") or "").lower() == "completed" and job["startYear"] > DATA_YEAR:
                conf, detail = "low", detail + "; but the page marks its project Completed and the job starts in %d" % (
                    job["startYear"])
        # At the same confidence, the job's own project page beats a page for
        # its contract, which beats a programme page that lists it.
        kind = kind or page_kind(p)
        rank = ({"high": 3, "medium": 2, "low": 1}[conf] * 10 + {"project": 3, "contract": 2, "program": 1}[kind], score)
        if best is None or rank > best[4]:
            best = (p, method, conf, detail, rank, kind)

    for p in pages:
        hay = " ".join([p["url"], p.get("alt") or "", p["title"] or "", p["text"]])
        # url: the feed row names the page
        for u in job["urls"]:
            if u.rstrip("/").lower() in (p["url"].rstrip("/").lower(), (p.get("alt") or "").rstrip("/").lower()):
                offer(p, "url", "high", "the feed row's description gives this address")
        # contract number
        path_alias = urllib.parse.urlparse(p["url"]).path.rsplit("/", 1)[-1].upper()
        for c in job["contracts"]:
            if p.get("bid"):
                # A bid page is one contract's page: its own number must be
                # the job's. Its text often names a related contract (the
                # WW-719CR page names WW-719D), which is not a match.
                if c in contracts(p.get("bidContract") or ""):
                    # An as-needed contract is let once and used at many
                    # places ("San Miguel St Customer Service Changeover" is
                    # done under WD-2819 As-Needed Water Main Replacement), so
                    # its page is the job's only when the job is the contract.
                    blanket = (re.search(r"as.needed", p["title"] or "", re.I)
                               and not re.search(r"as.needed", job["name"], re.I))
                    offer(p, "contract", "high", "the page is contract %s's bid%s" % (
                        p["bidContract"], ", an as-needed contract the job is done under" if blanket else ""),
                        kind="program" if blanket else None)
            elif c == path_alias or re.search(r"\b%s\b" % re.escape(c), hay, re.I):
                offer(p, "contract", "high", "contract %s is on the page" % c)
            part = PART.match(p.get("bidContract") or "")
            if part and part.group(1) == c:
                # "WD-2922A" is one part of WD-2922, which the feed enters as
                # two jobs; the page must name the job's own streets as well,
                # and every street the job's name bounds it by: the west half,
                # "Lincoln Way from Sunset to La Playa", is not part A, which
                # runs "from Sunset Blvd. to 19th Ave.".
                pstreets = street_keys(p["title"], p["text"][:4000])
                missing = name_bounds(job["name"]) - pstreets
                if not missing and (len(job["streets"] & pstreets) >= 2 or job["streets"] and job["streets"] <= pstreets):
                    offer(p, "contract", "medium", "the page is %s, part %s of the job's contract %s, and names %s" % (
                        p["bidContract"], part.group(2), c, ", ".join(sorted(job["streets"] & pstreets)[:4])))
                else:
                    offer(p, "contract", "low", "the page is %s, part of %s, but %s" % (
                        p["bidContract"], c, "never names %s, which bounds the job" % ", ".join(sorted(missing))
                        if missing else "names too few of the job's streets"))
        # bid title: an SFPUC bid page whose title is the job's own numbered
        # contract. Public Works builds SFPUC's as-needed sewer contracts and
        # enters them in the feed under its own number (2533I), so the job
        # carries no WW number; the bid is titled with the same name and
        # series number ("WW-783 As-Needed Spot Sewer Replacement No. 47",
        # feed job "PW As Needed Spot Sewer Replacement No 47", read
        # 2026-09-29). Series numbers are reused over the years, so the bid
        # must be due in the three years before the job starts.
        if p.get("bid") and p["department"] == "SFPUC" and p.get("bidDue") and job.get("startYear"):
            mine = numbered(job["name"])
            if mine and mine == numbered(p["title"]) and job["startYear"] - 3 <= int(p["bidDue"][:4]) <= job["startYear"]:
                offer(p, "bid-title", "high", "the bid is titled with the job's own contract name and number, “%s”, "
                      "and was due %s, within the three years up to the job's %d start" % (p["title"], p["bidDue"], job["startYear"]))
        # manager: a Public Works bid page names its project manager, and so
        # does the feed row. The same manager and a street both names is the
        # same job under a new title ("Visitacion Avenue Streetscape Project"
        # went out to bid as "Visitacion Avenue Pedestrian and Bicycle Safety
        # Improvements Project").
        if p.get("bid") and p["department"] == "Public Works" and job["managers"]:
            pm = any(re.search(r"Project Manager\s+%s\b" % re.escape(m), p["text"], re.I) for m in sorted(job["managers"]))
            shared = street_keys(job["name"]) & street_keys(p["title"])
            if pm and shared:
                offer(p, "manager", "high", "the bid names the feed row's project manager, and both name %s"
                      % ", ".join(sorted(shared)))
        # contract series
        pser =series(p["title"]) | series(path_alias.replace("VL", "Various Locations No ") if path_alias.startswith("VL") else "")
        if path_alias.startswith("VL") and not pser:
            num = path_alias[2:]
            for kind, rx in SERIES_KIND:
                if re.search(rx, p["title"] + " " + p["text"][:1500], re.I):
                    pser.add((kind, num))
        shared_series = job["series"] & pser
        if shared_series and p.get("bid") and p["department"] == "Public Works":
            # A bid page is the contract out to bid now, so a reused series
            # number from an earlier decade cannot be what it names.
            offer(p, "series", "high", "same contract series %s No. %s, and the page is that contract out to bid now" % (
                sorted(shared_series)[0][0], sorted(shared_series)[0][1]))
        elif shared_series:
            pstreets = street_keys(p["location"] or "", p["text"][:4000])
            if job["streets"] & pstreets:
                offer(p, "series", "high", "same contract series %s No. %s, and the page names %s" % (
                    sorted(shared_series)[0][0], sorted(shared_series)[0][1], ", ".join(sorted(job["streets"] & pstreets)[:3])))
            else:
                offer(p, "series", "low", "same series number, but the page names none of the job's streets")
        # name
        jw, pw = job["words"], words(p["title"])
        if jw and pw:
            inter = jw & pw
            jac = len(inter) / len(jw | pw)
            # A shared place: a street both names, or, when the job names no
            # street, a shared word that is not a kind of work. "Contract 35
            # Traffic Signal Upgrade" and "Gough Street Traffic Signal Upgrade"
            # share only the work.
            jstreets = street_keys(job["name"])
            same_place = (bool(jstreets & street_keys(p["title"])) if jstreets
                          else bool({w for w in inter if not w.isdigit()} - WORK_WORDS))
            # Numbers are contract and series ids: "Contract 66" is not "Contract No. 65".
            jn, pn = {w for w in jw if re.match(r"^\d+[a-z]?$", w)}, {w for w in pw if re.match(r"^\d+[a-z]?$", w)}
            same_numbers = jn == pn or not (jn and pn)
            # A numbered series job ("Various Locations No 71B ...") is matched
            # by its number; an unnumbered page is a different contract.
            if job["series"] and not pn:
                same_numbers = False
            # Shared streets alone are not tried: they name a place, not a
            # project ("7th St, 8th St and Folsom St Pavement Renovation" is
            # not "19 Polk on 7th and 8th Streets").
            # Each name naming a place the other lacks is two places:
            # "PW Oceanside Treatment Plant Construction" is not
            # "Construction at the Southeast Treatment Plant".
            two_places = bool(place_words(job["name"]) - pw) and bool(place_words(p["title"]) - jw)
            if jw == pw:
                offer(p, "name", "high", "same name once filler words are dropped")
            elif jac >= 0.6 and same_place and same_numbers and not two_places:
                offer(p, "name", "medium", "names share %d of %d distinctive words (%s)" % (
                    len(inter), len(jw | pw), ", ".join(sorted(inter))), score=jac)
            elif jac >= 0.5:
                offer(p, "name", "low", "names share %d of %d distinctive words" % (len(inter), len(jw | pw)), score=jac)
        # streets: the page's title names two or more of the job's streets,
        # both are the same kind of work, and every street the job's name
        # bounds it by ("from 3rd St to Griffith St") is on the page. "Palou,
        # Quesada, and Revere Avenues Water and Sewer Improvements Project" is
        # WD-2921's page; the kind test keeps "19 Polk on 7th and 8th Streets"
        # off a 7th and 8th Street repave, and the bounds keep the east half
        # of the Lincoln Way water work off the west half's job.
        # The streets are those the job's own name gives, never every street
        # its rows touch: a Various Locations job's rows run on dozens of
        # streets, and any page naming two of them would match
        # ("Various Locations Sewer Replacement No 29" is not the Fulton and
        # Grove page).
        if p["department"] != "SFMTA" and not job["series"]:
            tstreets = street_keys(p["title"] or "")
            both = street_keys(job["name"]) & tstreets
            kinds = work_kinds(job["name"]) & work_kinds(p["title"])
            if len(both) >= 2 and kinds:
                missing = name_bounds(job["name"]) - street_keys(p["title"] or "", p["text"])
                if missing:
                    offer(p, "streets", "low", "the title names %s, but the page never names %s, which bounds the job"
                          % (", ".join(sorted(both)), ", ".join(sorted(missing))))
                else:
                    offer(p, "streets", "medium", "the title names %s, the same %s work, and the page names the job's bounds"
                          % (", ".join(sorted(both)), " and ".join(sorted(kinds))))
        # section: SFPUC gives some projects a section of a shared page, not a
        # page of their own ("Outfall Rehabilitation Projects" carries "Brannan
        # Street and Sansome Street Outfalls Improvement Project" with its own
        # status, schedule and updates). A project name in the page's text
        # that holds every place word of the job's name, and the same kind of
        # work, is the job's section.
        if p["department"] == "SFPUC" and not job["series"] and job["places"] and page_kind(p) == "project":
            for phrase in PROJECT_PHRASE.findall(p["text"]):
                pw_ = place_words(phrase)
                if job["places"] <= pw_ and work_kinds(job["name"]) & work_kinds(phrase):
                    offer(p, "section", "medium", "the page has a section for “%s”, which names %s and the same work"
                          % (phrase.strip(), ", ".join(sorted(job["places"]))))
                    break
        # acronym: the job's name carries an acronym that spells the page's
        # whole title ("FASIP" and "Folsom Area Stormwater Improvement
        # Project"), or, five letters or more, that the page spells out
        # ("PEFWS": "referred to as the Potable Emergency Firefighting Water
        # System" on the Westside Emergency Firefighting Water System page).
        # A shorter one in the text is not enough: "EFWS Fort Mason Manifold"
        # is the existing system, which the Westside page describes too.
        for acr in job["acronyms"]:
            initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", p["title"] or "") if w[0].isupper())
            spelled = re.compile(r"\b" + r"\s+".join("%s[a-z]+" % c for c in acr) + r"\b")
            if initials == acr:
                offer(p, "acronym", "high", "%s spells the page's title" % acr)
            elif len(acr) >= 5 and spelled.search(p["text"]):
                offer(p, "acronym", "medium", "the page spells out %s as “%s”" % (acr, spelled.search(p["text"]).group(0)))
    return best


WORK_KIND_RX = {"water": r"\bwater\b", "sewer": r"sewer|\bcsd\b|outfall|stormwater",
                "pavement": r"pavement|paving|resurfac", "streetscape": r"streetscape|pedestrian|safety|\bbike\b"}


def name_bounds(name):
    """The streets a job's name bounds it by: "from 3rd St to Griffith St" gives 3rd St and Griffith St."""
    return street_keys(" ".join(re.findall(r"\b(?:from|to|between|and)\s+([A-Z0-9][\w.' ]{2,30}?)"
                                           r"(?=\s+(?:to|and|&|from)\b|,|$)", name or "")))


def work_kinds(name):
    return {k for k, rx in WORK_KIND_RX.items() if re.search(rx, name or "", re.I)}


# A project's name as a page's text gives it: capitalised words ending in
# "Project" ("Evans and Mariposa Outfall Improvement Project").
PROJECT_PHRASE = re.compile(r"((?:[A-Z][\w'/-]*,?\s+(?:(?:and|&|of|the)\s+)?){1,10}(?:Improvements?|Rehabilitation)\s+Project)\b")


def place_words(name):
    """The words of a name that say where, not what: no filler, no kind of work, no numbers, no CSD."""
    return {w for w in words(name) if not w.isdigit() and w not in WORK_WORDS
            and w not in {"csd", "outfall", "outfalls", "improvement", "improvements", "rehabilitation", "sewer",
                          "system", "area", "district", "districts", "project", "and"}}


def acronyms(name):
    """Upper-case initialisms in a job's name ("PEFWS Pipeline Contract B", "FASIP - ..."); contract ids are not ones."""
    return {a for a in re.findall(r"\b([A-Z]{4,6})\b", name or "") if not re.match(r"^(W[DW]|VL|JV|PR)$", a)}


def linked(row):
    """A match that gives the job its own page: its project page or its contract's page, at high or medium."""
    return row.get("confidence") in ("high", "medium") and row.get("pageKind") in ("project", "contract")


def closest_of(row):
    return {"url": row["url"], "title": row["title"], "department": row["pageDepartment"],
            "why": "a programme page that lists the job's contract (%s)" % row["detail"]}


# Floors the harvest must clear before anything is written. A department's
# page count this low means a fetch failed, not that the pages were taken down.
FLOORS = {"Public Works": 250, "SFPUC": 50, "SFMTA": 300}
# SFPUC project pages, service pages and programmes left out: 62 on 2026-09-29.
PUC_LIST_FLOOR = 45


def quality(jobs, corpora, out, paving, puc_list=()):
    """The checks run after every harvest; any failure stops the step before it writes."""
    bad = []
    # SFPUC's project list: a floor, one record per page, required fields.
    if len(puc_list) < PUC_LIST_FLOOR:
        bad.append("SFPUC project list: %d pages, under the floor of %d" % (len(puc_list), PUC_LIST_FLOOR))
    pids = [r["id"] for r in puc_list]
    if len(pids) != len(set(pids)):
        bad.append("SFPUC project list: %d ids, %d unique" % (len(pids), len(set(pids))))
    for r in puc_list:
        if not (r.get("name") and (r.get("url") or "").startswith(PUC) and r.get("status")):
            bad.append("SFPUC project list: %s lacks a name, an sfpuc.gov address or a status" % r.get("id"))
        if r.get("cnns") and not r.get("cnnsBasis"):
            bad.append("SFPUC project list: %s has blocks with no basis" % r["id"])
    for d, n in FLOORS.items():
        if len(corpora[d]) < n:
            bad.append("%s: %d pages read, under the floor of %d" % (d, len(corpora[d]), n))
    if len(jobs) < 250:
        bad.append("%d feed jobs, under the floor of 250" % len(jobs))
    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)) or len(out) != len(jobs):
        bad.append("matches are not one row per feed job (%d rows, %d unique, %d jobs)" % (len(ids), len(set(ids)), len(jobs)))
    for r in out:
        if r.get("confidence") in ("high", "medium") and not (r.get("url") or "").startswith("http"):
            bad.append("%s: a %s match with no address" % (r["id"], r["confidence"]))
        if r.get("closest") and linked(r):
            bad.append("%s: carries both its own page and a closest source" % r["id"])
    urls = collections.Counter(p["url"] for d in corpora for p in corpora[d])
    twice = sorted(u for u, n in urls.items() if n > 1)
    if twice:
        bad.append("%d page addresses read twice: %s" % (len(twice), ", ".join(twice[:5])))
    if not paving and not OFFLINE:
        bad.append("Public Works' paving map returned no contracts")
    # Against the last good run: a department's linked jobs falling by more
    # than a fifth means pages failed to load, not that departments unpublished.
    prev_path = os.path.join(OUT, "matches.json")
    if os.path.exists(prev_path):
        prev = json.load(open(prev_path, encoding="utf-8"))["matches"]
        for d in ("Public Works", "SFPUC", "SFMTA"):
            was = sum(1 for r in prev if r["department"] == d and linked(r))
            now = sum(1 for r in out if r["department"] == d and linked(r))
            if was >= 5 and now < 0.8 * was:
                bad.append("%s: %d jobs linked, down from %d last run" % (d, now, was))
    return bad


def main():
    global OFFLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="read only what is cached")
    ap.add_argument("--sample", type=int, help="print N random high or medium matches to grade by hand")
    ap.add_argument("--update", action="store_true",
                    help="re-read sitemaps, and any cached page over a week old")
    args = ap.parse_args()
    OFFLINE = args.offline
    global MAX_AGE_DAYS
    if args.update:
        MAX_AGE_DAYS = 7

    # The jobs: every feed job the project record carries (the candidates for the
    # Current Projects list), grouped by DotMaps id.
    record = json.load(open(RECORD))
    candidates = {p["id"].split(":", 1)[1] for p in record["projects"] if p["id"].startswith("dotmaps:")}
    feed = fetch(FEED)
    # Years are compared with the year the feed was read, never the wall
    # clock, so a later run over the same data writes the same matches
    # (pipeline/README.md, rule 3).
    global DATA_YEAR
    DATA_YEAR = feed.fetched_on.year
    rows = collections.defaultdict(list)
    for r in feed.rows:
        pid = str(r.get("dotmapsid") or "").strip()
        if pid in candidates:
            rows[pid].append(r)
    jobs = []
    for pid, rs in rows.items():
        r0 = rs[0]
        dept = department(r0.get("agency_name"))
        if not dept:
            continue
        descs = " ".join(sorted({(r.get("description") or "") for r in rs}))
        ids = " ".join(str(r0.get(k) or "") for k in ("peoplesoft_id", "client_contract_id", "external_id"))
        jobs.append({
            "id": pid, "name": r0.get("name") or "", "department": dept, "agency": r0.get("agency_name"),
            "contracts": contracts(r0.get("name"), descs, ids),
            "series": series(r0.get("name")),
            "urls": set(re.findall(r"https?://[^\s,;]+", descs)),
            "streets": {canon(r.get("on_street")) for r in rs if r.get("on_street")} - {""},
            "words": words(r0.get("name")),
            "acronyms": acronyms(r0.get("name")),
            "places": place_words(re.sub(r"^(PW|Joint)\b[^A-Za-z0-9]*(?:[-\w ]+ Lead - )?", "", r0.get("name") or "")),
            "peoplesoft": sorted({str(r.get("peoplesoft_id") or "").split("-")[0] for r in rs} - {"", "_NA", "None", "NONE"}),
            "cnns": {str(r.get("cnn")) for r in rs if r.get("cnn")},
            "managers": {re.sub(r"\s+", " ", str(r.get(k))).strip().lower() for r in rs
                         for k in ("project_manager_name", "owner_name") if r.get(k)},
            "startYear": min((int(r["start_date"][:4]) for r in rs if (r.get("start_date") or "")[:4].isdigit()),
                             default=None),
        })
    print(f"{len(jobs)} feed jobs from the three departments", file=sys.stderr)

    # Public Works: the listed pages, then the search and the aliases.
    listed = {r["url"]: r for r in json.load(open(DPW_LIST))["records"]}
    dpw = {}
    for url, rec in listed.items():
        p = dpw_page(url, rec)
        if p:
            dpw[url] = p
    tried = set()
    for j in jobs:
        if j["department"] not in ("Public Works", "SFPUC"):
            continue
        queries = []
        for kind, num in sorted(j["series"]):
            queries.append({"pavement": "Pavement Renovation No %s", "sewer": "Sewer Replacement No %s",
                            "curb ramps": "Curb Ramps No %s"}[kind] % num)
            queries.append("VL%s" % num)
        queries += sorted(j["contracts"])
        if not j["series"]:
            q = re.sub(r"^(PW|Joint)\b[^A-Za-z0-9]*(?:[-\w ]+ Lead - )?", "", j["name"]).strip(" -")
            queries.append(q[:80])
        for q in queries:
            if q in tried:
                continue
            tried.add(q)
            for u, t in dpw_search(q):
                if not u.startswith(DPW) or re.search(r"/(about|news|search|commission)\b", u, re.I):
                    continue
                if u not in dpw and u.replace("/index.php", "") not in dpw:
                    p = dpw_page(u)
                    if p:
                        dpw[u] = p
        for kind, num in sorted(j["series"]):
            u = DPW + "/VL" + num
            if u not in dpw:
                p = dpw_page(u)
                if p:
                    dpw[u] = p
        for c in sorted(j["contracts"]):
            if re.match(r"^\d{4}[IJ]$", c):
                u = DPW + "/" + c.lower()
                if u not in dpw:
                    p = dpw_page(u)
                    if p:
                        dpw[u] = p
    # One page can answer at several addresses; keep one per title.
    by_title = {}
    for p in dpw.values():
        k = p["title"].lower()
        if k not in by_title or p["listed"]:
            by_title[k] = p
    # and one address can carry two titles over time (a renamed page found
    # once by the list and once by the search); keep one per address too.
    by_url = {}
    for p in sorted(by_title.values(), key=lambda p: (not p["listed"], p["title"])):
        by_url.setdefault(p["url"], p)
    dpw_list = list(by_url.values())
    bids = bid_pages()
    dpw_list += bids
    puc = puc_pages()
    puc_bids = puc_bid_pages({c for j in jobs for c in j["contracts"]}, {numbered(j["name"]) for j in jobs} - {None})
    puc += puc_bids
    mta = sfmta_pages()
    print(f"pages: Public Works {len(dpw_list)} ({sum(1 for p in dpw_list if not p['listed'])} not on its list, "
          f"{len(bids)} on its bid portal), SFPUC {len(puc)} ({len(puc_bids)} bid pages), SFMTA {len(mta)}",
          file=sys.stderr)

    corpora = {"Public Works": dpw_list, "SFPUC": puc, "SFMTA": mta}
    out = []
    for j in sorted(jobs, key=lambda j: j["id"]):
        own = match_job(j, corpora[j["department"]])
        other = None
        if not own or own[2] == "low" or own[5] == "program":
            # A joint job led by another department: its page is the lead's.
            for d, pages in corpora.items():
                if d == j["department"]:
                    continue
                m = match_job(j, pages)
                if m and m[2] != "low" and (other is None or m[4] > other[4]):
                    other = m
        pick = other if other and (not own or other[4] > own[4]) else own
        row = {"id": "dotmaps:" + j["id"], "name": j["name"], "department": j["department"],
               "contracts": sorted(j["contracts"]), "series": sorted("%s %s" % s for s in j["series"])}
        if pick:
            p, method, conf, detail, _, kind = pick
            row.update({"url": p["url"], "title": p["title"], "pageDepartment": p["department"],
                        "pageStatus": p.get("status"), "method": method, "confidence": conf, "detail": detail,
                        "ownDepartment": p["department"] == j["department"], "pageKind": kind})
        out.append(row)

    # Pages read by hand (READ_PAGES): the job's own page, where no matcher
    # above reaches it. The page must be in this run's harvest.
    by_url = {p["url"].rstrip("/"): p for d in corpora for p in corpora[d]}
    for j, row in zip(sorted(jobs, key=lambda j: j["id"]), out):
        # A page read by hand replaces a bid page: the job's own project page
        # beats its contract's page.
        if j["id"] not in READ_PAGES or (linked(row) and row.get("pageKind") == "project"):
            continue
        url, evidence = READ_PAGES[j["id"]]
        p = by_url.get(url.rstrip("/"))
        if p is None:
            print("read page for job %s is not in the harvest: %s" % (j["id"], url), file=sys.stderr)
            continue
        row.update({"url": p["url"], "title": p["title"], "pageDepartment": p["department"],
                    "pageStatus": p.get("status"), "method": "read", "confidence": "high", "detail": evidence,
                    "ownDepartment": p["department"] == j["department"], "pageKind": "project"})

    # A job with no page of its own takes the page of another feed job that
    # carries the same contract number: SFPUC's WD-2921 and Public Works'
    # "8 & 12-Inch ... Palou, Quesada and Revere" (2562I, WD-2921) are one
    # contract, entered once by each department.
    # A programme page is replaced by a sibling's page for the contract itself.
    by_contract = collections.defaultdict(list)
    for j, row in zip(sorted(jobs, key=lambda j: j["id"]), out):
        for cn in j["contracts"]:
            if linked(row) and row["method"] != "sibling":
                by_contract[cn].append(row)
    for j, row in zip(sorted(jobs, key=lambda j: j["id"]), out):
        if linked(row):
            continue
        sib = None
        for cn in sorted(j["contracts"]):
            pages_ = {s["url"] for s in by_contract.get(cn, ()) if s["id"] != row["id"]}
            # Two jobs on one contract with different pages ("WD-2922" has an
            # east half and a west half) leave a third job's page unknown.
            if len(pages_) == 1:
                sib = next(s for s in by_contract[cn] if s["id"] != row["id"])
                break
        if sib:
            cn = next(c for c in sorted(j["contracts"]) if sib in by_contract.get(c, ()))
            row.update({k: sib[k] for k in ("url", "title", "pageDepartment", "pageStatus", "pageKind")})
            row.update({"method": "sibling", "confidence": "medium",
                        "detail": "shares contract %s with feed job %s (%s), matched by %s" % (cn, sib["id"], sib["name"], sib["method"]),
                        "ownDepartment": sib["pageDepartment"] == j["department"]})

    # Public Works' paving map: the one place Public Works publishes a paving
    # contract before it is built. It is the closest official source for a
    # job with no page, not the job's page, so it is written beside the match.
    paving = paving_map()
    by_jo = collections.defaultdict(list)
    by_pname = {}
    for k in paving:
        by_jo[k["jo"]].append(k)
        by_pname[" ".join(sorted(words(k["contract"])))] = k
    for j, row in zip(sorted(jobs, key=lambda j: j["id"]), out):
        if j["department"] != "Public Works":
            continue
        hit, how = None, None
        for jo in j["peoplesoft"]:
            for k in by_jo.get(jo, ()):
                # A PeopleSoft id is reused across a programme's contracts
                # ("Various Locations Sewer Replacement #21" carries the id
                # the map gives Sewer Replacement No 14), so the series or
                # the blocks must agree too.
                ks = series(k["contract"])
                overlap = len(j["cnns"] & set(k["cnns"])) / max(1, len(j["cnns"]))
                if ({n for _, n in j["series"]} & {n for _, n in ks}) or (not (j["series"] and ks) and overlap >= 0.5):
                    hit, how = k, "PeopleSoft id %s, %d%% of the job's blocks" % (jo, round(100 * overlap))
        if not hit:
            k = by_pname.get(" ".join(sorted(j["words"])))
            if k:
                hit, how = k, "same contract name"
        if hit:
            row["pavingMap"] = {"contract": hit["contract"], "jo": hit["jo"], "phase": hit["phase"],
                                "projectedYear": hit["projectedYear"], "estStart": hit["estStart"], "estEnd": hit["estEnd"],
                                "blocks": len(hit["cnns"]), "matchedBy": how}

    # The series whose contracts carry a WW number: from the feed's jobs, the
    # paving map's contract names and SFPUC's bid titles, each read this run.
    job_of = {"dotmaps:" + j["id"]: j for j in jobs}
    puc_by_url = {p["url"]: p for p in corpora["SFPUC"]}
    ww_series = {}
    for name, ids in sorted([(j["name"], sorted(j["contracts"])) for j in jobs]
                            + [(k["contract"], sorted(contracts(k["contract"]))) for k in paving]
                            + [(p["title"], sorted(contracts(p["title"]))) for p in corpora["SFPUC"] if p.get("bid")]):
        key = series_key(name)
        ww = [c for c in ids if c.startswith("WW-")]
        if key and ww:
            plain = re.sub(r"^\s*(?:PW|Joint)\b[^A-Za-z0-9]*(?:[-\w ]+ Lead - )?|\s*\((?:W[DW]|\d{4}[IJ])[^)]*\)|"
                           r"^\s*W[DW]-\d{3,4}\w*\s*", "", name, flags=re.I).strip()
            if (plain, ww[0]) not in ww_series.setdefault(key, []):
                ww_series[key].append((plain, ww[0]))

    # The closest official source, for a job its department publishes no page
    # for: a programme page that lists its contract, or, for a paving job,
    # Public Works' paving map. Shown on the list apart from the job's own
    # page, and never counted as one.
    for row in out:
        if linked(row):
            # A job linked only by its Public Works bid page loses that page
            # when the contract is awarded (the portal drops it). The source
            # it falls back to is written now, as `fallback`, so the list can
            # carry it beside the bid page and a reader still has an official
            # source the day the bid page goes (review, 2026-09-29).
            if (row.get("url") or "").startswith(BIDS) and row.get("pavingMap"):
                pm = row["pavingMap"]
                row["fallback"] = {"url": PAVING_PAGE, "title": "Public Works paving map", "department": "Public Works",
                                   "why": "the map lists this contract as “%s” (%s%s)" % (
                                       pm["contract"], pm["phase"] or "no phase",
                                       ", projected for %s" % pm["projectedYear"] if pm.get("projectedYear") else "")}
            continue
        if row.get("confidence") in ("high", "medium") and row.get("pageKind") == "program":
            row["closest"] = closest_of(row)
        elif row.get("pavingMap"):
            pm = row["pavingMap"]
            row["closest"] = {"url": PAVING_PAGE, "title": "Public Works paving map", "department": "Public Works",
                              "why": "the map lists this contract as “%s” (%s%s)" % (
                                  pm["contract"], pm["phase"] or "no phase",
                                  ", projected for %s" % pm["projectedYear"] if pm.get("projectedYear") else "")}
        else:
            got = programme_source(job_of[row["id"]], puc_by_url, ww_series)
            jid = row["id"].split(":", 1)[1]
            if not got and jid in CLOSEST_READ:
                url, why = CLOSEST_READ[jid]
                page = puc_by_url.get(url)
                if page is None:
                    print("closest source for job %s is not in the harvest: %s" % (jid, url), file=sys.stderr)
                else:
                    got = (url, page["title"], why)
            if got:
                row["closest"] = {"url": got[0], "title": got[1], "department": "SFPUC", "why": got[2]}
            elif jid in NO_SOURCE:
                row["noSource"] = NO_SOURCE[jid]

    today = feed.fetched_on.isoformat()
    pages_out = sorted(({k: p.get(k) for k in ("department", "url", "title", "status", "location", "listed", "start", "completion")
                         if k in ("department", "url", "title", "status", "location", "listed") or p.get(k)}
                        | {"kind": page_kind(p)} for d in ("Public Works", "SFPUC", "SFMTA") for p in corpora[d]),
                       key=lambda p: (p["department"], p["url"]))
    # Two sfmta.com nodes can share one canonical address (a project page and
    # the node it replaced); the page is read once and listed once.
    seen = set()
    pages_out = [p for p in pages_out
                 if (p["department"], p["url"]) not in seen and not seen.add((p["department"], p["url"]))]
    paving_out = [{k: v for k, v in x.items() if k != "cnns"} | {"blocks": len(x["cnns"])} for x in paving]
    puc_list = puc_project_list(corpora["SFPUC"], out, record)
    failures = quality(jobs, corpora, out, paving_out, puc_list)
    if failures:
        for f in failures:
            print("QUALITY CHECK FAILED: " + f, file=sys.stderr)
        pipeline_state.record("department-pages", "failed", detail="; ".join(failures))
        print("Nothing written; the previous out/department-pages/ stays in place.", file=sys.stderr)
        sys.exit(2)
    changed = stable.write_json(os.path.join(OUT, "pages.json"), {"generated": today, "pages": pages_out}, indent=1)
    changed |= stable.write_json(os.path.join(OUT, "paving-map.json"),
                                 {"generated": today, "source": PAVING_MAP, "page": PAVING_PAGE,
                                  "contracts": paving_out}, indent=1)
    changed |= stable.write_json(os.path.join(OUT, "matches.json"), {
        "generated": today,
        "method": "url, contract number, contract series with a shared street, name, the streets a title names, "
                  "an acronym, or a contract number shared with another feed job; high and medium are linked. "
                  "pageKind project is the job's own page, contract the department's page for its contract "
                  "(a bid page), program a programme page listing it; only project and contract count as "
                  "the job's page, and a job with neither may carry its closest official source",
        "published": PUBLISHED,
        "matches": out}, indent=1)
    changed |= stable.write_json(PUC_EXTRACT, {
        "generated": today,
        "source": PUC + "/sitemap.xml (every construction-project page, under /construction-contracts/construction-projects/ or at the site root)",
        "method": "status from each page's Project Phase line (Completed, or in progress); blocks from the "
                  "corridors between the limits its text names, else from the feed jobs matched to it",
        "records": puc_list}, indent=1)
    pipeline_state.record("department-pages", "changed" if changed else "unchanged",
                          detail="%d pages, %d jobs, %d linked" % (len(pages_out), len(out), sum(map(linked, out))))

    c = collections.Counter((r["department"], r.get("confidence") or "none") for r in out)
    for d in ("SFMTA", "Public Works", "SFPUC"):
        print(d, {k: c[(d, k)] for k in ("high", "medium", "low", "none")})
    print("paving map: %d contracts; %d Public Works jobs found on it" % (len(paving), sum(1 for r in out if r.get("pavingMap"))))
    print(f"→ {os.path.relpath(os.path.join(OUT, 'matches.json'), ROOT)}")

    if args.sample:
        good = [r for r in out if r.get("confidence") in ("high", "medium")]
        random.seed(20260928)
        for r in random.sample(good, min(args.sample, len(good))):
            print(f"- {r['name']} → {r['title']} ({r['pageDepartment']}) [{r['method']}, {r['confidence']}] {r['detail']} {r['url']}")


if __name__ == "__main__":
    main()
