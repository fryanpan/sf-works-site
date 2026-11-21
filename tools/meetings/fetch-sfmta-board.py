#!/usr/bin/env python3
"""Mirror every SFMTA Board of Directors agenda item since 2019, with its disposition from the minutes where sfmta.com has them, to data/sfmta-board/.

    tools/meetings/fetch-sfmta-board.py                   # since 2019-01-01; fetches only what is new or draft
    tools/meetings/fetch-sfmta-board.py --since 2015-01-01
    tools/meetings/fetch-sfmta-board.py --rewrite         # no listing fetch; re-apply the minutes to every meeting

tools/meetings/sfmta-board-records.py keeps only the items that name a bike word,
139 of about 3,200 since 2019, so an item that names a project without one
(a contract award for "Geary Rapid", a Slow Streets program) was invisible to
the project record. This keeps every item, with its full title.

Agendas: SFGovTV's Granicus view 55, the same archive sfmta-board-records.py
reads. Dispositions: the minutes PDFs listed on sfmta.com's Resolutions &
Legislation page, which reach back to the 2018-12-18 meeting (measured
2026-09-29: 168 of the 180 meetings mirrored since 2019 have minutes there);
items of a meeting without minutes carry no disposition. The minutes
parser and the minutes index are sfmta-board-records.py's own, imported
rather than copied, so the two readers cannot drift. Minutes PDFs are kept
in the byte cache (.cache/sfmta-board-minutes/): once posted they do not
change, so a rerun reads each from disk.

Granicus indexes some consent calendars as the one point "10 Consent
Calendar will be acted upon by a single vote" with nothing under it; the
minutes print the calendar's items as 10.1, 10.2 ... ("(10.1)" from 2019-12
to 2021-08), each with its resolution number, and those are added under the
calendar ("from": "minutes"). Others it indexes only in part (one item, a
lettered part, or letters of its own); every item the minutes print that the
index does not carry under its own number is added the same way. An item
severed from the calendar takes its own vote, never the calendar's.

Each meeting records the minutes parser it was read with ("parser"). Every
run re-reads, from disk and the minutes byte cache, each meeting read with an
older parser, so a fix to the reading reaches meetings already final.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib.fetch import Fetcher, pdf_text  # noqa: E402
from lib.mirror import Mirror, summary  # noqa: E402
from lib import granicus  # noqa: E402

board = paths.load("sfmta-board-records.py")

VIEWS = {55: "SFMTA Board of Directors"}
NOTES = ["Agendas from SFGovTV's Granicus view 55; dispositions from the minutes on "
         "https://www.sfmta.com/resolutions-legislation, which reach back to the 2018-12-18 meeting; a consent "
         "calendar the agenda index lacks, or holds only in part, gets its other items from the minutes."]


def minutes_reader(refetch=False):
    """A minutes reader that keeps each page and PDF in the byte cache: once posted, minutes do not change."""
    f = Fetcher("sfmta-board-minutes", pause=0.7, refetch=refetch)

    def read(node_url):
        try:
            page = f.get(node_url)
            m = board.MEDIA.search(page)
            return pdf_text(f.get(board.SITE + m.group(1), binary=True)) if m else None
        except Exception as exc:  # noqa: BLE001
            print("  minutes %s unreadable (%s); the meeting keeps what it had" % (node_url, exc))
            return None
    return read


# The consent calendar's own items. Granicus indexes 46 of the 180 meetings'
# consent calendars as one point with nothing under it, and that is where most
# street legislation is approved ("10.3. Approving the two-way traffic
# conversion ... on Steuart Street", 2024-04-16).
CONSENT = re.compile(r"(?i)^\s*(?:consent calendar|all matters listed hereunder constitute a consent calendar)")
# The calendar's heading in the minutes: "10. All matters listed hereunder
# constitute a Consent Calendar ..." (or "10. CONSENT CALENDAR").
MINUTES_CALENDAR = re.compile(r"(?m)^\s*(\d{1,2})\.\s+(?:All matters listed hereunder constitute a Consent Calendar"
                              r"|CONSENT CALENDAR)")


# Bumped whenever the reading of the minutes changes. Every meeting records
# the version it was read with, and a run re-reads (from the byte cache, no
# agenda refetch) each meeting read with an older one, so a parser fix reaches
# the final meetings too. 2: "(10.1)" numbering, severed items. 3: the items
# of a calendar Granicus indexes only in part; "amend ... and approve as
# amended" read as the calendar's vote. 4: a calendar headed "All matters
# listed hereunder constitute a Consent Calendar", or missing from the index
# altogether, found from the minutes' own heading.
PARSER = 4

# A consent item's number at the start of its line: "10.1." since 2021-09,
# "(10.1)" from 2019-12 to 2021-08.
def _sub_header(n):
    return re.compile(r"(?m)^[ \t\f\v]*(?:\(%s\.(\d{1,2})\)|%s\.(\d{1,2})\.?)[ \t]+(?=\S)" % (n, n))


# "RESOLUTION No. 240416-036" now, "RESOLUTION 200303-025" before 2021.
RESO = re.compile(r"RESOLUTION\s+(?:No\.?\s*)?(\d{6}-\d{3})", re.I)
MOTION = re.compile(r"(?s)On motion to\s+(.{0,900}?):")
_LETTERS = r"((?:[\s,]*(?:and\s+)?\(?[A-Z]\)?(?![a-z]))*)"


def _vote(chunk):
    """The roll call that follows a motion, as board.disposition prints it, or None."""
    votes = board.VOTE.findall(chunk)
    if not votes:
        return None
    out = votes[0][0].strip().upper()
    ayes, nayes = board.AYES.search(chunk), board.NAYES.search(chunk)
    if ayes:
        n_a, n_n = board._names(ayes.group(1)), board._names(nayes.group(1)) if nayes else 0
        out += " — %d aye%s" % (n_a, "s" if n_a != 1 else "")
        if n_n:
            out += ", %d nay%s" % (n_n, "s" if n_n != 1 else "")
    return out


def severed(seg, n):
    """{item number: set of lettered parts severed, empty for the whole item} from a calendar's minutes.

    "Item 10.2 was severed", "Item 10.1 G, H and I were severed", "Directors
    ... severed Item 10.1", "requested that Item 10.1(K) be severed", "On
    motion to approve the Consent Calendar (Item 10.5 severed)", and "All
    items were severed". An item absent from the result was not severed.
    """
    out = {}
    num = r"%s\.(\d{1,2})" % n

    def add(k, letters):
        parts = set(re.findall(r"\b([A-Z])\b", letters or ""))
        if k in out and (not out[k] or not parts):
            out[k] = set()  # the whole item, once any mention says so
        else:
            out[k] = out.get(k, set()) | parts
    for m in re.finditer(r"Items?\s+" + num + _LETTERS + r"\s+(?:was|were)\s+severed", seg):
        add(m.group(1), m.group(2))
    for m in re.finditer(r"sever(?:ed)?\s+Items?\s+" + num + _LETTERS, seg):
        add(m.group(1), m.group(2))
    for m in re.finditer(r"Item\s+" + num + _LETTERS + r"\s+be\s+severed", seg):
        add(m.group(1), m.group(2))
    for m in MOTION.finditer(seg):
        paren = re.search(r"\(([^)]*\b(?:severed|removed))\)", m.group(1))
        if paren:
            for x in re.finditer(num + _LETTERS, paren.group(1)):
                add(x.group(1), x.group(2))
    if re.search(r"(?i)\ball items were severed\b", seg):
        for h in _sub_header(n).finditer(seg):
            add(h.group(1) or h.group(2), "")
    return out


def consent_items(minutes, parent):
    """The numbered items (10.1, 10.2 ...) the minutes print under a consent calendar index point.

    Each item takes the calendar's vote unless it was severed. A severed item
    takes the vote the minutes record for it (a motion inside its own text,
    or one that names it); with none, a calendar vote that does not exclude
    it; with neither, no decision, and "severed": true. Lettered parts
    severed from an item are named after the calendar's vote.
    """
    base = re.match(r"^(\d{1,2})$", str(parent["no"]))
    if not base:
        return []
    n = base.group(1)
    seg = board.item_slice(minutes, n) or ""
    subs = list(_sub_header(n).finditer(seg))
    if not subs:
        return []
    motions = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip(),
                _vote(seg[m.end():(nx.start() if nx else len(seg))]))
               for m, nx in zip(MOTION.finditer(seg), list(MOTION.finditer(seg))[1:] + [None])]
    named = re.compile(r"\b%s\.(\d{1,2})\b" % n)
    group = re.compile(r"\[([^\]]*)\]|\(((?:[^()]|\([^()]*\))*)\)")

    def listing(text):
        """(included, excluded) item numbers a motion's bracket names: "(Items 10.2 and 10.3)",
        "[Items 10.1(A-J), 10.2 & 10.3]", "(Item 10.2 severed)"."""
        inc, exc = set(), set()
        for g in group.finditer(text):
            inner = g.group(1) if g.group(1) is not None else g.group(2)
            nos = set(named.findall(inner))
            # "(Items 10.1-10.3)"
            for a, b in re.findall(r"\b%s\.(\d{1,2})\s*[-–]\s*(?:%s\.)?(\d{1,2})\b" % (n, n), inner):
                nos.update(str(x) for x in range(int(a), int(b) + 1))
            (exc if re.search(r"(?i)sever|removed", inner) else inc).update(nos)
        return inc, exc

    # The calendar's own vote: it says "Consent Calendar", or its bracket
    # lists what it approves or leaves out ("On motion to approve (Item 10.2
    # severed)", "On motion to approve [Items 10.1(A-J), 10.2 & 10.3]").
    cal = [x for x in motions if re.search(r"(?i)consent calendar", x[1])
           or listing(x[1])[1] or len(listing(x[1])[0]) >= 2]
    if not cal:
        cal = [x for x in motions if not named.search(x[1]) and not re.search(r"(?i)\bamend", x[1])][-1:]
    # "On motion to amend Item 10.2D to remove ... and approve as amended"
    # (2024-11-19): with no other calendar vote, an approving motion after the
    # last item is the calendar's vote, and each item it amends says so.
    amended = False
    if not cal:
        cal = [x for x in motions if x[0] > subs[-1].start()
               and re.search(r"(?i)\band\s+approve(?:\s+as\s+amended)?\s*$", x[1])][-1:]
        amended = bool(cal)
    cal = cal[-1] if cal else None
    reg = re.search(r"REGULAR CALENDAR", seg)
    stop = reg.start() if reg else len(seg)
    if cal is None and not motions:
        # Some minutes print the calendar's roll call with no motion line
        # before it (2023-09-05): the last vote after the last item is it.
        tail = [v for v in board.VOTE.finditer(seg, subs[-1].end(), stop)]
        if tail:
            cal = (tail[-1].start(), "approve the Consent Calendar", _vote(seg[tail[-1].start():stop]))
    included, excluded = listing(cal[1]) if cal else (set(), set())
    # The last item's text ends where the calendar's vote begins.
    cut = cal[0] if cal and (re.search(r"(?i)consent calendar", cal[1]) or included or excluded) else len(seg)
    cut = min(cut, stop)
    sev = severed(seg, n)
    out = []
    for i, m in enumerate(subs):
        k = m.group(1) or m.group(2)
        # A calendar vote printed before the severed items (2023-05-16) does
        # not end the items after it.
        last_end = cut if cut > m.end() else stop
        start, end = m.end(), subs[i + 1].start() if i + 1 < len(subs) else last_end
        span = seg[start:max(start, end)]
        # The item's own words stop at its public comment or roll call.
        body = re.split(r"PUBLIC COMMENT|On motion|REGULAR CALENDAR|\n\s*Items?\s+%s\.%s\b[^\n]*sever" % (n, k), span)[0]
        # The headline runs to its lettered actions, its CEQA parenthetical or
        # its resolution number, whichever comes first.
        head = re.split(r"\n\s*[A-Z]\.\s|\(The\s|\(Explanatory|RESOLUTION\b|\n\s*\n", body)[0]
        head = re.sub(r"\s+", " ", head).strip(" :;")
        if len(head) < 8:
            continue
        resos = RESO.findall(span)
        # Its own votes: a motion inside its text, or one elsewhere that names
        # it. The last that is not an amendment is the one that decided it.
        own = [x for x in motions if x is not cal and x[2] and (
            start <= x[0] < start + len(span) or k in named.findall(x[1]))]
        own = sorted(own, key=lambda x: x[0])
        final = [x for x in own if not re.match(r"(?i)amend\b", x[1])] or own
        whole = k in sev and not sev[k]
        in_cal = cal is not None and not (k in excluded and whole) and (not included or k in included)
        cal_vote = cal[2] if in_cal else None
        rec = {"no": "%s.%s" % (n, k), "title": head[:600],
               "text": re.sub(r"\s+", " ", body).strip()[:1500],
               "parent": "Consent Calendar", "from": "minutes"}
        if whole:
            rec["severed"] = True
            if final:
                o = final[-1]
                plain = re.match(r"(?i)approve(?:\s+as amended|\s+\[?items?\s+%s\.%s\]?)?\s*$" % (n, k), o[1])
                vote = o[2] + ("" if plain else " (on motion to %s)" % o[1][:120])
            else:
                vote = cal_vote
        else:
            vote = cal_vote
            if vote and amended and k in re.findall(r"\b%s\.(\d{1,2})(?=[A-Z]?\b)" % n, cal[1]):
                vote += " (on motion to %s)" % cal[1][:160]
            if k in sev:
                parts = ", ".join(sorted(sev[k]))
                vote = (vote or "no calendar vote found") + "; part%s %s severed" % ("s" if len(sev[k]) > 1 else "", parts)
                if final:
                    vote += " and voted separately: " + final[-1][2]
        if not vote and re.search(r"(?i)\b(?:item|it) was continued\b", span):
            vote = "CONTINUED"  # "The item was continued to a future meeting." (2021-08-03)
        rec["decision"] = (vote + (" (Resolution %s)" % resos[-1] if resos else "")) if vote else None
        out.append(rec)
    return out


def item_order(no):
    """Agenda order of an item number: 10 before 10.1 before 10.2 before 11."""
    m = re.match(r"^(\d+)(?:\.(\d+))?([a-z]?)", str(no).lower())
    return (int(m.group(1)), int(m.group(2) or 0), m.group(3)) if m else (999, 0, str(no))


def _same_head(a, b):
    """True when two titles open with the same forty letters, case and spacing aside."""
    def key(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())[:40]
    return bool(key(a)) and key(a) == key(b)


def calendar_point(n, items):
    """The consent calendar's own point, read from the minutes, for a meeting whose agenda index lacks it."""
    votes = [re.split(r" \(Resolution |; part", c["decision"])[0] for c in items
             if c.get("decision") and not c.get("severed")]
    return {"no": n, "title": "Consent Calendar", "from": "minutes",
            "decision": max(sorted(set(votes)), key=votes.count) if votes else None}


def enrich_with(rec, url, text):
    """Dispositions and consent items from one meeting's minutes.

    Idempotent: what an earlier run took from the minutes is dropped and read
    again, so a change in the reading reaches meetings already mirrored."""
    rec["items"] = [it for it in rec["items"] if it.get("from") != "minutes"]
    rec["sources"]["minutes"] = url
    rec["status"] = "final"
    rec["parser"] = PARSER
    calendars = {}
    for it in rec["items"]:
        base = it["no"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        # A consent item Granicus indexes on its own ("10.3") takes the vote
        # consent_items() reads for it, so a severed one does not inherit the
        # calendar's (or another severed item's) roll call.
        sub = re.match(r"^(\d{1,2})\.(\d{1,2})$", base)
        if sub:
            if sub.group(1) not in calendars:
                calendars[sub.group(1)] = {c["no"]: c for c in consent_items(text, {"no": sub.group(1)})}
            c = calendars[sub.group(1)].get(base)
            if c is not None:
                it.pop("decision", None)
                it.pop("severed", None)
                if c.get("decision"):
                    it["decision"] = c["decision"]
                if c.get("severed"):
                    it["severed"] = True
                continue
        d = board.disposition(text, base, it["title"])
        if d:
            it["decision"] = d
    # The calendar's items the agenda index lacks, from the minutes. Granicus
    # indexes some calendars as one point and others only in part: one item
    # ("10.2" alone, 2025-01-21), a lettered part ("10.1K", 2023-06-06),
    # letters of its own ("10a"-"10d", 2020-09-01), its first item under the
    # calendar's own number ("10" for the warrants, 2019-10-01), or not at
    # all (item 10 is missing from the 2019-05-21 and 2025-07-15 indexes). An
    # item indexed under its own number, or anywhere under the calendar with
    # the same title ("10.3E", 2019-09-03), is left to the index; every other
    # item the minutes print is added, after the calendar's own point.
    cal_nos = {str(it["no"]) for it in rec["items"]
               if CONSENT.match(it.get("title") or "") and re.match(r"^\d{1,2}$", str(it["no"]))}
    head = MINUTES_CALENDAR.search(text)
    if head:
        cal_nos.add(head.group(1))
    nos = {str(it["no"]) for it in rec["items"]}
    add = {}
    for n in cal_nos:
        if n not in calendars:
            calendars[n] = {c["no"]: c for c in consent_items(text, {"no": n})}
        under = [x for x in rec["items"] if re.match(r"^%s(?:$|[A-Za-z.])" % n, str(x["no"]))]
        new = sorted((c for c in calendars[n].values() if c["no"] not in nos
                      and not any(_same_head(x.get("title"), c["title"]) for x in under)),
                     key=lambda c: item_order(c["no"]))
        if new:
            # A calendar the index lacks gets its own point, carrying the vote
            # its items took.
            add[n] = new if n in nos else [calendar_point(n, new)] + new
    out = []
    for it in rec["items"]:
        no = str(it["no"])
        for n in sorted((n for n in add if n not in nos and item_order(n) < item_order(no)), key=int):
            out += add.pop(n)
        out.append(it)
        if no in add:
            out += add.pop(no)
    for n in sorted(add, key=int):
        out += add[n]
    rec["items"] = out
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--update", action="store_true",
                    help="the default behaviour, named for the orchestrator: list the meetings, fetch only new and "
                         "draft ones, then re-read from disk every meeting read by an older parser (PARSER)")
    ap.add_argument("--rewrite", action="store_true",
                    help="no listing fetch: re-apply the minutes to every mirrored meeting that has them (each "
                         "minutes PDF from the byte cache; the network only the first time)")
    args = ap.parse_args()
    read_minutes = minutes_reader(args.refetch)
    mirror = Mirror("sfmta-board", "SFMTA Board of Directors", granicus.listing_url(55))

    def enrich_known(rec, mindex=None):
        url = (rec.get("sources") or {}).get("minutes") or (mindex or {}).get(rec["date"])
        text = read_minutes(url) if url else None
        return enrich_with(rec, url, text) if text else rec

    if args.rewrite:
        print("  rewrote %d meetings from disk" % granicus.rewrite(mirror, enrich_known, NOTES))
        return

    fetcher = Fetcher("sfmta-board", pause=0.5, refetch=args.refetch)
    # No page cap of our own: at 80 pages the walk stopped at the 2019-09-03
    # minutes, and every earlier meeting read as having none, though the
    # listing carries them back to 2018-12-18 (2026-09-29).
    mindex = board.minutes_index(args.since)
    print("  %d minutes documents listed on sfmta.com, earliest %s" % (len(mindex), min(mindex) if mindex else "-"))

    def enrich(rec):
        url = mindex.get(rec["date"])
        text = read_minutes(url) if url else None
        rec["parser"] = PARSER
        return enrich_with(rec, url, text) if text else rec

    idx = granicus.mirror_views(mirror, fetcher, VIEWS, args.since, enrich=enrich,
                                notes=NOTES)
    # A final meeting is never fetched again, so a parser change, or minutes
    # posted after the meeting went final, reach it here: from disk and the
    # minutes byte cache, with no agenda refetch.
    n = granicus.reparse(mirror, lambda rec: enrich_known(rec, mindex), PARSER, notes=NOTES,
                         stale=lambda rec: not (rec.get("sources") or {}).get("minutes") and rec["date"] in mindex)
    if n:
        idx = json.load(open(os.path.join(mirror.dir, "index.json"), encoding="utf-8"))
    print("  re-read %d meetings from disk (parser %d)" % (n, PARSER))
    print(summary(idx))


if __name__ == "__main__":
    main()
