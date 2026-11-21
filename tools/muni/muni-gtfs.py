#!/usr/bin/env python3
"""Muni routes and weekday bell-hour arrivals near the ten case-study schools, from SFMTA's published GTFS feed.

    tools/muni/muni-gtfs.py              # rebuild site/data/muni-schools.json from disk; fetch once if absent
    tools/muni/muni-gtfs.py --update     # ask SFMTA whether the feed changed; re-read it only if it did
    tools/muni/muni-gtfs.py --refresh    # re-read the feed whatever its markers say
    tools/muni/muni-gtfs.py --check      # run the quality checks on the feed and the output on disk
    tools/muni/muni-gtfs.py --selftest   # prove the checks fail on a broken feed and the bad copy is refused
    scripts/muni-gtfs-test.py         # the per-day service check on the 2026-08-19 and 2026-11-13 copies' counts

THE SOURCE. SFMTA's "GTFS Transit Data" page (https://www.sfmta.com/reports/gtfs-transit-data,
read 2026-10-07) links one file, FEED_URL, scheduled service only, no API key.
Use is under the SFMTA Transit Data License Agreement printed on that page and
shipped in the zip: it allows use, reproduction and redistribution, requires
every derivative to "bear the following notice" (term 12), and bars SFMTA and
Muni logos (term 7). The output carries the term 12 notice word for word, read
out of the zip's own licence file, and no logos or route colours.

INCREMENTAL. The file is served from GitHub Pages with Last-Modified and an
ETag. --update sends one HEAD request and re-reads the zip only when either
differs from the copy held in .cache/muni-gtfs/ (gitignored); a re-read whose
bytes hash the same as the held copy is recorded as unchanged. The feed has no
feed_info.txt, so the HTTP markers and the zip's SHA-256 are the version.
A failed re-read, or a new zip that fails its checks, keeps the held copy and
records the failure under gtfs:sfmta-muni in data/pipeline-state/sources.json.

CHECKS (pipeline/README.md, rule 2), run on every new zip before
it replaces the held one and again by pipeline/transportation-update.py after
the step: row floors for every core file, and the fall or rise against the
previous copy for all but trips.txt, stop_times.txt and the two calendar
files; service per day (next paragraph); required fields; unique keys (route_id, trip_id, stop_id, service_id,
(trip_id, stop_sequence), (shape_id, shape_pt_sequence), (service_id, date));
calendar dates in range; arrival times well formed; every stop inside San
Francisco's bounding box; and joins: every stop_time's trip and stop exist,
every trip's route, service and shape exist, every trip has stop times. On the
output: one row per shortlisted school, each with a bell source, and every
arrival inside its window. stop_times.txt (about 1.9 million rows) is streamed
once per copy, not held in memory.

SERVICE PER DAY. A feed's total trips depend on how many service periods it
carries, not on how much service runs: the 2026-08-19 copy held six services
(M11 and M21 on weekdays, M12 and 2 on Saturdays, M13 and 3 on Sundays) and
the 2026-11-13 copy holds four (no M12 or M13), so trips.txt fell 32% (50,690
to 34,668), stop_times.txt 32% and calendar_dates.txt 38% with a weekday's
trips going from 9,456 to 9,482 and a Saturday's or Sunday's from 7,859 to
7,861. So trips and stop times are compared per day, and the two calendar
files, which that comparison reads, keep only their floors. Every date from the calendar's first to its last
is resolved to the services running then (calendar.txt, then
calendar_dates.txt's additions and removals), and each of weekday (Monday to
Friday), Saturday and Sunday is represented by its median date by trips (the
lower of two middle ones), so the holidays inside a period don't set it. That
date's trips and stop times must clear DAY_FLOORS and must sit within
DAY_MAX_CHANGE (15%) of the previous copy's for the same day type, either
way; --accept-growth lifts the upper side for one refresh. The bound is
tighter than a file's row bound because a day's service moves a few percent
between signups (0.3% between these two copies), and wide enough for a
signup's ordinary changes. A cut that reaches fewer than half of a day type's
dates does not move its median and passes.

THE TEN SCHOOLS. The school case study plan's two lists, recomputed here from
out/school-priority/: the first five of the shortlist in
out/school-priority/summary.json (most bell-hour injury crashes within 600 ft,
ties by how unlikely the count is), and the five schools in
out/school-priority/schools.csv with the most children over 15 minutes away
today. Bell times come from out/school-hour-crashes/schools.json. A school
with a record in data/school-case/dropoff.json is placed at that record's door,
the point the case study page measures every walk from; any other school at
its point in out/school-hour-crashes/schools.json. (Proof School's repo point
is its old Mission St address, 5,616 ft from the door.) An output check fails
when a school sits more than DOOR_MAX_FT from its door.

STALENESS. The feed carries its own end date. When the latest end date in
calendar.txt and calendar_dates.txt is more than STALE_DAYS before today, the
run records gtfs:sfmta-muni as "stale" in data/pipeline-state/sources.json
(the audit's F3 lists it), and the output's feed.stale says so, so a page can
print that the schedule has expired. It doesn't fail the step: the source has
nothing newer, and the held copy is all there is. Whether 511's regional feed
should stand in when SFMTA's file stops updating is open; it needs an API key
and is not read here.

BELL TIMES. One source for the whole case study: the start and dismissal
read from each school's own website in data/school-case/dropoff.json
(bellSource "school"), with its Wednesday early release. A school with no
dropoff.json bell falls back to SFUSD's published 2025-26 start and end
times where it is on SFUSD's page (bellSource "sfusd"), and otherwise to the
placeholder 8:00 AM and 3:00 PM (bellSource "placeholder"), which is not its
bell. A missing start or dismissal in dropoff.json takes the placeholder for
that bell alone, and the school is then marked placeholder.

WHAT IS COUNTED. A stop is near a school when it lies within a quarter mile
(1,320 ft) in a straight line; walking distance is not used. A route is listed
when a trip on the service day stops at one of those stops. The service day is
data-only, so a rerun on a later date gives the same file: the last Wednesday
inside the feed's calendar, with the services calendar.txt and
calendar_dates.txt say run then. Each trip is counted once per window, at the
near stop closest to the school, and kept when that arrival falls between 45
minutes before the earliest bell and 45 minutes after the latest. Times are
truncated to the minute. Route shapes are the most-used shape per route and
direction among those trips, simplified to SIMPLIFY_FT and rounded to five
decimals.

Writes site/data/muni-schools.json. Exit codes: 0 done or current, including
a failed re-read whose held copy was used (recorded as failed in sources.json,
which pipeline/transportation-update.py reports under REFRESH FAILED); 1 the
held copy or the output fails its checks.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state  # noqa: E402
from lib.quality import Each, Join, Result, Table, read_json, run  # noqa: E402
from lib.stable import write_json  # noqa: E402

FEED_URL = "https://muni-gtfs.apps.sfmta.com/data/muni_gtfs-current.zip"
FEED_PAGE = "https://www.sfmta.com/reports/gtfs-transit-data"
MARKER = "gtfs:sfmta-muni"
CACHE_REL = ".cache/muni-gtfs"
ZIP_NAME = "muni_gtfs-current.zip"
META_NAME = "meta.json"
OUT_REL = "site/data/muni-schools.json"
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"

QUARTER_MILE_FT = 1320
WINDOW_MIN = 45
SIMPLIFY_FT = 30
PLACEHOLDER = {"start": 8 * 60, "end": 15 * 60}
FT_PER_DEG_LAT = 364_000.0  # 69.0 miles
BBOX = (-123.2, 37.6, -122.3, 37.9)  # San Francisco, with the islands
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ---- the feed on disk ---------------------------------------------------------

def zip_path(root=ROOT):
    return os.path.join(root, CACHE_REL, ZIP_NAME)


def meta_path(root=ROOT):
    return os.path.join(root, CACHE_REL, META_NAME)


def rows(zf, name):
    """DictReader over one GTFS file in an open zip; values stripped."""
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        for r in csv.DictReader(text):
            yield {k.strip(): (v or "").strip() for k, v in r.items() if k}


def gtfs_date(s):
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if re.fullmatch(r"\d{8}", s or "") else ("invalid:" + (s or ""))


def minutes(t):
    """GTFS HH:MM:SS (hours may pass 24) -> minutes after midnight, truncated, or None."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", t or "")
    if not m or int(m.group(2)) > 59 or int(m.group(3)) > 59 or int(m.group(1)) > 47:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def hhmm(m):
    return "%02d:%02d" % (m // 60, m % 60)


# ---- quality checks -------------------------------------------------------------

# Per file: floor, largest fall and rise against the previous copy, required
# fields (a (field, share) pair allows that share empty), unique key, date fields.
# Floors sit under the 2026-11-13 copy's counts (routes 68, trips 34,668,
# stops 3,240, stop_times 1,302,039, shapes 45,014), so they catch an emptied
# file; a shrink is the max_drop bound. Schedules change between signups, so
# the bound is wide. per_day marks the four files whose row count follows the
# number of service periods the feed carries and the holidays inside them:
# they keep the floor and are compared with the previous copy per service day
# instead (ServiceDays).
RULES = {
    "agency.txt": dict(floor=1, key=("agency_id",), required=["agency_name", "agency_timezone"]),
    "routes.txt": dict(floor=50, key=("route_id",), required=["route_id", "route_short_name", "route_type"]),
    "trips.txt": dict(floor=20000, key=("trip_id",), required=["trip_id", "route_id", "service_id", "direction_id",
                                                              ("shape_id", 0.01)], per_day=True),
    "stops.txt": dict(floor=2500, key=("stop_id",), required=["stop_id", "stop_name", "stop_lat", "stop_lon"]),
    "stop_times.txt": dict(floor=1_000_000, key=("trip_id", "stop_sequence"),
                           required=["trip_id", "stop_id", "stop_sequence", "arrival_time"], per_day=True),
    "calendar.txt": dict(floor=1, key=("service_id",), required=["service_id", "start_date", "end_date"],
                         dates={"start_date": ("2020-01-01", "+400"), "end_date": ("2020-01-01", "+1500")}, per_day=True),
    "calendar_dates.txt": dict(floor=0, key=("service_id", "date"), required=["service_id", "date", "exception_type"],
                               dates={"date": ("2020-01-01", "+1500")}, per_day=True),
    "shapes.txt": dict(floor=20000, key=("shape_id", "shape_pt_sequence"),
                       required=["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]),
}
MAX_DROP, MAX_GROWTH = 0.30, 1.0
# --accept-growth lifts the growth bound for one refresh, on the files compared
# by rows and on the per-day counts.
ACCEPT_GROWTH = {"on": False}
STALE_DAYS = 14
DOOR_MAX_FT = 500
# The day types service is compared on, and the fewest trips and stop times the
# representative date of each may hold. The floors sit under the 2026-11-13
# copy's (weekday 9,482 trips and 350,724 stop times; Saturday and Sunday 7,861
# and 300,583).
DAY_TYPES = ("weekday", "saturday", "sunday")
DAY_FLOORS = {"trips": 4000, "stop_times": 150_000}
# The largest fall or rise in a day's trips or stop times against the previous
# copy. Between the 2026-08-19 and 2026-11-13 copies a day moved 0.3% or less.
DAY_MAX_CHANGE = 0.15
# Columns whose distinct values the joins need.
DISTINCT = {"stop_times.txt": ("trip_id", "stop_id"), "trips.txt": ("route_id", "service_id", "shape_id", "trip_id"),
            "routes.txt": ("route_id",), "stops.txt": ("stop_id",), "calendar.txt": ("service_id",),
            "calendar_dates.txt": ("service_id",), "shapes.txt": ("shape_id",)}

_SCANS = {}


def scan(path):
    """One pass over every core file of the zip at `path`: counts, empty required
    fields, repeated keys, dates out of range, malformed times, stops outside the
    bounding box, and the distinct values the joins read. Memoised on the file's
    size and modification time, so the checks read stop_times.txt once per copy."""
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    memo = (path, st.st_size, st.st_mtime_ns)
    if memo in _SCANS:
        return _SCANS[memo]
    out = {}
    trip_service = {}
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for name, rule in RULES.items():
            if name not in names:
                out[name] = None
                continue
            req = [(r if isinstance(r, tuple) else (r, 0.0)) for r in rule.get("required", [])]
            s = {"rows": 0, "empty": collections.Counter(), "dups": 0, "dup_sample": [],
                 "dates": {f: [] for f in rule.get("dates", {})}, "bad_times": [], "outside": [],
                 "distinct": {c: set() for c in DISTINCT.get(name, ())}}
            seen = set()
            big = name == "stop_times.txt"
            if name in ("trips.txt", "stop_times.txt"):
                s["by_service"] = collections.Counter()
            if name in ("calendar.txt", "calendar_dates.txt"):
                s["records"] = []
            for r in rows(zf, name):
                s["rows"] += 1
                if name == "trips.txt":
                    trip_service[r.get("trip_id")] = r.get("service_id")
                    s["by_service"][r.get("service_id")] += 1
                elif big:
                    s["by_service"][trip_service.get(r.get("trip_id"))] += 1
                elif "records" in s:
                    s["records"].append(r)
                for f, _ in req:
                    if not r.get(f):
                        s["empty"][f] += 1
                k = tuple(r.get(c, "") for c in rule["key"])
                h = hash(k) if big else k
                if h in seen:
                    s["dups"] += 1
                    if len(s["dup_sample"]) < 4:
                        s["dup_sample"].append("|".join(k))
                else:
                    seen.add(h)
                for f in s["dates"]:
                    if r.get(f):
                        s["dates"][f].append(gtfs_date(r[f]))
                for c in s["distinct"]:
                    if r.get(c):
                        s["distinct"][c].add(r[c])
                if big:
                    for f in ("arrival_time", "departure_time"):
                        if r.get(f) and minutes(r[f]) is None and len(s["bad_times"]) < 50:
                            s["bad_times"].append("%s %s=%s" % (r.get("trip_id"), f, r[f]))
                if name == "stops.txt":
                    try:
                        x, y = float(r["stop_lon"]), float(r["stop_lat"])
                        if not (BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]):
                            s["outside"].append(r["stop_id"])
                    except (KeyError, ValueError):
                        s["outside"].append(r.get("stop_id") or "?")
            out[name] = s
    if out.get("calendar.txt") and out.get("trips.txt") and out.get("stop_times.txt"):
        out["service-days"] = service_days(out["calendar.txt"]["records"],
                                           (out.get("calendar_dates.txt") or {}).get("records") or [],
                                           out["trips.txt"]["by_service"], out["stop_times.txt"]["by_service"])
    _SCANS[memo] = out
    return out


def service_days(cal, exc, trips_by_service, stop_times_by_service):
    """{day type: {"date", "trips", "stop_times", "days"}} for weekday, Saturday and Sunday.

    Every date from the calendar's first to its last is resolved to the
    services running then: calendar.txt's rows in range with that weekday set,
    then calendar_dates.txt's additions (1) and removals (2). Each day type is
    represented by its median date by trips (the lower of two middle ones),
    with that date's trips and stop times; "days" is
    how many dates of the type the calendar holds. A date outside every
    calendar.txt row and named only in calendar_dates.txt still counts."""
    add, drop = collections.defaultdict(set), collections.defaultdict(set)
    for e in exc:
        (add if e.get("exception_type") == "1" else drop)[e.get("date")].add(e.get("service_id"))
    ymds = [c.get(f) for c in cal for f in ("start_date", "end_date")] + list(add) + list(drop)
    ymds = [d for d in ymds if re.fullmatch(r"\d{8}", d or "")]
    out = {t: None for t in DAY_TYPES}
    if not ymds:
        return out
    day, last = (dt.datetime.strptime(d, "%Y%m%d").date() for d in (min(ymds), max(ymds)))
    by_type = collections.defaultdict(list)
    while day <= last:
        ymd, col = day.strftime("%Y%m%d"), WEEKDAYS[day.weekday()]
        on = {c.get("service_id") for c in cal
              if c.get("start_date", "") <= ymd <= c.get("end_date", "") and c.get(col) == "1"}
        on = (on | add[ymd]) - drop[ymd]
        kind = col if col in ("saturday", "sunday") else "weekday"
        by_type[kind].append((sum(trips_by_service.get(s, 0) for s in on), ymd,
                              sum(stop_times_by_service.get(s, 0) for s in on)))
        day += dt.timedelta(days=1)
    for kind, days in by_type.items():
        days.sort()
        trips, ymd, stop_times = days[(len(days) - 1) // 2]
        out[kind] = {"date": gtfs_date(ymd), "trips": trips, "stop_times": stop_times, "days": len(days)}
    return out


class ServiceDays(object):
    """Trips and stop times on a representative weekday, Saturday and Sunday, against a floor and the previous copy.

    Stands in for the row-count comparison on trips.txt and stop_times.txt,
    whose totals follow how many service periods the feed carries. Results are
    named muni-gtfs/service-days.<trips|stop_times>[<day type>]."""

    name = "muni-gtfs/service-days"

    def __init__(self, path_of):
        self.path_of = path_of

    def load(self, root):
        sc = scan(self.path_of(root))
        return None if sc is None else sc.get("service-days")

    def check(self, s, prev, today):
        if s is None:
            # No feed on disk, or one without a calendar, trips or stop times:
            # FeedTable reports either under the file's own name.
            return []
        out = []
        for kind in DAY_TYPES:
            for what, floor in DAY_FLOORS.items():
                name = "%s.%s[%s]" % (self.name, what, kind)
                d = s.get(kind)
                if d is None:
                    out.append(Result(name, False, "the calendar holds no %s" % kind))
                    continue
                cnt = d[what]
                ok = cnt >= floor
                detail = "%d on %s (median of %d), floor %d" % (cnt, d["date"], d["days"], floor)
                p = (prev or {}).get(kind) if isinstance(prev, dict) else None
                if p:
                    detail += ", previously %d on %s" % (p[what], p["date"])
                    if cnt < p[what] * (1 - DAY_MAX_CHANGE):
                        ok, detail = False, detail + " (fell more than %d%%)" % round(100 * DAY_MAX_CHANGE)
                    if cnt > p[what] * (1 + DAY_MAX_CHANGE) and not ACCEPT_GROWTH["on"]:
                        ok, detail = False, detail + " (grew more than %d%%)" % round(100 * DAY_MAX_CHANGE)
                out.append(Result(name, ok, detail))
        return out


class FeedTable(object):
    """lib.quality's Table checks for one GTFS file, computed by scan() in one
    streamed pass instead of from a list of row dicts. Results are named as
    Table names them: <name>.rows, .required[f], .unique[k], .dates[f]."""

    def __init__(self, name, path_of):
        self.name, self.path_of, self.rule = "muni-gtfs/" + name, path_of, RULES[name]
        self.file = name

    def load(self, root):
        sc = scan(self.path_of(root))
        return None if sc is None else (sc.get(self.file) or "missing")

    def check(self, s, prev, today):
        n = self.name
        if s is None:
            # .cache/muni-gtfs is gitignored, so a fresh checkout has no feed
            # until the first fetch; that is "not fetched yet", not a broken
            # feed. The output checks below still run on muni-schools.json.
            return [Result(n + ".present", True, "no feed on disk yet (not fetched); run tools/muni/muni-gtfs.py")]
        if s == "missing":
            return [Result(n + ".present", False, "%s is not in the zip" % self.file)]
        cnt, floor = s["rows"], self.rule["floor"]
        ok = cnt >= floor
        detail = "%d rows, floor %d" % (cnt, floor)
        if isinstance(prev, dict) and self.rule.get("per_day"):
            detail += ", previously %d (compared per service day)" % prev["rows"]
        elif isinstance(prev, dict):
            p = prev["rows"]
            detail += ", previously %d" % p
            if cnt < p * (1 - MAX_DROP):
                ok, detail = False, detail + " (fell more than %d%%)" % round(100 * MAX_DROP)
            if p and cnt > p * (1 + MAX_GROWTH) + 5 and not ACCEPT_GROWTH["on"]:
                ok, detail = False, detail + " (grew more than %d%%)" % round(100 * MAX_GROWTH)
        out = [Result(n + ".rows", ok, detail)]
        for spec in self.rule.get("required", []):
            f, share = spec if isinstance(spec, tuple) else (spec, 0.0)
            bad, allowed = s["empty"][f], int(share * cnt)
            out.append(Result("%s.required[%s]" % (n, f), bad <= allowed, "%d of %d rows lack it%s" % (
                bad, cnt, (", %d allowed" % allowed) if allowed else "")))
        key = "+".join(self.rule["key"])
        out.append(Result("%s.unique[%s]" % (n, key), not s["dups"], "%d repeated%s" % (
            s["dups"], (": " + ", ".join(s["dup_sample"])) if s["dups"] else "")))
        for f, (lo, hi) in self.rule.get("dates", {}).items():
            lo_, hi_ = (_bound(lo, today), _bound(hi, today))
            bad = sorted(d for d in s["dates"][f] if d.startswith("invalid:") or d < lo_ or d > hi_)
            out.append(Result("%s.dates[%s]" % (n, f), not bad, "%s..%s; %d out of range%s" % (
                lo_, hi_, len(bad), (": " + ", ".join(bad[:4])) if bad else "")))
        if self.file == "stop_times.txt":
            out.append(Result(n + ".times", not s["bad_times"], "%d malformed arrival or departure times%s" % (
                len(s["bad_times"]), (": " + ", ".join(s["bad_times"][:4])) if s["bad_times"] else "")))
        if self.file == "stops.txt":
            out.append(Result(n + ".in-sf", not s["outside"], "%d stops outside San Francisco's bounding box%s" % (
                len(s["outside"]), (": " + ", ".join(s["outside"][:4])) if s["outside"] else "")))
        return out


def _bound(b, today):
    if isinstance(b, str) and b[:1] in "+-" and b[1:].isdigit():
        return (today + dt.timedelta(days=int(b))).isoformat()
    return b


def _distinct(path_of, name, col):
    def get(root):
        sc = scan(path_of(root))
        return None if sc is None or not sc.get(name) else sorted(sc[name]["distinct"][col])
    return get


def _services(path_of):
    def get(root):
        sc = scan(path_of(root))
        if sc is None or not sc.get("calendar.txt"):
            return None
        both = sc["calendar.txt"]["distinct"]["service_id"]
        if sc.get("calendar_dates.txt"):
            both = both | sc["calendar_dates.txt"]["distinct"]["service_id"]
        return sorted(both)
    return get


def feed_checks(root=ROOT, path_of=zip_path):
    """The checks on a feed zip: every core file, service per day, then the joins between them."""
    out = [FeedTable(name, path_of) for name in RULES] + [ServiceDays(path_of)]
    d = lambda name, col: _distinct(path_of, name, col)  # noqa: E731
    out += [
        # Every stop_time's trip exists, and every trip has stop times.
        Join("muni-gtfs stop_times.trip_id~trips", left=d("stop_times.txt", "trip_id"), right=d("trips.txt", "trip_id")),
        # Every stop_time's stop exists; stops with no service (retired or
        # seasonal) are allowed.
        Join("muni-gtfs stop_times.stop_id~stops", left=d("stop_times.txt", "stop_id"), right=d("stops.txt", "stop_id"),
             extra_ok=True),
        Join("muni-gtfs trips.route_id~routes", left=d("trips.txt", "route_id"), right=d("routes.txt", "route_id"),
             extra_ok=True),
        Join("muni-gtfs trips.service_id~calendar", left=d("trips.txt", "service_id"), right=_services(path_of),
             extra_ok=True),
        Join("muni-gtfs trips.shape_id~shapes", left=d("trips.txt", "shape_id"), right=d("shapes.txt", "shape_id"),
             extra_ok=True),
    ]
    return out


def output_checks(root=ROOT):
    """The checks on site/data/muni-schools.json: one row per shortlisted school, arrivals inside their windows."""
    def schools(r):
        d = read_json(r, OUT_REL)
        return None if d is None else d["schools"]

    def picked(r):
        try:
            return [s["name"] for s in pick_schools(r)]
        except FileNotFoundError:
            return None

    def in_window(s):
        bad = []
        for w in s["windows"]:
            lo, hi = w["from"], w["to"]
            bad += ["%s %s %s" % (s["name"], w["name"], t) for dd in w["arrivals"].values() for by in dd.values()
                    for ts in by.values() for t in ts if not lo <= t <= hi]
        return "; ".join(bad[:3]) or None

    def meta(r):
        d = read_json(r, OUT_REL)
        return None if d is None else [{"notice": d.get("notice"), "serviceDate": d["feed"].get("serviceDate"),
                                        "routes": len(d.get("routes") or {})}]
    def at_door(s):
        door = DOORS.get(s["name"])
        if door is None:
            return None
        f = feet(s["lon"], s["lat"], door[0], door[1])
        return None if f <= DOOR_MAX_FT else "%s sits %d ft from its dropoff.json door" % (s["name"], f)

    return [
        Each("muni-schools/at-door", schools, at_door, "each case-study school sits within %d ft of its door" % DOOR_MAX_FT),
        Table("muni-schools", schools, floor=10, max_drop=0.0, key="name",
              required=["name", "lat", "lon", "bellSource", "windows"]),
        Join("muni-schools schools~school-priority", left=picked,
             right=lambda r: None if schools(r) is None else [s["name"] for s in schools(r)]),
        Each("muni-schools/arrivals-in-window", schools, in_window, "every arrival lies inside its window"),
        Each("muni-schools/bell-source", schools,
             lambda s: None if s["bellSource"] in ("school", "sfusd", "placeholder") else "%s: %r" % (s["name"], s["bellSource"]),
             "every school's bell is its own, SFUSD's or the flagged placeholder"),
        Table("muni-schools/feed", meta, floor=1, max_drop=None, required=["notice", "serviceDate", "routes"],
              dates={"serviceDate": ("2020-01-01", "+1500")}),
    ]


def checks(root=ROOT):
    """Every check, for scripts/transportation-quality.py."""
    return feed_checks(root) + output_checks(root)


def failures(results):
    return [r for r in results if not r.ok]


# ---- fetch ----------------------------------------------------------------------

def read_meta(root=ROOT):
    try:
        with open(meta_path(root), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return None


def head():
    req = urllib.request.Request(FEED_URL, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return {"etag": r.headers.get("ETag"), "lastModified": r.headers.get("Last-Modified"),
                "bytes": int(r.headers.get("Content-Length") or 0)}


def download(dest):
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": UA})
    h = hashlib.sha256()
    n = 0
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as fh:
        hdr = {"etag": r.headers.get("ETag"), "lastModified": r.headers.get("Last-Modified")}
        want = int(r.headers.get("Content-Length") or 0)
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            h.update(b)
            fh.write(b)
            n += len(b)
    if want and n != want:
        raise IOError("short read: %d of %d bytes" % (n, want))
    hdr.update(sha256=h.hexdigest(), bytes=n)
    return hdr


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def adopt(new_zip, hdr, root=ROOT):
    """Check `new_zip` against the held copy; move it into place only if every
    check passes. Returns the failing results (empty when adopted)."""
    held = zip_path(root)
    res = run(feed_checks(root, path_of=lambda r: new_zip if r == "<new>" else zip_path(r)), "<new>",
              prev_root=root if os.path.exists(held) else None)
    bad = failures(res)
    if bad:
        return bad
    os.makedirs(os.path.dirname(held), exist_ok=True)
    os.replace(new_zip, held)
    meta = dict(hdr, url=FEED_URL, fetched_on=dt.date.today().isoformat())
    with open(meta_path(root), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)
    return []


def refresh(force, root=ROOT):
    """Ask the source; re-read only what moved. Returns 'unchanged', 'changed' or raises."""
    have = read_meta(root)
    held = os.path.exists(zip_path(root))
    if held and have and not force:
        h = head()
        if h["etag"] == have.get("etag") and h["lastModified"] == have.get("lastModified"):
            print("  muni-gtfs unchanged (Last-Modified %s, ETag %s)" % (h["lastModified"], h["etag"]))
            return "unchanged", have
    os.makedirs(os.path.join(root, CACHE_REL), exist_ok=True)
    tmp = os.path.join(root, CACHE_REL, "incoming.zip")
    try:
        hdr = download(tmp)
        if held and have and hdr["sha256"] == have.get("sha256"):
            os.remove(tmp)
            meta = dict(have, etag=hdr["etag"], lastModified=hdr["lastModified"])
            with open(meta_path(root), "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=1, sort_keys=True)
            print("  muni-gtfs markers moved but the bytes are the same; held copy kept")
            return "unchanged", meta
        bad = adopt(tmp, hdr, root)
        if bad:
            raise ValueError("new copy fails %d checks: %s" % (len(bad), "; ".join(map(repr, bad[:3]))))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("  muni-gtfs re-read: %d bytes, Last-Modified %s" % (hdr["bytes"], hdr["lastModified"]))
    return "changed", read_meta(root)


# ---- the ten schools --------------------------------------------------------------

def _doors(root=ROOT):
    """repo_name -> (lon, lat) of each school's door in data/school-case/dropoff.json."""
    try:
        d = json.load(open(os.path.join(root, "data", "school-case", "dropoff.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {s["repo_name"]: (s["door"]["lon"], s["door"]["lat"]) for s in d["schools"] if s.get("door")}


def _bells(root=ROOT):
    """repo_name -> the bell record in data/school-case/dropoff.json, read from the school's own site."""
    try:
        d = json.load(open(os.path.join(root, "data", "school-case", "dropoff.json"), encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {s["repo_name"]: s.get("bell") or {} for s in d["schools"]}


DOORS = _doors()


def pick_schools(root=ROOT):
    """The plan's two lists of five: most bell-hour injury crashes, most children over 15 minutes."""
    summary = json.load(open(os.path.join(root, "out", "school-priority", "summary.json"), encoding="utf-8"))
    with open(os.path.join(root, "out", "school-priority", "schools.csv"), newline="", encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    injury = [s["campus"] for s in summary["shortlist"][:5]]
    far = [r["school"] for r in sorted(table, key=lambda r: (-int(r["children_over_15_min_today"] or 0), r["school"]))[:5]]
    loc = {s["name"]: s for s in json.load(open(os.path.join(root, "out", "school-hour-crashes", "schools.json"),
                                                encoding="utf-8"))}
    priv = {r["school"]: r["private"] == "True" for r in table}
    doors = _doors(root)
    bells = _bells(root)
    out = []
    for name, why in [(n, "injury") for n in injury] + [(n, "unconnected") for n in far]:
        if name in [o["name"] for o in out]:
            next(o for o in out if o["name"] == name)["lists"].append(why)
            continue
        s = loc[name]  # a KeyError here is a renamed campus: fail loudly
        door = doors.get(name)
        lon, lat = door if door else (s["lon"], s["lat"])
        out.append({"name": name, "lat": lat, "lon": lon, "point": "door" if door else "repo", "private": priv.get(name),
                    "bell": s.get("bell") or {}, "bell_source": s.get("bell_source"), "school_bell": bells.get(name),
                    "lists": [why]})
    return out


def bell_windows(s):
    """[(window name, from, to, bell text)] and the bell source, from SFUSD's latest year or the placeholder."""
    years = sorted(s["bell"])
    sb = s.get("school_bell") or {}
    mins = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])  # noqa: E731
    if sb.get("start") or sb.get("dismissal"):
        st0 = st1 = mins(sb["start"]) if sb.get("start") else PLACEHOLDER["start"]
        en0 = en1 = mins(sb["dismissal"]) if sb.get("dismissal") else PLACEHOLDER["end"]
        src = "school" if sb.get("start") and sb.get("dismissal") else "placeholder"
        year = None
        early = {2: [mins(sb["wednesday_dismissal"])]} if sb.get("wednesday_dismissal") else {}
    elif s["bell_source"] == "sfusd" and years:
        b = s["bell"][years[-1]]
        st0, st1, en0, en1 = b["start_min"], b["start_max"], b["end_min"], b["end_max"]
        src, year = "sfusd", years[-1]
        early = collections.defaultdict(list)
        for wd, t in b.get("early") or []:
            early[wd].append(t)
    else:
        st0 = st1 = PLACEHOLDER["start"]
        en0 = en1 = PLACEHOLDER["end"]
        src, year, early = "placeholder", None, {}

    def span(a, b_):
        return hhmm(a) if a == b_ else "%s-%s" % (hhmm(a), hhmm(b_))
    w = [("start", st0 - WINDOW_MIN, st1 + WINDOW_MIN, span(st0, st1)),
         ("end", en0 - WINDOW_MIN, en1 + WINDOW_MIN, span(en0, en1))]
    for wd in sorted(early):
        t0, t1 = min(early[wd]), max(early[wd])
        w.append(("early-release " + WEEKDAYS[wd].capitalize(), t0 - WINDOW_MIN, t1 + WINDOW_MIN, span(t0, t1)))
    return w, src, year


# ---- build ----------------------------------------------------------------------------

def feet(lon0, lat0, lon1, lat1):
    k = math.cos(math.radians((lat0 + lat1) / 2))
    return math.hypot((lon1 - lon0) * FT_PER_DEG_LAT * k, (lat1 - lat0) * FT_PER_DEG_LAT)


def route_name(x):
    """SFMTA's long name in title case with ordinals and BART kept: "19TH AVENUE" → "19th Avenue", "BART EARLY BIRD" → "BART Early Bird"."""
    t = x.title()
    t = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)
    return re.sub(r"\bBart\b", "BART", t)


def simplify(pts, tol_ft):
    """Douglas-Peucker on [lon, lat] points, in feet."""
    if len(pts) < 3:
        return pts
    k = math.cos(math.radians(pts[0][1]))
    xy = [(p[0] * FT_PER_DEG_LAT * k, p[1] * FT_PER_DEG_LAT) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x0, y0), (x1, y1) = xy[a], xy[b]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = xy[i]
            d = abs(dy * (x - x0) - dx * (y - y0)) / L if L else math.hypot(x - x0, y - y0)
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol_ft:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k_ in zip(pts, keep) if k_]


def service_day(zf):
    """The last Wednesday inside the feed's calendar, and the services running then."""
    cal = list(rows(zf, "calendar.txt"))
    exc = list(rows(zf, "calendar_dates.txt")) if "calendar_dates.txt" in zf.namelist() else []
    dates = [gtfs_date(c["start_date"]) for c in cal] + [gtfs_date(c["end_date"]) for c in cal] + \
            [gtfs_date(e["date"]) for e in exc]
    last = dt.date.fromisoformat(max(dates))
    first = dt.date.fromisoformat(min(dates))
    day = last - dt.timedelta(days=(last.weekday() - 2) % 7)
    if day < first:
        raise ValueError("the feed's calendar holds no Wednesday")
    ymd = day.strftime("%Y%m%d")
    on = {c["service_id"] for c in cal if c["start_date"] <= ymd <= c["end_date"] and c["wednesday"] == "1"}
    for e in exc:
        if e["date"] == ymd:
            (on.add if e["exception_type"] == "1" else on.discard)(e["service_id"])
    return day, sorted(on), first, last


def licence_notice(zf):
    name = next((n for n in zf.namelist() if "license" in n.lower()), None)
    if not name:
        raise ValueError("no licence file in the zip")
    text = zf.read(name).decode("utf-8", "replace").replace("\r", "")
    m = re.search(r"following notice:\s*(.*?)\n\s*13\.", text, re.S)
    if not m:
        raise ValueError("term 12's notice not found in %s" % name)
    return re.sub(r"\s+", " ", m.group(1)).strip()


def build(root=ROOT, meta=None):
    meta = meta or read_meta(root) or {}
    schools = pick_schools(root)
    with zipfile.ZipFile(zip_path(root)) as zf:
        day, services, first, last = service_day(zf)
        notice = licence_notice(zf)
        stops = {s["stop_id"]: s for s in rows(zf, "stops.txt")}
        routes = {r["route_id"]: r for r in rows(zf, "routes.txt")}
        dirs = collections.defaultdict(dict)
        if "directions.txt" in zf.namelist():
            for d in rows(zf, "directions.txt"):
                dirs[d["route_id"]][d["direction_id"]] = d["direction"]
        trips = {t["trip_id"]: t for t in rows(zf, "trips.txt") if t["service_id"] in services}

        near = {}  # stop_id -> {school index: feet}
        for sid, s in stops.items():
            lon, lat = float(s["stop_lon"]), float(s["stop_lat"])
            for i, sc in enumerate(schools):
                f = feet(sc["lon"], sc["lat"], lon, lat)
                if f <= QUARTER_MILE_FT:
                    near.setdefault(sid, {})[i] = f
        # Per school and trip: the near stop closest to the school, and its arrival.
        best = [dict() for _ in schools]
        stop_routes = collections.defaultdict(set)
        for st in rows(zf, "stop_times.txt"):
            sid, tid = st["stop_id"], st["trip_id"]
            if sid not in near or tid not in trips:
                continue
            stop_routes[sid].add(trips[tid]["route_id"])
            m = minutes(st["arrival_time"] or st["departure_time"])
            for i, f in near[sid].items():
                cur = best[i].get(tid)
                if cur is None or f < cur[0] or (f == cur[0] and m < cur[2]):
                    best[i][tid] = (f, sid, m)
        shape_use = collections.Counter()
        for b in best:
            for tid in b:
                t = trips[tid]
                shape_use[(t["route_id"], t["direction_id"], t["shape_id"])] += 1
        want_shapes = {}
        for (rid, did, shp), n in sorted(shape_use.items(), key=lambda kv: (-kv[1], kv[0])):
            want_shapes.setdefault((rid, did), shp)
        pts = collections.defaultdict(list)
        need = set(want_shapes.values())
        for p in rows(zf, "shapes.txt"):
            if p["shape_id"] in need:
                pts[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"])))

    out_routes = {}
    for (rid, did), shp in sorted(want_shapes.items()):
        r = routes[rid]
        line = [[round(x, 5), round(y, 5)] for _, x, y in sorted(pts[shp])]
        e = out_routes.setdefault(rid, {"short": r.get("route_short_name") or rid, "long": route_name(r.get("route_long_name", "")),
                                        "type": int(r["route_type"]), "directions": {}})
        e["directions"][did] = {"name": dirs[rid].get(did, did), "shape": simplify(line, SIMPLIFY_FT)}

    out_schools = []
    for i, sc in enumerate(schools):
        windows, src, year = bell_windows(sc)
        mine = sorted(((f[i], sid) for sid, f in near.items() if i in f), key=lambda x: (x[0], x[1]))
        st_list = [{"id": sid, "name": stops[sid]["stop_name"], "ft": int(round(f)),
                    "lat": round(float(stops[sid]["stop_lat"]), 5), "lon": round(float(stops[sid]["stop_lon"]), 5),
                    "routes": sorted(stop_routes.get(sid, ()))} for f, sid in mine]
        served = sorted({trips[t]["route_id"] for t in best[i]})
        ws = []
        for name, lo, hi, bell in windows:
            arr = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
            per = collections.Counter()
            for t, (f, sid, m) in best[i].items():
                if m is not None and lo <= m <= hi:
                    arr[trips[t]["route_id"]][trips[t]["direction_id"]][sid].append(hhmm(m))
                    per[trips[t]["route_id"]] += 1
            ws.append({"name": name, "bell": bell, "from": hhmm(lo), "to": hhmm(hi),
                       "tripsByRoute": dict(sorted(per.items())),
                       "arrivals": {r: {d: {sid: sorted(ts) for sid, ts in sorted(by.items())}
                                        for d, by in sorted(dd.items())} for r, dd in sorted(arr.items())}})
        out_schools.append({"name": sc["name"], "lists": sc["lists"], "private": sc["private"],
                            "lat": sc["lat"], "lon": sc["lon"], "point": sc["point"], "bellSource": src, "bellYear": year,
                            "routes": served, "stops": st_list, "windows": ws})

    doc = {
        "source": "SFMTA GTFS Transit Data, %s, linked from %s [primary — queried %s]" % (
            FEED_URL, FEED_PAGE, meta.get("fetched_on") or "unknown"),
        "notice": notice,
        "feed": {"url": FEED_URL, "lastModified": meta.get("lastModified"), "sha256": (meta.get("sha256") or "")[:16],
                 "calendarFrom": first.isoformat(), "calendarTo": last.isoformat(),
                 "serviceDate": day.isoformat(), "services": services,
                 "stale": last < dt.date.fromisoformat(meta.get("fetched_on") or last.isoformat()) - dt.timedelta(days=STALE_DAYS),
                 "checkedOn": meta.get("fetched_on")},
        "method": {
            "nearStop": "a stop within a quarter mile (1,320 ft) of the school in a straight line",
            "schoolPoint": "the door in data/school-case/dropoff.json where the school has one (point door), else "
                           "out/school-hour-crashes/schools.json (point repo)",
            "serviceDate": "the last Wednesday inside the feed's calendar, with the services running that day",
            "window": "%d minutes before the earliest bell to %d minutes after the latest" % (WINDOW_MIN, WINDOW_MIN),
            "arrival": "each trip once per window, at the near stop closest to the school; times truncated to the minute; "
                       "tripsByRoute counts those trips",
            "bells": "the school's own start and dismissal from data/school-case/dropoff.json (bellSource school); "
                     "else SFUSD's published start and end times (bellSource sfusd, with bellYear); else a placeholder "
                     "8:00 AM start and 3:00 PM end (bellSource placeholder), which is not the school's bell",
            "shapes": "the most-used shape per route and direction among those trips, simplified to %d ft" % SIMPLIFY_FT,
            "arrivals": "route -> direction_id -> stop_id -> arrival times HH:MM",
        },
        "schools": out_schools,
        "routes": out_routes,
    }
    wrote = write_json(os.path.join(root, OUT_REL), doc, separators=(",", ":"))
    return doc, wrote


# ---- selftest ----------------------------------------------------------------------------

def cut_service(src_zip, dst_zip, service_id, share, broken_stop_times=False):
    """Copy the feed at `src_zip` to `dst_zip` without `share` of `service_id`'s trips or their stop times.

    The service cut the per-day check must refuse; --selftest and
    scripts/muni-gtfs-test.py both use it. `broken_stop_times` also appends a
    repeated stop_time and one whose trip does not exist. Returns the number of
    trips removed."""
    with zipfile.ZipFile(src_zip) as src, zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED) as dst:
        mine = [t["trip_id"] for t in rows(src, "trips.txt") if t["service_id"] == service_id]
        gone = set(mine[: int(len(mine) * share)])
        names = src.namelist()
        for name in ["trips.txt"] + [n for n in names if n != "trips.txt"]:
            data = src.read(name)
            if name in ("trips.txt", "stop_times.txt"):
                lines = data.decode("utf-8-sig").splitlines(True)
                col = next(csv.reader([lines[0]])).index("trip_id")
                keep = [lines[0]] + [ln for ln in lines[1:] if next(csv.reader([ln]))[col].strip() not in gone]
                if name == "stop_times.txt" and broken_stop_times:
                    keep.append(keep[1])
                    keep.append(keep[1].replace(keep[1].split(",")[0], "NO-SUCH-TRIP", 1))
                data = "".join(keep).encode("utf-8")
            dst.writestr(name, data)
    return len(gone)


def selftest():
    """A broken copy of the held feed fails its checks, adopt() refuses it, and the held copy is untouched."""
    held = zip_path()
    if not os.path.exists(held):
        sys.exit("selftest needs the held feed; run tools/muni/muni-gtfs.py first")
    before = sha256(held)
    days = scan(held)["service-days"]
    with zipfile.ZipFile(held) as zf:
        _, services, _, _ = service_day(zf)
    busiest = max(services, key=lambda s: scan(held)["trips.txt"]["by_service"][s])
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.zip")
        # 35% of the weekday service's trips gone (a service cut, or a short
        # read), a stop_time whose trip does not exist, and a repeated key.
        n = cut_service(held, bad, busiest, 0.35, broken_stop_times=True)
        print("  held copy: %d trips on a weekday (%s); broken copy lacks %d of service %s's trips" % (
            days["weekday"]["trips"], days["weekday"]["date"], n, busiest))
        refused = adopt(bad, {"etag": "test", "lastModified": "test", "sha256": "test", "bytes": 0})
        names = sorted({r.check for r in refused})
        print("  broken copy refused, %d failing checks:" % len(refused))
        for r in refused:
            print("    %r" % r)
        want = ["muni-gtfs stop_times.trip_id~trips.join", "muni-gtfs/stop_times.txt.unique[trip_id+stop_sequence]",
                "muni-gtfs/service-days.trips[weekday]", "muni-gtfs/service-days.stop_times[weekday]"]
        missing = [w for w in want if w not in names]
        assert not missing, "expected failures not raised: %s" % missing
        assert os.path.exists(bad), "the refused copy was moved into place"
    assert sha256(held) == before, "the held copy changed"
    print("muni-gtfs selftest ok: held copy unchanged")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--accept-growth", action="store_true",
                    help="with --update or --refresh: accept a new feed that more than doubles a file's rows, or adds more "
                         "than 15%% to a day's trips or stop times")
    a = ap.parse_args()
    ACCEPT_GROWTH["on"] = a.accept_growth
    if a.selftest:
        return selftest()
    if a.check:
        res = run(checks(), ROOT)
        for r in res:
            print("  %r" % r)
        sys.exit(1 if failures(res) else 0)
    held = os.path.exists(zip_path())
    meta = read_meta()
    if a.update or a.refresh or not held:
        try:
            status, meta = refresh(force=a.refresh or not held)
            pipeline_state.record(MARKER, status, version=meta.get("lastModified"),
                                  detail="ETag %s, sha256 %s" % (meta.get("etag"), (meta.get("sha256") or "")[:12]))
        except (urllib.error.URLError, IOError, ValueError, OSError) as exc:
            if not held:
                raise
            pipeline_state.record(MARKER, "failed", version=(meta or {}).get("lastModified"),
                                  detail="re-read failed, held copy of %s kept: %s" % ((meta or {}).get("fetched_on"), exc))
            print("  muni-gtfs re-read failed (%s); keeping the held copy" % exc)
    doc, wrote = build(meta=meta)
    f = doc["feed"]
    print("  muni-schools: %d schools, %d routes, service day %s (feed calendar %s to %s); %s" % (
        len(doc["schools"]), len(doc["routes"]), f["serviceDate"], f["calendarFrom"], f["calendarTo"],
        "written" if wrote else "unchanged"))
    if f["calendarTo"] < (dt.date.today() - dt.timedelta(days=STALE_DAYS)).isoformat():
        print("  STALE: the feed's calendar ended %s, more than %d days ago; SFMTA has not published a later file"
              % (f["calendarTo"], STALE_DAYS))
        pipeline_state.record(MARKER, "stale", version=(meta or {}).get("lastModified"),
                              detail="calendar ended %s; checked %s" % (f["calendarTo"], dt.date.today().isoformat()))
    res = run(checks(), ROOT)
    bad = failures(res)
    for r in bad:
        print("  %r" % r)
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
