#!/usr/bin/env python3
"""How San Franciscans travel, 2015 to today: SFMTA's all-trips survey and the Census commute series, against the 80% target.

    tools/travel/sf-mode-share.py              # writes site/data/mode-share.json
    tools/travel/sf-mode-share.py --refetch    # re-read the Census tables first

Bryan, 2026-09-24: "Can we add a section on mode share from 2015 to 2025?
And note the 2030 target of 80% non car mode share (check sources on all of
this)", and "Ultimately our goal isn't some abstract metric like
connectivity the goal is to make it comfortable enough for people to choose
to bike over other modes of transportation."

Two series, because neither covers the whole window:

  SFMTA Travel Decisions Survey   every trip in San Francisco, by residents
                                  and visitors, fall 2015, 2017, 2019, 2021.
                                  No later survey is published on sfmta.com
                                  (checked 2026-09-24). Figures are the
                                  reports' own rounded percentages, hand
                                  entered below with the page they sit on.
  Census ACS 1-year, B08301       means of transportation to work, San
                                  Francisco County, every year the Census
                                  publishes it (no 2020 1-year release; 2025
                                  not yet out). Commutes only. Read from
                                  data.census.gov's table endpoint, which
                                  needs no key; api.census.gov now does.

Walking, biking and transit are summed for each. The survey's share is of
all trips; the commute share is of workers who travelled, leaving out those
who worked from home, so the pandemic's home workers do not read as a shift
to the car or away from it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import Extract  # noqa: E402
from lib import pipeline_state, stable  # noqa: E402

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "site", "data", "mode-share.json")
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"
ACS = "https://data.census.gov/api/access/data/table?id=ACSDT1Y{y}.B08301&g=050XX00US06075"
ACS_PAGE = "https://data.census.gov/table/ACSDT1Y{y}.B08301?g=050XX00US06075"
FIRST, LAST = 2015, dt.date.today().year

# Each report's "Estimated Mode Share in San Francisco" table, all trips in
# the city by residents and visitors, fall of the year. Read 2026-09-24.
SURVEYS = [
    {"year": 2015, "url": "https://www.sfmta.com/media/5698/download?inline", "page": 5,
     "walk": 25, "bike": 2, "transit": 24, "privateAuto": 47, "tnc": 2},
    {"year": 2017, "url": "https://www.sfmta.com/media/9328/download?inline", "page": 5,
     "walk": 25, "bike": 2, "transit": 26, "privateAuto": 43, "tnc": 4},
    {"year": 2019, "url": "https://www.sfmta.com/sites/default/files/reports-and-documents/2020/01/sfmta_travel_decision_survey_2019.pdf", "page": 5,
     "walk": 22, "bike": 2, "transit": 22, "privateAuto": 48, "tnc": 5},
    {"year": 2021, "url": "https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf", "page": 5,
     "walk": 24, "bike": 3, "transit": 10, "privateAuto": 61, "tnc": 2},
]

TARGET = {
    "share": 80, "year": 2030,
    "climate": {"words": "By 2030, 80% of trips taken by low-carbon modes",
                "source": "San Francisco Climate Action Plan 2021, Executive Summary",
                "url": "https://www.sfcta.org/sites/default/files/2022-01/Item%2011%20-%20Climate%20Action%20Plan%20Executive%20Summary.pdf",
                "page": 5, "read": "2026-09-24"},
    "sfmta": {"words": "SFMTA's Strategic Objective 2.2 Key Performance Indicator (80% Sustainable Mode Share)",
              "counts": "walking, bicycling, and public transit",
              "source": "SFMTA Travel Decisions Survey 2019", "url": SURVEYS[2]["url"], "page": 3, "read": "2026-09-24"},
    # The Department of the Environment's March 2026 update restates the 2021
    # goal with its modes named, and sets a driving target in its place.
    # Whether the update has been adopted was not checked.
    "update": {"source": "San Francisco Climate Action Plan, Updated Sector Goals & Current Status (SF Environment, March 2026)",
               "url": "https://www.sfenvironment.org/files/2026-03/Item%2008.%20SF%20CAP%20Update%20Sector%20Goals%20%26%20Current%20Status.pdf",
               "old": "By 2030, 80% of trips taken by low carbon modes such as walking, biking, transit, and shared EVs.",
               "new": "By 2030, achieve a 25% reduction in per-capita vehicle miles traveled",
               "vmt2019": 12.4, "vmtSep2025": 12, "vmtGoal": 9.3, "read": "2026-09-24"},
}

WEEKLY = {"share": 29, "daily": 10,
          "words": "29% of people bike or roll every week for commute, shopping, recreational, and social trips",
          "source": "San Francisco Biking and Rolling Plan (2025), p. 12, from its Resident Preference Survey (Appendix K)",
          "read": "2026-09-24"}


def acs_year(year):
    """{column: value} for one year of B08301, or None when that year is not published.

    data.census.gov answers an unpublished year with HTTP 400. Any other
    failure (a timeout, a 5xx) raises: reading it as "not published" would
    drop a year from the series, or say a release is not out when it is.
    """
    req = urllib.request.Request(ACS.format(y=year), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            d = json.load(fh).get("response", {}).get("data")
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            return None
        raise
    return dict(zip(d[0], d[1])) if d else None


def published(year):
    """True when data.census.gov answers for this year's B08301."""
    return acs_year(year) is not None


def fetch_acs():
    rows = []
    for y in range(FIRST, LAST + 1):
        e = acs_year(y)
        if e is None:
            continue
        rows.append({"year": y, **{k: float(e[k]) for k in (
            "B08301_001E", "B08301_003E", "B08301_004E", "B08301_010E", "B08301_016E", "B08301_017E",
            "B08301_018E", "B08301_019E", "B08301_020E", "B08301_021E", "B08301_018M")}})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--update", action="store_true",
                    help="re-read the Census tables only if a year newer than the extract's is published")
    args = ap.parse_args()
    refresh = args.refetch
    if args.update:
        have = Extract("census-acs").read("b08301-sf")
        nxt = max(r["year"] for r in have.records) + 1 if have else FIRST
        try:
            out_now = published(nxt)
        except Exception as exc:  # noqa: BLE001
            # Unknown is not "not yet published": record the failed check and
            # keep the extract, so the next run asks again.
            pipeline_state.record("census:acs1-b08301", "failed", detail=f"release check for {nxt} failed: {exc}")
            print(f"  ACS 1-year {nxt}: release check failed ({exc}); keeping the extract")
            out_now = False
        else:
            pipeline_state.record("census:acs1-b08301", "changed" if out_now else "unchanged",
                                  version=str(nxt if out_now else nxt - 1),
                                  detail=f"ACS 1-year {nxt} {'published' if out_now else 'not yet published'}")
            print(f"  ACS 1-year {nxt}: {'published, re-reading' if out_now else 'not yet published'}")
        refresh = refresh or have is None or out_now
    acs = Extract("census-acs").fetch_or_read("b08301-sf", fetch_acs, refresh=refresh,
                                              meta={"table": "B08301", "geo": "San Francisco County", "product": "ACS 1-year"})
    commute = []
    for r in acs.records:
        workers, home = r["B08301_001E"], r["B08301_021E"]
        travelled = workers - home
        wbt = r["B08301_010E"] + r["B08301_018E"] + r["B08301_019E"]
        commute.append({"year": r["year"], "share": round(100 * wbt / travelled, 1),
                        "bike": round(100 * r["B08301_018E"] / travelled, 1),
                        "bikeOfWorkers": round(100 * r["B08301_018E"] / workers, 1),
                        "car": round(100 * (r["B08301_003E"] + r["B08301_004E"]) / travelled, 1),
                        "home": round(100 * home / workers, 1), "workers": int(workers),
                        "url": ACS_PAGE.format(y=r["year"])})
    surveys = [{**s, "share": s["walk"] + s["bike"] + s["transit"]} for s in SURVEYS]
    out = {"generated": dt.date.today().isoformat(), "acsRead": acs.fetched_on.isoformat(),
           "surveys": surveys, "commute": commute, "target": TARGET, "weekly": WEEKLY,
           "note": "Survey shares are the reports' rounded figures summed; commute shares leave out people who worked from home."}
    stable.write_json(OUT, out, indent=1)
    for s in surveys:
        print(f"survey {s['year']}: walk+bike+transit {s['share']}% of trips, bike {s['bike']}%")
    for c in commute:
        print(f"acs {c['year']}: walk+bike+transit {c['share']}% of commutes, bike {c['bike']}%, home {c['home']}%")
    print(f"→ {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
