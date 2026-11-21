#!/usr/bin/env python3
"""Cars per minute at rush hour on every San Francisco residential and main-street block: counted where SFMTA counted it, modelled where SF-CHAMP carries the street, and on residential blocks also carried along the street from a count or estimated from the parallel main street, on a doubling scale from 1.5 to 48 cars a minute, with the people hurt on each.

    python3 tools/street-safety/hin-cut-through.py

Bryan, 2026-11-18 on the Part 1.2 Data and Notes doc: "identify every residential street with
more than 1.5 car per minute at rush hour. At gradations." Then: "wherever we have SFMTA traffic counts. Or Telraam
public data, or something else, we can estimate. And then maybe for now, we can model and guess based on the traffic
volume modeled at the main street next door, how much traffic goes onto the side streets." And: "if SFMTA measures a
certain traffic volume on one street, also assume the next block of the same street will have at least similar volume
conservatively (i.e. see how many households/cars on that street, and assume as many people drop off and go to their
homes as possible, but that will leave still a bunch of cars to go to the next street)."
Then, same day: "Traffic stress layer should also include measured or modeled main streets from the big models that
model main street traffic", and "higher gradations of traffic beyond 6 a minute".
Prior work: research/notes/whitepaper-2026-11/part-1/2026-11-18-cut-through-prior-work.md.

The Street Safety map (sf-works.org/transportation/street-safety) reads its blocks.json through
tools/street-safety/street-safety-map.py, which is rebuilt by hand (MANUAL in pipeline/transportation-update.py) until the crash
extract it also reads has an updater. Its Telraam input refreshes weekly (step "telraam"); its other inputs are fixed
files or cached reads.

INPUTS
  blocks    DataSF 3psu-pn9h active centerlines (the query tools/street-safety/hin-injury-kinds.py makes). A residential block is
            classcode 5 on a STREETS* layer: park roads (PARKS*), PRIVATE, PAPER, PSEUDO and FREEWAYS are left out.
  counts    SFMTA Corridor Counts CSV (sfmta.com/media/40635; sources/sfmta-corridor-counts.md), at COUNTS (scratch,
            not tracked). One row = one direction, one block, one day. VOLUME_ADT is that day's 24-hour count.
            VOLUME_AM_PEAK / VOLUME_PM_PEAK are filled on 2014 to 2019 rows only.
  slow      data/slow-streets/evaluations.csv: SFMTA's 2023 Slow Streets evaluation, weekday daily vehicles per count
            segment. Matched to a block by street and its two cross streets.
  telraam   data/extract/telraam/segments.json from tools/street-safety/telraam-sf.py: residents' Telraam window counters, the
            median Tue to Thu peak hour, April to September where it has one, in the 12 months to the read date (sources/telraam.md).
  champ     SFCTA SF-CHAMP hwynet_weekday DAILY link volumes (v_1, both directions added) on hwy_base2020 links, from
            api.sfcta.org (sources/sfcta-champ-hwynet.md): an undated run of mid-2019 or earlier. Cached in RUNS.
  housing   data/extract/census-blocks/2020.json and outlines-2020.json: 2020 Census housing units per census block.
  vehicles  ACS 2020-24 5-year B25044 (vehicles available) by tract, from api.censusreporter.org, cached in RUNS.
  people    scratch/runs/hin-injuries/points.geojson from tools/street-safety/hin-injury-kinds.py: people severely injured or
            killed, 2022 to 2024.

RULES
  Peak hour. Two-way vehicles in the busier of the morning and evening peak hours on a midweek day (Tue to Thu; Mon and
  Fri only where no midweek day was counted). Where a count row carries AM and PM peak volumes, the day's peak is the
  larger of its two-way AM and two-way PM sums. SFMTA's legend labels these "AM PEAK(7-9AM)" and "PM PEAK(4-7PM)"
  without saying hour or period. Their median share of the 24-hour count on residential rows is about 9%, which fits a
  single hour and not a two- or three-hour total, so they are read as the peak hour inside that window [inference].
  Every other volume is turned into a peak hour with K, the median two-way peak-hour share of the 24-hour count over
  residential count-days that carry both, computed here.
  Count dates. Some batches of the CSV carry the wrong YEAR (160 rows labelled February 2020 fall on February
  2021's weekdays); count_years() rebuilds the year from the weekday, day and month, and drops rows it cannot date.
  The pandemic test below reads the rebuilt year.
  Count-day errors. A peak share under 3% means the 24-hour figure is wrong (SFMTA's September 2014 Bay Metrics batch
  runs about 5 times high), so that day keeps its peak hour and its daily becomes peak / K. A share over 25% keeps the
  24-hour figure and its peak becomes daily x K. A day with a zero in any direction is a failed count and is dropped.
  Matching a count to a block. The CSV's CNN is used only when the centerline's street name matches PRIMARY_STREET.
  Otherwise, and where CNN is blank, the row goes to every block with that street and both cross streets.
  Counted. The block's latest count year outside March 2020 to December 2021 (the pandemic years, used only when a
  block has nothing else). Within it, the day figures are averaged, unless they read DISAGREE-fold apart: then the
  block has no count and its row carries the counts_disagree caveat (caveats()). A two-way block counted in one direction only takes
  the opposite direction from the next block of the same street counted the same day, where one exists ("paired"),
  and is doubled otherwise. A 2023 Slow Streets figure replaces an older count.
  Telraam. A segment joins the nearest block within MATCH_FT of its midpoint and within ANGLE degrees of parallel. Its
  peak hour is counted, the April to September median where the segment has one (its winter evenings are counted by
  headlights and read high); its day is the peak over the camera's own peak share where it counts all 24 hours, else over
  the block's own SFMTA share, else K (K main on main streets). A counter that sees one direction only is left out
  unless the block is a one-way street with no carriageway beside it (sees_one_side()). Where the block also has an
  SFMTA figure, COUNT_RULE (choose_count) picks the one the block uses: the counter's when it passes the override gate
  (overrides(): OVERRIDE_MIN_DAYS valid April to September days in the extract's window), else SFMTA's. The other stays on the row (tel_* or sfmta_* columns). A 2023 Slow
  Streets figure is a day count, so it is compared with the counter day against day. Telraam joins after K and the
  SF-CHAMP scales are fitted, so those rest on SFMTA's counts alone; carrying and the validations below use the chosen
  count like any count.
  Modelled. SF-CHAMP link within MATCH_FT of the block's midpoint, within ANGLE degrees of parallel, with the same
  street name. The model ran high against the counts on the residential blocks with both, so its daily volume is
  scaled by their median count/model ratio, computed here. A block the model codes as a major road (MAJOR_FT), and any
  block named RAMP or TUNL, is a main street's block and leaves the residential layer.
  Carried. From each counted block, walk the same street block by block through shared centerline nodes. Each next
  block keeps peak = previous peak minus the most peak-hour trips that could end on it, taken generously as every
  vehicle its homes own arriving in that hour: housing units fronting the block x the tract's vehicles per household
  (ACS B25044). The walk stops at a node any main street (classcode 1 to 4) touches, at a dead end, at another counted
  block, and when the value falls under 90. Where walks meet, the larger value stands. It is a floor only if no car
  turns off at a corner, which the validation in the summary tests on pairs of counted blocks.
  Estimated. A block with none of the above: SPILL share of the nearest parallel main block (classcode 2 to 4) within
  PAR_FT, whose own volume is counted or modelled. On SF's own counts this guess has almost no skill (summary
  "calibration"), so it is reported apart and never names a street.
  Order. counted > modelled > carried > estimated.
  Classes (peak-hour vehicles, two-way): under 90, then doubling: 90 (1.5 a minute), 180, 360, 720, 1,440, 2,880 and up.
  Main streets. Classcode 2 to 4 on a STREETS or PARKS layer, plus the residential-class blocks found to be a main
  street's, ramps and tunnels left out. Counted first (peak share KM, from main-street count-days of the same
  classcode, since a main street's day is flatter), then SF-CHAMP: every same-named parallel link beside the block
  within DUAL_FT summed (beside(): the links the block's midpoint projects inside, never the link before or after it
  along the street), so a divided road or a pair of one-direction links gives both directions. A divided road is
  two one-way centerlines of the same street side by side whose traffic runs opposite ways, paired by geometry
  (carriageways()), and both halves take the pair's two-way figure (two counts summed, one doubled). Card caveats
  (caveats()) mark a main-street Telraam figure, a winter-only counter and a block whose counts disagree. The model is scaled per band of its own volume (MAIN_BANDS) by the median count/model
  ratio on main blocks with a 2014 to 2019 count, because the ratio falls as volume rises; it is applied as one curve
  fitted on logs (Theil-Sen), with the band medians kept as its check. SFMTA's
  SF-CHAMP 2019 Base run (DTX_URL, links of 5,001 a day and up) is compared link by link as a vintage check only.
  Residents. Housing units fronting each block x RES_RATE peak-hour trips per unit. Peak minus that is the remainder
  not from the block's own homes, an inference that still counts neighbours from the next blocks along.
  People. A person counts toward the residential street network when hin-injury-kinds.py placed them on a residential
  street (midblock, or a corner of residential streets). They count toward the busiest residential block within
  NEAR_FT that has a figure, by the order above, so a corner person goes to the busier leg. A person placed on a main
  street counts on the busiest main block within NEAR_FT, measured or modelled.

OUTPUTS
  data/extract/residential-traffic/blocks.json   one row per block: cnn, road (res or main), kind (measured, modelled,
                                                 carried, estimated, none), class, peak, daily, source, year, low, high.
  out/hin-cut-through/summary.json               class counts, miles and people by kind, coverage, K, checks.

Checks (stop on failure): >= 8,000 count rows, >= 9,000 residential blocks, >= 1,000 residential count-days with peak
columns, K between 0.06 and 0.14, CHAMP >= 8,000 links with geometry, >= 50 blocks with both a count and SF-CHAMP,
ACS tracts >= 200, one output row per residential block, people file 922 rows, >= 40 count-days per main classcode,
>= 150 main blocks with a pre-2020 count and SF-CHAMP, >= 15 pairs per model-volume band, >= 4,000 SF-CHAMP 2019 Base links, no main block summing two SF-CHAMP links that
lie end to end along it (in_series()).
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import csv
import datetime as dt
import json
import math
import statistics
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402
from lib.stable import write_text  # noqa: E402

# Downloads and caches too big to track live in the gitignored scratch/ folder, or wherever $SF_WORKS_SCRATCH names.
# Nothing is read from it when this module is imported (street-safety-map.py imports it for its rules); a step that
# needs a file there opens it, and stops naming the file when it is missing.
SCR = Path(os.environ.get("SF_WORKS_SCRATCH") or ROOT / "scratch")
COUNTS = SCR / "runs/citywide-speed/sfmta-corridor-counts.csv"
RUNS = SCR / "runs/hin-cut-through"
POINTS = SCR / "runs/hin-injuries/points.geojson"
SLOW = ROOT / "data/slow-streets/evaluations.csv"
HU = ROOT / "data/extract/census-blocks/2020.json"
OUTLINES = ROOT / "data/extract/census-blocks/outlines-2020.json"
TELRAAM = ROOT / "data/extract/telraam/segments.json"       # from tools/street-safety/telraam-sf.py
OUT_BLOCKS = ROOT / "data/extract/residential-traffic/blocks.json"
OUT_SUM = ROOT / "out/hin-cut-through/summary.json"
CHAMP_API = "https://api.sfcta.org/api/"
DTX_URL = ("https://services.sfmta.com/arcgis/rest/services/Multimodal/modal_planning_framework/MapServer/1/query"
           "?where=1%3D1&outFields=A,B,DAILY_TOT&returnGeometry=false&f=json&resultRecordCount=2000&resultOffset=")
ACS_URL = "https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B25044&geo_ids=140|05000US06075"

# Bryan, 2026-11-18: 1.5, 3 and 6 cars a minute, then "higher gradations of traffic beyond 6 a minute": each step doubles.
CLASSES = [(0, 90, "under 1.5 a minute"), (90, 180, "1.5 to 3 a minute"), (180, 360, "3 to 6 a minute"),
           (360, 720, "6 to 12 a minute"), (720, 1440, "12 to 24 a minute"), (1440, 2880, "24 to 48 a minute"),
           (2880, 10 ** 9, "48 or more a minute")]
KINDS = ("measured", "modelled", "carried", "estimated")
MATCH_FT, ANGLE, PAR_FT, NEAR_FT, CELL = 60, 20, 660, 60, 500
OPPOSED = 30     # degrees off antiparallel that two one-way halves of a divided road may run
DISAGREE = 3     # count-days on one block this many times apart are not averaged (measured())
DUAL_FT = 150    # a divided road's other carriageway, or the other one-direction link of a two-way street, lies within this
# SF-CHAMP over the counts on main streets is not flat: it overstates small mains and understates big ones, so the
# count/model scale is fitted per band of the model's own daily volume.
MAIN_BANDS = [(0, 5000), (5000, 10000), (10000, 20000), (20000, 10 ** 9)]
# Spillover share of the parallel main street's daily volume. No study publishes this ratio. The bounds come from London
# LTN counts in the prior-work note: Hackney's Elsdale Street carried 13.5% of parallel Morning Lane before filtering, and
# the traffic filtering removed was 9% of it (central). Lambeth's Railton Road carried about 28% of boundary Effra Road
# (high). Low is a judgement for an ordinary block, since every measured ratio is from a known rat run.
SPILL = {"low": 0.03, "central": 0.10, "high": 0.25}
SPILL_SOURCE = "London LTN counts (Hackney Elsdale Street, Lambeth Railton Road), prior-work note 2026-11-18"
# SF-CHAMP facility types read as a major road. ft meanings are not in the API. These follow SF-CHAMP's usual coding (2
# freeway, 3 expressway, 5 ramp, 7 major arterial, 12 minor arterial, 15 super arterial) [model knowledge — verify].
MAJOR_FT = {1, 2, 3, 5, 7, 12, 15}
PEAK_SHARE_OK = (0.03, 0.25)
RES_RATE = {"low": 0.2, "central": 0.35, "high": 0.5}   # residents' peak-hour car trips per housing unit
RES_SOURCE = "stated assumption [model knowledge — verify]"
MIDWEEK = {"TUESDAY", "WEDNESDAY", "THURSDAY"}
WEEKDAY = MIDWEEK | {"MONDAY", "FRIDAY"}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}

FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
SUFFIX = {"ST", "AVE", "AV", "BLVD", "DR", "WAY", "WY", "TER", "TERR", "CT", "PL", "LN", "RD", "HWY", "CIR", "CR",
          "ALY", "PLZ", "EXPY", "STWY", "WALK", "PARK", "ROW", "LOOP", "HL", "STREET", "AVENUE", "N", "S", "E", "W",
          "NB", "SB", "EB", "WB"}
ALIAS = {"SAINT": "ST", "MOUNT": "MT",
         "HAMPHIRE": "HAMPSHIRE"}   # SFMTA's counts file spells Hampshire St this way on its 2017 rows


def check(ok, msg):
    if not ok:
        sys.exit("CHECK FAILED: " + msg)
    print("ok  " + msg, file=sys.stderr)


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


def base(name):
    """Street name without its trailing type, leading zeros or punctuation: '02ND AVE' -> '2ND', 'SAINT FRANCIS
    BLVD' -> 'ST FRANCIS'."""
    t = [ALIAS.get(w, w) for w in (name or "").upper().replace(".", " ").replace(",", " ").split()]
    t = [w.lstrip("0") or "0" if w[:1].isdigit() else w for w in t]
    while len(t) > 1 and t[-1] in SUFFIX:
        t.pop()
    return " ".join(t)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def length(P):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(P, P[1:]))


def bearing(P):
    (x0, y0), (x1, y1) = P[0], P[-1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180


def parallel(b1, b2):
    d = abs(b1 - b2) % 180
    return min(d, 180 - d) <= ANGLE


def midpoint(P):
    half, run = length(P) / 2, 0.0
    for a, b in zip(P, P[1:]):
        s = math.hypot(b[0] - a[0], b[1] - a[1])
        if run + s >= half and s > 0:
            t = (half - run) / s
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        run += s
    return P[-1]


class Grid(object):
    """Polylines in feet, bucketed on a CELL grid."""

    def __init__(self, items):
        self.items, self.g = items, collections.defaultdict(set)
        for k, (P, _) in enumerate(items):
            for a, b in zip(P, P[1:]):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.g[(cx, cy)].add(k)

    def near(self, p, reach):
        r = int(reach // CELL) + 1
        cx, cy, out = int(p[0] // CELL), int(p[1] // CELL), {}
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for k in self.g.get((cx + dx, cy + dy), ()):
                    P = self.items[k][0]
                    d = min(seg_dist(p, a, b) for a, b in zip(P, P[1:]))
                    if d <= reach:
                        out[k] = d
        return [(d, self.items[k][1]) for k, d in sorted(out.items(), key=lambda kv: (kv[1], kv[0]))]


def cls_of(peak):
    for i, (lo, hi, _) in enumerate(CLASSES):
        if lo <= peak < hi:
            return i
    return len(CLASSES) - 1


def num(s):
    try:
        v = float(str(s).replace(",", "").strip())
    except ValueError:
        return None
    return v if v > 0 else None


def is_zero(s):
    try:
        return float(str(s).replace(",", "").strip()) == 0
    except ValueError:
        return False


def fold_dir(d):
    d = (d or "").strip().upper()
    return d[:1] if d[:1] and d[:1] in "NSEW" else None


def pandemic(key):
    return (key[0] == 2020 and key[1] >= 3) or key[0] == 2021


def read_blocks():
    C = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                     where="active='true'", floor=15000)
    blocks, nodes = {}, collections.defaultdict(set)
    for r in C.rows:
        layer = r.get("layer") or ""
        if not r.get("line") or layer.startswith(("FREEWAYS", "PAPER", "PSEUDO")):
            continue
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        P = [xy(*p) for ln in lines for p in ln]
        if len(P) < 2:
            continue
        cnn = str(int(float(r["cnn"])))
        cls = r.get("classcode") or "0"
        name = (r.get("streetname") or "").strip()
        ends = [str(int(float(n))) for n in (r.get("f_node_cnn"), r.get("t_node_cnn")) if n]
        blocks[cnn] = {"cnn": cnn, "P": P, "len": length(P), "brg": bearing(P), "mid": midpoint(P),
                       "street": base(name), "f": base(r.get("f_st")), "t": base(r.get("t_st")), "cls": cls,
                       "res": cls == "5" and layer.startswith("STREETS"), "oneway": r.get("oneway") or "B",
                       "name": name, "fname": (r.get("f_st") or "").strip(), "tname": (r.get("t_st") or "").strip(),
                       "nodes": ends, "layer": layer, "rampish": any(w in name.upper().split() for w in ("RAMP", "TUNL"))}
        for n in ends:
            nodes[n].add(cnn)
    return blocks, nodes, C.tag


def place_index(blocks):
    by_place = collections.defaultdict(set)
    for b in blocks.values():
        by_place[(b["street"], frozenset((b["f"], b["t"])))].add(b["cnn"])
    return by_place


WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
# Rows in a batch with no row on its labelled year's calendar, whose weekdays agree on no other year within two, by
# labelled (year, month): read off the 2026-11 copy of the CSV (count_years). They are dropped; a new one fails the run.
# The four are Congdon St, Trumbull to Ney, "16 WEDNESDAY" and "17 THURSDAY" January 2022, which no year within two,
# and no shift by January 2022's DATE slip of ten days, puts on its weekday.
UNDATED_KNOWN = {(2022, 1): 4}


def count_years(rows):
    """Row index -> the year the row's weekday, day and month fit, or None when it fits none.

    SFMTA's CSV carries YEAR, MONTH, DAY_OF_MONTH and DAY_OF_WEEK, and in some batches YEAR is wrong: 160 rows
    labelled February 2020 fall on February 2021's weekdays (Lake St, 6th to 7th Ave, "2020-02-03 WEDNESDAY", when 3
    February 2020 was a Monday), and 48 labelled December 2020 fall on December 2019's. A batch is one street, its two
    cross streets, and a labelled year and month. A row whose weekday fits its labelled year keeps it. In a batch where
    some rows fit, a row that doesn't is a weekday slip (Taylor St's February 2016 count lists 23 February as both a
    Tuesday and a Wednesday) and is dropped. In a batch where no row fits, the year is the nearest one, within two, whose calendar puts
    each row's weekday on its day, when every row agrees on it; failing that the rows have no year and are dropped.
    A full m/d/yyyy `DATE` that falls on the row's weekday wins over YEAR, MONTH and DAY_OF_MONTH: 24th Ave, Cabrillo
    to Fulton, carries DATE 1/5/2022 (a Wednesday) beside DAY_OF_MONTH 15. A full DATE that agrees with YEAR, MONTH
    and DAY_OF_MONTH wins over the weekday, three fields to one (Carroll Ave, 3rd St to the Caltrain tracks, DATE
    4/6/2022 "TUESDAY"). A day-only DATE that falls on the weekday wins over a DAY_OF_MONTH that doesn't (17th St, Ord
    to Temple, DATE 16 beside DAY_OF_MONTH 1, "TUESDAY", November 2021). A row that copies a fully dated row takes that
    row's date. A batch no row of which fits first tries its month's DATE slip (below), then a year move.
    Returns row index -> (year, month, day) and a tally of what was done."""
    def on(y, m, d, w):
        try:
            return WEEKDAYS[dt.date(y, m, d).weekday()] == w
        except ValueError:
            return False
    batch = collections.defaultdict(list)
    parsed, dated, odd, full_dated = {}, {}, collections.Counter(), set()   # full_dated: a full DATE on the weekday
    slips = collections.defaultdict(collections.Counter)   # (year, month) -> DAY_OF_MONTH minus its full DATE's day
    for i, r in enumerate(rows):
        y, m, d, w = r["YEAR"].strip(), (r["MONTH"] or "").strip(), (r["DAY_OF_MONTH"] or "").strip(), r["DAY_OF_WEEK"].strip().upper()
        if w and w not in WEEKDAYS:
            odd[w] += 1
        full = (r.get("DATE") or "").strip().split("/")
        if len(full) == 3 and all(x.isdigit() for x in full) and len(full[2]) == 4 and w in WEEKDAYS:
            try:
                fd = dt.date(int(full[2]), int(full[0]), int(full[1]))
            except ValueError:
                fd = None
            if fd and WEEKDAYS[fd.weekday()] == w and (not y.isdigit() or abs(fd.year - int(y)) <= 2):
                dated[i] = (fd.year, fd.month, fd.day)
                full_dated.add(i)
                if (str(fd.year), str(fd.month), str(fd.day)) != (y, m, d):
                    odd["full DATE used over YEAR, MONTH, DAY_OF_MONTH"] += 1
                    if (str(fd.year), str(fd.month)) == (y, m) and d.isdigit():
                        slips[(fd.year, fd.month)][int(d) - fd.day] += 1
            elif fd and (str(fd.year), str(fd.month), str(fd.day)) == (y, m, d):
                dated[i] = (fd.year, fd.month, fd.day)   # DATE, YEAR, MONTH and DAY_OF_MONTH agree; only the weekday is off
                odd["full DATE and labels agree, weekday off"] += 1
        elif full[0].isdigit() and len(full) == 1 and full[0] != d and y.isdigit() and m.isdigit() and d.isdigit() \
                and w in WEEKDAYS and on(int(y), int(m), int(full[0]), w) and not on(int(y), int(m), int(d), w):
            dated[i] = (int(y), int(m), int(full[0]))   # a day-only DATE that falls on the weekday, beside a day that doesn't
            odd["full day-only DATE used over DAY_OF_MONTH"] += 1
        if not (y.isdigit() and m.isdigit() and d.isdigit() and w in WEEKDAYS):
            continue
        parsed[i] = (int(y), int(m), int(d), w)
        batch[(r["PRIMARY_STREET"].strip().upper(), r["CROSS_STREET_1"].strip().upper(), r["CROSS_ST_2"].strip().upper(),
               int(y), int(m))].append(i)
    # A row that repeats a fully dated row (same street, cross streets, direction, 24-hour volume and weekday) is a copy
    # of that count and takes its date: 14th St, Castro to Divisadero, lists 6 and 7 November 2019 again as 16 and 17
    # November 2020, and Baker St, Oak to Fell, lists 5 February 2020 again as 5 January 2020.
    twin_key = lambda r: (base(r["PRIMARY_STREET"]), frozenset((base(r["CROSS_STREET_1"]), base(r["CROSS_ST_2"]))),  # noqa: E731
                          fold_dir(r["DIRECTION"]), (r["VOLUME_ADT"] or "").strip(), r["DAY_OF_WEEK"].strip().upper())
    twins, copied = collections.defaultdict(set), 0
    for i, ymd in dated.items():
        if i in full_dated and num(rows[i]["VOLUME_ADT"]):
            twins[twin_key(rows[i])].add(ymd)
    for i in parsed:
        if i not in dated and num(rows[i]["VOLUME_ADT"]) and len(twins.get(twin_key(rows[i]), ())) == 1 \
                and not on(*parsed[i]):   # a row whose own labels fall on its weekday keeps them
            dated[i] = next(iter(twins[twin_key(rows[i])]))
            if dated[i] != parsed[i][:3]:
                copied += 1

    def fits(y, m, d, w):
        for yy in sorted(range(y - 2, y + 3), key=lambda v: (abs(v - y), v)):
            try:
                if WEEKDAYS[dt.date(yy, m, d).weekday()] == w:
                    return yy
            except ValueError:
                continue
        return None
    years, tally, undated = {}, collections.Counter(), collections.Counter()
    for k, idx in batch.items():
        # A row dated by its full DATE in the labelled year and month counts as one that fits.
        good_days = {parsed[i][2] for i in idx if fits(*parsed[i]) == parsed[i][0] or dated.get(i, (0, 0))[:2] == k[3:5]}
        dated_days = {dated[i][2] for i in idx if dated.get(i, (0, 0))[:2] == k[3:5]}
        moves = {}
        for i in idx:
            if i in dated:
                continue
            y, m, d, w = parsed[i]
            f_ = fits(y, m, d, w)
            if f_ == y:
                years[i] = (y, m, d)
            elif d in dated_days:
                years[i] = (y, m, d)   # same day as a row its DATE dates: Middle Point Rd's 22 June 2022, DATE 6/23/2033
                tally["day of a dated row in its batch"] += 1
            elif good_days:
                tally["weekday slip, dropped"] += 1
            else:
                moves[i] = f_
        # Before moving the year, try the labelled month with DAY_OF_MONTH shifted by a slip the month's full DATEs show:
        # in January 2022, 24th Ave's DATE 1/5/2022 sits beside DAY_OF_MONTH 15, and 19th St's 14 and 15 January,
        # a Tuesday and Wednesday, are 4 and 5 January 2022.
        slip = next((sl for sl, _ in sorted(slips[k[3:5]].items(), key=lambda kv: (-kv[1], abs(kv[0]), kv[0]))
                     if moves and all(on(k[3], k[4], parsed[i][2] - sl, parsed[i][3]) for i in moves)), None)
        if slip is not None:
            for i in moves:
                years[i] = (k[3], k[4], parsed[i][2] - slip)
                tally["day shifted by the month's DATE slip: %d-%02d" % k[3:5]] += 1
            moves = {}
        to = set(moves.values())
        for i in moves:
            if len(to) == 1 and None not in to:
                years[i] = (next(iter(to)), parsed[i][1], parsed[i][2])
                tally["year from weekday: %d labelled %d-%02d" % (years[i][0], k[3], k[4])] += 1
            else:
                undated[(k[3], k[4])] += 1
    years.update(dated)
    for i, r in enumerate(rows):
        if i not in parsed and i not in dated and r["YEAR"].strip().isdigit() and not r["DAY_OF_WEEK"].strip():
            day = (r["DAY_OF_MONTH"] or "").strip()   # no weekday to test: the label stands
            years[i] = (int(r["YEAR"]), int(r["MONTH"] or 0), int(day) if day.isdigit() else 0)
    check(not [w for w in odd if not w.startswith("full")],
          "every DAY_OF_WEEK is a full weekday name or blank (%s)" % ", ".join(sorted(w for w in odd if not w.startswith("full"))))
    tally.update({k: v for k, v in odd.items() if k.startswith("full")})
    tally["date from a fully dated copy of the row"] = copied
    check(all(n <= UNDATED_KNOWN.get(k, 0) for k, n in undated.items()),
          "SFMTA rows with no year their weekday fits are among the known %d (%s)"
          % (sum(UNDATED_KNOWN.values()), ", ".join("%d-%02d: %d" % (y, m, n) for (y, m), n in sorted(undated.items()))))
    tally["no year fits, dropped"] = sum(undated.values())
    return years, tally


def read_counts(blocks):
    rows = list(csv.DictReader(open(COUNTS, encoding="latin-1")))
    check(len(rows) >= 8000, "corridor count file has >= 8,000 rows (%d)" % len(rows))
    years, date_fix = count_years(rows)
    place = lambda r: (base(r["PRIMARY_STREET"]), frozenset((base(r["CROSS_STREET_1"]), base(r["CROSS_ST_2"]))))  # noqa: E731
    by_place = place_index(blocks)
    days = collections.defaultdict(lambda: collections.defaultdict(dict))  # cnn -> (y, m, d) -> dir -> (adt, am, pm, dow)
    failed = collections.defaultdict(set)
    stats = collections.Counter()
    for i, r in enumerate(rows):
        d = fold_dir(r["DIRECTION"])
        v, zero = num(r["VOLUME_ADT"]), is_zero(r["VOLUME_ADT"])
        if d is None or i not in years or (v is None and not zero):
            continue
        street = base(r["PRIMARY_STREET"])
        cnns = set()
        if r["CNN"].strip():
            c = str(int(float(r["CNN"])))
            if c in blocks and blocks[c]["street"] == street:
                cnns = {c}
            else:
                stats["csv_cnn_other_street_or_inactive"] += 1
        if not cnns:
            cnns = set(by_place.get(place(r), ()))
            stats["placed_by_street_and_cross_streets" if cnns else "unplaced"] += 1
        day = (r["DAY_OF_MONTH"] or "").strip()
        key = years[i]
        for cnn in cnns:
            if zero:
                failed[cnn].add(key)
                continue
            prev = days[cnn][key].get(d)
            if prev and max(prev[0], v) >= DISAGREE * min(prev[0], v):
                # two rows for one block, day and direction DISAGREE-fold apart (two count sites placed on one block, as
                # on Roosevelt Way, Levant to Masonic, 15 July 2020: 773 and 2,400 eastbound): the day is unusable
                failed[cnn].add(key)
                days[cnn][key].pop(d)   # nor does the earlier row feed K
                stats["same_day_direction_rows_disagree"] += 1
                continue
            days[cnn][key][d] = (v, num(r["VOLUME_AM_PEAK"]), num(r["VOLUME_PM_PEAK"]), r["DAY_OF_WEEK"].strip().upper())
            stats["row_block_pairs"] += 1
    stats["failed_count_days"] = sum(len(v) for v in failed.values())
    return days, failed, stats, len(rows), date_fix


def k_factor(days, blocks, pick=lambda b: b["res"], floor=1000, what="residential"):
    """Median two-way peak-hour share of the 24-hour count on midweek count-days carrying both, over blocks `pick` keeps."""
    shares = []
    for cnn, dd in days.items():
        if not pick(blocks[cnn]):
            continue
        for key, dirs in dd.items():
            if not dirs or not all(x[1] and x[2] for x in dirs.values()) or next(iter(dirs.values()))[3] not in MIDWEEK:
                continue
            adt = sum(x[0] for x in dirs.values())
            if adt < 100:
                continue
            sh = max(sum(x[1] for x in dirs.values()), sum(x[2] for x in dirs.values())) / adt
            if PEAK_SHARE_OK[0] <= sh <= PEAK_SHARE_OK[1]:
                shares.append(sh)
    check(len(shares) >= floor, "%s midweek count-days with peak columns >= %d (%d)" % (what, floor, len(shares)))
    K = statistics.median(shares)
    q = statistics.quantiles(shares, n=4)
    check(0.06 <= K <= 0.14, "%s peak-hour share K within 0.06 to 0.14 (%.4f)" % (what, K))
    return K, {"k": round(K, 4), "p25": round(q[0], 4), "p75": round(q[2], 4), "count_days": len(shares)}


def day_figure(dirs, K):
    """(daily, peak, how) for one count-day's directions."""
    adt = sum(x[0] for x in dirs.values())
    if all(x[1] and x[2] for x in dirs.values()):
        pk = max(sum(x[1] for x in dirs.values()), sum(x[2] for x in dirs.values()))
        sh = pk / adt
        if sh < PEAK_SHARE_OK[0]:
            return pk / K, pk, "own peak hour, 24-hour figure rejected"
        if sh > PEAK_SHARE_OK[1]:
            return adt, adt * K, "24-hour count x K"
        return adt, pk, "own peak hour"
    return adt, adt * K, "24-hour count x K"


def measured(days, failed, blocks, nodes, Kof):
    """cnn -> counted figure from the block's latest usable count year, and cnn -> the count-days and day figures of
    a block whose days in that year disagree DISAGREE-fold, which gets no count. Kof(cnn) is the block's peak-hour
    share."""
    raw, disagree = {}, {}
    for cnn, dd in days.items():
        valid = [k for k in dd if k not in failed[cnn]]
        pool = [k for k in valid if not pandemic(k)] or valid
        if not pool:
            continue
        year = max(k[0] for k in pool)
        keys = [k for k in pool if k[0] == year]
        dow = lambda k: next(iter(dd[k].values()))[3]  # noqa: E731
        wk = [k for k in keys if dow(k) in MIDWEEK] or [k for k in keys if dow(k) in WEEKDAY or not dow(k)]
        if not wk:
            continue
        ndir = max(len(dd[k]) for k in wk)
        wk = sorted(k for k in wk if len(dd[k]) == ndir)
        figs = [day_figure(dd[k], Kof(cnn)) for k in wk]
        if min(f[0] for f in figs) > 0 and max(f[0] for f in figs) >= DISAGREE * min(f[0] for f in figs):
            # Count-days DISAGREE-fold apart are not averaged, and no one of them can be chosen: 14th St, Castro to
            # Divisadero, counted about 1,200 a day on 6 and 7 November 2019 and 6,600 on 11 and 12 December, and
            # Octavia St's central roadway, Oak to Fell, 23,216 northbound on 3 February 2015 and 876 on 7 July, a
            # local lane's figure. The block gets no count, and its row says why (caveats()).
            disagree[cnn] = [(k, round(f[0])) for k, f in zip(wk, figs)]
            continue
        hows = sorted({f[2] for f in figs})
        raw[cnn] = {"daily": statistics.mean(f[0] for f in figs), "peak": statistics.mean(f[1] for f in figs), "year": year,
                    "keys": set(wk), "dirs": set(next(iter(dd[k] for k in wk))), "n_days": len(wk), "how": "; ".join(hows),
                    "pandemic": all(pandemic(k) for k in wk)}
    out = {}
    for cnn, m in raw.items():
        m = dict(m)
        m["note"] = ""
        if len(m["dirs"]) == 1 and blocks[cnn]["oneway"] == "B":
            d = next(iter(m["dirs"]))
            mate = None
            for n in blocks[cnn]["nodes"]:
                for o in sorted(nodes[n]):
                    r2 = raw.get(o)
                    if o != cnn and r2 and blocks[o]["street"] == blocks[cnn]["street"] and r2["dirs"] == {OPP[d]} \
                            and r2["keys"] & m["keys"]:
                        mate = o
                        break
                if mate:
                    break
            if mate:
                m["daily"] += raw[mate]["daily"]
                m["peak"] += raw[mate]["peak"]
                m["note"] = "other direction from the next block, same days"
            else:
                m["daily"] *= 2
                m["peak"] *= 2
                m["note"] = "one direction counted, doubled"
        out[cnn] = m
    return out, disagree


def travel(b):
    """Bearing a one-way block's traffic runs, 0 to 360. The centerline runs from its from node to its to node, and
    oneway F is traffic from-to, T to-from."""
    (x0, y0), (x1, y1) = b["P"][0], b["P"][-1]
    a = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360
    return a if b["oneway"] == "F" else (a + 180) % 360


def opposed(a, b):
    """Two one-way blocks carry traffic in opposite directions, within OPPOSED degrees. Wider than ANGLE because the
    halves of a divided road flare apart at its ends: Van Ness Ave's two blocks from Austin to Pine meet at Pine 160
    degrees apart, Richardson Ave's at Chestnut 156."""
    d = abs(travel(a) - travel(b)) % 360
    return min(d, 360 - d) >= 180 - OPPOSED


def carriageways(mains):
    """cnn -> the other carriageway(s) of a divided road beside it: one-way (F or T) blocks of the same street whose
    traffic runs the opposite way, within ANGLE degrees, with one's midpoint within DUAL_FT of the other and projecting
    inside it (so never the next block along), plus the opposed pairs that name the same cross streets. Paired by
    geometry first, because the halves of a divided road often name different ones: Monterey Blvd's 9284201 runs
    Plymouth to Yerba Buena beside 9284101, Plymouth to Plymouth, and Market St's 8750201 runs Taylor to McAllister
    beside 8750101, Taylor to 7th. Two one-way blocks that run the same way are never a pair: Octavia Blvd's local lanes
    beside its central roadway, the Oak and Fell slip lanes at Stanyan, Geary's Fillmore underpass beside its surface
    lanes, and Junipero Serra's frontage roads each carry part of one direction, so pairing them and doubling a count
    double-counts that direction. The same test keeps Beale St's centerline drawn twice (2864000 beside 2864001,
    both northbound) from pairing with itself; 13th St's two lines from Bryant to Harrison, drawn on one line but
    one each way, still pair, since each carries one direction of one roadway."""
    ow = {c: b for c, b in mains.items() if b["oneway"] in ("F", "T")}
    G = Grid([(b["P"], c) for c, b in sorted(ow.items(), key=lambda kv: int(kv[0]))])
    mates = collections.defaultdict(set)
    pair = lambda a, b: a["street"] == b["street"] and opposed(a, b)  # noqa: E731
    for c in sorted(ow, key=int):
        b = ow[c]
        for d, o in G.near(b["mid"], DUAL_FT):
            if o != c and pair(ow[o], b) and parallel(ow[o]["brg"], b["brg"]) and interior(b["mid"], ow[o]["P"], DUAL_FT):
                mates[c].add(o)
                mates[o].add(c)
    # A pair the projection test misses (a midpoint at a bend, as on 3rd St, 22nd to 23rd) still pairs when the two
    # halves name the same cross streets, run opposite ways, and are the only one-way blocks that do.
    named = collections.defaultdict(list)
    for c, b in ow.items():
        named[(b["street"], frozenset((base(b["fname"]), base(b["tname"]))))].append(c)
    for cs in named.values():
        if len(cs) == 2 and pair(ow[cs[0]], ow[cs[1]]):
            mates[cs[0]].add(cs[1])
            mates[cs[1]].add(cs[0])
    return dict(mates)


# Which count a block uses when it has both an SFMTA count and a resident's Telraam counter: its colour, every figure
# built on it, and the blocks carried from it. Bryan's answer (Telraam against SFMTA),
# 2026-11-21: "Telraam wins" (docs/decisions/street-safety.md), where the option he chose says a working counter. A
# counter is working when it passes telraam-sf.py's checks, sees both directions of a two-way street (telraam()), and
# passes the override gate (overrides()): OVERRIDE_MIN_DAYS valid April to September days in the extract's window.
# There is no test of how lately it counted: a counter that stopped two or three months ago is still far newer than
# any SFMTA count it replaces. Such a block uses the counter's April to September median and
# keeps SFMTA's count beside it with its year. A counter that fails the gate stays on the row beside SFMTA's count,
# with its days and dates. A counter that fails the checks or sees one side never reaches choose_count (telraam() skips
# it). A block with a counter and no SFMTA count uses the counter either way. This line is the only place the rule is set.
COUNT_RULE = "telraam"
OVERRIDE_MIN_DAYS = 20     # valid April to September days (telraam-sf.py's daylight_days)
# The rule in words, for the Street Safety map's About page (tools/street-safety/street-safety-map.py copies it into map.json) and
# sources/telraam.md, so the code, the page and the source note say the same thing.
COUNT_RULE_TEXT = {
    "sfmta": "Where a block has both, we colour it by SFMTA's count and its card gives the Telraam figure beside it, "
             "except where SFMTA's count is from the pandemic (March 2020 to the end of 2021), when the counter colours it.",
    "telraam": "Where a block has both, we colour it by the counter's April to September median when the counter has "
               "%d or more valid days in those months, and its card gives SFMTA's count with its year. Otherwise we "
               "colour it by SFMTA's count and its card gives the counter's figure with its days and dates."
               % OVERRIDE_MIN_DAYS,
}


def overrides(season_days):
    """The override gate: whether a counter's figure replaces SFMTA's count on the same block. `season_days` is its
    valid April to September days in the extract's window."""
    return (season_days or 0) >= OVERRIDE_MIN_DAYS


def choose_count(sfmta, tel, rule=None):
    """Which of a block's counts it uses, "sfmta" or "telraam", under COUNT_RULE. `sfmta` is the block's SFMTA figure
    (a corridor count or the 2023 Slow Streets evaluation) or None, `tel` its Telraam figure from telraam_fig(), whose
    `overrides` is the gate's answer."""
    rule = rule or COUNT_RULE
    if sfmta is None:
        return "telraam"
    if rule == "telraam":
        return "telraam" if tel["overrides"] else "sfmta"
    if rule == "sfmta":
        return "telraam" if sfmta["pandemic"] else "sfmta"
    raise ValueError("unknown COUNT_RULE %r" % rule)


def sees_one_side(s, block, has_mate):
    """A counter telraam-sf.py flagged `one side` (its smaller direction under 2% of its cars) on a block where both
    directions pass: a two-way street, or one carriageway of a divided road, whose figure here is the whole road's. On
    a one-way street with no carriageway beside it one side is all there is (Oak St)."""
    return "one side" in s.get("flags", ()) and not (block["oneway"] in ("F", "T") and not has_mate)


def telraam(blocks, mates=()):
    """Telraam segments from tools/street-safety/telraam-sf.py, each joined to one centerline block: the nearest block within
    MATCH_FT of the segment's midpoint that runs within ANGLE degrees of parallel. `mates` holds the blocks with a
    carriageway beside them (carriageways()). Returns cnn -> segment row, the segments found but not joined, not kept or
    seeing one side of a two-way road, with the reason, and the date the extract was read."""
    T = json.loads(TELRAAM.read_text())
    G = Grid([(b["P"], c) for c, b in sorted(blocks.items(), key=lambda kv: int(kv[0]))])
    out, skipped = {}, []
    for s in T["segments"]:
        if not s["kept"]:
            skipped.append((s["id"], "; ".join(s["fail"])))
            continue
        P = [xy(x, y) for x, y in s["line"]]
        hit = next((c for d, c in G.near(midpoint(P), MATCH_FT) if parallel(blocks[c]["brg"], bearing(P))), None)
        if hit is None:
            skipped.append((s["id"], "no parallel SF block within %d ft" % MATCH_FT))
        elif sees_one_side(s, blocks[hit], hit in mates):
            skipped.append((s["id"], "one side: %.1f%% of its cars go the other way on block %s, which is %s"
                            % (100 * s["side_share"], hit, "one carriageway of a divided road" if hit in mates else "two-way")))
        elif hit in out:   # two counters on one block: the one with more valid days
            if s["valid_days"] > out[hit]["valid_days"]:
                skipped.append((out[hit]["id"], "second counter on block %s" % hit))
                out[hit] = s
            else:
                skipped.append((s["id"], "second counter on block %s" % hit))
        else:
            out[hit] = s
    return out, skipped, T["window"][1]


def own_share(m):
    """A count's own peak-hour share of its day, where it counted both, else None."""
    if m and not m.get("slow") and not m.get("telraam") and m.get("how") == "own peak hour" and m.get("daily"):
        return m["peak"] / m["daily"]
    return None


def telraam_fig(s, Kday):
    """A Telraam segment as a counted figure. Peak hour is measured: the median over April to September
    (`peak_daylight`) where the segment has one, since the camera's `night` count reads about 1.5 times its daylight
    count at 5 and 6 pm, else the all-year median. The day is the peak hour over the segment's own peak share on the
    days its camera counted all 24 hours (telraam-sf.py); a daylight-only camera's day is the peak hour over Kday, the
    block's own SFMTA share where it has one."""
    dl = bool(s.get("peak_daylight"))
    # the share from the same days as the peak: April to September's where the peak is theirs and it has ten full days
    share = s.get("peak_share_daylight") if dl and s.get("peak_share_daylight") else s.get("peak_share")
    full = s.get("full_days", 0) >= 10 and share
    pk, n, first, last = (s["peak_daylight"], s["daylight_days"], s["daylight_first"], s["daylight_last"]) if dl else \
        (s["peak"], s["valid_days"], s["first"], s["last"])
    return {"daily": pk / share if full else pk / Kday, "peak": pk, "year": int(last[:4]), "n_days": n,
            "pandemic": False, "slow": False, "telraam": s["id"], "keys": set(), "dirs": {"both"}, "first": first,
            "last": last, "allday": bool(full), "flags": s.get("flags", []), "peak_daylight": s.get("peak_daylight"),
            "season_days": s.get("daylight_days", 0), "last_valid": s["last"],
            "overrides": overrides(s.get("daylight_days", 0)),
            "how": "Telraam %s, median of %d%s Tue-Thu busiest hours, %s to %s, day %s" % (
                s["id"], n, " April to September" if dl else "", first, last,
                "= peak / its own peak share on %d days counted all 24 hours" % (
                    s["full_days_daylight"] if dl and s.get("peak_share_daylight") else s["full_days"]) if full
                else "= peak / %.3f (daylight-only camera)" % Kday),
            "note": ""}


def tel_fields(m):
    """The two-count columns of an output row: which count it uses, the Telraam counter on the block and SFMTA's
    figure, whichever of them is the row's own."""
    o = m.get("other")
    T = m if m.get("telraam") else o if o and o.get("telraam") else None
    if not T:
        return {}
    S = o if T is m else m
    out = {"count_choice": "telraam" if T is m else "sfmta", "telraam": T["telraam"], "tel_days": T["n_days"],
           "tel_season_days": T["season_days"], "tel_last_valid": T["last_valid"], "tel_overrides": 1 if T["overrides"] else 0,
           "tel_first": T["first"], "tel_last": T["last"], "tel_peak": round(T["peak"]), "tel_daily": round(T["daily"]),
           "tel_allday": 1 if T["allday"] else 0, "tel_flags": ",".join(T["flags"]) or None,
           "tel_peak_daylight": round(T["peak_daylight"]) if T.get("peak_daylight") else None}
    if S:
        out.update(sfmta_peak=round(S["peak"]), sfmta_daily=round(S["daily"]), sfmta_year=S["year"],
                   sfmta_slow=1 if S.get("slow") else 0, sfmta_pandemic=1 if S["pandemic"] else 0)
    return out


def caveats(m, road, split=None):
    """A row's caveats for the map card: `counts_disagree` (SFMTA's count-days on the block read DISAGREE-fold apart,
    so it has no count; their lowest and highest day figures kept as disagree_low and disagree_high), `tel_main` (the
    figure is a Telraam counter's on a main street, where few counters have an SFMTA count to check them against)
    and `tel_winter` (the figure is a counter's with only winter days, whose evening peak may be read in the dark)."""
    out, cav = {}, []
    if split and not m:
        cav.append("counts_disagree")
        out.update(disagree_low=min(v for _, v in split), disagree_high=max(v for _, v in split))
    if m and m.get("telraam") and road == "main":
        cav.append("tel_main")
    other = (m or {}).get("other") or {}
    tel = m if m and m.get("telraam") else other if other.get("telraam") else None
    if tel and "winter only" in tel["flags"]:   # the counter's figure, used or shown beside SFMTA's
        cav.append("tel_winter")
    if cav:
        out["caveat"] = ",".join(cav)
    return out


def slow_streets(blocks, K):
    """2023 Slow Streets segment counts matched to one block by street and both cross streets."""
    by_place = place_index(blocks)
    out, unmatched = {}, []
    for r in csv.DictReader(open(SLOW)):
        if r["scope"] != "segment" or r["period"] != "2023" or r["day_type"] != "weekday" or not num(r["daily_vehicles"]):
            continue
        cn = by_place.get((base(r["hkz3_street"]), frozenset((base(r["segment_from"]), base(r["segment_to"])))), set())
        if not cn:
            unmatched.append("%s %s-%s" % (r["street"], r["segment_from"], r["segment_to"]))
            continue
        v = num(r["daily_vehicles"])
        for cnn in cn:
            out[cnn] = {"daily": v, "peak": v * K, "year": 2023, "n_days": None, "how": "Slow Streets 2023 weekday daily x K",
                        "pandemic": False, "note": "", "slow": True}
    return out, unmatched


def champ_links():
    RUNS.mkdir(parents=True, exist_ok=True)
    fb, fv = RUNS / "hwy_base2020.json", RUNS / "hwynet_DAILY.json"
    if not fb.exists():
        fb.write_bytes(urllib.request.urlopen(CHAMP_API + "hwy_base2020?select=streetname,ft,a_b,geometry&limit=60000", timeout=300).read())
    if not fv.exists():
        fv.write_bytes(urllib.request.urlopen(CHAMP_API + "hwynet_weekday?time_period=eq.DAILY&select=a,b,ft,v_1&limit=100000", timeout=300).read())
    basel, vol = json.load(open(fb)), json.load(open(fv))
    check(len(basel) >= 8000, "SF-CHAMP hwy_base2020 links >= 8,000 (%d)" % len(basel))
    V = {(r["a"], r["b"]): r["v_1"] or 0 for r in vol}
    items = []
    for r in basel:
        if not r.get("geometry"):
            continue
        a, b = (int(x) for x in r["a_b"].split("_"))
        if (a, b) not in V and (b, a) not in V:
            continue
        g = json.loads(r["geometry"])
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for ln in lines:
            P = [xy(*p) for p in ln]
            if len(P) >= 2:
                items.append((P, {"a_b": r["a_b"], "street": base(r["streetname"]), "ft": r["ft"],
                                  "daily": V.get((a, b), 0) + V.get((b, a), 0), "brg": bearing(P), "P": P}))
    return items


def modelled(blocks, items):
    G = Grid(items)
    out = {}
    for cnn, b in blocks.items():
        for d, it in G.near(b["mid"], MATCH_FT):
            if it["street"] == b["street"] and parallel(it["brg"], b["brg"]) and it["daily"] > 0:
                out[cnn] = {"daily": it["daily"], "a_b": it["a_b"], "ft": it["ft"]}
                break
    return out


def interior(p, P, reach):
    """True when p lies within reach of P and its nearest point on P falls inside the line, not at or off an end (more
    than 5% of P's length from either end, measured along the whole line, so a vertex in the middle of P doesn't count
    as an end): a link beside the block (the other carriageway of a divided road), never the next link along the same
    street."""
    best, run, total = None, 0.0, length(P)
    for a, b in zip(P, P[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if not L2:
            continue
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        d = math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
        if best is None or d < best[0]:
            best = (d, (run + t * math.sqrt(L2)) / total)
        run += math.sqrt(L2)
    return best is not None and best[0] <= reach and 0.05 < best[1] < 0.95


def spans(b, its):
    """Each link's extent along the block's own line (its first to last point), in feet from the block's first point."""
    (x0, y0), (x1, y1) = b["P"][0], b["P"][-1]
    n = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / n, (y1 - y0) / n
    return [(min(t), max(t)) for t in ([(p[0] - x0) * ux + (p[1] - y0) * uy for p in it["P"]] for it in its)]


def in_series(b, its, share=0.25):
    """Pairs of a block's links that lie end to end along the street rather than side by side. Two links beside each
    other overlap along the block's line; two in series meet at a point or leave a gap. A pair overlapping by less than
    `share` of the shorter one's extent is in series. Returns the pairs as index pairs into `its`."""
    sp = spans(b, its)
    return [(i, j) for i in range(len(its)) for j in range(i + 1, len(its))
            if min(sp[i][1], sp[j][1]) - max(sp[i][0], sp[j][0]) < share * min(sp[i][1] - sp[i][0], sp[j][1] - sp[j][0])]


def beside(b, its):
    """Of the links matched to block b, the ones beside it, which a line across the street at the block's midpoint
    would cross: those the midpoint projects inside (interior()), so both halves of a divided road stay, even where the
    halves share end nodes, as Third Street's do around the T line's platforms. A link in series with one of those
    along the block's line (in_series()) is the block before or after, and goes. The rest, where the midpoint projects
    inside none of a carriageway's links (the block is short, or its midpoint sits on their shared node or in a gap
    SF-CHAMP leaves at an intersection), form runs of links in series with each other; each run keeps the one link
    that covers most of the block's own extent (in tenths of it), then the busiest, then the nearest. Used by modelled_main() and,
    through it, by through-traffic.py's blocks."""
    mid = b["mid"]
    inside = [i for i, it in enumerate(its) if interior(mid, it["P"], DUAL_FT)]
    ser = set(in_series(b, its))
    s = lambda i, j: (min(i, j), max(i, j)) in ser  # noqa: E731
    rest = [i for i in range(len(its)) if i not in inside and not any(s(i, j) for j in inside)]
    root = {i: i for i in rest}

    def find(i):
        while root[i] != i:
            i = root[i]
        return i
    for i in rest:
        for j in rest:
            if i < j and s(i, j):
                root[find(i)] = find(j)
    runs = collections.defaultdict(list)
    for i in rest:
        runs[find(i)].append(i)
    sp = spans(b, its)
    blen = math.hypot(b["P"][-1][0] - b["P"][0][0], b["P"][-1][1] - b["P"][0][1])
    cover = lambda i: max(0.0, min(sp[i][1], blen) - max(sp[i][0], 0.0))  # noqa: E731
    near = lambda i: min(seg_dist(mid, p, q) for p, q in zip(its[i]["P"], its[i]["P"][1:]))  # noqa: E731
    # Cover in tenths of the block, so a block split near its middle by a node is a tie, which goes to the busier link:
    # Spear St, Folsom to Harrison, is two halves of 12 and 2,022 a day either side of a zone's connector.
    keep = set(inside) | {min(r, key=lambda i: (-round(10 * cover(i) / (blen or 1.0)), -its[i]["daily"], near(i), its[i]["a_b"]))
                          for r in runs.values()}
    return sorted((its[i] for i in keep), key=lambda x: x["a_b"])


def modelled_main(mains, items):
    """cnn -> SF-CHAMP daily for a main-street block: the sum of every same-named parallel link beside it (within
    DUAL_FT, projecting inside the link, or within MATCH_FT; then beside()), each node pair once with both its
    directions. A two-way centerline drawn between two one-direction links, and each half of a divided road, so get
    both directions. Checks that no block sums two links in series (in_series())."""
    G = Grid(items)
    out, dropped, series = {}, 0, []
    for cnn, b in mains.items():
        got = {}
        for d, it in G.near(b["mid"], DUAL_FT):
            if it["street"] != b["street"] or not parallel(it["brg"], b["brg"]) or it["daily"] <= 0:
                continue
            k = frozenset(it["a_b"].split("_"))
            if k in got:
                continue
            if d <= MATCH_FT or interior(b["mid"], it["P"], DUAL_FT):
                got[k] = it
        if got:
            its = beside(b, list(got.values()))
            dropped += len(its) < len(got)
            series += [(cnn, its[i]["a_b"], its[j]["a_b"]) for i, j in in_series(b, its)]
            out[cnn] = {"daily": sum(x["daily"] for x in its), "a_b": "+".join(x["a_b"] for x in its), "ft": its[0]["ft"],
                        "links": len(its)}
    print("main blocks whose links before or after them along the street were dropped (beside()): %d" % dropped,
          file=sys.stderr)
    check(not series, "no main block sums two SF-CHAMP links in series along the street (%d: %s)" % (len(series), series[:5]))
    return out


def tract_vehicles():
    f = RUNS / "acs-b25044-tracts.json"
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(ACS_URL, timeout=120).read())
    d = json.load(open(f))
    out = {}
    for g, t in d["data"].items():
        e = t["B25044"]["estimate"]
        hh = e.get("B25044001") or 0
        veh = sum(n * ((e.get("B25044%03d" % (3 + n)) or 0) + (e.get("B25044%03d" % (10 + n)) or 0)) for n in range(1, 6))
        if hh:
            out[g[-11:]] = veh / hh
    check(len(out) >= 200, "ACS tracts with households >= 200 (%d)" % len(out))
    return out


def frontage(blocks, vph):
    """cnn -> (housing units, vehicles) fronting it: each census block's units shared by frontage along its outline,
    vehicles = units x its tract's vehicles per household."""
    hu = {r["geoid"]: r["hu"] for r in json.load(open(HU))["records"]}
    city_vph = statistics.median(vph.values())
    G = Grid([(b["P"], b["cnn"]) for b in blocks.values()])
    units, cars = collections.Counter(), collections.Counter()
    for rec in json.load(open(OUTLINES))["records"]:
        h = hu.get(rec["geoid"]) or 0
        if not h:
            continue
        v = vph.get(rec["geoid"][:11], city_vph)
        front = collections.Counter()
        R = [xy(*p) for p in rec["rings"][0]]
        for a, c in zip(R, R[1:]):
            s = math.hypot(c[0] - a[0], c[1] - a[1])
            n = max(1, int(s // 40))
            for i in range(n):
                t = (i + 0.5) / n
                nb = G.near((a[0] + t * (c[0] - a[0]), a[1] + t * (c[1] - a[1])), 120)
                if nb:
                    front[nb[0][1]] += s / n
        tot = sum(front.values())
        for cnn, fl in front.items():
            units[cnn] += h * fl / tot
            cars[cnn] += h * v * fl / tot
    return units, cars


def main():
    blocks, nodes, ctag = read_blocks()
    res = {c: b for c, b in blocks.items() if b["res"]}
    check(len(res) >= 9000, "residential blocks >= 9,000 (%d)" % len(res))
    days, failed, cstats, nrows, date_fix = read_counts(blocks)
    K, kinfo = k_factor(days, blocks)
    # Main streets have a flatter day than residential ones, so a lower peak-hour share, and it falls with road size.
    KM, kminfo = {}, {}
    for cc in ("2", "3", "4"):
        KM[cc], kminfo[cc] = k_factor(days, blocks, lambda b, cc=cc: b["cls"] == cc, 40, "classcode " + cc)
    meas, disagree = measured(days, failed, blocks, nodes, lambda c: K)
    kmain = lambda c: KM.get(blocks[c]["cls"], KM["4"])  # noqa: E731  (a residential-class main street's block: class 4's)
    meas_main, disagree_main = measured(days, failed, blocks, nodes, kmain)
    slow, slow_unmatched = slow_streets(blocks, K)
    for cnn, m in slow.items():          # the 2023 evaluation replaces an older count
        if cnn not in meas or meas[cnn]["year"] < 2023:
            meas[cnn] = m
    mod = modelled(blocks, champ_links())
    main_like = {c for c in res if res[c]["rampish"] or (c in mod and mod[c]["ft"] in MAJOR_FT)}
    res_both = [(meas[c]["daily"], mod[c]["daily"]) for c in sorted(meas) if c in res and c in mod and c not in main_like]
    check(len(res_both) >= 50, "residential blocks with both a count and SF-CHAMP >= 50 (%d)" % len(res_both))
    CHAMP_SCALE = statistics.median(c / m for c, m in res_both)
    rq = statistics.quantiles([m / c for c, m in res_both], n=4)

    # Main streets: every other surface street block (classcode 2 to 4 on a STREETS or PARKS layer), plus the
    # residential-class blocks found above to be a main street's block. Counted first, then SF-CHAMP scaled to the
    # counts on main streets, per band of model volume.
    mains = {c: b for c, b in blocks.items() if b["layer"].startswith(("STREETS", "PARKS")) and not b["rampish"]
             and (b["cls"] in ("2", "3", "4") or c in main_like)}
    mod_main = modelled_main(mains, champ_links())
    # Divided roads: two one-way centerlines of the same street side by side. Each half carries one direction, so
    # both get the pair's two-way figure: counts summed (or one side doubled), the model's larger sum. Paired by
    # geometry (carriageways()), since the halves often name different cross streets.
    mates = carriageways(mains)
    dual = {}
    for c in sorted(mates, key=int):
        dual[c] = min(mates[c], key=lambda o: (min(seg_dist(mains[c]["mid"], p, q) for p, q in zip(mains[o]["P"], mains[o]["P"][1:])), int(o)))
    by_name = collections.defaultdict(list)
    for c, b in mains.items():
        if b["oneway"] in ("F", "T"):
            by_name[(b["street"], frozenset((base(b["fname"]), base(b["tname"]))))].append(c)
    dual_by_name = sum(len(cs) for cs in by_name.values()
                       if len(cs) == 2 and opposed(mains[cs[0]], mains[cs[1]]))
    mmeas = {}
    for c in sorted(mains, key=int):
        m, o = meas_main.get(c), dual.get(c)
        if o is None:
            if m:
                mmeas[c] = m
            continue
        mo = meas_main.get(o)
        # A count placed by street and cross streets lands on both halves, so the same count can appear twice.
        same = m and mo and m["keys"] == mo["keys"] and m["dirs"] == mo["dirs"] and abs(m["daily"] - mo["daily"]) < 1
        if m and mo and not same and not (m["dirs"] & mo["dirs"]):
            mmeas[c] = dict(m, daily=m["daily"] + mo["daily"], peak=m["peak"] + mo["peak"], year=max(m["year"], mo["year"]),
                            pandemic=m["pandemic"] and mo["pandemic"], note="both carriageways counted, summed")
        elif m or mo:
            x = max((y for y in (m, mo) if y), key=lambda y: (len(y["dirs"]), y["year"], y["daily"]))
            mmeas[c] = dict(x) if len(x["dirs"]) > 1 else dict(x, daily=x["daily"] * 2, peak=x["peak"] * 2,
                                                                note="one carriageway of a divided road counted, doubled")
    for c, o in dual.items():
        if c in mod_main and o in mod_main and mod_main[o]["daily"] > mod_main[c]["daily"]:
            mod_main[c] = mod_main[o]
        elif o in mod_main and c not in mod_main:
            mod_main[c] = mod_main[o]
    band_of = lambda v: next(i for i, (lo, hi) in enumerate(MAIN_BANDS) if lo <= v < hi)  # noqa: E731
    # Fit on pre-pandemic counts only: the model is a 2019-or-earlier run.
    main_both = [(c, mmeas[c]["daily"], mod_main[c]["daily"]) for c in sorted(mains, key=int)
                 if c in mmeas and c in mod_main and not mmeas[c]["pandemic"] and mmeas[c]["year"] <= 2019]
    check(len(main_both) >= 150, "main-street blocks with both a pre-2020 count and SF-CHAMP >= 150 (%d)" % len(main_both))
    MAIN_SCALES = []
    for i, (lo, hi) in enumerate(MAIN_BANDS):
        rs = [c / m for _, c, m in main_both if band_of(m) == i]
        check(len(rs) >= 15, "main-street count/model pairs in band %d to %s >= 15 (%d)" % (lo, hi, len(rs)))
        MAIN_SCALES.append({"from": lo, "to": hi if hi < 10 ** 9 else None, "pairs": len(rs), "scale": round(statistics.median(rs), 3)})
    # Applied as one smooth curve, count = A x model^B, fitted by Theil-Sen on logs (the median of pairwise slopes), so
    # two blocks either side of a band edge don't jump. The band medians are kept in the summary as the check on it.
    LX = [(math.log(m), math.log(c)) for _, c, m in main_both]
    B = statistics.median((y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(LX) for x2, y2 in LX[i + 1:] if abs(x2 - x1) > 0.05)
    A = math.exp(statistics.median(y - B * x for x, y in LX))
    check(0.3 <= B <= 1.2, "main-street count/model log slope within 0.3 to 1.2 (%.3f)" % B)
    lo_m, hi_m = min(m for _, _, m in main_both), max(m for _, _, m in main_both)
    mscale = lambda v: A * min(max(v, lo_m), hi_m) ** (B - 1)  # noqa: E731  (held flat beyond the fitted range)
    for b_ in MAIN_SCALES:
        mid = b_["from"] * 1.5 if b_["to"] is None else (b_["from"] + b_["to"]) / 2 or 2500
        b_["curve_at_middle"] = round(mscale(mid), 3)
    mq = statistics.quantiles([m / c for _, c, m in main_both], n=4)
    main_agree = sum(cls_of(mmeas[x]["peak"]) == cls_of(m * mscale(m) * kmain(x)) for x, c, m in main_both)
    road_w = lambda c: 0.5 if c in dual else 1.0  # noqa: E731  (a divided road's two centerlines are one road)

    # Telraam: residents' counters, the 12 months to the extract's read date. Joined after the model scales are fitted, so SF-CHAMP stays
    # scaled to SFMTA's counts alone. Where a block also has an SFMTA figure, choose_count() picks the one it uses (and
    # so the one carried along its street); the other is kept on the row as `other`. A counter on one carriageway of a
    # divided road, seeing both directions, gives every carriageway beside it the same two-way figure.
    tel, tel_skipped, tel_read = telraam(blocks, mates)
    check(len(tel) >= 5, "Telraam segments joined to an SF block >= 5 (%d)" % len(tel))
    tel_vs_sfmta, tel_res, tel_main = [], [], []
    for c in sorted(tel, key=int):
        s = tel[c]
        if c in res and c not in main_like:
            table, targets, kk = meas, [c], lambda x: K
            tel_res.append(c)
        elif c in mains:
            table, targets, kk = mmeas, [c] + sorted(mates.get(c, ()), key=int), kmain
            tel_main.append(c)
        else:
            tel_skipped.append((s["id"], "block %s is neither residential nor a main street (layer %s, class %s)"
                                % (c, blocks[c]["layer"], blocks[c]["cls"])))
            continue
        for x in targets:
            old = table.get(x)
            has_tel = old and (old.get("telraam") or (old.get("other") or {}).get("telraam"))
            if has_tel:
                if x != c:       # the carriageway beside has its own counter, or took one already
                    continue
                old = old if not old.get("telraam") else old.get("other")
                if old and old.get("other"):   # drop the counter carried from beside; this block's own replaces it
                    old = {k: v for k, v in old.items() if k != "other"}
            tf = telraam_fig(s, own_share(old) or kk(x))
            table[x] = dict(tf, other=old) if choose_count(old, tf) == "telraam" else dict(old, other=tf)
            if old and x == c:
                # A Slow Streets figure is a day count (its peak hour is the day x K), so it is compared day against day.
                slow = bool(old.get("slow"))
                if not slow or tf["allday"]:
                    tv, sv = (tf["daily"], old["daily"]) if slow else (tf["peak"], old["peak"])
                    tel_vs_sfmta.append({"cnn": c, "telraam": s["id"], "unit": "day" if slow else "peak hour",
                                         "group": "Slow Streets 2023 (day count)" if slow else "SFMTA count",
                                         "telraam_value": round(tv), "sfmta_value": round(sv), "sfmta_year": old["year"],
                                         "sfmta_pandemic": 1 if old["pandemic"] else 0, "ratio": round(tv / sv, 2),
                                         "uses": choose_count(old, tf)})
    for x, m in [(x, meas[x]) for x in meas] + [(x, mmeas[x]) for x in mmeas]:
        if m.get("other"):
            check(("telraam" if m.get("telraam") else "sfmta") == choose_count(m if not m.get("telraam") else m["other"],
                                                                              m if m.get("telraam") else m["other"]),
                  "block %s uses the count COUNT_RULE picks" % x)
    tel_groups = {}
    for g in sorted({t["group"] for t in tel_vs_sfmta}):
        rs = [t["ratio"] for t in tel_vs_sfmta if t["group"] == g]
        tel_groups[g] = {"blocks": len(rs), "median_ratio": round(statistics.median(rs), 2),
                         "within_half_to_1_5": sum(1 for r in rs if 0.5 <= r <= 1.5)}

    vph = tract_vehicles()
    units, cars = frontage(blocks, vph)

    # Carried: walk each counted residential block's street through shared nodes.
    main_node = {n for n, cs in nodes.items() if any(blocks[c]["cls"] in ("1", "2", "3", "4") for c in cs)}
    counted = {c for c in meas if c in res and c not in main_like}

    def walk(src, start_peak):
        out = {}
        stack = [(src, start_peak)]
        while stack:
            cur, val = stack.pop()
            for n in blocks[cur]["nodes"]:
                if n in main_node:
                    continue
                for nx in sorted(nodes[n]):
                    if nx == cur or nx not in res or nx in main_like or res[nx]["street"] != res[cur]["street"] or nx in counted:
                        continue
                    v = val - cars.get(nx, 0.0)
                    if v < 90 or out.get(nx, 0) >= v:
                        continue
                    out[nx] = v
                    stack.append((nx, v))
        return out

    carried = {}
    for src in sorted(counted, key=int):
        for nx, v in walk(src, meas[src]["peak"]).items():
            if nx not in carried or v > carried[nx][0]:
                carried[nx] = (v, src)
    # Validation: counted blocks next to another counted block on the same street.
    floor_ok = floor_n = floor_ok90 = floor_n90 = 0
    for c in sorted(counted, key=int):
        for n in res[c]["nodes"]:
            if n in main_node:
                continue
            for o in sorted(nodes[n]):
                if o != c and o in counted and res[o]["street"] == res[c]["street"]:
                    pred = meas[o]["peak"] - cars.get(c, 0.0)
                    floor_n += 1
                    floor_ok += pred <= meas[c]["peak"]
                    if pred >= 90:
                        floor_n90 += 1
                        floor_ok90 += pred <= meas[c]["peak"]

    # Main-street estimate.
    main_vol = {}
    for cnn, b in blocks.items():
        if b["cls"] in ("2", "3", "4") and cnn in mains:
            if cnn in mmeas:
                main_vol[cnn] = (mmeas[cnn]["daily"], "counted", mmeas[cnn]["year"])
            elif cnn in mod_main:
                main_vol[cnn] = (mod_main[cnn]["daily"] * mscale(mod_main[cnn]["daily"]), "modelled", None)
    G_main = Grid([(blocks[c]["P"], c) for c in sorted(main_vol, key=int)])

    def parallel_main(b):
        for d, c in G_main.near(b["mid"], PAR_FT):
            if parallel(blocks[c]["brg"], b["brg"]) and blocks[c]["street"] != b["street"]:
                return c, d
        return None, None

    calib, agree = [], collections.Counter()
    for cnn in sorted(counted, key=int):
        c, d = parallel_main(res[cnn])
        if c:
            calib.append(meas[cnn]["daily"] / main_vol[c][0])
            agree[(cls_of(meas[cnn]["peak"]), cls_of(main_vol[c][0] * SPILL["central"] * K))] += 1
    cq = statistics.quantiles(calib, n=4)
    modal = max(sum(v for (x, y), v in agree.items() if x == i) for i in range(len(CLASSES)))

    rows = []
    for cnn in sorted(res, key=int):
        b = res[cnn]
        u = units.get(cnn, 0.0)
        row = {"cnn": cnn, "street": b["name"], "from": b["fname"], "to": b["tname"], "ft": round(b["len"]),
               "units": round(u, 1), "cars": round(cars.get(cnn, 0.0), 1), "res_peak": round(u * RES_RATE["central"], 1)}
        if cnn in main_like:
            row.update(kind="main", src="a main street's block: %s" % ("named a ramp or tunnel" if b["rampish"] else
                                                                      "SF-CHAMP codes it as a major road (ft %s)" % mod[cnn]["ft"]))
        elif cnn in meas:
            m = meas[cnn]
            if m.get("slow"):
                src = "SFMTA Slow Streets evaluation 2023, weekday daily x K"
            elif m.get("telraam"):
                src = m["how"]
            else:
                src = "SFMTA count, %d day%s, %s%s%s" % (m["n_days"], "" if m["n_days"] == 1 else "s", m["how"],
                                                        ", " + m["note"] if m["note"] else "",
                                                        ", pandemic-era count" if m["pandemic"] else "")
            row.update(kind="measured", daily=round(m["daily"]), peak=round(m["peak"]), year=m["year"], src=src,
                       pandemic=1 if m["pandemic"] else 0)
            row.update(tel_fields(m))
        elif cnn in mod:
            m = mod[cnn]
            row.update(kind="modelled", daily=round(m["daily"] * CHAMP_SCALE), peak=round(m["daily"] * CHAMP_SCALE * K),
                       raw_daily=round(m["daily"]), raw_cls=cls_of(m["daily"] * K),
                       src="SF-CHAMP weekday daily, link %s, undated run (mid-2019 or earlier), x %.2f (count/model) x K"
                           % (m["a_b"], CHAMP_SCALE))
        elif cnn in carried:
            v, s0 = carried[cnn]
            row.update(kind="carried", peak=round(v), daily=round(v / K), low=round(v), high=round(meas[s0]["peak"]),
                       year=meas[s0]["year"], from_cnn=s0,
                       src="carried from the count on %s, %s to %s (%d), less every car the homes between could park"
                           % (blocks[s0]["name"], blocks[s0]["fname"], blocks[s0]["tname"], meas[s0]["year"]))
        else:
            c, d = parallel_main(b)
            if not c:
                row.update(kind="none")
            else:
                mv, mk, my = main_vol[c]
                daily = mv * SPILL["central"]
                row.update(kind="estimated", daily=round(daily), peak=round(daily * K),
                           low=round(mv * SPILL["low"] * K), high=round(mv * SPILL["high"] * K),
                           src="%d%% of the parallel main street's %s volume" % (round(SPILL["central"] * 100), mk))
        if "peak" in row:
            row["cls"] = cls_of(row["peak"])
            row["excess"] = round(row["peak"] - row["res_peak"])
        if row["kind"] != "main":
            row.update(caveats(meas.get(cnn) if row["kind"] == "measured" else None, "res", disagree.get(cnn)))
        rows.append(row)
    check(len({r["cnn"] for r in rows}) == len(rows) == len(res), "one output row per residential block")

    mrows_all = []
    for cnn in sorted(mains, key=int):
        b = mains[cnn]
        row = {"cnn": cnn, "road": "main", "street": b["name"], "from": b["fname"], "to": b["tname"], "ft": round(b["len"]),
               "classcode": b["cls"]}
        if cnn in dual:
            row["divided_with"] = dual[cnn]
        if cnn in mmeas:
            m = mmeas[cnn]
            row.update(kind="measured", daily=round(m["daily"]), peak=round(m["peak"]), year=m["year"],
                       pandemic=1 if m["pandemic"] else 0,
                       src=m["how"] if m.get("telraam") else
                       "SFMTA count, %s day%s, %s%s%s" % (m["n_days"], "" if m["n_days"] == 1 else "s", m["how"],
                                                          ", " + m["note"] if m["note"] else "",
                                                          ", pandemic-era count" if m["pandemic"] else ""))
            row.update(tel_fields(m))
        elif cnn in mod_main:
            m = mod_main[cnn]
            sc, kk = mscale(m["daily"]), kmain(cnn)
            row.update(kind="modelled", daily=round(m["daily"] * sc), peak=round(m["daily"] * sc * kk),
                       raw_daily=round(m["daily"]),
                       src="SF-CHAMP weekday daily, link%s %s, undated run (mid-2019 or earlier), x %.2f (count/model on main "
                           "streets, fitted on model volume) x %.3f (main-street peak share, classcode %s)"
                           % ("s" if m["links"] > 1 else "", m["a_b"], sc, kk, blocks[cnn]["cls"]))
        else:
            row.update(kind="none")
        if "peak" in row:
            row["cls"] = cls_of(row["peak"])
        row.update(caveats(mmeas.get(cnn), "main", disagree_main.get(cnn)))
        mrows_all.append(row)
    # Few Telraam counters on a main street have an SFMTA count on their block to check them against (the summary's
    # main_vs_sfmta_same_block lists them, and the tel_main card caveat names them). A counter's figure against the
    # scaled model on the next blocks of the same street is the other check, kept in the summary, and every
    # main-street Telraam figure carries the `tel_main` caveat.
    by_mrow = {r["cnn"]: r for r in mrows_all}
    tel_main_vs_model = []
    for c in sorted(tel_main, key=int):
        r = by_mrow[c]
        nb = sorted({o for n in blocks[c]["nodes"] for o in nodes[n]
                     if o != c and o in by_mrow and blocks[o]["street"] == blocks[c]["street"] and o not in mates.get(c, ())
                     and by_mrow[o]["kind"] == "modelled"}, key=int)
        if r.get("count_choice") == "telraam" and nb:
            mp = statistics.median(by_mrow[o]["peak"] for o in nb)
            tel_main_vs_model.append({"cnn": c, "telraam": r["telraam"], "telraam_peak": r["peak"], "model_peak": round(mp),
                                      "next_blocks": nb, "ratio": round(r["peak"] / mp, 2)})
    # SF-CHAMP's undated table against SFMTA's dated 2019 Base run of the same model (DTX application), per link.
    dtx_f = RUNS / "sfmta-champ-2019-base.json"
    if not dtx_f.exists():
        feats, off = [], 0
        while True:
            page = json.load(urllib.request.urlopen(DTX_URL + str(off), timeout=120))["features"]
            feats += [f["attributes"] for f in page]
            if len(page) < 2000:
                break
            off += 2000
        dtx_f.write_text(json.dumps(feats))
    dtx = {(a["A"], a["B"]): a["DAILY_TOT"] for a in json.load(open(dtx_f))}
    check(len(dtx) >= 4000, "SFMTA SF-CHAMP 2019 Base links >= 4,000 (%d)" % len(dtx))
    hv = {(r["a"], r["b"]): r["v_1"] or 0 for r in json.load(open(RUNS / "hwynet_DAILY.json"))}
    dtx_ratio = [hv[k] / v for k, v in sorted(dtx.items()) if v and hv.get(k)]

    # People hurt on residential streets, 2022 to 2024: the busiest residential block within NEAR_FT with a figure.
    G = json.load(open(POINTS))
    check(len(G["features"]) == 922, "people file has 922 rows (%d)" % len(G["features"]))
    GR = Grid([(b["P"], c) for c, b in res.items()])
    by_cnn = {r["cnn"]: r for r in rows}
    rank = {k: i for i, k in enumerate(KINDS)}
    people = collections.Counter()
    people_res = corner_legs = 0
    for f in G["features"]:
        p = f["properties"]
        if not p["place"].startswith("residential"):
            continue
        people_res += 1
        legs = [by_cnn[c] for _, c in GR.near(xy(*f["geometry"]["coordinates"][:2]), NEAR_FT)]
        if not legs:
            people[("none", "no block within 60 ft")] += 1
            continue
        corner_legs += len(legs) > 1
        fig = [r for r in legs if r["kind"] in rank]
        if not fig:
            people[(legs[0]["kind"], "none")] += 1
            continue
        best = min(rank[r["kind"]] for r in fig)
        r = max((r for r in fig if rank[r["kind"]] == best), key=lambda r: (r["peak"], -int(r["cnn"])))
        people[(r["kind"], r["cls"])] += 1

    GM = Grid([(b["P"], c) for c, b in mains.items()])
    by_main = {r["cnn"]: r for r in mrows_all}
    people_main = collections.Counter()
    on_main = 0
    for f in G["features"]:
        if not f["properties"]["place"].startswith("main"):
            continue
        on_main += 1
        legs = [by_main[c] for _, c in GM.near(xy(*f["geometry"]["coordinates"][:2]), NEAR_FT)]
        fig = [r for r in legs if r["kind"] in ("measured", "modelled")]
        if not fig:
            people_main[("none", "none")] += 1
            continue
        r = max(fig, key=lambda r: (r["peak"], -int(r["cnn"])))   # the busiest leg, measured or modelled
        people_main[(r["kind"], r["cls"])] += 1
    main_table = []
    for i, (lo, hi, lab) in enumerate(CLASSES):
        row = {"class": i, "label": lab}
        for k in ("measured", "modelled"):
            rs = [r for r in mrows_all if r["kind"] == k and r["cls"] == i]
            row[k] = {"blocks": len(rs), "miles": round(sum(r["ft"] * road_w(r["cnn"]) for r in rs) / 5280, 1),
                      "people": people_main[(k, i)]}
        main_table.append(row)

    table = []
    for i, (lo, hi, lab) in enumerate(CLASSES):
        row = {"class": i, "label": lab, "peak_from": lo, "peak_to": hi if hi < 10 ** 9 else None,
               "daily_from": round(lo / K), "daily_to": round(hi / K) if hi < 10 ** 9 else None}
        for k in KINDS:
            rs = [r for r in rows if r["kind"] == k and r["cls"] == i]
            row[k] = {"blocks": len(rs), "miles": round(sum(r["ft"] for r in rs) / 5280, 1), "people": people[(k, i)],
                      "blocks_after_residents": sum(1 for r in rows if r["kind"] == k and cls_of(max(0, r["excess"])) == i)}
        table.append(row)
    est = [r for r in rows if r["kind"] == "estimated"]
    mrows = [r for r in rows if r["kind"] == "measured"]
    summary = {
        "about": "Residential blocks (centerline classcode 5, STREETS layers) and main-street blocks (main_streets) by "
                 "two-way peak-hour vehicles, by how the volume was found. See scripts/hin-cut-through.py.",
        "sources": {"centerlines": ctag, "counts": "SFMTA Corridor Counts CSV, https://www.sfmta.com/media/40635",
                    "slow_streets": "data/slow-streets/evaluations.csv", "champ": CHAMP_API + "hwynet_weekday",
                    "housing": "data/extract/census-blocks/2020.json", "vehicles": ACS_URL, "people": G.get("sources")},
        "k": kinfo, "spill": SPILL, "spill_source": SPILL_SOURCE, "res_rate": RES_RATE, "res_source": RES_SOURCE,
        "residential_blocks": len(rows), "residential_miles": round(sum(r["ft"] for r in rows) / 5280, 1),
        "coverage": {k: {"blocks": sum(1 for r in rows if r["kind"] == k),
                         "miles": round(sum(r["ft"] for r in rows if r["kind"] == k) / 5280, 1)} for k in KINDS + ("none", "main")},
        "measured_years": dict(sorted(collections.Counter(str(r["year"]) for r in mrows).items())),
        "measured_pandemic_only": sum(r.get("pandemic", 0) for r in mrows),
        "measured_from_slow_streets": sum(1 for r in mrows if "Slow Streets" in r["src"]),
        "measured_paired": sum(1 for r in mrows if "next block" in r["src"]),
        "measured_one_dir_doubled": sum(1 for r in mrows if "doubled" in r["src"]),
        "measured_24h_rejected": sum(1 for r in mrows if "rejected" in r["src"]),
        "classes": table,
        "estimated_range": {"low": dict(sorted(collections.Counter(str(cls_of(r["low"])) for r in est).items())),
                            "high": dict(sorted(collections.Counter(str(cls_of(r["high"])) for r in est).items()))},
        "calibration": {"blocks": len(calib), "median": round(statistics.median(calib), 4), "p25": round(cq[0], 4),
                        "p75": round(cq[2], 4),
                        "note": "counted residential block's daily / its parallel main block's daily (counted or modelled)",
                        "class_agree": sum(v for (x, y), v in agree.items() if x == y),
                        "class_within_one": sum(v for (x, y), v in agree.items() if abs(x - y) <= 1),
                        "modal_class_guess": modal},
        "carried_validation": {"pairs": floor_n, "floor_held": floor_ok, "pairs_floor_90_plus": floor_n90,
                               "floor_held_90_plus": floor_ok90,
                               "note": "next counted block's peak less this block's vehicles, against this block's own count"},
        "sink": {"rule": "housing units fronting the block x tract vehicles per household (ACS B25044), all arriving in the peak hour",
                 "vehicles_per_household_median_tract": round(statistics.median(vph.values()), 2),
                 "residential_block_vehicles_median": round(statistics.median(cars.get(c, 0.0) for c in res), 1)},
        "champ_vs_count": {"blocks": len(res_both), "median_ratio": round(statistics.median(m / c for c, m in res_both), 3),
                           "ratio_p25": round(rq[0], 3), "ratio_p75": round(rq[2], 3), "scale_applied": round(CHAMP_SCALE, 3),
                           "unscaled_classes": dict(sorted(collections.Counter(str(r["raw_cls"]) for r in rows if r["kind"] == "modelled").items()))},
        "people": {"on_residential_streets": people_res, "at_corners_with_several_legs": corner_legs,
                   "no_block": people[("none", "no block within 60 ft")], "no_data": people[("none", "none")],
                   "main_street_blocks": people[("main", "none")]},
        "main_streets": {
            "blocks": len(mrows_all), "miles": round(sum(r["ft"] * road_w(r["cnn"]) for r in mrows_all) / 5280, 1),
            "miles_note": "road miles: a divided road's two centerlines count once",
            "divided_blocks": len(dual), "divided_blocks_by_cross_street_name": dual_by_name, "k_by_classcode": kminfo,
            "coverage": {k: {"blocks": sum(1 for r in mrows_all if r["kind"] == k),
                             "miles": round(sum(r["ft"] * road_w(r["cnn"]) for r in mrows_all if r["kind"] == k) / 5280, 1)}
                         for k in ("measured", "modelled", "none")},
            "classes": main_table,
            "people": {"on_main_streets": on_main, "no_figure": people_main[("none", "none")]},
            "champ_vs_count": {"blocks": len(main_both), "median_ratio": round(statistics.median(m / c for _, c, m in main_both), 3),
                               "ratio_p25": round(mq[0], 3), "ratio_p75": round(mq[2], 3), "scale_by_model_volume": MAIN_SCALES,
                               "curve": {"A": round(A, 4), "B": round(B, 4), "applied": "count = A x model^B, model held within %d to %d" % (lo_m, hi_m)},
                               "class_agree_scaled_in_sample": main_agree,
                               "fit_on": "main-street blocks with a 2014 to 2019 count and an SF-CHAMP figure"},
            "champ_vs_2019_base": {"links": len(dtx_ratio), "median_ratio": round(statistics.median(dtx_ratio), 3),
                                   "note": "undated hwynet_weekday v_1 / SFMTA's SF-CHAMP 2019 Base DAILY_TOT (links >= 5,001 a day only), same directed link"}},
        "count_rows": nrows, "count_stats": dict(sorted(cstats.items())), "count_dates": dict(sorted(date_fix.items())),
        "count_days_disagree": {"rule": "a block whose count-days in its latest year read %d-fold apart has no count "
                                        "(card caveat counts_disagree)" % DISAGREE,
                                "residential": {c: [["%d-%02d-%02d" % k, v] for k, v in d] for c, d in sorted(disagree.items(), key=lambda kv: int(kv[0]))
                                                if c in res and c not in main_like},
                                "main": {c: [["%d-%02d-%02d" % k, v] for k, v in d] for c, d in sorted(disagree_main.items(), key=lambda kv: int(kv[0]))
                                         if c in mains}},
        "slow_streets_unmatched": sorted(slow_unmatched),
        "telraam": {"source": "data/extract/telraam/segments.json (tools/street-safety/telraam-sf.py)",
                    "segments_joined": len(tel), "residential_blocks": len(tel_res), "main_blocks": len(tel_main),
                    "skipped": [{"segment": a_, "why": b_} for a_, b_ in sorted(tel_skipped)],
                    "count_rule": COUNT_RULE, "count_rule_text": COUNT_RULE_TEXT[COUNT_RULE],
                    "override_gate": {"min_season_days": OVERRIDE_MIN_DAYS, "read": tel_read},
                    "main_vs_sfmta_same_block": [dict(t, street=blocks[t["cnn"]]["name"], **{"from": blocks[t["cnn"]]["fname"], "to": blocks[t["cnn"]]["tname"]})
                                                 for t in tel_vs_sfmta if t["cnn"] in tel_main and t["unit"] == "peak hour"],
                    "vs_sfmta_same_block": tel_vs_sfmta, "vs_sfmta_by_group": tel_groups,
                    "main_vs_next_model_blocks": {"blocks": len(tel_main_vs_model),
                                                  "median_ratio": round(statistics.median(t["ratio"] for t in tel_main_vs_model), 2)
                                                  if tel_main_vs_model else None, "rows": tel_main_vs_model}},
    }
    out_rows = [{k: v for k, v in r.items() if v is not None} for r in [dict(r, road="res") for r in rows if r["kind"] != "main"] + mrows_all]
    write_text(OUT_BLOCKS, json.dumps({"about": summary["about"], "k": kinfo["k"], "spill": SPILL, "champ_scale": round(CHAMP_SCALE, 3), "main_curve": [round(A, 4), round(B, 4)], "k_main": {c: round(v, 4) for c, v in KM.items()},
                                       "count_rule": {"rule": COUNT_RULE, "text": COUNT_RULE_TEXT[COUNT_RULE], "min_season_days": OVERRIDE_MIN_DAYS,
                                                      "read": tel_read},
                                       "classes": [c[2] for c in CLASSES], "blocks": out_rows}, indent=0, sort_keys=True) + "\n")
    write_text(OUT_SUM, json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ("k", "coverage", "calibration", "carried_validation", "people", "champ_vs_count",
                                              "sink")}, indent=1), file=sys.stderr)
    for t in table:
        print(t["label"], {k: (t[k]["blocks"], t[k]["miles"], t[k]["people"]) for k in KINDS}, file=sys.stderr)
    print(json.dumps({k: v for k, v in summary["main_streets"].items() if k != "classes"}, indent=1), file=sys.stderr)
    for t in main_table:
        print("main", t["label"], {k: (t[k]["blocks"], t[k]["miles"], t[k]["people"]) for k in ("measured", "modelled")}, file=sys.stderr)


if __name__ == "__main__":
    main()
