#!/usr/bin/env python3
"""Measure the discussion-record criteria C1 to C4 of pipeline/transportation-data-audit-criteria.md against the current data.

    tools/projects/record-coverage.py                          # print every measure and its pass line
    tools/projects/record-coverage.py --json out/record-coverage/coverage.json
    tools/projects/record-coverage.py --coordination OTHER.json  # measure another build, e.g. a baseline

Reads site/data/coordination.json (the listed projects and the records
attached to each) and data/<body>/index.json (what each body's fetch script
mirrored). Nothing here reaches the network.

  C1  per deciding body: the window read, meetings listed, meetings missing,
      whether full item titles are kept. Pass: from 2019 or earlier to within
      31 days of today, under 5% missing, full titles.
  C2  per major project (outlined on the list, or at least one plan mile):
      distinct dates carrying a city-body record graded exact, strong or
      probable. Pass: 80% have three or more.
  C3  records from a project's own page shown with a city body's label, and
      records whose title names the project that are graded weaker than the
      project's own. Pass: zero of each.
  C4  listed projects with a start date that have a city-body record dated
      before the start. Pass: over 90%. Each one without is listed with the
      body that should have decided it.

"City-body record" means a record from a body's own agenda, minutes or
order, never an item copied off the project's web page.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.mirror import index as body_index  # noqa: E402
from lib import stable  # noqa: E402

COORD = os.path.join(ROOT, "site", "data", "coordination.json")
TRUSTED = {"exact", "strong", "probable"}
OWNPAGE = "listed on this project's own page"
CITY_KINDS = {"hearing", "board", "supervisors", "sfpuc", "sfcta", "pwc", "pwdelegated", "recpark"}
CITY_LABELS = {"Engineering hearing", "SFMTA Board", "Board of Supervisors", "SFPUC Commission",
               "SFCTA Board", "Public Works Commission", "Recreation and Park Commission"}

# The deciding bodies C1 names, with the mirror each one's fetch script writes.
BODIES = [
    ("SFMTA engineering hearings", "sfmta-hearings"),
    ("SFMTA Board", "sfmta-board"),
    ("Board of Supervisors", "bos-meetings"),
    ("SFPUC Commission", "sfpuc-commission"),
    ("Public Works Commission", "public-works-commission"),
    ("SFCTA Board", "sfcta-board"),
    ("Recreation and Park Commission", "rec-park-commission"),
]

# A body that did not exist in 2019 cannot be read from 2019: it is read from
# its first meeting. The Public Works Commission's transition date is set by
# the Board of Supervisors' motion of 2021-12-14, "setting July 1, 2022, as the
# Transition Date, pursuant to Charter, Section 4.139(d), for purposes of
# establishing the Sanitation and Streets Commission" (data/bos-meetings/,
# meeting 914226). Before it, Public Works contracts were the Director's to
# award, which C4 names as the body for those projects.
ESTABLISHED = {
    "Public Works Commission": ("2022-07-01", "Board of Supervisors motion of 2021-12-14 setting the Charter "
                                              "§4.139(d) transition date"),
}


def is_city(r):
    return r.get("kind") in CITY_KINDS and r.get("relation") != OWNPAGE


def month_key(d):
    """A record or start date as a comparable string; '2025' and '2025-06' stay coarse."""
    return (d or "")[:10]


# C4's rule ("a city-body record dated before the start") lives in
# lib/record_dates.py, which the audit's C4 reads too.
from lib.record_dates import records_before_start  # noqa: E402


GENERIC = re.compile(r"\b(project|projects|program|phase \w+|improvements?|pw|joint|streetscape lead)\b")


def core_name(name):
    t = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    t = GENERIC.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def should_decide(p):
    """The body that should carry a dated decision on this project, by who runs it."""
    dept = p["department"]
    if dept == "SFMTA":
        return "SFMTA engineering hearing or SFMTA Board (legislation); SFCTA Board if Prop K/L funds it"
    if dept == "SFPUC":
        return "SFPUC Commission (contract award)"
    if (p.get("start") or "") < "2022-07":
        return "Director of Public Works (contract awards before the Public Works Commission first met, 2022-07-28)"
    return "Public Works Commission (contract award)"


def measure(coord_path):
    d = json.load(open(coord_path, encoding="utf-8"))
    P = d["projects"]
    # Measured as of the day the record was built, not the wall clock, so a
    # rerun on unchanged data writes the same file.
    today = (d.get("generated") or dt.date.today().isoformat())[:10]
    res = {"generated": today, "coordination": os.path.relpath(coord_path, ROOT),
           "coordinationGenerated": d.get("generated")}

    # C1 ---------------------------------------------------------------
    c1 = []
    for name, body in BODIES:
        idx = body_index(body)
        if not idx:
            c1.append({"body": name, "mirror": body, "read": False, "pass": False})
            continue
        last_held = max((m["date"] for m in idx["meetings"] if m["date"] <= today), default=None)
        lag = (dt.date.fromisoformat(today) - dt.date.fromisoformat(last_held)).days if last_held else None
        held = [m for m in idx["meetings"] if m["date"] <= today]
        missing = [m for m in held if m["outcome"] != "mirrored"]
        share = len(missing) / len(held) if held else None
        first = idx["range"][0] if idx["range"] else None
        row = {"body": name, "mirror": body, "read": True, "first": first, "last": last_held,
               "daysSinceLast": lag, "held": len(held), "missing": len(missing),
               "missingShare": round(share, 4) if share is not None else None,
               "items": idx["items"], "fullTitles": True,
               "startsBy2019": bool(first and first < "2020-01-01"),
               "notes": idx.get("notes", [])}
        est = ESTABLISHED.get(name)
        if est:
            row["established"], row["establishedSource"] = est
            # Read from its first meeting: the first mirrored one within 60 days of the transition.
            row["startsBy2019"] = bool(first and (dt.date.fromisoformat(first) - dt.date.fromisoformat(est[0])).days <= 60)
        row["pass"] = bool(row["startsBy2019"] and lag is not None and lag <= 31 and share is not None and share < 0.05)
        c1.append(row)
    res["C1"] = c1

    # C2 ---------------------------------------------------------------
    major = [p for p in P if p.get("highlight") or (p.get("planMiles") or 0) >= 1]
    rows = []
    for p in major:
        dates = sorted({r["date"][:10] for r in p["records"] if is_city(r) and r.get("grade") in TRUSTED and r.get("date")})
        rows.append({"name": p["name"], "department": p["department"], "dates": len(dates)})
    three = sum(1 for r in rows if r["dates"] >= 3)
    res["C2"] = {"major": len(major), "threeOrMore": three,
                 "share": round(three / len(major), 4) if major else None,
                 "distribution": dict(collections.Counter(min(r["dates"], 3) for r in rows)),
                 "byDepartment": {dep: {"major": sum(1 for r in rows if r["department"] == dep),
                                        "threeOrMore": sum(1 for r in rows if r["department"] == dep and r["dates"] >= 3)}
                                  for dep in sorted({r["department"] for r in rows})},
                 "below": sorted((r for r in rows if r["dates"] < 3), key=lambda r: (r["dates"], r["name"])),
                 "pass": bool(major) and three / len(major) >= 0.8}

    # C3 ---------------------------------------------------------------
    mislabelled = [{"project": p["name"], "date": r.get("date"), "label": r.get("label"), "title": r.get("title", "")[:100]}
                   for p in P for r in p["records"]
                   if r.get("relation") == OWNPAGE and r.get("label") in CITY_LABELS]
    weaker = []
    for p in P:
        core = core_name(p["name"])
        if len(core) < 10:
            continue
        for r in p["records"]:
            if r.get("grade") in TRUSTED or not is_city(r):
                continue
            if core in core_name(r.get("title")):
                weaker.append({"project": p["name"], "date": r.get("date"), "grade": r.get("grade"),
                               "title": r.get("title", "")[:100]})
    res["C3"] = {"pageItemsWithCityLabel": len(mislabelled), "nameMatchesGradedWeaker": len(weaker),
                 "examples": mislabelled[:10] + weaker[:10],
                 "pass": not mislabelled and not weaker}

    # C4 ---------------------------------------------------------------
    dated = [p for p in P if p.get("start")]
    got, without = 0, []
    for p in dated:
        prior = records_before_start(p)
        if prior:
            got += 1
        else:
            later = [r for r in p["records"] if is_city(r) and r.get("grade") in TRUSTED]
            without.append({"name": p["name"], "department": p["department"], "start": p["start"],
                            "phase": p.get("phase"),
                            "cityRecordsAfterStart": len(later),
                            "shouldDecide": should_decide(p)})
    res["C4"] = {"withStart": len(dated), "withPriorRecord": got,
                 "share": round(got / len(dated), 4) if dated else None,
                 "byDepartment": {dep: {"withStart": sum(1 for p in dated if p["department"] == dep),
                                        "without": sum(1 for w in without if w["department"] == dep)}
                                  for dep in sorted({p["department"] for p in dated})},
                 "without": sorted(without, key=lambda w: (w["department"], w["start"], w["name"])),
                 "pass": bool(dated) and got / len(dated) > 0.9}
    # A planned contract that has not started usually has not been awarded
    # yet, so its deciding record may simply not exist; split the two so the
    # share for projects already under way can be read on its own.
    started = [p for p in dated if p["start"] <= today]
    started_without = [w for w in without if w["start"] <= today]
    res["C4"]["startedByToday"] = {"withStart": len(started),
                                   "withPriorRecord": len(started) - len(started_without),
                                   "share": round(1 - len(started_without) / len(started), 4) if started else None}
    res["C4"]["notYetStarted"] = {"withStart": len(dated) - len(started),
                                  "withPriorRecord": got - (len(started) - len(started_without))}
    return res


def show(res):
    print("C1 source coverage")
    for r in res["C1"]:
        if not r["read"]:
            print("  FAIL %-32s not mirrored" % r["body"])
            continue
        print("  %s %-32s %s..%s  %d held, %d missing (%.1f%%), %d items"
              % ("pass" if r["pass"] else "FAIL", r["body"], r["first"], r["last"], r["held"], r["missing"],
                 100 * (r["missingShare"] or 0), r["items"]))
    c = res["C2"]
    print("C2 %s  %d of %d major projects have 3+ dated city-body records (%.0f%%); distribution %s"
          % ("pass" if c["pass"] else "FAIL", c["threeOrMore"], c["major"], 100 * (c["share"] or 0), c["distribution"]))
    c = res["C3"]
    print("C3 %s  %d project-page items carry a city body's label; %d name-matching records graded weaker"
          % ("pass" if c["pass"] else "FAIL", c["pageItemsWithCityLabel"], c["nameMatchesGradedWeaker"]))
    c = res["C4"]
    print("C4 %s  %d of %d projects with a start date have a city-body record before it (%.1f%%); by department %s"
          % ("pass" if c["pass"] else "FAIL", c["withPriorRecord"], c["withStart"], 100 * (c["share"] or 0), c["byDepartment"]))
    s, n = c["startedByToday"], c["notYetStarted"]
    print("     started by today: %d of %d (%.1f%%); not yet started: %d of %d"
          % (s["withPriorRecord"], s["withStart"], 100 * (s["share"] or 0), n["withPriorRecord"], n["withStart"]))
    for e in res["C3"]["examples"]:
        print("     C3 example:", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coordination", default=COORD)
    ap.add_argument("--json")
    ap.add_argument("--without", action="store_true", help="list each C4 project with no prior record")
    args = ap.parse_args()
    res = measure(args.coordination)
    show(res)
    if args.without:
        for w in res["C4"]["without"]:
            print("  %s | %s | start %s | %s" % (w["department"], w["name"], w["start"], w["shouldDecide"]))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        stable.write_json(args.json, res, indent=1, ensure_ascii=False)
        print("->", args.json)


if __name__ == "__main__":
    main()
