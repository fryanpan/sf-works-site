#!/usr/bin/env python3
"""Keep the Street Safety map's and the injury pages' DataSF crash reads current: read every query lib/street_safety_reads.py names, cold or when its table changed, check the rows, and keep the last good copy on a failed read.

    python3 tools/street-safety/street-safety-crashes.py            # check the held reads; read only the queries not held yet
    python3 tools/street-safety/street-safety-crashes.py --update   # also ask DataSF what changed and re-read it

WHAT IT HOLDS. street_safety_reads.QUERIES, the queries of tools/street-safety/hin-injury-kinds.py, street-safety-light.py,
hin-densest-stretches.py, hin-people-map.py, hin_crash_cards.py, injury-map.py and injury-severe-why.py, in
data/socrata-cache/street-safety/ (gitignored). Four tables: nwes-mmgh (victims), 8gtc-pjc6 (parties), ubvf-ztfx
(crashes) and dau3-4s8f (fatality log). A held file that no query names any more (a query whose text changed) is
deleted, so stale copies don't pile up.

INCREMENTAL FETCH. A query with no held copy is read cold: a new machine's first run reads everything, through the
same checks as any re-read. With --update, DataSF's rowsUpdatedAt for each table, to the second: when it has not moved
since the last good check (data/pipeline-state/sources.json, "crashes:<id>"), nothing of that table is read; when it
has, each of the table's queries is re-read into a staging folder. A held copy whose rows no longer hash as this
script last recorded them (data/socrata-cache/street-safety/_manifest.json) is re-read too, so a damaged copy mends
itself; a run without --update reports it and leaves it unrecorded. A re-read that returns the rows already held
keeps the held copy and its date, so nothing downstream moves. A transient failure (no answer, HTTP 5xx or 429, a
timeout) keeps the held copy, records the table as failed and goes on, exit 0, so the builds run on the last good
reads.

CHECKS, run on every read before it replaces or becomes a held copy (street_safety_reads.check_query, check_joins):
  rows       at least the query's floor, and at least 90% of the held copy's count;
  required   the table's key fields (and collision_datetime where the query selects it) on every row;
  dates      every collision_datetime from 2005-01-01 to tomorrow, and inside the query's own date range where its
             $where holds one date clause;
  keys       one row per key: victims (case, victim), parties (case, party number), crashes (case), fatality log
             (unique_id). DataSF corrects a row by appending another under the same key with a newer data_updated_at;
             the newest is kept and each one is printed as a warning. Two rows with the same data_updated_at that differ
             fail, except case 260408381's parties (street_safety_reads.TIES);
  joins      every victim's and party's case dated inside the crash reads' range is in the crash reads, at most 0.5%
             missing (the same bound as tools/street-safety/street-safety-cards.py).
pipeline/transportation-update.py snapshots the folder before the step and runs pipeline/transportation-quality.py's
street-safety-crashes checks after it.

Exit codes: 0 done, or a table's read failed transiently and its held copies were kept; 1 a check failed, and every
held copy is as it was; 2 a read failed for another reason (a 400 from a malformed query, say), nothing replaced.

Interval: daily, with the scheduled run (pipeline/transportation-update.py step street-safety-crashes).
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402
from lib import pipeline_state, street_safety_reads as ssr  # noqa: E402
from lib.fetch import is_transient  # noqa: E402


def rows_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="ask DataSF what changed and re-read it")
    a = ap.parse_args()
    today = dt.date.today()
    shutil.rmtree(ssr.STAGE, ignore_errors=True)   # reads a stopped run left staged were never checked
    try:
        files = json.loads(ssr.MANIFEST.read_text()).get("files", {})
    except (FileNotFoundError, ValueError):
        files = {}
    state = pipeline_state.load()
    by_table = {fxf: sorted(n for n, q in ssr.QUERIES.items() if q["fxf"] == fxf) for fxf in ssr.DATASETS}
    outcome, staged, bad, reads, warns, damaged_left = {}, [], [], {}, [], []
    for fxf in ssr.DATASETS:
        status, version, detail, changed = "unchanged", None, "", False
        if a.update:
            try:
                version = str(sfdata.metadata(fxf).get("rows_updated_ts"))
                last = state.get("crashes:" + fxf, {})
                changed = not (last.get("version") == version and last.get("status") != "failed")
            except Exception as e:  # noqa: BLE001
                if not is_transient(e):
                    print("STOPPED: rowsUpdatedAt of %s: %s" % (fxf, e), file=sys.stderr)
                    sys.exit(2)
                status, detail = "failed", "rowsUpdatedAt not read (%s); held reads kept" % e
        reads[fxf] = []
        failed, n_read, n_new, n_cold = [], 0, 0, 0
        for name in by_table[fxf]:
            path = ssr.path_of(name)
            blob = json.loads(path.read_text()) if path.exists() else None
            rec = files.get(path.name)
            now = rows_hash(blob["rows"]) if blob else None
            damaged = blob is not None and rec is not None and rec.get("sha") != now
            held_n = (rec or {}).get("n", 0) if damaged else len(blob["rows"]) if blob else 0
            want = blob is None or (a.update and (damaged or (changed and status != "failed")))
            if not want:
                b, w = ssr.check_query(name, blob["rows"], held_n, today)
                bad += b
                warns += w
                reads[fxf].append(blob["rows"])
                if damaged:
                    damaged_left.append(path.name)   # reported, not recorded as good
                else:
                    files[path.name] = {"sha": now, "n": len(blob["rows"])}
                continue
            try:
                r = ssr.stage_read(name)
            except Exception as e:  # noqa: BLE001
                if not is_transient(e):
                    print("STOPPED: %s: %s" % (name, e), file=sys.stderr)
                    shutil.rmtree(ssr.STAGE, ignore_errors=True)
                    sys.exit(2)
                failed.append("%s (%s)" % (name, str(e)[:80]))
                if blob:
                    reads[fxf].append(blob["rows"])
                continue
            n_read += 1
            n_cold += blob is None
            b, w = ssr.check_query(name, r.rows, held_n, today)
            bad += b
            warns += w
            if blob is None or r.rows != blob["rows"]:
                n_new += 1
            reads[fxf].append(r.rows)
            staged.append((path, r.rows))
            print("  %s %s: %s, %d rows%s" % (fxf, name, "read cold" if blob is None else "re-read", len(r.rows),
                                              "" if blob is None or r.rows == blob["rows"] else " (held %d)" % len(blob["rows"])),
                  file=sys.stderr)
        if failed:
            status, detail = "failed", "read failed, held copy kept: " + "; ".join(failed[:5])
        elif status != "failed" and (a.update or n_cold):
            status = "changed" if n_new else "unchanged"
            detail = "%d queries; %d read (%d cold), %d with new rows" % (len(by_table[fxf]), n_read, n_cold, n_new)
        outcome[fxf] = (status, version, detail)
    jbad, jnote = ssr.check_joins(reads)
    bad += jbad
    for w in sorted(set(warns))[:20]:
        print("  warning: %s" % w, file=sys.stderr)
    if len(set(warns)) > 20:
        print("  warning: %d more corrected rows" % (len(set(warns)) - 20), file=sys.stderr)
    if bad:
        shutil.rmtree(ssr.STAGE, ignore_errors=True)
        if a.update:
            for fxf in outcome:
                pipeline_state.record("crashes:" + fxf, "failed", version=None, detail="checks failed: " + "; ".join(bad)[:300])
        print("STOPPED: street-safety-crashes checks failed: %s" % "; ".join(bad[:8]), file=sys.stderr)
        sys.exit(1)
    ssr.CACHE.mkdir(parents=True, exist_ok=True)
    for path, rows in staged:
        os.replace(ssr.STAGE / path.name, path)
        files[path.name] = {"sha": rows_hash(rows), "n": len(rows)}
    shutil.rmtree(ssr.STAGE, ignore_errors=True)
    named = {ssr.path_of(n).name for n in ssr.QUERIES}
    gone = sorted(p.name for p in ssr.CACHE.glob("*-*.json") if p.name not in named)
    for f in gone:
        os.remove(ssr.CACHE / f)
    files = {k: v for k, v in sorted(files.items()) if k in named and (ssr.CACHE / k).exists()}
    text = json.dumps({"files": files}, sort_keys=True, indent=1) + "\n"
    if not ssr.MANIFEST.exists() or ssr.MANIFEST.read_text() != text:
        ssr.MANIFEST.write_text(text)
    if a.update:
        for fxf, (status, version, detail) in outcome.items():
            pipeline_state.record("crashes:" + fxf, status, version=version, detail=detail or None)
    for fxf, (status, version, detail) in outcome.items():
        print("street-safety-crashes %s: %s%s" % (fxf, status, (", " + detail) if detail else ""), file=sys.stderr)
    print("street-safety-crashes joins: %s" % (jnote or "none to check"), file=sys.stderr)
    if gone:
        print("street-safety-crashes: deleted %d held files no query names: %s" % (len(gone), ", ".join(gone[:5])), file=sys.stderr)
    if damaged_left:
        print("street-safety-crashes: %d held copies changed since they were checked, left for the next --update: %s" % (
            len(damaged_left), ", ".join(damaged_left[:5])), file=sys.stderr)
    if any(s[0] == "failed" for s in outcome.values()):
        print("REFRESH FAILED: " + "; ".join("%s %s" % (f, s[2]) for f, s in outcome.items() if s[0] == "failed"), file=sys.stderr)


if __name__ == "__main__":
    main()
