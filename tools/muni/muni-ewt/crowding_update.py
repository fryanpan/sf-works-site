"""Daily rebuild of the Muni crowding figures from our 511 realtime archive: crowding_by_hour.py's and crowding_levels.py's outputs.

The line pages, the overview and the lines list draw how full buses are from SFMTA's live
occupancy levels (crowding_levels.py) and the line optimizer reads the crowded share by hour (crowding_by_hour.py).
Both summarise the archive's compacted day files, so this step re-runs them each day once the new day is compacted
(daily, in transportation-update.py STEPS).

Incremental: optimizer_crowding.fetch() lists the bucket's compacted vehicle-position files
(sf/parquet/vehicle_positions/ in the archive bucket, one a UTC day, written by compact.py at 01:30 UTC and
never replaced) and downloads only the ones missing from .cache/rt-archive/vehicle_positions/ or whose size changed.
A failed listing or download keeps the cached copies. A service day runs to 01:00 Pacific, which is 08:00 or 09:00 UTC
the next day, so at the 13:15 UTC run yesterday's service day still needs today's UTC file, which compact.py won't
write until 01:30 UTC tomorrow. So each UTC day after the newest compacted one, through today, is also decoded from the
raw snapshots by tools/muni/rt-archive/day_parquet.py (compact.py's own decoder) into the cache's raw/ folder, rewritten
every run and deleted once its compacted file arrives. Without it the newest complete day was always two days old at
the run, and a single overnight 511 outage (15 Nov 2026: empty feeds 00:00 to 01:50 Pacific on 16 Nov) failed the
newest-day check. Both summaries then re-read the newest WINDOW_FILES cached
files (DuckDB over Parquet, a few seconds), so the figures cover the complete service days of about the last four
weeks, and a rerun with no new day writes the same bytes.

On the VM only (heavy reads stay off the laptop, and only the VM has the archive's credentials): off it (no
~/muni-511/history, the test rt_daily.py uses) it says so and exits 0, and the copy in the repo stands.

Checks, before anything in the repo is written; a failure exits 1 and leaves every output as it was:
  - each script's own checks (at least two counted weekdays, levels known and adding up to reads, crowded reads no
    more than reads, buses in service every hour 06-21);
  - the two agree: on every line, direction, day type and hour, crowding_levels.py's reads equal crowding_by_hour.py's,
    and its standing room, crushed, full and not-accepting counts add up to crowding_by_hour.py's crowded reads (the
    same reads under the same rules, so any difference is a bug in one of them);
  - both name the same counted days and the same short hours, and give every line-hour the same `days`.
Which days and hours count is optimizer_crowding.service_hours: an hour with fewer than 15 of its 20 snapshots is
dropped, and a day counts with at least 16 of its 21 hours (its docstring says why), so an overnight 511 outage costs
an hour, not the day. The newest complete day's age is the quality step's check (transportation-quality.py, muni-crowding/newest-day).
Outputs, each rewritten only when its bytes change (lib/stable.py): data/muni-ewt/optimizer/crowding_by_hour.csv
and .json, crowding_levels_hour.csv, crowding_levels_along.csv and crowding_levels.json.
Usage: ~/.venvs/sf-works-geo/bin/python -I tools/muni/muni-ewt/crowding_update.py [--update]
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, paths.ROOT)
from lib import stable  # noqa: E402

ROOT = paths.ROOT
OUT = os.path.join(ROOT, "data", "muni-ewt", "optimizer")
WINDOW_FILES = 29  # UTC day files read: 28 service days, each of which runs into the next UTC day
NAMES = ["crowding_by_hour.csv", "crowding_by_hour.json", "crowding_levels_hour.csv", "crowding_levels_along.csv", "crowding_levels.json"]
CROWDED_COLS = ("standing_room", "crushed", "full", "not_accepting")


def on_vm():
    return os.path.isdir(os.path.expanduser(os.environ.get("MUNI_511_ROOT", "~/muni-511") + "/history"))


RAW_DAYS_MAX = 2  # UTC days decoded from raw snapshots in one run: today, and yesterday if compaction failed


def keep_window(files):
    """The newest WINDOW_FILES day files, by the day in each file's name (raw/ files sort among the compacted ones)."""
    return sorted(files, key=os.path.basename)[-WINDOW_FILES:]


def raw_days(cache, rt_py, today):
    """Decode each UTC day after the newest compacted file in `cache`, through `today`, from the raw snapshots into
    cache/raw/<day>.parquet. Returns the paths written. A failed decode leaves no file for that day, so its service day
    is just not complete yet; a raw file whose compacted copy is now cached is removed."""
    raw = os.path.join(cache, "raw")
    os.makedirs(raw, exist_ok=True)
    have = {os.path.basename(f)[:10] for f in glob.glob(os.path.join(cache, "*.parquet"))}
    for f in glob.glob(os.path.join(raw, "*.parquet")):
        if os.path.basename(f)[:10] in have or os.path.basename(f)[:10] < max(have, default=""):
            os.remove(f)
    if not have or not os.path.exists(rt_py):
        return []
    d = dt.date.fromisoformat(max(have)) + dt.timedelta(days=1)
    days = []
    while d <= today:
        days.append(d)
        d += dt.timedelta(days=1)
    out = []
    for d in days[-RAW_DAYS_MAX:]:
        path = os.path.join(raw, f"{d}.parquet")
        r = subprocess.run([rt_py, paths.script("day_parquet.py"), "--feed",
                            "vehicle_positions", "--day", str(d), "--out", path], capture_output=True, text=True, timeout=1800)
        if r.returncode == 0 and os.path.exists(path):
            out.append(path)
            print(f"crowding_update: decoded {d} from raw snapshots: {r.stdout.strip().splitlines()[-1]}")
        else:
            print(f"crowding_update: could not decode {d} from raw snapshots: {r.stderr.strip()[-200:]}")
            if os.path.exists(path):
                os.remove(path)
    return out


def agree(tmp):
    """Errors where crowding_levels.py and crowding_by_hour.py disagree on the same reads."""
    errs = []
    rd = lambda n: list(csv.DictReader(open(os.path.join(tmp, n), encoding="utf-8")))
    key = lambda r: (r["line"], r["direction"], r["day_type"], r["hour"])
    hb = {key(r): r for r in rd("crowding_by_hour.csv")}
    hl = {key(r): r for r in rd("crowding_levels_hour.csv")}
    if set(hb) != set(hl):
        errs.append(f"{len(set(hb) ^ set(hl))} line-direction-hours in one file and not the other")
    for k in sorted(set(hb) & set(hl)):
        a, b = hb[k], hl[k]
        if int(a["reads"]) != int(b["reads"]) or int(a["days"]) != int(b["days"]) or int(a["crowded_reads"]) != sum(int(b[c]) for c in CROWDED_COLS):
            errs.append(f"{k}: by hour {a['crowded_reads']} of {a['reads']} crowded, levels {sum(int(b[c]) for c in CROWDED_COLS)} of {b['reads']}")
    jb = json.load(open(os.path.join(tmp, "crowding_by_hour.json")))
    jl = json.load(open(os.path.join(tmp, "crowding_levels.json")))
    if sorted(jb["complete_days"]) != sorted(jl["complete_days"]["weekday"] + jl["complete_days"]["weekend"]):
        errs.append(f"counted days differ: by hour {jb['complete_days']}, levels {jl['complete_days']}")
    if jb["short_hours"] != jl["short_hours"]:
        errs.append(f"short hours differ: by hour {jb['short_hours']}, levels {jl['short_hours']}")
    return errs[:20]


def main(argv):
    if not on_vm():
        print("crowding_update: not on the VM (~/muni-511/history missing); the repo's crowding files are kept")
        return 0
    import optimizer_crowding as OC
    import crowding_by_hour as CBH
    import crowding_levels as CL
    if "--update" in argv:
        got, fail = OC.fetch()
        print(f"crowding_update: {got} day file(s) fetched, {fail} failed")
        raw_days(OC.CACHE, OC.RT_PY, dt.datetime.now(dt.timezone.utc).date())
    files = keep_window(glob.glob(os.path.join(OC.CACHE, "*.parquet")) + glob.glob(os.path.join(OC.CACHE, "raw", "*.parquet")))
    if not files:
        print("crowding_update: FAIL no cached day files")
        return 1
    tmp = tempfile.mkdtemp(prefix="crowding-")
    try:
        p = lambda n: os.path.join(tmp, n)
        if CBH.summarise(files, p("crowding_by_hour.csv"), p("crowding_by_hour.json")):
            print("crowding_update: FAIL crowding_by_hour.py's checks; outputs kept")
            return 1
        if CL.summarise(files, p("crowding_levels_hour.csv"), p("crowding_levels_along.csv"), p("crowding_levels.json")):
            print("crowding_update: FAIL crowding_levels.py's checks; outputs kept")
            return 1
        errs = agree(tmp)
        if errs:
            for e in errs:
                print(f"crowding_update: FAIL {e}")
            return 1
        os.makedirs(OUT, exist_ok=True)
        for n in NAMES:
            changed = stable.write_text(os.path.join(OUT, n), open(p(n), encoding="utf-8").read())
            print(f"crowding_update: {'wrote' if changed else 'unchanged'} {os.path.relpath(os.path.join(OUT, n), ROOT)}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
