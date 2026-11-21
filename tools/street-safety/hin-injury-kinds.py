#!/usr/bin/env python3
"""Every person severely injured or killed on SF streets in 2022 to 2024, sorted by where on the High Injury Network, by kind of crash, by where in the intersection, and by a guessed trip type, for Whitepaper Part 1.2 (the HIN piece).

    uv run --no-project --with numpy python tools/street-safety/hin-injury-kinds.py

Writes scratch/runs/hin-injuries/summary.json (every count below) and scratch/runs/hin-injuries/points.geojson (one
point per person, the data prep for the silhouette map). One-off analysis behind a notes page; no page reads it on a
schedule, so the incremental-updater rule doesn't apply yet.

THE BASE. DataSF nwes-mmgh (police crash reports, one row per injured person), victim_degree_of_injury 'Severe Injury'
or 'Fatal Injury', collision_datetime in 2022-01-01 to 2024-12-31. One row is one person (research/sources/
datasf-traffic-crashes.md). Fatal rows are checked against DataSF dau3-4s8f, the Vision Zero fatality log.

ON THE HIN. Within ON_FT (60 ft) of the HIN centerline, the rule scratch/hin-map/hin_split.py used. Both editions:
2022 (data/extract/access/hin-2022.json, drawn from injuries before 2022, so 2022-2024 is new data for it) and 2024
(hin-2024.json, whose metadata says its injuries run to December 2024, so our window is inside the data it was drawn
from). dau3-4s8f's own on_vz_hin_2022 flag checks the 60 ft rule. "Top 40": each injury on the 2024 HIN goes to its
nearest HIN record (one record is one block, or one carriageway run of a divided street); records are ranked by count.

STREET CLASS. DataSF 3psu-pn9h active centerlines, classcode: 2 major, 3 arterial, 4 collector are MAIN; 5 residential.
For where a crash was, a freeway (1) or ramp (6) piece also counts as main (Richardson Ave is class 6), and at a node a
street's class ignores class 0 stubs and, where a surface class is there too, its 1 and 6 pieces.
An intersection crash (intersection = 'Intersection <= 20ft') takes the classes of the streets meeting at its
cnn_intrsctn_fkey node; the primary and secondary roads are matched to them by name. A midblock crash ('Midblock >
20ft' or 'Intersection Rear End <= 150ft') takes the class of the nearest surface segment.

WHICH CROSSWALK. For a pedestrian hurt at a node where a main street meets a residential one, the striking driver
(party_type 'Driver' in DataSF 8gtc-pjc6, at-fault first) tells which crosswalk: straight on the main street or turning
onto it means crossing the main street; turning off the main street or straight on the side street means crossing the
side street. The report doesn't say which crosswalk; this is an inference.

KINDS, the 8 summary kinds in points.geojson's `kind` (first rule that matches wins; each a query on the report's fields):
  late_night       hour of collision_time in 22..23 or 0..3, any day.
  downtown_commute analysis_neighborhood in DOWNTOWN, location on a main street or a class 5 street on the 2024 HIN,
                   weekday, hour 6..9 or 15..18.
  other            hour not stated (one "Other or unplaced" kind with the last rule).
  residential      location is residential (midblock on class 5, or a node where every street is class 5) and placed
                   off the 2024 HIN.
  downtown_other   every other main-street or HIN crash in DOWNTOWN.
  main_elsewhere   every other main-street or HIN crash outside DOWNTOWN, by weekday peak / weekday off-peak / weekend.
  other            freeway ramps, an intersection with no node, unmatched places, even when on the HIN.
DETAILED GROUPS, points.geojson's `kind_detail`: each kind split by DRILL (road user, who hit whom, a driver had been
drinking, place type, driver's move, crash type, cause, hour band, weekday or weekend, age band), taking the first field
that cuts a piece into parts of MIN_CHUNK or more, until no piece is over SPLIT_OVER; a remainder under MIN_CHUNK joins
the smallest part. Then riders and mixed groups where 40% or more had no other moving motor vehicle split on that.
ROAD USER (`user`, `road_user`) is the person's own party in 8gtc-pjc6, the same reading for every table. WHO HIT WHOM uses
tools/street-safety/hin-who-hit-whom.py's mode() and group() rules and labels, copied (that script imports this one).
CAUSE is cause() on vz_pcf_code, the one primary collision factor per crash; under it, SUBCAUSE is the Vehicle Code
section recorded, codes held by fewer than 3 people pooled as "Other <cause>" (summary.json's cause_subcauses).
Alcohol (any party_sobriety starting 'Had Been Drinking') is also reported across all kinds.
On the 2024 HIN uses the 60 ft rule above; a person with no location is neither on nor off. Outputs for the doc:
kinds_chart.mdx (summary PlotChart), kinds_drill.json and scratch/embeds/hin-kinds-drill/index.html (the drill-down,
from the template scripts/hin-kinds-drill.html), and summary.json's kind_details (the levers table).

TRIP TYPE (our inference from time and place alone; mutually exclusive, first match wins):
  school_trip lib/school_window.py's one definition: victim_age 5 to 18, a weekday, 6 am up to 6 pm, August 1 to
  May 31 (no school calendar); late_night 22..3; commute
  weekday 6..9 or 15..18; weekend_day Sat/Sun 10..21; weekday_midday 10..14; evening the rest. Whether a school trip was
  within 1,320 ft of a school's grounds (lib/school_grounds.py, site/data/school-sim/index.json) is reported.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, datetime as dt, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import numpy as np
import sfdata
from lib import school_grounds, school_window

OUT = os.path.join(ROOT, "scratch", "runs", "hin-injuries")
ON_FT, NEAR_MAIN_FT, SCHOOL_FT, CELL = 60, 660, 1320, 500
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
MAIN = {"2", "3", "4"}
MAIN_LIKE = MAIN | {"1", "6"}   # for where a crash was: a freeway or ramp piece (Richardson Ave is class 6) counts as main
DOWNTOWN = {"Financial District/South Beach", "South of Market", "Tenderloin", "Chinatown"}
SEVERE = ("Severe Injury", "Fatal Injury")
# Road user for splitting a kind: the injured person's mode, folded to three groups that point at different fixes.
MODE = {"Walking": "walking", "Biking": "bike or scooter", "Scooter or board": "bike or scooter",
        "Car or truck": "car or motorcycle", "Motorcycle or moped": "car or motorcycle"}
# The summary kinds in chart order (largest first is computed), with two-line labels that fit a 620 px board doc.
KINDS = {
    "Late night, 10 pm to 4 am": "Late night\n10 pm to 4 am",
    "Downtown main streets, weekday peak": "Downtown main streets\nweekday peak",
    "Downtown main streets, other hours": "Downtown main streets\nother hours",
    "Main streets outside downtown, weekday peak": "Main streets elsewhere\nweekday peak",
    "Main streets outside downtown, weekday off-peak": "Main streets elsewhere\nweekday off-peak",
    "Main streets outside downtown, weekend": "Main streets elsewhere\nweekend",
    "Residential streets off the HIN": "Residential streets\noff the HIN",
    "Other or unplaced": "Other or unplaced",
}
ON_HIN_FILL, OFF_HIN_FILL = "#2f7d76", "#a9cfc9"   # --seq-3 and a lighter step of the same ramp

# WHO HIT WHOM, matching tools/street-safety/hin-who-hit-whom.py's mode() and group() (same names, so the two read alike).
BIKE_V = {"Bicycle", "Electric Bicycle", "Motorized Bicycle", "Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
MOTO_V = {"Motorcycle", "Motor Driven Cycle/Scooter", "Moped", "Police Motorcycle"}


def party_mode(p):
    t, v = p.get("party_type"), p.get("stwd_vehicle_type") or ""
    if t == "Pedestrian":
        return "walk"
    if t == "Parked Vehicle":
        return "parked"
    if v in BIKE_V:
        return "bike"
    if v in MOTO_V:
        return "moto"
    if v == "Misc. Non-Motor Vehicle":
        return "other"
    return "car"


def who_group(me, others):
    motor = bool(others & {"car", "moto"})
    if me in ("car", "parked"):
        return "Car occupant, " + ("with another motor vehicle" if motor else "single vehicle")
    if me == "moto":
        return "Motorcyclist, " + ("with another motor vehicle" if motor else "solo")
    if me == "walk":
        return "Walking, hit by a motor vehicle" if motor else "Other"
    if me == "bike":
        return "Biking or scooting, " + ("with a motor vehicle" if motor else "no moving motor vehicle")
    return "Other"


PLACE_TYPE = {"main x main": "Main-street corner", "main x residential": "Main-street corner", "main midblock": "Main-street midblock",
              "residential x residential": "Local-street corner", "residential midblock": "Local-street midblock"}
TIME_WINDOWS = ["Late night, 10 pm to 4 am", "Weekday commute peaks, 6 to 10 am and 3 to 7 pm", "Weekday off-peak", "Weekend, 4 am to 10 pm"]


def hour_band(h):
    if h is None:
        return "hour not stated"
    for lo, hi, lab in ((22, 23, "10 pm to midnight"), (0, 3, "midnight to 4 am"), (4, 5, "4 to 6 am"), (6, 9, "6 to 10 am"),
                        (10, 14, "10 am to 3 pm"), (15, 18, "3 to 7 pm"), (19, 21, "7 to 10 pm")):
        if lo <= h <= hi:
            return lab


# THE DETAILED CHUNKS. Each summary kind is split again and again, by the first field in this list that cuts it into
# pieces of at least MIN_CHUNK people, until every piece is SPLIT_OVER people or fewer. Values with fewer than MIN_CHUNK
# people are pooled as "other ...". The order puts the fields that point at a fix first.
DRILL = [("mode", "road users", lambda o: o["road_user"]),
         ("who", "who hit whom", lambda o: o["who"]),
         ("drink", "drinking", lambda o: "a driver had been drinking" if o["driver_drinking"] else "no drinking driver recorded"),
         ("place_type", "place", lambda o: o["place_type"]),
         ("move", "driver's move", lambda o: o["move"]),
         ("collision", "crash type", lambda o: "crash type " + (o["collision"] or "not stated")),
         ("cause", "cause", lambda o: "cause: " + o["cause"]),
         ("hour_band", "hour", lambda o: o["hour_band"]),
         ("day", "day", lambda o: "weekday" if o["dow"] < 5 else "weekend"),
         ("band", "age", lambda o: {"Kid (0-17)": "kids", "Adult (18-64)": "adults 18 to 64", "Senior (65+)": "seniors 65+"}.get(o["band"], "age not stated"))]
SPLIT_OVER, MIN_CHUNK = 60, 15


def drill(rows, path, out):
    """Leaves of the split tree as (label path, rows), in a stable order."""
    if len(rows) > SPLIT_OVER:
        for key, name, f in DRILL:
            c = collections.Counter(f(o) for o in rows)
            keep = sorted([v for v, k in c.items() if k >= MIN_CHUNK], key=lambda v: (-c[v], v))
            rest = [o for o in rows if f(o) not in keep]
            if len(keep) + (1 if rest else 0) < 2 or (len(keep) == 1 and len(rest) < MIN_CHUNK):
                continue
            if 0 < len(rest) < MIN_CHUNK:   # a small remainder joins the smallest piece rather than standing alone
                small = keep[-1]
                pieces = [(v, [o for o in rows if f(o) == v] + (rest if v == small else [])) for v in keep]
                rest = []
            else:
                pieces = [(v, [o for o in rows if f(o) == v]) for v in keep]
            for v, rs in pieces:
                lab = v[len(path[-1]) + 2:] if v.startswith(path[-1] + ", ") else v   # "Car occupant · single vehicle"
                drill(rs, path + [lab], out)
            if rest:
                drill(rest, path + ["other " + name], out)
            return out
    # Riders and mixed groups where 40% or more had no other moving motor vehicle split on that, whatever the size,
    # because the two halves point at different fixes.
    if path[-1] in ("Biking or scooting", "Motorcyclist", "other road users") and len(rows) > 1:
        solo = [o for o in rows if not o["motor_other"]]
        if 0.4 <= len(solo) / len(rows) < 1:
            out.append((path + ["with a motor vehicle"], [o for o in rows if o["motor_other"]]))
            out.append((path + ["no other moving motor vehicle"], solo))
            return out
    out.append((path, rows))
    return out


def hours_chart(out):
    """The doc's hour-of-day PlotChart: people by the hour of collision_time."""
    c = collections.Counter(o["hour"] for o in out if o["hour"] is not None)
    lab = lambda h: "12 am" if h == 0 else "12 pm" if h == 12 else "%d am" % h if h < 12 else "%d pm" % (h - 12)
    bars = [{"h": h, "l": lab(h), "v": c[h]} for h in range(24)]
    spec = {"data": {"bars": bars},
            "marks": [{"mark": "barY", "data": "bars", "options": {"x": "l", "y": "v", "fill": "#2f7d76", "fillOpacity": 0.85}},
                      {"mark": "text", "data": "bars", "options": {"x": "l", "y": "v", "text": "v", "dy": -6, "fontSize": 10, "fill": "#2f7d76"}}],
            "options": {"width": 620, "height": 260, "marginLeft": 40, "marginRight": 10, "marginTop": 20, "marginBottom": 40,
                        "x": {"domain": [b["l"] for b in bars], "label": "Hour the crash happened", "labelAnchor": "center", "labelArrow": False, "tickSize": 0, "tickRotate": -45},
                        "y": {"label": "People", "grid": True, "tickSize": 0}}}
    j = lambda v: json.dumps(v, ensure_ascii=False)
    return "<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n" % (
        j("As Many People Are Hurt at 1 am as at Noon"), j(spec["data"]), j(spec["marks"]), j(spec["options"]))


def stacked_chart(title, bars, n, killed):
    """A PlotChart block: one stacked bar per item, on the 2024 HIN dark, off it light, each labelled."""
    rows, labels = [], []
    for b in bars:
        rows += [{"d": b["label"], "s": "On the 2024 HIN", "v": b["on_hin"]}, {"d": b["label"], "s": "Off the HIN", "v": b["off_hin"]}]
        unplaced = b["n"] - b["on_hin"] - b["off_hin"]   # no location, so no HIN answer: printed, not drawn
        labels.append({"d": b["label"], "v": b["on_hin"] + b["off_hin"], "t": "%d (%d killed), %d on HIN%s" % (
            b["n"], b["killed"], b["on_hin"], ", %d unplaced" % unplaced if unplaced else "")})
    top = max(b["n"] for b in bars)
    spec = {
        "data": {"bars": rows, "labels": labels},
        "marks": [{"mark": "barX", "data": "bars", "options": {"y": "d", "x": "v", "fill": "s"}},
                  {"mark": "text", "data": "labels", "options": {"y": "d", "x": "v", "text": "t", "dx": 5, "textAnchor": "start", "fontSize": 11, "fill": "#333"}}],
        "options": {"width": 620, "height": 34 * len(bars) + 80, "marginLeft": 160, "marginRight": 160, "marginTop": 10, "marginBottom": 36,
                    "color": {"legend": True, "domain": ["On the 2024 HIN", "Off the HIN"], "range": [ON_HIN_FILL, OFF_HIN_FILL]},
                    "x": {"domain": [0, top], "label": "People severely injured or killed (%d, %d killed)" % (n, killed), "labelAnchor": "center",
                          "labelArrow": False, "grid": True, "tickSize": 0},
                    "y": {"domain": [b["label"] for b in bars], "label": None, "tickSize": 0}},
    }
    j = lambda v: json.dumps(v, ensure_ascii=False)
    return "<PlotChart\n  title=%s\n  data={%s}\n  marks={%s}\n  options={%s}\n/>\n" % (j(title), j(spec["data"]), j(spec["marks"]), j(spec["options"]))


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


def norm(s):
    s = (s or "").upper().replace("'", "").replace(".", "").strip()
    s = re.sub(r"\b0+(\d)", r"\1", s)
    s = s.replace("BAY SHORE", "BAYSHORE").replace("GREAT HIGHWAY", "GREAT HWY")
    return re.sub(r"\s+", " ", s)


SUFFIX = {"ST", "STREET", "STEET", "AVE", "AV", "AVENUE", "BL", "BLVD", "BOULEVARD", "WAY", "DR", "DRIVE", "RD", "ROAD", "TER", "PL", "LN", "CT", "HWY", "EXPY"}


def same_street(a, b):
    """Officer free text ('MISSION STREET', 'ALEMANY BL') against a centerline name: compare without suffixes."""
    f = lambda s: tuple(w for w in norm(s).split() if w not in SUFFIX)
    return bool(a and b) and f(a) == f(b)


def cause(code):
    """Plain cause group of a vz_pcf_code (scratch/hin-map/hin_split.py's cause(), SFPD Focus on the Five plus)."""
    c = (code or "").strip()
    if not c or c.lower() in ("unknown", "na", "other than driver", "other improper driving"):
        return "Unknown or not stated"
    m = re.match(r"(\d+(?:\.\d+)?)(?:\(([a-z])\))?", c)
    if not m:
        return "Other"
    sec, sub = m.group(1), m.group(2)
    if sec == "22350" or (sec.isdigit() and 22348 <= int(sec) <= 22356):
        return "Unsafe speed"
    if sec == "21453":
        return "Pedestrian violation" if sub == "d" else "Red light"
    if sec == "21950":
        return "Pedestrian violation" if sub in ("b", "e") else "Not yielding in crosswalk"
    if sec == "21801":
        return "Left turn, not yielding"
    if sec == "22450":
        return "Stop sign"
    if sec in ("22107", "21658", "22100", "22101", "22102", "21755", "21804"):
        return "Unsafe turn or lane change"   # turns, lane changes, passing on the right, pulling out of a driveway
    if sec == "22517":
        return "Dooring"
    if sec == "21703":
        return "Following too closely"
    if sec in ("23152", "23153"):
        return "DUI"
    if sec in ("21954", "21955", "21456") and not (sec == "21954" and sub == "b"):
        return "Pedestrian violation"
    return "Other"


# SUBCAUSES: under each cause, the Vehicle Code section the officer recorded in vz_pcf_code. The key is the section
# with its first subdivision ("21954(a)" from "21954(a)", "21200(a)" from "21200(a)(1)"); sections in FOLD_SUB are one
# subcause whatever the subdivision, because the label says the same thing for each (21456's walk-signal rules were
# renumbered in 2023, so the data holds (a), (a)(3), (b) and (c) for one act). Labels paraphrase the section text as
# printed by california.public.law, which reproduces leginfo.legislature.ca.gov (leginfo itself refused automated
# reads). [secondary — read 2026-11-19] Every code held by 3 or more people needs a label here; the script asserts it.
FOLD_SUB = {"21456", "21750", "21955", "22100"}
MIN_SUBCAUSE = 3
SUBCAUSE = {
    "22350": "Speed unsafe for conditions",
    "21453(a)": "Not stopping for a red light",
    "21954(a)": "Pedestrian outside a crosswalk not yielding to traffic",
    "21955": "Pedestrian crossing mid-block between signals",
    "21453(d)": "Pedestrian entering the street against a red light",
    "21950(b)": "Pedestrian stepping suddenly into a vehicle's path",
    "21456": "Pedestrian crossing against the walk signal",
    "22107": "Turning or changing lanes unsafely or without signalling",
    "21658(a)": "Leaving a lane unsafely",
    "21804(a)": "Pulling out of a driveway or alley without yielding",
    "21755(a)": "Passing on the right unsafely",
    "22100": "Turning from the wrong lane position",
    "22101(d)": "Disobeying a turn sign or marking",
    "22102": "U-turn mid-block in a business district",
    "21950(a)": "Driver not yielding to a pedestrian in a crosswalk",
    "23152(a)": "Driving under the influence of alcohol",
    "23153(a)": "Driving under the influence of alcohol, injuring someone",
    "23152(g)": "Driving under alcohol and drugs combined",
    "23153(f)": "Driving under the influence of drugs, injuring someone",
    "21801(a)": "Turning left without yielding to oncoming traffic",
    "22450(a)": "Not stopping at a stop sign",
    "21703": "Following too closely",
    "22517": "Opening a door into traffic",
    "22106": "Starting or backing up unsafely",
    "21663": "Driving a motor vehicle on the sidewalk",
    "21657": "Going the wrong way on a one-way street",
    "21650": "Not keeping to the right half of the road",
    "21800(a)": "Not yielding to a vehicle already in the intersection",
    "21460(a)": "Crossing double solid yellow lines",
    "21650.1": "Riding a bicycle against traffic",
    "21750": "Passing on the left unsafely",
    "21461(a)": "Disobeying a regulatory sign or signal",
    "21802(a)": "Not yielding after stopping at a stop sign",
    "21954(b)": "Driver not taking due care for a pedestrian outside a crosswalk",
    "21235(g)": "Riding a motorized scooter on the sidewalk",
    "21651(b)": "Driving left of a median or divider",
    "none": "No code recorded",
    "UNKNOWN": "Recorded as unknown",
}


def code_key(code):
    """The subcause key of a vz_pcf_code (see SUBCAUSE)."""
    c = re.sub(r"\s+", "", code or "").lower()
    if not c:
        return "none"
    m = re.match(r"(\d+(?:\.\d+)?)(?:\(([a-z])\))?(?:\(\d+\))?$", c)   # as cause() reads it, case and spaces aside
    if not m:
        return c.upper()   # "Unknown", "Other Than Driver", local ordinance codes such as "7.2.12TC"
    sec, sub = m.group(1), m.group(2)
    return sec if sec in FOLD_SUB or not sub else "%s(%s)" % (sec, sub)


def subcauses(out):
    """Set o['subcause'] for every person; return {cause: [(label, tip, people), ...]} biggest first, the pooled rest last."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for o in out:
        by[o["cause"]][code_key(o["pcf"])].append(o)
    res = {}
    for c, keys in by.items():
        big = sorted([k for k, rs in keys.items() if len(rs) >= MIN_SUBCAUSE], key=lambda k: (-len(keys[k]), k))
        missing = [k for k in big if k not in SUBCAUSE]
        assert not missing, "codes held by %d or more people need a label in SUBCAUSE: %s" % (MIN_SUBCAUSE, missing)
        groups = []
        for k in big:
            codes = sorted({(o["pcf"] or "").strip() for o in keys[k]} - {""})
            lab = SUBCAUSE[k] + (" (VC %s)" % k if k[0].isdigit() else "")
            # A tip only where it adds something: the subdivisions folded into one row.
            groups.append((lab, "Recorded as " + ", ".join(codes) if k[0].isdigit() and codes != [k] else "", keys[k], k))
        small = sorted([k for k in keys if k not in big], key=lambda k: (-len(keys[k]), k))
        if small:
            rest = [o for k in small for o in keys[k]]
            name = "Other codes" if c == "Other" else "Other " + (c if c[:2].isupper() else c[0].lower() + c[1:])
            recorded = collections.Counter((o["pcf"] or "").strip() or "none" for o in rest)
            tip = "Codes under %d people each: " % MIN_SUBCAUSE + ", ".join(
                "%s (%d)" % (k, v) for k, v in sorted(recorded.items(), key=lambda kv: (-kv[1], kv[0])))
            groups.append((name, tip, rest, "other"))
        # Each person's subcause label, and its key: the code_key() of the section, or "other" for the pooled rest.
        # The Street Safety map filters on the key (tools/street-safety/street-safety-map.py), so a link survives a relabel.
        for lab, _, rs, key in groups:
            for o in rs:
                o["subcause"], o["subcause_key"] = lab, key
        # Subcauses add up to their cause, person for person.
        assert sum(len(rs) for _, _, rs, _ in groups) == sum(len(rs) for rs in keys.values())
        assert len({id(o) for _, _, rs, _ in groups for o in rs}) == sum(len(rs) for rs in keys.values())
        res[c] = [g[:3] for g in groups]
    assert all("subcause" in o and "subcause_key" in o for o in out)
    return res


class Lines(object):
    """Polylines in feet with a grid for nearest-line queries."""

    def __init__(self, items):
        self.items, grid = items, collections.defaultdict(list)
        for k, (P, _) in enumerate(items):
            for a, b in zip(P, P[1:]):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        grid[(cx, cy)].append((a[0], a[1], b[0], b[1], k))
        self.cells = {k: np.array(v) for k, v in grid.items()}

    def within(self, x, y, ft):
        """{item index: distance} of every item within ft of (x, y)."""
        cx, cy, got = int(x // CELL), int(y // CELL), {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                A = self.cells.get((cx + dx, cy + dy))
                if A is None:
                    continue
                ddx, ddy = A[:, 2] - A[:, 0], A[:, 3] - A[:, 1]
                L2 = ddx * ddx + ddy * ddy
                t = np.clip(np.where(L2 > 0, ((x - A[:, 0]) * ddx + (y - A[:, 1]) * ddy) / np.where(L2 > 0, L2, 1), 0), 0, 1)
                d = np.hypot(x - (A[:, 0] + t * ddx), y - (A[:, 1] + t * ddy))
                for j in np.nonzero(d <= ft)[0]:
                    k = int(A[j, 4])
                    got[k] = min(got.get(k, 1e9), float(d[j]))
        return got

    def nearest(self, x, y, reach=1):
        cx, cy, best = int(x // CELL), int(y // CELL), (None, float("inf"))
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                A = self.cells.get((cx + dx, cy + dy))
                if A is None:
                    continue
                ddx, ddy = A[:, 2] - A[:, 0], A[:, 3] - A[:, 1]
                L2 = ddx * ddx + ddy * ddy
                t = np.clip(np.where(L2 > 0, ((x - A[:, 0]) * ddx + (y - A[:, 1]) * ddy) / np.where(L2 > 0, L2, 1), 0), 0, 1)
                d = np.hypot(x - (A[:, 0] + t * ddx), y - (A[:, 1] + t * ddy))
                i = int(np.argmin(d))
                if d[i] < best[1]:
                    best = (int(A[i, 4]), float(d[i]))
        return best


def hour(v):
    t = v.get("collision_time") or ""
    return int(t[:2]) if re.match(r"^\d\d:", t) else None


def write_drill(out, chunks, subs, tags, n, killed):
    """The drill-down embed's data (kinds_drill.json) and page (scratch/embeds/hin-kinds-drill/index.html, from the
    template scripts/hin-kinds-drill.html): one row per person, coded against the five groupings, the chunk list and,
    for the cause grouping, the subcause list (in each cause's order, the pooled rest last)."""
    groupings = [("kind", "Time and place"), ("who", "Who hit whom"), ("cause", "Recorded cause"),
                 ("place_type", "Place"), ("time_window", "Time window")]
    dicts = {k: sorted({o[k] for o in out}) for k, _ in groupings}
    details = [" · ".join(p) for p, _ in chunks]
    sublist = [{"label": lab, "tip": tip} for c in sorted(subs) for lab, tip, _ in subs[c]]
    sub_ix = {(c, lab): i for i, (c, lab) in enumerate((c, lab) for c in sorted(subs) for lab, _, _ in subs[c])}
    people = [[dicts[k].index(o[k]) for k, _ in groupings] + [details.index(o["kind_detail"]), int(o["severity"] == "Killed"),
              None if o.get("hin2024") is None else int(o["hin2024"]), sub_ix[(o["cause"], o["subcause"])]] for o in out]
    D = {"groupings": [{"key": k, "name": nm, "values": dicts[k]} for k, nm in groupings], "details": details,
         "subcauses": sublist, "no_code": sum(code_key(o["pcf"]) == "none" for o in out),
         "people": people, "n": n, "killed": killed, "read": tags["victims"]}
    with open(os.path.join(OUT, "kinds_drill.json"), "w") as f:
        json.dump(D, f, sort_keys=True); f.write("\n")
    page = open(os.path.join(HERE, "hin-kinds-drill.html")).read().replace("__DATA__", json.dumps(D, sort_keys=True), 1)
    emb = os.path.join(ROOT, "scratch", "embeds", "hin-kinds-drill")
    os.makedirs(emb, exist_ok=True)
    with open(os.path.join(emb, "index.html"), "w") as f:
        f.write(page)


def main():
    os.makedirs(OUT, exist_ok=True)
    V = sfdata.fetch("nwes-mmgh", where="victim_degree_of_injury in ('Severe Injury','Fatal Injury') and "
                     "collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59'", floor=800)
    F = sfdata.fetch("dau3-4s8f", select="unique_id,case_id_fkey,collision_datetime,on_vz_hin_2022,latitude,longitude",
                     where="collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59'", floor=80)
    C = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                     where="active='true'", floor=15000)
    rows = {}
    for v in V.rows:
        rows[(v["case_id_pkey"], v["victim_id"])] = v
    rows = [rows[k] for k in sorted(rows)]
    ids = sorted({r["case_id_pkey"] for r in rows})
    P = sfdata.fetch("8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,at_fault,street_of_travel,move_pre_acc,"
                     "stwd_vehicle_type,party_sobriety,party_age", where="case_id_pkey in (%s)" % ",".join("'%s'" % i for i in ids))
    parties = collections.defaultdict(dict)
    for p in P.rows:
        parties[p["case_id_pkey"]][p.get("party_number_ckey")] = p
    tags = {"victims": V.tag, "fatality_log": F.tag, "centerlines": C.tag, "parties": P.tag}

    # Centerlines: segments, node membership, grid of surface segments and of main streets.
    segs, at_node, surf, main_items = [], collections.defaultdict(list), [], []
    for r in C.rows:
        if not r.get("line"):
            continue
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for ln in lines:
            Pp = [xy(*p) for p in ln]
            s = {"cnn": int(float(r["cnn"])), "street": norm(r.get("streetname")), "cls": r.get("classcode") or "0",
                 "layer": r.get("layer") or ""}
            if not s["layer"].startswith(("FREEWAYS", "PAPER", "PSEUDO")):
                surf.append((Pp, s))
                if s["cls"] in MAIN:
                    main_items.append((Pp, s))
        for n in (r.get("f_node_cnn"), r.get("t_node_cnn")):
            if n:
                at_node[int(float(n))].append({"street": norm(r.get("streetname")), "cls": r.get("classcode") or "0"})
    n_segments = len({s["cnn"] for _, s in surf if s["cls"] in MAIN | {"5"}})
    SURF, MAINL = Lines(surf), Lines(main_items)
    BY_CNN = {s["cnn"]: s for _, s in surf}

    hin = {}
    for ed in ("2022", "2024"):
        H = json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-%s.json" % ed)))
        items = [([xy(*p) for p in rec["pts"]], rec) for rec in H["records"] if len(rec["pts"]) > 1]
        hin[ed] = (Lines(items), H["fetched_on"], H["meta"]["url"])

    sch = json.load(open(os.path.join(ROOT, "site", "data", "school-sim", "index.json")))["schools"]
    lo = np.array([float(r["tb_longitude"]) if r.get("tb_longitude") else np.nan for r in rows])
    la = np.array([float(r["tb_latitude"]) if r.get("tb_latitude") else np.nan for r in rows])
    ok = ~np.isnan(lo)
    sj, sd = school_grounds.nearest([(s["lon"], s["lat"]) for s in sch], np.where(ok, lo, 0), np.where(ok, la, 0), SCHOOL_FT)

    out = []
    for i, r in enumerate(rows):
        d = dt.datetime.fromisoformat(r["collision_datetime"][:19])
        h = hour(r)
        role = r.get("victim_role") or "Other"
        # Road user: the person's own party (8gtc-pjc6, by party_number_ckey), as tools/street-safety/hin-who-hit-whom.py reads it.
        ps = parties[r["case_id_pkey"]]
        own = ps.get(r.get("party_number_ckey"))
        me = "walk" if role == "Pedestrian" else party_mode(own) if own else party_mode(r)
        vt = (own or r).get("stwd_vehicle_type") or ""
        user = {"walk": "Walking", "moto": "Motorcycle or moped", "car": "Car or truck", "parked": "Car or truck",
                "bike": "Biking" if vt in ("Bicycle", "Electric Bicycle", "Motorized Bicycle") else "Scooter or board"}.get(me, "Other")
        try:
            age = int(r.get("victim_age"))
        except (TypeError, ValueError):
            age = None
        if age == 0 and role == "Driver":
            age = None   # a sentinel: no driver is 0
        band = None if age is None or age >= 125 else "Kid (0-17)" if age < 18 else "Senior (65+)" if age >= 65 else "Adult (18-64)"
        rec = {"case": r["case_id_pkey"], "victim": r["victim_id"], "severity": "Killed" if r["victim_degree_of_injury"] == "Fatal Injury" else "Severe",
               "date": d.date().isoformat(), "hour": h, "dow": d.weekday(), "user": user, "age": age, "band": band,
               "cause": cause(r.get("vz_pcf_code")), "pcf": r.get("vz_pcf_code"), "collision": r.get("type_of_collision"),
               "ped_action": r.get("ped_action"), "lighting": r.get("lighting"), "hood": r.get("analysis_neighborhood"),
               "primary": r.get("primary_rd"), "secondary": r.get("secondary_rd"), "lon": None, "lat": None}
        drunk = lambda p: (p.get("party_sobriety") or "").startswith("Had Been Drinking")
        drv = [p for p in parties[r["case_id_pkey"]].values() if p.get("party_type") == "Driver"]
        drv.sort(key=lambda p: (p.get("at_fault") != "Yes", p.get("party_number_ckey") or ""))
        rec["alcohol"] = any(drunk(p) for p in parties[r["case_id_pkey"]].values())
        rec["driver_drinking"] = any(drunk(p) for p in drv)
        # The injured person was the drinking driver, or rode in that driver's vehicle.
        rec["own_party_drinking"] = bool(own) and own.get("party_type") == "Driver" and drunk(own)
        rec["driver_sobriety"] = sorted({p.get("party_sobriety") or "" for p in drv})
        rec["driver_move"] = drv[0].get("move_pre_acc") if drv else None
        rec["driver_street"] = drv[0].get("street_of_travel") if drv else None
        rec["driver_vehicle"] = drv[0].get("stwd_vehicle_type") if drv else None
        rec["has_driver"] = bool(drv)
        ixf = r.get("intersection") or ""
        rec["at"] = "intersection" if ixf.startswith("Intersection <=") else "midblock" if ixf else "unknown"
        if ok[i]:
            x, y = xy(lo[i], la[i])
            rec["lon"], rec["lat"] = round(float(lo[i]), 6), round(float(la[i]), 6)
            k, dd = SURF.nearest(x, y)
            seg = SURF.items[k][1] if k is not None and dd <= 150 else None
            sk = int(float(r["cnn_sgmt_fkey"])) if r.get("cnn_sgmt_fkey") else None
            if sk in BY_CNN:   # the city's own segment key wins over our snap
                seg = BY_CNN[sk]
            rec["seg"] = seg["cnn"] if seg else None
            for ed, (L, _, _) in hin.items():
                k2, d2 = L.nearest(x, y)
                rec["hin" + ed] = d2 <= ON_FT
                # Every record within 5 ft of the nearest shares the person, so a corner where four HIN blocks meet
                # splits them evenly instead of handing them to whichever block the grid lists first. Records are
                # keyed by id; an id that spans several records (divided streets) is one block.
                near = {L.items[k][1]["id"] for k, dk in L.within(x, y, d2 + 5).items()} if d2 <= ON_FT else set()
                rec["hin%s_rec" % ed] = sorted(near) or None
            km, dm = MAINL.nearest(x, y, reach=2)
            rec["main_ft"] = round(dm) if dm < 1e9 else None
            rec["school_ft"] = None if sj[i] < 0 else round(float(sd[i]))
        else:
            seg = None
            rec.update({"seg": None, "hin2022": None, "hin2024": None, "hin2022_rec": None, "hin2024_rec": None, "main_ft": None, "school_ft": None})
        # Street class at the place.
        node = int(float(r["cnn_intrsctn_fkey"])) if r.get("cnn_intrsctn_fkey") else None
        here = at_node.get(node, []) if node else []
        def cls_of(name):
            # Ignore class 0 stubs (paper streets, UPROW, pedestrian pieces) and, where a surface class is there too,
            # freeway (1) and ramp (6) pieces of the same name, so a stub doesn't turn a real street into "other".
            cs = {s["cls"] for s in here if s["street"] == norm(name)} - {"0"}
            cs = (cs - {"1", "6"}) or cs
            return min(cs) if cs else None
        if rec["at"] == "intersection" and here:
            pc, sc = cls_of(r.get("primary_rd")), cls_of(r.get("secondary_rd"))
            classes = {s["cls"] for s in here if s["cls"] != "0"} or {"0"}
            rec["name_fallback"] = pc is None or sc is None
            if pc is None or sc is None:
                pc = pc or min(classes); sc = sc or max(classes)
            kinds = {"main" if c in MAIN_LIKE else "res" if c == "5" else "other" for c in (pc, sc)}
            rec["place"] = ("main x main" if kinds in ({"main"}, {"main", "other"}) else "main x residential" if kinds == {"main", "res"}
                            else "residential x residential" if kinds == {"res"} else "other")
            rec["main_street"] = (r.get("primary_rd") if pc in MAIN_LIKE else r.get("secondary_rd")) if rec["place"] == "main x residential" else None
        elif rec["at"] in ("midblock", "intersection") and seg:
            rec["place"] = "main midblock" if seg["cls"] in MAIN_LIKE else "residential midblock" if seg["cls"] == "5" else "other"
            if rec["at"] == "intersection":   # no node on the record: say so rather than guess the crossing
                rec["place"] = "intersection, node unknown"
            rec["main_street"] = None
        else:
            rec["place"], rec["main_street"] = "unknown", None
        rec["on_main"] = rec["place"] in ("main midblock", "main x main", "main x residential")
        rec["on_res"] = rec["place"] in ("residential midblock", "residential x residential")
        # The city's class 5 includes commercial streets on the HIN (Polk, Valencia, Ellis, Haight). Only class 5 off
        # the 2024 HIN counts as a residential street for the kinds; class 5 on the HIN counts with main streets.
        rec["res_on_hin"] = bool(rec["on_res"] and rec.get("hin2024"))
        if rec["res_on_hin"]:
            rec["on_res"], rec["on_main"] = False, True
        # Which crosswalk, for pedestrians at a main x residential node.
        rec["crossing"] = None
        if user == "Walking" and rec["place"] == "main x residential":
            on = rec["driver_street"]
            mv = rec["driver_move"] or ""
            turn = "turn" if "Turn" in mv or "U-Turn" in mv else "straight" if "Straight" in mv else "other"
            if not on or turn == "other":
                rec["crossing"] = "can't tell"
            else:
                on_main = same_street(on, rec["main_street"])
                rec["crossing"] = ("crossing the main street" if (on_main and turn == "straight") or (not on_main and turn == "turn")
                                   else "crossing the side street (driver turning off or along it)")
        # Kind: the summary kind (KINDS in the docstring); kind_detail, its detailed chunk, is set after the loop.
        wk = rec["dow"] < 5
        late = h is not None and (h >= 22 or h < 4)
        peak = h is not None and (6 <= h <= 9 or 15 <= h <= 18)
        when = "weekday peak" if wk and peak else "weekday off-peak" if wk else "weekend"
        if late:
            kind = "Late night, 10 pm to 4 am"
        elif rec["hood"] in DOWNTOWN and rec["on_main"] and wk and peak:
            kind = "Downtown main streets, weekday peak"
        elif h is None:
            kind = "Other or unplaced"
        elif rec["on_res"] and rec.get("hin2024") is False:
            kind = "Residential streets off the HIN"
        elif rec["on_main"] and rec["hood"] in DOWNTOWN:
            kind = "Downtown main streets, other hours"
        elif rec["on_main"]:
            kind = "Main streets outside downtown, " + when
        else:
            kind = "Other or unplaced"
        rec["kind"] = kind
        # The fields the detailed chunks and the drill-down's groupings split on.
        others = {party_mode(p) for k, p in ps.items() if k != r.get("party_number_ckey")} - {"parked"}
        rec["who"] = who_group(me, others)
        rec["motor_other"] = bool(others & {"car", "moto"})
        rec["road_user"] = {"walk": "Walking", "car": "Car occupant", "parked": "Car occupant", "moto": "Motorcyclist",
                            "bike": "Biking or scooting"}.get(me, "Other road user")
        rec["place_type"] = PLACE_TYPE.get(rec["place"], "Other or unknown place")
        rec["hour_band"] = hour_band(h)
        rec["time_window"] = (TIME_WINDOWS[0] if late else "Time not stated" if h is None else TIME_WINDOWS[1] if wk and peak
                              else TIME_WINDOWS[2] if wk else TIME_WINDOWS[3])
        mv = rec["driver_move"] or ""
        rec["move"] = ("no driver in the crash" if not rec["has_driver"] else "driver turning" if "Turn" in mv
                       else "driver going straight" if "Straight" in mv else "driver doing something else")
        # Trip type, our inference.
        if age is not None and school_window.AGE_MIN <= age <= school_window.AGE_MAX and school_window.in_window(d.date(), h):
            trip = "School trips: kids 5 to 18 on weekdays, 6 am to 6 pm"
        elif late:
            trip = "Late night (10 pm to 4 am)"
        elif wk and peak:
            trip = "Weekday commute peak"
        elif not wk and h is not None and 10 <= h <= 21:
            trip = "Weekend daytime and evening"
        elif wk and h is not None and 10 <= h <= 14:
            trip = "Weekday midday"
        elif h is None:
            trip = "Time not stated"
        else:
            trip = "Other hours (early morning, weekday evening)"
        rec["trip"] = trip
        out.append(rec)

    # ---- Checks.
    n = len(out)
    assert 850 <= n <= 1000, n
    assert len({(o["case"], o["victim"]) for o in out}) == n
    fat = sum(o["severity"] == "Killed" for o in out)
    placed = sum(o["lon"] is not None for o in out)

    # Published total: fatal victims against the Vision Zero fatality log, by year.
    fy, vy = collections.Counter(f["collision_datetime"][:4] for f in F.rows), collections.Counter(o["date"][:4] for o in out if o["severity"] == "Killed")
    # The fatality log's own HIN-2022 flag against our 60 ft rule, joined by case id.
    assert all(abs(fy[y] - vy[y]) <= 2 for y in ("2022", "2023", "2024")), (fy, vy)
    flag = {}
    for f in F.rows:
        flag.setdefault(f.get("case_id_fkey"), []).append(f.get("on_vz_hin_2022"))
    agree = collections.Counter()
    for o in out:
        if o["severity"] == "Killed" and o["case"] in flag and o["hin2022"] is not None:
            agree[(str(flag[o["case"]][0]), o["hin2022"])] += 1

    def share(pred, base=None):
        b = [o for o in out if (base is None or base(o))]
        k = sum(1 for o in b if pred(o))
        return {"n": k, "of": len(b), "pct": round(100.0 * k / len(b), 1) if b else None}

    S = {"sources": tags, "hin_sources": {ed: {"fetched_on": v[1], "url": v[2]} for ed, v in hin.items()},
         "n": n, "killed": fat, "severe": n - fat, "placed": placed,
         "by_year": dict(sorted(collections.Counter(o["date"][:4] for o in out).items())),
         "published_total_fatal": {"fatality_log": dict(sorted(fy.items())), "victims_table": dict(sorted(vy.items()))},
         "hin_flag_check_2022": {"%s|ours=%s" % k: v for k, v in sorted(agree.items(), key=str)}}
    pl = lambda o: o["lon"] is not None
    S["hin"] = {ed: {"on": share(lambda o, e=ed: o["hin" + e], pl), "on_killed": share(lambda o, e=ed: o["hin" + e], lambda o: pl(o) and o["severity"] == "Killed")}
                for ed in ("2022", "2024")}
    # Top 40 blocks of the 2024 HIN, with each person split evenly across the HIN blocks at their spot.
    cnt = collections.defaultdict(float)
    for o in out:
        for k in o.get("hin2024_rec") or []:
            cnt[k] += 1.0 / len(o["hin2024_rec"])
    H24 = collections.defaultdict(list)
    for rec in json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-2024.json")))["records"]:
        H24[rec["id"]].append(rec)
    def miles(k):
        tot = 0.0
        for rec in H24[k]:
            Pp = [xy(*p) for p in rec["pts"]]
            tot += sum(math.dist(a, b) for a, b in zip(Pp, Pp[1:])) / 5280
        return tot
    top = sorted(cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))
    t40 = top[:40]
    cut = t40[-1][1] if t40 else None
    S["top40_2024"] = {"blocks_on_hin": len(H24), "blocks_with_any": len(cnt), "blocks_with_none": len(H24) - len(cnt),
                       "top40_injuries": round(sum(c for _, c in t40), 1), "top40_min_count": round(cut, 2),
                       "blocks_tied_at_cutoff": sum(1 for _, c in top if abs(c - cut) < 1e-9),
                       "top40_miles": round(sum(miles(k) for k, _ in t40), 1), "hin_miles_raw": round(sum(miles(k) for k in H24), 1),
                       "top40_blank_street_blocks": sum(1 for k, _ in t40 if not H24[k][0]["street"].strip()),
                       "top40_share_of_all": round(100.0 * sum(c for _, c in t40) / placed, 1),
                       "top40_share_of_on_hin": round(100.0 * sum(c for _, c in t40) / sum(cnt.values()), 1),
                       "max_on_one_block": round(top[0][1], 2) if top else None,
                       "top10": [[H24[k][0]["street"].strip() or "(divided street)", round(c, 2)] for k, c in top[:10]]}
    off = [o for o in out if pl(o) and not o["hin2024"]]
    S["off_hin_2024"] = {"injuries": len(off), "distinct_segments": len({o["seg"] for o in off if o["seg"]}),
                         "segments_citywide_main_or_residential": n_segments,
                         "segments_with_any_injury": len({o["seg"] for o in out if o["seg"]}),
                         "max_on_one_offhin_segment": max(collections.Counter(o["seg"] for o in off if o["seg"]).values())}

    def tab(key, base=lambda o: True):
        b = [o for o in out if base(o)]
        c = collections.Counter(o[key] for o in b)
        return [{"k": k, "n": v, "pct": round(100.0 * v / len(b), 1), "killed": sum(1 for o in b if o[key] == k and o["severity"] == "Killed")}
                for k, v in c.most_common()]
    S["kinds"] = tab("kind")
    # Detailed chunks: each summary kind split by DRILL until no piece is over SPLIT_OVER people.
    chunks = []
    for k in KINDS:
        chunks += drill([o for o in out if o["kind"] == k], [k], [])
    for path, rs in chunks:
        for o in rs:
            o["kind_detail"] = " · ".join(path)
    assert all("kind_detail" in o for o in out) and len({(o["case"], o["victim"]) for _, rs in chunks for o in rs}) == n
    count = lambda rs: {"n": len(rs), "killed": sum(o["severity"] == "Killed" for o in rs),
                        "on_hin": sum(o.get("hin2024") is True for o in rs), "off_hin": sum(o.get("hin2024") is False for o in rs)}
    def top(rs, f):
        """The two most common values, and every value tied with the second when that tie is 2 or more."""
        c = sorted(collections.Counter(f(o) for o in rs).items(), key=lambda kv: (-kv[1], str(kv[0])))
        return [[v, k] for i, (v, k) in enumerate(c) if i < 2 or (k >= 2 and k == c[1][1])]
    S["kind_details"] = [dict(count(rs), kind=path[0], detail=" · ".join(path), causes=top(rs, lambda o: o["cause"]),
                              types=top(rs, lambda o: o["collision"] or "Not Stated"), moves=top(rs, lambda o: o["move"]),
                              drinking=sum(o["driver_drinking"] for o in rs)) for path, rs in chunks]
    S["kind_summary"] = sorted([dict(count([o for o in out if o["kind"] == k]), kind=k, label=lab) for k, lab in KINDS.items()],
                               key=lambda b: (-b["n"], b["kind"]))
    assert sum(b["n"] for b in S["kind_summary"]) == n and set(S["kinds"][i]["k"] for i in range(len(S["kinds"]))) <= set(KINDS)
    late = next(g for g in S["kinds"] if g["k"].startswith("Late night"))
    assert 20 <= late["pct"] < 30 and 0.25 <= late["killed"] / fat < 0.35, "the chart title's 'a quarter' and '3 in 10' no longer hold"
    S["kinds_by_user"] = {k: dict(collections.Counter(o["user"] for o in out if o["kind"] == k)) for k in {o["kind"] for o in out}}
    S["kinds_by_cause"] = {k: dict(collections.Counter(o["cause"] for o in out if o["kind"] == k).most_common(4)) for k in {o["kind"] for o in out}}
    S["kinds_on_hin2024"] = {k: share(lambda o: o["hin2024"], lambda o, k=k: o["kind"] == k and pl(o)) for k in {o["kind"] for o in out}}
    S["alcohol"] = share(lambda o: o["alcohol"])
    S["driver_drinking"] = share(lambda o: o["driver_drinking"])
    S["driver_drinking_late"] = share(lambda o: o["driver_drinking"], lambda o: o["kind"].startswith("Late night"))
    S["alcohol_late"] = share(lambda o: o["alcohol"], lambda o: o["kind"].startswith("Late night"))
    S["dark_late"] = dict(collections.Counter(o["lighting"] for o in out if o["kind"].startswith("Late night")))
    S["users"] = tab("user")
    S["ped_bands"] = tab("band", lambda o: o["user"] == "Walking")
    S["place"] = tab("place")
    S["place_by_user"] = {u: tab("place", lambda o, u=u: o["user"] == u) for u in ("Walking", "Biking", "Car or truck", "Motorcycle or moped", "Scooter or board")}
    S["local_place_on_hin"] = {k: share(lambda o: o.get("hin2024"), lambda o, k=k: o["place"] == k and pl(o)) for k in ("residential midblock", "residential x residential")}
    S["name_fallback"] = sum(1 for o in out if o.get("name_fallback"))
    S["ped_place_by_band"] = {b: tab("place", lambda o, b=b: o["user"] == "Walking" and o["band"] == b) for b in ("Kid (0-17)", "Adult (18-64)", "Senior (65+)")}
    S["ped_crossing"] = tab("crossing", lambda o: o["user"] == "Walking" and o["place"] == "main x residential")
    S["ped_crossing_by_band"] = {b: tab("crossing", lambda o, b=b: o["user"] == "Walking" and o["place"] == "main x residential" and o["band"] == b)
                                 for b in ("Kid (0-17)", "Adult (18-64)", "Senior (65+)")}
    S["at"] = tab("at")
    S["at_by_user"] = {u: tab("at", lambda o, u=u: o["user"] == u) for u in ("Walking", "Biking", "Car or truck", "Motorcycle or moped", "Scooter or board")}
    S["trip"] = tab("trip")
    S["trip_kids"] = tab("trip", lambda o: o["band"] == "Kid (0-17)")
    sch_trip = lambda o: o["trip"].startswith("School trips")
    S["school_trips"] = {"n": sum(map(sch_trip, out)), "killed": sum(sch_trip(o) and o["severity"] == "Killed" for o in out),
                         "kids": sum(o["band"] == "Kid (0-17)" for o in out),
                         "on_hin": sum(sch_trip(o) and o.get("hin2024") is True for o in out),
                         "near_school": sum(sch_trip(o) and o["school_ft"] is not None for o in out),
                         "by_user": dict(collections.Counter(o["user"] for o in out if sch_trip(o))),
                         "by_hour": dict(collections.Counter(o["hour"] for o in out if sch_trip(o))),
                         "near_school_on_hin": sum(sch_trip(o) and o["school_ft"] is not None and o.get("hin2024") is True for o in out)}
    S["downtown_commute_share_of_downtown"] = share(lambda o: o["trip"] == "Weekday commute peak", lambda o: o["hood"] in DOWNTOWN)
    S["cause"] = tab("cause")
    for k in ("main x residential", "main midblock"):
        assert any(p["k"] == k for p in S["place"]), k
    assert sum(p["n"] for p in S["kinds"]) == n and sum(p["n"] for p in S["trip"]) == n
    # Figures the doc's sentences quote, so each is computed rather than typed.
    late = [o for o in out if o["kind"].startswith("Late night")]
    UNK = ("Impairment Not Known", "Not Stated", "")
    S["late_drinking"] = {"people": sum(o["driver_drinking"] for o in late), "of": len(late),
                          "crashes": len({o["case"] for o in late if o["driver_drinking"]}), "crashes_of": len({o["case"] for o in late}),
                          "own_party": sum(o["own_party_drinking"] for o in late),
                          "all_people": sum(o["driver_drinking"] for o in out), "all_own_party": sum(o["own_party_drinking"] for o in out),
                          "sobriety_unknown_people": sum(1 for o in late if not o["driver_drinking"] and any(x in UNK for x in o["driver_sobriety"]))}
    dtn = [o for o in out if o["hood"] in DOWNTOWN]
    S["downtown_weekday_peak_any_place"] = {"n": sum(1 for o in dtn if o["dow"] < 5 and o["hour"] is not None and (6 <= o["hour"] <= 9 or 15 <= o["hour"] <= 18)), "of": len(dtn)}
    res = [o for o in out if o["kind"] == "Residential streets off the HIN"]
    S["residential_no_driver"] = dict(collections.Counter(o["road_user"] for o in res if not o["has_driver"]))
    logcases = {f.get("case_id_fkey") for f in F.rows if f.get("case_id_fkey")}
    ourk = {o["case"] for o in out if o["severity"] == "Killed"}
    S["fatality_log_by_case"] = {"our_killed_people": fat, "people_matched": sum(1 for o in out if o["severity"] == "Killed" and o["case"] in logcases),
                                 "log_rows_no_case": sum(1 for f in F.rows if not f.get("case_id_fkey")), "log_cases_not_ours": len(logcases - ourk),
                                 "hin2022_flag_disagree": sum(v for k, v in agree.items() if (k[0].lower() in ("true", "1", "yes")) != k[1]),
                                 "hin2022_flag_compared": sum(agree.values())}
    S["rule_order"] = {"late_downtown": sum(o["hood"] in DOWNTOWN for o in late),
                       "late_residential_off_hin": sum(o["place"] in ("residential midblock", "residential x residential") and o.get("hin2024") is False for o in late),
                       "class5_on_hin": sum(o["res_on_hin"] for o in out), "class5_on_hin_late": sum(o["res_on_hin"] for o in late),
                       "offpeak_4_to_6am": sum(o["kind"] == "Main streets outside downtown, weekday off-peak" and o["hour"] in (4, 5) for o in out)}
    S["other_kind"] = [[o["place"], o["primary"], o["secondary"], o["hour"], o["lon"] is None] for o in out if o["kind"] == "Other or unplaced"]
    with open(os.path.join(OUT, "hours_chart.mdx"), "w") as f:
        f.write(hours_chart(out))
    with open(os.path.join(OUT, "kinds_chart.mdx"), "w") as f:
        f.write(stacked_chart("Late Night Holds a Quarter of Severe Injuries and 3 in 10 Deaths, 2022 to 2024", S["kind_summary"], n, fat))
    subs = subcauses(out)
    S["cause_subcauses"] = {c: [{"subcause": lab, "codes": tip, "n": len(rs), "killed": sum(o["severity"] == "Killed" for o in rs)}
                                for lab, tip, rs in g] for c, g in sorted(subs.items())}
    S["pcf_code_null"] = share(lambda o: code_key(o["pcf"]) == "none")
    for c, g in S["cause_subcauses"].items():   # each cause's subcauses add up to its row in S["cause"]
        row = next(r for r in S["cause"] if r["k"] == c)
        assert sum(x["n"] for x in g) == row["n"] and sum(x["killed"] for x in g) == row["killed"], c
    write_drill(out, chunks, subs, tags, n, fat)

    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(S, f, indent=1, sort_keys=True); f.write("\n")
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [o["lon"], o["lat"]]},
              "properties": {k: o[k] for k in ("case", "victim", "severity", "date", "hour", "user", "band", "cause", "collision", "ped_action",
                                               "place", "crossing", "kind", "kind_detail", "trip", "hin2024", "driver_move", "at", "pcf",
                                               "subcause", "subcause_key")}}
             for o in out if o["lon"] is not None]
    with open(os.path.join(OUT, "points.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "sources": tags, "features": feats}, f, sort_keys=True); f.write("\n")
    print(json.dumps({k: S[k] for k in ("n", "killed", "placed", "by_year", "published_total_fatal", "hin_flag_check_2022", "hin", "top40_2024", "off_hin_2024")}, indent=1))


if __name__ == "__main__":
    main()
