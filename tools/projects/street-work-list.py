#!/usr/bin/env python3
"""Which street work is coming, and does the block have a bikeway today.

The Idea 1 join, built light: three DataSF datasets, one key (`cnn`, the street
centerline number), one table out.

    tools/projects/street-work-list.py                 # writes to out/street-work/
    tools/projects/street-work-list.py --out DIR
    tools/projects/street-work-list.py --cache         # reuse a previous fetch

Why the output is per project and not per row: `btxj-k9uh` is a
project-on-a-segment table. 8,120 rows carry 389 distinct `dotmapsid` values.
An earlier draft of `topics/sf-street-work-compliance.md` reported the row count
as a project count and was wrong by a factor of twenty, so this script prints
both numbers every time it runs and refuses to quote one without the other.

Every failure mode in this system so far has returned success with the data
missing, so each fetch asserts a floor and dies loudly under it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import ast
import csv
import datetime as dt
import html
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import stable  # noqa: E402
import sfdata
import urllib.parse
import urllib.request

BASE = "https://data.sfgov.org/resource"

# SFMTA's own ArcGIS server. DataSF does not index it, which is why an earlier
# version of this project concluded the planned-network join could not be run.
# `MTA.MPF_Network` is the Modal Planning Framework: one row per street segment,
# keyed on the same CNN, saying which modes that street is supposed to serve.
MPF_URL = (
    "https://services.sfmta.com/arcgis/rest/services/Multimodal/"
    "modal_planning_framework/MapServer/2/query"
)
MPF_FIELDS = "CNN,CORE_BIKING,GAP_BIKE_SEGMENTS,HIGH_INJURY_NETWORK"
MPF_PAGE = 2000          # the layer's own maxRecordCount
MPF_FLOOR = 15000        # 17,026 on 2026-09-04

# MPF_Network's metadata records it as created in 2022 and updated "as-needed
# and according to staff capacity". It therefore PRE-DATES the 2025 Biking and
# Rolling Plan and is NOT the North Star Network. Every output says so, because
# a reader who knows the 2025 plan will otherwise assume this is it.
MPF_VINTAGE = "2022"

BIKE_PRIORITY_ORDER = ["High", "Medium", "Low", "None"]

# The 2025 network, read off the plan's own map. Preferred over the traced
# index because the plan says to defer to the map where the two differ.
NORTH_STAR_PATHS = [
    "out/north-star/map-trace/traced.geojson",
    "out/north-star/segments.geojson",
]

# Does the published record say this project will touch biking or walking?
# It usually does not. `description` is "NONE", "N/A" or a ticket number on
# 123 of 389 projects and its median length is 13 characters, so the project
# NAME carries almost all of the signal and the answer for most projects is
# "the record does not say" rather than "no".
BIKE_WORDS = re.compile(
    r"\bbike|\bbicycl|bikeway|cycle ?track|cycletrack|sharrow|greenway|"
    r"slow street|quick.?build|protected lane|buffered lane", re.I)
ACTIVE_WORDS = re.compile(
    r"pedestrian|streetscape|vision zero|curb ramp|bulb|crosswalk|"
    r"traffic calming|complete street", re.I)
# SFMTA's own bike and pedestrian units. A project owned by one of these is
# about street design whatever its name says.
BIKE_UNITS = re.compile(r"MTA .*(Livable Streets|Transportation Engineering)", re.I)

SCOPE_BIKE = "bike work named"
SCOPE_ACTIVE = "walking or streetscape named"
SCOPE_UNIT = "SFMTA street-design unit"
SCOPE_SILENT = "the record does not say"

# A project whose design can still change is one that has not finished.
#
# The earlier rule excluded Construction unless the start date was still ahead,
# which cut a project off the moment work began. That is the wrong end of the
# job: bike infrastructure goes in near the end, before restriping, so the
# window closes at completion and not at groundbreaking. Every construction
# project in the feed that has started still has a future end date, median 237
# days out, so the old rule dropped mid-flight projects with most of a year
# left. Mirrored in `site/scripts/lib/upcoming.mjs`; check-upcoming-parity.py
# fails if the two drift.


def load_north_star(paths=NORTH_STAR_PATHS):
    """cnn -> facility, from whichever North Star artifact exists.

    Returns ({}, None) when neither does, and every output then says the
    planned-network column is missing rather than printing an empty one."""
    for path in paths:
        if not os.path.exists(path):
            continue
        by_cnn = {}
        for f in json.load(open(path))["features"]:
            pr = f["properties"]
            fac = pr.get("facility") or pr.get("north_star") or "?"
            cnns = pr["cnns"] if "cnns" in pr else [pr.get("cnn")]
            for c in cnns:
                if c is not None:
                    by_cnn[str(c)] = fac
        return by_cnn, path
    return {}, None


# How close a project's own line has to come to a North Star line before we
# call it a match. The threshold is not doing the work: of the 41 projects this
# path exists for, 24 sit at exactly 0 m (their vertices are the same snapped
# centerline points), 3 more are under 10 m, and the next one is 34 m away. Any
# value from 10 to 30 selects the same 27 projects.
NS_GEOMETRY_METRES = 25.0

# Degrees per grid cell, about 45 m at this latitude. Only used to bucket
# points so the nearest-vertex scan looks at nine cells instead of 15,498.
_NS_CELL = 0.0005


def _vertices(geom):
    """Every coordinate in a GeoJSON geometry, whatever its type.

    Public Works publishes LineStrings for most projects, Polygons for 18 of
    them and Points for 2, so a LineString-only reader silently drops twenty.
    """
    if not geom:
        return []
    if isinstance(geom, str):
        try:
            geom = json.loads(geom)
        except ValueError:
            return []
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "LineString":
        return [tuple(pt[:2]) for pt in c]
    if t == "MultiLineString":
        return [tuple(pt[:2]) for line in c for pt in line]
    if t == "Polygon":
        return [tuple(pt[:2]) for ring in c for pt in ring]
    if t == "MultiPolygon":
        return [tuple(pt[:2]) for poly in c for ring in poly for pt in ring]
    if t == "Point":
        return [tuple(c[:2])]
    return []


def load_north_star_geometry(paths=NORTH_STAR_PATHS):
    """A point index of the North Star network, for projects with no CNN.

    THE DEFECT THIS EXISTS FOR. `btxj-k9uh` publishes its `cnn` field as the
    literal string "[]" for 61 of the 389 projects — no centerline id at all —
    so a match keyed on CNN cannot see them and they render as "not on the
    network". They are not: 41 of the 61 publish real geometry, and 27 of those
    lie on the North Star network, 24 of them exactly. Every one was reported
    to the reader as a street with no planned bike work.

    Returns (grid, count). The grid maps a coarse cell to (lon, lat, facility)
    so a match can name the planned facility the same way a CNN match does.
    """
    grid, n = {}, 0
    for path in paths:
        if not os.path.exists(path):
            continue
        for f in json.load(open(path))["features"]:
            pr = f.get("properties") or {}
            fac = pr.get("facility") or pr.get("north_star") or "?"
            for x, y in _vertices(f.get("geometry")):
                grid.setdefault((int(x / _NS_CELL), int(y / _NS_CELL)), []).append((x, y, fac))
                n += 1
    return grid, n


def nearest_north_star(points, grid, limit=NS_GEOMETRY_METRES):
    """(facility, metres) for the closest North Star vertex, or (None, None).

    Flat-earth distance. Over 25 m in San Francisco the error is centimetres,
    and the alternative is a projection library this repo does not have.
    """
    best_d, best_f = None, None
    for x, y in points:
        gx, gy = int(x / _NS_CELL), int(y / _NS_CELL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ax, ay, fac in grid.get((gx + dx, gy + dy), ()):
                    d = math.hypot((ax - x) * 88800.0, (ay - y) * 111000.0)
                    if best_d is None or d < best_d:
                        best_d, best_f = d, fac
    if best_d is not None and best_d <= limit:
        return best_f, best_d
    return None, None


def read_scope(name, description, agency):
    """What the published record says about this project's scope.

    Deliberately not a judgement about what the city will build. It reports
    what the three published fields contain, and its most common answer is
    that they contain nothing on the question."""
    text = f"{name} {description}"
    if BIKE_WORDS.search(text):
        return SCOPE_BIKE
    if BIKE_UNITS.search(agency or ""):
        return SCOPE_UNIT
    if ACTIVE_WORDS.search(text):
        return SCOPE_ACTIVE
    return SCOPE_SILENT

# Floors are set well below the counts observed on 2026-09-04 (8,120 / 5,457 /
# 3,381). They are here to catch a silent empty or a truncated response, not to
# pin the data to a day.
DATASETS = {
    "projects": ("btxj-k9uh", 4000),
    "bikeways": ("ygmz-vaxd", 3000),
    "moratorium": ("5wbp-dwzt", 1500),
}

# A project whose work starts inside this window is one an advocate can still
# act on. It is the notice the city gives excavators before it paves a block
# (Public Works Order 187005 sec. 5.2(A)(2)); the public gets no equivalent.
EXCAVATOR_NOTICE_DAYS = 120


READ_ON = []


def fetch(fxf, floor, cache_dir=None, update=False):
    """Pull every row of a dataset. Die if it comes back thin.

    The hand-rolled cache that used to live here was replaced on 2026-09-06 by
    `lib/sfdata.py`. It had two defects the shared layer fixes: it stored a
    bare list with no date, so a cached run could not say when its rows were
    true, and it asked for a single `$limit` of 50,000 with no pagination --
    a dataset that outgrew one page would have truncated silently, under a
    floor set well below the limit. The floors move across unchanged.

    Without --cache the contract is unchanged too: refresh=True reads from
    Socrata whatever is on disk, and the fresh rows are still written to the
    shared cache so they carry today's date.
    """
    # --update reads the shared cache, which pipeline/refresh-socrata.py keeps
    # current by re-reading only datasets DataSF says have changed.
    r = sfdata.fetch(fxf, floor=floor,
                     cache_dir=cache_dir or None,
                     refresh=not (cache_dir or update))
    READ_ON.append(r.fetched_on)
    print(f"  {fxf}: {len(r.rows):,} rows"
          f"{' (cached ' + r.fetched_on.isoformat() + ')' if r.from_cache else ''}",
          file=sys.stderr)
    return r.rows


def rows_updated_at(fxf):
    """When the publisher last touched the rows. Not the same as when they last
    checked: `ygmz-vaxd` claims a quarterly cadence and on 2026-09-04 had not
    been updated since April, which is long enough for a new bikeway to be
    missing from it."""
    try:
        url = f"https://data.sfgov.org/api/views/{fxf}.json"
        with urllib.request.urlopen(url, timeout=60) as resp:
            v = json.load(resp)
        ts = v.get("rowsUpdatedAt")
        return dt.date.fromtimestamp(ts) if ts else None
    except Exception:
        return None


def norm_cnn(v):
    """One CNN as a comparable string.

    DataSF publishes `cnn` as a string, SFMTA's ArcGIS layer publishes it as a
    double — "361000" against 15145000.0 — so both sides go through here or the
    join silently matches nothing.
    """
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return None


def parse_cnns(value):
    """Every CNN in a `cnn` field, which is not always one CNN.

    `btxj-k9uh` puts a Python-style list in this field when a project row spans
    several centreline segments: `"['23348000', '23347000', '1720000']"`. On
    2026-09-04 that was 914 of 8,120 rows (11.3%), touching 158 of the 389
    projects (40.6%), and unpacking them raises the distinct CNN count from
    6,728 to 7,916.

    An earlier version of this script read the field as a single key. Those rows
    then matched nothing in the bikeway or moratorium tables, so their segments
    were counted as having no bikeway — which is the failure direction that
    matters here, because it inflates the headline "touches no existing bikeway"
    number that the whole page is built on. The other two DataSF datasets were
    checked on 2026-09-04 and carry no list-shaped values.
    """
    raw = (value or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
        return [c for c in (norm_cnn(v) for v in parsed) if c]
    one = norm_cnn(raw)
    return [one] if one else []


# The layer carries no edit date, so the marker also counts rows by the three
# fields read: a block moved onto or off the high-injury network changes a
# count even when the row count and the largest OBJECTID stay put. An edit
# that swaps two blocks' values leaves every count as it was, so a copy is
# also re-read once it is MPF_MAX_AGE_DAYS old.
MPF_MAX_AGE_DAYS = 30


def mpf_marker():
    """Row count, largest OBJECTID, and row counts by the fields read: moves when the layer does."""
    def stats(extra):
        q = urllib.parse.urlencode(dict({"where": "1=1", "f": "json"}, **extra))
        with urllib.request.urlopen(f"{MPF_URL}?{q}", timeout=60) as resp:
            d = json.load(resp)
        if "error" in d or not d.get("features"):
            raise RuntimeError("no statistics in the answer: %s" % json.dumps(d)[:200])
        return [{k.lower(): v for k, v in f["attributes"].items()} for f in d["features"]]
    a = stats({"outStatistics": json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "n"},
        {"statisticType": "max", "onStatisticField": "OBJECTID", "outStatisticFieldName": "m"}])})[0]
    groups = stats({"outStatistics": json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "n"}]),
        "groupByFieldsForStatistics": "CORE_BIKING,GAP_BIKE_SEGMENTS,HIGH_INJURY_NETWORK"})
    by = sorted("%s/%s/%s=%s" % (g.get("core_biking"), g.get("gap_bike_segments"), g.get("high_injury_network"),
                                 g.get("n")) for g in groups)
    return "%s rows, max OBJECTID %s; %s" % (a.get("n"), a.get("m"), " ".join(by))


def read_mpf():
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": MPF_FIELDS, "returnGeometry": "false",
            "resultOffset": offset, "resultRecordCount": MPF_PAGE, "f": "json",
        })
        with urllib.request.urlopen(f"{MPF_URL}?{q}", timeout=180) as resp:
            page = json.load(resp)
        if "error" in page:
            sys.exit(f"FAIL: MPF_Network returned an error: {page['error']}")
        feats = page.get("features", [])
        rows += [f["attributes"] for f in feats]
        if len(feats) < MPF_PAGE:
            break
        offset += MPF_PAGE
    print(f"  MTA.MPF_Network: {len(rows):,} rows", file=sys.stderr)
    return rows


def fetch_mpf(cache_dir=None, update=False):
    """SFMTA's modal priority layer, paged. Dies if it comes back thin.

    With --update the copy in .cache/street-work/ is kept until the layer's
    marker (mpf_marker) moves or the copy is MPF_MAX_AGE_DAYS old. The copy
    is replaced only after a full read has passed the floor, and the new
    marker is recorded only then, so a failed re-read keeps the last good
    copy and the next run tries again."""
    if update:
        cache_dir = os.path.join(paths.ROOT, ".cache", "street-work")
    cache = os.path.join(cache_dir, "mpf_network.json") if cache_dir else None
    marker, reread = None, not (cache and os.path.exists(cache))
    if update:
        from lib import pipeline_state
        try:
            marker = mpf_marker()
        except Exception as exc:  # noqa: BLE001
            pipeline_state.record("arcgis:mta-mpf", "failed", detail="marker check failed: %s" % exc)
            print(f"  MTA.MPF_Network: change check failed ({exc}); using the copy", file=sys.stderr)
        last = pipeline_state.load().get("arcgis:mta-mpf", {})
        old = os.path.exists(cache) and (
            dt.datetime.now().timestamp() - os.path.getmtime(cache)) > MPF_MAX_AGE_DAYS * 86400
        if marker and (marker != last.get("version") or last.get("status") == "failed" or old):
            reread = True
        elif marker:
            pipeline_state.record("arcgis:mta-mpf", "unchanged", version=marker)
    if cache and not reread:
        with open(cache) as fh:
            rows = json.load(fh)
        print(f"  MTA.MPF_Network: {len(rows):,} rows (cached)", file=sys.stderr)
    else:
        rows = read_mpf()
    if len(rows) < MPF_FLOOR:
        sys.exit(
            f"FAIL: MPF_Network returned {len(rows)} rows, floor is {MPF_FLOOR}. "
            f"Paging may have stopped early, which looks like a quiet city from "
            f"here, so this stops rather than reporting."
        )
    if cache and reread:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache + ".tmp", "w") as fh:
            json.dump(rows, fh)
        os.replace(cache + ".tmp", cache)
        if update and marker:
            from lib import pipeline_state
            pipeline_state.record("arcgis:mta-mpf", "changed", version=marker, detail="%d rows re-read" % len(rows))
    return rows


def parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def build(projects, bikeways, moratorium, mpf, north_star, today, ns_grid=None):
    """Collapse the segment rows into one record per project."""
    # cnn -> facility types present on that segment today
    bikeway_cnn = {}
    for r in bikeways:
        for cnn in parse_cnns(r.get("cnn")):
            bikeway_cnn.setdefault(cnn, set()).add(r.get("facility_t") or "?")

    # cnn -> latest expiration of a five-year paving lock still in force
    locked_cnn = {}
    for r in moratorium:
        exp = parse_date(r.get("expirationdate"))
        if not (exp and exp >= today):
            continue
        for cnn in parse_cnns(r.get("cnn")):
            if cnn not in locked_cnn or exp > locked_cnn[cnn]:
                locked_cnn[cnn] = exp

    # cnn -> the modal priority record for that segment
    mpf_cnn = {}
    for r in mpf:
        cnn = norm_cnn(r.get("CNN"))
        if cnn:
            mpf_cnn[cnn] = r

    by_project = {}
    rows_without_id = 0
    for r in projects:
        pid = (r.get("dotmapsid") or "").strip()
        if not pid:
            rows_without_id += 1
            continue
        p = by_project.setdefault(
            pid,
            {
                "id": pid,
                "name": r.get("name") or "",
                "agency": r.get("agency_name") or "",
                "status": r.get("project_status") or "",
                "phase": r.get("project_phase") or "",
                "description": r.get("description") or "",
                "pm_name": r.get("project_manager_name") or "",
                # The manager's address is deliberately NOT carried into any
                # output. Bryan, 2026-09-19: the city should stay the only
                # publisher of its staff's email addresses. Their name in their
                # official role is public record and stays; every row links to
                # Public Works' own record for the project, which carries the
                # address, so the reader is one click from it and the city is
                # the one publishing it.
                "start": parse_date(r.get("start_date")),
                "end": parse_date(r.get("end_date")),
                "cnns": set(),
                "streets": set(),
                "points": [],
            },
        )
        p["cnns"].update(parse_cnns(r.get("cnn")))
        # Kept only for the no-CNN fallback below. Cheap: 61 projects reach it.
        p["points"].extend(_vertices(r.get("co_ordinatelinestring")))
        if r.get("on_street"):
            p["streets"].add(r["on_street"].strip())
        # Keep the earliest start and the latest end across the segments.
        s, e = parse_date(r.get("start_date")), parse_date(r.get("end_date"))
        if s and (p["start"] is None or s < p["start"]):
            p["start"] = s
        if e and (p["end"] is None or e > p["end"]):
            p["end"] = e

    out = []
    for p in by_project.values():
        cnns = p["cnns"]
        with_bikeway = {c for c in cnns if c in bikeway_cnn}
        locked = {c for c in cnns if c in locked_cnn}
        facilities = sorted({f for c in with_bikeway for f in bikeway_cnn[c]})
        days = (p["start"] - today).days if p["start"] else None
        # Time left before the work is finished, which is the window that
        # matters for asking. Negative means the published end date has passed.
        days_to_end = (p["end"] - today).days if p["end"] else None

        # Modal priority, from the 2022 layer. `in_mpf` is reported alongside
        # every other MPF number because 37% of project segments are not in the
        # layer at all, and a blank there means "unrecorded", not "not a
        # priority". Reporting the counts without the denominator would read as
        # the second thing.
        in_mpf = [mpf_cnn[c] for c in cnns if c in mpf_cnn]
        priorities = {(r.get("CORE_BIKING") or "").strip() for r in in_mpf}
        # "None" and "no record" are different answers and must not both render
        # blank: the first is SFMTA saying this street is not a bike priority,
        # the second is SFMTA not having said anything about it.
        if not in_mpf:
            top = "no record"
        else:
            top = next((p_ for p_ in BIKE_PRIORITY_ORDER if p_ in priorities), "None")

        # THE FLAG THIS LIST EXISTS FOR. Not "is there a bike lane here today"
        # — that is the wrong question, because a street with no bike lane is
        # the normal case and says nothing about whether one is wanted. The
        # question is whether the city's own plan says this street should carry
        # biking. A segment qualifies if SFMTA's modal layer puts it on the core
        # biking network at any priority, or flags it as a hole in the network.
        planned_segs = sum(
            1 for r in in_mpf
            if (r.get("CORE_BIKING") or "").strip() in ("High", "Medium", "Low")
            or (r.get("GAP_BIKE_SEGMENTS") or "") == "Yes"
        )
        gap_segs = sum(
            1 for r in in_mpf if (r.get("GAP_BIKE_SEGMENTS") or "") == "Yes"
        )
        if not in_mpf:
            flag = "no record"
        elif gap_segs:
            flag = "YES — gap"
        elif planned_segs:
            flag = "YES — %s" % top
        else:
            flag = "—"

        # THE FLAG THIS LIST NOW EXISTS FOR, and it replaces the 2022 one
        # above. Does this project sit on the 2025 North Star network, and
        # does anything the city has published say bike work is in its scope?
        ns_hits = [north_star[c] for c in cnns if c in north_star]
        # The no-CNN fallback. Only projects the centerline match CANNOT reach
        # are sent down it, so the 187 projects matched by CNN keep exactly the
        # numbers they had and any change in the total is attributable here.
        ns_match = "centerline" if ns_hits else "—"
        ns_metres = None
        if not cnns and ns_grid and p["points"]:
            fac, dist = nearest_north_star(p["points"], ns_grid)
            if fac:
                ns_hits = [fac]
                ns_match, ns_metres = "geometry", round(dist, 1)
        ns_facilities = sorted(set(ns_hits))
        scope = read_scope(p["name"], p["description"], p["agency"])
        # Finished work cannot change. Everything else can, whatever its phase.
        changeable = days_to_end is None or days_to_end >= 0
        # "Ask about this one" is not "the city is not building a bike lane
        # here". It is: the plan says this street should carry biking, work
        # is coming, and nothing published says the bike work is in scope —
        # which is exactly what §2.4.13 requires a determination about.
        ask = bool(ns_hits) and scope == SCOPE_SILENT and changeable

        out.append(
            {
                **p,
                "segments": len(cnns),
                "segments_with_bikeway": len(with_bikeway),
                "segments_locked": len(locked),
                "facility_types": ", ".join(facilities),
                "segments_in_mpf": len(in_mpf),
                "bike_priority": top,
                "on_planned_bike_network": flag,
                "segments_north_star": len(ns_hits),
                "north_star_match": ns_match,
                "north_star_metres": "" if ns_metres is None else ns_metres,
                "north_star_facility": ", ".join(ns_facilities),
                "on_north_star": ("YES — " + ", ".join(ns_facilities)) if ns_hits else "—",
                "bike_scope": scope,
                "still_changeable": changeable,
                "ask_about": ask,
                "segments_planned_bike": planned_segs,
                "segments_bike_gap": gap_segs,
                "segments_hin": sum(
                    1 for r in in_mpf
                    if (r.get("HIGH_INJURY_NETWORK") or "") == "Yes"
                ),
                "days_to_start": days,
                "days_to_end": days_to_end,
                # The whole point of the list: work that has not started, close
                # enough that the design could still change.
                "in_notice_window": days is not None and 0 <= days <= EXCAVATOR_NOTICE_DAYS,
                "streets": ", ".join(sorted(p["streets"])[:6]),
            }
        )

    # Most actionable first, and what makes a project actionable is how long is
    # left before it finishes — not how long until it starts. A job with 30 days
    # to restriping is the most urgent row here; a job starting in two years is
    # the least. So the sort runs on time remaining, and a project with no
    # published end date goes last because nothing can be said about it.
    def rank(p):
        d = p["days_to_end"]
        if d is None:
            return (2, 0)
        if d < 0:
            return (1, -d)
        return (0, d)

    out.sort(key=rank)
    return out, rows_without_id


COLUMNS = [
    ("days_to_start", "Days to start"),
    ("start", "Start"),
    ("end", "End"),
    ("name", "Project"),
    ("agency", "Agency"),
    ("status", "Status"),
    ("phase", "Phase"),
    ("streets", "Streets"),
    ("segments", "Segments"),
    ("ask_about", "Ask about this one"),
    ("on_north_star", "On the 2025 North Star network"),
    ("segments_north_star", "Segments on the 2025 network"),
    ("north_star_facility", "Planned facility"),
    ("north_star_match", "Matched by"),
    ("north_star_metres", "Metres to the network"),
    ("bike_scope", "What the record says about scope"),
    ("segments_with_bikeway", "With bikeway today"),
    ("segments_hin", "High-injury segments"),
    ("segments_in_mpf", "Segments with a priority record"),
    ("segments_locked", "In moratorium"),
    ("facility_types", "Facility types"),
    ("pm_name", "Project manager"),
    ("id", "DotMaps id"),
]

ORDINANCE = (
    "San Francisco Administrative Code §98.1(d)(2): “Decisions regarding the "
    "design and use of the City’s limited public street space shall prioritize "
    "space for pedestrians, bicycles, and public transit over space for "
    "automobiles.”"
)


def write_csv(path, rows):
    import io
    fh = io.StringIO(newline="")
    w = csv.writer(fh)
    w.writerow([label for _, label in COLUMNS])
    for r in rows:
        w.writerow([r[k] if r[k] is not None else "" for k, _ in COLUMNS])
    stable.write_text(path, fh.getvalue())


def write_html(path, rows, stats, today, vintage):
    upcoming = [r for r in rows if r["in_notice_window"]]
    flagged = [r for r in rows if r["ask_about"]]

    def cells(r):
        return "".join(
            f"<td>{html.escape(str(r[k]) if r[k] is not None else '')}</td>"
            for k, _ in COLUMNS
        )

    def table(rs):
        head = "".join(f"<th>{html.escape(l)}</th>" for _, l in COLUMNS)
        body = "".join(
            f"<tr class=\"{'nb' if r['ask_about'] else ''}\">{cells(r)}</tr>"
            for r in rs
        )
        return f"<div class=scroll><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"

    doc = f"""<!doctype html>
<meta charset=utf-8>
<title>SF street work and bikeways &mdash; {today}</title>
<style>
 body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 78rem;
        padding: 0 1rem; color: #1a1a1a; }}
 h1 {{ font-size: 1.5rem; margin-bottom: .2rem; }}
 h2 {{ font-size: 1.1rem; margin-top: 2.2rem; }}
 .sub {{ color: #666; margin-top: 0; }}
 blockquote {{ border-left: 3px solid #999; margin: 1rem 0; padding: .3rem 0 .3rem 1rem;
               color: #333; }}
 .scroll {{ overflow-x: auto; }}
 table {{ border-collapse: collapse; font-size: 13px; margin: .8rem 0; }}
 th, td {{ border-bottom: 1px solid #ddd; padding: .35rem .55rem; text-align: left;
           white-space: nowrap; }}
 th {{ background: #f4f4f4; position: sticky; top: 0; }}
 tr.nb td {{ background: #fffaf0; }}
 .caveat {{ background: #f7f7f7; padding: 1rem 1.2rem; border-radius: 4px; font-size: 14px; }}
 code {{ background: #f0f0f0; padding: 0 .25em; }}
</style>
<h1>Street work on the streets the 2025 bike plan wants</h1>
<p class=sub>Generated {today} from DataSF. Regenerate with
<code>tools/projects/street-work-list.py</code>.</p>

<blockquote>{html.escape(ORDINANCE)}</blockquote>

<h2>Starting within {EXCAVATOR_NOTICE_DAYS} days &mdash; {len(upcoming)} projects</h2>
<p>{EXCAVATOR_NOTICE_DAYS} days is the notice the city gives excavators before it
paves a block (Public Works Order 187005 &sect;5.2(A)(2)). There is no public
equivalent, so this list is the notice. Once a block is paved it is a Moratorium
Street and cannot be opened for five years.</p>
<p><strong>{len(flagged)} projects across the whole list are worth asking about</strong>
&mdash; highlighted rows, and the <em>Ask about this one</em> column. Each sits on the
2025 North Star network, is early enough to change, and has nothing in the published
record saying bike or pedestrian work is in its scope. That is not proof the work is
being left out; it is the case &sect;2.4.13 requires a determination about and where no
determination has been published.</p>
{table(upcoming) if upcoming else '<p><em>None.</em></p>'}

<h2>Everything else &mdash; {len(rows) - len(upcoming)} projects</h2>
{table([r for r in rows if not r['in_notice_window']])}

<h2>What this list does not see</h2>
<div class=caveat>
<p><strong>One row is not one project.</strong> <code>btxj-k9uh</code> holds
{stats['project_rows']:,} rows and {stats['projects']:,} distinct projects &mdash; a
project appears once per street segment. Every count on this page is projects.</p>
<p><strong>Coverage is unmeasured.</strong> <code>btxj-k9uh</code> is the
<em>coordination</em> list: work agencies filed with the Public Works coordinate
application. What fraction of actual city street work reaches it is not published
and this script cannot tell you. It is a floor, not a census.</p>
<p><strong>{stats['rows_without_id']:,} rows carry no project id</strong> and are
dropped. <strong>{stats['no_start']:,} projects carry no start date</strong> and sort
to the bottom rather than the top.</p>
<p><strong>The planned network is traced, not published.</strong> SFMTA published
the North Star network only as a map inside the 2025 plan. That map is a vector PDF,
so its lines are real geometry, and <code>tools/bike-network/north-star-map-trace.py</code> snaps
them back onto DataSF street centerlines. A block near the edge of a drawn corridor is
a judgement the trace made, not something SFMTA stated.</p>
<p><strong>&ldquo;The record does not say&rdquo; is a silent field, not a No.</strong>
The scope column reads three published fields &mdash; project name, description and
owning agency. The description reads &ldquo;NONE&rdquo;, &ldquo;N/A&rdquo; or a ticket
number on most rows, so the name carries nearly all of it. A project can be planning a
protected lane and say nothing about it here.</p>
<p><strong>High injury is still SFMTA&rsquo;s {MPF_VINTAGE} layer</strong>, kept because
the high-injury network is a separate product from the bike plan. Only
{stats['mpf_matched']:,} of the {stats['project_cnns']:,} segments under these projects
({stats['mpf_pct']:.0f}%) appear in that layer at all, so a zero there means no record
rather than no risk. The {MPF_VINTAGE} bike-priority columns that used to lead this page
are gone: they pre-dated the 2025 plan and are superseded by it.</p>
<p><strong>{stats['listy_rows']:,} project rows list several segments in one
field</strong> &mdash; <code>cnn</code> arrives as
<code>"['23348000', '23347000', ...]"</code>. They are unpacked. An earlier version
of this script read that field as a single key, so those segments matched nothing
and every priority and bikeway count on those rows was wrong.</p>
<p><strong>The flag is the plan, not the pavement.</strong> A missing bike lane is
not by itself a finding &mdash; most streets have none. What makes a row worth a letter
is that the city&rsquo;s own adopted plan says this street should carry biking and work
is about to happen on it.</p>
<p><strong>The moratorium column is a lock still in force on {today}</strong>
({stats['locked_segments']:,} segments), joined by <code>cnn</code>. A project
overlapping one is either waiting for the lock to lift or holds a waiver from the
Public Works Director &mdash; a decision with no public step.</p>
<p><strong>Dates move.</strong> Public Works states that project planning runs on
annual funding projections that &ldquo;are very dynamic and can change at any
time.&rdquo; Nothing here is a commitment by the city.</p>
<p><strong>How old each source is.</strong> {vintage}</p>
</div>
"""
    stable.write_text(path, doc)


MD_COLUMNS = [
    ("days_to_start", "In"),
    ("start", "Starts"),
    ("name", "Project"),
    ("agency", "Agency"),
    ("phase", "Phase"),
    ("streets", "Streets"),
    ("north_star_facility", "Planned facility"),
    ("bike_scope", "Scope says"),
    ("segments_with_bikeway", "Bikeway"),
    ("segments_hin", "High injury"),
    ("segments_locked", "Locked"),
    ("pm_name", "Project manager"),
]


def write_markdown(path, rows, stats, today, vintage_plain):
    """A readable version for a review doc, since the HTML page cannot be read
    on a board or a phone. The lead table is the ask-about list; the full list
    is the CSV."""
    upcoming = [r for r in rows if r["in_notice_window"]]
    on_ns = [r for r in rows if r["segments_north_star"] > 0]
    ask = [r for r in rows if r["ask_about"]]
    phases = {}
    for r in upcoming:
        phases[r["phase"] or "?"] = phases.get(r["phase"] or "?", 0) + 1
    phase_note = "Of these, " + ", ".join(
        f"{n} are in {ph}" for ph, n in sorted(phases.items(), key=lambda kv: -kv[1])
    ) + "."
    spans = sorted(
        (r["end"] - r["start"]).days
        for r in rows
        if r["start"] and r["end"] and r["end"] >= r["start"]
    )
    span_median = spans[len(spans) // 2] if spans else "?"

    def row(r):
        vals = []
        for k, _ in MD_COLUMNS:
            v = r[k]
            if k == "days_to_start":
                v = f"{v}d"
            elif k == "name":
                # Every project name links to Public Works' own rows for it, so
                # a reader can check any figure on this line against the city
                # rather than against us. Bryan asked for this on 2026-09-06:
                # "Make sure table and map have sourced links for app
                # information. And verify that it's all true."
                v = "[%s](https://data.sfgov.org/resource/btxj-k9uh.json?dotmapsid=%s)" % (
                    str(v).replace("|", "/").replace("[", "(").replace("]", ")"), r["id"])
            elif k == "north_star_facility" and r["north_star_match"] == "geometry":
                # Say how the match was made wherever the match is unusual. These
                # are the projects with no centerline id, matched on their own
                # geometry, and a reader checking the source record will find no
                # cnn on it — so the table has to explain that before they do.
                v = "%s *(by geometry, %s m — no centerline id published)*" % (v, r["north_star_metres"])
            vals.append(str(v if v is not None else "").replace("\n", " "))
        return "| " + " | ".join(vals) + " |"

    head = "| " + " | ".join(l for _, l in MD_COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in MD_COLUMNS) + " |"
    empty = "| *none* |" + " |" * (len(MD_COLUMNS) - 1)

    # Soonest first, but a project that has not started yet ranks above one
    # already under way, because only the first can still be changed.
    def by_soonest(rs):
        return sorted(rs, key=lambda r: (
            0 if (r["days_to_start"] is not None and r["days_to_start"] >= 0) else 1,
            r["days_to_start"] if r["days_to_start"] is not None else 10 ** 6))

    ask_table = "\n".join(row(r) for r in by_soonest(ask)) or empty
    ask_soon = [r for r in ask if r["in_notice_window"]]
    ask_soon_table = "\n".join(row(r) for r in by_soonest(ask_soon)) or empty
    ns_table = "\n".join(row(r) for r in by_soonest(on_ns)) or empty
    construction = [
        r for r in rows
        if r["phase"] == "Construction" and r["days_to_start"] is not None
        and r["days_to_start"] <= EXCAVATOR_NOTICE_DAYS
    ][:25]
    construction_rows = "\n".join(row(r) for r in construction) or empty
    scopes = {}
    for r in on_ns:
        scopes[r["bike_scope"]] = scopes.get(r["bike_scope"], 0) + 1
    scope_note = ", ".join(f"{n} say {k}" for k, n in
                           sorted(scopes.items(), key=lambda kv: -kv[1]))

    body = f"""# Street work on the streets the bike plan wants

Generated {today} by `tools/projects/street-work-list.py`. **This file is regenerated, so
comment on it freely but do not edit it — the next run overwrites the text.**

**{len(ask)} of the {stats['projects']} coordinated street projects are worth asking about.** Each
one sits on a street the 2025 Biking and Rolling Plan says should carry biking, is early enough
that its design could still change, and has nothing in anything the city has published saying
bike or pedestrian work is part of it. That is not proof the city is leaving the bike work out.
It is the case where Public Works Code §2.4.13 requires a determination and nobody has published
one, which is what makes it worth a letter.

**How the two halves of that test are made.** The first half is geometry: {len(on_ns)} projects
overlap the North Star network, read off the plan's own map and snapped to street centerlines.
The second half is the published record, and it is thin. Of those {len(on_ns)} projects,
{scope_note}. `btxj-k9uh` carries a `description` field that reads "NONE", "N/A" or a ticket
number on most rows, so the project name does nearly all the work, and an SFMTA street-design
unit owning the project counts as scope even when the name does not say so.

**What this cannot tell you.** Whether the bike work is in the project. The city publishes where
it will dig; it does not publish what it decided about the street while it was there. A project
in the ask-about table may already have a bike lane in its drawings. The point of the letter is
to make somebody say so in writing.

> Public Works Code §2.4.13: a repaving project "shall include, to the maximum extent practicable
> and feasible" the bicycle and pedestrian safety measures in "any official City adopted bicycle
> or pedestrian safety plan".
>
> Administrative Code §98.1(d)(2): "Decisions regarding the design and use of the City's limited
> public street space shall prioritize space for pedestrians, bicycles, and public transit over
> space for automobiles."

**Read the Phase column before the date.** `Starts` is when the *project* starts, not when the
street is opened. The median project here runs {span_median} days from start to end, so a
project entering Design is typically more than a year from paving. That is good news: the
warning is longer than the {EXCAVATOR_NOTICE_DAYS} days the city gives excavators, not shorter.
{len(upcoming)} projects start within {EXCAVATOR_NOTICE_DAYS} days. {phase_note}

## Start here: the {len(ask_soon)} that start within {EXCAVATOR_NOTICE_DAYS} days

These are the ones where the clock is running. Everything in the next table is worth a letter;
these are worth one this week.

{head}
{sep}
{ask_soon_table}

## The whole ask-about list

{len(ask)} projects. On the 2025 network, still changeable, and the record says nothing about
bike work. Soonest first; a negative *In* means the work has already begun. Most of these are in
Design or Planning and are years from paving, which is the good case: a project entering Design
is the one whose drawings can still change.

{head}
{sep}
{ask_table}

## Everything on the 2025 North Star network

All {len(on_ns)} projects that overlap the planned network, whatever their scope says, so the
list above can be checked against the ones it left out.

{head}
{sep}
{ns_table}

## Where the street actually gets opened: Construction phase

Projects in Construction. The design decision on these has been made, so this is the list for
checking what was built, not for changing it.

{head}
{sep}
{construction_rows}

The full list of {stats['projects']} projects is in `out/street-work/street-work.csv`; the
browsable version is `out/street-work/index.html`; the map is `out/street-work/map.html`.

## What this list does not see

- **One row is not one project.** `btxj-k9uh` holds {stats['project_rows']:,} rows and
  {stats['projects']:,} distinct projects — a project appears once per street segment.
  Every count here is projects.
- **Coverage is unmeasured.** `btxj-k9uh` is the *coordination* list: work agencies filed with
  the Public Works coordinate application. What fraction of actual city street work reaches it
  is not published. It is a floor, not a census.
- **"The record does not say" is the honest reading of a silent field, not a No.** The scope
  test reads three published fields — project name, description and owning agency — and the
  description is unusable on most rows. A project can be planning a protected lane and say
  nothing about it here.
- **The planned network is traced, not published.** SFMTA published the North Star network only
  as a map inside the 2025 plan. The map is a vector PDF, so its lines are real geometry, and
  `tools/bike-network/north-star-map-trace.py` snaps them back onto DataSF centerlines. A block near the
  edge of a drawn corridor is a judgement the trace made, not something SFMTA stated.
- **{stats['rows_without_id']:,} rows carry no project id** and are dropped.
  **{stats['no_start']:,} projects carry no start date** and sort to the bottom.
- **{stats['listy_rows']:,} project rows list several segments in one `cnn` field** and are
  unpacked. An earlier version of this script read that field as a single key, so those segments
  matched nothing and every count on those rows was wrong.
- **High injury is SFMTA's {MPF_VINTAGE} layer**, kept because the high-injury network is a
  separate product from the bike plan. The {MPF_VINTAGE} bike-priority columns that used to lead
  this page are gone: they pre-dated the 2025 plan and are superseded by it.
- **Locked** means a five-year paving moratorium in force on {today}
  ({stats['locked_segments']:,} segments citywide). The Public Works Director can waive it for
  good cause, with no public step.
- **Dates move.** Public Works states project planning runs on annual funding projections that
  "are very dynamic and can change at any time."
- **How old each source is.** {vintage_plain}
"""
    stable.write_text(path, body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out/street-work")
    ap.add_argument("--cache", action="store_true",
                    help="reuse a previous fetch under <out>/cache")
    ap.add_argument("--update", action="store_true",
                    help="read DataSF from the shared cache (kept current by refresh-socrata.py) "
                         "and re-read the priority layer only when it has changed")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    cache_dir = os.path.join(args.out, "cache") if args.cache else None

    print("Fetching:", file=sys.stderr)
    data = {k: fetch(fxf, floor, cache_dir, args.update) for k, (fxf, floor) in DATASETS.items()}
    mpf = fetch_mpf(cache_dir, args.update)
    # The day the windows and countdowns run from is the day the rows were
    # read, so a run with no new data writes the same files.
    today = max(READ_ON) if args.update else dt.date.today()

    # Say out loud how stale each source is. A join across three datasets is only
    # as current as its oldest arm, and nothing on the page would otherwise show it.
    ages = []
    for name, (fxf, _) in DATASETS.items():
        d = rows_updated_at(fxf)
        if d is None:
            ages.append(f"<code>{fxf}</code> ({name}): update date unavailable")
        else:
            days = (today - d).days
            flag = " &mdash; <strong>stale</strong>" if days > 45 else ""
            ages.append(f"<code>{fxf}</code> ({name}): rows last updated {d}, {days} days ago{flag}")
    vintage = "; ".join(ages) + "."
    vintage_plain = (
        vintage.replace("<code>", "`").replace("</code>", "`")
        .replace("<strong>", "**").replace("</strong>", "**")
        .replace("&mdash;", "—")
    )


    north_star, ns_path = load_north_star()
    if not north_star:
        sys.exit("FAIL: no North Star network artifact. Run tools/bike-network/north-star-map-trace.py "
                 "or tools/bike-network/north-star-index.py first — without it the ask-about list is empty "
                 "and the page would read as 'nothing to ask about'.")
    print(f"  2025 North Star network: {len(north_star):,} street segments from {ns_path}",
          file=sys.stderr)
    ns_grid, ns_vertices = load_north_star_geometry()
    print(f"  2025 North Star geometry: {ns_vertices:,} vertices, for the projects "
          f"btxj-k9uh publishes with no centerline id", file=sys.stderr)
    rows, rows_without_id = build(
        data["projects"], data["bikeways"], data["moratorium"], mpf, north_star, today,
        ns_grid=ns_grid
    )
    by_geometry = [r for r in rows if r["north_star_match"] == "geometry"]
    print(f"  matched by geometry rather than centerline: {len(by_geometry)}", file=sys.stderr)
    # Every failure mode in this system has returned success with the data
    # missing, so the geometry path asserts a floor like every fetch does. It
    # found 27 on 2026-09-06 and the distances are not marginal — 24 of them sit
    # at exactly 0 m — so a run that finds almost none has lost the North Star
    # artifact or the project geometry, and would quietly under-report the
    # ask-about list by a sixth rather than fail.
    if len(by_geometry) < 15:
        sys.exit("FAIL: only %d projects matched the North Star network by geometry; "
                 "expected about 27. Either out/north-star/ is stale or btxj-k9uh "
                 "stopped publishing co_ordinatelinestring." % len(by_geometry))

    # How much of the project side the priority layer actually covers. This is
    # the number that decides whether a blank priority column can be read as
    # "not a priority" — it cannot, and the page says so with this figure.
    project_cnns = set()
    listy_rows = 0
    for r in data["projects"]:
        cnns = parse_cnns(r.get("cnn"))
        project_cnns.update(cnns)
        if (r.get("cnn") or "").strip().startswith("["):
            listy_rows += 1
    mpf_cnns = {c for c in (norm_cnn(r.get("CNN")) for r in mpf) if c}
    matched = project_cnns & mpf_cnns
    if project_cnns and not matched:
        sys.exit(
            "FAIL: not one project segment matched MTA.MPF_Network. The CNN "
            "normalisation on one side has drifted, and an all-blank priority "
            "column would read as 'nothing is a bike priority'."
        )

    stats = {
        "project_rows": len(data["projects"]),
        "projects": len(rows),
        "rows_without_id": rows_without_id,
        "no_start": sum(1 for r in rows if r["start"] is None),
        "locked_segments": len({
            c for r in data["moratorium"]
            for c in parse_cnns(r.get("cnn"))
            if parse_date(r.get("expirationdate"))
            and parse_date(r["expirationdate"]) >= today
        }),
        "listy_rows": listy_rows,
        "project_cnns": len(project_cnns),
        "mpf_cnns": len(mpf_cnns),
        "mpf_matched": len(matched),
        "mpf_pct": 100.0 * len(matched) / len(project_cnns) if project_cnns else 0.0,
    }

    csv_path = os.path.join(args.out, "street-work.csv")
    html_path = os.path.join(args.out, "index.html")
    write_csv(csv_path, rows)
    write_html(html_path, rows, stats, today, vintage)
    md_path = os.path.join(args.out, "street-work.md")
    write_markdown(md_path, rows, stats, today, vintage_plain)

    upcoming = [r for r in rows if r["in_notice_window"]]
    print(
        f"\n{stats['project_rows']:,} rows -> {stats['projects']:,} projects\n"
        f"{len(upcoming):,} start within {EXCAVATOR_NOTICE_DAYS} days\n"
        f"{sum(1 for r in rows if r['segments_north_star'] > 0):,} projects on the 2025 North "
        f"Star network; {sum(1 for r in rows if r['ask_about']):,} of those are still changeable "
        f"and say nothing about bike work\n"
        f"wrote {csv_path}, {html_path} and {md_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
