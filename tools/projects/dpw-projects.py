#!/usr/bin/env python3
"""Public Works' own project pages, which carry what the coordination feed does not.

    tools/projects/dpw-projects.py                 # fetch (cached), write out/dpw-projects/
    tools/projects/dpw-projects.py --refresh       # ignore the cache
    tools/projects/dpw-projects.py --update        # the index now, each page once its copy is a week old
    tools/projects/dpw-projects.py --limit 20      # a sample, for a quick look

The interagency coordination feed `btxj-k9uh` is a scheduling record: it says a
job exists on a block, and its description is written for excavators. It never
says whether bike work is in scope, which is the one thing Public Works Code
§2.4.13 requires a determination about. A session reading only that feed
reported, wrongly, that Public Works publishes no project pages at all.

It does. https://sfpublicworks.org/projects lists 269 of them, and a project
page carries the determination in prose. Folsom Street's says the roadway "will
be resurfaced and re-striped from four lanes to two lanes with bike lanes
between 19th and 24th Streets" — scope, extent and mode in one sentence, none of
which is anywhere in the feed.

What this writes is the input to the project-to-document join, not the join
itself: one record per project, with every street it names and every document it
links, so a hearing item can later be matched to a project by place and date
rather than by a street name shared with an unrelated job.

Deliberately kept out: staff email addresses. The project manager's NAME stays,
because a public employee acting in their official role is public record and the
name is what makes a row actionable, and every record links the city's own page,
which carries the address. Only the city should publish the address itself.

Refresh (--update): Public Works publishes no sitemap, Last-Modified or ETag,
so the re-read is bounded: the index every run, and each project page whose
copy is over a week old (MAX_AGE_DAYS). The check is recorded as
`pages:dpw-projects` in data/pipeline-state/sources.json, failed when any page
in that bound could not be reached (its held copy kept) or answered with an
HTTP error, so a refresh that keeps failing ages the extract.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
from streetnames import streets_in_order  # noqa: E402
from streetindex import StreetIndex  # noqa: E402

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "out", "dpw-projects")
CACHE = os.path.join(ROOT, "data", "dpw-cache")
INDEX = "https://sfpublicworks.org/projects"
HOST = "https://sfpublicworks.org"

# The index encodes each project's metadata in the class attribute of its own
# div — `cat-18 district-35 cost_b year_4 completed`. The district numbers are
# term ids, and the page's own filter list is what maps them back; reading that
# list rather than hardcoding the offset means a renumbering shows up as a
# missing key instead of as eleven wrong districts.
DISTRICT_TERMS = re.compile(r'<a href="#District (\d+)" data-val="(\d+)"')

ITEM = re.compile(r'<div id="node-(\d+)" class="project\s+([^"]*)"')
ITEM_SPLIT = re.compile(r'(?=<div id="node-\d+" class="project\s)')
TITLE = re.compile(r'class="portfolio-title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)

# A project page prints its structured fields as a label followed by its value,
# each in its own element. Flattening the tags to newlines and reading the line
# after a known label is more robust here than a CSS path, because the page's
# markup differs between the /project/<slug> template and the vanity-URL ones.
FIELDS = (
    "Status",
    "Location",
    "Districts",
    "Budget",
    "Project Manager",
    "Project Team",
)
# Contact details for an individual member of staff. These pages DO print them —
# a project manager's direct line beside their name, and a press contact's
# address in the project team block — and the first version of this script wrote
# both straight into the output. Keep the name, drop the way to reach the person:
# the record links the city's own page, which carries the address, and only the
# city should be the one publishing it.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
INDEX_STREETS = None
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")
# The department's own boilerplate, which every page repeats and none of which
# is about the project. It marks where the article ends.
FOOTER = "San Francisco Public Works is one of the largest"


def strip_contacts(value):
    """A staff name with no direct line and no address attached to it."""
    if not value:
        return value
    if EMAIL.search(value):
        return None
    v = PHONE.sub("", value)
    return re.sub(r"[\s,;.]+$", "", re.sub(r"\s{2,}", " ", v)).strip() or None


# --update: a page copy older than this is re-read. Public Works publishes no
# sitemap and sends no Last-Modified or ETag (checked 2026-09-28), so there is
# no cheap way to ask whether one page changed; a rolling re-read bounds how
# stale any page can be while each run fetches about a seventh of them.
MAX_AGE_DAYS = None
# Pages a re-read could not reach this run, whose held copy was used or
# which answered with an HTTP error.
STALE = []


def fetch(url, refresh=False):
    """The page, from a local copy unless asked otherwise."""
    os.makedirs(CACHE, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".html"
    path = os.path.join(CACHE, key)
    if MAX_AGE_DAYS is not None and os.path.exists(path) and \
            time.time() - os.path.getmtime(path) > MAX_AGE_DAYS * 86400:
        refresh = True
    if os.path.exists(path) and not refresh:
        return open(path, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": "sf-works/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        # A failed re-read of a page we already hold keeps the copy we have.
        if os.path.exists(path):
            STALE.append(url)
            return open(path, encoding="utf-8", errors="replace").read()
        raise
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    # Public Works' site is a small Drupal install. One request a second.
    time.sleep(1)
    return body


def text_lines(markup):
    """Every tag becomes a line break, so a label and its value are adjacent."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", markup, flags=re.S)
    t = re.sub(r"<[^>]+>", "\n", t)
    return [ln.strip() for ln in html.unescape(t).split("\n") if ln.strip()]


def same_path(url):
    """A page address as compared, not as stored: Public Works serves one page as /index.php/<path>,
    /index%2Ephp/<path> and /<path>, and moved its index links from the first to the last in
    September 2026."""
    u = urllib.parse.unquote(url).replace("/index.php/", "/")
    return re.sub(r"^https?://(www\.)?", "", u).rstrip("/").lower()


def held_urls():
    """{node: url} as the tracked extract last recorded them."""
    path = os.path.join(ROOT, "data", "extract", "dpw-projects", "projects.json")
    try:
        return {r["node"]: r["url"] for r in json.load(open(path, encoding="utf-8"))["records"] if r.get("url")}
    except (FileNotFoundError, ValueError, KeyError):
        return {}


def read_index(refresh=False):
    """One record per project, from the index's own class attributes.

    A project whose link differs from the one on file only in spelling keeps
    the address on file: the page is the same, and every downstream key (the
    department page matcher, the dates read off each page, the project
    record's links) is that address, so a respelling on Public Works' side
    would otherwise read as ~140 new pages."""
    page = fetch(INDEX, refresh)
    held = held_urls()
    districts = {tid: int(num) for num, tid in DISTRICT_TERMS.findall(page)}
    if not districts:
        sys.exit("index: no district filter terms found — the page markup moved")

    out = []
    for block in ITEM_SPLIT.split(page)[1:]:
        m = ITEM.search(block)
        if not m:
            continue
        node, classes = m.group(1), m.group(2).split()
        t = TITLE.search(block)
        if not t:
            continue
        href = html.unescape(t.group(1))
        out.append(
            {
                "id": f"dpw:{node}",
                "node": node,
                # The index links some projects by a vanity path (/hairball,
                # /13thStreetSafety) and some by /project/<slug>. Both resolve;
                # neither is derivable from the other, so the href is kept as
                # the page gave it.
                "url": (held[node] if node in held and same_path(held[node]) == same_path(HOST + href)
                        else HOST + href),
                "name": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t.group(2)))).strip(),
                "status": (
                    "Completed" if "completed" in classes
                    else "In progress" if "in-progress" in classes
                    else None
                ),
                "districts": sorted(
                    districts[c.split("-", 1)[1]]
                    for c in classes
                    if c.startswith("district-") and c.split("-", 1)[1] in districts
                ),
                "costBand": next(
                    (c.split("_", 1)[1] for c in classes if c.startswith("cost_")), None
                ),
            }
        )
    return out


def read_project(rec, refresh=False):
    """The structured fields and the prose, from one project's own page."""
    try:
        page = fetch(rec["url"], refresh)
    except urllib.error.HTTPError as e:
        rec["error"] = f"HTTP {e.code}"
        STALE.append(rec["url"])
        return rec
    lines = text_lines(page)
    # Everything below the department boilerplate is site furniture — a nav list
    # that happens to contain the words "Budget" and "Reports". Reading the
    # whole page found the footer's "Budget" link and recorded every project's
    # budget as "Commissions".
    end = next((i for i, ln in enumerate(lines) if ln.startswith(FOOTER)), len(lines))
    lines = lines[:end]

    # The fields sit in a run near the bottom of the article. Reading the line
    # AFTER each label, and stopping at the next label, keeps a multi-line value
    # like Project Team intact without needing to know how many rows it has.
    labels = {ln: i for i, ln in enumerate(lines) if ln in FIELDS}
    fields = {}
    for label, i in labels.items():
        values = []
        for ln in lines[i + 1:]:
            if ln in FIELDS or ln.startswith("Download project"):
                break
            values.append(ln)
            if label not in ("Project Team",):
                break
        fields[label] = values

    rec["pageStatus"] = (fields.get("Status") or [None])[0]
    rec["location"] = (fields.get("Location") or [None])[0]
    # A page with no Budget field lets the label match the site's own "Budget"
    # nav link, and the value read back is whatever followed it — "Commissions".
    # A budget is a figure, so anything without one is no budget.
    budget = (fields.get("Budget") or [None])[0]
    rec["budget"] = budget if budget and re.search(r"\d", budget) else None
    rec["projectManager"] = strip_contacts((fields.get("Project Manager") or [None])[0])
    # The team block runs into a press contact — name, phone, email — so each
    # line goes through the same filter and the labels around it are dropped.
    rec["team"] = [
        t for t in (strip_contacts(x) for x in (fields.get("Project Team") or []))
        if t and t not in ("Contact", "Phone", "Email", "Public Affairs")
    ]

    # The description is the prose above the fields: the longest paragraphs on
    # the page. It is where the scope determination lives when there is one.
    body = [ln for ln in lines if len(ln) > 120]
    rec["description"] = " ".join(body[:4])

    # Linked documents. A factsheet is the most likely place a phase schedule
    # appears, which is the open question on when restriping happens.
    docs = []
    for href, label in re.findall(r'href="([^"]+\.(?:pdf|docx?|xlsx?))"[^>]*>(.*?)</a>', page, re.S | re.I):
        docs.append(
            {
                "url": href if href.startswith("http") else HOST + html.unescape(href),
                "label": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", label))).strip(),
            }
        )
    rec["documents"] = docs

    # Streets, from the location field and the prose, in the order named. The
    # order carries meaning in these pages as it does in hearing orders: the
    # corridor comes first and the cross streets bound its extent.
    # Only names the city's own centreline has. Reading prose for street names
    # returns things that merely end in a suffix word — "redesigned Street",
    # "project-related Street" — and each of those is a false match waiting to
    # be made. The index also hands back the CNNs, which is what a geographic
    # join needs and what a name alone can never give.
    #
    # Two sets, and keeping them apart matters more than it looks. The LOCATION
    # field is the project's extent — "22nd Street, Pennsylvania Avenue to
    # Illinois Street". The description MENTIONS streets for context: a
    # playground's page names the corridor it sits beside, a plaza's names the
    # route past it. Pooling the two gave Kimbell Playground an extent of 188
    # blocks and matched it to a sewer job on Geary, because Geary appears in
    # its prose. Anything asking "is this the same piece of work" must use the
    # extent; the mentions are context and are kept as such.
    located = streets_in_order(rec.get("location") or "")
    mentioned = streets_in_order(rec["description"])
    rec["streets"] = INDEX_STREETS.resolve(located)
    rec["streetsMentioned"] = [
        s for s in INDEX_STREETS.resolve(mentioned) if s not in rec["streets"]
    ]
    rec["streetsRejected"] = [
        n for n in located + mentioned if not INDEX_STREETS.is_street(n)
    ]
    rec["cnns"] = sorted({c for n in rec["streets"] for c in INDEX_STREETS.cnns(n)})

    return rec


def write(records, today):
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(os.path.join(OUT, "projects.json"), {"generated": today, "source": INDEX, "projects": records},
                      end="", ensure_ascii=True, indent=1)

    withstreets = [r for r in records if r.get("streets")]
    withdocs = [r for r in records if r.get("documents")]
    lines = [
        "# Public Works project pages",
        "",
        f"Generated {today} by `tools/projects/dpw-projects.py` from [{INDEX}]({INDEX}). "
        "**Do not edit this file by hand — the next run overwrites it.**",
        "",
        f"{len(records)} projects. "
        f"{sum(1 for r in records if r['status'] == 'Completed')} completed, "
        f"{sum(1 for r in records if r['status'] == 'In progress')} in progress. "
        f"{len(withstreets)} name at least one street in prose; "
        f"{len(withdocs)} link at least one document.",
        "",
        "These pages carry what the interagency coordination feed does not: whether "
        "bike or streetscape work is in scope, in the department's own words. That is "
        "the determination Public Works Code §2.4.13 requires, and it is the reason "
        "this record exists.",
        "",
    ]
    for r in sorted(records, key=lambda r: r["name"].lower()):
        lines.append(f"### [{r['name']}]({r['url']})")
        lines.append("")
        bits = [r.get("pageStatus") or r.get("status") or "status not stated"]
        if r.get("districts"):
            bits.append("District " + ", ".join(str(d) for d in r["districts"]))
        if r.get("budget"):
            bits.append(r["budget"])
        lines.append(" · ".join(bits))
        lines.append("")
        if r.get("location"):
            lines.append(f"**Location.** {r['location']}")
            lines.append("")
        if r.get("streets"):
            lines.append("**Streets named.** " + ", ".join(r["streets"]))
            lines.append("")
        if r.get("description"):
            lines.append(r["description"])
            lines.append("")
        for d in r.get("documents", []):
            lines.append(f"- [{d['label'] or 'document'}]({d['url']})")
        if r.get("documents"):
            lines.append("")
    stable.write_text(os.path.join(OUT, "projects.md"), "\n".join(lines) + "\n")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import Extract, scrub  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore the local cache")
    ap.add_argument("--limit", type=int, help="only read this many project pages")
    ap.add_argument("--update", action="store_true",
                    help="re-read the index, and each page whose copy is over a week old")
    args = ap.parse_args()
    global MAX_AGE_DAYS
    if args.update:
        MAX_AGE_DAYS = 7
    global INDEX_STREETS
    INDEX_STREETS = StreetIndex()
    print(f"streets: {len(INDEX_STREETS):,} names in the city centreline")

    def produce():
        index = read_index(args.refresh or args.update)
        print(f"index: {len(index)} projects")
        todo = index[: args.limit] if args.limit else index
        records = []
        for i, rec in enumerate(todo, 1):
            records.append(read_project(rec, args.refresh))
            if i % 25 == 0 or i == len(todo):
                print(f"  read {i}/{len(todo)}")
        return records

    # The extract layer scrubs at write and refuses if an address survives,
    # so the scrub is asserted there rather than assumed here. A --limit run
    # is a partial read: it is scrubbed the same way but never becomes the
    # tracked extract.
    if args.limit:
        records, today = scrub(produce()), dt.date.today().isoformat()
    else:
        ex = Extract("dpw-projects").fetch_or_read(
            "projects", produce, refresh=args.refresh or args.update, meta={"site": INDEX})
        print(f"  extract: {ex}")
        records, today = ex.records, ex.fetched_on.isoformat()
        if args.update:
            # No change marker: the bound is the index, re-read every run, and
            # every page whose copy is over MAX_AGE_DAYS old.
            from lib import pipeline_state
            pipeline_state.refreshed("pages:dpw-projects", STALE,
                                     detail="index and pages over %d days old re-read" % MAX_AGE_DAYS)

    write(records, today)
    named = sum(1 for r in records if r.get("streets"))
    cnns = len({c for r in records for c in r.get("cnns", [])})
    docs = sum(len(r.get("documents", [])) for r in records)
    print(
        f"dpw-projects: {len(records)} projects, {named} naming a street the city "
        f"has, {cnns:,} distinct blocks, {docs} linked documents → out/dpw-projects/"
    )


if __name__ == "__main__":
    main()
