"""Place community plans' proposed bikeways on city street blocks, and mark the ones the Biking and Rolling Plan left out.

Input is data/community-plans/bikeway-proposals.json: one row per bikeway a
community or neighborhood transportation plan proposed, read from the plan PDF
with its street, FROM and TO cross streets, page and quote. Each row is walked
onto DataSF 3psu-pn9h centerline blocks with place() from
tools/bike-network/north-star-index.py, the same matcher that digitised the plan's North
Star network, so the two layers agree block by block.

Each block is then graded against two all-ages layers, by cnn, and by geometry
for a line on a different cnn running along it (LineIndex):
  today   today's all-ages network, as lib/school-travel-time.py reads it
          (site/data/bike-history, codes 1, 4, S, 2c and 3c)
  plan    the Biking and Rolling Plan's North Star line drawn Separated,
          Shared, Shared-use Path or Car-free (site/data/north-star/traced.geojson)
A block on neither is a gap filler: a community plan recommended a bikeway
there and the 2025 plan draws no all-ages line on it. A block only a plan
considered and set aside is graded "considered", not a gap.

The brp-draft-2024 rows (SFMTA's November 2024 first draft) were traced off
its map, not read from text; data/community-plans/brp-draft-extents.json,
written by tools/bike-network/brp-draft-trace.py, holds the block ids each was traced
to, so a placement here can be checked against it.

Rows whose ends name no cross street ("not stated", "the map edge") are listed
as unplaced with the reason, never guessed.

Outputs, under out/community-plans/
  blocks.geojson   one feature per placed block, with the proposing plan(s)
  unplaced.csv     rows that could not be placed, with the reason
  summary.md       counts and miles by plan and by grade
and the site's copy, site/data/community-plans/blocks.json, which the
/transportation/bike/community-plans page reads: the plans, the proposals, and
per block its line (lon/lat at six decimals), grade, street, feet and the
proposals on it. A gap block is split by who asked for it: "community" when any
neighborhood or community plan recommends it, "bikeplan" when only the 2009
citywide Bicycle Plan does. Everything is sorted and carries no run stamp, so a
rerun with no change in its inputs leaves git clean (lib/stable.py).

    python3 tools/bike-network/community-plan-bikeways.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv
import importlib.util
import json
import math
import os
import re
import sys
from collections import defaultdict

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)


def load(name, file):
    return paths.load(file, name)


nsi = load("north_star_index", "north-star-index.py")
import stable  # noqa: E402  (lib, on the path above)
# Names the plans use that the centerline file spells differently. Phelan Ave
# was renamed Frida Kahlo Way in 2018.
nsi.ALIASES.update({"PHELAN": "FRIDA KAHLO", "TERRY FRANCOIS": "TERRY A FRANCOIS"})

PROPOSALS = os.path.join(ROOT, "data", "community-plans", "bikeway-proposals.json")
BIKE = os.path.join(ROOT, "site", "data", "bike-history")
NS = os.path.join(ROOT, "site", "data", "north-star")
OUT = os.path.join(ROOT, "out", "community-plans")
SITE_OUT = os.path.join(ROOT, "site", "data", "community-plans", "blocks.json")
# The 2009 Bicycle Plan is citywide, not a neighborhood plan, so its asks are
# kept apart from the community plans' on the page.
CITYWIDE = {"bikeplan-2009"}
# Short names for the page's table and popover, in the plans' own words.
SHORT = {
    "bayview-cbtp-2020": "Bayview Community Based Transportation Plan",
    "wa-cbtp-2017": "Western Addition Community-Based Transportation Plan",
    "d4-mobility-2021": "District 4 Mobility Study",
    "chinatown-ntp-2015": "Chinatown Neighborhood Transportation Plan",
    "columbus-2010": "Columbus Avenue Neighborhood Transportation Study",
    "tenderloin-ntp-2007": "Tenderloin-Little Saigon Neighborhood Transportation Plan",
    "ocean-map-2023": "Ocean Avenue Mobility Action Plan",
    "ocean-geneva-cdp-2015": "Ocean and Geneva Corridor Design Plan",
    "balboa-park-plan-map": "Balboa Park Station Area Plan",
    "eom-strategy-2018": "Excelsior and Outer Mission Neighborhood Strategy",
    "brp-cap-2025": "Biking and Rolling Plan Community Action Plans",
    "mission-streetscape-2010": "Mission District Streetscape Plan",
    "showplace-potrero-2007": "Showplace Square / Potrero Hill Area Plan",
    "en-map-2008": "Eastern Neighborhoods Plan",
    "cwd-prp-2018": "Central Waterfront / Dogpatch Public Realm Plan",
    "port-waterfront-plan-2024": "Port of San Francisco Waterfront Plan",
    "cphps-tp-2018": "Candlestick Point Hunters Point Shipyard Transportation Plan",
    "safer-illinois-2023": "Safer Illinois",
    "bikeplan-2009": "San Francisco Bicycle Plan",
}


def short(plans, k):
    """A plan's short name: SHORT above, or the "short" field a newer plan row carries."""
    return SHORT.get(k) or plans[k]["short"]
CACHE = os.path.join(ROOT, "out", "north-star", "cache")
TODAY_CODES = {"1", "4", "S", "2c", "3c"}           # as lib/school-travel-time.py
PLAN_FACILITIES = {"Separated", "Car-free", "Shared-use Path", "Shared"}
FT_PER_M = 3.28084

# Words that describe an end without naming a cross street.
VAGUE = re.compile(r"\b(not stated|map edge|no street named|study area)\b", re.I)
# Said anywhere in an end's label, brackets included, these mean the plan
# names no cross street there ("Fillmore neighborhood (west end not stated)").
UNNAMED = re.compile(r"\b(not stated|map edge|no street named)\b", re.I)
# A block this short that sits between two all-ages blocks is an intersection
# stub, not a stretch a plan left out.
STUB_FT = 100


def clean_end(label):
    """'Washington St (study area south end)' -> 'Washington St'; 'east to X' -> 'X'; vague -> None."""
    if UNNAMED.search(label or ""):
        return None
    s = re.sub(r"\([^)]*\)", "", label or "").strip()
    s = re.sub(r"^(east|west|north|south)\s+(past\s+\S+\s+\S+\s+)?to\s+", "", s, flags=re.I)
    s = re.sub(r"\babout\s+", "", s, flags=re.I)
    s = re.sub(r"\s+and\s+", " / ", s)
    s = re.sub(r"^the\s+", "", s, flags=re.I) if s.lower().startswith("the panhandle") else s
    if not s:
        return ""
    if VAGUE.search(label) and not s:
        return None
    if VAGUE.search(s):
        return None
    return s


def clean_street(label):
    """'Ocean Ave (westbound side)' -> 'Ocean Ave'; 'Cesar Chavez St and 26th St' -> ['Cesar Chavez St', '26th St']."""
    s = re.sub(r"\([^)]*\)", "", label or "").strip()
    if VAGUE.search(label) or "no street named" in label:
        return []
    s = re.sub(r"^[^:]*:\s*", "", s)                # "Glen Park area: Arlington St, ..."
    return [p.strip() for p in re.split(r"\s+and\s+|,\s*", s) if p.strip()]


def all_ages_cnns():
    segments = json.load(open(os.path.join(BIKE, "segments.json")))
    components = json.load(open(os.path.join(BIKE, "components.json")))
    last = len(segments["years"]) - 1
    today, today_lines, plan_lines = set(), [], []
    for s in segments["segments"]:
        if s["y"][last] == "0":
            continue
        comp = components["blocks"].get(s["key"])
        if not comp:
            continue
        codes = set(comp["m"])
        if comp.get("s") is not None:
            codes.add("S")
        if codes & TODAY_CODES:
            if s.get("cnn"):
                today.add(str(s["cnn"]))
            today_lines.append(s["pts"])
    plan = {}
    for f in json.load(open(os.path.join(NS, "traced.geojson")))["features"]:
        p = f["properties"]
        if p["facility"] in PLAN_FACILITIES:
            plan[str(p["cnn"])] = p["facility"]
            plan_lines.append(f["geometry"]["coordinates"])
    return today, plan, LineIndex(today_lines), LineIndex(plan_lines)


class LineIndex:
    """Line pieces in a 50 m grid, to ask whether a block runs along one.

    The grades above go by cnn, and a bikeway can sit on a different cnn from
    the block a plan names: the other carriageway of a divided street, or a
    path the layer carries with no cnn. A block counts as on a line when most
    of its length lies within NEAR_M of a piece running the same way (within
    ANGLE_DEG), so a line that only crosses it does not count."""
    NEAR_M, ANGLE_DEG, CELL = 12.0, 20.0, 50.0

    def __init__(self, runs):
        self.pieces, self.grid = [], defaultdict(list)
        for run in runs:
            pts = [xy(p) for p in run]
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    continue
                k = len(self.pieces)
                self.pieces.append((a, b))
                for gx in range(int(min(a[0], b[0]) // self.CELL) - 1, int(max(a[0], b[0]) // self.CELL) + 2):
                    for gy in range(int(min(a[1], b[1]) // self.CELL) - 1, int(max(a[1], b[1]) // self.CELL) + 2):
                        self.grid[(gx, gy)].append(k)

    def runs_along(self, line):
        pts = [xy(p) for p in line]
        samples = []
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(math.dist(a, b) // 10))
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            samples += [((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n), ang) for i in range(1, n)] or [(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), ang)]
        if not samples:
            return False
        hits = 0
        for p, ang in samples:
            for k in self.grid.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
                a, b = self.pieces[k]
                d = abs(math.degrees(ang - math.atan2(b[1] - a[1], b[0] - a[0]))) % 180
                if min(d, 180 - d) <= self.ANGLE_DEG and seg_dist(p, a, b) <= self.NEAR_M:
                    hits += 1
                    break
        return hits / len(samples) > 0.5


def xy(p):
    return (p[0] * 111_320 * nsi.COS, p[1] * 111_320)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def first_end(label):
    """'Vicente St / Sloat Blvd' -> 'Vicente St': the first named end, not the alternative."""
    return label.split("/")[0].strip() if label else label


def end_nodes(street, label, by_base, by_base_type, node_streets):
    """The street's nodes that a centerline named `label` also meets, by name only."""
    segs = []
    for part in street.split("/"):
        sbase, styp = nsi.norm(part)
        segs += (by_base_type.get((sbase, styp)) if styp else None) or by_base.get(sbase, [])
    own = {s["f_node_cnn"] for s in segs} | {s["t_node_cnn"] for s in segs}
    xb, _ = nsi.norm(label)
    return {n for n in own if xb in node_streets.get(n, ())}


def place_leg(street, frm, to, by_base, by_base_type, node_streets, node_xy, by_cnn):
    """place() from north-star-index.py, held to the ends the plan names.

    An end with alternatives ("Vicente St / Sloat Blvd") is tried by its first
    name alone, so place() never reaches the alternative, or a cross street it
    can only find by distance (nearest()), when the first name matches. Then
    every block whose middle lies past either named end, along the line from
    one end to the other, is dropped: place() walks a divided street's other
    carriageway and an offset intersection a block or more past the end
    (Geary west of 25th Ave, Ocean west of Frida Kahlo). Done here rather than
    in place() so the North Star trace it also serves does not change."""
    a, b = first_end(frm), first_end(to)
    cnns, why = nsi.place({"street": street, "from": a, "to": b}, by_base, by_base_type, node_streets, node_xy)
    if not cnns and (a != frm or b != to):
        a, b = frm, to
        cnns, why = nsi.place({"street": street, "from": a, "to": b}, by_base, by_base_type, node_streets, node_xy)
    if not cnns:
        return cnns, why
    A = end_nodes(street, a, by_base, by_base_type, node_streets) if a else set()
    B = end_nodes(street, b, by_base, by_base_type, node_streets) if b else set()
    A, B = [node_xy[n] for n in A if n in node_xy], [node_xy[n] for n in B if n in node_xy]
    if not A or not B:
        return cnns, why
    ax, ay = sum(p[0] for p in A) / len(A), sum(p[1] for p in A) / len(A)
    bx, by = sum(p[0] for p in B) / len(B), sum(p[1] for p in B) / len(B)
    L = math.hypot(bx - ax, by - ay)
    if L < 1:
        return cnns, why
    ux, uy = (bx - ax) / L, (by - ay) / L
    # An end can be several nodes (a divided street, an offset intersection).
    # The stretch runs from the A node nearest B to the B node nearest A, so
    # a block between two of B's nodes, past the first, is not kept: 15th Ave
    # meets Noriega at three nodes, and the centroid kept the block beyond.
    lo = max((p[0] - ax) * ux + (p[1] - ay) * uy for p in A)
    hi = min((p[0] - ax) * ux + (p[1] - ay) * uy for p in B)
    if hi - lo < 1:
        lo, hi = 0.0, L
    kept = []
    for c in cnns:
        co = by_cnn[str(int(float(c)))]["line"]["coordinates"]
        mx, my = xy(co[len(co) // 2]) if len(co) > 2 else xy(((co[0][0] + co[-1][0]) / 2, (co[0][1] + co[-1][1]) / 2))
        t = (mx - ax) * ux + (my - ay) * uy
        if lo - TRIM_M <= t <= hi + TRIM_M:
            kept.append(c)
    return kept, why


TRIM_M = 20.0


def carriageway_pairs(features):
    """The features to drop so a divided street counts once.

    3psu-pn9h gives each carriageway of a divided street its own cnn, sharing
    the thousands and differing in the hundreds (9817101 and 9817201). For each
    street and thousands, the side with the most feet is kept, and it takes
    the best network grade of either side (BEST), so an all-ages line on the
    dropped carriageway is not lost: Cargo Way's 3693101 is all-ages today and
    the longer side it pairs with is only in the plan."""
    groups = defaultdict(lambda: defaultdict(list))
    for f in features:
        c = int(f["properties"]["cnn"])
        if c % 1000 >= 100:
            groups[(nsi.base_of_centerline(f["properties"]["street"] or ""), c // 1000)][(c % 1000) // 100].append(f)
    drop = set()
    for sides in groups.values():
        if len(sides) < 2:
            continue
        keep = max(sorted(sides), key=lambda k: sum(f["properties"]["feet"] for f in sides[k]))
        drop |= {f["properties"]["cnn"] for k, fs in sides.items() if k != keep for f in fs}
        best = min((BEST.index(f["properties"]["grade"]) for fs in sides.values() for f in fs if f["properties"].get("grade") in BEST), default=None)
        if best is not None:
            for f in sides[keep]:
                g = f["properties"].get("grade")
                if g not in BEST or BEST.index(g) > best:
                    f["properties"]["grade"] = BEST[best]
    return drop


# Network grades, best first: a block's carriageways share the best of them.
BEST = ["today", "plan", "undecided"]


def trace_holes(features, by_cnn, undecided):
    """Gap blocks whose same-street neighbours at both ends the 2025 plan draws Undecided.

    The North Star trace has no feature for a few blocks inside a line the
    map draws continuously; Clarendon Ave's Panorama to Ashwood and Galewood
    to Olympia blocks sit between Undecided blocks. Such a block is graded
    Undecided too, rather than left out. Only Undecided is filled this way:
    a hole in a Separated or Shared line would hide a real gap if guessed."""
    at = defaultdict(set)
    for c, s in by_cnn.items():
        for n in (s["f_node_cnn"], s["t_node_cnn"]):
            at[n].add(c)
    out = set()
    for f in features:
        p = f["properties"]
        if p["grade"] != "gap":
            continue
        s = by_cnn[p["cnn"]]
        ends = [[c for c in at[n] if c != p["cnn"] and by_cnn[c].get("streetname") == s.get("streetname")]
                for n in (s["f_node_cnn"], s["t_node_cnn"])]
        if all(e and all(c in undecided for c in e) for e in ends):
            out.add(p["cnn"])
    return out


TWIN_M, TWIN_ANGLE = 60.0, 20.0


def parallel_twins(features):
    """Placed blocks that run beside another placed block of the same street, to drop so it counts once.

    carriageway_pairs() catches a divided street whose sides share the cnn's
    thousands. Some do not: the Great Highway's west side is one 10,481 ft
    centerline (cnn 6436101) beside the block-by-block east side (8508000 to
    8524000), about 45 m away. A block is a twin when most of its length lies
    within TWIN_M of another block of the same street running the same way
    (within TWIN_ANGLE), measured square to that block, so the next block along
    the same line never counts. Longest first, and a dropped block no longer
    counts as a partner, so of two equal sides one is kept."""
    groups = defaultdict(list)
    for f in features:
        groups[nsi.base_of_centerline(f["properties"]["street"] or "")].append(f)
    drop = set()
    for fs in groups.values():
        if len(fs) < 2:
            continue
        pieces = {}
        for f in fs:
            pts = [xy(q) for q in f["geometry"]["coordinates"]]
            pieces[f["properties"]["cnn"]] = [(a, b) for a, b in zip(pts, pts[1:]) if a != b]
        for f in sorted(fs, key=lambda f: (-f["properties"]["feet"], f["properties"]["cnn"])):
            c = f["properties"]["cnn"]
            others = [pc for k, ps in pieces.items() if k != c and k not in drop for pc in ps]
            if not others:
                continue
            samples = []
            for a, b in pieces[c]:
                n = max(1, int(math.dist(a, b) // 10))
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                samples += [((a[0] + (b[0] - a[0]) * (i + 0.5) / n, a[1] + (b[1] - a[1]) * (i + 0.5) / n), ang) for i in range(n)]
            if not samples:
                continue
            hits = sum(1 for pt, ang in samples if any(beside(pt, ang, a, b) for a, b in others))
            if hits / len(samples) > 0.5:
                drop.add(c)
    return drop


def beside(p, ang, a, b):
    """p lies square to piece a-b (its foot falls on the piece), within TWIN_M, and the two run the same way."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    if not 0.0 <= t <= 1.0:
        return False
    d = abs(math.degrees(ang - math.atan2(dy, dx))) % 180
    return min(d, 180 - d) <= TWIN_ANGLE and math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy) <= TWIN_M


def stubs(features, by_cnn, all_ages):
    """Gap blocks under STUB_FT whose neighbours on the same street are all all-ages.

    A neighbour is a block of the same street meeting either end that is placed
    (and must be graded today or plan) or is in `all_ages`, the cnns today's
    network or the 2025 plan carry. Frida Kahlo Way's 80 ft jog at Judson,
    between a Separated block and the end of the ask, is the case."""
    graded = {f["properties"]["cnn"]: f["properties"]["grade"] for f in features}
    at = defaultdict(set)
    for c, s in by_cnn.items():
        for n in (s["f_node_cnn"], s["t_node_cnn"]):
            at[n].add(c)
    out = set()
    for f in features:
        p = f["properties"]
        if p["grade"] != "gap" or p["feet"] >= STUB_FT:
            continue
        s = by_cnn[p["cnn"]]
        name = s.get("streetname")
        # Neighbours on the same street that are placed or all-ages; a block
        # past the proposal's end that nothing carries is left out of the test.
        nb = [c for n in (s["f_node_cnn"], s["t_node_cnn"]) for c in at[n]
              if c != p["cnn"] and by_cnn[c].get("streetname") == name and (c in graded or c in all_ages)]
        if nb and all(graded.get(c, "today") in ("today", "plan") for c in nb):
            out.add(p["cnn"])
    return out


def unplaced_reason(why):
    """The page's three reasons a proposal could not be drawn, from place()'s own words."""
    if why.startswith("street not in centerlines"):
        return "path"        # a path, bridge, trail or an unnamed street: no centerline to draw on
    if why.startswith("no continuous"):
        return "broken"      # the two ends don't join along one street
    return "end"             # an end that is a landmark, the map's edge, or not stated


def pdf_page(page):
    """'p. 10 (PDF page 12)' -> 12, '41 (PDF page 43)' -> 43; a bare printed number is not trusted as a PDF page."""
    m = re.search(r"PDF page (\d+)", page or "")
    return int(m.group(1)) if m else None


def proposal_count(rows):
    """Rows that propose something: a row describing lanes that already existed is not one."""
    return sum(1 for r in rows if not r.get("describes_existing"))


def asks(f, rows):
    """The plan ids that recommend a bikeway on a block: a set-aside option or a road diet is not an ask."""
    return {q["plan_id"] for q in f["properties"]["proposals"]
            if q["recommended"] and not rows[q["row"]].get("not_a_bikeway")}


# Grades that mean the 2025 plan draws no all-ages line on the block and
# none runs there today. "undecided" is drawn by the plan, so it is not one.
OUT_GRADES = {"gap", "considered", "notbike"}


def oriented(coords):
    """The block's line run west to east, or south to north when it runs more north-south.

    The page draws plans that share a block side by side with line-offset,
    which offsets to the right of the line's direction, so neighbouring blocks
    have to run the same way or the side-by-side lines swap at every block."""
    (x0, y0), (x1, y1) = coords[0], coords[-1]
    dx, dy = (x1 - x0) * nsi.COS, y1 - y0
    flip = dx < 0 if abs(dx) >= abs(dy) else dy < 0
    return list(reversed(coords)) if flip else coords


def site_json(d, plans, rows, features, unplaced, network_feet):
    """The page's data file: plans, proposals and blocks, sorted, with no run stamp.

    Plans run oldest first (year, then short name), which is the page's list
    order and the order its colours are dealt in. Each plan carries `feet`,
    the blocks it recommends a bikeway on, and `outFeet`, the part of those
    with no all-ages line today or in the 2025 plan; a block two plans ask
    for counts in both."""
    used = sorted({r["plan_id"] for r in rows} | set(plans), key=lambda k: (plans[k]["year"], short(plans, k)))
    pidx = {k: i for i, k in enumerate(used)}
    feet, out_feet = defaultdict(int), defaultdict(int)
    for f in features:
        for k in asks(f, rows):
            feet[k] += f["properties"]["feet"]
            if f["properties"]["grade"] == "gap":
                out_feet[k] += f["properties"]["feet"]
    unplaced_rows = {u["row"] for u in unplaced}
    out_plans = [{"id": k, "name": short(plans, k), "title": plans[k]["title"], "agency": plans[k]["agency"],
                  "year": plans[k]["year"], "url": plans[k]["url"], "citywide": k in CITYWIDE,
                  "kind": plans[k].get("kind", "plan"), "feet": feet[k], "outFeet": out_feet[k],
                  "proposalCount": sum(1 for i, r in enumerate(rows) if r["plan_id"] == k and not r.get("describes_existing")),
                  "unplacedCount": sum(1 for i in unplaced_rows if rows[i]["plan_id"] == k)} for k in used]
    placed_rows = sorted({q["row"] for f in features for q in f["properties"]["proposals"]})
    ridx = {r: i for i, r in enumerate(placed_rows)}
    proposals = []
    for r in placed_rows:
        x = rows[r]
        proposals.append({"plan": pidx[x["plan_id"]], "street": x["street"], "from": x["from"], "to": x["to"],
                          "page": x["page"], "pdfPage": pdf_page(x["page"]), "asWritten": x["facility_as_written"],
                          "recommended": bool(x["recommended"]), "bike": not x.get("not_a_bikeway")})
    blocks = []
    for f in features:
        p = f["properties"]
        qs = p["proposals"]
        who = None
        if p["grade"] == "gap":
            rec = [q for q in qs if q["recommended"]]
            who = "community" if any(q["plan_id"] not in CITYWIDE for q in rec) else "bikeplan"
        blocks.append({"cnn": p["cnn"], "street": p["street"], "grade": p["grade"], "who": who, "feet": p["feet"],
                       "line": [[round(x, 6), round(y, 6)] for x, y in oriented(f["geometry"]["coordinates"])],
                       "proposals": sorted({ridx[q["row"]] for q in qs})})
    reasons = defaultdict(int)
    for u in unplaced:
        reasons[unplaced_reason(u["reason"])] += 1
    out = {"read": d["read"], "mileBasis": "centerline block, each block counted once",
           "source": "data/community-plans/bikeway-proposals.json placed by tools/bike-network/community-plan-bikeways.py",
           "proposalCount": proposal_count(rows), "placedCount": proposal_count(rows) - len(unplaced),
           "networkFeet": network_feet,
           "plans": out_plans, "proposals": proposals, "blocks": blocks,
           "unplaced": {"byReason": dict(sorted(reasons.items())),
                        "rows": sorted(({"plan": pidx[u["plan_id"]], "street": u["street"], "from": u["from"], "to": u["to"],
                                         "page": u["page"], "reason": unplaced_reason(u["reason"])} for u in unplaced),
                                       key=lambda u: (u["plan"], u["street"], u["from"]))}}
    os.makedirs(os.path.dirname(SITE_OUT), exist_ok=True)
    stable.write_text(SITE_OUT, json.dumps(out, sort_keys=True, separators=(",", ":")) + "\n")


def network_feet(plan, by_cnn):
    """Feet of street the 2025 plan draws all-ages, each block once, by the same carriageway rule."""
    fs = [{"properties": {"cnn": c, "street": by_cnn[c].get("streetname") or by_cnn[c].get("street"),
                          "feet": round(nsi.seg_len_m(by_cnn[c]["line"]["coordinates"]) * FT_PER_M)}}
          for c in sorted(plan, key=int) if c in by_cnn]
    gone = carriageway_pairs(fs)
    return sum(f["properties"]["feet"] for f in fs if f["properties"]["cnn"] not in gone)


def main():
    d = json.load(open(PROPOSALS))
    plans = {p["id"]: p for p in d["plans"]}
    rows = d["segments"]

    cl = nsi.fetch_centerlines(CACHE)
    by_cnn = {}
    by_base, by_base_type = defaultdict(list), defaultdict(list)
    for s in cl:
        if not s.get("line") or not s.get("f_node_cnn"):
            continue
        s["cnn"] = str(int(float(s["cnn"])))
        by_cnn[s["cnn"]] = s
        b = nsi.base_of_centerline(s.get("streetname") or s.get("street") or "")
        by_base[b].append(s)
        by_base_type[(b, (s.get("st_type") or "").upper() or None)].append(s)
    node_streets, node_xy = defaultdict(set), {}
    for s in by_cnn.values():
        b = nsi.base_of_centerline(s.get("streetname") or s.get("street") or "")
        node_streets[s["f_node_cnn"]].add(b)
        node_streets[s["t_node_cnn"]].add(b)
        c = s["line"]["coordinates"]
        node_xy.setdefault(s["f_node_cnn"], (c[0][0] * 111_320 * nsi.COS, c[0][1] * 111_320))
        node_xy.setdefault(s["t_node_cnn"], (c[-1][0] * 111_320 * nsi.COS, c[-1][1] * 111_320))

    today, plan, today_near, plan_near = all_ages_cnns()
    undecided = {str(f["properties"]["cnn"]) for f in json.load(open(os.path.join(NS, "traced.geojson")))["features"]
                 if f["properties"]["facility"] == "Undecided"}
    blocks = {}                                   # cnn -> list of row indexes
    unplaced = []
    for i, r in enumerate(rows):
        if r.get("describes_existing"):
            continue                              # not a proposal: lanes that already existed
        streets = clean_street(r["street"])
        frm, to = clean_end(r["from"]), clean_end(r["to"])
        if r.get("legs"):
            # A row the data splits into one leg per street (legs_note says why).
            legs = [(g["street"], g["from"], g["to"]) for g in r["legs"]]
        else:
            # An end that packs two extents ("Kansas 23rd to 26th; 23rd ...")
            # with no legs in the data is not guessed at.
            if not streets or frm is None or to is None or (frm == "" and to == "") or ";" in (frm or "") + (to or ""):
                unplaced.append({**r, "row": i, "reason": "no street or no named cross street"})
                continue
            legs = [(st, frm, to) for st in streets]
        got, whys = set(), []
        for st, a, b in legs:
            cnns, why = place_leg(st, a, b, by_base, by_base_type, node_streets, node_xy, by_cnn)
            got |= set(cnns)
            if why:
                whys.append(why)
        if not got:
            unplaced.append({**r, "row": i, "reason": "; ".join(whys)})
            continue
        for c in got:
            blocks.setdefault(c, []).append(i)

    features = []
    for c in sorted(blocks, key=int):
        s = by_cnn[c]
        props = []
        for i in blocks[c]:
            r = rows[i]
            p = plans[r["plan_id"]]
            props.append({"row": i, "plan_id": r["plan_id"], "plan": p["title"], "year": p["year"], "url": p["url"], "page": r["page"],
                          "facility": r["facility_class"], "as_written": r["facility_as_written"],
                          "recommended": r["recommended"], "map_only": r["map_only"]})
        # A block only a plan considered and set aside ("considered") is not a gap filler.
        line = s["line"]["coordinates"]
        bike = [q for q in props if not rows[q["row"]].get("not_a_bikeway")]
        if c in today or today_near.runs_along(line):
            grade = "today"
        elif c in plan or plan_near.runs_along(line):
            grade = "plan"
        elif c in undecided:
            grade = "undecided"                   # the plan draws it, type Undecided
        elif not bike:
            grade = "notbike"                     # asked for, but not as a bikeway (Columbus road diet)
        else:
            grade = "gap" if any(q["recommended"] for q in bike) else "considered"
        length_m = nsi.seg_len_m(s["line"]["coordinates"])
        features.append({"type": "Feature",
                         "properties": {"cnn": c, "street": s.get("streetname") or s.get("street"),
                                        "grade": grade, "plan_facility": plan.get(c),
                                        "feet": round(length_m * FT_PER_M), "proposals": props},
                         "geometry": s["line"]})

    # A divided street counts once, and an intersection stub between two
    # all-ages blocks is not a stretch left out.
    gone = carriageway_pairs(features)
    features = [f for f in features if f["properties"]["cnn"] not in gone]
    gone = parallel_twins(features)
    features = [f for f in features if f["properties"]["cnn"] not in gone]
    holes = trace_holes(features, by_cnn, undecided)
    for f in features:
        if f["properties"]["cnn"] in holes:
            f["properties"]["grade"] = "undecided"
    gone = stubs(features, by_cnn, today | set(plan))
    features = [f for f in features if f["properties"]["cnn"] not in gone]

    site_json(d, plans, rows, features, unplaced, network_feet(plan, by_cnn))
    # The geojson's per-proposal row and plan id are for the site copy only.
    for f in features:
        for q in f["properties"]["proposals"]:
            q.pop("row", None)
            q.pop("plan_id", None)

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "blocks.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "read": d["read"], "features": features}, fh, sort_keys=True)
    with open(os.path.join(OUT, "unplaced.csv"), "w", newline="") as fh:
        keys = ["plan_id", "street", "from", "to", "page", "reason"]
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(unplaced)

    mi = lambda fs: sum(f["properties"]["feet"] for f in fs) / 5280
    by_grade = defaultdict(list)
    for f in features:
        by_grade[f["properties"]["grade"]].append(f)
    by_plan = defaultdict(lambda: defaultdict(list))
    for f in features:
        for p in {q["plan"] for q in f["properties"]["proposals"]}:
            by_plan[p][f["properties"]["grade"]].append(f)
    lines = ["# Community Plan Bikeways on City Blocks", "",
             f"{proposal_count(rows) - len(unplaced)} of {proposal_count(rows)} proposals placed on {len(features)} blocks. "
             f"Proposals read {d['read']}. Miles are centerline block miles, with one carriageway of a "
             "divided street such as Geary counted.", "",
             "| Grade | Blocks | Miles |", "|---|---|---|"]
    for g, label in (("gap", "No all-ages line today or in the 2025 plan"), ("plan", "In the 2025 plan, not built"),
                     ("today", "All-ages today"), ("undecided", "In the 2025 plan as Undecided"),
                     ("considered", "Considered and not recommended"), ("notbike", "Asked for, but not as a bikeway")):
        lines.append(f"| {label} | {len(by_grade[g])} | {mi(by_grade[g]):.1f} |")
    lines += ["", "Plans oldest first. Asked is every block a plan recommends a bikeway on; "
              "not in the 2025 plan is the part with no all-ages line today or in the plan. "
              "A block two plans ask for counts in both rows.", "",
              "| Year | Plan | Asked miles | Not in the 2025 plan | Today miles | Unplaced proposals |", "|---|---|---|---|---|---|"]
    site = json.load(open(SITE_OUT))
    for p in site["plans"]:
        g = by_plan[p["title"]]
        lines.append(f"| {p['year']} | {p['name']} | {p['feet'] / 5280:.1f} | {p['outFeet'] / 5280:.1f} | "
                     f"{mi(g['today']):.1f} | {p['unplacedCount']} of {p['proposalCount']} |")
    union = by_grade["gap"]                       # a gap block is one some plan recommends a bikeway on
    lines += ["", f"With every plan counted, {mi(union):.1f} miles on {len(union)} blocks have no all-ages line today "
              f"or in the 2025 plan. The 2025 plan draws {site['networkFeet'] / 5280:.1f} miles all-ages, each block once."]
    lines += ["", f"{len(unplaced)} proposals could not be placed; see unplaced.csv.", ""]
    open(os.path.join(OUT, "summary.md"), "w").write("\n".join(lines))
    print("\n".join(lines))
    for u in unplaced:
        print("  unplaced:", u["plan_id"], "|", u["street"], "|", u["from"], "|", u["to"], "|", u["reason"][:90], file=sys.stderr)


if __name__ == "__main__":
    main()
