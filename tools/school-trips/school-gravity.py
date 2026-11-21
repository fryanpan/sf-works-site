#!/usr/bin/env python3
"""Where each school's students are expected to live: a gravity model fit so SFUSD's K-5 students travel as far as SFCTA's School Access Plan, Fig. 5, says, with a flatter curve at schools that get more requests per seat.

    pipeline/venv-step.py tools/school-trips/school-gravity.py            # fit from the held inputs
    pipeline/venv-step.py tools/school-trips/school-gravity.py --update   # first ask CDE and SFUSD for newer files: see INCREMENTAL

Bryan, 2026-10-08, on the school case study: count the school's own students,
not every child nearby, following option B of
notes/school-trips-2026-10/2026-10-08-where-students-attend.md. And: "most
students at a school live nearby, while oversubscribed schools draw from
farther away."

THE MODEL. A child on block b goes to school j with weight
    kids_b x f(d_bj / s_j),   f(x) = (x + D0)^-ALPHA x exp(-BETA x)
where d is the straight-line distance in miles from the block's census point
to the school's CDE point, and s_j the school's reach.
  * Reach s_j = LEVEL_STRETCH[level] x clip((rps_j / median rps of its level) ^ RPS_POWER, 0.5, 2):
    rps is SFUSD's Main Round 2026 requests per seat at the school's entry
    grade (K, 6 or 9), all programs summed. More requests per seat, a flatter
    curve. The mapping and its power are our assumption; SFUSD publishes no
    distance by school. A school with no requests figure (a charter, a private
    school) has rps at its level's median, times CHOICE_STRETCH.
  * The fit: every SFUSD-run school with K-5 students (CDE Census Day
    enrolment, 2025-26), a doubly constrained model (Furness balancing, so each
    block's K-5 children and each school's K-5 enrolment are both met), ALPHA
    and BETA chosen so the citywide trip-length shares match Fig. 5: 50.6%
    under 1 mile, 21.5% at 1 to 2, 27.8% over 2, and the 1.40-mile mean from
    SFUSD's Study Session #2 simulation baseline. Kids are census 2020 DHC P12
    ages 5-9 (K-4); the public-school share (ACS S1401) is one citywide figure,
    so it scales the origins and doesn't move the spread.
  * Middle and high schools: no published distance distribution. We stretch
    the K-5 curve by LEVEL_STRETCH (1.5 for grades 6-8, 2 for 9-12), our
    assumption, and spread each school singly constrained (its enrolment met,
    blocks not).
  * Charter and private schools (KIPP Bayview, the private schools) take
    applicants citywide by lottery or application, so their curve is a further
    CHOICE_STRETCH flatter, our assumption.

INCREMENTAL. Two sources, neither with a change marker:
  cde:census-enrolment-file  CDE's Census Day file, one per school year
      (cdenroll<yy><yy>.txt). --update tries each school year after the one
      held, newest first, up to the year containing today; the first that
      reads replaces the held copy, which keeps county 38's school rows only.
  sfusd:requests-per-seat    the "Main Round <year> Transitional Grade Requests
      per Seat" PDF linked from SFUSD's Annual Assignment Highlights page.
      --update reads the page and fetches the PDF only for a year newer than
      the one held (pdftotext reads it).
A failed read keeps the held copy and records the source as failed. The checks
in pipeline/transportation-quality.py (school-gravity) run after every update.

WRITES data/school-case/enrolment-sf.json (CDE, SF schools),
data/school-case/requests-per-seat.json (SFUSD), data/school-case/gravity.json
(the fit, its match to Fig. 5, each school's reach, and the ZIP check against
SFUSD's dashboard), and site/data/school-gravity.json (the same less the reach,
for About the Model).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime
import html
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import pipeline_state, school_points, stable  # noqa: E402

CITY = os.path.join(ROOT, "data", "school-case", "enrolment-sf.json")
RPS = os.path.join(ROOT, "data", "school-case", "requests-per-seat.json")
OUT = os.path.join(ROOT, "data", "school-case", "gravity.json")
SITE_OUT = os.path.join(ROOT, "site", "data", "school-gravity.json")
CDE_POINTS = os.path.join(ROOT, "data", "extract", "schools", "cde-sf.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
CDE_URL = "https://www3.cde.ca.gov/demo-downloads/census/cdenroll%s.txt"
HIGHLIGHTS = "https://www.sfusd.edu/schools/enroll/student-assignment-policy/annual-assignment-highlights"
SFUSD_DISTRICT = "68478"
GRADES = ["TK", "KN", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
MI = 1609.344
# SFCTA, San Francisco School Access Plan, May 2023, p. 16, Fig. 5 (SFUSD K-5 students), and the
# 1.40-mile mean from SFUSD's School Reorganization Study Session #2 deck, 2026-09-01.
TARGET = {"under1": 50.6, "1to2": 21.5, "over2": 27.8, "meanMi": 1.40}
TARGET_SRC = {
    "bands": {"url": "https://www.sfcta.org/sites/default/files/2024-07/SF_School_Access_Plan_Report_2023-05-04_FINAL.pdf",
              "label": "SFCTA, San Francisco School Access Plan, May 2023, p. 16, Fig. 5", "tag": "[primary — read 2026-10-08]"},
    "mean": {"url": "https://go.boarddocs.com/ca/sfusd/Board.nsf/pfiles/DXE3RY083148/$file/School%20Reorg%20Study%20Session%20%232%20(FINAL%2C%208.28.26).pdf",
             "label": "SFUSD, School Reorganization Study Session #2, 2026-09-01, simulation baseline", "tag": "[primary — read 2026-10-01]"},
}
D0 = 0.1                 # miles: keeps the power term finite at the door
# The mean's weight in the fit's loss, against the three bands' points. At 10 the fit gave 1.46 miles, outside
# school-sim's 0.05 mile check against Stanford's 1.40; at 30 it gives 1.44 with each band within 1.5 points.
MEAN_WEIGHT = 30
LEVEL_STRETCH = {"elementary": 1.0, "middle": 1.5, "high": 2.0}   # our assumption
CHOICE_STRETCH = 2.0     # charter and private schools, our assumption
RPS_POWER = 0.5          # our assumption
RPS_CLIP = (0.25, 2.0)
ENTRY = {"elementary": "K", "middle": "6", "high": "9"}
ENTRY_CDE = {"elementary": "KN", "middle": "06", "high": "09"}  # a school is matched only at a level whose entry grade it enrols
NAME_STOP = {"es", "ms", "hs", "elementary", "middle", "high", "school", "k", "8", "k8", "academy", "the", "of", "at",
             "and", "sch", "ees", "for", "sf", "fec", "academic", "international"}


# -- fetching ------------------------------------------------------------------

def _get(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()


def year_label(y):
    return "%d-%02d" % (y, (y + 1) % 100)


def current_start(today):
    return today.year if today.month >= 8 else today.year - 1


def parse_cde(raw, year):
    """County 38's school rows, all students, from one Census Day file."""
    lines = raw.decode("latin-1").splitlines()
    head = lines[0].split("\t")
    ix = {h: i for i, h in enumerate(head)}
    out = {}
    for L in lines[1:]:
        r = L.split("\t")
        if len(r) < len(head) or r[ix["AggregateLevel"]] != "S" or r[ix["CountyCode"]] != "38" or r[ix["ReportingCategory"]] != "TA":
            continue
        cds = "38%s%s" % (r[ix["DistrictCode"]], r[ix["SchoolCode"]])
        g = {k: int(r[ix["GR_" + k]] or 0) for k in GRADES}
        out[cds] = {"name": r[ix["SchoolName"]], "district": r[ix["DistrictCode"]], "charter": r[ix["Charter"]] == "Y",
                    "total": int(r[ix["TOTAL_ENR"]] or 0), "grades": g}
    return {"year": year, "url": CDE_URL % (year[2:4] + year[5:7]), "schools": dict(sorted(out.items()))}


def update_city(today):
    held = json.load(open(CITY)) if os.path.exists(CITY) else None
    have = int(held["year"][:4]) if held else 2024
    for y in range(current_start(today), have, -1):
        lab = year_label(y)
        try:
            raw = _get(CDE_URL % (lab[2:4] + lab[5:7]))
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "code", None) == 404:
                continue
            return held, "CDE %s: %s" % (lab, exc)
        if not raw.startswith(b"AcademicYear"):
            continue  # not posted: the site answers with a page, not the file
        got = parse_cde(raw, lab)
        got["read"] = today.isoformat()
        got["tag"] = "[primary — read %s]" % got["read"]
        stable.write_json(CITY, got, indent=1)
        print("  CDE Census Day %s: %d SF schools" % (lab, len(got["schools"])))
        return got, None
    return held, None


def parse_rps(text):
    """Rows of the requests-per-seat table: grade, program, school, requests, seats."""
    rx = re.compile(r"^\s*(TK|K|\d+)\s+(\S+)\s+(.+?)\s{2,}(.+?)\s{2,}([\d.]+|-)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+|-)\s*$")
    rows = []
    for L in text.replace("​", "").splitlines():
        m = rx.match(L)
        if not m:
            continue
        rows.append({"grade": m.group(1), "program": m.group(2), "school": m.group(3).strip(),
                     "requests": int(m.group(6).replace(",", "")),
                     "seats": None if m.group(8) == "-" else int(m.group(8).replace(",", ""))})
    return rows


def update_rps(today):
    held = json.load(open(RPS)) if os.path.exists(RPS) else None
    try:
        page = _get(HIGHLIGHTS).decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return held, "SFUSD highlights page: %s" % exc
    found = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).replace("\u200b", "")).strip()
        mm = re.match(r"Main Round (\d{4}) Transitional Grade Requests per Seat", txt)
        fid = re.search(r"/d/([\w-]+)", m.group(1))
        if mm and fid:
            found.append((int(mm.group(1)), fid.group(1), txt))
    if not found:
        return held, "no requests-per-seat link on the highlights page"
    year, fid, label = max(found)
    if held and held["year"] >= year:
        return held, None
    try:
        pdf = _get("https://drive.google.com/uc?export=download&id=%s" % fid)
        assert pdf.startswith(b"%PDF"), "not a PDF (a login page?)"
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf)
            f.flush()
            text = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True).stdout.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        return held, "requests per seat %d: %s" % (year, exc)
    rows = parse_rps(text)
    got = {"year": year, "label": label, "url": "https://drive.google.com/file/d/%s/view" % fid, "via": HIGHLIGHTS,
           "read": today.isoformat(), "tag": "[primary — read %s]" % today.isoformat(), "rows": rows}
    stable.write_json(RPS, got, indent=1)
    print("  SFUSD requests per seat %d: %d rows" % (year, len(rows)))
    return got, None


# -- the curve -----------------------------------------------------------------

def curve(x, alpha, beta):
    import numpy
    return numpy.power(x + D0, -alpha) * numpy.exp(-beta * x)


def _tokens(name):
    t = re.sub(r"\(([^)]*)\)", r" \1 ", name.lower()).replace("san francisco", " ")
    return set(w for w in re.split(r"[^a-z0-9]+", t) if w and w not in NAME_STOP)


def rps_by_school(rps):
    """{(normalized tokens tuple, entry grade): requests per seat}, all programs summed."""
    agg = {}
    for r in rps["rows"]:
        if not r["seats"]:
            continue
        k = (r["school"], r["grade"])
        a = agg.setdefault(k, [0, 0])
        a[0] += r["requests"]
        a[1] += r["seats"]
    return {k: v[0] / float(v[1]) for k, v in agg.items() if v[1] > 0}


def match_rps(name, grade, table):
    """The requests-per-seat school whose name best matches a CDE name, at an entry grade, or None."""
    want = _tokens(name)
    best, score = None, 0.0
    for (sch, g), v in table.items():
        if g != grade:
            continue
        have = _tokens(sch)
        if not have or not want:
            continue
        sc = len(want & have) / float(max(len(have), len(want)))
        if sc > score:
            best, score = (sch, v), sc
    return best if score >= 0.5 else None


def reaches(city, rps):
    """Each SFUSD-run school's reach by level, from requests per seat; plus each level's median."""
    table = rps_by_school(rps)
    out, med = {}, {}
    for lvl in ENTRY:
        vals = []
        for cds, s in city["schools"].items():
            if s["district"] != SFUSD_DISTRICT or s["charter"] or not s["grades"][ENTRY_CDE[lvl]]:
                continue
            m = match_rps(s["name"], ENTRY[lvl], table)
            if m:
                out.setdefault(cds, {})[lvl] = {"rps": round(m[1], 2), "rpsSchool": m[0]}
                vals.append(m[1])
        vals.sort()
        med[lvl] = vals[len(vals) // 2] if vals else 1.0
    for cds, by in out.items():
        for lvl, r in by.items():
            r["stretch"] = round(stretch_of(lvl, r["rps"], med), 3)
    return out, {k: round(v, 2) for k, v in med.items()}


def stretch_of(level, rps, med, choice=False):
    if rps is None:
        s = 1.0
    else:
        s = min(RPS_CLIP[1], max(RPS_CLIP[0], (rps / med[level]) ** RPS_POWER))
    return LEVEL_STRETCH[level] * s * (CHOICE_STRETCH if choice else 1.0)


def grade_set(g):
    """"K-8" → {0, ..., 8}; TK and PreK read as K."""
    lo, hi = str(g).replace("PreK", "K").replace("TK", "K").split("-")
    f = lambda v: 0 if v.strip().upper() in ("K", "PK", "P") else int(v)  # noqa: E731
    return set(range(f(lo), f(hi) + 1))


# -- blocks and schools ------------------------------------------------------------

# Children of each level's ages per block, from census 2020 P12's age bands:
# a grade's age is its number plus 5, and a10_14 is split a fifth per year,
# so K-5 is ages 5 to 10, 6-8 ages 11 to 13, 9-12 ages 14 to 17.
LEVEL_KIDS = {"elementary": (("a5_9", 1.0), ("a10_14", 0.2)), "middle": (("a10_14", 0.6),),
              "high": (("a10_14", 0.2), ("a15_17", 1.0))}


def level_kids(b, level):
    return sum(b[k] * w for k, w in LEVEL_KIDS[level])


def blocks():
    kids = {r["geoid"]: r for r in json.load(open(os.path.join(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")))["records"]}
    pts = {r["geoid"]: r for r in json.load(open(os.path.join(ROOT, "data", "extract", "census-blocks", "2020.json")))["records"]}
    out = []
    for gid in sorted(kids):
        k = kids[gid]
        if k["a5_9"] + k["a10_14"] + k["a15_17"] == 0:
            continue
        p = pts[gid]
        out.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "a5_9": k["a5_9"], "a10_14": k["a10_14"], "a15_17": k["a15_17"]})
    return out


def _xy(lon, lat):
    lat0 = math.radians(37.76)
    return (math.radians(lon) * math.cos(lat0) * 6371008.8, math.radians(lat) * 6371008.8)


def dist_mi(blks, lon, lat):
    import numpy
    bx = numpy.array([_xy(b["lon"], b["lat"])[0] for b in blks])
    by = numpy.array([_xy(b["lon"], b["lat"])[1] for b in blks])
    x, y = _xy(lon, lat)
    return numpy.hypot(bx - x, by - y) / MI


def k5_schools(city):
    """SFUSD-run schools with K-5 students and a CDE point: (cds, name, lon, lat, K-5 enrolment)."""
    pts = {r["cds"]: r for r in school_points.records(CDE_POINTS) if r.get("lon") and r.get("lat")}
    out, missing = [], []
    for cds, s in city["schools"].items():
        if s["district"] != SFUSD_DISTRICT or s["charter"]:
            continue
        k5 = sum(s["grades"][g] for g in ("KN", "01", "02", "03", "04", "05"))
        if k5 <= 0:
            continue
        p = pts.get(cds)
        if not p:
            missing.append(s["name"])
            continue
        out.append((cds, s["name"], p["lon"], p["lat"], k5))
    return out, missing


def furness(O, D, F, iters=200):
    """Doubly constrained trips T = a_i O_i b_j D_j F_ij, rows summing to O and columns to D."""
    import numpy
    b = numpy.ones(F.shape[1])
    for _ in range(iters):
        a = 1.0 / numpy.maximum(F @ (b * D), 1e-300)
        b = 1.0 / numpy.maximum((a * O) @ F, 1e-300)
    return (a * O)[:, None] * F * (b * D)[None, :]


def bands_of(T, d):
    import numpy
    tot = T.sum()
    return {"under1": 100 * T[d < 1].sum() / tot, "1to2": 100 * T[(d >= 1) & (d < 2)].sum() / tot,
            "over2": 100 * T[d >= 2].sum() / tot, "meanMi": float((T * d).sum() / tot)}


def setup(city, rps):
    import numpy
    blks = blocks()
    sch, missing = k5_schools(city)
    reach, med = reaches(city, rps)
    O = numpy.array([level_kids(b, "elementary") for b in blks], dtype=float)
    D = numpy.array([s[4] for s in sch], dtype=float)
    O *= D.sum() / O.sum()
    d = numpy.stack([dist_mi(blks, s[2], s[3]) for s in sch], axis=1)
    st = numpy.array([(reach.get(s[0], {}).get("elementary") or {}).get("stretch") or stretch_of("elementary", None, med) for s in sch])
    return blks, sch, missing, reach, med, O, D, d, st


def matrix(alpha, beta, O, D, d, st):
    return furness(O, D, curve(d / st[None, :], alpha, beta))


def fit(O, D, d, st):
    from scipy.optimize import minimize

    def loss(p):
        a, b = p
        if a < 0 or b < 0:
            return 1e9
        r = bands_of(matrix(a, b, O, D, d, st), d)
        return sum((r[k] - TARGET[k]) ** 2 for k in ("under1", "1to2", "over2")) + (MEAN_WEIGHT * (r["meanMi"] - TARGET["meanMi"])) ** 2
    best = None
    for a0, b0 in ((1.0, 0.5), (0.5, 1.0), (1.5, 0.1), (0.2, 1.5)):
        r = minimize(loss, [a0, b0], method="Nelder-Mead", options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 400})
        if best is None or r.fun < best.fun:
            best = r
    return float(best.x[0]), float(best.x[1]), float(best.fun)


# -- for tools/school-trips/school-case.py ------------------------------------------------------

class Model(object):
    """The fitted curve, each school's reach, and the doubly constrained K-5 matrix, for spreading a school's enrolment."""

    def __init__(self):
        import numpy
        g = json.load(open(OUT))
        self.g = g
        self.alpha, self.beta = g["fit"]["alpha"], g["fit"]["beta"]
        self.city = json.load(open(CITY))
        rps = json.load(open(RPS))
        self.blks, self.sch, _m, self.reach, self.med, O, D, d, st = setup(self.city, rps)
        T = matrix(self.alpha, self.beta, O, D, d, st)
        self.k5 = {s[0]: T[:, j] / T[:, j].sum() for j, s in enumerate(self.sch)}
        self.index = {b["geoid"]: i for i, b in enumerate(self.blks)}
        self.numpy = numpy

    def spread(self, cds, lon, lat, span_students, choice):
        """Expected students per block (in self.blks order) for a school, given its students by level.

        span_students: {"elementary": n, "middle": n, "high": n}. An SFUSD
        school's K-5 students follow its column of the doubly constrained
        matrix; every other level, or school, is singly constrained."""
        np = self.numpy
        d = dist_mi(self.blks, lon, lat)
        out = np.zeros(len(self.blks))
        how = {}
        for lvl, n in span_students.items():
            if n <= 0:
                continue
            if lvl == "elementary" and cds in self.k5 and not choice:
                out += n * self.k5[cds]
                how[lvl] = {"method": "doubly", "stretch": (self.reach.get(cds, {}).get(lvl) or {}).get("stretch")}
                continue
            r = (self.reach.get(cds, {}) if cds else {}).get(lvl)
            s = stretch_of(lvl, r["rps"] if r and not choice else None, self.med, choice=choice)
            kids = np.array([level_kids(b, lvl) for b in self.blks], dtype=float)
            w = kids * curve(d / s, self.alpha, self.beta)
            out += n * w / w.sum()
            how[lvl] = {"method": "singly", "stretch": round(s, 3), "rps": r["rps"] if r and not choice else None}
        return out, how


# SFUSD Public Data Dashboard 2025-26, "Enrollment & Residence by Group", the
# Zip Code Table for each school and grade span, every student group: the top
# five home ZIPs with counts and the group's total. Read 2026-10-08 through the
# dashboard's own Tableau session (downloads are off), by a research agent
# whose scripts are in the session scratchpad. [primary — read 2026-10-08]
DASHBOARD = {
    "url": "https://public.tableau.com/app/profile/san.francisco.unified.school.district/viz/SFUSDPublicDataDashboard2025-26/Story1",
    "read": "2026-10-08", "tag": "[primary — read 2026-10-08]",
    "schools": {
        "carmichael|elementary": {"total": 261, "top": [["94103", 166], ["94102", 31], ["94105", 22], ["94124", 21], ["94158", 21]]},
        "carmichael|middle": {"total": 137, "top": [["94103", 68], ["94102", 24], ["94124", 20], ["94158", 14], ["94107", 11]]},
        "burton|high": {"total": 921, "top": [["94134", 299], ["94124", 274], ["94112", 263], ["94110", 52], ["94132", 33]]},
        "june-jordan|high": {"total": 141, "top": [["94112", 68], ["94124", 34], ["94110", 14], ["94134", 14], ["94132", 11]]},
        "balboa|high": {"total": 1026, "top": [["94112", 516], ["94134", 192], ["94124", 182], ["94110", 79], ["94132", 57]]},
    },
}
ZCTA = os.path.join(ROOT, "data", "extract", "census-zcta", "sf-2020.json")


def _in_ring(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def block_zips(blks):
    z = json.load(open(ZCTA))["zctas"]
    polys = {k: (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]) for k, g in z.items()}
    out = []
    for b in blks:
        hit = None
        for k, ps in polys.items():
            if any(_in_ring(b["lon"], b["lat"], p[0]) and not any(_in_ring(b["lon"], b["lat"], h) for h in p[1:]) for p in ps):
                hit = k
                break
        out.append(hit)
    return out


# SFUSD's 58 elementary attendance areas, DataSF e6tr-sxwg. Bryan, 2026-10-08
# "Use SFUSD data to guess at what fraction of
# students come from the school's designated neighborhood area (if it has one)
# vs. city wide, and for citywide, spread by distance." So an attendance-area
# school's elementary students are a mix: a share spread over its area's blocks
# by their children, the rest over the city by the distance curve. The share is
# fit per school in tools/school-trips/school-sim.py against the dashboard's home ZIPs.
# Middle and high schools have no attendance area (feeders are a tiebreaker,
# not an area), so they're citywide only.
ATTENDANCE_ID = "e6tr-sxwg"
# DataSF's synergy_na is SFUSD's own school name, the dashboard's spelling,
# except one typo.
AREA_ALIAS = {"Malcolm X Adademy ES": "Malcolm X Academy ES"}


def attendance_areas():
    """[(SFUSD school name as the dashboard spells it, polygons)], and the read's provenance tag."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sfdata
    r = sfdata.fetch(ATTENDANCE_ID, order=":id", floor=50)
    out = []
    for row in r.rows:
        g = row["the_geom"]
        nm = row.get("synergy_na") or row.get("sch_lng_na")
        out.append((AREA_ALIAS.get(nm, nm), g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]))
    return out, getattr(r, "tag", "[DataSF e6tr-sxwg]")


def block_areas(blks, areas):
    """Each block's attendance area index into areas (by its census point), or None."""
    out = []
    for b in blks:
        hit = None
        for k, (_nm, ps) in enumerate(areas):
            if any(_in_ring(b["lon"], b["lat"], p[0]) and not any(_in_ring(b["lon"], b["lat"], h) for h in p[1:]) for p in ps):
                hit = k
                break
        out.append(hit)
    return out


def zip_check(model):
    """The model's share of each school's students in the dashboard's top five home ZIPs, against the dashboard's."""
    drop = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "data", "school-case", "dropoff.json")))["schools"]}
    enrol = json.load(open(os.path.join(ROOT, "data", "school-case", "enrolment.json")))["schools"]
    zips = block_zips(model.blks)
    out = {}
    for key, dash in sorted(DASHBOARD["schools"].items()):
        sid, lvl = key.split("|")
        s, en = drop[sid], enrol[sid]
        arr, _how = model.spread(en["cds"], s["door"]["lon"], s["door"]["lat"], {lvl: 1.0}, False)
        by = {}
        for z, v in zip(zips, arr):
            by[z or "none"] = by.get(z or "none", 0.0) + float(v)
        # The dashboard's figures are counts; its "total" is the five ZIPs' sum, so the
        # share is of the school's CDE enrolment in those grades.
        gs = {"elementary": ("TK", "K", "1", "2", "3", "4", "5"), "middle": ("6", "7", "8"), "high": ("9", "10", "11", "12")}[lvl]
        den = en["total"] * sum(en["grade_pct"].get(g, 0) for g in gs) / 100.0
        rows = [{"zip": z, "count": n, "dashboard": round(100.0 * n / den, 1), "model": round(100.0 * by.get(z, 0.0), 1)} for z, n in dash["top"]]
        mtop = sorted(((v, z) for z, v in by.items() if z != "none"), reverse=True)[:5]
        out[key] = {"rows": rows, "enrolled": round(den), "modelTop": [z for _v, z in mtop],
                    "sameTop5": len({z for z, _n in dash["top"]} & {z for _v, z in mtop}),
                    "top5Dashboard": round(sum(r["dashboard"] for r in rows), 1), "top5Model": round(sum(r["model"] for r in rows), 1)}
    return out


def main():
    import numpy
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="ask CDE and SFUSD for newer files first")
    a = ap.parse_args()
    today = datetime.date.today()
    if a.update or not os.path.exists(CITY):
        city, err = update_city(today)
        pipeline_state.refreshed("cde:census-enrolment-file", [err] if err else [], version=city and city["year"],
                                 detail="newer school years asked for")
        if err:
            print("  CDE re-read failed, held copy kept: %s" % err)
    if a.update or not os.path.exists(RPS):
        rps, err = update_rps(today)
        pipeline_state.refreshed("sfusd:requests-per-seat", [err] if err else [], version=rps and str(rps["year"]),
                                 detail="the highlights page's newest Main Round asked for")
        if err:
            print("  SFUSD requests-per-seat re-read failed, held copy kept: %s" % err)
    city = json.load(open(CITY))
    rps = json.load(open(RPS))
    blks, sch, missing, reach, med, O, D, d, st = setup(city, rps)
    alpha, beta, loss = fit(O, D, d, st)
    T = matrix(alpha, beta, O, D, d, st)
    got = bands_of(T, d)
    # The same curve with every reach 1, to show what the requests-per-seat reach changes.
    flat = bands_of(matrix(alpha, beta, O, D, d, numpy.ones_like(st)), d)
    matched = sum(1 for s in sch if "elementary" in reach.get(s[0], {}))
    out = {
        "note": "Distance curve for where each school's students live, written by tools/school-trips/school-gravity.py. "
                "f(x) = (x + d0)^-alpha exp(-beta x), x = straight-line miles / the school's reach.",
        "fit": {"alpha": round(alpha, 4), "beta": round(beta, 4), "d0": D0, "loss": round(loss, 4),
                "got": {k: round(float(v), 2) for k, v in got.items()}, "target": TARGET, "targetSrc": TARGET_SRC,
                "withoutReach": {k: round(float(v), 2) for k, v in flat.items()},
                "schools": len(sch), "students": int(D.sum()), "unplaced": sorted(missing), "rpsMatched": matched},
        "assume": {"levelStretch": LEVEL_STRETCH, "choiceStretch": CHOICE_STRETCH, "rpsPower": RPS_POWER, "rpsClip": list(RPS_CLIP),
                   "entry": ENTRY},
        "rpsMedian": med,
        "inputs": {"cde": {k: city[k] for k in ("year", "url", "read", "tag")},
                   "rps": {k: rps[k] for k in ("year", "label", "url", "via", "read", "tag")}},
        "reach": {k: reach[k] for k in sorted(reach)},
    }
    stable.write_json(OUT, out, indent=1, ensure_ascii=False)
    out["zipCheck"] = {"source": {k: DASHBOARD[k] for k in ("url", "read", "tag")}, "zcta": json.load(open(ZCTA))["url"],
                       "schools": zip_check(Model())}
    stable.write_json(OUT, out, indent=1, ensure_ascii=False)
    # The site's copy, for About the Model: everything but each school's reach.
    stable.write_json(SITE_OUT, {k: v for k, v in out.items() if k != "reach"}, indent=1, ensure_ascii=False)
    for k, v in out["zipCheck"]["schools"].items():
        print("  zip check %s: top five %.0f%% on the dashboard, %.0f%% in the model, %d of 5 the same" % (
            k, v["top5Dashboard"], v["top5Model"], v["sameTop5"]))
    print("  gravity: alpha %.3f beta %.3f; got %s against %s (%d schools, %d with requests per seat)" % (
        alpha, beta, {k: round(float(v), 2) for k, v in got.items()}, TARGET, len(sch), matched))


if __name__ == "__main__":
    main()
