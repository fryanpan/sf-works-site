#!/usr/bin/env python3
"""SFMTA engineering public hearings: what was proposed, and what was decided.

    tools/meetings/sfmta-hearings.py                    # writes out/sfmta-hearings/
    tools/meetings/sfmta-hearings.py --since 2025-03-04
    tools/meetings/sfmta-hearings.py --pages 6 --out DIR
    tools/meetings/sfmta-hearings.py --update           # new hearings and late results only

Bryan chose this on 2026-09-20, answering how deep to go on MTA records:
"Minutes plus hearings."

**This is where a bikeway is actually legislated.** The SFMTA Board's own agenda
names the bike network in 14 items across 8 of the 34 meetings since the Biking
and Rolling Plan was adopted — which reads like very little happening, and is
not what is happening. SFMTA's own account of the process, on
[Engineering Public Hearings](https://www.sfmta.com/committees/engineering-public-hearings):

    "Following the public hearing, some items--indicated by an diamond on the
    public hearing agenda--can be approved by the City Traffic Engineer. Other
    items must be submitted to the SFMTA Board of Directors for approval."

So most street-level changes — the ESTABLISH CLASS IV BIKEWAY that puts a
protected lane on a block — never reach the board at all. Reading the board
record alone and concluding the city legislated almost no bikeways would be
wrong, and wrong in a way nothing in the board record could reveal.

What each hearing publishes, on its own page:

    Agenda   `/reports/engineering-public-hearing-agenda-<month>-<day>-<year>`
             plus a PDF. Ten days ahead. The proposals.
    Results  a PDF titled "Streets Division Directive Order No. N". The week
             after. Per item: the action, the street and extent, the supervisor
             district, WHO approves it (City Traffic Engineer or the SFMTA
             Board), the public comments, and the decision.

The results order is the disposition record this repo did not have. Its decision
line distinguishes the three outcomes that matter: approved for implementation,
approved and forwarded to the board for final approval, or continued.

Archive: `/past-meetings-and-events/2617`, paged, about 20 hearings a year back
to 2018.

**Not a substitute for reading the item.** This matches on words, and an item's
own text is a line or two. A hit is a pointer to the order, which is linked.

Refresh (--update): sfmta.com gives the hearing archive no change marker, so
the re-read is bounded: the archive listing and every hearing page under 60
days old (RECENT_DAYS), when a results order can still be posted; a PDF once
read is kept. The check is recorded as `listing:sfmta-hearings` in
data/pipeline-state/sources.json, failed when any page in that bound could not
be reached (its held copy kept), so a refresh that keeps failing ages the extract.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import hashlib
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = paths.ROOT
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
SITE = "https://www.sfmta.com"
ARCHIVE = SITE + "/past-meetings-and-events/2617"

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}

# Same term list as the board reader, so the two records are filtered alike and
# a corridor can be followed from one to the other. Deliberately broad.
TERMS = [
    # Not a bare "cycle": it matches MOTORCYCLE PARKING, which these orders
    # legislate constantly, and "budget cycle". Nine of 68 hearing items
    # were motorcycle parking before this.
    "bike", "bicycl", "bikeway", "cycle track", "cycletrack",
    "cycling", "cyclist",
    "class ii", "class iii", "class iv", "quick.?build", "quick build",
    "slow street", "neighborway", "protected lane", "protected bike",
    "sharrow", "green wave", "contraflow", "bike lane", "bicycle lane",
]
HIT = re.compile("|".join(TERMS), re.I)

# Individual city staff email addresses are scrubbed on the way in — the orders
# print a project manager's address beside almost every item. Bryan's standing
# rule: only the city publishes those. The person's name stays.
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PERSONAL_LOCAL = re.compile(r"^[A-Za-z][A-Za-z'-]*(?:[._][A-Za-z][A-Za-z'-]*)+$")


def scrub(text):
    def one(m):
        local = m.group(0).split("@", 1)[0]
        return ("[staff email removed — see the order]"
                if PERSONAL_LOCAL.match(local) else m.group(0))
    return EMAIL.sub(one, text)


# sfmta.com throttles a run that walks it quickly, and answers 403 rather than
# 429 when it does. The first run of this script died on one: HTTPError is a
# subclass of URLError, so three fast retries burned through in six seconds and
# the exception took the whole walk with it. So: a pause between requests, and a
# backoff long enough for a throttle to lift rather than one tuned to a dropped
# connection.
PAUSE = 0.7
BACKOFF = (5, 20, 60)


# Fetched bytes are cached under `.cache/sfmta-hearings/`, keyed by URL. A
# results order published two years ago does not change, and without the cache
# every re-run costs ten minutes of refetching — which is enough to stop anyone
# re-running after a parser fix, and the parser is the part that keeps being
# wrong. `--refetch` ignores the cache.
CACHE = os.path.join(ROOT, ".cache", "sfmta-hearings")
REFETCH = False
# --update: re-read what can change and nothing else. The archive listing
# gains a hearing every two weeks, and a hearing's own page gains its results
# order a few weeks after the hearing, so both are re-read while the hearing
# is under 60 days old. A PDF, once published, is kept.
UPDATE = False
RECENT_DAYS = 60
# Pages a re-read could not reach this run, whose held copy was used.
STALE = []
_SLUG_DATE = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)"
                        r"-(\d{1,2})-(\d{4})", re.I)
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december"]


def may_have_changed(url):
    if "/media/" in url or "download" in url:
        return False
    m = _SLUG_DATE.search(url)
    if not m:
        return True  # a listing page
    d = dt.date(int(m.group(3)), _MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
    return (dt.date.today() - d).days <= RECENT_DAYS


def cached(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())


def get(url, binary=False, tries=3):
    path = cached(url)
    if not REFETCH and os.path.exists(path) and not (UPDATE and may_have_changed(url)):
        with open(path, "rb") as fh:
            raw = fh.read()
        return raw if binary else raw.decode("utf-8", "replace")
    if UPDATE and os.path.exists(path):
        # An --update re-read of a page we already hold: if it fails, the copy
        # stands, so one unreachable page does not drop a hearing's items.
        try:
            return _download(url, path, binary, tries)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! re-read of {url} failed ({type(exc).__name__}); using the copy", file=sys.stderr)
            STALE.append(url)
            with open(path, "rb") as fh:
                raw = fh.read()
            return raw if binary else raw.decode("utf-8", "replace")
    return _download(url, path, binary, tries)


def _download(url, path, binary, tries):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    for i in range(tries):
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(req, timeout=90) as fh:
                raw = fh.read()
            os.makedirs(CACHE, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(raw)
            return raw if binary else raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 500, 502, 503) and i < tries - 1:
                time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)])


TAG = re.compile(r"(?s)<[^>]+>")


def hearings(pages):
    """Every past hearing the archive lists, newest first."""
    seen, out = set(), []
    for pg in range(pages):
        raw = get(f"{ARCHIVE}?page={pg}")
        # Drupal suffixes a reused title with "-0", "-1": the February 16,
        # 2024 hearing lives at ...-february-16-2024-0, and the bare slug
        # answers 403 "Content Not Found". Dropping the suffix is how 18
        # hearings read as unreachable before 2026-09-28. Since November 2026
        # the archive links the January 17, 2025 hearing as "...-meetings-...",
        # so the plural is read too.
        for slug in re.findall(
            r"/calendar/(engineering-public-hearing-meetings?-[a-z]+-\d+-\d{4}(?:-\d{1,2})?)(?=[\"?#])", raw
        ):
            if slug in seen:
                continue
            seen.add(slug)
            m = re.search(r"-([a-z]+)-(\d+)-(\d{4})(?:-\d{1,2})?$", slug)
            mon = MONTHS.get(m.group(1))
            if not mon:
                continue
            out.append({
                "date": f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}",
                "page": f"{SITE}/calendar/{slug}",
            })
    # One hearing per date. SFMTA lists some hearings under two addresses (February 19, 2021 at
    # ...-february-19-2021 and ...-2021-0), and which of them a read of the archive returns changes from read to
    # read, so the count moved by one between two runs with no new hearing (2026-11-10). The first address in
    # sorted order is kept, as tools/meetings/fetch-sfmta-hearings.py does.
    one = {}
    for r in sorted(out, key=lambda r: r["page"]):
        one.setdefault(r["date"], r)
    return sorted(one.values(), key=lambda r: r["date"], reverse=True)


def documents(page_url):
    """The agenda and results PDFs linked from one hearing's page."""
    raw = get(page_url)
    docs = {}
    for href, text in re.findall(r'href="([^"]+)"[^>]*>([^<]{4,120})</a>', raw):
        label = html.unescape(re.sub(r"\s+", " ", text)).strip().lower()
        if "/media/" not in href:
            continue
        url = href if href.startswith("http") else SITE + href
        # sfmta.com serves the same PDF link as /media/... on one read and
        # /index%2Ephp/media/... on the next; the extract flipped between the
        # two with no new hearing. Keep one spelling so a re-read is a no-op.
        url = re.sub(r"(sfmta\.com)/index(?:%2[Ee]|\.)php/", r"\1/", url)
        if "results" in label and "results" not in docs:
            docs["results"] = url
        elif "agenda" in label and "agenda" not in docs:
            docs["agenda"] = url
    return docs


def pdf_text(url):
    """A PDF's text, via pdftotext -layout. None if it cannot be read."""
    try:
        raw = get(url, binary=True)
    except Exception:
        return None
    try:
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=raw,
                           capture_output=True, timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    return scrub(p.stdout.decode("utf-8", "replace"))


# An order's items are numbered, and the number runs straight into the action
# with no space ("1.RESCIND – PERPENDICULAR PARKING"). The page furniture — a
# running header repeating the order number, and "Page N of M" — lands in the
# middle of an item, so it is stripped before splitting rather than after.
FURNITURE = re.compile(
    r"(?m)^\s*(Page \d+ of \d+|Streets Division|Directive Order No\s*\.?\s*\d+|"
    r"SAN FRANCISCO MUNICIPAL TRANSPORTATION AGENCY|Order #\s*\d+|"
    r"FOR PUBLIC HEARING)\s*$")
# An item is numbered `5.`, or split into lettered actions `4(a).` .. `4(d).`
# that share one proposal, one public-comment note and one decision. The
# boundary is therefore a change of top-level number, not every marker: a
# hearing whose items are all lettered parsed as zero items before this.
MARKER = re.compile(r"(?m)^[ \t]*(\d{1,2})[ \t]*(\([a-z]\))?[ \t]*\.[ \t]*(?=[A-Z])")

DECISION = re.compile(r"(?s)\bDecision:\s*(.+?)(?:\n\s*\n|\Z)")
COMMENTS = re.compile(r"(?s)\bPublic Comments?:\s*(.+?)(?=\n\s*\n|\bDecision:|\Z)")
DISTRICT = re.compile(r"\(Supervisor District ([0-9, and]+)\)", re.I)
APPROVER = re.compile(r"\((Approvable by the City Traffic Engineer|"
                      r"Requires approval by the SFMTA Board)\)", re.I)
ORDER_NO = re.compile(r"Directive Order No\s*\.?\s*(\d+)")


def split_items(body):
    """(number, text) per item, lettered actions grouped under their number."""
    marks = [(m.start(), m.group(1)) for m in MARKER.finditer(body)]
    out = []
    for i, (pos, no) in enumerate(marks):
        if i and marks[i - 1][1] == no:
            continue
        end = next((p for p, n in marks[i + 1:] if n != no), len(body))
        out.append((no, body[pos:end]))
    return out


def items(text):
    body = FURNITURE.sub("", text)
    out = []
    for no, chunk in split_items(body):
        one = re.sub(r"[ \t]+", " ", chunk).strip()
        if len(one) < 20:
            continue
        dec = DECISION.search(one)
        com = COMMENTS.search(one)
        dist = DISTRICT.search(one)
        app = APPROVER.search(one)
        # The headline is everything before the first structured field — the
        # action lines and the street extent, which is what a reader scans.
        head = re.split(r"\b(?:Proposal|Public Comments?|Decision)\b", one)[0]
        # The chunk starts at its own marker, which the caller prints itself.
        head = re.sub(r"^\d{1,2}\s*(\([a-z]\))?\s*\.\s*", "", head)
        out.append({
            "no": no,
            "head": re.sub(r"\s+", " ", head).strip()[:400],
            "district": dist.group(1) if dist else None,
            "approver": app.group(1) if app else None,
            "comments": re.sub(r"\s+", " ", com.group(1)).strip()[:300] if com else None,
            "decision": re.sub(r"\s+", " ", dec.group(1)).strip()[:300] if dec else None,
            "text": one[:1500],
        })
    return out


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
from extract import Extract  # noqa: E402


def read_archive(since, pages):
    """Walk the archive and parse every results order since `since`.

    The only function that reaches the network. What it returns is written
    to data/extract/sfmta-hearings/ and tracked, so a second run — and a
    fresh clone — builds from disk and makes no request.
    """
    # Newest first, and by page address within a date: the archive lists two
    # hearings on one date in either order from one read to the next, and a
    # rerun with nothing new must not reorder them.
    all_h = sorted(hearings(pages), key=lambda h: (h["date"], h["page"]), reverse=True)
    print(f"  {len(all_h)} hearings listed, {all_h[-1]['date']} .. {all_h[0]['date']}")
    want = [h for h in all_h if h["date"] >= since]
    print(f"  {len(want)} since {since}")

    hits, noresults, unreachable, unparsed, parsed = [], [], [], [], 0
    for i, h in enumerate(want, 1):
        try:
            docs = documents(h["page"])
        except Exception as exc:
            # The hearing page itself would not load. That is a different fact
            # from a hearing that posted no results order, so it is reported
            # separately — one is a gap in our read, the other in the record.
            print(f"  !! {h['date']}: {type(exc).__name__} {exc}")
            unreachable.append(f"{h['date']} ({exc})")
            continue
        h.update(docs)
        if not docs.get("results"):
            noresults.append(h["date"])
            continue
        text = pdf_text(docs["results"])
        if not text:
            noresults.append(h["date"])
            continue
        order = ORDER_NO.search(text)
        h["order"] = order.group(1) if order else None
        rows = items(text)
        h["itemCount"] = len(rows)
        parsed += 1
        matched = [r for r in rows if HIT.search(r["text"])]
        for r in matched:
            hits.append({**r, "date": h["date"], "order": h.get("order"),
                         "results": docs["results"], "agenda": docs.get("agenda"),
                         "page": h["page"]})
        # Same self-check as the board reader: an order whose raw text names a
        # term while none of its parsed items does means the split dropped an
        # item, not that the hearing had none.
        if HIT.search(text) and not matched:
            unparsed.append(h["date"])
        if i % 5 == 0:
            print(f"  hearings: {i}/{len(want)}")
    if unparsed:
        print(f"  !! {len(unparsed)} orders match on raw text but produced no "
              f"matching item: {', '.join(unparsed)}")
    return [{"all": all_h, "hearings": want, "matches": hits, "parsed": parsed,
             "noresults": noresults, "unreachable": unreachable, "unparsed": unparsed}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "sfmta-hearings"))
    ap.add_argument("--since", default="2025-03-04",
                    help="hearings from this date on (default: the day the "
                         "Biking and Rolling Plan was adopted)")
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the extract and the byte cache; re-download everything")
    ap.add_argument("--pages", type=int, default=8,
                    help="archive pages to walk (about 20 hearings a page)")
    ap.add_argument("--update", action="store_true",
                    help="re-read the archive listing and hearings under 60 days old; keep every held PDF")
    args = ap.parse_args()
    global REFETCH, UPDATE
    REFETCH = args.refetch
    UPDATE = args.update
    os.makedirs(args.out, exist_ok=True)
    ex = Extract("sfmta-hearings").fetch_or_read(
        f"since-{args.since}", lambda: read_archive(args.since, args.pages),
        refresh=args.refetch or args.update, meta={"site": ARCHIVE, "since": args.since, "pages": args.pages})
    print(f"  extract: {ex}")
    today = ex.fetched_on.isoformat()
    rec = ex.records[0]
    all_h, want, hits = rec["all"], rec["hearings"], rec["matches"]
    noresults, unreachable, unparsed, parsed = (rec["noresults"], rec["unreachable"],
                                                rec["unparsed"], rec["parsed"])
    if args.update:
        # No change marker: the bound is the archive listing plus every
        # hearing under RECENT_DAYS old. Anything in it not reached fails the check.
        from lib import pipeline_state
        pipeline_state.refreshed("listing:sfmta-hearings", STALE + list(unreachable),
                                 version=all_h[0]["date"] if all_h else None,
                                 detail="listing and hearings under %d days re-read" % RECENT_DAYS)

    stable.write_json(os.path.join(args.out, "hearings.json"),
                      {"generated": today, "archive": ARCHIVE, "since": args.since,
                       "hearings": want, "matches": hits}, end="", ensure_ascii=True, indent=1)

    by_date = {}
    for x in hits:
        by_date.setdefault(x["date"], []).append(x)

    # What the decision line actually said, grouped, because the split between
    # "approved for implementation" and "forwarded to the board" is the whole
    # reason this record is worth reading.
    def bucket(d):
        if not d:
            return "not recorded"
        low = d.lower()
        refused = ("not approved" in low or "disapprov" in low
                   or "withdraw" in low)
        if refused and "approved by" in low:
            # "Item 9(a)(B) disapproved … All other items approved" is one
            # decision covering several actions, and neither bucket alone.
            return "partly approved"
        if "forward" in low or "sfmta board" in low:
            return "approved, forwarded to the SFMTA Board"
        if "on hold" in low:
            return "held over"
        if "continu" in low:
            return "continued"
        if refused:
            return "not approved or withdrawn"
        if "approv" in low:
            return "approved by the City Traffic Engineer"
        return "other"

    buckets = {}
    for x in hits:
        buckets[bucket(x["decision"])] = buckets.get(bucket(x["decision"]), 0) + 1

    L = [
        "# SFMTA engineering hearings: bike items and what was decided",
        "",
        f"Generated {today} by `tools/meetings/sfmta-hearings.py`. **Do not edit this file "
        "by hand — the next run overwrites it.**",
        "",
        f"The [hearing archive]({ARCHIVE}) lists **{len(all_h)} hearings**, "
        f"{all_h[-1]['date']} to {all_h[0]['date']}. This reads the {parsed} "
        f"decision orders published since **{args.since}**, the day the "
        "[Biking and Rolling Plan](https://www.sfmta.com/projects/biking-and-rolling-plan) "
        f"was adopted, and flags **{len(hits)} items** across {len(by_date)} "
        "hearings.",
        "",
        "**This is where a bikeway is legislated.** SFMTA's own account of the "
        "process: items marked with a diamond on the hearing agenda "
        "*\"can be approved by the City Traffic Engineer\"*, and only the others "
        "*\"must be submitted to the SFMTA Board of Directors for approval\"* "
        "([Engineering Public Hearings](https://www.sfmta.com/committees/engineering-public-hearings), "
        f"read {today}). The board record alone therefore understates what the "
        "city legislated, and cannot show by how much.",
        "",
        "## What was decided",
        "",
        "| Outcome | Items |",
        "| --- | --- |",
    ]
    for k in sorted(buckets, key=lambda k: -buckets[k]):
        L.append(f"| {k} | {buckets[k]} |")
    L += ["", f"Total {len(hits)}.", ""]
    if noresults:
        L += [f"Hearings that published no readable results order: "
              f"{', '.join(sorted(noresults))}. Nothing was decided there that "
              "this file can show.", ""]
    if unreachable:
        L += ["**Hearing pages this could not load, so their items are missing "
              "from every count above:** " + "; ".join(sorted(unreachable))
              + ". Re-run; if it persists, open the page by hand.", ""]
    if unparsed:
        L += [f"**Orders whose text names one of these terms while no item parsed "
              f"out of them did — the parser dropped something and these need a "
              f"human read: {', '.join(sorted(unparsed))}.**", ""]

    L += ["## The items", ""]
    for date in sorted(by_date, reverse=True):
        rows = by_date[date]
        h = next(x for x in want if x["date"] == date)
        links = f"[results]({h['results']})"
        if h.get("agenda"):
            links += f" · [agenda]({h['agenda']})"
        links += f" · [hearing page]({h['page']})"
        order = f" — Directive Order {h['order']}" if h.get("order") else ""
        L += [f"### {date}{order}", "", links, ""]
        for r in rows:
            L.append(f"**{r['no']}.** {r['head']}")
            meta = []
            if r["district"]:
                meta.append(f"District {r['district']}")
            if r["approver"]:
                meta.append(r["approver"])
            if meta:
                L.append(f"  <br>*{' · '.join(meta)}*")
            if r["comments"]:
                L.append(f"  <br>**Public comments:** {r['comments']}")
            L.append(f"  <br>**Decision:** {r['decision'] or 'not recorded in the order'}")
            L.append("")
    L += [
        "## What this does not say",
        "",
        "- **The match is on words, not meaning.** The term list is broad on "
        "purpose — a false positive costs one read, a miss costs the finding.",
        "- **An item is a line or two and this prints the head of it.** Follow "
        "the order for the full text; it is linked on every date.",
        "- **A decision is not an installation.** \"Approved by the City Traffic "
        "Engineer for implementation\" is a legislative act with no date attached "
        "to the paint. Join it to the bikeway layer's `INSTALL_YR` before saying "
        "something was built.",
        "- **Items forwarded to the SFMTA Board are not final here.** Their "
        "approval is in the board record, `out/sfmta-board/bike-items.md`.",
        "",
    ]
    stable.write_text(os.path.join(args.out, "bike-items.md"), "\n".join(L) + "\n")

    print(f"{len(hits)} flagged items across {len(by_date)} hearings → {args.out}/")


if __name__ == "__main__":
    main()
