#!/usr/bin/env python3
"""Where people are hurt on San Francisco's streets, and whether the city's safety fixes moved the reported injury
counts: the data behind the injury map embed (site/src/injury-page.mjs).

    ~/.venvs/sf-works-geo/bin/python tools/street-safety/injury-map.py      # writes site/data/injury-map.json

Bryan, 2026-10-21: "please get high injury network page up there as a feature flagged addition to the mobility
section", and the same day: "make it possible to look at where injuries happened near a specific school, and share a
link around for what you're looking at".

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build step, like school-injury-points.py: it reads the cached DataSF
queries through lib/sfdata.py and the tracked extracts named below, and has no --update of its own. It is in
pipeline/transportation-update.py after project-record, whose projects.json it reads. Its output names every source's
read date under "source" and map.fixes.fetched, so the page dates its figures from the data, not the build.

THE SCHOOL PICKER. For each of the School Trips tool's schools (site/data/school-sim/index.json), its grounds
(lib/school_grounds.py, measured from the edge of the grounds as state law measures a school zone), those
grounds grown by 500 ft and by a quarter mile (1,320 ft), and the indices into map.kidPoints of the kids inside that
quarter-mile ring as drawn; map.kidSevere holds the indices of the kids severely hurt or killed. A kid is a victim 5 to
18 hurt on a weekday from 6 AM to 6 PM, August 1 to May 31, inside
the page's five-year window, which runs September to August, so its first school year loses August and its last
August belongs to the next school year. June and July are out;
holidays inside August to May stay in. The rule is lib/school_window.py's, the one definition every count of
kids hurt near schools uses (Bryan, 2026-10-21: "keep it to school hours (6AM to 6PM) on weekdays during the school
year. And make the school year from August to end of May").

WHERE PEOPLE ARE HURT. Every injured or killed victim in DataSF nwes-mmgh (police crash reports) in the five years to
the data's last full month, snapped to the nearest active street centerline in DataSF 3psu-pn9h. A crash the report
places at an intersection (`intersection` starts "Intersection") counts for the biggest street meeting there, using
the centerline layer's own class code (1 freeway, 2 major street, 3 arterial, 4 collector, 5 residential, 6 ramp,
0 other); a midblock crash takes its own street's class. "Main roads" are classes 2, 3 and 4; the few victims the node
rule puts on a freeway or ramp are reported separately. On the High Injury
Network means within ON_FT of SFMTA's 2022 HIN centerline (data/extract/access/hin-2022.json).

DID THE FIXES WORK. For each intervention with a place and a date (the 33 speed camera locations from DataSF
d5uh-bk84, 31 quick-build or near-term corridors from SFMTA's Safe Streets Evaluation Program reports and project
pages, and the Tenderloin daylighting of 2015) we count reported injuries in equal windows before and after the start
date, at the site and in the site plus two blocks: the site's segments and end nodes, then every segment at a site
node (the next block along the street and the first block of each cross street) and, from those segments' far ends,
the next segment of the same street (the second block along each). Freeway and paper-street centerlines are left out
of the snapping, because the crash data excludes freeway crashes and a point under a freeway is a surface crash.
Pooled rows are Mantel-Haenszel ratios over locations with the Robins-Breslow-Greenland interval. Windows are capped at WINDOW_YEARS each
side (SFMTA's own evaluations use up to three years before). The comparison is the rest of the city, every injury
outside the site and its two blocks, over the same two windows. The result is a rate ratio of ratios with a Poisson
95% interval: exp(log((a/b)/(c/d)) ± 1.96·sqrt(1/a + 1/b + 1/c + 1/d)), with 0.5 added to each count when any is 0.
Start dates: a camera starts on its first day in d5uh-bk84, which begins 2025-04-01 (SFMTA says the program launched
2025-03-20 and all cameras were issuing warnings by 2025-06-06); a corridor starts the day after the completion period SFMTA states (a year ends 31 Dec, a
season at its end, a month at its end); the Tenderloin daylighting starts 2015-03-20, the day SFMTA wrote that it had
"recently improved 80 intersections in the Tenderloin with daylighting".

WHY AND WHERE ON THE BLOCK. The same five-year victims, main roads (classes 2, 3, 4) against residential (5), by the
report's primary collision factor and by where on the block. Cause is the victim row's own `vz_pcf_code`, the
California Vehicle Code section the officer names as the crash's primary collision factor (one per crash, repeated on
each victim). It is grouped by cause() into plain causes of our own: unsafe speed, red light, not yielding in a
crosswalk, not yielding while turning left, stop sign, unsafe turn or lane change, following too closely,
driving under the influence, pedestrian violations,
every other code, and unknown or not stated (a null code, or one whose vz_pcf_description is "Unknown"). Place is the report's
`intersection` field (`Intersection <= 20ft`, `Intersection Rear End <= 150ft`, `Midblock > 20ft`), with a midblock
crash split by `distance`, the report's offset in feet from the secondary (cross) road, at 150 ft.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, datetime, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
OUT = os.path.join(ROOT, "site", "data", "injury-map.json")
QUARTER_FT, ZONE_FT = 1320, 500
import numpy as np
import sfdata
from lib import school_window

ON_FT, NODE_FT, SNAP_FT, PAIR_FT, EDGE_FT, CELL, CAM_PAIR_FT = 60, 50, 150, 160, 10, 500, 3000
WINDOW_YEARS = 3
RING_HOPS = 8          # the surrounding blocks, hops 3 to 8 from the site's nodes, a second comparison group
GROUPS = ("all", "severe", "ped", "bike")
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
MAIN = {"2", "3", "4"}
CLASS = {"1": "Freeway", "2": "Major street or highway", "3": "Arterial street", "4": "Collector street",
         "5": "Residential street", "6": "Freeway ramp", "0": "Other (private, paper street)"}
SEVERE = {"Severe Injury", "Fatal Injury"}
D = datetime.date

# Cause groups, in display order (the page re-sorts by count). Codes are matched on the section number
# and, where a section mixes driver and pedestrian duties, its subdivision.
CAUSES = [("speed", "Unsafe speed"), ("red", "Running a red light"), ("xwalk", "Not yielding to a person in a crosswalk"),
          ("left", "Not yielding while turning left"), ("stop", "Running a stop sign"),
          ("turn", "Unsafe turn or lane change"), ("follow", "Following too closely"), ("dui", "Driving under the influence"),
          ("ped", "Pedestrian violation"), ("other", "Every other cause"),
          ("unknown", "Unknown or not stated")]
PLACES = [("ix", "At the intersection, within 20 ft"), ("mid", "Midblock"),
          ("unknown", "Not stated")]


def cause(code):
    """Group a vz_pcf_code. 22350 is the basic speed law; 22348 to 22356 are the other speed sections. 21950(a) and
    (c) are the driver's duty at a crosswalk, 21950(b) the pedestrian's. 21453(a) to (c) bind drivers and bicyclists
    at a red signal, 21453(d) pedestrians. 21801 is the left or U turn yield [inference]."""
    c = (code or "").strip()
    # The city's own vz_pcf_description reads "Unknown" for these CHP labels too, so they count as not stated.
    if not c or c.lower() in ("unknown", "na", "other than driver", "other improper driving"):
        return "unknown"
    m = re.match(r"(\d+(?:\.\d+)?)(?:\(([a-z])\))?", c)
    if not m:
        return "other"           # "Other Than Driver", "Other Improper Driving", local ordinances like 7.2.12TC
    sec, sub = m.group(1), m.group(2)
    if sec == "22350" or (sec.isdigit() and 22348 <= int(sec) <= 22356):
        return "speed"
    if sec == "21453":
        return "ped" if sub == "d" else "red"
    if sec == "21950":
        return "ped" if sub in ("b", "e") else "xwalk"     # the city groups 21950(e)(2) with (b), a pedestrian duty
    if sec == "21801":
        return "left"
    if sec == "22450":
        return "stop"
    if sec == "22107":
        return "turn"
    if sec == "21703":
        return "follow"
    if sec in ("23152", "23153"):
        return "dui"
    if sec in ("21954", "21955", "21456") and not (sec == "21954" and sub == "b"):
        return "ped"
    return "other"


# Who the officer marked at fault, by mode. One group per person hurt, from the at-fault party in their crash
# (DataSF 8gtc-pjc6, at_fault = "Yes"). Motorcycles and mopeds go with cars and trucks, as people driving a motor
# vehicle; a hit-and-run driver whose vehicle is unknown does too. "Public Transit Authority" is the CHP vehicle type
# for a transit vehicle, which in San Francisco is mostly Muni (its makes are New Flyer buses, LRVs, cable cars).
FAULTS = [("drive", "Someone driving a car, truck or motorcycle"), ("transit", "A Muni or other transit driver"),
          ("bike", "Someone on a bike"), ("walk", "Someone walking"), ("scoot", "Someone on a scooter or board"),
          ("other", "Other or not stated"), ("none", "No one marked at fault")]
MICRO = {"Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
BIKE = {"Bicycle", "Electric Bicycle", "Motorized Bicycle"}
NOT_STATED = {None, "", "Not Stated", "Passengers", "Misc. Non-Motor Vehicle", "Pedestrian"}   # "Misc. Motor Vehicle" is a motor vehicle


def mode(p):
    """Mode of one party from party_type and stwd_vehicle_type."""
    t, v = p.get("party_type"), p.get("stwd_vehicle_type")
    if t == "Pedestrian" or v == "Pedestrian":
        return "walk"
    if v in BIKE or t == "Bicyclist":
        return "bike"
    if v in MICRO:
        return "scoot"
    if v == "Public Transit Authority":
        return "transit"
    if t == "Parked Vehicle":
        return "other"     # nobody was driving it (mostly a door opened into traffic)
    if t == "Driver":
        return "drive"     # any vehicle a driver was in, including one whose type is not stated
    if v in NOT_STATED:
        return "other"
    return "drive" if v else "other"   # an "Other" party in a car, motorcycle or the like


def faults():
    """case_id -> the at-fault parties' modes, one per distinct party (the table repeats two party rows once)."""
    P = sfdata.fetch("8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,at_fault,stwd_vehicle_type", floor=100000)
    by, allp = collections.defaultdict(dict), collections.defaultdict(dict)
    for p in P.rows:
        m = (mode(p), p.get("stwd_vehicle_type"), p.get("party_type"))
        allp[p["case_id_pkey"]][p.get("party_number_ckey")] = m
        if p.get("at_fault") == "Yes":
            by[p["case_id_pkey"]][p.get("party_number_ckey")] = m
    return by, allp, P.fetched_on.isoformat()


def motor(m):
    """A motor vehicle party: someone driving, a transit vehicle, or a parked vehicle (its door, or the car itself)."""
    return m[0] in ("drive", "transit") or m[2] == "Parked Vehicle"


def place(ix, dist):
    """Where on the block, from the report's `intersection` field and, for midblock, its `distance` in feet."""
    if ix == "Intersection <= 20ft":
        return "ix"
    if ix == "Intersection Rear End <= 150ft":   # counted as midblock (Bryan)
        return "mid"
    if ix == "Midblock > 20ft":   # one midblock group (Bryan)
        return "mid"
    return "unknown"


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


def norm(s):
    """Centerline spelling: no apostrophes, zero-padded numbered streets, BAY SHORE."""
    s = s.upper().replace("'", "").replace(".", "").strip()
    s = re.sub(r"\b(\d)(ST|ND|RD|TH)\b", r"0\1\2", s)
    s = s.replace("BAYSHORE", "BAY SHORE").replace("GREAT HIGHWAY", "GREAT HWY")
    return re.sub(r"\s+", " ", s)


# Corridors: (label, street, from, to, after-window start, SFMTA's stated completion, source). The start is the day after
# the stated period. "Both carriageways" of a divided street come in through PAIR_FT. Sources are quoted in build.mjs.
CORRIDORS = [
    ("Folsom St quick-build", "FOLSOM ST", "2ND ST", "5TH ST", "2019-01-01", "installed 2018", "ssep2022"),
    ("Turk St safety project", "TURK ST", "MARKET ST", "POLK ST", "2018-07-01", "spring 2018", "ssep2022"),
    ("8th St safety project", "8TH ST", "MARKET ST", "TOWNSEND ST", "2019-08-01", "May 2017 to July 2019", "ssep2022"),
    ("Valencia St pilot bikeway", "VALENCIA ST", "MARKET ST", "15TH ST", "2019-02-01", "January 2019", "sfgov2019"),
    ("Taylor St quick-build", "TAYLOR ST", "MARKET ST", "SUTTER ST", "2019-10-01", "summer 2019", "ssep2022"),
    ("6th St quick-build", "6TH ST", "MARKET ST", "FOLSOM ST", "2019-10-01", "September 2019", "ssep2022"),
    ("Indiana St quick-build", "INDIANA ST", "23RD ST", "CESAR CHAVEZ ST", "2019-11-01", "October 2019", "ssep2022"),
    ("Howard St quick-build", "HOWARD ST", "3RD ST", "THE EMBARCADERO", "2020-04-01", "winter 2020", "howard"),
    ("Brannan St quick-build", "BRANNAN ST", "THE EMBARCADERO", "DIVISION ST", "2020-04-01", "early winter 2020", "brannan"),
    ("Fell St protected bike lane", "FELL ST", "BAKER ST", "SHRADER ST", "2020-04-01", "early 2020", "ssep2022"),
    ("Townsend St corridor", "TOWNSEND ST", "3RD ST", "8TH ST", "2020-07-01", "spring 2020", "townsend"),
    ("California St quick-build", "CALIFORNIA ST", "ARGUELLO BLVD", "18TH AVE", "2020-10-01", "summer 2020", "ssep2022"),
    ("Beale St quick-build", "BEALE ST", "MARKET ST", "HOWARD ST", "2021-01-01", "December 2020", "beale"),
    ("Central Embarcadero quick-build", "THE EMBARCADERO", "MISSION ST", "BROADWAY", "2021-04-01", "early 2021", "ssep2022"),
    ("Anza St bike lanes", "ANZA ST", "30TH AVE", "ARGUELLO BLVD", "2021-07-01", "June 2021", "anza"),
    ("7th St quick-build", "7TH ST", "FOLSOM ST", "TOWNSEND ST", "2022-01-01", "2020 and 2021", "ssep2022"),
    ("Golden Gate Ave quick-build", "GOLDEN GATE AVE", "POLK ST", "MARKET ST", "2022-01-01", "2021", "ssep2022"),
    ("Leavenworth St quick-build", "LEAVENWORTH ST", "MCALLISTER ST", "POST ST", "2022-01-01", "2021", "ssep2022"),
    ("Williams Ave quick-build", "WILLIAMS AVE", "3RD ST", "PHELPS ST", "2021-11-01", "October 2021", "williams"),
    ("South Van Ness Ave quick-build", "SOUTH VAN NESS AVE", "14TH ST", "CESAR CHAVEZ ST", "2022-02-01", "January 2022", "svn"),
    ("Jones St quick-build", "JONES ST", "GOLDEN GATE AVE", "O'FARRELL ST", "2022-10-01", "summer 2022", "jones"),
    ("Evans Ave quick-build", "EVANS AVE", "CESAR CHAVEZ ST", "3RD ST", "2023-01-01", "summer to fall 2022", "evans"),
    ("Franklin St quick-build", "FRANKLIN ST", "BROADWAY", "LOMBARD ST", "2023-01-01", "late 2022", "franklin"),
    ("Battery St quick-build", "BATTERY ST", "MARKET ST", "VALLEJO ST", "2023-02-01", "January 2023", "battery"),
    ("Sansome St quick-build", "SANSOME ST", "SUTTER ST", "BROADWAY", "2023-02-01", "January 2023", "battery"),
    ("17th St quick-build", "17TH ST", "POTRERO AVE", "PENNSYLVANIA AVE", "2024-01-01", "summer to fall 2023", "17th"),
    ("Bayshore Blvd quick-build", "BAYSHORE BLVD", "OAKDALE AVE", "SILVER AVE", "2024-01-01", "construction August 2023, completed fall 2023", "bayshore"),
    ("Lincoln Way quick-build", "LINCOLN WAY", "GREAT HWY", "ARGUELLO BLVD", "2024-04-01", "winter 2024", "lincoln"),
    ("3rd St quick-build", "3RD ST", "CHANNEL ST", "TOWNSEND ST", "2024-04-01", "March 2024", "3rd"),
    ("Guerrero St quick-build", "GUERRERO ST", "MARKET ST", "20TH ST", "2024-10-01", "summer 2024", "guerrero"),
    ("Frida Kahlo Way quick-build", "FRIDA KAHLO WAY", "JUDSON AVE", "OCEAN AVE", "2025-01-01", "fall 2024", "frida"),
]
# The Tenderloin daylighting area, "bound by Market, Mason, Pine, and Larkin streets" (SFMTA project sheet).
TL_CORNERS = [("MARKET ST", "LARKIN ST"), ("MARKET ST", "MASON ST"), ("MASON ST", "PINE ST"), ("PINE ST", "LARKIN ST")]
TL_START = "2015-03-20"
CAM_CITE = D.fromisoformat("2025-08-05")   # first day of issued_citations at every camera location, d5uh-bk84
# The named streets of that area. An intersection is a node where two of them meet; alleys (Cosmo Pl, Shannon St, Olive St...) don't count.
TL_STREETS = {norm(x) for x in ("MARKET ST", "MASON ST", "PINE ST", "LARKIN ST", "HYDE ST", "LEAVENWORTH ST", "JONES ST", "TAYLOR ST", "GOLDEN GATE AVE",
                                "MCALLISTER ST", "TURK ST", "EDDY ST", "ELLIS ST", "O'FARRELL ST", "GEARY ST", "POST ST", "SUTTER ST", "BUSH ST")}


def pretty(st):
    """A centerline name for a reader: 09TH ST -> 9th St, BAY SHORE BLVD -> Bayshore Blvd."""
    w = st.replace("BAY SHORE", "BAYSHORE").title().split()
    return " ".join(re.sub(r"^0?(\d+)(St|Nd|Rd|Th)$", lambda m: m.group(1) + m.group(2).lower(), x) for x in w)


def seg_dist(px, py, ax, ay, bx, by):
    """Distance from point(s) to segment(s); either side may be an array, broadcasting."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(L2 > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(L2 > 0, L2, 1), 0.0)
    t = np.clip(t, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def along(pt, poly):
    """(feet along poly to the foot of pt, poly length, distance). The foot isn't clamped at the two ends."""
    best, run, n = None, 0.0, len(poly) - 1
    for i, (a, b) in enumerate(zip(poly, poly[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy)
        if not l:
            continue
        t = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / l / l
        tc = min(1, max(0, t))
        d = math.hypot(pt[0] - a[0] - tc * dx, pt[1] - a[1] - tc * dy)
        tt = t if (i == 0 and t < 0) or (i == n - 1 and t > 1) else tc
        if best is None or d < best[2]:
            best = (run + tt * l, None, d)
        run += l
    return best[0], run, best[2]


class Streets(object):
    """Active centerlines as a graph: segments keyed by CNN with class, street and end nodes, plus a grid for snapping."""

    def __init__(self):
        C = sfdata.fetch("3psu-pn9h", select="cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line",
                         where="active='true'", floor=15000)
        self.fetched = C.fetched_on.isoformat()
        self.seg, self.node_xy, self.at_node, self.by_street = {}, {}, collections.defaultdict(set), collections.defaultdict(list)
        self.grid = collections.defaultdict(list)
        for r in C.rows:
            if not r.get("line") or not r.get("f_node_cnn") or not r.get("t_node_cnn"):
                continue
            cnn = int(float(r["cnn"]))
            g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
            lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
            pts = [p for ln in lines for p in ln]
            P = [xy(*p) for p in pts]
            f, t = int(float(r["f_node_cnn"])), int(float(r["t_node_cnn"]))
            s = {"cnn": cnn, "street": norm(r.get("streetname") or ""), "cls": r.get("classcode") or "0", "layer": r.get("layer"),
                 "f": f, "t": t, "pts": pts, "P": P, "ft": sum(math.dist(a, b) for a, b in zip(P, P[1:]))}
            s["mid"] = self.midpoint(P)
            s["surface"] = not (s["layer"] or "").startswith(("FREEWAYS", "PAPER", "PSEUDO"))
            self.seg[cnn] = s
            self.node_xy.setdefault(f, P[0]); self.node_xy.setdefault(t, P[-1])
            self.at_node[f].add(cnn); self.at_node[t].add(cnn)
            self.by_street[s["street"]].append(cnn)
            if not s["surface"]:
                continue   # the crash data excludes freeway crashes, so a point under a freeway is a surface-street crash
            for a, b in zip(P, P[1:]):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.grid[(cx, cy)].append((a[0], a[1], b[0], b[1], cnn))
        self.cells = {k: np.array(v) for k, v in self.grid.items()}

    @staticmethod
    def midpoint(P):
        L = [math.dist(a, b) for a, b in zip(P, P[1:])]
        half, run = sum(L) / 2, 0.0
        for (a, b), l in zip(zip(P, P[1:]), L):
            if l and run + l >= half:
                t = (half - run) / l
                return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return P[0]

    def nearest(self, x, y):
        """(cnn, distance ft, nearest end node of that segment, distance to it) or None when nothing is within a cell."""
        cx, cy = int(x // CELL), int(y // CELL)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                A = self.cells.get((cx + dx, cy + dy))
                if A is None:
                    continue
                d = seg_dist(x, y, A[:, 0], A[:, 1], A[:, 2], A[:, 3])
                i = int(np.argmin(d))
                if best is None or d[i] < best[1]:
                    best = (int(A[i, 4]), float(d[i]))
        if best is None:
            return None
        s = self.seg[best[0]]
        nf, nt = math.dist((x, y), self.node_xy[s["f"]]), math.dist((x, y), self.node_xy[s["t"]])
        return best[0], best[1], (s["f"] if nf <= nt else s["t"]), min(nf, nt)

    def meeting(self, a, b):
        """Nodes where streets a and b meet."""
        A = {n for c in self.by_street.get(norm(a), []) for n in (self.seg[c]["f"], self.seg[c]["t"])}
        B = {n for c in self.by_street.get(norm(b), []) for n in (self.seg[c]["f"], self.seg[c]["t"])}
        return A & B

    def corridor(self, street, x, y):
        """Segments of `street` on the shortest path between its meetings with x and y, plus the other carriageway."""
        import heapq
        st = norm(street)
        ss = self.by_street.get(st, [])
        A, B = self.meeting(street, x), self.meeting(street, y)
        if not ss or not A or not B:
            return None, "no street" if not ss else "end not found: " + ("" if A else x) + ("" if B else " " + y)
        adj = collections.defaultdict(list)
        for c in ss:
            s = self.seg[c]
            adj[s["f"]].append((s["t"], c)); adj[s["t"]].append((s["f"], c))
        best = None
        for a in A:
            dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
            while pq:
                d, n = heapq.heappop(pq)
                if d > dist.get(n, 1e18):
                    continue
                if n in B and n != a:
                    if best is None or d < best[0]:
                        path, nodes, m = [], [n], n
                        while m != a:
                            pn, c = prev[m]
                            path.append(c); m = pn; nodes.append(m)
                        best = (d, path, nodes)
                    break
                for m, c in adj[n]:
                    nd = d + self.seg[c]["ft"]
                    if nd < dist.get(m, 1e18):
                        dist[m], prev[m] = nd, (n, c)
                        heapq.heappush(pq, (nd, m))
        if not best:
            return None, "ends not connected along the street"
        ids = set(best[1])
        self.last_path_ft = best[0]
        poly = [self.node_xy[n] for n in best[2]]
        for c in ss:
            if c in ids:
                continue
            al, L, dd = along(self.seg[c]["mid"], poly)
            if EDGE_FT < al < L - EDGE_FT and dd <= PAIR_FT:
                ids.add(c)
        return ids, "path"

    def two_blocks(self, site_segs, site_nodes):
        """The next two blocks out from the site: every segment at a site node (the next block along the street and the
        first block of each cross street), then from each of those segments' far ends the segments of the same street
        (the second block along each). Parallel streets one block over are not taken in."""
        first, nodes = set(), set(site_nodes)
        for n in site_nodes:
            first |= self.at_node[n] - site_segs
        second = set()
        for c in first:
            s = self.seg[c]
            for m in (s["f"], s["t"]):
                if m in site_nodes:
                    continue
                nodes.add(m)
                for c2 in self.at_node[m]:
                    if c2 not in first and c2 not in site_segs and self.seg[c2]["street"] == s["street"]:
                        second.add(c2)
        for c in second:
            nodes.add(self.seg[c]["f"]); nodes.add(self.seg[c]["t"])
        return first | second, nodes - set(site_nodes)

    def hops(self, nodes, k):
        """Segments within k graph hops of `nodes`, and the nodes reached."""
        segs, seen, frontier = set(), set(nodes), set(nodes)
        for _ in range(k):
            nxt = set()
            for n in frontier:
                for c in self.at_node[n]:
                    segs.add(c)
                    s = self.seg[c]
                    for m in (s["f"], s["t"]):
                        if m not in seen:
                            nxt.add(m)
            seen |= nxt
            frontier = nxt
        return segs, seen


def victims():
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,victim_role,collision_datetime,"
                     "collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd,intersection,distance,ped_action,street_of_travel,"
                     "move_pre_acc,party_type,party_number_ckey,type_of_collision,vz_pcf_code", floor=80000)
    out = []
    for v in V.rows:
        if v.get("victim_degree_of_injury") in (None, "No Injury"):
            continue
        dts = v.get("collision_datetime") or ""
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not dts or not (37.6 < la < 37.85 and -122.53 < lo < -122.35):
            continue
        try:
            age = int(float(v.get("victim_age") or ""))
        except ValueError:
            age = None
        # a null collision_time leaves collision_datetime at 00:00, a fill for an unknown time, not midnight
        hr = int(dts[11:13]) if v.get("collision_time") and len(dts) >= 13 and dts[11:13].isdigit() else None
        dd = D.fromisoformat(dts[:10])
        # Bryan's school-trip window (lib/school_window.py): a child 5 to 18, on a weekday, 6 AM to 6 PM, August to May.
        kid = school_window.kid_hurt(v) is not None
        out.append({"d": dd, "lon": lo, "lat": la, "sev": v["victim_degree_of_injury"] in SEVERE, "fatal": v["victim_degree_of_injury"] == "Fatal Injury", "kid": kid,
                    "role": v.get("victim_role"), "ix": (v.get("intersection") or "").startswith("Intersection"),
                    "cause": cause(v.get("vz_pcf_code")), "place": place(v.get("intersection"), v.get("distance")),
                    "pcf": v.get("vz_pcf_code"), "toc": v.get("type_of_collision"), "mpa": v.get("move_pre_acc"), "case": v.get("case_id_pkey"), "party": v.get("party_number_ckey"), "hr": hr, "hm": dts[11:16]})
    # citywide yearly series for the trend chart: every injured victim row, with or without a location
    yc = collections.defaultdict(collections.Counter)
    for v in V.rows:
        deg, y = v.get("victim_degree_of_injury"), (v.get("collision_datetime") or "")[:4]
        if deg in (None, "No Injury") or not y.isdigit():
            continue
        yc[y]["all"] += 1; yc[y]["severe"] += deg in SEVERE; yc[y]["fatal"] += deg == "Fatal Injury"
    victims.yearly = {y: dict(c) for y, c in sorted(yc.items())}
    # Why fewer since 2020 (Bryan): quarterly totals 2018 to 2023, and 2015-19 against 2021-25
    # yearly averages by injury degree, victim role, a downtown box (east of -122.425, north of 37.765: FiDi, SoMa,
    # Tenderloin, Chinatown, North Beach), time of day and weekday.
    qc = collections.Counter(); sp = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for v in V.rows:
        deg, dts = v.get("victim_degree_of_injury"), v.get("collision_datetime") or ""
        if deg in (None, "No Injury") or len(dts) < 10:
            continue
        y = dts[:4]
        if "2018" <= y <= "2023":
            qc["%sQ%d" % (y, (int(dts[5:7]) - 1) // 3 + 1)] += 1
        per = "pre" if "2015" <= y <= "2019" else "post" if "2021" <= y <= "2025" else None
        if not per:
            continue
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"]); area = "downtown" if lo >= -122.425 and la >= 37.765 else "rest"
        except (KeyError, TypeError, ValueError):
            area = "no location"
        t = v.get("collision_time"); h = int(t[:2]) if t else None
        tod = "none" if h is None else "commute" if h in (7, 8, 9, 16, 17, 18) else "night" if h >= 22 or h < 6 else "other"
        wk = "weekend" if D.fromisoformat(dts[:10]).weekday() >= 5 else "weekday"
        for k, val in (("degree", deg), ("role", v.get("victim_role") or "Not stated"), ("area", area), ("tod", tod), ("day", wk)):
            sp[k][val][per] += 1
    victims.step = {"quarters": dict(sorted(qc.items())),
                    "split": {k: {val: {"pre": c["pre"] / 5, "post": c["post"] / 5} for val, c in d.items()} for k, d in sp.items()}}
    return out, V.fetched_on.isoformat()


BOOT, BOOT_SEED = 2000, 20261020   # pooled bootstrap reps and seed (pooled() docstring)


def in_group(v, g):
    """Whether victim v counts in group g: all, severe, ped (role Pedestrian) or bike (role Bicyclist)."""
    return g == "all" or (g == "severe" and bool(v["sev"])) or (g == "ped" and v["role"] == "Pedestrian") or (g == "bike" and v["role"] == "Bicyclist")


def rr(a, b, c, d):
    """Ratio of the site's after/before to the rest of the city's, with a 95% interval."""
    if min(a, b, c, d) == 0:
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    est = (a / b) / (c / d)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return est, est * math.exp(-1.96 * se), est * math.exp(1.96 * se)


def main():
    S = Streets()
    V, vdate = victims()
    # The data's last month is complete when its count sits in the range of the twelve before it; otherwise drop it.
    months = collections.Counter((v["d"].year, v["d"].month) for v in V)
    last = max(months)
    prior = [months[m] for m in sorted(months)[-13:-1]]
    END = D(last[0], last[1], 1) + datetime.timedelta(days=31)
    END = END.replace(day=1) - datetime.timedelta(days=1)
    if months[last] < 0.7 * min(prior):
        END = D(last[0], last[1], 1) - datetime.timedelta(days=1)
    # Five calendar years back; a 29 February end falls back to the 28th in a year without one.
    START5 = D(END.year - 5, END.month, min(END.day, 28) if (END.month, END.day) == (2, 29) else END.day) + datetime.timedelta(days=1)

    hin_file = json.load(open(os.path.join(ROOT, "data", "extract", "access", "hin-2022.json")))
    hin_ids = {r["id"] for r in hin_file["records"]}
    hin_pieces = []
    for r in hin_file["records"]:
        P = [xy(*p) for p in r["pts"]]
        hin_pieces.extend((a[0], a[1], b[0], b[1]) for a, b in zip(P, P[1:]))
    H = np.array(hin_pieces)

    # snap every victim
    px = np.array([xy(v["lon"], v["lat"])[0] for v in V]); py = np.array([xy(v["lon"], v["lat"])[1] for v in V])
    hd = np.full(len(V), 1e9)
    for i in range(0, len(H), 2000):
        blk = H[i:i + 2000]
        for row in blk:
            d = seg_dist(px, py, *row)
            np.minimum(hd, d, out=hd)
    unsnapped = 0
    for i, v in enumerate(V):
        n = S.nearest(px[i], py[i])
        v["hin"] = bool(hd[i] <= ON_FT)
        if n is None or n[1] > SNAP_FT:
            v["seg"] = v["node"] = None; v["cls"] = None; unsnapped += 1
            continue
        cnn, dseg, node, dnode = n
        v["seg"] = cnn
        v["node"] = node if (v["ix"] or dnode <= NODE_FT) else None
        if v["node"] is not None:
            v["cls"] = max((S.seg[c]["cls"] for c in S.at_node[node]), key=lambda k: {"1": 6, "2": 5, "3": 4, "4": 3, "6": 2, "5": 1, "0": 0}[k])
        else:
            v["cls"] = S.seg[cnn]["cls"]

    # 1. where people are hurt, the five years to END
    W = [v for v in V if START5 <= v["d"] <= END and v["cls"] is not None]
    def shares(rows):
        by = collections.Counter(v["cls"] for v in rows)
        return {"total": len(rows), "main": sum(1 for v in rows if v["cls"] in MAIN), "hin": sum(1 for v in rows if v["hin"]),
                "freeway": sum(1 for v in rows if v["cls"] in ("1", "6")),
                "mainAndHin": sum(1 for v in rows if v["hin"] and v["cls"] in MAIN), "byClass": {k: by.get(k, 0) for k in CLASS},
                "byRole": dict(collections.Counter(v["role"] for v in rows))}
    where = {"from": START5.isoformat(), "to": END.isoformat(), "all": shares(W), "severe": shares([v for v in W if v["sev"]]),
             "unsnapped": sum(1 for v in V if START5 <= v["d"] <= END and v["cls"] is None), "classNames": CLASS}
    # street miles by class, the same centerline layer, STREETS layer only
    miles = collections.Counter()
    for s in S.seg.values():
        if s["layer"] == "STREETS":
            miles[s["cls"]] += s["ft"] / 5280
    where["milesByClass"] = {k: round(miles.get(k, 0), 1) for k in CLASS}
    # two example streets per class: the longest streets with most of their own miles in that class
    by_street = collections.defaultdict(collections.Counter)
    for s in S.seg.values():
        if s["layer"] == "STREETS" and s["street"]:
            by_street[s["street"]][s["cls"]] += s["ft"] / 5280
    where["examplesByClass"] = {k: [n for n, c in sorted(by_street.items(), key=lambda kv: -kv[1][k])
                                    if c[k] > 0.5 * sum(c.values())][:2] for k in CLASS}
    where["mainMiles"] = round(sum(miles[k] for k in MAIN), 1)
    where["yearly"] = victims.yearly
    where["step"] = victims.step
    # Bryan, thread tlwgirvawpdt: main roads are one group. Its examples are the streets he named, checked here to be
    # mostly main road by their own miles. Posted speed limits from SFMTA's speed limit layer, by centerline cnn.
    ex = ["19TH AVE", "GEARY BLVD", "03RD ST"]
    where["mainExamples"] = [n for n in ex if sum(by_street[n][k] for k in MAIN) > 0.5 * sum(by_street[n].values())]
    SL = sfdata.fetch("3t7b-gebn", select="cnn,speedlimit,schoolzone,mtab_date", floor=3000)
    lim = {}
    for r in SL.rows:
        try:
            lim[int(float(r["cnn"]))] = int(r.get("speedlimit") or 0)
        except (KeyError, TypeError, ValueError):
            pass
    sp = collections.Counter()
    for c, sg in S.seg.items():
        if sg["layer"] == "STREETS" and sg["cls"] in MAIN:
            v = lim.get(c)
            sp["none" if v is None else "zero" if v == 0 else "over25" if 25 < v < 99 else "99" if v >= 99 else "upto25"] += sg["ft"] / 5280
    where["mainSpeed"] = {k: round(v, 1) for k, v in sorted(sp.items())}
    where["mainSpeed"]["fetched"] = SL.fetched_on.isoformat()
    # Blocks posted at 20 mph by an SFMTA Board action from 2022 on (mtab_date), the limit AB 43 newly allows: miles,
    # streets and the span of Board dates. The dataset does not carry the prior limit or the day signs went up.
    dates = {}
    for r in SL.rows:
        try:
            c = int(float(r["cnn"]))
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("speedlimit") == "20" and (r.get("mtab_date") or "")[:4] >= "2022":
            dates[c] = r["mtab_date"][:10]
    segs = [c for c in dates if c in S.seg and S.seg[c]["layer"] == "STREETS"]
    where["to20"] = {"miles": round(sum(S.seg[c]["ft"] for c in segs) / 5280, 1), "blocks": len(segs),
                     "streets": len({S.seg[c]["street"] for c in segs}), "first": min(dates[c] for c in segs), "last": max(dates[c] for c in segs),
                     "byYear": dict(sorted(collections.Counter(dates[c][:4] for c in segs).items()))}
    where["streetMiles"] = round(sum(miles.values()), 1)
    hin_mi = sum(math.dist(xy(*a), xy(*b)) for r in hin_file["records"] for a, b in zip(r["pts"], r["pts"][1:])) / 5280
    where["hinMiles"] = round(hin_mi, 1)
    # why and where on the block: people hurt by cause group and by place, main roads against residential streets
    def tally(key, groups):
        o = {}
        for side, ks in (("main", MAIN), ("res", {"5"})):
            rows = [v for v in W if v["cls"] in ks]
            a = collections.Counter(v[key] for v in rows); sv = collections.Counter(v[key] for v in rows if v["sev"])
            o[side] = {"total": len(rows), "severe": sum(1 for v in rows if v["sev"]),
                       "rows": {k: {"all": a.get(k, 0), "severe": sv.get(k, 0)} for k, _ in groups}}
            assert sum(r["all"] for r in o[side]["rows"].values()) == len(rows), (key, side)
        o["names"] = dict(groups)
        o["order"] = [k for k, _ in groups]
        return o
    F, ALLP, pdate = faults()
    for v in W:
        f = list(F.get(v["case"], {}).values())
        v["fault"] = f[0][0] if len(f) == 1 else "none"     # no at-fault party (twoAtFault counts any with more than one)
        v["selfFault"] = len(f) == 1 and v["party"] in F[v["case"]]
        v["faultVeh"] = f[0][1] if len(f) == 1 else None
        v["faultType"] = f[0][2] if len(f) == 1 else None
        ps = ALLP.get(v["case"], {})
        v["motorIn"] = any(motor(m) for m in ps.values())
        own = ps.get(v["party"])
        others = [m for k, m in ps.items() if k != v["party"]]
        v["ownMode"] = own[0] if own else None
        v["hitBy"] = "motor" if any(motor(m) for m in others) else ("nonmotor" if others else "alone")
    where["fault"] = tally("fault", FAULTS)
    # Bryan: was a motor vehicle in the crash at all, for each at-fault group
    for side, ks in (("main", MAIN), ("res", {"5"})):
        for k, _ in FAULTS:
            where["fault"][side]["rows"][k]["motor"] = sum(1 for v in W if v["cls"] in ks and v["fault"] == k and v["motorIn"])
    # people walking, biking or on a scooter: severe or killed share by what else was in the crash
    vul = [v for v in W if v["cls"] in MAIN | {"5"} and v["ownMode"] in ("walk", "bike", "scoot")]
    where["fault"]["hitBy"] = {g: {"n": sum(1 for v in vul if v["hitBy"] == g), "severe": sum(1 for v in vul if v["hitBy"] == g and v["sev"])}
                               for g in ("motor", "nonmotor", "alone")}
    # Who hurt whom (coordinator's ask, not on the page yet). "What hit them" is the one other party in a two-party
    # crash. With three or more, the data does not say which parties collided, so: the at-fault party if it is not the
    # victim's own; otherwise the other parties' most dangerous mode, motor vehicle first (transit, then driving).
    RANK = {"transit": 0, "drive": 1, "bike": 3, "scoot": 4, "walk": 5, "other": 6}
    def hit(v):
        ps = ALLP.get(v["case"], {}); others = {k: m for k, m in ps.items() if k != v["party"]}
        if not others:
            return "alone"
        af = [k for k in F.get(v["case"], {}) if k != v["party"]]
        if len(others) > 1 and af:
            m = others[af[0]]
        else:
            m = min(others.values(), key=lambda m: (RANK.get("drive" if m[2] == "Parked Vehicle" else m[0], 9), str(m)))
        return "drive" if m[2] == "Parked Vehicle" else m[0]
    wh = collections.defaultdict(lambda: [0, 0])
    for v in W:
        if v["cls"] in MAIN | {"5"}:
            c = wh[(v["ownMode"] or "other", hit(v))]; c[0] += 1; c[1] += v["sev"]
    where["whoHurtWhom"] = {"%s|%s" % k: c for k, c in sorted(wh.items())}
    where["fault"]["threePlus"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and len(ALLP.get(v["case"], {})) >= 3)
    # Everyone hurt, citywide, by the mode they were using: their own party's mode (a passenger takes the vehicle's).
    OWN = [("walk", "Walking"), ("bike", "Biking"), ("scoot", "On a scooter or board"), ("drive", "In a car, truck or motorcycle"),
           ("transit", "On Muni or other transit"), ("other", "Other or not stated")]
    for v in W:
        if v.get("ownMode") is None:
            ps = ALLP.get(v["case"], {}); own = ps.get(v["party"]); v["ownMode"] = own[0] if own else None
    oc = collections.Counter(v["ownMode"] or "other" for v in W); os_ = collections.Counter(v["ownMode"] or "other" for v in W if v["sev"])
    where["ownMode"] = {"total": len(W), "severe": sum(1 for v in W if v["sev"]), "order": [k for k, _ in OWN], "names": dict(OWN),
                        "rows": {k: {"all": oc.get(k, 0), "severe": os_.get(k, 0)} for k, _ in OWN},
                        "unmatched": sum(1 for v in W if v["ownMode"] is None)}
    assert sum(r["all"] for r in where["ownMode"]["rows"].values()) == len(W)
    # Per trip (Bryan): for someone going out by each mode, over the five-year window W:
    # crash parties of that mode (one party is one walker, rider or vehicle, passengers not counted), people hurt
    # while using it, and people hurt by a party of that mode marked solely at fault, other than that party and the
    # people in it (its driver and passengers share its party number). Parked vehicles are not trips and count as none.
    cases_w = {v["case"] for v in W}
    pt = {"crashParties": collections.Counter(), "hurt": collections.Counter(), "hurtSevere": collections.Counter(),
          "hurtOthers": collections.Counter(), "hurtOthersSevere": collections.Counter(), "killed": collections.Counter()}
    # Motorcycles and mopeds get their own key here (skeptic review, 2026-10-20): the trip survey has no motorcycle
    # share, so the car-or-truck rate leaves their riders and crashes out of the count rather than spread them over car trips.
    MOTO = {"Motorcycle", "Motor Driven Cycle/Scooter", "Moped", "Police Motorcycle"}
    ptm = lambda m: "moto" if m[0] == "drive" and m[1] in MOTO else m[0]
    for cs in cases_w:
        for k, m in ALLP.get(cs, {}).items():
            if m[2] != "Parked Vehicle":
                pt["crashParties"][ptm(m)] += 1
    for v in W:
        own = ALLP.get(v["case"], {}).get(v["party"])
        om = (ptm(own) if own and v["ownMode"] else None) or v["ownMode"] or "other"
        pt["hurt"][om] += 1; pt["hurtSevere"][om] += v["sev"]
        pt["killed"][om] += v.get("fatal", False)
        f = F.get(v["case"], {})
        if len(f) == 1:
            (fk, fm), = f.items()
            if fk != v["party"] and fm[2] != "Parked Vehicle":
                pt["hurtOthers"][ptm(fm)] += 1; pt["hurtOthersSevere"][ptm(fm)] += v["sev"]
    # Bryan: the at-fault vehicle's body type, from stwd_vehicle_type (the data has make and
    # year but no model, so no finer body class or grille height). People hurt outside the at-fault vehicle.
    BODY = {"Passenger Car": "car", "Sport Utility Vehicle": "suv", "Pickup or Panel Truck": "pickup", "Pickup or Panel Truck with Trailer": "pickup",
            "Minivan": "pickup", "Motorcycle": "moto", "Motor Driven Cycle/Scooter": "moto", "Two Axle Truck": "big", "Semi": "big",
            "Three or More Axle Truck": "big", "Two Axle Tank Truck": "big", "Other Commercial": "big", "Fire Truck": "big", "Public Transit Authority": "big", "Paratransit": "big"}
    bt = collections.defaultdict(lambda: [0, 0])
    for v in W:
        f = F.get(v["case"], {})
        if len(f) == 1:
            (fk, fm), = f.items()
            if fk != v["party"] and fm[2] == "Driver" and fm[1] in BODY:
                c = bt[BODY[fm[1]]]; c[0] += 1; c[1] += v["sev"]
    pt["byBody"] = {k: {"all": c[0], "severe": c[1]} for k, c in bt.items()}
    # Who hurts whom (Bryan): the single at-fault party's mode against the injured person's own
    # mode, every person hurt in the window, the at-fault party included (a cyclist who falls alone is in Biking,
    # Biking). A parked vehicle at fault counts as driving. No at-fault party, two, or an unstated mode is "none".
    COLS = {"walk": "walk", "bike": "bike", "scoot": "scoot", "drive": "veh", "transit": "veh"}
    grid = collections.defaultdict(lambda: [0, 0])
    causes = {"bike": collections.Counter(), "drive": collections.Counter()}
    pcfs = {"bike": collections.Counter(), "drive": collections.Counter()}
    for v in W:
        f = F.get(v["case"], {})
        if len(f) == 1:
            (fk, fm), = f.items()
            row = "drive" if fm[2] == "Parked Vehicle" else fm[0] if fm[0] in ("drive", "transit", "bike", "scoot", "walk") else "none"
        else:
            row = "none"
        col = COLS.get(v["ownMode"] or "other", "veh")
        if row == "bike" and len(f) == 1 and fk == v["party"]:
            row = "bikeself"   # the at-fault cyclist themselves (Bryan)
        c = grid[row + "|" + col]; c[0] += 1; c[1] += v["sev"]
        if len(f) == 1 and row in ("bike", "bikeself", "drive"):
            causes["bike" if row != "drive" else "drive"][v["cause"]] += 1
            pcfs["bike" if row != "drive" else "drive"][v["pcf"] or "none"] += 1
    pt["grid"] = {k: {"all": c[0], "severe": c[1]} for k, c in sorted(grid.items())}
    pt["faultCauses"] = {k: dict(c.most_common()) for k, c in causes.items()}
    pt["faultCodes"] = {k: dict(c.most_common(12)) for k, c in pcfs.items()}
    # People who hurt themselves (Bryan): the at-fault cyclist or walker is the person hurt.
    # "Solo" is a crash with no other party at all. Road fields come from the crash table (ubvf-ztfx), one row a crash.
    CR = sfdata.fetch("ubvf-ztfx", select="case_id_pkey,lighting,road_surface,road_cond_1,road_cond_2,weather_1",
                      where="collision_datetime >= '2021-09-01T00:00:00'", floor=10000)
    crash = {r["case_id_pkey"]: r for r in CR.rows}
    DESC = {}
    for r in sfdata.fetch("ubvf-ztfx", select="case_id_pkey,collision_datetime,vz_pcf_code,vz_pcf_group,vz_pcf_description,type_of_collision,dph_col_grp_description,intersection,distance,number_killed,number_injured",
                          where="collision_datetime >= '2021-09-01T00:00:00'", floor=10000).rows:
        if r.get("vz_pcf_code") and r.get("vz_pcf_description"):
            DESC.setdefault(r["vz_pcf_code"], r["vz_pcf_description"])
    DEFECT = {"Holes, Deep Rut", "Loose Material on Roadway", "Obstruction on Roadway", "Construction or Repair Zone", "Reduced Roadway Width", "Flooded"}
    def wyear(dd):   # window years run September to August
        return dd.year if dd.month >= 9 else dd.year - 1
    selfh = {}
    for g, md in (("bike", "bike"), ("walk", "walk")):
        rows = []
        for v in W:
            f = F.get(v["case"], {})
            if len(f) == 1:
                (fk, fm), = f.items()
                if fm[0] == md and fk == v["party"]:
                    rows.append(v)
        solo = [v for v in rows if len(ALLP.get(v["case"], {})) == 1]
        cr = [crash.get(v["case"], {}) for v in rows]
        rc = collections.Counter(c.get("road_cond_1") or "missing" for c in cr)
        selfh[g] = {"n": len(rows), "solo": len(solo), "severe": sum(v["sev"] for v in rows), "killed": sum(v["fatal"] for v in rows),
                    "soloSevere": sum(v["sev"] for v in solo),
                    "byYear": dict(sorted(collections.Counter(wyear(v["d"]) for v in rows).items())),
                    "soloByYear": dict(sorted(collections.Counter(wyear(v["d"]) for v in solo).items())),
                    "codes": [[c, n, DESC.get(c)] for c, n in collections.Counter(v["pcf"] or "none" for v in rows).most_common(60)],
                    "soloCodes": [[c, n, DESC.get(c)] for c, n in collections.Counter(v["pcf"] or "none" for v in solo).most_common(8)],
                    "toc": dict(collections.Counter(v["toc"] or "none" for v in rows).most_common()),
                    "roadCond": dict(rc.most_common()), "defect": sum(n for k, n in rc.items() if k in DEFECT),
                    "soloDefect": sum(1 for v in solo if crash.get(v["case"], {}).get("road_cond_1") in DEFECT),
                    "surface": dict(collections.Counter(c.get("road_surface") or "missing" for c in cr).most_common()),
                    "lighting": dict(collections.Counter(c.get("lighting") or "missing" for c in cr).most_common()),
                    "matched": sum(1 for c in cr if c)}
    where["selfHurt"] = selfh
    where["selfHurt"]["crashFetched"] = CR.fetched_on.isoformat()
    # Why people biking get hurt (Bryan): everyone hurt while biking, by who was at fault, the
    # crash type, the High Injury Network, a bikeway on the block they snapped to, and light, against people walking.
    NET = json.load(open(os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "network.json")))["records"]
    bw = collections.defaultdict(set)
    for r in NET:
        if r.get("CNN"):
            bw[int(float(r["CNN"]))].add(r.get("FACILITY_T"))
    surf = [sg for sg in S.seg.values() if sg["surface"]]
    bw_ft = sum(sg["ft"] for sg in surf if bw.get(sg["cnn"], set()) - {"CLASS III"}); all_ft = sum(sg["ft"] for sg in surf)
    p4_ft = sum(sg["ft"] for sg in surf if "CLASS IV" in bw.get(sg["cnn"], ()))
    why = {}
    for md in ("bike", "walk"):
        rows = [v for v in W if v["ownMode"] == md]
        fa = collections.Counter()
        for v in rows:
            f = F.get(v["case"], {})
            if len(f) != 1:
                fa["none"] += 1; continue
            (fk, fm), = f.items()
            fa["self" if fk == v["party"] else "parked" if fm[2] == "Parked Vehicle" else ("drive" if fm[0] in ("drive", "transit") else fm[0])] += 1
        lit = collections.Counter(crash.get(v["case"], {}).get("lighting") or "missing" for v in rows)
        why[md] = {"n": len(rows), "severe": sum(v["sev"] for v in rows), "fault": dict(fa.most_common()),
                   "toc": dict(collections.Counter(v["toc"] or "none" for v in rows).most_common()),
                   "mpa": dict(collections.Counter(v["mpa"] or "none" for v in rows).most_common(10)),
                   "hin": sum(v["hin"] for v in rows), "main": sum(1 for v in rows if v["cls"] in MAIN),
                   "bikeway": sum(1 for v in rows if bw.get(v["seg"], set()) - {"CLASS III"}), "classIV": sum(1 for v in rows if "CLASS IV" in bw.get(v["seg"], ())),
                   "lighting": dict(lit.most_common()), "dark": sum(n for k, n in lit.items() if k.startswith("Dark") or k == "Dusk - Dawn")}
    why["bikewayMilesShare"] = round(bw_ft / all_ft, 4); why["classIVMilesShare"] = round(p4_ft / all_ft, 4)
    why["allHin"] = sum(v["hin"] for v in W); why["all"] = len(W)
    where["bikeWhy"] = why
    where["perTrip"] = {k: dict(c) for k, c in pt.items()}
    def pois_ci(k):
        """Exact (Garwood) 95% range for a Poisson count k, by bisection on the Poisson tail."""
        def cdf(lam, n):
            t = term = math.exp(-lam)
            for i in range(1, n + 1):
                term *= lam / i; t += term
            return t
        def solve(f, lo, hi):
            for _ in range(80):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if f(mid) else (lo, mid)
            return (lo + hi) / 2
        low = 0.0 if k == 0 else solve(lambda l: 1 - cdf(l, k - 1) < 0.025, 0, k + 50)
        high = solve(lambda l: cdf(l, k) > 0.025, 0, k * 3 + 20)
        return [round(low, 3), round(high, 3)]
    where["perTrip"]["killedCI"] = {m: pois_ci(n) for m, n in where["perTrip"]["killed"].items()}
    where["perTrip"].update(crashes=len(cases_w), years=round(((END - START5).days + 1) / 365.25, 3))
    # Involvement (Bryan): for each mode, people hurt in a crash where any party, the victim's own
    # included, used it. A crash with a car and a bike counts under both, so the rows add to more than everyone hurt.
    # A parked vehicle counts as a car. A victim with no party rows counts under none.
    inv = collections.Counter(); inv_s = collections.Counter(); nmodes = collections.Counter()
    for v in W:
        ms = {("drive" if m[2] == "Parked Vehicle" else m[0]) for m in ALLP.get(v["case"], {}).values()}
        ms.discard("other"); nmodes[len(ms)] += 1
        for k in ms:
            inv[k] += 1; inv_s[k] += v["sev"]
    where["involved"] = {"total": len(W), "severe": sum(1 for v in W if v["sev"]),
                         "rows": {k: {"all": inv.get(k, 0), "severe": inv_s.get(k, 0)} for k in ("drive", "transit", "bike", "scoot", "walk")},
                         "modesPerVictim": {str(k): n for k, n in sorted(nmodes.items())},
                         "noParty": sum(1 for v in W if v["case"] not in ALLP)}
    # most car involvement is built in, since a person hurt in a car is in a crash with a car: the share among the rest
    nc = [v for v in W if (v["ownMode"] or "other") != "drive"]
    where["involved"]["notInCar"] = {"all": len(nc), "car": sum(1 for v in nc if any(m[0] == "drive" or m[2] == "Parked Vehicle" for m in ALLP.get(v["case"], {}).values()))}
    # Time of day (Bryan): people hurt by the crash's hour, weekday against weekend, per day of
    # that type in the window. collision_datetime carries the time; a time of exactly 00:00 is held out as a likely
    # default when it is far commoner than the other minutes of that hour.
    days = collections.Counter("we" if (START5 + datetime.timedelta(days=i)).weekday() >= 5 else "wd" for i in range((END - START5).days + 1))
    zero = sum(1 for v in W if v["hm"] == "00:00"); hour0 = [v for v in W if v["hr"] == 0 and v["hm"] != "00:00"]
    drop_zero = zero > 3 * max(1, len(hour0) / 59)
    tod = {"days": dict(days), "missing": sum(1 for v in W if v["hr"] is None), "midnight": zero, "midnightDropped": drop_zero,
           "hours": {g: {"all": [0] * 24, "severe": [0] * 24} for g in ("wd", "we")}}
    for v in W:
        if v["hr"] is None or (drop_zero and v["hm"] == "00:00"):
            continue
        g = "we" if v["d"].weekday() >= 5 else "wd"
        tod["hours"][g]["all"][v["hr"]] += 1; tod["hours"][g]["severe"][v["hr"]] += v["sev"]
    where["tod"] = tod
    where["fault"]["unmatchedParty"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and v["ownMode"] is None)
    where["fault"]["partiesFetched"] = pdate
    where["fault"]["twoAtFault"] = sum(1 for v in W if len(F.get(v["case"], {})) > 1)
    where["fault"]["motorcycle"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and v["faultVeh"] in ("Motorcycle", "Motor Driven Cycle/Scooter"))
    where["fault"]["driverOrPassenger"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and v["fault"] in ("drive", "transit") and v["selfFault"])
    where["fault"]["parked"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and v["faultType"] == "Parked Vehicle")
    where["fault"]["hitRun"] = sum(1 for v in W if v["cls"] in MAIN | {"5"} and v["faultVeh"] == "Unknown Hit and Run")
    # what at-fault drivers did: cause among people hurt where a car, truck, motorcycle or transit driver was at fault
    dr = [v for v in W if v["cls"] in MAIN | {"5"} and v["fault"] in ("drive", "transit")]
    where["fault"]["driverCause"] = {"total": len(dr), "rows": dict(collections.Counter(v["cause"] for v in dr))}
    where["cause"] = tally("cause", CAUSES)
    where["place"] = tally("place", PLACES)
    # crashes behind the main-road and residential victims, for the note: one cause per crash
    where["cause"]["crashes"] = len({v["case"] for v in W if v["cls"] in MAIN | {"5"}})

    # 2. interventions
    sites = []

    VI = {id(v): i for i, v in enumerate(V)}

    def evaluate(label, kind, site_segs, site_nodes, start, note, claim_key, extra=None, record=True):
        buf_segs, buf_nodes = S.two_blocks(site_segs, site_nodes)
        ring_segs, ring_nodes = S.hops(site_nodes, RING_HOPS)
        ring_segs -= buf_segs | site_segs
        ring_nodes -= buf_nodes | set(site_nodes)
        days = min(round(WINDOW_YEARS * 365.25), (END - start).days + 1)
        yrs = days / 365.25
        span = datetime.timedelta(days=days)
        after0, after1 = start, start + span - datetime.timedelta(days=1)
        before0, before1 = start - span, start - datetime.timedelta(days=1)
        pre0, pre1 = before0 - span, before0 - datetime.timedelta(days=1)   # placebo: the window before the before window
        def where_is(v):
            if v["seg"] is None:
                return "city"
            if v["seg"] in site_segs or (v["node"] is not None and v["node"] in site_nodes):
                return "site"
            if v["seg"] in buf_segs or (v["node"] is not None and v["node"] in buf_nodes):
                return "near"
            if v["seg"] in ring_segs or (v["node"] is not None and v["node"] in ring_nodes):
                return "ring"
            return "city"
        # counts[place][group] = [before, after]; groups: all, severe, ped, bike
        cnt = {p: {g: [0, 0] for g in GROUPS} for p in ("site", "near", "ring", "city")}
        members, comp_pre = [], {g: 0 for g in GROUPS}   # (victim index, site or near, window) for pooling; comparator pre counts
        area = {}   # victim index -> site or near, at any date: where this row's area holds them, for pooled() weights
        for v in V:
            wa = where_is(v)
            if wa in ("site", "near"):
                area[VI[id(v)]] = wa
            if before0 <= v["d"] <= before1:
                k = 0
            elif after0 <= v["d"] <= after1:
                k = 1
            elif pre0 <= v["d"] <= pre1:
                w = where_is(v)
                if w in ("site", "near"):
                    members.append((VI[id(v)], w, -1))
                else:
                    for g in GROUPS:
                        comp_pre[g] += in_group(v, g)
                continue
            else:
                continue
            w = where_is(v)
            if w in ("site", "near"):
                members.append((VI[id(v)], w, k))
            cnt[w]["all"][k] += 1
            if v["sev"]:
                cnt[w]["severe"][k] += 1
            if v["role"] == "Pedestrian":
                cnt[w]["ped"][k] += 1
            elif v["role"] == "Bicyclist":
                cnt[w]["bike"][k] += 1
        def block(place, extra_place=None):
            o = {}
            for g in GROUPS:
                b, a = cnt[place][g]
                if extra_place:
                    b += cnt[extra_place][g][0]; a += cnt[extra_place][g][1]
                d_, c_ = cnt["city"][g][0] + cnt["ring"][g][0], cnt["city"][g][1] + cnt["ring"][g][1]
                est, lo, hi = rr(a, b, c_, d_)
                o[g] = {"before": b, "after": a, "rr": [round(est, 3), round(lo, 3), round(hi, 3)]}
                rb, ra = cnt["ring"][g]
                e2, l2, h2 = rr(a, b, ra, rb)
                o[g]["rrRing"] = [round(e2, 3), round(l2, 3), round(h2, 3)]
            return o
        site_o, near_o = block("site"), block("site", "near")
        row = {"label": label, "kind": kind, "start": start.isoformat(), "years": round(yrs, 2), "note": note, "claim": claim_key,
               "before": [before0.isoformat(), before1.isoformat()], "after": [after0.isoformat(), after1.isoformat()],
               "site": dict(site_o["all"], severeBefore=site_o["severe"]["before"], severeAfter=site_o["severe"]["after"], groups=site_o),
               "near": dict(near_o["all"], severeBefore=near_o["severe"]["before"], severeAfter=near_o["severe"]["after"], groups=near_o),
               "city": {"before": cnt["city"]["all"][0] + cnt["ring"]["all"][0], "after": cnt["city"]["all"][1] + cnt["ring"]["all"][1],
                        "groups": {g: {"before": cnt["city"][g][0] + cnt["ring"][g][0], "after": cnt["city"][g][1] + cnt["ring"][g][1]} for g in GROUPS}},
               "ring": {"before": cnt["ring"]["all"][0], "after": cnt["ring"]["all"][1], "groups": {g: {"before": cnt["ring"][g][0], "after": cnt["ring"][g][1]} for g in GROUPS}},
               "segments": sorted(site_segs), "nearSegments": sorted(buf_segs), "_m": members, "_compPre": comp_pre, "_area": area,
               "pre": [pre0.isoformat(), pre1.isoformat()]}
        if extra:
            row.update(extra)
        if record:
            sites.append(row)
        return row

    # cameras: group the dataset's sites into locations by street and 400 ft
    cam = sfdata.fetch("d5uh-bk84", floor=1000)
    cam_sites = {}
    for x in cam.rows:
        sid = x["site_id"]
        m = re.match(r"(NB|SB|EB|WB) (\d+) (.*)", x["location"])
        st = norm(m.group(3))
        la, lo = float(x["latitude"]), float(x["longitude"])
        s = cam_sites.setdefault(sid, {"id": sid, "street": st, "lon": lo, "lat": la, "first": x["date"][:10], "dir": m.group(1), "addr": m.group(2), "limit": x.get("posted_speed")})
        s["first"] = min(s["first"], x["date"][:10])
    locs = []
    for s in sorted(cam_sites.values(), key=lambda s: s["id"]):
        p = xy(s["lon"], s["lat"])
        for L in locs:
            # SFMTA's 33 "enforcement locations": the two cameras of one location face opposite ways on the same
            # street, up to about 2,600 ft apart (the Embarcadero's pair, Green St to Battery St). Two locations on one street are a mile apart.
            if L["street"] == s["street"] and math.dist(p, xy(L["lon"], L["lat"])) <= CAM_PAIR_FT:
                L["cams"].append(s); L["first"] = min(L["first"], s["first"])
                break
        else:
            locs.append({"street": s["street"], "lon": s["lon"], "lat": s["lat"], "first": s["first"], "cams": [s], "addr": s["addr"], "limit": s["limit"]})
    cam_rows = []
    for L in locs:
        site_segs = set()
        for c0 in L["cams"]:
            # the camera's block: the nearest segment of its own street (a camera sits mid-block at an address)
            px0, py0 = xy(c0["lon"], c0["lat"])
            cands = [(min(float(seg_dist(px0, py0, a[0], a[1], b[0], b[1])) for a, b in zip(S.seg[c]["P"], S.seg[c]["P"][1:])), c)
                     for c in S.by_street.get(L["street"], []) if len(S.seg[c]["P"]) > 1]
            cnn = min(cands)[1]
            site_segs.add(cnn)
            for c in S.by_street.get(L["street"], []):   # the other carriageway of a divided street at the same block
                if c != cnn and math.dist(S.seg[c]["mid"], S.seg[cnn]["mid"]) <= PAIR_FT:
                    site_segs.add(c)
        site_nodes = {S.seg[c]["f"] for c in site_segs} | {S.seg[c]["t"] for c in site_segs}
        row = evaluate("%s, %s block" % (pretty(L["street"]), L["addr"]), "camera", site_segs, site_nodes, D.fromisoformat(L["first"]),
                       "in the camera data from %s, %s" % (L["first"], " and ".join(sorted({c["dir"] for c in L["cams"]}))), "camera",
                       {"lon": L["lon"], "lat": L["lat"], "limit": L["limit"], "cameraSites": sorted(c["id"] for c in L["cams"]), "blocks": len(site_segs)})
        cam_rows.append(row)
    # pooled cameras: sum the per-location counts (each location has its own windows)
    def mh(tables):
        """Mantel-Haenszel pooled ratio of (a/b)/(c/d) over strata (a, b, c, d), with the Robins, Breslow and
        Greenland variance of its log. Each location is a stratum with its own windows."""
        R = S_ = 0.0
        PR = PSQR = QS = 0.0
        for a, b, c, d in tables:   # no zero-cell correction: MH sums over strata, the same estimator as pooled()
            N = a + b + c + d
            if N == 0:
                continue
            P, Q, Ri, Si = (a + d) / N, (b + c) / N, a * d / N, b * c / N
            R += Ri; S_ += Si
            PR += P * Ri; PSQR += P * Si + Q * Ri; QS += Q * Si
        est = R / S_
        var = PR / (2 * R * R) + PSQR / (2 * R * S_) + QS / (2 * S_ * S_)
        se = math.sqrt(var)
        return est, est * math.exp(-1.96 * se), est * math.exp(1.96 * se)

    def pooled(rows, label):
        """Pool a fix's rows (Fable skeptic review, 2026-10-20). Each person counts once per pool: a person inside the
        site or two blocks of several rows is split evenly across the rows whose site holds them (else whose two blocks
        do), each share in that row's window, so overlap neither double counts nor leans to the before or after side. The ratio is Mantel-Haenszel over the rows against the rest of the city
        (each row's own windows). Its 95% range is a bootstrap that resamples the pool's crashes (case_id), BOOT reps
        with a fixed seed, so multi-victim crashes widen it; the comparison counts, thousands per window, are held
        fixed. p is from the bootstrap's spread of the log ratio. The placebo repeats it one window earlier, the
        before window against the window before that, where a real fix should show no change."""
        out = {"label": label, "n": len(rows), "years": round(sum(r["years"] for r in rows) / len(rows), 2), "site": {}, "near": {}, "city": {}, "ring": {}}
        rng = np.random.default_rng(BOOT_SEED)
        for place in ("site", "near"):
            for g in GROUPS:
                for kb, ka, tag_ in ((0, 1, "main"), (-1, 0, "placebo")):
                    # vi -> [(row, window, weight)]. The weight comes from place alone: the rows whose site holds the
                    # person's location (else whose two blocks do), whatever the date, split evenly. Then each row
                    # counts its share only if the person falls in that row's two windows being compared.
                    claim = collections.defaultdict(list)
                    for i, r in enumerate(rows):
                        for vi, w, k in r["_m"]:
                            if k not in (kb, ka) or (place == "site" and w != "site") or not in_group(V[vi], g):
                                continue
                            homes = [j for j, q in enumerate(rows) if q["_area"].get(vi) == "site"]
                            if place == "near" and not homes:
                                homes = [j for j, q in enumerate(rows) if vi in q["_area"]]
                            if i in homes:
                                claim[vi].append((i, k, 1 / len(homes)))
                    nS = len(rows)
                    if tag_ == "main":
                        c = np.array([r["city"]["groups"][g]["after"] for r in rows], float); d = np.array([r["city"]["groups"][g]["before"] for r in rows], float)
                    else:
                        c = np.array([r["city"]["groups"][g]["before"] for r in rows], float); d = np.array([r["_compPre"][g] for r in rows], float)
                    cases = sorted({V[vi]["case"] or ("v%d" % vi) for vi in claim})
                    ci_ = {cs: j for j, cs in enumerate(cases)}
                    M = np.zeros((max(1, len(cases)), 2 * nS))
                    for vi, cs in claim.items():
                        for i, k, wt in cs:
                            M[ci_[V[vi]["case"] or ("v%d" % vi)], i + (0 if k == ka else nS)] += wt
                    obs = M.sum(0)
                    a, b = obs[:nS], obs[nS:]
                    def mhv(a, b):
                        N = a + b + c + d
                        N = np.where(N == 0, 1, N)
                        return (a * d / N).sum(-1) / np.maximum((b * c / N).sum(-1), 1e-9)
                    est = float(mhv(a, b))
                    o = {"before": round(float(b.sum())), "after": round(float(a.sum()))}
                    if len(cases) and a.sum() and b.sum():
                        Wt = rng.multinomial(len(cases), np.full(len(cases), 1 / len(cases)), size=BOOT)
                        B = Wt @ M
                        bs = mhv(B[:, :nS], B[:, nS:])
                        bs = bs[bs > 0]
                        lo_, hi_ = np.percentile(bs, [2.5, 97.5])
                        se = float(np.std(np.log(bs)))
                        pv = math.erfc(abs(math.log(est)) / se / math.sqrt(2)) if se > 0 and est > 0 else 1.0
                        o.update(rr=[round(est, 3), round(float(lo_), 3), round(float(hi_), 3)], p=pv, crashes=len(cases))
                    else:
                        o.update(rr=[round(est, 3), 0, 0], p=1.0, crashes=len(cases))
                    if tag_ == "main":
                        o["summed"] = {"before": sum(r[place]["groups"][g]["before"] for r in rows), "after": sum(r[place]["groups"][g]["after"] for r in rows)}
                        e2, l2, h2 = mh([(a[i], b[i], r["ring"]["groups"][g]["after"], r["ring"]["groups"][g]["before"]) for i, r in enumerate(rows)])
                        o["rrRing"] = [round(e2, 3), round(l2, 3), round(h2, 3)]
                        out[place][g] = o
                    else:
                        out[place][g]["placebo"] = o
        for g in GROUPS:
            out["city"][g] = {"before": sum(r["city"]["groups"][g]["before"] for r in rows), "after": sum(r["city"]["groups"][g]["after"] for r in rows)}
            out["ring"][g] = {"before": sum(r["ring"]["groups"][g]["before"] for r in rows), "after": sum(r["ring"]["groups"][g]["after"] for r in rows)}
        for place in ("site", "near"):
            out[place].update(out[place]["all"])
        return out

    def pooled_old(rows, label):
        out = {"label": label, "n": len(rows), "years": round(sum(r["years"] for r in rows) / len(rows), 2), "site": {}, "near": {}, "city": {}, "ring": {}}
        for g in GROUPS:
            c = sum(r["city"]["groups"][g]["after"] for r in rows); d = sum(r["city"]["groups"][g]["before"] for r in rows)
            rc = sum(r["ring"]["groups"][g]["after"] for r in rows); rd = sum(r["ring"]["groups"][g]["before"] for r in rows)
            for place in ("site", "near"):
                a = sum(r[place]["groups"][g]["after"] for r in rows); b = sum(r[place]["groups"][g]["before"] for r in rows)
                e, lo, hi = mh([(r[place]["groups"][g]["after"], r[place]["groups"][g]["before"], r["city"]["groups"][g]["after"], r["city"]["groups"][g]["before"]) for r in rows])
                o = {"before": b, "after": a, "rr": [round(e, 3), round(lo, 3), round(hi, 3)]}
                e2, l2, h2 = mh([(r[place]["groups"][g]["after"], r[place]["groups"][g]["before"], r["ring"]["groups"][g]["after"], r["ring"]["groups"][g]["before"]) for r in rows])
                o["rrRing"] = [round(e2, 3), round(l2, 3), round(h2, 3)]
                out[place][g] = o
            out["city"][g] = {"before": d, "after": c}
            out["ring"][g] = {"before": rd, "after": rc}
        for place in ("site", "near"):
            out[place].update(out[place]["all"])
        return out
    cam_pool = pooled(cam_rows, "All %d speed camera locations" % len(cam_rows))
    # citations began 2025-08-05 at every location (d5uh-bk84 issued_citations); the same locations counted from then
    cite_rows = [evaluate(r["label"], "camera", set(r["segments"]), {S.seg[c]["f"] for c in r["segments"]} | {S.seg[c]["t"] for c in r["segments"]},
                          CAM_CITE, r["note"], "camera", record=False) for r in cam_rows]
    cam_cite = pooled(cite_rows, "All %d speed camera locations, from citations" % len(cite_rows))
    cam_pool["fromCitations"] = {"start": CAM_CITE.isoformat(), "years": cam_cite["years"], "site": {k: cam_cite["site"][k] for k in ("before", "after", "rr")},
                                 "near": {k: cam_cite["near"][k] for k in ("before", "after", "rr")}}
    cam_pool["warningFirst"] = [min(L["first"] for L in locs), max(L["first"] for L in locs)]
    # how long until the pooled camera count could show a 20% drop: 1.96*sqrt(2/n) <= ln(1/0.8) over equal windows
    n_need = 2 * (1.96 / math.log(1 / 0.8)) ** 2
    rate = cam_pool["site"]["before"] / cam_pool["years"] if cam_pool["years"] else 0   # pooled injuries a year, before
    cam_pool["needPerWindow"] = round(n_need)
    cam_pool["yearsNeeded"] = round(n_need / rate, 1) if rate else None
    rate2 = cam_pool["near"]["before"] / cam_pool["years"] if cam_pool["years"] else 0
    cam_pool["yearsNeededNear"] = round(n_need / rate2, 1) if rate2 else None

    # corridors
    unmatched, qb_rows = [], []
    for label, street, x, y, start, stated, src in CORRIDORS:
        ids, how = S.corridor(street, x, y)
        if not ids:
            unmatched.append((label, how)); continue
        nodes = {S.seg[c]["f"] for c in ids} | {S.seg[c]["t"] for c in ids}
        row = evaluate(label, "quickbuild", ids, nodes, D.fromisoformat(start), "SFMTA: %s" % stated, src,
                       {"street": norm(street), "extent": "%s to %s" % (pretty(x), pretty(y)), "miles": round(sum(S.seg[c]["ft"] for c in ids) / 5280, 2),
                        "pathMiles": round(S.last_path_ft / 5280, 2), "blocks": len(ids)})
        qb_rows.append(row)
    qb_pool = pooled(qb_rows, "All %d corridors" % len(qb_rows))
    # SFMTA's Tenderloin four, for its 44% claim
    tl4 = [r for r in qb_rows if r["label"].split(" ")[0] in ("Golden", "Jones", "Leavenworth", "Taylor")]
    tl_pool = pooled(tl4, "Tenderloin quick-builds (Golden Gate, Jones, Leavenworth, Taylor)")

    # Tenderloin daylighting: intersections inside the quadrilateral
    corners = []
    for a, b in TL_CORNERS:
        ns = S.meeting(a, b)
        if not ns:
            unmatched.append(("Tenderloin corner %s/%s" % (a, b), "not found")); continue
        # Market/Mason is the node nearest to Mason's own end; take the node nearest the mean of the candidates
        pts = [S.node_xy[n] for n in ns]
        corners.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    def inside(p, poly):
        x, y = p; ins = False
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                ins = not ins
        return ins
    def edge_dist(p, poly):
        return min(along(p, [a, b])[2] for a, b in zip(poly, poly[1:] + poly[:1]))
    tl_nodes = set()
    if len(corners) == 4:
        for n, p in S.node_xy.items():
            if inside(p, corners) or edge_dist(p, corners) <= 30:
                # an intersection of two of the area's named streets, not an alley mouth or a mid-block node
                if len({S.seg[c]["street"] for c in S.at_node[n]} & TL_STREETS) >= 2:
                    tl_nodes.add(n)
    def in_area(n):
        p = S.node_xy[n]
        return len(corners) == 4 and (inside(p, corners) or edge_dist(p, corners) <= 30)
    tl_segs = {c for st in TL_STREETS for c in S.by_street.get(st, []) if in_area(S.seg[c]["f"]) and in_area(S.seg[c]["t"])}
    tl_site_nodes = tl_nodes | {S.seg[c]["f"] for c in tl_segs} | {S.seg[c]["t"] for c in tl_segs}
    tl_row = evaluate("Tenderloin daylighting, %d intersections" % len(tl_nodes), "daylighting", tl_segs, tl_site_nodes, D.fromisoformat(TL_START),
                      "SFMTA: 80 intersections, red zones in place by March 2015", "tl_day", {"intersections": len(tl_nodes), "blocks": len(tl_segs), "corners": [[round(c[0]), round(c[1])] for c in corners]})

    tl_row["pooled"] = pooled([tl_row], "Tenderloin daylighting")

    # map data
    def paths(ids):
        return [S.seg[c]["pts"] for c in sorted(ids)]
    # Kids in the window, sorted by their rounded point; the full point is kept for the distance to each school, and
    # the last field is nwes-mmgh's own victim_degree_of_injury read as severe or fatal, the "Severe and fatal only" rule.
    kids = sorted([round(v["lon"], 4), round(v["lat"], 4), v["lon"], v["lat"], v["sev"]] for v in W if v["kid"])
    out = {
        "source": {"victimsFetched": vdate, "centerlinesFetched": S.fetched, "camerasFetched": cam.fetched_on.isoformat(), "hinFetched": hin_file["fetched_on"],
                   "dataEnd": END.isoformat(), "lastMonthRows": months[last], "lastMonth": "%d-%02d" % last, "unsnappedAll": unsnapped, "victims": len(V)},
        "where": where,
        "cameras": {"rows": cam_rows, "pooled": cam_pool, "locations": len(cam_rows), "sites": len(cam_sites)},
        "corridors": {"rows": qb_rows, "pooled": qb_pool, "tenderloinPooled": tl_pool, "unmatched": unmatched},
        "daylighting": tl_row,
        "windowYears": WINDOW_YEARS,
        "map": {
            "hin": [r["pts"] for r in hin_file["records"]],
            "corridorPaths": [{"label": r["label"], "paths": paths(r["segments"])} for r in qb_rows],
            "cameraPoints": [[round(r["lon"], 5), round(r["lat"], 5), r["label"]] for r in cam_rows],
            "tlPolygon": [[round(((c[0] / FT_LON) - 122.44), 5), round((c[1] / FT_LAT) + 37.76, 5)] for c in corners],
            "allPoints": sorted([round(v["lon"], 4), round(v["lat"], 4)] for v in W),
            "severePoints": sorted([round(v["lon"], 4), round(v["lat"], 4)] for v in W if v["sev"]),
            "kidPoints": [k[:2] for k in kids],
            # indices into kidPoints of the kids severely hurt or killed
            "kidSevere": [i for i, k in enumerate(kids) if k[4]],
        },
    }
    # Per-project geometry for the page's details panels: the site's centerlines and the rest of its two blocks,
    # coordinates rounded to 5 decimals (about 3 ft), in the order of `sites`.
    def r5(ids):
        return [[[round(c[0], 5), round(c[1], 5)] for c in S.seg[i]["pts"]] for i in sorted(ids)]
    out["projects"] = [{"label": r["label"], "kind": r["kind"], "start": r["start"], "note": r["note"], "claim": r["claim"],
                        "site": r5(r["segments"]), "near": r5(set(r["nearSegments"]) - set(r["segments"]))} for r in sites]
    for r in sites:
        r.pop("segments", None); r.pop("nearSegments", None); r.pop("_m", None); r.pop("_compPre", None); r.pop("_area", None)
    # "Show fixes" map layers (Bryan, thread cxjvmefmvfmu): interventions from the last ten years and planned ones, each
    # drawn on the centerline blocks its row names (cnn), or as a point where the dataset gives one.
    def segpts(c):
        try:
            sg = S.seg.get(int(float(c)))
        except (TypeError, ValueError):
            return None
        return [[round(x, 5), round(y, 5)] for x, y in sg["pts"]] if sg else None
    def ms(v):
        try:
            return datetime.datetime.fromtimestamp(int(v) / 1000, datetime.timezone.utc).date().isoformat()
        except (TypeError, ValueError):
            return (v or "")[:10] or None
    fx = {}
    fx["to20"] = [{"p": segpts(c), "date": dates[c]} for c in sorted(segs) if segpts(c)]
    SLW = sfdata.fetch("hkz3-itiu", select="cnn,streetname,extents,status,install_date", floor=200)
    fx["slow"] = [{"p": segpts(r["cnn"]), "name": f'{pretty(r.get("streetname") or "")} Slow Street', "ext": r.get("extents") or "",
                   "date": (r.get("install_date") or "")[:10], "planned": r.get("status") == "Planned"} for r in SLW.rows if segpts(r.get("cnn"))]
    MID = sfdata.fetch("abhw-ffzx", select="cnn,streetname,from_st,to_st,tc_measure,install_yr,current_status", floor=1000)
    IXC = sfdata.fetch("bp3t-bd4t", select="cnn,streetname,from_st,tc_measure,install_yr,current_status,shape", floor=200)
    def yr(v):
        return int(v) if (v or "").isdigit() and 1990 < int(v) < 2100 else None
    fx["calm"] = []
    for r in MID.rows:
        st, y, pp = r.get("current_status") or "", yr(r.get("install_yr")), segpts(r.get("cnn"))
        if not pp or st == "Obsolete":
            continue
        if st == "Complete" and (y or 0) >= 2016 or st.startswith("Pending"):
            fx["calm"].append({"p": pp, "name": (r.get("tc_measure") if r.get("tc_measure") not in (None, "<Null>") else "Traffic calming"),
                               "where": f'{pretty(r.get("streetname") or "")}, {r.get("from_st") or ""} to {r.get("to_st") or ""}', "date": str(y or ""), "planned": st.startswith("Pending"), "status": st})
    fx["calmPts"] = []
    for r in IXC.rows:
        st, y, sh = r.get("current_status") or "", yr(r.get("install_yr")), r.get("shape") or {}
        if not sh.get("coordinates") or not (st == "Complete" and (y or 0) >= 2016 or st.lower().startswith("pending")):
            continue
        fx["calmPts"].append({"c": [round(sh["coordinates"][0], 5), round(sh["coordinates"][1], 5)], "name": r.get("tc_measure") or "Traffic calming",
                              "where": f'{pretty(r.get("streetname") or "")} at {r.get("from_st") or ""}', "date": str(y or ""), "planned": st.lower().startswith("pending"), "status": st})
    PSZ = sfdata.fetch("vtn2-q8ky", select="cnn,location,install_da,mtab_date,shape", floor=200)
    fx["psz"] = [{"c": [round(r["shape"]["coordinates"][0], 5), round(r["shape"]["coordinates"][1], 5)], "where": r.get("location") or "", "date": ms(r.get("install_da"))}
                 for r in PSZ.rows if (r.get("shape") or {}).get("coordinates")]
    PROJ = json.load(open(os.path.join(ROOT, "out", "project-record", "projects.json")))["projects"]
    FUTURE = ("planning", "design", "detailed design", "legislated", "bid & award", "construction", "implementation")
    fx["planned"] = []
    for pr in PROJ:
        ph = (pr.get("phase") or "").lower()
        if not pr.get("id", "").startswith("sfmta:") or not ph or not any(ph.startswith(f) for f in FUTURE) or "complete" in ph:
            continue
        paths_ = [q for q in (segpts(c) for c in pr.get("cnns") or []) if q]
        if paths_:
            n = pr["name"].lower()   # the record has no type field, so the type comes from the project's own name
            kind = ("qb" if "quick-build" in n else "sig" if "signal" in n else "bike" if any(w in n for w in ("bike", "slow street", "pathway")) else
                    "safety" if any(w in n for w in ("safety", "calming")) else "area")
            fx["planned"].append({"name": pr["name"], "phase": pr.get("phase"), "page": pr.get("page"), "end": pr.get("end"), "kind": kind, "paths": paths_})
    fx["fetched"] = {"to20": SL.fetched_on.isoformat(), "slow": SLW.fetched_on.isoformat(), "calm": MID.fetched_on.isoformat(), "calmPts": IXC.fetched_on.isoformat(),
                     "psz": PSZ.fetched_on.isoformat(), "planned": json.load(open(os.path.join(ROOT, "out", "project-record", "projects.json")))["generated"]}
    out["map"]["fixes"] = fx
    out["schools"] = school_rings(kids)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print("injury-map: wrote %s, %d KB" % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT) // 1024), file=sys.stderr)
    summary = {"source": out["source"], "where": {k: where[k] for k in ("from", "to", "all", "severe", "unsnapped", "mainMiles", "streetMiles", "hinMiles", "cause", "place", "fault")},
               "cameras": {"pooled": cam_pool, "locations": len(cam_rows), "sites": len(cam_sites)},
               "corridorsPooled": qb_pool, "tenderloinPooled": tl_pool, "unmatched": unmatched,
               "daylighting": {k: tl_row[k] for k in ("label", "site", "near", "city", "years")},
               "corridors": [(r["label"], r["miles"], r["site"]["before"], r["site"]["after"], r["site"]["rr"], r["site"]["rrRing"], r["near"]["before"], r["near"]["after"], r["near"]["rr"], r["near"]["rrRing"]) for r in qb_rows],
               "cameraRows": [(r["label"], r["blocks"], r["site"]["before"], r["site"]["after"], r["near"]["before"], r["near"]["after"]) for r in cam_rows]}
    print(json.dumps(summary, indent=1, default=str))



def school_rings(kids):
    """Each School Trips school's grounds, 500 ft zone and quarter-mile ring as outer rings of [lon, lat], and the
    indices into `kids` (map.kidPoints) inside the quarter-mile ring. Rings are grown the way
    tools/school-trips/school-grounds.py grows its 500 ft zone, so the 500 ft ring here is that zone. A kid counts when the point
    the page draws (rounded to 4 decimals) lies inside or on the ring the page draws, so every dot inside the dashed
    ring is in the count and none outside it is. That ring is the grounds grown by QUARTER_FT and simplified to 8 ft,
    and the dots are rounded to about 35 ft, so a kid within about 40 ft of the quarter mile can fall either side."""
    import shapely
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    from shapely import affinity
    from lib import school_grounds, school_points
    idx = school_points.index_schools()
    klon = np.array([k[0] for k in kids], float)
    klat = np.array([k[1] for k in kids], float)
    rows = []
    for s in idx:
        lon, lat = s["lon"], s["lat"]
        rs = school_grounds.rings(lon, lat)
        g = unary_union([Polygon([((x - lon) * FT_LON, (y - lat) * FT_LAT) for x, y in q]).buffer(0) for q in rs]) if rs else Point(0, 0).buffer(1)

        def outer(geom):
            geom = affinity.translate(affinity.scale(geom, 1 / FT_LON, 1 / FT_LAT, origin=(0, 0)), lon, lat)
            return [[[round(x, 5), round(y, 5)] for x, y in p.exterior.coords] for p in getattr(geom, "geoms", [geom])]
        quarter = outer(g.buffer(QUARTER_FT, quad_segs=6).simplify(8))
        drawn = unary_union([Polygon(r) for r in quarter])
        near = np.nonzero(shapely.intersects_xy(drawn, klon, klat))[0] if len(kids) else []
        rows.append({"cds": s["cds"], "name": s["name"], "lon": lon, "lat": lat, "grounds": outer(g.simplify(3)),
                     "zone": outer(g.buffer(ZONE_FT, quad_segs=6).simplify(8)), "quarter": quarter, "kids": [int(i) for i in near]})
    assert len(rows) == len(idx) and len({r["cds"] for r in rows}) == len(rows), "school rows not one per school"
    return rows


if __name__ == "__main__":
    main()
