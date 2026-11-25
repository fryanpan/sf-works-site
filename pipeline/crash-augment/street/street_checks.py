#!/usr/bin/env python3
"""Quality checks on the crash street-context table; the build runs them on every new table before it replaces the held one, and any failure stops it.

    python3 pipeline/crash-augment/street/street_checks.py    # re-check the held table; exit 1 on any failure

What is checked, each a lib/quality.py Result named "crash-street.<check>":

  rows            one output row per input crash: the join of crash keys neither drops, repeats nor invents a row
  rows-vs-prev    row count against the previous build's summary: at most 2% fewer, at most 10% more
  unique          case_id_pkey unique
  coverage[f]     share of crashes with a value for each field at or above its floor (FLOORS), set a few points
                  under the first build's rate so a broken join fails and ordinary drift does not
  coverage-vs-prev[f]  that share no more than 3 points below the previous build's
  basis[f]        every <field>_basis is one of the allowed values, and the value is empty exactly when the basis is
                  unknown or not_applicable
  range[f]        values in their domain: speed limits 15 to 65 in steps of 5, lanes 0 to 10, classes and corner
                  types from 3psu-pn9h's codes, BCI traffic light/medium/heavy, flags true/false, EPC tracts in SF
  dated[f]        dated values that cannot predate their programme: no 20 mph limit before 2018, no camera
                  corridor flag before 2025
  sources         every input at or above its floor, and every speed camera site placed on a block
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv
import json
import os
import re

from lib.quality import Join, Result  # noqa: E402

NAME = "crash-street"
# The least share of crashes that must carry a value. First build (2026-11-25) rates, less a margin; see README.
FLOORS = {
    "in_epc": 0.98, "posted_speed_limit_mph": 0.95, "street_class": 0.98, "corner_type": 0.98, "lanes": 0.97,
    "bci_traffic_category": 0.97, "painted_safety_zone": 0.99, "speed_camera_corridor": 0.99,
    "traffic_calming": 0.96, "slow_street": 0.99, "signal_present": 0.98,
}
BASES = {f: {"dated", "current_state_only", "unknown"} for f in FLOORS}
BASES["in_epc"] = {"definition_acs2022", "unknown"}
BASES["corner_type"] = {"current_state_only", "unknown", "not_applicable"}
CLASSES = ("freeway", "major", "arterial", "collector", "residential", "ramp", "other")
CORNER = re.compile(r"^(%s)_(x_(%s)|only)$" % ("|".join(CLASSES), "|".join(CLASSES)))
FLAG = {"true", "false"}
DOMAIN = {
    "posted_speed_limit_mph": lambda v: v.isdigit() and 15 <= int(v) <= 65 and int(v) % 5 == 0,
    "lanes": lambda v: v.isdigit() and 0 <= int(v) <= 10,
    "street_class": lambda v: v in CLASSES,
    "corner_type": lambda v: bool(CORNER.match(v)),
    "bci_traffic_category": lambda v: v in ("light", "medium", "heavy"),
    "in_epc": lambda v: v in FLAG,
    "painted_safety_zone": lambda v: v in FLAG, "speed_camera_corridor": lambda v: v in FLAG,
    "traffic_calming": lambda v: v in FLAG, "slow_street": lambda v: v in FLAG, "signal_present": lambda v: v in FLAG,
}
MAX_DROP, MAX_GROWTH, MAX_COVERAGE_FALL = 0.02, 0.10, 0.03


def coverage(rows, field):
    """Share of rows with a value; for corner_type, among rows where it applies."""
    pool = [r for r in rows if r.get(field + "_basis") != "not_applicable"]
    if not pool:
        return 0.0
    return sum(1 for r in pool if r.get(field) not in (None, "")) / len(pool)


def run(rows, crash_keys, prev_summary=None, source_counts=None, source_floors=None, cameras_unplaced=()):
    """Every check over `rows` (dicts of strings, as written to the CSV). `crash_keys` are the input crash keys."""
    out = []
    n = len(rows)
    keys = [r.get("case_id_pkey") for r in rows]
    out += Join(NAME + ".rows", left=lambda root: crash_keys, right=lambda root: keys).check(None)
    if prev_summary and prev_summary.get("rows"):
        p = prev_summary["rows"]
        ok = p * (1 - MAX_DROP) <= n <= p * (1 + MAX_GROWTH)
        out.append(Result(NAME + ".rows-vs-prev", ok, "%d rows, previously %d" % (n, p)))
    dup = n - len(set(keys))
    out.append(Result(NAME + ".unique[case_id_pkey]", dup == 0, "%d repeated" % dup))

    for f, floor in sorted(FLOORS.items()):
        share = coverage(rows, f)
        out.append(Result("%s.coverage[%s]" % (NAME, f), share >= floor, "%.4f, floor %.2f" % (share, floor)))
        if prev_summary:
            was = ((prev_summary.get("coverage") or {}).get(f) or {}).get("all", {}).get("non_null")
            if was is not None:
                out.append(Result("%s.coverage-vs-prev[%s]" % (NAME, f), share >= was - MAX_COVERAGE_FALL,
                                  "%.4f, previously %.4f" % (share, was)))
        bad_basis, mismatch, bad_value = [], [], []
        for r in rows:
            b, v = r.get(f + "_basis"), r.get(f) or ""
            if b not in BASES[f]:
                bad_basis.append((r.get("case_id_pkey"), b))
            elif (v == "") != (b in ("unknown", "not_applicable")):
                mismatch.append((r.get("case_id_pkey"), v, b))
            if v and not DOMAIN[f](v):
                bad_value.append((r.get("case_id_pkey"), v))
        out.append(Result("%s.basis[%s]" % (NAME, f), not bad_basis and not mismatch,
                          "%d bad basis, %d value/basis mismatches%s" % (
                              len(bad_basis), len(mismatch), (": %s" % (bad_basis + mismatch)[:3]) if bad_basis or mismatch else "")))
        out.append(Result("%s.range[%s]" % (NAME, f), not bad_value,
                          "%d out of domain%s" % (len(bad_value), (": %s" % bad_value[:3]) if bad_value else "")))
        if f in ("lanes",):
            for g in ("lanes_am", "lanes_pm"):
                bad = [(r.get("case_id_pkey"), r.get(g)) for r in rows if r.get(g) and not DOMAIN["lanes"](r[g])]
                out.append(Result("%s.range[%s]" % (NAME, g), not bad, "%d out of domain" % len(bad)))

    bad_tract = [r["case_id_pkey"] for r in rows if r.get("epc_tract") and not r["epc_tract"].startswith("06075")]
    out.append(Result(NAME + ".range[epc_tract]", not bad_tract, "%d outside SF" % len(bad_tract)))
    early20 = [r["case_id_pkey"] for r in rows if r.get("posted_speed_limit_mph") == "20"
               and r.get("posted_speed_limit_mph_basis") == "dated" and r.get("collision_date", "") < "2018-01-01"]
    out.append(Result(NAME + ".dated[posted_speed_limit_mph]", not early20, "%d dated 20 mph before 2018" % len(early20)))
    early_cam = [r["case_id_pkey"] for r in rows if r.get("speed_camera_corridor") == "true"
                 and r.get("collision_date", "") < "2025-01-01"]
    out.append(Result(NAME + ".dated[speed_camera_corridor]", not early_cam, "%d before 2025" % len(early_cam)))

    for name, cnt in sorted((source_counts or {}).items()):
        fl = (source_floors or {}).get(name, 1)
        out.append(Result("%s.sources[%s]" % (NAME, name), cnt >= fl, "%d rows, floor %d" % (cnt, fl)))
    out.append(Result(NAME + ".sources[camera-sites-placed]", not cameras_unplaced,
                      "%d unplaced%s" % (len(cameras_unplaced), (": " + ", ".join(cameras_unplaced)) if cameras_unplaced else "")))
    return out


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def report(results):
    """Print failures (and a one-line tally); return True when every check passed."""
    bad = [r for r in results if not r.ok]
    for r in bad:
        print("  %r" % r)
    print("  %s: %d checks, %d failed" % (NAME, len(results), len(bad)))
    return not bad


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import street_paths
    import street_sources
    if not os.path.exists(street_paths.OUT_CSV):
        print("no table at %s; run crash-street-context.py first" % street_paths.OUT_CSV)
        return 1
    rows = read_csv(street_paths.OUT_CSV)
    summary = json.load(open(street_paths.OUT_SUMMARY, encoding="utf-8")) if os.path.exists(street_paths.OUT_SUMMARY) else {}
    src = street_sources.load_all(update=False)
    keys = [r["case_id_pkey"] for r in src["crashes"].rows]
    ok = report(run(rows, keys, prev_summary=summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
