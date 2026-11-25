"""Where the crash street-context build writes: the full table (gitignored, about 10 MB) and its small tracked summary.

    import street_paths
    street_paths.OUT_CSV        out/crash-augment/street/crash-street.csv, one row per crash in ubvf-ztfx
    street_paths.OUT_SUMMARY    out/crash-augment/street/summary.json, counts and coverage per field and basis
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import os

OUT_DIR = os.path.join(paths.ROOT, "out", "crash-augment", "street")
OUT_CSV = os.path.join(OUT_DIR, "crash-street.csv")
OUT_SUMMARY = os.path.join(OUT_DIR, "summary.json")
