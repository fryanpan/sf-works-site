"""Digitise the 2025 Biking and Rolling Plan's North Star network from Appendix L.

SFMTA publishes the North Star network only as a map image (the 2025 "North
Star Map" PDF is a single raster page) — but the plan's Appendix L, "North Star
Index", lists every roadway segment on that map as a table:

    Street | From | To | Existing Facility | North Star Facility | New? | Upgrade?

with the caveat "If discrepancies between this index and the map occur, defer
to the map." This script turns that table into geometry by matching each row
to the city's street centerline network (DataSF 3psu-pn9h) and walking the
centerline segments between the two cross streets, then compares the result
with SFMTA's 2022 Modal Planning Framework planned-bike layer (the network the
street-work map currently draws).

Inputs
  --appendix   the plan appendix PDF, or its pdftotext -layout text. The PDF is
               sfmta.com/media/41946/download, cached in .cache/north-star-appendix/ ("Biking and Rolling Plan
               Appendix 2025 FINAL"); Appendix L is on its last pages.
  DataSF 3psu-pn9h  street centerlines, active rows (~16,400), with f_st/t_st
                    cross streets and node ids.
  out/street-work/cache/mpf_geometry.json  the 2022 MPF layer with geometry,
                    as fetched by scripts/street-work-map.py.

Outputs, under out/north-star/
  index.csv        the parsed Appendix L rows, one per line
  segments.geojson one feature per index row that matched, MultiLineString
  unmatched.csv    rows that could not be placed, with the reason
  comparison.md    North Star 2025 vs MPF 2022 by segment and by mile

Every match is by name, not by eye. Where a row could not be placed it is
listed, not guessed. Run:

    python3 tools/bike-network/north-star-index.py    # reads .cache/north-star-appendix/appendix.pdf
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import csv
import heapq
import json
import math
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfdata
from collections import defaultdict, deque

CENTERLINES = "3psu-pn9h"
CENTERLINE_FLOOR = 15000
COS = math.cos(math.radians(37.76))
OUT = "out/north-star"
MPF_GEOM = "out/street-work/cache/mpf_geometry.json"
# The plan's appendix PDF ("Biking and Rolling Plan Appendix 2025 FINAL"). The
# transportation audit caches the same file at the same path.
APPENDIX_URL = "https://www.sfmta.com/media/41946/download"
APPENDIX_PDF = ".cache/north-star-appendix/appendix.pdf"

# Names Appendix L uses that the centerline file spells differently.
ALIASES = {
    "JFK": "JOHN F KENNEDY", "TERRY A FRANCOIS": "TERRY A FRANCOIS",
    "MISSION BAY N": "MISSION BAY BLVD NORTH", "MISSION BAY S": "MISSION BAY BLVD SOUTH",
    "CESAR CHAVEZ": "CESAR CHAVEZ", "MLK": "MARTIN LUTHER KING JR", "MARTIN LUTHER KING": "MARTIN LUTHER KING JR",
    "EL CAMINO DEL MAR": "EL CAMINO DEL MAR", "UPPER GREAT HWY": "GREAT HWY", "GREAT HIGHWAY": "GREAT HWY",
    "THE EMBARCADERO": "THE EMBARCADERO", "EMBARCADERO": "THE EMBARCADERO",
    "MISSISSIPI": "MISSISSIPPI", "3RD ST BRIDGE": "03RD ST", "BAYSHORE": "BAY SHORE", "MT VERNON": "MOUNT VERNON",
    "UPPER MARKET": "MARKET", "GGP": "JOHN F KENNEDY", "STONESTOWN": "STONESTOWN GALLERIA",
    "FANCISCO": "FRANCISCO", "HARROLD": "HAROLD", "I-280": "I-280", "HUNTERS POINT": "HUNTERS POINT",
    "GLEN CANYON TRAILHEAD": "ELK", "LANDS END": "EL CAMINO DEL MAR", "CAYUGA PARK": "CAYUGA",
    "SAFEWAY PARKING LOT": "DUNCAN", "JOHN F SHELLEY": "JOHN F SHELLEY", "LAKE MERCED PATH": "LAKE MERCED",
}
OPEN_END = {"", "---", "—", "-"}          # Appendix L leaves an end blank where the street simply ends
NEAR_M = 250                               # a cross street that stops short of the street still counts within this
BRIDGE_M = 50                              # two of a street's nodes this close are one place (a break in its graph)
TYPES = {"ST", "AVE", "BLVD", "DR", "WAY", "RD", "LN", "PL", "CT", "TER", "HWY", "PKWY", "CIR", "ALY", "PATH", "STWY", "PLZ", "LOOP", "ROW", "WALK", "TUNL", "EXPY", "HL", "RAMP"}
TYPE_WORDS = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN", "PLACE": "PL", "TERRACE": "TER", "HIGHWAY": "HWY", "PARKWAY": "PKWY", "CIRCLE": "CIR", "ALLEY": "ALY"}
DIRS = {"EB", "WB", "NB", "SB", "N", "S", "E", "W", "NORTH", "SOUTH"}


def norm(name):
    """'2nd St' -> ('02ND', 'ST'); 'Alemany EB' -> ('ALEMANY', None); 'JFK' -> ('JOHN F KENNEDY', None)."""
    s = re.sub(r"[.,']", "", name.strip().upper())
    s = re.sub(r"\s+", " ", s)
    if s in ALIASES:
        s = ALIASES[s]
    toks = s.split()
    while len(toks) > 1 and toks[-1] in DIRS:
        toks.pop()
    typ = None
    if len(toks) > 1 and (toks[-1] in TYPES or toks[-1] in TYPE_WORDS):
        typ = TYPE_WORDS.get(toks[-1], toks[-1])
        toks.pop()
    toks = [re.sub(r"^(\d)(ST|ND|RD|TH)$", r"0\1\2", t) for t in toks]
    base = " ".join(toks)
    base = ALIASES.get(base, base)
    return base, typ


def base_of_centerline(streetname):
    b, _ = norm(streetname)
    return b


def appendix_text(path):
    """The appendix as pdftotext -layout text: a .txt is read as is, a PDF is
    converted, and the PDF is fetched from sfmta.com when it is missing."""
    if path.endswith(".txt"):
        return open(path, encoding="utf-8", errors="replace").read()
    if not os.path.exists(path):
        req = urllib.request.Request(APPENDIX_URL, headers={"User-Agent": "Mozilla/5.0 (sf-works; +https://sf-works.org)"})
        with urllib.request.urlopen(req, timeout=300) as fh:
            body = fh.read()
        if not body.startswith(b"%PDF"):
            sys.exit(f"{APPENDIX_URL} did not return a PDF")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(body)
    return subprocess.run(["pdftotext", "-layout", path, "-"], check=True,
                          capture_output=True).stdout.decode("utf-8", "replace")


def parse_appendix(text):
    lines = text.split("\n")
    rows, cols = [], None
    in_l = False
    for ln in lines:
        if "Appendix L" in ln and "North Star Index" in ln:
            in_l = True
            continue
        if not in_l:
            continue
        if re.match(r"\s*Street\s+From\s+To\s+Existing Facility", ln):
            cols = [m.start() for m in re.finditer(r"Street|From|To |Existing Facility|North Star Facility|New\?|Upgrade\?", ln)]
            continue
        if "North Star Index • February 2025 | Page" in ln or "The following is an index" in ln or "between this index and the map" in ln:
            continue
        if re.match(r"\s*Appendix [M-Z]", ln):
            break
        if cols is None or not ln.strip():
            continue
        cells = [ln[a:b].strip() for a, b in zip(cols, cols[1:] + [len(ln) + 200])]
        if len(cells) < 7 or not cells[0]:
            continue
        street, frm, to, existing, ns, new, upg = cells[:7]
        if new not in ("Y", "N") or upg not in ("Y", "N"):
            continue
        rows.append({"street": street, "from": frm, "to": to, "existing": existing,
                     "north_star": ns, "new": new, "upgrade": upg})
    return rows


def fetch_centerlines(cache_dir):
    """Active street centerlines. Through `lib/sfdata.py` since 2026-09-06 --
    the read now paginates, where the $limit of 50,000 it used to send was one
    page and would have truncated silently had the network outgrown it."""
    r = sfdata.fetch(
        CENTERLINES,
        select="cnn,street,st_type,streetname,f_st,t_st,f_node_cnn,t_node_cnn,line,oneway",
        where="active='true'", floor=CENTERLINE_FLOOR, cache_dir=cache_dir)
    print(f"  {CENTERLINES}: {len(r.rows):,} active centerlines"
          f"{' (cached ' + r.fetched_on.isoformat() + ')' if r.from_cache else ''}",
          file=sys.stderr)
    return r.rows


def seg_len_m(coords):
    d = 0.0
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        dx = (x1 - x0) * 111_320 * math.cos(math.radians((y0 + y1) / 2))
        dy = (y1 - y0) * 111_320
        d += math.hypot(dx, dy)
    return d


def place(row, by_base, by_base_type, node_streets, node_xy):
    """Return (cnn list, reason). The street's centerline blocks between where FROM meets it and where TO meets it:
    every block on a run between the two no more than a quarter longer than the shortest (both carriageways of a
    divided street), or every block reachable from the named end when the other end is open.

    Matching, in order: a node shared with a centerline carrying the cross street's name (exact, then prefix);
    then the street node nearest any node of the cross street if within NEAR_M (a cross street that stops
    short); a blank or '---' end means the street's own end. Two of the street's nodes within BRIDGE_M are
    linked, so a break in the centerline graph does not stop the walk.
    """
    segs = []
    for part in row["street"].split("/"):          # "Duboce / 13th St" is one corridor on two names
        sbase, styp = norm(part)
        got = by_base_type.get((sbase, styp)) if styp else None
        segs += got or by_base.get(sbase, [])
    if not segs:
        return [], f"street not in centerlines: {row['street']!r} -> {norm(row['street'])[0]!r}"
    own_nodes = {s["f_node_cnn"] for s in segs} | {s["t_node_cnn"] for s in segs}

    # The centerline file breaks some streets' graphs at an offset
    # intersection (Plymouth by 33 m, San Jose Ave by 45 m at the I-280
    # ramps). Two of the street's own nodes within BRIDGE_M that no block
    # joins are one place, linked at no length by a link that names no block.
    nodes = sorted(n for n in own_nodes if n in node_xy)
    joined = {frozenset((s["f_node_cnn"], s["t_node_cnn"])) for s in segs}
    bridges = [(n, m) for i, n in enumerate(nodes) for m in nodes[i + 1:]
               if math.dist(node_xy[n], node_xy[m]) <= BRIDGE_M and frozenset((n, m)) not in joined]
    def by_name(xbase):
        out = {n for n in own_nodes if xbase in node_streets.get(n, ())}
        if not out and len(xbase) >= 5:
            out = {n for n in own_nodes if any(b.startswith(xbase) or xbase.startswith(b) for b in node_streets.get(n, ()) if len(b) >= 5)}
        return out

    def nearest(xbase):
        targets = [node_xy[n] for n, bs in node_streets.items() if n in node_xy and any(b == xbase or (len(xbase) >= 5 and b.startswith(xbase)) for b in bs)]
        if not targets:
            return set()
        best, bd = None, NEAR_M
        for n in own_nodes:
            if n not in node_xy:
                continue
            x0, y0 = node_xy[n]
            for x1, y1 in targets:
                d = math.hypot(x1 - x0, y1 - y0)
                if d < bd:
                    best, bd = n, d
        return {best} if best else set()

    def ends(label):
        raw = label.strip()
        if raw in OPEN_END:
            return "open", set()
        found = set()
        for part in raw.split("/"):
            xb, _ = norm(part)
            found |= by_name(xb) or nearest(xb)
        return ("ok", found) if found else ("missing", set())

    adj = defaultdict(list)
    for sg in segs:
        a, b = sg["f_node_cnn"], sg["t_node_cnn"]
        adj[a].append((b, sg["cnn"]))
        adj[b].append((a, sg["cnn"]))
    for a, b in bridges:
        adj[a].append((b, None))
        adj[b].append((a, None))

    def bfs(start):
        prev = {start: (None, None)}
        order = []
        dq = deque([start])
        while dq:
            n = dq.popleft()
            order.append(n)
            for m, cnn in adj[n]:
                if m not in prev:
                    prev[m] = (n, cnn)
                    dq.append(m)
        return prev, order

    fa, A = ends(row["from"])
    tb, B = ends(row["to"])
    if fa == "missing":
        return [], f"cross street not on {row['street']!r}: {row['from']!r}"
    if tb == "missing":
        return [], f"cross street not on {row['street']!r}: {row['to']!r}"
    if fa == "open" and tb == "open":
        return sorted({sg["cnn"] for sg in segs}), ""
    if fa == "open" or tb == "open":
        # Every block of the street reachable from the named end. One walk
        # to the farthest node kept one carriageway of a divided street and
        # one direction of a street that runs both ways from the cross
        # street (Skyline from John Muir, 2026-09-29); the map then says
        # which of them the plan draws.
        starts = B if fa == "open" else A
        got = set()
        for st in sorted(starts):
            prev, order = bfs(st)
            got |= {cnn for n in order for _, cnn in adj[n] if cnn}
        return sorted(got), ("" if got else f"{row['street']!r} has no extent from {row['from'] or row['to']!r}")
    # The street's blocks on any run from A to B no more than a quarter
    # longer than the shortest, plus 50 m. A single shortest walk named one
    # carriageway of a divided street (Octavia, Potrero, Brotherhood, the
    # Embarcadero) and skipped the short pieces at a split intersection, so
    # the trace held those blocks to the unnamed 20 m tolerance.
    seg_m = {sg["cnn"]: seg_len_m(sg["line"]["coordinates"]) for sg in segs}

    def reach(starts):
        dist, heap = {}, []
        for n in sorted(starts):
            dist[n] = 0.0
            heapq.heappush(heap, (0.0, n))
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist.get(n, 1e18):
                continue
            for m, cnn in adj[n]:
                nd = d + (seg_m[cnn] if cnn else 0.0)
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    heapq.heappush(heap, (nd, m))
        return dist
    # The shortest run between two distinct end nodes. A street that meets
    # the same cross street twice ("Congdon, Alemany to Alemany") has both
    # ends in A and in B, so the pair has to be distinct rather than B
    # outside A. The distances are then from every node of each end, so a
    # second road of the same name between the two cross streets (the upper
    # and lower Great Highway) is the row's too.
    shortest = None
    for a in sorted(A):
        d = reach({a})
        for b in sorted(B):
            if b != a and b in d and (shortest is None or d[b] < shortest):
                shortest = d[b]
    if shortest is None:
        return [], f"no continuous {row['street']!r} between {row['from']!r} and {row['to']!r}"
    da, db = reach(A), reach(B)
    lim = 1.25 * shortest + 50.0
    def through(cnn, x, y):
        # A run A..x, the block, y..B that does not double back over the
        # block: a dead-end stub past an end (Octavia north of Hayes on the
        # row that runs Market to Hayes) otherwise fit inside the 50 m.
        L = seg_m[cnn]
        ax, by_ = da.get(x, 1e18), db.get(y, 1e18)
        return ax + L + by_ <= lim and by_ < db.get(x, 1e18) + L - 1e-6 and ax < da.get(y, 1e18) + L - 1e-6

    got = set()
    for sg in segs:
        f, t = sg["f_node_cnn"], sg["t_node_cnn"]
        if through(sg["cnn"], f, t) or through(sg["cnn"], t, f):
            got.add(sg["cnn"])
    return sorted(got), ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--appendix", default=APPENDIX_PDF,
                    help="the appendix PDF, or its pdftotext -layout output (fetched from sfmta.com when missing)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--cache", action="store_true")
    args = ap.parse_args()
    cache_dir = os.path.join(args.out, "cache") if args.cache else None
    os.makedirs(args.out, exist_ok=True)

    rows = parse_appendix(appendix_text(args.appendix))
    if len(rows) < 300:
        sys.exit(f"FAIL: parsed only {len(rows)} index rows; the layout parser has lost the table")
    with open(os.path.join(args.out, "index.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"Appendix L: {len(rows)} rows; new {sum(r['new']=='Y' for r in rows)}, upgrade {sum(r['upgrade']=='Y' for r in rows)}", file=sys.stderr)

    print("Fetching:", file=sys.stderr)
    cl = fetch_centerlines(cache_dir)
    by_cnn = {}
    by_base, by_base_type = defaultdict(list), defaultdict(list)
    for s in cl:
        if not s.get("line") or not s.get("f_node_cnn"):
            continue
        s["cnn"] = str(int(float(s["cnn"])))
        by_cnn[s["cnn"]] = s
        b = base_of_centerline(s.get("streetname") or s.get("street") or "")
        by_base[b].append(s)
        by_base_type[(b, (s.get("st_type") or "").upper() or None)].append(s)

    node_streets, node_xy = defaultdict(set), {}
    for s in by_cnn.values():
        b = base_of_centerline(s.get("streetname") or s.get("street") or "")
        node_streets[s["f_node_cnn"]].add(b)
        node_streets[s["t_node_cnn"]].add(b)
        c = s["line"]["coordinates"]
        node_xy.setdefault(s["f_node_cnn"], (c[0][0] * 111_320 * COS, c[0][1] * 111_320))
        node_xy.setdefault(s["t_node_cnn"], (c[-1][0] * 111_320 * COS, c[-1][1] * 111_320))

    features, unmatched = [], []
    ns_cnns = {}
    for r in rows:
        cnns, why = place(r, by_base, by_base_type, node_streets, node_xy)
        if not cnns:
            unmatched.append({**r, "reason": why})
            continue
        for c in cnns:
            ns_cnns[c] = r
        features.append({"type": "Feature", "properties": {**r, "cnns": cnns, "segments": len(cnns),
                         "length_m": round(sum(seg_len_m(by_cnn[c]["line"]["coordinates"]) for c in cnns))},
                         "geometry": {"type": "MultiLineString", "coordinates": [by_cnn[c]["line"]["coordinates"] for c in cnns]}})
    json.dump({"type": "FeatureCollection", "features": features}, open(os.path.join(args.out, "segments.geojson"), "w"))
    with open(os.path.join(args.out, "unmatched.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ["reason"])
        w.writeheader(); w.writerows(unmatched)
    placed_m = sum(f["properties"]["length_m"] for f in features)
    print(f"Placed {len(features)}/{len(rows)} rows on {len(ns_cnns):,} centerline segments, {placed_m/1609.34:.1f} miles; {len(unmatched)} unmatched", file=sys.stderr)

    # --- compare with MPF 2022 ------------------------------------------------
    comp = []
    if os.path.exists(MPF_GEOM):
        mpf = json.load(open(MPF_GEOM))
        planned = {}
        for f in mpf:
            a = f["attributes"]
            cb = (a.get("CORE_BIKING") or "").strip()
            if cb in ("High", "Medium", "Low") or a.get("GAP_BIKE_SEGMENTS") == "Yes":
                c = a.get("CNN")
                if c is not None:
                    planned[str(int(float(c)))] = a
        def miles(cnns):
            return sum(seg_len_m(by_cnn[c]["line"]["coordinates"]) for c in cnns if c in by_cnn) / 1609.34
        both = set(ns_cnns) & set(planned)
        only_ns = set(ns_cnns) - set(planned)
        only_mpf = set(planned) - set(ns_cnns)
        # Split MPF-only by whether Appendix L names the street at all (placed or not). A segment on a street
        # the index never mentions is genuinely absent from the 2025 network; one on a street it does name is
        # more likely a row this script could not place, or a different extent.
        index_streets = set()
        for r in rows:
            for part in r["street"].split("/"):
                index_streets.add(norm(part)[0])
        mpf_named = {c for c in only_mpf if base_of_centerline(planned[c].get("STREETNAME") or "") in index_streets}
        mpf_unnamed = only_mpf - mpf_named
        by_fac = defaultdict(list)
        for c in only_ns:
            by_fac[ns_cnns[c]["north_star"]].append(c)
        comp = [
            "# North Star 2025 vs Modal Planning Framework 2022",
            "",
            f"Generated by `tools/bike-network/north-star-index.py`. North Star rows come from Appendix L of the 2025 Biking and Rolling Plan (index dated February 2025), placed on DataSF `{CENTERLINES}` centerlines by street and cross-street name. MPF planned = `CORE_BIKING` in High/Medium/Low or `GAP_BIKE_SEGMENTS` = Yes, from SFMTA's `MTA.MPF_Network` layer (created 2022). Both are compared on the city's centerline segment id (CNN).",
            "",
            "| | Segments | Miles |",
            "| --- | --- | --- |",
            f"| North Star 2025, placed | {len(ns_cnns):,} | {miles(ns_cnns):.1f} |",
            f"| MPF 2022 planned bike (all) | {len(planned):,} | {miles(planned):.1f} |",
            f"| On both | {len(both):,} | {miles(both):.1f} |",
            f"| **North Star only** (planned in 2025, not in the 2022 layer) | **{len(only_ns):,}** | **{miles(only_ns):.1f}** |",
            f"| MPF only, all | {len(only_mpf):,} | {miles(only_mpf):.1f} |",
            f"| MPF only, on a street Appendix L names (extent differs, or this script could not place the row) | {len(mpf_named):,} | {miles(mpf_named):.1f} |",
            f"| **MPF only, on a street Appendix L never names** (in the 2022 layer, absent from the 2025 index) | **{len(mpf_unnamed):,}** | **{miles(mpf_unnamed):.1f}** |",
            "",
            "North Star-only segments by 2025 facility type:",
            "",
        ] + [f"- {k or '(blank)'}: {len(v):,} segments, {miles(v):.1f} miles" for k, v in sorted(by_fac.items(), key=lambda kv: -len(kv[1]))] + [
            "",
            f"Unplaced Appendix L rows: {len(unmatched)} of {len(rows)} (see `unmatched.csv`). Their miles are not in the North Star totals above, so the North Star-only figure is a floor.",
            "",
            "Streets in the 2022 layer that Appendix L never names, most segments first (a name change, a path, or a dropped corridor; check the North Star map before calling it dropped):",
            "",
        ]
        by_street = defaultdict(int)
        for c in mpf_unnamed:
            by_street[planned[c].get("STREETNAME") or "?"] += 1
        comp += [f"- {k}: {v}" for k, v in sorted(by_street.items(), key=lambda kv: -kv[1])[:25]]
        open(os.path.join(args.out, "comparison.md"), "w").write("\n".join(comp) + "\n")
        print("\n".join(comp[4:15]), file=sys.stderr)
    else:
        print(f"  (no {MPF_GEOM}; run scripts/street-work-map.py --cache first to compare)", file=sys.stderr)


if __name__ == "__main__":
    main()
