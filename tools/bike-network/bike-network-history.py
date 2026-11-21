#!/usr/bin/env python3
"""The bike network by year since 2015: total miles, all-ages miles, and who is within reach of the all-ages part.

    tools/bike-network/bike-network-history.py            # build from the tracked extracts
    tools/bike-network/bike-network-history.py --refetch  # re-read every source first

Bryan, 2026-09-22: start with miles of bike network over
time "because that's what the city reports need to monitor"; then miles that
meet the all-ages standard; then "what fraction of the people of the city have
had access" to the all-ages network and "how many of the schools are near the
all-ages network", trended back; judge "based on modern standards"; and "tell
me where the data quality no longer supports the analysis." Schools and
libraries enter the count within about a year of opening; population is right
within about a year at block level; distance was first "as the bird flies".
Bryan, 2026-09-29: measure it "walkable ... instead of
as the bird flies", so reach is walking distance along OpenStreetMap's walk
network (lib/walknet.py), and a block is 440 feet, near the
population-weighted typical block pipeline/sources/sf-block-length.py measures.

Sources, each mirrored once under data/extract/ with the date it was fetched:
  sfmta-bikeway/network.json     SFMTA's ArcGIS bikeway layer, attributes
                                 (INSTALL_YR/MO, UPDATE_YR/MO); the live state.
  sfmta-bikeway/geometry.json    the same layer's line geometry, per row.
  bikeway-snapshots/<stamp>.json Internet Archive captures of DataSF ygmz-vaxd's
                                 CSV export. DataSF replaces the dataset
                                 wholesale on refresh and keeps no history, so
                                 these captures are the only record of what the
                                 layer said in 2021, 2022, 2024, 2025 and early
                                 2026.
  slow-streets/segments.json     DataSF hkz3-itiu, the Slow Streets program's
                                 segments with install dates.
  census-blocks/2010.json        Census 2010 blocks, population and interior
                                 point, from TIGERweb (the Census API now needs a
                                 key; TIGERweb does not).
  census-blocks/2020.json        Census 2020 blocks, population and interior
                                 point, from DataSF p2fw-hsrv.
  census-blocks/acs5-bg.json     ACS 5-year total population by block group,
                                 2015 to 2024, from data.census.gov's table API.
  schools/cde-sf.json            California Department of Education public
                                 school directory, San Francisco rows, from the
                                 Internet Archive's 2025-10-05 capture (the live
                                 download sits behind a web application firewall
                                 that returns a challenge page). Carries OpenDate
                                 and ClosedDate, which DataSF 7e7j-59qk lacks for
                                 closed schools (it lists only active ones).
  libraries/branches.json        SFPL branches and the Main Library from DataSF
                                 nc68-ngbr (City Facilities), plus the one
                                 renovation closure in the window, from SFPL's
                                 own pages, entered by hand below.

Writes out/bike-network-history/history.json, .../history.md, and under
site/data/bike-history/: segments.json (per-segment class by year),
all-ages.geojson (the all-ages blocks with the year each became one) and
reach.json (census blocks, schools and branches with the year each came within
reach), for the animated map on the site's /transportation page.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import csv
import datetime as dt
import gzip
import io
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import stable  # noqa: E402
from extract import Extract  # noqa: E402
import sfdata  # noqa: E402
from bikeway_snap import TOLERANCE_M, rekeyed_layer, shared_snapper  # noqa: E402
from mile_basis import BASIS  # noqa: E402
import bikeway_snap  # noqa: E402
from lib import bikeway_departed  # noqa: E402
# The pandemic Slow Street corridors SFMTA dropped in December 2022, resolved
# to centerline blocks from the centerline and hkz3-itiu alone (not from
# tools/bike-network/bike-removals.py's output, which reads this script's).
from lib import slow_corridors  # noqa: E402
import walknet  # noqa: E402
from walknet import WalkReach  # noqa: E402
# Census blocks are measured from their street frontage (lib/walknet.py).
walknet.use_census_outlines()

# ---------------------------------------------------------------------------
# Working defaults. Bryan may change any of these; each is one constant.
# ---------------------------------------------------------------------------

# The pages use the Biking and Rolling Plan's definitions throughout (Bryan,
# 2026-09-22: "use as close as you can get to the plan's definition wherever
# possible"). Two conventions follow from the plan:
#
# 1. Miles are counted per direction row, as the layer holds them. The plan's
#    "472 miles today" (printed p. 20) is the sum of every row's length in
#    SFMTA's bikeway layer, which carries one row per direction of travel on
#    most blocks; summing the live rows' geometry gives 472.6. A two-way street
#    with a lane each way is two rows and counts twice. Centreline miles (one
#    length per block) are kept in the JSON beside the row miles for a reader
#    who wants them, and nothing on a page uses them.
# 2. All-ages is the plan's high-quality test (printed p. 24; Appendix G,
#    Toole Design connectivity memo of 2024-02-13): Class I, Class IV and Slow
#    Streets; Class II with Bike Comfort Index above 80; Class III with traffic
#    calming and BCI above 80. A row qualifies by its own class; a Class II or
#    III row qualifies when its block's BCI clears the threshold, and a Class
#    III row also needs traffic calming on its block by that year. No dataset
#    says "calmed" per street, so calming is read from the city's two traffic
#    calming datasets: a mid-block measure on the block (DataSF abhw-ffzx) or
#    an intersection device at either end (bp3t-bd4t), status Complete or
#    Existing, installed by that year or undated. Bryan chose this reading on
#    2026-09-24 ("Use calming test"); scripts/reach-method-test.py showed it
#    brings the 2024 residents share to the plan's printed 80%.
#
# SFMTA's classes: CLASS I is an off-street path, CLASS II a painted lane,
# CLASS III a sharrow or signed route, CLASS IV a separated (protected) lane.
PLAN_ALL_AGES_CLASSES = {"CLASS I", "CLASS IV"}
PLAN_BCI_CLASSES = {"CLASS II", "CLASS III"}
PLAN_BCI_THRESHOLD = 80
PLAN_BCI_FIELD = "bci"  # the combined score; the plan does not say whether it means bci, bci_ft or bci_tf
# Slow Streets (DataSF hkz3-itiu) count as all-ages from their install date. A
# Slow Street is two-way, so a Slow Street block outside the bikeway layer
# counts its length twice, which is how the plan's 32 miles of Slow Streets
# (p. 20) comes out of the dataset's 16 centreline miles.
INCLUDE_SLOW_STREETS = True
CALMING_MID_BLOCK = "abhw-ffzx"
CALMING_INTERSECTION = "bp3t-bd4t"
CENTERLINES = "3psu-pn9h"
SLOW_STREET_DIRECTIONS = 2
# The one definition the pages read. A stricter set (Class I, Class IV and
# Slow Streets only, no BCI test) is written to the JSON as all_ages_strict_miles
# because it costs one sum; no page shows it.
DEFAULT_DEFINITION = "plan"
# Off-street paths in the Presidio (federal land; the layer's NOTES say
# "PRESIDIO") are in the layer with no CNN. True keeps them in every figure;
# the tables also print them separately so the figures can be read without.
INCLUDE_PRESIDIO = True
# First year in the table.
START_YEAR = 2015
# "Within reach" is a walking distance from an all-ages segment. The
# plan's is a quarter mile; REACH_THRESHOLDS (below MILE) adds one and two
# city blocks and 1,000 feet, so a reader can pick the distance.
REACH_MILES = 0.25
# A school or library counts in year Y when open on this month-day of Y.
COUNT_DATE = "09-01"
# The school types counted as public schools (CDE SOCType). Preschools, adult
# education centres, ROC/ROP and rows without a type are left out.
SCHOOL_TYPES = {
    "Elementary Schools (Public)", "High Schools (Public)",
    "Intermediate/Middle Schools (Public)", "Junior High Schools (Public)",
    "K-12 Schools (Public)", "Elemen Schools In 1 School Dist. (Public)",
    "Alternative Schools of Choice", "Continuation High Schools",
    "Special Education Schools (Public)", "County Community",
    "Juvenile Court Schools", "Opportunity Schools",
}

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

SERVICE = "https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0"
# The 2023 Draft Bike Comfort Index, every street segment in the city, keyed by
# CNN (the field is named cnn_sgmt_pkey). One snapshot, no history. See
# research/sources/sfmta-arcgis.md for the scale: 4 to 146, higher is more comfortable,
# median 59; 21% of segments clear 80.
BCI_SERVICE = "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4"
# Internet Archive captures of DataSF ygmz-vaxd's CSV export, from the CDX
# index (collapse=digest, status 200) read 2026-09-22. 20251206203856 holds the
# same release as 20251208144027 (both loaded 2025-06-17) and is not repeated.
SNAPSHOT_CAPTURES = [
    ("20210325171932", "rows.csv?accessType=DOWNLOAD"),
    ("20221209021723", "rows.csv?accessType=DOWNLOAD"),
    ("20240331194201", "rows.csv?accessType=DOWNLOAD"),
    ("20251208144027", "rows.csv?accessType=DOWNLOAD"),
    ("20260215091752", "rows.csv?accessType=DOWNLOAD"),
    ("20260405114850", "rows.csv?accessType=DOWNLOAD"),
]
WAYBACK = "https://web.archive.org/web/%sid_/https://data.sfgov.org/api/views/ygmz-vaxd/%s"
DATASF = "https://data.sf.gov/resource/%s.json?%s"
SLOW_STREETS_ID = "hkz3-itiu"
# SFMTA's Slow Streets Program page (sfmta.com, read 2026-09-22) says the
# Board approved the program on December 6, 2022; the Board record itself is
# [unretrieved — verify]. Segments the dataset dates to 1899 (its null) are
# counted from this year.
SLOW_STREETS_APPROVED = 2022
BLOCKS_2020_ID = "p2fw-hsrv"
TIGER_2010 = ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
              "tigerWMS_Census2010/MapServer/18/query")
CEDSCI = "https://data.census.gov/api/access/data/table?id=ACSDT5Y%d.B01003&g=050XX00US06075$1500000"
ACS_YEARS = list(range(2015, 2025))
CDE_CAPTURE = ("https://web.archive.org/web/20251005140551id_/"
               "https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=xlsx&ict=Y")
CDE_FILE_DATE = "2025-10-05"
FACILITIES_ID = "nc68-ngbr"
SCHOOLS_ID = "7e7j-59qk"
# Private K-12 schools from DataSF's Schools (Bryan, 2026-09-29: "please
# include private K-12 schools, and let's label it as such (i.e. "K-12") in our
# map"). Private kindergartens are left out. The dataset lists active schools
# only, so each is dated from its open_date and one that closed earlier is
# missing from earlier years.
PRIVATE_TYPES = {"Elementary School (Private)", "K-12 Schools (Private)", "High Schools (Private)"}
# A private row within this distance of a counted CDE school is the same school.
SAME_SCHOOL_M = 30.0

# The one branch closure inside the window. SFPL, release of 2022-06-13: "The
# Mission Branch Library has remained closed since the shutdown in March 2020."
# SFPL, Mission Branch Library renovation page, read 2026-09-22: "Opening: Fall
# 2026", status "In construction". Its temporary site at 1234 Valencia St opened
# 2022-06-18 and is not counted as the branch.
LIBRARY_CLOSURES = {
    "Mission Branch Library": {"closed_from": 2020, "reopens": None,
                               "source": "https://sfpl.org/releases/2022/06/13/san-francisco-public-library-opens-new-temporary-library-site-mission-saturday"},
}
NOT_A_BRANCH = {"Library Support Services"}

OUT = os.path.join(ROOT, "out", "bike-network-history")
SITE_OUT = os.path.join(ROOT, "site", "data", "bike-history", "segments.json")

MILE = 1609.344
# The three distances the page offers, in metres. One block is 440 feet and
# two are 880 (Bryan, 2026-09-29: "let's use ~440 feet for
# 1 block and ~880 feet for 2 blocks"). pipeline/sources/sf-block-length.py measures
# the population-weighted typical block, intersection to intersection on the
# city's street centerline, weighted by census tract population; BLOCK_SOURCE
# carries its figure, and the explorer's feet stay at Bryan's round numbers
# while the measured one is within 10% of them.
FT = 0.3048
BLOCK_FT = 440
ITDP_FT = 1000
_bl = json.load(open(os.path.join(ROOT, "out", "block-length", "summary.json")))
BLOCK_SOURCE = {"measured_ft": _bl["pop_weighted_mean_ft"], "used_ft": BLOCK_FT, "tracts": _bl["tracts"],
                "blocks": _bl["chain"]["blocks"], "read": _bl["centerline"]["queried"],
                "url": _bl["centerline"]["url"], "census_url": _bl["census"]["url"],
                "script": "pipeline/sources/sf-block-length.py",
                "source": "DataSF street centerlines (3psu-pn9h) and Census 2020 blocks (p2fw-hsrv)",
                "rounding": "one block is taken as %d feet and two as %d, Bryan's figures; the measured typical block is %d feet" % (
                    BLOCK_FT, 2 * BLOCK_FT, _bl["pop_weighted_mean_ft"])}
assert abs(_bl["pop_weighted_mean_ft"] - BLOCK_FT) <= 0.10 * BLOCK_FT, "measured block %s ft is more than 10%% from %d ft; ask Bryan" % (_bl["pop_weighted_mean_ft"], BLOCK_FT)
REACH_THRESHOLDS = [
    {"id": "quarter", "metres": REACH_MILES * MILE, "label": "Quarter mile", "short": "a quarter mile", "basis": "the plan's distance (printed p. 24; Appendix G)"},
    {"id": "block", "metres": BLOCK_FT * FT, "label": "1 block", "short": "about one block (%d feet)" % BLOCK_FT, "basis": "one typical San Francisco block"},
    {"id": "2blocks", "metres": 2 * BLOCK_FT * FT, "label": "2 blocks", "short": "about two blocks (%d feet)" % (2 * BLOCK_FT), "basis": "two typical San Francisco blocks"},
    # Bryan, 2026-10-06: "Can you add 1000 feet to the explorer?" The SF bike
    # post compares San Francisco with Montreal at about 1,000 feet, the ITDP
    # Atlas's 300 m walk to a protected bikeway. Appended rather than sorted in,
    # so reach.json's existing columns keep their places; the explorer sorts
    # the distances itself.
    {"id": "1000ft", "metres": ITDP_FT * FT, "label": "1,000 feet", "short": "1,000 feet", "basis": "the distance the post uses for Montreal's ITDP figure (ITDP Atlas of Sustainable City Transport, 300 m)"},
]
DEFAULT_REACH = "quarter"
RANK ={"CLASS III": 1, "CLASS II": 2, "CLASS IV": 3, "CLASS I": 4}
CODE = {None: "0", "CLASS I": "1", "CLASS II": "2", "CLASS III": "3", "CLASS IV": "4", "SLOW": "S", "UNKNOWN": "?"}
LAT0 = math.radians(37.76)


# ---------------------------------------------------------------------------
# Geometry, in metres, flat around San Francisco
# ---------------------------------------------------------------------------

def xy(lon, lat):
    return (math.radians(lon) * math.cos(LAT0) * 6371008.8, math.radians(lat) * 6371008.8)


def line_miles(pts):
    """Miles along points already projected by xy(): the formula of
    mile_basis.line_metres, so a row measured here and a row measured by
    lib/plan_directions.py come out the same."""
    m = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        m += math.hypot(x2 - x1, y2 - y1)
    return m / MILE


def wkt_points(w):
    """[[lon, lat], ...] from a LINESTRING or MULTILINESTRING, parts joined."""
    out = []
    for chunk in re.findall(r"\(([^()]*)\)", w or ""):
        for pair in chunk.split(","):
            v = pair.split()
            if len(v) == 2:
                try:
                    out.append([round(float(v[0]), 6), round(float(v[1]), 6)])
                except ValueError:
                    pass
    return out


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Reach(object):
    """Is a point within REACH of any line? A grid of REACH-sized cells.

    `lines` is a list of point lists, or of (key, points) pairs; a key is
    what nearest() hands back, so a newly reached school can be tied to the
    block that reached it."""

    def __init__(self, lines, reach_m):
        self.r = reach_m
        self.cells = collections.defaultdict(list)
        for item in lines:
            key, pts = item if isinstance(item, tuple) else (None, item)
            P = [xy(lon, lat) for lon, lat in pts]
            for a, b in zip(P, P[1:]):
                x0, x1 = sorted((a[0], b[0]))
                y0, y1 = sorted((a[1], b[1]))
                for cx in range(int(x0 // reach_m), int(x1 // reach_m) + 1):
                    for cy in range(int(y0 // reach_m), int(y1 // reach_m) + 1):
                        self.cells[(cx, cy)].append((a[0], a[1], b[0], b[1], key))

    def within(self, lon, lat):
        px, py = xy(lon, lat)
        cx, cy = int(px // self.r), int(py // self.r)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for ax, ay, bx, by, _ in self.cells.get((cx + i, cy + j), ()):
                    if seg_dist(px, py, ax, ay, bx, by) <= self.r:
                        return True
        return False

    def nearest(self, lon, lat):
        """(key, metres) of the nearest line within reach, else (None, None)."""
        px, py = xy(lon, lat)
        cx, cy = int(px // self.r), int(py // self.r)
        best_k, best_d = None, None
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for ax, ay, bx, by, k in self.cells.get((cx + i, cy + j), ()):
                    d = seg_dist(px, py, ax, ay, bx, by)
                    if d <= self.r and (best_d is None or d < best_d):
                        best_k, best_d = k, d
        return best_k, best_d


# ---------------------------------------------------------------------------
# Fetchers (each runs only when its extract is missing or --refetch is set)
# ---------------------------------------------------------------------------

def get(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "sf-works/0.1 (research; bike-network-history)"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        data = fh.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def fetch_geometry():
    """Every row's line geometry from SFMTA's layer, 6 decimal places."""
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "outFields": "OBJECTID,CNN", "returnGeometry": "true",
                                    "outSR": 4326, "orderByFields": "OBJECTID", "resultOffset": offset,
                                    "resultRecordCount": 2000, "f": "json"})
        d = json.loads(get("%s/query?%s" % (SERVICE, q)))
        feats = d.get("features", [])
        for f in feats:
            if not (f.get("geometry") or {}).get("paths"):
                continue  # an empty record with no line (see fetch_layer in bike-progress.py)
            pts = [[round(x, 6), round(y, 6)] for path in f["geometry"]["paths"] for x, y in path]
            out.append({"oid": f["attributes"]["OBJECTID"], "cnn": f["attributes"]["CNN"], "pts": pts})
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    if len(out) < 5000:
        raise RuntimeError("bikeway geometry returned %d rows; expected about 5,457" % len(out))
    return out


def fetch_bci():
    """Every segment's Bike Comfort Index, attributes only, paged by 2,000.

    traffic_ft/tf is the layer's traffic rating per direction (Light, Medium or
    Heavy Traffic), read by scripts/school-budget-value.py to price busy blocks."""
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"where": "1=1", "returnGeometry": "false", "orderByFields": "cnn_sgmt_pkey",
                                    "outFields": "cnn_sgmt_pkey,bci,bci_ft,bci_tf,lts_segment_ft,lts_segment_tf,"
                                                 "traffic_category_ft,traffic_category_tf",
                                    "resultOffset": offset, "resultRecordCount": 2000, "f": "json"})
        d = json.loads(get("%s/query?%s" % (BCI_SERVICE, q)))
        feats = [f["attributes"] for f in d.get("features", [])]
        out += [{"cnn": str(r["cnn_sgmt_pkey"]), "bci": r["bci"], "bci_ft": r["bci_ft"], "bci_tf": r["bci_tf"],
                 "lts_ft": r["lts_segment_ft"], "lts_tf": r["lts_segment_tf"],
                 "traffic_ft": r["traffic_category_ft"], "traffic_tf": r["traffic_category_tf"]} for r in feats]
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    if len(out) < 15000:
        raise RuntimeError("BCI layer returned %d rows; expected 15,280" % len(out))
    return out


def fetch_snapshot(stamp, tail, live_cnns):
    """One archived CSV export, reduced to the columns this script reads.
    Geometry is kept for rows with no CNN (off-street paths, keyed by their
    endpoints) and for blocks the live layer no longer carries; every other
    block is measured from the live geometry."""
    text = get(WAYBACK % (stamp, tail)).decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) < 5000:
        raise RuntimeError("capture %s parsed to %d rows; expected about 5,300" % (stamp, len(rows)))
    out = []
    for r in rows:
        cnn = (r.get("CNN") or "").strip().lstrip("0")
        out.append({
            "cnn": cnn or None, "cls": (r.get("FACILITY_T") or "").strip() or None,
            "dir": r.get("DIR"), "len_mi": float(r["LENGTH"]) if (r.get("LENGTH") or "").strip() else None,
            "inst_yr": r.get("INSTALL_YR") or None, "inst_mo": r.get("INSTALL_MO") or None,
            "upd_yr": r.get("UPDATE_YR") or None, "upd_mo": r.get("UPDATE_MO") or None,
            "street": (r.get("STREETNAME") or "").strip() or None, "from": r.get("FROM_ST"), "to": r.get("TO_ST"),
            "notes": (r.get("NOTES") or "").strip() or None,
            "pts": wkt_points(r.get("shape") or r.get("the_geom")) if (not cnn or cnn not in live_cnns) else None,
        })
    loaded = rows[0].get("data_loaded_at") or None
    return out, loaded


def fetch_datasf(fxf, params, floor):
    rows = json.loads(get(DATASF % (fxf, urllib.parse.urlencode(params))))
    if len(rows) < floor:
        raise RuntimeError("%s returned %d rows; expected at least %d" % (fxf, len(rows), floor))
    return rows


def fetch_blocks_2010():
    q = urllib.parse.urlencode({"where": "STATE='06' AND COUNTY='075'", "returnGeometry": "false",
                                "outFields": "GEOID,POP100,HU100,INTPTLAT,INTPTLON", "f": "json"})
    d = json.loads(get(TIGER_2010 + "?" + q))
    if d.get("exceededTransferLimit"):
        raise RuntimeError("TIGERweb 2010 blocks truncated")
    out = [{"geoid": a["GEOID"], "pop": int(a["POP100"]), "hu": int(a["HU100"]),
            "lat": float(a["INTPTLAT"]), "lon": float(a["INTPTLON"])}
           for a in (f["attributes"] for f in d["features"])]
    if len(out) < 7000:
        raise RuntimeError("TIGERweb returned %d 2010 blocks; expected about 7,386" % len(out))
    return out


def fetch_blocks_2020():
    rows = fetch_datasf(BLOCKS_2020_ID, {"$select": "geoid20,intptlat20,intptlon20,pop20,housing20",
                                         "$limit": 50000, "$order": "geoid20"}, 5000)
    # DataSF stores geoid20 as a number, so the leading zero of state 06 is gone.
    return [{"geoid": r["geoid20"].zfill(15), "pop": int(float(r.get("pop20") or 0)),
             "hu": int(float(r.get("housing20") or 0)),
             "lat": float(r["intptlat20"]), "lon": float(r["intptlon20"])} for r in rows]


def fetch_acs():
    out = []
    for y in ACS_YEARS:
        d = json.loads(get(CEDSCI % y))["response"]["data"]
        hdr = d[0]
        gi, ei = hdr.index("GEO_ID"), hdr.index("B01003_001E")
        rows = [{"year": y, "bg": r[gi].split("US")[1], "pop": int(r[ei])} for r in d[1:] if r[ei] not in (None, "")]
        if len(rows) < 500:
            raise RuntimeError("ACS %d returned %d block groups; expected about 580 to 680" % (y, len(rows)))
        out += rows
    return out


def fetch_slow_streets():
    rows = fetch_datasf(SLOW_STREETS_ID, {"$limit": 50000, "$order": "objectid"}, 200)
    out, seen = [], set()
    for r in rows:
        rec = {"cnn": str(int(float(r["cnn"]))) if r.get("cnn") else None, "street": r.get("streetname"),
               "extents": r.get("extents"), "status": r.get("status"), "phase": r.get("phase"),
               "install_date": (r.get("install_date") or "")[:10] or None,
               "len_mi": float(r["length"]) if r.get("length") else None,
               "pts": [[round(x, 6), round(y, 6)] for x, y in (r.get("shape") or {}).get("coordinates", [])]}
        # The dataset carries four Golden Gate Ave blocks (Masonic to Parker,
        # phase 2) twice under two objectids, identical in every other field
        # (checked 2026-09-28). One block is one block: counting both would
        # add their length to the Slow Streets miles twice.
        k = json.dumps(rec, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(rec)
    if len(out) < len(rows):
        print(f"  slow streets: {len(rows) - len(out)} rows repeat another row exactly; kept once", file=sys.stderr)
    return out


def fetch_cde_schools():
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(get(CDE_CAPTURE, timeout=600)), read_only=True)
    ws = wb[wb.sheetnames[0]]
    hdr, out = None, []
    for r in ws.iter_rows(values_only=True):
        if hdr is None:
            if r and "CDSCode" in [str(x) for x in r]:
                hdr = [str(x) for x in r]
            continue
        d = dict(zip(hdr, r))
        if d.get("County") != "San Francisco":
            continue

        def day(v):
            return v.date().isoformat() if isinstance(v, dt.datetime) else (str(v)[:10] if v and str(v) != "No Data" else None)

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        out.append({"cds": str(d.get("CDSCode")), "school": d.get("School"), "district": d.get("District"),
                    "status": d.get("StatusType"), "open": day(d.get("OpenDate")), "closed": day(d.get("ClosedDate")),
                    "charter": d.get("Charter"), "soc_type": d.get("SOCType"), "grades": d.get("GSoffered"),
                    "virtual": d.get("Virtual"), "lat": num(d.get("Latitude")), "lon": num(d.get("Longitude"))})
    if len(out) < 200:
        raise RuntimeError("CDE capture parsed to %d San Francisco rows; expected about 266" % len(out))
    return out


def fetch_libraries():
    rows = fetch_datasf(FACILITIES_ID, {"$where": "upper(department_name) like '%LIBRAR%'", "$limit": 500}, 25)
    out = []
    for r in rows:
        name = r.get("common_name")
        if name in NOT_A_BRANCH:
            continue
        c = LIBRARY_CLOSURES.get(name, {})
        out.append({"name": name, "facility_id": r.get("facility_id"), "address": r.get("address"),
                    "lat": float(r["latitude"]), "lon": float(r["longitude"]),
                    "closed_from": c.get("closed_from"), "reopens": c.get("reopens"), "closure_source": c.get("source")})
    return out


# ---------------------------------------------------------------------------
# The network, year by year
# ---------------------------------------------------------------------------

def yr(v):
    try:
        y = int(float(v))
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= 2100 else None


class PathRegistry(object):
    """Keys for rows with no CNN. OBJECTIDs are renumbered between captures,
    so the geometry is the only thing that identifies an off-street path: a
    path is the same path when both endpoints fall within PATH_TOLERANCE_M of
    an already-registered one (the DataSF export and the ArcGIS layer place
    the same line about 9 m apart). The live layer registers first, so its
    keys are canonical."""

    PATH_TOLERANCE_M = 25

    def __init__(self):
        self.entries = []  # (key, (x1, y1), (x2, y2))

    def key(self, pts):
        if not pts:
            return None
        a, b = xy(*pts[0]), xy(*pts[-1])
        for k, ea, eb in self.entries:
            if (max(math.hypot(a[0] - ea[0], a[1] - ea[1]), math.hypot(b[0] - eb[0], b[1] - eb[1])) <= self.PATH_TOLERANCE_M
                    or max(math.hypot(a[0] - eb[0], a[1] - eb[1]), math.hypot(b[0] - ea[0], b[1] - ea[1])) <= self.PATH_TOLERANCE_M):
                return k
        k = "P:%.5f,%.5f|%.5f,%.5f" % (pts[0][0], pts[0][1], pts[-1][0], pts[-1][1])
        self.entries.append((k, a, b))
        return k


PATHS = PathRegistry()


def path_key(pts):
    return PATHS.key(pts)


def is_presidio(notes):
    return bool(notes) and "PRES" in notes.upper()


def per_cnn(rows, measure):
    """One record per block from a snapshot's rows: its direction rows as
    (class, miles) pairs, the row miles summed (`mi`, the plan's unit), the
    block's centreline miles (`cl_mi`, one length per block), and its
    install/update years. A block is a CNN, or for the off-street paths that
    carry none, a path_key. `measure(k, rs)` returns (per-row miles, centreline)."""
    by = collections.defaultdict(list)
    for r in rows:
        if not r["cls"]:
            continue
        k = r["cnn"] or path_key(r.get("pts"))
        if k:
            by[k].append(r)
    out = {}
    for k, rs in by.items():
        row_mi, cl_mi = measure(k, rs)
        dir_rows = [(r["cls"], m) for r, m in zip(rs, row_mi)]
        inst = [yr(r["inst_yr"]) for r in rs if yr(r["inst_yr"])]
        upd = [yr(r["upd_yr"]) for r in rs if yr(r["upd_yr"])]
        out[k] = {"classes": frozenset(r["cls"] for r in rs), "rows": dir_rows, "mi": sum(row_mi), "cl_mi": cl_mi,
                  "inst": min(inst) if inst else None, "upd": max(upd) if upd else None,
                  "street": rs[0].get("street"), "from": rs[0].get("from"), "to": rs[0].get("to"),
                  "presidio": any(is_presidio(r.get("notes")) for r in rs), "path": not rs[0]["cnn"]}
    return out


def row_qualifies(cls, bci_score, calmed=False):
    """The plan's high-quality test for one direction row. `calmed` is whether
    the block has traffic calming by the year in question; only Class III
    needs it."""
    if cls in PLAN_ALL_AGES_CLASSES:
        return True
    # A Class II or III row on a block with no BCI score does not qualify:
    # the test cannot be run, and an untestable row is counted as failing.
    # The blocks and miles this touches are counted separately (bci.unscored).
    if cls not in PLAN_BCI_CLASSES or bci_score is None or bci_score <= PLAN_BCI_THRESHOLD:
        return False
    return cls != "CLASS III" or calmed


def qualifying_miles(rows, bci_score, strict=False, calmed=False):
    """Row miles on a block that meet the plan's test (or, strict, that are
    Class I or IV). None rows (class unknown) give 0."""
    if not rows:
        return 0.0
    if strict:
        return sum(m for c, m in rows if c in PLAN_ALL_AGES_CLASSES)
    return sum(m for c, m in rows if row_qualifies(c, bci_score, calmed))


def best(classes):
    return max(classes, key=lambda c: RANK.get(c, 0)) if classes else None


def state_in_year(Y, snaps):
    """{cnn: {"classes": frozenset|None, "mi": float, "basis": str}} for year Y.

    A segment's class in Y is its class in the nearest snapshot captured after
    the end of Y, unless UPDATE_YR says the change came after Y, in which case
    it is the class in the nearest earlier snapshot (or unknown when there is
    none). Existence in Y needs INSTALL_YR <= Y, or a blank INSTALL_YR.
    Segments present in the earlier snapshot and gone from the later one are
    counted through Y (the removal's date inside the gap is unknown).
    """
    end = dt.date(Y, 12, 31)
    later = next((s for s in snaps if s["date"] > end), snaps[-1])
    earlier = next((s for s in reversed(snaps) if s["date"] <= end), None)
    out, notes = {}, collections.Counter()
    for cnn, rec in later["cnns"].items():
        inst = rec["inst"]
        if rec["presidio"] and not INCLUDE_PRESIDIO:
            continue
        if inst is not None and inst > Y:
            continue
        if inst is None:
            notes["undated install, assumed present"] += 1
        if earlier and cnn not in earlier["cnns"] and inst is not None and inst <= earlier["date"].year:
            notes["INSTALL_YR predates a snapshot that lacks the block"] += 1
        classes, dir_rows, mi, basis = rec["classes"], rec["rows"], rec["mi"], "later snapshot"
        if rec["upd"] is not None and rec["upd"] > Y:
            if earlier and cnn in earlier["cnns"]:
                e = earlier["cnns"][cnn]
                classes, dir_rows, mi, basis = e["classes"], e["rows"], e["mi"], "earlier snapshot (UPDATE_YR after Y)"
            else:
                # The block existed with an unknown class; its row count is
                # taken from the later capture so its miles stay in the total.
                classes, dir_rows, basis = None, None, "unknown (UPDATE_YR after Y, no earlier snapshot)"
                notes["class unknown before a later upgrade"] += 1
        elif earlier and cnn in earlier["cnns"] and earlier["cnns"][cnn]["classes"] != classes and rec["upd"] is None:
            notes["class changed between snapshots with no UPDATE_YR"] += 1
        out[cnn] = {"classes": classes, "rows": dir_rows, "mi": mi, "cl_mi": rec["cl_mi"], "basis": basis,
                    "later_classes": rec["classes"], "later_rows": rec["rows"],
                    "inst": inst, "presidio": rec["presidio"], "path": rec["path"]}
    if earlier:
        for cnn, rec in earlier["cnns"].items():
            if rec["presidio"] and not INCLUDE_PRESIDIO:
                continue
            if cnn not in later["cnns"] and cnn not in out:
                out[cnn] = {"classes": rec["classes"], "rows": rec["rows"], "mi": rec["mi"], "cl_mi": rec["cl_mi"],
                            "basis": "earlier snapshot (removed before the later one)",
                            "later_classes": None, "later_rows": None, "inst": rec["inst"], "presidio": rec["presidio"], "path": rec["path"]}
                notes["present earlier, gone later: counted through Y"] += 1
    return out, later, earlier, notes


def alias_paths(snaps, pts_of):
    """A block that carries a CNN in one capture and none in another (Lake
    Merced Blvd's CLASS I blocks lose theirs from the 2025 captures on) is one
    block. Any path key whose endpoints match a CNN block's within the path
    tolerance is renamed to that CNN in every capture. Returns the aliases."""
    cnn_keys = {k for s in snaps for k in s["cnns"] if not k.startswith("P:")}
    path_keys = {k for s in snaps for k in s["cnns"] if k.startswith("P:")}
    ends = {}
    for k in cnn_keys:
        p = pts_of.get(k)
        if p:
            ends[k] = (xy(*p[0]), xy(*p[-1]))
    tol = PathRegistry.PATH_TOLERANCE_M
    alias = {}
    for pk in path_keys:
        p = pts_of.get(pk)
        if not p:
            continue
        a, b = xy(*p[0]), xy(*p[-1])
        for k, (ea, eb) in ends.items():
            if (max(math.hypot(a[0] - ea[0], a[1] - ea[1]), math.hypot(b[0] - eb[0], b[1] - eb[1])) <= tol
                    or max(math.hypot(a[0] - eb[0], a[1] - eb[1]), math.hypot(b[0] - ea[0], b[1] - ea[1])) <= tol):
                alias[pk] = k
                break
    for s in snaps:
        for pk, k in alias.items():
            if pk in s["cnns"]:
                rec = s["cnns"].pop(pk)
                if k in s["cnns"]:
                    # The same block twice in one capture, once with its CNN
                    # and once without: both records' rows are the block's.
                    t = s["cnns"][k]
                    t["rows"] = (t["rows"] or []) + (rec["rows"] or [])
                    t["mi"] += rec["mi"]
                    t["cl_mi"] = max(t["cl_mi"], rec["cl_mi"])
                    t["classes"] = frozenset(t["classes"] | rec["classes"])
                    if rec["inst"] is not None:
                        t["inst"] = rec["inst"] if t["inst"] is None else min(t["inst"], rec["inst"])
                    if rec["upd"] is not None:
                        t["upd"] = rec["upd"] if t["upd"] is None else max(t["upd"], rec["upd"])
                    t["presidio"] = t["presidio"] or rec["presidio"]
                else:
                    rec["path"] = False
                    s["cnns"][k] = rec
    return alias


def fill_gaps(snaps):
    """A block present in an earlier and a later capture but missing from one
    between is carried through the gap with its earlier record, because a
    removal and reinstatement of the same block inside the gap is less likely
    than a capture that dropped it. Returns fills per capture."""
    keys = set()
    for s in snaps:
        keys |= set(s["cnns"])
    fills = collections.Counter()
    for k in keys:
        present = [i for i, s in enumerate(snaps) if k in s["cnns"]]
        for i in range(present[0], present[-1]):
            if k not in snaps[i]["cnns"]:
                prev = next(s for s in reversed(snaps[:i]) if k in s["cnns"])
                snaps[i]["cnns"][k] = dict(prev["cnns"][k], filled=True)
                fills[snaps[i]["label"]] += 1
    return fills


# A closed year's figures that a refresh must not move. A row SFMTA deletes or re-stamps today does not change what
# was on the street in an earlier year (lead's ruling, 2026-11-10); a deliberate method change reopens them with
# --reopen-closed-years.
CLOSED_FIELDS = ("network_miles", "all_ages_miles", "class_iv_miles", "blocks_all_ages")


def closed_year_check(rows, live_year, reopen):
    """Stop before writing when a year before the live layer's year has a CLOSED_FIELDS figure unlike the last run's."""
    try:
        prev = {r["year"]: r for r in json.load(open(os.path.join(OUT, "history.json"), encoding="utf-8"))["rows"]}
    except (FileNotFoundError, ValueError, KeyError):
        return
    moved = ["%d %s %s -> %s" % (r["year"], f, prev[r["year"]].get(f), r.get(f))
             for r in rows if r["year"] < live_year and r["year"] in prev
             for f in CLOSED_FIELDS if prev[r["year"]].get(f) != r.get(f)]
    if moved and not reopen:
        raise SystemExit("closed years changed, nothing written (rerun with --reopen-closed-years for a deliberate "
                         "method change):\n  " + "\n  ".join(moved))
    if moved:
        print("  closed years reopened on purpose: " + "; ".join(moved))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--reopen-closed-years", action="store_true",
                    help="allow a closed year's figures to change (a deliberate method change), which the check refuses")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.dirname(SITE_OUT), exist_ok=True)
    R = args.refetch
    sources = {}

    # -- live layer -------------------------------------------------------
    bike = Extract("sfmta-bikeway")
    live = bike.read("network")
    if live is None:
        raise SystemExit("data/extract/sfmta-bikeway/network.json is missing; run tools/bike-network/bike-progress.py --refetch first")
    geom = bike.fetch_or_read("geometry", fetch_geometry, refresh=R,
                              meta={"service": SERVICE, "note": "line geometry per row, WGS84, 6 dp; joins network.json on oid"})
    # The re-keyed rows below read their lines from this extract (bikeway_snap.GEOMETRY).
    # The layer's CNN is wrong on some rows: Class I paths on John F Kennedy
    # Drive carry Cabrillo Street CNNs up to 2.3 miles away, and 21 blocks
    # carry CNNs the centerline has retired. Every row is re-keyed to the
    # centerline block it lies on, and a row spanning several blocks is split
    # (lib/bikeway_snap.py). Everything below reads the re-keyed rows.
    # One snapper per process (bikeway_snap.shared_snapper), so the
    # plan_directions read below re-keys the same rows without a second pass.
    snapper = shared_snapper()
    live_recs = rekeyed_layer(live.records, snapper)
    print("  %d layer rows re-keyed to the block they lie on (%d rows after splitting)"
          % (len(snapper.log), len(live_recs)))
    # One geometry per block: where the direction rows carry different lines
    # (36 CNNs), the longest row's line, so a block's miles are never the
    # shorter side. Rows with no CNN are keyed by their endpoints.
    live_pts = {}
    for r in live_recs:
        p = r["_pts"]
        if not p:
            continue
        k = str(int(float(r["CNN"]))) if r.get("CNN") else path_key(p)
        if k and (k not in live_pts or line_miles([xy(*q) for q in p]) > line_miles([xy(*q) for q in live_pts[k]])):
            live_pts[k] = p
    live_cnns = {k for k in live_pts if not k.startswith("P:")}
    # Rows on a retired block no active block replaced keep their line and lose
    # their CNN. They are on-street bikeways, not paths, so they are counted
    # apart from the paths (Terry A Francois Blvd's Class IV lanes). Keyed
    # after the loop above registers every live line, so no key moves.
    retired_keys = {path_key(r["_pts"]) for r in live_recs if r.get("_snap") == "retired" and r.get("_pts")}
    sources["network"] = {"name": "SFMTA bikeway layer (ArcGIS Bicycle/bicycle, layer 0)", "url": SERVICE,
                          "queried": live.fetched_on.isoformat(), "geometry_queried": geom.fetched_on.isoformat()}

    # Each live row's own miles, from its geometry, and the mean per block:
    # the archived CSV exports carry no geometry for blocks still in the
    # layer, so a snapshot row on such a block is measured at the live
    # layer's mean row length for the block. Summing the live rows' own
    # geometry gives 472.6 miles against the plan's 472 (printed p. 20).
    live_row_mi = {}
    for r in live_recs:
        p = r["_pts"]
        if p and r.get("FACILITY_T"):
            k = str(int(float(r["CNN"]))) if r.get("CNN") else path_key(p)
            live_row_mi.setdefault(k, []).append(r["_mi"] if r["_mi"] is not None else line_miles([xy(*q) for q in p]))
    live_mean_row_mi = {k: sum(v) / len(v) for k, v in live_row_mi.items()}

    # A row SFMTA deleted from the live layer keeps its last line and row length, so the closed years it was in keep
    # their miles (lib/bikeway_departed.py). Only a block with no live row left takes them; the live year
    # (built from live_rows below) does not carry it. On a block that keeps some live rows, the departed rows join
    # the mean row length and the longest line, as they did while they were live, so the captures measure the block
    # as before.
    departed = bikeway_departed.load()
    departed_rows = []
    if departed:
        dep_recs = rekeyed_layer([d["row"] for d in departed], snapper,
                                 pts_by_oid={d["oid"]: d["pts"] for d in departed if d.get("pts")})
        dep_row_mi = {}
        for r in dep_recs:
            p = r["_pts"]
            if not p or not r.get("FACILITY_T"):
                continue
            k = str(int(float(r["CNN"]))) if r.get("CNN") else path_key(p)
            if not k:
                continue
            dep_row_mi.setdefault(k, []).append(r["_mi"] if r["_mi"] is not None else line_miles([xy(*q) for q in p]))
            if k not in live_pts or line_miles([xy(*q) for q in p]) > line_miles([xy(*q) for q in live_pts[k]]):
                live_pts[k] = p
        for k, v in dep_row_mi.items():
            both = live_row_mi.get(k, []) + v
            live_mean_row_mi[k] = sum(both) / len(both)
        when = {d["oid"]: d["departed"] for d in departed}
        departed_rows = sorted(({"oid": d["oid"], "departed": when[d["oid"]], "cnn": d["row"].get("CNN") and str(int(float(d["row"]["CNN"]))),
                                 "street": d["row"].get("STREETNAME"), "from": d["row"].get("FROM_ST"), "to": d["row"].get("TO_ST"),
                                 "class": d["row"].get("FACILITY_T")} for d in departed), key=lambda x: x["oid"])
        print("  %d row(s) SFMTA deleted from the layer keep their line for closed years, on %d block(s): %s"
              % (len(departed), len(dep_row_mi), ", ".join(sorted({"%s %s-%s" % (x["street"], x["from"], x["to"]) for x in departed_rows}))))

    def measure(cnn, rows):
        """(per-row miles, centreline miles) for one block's rows in one
        capture. A row is measured by its own geometry when the capture kept
        one, else at the live layer's mean row length for the block, else by
        its LENGTH column. Centreline is one length per block: the live
        geometry when the block is still in the layer, else the longest row."""
        per_row = []
        for r in rows:
            if r.get("mi") is not None:
                per_row.append(r["mi"])  # a re-keyed piece's share of its row
            elif r.get("pts"):
                per_row.append(line_miles([xy(*p) for p in r["pts"]]))
            elif cnn in live_mean_row_mi:
                per_row.append(live_mean_row_mi[cnn])
            else:
                per_row.append(float(r["len_mi"] or 0.0))
        if cnn in live_pts:
            cl = line_miles([xy(*p) for p in live_pts[cnn]])
        else:
            cl = max(per_row or [0.0])
        return per_row, cl

    live_rows = [{"cnn": str(int(float(r["CNN"]))) if r.get("CNN") else None, "cls": r.get("FACILITY_T"), "dir": r.get("DIRECT"),
                  "len_mi": r.get("LENGTH"), "inst_yr": r.get("INSTALL_YR"), "upd_yr": r.get("UPDATE_YR"),
                  "street": (r.get("STREETNAME") or "").strip() or None, "from": r.get("FROM_ST"), "to": r.get("TO_ST"),
                  "notes": r.get("NOTES"), "pts": r["_pts"], "mi": r["_mi"]}
                 for r in live_recs]

    # -- archived snapshots ---------------------------------------------------
    snaps = []
    arch = Extract("bikeway-snapshots")
    for stamp, tail in SNAPSHOT_CAPTURES:
        key = stamp[:8]
        r = arch.read(key)
        if r is None or R:
            rows, loaded = fetch_snapshot(stamp, tail, live_cnns)
            r = arch.write(key, rows, meta={"wayback": WAYBACK % (stamp, tail), "captured": stamp,
                                              "geometry": "kept for rows with no CNN and for blocks absent from the live layer at extract time",
                                              "data_loaded_at": loaded, "dataset": "https://data.sf.gov/d/ygmz-vaxd"})
        d = dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        cap_rows = snapper.snapshot_rows(r.records)
        snaps.append({"date": d, "label": d.isoformat(), "kind": "archive", "cnns": per_cnn(cap_rows, measure),
                      "url": r.meta["wayback"], "loaded": r.meta.get("data_loaded_at"), "fetched": r.fetched_on.isoformat()})
        for row in cap_rows:
            if row.get("pts"):
                k = row["cnn"] or path_key(row["pts"])
                if k and (k not in live_pts or line_miles([xy(*q) for q in row["pts"]]) > line_miles([xy(*q) for q in live_pts[k]])):
                    live_pts[k] = row["pts"]
    snaps.append({"date": live.fetched_on, "label": live.fetched_on.isoformat(), "kind": "live",
                  "cnns": per_cnn(live_rows, measure), "url": SERVICE, "loaded": None, "fetched": live.fetched_on.isoformat()})
    snaps.sort(key=lambda s: s["date"])
    # A block's ends are its own centerline's ends where the centerline carries
    # it, not a row's line: a split row's piece can end short of the block, and
    # a 16 m connector path past Saint Charles Ave's south end matched the
    # piece's ends though it lies on no block.
    ends_of = {k: (snapper.cl.lonlat.get(k) or p) if not k.startswith("P:") else p for k, p in live_pts.items()}
    aliases = alias_paths(snaps, ends_of)
    for pk, k in aliases.items():
        if pk in live_pts:
            live_pts.setdefault(k, live_pts[pk])
    print("  %d paths without a CNN matched a CNN block's geometry and were merged into it" % len(aliases))
    fills = fill_gaps(snaps)
    path_keys_live = {k for k in snaps[-1]["cnns"] if k.startswith("P:")}
    path_keys_first = {k for k in snaps[0]["cnns"] if k.startswith("P:")}
    print("  off-street paths without a CNN: %d in the live layer, %d in the first capture, %d in both (keyed by endpoints)"
          % (len(path_keys_live), len(path_keys_first), len(path_keys_live & path_keys_first)))
    sources["snapshots"] = [{"captured": s["label"], "kind": s["kind"], "url": s["url"], "data_loaded_at": s["loaded"],
                             "fetched": s["fetched"], "blocks": len(s["cnns"]),
                             "rows": sum(len(v["rows"]) for v in s["cnns"].values()),
                             "row_miles": round(sum(v["mi"] for v in s["cnns"].values()), 1),
                             "centerline_miles": round(sum(v["cl_mi"] for v in s["cnns"].values()), 1),
                             "blocks_filled_through_gap": fills.get(s["label"], 0),
                             "row_miles_LENGTH_column": None} for s in snaps]
    # The layer's two length columns, summed over every row, beside the
    # geometry: LENGTH (miles) and LENGTH_FT disagree with each other by three
    # miles, and the plan's 472 sits between the geometry and LENGTH_FT.
    row_sum = sum(float(r.get("LENGTH") or 0) for r in live.records)
    row_sum_ft = sum(float(r.get("LENGTH_FT") or 0) for r in live.records) / 5280
    row_sum_iv = sum(float(r.get("LENGTH") or 0) for r in live.records if r.get("FACILITY_T") in ("CLASS IV",))
    row_sum_iv_contraflow = sum(float(r.get("LENGTH") or 0) for r in live.records if r.get("FACILITY_T") == "CLASS IV" and r.get("CONTRAFLOW") == "YES")
    # Blocks the layer holds as one row marked two-way (DIRECT=2W): two-way
    # paths and two-way protected lanes. Row counting gives them one length
    # where a street with a lane each way gets two.
    live_by_cnn = collections.defaultdict(list)
    for r in live_recs:
        if r.get("CNN") and r.get("FACILITY_T"):
            live_by_cnn[str(int(float(r["CNN"])))].append(r)
    single_2w = [rs[0] for rs in live_by_cnn.values() if len(rs) == 1 and (rs[0].get("DIRECT") or "").upper() == "2W"]
    single_2w_note = {"blocks": len(single_2w), "row_miles": round(sum(float(r.get("LENGTH") or 0) for r in single_2w), 1),
                      "by_class": dict(collections.Counter(r["FACILITY_T"] for r in single_2w)),
                      "note": "live blocks held as one row marked DIRECT=2W; counted once, as the plan's row sum counts them"}
    sources["snapshots"][-1]["row_miles_LENGTH_column"] = round(row_sum, 1)
    sources["snapshots"][-1]["row_miles_LENGTH_FT_column"] = round(row_sum_ft, 1)

    # -- bike comfort index (for the plan's definition) ---------------------
    bci_ex = Extract("sfmta-bci").fetch_or_read("scores", fetch_bci, refresh=R,
                                                meta={"service": BCI_SERVICE, "layer": "2023 Draft Bike Comfort Index, Toole Design / SFMTA",
                                                      "note": "attributes only; key cnn_sgmt_pkey is a CNN"})
    bci = {r["cnn"]: r[PLAN_BCI_FIELD] for r in bci_ex.records if r.get(PLAN_BCI_FIELD) is not None}
    bci_dir = {r["cnn"]: (r.get("bci_ft"), r.get("bci_tf")) for r in bci_ex.records}
    live_cnn_blocks = {k for k in snaps[-1]["cnns"] if not k.startswith("P:")}
    # The combined `bci` is the block minimum of the two directional scores on
    # most segments, so it is the stricter reading. The sensitivity: live
    # Class II and III rows whose verdict would change if the plan meant one
    # directional score instead of the combined one.
    is_min = sum(1 for c, (ft, tf) in bci_dir.items() if ft is not None and tf is not None and bci.get(c) == min(ft, tf))
    flip_rows, flip_mi = 0, 0.0
    unscored_blocks, unscored_rows, unscored_mi = set(), 0, 0.0
    for c in live_cnn_blocks:
        rows_c = snaps[-1]["cnns"][c]["rows"] or []
        bci_rows = [(cls, m) for cls, m in rows_c if cls in PLAN_BCI_CLASSES]
        if not bci_rows:
            continue
        if c not in bci:
            unscored_blocks.add(c)
            unscored_rows += len(bci_rows)
            unscored_mi += sum(m for _, m in bci_rows)
            continue
        base = bci[c] > PLAN_BCI_THRESHOLD
        for d in bci_dir.get(c, (None, None)):
            if d is not None and (d > PLAN_BCI_THRESHOLD) != base:
                flip_rows += len(bci_rows)
                flip_mi += sum(m for _, m in bci_rows)
                break
    sources["bci"] = {"name": bci_ex.meta["layer"], "url": BCI_SERVICE, "queried": bci_ex.fetched_on.isoformat(),
                      "segments": len(bci_ex.records), "field": PLAN_BCI_FIELD, "threshold": PLAN_BCI_THRESHOLD,
                      "bikeway_blocks_with_a_score": len(live_cnn_blocks & set(bci)), "bikeway_blocks_with_cnn": len(live_cnn_blocks),
                      "combined_is_directional_minimum_segments": is_min,
                      "directional_sensitivity": {"class_ii_iii_rows_that_flip": flip_rows, "miles": round(flip_mi, 1),
                                                  "note": "live Class II/III rows whose verdict changes under bci_ft or bci_tf in place of the combined bci"},
                      "unscored": {"bikeway_blocks_with_class_ii_iii_rows": len(unscored_blocks), "rows": unscored_rows, "miles": round(unscored_mi, 1),
                                   "note": "Class II/III rows on bikeway blocks with no BCI score; counted as not qualifying"},
                      "note": "one 2023 snapshot, labelled draft; held fixed for every year"}
    print("  BCI: combined score is the directional minimum on %d of %d segments; %d live Class II/III rows (%.1f mi) flip under one directional score; "
          "%d bikeway blocks with Class II/III rows carry no score (%d rows, %.1f mi), counted as not qualifying"
          % (is_min, len(bci_ex.records), flip_rows, flip_mi, len(unscored_blocks), unscored_rows, unscored_mi))

    def score(c):
        """A block's BCI, or None for an off-street path with no CNN."""
        return None if c.startswith("P:") else bci.get(c)

    # -- traffic calming, for the plan's Class III condition ----------------
    calm_mid = sfdata.fetch(CALMING_MID_BLOCK, refresh=R)
    calm_node = sfdata.fetch(CALMING_INTERSECTION, refresh=R)
    cl_rows = sfdata.fetch(CENTERLINES, refresh=R)
    cnn_ends = {str(r["cnn"]).replace(".0", ""): (str(r.get("f_node_cnn") or "").replace(".0", ""), str(r.get("t_node_cnn") or "").replace(".0", ""))
                for r in cl_rows.rows if r.get("cnn")}

    def built_by(r, Y):
        if (r.get("current_status") or "") not in ("Complete", "Existing"):
            return False
        try:
            y = int(float(r.get("install_yr") or 0))
        except ValueError:  # the file writes a missing year as "<Null>"
            y = 0
        if 0 < y < 100:  # one row writes 2024 as "24"
            y += 2000
        return y == 0 or y <= Y  # an undated device counts; the files date few of them

    def calmed_in(Y):
        blocks_ = {str(r["cnn"]).replace(".0", "") for r in calm_mid.rows if r.get("cnn") and built_by(r, Y)}
        nodes_ = {str(r["cnn"]).replace(".0", "") for r in calm_node.rows if r.get("cnn") and built_by(r, Y)}
        return blocks_ | {c for c, (f, t) in cnn_ends.items() if f in nodes_ or t in nodes_}

    sources["calming"] = {"mid_block": {"id": CALMING_MID_BLOCK, "url": "https://data.sfgov.org/d/" + CALMING_MID_BLOCK, "queried": str(calm_mid.fetched_on), "rows": len(calm_mid.rows)},
                          "intersection": {"id": CALMING_INTERSECTION, "url": "https://data.sfgov.org/d/" + CALMING_INTERSECTION, "queried": str(calm_node.fetched_on), "rows": len(calm_node.rows)},
                          "centerlines": {"id": CENTERLINES, "queried": str(cl_rows.fetched_on)}}

    # -- slow streets -----------------------------------------------------
    slow = Extract("slow-streets").fetch_or_read("segments", fetch_slow_streets, refresh=R,
                                                 meta={"dataset": "https://data.sf.gov/d/" + SLOW_STREETS_ID})
    slow_by_year = collections.defaultdict(dict)  # first year -> {cnn: rec}
    slow_undated = 0
    for s in slow.records:
        if s["status"] != "Implemented" or not s["cnn"]:
            continue
        y = yr((s["install_date"] or "")[:4])
        if y is None or y < 1950:
            y, slow_undated = SLOW_STREETS_APPROVED, slow_undated + 1
        # A Slow Street row can carry a retired CNN too (Cayuga Avenue); it
        # is re-keyed the same way as the bikeway layer's rows.
        # A piece on no active block of its street (Cayuga Avenue's retired
        # block) is keyed by its endpoints, as the layer's unkeyed paths are.
        pieces = snapper.pieces(s["cnn"], s["street"], s["pts"]) if s.get("pts") else []
        if not pieces or pieces[0][2] == "kept":
            slow_by_year[y][s["cnn"]] = s
            continue
        total = sum(bikeway_snap.length_m(p) for _, p, _ in pieces) or 1.0
        for c, p, _ in pieces:
            share = bikeway_snap.length_m(p) / total
            k = c or path_key(p)
            slow_by_year[y][k] = dict(s, cnn=k, pts=p, len_mi=s["len_mi"] * share if s.get("len_mi") else s.get("len_mi"))
    sources["slow_streets"] = {"name": "Slow Streets", "dataset": "https://data.sf.gov/d/" + SLOW_STREETS_ID,
                               "queried": slow.fetched_on.isoformat(),
                               "implemented_segments": sum(len(v) for v in slow_by_year.values()),
                               "undated_segments_counted_from": SLOW_STREETS_APPROVED if slow_undated else None,
                               "undated_segments": slow_undated}

    # -- population -------------------------------------------------------
    cb = Extract("census-blocks")
    b10 = cb.fetch_or_read("2010", fetch_blocks_2010, refresh=R,
                           meta={"source": "TIGERweb tigerWMS_Census2010 layer 18 (Census Blocks), POP100 and interior point",
                                 "url": TIGER_2010})
    b20 = cb.fetch_or_read("2020", fetch_blocks_2020, refresh=R,
                           meta={"source": "DataSF Census 2020: Blocks for San Francisco, pop20 and interior point",
                                 "dataset": "https://data.sf.gov/d/" + BLOCKS_2020_ID})
    acs = cb.fetch_or_read("acs5-bg", fetch_acs, refresh=R,
                           meta={"source": "ACS 5-year B01003 total population by block group, via data.census.gov table API (no key)",
                                 "url": CEDSCI.replace("%d", "<year>"), "years": ACS_YEARS})
    acs_by = collections.defaultdict(dict)
    for r in acs.records:
        acs_by[r["year"]][r["bg"]] = r["pop"]

    def blocks_for(Y):
        """[(lon, lat, pop)] and a note on the level and vintage used."""
        if Y == 2020:
            return [(b["lon"], b["lat"], b["pop"]) for b in b20.records], "Census 2020 block counts (PL 94-171)"
        if Y < 2020:
            base, geo, ay = b10.records, "2010", Y
            note = "ACS %d–%d block-group totals, spread over 2010 blocks by their 2010 census shares" % (Y - 4, Y)
        else:
            ay = min(Y, max(ACS_YEARS))
            base, geo = b20.records, "2020"
            note = "ACS %d–%d block-group totals, spread over 2020 blocks by their 2020 census shares" % (ay - 4, ay)
            if ay != Y:
                note += "; the %d–%d ACS is the latest released, so %d is held at it" % (ay - 4, ay, Y)
        groups = collections.defaultdict(list)
        for b in base:
            groups[b["geoid"][:12]].append(b)
        out, missing = [], 0
        for bg, bs in groups.items():
            tot = acs_by[ay].get(bg)
            if tot is None:
                missing += 1
                for b in bs:
                    out.append((b["lon"], b["lat"], b["pop"]))
                continue
            base_sum = sum(b["pop"] for b in bs)
            for b in bs:
                share = (b["pop"] / base_sum) if base_sum else 1.0 / len(bs)
                out.append((b["lon"], b["lat"], tot * share))
        if missing:
            note += "; %d block groups absent from the ACS table kept their census count" % missing
        return out, note

    sources["population"] = {
        "2010_blocks": {"source": b10.meta["source"], "url": TIGER_2010, "queried": b10.fetched_on.isoformat(),
                        "blocks": len(b10.records), "total": sum(b["pop"] for b in b10.records)},
        "2020_blocks": {"source": b20.meta["source"], "dataset": b20.meta["dataset"], "queried": b20.fetched_on.isoformat(),
                        "blocks": len(b20.records), "total": sum(b["pop"] for b in b20.records)},
        "acs5_block_groups": {"source": acs.meta["source"], "queried": acs.fetched_on.isoformat(),
                              "totals": {y: sum(acs_by[y].values()) for y in ACS_YEARS}},
    }

    # -- schools ----------------------------------------------------------
    cde = Extract("schools").fetch_or_read("cde-sf", fetch_cde_schools, refresh=R,
                                           meta={"source": "CDE Public Schools and Districts data file, %s, via Internet Archive" % CDE_FILE_DATE,
                                                 "url": CDE_CAPTURE, "live_page": "https://www.cde.ca.gov/ds/si/ds/pubschls.asp"})
    schools = [s for s in cde.records if s["soc_type"] in SCHOOL_TYPES and s["lat"] and s["lon"] and s["open"]]
    skipped = collections.Counter(s["soc_type"] for s in cde.records if s["soc_type"] not in SCHOOL_TYPES)
    no_coord = sum(1 for s in cde.records if s["soc_type"] in SCHOOL_TYPES and not (s["lat"] and s["lon"] and s["open"]))
    virtual = sum(1 for s in schools if s.get("virtual") in ("F", "Exclusively Virtual"))

    # Private K-12 schools, through the dated DataSF cache (refreshed on
    # rowsUpdatedAt by pipeline/refresh-socrata.py).
    priv_rows = sfdata.fetch(SCHOOLS_ID, where="public_yesno=false and status='Active'", order=":id", floor=80)
    cde_cds = {s["cds"] for s in cde.records}
    cde_xy = [xy(s["lon"], s["lat"]) for s in schools]
    private, private_dupes, private_redacted = [], [], []

    def coord(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    for r in priv_rows.rows:
        if r.get("entity_type") not in PRIVATE_TYPES or not r.get("open_date"):
            continue
        lon, lat = coord(r.get("longitude")), coord(r.get("latitude"))
        if lon is None or lat is None:
            # DataSF prints "Information Redacted" in place of some schools' coordinates.
            private_redacted.append(r["school"])
            continue
        px, py = xy(lon, lat)
        if r["cds_code"] in cde_cds or any(math.hypot(px - x, py - y) <= SAME_SCHOOL_M for x, y in cde_xy):
            private_dupes.append(r["school"])
            continue
        private.append({"cds": r["cds_code"], "school": r["school"], "soc_type": r["entity_type"], "open": r["open_date"][:10],
                        "closed": None, "lat": lat, "lon": lon, "private": True})
    schools = schools + sorted(private, key=lambda s: s["cds"])

    def schools_in(Y):
        d = "%d-%s" % (Y, COUNT_DATE)
        return [s for s in schools if s["open"] <= d and (not s["closed"] or s["closed"] >= d)]

    # The cross-check count goes through the same dated cache as the private
    # schools above, so pipeline/refresh-socrata.py (a source step) refreshes it
    # and this build step reads no network. "Open now" means open on the count
    # date of the year the CDE directory was read, not of the year it runs.
    try:
        ds = sfdata.fetch(SCHOOLS_ID, select="count(*) as count", where="public_yesno=true and status='Active'",
                          order="count", floor=1)
        datasf_active = int(ds.rows[0]["count"])
        datasf_date = ds.fetched_on.isoformat()
    except Exception as e:  # a check, not an input
        datasf_active, datasf_date = None, str(e)
    open_year = cde.fetched_on.year
    latest_open = schools_in(open_year)
    sources["schools"] = {"source": cde.meta["source"], "url": CDE_CAPTURE, "queried": cde.fetched_on.isoformat(),
                          "open_now_charters": sum(1 for s in latest_open if s.get("charter") == "Y"),
                          "open_now_county_community": sum(1 for s in latest_open if s.get("soc_type") == "County Community"),
                          "open_now_total": len(latest_open),
                          "open_now_public": sum(1 for s in latest_open if not s.get("private")),
                          "open_now_private": sum(1 for s in latest_open if s.get("private")),
                          "private": {"source": "DataSF Schools, active private schools of the types %s" % ", ".join(sorted(PRIVATE_TYPES)),
                                      "dataset": "https://data.sf.gov/d/" + SCHOOLS_ID, "queried": priv_rows.fetched_on.isoformat(),
                                      "active_rows": len(priv_rows.rows), "counted": len(private),
                                      "same_as_a_cde_school": sorted(private_dupes),
                                      "location_redacted": sorted(private_redacted),
                                      "note": "the dataset lists active schools only, so a private school that closed earlier is missing from earlier years"},
                          "sf_rows": len(cde.records), "counted_types": sorted(SCHOOL_TYPES),
                          "skipped_by_type": dict(skipped), "counted_type_but_no_coordinates_or_open_date": no_coord,
                          "of_those_open_in_window": [s["school"] for s in cde.records if s["soc_type"] in SCHOOL_TYPES
                                                      and not (s["lat"] and s["lon"]) and (s["closed"] or "9999") >= "%d-%s" % (START_YEAR, COUNT_DATE)],
                          "virtual_schools_included": virtual,
                          "cross_check": {"dataset": "https://data.sf.gov/d/" + SCHOOLS_ID, "active_public_schools": datasf_active,
                                          "queried": datasf_date, "note": "DataSF's Schools lists active schools only, so it cannot date closures"}}

    # -- libraries --------------------------------------------------------
    libs = Extract("libraries").fetch_or_read("branches", fetch_libraries, refresh=R,
                                              meta={"source": "DataSF City Facilities, department Public Library, minus Library Support Services",
                                                    "dataset": "https://data.sf.gov/d/" + FACILITIES_ID,
                                                    "closures": LIBRARY_CLOSURES,
                                                    "not_counted": "SFPL Book Stop kiosks (Treasure Island, Dogpatch, Sunnydale) and the Mission temporary site"})

    def libs_in(Y):
        return [l for l in libs.records if not (l["closed_from"] and Y >= l["closed_from"] and (l["reopens"] is None or Y < l["reopens"]))]

    sources["libraries"] = {"source": libs.meta["source"], "dataset": libs.meta["dataset"], "queried": libs.fetched_on.isoformat(),
                            "branches_including_main": len(libs.records), "closures": LIBRARY_CLOSURES,
                            "not_counted": libs.meta["not_counted"]}

    # -- work SFMTA's project pages report as built this year ------------------
    # The bikeway layer dates work only into early 2026. scripts/bike-reported-
    # work.py lists the projects whose own pages say the work is complete, with
    # the page's words, the class built and the city blocks it covers. A block
    # already in the layer is upgraded to that class in the latest capture, with
    # UPDATE_YR set to the reported year, so earlier years keep the class the
    # archives show. A block the layer lacks is added with INSTALL_YR set to
    # that year, one row per direction of travel on its street (the plan's
    # unit, and what tools/bike-network/bike-progress.py counts for the same block).
    _dirs = []

    def directions():
        # Loaded on first use: it reads the layer extract and the centerlines.
        if not _dirs:
            sys.path.insert(0, paths.LIB)
            from plan_directions import Directions
            _dirs.append(Directions())
        return _dirs[0]

    reported_path = os.path.join(ROOT, "site", "data", "bike-history", "reported.json")
    rep = json.load(open(reported_path)) if os.path.exists(reported_path) else {"projects": []}
    rep_log = []
    latest = snaps[-1]["cnns"]
    for proj in rep["projects"]:
        cls, Y = proj["class"], proj["year"]
        upgraded, added, mi_up, mi_new = [], [], 0.0, 0.0
        for blk in proj["blocks"]:
            k, rec = blk["cnn"], latest.get(blk["cnn"])
            if rec and rec["rows"]:
                rows_new = [(cls if RANK.get(c, 0) < RANK[cls] else c, m) for c, m in rec["rows"]]
                if rows_new == rec["rows"]:
                    continue
                mi_up += sum(m for (c0, m), (c1, _) in zip(rec["rows"], rows_new) if c0 != c1)
                rec["rows"], rec["classes"] = rows_new, frozenset(c for c, _ in rows_new)
                rec["upd"] = max(rec["upd"] or 0, Y)
                upgraded.append(k)
            elif not rec:
                m = line_miles([xy(*c) for c in blk["pts"]])
                n = directions().count(k)[0]
                latest[k] = {"classes": frozenset([cls]), "rows": [(cls, m)] * n, "mi": m * n, "cl_mi": m, "inst": Y, "upd": None,
                             "street": blk["street"], "from": blk["from"], "to": blk["to"], "presidio": False, "path": False}
                live_pts.setdefault(k, blk["pts"])
                mi_new += m * n
                added.append(k)
        rep_log.append({"node": proj["node"], "name": proj["name"], "page": proj["page"], "year": Y, "class": cls,
                        "quote": proj["quote"], "blocks_upgraded": len(upgraded), "row_miles_upgraded": round(mi_up, 2),
                        "blocks_added": len(added), "row_miles_added": round(mi_new, 2)})
        print("  reported: %s -> %d blocks upgraded (%.2f row mi), %d added (%.2f mi) as %s in %d"
              % (proj["name"], len(upgraded), mi_up, len(added), mi_new, cls, Y))
    sources["reported"] = {"source": rep.get("source"), "generated": rep.get("generated"), "projects": rep_log}

    # -- the table --------------------------------------------------------
    latest_year = snaps[-1]["date"].year
    years = list(range(START_YEAR, latest_year + 1))
    first_archive = min(s["date"] for s in snaps if s["kind"] == "archive")
    rows, seg_years = [], collections.defaultdict(dict)
    aa_keys_prev = None
    aa_miles_latest = {}  # block key -> its qualifying row miles in the latest year it qualified
    # threshold id -> kind -> key -> (first year within reach, block that reached it)
    first_reach = {t["id"]: {"blocks": {}, "schools": {}, "libraries": {}} for t in REACH_THRESHOLDS}
    aa_years = collections.defaultdict(set)  # block key -> the years it was all-ages
    # threshold id -> kind -> key -> the years the point was within reach. The
    # map lights a point in exactly these years (write_map_data encodes them as
    # the first year and the years out of reach after it).
    within_years = {t["id"]: {"blocks": collections.defaultdict(set), "schools": collections.defaultdict(set),
                              "libraries": collections.defaultdict(set)} for t in REACH_THRESHOLDS}
    # threshold id -> points reached in some year and out of reach in the latest.
    reached_out = {}
    # Year -> the population per 2020 census block the year's figures use, for
    # the check that the map's lit dots add up to the year's residents.
    pop20_by_year = {}
    # The pandemic Slow Streets SFMTA dropped count toward the all-ages miles
    # and the reach in the years they stood: from their corridor's install
    # year through the year before slow_corridors.DROPPED_YEAR. hkz3-itiu
    # lists only the corridors the program kept, so without them 2020 and
    # 2021 would leave out those streets and the residents, schools and
    # branches they connected, and 2022 would not show them going.
    dropped_ss = slow_corridors.dropped_lines() if INCLUDE_SLOW_STREETS else []
    for Y in years:
        st, later, earlier, notes = state_in_year(Y, snaps)
        calmed = calmed_in(Y)
        net_mi = sum(v["mi"] for v in st.values())
        net_cl_mi = sum(v["cl_mi"] for v in st.values())
        slow_cnns = {}
        if INCLUDE_SLOW_STREETS:
            for y0, d in slow_by_year.items():
                if y0 <= Y:
                    slow_cnns.update(d)
        slow_only = {c: s for c, s in slow_cnns.items() if c not in st}
        slow_only_cl_mi = sum(line_miles([xy(*p) for p in s["pts"]]) for s in slow_only.values() if s["pts"])
        slow_only_mi = SLOW_STREET_DIRECTIONS * slow_only_cl_mi
        # Per block: the row miles that meet the plan's test. A Slow Street
        # block qualifies on every row. `aa` is the set of blocks with any
        # qualifying row, which is what the reach and the map use. The split:
        # rows that qualify by class or BCI are bikeway miles whether or not
        # the block is also a Slow Street; the Slow Street bucket is the
        # increment the programme adds, so a block that already qualified
        # does not move buckets in the year it became a Slow Street.
        aa_mi_of, aa_bike_mi, slow_on_bike_mi = {}, 0.0, 0.0
        for c, v in st.items():
            q = qualifying_miles(v["rows"], score(c), calmed=c in calmed)
            aa_mi_of[c] = v["mi"] if c in slow_cnns else q
            aa_bike_mi += q
            if c in slow_cnns:
                slow_on_bike_mi += v["mi"] - q
        aa = {c for c, m in aa_mi_of.items() if m > 0}
        # The pandemic Slow Street blocks SFMTA dropped in December 2022,
        # standing this year. Each counts every row, SLOW_STREET_DIRECTIONS
        # times its centreline length, as the kept Slow Streets outside the
        # bikeway layer do, unless its block is already all-ages this year (a
        # qualifying bikeway, or a Slow Street hkz3-itiu lists). Bryan,
        # 2026-09-29: "in 2022, we had a negative change in # of all ages
        # miles".
        dropped_lines = [(k, p) for k, p, y0, y1 in dropped_ss if y0 <= Y <= y1]
        pandemic_cl_mi, pandemic_blocks = 0.0, 0
        for k, p in dropped_lines:
            if k[3:] in aa or k[3:] in slow_cnns:
                continue
            pandemic_cl_mi += slow_corridors.centerline_miles(p)
            pandemic_blocks += 1
        pandemic_mi = SLOW_STREET_DIRECTIONS * pandemic_cl_mi
        aa_mi = aa_bike_mi + slow_on_bike_mi + slow_only_mi + pandemic_mi
        # Every row on a Slow Street block, both directions, for the check
        # against the plan's printed Slow Street miles.
        slow_all_rows_mi = sum(v["mi"] for c, v in st.items() if c in slow_cnns) + slow_only_mi
        aa_cl_mi = sum(st[c]["cl_mi"] for c in aa) + slow_only_cl_mi + pandemic_cl_mi
        strict_mi = sum(v["mi"] if c in slow_cnns else qualifying_miles(v["rows"], None, strict=True) for c, v in st.items()) + slow_only_mi + pandemic_mi
        # Rows admitted by the BCI test (Class II) and by BCI with calming
        # (Class III), and the Class III rows on calm streets that fail only
        # for want of recorded calming, so the calming proxy has a size.
        bci_ii_mi = sum(m for c, v in st.items() if c not in slow_cnns for cls, m in (v["rows"] or []) if cls == "CLASS II" and row_qualifies(cls, score(c)))
        bci_iii_mi = sum(m for c, v in st.items() if c not in slow_cnns for cls, m in (v["rows"] or []) if cls == "CLASS III" and row_qualifies(cls, score(c), c in calmed))
        bci_iii_uncalmed_mi = sum(m for c, v in st.items() if c not in slow_cnns and c not in calmed for cls, m in (v["rows"] or [])
                                  if cls == "CLASS III" and row_qualifies(cls, score(c), True))
        class_iv_mi = sum(m for v in st.values() for cls, m in (v["rows"] or []) if cls == "CLASS IV")
        class_iv_cl_mi = sum(v["cl_mi"] for v in st.values() if any(cls == "CLASS IV" for cls, _ in (v["rows"] or [])))
        class_iv_undated_mi = sum(m for v in st.values() if v["inst"] is None for cls, m in (v["rows"] or []) if cls == "CLASS IV")
        class_i_mi = sum(m for v in st.values() for cls, m in (v["rows"] or []) if cls == "CLASS I")
        # Slow Street centreline miles counted this year, from the dataset's
        # own geometry, one length per segment.
        slow_cl_mi = sum(line_miles([xy(*p) for p in s["pts"]]) for s in slow_cnns.values() if s["pts"])
        unknown_mi = sum(v["mi"] for v in st.values() if v["classes"] is None)
        # The two sides of the pre-archive uncertainty band: miles whose class
        # in Y is unknown but qualify in the later capture (the figure may be
        # low by this much), and CLASS IV miles credited to Y by an INSTALL_YR
        # before 2014, when Caltrans first defined Class IV (the figure may be
        # high by this much).
        unknown_aa_mi = sum(qualifying_miles(v["later_rows"], score(c), calmed=c in calmed) for c, v in st.items() if v["classes"] is None)
        pre2014_iv_mi = sum(m for c, v in st.items() if v["inst"] is not None and v["inst"] < 2014
                            for cls, m in (v["rows"] or []) if cls == "CLASS IV")
        presidio_net_mi = sum(v["mi"] for v in st.values() if v["presidio"])
        presidio_aa_mi = sum(aa_mi_of[c] for c in aa if st[c]["presidio"])
        path_net_mi = sum(v["mi"] for c, v in st.items() if v["path"] and not v["presidio"] and c not in retired_keys)
        path_aa_mi = sum(aa_mi_of[c] for c in aa if st[c]["path"] and not st[c]["presidio"] and c not in retired_keys)
        retired_net_mi = sum(v["mi"] for c, v in st.items() if c in retired_keys)
        retired_aa_mi = sum(aa_mi_of[c] for c in aa if c in retired_keys)
        for c in aa:
            aa_miles_latest[c] = aa_mi_of[c]
        for c, s in slow_only.items():
            if s["pts"]:
                aa_miles_latest[c] = SLOW_STREET_DIRECTIONS * line_miles([xy(*p) for p in s["pts"]])

        # Two sources, kept apart and named: the all-ages lines of the bikeway
        # layer and hkz3-itiu, and the dropped pandemic Slow Street blocks
        # standing this year. A dropped block on an all-ages line is reached
        # twice, which changes nothing. Sorted by key, so ties in the walking
        # search go the same way on every run.
        lines = sorted([(c, live_pts[c]) for c in aa if c in live_pts] + [(c, s["pts"]) for c, s in slow_only.items() if s["pts"]])
        reach_lines = lines + dropped_lines
        # One grid per threshold; the plan's quarter mile is the default and
        # feeds the row's top-level figures.
        reaches = {t["id"]: WalkReach(reach_lines, t["metres"]) for t in REACH_THRESHOLDS}
        reach = reaches[DEFAULT_REACH]
        # For the map: which blocks became all-ages this year, and which
        # school, branch or census block each one first brought within reach.
        # A dropped Slow Street block ("SS:<cnn>") can be the block that first
        # reached a point; it is never drawn from all-ages.geojson, since the
        # site draws the dropped corridors from removed.json.
        aa_keys = {c for c, _ in reach_lines}
        for c in aa_keys:
            if not c.startswith("SS:"):
                aa_years[c].add(Y)
        new_lines = [(c, p) for c, p in reach_lines if c not in aa_keys_prev] if aa_keys_prev is not None else None
        aa_keys_prev = aa_keys
        for t in REACH_THRESHOLDS:
            R, fr, wy = reaches[t["id"]], first_reach[t["id"]], within_years[t["id"]]
            new_reach = WalkReach(new_lines, t["metres"]) if new_lines is not None else None
            for kind, items, ident in (("blocks", b20.records, lambda b: b["geoid"]), ("schools", schools, lambda s: s["cds"]),
                                       ("libraries", libs.records, lambda l: l["name"])):
                for it in items:
                    k = ident(it)
                    if not R.within(it["lon"], it["lat"]):
                        continue
                    wy[kind][k].add(Y)
                    if k in fr[kind]:
                        continue
                    near = new_reach.nearest(it["lon"], it["lat"])[0] if new_reach else None
                    fr[kind][k] = (Y, near)

        blocks, pop_note = blocks_for(Y)
        pop_total = sum(p for _, _, p in blocks)
        if Y >= 2020:
            pop20_by_year[Y] = {(lon, lat): p for lon, lat, p in blocks}
        sch = schools_in(Y)
        lb = libs_in(Y)
        by_threshold = {}
        for t in REACH_THRESHOLDS:
            R = reaches[t["id"]]
            pi = sum(p for lon, lat, p in blocks if R.within(lon, lat))
            si = sum(1 for s in sch if R.within(s["lon"], s["lat"]))
            li = sum(1 for l in lb if R.within(l["lon"], l["lat"]))
            by_threshold[t["id"]] = {
                "metres": round(t["metres"], 1),
                "residents_within_reach": int(round(pi)), "resident_share": round(pi / pop_total, 4) if pop_total else None,
                "schools_within_reach": si, "school_share": round(si / len(sch), 4) if sch else None,
                "libraries_within_reach": li, "library_share": round(li / len(lb), 4) if lb else None,
            }
        # The same figures without the dropped Slow Streets, in the years they
        # stood, so the check below and a reader can see what they add.
        without = None
        if dropped_lines:
            without = {}
            for t in REACH_THRESHOLDS:
                R0 = WalkReach(lines, t["metres"])
                without[t["id"]] = {"residents_within_reach": int(round(sum(p for lon, lat, p in blocks if R0.within(lon, lat)))),
                                    "schools_within_reach": sum(1 for s in sch if R0.within(s["lon"], s["lat"])),
                                    "libraries_within_reach": sum(1 for l in lb if R0.within(l["lon"], l["lat"]))}
                without[t["id"]]["resident_share"] = round(without[t["id"]]["residents_within_reach"] / pop_total, 4) if pop_total else None
        for t in REACH_THRESHOLDS:
            R, fr = reaches[t["id"]], first_reach[t["id"]]
            ob = [b for b in b20.records if b["pop"] > 0 and b["geoid"] in fr["blocks"] and not R.within(b["lon"], b["lat"])]
            reached_out[t["id"]] = {"year": Y, "blocks": len(ob), "residents_2020": int(round(sum(b["pop"] for b in ob))),
                                "schools": sorted(s["school"] for s in sch if s["cds"] in fr["schools"] and not R.within(s["lon"], s["lat"])),
                                "libraries": sorted(l["name"] for l in lb if l["name"] in fr["libraries"] and not R.within(l["lon"], l["lat"]))}
        pop_in = sum(p for lon, lat, p in blocks if reach.within(lon, lat))
        sch_in = [s for s in sch if reach.within(s["lon"], s["lat"])]
        lb_in = [l for l in lb if reach.within(l["lon"], l["lat"])]

        if later["kind"] == "live" and later["date"].year == Y:
            basis = "live layer as of %s (year to date)" % later["label"]
            tier = "current"
        elif earlier is None:
            basis = ("existence from INSTALL_YR in the %s capture; class from that capture, moved back where UPDATE_YR says the change came later; "
                     "blocks removed before %s are invisible" % (later["label"], first_archive.isoformat()))
            tier = "INSTALL_YR only"
        else:
            basis = "bracketed by captures %s and %s; changes inside the gap dated by UPDATE_YR where present" % (earlier["label"], later["label"])
            tier = "archived snapshots"
        rows.append({
            "year": Y,
            # Row miles, the plan's unit: one length per direction row.
            "network_miles": round(net_mi, 1), "all_ages_miles": round(aa_mi, 1),
            # Centreline miles, one length per block, for a reader who wants them.
            "network_centerline_miles": round(net_cl_mi, 1), "all_ages_centerline_miles": round(aa_cl_mi, 1),
            # The stricter set, Class I/IV and Slow Streets with no BCI test. No page shows it.
            "all_ages_strict_miles": round(strict_mi, 1),
            # all_ages_bikeway_miles: rows that qualify by class or BCI, on any
            # block. slow_street_miles_on_bikeway_blocks: the rows the Slow
            # Street designation adds on bikeway blocks beyond those.
            "all_ages_bikeway_miles": round(aa_bike_mi, 1), "slow_street_miles_on_bikeway_blocks": round(slow_on_bike_mi, 1),
            "slow_street_miles_not_in_bikeway_layer": round(slow_only_mi, 1),
            # The dropped pandemic Slow Street blocks counted in this year's
            # all-ages miles (those no all-ages line already covered), per
            # direction; the drop from the year before is filled in below.
            "pandemic_slow_street_miles": round(pandemic_mi, 2), "pandemic_slow_street_blocks": pandemic_blocks,
            # Every Slow Street mile in the all-ages total, kept and dropped:
            # the rows the designation adds beyond what already qualified as
            # bikeway, per direction (the two buckets above plus the pandemic one).
            "slow_street_all_ages_miles": round(slow_on_bike_mi + slow_only_mi + pandemic_mi, 2),
            "slow_street_miles_all_rows": round(slow_all_rows_mi, 1),
            "all_ages_by_bci_class_ii_miles": round(bci_ii_mi, 1), "all_ages_by_bci_class_iii_miles": round(bci_iii_mi, 1),
            "class_iii_calm_street_no_calming_miles": round(bci_iii_uncalmed_mi, 1),
            "class_iv_miles": round(class_iv_mi, 1), "class_i_miles": round(class_i_mi, 1),
            "class_iv_centerline_miles": round(class_iv_cl_mi, 1), "class_iv_miles_with_no_install_year": round(class_iv_undated_mi, 1),
            "slow_street_centerline_miles": round(slow_cl_mi, 1),
            "blocks_all_ages": len(aa) + len(slow_only) + pandemic_blocks, "rows": sum(len(v["rows"] or v["later_rows"] or []) for v in st.values()),
            "miles_class_unknown": round(unknown_mi, 1), "miles_class_unknown_all_ages_later": round(unknown_aa_mi, 1),
            "class_iv_miles_with_install_before_2014": round(pre2014_iv_mi, 1),
            "presidio_network_miles": round(presidio_net_mi, 1), "presidio_all_ages_miles": round(presidio_aa_mi, 1),
            "other_no_cnn_path_network_miles": round(path_net_mi, 1), "other_no_cnn_path_all_ages_miles": round(path_aa_mi, 1),
            # On-street rows on a block the centerline retired and nothing replaced.
            "retired_block_network_miles": round(retired_net_mi, 1), "retired_block_all_ages_miles": round(retired_aa_mi, 1),
            "blocks": len(st),
            "residents_within_reach": int(round(pop_in)), "residents_total": int(round(pop_total)),
            "resident_share": round(pop_in / pop_total, 4) if pop_total else None, "population_basis": pop_note,
            "schools_within_reach": len(sch_in), "schools_total": len(sch),
            "school_share": round(len(sch_in) / len(sch), 4) if sch else None,
            "libraries_within_reach": len(lb_in), "libraries_total": len(lb),
            "library_share": round(len(lb_in) / len(lb), 4) if lb else None,
            # The same six figures at every distance in REACH_THRESHOLDS; the
            # entry for DEFAULT_REACH repeats the fields above.
            "reach_by_threshold": by_threshold,
            # The dropped pandemic Slow Street blocks counted in this year's
            # reach, and the reach figures without them.
            "dropped_slow_street_blocks_in_reach": len(dropped_lines),
            "reach_without_dropped_slow_streets": without,
            "network_basis": basis, "tier": tier, "network_notes": dict(notes),
        })
        for c, v in st.items():
            seg_years[c][Y] = "S" if c in slow_cnns else CODE.get(best(v["classes"]) if v["classes"] else "UNKNOWN", "?")
            seg_years[c]["presidio"] = v["presidio"]
        for c in slow_only:
            seg_years[c][Y] = "S"
        print("  %d  net %6.1f (centreline %5.1f)  all-ages %5.1f (strict %5.1f; by BCI II %5.1f III %5.1f)  residents %5.1f%%  schools %3d/%3d  libraries %2d/%2d  [%s]"
              % (Y, net_mi, net_cl_mi, aa_mi, strict_mi, bci_ii_mi, bci_iii_mi, 100 * pop_in / pop_total, len(sch_in), len(sch), len(lb_in), len(lb), tier))

    # The dropped pandemic miles that left the all-ages series each year.
    for i, r in enumerate(rows):
        prev_p = rows[i - 1]["pandemic_slow_street_miles"] if i else 0.0
        r["pandemic_dropped_miles"] = round(max(0.0, prev_p - r["pandemic_slow_street_miles"]), 2)

    # -- planned work, counted the same way --------------------------------
    # Bryan, 2026-09-24: "include planned projects for 2027 and beyond, as much
    # as MTA has available". tools/bike-network/bike-reported-work.py lists the bikeway
    # work SFMTA's pages still call pending, with the year each gives for
    # finishing it. Starting from the latest year's network (st, left by the
    # loop above), each year's projects upgrade their blocks as the reported
    # work does, and the all-ages miles are counted with the same test. The
    # latest year's residents, BCI scores and Slow Streets are held fixed.
    planned_path = os.path.join(ROOT, "site", "data", "bike-history", "planned.json")
    pl = json.load(open(planned_path)) if os.path.exists(planned_path) else {"projects": []}
    fut = {c: dict(v, rows=list(v["rows"] or [])) for c, v in st.items()}

    def aa_total(state):
        bike, on_slow = 0.0, 0.0
        for c, v in state.items():
            q = qualifying_miles(v["rows"], score(c), calmed=c in calmed)
            bike += q
            if c in slow_cnns:
                on_slow += v["mi"] - q
        return bike + on_slow + slow_only_mi

    # The residents, schools and branches within reach of each planned year's
    # network, at every distance, against the latest year's population, schools
    # and branches (blocks, sch and lb, left by the loop above).
    plan_pts = {}

    def reach_of(state):
        ls = [(c, live_pts.get(c) or plan_pts.get(c)) for c, v in state.items()
              if c in slow_cnns or qualifying_miles(v["rows"], score(c), calmed=c in calmed) > 0]
        ls = [(c, p) for c, p in ls if p] + [(c, s["pts"]) for c, s in slow_only.items() if s["pts"]]
        out = {}
        for t in REACH_THRESHOLDS:
            R = WalkReach(ls, t["metres"])
            pi = sum(p for lon, lat, p in blocks if R.within(lon, lat))
            si = sum(1 for s in sch if R.within(s["lon"], s["lat"]))
            li = sum(1 for l in lb if R.within(l["lon"], l["lat"]))
            out[t["id"]] = {"metres": round(t["metres"], 1),
                            "residents_within_reach": int(round(pi)), "resident_share": round(pi / pop_total, 4) if pop_total else None,
                            "schools_within_reach": si, "school_share": round(si / len(sch), 4) if sch else None,
                            "libraries_within_reach": li, "library_share": round(li / len(lb), 4) if lb else None}
        return out

    planned_rows, prev = [], aa_total(fut)
    for Y in sorted({p["year"] for p in pl["projects"]}):
        names = []
        for proj in (p for p in pl["projects"] if p["year"] == Y):
            cls = proj["class"]
            for blk in proj["blocks"]:
                # Existing rows are re-classed; a block gains rows up to the
                # direction rows the finished bikeway has (blk["rows"]), so a
                # one-way lane made two-way adds its second direction.
                rec = fut.get(blk["cnn"])
                m = line_miles([xy(*c) for c in blk["pts"]])
                if not rec:
                    rec = fut[blk["cnn"]] = {"rows": [], "mi": m}
                plan_pts.setdefault(blk["cnn"], blk["pts"])
                rec["rows"] = [(cls if RANK.get(c, 0) < RANK[cls] else c, rm) for c, rm in rec["rows"]]
                while len(rec["rows"]) < blk.get("rows", 1):
                    rec["rows"].append((cls, rec["rows"][0][1] if rec["rows"] else m))
            names.append({"node": proj["node"], "name": proj["name"], "page": proj["page"], "quote": proj["quote"]})
        now = aa_total(fut)
        by_t = reach_of(fut)
        planned_rows.append({"year": Y, "all_ages_miles": round(now, 1), "added_miles": round(now - prev, 1),
                             "residents_total": int(round(pop_total)), "schools_total": len(sch), "libraries_total": len(lb),
                             "reach_by_threshold": by_t, "projects": names})
        print("  planned %d: all-ages %.1f (+%.1f), %.1f%% of residents within reach, from %s"
              % (Y, now, now - prev, 100 * by_t[DEFAULT_REACH]["resident_share"], ", ".join(n["name"] for n in names)))
        prev = now
    planned_out = {"generated": pl.get("generated"), "source": pl.get("source"), "rows": planned_rows,
                   "uncounted": pl.get("uncounted", [])}

    disagreements = {
        "published_vs_centerline": {
            "sfmta_published": {"miles": 470, "separated_miles": 50, "source": "https://www.sfmta.com/blog/safety-upgrades-make-difference-bike-ridership-rise", "date": "2026-05-28"},
            "plan_printed": {"miles": 472, "miles_2010": 302, "protected_miles": 41, "slow_street_miles": 32, "car_free_miles": 7,
                             "source": "https://www.sfmta.com/media/41810/download", "page": 20, "read": "2026-09-22"},
            "layer_row_sum_LENGTH": {"miles": round(row_sum, 1), "class_iv_miles": round(row_sum_iv, 1), "class_iv_contraflow_miles": round(row_sum_iv_contraflow, 1),
                                     "queried": live.fetched_on.isoformat()},
            "single_row_two_way_blocks": single_2w_note,
            "layer_row_sum_LENGTH_FT": {"miles": round(row_sum_ft, 1), "queried": live.fetched_on.isoformat()},
            "layer_row_geometry": {"miles": rows[-1]["network_miles"], "rows": rows[-1]["rows"], "queried": live.fetched_on.isoformat()},
            "layer_centerline": {"miles_from_geometry": rows[-1]["network_centerline_miles"], "blocks": rows[-1]["blocks"], "queried": live.fetched_on.isoformat()},
            "used": ("row miles: every direction row's length from its geometry, summed, which is how the plan's 472 is counted. "
                     "The layer holds one row per direction of travel on most blocks, so a two-way street with a lane each way counts twice."),
        },
        "schools_active_count": {"cde_archive_open_on_%d-%s" % (years[-1], COUNT_DATE): rows[-1]["schools_total"],
                                 "datasf_%s_active_public" % SCHOOLS_ID: datasf_active,
                                 "used": "CDE archive, because it carries closure dates; DataSF's count includes preschools, adult schools and other types this table leaves out"},
    }

    # The check against the plan's own printed figures, at the year the plan
    # measured (its memo is dated 2024-02-13, its network figures early 2025).
    plan_row = next((r for r in rows if r["year"] == 2024), None)
    comparison = None
    if plan_row:
        ours = plan_row["resident_share"]
        slow_2024 = plan_row["slow_street_miles_all_rows"]
        comparison = {
            "year": 2024, "plan_reported_share": 0.80, "plan_reported_epc_share": 0.71, "ours_plan_definition_share": ours,
            "gap_points": round(100 * (0.80 - ours), 1),
            "plan_source": "Biking and Rolling Plan, printed p. 24, and Appendix G, Toole Design connectivity memo, 2024-02-13 [primary — read 2026-09-22]",
            "network_miles": {"ours_2024": plan_row["network_miles"], "ours_latest": rows[-1]["network_miles"], "plan_p20": 472},
            "protected_miles": {"ours_2024_class_iv": plan_row["class_iv_miles"], "ours_latest_class_iv": rows[-1]["class_iv_miles"], "plan_p20": 41,
                                "ours_2024_class_iv_centerline": plan_row["class_iv_centerline_miles"],
                                "ours_2024_class_iv_with_no_install_year": plan_row["class_iv_miles_with_no_install_year"],
                                "ours_2021_class_iv": next((r["class_iv_miles"] for r in rows if r["year"] == 2021), None),
                                "live_class_iv_contraflow_miles": round(row_sum_iv_contraflow, 1),
                                "note": ("Counted once per block the 2024 figure falls below 41, so the unit does not explain the gap. Class IV row miles reached 41.0 at the end of 2021, "
                                         "the plan's figure exactly, and 42.1 in 2022, so a row sum taken from the layer as it stood in 2021 or 2022 gives the plan's number. "
                                         "The most consistent reading is that the plan's 41 was counted before its 2024 connectivity memo and not updated; SFMTA's May 2026 "
                                         "blog figure of 50 separated miles matches the layer's row sum for 2024. [inference — mine]")},
            "slow_street_miles": {"ours_2024_both_directions": round(slow_2024, 1), "dataset_centerline": plan_row["slow_street_centerline_miles"], "plan_p20": 32,
                                  "note": "dataset_centerline is the sum of the implemented segments' own geometry, one length per segment"},
            "car_free_miles": {"ours": None, "plan_p20": 7, "note": "the bikeway layer has no car-free class; JFK Promenade and the Great Highway are Class I rows"},
            "epc_comparison": "not computed: no equity priority communities layer is catalogued in this repo (DataSF search 2026-09-22 found none)",
            "likely_causes": [
                "Class III calming: read from the city's two traffic calming datasets, which may miss calming the plan's authors counted or count devices they did not; %.1f miles of Class III on calm streets were left out in 2024 for want of recorded calming." % plan_row["class_iii_calm_street_no_calming_miles"],
                "Distance: a quarter mile walked along OpenStreetMap's walk network from the census block's interior point. Appendix G's own distance method was not read here, so whether it walks or measures a straight line is unverified [unretrieved — verify].",
                "BCI vintage: the 2023 Draft layer is the only one published; the plan says the index 'was updated for all streets', so the memo may have scored some blocks differently in either direction.",
                "Population base: ACS 2020–2024 block-group totals spread over 2020 census blocks; the memo's base and geography are not stated in what was read.",
            ] if abs(0.80 - ours) > 0.03 else [],
            "tag": "[inference — mine]",
        }

    method = {
        "definitions": {
            "plan": ("The Biking and Rolling Plan's high-quality test (printed p. 24; Appendix G, Toole Design connectivity memo of 2024-02-13): Class I, Class IV and "
                     "Slow Streets; Class II with Bike Comfort Index above %d; Class III with traffic calming and BCI above %d. A direction row qualifies by its own class; a Class II or III row "
                     "qualifies when its block's 2023 Draft BCI (%s) clears %d. BCI is one 2023 snapshot held fixed for every year. A Class III row also needs traffic calming on its block by that year, "
                     "read from DataSF abhw-ffzx (mid-block) and bp3t-bd4t (intersection devices at either end of the block); class_iii_calm_street_no_calming_miles is what that condition removes."
                     % (PLAN_BCI_THRESHOLD, PLAN_BCI_THRESHOLD, PLAN_BCI_FIELD, PLAN_BCI_THRESHOLD)),
            "strict": "Class I, Class IV and Slow Street rows only, no BCI test. Written as all_ages_strict_miles; no page shows it.",
            "default": DEFAULT_DEFINITION,
        },
        "all_ages": {"classes": sorted(PLAN_ALL_AGES_CLASSES), "bci_classes": sorted(PLAN_BCI_CLASSES), "bci_threshold": PLAN_BCI_THRESHOLD,
                     "slow_streets": INCLUDE_SLOW_STREETS, "per_row": True,
                     "rule": "A direction row is all-ages when it is CLASS I or CLASS IV, or CLASS II or CLASS III on a block whose BCI is above %d, or on an implemented Slow Street from its install year. A block is within reach of a point when any of its rows qualifies." % PLAN_BCI_THRESHOLD},
        "year_state": ("A block's class in year Y is its class in the nearest archived copy captured after the end of Y, unless UPDATE_YR says the change came after Y, "
                       "in which case it is the class in the nearest earlier copy, or unknown when there is none. A block exists in Y when INSTALL_YR is Y or earlier, or blank. "
                       "A block in the earlier copy and gone from the later one is counted through Y."),
        "miles": ("Row miles, the plan's unit: every direction row's length, summed, so a two-way street with a lane each way counts twice. A live row is measured from its own "
                  "line geometry (equirectangular projection about 37.76 N); an archived row on a block still in the layer at the live layer's mean row length for that block, "
                  "since the archived exports keep no geometry for those; an archived row on a block since dropped from its own geometry. Slow Street blocks outside the "
                  "bikeway layer count their length %d times. Centreline miles, one length per block, are written beside every row-mile figure. Off-street paths with no CNN "
                  "(Presidio trails, Golden Gate Park, Kirkham, SFSU and other paths) are keyed by their endpoints and counted; the Presidio's are also shown separately."
                  % SLOW_STREET_DIRECTIONS),
        "gap_fill": "A block present in an earlier and a later capture but missing from one between is carried through the gap with its earlier record.",
        "timing": "Network state is the end of the year (or the latest capture for the current year); schools and libraries are counted as open on %s of the year." % COUNT_DATE,
        "reach": ("Walking distance along OpenStreetMap's walk network (OSMnx's walk filter plus cycle paths; see site/data/bike-history/walk-reach.json for the copy read) from the census block's interior point, the school's CDE coordinate or the branch's City Facilities coordinate "
                  "to the nearest all-ages line, at most %.2f miles by default; the point joins the network at the nearest street or path in a straight line, and a line is reached where it passes within %.0f m of a walkable way (lib/walknet.py). "
                  "reach_thresholds names the shorter distances the overview also offers. The lines reached include the pandemic Slow Street blocks SFMTA dropped in December %d, from their corridor's install year through %d, as the miles do (reach_without_dropped_slow_streets on each row gives the figures without them)."
                  % (REACH_MILES, walknet.SOURCE_SNAP_M, slow_corridors.DROPPED_YEAR, slow_corridors.DROPPED_YEAR - 1)),
        "reach_thresholds": ("Four distances, the plan's quarter mile (%.0f m) by default, one and two city blocks (%d and %d feet), and %d feet, about the 300 m walk to a protected bikeway the ITDP Atlas of Sustainable City Transport measures. The population-weighted average block, intersection to intersection on the street centerline over %d tracts, is %d feet (%s, %s, read %s), so %s. Each row's reach_by_threshold carries the six reach figures at each."
                             % (REACH_MILES * MILE, BLOCK_FT, 2 * BLOCK_FT, ITDP_FT, BLOCK_SOURCE["tracts"], BLOCK_SOURCE["measured_ft"], BLOCK_SOURCE["script"], BLOCK_SOURCE["url"], BLOCK_SOURCE["read"], BLOCK_SOURCE["rounding"])),
        "population_denominator": "Every block in San Francisco County, including Treasure Island and the Farallones.",
        "school_denominator": ("K-12 schools: public schools of the counted types (see sources.schools) open on %s of the year, by CDE OpenDate and ClosedDate, "
                               "plus DataSF's active private elementary, high and K-12 schools from their open_date (a private school that closed earlier is missing). "
                               "Charter schools are included (%d of the %d open in %d), as is the County Community school run in the county jail (%d)."
                               % (COUNT_DATE, sources["schools"]["open_now_charters"], sources["schools"]["open_now_total"], int(sources["schools"]["queried"][:4]),
                                  sources["schools"]["open_now_county_community"])),
        "library_denominator": "SFPL branches plus the Main Library in City Facilities, minus branches closed for renovation that year.",
        "count_date": COUNT_DATE, "reach_miles": REACH_MILES, "start_year": START_YEAR,
    }
    limits = [
        "Before %s no archived copy of the layer exists. Years %d–%d rest on INSTALL_YR alone: a block installed before %d and removed before the first capture is invisible, a block whose class was upgraded with no UPDATE_YR is credited with its later class in every year back to its install, and 23%% of the live layer's miles carry no INSTALL_YR at all and are assumed present throughout. Treat network miles in those years as a floor."
        % (first_archive.isoformat(), START_YEAR, first_archive.year - 1, first_archive.year),
        "All-ages miles before %d carry an uncertainty band of about ±%.0f miles in %d, from two opposite errors. %.1f miles have an unknown class in %d because UPDATE_YR is later and there is no earlier capture, and %.1f of those are all-ages today, so the figure may be low by up to that much. In the other direction, %.1f miles of CLASS IV are credited to %d by an INSTALL_YR of 2013 or earlier, before Caltrans defined Class IV (2014), so on those rows INSTALL_YR dates the street's first bikeway rather than the separated lane, and the figure may be high by up to that much. [inference — mine]"
        % (first_archive.year, max(rows[0]["miles_class_unknown_all_ages_later"], rows[0]["class_iv_miles_with_install_before_2014"]), START_YEAR,
           rows[0]["miles_class_unknown"], START_YEAR, rows[0]["miles_class_unknown_all_ages_later"], rows[0]["class_iv_miles_with_install_before_2014"], START_YEAR),
        "Between captures a change is dated by UPDATE_YR when the row carries one; otherwise it is credited to the year before the later capture. The 2022-12-09 to 2024-03-31 and 2024-03-31 to 2025-12-08 gaps are the widest.",
        "Population for years other than 2020 is an ACS 5-year block-group estimate spread across blocks by census shares, so it is a five-year average, not a point count, and block-level shares are held at the nearest census. 2025 and 2026 are held at the 2020–2024 ACS, the latest released.",
        "The Slow Streets dataset was last loaded 2024-01-18 and carries no removal dates; the pandemic-era Slow Streets that were dropped in 2022 are not in it, and %d segments (the SoMa streets) carry no install date and are counted from %d. The dropped corridors are traced from SFMTA's 2020 and 2021 Board reports (lib/slow_corridors.py) and counted in the all-ages miles and the reach from their install year through %d: %d blocks, %.1f all-ages miles in %d that no other all-ages line covered, adding %.1f points of residents within a quarter mile in %d. The reports give each corridor's extent as approved; where a corridor went in shorter, these years are high by the difference." % (
            slow_undated, SLOW_STREETS_APPROVED, slow_corridors.DROPPED_YEAR - 1, len(dropped_ss),
            rows[years.index(slow_corridors.DROPPED_YEAR - 1)]["pandemic_slow_street_miles"], slow_corridors.DROPPED_YEAR - 1,
            100 * (rows[years.index(2020)]["resident_share"] - rows[years.index(2020)]["reach_without_dropped_slow_streets"][DEFAULT_REACH]["resident_share"]), 2020),
        "The CDE directory is the 2025-10-05 archive capture, so schools opened or closed after that date are missing. School coordinates are CDE's; most schools closed before 2015 carry none, and the one school open in the window without one (Gateway to College, closed 2016) is left out.",
        "Library closures are entered by hand from SFPL's pages; only the Mission Branch's renovation closure is recorded. The system-wide COVID closure of March 2020 to May 2021 is not treated as a closure.",
        "The map lights a point in exactly the years it is within reach, so a point reached only through a dropped Slow Street or a removed bikeway goes grey when it went. In %d, %d blocks (%s residents at the 2020 count) and %d %s that were within a quarter mile of an all-ages line in an earlier year are not."
        % (reached_out[DEFAULT_REACH]["year"], reached_out[DEFAULT_REACH]["blocks"], format(reached_out[DEFAULT_REACH]["residents_2020"], ","), len(reached_out[DEFAULT_REACH]["libraries"]),
           "branch" if len(reached_out[DEFAULT_REACH]["libraries"]) == 1 else "branches"),
    ]
    reach_checks(years, rows, within_years, b20, schools_in, libs_in, pop20_by_year)
    out = {"generated": dt.date.today().isoformat(), "mileBasis": BASIS, "years": years, "rows": rows, "sources": sources,
           "reach_thresholds": REACH_THRESHOLDS, "default_reach": DEFAULT_REACH, "block_source": BLOCK_SOURCE,
           "reached_earlier_out_latest": reached_out,
           "no_cnn_paths": len(path_keys_live - retired_keys), "include_presidio": INCLUDE_PRESIDIO,
           "retired_block_streets": sorted({(r.get("STREETNAME") or "").strip().title().replace(" Of ", " of ") for r in live_recs
                                            if r.get("_snap") == "retired" and (r.get("STREETNAME") or "").strip()}),
           "default_definition": DEFAULT_DEFINITION, "plan_comparison_2024": comparison,
           "disagreements": disagreements, "method": method, "limits": limits, "planned": planned_out,
           "departed_rows": departed_rows}
    closed_year_check(rows, live.fetched_on.year, args.reopen_closed_years)
    stable.write_json(os.path.join(OUT, "history.json"), out, end="", indent=1, ensure_ascii=False)
    # The site builds from site/data alone (site/scripts/check-public.mjs
    # refuses a reference outside site/), so the table travels there too.
    stable.write_json(os.path.join(os.path.dirname(SITE_OUT), "history.json"), out, end="", indent=1,
                      ensure_ascii=False)

    # -- the explorer's components, latest year ----------------------------
    # The overview's definition explorer lets a reader choose which facility
    # classes count as all-ages (Bryan, 2026-09-23: "choose what's acceptable
    # bike infra for 'all ages and abilities'"). So each block's row miles in
    # the latest year are split seven ways: Class I, Class IV, Class II and
    # III each on a calm street (BCI above the plan's threshold) or not, and
    # the Slow Street designation, which covers every row on its block.
    def comp_code(cls, c):
        if cls == "CLASS I":
            return "1"
        if cls == "CLASS IV":
            return "4"
        if cls in ("CLASS II", "CLASS III"):
            # Class III is "c" only when it meets the plan's whole test, BCI
            # and calming, so the explorer's calm switch applies the plan.
            return ("2" if cls == "CLASS II" else "3") + ("c" if row_qualifies(cls, score(c), c in calmed) else "b")
        return None
    components = {}
    for c, v in st.items():
        by_comp = collections.defaultdict(float)
        for cls, m_ in (v["rows"] or []):
            code = comp_code(cls, c)
            if code:
                by_comp[code] += m_
        entry = {"m": {k: round(x, 4) for k, x in by_comp.items() if x > 0}}
        if c in slow_cnns:
            entry["s"] = round(v["mi"], 4)
        if entry["m"] or "s" in entry:
            components[c] = entry
    for c, s_ in slow_only.items():
        if s_["pts"]:
            components[c] = {"m": {}, "s": round(SLOW_STREET_DIRECTIONS * line_miles([xy(*p) for p in s_["pts"]]), 4)}
    stable.write_json(os.path.join(os.path.dirname(SITE_OUT), "components.json"), {"year": years[-1], "mileBasis": BASIS, "bci_threshold": PLAN_BCI_THRESHOLD,
                   "codes": {"1": "Class I off-street path", "4": "Class IV separated lane",
                             "2c": "Class II painted lane on a block with BCI above %d" % PLAN_BCI_THRESHOLD,
                             "2b": "Class II painted lane on a block with BCI at or below %d, or unscored" % PLAN_BCI_THRESHOLD,
                             "3c": "Class III signed route on a block with BCI above %d" % PLAN_BCI_THRESHOLD,
                             "3b": "Class III signed route on a block with BCI at or below %d, or unscored" % PLAN_BCI_THRESHOLD},
                   "note": "Per block (keyed as segments.json's key): m holds row miles by code in the latest year; s, when present, is the block's miles on every row under its Slow Street designation, which covers rows of any code.",
                   "blocks": components}, end="", ensure_ascii=True, separators=(",", ":"))
    print("  components: %d blocks split by facility code for %d" % (len(components), years[-1]))

    # -- site data ---------------------------------------------------------
    segs, pts_by_key = [], {}
    for c, ys in seg_years.items():
        pts = live_pts.get(c) or (slow_cnns.get(c) or {}).get("pts") or next(
            (s["pts"] for d in slow_by_year.values() for cc, s in d.items() if cc == c and s["pts"]), None)
        if not pts:
            continue
        rec = None
        for s in reversed(snaps):
            if c in s["cnns"]:
                rec = s["cnns"][c]
                break
        pts_by_key[c] = pts
        seg = {"key": c, "cnn": None if c.startswith("P:") else c,
               "name": (rec or {}).get("street") or next((s["street"] for d in slow_by_year.values() for cc, s in d.items() if cc == c), None),
               "pts": [[round(x, 5), round(y, 5)] for x, y in pts],
               "y": "".join(ys.get(Y, "0") for Y in years)}
        if ys.get("presidio"):
            seg["presidio"] = True
        if not c.startswith("P:") and c in bci:
            seg["bci"] = bci[c]
        segs.append(seg)
    site = {"years": years, "mileBasis": BASIS, "codes": {"0": "absent", "1": "CLASS I path", "2": "CLASS II painted lane", "3": "CLASS III sharrow",
                                      "4": "CLASS IV separated lane", "S": "Slow Street", "?": "present, class unknown"},
            "all_ages_codes": sorted({CODE[c] for c in PLAN_ALL_AGES_CLASSES} | ({"S"} if INCLUDE_SLOW_STREETS else set())),
            "definitions": {"default": DEFAULT_DEFINITION,
                            "plan": "code in all_ages_codes, or code in ('2', '3') and the segment's bci > %d (bci is the 2023 Draft Bike Comfort Index, one snapshot for all years); a block's miles are counted per direction row" % PLAN_BCI_THRESHOLD},
            "plan_bci_threshold": PLAN_BCI_THRESHOLD,
            "series": {"years": years,
                       "plan": {"network_miles": [r["network_miles"] for r in rows], "all_ages_miles": [r["all_ages_miles"] for r in rows],
                                "resident_share": [r["resident_share"] for r in rows],
                                "schools_within_reach": [r["schools_within_reach"] for r in rows], "libraries_within_reach": [r["libraries_within_reach"] for r in rows]},
                       "schools_total": [r["schools_total"] for r in rows], "libraries_total": [r["libraries_total"] for r in rows]},
            "note": "One string per segment, one character per year in `years`; the class shown is the best class on the block. `cnn` is null for off-street paths the layer carries without one; `presidio` marks paths on federal land.",
            "sources": {"network": sources["network"], "snapshots": [{"captured": s["captured"], "url": s["url"]} for s in sources["snapshots"]],
                        "slow_streets": sources["slow_streets"]["dataset"]},
            "segments": segs}
    # Criterion E2 (pipeline/transportation-data-audit-criteria.md): a
    # segment keyed by a CNN lies on that active centerline block, within
    # 50 ft. A regression stops the build here rather than reaching the map.
    cl = snapper.cl
    off = [(s["cnn"], s["name"], "retired" if s["cnn"] not in cl.active else "%.0f m" % cl.max_dist(s["pts"], s["cnn"]))
           for s in segs if s["cnn"] and (s["cnn"] not in cl.active or cl.max_dist(s["pts"], s["cnn"]) > TOLERANCE_M)]
    if off:
        raise SystemExit("E2: %d segments are not on their CNN's active centerline block within 50 ft: %s"
                         % (len(off), "; ".join("%s %s (%s)" % o for o in off[:20])))
    stable.write_json(SITE_OUT, site, end="", ensure_ascii=True, separators=(",", ":"))
    print("  site data: %d segments, %.1f KB" % (len(segs), os.path.getsize(SITE_OUT) / 1024))
    pop_latest = {(lon, lat): p for lon, lat, p in blocks}  # the last year's ACS-spread population per 2020 block
    write_map_data(years, segs, pts_by_key, aa_years, aa_miles_latest, first_reach, within_years, b20, schools, libs, sources, reached_out, pop_latest)

    write_md(out)
    print("  wrote %s/history.{json,md}" % OUT)


def school_level(soc_type):
    """CDE's school type folded to the level a parent would name (Bryan,
    2026-09-23: "make sure this includes elementary, middle and high
    schools"). Alternative, continuation, special education, court and
    county community schools are 'other'."""
    t = soc_type or ""
    if t.startswith("Elem"):
        return "elementary"
    if "Middle" in t or "Junior High" in t:
        return "middle"
    if t.startswith("High Schools") or t.startswith("Continuation High"):
        return "high"
    if t.startswith("K-12"):
        return "k12"
    if t.startswith("Elementary School (Private)"):
        return "elementary"
    return "other"


def lit_years(ys, last):
    """A point's years within reach as the map reads them: the first year (0 for never) and the later years, through `last`, it is out of reach."""
    if not ys:
        return 0, []
    first = min(ys)
    return first, [Y for Y in range(first, last + 1) if Y not in ys]


def is_lit(first, off, Y):
    """The map's rule, as site/src/bike-history.mjs applies it."""
    return bool(first) and first <= Y and Y not in off


def reach_checks(years, rows, within_years, b20, schools_in, libs_in, pop20_by_year):
    """The reach's own quality checks; exits before anything is written when one fails.

    Also 3, below: the dropped pandemic miles and the all-ages series agree.

    1. In every year a dropped pandemic Slow Street stood, reach at every
       distance is at least what it is without them, and some were counted.
    2. The map's encoding (lit_years) lights a point in exactly the years it
       is within reach, and the lit points add up to each year's figures:
       residents from 2020 on (earlier years spread population over 2010
       blocks, which the map does not draw), schools and branches every year."""
    errs = []
    # 3. The dropped pandemic miles stand only while the corridors did, and
    #    the all-ages series falls by them in the year they went: its change
    #    from the year before equals the change without them less the drop.
    by_year = {r["year"]: r for r in rows}
    dy = slow_corridors.DROPPED_YEAR
    for r in rows:
        if r["pandemic_slow_street_miles"] and not 2020 <= r["year"] < dy:
            errs.append("%d: %.1f pandemic Slow Street miles outside 2020-%d" % (r["year"], r["pandemic_slow_street_miles"], dy - 1))
    if dy in by_year and dy - 1 in by_year:
        a, b = by_year[dy - 1], by_year[dy]
        drop = b["pandemic_dropped_miles"]
        rest = (b["all_ages_miles"] - b["pandemic_slow_street_miles"]) - (a["all_ages_miles"] - a["pandemic_slow_street_miles"])
        if not 5 <= drop <= 60:
            errs.append("%d: %.1f pandemic Slow Street miles dropped, outside 5-60" % (dy, drop))
        if abs((b["all_ages_miles"] - a["all_ages_miles"]) - (rest - drop)) > 0.25:
            errs.append("%d: all-ages miles changed %.1f; without the pandemic streets %.1f, less %.1f dropped"
                        % (dy, b["all_ages_miles"] - a["all_ages_miles"], rest, drop))
    for r in rows:
        w = r.get("reach_without_dropped_slow_streets")
        if r["year"] in (2020, 2021) and not r["dropped_slow_street_blocks_in_reach"]:
            errs.append("%d: no dropped pandemic Slow Street block counted in reach" % r["year"])
        for tid, wo in (w or {}).items():
            b = r["reach_by_threshold"][tid]
            for f in ("residents_within_reach", "schools_within_reach", "libraries_within_reach"):
                if b[f] < wo[f]:
                    errs.append("%d %s: %s %d with the dropped Slow Streets, %d without" % (r["year"], tid, f, b[f], wo[f]))
    for tid, kinds in within_years.items():
        enc = {kind: {k: lit_years(ys, years[-1]) for k, ys in d.items()} for kind, d in kinds.items()}
        for kind, d in kinds.items():
            for k, ys in d.items():
                first, off = enc[kind][k]
                bad = [Y for Y in years if is_lit(first, off, Y) != (Y in ys)]
                if bad:
                    errs.append("%s %s %s: lit %s out of reach, or dark within it" % (tid, kind, k, bad[:3]))
        for Y in years:
            b = by_year[Y]["reach_by_threshold"][tid]
            sch = sum(1 for s in schools_in(Y) if is_lit(*enc["schools"].get(s["cds"], (0, [])), Y))
            lib = sum(1 for l in libs_in(Y) if is_lit(*enc["libraries"].get(l["name"], (0, [])), Y))
            if sch != b["schools_within_reach"] or lib != b["libraries_within_reach"]:
                errs.append("%d %s: map lights %d schools and %d branches, the figures say %d and %d"
                            % (Y, tid, sch, lib, b["schools_within_reach"], b["libraries_within_reach"]))
            if Y in pop20_by_year:
                pop = pop20_by_year[Y]
                res = sum(pop.get((x["lon"], x["lat"]), 0) for x in b20.records if is_lit(*enc["blocks"].get(x["geoid"], (0, [])), Y))
                if abs(res - b["residents_within_reach"]) > 1:
                    errs.append("%d %s: map lights %.0f residents, the figures say %d" % (Y, tid, res, b["residents_within_reach"]))
    if errs:
        raise SystemExit("reach checks: %d failed, nothing written:\n  %s" % (len(errs), "\n  ".join(errs[:30])))
    print("  reach checks: passed (dropped Slow Streets only add reach; map dots match every year's figures at every distance)")


def write_map_data(years, segs, pts_by_key, aa_years, aa_miles_latest, first_reach, within_years, b20, schools, libs, sources, reached_out, pop_latest):
    """Two compact files for the animated map on the site's transportation page.

    all-ages.geojson: every block that was all-ages in any year, with the first
    year it was (`first`), the last year if it stopped being (`until`), its
    qualifying row miles in the latest year it qualified (`miles`, the plan's
    unit), and its key, which is the CNN or the endpoint key of an off-street
    path.

    reach.json: the 2020 census blocks (interior point and 2020 population),
    the K-12 schools and the library branches, each with the first year an
    all-ages block came within REACH_MILES of it, the key of the block that
    did, and the later years it was out of reach again, at every distance. Blocks are the 2020 census throughout, so the map holds one set of
    points; the table's population by year is the ACS estimate, not this."""
    # The per-segment code in segments.json is the BEST class on the block;
    # which blocks qualify, and for how many row miles, comes from the year
    # loop (aa_years, aa_miles_latest), not from that code.
    name_of = {(s["cnn"] or path_key([[x, y] for x, y in s["pts"]])): s["name"] for s in segs}
    feats = []
    for c, yset in aa_years.items():
        pts = pts_by_key.get(c)
        if not pts:
            continue
        ys = sorted(yset)
        props = {"key": c, "cnn": None if c.startswith("P:") else c, "name": name_of.get(c), "first": ys[0],
                 "miles": round(aa_miles_latest.get(c, 0.0), 4)}
        if ys[-1] != years[-1]:
            props["until"] = ys[-1]
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": [[round(x, 5), round(y, 5)] for x, y in pts]}})
    feats.sort(key=lambda f: (f["properties"]["first"], f["properties"]["key"]))
    stable.write_json(os.path.join(os.path.dirname(SITE_OUT), "all-ages.geojson"), {"type": "FeatureCollection", "mileBasis": BASIS, "years": years, "reach_miles": REACH_MILES,
                   "note": "Blocks that were all-ages under the plan's definition in any year since %d. `first` is the first such year, `until` the last when the block later stopped being all-ages, `miles` its qualifying row miles (per direction row, the plan's unit) in the latest such year." % years[0],
                   "sources": {"network": sources["network"], "slow_streets": sources["slow_streets"]["dataset"]},
                   "features": feats}, end="", ensure_ascii=True, separators=(",", ":"))
    fr = first_reach[DEFAULT_REACH]
    others = [t["id"] for t in REACH_THRESHOLDS if t["id"] != DEFAULT_REACH]
    year_at = lambda tid, kind, k: first_reach[tid][kind].get(k, (0, None))[0]
    # The years out of reach after the first, which the map greys the point in.
    off_at = lambda tid, kind, k: lit_years(within_years[tid][kind].get(k), years[-1])[1]
    for tid in within_years:
        for kind in within_years[tid]:
            for k in within_years[tid][kind]:
                assert lit_years(within_years[tid][kind][k], years[-1])[0] == year_at(tid, kind, k), (tid, kind, k)
    ids = [DEFAULT_REACH] + others
    blocks = [[round(b["lon"], 5), round(b["lat"], 5), b["pop"], fr["blocks"].get(b["geoid"], (0, None))[0], fr["blocks"].get(b["geoid"], (0, None))[1] or ""]
              + [year_at(tid, "blocks", b["geoid"]) for tid in others]
              + [int(round(pop_latest.get((b["lon"], b["lat"]), b["pop"])))]
              + [off_at(tid, "blocks", b["geoid"]) for tid in ids]
              for b in b20.records if b["pop"] > 0]
    out = {"years": years, "reach_miles": REACH_MILES, "count_date": COUNT_DATE,
           "thresholds": REACH_THRESHOLDS, "default_reach": DEFAULT_REACH, "reached_earlier_out_latest": reached_out,
           "note": ("`reach` is the first year an all-ages block lay within reach_miles (walking) of the point; 0 means never. `off` lists the later years it was out of reach again (a dropped Slow Street or a removed bikeway), in which the map greys it; a point is lit in year Y when 0 < reach <= Y and Y is not in `off`. "
                    "`near` is the key of the block that first reached it, blank for points reached from the %d baseline; a key \"SS:<cnn>\" is a pandemic Slow Street block SFMTA dropped in %d (site/data/bike-history/removed.json). "
                    "`reach_<id>` and `off_<id>` on a block row, and `reach_by` and `off_by` on a school or branch, give the same at each other distance in `thresholds`." % (years[0], slow_corridors.DROPPED_YEAR)),
           "blocks": {"source": sources["population"]["2020_blocks"], "columns": ["lon", "lat", "pop2020", "reach", "near"] + ["reach_%s" % tid for tid in others] + ["pop_latest", "off"] + ["off_%s" % tid for tid in others], "rows": blocks,
                      "pop_latest": "the last year's population on the row's basis (ACS block-group totals spread over 2020 blocks), which the explorer's residents share uses so its default state matches the year figures"},
           "schools": [{"name": s["school"], "level": school_level(s.get("soc_type")), "private": bool(s.get("private")), "lon": round(s["lon"], 5), "lat": round(s["lat"], 5), "open": s["open"], "closed": s["closed"],
                        "reach": fr["schools"].get(s["cds"], (0, None))[0], "near": fr["schools"].get(s["cds"], (0, None))[1],
                        "reach_by": {tid: year_at(tid, "schools", s["cds"]) for tid in others},
                        "off": off_at(DEFAULT_REACH, "schools", s["cds"]), "off_by": {tid: off_at(tid, "schools", s["cds"]) for tid in others}} for s in schools],
           "libraries": [{"name": l["name"], "lon": round(l["lon"], 5), "lat": round(l["lat"], 5), "closed_from": l["closed_from"], "reopens": l["reopens"],
                          "reach": fr["libraries"].get(l["name"], (0, None))[0], "near": fr["libraries"].get(l["name"], (0, None))[1],
                          "reach_by": {tid: year_at(tid, "libraries", l["name"]) for tid in others},
                          "off": off_at(DEFAULT_REACH, "libraries", l["name"]), "off_by": {tid: off_at(tid, "libraries", l["name"]) for tid in others}} for l in libs.records],
           "sources": {"schools": {k: sources["schools"][k] for k in ("source", "url", "queried")},
                       "libraries": {k: sources["libraries"][k] for k in ("source", "dataset", "queried")},
                       "blocks": sources["population"]["2020_blocks"]}}
    p = os.path.join(os.path.dirname(SITE_OUT), "reach.json")
    stable.write_json(p, out, end="", ensure_ascii=True, separators=(",", ":"))
    print("  map data: %d all-ages blocks, %d census blocks, %d schools, %d libraries; reach.json %.1f KB"
          % (len(feats), len(blocks), len(out["schools"]), len(out["libraries"]), os.path.getsize(p) / 1024))


def pct(v):
    return "—" if v is None else "%.0f%%" % (100 * v)


def write_md(o):
    rows, S = o["rows"], o["sources"]
    d = o["disagreements"]["published_vs_centerline"]
    c = o.get("plan_comparison_2024")
    L = ["# The bike network by year, %d–%d" % (o["years"][0], o["years"][-1]), "",
         "Miles of bikeway, the miles that meet the Biking and Rolling Plan's all-ages test, and how many residents, K-12 schools (public and private) and library branches sit within a %.2f-mile walk of an all-ages segment. Generated %s by `tools/bike-network/bike-network-history.py`." % (o["method"]["reach_miles"], o["generated"]), "",
         "Every figure uses the [plan](%s)'s definitions. **Miles are counted per direction row**, as SFMTA's bikeway layer holds them and as the plan's 472 miles (printed p. 20) are counted; a two-way street with a lane each way counts twice. **All-ages** is the plan's high-quality test (printed p. 24; [Appendix G](https://www.sfmta.com/media/41946/download)): Class I, Class IV and Slow Streets; Class II with Bike Comfort Index above %d; Class III with traffic calming and BCI above %d. The calming condition is in no published dataset and is not applied, so Class III rows are admitted on BCI alone; the third column is their size." % (d["plan_printed"]["source"], S["bci"]["threshold"], S["bci"]["threshold"]), "",
         "| Year | Network miles | All-ages miles | of which Class III by BCI alone | Residents within reach | K-12 schools within reach | Library branches within reach | Rests on |",
         "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for r in rows:
        L.append("| %d | %.1f | %.1f | %.1f | %s (%s of %s) | %d of %d (%s) | %d of %d (%s) | %s |" % (
            r["year"], r["network_miles"], r["all_ages_miles"], r["all_ages_by_bci_class_iii_miles"], pct(r["resident_share"]),
            format(r["residents_within_reach"], ","), format(r["residents_total"], ","),
            r["schools_within_reach"], r["schools_total"], pct(r["school_share"]),
            r["libraries_within_reach"], r["libraries_total"], pct(r["library_share"]), r["tier"]))
    L += ["", "Denominators: residents are every census block in San Francisco County; schools are K-12 schools, public ones of the counted types and private ones from DataSF, open on %s of the year; libraries are SFPL branches plus the Main Library open that year." % o["method"]["count_date"], ""]
    T, bs = o["reach_thresholds"], o["block_source"]
    L += ["## Reach at four distances", "",
          "The table above uses the plan's quarter mile. The population-weighted average San Francisco block is %d feet, intersection to intersection ([street centerlines](%s), read %s; [census blocks](%s); `%s`), so %s." % (
              bs["measured_ft"], bs["url"], bs["read"], bs["census_url"], bs["script"], bs["rounding"]), "",
          "| Year | " + " | ".join("Residents, %s" % t["label"] for t in T) + " | " + " | ".join("Schools, %s" % t["label"] for t in T) + " | " + " | ".join("Libraries, %s" % t["label"] for t in T) + " |",
          "| --- |" + " ---: |" * (3 * len(T))]
    for r in rows:
        b = r["reach_by_threshold"]
        L.append("| %d | %s | %s | %s |" % (r["year"],
                                           " | ".join(pct(b[t["id"]]["resident_share"]) for t in T),
                                           " | ".join("%d of %d" % (b[t["id"]]["schools_within_reach"], r["schools_total"]) for t in T),
                                           " | ".join("%d of %d" % (b[t["id"]]["libraries_within_reach"], r["libraries_total"]) for t in T)))
    L.append("")
    L += ["## Check against the plan's printed figures", "",
          "The plan prints (p. 20, [primary — read 2026-09-22]) a network that \"has grown from 302 miles in 2010 to 472 miles today\", with \"41 miles of protected bike lanes, 32 miles of Slow Streets, and seven miles of car-free streets\"; p. 24 and Appendix G report 80% of residents within a quarter mile of a high-quality facility in early 2024. Against this table:", "",
          "| Figure | Plan | This table | Note |", "| --- | ---: | ---: | --- |"]
    if c:
        nm, pm, sm = c["network_miles"], c["protected_miles"], c["slow_street_miles"]
        L += ["| Network miles | %d | %.1f (%d); %.1f (%d) | live rows' geometry summed; the layer's own LENGTH column sums to %.1f and LENGTH_FT to %.1f |"
              % (nm["plan_p20"], nm["ours_latest"], rows[-1]["year"], nm["ours_2024"], c["year"], d["layer_row_sum_LENGTH"]["miles"], d["layer_row_sum_LENGTH_FT"]["miles"]),
              "| Protected (Class IV) miles | %d | %.1f (%d); %.1f (%d) | SFMTA's blog gave %d separated miles on %s; counted once per block, %.1f miles in %d; %.1f row miles in 2021; %.1f miles carry no install year; %.1f live miles are contraflow |"
              % (pm["plan_p20"], pm["ours_2024_class_iv"], c["year"], pm["ours_latest_class_iv"], rows[-1]["year"], d["sfmta_published"]["separated_miles"], d["sfmta_published"]["date"],
                 pm["ours_2024_class_iv_centerline"], c["year"], pm["ours_2021_class_iv"] or 0, pm["ours_2024_class_iv_with_no_install_year"], pm["live_class_iv_contraflow_miles"]),
              "| Slow Street miles | %d | %.1f (%d) | the dataset's implemented segments sum to %.1f centreline miles by their own geometry, counted in both directions as the plan does |"
              % (sm["plan_p20"], sm["ours_2024_both_directions"], c["year"], sm["dataset_centerline"]),
              "| Car-free miles | %d | — | %s |" % (c["car_free_miles"]["plan_p20"], c["car_free_miles"]["note"]),
              "| Residents within a quarter mile, %d | %s | %s | the gap is taken up below |" % (c["year"], pct(c["plan_reported_share"]), pct(c["ours_plan_definition_share"])),
              "| Residents in equity priority communities within a quarter mile, %d | %s | — | %s |" % (c["year"], pct(c["plan_reported_epc_share"]), c["epc_comparison"]),
              "", "Protected miles: %s" % pm["note"], ""]
        if c["likely_causes"]:
            L += ["The %d-point gap on residents is a finding. The likeliest causes, the ones that push this table's figure %s the plan's first %s:"
                  % (abs(c["gap_points"]), "above" if c["gap_points"] < 0 else "below", c["tag"]), ""] + ["- " + x for x in c["likely_causes"]]
        L.append("")
    L += ["## Centreline miles, one length per block", "",
          "For a reader who wants the network counted once per block rather than per direction row.", "",
          "| Year | Network centreline miles | All-ages centreline miles | Direction rows | Blocks |", "| --- | ---: | ---: | ---: | ---: |"]
    for r in rows:
        L.append("| %d | %.1f | %.1f | %s | %s |" % (r["year"], r["network_centerline_miles"], r["all_ages_centerline_miles"], format(r["rows"], ","), format(r["blocks"], ",")))
    L.append("")
    L += ["## What each year rests on", "",
          "| Year | Network figures | Population figures |", "| --- | --- | --- |"]
    for r in rows:
        L.append("| %d | %s | %s |" % (r["year"], r["network_basis"], r["population_basis"]))
    L += ["", "Per-year notes on the network reconstruction (counts of blocks):", ""]
    for r in rows:
        if r["network_notes"]:
            L.append("- %d: %s" % (r["year"], "; ".join("%s: %d" % kv for kv in sorted(r["network_notes"].items()))))
    L += ["", "## All-ages miles, split", "", "| Year | Bikeway rows all-ages | of which Class II by BCI | of which Class III by BCI | of which in the Presidio (federal land) | of which other paths with no CNN | Slow Street miles added on bikeway blocks (rows not already qualifying) | Slow Street miles not in the bikeway layer | Class I/IV and Slow Streets only (no BCI test) | Miles present but class unknown |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        L.append("| %d | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f |" % (r["year"], r["all_ages_bikeway_miles"], r["all_ages_by_bci_class_ii_miles"], r["all_ages_by_bci_class_iii_miles"],
                                                                                          r["presidio_all_ages_miles"], r["other_no_cnn_path_all_ages_miles"],
                                                                                          r["slow_street_miles_on_bikeway_blocks"], r["slow_street_miles_not_in_bikeway_layer"], r["all_ages_strict_miles"], r["miles_class_unknown"]))
    L += ["", "The layer carries %d off-street paths with no street segment number (CNN): the Presidio's trails on federal land (NOTES says PRESIDIO), and paths elsewhere, named (Kirkham Path, SFSU Path, Vicente Path, Cesar Chavez St, San Jose Ave, McCoppin Stub Path) or unnamed. Both are in every figure above (INCLUDE_PRESIDIO is on); the Presidio column (every row whose NOTES says PRESIDIO, paths and signed routes alike) lets the all-ages figure be read without federal land. In %d the Presidio's bikeways are %.1f of %.1f network miles."
          % (o["no_cnn_paths"], rows[-1]["year"], rows[-1]["presidio_network_miles"], rows[-1]["network_miles"])]
    if o["retired_block_streets"]:
        L += ["", "In %d, %.1f network miles lie on blocks the city's centerline has retired with no active block along the same line: %s. "
              "They keep SFMTA's line and lose the retired CNN, so no plan block can be marked built by them, and they are counted in every "
              "figure above but not in the paths column."
              % (rows[-1]["year"], rows[-1]["retired_block_network_miles"], ", ".join(o["retired_block_streets"]))]
    L += ["", "Network miles count the SFMTA bikeway layer only; Slow Street blocks outside that layer are added to all-ages miles and are not in the network total.", ""]
    for a, b in zip(rows, rows[1:]):
        if b["all_ages_miles"] - a["all_ages_miles"] < 5:
            continue
        slow_add = ((b["slow_street_miles_on_bikeway_blocks"] + b["slow_street_miles_not_in_bikeway_layer"])
                    - (a["slow_street_miles_on_bikeway_blocks"] + a["slow_street_miles_not_in_bikeway_layer"]))
        why = ""
        if b["year"] == 2020:
            why = ("The Slow Streets dataset dates its first segments to April 2020, the pandemic-era program, but it holds only the corridors that were "
                   "kept when the SFMTA Board approved the permanent program (December 6, 2022 per [SFMTA's program page](https://www.sfmta.com/projects/slow-streets-program), "
                   "read 2026-09-22; the Board record is [unretrieved — verify]). The barricade-era corridors removed before then are not in it, so the 2020 and 2021 "
                   "all-ages figures are a floor. [inference — mine]")
        L.append("The step from %d to %d, %.1f to %.1f all-ages miles, is %.1f miles of Slow Streets and %.1f miles of bikeway rows meeting the plan's test. %s"
                 % (a["year"], b["year"], a["all_ages_miles"], b["all_ages_miles"], slow_add,
                    b["all_ages_bikeway_miles"] - a["all_ages_bikeway_miles"], why))
        L.append("")
    L += ["## Where sources disagree", "",
          "- The plan prints [472 miles](%s) (p. 20, read %s); SFMTA published [%d miles, %d of them separated](%s) on %s. Summing every live row's geometry gives %.1f miles over %s rows; the layer's `LENGTH` column sums to %.1f and its `LENGTH_FT` column to %.1f, so the layer disagrees with itself by three miles. Counted once per block the network is %.1f centreline miles over %s blocks. **The table uses row miles from the geometry**, the plan's unit, and prints centreline miles beside them. [SFMTA ArcGIS — queried %s]"
          % (d["plan_printed"]["source"], d["plan_printed"]["read"], d["sfmta_published"]["miles"], d["sfmta_published"]["separated_miles"], d["sfmta_published"]["source"], d["sfmta_published"]["date"],
             d["layer_row_geometry"]["miles"], format(d["layer_row_geometry"]["rows"], ","), d["layer_row_sum_LENGTH"]["miles"], d["layer_row_sum_LENGTH_FT"]["miles"],
             d["layer_centerline"]["miles_from_geometry"], format(d["layer_centerline"]["blocks"], ","), d["layer_centerline"]["queried"]),
          "- DataSF's [Schools](https://data.sf.gov/d/7e7j-59qk) lists %s active public schools; the CDE archive gives %d open on %d-%s of the counted types. The table uses the CDE archive, because it carries closure dates; DataSF's count includes preschools, adult schools and other types the table leaves out. [DataSF 7e7j-59qk — queried %s]"
          % (o["disagreements"]["schools_active_count"]["datasf_7e7j-59qk_active_public"], rows[-1]["schools_total"], rows[-1]["year"], o["method"]["count_date"], S["schools"]["cross_check"]["queried"]),
          "", "## Where the data no longer supports the analysis", ""]
    L += ["- " + x for x in o["limits"]]
    L += ["", "## Sources", "",
          "- Network: [SFMTA bikeway layer](%s), attributes queried %s, geometry queried %s. Archived copies of [DataSF ygmz-vaxd](https://data.sf.gov/d/ygmz-vaxd) from the Internet Archive:" % (S["network"]["url"], S["network"]["queried"], S["network"]["geometry_queried"])]
    for s in S["snapshots"]:
        L.append("  - [%s](%s): %d blocks, %s rows, %.1f row miles (%.1f centreline)%s%s%s" % (s["captured"], s["url"], s["blocks"], format(s["rows"], ","), s["row_miles"], s["centerline_miles"],
                                                                          ", release loaded %s" % s["data_loaded_at"] if s["data_loaded_at"] else "",
                                                                          " (live layer)" if s["kind"] == "live" else "",
                                                                          "; %d blocks carried through a gap" % s["blocks_filled_through_gap"] if s["blocks_filled_through_gap"] else ""))
    ss = S["slow_streets"]
    L += ["- Slow Streets: [DataSF %s](%s), queried %s; %d implemented segments, %d of them undated and counted from %s." % (
        SLOW_STREETS_ID, ss["dataset"], ss["queried"], ss["implemented_segments"], ss["undated_segments"], ss["undated_segments_counted_from"])]
    P = S["population"]
    L += ["- Population: 2010 blocks from [TIGERweb](%s) (%s blocks, %s people), queried %s; 2020 blocks from [DataSF %s](%s) (%s blocks, %s people), queried %s; ACS 5-year block-group totals 2015–2024 from [data.census.gov](https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000), queried %s (county totals: %s)." % (
        P["2010_blocks"]["url"], format(P["2010_blocks"]["blocks"], ","), format(P["2010_blocks"]["total"], ","), P["2010_blocks"]["queried"],
        BLOCKS_2020_ID, P["2020_blocks"]["dataset"], format(P["2020_blocks"]["blocks"], ","), format(P["2020_blocks"]["total"], ","), P["2020_blocks"]["queried"],
        P["acs5_block_groups"]["queried"], ", ".join("%s: %s" % (y, format(v, ",")) for y, v in P["acs5_block_groups"]["totals"].items()))]
    sc = S["schools"]
    L += ["- Schools: [CDE Public Schools and Districts file](%s), %s capture from the Internet Archive (the [live download](https://www.cde.ca.gov/ds/si/ds/pubschls.asp) answers with a firewall challenge page), read %s; %d San Francisco rows. Counted types: %s. Left out by type: %s. %d rows of a counted type lack a coordinate or an open date; %d of those were open in the window and are left out: %s." % (
        sc["url"], CDE_FILE_DATE, sc["queried"], sc["sf_rows"], ", ".join(sc["counted_types"]),
        ", ".join("%s (%d)" % kv for kv in sorted(sc["skipped_by_type"].items())), sc["counted_type_but_no_coordinates_or_open_date"],
        len(sc["of_those_open_in_window"]), ", ".join(sc["of_those_open_in_window"]) or "none")]
    lb = S["libraries"]
    L += ["- Libraries: [DataSF %s City Facilities](%s), queried %s; %d branches including the Main Library. Not counted: %s. Closures: %s." % (
        FACILITIES_ID, lb["dataset"], lb["queried"], lb["branches_including_main"], lb["not_counted"],
        "; ".join("%s closed from %d%s ([SFPL](%s))" % (k, v["closed_from"], " to %d" % v["reopens"] if v["reopens"] else ", not yet reopened", v["source"]) for k, v in lb["closures"].items()))]
    B = S["bci"]
    L += ["- Bike Comfort Index: [%s](%s), %d segments, queried %s; field `%s`, threshold %d. %s. The combined `bci` is the lower of the two directional scores (`bci_ft`, `bci_tf`) on %s of %s segments, so it is the stricter reading; %d live Class II/III rows (%.1f miles) would change verdict under one directional score in its place. %d bikeway blocks with Class II/III rows carry no score (%d rows, %.1f miles) and are counted as not qualifying." % (
        B["name"], B["url"], B["segments"], B["queried"], B["field"], B["threshold"], B["note"].capitalize(),
        format(B["combined_is_directional_minimum_segments"], ","), format(B["segments"], ","),
        B["directional_sensitivity"]["class_ii_iii_rows_that_flip"], B["directional_sensitivity"]["miles"],
        B["unscored"]["bikeway_blocks_with_class_ii_iii_rows"], B["unscored"]["rows"], B["unscored"]["miles"])]
    tw = d["single_row_two_way_blocks"]
    L += ["- Direction rows: %d live blocks (%.1f row miles) are held as one row marked two-way (DIRECT=2W): %s. Row counting gives each one length where a street with a lane each way gets two; it is kept because it reproduces the plan's 472." % (
        tw["blocks"], tw["row_miles"], ", ".join("%s %d" % kv for kv in sorted(tw["by_class"].items())))]
    L += ["", "## Method", ""] + ["- **%s**: %s" % (k, v if not isinstance(v, dict) else v.get("rule") or "; ".join("%s: %s" % kv for kv in v.items()))
                                  for k, v in o["method"].items() if k not in ("count_date", "reach_miles", "start_year")]
    stable.write_text(os.path.join(OUT, "history.md"), "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
