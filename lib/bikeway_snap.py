#!/usr/bin/env python3
"""Re-key SFMTA bikeway layer rows to the centerline block they lie on, splitting a row that spans several blocks.

    from bikeway_snap import rekeyed_layer, shared_snapper
    rows = rekeyed_layer(network_records)                # re-keyed, split; once per process
    rows = shared_snapper().snapshot_rows(capture_records)  # same keys, by name

    python3 lib/bikeway_snap.py        # print what it changes, and why

Why. Every join on the transportation pages runs on CNN, the city's block id.
SFMTA's bikeway layer carries a CNN on each row, and on 2026-09-28 the audit
(research/transportation-audit-2026-09/data-quality.md, E2) found 51 of 3,017
bikeway blocks whose drawn line sits more than 50 ft from the block its CNN
names, 21 of them more than 330 ft, up to 2.3 miles. The worst are Class I
paths on John F Kennedy Drive keyed with Cabrillo Street CNNs: the join then
gives Cabrillo a separated path it does not have. Another 21 blocks carry
CNNs the centerline has retired, so they miss the plan blocks that replaced
them.

What. A row is kept as SFMTA keyed it when its CNN is an active centerline
block and every vertex lies within TOLERANCE_M (50 ft) of that block. Any
other row is walked in SAMPLE_M steps. Each sample goes to the nearest active
block of the SAME street within SEARCH_M, and the run of samples on one block
becomes one piece, keyed by that block and drawn on its centerline. A row
whose samples find no block of its street (the San Francisco Bay Trail) is an
off-street path: its CNN is dropped and it is keyed by its endpoints, as the
layer's 79 other unkeyed paths already are. The street-name test is the
safeguard: a path beside a street is not given that street's CNN. A row with
no street name therefore never takes one from the CNN SFMTA typed unless it
lies on that block; otherwise it is a path (the straight two-point line
across Marina Green, keyed to a Marina Boulevard block 580 m away).

Three cases the name test alone gets wrong:
  - A divided street. Where SFMTA typed a block of the street's other
    carriageway, its choice stands (Octavia Boulevard). Where
    it drew two on-street direction rows of one class as one line with one
    CNN, the second goes to the other carriageway wherever one runs beside it
    (Terry A Francois Boulevard, Alemany Boulevard). See Snapper.live_rows.
  - A renamed street. A row on a retired block goes to an active block of
    another name that took the retired block's place along its whole line
    (Avenue of the Palms, now Treasure Island Road). See Centerline.renamed.
  - A retired block nothing replaced (Hunters Point Expressway; Terry A
    Francois Boulevard between Third Street and Mission Rock Street). The row keeps its line, loses its CNN and is marked
    "retired", not "path", so reports can count it as an on-street bikeway.

The archived captures (DataSF ygmz-vaxd via the Internet Archive) keep no
geometry for blocks still in the live layer, so a capture row is re-keyed by
matching its old CNN, street and cross streets to a live row, and failing
that, a retired CNN goes to the active blocks that replaced it.

The centerline is DataSF 3psu-pn9h, all rows with their `active` flag, from
the sfdata cache. bike-network-history, bike-progress, plan_directions and
repave-lever all read the layer through rekeyed_layer(), so a run loads and
grids the centerline once and every script sees the same rows.

The checks: pipeline/transportation-geometry-check.py (E2, and a cross-street
test that does not use the snapper's own geometry).
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfdata  # noqa: E402
from streetindex import canon  # noqa: E402
from streetnames import SUFFIX  # noqa: E402

CENTERLINES = "3psu-pn9h"
TOLERANCE_M = 15.24   # 50 ft, the audit's pass line (criteria E2)
SEARCH_M = 60.0       # how far a sample may sit from a block of its own street
SAMPLE_M = 5.0
MIN_PIECE_M = 8.0     # a shorter run is the corner of an intersection
END_M = 30.0          # an unmatched end shorter than this is the intersection box
RENAMED_M = 2 * TOLERANCE_M   # how far a renamed street's block may sit from the retired one it replaced
RENAMED_MIN_M = 30.0  # shorter than this, a block along a retired line is a cross street's stub
END_TOL_M = 1.0       # a nearest point this close to a block's end is past the block, not beside it
# Classes drawn on the roadway, one row per direction of travel. A pair of
# these rows with one line between them is split across a divided street's
# two carriageways; a Class I path lies beside one carriageway and is not.
ON_STREET = {"CLASS II", "CLASS III", "CLASS IV"}
CELL = 100.0
MILE_M = 1609.344

K_LON = 111_320.0 * math.cos(math.radians(37.76))
K_LAT = 111_320.0

# Types the layer and the centerline put after a name. Stripped before names
# are compared, because the two disagree on them ("BROADWAY ST" against
# "BROADWAY", "GIRARD RD" against "GIRARD").
_TYPES = set(SUFFIX) | set(SUFFIX.values()) | {"path", "trl", "trail", "loop", "walk", "ramp", "hy", "tunl", "stwy"}


def proj(p):
    return (p[0] * K_LON, p[1] * K_LAT)


def unproj(q):
    return [round(q[0] / K_LON, 6), round(q[1] / K_LAT, 6)]


def _closest(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return (a[0] + t * dx, a[1] + t * dy)


def seg_dist(p, a, b):
    c = _closest(p, a, b)
    return math.hypot(p[0] - c[0], p[1] - c[1])


def length_m(pts):
    q = [proj(p) for p in pts]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(q, q[1:]))


def name_key(name):
    """A street's base name for comparison: no type, no middle initial."""
    # "GREAT HWY HWY" and "GREAT HWY", "SAN JOSE AVE ON RAMP" and "SAN JOSE
    # AV ON RAMP": types are spelled one way, then every trailing one goes.
    words = [SUFFIX.get(w, w) for w in re.sub(r"\s+", " ", (name or "").strip().lower()).split(" ")]
    while len(words) > 1 and words[-1] in _TYPES:
        words = words[:-1]
    if len(words) > 2:
        words = [words[0]] + [w for w in words[1:-1] if len(w) > 1] + [words[-1]]
    return canon(" ".join(words))


def cnn_key(v):
    """The CNN as the repo writes it: an integer string, None for 0 or blank."""
    if v in (None, ""):
        return None
    try:
        k = str(int(float(v)))
    except ValueError:
        return None
    return None if k == "0" else k


class Centerline:
    """Every centerline block, projected to metres, with a grid over the active ones."""

    def __init__(self):
        # Every row, active and retired, with every column: one cached read.
        geo = sfdata.fetch(CENTERLINES)
        self.tag = geo.tag
        self.queried = geo.fetched_on.isoformat()
        self.active = {cnn_key(r["cnn"]) for r in geo.rows if str(r.get("active")).lower() == "true"}
        self.line, self.name, self.lonlat, self.cross = {}, {}, {}, {}
        # An intersection's CNN is a node: the end of the blocks that meet
        # there. The coordination feed keys intersection work by it.
        self.node = {}
        for r in geo.rows:
            c = cnn_key(r.get("cnn"))
            coords = (r.get("line") or {}).get("coordinates") or []
            if not c or len(coords) < 2:
                continue
            self.lonlat[c] = coords
            self.line[c] = [proj(p) for p in coords]
            self.name[c] = name_key(r.get("street"))
            # The block's two cross streets, for checks that do not use geometry.
            self.cross[c] = {k for k in (name_key(r.get("f_st")), name_key(r.get("t_st"))) if k}
            live = c in self.active
            for k, end in (("f_node_cnn", coords[0]), ("t_node_cnn", coords[-1])):
                n = cnn_key(r.get(k))
                if n and (n not in self.node or live):
                    self.node[n] = end
        self.cells = collections.defaultdict(list)
        # Sorted, so each cell lists its blocks in one order whatever the hash
        # seed: nearest() and twin() break a tie in distance by that order, and
        # iterating the set placed three layer rows differently per seed
        # (Fable review, 2026-09-29: Girard Rd 15185101/15185201).
        for c in sorted(self.active):
            pts = self.line.get(c)
            if not pts:
                continue
            for a, b in zip(pts, pts[1:]):
                for gx in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for gy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.cells[(gx, gy)].append((a, b, c))

    def dist(self, q, cnn):
        """Metres from projected point q to block cnn's line."""
        pts = self.line[cnn]
        return min(seg_dist(q, a, b) for a, b in zip(pts, pts[1:]))

    def max_dist(self, pts, cnn):
        """The audit's measure: the farthest vertex of a lon/lat line from block cnn."""
        if cnn not in self.line:
            return None
        return max(self.dist(proj(p), cnn) for p in pts)

    def on(self, q, cnn):
        """The point on block cnn's line nearest projected point q."""
        pts = self.line[cnn]
        best = min((_closest(q, a, b) for a, b in zip(pts, pts[1:])),
                   key=lambda c: math.hypot(q[0] - c[0], q[1] - c[1]))
        return best

    def nearest(self, q, key, reach, also=(), skip=None):
        """The nearest active block named `key` (any name when key is None), or
        listed in `also`, within `reach` metres of q; never `skip`."""
        gx, gy = int(q[0] // CELL), int(q[1] // CELL)
        n = int(math.ceil(reach / CELL))
        best, bd = None, reach
        for dx in range(-n, n + 1):
            for dy in range(-n, n + 1):
                for a, b, c in self.cells.get((gx + dx, gy + dy), ()):
                    if c == skip or (key is not None and self.name.get(c) != key and c not in also):
                        continue
                    d = seg_dist(q, a, b)
                    if d <= bd:
                        best, bd = c, d
        return best

    def interior(self, q, cnn):
        """Whether q's nearest point on block cnn lies inside the block, not
        on one of its ends: q is beside the block, not past it."""
        pts = self.line[cnn]
        c = self.on(q, cnn)
        return min(math.hypot(c[0] - pts[0][0], c[1] - pts[0][1]),
                   math.hypot(c[0] - pts[-1][0], c[1] - pts[-1][1])) > END_TOL_M

    def twin(self, q, cnn):
        """The other carriageway of a divided street at q: the nearest active
        block of cnn's street, not cnn, within SEARCH_M, that q lies beside
        (interior to both), so the two run side by side rather than end to end."""
        if not self.interior(q, cnn):
            return None
        key = self.name.get(cnn)
        gx, gy = int(q[0] // CELL), int(q[1] // CELL)
        n = int(math.ceil(SEARCH_M / CELL))
        best, bd = None, SEARCH_M
        for dx in range(-n, n + 1):
            for dy in range(-n, n + 1):
                for a, b, c in self.cells.get((gx + dx, gy + dy), ()):
                    if c == cnn or self.name.get(c) != key:
                        continue
                    d = seg_dist(q, a, b)
                    if d <= bd and self.interior(q, c):
                        best, bd = c, d
        return best

    def renamed(self, cnn):
        """Active blocks of another name that took a retired block's place:
        each at least RENAMED_MIN_M long and lying, every vertex, within
        RENAMED_M of the retired line, so it runs along it rather than across.
        Avenue of the Palms on Treasure Island is Treasure Island Road now,
        realigned by a few metres, so the tolerance is wider than E2's."""
        if cnn in self.active or cnn not in self.line:
            return []
        old = self.line[cnn]
        found = set()
        for q in _samples(old):
            c = self.nearest(q, None, RENAMED_M)
            if c and self.name.get(c) != self.name[cnn]:
                found.add(c)
        return sorted(c for c in found
                      if length_m(self.lonlat[c]) >= RENAMED_MIN_M
                      and all(min(seg_dist(p, a, b) for a, b in zip(old, old[1:])) <= RENAMED_M for p in self.line[c]))

    def successors(self, cnn):
        """The active blocks of the same street lying on a retired block's line."""
        if cnn in self.active or cnn not in self.line:
            return []
        key, out = self.name[cnn], []
        found = set()
        for q in _samples(self.line[cnn]):
            c = self.nearest(q, key, TOLERANCE_M)
            if c and c not in found:
                found.add(c)
                out.append(c)
        # A successor must lie along the retired block, not merely touch its end.
        keep = []
        for c in out:
            if all(min(seg_dist(p, a, b) for a, b in zip(self.line[cnn], self.line[cnn][1:])) <= TOLERANCE_M
                   for p in self.line[c]):
                keep.append(c)
        return keep


def _samples(qs):
    """Points every SAMPLE_M metres along a projected line, vertices included."""
    out = [qs[0]]
    for a, b in zip(qs, qs[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L // SAMPLE_M))
        for i in range(1, n + 1):
            t = i / n
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return out


def _simplify(qs, tol=0.5):
    """Drop points within tol metres of the line through their neighbours."""
    out = [qs[0]]
    for i in range(1, len(qs) - 1):
        if seg_dist(qs[i], out[-1], qs[i + 1]) > tol:
            out.append(qs[i])
    out.append(qs[-1])
    return out


class Snapper:
    def __init__(self, centerline=None):
        self.cl = centerline or Centerline()
        self.log = []          # one entry per row changed
        self._by_old = {}      # (old cnn, street, from, to) -> [(new cnn, share)]

    def pieces(self, cnn, street, pts, twin=False):
        """[(cnn or None, lon/lat points, how)] for one row's line. `how` is
        kept, snapped, path (off any block of its street) or retired (on the
        retired block SFMTA typed, which no active block replaced). With
        twin, each sample beside a divided street's carriageway goes to the
        other carriageway (see live_rows)."""
        cl = self.cl
        if cnn and cnn in cl.active and cl.max_dist(pts, cnn) <= TOLERANCE_M:
            return [(cnn, pts, "kept")]
        # The row lies along the block SFMTA typed, which is retired.
        on_retired = bool(cnn) and cnn in cl.line and cnn not in cl.active and cl.max_dist(pts, cnn) <= TOLERANCE_M
        key = name_key(street)
        if not key:
            # A row with no street name is a street row only when it lies on
            # the block SFMTA typed. Otherwise it is a path, wherever it runs:
            # a line beside a street does not take that street's CNN.
            if not on_retired:
                return [(None, pts, "path")]
            key = cl.name[cnn]
        # A retired block that a block of another name replaced along its
        # whole line: the street was renamed (Avenue of the Palms, on
        # Treasure Island, is Treasure Island Road now).
        alias = set(cl.renamed(cnn)) if on_retired else set()
        qs = [proj(p) for p in pts]
        samples = _samples(qs)
        # Where a street has two parallel carriageways (Octavia Boulevard,
        # Market Street at Octavia), SFMTA's own choice of block stands
        # whenever that block is about as near as the nearest one, or runs
        # beside it as the street's other carriageway.
        keep = cnn if cnn in cl.active and cl.name.get(cnn) == key else None
        plain = [cl.nearest(q, key, SEARCH_M, also=alias) for q in samples]
        labels = list(plain)
        if keep:
            for i, q in enumerate(samples):
                d_keep = cl.dist(q, keep)
                if labels[i] != keep and d_keep <= SEARCH_M and (
                        labels[i] is None or d_keep <= cl.dist(q, labels[i]) + TOLERANCE_M
                        or (cl.interior(q, keep) and cl.interior(q, labels[i]))):
                    labels[i] = keep

        def runs_of(labels):
            runs = []
            for i, (q, lab) in enumerate(zip(samples, labels)):
                if runs and runs[-1][0] == lab:
                    runs[-1][1].append(q)
                    runs[-1][2].append(i)
                else:
                    runs.append([lab, [q], [i]])
            return runs

        def on_block(lab, qq):
            line = []
            for q in qq:
                c = cl.on(q, lab)
                if not line or math.hypot(c[0] - line[-1][0], c[1] - line[-1][1]) > 0.01:
                    line.append(c)
            return line

        def plen(qq):
            return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(qq, qq[1:]))

        # Samples past the end of a block project onto its end point; a run
        # that is only that is not on the block. Where SFMTA's block was
        # preferred and is not really there, the nearest block stands instead.
        runs = runs_of(labels)
        if keep:
            for lab, qq, ix in runs:
                if lab == keep and plen(on_block(lab, qq)) < MIN_PIECE_M:
                    for i in ix:
                        labels[i] = plain[i]
            runs = runs_of(labels)
        if twin:
            labels = [(cl.twin(q, lab) or lab) if lab else lab for q, lab in zip(samples, labels)]
            runs = runs_of(labels)
        runs = [[lab, qq] for lab, qq, _ in runs]
        for r in runs:
            if r[0] is not None and plen(on_block(r[0], r[1])) < MIN_PIECE_M:
                r[0] = None
        # A short gap between two runs on the same block (a bend in the
        # drawn line that swings past SEARCH_M) belongs to that block.
        for i in range(1, len(runs) - 1):
            if runs[i][0] is None and runs[i - 1][0] and runs[i - 1][0] == runs[i + 1][0] and plen(runs[i][1]) < 50:
                runs[i][0] = runs[i - 1][0]
        # A short unmatched end is the row running into the intersection box
        # past its block's end; it is not a path of its own.
        if any(r[0] for r in runs):
            while runs and runs[0][0] is None and plen(runs[0][1]) < END_M:
                runs.pop(0)
            while runs and runs[-1][0] is None and plen(runs[-1][1]) < END_M:
                runs.pop()
        merged = []
        for lab, qq in runs:
            if merged and merged[-1][0] == lab:
                merged[-1][1].extend(qq[1:] if merged[-1][1][-1] == qq[0] else qq)
            else:
                # Runs share their boundary sample so no length falls between.
                merged.append([lab, ([merged[-1][1][-1]] if merged else []) + qq])
        out = []
        unkeyed = "retired" if on_retired else "path"
        for lab, qq in merged:
            if lab is None:
                if plen(qq) >= MIN_PIECE_M:
                    out.append((None, [unproj(q) for q in _simplify(qq)], unkeyed))
                continue
            line = on_block(lab, qq)
            if plen(line) < MIN_PIECE_M:
                continue
            # The same block can come back after a gap (Twin Peaks Boulevard's
            # figure eight); each visit is its own piece, so no length is lost.
            out.append((lab, [unproj(q) for q in _simplify(line)], "snapped"))
        if not out:
            # Shorter than one piece everywhere: keep it as an unkeyed path.
            out = [(None, pts, unkeyed)]
        return out

    def live_rows(self, records, pts_by_oid):
        """The layer's rows, re-keyed and split. Each copy carries `CNN`,
        `_pts`, `_share` (its fraction of the row's length), `_mi` (that
        fraction of the row's own drawn length, so splitting and snapping
        neither add nor lose miles; None on a row kept whole) and `_snap`. LENGTH and LENGTH_FT are
        scaled by the share.

        A divided street. SFMTA holds one row per direction of travel, and on
        a street the centerline draws as two carriageways it sometimes draws
        both direction rows as one line and types one CNN for both (Terry A
        Francois Boulevard between South Street and Mariposa). Snapped by
        nearest, both would land on one carriageway and the other would read
        as having no bikeway. So where exactly two on-street rows of one
        class share one line, one street and one typed CNN, the second is
        snapped to the other carriageway wherever it runs beside one, and
        each carriageway gets one direction row."""
        pair = collections.defaultdict(list)
        for r in records:
            pts = pts_by_oid.get(r["OBJECTID"])
            if pts and cnn_key(r.get("CNN")) and r.get("FACILITY_T") in ON_STREET:
                pair[(tuple(map(tuple, pts)), cnn_key(r.get("CNN")), name_key(r.get("STREETNAME")), r.get("FACILITY_T"))].append(r["OBJECTID"])
        second = {sorted(v)[1] for v in pair.values() if len(v) == 2}
        out = []
        for r in records:
            pts = pts_by_oid.get(r["OBJECTID"])
            old = cnn_key(r.get("CNN"))
            if not pts or not old:
                out.append(dict(r, _pts=pts, _share=1.0, _mi=None, _snap="unkeyed" if pts else "no geometry"))
                continue
            ps = self.pieces(old, r.get("STREETNAME"), pts, twin=r["OBJECTID"] in second)
            total = sum(length_m(p) for _, p, _ in ps) or 1.0
            k = (old, name_key(r.get("STREETNAME")), name_key(r.get("FROM_ST")), name_key(r.get("TO_ST")))
            shares = []
            for c, p, how in ps:
                share = length_m(p) / total
                row = dict(r, CNN=float(c) if c else None, _pts=p, _share=share,
                           _mi=None if how == "kept" else length_m(pts) * share / MILE_M, _snap=how)
                for f in ("LENGTH", "LENGTH_FT"):
                    if isinstance(r.get(f), (int, float)):
                        row[f] = r[f] * share
                out.append(row)
                shares.append((c, share, p))
            # Every live row under one key, in layer order: a capture's rows
            # under that key take them in the same order (a divided street's
            # two direction rows go to its two carriageways in both).
            self._by_old.setdefault(k, []).append(shares)
            if ps[0][2] != "kept":
                self.log.append({"oid": r["OBJECTID"], "cnn": old, "street": r.get("STREETNAME"),
                                 "from": r.get("FROM_ST"), "to": r.get("TO_ST"), "facility": r.get("FACILITY_T"),
                                 "was_m": round(self.cl.max_dist(pts, old), 1) if old in self.cl.line else None,
                                 "retired": old in self.cl.line and old not in self.cl.active,
                                 "twin": r["OBJECTID"] in second,
                                 "to_cnns": [c for c, _, _ in ps], "how": sorted({h for _, _, h in ps}),
                                 "pieces": [(c, round(length_m(p), 1), h) for c, p, h in ps]})
        return out

    def snapshot_rows(self, records):
        """A capture's rows under the live layer's keys. A row with its own
        geometry is snapped like a live row; one without is matched to a live
        row by old CNN, street and cross streets, and failing that a retired
        CNN is split over the blocks that replaced it."""
        out = []
        taken = collections.Counter()
        for r in records:
            old = r.get("cnn")
            if not old:
                out.append(r)
                continue
            if r.get("pts"):
                ps = self.pieces(old, r.get("street"), r["pts"])
                total = sum(length_m(p) for _, p, _ in ps) or 1.0
                for c, p, _ in ps:
                    share = length_m(p) / total
                    out.append(dict(r, cnn=c, pts=p, mi=length_m(r["pts"]) * share / MILE_M,
                                    len_mi=(r.get("len_mi") or 0) * share if r.get("len_mi") else r.get("len_mi")))
                continue
            k = (old, name_key(r.get("street")), name_key(r.get("from")), name_key(r.get("to")))
            live = self._by_old.get(k)
            shares = None
            if live:
                shares = live[min(taken[k], len(live) - 1)]
                taken[k] += 1
            if shares is None and old not in self.cl.active:
                succ = self.cl.successors(old)
                if succ:
                    L = [length_m(self.cl.lonlat[c]) for c in succ]
                    shares = [(c, l / sum(L), None) for c, l in zip(succ, L)]
            if not shares or [(c, sh) for c, sh, _ in shares] == [(old, 1.0)]:
                out.append(r)
                continue
            for c, share, p in shares:
                # A piece that became an unkeyed path takes the live row's
                # line, so the capture row lands on the same path key.
                out.append(dict(r, cnn=c, pts=None if c else p,
                                len_mi=(r.get("len_mi") or 0) * share if r.get("len_mi") else r.get("len_mi")))
        return out


ROOT = paths.ROOT
GEOMETRY = os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "geometry.json")


_shared = []
_layers = {}


def shared_snapper():
    """One Snapper per process, so every script that re-keys the layer loads
    and grids the centerline once and sees the same rows."""
    if not _shared:
        _shared.append(Snapper())
    return _shared[0]


def rekeyed_layer(records, snapper=None, pts_by_oid=None):
    """The live layer's rows (network.json records), re-keyed and split, with
    each row's line from the tracked geometry extract (or pts_by_oid). A row
    with no line passes through as SFMTA keyed it. The result is computed once
    per process for a given snapper and layer; each caller gets its own copy
    of every row, so one script's edits to a row never reach another's."""
    import json
    snapper = snapper or shared_snapper()
    sig = (id(snapper), len(records), hash(tuple((r.get("OBJECTID"), r.get("CNN"), r.get("STREETNAME"), r.get("FACILITY_T"))
                                                  for r in records)), pts_by_oid is None)
    if sig not in _layers:
        pts = pts_by_oid if pts_by_oid is not None else {g["oid"]: g["pts"] for g in json.load(open(GEOMETRY))["records"]}
        _layers[sig] = snapper.live_rows(records, pts)
    return [dict(r) for r in _layers[sig]]


def main():
    import json
    net = json.load(open(os.path.join(ROOT, "data", "extract", "sfmta-bikeway", "network.json")))
    s = Snapper()
    rows = rekeyed_layer(net["records"], s)
    print("%d layer rows -> %d after splitting; %d rows re-keyed" % (len(net["records"]), len(rows), len(s.log)))
    for e in s.log:
        print("  oid %-5s %-9s %-26s %s -> %s  was %s m%s  %s" % (
            e["oid"], e["cnn"], e["street"], e["from"], e["to"], e["was_m"],
            " (retired)" if e["retired"] else "", ", ".join("%s %.0f m" % (c or how, m) for c, m, how in e["pieces"])
            + ("  [second of a divided street's direction pair]" if e["twin"] else "")))


if __name__ == "__main__":
    main()
