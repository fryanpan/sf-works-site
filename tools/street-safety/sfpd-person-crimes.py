#!/usr/bin/env python3
"""Citywide SFPD reports from DataSF wg3w-h783: person crimes (assault, robbery, rape, weapons) over the newest 12 months for the "Crime near Muni stops" layer of tools/street-safety/hin-people-map.py, and every report since 2018 by place, year, kind, day and time for the Street Safety map's crime view.

    python3 tools/street-safety/sfpd-person-crimes.py            # read once if there is no copy, else use the copy on disk
    python3 tools/street-safety/sfpd-person-crimes.py --update   # ask DataSF whether rows changed (rowsUpdatedAt); re-read only if so
    python3 tools/street-safety/sfpd-person-crimes.py --refresh  # re-read regardless

Writes data/extract/sfpd-person-crimes/incidents.json ([date, [categories], lon, lat, incident_id] per incident),
all-places.json ([lon, lat, incidents, then incidents by GROUPS, then the day and time cells] for every report of any
category: the baseline, and the map's all-crime heatmap) and meta.json. The day and time cells are a flat list of
[cell, incidents, cell, incidents, ...] for every non-empty cell, where cell = (group index * 7 + weekday) * 6 + period:
weekday is the incident_date's, Sunday 0 (JavaScript's getUTCDay(), the rule the Street Safety map's crash filter
uses), and period is the incident_time's place in PERIODS (the map's TIMES), 5 when the time is missing. So the map can
filter the reports by day and time of day and still split them by group. Bryan asked for the day filter on the crime
view on 2026-11-19, then for one joint day and time choice that applies to crime fully. Bryan asked on 2026-11-18 why the layer showed one neighborhood: it read the
Portola and Visitacion Valley extract alone (data/extract/vvp-crime-fire/). This is the citywide read.

Window: the 365 days ending on the last complete day in the dataset (the day before its newest incident_date), so the
window is the data's, not the wall clock's. Reports are filed days to weeks after the incident, so the newest weeks
undercount.

Counting rules, the ones scripts/vvp-crime-fire.py follows (sources/datasf-public-safety.md): one row is one incident
code on one report. Supplement reports are dropped (the dataset's explainer: failing to filter them "can lead to double
counting"), and so are rows with police_district "Out of SF". Rows are grouped by incident_id, so one incident counts
once and keeps each person-crime category it carries. Categories kept: PERSON_CRIMES. Locations are SFPD's own, the
nearest intersection; a report with no location can't be placed and its count goes in meta.json.

Incremental: --update reads the dataset's rowsUpdatedAt and re-reads the window only when it differs from the one
recorded in meta.json. A failed read keeps the last good copy and records the failure in data/pipeline-state/.
Quality checks run after every read and stop the run before anything is written: incidents >= FLOOR and >= 80% of
the previous copy, per-category floors, a floor for every whole month in the window, the newest incident_date within 14
days before today and not after it, at least PLACE_FLOOR distinct locations, a baseline of at least ALL_FLOOR
incidents, row_id unique, every kept incident with a date in the window and a location inside SF, incident ids unique,
one date, time and place per incident, every weekday at least 10% of the year, every time of day at least
5% of it, and at most 2% with no time. A run with no new rows leaves both files unchanged (lib/stable.py).
all-years.json is the same as all-places.json over every year from 2018-01-01 (the dataset's first day) to the
window's end, with the year added to the front of each cell: ((year - 2018) * 5 + group) * 7 + weekday) * 6 + period.
The Street Safety map reads it so its crime view can filter by year (Bryan, 2026-11-19: "Thought
we would have more than 12 months?"). It is read one calendar year at a time, so a year's query and its cache key stay
fixed. The bounded re-read: when rowsUpdatedAt moves, the years ending within RECENT_DAYS (400) of the window's end are
read again; an older year comes from the cache until the cache is YEAR_MAX_AGE (90) days old, then it is read again,
so a late correction to an old report lands within three months. --refresh re-reads every year. Its checks: every
year present, each whole year at least YEAR_FLOOR incidents and each group over its floor, each year at least 80% of
the last copy's, the year so far over a pro-rata floor, cells that add up to each place's groups, places inside SF,
every time of day at least 5% of each year and at most 2% with no time, and no unknown category of 100 or more.
Registered in pipeline/transportation-update.py as sfpd-crime, ahead of street-safety-map.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.stable import write_json  # noqa: E402

FXF = "wg3w-h783"
MARKER = "socrata:" + FXF + ":person-crimes"
OUT = os.path.join(ROOT, "data", "extract", "sfpd-person-crimes")
CACHE = os.path.join(ROOT, "scratch", "runs", "sfpd-person-crimes", "cache")
PERSON_CRIMES = ("Assault", "Robbery", "Rape", "Weapons Offense", "Weapons Carrying Etc")
SPELLING = {"Weapons Offence": "Weapons Offense"}   # SFPD files a few rows under the other spelling
FLOOR = 5000
CAT_FLOOR = {"Assault": 3000, "Robbery": 400, "Weapons Offense": 200}
MONTH_FLOOR = 250        # incidents in each whole calendar month of the window (about 650 a month in 2025-26)
PLACE_FLOOR = 1500       # distinct report locations (SFPD snaps reports to intersections)
ALL_FLOOR = 50000        # incidents of any category, the baseline
YEARS_FROM = 2018        # the dataset's first year (DataSF wg3w-h783, "2018 to Present")
YEAR_FLOOR = 50000       # incidents in each whole year (62,646 in 2025, the lowest, queried 2026-11-19)
RECENT_DAYS = 400        # on a re-read, the years ending within this many days of the window's end are read again
YEAR_MAX_AGE = 90        # and an older year when its cache is this many days old
SF_BOX = (-122.53, 37.70, -122.35, 37.84)
# Bryan, 2026-11-18: "give hotspots for all crime of all types". Each incident goes to the first group any of its
# categories falls in, in this order; a category in no group is "Other" (warrants, non-criminal, lost property and the like).
GROUPS = [("Violence and weapons", {"Assault", "Robbery", "Rape", "Weapons Offense", "Weapons Offence", "Weapons Carrying Etc",
                                    "Homicide", "Sex Offense", "Human Trafficking (A), Commercial Sex Acts",
                                    "Human Trafficking, Commercial Sex Acts", "Human Trafficking (B), Involuntary Servitude"}),
          ("Theft, burglary and fraud", {"Larceny Theft", "Burglary", "Motor Vehicle Theft", "Motor Vehicle Theft?", "Stolen Property",
                                         "Fraud", "Forgery And Counterfeiting", "Embezzlement"}),
          ("Vandalism and arson", {"Malicious Mischief", "Vandalism", "Arson"}),
          ("Drugs", {"Drug Offense", "Drug Violation"}),
          ("Other", set())]


OTHER_KNOWN = {"Other Miscellaneous", "Warrant", "Non-Criminal", "Lost Property", "Missing Person", "Disorderly Conduct",
               "Recovered Vehicle", "Suspicious Occ", "Miscellaneous Investigation", "Offences Against The Family And Children",
               "Traffic Violation Arrest", "Other Offenses", "Other", "Traffic Collision", "Case Closure", "Courtesy Report",
               "Prostitution", "Vehicle Impounded", "Fire Report", "Civil Sidewalks", "Suicide", "Vehicle Misplaced", "Gambling",
               "Liquor Laws", "Suspicious", "(none)"}


DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
# The map's times of day (site/src/safety-map/state.js TIMES): [id, first hour, hour after the last]; night wraps.
PERIODS = [("am", 6, 9), ("midday", 9, 15), ("pm", 15, 19), ("evening", 19, 22), ("night", 22, 6)]
NO_TIME = len(PERIODS)
CELLS = 7 * (len(PERIODS) + 1)   # cells per group


def period(t):
    """An incident_time "HH:MM" to its index in PERIODS, or NO_TIME when missing or unreadable."""
    try:
        h = int(str(t).split(":")[0])
    except ValueError:
        return NO_TIME
    if not 0 <= h <= 23:
        return NO_TIME
    for i, (_, a, b) in enumerate(PERIODS):
        if (a <= h < b) if a < b else (h >= a or h < b):
            return i
    return NO_TIME


def weekday(d):
    """An ISO date's weekday with Sunday 0, as JavaScript's getUTCDay() counts it."""
    return (dt.date.fromisoformat(d).weekday() + 1) % 7


def group_of(cats):
    for i, (_, g) in enumerate(GROUPS[:-1]):
        if cats & g:
            return i
    return len(GROUPS) - 1


def fail(msg):
    sys.exit("sfpd-person-crimes: check failed: " + msg)


def read(refresh):
    mx = sfdata.fetch(FXF, select="max(incident_date) AS mx", order="mx", floor=1, cache_dir=CACHE, refresh=refresh)
    newest = dt.date.fromisoformat(mx.rows[0]["mx"][:10])
    end = newest - dt.timedelta(days=1)
    start = end - dt.timedelta(days=364)
    cats = ",".join("'%s'" % c for c in PERSON_CRIMES + tuple(SPELLING))
    win = "incident_date between '%sT00:00:00' and '%sT23:59:59'" % (start, end)
    r = sfdata.fetch(FXF, select="row_id,incident_id,incident_date,incident_category,report_type_description,police_district,latitude,longitude",
                     where="%s AND incident_category in (%s)" % (win, cats), floor=FLOOR, cache_dir=CACHE, refresh=refresh)
    if len({x["row_id"] for x in r.rows}) != len(r.rows):
        fail("row_id not unique")
    inc, out_of_sf, unloc = {}, set(), set()
    for x in r.rows:
        if "Supplement" in (x.get("report_type_description") or ""):
            continue
        if x.get("police_district") == "Out of SF":
            out_of_sf.add(x["incident_id"])
            continue
        if not x.get("latitude") or not x.get("longitude"):
            unloc.add(x["incident_id"])
            continue
        lon, lat = round(float(x["longitude"]), 5), round(float(x["latitude"]), 5)
        d = inc.setdefault(x["incident_id"], {"d": x["incident_date"][:10], "c": set(), "x": (lon, lat)})
        if d["d"] != x["incident_date"][:10] or d["x"] != (lon, lat):
            fail("incident %s has rows with different dates or places" % x["incident_id"])
        d["c"].add(SPELLING.get(x["incident_category"], x["incident_category"]))
    unloc -= set(inc)
    rows = [[v["d"], sorted(v["c"]), v["x"][0], v["x"][1], k] for k, v in sorted(inc.items(), key=lambda kv: (kv[1]["d"], kv[0]))]
    # Baseline: every located, non-supplement report of any category, as places with a count, so a reader can see how
    # much of all reported crime is near a stop, not only person crime. Read a calendar year at a time from 2018, the
    # dataset's first year; the 12-month baseline is the window's part of it.
    allinc = read_years(end, refresh)
    win_inc = {k: v for k, v in allinc.items() if str(start) <= v["d"] <= str(end)}
    seen = set(win_inc)
    all_dates = [v["d"] for v in win_inc.values()]
    all_places = places_of(win_inc, lambda v: 0)
    years = list(range(YEARS_FROM, end.year + 1))
    year_places = places_of(allinc, lambda v: int(v["d"][:4]) - YEARS_FROM)
    other = collections.Counter(c or "(none)" for v in win_inc.values() if group_of(v["c"]) == len(GROUPS) - 1 for c in v["c"])
    years_other = collections.Counter(c or "(none)" for v in allinc.values() if group_of(v["c"]) == len(GROUPS) - 1 for c in v["c"])
    u = sfdata.fetch(FXF, select="count(distinct incident_id) AS n", order="n",
                     where=win + " AND latitude IS NULL AND report_type_description NOT LIKE '%Supplement%' AND "
                     "police_district != 'Out of SF'", floor=1, cache_dir=CACHE, refresh=refresh)
    meta = {"source": "DataSF %s, SFPD incident reports 2018 to present" % FXF, "url": "https://data.sfgov.org/d/" + FXF,
            "fetched_on": str(r.fetched_on), "from": str(start), "to": str(end), "incidents": len(rows), "rows_read": len(r.rows),
            "categories": {c: sum(1 for x in rows if c in x[1]) for c in PERSON_CRIMES},
            "dropped_out_of_sf": len(out_of_sf), "unlocated": len(unloc),
            "fields": ["incident_date", "categories", "lon", "lat", "incident_id"],
            "rule": "supplement reports dropped; police_district 'Out of SF' dropped; one incident per incident_id; "
                    "categories " + ", ".join(PERSON_CRIMES),
            "lag_note": "reports are filed days to weeks after the incident, so the newest weeks undercount",
            "newest_incident_date": str(newest), "all_incidents": len(seen), "all_places": len(all_places),
            "all_from": min(all_dates), "all_to": max(all_dates), "groups": [g[0] for g in GROUPS],
            "all_unlocated": int(u.rows[0]["n"]), "other_categories": dict(sorted(other.items(), key=lambda kv: (-kv[1], kv[0]))),
            "all_by_group": {g[0]: sum(p[3 + i] for p in all_places) for i, g in enumerate(GROUPS)},
            "all_by_weekday": {d: sum(n for p in all_places for cell, n in zip(p[-1][::2], p[-1][1::2])
                                      if cell // (len(PERIODS) + 1) % 7 == i) for i, d in enumerate(DAY_NAMES)},
            "all_by_period": {k: sum(n for p in all_places for cell, n in zip(p[-1][::2], p[-1][1::2])
                                     if cell % (len(PERIODS) + 1) == i) for i, k in enumerate([x[0] for x in PERIODS] + ["no time"])},
            "periods": [list(x) for x in PERIODS],
            "all_fields": ["lon", "lat", "incidents"] + [g[0] for g in GROUPS]
                          + ["[(group * 7 + weekday (Sunday 0)) * 6 + period (PERIODS, 5 no time), incidents, ...]"],
            "not_included": "Homicide, Sex Offense and Human Trafficking are other SFPD categories, left out of the person-crime "
                            "definition (incidents.json); the all-category baseline puts them in Violence and weapons"}
    # Every year from 2018, for the Street Safety map's crime view (all-years.json). A cell adds the year to the front:
    # ((year index * groups + group) * 7 + weekday) * 6 + period, year index = year - 2018.
    ycell = len(GROUPS) * CELLS
    pairs = lambda p: zip(p[-1][::2], p[-1][1::2])   # noqa: E731
    meta.update({
        "years": years, "years_from": "%d-01-01" % YEARS_FROM, "years_to": str(end), "years_fetched_on": READ["fetched_on"], "years_cross_year": READ["cross_year"],
        "years_incidents": len(allinc), "years_places": len(year_places),
        "years_by_year": {str(y): sum(n for p in year_places for cell, n in pairs(p) if cell // ycell == i) for i, y in enumerate(years)},
        "years_by_year_group": {str(y): {g[0]: sum(n for p in year_places for cell, n in pairs(p) if cell // ycell == i and cell // CELLS % len(GROUPS) == j)
                                         for j, g in enumerate(GROUPS)} for i, y in enumerate(years)},
        "years_by_year_period": {str(y): {k: sum(n for p in year_places for cell, n in pairs(p) if cell // ycell == i and cell % (len(PERIODS) + 1) == q)
                                          for q, k in enumerate([x[0] for x in PERIODS] + ["no time"])} for i, y in enumerate(years)},
        "years_by_weekday": {d: sum(n for p in year_places for cell, n in pairs(p) if cell // (len(PERIODS) + 1) % 7 == i) for i, d in enumerate(DAY_NAMES)},
        "years_other_categories": dict(sorted(years_other.items(), key=lambda kv: (-kv[1], kv[0]))),
        "years_fields": ["lon", "lat", "incidents"] + [g[0] for g in GROUPS]
                        + ["[(((year - %d) * %d + group) * 7 + weekday (Sunday 0)) * 6 + period (PERIODS, 5 no time), incidents, ...]" % (YEARS_FROM, len(GROUPS))],
        "years_reread": "on --update, the years ending within %d days of the window's end are re-read and older years come "
                        "from the cache until it is %d days old" % (RECENT_DAYS, YEAR_MAX_AGE)})
    return rows, meta, all_places, year_places


# The newest date any year was read, for the multi-year file (read_years sets it), and --refresh's re-read of every year.
READ = {"fetched_on": None}
REFRESH_ALL = [False]


def read_years(end, refresh):
    """Every located, non-supplement, in-SF report from 2018-01-01 to `end`, one dict per incident_id.

    One query per calendar year, its key fixed (the whole year), so a past year's cache is reused. With `refresh`
    (a re-read because rowsUpdatedAt moved) the years that end within RECENT_DAYS of `end` are re-read; an older year
    is re-read when its cache is YEAR_MAX_AGE days old, so a late correction still lands. --refresh re-reads every year."""
    out, dates = {}, []
    READ["cross_year"] = 0
    # Newest year first: an incident whose rows SFPD has moved into another year (or that spans two) counts once, in
    # the newest year's read, since an older year may come from a cache up to YEAR_MAX_AGE days old.
    for y in range(end.year, YEARS_FROM - 1, -1):
        recent = (end - dt.date(y, 12, 31)).days < RECENT_DAYS
        where = ("incident_date between '%d-01-01T00:00:00' and '%d-12-31T23:59:59' AND latitude IS NOT NULL AND "
                 "(report_type_description IS NULL OR report_type_description NOT LIKE '%%Supplement%%') AND "
                 "(police_district IS NULL OR police_district != 'Out of SF')" % (y, y))
        # The year so far has no row floor here (a new year's first days hold few reports); check_years floors it pro rata.
        r = sfdata.fetch(FXF, select="incident_id,incident_date,incident_time,incident_category,latitude,longitude", where=where,
                         floor=YEAR_FLOOR if dt.date(y, 12, 31) <= end else 1, cache_dir=CACHE,
                         refresh=REFRESH_ALL[0] or (refresh and recent), max_age_days=None if recent else YEAR_MAX_AGE)
        dates.append(r.fetched_on)
        year = {}
        for x in r.rows:
            d0 = x["incident_date"][:10]
            if d0 > str(end) or not x.get("longitude"):
                continue   # the newest day is not yet complete; a row with no longitude can't be placed
            x0 = (round(float(x["longitude"]), 5), round(float(x["latitude"]), 5))
            d = year.setdefault(x["incident_id"], {"x": x0, "d": d0, "t": x.get("incident_time"), "c": set()})
            if d["d"] != d0 or d["x"] != x0 or d["t"] != x.get("incident_time"):   # the cells assume one per incident
                fail("baseline incident %s has rows with different dates, times or places" % x["incident_id"])
            d["c"].add(x.get("incident_category") or "")
        for k, v in year.items():
            if k in out:
                READ["cross_year"] += 1
            else:
                out[k] = v
    READ["fetched_on"] = str(max(dates))
    return out


def places_of(incidents, year_index):
    """[lon, lat, incidents, incidents by GROUPS, cells] per place, sorted. A cell is
    ((year_index(incident) * groups + group) * 7 + weekday) * 6 + period, flat as [cell, incidents, ...]."""
    places, cells = {}, {}
    for v in incidents.values():
        pl = places.setdefault(v["x"], [0] * (1 + len(GROUPS)))
        g = group_of(v["c"])
        pl[0] += 1
        pl[1 + g] += 1
        c = cells.setdefault(v["x"], collections.Counter())
        c[((year_index(v) * len(GROUPS) + g) * 7 + weekday(v["d"])) * (len(PERIODS) + 1) + period(v["t"])] += 1
    return [[k[0], k[1]] + n + [[x for cell in sorted(cells[k]) for x in (cell, cells[k][cell])]] for k, n in sorted(places.items())]


def check(rows, meta, prev, all_places, today=None):
    today = today or dt.date.today()
    newest = dt.date.fromisoformat(meta["newest_incident_date"])
    if newest > today or (today - newest).days > 14:
        fail("newest incident_date %s is not within 14 days before %s" % (newest, today))
    for c, f in CAT_FLOOR.items():
        if meta["categories"].get(c, 0) < f:
            fail("only %d %s incidents" % (meta["categories"].get(c, 0), c))
    start, end = dt.date.fromisoformat(meta["from"]), dt.date.fromisoformat(meta["to"])
    by_month = {}
    for x in rows:
        by_month[x[0][:7]] = by_month.get(x[0][:7], 0) + 1
    m = dt.date(start.year, start.month, 1)
    while m <= end:
        nxt = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        if m >= start and nxt - dt.timedelta(days=1) <= end and by_month.get(m.isoformat()[:7], 0) < MONTH_FLOOR:
            fail("only %d incidents in %s" % (by_month.get(m.isoformat()[:7], 0), m.isoformat()[:7]))
        m = nxt
    if len({(x[2], x[3]) for x in rows}) < PLACE_FLOOR:
        fail("only %d distinct report locations" % len({(x[2], x[3]) for x in rows}))
    if sum(p[2] for p in all_places) < ALL_FLOOR:
        fail("baseline has only %d incidents" % sum(p[2] for p in all_places))
    if not (meta["from"] <= meta["all_from"] and meta["all_to"] <= meta["to"]):
        fail("baseline dates %s to %s outside %s to %s" % (meta["all_from"], meta["all_to"], meta["from"], meta["to"]))
    if prev and prev.get("all_incidents") and meta["all_incidents"] < 0.8 * prev["all_incidents"]:
        fail("baseline %d incidents against %d in the last copy" % (meta["all_incidents"], prev["all_incidents"]))
    ng = len(GROUPS)
    for p in all_places:
        if sum(p[3:3 + ng]) != p[2] or not (SF_BOX[0] < p[0] < SF_BOX[2] and SF_BOX[1] < p[1] < SF_BOX[3]):
            fail("baseline place %s: groups don't sum to its count, or it lies outside SF" % p[:3])
        # The day-of-week cells hold every incident once: each group's cells add up to the group, and no cell is empty.
        cells = p[3 + ng]
        by_g = [0] * ng
        for cell, n in zip(cells[::2], cells[1::2]):
            if not (0 <= cell < ng * CELLS) or n <= 0:
                fail("baseline place %s: day cell %s holds %s" % (p[:3], cell, n))
            by_g[cell // CELLS] += n
        if by_g != p[3:3 + ng] or len(cells[::2]) != len(set(cells[::2])):
            fail("baseline place %s: day-of-week cells don't add up to its groups" % p[:3])
    # Every weekday holds a fair share of a year's reports: a date field read as the wrong type would pile them on one day.
    per = meta["all_by_period"]
    if min(per[x[0]] for x in PERIODS) < 0.05 * meta["all_incidents"] or per["no time"] > 0.02 * meta["all_incidents"]:
        fail("reports by time of day %s: a period under 5%% or over 2%% with no time" % per)
    days = meta["all_by_weekday"]
    if min(days.values()) < 0.1 * meta["all_incidents"]:
        fail("reports by weekday %s: a day under 10%% of the year" % days)
    # A category in no group lands in Other unseen, so a new or respelled one big enough to matter stops the run.
    for c, n in meta["other_categories"].items():
        if c not in OTHER_KNOWN and n >= 100:
            fail("category %r (%d incidents) is in no group: add it to GROUPS or OTHER_KNOWN" % (c, n))
    for g, f in (("Violence and weapons", 5000), ("Drugs", 2000), ("Vandalism and arson", 1500), ("Theft, burglary and fraud", 15000), ("Other", 10000)):
        if meta["all_by_group"].get(g, 0) < f:
            fail("baseline has only %d %s incidents" % (meta["all_by_group"].get(g, 0), g))
    if len(rows) < FLOOR:
        fail("only %d incidents" % len(rows))
    if prev and len(rows) < 0.8 * prev["incidents"]:
        fail("%d incidents against %d in the last copy" % (len(rows), prev["incidents"]))
    if len({x[4] for x in rows}) != len(rows):
        fail("incident ids not unique")
    for x in rows:
        if not (meta["from"] <= x[0] <= meta["to"]):
            fail("date %s outside %s to %s" % (x[0], meta["from"], meta["to"]))
        if not (SF_BOX[0] < x[2] < SF_BOX[2] and SF_BOX[1] < x[3] < SF_BOX[3]):
            fail("incident %s placed outside SF" % x[4])
        if not x[1] or set(x[1]) - set(PERSON_CRIMES):
            fail("incident %s has categories %s" % (x[4], x[1]))


# Each whole year's floor per group, a little over half the lowest whole year from 2018 to 2025 (read 2026-11-19:
# violence 8,273 in 2025, theft 27,428 in 2025, vandalism 4,842 in 2025, drugs 826 in 2021, other 17,699 in 2020).
YEAR_GROUP_FLOOR = {"Violence and weapons": 5000, "Theft, burglary and fraud": 15000, "Vandalism and arson": 2500, "Drugs": 450, "Other": 10000}


def check_years(meta, year_places, prev):
    """The multi-year file (all-years.json): every year from 2018 present and full, cells that add up, places in SF."""
    end = dt.date.fromisoformat(meta["years_to"])
    years = list(range(YEARS_FROM, end.year + 1))
    if meta["years"] != years:
        fail("years %s, expected %s" % (meta["years"], years))
    ng, ycell = len(GROUPS), len(GROUPS) * CELLS
    total = 0
    for p in year_places:
        if sum(p[3:3 + ng]) != p[2] or not (SF_BOX[0] < p[0] < SF_BOX[2] and SF_BOX[1] < p[1] < SF_BOX[3]):
            fail("year place %s: groups don't sum to its count, or it lies outside SF" % p[:3])
        cells, by_g = p[3 + ng], [0] * ng
        for cell, n in zip(cells[::2], cells[1::2]):
            if not (0 <= cell < len(years) * ycell) or n <= 0:
                fail("year place %s: cell %s holds %s" % (p[:3], cell, n))
            by_g[cell // CELLS % ng] += n
        if by_g != p[3:3 + ng] or len(cells[::2]) != len(set(cells[::2])):
            fail("year place %s: cells don't add up to its groups" % p[:3])
        total += p[2]
    if total != meta["years_incidents"] or sum(meta["years_by_year"].values()) != total:
        fail("year places hold %d incidents, meta %d, by year %d" % (total, meta["years_incidents"], sum(meta["years_by_year"].values())))
    for y in years:
        n, whole = meta["years_by_year"][str(y)], dt.date(y, 12, 31) <= end
        # The year so far: at least 60% of a whole year's floor, pro rata (reports trail the incident by weeks).
        floor = YEAR_FLOOR if whole else 0.6 * YEAR_FLOOR * ((end - dt.date(y, 1, 1)).days + 1) / 365
        if n < floor:
            fail("%d has %d incidents, under %d" % (y, n, floor))
        if whole:
            for g, f in YEAR_GROUP_FLOOR.items():
                if meta["years_by_year_group"][str(y)][g] < f:
                    fail("%d has only %d %s incidents" % (y, meta["years_by_year_group"][str(y)][g], g))
        if prev and prev.get("years_by_year", {}).get(str(y)) and whole and n < 0.8 * prev["years_by_year"][str(y)]:
            fail("%d has %d incidents against %d in the last copy" % (y, n, prev["years_by_year"][str(y)]))
        per = meta["years_by_year_period"][str(y)]
        if n >= 5000 and (min(per[x[0]] for x in PERIODS) < 0.05 * n or per["no time"] > 0.02 * n):   # a new year's first days are too few to judge
            fail("%d by time of day %s: a period under 5%% or over 2%% with no time" % (y, per))
    if meta["years_cross_year"] > 0.001 * total:
        fail("%d incidents sit in two years' reads" % meta["years_cross_year"])
    if min(meta["years_by_weekday"].values()) < 0.1 * total:
        fail("reports by weekday %s: a day under 10%% of the years" % meta["years_by_weekday"])
    if prev and prev.get("years_incidents") and total < 0.8 * prev["years_incidents"]:
        fail("%d incidents over the years against %d in the last copy" % (total, prev["years_incidents"]))
    for c, n in meta["years_other_categories"].items():
        if c not in OTHER_KNOWN and n >= 100:
            fail("category %r (%d incidents since 2018) is in no group: add it to GROUPS or OTHER_KNOWN" % (c, n))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    mpath, ipath = os.path.join(OUT, "meta.json"), os.path.join(OUT, "incidents.json")
    prev = json.load(open(mpath)) if os.path.exists(mpath) and os.path.exists(ipath) else None
    older = prev
    if prev and not (os.path.exists(os.path.join(OUT, "all-places.json")) and prev.get("groups") == [g[0] for g in GROUPS]
                     and "all_by_period" in prev and "years" in prev and os.path.exists(os.path.join(OUT, "all-years.json"))):
        prev = None   # an older copy without the grouped baseline, its days or its years: read again
    if prev and not (a.update or a.refresh):
        print("sfpd-person-crimes: using the copy read %s (%d incidents)" % (prev["fetched_on"], prev["incidents"]))
        return
    try:
        stamp = sfdata.metadata(FXF)["rows_updated_ts"]
        if prev and a.update and not a.refresh and prev.get("rows_updated_ts") == stamp:
            pipeline_state.record(MARKER, "unchanged", version=str(stamp), detail="rowsUpdatedAt %s" % stamp)
            print("sfpd-person-crimes: rowsUpdatedAt unchanged (%s); nothing to do" % stamp)
            return
        REFRESH_ALL[0] = a.refresh
        rows, meta, all_places, year_places = read(refresh=bool(prev) or a.refresh)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if not prev:
            raise
        pipeline_state.record(MARKER, "failed", detail="re-read failed, copy of %s kept: %s" % (prev["fetched_on"], exc))
        print("sfpd-person-crimes: re-read failed (%s); keeping the copy read %s" % (exc, prev["fetched_on"]))
        return
    # An older copy rebuilt from the cache holds the rows of its own read, so it keeps that read's marker; otherwise
    # --update would take today's marker as already read and skip the next real re-read.
    rebuilt = older and not prev and not a.refresh and meta["fetched_on"] == older.get("fetched_on")
    meta["rows_updated_ts"] = older["rows_updated_ts"] if rebuilt and older.get("rows_updated_ts") else stamp
    check(rows, meta, prev, all_places)
    check_years(meta, year_places, prev)
    os.makedirs(OUT, exist_ok=True)
    write_json(ipath, rows, separators=(",", ":"))
    write_json(os.path.join(OUT, "all-places.json"), all_places, separators=(",", ":"))
    write_json(os.path.join(OUT, "all-years.json"), year_places, separators=(",", ":"))
    write_json(mpath, meta, indent=1)
    if a.update:
        pipeline_state.record(MARKER, "changed", version=str(stamp), detail="%d incidents %s to %s" % (len(rows), meta["from"], meta["to"]))
    print(json.dumps({k: meta[k] for k in ("from", "to", "incidents", "rows_read", "categories", "unlocated", "dropped_out_of_sf",
                                           "years_from", "years_to", "years_incidents", "years_places", "years_by_year")}))


if __name__ == "__main__":
    main()
