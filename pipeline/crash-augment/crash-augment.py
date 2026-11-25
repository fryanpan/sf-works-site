#!/usr/bin/env python3
"""Build DataSF's three injury-crash tables with vehicle and street columns added: fetch, vehicles, street, merge, check.

    python3 pipeline/crash-augment/crash-augment.py            # build from the held copies (no DataSF read once held)
    python3 pipeline/crash-augment/crash-augment.py --update   # ask every source what changed first, read only that
    python3 pipeline/crash-augment/crash-augment.py --check    # run every check on the current outputs, build nothing

The stages, in order. Any stage that fails stops the run with exit 1 and leaves the last good outputs in place.

  1. fetch     crash_tables.py: the held copy of crashes ubvf-ztfx, parties 8gtc-pjc6 and victims nwes-mmgh, in
               data/socrata-cache/crash-augment/. With --update it reads only rows whose data_updated_at moved and
               reconciles any year whose count is off, then checks the copy against DataSF's counts.
  2. vehicles  vehicles/vehicle-fields.py: clean make, model and estimated curb weight for every party and victim,
               and the heaviest vehicle per crash, into .cache/crash-augment/vehicles/. Its own checks run inside it.
  3. street    street/crash-street-context.py: the street context of every crash as of its date, into
               out/crash-augment/street/. With --update it asks each street source for its change marker. Its own
               checks run inside it.
  4. merge     augment_merge.py: every DataSF column plus the lanes' columns, written to a staging folder.
  5. check     augment_checks.py on the staged tables, against the live ones as the previous build. Only when every
               check passes do the staged files replace the live ones, and a file whose bytes did not change is left
               alone, so a rerun with no new data changes nothing.

Both lanes run with CRASH_TABLES_HELD=1, so they read the copy stage 1 just checked rather than refreshing it again:
every column in the three tables describes the same DataSF update.

OUTPUT (the CSVs gitignored):

  out/crash-augment/tables/crashes.csv    66,991 rows on 2026-11-25
  out/crash-augment/tables/parties.csv    140,843 rows
  out/crash-augment/tables/victims.csv    84,943 rows
  out/crash-augment/tables/summary.json   tracked: row counts, added columns, each input's content hash and read date

Columns, rules and checks: pipeline/crash-augment/README.md. Interval: daily, with the scheduled refresh
(pipeline/transportation-update.py step "crash-augment").
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import augment_checks  # noqa: E402
import augment_merge  # noqa: E402
import crash_tables  # noqa: E402

OUT = os.path.join(paths.ROOT, augment_checks.OUT_REL)
FILES = ("crashes.csv", "parties.csv", "victims.csv", "summary.json")
LANES = [
    ("vehicles", os.path.join(HERE, "vehicles", "vehicle-fields.py")),
    ("street", os.path.join(HERE, "street", "crash-street-context.py")),
]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(name, t0):
    print("[%s] %.0fs" % (name, time.time() - t0), flush=True)


def run_lane(name, script, update):
    env = dict(os.environ, CRASH_TABLES_HELD="1", PYTHONHASHSEED=os.environ.get("PYTHONHASHSEED", "0"))
    cmd = [sys.executable, script] + (["--update"] if update else [])
    code = subprocess.call(cmd, env=env, cwd=paths.ROOT)
    if code:
        print("crash-augment: the %s lane exited %d; the last good outputs are kept" % (name, code))
    return code


def check_only():
    results = augment_checks.run(paths.ROOT)
    for r in results:
        print("   ", r)
    bad = [r for r in results if not r.ok]
    print("crash-augment: %d of %d checks failed" % (len(bad), len(results)) if bad else
          "crash-augment: %d checks pass" % len(results))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="ask every source what changed, and read only that")
    ap.add_argument("--check", action="store_true", help="run the checks on the current outputs and stop")
    args = ap.parse_args()
    if args.check:
        return check_only()
    t0 = time.time()

    stage("fetch", t0)
    try:
        crash_tables.refresh(update=args.update)
    except crash_tables.CheckFailed as exc:
        for r in exc.results:
            if not r.ok:
                print("   ", r)
        print("crash-augment: the held DataSF tables failed their checks; nothing was rebuilt")
        return 1

    for name, script in LANES:
        stage(name, t0)
        if run_lane(name, script, args.update):
            return 1

    stage("merge", t0)
    # The staging folder mirrors the repo's layout, so the checks read it with the live outputs as the previous build.
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="crash-augment-stage-", dir=os.path.dirname(OUT))
    try:
        staged = os.path.join(tmp, augment_checks.OUT_REL)
        augment_merge.build(staged)

        stage("check", t0)
        results = augment_checks.run(tmp, prev_root=paths.ROOT if os.path.isdir(OUT) else None)
        bad = [r for r in results if not r.ok]
        for r in bad:
            print("   ", r)
        if bad:
            print("crash-augment: %d of %d checks failed; the last good tables are kept in %s"
                  % (len(bad), len(results), os.path.relpath(OUT, paths.ROOT)))
            return 1
        os.makedirs(OUT, exist_ok=True)
        wrote = []
        for f in FILES:
            src, dest = os.path.join(staged, f), os.path.join(OUT, f)
            if os.path.exists(dest) and sha(dest) == sha(src):
                continue
            shutil.move(src, dest)
            wrote.append(f)
        info = augment_checks.summary(paths.ROOT)["tables"]
        print("crash-augment: %d checks pass; %s; %s" % (
            len(results), ", ".join("%s %d rows" % (n, t["rows"]) for n, t in sorted(info.items())),
            ("wrote " + ", ".join(wrote)) if wrote else "nothing changed"))
        print("  tables in %s (%.0fs)" % (OUT, time.time() - t0))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
