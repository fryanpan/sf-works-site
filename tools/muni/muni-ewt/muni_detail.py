"""Write site/data/muni-lines.json: each listed Muni line's excess wait and speed over each period, for its own page.

Reads site/data/muni.json (the periods and the listed lines, from site_data.py) and data/muni-ewt/daily/
(ewt_daily.py: each line by service date, and by service date and hour for the newest three months).

Granularity. Bryan, 2026-11-09: pick the finest unit from hourly, 6-hourly, daily and weekly that keeps a chart at or under
about 1,000 points. So a period of D days takes the first unit u in (1, 6, 24) hours with D * 24 / u <= 1000: 30 days
is hourly, 90 days 6-hourly, 365 days daily, and 5 years and Max (Bryan, 2026-11-09) weekly, Monday to Sunday, from
ewt_daily.py --by-week. Days are the days the period's usable months cover (site_data.py leaves the 511 outage out), and
a week counts only when all seven of its days fall in them. A 6-hour point is one of the three 6-hour blocks of a service date, 05-10, 11-16 and 17-22 (the hours service is counted, 05:00 to 22:59), from ewt_daily.py --by-6h. Each point also
carries the 10th, 50th and 90th percentiles across the line's stops (excess wait) and trips (speed), from ewt_daily.py. Points pool the same way as everywhere else:
scheduled wait by scheduled departures, and actual wait, already pooled within each hour by observed departures, by
the scheduled departures of the hours a bus was seen (ewt_daily.py's eba); speed is miles over hours. A point with
under MIN_EB scheduled departures in frequent hours has no excess wait, and one with no measured stretch no speed.

Each period also gets the line's figures over the whole period and over the period of the same length just before
it (left out where that earlier period runs into a month site_data.py marks unusable), for the page's top row.

Checks before writing: every period's unit follows the rule, every 6-hour point starts at 5, 11 or 17, no line has points outside its period, and the newest
period's points come from the newest month. A failure exits 1 and leaves the old file.
Checks tying this file to muni.json, which the same pages read beside it: the same periods and the same lines; every line
a period lists has this period here; each line's 30-day speed equals muni.json's newest month for that line to 0.01 mph
(both are miles over observed hours from the same trips, and the line page shows one beside the other's sparkline);
and each listed line's excess wait over the period, cable cars included, is within TOL minute of muni.json's figure for
it pooled by scheduled departures (nowByDepartures: the two pool the same stop-hours; muni.json weights dates equally
within a month's hour cell, this file by scheduled departures). The cards on a line's page pool its hours by riders on
board (site_data.py, Riders on board), which a day row, carrying no hour, can't do, so the charts here stay by departures.
And each line's 365-day heat map (muni-heat.json) pooled by stop-hours is within HEATTOL of its figure by departures,
unless the map blanks more than HEATBLANK of its stop-hours (see the check). A listed line with no figure fails, and so does a period month with no daily rows at all.
Idempotent: no run date written, keys sorted.
Usage: python3 tools/muni/muni-ewt/muni_detail.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, glob, json, os, sys
from collections import defaultdict

ROOT = paths.ROOT
D = os.path.join(ROOT, "data", "muni-ewt", "daily")
OUT = os.path.join(ROOT, "site", "data", "muni-lines.json")
SITE = json.load(open(os.path.join(ROOT, "site", "data", "muni.json")))
MAX_POINTS, UNITS, MIN_EB, TOL = 1000, (1, 6, 24, 168), 30, 0.1
errors = []

def unit_for(days):
    return next(u for u in UNITS if days * 24 / u <= MAX_POINTS)

def wkend(sdate):
    """The month of the Sunday that ends the week starting on Monday sdate."""
    import datetime
    return (datetime.date(int(sdate[:4]), int(sdate[4:6]), int(sdate[6:])) + datetime.timedelta(days=6)).strftime("%Y-%m")

def span(a, b):
    out, (y, m) = [], (int(a[:4]), int(a[5:]))
    while f"{y}-{m:02d}" <= b:
        out.append(f"{y}-{m:02d}"); y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out

lines = set(SITE["lines"])
daily, hourly, six, weekly = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
for f in sorted(glob.glob(os.path.join(D, "20*.csv"))):
    for r in csv.DictReader(open(f)):
        if r["route"] in lines:
            daily[r["sdate"][:4] + "-" + r["sdate"][4:6]].append(r)
for pat, into in (("hourly-*.csv", hourly), ("6h-*.csv", six), ("weekly.csv", weekly)):
    for f in sorted(glob.glob(os.path.join(D, pat))):
        for r in csv.DictReader(open(f)):
            if r["route"] in lines:
                into[r["sdate"][:4] + "-" + r["sdate"][4:6]].append(r)

num = lambda v: float(v) if v not in ("", None) else 0.0
def acc():
    return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # swt*eb, eb, awt*eba, eba, miles, obs_hr
def add(a, r):
    # both waits by scheduled departures, as ewt_daily.py pooled the row's hours; awt over the hours a bus was seen (eba)
    eb, eba = num(r["eb"]), num(r["eba"])
    if r["swt"] and eb > 0:
        a[0] += num(r["swt"]) * eb; a[1] += eb
    if r["awt"] and eba > 0:
        a[2] += num(r["awt"]) * eba; a[3] += eba
    if r["miles"] and num(r["obs_hr"]) > 0:
        a[4] += num(r["miles"]); a[5] += num(r["obs_hr"])
def value(a, min_eb=MIN_EB):
    return {"ewt": round(a[2] / a[3] - a[0] / a[1], 2) if a[1] >= min_eb and a[3] > 0 else None,
            "mph": round(a[4] / a[5], 2) if a[5] > 0 else None}

# Excess wait by cause, at a grain that follows the period (Bryan, 2026-11-10: "Change the reporting period depending on
# time range"): each day over 30 days, each week over 90 and 365 days; 5 years and Max keep muni.json's months. Missing
# and weighting pool by scheduled departures like the excess wait they split (ewt_daily.py), and spacing is the rest.
CAUSE_GRAIN = {"30": "day", "90": "week", "365": "week"}
def causes(line, ms, grain):
    if grain == "day":
        rows = [r for m in ms for r in daily.get(m, []) if r["route"] == line]
    else:
        keep = set(ms)
        rows = [r for m in ms for r in weekly.get(m, []) if r["route"] == line and wkend(r["sdate"]) in keep]
    res = []
    for r in sorted(rows, key=lambda r: r["sdate"]):
        a = acc(); add(a, r)
        e = value(a)["ewt"]
        eb = num(r["eb"])
        mis = round(float(r["mis"]), 2) if r.get("mis") not in ("", None) else None
        wgt = round(float(r["wgt"]), 2) if r.get("wgt") not in ("", None) else None
        ok = e is not None and mis is not None and wgt is not None and eb >= MIN_EB
        res.append({"t": r["sdate"], "ewt": e if ok else None, "missing": mis if ok else None, "weighting": wgt if ok else None,
                    "spacing": round(e - mis - wgt, 2) if ok else None})
    if rows and "mis" not in rows[0]:
        errors.append(f"line {line}: daily/ rows carry no cause columns (rerun ewt_daily.py)")
    return res

# Speed along the line, by tenth and by stop pair (speed_along_line.py; Bryan, 2026-11-10: "Can you show speed along
# the line here and also show speed above in the map?"), carried per line and period for the line page.
_sp = os.path.join(ROOT, "data", "muni-ewt", "speed_along_line.json")
_spj = json.load(open(_sp)) if os.path.exists(_sp) else {"windows": {}}
SPEED = {w: x["lines"] for w, x in _spj["windows"].items()}
# The share of each line's measured bus-miles that its line speed covers (speed_along_line.py's cover), carried as
# period.cover: the Lines page and the line page show no speed under MINCOVER, where the line figure covers a small,
# unrepresentative part of the route (the 8AX's freeway and the 25's bridge fall outside its timepoint window).
COVER = {w: x.get("cover", {}) for w, x in _spj["windows"].items()}
if SPEED and set(SPEED) != set(SITE["windows"]):
    errors.append(f"speed_along_line.json periods {sorted(SPEED)} are not muni.json's {sorted(SITE['windows'])}")

out = {"units": {}, "lines": {}}
for w, x in SITE["windows"].items():
    days, ms = x["days"], x.get("monthList") or span(*x["months"])
    u = unit_for(days)
    out["units"][w] = u
    src = {1: hourly, 6: six, 24: daily, 168: weekly}[u]
    if u == 168:
        # a week counts only when all seven of its days fall in the period's usable months
        keep = set(ms)
        src = {m: [r for r in rows if wkend(r["sdate"]) in keep] for m, rows in weekly.items() if m in keep}
    if any(m not in src for m in ms):
        errors.append(f"{w} days at {u}-hour points needs {ms}, have {sorted(src)}")
        continue
    prev = span(*x["before"]) if x["before"] else []
    for line in sorted(lines):
        pts, whole, before = defaultdict(acc), acc(), acc()
        for m in ms:
            for r in src[m]:
                if r["route"] != line:
                    continue
                key = r["sdate"] if u >= 24 else f"{r['sdate']}T{int(r['hr']):02d}"  # a 6-hour file's hr is its block's first hour
                add(pts[key], r)
        for m in ms:
            for r in daily.get(m, []):
                if r["route"] == line:
                    add(whole, r)
        for m in prev:
            for r in daily.get(m, []):
                if r["route"] == line:
                    add(before, r)
        spread = {}
        for m in ms:
            for r in src[m]:
                if r["route"] == line:
                    key = r["sdate"] if u >= 24 else f"{r['sdate']}T{int(r['hr']):02d}"
                    spread[key] = {k: (round(float(r[k]), 2) if r.get(k) else None) for k in ("ewt_p10", "ewt_p50", "ewt_p90", "mph_p10", "mph_p50", "mph_p90")}
        series = [{"t": k, **value(a), **spread.get(k, {})} for k, a in sorted(pts.items())]
        if series and not (ms[0].replace("-", "") <= series[0]["t"][:6] and series[-1]["t"][:6] <= ms[-1].replace("-", "")):
            errors.append(f"line {line}, {w} days: points outside the period")
        out["lines"].setdefault(line, {})[w] = {
            "points": series, "period": value(whole, MIN_EB * 10), "previous": value(before, MIN_EB * 10) if prev else None}
        cv = COVER.get(w, {}).get(line)
        if cv is not None:
            out["lines"][line][w]["period"]["cover"] = cv["share"]
        sp = SPEED.get(w, {}).get(line)
        if sp:
            out["lines"][line][w]["speedAlong"] = {d: {"tenths": v["tenths"], "pairs": v["pairs"]} for d, v in sorted(sp.items())}
        if w in CAUSE_GRAIN:
            out["lines"][line][w]["causes"] = causes(line, ms, CAUSE_GRAIN[w])
# ties to muni.json
for w, x in SITE["windows"].items():
    gone = [m for m in (x.get("monthList") or span(*x["months"])) if not daily.get(m)]
    if gone:
        errors.append(f"{w} days: no daily/ rows for {gone}")
nw = SITE["windows"]["30"]["months"][1]
for w, x in SITE["windows"].items():
    for r in x["lines"]:
        d = out["lines"].get(r["line"], {}).get(w)
        if d is None:
            errors.append(f"{r['line']} listed for {w} days in muni.json but has no {w}-day figures here")
        elif r.get("now") is not None and r.get("nowByDepartures") is None:
            errors.append(f"{r['line']} {w} days: no nowByDepartures in muni.json (site_data.py)")
        elif r.get("now") is not None and (d["period"]["ewt"] is None or abs(d["period"]["ewt"] - r["nowByDepartures"]) > TOL):
            errors.append(f"{r['line']} {w} days: excess wait {d['period']['ewt']} here, {r['nowByDepartures']} in muni.json by departures")
# Check: each line's heat map (site/data/muni-heat.json, site_data.py), its cells pooled by stop-hours, is within HEATTOL
# minute of the line's 365-day excess wait by scheduled departures (nowByDepartures), the figure that pools the same
# stop-hours. Not the riders-on-board figure the cards show: a map cell carries no riders, and weighting hours by
# riders moves the 12 and the 23 0.1 minute above nowByDepartures. The map still differs by its own weights (each
# stop-hour counts once, where the line's figure weights by departures and gives each date equal weight) and by its
# blank cells, so a line whose map blanks more than HEATBLANK of its stop-hours is named, not failed: the 8BX's 10 am
# inbound, 7 buses seen for every 12 scheduled at about 4 minutes, is in its figure and blank on its map (2026-11-17).
HEATTOL, HEATBLANK = 0.15, 0.05
_hp = os.path.join(ROOT, "site", "data", "muni-heat.json")
HEATJ = json.load(open(_hp)) if os.path.exists(_hp) else None
if HEATJ is None:
    errors.append(f"no {_hp} (site_data.py)")
else:
    for r in SITE["windows"]["365"]["lines"]:
        h = HEATJ.get("365", {}).get(r["line"])
        c = [x for d in ("0", "1") for x in (h or {}).get(d, [])]
        if not c or r.get("nowByDepartures") is None:
            continue
        p = sum(x[2] * x[3] for x in c) / sum(x[3] for x in c)
        if abs(p - r["nowByDepartures"]) > HEATTOL:
            if (h.get("blanked") or 0) > HEATBLANK:
                print(f"note: {r['line']} 365 days: heat map {p:.2f} against {r['nowByDepartures']}, {h['blanked']:.0%} of its stop-hours blank")
            else:
                errors.append(f"{r['line']} 365 days: heat map pools to {p:.3f}, nowByDepartures {r['nowByDepartures']}")
for l, L in SITE["lines"].items():
    m = next((t["mph"] for t in L["trend"] if t["month"] == nw), None)
    p = out["lines"].get(l, {}).get("30", {}).get("period", {}).get("mph")
    if (m is None) != (p is None) or (m is not None and abs(m - p) > 0.01):
        errors.append(f"{l}: 30-day speed {p} here, {m} for {nw} in muni.json")
# Check: line by line, the day rows' causes pooled over the newest month match muni.json's month to 0.05 minute. Not
# exact: a day row's split covers only its hours with a tracked bus, but it is pooled here by all its scheduled
# departures (the PM cable car, partly tracked, is 0.034 minute off for October 2026). Since SFMTA's line types made every
# hour of a line like the 9, 33, 54 or 8AX count (2026-11-17), its quieter hours, with more stop-hours where no bus was
# seen, put the day rows up to 0.07 minute above muni.json, so the bound is 0.08, and TOL is 0.1 for the same reason.
for l, L in SITE["lines"].items():
    t = L.get("splitByDepartures") if (L.get("splitByDepartures") or {}).get("month") == nw else None
    rows = [r for r in daily.get(nw, []) if r["route"] == l and r.get("mis") not in ("", None)]
    if not t or t.get("missing") is None or not rows:
        continue
    eb = sum(num(r["eb"]) for r in rows)
    for k, c in (("missing", "mis"), ("weighting", "wgt")):
        v = sum(float(r[c]) * num(r["eb"]) for r in rows) / eb
        if abs(v - t[k]) > 0.08:
            errors.append(f"{l} {nw}: {k} {v:.3f} from the days, {t[k]} in muni.json")
for w, u in out["units"].items():
    if u == 6 and any(p["t"][9:] not in ("05", "11", "17") for L in out["lines"].values() for p in L.get(w, {}).get("points", [])):
        errors.append(f"{w} days: a 6-hour point off the 5, 11 and 17 o'clock blocks")
    if u != unit_for(SITE["windows"][w]["days"]):
        errors.append(f"{w} days: unit {u} breaks the rule")
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
text = json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n"
old = open(OUT).read() if os.path.exists(OUT) else None
if text != old:
    open(OUT, "w").write(text)
    print("wrote", OUT, len(text), "bytes")
else:
    print("unchanged", OUT)
print("units:", out["units"], "lines:", len(out["lines"]))
