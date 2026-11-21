#!/usr/bin/env python3
"""Mirror every Public Works Commission agenda item since its first meeting in 2022 from SFGovTV's Granicus archive to data/public-works-commission/, with consent-calendar items read from the posted agenda.

    tools/meetings/fetch-public-works-commission.py        # fetches only what is new or draft

Its earliest meeting on Granicus is 2022-07-28 (listing read 2026-09-28); the
Commission was created by Proposition B of November 2020 [model knowledge —
verify]. Its agendas award Public Works construction contracts by name
("Union Street Pavement Renovation and Sewer Replacement", 2026-09-24), which
is where such a job first appears as a dated city decision. Before 2022 there
is no commission record to read. Agendas are on Granicus view 218. The agenda is the video index: item
numbers and titles, not the vote.

Consent calendars. The Granicus index of some meetings lists the consent
calendar as one point, "4. Consent Calendar of Routine Matters", and never its
lettered items, which is where many contract awards sit: the Beale Street
Improvement Phase 1 award was item 4h of 2025-03-13, and the Transit U
Improvement Project award item 4b of 2024-10-17. For such a meeting the
lettered items are read from the agenda as posted: the Granicus PDF when the
meeting's agenda is one, otherwise the agenda or adopted minutes PDF that
sfpublicworks.org's commission calendar page links for that date. A meeting
whose posted agenda cannot be found keeps the one point and says so
("consentUnread"); every run looks for it again. The same pass drops the
numbered call-in instructions ("Dial 415-655-0001 ...") that a PDF agenda's
remote-access page put in as items.

Delegated contract reports. Under the Commission's Contract Approval
Delegation Policy (amended April 2024 and September 2025) the Director
approves some contract awards and changes without a Commission vote, and the
Director's Report at each meeting attaches a list of them: "Delegated
Contracts Report", "Delegated Contract Approvals", "Delegated Approvals
Report". Each row is one contract: its ten-digit contract ID, project title,
what was approved ("Extend contract duration by 200 calendar days.") and why.
Those reports are linked only from inside the posted agenda PDF, so every
agenda PDF the commission calendar page lists (and each Granicus agenda that
is a PDF) is read once for such links, and each report once for its rows,
into data/public-works-commission/delegated.json. The calendar page is the
change marker: it is read on every run, and only an agenda it newly lists, or
a report no agenda read so far has linked, reaches the network. An agenda or
report that cannot be read is listed as unread and tried again next run; a
report already read is never replaced. The calendar lists agendas from 2025
on; the earliest report found is dated 2024-12-20, and the 2025-10-23 agenda
names one without linking it. A meeting whose agenda PDF is on neither the
calendar nor Granicus (seven between 2024-10-28 and 2026-06-18, as of
2026-09-29) is listed as meetingsWithNoAgendaRead: a report attached to it is
not seen.

A report's date is the "Date of Report" it prints, else the date in its file
name. Where the two disagree ("Delegated Contracts Report 6-05-25.pdf" prints
"May 5, 2025") both are kept and the later is used, since the approval is
dated no later than the report that lists it and the later date is the one
that cannot overstate how early the record exists; a date after the meeting
the report was attached to is a misprint and is not used. `--delegated-only` runs
this part alone.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import html
import io
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.fetch import Fetcher, pdf_text  # noqa: E402
from lib.mirror import Mirror, summary  # noqa: E402
from lib import granicus  # noqa: E402

VIEWS = {218: "Public Works Commission"}
# Bumped whenever the reading of a meeting changes; a run re-reads from disk
# every meeting stamped with an older one (granicus.reparse). 1: consent
# calendar items from the posted agenda, call-in instructions dropped.
# 2: the "Regular Calendar" heading and the agenda's running page header
# no longer run into an item's title.
PARSER = 2
CALENDAR = "https://sfpublicworks.org/about/public-works-commission-calendar"
SITE = "https://sfpublicworks.org"

CONSENT = re.compile(r"^\s*consent calendar", re.I)
# The remote-access page's numbered steps, which a PDF agenda's item parser
# reads as items 1 to 12 ahead of the real item 1.
CALL_IN = re.compile(r"\b(?:dial\b|press [#‘'*]|you will hear\b|webex\b|speaker line\b|raised? your hand\b"
                     r"|quiet location\b|unmuted\b|welcome caller\b|participants who wish\b|wait for public comment\b"
                     r"|once your time has expired\b|to withdraw your request\b)", re.I)


_PAGES = {}


def calendar_pages(fetcher):
    """The commission calendar page and the meeting pages it links, as HTML, read once per run.

    An unreachable calendar page gives [] and says so; the caller then reads
    nothing new rather than anything less."""
    if "bodies" in _PAGES:
        return _PAGES["bodies"]
    pages = [CALENDAR]
    try:
        raw = fetcher.get(CALENDAR, cache=False)
    except Exception as exc:  # recorded by the caller as unread, not swallowed
        print("  posted agendas: calendar page unreachable (%s: %s)" % (type(exc).__name__, exc))
        _PAGES["bodies"] = []
        return []
    bodies = [raw]
    for href in sorted(set(re.findall(r'href="([^"]+)"', raw))):
        href = html.unescape(href)
        if re.search(r"(?i)commission-meeting|pw-commission-meeting", href) and not href.lower().endswith(".pdf"):
            url = urllib.parse.urljoin(SITE, href)
            if url not in pages:
                pages.append(url)
                try:
                    bodies.append(fetcher.get(url, cache=False))
                except Exception as exc:
                    print("  posted agendas: %s unreachable (%s)" % (url, type(exc).__name__))
    _PAGES["bodies"] = bodies
    return bodies


def calendar_agendas(fetcher):
    """[(meeting date, agenda PDF URL)] for every agenda PDF the calendar and its meeting pages link.

    Wider than posted_documents: a special or joint meeting's agenda ("2026-1-22 PW
    SAS Special Joint Meeting Agenda Amended") is an agenda too, and it is where
    that meeting's delegated report is linked."""
    out = set()
    for body in calendar_pages(fetcher):
        for href in re.findall(r'href="([^"]+\.pdf)"', body, re.I):
            url = urllib.parse.urljoin(SITE, html.unescape(href))
            name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
            if not re.search(r"(?i)\bagenda\b", name):
                continue
            m = re.match(r"(?:PWC\s+)?(\d{4})-(\d{1,2})-(\d{1,2})\b", name)
            date = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else (file_date(url) or "")
            out.add((date, url))
    return sorted(out)


def posted_documents(fetcher):
    """{date: [url, ...]}: the agenda and minutes PDFs sfpublicworks.org's calendar page (and the meeting pages it links) carry.

    A file is dated by its own name ("2025-5-22 PW Commission Agenda v521.pdf",
    "2025-3-13 PWC Minutes adopted 2024-3-27.pdf"): the first date in the name
    is the meeting's. Agendas first, then minutes."""
    bodies = calendar_pages(fetcher)
    out = {}
    for body in bodies:
        for href in re.findall(r'href="([^"]+\.pdf)"', body, re.I):
            url = urllib.parse.urljoin(SITE, html.unescape(href))
            name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
            kind = ("agenda" if re.search(r"(?i)commission agenda", name)
                    else "minutes" if re.search(r"(?i)\bminutes\b", name) else None)
            m = re.match(r"(?:PWC\s+)?(\d{4})-(\d{1,2})-(\d{1,2})\b", name)
            if not kind or not m:
                continue
            date = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
            out.setdefault(date, {}).setdefault(kind, [])
            if url not in out[date][kind]:
                out[date][kind].append(url)
    return {d: v.get("agenda", []) + v.get("minutes", []) for d, v in out.items()}


LETTER = re.compile(r"(?m)^[ \t\f]{2,12}([a-z])[.)][ \t]+(?=\S)")
TOP = re.compile(r"(?m)^[ \t]{0,8}\d{1,2}\.[ \t]+\S|^\s*Regular (Items for Consideration|Calendar)\b|^\s*Closed Session\s*$")
# Where a lettered item's title ends: its staff recommendation, the list of
# attachments, or the action column.
TITLE_END = re.compile(r"(?i)\n[\s•]*(staff recommendation|staff report|minutes\s{3,}|resolution\b)|\s{3,}(action|informational)\s*$",
                       re.M)


def consent_items(text, parent_no):
    """The lettered items under a posted agenda's consent calendar: [{no, title, text}]."""
    head = re.search(r"(?im)^[ \t]{0,8}(\d{1,2})\.[ \t]+consent calendar[^\n]*", text)
    if not head:
        return []
    rest = text[head.end():]
    stop = TOP.search(rest)
    block = rest[:stop.start()] if stop else rest
    # Page furniture a PDF puts between lines: a bare page number.
    block = re.sub(r"(?m)^\s*\d{1,2}\s*$|^\s*Public Works Commission\s*[-–]\s*Meeting agenda[^\n]*$", "", block)
    marks = list(LETTER.finditer(block))
    out = []
    for i, m in enumerate(marks):
        chunk = block[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(block)]
        cut = TITLE_END.search(chunk)
        title = re.sub(r"\s+", " ", chunk[:cut.start()] if cut else chunk).strip()
        body = re.split(r"(?im)^[\s•]*staff report\b|^[\s•]*minutes\s{3,}", chunk)[0]
        body = re.sub(r"\s+", " ", body.replace("•", " ")).strip()
        body = re.sub(r"\s{2,}|\s+(Action|Informational)$", " ", body).strip()
        if len(title) < 4:
            continue
        out.append({"no": "%s%s" % (parent_no, m.group(1)), "title": title[:600],
                    **({"text": body[:1500]} if body != title else {})})
    return out


# ---- delegated contract reports ----------------------------------------------

DELEGATED_PARSER = 2  # 2: a page with contract IDs and no ruled table leaves the report unread
# A report's file name: "Delegated Contracts Report", "Delegated Contract
# Approvals", "Delegated Approvals Report", "Delegated approvals Period". The
# policy itself and its amendments say "Delegation", and are not reports.
REPORT_NAME = re.compile(r"(?i)(?<![a-z])delegated(?![a-z])")  # "Item 2_Delegated": "_" is a word character
CONTRACT_ID = re.compile(r"^1\d{9}$")
SECTIONS = ("Construction", "Professional Services")
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"), 1)}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def pdf_links(raw):
    """Every link URI in a PDF, in page order, each once."""
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            for h in page.hyperlinks:
                uri = (h.get("uri") or "").strip()
                if uri and uri not in out:
                    out.append(uri)
    return out


def report_links(raw):
    """The delegated-report URLs an agenda PDF links."""
    return [u for u in pdf_links(raw)
            if u.lower().endswith(".pdf") and REPORT_NAME.search(urllib.parse.unquote(u.rsplit("/", 1)[-1]))]


def file_date(url):
    """The date in a report's or agenda's file name ("2025-4-3", "12-20-24", "9-1-25"), or None."""
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", name)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"\b(\d{1,2})-(\d{1,2})-(\d{2})\b", name)
        if not m:
            return None
        mo, d, y = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _columns(page):
    """The table's column edges, from its ruled vertical lines: [id, title, request, summary] as (x0, x1)."""
    xs = sorted(e["x0"] for e in page.vertical_edges if e["bottom"] - e["top"] > 5)
    groups = []
    for x in xs:
        if groups and x - groups[-1][-1] < 15:
            groups[-1].append(x)
        else:
            groups.append([x])
    edges = [g[0] for g in groups]
    if len(edges) < 5:
        return None
    # The first five rules bound the four columns; a later rule (a
    # summary-column cell split) is not a column.
    # The first four rules open the four columns and the last closes the
    # table; a rule between (a summary cell split, 2026-09-10) is not a column.
    e = edges[:4] + [edges[-1]]
    return [(e[i], e[i + 1]) for i in range(4)]


def parse_report(raw):
    """{printedDate, rows, empty} for one delegated report PDF, or None when it holds no readable table.

    Rows are anchored on their contract ID. The report centres the ID
    vertically in a row whose title and request wrap over a few lines, so each
    line in those two columns goes to the row whose ID is nearest it on the
    page, within the section (Construction, Professional Services) the line is
    under. The summary column is not read: a summary runs to ten lines, past
    the midpoint between two IDs, and nearest-ID assignment put the tail of
    one row's reason on the next row. The report's own URL carries it."""
    import pdfplumber
    text = pdf_text(raw) or ""
    printed = None
    m = re.search(r"Date of Report:\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1).lower() in MONTHS:
        printed = dt.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    rows = []
    section = None  # a section runs on over a page break
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            cols = _columns(page)
            if not cols:
                # A page with contract IDs but no ruled table would lose its
                # rows in silence; the report is left unread instead.
                if re.search(r"\b1\d{9}\b", page.extract_text() or ""):
                    return None
                continue
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            head = [w for w in words if w["text"] == "Contract" and w["x0"] < cols[0][1]]
            top = min((w["bottom"] for w in head), default=0)
            words = [w for w in words if w["top"] > top and cols[0][0] <= w["x0"] < cols[3][1]]
            # Lines, by their vertical position.
            lines = []
            for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
                if lines and abs(lines[-1][0] - w["top"]) < 3:
                    lines[-1][1].append(w)
                else:
                    lines.append([w["top"], [w]])
            anchors, parts = [], []
            for y, ws in lines:
                joined = " ".join(w["text"] for w in ws).strip()
                if joined in SECTIONS:
                    section = joined
                    continue
                if re.match(r"^Page \d+ of \d+$", joined):
                    continue
                for w in ws:
                    col = next((i for i, (a, b) in enumerate(cols) if a - 2 <= w["x0"] < b), None)
                    if col == 0 and CONTRACT_ID.match(w["text"]):
                        anchors.append({"y": (w["top"] + w["bottom"]) / 2, "section": section,
                                        "contract": w["text"], "cells": {1: [], 2: []}})
                    elif col in (1, 2):
                        parts.append((w["top"], (w["top"] + w["bottom"]) / 2, section, col, w["x0"], w["text"]))
            for top_, mid, sec, col, x, t in parts:
                near = [a for a in anchors if a["section"] == sec]
                if not near:
                    continue
                a = min(near, key=lambda a: abs(a["y"] - mid))
                a["cells"][col].append((round(top_), x, t))
            for a in anchors:
                cell = lambda c: re.sub(r"\s+", " ", " ".join(t for _, _, t in sorted(a["cells"][c]))).strip()
                title, request = EMAIL.sub("", cell(1)), EMAIL.sub("", cell(2))
                rows.append({"contract": a["contract"], "section": a["section"] or "",
                             "title": title, "request": request,
                             "action": "award" if re.search(r"(?i)\baward", request) else "modification"})
    empty = not rows and bool(re.search(r"(?m)^\s*(None|None during the period)\s*$", text))
    if not rows and not empty:
        return None
    return {"printedDate": printed, "rows": rows, "empty": empty}


def read_delegated(mirror, fetcher, posted_agendas):
    """Bring data/public-works-commission/delegated.json up to date. Returns its path.

    posted_agendas: [(meeting date, agenda PDF URL)] from the commission
    calendar page (calendar_agendas), read this run."""
    path = os.path.join(mirror.dir, "delegated.json")
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    if old.get("parser") != DELEGATED_PARSER:
        old = {"agendas": old.get("agendas", [])}  # a new parser re-reads every report, from the byte cache
    agendas = {a["url"]: a for a in old.get("agendas", [])}
    reports = {r["url"]: r for r in old.get("reports", [])}
    unread = []
    # The agenda PDFs to read: every posted agenda on the calendar page, and
    # every Granicus agenda that is a PDF.
    wanted = list(posted_agendas)
    for rec in mirror.all():
        a = (rec.get("sources") or {}).get("agenda")
        if a and rec.get("form") == "pdf":
            wanted.append((rec["date"], a))
    for date, url in wanted:
        if url in agendas:
            continue
        try:
            raw = fetcher.get(url, binary=True)
            if not raw.lstrip()[:5].startswith(b"%PDF"):
                # A Granicus agenda link redirects to the PDF viewer page.
                doc = re.search(rb"(sanfrancisco_[0-9a-f]{16,}\.pdf)", raw)
                if not doc:
                    raise ValueError("not a PDF")
                raw = fetcher.get("%s/DocumentViewer.php?file=%s&view=1" % (granicus.HOST, doc.group(1).decode()),
                                  binary=True)
            links = report_links(raw)
        except Exception as exc:
            unread.append({"url": url, "what": "agenda", "meeting": date, "reason": "%s: %s" % (type(exc).__name__, exc)})
            continue
        agendas[url] = {"url": url, "meeting": date, "reports": links}
    for a in sorted(agendas.values(), key=lambda a: (a["meeting"], a["url"])):
        for url in a["reports"]:
            if url in reports:
                meetings = sorted(set(reports[url]["meetings"]) | {a["meeting"]})
                reports[url]["meetings"] = meetings
                continue
            try:
                raw = fetcher.get(url, binary=True)
                got = parse_report(raw)
            except Exception as exc:
                got, why = None, "%s: %s" % (type(exc).__name__, exc)
            else:
                why = "no table of contracts, and no \"None\" either, was read from it"
            if got is None:
                if not any(u["url"] == url for u in unread):
                    unread.append({"url": url, "what": "report", "meeting": a["meeting"], "reason": why})
                continue
            fdate = file_date(url)
            dates = [d for d in (got["printedDate"], fdate) if d]
            # The report existed by the meeting it was attached to, so a date
            # after that meeting is a misprint ("Date of Report: May 1, 2026"
            # on the report for 2026-04-09).
            dates_ok = [d for d in dates if d <= a["meeting"]] or [a["meeting"]]
            print("  delegated report read: %s (%d rows)" % (urllib.parse.unquote(url.rsplit("/", 1)[-1]), len(got["rows"])))
            reports[url] = {
                "url": url, "file": urllib.parse.unquote(url.rsplit("/", 1)[-1]),
                "meetings": [a["meeting"]],
                "date": max(dates_ok),
                "printedDate": got["printedDate"], "fileDate": fdate,
                **({"datesDisagree": True} if len(set(dates)) > 1 else {}),
                "empty": got["empty"], "rows": got["rows"]}
    out = {
        "body": "public-works-commission",
        "what": "Contracts the Director of Public Works approved under the Commission's Contract Approval Delegation "
                "Policy, as listed in the delegated contract reports attached to the Commission's agendas.",
        "parser": DELEGATED_PARSER,
        "source": CALENDAR,
        "notes": ["A row's date is its report's: the approval is dated no later than that, and the report does not "
                  "give the approval's own date.",
                  "The calendar page lists agendas from 2025 on; earlier reports, if any were attached, are not "
                  "linked from anything this script reads."],
        "agendas": sorted(agendas.values(), key=lambda a: (a["meeting"], a["url"])),
        "reports": sorted(reports.values(), key=lambda r: (r["date"], r["url"])),
        "unread": sorted(unread, key=lambda u: (u["meeting"], u["url"])),
        # Meetings held since the first agenda read whose agenda PDF this
        # script never reaches (the calendar lists none and Granicus's is
        # HTML): a report attached to one of them is not seen.
        "meetingsWithNoAgendaRead": sorted(
            {r["date"] for r in mirror.all()
             if agendas and r["date"] >= min(a["meeting"] for a in agendas.values())}
            - {a["meeting"] for a in agendas.values()}),
    }
    from lib import stable
    stable.write_json(path, out, indent=1)
    n = sum(len(r["rows"]) for r in out["reports"])
    print("  delegated reports: %d from %d agendas, %d contract rows, %d unread"
          % (len(out["reports"]), len(out["agendas"]), n, len(out["unread"])))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2019-01-01")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--update", action="store_true", help="the default: fetch only what is new or draft")
    ap.add_argument("--delegated-only", action="store_true", help="read the delegated contract reports only")
    args = ap.parse_args()
    mirror = Mirror("public-works-commission", "Public Works Commission", granicus.listing_url(218))
    fetcher = Fetcher("public-works-commission", pause=0.5, refetch=args.refetch)
    if args.delegated_only:
        read_delegated(mirror, fetcher, calendar_agendas(fetcher))
        return
    posted = {}
    looked = []

    def posted_for(date):
        if not looked:
            looked.append(True)
            posted.update(posted_documents(fetcher))
        return posted.get(date, [])

    def granicus_pdf(rec):
        """The agenda PDF a meeting's Granicus agenda link redirects to, as text, or None."""
        url = (rec.get("sources") or {}).get("agenda")
        if not url or rec.get("form") != "pdf":
            return None, None
        page = fetcher.get(url, binary=True).decode("utf-8", "replace")
        doc = re.search(r"(sanfrancisco_[0-9a-f]{16,}\.pdf)", page)
        if not doc:
            return None, None
        pdf_url = "%s/DocumentViewer.php?file=%s&view=1" % (granicus.HOST, doc.group(1))
        return pdf_text(fetcher.get(pdf_url, binary=True)), pdf_url

    def enrich(rec):
        rec["parser"] = PARSER
        rec["items"] = [it for it in rec["items"]
                        if it.get("from") != "posted agenda" and not CALL_IN.search(it.get("title") or "")]
        rec.pop("consentUnread", None)
        (rec.get("sources") or {}).pop("postedAgenda", None)
        heads = [it for it in rec["items"] if CONSENT.match(it.get("title") or "")]
        if not heads:
            return rec
        head = heads[0]
        if any(it.get("parent") or re.match(r"^%s[a-z]$" % re.escape(str(head["no"])), str(it.get("no")), re.I)
               for it in rec["items"]):
            return rec
        found, src = [], None
        try:
            text, url = granicus_pdf(rec)
        except Exception as exc:
            text, url = None, None
            print("  %s: Granicus agenda PDF unreachable (%s)" % (rec["date"], type(exc).__name__))
        if text:
            found, src = consent_items(text, head["no"]), url
        if not found:
            for url in posted_for(rec["date"]):
                try:
                    text = pdf_text(fetcher.get(url, binary=True))
                except Exception as exc:
                    print("  %s: %s unreachable (%s)" % (rec["date"], url, type(exc).__name__))
                    continue
                found = consent_items(text or "", head["no"]) if text else []
                if found:
                    src = url
                    break
        if not found:
            rec["consentUnread"] = ("Granicus indexes this meeting's consent calendar as one point, and no posted "
                                    "agenda or minutes with its lettered items was found on Granicus or "
                                    "sfpublicworks.org's commission calendar page.")
            return rec
        rec.setdefault("sources", {})["postedAgenda"] = src
        parent = re.sub(r"(?i)^(consent calendar[a-z ]*?)(\s+all items\b.*)?$", r"\1", head["title"]).strip()
        at = rec["items"].index(head) + 1
        rec["items"][at:at] = [dict(it, parent=parent, **{"from": "posted agenda"}) for it in found]
        return rec

    idx = granicus.mirror_views(mirror, fetcher, VIEWS, args.since, enrich=enrich,
                                notes=["The Commission first met in 2022; there is no earlier record to read.",
                                       "Items carry titles only. Granicus does not publish the vote.",
                                       "Where Granicus indexes a consent calendar as one point, its lettered items "
                                       "come from the posted agenda (field \"from\": \"posted agenda\")."])
    # Final meetings are never fetched again: a change in how a meeting is
    # read reaches them from disk, and a consent calendar left unread is
    # looked for again on every run.
    n = granicus.reparse(mirror, enrich, PARSER, stale=lambda rec: bool(rec.get("consentUnread")))
    print("  re-read %d meetings (parser %d)" % (n, PARSER))
    unread = [r["date"] for r in mirror.all() if r.get("consentUnread")]
    if unread:
        print("  consent calendar not itemised (no posted agenda found): %s" % ", ".join(unread))
    if n:
        idx = json.load(open(os.path.join(mirror.dir, "index.json"), encoding="utf-8"))
    print(summary(idx))
    read_delegated(mirror, fetcher, calendar_agendas(fetcher))


if __name__ == "__main__":
    main()
