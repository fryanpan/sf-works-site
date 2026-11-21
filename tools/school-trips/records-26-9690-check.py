#!/usr/bin/env python3
"""Reproduce the published totals in records request 26-9690: the 2024-25 Travel Tally workbook against SF-SRTS's memo, and the North Star shapefile's miles by class.

Reads .cache/records-26-9690/, which is gitignored. Standard library only. Exits 1 if a total stops matching.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

CACHE = Path(paths.ROOT) / ".cache" / "records-26-9690"
if not CACHE.exists():  # a worktree has no .cache of its own
    CACHE = Path(paths.ROOT).parents[2] / ".cache" / "records-26-9690"  # .claude/worktrees/<name> -> the main checkout
WORKBOOK = CACHE / "2024-25 SFUSD Travel Tally Data_YSB_Final_ToShare.xlsx"
SHAPEFILE = CACHE / "bikeandrollNSnetwork_share.zip"
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# The memo's counts, section V.B and its footnote 3.
MEMO = {"AP": 10125, "BC": 10026, "AQ": 1749, "BD": 1888, "AS": 2523, "BF": 2872, "AV": 5151, "BI": 4641}
MEMO_SCHOOLS = 95
MEMO_CAR_SHARE = 48.6  # section V, an AM/PM average
# The memo's other shares, section V, as morning and afternoon count columns. It prints biking as 2%.
MEMO_SHARES = {"walking": (("AQ", "BD"), 18.1), "transit": (("AS", "BF"), 26.8), "biking": (("AR", "BE"), 2.0),
               "carpool": (("AT", "BG"), 3.9), "other": (("AU", "BH"), 0.7)}


def sheet(path, name):
    """One worksheet as a list of {column letter: value} rows."""
    z = zipfile.ZipFile(path)
    strings = ["".join(t.text or "" for t in si.iter(M + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find(M + "sheets"):
        if s.get("name") != name:
            continue
        target = rels[s.get(REL + "id")].lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        rows = []
        for r in ET.fromstring(z.read(target)).find(M + "sheetData"):
            row = {}
            for c in r:
                v = c.find(M + "v")
                if v is not None:
                    col = re.match(r"[A-Z]+", c.get("r")).group()
                    row[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
            rows.append(row)
        return rows
    raise SystemExit(f"no sheet {name}")


def num(row, col):
    try:
        return float(row.get(col, 0))
    except ValueError:  # '#REF!' and 'N/A' cells
        return 0.0


def tally():
    """One row is one school. The sheet's section labels carry no counts, so a school is a row with a tally."""
    schools = [r for r in sheet(WORKBOOK, "2024-2025")[4:] if num(r, "AP") or num(r, "BC")]
    ok = len(schools) == MEMO_SCHOOLS
    print(f"schools with a tally: {len(schools)} (memo {MEMO_SCHOOLS})")
    for col, want in MEMO.items():
        got = int(sum(num(r, col) for r in schools))
        ok &= got == want
        print(f"  column {col}: {got} (memo {want})")
    car = 50 * (sum(num(r, "AV") for r in schools) / MEMO["AP"] + sum(num(r, "BI") for r in schools) / MEMO["BC"])
    ok &= round(car, 1) == MEMO_CAR_SHARE
    print(f"family car, AM/PM average: {car:.1f}% (memo {MEMO_CAR_SHARE}%)")
    for mode, ((am, pm), want) in MEMO_SHARES.items():
        got = 50 * (sum(num(r, am) for r in schools) / MEMO["AP"] + sum(num(r, pm) for r in schools) / MEMO["BC"])
        ok &= abs(got - want) <= 0.1
        print(f"{mode}, AM/PM average: {got:.1f}% (memo {want}%)")
    print(f"yellow bus count, these schools: {int(sum(num(r, 'AO') for r in schools))}")
    return ok


def north_star():
    """One row is one street block by CNN, or a piece of one. Lengths are in US survey feet (CS13_ftUS)."""
    z = zipfile.ZipFile(SHAPEFILE)
    b = z.read("bikeandrollNSnetwork_share.dbf")
    n, header, width = struct.unpack("<xxxxIHH", b[:12])
    fields = [(b[o:o + 11].split(b"\0")[0].decode(), b[o + 16]) for o in range(32, header - 1, 32)]
    classes = []
    for i in range(n):
        p = header + i * width + 1
        row = {}
        for name, size in fields:
            row[name] = b[p:p + size].decode("utf8", "replace").strip()
            p += size
        classes.append(row["NS_bikeway"])
    s = z.read("bikeandrollNSnetwork_share.shp")
    o, feet = 100, []
    while o < len(s):
        length = struct.unpack(">ii", s[o:o + 8])[1]
        parts, points = struct.unpack("<ii", s[o + 44:o + 52])
        starts = list(struct.unpack(f"<{parts}i", s[o + 52:o + 52 + 4 * parts])) + [points]
        q = o + 52 + 4 * parts
        xy = struct.unpack(f"<{2 * points}d", s[q:q + 16 * points])
        feet.append(sum(math.hypot(xy[2 * i + 2] - xy[2 * i], xy[2 * i + 3] - xy[2 * i + 1])
                        for a, e in zip(starts, starts[1:]) for i in range(a, e - 1)))
        o += 8 + 2 * length
    miles = collections.Counter()
    for c, f in zip(classes, feet):
        miles[c] += f / 5280
    for c, m in miles.most_common():
        print(f"  {c}: {m:.1f} miles")
    print(f"North Star file: {n} rows, {sum(miles.values()):.1f} miles")
    return n == len(feet)


if __name__ == "__main__":
    good = tally()
    good &= north_star()
    sys.exit(0 if good else 1)
