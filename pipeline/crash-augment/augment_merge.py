"""Join the vehicle and street lanes' columns onto the full DataSF rows, and write the three augmented tables.

    import augment_merge
    staged = augment_merge.build(stage_dir)   # write crashes.csv, parties.csv, victims.csv and summary.json there

Reads the held DataSF tables through crash_tables.py, one collision year at a time, and the lanes' outputs:

  vehicles/  .cache/crash-augment/vehicles/{parties,victims,crashes}-vehicles.csv (CRASH_AUGMENT_VEHICLES_OUT)
  street/    out/crash-augment/street/crash-street.csv

and writes, in the folder it is given:

  crashes.csv   every ubvf-ztfx column, then the street columns, then the vehicle rollup, one row per crash
  parties.csv   every 8gtc-pjc6 column, then the six vehicle columns, one row per party
  victims.csv   every nwes-mmgh column, then the six vehicle columns, one row per victim
  summary.json  row counts, the columns each table adds, and the DataSF marker and read date of each input

Rows come out in collision-year order and by key within a year (crash_tables.iter_rows), so a rerun on the same
inputs writes the same bytes. A lane row is matched by the table's key (case_id_pkey for crashes, unique_id for
parties and victims). A key with no lane row is written with that lane's columns empty and counted in the summary
under `missing_lane_rows`; augment_checks.py fails the build on any, and on a lane row whose key is not held.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import crash_tables  # noqa: E402

VEHICLES_OUT = os.environ.get("CRASH_AUGMENT_VEHICLES_OUT") or os.path.join(paths.ROOT, ".cache", "crash-augment", "vehicles")
STREET_CSV = os.path.join(paths.ROOT, "out", "crash-augment", "street", "crash-street.csv")

# The columns each lane adds, in output order. Join keys and columns the DataSF row already holds are left out.
VEHICLE_COLS = ["vehicle_make_clean", "vehicle_model_clean", "estimated_vehicle_weight_lb", "vehicle_match_method",
                "vehicle_match_reason", "vehicle_body_type_clean"]
ROLLUP_COLS = ["motor_vehicle_parties", "vehicles_with_weight", "heaviest_vehicle_weight_lb",
               "heaviest_vehicle_make_clean", "heaviest_vehicle_model_clean"]
STREET_SKIP = {"case_id_pkey", "collision_date"}

# table -> (key, [(lane name, lane file, columns or None for "every column but the key and STREET_SKIP")])
PLAN = {
    "crashes": ("case_id_pkey", [("street", STREET_CSV, None),
                                 ("vehicles", os.path.join(VEHICLES_OUT, "crashes-vehicles.csv"), ROLLUP_COLS)]),
    "parties": ("unique_id", [("vehicles", os.path.join(VEHICLES_OUT, "parties-vehicles.csv"), VEHICLE_COLS)]),
    "victims": ("unique_id", [("vehicles", os.path.join(VEHICLES_OUT, "victims-vehicles.csv"), VEHICLE_COLS)]),
}


def street_columns(path=STREET_CSV):
    with open(path, encoding="utf-8", newline="") as fh:
        head = next(csv.reader(fh))
    return [c for c in head if c not in STREET_SKIP]


def read_lane(path, key, cols):
    """({key: [values]}, extra keys counted twice) for one lane file, keeping only `cols`."""
    out, dup = {}, []
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            k = r[key]
            if k in out:
                dup.append(k)
            out[k] = [r.get(c, "") for c in cols]
    return out, dup


def build_table(name, dest):
    """Write one augmented table to `dest`; return its summary entry."""
    key, lanes = PLAN[name]
    base = crash_tables.columns(name)
    loaded, added = [], []
    for lane, path, cols in lanes:
        cols = cols or street_columns(path)
        rows, dup = read_lane(path, key, cols)
        loaded.append((lane, cols, rows, dup))
        added.append({"lane": lane, "file": os.path.relpath(path, paths.ROOT), "columns": cols})
    extra_cols = []
    n = 0
    missing = {lane: 0 for lane, _, _, _ in loaded}
    seen = set()
    with open(dest, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        header = None
        for row in crash_tables.iter_rows(name):
            if header is None:
                extra_cols = sorted(c for c in row if c not in base)
                header = base + extra_cols + [c for _, cols, _, _ in loaded for c in cols]
                w.writerow(header)
            k = row[key]
            seen.add(k)
            out = [row.get(c, "") for c in base + extra_cols]
            for lane, cols, rows, _ in loaded:
                vals = rows.get(k)
                if vals is None:
                    missing[lane] += 1
                    vals = [""] * len(cols)
                out += vals
            w.writerow(out)
            n += 1
    return {
        "rows": n,
        "key": key,
        "datasf_columns": len(base) + len(extra_cols),
        "added": added,
        "missing_lane_rows": missing,
        "lane_rows_not_held": {lane: sum(1 for k in rows if k not in seen) for lane, _, rows, _ in loaded},
        "lane_keys_repeated": {lane: len(dup) for lane, _, _, dup in loaded},
        "input": crash_tables.info(name),
    }


def build(out_dir):
    """Write every table and summary.json into `out_dir`; return the summary."""
    os.makedirs(out_dir, exist_ok=True)
    summary = {
        "about": "DataSF's three injury-crash tables with the crash-augment columns added; built by "
                 "pipeline/crash-augment/crash-augment.py. Columns and rules: pipeline/crash-augment/README.md.",
        "tables": {},
    }
    # What the vehicle lane says it read, so the checks can hold every lane to the same DataSF update.
    inputs = os.path.join(VEHICLES_OUT, "inputs.json")
    summary["vehicle_inputs"] = json.load(open(inputs, encoding="utf-8")) if os.path.exists(inputs) else {}
    for name in ("crashes", "parties", "victims"):
        summary["tables"][name] = build_table(name, os.path.join(out_dir, name + ".csv"))
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    return summary
