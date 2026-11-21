#!/usr/bin/env python3
"""Injury crashes near each school at its own drop-off and pick-up hours, on school days, against the same places at other hours.

    tools/school-trips/school-hour-crashes.py                # build out/school-hour-crashes/
    tools/school-trips/school-hour-crashes.py --fetch-bell   # re-download the four bell-schedule pages first

Bryan, 2026-10-01: "Do we have stats for where we had
the most injuries or close calls near schools at pickup and dropoff hours for
that school (which may vary by grade and year)? Just curious how bad it is
quantitatively in addition to the walking surveys."

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A one-off exploration. It does not
meet the rule in pipeline/README.md: there is no --update, it is not registered in
pipeline/transportation-update.py, and the idempotence proofs have not been run.
It reads DataSF through lib/sfdata.py, which caches every query under
data/socrata-cache/ with the date it was read, so a rerun reuses the same rows.
It does run quality checks on what it reads (QUALITY below) and stops on a
failure. If a page comes to depend on it, it needs a rowsUpdatedAt check on the
three crash datasets, registration in STEPS, and the run-twice proof.

INPUTS.
  * Schools: the site's school list, exactly as lib/school-travel-time.py
    loads it (load_schools: the bike explorer's open schools without court,
    community, special-education, continuation and in-custody schools).
  * Bell times: SFUSD's "School Start and End Times" page for 2022-23, 2023-24,
    2024-25 (Internet Archive copies; the live URLs now redirect to 2025-26) and
    2025-26 (live). Cached as HTML under data/school-hour-crashes/raw/
    (gitignored) and parsed into data/school-hour-crashes/bell-times.json.
    Only the K-12 sections are used. A school with more than one row (TK, SDC,
    a K-8's grade bands) takes the row that is its main program; see
    pick_row(). Charter and private schools are not on the page and take
    DEFAULT_START/DEFAULT_END.
  * School days: data/school-hour-crashes/sfusd-calendar.json, typed from
    SFUSD's calendars. Charter and private schools are given SFUSD's calendar
    too, which is an approximation.
  * Crashes: DataSF ubvf-ztfx (one row per injury crash) and nwes-mmgh (one row
    per injured or killed person). They join on case_id_pkey; their unique_id
    columns are different sequences and do not join. dau3-4s8f (fatalities) is
    read for a cross-check only.

THE COUNT. For each school and each school day, the drop-off window runs
AM_BEFORE minutes before the start bell to AM_AFTER after it, and the pick-up
window PM_BEFORE before the end bell to PM_AFTER after it, using the
early-release time on the school's early-release weekday. A crash counts for a
school when it happened on a school day, inside one of those windows, within
600 ft (182.88 m) or a quarter mile (402.34 m) of the school's grounds,
measured from their edge as state law measures a school zone
(data/school-sim/grounds.json, tools/school-trips/school-grounds.py). The
comparison is the same circles at OTHER hours: (a) the rest of the school-day
daytime, DAY_START to DAY_END, outside both windows, and (b) the same clock
windows on weekdays when school is out (breaks and summer). Each is turned
into crashes per hour so the windows (2 hours a day) and the rest of the day
(12 hours) compare fairly.

Those raw rates flatter the windows, because injury crashes everywhere in the
city peak at 3 and 4 pm. So each school also gets an expected window count
from the city's clock: its own other-daytime count times the citywide ratio
of school-day crashes in its window minutes to those in the rest of the
daytime (clock_split). The summary splits every figure by whether the school's
bell came from SFUSD or from the default, since a guessed bell pulls the ratio
toward 1. 600 ft circles of neighboring schools overlap; shares_crashes_with
names the schools whose counts share crashes.

Children: a victim row with victim_role Pedestrian or Bicyclist and
victim_age under 18. Counted per person, not per crash.

WHAT IT WRITES. out/school-hour-crashes/schools.json (every school, ranked)
and out/school-hour-crashes/summary.json (citywide figures, the data checks,
and the step-change diagnostics).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import html as htmllib
import importlib.util
import json
import math
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import school_grounds  # noqa: E402

DATA = os.path.join(ROOT, "data", "school-hour-crashes")
RAW = os.path.join(DATA, "raw")
OUT = os.path.join(ROOT, "out", "school-hour-crashes")

CRASHES, VICTIMS, FATAL = "ubvf-ztfx", "nwes-mmgh", "dau3-4s8f"
YEARS = ["2022-23", "2023-24", "2024-25", "2025-26"]
BELL_URL = "https://www.sfusd.edu/schools/enroll/resources/school-start-and-end-times-%s"
# The live URLs for earlier years now 301 to 2025-26; these are the Internet Archive copies read.
BELL_SNAPSHOT = {
    "2022-23": "https://web.archive.org/web/20221004124058/" + BELL_URL % "2022-23",
    "2023-24": "https://web.archive.org/web/20230929142713/" + BELL_URL % "2023-24",
    "2024-25": "https://web.archive.org/web/20240812141433/" + BELL_URL % "2024-25",
    "2025-26": BELL_URL % "2025-26",
}
K12_SECTIONS = {"Elementary Schools", "K-8 Schools", "Middle Schools", "High Schools"}

AM_BEFORE, AM_AFTER = 45, 15
PM_BEFORE, PM_AFTER = 15, 45
DEFAULT_START, DEFAULT_END = "8:15", "15:15"
DAY_START, DAY_END = 6 * 60, 20 * 60
COUNT_KEYS = ("window", "window_am", "window_pm", "other_daytime", "window_no_school", "window_child_ped",
              "window_child_bike", "window_severe_fatal", "window_ped_or_bike_crash", "child_ped_all_hours", "child_bike_all_hours",
              "other_daytime_child_ped_bike", "window_no_school_child_ped_bike")
FT_M = 0.3048
RADII = {"600ft": 600 * FT_M, "quarter_mile": 1320 * FT_M}

# Bell-page name -> site name, where the token match below cannot find it.
# Each was checked by hand against the two lists on 2026-10-01.
BELL_ALIAS = {
    "Carver (Dr George W) ES": "Carver (George Washington) Elementary",
    "CIS at DeAvila ES": "Chinese Immersion School at DeAvila",
    "Drew (Dr Charles) ES": "Drew (Charles) College Preparatory Academy",
    "Visitacion Valley ES": "Visitacion Valley Elementary",
    "Visitacion Valley MS": "Visitacion Valley Middle",
    "Francisco MS": "Francisco Middle",
}
DAY_ABBR = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}


def read(*p):
    return json.load(open(os.path.join(*p)))


def load_schools():
    m = paths.load("school-travel-time.py", "stt")
    schools, dropped, _priv = m.load_schools()
    return schools, dropped


# -- bell times ---------------------------------------------------------------

class BellTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sec, self.rows, self.cur, self.cell, self.inh, self.h = None, [], None, None, False, ""

    def handle_starttag(self, t, a):
        if t in ("h2", "h3"):
            self.inh, self.h = True, ""
        if t == "tr":
            self.cur = []
        if t in ("td", "th") and self.cur is not None:
            self.cell = ""

    def handle_endtag(self, t):
        if t in ("h2", "h3"):
            self.inh = False
            h = " ".join(self.h.split())
            if h and h not in ("Sch. ID", "Sch. Name", "Start Time", "End Time", "Early Release Day", "Early Release Time"):
                self.sec = h
        if t in ("td", "th") and self.cur is not None and self.cell is not None:
            self.cur.append(" ".join(htmllib.unescape(self.cell).split()))
            self.cell = None
        if t == "tr" and self.cur is not None:
            if self.cur and self.cur[0] != "Sch. ID":
                self.rows.append((self.sec, self.cur))
            self.cur = None

    def handle_data(self, d):
        if self.inh:
            self.h += d
        if self.cell is not None:
            self.cell += d


def minutes(s):
    """'8:40 AM' or '15:15' -> minutes after midnight."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)?", s.strip().upper())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return h * 60 + mi


def fetch_bell():
    os.makedirs(RAW, exist_ok=True)
    for y, url in BELL_SNAPSHOT.items():
        raw = url.replace("/web/", "/web/").replace("/https://", "id_/https://", 1) if "web.archive.org" in url else url
        req = urllib.request.Request(raw, headers={"User-Agent": "Mozilla/5.0 sf-works"})
        body = urllib.request.urlopen(req, timeout=120).read()
        open(os.path.join(RAW, "bell-%s.html" % y), "wb").write(body)


def parse_bell():
    out = {}
    for y in YEARS:
        p = BellTable()
        p.feed(open(os.path.join(RAW, "bell-%s.html" % y), encoding="utf-8", errors="replace").read())
        rows = []
        for sec, r in p.rows:
            if sec not in K12_SECTIONS or len(r) < 4:
                continue
            rows.append({"section": sec, "id": r[0], "name": r[1], "start": minutes(r[2]) if r[2] else None,
                         "end": minutes(r[3]) if r[3] else None,
                         "early_day": (r[4] if len(r) > 4 else "") or None,
                         "early_end": minutes(r[5]) if len(r) > 5 and r[5] else None,
                         "early_by_day": early_by_day(r[4] if len(r) > 4 else "", r[5] if len(r) > 5 else "")})
        out[y] = rows
    return out


NORM_SUB = [(r"\bes\b", "elementary"), (r"\bms\b", "middle"), (r"\bhs\b", "high"), (r"\bk ?8\b", "k8"),
            (r"\bjr\b", "junior")]
DROP_TOK = {"school", "the", "of", "sf", "san", "francisco", "academy", "and", "elementary", "middle", "high",
            "k8", "alternative", "academic", "for", "at"}


def toks(name):
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    for a, b in NORM_SUB:
        s = re.sub(a, b, s)
    return set(s.split())


def core(name):
    return toks(name) - DROP_TOK


def pick_rows(rows):
    """The school's grade-band rows (a K-8's K-5 and 6-8 rows both count), without TK, PK, SDC and
    the high schools' 'Access' (adult transition) rows, which are separate programs on the same campus."""
    return sorted((r for r in rows if not re.search(r"\b(TK|PK|SDC|EES|ECE|Pre-?K|Access)\b", r["name"])
                   and r["start"] is not None and r["end"] is not None), key=lambda r: r["name"])


def early_days(s):
    """'Wednesday', 'Wed, Thu', 'Tue, Thu' -> {weekday numbers}."""
    return {DAY_ABBR[t[:3]] for t in re.split(r"[,/& ]+", (s or "").lower()) if t[:3] in DAY_ABBR}


def early_by_day(day_cell, time_cell):
    """[(weekday, minutes)] from the early-release cells. Most rows give one day and one time
    ('Wednesday', '12:50 PM'); a few give a time per day ('W: 1:55 PM / Th: 3:10 PM')."""
    out = []
    for part in (time_cell or "").split("/"):
        m = re.match(r"\s*([A-Za-z]+)\s*:\s*(\d.*)$", part)
        if m:
            day = {"m": 0, "tu": 1, "t": 1, "w": 2, "th": 3, "f": 4}.get(m.group(1).lower()[:2]) \
                if m.group(1).lower()[:2] in ("tu", "th") else {"m": 0, "w": 2, "f": 4}.get(m.group(1).lower()[:1])
            t = minutes(m.group(2))
            if day is not None and t is not None:
                out.append((day, t))
    if out:
        return sorted(out)
    t = minutes(time_cell) if time_cell else None
    return sorted((d, t) for d in early_days(day_cell)) if t is not None else []


def bell_name(rows):
    return re.sub(r"\s+(6-8|K-?5)$", "", rows[0]["name"])


def match_bell(schools, bell):
    """For each site school and each year, the bell row it takes, or None."""
    pub = [s for s in schools if not s["private"]]
    matches = {}
    unmatched = collections.defaultdict(list)
    for y, rows in bell.items():
        by_id = collections.defaultdict(list)
        for r in rows:
            by_id[r["id"]].append(r)
        for sid, rs in sorted(by_id.items()):
            rs = pick_rows(rs)
            if not rs:
                continue
            bname = bell_name(rs)
            name = BELL_ALIAS.get(bname)
            if name is None:
                c = core(bname)
                cands = []
                for s in pub:
                    sc = core(s["name"])
                    if not c or not sc:
                        continue
                    j = len(c & sc) / len(c | sc)
                    if j > 0:
                        cands.append((j, s["name"]))
                cands.sort(reverse=True)
                if cands and cands[0][0] >= 0.5 and (len(cands) == 1 or cands[1][0] < cands[0][0]):
                    name = cands[0][1]
                else:
                    unmatched[y].append((bname, cands[:3]))
                    continue
            if y in matches.get(name, {}):
                raise SystemExit("two bell entries matched %s in %s" % (name, y))
            # Grade bands differ (a K-8's 6-8 ends later): the windows cover every band's bell.
            matches.setdefault(name, {})[y] = {
                "rows": [r["name"] for r in rs],
                "start_min": min(r["start"] for r in rs), "start_max": max(r["start"] for r in rs),
                "end_min": min(r["end"] for r in rs), "end_max": max(r["end"] for r in rs),
                "early": sorted({(d, t) for r in rs for d, t in r["early_by_day"]}),
            }
    return matches, unmatched


# -- school days ----------------------------------------------------------------

def school_days():
    cal = read(DATA, "sfusd-calendar.json")
    days, check = {}, []
    for yr in cal["years"]:
        closed = set()
        for rng in yr["closed"]:
            a = dt.date.fromisoformat(rng[0])
            b = dt.date.fromisoformat(rng[-1])
            while a <= b:
                closed.add(a)
                a += dt.timedelta(days=1)
        d = dt.date.fromisoformat(yr["first"])
        last = dt.date.fromisoformat(yr["last"])
        n = 0
        while d <= last:
            if d.weekday() < 5 and d not in closed:
                days[d] = yr["year"]
                n += 1
            d += dt.timedelta(days=1)
        check.append({"year": yr["year"], "days": n, "expected": yr["days_expected"]})
    return days, check


# -- geometry ---------------------------------------------------------------------

def dist_m(lat1, lon1, lat2, lon2):
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371008.8 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


# -- main ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch-bell", action="store_true")
    a = ap.parse_args()
    if a.fetch_bell:
        fetch_bell()

    quality = []

    def check(name, ok, detail):
        quality.append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            raise SystemExit("quality check failed: %s: %s" % (name, detail))

    schools, dropped = load_schools()
    check("school list", len(schools) >= 180, "%d schools" % len(schools))

    bell = parse_bell()
    for y in YEARS:
        check("bell rows %s" % y, len(bell[y]) >= 100, "%d K-12 rows" % len(bell[y]))
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "bell-times.json"), "w") as f:
        json.dump({"source": BELL_SNAPSHOT, "read": "2026-10-01", "years": bell}, f, indent=1, sort_keys=True)
        f.write("\n")
    matches, unmatched = match_bell(schools, bell)

    days, daycheck = school_days()
    for c in daycheck:
        if c["expected"]:

            check("school days %s" % c["year"], c["days"] == c["expected"], "%d counted, %d expected" % (c["days"], c["expected"]))

    # crashes
    C = sfdata.fetch(CRASHES, select="unique_id,case_id_pkey,collision_datetime,collision_time,tb_latitude,tb_longitude,"
                     "geocode_source,collision_severity,type_of_collision,ped_action,party1_type,party2_type,"
                     "dph_col_grp_description,number_injured,number_killed,day_of_week,primary_rd,secondary_rd",
                     floor=60000)
    V = sfdata.fetch(VICTIMS, select="case_id_pkey,victim_id,victim_role,victim_age,victim_degree_of_injury,party_type,collision_datetime",
                     floor=80000)
    F = sfdata.fetch(FATAL, select="case_id_fkey,collision_datetime,latitude,longitude,age,deceased", floor=300)
    crashes, victims = C.rows, V.rows
    case_ids = [r["case_id_pkey"] for r in crashes]
    check("crash case ids unique", len(set(case_ids)) >= len(case_ids) - 2,
          "%d rows, %d distinct case ids" % (len(case_ids), len(set(case_ids))))
    cset = set(case_ids)
    orphan = sum(1 for r in victims if r["case_id_pkey"] not in cset)
    check("every victim joins a crash", orphan == 0, "%d victim rows with no crash" % orphan)
    vids = [r["victim_id"] for r in victims]
    check("victim ids unique", len(set(vids)) == len(vids), "%d rows, %d distinct" % (len(vids), len(set(vids))))
    by_case = collections.defaultdict(list)
    for r in victims:
        by_case[r["case_id_pkey"]].append(r)
    agree = 0
    for r in crashes:
        exp = int(float(r.get("number_injured") or 0)) + int(float(r.get("number_killed") or 0))
        agree += len(by_case.get(r["case_id_pkey"], [])) == exp
    check("victim rows match crash injured+killed", agree / len(crashes) > 0.99,
          "%d of %d crashes have exactly number_injured + number_killed victim rows" % (agree, len(crashes)))

    def is_child_pb(v):
        age = v.get("victim_age")
        return v["victim_role"] in ("Pedestrian", "Bicyclist") and age not in (None, "") and age.isdigit() and int(age) < 18

    # Field audit, over the whole dataset.
    audit = {
        "crash_rows": len(crashes), "victim_rows": len(victims),
        "first": min(r["collision_datetime"] for r in crashes)[:10],
        "last": max(r["collision_datetime"] for r in crashes)[:10],
        "null_time": sum(1 for r in crashes if not r.get("collision_time")),
        "time_0000": sum(1 for r in crashes if (r.get("collision_time") or "").startswith("00:00")),
        "minute_on_00_or_30": round(sum(1 for r in crashes if (r.get("collision_time") or "")[3:5] in ("00", "30")) / len(crashes), 3),
        "null_coords": sum(1 for r in crashes if not r.get("tb_latitude")),
        "geocode_source": dict(collections.Counter(r.get("geocode_source") for r in crashes).most_common()),
        "victim_role": dict(collections.Counter(r["victim_role"] for r in victims).most_common()),
        "victim_injury": dict(collections.Counter(r.get("victim_degree_of_injury") for r in victims).most_common()),
        "victim_age_null": sum(1 for r in victims if r.get("victim_age") in (None, "")),
        "ped_bike_victims": sum(1 for r in victims if r["victim_role"] in ("Pedestrian", "Bicyclist")),
        "ped_bike_age_null": sum(1 for r in victims if r["victim_role"] in ("Pedestrian", "Bicyclist") and r.get("victim_age") in (None, "")),
        "victim_age_over_110": sum(1 for r in victims if (r.get("victim_age") or "").isdigit() and int(r["victim_age"]) > 110),
        "stacked_coordinate_max": collections.Counter((r.get("tb_latitude"), r.get("tb_longitude")) for r in crashes if r.get("tb_latitude")).most_common(1)[0][1],
    }

    # Step-change diagnostics: children hurt walking or biking, by year, all hours.
    yearly = collections.defaultdict(lambda: collections.Counter())
    crash_by_case = {r["case_id_pkey"]: r for r in crashes}
    for v in victims:
        y = v["collision_datetime"][:4]
        role = v["victim_role"]
        if role in ("Pedestrian", "Bicyclist"):
            yearly[y]["ped_bike_all_ages"] += 1
            if v.get("victim_age") in (None, ""):
                yearly[y]["ped_bike_age_missing"] += 1
            if is_child_pb(v):
                yearly[y]["child_" + role.lower()] += 1
                yearly[y]["child_" + (v.get("victim_degree_of_injury") or "unknown").lower().replace(" ", "_")] += 1
    for r in crashes:
        y = r["collision_datetime"][:4]
        yearly[y]["crashes"] += 1
        yearly[y]["geocode_" + (r.get("geocode_source") or "none")] += 1
    yearly = {y: dict(sorted(c.items())) for y, c in sorted(yearly.items())}

    # The study period: school days in YEARS, crashes with a time and a place.
    period = []
    for r in crashes:
        if not r.get("collision_time") or not r.get("tb_latitude"):
            continue
        d = dt.date.fromisoformat(r["collision_datetime"][:10])
        if d < dt.date(2022, 7, 1) or d > dt.date(2026, 6, 30):
            continue
        period.append((d, minutes(r["collision_time"]), float(r["tb_latitude"]), float(r["tb_longitude"]), r))
    weekdays = [dt.date(2022, 7, 1) + dt.timedelta(days=i) for i in range((dt.date(2026, 6, 30) - dt.date(2022, 7, 1)).days + 1)]
    weekdays = [d for d in weekdays if d.weekday() < 5]
    out_weekdays = [d for d in weekdays if d not in days]

    def year_of(d):
        return "%d-%02d" % (d.year, (d.year + 1) % 100) if d.month >= 7 else "%d-%02d" % (d.year - 1, d.year % 100)

    def windows(s, d):
        """[(lo, hi, 'am'|'pm')] in minutes for school s on date d; the bell row used for its year."""
        b = s.get("bell", {}).get(year_of(d))
        if b:
            st0, st1, en0, en1 = b["start_min"], b["start_max"], b["end_min"], b["end_max"]
            early = [e for wd, e in b["early"] if wd == d.weekday()]
            if early:
                en0, en1 = min(early), max(early)
        else:
            st0 = st1 = minutes(DEFAULT_START)
            en0 = en1 = minutes(DEFAULT_END)
        return [(st0 - AM_BEFORE, st1 + AM_AFTER, "am"), (en0 - PM_BEFORE, en1 + PM_AFTER, "pm")]

    for s in schools:
        s["bell"] = matches.get(s["name"], {})

    child_by_case = collections.defaultdict(list)
    for v in victims:
        if is_child_pb(v):
            child_by_case[v["case_id_pkey"]].append(v)

    # The city's own clock: injury crashes everywhere in San Francisco peak at 3 and 4 pm on any
    # weekday, so a bell window beats "other daytime" anywhere. The control asks instead how a
    # school's window-to-other split compares with the whole city's split over the same minutes
    # on the same days: expected = this place's other-daytime count x (city in these windows /
    # city in the rest of the daytime). Children hurt walking or biking get the same treatment.
    city_clock = [(d, mi, len(child_by_case.get(r["case_id_pkey"], []))) for d, mi, la, lo, r in period
                  if d in days and mi is not None and DAY_START <= mi < DAY_END]

    def clock_split(s):
        w = o = kw = ko = 0
        for d, mi, nk in city_clock:
            if any(lo_ <= mi < hi_ for lo_, hi_, _ in windows(s, d)):
                w += 1
                kw += nk
            else:
                o += 1
                ko += nk
        return w, o, kw, ko

    results = []
    city = {k: collections.Counter() for k in RADII}
    groups = {g: {k: collections.Counter() for k in RADII} for g in ("sfusd_bell", "default_bell")}
    city_cases = {k: {"window": set(), "other": set()} for k in RADII}
    for s in schools:
        cw, co, ckw, cko = clock_split(s)
        near = {k: [] for k in RADII}
        # Feet to the school's grounds, as state law measures a school zone (lib/school_grounds.py).
        dg = school_grounds.dist_ft(s["lon"], s["lat"], [p[3] for p in period], [p[2] for p in period]) * FT_M
        for p, dm in zip(period, dg):
            for k, rad in RADII.items():
                if dm <= rad:
                    near[k].append(p)
        row = {"name": s["name"], "private": s["private"], "grades": s["grades"], "lat": s["lat"], "lon": s["lon"],
               "bell": {y: b for y, b in sorted(s["bell"].items())},
               "bell_years": len(s["bell"]),
               "bell_source": "sfusd" if s["bell"] else "default",
               # Other schools whose 600 ft circle overlaps this one's: their counts share crashes.
               "shares_crashes_with": sorted(t["name"] for t in schools if t is not s
                                             and dist_m(s["lat"], s["lon"], t["lat"], t["lon"]) <= 2 * RADII["600ft"]),
               "city_clock": {"window": cw, "other_daytime": co, "child_window": ckw, "child_other_daytime": cko}}
        grp = groups["sfusd_bell" if s["bell"] else "default_bell"]
        for k in RADII:
            n = collections.Counter()
            cases_w = []
            for d, mi, la, lo, r in near[k]:
                if d.weekday() >= 5 or mi is None:
                    continue
                w = windows(s, d)
                inw = any(lo_ <= mi < hi_ for lo_, hi_, _ in w)
                daytime = DAY_START <= mi < DAY_END
                kids = child_by_case.get(r["case_id_pkey"], [])
                if d in days:
                    if inw:
                        n["window"] += 1
                        n["window_" + next(t for lo_, hi_, t in w if lo_ <= mi < hi_)] += 1
                        n["window_child_ped"] += sum(1 for v in kids if v["victim_role"] == "Pedestrian")
                        n["window_child_bike"] += sum(1 for v in kids if v["victim_role"] == "Bicyclist")
                        n["window_severe_fatal"] += r["collision_severity"] in ("Injury (Severe)", "Fatal")
                        n["window_ped_or_bike_crash"] += (r.get("dph_col_grp_description") or "") in (
                            "Vehicle-Pedestrian", "Vehicle-Bicycle", "Bicycle-Pedestrian", "Vehicle-Bicycle-Pedestrian")
                        cases_w.append(r["case_id_pkey"])
                        city_cases[k]["window"].add(r["case_id_pkey"])
                    elif daytime:
                        n["other_daytime"] += 1
                        n["other_daytime_child_ped_bike"] += len(kids)
                        city_cases[k]["other"].add(r["case_id_pkey"])
                elif inw:
                    n["window_no_school"] += 1
                    n["window_no_school_child_ped_bike"] += len(kids)
                n["child_ped_all_hours"] += sum(1 for v in kids if v["victim_role"] == "Pedestrian")
                n["child_bike_all_hours"] += sum(1 for v in kids if v["victim_role"] == "Bicyclist")
            for key in COUNT_KEYS:
                n[key] += 0
            n["all_crashes"] = len(near[k])
            # Exposure in hours. Windows are 2 h a day; the rest of the daytime is the remainder.
            win_h = 0.0
            for d in days:
                win_h += sum(hi_ - lo_ for lo_, hi_, _ in windows(s, d)) / 60
            other_h = len(days) * (DAY_END - DAY_START) / 60 - win_h
            ns_h = sum(sum(hi_ - lo_ for lo_, hi_, _ in windows(s, d)) / 60 for d in out_weekdays)
            rate_w = n["window"] / win_h
            rate_o = n["other_daytime"] / other_h
            rate_ns = n["window_no_school"] / ns_h if ns_h else None
            row[k] = dict(sorted(n.items()), window_hours=round(win_h), other_hours=round(other_h), no_school_window_hours=round(ns_h),
                          per_1000h_window=round(1000 * rate_w, 2), per_1000h_other=round(1000 * rate_o, 2),
                          per_1000h_window_no_school=round(1000 * rate_ns, 2) if rate_ns is not None else None,
                          window_cases=sorted(cases_w),
                          window_expected_city_clock=round(n["other_daytime"] * cw / co, 2),
                          child_window_expected_city_clock=round(n["other_daytime_child_ped_bike"] * ckw / cko, 2))
            for key in COUNT_KEYS:
                city[k][key] += n[key]
                grp[k][key] += n[key]
            for c_ in (city[k], grp[k]):
                c_["expected_city_clock"] += n["other_daytime"] * cw / co
                c_["child_expected_city_clock"] += n["other_daytime_child_ped_bike"] * ckw / cko
                c_["schools"] += 1
            grp[k]["window_hours"] += win_h
            grp[k]["other_hours"] += other_h
            grp[k]["no_school_window_hours"] += ns_h
            city[k]["window_hours"] += win_h
            city[k]["other_hours"] += other_h
            city[k]["no_school_window_hours"] += ns_h
        results.append(row)

    def rank_key(r):
        return (-r["600ft"]["window"], -r["quarter_mile"]["window"], -(r["600ft"]["window_child_ped"] + r["600ft"]["window_child_bike"]), r["name"])

    results.sort(key=rank_key)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    # Walk-audit cross-check: the ten 2025 SFMTA walk-audit schools.
    audit_schools = {"Alvarado": "Alvarado Elementary", "Argonne": "Argonne Elementary", "Bessie Carmichael": "Carmichael (Bessie)/FEC",
                     "César Chávez": "Chavez (Cesar) Elementary", "Claire Lilienthal": "Lilienthal (Claire) Elementary",
                     "Commodore Sloat": "Sloat (Commodore) Elementary", "Dianne Feinstein": "Feinstein (Dianne) Elementary",
                     "Drew": "Drew (Charles) College Preparatory Academy", "Monroe": "Monroe Elementary", "Redding": "Redding Elementary"}
    by_name = {r["name"]: r for r in results}
    walk = []
    for short, name in audit_schools.items():
        r = by_name.get(name)
        walk.append({"audit_name": short, "name": name, "rank": r["rank"] if r else None,
                     "window_600ft": r["600ft"]["window"] if r else None,
                     "window_quarter_mile": r["quarter_mile"]["window"] if r else None,
                     "child_ped_bike_600ft": (r["600ft"]["window_child_ped"] + r["600ft"]["window_child_bike"]) if r else None})

    # Fatal cross-check: deaths within 600 ft of any school in its windows on a school day.
    fatal_near = []
    for f in F.rows:
        try:
            la, lo = float(f["latitude"]), float(f["longitude"])
            d = dt.date.fromisoformat(f["collision_datetime"][:10])
            mi = minutes(f["collision_datetime"][11:16])
        except (KeyError, TypeError, ValueError):
            continue
        if d not in days:
            continue
        for s in schools:
            if school_grounds.dist_ft(s["lon"], s["lat"], lo, la) * FT_M <= RADII["600ft"] and any(a_ <= mi < b_ for a_, b_, _ in windows(s, d)):
                fatal_near.append({"date": d.isoformat(), "school": s["name"], "age": f.get("age"), "deceased": f.get("deceased")})

    def city_rates(k, c=None, distinct=True):
        c = c if c is not None else city[k]
        kids_w = c["window_child_ped"] + c["window_child_bike"]
        out = {"schools": c["schools"],
                "window_expected_city_clock": round(c["expected_city_clock"], 1),
                "window_vs_city_clock": round(c["window"] / c["expected_city_clock"], 2) if c["expected_city_clock"] else None,
                "child_window_expected_city_clock": round(c["child_expected_city_clock"], 1),
                "child_window_vs_city_clock": round(kids_w / c["child_expected_city_clock"], 2) if c["child_expected_city_clock"] else None}
        if distinct:
            cases = city_cases[k]["window"]
            out["distinct_window_child_ped_bike"] = sum(len(child_by_case.get(cid, [])) for cid in cases)
            out["distinct_window_crashes"] = len(cases)
        return dict(out, **{"window": c["window"], "window_am": c["window_am"], "window_pm": c["window_pm"],
                "window_child_ped": c["window_child_ped"], "window_child_bike": c["window_child_bike"],
                "window_severe_fatal": c["window_severe_fatal"], "window_ped_or_bike_crash": c["window_ped_or_bike_crash"],
                "other_daytime": c["other_daytime"], "window_no_school": c["window_no_school"],
                "child_ped_bike_per_1000h_window": round(1000 * (c["window_child_ped"] + c["window_child_bike"]) / c["window_hours"], 3),
                "child_ped_bike_per_1000h_other_daytime": round(1000 * c["other_daytime_child_ped_bike"] / c["other_hours"], 3),
                "child_ped_bike_per_1000h_window_no_school": round(1000 * c["window_no_school_child_ped_bike"] / c["no_school_window_hours"], 3),
                "other_daytime_child_ped_bike": c["other_daytime_child_ped_bike"],
                "window_no_school_child_ped_bike": c["window_no_school_child_ped_bike"],
                "hours": {"window": round(c["window_hours"]), "other_daytime": round(c["other_hours"]), "window_no_school": round(c["no_school_window_hours"])},
                "per_1000h_window": round(1000 * c["window"] / c["window_hours"], 3),
                "per_1000h_other_daytime": round(1000 * c["other_daytime"] / c["other_hours"], 3),
                "per_1000h_window_no_school": round(1000 * c["window_no_school"] / c["no_school_window_hours"], 3),
                "summed_over_schools_note": "counts are summed over schools, so a crash near two schools counts twice; distinct_window_crashes does not"})

    summary = {
        "question": "Injury crashes near schools at each school's own drop-off and pick-up hours, school days 2022-23 to 2025-26",
        "sources": {"crashes": C.tag, "victims": V.tag, "fatalities": F.tag,
                    "bell": BELL_SNAPSHOT, "calendar": "data/school-hour-crashes/sfusd-calendar.json"},
        "method": {"am_window": "start bell -%d to +%d min" % (AM_BEFORE, AM_AFTER),
                   "pm_window": "end bell -%d to +%d min (early-release time on the early-release weekday)" % (PM_BEFORE, PM_AFTER),
                   "default_bell": "%s to %s for schools with no SFUSD bell row (charter, private)" % (DEFAULT_START, DEFAULT_END),
                   "other_daytime": "%02d:00-%02d:00 on school days outside both windows" % (DAY_START // 60, DAY_END // 60),
                   "radii_ft": {"600ft": 600, "quarter_mile": 1320}},
        "schools": len(schools), "schools_dropped": dict(dropped),
        "schools_with_bell_times": {y: sum(1 for s in schools if y in s["bell"]) for y in YEARS},
        "public_schools_without_bell_times": sorted(s["name"] for s in schools if not s["private"] and not s["bell"]),
        "bell_rows_unmatched": {y: [u[0] for u in v] for y, v in sorted(unmatched.items())},
        "school_days": daycheck, "no_school_weekdays": len(out_weekdays),
        "period_crashes": len(period),
        "city": {k: city_rates(k) for k in RADII},
        "by_bell_source": {g: {k: city_rates(k, groups[g][k], distinct=False) for k in RADII} for g in groups},
        "tiers_600ft": {t: sum(1 for r in results if lo_ <= r["600ft"]["window"] <= hi_) for t, (lo_, hi_) in
                        {"0": (0, 0), "1-2": (1, 2), "3-4": (3, 4), "5+": (5, 10 ** 6)}.items()},
        "walk_audit_schools": walk,
        "fatal_in_window_600ft": fatal_near,
        "field_audit": audit,
        "yearly": yearly,
        "quality": quality,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "schools.json"), "w") as f:
        json.dump(results, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")
    print("schools %d, bell matched %s" % (len(schools), summary["schools_with_bell_times"]))
    print("unmatched bell rows:", json.dumps(summary["bell_rows_unmatched"], indent=0)[:3000])
    print("public without bell:", summary["public_schools_without_bell_times"])
    print(json.dumps(summary["city"], indent=1))
    for r in results[:20]:
        print(r["rank"], r["name"], r["600ft"]["window"], r["quarter_mile"]["window"], r["600ft"]["window_child_ped"], r["600ft"]["window_child_bike"])


if __name__ == "__main__":
    main()
