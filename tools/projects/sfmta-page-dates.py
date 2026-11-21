#!/usr/bin/env python3
"""Construction and consultation dates read off every SFMTA, Public Works and SFPUC project page by Claude Opus, re-asked only for pages whose text changed, with a hard $50 stop per run.

    ANTHROPIC_API_KEY="$(security find-generic-password -s <service> -w)" \
        tools/projects/sfmta-page-dates.py --update     # ask about new and changed pages only
    tools/projects/sfmta-page-dates.py --pages departments --update   # the same for Public Works' and SFPUC's pages
    tools/projects/sfmta-page-dates.py --update         # no key: every unchanged page kept; a changed one
                                                 # keeps its last answer and the run is recorded failed
    tools/projects/sfmta-page-dates.py --gold           # score the reader on the round-2 and round-3 answer keys
    tools/projects/sfmta-page-dates.py --node 1136      # show one page's picks in context

Bryan, 2026-09-29, answering: "I'd asked how expensive it was
to run the ground truth gold method on all data. If it's under $50, then let's
just do it. And consider keep doing it for any pages that we detect updates
on." The gold method is Claude Opus reading the whole page with every date
tagged, which replaced TypeSafe's Jev here on 2026-09-30. On this step's own
input (`--gold`, 2026-09-30, over all five fields) it scored 0.95 precision
(56 of 59) and 0.98 recall (51 of 52) on round 3's answer key, and 0.93
(106 of 114) and 0.97 (99 of 102) on round 2's. Jev on the same input
scored 0.97 and 0.96 on round 3 and 0.93 and 0.95 on round 2 (below): the
reader finds more of the stated dates at about the same precision. The first full run cost $1.40 for the keys,
$6.60 for 326 SFMTA pages and $5.15 for 345 Public Works and SFPUC pages.

The reader. One Messages API request per page, raw HTTP with
urllib like every other fetch here (the Anthropic Python SDK needs Python
3.10; the pipeline runs on 3.9). The system prompt and the layout of the user
turn are round 2's Claude method (scripts/typesafe-sfmta-dates-round2.py
claude()), which is how the Opus score above was measured: the marked page,
then one line per question with its definition, then "reply with JSON". Two
changes: each answer carries the reader's confidence, which the flag rule and
the start/end conflict rule below read, and the input is the production
input described next rather than round 2's. `--gold` measures the reader on
exactly this input.

Cost cap. COST_CAP_USD ($50) is a hard stop per calendar day across every
run of this script (both pipeline steps and --gold; Budget below): before
each request its worst case (the prompt's UTF-8 bytes counted as tokens at
half a token a byte, plus MAX_TOKENS of output, at READER's list prices) is
reserved against the cap, and a request whose reservation would take spent
plus reserved past the cap is not sent; its page keeps its last answer and
the run is recorded failed with "cost cap reached". After each response the
reservation is replaced by the cost of the tokens the API reports used.
`--max-cost` lowers the cap for one run; it cannot raise it. Every response
is kept under .cache/page-dates-reader/ (gitignored) by the request's hash,
so a run cut short by the cap, a crash or a failed check does not pay for
them again. A reply that does not parse is paid for and not kept, so its page
is asked again next run.

Everything below about the input, the definitions and the grading rules is
unchanged from the TypeSafe method, which this reader replaced on 2026-09-30.

Input, as scored for Jev: "round 2 best input, round-3 definitions", the method that
scored 0.97 precision and 0.93 recall on 25 fresh pages
(notes/typesafe-trial-2026-09/round-3.md). The input is round 2's
(scripts/typesafe-sfmta-dates-round2.py build()): the page's <main> text with
emails and phone numbers removed, followed by the page's sidebar notice and
meeting cards, with every date-like span marked [[cN|span — label]], where the
label is the timeline stage it sits in, else the line or heading around it.
Jev answers one Choice question per field whose options are the span ids and
`none`, so every answer is a span on the page. The code here is a copy of
round 2's page building, not an import: those trial scripts load
coordination-projects.py, which reads this script's output.

Two changes to that input, each kept because it scored better on both gold
sets (round-2's 50 pages and round-3's 25) than the input without it, in an
experiment of 2026-09-29 that also tried JSON state with named fields and a
cut-down state (both worse on round 2): every question names the project
("…of this project (Valencia Street Bikeway Improvements)"), with the title
in the state's first line and the context, since TypeSafe's docs name
indirection as a weakness (docs.typesafe.ai, model-jaggedness/jev-1.13); and
the text of the notice pages the page links (hearings, outreach) is appended
after the cards: the lines sharing two of the title's keywords, with a line
either side (a title with one keyword gets none). Naming the project made Jev
read a Slow Street's first, COVID-19 response form as another project, so the
start question says an interim version of the same street is this project
(INTERIM below). With the three changes, scored over all five fields, round 3
went from 0.966 precision (56/58) and 0.923 recall (48/52) to 0.967 (58/60)
and 0.962 (50/52); round 2 from 0.917 (100/109) and 0.941 (96/102) to 0.929
(104/112) and 0.951 (97/102). Better Market Street is left out of both, since
its gold was labelled on the page cut at 24,000 characters.

Definitions are round 3's with Bryan's two rules from his round-3 review:
a "Predicted Completion" field counts as the construction end whatever phase
the project is in, since it is the best date the city publishes; and when a
page describes a pilot and names a later build of the project, the pilot's
dates are not the project's construction dates. One sentence is added to the
start and consultation questions: a sentence saying work was completed or
substantially implemented by a date gives an end, not a start or an outreach
date. Jev read "As of the Fall of 2022, the design was substantially
implemented" as Lake Slow Street's start and as Shotwell Slow Street's
consultation; with the sentence it reads neither. The end's "Does not count"
names the end of a planning, design, outreach or approval stage, which kept
Jev off Climate Roadmap's "Fall 2022-Winter 2023 Phase 2 of outreach and Plan
approvals". On the round-3 gold these definitions score what round 3's best
Jev scored: 0.97 precision (60 of 62) and 0.93 recall (51 of 55)
(notes/typesafe-trial-2026-09/round-3.md; scored 2026-09-29).

After the Fable review of the first Opus run (2026-09-30): a project in
phases takes its earliest phase's start and its latest phase's end, and a
building's opening is its construction end (DEFS); a timeline stage whose
date line carries a word ("Starting Fall/Winter 2024") gets its own label
rather than the previous stage's (date_only_line); the page's Predicted
Completion field is applied as the construction end in derive(), with the
reader's pick kept under `jev`; and an unsure `none` on a page that dates a
construction stage is flagged (flags()). The first two change every request,
so every page is asked again on the next run with a key.

Input: data/extract/sfmta-pages/sitemap.json (every /projects/ page in
sfmta.com's sitemap, with its notice and meeting cards, written by
tools/projects/sfmta-project-pages.py --sitemap), each page's raw copy under
data/sfmta-pages/ (gitignored; the same step keeps it current), and a copy of
each linked notice page under .cache/sfmta-notices/ (gitignored), fetched the
first time a page links it and not re-read, since a notice is a dated posting
and a new hearing gets a new one. A notice that cannot be fetched is not
cached; its page keeps its last answer and the run is recorded failed.

Incremental: each page's request (definitions, model, settings and marked
page text) is hashed. A page whose hash matches the one on file keeps its answer and is
not sent; only a new page, a page whose text or cards changed, or a change
to the definitions sends a request. A page with no raw copy keeps its last
answer. Nothing is re-asked on a timer: the page text is the marker, and
sfmta.com's sitemap lastmod decides when the pages step re-reads it.
One thing moves the output without a request: flags() compares each date
with the day the pages were read, so a re-read sitemap can add or clear a
flag and rewrite dates.json and review.md.

Output: out/sfmta-page-dates/dates.json, one entry per sitemap page, sorted,
written through scripts/lib/stable.py. Each field is the span the reader picked,
its label, its confidence, and the date it reads as: `value` at the precision
the page gives ("2025", "2025-04", "2025-04-17"), `first` and `last`, the
period's first and last days, and `iso`, the one of those a field is
compared by (the last day for an end or a consultation, which the definitions ask for as the latest,
the first day for a start). A span that opens a range on its own line ("Fall 2024 - Fall 2025") is read
to the range's close for an end or a consultation, as the definitions' "the last date of its range" says;
`closes` names the closing span. The
dates are worked out from the stored span on every run, so a change to how
a span is read reaches every page without a request. `asked` is the date of the request that answer came
from, so it moves only when the page is re-asked. The file's total cost is
the list price of every answer it holds; the cost of this run is printed.

A page where the reader's end falls before its start drops one of the two, named
under `conflicts`: a timeline stage still marked Pending gives way to a date
the page reports (Anza Street's "06/11/2021: The project is now substantially
complete!" over "Summer 2021 Construction (Pending)"), and otherwise the pick
the reader is surer of stands (Fable review, 2026-09-29).

Each page also carries, read from its raw copy and never sent to the reader,
`projectStatus`, the ticked items of the page's own "Project Status" field
("Implementation / Construction"), which tools/projects/coordination-projects.py reads
as SFMTA's status for a page its layer does not phase; `latestDate`, the last
day of the latest date-like span anywhere on the page, which the checks hold
every kept date to; and `latestStageDate`, the same over spans on a line of
dates alone (a timeline or schedule row), which tells a passed phase end from
a finished project when the page schedules later work.

A person checks what the flag rule (flags()) picks out: a shown date carries
`flags`, the reasons, when the reader's confidence is under 0.45, the page's start
and end could not both hold, SFMTA's phase (its layer's, else the page's
Project Status) contradicts the date, or the date comes from a linked notice
rather than the project page. The confidence line, 0.55, is set from the
reader's answers on both answer keys (above flags()); `--gold` prints how
many picks it flags and how many wrong ones it catches. Flagged picks nobody has checked are
listed in out/sfmta-page-dates/review.md, and tools/projects/coordination-projects.py
notes on the project that the date is unchecked. A person's answer goes in
data/sfmta-page-dates/confirmed.csv (node, field, answer, who, date) and
stands over the reader's on every later run: `confirmed` on the field, and
the reader's own pick under `jev` (the key the schema has always used) when
the answer differs. A person can also give
`consultation_start`, the first workshop or meeting, which the reader is not asked;
tools/projects/coordination-projects.py shows a hand-checked date over every other
reading of the page.

Checks: pipeline/transportation-quality.py, step sfmta-page-dates. They run
right after every run of this script, on what it wrote; a failing check puts
the previous dates.json and review.md back, records the failure under the
step's marker in data/pipeline-state/sources.json and exits 1.

Public Works and SFPUC pages (--pages departments). Bryan, 2026-09-29, on the
Masonic Avenue Streetscape row: "How come this project is missing dates? Did
we run the date extractor on DPW and SFPUC projects as well?" The same method
reads every Public Works and SFPUC project page in
out/department-pages/pages.json (kind "project"; about 410), with three
changes: the state names the department's page rather than SFMTA's; only the
three published fields are asked, since the hearing and approval questions
name SFMTA's own bodies; and a page's phase for the flag rule is its own
Status field. A page has no notices or timeline markup, so the input is its
<main> text alone. The raw copy is the one the fetch steps keep current:
data/dpw-cache/ for a page Public Works lists (tools/projects/dpw-projects.py
--update re-reads each once a week) and data/dept-pages-cache/ for the rest
(tools/projects/department-project-pages.py --update, the same bound); both are
gitignored and hold the whole page, where the tracked extract's description
keeps only its long paragraphs and so drops a schedule such as Masonic's
"Construction phase: July 2016 to Spring 2018." Output
out/dept-page-dates/dates.json in the same shape, keyed by page address;
flagged picks in out/dept-page-dates/review.md; a person's answers in
data/dept-page-dates/confirmed.csv (the page address in `node`). Checks:
step dept-page-dates.

What leaves this machine: the public page text above, to Anthropic's
Messages API (https://docs.anthropic.com/en/api/messages). The key is read
from ANTHROPIC_API_KEY in the environment only; nothing here reads a file of
secrets.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state, seasons, stable  # noqa: E402

PAGES = os.path.join(ROOT, "data", "extract", "sfmta-pages", "sitemap.json")
RAW = os.path.join(ROOT, "data", "sfmta-pages")
OUT = os.path.join(ROOT, "out", "sfmta-page-dates", "dates.json")
REVIEW = os.path.join(ROOT, "out", "sfmta-page-dates", "review.md")
CONFIRMED = os.path.join(ROOT, "data", "sfmta-page-dates", "confirmed.csv")
NOTICES = os.path.join(ROOT, ".cache", "sfmta-notices")  # gitignored copies of the notice pages a project page links
LAYER = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
MARKER = "reader:sfmta-page-dates"
# gitignored; one file per request hash. PAGE_DATES_CACHE moves it, so a test never writes the real one.
RESPONSES = os.environ.get("PAGE_DATES_CACHE") or os.path.join(ROOT, ".cache", "page-dates-reader")

# --pages departments: Public Works and SFPUC project pages.
DEPT_PAGES = os.path.join(ROOT, "out", "department-pages", "pages.json")
DPW_RAW = os.path.join(ROOT, "data", "dpw-cache")         # tools/projects/dpw-projects.py's copies
DEPT_RAW = os.path.join(ROOT, "data", "dept-pages-cache")  # tools/projects/department-project-pages.py's copies
DEPT_OUT = os.path.join(ROOT, "out", "dept-page-dates", "dates.json")
DEPT_REVIEW = os.path.join(ROOT, "out", "dept-page-dates", "review.md")
DEPT_CONFIRMED = os.path.join(ROOT, "data", "dept-page-dates", "confirmed.csv")
DEPT_MARKER = "reader:dept-page-dates"
AGENCY = {"SFMTA": "San Francisco Municipal Transportation Agency", "Public Works": "San Francisco Public Works",
          "SFPUC": "San Francisco Public Utilities Commission"}

# ANTHROPIC_BASE_URL is honoured so the tests can point the step at a local stand-in.
ENDPOINT = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
MODEL = "claude-opus-5-5"  # pinned, so every answer on file names one model
EFFORT = "medium"  # the API's default for this model, set explicitly so a change of default changes nothing here
# Output, thinking included. The answer is under 200 tokens and Opus used at
# most 584 on the 25 trial pages; Sonnet 5 reached 5,068 there, so the bound
# leaves room for a page that makes the model think long.
MAX_TOKENS = 8000
PRICE_IN_PER_MTOK = 4.00   # list price, claude-opus-5-5, uncached input
PRICE_OUT_PER_MTOK = 20.00  # list price, output (thinking is billed as output)
COST_CAP_USD = 50.0  # hard stop: Bryan's "If it's under $50, then let's just do it" (2026-09-29)
# Round 1 capped the text at 24,000 characters. Better Market Street's page
# runs to 52,316, and the cut hid its last two years of updates (Fable
# review, 2026-09-29). No other page reaches 24,000.
MAX_CHARS = 60000
MAX_CANDIDATES = 254  # kept from the TypeSafe method, whose Choice question took 255 options, so ids do not move
WORKERS = 4  # the run is API-bound; low local concurrency

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")

# ------------------------------------------------------------ the method -----
# Copied from scripts/typesafe-sfmta-dates.py (DATE_RE, page_text,
# candidates) and scripts/typesafe-sfmta-dates-round2.py (build, marked),
# unchanged, so the marked page is the one both answer keys' ids refer to.

_M = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
      r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_S = r"(?:winter|spring|summer|fall|autumn)"
_Q = r"(?:early|mid|late|end of|beginning of|the end of)[- ]?"
DATE_RE = re.compile(
    r"(?:\b(?:%(q)s)?(?:%(m)s|%(s)s)(?:\s*(?:/|-|–|to|and|or)\s*(?:%(m)s|%(s)s))?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d\d\b"
    r"|\b(?:%(q)s)?(?:%(m)s|%(s)s)(?:\s*(?:/|-|–|to|and|or)\s*(?:%(m)s|%(s)s))?,?\s+(?:of\s+)?20\d\d\b"
    r"|\b(?:%(q)s)20\d\d\b"
    r"|\bQ[1-4]\s+20\d\d\b"
    r"|\b\d{1,2}/\d{1,2}/(?:20)?\d\d\b"
    r"|\b(?:%(m)s)\s+\d{1,2}(?:st|nd|rd|th)?\b(?!,?\s+20\d\d)"
    r"|\b20\d\d\b)" % {"m": _M, "s": _S, "q": _Q}, re.I)

PILOT = (" If the page describes a pilot, trial or interim installation and names a later build of this project "
         "that replaced or will replace it, the pilot's dates do not count; use the later build's.")
# Jev read completion sentences as a start and as a consultation (Lake and
# Shotwell Slow Streets, San Bruno Ave), so the two questions say that such a
# sentence dates an end (review of 2026-09-29).
DONE = (" A sentence saying work was completed, finished or substantially implemented by a date (\"As of Fall 2022, "
        "the design was substantially implemented\", \"the first phase was completed in August 2017\") gives an end "
        "date, not this one.")
# With the project named in each question, Jev read a Slow Street's first
# form as another project and answered none ("This corridor had initially been
# implemented as a COVID-19 Response Slow Street in 2021"; 12th Avenue, Hearst,
# Somerset, 23rd Avenue). This sentence says the interim version is the same
# project; with it both gold sets score at least what they did without it
# (scratchpad experiment, 2026-09-29).
INTERIM = (" An earlier interim version of the same street or corridor (a COVID-19 response Slow Street) is this "
           "project, and its installation date counts unless the page names a later build that replaced it.")
# Round 3's definitions (DEFS3 in scripts/typesafe-sfmta-dates-round3.py), with
# Bryan's two rules from his round-3 review: Predicted Completion is the
# construction end in any phase, and a pilot's dates give way to a later build's.
# Two changes after the Fable review of the first Opus run (2026-09-30), which
# need every page re-asked: a project in phases takes its earliest phase's
# start and its latest phase's end, where round 3 counted any phase's (that
# let the start and end come from different phases, and dropping one of the
# pair removed the right date on 3 of 11 such pages: Telegraph Hill, Market
# Octavia Living Alleys, 12 Folsom); and a building's opening is its
# construction end (the reader answered none on 7 department pages giving a
# fire station, library or hospital "opened on" or "reactivated" a date).
DEFS = {
    "construction_start": (
        "When does construction or implementation of this project begin or when did it begin? Counts: "
        "'construction begins/began/starts', a timeline stage named Construction, Implementation, Installation "
        "or Near-term Implementation (use the first date of its range). "
        "Does not count: design, outreach, environmental review, approval or completion dates, or another "
        "project's or program's work. If the project has several phases, the start of the earliest phase counts. "
        "If the page revises an estimate, only the revised estimate counts." + DONE + INTERIM + PILOT),
    "construction_end": (
        "When does construction or implementation of this project finish or when did it finish? Counts: the last "
        "date of a Construction or Implementation stage's range, 'construction complete', 'substantially complete', "
        "'implementation was completed', a 'Project Completion' stage, and a 'Predicted Completion' field, whatever "
        "phase the project is in, since it is the best date the page gives. Does not count: close-out, evaluation, "
        "the end of a planning, design, outreach or approval stage, or the completion of housing or another project. "
        "A building's opening, reopening or reoccupation ('opened on', 'reactivated') is its construction end. "
        "If the project has several phases, the end of the latest phase counts." + PILOT),
    "consultation": (
        "When was the most recent public consultation for this project? Counts: open houses, virtual open houses, "
        "community meetings, workshops, surveys, door-to-door outreach, tabling, office hours, and timeline stages "
        "named outreach or community engagement (pick the last date of such a stage's range). Does not count: an "
        "engineering public hearing, a Board of Directors meeting, or outreach for a different project." + DONE),
    "hearing": (
        "When was the most recent SFMTA public hearing on this project? Counts: an engineering public hearing, a "
        "public hearing notice for this project, or a timeline stage named public hearing. Does not count: a Board "
        "of Directors meeting or an open house."),
    "approval": (
        "When did a city body most recently approve this project? Counts: SFMTA Board of Directors approval or "
        "legislation, adoption of a plan, the City Traffic Engineer's approval, a timeline stage named Project "
        "Approvals, Legislation or Plan Adoption (pick the last date of its range), including planned dates. "
        "Does not count: environmental review, or approval of a different project."),
}
FIELDS = list(DEFS)
# The fields this step publishes. The reader is asked all five, as in the trial,
# since the questions share one state and cost no more; only these are kept.
KEEP = ["construction_start", "construction_end", "consultation"]
# Fields the reader is not asked but a person can confirm in confirmed.csv, and which
# then stand over what tools/projects/coordination-projects.py reads off the page. The
# first public consultation is the first workshop or meeting, so the span runs
# from the first to the last (Bryan, 2026-09-29, on Powell Street Promenade
# Refresh: "May 18 to Aug 28 2017 was the period from first to 4th workshop").
CONFIRM_ONLY = ["consultation_start"]
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"]


def page_text(raw):
    soup = BeautifulSoup(raw, "html.parser")
    main = soup.select_one("main") or soup
    for t in main.select("script,style,nav,noscript,form"):
        t.decompose()
    txt = main.get_text("\n")
    txt = EMAIL.sub("[email removed]", txt)
    txt = PHONE.sub("[phone removed]", txt)
    txt = re.sub(r"[ \t\u00a0\ufeff]+", " ", txt)  # round 1's class, byte for byte (no \u200b)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    return txt[:MAX_CHARS]


def candidates(text):
    out = []
    for m in DATE_RE.finditer(text):
        out.append({"id": "c%d" % (len(out) + 1), "span": m.group(0), "start": m.start(), "end": m.end()})
        if len(out) == MAX_CANDIDATES:
            break
    return out


def long_date(iso):
    d = dt.date.fromisoformat(iso)
    return "%s %d, %d" % (MONTH[d.month - 1], d.day, d.year)


def date_only_line(text, offset):
    """True when the line holding `offset` is nothing but dates and range punctuation ("Summer 2023 - Spring 2024")."""
    a = text.rfind("\n", 0, offset) + 1
    b = text.find("\n", offset)
    line = text[a:b if b >= 0 else len(text)]
    # A timeline stage's date line may carry a word or two around its dates
    # ("Starting Fall/Winter 2024", "By End of 2019", "Anticipated Winter
    # 2025", "2018 and beyond"). Without them the stage got no start, and its
    # dates fell into the previous stage's range and took that stage's label
    # (Arguello, 3rd Street, Smart City; Fable review, 2026-09-30).
    rest = re.sub(r"\b(?:to|through|ongoing|present|now|starting|starts|beginning|begins|by|end|of|the|"
                  r"anticipated|expected|estimated|est|projected|and|beyond|onward|onwards|approximately|approx|"
                  r"early|mid|late|tbd)\b|[\d\s\-–—/&,.:()]", "", DATE_RE.sub("", line), flags=re.I)
    return not rest


def raw_path(rec):
    return os.path.join(RAW, hashlib.sha1(rec["page"].encode()).hexdigest() + ".html")


def build(rec, raw):
    """Body text, sidebar card text, and candidates with context labels (round 2's build(), unchanged)."""
    body = page_text(raw)
    lines = ["Sidebar cards on this page (related notices and meetings):"]
    for n in rec.get("notices") or []:
        lines.append("Notice%s: %s" % (" dated " + long_date(n["date"]) if n["date"] else "", n["title"]))
    for m in rec.get("meetings") or []:
        lines.append("Meeting%s: %s" % (" on " + long_date(m["date"]) if m["date"] else "", m["title"]))
    cards = "\n".join(lines) if len(lines) > 1 else ""
    cards = EMAIL.sub("[email removed]", PHONE.sub("[phone removed]", cards))
    text = body + ("\n\n" + cards if cards else "")
    cands = candidates(text)
    for c in cands:
        c["in_cards"] = c["start"] >= len(body)

    soup = BeautifulSoup(raw, "html.parser")
    items = []
    tl = soup.select_one(".field-project-timeline")
    if tl:
        head = re.search(r"project timeline", body, re.I)
        body_cands = [c for c in cands if not c["in_cards"] and (not head or c["start"] >= head.start())]
        k, starts_so_far = 0, []
        for it in tl.select(".project-progress [class*='item-']"):
            t, d, s = it.select_one(".title"), it.select_one(".description"), it.select_one(".icon_text")
            if not (t and d):
                continue
            title = re.sub(r"\s+", " ", t.get_text(" ")).strip()
            status = re.sub(r"\s+", " ", s.get_text(" ")).strip() if s else ""
            desc = re.sub(r"\s+", " ", d.get_text(" ")).strip()
            if status and desc.endswith(status):
                desc = desc[: -len(status)].strip()
            when, what = title, desc
            if not re.search(r"\b20\d\d\b", when) and re.search(r"\b20\d\d\b", what):
                when, what = what, when
            k0 = k
            while k < len(body_cands) and not (
                    body_cands[k]["span"] in when and date_only_line(body, body_cands[k]["start"])
                    and (not starts_so_far or "\n" in body[starts_so_far[-1]:body_cands[k]["start"]])):
                k += 1
            start = body_cands[k]["start"] if k < len(body_cands) else None
            if start is not None:
                starts_so_far.append(start)
                k += 1
            else:
                k = k0
            items.append({"when": when, "what": what, "status": status, "start": start,
                          "size": len(when) + len(what) + len(status) + 30, "ids": []})
        starts = [it["start"] for it in items if it["start"] is not None]
        for it in items:
            if it["start"] is None:
                continue
            later = [s for s in starts if s > it["start"]]
            stop = min(later[0], it["start"] + it["size"] + 20) if later else it["start"] + it["size"]
            it["ids"] = [c["id"] for c in body_cands if it["start"] <= c["start"] < stop]
    in_item = {cid: it for it in items for cid in it["ids"]}

    all_lines = [(m.start(), m.group(0)) for m in re.finditer(r"[^\n]+", text)]
    for c in cands:
        idx = max(i for i, (s, _) in enumerate(all_lines) if s <= c["start"])
        c["line"] = all_lines[idx][1].strip()
        if c["id"] in in_item:
            it = in_item[c["id"]]
            c["label"] = "timeline stage: %s%s" % (it["what"][:80], (" (" + it["status"] + ")") if it["status"] else "")
            c["stage_when"] = it["when"]
            continue
        if c["in_cards"]:
            c["label"] = "sidebar card"
            continue
        line = all_lines[idx][1]
        date_only = len(re.sub(re.escape(c["span"]), "", line).strip(" -–:,/")) <= 3
        prev = [l for _, l in all_lines[max(0, idx - 12):idx]]
        nxt = all_lines[idx + 1][1].strip() if idx + 1 < len(all_lines) else ""
        if date_only:
            c["label"] = "line above: %s / line below: %s" % ((prev[-1].strip()[:60] if prev else ""), nxt[:60])
        elif len(line.strip()) <= 120:
            c["label"] = "its line: %s" % DATE_RE.sub("…", line.strip())
        else:
            heads = [l.strip() for l in prev if len(l.strip()) <= 60 and not l.strip().endswith(".")
                     and not DATE_RE.fullmatch(l.strip())]
            c["label"] = "section: %s" % heads[-1][:60] if heads else "body text"
    return {"text": text, "cands": cands}


def marked(text, cands):
    parts, pos = [], 0
    for c in cands:
        parts.append(text[pos:c["start"]])
        parts.append("[[%s|%s — %s]]" % (c["id"], c["span"], c["label"]))
        pos = c["end"]
    parts.append(text[pos:])
    return "".join(parts)


# ------------------------------------------------------ linked notices -----
# A project page links its hearing and outreach notices, and some dates live
# only there (Valencia Street's hearings). Each linked notice page's lines that
# name the project, with a line either side, are appended after the cards, so
# the page's own span ids do not move. A hearing agenda lists many projects;
# the keyword match keeps this one's lines. Meeting pages are not added: with
# them, precision fell on both gold sets (scratchpad experiment, 2026-09-29).
STOP = set("project projects street streets avenue safety improvement improvements program quick build quick-build "
           "the and of for to in on at sf san francisco sfmta phase transit plan study".split())
LINKED_HEAD = "\n\nLinked notice and meeting pages (text naming this project):\n"


def keywords(title):
    return {w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if w not in STOP and len(w) > 2}


def notice_path(url):
    return os.path.join(NOTICES, hashlib.sha1(url.encode()).hexdigest() + ".html")


def fetch_notice(url):
    """A notice page's HTML from its cached copy, fetched once when first linked. Returns None when the fetch
    fails, and caches nothing then, so the next run tries again. A notice is a dated posting sfmta.com does not
    revise in place (a new hearing is a new notice), so a cached copy is not re-read."""
    p = notice_path(url)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as fh:
            html = fh.read().decode("utf-8", "replace")
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError):
        return None
    if "<main" not in html and "<body" not in html:
        return None  # an empty or cut-off body is a failed read, not a notice
    os.makedirs(NOTICES, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(html)
    time.sleep(0.5)
    return html


def notice_excerpt(html, ptitle):
    """The notice's lines that share two of the project title's keywords, with a line either side, at most
    2,000 characters; empty when none does. A title with one keyword ("Geary", "13th") is not matched at all:
    one word finds other projects' items on a multi-item hearing agenda (Fable review, 2026-09-29)."""
    kw = keywords(ptitle)
    if len(kw) < 2:
        return ""
    lines = [l.strip() for l in page_text(html).split("\n") if l.strip()]
    hit = [i for i, l in enumerate(lines) if len(kw & set(re.findall(r"[a-z0-9]+", l.lower()))) >= 2]
    keep = sorted({j for i in hit for j in (i - 1, i, i + 1) if 0 <= j < len(lines)})
    return " / ".join(lines[j] for j in keep)[:2000]


def with_notices(page, rec, fetch=fetch_notice):
    """The page with its linked notices' excerpts appended and marked. Returns (page, urls that failed)."""
    extra, failed = [], []
    for n in rec.get("notices") or []:
        if not n.get("url"):
            continue
        html = fetch(n["url"])
        if html is None:
            failed.append(n["url"])
            continue
        ex = notice_excerpt(html, rec.get("title") or rec.get("name")) if html else ""
        if ex:
            extra.append((n["title"], ex))
    if not extra:
        return page, failed
    text = page["text"] + LINKED_HEAD + "\n".join(
        'Notice page "%s": %s' % (t, EMAIL.sub("[email removed]", PHONE.sub("[phone removed]", e))) for t, e in extra)
    cands = candidates(text)
    old = {c["id"]: c for c in page["cands"]}
    for c in cands:
        if c["id"] in old:
            c.update({k: v for k, v in old[c["id"]].items() if k not in ("start", "end")})
        else:
            c["in_cards"], c["linked"] = True, True
            ln = text.rfind("\n", 0, c["start"]) + 1
            nl = text.find("\n", c["start"])
            c["label"] = "linked page: " + text[ln:ln + 70].split(":")[0]
            c["line"] = text[ln:nl if nl > 0 else len(text)]
    return dict(page, text=text, cands=cands), failed


# Round 2's system prompt for its Claude method (CLAUDE_SYSTEM in
# scripts/typesafe-sfmta-dates-round2.py), with the agency named and a
# confidence asked for beside each id.
SYSTEM = (
    "You read one %s project web page and pick dates from it. "
    "Every date-like span on the page is marked [[cN|span — context]], where cN is its id and the context says "
    "which timeline stage or heading it sits under. For each question, answer with the id of the one marked span "
    "that answers it, or \"none\" when no marked span does. Read what the page says. Do not infer a date the page "
    "does not state. With each answer give your confidence that it is right, from 0 to 1. Reply with one JSON "
    "object and nothing else, mapping each question key to {\"answer\": id or \"none\", \"confidence\": number}.")


def request_body(page, title, agency=AGENCY["SFMTA"], fields=FIELDS):
    """The Messages API request for one page. Every question names the project, in the prompt's first line and
    the question itself: a page that mentions a neighbouring project's dates otherwise lends the reader that
    project's (Tenderloin took another project's start). `agency` names whose page it is; `fields` the
    questions asked (all five for SFMTA, as scored on the answer keys)."""
    prompt = "Project: %s\n\nPAGE\n\n%s\n\nQUESTIONS\n\n%s\n\nReply with JSON only: {%s}" % (
        title, marked(page["text"], page["cands"]),
        "\n".join("%s: %s" % (f, DEFS[f].replace("this project", "this project (%s)" % title)) for f in fields),
        ", ".join('"%s": {"answer": "cN or none", "confidence": 0.0}' % f for f in fields))
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "output_config": {"effort": EFFORT},
            "system": SYSTEM % agency, "messages": [{"role": "user", "content": prompt}]}


def body_hash(body):
    """The request in full, hashed: the page text, its marks, the definitions, the model and its settings. A
    page is re-asked when, and only when, this changes."""
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------- the call -----

class NoKey(Exception):
    pass


class OverCap(Exception):
    pass


def cost_of(usage):
    """Dollars for the tokens a response reports, at list price. Cache fields are counted as plain input: this
    step sets no cache breakpoints, so any the API reports are priced no lower than input."""
    u = usage or {}
    tin = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return tin * PRICE_IN_PER_MTOK / 1e6 + int(u.get("output_tokens") or 0) * PRICE_OUT_PER_MTOK / 1e6, tin


def worst_case(body):
    """The most one request can cost: its prompt's UTF-8 bytes counted at half a token each (English runs about
    four bytes a token, so this is roughly double), plus every output token MAX_TOKENS allows."""
    n = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    return (n / 2) * PRICE_IN_PER_MTOK / 1e6 + body["max_tokens"] * PRICE_OUT_PER_MTOK / 1e6


class Budget:
    """The hard cost cap. reserve() before a request, settle() after; a request whose worst case does not fit
    under the cap is refused before it is sent.

    The cap is shared by every run of this script on one calendar day, so the pipeline's two steps (SFMTA's
    pages and the departments') and a --gold run together stay under it: what each run spends is added to
    reader-spend.json beside data/pipeline-state/sources.json (gitignored), and a run starts with the day's
    spend so far already counted."""

    def __init__(self, cap, ledger=None):
        import threading
        self.cap, self.spent, self.reserved, self.lock = cap, 0.0, 0.0, threading.Lock()
        self.ledger = ledger or os.path.join(os.path.dirname(pipeline_state.PATH), "reader-spend.json")
        self.day = dt.date.today().isoformat()
        try:
            self.before = float(json.load(open(self.ledger, encoding="utf-8")).get(self.day) or 0.0)
        except (FileNotFoundError, ValueError, AttributeError):
            self.before = 0.0

    def reserve(self, amount):
        with self.lock:
            if self.before + self.spent + self.reserved + amount > self.cap:
                raise OverCap("cost cap $%.2f reached: $%.4f spent today before this run, $%.4f this run, "
                              "$%.4f in flight" % (self.cap, self.before, self.spent, self.reserved))
            self.reserved += amount

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual
            if actual:
                try:
                    days = json.load(open(self.ledger, encoding="utf-8"))
                except (FileNotFoundError, ValueError):
                    days = {}
                days[self.day] = round(self.before + self.spent, 6)
                os.makedirs(os.path.dirname(self.ledger), exist_ok=True)
                with open(self.ledger + ".tmp", "w", encoding="utf-8") as fh:
                    json.dump(days, fh, indent=1, sort_keys=True)
                os.replace(self.ledger + ".tmp", self.ledger)


def cached_response(h):
    p = os.path.join(RESPONSES, h + ".json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def ask(body, url, budget, h=None, ids=None, fields=FIELDS):
    """One page's answer: from .cache/page-dates-reader/ when this exact request was answered before (no call,
    no cost this run), else one Messages API request under the budget. Returns (record, called). The record
    holds the reply text, the usage and its cost, never the page text. Retries a 429, 5xx or 529 three times.

    A reply is kept only when it parses: every asked field names a span on the page (`ids`) or `none`. A reply
    that does not is paid for, not kept, and raised, so the page keeps its last answer and is asked again next
    run. A reply the API ended early (a refusal, or MAX_TOKENS reached) is kept with an `error`, so the same
    request is not bought again; a change to the page's text makes a new request, and deleting the file retries."""
    h = h or body_hash(body)
    rec = cached_response(h)
    if rec is not None:
        if rec.get("error"):
            raise RuntimeError("%s: %s (answer on file; delete %s to ask again)" % (url, rec["error"], h[:12]))
        return rec, False
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise NoKey(url)
    hold = worst_case(body)
    budget.reserve(hold)
    spent, done = 0.0, False
    try:
        req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode(), method="POST", headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        last = None
        for attempt in range(4):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=300) as fh:
                    resp = json.load(fh)
                break
            except urllib.error.HTTPError as e:
                # An error status is not billed.
                last = "HTTP %s: %s" % (e.code, e.read()[:300].decode("utf-8", "replace"))
                if e.code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                    wait = e.headers.get("retry-after") if e.headers else None
                    time.sleep(min(float(wait), 60) if wait and wait.replace(".", "", 1).isdigit() else 2 ** (attempt + 1))
                    continue
                raise RuntimeError(last)
            except (OSError, ValueError, http.client.HTTPException) as e:
                # A timeout (socket.timeout on 3.9), a dropped connection or a
                # cut-off body: the request may have run and been billed with
                # the reply lost, so its worst case is counted as spent.
                last = "%s: %s" % (type(e).__name__, e)
                budget.settle(hold, hold)
                hold = 0.0
                if attempt < 3:
                    time.sleep(2 ** (attempt + 1))
                    again = worst_case(body)
                    budget.reserve(again)  # raises OverCap with nothing held
                    hold = again
                    continue
                raise RuntimeError(last)
        else:
            raise RuntimeError(last)
        spent, tin = cost_of(resp.get("usage"))
        text = "".join(b.get("text") or "" for b in resp.get("content") or [] if b.get("type") == "text")
        rec = {"model": resp.get("model"), "stop_reason": resp.get("stop_reason"), "text": text,
               "usage": resp.get("usage"), "inputTokens": tin,
               "outputTokens": int((resp.get("usage") or {}).get("output_tokens") or 0),
               "costUsd": round(spent, 6), "latency_s": round(time.perf_counter() - t0, 2),
               "requested": dt.datetime.now().isoformat(timespec="seconds")}
        done = True
    finally:
        # A request that failed in a way not handled above is counted at its worst case.
        budget.settle(hold, spent if done else hold)
    if rec["stop_reason"] != "end_turn":
        rec["error"] = "stop_reason %s" % rec["stop_reason"]
    elif ids is not None:
        bad = [f for f, v in parse_reply(rec["text"], fields)["answers"].items()
               if v["choice"] != "none" and v["choice"] not in ids]
        if bad:
            raise RuntimeError("%s: reply does not parse for %s: %r" % (url, ", ".join(bad), rec["text"][:160]))
    os.makedirs(RESPONSES, exist_ok=True)
    tmp = os.path.join(RESPONSES, h + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(RESPONSES, h + ".json"))
    if rec.get("error"):
        raise RuntimeError("%s: %s" % (url, rec["error"]))
    return rec, True


def _answer_id(a):
    """An id as the reply gives it, normalised: "c12", "[[c12|Fall 2019 — …]]" and 12 are all "c12"."""
    if a is None:
        return "invalid"
    a = str(a).strip().strip("[]").split("|")[0].strip()
    if a.lower() == "none":
        return "none"
    if re.fullmatch(r"\d+", a):
        return "c" + a
    return a


def parse_reply(text, fields):
    """{field: {"choice": id or "none", "confidence": x}} from the reply, in the shape decode() reads: the first
    JSON object in it that names an asked field. A field the reply leaves out or garbles is `invalid`, which
    ask() refuses to keep. A confidence given as a percentage (1 < x <= 100) is read as one."""
    got, dec, i = {}, json.JSONDecoder(), 0
    text = text or ""
    while True:
        i = text.find("{", i)
        if i < 0:
            break
        try:
            obj, _ = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict) and any(f in obj for f in fields):
            got = obj
            break
        i += 1
    out = {}
    for f in fields:
        v = got.get(f)
        a, c = (v.get("answer"), v.get("confidence")) if isinstance(v, dict) else (v, None)
        try:
            c = float(c)
            c = c / 100 if 1 < c <= 100 else c
            c = min(max(c, 0.0), 1.0)
        except (TypeError, ValueError):
            c = 0.0
        out[f] = {"choice": _answer_id(a), "confidence": c}
    return {"answers": out}


# ------------------------------------------------------------- the dates -----

# The months tools/projects/coordination-projects.py reads a season as: season_date() for a
# start, stage_end() for an end, so the two sources compare month for month.
SEASON_FIRST = {"winter": 1, "spring": 4, "summer": 7, "fall": 10, "autumn": 10}
SEASON_LAST = {"winter": 2, "spring": 5, "summer": 8, "fall": 11, "autumn": 11}
QUAL_FIRST = {"early": 1, "beginning of": 1, "mid": 5, "late": 9, "end of": 10, "the end of": 10}
QUAL_LAST = {"early": 4, "beginning of": 3, "mid": 8, "late": 12, "end of": 12, "the end of": 12}
MON = {m[:3].lower(): i for i, m in enumerate(MONTH, 1)}


def last_day(y, m):
    return (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day


def read_span(span, line):
    """What a date-like span says: (value at the page's precision, first ISO day, last ISO day), or None.

    "Fall 2019" -> ("2019-09", "2019-09-01", "2019-11-30"); "2026" -> ("2026", "2026-01-01", "2026-12-31");
    "Spring/Summer 2024" -> first day of spring to last day of summer; "11/19/2024" and "November 19, 2024" -> the
    day. A span with no year ("November 19") takes the first year on its own line, and is unread when the line
    has none. A season or qualifier keeps the year-month of its first month as its value; an early, mid or
    late season names part of the season ("Late spring 2026" -> ("2026-05", "2026-05-01", "2026-06-30")).
    """
    s = span.strip().lower().rstrip(".")
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", s)
    if m:
        y, mo, d = int(m.group(3)) % 100 + 2000, int(m.group(1)), int(m.group(2))
        try:
            iso = dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
        return iso, iso, iso
    ys = re.findall(r"\b(20\d\d)\b", s)
    if ys:
        y = int(ys[-1])
    else:
        # Only when the line names one year: with two ("Following the 2019
        # outreach, construction began June 25 and ends in 2024") the span's
        # year is a guess, so it stays unread (Fable review, 2026-09-29).
        near = set(re.findall(r"\b(20\d\d)\b", line or ""))
        if len(near) != 1:
            return None
        y = int(near.pop())
    if re.fullmatch(r"(?:(?:early|mid|late)[- ]?)?winter,?\s+(?:of\s+)?20\d\d", s) and re.search(
            re.escape(span.strip()) + r"\s*[/-]\s*(?:20)?\d\d\b", line or "", re.I):
        return "%d-12" % y, "%d-12-01" % y, "%d-02-%02d" % (y + 1, last_day(y + 1, 2))
    # A winter that follows another season of its year on the line is the
    # winter that closes the year, as "Fall-Winter 2025" reads below: "Summer
    # & Winter 2020" (Active Beale Street; DATE_RE does not join by "&") and
    # "Summer 2020 to Late Winter 2020" (Howard Street).
    after = re.fullmatch(r"(?:(?:early|mid|late)[- ]?)?winter,?\s+(?:of\s+)?20\d\d", s) and re.search(
        r"\b(?:spring|summer|fall|autumn)(?:,?\s+(20\d\d))?\s*(?:&|and|-|–|—|to|through)\s*" + re.escape(span.strip()),
        line or "", re.I)
    if after and (not after.group(1) or int(after.group(1)) == y):
        return "%d-12" % y, "%d-12-01" % y, "%d-12-31" % y
    q = re.search(r"^q([1-4])\b", s)
    if q:
        a = 3 * int(q.group(1)) - 2
        return "%d-%02d" % (y, a), "%d-%02d-01" % (y, a), "%d-%02d-%02d" % (y, a + 2, last_day(y, a + 2))
    words = re.findall(r"[a-z]+", re.sub(r"\b20\d\d\b", "", s))
    marks = []  # (first month, last month) per month or season named, in order
    for i, w in enumerate(words):
        if w in SEASON_FIRST:
            # "Late spring" is May to June, not the whole season (lib/seasons.py).
            q = words[i - 1] if i and words[i - 1] in seasons.PART else None
            marks.append(seasons.months(q, w) if q else (SEASON_FIRST[w], SEASON_LAST[w]))
        elif w[:3] in MON and (w[:3] != "mar" or w in ("mar", "march")):
            marks.append((MON[w[:3]], MON[w[:3]]))
    day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", re.sub(r"\b20\d\d\b", "", s))
    if marks and day and len(marks) == 1 and marks[0][0] == marks[0][1]:
        mo, d = marks[0][0], int(day.group(1))
        try:
            iso = dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
        return iso, iso, iso
    if marks:
        a, b = marks[0][0], marks[-1][1]
        if b < a:  # "Fall-Winter 2025": the winter that closes the year, as round 3's span_key reads it
            b = 12
        return "%d-%02d" % (y, a), "%d-%02d-01" % (y, a), "%d-%02d-%02d" % (y, b, last_day(y, b))
    qual = next((k for k in sorted(QUAL_FIRST, key=len, reverse=True) if s.startswith(k)), None)
    if qual:
        a, b = QUAL_FIRST[qual], QUAL_LAST[qual]
        return str(y), "%d-%02d-01" % (y, a), "%d-%02d-%02d" % (y, b, last_day(y, b))
    return str(y), "%d-01-01" % y, "%d-12-31" % y


RANGE_TO = re.compile(r"\s*(?:-|–|—|to|through|until|thru)\s*", re.I)


def range_close(span, line):
    """The date-like span that closes a range the span opens on its line ("Fall 2024 - Fall 2025" -> "Fall 2025"),
    with what it reads as, or None. A closing span with no year takes the opening span's ("May - July 2019")."""
    line = line or ""
    i = line.find(span)
    if i < 0:
        return None
    m = RANGE_TO.match(line, i + len(span))
    if not m:
        return None
    # "2024-25", a two-year range DATE_RE reads as "2024" alone
    yy = re.fullmatch(r"20(\d\d)", span.strip()) and re.match(r"(\d\d)\b", line[m.end():])
    if yy and int(yy.group(1)) > int(span.strip()[2:]):
        y2 = "20" + yy.group(1)
        return y2, read_span(y2, y2)
    c = DATE_RE.match(line, m.end())
    if not c:
        return None
    close = c.group(0)
    y = re.findall(r"\b(20\d\d)\b", span)
    read = read_span(close, close if re.search(r"\b20\d\d\b", close) else (y[-1] if y else line))
    return (close, read) if read else None


RAW_KEYS = ("answer", "confidence", "span", "label", "line", "inCards", "stage", "linked", "picked")


def pick(cid, conf, by_id):
    """One field's answer as the reader gave it: the span it picked, with its label and line, or `none`."""
    if cid == "none" or cid not in by_id:
        return {"answer": "none" if cid == "none" else "invalid:" + str(cid), "confidence": round(conf, 3)}
    c = by_id[cid]
    if read_span(c["span"], c["line"]) is None:
        # A span with no year the reader picked when the page also gives the
        # same day with its year ("October 21" beside the card's "October 21,
        # 2026", Potrero Yard; "July 26th" beside "July 26, 2025"): take the
        # dated one, so the date is not lost as unread (Fable review of the
        # Opus run, 2026-09-30). The reader's own pick stays under `picked`.
        day = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", c["span"].strip().lower())
        twins = [x for x in by_id.values() if x is not c and re.search(r"\b20\d\d\b", x["span"])
                 # the same day, not a longer number ("April 2" is not "April 21, 2020")
                 and re.match(re.escape(day) + r"(?!\d)", re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "",
                                                                  x["span"].strip().lower()))
                 and not x.get("linked")]
        if len({x["span"].lower() for x in twins}) == 1:
            out = pick(twins[0]["id"], conf, by_id)
            out["picked"] = {"answer": cid, "span": c["span"]}
            return out
    out = {"answer": cid, "span": c["span"], "label": c["label"], "line": c["line"][:240],
           "inCards": c["in_cards"], "confidence": round(conf, 3)}
    if c.get("linked"):
        out["linked"] = True
    if c.get("stage_when"):
        out["stage"] = c["stage_when"]
    return out


ISO = re.compile(r"(20\d\d)(?:-(\d\d)(?:-(\d\d))?)?")


def read_answer(answer):
    """A hand-confirmed answer: an ISO date at any precision ("2025", "2025-10", "2025-10-14") or a date as the
    page words it ("Fall 2025"). Returns (value, first, last) or None."""
    m = ISO.fullmatch(answer.strip())
    if not m:
        return read_span(answer, answer)
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    try:
        if d:
            iso = dt.date(y, int(mo), int(d)).isoformat()
            return iso, iso, iso
        if mo:
            return "%d-%s" % (y, mo), "%d-%s-01" % (y, mo), "%d-%s-%02d" % (y, mo, last_day(y, int(mo)))
    except ValueError:
        return None
    return str(y), "%d-01-01" % y, "%d-12-31" % y


def load_confirmed(path=CONFIRMED):
    """data/sfmta-page-dates/confirmed.csv: node, field, answer, who, date. One row per checked pick; the answer
    is `none`, or the date as the page states it. Returns {(node, field): row}."""
    import csv
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except FileNotFoundError:
        return {}
    return {(r["node"].strip(), r["field"].strip()): {k: (r.get(k) or "").strip() for k in ("answer", "who", "date")}
            for r in rows if (r.get("node") or "").strip()}


def derive(raw, confirmed=None, predicted=None):
    """The dates each answer reads as, worked out afresh on every run from the stored span, so a fix to
    read_span reaches every page without asking again. A hand-confirmed answer (`confirmed`, by field)
    stands over the reader's: the same span marks its pick `confirmed`, another replaces it and keeps the
    reader's under `jev`. `predicted` is the page's Predicted Completion field, which stands over the
    reader's construction end (below). Returns (fields, conflicts)."""
    fields = {}
    for f in KEEP:
        src = raw.get(f) or {"answer": "none", "confidence": 0.0}
        v = {k: x for k, x in src.get("jev", src).items() if k in RAW_KEYS}
        c = (confirmed or {}).get(f)
        same = c and " ".join(c["answer"].lower().split()) == " ".join((v.get("span") or "none").lower().split())
        pc = read_span(predicted, predicted) if predicted and f == "construction_end" and not c else None
        if pc and not (v.get("span") and read_span(v["span"], v.get("line")) == pc):
            # Bryan's rule from his round-3 review: the Predicted Completion
            # field is the construction end whatever phase the project is in.
            # The definitions say so and the reader still picked another date
            # on 8 of the 51 pages that carry the field (Islais Creek,
            # 1 California, Muni Metro East; Fable review, 2026-09-30), so it
            # is applied here. The reader's own pick stays under `jev`.
            v = {"answer": "predicted", "span": predicted, "label": "the page's Predicted Completion field",
                 "line": "Predicted Completion: " + predicted, "confidence": 1.0, "jev": v}
        if c and not same:
            jev = v
            v = {"answer": "none"} if c["answer"] == "none" else {
                "answer": "confirmed", "span": c["answer"], "label": "checked by hand", "line": c["answer"]}
            v.update(confidence=1.0, jev=jev)
        if c:
            v["confirmed"] = c
        if v.get("span"):
            read = read_answer(v["span"]) if v["answer"] == "confirmed" else read_span(
                v["span"], predicted if v["answer"] == "predicted" else v.get("line"))
            head = re.match(r"section:\s*(.+)", v.get("label") or "")
            if read is None and v["answer"] not in ("confirmed", "predicted") and head:
                # A span with no year under a heading that names one takes the
                # heading's: "On December 2, ... held a virtual meeting" under
                # "FASIP Community Webinar December 2025" (SFPUC's Folsom Area
                # Stormwater page; D2 hand grade, 2026-09-29).
                read = read_span(v["span"], head.group(1))
            if read is None:
                v["unread"] = "the span names no year and its line names none, or more than one"
            else:
                v["value"], v["first"], v["last"] = read
                latest = f != "construction_start"
                # An end or a consultation is the last date of a range, so a
                # span that opens one reads to its close (West Portal: "Fall
                # 2024 - Fall 2025" -> Fall 2025; Fable review, 2026-09-29).
                close = range_close(v["span"], v.get("line")) if latest else None
                if close and close[1][2] > v["last"]:
                    v["closes"] = close[0]
                    v["value"], v["last"] = close[1][0], close[1][2]
                v["iso"] = v["last"] if latest else v["first"]
        fields[f] = v
    for f in CONFIRM_ONLY:
        c = (confirmed or {}).get(f)
        if not c or c["answer"] == "none":
            continue
        v = {"answer": "confirmed", "span": c["answer"], "label": "checked by hand", "line": c["answer"],
             "confidence": 1.0, "confirmed": c}
        read = read_answer(c["answer"])
        if read is None:
            v["unread"] = "the answer names no date"
        else:
            v["value"], v["first"], v["last"] = read
            v["iso"] = v["first"]
        fields[f] = v
    conflicts = []
    s, e = fields["construction_start"], fields["construction_end"]
    if s.get("iso") and e.get("iso") and e["iso"] < s["iso"]:
        # Two picks that cannot both hold. A timeline stage still marked
        # Pending is a plan and gives way to a date the page reports (Anza
        # Street: "06/11/2021: The project is now substantially complete!"
        # over "Summer 2021 Construction (Pending)"); otherwise the one the reader
        # is surer of stands, and a tie keeps the start.
        pend = [x for x in (s, e) if "(pending)" in (x.get("label") or "").lower()]
        sure = [x for x in (s, e) if x.get("confirmed")]
        if len(sure) == 2:
            conflicts.append({"field": "construction_end", "dropped": None, "iso": e["iso"],
                              "why": "both checked by hand, and the end is before the start: fix confirmed.csv"})
            return fields, conflicts
        if len(sure) == 1:
            lose, how = (e if sure[0] is s else s), "the other was checked by hand"
        elif len(pend) == 1 and not sure:
            lose, how = pend[0], "a timeline stage still marked Pending, against a date the page reports"
        else:
            lose = s if s["confidence"] < e["confidence"] else e
            how = "the reader is surer of the other (%.2f against %.2f)" % (
                max(s["confidence"], e["confidence"]), lose["confidence"])
        keep, name = (e, "construction_start") if lose is s else (s, "construction_end")
        why = "%s (%s): %s" % ("starts after the end" if lose is s else "ends before the start", keep["iso"], how)
        conflicts.append({"field": name, "dropped": lose["span"], "iso": lose["iso"], "why": why})
        for k in ("value", "first", "last", "iso", "closes"):
            lose.pop(k, None)
        lose["dropped"] = why
    return fields, conflicts


def page_facts(raw, page):
    """What the page says outside the request: its "Project Status" field's ticked items, the last day of the
    latest date-like span on it, and of the latest one on a line of dates alone, which is how a timeline or
    schedule row reads ("Fall 2024 - Early 2027")."""
    soup = BeautifulSoup(raw, "html.parser")
    status = [re.sub(r"\s+", " ", li.get_text(" ")).strip()
              for li in soup.select(".field--name-field-project-status .field__item li")]
    lasts, stages = [], []
    for c in page["cands"]:
        if c.get("linked"):
            continue
        for r in (read_span(c["span"], c["line"]), (range_close(c["span"], c["line"]) or (None, None))[1]):
            if r:
                lasts.append(r[2])
                if not c["in_cards"] and date_only_line(page["text"], c["start"]):
                    stages.append(r[2])
    pc = soup.select_one(".field--name-field-predicted-design-completio .field__item")
    built = next(("“%s” (%s)" % (c["span"], c["label"][len("timeline stage: "):]) for c in page["cands"]
                  if CONSTRUCTION_STAGE.search(c.get("label") or "")), None)
    return {"projectStatus": [x for x in status if x], "latestDate": max(lasts) if lasts else None,
            "latestStageDate": max(stages) if stages else None, "constructionStage": built,
            "predictedCompletion": re.sub(r"\s+", " ", pc.get_text(" ")).strip() or None if pc else None}


def decode(resp, page, confirmed=None, predicted=None):
    by_id = {c["id"]: c for c in page["cands"]}
    ans = resp["answers"]
    return derive({f: pick(ans[f]["choice"], ans[f].get("confidence") or 0.0, by_id) for f in KEEP}, confirmed,
                  predicted)


# ------------------------------------------------------------ the check -----
# Which picks a person should look at. The confidence line is set from the
# reader's own answers on both answer keys (claude-opus-5-5, 2026-09-30; 117
# picks of the three published fields, 9 wrong), and from all 1,106 dates it
# showed on SFMTA, Public Works and SFPUC pages the same day:
#   under 0.45: flags 3 gold picks (3%), catches 1 wrong; 2% of all dates
#   under 0.50: flags 8 (7%), catches 3; 4% of all dates
#   under 0.55: flags 17 (15%), catches 4; 11% of all dates
#   under 0.60: flags 24 (21%), catches 5; 18% of all dates
#   under 0.70: flags 41 (35%), catches 7; 31% of all dates
# The model's confidences come in steps of 0.05 and sit mostly between 0.6
# and 0.9, and two wrong picks sit at exactly 0.45. Bryan asked for about a
# tenth of shown dates to go to a person; 0.55 flags 11% and catches 4 of 9.
# The other signals, unchanged from the Jev method: start and end cannot both
# hold; SFMTA's phase contradicts the date; the date was read from a linked
# notice page. The five wrong picks the line misses are confident picks of
# another phase or a completion estimate (Upper Market's start at 0.80,
# Southeast Muni's end at 0.75, among them).
LOW_CONFIDENCE = 0.55
EARLY_PHASE = re.compile(r"planning|design|legislat", re.I)
DONE_PHASE = re.compile(r"complete", re.I)
CONSTRUCTION_PHASE = re.compile(r"construction|implementation", re.I)


# A `none` the reader is unsure of, on a page whose timeline dates a
# construction stage, goes to a person too: 5 of the 9 wrong answers in the
# Fable review's sample of the Opus run were a `none` at 0.50 to 0.70
# (Presidio Bus Lifts beside "Construction (Pending) Jan. 2020 to Mar. 2021",
# Transit U beside "Construction (Pending) 2025"), and a shown-date flag
# never sees them.
LOW_CONFIDENCE_NONE = 0.60
CONSTRUCTION_STAGE = re.compile(r"^timeline stage: .*\b(?:construction|implementation|installation)\b", re.I)


def flags(fields, conflicts, facts, title, phase, today, who="SFMTA"):
    """Why each shown pick needs a person to check it, by field: the reader's confidence under LOW_CONFIDENCE, a start
    and end that could not both hold, a phase (SFMTA's layer, else the page's Project Status; for Public Works
    and SFPUC the page's own Status) the date contradicts, or a date read from a linked notice page rather than
    the project page. `who` names whose phase it is."""
    out = {}
    for f in KEEP:
        v = fields[f]
        if (f in ("construction_start", "construction_end") and v.get("answer") == "none" and not v.get("confirmed")
                and v.get("confidence", 1.0) < LOW_CONFIDENCE_NONE and facts.get("constructionStage")):
            out[f] = ["the reader found no date (confidence %.2f), but the page's timeline dates a construction "
                      "stage: %s" % (v["confidence"], facts["constructionStage"])]
            continue
        if not v.get("iso") or v.get("confirmed"):
            continue
        why = []
        if v.get("confidence", 1.0) < LOW_CONFIDENCE:
            why.append("the reader's confidence is %.2f" % v["confidence"])
        if conflicts and f in ("construction_start", "construction_end"):
            why.append("the page's start and end could not both hold; the other was dropped")
        if phase and f in ("construction_start", "construction_end"):
            if f == "construction_end" and EARLY_PHASE.search(phase) and v["iso"] < today:
                why.append("%s lists the project in %s, but this end has passed" % (who, phase))
            if DONE_PHASE.search(phase) and v["iso"] > today:
                why.append("%s lists the project as %s, but this date is still to come" % (who, phase))
            if f == "construction_start" and CONSTRUCTION_PHASE.search(phase) and v["iso"] > today:
                why.append("%s lists the project in %s, but this start is still to come" % (who, phase))
        if v.get("linked"):
            why.append("read from a linked notice page, not the project page")
        if f == "consultation" and v["iso"] > today:
            # The question asks for the most recent consultation held; a date
            # still to come is a planned event (Bayview Community Pathway's
            # health fair, Jackson Square's "Community Outreach Begins Summer
            # 2026"; Fable review of the Opus run, 2026-09-30).
            why.append("this consultation date is after the day the page was read")
        if why:
            out[f] = why
    return out


# --------------------------------------------------------------- the run -----

FIELD_NAME = {"construction_start": "construction start", "construction_end": "construction end",
              "consultation": "latest public consultation"}


def review_md(pages, cfg=None):
    """review.md: every flagged pick nobody has checked, with its page, span, context and why it was flagged, and
    how to record the answer."""
    cfg = cfg or {}
    rows = [(p, f, v) for p in pages.values() if p.get("status") == "answered"
            for f, v in p["fields"].items() if v.get("flags")]
    out = ["# %s page dates to check by hand" % cfg.get("who", "SFMTA"), "",
           "Generated by `tools/projects/sfmta-page-dates.py%s`; do not edit. Each row is a date %s read off "
           "%s project page that the flag rule (`flags()` in the script) sends to a person. The site shows these "
           "dates with a note that they are unchecked." % (cfg.get("flag", ""), "Claude (%s)" % MODEL,
                                                           cfg.get("page_noun", "an SFMTA")), "",
           "To record an answer, add a row to `%s`: `node,field,answer,who,date`%s. "
           "`answer` is the date as the page states it (`Fall 2025`, or an ISO date such as `2025-10`), or `none` "
           "when the page gives no such date. A row whose answer is the reader's span confirms it; any other answer "
           "replaces it on the next run." % (os.path.relpath(cfg.get("confirmed", CONFIRMED), ROOT),
                                             cfg.get("node_note", "")), "",
           "%d picks to check." % len(rows), ""]
    for p, f, v in sorted(rows, key=lambda r: ((r[0].get("title") or "").lower(), KEEP.index(r[1]))):
        out += ["## [%s](%s) — %s" % (p.get("title"), p.get("url"), FIELD_NAME[f]), "",
                "- node `%s`, field `%s`" % (p["node"], f),
                ("- the reader's pick: **%s**%s, read as %s (confidence %.2f)" % (
                    v["span"], " – " + v["closes"] if v.get("closes") else "", v.get("value"), v.get("confidence", 0))
                 if v.get("span") else "- the reader's pick: **none** (confidence %.2f)" % v.get("confidence", 0)),
                "- where: %s" % (v.get("label") or ""),
                "- its line: “%s”" % (v.get("line") or "").replace("\n", " ")[:240],
                "- flagged: %s" % "; ".join(v["flags"]), ""]
    return "\n".join(out)


def load_prev(path=OUT):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def read_or_none(path, strip_status=False):
    """A raw page copy, or None. department-project-pages.py writes its copies with the HTTP status on the first
    line; only a 200 is a page."""
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return None
    if strip_status:
        status, _, raw = raw.partition("\n")
        if status.strip() != "200":
            return None
    return raw or None


def dept_raw(rec):
    """A Public Works or SFPUC page's raw copy: tools/projects/dpw-projects.py's for a page Public Works lists (it keeps
    those current), else tools/projects/department-project-pages.py's."""
    url = rec["page"]
    legacy = os.path.join(DPW_RAW, re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".html")
    return read_or_none(legacy) or read_or_none(
        os.path.join(DEPT_RAW, hashlib.sha1(url.encode()).hexdigest() + ".html"), strip_status=True)


def page_set(name):
    """What a run reads and writes: the SFMTA sitemap pages, or the Public Works and SFPUC project pages."""
    if name == "sfmta":
        src = json.load(open(PAGES, encoding="utf-8"))
        try:
            layer = {str(p["node"]): p.get("phase") for p in json.load(open(LAYER, encoding="utf-8"))["projects"]}
        except (FileNotFoundError, ValueError):
            layer = {}
        return {
            "recs": {str(r["node"]): r for r in src["records"]},
            "today": src.get("fetched_on") or dt.date.today().isoformat(),  # the day the pages were read
            "raw": lambda rec: read_or_none(raw_path(rec)),
            "phase": lambda rec, p: layer.get(str(rec.get("node"))) or (p.get("projectStatus") or [None])[-1],
            "agency": lambda rec: AGENCY["SFMTA"], "who": "SFMTA", "fields": FIELDS,
            "order": lambda n: (len(n), n),
            "out": OUT, "review": REVIEW, "confirmed": CONFIRMED, "marker": MARKER, "step": "sfmta-page-dates",
            "flag": "", "page_noun": "an SFMTA", "node_note": "",
            "no_copy": "data/sfmta-pages/",
            "source": "Claude (%s) reading every sfmta.com /projects/ page in "
                      "data/extract/sfmta-pages/sitemap.json" % MODEL,
            "method": "the gold method of notes/typesafe-trial-2026-09/round-3.md (Claude reading the whole page with "
                      "every date tagged), on the input and definitions the TypeSafe method used there ('round 2 best "
                      "input, round-3 definitions'), with Bryan's Predicted Completion and pilot rules; each question "
                      "names the project, and the linked notice pages' text is added (the script's docstring)",
            "department": False,
        }
    src = json.load(open(DEPT_PAGES, encoding="utf-8"))
    recs = {}
    for p in src["pages"]:
        if p.get("department") in ("Public Works", "SFPUC") and p.get("kind") == "project":
            recs[p["url"]] = {"node": p["url"], "page": p["url"], "title": p.get("title") or p["url"],
                              "department": p["department"], "status": p.get("status")}
    return {
        "recs": recs,
        "today": src.get("generated") or dt.date.today().isoformat(),
        "raw": dept_raw,
        "phase": lambda rec, p: rec.get("status"),
        "agency": lambda rec: AGENCY[rec["department"]], "who": "Public Works and SFPUC", "fields": KEEP,
        "order": lambda n: n,
        "out": DEPT_OUT, "review": DEPT_REVIEW, "confirmed": DEPT_CONFIRMED, "marker": DEPT_MARKER,
        "step": "dept-page-dates", "flag": " --pages departments", "page_noun": "a Public Works or SFPUC",
        "node_note": " (`node` is the page's address)", "no_copy": "data/dpw-cache/ or data/dept-pages-cache/",
        "source": "Claude (%s) reading every Public Works and SFPUC project page in "
                  "out/department-pages/pages.json" % MODEL,
        "method": "the SFMTA method (tools/projects/sfmta-page-dates.py's docstring), asked only the three published "
                  "fields, with the state naming the department's page",
        "department": True,
    }


def self_check(cfg, before):
    """The step's checks in pipeline/transportation-quality.py, run on what this run wrote with the files as they
    were before it as the previous data. A failure puts those files back. Returns the failing results."""
    import importlib.util
    import tempfile
    q = paths.load("transportation-quality.py")
    with tempfile.TemporaryDirectory() as tmp:
        for path, data in before.items():
            if data is not None:
                dst = os.path.join(tmp, os.path.relpath(path, ROOT))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as fh:
                    fh.write(data)
        bad = [r for r in q.check(cfg["step"], ROOT, tmp) if not r.ok]
    if bad:
        for path, data in before.items():
            if data is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                with open(path, "wb") as fh:
                    fh.write(data)
    return bad


# ------------------------------------------------------------ the answer keys -----
# The two hand-written answer keys of the TypeSafe trial: round 2's 50 pages
# and round 3's 25. Their ids are the candidate ids of round 2's build(), the
# same function as build() here, on the page copies of 2026-09-28; a page
# re-read since can shift them, so each key id is checked against the span it
# names and moved to the same span when the page's ids moved. Better Market
# Street is left out: its key was written on the page cut at 24,000
# characters. The grading rules are the key files' own (none_ok: `none` is
# also right), as scored in notes/typesafe-trial-2026-09/round-3.md.
GOLD_KEYS = [("round 2", os.path.join(ROOT, "tools", "projects", "fixtures", "round-2-gold.json")),
             ("round 3", os.path.join(ROOT, "tools", "projects", "fixtures", "round-3-gold.json"))]


def align_key(g, cands):
    """The answer key's ids for one field moved onto this build's candidates by span. Returns (ids, lost)."""
    spans = [c["span"] for c in cands]
    ids, lost = set(), 0
    for gid, span in zip(g["ids"], g["spans"]):
        i = int(gid[1:]) - 1
        if 0 <= i < len(cands) and cands[i]["span"] == span:
            ids.add(gid)
            continue
        near = sorted((abs(j - i), j) for j, sp in enumerate(spans) if sp == span)
        if near:
            ids.add(cands[near[0][1]]["id"])
        else:
            lost += 1
    return ids, lost


def gold_report(budget):
    """Ask the reader about every answer-key page, on the production input, and print precision and recall over
    all five fields, per key, with the cost. Answers come from .cache/page-dates-reader/ when this exact request
    was asked before."""
    src = json.load(open(PAGES, encoding="utf-8"))
    by_url = {}
    for r in src["records"]:
        for u in (r.get("canonical"), r.get("page")):
            if u:
                by_url[u.rstrip("/")] = r
    for name, path in GOLD_KEYS:
        gold = json.load(open(path, encoding="utf-8"))
        items, skipped = [], []
        for key, g in sorted(gold.items()):
            if re.search(r"better-?market-?street", g["url"]):
                skipped.append("%s (key written on a cut page)" % g["url"])
                continue
            rec = by_url.get(g["url"].rstrip("/"))
            raw = read_or_none(raw_path(rec)) if rec else None
            if raw is None:
                skipped.append("%s (%s)" % (g["url"], "no raw copy" if rec else "not in the sitemap"))
                continue
            page, _ = with_notices(build(rec, raw), rec)
            if not page["cands"]:
                skipped.append("%s (no candidate dates)" % g["url"])
                continue
            title = rec.get("title") or rec.get("name")
            body = request_body(page, title, AGENCY["SFMTA"], FIELDS)
            items.append((key, g, page, body))

        def one(it):
            key, g, page, body = it
            return it, ask(body, g["url"], budget, None, {c["id"] for c in page["cands"]}, FIELDS)

        C = W = NC = NW = CS = stated = lost = unscorable = 0
        per = {f: [0, 0, 0, 0] for f in FIELDS}  # right picks, picks, stated found, stated
        low = [0, 0]  # published-field picks under LOW_CONFIDENCE: all, wrong
        cost, called, errors = 0.0, 0, []
        with cf.ThreadPoolExecutor(WORKERS) as ex:
            results = list(ex.map(lambda it: _try(one, it), items))
        for it, res in results:
            key, g, page, body = it
            if isinstance(res, Exception):
                errors.append("%s: %s" % (g["url"], res))
                continue
            rec, sent = res
            called += sent
            cost += rec["costUsd"] if sent else 0.0
            ans = parse_reply(rec["text"], FIELDS)["answers"]
            for f in FIELDS:
                ok, n_lost = align_key(g["fields"][f], page["cands"])
                lost += n_lost
                is_stated = bool(g["fields"][f]["ids"]) and not g["fields"][f]["none_ok"]
                if is_stated and not ok:
                    unscorable += 1
                    continue
                stated += is_stated
                per[f][3] += is_stated
                a = ans[f]["choice"]
                if a == "none":
                    NC += not is_stated
                    NW += is_stated
                    continue
                right = a in ok
                C += right
                W += not right
                CS += right and is_stated
                per[f][0] += right
                per[f][1] += 1
                per[f][2] += right and is_stated
                if f in KEEP and ans[f]["confidence"] < LOW_CONFIDENCE:
                    low[0] += 1
                    low[1] += not right
        print("%s key: %d pages scored%s" % (name, len(items) - len(errors),
                                             ("; left out: " + "; ".join(skipped)) if skipped else ""))
        print("  precision %s (%d of %d picks right), recall %s (%d of %d stated fields found)" % (
            "%.2f" % (C / (C + W)) if C + W else "-", C, C + W, "%.2f" % (CS / stated) if stated else "-", CS, stated))
        print("  per field (right/picks, found/stated): " + "; ".join(
            "%s %d/%d, %d/%d" % (f, *per[f]) for f in FIELDS))
        print("  none where the key has a date: %d; key ids whose span is gone from the page: %d; stated fields "
              "left unscored for it: %d" % (NW, lost, unscorable))
        print("  published-field picks under confidence %.2f: %d, of which wrong: %d" % (LOW_CONFIDENCE, *low))
        print("  this key's new requests: %d, $%.4f" % (called, cost))
        for e in errors:
            print("  NOT ANSWERED: " + e)
    print("run total: $%.4f of the $%.2f cap" % (budget.spent, budget.cap))


def _try(fn, arg):
    try:
        return fn(arg)
    except Exception as exc:  # noqa: BLE001 - reported per page
        return arg, exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="ask about new and changed pages only (the default)")
    ap.add_argument("--pages", choices=("sfmta", "departments"), default="sfmta",
                    help="SFMTA's sitemap pages (default), or Public Works' and SFPUC's project pages")
    ap.add_argument("--node", help="print one page's picks in context and exit (a page address for departments)")
    ap.add_argument("--max-cost", type=float, default=COST_CAP_USD,
                    help="stop sending requests before this run's cost passes this many dollars (at most %.0f)"
                         % COST_CAP_USD)
    ap.add_argument("--gold", action="store_true",
                    help="score the reader on the round-2 and round-3 answer keys and exit; writes nothing tracked")
    args = ap.parse_args()
    budget = Budget(min(args.max_cost, COST_CAP_USD))

    if args.gold:
        gold_report(budget)
        return

    cfg = page_set(args.pages)
    recs = cfg["recs"]
    prev = load_prev(cfg["out"])
    held = prev.get("pages", {})
    confirmed = {}
    for (node, f), row in load_confirmed(cfg["confirmed"]).items():
        confirmed.setdefault(node, {})[f] = row
    today = cfg["today"]

    if args.node:
        e = held.get(args.node)
        print(json.dumps(e, indent=1, ensure_ascii=False) if e else "no answer on file for %s" % args.node)
        return

    pages, todo, no_copy, notice_failed = {}, [], [], []
    for node in sorted(recs, key=cfg["order"]):
        rec = recs[node]
        url = rec.get("canonical") or rec["page"]
        raw = cfg["raw"](rec)
        if raw is None:
            no_copy.append(node)
            if node in held and held[node].get("status") == "answered":
                fields, conflicts = derive(held[node]["fields"], confirmed.get(node),
                                           held[node].get("predictedCompletion"))
                pages[node] = dict(held[node], fields=fields, conflicts=conflicts)
            elif node in held:
                pages[node] = held[node]
            else:
                pages[node] = {"node": node, "title": rec.get("title") or rec.get("name"), "url": url,
                               "status": "no page copy"}
            continue
        page, missing = with_notices(build(rec, raw), rec)
        entry = {"node": node, "title": rec.get("title") or rec.get("name"), "url": url,
                 "candidates": len(page["cands"]), **page_facts(raw, page)}
        if cfg["department"]:
            entry.update(department=rec["department"], pageStatus=rec.get("status"))
        if not page["cands"]:
            # Nothing on the page reads as a date, so there is nothing to pick.
            pages[node] = dict(entry, status="no dates on page", hash=None,
                               fields={f: {"answer": "none", "confidence": 1.0} for f in KEEP})
            continue
        body = request_body(page, entry["title"], cfg["agency"](rec), cfg["fields"])
        h = body_hash(body)
        old = held.get(node)
        if missing:
            notice_failed.append(node)
        if old and old.get("status") == "answered" and (old.get("hash") == h or missing):
            # Unchanged, or a linked notice could not be read: the last answer
            # stands. When the reply is on file it is read again, with no
            # request, so a change to how a reply is read reaches every page.
            kept = cached_response(old["hash"]) if old.get("hash") == h else None
            if kept and not kept.get("error"):
                fields, conflicts = decode(parse_reply(kept["text"], cfg["fields"]), page, confirmed.get(node),
                                           entry.get("predictedCompletion"))
            else:
                fields, conflicts = derive(old["fields"], confirmed.get(node), entry.get("predictedCompletion"))
            pages[node] = dict(old, **entry, fields=fields, conflicts=conflicts)
            continue
        todo.append((node, entry, page, body, h, old))

    asked, failed, over_cap, called = [], [], [], 0
    key_missing = False

    def one(item):
        node, entry, page, body, h, old = item
        rec, sent = ask(body, entry["url"], budget, h, {c["id"] for c in page["cands"]}, cfg["fields"])
        return item, rec, sent

    if todo:
        with cf.ThreadPoolExecutor(WORKERS) as ex:
            futs = [ex.submit(one, it) for it in todo]
            for fut in cf.as_completed(futs):
                try:
                    (node, entry, page, body, h, old), rec, sent = fut.result()
                except NoKey:
                    key_missing = True
                    continue
                except OverCap as exc:
                    over_cap.append(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001 - one page's failure keeps its last answer
                    failed.append(str(exc)[:200])
                    continue
                called += sent
                fields, conflicts = decode(parse_reply(rec["text"], cfg["fields"]), page, confirmed.get(node),
                                           entry.get("predictedCompletion"))
                pages[node] = dict(entry, status="answered", hash=h, model=MODEL,
                                   asked=rec["requested"][:10], inputTokens=rec["inputTokens"],
                                   outputTokens=rec["outputTokens"], costUsd=rec["costUsd"],
                                   fields=fields, conflicts=conflicts)
                asked.append(node)
    # A page that could not be asked keeps its last answer, if it has one.
    unasked = [it for it in todo if it[0] not in pages]
    for node, entry, page, body, h, old in unasked:
        if old and old.get("status") == "answered":
            fields, conflicts = derive(old["fields"], confirmed.get(node), entry.get("predictedCompletion"))
            pages[node] = dict(old, **entry, fields=fields, conflicts=conflicts)
        else:
            pages[node] = dict(old or {}, **entry, status="not asked", hash=None)

    ordered = {n: pages[n] for n in sorted(pages, key=cfg["order"])}
    for node, p in ordered.items():
        if p.get("status") != "answered":
            continue
        rec = recs.get(node) or {}
        why = flags(p["fields"], p.get("conflicts"), p, p.get("title"), cfg["phase"](rec, p), today,
                    who=rec["department"] if cfg["department"] else cfg["who"])
        for f, v in p["fields"].items():
            v.pop("flags", None)
            if f in why:
                v["flags"] = why[f]
    answered = [p for p in ordered.values() if p.get("status") == "answered"]
    summary = {
        "pages": len(ordered),
        "answered": len(answered),
        "noDatesOnPage": sum(1 for p in ordered.values() if p.get("status") == "no dates on page"),
        "notAsked": sum(1 for p in ordered.values() if p.get("status") in ("not asked", "no page copy")),
        "withAnyDate": sum(1 for p in answered if any(f.get("iso") for f in p["fields"].values())),
        "byField": {f: sum(1 for p in answered if p["fields"][f].get("iso")) for f in KEEP},
        "inputTokens": sum(p.get("inputTokens") or 0 for p in answered if p.get("model") == MODEL),
        "outputTokens": sum(p.get("outputTokens") or 0 for p in answered if p.get("model") == MODEL),
        # Pages still holding an answer from an earlier model: their request hash
        # differs, so each is re-asked when a run can.
        "otherModel": sum(1 for p in answered if p.get("model") != MODEL),
        "flagged": sum(1 for p in answered for v in p["fields"].values() if v.get("flags")),
        "confirmed": sum(1 for p in answered for v in p["fields"].values() if v.get("confirmed")),
    }
    # Two nodes can hold one page (Shotwell Slow Street's 1138 and 27619), so
    # one request, and its cost, is counted once by its hash.
    paid = {p["hash"]: p for p in answered if p.get("model") == MODEL}
    summary["costUsd"] = round(sum(p.get("costUsd") or 0 for p in paid.values()), 6)
    summary["inputTokens"] = sum(p.get("inputTokens") or 0 for p in paid.values())
    summary["outputTokens"] = sum(p.get("outputTokens") or 0 for p in paid.values())
    out = {
        "source": cfg["source"],
        "method": cfg["method"],
        "script": "tools/projects/sfmta-page-dates.py" + cfg["flag"],
        "model": MODEL,
        "effort": EFFORT,
        "pricePerMillionInputTokens": PRICE_IN_PER_MTOK,
        "pricePerMillionOutputTokens": PRICE_OUT_PER_MTOK,
        "costCapPerRunUsd": COST_CAP_USD,
        "definitions": {f: DEFS[f] for f in cfg["fields"]},
        "fields": KEEP,
        "summary": summary,
        "pages": ordered,
    }
    before = {}
    for path in (cfg["out"], cfg["review"]):
        try:
            before[path] = open(path, "rb").read()
        except FileNotFoundError:
            before[path] = None
    os.makedirs(os.path.dirname(cfg["out"]), exist_ok=True)
    wrote = stable.write_json(cfg["out"], out, indent=1, sort_keys=True)
    wrote_review = stable.write_text(cfg["review"], review_md(ordered, cfg))
    rel_out, rel_review = os.path.relpath(cfg["out"], ROOT), os.path.relpath(cfg["review"], ROOT)

    detail = "%d pages; %d answered this run, %d of them by a new API request ($%.4f spent, cap $%.2f); %d unchanged" % (
        len(ordered), len(asked), called, budget.spent, budget.cap, len(ordered) - len(asked) - len(unasked))
    # The checks run on every run, with no one asking (pipeline/README.md, rule 2).
    bad = self_check(cfg, before)
    if bad:
        for r in bad:
            print("QUALITY CHECK FAILED: %s: %s" % (r.check, r.detail), file=sys.stderr)
        pipeline_state.record(cfg["marker"], "failed", version=MODEL, detail=detail + "; quality: " + "; ".join(
            "%s: %s" % (r.check, r.detail) for r in bad[:3]))
        print("Previous %s and %s kept. This run's requests cost $%.4f; their answers are kept under %s, so "
              "the next run does not pay for them again." % (rel_out, rel_review, budget.spent,
                                                             os.path.relpath(RESPONSES, ROOT)), file=sys.stderr)
        sys.exit(1)

    problems = ["%d page(s) changed but ANTHROPIC_API_KEY is not set" % len(unasked)] if key_missing and unasked else []
    if over_cap:
        problems.append("cost cap reached: %d page(s) not asked, %s" % (len(over_cap), over_cap[-1]))
    if failed:
        problems.append("%d request(s) failed: %s" % (len(failed), "; ".join(failed[:3])))
    if notice_failed:
        problems.append("%d page(s) kept their last answer because a linked notice could not be read: %s"
                        % (len(notice_failed), ", ".join(notice_failed[:5])))
    if no_copy:
        problems.append("%d page(s) with no raw copy under %s" % (len(no_copy), cfg["no_copy"]))
    only_no_key = bool(key_missing and unasked) and len(problems) == 1
    if only_no_key:
        # A host with no key, such as the scheduled refresh VM (lead, 2026-11-10: no key goes there), keeps the last
        # answers for changed pages by design. "kept" is not a failed refresh, so the run neither exits 2 nor trips the
        # freshness check; the pages wait for a run on a host that has the key.
        pipeline_state.record(cfg["marker"], "kept", version=MODEL, detail=detail + "; " + problems[0])
    elif problems:
        pipeline_state.record(cfg["marker"], "failed", version=MODEL, detail=detail + "; " + "; ".join(problems))
    else:
        pipeline_state.record(cfg["marker"], "changed" if asked else "unchanged", version=MODEL, detail=detail)
    print(detail + (" -> wrote %s" % rel_out if wrote else " -> no change")
          + (", %s" % rel_review if wrote_review else ""))
    print("%d picks flagged for a person to check, %d checked by hand (%s)"
          % (summary["flagged"], summary["confirmed"], rel_review))
    if asked and len(asked) <= 20:
        print("asked: " + ", ".join(sorted(asked, key=cfg["order"])))
    for p in problems:
        print("REFRESH FAILED, last answers kept: " + p)
    print("this run: %d API request(s), $%.4f; held answers from %s cost $%.4f in all (%d input, %d output tokens)"
          % (called, budget.spent, MODEL, summary["costUsd"], summary["inputTokens"], summary["outputTokens"]))


if __name__ == "__main__":
    main()
