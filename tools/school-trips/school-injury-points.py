#!/usr/bin/env python3
"""Kids 5 to 18 hurt near a school at school hours over 20 school years, as points for School Trips' heat map layer.

    tools/school-trips/school-injury-points.py      # writes site/data/school-sim/injuries.json

Bryan, 2026-10-13, on the evidence doc: "On the school tool, can you add a layer you can toggle on with a heat map of
the injuries near schools in the last 20 years during school hours? ... So that we can look at it by school and
city-wide".

INPUTS. DataSF nwes-mmgh (one row per injured or killed person), read through lib/sfdata.py, which caches the
query under data/socrata-cache/. The schools are site/data/school-sim/index.json's, the same doors the tool draws.

THE COUNT. A victim counts when they were 5 to 18, injured or killed, hurt on a weekday from 6 am to 6 pm, August 1 to
May 31, in school years 2005-06 to 2024-25 (lib/school_window.py, the one definition every count of kids hurt
near schools uses; Bryan, 2026-10-21: "keep it to school hours (6AM to 6PM) on weekdays during the school year"), at a crash within NEAR_FT of any school's grounds (data/school-sim/grounds.json,
measured from the edge of the grounds as state law measures a school zone). Each point is
[lon, lat] to 5 decimal places, the school year it fell in, and the index in index.json of the school with the nearest grounds. `near` counts,
for each school, every kid within NEAR_FT of its grounds, so a kid near two schools counts at both. A crash
with several hurt kids gives one point per kid, so the heat map counts kids, not crashes.

STATUS UNDER THE INCREMENTAL-UPDATER RULE. A build read by the School Trips page. It reads the cached query and has
no --update of its own; sfdata.py refetches when its cache is stale. In pipeline/transportation-update.py after school-sim.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
import sfdata
from lib import school_grounds, school_points, school_window

NEAR_FT = 1320
FIRST, LAST = 2005, 2024          # school years 2005-06 to 2024-25
OUT = os.path.join(ROOT, "site", "data", "school-sim", "injuries.json")
FT_LAT = 364000.0
FT_LON = 364000.0 * math.cos(math.radians(37.76))


def main():
    sch = school_points.index_schools()
    V = sfdata.fetch("nwes-mmgh", select="case_id_pkey,victim_id,victim_age,victim_degree_of_injury,collision_datetime,"
                     "collision_time,tb_latitude,tb_longitude", floor=80000)
    pts, years, cand = [], set(), []
    for v in V.rows:
        k = school_window.kid_hurt(v)
        if k is None:
            continue
        sy = school_window.school_year_start(k["date"])
        if not FIRST <= sy <= LAST:
            continue
        try:
            la, lo = float(v["tb_latitude"]), float(v["tb_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        cand.append((lo, la, sy))
    # Distance to each school's grounds, as state law measures a school zone (lib/school_grounds.py).
    where = [(s["lon"], s["lat"]) for s in sch]
    best, _d = school_grounds.nearest(where, [c[0] for c in cand], [c[1] for c in cand], NEAR_FT)
    near = {s["cds"]: 0 for s in sch}
    for j, s in enumerate(sch):
        dj = school_grounds.dist_ft(s["lon"], s["lat"], [c[0] for c in cand], [c[1] for c in cand])
        near[s["cds"]] = int((dj <= NEAR_FT).sum())
    for (lo, la, sy), j in zip(cand, best):
        if j < 0:
            continue
        pts.append([round(lo, 5), round(la, 5), sy, int(j)])
        years.add(sy)
    pts.sort()
    out = {"note": "Written by tools/school-trips/school-injury-points.py. pts: [lon, lat, school year it starts in, index of the "
                   "nearest school in index.json], one per kid hurt.",
           "source": V.tag,
           "rule": "%s, school years %s to %s, within %d ft of a school's grounds"
                   % (school_window.RULE, school_window.label(FIRST), school_window.label(LAST), NEAR_FT),
           "nearFt": NEAR_FT, "near": near, "years": LAST - FIRST + 1, "n": len(pts), "pts": pts}
    # Quality: a plausible count, every year present, every point inside San Francisco and on a school.
    assert len(pts) > 500, "fewer than 500 kids in 20 years: the read is short"
    assert years == set(range(FIRST, LAST + 1)), "school years missing: %s" % sorted(set(range(FIRST, LAST + 1)) - years)
    assert all(-122.52 < p[0] < -122.35 and 37.70 < p[1] < 37.84 and 0 <= p[3] < len(sch) for p in pts)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print("school-injury-points: %d kids within %d ft of %d schools over %d school years; wrote %s"
          % (len(pts), NEAR_FT, len(sch), LAST - FIRST + 1, os.path.relpath(OUT, ROOT)))


if __name__ == "__main__":
    main()
