#!/usr/bin/env python3
"""One school's case-study data for the school case study page: children within 15 minutes of it on all-ages streets today and with a School Connector, each nearby corridor or a calmed zone added, how much of each ride is on safe streets, Muni near the school, and street work nearby.

    pipeline/venv-step.py tools/school-trips/school-case.py                    # every school in data/school-case/dropoff.json
    pipeline/venv-step.py tools/school-trips/school-case.py --school kipp-bayview
    pipeline/venv-step.py tools/school-trips/school-case.py --fetch-enrolment  # re-read CDE enrolment first (tools/school-trips/school-enrolment.py)

Bryan, 2026-10-07: "give the user the option of making improvements around
the school (at a high level, not street by street). And also have the map
zoomed out far enough to let the user add critical bikeway corridors to bring
in students from nearby. And show muni routes and schedule information as
well." And: "consider kids within 15 minutes on all ages streets. Plus also
how much of their ride is safe."

THE MODEL is lib/school-travel-time.py's, run to one school instead of
the nearest: walk 2 mph, ride 10 mph only on all-ages edges, a route at most
25% longer than the shortest walk. It reuses that script's walk network,
all-ages lines, edge matching and gap grouping. Only pass 1 is run (the
Lagrangian sweep), so each time is a real route's time and an upper bound on
the fastest; the citywide script's exact pass 2 can only make a time shorter.
The run checks itself against the citywide model, for blocks whose nearest
school of the level is this one, twice (citywideCheck):
  pass   the repo's school point joined as the citywide model joins it, so
         the only difference is pass 1 against pass 2; pass 1 can only be
         slower, and the build fails if any block comes out more than
         PASS_SLACK_MIN faster.
  door   the door point as this page uses it, against the citywide model.
  doorEffect  the door's times against the repo point's on the same
         blocks, both pass 1: the door's effect alone.
pipeline/transportation-quality.py fails a school whose door effect has a
median over 2 minutes or any block over 5, unless the school is HELD.

  * Children: Census 2020 DHC P12, the age band(s) the school's grades serve
    (band_of_grades). Only blocks whose shortest walk to the door is at most
    REACH_MI count: past that no route can make 15 minutes even at riding
    speed the whole way. That pool is the "within reach by bike" group.
  * The school's point is its door from data/school-case/dropoff.json (the
    city's address point), not the repo's school point. The door joins the
    network where walknet.snap() puts it and also at the nearest public street
    edge (DOOR_STREET_HW) and any within TARGET_SLACK_M of it: a door point
    inside a campus otherwise snaps to an internal drive or path alone, and
    every route then pays for the way round the campus (Burton's door joined
    only a service road, 140 ft from it, and 335 ft from Mansell St).
  * Two definitions of a safe street:
      brp     the Biking and Rolling Plan's all-ages network, exactly as the
              bike explorer and school-travel-time.py pick it today.
      sfbike  SF Bike's November 2024 rule (proposal p. 10): "Physical
              protection ... must be prioritized where vehicle traffic is
              higher than 25 mph or daily volumes typically exceed 1,500
              vehicles", calmed shared streets where lower. Today: paths (code
              1) and separated lanes (4) count; a Slow Street counts where
              SFMTA's 2023 count (out/slow-streets/performance.json) shows at
              most 1,500 vehicles a day and a median under 25 mph, or where it
              was not counted (kept, and the count of such blocks is
              reported); painted lanes and signed routes (2c, 3c) do not
              count, being neither protection nor a calmed street, and no
              volume count exists for them. [inference — mine]
  * Options the page can add, each precomputed alone against today:
      connector SFMTA's School Connector (Safe School Connections draft,
                September 2026), from the door to the nearest street of today's
                network under each definition, two ways:
                  kf  "Protected where needed": the shortest walk, made safe.
                      Its footage on a busier street (BUSY_HW: OSM primary,
                      secondary, tertiary or trunk) becomes a separated bikeway,
                      priced at unit-costs.json's separated rate; the rest is
                      calmed, at the calmed rate.
                  ks  "Calm side streets": the shortest walk that never runs
                      along a busier street (it may cross one at a node), all
                      calmed. If none reaches the network within CALM_DETOUR
                      times the shortest walk, or CALM_EXTRA_FT more, whichever
                      allows more, it has no route and no gain (noQuiet),
                      names the busier street that needs a protected lane, and
                      keeps the quiet route's length (quietFt, None if none).
                Under brp every foot made safe counts. Under sfbike separated
                footage counts, and calmed footage counts only on a residential
                street (the corridors' rule: classcode 5 or 0 in DataSF
                3psu-pn9h, the centerline block nearest the edge, within
                CLASS_SNAP_M; an edge on no centerline, a path, counts), edge
                by edge. It ends on a connected run of safe streets at least
                CONNECT_MIN_MI long: the edge matching leaves short isolated
                stubs, and joining one doesn't reach the network. [inference —
                mine] A door that already joins such a run has no connector
                (onNetwork).
      zone      SF Bike's Phase 1 calmed school zone, one extra option: every
                residential OSM street edge within ZONE_FT of the door that
                isn't safe under SF Bike's rule, calmed with the full toolkit
                (speed humps, diverters, modal filters), counted under both
                definitions. SF Bike gives no size; the quarter mile is ours.
      corridor  a run of North Star blocks not all-ages today on one street
                (school-travel-time.py's gaps) with a point within
                CORRIDOR_MI of the door. Under sfbike, a Separated, Car-free
                or Shared-use Path run counts; a Shared run counts only if
                every block is classed residential (classcode 5, or 0 for
                private and paper streets, as data/school-budget/unit-costs.json
                reads it) in DataSF 3psu-pn9h, a stand-in for under 1,500
                vehicles a day, since no count exists. [inference — mine]
                Its cost is the per-mile cost of each facility, weighted by
                length. Its id comes from data/school-case/corridor-ids.json
                (lib/corridor_ids.py): first "c" plus its lowest CNN,
                kept when a built block splits the run, and an old id that
                merged into another resolves through corridorAliases.
    The connector and zone together make a base: none, kf, ks, zf, kf+zf or
    ks+zf. bases[d][key] holds each base's gains over
    today, and each corridor is run with every base in place
    (gains[d][key]), since a corridor that feeds the connector is the case a
    union would miss. One exact run adds every corridor ("all") on each base.
    The page combines selected corridors by taking each block's fastest
    result among them, which approximates corridors working together: a
    route that needs two new corridors at once is missed. comboCheck records
    how far that union falls short of the exact "all" run, with the full
    connector in place. A block whose minutes and safe share match its base
    keeps the base's high-injury count rather than recounting it.
  * Per block and network: minutes (tenths), share of the route's distance
    ridden on safe edges, and how many high-injury streets (DataSF enwt-3u8m)
    the route touches other than by riding a safe edge along them.
  * Muni: the stops and arrivals in site/data/muni-schools.json, plus the
    walk from each near stop to the door: its share on safe edges and the
    high-injury streets it touches. An arrival counts before the bell when it
    is no more than 45 minutes before it and the walk from its stop at 2 mph
    still reaches the door by the bell. Children within a quarter mile
    (straight line) of a route with such an arrival, as a one-seat-ride count;
    only those routes are drawn.
  * Street work: projects in site/data/coordination.json with a line within
    WORK_MI of the door that have not ended.
  * Enrolment: CDE DataQuest, Enrollment by Grade, the latest year published,
    for public schools by CDS code (data/extract/schools/cde-sf.json); cached
    in data/school-case/enrolment.json by tools/school-trips/school-enrolment.py, whose
    --update (a pipeline source step) asks for newer years.
  * Reach: model.reach counts the blocks and kids within REACH_MI of the door
    in a straight line, those kept (shortest walk at most REACH_MI), those
    whose walk is longer, and those whose block joins no street the door's
    network reaches (unjoined), for About the Model.

WRITES site/data/school-case/<id>.json, one per school, and prints a summary.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import heapq
import importlib.util
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import corridor_ids, stable  # noqa: E402
import sfdata  # noqa: E402

stt = paths.load("school-travel-time.py")
walknet = stt.walknet
school_enrolment = paths.load("school-enrolment.py")
school_gravity = paths.load("school-gravity.py")

DROPOFF = os.path.join(ROOT, "data", "school-case", "dropoff.json")
OUT = os.path.join(ROOT, "site", "data", "school-case")
MI = 1609.344
FT = 0.3048
REACH_MI = 2.5          # 15 minutes at 10 mph
CORRIDOR_MI = 1.5       # plan corridors offered as options
ZONE_FT = 1320          # a quarter mile around the door
CONNECT_MIN_MI = 0.5    # a connector ends on a run of safe streets at least this long, not a stub
CALM_DETOUR = 1.5       # a calm-side-street connector may run this many times the shortest walk ...
CALM_EXTRA_FT = 1320    # ... or this much longer, whichever allows more
CLASS_SNAP_M = 15.0     # an edge takes the street class of the centerline block within this distance
WORK_MI = 0.5           # street work listed
MUNI_REACH_FT = 1320    # one-seat ride: home within a quarter mile of the route
SUB_PAD_M = 900.0       # subgraph margin past the reach radius
HIN = "enwt-3u8m"
STREETS = "3psu-pn9h"
SF_BIKE_VOL, SF_BIKE_MPH = 1500, 25
RESIDENTIAL = {"5", "0"}  # 3psu-pn9h classcode: 5 residential, 0 other (private, paper), as unit-costs.json reads it
# Public street classes a door may join directly (see door_ends).
DOOR_STREET_HW = {"residential", "tertiary", "secondary", "primary", "unclassified", "living_street", "trunk",
                  "primary_link", "secondary_link", "tertiary_link", "trunk_link", "residential_link", "pedestrian"}
PASS_SLACK_MIN = 0.1
# Schools built but not shown, with why; the page leaves them out and the door check skips them.
HELD = {"proof": "Its crash ranking (out/school-hour-crashes) still sits at the old 973 Mission St point, "
                 "5,616 ft from the 221 Main St door; rerun it at the door before the school is shown.",
        "lavenia-rochelle": "Closed: the California School Directory (CDS 38684786170278, read 2026-10-07) gives a "
                            "closed date of 2026-06-30, though DataSF 7e7j-59qk still lists it as active."}
WALK_FT_PER_MIN = 2 * 5280 / 60.0
ZONE_HW = {"residential", "living_street", "unclassified"}
# OSM classes a connector treats as busier streets: a protected lane there, and the calm route avoids them.
BUSY_HW = {"primary", "secondary", "tertiary", "trunk", "primary_link", "secondary_link", "tertiary_link", "trunk_link"}
BAND_KEYS = {"5-9": "a5_9", "10-14": "a10_14", "15-17": "a15_17"}
# Drive time per block: street distance on the streets a car can use, at SFCTA's measured morning speed,
# plus a fixed allowance. SFCTA's INRIX speeds by CMP segment, September 2026, 8 to 9 AM
# (https://api.sfcta.org/api/inrix_rt_hourly_exp?date=eq.2026-09&period=eq.8): the median of 693
# segments is 13.4 mph. [SFCTA inrix_rt_hourly_exp — queried 2026-10-08] One citywide figure, since
# matching each street to a segment is heavier than the comparison needs; one-way streets and turns
# are ignored. The allowance is ours: a minute to get going, a minute to stop at the curb, a minute
# to walk to the door.
CAR_MPH = 13.4
CAR_FIXED_MIN = 3.0
CAR_SPEED_SRC = {"url": "https://api.sfcta.org/api/inrix_rt_hourly_exp?date=eq.2026-09&period=eq.8",
                 "label": "SFCTA, INRIX speeds on CMP segments, September 2026, 8 to 9 AM, median of 693 segments",
                 "tag": "[SFCTA inrix_rt_hourly_exp — queried 2026-10-08]"}
DRIVE_HW = {"residential", "tertiary", "secondary", "primary", "unclassified", "living_street", "trunk", "service",
            "primary_link", "secondary_link", "tertiary_link", "trunk_link"}
# Existing facility against the plan's, for the plan upgrades (see World).
RANK_NOW = {"1": 3, "4": 3, "S": 2, "2b": 1, "2c": 1, "3b": 1, "3c": 1}
RANK_PLAN = {"Separated": 3, "Car-free": 3, "Shared-use Path": 3, "Shared": 2}
INF = float("inf")


def band_of_grades(g):
    """The census age bands a grade span serves, taking a band when the span covers at least half its years.

    A grade's age is its number plus 5 (K is 5), so 5-9 is grades K-4, 10-14
    grades 5-9 and 15-17 grades 10-12: K-5 → 5-9 (grade 5 is one year of
    10-14), 5-8 or 6-8 → 10-14, 9-12 → 15-17 (grade 9 is one year of 10-14),
    K-8 → 5-9 and 10-14, 6-12 → 10-14 and 15-17."""
    lo, hi = g.replace("PreK", "K").replace("TK", "K").split("-")
    lo = 0 if lo.strip().upper() in ("K", "PK", "P") else int(lo)
    hi = 0 if hi.strip().upper() == "K" else int(hi)
    out = []
    for band, (a, b) in (("5-9", (0, 4)), ("10-14", (5, 9)), ("15-17", (10, 12))):
        covered = max(0, min(hi, b) - max(lo, a) + 1)
        if covered * 2 >= b - a + 1:
            out.append(band)
    return out


def _pair(a, b):
    """An edge's two ends, rounded and unordered, as a key."""
    return tuple(sorted(((round(a[0], 1), round(a[1], 1)), (round(b[0], 1), round(b[1], 1)))))


def read(*p):
    return json.load(open(os.path.join(ROOT, *p)))


def lonlat(x, y):
    return (round(math.degrees(x / (math.cos(walknet.LAT0) * walknet.EARTH)), 5), round(math.degrees(y / walknet.EARTH), 5))


def door_ends(net, lon, lat):
    """A door's joins: walknet's own, plus the nearest public street edge and any within TARGET_SLACK_M of it.

    More joins can only shorten a route, so this never lengthens a time; it
    stops a door inside a campus from leaving only by an internal drive."""
    G = net.G
    out = list(net.ends(lon, lat))
    px, py = walknet.xy(lon, lat)
    have = {e for _n, _c, _a, e in out}
    r = walknet.CELL_M
    cand = []
    while r <= 2000:
        cand = [c for c in G.edges_near(px, py, r) if G.joinable[c[0]] and G.ehw[c[0]] in DOOR_STREET_HW]
        if cand and min(c[2] for c in cand) + walknet.TARGET_SLACK_M <= r:
            break
        r *= 2
    if cand:
        best = min(c[2] for c in cand)
        for e, t, c in sorted(cand, key=lambda c: (c[2], c[0])):
            if c > best + walknet.TARGET_SLACK_M or e in have:
                continue
            L = net.L[e]
            out.append((G.eu[e], c, t * L, e))
            out.append((G.ev[e], c, (1 - t) * L, e))
    return out


# -- inputs shared by every school ------------------------------------------------

class World(object):
    def __init__(self, pure=False):
        t0 = time.time()
        stt.FAST["on"] = not pure and stt.rcsp.available()
        self.net = stt.Net(cache=True)
        G = self.net.G
        self.G = G
        today, plan, plan_meta = stt.all_ages_lines()
        self.plan, self.plan_meta = plan, plan_meta
        self.today_lines = today
        line_edges, _weak = stt.edges_of(self.net, today + plan, cache=True)
        self.line_edges = line_edges
        n_e = len(G.eu)
        comps = read("site", "data", "bike-history", "components.json")["blocks"]
        self.seg_name = {x["key"]: x.get("name") for x in read("site", "data", "bike-history", "segments.json")["segments"]}
        slow = {}
        perf = read("out", "slow-streets", "performance.json")
        for s in perf["sites"]:
            for r in s.get("hkz3_rows", []):
                slow[str(r["cnn"])] = (s["adt"], s["median_mph"])
        self.brp = [False] * n_e
        self.sfb = [False] * n_e
        self.slow_unmeasured = 0
        for key, _pts in today:
            c = comps.get(key, {})
            codes = set(c.get("m", {}))
            strict = bool(codes & {"1", "4"})
            if not strict and c.get("s") is not None:
                cnt = slow.get(str(key))
                if cnt is None:
                    strict = True
                    self.slow_unmeasured += 1
                else:
                    strict = cnt[0] <= SF_BIKE_VOL and cnt[1] < SF_BIKE_MPH
            for e in line_edges.get(key, ()):
                self.brp[e] = True
                if strict:
                    self.sfb[e] = True
        self.today_keys = {k for k, _ in today}
        self.edge_line = {}
        for key, _pts in today:
            for e in line_edges.get(key, ()):
                self.edge_line.setdefault(e, key)
        self.today_strict_keys = set()
        for key, _pts in today:
            es = line_edges.get(key, ())
            if es and all(self.sfb[e] for e in es):
                self.today_strict_keys.add(key)
        self.groups = stt.group_gaps(plan, plan_meta, self.today_keys)
        # Plan upgrades: a plan block whose street has a bikeway today that falls
        # short of the plan's facility (a painted lane or signed route where the
        # plan draws a separated lane or a calmed street, or a Slow Street over
        # SF Bike's limits where the plan draws a separated lane), and that isn't
        # safe under SF Bike's test today. The plan's definition already counts
        # the lane it has, so these are options under SF Bike's test only.
        self.today_codes = {}
        for key, _pts in today:
            c = comps.get(key, {})
            codes = set(c.get("m", {}))
            if c.get("s") is not None:
                codes.add("S")
            self.today_codes[key] = codes
        upg = []
        for k, pts_ in plan:
            cnn = plan_meta[k]["cnn"]
            if cnn not in self.today_keys or cnn in self.today_strict_keys:
                continue
            now = max((RANK_NOW.get(x, 0) for x in self.today_codes.get(cnn, ())), default=0)
            if RANK_PLAN[plan_meta[k]["facility"]] > now:
                upg.append((k, pts_))
        self.upgrade_groups = stt.group_gaps(upg, plan_meta, set())
        self.upgrade_keys = {tuple(g) for g in self.upgrade_groups}
        groups_all = self.groups + self.upgrade_groups
        # Each corridor's id, from the registry, the same whichever schools this run builds.
        ids, reg = corridor_ids.assign([[plan_meta[k]["cnn"] for k in g] for g in groups_all],
                                       names=[plan_meta[g[0]]["street"].title() for g in groups_all])
        corridor_ids.save(reg)
        self.corr_id = {tuple(g): i for g, i in zip(groups_all, ids)}
        self.corr_alias = corridor_ids.aliases(reg)
        # OSM street names, by the rounded ends of each of their segments, for the connector's note.
        blob = json.load(open(walknet.CACHE))
        coords = {e["id"]: (e["lon"], e["lat"]) for e in blob["elements"] if e["type"] == "node"}
        self.osm_name = {}
        for wy in blob["elements"]:
            tg = wy.get("tags", {}) if wy["type"] == "way" else {}
            if not tg.get("highway") or not tg.get("name"):
                continue
            pts = [walknet.xy(*coords[n]) for n in wy.get("nodes", ()) if n in coords]
            for a, b in zip(pts, pts[1:]):
                self.osm_name[_pair(a, b)] = tg["name"]
        del blob, coords
        # Each safe edge's connected run of safe edges, in miles, so a connector skips a short stub.
        self.run_mi = {"brp": self._runs(self.brp), "sfbike": self._runs(self.sfb)}
        # Street class of every centerline block, for the sfbike reading of Shared corridors.
        st = sfdata.fetch(STREETS, select="cnn,classcode", where="active=true")
        self.street_class = {r["cnn"]: r.get("classcode") for r in st.rows}
        self.street_read = str(st.fetched_on)
        # Each active centerline block's class by its geometry, for the connector's
        # sfbike reading: an edge takes the class of the block nearest it.
        geo = sfdata.fetch(STREETS)
        cl_lines, self.cl_class = [], {}
        for r in geo.rows:
            g = r.get("line")
            if str(r.get("active")) != "True" or not g or g.get("type") != "LineString":
                continue
            cl_lines.append((str(r["cnn"]), [c[:2] for c in g["coordinates"]]))
            self.cl_class[str(r["cnn"])] = str(r.get("classcode"))
        assert len(cl_lines) > 14000, "centerline geometry read looks short: %d" % len(cl_lines)
        self.cl_idx = stt.LineIndex(cl_lines)
        self._edge_class = {}
        # Cross streets of every block, to tell same-named corridors apart.
        xs = sfdata.fetch(STREETS, select="cnn,street,st_type,f_st,t_st")
        self.cross = {str(r["cnn"]): (r.get("f_st"), r.get("t_st")) for r in xs.rows}
        self.street_name = {str(r["cnn"]): nice_street(" ".join(x for x in (r.get("street"), r.get("st_type")) if x)) for r in xs.rows}
        # High-injury network, matched onto walk edges like a bikeway line.
        hin = sfdata.fetch(HIN, select="cnn_sgmt_pkey,full_street_name,geom")
        lines = []
        for r in hin.rows:
            g = r.get("geom")
            if not g:
                continue
            for L in (g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]):
                lines.append(((r.get("full_street_name") or "unnamed").title(), [c[:2] for c in L]))
        assert len(hin.rows) > 5000, "HIN read looks short: %d rows" % len(hin.rows)
        self.hin_fetched = str(hin.fetched_on)
        self.hin_edge = {}
        idx = stt.LineIndex(lines)
        for e in range(n_e):
            if G.ehw[e] == "steps":
                continue
            u, v = G.eu[e], G.ev[e]
            mx, my = (G.x[u] + G.x[v]) / 2, (G.y[u] + G.y[v]) / 2
            for i in idx.near(mx, my, 12.0):
                name, ax, ay, bx, by = idx.segs[i]
                if stt.seg_dist(mx, my, ax, ay, bx, by) <= 12.0:
                    self.hin_edge[e] = name
                    break
        self.node_hin = collections.defaultdict(set)
        for e, name in self.hin_edge.items():
            self.node_hin[G.eu[e]].add(name)
            self.node_hin[G.ev[e]].add(name)
        # The repo's school points, joined as the citywide model joins them, for the pass check.
        self.repo_point = {x["name"]: (x["lon"], x["lat"]) for x in stt.load_schools()[0]}
        kids = {r["geoid"]: r for r in read("data", "extract", "census-dhc", "p12-blocks.json")["records"]}
        pts = {r["geoid"]: r for r in read("data", "extract", "census-blocks", "2020.json")["records"]}
        self.blocks = []
        for gid in sorted(kids):
            k = kids[gid]
            if k["a5_9"] + k["a10_14"] + k["a15_17"] == 0:
                continue
            p = pts[gid]
            self.blocks.append({"geoid": gid, "lon": p["lon"], "lat": p["lat"], "a5_9": k["a5_9"],
                                "a10_14": k["a10_14"], "a15_17": k["a15_17"]})
        self.grav = school_gravity.Model()
        assert [b["geoid"] for b in self.grav.blks] == [b["geoid"] for b in self.blocks], "gravity blocks differ from the case study's"
        self.city = self.grav.city["schools"]
        self.drivable = [G.ehw[e] in DRIVE_HW for e in range(n_e)]
        self.areas = stt.attendance_areas()[0]
        self.block_reg = {}
        print("  world: %d upgrade runs; %d nodes, %d edges, %d HIN edges, %d slow-street lines with no count (%.0fs)" % (
            len(self.upgrade_groups), len(G.x), n_e, len(self.hin_edge), self.slow_unmeasured, time.time() - t0))


    def edge_residential(self, e):
        """Whether an edge counts as a residential street under SF Bike's rule, as corridors do: the class of the centerline block nearest its middle; an edge on no centerline (a path) counts."""
        if e not in self._edge_class:
            G = self.G
            u, v = G.eu[e], G.ev[e]
            mx, my = (G.x[u] + G.x[v]) / 2, (G.y[u] + G.y[v]) / 2
            best = None
            for i in sorted(self.cl_idx.near(mx, my, CLASS_SNAP_M)):
                key, ax, ay, bx, by = self.cl_idx.segs[i]
                dd = stt.seg_dist(mx, my, ax, ay, bx, by)
                if dd <= CLASS_SNAP_M and (best is None or dd < best[0]):
                    best = (dd, key)
            self._edge_class[e] = self.cl_class.get(best[1]) if best else None
        c = self._edge_class[e]
        return c is None or c in RESIDENTIAL

    def _runs(self, safe):
        G, L = self.G, self.net.L
        adj = collections.defaultdict(list)
        for e in range(len(G.eu)):
            if safe[e]:
                adj[G.eu[e]].append(e)
                adj[G.ev[e]].append(e)
        out = {}
        for e0 in range(len(G.eu)):
            if not safe[e0] or e0 in out:
                continue
            seen, stack = {e0}, [e0]
            while stack:
                e = stack.pop()
                for nd in (G.eu[e], G.ev[e]):
                    for f in adj[nd]:
                        if f not in seen:
                            seen.add(f)
                            stack.append(f)
            m = sum(L[e] for e in seen) / MI
            for e in seen:
                out[e] = m
        return out


# -- searches on a subgraph -------------------------------------------------------

class Sub(object):
    """The walk network within a radius of one school, with searches that keep each node's predecessor edge."""

    def __init__(self, world, cx, cy, radius):
        G = world.G
        keep = [i for i in range(len(G.x)) if math.hypot(G.x[i] - cx, G.y[i] - cy) <= radius]
        self.ix = {g: i for i, g in enumerate(keep)}
        self.glob = keep
        self.adj = [[] for _ in keep]
        for g in keep:
            for v, e in world.net.adj[g]:
                if v in self.ix:
                    self.adj[self.ix[g]].append((self.ix[v], e))
        self.L = world.net.L
        self.G = G

    def search(self, bike, seeds, lam, skip=None):
        """Least time + lam x walking-pace length from the seeds: (cost, time, length, pred edge, pred node) per local node. An edge with skip[e] true is never used."""
        n = len(self.adj)
        RW, RB = stt.RW, stt.RB
        lw = lam * RW
        cost = [INF] * n
        tm = [0.0] * n
        ln = [0.0] * n
        pe = [-1] * n
        pn = [-1] * n
        h = []
        for node, c, along, e in seeds:
            if node not in self.ix or (skip is not None and skip[e]):
                continue
            u = self.ix[node]
            t = c * RW + along * (RB if bike[e] else RW)
            m = c + along
            k = t + lw * m
            if k < cost[u]:
                cost[u], tm[u], ln[u] = k, t, m
                h.append((k, u))
        heapq.heapify(h)
        adj, L = self.adj, self.L
        while h:
            k, u = heapq.heappop(h)
            if k > cost[u]:
                continue
            tu, lu = tm[u], ln[u]
            for v, e in adj[u]:
                if skip is not None and skip[e]:
                    continue
                le = L[e]
                te = le * (RB if bike[e] else RW)
                nk = k + te + lw * le
                if nk < cost[v]:
                    cost[v], tm[v], ln[v], pe[v], pn[v] = nk, tu + te, lu + le, e, u
                    heapq.heappush(h, (nk, v))
        return cost, tm, ln, pe, pn


def route_hin(world, sub, arr, start_local, end_edge, bike, safe):
    """High-injury streets a route touches, other than those it only rides along on a safe edge."""
    _c, _t, _l, pe, pn = arr
    touched, ridden = set(), set()
    u = start_local
    edges = [end_edge]
    while u != -1:
        touched |= world.node_hin.get(sub.glob[u], set())
        if pe[u] != -1:
            edges.append(pe[u])
        u = pn[u]
    for e in edges:
        name = world.hin_edge.get(e)
        if name and safe[e]:
            ridden.add(name)
    # A street ridden safely along still counts if the route also crosses it bare;
    # we can't tell those apart at a node, so a safely ridden street is dropped.
    return len(touched - ridden)


def _hin_of_path(world, nodes, edges, bike):
    touched, ridden = set(), set()
    for u in nodes:
        touched |= world.node_hin.get(u, set())
    for e in edges:
        name = world.hin_edge.get(e)
        if name and bike[e]:
            ridden.add(name)
    # A street ridden safely along is dropped even if the route also crosses
    # it bare somewhere; a node can't tell the two apart.
    return len(touched - ridden)


def _path_back(world, arr, u, bike, lw):
    """Nodes and edges from node u back to a seed, read off a search's cost array: the predecessor is the neighbour whose cost plus the edge's equals u's."""
    cost = arr[0]
    L, adj = world.net.L, world.net.adj
    RW, RB = stt.RW, stt.RB
    nodes, edges, seen = [u], [], {u}
    while True:
        cu = cost[u]
        nxt = None
        for v, e in adj[u]:
            if v in seen or cost[v] == INF:
                continue
            le = L[e]
            if abs(cost[v] + le * (RB if bike[e] else RW) + lw * le - cu) <= 1e-6 * max(1.0, cu):
                nxt = (v, e)
                break
        if nxt is None:
            return nodes, edges
        u = nxt[0]
        edges.append(nxt[1])
        nodes.append(u)
        seen.add(u)


def flat_ends(blocks):
    """Every block's network joins laid out flat, for the array version of the per-block pick."""
    import numpy
    node, c, al, e, owner = [], [], [], [], []
    for bi, b in enumerate(blocks):
        for nd, cc, aa, ee in b["ends"]:
            node.append(nd)
            c.append(cc)
            al.append(aa)
            e.append(ee)
            owner.append(bi)
    return {"node": numpy.array(node, dtype=numpy.int64), "c": numpy.array(c), "al": numpy.array(al),
            "e": numpy.array(e, dtype=numpy.int64), "owner": numpy.array(owner, dtype=numpy.int64), "n": len(blocks)}


def times_to(world, sub, seeds, bike, blocks, walk, flat=None, base=None):
    """Per block: (tenths of a minute, % of distance on safe edges, high-injury streets) of the fastest capped route, or None.

    With the compiled searches (lib/rcsp.c) the sweep runs on the whole
    network, each weight cut off past the farthest route that could count;
    each block's least-cost join is picked over arrays (the first join of
    least cost, as block_best does); and each chosen route is read back off its
    search's cost array. With base (the same blocks on a smaller network), a
    block whose minutes and share match base keeps base's high-injury count
    rather than retracing the route. Without the compiled searches, the Python
    search on the subgraph keeps predecessors."""
    RW, RB = stt.RW, stt.RB
    net = world.net
    if net.fast is None:
        return _times_to_pure(world, sub, seeds, bike, blocks, walk)
    import numpy
    bk = net.bike_array(bike)
    ends_seed = stt.rcsp.Ends(seeds, school=[0] * len(seeds))
    far = stt.DETOUR * max(walk) + 50.0
    F = flat
    nb = F["n"]
    wcap = stt.DETOUR * numpy.array(walk) + 1e-6
    te = F["c"] * RW + F["al"] * numpy.where(bk[F["e"]] != 0, RB, RW)
    m_all = F["c"] + F["al"]
    best_t = numpy.full(nb, INF)
    best_m = numpy.zeros(nb)
    best_u = numpy.full(nb, -1, dtype=numpy.int64)
    best_e = numpy.full(nb, -1, dtype=numpy.int64)
    best_l = numpy.full(nb, -1, dtype=numpy.int64)
    arrs = []
    for li, lam in enumerate(stt.LAMBDAS):
        lw = lam * RW
        cost, tm, ln, _s = net.fast.lagrange(bk, RW, RB, lw, far * RW + lw * far, ends_seed, None)
        arrs.append((cost, lw))
        k = cost[F["node"]] + te + lw * m_all
        order = numpy.lexsort((k, F["owner"]))
        own = F["owner"][order]
        first = numpy.flatnonzero(numpy.r_[True, own[1:] != own[:-1]])
        idx = order[first]
        bi = own[first]
        ok = numpy.isfinite(k[idx])
        idx, bi = idx[ok], bi[ok]
        t = tm[F["node"][idx]] + te[idx]
        m = ln[F["node"][idx]] + m_all[idx]
        good = (m <= wcap[bi]) & (t < best_t[bi] - 1e-9)
        bi, idx, t, m = bi[good], idx[good], t[good], m[good]
        best_t[bi] = t
        best_m[bi] = m
        best_u[bi] = F["node"][idx]
        best_e[bi] = F["e"][idx]
        best_l[bi] = li
    out = []
    for i in range(nb):
        if not numpy.isfinite(best_t[i]):
            out.append(None)
            continue
        t, m = float(best_t[i]), float(best_m[i])
        ride = max(0.0, (m * RW - t) / (RW - RB))
        share = min(100, int(round(100 * ride / m))) if m > 0 else 0
        tenths = int(math.ceil(t / 6.0 - 1e-9))
        if base is not None and base[i] is not None and base[i][0] == tenths and base[i][1] == share:
            out.append((tenths, share, base[i][2]))
            continue
        cost, lw = arrs[best_l[i]]
        nodes, edges = _path_back(world, (cost,), int(best_u[i]), bike, lw)
        out.append((tenths, share, _hin_of_path(world, nodes, edges + [int(best_e[i])], bike)))
    return out


def _times_to_pure(world, sub, seeds, bike, blocks, walk):
    RW, RB = stt.RW, stt.RB
    best = [None] * len(blocks)
    for lam in stt.LAMBDAS:
        arr = sub.search(bike, seeds, lam)
        cost, tm, ln = arr[0], arr[1], arr[2]
        lw = lam * RW
        for bi, b in enumerate(blocks):
            pick = None
            for node, c, along, e in b["ends"]:
                u = sub.ix.get(node)
                if u is None or cost[u] == INF:
                    continue
                te = c * RW + along * (RB if bike[e] else RW)
                m = c + along
                k = cost[u] + te + lw * m
                if pick is None or k < pick[0]:
                    pick = (k, tm[u] + te, ln[u] + m, u, e)
            if pick is None:
                continue
            _k, t, m, u, e = pick
            if m > stt.DETOUR * walk[bi] + 1e-6:
                continue
            if best[bi] is None or t < best[bi][0] - 1e-9:
                best[bi] = (t, m, u, e, lam, arr)
    out = []
    for bi, r in enumerate(best):
        if r is None:
            out.append(None)
            continue
        t, m, u, e, lam, arr = r
        ride = max(0.0, (m * RW - t) / (RW - RB))
        share = min(100, int(round(100 * ride / m))) if m > 0 else 0
        out.append((int(math.ceil(t / 6.0 - 1e-9)), share, route_hin(world, sub, arr, u, e, bike, bike)))
    return out


# -- one school -------------------------------------------------------------------

def line_pts(world, edges):
    G = world.G
    return [[lonlat(G.x[G.eu[e]], G.y[G.eu[e]]), lonlat(G.x[G.ev[e]], G.y[G.ev[e]])] for e in sorted(edges)]


def merge_runs(segs):
    """Join two-point segments end to end into longer lines, for a smaller file."""
    ends = collections.defaultdict(list)
    for i, (a, b) in enumerate(segs):
        ends[tuple(a)].append(i)
        ends[tuple(b)].append(i)
    used = [False] * len(segs)
    runs = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        run = [segs[i][0], segs[i][1]]
        for side in (1, 0):
            while True:
                tip = tuple(run[-1] if side else run[0])
                nxt = [j for j in ends[tip] if not used[j]]
                if len(ends[tip]) != 2 or not nxt:
                    break
                j = nxt[0]
                used[j] = True
                a, b = segs[j]
                p = b if tuple(a) == tip else a
                if side:
                    run.append(p)
                else:
                    run.insert(0, p)
        runs.append([list(p) for p in run])
    return runs


def diff(base, new):
    out = []
    for bi, (a, b) in enumerate(zip(base, new)):
        if b is None:
            continue
        if a is None or b[0] < a[0] or b[1] != a[1] or b[2] != a[2]:
            out.append([bi, b[0], b[1], b[2]])
    return out


def nice_street(x):
    """A centerline street name in title case, ordinals kept lower case: "SAN BRUNO AVE" → "San Bruno Ave", "3RD ST" → "3rd St"."""
    if not x:
        return None
    t = " ".join(re.sub(r"^0+(?=\d)", "", w.capitalize()) for w in str(x).split())
    return re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), t)


def cross_ends(world, meta):
    """The cross streets at the two ends of a corridor's run of blocks, from DataSF 3psu-pn9h's f_st and t_st.

    Along a run A-B, B-C, C-D each inner cross street bounds two blocks and
    the ends bound one; a single block gives its own two. A run that doesn't
    resolve to two ends (a branch, a missing block) gives (None, None)."""
    pairs = [world.cross.get(str(m["cnn"])) for m in meta]
    if not pairs or any(p is None for p in pairs):
        return (None, None)
    c = collections.Counter(x for p in pairs for x in p if x)
    ends = sorted(x for x, n in c.items() if n == 1)
    if len(ends) != 2:
        return (None, None)
    first = pairs[0]
    a = ends[0] if ends[0] in first else ends[1]
    b = ends[1] if a == ends[0] else ends[0]
    return (nice_street(a), nice_street(b))


def feet_between(a, b):
    """Straight-line feet between two {lon, lat} points."""
    ax, ay = walknet.xy(a["lon"], a["lat"])
    bx, by = walknet.xy(b["lon"], b["lat"])
    return math.hypot(ax - bx, ay - by) / FT


def bell_minutes(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


LEVEL_GRADES = {"elementary": ("TK", "K", "1", "2", "3", "4", "5"), "middle": ("6", "7", "8"), "high": ("9", "10", "11", "12")}


def students_of(s, en):
    """The school's students by level, their total, and where the count comes from.

    A public school's is CDE's enrolment by grade. A private school's is the
    count it reports to CDE in its private school affidavit, or one the
    school publishes, recorded in dropoff.json as enrolment_published, spread
    evenly over its grades. None when neither exists."""
    if en.get("total") and en.get("grade_pct"):
        pct = en["grade_pct"]
        span = {lvl: en["total"] * sum(pct.get(g, 0) for g in gs) / 100.0 for lvl, gs in LEVEL_GRADES.items()}
        t = sum(span.values())
        span = {k: v * en["total"] / t for k, v in span.items()} if t else span
        return en["total"], span, {"kind": "cde", "year": en.get("year"), "url": en.get("url"), "tag": en.get("tag")}
    pub = s.get("enrolment_published")
    if not pub or not pub.get("total"):
        return None, None, None
    span = {lvl: 0.0 for lvl in LEVEL_GRADES}
    if pub.get("by_grade"):
        for g, n in pub["by_grade"].items():
            span[next(lvl for lvl, gs in LEVEL_GRADES.items() if g in gs)] += n
    else:
        g = school_gravity.grade_set(s["grades"])
        for y in g:
            span["elementary" if y <= 5 else "middle" if y <= 8 else "high"] += pub["total"] / float(len(g))
    return pub["total"], span, dict(pub, kind="published")


def car_minutes(world, sub, door, blocks):
    """Each block's drive to the door in tenths of a minute, and how many blocks fell back to their walk.

    The shortest street distance on drivable edges at CAR_MPH, plus
    CAR_FIXED_MIN. The door and any block that joins only a path start at
    the nearest drivable street at no cost. A block no drivable route
    reaches takes its walk distance at CAR_MPH, counted in
    model.reach.carFallbackBlocks."""
    G = world.G
    skip = [not x for x in world.drivable]

    def drive_ends(lon, lat):
        """The nearest drivable street edges to a point, as (node, metres off, metres along, edge) joins."""
        px, py = walknet.xy(lon, lat)
        r, cand = walknet.CELL_M, []
        while r <= 2000 and not cand:
            cand = [c for c in G.edges_near(px, py, r) if world.drivable[c[0]]]
            r *= 2
        if not cand:
            return []
        best = min(c[2] for c in cand)
        out_ = []
        for e, t, c in sorted(cand, key=lambda c: (c[2], c[0])):
            if c <= best + walknet.TARGET_SLACK_M:
                L = world.net.L[e]
                out_ += [(G.eu[e], c, t * L, e), (G.ev[e], c, (1 - t) * L, e)]
        return out_
    door_d = drive_ends(door["lon"], door["lat"])
    arr = sub.search([False] * len(G.eu), door_d, 0.0, skip=skip)
    out, fallback = [], 0
    for b in blocks:
        m = INF
        ends = [x for x in b["ends"] if world.drivable[x[3]]] or drive_ends(b["lon"], b["lat"])
        for node, c, along, e in ends:
            u = sub.ix.get(node)
            if u is not None and arr[0][u] < INF:
                m = min(m, arr[2][u] + c + along)
        if m == INF:
            m = b["walk"]
            fallback += 1
        out.append(int(math.ceil(10 * (max(m, b["walk"]) / MI / CAR_MPH * 60 + CAR_FIXED_MIN))))
    return out, fallback



TOP_N = 20
TOPS = [1, 3, 5, 10, 20]
FAC_TYPE = {"Separated": "separated", "Shared": "calmed", "Shared-use Path": "path", "Car-free": "car_free"}


def top_sequence(world, sub, seeds, nets, blocks, walk, flat, corr, base_rows, base_edges, with_edges, costs, door):
    """The plan blocks to build first, one at a time, per definition.

    Each step adds the candidate block that brings the most of the school's
    expected students newly within 15 minutes given the blocks already picked,
    with the protected connector in place (base "kf"; it equals today where the
    door is already on the network). Candidates are the blocks of the plan
    corridors within CORRIDOR_MI (new blocks under both definitions, upgrades
    under SF Bike's test only, and under SF Bike's test only the corridors it
    counts). A corridor whose own gain and whose removal from every corridor
    together are both zero is pruned. Selection is lazy: every candidate is
    timed once, then each step retimes the blocks touching those picked and,
    in order of their last gain, the rest until none could beat the best
    fresh gain, which is exact if a block's gain never grows as others are
    built and an approximation where two blocks only work together. A tie or
    a step where nothing gains goes to a block touching the network, the door
    or a block already picked, then the one nearest the door, so the sequence
    stays connected.

    Returns (blocks per definition, gains per definition, base and Top-N, a check)."""
    G = world.G
    stu = [b["stu"] for b in blocks]

    def score(rows):
        return sum(x for x, r in zip(stu, rows) if r and r[0] <= 150)

    def apply(base, gl):
        rows = list(base)
        for bi, t, sh, h in gl:
            if rows[bi] is None or t <= rows[bi][0]:
                rows[bi] = (t, sh, h)
        return rows
    dx, dy = walknet.xy(door["lon"], door["lat"])
    info = {}
    for o in corr:
        for k in o["_keys"]:
            es = world.line_edges.get(k, set())
            if not es:
                continue
            m = world.plan_meta[k]
            pts_ = next(p for kk, p in world.plan if kk == k)
            L = sum(math.hypot(*(a - b for a, b in zip(walknet.xy(*p), walknet.xy(*q)))) for p, q in zip(pts_, pts_[1:]))
            u = costs["types"][FAC_TYPE[m["facility"]]]
            f, t_ = world.cross.get(str(m["cnn"]), (None, None))
            mid = walknet.xy(*pts_[len(pts_) // 2])
            info[k] = {"id": "b%s" % m["cnn"], "cnn": m["cnn"], "street": m["street"].title(), "from": nice_street(f), "to": nice_street(t_),
                       "ft": int(round(L / FT)), "facility": m["facility"], "upgrade": o["upgrade"], "corridor": o["id"],
                       "cost": {c: round(u[c] * L / MI, 3) for c in ("low", "central", "high")},
                       "line": [[round(x, 5), round(y, 5)] for x, y in pts_],
                       "_edges": es, "_nodes": {nd for e in es for nd in (G.eu[e], G.ev[e])}, "_ok": {"brp": not o["upgrade"], "sfbike": o["sfbikeOk"]},
                       "_door": math.hypot(mid[0] - dx, mid[1] - dy)}
    out_b, out_g, check = {}, {}, {}
    for d in nets:
        key = "kf"
        base = base_rows[(d, key)]
        sets = base_edges[(d, key)]
        s0 = score(base)
        # Prune: corridors with no gain alone and none lost when removed from all of them.
        mine = [o for o in corr if (o["sfbikeOk"] if d == "sfbike" else not o["upgrade"])]
        every = set()
        for o in mine:
            every |= o["_edges"]
        full = times_to(world, sub, seeds, with_edges(d, every, *sets), blocks, walk, flat, base)
        sf = score(full)
        keep = set()
        for o in mine:
            alone = score(apply(base, o["gains"][d].get(key, []))) - s0
            if alone > 1e-6:
                keep.add(o["id"])
                continue
            rest = set()
            for p in mine:
                if p is not o:
                    rest |= p["_edges"]
            if sf - score(times_to(world, sub, seeds, with_edges(d, rest, *sets), blocks, walk, flat, full)) > 1e-6:
                keep.add(o["id"])
        cand = sorted((k for k, v in info.items() if v["_ok"][d] and v["corridor"] in keep), key=lambda k: int(info[k]["cnn"]))
        touch = set()
        for e in range(len(G.eu)):
            if nets[d][e]:
                touch.add(G.eu[e])
                touch.add(G.ev[e])
        for st in sets:
            for e in st:
                touch.add(G.eu[e])
                touch.add(G.ev[e])
        touch |= {x[0] for x in seeds}
        picked, edges, cur, cur_s = [], set(), base, s0
        near = set()  # nodes of the blocks picked so far: only their neighbours are retimed
        evals = 0

        def ev(k):
            rows = times_to(world, sub, seeds, with_edges(d, edges | info[k]["_edges"], *sets), blocks, walk, flat, cur)
            return score(rows) - cur_s, rows
        est = {}
        fresh = {}
        for k in cand:
            fresh[k] = ev(k)
            evals += 1
        left = set(cand)
        while len(picked) < TOP_N and left:
            for k in sorted(left):
                if k not in fresh and info[k]["_nodes"] & near:
                    fresh[k] = ev(k)
                    evals += 1
            for k in sorted(left - set(fresh), key=lambda k: (-est.get(k, 0), int(info[k]["cnn"]))):
                bf = max((g for g, _r in fresh.values()), default=0.0)
                if est.get(k, 0) <= bf + 1e-9:
                    break
                fresh[k] = ev(k)
                evals += 1
            for k, (g, _r) in fresh.items():
                est[k] = g

            def rank(k):
                g = fresh[k][0] if k in fresh else est.get(k, 0)
                return (-round(g, 6), 0 if info[k]["_nodes"] & touch else 1, info[k]["_door"], int(info[k]["cnn"]))
            pool = [k for k in left if k in fresh]
            best = min(pool or left, key=rank)
            g, rows = fresh[best] if best in fresh else ev(best)
            picked.append((best, max(0.0, g)))
            edges |= info[best]["_edges"]
            touch |= info[best]["_nodes"]
            near |= info[best]["_nodes"]
            cur, cur_s = rows, cur_s + g
            left.discard(best)
            fresh = {}
        # Each Top-N's result on every base, so the page only looks them up.
        out_g[d] = {}
        for (dd, bkey), bsets in sorted(base_edges.items()):
            if dd != d:
                continue
            brows = base_rows[(d, bkey)]
            out_g[d][bkey] = {}
            for n in TOPS:
                if n > len(picked):
                    continue
                es = set()
                for k, _g in picked[:n]:
                    es |= info[k]["_edges"]
                out_g[d][bkey][str(n)] = diff(brows, times_to(world, sub, seeds, with_edges(d, es, *bsets), blocks, walk, flat, brows))
        out_b[d] = [dict({x: v for x, v in info[k].items() if not x.startswith("_")}, gain=round(g, 2)) for k, g in picked]
        check[d] = {"candidates": len(cand), "corridorsKept": len(keep), "corridors": len(mine), "evals": evals,
                    "top20": round(cur_s - s0, 1), "everyCorridor": round(sf - s0, 1)}
        for k, _g in picked:
            world.block_reg[info[k]["cnn"]] = info[k]["street"]
    return out_b, out_g, check


def build(world, s, enrol, costs, priority):
    t0 = time.time()
    G = world.G
    net = world.net
    door = s["door"]
    dx, dy = walknet.xy(door["lon"], door["lat"])
    bands = band_of_grades(s["grades"])
    radius = REACH_MI * MI
    sub = Sub(world, dx, dy, radius + SUB_PAD_M)
    seeds = door_ends(net, door["lon"], door["lat"])
    assert seeds, "door does not join the network"
    # Shortest walk from the door, with predecessors, for the reach pool and the Muni walks.
    walk_arr = sub.search([False] * len(G.eu), seeds, 0.0)
    # The school's own students, spread over the city's blocks by the gravity
    # model (tools/school-trips/school-gravity.py), so each block carries its expected students.
    en0 = enrol["schools"].get(s["id"]) or {}
    total, span, stu_src = students_of(s, en0)
    cds = en0.get("cds")
    city = world.city.get(cds) if cds else None
    choice = (not s["public"]) or bool(city and city["charter"])
    if total:
        stu_all, stu_how = world.grav.spread(cds, door["lon"], door["lat"], span, choice)
    else:
        stu_all, stu_how = [0.0] * len(world.blocks), {}
    blocks = []
    reach = collections.Counter()
    for bi_, b in enumerate(world.blocks):
        k = sum(b[BAND_KEYS[x]] for x in bands)
        st_ = float(stu_all[bi_])
        if not k and st_ < 0.005:
            continue
        bx, by = walknet.xy(b["lon"], b["lat"])
        if math.hypot(bx - dx, by - dy) > radius:
            continue
        reach["lineBlocks"] += 1
        reach["lineKids"] += k
        ends = net.ends(b["lon"], b["lat"])
        w = INF
        for node, c, along, _e in ends:
            u = sub.ix.get(node)
            if u is not None and walk_arr[0][u] < INF:
                w = min(w, walk_arr[2][u] + c + along)
        if w > radius:
            # No join the door's network reaches, or a walk longer than the reach.
            kind = "unjoined" if w == INF else "far"
            reach[kind + "Blocks"] += 1
            reach[kind + "Kids"] += k
            continue
        reach["keptBlocks"] += 1
        reach["keptKids"] += k
        blocks.append({"geoid": b["geoid"], "lon": b["lon"], "lat": b["lat"], "kids": k, "ends": ends, "walk": w, "stu": st_})
    walk = [b["walk"] for b in blocks]
    flat = flat_ends(blocks)
    car, car_fallback = car_minutes(world, sub, door, blocks)
    reach["carFallbackBlocks"] = car_fallback
    kept_stu = sum(b["stu"] for b in blocks)
    students = None
    if total:
        students = {"total": total, "kept": round(kept_stu, 1), "beyond": round(total - kept_stu, 1),
                    "byLevel": {k: round(v, 1) for k, v in span.items() if v}, "how": stu_how, "choice": choice,
                    "source": stu_src}
    print("  %s: %d blocks, %d children %s within %.1f mi by street (%.0fs)" % (
        s["id"], len(blocks), sum(b["kids"] for b in blocks), "+".join(bands), REACH_MI, time.time() - t0))

    nets = {"brp": world.brp, "sfbike": world.sfb}
    today = {d: times_to(world, sub, seeds, nets[d], blocks, walk, flat) for d in nets}
    print("    today timed (%.0fs)" % (time.time() - t0))
    # Today on the plan's network from the repo's school point, joined and
    # capped as the citywide model does, for validate()'s pass check.
    repo_today = None
    rp = world.repo_point.get(s["repo_name"])
    if rp:
        rseeds = net.ends(rp[0], rp[1])
        rwalk_arr = sub.search([False] * len(G.eu), rseeds, 0.0)
        rwalk = []
        for b in blocks:
            w = INF
            for node, c, along, _e in b["ends"]:
                u = sub.ix.get(node)
                if u is not None and rwalk_arr[0][u] < INF:
                    w = min(w, rwalk_arr[2][u] + c + along)
            rwalk.append(w if w < INF else 0.0)
        repo_today = times_to(world, sub, rseeds, world.brp, blocks, rwalk, flat, today["brp"])

    # Options: plan corridors near the door, and the calmed zone.
    options = []
    near_m = CORRIDOR_MI * MI
    for g in world.groups + world.upgrade_groups:
        upgrade = tuple(g) in world.upgrade_keys
        pts = [p for k, pts_ in world.plan if k in set(g) for p in pts_]
        if not any(math.hypot(*(a - b for a, b in zip(walknet.xy(*p), (dx, dy)))) <= near_m for p in pts):
            continue
        edges = set()
        for k in g:
            edges |= world.line_edges.get(k, set())
        if not edges:
            continue
        meta = [world.plan_meta[k] for k in g]
        fac = sorted({m["facility"] for m in meta})
        classes = {str(world.street_class.get(m["cnn"])) for m in meta}
        strict_ok = all(f in ("Separated", "Car-free", "Shared-use Path") for f in fac) or classes <= RESIDENTIAL
        why = ("The plan draws it separated from cars" if all(f in ("Separated", "Car-free", "Shared-use Path") for f in fac)
               else "A side street the plan would share with calmed traffic. We take it as quiet enough (no car count is published)"
               if strict_ok else
               "A busier street the plan would share with traffic. SF Bike asks for a protected lane where more than 1,500 cars a day pass, and no count is published")
        if upgrade:
            codes = set().union(*(world.today_codes.get(m["cnn"], set()) for m in meta))
            now = ("a painted lane or signed route" if codes & {"2b", "2c", "3b", "3c"} else "a Slow Street that SFMTA's count finds too busy or fast")
            to = ("a separated lane" if all(f in ("Separated", "Car-free", "Shared-use Path") for f in fac) else "a calmed street")
            why = "An upgrade: today %s, which SF Bike's test doesn't count, and the plan draws %s. %s" % (now, to, why)
        gs = set(g)
        len_by_fac = collections.Counter()
        for k, pts_ in world.plan:
            if k in gs:
                len_by_fac[world.plan_meta[k]["facility"]] += sum(
                    math.hypot(*(a - b for a, b in zip(walknet.xy(*p), walknet.xy(*q)))) for p, q in zip(pts_, pts_[1:]))
        miles = sum(len_by_fac.values()) / MI
        typ = {"Separated": "separated", "Shared": "calmed", "Shared-use Path": "path", "Car-free": "car_free"}
        unit = {"low": 0.0, "central": 0.0, "high": 0.0}
        tot_len = sum(len_by_fac.values()) or 1.0
        for f in fac:
            u = costs["types"][typ[f]]
            share = len_by_fac[f] / tot_len
            for c in unit:
                unit[c] += u[c] * share
        ends_ = cross_ends(world, meta)
        lines = [[list(p) for p in pts_] for k, pts_ in world.plan if k in set(g)]
        options.append({"kind": "corridor", "id": world.corr_id[tuple(g)], "street": meta[0]["street"].title(), "facility": fac,
                        "upgrade": upgrade,
                        "from": ends_[0], "to": ends_[1],
                        "cnns": [m["cnn"] for m in meta], "miles": round(miles, 2),
                        "cost": {c: round(unit[c] * miles, 2) for c in unit}, "sfbikeOk": strict_ok, "sfbikeWhy": why,
                        "_edges": edges, "_keys": list(g), "lines": [[[round(x, 5), round(y, 5)] for x, y in L] for L in lines]})
    assert len({o["id"] for o in options}) == len(options), "corridor ids collide"
    mine_ids = {o["id"] for o in options}
    aliases = {k: v for k, v in sorted(world.corr_alias.items()) if v in mine_ids}
    zone = set()
    zr = ZONE_FT * FT
    for e in range(len(G.eu)):
        if G.ehw[e] not in ZONE_HW or world.sfb[e]:
            continue
        u, v = G.eu[e], G.ev[e]
        if math.hypot((G.x[u] + G.x[v]) / 2 - dx, (G.y[u] + G.y[v]) / 2 - dy) <= zr:
            zone.add(e)
    zmiles = sum(net.L[e] for e in zone) / MI
    cz = costs["types"]["calmed"]

    def full_cost(m):
        """The zone's full toolkit, dearer than a Slow Street: the calmed rate's central and high."""
        return {"low": round(cz["central"] * m, 2), "central": round(cz["high"] * m, 2), "high": round(cz["high"] * m, 2)}
    zone_opt = {"kind": "zone", "id": "zf", "variant": "full", "street": None, "miles": round(zmiles, 2),
                "cost": full_cost(zmiles), "sfbikeOk": True, "lines": merge_runs(line_pts(world, zone))}

    # The School Connector, two ways, per definition: the shortest walk from
    # the door to today's network with a protected lane wherever it follows a
    # busier street, and the shortest walk that never runs along one, calmed.
    csep = costs["types"]["separated"]
    ename = lambda e: world.osm_name.get(_pair((G.x[G.eu[e]], G.y[G.eu[e]]), (G.x[G.ev[e]], G.y[G.ev[e]])))  # noqa: E731

    def reach_net(d, arr):
        """The local node nearest the door (by walk) that touches a long enough run of safe streets, or None."""
        safe = nets[d]
        best = None
        for li in range(len(sub.adj)):
            if arr[0][li] == INF:
                continue
            if any(safe[e] and world.run_mi[d].get(e, 0) >= CONNECT_MIN_MI for _v, e in sub.adj[li]) and (
                    best is None or arr[2][li] < arr[2][best]):
                best = li
        return best

    def trace(d, arr, best, sd):
        """The route's edges door last, and the street it reaches."""
        safe = nets[d]
        edges = []
        x = best
        while arr[3][x] != -1:
            edges.append(arr[3][x])
            x = arr[4][x]
        # The door's own join onto the first node.
        g0 = sub.glob[x]
        j = min((s_ for s_ in sd if s_[0] == g0), key=lambda s_: s_[1] + s_[2], default=None)
        if j is not None and not safe[j[3]]:
            edges.append(j[3])
        to = None
        for _v, e in sorted(sub.adj[best], key=lambda t: t[1]):
            if safe[e] and world.run_mi[d].get(e, 0) >= CONNECT_MIN_MI:
                k = world.edge_line.get(e)
                to = nice_street(world.seg_name.get(k)) if k is not None else None
                to = to or ename(e) or "a path"
                break
        return edges, to

    def describe(d, edges, to, length_m):
        """One connector's record: what's built where, what counts under d, and its cost."""
        safe = nets[d]
        es = sorted(set(e for e in edges if not safe[e]))
        route = []
        for e in reversed(edges):  # door first
            nm = ename(e)
            if nm and not safe[e] and (not route or route[-1] != nm):
                route.append(nm)
        busy = collections.Counter()
        uncounted = collections.Counter()
        prot, calm = 0.0, 0.0
        count = set()
        for e in es:
            if G.ehw[e] in BUSY_HW:
                busy[ename(e) or ""] += net.L[e]
                prot += net.L[e]
                count.add(e)
            else:
                calm += net.L[e]
                if d == "brp" or world.edge_residential(e):
                    count.add(e)
                else:
                    uncounted[ename(e) or ""] += net.L[e]
        m = prot + calm
        cost = {c: round(csep[c] * prot / MI + cz[c] * calm / MI, 2) for c in ("low", "central", "high")}
        return {"onNetwork": False, "ft": int(round(m / FT)), "miles": round(m / MI, 3),
                "protectedFt": int(round(prot / FT)), "calmedFt": int(round(calm / FT)),
                "busyFt": int(round(sum(busy.values()) / FT)), "busyStreets": sorted(k for k in busy if k),
                "uncountedFt": int(round(sum(uncounted.values()) / FT)), "uncountedStreets": sorted(k for k in uncounted if k),
                "route": route, "to": to, "walkFt": int(round(length_m / FT)), "cost": cost,
                "lines": merge_runs(line_pts(world, es)), "_count": count}

    kconn = {}
    for d in nets:
        safe = nets[d]
        on = any(safe[e] and world.run_mi[d].get(e, 0) >= CONNECT_MIN_MI for _n, _c, _a, e in seeds)
        bp = None if on else reach_net(d, walk_arr)
        if bp is None:
            empty = {"onNetwork": True, "ft": 0, "miles": 0.0, "protectedFt": 0, "calmedFt": 0, "busyFt": 0, "busyStreets": [],
                     "uncountedFt": 0, "uncountedStreets": [], "route": [], "to": None, "walkFt": 0,
                     "cost": {"low": 0.0, "central": 0.0, "high": 0.0}, "lines": [], "_count": set()}
            kconn[("kf", d)] = dict(empty)
            kconn[("ks", d)] = dict(empty, noQuiet=False, needs=None)
            continue
        edges, to = trace(d, walk_arr, bp, seeds)
        kf = describe(d, edges, to, walk_arr[2][bp])
        kconn[("kf", d)] = kf
        # The calm route: never along a busier street that isn't already safe.
        skip = [G.ehw[e] in BUSY_HW and not safe[e] for e in range(len(G.eu))]
        cseeds = [s_ for s_ in seeds if not skip[s_[3]]]
        carr = sub.search([False] * len(G.eu), cseeds, 0.0, skip=skip) if cseeds else None
        bc = reach_net(d, carr) if carr else None
        limit = max(CALM_DETOUR * walk_arr[2][bp], walk_arr[2][bp] + CALM_EXTRA_FT * FT)
        if bc is None or carr[2][bc] > limit + 1e-6:
            needs = kf["busyStreets"][:1] or [ename(s_[3]) for s_ in seeds if G.ehw[s_[3]] in BUSY_HW and ename(s_[3])][:1]
            kconn[("ks", d)] = dict(kf, ft=0, miles=0.0, protectedFt=0, calmedFt=0, busyFt=0, busyStreets=[],
                                    uncountedFt=0, uncountedStreets=[], route=[], walkFt=0,
                                    cost={"low": 0.0, "central": 0.0, "high": 0.0}, lines=[], _count=set(),
                                    noQuiet=True, needs=needs[0] if needs else None,
                                    quietFt=int(round(carr[2][bc] / FT)) if bc is not None else None)
        else:
            cedges, cto = trace(d, carr, bc, cseeds)
            kconn[("ks", d)] = dict(describe(d, cedges, cto, carr[2][bc]), noQuiet=False, needs=None)
    kopts = []
    for variant in ("kf", "ks"):
        by = {d: {k: v for k, v in kconn[(variant, d)].items() if k != "_count"} for d in nets}
        kopts.append({"kind": "connector", "id": variant, "variant": "protected" if variant == "kf" else "calm",
                      "street": None, "miles": by["brp"]["miles"], "cost": by["brp"]["cost"], "byDef": by,
                      "sfbikeOk": True})

    def with_edges(d, *sets):
        bike = list(nets[d])
        for es in sets:
            for e in es:
                bike[e] = True
        return bike
    # Bases: the connector and the zone, alone and together, under each definition.
    base_edges = {}
    for d in nets:
        for k in ("", "kf", "ks"):
            for z in ("", "zf"):
                key = "+".join(x for x in (k, z) if x)
                sets = []
                if k:
                    sets.append(kconn[(k, d)]["_count"])
                if z:
                    sets.append(zone)
                base_edges[(d, key)] = sets
    base_rows = {}
    bases = {d: {} for d in nets}
    for (d, key), sets in sorted(base_edges.items()):
        if not key:
            base_rows[(d, key)] = today[d]
            continue
        if not any(sets_ for sets_ in sets):
            base_rows[(d, key)] = today[d]
            bases[d][key] = []
            continue
        rows = times_to(world, sub, seeds, with_edges(d, *sets), blocks, walk, flat, today[d])
        base_rows[(d, key)] = rows
        bases[d][key] = diff(today[d], rows)
    print("    %d bases timed (%.0fs)" % (len(base_rows), time.time() - t0))
    for o in options:
        o["gains"] = {}
        for d in nets:
            o["gains"][d] = {}
            if (d == "sfbike" and not o["sfbikeOk"]) or (d == "brp" and o["upgrade"]):
                continue
            for (dd, key), sets in sorted(base_edges.items()):
                if dd != d:
                    continue
                base = base_rows[(d, key)]
                o["gains"][d][key] = diff(base, times_to(world, sub, seeds, with_edges(d, o["_edges"], *sets), blocks, walk, flat, base))
    # How far the page's union of single corridors sits from building them all at once, with the full connector.
    corr = [o for o in options if o["kind"] == "corridor"]
    every = set()
    for o in corr:
        if not o["upgrade"]:
            every |= o["_edges"]
    kb = base_rows[("brp", "kf")]
    joint = times_to(world, sub, seeds, with_edges("brp", every, kconn[("kf", "brp")]["_count"]), blocks, walk, flat, kb)
    union = [list(r) if r else None for r in kb]
    for o in corr:
        for bi, t, sh, h in o["gains"]["brp"].get("kf", []):
            if union[bi] is None or t < union[bi][0]:
                union[bi] = [t, sh, h]
    within = lambda rows: round(sum(b["stu"] for b, r in zip(blocks, rows) if r and r[0] <= 150), 1)  # noqa: E731
    combo_check = {"union": within(union), "joint": within(joint), "corridors": len(corr), "base": "kf"}
    # Every corridor at once, exact, as its own option, so the page's "every
    # plan street" case is a real run rather than the union.
    # Its miles and cost are per definition: the plan's network leaves out the
    # upgrades it already counts, and SF Bike's test the streets it wouldn't count.
    use = {"brp": [o for o in corr if not o["upgrade"]], "sfbike": [o for o in corr if o["sfbikeOk"]]}
    byc = {d: {"miles": round(sum(o["miles"] for o in use[d]), 2),
               "cost": {c: round(sum(o["cost"][c] for o in use[d]), 2) for c in ("low", "central", "high")}} for d in use}
    allc = {"kind": "plan", "id": "all", "street": None, "miles": byc["brp"]["miles"], "cost": byc["brp"]["cost"],
            "byDefCost": byc, "sfbikeOk": True, "gains": {}}
    for d in nets:
        es = set()
        for o in use[d]:
            es |= o["_edges"]
        allc["gains"][d] = {}
        for (dd, key), sets in sorted(base_edges.items()):
            if dd != d:
                continue
            base = base_rows[(d, key)]
            allc["gains"][d][key] = diff(base, times_to(world, sub, seeds, with_edges(d, es, *sets), blocks, walk, flat, base))
    top_blocks, top_gains, top_check = top_sequence(world, sub, seeds, nets, blocks, walk, flat, corr, base_rows, base_edges,
                                                    with_edges, costs, door)
    print("    top blocks picked (%.0fs): %s" % (time.time() - t0, top_check))
    # What each corridor joins: today's safe bikeways (by street name) and other corridors, at a shared node.
    today_at = collections.defaultdict(set)
    for key, _pts in world.today_lines:
        nm = nice_street(world.seg_name.get(key)) or world.street_name.get(str(key))
        for e in world.line_edges.get(key, ()):
            for nd in (G.eu[e], G.ev[e]):
                today_at[nd].add(nm or "an unnamed path")
    corr_nodes = {o["id"]: {nd for e in o["_edges"] for nd in (G.eu[e], G.ev[e])} for o in options}
    for o in options:
        mine = corr_nodes[o["id"]]
        own = o["street"].lower()
        joins = sorted({nm for nd in mine for nm in today_at.get(nd, ())})
        o["joins"] = [j for j in joins if j.lower() != own] or joins
        o["joinsPlan"] = sorted({p["street"] for p in options if p["id"] != o["id"] and corr_nodes[p["id"]] & mine})
    options.sort(key=lambda o: (o["street"] or "", o["id"]))
    options = kopts + [zone_opt] + options + [allc]
    for o in options:
        o.pop("_edges", None)
    print("    %d options timed (%.0fs)" % (len(options), time.time() - t0))

    # Today's networks near the school, for the map.
    box = radius + 400
    def near_line(pts_):
        return any(math.hypot(*(a - b for a, b in zip(walknet.xy(*p), (dx, dy)))) <= box for p in pts_)
    net_lines = {"brp": [], "sfbike": [], "plan": []}
    for key, pts_ in world.today_lines:
        if near_line(pts_):
            L = [[round(x, 5), round(y, 5)] for x, y in pts_]
            net_lines["brp"].append(L)
            if key in world.today_strict_keys:
                net_lines["sfbike"].append(L)
    for key, pts_ in world.plan:
        if world.plan_meta[key]["cnn"] not in world.today_keys and near_line(pts_):
            net_lines["plan"].append([[round(x, 5), round(y, 5)] for x, y in pts_])

    # Muni.
    muni = None
    msrc = read("site", "data", "muni-schools.json")
    mrow = next((m for m in msrc["schools"] if m["name"] == s["repo_name"]), None)
    if mrow:
        bell = s["bell"].get("start") or None
        win = next((w for w in mrow["windows"] if w["name"] == "start"), None)
        bell_used = bell or win["bell"]
        bm = bell_minutes(bell_used)
        stops = []
        walk_ft = {}
        for st in mrow["stops"]:
            ends = net.ends(st["lon"], st["lat"])
            best = None
            for node, c, along, e in ends:
                u = sub.ix.get(node)
                if u is None or walk_arr[0][u] == INF:
                    continue
                m = walk_arr[2][u] + c + along
                if best is None or m < best[0]:
                    best = (m, u, e)
            row = {"id": st["id"], "name": st["name"], "ft": int(round(feet_between(st, door))), "lon": st["lon"],
                   "lat": st["lat"], "routes": st["routes"]}
            if best:
                m, u, e = best
                # Share of the shortest walk on safe edges, and high-injury streets it touches.
                safe = {}
                for d in nets:
                    on = 0.0
                    x = u
                    while x != -1 and walk_arr[3][x] != -1:
                        ee = walk_arr[3][x]
                        if nets[d][ee]:
                            on += net.L[ee]
                        x = walk_arr[4][x]
                    safe[d] = int(round(100 * on / m)) if m else 0
                row["walkFt"] = int(round(m / FT))
                row["safe"] = safe
                row["hin"] = route_hin(world, sub, walk_arr, u, e, [False] * len(G.eu), [False] * len(G.eu))
                walk_ft[st["id"]] = row["walkFt"]
            stops.append(row)
        # Arrivals that still make the bell on foot from their stop, by route and direction.
        before = collections.Counter()
        times_by_route = collections.defaultdict(lambda: collections.defaultdict(list))
        at_stop = collections.defaultdict(lambda: collections.defaultdict(list))
        for route, dirs in (win["arrivals"] if win else {}).items():
            dnames = {k: v.get("name", k) for k, v in msrc["routes"].get(route, {}).get("directions", {}).items()}
            for d, by_stop in dirs.items():
                for stop, ts in by_stop.items():
                    wf = walk_ft.get(stop)
                    if wf is None:
                        continue
                    for t in ts:
                        tm_ = bell_minutes(t)
                        if bm - 45 <= tm_ and tm_ + wf / WALK_FT_PER_MIN <= bm:
                            before[route] += 1
                            times_by_route[route][dnames.get(d, d)].append(t)
                            at_stop[stop][route].append(t)
        for row in stops:
            nx = at_stop.get(row["id"])
            if nx:
                row["next"] = {r: sorted(v) for r, v in sorted(nx.items())}
        served = sorted(before)
        # Children within a quarter mile of a route with an arrival before the bell.
        segs = []
        for r in served:
            for dd in msrc["routes"].get(r, {}).get("directions", {}).values():
                P = [walknet.xy(*p) for p in dd["shape"]]
                segs += list(zip(P, P[1:]))
        reach_m = MUNI_REACH_FT * FT
        one_seat = 0
        for b in blocks:
            bx, by = walknet.xy(b["lon"], b["lat"])
            if any(stt.seg_dist(bx, by, a[0], a[1], c[0], c[1]) <= reach_m for a, c in segs):
                one_seat += b["stu"]
        one_seat = round(one_seat, 1)
        routes = {}
        for r in served:
            rr = msrc["routes"].get(r)
            if rr:
                routes[r] = {"long": rr["long"], "type": rr["type"],
                             "shapes": [dd["shape"] for dd in rr["directions"].values()]}
        muni = {"bell": bell_used, "bellSource": "school" if bell else mrow["bellSource"], "window": [win["from"], win["to"]] if win else None,
                "before": dict(sorted(before.items())),
                "beforeTimes": {k: {d: sorted(ts) for d, ts in sorted(v.items())} for k, v in sorted(times_by_route.items())},
                "stops": stops, "routes": routes, "oneSeat": one_seat, "feed": msrc["feed"], "source": msrc["source"],
                "notice": msrc["notice"]}

    # Street work nearby.
    work = []
    coord = read("site", "data", "coordination.json")
    wm = WORK_MI * MI
    for p in coord["projects"]:
        if p.get("ended") or not p.get("geometry"):
            continue
        geo = p["geometry"]
        flat = [pt for L in geo for pt in L] if geo and isinstance(geo[0][0], list) else geo
        try:
            dmin = min(math.hypot(*(a - b for a, b in zip(walknet.xy(*pt[:2]), (dx, dy)))) for pt in flat)
        except (TypeError, ValueError):
            continue
        if dmin > wm:
            continue
        work.append({"name": p["name"], "kind": p["kind"], "department": p["department"], "phase": p.get("phase"),
                     "start": p.get("start"), "end": p.get("end"), "streets": p.get("streets"), "ft": int(round(dmin / FT)),
                     "onPlan": p.get("onPlan"), "slug": p["slug"],
                     "lines": geo if isinstance(geo[0][0], list) else [geo]})
    work.sort(key=lambda w: (w["start"] or "9999", w["name"]))

    # SFUSD's attendance area for the school, where one is drawn around it
    # (DataSF e6tr-sxwg): the area holding the door whose name matches the school's.
    area = None
    want = set(stt.norm(s["repo_name"])) - stt.STOP
    for a_ in world.areas:
        have = (set(stt.norm(a_["name"])) | set(stt.norm(a_["short"]))) - stt.STOP
        if want and have and len(want & have) / float(len(want)) >= 0.5 and stt.in_poly(door["lon"], door["lat"], a_["polys"]):
            area = {"name": a_["name"], "rings": [[[round(x, 5), round(y, 5)] for x, y, *_ in ring] for poly in a_["polys"] for ring in poly[:1]]}
            break

    pr = priority.get(s["repo_name"], {})
    en = enrol["schools"].get(s["id"]) or {}
    out = {
        "id": s["id"], "name": s["name"], "repoName": s["repo_name"], "public": s["public"], "grades": s["grades"],
        "bands": bands, "address": s["address"], "door": {k: door[k] for k in ("lon", "lat", "how", "tag", "description")},
        "bell": s["bell"], "dropOff": s["drop_off"], "loadingZone": s.get("loading_zone"),
        "afterSchool": s.get("after_school"), "schoolStreet": s.get("school_street"), "quotes": s.get("quotes", []), "sources": s.get("sources", []),
        "confidence": s.get("confidence"), "confidenceWhy": s.get("confidence_why"), "gaps": s.get("gaps", []),
        "enrolment": en if en.get("total") else {"total": None, "why": en.get("why")},
        "crashes": {k: pr.get(k) for k in ("bell_crashes_600ft", "expected_600ft", "p_at_least_seen", "hin_ft", "hin_street",
                                           "ej_community", "sfmta_group_label", "bell_source")},
        "model": {"walkMph": stt.WALK_MPH, "rideMph": stt.RIDE_MPH, "targetMin": 15, "detour": stt.DETOUR,
                  "reachMi": REACH_MI, "corridorMi": CORRIDOR_MI, "zoneFt": ZONE_FT, "connectMinMi": CONNECT_MIN_MI, "workMi": WORK_MI,
                  "slowUnmeasured": world.slow_unmeasured, "hinRead": world.hin_fetched,
                  "carMph": CAR_MPH, "carFixedMin": CAR_FIXED_MIN, "carSpeedSrc": CAR_SPEED_SRC},
        "blocks": [[round(b["lon"], 5), round(b["lat"], 5), b["kids"], int(round(b["walk"] / FT)), round(b["stu"], 3), c]
                   for b, c in zip(blocks, car)],
        "students": students,
        "today": {d: [r if r is None else list(r) for r in today[d]] for d in nets},
        "bases": bases, "options": options, "network": {k: merge_runs([[a, b] for L in v for a, b in zip(L, L[1:])]) for k, v in net_lines.items()},
        "topBlocks": top_blocks, "topGains": top_gains, "topCheck": top_check,
        "muni": muni, "work": work, "comboCheck": combo_check, "corridorAliases": aliases, "attendanceArea": area,
    }
    out["model"]["streetClassRead"] = world.street_read
    out["model"]["reach"] = {k: reach[k] for k in sorted(reach)}
    out["model"]["calmDetour"] = CALM_DETOUR
    out["model"]["calmExtraFt"] = CALM_EXTRA_FT
    if s["id"] in HELD:
        out["held"] = HELD[s["id"]]
    return out, repo_today


def _diffs(tr, si, lvl, data, rows):
    ours = {(b[0], b[1]): r for b, r in zip(data["blocks"], rows)}
    d = []
    for row in tr:
        x = row[lvl]
        if x.get("school_today") != si or x.get("today") is None:
            continue
        r = ours.get((row["lon"], row["lat"]))
        if r is None:
            continue
        d.append(r[0] / 10.0 - x["today"])
    if not d:
        return None
    d.sort()
    return {"blocks": len(d), "median_min": round(d[len(d) // 2], 2), "max_min": round(d[-1], 2), "min_min": round(d[0], 2)}


def validate(world, s, data, repo_today):
    """How far this run's brp times sit from the citywide model's, for blocks whose nearest school of the level is this one.

    pass: from the repo's school point, joined and capped as the citywide
    model does, so only pass 1 against pass 2 differs, and pass 1 can only be
    slower. door: from the door, as the page uses it."""
    tr = read("out", "school-travel", "blocks.json")["blocks"]
    names = [x["name"] for x in read("out", "school-travel", "summary.json")["schools"]["list"]]
    if s["repo_name"] not in names:
        return None
    si = names.index(s["repo_name"])
    lvl = {"5-9": "elementary", "10-14": "middle", "15-17": "high"}[data["bands"][0]]
    eff = None
    if repo_today:
        # The same blocks as the citywide check: those whose nearest school
        # this is. Farther blocks sit near the detour cap, where a cap measured
        # from a different point swings a route between riding and walking.
        mine = {(row["lon"], row["lat"]) for row in tr if row[lvl].get("school_today") == si}
        d = sorted(a[0] / 10.0 - b[0] / 10.0 for blk, a, b in zip(data["blocks"], data["today"]["brp"], repo_today)
                   if a and b and (blk[0], blk[1]) in mine)
        if d:
            eff = {"blocks": len(d), "median_min": round(d[len(d) // 2], 2), "max_min": round(d[-1], 2), "min_min": round(d[0], 2)}
    return {"pass": _diffs(tr, si, lvl, data, repo_today) if repo_today else None,
            "door": _diffs(tr, si, lvl, data, data["today"]["brp"]),
            "doorEffect": eff}


def slug(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def synth(row):
    """A case-study record for a school not yet researched: the repo's point as its door, nothing else."""
    return {"id": slug(row["name"]), "name": row["name"], "repo_name": row["name"], "public": not row["private"],
            "grades": row["grades"], "address": None,
            "door": {"lon": row["lon"], "lat": row["lat"], "how": "the repo's school point (CDE directory or DataSF 7e7j-59qk)",
                     "tag": "", "description": "The school's point in the state directory; its door hasn't been placed."},
            "drop_off": "Not researched.", "bell": {}, "loading_zone": None, "school_street": None, "quotes": [],
            "sources": [], "confidence": "unresearched", "confidence_why": None,
            "gaps": ["This school isn't in data/school-case/dropoff.json, so its door, bell times and drop-off rules haven't been researched."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--school", action="append",
                    help="school id from data/school-case/dropoff.json, or any school's name in out/school-priority/schools.csv (repeatable; default every dropoff.json school)")
    ap.add_argument("--fetch-enrolment", action="store_true", help="re-read CDE enrolment before building")
    ap.add_argument("--pure", action="store_true", help="use the pure-Python searches on a subgraph, not lib/rcsp.c")
    a = ap.parse_args()
    drop = read("data", "school-case", "dropoff.json")
    schools = [s for s in drop["schools"] if not a.school or s["id"] in a.school]
    # Any other school the priority table ranks can be added by its name, from
    # data alone: its point and grades from out/school-hour-crashes, and no
    # door, bell or drop-off research.
    known = {s["id"] for s in schools} | {s["repo_name"] for s in schools}
    for want in a.school or []:
        if want in known:
            continue
        row = next((r for r in read("out", "school-hour-crashes", "schools.json") if r["name"] == want), None)
        assert row, "no such school: %s (use an id from dropoff.json or a name from out/school-priority/schools.csv)" % want
        schools.append(synth(row))
    assert schools, "no such school"
    enrol, failures, _changed = school_enrolment.ensure(
        drop["schools"] + [x for x in schools if x["id"] not in {d["id"] for d in drop["schools"]}], refresh=a.fetch_enrolment)
    assert not failures, "enrolment read failed: %s" % failures
    costs = read("data", "school-budget", "unit-costs.json")
    import csv
    priority = {r["school"]: r for r in csv.DictReader(open(os.path.join(ROOT, "out", "school-priority", "schools.csv")))}
    for r in priority.values():
        for k in ("bell_crashes_600ft", "hin_ft"):
            r[k] = int(r[k]) if r.get(k) not in (None, "") else None
        for k in ("expected_600ft", "p_at_least_seen"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
        r["ej_community"] = r.get("ej_community") == "True"
    world = World(pure=a.pure)
    os.makedirs(OUT, exist_ok=True)
    bad = []
    for s in schools:
        data, repo_today = build(world, s, enrol, costs, priority)
        v = validate(world, s, data, repo_today)
        data["model"]["citywideCheck"] = v
        if v and v["pass"] and v["pass"]["min_min"] < -PASS_SLACK_MIN:
            # Pass 1 faster than pass 2 for the same origin is a broken search, not a finding.
            bad.append("%s: pass check min %+.2f min" % (s["id"], v["pass"]["min_min"]))
            print("    %s NOT WRITTEN: pass 1 came out faster than the citywide pass 2 (%s)" % (s["id"], v["pass"]))
            continue
        st_ = data["students"] or {}
        within = {d: sum(b[4] for b, r in zip(data["blocks"], data["today"][d]) if r and r[0] <= 150) for d in data["today"]}
        print("    %s: %s students, %.0f in reach; within 15 min today brp %.0f, sfbike %.0f; %d options (%d upgrades); check vs citywide %s" % (
            s["id"], st_.get("total"), st_.get("kept") or 0, within["brp"], within["sfbike"], len(data["options"]),
            sum(1 for o in data["options"] if o.get("upgrade")), v))
        stable.write_json(os.path.join(OUT, "%s.json" % s["id"]), data, separators=(",", ":"))
    reg = corridor_ids.register_blocks(corridor_ids.load(), world.block_reg)
    corridor_ids.save(reg)
    print("  wrote %s" % os.path.relpath(OUT, ROOT))
    if bad:
        sys.exit("school-case: " + "; ".join(bad))


if __name__ == "__main__":
    main()
