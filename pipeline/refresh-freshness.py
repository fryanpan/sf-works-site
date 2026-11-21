#!/usr/bin/env python3
"""Fail when any scheduled pipeline step's last good check is older than its update interval allows.

    pipeline/refresh-freshness.py                 # check data/pipeline-state/sources.json against today
    pipeline/refresh-freshness.py --now 2026-11-20T14:00:00   # as if run then, to watch it fail

The interval is each step's in pipeline/transportation-update.py (interval_days: DEFAULT_INTERVAL_DAYS, INTERVAL_DAYS,
and MANUAL for the School Trips model builds the schedule leaves out). A step's age runs from the last time
transportation-update.py recorded it as run without failing ("step:<name>" changed or unchanged in sources.json; a
build skipped because its inputs were unchanged counts as checked through the run's "run:scheduled" entry). A source
marker whose refresh failed ages from its last good check, on the interval of the step that records it
(TU.source_interval_days: a weekly step's marker is weekly). Grace is one interval: a daily step fails on its second
missed day, so one late or missed run does not alert and two do.

It also reads the published files whose pages print a "Data updated" date (PUBLISHED), and fails when that date is
older than the page's interval allows, by the same one-interval grace, or when the newest period the file covers ends
longer ago than its source can lag. That catches a step that runs and passes while the data it publishes stops moving.

Exit 0 when every step is inside its interval, 1 naming each one that is not. pipeline/site-refresh/run.sh runs this
after every scheduled run; a failure stops the deploy and opens the alert issue.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib import pipeline_state  # noqa: E402

TU = paths.load("transportation-update.py")


def good_time(entry):
    """When this entry last recorded a check that did not fail, or None."""
    if not entry:
        return None
    t = entry.get("last_good") if entry.get("status") in ("failed", "skipped") else entry.get("checked")
    return dt.datetime.fromisoformat(t) if t else None


def stale(now, state):
    """(step or marker, interval days, age in days or None) for everything past its interval plus one interval of grace."""
    out = []
    run_ok = good_time(state.get("run:scheduled"))
    for name, kind, *_ in TU.STEPS:
        days = TU.interval_days(name)
        if days is None:
            continue
        entry = state.get("step:" + name) or {}
        t = good_time(entry)
        # A build skipped as unchanged records nothing of its own; the scheduled run that skipped it checked it. A
        # build whose last attempt failed (its virtualenv missing) ages from its last good run instead.
        if kind != "source" and run_ok and entry.get("status") != "failed" and (t is None or run_ok > t):
            t = run_ok
        age = None if t is None else (now - t).total_seconds() / 86400
        if age is None or age > 2 * days:
            out.append((name, days, age))
    for key, entry in sorted(state.items()):
        if key.startswith(("step:", "quality:", "run:")) or entry.get("status") != "failed":
            continue
        t = good_time(entry)
        age = None if t is None else (now - t).total_seconds() / 86400
        days = TU.source_interval_days(key, entry)
        if age is None or age > 2 * days:
            out.append((key, days, age))
    return out


def _month_end(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)


# (published file, interval in days, how to read its "Data updated" date, its newest covered period's last day, and
#  the longest that period may lag the run). The Muni dashboard (site/data/muni.json, tools/muni/muni-ewt/site_data.py):
#  "read" moves daily with the occupancy days from our archive; the excess wait, speed and on-time figures come from
#  511's monthly records, posted in the first days of the next month, so the newest month may end up to 40 days back
#  (the muni/newest-month check's bound).
#  Upgrade a Bus Line (site/data/muni-optimizer/<month>.json, the newest file; tools/muni/muni-ewt/optimizer_build.py):
#  its step runs daily, but its "Data updated" date is the older of the dates 511's newest month and SFMTA's crowding
#  file were read, and both move about monthly, so the date itself has no daily bound (interval None); the newest month
#  it covers may end up to 40 days back, as the dashboard's. Read only while its step is on the schedule: a sixth
#  field names the step, and a step in MANUAL is left out here as stale() leaves it out.
PUBLISHED = [
    ("site/data/muni.json", 1, lambda d: d.get("read"),
     lambda d: _month_end(d["windows"]["30"]["months"][1]), 40),
    ("site/data/muni-optimizer/", None, lambda d: d.get("dataUpdated"),
     lambda d: _month_end(d["month"]), 40, "muni-optimizer"),
]


def published_stale(now):
    """(file, what, interval or bound in days, age in days) for each published file past its interval or lag bound."""
    import json
    out = []
    root = paths.ROOT
    for rel, days, read_of, newest_of, lag, *step in PUBLISHED:
        if step and TU.interval_days(step[0]) is None:
            continue
        try:
            path = os.path.join(root, rel)
            if rel.endswith("/"):  # one file a month: the newest
                path = os.path.join(path, sorted(f for f in os.listdir(path) if f.endswith(".json"))[-1])
                rel = os.path.relpath(path, root)
            d = json.load(open(path))
            read = dt.date.fromisoformat(read_of(d))
            newest = newest_of(d)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
            out.append((rel, "unreadable: %s" % e, days, None))
            continue
        age = (now.date() - read).days
        if days is not None and age > 2 * days:
            out.append((rel, "data read %s" % read, days, age))
        lagged = (now.date() - newest).days
        if lagged > lag:
            out.append((rel, "newest period ends %s" % newest, lag, lagged))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="ISO time to check against, for testing")
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now()
    bad, pub = stale(now, pipeline_state.load()), published_stale(now)
    if not bad and not pub:
        print("freshness: every scheduled step was checked inside its interval, and every published date is current")
        return 0
    if bad:
        print("freshness FAILED: %d step(s) or source(s) past their update interval:" % len(bad))
    for name, days, age in bad:
        print("  %-30s interval %dd, last good check %s" % (name, days, "never" if age is None else "%.1f days ago" % age))
    if pub:
        print("freshness FAILED: %d published file(s) past their interval:" % len(pub))
    for rel, what, days, age in pub:
        print("  %-30s %s, %s days ago (allowed %d)" % (rel, what, "?" if age is None else age, 2 * days if what.startswith("data read") else days))
    return 1


if __name__ == "__main__":
    sys.exit(main())
