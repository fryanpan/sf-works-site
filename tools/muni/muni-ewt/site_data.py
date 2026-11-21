"""Write site/data/muni.json (and muni-heat.json, the line pages' heat-map cells), the data behind sf-works.org/transportation/muni, from the Muni excess-wait extract and the bus speed summaries.

Reads data/muni-ewt/extract.csv and extract_freq.csv (line x month x day type x hour, ewt_aggregate.py; the second
from frequent stop-hours only), extract_months.csv,
summary/system_month.csv, service_delivered.csv (SFMTA's published service delivered, fetch_service_delivered.py), summary_trip/speed_system_month.csv, summary_trip/trip_rank.csv, ridership.csv (SFMTA's boardings by route, fetch_ridership.py), satisfaction.csv
(fetch_satisfaction.py), and for excess wait along the route stops/<month>.csv with SFMTA's GTFS zip in .cache/muni-gtfs/ (the muni-gtfs step),
and stophours/<month>.csv.gz (ewt_stop_hours.py, the same stops by clock hour) for the line pages' hour-by-tenth heat maps.
Reaches no network.

Frequent service: by SFMTA's line types (freq_rule.py; Bryan, 2026-11-17: "SFMTA's line types").
SFMTA's Connector lines and Owl service are infrequent and judged on time in SFMTA's window, 1 minute early to 4 late
(ontime_month.py); every other line is frequent and judged by excess wait in every hour it runs (extract_freq.csv,
ewt_aggregate.py --frequent), as in the stop, trend, map and on-time files, so the two figures never share a departure. Weighting is ewt_analyze.py's, TfL's three steps: cells within
a line by scheduled departures (for the frequent figures, times riders on board from SFMTA's occupancy readings: Riders on
board, below), then across lines SWT by scheduled and AWT by observed departures. Hours 05:00 to
22:59, LBUS counted as the L, months whose feed kept under 60% of departures left out.

Periods. The archive is monthly, so "30 days" is the newest month 511 has posted, 90 days the newest three calendar
months and 365 days the newest twelve, each against the period of the same length just before it (no comparison when
that earlier period touches a month the outage made unusable). 5 years is the newest 60 calendar months and Max every
month the extract has; both leave the unusable months out, carry the days they cover, and have no earlier period.

Checks, run before anything is written; a failure exits 1 and leaves the old file in place:
  - recomputing every month with TfL's own 5-bus line reproduces summary/system_month.csv's ewt_all and ewt_hf to 0.001;
  - each usable month's frequent-hour scheduled departures in daily/<month>.csv (ewt_daily.py, the line pages' source)
    are within 0.1% of extract_freq.csv's, and both hold the same lines: the same stop-hours, including those where
    no bus was seen (the overview leaves out a line-hour cell with no bus on any date of the month, up to 0.03% of
    departures in early 2022); a usable month with no daily file fails;
  - the 30, 90 and 365-day periods hold only usable months;
  - no line appears twice, and every line's figures are finite.
  - along the route: every tenth has blocks > 0 and finite figures, the system has all ten tenths in every period
    (each direction and the two combined by scheduled departures), and each month's stops and stophours files exist;
    every heat-map cell is finite; no listed line leaves more than LINEDROP of a period's stop-hours unplaced along
    its line, and none in the newest twelve months is off today's route (stop_pos);
  - satisfaction: at least 15 years, each between 0 and 100;
  - line types: freq_rule.py's infrequent lines are line_types.csv's, and every Connector or Owl route in SFMTA's
    ridership file (ridership.csv) is in line_types.csv;
  - wait (allService): the rider-weighted citywide figure sits within its lines and equals the Lines list's excess
    waits weighted by riders, its split adds up, lines with riders carry enough of the frequent departures, only
    frequent lines show an excess wait and every other listed line has an on-time figure.
Idempotent: no run date is written, keys and rows are sorted, so a rerun on the same inputs writes the same bytes.
Usage: python3 tools/muni/muni-ewt/site_data.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime, glob, gzip, io, json, math, os, sys, zipfile
import duckdb
from freq_rule import INFREQUENT, CONNECTOR, OWL, is_frequent  # the one frequent-service rule, SFMTA's line types

ROOT = paths.ROOT
D = os.path.join(ROOT, "data", "muni-ewt")
OUT = os.path.join(ROOT, "site", "data", "muni.json")
MINKEEP = 0.6
SMALL = 20000  # scheduled stop departures in frequent hours a line needs in a month to be listed (its change needs it in both)
# Listing: a line is listed in a period when it averages SMALL a month over it, or when it does so over the newest 12
# months and has at least a tenth of that in the period, so a line running now doesn't drop out of the 5-year view
# because it became frequent recently (the 48), and the 30, 90 and 365-day lists stay one list. The long periods also
# list lines that met the floor over them and no longer do (the 15, the 28, the KT).
MAIN = ["1", "5", "5R", "8", "9", "14", "14R", "22", "24", "29", "30", "38", "38R", "44", "49", "J", "K", "L", "M", "N", "T"]

errors = []
# Check: freq_rule.py's infrequent lines are the tracked record's (line_types.csv, SFMTA's Service Category column), and
#   SFMTA's ridership file names no Connector or Owl route the record lacks
LINE_TYPES = {r["route"]: r for r in csv.DictReader(open(os.path.join(D, "line_types.csv")))}
_inf = {r for r, x in LINE_TYPES.items() if x["rule"] == "infrequent"}
if _inf != {r for r in INFREQUENT if "-" not in r} or {r for r, x in LINE_TYPES.items() if x["sfmta_type"] == "Connector"} != set(CONNECTOR):
    errors.append(f"line types: freq_rule.py's infrequent lines {sorted(INFREQUENT)} against line_types.csv's {sorted(_inf)}")
_names = {x["name"] for x in LINE_TYPES.values()}
for _r in csv.DictReader(open(os.path.join(D, "ridership.csv"))):
    if _r["category"] in ("Connector", "Owl") and _r["route"] not in _names and _r["route"] != "K L M N Owl":
        errors.append(f"line types: SFMTA lists {_r['route']} as {_r['category']}, missing from line_types.csv")
con = duckdb.connect()
con.execute("SET threads=1")  # one thread: parallel float sums can land either side of a rounding edge, and a rerun must write the same bytes
REN_PY = {"C": "CA", "L-OWL": "LOWL", "N-OWL": "NOWL", "LBUS": "L"}  # GTFS route ids to the extract's names, as REN
REN = "CASE route WHEN 'C' THEN 'CA' WHEN 'L-OWL' THEN 'LOWL' WHEN 'N-OWL' THEN 'NOWL' WHEN 'LBUS' THEN 'L' ELSE route END"
ext = os.path.join(D, "extract.csv")
# DuckDB reads these itself; open them here too, so the orchestrator's read trace sees them and reruns this step when they move
for _p in (ext, os.path.join(D, "extract_freq.csv")):
    open(_p, "rb").close()
con.execute(f"CREATE TABLE mk AS SELECT * FROM read_csv('{D}/extract_months.csv', header=true)")
# src 'all' is every stop-hour (extract.csv, for the check against ewt_analyze.py's summary and the all-hours figure);
# src 'freq' is the frequent stop-hours only (extract_freq.csv), which every excess-wait figure on the site uses
con.execute(f"""CREATE TABLE c0 AS SELECT * REPLACE ({REN} AS route) FROM (
    SELECT 'all' src, * FROM read_csv('{ext}', header=true)
    UNION ALL BY NAME SELECT 'freq' src, * FROM read_csv('{os.path.join(D, "extract_freq.csv")}', header=true))
  WHERE hr BETWEEN 5 AND 22 AND swt IS NOT NULL AND awt IS NOT NULL
    AND month IN (SELECT month FROM mk WHERE kept_share >= {MINKEEP})""")
# LBUS and L in one month become one line, exactly as ewt_analyze.py merges them
con.execute("""CREATE TABLE c AS SELECT src, route, month, daytype, hr, sum(swt*eb)/sum(eb) swt, sum(awt*ob)/sum(ob) awt,
  sum(tswt_eb*eb) FILTER (WHERE tswt_eb IS NOT NULL)/sum(eb) FILTER (WHERE tswt_eb IS NOT NULL) tswt_eb,
  sum(tswt_ob*ob) FILTER (WHERE tswt_ob IS NOT NULL)/sum(ob) FILTER (WHERE tswt_ob IS NOT NULL) tswt_ob,
  sum(eb) eb, sum(ob) ob, sum(eb_per_block*eb)/sum(eb) bph FROM c0 GROUP BY ALL""")

# ---- Riders on board: the weight each hour carries within a line ----------------------------------------------
# Bryan, 2026-11-17, answering how a line's hours should pool: "Use occupancy readings". Within
# a line, each frequent cell (line, month, day type, hour) is weighted by its scheduled departures times the average load
# on a bus in that line, day type (weekday, or weekend for Saturday and Sunday) and hour, from SFMTA's occupancy
# readings (optimizer/crowding_levels_hour.csv, the feed's level on every in-service read of every bus, directions
# pooled by reads, since the extract pools a line's two directions at TfL's Step I). So a full 5 pm bus counts for more
# than a near-empty 10 pm one. Across lines the weight stays the line's weekday boardings (below). The 'all' cells keep
# departure weights, so the check against ewt_analyze.py's summary still reproduces it.
# Load per level, in seated loads (a bus with every seat taken is 1): [inference — mine]. The GTFS-realtime levels have no
# numbers in the spec and SFMTA publishes none for its feed, so these are midpoints of what the names say: empty a
# handful, many seats about a third full, few seats about three quarters, standing room about a fifth over the seats,
# fuller levels more. Within a line the scale cancels; only the ratios between hours matter. LOAD_ALT are the two
# mappings the sensitivity check runs (--load-map low|high prints the figures and writes nothing).
LOAD_MAPS = {"central": {"empty": 0.05, "many_seats": 0.35, "few_seats": 0.75, "standing_room": 1.2, "crushed": 1.6, "full": 1.8, "not_accepting": 1.8},
             "low": {"empty": 0.15, "many_seats": 0.45, "few_seats": 0.7, "standing_room": 1.0, "crushed": 1.2, "full": 1.3, "not_accepting": 1.3},
             "high": {"empty": 0.0, "many_seats": 0.25, "few_seats": 0.85, "standing_room": 1.5, "crushed": 2.0, "full": 2.2, "not_accepting": 2.2}}
LOAD_MAP = sys.argv[sys.argv.index("--load-map") + 1] if "--load-map" in sys.argv else "central"
OCC_MINREADS = 20  # reads a line needs in a day type and hour (all days, both directions) for its own load
_occ = {}
_occ_path = os.path.join(D, "optimizer", "crowding_levels_hour.csv")
for r in csv.DictReader(open(_occ_path)):
    k = (REN_PY.get(r["line"], r["line"]), r["day_type"], int(r["hour"]))
    a = _occ.setdefault(k, [0, 0.0])
    a[0] += int(r["reads"]); a[1] += sum(int(r[l]) * v for l, v in LOAD_MAPS[LOAD_MAP].items())
con.execute("CREATE TABLE occ (route VARCHAR, dt VARCHAR, hr INTEGER, reads BIGINT, lf DOUBLE)")
con.executemany("INSERT INTO occ VALUES (?, ?, ?, ?, ?)", [(k[0], k[1], k[2], a[0], a[1] / a[0]) for k, a in sorted(_occ.items()) if a[0] >= OCC_MINREADS])
# A line-hour with no load of its own takes the line's average load over its hours with one (same day type, else any),
# which within the line is the departure weight; a line with no readings at all (trains, cable cars, the F) pools by
# departures, as before.
con.execute("""CREATE OR REPLACE TABLE c AS SELECT c.*, CASE WHEN src = 'all' THEN eb
    ELSE eb * coalesce(o.lf, ld.lf, la.lf, 1) END w,
    (src = 'freq' AND o.lf IS NULL AND la.lf IS NOT NULL) w_fill, (src = 'freq' AND la.lf IS NULL) w_none
  FROM c
  LEFT JOIN occ o ON o.route = c.route AND o.dt = CASE WHEN c.daytype = 'weekday' THEN 'weekday' ELSE 'weekend' END AND o.hr = c.hr
  LEFT JOIN (SELECT route, dt, sum(lf*reads)/sum(reads) lf FROM occ GROUP BY ALL) ld
    ON ld.route = c.route AND ld.dt = CASE WHEN c.daytype = 'weekday' THEN 'weekday' ELSE 'weekend' END
  LEFT JOIN (SELECT route, sum(lf*reads)/sum(reads) lf FROM occ GROUP BY ALL) la ON la.route = c.route""")

def lines(where, key="month", w="w"):
    """Step II: each line's month (or other key), cells weighted by w: riders on board for frequent cells, scheduled
    departures for 'all' cells (see Riders on board above); w="eb" weights every cell by scheduled departures, as the
    line pages' day rows (ewt_daily.py) do, for muni_detail.py's check."""
    return f"""SELECT route, {key}, sum(swt*{w})/sum({w}) swt, sum(awt*{w})/sum({w}) awt, sum(eb) eb, sum(ob) ob,
      sum((tswt_eb-swt)*{w}) FILTER (WHERE tswt_ob IS NOT NULL)/sum({w}) FILTER (WHERE tswt_ob IS NOT NULL) mis,
      sum(tswt_eb*{w}) FILTER (WHERE tswt_ob IS NOT NULL)/sum({w}) FILTER (WHERE tswt_ob IS NOT NULL) teb,
      sum(tswt_ob*{w}) FILTER (WHERE tswt_ob IS NOT NULL)/sum({w}) FILTER (WHERE tswt_ob IS NOT NULL) tob
      FROM c WHERE {where} GROUP BY ALL"""

def system(where, key="month", w="w"):
    """Step III: across lines, SWT by scheduled and AWT by observed departures."""
    q = f"""SELECT {key}, sum(awt*ob)/sum(ob) - sum(swt*eb)/sum(eb) ewt,
      sum(mis*eb) FILTER (WHERE mis IS NOT NULL)/sum(eb) FILTER (WHERE mis IS NOT NULL) mis,
      sum(tob*ob) FILTER (WHERE tob IS NOT NULL)/sum(ob) FILTER (WHERE tob IS NOT NULL)
        - sum(teb*eb) FILTER (WHERE teb IS NOT NULL)/sum(eb) FILTER (WHERE teb IS NOT NULL) wgt,
      sum(eb) eb, count(*) n, sum(swt*eb)/sum(eb) swt FROM ({lines(where, key, w)}) GROUP BY 1 ORDER BY 1"""
    return {r[0]: dict(zip(["ewt", "mis", "wgt", "eb", "lines", "swt"], r[1:])) for r in con.execute(q).fetchall()}

F = "src = 'freq'"
freq = system(F)
allh = system("src = 'all'")
hf5 = system("src = 'all' AND bph >= 5")

# Check: TfL's own split reproduces ewt_analyze.py's published summary
pub = {r["month"]: r for r in csv.DictReader(open(os.path.join(D, "summary", "system_month.csv")))}
for m, r in pub.items():
    for mine, key in ((allh, "ewt_all"), (hf5, "ewt_hf")):
        if m not in mine or abs(mine[m]["ewt"] - float(r[key])) > 0.001:
            errors.append(f"{m} {key}: ours {mine.get(m, {}).get('ewt')} against summary {r[key]}")

months = [r for r in csv.DictReader(open(os.path.join(D, "extract_months.csv"))) if r["month"] >= "2022-01"]
usable = {r["month"] for r in months if float(r["kept_share"]) >= MINKEEP}

# Check: the overview's frequent stop-hours (extract_freq.csv) are the line pages' (daily/, ewt_daily.py); see docstring
xf = {(m, rt): eb for m, rt, eb in con.execute(f"SELECT month, route, sum(eb) FROM c WHERE {F} GROUP BY ALL").fetchall()}
for m in sorted(usable):
    f = os.path.join(D, "daily", f"{m}.csv")
    if not os.path.exists(f):
        errors.append(f"{m}: usable month with no daily/{m}.csv (ewt_daily.py)")
        continue
    dl, waitless = {}, set()
    for r in csv.DictReader(open(f)):
        if r["eb"]:
            dl[r["route"]] = dl.get(r["route"], 0) + float(r["eb"])
            if r["swt"]:
                waitless.add("!" + r["route"])
    # a line whose hours never have a scheduled wait (one bus an hour at each stop, as the 714 BART Early Bird) has
    #   departures in daily/ but no cell here, since site_data.py keeps only cells with a scheduled and actual wait
    for rt in [rt for rt in dl if "!" + rt not in waitless and (m, rt) not in xf]:
        del dl[rt]
    a = sum(v for (mm, _), v in xf.items() if mm == m)
    ratio = sum(dl.values()) / a if a else 0
    xl = {rt for (mm, rt), v in xf.items() if mm == m and v > 0}
    if not 0.999 <= ratio <= 1.001 or xl != {rt for rt, v in dl.items() if v > 0}:
        errors.append(f"{m}: daily/ holds {ratio:.5f} of extract_freq.csv's frequent departures, or other lines ({sorted(xl ^ set(dl))})")
speed = {r["month"]: r for r in csv.DictReader(open(os.path.join(D, "summary_trip", "speed_system_month.csv")))}
newest = max(usable)
if newest not in speed:
    errors.append(f"speed is missing {newest}")

r3 = lambda v: None if v is None else round(v, 3)
def wq(pairs, qs=(0.1, 0.5, 0.9)):
    """Weighted quantiles of (value, weight) pairs: the smallest value whose cumulative weight reaches q of the total."""
    pairs = sorted((v, w) for v, w in pairs if v is not None and w > 0)
    tot, out, cum, i = sum(w for _, w in pairs), [], 0.0, 0
    if not pairs:
        return [None] * len(qs)
    for q in qs:
        while i < len(pairs) - 1 and cum + pairs[i][1] < q * tot:
            cum += pairs[i][1]; i += 1
        out.append(round(pairs[i][0], 3))
    return out
# Spread across lines, each month: lines' frequent-hour excess wait weighted by their scheduled departures
spread = {}
for route, month, swt, awt, eb in con.execute(f"SELECT route, month, swt, awt, eb FROM ({lines(F)})").fetchall():
    spread.setdefault(month, []).append((awt - swt, eb))
# and bus lines' speed, weighted by measured miles (speed_line_month.py)
bus = {r["route"] for r in csv.DictReader(open(os.path.join(D, "ref", "route_types.csv"))) if r["route_type"] == "3"}
slm = {}
slm_path = os.path.join(D, "summary_trip", "speed_line_month.csv")
for r in csv.DictReader(open(slm_path)) if os.path.exists(slm_path) else []:
    if r["route"] in bus and float(r["obs_hr"]) > 0:
        slm.setdefault(r["month"], []).append((float(r["miles"]) / float(r["obs_hr"]), float(r["miles"])))
r2 = lambda v: None if v in (None, "") else round(float(v), 2)
trend = []
for r in months:
    m = r["month"]
    f = freq.get(m) if m in usable else None
    s = speed.get(m) if m in usable else None
    trend.append({
        "month": m,
        "ewt": r3(f["ewt"]) if f else None,
        "missing": r3(f["mis"]) if f else None,
        "spacing": r3(f["ewt"] - f["mis"] - f["wgt"]) if f else None,
        "weighting": r3(f["wgt"]) if f else None,
        **dict(zip(["ewtP10", "ewtP50", "ewtP90"], wq(spread.get(m, [])) if f else [None] * 3)),
        **dict(zip(["mphP10", "mphP50", "mphP90"], wq(slm.get(m, [])) if s else [None] * 3)),
        "mph": r2(s["mph"]) if s else None,
        "mphTimetable": r2(s["mph_sch"]) if s else None,
    })

us = sorted(usable)
first12, last12 = us[:12], us[-12:]
# Days, read as the newest 1, 3 and 12 calendar months; each is compared with the period of the same length just
# before it, and that comparison is left out when the earlier period touches a month the outage made unusable.
newest_i = sorted(r["month"] for r in months).index(newest)
cal = sorted(r["month"] for r in months)
def shift(m, k):
    """The month k months before m."""
    y, mo = divmod(int(m[:4]) * 12 + int(m[5:]) - 1 - k, 12)
    return f"{y}-{mo + 1:02d}"
def back(n):
    """The n calendar months ending at the newest, whether or not the extract has them."""
    y, m, out = int(newest[:4]), int(newest[5:]), []
    for _ in range(n):
        out.append(f"{y}-{m:02d}"); y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return sorted(out)
# 5 years and Max (Bryan, 2026-11-09: "let's allow 5 years and max on any of the pages"): the last 60 calendar months,
# and every month the extract has. Both leave out the months the outage made unusable, and say how many days remain.
SPANS = {"30": back(1), "90": back(3), "365": back(12), "1825": back(60), "max": cal[:newest_i + 1]}
WINDOWS = {w: [m for m in ms if m in usable] for w, ms in SPANS.items()}
for w in ("30", "90", "365"):
    if WINDOWS[w] != SPANS[w]:
        errors.append(f"{w}-day window {SPANS[w]} holds an unusable or missing month")
def mdays(m):
    """Service dates in month m with frequent-hour data (ewt_daily.py's file), or its calendar days if there's no file."""
    f = os.path.join(D, "daily", f"{m}.csv")
    if os.path.exists(f):
        return len({r["sdate"] for r in csv.DictReader(open(f)) if r["eb"]})
    y, mo = int(m[:4]), int(m[5:])
    return (datetime.date(y + mo // 12, mo % 12 + 1, 1) - datetime.date(y, mo, 1)).days
inl = lambda ms: ",".join(repr(m) for m in ms)
# an hour whose frequent stop-hours have no tracked-trip timetable (tswt) gets no split of its excess wait: under the
#   10-minute rule (pre-send gate round 4) a few early and late hours hold only such cells
causes = lambda v: {"ewt": r3(v["ewt"]), "missing": r3(v["mis"]) if v["mis"] is not None else None,
                    "weighting": r3(v["wgt"]) if v["wgt"] is not None else None,
                    "spacing": r3(v["ewt"] - v["mis"] - v["wgt"]) if v["mis"] is not None and v["wgt"] is not None else None,
                    "scheduled": r3(v["swt"])}
def pooled(where, ms):  # by scheduled departures throughout, cityByDepartures' comparison
    """One figure over several months: within a line months pool by scheduled departures (Step II), then Step III."""
    return system(f"{where} AND month IN ({inl(ms)})", "'w'", "eb").get("w")
def per_line(where, ms, w="w"):
    q = f"SELECT route, awt - swt, eb, swt FROM ({lines(f'{where} AND month IN ({inl(ms)})', chr(39) + 'w' + chr(39), w)})"
    return {r: (e, eb, sw) for r, e, eb, sw in con.execute(q).fetchall()}
def hours(where, ms):
    """Each hour: the pooled causes, and across lines the 10th, 50th and 90th percentile of excess wait in minutes
    (p*) and as a percent of the timetable's own wait (q*, Bryan, 2026-11-09: "% longer than expected")."""
    q = f"SELECT hr, awt - swt, eb, swt FROM ({lines(f'{where} AND month IN ({inl(ms)})', 'hr')})"
    by, pct = {}, {}
    for h, e, eb, sw in con.execute(q).fetchall():
        by.setdefault(h, []).append((e, eb))
        if sw:
            pct.setdefault(h, []).append((100 * e / sw, eb))
    return [{"hour": h, **causes(v), **dict(zip(["p10", "p50", "p90"], wq(by.get(h, [])))),
             **dict(zip(["q10", "q50", "q90"], [round(x, 1) for x in wq(pct[h])] if pct.get(h) else []))}
            for h, v in sorted(system(f"{where} AND month IN ({inl(ms)})", "hr").items())]
mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
def previous(ms):
    """The same number of calendar months just before ms, or [] if any of them is unusable (the 511 outage)."""
    y, m = int(ms[0][:4]), int(ms[0][5:])
    out = []
    for _ in ms:
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        out.append(f"{y}-{m:02d}")
    out = sorted(out)
    return out if all(x in usable for x in out) else []
def why_none(ms):
    """Why a period has no comparison: the period before is in the outage, or before the data starts."""
    first = previous(ms) or None
    y, m = int(ms[0][:4]), int(ms[0][5:])
    y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return None if first else ("outage" if f"{y}-{m:02d}" in cal else "start")

windows, listed = {}, set()
anchor = {rt for rt, (e, eb, sw) in per_line(F, WINDOWS["365"]).items() if eb >= SMALL * len(WINDOWS["365"])}
for w, ms in WINDOWS.items():
    ago = previous(ms) if ms == SPANS[w] else []
    now_l, then_l = per_line(F, ms), (per_line(F, ago) if ago else {})
    dep_l = per_line(F, ms, "eb")  # the same stop-hours by scheduled departures, for muni_detail.py's check
    floor = SMALL * len(ms)
    rows = []
    for route in sorted(now_l):
        e, eb, sw = now_l[route]
        if eb < floor and not (route in anchor and eb >= floor / 10):
            continue
        b = then_l.get(route)
        if not math.isfinite(e) or (b and not math.isfinite(b[0])):
            errors.append(f"line {route}: figure not finite")
        rows.append({"line": route, "now": r3(e), "before": r3(b[0]) if ago and b and b[1] >= SMALL * len(ago) else None, "scheduled": int(eb), "swt": r3(sw),
                     "nowByDepartures": r3(dep_l[route][0])})
    if len({r["line"] for r in rows}) != len(rows):
        errors.append("a line appears twice")
    rows.sort(key=lambda r: (-r["now"], r["line"]))
    listed |= {r["line"] for r in rows}
    windows[w] = {
        "months": [ms[0], ms[-1]], "monthList": ms, "days": sum(mdays(m) for m in ms),
        "gap": [m for m in SPANS[w] if m not in usable and m >= ms[0]],
        "before": [ago[0], ago[-1]] if ago else None, "monthsBefore": len(ago),
        "noBefore": None if ago else ("start" if w in ("1825", "max") else why_none(ms)),
        "city": causes(pooled(F, ms)), "cityBefore": causes(pooled(F, ago)) if ago else None,
        "speed": {"now": mean([float(speed[m]["mph"]) for m in ms if m in speed]),
                  "before": mean([float(speed[m]["mph"]) for m in ago if m in speed]),
                  "timetable": mean([float(speed[m]["mph_sch"]) for m in ms if m in speed])},
        "lines": rows,
        "byHour": hours(F, ms),
        "lineHours": {r["line"]: [{"hour": x["hour"], "ewt": x["ewt"], "scheduled": x["scheduled"]} for x in hours(f"{F} AND route = '{r['line']}'", ms)] for r in rows},
    }
# The 12-month view's cards when the 12 months before touch the 511 outage (Bryan, 2026-11-10: "show how this compares
# to period before"): excess wait and speed over the months whose same calendar month a year earlier is usable,
# against those months a year earlier, e.g. March to October 2026 against March to October 2025. Both sides pool the
# way the cards do (excess wait by TfL's steps, speed the mean of monthly speeds). Left out when under 3 months match.
for w in ("365",):
    x = windows[w]
    if x["before"] is None and x["monthList"] == SPANS[w]:
        now_m = [m for m in x["monthList"] if shift(m, 12) in usable]
        then_m = [shift(m, 12) for m in now_m]
        if len(now_m) >= 3:
            sp = lambda ms: mean([float(speed[m]["mph"]) for m in ms if m in speed])
            x["match"] = {"months": [now_m[0], now_m[-1]], "monthsBefore": [then_m[0], then_m[-1]], "n": len(now_m),
                          "ewt": {"now": r3(pooled(F, now_m)["ewt"]), "before": r3(pooled(F, then_m)["ewt"])},
                          "speed": {"now": sp(now_m), "before": sp(then_m)}}
            if any(v is None or not math.isfinite(v) for k in ("ewt", "speed") for v in x["match"][k].values()):
                errors.append(f"{w}: matching-months comparison has a missing figure: {x['match']}")
            if now_m != x["monthList"][-len(now_m):]:
                errors.append(f"{w}: matching months {now_m} aren't one run ending at the newest month")
for w in ("30", "90"):
    if {r["line"] for r in windows[w]["lines"]} != {r["line"] for r in windows["365"]["lines"]}:
        errors.append(f"{w}-day list differs from the 365-day list: a line comes and goes with the period")
if windows["30"]["months"][0] != newest:
    errors.append("30-day window is not the newest month")

# Bus speed by line, from trip_rank.csv: the latest 12 usable months against the first 12
trank = {}
for r in csv.DictReader(open(os.path.join(D, "summary_trip", "trip_rank.csv"))):
    if r["mph_latest12"]:
        trank[r["route"]] = {"now": r2(r["mph_latest12"]), "first12": r2(r["mph_first12"]), "timetable": r2(r["mph_sched_latest12"])}
lspeed = {}
for r in csv.DictReader(open(os.path.join(D, "summary_trip", "speed_line_year.csv"))):
    lspeed.setdefault(r["route"], []).append({"year": int(r["yr"]), "mph": r2(r["mph"]), "timetable": r2(r["mph_sch"]),
                                              "months": int(r["months"])})

METRO = ["J", "K", "L", "M", "N", "T"]
def mode(l):
    if l in METRO: return "metro"
    if l == "F": return "streetcar"
    if l in ("PH", "PM", "CA"): return "cable"
    return "rapid" if l.endswith("R") else "bus"

# Each listed line's month by month, the same three causes as the citywide chart. A month whose frequent hours
# carried under a tenth of SMALL scheduled departures is left blank rather than drawn from a handful of hours.
series = {}
for route, month, swt, awt, eb, mis, teb, tob in con.execute(
        f"SELECT route, month, swt, awt, eb, mis, teb, tob FROM ({lines(F)}) ORDER BY route, month").fetchall():
    if route not in listed or eb < SMALL / 10:
        continue
    wgt = (tob - teb) if tob is not None and teb is not None else None
    series.setdefault(route, {})[month] = {"ewt": r3(awt - swt), "missing": r3(mis), "weighting": r3(wgt),
        "spacing": r3(awt - swt - mis - wgt) if mis is not None and wgt is not None else None}
blank = {"ewt": None, "missing": None, "spacing": None, "weighting": None}
# Each line's speed by month (speed_line_month.py: miles over observed hours, the line page's own figure; trains
# include the subway), for the Lines list's speed sparkline (Bryan, 2026-11-10: "add avg speed per line with a spark
# line"). Months the outage made unusable stay blank, as in the excess-wait trend.
line_mph = {}
for r in csv.DictReader(open(slm_path)) if os.path.exists(slm_path) else []:
    if r["month"] in usable and float(r["obs_hr"]) > 0:
        v = float(r["miles"]) / float(r["obs_hr"])
        if not 2 < v < 40:
            errors.append(f"speed {r['route']} {r['month']}: {v:.1f} mph out of range")
        line_mph[(r["route"], r["month"])] = round(v, 2)
def meta(l):
    return {"mode": mode(l), "frequent": l in listed,
            "trend": [{"month": t["month"], **(series.get(l, {}).get(t["month"]) or blank), "mph": line_mph.get((l, t["month"]))} for t in trend],
            "speedByYear": sorted(lspeed.get(l, []), key=lambda x: x["year"]) if mode(l) in ("bus", "rapid") else [],
            "speed12": trank.get(l) if mode(l) in ("bus", "rapid") else None}
line_meta = {l: meta(l) for l in sorted(listed)}
# The newest 30-day month's split pooled by scheduled departures, as the line pages' day rows pool it, for muni_detail.py's check
_nw = WINDOWS["30"][-1]
for route, month, swt, awt, eb, mis, teb, tob in con.execute(
        "SELECT route, month, swt, awt, eb, mis, teb, tob FROM (" + lines(F + f" AND month = '{_nw}'", "month", "eb") + ")").fetchall():
    if route in line_meta and mis is not None and teb is not None and tob is not None:
        line_meta[route]["splitByDepartures"] = {"month": month, "missing": r3(mis), "weighting": r3(tob - teb)}

# SFMTA's own share of scheduled service hours delivered (DataSF kc49-udxn, carried in ewt_analyze.py's intake file).
# It's published monthly with a lag, so each period takes the same number of its newest published months, and the
# period before takes the months just before those.
sdr = list(csv.DictReader(open(os.path.join(D, "service_delivered.csv"))))
sd = sorted((r["month"], float(r["actual"])) for r in sdr)
# the current fiscal year's target where DataSF carries it ahead of the actuals (fetch_service_delivered.py writes
#   service_delivered_target.json; 98.5% from July 2026, pre-send gate round 6, R6-1), else the newest month's own
#   target, since a window of 12 months can straddle two fiscal years' targets
_tp = os.path.join(D, "service_delivered_target.json")
_sd_t = [r["target"] for r in sorted(sdr, key=lambda r: r["month"]) if r["target"]]
targets = {str(json.load(open(_tp))["target"])} if os.path.exists(_tp) else set(_sd_t[-1:])
if len(targets) != 1:
    errors.append(f"service delivered: the last year's target isn't one value: {targets}")
if len(sd) < 24:
    errors.append(f"service delivered has {len(sd)} months")
# each month carries the target DataSF gives it (99% for July 2025 to June 2026, 98.5% before and after), so the chart
#   draws the target each month was held to, not one flat line at today's (Fable review, 2026-11-19)
sdt = {r["month"]: float(r["target"]) for r in sdr if r["target"]}
delivered = {"trend": [{"month": m, "share": v, **({"target": sdt[m]} if m in sdt else {})} for m, v in sd], "target": float(targets.pop()) if len(targets) == 1 else None, "windows": {}}
sdm = dict(sd)
for w, ms in SPANS.items():
    # the same number of calendar months as the period, ending at SFMTA's newest published month; Max is every month
    n = len(ms)
    end = sd[-1][0]
    span_cur = [m for m, _ in sd] if w == "max" else [shift(end, k) for k in range(n - 1, -1, -1)]
    # 5 years and Max have no period before, as on every other card (5 years back would hold the 2020 cuts)
    span_prev = [] if w in ("max", "1825") else [shift(end, k) for k in range(2 * n - 1, n - 1, -1)]
    cur = [(m, sdm[m]) for m in span_cur if m in sdm]
    prev = [(m, sdm[m]) for m in span_prev if m in sdm] if span_prev and all(m in sdm for m in span_prev) else []
    n_prev = len(prev)
    delivered["windows"][w] = {"months": [cur[0][0], cur[-1][0]], "now": round(sum(v for _, v in cur) / len(cur), 4),
                               "before": round(sum(v for _, v in prev) / n_prev, 4) if prev else None,
                               "beforeMonths": [prev[0][0], prev[-1][0]] if prev else None}

# SFMTA's average weekday boardings. Monthly only, so a period takes its newest published months and compares them with the same
# months a year earlier (365 days: the 12 before); 5 years and Max have nothing earlier to compare with.
# The systemwide figure is SFMTA's own (measure 428): the route file's sums run 10 to 17% below it from 2020-04 to
# 2022-06 (Fable review, 2026-11-09), so they only check it, in fetch_ridership.py. Route months newer than 428's
# newest are provisional and named on About.
routes_wk = {}
for r in csv.DictReader(open(os.path.join(D, "ridership.csv"))):
    if r["day"] == "Weekday":
        routes_wk[r["month"]] = routes_wk.get(r["month"], 0) + float(r["boardings"])
wk = {r["month"]: float(r["weekday"]) for r in csv.DictReader(open(os.path.join(D, "weekday_boardings_published.csv")))
      if r["month"] >= "2019-01"}
settled = max(wk)
provisional = sorted(m for m in routes_wk if m > settled)
rm = sorted(wk)
if len(rm) < 60 or any(not 30000 < wk[m] < 1200000 for m in rm):
    errors.append(f"ridership: {len(rm)} months, or a month out of range")
ridership = {"trend": [{"month": m, "weekday": round(wk[m])} for m in rm], "windows": {}, "provisional": provisional}
# Average daily boardings by year and day type (Bryan, 2026-11-10: "Add one more chart that shows ridership by day by
# year"). SFMTA publishes no systemwide Saturday or Sunday figure, so all three day types are the route file's sums,
# each month's sum over routes averaged over the year's settled months (provisional months are left out). Those sums
# run 10 to 17% below measure 428 from 2020-04 to 2022-06 for weekdays, the same gap for every day type we can check.
by_day = {}
for r in csv.DictReader(open(os.path.join(D, "ridership.csv"))):
    if r["month"] <= settled:
        k = (r["month"], r["day"])
        by_day[k] = by_day.get(k, 0) + float(r["boardings"])
years = {}
for (m, day), v in by_day.items():
    years.setdefault((m[:4], day), []).append((m, v))
ridership["byYear"] = [{"year": y, "day": day, "riders": round(sum(v for _, v in xs) / len(xs)),
                        "months": [min(m for m, _ in xs), max(m for m, _ in xs)]}
                       for (y, day), xs in sorted(years.items())]
# The same sums each month, for the chart's month-level lines (Bryan, 2026-11-10: "show month level detail here").
ridership["byMonth"] = [{"month": m, "day": day, "riders": round(v)} for (m, day), v in sorted(by_day.items())]
if {r["day"] for r in ridership["byYear"]} != {"Weekday", "Saturday", "Sunday"}:
    errors.append("ridership: by-year rows lack a day type")
# Max covers the months the wait data covers (the extract's first month on), so its riders weight the same months as
# its wait (Fable review, 2026-11-19); the route file reaches back to 2019.
MAX_RM = [m for m in rm if m >= cal[0]]
for w, n in {"30": 1, "90": 3, "365": 12, "1825": 60, "max": len(MAX_RM)}.items():
    cur = rm[-n:]
    prev = [] if w in ("1825", "max") else [shift(m, 12) for m in cur]
    ok = prev and all(m in wk for m in prev)
    ridership["windows"][w] = {"months": [cur[0], cur[-1]], "now": round(sum(wk[m] for m in cur) / len(cur)),
                               "before": round(sum(wk[m] for m in prev) / len(prev)) if ok else None,
                               "beforeMonths": [prev[0], prev[-1]] if ok else None}

# Each line's average weekday boardings over the period's settled months, from SFMTA's route file (Bryan, 2026-11-16,
# "Can you give a sense of ridership?"). The route file names a line by its code and name ("44
# O'Shaughnessy"); line_types.csv maps each name to the line it is (the cable cars' "61 California Cable Car" to CA,
# "OWL JUDAH" to NOWL). A name it doesn't list ("K L M N Owl") is left out and named, and two names mapping to one line
# fail (Fable review, 2026-11-19: keyed by the first word, the K L M N Owl's riders landed in the K). 30 days takes the
# newest settled month.
NAME_LINE = {r["name"]: r["route"] for r in csv.DictReader(open(os.path.join(D, "line_types.csv")))}
line_wk, line_names, unlisted = {}, {}, set()
for r in csv.DictReader(open(os.path.join(D, "ridership.csv"))):
    if r["day"] == "Weekday" and r["month"] <= settled:
        l_ = NAME_LINE.get(r["route"])
        if l_ is None:
            unlisted.add(r["route"])
            continue
        if line_names.setdefault(l_, r["route"]) != r["route"]:
            errors.append(f"ridership: {line_names[l_]!r} and {r['route']!r} both map to line {l_}")
        line_wk.setdefault(l_, {})[r["month"]] = float(r["boardings"])
if unlisted:
    print(f"ridership: route names not in line_types.csv, left out of the line figures: {sorted(unlisted)}", file=sys.stderr)
ridership["byLine"] = {}
for w, n in {"30": 1, "90": 3, "365": 12, "1825": 60, "max": len(MAX_RM)}.items():
    cur = rm[-n:]
    ridership["byLine"][w] = {l: round(sum(ms[m] for m in cur if m in ms) / len([m for m in cur if m in ms]))
                              for l, ms in sorted(line_wk.items()) if any(m in ms for m in cur)}
# The same months one by one, for each line's riders sparkline on the lines list.
ridership["lineMonths"] = {l: [[m, round(ms[m])] for m in rm if m in ms] for l, ms in sorted(line_wk.items())}
if not 40 < len(ridership["byLine"]["90"]) < 120 or ridership["byLine"]["90"].get("38R", 0) < 1000:
    errors.append(f"ridership: {len(ridership['byLine']['90'])} lines with weekday boardings, or the 38R missing")

# On time at timepoints on SFMTA's Connector and Owl lines (freq_rule.py; ontime_month.py's early_sf and
# late_sf: SFMTA's window, 1 minute early to 4 late, Charter §8A.103(c)). Bryan, 2026-11-17: "partly
# I want to line up with rider experience and partly I want to line up with what busses are held to". Counts add up
# across stops, hours and months; a line needs MINOT departures a month. OT_TARGET is SFMTA's on-time target.
OT_TARGET = 0.85
MINOT = 500
otm = {}
for m in cal:
    f = os.path.join(D, "ontime", f"{m}-stops.csv")  # by stop; summed here to the line and month
    if m in usable and not os.path.exists(f):
        errors.append(f"on-time: no file for {m}")
    dg = os.path.join(D, "diag", f"{m}.json")
    standin = os.path.exists(dg) and json.load(open(dg)).get("schedule_source", "511 historic GTFS") != "511 historic GTFS"
    if m in usable and os.path.exists(f) and not standin:
        for r in csv.DictReader(open(f)):
            a = otm.setdefault((m, r["route"]), [0, 0, 0])
            a[0] += int(r["n"]); a[1] += int(r["early_sf"]); a[2] += int(r["late_sf"])
def ot(ms, route=None):
    n = e = l = 0
    for (m, rt), (a, b, c) in otm.items():
        if m in ms and (route is None or rt == route):
            n += a; e += b; l += c
    return {"onTime": round((n - e - l) / n, 4), "early": round(e / n, 4), "late": round(l / n, 4), "n": n} if n else None
def ot_spread(m):
    """The 10th, 50th and 90th percentile line's on-time share in month m, lines weighted by departures."""
    v = [((a - b - c) / a, a) for (mm, rt), (a, b, c) in otm.items() if mm == m and a >= MINOT]
    return dict(zip(["p10", "p50", "p90"], [round(x, 4) for x in wq(v)])) if v else {}
ontime = {"trend": [{"month": m, **(ot([m]) or {}), **ot_spread(m)} for m in cal if m in usable], "windows": {},
          "window": [-1, 4], "target": OT_TARGET}
# SFMTA's own published systemwide on-time share (Controller's performance measures, DataSF 6dpt-7w23, every line and
#   hour, by departures), set beside ours on About only, with why the two differ (Bryan: "No need
#   to show SFMTA orange lines")
ontime["published"] = [{"from": r["from"], "to": r["to"], "value": float(r["value"]), "label": r["label"]}
                       for r in csv.DictReader(open(os.path.join(D, "optimizer", "sfmta_ontime_published.csv")))]
if not ontime["published"] or not all(0.3 < p["value"] < 0.95 for p in ontime["published"]):
    errors.append(f"on-time: SFMTA's published figures {ontime['published']}")
for w, ms in WINDOWS.items():
    ago = previous(ms) if ms == SPANS[w] else []
    routes = sorted({rt for (m, rt) in otm if m in ms})
    ontime["windows"][w] = {"now": ot(ms), "before": ot(ago) if ago else None,
        "lines": {rt: {"now": v, "before": ot(ago, rt) if ago else None} for rt in routes
                  if (v := ot(ms, rt)) and v["n"] >= MINOT * len(ms)}}
# Each line's on-time share month by month, for the less frequent lines' sparklines (Bryan, 2026-11-16, thread
# vkc7s4y92is2: "update this table to show sparklines same as above"). A month under MINOT departures is left out.
ontime["lineMonths"] = {rt: [[m, round((a - b - c) / a, 4)] for (m, r2), (a, b, c) in sorted(otm.items()) if r2 == rt and a >= MINOT]
                        for rt in sorted({rt for (_, rt) in otm})}
for t in ontime["trend"]:
    if t.get("onTime") is not None and not 0.3 < t["onTime"] < 0.95:
        errors.append(f"on-time {t['month']}: {t['onTime']} out of range")

# The less frequent lines the Lines page lists (every line with an on-time figure in a period that the period doesn't
# list as frequent) get their own entry in lines too, marked frequent: false, so muni_map.py draws them, muni_detail.py
# and speed_along_line.py give them speed, and each gets a line page (Bryan, 2026-11-10: "Can we show less frequent
# lines too?"). Their excess wait stays blank: their hours are judged on time.
for l in sorted({rt for x in ontime["windows"].values() for rt in x["lines"]} - listed):
    line_meta[l] = meta(l)

# Each line's speed by hour of day over each period (Bryan, 2026-11-10: "average speed by hour of day by line"), from
# speed_line_month.py --by-hour: the period's months pooled as miles over observed hours, all day types, the hour of
# each measured stretch's scheduled start. An hour with under MINHR observed bus-hours a month of the period is left
# out (a 6am with one or two trips). The L's bus substitute (LBUS) counts as the L, as on the line pages. Checks: the hours' miles and observed hours add back up to the line's months in
# speed_line_month.csv (to 0.1%, beyond the rows' rounding), so no hour is lost or counted twice; and their speed is
# the line pages' period speed from daily/ (ewt_daily.py) to 0.5%.
MINHR = 1
slh_path = os.path.join(D, "summary_trip", "speed_line_hour.csv")
slh = {}
if not os.path.exists(slh_path):
    errors.append("no summary_trip/speed_line_hour.csv (speed_line_month.py --by-hour, post_all.sh)")
for r in csv.DictReader(open(slh_path)) if os.path.exists(slh_path) else []:
    if r["month"] in usable and float(r["obs_hr"]) > 0:
        a = slh.setdefault((REN_PY.get(r["route"], r["route"]), r["month"]), {}).setdefault(int(r["hr"]), [0.0, 0.0, 0.0, 0.0])
        a[0] += float(r["miles"]); a[1] += float(r["obs_hr"])
        if r["sch_hr"] and float(r["sch_hr"]) > 0:  # the timetable's speed: the same miles over scheduled hours, rows with both
            a[2] += float(r["miles"]); a[3] += float(r["sch_hr"])
# Citywide bus speed by hour of day over each period (Bryan, 2026-11-10: "Can you also show Average speed by time of
# day?"), drawn under the overview's excess wait by hour: the bus lines (GTFS route_type 3, as the speed card and
# trip_analyze.py count them, the L's bus substitute as a line of its own) pooled as miles over observed hours, and the
# timetable's speed as the same miles over scheduled hours. Unlike the card, lines aren't reweighted by scheduled
# bus-hours: an hour's figure is every measured bus-mile in it over the hours they took, about 1% above the card
# (checked to 3%). An hour needs MINHR_CITY
# observed bus-hours a month of the period.
MINHR_CITY = 50
sbh_raw = {}
for r in csv.DictReader(open(slh_path)) if os.path.exists(slh_path) else []:
    if r["month"] in usable and r["route"] in bus and float(r["obs_hr"]) > 0 and r["sch_hr"]:
        a = sbh_raw.setdefault((r["month"], int(r["hr"])), [0.0, 0.0, 0.0])
        a[0] += float(r["miles"]); a[1] += float(r["obs_hr"]); a[2] += float(r["sch_hr"])
for w, x in windows.items():
    acc_ = {}
    for (m, h), v in sbh_raw.items():
        if m in x["monthList"]:
            a = acc_.setdefault(h, [0.0, 0.0, 0.0])
            for i in range(3):
                a[i] += v[i]
    x["speedByHour"] = [{"hour": h, "mph": round(mi / hr, 2), "mphTimetable": round(mi / sh, 2)}
                        for h, (mi, hr, sh) in sorted(acc_.items()) if hr >= MINHR_CITY * len(x["monthList"]) and sh > 0]
    hrs_ = [v["hour"] for v in x["speedByHour"]]
    if hrs_ != list(range(5, 23)) or any(not 4 < v["mph"] < 25 or not 4 < v["mphTimetable"] < 25 for v in x["speedByHour"]):
        errors.append(f"citywide speed by hour {w}: hours {hrs_} or a speed out of range")
    if x["speed"]["now"] is not None:
        tot = [sum(a[i] for a in acc_.values()) for i in (0, 1)]
        if tot[1] and abs(tot[0] / tot[1] / x["speed"]["now"] - 1) > 0.03:
            errors.append(f"citywide speed by hour {w}: {tot[0] / tot[1]:.2f} mph over all hours, the card {x['speed']['now']}")

slm_raw = {}
for r in csv.DictReader(open(slm_path)) if os.path.exists(slm_path) else []:
    if r["month"] in usable:
        k = (REN_PY.get(r["route"], r["route"]), r["month"])  # the L's bus substitute counted as the L, as daily/ does
        slm_raw[k] = tuple(a + float(r[c]) for a, c in zip(slm_raw.get(k, (0.0, 0.0)), ("miles", "obs_hr")))
# and the line pages' own figure: miles over hours in daily/<m>.csv (ewt_daily.py), which muni_detail.py pools
dmi = {}
for m in sorted(usable):
    f = os.path.join(D, "daily", f"{m}.csv")
    for r in csv.DictReader(open(f)) if os.path.exists(f) else []:
        if r["miles"] and r["obs_hr"]:
            a = dmi.setdefault((r["route"], m), [0.0, 0.0]); a[0] += float(r["miles"]); a[1] += float(r["obs_hr"])
for w, x in windows.items():
    ms, out_ = x["monthList"], {}
    for l in sorted(line_meta):
        acc_, tot = {}, [0.0, 0.0]
        for m in ms:
            for h, (mi, hr, smi, sh) in slh.get((l, m), {}).items():
                a = acc_.setdefault(h, [0.0, 0.0, 0.0, 0.0]); a[0] += mi; a[1] += hr; a[2] += smi; a[3] += sh
                tot[0] += mi; tot[1] += hr
        ref = [sum(slm_raw.get((l, m), (0, 0))[i] for m in ms) for i in (0, 1)]
        if any(abs(t - f) > 0.001 * f + 0.05 * len(ms) * 18 for t, f in zip(tot, ref)):  # rounding: 0.01 mile, 0.001 hour a row
            errors.append(f"speed by hour {l} {w}: hours pool to {tot}, the line's months to {ref}")
        dd = [sum(dmi.get((l, m), (0, 0))[i] for m in ms) for i in (0, 1)]
        if tot[1] and dd[1] and abs((tot[0] / tot[1]) / (dd[0] / dd[1]) - 1) > 0.005:
            errors.append(f"speed by hour {l} {w}: {tot[0] / tot[1]:.2f} mph over the hours, {dd[0] / dd[1]:.2f} in daily/")
        # mphTimetable (Bryan, 2026-11-16: "Can you also show speed and crowding by time of day?"):
        # the line page draws actual against the timetable, as the overview's citywide chart does
        rows_ = [{"hour": h, "mph": round(mi / hr, 2), "mphTimetable": round(smi / sh, 2) if sh else None}
                 for h, (mi, hr, smi, sh) in sorted(acc_.items()) if hr >= MINHR * len(ms)]
        for v in rows_:
            if v["mphTimetable"] is not None and not 2 < v["mphTimetable"] < 45:
                errors.append(f"speed by hour {l} {w} {v['hour']}: timetable {v['mphTimetable']} mph out of range")
            if not 2 < v["mph"] < 45:
                errors.append(f"speed by hour {l} {w} {v['hour']}: {v['mph']} mph out of range")
        if rows_:
            out_[l] = rows_
    x["lineSpeedHours"] = out_

# Excess wait by how far along the line a stop is (Bryan, 2026-11-10: "show excess wait by distance from start along
# each line. Show that it gets worse later on.", then "Plot each direction separately with the appropriate destination
# name"), moved here from ewt_by_route_position.py. A stop's position is its distance along its line and direction's
# shape in SFMTA's GTFS (stop_pos, after gtfs() above), 0 at the shape's start and 1 at its end, binned into tenths.
# Each tenth's swt and awt are averaged over data/muni-ewt/stops/<month>.csv
# (ewt_stops.py, frequent hours only) weighted by stop-hours (blocks), each direction apart, and ewt = awt - swt.
# A direction's destination is the most common trip_headsign on its most common stop pattern, its name GTFS directions.txt's.
# Stops that can't be placed are dropped; a month losing more than POSDROP of its stop-hours that way is left out,
# and a listed line losing more than LINEDROP of a period's fails. The systemwide figure leaves the cable cars out
# and their own pages have no chart (Fable review of ewt_by_route_position.py, 2026-11-10).
#
# Each line's scheduling rule (Bryan, 2026-11-10: "Show somewhere what the scheduling target is. Is it by gap or
# specific times?"): by SFMTA's line types (freq_rule.py), a frequent line is judged by the gap in every weekday clock
# hour 5:00 to 22:59 its busiest stop for that hour has a bus, and the typical gap is 60 over the median departures an
# hour; a Connector or Owl line is judged by the timetable, and carries its type.
POSDROP = 0.15
LINEDROP = 0.2  # a listed line losing more of a period's stop-hours than this to stops it can't place fails (posdrop below)
HEATOBS, HEATRATIO, HEATHOUR = 60, (0.75, 1.25), 6  # the heat maps' blank-cell rules and first hour, explained at heat()
CABLE = {"PH", "PM", "CA"}  # out of the system figure: turntables set their gaps and the feed sees 70-82% of them
# SFMTA's GTFS zip as the muni-gtfs step holds it, read in place (no unzipped copy to go stale or be missing on the VM)
FEED = os.path.join(ROOT, ".cache", "muni-gtfs", "muni_gtfs-current.zip")
def gtfs(name, feed=FEED):
    z = zipfile.ZipFile(feed)
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig", newline=""))
# Stop placement by distance along the line (Fable pipeline review, 2026-11-17): a stop is placed where it falls along
# its line and direction's shape in SFMTA's current GTFS, as a share of the shape's length: the shape most of that
# direction's trips run, or, for a stop more than OFFSHAPE feet from it, the next most run shape it is near among those
# carrying BRANCH of the direction's trips (the 38's V.A. Hospital and 48th Avenue branches beside Balboa and 33rd). So a stop on a short-turn or variant pattern, or one since retired, lands in the tenth it sits
# in, where ranking stops on today's main pattern dropped it (16% of the 38's stop-hours over 365 days, 28% of the 6's
# and 27% of the L's over 5 years). Stop coordinates come from the current feed, then SFMTA's September 2022 feed
# (.cache/muni-gtfs/hist/, the one retired_lines.py reads) for stops since retired; a line the current feed lacks takes
# its shape from the 2022 feed. A stop more than OFFSHAPE feet from every such shape is off today's line (a detour, or
# a stretch the line no longer runs: the 6's route through 2022) and left out, and so is a stop neither feed places;
# posdrop below counts both.
HIST_FEED = os.path.join(ROOT, ".cache", "muni-gtfs", "hist", "20220926.zip")
OFFSHAPE, GRID, BRANCH = 500, 2000, 0.1  # feet: furthest a stop sits from its line's shape; the projection's index cell; a branch's least share of trips
FT_LAT, FT_LON = 364000.0, 364000.0 * math.cos(math.radians(37.77))  # feet per degree in San Francisco
def line_shapes():
    """{(route, direction): [polylines, in feet, of the shapes carrying BRANCH of its trips, most run first]}, current
    feed first, then 2022's for a line the current one lacks."""
    out = {}
    for feed in (FEED, HIST_FEED):
        if not os.path.exists(feed):
            errors.append(f"stop placement: no GTFS feed at {feed}")
            continue
        n = {}
        for r in gtfs("trips.txt", feed):
            k = (REN_PY.get(r["route_id"], r["route_id"]), r["direction_id"])
            if k not in out and r["shape_id"]:
                c = n.setdefault(k, {}); c[r["shape_id"]] = c.get(r["shape_id"], 0) + 1
        want = {k: [s for s, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if v >= BRANCH * sum(c.values())] for k, c in n.items()}
        pts = {}
        for r in gtfs("shapes.txt", feed):
            pts.setdefault(r["shape_id"], []).append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]) * FT_LON, float(r["shape_pt_lat"]) * FT_LAT))
        for k, ss in want.items():
            lines_ = [[(x, y) for _, x, y in sorted(pts.get(s, []))] for s in ss]
            if any(len(l_) > 1 for l_ in lines_):
                out[k] = [l_ for l_ in lines_ if len(l_) > 1]
    return out
STOP_XY = {}
def stop_xy():
    if not STOP_XY:
        for feed in (HIST_FEED, FEED):  # the current feed's coordinates win
            if os.path.exists(feed):
                for r in gtfs("stops.txt", feed):
                    if r["stop_lat"] and r["stop_lon"]:
                        STOP_XY[r["stop_id"]] = (float(r["stop_lon"]) * FT_LON, float(r["stop_lat"]) * FT_LAT)
    return STOP_XY
_index, _pos = {}, {}
def stop_pos(key, sid):
    """Where stop sid falls along key's shape, 0 (first point) to 1 (last), or None when it can't be placed."""
    if (key, sid) in _pos:
        return _pos[(key, sid)]
    xy, p = stop_xy().get(sid), None
    for n, line in enumerate(shapes.get(key, []) if xy else []):
        if (key, n) not in _index:  # each segment, with the distance along the shape where it starts, in every grid cell it touches
            cells, along = {}, 0.0
            for (x0, y0), (x1, y1) in zip(line, line[1:]):
                L = math.hypot(x1 - x0, y1 - y0)
                for gx in range(int(min(x0, x1) // GRID), int(max(x0, x1) // GRID) + 1):
                    for gy in range(int(min(y0, y1) // GRID), int(max(y0, y1) // GRID) + 1):
                        cells.setdefault((gx, gy), []).append((x0, y0, x1, y1, L, along))
                along += L
            _index[(key, n)] = (cells, along)
        cells, total = _index[(key, n)]
        gx, gy, best = int(xy[0] // GRID), int(xy[1] // GRID), None
        for c in [(gx + i, gy + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]:
            for x0, y0, x1, y1, L, along in cells.get(c, ()):
                t = 0.0 if L == 0 else max(0.0, min(1.0, ((xy[0] - x0) * (x1 - x0) + (xy[1] - y0) * (y1 - y0)) / (L * L)))
                dd = math.hypot(xy[0] - x0 - t * (x1 - x0), xy[1] - y0 - t * (y1 - y0))
                if best is None or (dd, along + t * L) < best:
                    best = (dd, along + t * L)
        if best and best[0] <= OFFSHAPE and total > 0:
            p = min(1.0, best[1] / total)
            break
    _pos[(key, sid)] = p
    return p
pos_rows, pos_left, heads, sched, feed_span, heat_rows, posdrop = {}, [], {}, {}, None, {}, {}  # posdrop: {(month, line): [stop-hours placed, left out]}
if not os.path.exists(FEED):
    errors.append(f"no GTFS feed at {FEED}: run tools/muni/muni-gtfs.py")
else:
    # weekday service: what runs on the feed's last Wednesday, calendar.txt with calendar_dates.txt's exceptions applied
    names = set(zipfile.ZipFile(FEED).namelist())
    cal_rows = list(gtfs("calendar.txt"))
    exc = list(gtfs("calendar_dates.txt")) if "calendar_dates.txt" in names else []
    end = max([r["end_date"] for r in cal_rows] + [r["date"] for r in exc])
    iso = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"
    feed_span = [iso(min(r["start_date"] for r in cal_rows)), iso(end)]
    # The feed SFMTA publishes as current can end before the newest month scored (its calendar ran out and no newer
    # file was posted): said on About from feed_span, and printed here, not failed, since there is nothing newer to read.
    if feed_span[1] < newest + "-01":
        print(f"warning: SFMTA's current GTFS ends {feed_span[1]}, before the newest month scored ({newest})", file=sys.stderr)
    day = datetime.date(int(end[:4]), int(end[4:6]), int(end[6:]))
    day -= datetime.timedelta(days=(day.weekday() - 2) % 7)
    wed = day.strftime("%Y%m%d")
    weekday_sv = {r["service_id"] for r in cal_rows if r["wednesday"] == "1" and r["start_date"] <= wed <= r["end_date"]}
    weekday_sv |= {r["service_id"] for r in exc if r["date"] == wed and r["exception_type"] == "1"}
    weekday_sv -= {r["service_id"] for r in exc if r["date"] == wed and r["exception_type"] == "2"}
    if not weekday_sv:
        errors.append(f"schedule: no service runs on {wed}")
    dname = {(r["route_id"], r["direction_id"]): r["direction"] for r in gtfs("directions.txt")}
    trips, hsign, wk_trip = {}, {}, set()
    for r in gtfs("trips.txt"):
        trips[r["trip_id"]] = (REN_PY.get(r["route_id"], r["route_id"]), r["direction_id"])
        hsign[r["trip_id"]] = r["trip_headsign"].strip()
        if r["service_id"] in weekday_sv:
            wk_trip.add(r["trip_id"])
    seqs, deps = {}, {}
    for r in gtfs("stop_times.txt"):
        t = r["trip_id"]
        if t in trips:
            seqs.setdefault(t, []).append((int(r["stop_sequence"]), r["stop_id"]))
            if t in wk_trip and r["departure_time"]:
                hh, mm, ss = (int(x) for x in r["departure_time"].split(":"))
                k = (trips[t][0], trips[t][1], r["stop_id"])
                deps.setdefault(k, []).append(hh * 3600 + mm * 60 + ss)  # 24:00 and later: the night's owl trips, left out below
    patterns = {}
    for t, sq in seqs.items():
        pt = tuple(x[1] for x in sorted(sq))
        c = patterns.setdefault(trips[t], {}).setdefault(pt, {})
        c[hsign[t]] = c.get(hsign[t], 0) + 1
    for key, c in sorted(patterns.items()):
        pat = max(c.items(), key=lambda kv: (sum(kv[1].values()), kv[0]))  # most trips; ties broken by the pattern itself
        heads[key] = {"direction": dname.get(key, "").title(), "to": max(pat[1].items(), key=lambda kv: (kv[1], kv[0]))[0].replace("`", "'")}
    shapes = line_shapes()
    # each clock hour's busiest stop of the line. A frequent line (freq_rule.py, SFMTA's line types) is judged by the gap
    # in every hour it runs, so its gap hours are the weekday hours 5 am to 11 pm its busiest stop has a bus; a Connector
    # or Owl line has none, and its type names it instead.
    top = {}
    for (rt, d, sid), ts in deps.items():
        ts = sorted(ts)
        t = top.setdefault(rt, {})
        n_h = {}
        for x in ts:
            n_h[x // 3600] = n_h.get(x // 3600, 0) + 1
        for h, n in n_h.items():
            if h < 24:
                t[h] = max(t.get(h, 0), n)
    for rt, hrs in sorted(top.items()):
        fh = {h for h in range(5, 23) if hrs.get(h)} if is_frequent(rt) else set()
        spans_ = []
        for h in sorted(fh):
            if spans_ and spans_[-1][1] == h:
                spans_[-1][1] = h + 1
            else:
                spans_.append([h, h + 1])
        cnt = sorted(hrs[h] for h in fh)
        # daytime: minutes between buses at the line's busiest stop, 7am to 7pm, from the median hour the line runs in
        #   that span, frequent or not, for the overview's how-often-buses-come figure (Bryan, 2026-11-16, thread
        #   2aw0zfb68hnb: "some way to understand the expected wait time, not just the excess")
        day_ = sorted(hrs[h] for h in range(7, 19) if hrs.get(h))
        sched[rt] = {"gapHours": spans_, "type": LINE_TYPES.get(REN_PY.get(rt, rt), {}).get("sfmta_type"), "gap": int(60 / cnt[len(cnt) // 2] + 0.5) if cnt else None,
                     "daytime": round(60 / day_[len(day_) // 2], 1) if day_ else None}
    del seqs, patterns, deps
    for m in sorted(set(us) & set(SPANS["max"])):
        f = os.path.join(D, "stops", f"{m}.csv")
        if not os.path.exists(f):
            errors.append(f"position: no stops file for {m}")
            continue
        acc, kept, lost = {}, 0, 0
        for r in csv.DictReader(open(f)):
            b = int(r["blocks"])
            sid = r["stop"][1:] if len(r["stop"]) == 5 and r["stop"].startswith("1") else r["stop"]  # 511's 1-prefixed ids
            if not r["swt"] or not r["awt"]:
                continue  # a stop whose frequent hours saw no bus: no actual wait to place
            p = stop_pos((r["route"], r["dir"]), sid)
            pd = posdrop.setdefault((m, r["route"]), [0, 0])
            pd[p is None] += b
            if p is None:
                lost += b; continue
            kept += b
            a = acc.setdefault((r["route"], r["dir"], min(int(p * 10), 9)), [0, 0.0, 0.0, 0, 0])
            a[0] += b; a[1] += float(r["swt"]) * b; a[2] += float(r["awt"]) * b; a[3] += int(r["eb"]); a[4] += int(r["ob"])
        if not kept or lost / (kept + lost) > POSDROP:
            pos_left.append(m)
        else:
            pos_rows[m] = acc
            # the same stops by clock hour (stophours/<month>.csv.gz, ewt_stop_hours.py, whose hours add up to the
            # stops file), binned into the same tenths, for the line pages' heat maps
            fh = os.path.join(D, "stophours", f"{m}.csv.gz")
            if not os.path.exists(fh):
                errors.append(f"heat map: no stophours file for {m}")
                continue
            hacc = {}
            for r in csv.DictReader(io.TextIOWrapper(gzip.open(fh), encoding="utf-8")):
                if int(r["hr"]) < HEATHOUR or not r["swt"] or not r["awt"]:
                    continue
                sid = r["stop"][1:] if len(r["stop"]) == 5 and r["stop"].startswith("1") else r["stop"]
                p = stop_pos((r["route"], r["dir"]), sid)
                if p is None:
                    continue
                b = int(r["blocks"])
                a = hacc.setdefault((r["route"], r["dir"], min(int(p * 10), 9), int(r["hr"])), [0, 0.0, 0.0, 0, 0])
                a[0] += b; a[1] += float(r["swt"]) * b; a[2] += float(r["awt"]) * b; a[3] += int(r["eb"]); a[4] += int(r["ob"])
            heat_rows[m] = hacc
# A line-month that can't place more than LINEDROP of its stop-hours ran a route other than today's (the 6 through June
# 2025, 27 to 38% of its stop-hours on a stretch it no longer runs): its stops would sit at today's route's tenths with
# the waits of another route, so that month is left out of the line's along-the-line and heat-map figures and the
# system's, and named. Today's route must place today's stops, so one in the newest twelve months fails.
line_left = {k for k, (a, lo) in posdrop.items() if a + lo and lo / (a + lo) > LINEDROP}
for m, l in sorted(line_left):
    if m in windows["365"]["monthList"] and l in {r["line"] for r in windows["365"]["lines"]} - CABLE:
        errors.append(f"position {l} {m}: {posdrop[(m, l)][1] / sum(posdrop[(m, l)]):.0%} of its stop-hours can't be placed along today's line")
_shown = {r["line"] for x in windows.values() for r in x["lines"]} - CABLE
if line_left & {(m, l) for m, l in line_left if l in _shown}:
    print("position: listed line-months left out, off today's route:", ", ".join(f"{l} {m}" for m, l in sorted(line_left) if l in _shown), file=sys.stderr)
def tenths(ms, d, route=None):
    """Each tenth of direction d of the route (or every route) over months ms: blocks-weighted scheduled and actual
    wait, ewt, and the share of scheduled departures observed."""
    acc = {}
    for m in ms:
        for (rt, dd, t), a in pos_rows.get(m, {}).items():
            if dd == d and (rt == route if route else rt not in CABLE) and (m, rt) not in line_left:
                x = acc.setdefault(t, [0, 0.0, 0.0, 0, 0])
                for i in range(5):
                    x[i] += a[i]
    out = []
    for t, (b, sw, aw, eb, ob) in sorted(acc.items()):
        if b <= 0 or not all(math.isfinite(v) for v in (sw, aw)):
            errors.append(f"position {route or 'system'} {d} tenth {t}: blocks {b} or a figure not finite")
            continue
        out.append({"tenth": t, "ewt": r3((aw - sw) / b), "swt": r3(sw / b), "observed": round(ob / eb, 3) if eb else None, "blocks": b})
    return out
# Line pages' heat maps (Bryan, 2026-11-17: "an inbound and outbound by time and along route heat
# map"): each direction's excess wait by clock hour and tenth of the route, stop-hours weighted by blocks as tenths()
# does. [hour, tenth, ewt, blocks], sorted; blocks (the cell's stop-hours, its weight) lets muni_detail.py pool the
# map to tie it to the line's figure; each line also carries "blanked", the share of its stop-hours in blank cells.
# A cell is left blank, and the page says too few buses were tracked, when:
#   - it saw under HEATOBS buses over the period. 60 because one stray gap moves a thin cell's actual wait a lot: with
#     buses every 10 minutes, one 30-minute gap among 60 gaps between observed buses raises the cell's actual wait
#     (sum of squared gaps over twice their sum) by about half a minute, 5.48 against 5.0 (6,800 / 1,240), a sixth of
#     the map's 0 to 3 minute scale, and among 7 gaps by 3.3 minutes (1,500 / 180). The 8BX inbound at 10 am, 7 buses
#     seen of 42, printed 15.9;
#   - its observed buses are under 0.75 or over 1.25 of its scheduled ones (HEATRATIO). Kept stop-hours run 0.96 to
#     0.98 observed to scheduled from 2023 and 0.78 to 0.87 in 2022, so a cell outside that band is the feed or the
#     timetable failing there, not the service: at a line's first and last trips a stop's first bus has no gap to the
#     one before it (ewt_month.py), and the 28 inbound at 5 am, tenth 8, printed +6.2 minutes from 44% more buses seen
#     than scheduled;
# and hours before HEATHOUR are left out, as the by-hour chart this map replaced left them (muni.mjs hourChart), since
# 5 am is mostly a line's first trips.
def heat(ms, d, route):
    acc = {}
    for m in ms:
        for (rt, dd, t, h), a in heat_rows.get(m, {}).items():
            if rt == route and dd == d and (m, rt) not in line_left:
                x = acc.setdefault((h, t), [0, 0.0, 0.0, 0, 0])
                for i in range(5):
                    x[i] += a[i]
    out, blank = [], 0
    for (h, t), (b, sw, aw, eb, ob) in sorted(acc.items()):
        if ob < HEATOBS or not eb or not HEATRATIO[0] <= ob / eb <= HEATRATIO[1]:
            blank += b
            continue
        if not all(math.isfinite(v) for v in (sw, aw)):
            errors.append(f"heat map {route} {d} hour {h} tenth {t}: a figure not finite")
            continue
        out.append([h, t, round((aw - sw) / b, 2), b])
    return out, blank
def both_dirs(sysp, ms):
    """The overview's one along-the-route panel (Bryan, 2026-11-17: "Why split outbound vs
    inbound?"): each tenth's two directions combined, each weighted by its scheduled departures (eb) in that tenth."""
    eb = {}
    for m in ms:
        for (rt, dd, t), a in pos_rows.get(m, {}).items():
            if rt not in CABLE and (m, rt) not in line_left:
                eb[(dd, t)] = eb.get((dd, t), 0) + a[3]
    out = []
    for t in range(10):
        r = [(eb.get((d, t), 0), next((x for x in sysp[d] if x["tenth"] == t), None)) for d in ("0", "1")]
        r = [(e, x) for e, x in r if x and e > 0]
        if not r:
            errors.append(f"position both directions tenth {t}: no departures")
            continue
        n = sum(e for e, _ in r)
        out.append({"tenth": t, "ewt": r3(sum(e * x["ewt"] for e, x in r) / n), "swt": r3(sum(e * x["swt"] for e, x in r) / n), "departures": n})
    return out
heat_out = {}  # site/data/muni-heat.json: {period: {line: {direction: [[hour, tenth, minutes, stop-hours], ...], "blanked": share}}}
for w, x in windows.items():
    ms = [m for m in x["monthList"] if m in pos_rows]
    sysp = {d: tenths(ms, d) for d in ("0", "1")}
    sysp["both"] = both_dirs(sysp, ms)
    heat_out[w] = {}
    for r in x["lines"]:
        if r["line"] not in CABLE:
            hd = {d: heat(ms, d, r["line"]) for d in ("0", "1")}
            shown = sum(c[3] for v, _ in hd.values() for c in v)
            blank = sum(bl for _, bl in hd.values())
            # blanked: the share of the line's stop-hours (6 am on) in blank cells, which muni_detail.py's tie to the
            # line's figure allows for
            heat_out[w][r["line"]] = {**{d: v for d, (v, _) in hd.items()}, "blanked": round(blank / (shown + blank), 4) if shown + blank else None}
    # Check: no listed line loses more than LINEDROP of the stop-hours of the months it uses here to stops it can't place
    for r in x["lines"]:
        if r["line"] not in CABLE:
            k, lo = (sum(posdrop.get((m, r["line"]), (0, 0))[i] for m in ms if (m, r["line"]) not in line_left) for i in (0, 1))
            if k + lo and lo / (k + lo) > LINEDROP:
                errors.append(f"position {r['line']} {w}: {lo / (k + lo):.0%} of its stop-hours can't be placed along the line")
    for d, v in sysp.items():
        if len(v) != 10:
            errors.append(f"position {w}: system direction {d} has {len(v)} tenths, not 10")
    x["byPosition"] = {"months": [ms[0], ms[-1]] if ms else None, "leftOut": [m for m in x["monthList"] if m in pos_left],
                       "system": sysp,
                       "lines": {r["line"]: {d: {**heads.get((r["line"], d), {"direction": "", "to": ""}), "tenths": tenths(ms, d, r["line"])}
                                             for d in ("0", "1")} for r in x["lines"] if r["line"] not in CABLE}}
for l in line_meta:
    line_meta[l]["schedule"] = sched.get(l)
    if l in sched and sched[l]["gap"] is not None and not 1 <= sched[l]["gap"] <= 60:
        errors.append(f"schedule {l}: gap {sched[l]['gap']} min outside 1 to 60")
    if l in sched and is_frequent(l) == (sched[l]["type"] in ("Connector", "Owl")):
        errors.append(f"schedule {l}: SFMTA type {sched[l]['type']} against freq_rule.py")

# ---- Each line's crowding, buses an hour and SFMTA's service changes, month by month, and its crowding by hour ----
# Bryan, 2026-11-16 on a line's "Trends over time": "Show crowding also in the top level trends,
# and also show the number of busses midday and during peak hours, along with links to key service changes from MTA";
# on its "By hour of day": "Can you also show speed and crowding by time of day?"
#
# crowded: SFMTA's published percent of the line's trips crowded that month (sfmta_crowding.py, the optimizer's own
#   source; "Percentage of trips where vehicles are above capacity for 10% or more of the stops"). The L's figure is
#   SFMTA's LBUS row (the L ran as a bus for most of the series); SFMTA's combined KT, KLM and TBUS rows are left out.
#   Where SFMTA lists one route under two names in a month (the 6, May to July 2025), the month is their mean.
# busesPeak, busesMidday: weekday buses an hour each way from the timetable, the optimizer's own count
#   (optimizer_build.py monthly_service, restated here, not imported): eb_per_block in extract.csv, every hour, the mean
#   timetabled departures in a stop-direction-hour block over the month's weekdays; busesPeak is the busiest clock hour
#   6am to 8pm and busesMidday the mean of 10am to 3pm (blank unless every one of those hours has buses). Months the
#   511 outage made unusable stay blank. Check: the 44's weekday midday gap reproduces SFMTA's published change, every
#   12 minutes to every 10 from 10 June 2023, to 0.75 min, as the optimizer's build checks it.
# changes: SFMTA's service changes and new transit lanes on the line from data/muni-ewt/interventions.csv, dated from
#   the first trend month on, linked only where the announcement is in service_change_pages.json (pages opened, with
#   the date read). Approvals and "made permanent" rows are left out: nothing changed on the street that day.
SERVICE_MIDDAY, SERVICE_DAY = range(10, 15), range(6, 20)
SERVICE_CHECK = (("44", "2023-05", 12), ("44", "2023-07", 10))
CHANGE_KINDS = {"service_increase", "service_cut", "route_change", "rail_opening", "transit_lane", "quick_build_package"}
sfc_path = os.path.join(D, "optimizer", "sfmta_crowding.csv")
sfc = {}
for r in csv.DictReader(open(sfc_path)):
    rt = "L" if r["route"] == "LBUS" else r["route"]
    if rt in line_meta:
        v = float(r["pct"])
        if not 0 <= v <= 100:
            errors.append(f"SFMTA crowding {r['route']} {r['month']}: {v} out of 0 to 100")
        sfc.setdefault((rt, r["month"]), []).append(v)
# The full timetable (Bryan, 2026-11-16: "Please show the full timetable, including weekend"):
#   busesEvening, the weekday mean of 8 to 11pm (the clock hours 20 to 22, the optimizer's SCHED_WIN evening), and
#   busesSat and busesSun, the mean of 10am to 3pm on Saturdays and Sundays, the weekday midday's hours. Each needs
#   every one of its hours to have buses, as midday does.
SERVICE_EVENING = range(20, 23)
svc = {}
for rt, m, dt_, h, v in con.execute(f"""SELECT {REN} r, month, daytype, CAST(hr AS INT) h, eb_per_block FROM read_csv('{ext}', header=true, types={{'route': 'VARCHAR'}})
        WHERE eb_per_block IS NOT NULL AND eb_per_block > 0""").fetchall():
    if m in usable and rt in line_meta:
        svc.setdefault((rt, m, dt_), {})[h] = v
def mean_all(hrs, rng):
    v = [hrs[h] for h in rng if h in hrs]
    return round(sum(v) / len(v), 2) if len(v) == len(rng) else None
for l, x in line_meta.items():
    for t in x["trend"]:
        c, hrs = sfc.get((l, t["month"])), svc.get((l, t["month"], "weekday"), {})
        day = [hrs[h] for h in SERVICE_DAY if h in hrs]
        t["crowded"] = round(sum(c) / len(c), 1) if c else None
        t["busesPeak"] = round(max(day), 2) if day else None
        t["busesMidday"] = mean_all(hrs, SERVICE_MIDDAY)
        t["busesEvening"] = mean_all(hrs, SERVICE_EVENING)
        t["busesSat"] = mean_all(svc.get((l, t["month"], "saturday"), {}), SERVICE_MIDDAY)
        t["busesSun"] = mean_all(svc.get((l, t["month"], "sunday"), {}), SERVICE_MIDDAY)
        for k in ("busesPeak", "busesMidday", "busesEvening", "busesSat", "busesSun"):
            if t[k] is not None and not 0 < t[k] < 60:
                errors.append(f"buses an hour {l} {t['month']} {k}: {t[k]}")
for l, m, want in SERVICE_CHECK:
    v = next((t["busesMidday"] for t in line_meta.get(l, {}).get("trend", []) if t["month"] == m), None)
    if v is None or abs(60 / v - want) > 0.75:
        errors.append(f"buses an hour: the {l}'s weekday midday gap in {m} is {None if v is None else round(60 / v, 1)} min, SFMTA published {want}")
pages_path = os.path.join(D, "service_change_pages.json")
pages = json.load(open(pages_path))
first_month = trend[0]["month"]
for r in csv.DictReader(open(os.path.join(D, "interventions.csv"))):
    d_ = r["description"]
    if r["line"] not in line_meta or r["type"] not in CHANGE_KINDS or r["date"][:7] < first_month:
        continue
    if d_.startswith("Approved") or "made permanent" in d_:
        continue
    pg = pages.get(r["source_url"])
    if not pg:
        print(f"service change left off the {r['line']}: {r['date']} {r['source_url']} is not in service_change_pages.json", file=sys.stderr)
        continue
    line_meta[r["line"]].setdefault("changes", []).append({"date": r["date"], "text": d_, "url": pg["url"], "title": pg["title"], "read": pg["read"]})
for l, x in line_meta.items():
    x["changes"] = sorted(x.get("changes", []), key=lambda c: (c["date"], c["text"]))
# How full the buses are, from SFMTA's live occupancy levels in our 511 archive (crowding_levels.py, run on the VM).
#   Bryan, 2026-11-16: "Can you also show speed and crowding by time of day?"; :
#   "Do we have a sense of where the crowding is along the line too?", then "Can we show the live crowding level
#   instead as an area chart showing all four types, and use a separate chart for inbound vs. outbound"; thread
#   i3gvop8agcv7 on the overview: "Can you show crowding by time of day?".
# Each point is the share of in-service bus reads at each of SFMTA's levels, in percent, unmerged (Bryan, 2026-11-16,
#   : "Please keep all of the original categories"): empty, many seats, few seats, standing room,
#   crushed standing room, full, not accepting passengers. Weekdays only (crowding_levels.json's complete weekdays). crowdHours: each line and direction by
#   hour, 6am to 10pm, an hour with under CROWD_READS reads left out (crowding_by_hour.py's own floor); crowdAlong: by
#   tenth of the route, a direction kept only with all ten tenths at CROWD_READS reads; crowdByHour: every bus line
#   pooled by reads, for the overview.
CROWD_READS = 60
CROWD_KEYS = ("empty", "many_seats", "few_seats", "standing_room", "crushed", "full", "not_accepting")  # every level SFMTA sends, unmerged
CROWDED_KEYS = ("standing_room", "crushed", "full", "not_accepting")  # standing room only or fuller, optimizer_crowding.CROWDED
cl_dir = os.path.join(D, "optimizer")
_clj = json.load(open(os.path.join(cl_dir, "crowding_levels.json"))) if os.path.exists(os.path.join(cl_dir, "crowding_levels.json")) else {}
cl_days = _clj.get("complete_days", {}).get("weekday", [])
# an hour row's days are crowding_levels.py's hdays, the counted service days with good reads in that hour. A clock hour
#   short of snapshots (an archive gap) drops its own service day, but a day's late trips can still read in the next
#   morning's hour, so the count sits between the counted weekdays less those short in that hour and all counted
#   weekdays. crowding_update.py checks the exact figure against crowding_by_hour.py's.
cl_short = _clj.get("short_hours", {})
def hour_days_ok(h, n):
    return sum(1 for d in cl_days if f"{h:02d}" not in cl_short.get(d, [])) <= n <= len(cl_days)
def day_list(ds):
    """Days as words, '10, 11 and 12 November 2026', or '28, 30 November and 1 December 2026' across months."""
    if not ds:
        return ""
    d = [datetime.datetime.strptime(x, "%Y%m%d") for x in sorted(ds)]
    groups = []
    for x in d:
        if groups and (groups[-1][0].year, groups[-1][0].month) == (x.year, x.month):
            groups[-1].append(x)
        else:
            groups.append([x])
    words = []
    for i, g in enumerate(groups):
        for j, x in enumerate(g):
            words.append(str(x.day) + (f" {x.strftime('%B')}" + (f" {x.year}" if i == len(groups) - 1 else "") if j == len(g) - 1 else ""))
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"
def day_span(ds):
    """The weekdays crowding_levels.json counts, as a range and the gaps in it (the coordinator, 2026-11-16, before the
    list grew with the daily rebuild: "on N weekdays, 10 to 28 November 2026", naming only the missing weekdays, the
    full list in the hover title). days: '10 to 28 November 2026'; missing: '13 Nov missing, 511 outage', the weekdays
    in the range that failed the complete-day rule (crowding_levels.py: every hour 04:00-01:00 at SNAP_HOUR snapshots,
    which only an archive gap breaks); list: every day, for the title."""
    if not ds:
        return {"days": "", "missing": "", "list": ""}
    d = [datetime.datetime.strptime(x, "%Y%m%d").date() for x in sorted(ds)]
    a, b = d[0], d[-1]
    if a == b:
        rng = f"{a.day} {a.strftime('%B')} {a.year}"
    elif (a.year, a.month) == (b.year, b.month):
        rng = f"{a.day} to {b.day} {b.strftime('%B')} {b.year}"
    elif a.year == b.year:
        rng = f"{a.day} {a.strftime('%B')} to {b.day} {b.strftime('%B')} {b.year}"
    else:
        rng = f"{a.day} {a.strftime('%B')} {a.year} to {b.day} {b.strftime('%B')} {b.year}"
    have = set(d)
    gap = [a + datetime.timedelta(n) for n in range((b - a).days + 1)]
    gap = [x for x in gap if x.weekday() < 5 and x not in have]
    words = [str(x.day) + (f" {x.strftime('%b')}" if k == len(gap) - 1 or gap[k + 1].month != x.month else "") for k, x in enumerate(gap)]
    missing = "" if not words else (words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}") + " missing, 511 outage"
    return {"days": rng, "missing": missing, "list": day_list(ds)}
CROWD_DAYS = day_span(cl_days)
def shares(r):
    n = int(r["reads"]); c = [int(r[k]) for k in CROWD_KEYS]
    if sum(c) != n or n <= 0:
        errors.append(f"crowding levels {r['line']} {r['direction']}: levels add to {sum(c)}, reads {n}")
        return None
    # two decimals: the fullest levels (crushed, full, not accepting) sit well under 1%, and the zoomed chart under the
    #   crowding charts would show them in 0.1% steps
    return {k: round(100 * v / n, 2) for k, v in zip(CROWD_KEYS, c)}
city = {}
p_ = os.path.join(cl_dir, "crowding_levels_hour.csv")
for r in csv.DictReader(open(p_)) if os.path.exists(p_) else []:
    if r["day_type"] != "weekday" or not 6 <= int(r["hour"]) <= 22:
        continue
    if not hour_days_ok(int(r["hour"]), int(r["days"])):
        errors.append(f"crowding levels {r['line']} {r['hour']}: {r['days']} days, {len(cl_days)} counted in the json, short hours {cl_short}")
    a = city.setdefault(int(r["hour"]), {k: 0 for k in ("reads",) + CROWD_KEYS})
    for k in a:
        a[k] += int(r[k])
    if r["line"] in line_meta and int(r["reads"]) >= CROWD_READS and (sh := shares(r)):
        ch = line_meta[r["line"]].setdefault("crowdHours", {**CROWD_DAYS, "n": len(cl_days), "dirs": {}})
        ch["dirs"].setdefault(r["direction"], {**heads.get((r["line"], r["direction"]), {"direction": "", "to": ""}), "hours": []})["hours"].append({"hour": int(r["hour"]), **sh})
for x in line_meta.values():
    for v in x.get("crowdHours", {}).get("dirs", {}).values():
        v["hours"].sort(key=lambda h: h["hour"])
# crowdShare: each line's share of weekday in-service bus reads at standing room or fuller, every hour, both directions
#   pooled by reads, for the lines list's Crowded column (Bryan, 2026-11-16: "Can you add a column
#   for % crowded (standing room only or full)"). Lines with no counter, and the rail lines, have none.
crowd_share = {**CROWD_DAYS, "n": len(cl_days), "lines": {}}
for r in csv.DictReader(open(os.path.join(cl_dir, "crowding_levels_hour.csv"))) if os.path.exists(os.path.join(cl_dir, "crowding_levels_hour.csv")) else []:
    if r["day_type"] == "weekday":
        a = crowd_share["lines"].setdefault(r["line"], [0, 0]); a[0] += sum(int(r[k]) for k in CROWDED_KEYS); a[1] += int(r["reads"])
crowd_share["lines"] = {l: round(100 * c / n, 1) for l, (c, n) in sorted(crowd_share["lines"].items()) if n >= 10 * CROWD_READS}
crowd_by_hour = {**CROWD_DAYS, "n": len(cl_days), "hours": [{"hour": h, **shares({"line": "all", "direction": "", **{k: str(v) for k, v in a.items()}})} for h, a in sorted(city.items())]}
if city and [h["hour"] for h in crowd_by_hour["hours"]] != list(range(6, 23)):
    errors.append(f"citywide crowding by hour: hours {[h['hour'] for h in crowd_by_hour['hours']]}")
crowd_along = {}  # not `cal`, the month list the stand-in loop below reads (Fable review, 2026-11-19)
p_ = os.path.join(cl_dir, "crowding_levels_along.csv")
for r in csv.DictReader(open(p_)) if os.path.exists(p_) else []:
    if r["line"] in line_meta:
        if int(r["days"]) != len(cl_days):
            errors.append(f"crowding along {r['line']} {r['direction']} {r['tenth']}: {r['days']} days")
        crowd_along.setdefault((r["line"], r["direction"]), []).append(r)
for (l, d), v in sorted(crowd_along.items()):
    v.sort(key=lambda r: int(r["tenth"]))
    if [int(r["tenth"]) for r in v] != list(range(10)) or min(int(r["reads"]) for r in v) < CROWD_READS:
        continue
    ca = line_meta[l].setdefault("crowdAlong", {**CROWD_DAYS, "n": len(cl_days), "dirs": {}})
    ca["dirs"][d] = {**heads.get((l, d), {"direction": "", "to": ""}), "tenths": [{"tenth": int(r["tenth"]), **(shares(r) or {})} for r in v]}

# SFMTA's Muni Rider Survey, yearly share rating Muni service overall good or excellent (fetch_satisfaction.py).
satisfaction = [{"year": int(r["year"]), "pct": float(r["good_or_excellent_pct"])}
                for r in csv.DictReader(open(os.path.join(D, "satisfaction.csv")))]
if len(satisfaction) < 15 or any(not 0 <= x["pct"] <= 100 for x in satisfaction):
    errors.append(f"satisfaction: {len(satisfaction)} years, or a value out of range")

fq_share = sum(freq[m]["eb"] for m in last12) / sum(allh[m]["eb"] for m in last12)

# Checks against SFMTA, for About (ewt_analyze.py's intake files), so its sentences follow the data rather than holding
# numbers typed in once: headway adherence from this feed against SFMTA's published figure, over the usable months both
# have (ours_all_routes, every route as SFMTA's measure counts them), and by year how far the share of scheduled trips
# the feed tracked runs below SFMTA's service hours delivered (outage days left out on both sides).
ha = [r for r in csv.DictReader(open(os.path.join(D, "summary", "intake_headway_adherence.csv")))
      if r["published"] and r["month"] in usable]
tg = {}
for r in csv.DictReader(open(os.path.join(D, "summary", "intake_service_delivered.csv"))):
    if r["diff_trips_no_outage_days"] and r["month"] in usable:
        tg.setdefault(r["month"][:4], []).append(-float(r["diff_trips_no_outage_days"]))
# Months scored against a stand-in timetable: 511's archive carried no Muni timetable for them, so ewt_month.py used
# SFMTA's own GTFS as the Internet Archive captured it (make_sched.py; the diag file names the capture). The excess-wait
# and speed charts mark them and About names the capture.
standin = {}
for m in cal:
    dg = os.path.join(D, "diag", f"{m}.json")
    src_ = json.load(open(dg)).get("schedule_source", "511 historic GTFS") if os.path.exists(dg) else "511 historic GTFS"
    if src_ != "511 historic GTFS":
        standin[m] = src_
if standin and len(set(standin.values())) != 1:
    errors.append(f"stand-in months use more than one timetable: {standin}")
# every diag file that names a stand-in timetable is a stand-in month here, and the other way round
_diag_standin = set()
for dg in sorted(glob.glob(os.path.join(D, "diag", "20??-??.json"))):
    if json.load(open(dg)).get("schedule_source", "511 historic GTFS") != "511 historic GTFS":
        _diag_standin.add(os.path.basename(dg)[:7])
if set(standin) != _diag_standin & set(cal):
    errors.append(f"stand-in months {sorted(standin)} against the diag files' {sorted(_diag_standin)}")
if len(ha) < 12 or not tg:
    errors.append(f"checks against SFMTA: {len(ha)} headway months, {len(tg)} tracked-share years")
dropped = sorted(r["month"] for r in months if float(r["kept_share"]) < MINKEEP)
# ---- How often buses come, as riders meet it ----------------------------------
# Weekday riders (the 12-month byLine average) on frequent lines and on SFMTA's Connector and Owl lines, by
# freq_rule.py's line types (Bryan, 2026-11-17). Bryan, 2026-11-17: two bars,
# "Frequent arrivals (scheduled by gap)" and "Infrequent arrivals (scheduled by time)".
frequency = {"months": ridership["windows"]["365"]["months"],
             "frequentLines": sorted(l for l in ridership["byLine"]["365"] if is_frequent(l)),
             "connector": sorted(CONNECTOR, key=int), "owl": sorted(r for r in OWL if "-" not in r)}
frequency["frequent"] = sum(ridership["byLine"]["365"][l] for l in frequency["frequentLines"])
frequency["total"] = sum(ridership["byLine"]["365"].values())
frequency["infrequent"] = frequency["total"] - frequency["frequent"]
if not 0.9 < frequency["frequent"] / max(frequency["total"], 1) < 0.995:  # Connector and Owl lines carry about 2.5% of weekday riders
    errors.append(f"frequency: {frequency['frequent']} of {frequency['total']} weekday riders on frequent lines")
# each period's own split, so the chart follows the period switch (Bryan, 2026-11-17: "all charts
#   below should respect the date range")
frequency["windows"] = {}
for w_, bl in sorted(ridership["byLine"].items()):
    f_ = sum(v for l, v in bl.items() if is_frequent(l)); t_ = sum(bl.values())
    frequency["windows"][w_] = {"months": ridership["windows"][w_]["months"], "frequent": f_, "infrequent": t_ - f_, "total": t_}
    if not 0.9 < f_ / max(t_, 1) < 0.995:
        errors.append(f"frequency {w_}: {f_} of {t_} weekday riders on frequent lines")
# ---- Wait figures for the site: frequent hours only, each line by its weekday riders --------------------------
# Bryan, 2026-11-17, picked "Report TfL's way": wait figures cover only frequent lines, every line
# but SFMTA's Connector and Owl lines (freq_rule.py; ), by TfL's excess wait (extract_freq.csv), and
# Connector and Owl lines are reported by on time (ontime, above), so nothing assumes when riders arrive. Within a line its hours pool by riders on board (scheduled
# departures times load, Step II, as windows[w]["lines"]); citywide, each line counts by its weekday riders. Bryan, 2026-11-16,
# , asked whether citywide excess wait should count each scheduled bus once or each line by its
# weekday riders: "By riders". The weights are the line's average weekday boardings, the Riders column of the Lines list
# (ridership.byLine): a period's own figure for the period and for its year-before comparison, so the change holds the
# weights still, and the latest 12 months' for the monthly series and its spread. Only lines the Lines list shows with an
# excess wait count (listed: SMALL frequent departures a month), so a line with a stray frequent hour doesn't carry its
# whole ridership on it. Lines without boardings in SFMTA's route file drop out: the cable cars (never in it), the F
# (not since 2020-03) and the rail lines' bus substitutes; a month a line didn't run shares its weight among the rest.
def all_lines(ms, key="'w'"):
    """Each line's frequent-hour excess wait, scheduled wait and departures over months ms, by key."""
    return {(r, k): {"ewt": awt - swt, "swt": swt, "eb": eb} for r, k, swt, awt, eb in con.execute(
        f"SELECT route, {key}, swt, awt, eb FROM ({lines(f'{F} AND month IN ({inl(ms)})', key)})").fetchall()}
def all_city(ms, key="'w'", route=None):
    """TfL's Step III by key over months ms (citywide, or one line's with route): excess wait, its split and scheduled wait."""
    rw = f" AND route = '{route}'" if route else ""
    return {k: causes(v) for k, v in system(f"{F} AND month IN ({inl(ms)}){rw}", key).items()}
con.execute(f"""CREATE OR REPLACE TABLE c AS SELECT *, route || '|' || month rmonth,
  route || '|' || CAST(hr AS VARCHAR) rhr, route || '|w' rwin FROM c""")
RIDER_KEYS = ("ewt", "scheduled")
SPLIT_KEYS = ("missing", "weighting")
RIDER_COVER = 0.92  # the lines left out above carry about 6% of frequent departures; more means a line lost its riders
RIDER_COVER_HR = 0.88  # by hour: the cable cars, which have no riders in SFMTA's route file, carry more of some hours' departures
SPLIT_COVER = 0.9   # riders on lines whose figure has a split (a tracked-trip timetable), for a citywide split
def per_line(ms, key):
    """Each line's all_city figures and departures over months ms: {k: {route: v}}, key one of month, hr, w."""
    col, conv = {"month": ("rmonth", str), "hr": ("rhr", int), "w": ("rwin", str)}[key]
    eb = {(r, k): v["eb"] for (r, k), v in all_lines(ms, {"month": "month", "hr": "hr", "w": "'w'"}[key]).items()}
    out_ = {}
    for rk, v in all_city(ms, col).items():
        r, k = rk.split("|", 1)
        out_.setdefault(conv(k), {})[r] = {**v, "eb": eb.get((r, conv(k)), 0.0)}
    return out_
def by_riders(ms, key, wts, label, keep):
    """Citywide by key over months ms, the lines in keep weighted by their weekday riders wts; plus the spread across
    lines, rider-weighted, as {k: [(ewt, riders)]}. The split averages over the lines that have one, and spacing is
    what's left, so the parts add up to the figure."""
    out_, spread = {}, {}
    for k, ls in sorted(per_line(ms, key).items()):
        ls = {r: v for r, v in ls.items() if r in keep and v["ewt"] is not None}
        have = {r: v for r, v in ls.items() if wts.get(r)}
        eb_all, eb_have = sum(v["eb"] for v in ls.values()), sum(v["eb"] for v in have.values())
        if not have:
            continue
        if eb_all and eb_have / eb_all < (RIDER_COVER_HR if key == "hr" else RIDER_COVER):
            errors.append(f"wait {label} {k}: lines with weekday riders carry {eb_have / eb_all:.1%} of frequent departures")
        tot = sum(wts[r] for r in have)
        o = {f: r3(sum(v[f] * wts[r] for r, v in have.items()) / tot) for f in RIDER_KEYS}
        sp = {r: v for r, v in have.items() if v["missing"] is not None and v["weighting"] is not None}
        n_sp = sum(wts[r] for r in sp)
        if n_sp >= SPLIT_COVER * tot:
            for f in SPLIT_KEYS:
                o[f] = r3(sum(v[f] * wts[r] for r, v in sp.items()) / n_sp)
            o["spacing"] = r3(o["ewt"] - o["missing"] - o["weighting"])
        else:
            o.update({"missing": None, "weighting": None, "spacing": None})
        o["riders"] = int(tot)
        out_[k] = o
        spread[k] = [(v["ewt"], wts[r]) for r, v in have.items()]
    return out_, spread
W_TREND = ridership["byLine"]["365"]
all_trend, all_spread = by_riders(sorted(usable), "month", W_TREND, "trend", listed)
all_service = {"trend": [{"month": t["month"], **(all_trend.get(t["month"]) or {}),
                          **dict(zip(["ewtP10", "ewtP50", "ewtP90"], wq(all_spread.get(t["month"], [])) if t["month"] in all_trend else [None] * 3))}
                         for t in trend],
               "windows": {}}
ot_lines = lambda w: ontime["windows"][w]["lines"]
# The Lines list: one row a line. A line the period lists as frequent shows its frequent-hour excess wait (as
# windows[w]["lines"]); any other line shows on time in its timetabled hours, in SFMTA's window, and no excess wait.
for w, ms in WINDOWS.items():
    ago = previous(ms) if ms == SPANS[w] else []
    freq_rows = {r["line"]: r for r in windows[w]["lines"]}
    rows = []
    for route in sorted(set(freq_rows) | set(ot_lines(w))):
        f_, o = freq_rows.get(route), ot_lines(w).get(route, {})
        now_o, bef_o = o.get("now") or {}, o.get("before") or {}
        # the cable cars show no wait: they're out of the citywide figure (CABLE), and 511 tracks only about 80% of
        #   their scheduled trips in frequent hours, so their excess wait is mostly buses 511 didn't see
        cable = f_ is not None and mode(route) == "cable"
        if cable:
            f_ = None
        row = {"line": route, "show": "none" if cable else "wait" if f_ else "onTime",
               "now": f_["now"] if f_ else None, "before": f_["before"] if f_ else None,
               "swt": f_["swt"] if f_ else None, "scheduled": f_["scheduled"] if f_ else None,
               "onTime": now_o.get("onTime"), "onTimeBefore": bef_o.get("onTime"),
               "early": now_o.get("early"), "late": now_o.get("late"), "otN": now_o.get("n")}
        if row["show"] == "wait" and (row["now"] is None or not -1 < row["now"] < 30):
            errors.append(f"lines list {w} line {route}: excess wait {row['now']}")
        if row["show"] == "none" and mode(route) != "cable":
            errors.append(f"lines list {w} line {route}: no figure shown")
        if row["show"] == "onTime" and row["onTime"] is None:
            errors.append(f"lines list {w} line {route}: neither an excess wait nor an on-time figure")
        rows.append(row)
    wts = ridership["byLine"][w]
    keep = set(freq_rows)
    hrs, hl = by_riders(ms, "hr", wts, f"{w} by hour", keep)
    city = by_riders(ms, "w", wts, w, keep)[0].get("w")
    # for the record: the same lines' frequent hours counting each scheduled bus once, against the rider weighting
    same = sorted(r for r in keep if wts.get(r))
    by_dep = pooled(f"{F} AND route IN ({inl(same)})", ms)
    all_service["windows"][w] = {
        "city": city, "cityByDepartures": r3(by_dep["ewt"]) if by_dep else None, "cityLines": len(same), "cityBefore": by_riders(ago, "w", wts, f"{w} before", keep)[0].get("w") if ago else None,
        "riderMonths": ridership["windows"][w]["months"], "lines": rows,
        "byHour": [{"hour": h, **v, **dict(zip(["p10", "p50", "p90"], wq(hl.get(h, []))))} for h, v in sorted(hrs.items())],
    }
    # the rider-weighted figure sits within its lines, and the split adds back up to it
    lo_hi = [r["now"] for r in rows if r["now"] is not None]
    if not min(lo_hi) - 0.01 <= city["ewt"] <= max(lo_hi) + 0.01:
        errors.append(f"wait {w}: citywide {city['ewt']} outside its lines {min(lo_hi)} to {max(lo_hi)}")
    if city["spacing"] is None:
        errors.append(f"wait {w}: no citywide split")
    for k, v in [("w", city)] + [(h["hour"], h) for h in all_service["windows"][w]["byHour"]]:
        if v["spacing"] is not None and abs(v["spacing"] + v["missing"] + v["weighting"] - v["ewt"]) > 0.002:
            errors.append(f"wait {w} {k}: the split doesn't add up to {v['ewt']}")
all_lines_months = {}
for (r, m), v in sorted(all_lines(sorted(usable), "month").items()):
    if r in listed:
        all_lines_months.setdefault(r, []).append((m, r3(v["ewt"])))
# Each frequent line's page: its excess wait by month and by hour, split as the overview's (site/src/pages/transportation-muni-line.mjs)
all_service["lineTrend"] = {}
for l in sorted(listed):
    lt = all_city(sorted(usable), "month", route=l)
    all_service["lineTrend"][l] = [{"month": m, **lt[m]} for m in sorted(lt)]
    for w, ms in WINDOWS.items():
        lh = all_city(ms, "hr", route=l)
        all_service["windows"][w].setdefault("lineHours", {})[l] = [{"hour": h, **v} for h, v in sorted(lh.items())]
    # within a line the split adds back up to its figure, and the month matches the Lines list's sparkline
    lm = dict(all_lines_months.get(l, []))
    for t in all_service["lineTrend"][l]:
        if t["spacing"] is not None and abs(t["spacing"] + t["missing"] + t["weighting"] - t["ewt"]) > 0.01:
            errors.append(f"wait line {l} {t['month']}: the split doesn't add up to {t['ewt']}")
        if t["month"] in lm and abs(lm[t["month"]] - t["ewt"]) > 0.002:
            errors.append(f"wait line {l} {t['month']}: {t['ewt']} on its page, {lm[t['month']]} on the Lines list")
all_service["lineMonths"] = {r: [[m, e] for m, e in v] for r, v in sorted(all_lines_months.items())}
# Check: the citywide figure is the Lines list's own excess waits weighted by its Riders column, line for line, and
# every line the list shows with an excess wait is a frequent line (none is an hours-run-to-a-timetable figure)
for w in WINDOWS:
    _rw = [(r["now"], n) for r in all_service["windows"][w]["lines"] if r["now"] is not None and (n := ridership["byLine"][w].get(r["line"]))]
    _c = all_service["windows"][w]["city"]["ewt"]
    if _rw and abs(sum(e * n for e, n in _rw) / sum(n for _, n in _rw) - _c) > 0.002:
        errors.append(f"wait {w}: citywide {_c} against the Lines list weighted by riders "
                      f"{sum(e * n for e, n in _rw) / sum(n for _, n in _rw):.3f}")
    if any(r["now"] is not None and r["line"] not in listed for r in all_service["windows"][w]["lines"]):
        errors.append(f"wait {w}: an excess wait on a line that isn't frequent")
# For the record: how many frequent line-hours (line, day type, hour) of the latest 12 months had a load of their own,
#   took their line's average (the departure weight), or have no readings on the line at all
_oc = con.execute(f"""SELECT count(*) FILTER (WHERE NOT f AND NOT n), count(*) FILTER (WHERE f), count(*) FILTER (WHERE n),
  sum(eb) FILTER (WHERE f) / sum(eb), sum(eb) FILTER (WHERE n) / sum(eb) FROM (SELECT route, daytype, hr, bool_or(w_fill) f,
  bool_or(w_none) n, sum(eb) eb FROM c WHERE {F} AND month IN ({inl(WINDOWS['365'])}) GROUP BY ALL)""").fetchone()
print(f"riders on board ({LOAD_MAP} load map): {_oc[0]} line-hours with their own load, {_oc[1]} on their line's average "
      f"({_oc[3]:.1%} of departures), {_oc[2]} on lines with no readings ({_oc[4]:.1%} of departures)")
# For the record, not the page: the same lines' frequent hours counting each scheduled bus once instead
_a = all_service["windows"]["365"]
print(f"wait, 365 days, frequent hours, {_a['cityLines']} lines: {_a['city']['ewt']} min by weekday riders, "
      f"{_a['cityByDepartures']} by scheduled departures; on time {ontime['windows']['365']['now']}")

# Steps in 511's tracking that move the missing-bus part of the wait (data/muni-ewt/optimizer/series_steps.csv, line
#   "all"; the checks run are in its note column): the overview's cause chart notes the latest one
tracking_steps = sorted(r["month"] for r in csv.DictReader(open(os.path.join(D, "optimizer", "series_steps.csv"))) if r["line"] == "all")
if not tracking_steps:
    errors.append("series_steps.csv: no citywide tracking step")
w30 = windows["30"]
out = {
    "trackingSteps": tracking_steps,
    "allService": all_service,
    "windows": windows,
    "trend": trend,
    "delivered": delivered,
    "ridership": ridership,
    "ontime": ontime,
    "satisfaction": satisfaction,
    "crowdByHour": crowd_by_hour,
    "crowdShare": crowd_share,
    "frequency": frequency,
    "lines": line_meta,
    "smallCount": SMALL,
    "about": {
        "first12": [first12[0], first12[-1]], "last12": [last12[0], last12[-1]], "dropped": dropped,
        "frequentShareLast12": round(fq_share, 3),
        "allHoursNow": r3(allh[newest]["ewt"]), "londonLineNow": r3(hf5[newest]["ewt"]),
        "speedLines": int(speed[newest]["lines"]),
        "headwayCheck": {"months": len(ha), "first": ha[0]["month"], "last": ha[-1]["month"],
                         "points": round(100 * sum(float(r["ours_all_routes"]) - float(r["published"]) for r in ha) / len(ha), 1)} if ha else None,
        "trackedGap": {y: round(100 * sum(v) / len(v), 1) for y, v in sorted(tg.items())},
        "schedule": feed_span,
        "standin": {"months": sorted(standin), "capture": sorted(set(standin.values()))[0] if standin else None},
    },
}
# read: the date the newest data in this file was read, for the pages' "Data updated" line (Bryan, 2026-11-09:
#   "each report that has data that gets updated should have up top a very short blurb that just says when the data
#   was last updated"). The newest of: the date each 511 month used was read (read_511.csv, its DONE marker's date,
#   written by vm_local.sh), the date SFMTA's crowding file was read (sfmta_crowding_read.json), and for the occupancy
#   days from our archive the day after the newest one counted (crowding_update.py counts a service day once it has
#   ended, and the daily refresh reads it the next morning). Never the run date, so a rerun on the same inputs writes
#   the same bytes.
_reads = []
_r511 = os.path.join(D, "read_511.csv")
if os.path.exists(_r511):
    _reads += [r["read"] for r in csv.DictReader(open(_r511)) if r["month"] in set(cal)]
if not _reads or set(cal) - {r["month"] for r in csv.DictReader(open(_r511))}:
    errors.append(f"read date: read_511.csv lacks a month the extract holds")
_sfc_read = os.path.join(D, "optimizer", "sfmta_crowding_read.json")
if os.path.exists(_sfc_read):
    _reads.append(json.load(open(_sfc_read))["read"])
_cl_all = cl_days + _clj.get("complete_days", {}).get("weekend", [])  # weekends too, so a weekend doesn't age the date (code review, 2026-11-19)
if _cl_all:
    _reads.append((datetime.datetime.strptime(max(_cl_all), "%Y%m%d").date() + datetime.timedelta(days=1)).isoformat())
out["read"] = max(_reads) if _reads else None
if out["read"] and not "2026-01-01" <= out["read"] <= datetime.date.today().isoformat():
    errors.append(f"read date {out['read']} out of range")
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
if LOAD_MAP != "central":  # the sensitivity run prints its figures and writes nothing
    sys.exit(0)
# the heat maps' cells go in a file of their own, one line a period, so muni.json stays readable
HEAT_OUT = os.path.join(ROOT, "site", "data", "muni-heat.json")
for path_, text in ((OUT, json.dumps(out, indent=1, sort_keys=True) + "\n"),
                    (HEAT_OUT, "{\n" + ",\n".join(f"{json.dumps(w)}: {json.dumps(heat_out[w], sort_keys=True, separators=(',', ':'))}" for w in sorted(heat_out)) + "\n}\n")):
    old = open(path_).read() if os.path.exists(path_) else None
    if text != old:
        open(path_, "w").write(text)
        print("wrote", path_)
    else:
        print("unchanged", path_)
for w, x in windows.items():
    bp = x["byPosition"]
    for d in ("0", "1"):
        dl = [v[d]["tenths"] for v in bp["lines"].values() if len(v[d]["tenths"]) >= 2]
        print(f"  position dir {d} {bp['months']}, left out {bp['leftOut']}: " + " ".join(str(t["ewt"]) for t in bp["system"][d])
              + f"; rising on {sum(1 for v in dl if v[-1]['ewt'] > v[0]['ewt'])} of {len(dl)} lines")
    a_ = all_service["windows"][w]
    print(f"{w} days {x['months']}: excess wait by riders {a_['city']['ewt']} against {(a_['cityBefore'] or {}).get('ewt')} "
          f"({a_['cityLines']} lines; by departures on them {a_['cityByDepartures']}); speed {x['speed']['now']} against {x['speed']['before']}; {len(x['lines'])} lines")
