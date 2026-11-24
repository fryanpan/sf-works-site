#!/usr/bin/env python3
"""Every unit of protected public open space the California Protected Areas Database (CPAD) lists in San Francisco County: the Presidio, the GGNRA's units, Candlestick Point, the Port's parks, and the city's own, Rec and Park's included.

    pipeline/sources/cpad-sf.py   # write data/extract/cpad/sf-units.json (pipeline/refresh-extracts.py runs this
                                  # only when the layer's marker moves)

The full access map's "park" and "major park" were Rec and
Park's own properties (DataSF gtr9-ntp6) only, so the Presidio, Ocean Beach,
Lands End and Fort Funston were not parks on it (Fable review, 2026-10-23).
CPAD is GreenInfo Network's inventory of every protected park and open space
holding in California, published by the California Natural Resources Agency
(calands.org). This reads its "Units by access type" layer on CNRA's ArcGIS
server (SERVICE), one row per park unit.

WHAT IS KEPT. Every unit in San Francisco County, whatever its holder or access
type, so the extract is the county's whole list. tools/travel/full-map-destinations.py
picks from it: the open-access public units Rec and Park's own dataset doesn't
already cover. Geometry is GeoJSON in WGS84, rounded to 6 decimal places
(about 10 cm).

INCREMENTAL. pipeline/refresh-extracts.py compares the layer's marker, its
statewide row count plus the release named in the layer's description (for
example "Units by access type 2025b"), with the last run's, and re-reads only
when it moved. CPAD publishes about twice a year. Checks: extracts_checks in
pipeline/transportation-quality.py (row floor, unique unit_id, required fields,
the Presidio present at over 1,000 acres).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402,F401  (puts lib/ on sys.path, for `from extract import Extract`)
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SERVICE = "https://gis.cnra.ca.gov/arcgis/rest/services/Boundaries/CPAD_AccessType/MapServer/1"
FIELDS = ["UNIT_ID", "UNIT_NAME", "AGNCY_NAME", "AGNCY_LEV", "MNG_AGENCY", "ACCESS_TYP", "ACRES", "YR_EST"]


def get_json(url, data=None, timeout=180):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.load(fh)


def release():
    """The release the layer's description names, e.g. 'Units by access type 2025b'."""
    return (get_json(SERVICE + "?f=json").get("description") or "").strip()


def _round(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 6), round(c[1], 6)]
    return [_round(x) for x in c]


def fetch_units():
    """Every San Francisco County unit, sorted by unit id."""
    q = urllib.parse.urlencode({"where": "COUNTY='San Francisco'",
                                "outFields": ",".join(FIELDS), "returnGeometry": "true", "outSR": "4326",
                                "f": "geojson", "resultRecordCount": "2000"}).encode()
    d = get_json(SERVICE + "/query", data=q)
    if d.get("error") or d.get("exceededTransferLimit"):
        raise RuntimeError("CPAD query failed or was truncated: %s" % json.dumps(d)[:300])
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        g = f.get("geometry")
        out.append({"unit_id": p["UNIT_ID"], "name": p["UNIT_NAME"], "agency": p["AGNCY_NAME"],
                    "agency_level": p["AGNCY_LEV"], "manager": p["MNG_AGENCY"], "access": p["ACCESS_TYP"],
                    "acres": round(float(p["ACRES"] or 0), 2), "year_established": p.get("YR_EST"),
                    "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"])} if g else None})
    return sorted(out, key=lambda r: r["unit_id"])


def meta():
    """The extract's meta, with the release the layer names now, so a re-read never keeps an old release's name."""
    return {"source": "California Protected Areas Database, Units by access type (CNRA ArcGIS)",
            "service": SERVICE, "release": release(), "rule": "COUNTY = San Francisco, every unit"}


def main():
    from extract import Extract
    ex = Extract("cpad")
    old = ex.read("sf-units")
    meta_ = meta()
    records = fetch_units()
    if old is not None and len(records) < len(old.records) // 2:
        raise SystemExit("CPAD re-read returned %d units against %d on disk; kept the old copy"
                         % (len(records), len(old.records)))
    ex.write("sf-units", records, meta=meta_)
    print("  cpad/sf-units: %d units (%s)" % (len(records), meta_["release"]))


if __name__ == "__main__":
    main()
