#!/usr/bin/env python3
"""Price each school's School Connector by street type and count TK-8 students over half a mile out, for School Trips.

Writes site/data/school-sim/rules.json, which site/src/pages/transportation-school-trips.mjs inlines and
site/src/school-trips-model.mjs reads. Two figures the School Trips tool needs that the simulation doesn't write,
both by the rules Bryan set for the SSC comment on 2026-10-11:

CONNECTOR COST. Each School Connector block is priced at its street type's central per-mile figure in
data/school-budget/unit-costs.json, the same rates as the ranked all-ages segments (tools/school-trips/school-segments.py):
a residential, living, unclassified or service street as calmed ($0.25M a mile), any other street as separated
($1.5M a mile). A connector edge (site/data/school-sim/overlays.json, [lon, lat] to 5 dp) takes the highway tag of
the OpenStreetMap way it lies on, matched at 4 dp in the walk and drive caches (data/osm-cache/sf-walk.json,
sf-drive.json, written by tools/travel/osm-walk-network.py). A sidewalk, path or unmatched edge takes the street type of
the nearest drivable way within 25 m of its midpoint. Beyond 25 m it's off-street, priced halfway between calmed
and a new shared-use path ($0.72M a mile), since we can't tell which it needs. A connector shorter than a quarter
mile is priced as a quarter mile, so a short link isn't nearly free. "ss" is the cost with a School Street on, when
the connector's feet on the School Street block are already safe and aren't built (overlays' connectorOnSchoolStreetFt,
taken off each piece in proportion). "full" is the cost without one.

FREE MUNI. muniFar is the TK-8 students living over half a mile from school in a straight line, from each school's
home blocks (site/data/school-sim/<cds>.json homes), its door (data/extract/schools/cde-sf.json) and its share of
TK-8 students (data/school-case/enrolment-sf.json), scaled up to city.json's K-5 plus 6-8 students since the home
blocks hold only part of them. Free Muni for caregivers raises Muni's share among these students.

Run after tools/school-trips/school-sim.py, and after the osm-walk-network and osm-drive steps that write the caches. Writes only when a figure changes (lib/stable.py) and checks its output
before writing: every connector school priced, each full cost positive and no less than its cost with a School Street, the total between $2M and $15M (about $3.8M at the 17 schools
one block from the network that need one, 2026-10-12), muniFar between
10,000 and 30,000 students. A failing check exits 1 and leaves the previous file in place."""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import glob
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, paths.LIB)
import stable  # noqa: E402
import school_points  # noqa: E402

ROOT = paths.ROOT
SIM = os.path.join(ROOT, "site", "data", "school-sim")
OUT = os.path.join(SIM, "rules.json")
FT = 0.3048
MIN_MI = 0.25
NEAR_M = 25.0
CALM = {"residential", "living_street", "unclassified", "service"}
WALK = {"footway", "path", "pedestrian", "steps", "cycleway", "track"}


def key(lon, lat):
    return (round(lon, 4), round(lat, 4))


def seg_ft(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2)) * 111320
    return math.hypot((a[0] - b[0]) * k, (a[1] - b[1]) * 110540) / FT


def street_index():
    """Edge and node highway tags from both OSM caches, and a 50 m grid of drivable way pieces."""
    ll, ways, drive = {}, [], []
    for fn in ("sf-walk.json", "sf-drive.json"):
        d = json.load(open(os.path.join(ROOT, "data", "osm-cache", fn)))
        for e in d["elements"]:
            if e["type"] == "node":
                ll[e["id"]] = (e["lon"], e["lat"])
        for e in d["elements"]:
            if e["type"] == "way":
                ways.append(e)
                if fn == "sf-drive.json":
                    drive.append(e)
    # Walk and drive edges share keys at 4 dp (about 10 m), so a sidewalk that close to its roadway takes the
    # roadway's tag. The 25 m nearest-drive fallback would give it the same.
    edge_hw, node_hw = {}, defaultdict(set)
    for w in ways:
        hw = (w.get("tags") or {}).get("highway", "?")
        nd = [n for n in w["nodes"] if n in ll]
        for n in nd:
            node_hw[key(*ll[n])].add(hw)
        for a, b in zip(w["nodes"][:-1], w["nodes"][1:]):
            if a in ll and b in ll:
                edge_hw[frozenset((key(*ll[a]), key(*ll[b])))] = hw
    kx, ky = math.cos(math.radians(37.76)) * 111320, 110540
    grid = defaultdict(list)
    for w in drive:
        hw = (w.get("tags") or {}).get("highway", "?")
        for a, b in zip(w["nodes"][:-1], w["nodes"][1:]):
            if a in ll and b in ll:
                p, q = ll[a], ll[b]
                for gx in range(int(min(p[0], q[0]) * kx // 50), int(max(p[0], q[0]) * kx // 50) + 1):
                    for gy in range(int(min(p[1], q[1]) * ky // 50), int(max(p[1], q[1]) * ky // 50) + 1):
                        grid[(gx, gy)].append((p, q, hw))

    def nearest(pt):
        x, y = pt[0] * kx, pt[1] * ky
        best = (NEAR_M, None)
        for gx in range(int(x // 50) - 1, int(x // 50) + 2):
            for gy in range(int(y // 50) - 1, int(y // 50) + 2):
                for p, q, hw in grid.get((gx, gy), ()):
                    ax, ay, bx, by = p[0] * kx, p[1] * ky, q[0] * kx, q[1] * ky
                    dx, dy = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1e-9)))
                    dist = math.hypot(ax + t * dx - x, ay + t * dy - y)
                    if dist < best[0]:
                        best = (dist, hw)
        return best[1]
    return edge_hw, node_hw, nearest


def connector_costs():
    rates = {k: v["central"] for k, v in json.load(open(os.path.join(ROOT, "data", "school-budget", "unit-costs.json")))["types"].items()}
    off_rate = (rates["calmed"] + rates["path"]) / 2
    edge_hw, node_hw, nearest = street_index()
    ov = json.load(open(os.path.join(SIM, "overlays.json")))
    out, miles = {}, defaultdict(float)
    for s in sorted(ov["schools"], key=lambda x: x["cds"]):
        if not s["connector"]:
            continue
        ft = defaultdict(float)
        for a, b in s["connector"]:
            hw = edge_hw.get(frozenset((key(*a), key(*b))))
            if hw is None:
                both = node_hw.get(key(*a), set()) & node_hw.get(key(*b), set())
                hw = next(iter(both)) if len(both) == 1 else "?"
            if hw in WALK or hw == "?":
                hw = nearest(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) or "offstreet"
            ft["calm" if hw in CALM else "off" if hw == "offstreet" or hw in WALK else "sep"] += seg_ft(a, b)
        tot = sum(ft.values())
        keep = max(0.0, 1 - s.get("connectorOnSchoolStreetFt", 0) / s["connectorFt"]) if s["connectorFt"] else 1.0

        def price(share):
            mi = tot * share / 5280
            c = (ft["calm"] * rates["calmed"] + ft["sep"] * rates["separated"] + ft["off"] * off_rate) * share / 5280
            return round((c / mi * MIN_MI if 0 < mi < MIN_MI else c) * 1e6) if mi > 0 else 0
        for k, v in ft.items():
            miles[k] += v * keep / 5280
        out[s["cds"]] = {"full": price(1.0), "ss": price(keep)}
    return out, {k: round(v, 2) for k, v in sorted(miles.items())}, {"calmed": rates["calmed"], "separated": rates["separated"], "offStreet": off_rate}


def muni_far():
    city = json.load(open(os.path.join(SIM, "city.json")))
    en = json.load(open(os.path.join(ROOT, "data", "school-case", "enrolment-sf.json")))["schools"]
    pts = {r["cds"]: r for r in school_points.records() if r.get("lat")}
    tot = far = 0.0
    for f in sorted(glob.glob(os.path.join(SIM, "3*.json"))):
        s = json.load(open(f))
        p = pts.get(s["cds"])
        if not p:
            continue
        g = en.get(s["cds"], {}).get("grades", {})
        k8 = sum(v for k, v in g.items() if k not in ("09", "10", "11", "12")) / (sum(g.values()) or 1)
        h = s["homes"]
        for lo, la, n in zip(h["lon"], h["lat"], h["students"]):
            d = math.hypot((lo - p["lon"]) * math.cos(math.radians((la + p["lat"]) / 2)) * 69.17, (la - p["lat"]) * 69.0)
            tot += n * k8
            if d > 0.5:
                far += n * k8
    return far / tot * (city["bandN"][0] + city["bandN"][1])


def main():
    conn, miles, rates = connector_costs()
    far = muni_far()
    ix = json.load(open(os.path.join(SIM, "index.json")))
    want = {s["cds"] for s in ix["schools"] if s.get("connector") and not s.get("connectorOnNetwork")}
    total_ss = sum(c["ss"] for c in conn.values())
    bad = []
    if set(conn) - want:
        bad.append("connectors priced at schools that don't get one: " + ", ".join(sorted(set(conn) - want)))
    if want - set(conn):
        bad.append("connector schools with no price: " + ", ".join(sorted(want - set(conn))))
    if any(c["full"] <= 0 or c["ss"] < 0 or c["full"] < c["ss"] for c in conn.values()):
        bad.append("a connector priced at zero, or cheaper without a School Street than with one")
    if not 2e6 <= total_ss <= 15e6:
        bad.append("connector total $%.1fM outside $2M to $15M" % (total_ss / 1e6))
    if not 10000 <= far <= 30000:
        bad.append("muniFar %.0f outside 10,000 to 30,000" % far)
    if bad:
        print("school-sim-rules: checks failed, rules.json left as it was:\n  " + "\n  ".join(bad), file=sys.stderr)
        sys.exit(1)
    out = {
        "note": "Written by tools/school-trips/school-sim-rules.py. connector: each School Connector school's cost in dollars, "
                "full and with a School Street on (ss), priced by street type. connectorMiles: the miles beyond School "
                "Street blocks by type. muniFar: TK-8 students living over half a mile from school.",
        "connector": conn, "connectorMiles": miles, "connectorRates": rates, "muniFar": round(far, 1),
    }
    stable.write_json(OUT, out, indent=1, sort_keys=True)
    print("school-sim-rules: %d connectors, $%.2fM with School Streets on, $%.2fM without; %s mi; muniFar %.0f"
          % (len(conn), total_ss / 1e6, sum(c["full"] for c in conn.values()) / 1e6, miles, far))


if __name__ == "__main__":
    main()
