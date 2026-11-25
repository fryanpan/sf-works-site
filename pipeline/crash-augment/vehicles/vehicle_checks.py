#!/usr/bin/env python3
"""The quality checks every vehicle-fields build must pass before its files replace the last good build.

    python3 pipeline/crash-augment/vehicles/vehicle_checks.py           # check the built files; exit 1 on a failure
    python3 pipeline/crash-augment/vehicles/vehicle_checks.py <dir>     # check the files in another folder

vehicle-fields.py runs these on its staged output, with the previous build as `prev_root`, and keeps the
previous build when any fails (pipeline/README.md, rule 2). Each check is named "<file>.<check>":

  rows, unique, required   lib/quality.py's Table: a floor, no fall of more than 2% (or rise of more than
                           10%) against the previous build, keys unique, key fields never empty.
  rows_exact               each output has exactly the rows its DataSF input had (inputs.json).
  join                     every victim's party is a parties row, once; every party's crash is a crash row.
  victim_matches_party     a victim's vehicle columns equal its party's, since both read the same fields.
  each                     per row: a known method; a weight exactly when the method gives one; a reason
                           whenever the row fell back or has no weight; no model without a make; and the
                           weight within the bounds for its body type (WEIGHT_BOUNDS).
  rate[...]                match rates no lower than RATE_FLOORS, set a little under the first full build
                           (2026-11-25), so a parser or vPIC regression that loses matches fails loudly.
  golden                   every string in golden.csv, each read by hand, comes out of the lookup as the
                           make and model written beside it.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv
import json
import os

from lib.quality import Each, Join, Result, Table, run as quality_run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vehicle_parse  # noqa: E402

GOLDEN = os.path.join(HERE, "golden.csv")
OUT = os.environ.get("CRASH_AUGMENT_VEHICLES_OUT") or os.path.join(paths.ROOT, ".cache", "crash-augment", "vehicles")
PARTIES, VICTIMS, CRASHES = "8gtc-pjc6", "nwes-mmgh", "ubvf-ztfx"
METHODS = ("exact_make_model_year", "model_10yr_avg", "body_type_avg", "unmatched", "not_applicable")
WEIGHED = METHODS[:3]
TWO_WHEEL = {"Motorcycle", "Motor Driven Cycle/Scooter", "Moped", "Police Motorcycle", "Motorized Bicycle"}
HEAVY = {"Other Bus", "Public Transit Authority", "School Bus", "Tour Bus", "Truck or Truck Tractor",
         "Truck or Truck Tractor with Trailer", "Semi", "Two Axle Truck", "Three or More Axle Truck",
         "Two Axle Tank Truck", "Three Axle Tank Truck", "Fire Truck", "Truck Tractor", "Paratransit",
         "Motor Home", "Two Axle Tow Truck", "Three Axle Tow Truck"}
# Curb weight bounds in lb. Passenger vehicles and light trucks run from about 1,800 lb (a Smart Fortwo)
# to about 8,000 (a dual-rear-wheel pickup); 1,500 to 14,000 leaves room without letting a unit error in.
WEIGHT_BOUNDS = {"two_wheel": (150, 1500), "heavy": (3000, 80000), "light": (1500, 14000)}
# Floors, as shares. "motor" is parties rows that are not pedestrians, bicyclists or non-motor body types;
# "motor_text" those that also have a vehicle_make string. Each floor sits a few points under the first
# full build (2026-11-25), whose figure is beside it.
RATE_FLOORS = {
    "make_of_motor_text": 0.95,        # 0.982
    "model_of_motor_text": 0.28,       # 0.310: before 2018 the field is mostly a make alone
    "weight_of_motor": 0.76,           # 0.798
    "exact_of_motor": 0.24,            # 0.261
    "exact_or_10yr_of_motor": 0.25,    # 0.274
    "model_weight_of_named": 0.90,     # 0.935: rows with a model whose weight is that model's
    "distinct_with_make": 0.58,        # 0.614
    "distinct_with_model": 0.32,       # 0.346
}
GOLDEN_MAX_MISSING = 0.10
# Fewest rows each output may hold. The tables held 140,843 parties, 84,943 victims and 66,991 crashes
# on 2026-11-25; the floors catch an empty or truncated read, and the 2% drop bound catches the rest.
ROW_FLOORS = {"parties-vehicles.csv": 100000, "victims-vehicles.csv": 50000, "crashes-vehicles.csv": 40000}


def read_csv(root, name):
    p = os.path.join(root, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def loader(name):
    cache = {}

    def load(root):
        if root not in cache:
            cache[root] = read_csv(root, name)
        return cache[root]
    load.__name__ = name
    return load


def bounds_for(body):
    return WEIGHT_BOUNDS["two_wheel" if body in TWO_WHEEL else "heavy" if body in HEAVY else "light"]


def row_rule(o):
    """None when an output row is internally consistent, else what is wrong with it."""
    m, w, why = o.get("vehicle_match_method"), o.get("estimated_vehicle_weight_lb"), o.get("vehicle_match_reason")
    uid = o.get("unique_id")
    if m not in METHODS:
        return "%s: method %r" % (uid, m)
    if (m in WEIGHED) != bool(w):
        return "%s: method %s with weight %r" % (uid, m, w)
    if m != "exact_make_model_year" and not why:
        return "%s: %s with no reason" % (uid, m)
    if o.get("vehicle_model_clean") and not o.get("vehicle_make_clean"):
        return "%s: a model with no make" % uid
    if w:
        try:
            lb = int(w)
        except ValueError:
            return "%s: weight %r is not a whole number" % (uid, w)
        lo, hi = bounds_for(o.get("vehicle_body_type_clean"))
        if not lo <= lb <= hi:
            return "%s: %d lb outside %d-%d for %s" % (uid, lb, lo, hi, o.get("vehicle_body_type_clean"))
    return None


def exact_rows(root):
    """Each output's row count against its input's, from inputs.json."""
    try:
        with open(os.path.join(root, "inputs.json"), encoding="utf-8") as fh:
            inputs = json.load(fh)
    except (OSError, ValueError) as exc:
        return [Result("inputs.read", False, str(exc))]
    out = []
    for name, fxf in (("parties-vehicles.csv", PARTIES), ("victims-vehicles.csv", VICTIMS), ("crashes-vehicles.csv", CRASHES)):
        rows = read_csv(root, name)
        n, want = (len(rows) if rows is not None else -1), inputs.get(fxf, {}).get("rows")
        out.append(Result("%s.rows_exact" % name, n == want, "%d rows out, %s in" % (n, want)))
    return out


def victim_consistency(root):
    parties, victims = read_csv(root, "parties-vehicles.csv"), read_csv(root, "victims-vehicles.csv")
    if parties is None or victims is None:
        return [Result("victims-vehicles.csv.victim_matches_party", False, "no data on disk")]
    cols = ("vehicle_make_clean", "vehicle_model_clean", "estimated_vehicle_weight_lb", "vehicle_match_method")
    by = {(p["case_id_pkey"], p["party_number_ckey"]): p for p in parties}
    differ = [v["unique_id"] for v in victims
              if (v["case_id_pkey"], v["party_number_ckey"]) in by
              and any(v[c] != by[(v["case_id_pkey"], v["party_number_ckey"])][c] for c in cols)]
    allowed = int(0.005 * len(victims))
    return [Result("victims-vehicles.csv.victim_matches_party", len(differ) <= allowed,
                   "%d of %d victims differ from their party, %d allowed%s" % (
                       len(differ), len(victims), allowed, (": " + ", ".join(differ[:4])) if differ else ""))]


def rates(root, floors=None):
    floors = floors or RATE_FLOORS
    parties = read_csv(root, "parties-vehicles.csv")
    lookup = read_csv(root, "make-model-lookup.csv")
    if parties is None or lookup is None:
        return [Result("rate.read", False, "no data on disk")]
    motor = [o for o in parties if o["vehicle_match_method"] != "not_applicable"]
    # A motor vehicle row with no string at all carries the reason "no make named" and no make.
    text_keys = {l["key"] for l in lookup if l["key"]}
    motor_text = [o for o in motor if not (o["vehicle_match_reason"].startswith("no make named") and not o["vehicle_make_clean"])]
    keyed = [l for l in lookup if l["key"]]

    def share(a, b):
        return (a / b) if b else 0.0
    got = {
        "make_of_motor_text": share(sum(1 for o in motor_text if o["vehicle_make_clean"]), len(motor_text)),
        "model_of_motor_text": share(sum(1 for o in motor_text if o["vehicle_model_clean"]), len(motor_text)),
        "weight_of_motor": share(sum(1 for o in motor if o["estimated_vehicle_weight_lb"]), len(motor)),
        "exact_of_motor": share(sum(1 for o in motor if o["vehicle_match_method"] == "exact_make_model_year"), len(motor)),
        "exact_or_10yr_of_motor": share(sum(1 for o in motor if o["vehicle_match_method"] in WEIGHED[:2]), len(motor)),
        "model_weight_of_named": share(sum(1 for o in motor if o["vehicle_model_clean"] and o["vehicle_match_method"] in WEIGHED[:2]),
                                       sum(1 for o in motor if o["vehicle_model_clean"])),
        "distinct_with_make": share(sum(1 for l in keyed if l["vehicle_make_clean"]), len(text_keys)),
        "distinct_with_model": share(sum(1 for l in keyed if l["vehicle_model_clean"]), len(text_keys)),
    }
    return [Result("rate[%s]" % k, got[k] >= floors[k], "%.3f, floor %.2f" % (got[k], floors[k]))
            for k in sorted(floors)]


def golden(root, path=GOLDEN):
    lookup = read_csv(root, "make-model-lookup.csv")
    if lookup is None:
        return [Result("golden", False, "no lookup on disk")]
    with open(path, encoding="utf-8", newline="") as fh:
        gold = list(csv.DictReader(fh))
    by = {l["key"]: l for l in lookup}
    wrong, missing = [], []
    for g in gold:
        k = vehicle_parse.lookup_key(g["raw"])
        l = by.get(k)
        if l is None:
            missing.append(g["raw"])
            continue
        got = (l["vehicle_make_clean"], l["vehicle_model_clean"])
        want = (g["expected_make"].strip(), g["expected_model"].strip())
        if got != want:
            wrong.append("%r -> %s/%s, expected %s/%s" % (g["raw"], got[0] or "-", got[1] or "-", want[0] or "-", want[1] or "-"))
    ok = not wrong and len(missing) <= GOLDEN_MAX_MISSING * len(gold)
    return [Result("golden", ok, "%d strings: %d wrong, %d no longer in the data%s" % (
        len(gold), len(wrong), len(missing), ("; " + "; ".join(wrong[:6])) if wrong else ""))]


def checks(row_floors=None):
    f = dict(ROW_FLOORS, **(row_floors or {}))
    P, V, C = loader("parties-vehicles.csv"), loader("victims-vehicles.csv"), loader("crashes-vehicles.csv")
    req = ["unique_id", "case_id_pkey", "party_number_ckey", "vehicle_match_method"]
    return [
        Table("parties-vehicles.csv", P, floor=f["parties-vehicles.csv"], max_drop=0.02, max_growth=0.10, key="unique_id", required=req),
        Table("victims-vehicles.csv", V, floor=f["victims-vehicles.csv"], max_drop=0.02, max_growth=0.10, key="unique_id",
              required=req + ["victim_id"]),
        Table("crashes-vehicles.csv", C, floor=f["crashes-vehicles.csv"], max_drop=0.02, max_growth=0.10, key="case_id_pkey",
              required=["case_id_pkey", "motor_vehicle_parties"]),
        Join("victims-vehicles.csv>parties", left=lambda r: [(v["case_id_pkey"], v["party_number_ckey"]) for v in V(r)] if V(r) is not None else None,
             right=lambda r: [(p["case_id_pkey"], p["party_number_ckey"]) for p in P(r)] if P(r) is not None else None, extra_ok=True),
        Join("parties-vehicles.csv>crashes", left=lambda r: [p["case_id_pkey"] for p in P(r)] if P(r) is not None else None,
             right=lambda r: [c["case_id_pkey"] for c in C(r)] if C(r) is not None else None, extra_ok=True),
        Each("parties-vehicles.csv", P, row_rule, "consistent method, weight, reason and bounds"),
        Each("victims-vehicles.csv", V, row_rule, "consistent method, weight, reason and bounds"),
    ]


def run(root, prev_root=None, golden_path=GOLDEN, row_floors=None, rate_floors=None):
    """Every Result for the build in `root`, against the previous build in `prev_root` when given.

    The tests pass small `row_floors` and `rate_floors` and their own golden file; the pipeline uses the
    defaults above."""
    out = quality_run(checks(row_floors), root=root, prev_root=prev_root)

    def rate_check(r):
        return rates(r, rate_floors)

    def golden_check(r):
        return golden(r, golden_path)
    for extra in (exact_rows, victim_consistency, rate_check, golden_check):
        try:
            out += extra(root)
        except Exception as exc:  # noqa: BLE001 - a check that cannot read its data fails
            out.append(Result(getattr(extra, "__name__", "check") + ".read", False, "%s: %s" % (type(exc).__name__, exc)))
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else OUT
    # The committed review files live beside this script; a check of the live build reads them from there.
    if root == OUT:
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="vehicle-checks-")
        try:
            for name in os.listdir(OUT):
                shutil.copy(os.path.join(OUT, name), tmp)
            shutil.copy(os.path.join(HERE, "make-model-lookup.csv"), tmp)
            results = run(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        results = run(root)
    for r in results:
        print(r)
    bad = [r for r in results if not r.ok]
    print("vehicle_checks: %d of %d pass" % (len(results) - len(bad), len(results)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
