#!/usr/bin/env python3
"""How often Muni comes at every stop: scheduled departures per hour on a weekday in the morning peak, midday and evening, from SFMTA's GTFS feed.

    tools/muni/muni-frequency.py            # write out/full-map/muni-stops.json from the held feed
    tools/muni/muni-frequency.py --check    # run the output checks only

For the full access map. Reads the feed tools/muni/muni-gtfs.py
holds in .cache/muni-gtfs/ and keeps current with --update; this script fetches
nothing, so it is a build step that reruns when that zip changes.

THE DAY. muni-gtfs.py's service day: the last Wednesday inside the feed's
calendar, with the services calendar.txt and calendar_dates.txt run then. It
depends only on the feed, so a rerun on a later date writes the same file.

THE PERIODS are SFMTA's own: "Time Periods are generally: AM - 7 to 9 a.m.;
Midday - 10 a.m. to 2 p.m.; PM - 4 to 6 p.m.; Evening - 8 to 10 p.m."
(SFMTA, Service Modification Proposals as of Feb. 26, 2010, notes to each
table, archives.sfmta.com/cms/rbudgjan2010/documents/Service_Mod_Details_2-23-2010forpdf.pdf).
A period includes its start minute and excludes its end.

WHAT IS COUNTED. A departure is a stop_time on a trip that runs on the day,
at a stop a rider can board (not the trip's last stop, where nobody boards),
timed by departure_time. Per stop and period: departures per hour, all routes
together (tph), and the most of any one route (route_tph). A headway is
60 / tph minutes, so "every 5 minutes" means 12 or more departures an hour.
Stops are GTFS stops: one per side of the street, so each direction is its
own stop, as SFMTA's stop list counts them.

REPRODUCED. SFMTA's route pages list weekday service frequency by Morning,
Midday and Evening, undated (read 2026-10-23). The `published` block
recomputes a route's headway at a named stop from the feed, in the more
frequent direction, against SFMTA's figure. The 1 California's midday, every
10 minutes west of Presidio Avenue and every 5 east of it
(sfmta.com/routes/1-california), is the reproduction, and a check fails if
the feed is more than PUBLISHED_TOL_MIN off. Three more rows are printed and
kept for comparison only, because they do not match: the 14R's morning (6
north of Mission & Lowell, 10 south, against the feed's 5 inbound at both, 10
outbound) and the 22 Fillmore's morning (7, against 5.7). SFMTA's pages are
undated and may predate the August 2026 signup, and their periods are not
defined; their Evening is not SFMTA's 2010 8 to 10 p.m. (the 1 is every 5 east
of Presidio on the page, every 11 to 12 in the feed 8 to 10 p.m.).

A STALE FEED WARNS, IT DOES NOT FAIL. SFMTA kept serving the feed whose
calendar ends 2026-08-28 into October 2026 (Fable review, 2026-10-23), so a
service change since then is invisible here. Every run prints a warning when
the feed's calendar ended more than STALE_DAYS before today; the output is
unchanged, because the minutes are still a real schedule, just an old one.

Writes out/full-map/muni-stops.json: the feed's markers, SFMTA's licence
notice (term 12, word for word from the zip), the periods, and per stop
[stop_id, name, lon, lat, routes, tph per period, route_tph per period].
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import importlib.util
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib.quality import Each, Table, read_json, run  # noqa: E402
from lib.stable import write_json  # noqa: E402

G = paths.load("muni-gtfs.py")

OUT_REL = "out/full-map/muni-stops.json"
# SFMTA's periods (see THE PERIODS): name -> (start minute, end minute).
PERIODS = {"am": (7 * 60, 9 * 60), "midday": (10 * 60, 14 * 60), "evening": (20 * 60, 22 * 60)}
PERIODS_SOURCE = ("SFMTA, Service Modification Proposals as of Feb. 26, 2010, table notes: \"Time Periods are "
                  "generally: AM - 7 to 9 a.m.; Midday - 10 a.m. to 2 p.m.; PM - 4 to 6 p.m.; Evening - 8 to 10 p.m.\" "
                  "https://archives.sfmta.com/cms/rbudgjan2010/documents/Service_Mod_Details_2-23-2010forpdf.pdf")
# SFMTA's route pages, read 2026-10-23 (see REPRODUCED). check: the reproduction, which fails the build if off.
PUBLISHED = [
    {"route": "1", "stopName": "California St & 6th Ave", "period": "midday", "headwayMin": 10, "check": True,
     "where": "west of Presidio Avenue", "source": "https://www.sfmta.com/routes/1-california"},
    {"route": "1", "stopName": "Sacramento St & Fillmore St", "period": "midday", "headwayMin": 5, "check": True,
     "where": "east of Presidio Avenue", "source": "https://www.sfmta.com/routes/1-california"},
    {"route": "14R", "stopName": "Mission St & 16th St", "period": "am", "headwayMin": 6, "check": False,
     "where": "north of Mission & Lowell (short route)", "source": "https://www.sfmta.com/routes/14r-mission-rapid"},
    {"route": "14R", "stopName": "Mission St & Geneva Ave", "period": "am", "headwayMin": 10, "check": False,
     "where": "south of Mission & Lowell (long route)", "source": "https://www.sfmta.com/routes/14r-mission-rapid"},
    {"route": "22", "stopName": "Fillmore St & Haight St", "period": "am", "headwayMin": 7, "check": False,
     "where": "whole route", "source": "https://www.sfmta.com/routes/22-fillmore"},
]
PUBLISHED_TOL_MIN = 0.5


def tph(n, period):
    lo, hi = PERIODS[period]
    return round(n * 60.0 / (hi - lo), 2)


def build(root=ROOT):
    path = G.zip_path(root)
    if not os.path.exists(path):
        raise SystemExit("no Muni feed at %s; run tools/muni/muni-gtfs.py --update first" % path)
    meta = G.read_meta(root) or {}
    with zipfile.ZipFile(path) as zf:
        day, services, first, last = G.service_day(zf)
        notice = G.licence_notice(zf)
        routes = {r["route_id"]: r for r in G.rows(zf, "routes.txt")}
        stops = {s["stop_id"]: s for s in G.rows(zf, "stops.txt")}
        on = set(services)
        trip_route = {t["trip_id"]: t["route_id"] for t in G.rows(zf, "trips.txt") if t["service_id"] in on}
        # Each trip's stop times, so its last stop (no boarding) can be dropped.
        last_seq = {}
        times = []
        for st in G.rows(zf, "stop_times.txt"):
            tid = st["trip_id"]
            if tid not in trip_route:
                continue
            seq = int(st["stop_sequence"])
            m = G.minutes(st.get("departure_time") or st["arrival_time"])
            times.append((tid, seq, st["stop_id"], m))
            if seq > last_seq.get(tid, -1):
                last_seq[tid] = seq
    count = collections.defaultdict(lambda: collections.Counter())      # stop -> period -> n
    by_route = collections.defaultdict(lambda: collections.Counter())   # (stop, route) -> period -> n
    served = collections.defaultdict(set)
    for tid, seq, sid, m in times:
        if seq == last_seq[tid] or m is None:
            continue
        rid = trip_route[tid]
        served[sid].add(rid)
        for p, (lo, hi) in PERIODS.items():
            # A trip past midnight carries times over 24:00; the periods are all before it.
            if lo <= m < hi:
                count[sid][p] += 1
                by_route[(sid, rid)][p] += 1
    rows = []
    for sid in sorted(served, key=lambda s: (len(s), s)):
        s = stops[sid]
        best = {p: max(by_route[(sid, r)][p] for r in served[sid]) for p in PERIODS}
        rows.append([sid, s["stop_name"], round(float(s["stop_lon"]), 6), round(float(s["stop_lat"]), 6),
                     sorted(routes[r]["route_short_name"] for r in served[sid]),
                     {p: tph(count[sid][p], p) for p in PERIODS},
                     {p: tph(best[p], p) for p in PERIODS}])
    published = []
    name_of = {r["route_short_name"]: rid for rid, r in routes.items()}
    for want in PUBLISHED:
        rid = name_of.get(want["route"])
        hits = [sid for sid in served if stops[sid]["stop_name"] == want["stopName"] and rid in served[sid]]
        lo, hi = PERIODS[want["period"]]
        got = []
        for sid in sorted(hits):
            n = by_route[(sid, rid)][want["period"]]
            got.append({"stopId": sid, "departures": n, "headwayMin": round((hi - lo) / n, 1) if n else None})
        best = min((g["headwayMin"] for g in got if g["headwayMin"]), default=None)
        published.append(dict(want, feed=got, feedHeadwayMin=best))
    out = {
        "source": "SFMTA GTFS Transit Data, %s, linked from %s" % (G.FEED_URL, G.FEED_PAGE),
        "notice": notice,
        "feed": {"lastModified": meta.get("lastModified"), "sha256": (meta.get("sha256") or "")[:16],
                 "calendarFrom": first.isoformat(), "calendarTo": last.isoformat(),
                 "serviceDate": day.isoformat(), "services": services},
        "periods": {p: [G.hhmm(lo), G.hhmm(hi)] for p, (lo, hi) in PERIODS.items()},
        "periodsSource": PERIODS_SOURCE,
        "method": "Scheduled departures per hour at each boardable GTFS stop on the service day, every route "
                  "together (tph) and the busiest single route (route_tph); a trip's last stop is not counted. "
                  "Headway is 60 / tph minutes.",
        "columns": ["stop_id", "name", "lon", "lat", "routes", "tph", "route_tph"],
        "published": published,
        "stops": rows,
    }
    os.makedirs(os.path.join(root, os.path.dirname(OUT_REL)), exist_ok=True)
    write_json(os.path.join(root, OUT_REL), out, separators=(",", ":"))
    return out


def checks(root=ROOT):
    def stops(r):
        d = read_json(r, OUT_REL)
        return None if d is None else [dict(zip(d["columns"], s)) for s in d["stops"]]

    def published(r):
        d = read_json(r, OUT_REL)
        return None if d is None else d["published"]

    def in_sf(s):
        x, y = s["lon"], s["lat"]
        return None if G.BBOX[0] <= x <= G.BBOX[2] and G.BBOX[1] <= y <= G.BBOX[3] else "%s outside SF" % s["stop_id"]

    def sane(s):
        bad = [p for p in PERIODS if not 0 <= s["route_tph"][p] <= s["tph"][p] <= 200]
        return ("%s: route_tph above tph or out of range in %s" % (s["stop_id"], bad)) if bad else None

    def matches(p):
        if not p["check"]:
            return None
        if p["feedHeadwayMin"] is None:
            return "no %s departures at %s in the feed" % (p["route"], p["stopName"])
        if abs(p["feedHeadwayMin"] - p["headwayMin"]) > PUBLISHED_TOL_MIN:
            return "%s at %s: feed %s against SFMTA's %s min" % (p["route"], p["stopName"], p["feedHeadwayMin"],
                                                                 p["headwayMin"])
        return None

    return [
        Table("muni-stops", stops, floor=2500, max_drop=0.30, key="stop_id",
              required=["stop_id", "name", "lon", "lat", "routes"]),
        Each("muni-stops/in-sf", stops, in_sf, "every stop inside San Francisco's bounding box"),
        Each("muni-stops/tph", stops, sane, "0 <= busiest route's tph <= the stop's tph <= 200"),
        Each("muni-stops/published", published, matches,
             "the 1 California's midday headway within %g minute of SFMTA's route page" % PUBLISHED_TOL_MIN),
    ]


STALE_DAYS = 14


def stale_warning(feed, today=None):
    """A warning line when the feed's calendar ended more than STALE_DAYS before today, else None."""
    import datetime as dt
    today = today or dt.date.today()
    end = dt.date.fromisoformat(feed["calendarTo"])
    gap = (today - end).days
    if gap > STALE_DAYS:
        return ("  WARNING: SFMTA's feed calendar ended %s, %d days ago; service changes since then are not in "
                "the map (tools/muni/muni-gtfs.py --update fetches a newer feed when SFMTA publishes one)" % (end, gap))
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="run the output checks only")
    a = ap.parse_args()
    if not a.check:
        out = build()
        am = [s[5]["am"] for s in out["stops"]]
        print("  %d stops served on %s; %d at 12+ departures an hour 7-9 AM, %d at 6+" % (
            len(am), out["feed"]["serviceDate"], sum(x >= 12 for x in am), sum(x >= 6 for x in am)))
        for p in out["published"]:
            print("  published%s: %s at %s, %s, SFMTA %s min; feed %s (by direction %s)" % (
                "" if p["check"] else " (comparison only)", p["route"], p["stopName"], p["period"], p["headwayMin"],
                p["feedHeadwayMin"], [f["headwayMin"] for f in p["feed"]]))
    blob = read_json(ROOT, OUT_REL)
    warn = blob and stale_warning(blob["feed"])
    if warn:
        print(warn)
    results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
