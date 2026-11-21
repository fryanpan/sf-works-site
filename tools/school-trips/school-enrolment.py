#!/usr/bin/env python3
"""Enrolment by grade for the school case study's public schools, from CDE DataQuest (Enrollment by Grade, school level), the latest school year published.

    tools/school-trips/school-enrolment.py            # read any school missing from the cache, at its latest year
    tools/school-trips/school-enrolment.py --update   # also ask for each school's newer years: see INCREMENTAL
    tools/school-trips/school-enrolment.py --refresh  # re-read every school's latest year

Schools are every public school in data/school-case/dropoff.json, matched to
its CDS code by name in data/extract/schools/cde-sf.json. Private schools are
not in DataQuest and are recorded with why. tools/school-trips/school-case.py calls
ensure() for any school it builds that the cache lacks.

INCREMENTAL. DataQuest has no change marker to ask, so --update is a bounded
re-read: for each public school, each school year after the one held, up to
the school year that contains today, newest first (at most two requests a
school, since a year runs August to July). The first year that parses
replaces the held copy. A year DataQuest hasn't posted returns a page with no
table, which reads as nothing new. A failed request keeps the held copy and
records the source as failed. The checks in pipeline/transportation-quality.py
(school-enrolment) run after every update: a record for every dropoff.json
school, each public one with a total between 20 and 5,000, grade shares
summing to 100 within 1.5 points, a year no older than the one held before,
and a URL that names that year.

Writes data/school-case/enrolment.json.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state, stable  # noqa: E402

ENROL = os.path.join(ROOT, "data", "school-case", "enrolment.json")
DROPOFF = os.path.join(ROOT, "data", "school-case", "dropoff.json")
CDE = os.path.join(ROOT, "data", "extract", "schools", "cde-sf.json")
MARKER = "cde:dataquest-enrolment"
GRADE_COLS = ["TK", "K", "1", "2", "3", "4", "5", "6", "7", "8", "UE", "9", "10", "11", "12", "US"]
OLDEST = 2024  # a fresh read looks back no further than 2024-25
NOTE = ("Enrolment by grade from CDE DataQuest (Enrollment by Grade, school level), the latest year published, "
        "written by tools/school-trips/school-enrolment.py. Private schools are not in DataQuest.")


def fetch(cds, year):
    """One school's year, or None when DataQuest has no table for it."""
    url = "https://dq.cde.ca.gov/dataquest/dqcensus/EnrGrdLevels.aspx?cds=%s&agglevel=school&year=%s" % (cds, year)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sf-works research"}), timeout=60).read()
    t = raw.decode("utf-8", "ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
    m = re.search(r"Ungr Sec Ascending Descending Name Total .*? Ungr Sec (.+?) ([\d,]+) ((?:[\d.]+% ){15}[\d.]+%)", t)
    if not m:
        return None
    pct = [float(v.rstrip("%")) for v in m.group(3).split()]
    return {"cds": cds, "year": year, "name": m.group(1).strip(), "total": int(m.group(2).replace(",", "")),
            "grade_pct": dict(zip(GRADE_COLS, pct)), "url": url}


def year_label(y):
    """2025 → "2025-26"."""
    return "%d-%02d" % (y, (y + 1) % 100)


def current_start(today):
    """The first calendar year of the school year containing today (August to July)."""
    return today.year if today.month >= 8 else today.year - 1


def latest(cds, newer_than, today):
    """The newest year after newer_than (a first calendar year) that DataQuest has, newest first, or None."""
    for y in range(current_start(today), newer_than, -1):
        got = fetch(cds, year_label(y))
        if got:
            return got
    return None


def ensure(schools, refresh=False, update=False, today=None):
    """The enrolment cache, with every school in `schools` present; fetches only what's missing unless asked.

    schools: dicts with id, repo_name, public. Returns (cache, failures)."""
    today = today or datetime.date.today()
    have = json.load(open(ENROL)) if os.path.exists(ENROL) else {"note": NOTE, "schools": {}}
    cde = {r["school"]: r for r in json.load(open(CDE))["records"]}
    stamp = today.isoformat()
    failures, changed = [], False
    for s in schools:
        held = have["schools"].get(s["id"])
        if held and not (refresh or update):
            continue
        r = cde.get(s["repo_name"])
        if not r or not s["public"]:
            row = {"total": None, "why": "Private school: not in CDE DataQuest's public-school enrolment."
                   if not s["public"] else "No CDE record matched by name."}
            if held != row:
                have["schools"][s["id"]] = row
                changed = True
            continue
        held_year = int(held["year"][:4]) if held and held.get("year") else OLDEST - 1
        try:
            got = latest(r["cds"], OLDEST - 1 if refresh else held_year, today)
        except Exception as exc:  # noqa: BLE001
            failures.append("%s: %s" % (s["id"], exc))
            continue
        if got is None:
            if not held:
                have["schools"][s["id"]] = {"total": None, "why": "CDE page did not parse.", "cds": r["cds"]}
                changed = True
            continue
        if held and held.get("year") == got["year"] and held.get("total") == got["total"] \
                and held.get("grade_pct") == got["grade_pct"]:
            continue
        got["read"] = stamp
        got["tag"] = "[primary — read %s]" % stamp
        have["schools"][s["id"]] = got
        changed = True
        print("  %s: %s, %d students" % (s["id"], got["year"], got["total"]))
    if changed:
        have["note"] = NOTE
        have["schools"] = {k: have["schools"][k] for k in sorted(have["schools"])}
        stable.write_json(ENROL, have, indent=1)
    return have, failures, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="ask for each school's newer years (bounded re-read)")
    ap.add_argument("--refresh", action="store_true", help="re-read every school's latest year")
    a = ap.parse_args()
    schools = json.load(open(DROPOFF))["schools"]
    have, failures, changed = ensure(schools, refresh=a.refresh, update=a.update)
    if a.update or a.refresh:
        years = sorted({v["year"] for v in have["schools"].values() if v.get("year")})
        pipeline_state.refreshed(MARKER, failures, version=",".join(years),
                                 detail="newer years asked for each public school; %s" % ("a newer year read" if changed else "nothing new"))
    for f in failures:
        print("  enrolment re-read failed, held copy kept: %s" % f)
    pub = {k: v for k, v in have["schools"].items() if v.get("total")}
    print("  enrolment: %d schools, %d with a CDE count (%s)" % (
        len(have["schools"]), len(pub), ", ".join("%s %s %d" % (k, v["year"], v["total"]) for k, v in sorted(pub.items()))))


if __name__ == "__main__":
    main()
