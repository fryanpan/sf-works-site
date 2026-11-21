"""Write one UTC day of one archived 511 feed as decoded Parquet to a local path, for the Muni daily figures.

Takes the day's compacted Parquet from the bucket when compact.py has written it (sf/parquet/{feed}/YYYY/MM/<day>.parquet).
For a day not compacted yet (today, or yesterday before the 01:30 UTC compaction), it decodes the day's raw snapshots
itself, with compact.py's own decoder, from the VM's spool and, for any snapshot the spool no longer holds, the bucket.
Nothing is uploaded and nothing in the bucket changes. Prints one JSON line: {"from": "parquet" | "raw", "final": bool,
"snapshots": n}; "final" is true only for a compacted day, which can't change again (compact.py never replaces one), so
the caller may cache it, and false for raw, which may still grow.

Runs in the archive's virtualenv (~/.venvs/rt-archive: google-cloud-storage, gtfs-realtime-bindings, pyarrow).
Usage: day_parquet.py --feed vehicle_positions --day 2026-11-12 --out /path/x.parquet
"""

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compact as C  # noqa: E402
import rtarchive as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", required=True, choices=sorted(R.FEEDS))
    ap.add_argument("--day", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    day = dt.date.fromisoformat(a.day)
    b = R.bucket()
    blob = b.blob(R.parquet_name(a.feed, day))
    tmp = a.out + ".part"
    if blob.exists():
        blob.download_to_filename(tmp, timeout=600)
        os.replace(tmp, a.out)
        print(json.dumps({"from": "parquet", "final": True, "snapshots": None}))
        return
    nsnap, _ = C.compact(a.feed, day, b, tmp)
    os.replace(tmp, a.out)
    print(json.dumps({"from": "raw", "final": False, "snapshots": nsnap}))


if __name__ == "__main__":
    main()
