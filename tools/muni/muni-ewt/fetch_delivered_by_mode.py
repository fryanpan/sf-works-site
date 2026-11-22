"""Fetch SFMTA's share of scheduled service delivered by mode and month into data/muni-ewt/lever/delivered_by_mode.csv, for Upgrade a Bus Line's fill-missed-trips fix.

Source: SFMTA transtat, Goal 2 dashboards, Service Delivered table,
https://transtat.sfmta.com/t/public/views/Goal2Dashboards/ServiceDeliveryTable.csv: one row per mode per day (columns
Fiscal Year, Mode, Month, Service Delivered (%)), four modes (Motor Coach, Trolley Coach, Light Rail (LRV), Historic
Streetcar), July 2014 on. SFMTA counts revenue hours delivered over scheduled; the month's figure here is the plain
mean of its daily rows, as the pre-send verifier took it (2026-11-15), since the table gives no hours to weight by.
optimizer_build.py (window_delivery) reads the motor and trolley coach figures over the page's three months to tell
untracked trips that ran from trips that didn't; the lever model (lever_car_miles.py, lever_roi.py) reads them over
its own twelve.

--update. The view has no change marker (no Last-Modified or ETag), so the whole table, about 1 MB, is re-read every
run and the file replaced only when its rows differ. A read that fails is retried after 5, 20 and 60 seconds
(lib/fetch.py); one that still fails on a 5xx or a timeout keeps the last good file, records
transtat:muni-delivered-by-mode failed in data/pipeline-state/sources.json and exits 0, so the builds run on the last
good file; any other read error exits 2.
Checks, before the file is replaced: at least MIN_ROWS daily rows; both coach modes present; every daily value between
0 and 1; no mode-month the previous file held is gone; the newest month no earlier than the previous file's. A
failure keeps the old file and exits 1. The orchestrator's muni-delivered-by-mode checks run on the file afterwards.
Idempotent: rows sorted by month and mode, no run date written. A month still in progress is written with the days it
has so far ("days"), and moves until the month closes; optimizer_build.py reads only months that have closed.
Output: month (YYYY-MM), mode (motor, trolley, lrv, streetcar), delivered (0 to 1), days.
Usage: python3 tools/muni/muni-ewt/fetch_delivered_by_mode.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections, csv, datetime as dt, io, os, sys

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "muni-ewt", "lever", "delivered_by_mode.csv")
URL = "https://transtat.sfmta.com/t/public/views/Goal2Dashboards/ServiceDeliveryTable.csv"
MARKER = "transtat:muni-delivered-by-mode"
MODES = {"Motor Coach": "motor", "Trolley Coach": "trolley", "Light Rail (LRV)": "lrv", "Historic Streetcar": "streetcar"}
MIN_ROWS = 15000
sys.path.insert(0, paths.LIB)
from lib import pipeline_state  # noqa: E402
from lib.fetch import read, upstream_failed  # noqa: E402


def parse(raw):
    """({(month, mode): [daily shares]}, errors) from the table's CSV text."""
    rows = list(csv.DictReader(io.StringIO(raw)))
    seen = {r.get("Mode") for r in rows}
    errors = []
    if len(rows) < MIN_ROWS:
        errors.append(f"{len(rows)} daily rows, under {MIN_ROWS}")
    if not {"Motor Coach", "Trolley Coach"} <= seen:
        errors.append(f"modes {sorted(m for m in seen if m)}: a coach mode is missing")
    acc = collections.defaultdict(list)
    for r in rows:
        if not (r.get("Service Delivered (%)") or "").strip():
            continue  # a day with no figure (blank in SFMTA's table) is left out, not read as zero
        if r.get("Mode") not in MODES:
            errors.append(f"a mode this script doesn't know: {r.get('Mode')!r}")
            continue
        try:
            m = dt.datetime.strptime(r["Month"], "%B %Y").strftime("%Y-%m")
            v = float(r["Service Delivered (%)"])
        except (KeyError, ValueError) as e:
            errors.append(f"unreadable row {r}: {e}")
            continue
        if not 0 <= v <= 1.0001:  # a streetcar day can run 12% (January 2016)
            errors.append(f"{m} {r['Mode']}: daily share {v} out of range")
        acc[(m, MODES[r["Mode"]])].append(v)
    return acc, errors


def text_of(acc):
    out = io.StringIO()
    w = csv.writer(out)  # the csv module's own line ends (CRLF), as the file has had since its first read
    w.writerow(["month", "mode", "delivered", "days"])
    for (m, mode), v in sorted(acc.items()):
        w.writerow([m, mode, f"{sum(v) / len(v):.5f}", len(v)])
    return out.getvalue()


def main():
    try:
        raw = read(URL, headers={"User-Agent": "sf-works"}, timeout=120).decode("utf-8-sig")
    except Exception as e:
        upstream_failed(MARKER, e, step="muni-delivered-by-mode")
    acc, errors = parse(raw)
    prev = {(r["month"], r["mode"]) for r in csv.DictReader(open(OUT))} if os.path.exists(OUT) else set()
    gone = sorted(prev - set(acc))
    if gone:
        errors.append(f"{len(gone)} mode-months the previous file held are gone, the first {gone[0]}")
    if prev and acc and max(m for m, _ in acc) < max(m for m, _ in prev):
        errors.append(f"newest month {max(m for m, _ in acc)}, the previous file reached {max(m for m, _ in prev)}")
    if errors:
        for e in errors[:10]:
            print("check failed:", e, file=sys.stderr)
        sys.exit(1)
    text = text_of(acc)
    moved = not os.path.exists(OUT) or open(OUT, newline="").read() != text
    if moved:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT + ".tmp", "w", newline="") as f:
            f.write(text)
        os.replace(OUT + ".tmp", OUT)
        print("wrote", os.path.relpath(OUT, ROOT), len(acc), "mode-months through", max(m for m, _ in acc))
    else:
        print("unchanged", os.path.relpath(OUT, ROOT))
    pipeline_state.record(MARKER, "changed" if moved else "unchanged", version=max(m for m, _ in acc))


if __name__ == "__main__":
    main()
