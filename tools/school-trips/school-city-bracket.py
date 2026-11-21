#!/usr/bin/env python3
"""School Trips' simple track: SF student car and bike share at years 4 and 10 for each bikeway budget, as a bracket of three cases paced on real cities (Portland, Seville, Paris), with a separate cost-of-driving row and a per-school split.

    ~/.venvs/sf-works-geo/bin/python tools/school-trips/school-city-bracket.py           # writes out/school-sim/city-bracket.json
    ~/.venvs/sf-works-geo/bin/python tools/school-trips/school-city-bracket.py --check   # the checks on the written file

Bryan, 2026-10-18: "Can we do both paths and make them parallel tracks. And
present them separately for review?" This is the simple path from
notes/school-trips-2026-10/2026-10-18-city-mode-shift-models.md ("Our plan"):
the headline comes from what whole cities measured, and the detailed sim is
used only for where the network goes and how the result splits by school.
Reviewed in notes/school-trips-2026-10/2026-10-18-simple-track-pipeline-review.md.

INPUTS, read fresh on every run (segments.json is replaced by each rerun):
  out/school-sim/city.json        today's citywide shares (levers.today), the sim's calibrated output
  out/school-sim/schools.json     each school's cds, name and modelled students
  out/school-sim/segments.json    each budget's chosen chunks and their edges
  site/data/school-sim/today-net.json   the all-ages lines the sim counts as built today
  out/school-sim/blocks.json      expected students and today's car share by block and school
  data/extract/census-blocks/2020.json, data/extract/census-dhc/p12-blocks.json   block points, children 5 to 17

COVERAGE. A home block is covered when its census interior point lies within
1,000 ft, straight line, of an all-ages line. Each block counts by its
children aged 5 to 17 (census 2020 DHC P12). After a build, the lines are
today's plus every chunk the budget picks.

THE CASES. Each case is one city's measured bike pace, held for the years
that city sustained it:
  low      Portland's measured pace applied to SF's build: bike commute 5.8% (2009) to 6.3% (2017),
           the first and last years PBOT's decade report gives, then held
  central  Seville, all trips 3.2% (2007) to 5.6% (2011), then held (its plateau)
  high     Paris, bike commute 4.2% (2015) to 10.1% (2022), run to year 10 (it was still rising)
RANGE (Bryan, 2026-10-18: "Use middle end and show low to high range"). Each
case at each budget and year runs two variants. The pace is the city's
percentage points a year (Bryan, 2026-10-18: "Can we do it as absolute
percentages instead?"), times the share of the bike gain drawn from cars,
Seville's 28% or SF's proportional draw (the car's share of the other modes,
about 44%).
range.low and range.high are the variants with the fewest and most students
out of cars. range.middle is their midpoint, field by field.
SCALING. Every case's pace is scaled the same way: by the share of SF's
uncovered children 5 to 17 the build reaches, treating each city's pace as
what a whole-city program gives. No city's coverage before its program is on
the same measure as ours, so no city-to-SF coverage ratio is used.
CAR SIDE OF A NETWORK CASE. Marqués et al. 2014, Table 3, found 28% of
Seville's new cyclists came from cars (taxi and car passenger included), 28%
from walking, 40% from transit, 4% from motorbikes. The rest of each city's
measured car fall is not counted as network effect, and is reported beside the
driving-cost row (cityCarResidual).
DRIVING-COST ROW. Parking removal, parking price and a driving charge, merged
into one lever. Kept apart from every budget's figure, never added into it:
  low      Oslo, centre parking removal: "few adaptations through changed travel behaviour", taken as 0
  central  Ghent circulation plan, trips to school: car 14% to 11%, bike 49% to 55% (report p. 42), over 3 years
  high     London ULEZ, a net 22% of driven children switched (42% against 20% in Luton), at one year
PER SCHOOL. Each budget's citywide students out of cars, at the middle figure,
are split across schools in proportion to each school's drivers whose home block is uncovered
today and covered after the build (blocks.json rows, students x carPct). The
budgets are separate plans, not nested, so runningMax holds each school's
largest figure at that budget or any smaller one. The independent check sums
each school's students out estimated from its own rows' newly covered
students and compares the total with the citywide figure from census coverage.

Light compute: one process, no sim rerun. Run with nice 15 and PYTHONHASHSEED=0.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import math
import os
import sys

import numpy as np
from shapely import STRtree, points as sh_points
from shapely.geometry import LineString, MultiLineString

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import stable  # noqa: E402

SIM = os.path.join(ROOT, "out", "school-sim")
OUT = os.path.join(SIM, "city-bracket.json")
TODAY_NET = os.path.join(ROOT, "site", "data", "school-sim", "today-net.json")
BLOCK_PTS = os.path.join(ROOT, "data", "extract", "census-blocks", "2020.json")
BLOCK_KIDS = os.path.join(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")

COVER_FT = 1000.0
FT = 0.3048
YEARS = (4, 10)
RULES = ("absolute",)   # percentage points a year; growth on a city's own base was dropped 2026-10-18
DRAWS = ("seville28", "sfDraw")   # Seville's 28% of new cyclists from cars, or SF's proportional draw
VARIANTS = tuple("%s-%s" % (r, w) for r in RULES for w in DRAWS)
SPLIT_TOL = 0.01     # the written per-school split against the citywide figure
INDEP_TOL = 0.12     # the per-school estimate from the sim's own rows against census coverage. The sim's SFUSD
                     # students gain coverage up to 11% faster than all census children at $5M, because the
                     # program aims at where those students live. A broken join or a dropped school misses by far more.
CAR_FROM_BIKE = 0.28  # Marqués et al. 2014, Table 3: share of Seville's new cyclists who came from cars
WIT = "https://www.witpress.com/Secure/elibrary/papers/SC14/SC14065FU1.pdf"
PARIS = "https://www.paris.fr/pages/comment-se-sont-deplaces-les-parisiens-en-2025-35425"

CASES = [
    {"case": "low", "city": "Portland", "label": "Portland's measured pace applied to SF's build",
     "measure": "bike commute share, ACS", "bike": (5.8, 6.3), "car": None, "span": (2009, 2017), "holdAfter": 8,
     "scale": "uncovered",
     "src": "BikePortland, 2019-09-11, PBOT's decade progress report on the 2030 Bike Plan",
     "url": "https://bikeportland.org/2019/09/11/a-decade-in-pbot-shares-progress-report-on-2030-bike-plan-304557",
     "tag": "[secondary — verify]",
     "context": "2009 and 2017 are the first and last years the article gives. PBOT's own report link returns 404. "
                "Portland built about 99 of 681 planned miles. No car series in the source."},
    {"case": "central", "city": "Seville", "label": "Seville's measured pace, 2007 to 2011",
     "measure": "share of all trips", "bike": (3.2, 5.6),
     # car 2009 and 2011 are the authors' estimates, 2007 car trips scaled by a 16% fall in traffic counts (Table 2)
     "car": (36.3, 30.5), "span": (2007, 2011), "holdAfter": 4,
     "scale": "uncovered",
     "src": "Marqués et al., WIT Transactions 191, 2014, Tables 2 and 3", "url": WIT,
     "tag": "[primary — read 2026-10-18]",
     "context": "A 120 km cycle network built from 2006 to 2010. Figures stabilised 2011 to 2013."},
    {"case": "high", "city": "Paris", "label": "Paris's measured pace, 2015 to 2022, run to year 10",
     "measure": "bike commute share, census", "bike": (4.2, 10.1), "car": (12.3, 9.0), "span": (2015, 2022),
     "holdAfter": 10, "scale": "uncovered",
     "src": "Ville de Paris, \"Comment se sont déplacés les Parisiens en 2025\"", "url": PARIS,
     "tag": "[primary — read 2026-10-18]",
     "context": "Census commute shares of resident workers. Run past its 7 measured years."},
]

SEVILLE_QUOTE = ("The modal shift from car to bike is meaningful, but this alone cannot explain the estimated reduction "
                 "in car mobility shown in Table 2. Other reasons, such as the economic crisis or the onset of new public "
                 "transport infrastructures (subway and tram), could contribute to this decline.")

DRIVING_COST = [
    {"case": "low", "city": "Oslo", "car": (1.0, 1.0), "bike": (1.0, 1.0), "years": 1,
     "src": "TØI, BYTRANS: changes in the city centre of Oslo 2017 to 2019",
     "url": "https://www.toi.no/publications/bytrans-changes-in-the-city-centre-of-oslo-2017-2019-effects-and-consequences-for-commuters-city-centre-users-city-centre-attractiveness-and-for-delivery-drivers-article36324-29.html",
     "tag": "[primary — read 2026-10-18]",
     "rule": "\"Few adaptations through changed travel behaviour\", taken as no change."},
    {"case": "central", "city": "Ghent", "car": (14.0, 11.0), "bike": (49.0, 55.0), "years": 3,
     "src": "Evaluatierapport Circulatieplan Gent, May 2019, p. 42, trips to school",
     "url": "https://www.Stad.Gent/sites/default/files/onepager/cta/Evaluatierapport%20Circulatieplan%20Gent%202019%20finaal.pdf",
     "tag": "[primary — read 2026-10-18]",
     "rule": "Trips to school before and after the 2017 plan: car 14% to 11%, bike 49% to 55%. Applied over 3 years, then held."},
    {"case": "high", "city": "London ULEZ", "drivenSwitch": 0.22, "years": 1,
     "src": "University of Cambridge on the CHILL study, IJBNPA, 2024-09-05",
     "url": "https://www.cam.ac.uk/research/news/children-switch-to-walking-and-cycling-to-school-after-introduction-of-londons-ultra-low-emission",
     "tag": "[primary — read 2026-10-18, press release only]",
     "rule": "42% of driven children switched to active travel against 20% in Luton. The 22-point net is applied to SF's driven students "
             "at year 1, then held. No bike split is given, so bike is unchanged."},
]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def xy(lon, lat):
    """Local metres, the equirectangular frame school-gravity.py uses."""
    lat0 = math.radians(37.76)
    return (math.radians(lon) * math.cos(lat0) * 6371008.8, math.radians(lat) * 6371008.8)


def line(pts):
    return LineString([xy(p[0], p[1]) for p in pts])


def blocks():
    kids = {r["geoid"]: r for r in read(BLOCK_KIDS)["records"]}
    pts = {r["geoid"]: r for r in read(BLOCK_PTS)["records"]}
    out = []
    for gid in sorted(kids):
        k = kids[gid]
        n = k["a5_9"] + k["a10_14"] + k["a15_17"]
        if n <= 0:
            continue
        p = pts[gid]
        out.append((gid, p["lon"], p["lat"], n))
    return out


def covered_by(geoms, bx, by):
    """Pairs (block index, geometry index) of block points within COVER_FT of a geometry."""
    tree = STRtree(geoms)
    pb = sh_points(np.column_stack([bx, by]))
    bi, gi = tree.query(pb, predicate="dwithin", distance=COVER_FT * FT)
    return bi, gi


def pace(c):
    """(log growth a year, points a year) for bike, and the same for car or None."""
    yrs = c["span"][1] - c["span"][0]
    b0, b1 = c["bike"]
    out = {"years": yrs, "bikeLog": math.log(b1 / b0) / yrs, "bikePts": (b1 - b0) / yrs}
    if c["car"]:
        c0, c1 = c["car"]
        out.update(carLog=math.log(c1 / c0) / yrs, carPts=(c1 - c0) / yrs)
    return out


def figures(shares, n, dbike, dcar):
    return {"bikePct": round(shares["bike"] + dbike, 2), "carPct": round(shares["car"] + dcar, 2),
            "bikePts": round(dbike, 3), "carPts": round(dcar, 3),
            "studentsOutOfCars": round(-dcar / 100.0 * n, 1) + 0.0,
            "studentsOntoBikes": round(dbike / 100.0 * n, 1) + 0.0}


def build():
    city = read(os.path.join(SIM, "city.json"))
    today = city["levers"]["today"]
    shares = {m: today[m] for m in ("car", "carpool", "walk", "bike", "transit", "bus")}
    sf_draw = shares["car"] / (100.0 - shares["bike"])  # the car's share of the modes a new cyclist leaves
    sch = read(os.path.join(SIM, "schools.json"))["schools"]
    n_students = sum(s["students"] for s in sch)
    seg = read(os.path.join(SIM, "segments.json"))
    net = read(TODAY_NET)["lines"]
    bl = read(os.path.join(SIM, "blocks.json"))

    blk = blocks()
    gid_ix = {b[0]: i for i, b in enumerate(blk)}
    bxy = np.array([xy(b[1], b[2]) for b in blk])
    kids = np.array([b[3] for b in blk], dtype=float)

    bi, _gi = covered_by([line(p) for p in net if len(p) >= 2], bxy[:, 0], bxy[:, 1])
    cov_today = np.zeros(len(blk), dtype=bool)
    cov_today[bi] = True

    chunks = seg["chunks"]
    cid = [c["id"] for c in chunks]
    cgeom = [MultiLineString([[xy(*e[0]), xy(*e[1])] for e in c["pts"]]) for c in chunks]
    bi, gi = covered_by(cgeom, bxy[:, 0], bxy[:, 1])
    chunk_blocks = {}
    for b, g in zip(bi.tolist(), gi.tolist()):
        chunk_blocks.setdefault(cid[g], []).append(b)

    col = bl["columns"]
    school_cds = bl["schools"]
    row_blk = np.array([gid_ix.get(bl["geoids"][b], -1) for b in col["block"]])
    if (row_blk < 0).any():
        raise SystemExit("blocks.json has %d rows whose block has no census point" % int((row_blk < 0).sum()))
    row_students = np.array(col["students"], dtype=float)
    row_drivers = row_students * np.array(col["carPct"], dtype=float) / 100.0
    row_school = np.array(col["school"])
    school_ids = sorted(set(row_school.tolist()))
    names = {s["cds"]: s["name"] for s in sch}

    def share(mask, w):
        return float((w * mask).sum() / w.sum())

    budgets = [{"budgetM": 0, "chunks": [], "centerlineMi": 0.0}] + seg["budgets"]
    out_b = []
    run_max = {}
    for b in sorted(budgets, key=lambda r: r["budgetM"]):
        cov = cov_today.copy()
        for c in b["chunks"]:
            cov[chunk_blocks.get(c, [])] = True
        before, after = share(cov_today, kids), share(cov, kids)
        gain = after - before
        newly = cov[row_blk] & ~cov_today[row_blk]
        gaining = row_drivers * newly
        students_gaining = row_students * newly

        cases = []
        for c in CASES:
            p = pace(c)
            s = min(1.0, gain / (1.0 - before)) if before < 1 else 0.0
            res = {}
            for rule in RULES:
                for draw in DRAWS:
                    share_from_car = CAR_FROM_BIKE if draw == "seville28" else sf_draw
                    yr = {}
                    for t in YEARS:
                        k = min(t, c["holdAfter"])
                        if rule == "relative":
                            dbike = shares["bike"] * (math.exp(s * p["bikeLog"] * k) - 1.0)
                        else:
                            dbike = p["bikePts"] * s * k
                        yr[str(t)] = figures(shares, n_students, dbike, -share_from_car * dbike)
                    res["%s-%s" % (rule, draw)] = yr
            rng = {}
            for t in YEARS:
                vs = sorted(VARIANTS, key=lambda v: (res[v][str(t)]["studentsOutOfCars"], v))
                lo, hi = res[vs[0]][str(t)], res[vs[-1]][str(t)]
                mid = {f: round((lo[f] + hi[f]) / 2.0, 2) for f in ("studentsOutOfCars", "studentsOntoBikes", "carPct", "bikePct")}
                rng[str(t)] = {"low": lo, "high": hi, "middle": mid, "lowVariant": vs[0], "highVariant": vs[-1]}
            cases.append({"case": c["case"], "city": c["city"], "scale": round(s, 4), "variants": res, "range": rng})

        tot_gain = float(gaining.sum())
        tot_students_gaining = float(students_gaining.sum())
        recs = []
        indep_sum = {}
        for j in school_ids:
            m = row_school == j
            g = float(gaining[m].sum())
            w = g / tot_gain if tot_gain > 0 else 0.0
            rec = {"cds": school_cds[j], "name": names.get(school_cds[j], school_cds[j]),
                   "driversGaining": round(g, 1), "weight": round(w, 6)}
            sg = float(students_gaining[m].sum())
            for cs in cases:
                for t in YEARS:
                    k = "%s%d" % (cs["case"], t)
                    v = cs["range"][str(t)]["middle"]["studentsOutOfCars"]
                    rec[k] = round(w * v, 2)
                    # independent: this school's newly covered students, scaled from the rows' 67.9% to all students,
                    # times the citywide students out per newly covered child on census coverage
                    if gain > 0 and tot_students_gaining > 0:
                        est = sg * (n_students / row_students.sum()) * v / (n_students * gain)
                    else:
                        est = 0.0
                    indep_sum[k] = indep_sum.get(k, 0.0) + est
                    mk = (rec["cds"], k)
                    run_max[mk] = max(run_max.get(mk, 0.0), rec[k])
                    rec[k + "RunningMax"] = round(run_max[mk], 2)
            recs.append(rec)
        indep = {"rowsOverCensusGain": round(float(students_gaining.sum() / row_students.sum()) / gain, 4) if gain > 0 else None}
        for cs in cases:
            for t in YEARS:
                k = "%s%d" % (cs["case"], t)
                want = cs["range"][str(t)]["middle"]["studentsOutOfCars"]
                indep[k] = round(indep_sum[k], 1)
                if want and abs(indep_sum[k] - want) / want > INDEP_TOL:
                    raise SystemExit("independent per-school sum %s at $%sM is %.1f, citywide %.1f"
                                     % (k, b["budgetM"], indep_sum[k], want))

        out_b.append({"budgetM": b["budgetM"], "nChunks": len(b["chunks"]), "centerlineMi": b.get("centerlineMi", 0.0),
                      "coverage": {"before": round(before, 4), "after": round(after, 4), "gainPts": round(gain * 100, 2),
                                   "simStudentsBefore": round(share(cov_today[row_blk], row_students), 4),
                                   "simStudentsAfter": round(share(cov[row_blk], row_students), 4)},
                      "driversGaining": round(tot_gain, 1), "cases": cases, "independentSchoolSum": indep,
                      "schools": [r for r in recs if r["driversGaining"] > 0 or any(
                          r[k] > 0 for k in r if k.endswith("RunningMax"))]})

    dc = []
    for d in DRIVING_COST:
        res = {}
        for rule in RULES:
            yr = {}
            for t in YEARS:
                f = min(t, d["years"]) / d["years"]
                if "drivenSwitch" in d:
                    dcar, dbike = -d["drivenSwitch"] * shares["car"] * f, 0.0
                elif rule == "relative":
                    dcar = shares["car"] * ((d["car"][1] / d["car"][0]) ** f - 1.0)
                    dbike = shares["bike"] * ((d["bike"][1] / d["bike"][0]) ** f - 1.0)
                else:
                    dcar = (d["car"][1] - d["car"][0]) * f
                    dbike = (d["bike"][1] - d["bike"][0]) * f
                yr[str(t)] = figures(shares, n_students, dbike, dcar)
            res[rule] = yr
        dc.append({"case": d["case"], "city": d["city"], "rule": d["rule"], "src": d["src"], "url": d["url"],
                   "tag": d["tag"], "rules": res})

    residual = []
    case_meta = []
    for c in CASES:
        p = pace(c)
        case_meta.append({"case": c["case"], "city": c["city"], "label": c["label"], "measure": c["measure"],
                          "span": list(c["span"]), "bikeStartEnd": list(c["bike"]),
                          "carStartEnd": list(c["car"]) if c["car"] else None,
                          "bikeGrowthPctOfItselfPerYr": round((math.exp(p["bikeLog"]) - 1) * 100, 2),
                          "bikePtsPerYr": round(p["bikePts"], 4), "holdAfterYear": c["holdAfter"],
                          "scaleRule": "SF coverage gain / SF's uncovered share today",
                          "src": c["src"], "url": c["url"], "tag": c["tag"], "context": c["context"]})
        if c["car"]:
            measured = c["car"][1] - c["car"][0]
            network = -CAR_FROM_BIKE * (c["bike"][1] - c["bike"][0])
            r = {"city": c["city"], "span": list(c["span"]), "carPtsMeasured": round(measured, 2),
                 "carPtsNetwork": round(network, 2), "carPtsNotNetwork": round(measured - network, 2)}
            if c["city"] == "Seville":
                r["quote"] = SEVILLE_QUOTE
                r["src"] = "Marqués et al. 2014, under Table 3"
                r["url"] = WIT
            residual.append(r)

    return {
        "note": "Written by tools/school-trips/school-city-bracket.py. The simple track of School Trips' mode-shift model: a city "
                "bracket for each budget at each city's pace in percentage points a year, a separate driving-cost row, and "
                "each budget's students out of cars split by school. Shares are percent of modelled students. Car is "
                "single-family car, the all-grade calibrated base (not the Travel Tally's 48.6% grade mix). Coverage is "
                "the share of children 5 to 17 whose home block's census point is within 1,000 ft of an all-ages line.",
        "students": n_students, "today": shares, "carFromBike": {"seville28": CAR_FROM_BIKE, "sfDraw": round(sf_draw, 4)}, "coverFt": COVER_FT,
        "headline": "range.middle", "cases": case_meta, "budgets": out_b, "drivingCost": dc,
        "cityCarResidual": residual,
        "inputs": ["out/school-sim/city.json", "out/school-sim/schools.json", "out/school-sim/segments.json",
                   "site/data/school-sim/today-net.json", "out/school-sim/blocks.json",
                   "data/extract/census-blocks/2020.json", "data/extract/census-dhc/p12-blocks.json"],
    }


def check(d):
    errs = []
    if d["students"] < 40000:
        errs.append("students %d under 40,000" % d["students"])
    if abs(sum(d["today"].values()) - 100) > 0.5:
        errs.append("today's shares sum to %.2f" % sum(d["today"].values()))
    prev = None
    for b in d["budgets"]:
        c = b["coverage"]
        tag = "$%sM" % b["budgetM"]
        if not 0 <= c["before"] <= c["after"] <= 1:
            errs.append("%s coverage out of order" % tag)
        if prev is not None and c["after"] + 1e-9 < prev:
            errs.append("%s covers less than a smaller budget" % tag)
        prev = c["after"]
        by = {cs["case"]: cs for cs in b["cases"]}
        for cs in b["cases"]:
            if sorted(cs["variants"]) != sorted(VARIANTS):
                errs.append("%s %s lacks a variant" % (tag, cs["case"]))
            for t in ("4", "10"):
                for v, yr in cs["variants"].items():
                    y = yr[t]
                    if not 0 <= y["carPct"] <= d["today"]["car"] + 1e-9 or not d["today"]["bike"] - 1e-9 <= y["bikePct"] <= 100:
                        errs.append("%s %s %s year %s out of range" % (tag, cs["case"], v, t))
                r = cs["range"][t]
                if not r["low"]["studentsOutOfCars"] <= r["middle"]["studentsOutOfCars"] <= r["high"]["studentsOutOfCars"]:
                    errs.append("%s %s year %s middle outside its range" % (tag, cs["case"], t))
        for t in ("4", "10"):
            cars = [by[k]["range"][t]["middle"]["carPct"] for k in ("low", "central", "high")]
            # year 10: low >= central >= high. Year 4: Seville grew faster than Paris and then stopped, so only
            # low must be the smallest move.
            if t == "10" and not cars[2] <= cars[1] <= cars[0]:
                errs.append("%s year 10 middles not ordered: %s" % (tag, cars))
            if t == "4" and not cars[0] >= max(cars[1], cars[2]):
                errs.append("%s year 4 low is not the smallest move: %s" % (tag, cars))
        schools = b["schools"]
        for s in schools:
            if not 0 <= s["weight"] <= 1:
                errs.append("%s %s weight %.4f outside 0 to 1" % (tag, s["cds"], s["weight"]))
            if s["driversGaining"] == 0 and s["weight"] > 1e-4:   # under 0.05 drivers rounds to 0 but keeps a tiny weight
                errs.append("%s %s has weight with no gaining drivers" % (tag, s["cds"]))
        for cs in b["cases"]:
            for t in ("4", "10"):
                k = "%s%s" % (cs["case"], t)
                want = cs["range"][t]["middle"]["studentsOutOfCars"]
                got = sum(s[k] for s in schools)
                if want >= 1 and abs(got - want) / want > SPLIT_TOL:
                    errs.append("%s split %s sums to %.1f, citywide %.1f" % (tag, k, got, want))
                ind = b["independentSchoolSum"][k]
                if want >= 1 and abs(ind - want) / want > INDEP_TOL:
                    errs.append("%s independent %s is %.1f, citywide %.1f" % (tag, k, ind, want))
    return errs


def main():
    if "--check" in sys.argv:
        errs = check(read(OUT))
        for e in errs:
            print("FAIL", e)
        print("ok" if not errs else "%d failed" % len(errs))
        sys.exit(1 if errs else 0)
    d = build()
    errs = check(d)
    if errs:
        for e in errs:
            print("FAIL", e)
        raise SystemExit("checks failed; %s left as it was" % OUT)
    wrote = stable.write_json(OUT, d, indent=1, sort_keys=True)
    print("%s %s" % ("wrote" if wrote else "unchanged", os.path.relpath(OUT, ROOT)))
    for b in d["budgets"]:
        c = b["coverage"]
        print("$%3sM cover %.1f%% -> %.1f%%" % (b["budgetM"], c["before"] * 100, c["after"] * 100))
        for cs in b["cases"]:
            parts = []
            for t in ("4", "10"):
                r = cs["range"][t]
                parts.append("y%s %5.0f (%5.0f to %5.0f) car %.2f bike %.1f" % (
                    t, r["middle"]["studentsOutOfCars"], r["low"]["studentsOutOfCars"], r["high"]["studentsOutOfCars"],
                    r["middle"]["carPct"], r["middle"]["bikePct"]))
            print("   %-8s %s | indep %s" % (cs["case"], " | ".join(parts), b["independentSchoolSum"]["%s10" % cs["case"]]))
    for r in d["drivingCost"]:
        for rule in RULES:
            y = r["rules"][rule]
            print("driving cost %-7s %-12s %-8s y4 %5.0f out car %.1f bike %.1f | y10 %5.0f out car %.1f" % (
                r["case"], r["city"], rule, y["4"]["studentsOutOfCars"], y["4"]["carPct"], y["4"]["bikePct"],
                y["10"]["studentsOutOfCars"], y["10"]["carPct"]))
    for r in d["cityCarResidual"]:
        print("residual", r)


if __name__ == "__main__":
    main()
