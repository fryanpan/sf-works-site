#!/usr/bin/env python3
"""Checks the all-ages network the full access map rides against a published Level of Traffic Stress method: Mekuria, Furth and Nixon's LTS criteria, read from OpenStreetMap's tags on every walk-network edge.

    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map-lts.py          # out/full-map/lts.json
    ~/.venvs/sf-works-geo/bin/python tools/travel/full-map-lts.py --check

The map's low-stress bike minutes ride only School Trips'
all-ages network (Class I paths, Class IV separated lanes, Slow Streets:
lib/school-travel-time.py all_ages_lines(brp_rule=True)) and read it as
LTS 1, which the method defines as "Strong separation from all except low
speed, low volume traffic. Simple crossings. Suitable for children."
(peterfurth.sites.northeastern.edu/level-of-traffic-stress, read 2026-10-23).
This script rates every edge of the walk network by the method's segment
tables and reports how the two agree, by length.

THE TABLES (LTS Criteria Tables, peterfurth.sites.northeastern.edu/files/2014/05/LTS-Tables1.pdf, read 2026-10-23):
  Table 1  stand-alone paths and segregated paths (cycle tracks): LTS 1.
  Table 2  bike lane beside parking: LTS > 1 with 2+ through lanes per
           direction (LTS 3), bike plus parking lane under 15 ft (14 to 14.5
           ft: 2; 13.5 or less: 3), speed over 25 mph (30: 2, 35: 3, 40+: 4).
           "If speed limit < 25 mph, or land use is residential with little
           parking turnover, then any width is acceptable for LTS 2."
  Table 4  mixed traffic: up to 25 mph, 2 to 3 lanes LTS 1 or 2, 4 to 5
           lanes LTS 3, 6+ LTS 4; 30 mph, 2 to 3 lanes LTS 2 or 3, 4+ LTS 4;
           35+ mph LTS 4. "Use lower value for streets without marked
           centerlines and with ADT < 3000; use higher value otherwise."
Weakest link: the worst dimension sets the edge's LTS. Crossings (Table 6)
and right-turn lanes (Table 5) are not rated; OSM does not carry them.

READING OSM. Speed is the way's maxspeed in mph. Where it is missing, the
median maxspeed of the walk network's ways of the same class that do carry one
(local_defaults), when at least LOCAL_MIN_TAGGED of them do, for every class
but the quiet ones (residential, unclassified, service), which keep 25; otherwise the
PeopleForBikes BNA's national default for the class (primary and secondary 40
mph, tertiary 30, residential and unclassified 25: cityratings.peopleforbikes.org/
about/methodology, Table 2, read 2026-10-23). The BNA's 40 mph contradicts the
city's own tags: of the tagged secondary ways 527 of 724 are 20 or 25 mph, and
of the tagged tertiary ways 297 of 350 (Fable review, 2026-10-23). The class
medians are written to lts.json's method.default_mph. Only a quiet class can be
rated LTS 1 by speed, and those keep 25, so the defaults move no edge into or
out of LTS 1 and the furth1 bike run is unaffected. Lanes is the way's lanes tag;
where it is missing, two for a two-way street and one for a one-way, except
primary and secondary, four and two [inference — mine]. Bike lane and parking
widths are not in OSM here, so a painted lane takes the BNA's minimums (5 ft
lane beside 8 ft parking: 13 ft, so LTS 3 by Table 2) unless Table 2's
footnote applies. No ADT or centerline data: a residential, living street or
unclassified way is taken to have no centerline and under 3,000 vehicles a
day, so it takes Table 4's lower value, and every other class the higher
[inference — mine]; that is the method's largest unknown here. Footways
without bicycle=yes or designated, steps, elevators and corridors are not
ridden and are left out (n/a).

Writes out/full-map/lts.json: the walk network's length by LTS, the all-ages
network's length by LTS, and the LTS 1 length the all-ages network leaves out,
by OSM class, in miles. all_ages_rated_share_lts1 is a floor, not an estimate:
School Trips' network attaches a walk edge to a Class I or IV line within 15 m (EDGE_SNAP_M),
and that edge is often the roadway beside the facility, tagged cycleway=lane
(Masonic Avenue's raised cycle track, the Embarcadero) or 35 mph (Sloat), so
the tables rate the street a rider has been separated from.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import importlib.util
import json
import os
import re
import sys

# The orchestrator's interpreter, which has no numpy, imports this file only for checks(); the
# analysis virtualenv runs the build (pipeline/venv-step.py).
try:
    import numpy
except ImportError:
    numpy = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
from lib.quality import Each, Table, read_json, run  # noqa: E402

OUT_REL = "out/full-map/lts.json"
MI = 1609.344
STREETS = {"residential", "living_street", "unclassified", "tertiary", "secondary", "primary", "trunk", "service",
           "tertiary_link", "secondary_link", "primary_link", "trunk_link", "busway"}
QUIET = {"residential", "living_street", "unclassified", "service"}
DEFAULT_MPH = {"primary": 40, "primary_link": 40, "trunk": 40, "trunk_link": 40, "secondary": 40, "secondary_link": 40,
               "tertiary": 30, "tertiary_link": 30, "residential": 25, "unclassified": 25, "service": 25,
               "living_street": 15, "busway": 25}
PATHS = {"cycleway"}
MAYBE_PATHS = {"path", "footway", "pedestrian", "track", "bridleway"}


LOCAL_MIN_TAGGED = 30


def local_defaults(way_tags):
    """{class: mph} for a way with no maxspeed: the median tagged maxspeed of that class's ways, where at least
    LOCAL_MIN_TAGGED carry one, else DEFAULT_MPH (the BNA's national default)."""
    seen = collections.defaultdict(list)
    for t in way_tags:
        v = mph(t.get("maxspeed"))
        if v:
            seen[t.get("highway")].append(v)
    out = dict(DEFAULT_MPH)
    for hw, vs in seen.items():
        # The quiet classes keep the BNA's 25 mph: Table 4 can rate them LTS 1, so a local median over 25 would move
        # edges out of LTS 1 (and the furth1 bike network) on a tagging change, and one under it changes nothing.
        if hw in out and hw not in QUIET and len(vs) >= LOCAL_MIN_TAGGED:
            vs = sorted(vs)
            out[hw] = vs[len(vs) // 2]
    return dict(sorted(out.items()))


def mph(tag):
    if not tag:
        return None
    m = re.match(r"\s*(\d+)\s*(mph)?", tag)
    if not m:
        return None
    v = int(m.group(1))
    return v if m.group(2) else round(v / 1.609344)


def lanes_of(t):
    try:
        return int(str(t.get("lanes", "")).split(";")[0])
    except ValueError:
        return None


def lts(t, defaults=DEFAULT_MPH):
    """(LTS 1-4, or None where nobody rides) for one OSM way's tags; defaults is the class's mph where maxspeed is missing."""
    hw = t.get("highway")
    bike = t.get("bicycle")
    if hw in PATHS or (hw in MAYBE_PATHS and bike in ("yes", "designated")):
        return 1
    if hw not in STREETS or bike == "no" or hw == "busway":
        return None
    # A cycle track, on the way or mapped beside it as its own way ("separate"), is a segregated path (Table 1).
    if any(k.startswith("cycleway") and k.count(":") <= 1 and v in ("track", "separate") for k, v in t.items()):
        return 1
    if hw == "living_street":
        return 1
    speed = mph(t.get("maxspeed")) or defaults.get(hw, 25)
    oneway = t.get("oneway") in ("yes", "1", "-1")
    lanes = lanes_of(t)
    if lanes is None:
        lanes = (2 if hw in ("primary", "secondary", "trunk") else 1) * (1 if oneway else 2)
    per_dir = lanes if oneway else max(1, lanes // 2)
    has_lane = any(k.startswith("cycleway") and k.count(":") <= 1 and v == "lane" for k, v in t.items())
    if has_lane:
        # Table 2, bike lane beside parking (SF's usual arrangement); weakest link over its dimensions.
        width = 3 if not (speed < 25 or hw in QUIET) else 2
        s = 1 if speed <= 25 else 2 if speed <= 30 else 3 if speed <= 35 else 4
        return max(3 if per_dir >= 2 else 1, width, s)
    # Table 4, mixed traffic.
    low = hw in QUIET
    if speed <= 25:
        return (1 if low else 2) if lanes <= 3 else 3 if lanes <= 5 else 4
    if speed <= 30:
        return (2 if low else 3) if lanes <= 3 else 4
    return 4


def way_tags_per_edge(G, path):
    """Each walk edge's OSM tags, rebuilding walknet.Graph's edge order from the same file; checked edge by edge."""
    blob = json.load(open(path))
    coords = {e["id"]: True for e in blob["elements"] if e["type"] == "node"}
    idx, n = {}, 0
    tags = []
    for w in (e for e in blob["elements"] if e["type"] == "way"):
        prev = None
        for nd in w.get("nodes", ()):
            if nd not in coords:
                continue
            if nd not in idx:
                idx[nd] = n
                n += 1
            i = idx[nd]
            if prev is not None and prev != i:
                tags.append(w.get("tags", {}))
            prev = i
    if len(tags) != len(G.eu) or n != len(G.x):
        raise SystemExit("walk network order differs from %s: %d edges and %d nodes against %d and %d" % (
            path, len(tags), n, len(G.eu), len(G.x)))
    hw = [t.get("highway") for t in tags]
    if hw != list(G.ehw):
        raise SystemExit("edge highway tags differ from the walk network's; the order was not rebuilt")
    return tags


def edge_lts(G):
    import walknet
    tags = way_tags_per_edge(G, walknet.CACHE)
    # One dict per way, shared by its edges: dedupe by identity so a long way is not counted once per edge.
    defaults = local_defaults(list({id(t): t for t in tags}.values()))
    edge_lts.defaults = defaults
    return numpy.array([lts(t, defaults) or 0 for t in tags], dtype=numpy.int8), tags


def top_streets(L, mask, tags, n=12):
    """The streets with the most miles under mask, by OSM name: {name: miles}."""
    c = collections.Counter()
    for e in numpy.flatnonzero(mask).tolist():
        c[tags[e].get("name") or "(unnamed %s)" % tags[e].get("highway")] += L[e] / MI
    return {k: round(v, 2) for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]}


def build():
    A = paths.load("access-time.py")
    M = A.M
    net = M.Net(cache=True)
    G = net.G
    L = numpy.asarray(G.elen)
    rate, tags = edge_lts(G)
    A.RULE["brp"] = True
    ours = A.networks(net)["today"].astype(bool)
    A.RULE["brp"] = False
    explorer = A.networks(net)["today"].astype(bool)

    def by_lts(mask):
        return {("n/a" if k == 0 else "LTS %d" % k): round(float(L[mask & (rate == k)].sum()) / MI, 1) for k in range(5)}

    hw = numpy.array([t.get("highway") or "" for t in tags])
    missing = (rate == 1) & ~ours
    left_out = collections.Counter()
    for c in sorted(set(hw[missing].tolist())):
        left_out[c] = round(float(L[missing & (hw == c)].sum()) / MI, 1)
    out = {
        "note": "Miles of walk-network edge by Mekuria, Furth and Nixon's LTS, read from OSM tags (see the "
                "script's docstring for the defaults). all_ages: School Trips' protected-only network, which "
                "the full access map rides as LTS 1; explorer: the bike explorer's network, painted lanes "
                "above the BCI line included. A two-way street's edge is counted once.",
        "method": {"criteria": "https://peterfurth.sites.northeastern.edu/files/2014/05/LTS-Tables1.pdf",
                   "defaults": "missing maxspeed: the class's median tagged maxspeed on the walk network (at least %d "
                               "tagged ways; residential, unclassified and service keep 25), else the BNA's national default, "
                               "https://cityratings.peopleforbikes.org/about/methodology" % LOCAL_MIN_TAGGED,
                   "default_mph": edge_lts.defaults,
                   "osm_base": G.osm_base},
        "walk_network": by_lts(numpy.ones(len(L), dtype=bool)),
        "all_ages": by_lts(ours),
        "explorer": by_lts(explorer),
        "all_ages_miles": round(float(L[ours].sum()) / MI, 1),
        "lts1_not_all_ages_by_class": dict(sorted(left_out.items(), key=lambda kv: -kv[1])),
        "lts1_miles": round(float(L[rate == 1].sum()) / MI, 1),
        "lts1_share_in_all_ages": round(100.0 * float(L[(rate == 1) & ours].sum()) / max(1.0, float(L[rate == 1].sum())), 1),
        "all_ages_share_lts1": round(100.0 * float(L[ours & (rate == 1)].sum()) / max(1.0, float(L[ours].sum())), 1),
        # Of the all-ages edges the tables can rate (streets and bike paths, not sidewalks), the share rated LTS 1.
        # A floor: an edge attached to a Class I or IV line is often the roadway beside it, tagged cycleway=lane
        # (Masonic's raised track, the Embarcadero), so the tables rate the street, not the separated facility.
        "all_ages_rated_share_lts1": round(100.0 * float(L[ours & (rate == 1)].sum())
                                           / max(1.0, float(L[ours & (rate > 0)].sum())), 1),
        "all_ages_lts3plus_by_street": top_streets(L, ours & (rate >= 3), tags),
    }
    stable.write_json(os.path.join(ROOT, OUT_REL), out, indent=1)
    return out


def checks(root=ROOT):
    def rows(r):
        d = read_json(r, OUT_REL)
        return None if d is None else [{"net": k, "miles": sum(d[k].values())} for k in ("walk_network", "all_ages", "explorer")]

    return [
        Table("full-map-lts", rows, floor=3, max_drop=0.0, key="net", required=["net", "miles"]),
        # The walk network is about 2,000+ miles of edge; the all-ages network is a small part of it.
        Each("full-map-lts/miles", rows, lambda x: None if (x["net"] == "walk_network" and x["miles"] > 1000)
             or (x["net"] != "walk_network" and 20 < x["miles"] < 1000) else "%s: %s miles" % (x["net"], x["miles"]),
             "the walk network over 1,000 miles; each bike network between 20 and 1,000"),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        out = build()
        print(json.dumps({k: out[k] for k in ("walk_network", "all_ages", "explorer", "lts1_miles",
                                               "lts1_share_in_all_ages", "all_ages_share_lts1", "all_ages_rated_share_lts1", "all_ages_lts3plus_by_street",
                                               "lts1_not_all_ages_by_class")}, indent=1))
    results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
