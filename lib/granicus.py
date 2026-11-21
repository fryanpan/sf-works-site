"""Read a body's meeting list and agendas off SFGovTV's Granicus archive, sanfrancisco.granicus.com.

SFGovTV publishes a Granicus "view" per televised body, and each held meeting
carries an agenda whose items are the video's index points: the item numbers
and titles as the clerk entered them. Views this repo reads (checked
2026-09-28 by walking view_id 1..420 and reading each page's heading):

    22   Public Utilities Commission
    23   Transportation Authority Finance Committee
    24   Transportation Authority Full Board
    25   Transportation Authority Plans & Programs Committee (last meeting 2017)
    55   San Francisco Municipal Transportation Agency (SFMTA)
    91   Recreation and Park Commission
    172  Transportation Authority Vision Zero Committee
    218  Public Works Commission (first meeting 2022)

Two limits a reader must carry. The list is of meetings SFGovTV recorded, so
a meeting held and not televised is not in it and cannot be counted missing
from it. And the agenda is the index: it names every item but does not
record how the vote went. Granicus "minutes" links exist only for 2006 to 2008.

Agendas come in two forms. Most are HTML (GeneratedAgendaViewer). Some
redirect to a PDF of the posted agenda, which is read with pdftotext and split
on its item numbers.
"""

import html
import json
import os
import re

HOST = "https://sanfrancisco.granicus.com"

TAG = re.compile(r"(?s)<[^>]+>")
DROP = re.compile(r"(?s)<(script|style)\b.*?</\1>|<!--.*?-->")


def flatten(frag):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", DROP.sub(" ", frag)))).strip()


def listing_url(view):
    return "%s/ViewPublisher.php?view_id=%d" % (HOST, view)


def meetings(fetcher, view):
    """Every meeting a view lists, newest first: date, clip id, agenda and minutes links, title."""
    raw = fetcher.get(listing_url(view), cache=False)
    out, seen = [], set()
    for tr in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", raw):
        txt = flatten(tr)
        m = re.search(r"\b(\d{2})/(\d{2})/(\d{2})\b", txt)
        if not m:
            continue
        mm, dd, yy = m.groups()
        date = "20%s-%s-%s" % (yy, mm, dd)
        links = {}
        for href in re.findall(r'href="([^"]+)"', tr):
            href = html.unescape(href)
            full = href if href.startswith("http") else ("https:" + href if href.startswith("//") else HOST + "/" + href.lstrip("/"))
            if "AgendaViewer" in href and "agenda" not in links:
                links["agenda"] = full
            elif "MinutesViewer" in href and "minutes" not in links:
                links["minutes"] = full
        clip = re.search(r"clip_id=(\d+)", tr)
        name = re.search(r'(?s)<td[^>]*class="listItem"[^>]*>(.*?)</td>', tr)
        title = flatten(name.group(1)) if name else None
        key = clip.group(1) if clip else date
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": date, "clip": clip.group(1) if clip else None, "title": title,
                    "agenda": links.get("agenda"), "minutes": links.get("minutes"), "view": view})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


# An index point: "5.", "5a.", "5A.", "10.2.", at the start of a line.
POINT = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})*[A-Za-z]?)\.{1,2}\s+(\S.*)$")
# The end of the index: the clerk's attestation block.
END = re.compile(r"^\s*(ATTEST:|By:\s*$)")


def html_items(raw):
    """Items from a GeneratedAgendaViewer page: one per numbered line."""
    body = DROP.sub(" ", raw)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|td|h\d)>", "\n", body)
    lines = [re.sub(r"[ \t\xa0]+", " ", html.unescape(TAG.sub(" ", ln))).strip()
             for ln in body.split("\n")]
    items, cur = [], None
    for ln in lines:
        if not ln:
            continue
        if END.match(ln):
            break
        m = POINT.match(ln)
        if m:
            cur = {"no": m.group(1), "title": m.group(2).strip()}
            items.append(cur)
    return items


# A posted agenda PDF: the item number at the left margin, the title running on
# until the next number or a blank line.
PDF_POINT = re.compile(r"(?m)^[ \t]{0,8}(\d{1,2}(?:\.\d{1,2})*[A-Za-z]?)\.[ \t]+(?=\S)")


def pdf_items(text):
    items = []
    marks = list(PDF_POINT.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[m.end():end]
        chunk = re.split(r"\n\s*\n", chunk, 1)[0]
        title = re.sub(r"\s+", " ", chunk).strip()
        if len(title) >= 4:
            items.append({"no": m.group(1), "title": title[:1500]})
    return items


# Granicus stores some titles with every non-ASCII character already turned
# into a literal "?": "No. 70 ? Contract Award", "Michael O?Shaughnessy". The
# page serves the "?" itself, so there is nothing to decode; the two shapes it
# takes are put back as the characters they stood for. A "?" that ends a
# question is left alone.
_LOST_DASH = re.compile(r"(?<=\S) \? (?=\S)")
_LOST_APOS = re.compile(r"(?<=[A-Za-z])\?(?=[A-Za-z])")


def repair(title):
    t = _LOST_DASH.sub(" – ", title or "")
    return _LOST_APOS.sub("’", t)


def tidy(items):
    """Repair lost characters and drop an index point the agenda repeats.

    Granicus lists some points twice inside one agenda (SFPUC's 2026-06-23
    "7 CONSENT CALENDAR" and "8 Public hearing ..." each appear twice), and a
    parser that keeps both shows one vote twice on a project page.
    """
    out, seen = [], set()
    for it in items:
        it = dict(it, title=repair(it.get("title")))
        if it.get("text"):
            it["text"] = repair(it["text"])
        key = (str(it.get("no")).lower(), re.sub(r"\W+", " ", it["title"].lower()).strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def rewrite(mirror, enrich=None, notes=None):
    """Re-apply tidy() and `enrich` to every meeting already on disk, with no fetch.

    For a change in how items are cleaned or enriched: the final meetings are
    never fetched again, so without this they would keep the old reading.
    Returns the number of meetings rewritten.
    """
    n = 0
    for rec in mirror.all():
        before = json.dumps(rec, sort_keys=True)
        rec["items"] = tidy(rec["items"])
        if enrich:
            rec = enrich(rec) or rec
            rec["items"] = tidy(rec["items"])
        if json.dumps(rec, sort_keys=True) != before:
            mirror.write(rec)
            n += 1
    # The index counts the items, so it is rewritten from its own meeting list
    # (no listing fetch); notes passed here replace the ones it carries.
    ipath = os.path.join(mirror.dir, "index.json")
    if os.path.exists(ipath):
        idx = json.load(open(ipath, encoding="utf-8"))
        mirror.write_index(idx["meetings"], idx["since"], notes if notes is not None else idx.get("notes"))
    return n


def reparse(mirror, enrich, version, stale=None, notes=None):
    """Re-apply `enrich` to every mirrored meeting read by an older parser, from disk; stamp `version`.

    A final meeting is never fetched again, so a change in how its minutes are
    read would otherwise reach only new meetings. Each meeting carries the
    "parser" version it was read with; a meeting with another version (or
    none), or one `stale(rec)` names, is re-read from what is on disk (the
    minutes from the byte cache) and stamped. Run on every update, it costs
    nothing once every meeting carries the current version. Returns the
    number of meetings re-read.
    """
    n = 0
    for rec in mirror.all():
        if rec.get("parser") == version and not (stale and stale(rec)):
            continue
        rec["items"] = tidy(rec["items"])
        rec = enrich(rec) or rec
        rec["items"] = tidy(rec["items"])
        rec["parser"] = version
        mirror.write(rec)
        n += 1
    if n:
        ipath = os.path.join(mirror.dir, "index.json")
        if os.path.exists(ipath):
            idx = json.load(open(ipath, encoding="utf-8"))
            mirror.write_index(idx["meetings"], idx["since"], notes if notes is not None else idx.get("notes"))
    return n


def mirror_views(mirror, fetcher, views, since, notes=None, enrich=None, until=None):
    """Mirror every meeting the views list from `since` on; write the index. Returns the index.

    `views` maps a Granicus view id to the committee name it carries. A
    meeting already mirrored as final is not fetched again; a draft is. An
    agenda that cannot be fetched, or parses to nothing, is recorded in the
    index with its reason rather than skipped in silence. `enrich(rec)` may add
    decisions or longer titles from another source before the write.
    """
    import datetime as dt
    from lib.mirror import settled
    today = dt.date.today().isoformat()
    listed, got, kept = [], 0, 0
    for view, committee in views.items():
        for m in meetings(fetcher, view):
            if m["date"] < since or (until and m["date"] > until):
                continue
            mid = "g%d-%s" % (view, m["clip"] or m["date"])
            row = {"date": m["date"], "id": mid, "committee": committee, "agenda": m["agenda"]}
            listed.append(row)
            if m["date"] > today:
                row.update(outcome="no-agenda", reason="not yet held")
                continue
            if mirror.is_final(m["date"], mid):
                row["outcome"] = "mirrored"
                kept += 1
                continue
            if not m["agenda"]:
                row.update(outcome="no-agenda", reason="Granicus lists the meeting with no agenda link")
                continue
            final = settled(m["date"])
            try:
                items, form = agenda(fetcher, m["agenda"], cache=final)
            except Exception as exc:  # recorded, not swallowed
                row.update(outcome="unreachable", reason="%s: %s" % (type(exc).__name__, exc))
                continue
            if not items:
                row.update(outcome="empty", reason="agenda parsed to no items (%s)" % form)
                continue
            rec = {"committee": committee, "date": m["date"], "id": mid,
                   "status": "final" if final else "draft",
                   "sources": {"agenda": m["agenda"], "listing": listing_url(view)},
                   "fetched": today, "form": form, "items": tidy(items)}
            if enrich:
                rec = enrich(rec) or rec
                rec["items"] = tidy(rec["items"])
            mirror.write(rec)
            row["outcome"] = "mirrored"
            got += 1
    idx = mirror.write_index(listed, since, notes)
    print("  fetched %d, already final %d, %d requests" % (got, kept, fetcher.requests))
    return idx


def agenda(fetcher, url, cache=True):
    """(items, form) for one agenda link; form is html, pdf or none."""
    raw = fetcher.get(url, binary=True, cache=cache)
    if raw.lstrip()[:5].startswith(b"%PDF"):
        from lib.fetch import pdf_text
        text = pdf_text(raw) or ""
        return pdf_items(text), "pdf"
    page = raw.decode("utf-8", "replace")
    items = html_items(page)
    if items:
        return items, "html"
    # An uploaded agenda PDF is served through Google's viewer: the redirect
    # lands on docs.google.com/gview, whose page names the Granicus file.
    doc = re.search(r"(sanfrancisco_[0-9a-f]{16,}\.pdf)", page)
    if doc:
        from lib.fetch import pdf_text
        pdf = fetcher.get("%s/DocumentViewer.php?file=%s&view=1" % (HOST, doc.group(1)), binary=True, cache=cache)
        return pdf_items(pdf_text(pdf) or ""), "pdf"
    return [], "none"
