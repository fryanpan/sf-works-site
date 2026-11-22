"""Each Muni line's timetable month by month, from 511's historic schedules: the most buses in service at once on a
weekday, and the gap between buses weekdays, weekday evenings, Saturdays and Sundays.

For the Upgrade a Bus Line page's history (optimizer_build.py, "History"; Bryan, 2026-11-16
and the 44: "show changes over time in number of busses serving the line, and also changes over time in scheduled
frequency during daytime and off hours"). Runs on the VM, where the months live (~/muni-511/history/
regional-<YYYY-MM>-so-sf: trips.csv.gz, stop_times.csv.gz, calendar_dates.csv.gz, Muni rows only).
On each service date, with optimizer_build.py's own rules for SFMTA's current timetable, so the newest month here and
the line's basic timetable on the page agree (optimizer_build checks it):
  buses  peak_buses(): a block (one bus's day) is on a line from a trip's first departure to the next trip's first
         departure in the block when that comes within LAYOVER_GAP, so layover counts, else to the trip's last
         arrival; buses counted minute by minute, the most at once;
  gaps   departures() and schedule(): every departure at each direction's busiest stop (the most trips that day, a
         trip's last stop and a loop's second call not counted; ties to the stop nearest the start, then the lowest
         stop_id), in the direction with more departures there (direction 0 on a tie); the median gap in minutes over
         SCHED_WIN's hours, weekdays 7 to 19, evenings 20 to 23, Saturdays and Sundays 7 to 19.
A month's figure is the median over its dates of that kind: Monday to Friday leaving out holidays (a date whose
scheduled Muni trips are under 90% of the month's weekday median, ewt_month.py's rule), Saturdays, Sundays. Gaps keep
one decimal (the page rounds). A month whose trips carry no block_id (2022-08 to 2022-12, rebuilt from SFMTA's own
GTFS by make_sched.py) has gaps but no buses.
Output: CSV with line (511's route_id without "SF:"), month, buses, day, eve, sat, sun, weekdays (dates counted).
Checks: at least 40 lines a month with a weekday gap; a failure prints and exits 1, and no file is written.

--update, the muni-timetable-history step of the site's scheduled refresh, run on the VM itself after the muni-511 step
has fetched any new month. Change marker: a month directory with pull_all.py's DONE file that is later than the newest
month in data/muni-ewt/optimizer/timetable_month.csv. Only those months are read (one month's stop times, about 20 MB
gzipped, a few seconds); their rows are added and no earlier row is touched, so a run with no new month writes
nothing. Not on the VM (no ~/muni-511/history, or $MUNI_511_ROOT/history): says so and exits 0, the last good file
kept. An error reading a month keeps the file, records 511:muni-timetable-history failed in
data/pipeline-state/sources.json and exits 0, so the builds run on the last good file and Upgrade a Bus Line waits
for the month (optimizer_build.py, "Waiting"); a month that reads but fails the check above exits 1 with the file
kept. The orchestrator's muni-timetable-history checks run on the file afterwards.
Usage: PYTHONPATH=pylib python3 timetable_month.py <history dir> <out.csv>      every month, from nothing
       python3 tools/muni/muni-ewt/timetable_month.py --update                      new months only, into the tracked file
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, glob, os, statistics, sys

import duckdb

ROOT = paths.ROOT
TRACKED = os.path.join(ROOT, "data", "muni-ewt", "optimizer", "timetable_month.csv")
MARKER = "511:muni-timetable-history"
FIELDS = ["line", "month", "buses", "day", "eve", "sat", "sun", "weekdays"]

LAYOVER_GAP = 3600  # seconds, optimizer_build.py's and lever_roi.py's rule
WIN = {"day": (7, 19), "eve": (20, 23), "sat": (7, 19), "sun": (7, 19)}  # optimizer_build.SCHED_WIN


def median_gap(ts, win):
    a = [t for t in ts if win[0] * 3600 <= t < win[1] * 3600]
    g = sorted(q - p for p, q in zip(a, a[1:]))
    return statistics.median(g) / 60 if g else None


def month_rows(d):
    """(rows, error or None) for one month's directory, regional-<YYYY-MM>-so-sf."""
    rows, error = [], None
    month = os.path.basename(d)[9:16]
    con = duckdb.connect()
    con.execute("SET threads=4")
    rd = lambda n: f"read_csv('{os.path.join(d, n)}', header=true, all_varchar=true)"
    has_block = "block_id" in [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {rd('trips.csv.gz')}").fetchall()]
    sec = lambda c: f"(CAST(split_part({c},':',1) AS INT)*3600 + CAST(split_part({c},':',2) AS INT)*60 + CAST(split_part({c},':',3) AS INT))"
    con.execute(f"""CREATE TABLE cal AS SELECT service_id, date sdate, dayofweek(strptime(date, '%Y%m%d')) w
      FROM {rd('calendar_dates.csv.gz')} WHERE exception_type = '1'""")
    con.execute(f"""CREATE TABLE tr AS SELECT replace(route_id, 'SF:', '') r, {"block_id" if has_block else "NULL"} b,
      service_id, direction_id dir, trip_id FROM {rd('trips.csv.gz')}""")
    con.execute(f"""CREATE TABLE st AS SELECT trip_id, stop_id, CAST(stop_sequence AS INT) seq,
        {sec("coalesce(nullif(departure_time,''), arrival_time)")} t,
        {sec("coalesce(nullif(arrival_time,''), departure_time)")} ta
      FROM {rd('stop_times.csv.gz')} WHERE trip_id IN (SELECT trip_id FROM tr)""")
    # kinds of day: weekdays less holidays, Saturdays, Sundays
    con.execute("""CREATE TABLE days AS WITH n AS (SELECT c.sdate, any_value(c.w) w, count(*) k FROM tr JOIN cal c USING (service_id) GROUP BY 1)
      SELECT sdate, CASE WHEN w = 6 THEN 'sat' WHEN w = 0 THEN 'sun'
                         WHEN k >= 0.9 * (SELECT median(k) FROM n WHERE w BETWEEN 1 AND 5) THEN 'day' END kind
      FROM n""")
    con.execute("DELETE FROM days WHERE kind IS NULL")
    out = {}
    # gaps: departures at each direction's busiest stop on each date
    con.execute("""CREATE TABLE x AS SELECT tr.r, c.sdate, tr.dir, tr.trip_id, st.stop_id, st.t, st.seq,
        st.seq = max(st.seq) OVER (PARTITION BY tr.trip_id, c.sdate) is_last
      FROM tr JOIN cal c USING (service_id) JOIN days USING (sdate) JOIN st USING (trip_id)
      QUALIFY row_number() OVER (PARTITION BY tr.trip_id, c.sdate, st.stop_id ORDER BY st.seq) = 1""")
    q = """SELECT x.r, x.sdate, x.dir, list(x.t ORDER BY x.t) FROM x JOIN (
             SELECT r, sdate, dir, stop_id FROM x WHERE NOT is_last GROUP BY r, sdate, dir, stop_id
             QUALIFY row_number() OVER (PARTITION BY r, sdate, dir ORDER BY count(*) DESC, median(seq), stop_id) = 1) b
           USING (r, sdate, dir, stop_id) WHERE NOT x.is_last GROUP BY x.r, x.sdate, x.dir"""
    busiest = {}
    for r, sdate, dr, ts in con.execute(q).fetchall():
        busiest.setdefault((r, sdate), {})[dr] = ts
    kind = dict(con.execute("SELECT sdate, kind FROM days").fetchall())
    per = {}
    for (r, sdate), dd in busiest.items():
        a, b = dd.get("0", []), dd.get("1", [])
        ts = a if len(a) >= len(b) else b
        k = kind[sdate]
        for win in (("day", "eve") if k == "day" else (k,)):
            g = median_gap(ts, WIN[win])
            if g is not None:
                per.setdefault((r, win), []).append(g)
    nwd = sum(1 for v in kind.values() if v == "day")
    # buses: the most in service at once on each weekday
    if has_block:
        con.execute(f"""CREATE TABLE iv AS
          SELECT r, sdate, a // 60 sm,
            greatest(a // 60 + 1, (CASE WHEN nxt IS NOT NULL AND nxt - e < {LAYOVER_GAP} THEN nxt ELSE e END) // 60) em
          FROM (SELECT *, lead(a) OVER (PARTITION BY sdate, b ORDER BY a, trip_id) nxt FROM (
                  SELECT tr.r, tr.b, tr.trip_id, c.sdate, s.a, s.e FROM tr JOIN cal c USING (service_id)
                  JOIN days USING (sdate) JOIN (SELECT trip_id, min(t) a, max(ta) e FROM st GROUP BY 1) s USING (trip_id)
                  WHERE days.kind = 'day' AND coalesce(tr.b, '') <> ''))""")
        q = """SELECT r, sdate, max(n) FROM (
                 SELECT r, sdate, sum(v) OVER (PARTITION BY r, sdate ORDER BY m, v ROWS UNBOUNDED PRECEDING) n
                 FROM (SELECT r, sdate, sm m, 1 v FROM iv UNION ALL SELECT r, sdate, em m, -1 v FROM iv))
               GROUP BY 1, 2"""
        for r, sdate, n in con.execute(q).fetchall():
            per.setdefault((r, "buses"), []).append(n)
    lines = sorted({r for r, _ in per})
    for r in lines:
        row = {"line": r, "month": month, "weekdays": nwd}
        for k in ("buses", "day", "eve", "sat", "sun"):
            v = per.get((r, k))
            row[k] = "" if not v else int(round(statistics.median(v))) if k == "buses" else round(statistics.median(v), 1)
        rows.append(row)
    n_day = sum(1 for r in lines if per.get((r, "day")))
    print(f"{month}: {n_day} lines with a weekday gap, {nwd} weekdays, buses {'yes' if has_block else 'no'}", flush=True)
    if n_day < 40:
        error = f"{month}: {n_day} lines with a weekday gap, under 40"
    return rows, error


def text_of(rows):
    import io
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(sorted(rows, key=lambda x: (x["line"], x["month"])))
    return out.getvalue()


def full(hist, out_path):
    rows, errors = [], []
    for d in sorted(glob.glob(os.path.join(hist, "regional-20??-??-so-sf"))):
        r, e = month_rows(d)
        rows += r
        if e:
            errors.append(e)
    if errors:
        for e in errors:
            print("timetable_month: FAIL", e)
        return 1
    with open(out_path, "w", newline="") as f:
        f.write(text_of(rows))
    print(f"timetable_month: {len(rows)} rows to {out_path}")
    return 0


def update():
    sys.path.insert(0, paths.LIB)
    from lib import pipeline_state
    hist = os.path.join(os.path.expanduser(os.environ.get("MUNI_511_ROOT", "~/muni-511")), "history")
    if not os.path.isdir(hist):
        print(f"muni-timetable-history: not on the VM ({hist} missing); last good {os.path.relpath(TRACKED, ROOT)} kept", file=sys.stderr)
        return 0
    with open(TRACKED, newline="") as f:
        have = list(csv.DictReader(f))
    newest = max(r["month"] for r in have)
    new = [d for d in sorted(glob.glob(os.path.join(hist, "regional-20??-??-so-sf")))
           if os.path.basename(d)[9:16] > newest and os.path.exists(os.path.join(d, "DONE"))]
    if not new:
        print(f"muni-timetable-history: no month after {newest} posted; unchanged")
        pipeline_state.record(MARKER, "unchanged", version=newest)
        return 0
    added = []
    for d in new:
        try:
            r, e = month_rows(d)
        except Exception as ex:  # noqa: BLE001  a month that can't be read keeps the file; the tool waits for it
            print(f"muni-timetable-history: {os.path.basename(d)} could not be read ({type(ex).__name__}: {ex}); last good file kept", file=sys.stderr)
            pipeline_state.record(MARKER, "failed", detail=f"{os.path.basename(d)}: {type(ex).__name__}: {ex}"[:300])
            return 0
        if e:
            print("timetable_month: FAIL", e)
            return 1
        added += r
    text = text_of(have + added)
    with open(TRACKED + ".tmp", "w", newline="") as f:
        f.write(text)
    os.replace(TRACKED + ".tmp", TRACKED)
    last = max(r["month"] for r in added)
    print(f"muni-timetable-history: added {len(added)} rows for {', '.join(os.path.basename(d)[9:16] for d in new)}")
    pipeline_state.record(MARKER, "changed", version=last)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--update"]:
        sys.exit(update())
    sys.exit(full(sys.argv[1], sys.argv[2]))
