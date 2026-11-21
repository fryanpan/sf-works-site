#!/usr/bin/env python3
"""Public meetings coming up in the next 90 days at the bodies the project pages read, with each posted agenda's items, to data/upcoming-meetings/meetings.json.

    tools/meetings/upcoming-meetings.py            # read every source's listing now
    tools/meetings/upcoming-meetings.py --update   # the same; the flag the pipeline passes

Bryan, 2026-09-29, on Current Projects: "I think we need to highlight projects
with upcoming meetings. And also highlight other projects that might be early
enough to do something about them." The body mirrors (scripts/fetch-*.py) keep
held meetings only; this keeps the ones not yet held, so
tools/projects/project-record.py can match an agenda item or an event to the project
it names, the same way it matches a past decision.

Sources, each read from the body's own listing:

  sfmta     sfmta.com/meetings-events, every SFMTA meeting and community event
            not yet held (one page, no paging), and the engineering hearings'
            own upcoming list (/upcoming-meetings-and-events/2617). Each event's
            page is read for its agenda PDF, its "Item N" reports and any
            /projects/ page it links; an open house names its project that way.
  bos       Legistar's calendar, "BOS and Committees": each future meeting's
            agenda grid, once the clerk posts it (about a week ahead).
  pwc       Public Works Commission calendar on sfpublicworks.org: agenda PDFs
            whose file name carries a date not yet past.
  sfpuc     SFPUC Commission agendas, minutes and resolutions log: agenda PDFs
            (M.D.YYYY_A.pdf) dated today or later.

Not read, and said so in the output's "gaps": the SFCTA Board (sfcta.org
answers 403 to a script, and Granicus lists no meeting before it is held),
Public Works director's hearings (no listing a script can read), and the
Recreation and Park Commission (its agendas name parks, not street projects).

Refresh. No source has a change marker for meetings not yet held, so the
re-read is bounded: every run reads each listing and every listed meeting
dated after today to 90 days out (WINDOW_DAYS), and nothing already held
or held today (the body mirrors take those).

Legistar and the Public Works and SFPUC logs list a meeting only once its
agenda is posted (checked 2026-09-29), so only sfmta.com shows a meeting
whose agenda is still to come. A source
whose listing cannot be read keeps its last good meetings (those still ahead)
and records `upcoming:<source>` as failed in data/pipeline-state/sources.json.
Meetings are sorted by date and id, so a rerun with nothing new posted
rewrites nothing.

Individual staff email addresses are scrubbed on the way in;
institutional inboxes stay.
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)

# Legistar's scraper lives in its own virtualenv (scripts/refresh-legistar.sh);
# run from it when the system Python lacks it, as fetch-bos-meetings.py does.
try:
    import legistar.bills  # noqa: F401
    HAVE_LEGISTAR = True
except ImportError:
    _venv = os.path.expanduser(os.environ.get("CACHE", "~/.cache/sf-legistar")) + "/venv/bin/python"
    if os.path.exists(_venv) and not os.environ.get("SF_LEGISTAR_REEXEC"):
        os.environ["SF_LEGISTAR_REEXEC"] = "1"
        os.execv(_venv, [_venv, os.path.abspath(__file__)] + sys.argv[1:])
    HAVE_LEGISTAR = False

from extract import EMAIL, KEEP, scrub  # noqa: E402
from lib import granicus, pipeline_state, stable  # noqa: E402
from lib.fetch import Fetcher, pdf_text  # noqa: E402
from lib.mirror import slug  # noqa: E402

OUT = os.path.join(ROOT, "data", "upcoming-meetings", "meetings.json")
WINDOW_DAYS = 90

SFMTA = "https://www.sfmta.com"
SFMTA_LISTINGS = [SFMTA + "/meetings-events", SFMTA + "/upcoming-meetings-and-events/2617"]
# The engineering hearings' own page lists each hearing, past and coming, as a
# /calendar/ link whose slug carries the date; the general listing shows a
# posted hearing only as a /notices/ link.
HEARINGS_PAGE = SFMTA + "/committees/engineering-public-hearings"
HEARING_SLUG = re.compile(r"/calendar/(engineering-public-hearing-meeting-([a-z]+)-(\d{1,2})-(\d{4})(?:-\d{1,2})?)(?=[\"?#])")
PWC_LISTING = "https://sfpublicworks.org/about/public-works-commission-calendar"
SFPUC_LISTING = ("https://www.sfpuc.gov/about-us/boards-commissions-committees/sfpuc-commission/"
                 "agendas-minutes-resolutions-log")
LEGISTAR_LISTING = "https://sfgov.legistar.com/Calendar.aspx"

SOURCES = {
    "sfmta": ("SFMTA meetings and events", SFMTA + "/meetings-events"),
    "bos": ("Board of Supervisors and its committees", LEGISTAR_LISTING),
    "pwc": ("Public Works Commission", PWC_LISTING),
    "sfpuc": ("SFPUC Commission", SFPUC_LISTING),
}
GAPS = [
    {"body": "San Francisco County Transportation Authority Board",
     "why": "sfcta.org answers 403 to a script, and SFGovTV's Granicus lists a meeting only once it is held"},
    {"body": "Public Works director's hearings",
     "why": "sfpublicworks.org publishes no listing of them a script can read"},
    {"body": "Recreation and Park Commission", "why": "not read: its agendas name parks, not street projects"},
]

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}

# An SFMTA event's body, from its title. The kind is the one
# tools/projects/project-record.py gives the same body's held meetings.
SFMTA_BODIES = [
    (re.compile(r"^engineering public hearing", re.I), "SFMTA engineering public hearing", "hearing"),
    (re.compile(r"^board of directors", re.I), "SFMTA Board of Directors", "board"),
    (re.compile(r"citizens.? advisory council", re.I), "SFMTA Citizens' Advisory Council", "sfmta-cac"),
    (re.compile(r"committee", re.I), None, "sfmta-committee"),
]


def tidy_text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", s or ""))).strip()


def month_day_year(text):
    m = re.search(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", text or "")
    if not m or m.group(1).lower() not in MONTHS:
        return None
    return "%s-%02d-%02d" % (m.group(3), MONTHS[m.group(1).lower()], int(m.group(2)))


# ---- sfmta.com ---------------------------------------------------------------

def sfmta_listing(fetcher, url):
    """(date, time, title, slug) for each event a listing page shows, in page order."""
    raw = fetcher.get(url, cache=False)
    out, date = [], None
    # The day heading's datetime was "--" until November 2026, when sfmta.com
    # began printing the ISO date there; either form is read from the text.
    tok = re.compile(r'<time datetime="(?:--|\d{4}-\d\d-\d\d)">([^<]+)</time>'
                     r'|<a href="/calendar/([a-z0-9-]+)"[^>]*>([^<]+)</a>'
                     r'|<time datetime="[^"]+" class="datetime">([^<]+)</time>')
    for m in tok.finditer(raw):
        if m.group(1):
            date = month_day_year(m.group(1)) or date
        elif m.group(2):
            out.append({"date": date, "slug": m.group(2), "title": tidy_text(m.group(3)), "time": None})
        elif m.group(4) and out and out[-1]["time"] is None:
            out[-1]["time"] = m.group(4).strip()
    return out


REPORT_ITEM = re.compile(r"^\s*[\d-]+\s+[A-Z]+\s+Item\s+([0-9]+(?:\.[0-9]+)?[A-Za-z]?)\s+(.+)$")


def sfmta_event(fetcher, ev):
    """One event's page: its agenda, its item reports, and the project pages it links."""
    page = SFMTA + "/calendar/" + ev["slug"]
    raw = fetcher.get(page, cache=False)
    projects = sorted({SFMTA + "/projects/" + s for s in re.findall(r'href="(?:https://www\.sfmta\.com)?/projects/([a-z0-9-]+)"', raw)})
    # A page linking many projects is a roundup, not one project's event.
    if len(projects) > 3:
        projects = []
    agenda, items = None, []
    for href, text in re.findall(r'href="([^"]+)"[^>]*>([^<]{3,200})</a>', raw):
        label = tidy_text(text)
        url = href if href.startswith("http") else SFMTA + href
        url = re.sub(r"(sfmta\.com)/index(?:%2[Ee]|\.)php/", r"\1/", url)
        if "/media/" in href and re.search(r"agenda", label, re.I) and not agenda:
            agenda = url
        m = REPORT_ITEM.match(label) if "/reports/" in href else None
        if m:
            items.append({"no": m.group(1), "title": m.group(2).strip(), "url": url})
    if agenda:
        text = pdf_text(fetcher.get(agenda, binary=True, cache=False)) or ""
        have = {i["no"] for i in items}
        for it in granicus.pdf_items(text):
            if it["no"] not in have:
                items.append({"no": it["no"], "title": it["title"][:900], "url": agenda})
                have.add(it["no"])
    return page, agenda, items, projects


def read_sfmta(fetcher, today, until):
    seen, events = set(), []
    for url in SFMTA_LISTINGS:
        for ev in sfmta_listing(fetcher, url):
            if ev["slug"] in seen:
                continue
            seen.add(ev["slug"])
            events.append(ev)
    raw = fetcher.get(HEARINGS_PAGE, cache=False)
    for slug_, mon, day, year in HEARING_SLUG.findall(raw):
        if slug_ in seen or mon not in MONTHS:
            continue
        seen.add(slug_)
        events.append({"date": "%s-%02d-%02d" % (year, MONTHS[mon], int(day)), "slug": slug_,
                       "title": "Engineering Public Hearing, %s %s, %s" % (mon.title(), day, year), "time": None})
    if not events:
        raise RuntimeError("sfmta.com listed no upcoming events; a listing that empties is a broken read")
    out = []
    for ev in events:
        if not ev["date"] or not (today < ev["date"] <= until):
            continue
        # Any other event carries its own name, without the date and "Meeting".
        body = "SFMTA " + re.sub(r"(?i)[\s,]*(regular )?meeting\b.*$|,? [A-Z][a-z]+ \d{1,2}, \d{4}$", "", ev["title"]).strip()
        kind = "sfmta-event"
        for rx, name, k in SFMTA_BODIES:
            if rx.search(ev["title"]):
                body, kind = name or "SFMTA " + re.sub(r"\s*(regular )?meeting.*$", "", ev["title"], flags=re.I), k
                break
        page, agenda, items, projects = sfmta_event(fetcher, ev)
        out.append({"source": "sfmta", "kind": kind, "body": body, "date": ev["date"], "time": ev["time"],
                    "title": ev["title"], "url": page, "agenda": agenda, "items": items,
                    "projectPages": projects})
    return out


# ---- Legistar ----------------------------------------------------------------

def read_bos(today, until):
    if not HAVE_LEGISTAR:
        raise RuntimeError("cannot import legistar.bills; run scripts/refresh-legistar.sh once")
    import sf_legistar
    s = sf_legistar._new(rpm=60)
    out, seen = [], set()
    # A window that crosses New Year asks for two years. Legistar answers a year
    # it has no meetings for yet with every year (4,901 rows for "2027" on
    # 2026-11-10), which repeats this year's rows, so a meeting already read is
    # skipped by its detail URL.
    for year in sorted({today[:4], until[:4]}):
        for n, m in enumerate(s.meetings("BOS and Committees", year)):
            date = dt.datetime.strptime(m["date"], "%m/%d/%Y").date().isoformat()
            # The listing runs newest first, so an every-year answer opens on
            # another year; stop there rather than page through all of them.
            if n == 0 and date[:4] != year:
                break
            if not (today < date <= until):
                continue
            key = m.get("url") or (m["body"], m["date"], m.get("time"))
            if key in seen:
                continue
            seen.add(key)
            items = []
            if m.get("url"):
                for i, it in enumerate(s.agenda(m["url"])):
                    items.append({"no": it["file"] or str(i + 1), "title": it["title"] or it["name"],
                                  "url": it["url"], "type": it["type"]})
            out.append({"source": "bos", "kind": "supervisors", "body": m["body"], "date": date,
                        "time": m.get("time") or None, "title": "%s, %s" % (m["body"], m["date"]),
                        "url": m.get("url") or LEGISTAR_LISTING,
                        "agenda": m.get("agenda_pdf") if items else None, "items": items, "projectPages": []})
    return out


# ---- PDF agenda logs ---------------------------------------------------------

def pdf_meetings(fetcher, listing, pattern, source, kind, body, today, until):
    """Agenda PDFs a department lists, dated by their file name, from today to `until`."""
    raw = fetcher.get(listing, cache=False)
    base = re.match(r"https://[^/]+", listing).group(0)
    found = {}
    for href in re.findall(r'href="([^"]+\.pdf)"', raw):
        name = html.unescape(href).replace("%20", " ").replace("%2C", ",")
        m = pattern.search(name)
        if not m:
            continue
        y, mo, d = (int(x) for x in m.group("y", "m", "d"))
        try:
            date = dt.date(y, mo, d).isoformat()
        except ValueError:
            continue
        if not (today < date <= until):
            continue
        url = href if href.startswith("http") else base + href
        # A revised agenda is posted beside the first ("v922b"); the later
        # file name sorts last and is the one kept.
        if date not in found or url > found[date]:
            found[date] = url
    out = []
    for date, url in sorted(found.items()):
        text = pdf_text(fetcher.get(url, binary=True, cache=False)) or ""
        items = [{"no": it["no"], "title": it["title"][:900], "url": url} for it in granicus.pdf_items(text)]
        out.append({"source": source, "kind": kind, "body": body, "date": date, "time": None,
                    "title": "%s, %s" % (body, date), "url": url, "agenda": url, "items": items,
                    "projectPages": []})
    return out


PWC_PDF = re.compile(r"(?P<y>20\d\d)-(?P<m>\d{1,2})-(?P<d>\d{1,2}) PW[^/]*Agenda", re.I)
SFPUC_PDF = re.compile(r"/(?P<m>\d{1,2})\.(?P<d>\d{1,2})\.(?P<y>20\d\d)_(?:SpcMtg_)?A(?:_\d+)?\.pdf$")


# ---- assembly ----------------------------------------------------------------

def meeting_id(m):
    """source:date:key, where the key is the listing's own: Legistar's meeting ID,
    the sfmta.com event slug, or the agenda PDF's file name."""
    gid = re.search(r"MeetingDetail\.aspx\?ID=(\d+)", m["url"])
    key = gid.group(1) if gid else m["url"].rstrip("/").rsplit("/", 1)[-1]
    return "%s:%s:%s" % (m["source"], m["date"], slug(re.sub(r"\.pdf$", "", key))[:80])


def finish(m):
    m["id"] = meeting_id(m)
    m["agendaPosted"] = bool(m["items"])
    m["items"] = [dict(it, title=re.sub(r"\s+", " ", it["title"]).strip()) for it in m["items"]
                  if (it.get("title") or "").strip()]
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="the pipeline's flag; every run is a bounded re-read")
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--today", help="YYYY-MM-DD; default today")
    args = ap.parse_args()
    today = args.today or dt.date.today().isoformat()
    until = (dt.date.fromisoformat(today) + dt.timedelta(days=args.days)).isoformat()
    fetcher = Fetcher("upcoming-meetings", pause=0.5)

    prev = {}
    if os.path.exists(OUT):
        prev = json.load(open(OUT, encoding="utf-8"))
    readers = {
        "sfmta": lambda: read_sfmta(fetcher, today, until),
        "bos": lambda: read_bos(today, until),
        "pwc": lambda: pdf_meetings(fetcher, PWC_LISTING, PWC_PDF, "pwc", "pwc", "Public Works Commission",
                                    today, until),
        "sfpuc": lambda: pdf_meetings(fetcher, SFPUC_LISTING, SFPUC_PDF, "sfpuc", "sfpuc", "SFPUC Commission",
                                      today, until),
    }
    meetings, sources = [], []
    for key, read in readers.items():
        name, listing = SOURCES[key]
        try:
            got = [finish(m) for m in read()]
            status, detail = "read", None
            pipeline_state.refreshed("upcoming:" + key, [], detail="%d meetings to %s" % (len(got), until))
        except Exception as exc:  # the last good copy is kept, and the failure recorded
            got = [m for m in prev.get("meetings", []) if m["source"] == key and m["date"] >= today]
            status, detail = "failed", "%s: %s" % (type(exc).__name__, str(exc)[:200])
            pipeline_state.refreshed("upcoming:" + key, [detail])
            print("  %s: FAILED, kept %d held meetings: %s" % (key, len(got), detail))
        meetings += got
        sources.append({"id": key, "name": name, "listing": listing, "status": status,
                        "meetings": len(got), "withAgenda": sum(1 for m in got if m["agendaPosted"]),
                        **({"detail": detail} if detail else {})})
        print("  %-6s %2d meetings, %d with an agenda" % (key, len(got), sources[-1]["withAgenda"]))

    meetings.sort(key=lambda m: (m["date"], m["id"]))
    payload = scrub({
        "generated": today,
        "windowDays": args.days,
        "sources": sources,
        "gaps": GAPS,
        "meetings": meetings,
    })
    text = json.dumps(payload, ensure_ascii=False)
    leaked = [e for e in set(EMAIL.findall(text)) if not KEEP.match(e)]
    if leaked:
        sys.exit("REFUSING TO WRITE: %d personal email address(es) survived the scrub" % len(leaked))
    wrote = stable.write_json(OUT, payload, indent=1)
    print("%s %s: %d meetings, %d with a posted agenda" % ("wrote" if wrote else "unchanged", os.path.relpath(OUT, ROOT),
                                                            len(meetings), sum(1 for m in meetings if m["agendaPosted"])))
    if any(s["status"] == "failed" for s in sources) and not meetings:
        sys.exit(1)


if __name__ == "__main__":
    main()
