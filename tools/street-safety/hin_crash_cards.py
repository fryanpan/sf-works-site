"""The crash card behind each person on the HIN people map: a plain account, a details list and a diagram spec per police crash report, joined from DataSF's crash, parties and victims tables.

Imported by tools/street-safety/hin-people-map.py (the severe injuries and deaths of 2022 to 2024) and tools/street-safety/street-safety-cards.py
(every injury crash since 2005, for the site); site/src/safety-map/crash-cards.js draws the cards from what `build` returns.

    import hin_crash_cards
    cards, stats = hin_crash_cards.build(cases, hin_years)

INPUTS, each one DataSF query cached by lib/sfdata.py (plus the active street centrelines, 3psu-pn9h, for the
diagram), crashes from 2022-01-01 on (the map's 2022 to 2024 police
people plus the fatality log's later deaths, which carry a case number):
  crashes  ubvf-ztfx, one row per crash: time, lighting, weather, road surface, collision type, pedestrian action,
           traffic control, intersection or midblock, the offset from the secondary road, primary collision factor.
  parties  8gtc-pjc6, one row per party ("drivers, pedestrians, bicyclists, and parked vehicles"): type, vehicle,
           direction of travel, movement before the crash, at-fault flag, age, sobriety, drugs, phone, autonomy.
  victims  nwes-mmgh, one row per person hurt, any severity, with the party they belonged to.
They join on case_id_pkey; a party is (case_id_pkey, party_number_ckey) and a victim (case_id_pkey, victim_id).

RULES. Nothing is inferred. A field the record leaves "Not Stated" is omitted, never printed as unknown.
  Point of impact: no public field records it (the CHP 555 damage area, item 48h, is not published), so each card says
  so. The diagram's dashed ring marks only where the report places the crash, at the intersection or on the block.
  Streets: the diagram draws DataSF 3psu-pn9h's surface centrelines (not freeways, paper streets or footways) around
  the crash point, north up, 150 ft from the point to the top edge, so a corner is an L, a T a T, and skewed and
  five-way junctions keep their angles; a midblock point sits on its block where the record puts it. A leg is a road
  passing within 50 ft of the point, from its nearest point outward. A crash with no such road keeps the generic cross
  and says so under the drawing.
  Divided streets: the city draws each direction of a divided street as its own centreline, and at a junction it pulls
  both to one node, so the two halves seem to pinch together there. Where two centrelines of one street leave a node
  apart and then run parallel, each is carried straight on to the node's cross line instead (`_straighten`), so the
  halves stay a median apart as they are on the ground. This is the one place the drawing departs from the centreline file.
  Parties on legs: a party going straight comes in on the leg that runs opposite its recorded direction (its recorded
  street), or, with no such leg, leaves on the leg that runs its way. A party that fits no leg, or whose recorded
  street isn't at this point, keeps the compass placement, marked with an asterisk. Backing is dashed; stopped or
  parked is a stub; no direction, no arrow. Walkers are drawn beside the ring, on the side of the street they walk
  along that the point is on (the record names no crosswalk leg). On a divided street a party takes the half on its right.
  Each party on a leg is drawn along that leg's own centreline (its track, `k`), so it stays on the drawn road and its
  arrow runs along it: a lane to the right of the line on a two-way street, on the line on a one-way street or one half
  of a divided one (the centreline file's `oneway`). A compass placement that would land off every drawn road is not
  drawn there: the party goes below the drawing, starred, with its recorded direction as a small arrow.
  Turns: the record doesn't settle whether a turning party's direction is its heading before or after the turn (CHP's
  manual, HPM 110.5 ch. 3, item 36c, asks for the pre-turn direction only when the area of impact is inside the
  intersection, and in SF's rows a left-turner against a straight-going party is recorded opposite it about as often as
  perpendicular to it). So both readings are tried, and a reading counts only if its approach and exit legs both exist
  here, the two legs make that turn, and the recorded street is the leg the recorded direction belongs to. One
  reading: drawn as a solid curve from one leg onto the other. Both: drawn dashed, and the party's line says the
  direction before or after the turn is unclear. Neither: a straight arrow with the turn named.
  Fault: the officer's at-fault party ("the involved party most at fault", HPM 110.5 ch. 4, item 12) and the primary
  collision factor are printed as the report's, in separate sentences, since a few rows pair them across modes.
  Ages: one source per person. Anyone hurt takes the victims table's age (victim_age), the table every person on the
  map comes from; a party nobody was hurt in takes the parties table's (party_age). The two disagree on some rows
  (case 230022717: 64 in parties, 65 in victims).
  Account: DataSF publishes the report's coded fields and no officer's narrative (none of the three tables has a
  free-text column; column lists read 2026-11-20), so the account is those fields in words, and the page prints it
  above the drawing (Bryan, 2026-11-20: "Is there any narrative we're not showing? If so show it before the map"). It
  is the party list (`pr`: who each party was, what the report says it was doing, who the officer marked at fault),
  each party's people and how badly each was hurt (`pi`, below), the primary factor from the details list, and `t`,
  which says "no party marked at fault" when the report marks none. Each fact is said once.
  Injuries: `pi[i]` lists party i's people from the victims table, every level, in DataSF's own words for the level
  (victim_degree_of_injury): [level] for the party's own person, [level, who] for anyone else filed under it (a
  passenger, with their age), level "k" Fatal Injury, "s" Severe Injury, "v" Other Visible Injury, "p" Complaint of
  Pain. A party whose own person has no row in the victims table ("all victims (parties who are injured)", the table's
  description) gets ["n"], printed as "no injury recorded"; a parked vehicle and a driverless car have no person.
  Colour: a party takes the map's colour for the worst injury among its people (`h`, 3 killed and 2 severe; below
  severe, `hl` is "v" for Other Visible Injury or "p" for Complaint of Pain); a party with nobody hurt is grey.
  Road names: each drawn street is labelled with its centreline name. On the generic cross only, a name comes from the
  street each vehicle or bike that is not turning was on, put on the axis of its direction; at an intersection the
  other recorded road takes the other axis. Two names on one axis: neither is shown.

Checks (assertions in `build`): a duplicate crash row, party key or victim key is allowed only off the map and only as
an identical repeat (case 260408381 repeats in the crash and parties tables, sources/datasf-traffic-crashes.md);
every crash on the map has at least one party, and every victim names a party of its crash.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402

SINCE = "collision_datetime >= '2022-01-01T00:00:00'"
CRASH_FIELDS = ("case_id_pkey,collision_datetime,collision_time,primary_rd,secondary_rd,distance,direction,weather_1,"
                "type_of_collision,mviw,ped_action,road_surface,road_cond_1,road_cond_2,lighting,control_device,intersection,"
                "vz_pcf_code,vz_pcf_description,party_at_fault")
PARTY_FIELDS = ("case_id_pkey,party_number_ckey,party_type,at_fault,party_age,party_sobriety,party_drug_physical,dir_of_travel,"
                "move_pre_acc,stwd_vehicle_type,street_of_travel,sp_info_1,sp_info_2,vehicle_autonomous")
VICTIM_FIELDS = "case_id_pkey,victim_id,party_number_ckey,victim_role,victim_age,victim_degree_of_injury"

NONE = {None, "", "Not Stated", "Not stated", "Unknown", "Not Collected"}   # street_of_travel is "Not Collected" on every 2005-2012 party
DIRS = {"North": "N", "South": "S", "East": "E", "West": "W"}
# Movement before the crash: the diagram's arrow shape and the words for it.
MOVE = {"Proceeding Straight": ("s", ""), "Making Left Turn": ("l", "turning left"), "Making Right Turn": ("r", "turning right"),
        "Making U Turn": ("u", "making a U-turn"), "Stopped In Road": ("x", "stopped"),
        "Crossed Into Opposing Lane - Unplanned": ("s", "crossing into the opposing lane"), "Backing": ("b", "backing up"), "Stopped": ("x", "stopped"),
        "Parked": ("x", "parked"), "Parking Maneuver": ("x", "parking"), "Slowing/Stopping": ("s", "slowing to stop"),
        "Changing Lanes": ("s", "changing lanes"), "Entering Traffic": ("s", "entering traffic"), "Merging": ("s", "merging"),
        "Traveling Wrong Way": ("s", "going the wrong way"), "Crossed Into Opposing Lane": ("s", "crossing into the opposing lane"),
        "Ran Off Road": ("s", "running off the road"), "Passing Other Vehicle": ("s", "passing"), "Other Unsafe Turning": ("s", "turning unsafely"),
        "Other": ("s", ""), "Not Stated": ("s", "")}
# Vehicle: (noun, glyph). Glyphs are drawn by hin-crash-cards.js.
VEH = {"Passenger Car": ("car", "car"), "Sport Utility Vehicle": ("SUV", "car"), "Minivan": ("minivan", "car"),
       "Pickup or Panel Truck": ("pickup or van", "truck"), "Pickup or Panel Truck with Trailer": ("pickup with a trailer", "truck"),
       "Two Axle Truck": ("truck", "truck"), "Three or More Axle Truck": ("large truck", "truck"), "Semi": ("semi truck", "truck"),
       "Two Axle Tow Truck": ("tow truck", "truck"), "Other Commercial": ("commercial vehicle", "truck"),
       "Public Transit Authority": ("transit vehicle", "bus"), "Paratransit": ("paratransit van", "bus"),
       "Police Car": ("police car", "car"), "Police Motorcycle": ("police motorcycle", "moto"), "Motorcycle": ("motorcycle", "moto"),
       "Motor Driven Cycle/Scooter": ("moped", "moto"), "Bicycle": ("bike", "bike"), "Electric Bicycle": ("e-bike", "bike"),
       "Motorized Bicycle": ("motorized bike", "bike"), "Go-ped, ZIP Electric Scooter, Motorboard": ("scooter or board", "scooter"),
       "Electrically Motorized Board": ("electric board", "scooter"), "Misc. Motor Vehicle": ("motor vehicle", "car"),
       "Unknown Hit and Run": ("vehicle", "car"), "Pedestrian": ("", "walk"),
       "Other Bus": ("bus", "bus"), "School Bus": ("school bus", "bus"), "Emergency Vehicle": ("emergency vehicle", "truck"),
       "Ambulance": ("ambulance", "truck"), "Fire Truck": ("fire truck", "truck"), "Truck or Truck Tractor": ("truck", "truck"),
       "Truck": ("truck", "truck"), "Passenger Car with Trailer": ("car with a trailer", "car"), "Other Vehicle": ("vehicle", "car"),
       "All Terrain Vehicle": ("all-terrain vehicle", "car"), "Moped": ("moped", "moto"), "Construction Equipment": ("construction vehicle", "truck"),
       "Minvian": ("minivan", "car"), "Other Commerical": ("commercial vehicle", "truck"), "Passenge Car": ("car", "car")}
INJ = {"Fatal Injury": ("was killed", 3), "Severe Injury": ("was severely injured", 2), "Other Visible Injury": ("had a visible injury", 1),
       "Complaint of Pain": ("complained of pain", 1)}
LEVEL = {"Fatal Injury": "k", "Severe Injury": "s", "Other Visible Injury": "v", "Complaint of Pain": "p"}   # `pi`, crash-cards.js LEVELS
# What the crash involved besides the parties' own vehicles (crashes.mviw, "motor vehicle involved with"), where the
# party list doesn't already show it: a pedestrian, a bicycle and another motor vehicle are parties with their own lines.
MVIW = {"Fixed Object": "a fixed object", "Other Object": "an object", "Parked Motor Vehicle": "a parked vehicle",
        "Motor Vehicle on Other Roadway": "a vehicle on another roadway", "Animal": "an animal", "Train": "a train"}
PED = {"Crossing in Crosswalk at Intersection": "crossing in the crosswalk at the intersection",
       "Crossing in Crosswalk Not at Intersection": "crossing in a midblock crosswalk",
       "Crossing Not in Crosswalk": "crossing outside a crosswalk", "In Road, Including Shoulder": "in the road",
       "Not in Road": "off the road", "Not In Road": "off the road", "In Road": "in the road",
       "Crossing In Crosswalk at Intersection": "crossing in the crosswalk at the intersection",
       "Approaching/Leaving School Bus": "approaching or leaving a school bus"}
COLL = {"Broadside": "broadside", "Head-On": "head-on", "Rear End": "rear-end", "Sideswipe": "sideswipe",
        "Vehicle/Pedestrian": "vehicle hitting a pedestrian", "Hit Object": "hit an object", "Overturned": "overturned"}
CONTROL = {"Functioning": "Signal or sign, working", "Not Functioning": "Signal or sign, not working",
           "Obscured": "Signal or sign, obscured", "None": "None present, or not a factor"}
LIGHT = {"Daylight": "Daylight", "Dark - Street Lights": "Dark, street lights on", "Dark - No Street Lights": "Dark, no street lights",
         "Dark - Street Lights Not Functioning": "Dark, street lights not working", "Dusk - Dawn": "Dusk or dawn"}


ORDINAL_WORDS = {w: "%d%s" % (i + 1, "ST" if i == 0 else "ND" if i == 1 else "RD" if i == 2 else "TH") for i, w in enumerate(
    "FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH".split())}


def street(s):
    """'MISSION STREET', 'Mission St.' and 'MISSION ST' to 'Mission St'; '05TH AV' to '5th Ave'."""
    if s in NONE:
        return ""
    s = re.sub(r"\s+", " ", re.sub(r"[.,]", " ", s).strip().upper())
    for a, b in (("STREET", "ST"), ("AVENUE", "AVE"), ("AV", "AVE"), ("BOULEVARD", "BLVD"), ("DRIVE", "DR"), ("ROAD", "RD"),
                 ("PLACE", "PL"), ("TERRACE", "TER"), ("HIGHWAY", "HWY"), ("BAY SHORE", "BAYSHORE")):
        s = re.sub(r"\b%s\b" % a, b, s)
    s = re.sub(r"\b0+(\d)", r"\1", s)
    for w, n in ORDINAL_WORDS.items():   # "THIRD STREET" as the centrelines name it, "3rd St"
        s = re.sub(r"\b%s\b(?= (ST|AVE)\b)" % w, n, s)
    # A bare number before St or Ave ("23 ST") takes its ordinal suffix, as the centrelines write it.
    s = re.sub(r"\b(\d+) (?=(ST|AVE)\b)", lambda m: m.group(1) + ("TH" if 10 <= int(m.group(1)) % 100 <= 20 else {1: "ST", 2: "ND", 3: "RD"}.get(int(m.group(1)) % 10, "TH")) + " ", s)
    s = s.title()
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)


# ---- Street geometry for the diagram: the city's centrelines around the crash point, north up. ----
CENTERLINE_FIELDS = "cnn,streetname,street,st_type,f_st,t_st,f_node_cnn,t_node_cnn,classcode,layer,oneway,line"   # the query hin-injury-kinds.py makes, so one cache entry serves both
FT_LAT = 364000.0
FT_LON = FT_LAT * math.cos(math.radians(37.76))
BOX_X, BOX_Y = 215, 160   # half the drawing in feet (260 x 196 px at PX_FT); roads are clipped to it
PX_FT = 95 / 150          # 150 ft from the point to the top edge, the reach the diagram promises
LEG_NEAR_FT = 50          # a road passing this close to the point starts a leg at its nearest point
LEG_MIN_FT = 25           # a piece shorter than this is not a leg
LEG_BEARING_FT = 60       # a leg's bearing is taken from its start to this far along it
LEG_SIDE_FT = 50          # a leg's side of the road is judged this far out along it (pick)
TRACK_TURN_DEG = 60       # a leg's track carries on into the next block of its street when it turns less than this there
SPLAY_MAX_FT = 100        # a divided street's half is straightened only when its bend toward the node is this short
SPLAY_MIN_DEG, SPLAY_MAX_DEG, SPLAY_PARALLEL_DEG = 15, 170, 15   # how far apart two halves leave a node, and how nearly parallel they then run
SIDE_MIN_FT = 5           # and counts as the right-hand side only when this far right of the point
SIDE_PARALLEL_DEG = 20    # two legs of one street within this of each other run side by side: the halves of a divided street
SKIP_LAYERS = ("FREEWAYS", "PAPER", "PSEUDO", "STREETS_PEDESTRI")   # grade-separated, unbuilt, or footways and stairs
BEAR = {"N": 0, "E": 90, "S": 180, "W": 270}
TURN = {"l": -90, "r": 90, "u": 180}
TOL_NAMED, TOL_UNNAMED, TOL_TURN = 60, 40, 50   # degrees between a recorded direction and a leg's bearing
CELL = 0.004


def load_network():
    """Surface centrelines from DataSF 3psu-pn9h as (name, [(lon, lat), ...], one-way) with a grid index over their boxes."""
    C = sfdata.fetch("3psu-pn9h", select=CENTERLINE_FIELDS, where="active='true'", floor=15000)
    lines, grid = [], collections.defaultdict(list)
    for r in C.rows:
        if not r.get("line") or (r.get("layer") or "").startswith(SKIP_LAYERS):
            continue
        g = r["line"] if isinstance(r["line"], dict) else json.loads(r["line"].replace("'", '"'))
        if g["type"] not in ("LineString", "MultiLineString"):
            continue
        for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]):
            pts = [(float(c[0]), float(c[1])) for c in ln]
            i = len(lines)
            lines.append((street(r.get("streetname")), pts, r.get("oneway") in ("F", "T")))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            for cx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
                for cy in range(int(min(ys) // CELL), int(max(ys) // CELL) + 1):
                    grid[(cx, cy)].append(i)
    return lines, grid, C.tag


def _clip(a, b):
    """Liang-Barsky: the part of segment a-b inside the drawing box, or None."""
    t0, t1, dx, dy = 0.0, 1.0, b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] + BOX_X), (dx, BOX_X - a[0]), (-dy, a[1] + BOX_Y), (dy, BOX_Y - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


def _length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _bearing(pts):
    """Compass bearing from pts[0] to the point LEG_BEARING_FT along pts (x east, y south)."""
    left, (x, y) = LEG_BEARING_FT, pts[0]
    for i in range(len(pts) - 1):
        d = math.dist(pts[i], pts[i + 1])
        if d >= left:
            f = left / d
            x, y = pts[i][0] + f * (pts[i + 1][0] - pts[i][0]), pts[i][1] + f * (pts[i + 1][1] - pts[i][1])
            break
        left -= d
        x, y = pts[i + 1]
    return math.degrees(math.atan2(x - pts[0][0], pts[0][1] - y)) % 360


def _unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d) if d else None


def _angle(u, v):
    return math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))


def _straighten(cand):
    """Carry each half of a divided street straight on to its junction. cand: [[name, [(x, y), ...], one-way], ...] in
    feet, changed in place. The centreline file ends both halves of a divided street on one node, so each half bends
    toward the other over its last few dozen feet. Where two lines of one street share an end node, leave it
    SPLAY_MIN_DEG to SPLAY_MAX_DEG apart and then run within SPLAY_PARALLEL_DEG of parallel, the end of each whose first
    piece is no longer than SPLAY_MAX_FT moves to the foot of the node on the line of its second piece."""
    ends = collections.defaultdict(list)   # (street, node) -> [(line, 0 for its first point or -1 for its last)]
    for i, (name, pts, _) in enumerate(cand):
        if name and len(pts) >= 3:
            for e in (0, -1):
                ends[(_base(name), round(pts[e][0], 1), round(pts[e][1], 1))].append((i, e))
    moves = []
    for group in ends.values():
        away = {}   # (line, end) -> (node, direction leaving it, direction of the piece after)
        for i, e in group:
            p = cand[i][1] if e == 0 else cand[i][1][::-1]
            d0, d1 = _unit(p[0], p[1]), _unit(p[1], p[2])
            if d0 and d1:
                away[(i, e)] = (p, d0, d1)
        for (i, e), (p, d0, d1) in away.items():
            if math.dist(p[0], p[1]) > SPLAY_MAX_FT:
                continue
            if any(o != (i, e) and SPLAY_MIN_DEG <= _angle(d0, q0) <= SPLAY_MAX_DEG and _angle(d1, q1) <= SPLAY_PARALLEL_DEG
                   for o, (_, q0, q1) in away.items()):
                t = (p[0][0] - p[1][0]) * d1[0] + (p[0][1] - p[1][1]) * d1[1]
                moves.append((i, e, (p[1][0] + t * d1[0], p[1][1] + t * d1[1])))
    for i, e, pt in moves:
        cand[i][1][e] = pt


def _carry_on(half, name, roads):
    """A leg's centreline carried on past its block: the city's file ends each line at the next junction, so the track
    takes up the piece of the same street that starts where it ends and turns least (under TRACK_TURN_DEG), and so on to
    the edge of the drawing. A street that ends there (a T) ends the track."""
    half, used = list(half), set()
    while True:
        end, d, best = half[-1], _unit(half[-2], half[-1]), None
        for i, (n, pts, _) in enumerate(roads):
            if i in used or _base(n) != _base(name) or not d:
                continue
            for p in (pts, pts[::-1]):
                u = _unit(p[0], p[1])
                if math.dist(p[0], end) < 6 and u and (best is None or _angle(d, u) < best[0]):
                    best = (_angle(d, u), i, p)
        if best is None or best[0] > TRACK_TURN_DEG:
            return half
        used.add(best[1])
        half += best[2][1:]


def geometry(lon, lat, net):
    """The streets around one crash point in feet from it (x east, y south), and its legs: the roads that pass within
    LEG_NEAR_FT, each split at its point nearest the crash into the pieces running away from it.
    Returns ({"r": [[name, [[x, y], ...]], ...], "l": [[x, y, bearing, name], ...], "k": [[one-way, [[x, y], ...]], ...]},
    None) or (None, reason). k[i] is leg i's track: its centreline from the leg's start outward, and 1 when it is one-way."""
    lines, grid = net
    cx, cy = int(lon // CELL), int(lat // CELL)
    seen, cand, roads, legs, tracks = set(), [], [], [], []
    for gx in (cx - 1, cx, cx + 1):
        for gy in (cy - 1, cy, cy + 1):
            for i in grid.get((gx, gy), ()):
                if i in seen:
                    continue
                seen.add(i)
                name, pts, *one = lines[i]
                cand.append([name, [((x - lon) * FT_LON, (lat - y) * FT_LAT) for x, y in pts], bool(one and one[0])])
    _straighten(cand)
    for name, loc, one in cand:
        piece = []
        for a, b in zip(loc, loc[1:]):   # clip to the box, keeping each run of inside segments as one piece
            c = _clip(a, b)
            if c is None:
                if len(piece) > 1:
                    roads.append((name, piece, one))
                piece = []
                continue
            if piece and math.dist(piece[-1], c[0]) < 1e-6:
                piece.append(c[1])
            else:
                if len(piece) > 1:
                    roads.append((name, piece, one))
                piece = [c[0], c[1]]
        if len(piece) > 1:
            roads.append((name, piece, one))
    roads = [r for r in roads if _length(r[1]) >= 1]   # a sliver clipped at the box edge would draw as a blob
    if not roads:
        return None, "no street in the drawing"
    for name, pts, one in roads:
        best = None   # (distance, segment index, point)
        for k in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0 if L == 0 else max(0, min(1, -(ax * dx + ay * dy) / L))
            q = (ax + t * dx, ay + t * dy)
            d = math.hypot(*q)
            if best is None or d < best[0]:
                best = (d, k, q)
        if best[0] > LEG_NEAR_FT:
            continue
        d, k, q = best
        for half in ([q] + pts[k + 1:], [q] + pts[k::-1]):
            if _length(half) >= LEG_MIN_FT:
                legs.append((round(q[0], 1), round(q[1], 1), round(_bearing(half), 1), name))
                half = _carry_on(half, name, roads)
                tracks.append([1 if one else 0, [[round(x, 1), round(y, 1)] for x, y in half[:1]] + [[round(x), round(y)] for x, y in half[1:]]])
    if not legs:
        return None, "no street within %d ft of the point" % LEG_NEAR_FT
    return {"r": [[n, [[round(x), round(y)] for x, y in p]] for n, p, _ in roads], "l": [list(l) for l in legs], "k": tracks}, None


def _base(name):
    return re.sub(r"\s+(St|Ave|Blvd|Dr|Rd|Pl|Ter|Way|Ln|Ct|Hwy|Aly|Plz|Cir)$", "", name or "")


def _diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def _right(lg, coming_in):
    """How far (ft) a leg lies to the right of a party on it, through the point: judged LEG_SIDE_FT out along the leg,
    against the leg's own heading (toward the point when coming_in, else away from it)."""
    b = math.radians(lg[2])
    h = b + math.pi if coming_in else b
    x, y = lg[0] + LEG_SIDE_FT * math.sin(b), lg[1] - LEG_SIDE_FT * math.cos(b)
    return x * math.cos(h) + y * math.sin(h)   # (cos, sin) is the right-hand normal of a heading, in x east, y south


def _own_side(legs, lg, coming_in):
    """The leg a driver on `lg` takes: `lg`, or the half of the same street running beside it (within SIDE_PARALLEL_DEG)
    that lies further to the driver's right by more than SIDE_MIN_FT."""
    best = max((x for x in legs if _base(x[3]) == _base(lg[3]) and _diff(x[2], lg[2]) <= SIDE_PARALLEL_DEG),
               key=lambda x: _right(x, coming_in))
    return best if _right(best, coming_in) - _right(lg, coming_in) > SIDE_MIN_FT else lg


def pick(legs, outward, name, tol, coming_in):
    """The leg whose outward bearing is nearest `outward` within tol degrees, and whose street is `name` when a name is
    given. A divided street draws each direction as its own centreline, so a leg's side is judged LEG_SIDE_FT out along
    it: when the legs that fit include one lying to the right of the party's heading, only those count, and of two
    halves running side by side the one further right wins, so a driver takes their own side (Lombard St at Laguna and
    at Steiner; Crossover Dr, where the point sits on one half)."""
    fits = []
    for lg in legs:
        dd = _diff(lg[2], outward)
        if dd > tol or (name and _base(lg[3]) != _base(name)):
            continue
        fits.append((_right(lg, coming_in) > SIDE_MIN_FT, dd, lg))
    if any(f[0] for f in fits):
        fits = [f for f in fits if f[0]]
    return _own_side([f[2] for f in fits], min(fits, key=lambda f: f[1])[2], coming_in) if fits else None


def turn_pair(legs, h_in, h_out, kind, name, on_exit):
    """The (approach leg, exit leg) pair for one reading of a turn, or None. The approach leg runs opposite the heading
    in and the exit leg along the heading out, each within TOL_TURN; the angle between the leg headings must itself be
    the turn (a left turn swings 45 to 135 degrees anticlockwise, a right turn as far clockwise, a U-turn at least 135),
    so a diagonal grid can't pass a straight run or the opposite turn off as this one; and the record's street is the
    leg its direction belongs to (the exit leg when on_exit, else the approach leg). On a divided street the halves on
    the driver's right come first (the approach half right of the heading in, the exit half right of the heading out);
    after that, least total bearing error wins."""
    best = None
    for a in legs:
        da = _diff(a[2], (h_in + 180) % 360)
        if da > TOL_TURN:
            continue
        for b in legs:
            db = _diff(b[2], h_out % 360)
            if db > TOL_TURN or (a is b and kind != "u"):
                continue
            swing = (b[2] - (a[2] + 180) + 180) % 360 - 180   # heading out minus heading in, clockwise positive
            if (abs(swing) < 135) if kind == "u" else _diff(swing, TURN[kind]) > 45:
                continue
            if name and _base(name) != _base((b if on_exit else a)[3]):
                continue
            score = ((_right(a, True) <= SIDE_MIN_FT) + (_right(b, False) <= SIDE_MIN_FT), da + db)
            if best is None or score < best[0]:
                best = (score, a, b)
    if not best:
        return None
    a, b = _own_side(legs, best[1], True), _own_side(legs, best[2], False)
    return (a, b) if kind == "u" or a is not b else best[1:]


def place_party(q, p, geo, tally):
    """Put one diagram party on the real legs. Adds to q: "a" [x, y, bearing, leg number] the leg it comes in on, or "e"
    the leg it leaves on; "t" {"a", "b", "u"} for a turn drawn as a curve (u: both readings fit, so it is drawn dashed);
    "fb" 1 when nothing matched and it keeps the compass placement. The leg number indexes geo["l"] and geo["k"].
    Returns "both" for an unresolved turn, else None."""
    if not q["d"] or q["v"] == "walk":
        return None   # no direction: listed below the drawing; walkers stay beside the ring, the record names no crosswalk
    h, name = BEAR[q["d"]], street(p.get("street_of_travel"))
    legs = geo["l"]

    def ref(lg):
        return lg[:3] + [next(i for i, x in enumerate(legs) if x is lg)]
    if name and not any(_base(lg[3]) == _base(name) for lg in legs):
        # The record puts the party on a street that isn't at this point (another block, a ramp, a parking lot, or a
        # point placed off its street): drawing it on whatever street is here would contradict the card's text.
        q["fb"] = 1
        tally["party_street_not_drawn"] += 1
        return None
    tol = TOL_NAMED if name else TOL_UNNAMED
    if q["m"] in TURN:
        T, ok = TURN[q["m"]], []
        for h_in, h_out, on_exit in ((h, h + T, False), (h - T, h, True)):   # the direction is the approach, or the exit
            pair = turn_pair(legs, h_in, h_out, q["m"], name, on_exit)
            if pair:
                ok.append(pair)
        if len(ok) == 1 or (len(ok) == 2 and ok[0] == ok[1]):
            q["t"] = {"a": ref(ok[0][0]), "b": ref(ok[0][1])}
            tally["turn_one_reading"] += 1
            return None
        if len(ok) == 2:
            q["t"] = {"a": ref(ok[0][0]), "b": ref(ok[0][1]), "u": 1}
            tally["turn_both_readings"] += 1
            return "both"
        tally["turn_neither_reading"] += 1
    a = pick(legs, (h + 180) % 360, name, tol, True)
    if a:
        q["a"] = ref(a)
        tally["party_on_approach_leg"] += 1
        return None
    e = pick(legs, h, name, tol, False)
    if e:
        q["e"] = ref(e)
        tally["party_on_exit_leg"] += 1
        return None
    q["fb"] = 1
    tally["party_compass_fallback"] += 1
    return None


def an(w):
    m = re.match(r"(\d+)-", w)
    if m:
        n = m.group(1)
        return ("an " if n.startswith("8") or n in ("11", "18") else "a ") + w
    return ("an " if re.match(r"[aeiouAEIOU]|SUV|e-", w) else "a ") + w


def age_of(r, key="party_age"):
    try:
        a = int(float(r.get(key)))
    except (TypeError, ValueError):
        return None
    return a if 0 < a < 125 else None


def driverless(p):
    return (p.get("vehicle_autonomous") or "").startswith("Driverless")


def who(p):
    """A party as a noun phrase without its article: 'driver in an SUV', 'person walking', 'parked car'."""
    t, vt = p.get("party_type"), p.get("stwd_vehicle_type") or ""
    noun = VEH.get(vt, ("vehicle", "car"))[0]
    if t == "Pedestrian" or vt == "Pedestrian":
        return "person walking"
    if t == "Parked Vehicle":
        return "parked " + (noun if vt not in NONE else "vehicle")
    if driverless(p):
        return "driverless car"
    if vt == "Unknown Hit and Run":
        return "hit-and-run driver"
    if vt in ("Motorcycle", "Police Motorcycle"):
        return "motorcyclist" if vt == "Motorcycle" else "police motorcyclist"
    if VEH.get(vt, ("", ""))[1] in ("bike", "scooter", "moto"):
        return "person on " + an(noun)
    if t == "Driver":
        return "driver" + (" in " + an(noun) if vt not in NONE else "")
    return "person in " + an(noun) if vt not in NONE else "person"


def glyph(p):
    if p.get("party_type") == "Pedestrian":
        return "walk"
    return VEH.get(p.get("stwd_vehicle_type") or "", ("", "car"))[1] or "car"


def flags(p):
    """What the record says about alcohol, drugs, fatigue and phone use for one party, as short phrases."""
    out = []
    sob = p.get("party_sobriety") or ""
    if sob.startswith("Had Been Drinking"):
        out.append({"Had Been Drinking, Under Influence": "had been drinking, under the influence",
                    "Had Been Drinking, Not Under Influence": "had been drinking, not under the influence"}.get(sob, "had been drinking"))
    drug = p.get("party_drug_physical") or ""
    if "Cannabis" in sob or "Cannabis" in drug:   # the 2018-2024 rows carry it in party_drug_physical
        out.append("suspected cannabis use")
    # A few 2018 rows carry the drug and physical values in party_sobriety.
    for v in {drug, sob}:
        if v == "Under Drug Influence":
            out.append("under the influence of drugs")
        elif v == "Impairment - Physical":
            out.append("physically impaired")
        elif v == "Sleepy/Fatigued":
            out.append("sleepy or fatigued")
    for k in ("sp_info_1", "sp_info_2"):
        v = p.get(k) or ""
        if v.lower().startswith("cell phone") and "in use" in v.lower() and "not" not in v.lower():
            out.append("using a phone, " + ("handheld" if "Handheld" in v else "hands-free"))
    return out


def ride(p):
    for k in ("sp_info_1", "sp_info_2"):
        v = p.get(k) or ""
        if v.startswith("Vehicle for Hire") or v.startswith("TNC"):
            return "ride-hail or taxi, " + ("with a passenger" if "WITH" in v else "no passenger")
    return ""


def dedupe(rows, key, cases, what):
    """Rows keyed by key(); a repeat must be identical, and off the map when `cases` names the map's crashes (pass an
    empty set to allow an identical repeat anywhere, as the every-crash build in street-safety-cards.py does)."""
    out, seen = [], {}
    for r in rows:
        k = key(r)
        if k in seen:
            assert k[0] not in cases, f"duplicate {what} {k} on the map"
            assert seen[k] == r, f"duplicate {what} {k} differs"
            continue
        seen[k] = r
        out.append(r)
    return out


def index_rows(X, P, V, on_map):
    """The three tables' rows by case: ({case: crash row}, {case: [party rows]}, {case: [victim rows]})."""
    crash = {r["case_id_pkey"]: r for r in dedupe(X, lambda r: (r["case_id_pkey"],), on_map, "crash row")}
    parties, victims = collections.defaultdict(list), collections.defaultdict(list)
    for r in dedupe(P, lambda r: (r["case_id_pkey"], r.get("party_number_ckey")), on_map, "party"):
        parties[r["case_id_pkey"]].append(r)
    for r in dedupe(V, lambda r: (r["case_id_pkey"], r.get("victim_id")), on_map, "victim"):
        victims[r["case_id_pkey"]].append(r)
    return crash, parties, victims


def build(cases, hin_years, rows=None, net=None):
    """cases: {case id: (lon, lat)}. hin_years: function (lon, lat) -> sorted list of HIN editions the spot is on.
    rows: (crash, parties, victims) from index_rows, and tags {"crashes", "parties", "victims"}, for a caller that
    has read the tables itself; by default the 2022-on queries above. net: load_network()'s result, likewise.
    Returns ({case: card}, stats). A case missing from the crash table gets no card; the caller decides if that's allowed."""
    if rows is None:
        X = sfdata.fetch("ubvf-ztfx", select=CRASH_FIELDS, where=SINCE, floor=8000)
        P = sfdata.fetch("8gtc-pjc6", select=PARTY_FIELDS, where=SINCE, floor=15000)
        V = sfdata.fetch("nwes-mmgh", select=VICTIM_FIELDS, where=SINCE, floor=10000)
        (crash, parties, victims), tags = index_rows(X.rows, P.rows, V.rows, cases), {"crashes": X.tag, "parties": P.tag, "victims": V.tag}
    else:
        (crash, parties, victims), tags = rows
    missing = sorted(c for c in cases if c not in crash)
    lines, grid, ctag = net or load_network()
    tally = collections.Counter()

    cards, cover = {}, collections.Counter()
    for case in sorted(c for c in cases if c in crash):
        c, ps = crash[case], sorted(parties.get(case, []), key=lambda p: int(p.get("party_number_ckey") or 0))
        assert ps, f"crash {case} has no parties"
        vs = sorted(victims.get(case, []), key=lambda v: (-INJ.get(v.get("victim_degree_of_injury"), ("", 0))[1], v.get("victim_id") or ""))
        pn = {p.get("party_number_ckey") for p in ps}
        for v in vs:
            assert v.get("party_number_ckey") in pn, f"victim {v.get('victim_id')} names party {v.get('party_number_ckey')} not in crash {case}"
        geo, why = geometry(*cases[case], (lines, grid))
        tally["crash_real_streets" if geo else "crash_generic: " + why] += 1
        cards[case] = card(c, ps, vs, hin_years(*cases[case]), geo, tally)
        place = c.get("intersection") or ""
        try:
            dist = float(c.get("distance") or 0)
        except ValueError:
            dist = 0
        cover["parties"] += len(ps)
        cover["dir"] += sum(1 for p in ps if p.get("dir_of_travel") in DIRS)
        cover["move"] += sum(1 for p in ps if p.get("move_pre_acc") not in NONE)
        cover["move_other"] += sum(1 for p in ps if p.get("move_pre_acc") == "Other")
        cover["vehicle"] += sum(1 for p in ps if p.get("stwd_vehicle_type") not in NONE)
        cover["crash_with_fault"] += any(p.get("at_fault") == "Yes" for p in ps)
        cover["age"] += sum(1 for p in ps if age_of(p))
        cover["lighting"] += c.get("lighting") not in NONE
        cover["collision_type"] += c.get("type_of_collision") not in NONE
        cover["at_intersection_no_offset"] += place.startswith("Intersection <= 20") and not dist
        cover["placed_at_offset"] += bool(dist) and c.get("direction") in DIRS
        cover["geocoded_midblock"] += place.startswith("Midblock")
        cover["turning_parties"] += sum(1 for p in ps if MOVE.get(p.get("move_pre_acc"), ("s", ""))[0] in "lru")
    stats = {"cases": len(cases), "joined": len(cards), "not_in_crash_table": missing, "coverage": dict(sorted(cover.items())),
             "diagram": dict(sorted(tally.items())),
             "tags": dict(tags, centerlines=ctag)}
    return cards, stats


def card(c, ps, vs, hin, geo=None, tally=None):
    case = c["case_id_pkey"]
    t = dt.datetime.fromisoformat(c["collision_datetime"][:19])
    tm = (c.get("collision_time") or "")[:5]
    hour = int(tm[:2]) if re.match(r"\d\d:\d\d", tm) else None
    head = [t.strftime("%A"), t.strftime("%b ") + str(t.day) + t.strftime(", %Y")]
    if hour is not None and tm != "00:00":   # midnight sharp is often a blank time
        head.append(str(hour % 12 or 12) + ":" + tm[3:5] + (" am" if hour < 12 else " pm"))

    by_num = {p.get("party_number_ckey"): p for p in ps}
    fault = [p for p in ps if p.get("at_fault") == "Yes"]
    hurt = collections.defaultdict(int)   # party number -> worst injury rank among its people
    for v in vs:
        hurt[v.get("party_number_ckey")] = max(hurt[v.get("party_number_ckey")], INJ.get(v.get("victim_degree_of_injury"), ("", 0))[1])
    minor = {}   # party number -> "v" (Other Visible Injury) or "p" (Complaint of Pain), its worst level below severe
    for v in vs:
        lv = {"Other Visible Injury": "v", "Complaint of Pain": "p"}.get(v.get("victim_degree_of_injury"))
        if lv and minor.get(v.get("party_number_ckey")) != "v":
            minor[v.get("party_number_ckey")] = lv
    nouns = collections.Counter(who(p) for p in ps)

    def name(p):
        """The party's short name, with its diagram number when another party has the same name."""
        w = who(p)
        return w + (" (%s)" % p.get("party_number_ckey") if nouns[w] > 1 else "")

    def own(p, v):
        """True when victim row v is party p's own person (not a passenger in it)."""
        role = v.get("victim_role") or ""
        return bool(p) and ((role == "Pedestrian" and p.get("party_type") == "Pedestrian") or (role == "Driver" and p.get("party_type") == "Driver")
                            or (role == "Bicyclist" and glyph(p) in ("bike", "scooter", "moto"))
                            # a scooter, board or moped rider is often filed as role "Other" on a party of type "Other"
                            or (role == "Other" and p.get("party_type") == "Other"))
    vage = {}   # party number -> its own hurt person's age in the victims table
    for v in vs:
        p = by_num.get(v.get("party_number_ckey"))
        if own(p, v) and age_of(v, "victim_age"):
            vage[v.get("party_number_ckey")] = age_of(v, "victim_age")

    walkers = [p for p in ps if p.get("party_type") == "Pedestrian"]
    first_walker = walkers[0] if walkers else None

    def phrase(p, article=True):
        a = vage.get(p.get("party_number_ckey")) or age_of(p)
        dirn, mv = p.get("dir_of_travel"), p.get("move_pre_acc")
        num = " (%s)" % p.get("party_number_ckey") if nouns[who(p)] > 1 else ""
        if p.get("party_type") == "Pedestrian":
            w = (f"{a}-year-old " if a else "") + "person walking" + (" " + dirn.lower() if dirn in DIRS else "") + num
            act = PED.get(c.get("ped_action")) if p is first_walker else None   # the form records one action, for the first walker
            return (an(w) if article else w) + (", " + act if act else "")
        w = who(p)
        if a and p.get("party_type") != "Parked Vehicle":
            w = f"{a}-year-old {w}"
        out = (an(w) if article else w) + num
        if p.get("party_type") == "Parked Vehicle":
            return out
        st = street(p.get("street_of_travel"))
        kind, words = MOVE.get(mv, ("s", "")) if mv not in NONE else ("s", "")
        if kind in "lru":   # a turn: the direction is the record's, without saying before or after the turn
            go = words + ("; recorded direction " + dirn.lower() if dirn in DIRS else "") + (" on " + st if st else "")
            return out + ", " + go
        go = ("going " + dirn.lower() + (" on " + st if st else "")) if dirn in DIRS else ("on " + st if st else "")
        if kind == "x":
            go = words + (", facing " + dirn.lower() if dirn in DIRS else "") + (" on " + st if st else "")
            words = ""
        return out + "".join(", " + b for b in (go, words) if b)

    movers = [p for p in ps if p.get("party_type") != "Pedestrian"]
    ctype = c.get("type_of_collision")
    pcf = c.get("vz_pcf_description") if c.get("vz_pcf_description") not in NONE else ""
    story = "" if fault else "The officer's report marks no party at fault."

    def people(p):
        """Party p's people and how badly each was hurt, for `pi`: its own person first, then anyone else filed under it."""
        n, mine, others = p.get("party_number_ckey"), None, collections.defaultdict(list)
        for v in vs:
            if v.get("party_number_ckey") != n:
                continue
            lv = LEVEL.get(v.get("victim_degree_of_injury"))
            if own(p, v) and mine is None:
                mine = lv or "n"   # a "No Injury" row (2014 to 2016) is the record saying so
                continue
            if lv:
                others[(lv, v.get("victim_role") or "")].append(age_of(v, "victim_age"))
        if mine is None and p.get("party_type") != "Parked Vehicle" and not driverless(p):
            mine = "n"
        rest = []   # the worst hurt first; people of one role and level share an entry, so five passengers are one phrase
        for (lv, role), ages in sorted(others.items(), key=lambda kv: ("ksvp".index(kv[0][0]), kv[0][1])):
            one, many = {"Passenger": ("Passenger", "passengers"), "Pedestrian": ("Person walking", "people walking"),
                         "Bicyclist": ("Person on a bike", "people on bikes"), "Driver": ("Driver", "drivers")}.get(role, ("Person", "people"))
            known = sorted(a for a in ages if a)
            if len(ages) == 1:
                rest.append([lv, one + (f", age {known[0]}" if known else "")])
            else:
                listed = (", ".join(map(str, known[:-1])) + " and " + str(known[-1])) if len(known) > 1 else ""
                rest.append([lv, f"{len(ages)} {many}" + (f", ages {listed}" if len(known) == len(ages) else "")])
        return ([[mine]] if mine else []) + rest

    det = []
    cond = [LIGHT.get(c.get("lighting"), c.get("lighting"))] if c.get("lighting") not in NONE else []
    if c.get("weather_1") not in NONE and c["weather_1"] != "Other":
        cond.append(c["weather_1"].lower())
    if c.get("road_surface") not in NONE:
        cond.append(c["road_surface"].lower() + " road")
    for k in ("road_cond_1", "road_cond_2"):
        if c.get(k) not in NONE and c[k] not in ("No Unusual Condition", "Other"):
            cond.append(c[k].lower())
    if cond:
        det.append(["Conditions", ", ".join(cond)])
    if c.get("control_device") in CONTROL:
        det.append(["Traffic control", CONTROL[c["control_device"]]])
    pr, sr = street(c.get("primary_rd")), street(c.get("secondary_rd"))
    cls = c.get("intersection") or ""
    try:
        ft = int(float(c.get("distance") or 0))
    except ValueError:
        ft = 0
    off = f"{ft:,} ft {c['direction'].lower()} of {sr}" if ft and c.get("direction") in DIRS and sr else ""
    if cls.startswith("Intersection <= 20"):
        both = f" of {pr} and {sr}" if pr and sr and pr != sr else f" on {pr or sr}" if pr or sr else ""
        place = "At the intersection" + both + (f", {off}" if off else "")
    else:
        lead = "Midblock" if cls.startswith("Midblock") and ft > 50 else "On the block"
        place = lead + (f" on {pr}" if pr else "") + (f", {off}" if off else (f", near {sr}" if sr else ""))
    det.append(["Where", place])
    kind = {"Vehicle/Pedestrian": "Vehicle and pedestrian"}.get(ctype, ctype) if ctype not in NONE and ctype != "Other" else ""
    with_ = MVIW.get(c.get("mviw"))
    if c.get("mviw") == "Parked Motor Vehicle" and any(p.get("party_type") == "Parked Vehicle" or p.get("move_pre_acc") == "Parked" for p in ps):
        with_ = None   # the parked vehicle is a party with its own line
    if c.get("mviw") == "Non-Collision":   # the record's word: nothing was struck (a fall, an overturned vehicle)
        # Said only where the collision type agrees or says nothing; 160 rows pair it with a broadside or the like.
        kind = "Overturned, no collision" if kind == "Overturned" else kind or "No collision"
    elif with_ and not (kind == "Hit Object" and with_ == "an object"):
        kind = (kind + ", involving " + with_) if kind else "Involving " + with_
    if kind:
        det.append(["Collision type", kind])
    if pcf:
        det.append(["Primary factor", pcf + (" (" + c["vz_pcf_code"] + ")" if c.get("vz_pcf_code") not in NONE else "")])
    if any(p.get("stwd_vehicle_type") == "Unknown Hit and Run" for p in ps):
        det.append(["Hit-and-run", "Yes, the vehicle was not identified"])
    sub = [name(p) + ": " + "; ".join(flags(p)) for p in ps if flags(p)]
    if sub:
        det.append(["Alcohol, drugs, phone, impairment", " · ".join(x[0].upper() + x[1:] for x in sub)])
    rh = [name(p) + ": " + ride(p) for p in ps if ride(p)]
    if rh:
        det.append(["Ride-hail", " · ".join(x[0].upper() + x[1:] for x in rh)])
    av = [name(p) for p in ps if driverless(p)]
    if av:
        det.append(["Autonomous vehicle", ", ".join(x[0].upper() + x[1:] for x in av) + ": driverless, no driver override possible"])
    det.append(["High Injury Network", ("On the " + (", ".join(hin[:-1]) + " and " if len(hin) > 1 else "") + hin[-1] + " network" + ("s" if len(hin) > 1 else "")) if hin else "Not on it"])
    det.append(["Point of impact", "Not in the public record"])

    rows, g, pi = [], [], []
    tally = tally if tally is not None else collections.Counter()
    for p in ps:
        n = p.get("party_number_ckey")
        r = phrase(p, article=False)
        r = r[0].upper() + r[1:]
        if p.get("at_fault") == "Yes":
            r += " · marked most at fault"
        mv = p.get("move_pre_acc")
        q = {"n": int(n or 0), "v": glyph(p), "d": DIRS.get(p.get("dir_of_travel"), ""),
             "m": "x" if p.get("party_type") == "Parked Vehicle" else MOVE.get(mv, ("s", ""))[0] if mv not in NONE else "s",
             "h": hurt.get(n, 0), "pk": 1 if p.get("party_type") == "Parked Vehicle" or mv == "Parked" else 0,
             "f": 1 if p.get("at_fault") == "Yes" else 0}
        if q["h"] == 1:
            q["hl"] = minor[n]   # the map's own colour for the two lower levels
        if geo and place_party(q, p, geo, tally) == "both":
            r += "; direction before or after the turn is unclear"
        rows.append(r)
        g.append(q)
        pi.append(people(p))
    axis = {"v": set(), "h": set()}
    for p in movers:
        st = street(p.get("street_of_travel"))
        dd = DIRS.get(p.get("dir_of_travel"))
        if st and dd and MOVE.get(p.get("move_pre_acc"), ("s", ""))[0] in ("s", "b", "x"):
            axis["v" if dd in "NS" else "h"].add(st)
    lab = {k: (next(iter(v)) if len(v) == 1 else "") for k, v in axis.items()}
    inter = cls.startswith("Intersection <= 20")
    if inter and pr and sr:
        for k, o in (("v", "h"), ("h", "v")):
            if lab[k] and not lab[o] and not axis[o]:
                lab[o] = sr if lab[k] == pr else pr if lab[k] == sr else ""
    if lab["v"] and lab["v"] == lab["h"]:
        lab = {"v": "", "h": ""}
    mid_axis = "h"
    if not inter:
        nv = sum(1 for p in movers if DIRS.get(p.get("dir_of_travel"), "") in ("N", "S"))
        nh = sum(1 for p in movers if DIRS.get(p.get("dir_of_travel"), "") in ("E", "W"))
        mid_axis = "v" if nv > nh else "h"
    return {"hd": " · ".join(head), "t": story, "dl": det, "pr": rows, "pi": pi,
            "g": dict({"x": 1 if inter else 0, "ax": mid_axis, "lv": lab["v"], "lh": lab["h"], "p": g}, **({"geo": geo} if geo else {})), "src": case}
