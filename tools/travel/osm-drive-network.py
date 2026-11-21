#!/usr/bin/env python3
"""San Francisco's drivable streets from OpenStreetMap, so the school simulation routes a car on the streets a car uses.

    tools/travel/osm-drive-network.py            # fetch if there is no copy
    tools/travel/osm-drive-network.py --update   # ask Overpass what changed; re-read if anything did
    tools/travel/osm-drive-network.py --refresh  # re-read regardless

WHY. The walk network (tools/travel/osm-walk-network.py) leaves out every street
whose sidewalks are mapped as their own ways, in favour of those sidewalks. That
is right for a walker and wrong for a car: Van Ness Avenue survived in it only
as its busway and footways, and a car from City Hall to Carmichael was routed
25.9 km around it (Fable pipeline review, 2026-10-08). tools/school-trips/school-sim.py
adds these ways to its graph as edges only a car may use.

WHICH WAYS. Modelled on OSMnx 2.1.1's "drive_service" network filter: every
highway a motor vehicle may use, service roads included, less abandoned,
proposed or under construction ways, paths, footways, cycleways, steps,
platforms, busways and bus guideways, ways closed to motor vehicles or cars,
private or no access, and parking aisles and emergency access. Motorways are
in: a car crossing the city takes them.

INCREMENTAL. As tools/travel/osm-walk-network.py: --update asks Overpass how many
matching ways (or their nodes) were edited since the copy's planet timestamp and
re-reads the city only when that count is not zero, or when the copy is
FULL_EVERY_DAYS old (a way whose tags stopped matching is invisible to an
edited-since count). The re-read replaces the copy only when it holds at least
90% of the held ways and Overpass sent no remark; otherwise the held copy stays
and the check is recorded as failed. Quality checks: drive_checks in
scripts/transportation-quality.py.

Writes data/osm-cache/sf-drive.json (gitignored, refetchable): Overpass's
answer, ways with their node ids and tags, then every node's coordinates.
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

CACHE = os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")
MARKER = "overpass:sf-drive"
STEP = "osm-drive-network"
FULL_EVERY_DAYS = 30
KEEP_SHARE = 0.90
BBOX = "(37.63,-122.60,37.84,-122.33)"   # tools/travel/osm-walk-network.py's box

DRIVE = ('["highway"]["area"!~"yes"]["access"!~"private|no"]'
         '["highway"!~"abandoned|bridleway|bus_guideway|busway|construction|corridor|cycleway|elevator|escalator|footway|'
         'no|path|pedestrian|planned|platform|proposed|raceway|razed|rest_area|services|steps|track"]'
         '["motor_vehicle"!~"no"]["motorcar"!~"no"]["service"!~"emergency_access|parking|parking_aisle|private"]')


def query():
    return "way(area.sf)%s%s;" % (BBOX, DRIVE)


def changed_since(base):
    """Ways edited since `base`, plus ways whose nodes moved since."""
    q = AREA.format(t=240) + "way(area.sf)%s%s->.w;\n(way.w(newer:\"%s\"); node(w.w)(newer:\"%s\"););\nout count;" % (BBOX, DRIVE, base, base)
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
            print("  OSM drive: change check failed (%s); keeping the copy" % exc)
            fetch_lib.upstream_failed(MARKER, exc, step=STEP)
        refresh = n > 0 or age >= FULL_EVERY_DAYS
        # "changed" is recorded only once the re-read lands: recorded before it, a failed re-read would carry this
        # run's time over as last_good and the freshness check would never see the copy age.
        if not refresh:
            pipeline_state.record(MARKER, "unchanged", version=base,
                                  detail="%d drivable ways edited since; copy %d days old" % (n, age))
        print("  OSM drive: %d drivable ways edited since %s; copy %d days old%s"
              % (n, base[:10], age, " -> re-reading" if refresh else ""))
    if old is not None and not refresh:
        print("  OSM drive: %d ways held, planet as of %s" % (ways_of(old), old.get("osm3s", {}).get("timestamp_osm_base", "?")[:10]))
        return 0
    try:
        blob = overpass(AREA.format(t=900) + query() + "\nout body qt;\n>;\nout skel qt;", 900)
    except Exception as exc:  # noqa: BLE001
        if old is None:
            raise
        print("  OSM drive: re-read failed (%s); keeping the copy" % exc)
        fetch_lib.upstream_failed(MARKER, exc, step=STEP)
    held = ways_of(old) if old else 0
    got = ways_of(blob)
    if blob.get("remark") or got < max(int(held * KEEP_SHARE), 1):
        why = "Overpass answered %d ways against %d held%s" % (got, held, (" with the remark: " + blob["remark"][:200]) if blob.get("remark") else "")
        if old is None:
            raise SystemExit("FAIL: " + why)
        pipeline_state.record(MARKER, "failed", detail=why + "; copy kept")
        print("  OSM drive: %s; keeping the copy" % why)
        return 2
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(blob, fh, separators=(",", ":"))
    os.replace(tmp, CACHE)
    pipeline_state.record(MARKER, "changed", version=blob.get("osm3s", {}).get("timestamp_osm_base"),
                          detail="%d ways re-read" % got)
    print("  OSM drive: %d ways fetched, planet as of %s" % (got, blob.get("osm3s", {}).get("timestamp_osm_base", "?")[:10]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    sys.exit(fetch(refresh=a.refresh, update=a.update))


if __name__ == "__main__":
    main()
