#!/usr/bin/env python3
"""The 2017, 2022 and 2024 High Injury Networks compared: miles kept, dropped and added, who was hurt next on each, and how much of the next three years each version caught, for Whitepaper Part 1.2.

    python3 tools/street-safety/hin-versions.py            # cached layers and crash rows
    python3 tools/street-safety/hin-versions.py --refresh  # re-read the 2017 ArcGIS layer and every DataSF query

Writes out/hin-versions/summary.json (every figure below), out/hin-versions/chart.mdx (the PlotChart for the doc) and
data/extract/access/hin-2017.json (the 2017 lines, in hin-2022.json's shape, for tools/street-safety/hin-people-map.py). One-off
analysis behind a notes page; no page reads it on a schedule, so the incremental-updater rule does not apply yet.

THE THREE VERSIONS (research/sources/sf-high-injury-network.md has each one's method and published total).
  2017  SFDPH ArcGIS layer vz_hin_2017_single_line (135 corridors, `length` in miles). Despite the name it draws some
        divided streets on both sides: 167.4 drawn miles against a `length` total of 128.9 (Geary 7.36 against 3.99).
        A corridor's miles are spread evenly over its drawn feet, so a part-divided corridor's divided stretch gets
        double weight per foot; the totals are unaffected and the 2017-2022 overlap still matches the published one. Drawn from 2013-2015 severe and fatal injuries, >= 7 per mile, plus 2015-network sections
        with a 2013-2016 fatality and manual additions for 2016 and 2017 fatalities. No block ids.
  2022  DataSF 8vtn-qytr, one row per centerline block (cnn_sgmt_pkey) repeated up to 5 times; deduplicated on the
        block id. corrected_length_miles halves a dual carriageway. Drawn from 2017-2021, >= 10 per mile.
  2024  DataSF enwt-3u8m, the same shape. Drawn from 2020-2024, >= 10 per mile, with "stubs" over 500 ft past the last
        KSI removed.
  Miles are the agency's corrected_length_miles; they reproduce the published 121.5 and 132.9 miles. The 2017 layer's
  own `length` reproduces its published 128.9. In 2024, 471 rows carry a dual-carriageway id in cnn_sgmt_pkey rather
  than a centerline block id, so versions are matched by geometry, not by id.

MATCHING VERSIONS. Each version's lines are cut into PIECE_FT pieces, each carrying its share of its record's corrected
miles. A piece is kept when its midpoint is within MATCH_FT of a line of the same street name (suffix dropped) in the
other version and projects onto that line no more than END_FT past its ends, so a section that stops is not stretched
by the buffer. MATCH_FT is wide because the 2024 layer draws some divided streets once, down the middle (its
dual-carriageway ids), while 2022 draws each side and 2017 does either. Kept miles are measured on both versions and averaged. Checks: 2017-2022 overlap against the 2022
methodology's 76.7 miles, and 2022-2024 kept, added and dropped against DPH's 93, 39.9 and 28.6.

PEOPLE. DataSF nwes-mmgh, one row per injured person, victim_degree_of_injury 'Severe Injury' or 'Fatal Injury',
deduplicated on (case_id_pkey, victim_id), placed by tb_longitude/tb_latitude. Police reports only: the HIN itself
also uses hospital records the public data lacks, so our in-window shares are not the agency's.
On a network: within ON_FT (60 ft) of its lines, the rule of tools/street-safety/hin-injury-kinds.py (which gives the 2022 HIN 620
of 922 placed people for 2022-2024). Shares are of placed people.

OUT OF SAMPLE. Each version against the three calendar years after the last crash it used:
  2017 -> 2018-2020 (its manual review used 2016 and 2017 fatalities, so 2016-2017 are inside).
  2022 -> 2022-2024.
  2024 -> 2025-01 to the newest row (partial). Its 2020-2024 share is reported too, labelled in-sample.
Share of streets is the agency's own published figure for each version (12.8%, 12.2%, 13%).

CHURN. For 2017->2022 and 2022->2024, every piece of either version is kept (on both), dropped (first only) or added
(second only). A person goes to the nearest piece within ON_FT whose street name is the report's primary_rd, the
HIN's own assignment rule (only injuries on the section's primary street count). Near a piece but with another primary
road: "cross_street", reported and left out of every rate. Within ON_FT of nothing: "elsewhere", whose miles are
CITY_MILES less the three groups. CITY_MILES comes from a rounded 12.2%, and the other versions imply 1,007 to 1,022,
so the elsewhere rate is good to about 0.1, not two decimals. The period after a version ends at the newest crash of
any severity in nwes-mmgh, the data's own end. People per mile
per year are counted in the period after the second version's window: 2022-2024 for 2017->2022, and 2025 to the newest
row for 2022->2024. A dropped street that stays as dangerous as a kept one is a street the update stopped watching.

Checks stop the run: layer row counts, miles within 1% of the published figures, 2022-2024 churn within 5% of DPH's,
the 620-of-922 rerun, unique person ids, at least 98% of people placed, and every year in range present.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib.stable import write_json, write_text  # noqa: E402

OUT = os.path.join(ROOT, "out", "hin-versions")
ACCESS = os.path.join(ROOT, "data", "extract", "access")
H2017_URL = "https://services.arcgis.com/Zs2aNLFN00jrS4gG/arcgis/rest/services/vz_hin_2017_single_line/FeatureServer/0"
ON_FT, MATCH_FT, END_FT, PIECE_FT, CELL = 60, 110, 10, 25, 500
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
KSI = ("Severe Injury", "Fatal Injury")
PUBLISHED = {
    "2017": {"miles": 128.9, "street_pct": 12.8, "ksi_pct": 74.6, "ksi": "1,102 of 1,477", "window": "2013-2015",
             "threshold": ">= 7 per mile", "source": "SFDPH, Vision Zero High Injury Network: 2017 Update, July 2017, Table 1 and 2"},
    "2022": {"miles": 121.5, "street_pct": 12.2, "ksi_pct": 68.2, "ksi": "1,792 of 2,627", "window": "2017-2021",
             "threshold": ">= 10 per mile", "source": "SFDPH, 2022 Vision Zero Network Update Methodology, Table 1 and 2"},
    "2024": {"miles": 132.9, "street_pct": 13, "ksi_pct": 74, "ksi": None, "window": "2020-2024",
             "threshold": ">= 10 per mile", "source": "SFDPH Health Commission deck 2026-08-17 (93 + 39.9 mi), SFMTA blog (13%, 74%)"},
}
# City street miles, the 2022 methodology's denominator: 121.5 miles is 12.2% (Table 1), so about 996 miles of street
# without freeways, the Presidio, Fort Mason and streets closed to vehicles. Used for the "elsewhere" group's miles.
CITY_MILES = 121.5 / 0.122
# Health Commission deck, 2026-08-17, slide 11: 2022 -> 2024 change in miles.
PUBLISHED_CHURN_2024 = {"kept": 93.0, "added": 39.9, "dropped": 28.6}
PUBLISHED_OVERLAP_2017_2022 = 76.7   # 2022 methodology, Table 1
OOS = {"2017": ("2018-01-01", "2020-12-31"), "2022": ("2022-01-01", "2024-12-31"), "2024": ("2025-01-01", None)}
IN_WINDOW = {"2017": ("2013-01-01", "2015-12-31"), "2022": ("2017-01-01", "2021-12-31"), "2024": ("2020-01-01", "2024-12-31")}


def xy(lon, lat):
    return ((lon + 122.44) * FT_LON, (lat - 37.76) * FT_LAT)


SUFFIX = {"ST", "AVE", "AV", "BLVD", "BL", "WAY", "DR", "RD", "TER", "PL", "LN", "CT", "HWY", "EXPY", "CIR", "ALY", "PLZ"}


def name_key(s):
    s = (s or "").upper().replace("'", "").replace(".", "").strip()
    s = re.sub(r"\b0+(\d)", r"\1", s).replace("BAY SHORE", "BAYSHORE")
    return tuple(w for w in s.split() if w not in SUFFIX)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def length_ft(P):
    return sum(math.dist(a, b) for a, b in zip(P, P[1:]))


class Grid(object):
    """Polylines in feet, bucketed so a query only scans nearby segments."""

    def __init__(self, items):
        self.items, self.g = items, collections.defaultdict(list)
        for k, (P, _) in enumerate(items):
            for a, b in zip(P, P[1:]):
                for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.g[(cx, cy)].append((a, b, k))

    def near(self, p, reach):
        """{item index: distance} for items within reach (reach <= CELL)."""
        cx, cy, out = int(p[0] // CELL), int(p[1] // CELL), {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a, b, k in self.g.get((cx + dx, cy + dy), ()):
                    d = seg_dist(p, a, b)
                    if d <= reach and d < out.get(k, 1e18):
                        out[k] = d
        return out

    def nearest(self, p, reach):
        got = self.near(p, reach)
        return min(got.items(), key=lambda kv: (kv[1], kv[0]))[0] if got else None


def geom_lines(g):
    g = g if isinstance(g, dict) else json.loads(g)
    return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]


def fetch_2017(refresh):
    path = os.path.join(ACCESS, "hin-2017.json")
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "OBJECTID,full_stree,length", "outSR": 4326,
                                "returnGeometry": "true", "f": "geojson"})
    with urllib.request.urlopen(H2017_URL + "/query?" + q, timeout=120) as r:
        gj = json.load(r)
    recs = []
    for f in sorted(gj["features"], key=lambda f: f["properties"]["OBJECTID"]):
        p = f["properties"]
        for ln in geom_lines(f["geometry"]):
            recs.append({"id": p["OBJECTID"], "street": p["full_stree"], "miles": round(p["length"], 6),
                         "pts": [[round(x, 6), round(y, 6)] for x, y in ln]})
    assert len({r["id"] for r in recs}) == 135, "2017 layer: expected 135 corridors"
    out = {"fetched_on": dt.date.today().isoformat(),
           "meta": {"source": "SFDPH 2017 Vision Zero High Injury Network (ArcGIS layer vz_hin_2017_single_line, owner "
                              "dph.opendata_sfgov, created 2017-07-20)", "url": H2017_URL},
           "records": recs}
    write_json(path, out)
    return out


def datasf_hin(fxf, refresh):
    r = sfdata.fetch(fxf, floor=1000, refresh=refresh)
    by = {}
    for x in r.rows:
        by.setdefault(x["cnn_sgmt_pkey"], x)   # rows repeat a block up to 5 times with the same geometry
    blocks = {}
    for cnn, x in by.items():
        blocks[int(float(cnn))] = {"miles": float(x["corrected_length_miles"]), "street": x.get("full_street_name") or x.get("street_name") or "",
                                   "lines": geom_lines(x["geom"])}
    return blocks, r


def share(k, n):
    return {"n": k, "of": n, "pct": round(100.0 * k / n, 1) if n else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    # ---- the three networks
    H17 = fetch_2017(a.refresh)
    b22, r22 = datasf_hin("8vtn-qytr", a.refresh)
    b24, r24 = datasf_hin("enwt-3u8m", a.refresh)
    assert len(b22) == 2388 and len(b24) == 1917, (len(b22), len(b24))
    miles17 = sum({r["id"]: r["miles"] for r in H17["records"]}.values())
    miles = {"2017": miles17, "2022": sum(b["miles"] for b in b22.values()), "2024": sum(b["miles"] for b in b24.values())}
    for v, m in miles.items():
        assert abs(m - PUBLISHED[v]["miles"]) / PUBLISHED[v]["miles"] < 0.01, (v, m)

    # ---- every version cut into PIECE_FT pieces, each carrying its share of the record's corrected miles
    def pieces(recs):
        """recs: (corrected miles, street name key, [polyline in lon/lat, ...]) -> [(a, b, miles, name)] in feet."""
        out = []
        for m, nm, lines in recs:
            Ps = [[xy(*p) for p in ln] for ln in lines if len(ln) > 1]
            tot = sum(length_ft(P) for P in Ps)
            for P in Ps:
                for a0, b0 in zip(P, P[1:]):
                    d = math.dist(a0, b0)
                    k = max(1, int(math.ceil(d / PIECE_FT)))
                    for i in range(k):
                        a1 = (a0[0] + (b0[0] - a0[0]) * i / k, a0[1] + (b0[1] - a0[1]) * i / k)
                        b1 = (a0[0] + (b0[0] - a0[0]) * (i + 1) / k, a0[1] + (b0[1] - a0[1]) * (i + 1) / k)
                        out.append((a1, b1, m * (d / k) / tot if tot else 0.0, nm))
        return out

    rec17 = collections.defaultdict(lambda: [0.0, None, []])
    for r in H17["records"]:
        rec17[r["id"]][0] = r["miles"]
        rec17[r["id"]][1] = name_key(r["street"])
        rec17[r["id"]][2].append(r["pts"])
    PCS = {"2017": pieces([tuple(rec17[k]) for k in sorted(rec17)]),
           "2022": pieces([(b["miles"], name_key(b["street"]), b["lines"]) for c, b in sorted(b22.items())]),
           "2024": pieces([(b["miles"], name_key(b["street"]), b["lines"]) for c, b in sorted(b24.items())])}
    for v, ps in PCS.items():
        assert abs(sum(p[2] for p in ps) - miles[v]) < 0.05, v

    def matched(A, B):
        """For each piece of A: is its midpoint within MATCH_FT of a same-name line of B, projecting inside that
        segment (to END_FT past its ends), so a section that stops is not extended by the buffer."""
        g = collections.defaultdict(list)
        for a, b, _, nm in PCS[B]:
            for cx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                for cy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                    g[(cx, cy)].append((a, b, nm))
        out = []
        for a, b, _, nm in PCS[A]:
            p = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            cx, cy, hit = int(p[0] // CELL), int(p[1] // CELL), False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for s0, s1, n2 in g.get((cx + dx, cy + dy), ()):
                        if n2 != nm:
                            continue
                        ux, uy = s1[0] - s0[0], s1[1] - s0[1]
                        Ls = math.hypot(ux, uy)
                        if Ls == 0:
                            continue
                        t = ((p[0] - s0[0]) * ux + (p[1] - s0[1]) * uy) / Ls
                        if -END_FT <= t <= Ls + END_FT and seg_dist(p, s0, s1) <= MATCH_FT:
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    break
            out.append(hit)
        return out

    churn_geo = {}
    for A, B in (("2017", "2022"), ("2022", "2024")):
        mA, mB = matched(A, B), matched(B, A)
        keptA = sum(p[2] for p, h in zip(PCS[A], mA) if h)
        keptB = sum(p[2] for p, h in zip(PCS[B], mB) if h)
        churn_geo[(A, B)] = {"mA": mA, "mB": mB, "kept_on_first": keptA, "kept_on_second": keptB,
                             "dropped": miles[A] - keptA, "added": miles[B] - keptB}

    # ---- people
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,collision_datetime,victim_degree_of_injury,tb_latitude,tb_longitude,primary_rd",
                     where="victim_degree_of_injury in ('Severe Injury','Fatal Injury') and collision_datetime >= '2013-01-01T00:00:00'",
                     floor=3000, refresh=a.refresh)
    ppl = {}
    for v in V.rows:
        ppl[(v["case_id_pkey"], v["victim_id"])] = v
    assert len(ppl) == len(V.rows), "duplicate (case, victim) rows"
    # The data's own end: the newest crash of any severity, not the newest severe one.
    mx = sfdata.fetch("nwes-mmgh", select="max(collision_datetime) AS mx", order="mx", floor=1, refresh=a.refresh)
    newest = mx.rows[0]["mx"][:10]
    assert newest >= max(v["collision_datetime"][:10] for v in ppl.values())
    years = collections.Counter(v["collision_datetime"][:4] for v in ppl.values())
    assert all(years.get(str(y), 0) > 150 for y in range(2013, int(newest[:4]) + 1)), years
    people = []
    for k in sorted(ppl):
        v = ppl[k]
        try:
            lo, la = float(v["tb_longitude"]), float(v["tb_latitude"])
            P = xy(lo, la) if -122.53 < lo < -122.35 and 37.70 < la < 37.84 else None
        except (TypeError, ValueError, KeyError):
            P = None
        people.append({"date": v["collision_datetime"][:10], "killed": v["victim_degree_of_injury"] == "Fatal Injury", "P": P,
                       "rd": name_key(v.get("primary_rd"))})
    placed_share = sum(1 for p in people if p["P"]) / len(people)
    assert placed_share >= 0.98, placed_share

    def in_period(p, lo, hi):
        return p["date"] >= lo and (hi is None or p["date"] <= hi)

    # Own-geometry grids (the page's 60 ft rule): 2017 ArcGIS lines, 2022 and 2024 both ArcGIS (as the page) and DataSF.
    own = {"2017": Grid([([xy(*p) for p in r["pts"]], 1) for r in H17["records"]])}
    for v in ("2022", "2024"):
        H = json.load(open(os.path.join(ACCESS, "hin-%s.json" % v)))
        own[v] = Grid([([xy(*p) for p in r["pts"]], 1) for r in H["records"] if len(r["pts"]) > 1])
    ds = {"2022": Grid([([xy(*p) for p in ln], 1) for b in b22.values() for ln in b["lines"]]),
          "2024": Grid([([xy(*p) for p in ln], 1) for b in b24.values() for ln in b["lines"]])}

    def capture(grid, lo, hi, killed=None):
        base = [p for p in people if p["P"] and in_period(p, lo, hi) and (killed is None or p["killed"] == killed)]
        return share(sum(1 for p in base if grid.near(p["P"], ON_FT)), len(base))

    S = {"sources": {"nwes-mmgh": V.tag, "8vtn-qytr": r22.tag, "enwt-3u8m": r24.tag, 
                     "hin-2017": {"url": H2017_URL, "fetched_on": H17["fetched_on"]}},
         "newest_crash": newest, "people_by_year": dict(sorted(years.items())), "placed_share": round(100 * placed_share, 2),
         "rules": {"on_ft": ON_FT, "match_ft": MATCH_FT, "end_ft": END_FT, "piece_ft": PIECE_FT},
         "published": PUBLISHED, "versions": {}}
    for v in ("2017", "2022", "2024"):
        lo, hi = OOS[v]
        wl, wh = IN_WINDOW[v]
        S["versions"][v] = {
            "miles": round(miles[v], 1),
            "street_pct_published": PUBLISHED[v]["street_pct"],
            "out_of_sample": {"from": lo, "to": hi or newest, "people": capture(own[v], lo, hi), "killed": capture(own[v], lo, hi, True),
},
            "in_window_police": {"from": wl, "to": wh, "people": capture(own[v], wl, wh)},
        }
        if v in ds:
            S["versions"][v]["out_of_sample"]["people_datasf_geometry"] = capture(ds[v], lo, hi)
    S["versions"]["2024"]["in_sample_2020_2024"] = S["versions"]["2024"]["in_window_police"]
    S["versions"]["2024"]["in_sample_2022_2024"] = {"people": capture(own["2024"], "2022-01-01", "2024-12-31")}
    S["versions"]["2022"]["check_620_of_922"] = S["versions"]["2022"]["out_of_sample"]["people"]
    assert S["versions"]["2022"]["out_of_sample"]["people"]["n"] == 620 and S["versions"]["2022"]["out_of_sample"]["people"]["of"] == 922, \
        S["versions"]["2022"]["out_of_sample"]["people"]
    cg = churn_geo[("2017", "2022")]
    S["overlap_2017_2022"] = {"kept_miles_on_2017": round(cg["kept_on_first"], 1), "kept_miles_on_2022": round(cg["kept_on_second"], 1),
                              "published_overlap_miles": PUBLISHED_OVERLAP_2017_2022}

    # ---- churn: kept, dropped, added, and who was hurt on each in the period after the newer version's data
    S["churn"] = {}
    for A, B, lo, hi in (("2017", "2022", "2022-01-01", "2024-12-31"), ("2022", "2024", "2025-01-01", None)):
        cg = churn_geo[(A, B)]
        items = [((a, b), ("kept" if h else "dropped", nm)) for (a, b, _, nm), h in zip(PCS[A], cg["mA"])]
        items += [((a, b), ("kept" if h else "added", nm)) for (a, b, _, nm), h in zip(PCS[B], cg["mB"])]
        grid = Grid([([a, b], g) for (a, b), g in items])
        base = [p for p in people if p["P"] and in_period(p, lo, hi)]
        cnt, kil = collections.Counter(), collections.Counter()
        # A person goes to the nearest piece within ON_FT whose street is the report's primary road, the HIN's own
        # assignment rule. Near a piece only on the cross street: "cross_street", in no group's rate.
        for p in base:
            near = grid.near(p["P"], ON_FT)
            same = sorted((d, k) for k, d in near.items() if grid.items[k][1][1] == p["rd"])
            if same:
                g = grid.items[same[0][1]][1][0]
            elif near:
                g = "cross_street"
            else:
                g = "elsewhere"
            cnt[g] += 1
            kil[g] += p["killed"]
        end = dt.date.fromisoformat(hi or newest)
        yrs = ((end - dt.date.fromisoformat(lo)).days + 1) / 365.25
        city_miles = CITY_MILES
        kept = (cg["kept_on_first"] + cg["kept_on_second"]) / 2
        gm = {"kept": kept, "dropped": cg["dropped"], "added": cg["added"]}
        gm["elsewhere"] = city_miles - sum(gm.values())
        out = {"period": [lo, hi or newest], "years": round(yrs, 2), "people": len(base), "groups": {},
               "kept_miles_measured_on": {A: round(cg["kept_on_first"], 1), B: round(cg["kept_on_second"], 1)}}
        for g in ("kept", "dropped", "added", "elsewhere"):
            out["groups"][g] = {"miles": round(gm[g], 1), "people": cnt[g], "killed": kil[g],
                                "per_mile_year": round(cnt[g] / gm[g] / yrs, 2 if g != "elsewhere" else 1)}
        out["cross_street"] = {"people": cnt["cross_street"], "killed": kil["cross_street"],
                               "note": "within 60 ft of a piece of either version, but the report's primary road is another street"}
        out["elsewhere_miles_note"] = "city street miles implied by the 2022 HIN's 121.5 mi and 12.2%% (%.0f mi), less the three groups" % city_miles
        S["churn"]["%s_to_%s" % (A, B)] = out
    c24 = S["churn"]["2022_to_2024"]["groups"]
    for g, m in PUBLISHED_CHURN_2024.items():
        assert abs(c24[g]["miles"] - m) / m < 0.05, (g, c24[g]["miles"], m)

    write_json(os.path.join(OUT, "summary.json"), S)
    write_text(os.path.join(OUT, "chart.mdx"), chart(S))
    print(json.dumps({v: {"miles": x["miles"], "oos": x["out_of_sample"]["people"], "in_window": x["in_window_police"]["people"]}
                      for v, x in S["versions"].items()}, indent=1))
    print(json.dumps(S["overlap_2017_2022"]), json.dumps(S["churn"], indent=1))


def chart(S):
    """The doc's PlotChart: per version, its share of city streets against its share of people severely injured or
    killed in the years after its data. Two bars per version, labelled with their own figures."""
    rows, dom = [], []
    end = dt.date.fromisoformat(S["versions"]["2024"]["out_of_sample"]["to"])
    lab = {"2017": "2017 HIN: hurt 2018 to 2020", "2022": "2022 HIN: hurt 2022 to 2024",
           "2024": "2024 HIN: hurt Jan 2025 to %s" % end.strftime("%b %Y")}
    for v in ("2017", "2022", "2024"):
        x = S["versions"][v]
        o = x["out_of_sample"]["people"]
        d1, d2 = lab[v], "%s HIN: street miles" % v
        dom += [d2, d1]
        rows.append({"d": d2, "s": "Share of city street miles", "v": x["street_pct_published"],
                     "t": "%s%% (%s mi)" % (x["street_pct_published"], x["miles"])})
        rows.append({"d": d1, "s": "Share of people severely injured or killed", "v": o["pct"],
                     "t": "%s of %s (%d%%)" % (o["n"], o["of"], round(o["pct"]))})
    dj = lambda o: json.dumps(o)
    marks = [{"mark": "barX", "data": "bars", "options": {"y": "d", "x": "v", "fill": "s", "fillOpacity": 0.9}},
             {"mark": "text", "data": "bars", "options": {"y": "d", "x": "v", "text": "t", "dx": 6, "textAnchor": "start", "fontSize": 11, "fill": "#333"}}]
    opts = {"width": 620, "height": 260, "marginLeft": 240, "marginRight": 110, "marginTop": 30, "marginBottom": 36,
            "color": {"domain": ["Share of city street miles", "Share of people severely injured or killed"], "range": ["#9cc7c1", "#2f7d76"], "legend": True},
            "x": {"domain": [0, 100], "label": "Percent", "labelAnchor": "center", "labelArrow": False, "grid": True, "tickSize": 0},
            "y": {"domain": dom, "label": None, "tickSize": 0}}
    return ("<PlotChart\n  title=\"Each HIN Held About Two Thirds of the People Hurt After It Was Drawn\"\n"
            "  data={%s}\n  marks={%s}\n  options={%s}\n/>\n") % (dj({"bars": rows}), dj(marks), dj(opts))


if __name__ == "__main__":
    main()
