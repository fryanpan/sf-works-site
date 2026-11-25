#!/usr/bin/env python3
"""Tests for the crash street-context build: the dated field rules on tiny made-up sources, and the quality checks failing on bad input.

    python3 pipeline/crash-augment/street/tests/test_crash_street.py

No network: every source is built in the test.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import street_checks  # noqa: E402
import street_fields  # noqa: E402


def square(x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def sources():
    """Two blocks of A ST meeting B ST (a residential street) at node 100; one tract that is an EPC."""
    line = lambda a, b: {"type": "LineString", "coordinates": [a, b]}  # noqa: E731
    return {
        "streets": [
            {"cnn": "1", "streetname": "A ST", "classcode": "3", "f_node_cnn": "99.0", "t_node_cnn": "100.0",
             "active": True, "line": line([-122.42, 37.77], [-122.419, 37.77])},
            {"cnn": "2", "streetname": "A ST", "classcode": "3", "f_node_cnn": "100.0", "t_node_cnn": "101.0",
             "active": True, "line": line([-122.419, 37.77], [-122.418, 37.77])},
            {"cnn": "3", "streetname": "B ST", "classcode": "5", "f_node_cnn": "100.0", "t_node_cnn": "102.0",
             "active": True, "line": line([-122.419, 37.77], [-122.419, 37.771])},
        ],
        "speed_limits": [{"cnn": "1", "speedlimit": "20", "install_date": "2021-06-01T16:00:00.000"},
                         {"cnn": "2", "speedlimit": "0"}, {"cnn": "3", "speedlimit": "99"}],
        "lanes": [{"attributes": {"CNN": 1.0, "LANES_OP": 2, "LANES_AM": 2, "LANES_PM": 3}}],
        "bci": [{"attributes": {"cnn_sgmt_pkey": 1, "traffic_category_ft": "Light Traffic",
                                "traffic_category_tf": "Heavy Traffic"}}],
        "safety_zones": [{"cnn": "100", "install_da": "1659052800000"}],        # 2022-07-29
        "traffic_calming": [{"cnn": "1", "tc_measure": "Speed Hump", "install_datetime": "2019-03-01T00:00:00.000",
                             "current_status": "Complete"},
                            {"cnn": "2", "tc_measure": "Speed Hump", "install_datetime": "1900-01-01T00:00:00.000",
                             "current_status": "Complete"}],
        "slow_streets": [{"cnn": "3", "status": "Implemented", "install_date": "2020-05-01T00:00:00.000"}],
        "signals": [{"cnn": "100", "type": "SIGNAL", "startyear": "2015"}],
        "cameras": [{"site_id": "S1", "location": "EB 100 A ST", "date": "2025-04-01T00:00:00.000",
                     "point": {"coordinates": [-122.4195, 37.77]}}],
        "epc": [{"attributes": {"tract_geoid": "06075000100", "epc_2050p": 1},
                 "geometry": {"rings": square(-122.43, 37.76, -122.41, 37.78)}}],
    }


def crash(case, date, seg=None, node=None, where="Midblock > 20ft", lat="37.77", lon="-122.4195"):
    return {"case_id_pkey": case, "collision_date": date + "T00:00:00.000", "cnn_sgmt_fkey": seg,
            "cnn_intrsctn_fkey": node, "intersection": where, "primary_rd": "A ST", "tb_latitude": lat,
            "tb_longitude": lon, "collision_severity": "Injury (Severe)"}


class FieldRules(unittest.TestCase):
    def setUp(self):
        self.ctx = street_fields.Context(sources())

    def one(self, c):
        return street_fields.augment([c], self.ctx)[0]

    def test_speed_20_is_25_before_install(self):
        self.assertEqual(self.one(crash("a", "2021-05-31", seg="1"))["posted_speed_limit_mph"], 25)
        r = self.one(crash("b", "2021-06-01", seg="1"))
        self.assertEqual((r["posted_speed_limit_mph"], r["posted_speed_limit_mph_basis"]), (20, "dated"))

    def test_speed_code_0_is_25_current_and_99_unknown(self):
        r = self.one(crash("a", "2010-01-01", seg="2"))
        self.assertEqual((r["posted_speed_limit_mph"], r["posted_speed_limit_mph_basis"]), (25, "current_state_only"))
        r = self.one(crash("b", "2010-01-01", seg="3"))
        self.assertEqual((r["posted_speed_limit_mph"], r["posted_speed_limit_mph_basis"]), (None, "unknown"))

    def test_intersection_crash_uses_primary_road_blocks_and_corner(self):
        r = self.one(crash("a", "2023-01-01", node="100", where="Intersection <= 20ft"))
        self.assertEqual(r["street_block_join"], "node_primary_rd")
        self.assertEqual(r["street_block_cnns"], "1;2")
        self.assertEqual(r["corner_type"], "arterial_x_residential")
        self.assertEqual(r["posted_speed_limit_mph"], 25)      # max(20 after install on 1, 25 default on 2)
        self.assertIs(r["painted_safety_zone"], True)
        self.assertIs(r["signal_present"], True)

    def test_dated_flags_flip_at_install(self):
        before = self.one(crash("a", "2022-07-28", node="100", where="Intersection <= 20ft"))
        self.assertIs(before["painted_safety_zone"], False)
        same_year = self.one(crash("b", "2015-06-01", node="100", where="Intersection <= 20ft"))
        self.assertEqual((same_year["signal_present"], same_year["signal_present_basis"]), (None, "unknown"))

    def test_calming_undated_is_unknown(self):
        r = self.one(crash("a", "2020-01-01", seg="1"))
        self.assertEqual((r["traffic_calming"], r["traffic_calming_types"]), (True, "Speed Hump"))
        r = self.one(crash("b", "2020-01-01", seg="2"))
        self.assertEqual((r["traffic_calming"], r["traffic_calming_basis"]), (None, "unknown"))

    def test_camera_corridor_from_first_day(self):
        self.assertIs(self.one(crash("a", "2025-03-31", seg="2"))["speed_camera_corridor"], False)
        self.assertIs(self.one(crash("b", "2025-04-01", seg="2"))["speed_camera_corridor"], True)
        self.assertIs(self.one(crash("c", "2025-04-01", seg="3"))["speed_camera_corridor"], False)

    def test_epc_and_lanes_and_bci(self):
        r = self.one(crash("a", "2020-01-01", seg="1"))
        self.assertEqual((r["in_epc"], r["epc_tract"]), (True, "06075000100"))
        self.assertEqual((r["lanes"], r["lanes_pm"], r["bci_traffic_category"]), (2, 3, "heavy"))
        r = self.one(crash("b", "2020-01-01", seg="1", lat="", lon=""))
        self.assertEqual((r["in_epc"], r["in_epc_basis"]), (None, "unknown"))


def as_strings(rows):
    cell = lambda v: "true" if v is True else "false" if v is False else "" if v is None else str(v)  # noqa: E731
    return [{k: cell(r.get(k)) for k in street_fields.COLUMNS} for r in rows]


class ChecksFail(unittest.TestCase):
    """A clean table passes the row, key, basis, range and dated checks; each kind of bad input fails its check."""

    def setUp(self):
        ctx = street_fields.Context(sources())
        self.crashes = [crash(str(i), "2024-0%d-01" % (1 + i % 9), seg="1") for i in range(50)]
        self.rows = as_strings(street_fields.augment(self.crashes, ctx))
        self.keys = [c["case_id_pkey"] for c in self.crashes]

    def failed(self, rows, keys=None, **kw):
        return {r.check for r in street_checks.run(rows, keys or self.keys, **kw) if not r.ok}

    def test_clean_passes_structure(self):
        bad = self.failed(self.rows)
        self.assertFalse({b for b in bad if not b.startswith("crash-street.coverage")}, bad)

    def test_dropped_row_fails(self):
        self.assertIn("crash-street.rows.join", self.failed(self.rows[:-1]))

    def test_duplicated_row_fails(self):
        bad = self.failed(self.rows + [self.rows[0]])
        self.assertIn("crash-street.rows.join", bad)
        self.assertIn("crash-street.unique[case_id_pkey]", bad)

    def test_row_count_vs_previous_fails(self):
        self.assertIn("crash-street.rows-vs-prev", self.failed(self.rows, prev_summary={"rows": 100}))

    def test_out_of_range_speed_fails(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["posted_speed_limit_mph"] = "22"
        self.assertIn("crash-street.range[posted_speed_limit_mph]", self.failed(rows))

    def test_value_without_basis_fails(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["lanes_basis"] = "unknown"
        self.assertIn("crash-street.basis[lanes]", self.failed(rows))

    def test_camera_before_2025_fails(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["speed_camera_corridor"], rows[0]["collision_date"] = "true", "2019-01-01"
        self.assertIn("crash-street.dated[speed_camera_corridor]", self.failed(rows))

    def test_coverage_floor_fails(self):
        rows = [dict(r, in_epc="", in_epc_basis="unknown") for r in self.rows]
        self.assertIn("crash-street.coverage[in_epc]", self.failed(rows))

    def test_unplaced_camera_fails(self):
        self.assertIn("crash-street.sources[camera-sites-placed]", self.failed(self.rows, cameras_unplaced=["X"]))

    def test_short_source_fails(self):
        self.assertIn("crash-street.sources[epc]",
                      self.failed(self.rows, source_counts={"epc": 3}, source_floors={"epc": 240}))


if __name__ == "__main__":
    unittest.main()
