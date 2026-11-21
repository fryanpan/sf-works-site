#!/usr/bin/env python3
"""San Francisco's address points (DataSF 3mea-di5p, the Enterprise Addressing System), boiled down to one point per side of each hundred block, for the School Trips page's address box.

    pipeline/sources/sf-address-points.py            # rebuild the site file from disk; fetch once if absent
    pipeline/sources/sf-address-points.py --update   # ask DataSF whether the addresses changed; re-read only if they did
    pipeline/sources/sf-address-points.py --refresh  # re-read the addresses

THE DATA. DataSF "Addresses with Units - Enterprise Addressing System"
(3mea-di5p): about 224,000 base addresses, each with a street number, street
name and type, and a point. The page needs only where a home is to within a
block, because every trip is routed from the nearest street, so the points are
averaged per street, hundred block and side (odd or even). That is about
25,000 points, small enough to load when a reader starts typing.

PRIVACY. The page looks the address up in this file, in the reader's browser.
The address never leaves the page.

CHECKS, before anything is written: at least FLOOR_STREETS streets and
FLOOR_POINTS points; every point inside San Francisco's bounding box; and each
landmark address in LANDMARKS found within 150 m of where it is. A failed check
raises, and the previous file stays.

INCREMENTAL. --update reads the dataset's rowsUpdatedAt and re-reads the
addresses only when it differs from the one recorded in the file. A failed
re-read keeps the last good copy and records the failure in
data/pipeline-state/sources.json.

Writes site/data/sf-addresses.json.
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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.stable import write_json  # noqa: E402

ROOT = paths.ROOT
FXF = "3mea-di5p"
MARKER = "socrata:" + FXF
OUT = os.path.join(ROOT, "site", "data", "sf-addresses.json")
BBOX = (-123.2, 37.6, -122.3, 37.9)
FLOOR_STREETS, FLOOR_POINTS = 1500, 15000
# A known address, and where it is (lon, lat), read off the city's own map.
LANDMARKS = {
    "1 DR CARLTON B GOODLETT PL": (-122.4193, 37.7793),   # City Hall
    "400 MONTEREY BLVD": (-122.4467, 37.7313),
    "375 07TH ST": (-122.4058, 37.7751),                  # Bessie Carmichael
}


def fetch():
    r = sfdata.fetch(FXF, select="address_number,street_name,street_type,longitude,latitude",
                     refresh=True, floor=150000)
    acc = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for row in r.rows:
        try:
            num = int(float(row["address_number"]))
            lon, lat = float(row["longitude"]), float(row["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        name = " ".join(x for x in (row.get("street_name"), row.get("street_type")) if x).strip().upper()
        if not name or num <= 0:
            continue
        k = (name, (num // 100) * 2 + num % 2)
        a = acc[k]
        a[0] += lon
        a[1] += lat
        a[2] += 1
    streets = collections.defaultdict(list)
    for (name, k), (x, y, n) in acc.items():
        streets[name].append([k, round(x / n * 1e5), round(y / n * 1e5)])
    return [{"s": s, "p": sorted(v)} for s, v in sorted(streets.items())], len(r.rows)


def lookup(streets, text):
    """(lon, lat) of an address line like '400 MONTEREY BLVD', the page's rule in Python, for the checks."""
    num, name = text.split(" ", 1)
    num = int(num)
    by = {s["s"]: s["p"] for s in streets}
    pts = by.get(name)
    if not pts:
        return None
    want = (num // 100) * 2 + num % 2
    best = min(pts, key=lambda p: (abs(p[0] // 2 - want // 2), p[0] % 2 != want % 2))
    return best[1] / 1e5, best[2] / 1e5


def check(streets):
    bad = []
    n = sum(len(s["p"]) for s in streets)
    if len(streets) < FLOOR_STREETS or n < FLOOR_POINTS:
        bad.append("%d streets and %d points, below the floors %d and %d" % (len(streets), n, FLOOR_STREETS, FLOOR_POINTS))
    out = [s["s"] for s in streets for p in s["p"] if not (BBOX[0] <= p[1] / 1e5 <= BBOX[2] and BBOX[1] <= p[2] / 1e5 <= BBOX[3])]
    if out:
        bad.append("%d points outside San Francisco's bounding box, e.g. %s" % (len(out), out[0]))
    for addr, (x, y) in sorted(LANDMARKS.items()):
        got = lookup(streets, addr)
        if got is None:
            bad.append("%s not found" % addr)
            continue
        d = math.hypot((got[0] - x) * 88000, (got[1] - y) * 111000)
        if d > 150:
            bad.append("%s found %.0f m from where it is" % (addr, d))
    return bad


def read_existing():
    if not os.path.exists(OUT):
        return None
    with open(OUT, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    have = read_existing()
    if have is not None and not (a.update or a.refresh):
        bad = check(have["streets"])
        if bad:
            sys.exit("sf-address-points: the file on disk fails its checks: " + "; ".join(bad))
        print("  %s: %d streets on disk, read %s" % (FXF, len(have["streets"]), have["read"]))
        return
    try:
        meta = sfdata.metadata(FXF)
        stamp = meta["rows_updated_ts"]
        if not a.refresh and have is not None and have.get("rowsUpdatedTs") == stamp:
            print("  %s unchanged (rowsUpdatedAt %s)" % (FXF, stamp))
            if a.update:
                pipeline_state.record(MARKER, "unchanged", version=str(stamp), detail="%d streets" % len(have["streets"]))
            return
        streets, rows = fetch()
        bad = check(streets)
        if bad:
            raise ValueError("; ".join(bad))
    except Exception as exc:  # noqa: BLE001
        if not (a.update and have):
            raise
        pipeline_state.record(MARKER, "failed", detail="re-read failed, copy of %s kept: %s" % (have["read"], exc))
        print("  %s re-read failed (%s); keeping the copy read %s" % (FXF, exc, have["read"]))
        return
    doc = {
        "source": "Addresses with Units - Enterprise Addressing System, DataSF %s" % FXF,
        "dataset": "https://data.sfgov.org/d/" + FXF,
        "rowsUpdatedAt": meta["rows_updated_at"].isoformat() if meta["rows_updated_at"] else None,
        "rowsUpdatedTs": stamp,
        "read": dt.date.today().isoformat(),
        "addresses": rows,
        "note": "One point per street, hundred block and side: p is [hundred x 2 + (number odd), lon x 1e5, lat x 1e5], "
                "the mean of that side's address points.",
        "streets": streets,
    }
    wrote = write_json(OUT, doc, separators=(",", ":"))
    if a.update:
        pipeline_state.record(MARKER, "changed", version=str(stamp), detail="%d streets" % len(streets))
    print("  %s: %d addresses to %d streets, %d points; %s" % (
        FXF, rows, len(streets), sum(len(s["p"]) for s in streets), "written" if wrote else "unchanged"))


if __name__ == "__main__":
    main()
