"""The Muni bus lines the line optimizer ("Upgrade a Bus Line") covers, and why each other dashboard line isn't on it.

Bryan, 2026-11-15, on the optimizer page: "Let's not include trains yet and call it 'Upgrade a Bus
Line'. And show all bus lines". So every line the Muni dashboard (site/data/muni.json) carries that SFMTA runs as a
bus today is on the picker, express and peak-only lines included (the 8AX, 8BX and 15 have a measured speed,
boardings, SFMTA's crowding and a timetable, which is all a menu needs), unless it lacks a figure the optimizer can't
start from: a speed in each of the page's three months. NOT_ON_PICKER names every other dashboard line with its
reason; scripts/muni-ewt/test_optimizer.py fails when a dashboard line is in neither list.

FREQUENT is the lever note's sixteen frequent bus lines (ridership.csv's Frequent Local and Rapid Bus, September
2026). The lever model ranks levers and takes its median line over them alone, so the note's figures don't move when
the optimizer covers more lines (lever_car_miles.py, "Lines").

Shared by stop_pair_lanes.py (open paths), stop_elev.py (block grades), stop_walk.py (stops removed), lever_car_miles.py
(per-line rows) and optimizer_build.py.
"""

FREQUENT = ("1", "14", "14R", "22", "24", "28", "28R", "30", "38", "38R", "49", "5R", "7", "8", "9", "9R")

# every bus line on the picker: the sixteen, SFMTA's Grid and Connector lines, and the express lines it runs today
OPT_BUS = tuple(sorted(FREQUENT + (
    "12", "18", "19", "2", "23", "27", "29", "31", "33", "43", "44", "45", "48", "5", "54", "6",  # Grid
    "25", "36", "37", "39", "52", "55", "56", "57", "66", "67",                                   # Connector
    "15", "8AX", "8BX",                                                                           # express
)))

# lines that already skip most local stops, so removing stops isn't their fix: the Rapids and the express lines (the 15
#   stops 28 times a trip against the 29's 75 to 85; stop_walk.py, lever_car_miles.py)
SKIPS_STOPS = tuple(sorted({l_ for l_ in OPT_BUS if l_.endswith("R")} | {"15", "8AX", "8BX"}))

_TRAIN = "a train; the page covers buses only for now (Bryan, 2026-11-15)"
NOT_ON_PICKER = {
    "21": "not running: SFMTA's timetable has no 21 Hayes trips, and the dashboard's last speed for it is June 2025",
    "35": "no measured speed: 511's records give the dashboard no speed for the 35 in any month, so the page has no "
          "speed to start from and no delay to cap a fix at",
    "58": "no measured speed: 511's records give the dashboard no speed for the 58 in any month, so the page has no "
          "speed to start from and no delay to cap a fix at",
    **{b: f"a bus run in place of the {b[0]} train before it starts, weekdays 5 to 6 am and weekends 5 to 8 am (SFMTA's "
          "GTFS), not a line of its own" for b in ("KBUS", "NBUS", "TBUS")},
    "KT": "a train (route type 0 in 511's route types), not in SFMTA's timetable today",
    "S": "a train (route type 0 in 511's route types), not in SFMTA's timetable today",
    **{t: _TRAIN for t in ("J", "K", "L", "M", "N", "T")},
    **{c: "a cable car" for c in ("CA", "PH", "PM")},
    "F": "a historic streetcar",
}

assert not set(OPT_BUS) & set(NOT_ON_PICKER) and set(FREQUENT) <= set(OPT_BUS) and len(OPT_BUS) == 45
