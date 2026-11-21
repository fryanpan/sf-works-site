#!/usr/bin/env python3
"""Tests the two gates on a Telraam counter with made-up input: the override gate in tools/street-safety/hin-cut-through.py (a counter replaces SFMTA's count only with 20 valid April to September days) and the one-side check (tools/street-safety/telraam-sf.py flags it, hin-cut-through.py fails it off a one-way street).

    python3 tools/street-safety/telraam-gates-test.py

site/tests/safety-map-test.mjs runs it, so `npm run check` and the pull request checks do too. Reads no file and no API.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name):
    return paths.load(name + ".py")


H, T = load("hin-cut-through"), load("telraam-sf")
READ = "2026-11-19"
SFMTA = {"peak": 88, "daily": 900, "year": 2017, "pandemic": False}


def fig(season_days, last_valid):
    """A counter's figure as telraam_fig() builds it, from a segment with these days."""
    s = {"id": "1", "peak": 50.0, "valid_days": 60, "first": "2025-12-02", "last": last_valid, "full_days": 0,
         "daylight_days": season_days}
    if season_days >= 5:
        s.update(peak_daylight=48.0, daylight_first="2026-04-07", daylight_last=min(last_valid, "2026-09-30"))
    return H.telraam_fig(s, 0.1)


def test_six_season_days_do_not_override():
    f = fig(6, "2026-11-17")
    assert not f["overrides"] and H.choose_count(SFMTA, f) == "sfmta"
    assert H.choose_count(None, f) == "telraam", "a block with only the counter keeps it"


def test_a_counter_last_valid_80_days_ago_with_65_season_days_overrides():
    last = (dt.date.fromisoformat(READ) - dt.timedelta(days=80)).isoformat()      # 2026-08-31
    f = fig(65, last)
    assert f["overrides"] and H.choose_count(SFMTA, f) == "telraam"
    assert H.choose_count(dict(SFMTA, pandemic=True, year=2021), f) == "telraam"
    old = fig(65, "2026-05-01")          # stopped in spring: still newer than any SFMTA count
    assert H.choose_count(SFMTA, old) == "telraam"


def test_twenty_recent_season_days_override():
    assert H.choose_count(SFMTA, fig(20, "2026-11-17")) == "telraam"
    assert H.choose_count(SFMTA, fig(19, "2026-11-17")) == "sfmta"
    assert H.choose_count(SFMTA, fig(0, "2026-11-17")) == "sfmta", "a winter-only counter has no season days"


def test_the_gate_counts_season_days_only():
    assert H.overrides(20) and not H.overrides(19) and not H.overrides(0) and not H.overrides(None)


def hours(left, right):
    """Hourly rows for every Tuesday to Thursday from March to August 2026, all 24 hours up, `left` and `right` cars
    each way an hour."""
    rows, day = [], dt.date(2026, 3, 3)
    while day < dt.date(2026, 9, 1):
        if day.weekday() in (1, 2, 3):
            for h in range(24):
                t = dt.datetime(day.year, day.month, day.day, h, tzinfo=T.LA).astimezone(dt.timezone.utc)
                rows.append({"date": t.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "uptime": 1, "car": left + right, "heavy": 0,
                             "night": 0, "bike": 1, "pedestrian": 1, "car_lft": left, "car_rgt": right})
        day += dt.timedelta(days=1)
    return rows


def summary(left, right):
    geom = {"type": "LineString", "coordinates": [[-122.45, 37.77], [-122.451, 37.77]]}
    return T.summarise("1", geom, hours(left, right), dt.date(2025, 11, 19), dt.date(2026, 11, 19))


TWO_WAY, ONE_WAY = {"oneway": "B"}, {"oneway": "F"}


def test_a_two_tenths_percent_side_fails_on_a_two_way_street_and_passes_on_a_one_way_street():
    s = summary(998, 2)
    assert s["kept"] and "one side" in s["flags"] and s["side_share"] == 0.002, s
    assert H.sees_one_side(s, TWO_WAY, False), "two-way street: the counter sees one side and fails"
    assert not H.sees_one_side(s, ONE_WAY, False), "one-way street: one side is the whole street"
    assert H.sees_one_side(s, ONE_WAY, True), "one carriageway of a divided road carries the road's two-way figure"


def test_an_exact_zero_side_is_flagged_not_failed_by_the_segment_script():
    s = summary(1000, 0)
    assert s["kept"] and "one side" in s["flags"] and s["side_share"] == 0.0, s
    assert H.sees_one_side(s, TWO_WAY, False) and not H.sees_one_side(s, ONE_WAY, False)


def test_a_counter_seeing_both_sides_passes_anywhere():
    for left, right in ((500, 500), (970, 30)):          # 3% is over the 2% line
        s = summary(left, right)
        assert s["kept"] and "one side" not in s["flags"], s
        assert not H.sees_one_side(s, TWO_WAY, False)


def test_hampshire_is_matched_as_the_counts_file_spells_it():
    assert H.base("HAMPHIRE ST") == H.base("HAMPSHIRE ST") == "HAMPSHIRE"


if __name__ == "__main__":
    tests = sorted((n, f) for n, f in globals().items() if n.startswith("test_"))
    for n, f in tests:
        f()
        print("ok  " + n)
    print("%d tests passed" % len(tests))
