#!/usr/bin/env python3
"""Injury crashes on the 2022 High Injury Network before and after SFMTA's "completed" upgrades, against the rest of SF.

    python3 tools/street-safety/hin-2022-before-after.py            # cached HIN layer and crash table
    python3 tools/street-safety/hin-2022-before-after.py --refresh  # re-read both

What SFMTA says it did. Its March 2026 post "Building Safer Streets for
Everyone" says the Streets team "completed safety upgrades at every
intersection along the High Injury Network", 925 intersections (high
visibility crosswalks, leading pedestrian intervals, signal lenses, limit
lines, turn hardening), with no dates per site. sf.gov's Street Safety
Initiative page says daylighting is done on "the entire 2022 High-Injury
Network" as of May 2026. Neither gives a list or dates, so the treated set is
the whole 2022 HIN and the work period is taken as the year to August 2025.

Places
  HIN segment   cnn_sgmt_pkey in SFMTA's 2022 HIN layer (ArcGIS hin2022,
                cached under scratch/runs/hin-2022/).
  HIN node      an f_node or t_node of a HIN segment: an intersection along
                the HIN.
  Crash         one row per case_id_pkey of DataSF ubvf-ztfx (every row is an
                injury crash). "Intersection <= 20ft" crashes are placed at
                cnn_intrsctn_fkey; midblock and rear-end-within-150ft crashes
                at cnn_sgmt_fkey. A crash is on the HIN if its place is a HIN
                node or segment.
  Comparison 1  every other crash in the city.
  Variant       "approaches": a midblock or rear-end crash whose
                cnn_intrsctn_fkey is a HIN node also counts as HIN.
  Comparison 2  crashes at places on main streets (centerline classcode 2, 3
                or 4, DataSF 3psu-pn9h) that are not on the HIN; a node is a
                main-street node if any segment meeting there is.

Windows (September to August years, the crash table ending 2026-08-31)
  Before   Sep 2022 to Aug 2024, two years, after the 2022 HIN was published
           and before the 2025 push.
  Build    Sep 2024 to Aug 2025, left out.
  After    Sep 2025 to Aug 2026, one year; rates are per year.
  Placebo  Sep 2022 to Aug 2023 against Sep 2023 to Aug 2024: the same test
           on a step with no claimed work, to show how much the ratio moves
           on its own.

The work SFMTA describes is at intersections, so intersection crashes are
the lead row. Midblock crashes rose citywide from about 330 to 460 a
half-year between 2021 and 2026 while intersection crashes stayed flat;
the cause is not known, and it moves the all-crash rows.

Change = (HIN after / HIN before) / (comparison after / comparison before),
with exposure in years. 95% ranges from a bootstrap over places (HIN and
comparison places resampled independently, 2,000 draws, fixed seed) and a
Poisson range for reference.

Checks stop the run: crash rows >= 60,000,
dates 2005 to 2026-08 or later, HIN layer >= 2,000 segments and 100 to 200
corrected miles, >= 98% of HIN segments found in the street centerline, and
>= 98% of crashes placeable.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import json
import math
import os
import pathlib
import random
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sfdata import fetch  # noqa: E402
from lib.stable import write_text  # noqa: E402

ROOT = pathlib.Path(paths.ROOT)
OUT = ROOT / "out" / "hin-2022-before-after"
CACHE = ROOT / "scratch" / "runs" / "hin-2022" / "hin2022-attributes.json"
HIN = "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/hin2022/FeatureServer/0"
SEED = 20261118
N_BOOT = 2000
MAIN = {"2", "3", "4"}
KSI = {"Fatal", "Injury (Severe)"}
PED = {"Vehicle-Pedestrian"}
WIN = {  # (start, end) as 'YYYY-MM' inclusive
    "before": ("2022-09", "2024-08"),
    "build": ("2024-09", "2025-08"),
    "after": ("2025-09", "2026-08"),
    "placebo_before": ("2022-09", "2023-08"),
    "placebo_after": ("2023-09", "2024-08"),
}


def check(ok, msg, log):
    log.append(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        print("\n".join(log), file=sys.stderr)
        raise SystemExit("quality check failed: " + msg)


def read_hin(refresh):
    if CACHE.exists() and not refresh:
        return json.loads(CACHE.read_text())
    rows, off = [], 0
    fields = "cnn_sgmt_pkey,f_node_cnn_intrsctn_fkey,t_node_cnn_intrsctn_fkey,class_code,corrected_length_miles,full_street_name"
    while True:
        q = {"where": "1=1", "outFields": fields, "returnGeometry": "false", "f": "json",
             "resultOffset": off, "resultRecordCount": 2000, "orderByFields": "objectid"}
        req = urllib.request.Request(HIN + "/query?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": "sf-works-research/1.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=120).read())
        if "error" in d:
            raise SystemExit(d["error"])
        rows += [f["attributes"] for f in d["features"]]
        if not d.get("exceededTransferLimit"):
            break
        off += len(d["features"])
    import datetime as dt
    blob = {"fetched_on": dt.date.today().isoformat(), "url": HIN, "rows": rows}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(blob, sort_keys=True))
    return blob


def k(x):
    """Centerline and node keys arrive as '35015000', '35015000.0' or ints."""
    return str(int(float(x)))


def in_win(ym, w):
    return WIN[w][0] <= ym <= WIN[w][1]


def years(w):
    a, b = WIN[w]
    return ((int(b[:4]) * 12 + int(b[5:])) - (int(a[:4]) * 12 + int(a[5:])) + 1) / 12


def ratio(t_before, t_after, c_before, c_after, wb, wa):
    rt = (t_after / years(wa)) / (t_before / years(wb))
    rc = (c_after / years(wa)) / (c_before / years(wb))
    return rt, rc, rt / rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    log = []

    hin = read_hin(args.refresh)
    segs = {k(r["cnn_sgmt_pkey"]) for r in hin["rows"] if r.get("cnn_sgmt_pkey")}
    nodes = {k(r[f]) for r in hin["rows"] for f in ("f_node_cnn_intrsctn_fkey", "t_node_cnn_intrsctn_fkey") if r.get(f)}
    miles = sum(r.get("corrected_length_miles") or 0 for r in hin["rows"])
    check(len(hin["rows"]) >= 2000, "HIN 2022 layer rows >= 2,000 (%d)" % len(hin["rows"]), log)
    check(100 <= miles <= 200, "HIN 2022 corrected miles 100-200 (%.1f)" % miles, log)
    log.append("INFO HIN 2022: %d segments, %d nodes, %.1f corrected miles, fetched %s"
               % (len(segs), len(nodes), miles, hin["fetched_on"]))

    cl = fetch("3psu-pn9h", select="cnn,classcode,f_node_cnn,t_node_cnn", floor=15000)
    cls = {k(r["cnn"]): r.get("classcode") for r in cl.rows}
    check(sum(s in cls for s in segs) / len(segs) >= 0.98,
          "HIN segments in street centerline: %.1f%%" % (100 * sum(s in cls for s in segs) / len(segs)), log)
    main_segs = {c for c, cc in cls.items() if cc in MAIN}
    main_nodes = {k(r[f]) for r in cl.rows if r.get("classcode") in MAIN for f in ("f_node_cnn", "t_node_cnn") if r.get(f)}

    cr = fetch("ubvf-ztfx", select="unique_id,case_id_pkey,cnn_sgmt_fkey,cnn_intrsctn_fkey,collision_datetime,"
               "collision_severity,intersection,dph_col_grp_description", floor=60000, refresh=args.refresh)
    check(len(cr.rows) >= 60000, "crash rows >= 60,000 (%d)" % len(cr.rows), log)
    dmin = min(r["collision_datetime"] for r in cr.rows)[:10]
    dmax = max(r["collision_datetime"] for r in cr.rows)[:10]
    check(dmin[:4] == "2005" and dmax[:7] >= WIN["after"][1], "crash dates %s to %s cover the after window" % (dmin, dmax), log)

    seen, crashes, unplaced = set(), [], 0
    for r in sorted(cr.rows, key=lambda r: r["unique_id"]):
        if r["case_id_pkey"] in seen:
            continue
        seen.add(r["case_id_pkey"])
        at_node = (r.get("intersection") or "").startswith("Intersection <=")
        key = r.get("cnn_intrsctn_fkey") if at_node else r.get("cnn_sgmt_fkey")
        if not key:
            unplaced += 1
            continue
        key = k(key)
        kind = "node" if at_node else "seg"
        on_hin = key in (nodes if at_node else segs)
        ikey = r.get("cnn_intrsctn_fkey")
        # Variant: a midblock or rear-end crash whose nearest intersection is
        # a HIN node is on that node's approach, so on the HIN.
        on_hin_wide = on_hin or (not at_node and ikey and k(ikey) in nodes)
        on_main = key in (main_nodes if at_node else main_segs)
        crashes.append({"place": kind + ":" + key, "ym": r["collision_datetime"][:7], "hin": on_hin, "hin_wide": bool(on_hin_wide),
                        "main_off_hin": on_main and not on_hin, "at_node": at_node,
                        "ksi": r.get("collision_severity") in KSI,
                        "ped": r.get("dph_col_grp_description") in PED})
    check(unplaced / len(seen) <= 0.02, "placeable crashes: %.2f%% unplaced" % (100 * unplaced / len(seen)), log)
    log.append("INFO crashes: %d cases, %d placed, %d unplaced" % (len(seen), len(crashes), unplaced))

    rng = random.Random(SEED)

    def test(filt, comp, wb, wa, seed_off=0, hk="hin"):
        sel = [dict(c, hin=c[hk]) for c in crashes if filt(c)]
        T = collections.defaultdict(lambda: [0, 0])
        C = collections.defaultdict(lambda: [0, 0])
        for c in sel:
            i = 0 if in_win(c["ym"], wb) else 1 if in_win(c["ym"], wa) else None
            if i is None:
                continue
            if c["hin"]:
                T[c["place"]][i] += 1
            elif comp(c):
                C[c["place"]][i] += 1
        tb, ta = sum(v[0] for v in T.values()), sum(v[1] for v in T.values())
        cb, ca = sum(v[0] for v in C.values()), sum(v[1] for v in C.values())
        rt, rc, rr = ratio(tb, ta, cb, ca, wb, wa)
        se = math.sqrt(1 / tb + 1 / ta + 1 / cb + 1 / ca)
        tv, cv = list(T.values()), list(C.values())
        r2 = random.Random(SEED + seed_off)
        draws = []
        for _ in range(N_BOOT):
            ts = [tv[r2.randrange(len(tv))] for _ in tv]
            cs = [cv[r2.randrange(len(cv))] for _ in cv]
            a, b = sum(x[0] for x in ts), sum(x[1] for x in ts)
            c_, d = sum(x[0] for x in cs), sum(x[1] for x in cs)
            if a and b and c_ and d:
                draws.append(ratio(a, b, c_, d, wb, wa)[2])
        draws.sort()
        return {"hin_before": tb, "hin_after": ta, "comp_before": cb, "comp_after": ca,
                "hin_per_year_before": round(tb / years(wb), 1), "hin_per_year_after": round(ta / years(wa), 1),
                "hin_change": round(rt - 1, 3), "comp_change": round(rc - 1, 3),
                "net_change": round(rr - 1, 3),
                "net_boot95": [round(draws[int(0.025 * len(draws))] - 1, 3), round(draws[int(0.975 * len(draws)) - 1] - 1, 3)],
                "net_poisson95": [round(math.exp(math.log(rr) - 1.96 * se) - 1, 3), round(math.exp(math.log(rr) + 1.96 * se) - 1, 3)],
                "hin_places_with_crash": len(T), "comp_places_with_crash": len(C)}

    every = lambda c: True  # noqa: E731
    rest = lambda c: True  # noqa: E731
    mainoff = lambda c: c["main_off_hin"]  # noqa: E731
    R = {}
    rows = [("all", every), ("intersection", lambda c: c["at_node"]), ("pedestrian", lambda c: c["ped"]),
            ("fatal_or_severe", lambda c: c["ksi"])]
    for i, (name, f) in enumerate(rows):
        R[name + "_vs_rest_of_city"] = test(f, rest, "before", "after", i)
        R[name + "_vs_main_streets_off_hin"] = test(f, mainoff, "before", "after", 10 + i)
    R["placebo_all_vs_rest_of_city"] = test(every, rest, "placebo_before", "placebo_after", 20)
    R["placebo_all_vs_main_streets_off_hin"] = test(every, mainoff, "placebo_before", "placebo_after", 21)
    R["all_vs_rest_of_city_approaches_on_hin"] = test(every, lambda c: not c["hin_wide"], "before", "after", 30, "hin_wide")
    R["intersection_and_approaches_vs_rest"] = test(lambda c: c["at_node"] or c["hin_wide"],
                                                   lambda c: c["at_node"] and not c["hin_wide"], "before", "after", 31, "hin_wide")
    # Window sensitivity, intersection crashes against the rest of the city.
    sens = {"after_is_build_year": ("before", "build"),
            "before_is_2023_24_only": ("placebo_after", "after")}
    for name, (wb, wa) in sens.items():
        R["intersection_vs_rest_of_city_" + name] = test(lambda c: c["at_node"], rest, wb, wa, 40)

    # Yearly series, Sep-Aug years, for the chart.
    # Year-to-year noise: the same ratio between each pair of consecutive
    # Sep-Aug years with no claimed work, intersection crashes only.
    def yr(c, y):
        return "%d-09" % y <= c["ym"] <= "%d-08" % (y + 1)
    steps = []
    for y in range(2015, 2023):
        h0 = sum(1 for c in crashes if c["at_node"] and c["hin"] and yr(c, y))
        h1 = sum(1 for c in crashes if c["at_node"] and c["hin"] and yr(c, y + 1))
        o0 = sum(1 for c in crashes if c["at_node"] and not c["hin"] and yr(c, y))
        o1 = sum(1 for c in crashes if c["at_node"] and not c["hin"] and yr(c, y + 1))
        steps.append(math.log((h1 / h0) / (o1 / o0)))
    mu = sum(steps) / len(steps)
    noise = {"years": "2015-16 to 2023-24 consecutive steps", "steps": [round(math.exp(x) - 1, 3) for x in steps],
             "sd_of_log_ratio": round(math.sqrt(sum((x - mu) ** 2 for x in steps) / (len(steps) - 1)), 3)}

    series = []
    for y in range(2015, 2026):
        a, b = "%d-09" % y, "%d-08" % (y + 1)
        h = sum(1 for c in crashes if a <= c["ym"] <= b and c["hin"])
        m = sum(1 for c in crashes if a <= c["ym"] <= b and c["main_off_hin"])
        o = sum(1 for c in crashes if a <= c["ym"] <= b and not c["hin"])
        hi = sum(1 for c in crashes if a <= c["ym"] <= b and c["hin"] and c["at_node"])
        oi = sum(1 for c in crashes if a <= c["ym"] <= b and not c["hin"] and c["at_node"])
        series.append({"year": "%d-%02d" % (y, (y + 1) % 100), "hin": h, "main_off_hin": m, "rest_of_city": o,
                       "hin_share": round(h / (h + o), 3), "hin_intersection": hi, "rest_intersection": oi,
                       "hin_intersection_share": round(hi / (hi + oi), 3)})

    res = {"data": {"hin2022_fetched_on": hin["fetched_on"], "hin2022_segments": len(segs), "hin2022_nodes": len(nodes),
                    "hin2022_corrected_miles": round(miles, 1),
                    "ubvf-ztfx": {"rows": len(cr.rows), "fetched_on": str(cr.fetched_on), "first": dmin, "last": dmax}},
           "windows": WIN, "results": R, "year_to_year_noise_intersections": noise, "yearly": series, "quality_log": log}
    OUT.mkdir(parents=True, exist_ok=True)
    write_text(OUT / "results.json", json.dumps(res, indent=1, sort_keys=True) + "\n")
    print("\n".join(log))
    print(json.dumps({"results": R, "yearly": series}, indent=1))


if __name__ == "__main__":
    main()
