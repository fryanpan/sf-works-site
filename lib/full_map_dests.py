"""The fingerprint of data/full-map/destinations.json that the full map's Muni minutes depend on.

tools/travel/full-map-transit.py records it in out/full-map/transit.json, and
tools/travel/full-map.py refuses minutes recorded against another fingerprint. It
covers each type's name and point coordinates only, the inputs R5 reads, so a
refresh that changes nothing but a source's "queried" date (as the zoning and
parks fetches did on 2026-11-11) leaves the minutes valid, while a moved, added
or dropped point still makes the rerun on the sim VM necessary.
"""
import hashlib
import json


def points_sha(dests):
    """First 16 hex of a SHA-256 over [[type, [[lon, lat], ...]], ...], types sorted, points in file order."""
    body = [[t, [[p[0], p[1]] for p in dests["types"][t]["points"]]] for t in sorted(dests["types"])]
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()[:16]
