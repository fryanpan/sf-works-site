#!/usr/bin/env python3
"""Per-direction metres of each North Star block, counted as the plan counts its network (lib/mile_basis.py).

The Biking and Rolling Plan counts its network per direction row: its "472
miles today" (printed p. 20) is the sum of every row's length in SFMTA's
bikeway layer. The traced North Star network (site/data/north-star/traced.geojson)
is one row per block with a centerline length and the `share` of the block
the plan draws (1 except where the plan's line stops partway along the
block, at a corridor's end), so a plan block's miles are:

  - where the block is in the bikeway layer, the sum of its layer rows' own
    drawn lengths (mile_basis.row_metres), the same per-block figure
    tools/bike-network/bike-network-history.py sums into the overview's network miles;
  - otherwise its centerline length times its directions of travel, from the
    street centerline's one-way flag (DataSF 3psu-pn9h, `oneway`: B both
    ways, F or T one way): 2 for B, 1 for F or T, and 2 with no flag;
  - either one times the trace's `share` of the block.

    from plan_directions import Directions
    D = Directions()
    D.plan_metres("4324002", length_m, share)   # metres, per direction of travel
    n, basis = D.count("4324002")                # (2, "layer rows"), direction rows
    D.summary()                                  # how many blocks took each basis

Used by tools/bike-network/bike-progress.py, tools/bike-network/repave-lever.py and
tools/projects/coordination-projects.py so every page's plan miles are one figure
per block.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import math
import os
import sys

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from extract import Extract  # noqa: E402
import sfdata  # noqa: E402
from bikeway_snap import rekeyed_layer  # noqa: E402
from mile_basis import block_metres, row_metres  # noqa: E402

CENTERLINES = "3psu-pn9h"
# The same query tools/bike-network/north-star-index.py makes, so the cached read is shared.
CENTERLINE_SELECT = "cnn,street,st_type,streetname,f_st,t_st,f_node_cnn,t_node_cnn,line,oneway"
CENTERLINE_FLOOR = 15000
DEFAULT_DIRECTIONS = 2


# Ends within this of a block's ends make a CNN-less path that block's row;
# tools/bike-network/bike-network-history.py's PathRegistry.PATH_TOLERANCE_M.
PATH_TOLERANCE_M = 25
_K = math.cos(math.radians(37.76)) * 6371008.8


def _xy(p):
    return (math.radians(p[0]) * _K, math.radians(p[1]) * 6371008.8)


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cnn_key(v):
    return str(v or "").split(".")[0].lstrip("0")


class Directions(object):
    def __init__(self, refetch=False):
        net = Extract("sfmta-bikeway").read("network")
        if net is None:
            raise SystemExit("data/extract/sfmta-bikeway/network.json is missing; run tools/bike-network/bike-progress.py --refetch first")
        cl = sfdata.fetch(CENTERLINES, select=CENTERLINE_SELECT, where="active='true'", floor=CENTERLINE_FLOOR, refresh=refetch)
        self.oneway = {cnn_key(r["cnn"]): r.get("oneway") for r in cl.rows if r.get("cnn")}
        self.layer_rows = collections.Counter()
        self.layer_m = collections.defaultdict(float)
        # Rows keyed by the centerline block each lies on (lib/bikeway_snap.py).
        rows = [r for r in rekeyed_layer(net.records) if r.get("FACILITY_T")]
        for r in rows:
            c = cnn_key(r.get("CNN"))
            if c:
                self.layer_rows[c] += 1
                self.layer_m[c] += row_metres(r)
        # A path row SFMTA left without a CNN whose two ends lie within 25 m of
        # the ends of a block's own centerline is that block's row, as
        # tools/bike-network/bike-network-history.py (alias_paths) and the audit's F1
        # count it.
        ends = {}
        for r in cl.rows:
            c = cnn_key(r.get("cnn"))
            pts = (r.get("line") or {}).get("coordinates") or []
            if c in self.layer_rows and len(pts) >= 2:
                ends[c] = (_xy(pts[0]), _xy(pts[-1]))
        for r in rows:
            if cnn_key(r.get("CNN")) or not r.get("_pts"):
                continue
            a, b = _xy(r["_pts"][0]), _xy(r["_pts"][-1])
            for c, (ea, eb) in sorted(ends.items()):
                if (max(_d(a, ea), _d(b, eb)) <= PATH_TOLERANCE_M or max(_d(a, eb), _d(b, ea)) <= PATH_TOLERANCE_M):
                    self.layer_rows[c] += 1
                    self.layer_m[c] += row_metres(r)
                    break
        self.layer_queried = net.fetched_on.isoformat()
        self.centerline_queried = cl.fetched_on.isoformat()
        self.centerline_tag = cl.tag
        self.used = collections.Counter()

    def metres(self, cnn, centerline_m):
        """A whole block's metres per direction of travel: its layer rows'
        own lengths where the layer carries it, else its centerline length
        times its directions of travel."""
        c = cnn_key(cnn)
        if c in self.layer_rows:
            self.count(c)
            return self.layer_m[c]
        return block_metres(centerline_m, self.count(c)[0])

    def plan_metres(self, cnn, centerline_m, share=1.0):
        """A plan block's metres: the block's metres times the share of it the plan draws."""
        return self.metres(cnn, centerline_m) * (1.0 if share is None else share)

    def count(self, cnn):
        """(direction rows, basis) for one block: the layer's rows, at most two, or the centerline's directions."""
        c = cnn_key(cnn)
        if c in self.layer_rows:
            # A street has at most two directions of travel. The layer holds 3
            # to 6 rows on some 2W blocks (a path beside two lanes, split
            # segments), which would count The Embarcadero five times (Fable
            # review, 2026-09-28).
            n, basis = min(self.layer_rows[c], 2), "layer rows"
        elif self.oneway.get(c) in ("F", "T"):
            n, basis = 1, "centerline one-way"
        elif self.oneway.get(c) == "B":
            n, basis = 2, "centerline two-way"
        else:
            n, basis = DEFAULT_DIRECTIONS, "no flag, two assumed"
        self.used[basis] += 1
        return n, basis

    def summary(self):
        """How the blocks counted so far were resolved, for the JSON a page reads."""
        return {
            "rule": ("A plan block's miles are the block's miles per direction of travel, times the part of it the plan draws where the plan's line stops partway along it: "
                     "the sum of its bikeway layer rows' own lengths where the layer carries it, "
                     "else its centerline length once where the street centerline's oneway flag is F or T, else twice."),
            "blocks_by_basis": dict(self.used),
            "layer": {"queried": self.layer_queried},
            "centerlines": {"id": CENTERLINES, "tag": self.centerline_tag, "queried": self.centerline_queried},
        }
