#!/usr/bin/env python3
"""The Daily Trips map's data for the site: every populated census block's outline, residents, Muni service and whole minutes to each destination type by mode, slimmed from out/full-map/ into site/data/daily-trips.json.

    python3 tools/travel/daily-trips-site.py           # write site/data/daily-trips.json, then run the checks
    python3 tools/travel/daily-trips-site.py --check   # the checks on the file on disk

out/full-map/blocks.json is 1.7 MB with no outlines, and
the site build reads nothing outside site/ (site/scripts/check-public.mjs), so
this step joins it to the 2020 block outlines and keeps only what the page
draws.

INPUTS, all built by other steps; this one fetches nothing.
  out/full-map/blocks.json            per-block table (tools/travel/full-map.py)
  out/full-map/summary.json           its published totals, which this file must reproduce
  out/full-map/transit-tthird.json    the faster T Third run (tools/travel/full-map-transit.py, TTHIRD=1)
  data/extract/census-blocks/outlines-2020.json  block outlines (pipeline/sources/census-block-outlines.py)

WHAT IT KEEPS, per block in blocks.json's order:
  pop      2020 residents.
  muni     how often one route comes at a stop within a quarter mile on foot,
           7 to 9 AM: 5 (every 5 minutes or better), 10 (every 10), 0 (less
           often, or no stop that close). One route, as Bryan ruled on
           2026-10-23 (docs/decisions/access-map.md).
  stop     walking feet to the nearest stop with any service, and to the
           nearest where one route comes every 5 minutes, 7 to 9 AM. Whole
           feet as full-map.py's feet() writes them: a stop past a quarter
           mile is never 1,320 or less, so the feet agree with muni.
  min      whole minutes per type and mode. Walk, bike and car are rounded up,
           so one shown at 15 is at most 15.0 minutes; the page's "within 15
           minutes" counts then match summary.json's, which compare the
           0.1-minute values. A Muni time that came from R5 is R5's whole
           minute, rounded down (an R5 15 is 15.0 to 15.99), as summary.json
           counts it; up() leaves an integer as it is.
  tthird   the transit minutes on the faster T Third feed, by full-map.py's
           own muni() rule (Muni or walking, whichever is faster).
  Outlines are rounded to 1e-5 degrees (the source's precision); at TOL 0
  simplify() drops only points exactly in line with their neighbours. Each ring delta-encoded as site/src/maplibre.mjs's
  encodeRuns does, so window.sfMap.decode reads them.

CHECKS (run after every write; a failure exits 1 and the orchestrator keeps
the last good file): every block of blocks.json is here once with an outline;
the residents within 15 and 30 minutes, per type and mode, equal summary.json's;
the T Third's equal summary.json's scenarios.tthird.within; the residents with
Muni every 5 and every 10 minutes equal summary.json's morning counts.

INCREMENTAL. A build step with no source of its own: the orchestrator runs it
when an input changes, and an unchanged input writes the same bytes
(lib/stable.py), so a rerun changes no tracked file.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
from lib.quality import Each, Join, Table, read_json, run  # noqa: E402

BLOCKS_REL = "out/full-map/blocks.json"
SUMMARY_REL = "out/full-map/summary.json"
TTHIRD_REL = "out/full-map/transit-tthird.json"
OUTLINES_REL = "data/extract/census-blocks/outlines-2020.json"
OUT_REL = "site/data/daily-trips.json"
STEP = 1e5
TOL = 0  # Douglas-Peucker tolerance, in 1e-5 degree steps: 0, since thinning each ring alone opens slivers along
# edges two blocks share, and it saved only 6 KB gzipped
QUARTER_MILE_FT = 1320
TARGETS = (15, 30)


def _full_map():
    m = paths.load("full-map.py")
    return m


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def up(v):
    """Whole minutes, rounded up: 15.0 stays 15, 15.1 shows as 16. None stays None."""
    return None if v is None else int(math.ceil(round(float(v), 1) - 1e-9))


def every5_ok(muni, ft):
    """True when a block's Muni category and its every-5 stop's feet agree: 5 exactly when the stop is within a quarter mile."""
    return (muni == 5) == (ft is not None and ft <= QUARTER_MILE_FT)


def simplify(run, tol):
    """Douglas-Peucker on integer points, keeping the ends."""
    if len(run) < 4:
        return run
    keep = [False] * len(run)
    keep[0] = keep[-1] = True
    stack = [(0, len(run) - 1)]
    while stack:
        i, j = stack.pop()
        (ax, ay), (bx, by) = run[i], run[j]
        L = math.hypot(bx - ax, by - ay)
        far, at = -1.0, -1
        for m in range(i + 1, j):
            px, py = run[m]
            off = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / L if L else math.hypot(px - ax, py - ay)
            if off > far:
                far, at = off, m
        if far > tol:
            keep[at] = True
            stack += [(i, at), (at, j)]
    out = [p for p, k in zip(run, keep) if k]
    return out if len(out) >= 4 else run


def signed_area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2.0


def inside(pt, ring):
    x, y = pt
    hit = False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i], ring[i + 1]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def polygons(rings):
    """TIGERweb's rings (outer clockwise, holes anticlockwise) as [[outer, hole, ...], ...] in integer steps."""
    q = [[(int(round(x * STEP)), int(round(y * STEP))) for x, y in r] for r in rings]
    outers = [r for r in q if signed_area(r) <= 0]
    holes = [r for r in q if signed_area(r) > 0]
    if not outers:  # a block drawn the other way round: every ring is its own polygon
        outers, holes = holes, []
    polys = [[o] for o in outers]
    for h in holes:
        home = next((p for p in polys if inside(h[0], p[0])), polys[0])
        home.append(h)
    return polys


def build():
    fm = _full_map()
    blocks = read(BLOCKS_REL)
    summary = read(SUMMARY_REL)
    outlines = {r["geoid"]: r["rings"] for r in read(OUTLINES_REL)["records"]}
    types, modes = blocks["minutes"]["types"], blocks["minutes"]["modes"]
    rows = blocks["blocks"]

    transit_src = blocks["sources"]["transit"] if isinstance(blocks["sources"]["transit"], dict) else {}
    tthird = None
    if os.path.exists(os.path.join(ROOT, TTHIRD_REL)):
        tr = read(TTHIRD_REL)
        problem = fm.transit_mismatch(tr, [r[0] for r in rows], types, fm.dest_sha(ROOT), fm.file_sha(ROOT, fm.ORIGINS_REL))
        if problem:
            raise SystemExit("%s does not belong to this build: %s" % (TTHIRD_REL, problem))
        wi = modes.index("walk")
        got = {g: (mins, wo) for (g, mins), wo in zip(tr["blocks"], tr["walk_only"]["minutes"])}
        ti = {t: i for i, t in enumerate(tr["types"])}
        tthird = {t: [] for t in types}
        for r in rows:
            mins, wo = got[r[0]]
            for t in types:
                tthird[t].append(up(fm.muni(mins[ti[t]], r[4][t][wi], wo[ti[t]])))

    n, d, shape = [], [], []
    cx = cy = 0
    for r in rows:
        polys = polygons(outlines[r[0]])
        shape.append([len(p) for p in polys])
        for p in polys:
            for ring in p:
                kept = simplify(ring, TOL)
                n.append(len(kept))
                for x, y in kept:
                    d += [x - cx, y - cy]
                    cx, cy = x, y

    def muni_code(hw):
        h = hw["am"][0]
        return 0 if h is None else 5 if h <= 5 else 10 if h <= 10 else 0

    mi = modes.index
    out = {
        "note": "The Daily Trips map's data, slimmed from out/full-map/ by scripts/daily-trips-site.py. Per populated "
                "2020 census block, in blocks.json's order: residents; muni, how often one route comes at a stop "
                "within a quarter mile on foot, 7 to 9 AM (5, 10 or 0 for less often or none); stop, walking feet "
                "to the nearest stop and to the nearest with one route every 5 minutes then; min, whole minutes "
                "rounded up per type and mode; tthird, the transit minutes on the faster T Third feed. Outlines as "
                "site/src/maplibre.mjs's encodeRuns, with shape giving each block's rings per polygon.",
        "types": types,
        "modes": modes,
        "residents": summary["residents"],
        "asof": {
            "census": "2020",
            "service_date": blocks["sources"]["stops"]["feed"]["serviceDate"],
            "schedule": (transit_src.get("inputs") or {}).get("schedule"),
            "departure": (transit_src.get("parameters") or {}).get("departure"),
        },
        "tthird_assumptions": ((summary.get("scenarios") or {}).get("tthird") or {}).get("assumptions"),
        "geoid": [r[0] for r in rows],
        "pop": [r[1] for r in rows],
        "muni": [muni_code(r[3]) for r in rows],
        "stop": [[r[2][0], r[2][2]] for r in rows],
        "min": {t: {m: [up(r[4][t][mi(m)]) for r in rows] for m in modes} for t in types},
        "tthird": tthird,
        "outline": {"n": n, "d": d, "shape": shape},
    }
    stable.write_json(os.path.join(ROOT, OUT_REL), out, separators=(",", ":"))
    return out


# -- checks ------------------------------------------------------------------------

def checks(root=ROOT):
    def site(r):
        return read_json(r, OUT_REL)

    def rows(r):
        d = site(r)
        if d is None:
            return None
        return [{"geoid": g, "pop": p, "shape": s} for g, p, s in zip(d["geoid"], d["pop"], d["outline"]["shape"])]

    def outlines(r):
        d = site(r)
        if d is None:
            return None
        sh, n = d["outline"]["shape"], d["outline"]["n"]
        bad = []
        if sum(sum(s) for s in sh) != len(n):
            bad.append("shape lists %d rings, n %d" % (sum(sum(s) for s in sh), len(n)))
        if 2 * sum(n) != len(d["outline"]["d"]):
            bad.append("n lists %d points, d holds %d" % (sum(n), len(d["outline"]["d"]) // 2))
        bad += ["%s has no outline" % g for g, s in zip(d["geoid"], sh) if not s]
        return [{"problem": p} for p in bad] or [{"problem": None}]

    def totals(r):
        """Every within-N count the page computes from this file, against summary.json's."""
        d, s = site(r), read_json(r, SUMMARY_REL)
        if d is None or s is None:
            return None
        pop = d["pop"]

        def within(vals, t):
            return sum(p for p, v in zip(pop, vals) if v is not None and v <= t)

        out = []
        for ty in d["types"]:
            for m in d["modes"]:
                for t in TARGETS:
                    want = s["within"][ty][m]["%d" % t]["residents"]
                    out.append({"what": "%s %s %d" % (ty, m, t), "got": within(d["min"][ty][m], t), "want": want})
                    if m == "transit" and d["tthird"] is not None and (s.get("scenarios") or {}).get("tthird"):
                        want = s["scenarios"]["tthird"]["within"][ty]["%d" % t]["residents"]
                        out.append({"what": "tthird %s %d" % (ty, t), "got": within(d["tthird"][ty], t), "want": want})
        for h in (5, 10):
            got = sum(p for p, c in zip(pop, d["muni"]) if c and c <= h)
            out.append({"what": "muni every %d am" % h, "got": got, "want": s["muni_within_quarter_mile"]["am"]["%d" % h]["residents"]})
        out.append({"what": "residents", "got": sum(pop), "want": s["residents"]})
        return out

    def every5(r):
        """A block counted as Muni every 5 minutes has its every-5 stop within a quarter mile, and the reverse."""
        d = site(r)
        if d is None:
            return None
        return [{"geoid": g, "c": c, "ft": st[1]} for g, c, st in zip(d["geoid"], d["muni"], d["stop"])]

    return [
        Table("daily-trips-site", rows, floor=5000, max_drop=0.02, key="geoid", required=["geoid", "pop"]),
        Join("daily-trips-site~full-map", left=lambda r: None if read_json(r, BLOCKS_REL) is None
             else [b[0] for b in read_json(r, BLOCKS_REL)["blocks"]],
             right=lambda r: None if rows(r) is None else [x["geoid"] for x in rows(r)]),
        Each("daily-trips-site/outlines", outlines, lambda x: x["problem"],
             "every block has an outline, and the ring and point counts add up"),
        Each("daily-trips-site/totals", totals,
             lambda x: None if x["got"] == x["want"] else "%s: %s here, %s in summary.json" % (x["what"], x["got"], x["want"]),
             "every residents-within count the page shows equals summary.json's"),
        Each("daily-trips-site/every-5", every5,
             lambda x: None if every5_ok(x["c"], x["ft"])
             else "%s: muni %s, every-5 stop %s ft" % (x["geoid"], x["c"], x["ft"]),
             "Muni every 5 minutes means the every-5 stop is within a quarter mile on foot"),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        out = build()
        print("  %d blocks, %d rings, %.0f KB" % (len(out["geoid"]), len(out["outline"]["n"]),
                                                 os.path.getsize(os.path.join(ROOT, OUT_REL)) / 1024))
    results = run(checks(), root=ROOT)
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  checks: %d passed, %d failed" % (len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
