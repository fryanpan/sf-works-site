#!/usr/bin/env python3
"""SFPUC Commission decisions on San Francisco streets, read from the Commission's own minutes.

    tools/meetings/sfpuc-commission.py                # build from the extract; fetch only what is missing
    tools/meetings/sfpuc-commission.py --refetch      # ignore the extract and re-read every PDF
    tools/meetings/sfpuc-commission.py --limit 6      # a few meetings, for a parser check

The Commission publishes one page — the agendas, minutes and resolutions log —
and nothing behind it: no Legistar, no search, no API. Every meeting is a PDF.
So this reads the log page once for its links, reads each MINUTES pdf once
(the minutes carry the resolution number and the vote, which the agenda does
not), parses every numbered item, and writes the parsed items to
data/extract/sfpuc-commission/ through scripts/extract.py. Pages build from
that extract; only the extract touches the network.

The meeting date comes from the PDF's own header ("Tuesday, March 10, 2026"),
never from the file name: the log lists "June 9 Minutes" for 2026 against a
file named 6.9.2023_M_0.pdf, and the older files carry no year at all.

Street names are read with lib/streetnames.py and kept only when the
city's centreline has them (lib/streetindex.py); a name it lacks is
reported as rejected rather than matched. An item that names a street the city
has is a "street item" — that is the set out/project-record/ consumes.

Refresh (--update): the log page has no change marker, so it is re-read every
run and any minutes file it newly lists is read; a minutes PDF once read is
kept. The check is recorded as `listing:sfpuc-commission` in
data/pipeline-state/sources.json, failed when the log page or a new minutes
file could not be reached, so a refresh that keeps failing ages the extract.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from extract import Extract, scrub  # noqa: E402
from lib import stable  # noqa: E402
from streetindex import StreetIndex  # noqa: E402
from streetnames import streets_in_order, corridors  # noqa: E402

HOST = "https://www.sfpuc.gov"
LOG = HOST + "/about-us/boards-commissions-committees/sfpuc-commission/agendas-minutes-resolutions-log"
OUT = os.path.join(ROOT, "out", "sfpuc-commission")
# Raw PDF bytes, keyed by URL. Never tracked: the agendas print staff names
# and phone numbers, and a minutes file is refetchable. `.cache/` is ignored.
CACHE = os.path.join(ROOT, ".cache", "sfpuc-commission")
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
PAUSE = 0.7
# --update: re-read the log page, so a newly posted minutes file is found; every
# PDF already read comes from the cache, so only new minutes reach the network.
UPDATE = False
BACKOFF = (5, 20, 60)
# Pages a re-read could not reach this run, whose held copy was used.
STALE = []


def get(url, binary=False, tries=3, fresh=False):
    """Cached forever by URL: a minutes PDF, once posted, does not change. `fresh`
    re-reads the page anyway, and a failed re-read falls back to the copy."""
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if fresh and os.path.exists(path):
        try:
            return _fetch(url, path, binary, tries)
        except Exception as exc:  # noqa: BLE001
            print(f"  re-read of {url} failed ({exc}); using the copy")
            STALE.append(url)
    if os.path.exists(path):
        raw = open(path, "rb").read()
        return raw if binary else raw.decode("utf-8", "replace")
    return _fetch(url, path, binary, tries)


def _fetch(url, path, binary, tries):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    for i in range(tries):
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(req, timeout=90) as fh:
                raw = fh.read()
            os.makedirs(CACHE, exist_ok=True)
            open(path, "wb").write(raw)
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


def pdf_text(url):
    raw = get(url, binary=True)
    if not raw.startswith(b"%PDF"):
        return None
    p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=raw,
                       capture_output=True, timeout=180)
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None


# ---- the log page ------------------------------------------------------------

PDF_LINK = re.compile(r'<a[^>]+href="(/sites/default/files/about-us/commission/[^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
MINUTES_NAME = re.compile(r"(_M(inutes)?(_\d)?\.pdf$|Minutes)", re.I)


def minutes_links():
    """Every minutes PDF on the log page, by URL, with the link text beside it."""
    page = get(LOG, fresh=UPDATE)
    out, seen = [], set()
    for href, label in PDF_LINK.findall(page):
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        name = href.rsplit("/", 1)[-1]
        if not (MINUTES_NAME.search(name) or re.search(r"minutes", label, re.I)):
            continue
        url = HOST + href
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "label": label, "file": name})
    return out


# ---- one minutes file ---------------------------------------------------------

MEETING_DATE = re.compile(
    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})")
MEETING_KIND = re.compile(r"(REGULAR|SPECIAL|BUDGET)\s+MEETING\s+MINUTES", re.I)
# Running headers: "SFPUC March 10, 2026 Meeting Minutes  Page 2 of 5" in the
# current layout, "SFPUC MINUTES – FEBRUARY 28, 2023   5" before 2025.
FURNITURE = re.compile(r"(?m)^\s*SFPUC .*? Minutes\s+Page \d+ of \d+\s*$|^\s*Page \d+ of \d+\s*$|"
                       r"^\s*SFPUC MINUTES\b.*$|^\s*[A-Z]+ \d{1,2}, \d{4} MINUTES\s*\d*\s*$")
# Item numbers sit anywhere from column 0 to column 12 depending on the year;
# lettered sub-items likewise, and in 2024 some sit at column 0.
ITEM = re.compile(r"(?m)^[ \t]{0,12}(\d{1,2})\.[ \t]+(?=\S)")
SUBITEM = re.compile(r"(?m)^[ \t]{0,14}([a-z])[\)\.][ \t]+(?=\S)")
# "(26-0034)" now; "(Resolution 23-0119)" and "(Resolution 23- 0046)" before 2025.
RESOLUTION = re.compile(r"\((?:Resolution\s+)?(\d{2}-\s*\d{4})\)")
# An item whose streets are somewhere else. The Commission runs a water
# system from the Sierra to the Peninsula, and "Skyline Boulevard" or
# "Alameda" in one of its titles is as likely to be San Mateo County as the
# city. These items are kept in the extract and left out of the street set.
OUTSIDE = re.compile(r"(?i)\b(San Mateo|Santa Clara|Alameda County|Tuolumne|Hetch Hetchy|Sunol|"
                     r"Moccasin|Millbrae|Sunnyvale|Crystal Springs|Peninsula|Calaveras|Mountain View|"
                     r"Palo Alto|Redwood City|San Bruno|Burlingame|Daly City|Pacifica|Ridge Trail|"
                     r"Upcountry|Tesla|Newark|Fremont|Pleasanton|Livermore|Bay Division Pipeline|"
                     # A Water Supply Assessment is a finding about one development,
                     # named by its address; "One Oak Street" is a building, not a street.
                     r"Water Supply Assessment)\b")
MOTION = re.compile(r"(?is)On (?:a )?motion (?:to |that )?(.+?)(?::|\n)")
AYES = re.compile(r"(?i)\bAyes:\s*(.+)")
NOES = re.compile(r"(?i)\bNoes:\s*(.+)")
# Lines that end an item's text and begin its record of what happened.
NARRATIVE = re.compile(r"(?im)^\s*(No public comment|Public Comment|On (a )?motion|Ayes:|Noes:|"
                       r"Absent:|Recused:|.*\b(presented|recessed|adjourned|called the meeting)\b|"
                       r"•|Item \d+ was (continued|removed|withdrawn)|(Commissioner|President|Vice President) \w+ (moved|requested|asked|noted))")
# Items that are procedure, not a decision about anything in the city.
PROCEDURAL = re.compile(r"(?i)^(Call to Order|Roll Call|Approval of the Minutes|General Public Comment|"
                        r"Report of the General Manager|Communications|Items initiated by Commissioners|"
                        r"Adjournment|Public Comment on the matters|Motion (on|regarding) whether|"
                        r"Announcement following|CONFERENCE WITH|Closed Session|New Commission Business|"
                        r"Other new business|Consent Calendar\s*$|Regular Calendar\s*$|BUDGET|"
                        r"Report on Recent|.*\b(Quarterly|Annual|Semiannual) Report|Advance Calendar|Contract Advertisement Report|Correspondence Log|"
                        r"Water Supply (Conditions|Development)|Quarterly|Annual|Semiannual|"
                        r"[\w\-,&' ]{0,80}\b(Report|Update|Log|Overview)$|Recess|Motion to continue|"
                        r"Bay Area Water Supply and Conservation Agency|Adopt renewed findings|Public Hearing to consider (the )?adopt(ion|ing) (of )?(the )?(proposed )?(schedules of )?rates)")


def parse_minutes(text, url):
    """The meeting and its items from one minutes file's text."""
    # pdftotext puts a form feed at each page break, in front of the first
    # line's indentation, so a sub-item at the top of a page did not begin
    # its line and was folded into the item before it.
    text = FURNITURE.sub("", text.replace("\x0c", ""))
    m = MEETING_DATE.search(text)
    if not m:
        return None
    date = dt.date(int(m.group(4)), MONTHS[m.group(2)], int(m.group(3))).isoformat()
    kind = (MEETING_KIND.search(text) or [None, "REGULAR"])[1].title()
    body = text[m.end():]
    body = body[body.find("1."):] if "1." in body else body

    items = []
    starts = [(x.start(), x.end(), x.group(1), None) for x in ITEM.finditer(body)]
    # Each numbered item's span; sub-items are split inside it.
    for i, (s, e, no, _) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        chunk = body[e:end]
        subs = [(x.start(), x.end(), x.group(1)) for x in SUBITEM.finditer(chunk)]
        head = chunk[: subs[0][0]] if subs else chunk
        parent_title = _title(head)
        # The disposition for a consent calendar is written once, after the
        # last sub-item, so it is read from the whole numbered span and then
        # given to every sub-item that has none of its own.
        shared = _disposition(chunk)
        if subs:
            for j, (ss, se, letter) in enumerate(subs):
                send = subs[j + 1][0] if j + 1 < len(subs) else len(chunk)
                piece = chunk[se:send]
                rec = _item(f"{no}{letter}", piece, date, url, parent_title)
                if rec["decision"] is None:
                    rec["decision"], rec["ayes"], rec["noes"] = shared
                items.append(rec)
        else:
            rec = _item(no, chunk, date, url, None)
            items.append(rec)
    return {"date": date, "kind": kind, "url": url, "items": items}


MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def _title(chunk):
    """The item's text: from its number to the first narrative line, one line."""
    cut = NARRATIVE.search(chunk)
    t = chunk[: cut.start()] if cut else chunk
    t = RESOLUTION.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" .;")


def _disposition(chunk):
    mo = MOTION.search(chunk)
    ay = AYES.search(chunk)
    no = NOES.search(chunk)
    decision = None
    if mo:
        decision = re.sub(r"\s+", " ", mo.group(1)).strip()
    elif re.search(r"(?i)\bcontinued\b", chunk):
        decision = "continued"
    elif re.search(r"(?i)\b(removed|withdrawn) from", chunk):
        decision = "removed"
    ayes = re.sub(r"\s+", " ", ay.group(1)).strip() if ay else None
    noes = re.sub(r"\s+", " ", no.group(1)).strip() if no else None
    return decision, ayes, noes


def _item(no, chunk, date, url, parent):
    title = _title(chunk)
    res = RESOLUTION.search(chunk)
    decision, ayes, noes = _disposition(chunk)
    return {
        "date": date, "item": no, "title": title, "parent": parent,
        "resolution": re.sub(r"\s+", "", res.group(1)) if res else None,
        "decision": decision, "ayes": ayes, "noes": noes, "url": url,
        "procedural": not title or bool(PROCEDURAL.match(title)),
        "outside": bool(OUTSIDE.search(title or "")),
    }


# ---- streets ------------------------------------------------------------------

def locate(items, index):
    """Resolve each item's street names against the centreline; keep the misses visible."""
    for it in items:
        named = streets_in_order(it["title"])
        # A street the item is about, as against an address it names: a lease
        # "at 1550 Evans Avenue" is one lot, and is kept apart as an address.
        it["streets"] = index.resolve(corridors(it["title"]))
        it["addresses"] = [s for s in index.resolve(named) if s not in it["streets"]]
        it["streetsRejected"] = [n for n in named if not index.is_street(n)]
        it["cnns"] = sorted({c for n in it["streets"] for c in index.cnns(n)})


def read_all(limit=None):
    """Read every minutes file on the log page. The only function that reaches the network."""
    links = minutes_links()
    print(f"  {len(links)} minutes files linked on the log page")
    if limit:
        links = links[:limit]
    meetings, failed, unparsed = [], [], []
    for i, ln in enumerate(links, 1):
        try:
            text = pdf_text(ln["url"])
        except Exception as exc:
            failed.append({"url": ln["url"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not text:
            failed.append({"url": ln["url"], "error": "not a PDF or pdftotext failed"})
            continue
        mt = parse_minutes(scrub(text), ln["url"])
        if not mt or not mt["items"]:
            unparsed.append(ln["url"])
            continue
        mt["file"] = ln["file"]
        mt["label"] = ln["label"]
        meetings.append(mt)
        if i % 10 == 0:
            print(f"  minutes: {i}/{len(links)}")
    meetings.sort(key=lambda m: m["date"], reverse=True)
    return [{"meetings": meetings, "failed": failed, "unparsed": unparsed, "log": LOG}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true", help="ignore the extract; re-read every minutes PDF")
    ap.add_argument("--update", action="store_true",
                    help="re-read the log page and read only minutes files not read before")
    ap.add_argument("--limit", type=int, help="only this many minutes files (never written to the tracked extract)")
    args = ap.parse_args()
    global UPDATE
    UPDATE = args.update
    os.makedirs(OUT, exist_ok=True)

    if args.limit:
        rec, today = scrub(read_all(args.limit))[0], dt.date.today().isoformat()
    else:
        ex = Extract("sfpuc-commission").fetch_or_read(
            "minutes", read_all, refresh=args.refetch or args.update, meta={"site": "sfpuc.gov", "log": LOG})
        print(f"  extract: {ex}")
        rec, today = ex.records[0], ex.fetched_on.isoformat()
        if args.update:
            # No change marker: the bound is the log page, re-read every run,
            # and any minutes file it lists that was never read.
            from lib import pipeline_state
            pipeline_state.refreshed("listing:sfpuc-commission",
                                     STALE + [f["url"] for f in rec.get("failed", [])],
                                     version=max((m["date"] for m in rec["meetings"]), default=None),
                                     detail="log page re-read")

    meetings = rec["meetings"]
    index = StreetIndex()
    items = [it for m in meetings for it in m["items"]]
    locate(items, index)
    decided = [it for it in items if not it["procedural"]]
    street = [it for it in decided if it["streets"] and not it["outside"]]
    outside = [it for it in decided if it["streets"] and it["outside"]]
    rejected = collections.Counter(n for it in decided for n in it["streetsRejected"])

    dates = sorted(m["date"] for m in meetings)
    stable.write_json(os.path.join(OUT, "items.json"), {"generated": today, "log": LOG, "meetings": len(meetings),
               "range": [dates[0], dates[-1]] if dates else None,
               "failed": rec["failed"], "unparsed": rec["unparsed"],
               "items": decided, "streetItems": street, "outsideItems": outside}, indent=1, ensure_ascii=True)

    L = [
        "# SFPUC Commission decisions on San Francisco streets", "",
        f"Read from the Commission's own minutes on its [agendas, minutes and resolutions log]({LOG}) "
        f"([primary — read {today}]). {len(meetings)} meetings, {dates[0] if dates else '—'} to "
        f"{dates[-1] if dates else '—'}; {len(decided)} items that were not procedure; "
        f"**{len(street)} of them ({_pct(len(street), len(decided))}) name a street the city's centreline has.** "
        f"A further {len(outside)} name a street the city has but also name a place outside it — the water system runs "
        f"from Tuolumne County to the Peninsula, and its Skyline Boulevard is San Mateo's — and are left out. "
        f"{len(rec['failed'])} files could not be read and {len(rec['unparsed'])} parsed to no items; both are listed at the end.",
        "",
        "**What this record is.** The Commission decides SFPUC's contracts and agreements. A water-main "
        "or sewer job that opens a street appears here as a contract award naming the streets it runs on; "
        "what happens to the surface afterwards is settled in that job's scope, not in any transport body's "
        "record. So this is the third leg beside the [SFMTA engineering hearings](../sfmta-hearings/bike-items.md) "
        "and the [SFMTA Board](../sfmta-board/bike-items.md).",
        "",
        "| Date | Item | Resolution | Decision | Streets | What it says |",
        "|---|---|---|---|---|---|",
    ]
    for it in street:
        L.append(f"| [{it['date']}]({it['url']}) | {it['item']} | {it['resolution'] or ''} | "
                 f"{(it['decision'] or 'not recorded')[:60]} | {', '.join(it['streets'])} | {it['title'][:240]} |")
    L += ["", "## Names read as streets that the city does not have", "",
          "Reported, not matched. Most are places outside the city (Hetch Hetchy, Peninsula) or words the parser took for a street.", ""]
    for n, c in rejected.most_common(40):
        L.append(f"- {n} ({c})")
    if rec["failed"]:
        L += ["", "## Files that could not be read", ""] + [f"- {f['url']} — {f['error']}" for f in rec["failed"]]
    if rec["unparsed"]:
        L += ["", "## Files that parsed to no items", ""] + [f"- {u}" for u in rec["unparsed"]]
    stable.write_text(os.path.join(OUT, "items.md"), "\n".join(L) + "\n")
    print(f"sfpuc-commission: {len(meetings)} meetings, {len(decided)} items, {len(street)} naming a city street "
          f"({_pct(len(street), len(decided))}), {len(rec['failed'])} failed → out/sfpuc-commission/")


def _pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "—"


if __name__ == "__main__":
    main()
