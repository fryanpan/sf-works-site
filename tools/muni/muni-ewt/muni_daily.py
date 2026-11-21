"""Write site/data/muni-daily.json: Muni's excess wait, bus speed and running time by service date, one series from two sources.

Bryan, 2026-11-12: the dashboard's figures update daily. 511's monthly record of observed
stop arrivals (data/muni-ewt/daily/<m>.csv, from the muni-511 step) covers every month 511 has posted; the days after
the newest one come from our realtime archive (data/muni-ewt/rt/daily/<m>.csv, rt_daily.py), computed by the same
scripts (ewt_month.py, trip_time.py, ewt_daily.py). A month 511 has posted always uses 511's record, so once a month
posts its archive days drop out of the series (they stay in data/muni-ewt/rt/ for the comparison). Each day carries
its source, "511" or "rt-archive", and the file carries the label the page shows beside archive days.

Pooling, the same for both sources and as muni_detail.py pools a line's points: scheduled wait by scheduled departures
(eb), actual wait by the scheduled departures of the hours a bus was seen (eba), excess wait their difference, over
the frequent stop-hours ewt_daily.py keeps (05:00 to 22:59), every line. Speed and running time are bus lines only
(route_type 3 in data/muni-ewt/ref/route_types.csv), as trip_analyze.py's citywide figures are: speed is measured
miles over observed hours, running time observed over scheduled hours minus one. A month whose feed kept under 60%
of departures (extract_months.csv) is left out, as site_data.py leaves it out.
Cable cars are left out of the citywide figures on every day, both sources (CITY_EXCLUDE): 511's realtime feed
carries almost no cable car positions (1,414 rows on 11 November 2026, against every bus's thousands), so the
archive days have none, and with them in on 511's days the series would step down about 0.18 minute at the source
change (Fable review 2026-11-13: October weekdays pool to 1.459 with them, 1.278 without). Their own line series
stop at the newest 511 month.

"updated" is the date the newest figures' data was read: the newest read date of an archive day in the series, or,
while no archive day is in it, the date the newest 511 month's daily file was built is unknown here, so it is null.

Series: "days", the citywide figure for each date of the last DAYS_KEPT; "lines", each line muni.json lists, for the
last LINE_DAYS; "last30" and "previous30", the 30 dates up to the newest and the 30 before, pooled, citywide and by
line, with how many of them are archive days. "comparison" carries the summary of each rt/compare-<m>.json, the
score of the archive days against 511's record once 511 posts the month, for the About page.

Checks before writing (a failure exits 1 and leaves the old file): every date once and in order; no archive day in a
month 511 has posted; the newest 511 month pooled from its days within TOL_EWT minute of muni.json's excess wait for
that month, TOL_MPH of its speed and TOL_RUN of trip_analyze.py's running time; every listed line present.
Idempotent: no run date written; "updated" moves only when new data is read. Reaches no network.
Usage: python3 tools/muni/muni-ewt/muni_daily.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, glob, json, os, sys

ROOT = paths.ROOT
D = os.path.join(ROOT, "data", "muni-ewt")
OUT = os.path.join(ROOT, "site", "data", "muni-daily.json")
DAYS_KEPT, LINE_DAYS, MIN_EB, MINKEEP = 400, 120, 30, 0.6
TOL_EWT, TOL_MPH, TOL_RUN, TOL_EB = 0.06, 0.4, 0.01, 0.05
CITY_EXCLUDE = {"CA", "PH", "PM"}  # cable cars: see the docstring
REN = {"C": "CA", "L-OWL": "LOWL", "N-OWL": "NOWL", "LBUS": "L"}
LABEL = {"511": "511's record of observed stop arrivals", "rt-archive": "Rebuilt from live position pings"}
errors = []


def read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


months = {r["month"]: float(r["kept_share"]) for r in read(os.path.join(D, "extract_months.csv"))}
posted = set(months)
bus = {r["route"] for r in read(os.path.join(D, "ref", "route_types.csv")) if r["route_type"] == "3"}
site = json.load(open(os.path.join(ROOT, "site", "data", "muni.json")))
# the lines muni.json lists that are judged by excess wait: since 2026-11-17 it also lists SFMTA's Connector and Owl
# lines, judged by on time (freq_rule.py), which ewt_daily.py leaves out
from freq_rule import is_frequent  # noqa: E402
listed = sorted(l for l in site["lines"] if is_frequent(l))

rows, src = [], {}
for p in sorted(glob.glob(os.path.join(D, "daily", "20??-??.csv"))):
    m = os.path.basename(p)[:7]
    if months.get(m, 0) < MINKEEP:
        continue
    for r in read(p):
        rows.append(r); src[r["sdate"]] = "511"
rt_days = {r["sdate"]: r for r in read(os.path.join(D, "rt", "days.csv"))} if os.path.exists(os.path.join(D, "rt", "days.csv")) else {}
for p in sorted(glob.glob(os.path.join(D, "rt", "daily", "20??-??.csv"))):
    m = os.path.basename(p)[:7]
    if m in posted:
        continue  # 511 has posted this month; its record wins
    for r in read(p):
        if rt_days.get(r["sdate"], {}).get("status") != "ok":
            continue
        rows.append(r); src[r["sdate"]] = "rt-archive"
for r in rows:
    r["route"] = REN.get(r["route"], r["route"])

num = lambda v: float(v) if v not in ("", None) else 0.0


def acc():
    return [0.0] * 7  # swt*eb, eb, awt*eba, eba, miles, obs_hr, sch_hr (bus lines)


def add(a, r):
    eb, eba = num(r["eb"]), num(r["eba"])
    if r["swt"] and eb > 0:
        a[0] += num(r["swt"]) * eb; a[1] += eb
    if r["awt"] and eba > 0:
        a[2] += num(r["awt"]) * eba; a[3] += eba
    if r["route"] in bus and r["miles"] and num(r["obs_hr"]) > 0 and num(r["sch_hr"]) > 0:
        a[4] += num(r["miles"]); a[5] += num(r["obs_hr"]); a[6] += num(r["sch_hr"])


def value(a, min_eb=MIN_EB, speed=True):
    v = {"ewt": round(a[2] / a[3] - a[0] / a[1], 3) if a[1] >= min_eb and a[3] > 0 else None}
    if speed:
        v["mph"] = round(a[4] / a[5], 2) if a[5] > 0 else None
        v["run"] = round(a[5] / a[6] - 1, 4) if a[6] > 0 else None
    return v


city, by_line, city_all = {}, {}, {}
for r in rows:
    add(city_all.setdefault(r["sdate"], acc()), r)
    if r["route"] not in CITY_EXCLUDE:
        add(city.setdefault(r["sdate"], acc()), r)
    if r["route"] in listed:
        a = by_line.setdefault(r["route"], {}).setdefault(r["sdate"], acc())
        # a line's speed is its own miles over hours, whatever its mode
        eb, eba = num(r["eb"]), num(r["eba"])
        if r["swt"] and eb > 0:
            a[0] += num(r["swt"]) * eb; a[1] += eb
        if r["awt"] and eba > 0:
            a[2] += num(r["awt"]) * eba; a[3] += eba
        if r["miles"] and num(r["obs_hr"]) > 0 and num(r["sch_hr"]) > 0:
            a[4] += num(r["miles"]); a[5] += num(r["obs_hr"]); a[6] += num(r["sch_hr"])

dates = sorted(city)
if dates != sorted(set(dates)):
    errors.append("a date appears twice")
for sd, s in src.items():
    if s == "rt-archive" and f"{sd[:4]}-{sd[4:6]}" in posted:
        errors.append(f"{sd}: archive day in a month 511 has posted")

# Check: the newest 511 month pooled from its days against muni.json and trip_analyze.py's month
m511 = max((m for m in months if months[m] >= MINKEEP and m >= "2022-01"), default=None)
if m511:
    a = acc()
    for sd, x in city_all.items():  # every line, cable cars in, as muni.json counts the month
        if src[sd] == "511" and sd.startswith(m511.replace("-", "")):
            a = [p + q for p, q in zip(a, x)]
    v = value(a)
    # Check: each archive day's scheduled frequent departures (cable cars out) within TOL_EB of the nearest day-type
    # median of that month on 511's record, so a day missing lines or hours can't pass as a full one
    import datetime, statistics
    kind = lambda sd: datetime.date(int(sd[:4]), int(sd[4:6]), int(sd[6:])).weekday()
    meds = {}
    for k, test in (("weekday", lambda w: w < 5), ("saturday", lambda w: w == 5), ("sunday", lambda w: w == 6)):
        xs = [city[sd][1] for sd in city if src[sd] == "511" and sd.startswith(m511.replace("-", "")) and test(kind(sd))]
        if xs:
            meds[k] = statistics.median(xs)
    for sd in (x for x in city if src[x] == "rt-archive"):
        eb = city[sd][1]
        near = min(meds.values(), key=lambda mv: abs(eb - mv)) if meds else None
        if near is None or abs(eb / near - 1) > TOL_EB:
            errors.append(f"{sd}: archive day's scheduled departures {eb:.0f}, nearest day-type median of {m511} {near}")
    tr = next((t for t in site["trend"] if t["month"] == m511), None)
    run = {r["month"]: float(r["run_share"]) for r in read(os.path.join(D, "summary_trip", "run_system_month.csv"))}
    if tr is None:
        errors.append(f"muni.json has no trend entry for {m511}")
    else:
        if v["ewt"] is None or abs(v["ewt"] - tr["ewt"]) > TOL_EWT:
            errors.append(f"{m511} excess wait from days {v['ewt']} against muni.json {tr['ewt']}")
        if v["mph"] is None or abs(v["mph"] - tr["mph"]) > TOL_MPH:
            errors.append(f"{m511} speed from days {v['mph']} against muni.json {tr['mph']}")
    if m511 in run and (v["run"] is None or abs(v["run"] - run[m511]) > TOL_RUN):
        errors.append(f"{m511} running time from days {v['run']} against trip_analyze.py {run[m511]}")
    check = {"month": m511, "fromDays": v, "monthly": {"ewt": tr and tr["ewt"], "mph": tr and tr["mph"], "run": run.get(m511)}}
else:
    check = None


def window(ds):
    a, ls = acc(), {}
    for sd in ds:
        for k, x in enumerate(city[sd]):
            a[k] += x
    for line, per in by_line.items():
        b = acc()
        for sd in ds:
            for k, x in enumerate(per.get(sd, acc())):
                b[k] += x
        ls[line] = value(b, MIN_EB * 10)
    return {"from": ds[0] if ds else None, "to": ds[-1] if ds else None, "days": len(ds),
            "rebuiltDays": sum(src[sd] == "rt-archive" for sd in ds), "city": value(a, MIN_EB * 10), "lines": ls}


rt_in = [sd for sd in dates if src[sd] == "rt-archive"]
out = {
    "labels": LABEL,
    "cityExcludes": sorted(CITY_EXCLUDE),
    "through": dates[-1] if dates else None,
    "updated": max((rt_days[sd]["read"] for sd in rt_in), default=None),
    "days": [{"t": sd, "src": src[sd], **value(city[sd])} for sd in dates[-DAYS_KEPT:]],
    "lines": {line: [{"t": sd, **value(per[sd])} for sd in sorted(per)[-LINE_DAYS:] if sd in dates[-LINE_DAYS:]]
              for line, per in sorted(by_line.items())},
    "last30": window(dates[-30:]),
    "previous30": window(dates[-60:-30]),
    "check": check,
    "comparison": {},
}
for p in sorted(glob.glob(os.path.join(D, "rt", "compare-20??-??.json"))):
    c = json.load(open(p))
    out["comparison"][c["month"]] = {"daysCompared": c["days_compared"], "method": c["method"], **c["summary"]}
missing = [line for line in listed if line not in out["lines"]]
if missing:
    errors.append(f"listed lines with no daily figures: {missing}")
if errors:
    print("muni_daily.py: not written:\n  " + "\n  ".join(errors), file=sys.stderr)
    sys.exit(1)
text = json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n"
if not os.path.exists(OUT) or open(OUT).read() != text:
    open(OUT, "w").write(text)
    print(f"muni-daily: wrote {os.path.relpath(OUT, ROOT)} through {out['through']}, {len(rt_in)} archive days, updated {out['updated']}")
else:
    print("muni-daily: unchanged")
