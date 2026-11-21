#!/usr/bin/env python3
"""What the Board of Supervisors legislated about a named street.

Bryan, 2026-09-21: "I'd like to have the legislative and engineering record.
Anything that can be correlated with the project, please include."

The engineering half is already read — `tools/meetings/sfmta-hearings.py` for the City
Traffic Engineer's orders and `tools/meetings/sfmta-board-records.py` for the SFMTA
Board. This is the legislative half: the Board of Supervisors, through Legistar.

WHAT THIS CAN AND CANNOT SEE. The Board does not legislate bikeway geometry —
that is the hearing's job, and the 58-to-14 split between the two records is
itself the finding. What the Board does do to a street is vacate it, permit an
encroachment on it, rename it, set its speed limit, appropriate money for it,
and urge an agency to act on it. So this reads a fixed list of phrases and
keeps only files whose TITLE names a street, because the title is where the
Board writes the street and the body is where every unrelated address lives.

Both halves of that are denominators a reader is owed, and the report prints
them: which phrases were searched, over which years, and how many files each
phrase returned before the title filter.

ONE YEAR AT A TIME, deliberately. Legistar's search returns at most 100 rows
and says nothing about the rest; `sf_legistar.py` splits a capped result by
matter type, but an All-Years query on a common phrase is both slow and liable
to stay capped inside a single type, where there is no further lever. A year is
small enough that almost every phrase fits under the cap in one request, so the
sweep is both complete and roughly six times faster.

    tools/meetings/bos-street-records.py
    tools/meetings/bos-street-records.py --refetch          # ignore the cache
    tools/meetings/bos-street-records.py --from 2024        # a shorter window

Output: out/bos-records/street-items.json and street-items.md.
`tools/projects/project-record.py` reads the JSON and links these to projects.
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from streetnames import corridors, streets_in_order  # noqa: E402
from lib import stable  # noqa: E402

OUT = os.path.join(ROOT, "out", "bos-records")
CACHE = os.path.join(ROOT, ".cache", "bos-records")

# Phrases the Board uses when a street is the subject. Quoted, because an
# unquoted term is OR-ed into noise by Legistar's search. Each one is a
# denominator the report names, so adding to this list changes a published
# number and the list is the honest account of what was looked for.
TERMS = [
    "bikeway",
    "bicycle lane",
    "bike lane",
    "bicycle facility",
    "street vacation",
    "traffic calming",
    "Vision Zero",
    "quick-build",
    "speed limit",
    "encroachment",
    "street renaming",
    "sidewalk widening",
    # Added 2026-09-21, once the title filter made a broad phrase safe to
    # search. Before it, "streetscape" or "crosswalk" would each have dragged
    # in several hundred property matters that merely cite them.
    "streetscape",
    "Slow Streets",
    "car-free",
    "street closure",
    "transit-only",
    "road diet",
    "pedestrian safety",
    "Better Streets",
    "traffic signal",
    "crosswalk",
    "curb ramp",
    "bicycle network",
]

# Title words that would otherwise be read as a street name. The shared parser
# is tuned for SFMTA order text; a Board title carries its own furniture.
BOS_NOISE = re.compile(
    r"\b(code|codes|section|sections|chapter|article|ordinance|resolution|"
    r"motion|hearing|amending|adding|repealing|approving|authorizing)\b",
    re.IGNORECASE)


def iso(d):
    """Legistar prints a final action as M/D/YYYY; every other source here is
    ISO, and a mixed column sorts and reads wrong."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", (d or "").strip())
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m \
        else (d or "").strip()


HISTORY = os.path.join(CACHE, "history")
BOARD = "Board of Supervisors"


def history(f, refetch=False):
    """A file's legislative history, newest first, as Legistar's detail page prints it: (date, body, action).

    Legistar's search row gives only the file's final action, the date the
    Mayor signed it or the Clerk filed it, which is not a meeting: file 220450
    was finally passed by the Board on 2022-07-19 and signed 2022-07-28 (D2
    hand grade, 2026-09-29). The history names each body that acted and when.
    Cached under the file's status and final action, so a file is read again
    only when one of those moves. None when the page cannot be read.
    """
    path = cached("history", f["url"], f.get("status") or "", f.get("final_action") or "")
    path = os.path.join(HISTORY, os.path.basename(path))
    if not refetch and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))["rows"]
    import html as htmlmod
    import ssl
    import urllib.request
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # the host's chain does not validate here (sf_legistar.py)
    url = re.sub(r"&FullText=1$", "", f["url"])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (sf-works bos-street-records)"})
        page = urllib.request.urlopen(req, timeout=60, context=ctx).read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - any failure keeps the search row's date
        print(f"  !! history of {f.get('file')}: {e}", file=sys.stderr)
        return None
    at = page.find("gridLegislation_ctl00")
    if at < 0:
        print(f"  !! history of {f.get('file')}: no history table on the page", file=sys.stderr)
        return None
    rows = []
    for tr in re.findall(r'(?s)<tr class="rg(?:Alt)?Row"[^>]*>(.*?)</tr>', page[at:]):
        cells = [" ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"(?s)<td[^>]*>(.*?)</td>", tr)]
        if len(cells) >= 4 and re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", cells[0]):
            rows.append([iso(cells[0]), cells[2], cells[3]])
    os.makedirs(HISTORY, exist_ok=True)
    json.dump({"url": f["url"], "rows": rows, "fetched_on": dt.date.today().isoformat()},
              open(path, "w", encoding="utf-8"), indent=1)
    return rows


def meeting_date(rows):
    """(date, body, action) of the last meeting that acted on the file: the full Board's, else a committee's.
    The Clerk, the President and the Mayor act outside a meeting, so theirs are not counted."""
    # A row with no action is an agenda placeholder for a meeting not yet held
    # or not yet minuted (file 260873, 2026-09-29), so it is not an action.
    rows = [r for r in rows or () if r[2].strip() and r[0] <= dt.date.today().isoformat()]
    # "Joint Special Meeting with the Board of Supervisors and ..." is the Board too (file 220339).
    acted = [r for r in rows if BOARD in r[1]]
    acted = acted or [r for r in rows if "Committee" in r[1]]
    if not acted:
        return None
    last = [r for r in acted if r[0] == max(x[0] for x in acted)]
    # Of one day's actions, the one that decided ("ADOPTED AS AMENDED" over the "AMENDED" before it).
    return next((r for r in last if re.search(r"passed|adopted|approved|tabled|killed|filed", r[2], re.I)), last[0])


def cached(*parts):
    key = hashlib.sha1("\x1f".join(parts).encode()).hexdigest()
    return os.path.join(CACHE, key + ".json")


def fetch(term, years, refetch):
    """Every file matching one phrase, with the count Legistar returned."""
    path = cached(term, years)
    if not refetch and os.path.exists(path):
        blob = json.load(open(path, encoding="utf-8"))
        return blob["rows"], blob["capped"]

    os.makedirs(CACHE, exist_ok=True)
    tmp = path + ".raw"
    # sf_legistar.py re-execs into its own venv, so it is run as a process
    # rather than imported — the same way amendment-check.py reaches it.
    # ALLOW_SHORT because a sweep would rather record which phrases Legistar
    # truncated than stop at the first one; the report prints them.
    env = dict(os.environ, SF_LEGISTAR_ALLOW_SHORT="1")
    subprocess.check_call(
        [sys.executable, paths.script("sf_legistar.py"),
         "search", '"%s"' % term, years, tmp],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    rows = json.load(open(tmp, encoding="utf-8"))
    still = json.load(open(tmp + ".capped", encoding="utf-8"))
    os.remove(tmp)
    os.remove(tmp + ".capped")
    if os.path.exists(path):
        # A Legistar file does not leave a year's search once it is in it, so
        # a re-search (--update) that returns fewer files than the answer we
        # hold is a short read: Legistar truncated it or timed out part way.
        # Keep every file we held, with the new rows' titles and statuses.
        old = json.load(open(path, encoding="utf-8"))
        have = {r["url"] for r in rows}
        lost = [r for r in old["rows"] if r["url"] not in have]
        if lost:
            print(f"  !! {term} {years}: re-search returned {len(rows)} files, held {len(old['rows'])}; "
                  f"keeping the {len(lost)} it did not return", file=sys.stderr)
            rows = rows + lost
    blob = {"term": term, "years": years, "rows": rows, "capped": still,
            "fetched_on": dt.date.today().isoformat()}
    json.dump(blob, open(path, "w", encoding="utf-8"), indent=1)
    return rows, still


def named_streets(title):
    """Streets a Board title LEGISLATES, or an empty list.

    Not every street a title names is one the Board is acting on. "located at
    2245 Post Street" is a building, and taking it as a corridor put a zoning
    district at one address beside a sewer job that runs the length of Post
    Street — one of eight bad links in a sample of eight before this. The
    address forms are dropped; `all_streets` keeps them for the report, so the
    reader can see what was set aside rather than only what survived.
    """
    if not title:
        return []
    # Strip the code-amendment furniture before the walk, so "Public Works
    # Code" does not contribute and "amending the Administrative Code" does
    # not put "code" in front of a suffix.
    return corridors(BOS_NOISE.sub(" ", title))


def all_streets(title):
    """Every street the title names, address or corridor."""
    return streets_in_order(BOS_NOISE.sub(" ", title)) if title else []


def collect(years, refetch, fresh_years=()):
    """`fresh_years` are re-searched even when cached (--update): files filed
    this year and last year are the ones whose status can still change."""
    by_url, counts, capped = {}, {}, {}
    for term in TERMS:
        total = 0
        for y in years:
            rows, still = fetch(term, y, refetch or y in fresh_years)
            total += len(rows)
            if still:
                capped.setdefault(term, []).append(f"{y}: {', '.join(still)}")
            for r in rows:
                rec = by_url.setdefault(r["url"], dict(r, terms=[]))
                if term not in rec["terms"]:
                    rec["terms"].append(term)
        counts[term] = total
        print(f"  {term:20s} {total:4d} files", flush=True)
    return list(by_url.values()), counts, capped


def in_title(f):
    """The search phrases that appear in the title, not merely in the body."""
    t = (f["title"] or "").lower()
    return [x for x in f["terms"] if x.lower() in t]


def to_records(files, refetch=False):
    """Keep the files that are ABOUT a street, and name which one.

    Two filters, and the first matters more than it looks. Legistar's search
    reads the body and every attachment, so "encroachment" matches any property
    matter carrying an encroachment clause and "Vision Zero" matches any
    document citing the policy in passing. 1,011 files came back and a sample of
    eight trusted links was eight wrong: a zoning district, a final map, a
    parcel lease. Requiring the phrase in the TITLE is what separates a file the
    Board is deciding about a street from one that mentions one.

    The second filter is the street itself: an address is one lot and a project
    is a corridor, so "located at 2245 Post Street" does not count.
    """
    kept, dropped, address_only, offtopic = [], 0, 0, 0
    for f in files:
        titled = in_title(f)
        if not titled:
            offtopic += 1
            continue
        named = named_streets(f["title"])
        if not named:
            dropped += 1
            if all_streets(f["title"]):
                address_only += 1
            continue
        # The record is dated by the last meeting that acted on the file; a
        # file no meeting took up (250429: received, then filed by the
        # Clerk) keeps its final action and says it was never heard.
        final = iso(f.get("final_action"))
        hist = history(f, refetch)
        met = meeting_date(hist)
        date, decision, basis = final, f.get("status"), "final action"
        if met:
            date, basis = met[0], ("%s: %s" % (met[1], met[2].lower())) if met[2] else met[1]
            # The decision is the one taken on that date. A file a committee
            # last acted on, and the Clerk later filed without a meeting
            # (220708: amended 2022-07-25, filed 2024-10-22), shows the
            # committee's action beside the committee's date, not "Filed"
            # (Fable review, 2026-09-30).
            # A status the meeting's action already says ("Passed" for
            # "FINALLY PASSED", the Mayor signing later) stays as it is.
            same = next((rx for rx in (r"pass|adopt|approv", r"filed|tabled|killed|withdr")
                         if re.search(rx, decision or "", re.I)), None)
            if met[2] and not (same and re.search(same, met[2], re.I)) and met[0] != final:
                decision = met[2][0].upper() + met[2][1:].lower()
        elif hist is not None and (f.get("status") or "").lower() == "filed":
            decision, basis = "Filed without a hearing", "final action; no meeting acted on the file"
        kept.append({
            "kind": "supervisors",
            "date": date,
            "dateBasis": basis,
            "finalAction": final,
            "item": f.get("file"),
            "title": f["title"],
            "type": f.get("type"),
            "status": f.get("status"),
            "districts": [],
            "decision": decision,
            "approver": "Board of Supervisors",
            "url": f["url"],
            "streets": named,
            "terms": titled,
            "foundBy": f["terms"],
        })
    kept.sort(key=lambda r: (r["date"] or "", r["item"] or ""), reverse=True)
    return kept, dropped, address_only, offtopic


def selfcheck(files, records):
    """A file whose title plainly names a street but produced none is a bug.

    Every reader in this repo re-reads its own raw source and flags what it
    failed to parse, because a parser that silently returns nothing is
    indistinguishable from a quiet year. Here the tell is a title containing a
    street suffix with no street coming out of it.
    """
    suffix = re.compile(r"\b(Street|Avenue|Boulevard|Road|Drive|Way|Place|"
                        r"Terrace|Lane|Court|Highway|Plaza|Parkway)\b")
    have = {r["url"] for r in records}
    # A title whose only street is an address was set aside on purpose, so it
    # is not a miss. Counting it as one would bury the real misses under it.
    missed = [f for f in files
              if f["url"] not in have and suffix.search(f["title"] or "")
              and not all_streets(f["title"])]
    return missed


def report(records, counts, capped, missed, files, address_only, offtopic,
           years, path):
    lines = ["# Board of Supervisors records that name a street", ""]
    lines.append(f"Generated {dt.date.today().isoformat()} by "
                 "`tools/meetings/bos-street-records.py`. **Do not edit by hand — the "
                 "next run overwrites it.**")
    lines.append("")
    lines.append(
        f"**{len(records)} records, from {len(files)} files read.** Two filters "
        "stand between those numbers, and both are here because the first "
        "sample of eight trusted links was eight wrong.")
    lines.append("")
    lines.append(
        f"- **{offtopic} files carry the search phrase only in the body.** "
        "Legistar searches every attachment, so `encroachment` matches any "
        "property matter with an encroachment clause and `Vision Zero` matches "
        "anything citing the policy in passing. A file the Board is deciding "
        "about a street says so in its title.")
    lines.append(
        f"- **{address_only} name a street only as a building's address** — "
        "\"located at 2245 Post Street\". An address is one lot; a project is "
        "a corridor.")
    lines.append("")
    lines.append(f"Years searched: **{years}**.")
    lines.append("")

    lines.append("## What was searched")
    lines.append("")
    lines.append("| Phrase | Files returned |")
    lines.append("| --- | ---: |")
    for t in TERMS:
        lines.append(f"| `{t}` | {counts.get(t, 0)} |")
    lines.append("")
    if capped:
        lines.append("**Short results.** Legistar returns at most 100 rows per "
                     "query and says nothing about the rest. These phrases were "
                     "still at the cap after splitting by matter type, so their "
                     "counts are floors:")
        for t, where in capped.items():
            lines.append(f"- `{t}` — capped in {'; '.join(where)}")
        lines.append("")

    kinds = collections.Counter(r["type"] for r in records)
    lines.append("## What kind of file")
    lines.append("")
    lines.append("| Type | Files |")
    lines.append("| --- | ---: |")
    for k, n in kinds.most_common():
        lines.append(f"| {k or '—'} | {n} |")
    lines.append("")

    if missed:
        lines.append("## Titles with a street suffix that produced no street")
        lines.append("")
        lines.append(f"{len(missed)} of {len(files)}. Each is a parser miss to "
                     "read, not a file to ignore.")
        lines.append("")
        for f in missed[:40]:
            lines.append(f"- [{f['file']}]({f['url']}) — {f['title'][:160]}")
        lines.append("")

    lines.append("## The records")
    lines.append("")
    for r in records:
        head = r["title"][:300]
        lines.append(f"### [{r['item']}]({r['url']}) — {r['type']}")
        lines.append("")
        lines.append(head)
        lines.append("")
        lines.append(f"- Streets named: {', '.join(r['streets'])}")
        lines.append(f"- Status: {r['status'] or '—'}")
        if r["date"]:
            lines.append(f"- Dated: {r['date']} ({r['dateBasis']})")
        if r["finalAction"] and r["finalAction"] != r["date"]:
            lines.append(f"- Final action: {r['finalAction']}")
        lines.append(f"- Found by: {', '.join('`%s`' % t for t in r['terms'])}")
        lines.append("")

    stable.write_text(path, "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--update", action="store_true",
                    help="re-search this year and last year; keep earlier years' cached answers")
    ap.add_argument("--from", dest="start", type=int, default=2019,
                    help="first year to sweep (default 2019)")
    a = ap.parse_args()

    years = [str(y) for y in range(a.start, dt.date.today().year + 1)]
    window = f"{years[0]}–{years[-1]}"
    os.makedirs(OUT, exist_ok=True)
    fresh = years[-2:] if a.update else ()
    files, counts, capped = collect(years, a.refetch, fresh)
    records, dropped, address_only, offtopic = to_records(files, a.refetch)
    missed = selfcheck(files, records)

    js = os.path.join(OUT, "street-items.json")
    stable.write_json(js, {"generated": dt.datetime.now().isoformat(timespec="seconds"),
               "years": window, "terms": TERMS, "counts": counts,
               "capped": capped, "files": len(files),
               "addressOnly": address_only, "offTopic": offtopic,
               "unparsed": [f["url"] for f in missed],
               "matches": records}, indent=1, ensure_ascii=True)
    report(records, counts, capped, missed, files, address_only, offtopic,
           window, os.path.join(OUT, "street-items.md"))

    print(f"{len(records)} records of {len(files)} files read "
          f"({offtopic} phrase in body only, {address_only} address only) "
          f"→ {OUT}")
    if missed:
        print(f"  !! {len(missed)} titles carry a street suffix and parsed to "
              "no street — listed in the report")
    if capped:
        print(f"  !! {len(capped)} phrases are still at Legistar's 100-row cap")


if __name__ == "__main__":
    main()
