#!/usr/bin/env python3
"""Telraam citizen traffic counters in San Francisco: every segment that reported in the last 12 months, its hourly counts, and one rush-hour figure per segment in the unit of tools/street-safety/hin-cut-through.py (two-way motor vehicles in the busier weekday peak hour), with the days a blind or failing camera reported dropped.

    TELRAAM_API_KEY=... python3 tools/street-safety/telraam-sf.py --update   # the 12 months to today: fetch what moved, summarise
    python3 tools/street-safety/telraam-sf.py --offline                      # re-summarise the window segments.json holds, cache only
    python3 tools/street-safety/telraam-sf.py --offline --end 2026-11-18     # the same for a named window end

The Street Safety map (sf-works.org/transportation/street-safety) reads it through
tools/street-safety/hin-cut-through.py, so it is an updater: registered as the "telraam" source step in
pipeline/transportation-update.py, with its checks in scripts/transportation-quality.py. Interval: weekly (the step's
minimum days between runs is 7, and the freshness check ages it from there).

INCREMENTAL. Telraam has no change marker, so the re-read is bounded. The window is the 365 days to END (today with
--update). Hourly reports are cached per segment in calendar chunks of three months starting 1 February, May, August
and November; a chunk that ended before END is closed and never re-read. The open chunk, the one holding END, is
re-read once per END and cached as <chunk start>_<END>.json, so a second run the same day reads nothing. Snapshots are
taken every 14 days from 2025-11-18, so each is read once. A read that fails, or a read that needs the API with no key
set, keeps the last good segments.json, records "telraam:segments" as failed in data/pipeline-state/, and exits 0,
which the orchestrator reports as a refresh failure.

The key is read from TELRAAM_API_KEY at call time and never written anywhere. Only read-only calls are made, at most
one a second: POST /v1/reports/traffic_snapshot (segments in an area at one hour) and POST /v1/reports/traffic
(hourly counts for one segment, at most 3 months a call). Source notes: sources/telraam.md.

FINDING THE SEGMENTS. Telraam has no list of segments by area with their active dates, so the script takes the
hourly snapshot of the SF bounding box at 20:00 UTC (noon Pacific in winter, 1 pm in summer) every 14 days, and keeps
every segment that appears in any snapshot. A counter that ran for less than two weeks between snapshots can be
missed.

RULES (sources/telraam.md has why).
  Motor vehicles = car + heavy + night, both directions. SFMTA's tube counts count every motor vehicle, so both
  Telraam vehicle classes are kept. "night" is the S2 camera's count of vehicles by their lights in the dark hours,
  when car and heavy read 0; a winter evening peak (5 pm and 6 pm from November to February) is dark, and leaving it
  out would read those evenings as nearly empty. Telraam's counts are already scaled up for the share of the hour the
  camera was counting ("uptime"); an hour with uptime under 0.5 is dropped, Telraam's advice.
  Peak hour: the busier of the morning (hours starting 7 and 8 am) and evening (4, 5 and 6 pm) peaks, local time, on a
  Tuesday to Thursday that is not a holiday (holidays() below), SFMTA's AM PEAK (7-9AM) and PM PEAK (4-7PM) windows
  as hin-cut-through.py reads them. A day counts only when both morning hours and at least two of the three evening
  hours pass the uptime test.
  Blind cameras. A camera can report full uptime and see nothing, or fade as its window fogs or its view is blocked.
    A day also needs two of the four midday hours (10 am to 2 pm) to pass the uptime test; its midday level is their
    mean car + heavy an hour. Midday is daylight all year, so the level tests below do not move when the clocks change
    and the 5 and 6 pm hours go into or out of the dark.
    1. Level changes. The midday levels are split at a sustained change of level: binary segmentation on medians,
       each side at least SPLIT_MIN days, splitting where the lower side's median is under LEVEL_DROP of the higher's.
       A run whose median is under LEVEL_DROP of the upper-half median of all the days is dropped, and its dates are
       kept in `split`. So a camera that went dark from May to October keeps its working months.
    1b. Outages. OUTAGE_MIN or more days in a row (no gap of more than a week between them), in what is left, whose midday level is under LEVEL_DROP of
       the upper-half median are dropped too and kept in `split`: a split leaves SPLIT_MIN days a side, so it misses an
       outage in the middle of the series.
    2. Dead days. In what is left, a day is dead when nothing at all was counted (every mode zero in every valid
       hour), its peak is under DEAD_SHARE of the upper-half median peak, or its midday level is under DEAD_SHARE of
       the upper-half median midday level (a camera that cannot see the street in daylight that day). Dead days are
       dropped.
    3. A segment fails when more than MAX_DEAD of its remaining days were dead, or when `night` exceeds car + heavy in
       the midday hours of its valid days, which fits a camera that cannot see the street in daylight.
    4. `peak_q1` is kept, and a segment whose lower quartile is under half its median is flagged `spread`.
  Seasons. The segment's figure is the median over its valid days. Night counts lift winter evenings (sources/
  telraam.md), so a segment needs at least MIN_SEASON_DAYS valid days in each of two seasons (December to February,
  March to May, June to August, September to November). One with no valid day from March to October is kept but
  flagged `winter only`, since its evening peak may be read in the dark, and the two-season test does not apply to it.
  `peak_daylight` is the median over April to September, when 4 to 7 pm is light, beside the all-year `peak`; the
  `night` count reads about 1.5 times the daylight count at 5 and 6 pm, so hin-cut-through.py uses `peak_daylight`
  where a segment has one.
  Full day: only on valid days where all 24 hours pass the uptime test (S2 cameras), every hour's vehicles summed.
  `peak_share` is the median of the day's peak over its total on those days, and `daily` is the peak over that
  share, so the day and the peak hour rest on the same days' shape. Daylight-only cameras have no full day, and
  hin-cut-through.py turns their peak hour into a day with the block's own share instead.
  One direction: `car_lft` and `car_rgt` are the cars each way over every valid hour and `side_share` the smaller
  side's share of them. A segment whose smaller side is under ONE_SIDE of its cars is flagged `one side`: the camera
  sees one direction only. That is right on a one-way street (Oak St reads 99% one way) and wrong on a two-way one,
  and this script has no street centerline, so hin-cut-through.py, which does, fails a `one side` counter on any block
  that is not a one-way street with no carriageway beside it.
  A segment is kept when it has at least MIN_DAYS valid days and fails none of the above.

OUTPUT: data/extract/telraam/segments.json, segments sorted by id: id, geometry (lon/lat line), first and last valid
day, valid days, median peak hour with its quartiles, the daylight-months peak with its first and last day, the share of peak hours that were the
evening's, full-day figures, the cars each way and the smaller side's share, the days dropped and why, flags, failures, and kept. No run stamps.
Raw API replies stay in scratch/runs/telraam/ (gitignored).

Checks (stop on failure): every snapshot answers with status 200; at least 10 segments found; every report call
answers 200; every kept segment has a geometry; hourly rows carry the fields used; at least 20 segments kept.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import http.client
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
from lib.stable import write_text  # noqa: E402
from lib import pipeline_state  # noqa: E402

SCR = ROOT / "scratch"
if not (SCR / "runs").exists():  # a worktree reads the main checkout's gitignored scratch/
    SCR = Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()).parent / "scratch"
RUNS = SCR / "runs/telraam"
OUT = ROOT / "data/extract/telraam/segments.json"
MARKER = "telraam:segments"
API = "https://telraam-api.net/v1"
BBOX = "-122.52,37.70,-122.35,37.84"     # San Francisco's land area; the join to SF centerlines drops anything outside
SNAP_EPOCH = dt.date(2025, 11, 18)        # snapshots fall every 14 days from the first run's window start
LA = ZoneInfo("America/Los_Angeles")
AM, PM, MIDDAY = (7, 8), (16, 17, 18), (10, 11, 12, 13)
MIN_UPTIME, MIN_DAYS = 0.5, 20
SPLIT_MIN, LEVEL_DROP = 10, 0.5           # a level change: at least 10 days a side, the lower under half the higher
DEAD_SHARE, MAX_DEAD = 0.25, 0.10         # a dead day peaks under 25% of the upper-half median; fail above 10% dead
OUTAGE_MIN = 5                            # this many low days in a row, inside a working stretch, are an outage
MIN_SEASON_DAYS = 5
ONE_SIDE = 0.02                           # a smaller side under 2% of the cars: the camera sees one direction
DAYLIGHT_MONTHS = range(4, 10)            # April to September: 4 to 7 pm is before sunset
LIGHT_MONTHS = range(3, 11)               # March to October: a segment with none of these is winter only


class NeedsKey(Exception):
    pass


def check(ok, msg):
    if not ok:
        sys.exit("CHECK FAILED: " + msg)
    print("ok  " + msg, file=sys.stderr)


_last = [0.0]


def post(path, body, cache):
    """POST to the Telraam API unless the reply is cached. One call a second at most."""
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except ValueError:          # a write cut short: read it again
            cache.unlink()
    key = os.environ.get("TELRAAM_API_KEY")
    if not key:
        raise NeedsKey(str(cache.relative_to(RUNS)))
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"X-Api-Key": key, "Content-Type": "application/json"})
    for attempt in range(4):   # a 504 or 429 is retried after 15, 45 and 135 seconds
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            print("    HTTP %d on %s, retrying" % (e.code, cache.name), file=sys.stderr)
            time.sleep(15 * 3 ** attempt)
    _last[0] = time.time()
    if d.get("download_url"):  # a large reply comes back as a link to a cached file
        with urllib.request.urlopen(d["download_url"], timeout=300) as r:
            d = json.loads(r.read())
    if d.get("status_code", 200) != 200 or not ("report" in d or "features" in d):
        return d          # never cache a refusal or an empty answer; the caller's check stops the run
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, cache)        # never a half-written cache file
    return d


def holidays(year):
    """Days whose traffic is not a working Tuesday to Thursday's: the federal holidays (and the weekday each is
    observed on), the day after Thanksgiving, and 24 December to 1 January."""
    def nth(month, weekday, n):          # n-th weekday of the month; n = -1 is the last
        if n > 0:
            d = dt.date(year, month, 1)
            d += dt.timedelta(days=(weekday - d.weekday()) % 7)
            return d + dt.timedelta(weeks=n - 1)
        d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
        return d - dt.timedelta(days=(d.weekday() - weekday) % 7)
    fixed = [dt.date(year, 1, 1), dt.date(year, 6, 19), dt.date(year, 7, 4), dt.date(year, 11, 11)]
    out = set()
    for d in fixed:
        out.add(d)
        out.add(d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d)
    thanks = nth(11, 3, 4)
    out |= {nth(1, 0, 3), nth(2, 0, 3), nth(5, 0, -1), nth(9, 0, 1), nth(10, 0, 2), thanks, thanks + dt.timedelta(days=1)}
    out |= {dt.date(year, 12, d) for d in range(24, 32)} | {dt.date(year, 1, 1)}
    return out


def window(end):
    return end - dt.timedelta(days=365), end


def snapshots(start, end):
    segs = {}
    day = SNAP_EPOCH + dt.timedelta(days=14 * max(0, -(-(start - SNAP_EPOCH).days // 14)))
    n = 0
    while day < end:     # END's own 20:00 UTC may not have happened yet, and a reply is cached for good
        t = "%s 20:00:00Z" % day.isoformat()
        d = post("/reports/traffic_snapshot", {"time": t, "contents": "minimal", "area": BBOX},
                 RUNS / "snapshots" / ("%s.json" % day.isoformat()))
        check(d.get("status_code") == 200, "snapshot %s answered 200" % t)
        for f_ in d["features"]:
            sid = str(f_["properties"]["segment_id"])
            segs.setdefault(sid, f_["geometry"])
        n += 1
        day += dt.timedelta(days=14)
    print("    %d snapshots, %d segments" % (n, len(segs)), file=sys.stderr)
    return segs


def chunks(start, end):
    """Calendar chunks of three months from 1 Feb, May, Aug and Nov that overlap [start, end). The last one ends at
    `end` when `end` falls inside it (the open chunk)."""
    a = max(dt.date(y, m, 1) for y in (start.year - 1, start.year) for m in (2, 5, 8, 11) if dt.date(y, m, 1) <= start)
    while a < end:
        b = dt.date(a.year + (a.month + 2) // 12, (a.month + 2) % 12 + 1, 1)
        yield a, min(b, end)
        a = b


def hourly(sid, start, end):
    rows = []
    for a, b in chunks(start, end):
        d = post("/reports/traffic", {"level": "segments", "format": "per-hour", "id": sid,
                                      "time_start": "%s 00:00:00Z" % a, "time_end": "%s 00:00:00Z" % b},
                 RUNS / "reports" / sid / ("%s_%s.json" % (a, b)))
        check(d.get("status_code", 200) == 200 and "report" in d, "report %s %s to %s answered" % (sid, a, b))
        rows += d["report"]
    return rows


def f(v):
    return float(v or 0)


def upper_median(vals):
    s = sorted(vals)
    return statistics.median(s[len(s) // 2:]) if s else 0.0


def level_runs(vals):
    """Index ranges of the series split at each sustained change of level (binary segmentation on medians)."""
    def rec(i0, i1):
        if i1 - i0 < 2 * SPLIT_MIN:
            return [(i0, i1)]
        best = None
        for k in range(i0 + SPLIT_MIN, i1 - SPLIT_MIN + 1):
            lo, hi = sorted((statistics.median(vals[i0:k]), statistics.median(vals[k:i1])))
            r = (lo + 1) / (hi + 1)
            if best is None or r < best[0]:
                best = (r, k)
        if best[0] < LEVEL_DROP:
            return rec(i0, best[1]) + rec(best[1], i1)
        return [(i0, i1)]
    return rec(0, len(vals))


def season(d):
    return ("winter", "spring", "summer", "fall")[(d.month % 12) // 3]


def summarise(sid, geom, rows, start, end):
    days = {}
    for r in rows:
        t = dt.datetime.fromisoformat(r["date"].replace("Z", "+00:00")).astimezone(LA)
        if start <= t.date() < end:
            days.setdefault(t.date(), {})[t.hour] = r
    ok = lambda r: r is not None and f(r.get("uptime")) >= MIN_UPTIME  # noqa: E731
    veh = lambda r: f(r.get("car")) + f(r.get("heavy")) + f(r.get("night"))  # noqa: E731
    allm = lambda r: veh(r) + f(r.get("bike")) + f(r.get("pedestrian"))  # noqa: E731
    hol = set().union(*(holidays(y) for y in range(start.year, end.year + 1)))
    lft = rgt = 0.0
    cand = []
    for day in sorted(days):
        H = days[day]
        for r in H.values():
            if ok(r):
                lft += f(r.get("car_lft"))
                rgt += f(r.get("car_rgt"))
        if day.weekday() not in (1, 2, 3) or day in hol:
            continue
        am = [veh(H[h]) for h in AM if ok(H.get(h))]
        pm = [veh(H[h]) for h in PM if ok(H.get(h))]
        md = [f(H[h].get("car")) + f(H[h].get("heavy")) for h in MIDDAY if ok(H.get(h))]
        if len(am) < 2 or len(pm) < 2 or len(md) < 2:
            continue
        cand.append({"day": day, "pk": max(am + pm), "pm": max(pm) >= max(am), "H": H, "mid": statistics.mean(md),
                     "act": sum(allm(r) for r in H.values() if ok(r)),
                     "mid_night": sum(f(H[h].get("night")) for h in MIDDAY if ok(H.get(h))),
                     "mid_car": sum(f(H[h].get("car")) + f(H[h].get("heavy")) for h in MIDDAY if ok(H.get(h)))})
    lines = [] if not geom else [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
    out = {"id": sid, "line": [[round(x, 6), round(y, 6)] for ln in lines for x, y in ln],
           "candidate_days": len(cand), "valid_days": 0}
    fail, flags = [], []
    if lft + rgt > 0:
        out.update(car_lft=round(lft), car_rgt=round(rgt), side_share=round(min(lft, rgt) / (lft + rgt), 4))
        if min(lft, rgt) < ONE_SIDE * (lft + rgt):
            flags.append("one side")     # hin-cut-through.py fails it unless the block is a one-way street
    # 1. Sustained level changes in the midday car level, which is daylight all year, so the change of clocks in March
    # and November, which moves the 5 and 6 pm hours into or out of the dark, is not read as a change of level: keep
    # the runs at the working level.
    vals = [c["mid"] for c in cand]
    ref = upper_median(vals)
    keep = []
    dropped = []
    for i0, i1 in level_runs(vals) if cand else []:
        run = cand[i0:i1]
        if statistics.median(vals[i0:i1]) >= LEVEL_DROP * ref:
            keep += run
        else:
            dropped.append([run[0]["day"].isoformat(), run[-1]["day"].isoformat(), len(run),
                            round(statistics.median(vals[i0:i1]), 1)])
    # 1b. Outages: OUTAGE_MIN or more days in a row inside a kept stretch whose midday level is under
    # LEVEL_DROP of the stretch's. A split must leave SPLIT_MIN days a side, so it can miss an outage in the middle.
    refm = upper_median([c["mid"] for c in keep])
    low = [c["mid"] < LEVEL_DROP * refm for c in keep]   # midday only: the peak steps down when the clocks change
    out_idx, i = set(), 0
    while i < len(keep):
        j = i
        # a run is low days with no qualifying day between them: no gap over a week (Thursday to next Tuesday is 5)
        while j < len(keep) and low[j] and (j == i or (keep[j]["day"] - keep[j - 1]["day"]).days <= 7):
            j += 1
        if j - i >= OUTAGE_MIN:
            out_idx.update(range(i, j))
            dropped.append([keep[i]["day"].isoformat(), keep[j - 1]["day"].isoformat(), j - i,
                            round(statistics.median(c["mid"] for c in keep[i:j]), 1)])
        i = max(j, i + 1)
    keep = [c for k, c in enumerate(keep) if k not in out_idx]
    if dropped:
        out["split"] = sorted(dropped)
        flags.append("split")
    # 2. Dead days in what is left: nothing counted, a peak under DEAD_SHARE of the upper-half median, or a midday car
    # level under DEAD_SHARE of its upper-half median, a camera that cannot see the street in daylight that day.
    ref2, refm2 = upper_median([c["pk"] for c in keep]), upper_median([c["mid"] for c in keep])
    dead = [c for c in keep if c["act"] == 0 or c["pk"] < DEAD_SHARE * ref2 or c["mid"] < DEAD_SHARE * refm2]
    valid = [c for c in keep if c not in dead]
    out["dead_days"] = len(dead)
    out["zero_days"] = sum(1 for c in cand if c["act"] == 0)
    if keep:
        out["dead_share"] = round(len(dead) / len(keep), 3)
        if len(dead) / len(keep) > MAX_DEAD:
            fail.append("%d%% of days dead" % round(100 * len(dead) / len(keep)))
    mid_n, mid_c = sum(c["mid_night"] for c in valid), sum(c["mid_car"] for c in valid)
    if valid and mid_n > mid_c:
        fail.append("night count above car count at midday")
    out["valid_days"] = len(valid)
    if valid:
        pk = [c["pk"] for c in valid]
        med = statistics.median(pk)
        q = statistics.quantiles(pk, n=4) if len(pk) >= 4 else [min(pk), 0, max(pk)]
        out.update(first=valid[0]["day"].isoformat(), last=valid[-1]["day"].isoformat(), peak=round(med, 1),
                   peak_q1=round(q[0], 1), peak_q3=round(q[2], 1),
                   pm_share=round(sum(c["pm"] for c in valid) / len(valid), 2))
        if q[0] < 0.5 * med:
            flags.append("spread")
        dl = [c for c in valid if c["day"].month in DAYLIGHT_MONTHS]
        out["daylight_days"] = len(dl)
        if len(dl) >= MIN_SEASON_DAYS:
            out.update(peak_daylight=round(statistics.median(c["pk"] for c in dl), 1),
                       daylight_first=dl[0]["day"].isoformat(), daylight_last=dl[-1]["day"].isoformat())
        per = {}
        for c in valid:
            per[season(c["day"])] = per.get(season(c["day"]), 0) + 1
        out["seasons"] = dict(sorted(per.items()))
        if not any(c["day"].month in LIGHT_MONTHS for c in valid):
            flags.append("winter only")   # shown with the flag; its evening peak may be read in the dark
        elif sum(1 for n in per.values() if n >= MIN_SEASON_DAYS) < 2:
            fail.append("one season")
        full, shares, shares_dl = [], [], []
        for c in valid:
            H = c["H"]
            if all(ok(H.get(h)) for h in range(24)):
                tot = sum(veh(H[h]) for h in range(24))
                if tot > 0:
                    full.append(tot)
                    shares.append(c["pk"] / tot)
                    if c["day"].month in DAYLIGHT_MONTHS:
                        shares_dl.append(c["pk"] / tot)
        if full:
            out.update(full_days=len(full), daily_counted=round(statistics.median(full)),
                       peak_share=round(statistics.median(shares), 4))
            if len(shares_dl) >= 10:   # the share on the April to September days peak_daylight is the median of
                out.update(full_days_daylight=len(shares_dl), peak_share_daylight=round(statistics.median(shares_dl), 4))
            out["daily"] = round(med / out["peak_share"]) if out["peak_share"] else out["daily_counted"]
    if len(valid) < MIN_DAYS:
        fail.append("%d valid days" % len(valid))
    out["flags"] = flags
    out["fail"] = fail
    out["kept"] = 0 if fail else 1
    return out


def build(end):
    start, end = window(end)
    segs = snapshots(start, end)
    check(len(segs) >= 10, "SF bounding box segments >= 10 (%d)" % len(segs))
    res = []
    for sid in sorted(segs, key=int):
        rows = hourly(sid, start, end)
        if rows:
            check(all("uptime" in r and "car" in r and "date" in r for r in rows), "segment %s rows carry uptime, car, date" % sid)
        s = summarise(sid, segs[sid], rows, start, end)
        s["hours"] = len(rows)
        res.append(s)
        print("    %s  hours %5d  days %3d  peak %s  daily %s  %s" % (sid, len(rows), s["valid_days"], s.get("peak"),
                                                                  s.get("daily"), "; ".join(s["fail"] + s["flags"])),
              file=sys.stderr)
    kept = [s for s in res if s["kept"]]
    check(all(len(s["line"]) >= 2 for s in kept), "every kept segment has a line")
    check(len(kept) >= 20, "segments kept >= 20 (%d)" % len(kept))
    return {"source": "Telraam API v1 (telraam-api.net), traffic_snapshot and per-hour traffic reports; sources/telraam.md",
            "window": [start.isoformat(), end.isoformat()], "bbox": BBOX,
            "rules": {"vehicles": "car + heavy + night, both directions", "min_uptime": MIN_UPTIME,
                      "peak_days": "Tue to Thu, holidays left out", "am_hours": list(AM), "pm_hours": list(PM),
                      "min_days": MIN_DAYS, "split_min_days": SPLIT_MIN, "level_drop": LEVEL_DROP,
                      "dead_share": DEAD_SHARE, "max_dead": MAX_DEAD, "min_season_days": MIN_SEASON_DAYS, "one_side_share": ONE_SIDE,
                      "daylight_months": [DAYLIGHT_MONTHS.start, DAYLIGHT_MONTHS.stop - 1]},
            "found": len(res), "kept": len(kept), "segments": res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="the 12 months to today; fetch what moved")
    ap.add_argument("--offline", action="store_true", help="cache only; the window segments.json holds unless --end")
    ap.add_argument("--end", help="window end, YYYY-MM-DD (exclusive)")
    a = ap.parse_args()
    if a.offline:
        os.environ.pop("TELRAAM_API_KEY", None)
    if a.end:
        end = dt.date.fromisoformat(a.end)
    elif a.offline and OUT.exists():
        end = dt.date.fromisoformat(json.loads(OUT.read_text())["window"][1])
    else:
        end = dt.date.today()
    try:
        doc = build(end)
    except NeedsKey as e:
        if a.offline:
            sys.exit("not cached, and --offline: %s" % e)
        pipeline_state.record(MARKER, "failed",
                              detail="TELRAAM_API_KEY not set on this host and %s is not cached; last segments.json kept" % e)
        print("TELRAAM_API_KEY not set and %s not cached: kept the last segments.json" % e, file=sys.stderr)
        return
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, http.client.HTTPException) as e:
        pipeline_state.record(MARKER, "failed", detail="Telraam API read failed (%s); last segments.json kept" % e)
        print("Telraam API read failed (%s): kept the last segments.json" % e, file=sys.stderr)
        return
    changed = write_text(OUT, json.dumps(doc, indent=1, sort_keys=True) + "\n")
    if not a.offline:
        pipeline_state.record(MARKER, "changed" if changed else "unchanged", version=doc["window"][1],
                              detail="%d segments found, %d kept" % (doc["found"], doc["kept"]))
    print("%s %s: %d segments found, %d kept" % ("wrote" if changed else "unchanged", OUT.relative_to(ROOT), doc["found"], doc["kept"]), file=sys.stderr)


if __name__ == "__main__":
    main()
