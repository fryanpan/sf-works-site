#!/usr/bin/env python3
"""Add a clean make, model and estimated curb weight to every row of DataSF's crash parties and victims tables.

    python3 pipeline/crash-augment/vehicles/vehicle-fields.py            # build from the cached DataSF reads
    python3 pipeline/crash-augment/vehicles/vehicle-fields.py --update   # first re-read any table DataSF changed
    python3 pipeline/crash-augment/vehicles/vehicle_checks.py            # the checks alone, on the built files

INPUTS. Three DataSF tables, from the held copy ../crash_tables.py keeps (data/socrata-cache/crash-augment/,
gitignored): parties 8gtc-pjc6 and victims nwes-mmgh, for their vehicle_make, vehicle_year, stwd_vehicle_type and
party_type; and crashes ubvf-ztfx, for its case ids and dates. NHTSA's vPIC API names the makes and
models and gives curb weights (vehicle_vpic.py, cached under .cache/crash-augment/vpic/).

--update first brings that held copy up to date (crash_tables.refresh: DataSF's `rowsUpdatedAt`, then only the
rows whose `data_updated_at` moved, recorded as "crash-augment:<id>" in data/pipeline-state/sources.json), unless
CRASH_TABLES_HELD is set because ../crash-augment.py already did. vPIC is asked only for makes and model years it
has not answered before, so a rerun with no new data makes no network call at all.

OUTPUTS, in .cache/crash-augment/vehicles/ (gitignored; CRASH_AUGMENT_VEHICLES_OUT moves it), sorted by
key, with no run stamps:

  parties-vehicles.csv   one row per parties row, keyed by unique_id
  victims-vehicles.csv   one row per victims row, keyed by unique_id (victim_id beside it)
  crashes-vehicles.csv   one row per crash, keyed by case_id_pkey: its motor vehicles and the heaviest
  inputs.json            each input's row count and DataSF marker, which the checks hold the outputs to

and, committed beside this script because they are small and are what a reviewer reads:

  make-model-lookup.csv  every distinct vehicle_make string, as the parser keys it, with the clean make
                         and model it reads and the rows that carry it
  body-type-averages.json  the body-type fallback weights, and the rows each is averaged over
  match-summary.json     how many rows and distinct strings each match method covers

THE NEW COLUMNS (parties and victims alike; a victim's columns describe the vehicle the victim was in or
on, read from the victim row's own party fields):

  vehicle_make_clean           vPIC's make name, e.g. TOYOTA, MERCEDES-BENZ; empty when not recognised
  vehicle_model_clean          vPIC's model name, e.g. Highlander, F-150, Model 3; empty when not named
  estimated_vehicle_weight_lb  curb weight in pounds, rounded to the pound; empty when there is no source
  vehicle_match_method         how the weight was found:
      exact_make_model_year    mean curb weight of the model's trims in its model year
      model_10yr_avg           the model with no usable year: mean over the ten model years ending at the
                               crash year, or, when a year is given but Transport Canada has no trims
                               for it, over the ten model years around it (year-5 to year+4)
      body_type_avg            no model weight: the mean of every exact_make_model_year weight among
                               parties rows of the same light body type (body-type-averages.json)
      unmatched                no weight, for the reason given
      not_applicable           a pedestrian, a bicyclist, or a non-motor body type; its make and model
                               are left empty too, since vPIC lists no bicycles
  vehicle_match_reason         why a row fell back or has no weight; empty for exact_make_model_year
  vehicle_body_type_clean      stwd_vehicle_type with its typos folded ("Passenge Car" is Passenger Car)

Nothing is guessed. A string the parser cannot read stays empty with its reason, and a body type with no
average (motorcycles, buses, heavy trucks, which Transport Canada does not measure) stays unmatched.
After every build the checks in vehicle_checks.py run on the new files before they replace the old
ones; a failing check leaves the previous build in place and exits 1.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import concurrent.futures as cf
import csv
import io
import json
import os
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))  # crash_tables.py, the held DataSF tables every lane reads
import vehicle_parse  # noqa: E402
import vehicle_vpic  # noqa: E402
import vehicle_weight  # noqa: E402

OUT = os.environ.get("CRASH_AUGMENT_VEHICLES_OUT") or os.path.join(paths.ROOT, ".cache", "crash-augment", "vehicles")
LOOKUP = os.path.join(HERE, "make-model-lookup.csv")
BODY_AVG = os.path.join(HERE, "body-type-averages.json")
SUMMARY = os.path.join(HERE, "match-summary.json")

PARTIES, VICTIMS, CRASHES = "8gtc-pjc6", "nwes-mmgh", "ubvf-ztfx"
VEHICLE_COLS = ["unique_id", "case_id_pkey", "party_number_ckey", "party_type", "collision_datetime",
                "vehicle_year", "vehicle_make", "stwd_vehicle_type"]
SELECT = {PARTIES: ",".join(VEHICLE_COLS), VICTIMS: ",".join(VEHICLE_COLS + ["victim_id"]),
          CRASHES: "case_id_pkey,collision_datetime"}

NEW_COLS = ["vehicle_make_clean", "vehicle_model_clean", "estimated_vehicle_weight_lb", "vehicle_match_method",
            "vehicle_match_reason", "vehicle_body_type_clean"]
PARTY_OUT = ["unique_id", "case_id_pkey", "party_number_ckey"] + NEW_COLS
VICTIM_OUT = ["unique_id", "victim_id", "case_id_pkey", "party_number_ckey"] + NEW_COLS
CRASH_OUT = ["case_id_pkey", "motor_vehicle_parties", "vehicles_with_weight", "heaviest_vehicle_weight_lb",
             "heaviest_vehicle_make_clean", "heaviest_vehicle_model_clean"]
METHODS = ("exact_make_model_year", "model_10yr_avg", "body_type_avg", "unmatched", "not_applicable")
WEIGHED = METHODS[:3]

# stwd_vehicle_type spellings folded into one, so a typo does not make its own body type.
BODY_SPELLINGS = {"Passenge Car": "Passenger Car", "Sports Utility Vehicle": "Sport Utility Vehicle",
                  "Sport Utility Vehicleicle": "Sport Utility Vehicle", "Minvian": "Minivan",
                  "Other Commerical": "Other Commercial"}
# The light body types a body-type average may stand in for. Heavier types (buses, tractors, two-axle trucks)
# and motorcycles get no average: Transport Canada measures neither, so an average of the light vehicles
# that happen to be coded that way would be a guess.
LIGHT_BODY = ("Passenger Car", "Sport Utility Vehicle", "Pickup or Panel Truck", "Minivan", "Police Car",
              "Passenger Car with Trailer", "Pickup or Panel Truck with Trailer")
BODY_AVG_MIN_ROWS = 100
# Two-wheelers and heavy vehicles, whose weight a light-vehicle model cannot be: Transport Canada's trims are
# cars, SUVs, vans and pickups, so a motorcycle-coded row read as a car model is a conflict, and so is a
# bus or tractor read as something under HEAVY_FLOOR_LB. Those rows are left unmatched and say so.
TWO_WHEEL_BODY = ("Motorcycle", "Motor Driven Cycle/Scooter", "Moped", "Police Motorcycle", "Motorized Bicycle")
HEAVY_BODY = ("Other Bus", "Public Transit Authority", "School Bus", "Tour Bus", "Truck or Truck Tractor",
              "Truck or Truck Tractor with Trailer", "Semi", "Two Axle Truck", "Three or More Axle Truck",
              "Two Axle Tank Truck", "Three Axle Tank Truck", "Fire Truck", "Truck Tractor", "Paratransit",
              "Motor Home", "Two Axle Tow Truck", "Three Axle Tow Truck")
TWO_WHEEL_MAX_LB = 1500
HEAVY_FLOOR_LB = 3000
NON_MOTOR_PARTY = {"Pedestrian": "party is a pedestrian", "Bicyclist": "party is a bicyclist"}
NON_MOTOR_BODY = {"Pedestrian", "Bicycle", "Electric Bicycle", "Misc. Non-Motor Vehicle",
                  "Go-ped, ZIP Electric Scooter, Motorboard", "Electrically Motorized Board"}
# Probe years: a make with no Canadian trims in any of these is not asked year by year.
PROBE_YEARS = (1995, 2005, 2012, 2018, 2023)
LIGHT_TYPES = {"car", "truck", "multipurpose passenger vehicle (mpv)"}
THREADS = 1


# ---- reading DataSF ------------------------------------------------------------------------------------

def read_tables(update):
    """{fxf: (rows, marker, read_on)} for the three tables, from the held copy that ../crash_tables.py keeps.

    With --update the held copy is first brought up to date (crash_tables.refresh), unless CRASH_TABLES_HELD is set,
    which ../crash-augment.py sets after refreshing it once, so every lane builds on the same read."""
    import crash_tables  # ../, on the path below
    if update and not os.environ.get("CRASH_TABLES_HELD"):
        crash_tables.refresh(update=True)
    out = {}
    for name, fxf in (("parties", PARTIES), ("victims", VICTIMS), ("crashes", CRASHES)):
        rows = crash_tables.rows(name, columns=SELECT[fxf].split(","))
        meta = crash_tables.info(name)
        out[fxf] = (rows, meta["rowsUpdatedAt"], meta["read_on"])
        print("  %s: %d rows held, read %s (DataSF rowsUpdatedAt %s)" % (fxf, len(rows), meta["read_on"], meta["rowsUpdatedAt"]))
    return out


# ---- the parts ------------------------------------------------------------------------------------------

def body_type(row):
    b = " ".join((row.get("stwd_vehicle_type") or "").split())
    return BODY_SPELLINGS.get(b, b)


def crash_year(row):
    try:
        return int((row.get("collision_datetime") or "")[:4])
    except ValueError:
        return None


def model_year(row):
    """The vehicle_year as a four-digit model year no later than the year after the crash, else None."""
    y = (row.get("vehicle_year") or "").strip()
    if len(y) != 4 or not y.isdigit():
        return None
    y, cy = int(y), crash_year(row)
    return y if 1900 <= y <= (cy + 1 if cy else 9999) else None


class Vpic(object):
    """The vPIC answers the build needs, fetched in parallel the first time and read from cache after."""

    def __init__(self, api=vehicle_vpic):
        self.api = api
        self._models, self._specs = {}, {}
        self._makes = None

    def makes(self):
        if self._makes is None:
            self._makes = self.api.makes()
        return self._makes

    def prefetch_models(self, makes):
        todo = sorted(m for m in set(makes) if m not in self._models)
        with cf.ThreadPoolExecutor(THREADS) as ex:
            for m, res in zip(todo, ex.map(self.api.models, todo)):
                self._models[m] = res

    def models(self, make):
        if make not in self._models:
            self._models[make] = self.api.models(make)
        return self._models[make]

    def prefetch_specs(self, pairs):
        todo = sorted(p for p in set(pairs) if p not in self._specs)
        with cf.ThreadPoolExecutor(THREADS) as ex:
            for p, res in zip(todo, ex.map(lambda p: self.api.canadian_specs(*p), todo)):
                self._specs[p] = res

    def specs(self, make, year):
        if (make, year) not in self._specs:
            self._specs[(make, year)] = self.api.canadian_specs(make, year)
        return self._specs[(make, year)]


def ten_years(row, year):
    """The model years the ten-year average spans for this row, given its usable model year or None."""
    if year is not None:
        return range(year - 5, year + 5)
    cy = crash_year(row)
    return range(cy - 9, cy + 1) if cy else range(0)


# ---- the build ------------------------------------------------------------------------------------------

def build(tables, vpic=None, log=print):
    """Every output, as {name: text}. `tables` is {fxf: (rows, marker, read_on)}; `vpic` a Vpic."""
    vpic = vpic or Vpic()
    parties, victims, crashes = (tables[f][0] for f in (PARTIES, VICTIMS, CRASHES))
    rows_all = list(parties) + list(victims)

    # 1. Parse every distinct string once.
    raw_n = collections.Counter(r.get("vehicle_make") or "" for r in parties)
    raw_v = collections.Counter(r.get("vehicle_make") or "" for r in victims)
    keys = {s: vehicle_parse.lookup_key(s) for s in set(raw_n) | set(raw_v)}
    probe = vehicle_parse.Matcher(vpic.makes(), lambda m: set())
    exact = collections.Counter()
    for s, n in raw_n.items():
        k = keys[s]
        if k and "/" not in k and " " not in k:
            hit = probe.find_make([k])
            if hit and hit[2] != "fuzzy":
                exact[hit[0]] += n
    common = sorted(m for m, n in exact.items() if n >= vehicle_parse.COMMON_MAKE_ROWS)
    makes_hit = set()
    for k in set(keys.values()):
        segs = [seg.split(" ") for seg in k.split("/") if seg]
        while len(segs) > 1 and all(vehicle_parse.squash(w) in vehicle_parse.GENERIC for w in segs[0]):
            segs = segs[1:]
        if segs:
            hit = probe.find_make(segs[0]) or (probe.find_make(segs[0][:1]) if segs[0] else None)
            if hit:
                makes_hit.add(hit[0])
    for a in probe.aliases.values():
        makes_hit.add(a[0])
    vpic.prefetch_models(makes_hit)
    matcher = vehicle_parse.Matcher(vpic.makes(), vpic.models, common_makes=common)
    parsed = {k: matcher.parse_key(k) for k in sorted(set(keys.values()))}
    log("  parsed %d distinct strings (%d keys); %d makes asked of vPIC" % (len(keys), len(parsed), len(makes_hit)))

    # 2. Ask Transport Canada for each (make, model year) a row needs, makes with any trims only.
    def names_for(make):
        """{model: names it goes by}: its own, plus every alias model-aliases.csv gives it."""
        out = {m: {m} for m in set(matcher.index(make).values())}
        for (mk, alias), model in matcher.model_aliases.items():
            if mk == make and model in out:
                out[model].add(alias)
        return out
    weights = vehicle_weight.Weights(vpic.specs, names_for)
    # Transport Canada measures cars, trucks and MPVs; a make vPIC lists only for motorcycles, buses or low
    # speed vehicles is not asked.
    light = {m for m, types in vpic.makes().items() if types & LIGHT_TYPES}
    made = sorted({p.make for p in parsed.values() if p.model and p.make in light})
    vpic.prefetch_specs([(m, y) for m in made for y in PROBE_YEARS])
    covered = {m for m in made if any(vpic.specs(m, y) for y in PROBE_YEARS)}
    need = set()
    for r in rows_all:
        p = parsed[keys[r.get("vehicle_make") or ""]]
        if p.model and p.make in covered:
            y = model_year(r)
            if y is not None:
                need.add((p.make, y))
    vpic.prefetch_specs(need)
    need2 = set()
    for r in rows_all:
        p = parsed[keys[r.get("vehicle_make") or ""]]
        if p.model and p.make in covered:
            y = model_year(r)
            if y is None or weights.model_year(p.make, p.model, y) is None:
                need2 |= {(p.make, yy) for yy in ten_years(r, y)}
    vpic.prefetch_specs(need2)
    log("  %d makes have Transport Canada trims; %d make-years asked" % (len(covered), len(need | need2)))

    # 3. Each row's fields, before the body-type fallback.
    def model_weight(r, p):
        if not p.model:
            return None, None, p.reason or "no model named"
        if p.make not in covered:
            return None, None, "no Transport Canada curb weights for make"
        y = model_year(r)
        if y is not None:
            w = weights.model_year(p.make, p.model, y)
            if w is not None:
                return w, "exact_make_model_year", None
        w, n = weights.window(p.make, p.model, ten_years(r, y))
        if w is not None:
            why = ("no usable model year" if y is None else "no Transport Canada trims for model year %d" % y)
            return w, "model_10yr_avg", "%s; mean of %d model years" % (why, n)
        return None, None, "no Transport Canada trims for this model in these model years"

    def first_pass(r):
        p = parsed[keys[r.get("vehicle_make") or ""]]
        out = {"vehicle_make_clean": p.make, "vehicle_model_clean": p.model}
        pt, bt = r.get("party_type") or "", body_type(r)
        if pt in NON_MOTOR_PARTY or bt in NON_MOTOR_BODY:
            # vPIC lists no bicycles, so a bicycle brand that matches a vPIC make (RIDLEY, a motorcycle
            # maker too) is a collision, not a reading. A non-motor row's make and model are left empty.
            out.update(vehicle_make_clean=None, vehicle_model_clean=None, w=None, method="not_applicable",
                       reason=NON_MOTOR_PARTY.get(pt) or "non-motor body type: %s" % bt)
            return out
        w, method, reason = model_weight(r, p)
        if w is not None and bt in TWO_WHEEL_BODY and w > TWO_WHEEL_MAX_LB:
            w, method, reason = None, "unmatched", "body type %s conflicts with %s %s (%d lb)" % (bt, p.make, p.model, w)
        elif w is not None and bt in HEAVY_BODY and w < HEAVY_FLOOR_LB:
            w, method, reason = None, "unmatched", "body type %s conflicts with %s %s (%d lb)" % (bt, p.make, p.model, w)
        out.update(w=w, method=method, reason=reason)
        return out

    first_p = [first_pass(r) for r in parties]
    first_v = [first_pass(r) for r in victims]

    # 4. Body-type averages, from the parties table's exact weights only.
    acc = collections.defaultdict(list)
    for r, f in zip(parties, first_p):
        if f["method"] == "exact_make_model_year" and body_type(r) in LIGHT_BODY:
            acc[body_type(r)].append(f["w"])
    body_avg = {b: {"weight_lb": round(sum(v) / len(v)), "rows": len(v)}
                for b, v in sorted(acc.items()) if len(v) >= BODY_AVG_MIN_ROWS}

    def finish(r, f):
        w, method, reason = f["w"], f["method"], f["reason"]
        if method is None:
            bt = body_type(r) or "Not Stated"
            if bt in body_avg:
                w, method, reason = body_avg[bt]["weight_lb"], "body_type_avg", "%s; %s average" % (reason, bt)
            else:
                method = "unmatched"
                reason = "%s; no body-type average for %s" % (reason, bt)
        return {"vehicle_make_clean": f["vehicle_make_clean"] or "", "vehicle_model_clean": f["vehicle_model_clean"] or "",
                "estimated_vehicle_weight_lb": "" if w is None else str(int(round(w))),
                "vehicle_match_method": method, "vehicle_match_reason": reason or "",
                "vehicle_body_type_clean": body_type(r)}

    out_p = []
    for r, f in zip(parties, first_p):
        o = {k: r.get(k) or "" for k in ("unique_id", "case_id_pkey", "party_number_ckey")}
        o.update(finish(r, f))
        out_p.append(o)
    out_v = []
    for r, f in zip(victims, first_v):
        o = {k: r.get(k) or "" for k in ("unique_id", "victim_id", "case_id_pkey", "party_number_ckey")}
        o.update(finish(r, f))
        out_v.append(o)
    assert len(out_p) == len(parties) and len(out_v) == len(victims), "a row was dropped or added"

    # 5. The crash rollup: one row per crash in ubvf-ztfx.
    by_case = collections.defaultdict(list)
    for o in out_p:
        by_case[o["case_id_pkey"]].append(o)
    out_c = []
    for c in crashes:
        cid = c.get("case_id_pkey") or ""
        motor = [o for o in by_case.get(cid, []) if o["vehicle_match_method"] != "not_applicable"]
        weighed = [o for o in motor if o["estimated_vehicle_weight_lb"]]
        top = max(weighed, key=lambda o: (int(o["estimated_vehicle_weight_lb"]), o["party_number_ckey"]), default=None)
        out_c.append({"case_id_pkey": cid, "motor_vehicle_parties": str(len(motor)), "vehicles_with_weight": str(len(weighed)),
                      "heaviest_vehicle_weight_lb": top["estimated_vehicle_weight_lb"] if top else "",
                      "heaviest_vehicle_make_clean": top["vehicle_make_clean"] if top else "",
                      "heaviest_vehicle_model_clean": top["vehicle_model_clean"] if top else ""})
    assert len(out_c) == len(crashes)

    # 6. The committed review files.
    n_p = collections.Counter(keys[r.get("vehicle_make") or ""] for r in parties)
    n_v = collections.Counter(keys[r.get("vehicle_make") or ""] for r in victims)
    lookup = [{"key": k, "vehicle_make_clean": p.make or "", "vehicle_model_clean": p.model or "",
               "make_how": p.make_how or "", "model_how": p.model_how or "", "reason": p.reason or "",
               "party_rows": n_p.get(k, 0), "victim_rows": n_v.get(k, 0)}
              for k, p in sorted(parsed.items())]
    summary = summarise(out_p, out_v, parties, lookup)

    inputs = {f: {"rows": len(tables[f][0]), "rowsUpdatedAt": tables[f][1]} for f in (PARTIES, VICTIMS, CRASHES)}
    return {
        "parties-vehicles.csv": to_csv(sorted(out_p, key=sort_key), PARTY_OUT),
        "victims-vehicles.csv": to_csv(sorted(out_v, key=sort_key), VICTIM_OUT),
        "crashes-vehicles.csv": to_csv(sorted(out_c, key=lambda o: num(o["case_id_pkey"])), CRASH_OUT),
        "inputs.json": json.dumps(inputs, indent=1, sort_keys=True) + "\n",
        "make-model-lookup.csv": to_csv(lookup, list(lookup[0].keys()) if lookup else ["key"]),
        "body-type-averages.json": json.dumps(body_avg, indent=1, sort_keys=True) + "\n",
        "match-summary.json": json.dumps(summary, indent=1, sort_keys=True) + "\n",
    }


def summarise(out_p, out_v, parties, lookup):
    """Match rates by method: share of party rows, of motor-vehicle party rows, and of distinct strings."""
    def rates(rows):
        c = collections.Counter(o["vehicle_match_method"] for o in rows)
        n = len(rows)
        motor = n - c["not_applicable"]
        return {m: {"rows": c[m], "share": round(c[m] / n, 4) if n else 0,
                    "share_of_motor_vehicles": round(c[m] / motor, 4) if motor and m != "not_applicable" else None}
                for m in METHODS}
    motor_p = [o for o in out_p if o["vehicle_match_method"] != "not_applicable"]
    with_text = [o for o, r in zip(out_p, parties) if vehicle_parse.lookup_key(r.get("vehicle_make")) and o["vehicle_match_method"] != "not_applicable"]
    keyed = [l for l in lookup if l["key"]]
    hows = collections.Counter((l["make_how"] or "none") + "/" + (l["model_how"] or "none") for l in keyed)
    return {
        "parties": rates(out_p),
        "victims": rates(out_v),
        "parties_motor_vehicle_rows": len(motor_p),
        "parties_motor_vehicle_rows_with_text": len(with_text),
        "parties_motor_vehicle_make_clean": sum(1 for o in motor_p if o["vehicle_make_clean"]),
        "parties_motor_vehicle_model_clean": sum(1 for o in motor_p if o["vehicle_model_clean"]),
        "distinct_strings": len(keyed),
        "distinct_strings_by_make_and_model_how": dict(sorted(hows.items())),
        "distinct_strings_with_make": sum(1 for l in keyed if l["vehicle_make_clean"]),
        "distinct_strings_with_model": sum(1 for l in keyed if l["vehicle_model_clean"]),
    }


def num(s):
    try:
        return (0, int(s), "")
    except (TypeError, ValueError):
        return (1, 0, s or "")


def sort_key(o):
    return num(o["unique_id"])


def to_csv(rows, cols):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ---- writing, after the checks pass ----------------------------------------------------------------------

COMMITTED = {"make-model-lookup.csv": LOOKUP, "body-type-averages.json": BODY_AVG, "match-summary.json": SUMMARY}


def write(outputs, out_dir=OUT, committed=None, check_args=None):
    """Stage every output, run the checks against the live copy, and replace it only when they pass."""
    from lib import stable
    import vehicle_checks
    committed = COMMITTED if committed is None else committed
    os.makedirs(os.path.dirname(os.path.abspath(out_dir)), exist_ok=True)
    stage = tempfile.mkdtemp(prefix="vehicles-stage-", dir=os.path.dirname(os.path.abspath(out_dir)))
    try:
        for name, text in outputs.items():
            with open(os.path.join(stage, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        results = vehicle_checks.run(stage, prev_root=out_dir if os.path.isdir(out_dir) else None, **(check_args or {}))
        failed = [r for r in results if not r.ok]
        for r in failed:
            print("   ", r)
        if failed:
            print("vehicle-fields: %d check(s) failed; the previous build is kept" % len(failed))
            return False
        changed = []
        for name, text in outputs.items():
            dest = committed.get(name) or os.path.join(out_dir, name)
            if stable.write_text(dest, text):
                changed.append(name)
        print("vehicle-fields: %d checks pass; %s" % (len(results), ("wrote " + ", ".join(changed)) if changed else "nothing changed"))
        return True
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true", help="re-read any DataSF table whose rowsUpdatedAt moved")
    args = ap.parse_args()
    tables = read_tables(args.update)
    before = dict(vehicle_vpic.STATS)
    outputs = build(tables)
    print("  vPIC: %d answers from cache, %d fetched" % (vehicle_vpic.STATS["cached"] - before["cached"],
                                                       vehicle_vpic.STATS["fetched"] - before["fetched"]))
    sys.exit(0 if write(outputs) else 1)


if __name__ == "__main__":
    main()
