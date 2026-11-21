#!/usr/bin/env python3
"""Every injured person the Street Safety map counts without a crash card: each level in every year from 2005 to the newest report, except the severe injuries and deaths of 2022 to 2024 that have a point (those come with cards from tools/street-safety/hin-people-map.py), with only the fields the map's filters read.

    uv run --no-project --with numpy python tools/street-safety/street-safety-light.py

Writes data/extract/street-safety/light-injuries.json, which tools/street-safety/street-safety-map.py folds into the map's people:
2021 to now inline in map.json, 2005 to 2020 in a file the page loads when the Years slider reaches back.

Bryan (2026-11-19): "overall on the dashboard, there should be a filter of what to show, death,
serious injury, and whatever the term is for less severe injury. Make it a range slider where you can filter to that
level and anything more severe." And  (2026-11-19): "please include as many years as you can up to
current day (incomplete on 2026). By default, please show 2021-current day." The levels are DataSF nwes-mmgh's
`victim_degree_of_injury` values, in its own words: Fatal Injury, Severe Injury, Other Visible Injury, Complaint of Pain
(research/sources/datasf-traffic-crashes.md). The handful of "No Injury" rows (2014 to 2016) are left out.

THE BASE. DataSF nwes-mmgh, one row per injured person, deduplicated on (case_id_pkey, victim_id), collision_datetime
from 2005-01-01 (the table's first year) to its newest row. Read the same way as tools/street-safety/hin-injury-kinds.py reads the
severe and fatal rows, with its own functions, so a filter means the same thing at every level:
  road user  the person's own party in DataSF 8gtc-pjc6 (party_number_ckey), hin-injury-kinds.py party_mode(); the
             parties are read in one query over the same dates, not per case;
  cause      vz_pcf_code through hin-injury-kinds.py cause(), and its subcause key code_key();
  place      `intersection` starting "Intersection <=" is at an intersection, else midblock, blank unknown;
  hour       collision_time's hour (hin-injury-kinds.py hour()).
  other      the other party involved (Bryan, 2026-11-20: "add another filter on other party involved. And so options
             would be something like 'No other vehicle', 'Car', 'Bike', 'Multiple vehicles'"): other_party() over every
             other party row of the person's crash in 8gtc-pjc6, one option per person (OTHERS). A party number that
             comes twice in a case must read the same both times, or the run stops.
Each row keeps its case id, so the map can put a severe or fatal person on the HIN segment
tools/street-safety/hin-densest-stretches.py assigned to the case. `card_other` holds the same reading for the 2022 to 2024 severe
injuries and deaths, keyed by nwes-mmgh victim_id, which tools/street-safety/street-safety-map.py gives the people with cards.

NO POINT. A row with no point inside the city's box (243 of 83,141 on 2026-11-20, four of them severe or fatal since
2021) is kept with lon and lat null: the person counts in the headline and under every filter that needs no place, and
the map leaves them off the drawing and out of the place filters (site/src/safety-map/state.js shownTest). That
includes the 2022 to 2024 severe injuries and deaths with no point, which the card path can't place, so every row of the
source is counted once, here or there.

PUBLISHED TOTAL. Checked on every run against a second read of the source (dates and levels only, no other rule): the
Fatal Injury and Severe Injury rows per year this file holds, plus the 2022 to 2024 rows handed to the card path, equal
the source's. Fatal Injury rows for 2025 are 25, SFMTA's published traffic deaths for the year, and Severe Injury rows
for 2016, 2017 and 2018 are 278, 261 and 283, SFDPH's published counts (research/sources/datasf-traffic-crashes.md,
Published total). No published count by the two lower levels was found. The Controller's Vision Zero injury benchmark (sf.gov, "Vision Zero benchmarking:
injuries") gives all non-fatal injuries as "around 415" per 100,000 residents in 2022 and "just over 300" in 2020, from
SWITRS through TIMS; this table's 2022 rows (3,630 non-fatal people) are about 450 per 100,000 at 808,000 residents, so
the levels here run near but above the state's copy. The map's About page says so. Checks stop the run: row counts per
level and complete year against floors, unique person ids, every row's level one of the four, the 2022-2024 severe and
fatal rows with a point left out, at least 97% of rows with a point, and the published totals above.
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import collections
import json
import sys
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(paths.ROOT)
sys.path.insert(0, str(HERE))
import sfdata  # noqa: E402
from lib.stable import write_json  # noqa: E402

hik = paths.load("hin-injury-kinds.py")

OUT = ROOT / "data/extract/street-safety/light-injuries.json"
LEVELS = {"Fatal Injury": 0, "Severe Injury": 1, "Other Visible Injury": 2, "Complaint of Pain": 3}
FIRST = "2005-01-01"
# Per level per complete year. 2005 to 2025 run 20 to 43 deaths, 170 to 307 severe, 790 to 1,082 other visible and
# 1,944 to 3,194 complaint of pain (nwes-mmgh, queried 2026-11-19).
FLOOR = {0: 15, 1: 150, 2: 700, 3: 1700}
# Totals an agency publishes that the rows must reproduce, by (level, year): SFMTA's traffic deaths for 2025, and SFDPH's
# police-reported severe injuries for 2016 to 2018 (research/sources/datasf-traffic-crashes.md, Published total).
PUBLISHED = {(0, "2025"): 25, (1, "2016"): 278, (1, "2017"): 261, (1, "2018"): 283}
SELECT = ("case_id_pkey,victim_id,collision_datetime,collision_time,victim_degree_of_injury,victim_role,"
          "party_number_ckey,tb_latitude,tb_longitude,vz_pcf_code,intersection")
CARD_ROWS = ("victim_degree_of_injury in ('Fatal Injury','Severe Injury') and "
             "collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59'")


def point(r):
    """A row's (lon, lat) inside the city's box, or None: no coordinates, or a point that is not in San Francisco."""
    try:
        lon, lat = float(r["tb_longitude"]), float(r["tb_latitude"])
    except (TypeError, ValueError, KeyError):
        return None
    return (lon, lat) if -122.53 < lon < -122.35 and 37.70 < lat < 37.84 else None


def check_totals(counted, source, published=PUBLISHED):
    """Stops the run unless the severe and fatal people counted per (level, year) are the source's rows, and the
    published totals are reproduced. `counted` and `source` are Counters over (level, year)."""
    for k in sorted(set(counted) | set(source)):
        if k[0] <= 1:
            assert counted[k] == source[k], f"level {k[0]} {k[1]}: {counted[k]} people counted, the source has {source[k]} rows"
    for k, n in sorted(published.items()):
        assert counted[k] == n, f"level {k[0]} {k[1]}: {counted[k]} people counted, the published total is {n}"
USERS = ["Walking", "Biking", "Motorcycle or moped", "Scooter or board", "Car or truck", "Other"]
# The other party involved, one option per injured person, from the crash's other rows in DataSF 8gtc-pjc6 ("Parties are
# individuals involved in a traffic crash including drivers, pedestrians, bicyclists, and parked vehicles", the
# dataset's description, read 2026-11-20; `party_type` is "party type" and `stwd_vehicle_type` the "party CHP towing
# vehicle type"). Each other party row is read by other_mode() below. A person on foot is not a vehicle and a parked
# vehicle is not moving, so:
#   none      no other party: the person's own party is the only one in the crash (or the rest are its passengers)
#   foot      no other vehicle, moving or parked, and one or more people on foot
#   car       one other moving vehicle, a car, truck, bus or any motor vehicle that is not a motorcycle
#   moto      one other moving vehicle, a motorcycle, motor scooter or moped
#   bike      one other moving vehicle, a bicycle, e-bike, scooter, board or other non-motor vehicle
#   parked    no other moving vehicle, and one or more parked vehicles (parked_empty() adds the ones filed as drivers)
#   multiple  two or more other moving vehicles of any kind, known or not
#   unknown   one other moving vehicle whose type the report doesn't give (UNKNOWN_V)
# The keys and their order are site/src/safety-map/state.js OTHERS, which tools/street-safety/street-safety-map.py checks.
OTHERS = ["none", "foot", "car", "moto", "bike", "parked", "multiple", "unknown"]
# Vehicle types that say nothing about the vehicle. Nearly all are from 2005 to 2012 (414 to 952 people a year, then 26
# to 74 from 2013; 8gtc-pjc6, queried 2026-11-20). The dataset's description, read 2026-11-20: injury crash data comes
# from "SFPD's Interim Collision System for 2018 to YTD, Crossroads Software Traffic Collision Database (CR) for years
# 2013-2017 and the Statewide Integrated Transportation Record System (SWITRS) ... for all years prior to 2013". That
# SWITRS's copy is why the type goes unstated is [inference — mine]; the description names the switch, not its effect.
UNKNOWN_V = {"Not Stated", "Unknown Hit and Run", "Unknown", "Other", "Other Vehicle", ""}
# A towed unit. On a Driver row it is the rig the driver was in (a "Semi" with a driver), one vehicle; on a row with no
# driver (party_type "Other") it is the trailer behind a truck that has its own row, so it is not a second vehicle.
TRAILER_V = {"Trailer", "Pull", "Pull Tank Trailer", "Semi", "Semi Tank Trailer", "Two Trailers (Includes Semi & Pull)", "Two Tank Trailer",
             "Container Chassis", "Trailer Coach", "Fifth Wheel Travel Trailer", "Federally Legal Semi", "Extralegal Permit Load"}


def parked_empty(p):
    """A parked vehicle with nobody in it that the report files as a Driver or Other party: its movement is "Parked",
    it has no age and no sex, it is not at fault and nobody in it was hurt. That is what a Parked Vehicle row looks like
    (95% have no age or sex), and from January to June 2019 SFPD's records file parked vehicles this way: 91 such rows
    in those six months, 100 in all the other years (8gtc-pjc6, queried 2026-11-20). A Driver row whose movement is
    "Parked" but which has a driver's age or sex (677 of 812 outside those months, half of them at fault, as in a
    dooring) is a person in the crash and stays a vehicle party."""
    return (p.get("party_type") in ("Driver", "Other") and p.get("move_pre_acc") == "Parked" and not p.get("party_age")
            and (p.get("party_sex") or "Not Stated") == "Not Stated" and p.get("at_fault") != "Yes"
            and (p.get("party_number_injured") or "0") == "0")


def other_mode(p):
    """One other party row as walk, parked, car, moto, bike, unknown, or None for a row that is no party of its own.
    party_type decides a person on foot and a parked vehicle, and parked_empty() finds the parked vehicles filed under
    another type; after that the vehicle type, which also says "Pedestrian"
    and "Passengers" on a few Driver and Other rows (people, not vehicles). A known type is read with
    hin-injury-kinds.py party_mode(), the reading the Travel mode filter uses for the person's own party."""
    t, v = p.get("party_type"), p.get("stwd_vehicle_type") or ""
    if t == "Pedestrian":
        return "walk"
    if t == "Parked Vehicle" or parked_empty(p):
        return "parked"
    if v == "Pedestrian":
        return "walk"
    if v == "Passengers" or (v in TRAILER_V and t != "Driver"):
        return None
    if v in UNKNOWN_V:
        return "unknown"
    m = hik.party_mode(p)
    return "bike" if m == "other" else m


def other_party(own, ps, role=None):
    """The OTHERS key for a person whose own party number is `own` in a crash with party rows `ps` (by party number),
    or None where the crash has no row for the person's own party, so the others can't be told from it. A person whose
    victim_role is Pedestrian was on foot whatever party number the report files them under (17 are filed under a
    vehicle's), so a vehicle row is never their own: every vehicle in the crash is another party."""
    if own not in ps:
        return None
    mine = lambda k, p: k == own and not (role == "Pedestrian" and other_mode(p) != "walk")
    modes = [m for m in (other_mode(p) for k, p in ps.items() if not mine(k, p)) if m]
    moving = [m for m in modes if m not in ("walk", "parked")]
    if len(moving) > 1:
        return "multiple"
    if moving:
        return moving[0]
    return "parked" if "parked" in modes else "foot" if "walk" in modes else "none"


def party_rows(rows):
    """Party rows by case and party number. A (case, party number) that comes twice must read the same both times:
    the same party type, vehicle type and parked_empty(), which is all the Travel mode and Other party readings take
    from a row. Case 260408381's two parties each come twice, alike but for party 2's injured count (0 and 1). Two rows
    under one number that read differently stop the run, since keeping either would be a guess."""
    reading = lambda p: (p.get("party_type"), p.get("stwd_vehicle_type"), parked_empty(p))
    parties, twice = collections.defaultdict(dict), 0
    for p in rows:
        had = parties[p["case_id_pkey"]].setdefault(p.get("party_number_ckey"), p)
        if had is not p:
            assert reading(had) == reading(p), f"case {p['case_id_pkey']} party {p.get('party_number_ckey')} has two rows that read differently: {had} and {p}"
            twice += 1
    return parties, twice


def selftest():
    """The other-party rules and the duplicate check on rows made up for the purpose, run before every extract, so the
    check has been seen to fail."""
    row = lambda n, t, v: {"case_id_pkey": "x", "party_number_ckey": n, "party_type": t, "stwd_vehicle_type": v}
    me, ped, car = row("1", "Driver", "Passenger Car"), row("2", "Pedestrian", "Pedestrian"), row("3", "Driver", "Minivan")
    crash = lambda *rows: {r["party_number_ckey"]: r for r in rows}
    for want, got in [
            ("none", other_party("1", crash(me))), ("none", other_party("1", crash(me, row("2", "Other", "Passengers")))),
            ("foot", other_party("1", crash(me, ped))), ("foot", other_party("1", crash(me, row("2", "Other", "Pedestrian")))),
            ("car", other_party("1", crash(me, car))), ("car", other_party("1", crash(me, car, row("4", "Other", "Trailer")))),
            ("car", other_party("1", crash(me, row("2", "Driver", "Semi")))), ("moto", other_party("1", crash(me, row("2", "Driver", "Moped")))),
            ("bike", other_party("1", crash(me, row("2", "Bicyclist", "Bicycle")))), ("unknown", other_party("1", crash(me, row("2", "Driver", "Not Stated")))),
            ("parked", other_party("1", crash(me, ped, row("3", "Parked Vehicle", "Not Stated")))),
            ("parked", other_party("1", crash(me, dict(car, move_pre_acc="Parked", party_sex="Not Stated", at_fault="No", party_number_injured="0")))),
            ("car", other_party("1", crash(me, dict(car, move_pre_acc="Parked", party_age="41", party_sex="Male")))),
            ("car", other_party("1", crash(me, dict(car, move_pre_acc="Parked", at_fault="Yes")))),
            ("none", other_party("1", crash(dict(me, move_pre_acc="Parked")))),
            ("multiple", other_party("1", crash(me, car, row("4", "Driver", "Unknown Hit and Run")))),
            ("car", other_party("1", crash(me, ped), "Pedestrian")), ("car", other_party("2", crash(me, ped), "Pedestrian")),
            (None, other_party("9", crash(me)))]:
        assert want == got, f"other_party selftest: wanted {want}, got {got}"
    assert party_rows([me, dict(me)])[1] == 1
    try:
        party_rows([me, dict(me, stwd_vehicle_type="Bicycle")])
    except AssertionError:
        pass
    else:
        raise AssertionError("party_rows let two different rows under one party number through")
    # The totals check: a person dropped from a year, and a year short of its published total, each stop the run.
    C = collections.Counter
    check_totals(C({(0, "2025"): 25}), C({(0, "2025"): 25}), {(0, "2025"): 25})
    for counted, source in ((C({(0, "2025"): 24}), C({(0, "2025"): 25})), (C({(0, "2025"): 24}), C({(0, "2025"): 24}))):
        try:
            check_totals(counted, source, {(0, "2025"): 25})
        except AssertionError:
            continue
        raise AssertionError("check_totals let a year short of its total through")


def main():
    selftest()
    V = sfdata.fetch("nwes-mmgh", select=SELECT,
                     where="victim_degree_of_injury in ('Fatal Injury','Severe Injury','Other Visible Injury','Complaint of Pain') and "
                     "collision_datetime >= '%sT00:00:00' and not (victim_degree_of_injury in ('Fatal Injury','Severe Injury') and "
                     "collision_datetime between '2022-01-01T00:00:00' and '2024-12-31T23:59:59')" % FIRST, floor=75000)
    rows = {}
    for v in V.rows:
        k = (v["case_id_pkey"], v["victim_id"])
        assert k not in rows, f"duplicate person {k}"
        rows[k] = v
    newest = max(v["collision_datetime"][:10] for v in rows.values())
    per = collections.Counter((LEVELS[v["victim_degree_of_injury"]], v["collision_datetime"][:4]) for v in rows.values())
    for lv, fl in FLOOR.items():
        for y in range(2005, int(newest[:4])):
            if lv <= 1 and 2022 <= y <= 2024:
                assert per[(lv, str(y))] == 0, f"level {lv} {y}: the card path's rows leaked in"
                continue
            assert per[(lv, str(y))] >= fl, f"level {lv} {y}: {per[(lv, str(y))]} rows, floor {fl}"
    P = sfdata.fetch("8gtc-pjc6", select="case_id_pkey,party_number_ckey,party_type,stwd_vehicle_type,move_pre_acc,collision_datetime,"
                     "party_number_injured,at_fault,party_age,party_sex",
                     where="collision_datetime >= '%sT00:00:00'" % FIRST, floor=100000)
    parties, twice = party_rows(P.rows)
    # The 2022 to 2024 severe injuries and deaths: one with a point is the card path's (tools/street-safety/hin-people-map.py), one
    # with none is counted here.
    K = sfdata.fetch("nwes-mmgh", select=SELECT, where=CARD_ROWS, floor=900)
    carded = collections.Counter()
    for v in K.rows:
        k = (v["case_id_pkey"], v["victim_id"])
        if point(v):
            carded[(LEVELS[v["victim_degree_of_injury"]], v["collision_datetime"][:4])] += 1
        else:
            assert k not in rows, f"duplicate person {k}"
            rows[k] = v
    cases = {k[0] for k in rows}
    no_party = sum(1 for c in cases if c not in parties)
    assert no_party <= 0.01 * len(cases), f"{no_party} cases with no party rows"
    out, unplaced, no_own = [], 0, 0
    for k in sorted(rows):
        r = rows[k]
        lon, lat = point(r) or (None, None)
        unplaced += lon is None
        role = r.get("victim_role") or "Other"
        own = parties[r["case_id_pkey"]].get(r.get("party_number_ckey"))
        me = "walk" if role == "Pedestrian" else hik.party_mode(own) if own else "car"
        vt = (own or {}).get("stwd_vehicle_type") or ""
        user = {"walk": "Walking", "moto": "Motorcycle or moped", "car": "Car or truck", "parked": "Car or truck",
                "bike": "Biking" if vt in ("Bicycle", "Electric Bicycle", "Motorized Bicycle") else "Scooter or board"}.get(me, "Other")
        other = other_party(r.get("party_number_ckey"), parties[r["case_id_pkey"]], role)
        if other is None:
            no_own += 1
            continue
        ix = r.get("intersection") or ""
        h = hik.hour(r)
        out.append([lon if lon is None else round(lon, 5), lat if lat is None else round(lat, 5), r["collision_datetime"][:10], -1 if h is None else h, LEVELS[r["victim_degree_of_injury"]],
                    USERS.index(user), hik.cause(r.get("vz_pcf_code")), hik.code_key(r.get("vz_pcf_code")),
                    1 if ix.startswith("Intersection <=") else 0 if ix else -1, r["case_id_pkey"], OTHERS.index(other)])
    assert unplaced <= 0.03 * len(rows), f"{unplaced} of {len(rows)} rows have no point"
    # Every person takes exactly one option. A person whose own party row is missing has none: the filter would need an
    # "Unknown" option (state.js OTHERS, the page's select and the chart) before such a row can be drawn.
    assert no_own == 0, f"{no_own} people have no party row of their own in 8gtc-pjc6: add an Unknown option"
    by_other = collections.Counter(OTHERS[o[10]] for o in out)
    assert sum(by_other.values()) == len(out) and set(by_other) <= set(OTHERS)
    # The people with crash cards (tools/street-safety/hin-people-map.py: 2022 to 2024, severe or fatal, with a point), by victim_id.
    card_other = {}
    for v in K.rows:
        if not point(v):
            continue
        o = other_party(v.get("party_number_ckey"), parties[v["case_id_pkey"]], v.get("victim_role"))
        assert o is not None, f"card person {v['victim_id']} has no party row of their own: add an Unknown option"
        assert card_other.setdefault(v["victim_id"], OTHERS.index(o)) == OTHERS.index(o), f"victim {v['victim_id']} twice"
    counts = collections.Counter((o[4], o[2][:4]) for o in out)
    # A second read of the source, dates and levels only, to count against.
    T = sfdata.fetch("nwes-mmgh", select="collision_datetime,victim_degree_of_injury",
                     where="victim_degree_of_injury in ('Fatal Injury','Severe Injury') and collision_datetime >= '%sT00:00:00'" % FIRST, floor=5000)
    source = collections.Counter((LEVELS[v["victim_degree_of_injury"]], v["collision_datetime"][:4]) for v in T.rows)
    check_totals(counts + carded, source)
    write_json(str(OUT), {
        "fields": ["lon", "lat", "date", "hour", "level", "user", "cause", "subcause_key", "at_intersection", "case", "other"],
        "others": OTHERS, "by_other": {k: by_other[k] for k in OTHERS}, "card_other": dict(sorted(card_other.items())), "card_source": K.tag,
        "levels": {"0": "Fatal Injury", "1": "Severe Injury", "2": "Other Visible Injury", "3": "Complaint of Pain"}, "users": USERS,
        "sources": {"nwes-mmgh": V.tag, "8gtc-pjc6": P.tag}, "rows": len(rows), "unplaced": unplaced, "newest_row": newest,
        "by_level_year": {"%d/%s" % k: counts[k] for k in sorted(counts)}, "people": out})
    print(f"{len(out)} people of {len(rows)} rows ({unplaced} with no point, counted and not drawn), newest {newest} -> {OUT.relative_to(ROOT)}")
    print("other party: " + ", ".join(f"{k} {by_other[k]}" for k in OTHERS) + f"; sum {sum(by_other.values())}; {len(card_other)} card people; "
          f"{twice} party rows came twice, each reading the same")


if __name__ == "__main__":
    main()
