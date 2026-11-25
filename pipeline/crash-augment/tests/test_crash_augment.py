#!/usr/bin/env python3
"""Tests for the held crash tables (crash_tables.py) and the augmented tables' checks (augment_checks.py), with a fake DataSF and no network.

    python3 pipeline/crash-augment/tests/test_crash_augment.py

Shows the refresh reading nothing when nothing moved, reading only the missing row when one is cut from the held
copy, reading only rows whose data_updated_at moved, moving a row whose collision year changed, and refusing a read
that repeats a key (the held copy stays). Then shows each augmented-table check failing on the bad input it is for.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402,F401
import csv
import json
import os
import re
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import augment_checks  # noqa: E402
import crash_tables  # noqa: E402
from lib import pipeline_state  # noqa: E402
from lib import quality  # noqa: E402


class FakeSocrata(object):
    """Just enough of lib/sfdata.py for crash_tables: the views API, a grouped count, and a paged read."""

    HOST = "fake"

    def __init__(self, tables):
        self.tables = tables          # fxf -> list of rows
        self.stamp = {f: 1 for f in tables}
        self.rows_served = 0

    def _url(self, fxf, params):
        return ("q", fxf, tuple(sorted(params.items())))

    def _get(self, url, timeout):
        if isinstance(url, str):
            fxf = url.rsplit("/", 1)[1][:-5]
            cols = sorted({k for r in self.tables[fxf] for k in r})
            return {"rowsUpdatedAt": self.stamp[fxf], "columns": [{"fieldName": c} for c in cols]}
        _, fxf, _ = url
        n = {}
        for r in self.tables[fxf]:
            y = r["collision_datetime"][:4]
            n[y] = n.get(y, 0) + 1
        return [{"y": y, "n": str(c)} for y, c in sorted(n.items())]

    def stream(self, fxf, select=None, where=None, order=None):
        rows = list(self.tables[fxf])
        m = re.match(r"date_extract_y\(collision_datetime\) = (\d+)$", where or "")
        if m:
            rows = [r for r in rows if r["collision_datetime"][:4] == m.group(1)]
        m = re.match(r"data_updated_at >= '(.*)'$", where or "")
        if m:
            rows = [r for r in rows if r["data_updated_at"] >= m.group(1)]
        m = re.match(r"(\w+) in \((.*)\)$", where or "")
        if m:
            want = set(re.findall(r"'([^']*)'", m.group(2)))
            rows = [r for r in rows if r[m.group(1)] in want]
        if select:
            rows = [{c: r[c] for c in select.split(",")} for r in rows]
        else:
            self.rows_served += len(rows)
            rows = [dict(r, data_loaded_at="2026-11-25T10:00:00", point={"type": "Point"}) for r in rows]
        yield rows


def crash(i, year, updated="2026-01-01"):
    return {"case_id_pkey": str(i), "unique_id": str(i), "collision_datetime": "%s-03-01T08:00:00.000" % year,
            "data_updated_at": updated + "T00:00:00.000", "primary_rd": "MARKET ST"}


class HeldTables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (crash_tables.STORE, crash_tables.STATE, crash_tables.sfdata, dict(crash_tables.FLOORS),
                      pipeline_state.PATH)
        crash_tables.STORE = os.path.join(self.tmp, "store")
        crash_tables.STATE = os.path.join(crash_tables.STORE, "_state.json")
        pipeline_state.PATH = os.path.join(self.tmp, "sources.json")
        crash_tables.FLOORS["crashes"] = 5
        # Rows last updated across 2025; the newest held day, 2025-12-01, carries rows 11 and 23.
        self.fake = FakeSocrata({"ubvf-ztfx": [crash(i, 2024 + i % 3, "2025-%02d-01" % (1 + i % 12)) for i in range(1, 31)]})
        crash_tables.sfdata = self.fake
        os.environ["CRASH_TABLES_TODAY"] = "2026-11-25"
        crash_tables.refresh(["crashes"], update=True, log=lambda *a: None)
        self.fake.rows_served = 0

    def tearDown(self):
        (crash_tables.STORE, crash_tables.STATE, crash_tables.sfdata, floors, pipeline_state.PATH) = self.saved
        crash_tables.FLOORS.clear()
        crash_tables.FLOORS.update(floors)
        os.environ.pop("CRASH_TABLES_TODAY", None)
        shutil.rmtree(self.tmp)

    def files(self, state=True):
        """Every held file's text; without `state`, the year files only (a failed refresh marks the state failed)."""
        out = {}
        for d, _, fs in os.walk(crash_tables.STORE):
            for f in fs:
                if not state and f == "_state.json":
                    continue
                p = os.path.join(d, f)
                out[os.path.relpath(p, crash_tables.STORE)] = open(p, encoding="utf-8").read()
        return out

    def refresh(self):
        return crash_tables.refresh(["crashes"], update=True, log=lambda *a: None)

    def test_cold_read_holds_every_row_without_load_stamps(self):
        rows = crash_tables.rows("crashes")
        self.assertEqual(len(rows), 30)
        self.assertNotIn("data_loaded_at", rows[0])
        self.assertNotIn("point", rows[0])
        self.assertEqual(crash_tables.years("crashes"), ["2024", "2025", "2026"])

    def test_rerun_with_nothing_new_reads_and_writes_nothing(self):
        before = self.files()
        self.refresh()
        self.assertEqual(self.fake.rows_served, 0)
        self.assertEqual(self.files(), before)

    def test_removed_row_is_the_only_row_read_again(self):
        before = self.files()
        p = os.path.join(crash_tables.STORE, "ubvf-ztfx", "2026.json")
        blob = json.load(open(p))
        blob["rows"] = blob["rows"][:-1]
        open(p, "w").write(json.dumps(blob))
        self.refresh()
        self.assertEqual(self.fake.rows_served, 1)
        self.assertEqual(self.files(), before)

    def test_a_held_file_edited_on_disk_is_read_again(self):
        before = self.files()
        p = os.path.join(crash_tables.STORE, "ubvf-ztfx", "2025.json")
        blob = json.load(open(p))
        blob["rows"][0]["primary_rd"] = "EDITED ST"
        open(p, "w").write(json.dumps(blob))
        self.refresh()
        self.assertEqual(self.fake.rows_served, 10)
        self.assertEqual(self.files(), before)

    def test_only_moved_rows_are_read_on_a_new_update(self):
        self.fake.tables["ubvf-ztfx"][4] = dict(self.fake.tables["ubvf-ztfx"][4], primary_rd="MISSION ST",
                                                data_updated_at="2026-11-24T00:00:00.000")
        self.fake.stamp["ubvf-ztfx"] = 2
        self.refresh()
        # Row 5, plus rows 11 and 23: the newest held day is read again, since data_updated_at is a date.
        self.assertEqual(self.fake.rows_served, 3)
        got = {r["case_id_pkey"]: r for r in crash_tables.rows("crashes")}
        self.assertEqual(got["5"]["primary_rd"], "MISSION ST")
        self.assertEqual(len(got), 30)

    def test_a_row_whose_year_changed_moves(self):
        self.fake.tables["ubvf-ztfx"][0] = dict(crash(1, 2026, "2026-11-24"))
        self.fake.stamp["ubvf-ztfx"] = 2
        self.refresh()
        rows = crash_tables.rows("crashes")
        self.assertEqual(sum(1 for r in rows if r["case_id_pkey"] == "1"), 1)
        self.assertEqual(len(rows), 30)

    def test_a_read_that_repeats_a_key_fails_and_keeps_the_held_copy(self):
        before = self.files(state=False)
        self.fake.tables["ubvf-ztfx"].append(dict(crash(7, 2025, "2026-11-24")))  # key 7 is held in 2025 already
        self.fake.tables["ubvf-ztfx"][6] = dict(crash(7, 2024, "2026-11-24"))
        self.fake.stamp["ubvf-ztfx"] = 2
        with self.assertRaises(crash_tables.CheckFailed):
            self.refresh()
        self.assertEqual(self.files(state=False), before)
        self.assertEqual(json.load(open(pipeline_state.PATH))["crash-augment:ubvf-ztfx"]["status"], "failed")

    def test_a_short_upstream_table_fails_the_floor(self):
        before = self.files(state=False)
        crash_tables.FLOORS["crashes"] = 29
        del self.fake.tables["ubvf-ztfx"][:5]
        self.fake.stamp["ubvf-ztfx"] = 2
        with self.assertRaises(crash_tables.CheckFailed) as cm:
            self.refresh()
        self.assertIn("crash-tables/crashes.rows", str(cm.exception))
        self.assertEqual(self.files(state=False), before)


# ---- the augmented tables' checks -----------------------------------------------------------------------------------

def write_out(root, crashes, parties, victims, summary_edit=None):
    d = os.path.join(root, augment_checks.OUT_REL)
    os.makedirs(d, exist_ok=True)
    tables = {}
    for name, rows, added in (("crashes", crashes, ["in_epc"]), ("parties", parties, ["vehicle_match_method"]),
                              ("victims", victims, ["vehicle_match_method"])):
        cols = list(rows[0])
        with open(os.path.join(d, name + ".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        tables[name] = {"rows": len(rows), "datasf_columns": len(cols) - len(added),
                        "added": [{"lane": "x", "columns": added}], "missing_lane_rows": {"x": 0},
                        "lane_rows_not_held": {"x": 0}, "lane_keys_repeated": {"x": 0},
                        "input": {"id": name, "rows": len(rows), "rowsUpdatedAt": "1"}}
    s = {"tables": tables, "vehicle_inputs": {}}
    if summary_edit:
        summary_edit(s)
    json.dump(s, open(os.path.join(d, "summary.json"), "w"))


class AugmentedChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = dict(augment_checks.FLOORS)
        augment_checks.FLOORS.update(crashes=2, parties=2, victims=2)
        when = "2024-03-01T08:00:00.000"
        self.c = [{"case_id_pkey": str(i), "collision_datetime": when, "in_epc": "true"} for i in range(1, 4)]
        self.p = [{"unique_id": "p%d" % i, "case_id_pkey": str(i), "party_number_ckey": "1", "collision_datetime": when,
                   "vehicle_match_method": "body_type_avg"} for i in range(1, 4)]
        self.v = [{"unique_id": "v%d" % i, "case_id_pkey": str(i), "party_number_ckey": "1", "collision_datetime": when,
                   "vehicle_match_method": "body_type_avg"} for i in range(1, 4)]

    def tearDown(self):
        augment_checks.FLOORS.clear()
        augment_checks.FLOORS.update(self.saved)
        augment_checks._cache.clear()
        shutil.rmtree(self.tmp)

    def failed(self, **kw):
        write_out(self.tmp, kw.get("c", self.c), kw.get("p", self.p), kw.get("v", self.v), kw.get("edit"))
        augment_checks._cache.clear()
        return sorted(r.check for r in augment_checks.run(self.tmp) if not r.ok)

    def test_good_tables_pass(self):
        self.assertEqual(self.failed(), [])

    def test_repeated_crash_key_fails(self):
        self.assertIn("crash-augment/crashes.csv.unique[case_id_pkey]", self.failed(c=self.c + [self.c[0]]))

    def test_party_with_no_crash_fails(self):
        p = self.p + [dict(self.p[0], unique_id="p9", case_id_pkey="99")]
        self.assertIn("crash-augment/parties.csv>crashes.join", self.failed(p=p))

    def test_victim_with_no_party_fails(self):
        v = self.v + [dict(self.v[0], unique_id="v9", party_number_ckey="2")]
        self.assertIn("crash-augment/victims.csv>parties.join", self.failed(v=v))

    def test_missing_lane_row_fails(self):
        def edit(s):
            s["tables"]["parties"]["missing_lane_rows"] = {"x": 1}
        self.assertIn("crash-augment/summary.json.each", self.failed(edit=edit))

    def test_rows_not_equal_to_the_held_table_fail(self):
        def edit(s):
            s["tables"]["crashes"]["input"]["rows"] = 4
        self.assertIn("crash-augment/summary.json.each", self.failed(edit=edit))

    def test_lanes_on_different_datasf_updates_fail(self):
        def edit(s):
            s["vehicle_inputs"] = {"parties": {"rows": 3, "rowsUpdatedAt": "2"}}
        self.assertIn("crash-augment/summary.json.each", self.failed(edit=edit))

    def test_an_added_column_with_no_value_fails(self):
        c = [dict(r, in_epc="") for r in self.c]
        self.assertIn("crash-augment/columns.each", self.failed(c=c))

    def test_a_drop_against_the_previous_build_fails(self):
        prev = os.path.join(self.tmp, "prev")
        write_out(prev, self.c * 1, self.p, self.v)
        big = [dict(self.c[0], case_id_pkey=str(i)) for i in range(1, 101)]
        write_out(prev, big, self.p, self.v)
        write_out(self.tmp, self.c, self.p, self.v)
        augment_checks._cache.clear()
        bad = [r.check for r in quality.run(augment_checks.checks(), self.tmp, prev) if not r.ok]
        self.assertIn("crash-augment/crashes.csv.rows", bad)


if __name__ == "__main__":
    unittest.main(verbosity=1)
