#!/usr/bin/env python3
"""The order School Trips' traffic calming takes schools in: kids 5 to 18 hurt within 660 feet of each school over the last 10 school years.

    tools/school-trips/school-calm-priority.py      # writes data/school-sim/calm-priority.json

Bryan, 2026-10-13, on the evidence doc: "Let's give a range for calming from $5M
to $20M for an eigth of a mile of streets, and use $10M as the central estimate.
With top injury schools (over last 10 years) as the priority order".

INPUTS. DataSF nwes-mmgh (one row per injured or killed person), read through
lib/sfdata.py, which caches the query under data/socrata-cache/. The
schools are site/data/school-sim/index.json's, so the order uses the
simulation's schools. Street classes come from OpenStreetMap,
data/osm-cache/sf-drive.json.

THE COUNT. A victim counts when they were 5 to 18, injured or killed, hurt on
a weekday between 6 am and 6 pm, in school years 2015-16 to 2024-25 (August 1 to
May 31, June and July out: lib/school_window.py, the one definition every
count of kids hurt near schools uses), at a crash within CALM_FT of a school's grounds (data/school-sim/grounds.json,
the edge of the grounds as state law measures a school zone). A crash near two
schools counts for the nearer. Schools are ranked by that count (`kids`), ties broken
by `residentialKids`, then by cds. `residentialKids` is the part where both of
the crash's streets are residential, living or unclassified in OpenStreetMap,
the streets calming treats. A street name with no OpenStreetMap match leaves
the crash out of `residentialKids` but in `kids`.

tools/school-trips/school-sim.py walks this list, adding each school's calmed miles at
$0.25M a mile until the budget runs out, so this file holds only the order and
the counts.

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A one-off build read by the
simulation. In pipeline/transportation-update.py before school-sim; it has no
--update of its own, and sfdata.py refetches when its cache is stale.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata
from lib import school_grounds, school_points, school_window

CALM_FT = 660
YEARS = school_window.years(2015, 2024)
OUT = os.path.join(ROOT, "data", "school-sim", "calm-priority.json")
RANK = {"motorway": 6, "motorway_link": 6, "trunk": 5, "trunk_link": 5, "primary": 4, "primary_link": 4,
        "secondary": 3, "secondary_link": 3, "tertiary": 2, "tertiary_link": 2,
        "unclassified": 1, "residential": 1, "living_street": 1}
ABBR = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "PLACE": "PL", "COURT": "CT",
        "LANE": "LN", "TERRACE": "TER", "HIGHWAY": "HWY", "ALLEY": "AL", "CIRCLE": "CIR", "PARKWAY": "PKWY", "PLAZA": "PLZ",
        "SAINT": "ST"}
FT_LAT = 364000.0
FT_LON = 364000.0 * math.cos(math.radians(37.76))


def norm(s):
    """A street name in one form for both sources: upper case, leading zeros off ("03RD" to "3RD"), suffixes abbreviated."""
    w = re.sub(r"[^A-Z0-9 ]", "", (s or "").upper()).split()
    return " ".join(ABBR.get(x, x) for x in (re.sub(r"^0+(?=\d)", "", x) for x in w))


def street_ranks():
    best = collections.defaultdict(int)
    for e in json.load(open(os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")))["elements"]:
        t = e.get("tags", {})
        if t.get("name") and t.get("highway") in RANK:
            k = norm(t["name"])
            best[k] = max(best[k], RANK[t["highway"]])
    return best


def main():
    sch = [(s["cds"], s["name"], s["lon"], s["lat"]) for s in school_points.index_schools()]
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,collision_datetime,"
                     "collision_time,tb_latitude,tb_longitude,primary_rd,secondary_rd", floor=80000)
    ranks = street_ranks()
    kids, res = collections.Counter(), collections.Counter()
    n_in, n_unmatched = 0, 0
    pts = []
    for v in V.rows:
        k = school_window.kid_hurt(v)
        if k is None or k["year"] not in YEARS:
            continue
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        pts.append((lo, la, v))
    # Distance to the school's grounds, as state law measures a school zone (lib/school_grounds.py).
    near, _d = school_grounds.nearest([(s[2], s[3]) for s in sch], [p[0] for p in pts], [p[1] for p in pts], CALM_FT)
    for (lo, la, v), j in zip(pts, near):
        if j < 0:
            continue
        best = sch[j][0]
        n_in += 1
        kids[best] += 1
        a, b = ranks.get(norm(v.get("primary_rd"))), ranks.get(norm(v.get("secondary_rd")))
        if a is None or b is None:
            n_unmatched += 1
        elif max(a, b) <= 1:
            res[best] += 1
    order = sorted(sch, key=lambda s: (-kids[s[0]], -res[s[0]], s[0]))
    out = {
        "source": V.tag,
        "rule": "%s, school years %s to %s, within %d ft of the school's grounds"
                % (school_window.RULE, YEARS[0], YEARS[-1], CALM_FT),
        "calmFt": CALM_FT, "years": len(YEARS),
        "kidsNear": n_in, "kidsUnmatchedStreet": n_unmatched, "residentialKids": sum(res.values()),
        "order": [{"cds": c, "name": n, "kids": kids[c], "residentialKids": res[c]} for c, n, _lo, _la in order],
    }
    # Quality: every school once, counts within the totals, nothing negative.
    assert len({o["cds"] for o in out["order"]}) == len(sch), "a school is listed twice"
    assert sum(o["kids"] for o in out["order"]) == n_in and out["residentialKids"] <= n_in
    assert n_in > 100, "fewer than 100 kids near schools in 10 years: the read is short"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("calm priority: %d kids within %d ft over %d years, %d where both streets are residential, %d with an unmatched street"
          % (n_in, CALM_FT, len(YEARS), out["residentialKids"], n_unmatched))
    print("  top: " + "; ".join("%s %d" % (o["name"], o["kids"]) for o in out["order"][:5]))
    print("  wrote " + os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
