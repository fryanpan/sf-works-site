"""CDE's school records with the points that fail the city's address check corrected.

Every script that reads a school's point out of data/extract/schools/cde-sf.json reads it through
records() here, so one correction holds across them. The corrections are
data/school-sim/school-points.json's "fixed" rows (tools/school-trips/school-points.py): a school whose CDE point
is more than 500 ft from the Enterprise Addressing System's point for its own street address takes the
EAS point. CDE's point is kept beside it as cde_lon, cde_lat.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import json
import os

ROOT = paths.ROOT
CDE = os.path.join(ROOT, "data", "extract", "schools", "cde-sf.json")
POINTS = os.path.join(ROOT, "data", "school-sim", "school-points.json")


def fixes():
    """{cds: (lon, lat)} for every school moved to its EAS point."""
    if not os.path.exists(POINTS):
        return {}
    rows = json.load(open(POINTS))["schools"]
    return {c: (x["eas"]["lon"], x["eas"]["lat"]) for c, x in sorted(rows.items()) if x.get("fixed") and x.get("eas")}


def apply(records):
    """CDE records (dicts with cds, lon, lat) with the fixes applied; new dicts, the input is left alone."""
    fx = fixes()
    out = []
    for r in records:
        if r.get("cds") in fx:
            r = dict(r, cde_lon=r.get("lon"), cde_lat=r.get("lat"), lon=fx[r["cds"]][0], lat=fx[r["cds"]][1])
        out.append(r)
    return out


def records(path=CDE):
    """cde-sf.json's records, corrected."""
    return apply(json.load(open(path))["records"])


INDEX = os.path.join(ROOT, "site", "data", "school-sim", "index.json")


def index_schools(path=INDEX):
    """site/data/school-sim/index.json's schools with the fixes applied.

    The steps before school-sim (grounds, crash counts, speed levers, the calming order) read the previous
    run's index.json, so a school moved here is moved for them before the simulation writes its new point.
    A case-study school keeps its point: the simulation uses its door from data/school-case/dropoff.json."""
    fx = fixes()
    out = []
    for s in json.load(open(path))["schools"]:
        if s["cds"] in fx and not s.get("case"):
            s = dict(s, lon=round(fx[s["cds"]][0], 5), lat=round(fx[s["cds"]][1], 5))
        out.append(s)
    return out
