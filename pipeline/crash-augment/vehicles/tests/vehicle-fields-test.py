#!/usr/bin/env python3
"""Tests for the vehicle-fields build: a small made-up crash table and a stub vPIC, no network.

    python3 pipeline/crash-augment/vehicles/tests/vehicle-fields-test.py

They show the build gives the weights it should (exact, ten-year, body-type, unmatched, not applicable),
that a rerun changes nothing, that the vPIC cache answers without the network, and that each quality
check fails on the bad input it exists to catch, leaving the previous build in place.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402,F401
import csv
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
_spec = importlib.util.spec_from_file_location("vehicle_fields", os.path.join(HERE, "vehicle-fields.py"))
VF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(VF)
import vehicle_checks  # noqa: E402
import vehicle_parse  # noqa: E402
import vehicle_vpic  # noqa: E402


class StubVpic(object):
    """The three vPIC calls the build makes, answered from a dict."""

    MAKES = {"TOYOTA": {"car"}, "HONDA": {"car", "motorcycle"}, "FORD": {"truck"}, "YAMAHA": {"motorcycle"},
             "NEW FLYER": {"bus"}, "ROVER": {"low speed vehicle (lsv)"}}
    MODELS = {"TOYOTA": {"Camry", "Prius", "Prius C", "RAV4", "Van"}, "HONDA": {"Civic", "PCX"},
              "FORD": {"F-150"}, "YAMAHA": {"Zuma 125"}, "NEW FLYER": {"Xcelsior"}}

    def makes(self):
        return {k: set(v) for k, v in self.MAKES.items()}

    def models(self, make):
        return set(self.MODELS.get(make, ()))

    def canadian_specs(self, make, year):
        if not 2010 <= year <= 2020:
            return []
        return {"TOYOTA": [("CAMRY 4DR SEDAN LE", 3300.0), ("CAMRY 4DR SEDAN XSE", 3500.0), ("PRIUS 5DR", 3050.0),
                           ("PRIUS C 5DR HATCH", 2500.0), ("RAV4 AWD 4DR SUV", 3600.0)],
                "HONDA": [("CIVIC 4DR SEDAN", 2800.0)],
                "FORD": [("F-150 P/U REG CAB 2WD", 4500.0)]}.get(make, [])


def party(uid, case, num, make, year="2015", body="Passenger Car", ptype="Driver", when="2018-06-01T08:00:00.000"):
    return {"unique_id": str(uid), "case_id_pkey": str(case), "party_number_ckey": str(num), "party_type": ptype,
            "collision_datetime": when, "vehicle_year": year, "vehicle_make": make, "stwd_vehicle_type": body}


def fixture():
    """(tables, special rows by name). 120 plain Camry drivers so the Passenger Car average exists."""
    P = [party(i, 1000 + i, 1, "Toyota/Camry/Silver") for i in range(1, 121)]
    special = {
        "camry_2015": party(201, 2001, 1, "TOYT/CAMRY/WHI"),
        "prius_c": party(202, 2002, 1, "Toyota/Prius C/Blue"),
        "prius": party(203, 2003, 1, "TOYOTA PRIUS BLACK"),
        "no_year": party(204, 2004, 1, "Toyota/Camry/Gray", year=""),
        "year_1985": party(205, 2005, 1, "Toyota/Camry/Gray", year="1985"),
        "make_only": party(206, 2006, 1, "TOYOTA"),
        "motorcycle": party(207, 2007, 1, "Yamaha/Zuma 125/BLK", body="Motorcycle"),
        "pedestrian": party(208, 2008, 1, "", year="", body="Pedestrian", ptype="Pedestrian"),
        "bicycle": party(209, 2009, 2, "ROVER", year="", body="Bicycle", ptype="Bicyclist"),
        "bus": party(210, 2010, 1, "NFLY/Bus/Gray", year="", body="Other Bus"),
        "rav4_as_mc": party(211, 2011, 1, "TOYOTA/RAV4/WHITE", body="Motorcycle"),
        "unknown": party(212, 2012, 1, "UNKNOWN/BLACK", body="Not Stated"),
        "pickup": party(213, 2013, 1, "FORD/F150/WHITE", body="Pickup or Panel Truck"),
        "two_digit_year": party(214, 2014, 1, "Honda/Civic/Gray", year="15"),
    }
    P += list(special.values())
    V = []
    for i, p in enumerate(P[:5] + [special["pedestrian"], special["prius_c"]]):
        v = dict(p)
        v["unique_id"] = str(9000 + i)
        v["victim_id"] = "%s-%s-%d" % (p["case_id_pkey"], p["party_number_ckey"], i)
        V.append(v)
    C = [{"case_id_pkey": p["case_id_pkey"], "collision_datetime": p["collision_datetime"]}
         for p in sorted({p["case_id_pkey"]: p for p in P}.values(), key=lambda p: int(p["case_id_pkey"]))]
    C.append({"case_id_pkey": "3999", "collision_datetime": "2019-01-01T00:00:00.000"})  # a crash with no parties
    tables = {VF.PARTIES: (P, "1", "2026-11-25"), VF.VICTIMS: (V, "1", "2026-11-25"), VF.CRASHES: (C, "1", "2026-11-25")}
    return tables, special


GOLDEN_TEST = "raw,expected_make,expected_model,note\nTOYT/CAMRY/WHI,TOYOTA,Camry,\nUNKNOWN/BLACK,,,\n"
SMALL = {"row_floors": {"parties-vehicles.csv": 10, "victims-vehicles.csv": 5, "crashes-vehicles.csv": 10},
         "rate_floors": {k: 0.0 for k in vehicle_checks.RATE_FLOORS}}


def rows_of(text):
    return list(csv.DictReader(io.StringIO(text)))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vehicle-fields-test-")
        self.golden = os.path.join(self.tmp, "golden.csv")
        with open(self.golden, "w") as fh:
            fh.write(GOLDEN_TEST)
        self.out = os.path.join(self.tmp, "out")
        self.committed = {n: os.path.join(self.tmp, "committed", n) for n in VF.COMMITTED}
        self.args = dict(SMALL, golden_path=self.golden)
        self.tables, self.special = fixture()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, tables=None):
        return VF.build(tables or self.tables, VF.Vpic(StubVpic()), log=lambda *a: None)

    def write(self, outputs):
        return VF.write(outputs, out_dir=self.out, committed=self.committed, check_args=self.args)

    def by_uid(self, outputs):
        return {r["unique_id"]: r for r in rows_of(outputs["parties-vehicles.csv"])}

    def test_weights_and_methods(self):
        out = self.build()
        got = self.by_uid(out)
        body = json.loads(out["body-type-averages.json"])
        s = {k: got[v["unique_id"]] for k, v in self.special.items()}
        self.assertEqual((s["camry_2015"]["vehicle_make_clean"], s["camry_2015"]["vehicle_model_clean"]), ("TOYOTA", "Camry"))
        self.assertEqual(s["camry_2015"]["estimated_vehicle_weight_lb"], "3400")   # mean of the two Camry trims
        self.assertEqual(s["camry_2015"]["vehicle_match_method"], "exact_make_model_year")
        self.assertEqual(s["prius_c"]["estimated_vehicle_weight_lb"], "2500")      # its own trim, not the Prius
        self.assertEqual(s["prius"]["estimated_vehicle_weight_lb"], "3050")
        self.assertEqual(s["no_year"]["vehicle_match_method"], "model_10yr_avg")
        self.assertEqual(s["no_year"]["estimated_vehicle_weight_lb"], "3400")
        self.assertEqual(s["year_1985"]["vehicle_match_method"], "body_type_avg")  # no trims within five years
        self.assertIn("no Transport Canada trims", s["year_1985"]["vehicle_match_reason"])
        self.assertEqual(s["make_only"]["vehicle_match_method"], "body_type_avg")
        # The Passenger Car average is over every exact weight of that body type: 120 Camrys and the rest.
        self.assertEqual(s["make_only"]["estimated_vehicle_weight_lb"], str(body["Passenger Car"]["weight_lb"]))
        self.assertTrue(3300 < body["Passenger Car"]["weight_lb"] < 3400, body)
        self.assertEqual(s["motorcycle"]["vehicle_match_method"], "unmatched")
        self.assertIn("no body-type average for Motorcycle", s["motorcycle"]["vehicle_match_reason"])
        self.assertEqual(s["pedestrian"]["vehicle_match_method"], "not_applicable")
        self.assertEqual((s["bicycle"]["vehicle_match_method"], s["bicycle"]["vehicle_make_clean"]), ("not_applicable", ""))
        self.assertEqual((s["bus"]["vehicle_make_clean"], s["bus"]["vehicle_match_method"]), ("NEW FLYER", "unmatched"))
        self.assertIn("conflicts", s["rav4_as_mc"]["vehicle_match_reason"])
        self.assertEqual(s["unknown"]["vehicle_make_clean"], "")
        self.assertEqual(s["pickup"]["estimated_vehicle_weight_lb"], "4500")
        self.assertEqual(s["two_digit_year"]["vehicle_match_method"], "model_10yr_avg")  # "15" is not a model year

    def test_rows_kept_and_crash_rollup(self):
        out = self.build()
        self.assertEqual(len(rows_of(out["parties-vehicles.csv"])), len(self.tables[VF.PARTIES][0]))
        self.assertEqual(len(rows_of(out["victims-vehicles.csv"])), len(self.tables[VF.VICTIMS][0]))
        crashes = {r["case_id_pkey"]: r for r in rows_of(out["crashes-vehicles.csv"])}
        self.assertEqual(len(crashes), len(self.tables[VF.CRASHES][0]))
        self.assertEqual(crashes["3999"]["motor_vehicle_parties"], "0")
        self.assertEqual(crashes["2013"]["heaviest_vehicle_weight_lb"], "4500")

    def test_good_build_passes_and_rerun_changes_nothing(self):
        out = self.build()
        self.assertTrue(self.write(out))
        snap = self.snapshot()
        again = self.build()
        self.assertEqual(out, again, "a second build from the same inputs differs")
        self.assertTrue(self.write(again))
        self.assertEqual(snap, self.snapshot())

    def snapshot(self):
        out = {}
        for n in sorted(os.listdir(self.out)):
            with open(os.path.join(self.out, n)) as fh:
                out[n] = fh.read()
        return out

    def results(self, outputs, prev=None):
        stage = os.path.join(self.tmp, "stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        for n, t in outputs.items():
            with open(os.path.join(stage, n), "w") as fh:
                fh.write(t)
        return {r.check: r for r in vehicle_checks.run(stage, prev_root=prev, **self.args)}

    def assertFails(self, results, check):
        self.assertIn(check, results, sorted(results))
        self.assertFalse(results[check].ok, "%s should fail: %s" % (check, results[check]))

    def test_duplicate_input_row_fails_and_keeps_previous_build(self):
        self.assertTrue(self.write(self.build()))
        before = self.snapshot()["parties-vehicles.csv"]
        P, m, d = self.tables[VF.PARTIES]
        bad = dict(self.tables)
        bad[VF.PARTIES] = (P + [dict(P[0])], m, d)
        out = self.build(bad)
        self.assertFails(self.results(out), "parties-vehicles.csv.unique[unique_id]")
        self.assertFalse(self.write(out))
        self.assertEqual(before, self.snapshot()["parties-vehicles.csv"])

    def test_dropped_output_row_fails(self):
        out = self.build()
        lines = out["parties-vehicles.csv"].splitlines(True)
        out["parties-vehicles.csv"] = "".join(lines[:-1])
        self.assertFails(self.results(out), "parties-vehicles.csv.rows_exact")

    def test_short_read_against_previous_build_fails(self):
        self.assertTrue(self.write(self.build()))
        P, m, d = self.tables[VF.PARTIES]
        bad = dict(self.tables)
        bad[VF.PARTIES] = (P[: len(P) // 2], m, d)
        self.assertFails(self.results(self.build(bad), prev=self.out), "parties-vehicles.csv.rows")

    def test_weight_out_of_bounds_fails(self):
        out = self.build()
        rows = rows_of(out["parties-vehicles.csv"])
        rows[0]["estimated_vehicle_weight_lb"] = "50000"
        out["parties-vehicles.csv"] = VF.to_csv(rows, VF.PARTY_OUT)
        self.assertFails(self.results(out), "parties-vehicles.csv.each")

    def test_weight_without_method_fails(self):
        out = self.build()
        rows = rows_of(out["parties-vehicles.csv"])
        r = next(r for r in rows if r["vehicle_match_method"] == "unmatched")
        r["estimated_vehicle_weight_lb"] = "3000"
        out["parties-vehicles.csv"] = VF.to_csv(rows, VF.PARTY_OUT)
        self.assertFails(self.results(out), "parties-vehicles.csv.each")

    def test_victim_with_no_party_fails(self):
        out = self.build()
        rows = rows_of(out["victims-vehicles.csv"])
        rows[0]["party_number_ckey"] = "9"
        out["victims-vehicles.csv"] = VF.to_csv(rows, VF.VICTIM_OUT)
        self.assertFails(self.results(out), "victims-vehicles.csv>parties.join")

    def test_golden_mismatch_fails(self):
        with open(self.golden, "w") as fh:
            fh.write("raw,expected_make,expected_model,note\nTOYT/CAMRY/WHI,TOYOTA,Corolla,deliberately wrong\n")
        self.assertFails(self.results(self.build()), "golden")

    def test_rate_floor_fails(self):
        self.args["rate_floors"] = dict(self.args["rate_floors"], exact_of_motor=0.99)
        self.assertFails(self.results(self.build()), "rate[exact_of_motor]")


class Parser(unittest.TestCase):
    def setUp(self):
        s = StubVpic()
        self.m = vehicle_parse.Matcher(s.makes(), s.models, common_makes=["TOYOTA"])

    def test_cases(self):
        def mm(raw):
            p = self.m.parse(raw)
            return (p.make, p.model)
        self.assertEqual(mm("TOYOTA/CAMERY/SILVER"), ("TOYOTA", "Camry"))      # misspelling
        self.assertEqual(mm("TOYOYTA/PRIUS"), ("TOYOTA", "Prius"))             # misspelt common make
        self.assertEqual(mm("Toyota/Van/White"), ("TOYOTA", None))             # a body word is not a model
        self.assertEqual(mm("ROVER"), (None, None))                            # low speed vehicle maker needs an alias
        self.assertEqual(mm("WHITE/TOYOTA/RAV 4"), ("TOYOTA", "RAV4"))
        self.assertEqual(self.m.parse("TOYOTA/PRI").model, "Prius")            # Prius C only extends Prius


class VpicCache(unittest.TestCase):
    def test_cached_answer_needs_no_network(self):
        tmp = tempfile.mkdtemp(prefix="vpic-cache-test-")
        old = vehicle_vpic.CACHE
        try:
            vehicle_vpic.CACHE = tmp
            url = vehicle_vpic.BASE + "GetModelsForMake/TOYOTA?format=json"
            with open(vehicle_vpic._path(url), "w") as fh:
                json.dump({"url": url, "results": [{"Model_Name": "Camry"}]}, fh)
            vehicle_vpic.set_offline(True)
            self.assertEqual(vehicle_vpic.models("TOYOTA"), {"Camry"})
            with self.assertRaises(vehicle_vpic.Offline):
                vehicle_vpic.models("HONDA")
        finally:
            vehicle_vpic.set_offline(False)
            vehicle_vpic.CACHE = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
