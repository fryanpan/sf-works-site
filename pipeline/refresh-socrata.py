#!/usr/bin/env python3
"""Re-read cached DataSF queries only for datasets the city has updated since the cache was filled.

    pipeline/refresh-socrata.py 3psu-pn9h btxj-k9uh      # these datasets' cached queries
    pipeline/refresh-socrata.py --force 3psu-pn9h        # re-read even if unchanged

Every query a script has made through lib/sfdata.py sits in
data/socrata-cache/ with its dataset, its parameters and the date its rows were
read. For each named dataset this asks DataSF when the rows last changed
(`rowsUpdatedAt`, one small request) and re-runs a cached query only when the
dataset changed on or after the day the query was read. A re-read that returns
the same rows leaves the cache entry, and so every figure built from it,
exactly as it was.

The date of the check goes to data/pipeline-state/sources.json (gitignored),
which is what the audit's freshness check reads. Exit status 0; prints one line
per dataset: unchanged, re-read with no difference, or changed.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sfdata  # noqa: E402
from lib import pipeline_state  # noqa: E402


def entries(fxf):
    out = []
    for p in sorted(glob.glob(os.path.join(sfdata.CACHE_ROOT, "%s-*.json" % fxf))):
        try:
            blob = json.load(open(p))
            out.append((p, blob))
        except (ValueError, OSError):
            continue
    return out


def refresh(fxf, force=False):
    meta = sfdata.metadata(fxf)
    updated = meta["rows_updated_at"]
    stamp = meta.get("rows_updated_ts")
    # The last check's marker, to the second. When it has not moved, nothing
    # has been published since, whatever day the cached rows were read.
    last = pipeline_state.load().get("socrata:" + fxf, {})
    settled = (stamp is not None and last.get("status") != "failed"
               and last.get("version") == str(stamp))
    changed, reread, kept = 0, 0, 0
    for path, blob in entries(fxf):
        read_on = dt.date.fromisoformat(blob["fetched_on"])
        if not force and (settled or (updated is not None and updated < read_on)):
            kept += 1
            continue
        p = blob.get("params") or {}
        before = os.path.getmtime(path)
        # A re-read shorter than half the cached one is a failed read, not a
        # smaller dataset, so it raises instead of replacing good rows.
        n = len(blob.get("rows") or ())
        sfdata.fetch(fxf, select=p.get("$select"), where=p.get("$where"), order=p.get("$order"),
                     refresh=True, floor=n // 2 if n > 1 else 0)
        reread += 1
        if os.path.getmtime(path) != before:
            changed += 1
    status = "changed" if changed else "unchanged"
    pipeline_state.record("socrata:" + fxf, status=status,
                          version=str(stamp) if stamp is not None else None,
                          detail="%d cached queries: %d kept, %d re-read, %d changed" % (kept + reread, kept, reread, changed))
    print("  %s: rows updated %s; %d cached queries, %d re-read, %d changed"
          % (fxf, updated, kept + reread, reread, changed))
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datasets", nargs="+")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    failed = []
    for fxf in args.datasets:
        # One dataset's failed check or short re-read must not stop the others
        # from being checked. A query whose re-read raised (sfdata's floor, a
        # timeout) keeps its cached rows; the dataset is recorded as failed,
        # not with the new marker, so the next run re-reads it rather than
        # taking the marker as read. F3 then ages it from its last good check.
        try:
            refresh(fxf, args.force)
        except Exception as exc:  # noqa: BLE001
            failed.append(fxf)
            pipeline_state.record("socrata:" + fxf, status="failed", detail="%s: %s" % (type(exc).__name__, exc))
            print("  %s: FAILED (%s: %s); cached rows kept" % (fxf, type(exc).__name__, exc))
    if failed:
        print("refresh-socrata: %d dataset(s) not refreshed: %s" % (len(failed), ", ".join(failed)))


if __name__ == "__main__":
    main()
