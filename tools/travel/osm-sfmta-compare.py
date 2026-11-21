#!/usr/bin/env python3
"""Where SFMTA's bikeway layer and OpenStreetMap disagree, block by block.

Two independent records of the same streets. SFMTA's layer is the city's own
and is what the city gets held to; OpenStreetMap is edited continuously by
people who ride here. Neither is the truth. Where they disagree, one of them
is wrong about a block somebody rides, and that block is worth going to look
at.

This joins them and says, per block, whether they agree and which way they
differ. It does not decide who is right -- that is a ride, not a query.

THREE THINGS THE JOIN HAS TO GET RIGHT, each of which was got wrong first:

1. MATCH ON NAME. An earlier pass took the nearest OSM way within 25 m of a
   block's midpoint with no name check. In SoMa the cross street sits within
   25 m of every midpoint, so 8th Street blocks matched Howard and Harrison
   and inherited their paint: sixteen blocks of protected bikeway that both
   datasets agree on were reported as a disagreement. A candidate must carry
   the same normalised street name AND come within TOLERANCE_M.

2. MEASURE TO THE LINE, NOT TO ITS VERTICES. SFMTA stores a block as two or
   three points. An OSM way sitting exactly on top of a long straight block
   can be 100 m from the nearest SFMTA vertex, so vertex distance reported
   777 co-located ways as absent from SFMTA's layer. With point-to-segment
   distance the same measurement puts 95% of ways within 25 m and leaves a
   clean break above it.

3. KEEP THE SUFFIX, MOSTLY. 5th Ave and 5th St are different streets, so
   normalising both to "5TH" merges them. The suffix is kept, and dropped
   only as a second pass when exactly one SFMTA street survives the drop --
   which is what matches OSM's "Broadway" to SFMTA's "BROADWAY ST" without
   also merging the numbered streets.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import csv
import io
import datetime as dt
import json
import math
import pathlib
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sfdata import fetch  # noqa: E402
from lib import pipeline_state, stable  # noqa: E402

ROOT = pathlib.Path(paths.ROOT)
OUT = ROOT / "out" / "osm-compare"
CACHE = ROOT / "data" / "osm-cache"

BIKEWAY = "ygmz-vaxd"
TOLERANCE_M = 25.0
SAMPLES = (0.2, 0.4, 0.6, 0.8)
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "sf-works-research/1.0 (https://github.com/fryanpan/sf-works-site)"

SFMTA_CLASS = {
    "CLASS I": "path",
    "CLASS II": "painted",
    "CLASS III": "sharrow",
    "CLASS IV": "separated",
}
RANK = {"sharrow": 1, "painted": 2, "separated": 3, "path": 3}

# OSM cycleway values on the same ladder. `track` is a lane physically
# separated from the carriageway; `lane` is paint. Values not listed -- `no`,
# `none`, `separate` (meaning "mapped as its own way") -- declare no bikeway
# on this way.
OSM_BUCKET = {
    "track": "separated", "opposite_track": "separated",
    "lane": "painted", "opposite_lane": "painted",
    "buffered_lane": "painted", "crossing": "painted",
    "shared_lane": "sharrow", "share_busway": "sharrow",
    "opposite": "sharrow", "shared": "sharrow",
}

SUFFIX = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD",
    "DRIVE": "DR", "ROAD": "RD", "WY": "WAY", "TERRACE": "TER",
    "PLACE": "PL", "COURT": "CT", "LANE": "LN", "HIGHWAY": "HWY",
    "PARKWAY": "PKWY", "CIRCLE": "CIR", "ALLEY": "ALY", "PLAZA": "PLZ",
    "SQUARE": "SQ", "JUNIOR": "JR", "SAINT": "ST.", "MOUNT": "MT",
}
DROPPABLE = {"ST", "AVE", "BLVD", "DR", "RD", "WAY", "TER", "PL", "CT",
             "LN", "HWY", "PKWY", "CIR", "ALY", "PLZ", "SQ"}
ORDINAL = {
    "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH",
    "FIFTH": "5TH", "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH",
    "NINTH": "9TH", "TENTH": "10TH", "ELEVENTH": "11TH", "TWELFTH": "12TH",
}

# Streets one dataset renamed and the other did not, and facilities OSM names
# after the path rather than the street it runs on. Each is a judgement, so
# each is written down here rather than inferred: the left side is what OSM
# calls it, the right is SFMTA's name for the same asphalt.
ALIAS = {
    "JOHN F KENNEDY PROMENADE": "JOHN F KENNEDY DR",   # renamed after the 2022 car-free vote
    "HERB CAEN WAY": "THE EMBARCADERO",                # the promenade's honorary name
    "LAKE MERCED BIKE PATH": "LAKE MERCED BLVD",
    "LAKE MERCED NORTHBOUND BIKEWAY": "LAKE MERCED BLVD",
    "GREAT HWY EXTENSION": "GREAT HWY",
    "OCTAVIA BLVD BIKE CONNECTOR": "OCTAVIA BLVD",
}

ALIAS = {" ".join(_k.replace("THE ", "", 1).split()): " ".join(_v.replace("THE ", "", 1).split())
         for _k, _v in ALIAS.items()}

K_LAT = 110540.0
K_LON = 111320.0 * math.cos(math.radians(37.77))


FACILITY_WORDS = ("PATH", "TRAIL", "BIKEWAY", "CONNECTOR")


def _norm_words(name):
    """The mechanical half: spelling, ordinals, suffixes, articles.

    `MC ALLISTER` joins up because SFMTA writes the space and OSM does not,
    and leaving them apart made 45 blocks of one street read as two datasets
    missing each other.
    """
    words = [w for w in re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split() if w]
    joined = []
    for w in words:
        if joined and joined[-1] == "MC":
            joined[-1] = "MC" + w
        else:
            joined.append(w)
    words = [SUFFIX.get(ORDINAL.get(w, w), ORDINAL.get(w, w)) for w in joined]
    while len(words) > 1 and words[-1] == words[-2]:   # SFMTA's "GREAT HWY HWY"
        words.pop()
    words = [re.sub(r"^0+(\d)", r"\1", w) for w in words]
    if words and words[0] == "THE":
        words.pop(0)
    return words


def norm_street(name):
    """`08TH ST`, `8th Street` and `Eighth St` all become `8TH ST`.

    The alias table is consulted twice, because a renamed facility can carry a
    facility word either side of the rename: `Lake Merced Bike Path` has to be
    looked up whole, before PATH is stripped, while `Herb Caen Way...` is
    looked up after punctuation goes. Missing the first pass is what left the
    aliases inert on the run that prompted this.
    """
    if not name:
        return None
    words = _norm_words(name)
    whole = " ".join(words)
    if whole in ALIAS:
        return ALIAS[whole]
    while len(words) > 1 and words[-1] in FACILITY_WORDS:
        words.pop()
    out = " ".join(words)
    return ALIAS.get(out, out) or None


def drop_suffix(n):
    w = n.split()
    return " ".join(w[:-1]) if len(w) > 1 and w[-1] in DROPPABLE else n


def project(lon, lat):
    return (lon * K_LON, lat * K_LAT)


def seg_dist(p, a, b):
    """Metres from a projected point to a projected segment."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


class Segments:
    """Segments grouped by street name, indexed on a grid for lookup."""

    CELL = 100.0  # metres; four times the tolerance

    def __init__(self):
        self.grid = collections.defaultdict(list)
        self.names = set()

    def add(self, name, pts, payload):
        self.names.add(name)
        for a, b in zip(pts, pts[1:]):
            lo_x, hi_x = sorted((a[0], b[0]))
            lo_y, hi_y = sorted((a[1], b[1]))
            for gx in range(int((lo_x - self.CELL) // self.CELL),
                            int((hi_x + self.CELL) // self.CELL) + 1):
                for gy in range(int((lo_y - self.CELL) // self.CELL),
                                int((hi_y + self.CELL) // self.CELL) + 1):
                    self.grid[(name, gx, gy)].append((a, b, payload))

    def near(self, name, p, tol=TOLERANCE_M):
        """`(distance, payload)` for everything on `name` within `tol` of `p`."""
        gx, gy = int(p[0] // self.CELL), int(p[1] // self.CELL)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a, b, payload in self.grid.get((name, gx + dx, gy + dy), ()):
                    d = seg_dist(p, a, b)
                    if d <= tol:
                        out.append((d, payload))
        return out


def osm_sides(tags):
    """`{side: bucket}` for the sides this way declares a bikeway on.

    A suffix like `cycleway:right:buffer` describes a lane rather than
    declaring one, so only the bare keys count.
    """
    out = {}
    for key, value in tags.items():
        parts = key.split(":")
        if parts[0] != "cycleway":
            continue
        if len(parts) == 1:
            side = "both"
        elif len(parts) == 2 and parts[1] in ("left", "right", "both"):
            side = parts[1]
        else:
            continue
        bucket = OSM_BUCKET.get(value)
        if bucket:
            out[side] = bucket
    return out


def osm_class(tags):
    highway = tags.get("highway")
    if highway == "cycleway":
        return "path"
    if highway in ("path", "footway", "track") and tags.get("bicycle") == "designated":
        return "path"
    return max(osm_sides(tags).values(), key=lambda c: RANK[c], default=None)


BIKE_FILTERS = """  way(area.sf)["cycleway"]{newer};
  way(area.sf)["cycleway:right"]{newer};
  way(area.sf)["cycleway:left"]{newer};
  way(area.sf)["cycleway:both"]{newer};
  way(area.sf)["highway"="cycleway"]{newer};
  way(area.sf)["bicycle"="designated"]["highway"~"^(path|footway|track)$"]{newer};"""
AREA = '[out:json][timeout:{t}];\narea["boundary"="administrative"]["admin_level"="6"]["name"="San Francisco"]->.sf;\n'
# A way whose bikeway tag was removed no longer matches the filters, so the
# edited-since check cannot see it. A full re-read at least this often catches those.
FULL_EVERY_DAYS = 30


# overpass-api.de answers a share of requests with 504 Gateway Timeout when it
# is busy (1 of 3 identical edited-since counts on 2026-09-29, each 9-13 s),
# and with 429 when a client asks too often. Both are the server's load, not
# the query, so they are retried after a wait; any other error is not.
RETRY_HTTP = {429, 502, 503, 504}
RETRY_WAITS_S = (20, 60, 120)


def overpass(query, timeout, waits=RETRY_WAITS_S, sleep=None):
    # Overpass refuses curl's and urllib's default agents with a bare 406.
    import socket
    import time
    import urllib.error
    sleep = sleep or time.sleep
    for attempt in range(len(waits) + 1):
        req = urllib.request.Request(
            OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(),
            headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return json.loads(fh.read())
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_HTTP or attempt == len(waits):
                raise
            after = exc.headers.get("Retry-After") if exc.headers else None
            wait = max(waits[attempt], int(after) if after and after.isdigit() else 0)
            why = f"HTTP {exc.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
            if attempt == len(waits):
                raise
            wait, why = waits[attempt], type(exc).__name__
        print(f"  OSM: Overpass {why}; retrying in {wait} s ({attempt + 1} of {len(waits)})")
        sleep(wait)


def osm_changed_since(base):
    """How many bikeway ways in the city were edited after `base` (an Overpass timestamp)."""
    q = AREA.format(t=180) + "(\n" + BIKE_FILTERS.format(newer='(newer:"%s")' % base) + "\n);\nout count;"
    d = overpass(q, 240)
    tags = (d.get("elements") or [{}])[0].get("tags", {})
    return int(tags.get("ways", tags.get("total", 0)))


def fetch_osm(refresh=False, update=False):
    """Every OSM way inside San Francisco that records a bikeway.

    Clipped to the county boundary by Overpass rather than to a bounding box.
    A box around San Francisco reaches into the Marin Headlands, and Conzelman
    Road and the Golden Gate Bridge sidewalks then read as bikeways missing
    from SFMTA's layer, which is true and useless -- they are not SFMTA's.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "sf-bikeways-clipped.json"
    if path.exists() and update and not refresh:
        blob = json.loads(path.read_text())
        base = blob.get("osm3s", {}).get("timestamp_osm_base", "")
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(base.replace("Z", "+00:00"))).days
        try:
            n = osm_changed_since(base)
        except Exception as exc:  # noqa: BLE001
            pipeline_state.record("overpass:sf-bikeways", "failed", version=base, detail=str(exc))
            print(f"  OSM: change check failed ({exc}); using the copy")
            n = 0
        else:
            # "changed" is recorded only once the re-read lands (below): recorded here, a failed re-read would carry
            # this run's time over as last_good and the freshness check would never see the copy age.
            if not (n or age >= FULL_EVERY_DAYS):
                pipeline_state.record("overpass:sf-bikeways", "unchanged",
                                      version=base, detail=f"{n} bikeway ways edited since; copy {age} days old")
        refresh = n > 0 or age >= FULL_EVERY_DAYS
        print(f"  OSM: {n} bikeway ways edited since {base[:10]}; copy {age} days old"
              + (" -> re-reading" if refresh else ""))
    if path.exists() and not refresh:
        blob = json.loads(path.read_text())
        print(f"  OSM: {len(blob['elements'])} ways from cache, planet as of "
              f"{blob.get('osm3s', {}).get('timestamp_osm_base', '?')[:10]}")
        return blob
    query = AREA.format(t=900) + "(\n" + BIKE_FILTERS.format(newer="") + "\n);\nout geom meta;"
    try:
        blob = overpass(query, 900)
    except Exception as exc:  # noqa: BLE001
        # A 5xx or timeout after the retries is Overpass's load (the 2026-11-18 run stopped on a 502 here): keep the
        # copy and build on it, as a failed change check does. Any other error, or no copy to keep, still raises.
        from lib.fetch import is_transient
        if not path.exists() or not is_transient(exc):
            raise
        pipeline_state.record("overpass:sf-bikeways", "failed", detail=f"re-read failed: {exc}; copy kept")
        print(f"  OSM: re-read failed ({exc}); using the copy")
        return json.loads(path.read_text())
    # Overpass answers a query that ran out of time or memory with HTTP 200, a
    # "remark" and whatever it had gathered, so a short answer is a failed read.
    # Either one keeps the copy on disk rather than replacing it.
    old = json.loads(path.read_text()) if path.exists() else None
    held = len(old["elements"]) if old else 0
    if blob.get("remark") or len(blob.get("elements") or ()) < max(held // 2, 1):
        why = (f"Overpass answered {len(blob.get('elements') or ())} ways against {held} held"
               f"{' with the remark: ' + blob['remark'][:200] if blob.get('remark') else ''}")
        if old is None:
            raise SystemExit("FAIL: " + why)
        pipeline_state.record("overpass:sf-bikeways", "failed", detail=why + "; copy kept")
        print(f"  OSM: {why}; keeping the copy from {old.get('osm3s', {}).get('timestamp_osm_base', '?')[:10]}")
        return old
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(blob))
    tmp.replace(path)
    pipeline_state.record("overpass:sf-bikeways", "changed", version=blob.get("osm3s", {}).get("timestamp_osm_base"),
                          detail=f"{len(blob['elements'])} bikeway ways re-read")
    print(f"  OSM: {len(blob['elements'])} ways fetched")
    return blob


def load_sfmta():
    """One record per block, both directions folded into it."""
    sf = fetch(BIKEWAY)
    blocks = {}
    for r in sf.rows:
        cls = SFMTA_CLASS.get(r.get("facility_t"))
        shape = r.get("shape")
        if not cls or not shape:
            continue
        geom = shape if isinstance(shape, dict) else json.loads(shape.replace("'", '"'))
        parts = (geom["coordinates"] if geom["type"] == "MultiLineString"
                 else [geom["coordinates"]])
        cnn = str(r.get("cnn") or "")
        key = cnn or f"anon{len(blocks)}"
        b = blocks.setdefault(key, {
            "cnn": key, "street": r.get("streetname", ""),
            "name": norm_street(r.get("streetname")),
            "from": r.get("from_st", ""), "to": r.get("to_st", ""),
            "dirs": {}, "installed": r.get("install_yr") or "",
            "updated": r.get("update_yr") or "", "parts": parts,
        })
        b["dirs"][r.get("dir") or "-"] = cls
        if (r.get("update_yr") or "") > b["updated"]:
            b["updated"] = r.get("update_yr") or ""
    for b in blocks.values():
        b["cls"] = max(b["dirs"].values(), key=lambda c: RANK[c])
    return sf, blocks


def main():
    refresh = "--refresh" in sys.argv
    update = "--update" in sys.argv
    print("Reading both records of the bike network.")
    sf, blocks = load_sfmta()
    print(f"  SFMTA: {len(sf.rows)} rows -> {len(blocks)} blocks, {sf.tag}")
    blob = fetch_osm(refresh, update)
    osm_date = blob.get("osm3s", {}).get("timestamp_osm_base", "")[:10]

    ways = []
    for w in blob["elements"]:
        tags = w.get("tags", {})
        cls = osm_class(tags)
        if not cls or "geometry" not in w:
            continue
        ways.append({
            "id": w["id"], "raw": tags.get("name"),
            "name": norm_street(tags.get("name")), "cls": cls,
            "sides": osm_sides(tags), "edited": w.get("timestamp", "")[:10],
            "pts": [project(p["lon"], p["lat"]) for p in w["geometry"]],
            "ll": [(p["lon"], p["lat"]) for p in w["geometry"]],
        })
    print(f"  OSM: {len(ways)} ways record a bikeway")

    # A second index under the suffix-dropped name, used only where dropping
    # the suffix leaves exactly one SFMTA street -- so "Broadway" reaches
    # "BROADWAY ST" while "5TH" stays ambiguous between 5th Ave and 5th St.
    sf_names = {b["name"] for b in blocks.values() if b["name"]}
    bare = collections.defaultdict(set)
    for n in sf_names:
        bare[drop_suffix(n)].add(n)
    unambiguous = {k: next(iter(v)) for k, v in bare.items() if len(v) == 1}

    # Same corridor, different suffix. Turk is ST east of Masonic and BLVD
    # west of it, and the two datasets put the change at different cross
    # streets, so 11 SFMTA blocks and 9 OSM ways on one street read as each
    # dataset missing the other. Where dropping the suffix leaves exactly one
    # SFMTA street, take it. Where it leaves several -- 5th Ave and 5th St --
    # the geometry decides, and only if exactly one candidate is in range.
    def resolve(name, probe=None):
        if not name or name in sf_names:
            return name
        cand = bare.get(drop_suffix(name))
        if not cand:
            return name
        if len(cand) == 1:
            return next(iter(cand))
        if probe is None:
            return name
        close = [c for c in cand if sf_index.near(c, probe)]
        return close[0] if len(close) == 1 else name

    sf_index = Segments()
    for b in blocks.values():
        b["proj"] = [[project(*p) for p in part] for part in b["parts"]]
        if b["name"]:
            for part in b["proj"]:
                sf_index.add(b["name"], part, b)

    osm_index = Segments()
    for w in ways:
        w["name"] = resolve(w["name"], w["pts"][len(w["pts"]) // 2])
        if w["name"]:
            osm_index.add(w["name"], w["pts"], w)

    # ---- block -> OSM ---------------------------------------------------
    results = []
    for b in blocks.values():
        pts = [p for part in b["proj"] for p in part]
        if not pts or not b["name"]:
            b["verdict"] = "unmatchable"
            b["osm"] = None
            results.append(b)
            continue
        hits = {}
        for f in SAMPLES:
            probe = pts[min(len(pts) - 1, int(f * len(pts)))]
            for _, w in osm_index.near(b["name"], probe):
                hits[w["id"]] = w
        if not hits:
            b["verdict"] = "no-osm-record"
            b["osm"] = None
            results.append(b)
            continue
        best = max(hits.values(), key=lambda w: RANK[w["cls"]])
        b["osm"] = {
            "cls": best["cls"],
            "edited": max(w["edited"] for w in hits.values()),
            "ways": sorted(hits),
            "sides": best["sides"],
        }
        b["verdict"] = ("agree" if RANK[best["cls"]] == RANK[b["cls"]]
                        else "osm-higher" if RANK[best["cls"]] > RANK[b["cls"]]
                        else "sfmta-higher")
        results.append(b)

    # ---- OSM -> block, for the other direction of absence ---------------
    orphans, unnamed = [], []
    for w in ways:
        if not w["name"]:
            unnamed.append(w)
            continue
        probe = w["pts"][len(w["pts"]) // 2]
        if not sf_index.near(w["name"], probe):
            orphans.append(w)

    tally = collections.Counter(b["verdict"] for b in results)
    print("\nVerdicts, per SFMTA block")
    for k in ("agree", "osm-higher", "sfmta-higher", "no-osm-record", "unmatchable"):
        if tally[k]:
            print(f"  {k:16s} {tally[k]:5d}")
    print(f"\n  {'osm-only ways':16s} {len(orphans):5d}  OSM records a bikeway, "
          f"SFMTA's layer has no block there")
    print(f"  {'unnamed osm':16s} {len(unnamed):5d}  park paths and connectors; "
          f"no street name to join on")

    write(results, orphans, unnamed, sf, osm_date, tally)


def write(results, orphans, unnamed, sf, osm_date, tally):
    OUT.mkdir(parents=True, exist_ok=True)
    features = []
    for b in results:
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": b["parts"]},
            "properties": {
                "cnn": b["cnn"], "street": b["street"],
                "from": b["from"], "to": b["to"],
                "sfmta": b["cls"], "dirs": b["dirs"],
                "osm": b["osm"]["cls"] if b["osm"] else None,
                "osmEdited": b["osm"]["edited"] if b["osm"] else None,
                "osmWays": b["osm"]["ways"] if b["osm"] else [],
                "verdict": b["verdict"], "installed": b["installed"],
                "updated": b["updated"],
            },
        })
    for w in orphans:
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": [w["ll"]]},
            "properties": {
                "cnn": f"osm/{w['id']}", "street": w["raw"] or w["name"] or "",
                "from": "", "to": "", "sfmta": None, "dirs": {},
                "osm": w["cls"], "osmEdited": w["edited"], "osmWays": [w["id"]],
                "verdict": "osm-only", "installed": "", "updated": "",
            },
        })
    stable.write_text(OUT / "compare.geojson", json.dumps(
        {"type": "FeatureCollection", "features": features}))

    stable.write_text(OUT / "summary.json", json.dumps({
        "generated": dt.date.today().isoformat(),
        "sfmtaTag": sf.tag, "osmDate": osm_date,
        "toleranceM": TOLERANCE_M,
        "blocks": len(results), "verdicts": dict(tally),
        "osmOnlyWays": len(orphans), "unnamedOsmWays": len(unnamed),
        "byStreet": street_tally(results),
    }, indent=2))

    fh = io.StringIO(newline="")
    wr = csv.writer(fh)
    wr.writerow(["street", "from", "to", "sfmta", "sfmta_updated",
                 "osm", "osm_edited", "verdict", "cnn", "osm_ways"])
    for b in sorted(results, key=lambda b: (b["street"], b["from"])):
        if b["verdict"] not in ("osm-higher", "sfmta-higher", "no-osm-record"):
            continue
        wr.writerow([b["street"], b["from"], b["to"], b["cls"], b["updated"],
                     b["osm"]["cls"] if b["osm"] else "",
                     b["osm"]["edited"] if b["osm"] else "",
                     b["verdict"], b["cnn"],
                     " ".join(str(i) for i in (b["osm"]["ways"] if b["osm"] else []))])

    stable.write_text(OUT / "disagreements.csv", fh.getvalue())
    print(f"\nWrote {OUT}/compare.geojson, summary.json, disagreements.csv")


def street_tally(results):
    out = {}
    for b in results:
        row = out.setdefault(b["street"], collections.Counter())
        row[b["verdict"]] += 1
    return {k: dict(v) for k, v in sorted(out.items())
            if v["osm-higher"] or v["sfmta-higher"]}


if __name__ == "__main__":
    main()
