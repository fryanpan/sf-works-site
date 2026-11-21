#!/usr/bin/env python3
"""Each SFMTA project's own record, read off its project page.

    tools/projects/sfmta-project-pages.py            # bike projects → out/sfmta-projects/pages.json
    tools/projects/sfmta-project-pages.py --all      # every project on the layer
    tools/projects/sfmta-project-pages.py --sitemap  # --all plus every /projects/ page in the sitemap

An SFMTA project page is not prose with a map. It carries the project's own
paper trail in five structured blocks that tools/projects/sfmta-projects.py flattens
away: a dated PROJECT TIMELINE of milestones; RELATED NOTICES, which are the
engineering-hearing and street-change notices for this very project; PAST
MEETINGS, including the Board meeting that approved it; PROJECT UPDATES; and
RELATED REPORTS AND DOCUMENTS. None of that has to be inferred from a street
name — the department has already said which project each item belongs to.

Found 2026-09-22 while trying to raise the record-to-project match rate by
joining blocks. The block join is right about PLACE and cannot tell a
project's own hearing from a bike-share dock on its street; this can, because
the page lists the one and not the other.

Refresh (--update): the change marker is sfmta.com's sitemap, whose
<lastmod> per page says when it was edited; a page is re-read only when that
is newer than our copy. The check is recorded as `sitemap:sfmta-pages` in
data/pipeline-state/sources.json: failed when any page could not be reached
(its held copy kept), so a refresh that keeps failing ages the extract.
The sitemap itself is about 10 MB in 15 parts; the index gives each part a
<lastmod>, so a part is re-read only when its lastmod differs from the held
copy's (sitemap_parts), and a run on a day sfmta.com has not regenerated its
sitemap reads the index alone.

Two stores, per Bryan's instruction the same day: the raw page is cached
under data/sfmta-pages/ (gitignored, refetchable, carries staff contacts) and
this structured extract is written to out/ with contacts stripped, so a later
run and a fresh clone both build from the extract rather than the network.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import Extract  # noqa: E402
from lib import stable  # noqa: E402

ROOT = paths.ROOT
PROJECTS = os.path.join(ROOT, "out", "sfmta-projects", "projects.json")
OUT = os.path.join(ROOT, "out", "sfmta-projects", "pages.json")
CACHE = os.path.join(ROOT, "data", "sfmta-pages")
SITE = "https://www.sfmta.com"
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


# --update: the sitemap's own <lastmod> per page, and when each cached copy
# was taken. A copy is re-read only when the page's lastmod is newer than the
# copy, so a run with no edits on sfmta.com reads the sitemap and nothing else.
LASTMOD = None
# Pages a re-read could not reach this run, whose held copy was used.
STALE = []


_PARTS = None


def sitemap_parts():
    """The text of each part of sfmta.com's sitemap, read once per run.

    The index is always read. A part is re-read only when the index's
    <lastmod> for it differs from the one its held copy was read under
    (data/sfmta-pages/sitemap-parts.json, gitignored like the page copies)."""
    global _PARTS
    if _PARTS is not None:
        return _PARTS
    index = get(SITE + "/sitemap.xml", refetch=True)
    held_path = os.path.join(CACHE, "sitemap-parts.json")
    try:
        held = json.load(open(held_path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        held = {}
    parts, now = [], {}
    for block in re.findall(r"<sitemap>(.*?)</sitemap>", index, re.S) or [index]:
        for loc in re.findall(r"<loc>([^<]+)</loc>", block):
            url = loc.replace("&amp;", "&")
            m = re.search(r"<lastmod>([^<]+)</lastmod>", block)
            lastmod = m.group(1).strip() if m else None
            path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".html")
            fresh = lastmod is None or held.get(url) != lastmod or not os.path.exists(path)
            parts.append(get(url, refetch=fresh))
            now[url] = lastmod
    with open(held_path, "w", encoding="utf-8") as fh:
        json.dump(now, fh, indent=1, sort_keys=True)
    _PARTS = parts
    return parts


def sitemap_lastmods():
    """{url: lastmod as epoch seconds} for every page in sfmta.com's sitemap."""
    out = {}
    for part in sitemap_parts():
        # One <url> block at a time: an entry without a <lastmod> must not
        # borrow the next entry's, which would also hide that next page.
        for block in re.findall(r"<url>(.*?)</url>", part, re.S):
            u = re.search(r"<loc>([^<]+)</loc>", block)
            m = re.search(r"<lastmod>([^<]+)</lastmod>", block)
            if not (u and m):
                continue
            try:
                out[u.group(1).replace("&amp;", "&")] = dt.datetime.fromisoformat(m.group(1).strip()).timestamp()
            except ValueError:
                pass
    return out


def changed_since_copy(url, path):
    """True when the sitemap says the page was edited after our copy was taken."""
    if LASTMOD is None or not os.path.exists(path):
        return False
    m = LASTMOD.get(url)
    if m is None:
        # A /node/N address is not in the sitemap; the copy names its alias.
        raw = open(path, encoding="utf-8").read()
        c = re.search(r'<link rel="canonical" href="([^"]+)"', raw)
        m = LASTMOD.get(c.group(1)) if c else None
    return m is not None and m > os.path.getmtime(path)


def get(url, refetch=False):
    """Page bytes, from the raw cache unless asked otherwise."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".html")
    if not refetch and os.path.exists(path) and not changed_since_copy(url, path):
        return open(path, encoding="utf-8").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                raw = fh.read().decode("utf-8", "replace")
            open(path, "w", encoding="utf-8").write(raw)
            time.sleep(1)  # one uncached page a second, to be polite to sfmta.com
            return raw
        except (urllib.error.URLError, TimeoutError):
            if i == 2:
                # A failed re-read of a page we hold keeps the copy we have.
                if os.path.exists(path):
                    STALE.append(url)
                    return open(path, encoding="utf-8").read()
                raise
            time.sleep(2 * (i + 1))


def clean(s):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = EMAIL.sub("", s)
    return PHONE.sub("", s).strip(" ,;")


def slug_date(href):
    """A date the URL slug carries: ".../board-directors-meeting-april-4-2023"."""
    m = re.search(r"(january|february|march|april|may|june|july|august|september|"
                  r"october|november|december)-(\d{1,2})-(\d{4})", href or "", re.I)
    if m:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def first_time(el):
    t = el.find("time") if el else None
    if not t:
        return None
    iso = (t.get("datetime") or "")[:10]
    if re.match(r"\d{4}-\d{2}-\d{2}$", iso):
        return iso
    # Event pages ship datetime="--" and carry the date only in the text:
    # "Saturday, November 16, 2024 - 10:00am - 1:00pm".
    m = re.search(r"(january|february|march|april|may|june|july|august|september|"
                  r"october|november|december)\s+(\d{1,2}),\s+(\d{4})", t.get_text(), re.I)
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}" if m else None


def sitemap_projects():
    """Every /projects/ page sfmta.com lists in its sitemap.

    The project layer holds only projects with a mapped geometry (224 on
    2026-09-24); the sitemap lists 415 project pages, including finished and
    unmapped ones. A page that has been unpublished is in neither.
    """
    urls = []
    for part in sitemap_parts():
        urls += re.findall(r"<loc>(https://www\.sfmta\.com/projects/[^<]+)</loc>", part)
    return sorted(set(urls))


_PERIOD = (r"(?:january|february|march|april|may|june|july|august|september|"
           r"october|november|december|winter|spring|summer|fall|autumn)")
WHEN = re.compile(r"((?:(?:early|mid|late)[- ])?(?:%s(?:/%s)?\s+)?\b20\d\d\b.*)$" % (_PERIOD, _PERIOD), re.I)


def prose_timeline(soup):
    """A timeline written into the page body instead of SFMTA's timeline block.

    Folsom-Howard's page, read 2026-09-28, puts it under a bold "Project
    Timeline" line as bold group names, each followed by a list of
    "Milestone: when" items ("Construction: 2024 to 2026"). Bryan, the same
    day: "On the project page, it clearly has listed construction dates for
    both folsom and howard streets."
    """
    head = next((el for el in soup.select("p") if clean(el.get_text()).lower() == "project timeline"), None)
    rows, group = [], None
    el = head.find_next_sibling() if head else None
    while el is not None and el.name in ("p", "ul", "ol"):
        if el.name == "p":
            text = clean(el.get_text())
            if not text:
                el = el.find_next_sibling()
                continue
            if not el.find("strong") or len(text) > 120:
                break
            group = text
        else:
            for li in el.select("li"):
                text = clean(li.get_text())
                what, _, when = text.rpartition(":")
                if not what:
                    m = WHEN.search(text)
                    if not m:
                        continue
                    what, when = text[:m.start()], m.group(1)
                if not re.search(r"\b20\d\d\b", when):
                    continue
                what = clean(what)
                rows.append({"when": clean(when), "what": f"{what} ({group})" if group else what, "status": None})
        el = el.find_next_sibling()
    return rows


def last_time(el):
    """The last day an element's <time>s give, when they span more than one: "Monday, April 18, 2022 - 8:00am -
    Saturday, April 30, 2022 - 5:00pm" -> 2022-04-30 (13th Street Safety Project's virtual open house; Fable
    review, 2026-09-30). None when they give one day."""
    days = []
    for t in (el.find_all("time") if el else ()):
        iso = (t.get("datetime") or "")[:10]
        if re.match(r"\d{4}-\d{2}-\d{2}$", iso):
            days.append(iso)
        for m in re.finditer(r"(january|february|march|april|may|june|july|august|september|"
                             r"october|november|december)\s+(\d{1,2}),\s+(\d{4})", t.get_text(), re.I):
            days.append(f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}")
    return max(days) if len(set(days)) > 1 else None


def event_date(url, refetch=False):
    """(first day, last day or None) an event's own calendar page gives, when the project page's card shows only
    month and day."""
    try:
        soup = BeautifulSoup(get(url, refetch), "html.parser")
    except Exception:  # noqa: BLE001
        return None, None
    main = soup.select_one("main") or soup
    return first_time(main), last_time(main)


def parse(raw):
    soup = BeautifulSoup(raw, "html.parser")
    out = {"timeline": [], "notices": [], "meetings": [], "updates": [], "documents": []}
    canon = soup.select_one('link[rel="canonical"]')
    out["canonical"] = canon.get("href") if canon else None
    h1 = soup.select_one("h1")
    out["title"] = clean(h1.get_text()) if h1 else None

    # The page's headline image, as SFMTA publishes it for link previews. The
    # site loads it from sfmta.com rather than copying it (Bryan, 2026-09-23).
    # The first hero image at SFMTA's own small size (768 px, about 25 kB) is
    # the one the page opens with. Where a page has no hero, its link-preview
    # image stands in; that one is the full-size original.
    hero = soup.select_one('img[src*="/files/styles/hero_slideshow_small_1x/"], source[srcset*="/files/styles/hero_slideshow_small_1x/"]')
    src = (hero.get("src") or hero.get("srcset", "").split()[0]) if hero else ""
    og = soup.select_one('meta[property="og:image"]')
    if src.startswith("/"):
        out["image"] = SITE + src
    elif og and og.get("content", "").startswith(SITE + "/"):
        out["image"] = og["content"]
    else:
        out["image"] = None
    out["image_full_size"] = not src.startswith("/") and out["image"] is not None

    # The page's own "Current Phase or Stage" field, where the page fills it
    # in ("Construction", "Planning & Outreach"): 56 of the 417 cached pages
    # on 2026-09-28. It is the phase for a project the layer gives none.
    ph = soup.select_one(".field--name-field-current-phase-or-stage .field__item")
    out["phase"] = clean(ph.get_text()) if ph else None

    tl = soup.select_one(".field-project-timeline")
    if tl:
        for item in tl.select(".project-progress [class*='item-']"):
            title = item.select_one(".title")
            desc = item.select_one(".description")
            status = item.select_one(".icon_text")
            if title and desc:
                when = clean(title.get_text())
                what = clean(desc.get_text().replace(status.get_text() if status else "", ""))
                # Some pages fill the block the other way round, milestone in
                # the title and date in the description ("Street Safety
                # Construction" / "Winter 2027", Western Addition Community
                # Safe Streets, read 2026-09-28).
                if not re.search(r"\b20\d\d\b", when) and re.search(r"\b20\d\d\b", what):
                    when, what = what, when
                out["timeline"].append({
                    "when": when, "what": what,
                    "status": clean(status.get_text()) if status else None,
                })

    if not out["timeline"]:
        out["timeline"] = prose_timeline(soup)

    for art in soup.select("article.node--type-notice"):
        a = art.select_one("h3 a") or art.select_one("a")
        if a:
            out["notices"].append({"title": clean(a.get_text()), "url": SITE + a["href"],
                                   "date": first_time(art)})

    for art in soup.select("article.node--type-event"):
        a = art.select_one("h3 a") or art.select_one("a")
        if a:
            ev = {"title": clean(a.get_text()), "url": SITE + a["href"],
                  "date": first_time(art) or slug_date(a["href"])}
            # An event that runs over several days ends on its last one.
            if ev["date"] and (last_time(art) or "") > ev["date"]:
                ev["end"] = last_time(art)
            out["meetings"].append(ev)

    for art in soup.select("article.node--type-project-update"):
        a = art.select_one("a")
        if a:
            out["updates"].append({"title": clean(a.get_text()), "url": SITE + a["href"]})

    seen = set()
    for art in soup.select("article.node--type-reports-and-documents"):
        a = art.select_one("h3 a") or art.select_one("a")
        if a and a["href"] not in seen:
            seen.add(a["href"])
            files = [SITE + f["href"] for f in art.select("a[href*='/media/']")]
            out["documents"].append({"title": clean(a.get_text()), "url": SITE + a["href"],
                                     "files": files})
    return out


def undated_events(rec):
    """Date each meeting the project page lists without a year from the meeting's own page."""
    for m in rec["meetings"]:
        if not m["date"]:
            m["date"], end = event_date(m["url"])
            if m["date"] and (end or "") > m["date"]:
                m["end"] = end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every project, not only bike")
    ap.add_argument("--sitemap", action="store_true",
                    help="also every /projects/ page in the sfmta.com sitemap (implies --all)")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--update", action="store_true",
                    help="re-read only pages the sitemap says changed since our copy")
    args = ap.parse_args()
    global LASTMOD
    if args.update:
        LASTMOD = sitemap_lastmods()
        print(f"  sitemap: {len(LASTMOD):,} pages with a lastmod", file=sys.stderr)

    args.all = args.all or args.sitemap
    projects = json.load(open(PROJECTS))["projects"]
    if not args.all:
        projects = [p for p in projects if p.get("bike")]
    if args.limit:
        projects = projects[: args.limit]

    pages, failed = {}, []
    for i, p in enumerate(projects, 1):
        try:
            raw = get(p["page"], args.refetch)
        except Exception as exc:  # noqa: BLE001
            failed.append((p["node"], str(exc)[:80]))
            continue
        rec = parse(raw)
        undated_events(rec)
        # The prose, for every page, so the Current Projects list can read a
        # project's scope whether or not SFMTA tags it Bike.
        main_el = BeautifulSoup(raw, "html.parser").select_one("main") or BeautifulSoup(raw, "html.parser")
        rec["pageText"] = clean(main_el.get_text(" "))[:8000]
        rec.update({"node": p["node"], "name": p["name"], "page": p["page"]})
        pages[str(p["node"])] = rec
        if i % 25 == 0:
            print(f"  {i}/{len(projects)}", file=sys.stderr)

    # Pages the layer does not map. Keyed by slug, since only the layer carries
    # a node number; `on_layer` says which kind a record is.
    for r in pages.values():
        r["on_layer"] = True
    if args.sitemap:
        known = {r["canonical"] for r in pages.values() if r.get("canonical")}
        extra = [u for u in sitemap_projects() if u not in known]
        print(f"  sitemap: {len(extra)} project pages not on the layer", file=sys.stderr)
        for i, url in enumerate(extra, 1):
            try:
                raw = get(url, args.refetch)
            except Exception as exc:  # noqa: BLE001
                failed.append((url, str(exc)[:80]))
                continue
            rec = parse(raw)
            undated_events(rec)
            # The prose, which the layer's projects.json carries as pageText
            # for mapped projects and nothing carries for these.
            main_el = BeautifulSoup(raw, "html.parser").select_one("main") or BeautifulSoup(raw, "html.parser")
            rec["pageText"] = clean(main_el.get_text(" "))[:8000]
            slug = url.rsplit("/", 1)[-1]
            rec.update({"node": "slug:" + slug, "name": rec["title"] or slug,
                        "page": url, "on_layer": False})
            pages[rec["node"]] = rec
            if i % 25 == 0:
                print(f"  sitemap {i}/{len(extra)}", file=sys.stderr)

    scope = "sitemap" if args.sitemap else "all" if args.all else "bike"
    # The tracked extract: scrubbed at write, refused on a leak, dated. This is
    # the copy a fresh clone builds from; out/ below is the same records where
    # project-record.py already reads them.
    ex = Extract("sfmta-pages").write(
        scope, list(pages.values()),
        meta={"site": "sfmta.com", "failed": failed})
    pages = {str(r["node"]): r for r in ex.records}

    n = len(pages)
    has = lambda k: sum(1 for r in pages.values() if r[k])  # noqa: E731
    dated = sum(1 for r in pages.values()
                if r["timeline"] or any(x["date"] for x in r["notices"] + r["meetings"]))
    print(f"{n} project pages read, {len(failed)} failed")
    print(f"  timeline {has('timeline')}, notices {has('notices')}, meetings {has('meetings')}, "
          f"updates {has('updates')}, documents {has('documents')}, image {has('image')}, of them full-size {has('image_full_size')}")
    print(f"  {dated} of {n} carry at least one dated event ({dated / max(1, n):.0%})")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    stable.write_json(OUT, {"generated": ex.fetched_on.isoformat(), "scope": scope,
                            "failed": failed, "pages": pages}, indent=1, ensure_ascii=True)
    print(f"→ {os.path.relpath(OUT, ROOT)} and {os.path.relpath(str(ex.path if hasattr(ex, 'path') else Extract('sfmta-pages').path('bike')), ROOT)}")
    if args.update:
        from lib import pipeline_state
        newest = max(LASTMOD.values()) if LASTMOD else None
        # A page sfmta.com refuses or no longer has (403, 404, 410) and that we
        # never held is not published, which no re-read will change: three
        # layer nodes answer 403 on every run. Anything else not reached is a
        # refresh that did not finish.
        gone = re.compile(r"HTTP Error (403|404|410)\b")
        pipeline_state.refreshed(
            "sitemap:sfmta-pages", STALE + [u for u, why in failed if not gone.match(why)],
            version=dt.datetime.utcfromtimestamp(newest).isoformat(timespec="seconds") if newest else None,
            detail="%d pages in the sitemap" % len(LASTMOD or {}))


if __name__ == "__main__":
    main()
