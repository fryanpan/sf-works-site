#!/usr/bin/env python3
"""The one mile basis every mile figure on the transportation pages is counted in, and the label each data file carries for it.

The Biking and Rolling Plan counts its network per direction of travel: its
"has grown from 302 miles in 2010 to 472 miles today" (printed p. 20) is the
sum of the length of every row in SFMTA's bikeway layer, which holds one row
per block per direction on most blocks, and on some blocks a path beside the
lanes as further rows (sources/sfmta-biking-rolling-plan.md). So every mile
figure the site shows is counted that one way:

  1. A bikeway layer row counts its own drawn length (row_metres). The layer's
     rows, summed, are the plan's 472 miles.
  2. A block's miles are the sum of its layer rows (block_metres). A block
     the layer does not carry counts its centerline length once on a one-way
     street and twice on a two-way street (lib/plan_directions.py).
  3. A plan block's miles are its block miles times the share of the block
     the plan's map draws (plan_metres, tools/bike-network/north-star-map-trace.py
     `share`). The share is 1 unless the plan's line stops partway along the
     block, at the end of a corridor; there it is the part from the block's
     end to where the line stops. A block the plan's line runs through counts
     whole however closely the trace followed it.

Every producer calls these functions: tools/bike-network/bike-network-history.py for
rules 1 and 2, and lib/plan_directions.py's Directions.plan_metres for
rule 3, which tools/bike-network/bike-progress.py (north-star/status.json),
tools/bike-network/repave-lever.py and tools/projects/coordination-projects.py read. Each
script that writes a file the pages take miles from puts `"mileBasis": BASIS`
at its top level. site/scripts/check-mile-basis.mjs stops the build when the
files disagree block for block, and pipeline/transportation-audit.py (F1)
measures every file against the bikeway layer itself.

A quarter mile of reach is a straight-line distance, not a length of street,
and carries no basis.
"""

import math

BASIS = "per direction of travel"
MILE = 1609.344
_LAT0 = math.radians(37.76)
_R = 6371008.8


def line_metres(pts):
    """Length of a [[lon, lat], ...] line in metres, flat around San Francisco."""
    m = 0.0
    k = math.cos(_LAT0) * _R
    for (a, b), (c, d) in zip(pts, pts[1:]):
        m += math.hypot(math.radians(c - a) * k, math.radians(d - b) * _R)
    return m


def row_metres(r):
    """One re-keyed layer row's own drawn length (lib/bikeway_snap.py rows).

    A row split over several blocks carries `_mi`, its piece of the row's
    length; a row kept whole is measured from its line; a row with no line
    falls back to SFMTA's LENGTH column (miles)."""
    if r.get("_mi") is not None:
        return r["_mi"] * MILE
    if r.get("_pts"):
        return line_metres(r["_pts"])
    try:
        return float(r.get("LENGTH") or 0.0) * MILE
    except (TypeError, ValueError):
        return 0.0


def block_metres(centerline_m, directions):
    """A block the layer does not carry: its centerline length times its directions (1 one-way, 2 two-way)."""
    return (centerline_m or 0.0) * directions
