#!/usr/bin/env python3
"""The quality checks the three augmented crash tables must pass before they replace the last good build.

    python3 pipeline/crash-augment/augment_checks.py     # check the built tables in out/crash-augment/tables/; exit 1 on a failure

crash-augment.py runs these on its staged tables, with the live tables as the previous build, and keeps the live ones
when any check fails. pipeline/transportation-quality.py runs the same list after the crash-augment step, against the
snapshot it took before the step. Each check is named "crash-augment/<file>.<check>":

  rows, unique, required, dates   lib/quality.py's Table: at least FLOORS rows, no fall of more than 2% or rise of
                                  more than 10% against the previous build, the key unique, the key and join fields
                                  never empty, every collision_datetime from 2005-01-01 to tomorrow.
  join                            every party's crash is a crash row, and every victim's party (case_id_pkey and
                                  party_number_ckey) is exactly one parties row, so no lane fanned a row out.
  each (summary.json)             every table holds exactly the rows of its held DataSF table; every held row found
                                  its row in every lane, no lane row is left over and none repeats; and the vehicle
                                  lane read the same held copy (crash_tables.info's content_sha) the tables were
                                  built from.
  each (accident_year)            accident_year is the year of collision_datetime on all but YEAR_MISMATCH_MAX rows.
                                  DataSF's accident_year runs a year behind on a handful of January to April crashes
                                  (7 on 2026-11-25, every one with a case number of the later year), so anything that
                                  groups by year reads collision_datetime; the check catches the field drifting further.
  each (columns)                  the header is DataSF's columns and then each lane's, as summary.json lists them,
                                  and every added column has a value on at least one row.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv
import json
import os

from lib.quality import Each, Join, Table, run as quality_run  # noqa: E402

OUT_REL = os.path.join("out", "crash-augment", "tables")
FLOORS = {"crashes": 60000, "parties": 125000, "victims": 75000}
# The fields each table's checks read; everything else is left unparsed.
FIELDS = {
    "crashes": ["case_id_pkey", "collision_datetime", "accident_year"],
    "parties": ["unique_id", "case_id_pkey", "party_number_ckey", "collision_datetime", "vehicle_match_method"],
    "victims": ["unique_id", "case_id_pkey", "party_number_ckey", "collision_datetime", "vehicle_match_method"],
}
YEAR_MISMATCH_MAX = 20
KEYS = {"crashes": "case_id_pkey", "parties": "unique_id", "victims": "unique_id"}

_cache = {}


def scan(root, name):
    """(rows of FIELDS, header, {column: rows with a value}) for one table under `root`, or None when absent."""
    p = os.path.join(root, OUT_REL, name + ".csv")
    if not os.path.exists(p):
        return None
    st = os.stat(p)
    tag = (p, st.st_size, st.st_mtime_ns)
    if tag not in _cache:
        rows, filled = [], None
        with open(p, encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd)
            idx = [header.index(f) for f in FIELDS[name] if f in header]
            names = [f for f in FIELDS[name] if f in header]
            filled = [0] * len(header)
            for r in rd:
                rows.append({f: r[i] for f, i in zip(names, idx)})
                for i, v in enumerate(r):
                    if v:
                        filled[i] += 1
        if len(_cache) > 6:
            _cache.clear()
        _cache[tag] = (rows, header, dict(zip(header, filled)))
    return _cache[tag]


def loader(name):
    def load(root):
        got = scan(root, name)
        return None if got is None else got[0]
    load.__name__ = name + ".csv"
    return load


def summary(root):
    p = os.path.join(root, OUT_REL, "summary.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def summary_rule(entry):
    name, t = entry["name"], entry["table"]
    why = []
    held = (t.get("input") or {}).get("rows")
    if t["rows"] != held:
        why.append("%s holds %s rows, its DataSF table %s" % (name, t["rows"], held))
    for what in ("missing_lane_rows", "lane_rows_not_held", "lane_keys_repeated"):
        bad = {k: v for k, v in (t.get(what) or {}).items() if v}
        if bad:
            why.append("%s %s: %s" % (name, what, bad))
    lane_inputs = entry.get("vehicle_inputs") or {}
    fxf = (t.get("input") or {}).get("id")
    if fxf in lane_inputs and str(lane_inputs[fxf].get("content_sha")) != str(t["input"].get("content_sha")):
        why.append("%s: vehicle lane built on held copy %s, the table on %s"
                   % (name, lane_inputs[fxf].get("content_sha"), t["input"].get("content_sha")))
    if fxf in lane_inputs and lane_inputs[fxf].get("rows") != t["rows"]:
        why.append("%s: vehicle lane read %s rows, the table holds %s" % (name, lane_inputs[fxf].get("rows"), t["rows"]))
    return "; ".join(why) or None


def summary_entries(root):
    s = summary(root)
    if s is None:
        return None
    vin = s.get("vehicle_inputs") or {}
    return [{"name": n, "table": t, "vehicle_inputs": vin} for n, t in sorted(s["tables"].items())]


def year_entries(root):
    got = scan(root, "crashes")
    if got is None:
        return None
    off = [r["case_id_pkey"] for r in got[0] if r.get("accident_year", "") != r["collision_datetime"][:4]]
    return [{"off": off, "rows": len(got[0])}]


def year_rule(entry):
    off = entry["off"]
    if len(off) <= YEAR_MISMATCH_MAX:
        return None
    return "%d of %d crashes have an accident_year that is not their collision_datetime year, %d allowed: %s" % (
        len(off), entry["rows"], YEAR_MISMATCH_MAX, ", ".join(off[:4]))


def column_entries(root):
    s = summary(root)
    if s is None:
        return None
    out = []
    for name, t in sorted(s["tables"].items()):
        got = scan(root, name)
        if got is None:
            return None
        out.append({"name": name, "table": t, "header": got[1], "filled": got[2]})
    return out


def column_rule(entry):
    t, header, filled = entry["table"], entry["header"], entry["filled"]
    added = [c for a in t["added"] for c in a["columns"]]
    if header[len(header) - len(added):] != added or len(header) != t["datasf_columns"] + len(added):
        return "%s: header does not end in the %d added columns summary.json lists" % (entry["name"], len(added))
    empty = [c for c in added if not filled.get(c)]
    return "%s: added columns with no value on any row: %s" % (entry["name"], ", ".join(empty)) if empty else None


def checks():
    C, P, V = loader("crashes"), loader("parties"), loader("victims")
    tables = []
    for name, load in (("crashes", C), ("parties", P), ("victims", V)):
        req = [f for f in FIELDS[name] if f != "collision_datetime"]
        tables.append(Table("crash-augment/%s.csv" % name, load, floor=FLOORS[name], max_drop=0.02, max_growth=0.10,
                            key=KEYS[name], required=req + ["collision_datetime"],
                            dates={"collision_datetime": ("2005-01-01", "+1")}))

    def keys_of(load, fields):
        def f(root):
            rows = load(root)
            return None if rows is None else [tuple(r[x] for x in fields) if len(fields) > 1 else r[fields[0]] for r in rows]
        return f
    return tables + [
        Join("crash-augment/parties.csv>crashes", left=keys_of(P, ["case_id_pkey"]), right=keys_of(C, ["case_id_pkey"]),
             extra_ok=True),
        Join("crash-augment/victims.csv>parties", left=keys_of(V, ["case_id_pkey", "party_number_ckey"]),
             right=keys_of(P, ["case_id_pkey", "party_number_ckey"]), extra_ok=True),
        Each("crash-augment/summary.json", summary_entries, summary_rule,
             "rows equal the held DataSF table; every lane row found, none left over or repeated; one DataSF update"),
        Each("crash-augment/accident_year", year_entries, year_rule,
             "accident_year is the year of collision_datetime, bar a few upstream slips"),
        Each("crash-augment/columns", column_entries, column_rule,
             "header is DataSF's columns then each lane's, and every added column has a value somewhere"),
    ]


def run(root, prev_root=None):
    return quality_run(checks(), root=root, prev_root=prev_root)


def main():
    results = run(paths.ROOT)
    for r in results:
        print("   ", r)
    bad = [r for r in results if not r.ok]
    print("augment_checks: %d of %d checks failed" % (len(bad), len(results)) if bad else
          "augment_checks: %d checks pass" % len(results))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
