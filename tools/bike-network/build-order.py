#!/usr/bin/env python3
"""A year-by-year build order for the North Star plan: which plan miles bring the most people within 15 minutes of school, jobs, groceries, libraries and clinics, at 20, 40 and 100 miles a year, with each plan chunk's gain alone and in the finished network.

    tools/bike-network/build-order.py                        # out/build-order/*.json
    tools/bike-network/build-order.py --epc-weight 1 --hin-weight 1   # the weighted variant
    tools/bike-network/build-order.py --bbox -122.43,37.75,-122.40,37.77   # development subset

Bryan, 2026-09-30: "Build our model." The question on
the task: given n miles a year, which miles reach the most people, where the
destinations are schools, jobs and services.

THE MODEL is lib/school-travel-time.py's network and speeds, imported from
it: OpenStreetMap's walk network; an edge along an all-ages bikeway is ridden
at 10 mph, every other edge walked at 2 mph; a block joins the network along
its frontage; the all-ages network today and the North Star plan's blocks are
picked exactly as that script picks them. One thing differs: there is no
detour cap. A trip's time is the fastest route over the network, however
long, as in Conveyal-style access analysis. The detour-capped search is exact
but costs a label-setting search per block and school, and a build order
re-times the city after every pick, for seven destination sets. The effect of
dropping the cap is measured, not assumed: the children-to-school counts for
today and for the finished plan are printed beside school-travel-time.py's
(summary.json) and written to the output's `validation`.

DESTINATIONS, each a set of points, and a person is within 15 minutes when the
fastest trip to the nearest one takes at most 15 minutes:
  * school: children 5-9, 10-14 and 15-17 (2020 DHC P12 by block) to the
    nearest school of their level, the list school-travel-time.py loads.
    Kept as its own measure, counted in children.
  * jobs: residents (2020 PL total population by block, DataSF p2fw-hsrv) to
    the nearest job centre, a 2020 block with at least JOB_CENTRE_MIN jobs in
    LEHD LODES 8 WAC 2023 (all jobs, C000). 132 blocks, 58% of SF's jobs.
  * grocery: residents to the nearest OpenStreetMap supermarket, grocery or
    greengrocer.
  * library: residents to the nearest open SFPL branch (DataSF nc68-ngbr,
    data/extract/libraries/branches.json).
  * health: residents to the nearest clinic or general acute care hospital,
    DataSF Health Care Facilities (jhsu-2pka), whose rows date from 2021.
Inputs are fetched by scripts/access-inputs.py into data/extract/access/.

CANDIDATES are school-budget.py's: the plan's North Star blocks not all-ages
today, joined into runs on one street and cut into chunks of about a quarter
mile. Miles are centerline miles (school-budget.py's MILES).

THE OBJECTIVE. For each chunk, the people newly within 15 minutes of each
destination type if it is added to the network as it stands; the score is
their sum over the five types, equal weights, divided by the chunk's miles.
Optional weights, both off by default, carry SFMTA's "network value"
criteria (Biking and Rolling Plan pp. 86-87): --epc-weight w counts a person
in an MTC Equity Priority Community tract (Plan Bay Area 2050 Plus) as 1 + w
people, and --hin-weight w multiplies a chunk's score by 1 + w x the share
of its miles on SFMTA's 2022 High Injury Network. Each measure is reported
separately whatever the weights.

THE GREEDY. Pick the chunk with the best score, add it, update every
travel time it changes, and re-score only the chunks whose last evaluation
read a node the pick changed (exact: a chunk's gain depends only on the times
and edges it read). When no chunk brings anyone new within 15 minutes, the
rest of the plan is still built, in this order: chunks touching the network
as it stands first (gap closure), then by High Injury Network share, longest
first; a later chunk that gains again is picked on score. So the order runs
until the plan runs out.

THE UPDATE is exact. Times are the multi-source shortest path from each
destination set, capped at 15 minutes (a time over it is only known to be
over). Adding a bikeway only shortens edges, so a pick is a decrease-only
update relaxed outward from its edges. A chunk's value in the finished
network, what is lost if it alone is left out, is the reverse: the nodes
whose shortest path used its edges are recomputed from their neighbours.

YEARS. At R miles a year, year k's network is the longest prefix of the order
whose miles fit in k x R (a chunk that does not fit waits for the next year).
The last year is the one in which the plan runs out; after it nothing is left
to build and the figures stop.

WHAT IT WRITES.
  out/build-order/build-order.json  the order, cumulative people per type, and
                                    the years at 20, 40 and 100 miles a year.
  out/build-order/segments.json     one row per chunk, keyed by a stable id
                                    (street/first CNN-last CNN), with its CNNs,
                                    miles, High Injury Network miles, greedy
                                    rank, and people per type alone (added to
                                    today's network) and in the network (lost
                                    if it alone is left out of the finished
                                    plan); plus a CNN -> chunk index.
With weights set, the files are written with a suffix (build-order-w.json).
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
from lib import stable  # noqa: E402
import walknet  # noqa: E402

SB = paths.load("school-budget.py")
ST = SB.ST

OUT = os.path.join(ROOT, "out", "build-order")
ACCESS = os.path.join(ROOT, "data", "extract", "access")
MILE = 1609.344
FOOT = 0.3048
RW, RB, INF = ST.RW, ST.RB, float("inf")
CAP = ST.TARGET_MIN * 60.0
EPS = 1e-6
RATES = [20, 40, 100]
JOB_CENTRE_MIN = 1000
HIN_SNAP_M = 20.0
TYPES = ["school", "jobs", "grocery", "library", "health"]
TYPE_LABEL = {"school": "children 5-17 within 15 minutes of a school of their level",
              "jobs": "residents within 15 minutes of a job centre (a block with at least %d jobs)" % JOB_CENTRE_MIN,
              "grocery": "residents within 15 minutes of a supermarket, grocery or greengrocer",
              "library": "residents within 15 minutes of an open public library branch",
              "health": "residents within 15 minutes of a clinic or general acute care hospital"}


def read(*p):
    return json.load(open(os.path.join(*p)))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


# -- one destination set ---------------------------------------------------------

class Measure(object):
    """Travel times to the nearest point of one destination set, capped at CAP, kept current as bikeways are added."""

    def __init__(self, name, typ, net, points, weights, cap=CAP):
        self.name, self.typ, self.net, self.cap = name, typ, net, cap
        self.seeds = []  # (node, connector m, along m, edge)
        for lon, lat in points:
            self.seeds.extend(net.ends(lon, lat))
        self.seeds_on = collections.defaultdict(list)
        for s in self.seeds:
            self.seeds_on[s[3]].append(s)
        self.seeds_on_node = collections.defaultdict(list)
        for s in self.seeds:
            self.seeds_on_node[s[0]].append(s)
        self.w = weights  # per origin block
        self.D = None

    def seed_t(self, s, bike, extra=()):
        node, c, along, e = s
        return c * RW + along * (RB if (bike[e] or e in extra) else RW)

    def full(self, bike, parents=False):
        """Capped multi-source Dijkstra. With parents: (D, parent edge or -1 for a seed, seed edge)."""
        n = len(self.net.adj)
        D = [INF] * n
        pe = [-2] * n if parents else None
        se = [-1] * n if parents else None
        h = []
        for s in self.seeds:
            t = self.seed_t(s, bike)
            if t <= self.cap and t < D[s[0]]:
                D[s[0]] = t
                if parents:
                    pe[s[0]], se[s[0]] = -1, s[3]
                h.append((t, s[0]))
        heapq.heapify(h)
        adj, L = self.net.adj, self.net.L
        while h:
            d, u = heapq.heappop(h)
            if d > D[u]:
                continue
            for v, e in adj[u]:
                nd = d + L[e] * (RB if bike[e] else RW)
                if nd <= self.cap and nd < D[v]:
                    D[v] = nd
                    if parents:
                        pe[v] = e
                    heapq.heappush(h, (nd, v))
        return (D, pe, se) if parents else D

    def add(self, E, bike):
        """Nodes whose time falls when edges E become bikeways: ({node: new time}, nodes read)."""
        D, adj, L, G = self.D, self.net.adj, self.net.L, self.net.G
        ch = {}
        h = []
        read = set()
        for e in E:
            u, v = G.eu[e], G.ev[e]
            read.add(u)
            read.add(v)
            w = L[e] * RB
            for a, b in ((u, v), (v, u)):
                if D[a] < INF:
                    nd = D[a] + w
                    if nd <= self.cap and nd < ch.get(b, D[b]) - EPS:
                        ch[b] = nd
                        h.append((nd, b))
            for s in self.seeds_on.get(e, ()):
                t = self.seed_t(s, bike, E)
                if t <= self.cap and t < ch.get(s[0], D[s[0]]) - EPS:
                    ch[s[0]] = t
                    h.append((t, s[0]))
        heapq.heapify(h)
        while h:
            d, u = heapq.heappop(h)
            if d > ch[u]:
                continue
            for v, e in adj[u]:
                read.add(v)
                nd = d + L[e] * (RB if (bike[e] or e in E) else RW)
                if nd <= self.cap and nd < ch.get(v, D[v]) - EPS:
                    ch[v] = nd
                    heapq.heappush(h, (nd, v))
        read.update(ch)
        return ch, read

    def remove(self, E, bike_without, P):
        """With the finished network's (D, pe, se, kids) in P: {node: new time} when edges E are walked again."""
        D, pe, se, kids = P
        G, adj, L = self.net.G, self.net.adj, self.net.L
        roots = set()
        for e in E:
            for x in (G.eu[e], G.ev[e]):
                if pe[x] == e or (pe[x] == -1 and se[x] in E):
                    roots.add(x)
        for e in E:
            for s in self.seeds_on.get(e, ()):
                if pe[s[0]] == -1 and se[s[0]] == e:
                    roots.add(s[0])
        A = set()
        stack = list(roots)
        while stack:
            u = stack.pop()
            if u in A:
                continue
            A.add(u)
            stack.extend(kids.get(u, ()))
        if not A:
            return {}
        new = {u: INF for u in A}
        for u in A:
            for s in self.seeds_on_node.get(u, ()):
                t = self.seed_t(s, bike_without)
                if t < new[u]:
                    new[u] = t
            for v, e in adj[u]:
                if v not in A and D[v] < INF:
                    nd = D[v] + L[e] * (RB if bike_without[e] else RW)
                    if nd < new[u]:
                        new[u] = nd
        h = [(t, u) for u, t in new.items() if t <= self.cap]
        heapq.heapify(h)
        while h:
            d, u = heapq.heappop(h)
            if d > new[u]:
                continue
            for v, e in adj[u]:
                if v in A:
                    nd = d + L[e] * (RB if bike_without[e] else RW)
                    if nd <= self.cap and nd < new[v]:
                        new[v] = nd
                        heapq.heappush(h, (nd, v))
        return {u: t for u, t in new.items() if t != D[u]}


# -- origins ---------------------------------------------------------------------

class Origins(object):
    def __init__(self, blocks):
        self.blocks = blocks
        self.node_blocks = collections.defaultdict(list)
        self.edge_blocks = collections.defaultdict(list)
        for i, b in enumerate(blocks):
            for node, _c, _a, e in b["ends"]:
                self.node_blocks[node].append(i)
                self.edge_blocks[e].append(i)

    def time(self, b, D, bike, over=None, extra=()):
        best = INF
        for node, c, along, e in b["ends"]:
            d = over.get(node, D[node]) if over else D[node]
            if d < INF:
                t = d + c * RW + along * (RB if (bike[e] or e in extra) else RW)
                if t < best:
                    best = t
        return best

    def touched(self, nodes, E):
        out = set()
        for x in nodes:
            out.update(self.node_blocks.get(x, ()))
        for e in E:
            out.update(self.edge_blocks.get(e, ()))
        return out


# -- the model -------------------------------------------------------------------

class Model(object):
    def __init__(self, net, origins, measures, bike, epc_w, epc):
        self.net, self.o, self.ms, self.bike = net, origins, measures, list(bike)
        self.mult = [1.0 + epc_w * epc[i] for i in range(len(origins.blocks))]
        for m in measures:
            m.D = m.full(self.bike)
        self.T = {m.name: [origins.time(b, m.D, self.bike) for b in origins.blocks] for m in measures}

    def under(self, m):
        return sum(m.w[i] for i, t in enumerate(self.T[m.name]) if t <= CAP + EPS)

    def evaluate(self, E):
        """People newly within 15 minutes per measure, weighted score, nodes read."""
        E = {e for e in E if not self.bike[e]}
        gains, score, read = {}, 0.0, set()
        for m in self.ms:
            ch, rd = m.add(E, self.bike)
            read |= rd
            g = 0
            for i in self.o.touched(ch, E):
                if not m.w[i] or self.T[m.name][i] <= CAP + EPS:
                    continue
                # The block's time reads every end, so a pick changing any of them re-scores this chunk.
                read.update(node for node, _c, _a, _e in self.o.blocks[i]["ends"])
                if self.o.time(self.o.blocks[i], m.D, self.bike, ch, E) <= CAP + EPS:
                    g += m.w[i]
                    score += m.w[i] * self.mult[i]
            gains[m.name] = g
        return gains, score, read

    def commit(self, E):
        E = {e for e in E if not self.bike[e]}
        dirty = set()
        gains = {}
        for m in self.ms:
            ch, _rd = m.add(E, self.bike)
            for x, t in ch.items():
                m.D[x] = t
            dirty.update(ch)
            gains[m.name] = 0
            gains.setdefault("_blocks_" + m.name, [])
            m._ch = ch
        for e in E:
            self.bike[e] = True
            dirty.add(self.net.G.eu[e])
            dirty.add(self.net.G.ev[e])
        for m in self.ms:
            for i in self.o.touched(m._ch, E):
                t = self.o.time(self.o.blocks[i], m.D, self.bike)
                if t <= CAP + EPS < self.T[m.name][i] and m.w[i]:
                    gains[m.name] += m.w[i]
                    gains["_blocks_" + m.name].append(i)
                self.T[m.name][i] = t
            m._ch = None
        return gains, dirty


def job_access(net, origins, centres, bike_today, bike_plan, order_edges, cuts, chunk_edges, t0):
    """Jobs within 15 minutes, summed over residents: sum over blocks of residents x the jobs at every job
    centre within 15 minutes. One capped search per centre, updated along the build order.

    Returns (today, finished plan, {prefix length: value}, {chunk: gain alone}, {chunk: loss in network})."""
    blocks = origins.blocks
    pop = [b["pop"] for b in blocks]
    G = net.G
    today = plan = 0
    at_cut = collections.Counter()
    alone, lost = collections.Counter(), collections.Counter()
    for ci, (pt, jobs) in enumerate(centres):
        m = Measure("centre", "jobs_access", net, [pt], pop)
        m.D = m.full(bike_today)
        T = [origins.time(b, m.D, bike_today) for b in blocks]
        val = sum(p for p, t in zip(pop, T) if t <= CAP + EPS)
        today += val * jobs
        at_cut[0] += val * jobs if 0 in cuts else 0
        for cid, E in chunk_edges.items():
            E = {e for e in E if not bike_today[e]}
            ch, _r = m.add(E, bike_today)
            g = sum(pop[i] for i in origins.touched(ch, E)
                    if T[i] > CAP + EPS and origins.time(blocks[i], m.D, bike_today, ch, E) <= CAP + EPS)
            alone[cid] += g * jobs
        bike = list(bike_today)
        for pos, E in enumerate(order_edges, 1):
            E = {e for e in E if not bike[e]}
            ch, _r = m.add(E, bike)
            for x, t in ch.items():
                m.D[x] = t
            for e in E:
                bike[e] = True
            for i in origins.touched(ch, E):
                t = origins.time(blocks[i], m.D, bike)
                if t <= CAP + EPS < T[i]:
                    val += pop[i]
                T[i] = t
            if pos in cuts:
                at_cut[pos] += val * jobs
        plan += val * jobs
        D, pe, se = m.full(bike_plan, parents=True)
        fresh = sum(pop[i] for i, b in enumerate(blocks) if origins.time(b, D, bike_plan) <= CAP + EPS)
        if fresh != val:
            raise SystemExit("job access for centre %d drifted: %d along the order, %d fresh" % (ci, val, fresh))
        kids_ = collections.defaultdict(list)
        for v in range(len(D)):
            e = pe[v]
            if e >= 0:
                kids_[G.eu[e] if G.ev[e] == v else G.ev[e]].append(v)
        P = (D, pe, se, kids_)
        for cid, E in chunk_edges.items():
            E = set(E)
            without = list(bike_plan)
            for e in E:
                without[e] = False
            ch = m.remove(E, without, P)
            n_lost = sum(pop[i] for i in origins.touched(ch, E)
                         if T[i] <= CAP + EPS and origins.time(blocks[i], D, without, ch) > CAP + EPS)
            lost[cid] += n_lost * jobs
        if ci % 20 == 0:
            print("    job access: centre %d/%d (%.0fs)" % (ci, len(centres), time.time() - t0), flush=True)
    return today, plan, at_cut, alone, lost


MINUTES_CAP = 30 * 60.0  # school times for the minutes-saved measures are exact up to 30 minutes
SHORTER_S = 120.0        # "at least 2 minutes shorter"


def school_minutes(net, origins, levels, bike_today, bike_plan, chunk_edges, t0):
    """Per chunk, over every child (not only those crossing 15 minutes): child-minutes saved, and children
    whose trip is at least SHORTER_S shorter; alone on today's network and in the finished plan.

    levels: [(name, school points, children per block)]. Times are searched to MINUTES_CAP; a trip over it
    counts as MINUTES_CAP, so a saving from a trip that long is a lower bound.
    Returns ({chunk: [minutes, children]} alone, the same in the network)."""
    blocks = origins.blocks
    alone = collections.defaultdict(lambda: [0.0, 0])
    innet = collections.defaultdict(lambda: [0.0, 0])

    def tally(acc, i, w, before, after):
        before, after = min(before, MINUTES_CAP), min(after, MINUTES_CAP)
        if after < before - EPS:
            acc[0] += w * (before - after) / 60.0
            if before - after >= SHORTER_S - EPS:
                acc[1] += w
    for name, points, w in levels:
        m = Measure(name, "school", net, points, w, cap=MINUTES_CAP)
        m.D = m.full(bike_today)
        T = [origins.time(b, m.D, bike_today) for b in blocks]
        for cid, E in chunk_edges.items():
            E = {e for e in E if not bike_today[e]}
            ch, _r = m.add(E, bike_today)
            for i in origins.touched(ch, E):
                if w[i]:
                    tally(alone[cid], i, w[i], T[i], origins.time(blocks[i], m.D, bike_today, ch, E))
        D, pe, se = m.full(bike_plan, parents=True)
        kids_ = collections.defaultdict(list)
        G = net.G
        for v in range(len(D)):
            e = pe[v]
            if e >= 0:
                kids_[G.eu[e] if G.ev[e] == v else G.ev[e]].append(v)
        Tp = [origins.time(b, D, bike_plan) for b in blocks]
        for cid, E in chunk_edges.items():
            E = set(E)
            without = list(bike_plan)
            for e in E:
                without[e] = False
            ch = m.remove(E, without, (D, pe, se, kids_))
            for i in origins.touched(ch, E):
                if w[i]:
                    tally(innet[cid], i, w[i], origins.time(blocks[i], D, without, ch), Tp[i])
        print("    school minutes: %s done (%.0fs)" % (name, time.time() - t0), flush=True)
    return alone, innet


def type_sum(d, measures):
    out = collections.Counter()
    for m in measures:
        out[m.typ] += d.get(m.name, 0)
    return {t: out[t] for t in TYPES}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--epc-weight", type=float, default=0.0)
    ap.add_argument("--hin-weight", type=float, default=0.0)
    ap.add_argument("--bbox", default="", help="development: lon0,lat0,lon1,lat1 limits origin blocks and chunks")
    ap.add_argument("--no-segments", action="store_true", help="skip the in-network (leave-one-out) pass")
    a = ap.parse_args()
    t0 = time.time()
    bbox = [float(x) for x in a.bbox.split(",")] if a.bbox else None

    def inside(lon, lat):
        return not bbox or (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3])

    net = ST.Net()
    G = net.G
    n_e = len(G.eu)

    # Origins: every block with residents or children.
    pts = {r["geoid"]: r for r in read(ROOT, "data", "extract", "census-blocks", "2020.json")["records"]}
    kids = {r["geoid"]: r for r in read(ROOT, "data", "extract", "census-dhc", "p12-blocks.json")["records"]}
    epc_rows = read(ACCESS, "epc.json")
    epc_tracts = {r["tract"] for r in epc_rows["records"] if r["epc"]}
    blocks = []
    for gid in sorted(pts):
        p, k = pts[gid], kids.get(gid, {})
        ch = [k.get(band, 0) for band, _l, _ in ST.BANDS]
        if (p["pop"] or 0) == 0 and sum(ch) == 0:
            continue
        if not inside(p["lon"], p["lat"]):
            continue
        b = {"geoid": gid, "pop": p["pop"] or 0, "epc": 1 if gid[:11] in epc_tracts else 0,
             "ends": net.ends(p["lon"], p["lat"])}
        for (band, _l, _), n in zip(ST.BANDS, ch):
            b[band] = n
        blocks.append(b)
    origins = Origins(blocks)
    epc = [b["epc"] for b in blocks]
    print("  %d origin blocks, %d residents, %d children 5-17 (%.0fs)" % (
        len(blocks), sum(b["pop"] for b in blocks), sum(b[x] for b in blocks for x, _l, _ in ST.BANDS), time.time() - t0), flush=True)

    # Destinations.
    loaded = ST.load_schools()
    schools = loaded[0]
    jobs = read(ACCESS, "jobs-2023.json")
    centre_list = [(pts[r["geoid"]], r["jobs"]) for r in jobs["records"] if r["jobs"] >= JOB_CENTRE_MIN and r["geoid"] in pts]
    centres = [p for p, _n in centre_list]
    centre_jobs = sum(r["jobs"] for r in jobs["records"] if r["jobs"] >= JOB_CENTRE_MIN)
    all_jobs = sum(r["jobs"] for r in jobs["records"])
    groc = read(ACCESS, "groceries.json")
    health = read(ACCESS, "health.json")
    libs = read(ROOT, "data", "extract", "libraries", "branches.json")
    # A forward-looking order counts every branch, the Mission Branch included: it is closed for
    # renovation and SFPL gives its reopening as fall 2026 (tools/bike-network/bike-network-history.py).
    open_libs = list(libs["records"])
    pop_w = [b["pop"] for b in blocks]
    measures = []
    for band, lvl, _lab in ST.BANDS:
        measures.append(Measure("school:" + lvl, "school", net, [(s["lon"], s["lat"]) for s in schools if lvl in s["levels"]],
                                [b[band] for b in blocks]))
    measures.append(Measure("jobs", "jobs", net, [(p["lon"], p["lat"]) for p in centres], pop_w))
    measures.append(Measure("grocery", "grocery", net, [(r["lon"], r["lat"]) for r in groc["records"]], pop_w))
    measures.append(Measure("library", "library", net, [(r["lon"], r["lat"]) for r in open_libs], pop_w))
    measures.append(Measure("health", "health", net, [(r["lon"], r["lat"]) for r in health["records"]], pop_w))
    print("  destinations: %d schools, %d job centres (%d of %d jobs), %d groceries, %d libraries, %d health sites (%.0fs)" % (
        len(schools), len(centres), centre_jobs, all_jobs, len(groc["records"]), len(open_libs), len(health["records"]),
        time.time() - t0), flush=True)

    # Networks and candidates.
    today_lines, plan_lines, plan_meta = ST.all_ages_lines()
    line_edges, _weak = ST.edges_of(net, today_lines + plan_lines)
    today_keys = {k for k, _ in today_lines}
    bike_today = [False] * n_e
    for k, _ in today_lines:
        for e in line_edges.get(k, ()):
            bike_today[e] = True
    cl = SB.sfdata.fetch(SB.CENTERLINES, select=SB.CENTERLINE_SELECT, where="active='true'", floor=15000)
    cross = {}
    for r in cl.rows:
        c = SB.cnn_key(r.get("cnn"))
        if c:
            cross[c] = [x.strip().title() for x in (r.get("f_st"), r.get("t_st")) if x and x.strip()]
    groups = ST.group_gaps(plan_lines, plan_meta, today_keys)
    plan_pts = dict(plan_lines)
    chunks = SB.chunk_runs(groups, plan_pts, plan_meta, line_edges, bike_today, cross)
    if bbox:
        chunks = [c for c in chunks if any(inside(*plan_pts[k][0]) for k in c["keys"])]

    # High Injury Network share, per plan block: its midpoint within HIN_SNAP_M of a HIN line, running along it.
    hin = read(ACCESS, "hin-2022.json")
    hidx = ST.LineIndex([(i, r["pts"]) for i, r in enumerate(hin["records"]) if len(r["pts"]) >= 2])

    def on_hin(pts_):
        P = [walknet.xy(*p) for p in pts_]
        a_, b_ = P[0], P[-1]
        mx, my = (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2
        # The midpoint along the line, not of its ends.
        tot = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(P, P[1:]))
        acc = 0.0
        for p, q in zip(P, P[1:]):
            s = math.hypot(q[0] - p[0], q[1] - p[1])
            if acc + s >= tot / 2 and s > 0:
                f = (tot / 2 - acc) / s
                mx, my = p[0] + f * (q[0] - p[0]), p[1] + f * (q[1] - p[1])
                break
            acc += s
        be = ST.bearing(a_[0], a_[1], b_[0], b_[1])
        for i in hidx.near(mx, my, HIN_SNAP_M):
            _k, ax, ay, bx, by = hidx.segs[i]
            if ST.seg_dist(mx, my, ax, ay, bx, by) <= HIN_SNAP_M and ST.angle_ok(be, ST.bearing(ax, ay, bx, by), ST.EDGE_ANGLE_DEG):
                return True
        return False

    hin_ids = {str(r["id"]).split(".")[0] for r in hin["records"]}
    hin_by = collections.Counter()

    def is_hin(k):
        cnn = plan_meta[k]["cnn"]
        if cnn in hin_ids:
            hin_by["cnn"] += 1
            return True
        if on_hin(plan_pts[k]):
            hin_by["geometry"] += 1
            return True
        return False

    for c in chunks:
        c["hin_m"] = sum(c["block_m"][plan_meta[k]["cnn"]] for k in c["keys"] if is_hin(k))
        # Ids from the chunk's lowest and highest CNN, so they do not depend on the run's direction.
        ns = sorted(c["cnns"], key=lambda x: (len(x), x))
        c["sid"] = "%s/%s-%s" % (slug(c["street"]), ns[0], ns[-1])
        c["nodes"] = {x for e in c["edges"] for x in (G.eu[e], G.ev[e])}
    sids = [c["sid"] for c in chunks]
    if len(set(sids)) != len(sids):
        raise SystemExit("chunk ids are not unique")
    by_id = {c["id"]: c for c in chunks}
    print("  %d chunks, %.1f mi, %.1f mi on the High Injury Network (%d blocks by CNN, %d by geometry), %d with no walk edge (%.0fs)" % (
        len(chunks), sum(c["m"] for c in chunks) / MILE, sum(c["hin_m"] for c in chunks) / MILE, hin_by["cnn"], hin_by["geometry"],
        sum(1 for c in chunks if not c["edges"]), time.time() - t0), flush=True)

    # Today.
    model = Model(net, origins, measures, bike_today, a.epc_weight, epc)
    today_under = {m.name: model.under(m) for m in measures}
    totals = {m.name: sum(m.w) for m in measures}
    print("  today within 15 min: %s (%.0fs)" % (type_sum(today_under, measures), time.time() - t0), flush=True)

    # First evaluation = each chunk alone on today's network.
    hin_mult = {c["id"]: 1.0 + a.hin_weight * (c["hin_m"] / c["m"] if c["m"] else 0.0) for c in chunks}
    ev = {}
    for i, c in enumerate(chunks):
        if c["edges"]:
            ev[c["id"]] = model.evaluate(c["edges"])
        if i % 100 == 0:
            print("    alone %d/%d (%.0fs)" % (i, len(chunks), time.time() - t0), flush=True)
    alone = {cid: g for cid, (g, _s, _r) in ev.items()}

    # Greedy.
    avail = {c["id"] for c in chunks if c["edges"]}
    on_net = [False] * len(G.x)
    for e in range(n_e):
        if model.bike[e]:
            on_net[G.eu[e]] = on_net[G.ev[e]] = True
    seq, spent, cum = [], 0.0, collections.Counter()
    while avail:
        best = None
        for cid in sorted(avail):
            g, s, _r = ev[cid]
            if s <= 0:
                continue
            r = s * hin_mult[cid] / (by_id[cid]["m"] / MILE)
            if best is None or r > best[0] + 1e-12:
                best = (r, cid)
        how = "score"
        if best is None:
            how = "fill"
            tail = sorted(avail, key=lambda cid: (not any(on_net[x] for x in by_id[cid]["nodes"]),
                                                   -by_id[cid]["hin_m"] / by_id[cid]["m"], -by_id[cid]["m"], cid))
            best = (0.0, tail[0])
        cid = best[1]
        c = by_id[cid]
        gains, dirty = model.commit(c["edges"])
        if any(gains[m.name] != ev[cid][0][m.name] for m in measures):
            raise SystemExit("stale score for %s: cached %s, committed %s" % (
                c["sid"], ev[cid][0], {m.name: gains[m.name] for m in measures}))
        for x in c["nodes"]:
            on_net[x] = True
        avail.discard(cid)
        spent += c["m"] / MILE
        for m in measures:
            cum[m.name] += gains[m.name]
        epc_g = {m.name: sum(m.w[i] for i in gains["_blocks_" + m.name] if epc[i]) for m in measures}
        seq.append({"chunk": cid, "how": how, "score_per_mi": round(best[0], 2), "miles": c["m"] / MILE, "spent_mi": spent,
                    "gains": {m.name: gains[m.name] for m in measures}, "epc_gains": epc_g, "cum": dict(cum)})
        for d in sorted(avail):
            if not ev[d][2].isdisjoint(dirty) or not by_id[d]["nodes"].isdisjoint(dirty):
                ev[d] = model.evaluate(by_id[d]["edges"])
        if len(seq) % 25 == 0:
            print("    %d picks, %.1f mi, %s (%.0fs)" % (len(seq), spent, type_sum(cum, measures), time.time() - t0), flush=True)
    for cid in sorted(c["id"] for c in chunks if not c["edges"]):
        c = by_id[cid]
        spent += c["m"] / MILE
        # A chunk with walk edges that are all ridden today is already all-ages by edge matching; one with none
        # has no walkable street under it. Either way it changes no one's time.
        how = "already all-ages" if any(line_edges.get(k) for k in c["keys"]) else "no walk edge"
        seq.append({"chunk": cid, "how": how, "score_per_mi": 0.0, "miles": c["m"] / MILE, "spent_mi": spent,
                    "gains": {m.name: 0 for m in measures}, "epc_gains": {m.name: 0 for m in measures}, "cum": dict(cum)})
    rank = {s["chunk"]: i + 1 for i, s in enumerate(seq)}

    # Check: the incremental state equals a fresh computation on the finished network.
    plan_under = {m.name: model.under(m) for m in measures}
    for m in measures:
        fresh = m.full(model.bike)
        n_fresh = sum(m.w[i] for i, b in enumerate(blocks) if origins.time(b, fresh, model.bike) <= CAP + EPS)
        if n_fresh != plan_under[m.name] or plan_under[m.name] - today_under[m.name] != cum[m.name]:
            raise SystemExit("incremental update drifted for %s: %d fresh, %d kept, %d summed" % (
                m.name, n_fresh, plan_under[m.name], today_under[m.name] + cum[m.name]))
    print("  finished plan within 15 min: %s; check passed (%.0fs)" % (type_sum(plan_under, measures), time.time() - t0), flush=True)

    # In the network: what each chunk alone left out of the finished plan loses.
    in_net = {}
    if not a.no_segments:
        bike_plan = model.bike
        P = {}
        for m in measures:
            D, pe, se = m.full(bike_plan, parents=True)
            kids_ = collections.defaultdict(list)
            for v in range(len(D)):
                e = pe[v]
                if e >= 0:
                    u = G.eu[e] if G.ev[e] == v else G.ev[e]
                    kids_[u].append(v)
            P[m.name] = (D, pe, se, kids_)
        for i, c in enumerate(chunks):
            if not c["edges"]:
                continue
            E = set(c["edges"])
            without = list(bike_plan)
            for e in E:
                without[e] = False
            lost = {}
            for m in measures:
                D = P[m.name][0]
                ch = m.remove(E, without, P[m.name])
                n_lost = 0
                for bi in origins.touched(ch, E):
                    if not m.w[bi] or model.T[m.name][bi] > CAP + EPS:
                        continue
                    if origins.time(blocks[bi], D, without, ch) > CAP + EPS:
                        n_lost += m.w[bi]
                lost[m.name] = n_lost
            in_net[c["id"]] = lost
            if i % 100 == 0:
                print("    in network %d/%d (%.0fs)" % (i, len(chunks), time.time() - t0), flush=True)

    # Check: alone and in-network for a spread of chunks against fresh computations.
    checked = sorted(in_net, key=lambda cid: sum(in_net[cid].values()), reverse=True)[:3] + sorted(in_net)[:3] if in_net else []
    for cid in dict.fromkeys(checked):
        E = set(by_id[cid]["edges"])
        with_ = [bike_today[e] or e in E for e in range(n_e)]
        without = [model.bike[e] and e not in E for e in range(n_e)]
        for m in measures:
            Dw, Dwo = m.full(with_), m.full(without)
            a_ = sum(m.w[i] for i, b in enumerate(blocks) if origins.time(b, Dw, with_) <= CAP + EPS) - today_under[m.name]
            l_ = plan_under[m.name] - sum(m.w[i] for i, b in enumerate(blocks) if origins.time(b, Dwo, without) <= CAP + EPS)
            if a_ != alone[cid][m.name] or l_ != in_net[cid][m.name]:
                raise SystemExit("chunk %s, %s: alone %d vs fresh %d, in network %d vs fresh %d" % (
                    by_id[cid]["sid"], m.name, alone[cid][m.name], a_, in_net[cid][m.name], l_))
    print("  alone and in-network checked against fresh searches on %d chunks (%.0fs)" % (len(dict.fromkeys(checked)), time.time() - t0), flush=True)

    # Years.
    years = {}
    for R in RATES:
        rows, k, pos = [], 1, 0
        while pos < len(seq):
            while pos < len(seq) and seq[pos]["spent_mi"] <= k * R + 1e-9:
                pos += 1
            last = seq[pos - 1] if pos else None
            cumk = last["cum"] if last else {}
            epck = collections.Counter()
            for s in seq[:pos]:
                for mn, v in s["epc_gains"].items():
                    epck[mn] += v
            rows.append({"year": k, "built_mi": round(last["spent_mi"], 2) if last else 0.0, "chunks": pos,
                         "hin_mi": round(sum(by_id[s["chunk"]]["hin_m"] for s in seq[:pos]) / MILE, 2),
                         "newly_within_15": type_sum(cumk, measures),
                         "within_15": {t: v + type_sum(today_under, measures)[t] for t, v in type_sum(cumk, measures).items()},
                         "newly_within_15_in_epc": type_sum(epck, measures),
                         "plan_exhausted": pos >= len(seq)})
            k += 1
        years[str(R)] = rows

    # Jobs within reach, summed over residents: today, finished, at each year, and per chunk.
    total_pop = float(sum(b["pop"] for b in blocks))
    cuts = {r["chunks"] for rows in years.values() for r in rows}
    ja_today, ja_plan, ja_cut, ja_alone, ja_lost = job_access(
        net, origins, [((p["lon"], p["lat"]), n) for p, n in centre_list], bike_today, model.bike,
        [by_id[s["chunk"]]["edges"] for s in seq], cuts,
        {c["id"]: c["edges"] for c in chunks if c["edges"]} if not a.no_segments else {}, t0)
    level_specs = [("school:" + lvl, [(sc["lon"], sc["lat"]) for sc in schools if lvl in sc["levels"]], [b[band] for b in blocks])
                   for band, lvl, _lab in ST.BANDS]
    seg_edges = {c["id"]: c["edges"] for c in chunks if c["edges"]} if not a.no_segments else {}
    sm_alone, sm_in = school_minutes(net, origins, level_specs, bike_today, model.bike, seg_edges, t0)
    # Check the minutes on two chunks against fresh searches.
    for cid in sorted(seg_edges, key=lambda c_: -sm_alone[c_][0])[:1] + sorted(seg_edges, key=lambda c_: -sm_in[c_][0])[:1]:
        E = set(by_id[cid]["edges"])
        with_ = [bike_today[e] or e in E for e in range(n_e)]
        without = [model.bike[e] and e not in E for e in range(n_e)]
        fa, fi = [0.0, 0], [0.0, 0]
        for name, pts_, w in level_specs:
            m = Measure(name, "school", net, pts_, w, cap=MINUTES_CAP)
            A, B, C, Dd = m.full(bike_today), m.full(with_), m.full(without), m.full(model.bike)
            for i, b in enumerate(blocks):
                if not w[i]:
                    continue
                for acc, x, y in ((fa, origins.time(b, A, bike_today), origins.time(b, B, with_)),
                                  (fi, origins.time(b, C, without), origins.time(b, Dd, model.bike))):
                    x, y = min(x, MINUTES_CAP), min(y, MINUTES_CAP)
                    if y < x - EPS:
                        acc[0] += w[i] * (x - y) / 60.0
                        if x - y >= SHORTER_S - EPS:
                            acc[1] += w[i]
        if abs(fa[0] - sm_alone[cid][0]) > 0.01 or fa[1] != sm_alone[cid][1] or abs(fi[0] - sm_in[cid][0]) > 0.01 or fi[1] != sm_in[cid][1]:
            raise SystemExit("school minutes for %s: alone %s vs fresh %s, in network %s vs fresh %s" % (
                by_id[cid]["sid"], sm_alone[cid], fa, sm_in[cid], fi))
    print("  school minutes checked against fresh searches (%.0fs)" % (time.time() - t0), flush=True)
    if ja_cut[len(seq)] != ja_plan:
        raise SystemExit("job access along the order (%d) does not end at the finished plan's (%d)" % (ja_cut[len(seq)], ja_plan))

    def avg_jobs(v):
        return round(v / total_pop, 1) if total_pop else None
    for rows in years.values():
        for r in rows:
            r["jobs_within_15_avg_resident"] = avg_jobs(ja_cut[r["chunks"]])
            r["jobs_within_15_avg_resident_gain"] = avg_jobs(ja_cut[r["chunks"]] - ja_today)

    def per_type(d):
        return type_sum(d, measures) if d is not None else None

    order = []
    for i, s in enumerate(seq):
        c = by_id[s["chunk"]]
        order.append({"rank": i + 1, "id": c["sid"], "street": c["street"], "from_to": c["from_to"],
                      "miles": round(s["miles"], 3), "cumulative_miles": round(s["spent_mi"], 3), "picked_by": s["how"],
                      "score_per_mile": s["score_per_mi"], "newly_within_15": per_type(s["gains"]),
                      "newly_within_15_detail": s["gains"], "cumulative": per_type(s["cum"])})

    by_type_today = type_sum(today_under, measures)
    by_type_plan = type_sum(plan_under, measures)
    by_type_total = type_sum(totals, measures)
    val = {}
    summ = os.path.join(ROOT, "out", "school-travel", "summary.json")
    if os.path.exists(summ) and not bbox:
        sm = read(summ)
        val = {"school_travel_time_children": sm["children"]["5-17"],
               "school_travel_time_over_15": {"today": sm["over_target"]["today"]["5-17"], "plan": sm["over_target"]["plan"]["5-17"]},
               "this_model_children": by_type_total["school"],
               "this_model_over_15": {"today": by_type_total["school"] - by_type_today["school"],
                                      "plan": by_type_total["school"] - by_type_plan["school"]},
               "note": "school-travel-time.py caps a route at 1.25 x the shortest walk; this model does not, so on the same "
                       "network it can only count as many or more children within 15 minutes, as it does today. The plan "
                       "figures differ more because the capped model also rides the plan chunks this model finds already "
                       "all-ages by edge matching (%d chunks, %.1f mi) and so leaves out of its order." % (
                           sum(1 for x in seq if x["how"] == "already all-ages"),
                           sum(x["miles"] for x in seq if x["how"] == "already all-ages"))}
        print("  validation: over 15 today %d (capped model %d), plan %d (capped model %d)" % (
            val["this_model_over_15"]["today"], val["school_travel_time_over_15"]["today"],
            val["this_model_over_15"]["plan"], val["school_travel_time_over_15"]["plan"]), flush=True)

    suffix = "-w" if (a.epc_weight or a.hin_weight) else ""
    if bbox:
        suffix += "-dev"
    meta = {
        "model": {"target_minutes": ST.TARGET_MIN, "walk_mph": ST.WALK_MPH, "ride_mph": ST.RIDE_MPH, "detour_cap": None,
                  "miles": "centerline miles: each plan block's traced line length, one count per block whatever its directions",
                  "chunk_target_mi": SB.CHUNK_MI, "rates_mi_per_year": RATES,
                  "objective": "people newly within 15 minutes, summed over the five destination types with equal weights, per mile",
                  "epc_weight": a.epc_weight, "hin_weight": a.hin_weight, "job_centre_min_jobs": JOB_CENTRE_MIN,
                  "bbox": bbox},
        "definitions": dict(TYPE_LABEL, **{
            "alone": "people newly within 15 minutes when this chunk alone is added to today's all-ages network",
            "in_network": "people who would no longer be within 15 minutes if this chunk alone were left out of the finished plan",
            "rank": "position in the greedy build order (1 = built first)",
            "hin_mi": "centerline miles of the chunk whose plan blocks run along SFMTA's 2022 High Injury Network (midpoint within %g feet, bearing within %g degrees)" % (
                round(HIN_SNAP_M / FOOT), ST.EDGE_ANGLE_DEG),
            "epc": "block in an MTC Equity Priority Community tract, Plan Bay Area 2050 Plus (ACS 2018-2022)",
            "jobs_caveat": "LODES places a worker at the employer's reporting address, so City Hall's block (23,678 jobs) and UCSF Parnassus (two blocks, 34,575) carry payrolls that work across the city, and job centres over-weight Civic Center and Parnassus",
            "health_caveat": "DataSF's list (rows last updated 2021-08-14) mixes community and free clinics, Community Health Network sites (including methadone, senior-care and psychiatric programmes) and general acute care hospitals",
            "library_note": "every SFPL branch counts, the Mission Branch included: it is closed for renovation and due to reopen in fall 2026",
            "jobs_within_15_avg_resident": "jobs at job centres within 15 minutes of home, averaged over all residents (sum over blocks of residents x the jobs at every job centre within 15 minutes, divided by residents)",
            "child_minutes_saved": "over every child 5-17 whose trip to the nearest school of their level gets shorter, the sum of minutes before minus minutes after, whatever side of 15 minutes either falls; alone = this chunk added to today's network, in_network = this chunk added last to the finished plan. Trips are timed to 30 minutes; a trip over 30 counts as 30, so savings from such trips are lower bounds",
            "children_2min_shorter": "children 5-17 whose trip to school is at least 2 minutes shorter with this chunk (alone: added to today's network; in_network: added last to the finished plan), trips timed to 30 minutes as above",
            "jobs_reach_alone": "the change in jobs_within_15_avg_resident when this chunk alone is added to today's network",
            "jobs_reach_in_network": "the fall in jobs_within_15_avg_resident if this chunk alone were left out of the finished plan"}),
        "population": by_type_total,
        "within_15_today": by_type_today,
        "within_15_plan": by_type_plan,
        "headroom_today": {t: by_type_total[t] - by_type_today[t] for t in TYPES},
        "job_centres": {"blocks": len(centres), "jobs": centre_jobs, "all_jobs": all_jobs},
        "jobs_within_15_avg_resident": {"today": avg_jobs(ja_today), "plan": avg_jobs(ja_plan)},
        "sources": {
            "network_and_plan": "lib/school-travel-time.py (imported): OpenStreetMap walk network, site/data/bike-history, site/data/north-star",
            "residents": "https://data.sf.gov/d/p2fw-hsrv (2020 PL pop20 by block)",
            "children": "data/extract/census-dhc/p12-blocks.json (2020 DHC P12)",
            "jobs": jobs["meta"]["url"],
            "groceries": "OpenStreetMap via Overpass, read %s" % groc["fetched_on"],
            "health": health["meta"]["dataset"] + " (rows updated %s)" % health["meta"]["rows_updated"],
            "libraries": libs["meta"]["dataset"],
            "hin": hin["meta"]["url"],
            "epc": epc_rows["meta"]["item"],
        },
    }
    os.makedirs(OUT, exist_ok=True)
    stable.write_json(os.path.join(OUT, "build-order%s.json" % suffix),
                      dict(meta, validation=val, years=years, order=order), indent=1)
    segs = []
    for c in sorted(chunks, key=lambda c: c["sid"]):
        segs.append({"id": c["sid"], "street": c["street"], "from_to": c["from_to"], "cnns": c["cnns"],
                     "miles": round(c["m"] / MILE, 3), "hin_mi": round(c["hin_m"] / MILE, 3), "rank": rank.get(c["id"]),
                     "facilities": c["facilities"],
                     "alone": per_type(alone.get(c["id"], {})) if c["edges"] else None,
                     "in_network": per_type(in_net[c["id"]]) if c["id"] in in_net else None,
                     "child_minutes_saved_alone": round(sm_alone[c["id"]][0]) if c["id"] in seg_edges else None,
                     "children_2min_shorter_alone": sm_alone[c["id"]][1] if c["id"] in seg_edges else None,
                     "child_minutes_saved_in_network": round(sm_in[c["id"]][0]) if c["id"] in seg_edges else None,
                     "children_2min_shorter_in_network": sm_in[c["id"]][1] if c["id"] in seg_edges else None,
                     "jobs_reach_alone": avg_jobs(ja_alone[c["id"]]) if c["edges"] and not a.no_segments else None,
                     "jobs_reach_in_network": avg_jobs(ja_lost[c["id"]]) if c["edges"] and not a.no_segments else None})
    by_cnn = {cnn: c["sid"] for c in chunks for cnn in c["cnns"]}
    stable.write_json(os.path.join(OUT, "segments%s.json" % suffix),
                      dict(meta, segments=segs, by_cnn=dict(sorted(by_cnn.items()))), indent=1)
    for R in RATES:
        for r in years[str(R)]:
            print("  %3d mi/yr year %d: %6.1f mi  %s%s" % (R, r["year"], r["built_mi"], r["newly_within_15"],
                                                         "  (plan exhausted)" if r["plan_exhausted"] else ""))
    print("  wrote out/build-order/build-order%s.json and segments%s.json (%.0fs)" % (suffix, suffix, time.time() - t0))


if __name__ == "__main__":
    main()
