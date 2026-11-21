#!/usr/bin/env python3
"""What the SFMTA Board actually voted on, from its agendas and minutes.

    tools/meetings/sfmta-board-records.py                 # writes out/sfmta-board/
    tools/meetings/sfmta-board-records.py --since 2025-03-04
    tools/meetings/sfmta-board-records.py --out DIR

Bryan, 2026-09-20: "yes please see what you can find for MTA board and hearing
records."

Where they are, and where they are not:

  **Not Legistar.** The Board of Supervisors is Legistar client `sfgov` and this
  repo reads it with `tools/meetings/sf_legistar.py`. SFMTA is not on Legistar at all:
  `webapi.legistar.com/v1/sfmta` answers "LegistarConnectionString setting is not
  set up in InSite for client: sfmta", and `sfmta.legistar.com` answers "Invalid
  parameters!". A session that assumed the Board of Supervisors' route works here
  would find nothing and conclude the records do not exist.

  **Not the DataSF dataset either.** `v5uc-gana`, "Municipal Transportation
  Agency Board Resolutions", is a real and useful thing — 14,533 parking, traffic
  and bicycle resolutions geocoded to a street and cross street — and it stops.
  Its rows run 2010 to 2021, with 141 in 2021 against 1,797 in 2019, and DataSF
  last published it on 2024-01-12 while declaring a weekly frequency. It cannot
  see anything after the Biking and Rolling Plan was adopted, which is the whole
  window this repo cares about. Read it for history, never for what is current.

  **Granicus, view 55.** 407 meetings from 2007-07-24 to the current month, each
  with an agenda. This is what the `video` column of `v5uc-gana` was already
  pointing at.

  **Granicus minutes stop in 2008.** Of those 407 meetings, 24 carry a
  `MinutesViewer` link and every one of them is from 2007 or 2008. Nothing since
  has minutes there, so "read the minutes off Granicus" is not a thing that can
  be done, and a session that assumed the agenda link implies a minutes link
  beside it would quietly return nothing for the entire modern record.

  **The minutes are on sfmta.com.** [Resolutions & Legislation](https://www.sfmta.com/resolutions-legislation)
  (SFMTA.com/Resolutions) lists, per meeting, the agenda, every item's own
  document, and the PREVIOUS meeting's minutes — minutes are approved at the
  following meeting, so "8-4-26 MTAB Minutes" appears under September 1. Each is
  a node page carrying one PDF.

An agenda gives item titles; the minutes give what the board did with them. Both
are read here, and an item is reported with its disposition where the minutes
name it.

**Most bikeway legislation never reaches this board.** Items marked with a
diamond on an engineering hearing agenda are approved by the City Traffic
Engineer instead. `tools/meetings/sfmta-hearings.py` reads that record, and without it
the counts here read as a city that legislated almost no bikeways.

Refresh (--update): Granicus gives the Board's meetings no change marker, so
the re-read is bounded: the meeting listing, the minutes index and every
meeting under 60 days old or never read; an older agenda keeps its read. The
check is recorded as `listing:sfmta-board` in data/pipeline-state/sources.json,
failed when any agenda in that bound could not be reached (its last read
kept), so a refresh that keeps failing ages the extract.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import sys
import datetime as dt
import html
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

ROOT = paths.ROOT
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"

HOST = "https://sanfrancisco.granicus.com"
VIEW = 55  # "San Francisco Municipal Transportation Agency (SFMTA)"
INDEX = f"{HOST}/ViewPublisher.php?view_id={VIEW}"

# Words that make an agenda item worth a human read for this repo's purposes.
# Deliberately broad: a false positive costs one read, a miss costs the finding.
# "Class IV" and "quick-build" are here because SFMTA names facilities that way
# in item titles where it does not use the word "bicycle".
TERMS = [
    # Not a bare "cycle": it matches MOTORCYCLE PARKING, which these orders
    # legislate constantly, and "budget cycle". Nine of 68 hearing items
    # were motorcycle parking before this.
    "bike", "bicycl", "bikeway", "cycle track", "cycletrack",
    "cycling", "cyclist",
    "class ii", "class iii", "class iv", "quick.?build", "quick build",
    "slow street", "neighborway", "protected lane", "protected bike",
    "biking and rolling", "north star", "active transportation",
    "vision zero", "traffic calming", "bulb.?out", "road diet",
]
HIT = re.compile("|".join(TERMS), re.I)

TAG = re.compile(r"(?s)<[^>]+>")
DROP = re.compile(r"(?s)<(script|style)\b.*?</\1>")


RESOLUTIONS = "https://www.sfmta.com/resolutions-legislation"
SITE = "https://www.sfmta.com"


def get(url, binary=False, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=90) as fh:
                raw = fh.read()
                return raw if binary else raw.decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def flatten(frag):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", DROP.sub(" ", frag)))).strip()


def meetings():
    """Every meeting Granicus lists for view 55, newest first.

    The index is one table row per meeting carrying a date, a duration, and up
    to three links: the video, the agenda, the minutes. Rows are parsed rather
    than the RSS feed read, because the feed carries only the most recent
    meetings and this wants the whole archive.
    """
    raw = get(INDEX)
    out = []
    for tr in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", raw):
        txt = flatten(tr)
        m = re.search(r"\b(\d{2})/(\d{2})/(\d{2})\b", txt)
        if not m:
            continue
        mm, dd, yy = m.groups()
        date = f"20{yy}-{mm}-{dd}"
        links = dict.fromkeys(("agenda", "minutes"))
        for href in re.findall(r'href="([^"]+)"', tr):
            if "AgendaViewer" in href:
                links["agenda"] = href if href.startswith("http") else "https:" + href
            elif "MinutesViewer" in href:
                links["minutes"] = href if href.startswith("http") else "https:" + href
        clip = re.search(r"clip_id=(\d+)", tr)
        out.append({"date": date, "clipId": clip.group(1) if clip else None,
                    "agenda": links["agenda"], "minutes": links["minutes"]})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


# An agenda's items are numbered lines. Granicus renders them in a table whose
# markup varies by year, so this works off the flattened text and splits on the
# numbering, which every year has in common.
#
# Three things this has to get right, each of which lost a real item first:
#
#   Lettered sub-items are items. The board legislates in them — item 11 on
#   2025-04-15 is "Approving revisions to the side-running protected bikeway ...
#   on Valencia Street" and its 11A..11N are the individual establishments, and
#   on 2026-06-16 it is the other way round: the parent says only "traffic
#   modifications" and the bicycle words are all in 12A..12D. Match the parent
#   alone and you lose the second; treat the sub-items as the parent's text and
#   you lose the first. So each marker, lettered or not, is its own item.
#   Length. A parent whose sub-items run past the cap used to fail the match
#   entirely and vanish rather than truncate — which is how the Valencia item
#   went missing. Sub-items being boundaries makes titles short again, and the
#   cap is generous anyway.
#   Granicus emits "10.2.." with a doubled period in some years.
#
# `--verify` re-reads every agenda and reports any whose raw text matches a term
# while its parsed items do not. That check is what found all three.
ITEM = re.compile(
    r"(?:^|\s)(\d{1,2}(?:\.\d{1,2})*[A-Za-z]?)\.{1,2}\s+(.{6,1200}?)"
    r"(?=\s\d{1,2}(?:\.\d{1,2})*[A-Za-z]?\.{1,2}\s|$)")


MTAB = re.compile(r'<a[^>]+href="(/node/\d+)"[^>]*>\s*([^<]*MTAB[^<]*)\s*</a>')
MD_Y = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2})\s+MTAB\s+Minutes", re.I)
MEDIA = re.compile(r'href="(/media/\d+/download[^"]*)"')


# Any MTAB document, not just the minutes, so the walk knows how far back a
# page has reached and can stop rather than guess a page count.
ANY_MD_Y = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{2})\s+MTAB", re.I)


def minutes_index(since, max_pages=150):
    """date -> node URL for every MTAB minutes document sfmta.com lists.

    Minutes are approved at the following meeting, so the document for August 4
    is listed under September 1. The date in the LABEL is the meeting the
    minutes are OF, which is the one to key on.

    The listing is paged and mixes minutes with every item document, so a page
    is worth about one meeting and a fixed page count is the wrong stopping
    rule: six pages reached 2026-01-20 and silently reported every 2025 meeting
    as having no minutes yet. This walks until a page's own dates fall before
    `since`. The cap is a runaway guard, not a stopping rule: at 40 pages the
    walk stopped at the 2022-11-15 minutes, and every earlier meeting read as
    having none, though the listing carries minutes back to 2019-09-03
    (measured 2026-09-28).

    Incremental: the index read last time is held in
    .cache/sfmta-board-minutes-index.json (gitignored). The listing is newest
    first, so the walk stops at the first page on which every minutes document
    is already held, and the held entries fill in the rest. A run with nothing
    new posted reads page 0 alone, instead of the 90 pages of a full walk.
    """
    held_path = os.path.join(ROOT, ".cache", "sfmta-board-minutes-index.json")
    try:
        held = json.load(open(held_path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        held = {}
    out = {}
    complete = False
    for pg in range(max_pages):
        try:
            raw = get(f"{RESOLUTIONS}?page={pg}")
        except Exception:
            break
        oldest, found = None, False
        page_keys = []
        for href, label in MTAB.findall(raw):
            label = html.unescape(re.sub(r"\s+", " ", label)).strip()
            any_m = ANY_MD_Y.match(label)
            if any_m:
                found = True
                mm, dd, yy = (int(x) for x in any_m.groups())
                d = f"20{yy:02d}-{mm:02d}-{dd:02d}"
                oldest = d if oldest is None else min(oldest, d)
            m = MD_Y.match(label)
            if not m:
                continue
            mm, dd, yy = (int(x) for x in m.groups())
            key = f"20{yy:02d}-{mm:02d}-{dd:02d}"
            out.setdefault(key, SITE + href)
            page_keys.append(key)
        if not found:
            complete = True
            break
        if oldest and oldest < since:
            complete = True
            break
        if held and page_keys and all(held.get(k) == out[k] for k in page_keys):
            # Everything from here down was read before.
            for k, u in held.items():
                out.setdefault(k, u)
            complete = True
            break
    if complete:
        os.makedirs(os.path.dirname(held_path), exist_ok=True)
        with open(held_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
    else:
        # The walk broke off (a page did not answer): the held entries stand
        # in for what was not reached, and nothing is written back.
        for k, u in held.items():
            out.setdefault(k, u)
    return out


def minutes_text(node_url):
    """The minutes PDF's text for one meeting, or None."""
    try:
        raw = get(node_url)
    except Exception:
        return None
    m = MEDIA.search(raw)
    if not m:
        return None
    try:
        pdf = get(SITE + m.group(1), binary=True)
    except Exception:
        return None
    try:
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf,
                           capture_output=True, timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None


# What the minutes record for one item.
#
# The board's minutes print the item number at the start of a line, then the
# item's text and its lettered sub-items, and only after all of them the motion
# and the roll call:
#
#     11. Approving revisions to the side-running protected bikeway ...
#          A. ESTABLISH – GREEN METERED ZONE ...
#          ...
#          On motion to approve:
#          ADOPTED:   AYES – Chen, Felder, Heminger, Henderson, Hinze, Cajina, and Tarlov
#          RESOLUTION No. 250415-036
#
# So the disposition is found by slicing the whole item — from its number to the
# next HIGHER top-level number — and reading the roll call at the end of it. A
# fixed window does not work: the first attempt read 900 characters after the
# number, which on Valencia covered the twelve sub-items and stopped short of
# the vote, and reported all fourteen items as having no disposition.
VOTE = re.compile(
    r"(?m)^\s*(ADOPTED|APPROVED|CONTINUED(?:\s+TO\s+[^\n:]+)?|TABLED|SEVERED"
    r"|WITHDRAWN|FAILED|NO ACTION|REMOVED)\s*:?(.*)$", re.I)
AYES = re.compile(r"AYES\s*[–—-]\s*([^\n]*)", re.I)
NAYES = re.compile(r"(?:NAYES|NOES|NAYS)\s*[–—-]\s*([^\n]*)", re.I)
RESO = re.compile(r"RESOLUTION No\.\s*([0-9-]+)", re.I)


def _names(blob):
    if not blob:
        return 0
    parts = [x.strip() for x in re.split(r",|\band\b", blob) if x.strip()]
    return len([x for x in parts if re.match(r"^[A-Z][A-Za-z'-]+$", x)])


def item_slice(minutes, no):
    """The minutes text for one top-level item, or None."""
    base = re.match(r"^(\d{1,2})", no)
    if not base:
        return None
    n = int(base.group(1))
    start = re.search(r"(?m)^\s*" + str(n) + r"\.\s", minutes)
    if not start:
        return None
    rest = minutes[start.start():]
    nxt = None
    for m in re.finditer(r"(?m)^\s*(\d{1,2})\.\s", rest[1:]):
        if int(m.group(1)) > n:
            nxt = m.start() + 1
            break
    return rest[:nxt] if nxt else rest


def disposition(minutes, no, title):
    """How the minutes recorded item `no`, as a short line, or None.

    Returns None rather than a guess — an item whose disposition cannot be
    located is reported as not found, because a wrong disposition is worse than
    a missing one.
    """
    if not minutes:
        return None
    seg = item_slice(minutes, no)
    if not seg:
        return None
    votes = VOTE.findall(seg)
    if not votes:
        return None
    verb, tail = votes[-1]
    out = verb.strip().upper()
    ayes, nayes = AYES.search(seg), NAYES.search(seg)
    if ayes:
        n_a, n_n = _names(ayes.group(1)), _names(nayes.group(1)) if nayes else 0
        out += f" — {n_a} aye" + ("s" if n_a != 1 else "")
        if n_n:
            out += f", {n_n} nay" + ("s" if n_n != 1 else "")
    reso = RESO.search(seg)
    if reso:
        out += f" (Resolution {reso.group(1)})"
    return out


# Some agendas print only the calendar heading for an item — 2025-09-02's item
# 11 is literally "11. REGULAR CALENDAR" — and the item's real title, with the
# street in it, appears only in the minutes. Carrying the heading through makes
# the item unusable: it names no street and links to no project.
CALENDAR_HEADING = re.compile(
    r"^(regular|consent|closed session)?\s*calendar$|^public comment$",
    re.I)


def headline_from_minutes(minutes, no):
    """An item's real title, taken from the minutes when the agenda lacks one."""
    sl = item_slice(minutes, no)
    if not sl:
        return None
    body = re.sub(r"^\s*\d{1,2}\.\s*", "", sl)
    # The title runs to the first lettered action or the parenthetical that
    # carries the CEQA determination, whichever comes first.
    body = re.split(r"\n\s*[A-Z]\.\s|\s\(The\s", body)[0]
    body = re.sub(r"\s+", " ", body).strip(" :;")
    return body[:400] or None


def items_from(txt):
    """Agenda items from one agenda's already-flattened text."""
    body = txt.split("Call to Order", 1)
    txt = "Call to Order" + body[1] if len(body) > 1 else txt
    return [{"no": no, "title": title.strip()} for no, title in ITEM.findall(txt)]


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
from extract import Extract  # noqa: E402


def read_board(since, prev=None, recent_days=60):
    """List the meetings, read every agenda since `since`, join the minutes.

    With `prev` (the extract's last record, under --update), a meeting older
    than `recent_days` whose agenda was already read keeps its earlier
    result, so only new meetings and those whose minutes may still arrive are
    fetched. An agenda posted long ago does not change.

    The only function that reaches the network. What it returns is written
    to data/extract/sfmta-board/ and tracked, so a second run — and a fresh
    clone — builds from disk and makes no request.
    """
    mtgs = meetings()
    print(f"  {len(mtgs)} meetings listed, {mtgs[-1]['date']} .. {mtgs[0]['date']}")

    want = [m for m in mtgs if m["date"] >= since and m["agenda"]]
    print(f"  {len(want)} with an agenda since {since}")

    mindex = minutes_index(since)
    print(f"  {len(mindex)} MTAB minutes documents listed on sfmta.com")
    mcache = {}

    cutoff = (dt.date.today() - dt.timedelta(days=recent_days)).isoformat()
    held = {a["agenda"]: a for a in (prev or {}).get("agendas", []) if a.get("itemCount") is not None}
    prev_hits = collections.defaultdict(list)
    for h in (prev or {}).get("matches", []):
        prev_hits[h["date"]].append(h)
    prev_unparsed = set((prev or {}).get("unparsed", []))

    hits, fetched, failed, unparsed = [], 0, [], []
    stale = []  # agendas a re-read could not reach; the last read kept
    for i, m in enumerate(want, 1):
        if m["date"] < cutoff and m["agenda"] in held:
            m["itemCount"] = held[m["agenda"]]["itemCount"]
            hits.extend(prev_hits.get(m["date"], []))
            if m["date"] in prev_unparsed:
                unparsed.append(m["date"])
            fetched += 1
            continue
        try:
            raw = flatten(get(m["agenda"], tries=2))
            # An agenda that read with items and now reads with none is a
            # short read (Granicus served the 2026-08-04 agenda empty on
            # 2026-09-29, after 13 items the run before), not a meeting that
            # lost its agenda: keep the last read, as for a failed fetch.
            if not items_from(raw) and (held.get(m["agenda"]) or {}).get("itemCount"):
                raise ValueError("agenda read with no items")
        except Exception as exc:
            if m["agenda"] in held:
                # A failed re-read keeps what the last read found, and says so,
                # rather than dropping the meeting's items from the record.
                print(f"  !! {m['date']}: agenda re-read failed ({type(exc).__name__}); keeping the last read")
                stale.append(m["date"])
                m["itemCount"] = held[m["agenda"]]["itemCount"]
                hits.extend(prev_hits.get(m["date"], []))
                if m["date"] in prev_unparsed:
                    unparsed.append(m["date"])
                fetched += 1
                continue
            failed.append(m["date"])
            continue
        items = items_from(raw)
        fetched += 1
        m["itemCount"] = len(items)
        # A sub-item read alone says "ESTABLISH - CLASS IV BIKEWAY" and not on
        # which street or as part of what, because that is in the parent item
        # the board actually voted. So carry the parent's title with it.
        by_no = {it["no"].lower(): it["title"] for it in items}
        matched = [it for it in items if HIT.search(it["title"])]
        if matched and m["date"] in mindex and m["date"] not in mcache:
            mcache[m["date"]] = minutes_text(mindex[m["date"]])
        mins = mcache.get(m["date"])
        for it in matched:
            parent = re.match(r"^(\d{1,2}(?:\.\d{1,2})*)[A-Za-z]$", it["no"])
            pno = parent.group(1) if parent else it["no"]
            ptitle = by_no.get(parent.group(1).lower()) if parent else None
            if mins and (ptitle is None or CALENDAR_HEADING.match(ptitle or "")):
                ptitle = headline_from_minutes(mins, pno) or ptitle
            hits.append({**it, "date": m["date"], "agenda": m["agenda"],
                         "minutes": mindex.get(m["date"]),
                         "disposition": disposition(mins, pno, it["title"]),
                         "parent": ptitle})
        # The parser is the weak point, so it checks itself: an agenda whose raw
        # text names a term while none of its parsed items do means an item was
        # dropped or truncated, not that the meeting had no such item.
        if HIT.search(raw) and not matched:
            unparsed.append(m["date"])
        if i % 5 == 0:
            print(f"  agendas: {i}/{len(want)}")
    # An agenda can print one item twice (the 2023-10-03 Vision Zero update,
    # item 12); the same item from the same agenda is one decision, not two.
    seen, uniq = set(), []
    for h in hits:
        k = json.dumps(h, sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    hits = uniq
    if unparsed:
        print(f"  !! {len(unparsed)} agendas match on raw text but produced no "
              f"matching item: {', '.join(unparsed)}")
    STALE[:] = stale
    return [{"meetings": mtgs, "agendas": want, "matches": hits, "fetched": fetched,
             "failed": failed, "unparsed": unparsed, "minutesIndex": mindex}]


# Agendas the last read_board() could not reach, whose last read was kept.
# Not written to the extract, which a rerun with nothing new must leave as it is.
STALE = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "sfmta-board"))
    ap.add_argument("--verify", action="store_true",
                    help="re-read each agenda and report any whose raw text "
                         "matches a term while no parsed item does")
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the extract and re-download every agenda")
    ap.add_argument("--update", action="store_true",
                    help="re-read only meetings under 60 days old and ones not yet read")
    ap.add_argument("--since", default="2025-03-04",
                    help="fetch agendas from this date on (default: the day the "
                         "Biking and Rolling Plan was adopted)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    held = Extract("sfmta-board").read(f"since-{args.since}") if args.update else None
    prev = held.records[0] if held and held.records else None
    ex = Extract("sfmta-board").fetch_or_read(
        f"since-{args.since}", lambda: read_board(args.since, prev),
        refresh=args.refetch or args.update, meta={"site": INDEX, "since": args.since})
    print(f"  extract: {ex}")
    today = ex.fetched_on.isoformat()
    rec = ex.records[0]
    mtgs, want, hits = rec["meetings"], rec["agendas"], rec["matches"]
    fetched, failed, unparsed = rec["fetched"], rec["failed"], rec["unparsed"]
    mindex = rec["minutesIndex"]
    if args.update:
        # No change marker: the bound is the meeting listing plus every
        # meeting under 60 days old. Any agenda in it not reached fails the check.
        from lib import pipeline_state
        pipeline_state.refreshed("listing:sfmta-board", STALE + list(failed),
                                 version=mtgs[0]["date"] if mtgs else None,
                                 detail="listing and meetings under 60 days re-read")

    stable.write_json(os.path.join(args.out, "meetings.json"),
                      {"generated": today, "view": INDEX, "since": args.since,
                       "meetings": mtgs, "matches": hits}, end="", ensure_ascii=True, indent=1)

    by_date = {}
    for h in hits:
        by_date.setdefault(h["date"], []).append(h)

    L = [
        "# SFMTA Board items that mention the bike network",
        "",
        f"Generated {today} by `tools/meetings/sfmta-board-records.py`. **Do not edit this "
        "file by hand — the next run overwrites it.**",
        "",
        f"[SFMTA Board archive on Granicus]({INDEX}) lists **{len(mtgs)} meetings**, "
        f"{mtgs[-1]['date']} to {mtgs[0]['date']}. This reads the "
        f"{fetched} agendas from **{args.since}**, the day the "
        "[Biking and Rolling Plan](https://www.sfmta.com/projects/biking-and-rolling-plan) "
        f"was adopted, and flags **{len(hits)} items** across "
        f"{len(by_date)} meetings.",
        "",
        "**An agenda title is a pointer, not a finding.** It says the board "
        "considered something on a date. How the vote went is in that meeting's "
        "minutes, linked beside each date below, and nothing here reads them.",
        "",
    ]
    if failed:
        L += [f"Agendas that could not be fetched: {', '.join(sorted(failed))}.", ""]
    if unparsed:
        L += [f"**Agendas whose text names one of these terms while no item "
              f"parsed out of them did — the parser dropped something and these "
              f"need a human read: {', '.join(sorted(unparsed))}.**", ""]
    for date in sorted(by_date, reverse=True):
        rows = by_date[date]
        m = next(x for x in want if x["date"] == date)
        links = f"[agenda]({m['agenda']})"
        if mindex.get(date):
            links += f" · [minutes]({mindex[date]})"
        L += [f"## {date} — {len(rows)} item{'s' if len(rows) != 1 else ''}", "",
              links, ""]
        shown = set()
        for h in rows:
            if h.get("parent") and h["parent"] not in shown:
                L.append(f"- {h['parent']}")
                shown.add(h["parent"])
            indent = "  " if h.get("parent") else ""
            L.append(f"{indent}- **{h['no']}.** {h['title']}")
            if h.get("disposition"):
                L.append(f"{indent}  <br>*Minutes:* {h['disposition']}")
            elif date in mindex:
                L.append(f"{indent}  <br>*The minutes for this meeting do not "
                         "name this item number — read them.*")
            else:
                L.append(f"{indent}  <br>*No minutes published for this meeting "
                         "yet. They are approved at the following meeting.*")
        L.append("")
    L += [
        "## What this does not say",
        "",
        "- **The match is on words, not meaning.** The term list is deliberately "
        "broad — a false positive costs one read and a miss costs the finding — so "
        "expect items here that turn out to be about something else.",
        "- **An agenda is what was scheduled.** An item can be continued, severed "
        "or withdrawn, and only the minutes record that.",
        "- **Engineering public hearings are not in here.** They are where much "
        "bikeway legislation is actually approved, and they are not on Granicus; "
        "they are noticed on sfmta.com. That is a gap, not an absence.",
        "",
    ]
    stable.write_text(os.path.join(args.out, "bike-items.md"), "\n".join(L) + "\n")

    print(f"{len(hits)} flagged items across {len(by_date)} meetings → {args.out}/")


if __name__ == "__main__":
    main()
