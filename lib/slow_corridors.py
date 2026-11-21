"""The pandemic Slow Street corridors SFMTA's Board reports name, resolved to centerline blocks.

Shared by tools/bike-network/bike-network-history.py, which counts the corridors SFMTA
later dropped in the years they stood (reach only, not miles), and by
tools/bike-network/bike-removals.py, which lists them as removals. Everything here reads
only the street centerline (DataSF 3psu-pn9h, through the sfdata cache) and the
Slow Streets extract (DataSF hkz3-itiu), never another step's output, so the
history can import it without reading bike-removals.py's output, which reads
the history's.

Per block of a corridor, `status` is:

  kept       in hkz3-itiu today, installed before READOPTED_FROM: part of
             the program throughout;
  readopted  in hkz3-itiu today with an install date of READOPTED_FROM or
             later: out of the program from DROPPED_YEAR until that date
             (`back`);
  out        not in hkz3-itiu today. bike-removals.py splits these into
             `replaced` (all-ages today as another bikeway) and `removed`.

The 2022 report dropped or shortened the corridors on 2022-12-06. The
network state for a year is its state at the year's end, so a block that is
not kept is counted from its corridor's install year through DROPPED_YEAR - 1.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import heapq
import json
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import sfdata  # noqa: E402

CENTERLINES = "3psu-pn9h"
SLOW_STREETS = os.path.join(ROOT, "data", "extract", "slow-streets", "segments.json")
MI = 1609.344
# A corridor block is in the Slow Streets program today when hkz3-itiu's lines
# lie within KEPT_M of it over KEPT_COVER of its length.
KEPT_M = 15.0
KEPT_COVER = 0.5

REPORT_2020 = {"title": "7-21-20 MTAB Item 12, Traffic Modifications - Slow Streets Corridors (staff report)",
               "url": "https://www.sfmta.com/media/23090/download?inline", "read": "2026-09-29"}
REPORT_2021 = {"title": "4-6-21 MTAB Item 12, Traffic Modifications - Slow Streets (staff report)",
               "url": "https://www.sfmta.com/media/26282/download?inline", "read": "2026-09-29"}
REPORT_2022 = {"title": "12-6-22 MTAB Item 14, TC Amendment - Slow Streets Program (staff report)",
               "url": "https://www.sfmta.com/media/33575/download?inline", "read": "2026-09-29"}
PROGRAM_PAGE = {"title": "SFMTA, Slow Streets Program", "url": "https://www.sfmta.com/projects/slow-streets-program",
                "read": "2026-09-29"}
REPORTS = {"2020": REPORT_2020, "2021": REPORT_2021, "2022": REPORT_2022}

# The year SFMTA's December 2022 report (Resolution 221206-116) dropped or
# shortened the pandemic corridors. A block the program did not keep is
# all-ages from its corridor's install year through DROPPED_YEAR - 1, and out
# from DROPPED_YEAR. The site draws it removed in this year only.
DROPPED_YEAR = 2022
# An hkz3-itiu row installed in this year or later postdates the pandemic
# program: a corridor block it covers was dropped and re-adopted, not kept.
# The 2022 report (p. 9) scheduled what materials remained for removal "in the
# Winter 2023".
READOPTED_FROM = 2023

# Each corridor: the report's words for it, the centerline name of the street,
# the cross streets at either end (alternatives in a tuple), the phase the
# 2022 report puts it in, the report that gives its extent, the year it went
# in, and what the 2022 report did with it ("removed", or "kept" for a
# corridor whose program extent may be shorter than its pandemic one).
# Phases 1 and 2 were in place by 2020-07-21 ("has already planned and
# implemented these barricades", 2020 report p. 4; "Beginning in April 2020");
# Phase 3 was approved that day and Phase 4 on 2021-04-06.
C = collections.namedtuple("C", "id words street a b phase report year fate")
CORRIDORS = [
    # Phase 1, removed.
    C("20th-ave", "20th Avenue from Lincoln Boulevard to Ortega Street", "20TH AVE", "LINCOLN WAY", "ORTEGA ST", 1, "2020", 2020, "removed"),
    C("41st-ave", "41st Avenue from Lincoln Way to Vicente Street", "41ST AVE", "LINCOLN WAY", "VICENTE ST", 1, "2020", 2020, "removed"),
    C("kirkham", "Kirkham Street from Great Highway to Seventh Avenue", "KIRKHAM ST", ("GREAT HWY", "LA PLAYA"), "07TH AVE", 1, "2020", 2020, "removed"),
    C("ortega", "Ortega Street from 47th to 15th avenues", "ORTEGA ST", "47TH AVE", "15TH AVE", 1, "2020", 2020, "removed"),
    # Phase 2, removed.
    C("20th-st-mission", "20th Street from Valencia Street to Potrero Avenue", "20TH ST", "VALENCIA ST", "POTRERO AVE", 2, "2020", 2020, "removed"),
    C("chenery", "Chenery Street from Burnside Avenue to Lippard Avenue", "CHENERY ST", "BURNSIDE AVE", "LIPPARD AVE", 2, "2020", 2020, "removed"),
    C("excelsior", "Excelsior Avenue from London to Munich streets", "EXCELSIOR AVE", "LONDON ST", "MUNICH ST", 2, "2020", 2020, "removed"),
    C("lombard", "Lombard Street", "LOMBARD ST", None, None, 2, "2022", 2020, "removed"),
    C("mariposa-west", "Mariposa Street from Kansas to Texas streets", "MARIPOSA ST", "KANSAS ST", "TEXAS ST", 2, "2020", 2020, "removed"),
    # Phase 3, removed.
    # The 2022 report names "20th Street" and "Mariposa Street" under Phase 2
    # only; their Phase 3 pieces are read as dropped too [inference], since
    # neither street is among the 15 program corridors.
    C("20th-st-potrero", "20th Street from San Bruno to Pennsylvania", "20TH ST", "SAN BRUNO AVE", "PENNSYLVANIA AVE", 3, "2020", 2020, "removed"),
    C("arkansas", "Arkansas from 23rd to 17th streets", "ARKANSAS ST", "23RD ST", "17TH ST", 3, "2020", 2020, "removed"),
    C("broderick", "Broderick from O'Farrell to Page", "BRODERICK ST", "OFARRELL ST", "PAGE ST", 3, "2020", 2020, "removed"),
    C("duncan", "Duncan from Diamond Heights to Tiffany", "DUNCAN ST", "DIAMOND HEIGHTS BLVD", "TIFFANY AVE", 3, "2020", 2020, "removed"),
    C("mariposa-east", "Mariposa from Texas to Mississippi", "MARIPOSA ST", "TEXAS ST", "MISSISSIPPI ST", 3, "2020", 2020, "removed"),
    C("pacific", "Pacific from Steiner to Gough", "PACIFIC AVE", "STEINER ST", "GOUGH ST", 3, "2020", 2020, "removed"),
    C("tompkins", "Tompkins from Andover to Peralta", "TOMPKINS AVE", "ANDOVER ST", "PERALTA AVE", 3, "2020", 2020, "removed"),
    # Phase 4. The 2022 report lists the SoMa alleys as not recommended, and
    # the Board adopted them into the program on 2023-05-16 (Resolution
    # 230516-043). hkz3-itiu dates them 1899-12-29, its null, which
    # bike-network-history.py counts from 2022 (SLOW_STREETS_APPROVED); they
    # are read as kept here too, so the map never shows them removed. Whether
    # their materials came out between December 2022 and May 2023 is not in
    # the records read. The five alleys lie wholly between Folsom and
    # Harrison, so every block of them is the corridor ("*").
    C("soma", "Lapu Lapu/Rizal/Tandang Sora/Bonifacio/Mabini streets from Folsom Street to Harrison Street",
      ("LAPU-LAPU ST", "RIZAL ST", "TANDANG SORA", "BONIFACIO ST", "MABINI ST"), "*", "*", 4, "2021", 2021, "kept"),
    # Kept by the 2022 report; any block of the pandemic extent outside the
    # program today was trimmed. The report's resolution gives the shorter
    # program extents itself (12th Avenue "from Lincoln Way to Lawton Street",
    # Noe Street "from Duboce Avenue to Beaver Street"). Lake Street (no
    # recommendation in the report) and Page Street (not in it; its own Board
    # project) are "kept" because hkz3-itiu carries them from 2020. Cayuga
    # Avenue, approved in 2020, entered as a new program street in 2022, so it
    # is in neither list below. Phase numbers for kept corridors are
    # approximate: the 2020 report lumps Phases 1 and 2 together.
    C("12th-ave", "12th Avenue from Lincoln Way to Noriega Street", "12TH AVE", "LINCOLN WAY", "NORIEGA ST", 4, "2021", 2021, "kept"),
    C("23rd-ave", "23rd Avenue from Lake to Cabrillo streets", "23RD AVE", "LAKE ST", "CABRILLO ST", 2, "2020", 2020, "kept"),
    C("arlington", "Arlington from Roanoke to Randall", "ARLINGTON ST", "ROANOKE ST", "RANDALL ST", 3, "2020", 2020, "kept"),
    C("cabrillo", "Cabrillo Street from 45th to 23rd avenues", "CABRILLO ST", "45TH AVE", "23RD AVE", 3, "2020", 2020, "kept"),
    C("clay", "Clay Street from Arguello to Steiner", "CLAY ST", "ARGUELLO BLVD", "STEINER ST", 3, "2020", 2020, "kept"),
    C("golden-gate", "Golden Gate Avenue from Masonic Avenue to Broderick Street", "GOLDEN GATE AVE", "MASONIC AVE", "BRODERICK ST", 2, "2020", 2020, "kept"),
    C("hearst", "Hearst from Ridgewood to Baden", "HEARST AVE", "RIDGEWOOD AVE", "BADEN ST", 3, "2020", 2020, "kept"),
    C("lake", "Lake Street from 28th to Second avenues", "LAKE ST", "28TH AVE", "02ND AVE", 1, "2020", 2020, "kept"),
    # The centerline has no Lyon Street block across the Panhandle, so the
    # corridor is resolved in two pieces.
    C("lyon", "Lyon Street from Turk Street to Haight Street", "LYON ST", ("TURK ST", "TURK BLVD"), "FELL ST", 4, "2021", 2021, "kept"),
    C("lyon-south", "Lyon Street from Turk Street to Haight Street", "LYON ST", "OAK ST", "HAIGHT ST", 4, "2021", 2021, "kept"),
    C("minnesota", "Minnesota from Mariposa to 22nd Street", "MINNESOTA ST", "MARIPOSA ST", "22ND ST", 3, "2020", 2020, "kept"),
    C("noe", "Noe from 23rd Street to Duboce", "NOE ST", "23RD ST", "DUBOCE AVE", 3, "2020", 2020, "kept"),
    C("page", "Page Street from Stanyan to Gough streets", "PAGE ST", "STANYAN ST", "GOUGH ST", 1, "2020", 2020, "kept"),
    C("sanchez", "Sanchez Street from 23rd to 30th streets", "SANCHEZ ST", "23RD ST", "30TH ST", 1, "2020", 2020, "kept"),
    C("shotwell", "Shotwell Street from Cesar Chavez to 14th Street", "SHOTWELL ST", "CESAR CHAVEZ ST", "14TH ST", 1, "2020", 2020, "kept"),
    C("somerset", "Somerset Street from Silver Avenue to Woolsey Street", "SOMERSET ST", "SILVER AVE", "WOOLSEY ST", 2, "2020", 2020, "kept"),
]
# Approved in 2020 or 2021 and named in neither list of the 2022 report. Lane
# Street is in the 2020 report's list of corridors already implemented; the
# others were approved and whether they went in is not in the reports read.
UNACCOUNTED = [
    {"words": "Lane Street from Oakdale Avenue to Third Street", "report": "2020", "note": "listed as already implemented in July 2020"},
    {"words": "Farallones from Orizaba to San Jose", "report": "2020", "note": "approved in July 2020"},
    {"words": "Holly Park Circle", "report": "2020", "note": "approved in July 2020"},
    {"words": "Pierce from Hayes to Duboce", "report": "2020", "note": "approved in July 2020"},
    {"words": "Armstrong Avenue/Kalmanovitz Street/Bitting Avenue from Newhall Street to Newhall Street", "report": "2021", "note": "approved in April 2021"},
    {"words": "Hollister Avenue from Third Street to Hawes Street", "report": "2021", "note": "approved in April 2021"},
    {"words": "Leland Avenue from Hahn Street to Alpha Street", "report": "2021", "note": "approved in April 2021"},
    {"words": "Mendell Street from Newcomb Avenue to Evans Avenue", "report": "2021", "note": "approved in April 2021"},
    {"words": "Scotia/Thornton/Thomas avenues from Silver Avenue to Griffith Street", "report": "2021", "note": "approved in April 2021"},
]


def read(path):
    with open(path) as f:
        return json.load(f)


# ---- geometry ------------------------------------------------------------------

def metres(a, b):
    r = math.pi / 180
    h = math.sin((b[1] - a[1]) * r / 2) ** 2 + math.cos(a[1] * r) * math.cos(b[1] * r) * math.sin((b[0] - a[0]) * r / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def line_m(pts):
    return sum(metres(a, b) for a, b in zip(pts, pts[1:]))


def local(p, lat0):
    return (p[0] * 111320.0 * math.cos(lat0 * math.pi / 180), p[1] * 110540.0)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


class Grid(object):
    """Line segments bucketed on a 50 m grid, for "how much of this line lies near those"."""

    def __init__(self, lines, lat0, cell=50.0):
        self.lat0, self.cell, self.cells = lat0, cell, collections.defaultdict(list)
        for pts in lines:
            q = [local(p, lat0) for p in pts]
            for a, b in zip(q, q[1:]):
                for i in range(int(min(a[0], b[0]) // cell) - 1, int(max(a[0], b[0]) // cell) + 2):
                    for j in range(int(min(a[1], b[1]) // cell) - 1, int(max(a[1], b[1]) // cell) + 2):
                        self.cells[(i, j)].append((a, b))

    def near(self, p, tol):
        q = local(p, self.lat0)
        segs = self.cells.get((int(q[0] // self.cell), int(q[1] // self.cell)), ())
        return any(seg_dist(q, a, b) <= tol for a, b in segs)

    def cover(self, pts, tol, step=5.0):
        """Share of the line's length within tol of the grid's lines, sampled every `step` metres."""
        samples = []
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(metres(a, b) // step))
            samples += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
        samples.append(tuple(pts[-1]))
        return sum(self.near(p, tol) for p in samples) / len(samples)


# ---- centerline ----------------------------------------------------------------

def centerline():
    r = sfdata.fetch(CENTERLINES)
    blocks, by_street, streets_at = {}, collections.defaultdict(list), collections.defaultdict(set)
    for x in r.rows:
        if str(x.get("active")).lower() != "true" or not x.get("cnn") or not x.get("line"):
            continue
        line = x["line"] if isinstance(x["line"], dict) else json.loads(x["line"].replace("'", '"'))
        if line.get("type") != "LineString":
            continue
        cnn = str(int(float(x["cnn"])))
        f, t = x.get("f_node_cnn"), x.get("t_node_cnn")
        if not f or not t:
            continue
        f, t = str(int(float(f))), str(int(float(t)))
        name = (x.get("streetname") or "").upper()
        pts = [[round(c[0], 6), round(c[1], 6)] for c in line["coordinates"]]
        blocks[cnn] = {"cnn": cnn, "street": name, "f": f, "t": t, "pts": pts, "m": line_m(pts)}
        by_street[name].append(cnn)
        streets_at[f].add(name)
        streets_at[t].add(name)
    return blocks, by_street, streets_at, r.fetched_on


def resolve(c, blocks, by_street, streets_at):
    """The blocks of c.street between the nodes it shares with c.a and c.b, by shortest path along the street."""
    if c.a is None:
        return None, "the reports read give no extent"
    if c.a == "*":
        ids = [k for st in c.street for k in by_street.get(st, [])]
        return (sorted(ids), None) if ids else (None, "no active centerline block named %s" % "/".join(c.street))
    ids = by_street.get(c.street)
    if not ids:
        return None, "no active centerline block named %s" % c.street
    adj = collections.defaultdict(list)
    for k in ids:
        b = blocks[k]
        adj[b["f"]].append((b["t"], k, b["m"]))
        adj[b["t"]].append((b["f"], k, b["m"]))
    ends = lambda names: [n for n in adj if streets_at[n] & set(names if isinstance(names, tuple) else (names,))]  # noqa: E731
    na, nb = ends(c.a), ends(c.b)
    if not na or not nb:
        return None, "%s does not meet %s" % (c.street, c.a if not na else c.b)
    best = None
    for s in na:
        dist, prev, heap = {s: 0.0}, {}, [(0.0, s)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, 1e18):
                continue
            for v, k, m in adj[u]:
                if d + m < dist.get(v, 1e18):
                    dist[v], prev[v] = d + m, (u, k)
                    heapq.heappush(heap, (d + m, v))
        for t in nb:
            if t in dist and t != s and (best is None or dist[t] < best[0]):
                path, u = [], t
                while u != s:
                    u, k = prev[u]
                    path.append(k)
                best = (dist[t], path[::-1])
    if best is None:
        return None, "no chain of %s blocks joins %s and %s" % (c.street, c.a, c.b)
    return best[1], None


# ---- the program today -------------------------------------------------------------

def readopted_year(pts, lines, years_of):
    """The install year of the re-adopted hkz3-itiu row that covers most of this block."""
    best = None
    for i, ln in enumerate(lines):
        share = Grid([ln], 37.76).cover(pts, KEPT_M)
        if share >= KEPT_COVER and (best is None or share > best[0]):
            best = (share, years_of.get(i))
    return best[1] if best else None


def corridor_blocks():
    """Every corridor resolved to blocks, each block marked kept, readopted or out (see the module docstring).

    Returns (corridors, centerline read date, hkz3-itiu read date). A corridor
    is {"c": the CORRIDORS entry, "unresolved": why not or None, "blocks":
    [{"cnn", "street", "status", "back", "m", "pts"}]}. A block on two
    corridors' paths goes to the first."""
    blocks, by_street, streets_at, cl_date = centerline()
    ss = read(SLOW_STREETS)
    # hkz3-itiu rows carry one CNN but can span several blocks, so a block is
    # in the program when the rows' own lines cover most of it: those
    # installed before READOPTED_FROM (kept through the pandemic), or later
    # (re-adopted).
    early, late, late_year = [], [], {}
    for r in ss["records"]:
        if r.get("status") != "Implemented" or not r.get("pts") or len(r["pts"]) < 2:
            continue
        yr = int((r.get("install_date") or "0")[:4] or 0)
        (late if yr >= READOPTED_FROM else early).append(r["pts"])
        if yr >= READOPTED_FROM:
            late_year[len(late) - 1] = yr
    g_early, g_late = Grid(early, 37.76), Grid(late, 37.76)
    out, seen = [], set()
    for c in CORRIDORS:
        path, why = resolve(c, blocks, by_street, streets_at)
        row = {"c": c, "unresolved": why, "blocks": []}
        for k in path or []:
            if k in seen:
                continue
            seen.add(k)
            b = blocks[k]
            if g_early.cover(b["pts"], KEPT_M) >= KEPT_COVER:
                status, back = "kept", None
            elif g_late.cover(b["pts"], KEPT_M) >= KEPT_COVER:
                status, back = "readopted", readopted_year(b["pts"], late, late_year)
            else:
                status, back = "out", None
            row["blocks"].append({"cnn": k, "street": b["street"], "status": status, "back": back, "m": b["m"], "pts": b["pts"]})
        out.append(row)
    return out, cl_date, ss["fetched_on"]


# The all-ages miles count a dropped block's every row: its street length this
# many times, as bike-network-history.py counts the kept Slow Streets outside
# the bikeway layer (SLOW_STREET_DIRECTIONS there).
DIRECTIONS = 2


def centerline_miles(pts):
    """A block's street length in miles, by bike-network-history.py's formula
    (equirectangular about 37.76 N, mile_basis.line_metres), so the history
    and bike-removals.py measure a dropped block the same."""
    k = math.cos(math.radians(37.76)) * 6371008.8
    q = [(math.radians(lon) * k, math.radians(lat) * 6371008.8) for lon, lat in pts]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:])) / MI


def dropped_lines():
    """The corridor blocks the program did not keep, as (key, points, first year, last year) for the reach.

    Keyed "SS:<cnn>" so no key can collide with a bikeway block's or an
    hkz3-itiu row's. Each counts from its corridor's install year through
    DROPPED_YEAR - 1. A readopted block's return is already in hkz3-itiu from
    its own install year, under that row's key."""
    corridors, _, _ = corridor_blocks()
    out = []
    for row in corridors:
        for b in row["blocks"]:
            if b["status"] != "kept":
                out.append(("SS:" + b["cnn"], b["pts"], row["c"].year, DROPPED_YEAR - 1))
    return sorted(out)
