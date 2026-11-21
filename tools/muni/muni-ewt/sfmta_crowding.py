"""Fetch SFMTA's published percent of Muni trips crowded, by route and month, for the line optimizer's crowding baseline.

Bryan, 2026-11-14: "use SFMTA's crowding figures but mention
we'll have more accurate ones in a few weeks". So the optimizer's "today" for crowding is SFMTA's own published figure.

Source: SFMTA, "Percent of daily Muni trips crowded by route and month",
https://www.sfmta.com/reports/percent-daily-muni-trips-crowded-route-and-month, whose route CSV is
https://transtat-public.sfmta.com/t/public/views/CrowdingbyRoute/CrowdingbyRoute.csv (columns "Month of Month",
ROUTE_NAME, "Prc Trips at Crowding Threshold"; whole percents, blank where SFMTA has no figure). SFMTA's definition,
from the report page: "Percentage of trips where vehicles are above capacity for 10% or more of the stops", method
"SUM (Trips at or above the 10% Threshold) / COUNT (Trips)", monthly, from automatic passenger counters, and it "does
not include historic streetcar or cable car ridership" [primary — read 2026-11-14]. As read on 2026-11-14 it runs
May 2022 to May 2026 for 63 routes.

Incremental (--update): the source carries no change marker (no Last-Modified or ETag; Cache-Control private), so the
bound is the whole file, about 110 KB, re-read each run and kept only when it parses and passes the checks. A failed
or short read keeps the cached copy (.cache/sfmta-crowding/CrowdingbyRoute.csv). The output is rewritten only when its
bytes change, so a run with no new month changes no file.

The date the current content was read goes to data/muni-ewt/optimizer/sfmta_crowding_read.json, rewritten only when
the content changes; each run's check date goes to the gitignored data/pipeline-state/sfmta-crowding.json. A line the
optimizer uses that had a figure in each of the newest three months and loses it in a new file prints a warning.
Output: data/muni-ewt/optimizer/sfmta_crowding.csv, one row a route, name and month with a figure: route (SFMTA's code,
leading zeros dropped, so "038R" is "38R"), route_name, month (YYYY-MM), pct (percent of trips crowded). Sorted.
Checks, run before writing; a failure exits 1 and keeps the old file: at least MIN_ROWS rows and no fewer than the
file before; route, name and month unique (SFMTA lists the 6 under two names in May to July 2025), and one figure a
month for each optimizer line; every pct a number from 0 to 100; months parse and the newest is no older than
the file before; at least MIN_LINES of the optimizer's lines (data/muni-ewt/lever/out/car_miles_lines.csv) have a
figure in each of the newest three months.
Usage: ~/.venvs/sf-works-geo/bin/python -I tools/muni/muni-ewt/sfmta_crowding.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, io, json, os, sys, urllib.request

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import pipeline_state, stable  # noqa: E402
MARKER = "transtat:sfmta-crowding"

URL = "https://transtat-public.sfmta.com/t/public/views/CrowdingbyRoute/CrowdingbyRoute.csv"
CACHE = os.path.join(ROOT, ".cache", "sfmta-crowding", "CrowdingbyRoute.csv")
OUT = os.path.join(ROOT, "data", "muni-ewt", "optimizer", "sfmta_crowding.csv")
READ = os.path.join(ROOT, "data", "muni-ewt", "optimizer", "sfmta_crowding_read.json")
STATE = os.path.join(ROOT, "data", "pipeline-state", "sfmta-crowding.json")
NEWEST = 3   # the optimizer's baseline months
LINES = os.path.join(ROOT, "data", "muni-ewt", "lever", "out", "car_miles_lines.csv")
FIELDS = ["route", "route_name", "month", "pct"]
MIN_ROWS = 2500
MIN_LINES = 20
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}


def fetch():
    """Download the route CSV to the cache; keep the cached copy on a failed or short read. Returns True on success."""
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "sf-works-pipeline"})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
    except Exception as e:  # noqa: BLE001
        print(f"sfmta_crowding: read failed, keeping the cached copy: {e}")
        pipeline_state.record(MARKER, "failed", detail=f"read failed: {e}")
        return False
    old = os.path.getsize(CACHE) if os.path.exists(CACHE) else 0
    if not body.startswith(b"Month of Month") or len(body) < 0.9 * old:
        print(f"sfmta_crowding: short or unexpected read ({len(body)} bytes against {old}), keeping the cached copy")
        pipeline_state.record(MARKER, "failed", detail=f"short read, {len(body)} bytes against {old}")
        return False
    if not os.path.exists(CACHE) or open(CACHE, "rb").read() != body:
        with open(CACHE + ".part", "wb") as f:
            f.write(body)
        os.replace(CACHE + ".part", CACHE)
    return True


def parse(text):
    """(rows, errors): one row a route and month with a figure, sorted."""
    rows, errors, seen = [], [], set()
    for r in csv.DictReader(io.StringIO(text)):
        name, month, pct = r.get("ROUTE_NAME", "").strip(), r.get("Month of Month", "").strip(), (r.get("Prc Trips at Crowding Threshold") or "").strip()
        if not pct:
            continue
        mname, _, year = month.partition(" ")
        if mname not in MONTHS or not year.isdigit():
            errors.append(f"month {month!r} doesn't parse")
            continue
        code, _, label = name.partition(" - ")
        route = code.strip().lstrip("0") or code.strip()
        try:
            v = float(pct.rstrip("%"))
        except ValueError:
            errors.append(f"{route} {month}: pct {pct!r} isn't a number")
            continue
        if not 0 <= v <= 100:
            errors.append(f"{route} {month}: pct {v} outside 0 to 100")
        key = (route, " ".join(label.split()), f"{int(year):04d}-{MONTHS[mname]:02d}")
        if key in seen:
            errors.append(f"{key} appears twice")
        seen.add(key)
        rows.append({"route": route, "route_name": key[1], "month": key[2], "pct": f"{v:g}"})
    rows.sort(key=lambda x: (x["route"], x["month"], x["route_name"]))
    return rows, errors


def check(rows, old_rows, wanted):
    errors = []
    if len(rows) < max(MIN_ROWS, len(old_rows)):
        errors.append(f"{len(rows)} rows, under {max(MIN_ROWS, len(old_rows))}")
    months = sorted({r["month"] for r in rows})
    if not months:
        return errors + ["no months"]
    if old_rows and months[-1] < max(r["month"] for r in old_rows):
        errors.append(f"newest month {months[-1]} is older than the file before")
    if months[-1] > dt.date.today().strftime("%Y-%m"):
        errors.append(f"newest month {months[-1]} is in the future")
    for m in months[-3:]:
        have = {r["route"] for r in rows if r["month"] == m}
        n = sum(1 for w in wanted if w in have)
        for w in wanted:
            if sum(1 for r in rows if r["month"] == m and r["route"] == w) > 1:
                errors.append(f"{m}: line {w} has more than one figure")
        if n < MIN_LINES:
            errors.append(f"{m}: {n} of the optimizer's {len(wanted)} lines have a figure, under {MIN_LINES}")
    return errors


def nulled(rows, old_rows, wanted):
    """Optimizer lines that had a figure in each of the old file's newest NEWEST months but don't in the new file's."""
    def full(rs):
        months = sorted({r["month"] for r in rs})[-NEWEST:]
        have = {}
        for r in rs:
            if r["month"] in months:
                have.setdefault(r["route"], set()).add(r["month"])
        return {w for w in wanted if len(have.get(w, ())) == len(months)}
    return sorted(full(old_rows) - full(rows)) if old_rows else []


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv):
    fetched = fetch() if "--update" in argv else False
    if not os.path.exists(CACHE):
        print("sfmta_crowding: no cached copy; run with --update")
        return 1
    with open(CACHE, encoding="utf-8-sig") as f:
        rows, errors = parse(f.read())
    old_rows = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old_rows = list(csv.DictReader(f))
    if os.path.exists(LINES):
        with open(LINES, encoding="utf-8") as f:
            wanted = sorted(r["line"] for r in csv.DictReader(f))
    else:
        # Without the line optimizer's outputs (main carries the dashboard, not the optimizer), the lines that must
        # have a figure are the bus lines the Muni dashboard lists (route_type 3 in ref/route_types.csv).
        with open(os.path.join(ROOT, "data", "muni-ewt", "ref", "route_types.csv"), encoding="utf-8") as f:
            bus = {r["route"] for r in csv.DictReader(f) if r["route_type"] == "3"}
        with open(os.path.join(ROOT, "site", "data", "muni.json"), encoding="utf-8") as f:
            wanted = sorted(l for l in json.load(f)["lines"] if l in bus)
    errors += check(rows, old_rows, wanted)
    if errors:
        for e in errors[:20]:
            print(f"sfmta_crowding: FAIL {e}")
        print("sfmta_crowding: kept the previous sfmta_crowding.csv")
        return 1
    for w in nulled(rows, old_rows, wanted):
        print(f"sfmta_crowding: WARN line {w} had a figure in each of the newest {NEWEST} months and no longer does; "
              "the optimizer will show no crowding for it")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    changed = stable.write_text(OUT, to_csv(rows))
    # the date this content was read: written only when the content changes, so a rerun leaves it alone; the date of
    #   every check goes to the gitignored pipeline state
    today = dt.date.today().isoformat()
    if changed or not os.path.exists(READ):
        stable.write_text(READ, json.dumps({"read": today}) + "\n")
    with open(READ, encoding="utf-8") as f:
        read = json.load(f)["read"]
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"checked": dt.datetime.now().isoformat(timespec="seconds"), "read": read,
                   "changed": changed, "newestMonth": max(r["month"] for r in rows)}, f, indent=1)
    months = sorted({r["month"] for r in rows})
    if fetched:  # a failed read was recorded failed in fetch(), so freshness ages the source from its last good read
        pipeline_state.record(MARKER, "changed" if changed else "unchanged", version=months[-1])
    print(f"sfmta_crowding: {len(rows)} route-months, {len({r['route'] for r in rows})} routes, {months[0]} to {months[-1]}; "
          f"{'wrote' if changed else 'unchanged'} {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
