"""The street context of each injury crash as of its crash date: the rules that turn the source rows into one row of columns per crash.

    from street_fields import Context, augment, COLUMNS
    ctx = Context(sources)              # sources: {name: rows}, as street_sources.load_all() gives
    rows = augment(crash_rows, ctx)     # one dict per crash, keys COLUMNS, same count and order as crash_rows

Every field has a companion <field>_basis column saying how far the value can be trusted for the crash's own date:

  dated               the source records when the thing changed, and the value is the one in force on the crash date
  current_state_only  the source holds today's state only, so the value is today's, whatever the crash date
  definition_acs2022  (in_epc only) MTC's Equity Priority Community definition from ACS 2018-2022, applied to every
                      year: it describes the area, not the street, and is not dated
  not_applicable      (corner_type only) the crash is not coded at an intersection
  unknown             the value cannot be established: no join, an undated record that may or may not predate the
                      crash, or a code that is not a value (99 mph means freeway)

WHICH BLOCK A CRASH IS ON (street_block_join). Block fields (speed limit, street class, lanes, BCI traffic,
traffic calming, slow street) are read off the crash's block:
  segment          the crash row's own segment CNN (cnn_sgmt_fkey), when it has one
  node_primary_rd  no segment CNN: the blocks meeting at the crash's intersection CNN (cnn_intrsctn_fkey, matched to
                   f_node_cnn/t_node_cnn in 3psu-pn9h) whose street name is the report's primary road
  node_all         as above when no block there carries the primary road's name: every block meeting there
  none             neither CNN joins
When more than one block is read, a number takes the highest value among blocks that have one (speed, lanes), a
class the most major, BCI traffic the heaviest, and a presence flag is true if any block has it. The basis is the
least certain basis among the blocks that gave a value.

FIELD RULES, each named in pipeline/crash-augment/street/README.md with its source:
  posted_speed_limit_mph  3t7b-gebn speedlimit; 0 is the 25 mph default (the dataset's own summary); 99 marks a
                          freeway and is no limit. A block now at 20 mph with an install_date was 25 before that
                          date and 20 on or after it (SFMTA Board resolutions for the 20 mph program each say "from
                          25"), basis dated. Every other block carries today's value, basis current_state_only.
                          A block the speed layer does not list (a CNN split or renumbered since) takes the highest
                          limit of the same street's blocks at its two ends; posted_speed_limit_source says
                          "block" or "adjacent_block".
  street_class            3psu-pn9h classcode: 1 freeway, 2 major, 3 arterial, 4 collector, 5 residential, 6 ramp,
                          0 other.
  corner_type             crashes coded at an intersection only: the streets meeting at the intersection CNN, each
                          taking its most major block's class, the two most major named major-first, e.g.
                          arterial_x_residential; a node with one street is <class>_only.
  lanes, lanes_am, lanes_pm  SFMTA MTA.CTA_trafficlanes LANES_OP, LANES_AM, LANES_PM, raw. On two-way streets the
                          count appears to be one direction. 0 is kept as the layer gives it.
  bci_traffic_category    SFMTA Bike Comfort Index traffic_category_ft and _tf, the heavier direction: light,
                          medium or heavy.
  painted_safety_zone     vtn2-q8ky, a zone at the crash's intersection CNN installed on or before the crash date.
                          A midblock crash is false: the zones are corner treatments.
  speed_camera_corridor   d5uh-bk84. Each camera site is placed on the nearest block of its own street (within
                          400 ft); its corridor is that block, the next block of the same street at each end, and the
                          intersections of those blocks. A crash is in the corridor when its segment CNN is a corridor
                          block, or when it is coded at an intersection that is a corridor intersection. True when the
                          crash date is on or after the site's first day in the data.
  traffic_calming         abhw-ffzx on the crash's block: true when a Complete measure was installed on or before the
                          crash date; unknown when the block has a Complete measure with no install date (blank or
                          1900-01-01) or an Obsolete one, neither of which can be placed against the crash date;
                          false otherwise. traffic_calming_types lists the measures that made it true.
  slow_street             hkz3-itiu Implemented rows on the crash's block, installed on or before the crash date.
                          An undated row is unknown from the earliest install date in the dataset on, and false
                          before it. Removals are not recorded and the dataset was last edited 2024-01-18.
  signal_present          ybh5-27n2 traffic signals (type SIGNAL, SIGNAL (CONTRACTOR MAINTAINED), CALTRANS) at the
                          crash's intersection CNN for a crash coded at an intersection, or on its segment CNN for a
                          midblock crash. startyear before the crash year is true (dated); the crash year itself is
                          unknown; no usable startyear (0, 9999) is true, current_state_only. Removed signals are not
                          in the inventory.
  in_epc                  the crash point (tb_latitude, tb_longitude) in an MTC PBA 2050 Plus EPC tract (epc_2050p).
"""

import collections

ROAD_CLASS = {"1": "freeway", "2": "major", "3": "arterial", "4": "collector", "5": "residential", "6": "ramp",
              "0": "other"}
CLASS_RANK = {"freeway": 0, "major": 1, "arterial": 2, "collector": 3, "residential": 4, "ramp": 5, "other": 6}
TRAFFIC = {"Light Traffic": "light", "Medium Traffic": "medium", "Heavy Traffic": "heavy"}
TRAFFIC_RANK = {"light": 0, "medium": 1, "heavy": 2}
SIGNAL_TYPES = {"SIGNAL", "SIGNAL (CONTRACTOR MAINTAINED)", "CALTRANS", "CALTRANS (BY CONTRACTOR CONSORTIUM GLC)"}
BASIS_RANK = {"dated": 0, "definition_acs2022": 0, "current_state_only": 1, "unknown": 2}
# The site's point is matched to its own street by name, so the radius only guards against a bad point. Two sites
# (MTAF046 and MTAF047, "2300 16TH ST") sit 314 ft from 16th St and 42 ft from Bryant St (d5uh-bk84, read 2026-11-25).
CAMERA_SNAP_FT = 400
KSI = {"Fatal", "Injury (Severe)"}

FIELDS = ["in_epc", "posted_speed_limit_mph", "street_class", "corner_type", "lanes", "bci_traffic_category",
          "painted_safety_zone", "speed_camera_corridor", "traffic_calming", "slow_street", "signal_present"]
COLUMNS = (["case_id_pkey", "collision_date", "street_block_join", "street_block_cnns", "epc_tract"]
           + [c for f in FIELDS for c in ([f, f + "_basis"] + (["lanes_am", "lanes_pm"] if f == "lanes" else [])
                                         + (["posted_speed_limit_source"] if f == "posted_speed_limit_mph" else [])
                                         + (["traffic_calming_types"] if f == "traffic_calming" else []))])


def cnn(v):
    """A CNN as a plain digit string: '26132000.0' and 26132000 both give '26132000'."""
    if v is None or v == "":
        return None
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return None


def day(v):
    """The ISO date of a Socrata date string or an epoch-milliseconds number, or None."""
    if v is None or v == "":
        return None
    s = str(v)
    if s.isdigit() and len(s) >= 11:
        import datetime as dt
        return dt.datetime.fromtimestamp(int(s) / 1000, dt.timezone.utc).date().isoformat()
    return s[:10] if len(s) >= 10 and s[4] == "-" else None


def street_key(s):
    """A street name for matching: upper case, leading zeros off numbered streets, no spaces, so "07TH ST" and
    "7TH ST" match, and so do "BAY SHORE BLVD" and "BAYSHORE BLVD"."""
    return "".join(t.lstrip("0") or t for t in str(s or "").upper().split())


def worst(bases):
    return max(bases, key=lambda b: BASIS_RANK.get(b, 2)) if bases else "unknown"


def any_flag(parts):
    """Combine (value, basis) presence flags: true if any is true (the most certain true), else unknown if any is
    unknown, else false with the least certain basis."""
    trues = [b for v, b in parts if v is True]
    if trues:
        return True, min(trues, key=lambda b: BASIS_RANK.get(b, 2))
    if not parts or any(v is None for v, b in parts):
        return None, "unknown"
    return False, worst([b for v, b in parts])


class Context(object):
    """Indexes over every source, built once."""

    def __init__(self, src):
        self.seg, self.node_segs = {}, collections.defaultdict(list)
        for r in src["streets"]:
            c = cnn(r.get("cnn"))
            if c is None:
                continue
            f, t = cnn(r.get("f_node_cnn")), cnn(r.get("t_node_cnn"))
            self.seg[c] = {"street": street_key(r.get("streetname")), "cls": ROAD_CLASS.get(r.get("classcode")),
                           "f": f, "t": t, "active": r.get("active") in (True, "true"),
                           "lines": _lines(r.get("line"))}
            for n in (f, t):
                if n:
                    self.node_segs[n].append(c)
        for n in self.node_segs:
            self.node_segs[n].sort()

        self.speed = collections.defaultdict(list)
        for r in src["speed_limits"]:
            c = cnn(r.get("cnn"))
            if c and c != "0":
                self.speed[c].append((r.get("speedlimit"), day(r.get("install_date"))))

        self.lanes = {}
        for f in src["lanes"]:
            a = f["attributes"]
            c = cnn(a.get("CNN"))
            if c is None:
                continue
            v = (a.get("LANES_OP"), a.get("LANES_AM"), a.get("LANES_PM"))
            if c not in self.lanes or (v[0] or 0) > (self.lanes[c][0] or 0):
                self.lanes[c] = v

        self.bci = {}
        for f in src["bci"]:
            a = f["attributes"]
            c = cnn(a.get("cnn_sgmt_pkey"))
            cats = [TRAFFIC.get(a.get(k)) for k in ("traffic_category_ft", "traffic_category_tf")]
            cats = [x for x in cats if x]
            if c and cats:
                self.bci[c] = max(cats, key=TRAFFIC_RANK.get)

        self.psz = collections.defaultdict(list)
        for r in src["safety_zones"]:
            c = cnn(r.get("cnn"))
            if c:
                self.psz[c].append(day(r.get("install_da")))

        self.calming = collections.defaultdict(list)
        for r in src["traffic_calming"]:
            c = cnn(r.get("cnn"))
            d = day(r.get("install_datetime"))
            if d and d < "1950-01-01":   # 1900-01-01 is the dataset's placeholder for no date
                d = None
            if c:
                self.calming[c].append((d, r.get("current_status"), r.get("tc_measure")))

        self.slow = collections.defaultdict(list)
        dated = []
        for r in src["slow_streets"]:
            if r.get("status") != "Implemented":
                continue
            c = cnn(r.get("cnn"))
            d = day(r.get("install_date"))
            if d and d < "2000-01-01":   # 1899 dates are placeholders
                d = None
            if d:
                dated.append(d)
            if c:
                self.slow[c].append(d)
        self.slow_start = min(dated) if dated else None

        self.signals = collections.defaultdict(list)
        for r in src["signals"]:
            if r.get("type") not in SIGNAL_TYPES:
                continue
            c = cnn(r.get("cnn"))
            try:
                y = int(r.get("startyear"))
            except (TypeError, ValueError):
                y = None
            if y is not None and not 1900 <= y <= 2100:
                y = None
            if c:
                self.signals[c].append(y)

        self.cameras, self.camera_unplaced = self._place_cameras(src["cameras"])

        from street_geo import TractIndex
        self.epc_flag = {}
        tracts = []
        for f in src["epc"]:
            a = f["attributes"]
            self.epc_flag[a["tract_geoid"]] = int(a.get("epc_2050p") or 0) == 1
            tracts.append((a["tract_geoid"], (f.get("geometry") or {}).get("rings") or []))
        self.tracts = TractIndex([t for t in tracts if t[1]])

    # -- cameras --
    def _place_cameras(self, rows):
        from street_geo import feet_to_line
        first, where = {}, {}
        for r in rows:
            s = r.get("site_id")
            d = day(r.get("date"))
            if not s or not d:
                continue
            if s not in first or d < first[s]:
                first[s] = d
            if s not in where and r.get("point") and r.get("location"):
                where[s] = (r["location"], r["point"]["coordinates"])
        by_street = collections.defaultdict(list)
        for c, s in self.seg.items():
            if s["active"]:
                by_street[s["street"]].append(c)
        sites, unplaced = [], []
        for s in sorted(first):
            if s not in where:
                unplaced.append(s)
                continue
            loc, (lon, lat) = where[s]
            # "WB 2999 MARKET ST": direction, address number, street.
            parts = str(loc).upper().split()
            while parts and (parts[0] in ("NB", "SB", "EB", "WB") or parts[0].isdigit()):
                parts = parts[1:]
            street = street_key(" ".join(parts))
            best = None
            for c in by_street.get(street, ()):
                d = min((feet_to_line(lon, lat, ln) for ln in self.seg[c]["lines"]), default=float("inf"))
                if best is None or (d, c) < best:
                    best = (d, c)
            if best is None or best[0] > CAMERA_SNAP_FT:
                unplaced.append(s)
                continue
            home = best[1]
            segs = {home}
            for n in (self.seg[home]["f"], self.seg[home]["t"]):
                for c in self.node_segs.get(n, ()):
                    if self.seg[c]["street"] == street and self.seg[c]["active"]:
                        segs.add(c)
            nodes = {self.seg[c][k] for c in segs for k in ("f", "t") if self.seg[c][k]}
            sites.append({"site": s, "start": first[s], "street": street, "home": home, "snap_ft": round(best[0]),
                          "segs": segs, "nodes": nodes})
        return sites, unplaced

    # -- the crash's blocks --
    def blocks(self, crash):
        seg, node = cnn(crash.get("cnn_sgmt_fkey")), cnn(crash.get("cnn_intrsctn_fkey"))
        if seg:
            return [seg], "segment"
        if node and node in self.node_segs:
            touching = self.at_node(node)
            primary = [c for c in touching if self.seg[c]["street"] == street_key(crash.get("primary_rd"))]
            return (primary, "node_primary_rd") if primary else (touching, "node_all")
        return [], "none"

    def at_node(self, node):
        """The blocks meeting at an intersection: active ones (all, if none is active), and surface streets only
        when any meet there, since freeway centerlines (Hwy 1, the Central Freeway) share nodes with the streets
        under them and the crash table holds surface crashes."""
        segs = [c for c in self.node_segs.get(node, ()) if self.seg[c]["active"]] or list(self.node_segs.get(node, ()))
        return [c for c in segs if self.seg[c]["cls"] not in ("freeway", "ramp")] or segs

    def speed_neighbours(self, seg):
        """Speed-limit rows of the same street's blocks sharing an end node with `seg`, for a block the speed layer
        does not list (its CNN split or renumbered since)."""
        s = self.seg.get(seg)
        if not s:
            return []
        rows = []
        for n in (s["f"], s["t"]):
            for c in self.node_segs.get(n, ()):
                if c != seg and self.seg[c]["street"] == s["street"] and c in self.speed:
                    rows.append(c)
        return sorted(set(rows))


def _lines(geom):
    from street_geo import line_coords
    return line_coords(geom)


# ---- per-field rules ---------------------------------------------------------------------------------------------

def speed_on_block(rows, date):
    """(mph, basis) for one block's speed-limit rows on a date."""
    best = None
    for sl, installed in rows:
        if sl in (None, "", "99"):
            v = (None, "unknown")
        elif sl == "0":
            v = (25, "current_state_only")
        elif sl == "20" and installed:
            v = (25 if date < installed else 20, "dated")
        else:
            try:
                v = (int(sl), "current_state_only")
            except ValueError:
                v = (None, "unknown")
        if best is None or (v[0] or -1) > (best[0] or -1):
            best = v
    return best or (None, "unknown")


def highest(parts, rank=None):
    """The highest (or, with rank, the most major) value among (value, basis) parts that have one."""
    got = [(v, b) for v, b in parts if v is not None]
    if not got:
        return None, "unknown"
    key = (lambda p: rank[p[0]]) if rank else (lambda p: -p[0])
    v = min(got, key=key)[0]
    return v, worst([b for x, b in got])


def corner_type(ctx, node):
    if not node or node not in ctx.node_segs:
        return None, "unknown"
    segs = ctx.at_node(node)
    by_street = {}
    for c in segs:
        s = ctx.seg[c]
        cls = s["cls"] or "other"
        if s["street"] not in by_street or CLASS_RANK[cls] < CLASS_RANK[by_street[s["street"]]]:
            by_street[s["street"]] = cls
    classes = sorted(by_street.values(), key=CLASS_RANK.get)
    # (freeway and ramp blocks are already left out by at_node() wherever a surface street meets the node)
    if not classes:
        return None, "unknown"
    return ("%s_x_%s" % (classes[0], classes[1]) if len(classes) > 1 else "%s_only" % classes[0]), "current_state_only"


def safety_zone(ctx, node, at_int, date):
    if not at_int:
        return False, "dated"
    if not node:
        return None, "unknown"
    dates = ctx.psz.get(node, [])
    if any(d is None for d in dates):
        return None, "unknown"
    return any(d <= date for d in dates), "dated"


def camera(ctx, seg, node, at_int, date):
    if not seg and not node:
        return None, "unknown"
    hit = False
    for s in ctx.cameras:
        inside = (seg in s["segs"]) if seg else False
        if not inside and node and (at_int or not seg) and node in s["nodes"]:
            inside = True
        if inside and date >= s["start"]:
            hit = True
    return hit, "dated"


def calming_on_block(rows, date):
    """(flag, basis, measures) for one block."""
    yes, maybe = set(), False
    for d, status, measure in rows:
        if status == "Complete":
            if d is None:
                maybe = True
            elif d <= date:
                yes.add(measure or "unnamed")
        elif status == "Obsolete" or status is None:
            if d is None or d <= date:
                maybe = True
    if yes:
        return True, "dated", yes
    if maybe:
        return None, "unknown", set()
    return False, "dated", set()


def slow_on_block(ctx, rows, date):
    parts = []
    for d in rows:
        if d is not None:
            parts.append((d <= date, "dated"))
        elif ctx.slow_start and date < ctx.slow_start:
            parts.append((False, "dated"))
        else:
            parts.append((None, "unknown"))
    return any_flag(parts) if parts else (False, "dated")


def signal(ctx, seg, node, at_int, date):
    key = node if at_int else seg
    if not key:
        return None, "unknown"
    year = int(date[:4])
    parts = []
    for y in ctx.signals.get(key, []):
        if y is None:
            parts.append((True, "current_state_only"))
        elif y < year:
            parts.append((True, "dated"))
        elif y == year:
            parts.append((None, "unknown"))
        else:
            parts.append((False, "dated"))
    return any_flag(parts) if parts else (False, "dated")


def epc(ctx, crash):
    try:
        lat, lon = float(crash.get("tb_latitude")), float(crash.get("tb_longitude"))
    except (TypeError, ValueError):
        return None, "unknown", None
    if not (37.6 < lat < 37.85 and -122.55 < lon < -122.35):
        return None, "unknown", None
    t = ctx.tracts.find(lon, lat)
    if t is None:
        return None, "unknown", None
    return ctx.epc_flag[t], "definition_acs2022", t


# ---- one row per crash -------------------------------------------------------------------------------------------

def augment_one(crash, ctx):
    date = (crash.get("collision_date") or "")[:10]
    seg, node = cnn(crash.get("cnn_sgmt_fkey")), cnn(crash.get("cnn_intrsctn_fkey"))
    at_int = str(crash.get("intersection") or "").startswith("Intersection")
    blocks, how = ctx.blocks(crash)
    out = {"case_id_pkey": crash["case_id_pkey"], "collision_date": date, "street_block_join": how,
           "street_block_cnns": ";".join(blocks)}

    out["in_epc"], out["in_epc_basis"], out["epc_tract"] = epc(ctx, crash)

    parts, source = [], "block"
    for b in blocks:
        if b in ctx.speed:
            parts.append(speed_on_block(ctx.speed[b], date))
        else:
            near = ctx.speed_neighbours(b)
            parts += [speed_on_block(ctx.speed[c], date) for c in near] or [(None, "unknown")]
            if near:
                source = "adjacent_block"
    out["posted_speed_limit_mph"], out["posted_speed_limit_mph_basis"] = highest(parts)
    out["posted_speed_limit_source"] = source if out["posted_speed_limit_mph"] is not None else None

    out["street_class"], out["street_class_basis"] = highest(
        [(ctx.seg[b]["cls"], "current_state_only") if b in ctx.seg else (None, "unknown") for b in blocks],
        rank=CLASS_RANK)

    if at_int:
        out["corner_type"], out["corner_type_basis"] = corner_type(ctx, node)
    else:
        out["corner_type"], out["corner_type_basis"] = None, "not_applicable"

    lanes = [ctx.lanes[b] for b in blocks if b in ctx.lanes and ctx.lanes[b][0] is not None]
    if lanes:
        op, am, pm = max(lanes, key=lambda v: (v[0], v[1] or 0, v[2] or 0))
        out.update(lanes=op, lanes_am=am, lanes_pm=pm, lanes_basis="current_state_only")
    else:
        out.update(lanes=None, lanes_am=None, lanes_pm=None, lanes_basis="unknown")

    out["bci_traffic_category"], out["bci_traffic_category_basis"] = highest(
        [(ctx.bci.get(b), "current_state_only") for b in blocks], rank={k: -v for k, v in TRAFFIC_RANK.items()})

    out["painted_safety_zone"], out["painted_safety_zone_basis"] = safety_zone(ctx, node, at_int, date)
    out["speed_camera_corridor"], out["speed_camera_corridor_basis"] = camera(ctx, seg, node, at_int, date)

    if blocks:
        cal = [calming_on_block(ctx.calming.get(b, []), date) for b in blocks]
        out["traffic_calming"], out["traffic_calming_basis"] = any_flag([(v, b) for v, b, m in cal])
        out["traffic_calming_types"] = ";".join(sorted(set().union(*[m for v, b, m in cal]))) or None
        out["slow_street"], out["slow_street_basis"] = any_flag(
            [slow_on_block(ctx, ctx.slow.get(b, []), date) for b in blocks])
    else:
        out.update(traffic_calming=None, traffic_calming_basis="unknown", traffic_calming_types=None,
                   slow_street=None, slow_street_basis="unknown")

    out["signal_present"], out["signal_present_basis"] = signal(ctx, seg, node, at_int, date)
    return out


def augment(crashes, ctx):
    rows = [augment_one(c, ctx) for c in crashes]
    assert len(rows) == len(crashes), (len(rows), len(crashes))
    return rows
