"""Fetch SFMTA's yearly Muni rider satisfaction (share rating Muni service overall good or excellent) into data/muni-ewt/satisfaction.csv.

Source: SFMTA, "Customer rating: Overall customer satisfaction with Muni"
(https://www.sfmta.com/reports/customer-rating-overall-customer-satisfaction-muni), from the Muni Rider Survey. Its
download is the Tableau view's CSV at transtat.sfmta.com, two columns: "Year of Year" and "Rating 1" (a share, 0 to 1).
The page's definition: respondents rating Muni service overall good or excellent, divided by all responses,
systemwide, reported annually. Its target: "Achieve a 2% increase per year over FY17 baseline". Its note: "No survey
conducted in 2020." Some other years have no survey either (2008, 2009, 2013, 2023 as first read on 2026-11-10).

--update. The view has no change marker and is about 200 bytes, so it's re-read every run and the file replaced only
when its rows differ. A read that fails is retried after 5, 20 and 60 seconds (lib/fetch.py); one that
still fails on a 5xx or a timeout keeps the last good file, records transtat:muni-satisfaction failed in
data/pipeline-state/sources.json and exits 0, so the builds run on the last good file; any other read error exits 2.
Checks, before the file is replaced: at least 15 rows and no fewer than the previous file; years unique, from 2000 to
this year, and 2020 absent; every value between 0 and 100 percent. A failure keeps the old file and exits 1.
Idempotent: rows sorted by year, no run date written.
Usage: python3 tools/muni/muni-ewt/fetch_satisfaction.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime, io, os, sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "muni-ewt", "satisfaction.csv")
URL = "https://transtat.sfmta.com/t/public/views/Goal2Dashboards/2_2_5Table.csv"
MARKER = "transtat:muni-satisfaction"
sys.path.insert(0, paths.LIB)
from lib import pipeline_state  # noqa: E402
from lib.fetch import read, upstream_failed  # noqa: E402

try:
    raw = read(URL, headers={"User-Agent": "sf-works"}, timeout=60).decode("utf-8-sig")
except Exception as e:
    upstream_failed(MARKER, e, step="muni-satisfaction")

rows, errors = {}, []
for r in csv.DictReader(io.StringIO(raw)):
    y, v = (r.get("Year of Year") or "").strip(), (r.get("Rating 1") or "").strip()
    if not y or not v:
        errors.append(f"blank cell in {r}")
        continue
    y, pct = int(y), round(100 * float(v), 1)
    if y in rows:
        errors.append(f"{y} twice")
    if not 0 <= pct <= 100:
        errors.append(f"{y}: {pct}% out of range")
    rows[y] = pct
this_year = datetime.date.today().year
prev = sum(1 for _ in csv.DictReader(open(OUT))) if os.path.exists(OUT) else 0
if len(rows) < max(15, prev):
    errors.append(f"{len(rows)} rows, previous file had {prev}")
if rows and (min(rows) < 2000 or max(rows) > this_year):
    errors.append(f"years {min(rows)} to {max(rows)} out of range")
if 2020 in rows:
    errors.append("a 2020 value, though SFMTA says no survey was conducted in 2020")
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
text = "year,good_or_excellent_pct\n" + "".join(f"{y},{v:g}\n" for y, v in sorted(rows.items()))
moved = not os.path.exists(OUT) or open(OUT).read() != text
if moved:
    open(OUT, "w").write(text)
    print("wrote", OUT, len(rows), "years,", min(rows), "to", max(rows))
else:
    print("unchanged", OUT)
pipeline_state.record(MARKER, "changed" if moved else "unchanged", version=str(max(rows)))
