"""Fetch SFMTA's average daily Muni boardings by route and month into data/muni-ewt/ridership.csv.

Source: SFMTA, "Average Daily Muni Boardings by Route and Month, Pre-pandemic to Present"
(https://www.sfmta.com/reports/average-daily-muni-boardings-route-and-month-pre-pandemic-present), whose download is
the Tableau view's CSV at transtat.sfmta.com. One row per month, route, service category and day type (Weekday,
Saturday, Sunday), from January 2019. A blank boardings cell (a route that didn't run) is left out.

Published total. Summed over every route, the weekday rows reproduce SFMTA's own systemwide "Muni average weekday
boardings" (DataSF kc49-udxn, measure 428). The check below asks for that to within 1% in each of the newest six
months both carry; it read 526,100 against 526,000 for August 2026 when first run on 2026-11-09.

--update. The view has no change marker, so the CSV (about 1 MB) is re-read and the file replaced only when its rows
differ. A read that fails is retried after 5, 20 and 60 seconds (lib/fetch.py); one that still fails on a
5xx or a timeout keeps the last good file, records transtat:muni-ridership failed in data/pipeline-state/sources.json
and exits 0, so the builds run on the last good file; any other read error exits 2. SFMTA's measure 428 itself goes to
data/muni-ewt/weekday_boardings_published.csv: the pages treat the months after its newest as provisional, because the
newest month of the route file can move a lot once it settles (October 2026, read 10 days after it ended, sat 7% below
October 2025 on almost every route at once, while September had been 2% above).
Checks, before the file is replaced: at least 10,000 rows; (month, route, day type) unique; boardings between 0 and
200,000; months from 2019-01 to this month; no fewer months than the previous file; the 428 reproduction above. A
failure keeps the old file and exits 1. Idempotent: rows sorted, no run date written.
Usage: python3 tools/muni/muni-ewt/fetch_ridership.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime, io, json, os, sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "muni-ewt", "ridership.csv")
PUBOUT = os.path.join(ROOT, "data", "muni-ewt", "weekday_boardings_published.csv")
sys.path.insert(0, paths.LIB)
from lib import pipeline_state  # noqa: E402
from lib.fetch import read, upstream_failed  # noqa: E402
URL = "https://transtat.sfmta.com/t/public/views/RidershipbyRoute/RidershipbyRouteTableDownload.csv"
PUB = ("https://data.sf.gov/resource/kc49-udxn.json?$select=calendar_month,actual"
       "&$where=measure_code='428'&$order=calendar_month&$limit=5000")
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}
MARKER = "transtat:muni-ridership"
fetch = lambda url: read(url, headers={"User-Agent": "sf-works"}, timeout=120)

try:
    raw = fetch(URL).decode("utf-8-sig")
    pub = json.loads(fetch(PUB))
except Exception as e:
    upstream_failed(MARKER, e, step="muni-ridership")

rows, errors = {}, []
for r in csv.DictReader(io.StringIO(raw)):
    v = (r.get("Average Daily Boardings") or "").replace(",", "").strip()
    if not v:
        continue
    name, year = r["Month"].rsplit(" ", 1)
    m = f"{int(year)}-{MONTHS[name]:02d}"
    k = (m, r["Route"].strip(), r["Service Day of the Week"].strip())
    if k in rows:
        errors.append(f"{k} twice")
    b = float(v)
    if not 0 <= b <= 200000:
        errors.append(f"{k}: {b} boardings out of range")
    rows[k] = (r["Service Category"].strip(), b)
today = datetime.date.today().strftime("%Y-%m")
months = sorted({k[0] for k in rows})
if len(rows) < 10000:
    errors.append(f"{len(rows)} rows")
if months and (months[0] < "2019-01" or months[-1] > today):
    errors.append(f"months {months[0]} to {months[-1]} out of range")
prev = len({r["month"] for r in csv.DictReader(open(OUT))}) if os.path.exists(OUT) else 0
if len(months) < prev:
    errors.append(f"{len(months)} months, previous file had {prev}")
weekday = {}
for (m, _, d), (_, b) in rows.items():
    if d == "Weekday":
        weekday[m] = weekday.get(m, 0) + b
published = {p["calendar_month"][:7]: float(p["actual"]) for p in pub if p.get("actual") not in (None, "", "-9999")}
both = sorted(set(weekday) & set(published))[-6:]
if len(both) < 3:
    errors.append(f"only {len(both)} months to compare with kc49-udxn 428")
for m in both:
    if abs(weekday[m] / published[m] - 1) > 0.01:
        errors.append(f"{m}: weekday sum {weekday[m]:.0f} against SFMTA's published {published[m]:.0f}")
if errors:
    for e in errors:
        print("check failed:", e, file=sys.stderr)
    sys.exit(1)
text = "month,route,category,day,boardings\n" + "".join(
    f'{m},"{route}",{c},{d},{b:g}\n' for (m, route, d), (c, b) in sorted(rows.items()))
moved = not os.path.exists(OUT) or open(OUT).read() != text
if moved:
    open(OUT, "w").write(text)
    print("wrote", OUT, len(rows), "rows,", months[0], "to", months[-1])
else:
    print("unchanged", OUT)
pipeline_state.record(MARKER, "changed" if moved else "unchanged", version=months[-1])
# SFMTA's own systemwide figure, kept beside it: the pages count a month as settled once SFMTA has published it there.
ptext = "month,weekday\n" + "".join(f"{m},{v:g}\n" for m, v in sorted(published.items()))
if not os.path.exists(PUBOUT) or open(PUBOUT).read() != ptext:
    open(PUBOUT, "w").write(ptext)
    print("wrote", PUBOUT, len(published), "months")
for m in both:
    print(f"  {m}: weekday sum {weekday[m]:,.0f}, SFMTA published {published[m]:,.0f}")
