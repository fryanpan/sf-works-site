#!/usr/bin/env python3
"""San Francisco's walk network from OpenStreetMap, for measuring how far residents walk to a bikeway.

    tools/travel/osm-walk-network.py            # fetch if there is no copy
    tools/travel/osm-walk-network.py --update   # ask Overpass what changed; re-read if anything did
    tools/travel/osm-walk-network.py --refresh  # re-read regardless

Bryan, 2026-09-29: "to be properly
defensible, we should do actual network connectivity analysis walkable for
'close enough' instead of as the bird flies".

WHICH WAYS. OSMnx 2.1.1's "walk" network filter, copied verbatim (osmnx
_overpass._get_network_filter("walk")): every highway except motorways and
their ramps, abandoned, proposed or under construction ways, platforms and
private ways; street ways whose sidewalks are mapped as separate ways are left
out in favour of those sidewalks. Stairways, footways, paths and pedestrian
streets are in. One addition: highway=cycleway, which OSMnx's walk filter
drops. A cycle path is itself a bikeway, and the distance being measured is to
reach it, so a park path that is mapped as a cycleway has to be in the network.

INCREMENTAL. --update asks Overpass how many matching ways were edited since
the copy's planet timestamp and re-reads the whole city only when that count is
not zero, or when the copy is FULL_EVERY_DAYS old (a way whose tags stopped
matching is invisible to an edited-since count). The re-read replaces the copy
only when it holds at least 90% of the held ways and Overpass sent no remark
(Overpass answers a query that ran out of time with HTTP 200 and part of the
data); otherwise the held copy stays and the check is recorded as failed.

Writes data/osm-cache/sf-walk.json (gitignored, refetchable, about 40 MB):
Overpass's answer, ways with their node ids and tags, then every node's
coordinates. lib/walknet.py builds the graph from it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import fetch as fetch_lib, pipeline_state  # noqa: E402

_osm = paths.load("osm-sfmta-compare.py", "osm_compare")
overpass, AREA = _osm.overpass, _osm.AREA

CACHE = os.path.join(ROOT, "data", "osm-cache", "sf-walk.json")
MARKER = "overpass:sf-walk"
STEP = "osm-walk-network"
FULL_EVERY_DAYS = 30
KEEP_SHARE = 0.90

# OSMnx 2.1.1, _overpass._get_network_filter("walk"), verbatim, less
# "cycleway" in the highway exclusion (see the docstring).
WALK = ('["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|construction|motor|no|planned|platform|proposed|raceway|razed|rest_area|services"]'
        '["foot"!~"no"]["service"!~"private"]["sidewalk"!~"separate"]["sidewalk:both"!~"separate"]'
        '["sidewalk:left"!~"separate"]["sidewalk:right"!~"separate"]')


# Overpass's area named "San Francisco" at admin_level 6 matches a dozen
# municipalities named San Francisco in the Philippines, Colombia, Panama and
# elsewhere; the box keeps the city and county's mainland, Treasure Island
# and Yerba Buena Island (the Farallones, with no residents, fall outside).
BBOX = "(37.63,-122.60,37.84,-122.33)"


def query(newer=""):
    return "way(area.sf)%s%s%s;" % (BBOX, WALK, newer)


def changed_since(base):
    """Ways edited since `base`, plus ways whose nodes moved since (moving a node leaves its way's timestamp alone)."""
    q = AREA.format(t=240) + "way(area.sf)%s%s->.w;\n(way.w(newer:\"%s\"); node(w.w)(newer:\"%s\"););\nout count;" % (BBOX, WALK, base, base)
    d = overpass(q, 300)
    tags = (d.get("elements") or [{}])[0].get("tags", {})
    return int(tags.get("total", 0))


def ways_of(blob):
    return sum(1 for e in blob.get("elements", ()) if e.get("type") == "way")


def fetch(refresh=False, update=False):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    old = json.load(open(CACHE)) if os.path.exists(CACHE) else None
    if old is not None and update and not refresh:
        base = old.get("osm3s", {}).get("timestamp_osm_base", "")
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(base.replace("Z", "+00:00"))).days
        try:
            n = changed_since(base)
        except Exception as exc:  # noqa: BLE001
            # A 5xx or timeout after overpass()'s retries is Overpass's load: the copy stays, the step exits 0 and
            # the builds run on it (lib/fetch.upstream_failed, #435). Any other error still exits 2.
            print("  OSM walk: change check failed (%s); keeping the copy" % exc)
            fetch_lib.upstream_failed(MARKER, exc, step=STEP)
        refresh = n > 0 or age >= FULL_EVERY_DAYS
        # "changed" is recorded only once the re-read lands: recorded before it, a failed re-read would carry this
        # run's time over as last_good and the freshness check would never see the copy age.
        if not refresh:
            pipeline_state.record(MARKER, "unchanged", version=base,
                                  detail="%d walkable ways edited since; copy %d days old" % (n, age))
        print("  OSM walk: %d walkable ways edited since %s; copy %d days old%s"
              % (n, base[:10], age, " -> re-reading" if refresh else ""))
    if old is not None and not refresh:
        print("  OSM walk: %d ways held, planet as of %s" % (ways_of(old), old.get("osm3s", {}).get("timestamp_osm_base", "?")[:10]))
        return 0
    try:
        blob = overpass(AREA.format(t=900) + query() + "\nout body qt;\n>;\nout skel qt;", 900)
    except Exception as exc:  # noqa: BLE001
        if old is None:
            raise
        print("  OSM walk: re-read failed (%s); keeping the copy" % exc)
        fetch_lib.upstream_failed(MARKER, exc, step=STEP)
    held = ways_of(old) if old else 0
    got = ways_of(blob)
    if blob.get("remark") or got < max(int(held * KEEP_SHARE), 1):
        why = "Overpass answered %d ways against %d held%s" % (got, held, (" with the remark: " + blob["remark"][:200]) if blob.get("remark") else "")
        if old is None:
            raise SystemExit("FAIL: " + why)
        pipeline_state.record(MARKER, "failed", detail=why + "; copy kept")
        print("  OSM walk: %s; keeping the copy" % why)
        return 2
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(blob, fh, separators=(",", ":"))
    os.replace(tmp, CACHE)
    pipeline_state.record(MARKER, "changed", version=blob.get("osm3s", {}).get("timestamp_osm_base"),
                          detail="%d ways re-read" % got)
    print("  OSM walk: %d ways fetched, planet as of %s" % (got, blob.get("osm3s", {}).get("timestamp_osm_base", "?")[:10]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    sys.exit(fetch(refresh=a.refresh, update=a.update))


if __name__ == "__main__":
    main()
