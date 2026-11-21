#!/usr/bin/env python3
"""Each school's point checked against the city's own address point for the street address CDE lists, and the points that fail corrected.

    tools/school-trips/school-points.py            # writes data/school-sim/school-points.json
    tools/school-trips/school-points.py --update   # re-read the city's addresses first if DataSF says they changed
    tools/school-trips/school-points.py --selftest # show the check failing on Life Learning Academy's old point

WHY. CDE's Public Schools and Districts file puts Life Learning Academy Charter
(651 Eighth Street, Building 229, Treasure Island, 94130) at 37.77091,
-122.40479, 7th and Brannan in SoMa: a geocoder matched SoMa's 8th Street.
DataSF's schools dataset (7e7j-59qk) is a copy of the CDE file and carries the
same point, so neither can check the other. The check here is the city's
Enterprise Addressing System (DataSF 3mea-di5p), which knows Treasure Island's
8th Street as "08TH TI ST".

THE MATCH. Each active SF school in the CDE capture the repo reads
(data/extract/schools/cde-sf.json's meta.url, a fixed Internet Archive copy)
has its street address (the file's StreetAbr) parsed to a number and a street
name and looked up in EAS by number, name and ZIP. Treasure Island streets
carry "TI" in EAS's name, so a 94130 address tries that name first. Ordinal
words (Eighth) become EAS's padded ordinals (08TH). An address EAS lacks is
matched to the nearest number on the same side of the same street, and marked.

THE RULE. A school whose CDE point is more than LIMIT_FT from its EAS point
takes the EAS point; every other school keeps CDE's. lib/school_points.py
applies this file to cde-sf.json's records for every script that reads them,
so the CDE extract stays a faithful copy of CDE. LIMIT_FT is 500 ft, the
school-zone distance (CVC §22352(b)(2)) the School Trips maps draw.

CHECKS, before anything is written: at least FLOOR_MATCHED schools matched, and
every public school in site/data/school-sim/index.json matched (its private
schools are not in the CDE public-schools file, so they have no CDE point to
check and keep the sim's own). A failed check raises
and the previous file stays. tools/school-trips/school-sim.py's school-sim/school-points-near
check then holds every simulated school's point to within LIMIT_FT of its EAS
point, in the school-sim step.

INCREMENTAL. The CDE capture is a fixed archive copy, cached under
.cache/school-points/. --update reads 3mea-di5p's rowsUpdatedAt and re-reads the
addresses only when it differs from the one recorded in the file.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import json
import math
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib.stable import write_json  # noqa: E402

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "school-sim", "school-points.json")
CDE_EXTRACT = os.path.join(ROOT, "data", "extract", "schools", "cde-sf.json")
INDEX = os.path.join(ROOT, "site", "data", "school-sim", "index.json")
CACHE = os.path.join(ROOT, ".cache", "school-points")
EAS = "3mea-di5p"
MARKER = "socrata:%s:school-points" % EAS
LIMIT_FT = 500.0
FLOOR_MATCHED = 120
FT_LAT = 364000.0
FT_LON = 364000.0 * math.cos(math.radians(37.76))

ORDINALS = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH", "NINTH", "TENTH",
            "ELEVENTH", "TWELFTH", "THIRTEENTH", "FOURTEENTH", "FIFTEENTH", "SIXTEENTH", "SEVENTEENTH",
            "EIGHTEENTH", "NINETEENTH", "TWENTIETH"]
TYPES = {"ST": "ST", "STREET": "ST", "AVE": "AVE", "AVENUE": "AVE", "AV": "AVE", "BLVD": "BLVD", "BOULEVARD": "BLVD",
         "DR": "DR", "DRIVE": "DR", "WAY": "WAY", "CIR": "CIR", "CIRCLE": "CIR", "RD": "RD", "ROAD": "RD",
         "TER": "TER", "TERRACE": "TER", "PL": "PL", "PLACE": "PL", "CT": "CT", "COURT": "CT", "LN": "LN",
         "LANE": "LN", "HWY": "HWY", "PLZ": "PLZ", "PLAZA": "PLZ", "ALY": "ALY", "ALLEY": "ALY"}


# CDE spellings that are not the street's name in EAS.
ALIASES = {"DOUGLAS": "DOUGLASS"}


def ft(a, b):
    return math.hypot((a[0] - b[0]) * FT_LON, (a[1] - b[1]) * FT_LAT)


def ordinal(n):
    suf = "TH" if 10 <= n % 100 <= 20 else {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return "%02d%s" % (n, suf)


def parse(street):
    """(number, name key, type) of a CDE street line like '651 Eighth St., Bldg. 229 Treasure Island', or None."""
    s = street.upper().split(",")[0].replace(".", " ")
    m = re.match(r"\s*(\d+)(?:-\d+)?\s+(.*)", s)
    if not m:
        return None
    num, words = int(m.group(1)), m.group(2).split()
    typ = None
    if words and words[-1] in TYPES:
        typ = TYPES[words.pop()]
    out = []
    for w in words:
        if w in ORDINALS:
            w = ordinal(ORDINALS.index(w) + 1)
        elif re.fullmatch(r"\d+(ST|ND|RD|TH)", w):
            w = ordinal(int(w[:-2]))
        out.append(w)
    return num, key(" ".join(out)), typ


def key(name):
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


# -- inputs -------------------------------------------------------------------------

def cde_rows():
    """{cds: CDE row} for San Francisco, read from the capture cde-sf.json was built from."""
    url = json.load(open(CDE_EXTRACT))["meta"]["url"]
    path = os.path.join(CACHE, "pubschls.xlsx")
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "sf-works school-points"})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        with open(path + ".part", "wb") as fh:
            fh.write(data)
        os.replace(path + ".part", path)
    return {r["CDSCode"]: r for r in read_xlsx(path) if r.get("County") == "San Francisco"}, url


def read_xlsx(path):
    """The first sheet's rows as dicts, from the header row that names CDSCode on (the standard library only)."""
    M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("{%s}si" % M):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % M)))
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]

    def col(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1
    hdr = None
    for _ev, el in ET.iterparse(z.open(sheet)):
        if not el.tag.endswith("}row"):
            continue
        vals = {}
        for c in el.findall("{%s}c" % M):
            v, t = c.find("{%s}v" % M), c.get("t")
            if t == "inlineStr":
                vals[col(c.get("r"))] = "".join(x.text or "" for x in c.iter("{%s}t" % M))
            elif v is not None:
                vals[col(c.get("r"))] = ss[int(v.text)] if t == "s" else v.text
        el.clear()
        row = [vals.get(i) for i in range(max(vals) + 1)] if vals else []
        if hdr is None:
            hdr = row if "CDSCode" in row else None
            continue
        yield dict(zip(hdr, row))


def eas(refresh=False):
    r = sfdata.fetch(EAS, select="eas_baseid,address_number,street_name,street_type,zip_code,longitude,latitude",
                     refresh=refresh, floor=150000)
    by = collections.defaultdict(list)
    for x in r.rows:
        try:
            num, lon, lat = int(float(x["address_number"])), float(x["longitude"]), float(x["latitude"])
        except (KeyError, TypeError, ValueError):
            continue
        by[key(x.get("street_name"))].append({"num": num, "type": x.get("street_type"), "zip": (x.get("zip_code") or "")[:5],
                                              "id": x.get("eas_baseid"), "lon": lon, "lat": lat,
                                              "address": "%d %s %s" % (num, x.get("street_name"), x.get("street_type") or "")})
    return by, r


def match(by, street, zip5):
    """The EAS row for a CDE street line and ZIP, how it matched, and the other ZIPs the same number and name exist in.

    The ZIP decides between two places with the same number and street name (651 8th St is in SoMa and on
    Treasure Island). CDE's ZIP is sometimes not EAS's (Willie Brown Middle's 94122 is EAS's 94124), so an
    address in only one place matches whatever its ZIP; one in two places more than LIMIT_FT apart, neither
    in CDE's ZIP, is left unmatched as ambiguous."""
    p = parse(street or "")
    if p is None:
        return None, "no street number", []
    num, name, typ = p
    name = ALIASES.get(name, name)
    names = ([name + "TI"] if zip5 == "94130" else []) + [name]
    for nm in names:
        rows = [x for x in by.get(nm, []) if typ is None or x["type"] == typ] or by.get(nm, [])
        same = [x for x in rows if x["num"] == num]
        # Every other place this number and street name exist, Treasure Island's and the city's alike.
        elsewhere = sorted(set(x["zip"] for n2 in names for x in by.get(n2, []) if x["num"] == num) - {zip5})
        hit = sorted(same, key=lambda x: (x["zip"] != zip5, x["id"] or ""))
        if hit and hit[0]["zip"] == zip5:
            return hit[0], "exact", elsewhere
        if hit:
            spread = max(ft((a["lon"], a["lat"]), (b["lon"], b["lat"])) for a in hit for b in hit)
            if spread > LIMIT_FT:
                return None, "ambiguous: %d %s is in ZIPs %s, not %s" % (num, nm, ", ".join(elsewhere), zip5), elsewhere
            return hit[0], "exact, EAS ZIP %s" % hit[0]["zip"], elsewhere
        side = [x for x in rows if x["num"] % 2 == num % 2 and abs(x["num"] - num) <= 100]
        zips = set(x["zip"] for x in side)
        side = [x for x in side if x["zip"] == zip5] or (side if len(zips) == 1 else [])
        if side:
            near = min(side, key=lambda x: (abs(x["num"] - num), x["id"] or ""))
            return near, "nearest number on the same side (%d)" % near["num"], elsewhere
    return None, "not in EAS", []


# -- build --------------------------------------------------------------------------

def build(refresh=False):
    cde, url = cde_rows()
    by, r = eas(refresh)
    sim = {s["cds"] for s in json.load(open(INDEX))["schools"] if not s.get("private")}
    rows, missing = {}, []
    for cds, c in sorted(cde.items()):
        if c.get("StatusType") != "Active":
            continue
        try:
            pt = [float(c["Longitude"]), float(c["Latitude"])]
        except (TypeError, ValueError):
            pt = None
        zip5 = (c.get("Zip") or "")[:5]
        hit, how, elsewhere = match(by, c.get("StreetAbr") or c.get("Street"), zip5)
        if hit is None:
            missing.append(cds)
            rows[cds] = {"name": c["School"], "address": c.get("StreetAbr"), "zip": zip5, "cde": pt, "eas": None, "how": how}
            continue
        d = round(ft(pt, (hit["lon"], hit["lat"]))) if pt else None
        rows[cds] = {"name": c["School"], "address": c.get("StreetAbr"), "zip": zip5, "cde": pt,
                     "eas": {"address": hit["address"].strip(), "id": hit["id"], "lon": round(hit["lon"], 6), "lat": round(hit["lat"], 6)},
                     "how": how, "ft": d, "sameAddressElsewhere": elsewhere,
                     "fixed": d is None or d > LIMIT_FT}
    bad = []
    matched = sum(1 for x in rows.values() if x["eas"])
    if matched < FLOOR_MATCHED:
        bad.append("%d schools matched in EAS, below the floor of %d" % (matched, FLOOR_MATCHED))
    lost = sorted(c for c in sim if not (rows.get(c) or {}).get("eas"))
    if lost:
        bad.append("simulated schools with no EAS match: %s" % ", ".join(lost))
    if bad:
        raise SystemExit("school-points: " + "; ".join(bad))
    meta = sfdata.metadata(EAS)
    return {"note": "Written by tools/school-trips/school-points.py. Each active SF school's CDE point (cde, [lon, lat]) against the EAS "
                    "address point for the street address CDE lists (eas). ft is the distance between them; fixed means it "
                    "is over %d ft and lib/school_points.py moves the school to its EAS point." % LIMIT_FT,
            "limitFt": LIMIT_FT,
            "sources": {"cde": {"url": url, "tag": "[primary — read 2026-10-21]"},
                        "eas": {"url": "https://data.sfgov.org/d/%s" % EAS, "tag": r.tag, "rowsUpdatedTs": meta.get("rows_updated_ts")}},
            "unmatched": missing, "schools": rows}


def selftest():
    """Life Learning Academy's old CDE point fails the LIMIT_FT rule, and sits on SoMa's 651 8th St, the geocoder's mistake."""
    by, _ = eas()
    hit, how, _e = match(by, "651 Eighth St., Bldg. 229 Treasure Island", "94130")
    old = (-122.40479, 37.77091)
    soma = [x for x in by.get("08TH", []) if x["num"] == 651 and x["type"] == "ST"]
    d = ft(old, (hit["lon"], hit["lat"])) if hit else 0
    d_soma = ft(old, (soma[0]["lon"], soma[0]["lat"])) if soma else 1e9
    print("  651 Eighth St, 94130 matches %s (%s); CDE's point is %s ft from it: %s" % (
        hit and hit["address"], how, format(round(d), ","), "fails the %d ft rule, as it should" % LIMIT_FT if d > LIMIT_FT else "PASSES (wrong)"))
    print("  CDE's point is %.0f ft from %s, ZIP %s" % (d_soma, soma and soma[0]["address"], soma and soma[0]["zip"]))
    return bool(hit) and hit["address"].startswith("651 08TH TI") and d > LIMIT_FT and d_soma < LIMIT_FT


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    refresh = False
    if a.update:
        have = json.load(open(OUT)) if os.path.exists(OUT) else {}
        stamp = sfdata.metadata(EAS).get("rows_updated_ts")
        refresh = (have.get("sources") or {}).get("eas", {}).get("rowsUpdatedTs") != stamp
        if not refresh:
            print("  %s unchanged (rowsUpdatedAt %s)" % (EAS, stamp))
            pipeline_state.record(MARKER, "unchanged", version=str(stamp))
            return
    out = build(refresh)
    write_json(OUT, out)
    fixed = sorted((x["ft"] or 0, c, x["name"]) for c, x in out["schools"].items() if x.get("fixed") and x["eas"])
    print("  %d active schools, %d matched in EAS, %d moved to their EAS point:" % (
        len(out["schools"]), sum(1 for x in out["schools"].values() if x["eas"]), len(fixed)))
    for d, c, n in reversed(fixed):
        print("    %s %s: CDE point %s ft from %s" % (c, n, format(d, ","), out["schools"][c]["eas"]["address"]))
    if a.update:
        pipeline_state.record(MARKER, "changed", version=str(out["sources"]["eas"]["rowsUpdatedTs"]))


if __name__ == "__main__":
    main()
