#!/usr/bin/env python3
"""Trace SFMTA's November 2024 draft Biking and Rolling Plan network map (https://www.sfmta.com/media/41119/download, printed p. 59) and record the lines the adopted plan dropped.

The first draft, "Biking and Rolling Plan First Draft 11.19.24", presented to
the SFMTA Board on 2024-11-19, prints its Northstar Network map on printed
page 59 (PDF page 31) as a vector page in the same format as the adopted
map. So this script cuts that page out with pdfseparate and runs
tools/bike-network/north-star-map-trace.py on it, imported, with only the legend and
basemap colours changed to the draft's own (read off its key with pdftocairo
-svg, 2026-10-14). The georeference checks in that script apply unchanged.

It then compares the draft trace with the adopted trace
(site/data/north-star/traced.geojson, and the adopted map's off-street lines
in out/north-star/map-trace/off-street.geojson) and checks the 19 extents in
EXTENTS below, which were read by eye against side-by-side crops of both maps
on 2026-10-14. An extent of "only" blocks must be traced in the draft with
the stated class, absent from the adopted trace, and mostly (over half its
length) more than NEAR_M from any adopted line, so it is a dropped line, not
the same line redrawn a few metres over. An extent whose blocks are listed as
None takes every draft block of that street and class the adopted map draws
Undecided (Sutter, Clarendon). Any failure stops the run.

Writes data/community-plans/brp-draft-extents.json: per extent its street,
ends, draft class, adopted state, and each block's cnn and metres. The
brp-draft-2024 rows in data/community-plans/bikeway-proposals.json are these
extents, and tools/bike-network/community-plan-bikeways.py places them by name like any
other plan; this file is what to check them against. The full trace stays in
.cache/brp-draft/trace/ (untracked, rebuilt on demand).

    python3 tools/bike-network/brp-draft-trace.py

Requires pdfseparate and pdftocairo (poppler). Fetches the 56 MB PDF into
.cache/brp-draft/ when missing.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
import stable  # noqa: E402

URL = "https://www.sfmta.com/media/41119/download"
PAGE = 31                                   # PDF page; printed page 59
CACHE = os.path.join(ROOT, ".cache", "brp-draft")
FULL_PDF = os.path.join(CACHE, "brp-first-draft-2024-11-19.pdf")
MAP_PDF = os.path.join(CACHE, "draft-map.pdf")
TRACE = os.path.join(CACHE, "trace")
ADOPTED = os.path.join(ROOT, "site", "data", "north-star", "traced.geojson")
ADOPTED_OFF = os.path.join(ROOT, "out", "north-star", "map-trace", "off-street.geojson")
OUT = os.path.join(ROOT, "data", "community-plans", "brp-draft-extents.json")
PROPOSALS = os.path.join(ROOT, "data", "community-plans", "bikeway-proposals.json")

# The draft's legend strokes. Same classes as the adopted map; the colours
# differ in the third decimal, and Shared L3 is drawn in two near-identical
# blues.
LEGEND = {
    "rgb(27.450562%, 49.803162%, 44.7052%)": "teal",
    "rgb(14.901733%, 36.077881%, 58.039856%)": "Separated",
    "rgb(32.156372%, 70.196533%, 83.137512%)": "Shared",
    "rgb(58.824158%, 81.568909%, 89.411926%)": "Shared L3",
    "rgb(58.432007%, 81.568909%, 89.411926%)": "Shared L3",
    "rgb(50.196838%, 51.373291%, 52.157593%)": "Undecided",
}
BASEMAP = "rgb(94.902039%, 94.117737%, 94.117737%)"

NEAR_M = 40.0
LON_M, LAT_M = 88000.0, 111000.0

ROUTE = "the Golden Gate Heights and Forest Hill route"
# street, from, to, draft class, blocks (None: every Undecided-in-adopted
# block of that street and class), adopted state.
EXTENTS = [
    ("Noe St", "Duboce Ave", "Beaver St", "Shared", ["9607000", "9608000", "9609000", "9610000"], None),
    ("17th Ave", "Kirkham St", "Moraga St", "Shared L3", ["760000", "761000"], None),
    ("Moraga St", "16th Ave", "17th Ave", "Shared L3", ["9342101", "9342201"], None),
    ("16th Ave", "Lomita Ave", "Moraga St", "Shared L3", ["683000"], None),
    ("Lomita Ave", "Aloha Ave", "16th Ave", "Shared L3", ["8469000"], None),
    ("Aloha Ave", "14th Ave", "Lomita Ave", "Shared L3", ["2209000"], None),
    ("15th Ave", "14th Ave", "Noriega St", "Shared L3", ["618101", "618102", "618201"], None),
    ("14th Ave", "Noriega St", "Radio Ter", "Shared L3", ["565000", "566000", "568101", "568201", "568102"], None),
    ("Quintara St", "12th Ave", "Funston Ave", "Shared L3", ["10848000"], None),
    ("9th Ave", "Mesa Ave", "Rivera St", "Shared L3", ["443000", "444101", "444102", "444201", "444202", "445000"], None),
    ("Mesa Ave", "9th Ave", "Santa Rita Ave", "Shared L3", ["8997000"], None),
    ("Santa Rita Ave", "Mesa Ave", "San Marcos Ave", "Shared L3", ["11588101", "11588201"], None),
    ("San Marcos Ave", "Santa Rita Ave", "Dorantes Ave", "Shared L3", ["11494000", "11493000"], None),
    ("Dorantes Ave", "San Marcos Ave", "Magellan Ave", "Shared L3", ["4921000"], None),
    ("Magellan Ave", "Dorantes Ave", "Pacheco St", "Shared L3", ["8619101", "8619202"], None),
    ("Pacheco St", "Magellan Ave", "Dewey Blvd", "Shared L3", ["10076000", "10075000"], None),
    ("John F Kennedy Dr", "Transverse Dr", "30th Ave", "Separated", ["7541000"], None),
    ("Sutter St", "Sansome St", "Polk St", "Separated", None, "Undecided"),
    ("Clarendon Ave", "Twin Peaks Blvd", "Laguna Honda Blvd", "Separated", None, "Undecided"),
]


def fetch():
    """The draft PDF and its map page, cut out once and kept in .cache/."""
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.exists(FULL_PDF):
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (sf-works; +https://sf-works.org)"})
        with urllib.request.urlopen(req, timeout=300) as fh:
            body = fh.read()
        if not body.startswith(b"%PDF"):
            sys.exit("%s did not return a PDF" % URL)
        with open(FULL_PDF, "wb") as fh:
            fh.write(body)
    if not os.path.exists(MAP_PDF):
        subprocess.run(["pdfseparate", "-f", str(PAGE), "-l", str(PAGE), FULL_PDF, MAP_PDF], check=True)


def trace():
    """tools/bike-network/north-star-map-trace.py's main(), run on the draft page with the draft's legend."""
    mod = paths.load("north-star-map-trace.py")
    mod.LEGEND, mod.BASEMAP = LEGEND, BASEMAP
    argv = sys.argv
    sys.argv = [argv[0], "--map", MAP_PDF, "--out", TRACE, "--work", os.path.join(CACHE, "work"),
                "--centerlines", os.path.join(ROOT, "out", "north-star", "cache", "centerlines.json"),
                "--segments", os.path.join(ROOT, "out", "north-star", "segments.geojson")]
    try:
        mod.main()
    finally:
        sys.argv = argv


def dense(coords, step=10.0):
    out = []
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        n = max(1, int(math.hypot((x1 - x0) * LON_M, (y1 - y0) * LAT_M) / step))
        out += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n + 1)]
    return out


def main():
    fetch()
    trace()
    draft = {f["properties"]["cnn"]: f for f in json.load(open(os.path.join(TRACE, "traced.geojson")))["features"]}
    adopted = json.load(open(ADOPTED))["features"]
    fac = {f["properties"]["cnn"]: f["properties"]["facility"] for f in adopted}
    # A 50 m grid of points along every adopted line, on-street and off.
    grid = collections.defaultdict(list)
    for f in adopted + json.load(open(ADOPTED_OFF))["features"]:
        for x, y in dense(f["geometry"]["coordinates"]):
            grid[(int(x * LON_M / 50), int(y * LAT_M / 50))].append((x, y))

    def near(x, y):
        gx, gy = int(x * LON_M / 50), int(y * LAT_M / 50)
        return any(((px - x) * LON_M) ** 2 + ((py - y) * LAT_M) ** 2 < NEAR_M ** 2
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) for px, py in grid.get((gx + dx, gy + dy), ()))

    out, bad = [], []
    for street, frm, to, cls, cnns, adopted_as in EXTENTS:
        if cnns is None:
            key = street.upper()
            cnns = sorted((c for c, f in draft.items() if f["properties"]["street"] == key
                           and f["properties"]["facility"] == cls and fac.get(c) == adopted_as), key=int)
            if not cnns:
                bad.append("%s: no draft %s block the adopted map draws %s" % (street, cls, adopted_as))
        blocks = []
        for c in cnns:
            f = draft.get(c)
            if not f:
                bad.append("%s: %s is not in the draft trace" % (street, c))
                continue
            if f["properties"]["facility"] != cls:
                bad.append("%s: %s is %s in the draft, not %s" % (street, c, f["properties"]["facility"], cls))
            if fac.get(c) != adopted_as:
                bad.append("%s: %s is %s in the adopted trace, not %s" % (street, c, fac.get(c), adopted_as))
            blocks.append({"cnn": c, "metres": f["properties"]["length_m"]})
        row = {"street": street, "from": frm, "to": to, "draft": cls, "adopted": adopted_as or "not drawn", "blocks": blocks}
        if adopted_as is None and blocks:
            pts = [p for b in blocks for p in dense(draft[b["cnn"]]["geometry"]["coordinates"])]
            share = sum(near(x, y) for x, y in pts) / len(pts)
            row["nearAdopted"] = round(share, 2)
            if share >= 0.5:
                bad.append("%s: %.0f%% lies within %d m of an adopted line, so it may be the same line redrawn"
                           % (street, 100 * share, NEAR_M))
        out.append(row)
    # The proposals file's draft rows must be these extents, end for end.
    rows = [(r["street"], r["from"], r["to"]) for r in json.load(open(PROPOSALS))["segments"] if r["plan_id"] == "brp-draft-2024"]
    if rows != [(e[0], e[1], e[2]) for e in EXTENTS]:
        bad.append("the brp-draft-2024 rows in %s differ from EXTENTS" % os.path.relpath(PROPOSALS, ROOT))
    if bad:
        sys.exit("brp-draft-trace: checks failed\n  " + "\n  ".join(bad))
    geo = json.load(open(os.path.join(TRACE, "georeference.json")))
    stable.write_json(OUT, {
        "source": URL, "printedPage": 59, "pdfPage": PAGE,
        "fullPdfSha256": hashlib.sha256(open(FULL_PDF, "rb").read()).hexdigest(),
        "georeference": {k: geo["report"][k] for k in ("scale_agreement", "median_resid_m")},
        "tracedBlocks": len(draft), "tracedMiles": round(sum(f["properties"]["length_m"] for f in draft.values()) / 1609.34, 1),
        "nearMetres": NEAR_M,
        "method": "tools/bike-network/brp-draft-trace.py: north-star-map-trace.py on the draft page with the draft's legend colours, "
                  "then each extent checked against the adopted trace. Extents were read by eye against crops of both maps.",
        "extents": out}, indent=1, ensure_ascii=False)
    print("wrote %s: %d extents, %d blocks" % (os.path.relpath(OUT, ROOT), len(out), sum(len(r["blocks"]) for r in out)))


if __name__ == "__main__":
    main()
