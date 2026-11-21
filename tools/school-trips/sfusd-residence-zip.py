#!/usr/bin/env python3
"""Read SFUSD's Public Data Dashboard for how many of each school's students live in each SF zip code, by grade span, 2025-26.

The dashboard (Tableau Public workbook SFUSDPublicDataDashboard, story point
"Enrollment Overview (2025-26)") draws a "Site-Level Enrollment by SF Zip Code"
map for one school and one grade span at a time. Its data download is turned
off ("allowDataAccess": false), so this script drives the dashboard in headless
Chrome: for each grade span it opens the School filter, selects each school in
turn, and reads the map's marks (zip code and student count) and the site's
total enrolment out of Tableau's own filter response. Nothing is computed here
that the dashboard does not draw.

What the dashboard leaves out, and so does this file: charter schools; any zip
with fewer than five students at that school and grade span (suppressed, so
the zip counts sum to less than the site total); students living outside SF.
`placed` is the sum of the zip counts and `enrolled` the dashboard's site
total, so `enrolled - placed` is the suppressed and out-of-city remainder.

Writes data/sfusd-residence/zip-by-school-2025-26.csv, one row per school,
grade span and zip, sorted, and schools-2025-26.csv, one row per school and
grade span with its enrolled total, placed total and zip count (this keeps the
schools whose every zip is suppressed, which have no zip rows). A one-off read (pipeline/README.md): no
page reads it on a schedule yet, so it has no --update. The dashboard covers
one school year; when SFUSD republishes it for 2026-27 this becomes a new file.

Needs Playwright and an installed Chrome:
    uv run --with playwright python tools/school-trips/sfusd-residence-zip.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://public.tableau.com/views/SFUSDPublicDataDashboard/Story1?:embed=y&:showVizHome=no"
OUT = Path(paths.ROOT) / "data/sfusd-residence/zip-by-school-2025-26.csv"
OUT_SCHOOLS = OUT.with_name("schools-2025-26.csv")
FILTER_CMD = "categorical-filter-by-index"
OPTION = ".tabMenuItemName, .FIText, [role=option]"


def parse_bootstrap(text):
    """Split Tableau's 'len;json len;json' bootstrap body into its JSON parts."""
    parts, i = [], 0
    while i < len(text):
        m = re.match(r"(\d+);", text[i:])
        n = int(m.group(1))
        s = i + len(m.group(0))
        parts.append(json.loads(text[s:s + n]))
        i = s + n
    return parts


def find(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from find(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from find(v, key)


class DataDictionary:
    """Tableau sends column values in numbered segments, and marks point into their concatenation by index.

    A later response can resend a segment with new values, replacing the old
    one under the same number (it does on a grade-span change), or list a
    number with null to mean "unchanged". So keep segments by number and
    concatenate them in order when reading.
    """

    def __init__(self):
        self.segs = {}

    def add(self, obj):
        for segs in find(obj, "dataSegments"):
            for k, seg in segs.items():
                if seg is not None:
                    self.segs[int(k)] = seg["dataColumns"]

    @property
    def cols(self):
        out = {}
        for k in sorted(self.segs):
            for c in self.segs[k]:
                out.setdefault(c["dataType"], []).extend(c["dataValues"])
        return out

    def sheet(self, obj, name):
        for zones in find(obj, "zones"):
            for z in zones.values():
                if z.get("worksheet") != name:
                    continue
                vd = z.get("presModelHolder", {}).get("visual", {}).get("vizData")
                if not vd:
                    continue
                res, cols = {}, self.cols
                for c in vd["paneColumnsData"]["vizDataColumns"]:
                    if not c.get("fieldCaption"):
                        continue
                    for pi, ci in zip(c["paneIndices"], c["columnIndices"]):
                        pc = vd["paneColumnsData"]["paneColumnsList"][pi]["vizPaneColumns"][ci]
                        arr = cols[c["dataType"]]
                        idx = pc.get("aliasIndices") or pc.get("valueIndices") or []
                        res[c["fieldCaption"]] = [arr[i] if i >= 0 else cols["cstring"][-i - 1] for i in idx]
                return res
        return None


async def choose(pg, combo_text, item, D, responses):
    """Open the dropdown showing combo_text, click item, and return the last filter response that followed.

    One click can trigger more than one filter command, and a response from an
    earlier click can still be in flight, so wait for the page to settle and
    take the newest response, feeding every one to D in arrival order.
    """
    await pg.locator(".tabComboBoxName", has_text=combo_text).first.click()
    await pg.wait_for_timeout(800)
    before = len(responses)
    await pg.locator(OPTION).get_by_text(item, exact=True).first.click()
    for _ in range(120):
        await pg.wait_for_timeout(500)
        if len(responses) > before and responses[-1]["done"]:
            await pg.wait_for_timeout(1500)
            if responses[-1]["done"]:
                break
    else:
        raise TimeoutError(f"no filter response after choosing {item}")
    good = [r["body"] for r in responses[before:] if r["body"] is not None]
    if not good:
        raise RuntimeError(f"no readable filter response after choosing {item}")
    for body in good:
        D.add(body)
    return good[-1]


async def dropdown_items(pg, combo_text):
    await pg.locator(".tabComboBoxName", has_text=combo_text).first.click()
    await pg.wait_for_timeout(1500)
    items = await pg.locator(OPTION).all_inner_texts()
    await pg.keyboard.press("Escape")
    await pg.wait_for_timeout(500)
    return [i.strip() for i in items if i.strip()]


async def run(limit):
    rows, totals = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        pg = await browser.new_page(viewport={"width": 1400, "height": 900})
        boot = {}

        async def on_resp(r):
            if "bootstrapSession" in r.url:
                boot["text"] = await r.text()

        responses = []

        async def on_filter(r):
            if FILTER_CMD in r.url:
                slot = {"done": False, "body": None}
                responses.append(slot)
                try:
                    text = await r.text()
                    slot["body"] = json.loads(text) if text.strip() else None
                except Exception as e:  # an evicted or empty body: skip it, keep the newest good one
                    print(f"   unreadable filter response: {e}", file=sys.stderr)
                slot["done"] = True

        pg.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        pg.on("response", lambda r: asyncio.ensure_future(on_filter(r)))
        await pg.goto(URL)
        await pg.wait_for_timeout(12000)
        D = DataDictionary()
        for part in parse_bootstrap(boot["text"]):
            D.add(part)

        span_now = "Grades TK-5"  # the dashboard's default selection
        spans = [s for s in await dropdown_items(pg, span_now) if s.startswith("Grades")]
        print("grade spans:", spans, file=sys.stderr)
        school_now = "SFUSD"
        for span in spans:
            if span != span_now:
                # The span list only offers the selected school's spans, so reset the school first.
                if school_now != "SFUSD":
                    await choose(pg, school_now, "SFUSD", D, responses)
                    school_now = "SFUSD"
                await choose(pg, span_now, span, D, responses)
                span_now = span
            schools = [s for s in await dropdown_items(pg, school_now) if s != "SFUSD"]
            if limit:
                schools = schools[:limit]
            print(f"{span}: {len(schools)} schools", file=sys.stderr)
            for school in schools:
                body = await choose(pg, school_now, school, D, responses)
                school_now = school
                zmap = D.sheet(body, "Site Map") or {}
                enr = D.sheet(body, "Site Enr") or {}
                zips = zmap.get("Student Residence Zip", [])
                ns = zmap.get("SUM(N)", [])
                enrolled = (enr.get("SUM(N)") or [None])[0]
                for z, n in zip(zips, ns):
                    rows.append({"grade_span": span.removeprefix("Grades "), "school": school, "zip": z, "students": n})
                totals.append({"grade_span": span.removeprefix("Grades "), "school": school,
                               "enrolled": enrolled, "placed": sum(ns), "zips": len(zips)})
                print(f"  {school}: enrolled {enrolled}, placed {sum(ns)} in {len(zips)} zips", file=sys.stderr)
        await browser.close()
    return rows, totals


def check(rows, totals):
    """Quality checks that must pass before the file is written."""
    problems = []
    if len(totals) < 100:
        problems.append(f"only {len(totals)} school-span reads, expected well over 100")
    keys = [(r["grade_span"], r["school"], r["zip"]) for r in rows]
    if len(keys) != len(set(keys)):
        problems.append("duplicate school, span and zip rows")
    for t in totals:
        if t["enrolled"] is None:
            problems.append(f"{t['school']} {t['grade_span']}: no site total")
        elif t["placed"] > t["enrolled"]:
            problems.append(f"{t['school']} {t['grade_span']}: zips sum to {t['placed']}, more than {t['enrolled']} enrolled")
    for r in rows:
        if not re.fullmatch(r"94\d{3}", str(r["zip"])) or not isinstance(r["students"], int) or r["students"] < 5:
            problems.append(f"bad row {r}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=0, help="schools per grade span, for a quick test")
    args = ap.parse_args()
    rows, totals = asyncio.run(run(args.limit))
    problems = [] if args.limit else check(rows, totals)
    if problems:
        print("Quality checks failed, nothing written:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
        sys.exit(1)
    if args.limit:
        print(json.dumps(totals, indent=1))
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tot = {(t["grade_span"], t["school"]): t for t in totals}
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, ["grade_span", "school", "enrolled", "placed", "zip", "students"])
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["grade_span"], r["school"], r["zip"])):
            t = tot[(r["grade_span"], r["school"])]
            w.writerow({**r, "enrolled": t["enrolled"], "placed": t["placed"]})
    with OUT_SCHOOLS.open("w", newline="") as f:
        w = csv.DictWriter(f, ["grade_span", "school", "enrolled", "placed", "zips"])
        w.writeheader()
        for t in sorted(totals, key=lambda t: (t["grade_span"], t["school"])):
            w.writerow(t)
    print(f"wrote {OUT} ({len(rows)} rows, {len(totals)} school-span reads)", file=sys.stderr)


if __name__ == "__main__":
    main()
