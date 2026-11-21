#!/usr/bin/env python3
"""One modelled city of SFUSD students: expected students from every home block to every school, the way each gets there from a nested logit on trip time and bike route fit to the 2024-25 Travel Tally, and each change applied on top in its study's own units.

    pipeline/venv-step.py tools/school-trips/school-sim.py                 # every school; writes out/school-sim/
    pipeline/venv-step.py tools/school-trips/school-sim.py --sample 3      # three schools only, for development; writes to .cache/school-sim/sample/
    pipeline/venv-step.py tools/school-trips/school-sim.py --check         # the quality checks on the written outputs
    pipeline/venv-step.py tools/school-trips/school-sim.py --selftest      # shows each check failing on bad input
    pipeline/venv-step.py tools/school-trips/school-sim.py --housing data/housing/pipeline-2030.json   # with the pipeline's new students; writes out/school-sim-housing-2030/

Steps 2 and 3 of the one-simulation school tool. Bryan,
2026-10-08: the tool should show "1) Your own individual experience getting to
school 2) Your school's experience 3) The city-wide experience from different
strategies. And these should all tie together." And, on the method: "distribute
students to schools and then have an expected number of students per block that
go to a school ... do the travel mode / travel time determination per block and
then end up with an probabilistically expected # of students per travel mode per
block." So a school's figure is the sum of its blocks' expected students, and
the city's the sum of its schools'.

SCHOOLS. Every school in CDE's Census Day file for San Francisco
(data/school-case/enrolment-sf.json, tools/school-trips/school-gravity.py) run by SFUSD
(district 68478) or chartered in the city, less the rows no student travels to
daily (EXCLUDE). The door is data/school-case/dropoff.json's for the case-study
schools, CDE's point (data/extract/schools/cde-sf.json) for the rest. SF's
private schools join them (data/school-sim/private-schools.json, CDE's private
school affidavit), each drawing students as SFUSD's citywide schools at its
level do (PRIVATE_RUN's note). County Office of Education schools are left out.

ASSIGNMENT, grade by grade (TK, K, 1 to 12): a doubly constrained gravity model
(Furness balancing) with tools/school-trips/school-gravity.py's fitted curve
f(x) = (x + d0)^-alpha exp(-beta x), x = straight-line miles over the school's
reach (its level's stretch, its requests per seat, and the choice stretch for a
charter). Each school's grade enrolment and each block's children of that age
(census 2020 DHC P12 by school_gravity.LEVEL_KIDS, scaled to the grade's
enrolment) are both met, so every student is placed exactly once, in
expectation. Step 1 spreads middle and high schools singly constrained; here
every grade is doubly constrained. A (block, school) pair holding under PRUNE
(0.1%) of the block's students in a grade is dropped from the choice and change
stage; validation.json's checks.prunedPct says what share of students that is.

ATTENDANCE AREAS (Bryan, 2026-10-08: "Use SFUSD
data to guess at what fraction of students come from the school's designated
neighborhood area (if it has one) vs. city wide, and for citywide, spread by
distance."). At each of the 58 schools with an SFUSD elementary attendance area
(DataSF e6tr-sxwg, school_gravity.attendance_areas), an elementary grade's
weight is a mix: a share over the area's blocks by their children, the rest by
the distance curve. fit_area picks each school's share, and the elementary
reach multiplier for the distance part, so the school's students spread across
home ZIPs as SFUSD's dashboard counts them (ZIP_CSV); gravity() then adjusts the
mix until the balanced matrix meets each share. Middle and high schools, and
citywide elementary schools, have no area, so they're the curve alone.
validation.json's attendanceArea gives each school's share and the student
weighted share by level. Fit to the ZIP counts, so the ZIP check below is a fit,
not a test.

TRIP TIMES, per block and school, from one set of shortest-path trees per
school on lib/school-travel-time.py's walk network (OpenStreetMap,
data/osm-cache/sf-walk.json) with OpenStreetMap's drivable streets joined in
(data/osm-cache/sf-drive.json, tools/travel/osm-drive-network.py; joined_graph):
the walk network leaves out a street whose sidewalks are mapped as their own
ways, so a car routed on it alone went far around Van Ness Avenue. Each trip
joins the network at the block's frontage and the door:
  walk     the shortest walk, at 2 mph, on walkable edges: not a car's street
           added from the drive network, and not a busway unless OSM tags it
           foot=yes. A block off the door's network (an island) takes the
           straight line x FALLBACK_DETOUR.
  car      the shortest drive on the drive network's streets (DRIVE_HW), at
           SFCTA's measured 13.4 mph morning median plus a 3-minute allowance
           for parking and the walk in, never shorter than the walk: step 1's
           car_minutes (tools/school-trips/school-case.py); then the moving part re-timed
           as CAR_GOOGLE_A + CAR_GOOGLE_B x it (1.68 + 0.955x), fit to Google
           Routes at the bell (minutes()). Two-way on every street: one-way streets
           and turn restrictions are not modelled.
  bike     ridden at BIKE_MPH (8.5 mph, fit to Google Routes) the whole way,
           plus BIKE_GOOGLE_MIN (1.1) and BIKE_FIXED_MIN, on the route
           with the smallest total gap off today's all-ages network (every
           off-network stretch summed, GAP_RULE) among routes at most
           25% longer than the shortest bikeable route (no stairs). Candidates
           come from trees that charge each metre off the network 1 + k times,
           k in GAP_K; the metres off the network (the total gap) and the
           summed rise (node elevations off the USGS 3DEP tiles
           tools/school-trips/street-grades.py caches, edge_rise) are carried down each
           tree (_tree, _tree_sums), the joins at either end counted as off the
           network. Timed on every network variant, and on two more for the
           back-cast: built (today's without the upcoming bikeways) and y2019.
  carpool  the car's time plus CARPOOL_EXTRA_MIN, our assumption.
  transit  scheduled Muni, door to door, from SFMTA's GTFS feed
           (tools/muni/muni-gtfs.py) by a reverse connection scan per grade band
           arriving MUNI_EARLY_MIN before the band's bell (muni_times), cached
           by the feed's hash.
  bus      the car's time plus BUS_EXTRA_MIN, ours, for TK-8 students over 2
           miles' walk.
The times are cached in .cache/school-sim/ by a key over their inputs.

TODAY'S CHOICE. A nest: the bike on top, P(bike) = inv.logit(g(d, h) + c[grade]),
g the Propensity to Cycle Tool's schools curve on the route's km and average
gradient (PCT_CURVE, capped at GRAD_CAP_PCT), and below it a logit over car,
carpool, walk, Muni and the yellow bus, U = ASC[mode, grade] + BETA_LOG[mode] x
ln(minutes), the family car's constant fixed at 0. Walking isn't a choice for
TK-5 past WALK_LIMIT_MI_K5, nor the bus outside its riders. BETA_LOG and the
walk limit are the best of a grid fit to SFCTA 2016 Fig. 3's K-5 drive-alone
share by distance band, the step-1 gate. Today's 2,000 yellow-bus riders
(BUS_TODAY) are its own target, the tally's shares scaled to make room. Bryan,
2026-10-08: "Time-based choice, but do it for all grades by extrapolating
distributions from the 4 grades that are in the travel tally." Each grade's
constants are fit so the expected citywide shares match that grade's target:
the family-car share follows a curve through the tally's four measured grades
(K 54%, 5th 56%, 6th 47%, 9th 33%; data/school-car-share/inputs.json),
straight lines between them, TK at K's value, and 10th to 12th held at 9th's
33% (Bryan, 2026-10-08: "Let's assume 9th grade is similar to 12th."); the
other modes split the rest in the tally's proportions, interpolated the same way
and held at 9th's past it (tally_targets). validation.json keeps one figure
continuing the 6th-to-9th line instead (curveByEnrolmentTrend). The model's all-students share is the grade curve
weighted by CDE enrolment by grade at the schools modelled.

THE TALLY BASIS. The tally's 48.6% is its respondents' mix, not an all-grade
figure: fitting its overall mix to its grade bars by non-negative least
squares, with the weights summing to 1, gives respondent weights K 0.212, 5th
0.373, 6th 0.148, 9th 0.232 and mixed 0.034 (TALLY_WEIGHTS; largest error 0.026
points). Fit to rounded bars, they are poorly identified one by one. So
city.json's carTally is 48.6 plus the modelled change in each grade band's
family-car share, weighted K-5 0.606, 6-8 0.153, 9-12 0.240 (TALLY_BAND_W, mixed
spread in proportion): the model starts at the measured 48.6% and every change
is on the basis of SFMTA's 30% goal. city.json also carries each band's share
(carK5, car68, car912), so the check recomputes carTally from them. Each
school's carTallyPts is its part of that change, so the page can sum schools.

THE SCHOOL VIEW'S CONTROLS. Five on/off toggles, every combination of them
(COMBOS, 32): School Street, Calm Streets, Protected School Connector, and
(Bryan, 2026-10-08) free Muni for a caregiver riding with a child and yellow
school bus seats, each as THE OTHER LEVERS below define it, and, at the case-study schools step 1 ranked, 0, 1, 3, 5, 10 or 20 of its
ranked bikeway blocks (site/data/school-case/<id>.json, topBlocks.brp, best
first) added to the network (BLOCK_NS). Every measure is written for every
cell of that grid and each of the three CASES, so the page only looks values up:
  School Street            the school's family-car share down 5.3 points
                           (Patterson et al. 2025): one utility penalty on the
                           car, solved per school, moving the car's share to the
                           other modes in proportion. Applied first.
  Traffic calming          part of Safety Upgrades for Walking: every
                           residential street edge whose midpoint is within an
                           eighth of a mile of the door counts as safe, at the
                           schools the central calming budget reaches in
                           calm-priority.json's order (limit_calm).
  Protected School Connector  SFMTA's School Connector, protected where needed
                           (step 1's kf): the shortest walk from the door to the
                           nearest street of a safe run at least half a mile long
                           counts as safe.
  the cases                Bryan, 2026-10-18: low, central and high. Each
                           moves a student's bike
                           logit by lambda x caseD x the rise in the route's
                           on-network share over today's, at year 10 of ten:
                           caseD is the PCT's Go Dutch shift less the level's
                           SF reference, High is lambda 1, Low is sized so a
                           full network gives Cambridge, MA's 14.3% of students
                           biking, Central is halfway. A route that gains
                           nothing gets nothing.

THE OTHER LEVERS (levers in the outputs), each alone and all together on
today's network, in their studies' own units, for the city view:
  safer_crossings  walking and biking up 3.3 points (McDonald et al. 2014,
                   p. 160) across the school's TK-8 students, the grades the
                   study covered: one utility bonus on walk and bike, solved
                   per school.
  walking_bus      walking and biking up 9.04 points among TK-5 students
                   living within a mile's walk (Johnson et al. 2024: grades 3-5,
                   within 1 mile), solved per school. The study did not test
                   TK-2; applying it there is our assumption (Bryan, 2026-10-09:
                   "Extend to TK-5").
  caregiver_muni   our labelled estimate: a TK-8 student who is driven and
                   whose Muni trip is within 15 minutes of the car switches to
                   Muni with probability 21% (caregivers who named cost, School
                   Access Plan p. 33) x 50% (take-up, our assumption).
  yellow_bus       shuttle loops at Denver's loop take-up (Bryan, 2026-10-15):
                   640 new riders citywide, 580 to 700, among TK-8 students
                   living over 2 miles' walk, by one shift on the bus
                   constant; the riders come from the other modes as the
                   choice gives them, checked against MyBus's 48% from a
                   single-family car.
  carpool          our labelled guess (Bryan, 2026-10-09): 5% of the families who
                   drive form two-family carpools, which a matching tool like
                   Denver's SchoolPool might achieve (https://cbsm.com/cases/
                   34151-denver-s-schoolpool: 19,000 families on 150 campuses,
                   500 fewer vehicle miles per family a year, method not
                   stated). Every driven student's car share moves 5% to
                   carpool. No study measures it.
  ebike            our labelled guess (Bryan, 2026-10-09, one "increase e-bike
                   adoption" bucket): at a school passing the e-bike gate
                   (EBIKE_GATE_MI), every student takes the PCT's e-bike
                   term, +0.1812 on the gradient coefficient, on the bike
                   logit; the ride is 15% faster in the trip-time figures.
  school_street    as above.
  car_cost         parking priced and a driving charge as one lever, not in
                   "all": a daily charge, $8 ($4 to $16), split over the
                   household's daily vehicle trips (CAR_COST_TRIPS, NHTS
                   2022), half on a carpool, priced by a money term at
                   USDOT's value of time on SF's median household income,
                   $33.60 an hour ($23.50 to $40.30). It moves the inner logit
                   only, and is tested against CHILL's ULEZ result.
"all" applies the student-level rules (Muni, bus, carpool, e-bike) first, then the school-level
shifts (crossings, walking bus, School Street last).

OUTCOMES, per school and citywide, for every cell of the grid and every lever:
  mode share       expected students by mode.
  medianMin        the weighted median of the expected students' trip minutes
                   on their chosen modes.
  noCaregiverPct   our assumption (SOLO): the share of students whose trip
                   needs no parent. Today: walking or biking from 3rd grade
                   when the trip is at most 15 minutes and the bike route's
                   total gap off today's all-ages network is at most
                   1,000 ft; Muni from 6th grade; a yellow bus at any grade.
                   It changes only with students who move onto a trip another
                   adult supplies (FREE_CREDIT): a yellow bus, a volunteer-led
                   walking school bus (two of three freed) or a two-family
                   carpool (half). Street changes, networks, the bike switch
                   and Free Muni for caregivers free no parent. The grades
                   and limits are parameters.
  safeTripPct      the share whose chosen trip is a safe one of at most 15
                   minutes: walking or biking with the bike route's total
                   gap at most 1,000 ft, or Muni door to door.
  injuries         a 5-year total of injury crashes, and severe or fatal ones,
                   within 600 ft of the school at its bell hours on school days
                   (out/school-hour-crashes/schools.json), scaled from its four
                   school years, 2022-23 to 2025-26, by 5/4. A scenario's figure
                   is today's times the change in family-car miles on the
                   school's expected trips: an exposure-based change only, with
                   no crash modification factor. The change in walking and
                   biking miles is written beside it.

VALIDATION (out/school-sim/validation.json, printed): every grade's car share,
marked measured, interpolated, extrapolated or held; the citywide figures beside
the tally's four-grade 48.6% and the 30% goal; the step-1 gate, K-5 family-car and
Muni shares by walking distance against SFCTA's 2016 Child Transportation
Survey Fig. 3 (byDistance), with BETA_LOG_ALT beside it; the cases' lambdas and
year-10 bike shares at full network; the bike curve's inputs (bikeCurve); the
back-cast from the 2019 network against the tally's 0 to 2.5 points (backcast);
the car charge at each price and value of time, and its test against CHILL's
London children (carCost); K-5 trip lengths against Fig. 5 of the School
Access Plan; and each change at the case-study schools beside its study's
effect. Stage timings are recorded in stageSeconds.

HOUSING (--housing PATH; Bryan, on School Trips: "How many of these projects
will be done by around 2030? Include them all in the simulation."). The new
SFUSD students a housing pipeline brings, from scripts/housing-pipeline.py
(data/housing/pipeline-2030.json, the projects likely done by about 2030, or
pipeline-all.json, the whole pipeline), are added after calibration
(add_housing). Each project's students go to the nearest block with children
of each level, split across grades by CDE enrolment by grade at every modelled
school. They are origin-constrained only: from their block and grade they
attend schools by the balanced matrix's weights, attendance-area mix included,
so a school's enrolment grows by what it receives. Capacity isn't modelled.
Every later stage treats them like other students, at today's mode-choice
constants. The run writes out/school-sim-housing-<case>/ (with housing.json:
per school the added students and the 2023 Facilities Master Plan's spare
seats, data/housing/fmp-seats.json) and its page data under
.cache/school-sim-housing-<case>/site/, never out/school-sim or
site/data/school-sim; a --sample goes to .cache/school-sim-housing-<case>/sample/.

QUALITY CHECKS (pipeline/README.md, rule 2): row floors,
required fields, unique keys, choice probabilities summing to 1, every
student assigned exactly once (each block's children and each school's
enrolment met by the balanced matrix), and the car route: among block-school
pairs at least CAR_DETOUR_MIN_MI apart on foot, under CAR_DETOUR_MAX_PCT drive
more than CAR_DETOUR_X times the walk (trips() stops before writing otherwise). They run after every build, and again
on the written files with --check; --selftest feeds each one bad input.

WRITES out/school-sim/:
  schools.json     per school: enrolment and drop-off and pickup bells by grade
                   range (SFUSD's 2025-26 start and end times; null where none
                   matches), grid[combo][blocks][measure] = one value per
                   case, and levers[scenario][measure].
  city.json        the same grid and levers citywide (blocks 0 only).
  blocks.json      per block, grade band and likely school: odds, expected
                   students, minutes by mode, total gap on each network,
                   today's choice, the car share after a School Street, and the
                   High case's logit shift on each street change.
  ranking.json     the city view's ordering inputs per school, read from the
                   scripts that own them (crashes, distance to the networks,
                   EJ community, SFMTA's group), plus the share with a safe
                   15-minute walk or bike trip.
  validation.json  the checks above.
Sorted and stamp-free, so a rerun on the same inputs changes nothing.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import glob
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import school_grounds  # noqa: E402
from lib import school_points  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = paths.ROOT
sys.path.insert(0, HERE)
from lib import stable  # noqa: E402
from lib.quality import Each, Table, run as run_checks  # noqa: E402


def _load(name, path):
    """Run the script at `path` as module `name`; a path under this repo goes through lib/paths.py."""
    if os.path.dirname(os.path.abspath(path)).startswith(paths.ROOT + os.sep):
        return paths.load(os.path.basename(path), name)
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Step 1 (tools/school-trips/school-gravity.py) may live in another checkout while it is
# unmerged: SCHOOL_SIM_STEP1_ROOT points at it, read only.
STEP1 = os.environ.get("SCHOOL_SIM_STEP1_ROOT") or ROOT
OUT = os.path.join(ROOT, "out", "school-sim")
CACHE = os.path.join(ROOT, ".cache", "school-sim")
MI = 1609.344
FT = 0.3048
PRUNE = 0.001           # a (block, school) pair under 0.1% of the block's students in a grade is dropped
FURNESS_ITERS = 500
MAX_WORKERS = 5          # Bryan, 2026-10-01: "allow up to 5 workers"
SEGMENTS_MAX_WORKERS = 3   # Team Lead, 2026-10-14: at most 3 workers, CP-SAT included; 6 put the load at 31
# A cloud VM, not this Mac, may raise both caps (SCHOOL_SIM_MAX_WORKERS=N): the limits above are this machine's.
if os.environ.get("SCHOOL_SIM_MAX_WORKERS"):
    MAX_WORKERS = SEGMENTS_MAX_WORKERS = int(os.environ["SCHOOL_SIM_MAX_WORKERS"])
WALK_MPH = 2.0
CAR_MPH, CAR_FIXED_MIN = 13.4, 3.0   # step 1's, tools/school-trips/school-case.py (SFCTA INRIX, Sept 2026, 8-9 AM median); the fixed part is parking and the walk in
BIKE_FIXED_MIN = 1.0     # getting the bike out and locking it: our assumption
# Calibrated to Google Routes at the bell, 500 home-to-school trips (notes/school-trips-2026-10/2026-10-08-google-drive-bike-check.md;
# fit in notes/school-trips-2026-10/2026-10-09-sim-calibration.md, scripts/research/google-routes-calibration-fit.py). Least
# squares of Google's minutes on the sim's moving minutes, dropping routes over 2.5x the sim's distance: drive drop-off
# 1.60 + 0.967x, pickup 1.76 + 0.944x, both pooled 1.68 + 0.955x (392 rows), bike 1.07 + 1.175x. So the car's moving time
# becomes CAR_GOOGLE_A + CAR_GOOGLE_B x the routed moving time (starts, stops, side streets), and the bike rides at
# 10 / 1.175 mph plus BIKE_GOOGLE_MIN. Both are applied in minutes(), after the cached trip-time section, so the routing
# cache stands. Every conversion back to miles undoes them. The bike speed partly absorbs route choice: Google's bike
# routes are 17% longer than the sim's at the median.
CAR_GOOGLE_A, CAR_GOOGLE_B = 1.68, 0.955
BIKE_MPH = 8.5
BIKE_GOOGLE_MIN = 1.1
CARPOOL_EXTRA_MIN = 2.0  # picking up another child: our assumption
# The choice among the modes other than the bike: U = ASC[mode, grade] + BETA_LOG[mode] x ln(minutes), the family car's
# constant fixed at 0. The values are the best of a 168-point grid fit to SFCTA 2016 Fig. 3's K-5 drive-alone share by
# distance band with the tally matched by grade (notes/school-trips-2026-10/2026-10-18-step1-nested-choice.md): car
# within 1.6 points in every band. BETA_LOG_ALT is the grid's best when Fig. 3's Muni bars are weighted in too.
BETA_LOG = {"car": -1.5, "carpool": -1.5, "bus": -1.5, "walk": -0.75, "transit": -0.5}
BETA_LOG_ALT = {"muniBandsWeighted": {"car": -1.0, "carpool": -1.0, "bus": -1.0, "walk": -0.5, "transit": -0.5}}
# Walking isn't a choice for a TK-5 student more than this many walking miles from school: ours, chosen by the same fit
# (without it 14% of K-5 students over 2 miles walked, on a 110-minute mean walk).
WALK_LIMIT_MI_K5 = 1.5
# A Muni trip's fixed part for scaled_minutes(): the walks to and from the stops and the wait, kept when an assignment
# option brings the school closer. Our assumption.
TRANSIT_FIXED_MIN = 10.0
# THE BIKE, nested on top of the other modes: P(bike) = inv.logit(g(d, h) + c[grade]), the Propensity to Cycle Tool's
# schools curve (Goodman et al. 2019, Boxes 1 and 2, https://eprints.whiterose.ac.uk/id/eprint/141852/20/1-s2.0-S2214140518301257-main.pdf
# [primary — read 2026-10-18]): d the route's km on today's network, h its average gradient in percent, centred on
# the Dutch 0.63%. TK-5 take the primary curve and 6-12 the secondary (the R package codes the secondary only; the
# primary coefficients are the paper's). Past the 5 km and 10 km fit limits the curve runs on as published: our choice.
# The gradient is capped at GRAD_CAP_PCT, the top of England's fit range (Fig. 2b), and the share capped is reported.
PCT_CURVE = {"primary": {"a": -4.813, "d": 0.9743, "d2": -0.2401, "sqrt": 0.0, "h": -0.4245},
             "secondary": {"a": -7.178, "d": -1.870, "d2": 0.0, "sqrt": 5.961, "h": -0.5290}}
PCT_H0 = 0.63
GRAD_CAP_PCT = 5.0
PCT_MAX_KM = 30.0          # a cap on d so the primary curve's square can't overflow; P(bike) is under 1e-9 long before it
# Go Dutch, the High case's target shift (Box 2): +3.642 primary, +3.574 + 0.3438 d secondary.
PCT_DUTCH = {"primary": (3.642, 0.0), "secondary": (3.574, 0.3438)}
# The PCT's e-bike scenario: +0.1812 on the gradient coefficient (the ebike lever and the e-bike sensitivity).
PCT_EBIKE_H = 0.1812
DETOUR = 1.25            # school-travel-time.py's cap
FALLBACK_DETOUR = 1.3    # straight line to street distance, for a block off the door's network: our assumption
GAP_K = (0.0, 1.0, 4.0, 16.0)
# The gap rule: a route's gap is its total off the all-ages network, every off-network stretch between home and school
# summed (_route_off). Bryan, 2026-10-21: "This is not the standard I asked for -- I asked for total gap of 1000 feet or
# less between home and school". Part of the trip cache's key, so a cache written under the longest-run rule is not read.
GAP_RULE = "total"
BLOCK_NS = (0, 1, 3, 5, 10, 20)   # the school view's bikeway-blocks control
ZONE_FT = 660            # Traffic calming: residential streets within an eighth of a mile of the school grounds (Bryan, 2026-10-13)
# Calming goes to schools in calm-priority.json's order (kids hurt nearby over 10 school years) until the budget
# runs out, at CALM_PER_MI a mile. Bryan, 2026-10-13: "a range for calming from $5M to $20M for an eigth of a mile of
# streets, and use $10M as the central estimate. With top injury schools (over last 10 years) as the priority order".
CALM_BUDGETS_M = (5.0, 10.0, 20.0)   # low, central, high; the central picks the schools the simulation calms
CALM_PER_MI = 0.25                   # $M a mile, the page's calmed-street rate (SFMTA Slow Streets plus 25%)
CALM_PRIORITY = os.path.join(ROOT, "data", "school-sim", "calm-priority.json")   # tools/school-trips/school-calm-priority.py
# E-bike help only at a school where most of its students living within EBIKE_GATE_MI have a bike route whose total
# gap passes the bike switch test (Bryan, 2026-10-13: "only do it at a school when it has a safe pathway for majority
# of students within 2 miles").
EBIKE_GATE_MI = 2.0
ZONE_HW = {"residential", "living_street", "unclassified"}
CONNECT_MIN_MI = 0.5     # a connector ends on a safe run at least this long, as tools/school-trips/school-case.py
DRIVE_HW = {"residential", "tertiary", "secondary", "primary", "unclassified", "living_street", "trunk", "service",
            "primary_link", "secondary_link", "tertiary_link", "trunk_link", "motorway", "motorway_link", "residential_link"}
DRIVE_CACHE = os.path.join(ROOT, "data", "osm-cache", "sf-drive.json")   # tools/travel/osm-drive-network.py
# Busy crossings (Bryan, 2026-10-14, a design rule, not a measured finding): a bike route that crosses a street of
# XING_LANES lanes or more, or posted at XING_MPH or more, at a crossing with no signal is broken whatever its gap.
# Busy streets and their nodes come from OpenStreetMap's lanes and maxspeed tags (DRIVE_CACHE); a node is signalled
# when a crossing way tagged crossing=traffic_signals or crossing:signals=yes touches it or lies within XING_SIGNAL_M.
# A route crosses at a node when it passes through on two edges neither of which is on the busy street. A broken
# route's gap carries BREAK_FT on top, so the switch test fails it and the plain figure is still there. The weighted
# searches charge XING_PEN_M of unsafe street per edge that reaches such a node, so they steer to a signal nearby.
XING_LANES, XING_MPH = 4, 35
XING_SIGNAL_M = 25.0      # our assumption: an intersection's own nodes
XING_PEN_M = 400.0        # our assumption
BREAK_FT = 1e5
# The car-route quality check: among block-school pairs at least CAR_DETOUR_MIN_MI apart on foot, the share whose
# drive is over CAR_DETOUR_X times the walk must stay under CAR_DETOUR_MAX_PCT, or the run stops. A car on a
# walk-only network failed it at 14.9% of students (Fable review, 2026-10-08).
CAR_DETOUR_X, CAR_DETOUR_MIN_MI, CAR_DETOUR_MAX_PCT = 2.0, 0.5, 1.0
SFUSD = "68478"
EXCLUDE = {"District Office": "no students attend it",
           "\"Nonpublic, Nonsectarian Schools\"": "students placed at private special-education schools; no campus",
           "Independence High": "independent study; no daily trip",
           "Five Keys Charter (SF Sheriff's)": "runs in the county jails",
           "Five Keys Independence HS (SF Sheriff's)": "runs in the county jails"}
GRADES = ["TK", "KN", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
GNUM = {g: (0 if g in ("TK", "KN") else int(g)) for g in GRADES}
LEVEL = {g: ("elementary" if GNUM[g] <= 5 else "middle" if GNUM[g] <= 8 else "high") for g in GRADES}
BAND = {"elementary": "K-5", "middle": "6-8", "high": "9-12"}
MODES = ["car", "carpool", "walk", "bike", "transit", "bus"]   # bus only under yellow_bus
CHOICE = MODES[:5]
CAR, POOL, WALK, BIKE, TRANSIT, BUS = range(6)
# For walking_bus, caregiver_muni and carpool, the sim runs a full-strength set, and the page blends each one down to
# its own central and range (WEIGHT in site/src/school-trips-model.mjs). So a set's size here is a ceiling at least
# as big as the page's high end, not the effect anyone reads.
CHANGES = {
    "school_street": {"pp": 5.3, "max_grade": 5, "src": "Patterson et al. 2025, https://pmc.ncbi.nlm.nih.gov/articles/PMC12964863/",
                      "study": "private motor vehicle share down 5.3 points (2.5 to 8.2) at 166 UK primary schools; applied to TK-5 students only"},
    # The safe-route test. It moves no one (the three cases do, Bryan 2026-10-18): it is the bikeway
    # program's objective until plan step 6, the e-bike gate's test and the safe-trip measures' gap rule.
    "bike_switch": {"within_min": 5.0, "gap_total_ft": 1000.0, "src": "Bryan's rule, 2026-10-08",
                    "study": "a safe route: the bike within 5 minutes of the car and the total gap off the all-ages "
                             "network at most 1,000 ft"},
    "safer_crossings": {"pp": 3.3, "max_grade": 8,
                        "src": "McDonald et al. 2014, p. 160, https://mcdonald.web.unc.edu/wp-content/uploads/sites/8583/2014/12/McDonald_etal_ImpactsSRTS_JAPA2014.pdf",
                        "study": "walking and biking up 3.3 points at schools with an engineering improvement"},
    "walking_bus": {"pp": 9.04, "min_grade": 0, "max_grade": 5, "within_mi": 1.0,
                    "src": "Johnson et al. 2024, https://pmc.ncbi.nlm.nih.gov/articles/PMC11083767/",
                    "study": "the full-strength set the page blends down from: days walked or biked up 9.04 points (1.10 "
                             "to 16.98), grades 3-5 within 1 mile, with paid leaders. The page's figure is 0.37 car points "
                             "of TK-5 students (0 to 1), wb_pts in site/data/school-trips-assumptions.json"},
    "caregiver_muni": {"cost_share": 0.21, "takeup": 0.5, "within_min": 15.0, "max_grade": 8,
                       "src": "SFCTA School Access Plan, May 2023, p. 33 (21% of caregivers named cost)",
                       "study": "the full-strength set the page blends down from, half of the 21% who named cost. The "
                                "page's figure is Muni's share up 1 point (0 to 3) among TK-8 students over half a mile, "
                                "muni_pts in site/data/school-trips-assumptions.json"},
    # Bryan, 2026-10-15 (task ): "Use loop take-up". Denver's Success Express loops carried 8.9% to
    # 10.7% of eligible students (data/evidence/studies.json, denver-success-express), so about 580 to 700 of SF's 6,500
    # TK-8 students over 2 miles, 640 central. 48% previously driven is MyBus's own 64% weighted by SF's grades
    # (wsp-2009-mybus).
    "yellow_bus": {"over_mi": 2.0, "max_grade": 8, "riders": 640, "riders_low": 580, "riders_high": 700,
                   "over2_students": 6500, "car_frac": 0.48,
                   "src": "Denver's Success Express loop take-up, 8.9% to 10.7% of eligible students, applied to SF's 6,500 TK-8 students over 2 miles (SFCTA School Access Plan p. 42); 48% previously driven from West Yorkshire's MyBus (64%) weighted by SF's grades",
                   "study": "640 riders (580 to 700), Denver's loop take-up, on SFUSD's costed loops for TK-8 students over 2 miles' walk, by one shift on the bus constant; the share leaving a single-family car comes out of the choice and is checked against MyBus's 48%"},
    "carpool": {"share": 0.05,
                "src": "Bryan, 2026-10-09, on Denver's SchoolPool, https://cbsm.com/cases/34151-denver-s-schoolpool",
                "study": "the full-strength set the page blends down from: 5% of driving families in two-family "
                         "carpools. The page's figure is 0.5% of driven students (0.2% to 1%), pool_share in "
                         "site/data/school-trips-assumptions.json"},
    "ebike": {"faster": 0.15, "gradient": PCT_EBIKE_H,
              "src": "Bryan, 2026-10-09: one 'increase e-bike adoption' bucket (lending, renting, help buying); the PCT's "
                     "e-bike scenario, Goodman et al. 2019 / ITSLeeds/pct",
              "study": "the full-strength set the page blends down from: every student at a school passing the e-bike gate "
                       "gets the PCT's e-bike term, +0.1812 on the gradient coefficient; the ride is 15% faster for the "
                       "trip-time figures; no study measures take-up"},
    # Parking priced and a driving charge, one lever (plan section 3): a daily charge on the family car turned into
    # minutes through one value of time. The value of time is USDOT's rule for local personal travel, 50% of hourly
    # median household income at 2,080 hours a year, range $9.50 to $16.30 around $13.60 (FAA's reproduction of the
    # USDOT 2016 guidance, Table 1-1, https://www.faa.gov/regulations_policies/policy_guidance/benefit_cost/econ-value-section-1-tx-time.pdf
    # [primary — read 2026-10-18]; the USDOT memo itself refused the fetch), applied to San Francisco's median
    # household income, $139,801 (ACS 2024 1-year B19013, via https://api.censusreporter.org/1.0/data/show/acs2024_1yr?table_ids=B19013&geo_ids=05000US06075
    # [primary — read 2026-10-18]): $33.60 an hour, $23.50 to $40.30 on USDOT's range. The charge's range is ours:
    # the high end is London's ULEZ daily charge, GBP 12.50, at about $1.27 [model knowledge — verify]. Set without
    # looking at the ULEZ result, so CHILL's child switching (inputs.json london_ulez) is a test of it.
    "car_cost": {"usd_day": {"low": 4.0, "central": 8.0, "high": 16.0},
                 "vot_usd_hr": {"low": 23.5, "central": 33.6, "high": 40.3},
                 "src": "USDOT value of travel time (local personal, 50% of hourly median household income) on SF's ACS 2024 median household income; charge range ours",
                 "study": "the full-strength set: a daily charge on every family car, $8 ($4 to $16), split over the household's 3.46 daily "
                          "vehicle trips (NHTS 2022) and priced at $33.60 an hour ($23.50 to $40.30) by a money term in the inner logit; the bike doesn't move, since the nest's bike "
                          "share depends on the route alone"},
    # SFUSD's two assignment options on the Board's 2026-10-13 agenda. Stanford's average elementary home-to-school
    # distance: 1.40 mi today, 1.21 Neighborhood + All Schools, 1.06 Neighborhood + Citywide Programs (SFUSD Study
    # Session #2, 2026-08-28). Every elementary trip's distance part is scaled by the option's ratio to today, and the
    # student re-chooses in the calibrated logit. Bryan, 2026-10-09: default to Neighborhood + All Schools.
    "assign_nas": {"ratio": round(1.21 / 1.40, 4), "max_grade": 5,
                   "src": "SFUSD Study Session #2, 2026-08-28, https://go.boarddocs.com/ca/sfusd/Board.nsf/pfiles/DXE3RY083148/$file/School%20Reorg%20Study%20Session%20%232%20%28FINAL%2C%208.28.26%29.pdf",
                   "study": "Stanford's average elementary distance falls from 1.40 to 1.21 miles under Neighborhood + All Schools; every TK-5 trip scaled by that ratio"},
    "assign_ncp": {"ratio": round(1.06 / 1.40, 4), "max_grade": 5,
                   "src": "SFUSD Study Session #2, 2026-08-28, https://go.boarddocs.com/ca/sfusd/Board.nsf/pfiles/DXE3RY083148/$file/School%20Reorg%20Study%20Session%20%232%20%28FINAL%2C%208.28.26%29.pdf",
                   "study": "Stanford's average elementary distance falls from 1.40 to 1.06 miles under Neighborhood + Citywide Programs; every TK-5 trip scaled by that ratio"},
}
ASSIGN = ("assign_nas", "assign_ncp")
# SFUSD's general-education yellow buses carry about 2,000 riders today (SFCTA School Access Plan, May 2023, p. 42, via
# data/school-car-share/inputs.json and notes/school-trips-2026-10/2026-10-14-deep-transit-bikebus.md). The Travel Tally
# the mode shares come from has no school-bus bar (its car share was rescaled with the bus taken out), so today's riders
# are seeded back: TK-8 students over 2 miles' walk, each mode giving up the same share, so the riders come to BUS_TODAY.
BUS_TODAY = 2000
# The school view: three on/off toggles, every combination, and the bike-switch slider (Bryan, 2026-10-08).
# Bryan, 2026-10-08 (staging ), on free Muni for a caregiver riding with a child: "Add it and yellow
# bus". They join the toggles as two more scenario options, not new kinds of control.
TOGGLES = ("school_street", "calm", "connector", "caregiver_muni", "yellow_bus")
COMBOS = [dict(zip(TOGGLES, [(i >> (len(TOGGLES) - 1 - k)) & 1 for k in range(len(TOGGLES))])) for i in range(2 ** len(TOGGLES))]
# Every other lever, alone and together, on today's network, for the city view. "all" carries Neighborhood +
# Citywide Programs: the SFUSD Board voted 5-2 for it on 2026-10-13
# (https://sfstandard.com/2026/10/14/sfusd-board-votes-neighborhood-school-plan/ [web search -- verify]).
LEVERS = ["assign_ncp", "caregiver_muni", "yellow_bus", "carpool", "ebike", "safer_crossings", "walking_bus", "school_street"]
# The other assignment option is a lever alone, not part of "all", which takes the adopted option.
# Car costs (parking priced and a driving charge) are a lever alone, not in "all": the 2026-10-18 rebuild adds them,
# and the page's road pricing already carries a charge's coverage.
# The school trip's share of a daily charge: US households made 3.46 vehicle trips a day in 2022, 5.11 in 2017
# (FHWA, Summary of Travel Trends: 2022 NHTS, Table 2-8, https://nhts.ornl.gov/assets/2022/pub/2022_NHTS_Summary_Travel_Trends.pdf
# [primary — read 2026-10-18]). National, not SF's.
CAR_COST_TRIPS = 3.46
CAR_COST_TRIPS_ALT = 5.11
CAR_COST_FORM = "money"
# The ULEZ test (car_cost_check). The charge fell only on non-compliant cars: 61% of vehicles in the zone met the
# standard in March 2019, the month before it began, and the charge was "£12.50 per day for cars, motorcycles and
# vans" (Mayor of London, Central London ULEZ Six Month Report, October 2019, pp. 3 and 5,
# https://www.london.gov.uk/sites/default/files/ulez_six_month_evaluation_report_final_oct.pdf [primary — read 2026-10-18]).
# £12.50 is about $16 at 1.27 dollars a pound [model knowledge — verify]. CHILL's adjusted odds ratio, 3.47 (1.73 to
# 7.02, Xiao et al. 2024, Table 3), on Luton's 74 of 364 gives London's driven children leaving the car at 30.6% to
# 64.2%, a gap over Luton of 10.3 to 43.9 points around the raw 21.6 [inference — mine]. The model passes when its
# gap lands in that range.
ULEZ_NONCOMPLIANT = 0.39
ULEZ_USD_DAY = 16.0
ULEZ_GAP_PTS = (10.3, 21.6, 43.9)
SCENARIOS = {"today": [], **{k: [k] for k in LEVERS}, "assign_nas": ["assign_nas"], "car_cost": ["car_cost"], "all": list(LEVERS)}
ORDER = LEVERS + ["assign_nas", "car_cost"]
CRASH_YEARS_COVERED = 4    # school-hour-crashes.py's bell-hour counts span 2022-23 to 2025-26
CRASH_YEARS_SHOWN = 5


def combo_key(c):
    return "ss%d-calm%d-conn%d-muni%d-bus%d" % (c["school_street"], c["calm"], c["connector"], c["caregiver_muni"], c["yellow_bus"])


def variant_of(c):
    return {(0, 0): "today", (1, 0): "calm", (0, 1): "connector", (1, 1): "both"}[(c["calm"], c["connector"])]


# SFCTA, Findings of the Child Transportation Survey, Nov 2016, pp. 10 and 12: K-5, driven at drop-off.
CTS_2016 = {"under1": 46.0, "1to2": 61.0, "over2": 59.2}
CTS_SRC = "https://www.sfcta.org/sites/default/files/2019-03/Child_Transportation_FINAL.pdf"
BLOCK_ODDS_MIN = 0.02    # blocks.json keeps a block's schools at or above these odds ...
BLOCK_TOP = 8            # ... at most this many per block and band


# -- inputs ----------------------------------------------------------------------

def gravity_module():
    path = paths.script("school-gravity.py") if STEP1 == ROOT else os.path.join(STEP1, "tools", "school-trips", "school-gravity.py")
    if not os.path.exists(path):
        sys.exit("school-sim: tools/school-trips/school-gravity.py not found under %s (set SCHOOL_SIM_STEP1_ROOT)" % STEP1)
    sys.dont_write_bytecode = True
    return _load("school_gravity", path)


def tally_targets(high="flat"):
    """Each grade's target shares (car, carpool, walk, bike, transit) and how its car share was found.

    The car share is a curve through the tally's four measured grades (K 54%,
    5th 56%, 6th 47%, 9th 33%): straight lines between them, TK at K's value,
    and grades 10 to 12 held at 9th's 33% (high="flat", the model's: Bryan,
    2026-10-08, "Let's assume 9th grade is similar to 12th.") or continuing the
    6th-to-9th line (high="trend", about 4.7 points a grade), kept only for
    validation.json's one-line range. The other four
    modes split the rest in the proportions of the tally's mix, interpolated
    the same way between measured grades and held at 9th's past it."""
    tg = json.load(open(os.path.join(ROOT, "data", "school-car-share", "inputs.json")))["measured"]["modes_by_tally_grade_2024_25"]
    pts = {0: "K", 5: "5", 6: "6", 9: "9"}

    def row(k):
        r = tg[k]
        return np.array([r["car"], r["carpool"], r["walk"], r["bike"], r["transit"]], dtype=float)
    R = {n: row(k) for n, k in pts.items()}
    xs = sorted(R)
    out, kind = {}, {}
    for g in GRADES:
        n = GNUM[g]
        if g == "TK":
            v, kd = R[0].copy(), "held at K"
        elif n in R:
            v, kd = R[n].copy(), "measured"
        elif n < 9:
            lo = max(x for x in xs if x < n)
            hi = min(x for x in xs if x > n)
            v, kd = R[lo] + (R[hi] - R[lo]) * (n - lo) / float(hi - lo), "interpolated"
        else:
            v = R[9].copy()
            if high == "trend":
                v[0] = R[9][0] + (R[9][0] - R[6][0]) / 3.0 * (n - 9)
                kd = "extrapolated (6th-9th trend)"
            else:
                kd = "held at 9th"
        car = v[0] / 100.0
        rest = v[1:] / v[1:].sum() * (1 - car)
        out[g] = np.r_[car, rest]
        kind[g] = kd
    return out, kind, tg


def schools(grav):
    """[(cds, name, lon, lat, charter, grade enrolment dict, case id or None)], sorted by cds; and what was left out."""
    city = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "enrolment-sf.json")))
    pts = {r["cds"]: r for r in school_points.records() if r.get("lon") and r.get("lat")}
    case = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "enrolment.json")))["schools"]
    doors = {x["id"]: x["door"] for x in json.load(open(os.path.join(grav.ROOT, "data", "school-case", "dropoff.json")))["schools"]}
    case_of = {v["cds"]: k for k, v in case.items() if v.get("cds")}
    out, left = [], {}
    for cds, s in sorted(city["schools"].items()):
        if s["district"] != SFUSD and not s["charter"]:
            continue
        if s["name"] in EXCLUDE:
            left[s["name"]] = EXCLUDE[s["name"]]
            continue
        if sum(s["grades"].values()) <= 0:
            left[s["name"]] = "no students by grade"
            continue
        cid = case_of.get(cds)
        if cid and cid in doors:
            lon, lat = doors[cid]["lon"], doors[cid]["lat"]
        elif cds in pts:
            lon, lat = pts[cds]["lon"], pts[cds]["lat"]
        else:
            left[s["name"]] = "no CDE point"
            continue
        out.append((cds, s["name"], lon, lat, bool(s["charter"]), dict(s["grades"]), cid))
    return out, left, city


BELL = os.path.join(ROOT, "data", "school-hour-crashes", "bell-times.json")
BELL_YEAR = "2025-26"
BELL_SECTION = {"Elementary Schools": "K-5", "Middle Schools": "6-8", "High Schools": "9-12"}


def _hhmm(m):
    return None if m is None else "%02d:%02d" % (m // 60, m % 60)


def bells(grav, sch):
    """Each school's start and end bell per grade range it serves, from SFUSD's 2025-26 start and end times page
    (data/school-hour-crashes/bell-times.json, tools/school-trips/school-hour-crashes.py), matched by name; for a case-study school SFUSD does not list (a charter), the bell its own page gives, recorded in data/school-case/dropoff.json; None otherwise.

    A K-8's page lists its K-5 and 6-8 bells separately. "(Access)" rows are a
    special-education program's bell and are skipped. A name matches when at
    least half its words match and no other row of the same range ties it."""
    import re
    d = json.load(open(BELL))
    rows = []
    for r in d["years"][BELL_YEAR]:
        if "(Access)" in r["name"]:
            continue
        nm = r["name"]
        band = BELL_SECTION.get(r["section"])
        m = re.search(r"\s+(6-8|K-?5)$", nm)
        if m:
            band = "6-8" if m.group(1) == "6-8" else "K-5"
            nm = nm[:m.start()]
        rows.append((grav._tokens(re.sub(r"\b(ES|MS|HS|High School)\b", " ", nm)), band, r))
    case_bell = {x["id"]: x.get("bell") for x in json.load(open(os.path.join(grav.ROOT, "data", "school-case", "dropoff.json")))["schools"]}
    out, missing = {}, []
    for s in sch:
        want = grav._tokens(s[1])
        got = {}
        for band in sorted(set(BAND_OF[g] for g, n in s[5].items() if n > 0 and g in BAND_OF)):
            if is_private(s):
                got[band] = None   # SFUSD's page lists its own schools; a private school's bell is unknown
                missing.append("%s (%s)" % (s[1], band))
                continue
            sc = sorted(((len(want & t) / float(max(len(want), len(t))), i) for i, (t, b, _r) in enumerate(rows) if b == band and t and want),
                        reverse=True)
            if sc and sc[0][0] >= 0.5 and (len(sc) == 1 or sc[1][0] < sc[0][0]):
                r = rows[sc[0][1]][2]
                got[band] = {"start": _hhmm(r["start"]), "end": _hhmm(r["end"]), "earlyDay": r.get("early_day"),
                             "earlyEnd": _hhmm(r.get("early_end")), "sfusdName": r["name"], "source": "sfusd"}
            elif s[6] and (case_bell.get(s[6]) or {}).get("start"):
                cb = case_bell[s[6]]
                got[band] = {"start": cb["start"], "end": cb.get("dismissal"), "earlyDay": "Wed" if cb.get("wednesday_dismissal") else None,
                             "earlyEnd": cb.get("wednesday_dismissal"), "sfusdName": None,
                             "source": "data/school-case/dropoff.json (%s), one bell for the school" % cb.get("source")}
            else:
                got[band] = None
                missing.append("%s (%s)" % (s[1], band))
        out[s[0]] = got
    src = {"url": d["source"][BELL_YEAR], "read": d["read"], "tag": "[primary — read %s]" % d["read"], "year": BELL_YEAR}
    return out, sorted(missing), src


BAND_OF = {g: BAND[LEVEL[g]] for g in GRADES}


# -- trip times on the network ---------------------------------------------------

_W = {}   # the network and joins, shared with forked workers


class DriveIndex(object):
    """A 50 m grid over the edges a car may join, with walknet.Graph's edges_near and snap, on the joined graph."""

    def __init__(self, x, y, eu, ev, ok, walknet):
        self.x, self.y, self.eu, self.ev, self.walknet = x, y, eu, ev, walknet
        C = walknet.CELL_M
        self.cells = {}
        for e in np.flatnonzero(ok).tolist():
            u, v = int(eu[e]), int(ev[e])
            x0, x1 = sorted((x[u], x[v]))
            y0, y1 = sorted((y[u], y[v]))
            for cx in range(int(x0 // C), int(x1 // C) + 1):
                for cy in range(int(y0 // C), int(y1 // C) + 1):
                    self.cells.setdefault((cx, cy), []).append(e)

    def edges_near(self, px, py, r):
        """[(edge, t, metres)] for every joinable drive edge within r metres of (px, py)."""
        C, out, seen = self.walknet.CELL_M, [], set()
        for cx in range(int((px - r) // C), int((px + r) // C) + 1):
            for cy in range(int((py - r) // C), int((py + r) // C) + 1):
                for e in self.cells.get((cx, cy), ()):
                    if e in seen:
                        continue
                    seen.add(e)
                    u, v = self.eu[e], self.ev[e]
                    ax, ay, bx, by = self.x[u], self.y[u], self.x[v], self.y[v]
                    dx, dy = bx - ax, by - ay
                    L2 = dx * dx + dy * dy
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2)) if L2 else 0.0
                    d = math.hypot(ax + t * dx - px, ay + t * dy - py)
                    if d <= r:
                        out.append((e, t, d))
        return out

    def snap(self, lon, lat):
        """walknet.Graph.snap's rule on the drive edges: along a census block's frontage when its outline is
        registered, else the nearest edge and every one within TARGET_SLACK_M of it."""
        wn = self.walknet
        rings = wn.OUTLINES.get((round(lon, 5), round(lat, 5)))
        if rings:
            best = {}
            for ring in rings:
                for px, py in wn.samples(ring):
                    for e, t, d in self.edges_near(px, py, wn.FRONTAGE_SNAP_M):
                        best.setdefault(e, []).append((t, d))
            out = []
            for e, ts in best.items():
                keep = {min(ts, key=lambda a: a[1]), min(ts, key=lambda a: a[0]), max(ts, key=lambda a: a[0])}
                out.extend((e, t, d) for t, d in sorted(keep))
            if out:
                return sorted(out, key=lambda c: (c[2], c[0], c[1]))
        px, py = wn.xy(lon, lat)
        r, cand = wn.CELL_M, []
        while r <= 4000:
            cand = self.edges_near(px, py, r)
            if cand and min(c[2] for c in cand) + wn.TARGET_SLACK_M <= r:
                break
            r *= 2
        if not cand:
            return []
        best = min(c[2] for c in cand)
        return sorted((c for c in cand if c[2] <= best + wn.TARGET_SLACK_M), key=lambda c: (c[2], c[0]))


def _drive_ends(D, L, lon, lat):
    """[(node, connector m, along-edge m, edge)] where a point joins the drive edges."""
    out = []
    for e, t, c in D.snap(lon, lat):
        out += [(int(D.eu[e]), c, t * L[e], e), (int(D.ev[e]), c, (1 - t) * L[e], e)]
    return out


FOOT_OK = {"yes", "designated", "permissive"}


def joined_graph(G, walknet):
    """The walk graph with OpenStreetMap's drivable streets joined in (tools/travel/osm-drive-network.py).

    The walk network leaves out a street whose sidewalks are mapped as their own ways, so Van Ness Avenue survives in
    it only as its busway and footways (Fable review, 2026-10-08). Each drivable way's pieces are matched to the walk
    graph by OSM node id: a piece the walk graph already has becomes drivable, and one it lacks is appended as an edge
    only a car may use. A busway is never drivable, and is walkable only where OSM tags it foot=yes, designated or
    permissive. Returns (x, y, eu, ev, L, hw, walkable, drivable, stats); the first len(G.eu) edges are G's, in order."""
    blob = json.load(open(walknet.CACHE))
    coords = {e["id"]: (e["lon"], e["lat"]) for e in blob["elements"] if e["type"] == "node"}
    # OSM node ids a signalled crossing way touches
    sig_ids = set()
    for w in (e for e in blob["elements"] if e["type"] == "way"):
        t = w.get("tags", {})
        if t.get("crossing") == "traffic_signals" or t.get("crossing:signals") == "yes":
            sig_ids.update(w.get("nodes", ()))
    idx, wtags = {}, []
    for w in (e for e in blob["elements"] if e["type"] == "way"):   # walknet.Graph's own loop, replayed for the ids
        prev = None
        for nd in (n for n in w.get("nodes", ()) if n in coords):
            if nd not in idx:
                idx[nd] = len(idx)
            i = idx[nd]
            if prev is not None and prev != i:
                wtags.append(w.get("tags", {}))
            prev = i
    del blob, coords
    n0, m0 = len(G.x), len(G.eu)
    assert len(idx) == n0 and len(wtags) == m0, "walk graph replay: %d/%d nodes, %d/%d edges" % (len(idx), n0, len(wtags), m0)
    x, y = list(G.x), list(G.y)
    eu, ev, L, hw = list(G.eu), list(G.ev), list(G.elen), list(G.ehw)
    walkable = [not (t.get("highway") == "busway" and t.get("foot") not in FOOT_OK) for t in wtags]
    drivable = [False] * m0
    pair = {}
    for e in range(m0):
        pair.setdefault((min(eu[e], ev[e]), max(eu[e], ev[e])), e)
    dblob = json.load(open(DRIVE_CACHE))
    dco = {e["id"]: (e["lon"], e["lat"]) for e in dblob["elements"] if e["type"] == "node"}
    shared = added = 0
    busy_ids, busy_edges = set(), set()
    for w in (e for e in dblob["elements"] if e["type"] == "way"):
        t = w.get("tags", {})
        h = t.get("highway")
        if h not in DRIVE_HW:
            continue
        busy = _busy_way(t)
        if busy:
            busy_ids.update(w.get("nodes", ()))
        prev = None
        for nd in (n for n in w.get("nodes", ()) if n in dco):
            if nd not in idx:
                idx[nd] = len(x)
                px, py = walknet.xy(*dco[nd])
                x.append(px)
                y.append(py)
            i = idx[nd]
            if prev is not None and prev != i:
                k = (min(prev, i), max(prev, i))
                e = pair.get(k)
                if e is None:
                    e = len(eu)
                    pair[k] = e
                    eu.append(prev)
                    ev.append(i)
                    L.append(math.hypot(x[i] - x[prev], y[i] - y[prev]))
                    hw.append(h)
                    walkable.append(False)
                    drivable.append(True)
                    added += 1
                elif not drivable[e]:
                    drivable[e] = hw[e] != "busway"
                    shared += drivable[e]
                if busy:
                    busy_edges.add(e)
            prev = i
    # the busy-crossing rule's masks: busy edges, and busy nodes with no signal at or within XING_SIGNAL_M of them
    from scipy.spatial import cKDTree
    xa, ya = np.asarray(x), np.asarray(y)
    xedge = np.zeros(len(eu), dtype=bool)
    xedge[list(busy_edges)] = True
    busy_n = np.array(sorted(idx[i] for i in busy_ids if i in idx), dtype=np.int64)
    sig_n = np.array(sorted(idx[i] for i in sig_ids if i in idx), dtype=np.int64)
    xnode = np.zeros(len(x), dtype=bool)
    if len(busy_n):
        xnode[busy_n] = True
        if len(sig_n):
            d, _i = cKDTree(np.c_[xa[sig_n], ya[sig_n]]).query(np.c_[xa[busy_n], ya[busy_n]], distance_upper_bound=XING_SIGNAL_M)
            xnode[busy_n[np.isfinite(d)]] = False
    eua, eva = np.asarray(eu, dtype=np.int64), np.asarray(ev, dtype=np.int64)
    xapp = ~xedge & (xnode[eua] | xnode[eva])
    stats = {"driveOsmBase": dblob.get("osm3s", {}).get("timestamp_osm_base"), "walkEdges": m0, "driveEdgesShared": shared,
             "driveOnlyEdges": added, "nodesAdded": len(x) - n0, "notWalkable": int(m0 - sum(walkable[:m0])),
             "busyEdges": int(xedge.sum()), "busyNodes": int(len(busy_n)), "busyNodesUnsignalled": int(xnode.sum()),
             "signalNodes": int(len(sig_n)), "approachEdges": int(xapp.sum())}
    return (xa, ya, eua, eva, np.asarray(L, dtype=float),
            hw, np.asarray(walkable, dtype=bool), np.asarray(drivable, dtype=bool), stats, xnode, xedge, xapp)


def _busy_way(tags):
    """Whether an OSM way is a busy street: XING_LANES lanes or more, or posted at XING_MPH or more."""
    def num(v):
        try:
            return float(str(v).split(";")[0].split()[0])
        except (ValueError, IndexError):
            return None
    lanes, mph = num(tags.get("lanes")), num(tags.get("maxspeed"))
    if lanes is not None and lanes >= XING_LANES:
        return True
    return mph is not None and mph >= XING_MPH and "mph" in str(tags.get("maxspeed"))


def _broken(pred, lookup, join_node=None, join_edge=None):
    """Per node: whether its tree route crosses a busy street at an unsignalled node (through it on two edges off the
    busy street). With join_node and join_edge (per block), also the crossing a block's own join makes at its node."""
    n = _W["n"]
    key, ref = lookup
    xnode, xedge = _W["xnode"], _W["xedge"]
    reach = np.flatnonzero(pred[:n] >= 0)
    p = pred[reach].astype(np.int64)
    r = ref[np.searchsorted(key, p * (n + 1) + reach)]
    pe = np.full(n, -1, dtype=np.int64)
    pe[reach] = r
    par = np.arange(n)
    inner = p < n
    par[reach[inner]] = p[inner]
    v = reach[inner]
    pv = par[v]
    ep = pe[pv]
    cross = xnode[pv] & ~xedge[pe[v]] & (ep >= 0) & ~xedge[np.maximum(ep, 0)]
    brk = np.zeros(n, dtype=bool)
    brk[v] = cross
    anc = par
    for _ in range(40):
        nb = brk | brk[anc]
        na = anc[anc]
        if np.array_equal(nb, brk) and np.array_equal(na, anc):
            break
        brk, anc = nb, na
    if join_node is None:
        return brk
    jp = pe[join_node]
    jx = xnode[join_node] & ~xedge[join_edge] & (jp >= 0) & ~xedge[np.maximum(jp, 0)]
    return brk[join_node] | jx


def _flat(ends_list):
    node, c, al, e, own = [], [], [], [], []
    for i, ends in enumerate(ends_list):
        for nd, cc, aa, ee in ends:
            node.append(nd)
            c.append(cc)
            al.append(aa)
            e.append(ee)
            own.append(i)
    return {"node": np.array(node, dtype=np.int64), "c": np.array(c), "al": np.array(al),
            "e": np.array(e, dtype=np.int64), "own": np.array(own, dtype=np.int64), "n": len(ends_list)}


def _runs(G, L, safe):
    """Each edge's connected run of safe edges, in metres (0 off the network)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(G.x)
    eu, ev = np.asarray(G.eu)[safe], np.asarray(G.ev)[safe]
    M = csr_matrix((np.ones(len(eu)), (eu, ev)), shape=(n, n))
    _k, lab = connected_components(M, directed=False)
    tot = np.bincount(lab[eu], weights=L[safe], minlength=n)
    out = np.zeros(len(L))
    out[safe] = tot[lab[eu]]
    return out


def top_blocks(grav, sch):
    """{cds: [(block id, line)]}: step 1's ranked bikeway blocks for a case-study school (site/data/school-case/<id>.json,
    topBlocks.brp, best first), the twenty the page offers."""
    out = {}
    for s in sch:
        if not s[6]:
            continue
        p = os.path.join(grav.ROOT, "site", "data", "school-case", "%s.json" % s[6])
        if not os.path.exists(p):
            continue
        tb = (json.load(open(p)).get("topBlocks") or {}).get("brp") or []
        out[s[0]] = [(b["id"], b["line"]) for b in tb[:max(BLOCK_NS)]]
    return out


def network(blks, tops=None):
    """The walk network, its all-ages edges, and every block's joins, for trips()."""
    stt = _load("school_travel_time", paths.script("school-travel-time.py"))
    walknet = stt.walknet
    net = stt.Net(cache=True)
    G = net.G
    today, _plan, _meta = stt.all_ages_lines(brp_rule=True)
    line_edges, _weak = stt.edges_of(net, today, cache=True)
    n_e = len(G.eu)
    safe = np.zeros(n_e, dtype=bool)
    for key, _pts in today:
        for e in line_edges.get(key, ()):
            safe[e] = True
    safe_built = safe.copy()
    # The 2019 network, for the back-cast (V2): every block whose 2019 class in the bikeway history is all-ages
    # (Class I or IV, or a Slow Street, none of which existed yet), matched as today's lines are.
    sg_hist = json.load(open(os.path.join(ROOT, "site", "data", "bike-history", "segments.json")))
    i19 = sg_hist["years"].index(BACKCAST_YEAR)
    y19 = [(s["key"], s["pts"]) for s in sg_hist["segments"] if s["y"][i19] in ("1", "4", "S") and len(s["pts"]) >= 2]
    safe_y19 = np.zeros(n_e, dtype=bool)
    for es in stt.edges_of(net, y19)[0].values():
        for e in es:
            safe_y19[e] = True
    # Every upcoming SFMTA bikeway is in the baseline at no cost (Bryan, 2026-10-09), as in school-segments.py.
    planned = json.load(open(os.path.join(ROOT, "site", "data", "bike-history", "planned.json")))
    pl_lines = [("pl:%s" % b["cnn"], b["pts"]) for pr in planned["projects"] for b in pr["blocks"] if len(b.get("pts") or []) >= 2]
    for es in stt.edges_of(net, pl_lines)[0].values():
        for e in es:
            safe[e] = True
    x, y, eu, ev, L, hw, walkable, drivable, jstats, xnode, xedge, xapp = joined_graph(G, walknet)
    n_all = len(x)
    pad = np.zeros(len(L) - n_e, dtype=bool)
    safe, safe_built, safe_y19 = np.r_[safe, pad], np.r_[safe_built, pad], np.r_[safe_y19, pad]
    steps = np.array([h == "steps" for h in hw])
    # A car trip starts and ends on the drivable grid's largest connected piece. A school's own driveway or a
    # block's private lane is often joined to the street only by footways, and seeding there left the drive
    # unable to reach any block, so the car fell back to the walk distance (21 schools, Fable review 2026-10-08).
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    _nc, lab = connected_components(coo_matrix((np.ones(int(drivable.sum())), (eu[drivable], ev[drivable])), shape=(n_all, n_all)),
                                    directed=False)
    main = np.bincount(lab[eu[drivable]]).argmax()
    drive_seed = drivable & (lab[eu] == main)
    D = DriveIndex(x, y, eu, ev, drive_seed, walknet)
    # Walk and bike joins on a walkable edge (a busway is not one); the car's along the drive edges.
    ends = []
    for b in blks:
        en = net.ends(b["lon"], b["lat"])
        ends.append([q for q in en if walkable[q[3]]] or en)
    car_ends = [_drive_ends(D, L, b["lon"], b["lat"]) for b in blks]
    run_ok = np.r_[_runs(G, np.asarray(G.elen, dtype=float), safe[:n_e]) >= CONNECT_MIN_MI * MI, np.zeros(len(L) - n_e, dtype=bool)]
    _W.update(n=n_all, eu=eu, ev=ev, L=L, safe=safe, walkable=walkable, Lw=np.where(walkable, L, np.inf), hw=np.asarray(hw),
              steps=steps, drivable=drivable, drive_seed=drive_seed, D=D, flat=_flat(ends), car_flat=_flat(car_ends), net=net, G=G,
              walknet=walknet, bxy=np.array([walknet.xy(b["lon"], b["lat"]) for b in blks]).reshape(-1, 2), x=x, y=y,
              joinable=np.r_[np.asarray(G.joinable, dtype=bool), np.ones(len(L) - n_e, dtype=bool)] & (walkable | drive_seed),
              zone_hw=np.array([h in ZONE_HW for h in hw]) & walkable, run_ok=run_ok, joined=jstats,
              xnode=xnode, xedge=xedge, xapp=xapp, xpen=np.where(xapp, XING_PEN_M, 0.0),
              safe_built=safe_built, safe_y2019=safe_y19, rise=edge_rise(x, y, eu, ev, L, walknet))
    # The ranked citywide segments' walk edges at each milestone, matched as the bikeway lines are.
    _W["seg_edges"] = {}
    if os.path.exists(SEGMENTS) and not IGNORE_SEGMENTS:
        sg = json.load(open(SEGMENTS))
        by_id = {c["id"]: c for c in sg["chunks"]}
        for bk in sg["budgets"]:
            seg_lines = [("%s:%d" % (cid, i), pts) for cid in bk["chunks"] for i, pts in enumerate(by_id[cid]["pts"])]
            es = stt.edges_of(net, seg_lines)[0] if seg_lines else {}
            _W["seg_edges"][bk["budgetM"]] = np.array(sorted(set().union(*es.values())) if es else [], dtype=np.int64)
    # Each ranked block's walk edges, matched as the bikeway lines are.
    lines = [(k, pts) for v in (tops or {}).values() for k, pts in v]
    be = stt.edges_of(net, lines)[0] if lines else {}
    _W["top_edges"] = {cds: [np.array(sorted(be.get(k, ())), dtype=np.int64) for k, _p in v] for cds, v in (tops or {}).items()}
    return dict({"safeEdges": int(safe.sum()), "edges": len(L), "nodes": n_all, "safeEdgesBuilt": int(safe_built.sum()),
                 "safeEdges2019": int(safe_y19.sum()), "riseKnownPct": round(100 * float(np.isfinite(_W["rise_raw"]).mean()), 2)}, **jstats)


# The bike curve's gradient is the route's summed rise over its length: each walk-network node's elevation from the
# USGS 3DEP tiles tools/school-trips/street-grades.py caches (sources/usgs-3dep-elevation.md), and each edge's rise the
# absolute difference of its ends, capped at RISE_CAP_X of its length so a bridge or stair over a drop between
# two DEM cells doesn't read as a cliff [inference -- mine]. An edge with an end off the tiles rises 0.
DEM_GLOB = os.path.join(ROOT, ".cache", "street-grades", "dem_*.tif")
RISE_CAP_X = 0.35
# V2's base year: the earliest tally the plan compares against (2019-20), on the network of that year.
BACKCAST_YEAR = 2019


def edge_rise(x, y, eu, ev, L, wn):
    """(edges) metres of rise per edge, from node elevations sampled off the cached DEM tiles."""
    import glob as _glob
    from pyproj import Transformer
    sg = _load("street_grades", paths.script("street-grades.py"))
    paths = sorted(_glob.glob(DEM_GLOB))
    assert paths, "no DEM tiles in %s: run tools/school-trips/street-grades.py" % DEM_GLOB
    lon = np.degrees(np.asarray(x) / (math.cos(wn.LAT0) * wn.EARTH))
    lat = np.degrees(np.asarray(y) / wn.EARTH)
    ux, uy = Transformer.from_crs(4326, 26910, always_xy=True).transform(lon, lat)
    z = np.full(len(lon), np.nan)
    for pth in paths:
        need = np.isnan(z)
        if not need.any():
            break
        z[need] = sg.Tile(pth).sample(np.asarray(ux)[need], np.asarray(uy)[need])
    raw = np.abs(z[ev] - z[eu])
    _W["rise_raw"] = raw
    return np.where(np.isfinite(raw), np.minimum(raw, RISE_CAP_X * np.asarray(L)), 0.0)


def _dijkstra(w_edge, seeds, seed_cost):
    """One-to-all from a virtual source joined to the seeds: (dist, pred, kept-entry lookup)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    n, eu, ev = _W["n"], _W["eu"], _W["ev"]
    ok = np.isfinite(w_edge)
    eid = np.flatnonzero(ok)
    rows = np.concatenate([eu[ok], ev[ok], np.full(len(seeds), n)])
    cols = np.concatenate([ev[ok], eu[ok], np.asarray(seeds, dtype=np.int64)])
    data = np.concatenate([w_edge[ok], w_edge[ok], np.asarray(seed_cost, dtype=float)]) + 1e-6
    ref = np.concatenate([eid, eid, -1 - np.arange(len(seeds))])   # edge id, or -1-seed index
    key = rows * (n + 1) + cols
    o = np.lexsort((data, key))
    key, rows, cols, data, ref = key[o], rows[o], cols[o], data[o], ref[o]
    first = np.r_[True, key[1:] != key[:-1]]
    key, rows, cols, data, ref = key[first], rows[first], cols[first], data[first], ref[first]
    M = csr_matrix((data, (rows, cols)), shape=(n + 1, n + 1))
    dist, pred = dijkstra(M, directed=True, indices=n, return_predecessors=True)
    return dist, pred, (key, ref)


def _tree(dist, pred, lookup, seed_len, seed_run, seed_max, safe):
    """Along each node's tree path from the door: true length, the off-network run ending there, the longest run.
    Pointer doubling over the shortest-path tree (school-segments.py's tree_fast without its excess), so no
    node-by-node loop; _tree_slow is the node-by-node reference, kept to check it against."""
    n, L = _W["n"], _W["L"]
    key, ref = lookup
    reach = np.flatnonzero(np.isfinite(dist[:n]))
    ln_o, run_o, mx_o = np.full(n, np.inf), np.zeros(n), np.zeros(n)
    if not len(reach):
        return ln_o, run_o, mx_o
    p = pred[reach].astype(np.int64)
    r = ref[np.searchsorted(key, p * (n + 1) + reach)]
    idx = np.full(n, -1, dtype=np.int64)
    idx[reach] = np.arange(len(reach))
    m = len(reach)
    seed = r < 0
    anc = np.where(seed, np.arange(m), idx[np.where(seed, 0, p)])
    le = np.where(seed, 0.0, L[np.maximum(r, 0)])
    un = np.where(seed, True, ~safe[np.maximum(r, 0)])
    tot, allu = le.copy(), un.copy()
    top = np.where(un, le, 0.0)
    bot, mx = top.copy(), top.copy()
    for _ in range(64):
        if np.all(seed[anc]):
            break
        Ut, Ua, Utop, Ubot, Umx = tot[anc], allu[anc], top[anc], bot[anc], mx[anc]
        nbot = np.where(allu, tot + Ubot, bot)
        ntop = np.where(Ua, Ut + top, Utop)
        nmx = np.maximum(np.maximum(Umx, mx), Ubot + top)
        tot, allu, top, bot, mx = Ut + tot, Ua & allu, ntop, nbot, nmx
        anc = anc[anc]
    assert np.all(seed[anc]), "route tree deeper than 2^64"
    s = -1 - r[anc]
    sl, sr, sm = (np.asarray(x, dtype=float)[s] for x in (seed_len, seed_run, seed_max))
    ln_o[reach] = sl + tot
    run_o[reach] = np.where(allu, sr + tot, bot)
    mx_o[reach] = np.maximum(np.maximum(sm, mx), sr + top)
    return ln_o, run_o, mx_o


def _tree_slow(dist, pred, lookup, seed_len, seed_run, seed_max, safe):
    """_tree node by node in distance order, the reference for the selftest."""
    n = _W["n"]
    L = _W["L"]
    key, ref = lookup
    reach = np.flatnonzero(np.isfinite(dist[:n]))
    order = reach[np.argsort(dist[reach], kind="stable")]
    p = pred[order]
    k = np.searchsorted(key, p.astype(np.int64) * (n + 1) + order)
    r = ref[k]
    ln = np.full(n, np.inf)
    run = np.zeros(n)
    mx = np.zeros(n)
    Lr = np.where(r >= 0, L[np.maximum(r, 0)], 0.0)
    Ur = np.where(r >= 0, ~safe[np.maximum(r, 0)], False)
    ln_l, run_l, mx_l = ln.tolist(), run.tolist(), mx.tolist()
    for v, pv, rv, le, un in zip(order.tolist(), p.tolist(), r.tolist(), Lr.tolist(), Ur.tolist()):
        if rv < 0:
            s = -1 - rv
            ln_l[v], run_l[v], mx_l[v] = seed_len[s], seed_run[s], seed_max[s]
            continue
        ln_l[v] = ln_l[pv] + le
        rr = run_l[pv] + le if un else 0.0
        run_l[v] = rr
        m = mx_l[pv]
        mx_l[v] = rr if rr > m else m
    return np.array(ln_l), np.array(run_l), np.array(mx_l)


def _tree_sums(dist, pred, lookup, edge_vals, seed_vals):
    """(nodes x K) sums of per-edge values (edges x K) along each node's tree path from the door, starting from its
    seed's values (seeds x K); 0 where unreached. Pointer doubling over the tree, so no node-by-node loop."""
    n = _W["n"]
    key, ref = lookup
    out = np.zeros((n, edge_vals.shape[1]))
    reach = np.flatnonzero(np.isfinite(dist[:n]))
    if not len(reach):
        return out
    p = pred[reach].astype(np.int64)
    r = ref[np.searchsorted(key, p * (n + 1) + reach)]
    idx = np.full(n, -1, dtype=np.int64)
    idx[reach] = np.arange(len(reach))
    seed = r < 0
    m = len(reach)
    anc = np.where(seed, np.arange(m), idx[np.where(seed, 0, p)])
    acc = np.where(seed[:, None], np.asarray(seed_vals, dtype=float)[np.where(seed, -1 - r, 0)], edge_vals[np.maximum(r, 0)])
    done = seed.copy()
    for _ in range(64):
        if done.all():
            break
        a = anc
        acc = np.where(done[:, None], acc, acc + acc[a])
        done = done | done[a]
        anc = np.where(done, anc, anc[a])
    assert done.all(), "route tree deeper than 2^64"
    out[reach] = acc
    return out


def _block_pick(F, node_cost, w_end):
    """Each block's least-cost join: (index into F or -1)."""
    k = node_cost[F["node"]] + w_end
    o = np.lexsort((k, F["own"]))
    own = F["own"][o]
    first = np.flatnonzero(np.r_[True, own[1:] != own[:-1]])
    idx = o[first]
    out = np.full(F["n"], -1, dtype=np.int64)
    good = np.isfinite(k[idx])
    out[own[first][good]] = idx[good]
    return out


def _route_off(dist, pred, lk, bd, un_e, F, pi, nd, ue):
    """Per block, the metres of its route off the all-ages network: every off-network stretch between home and the door
    summed, the door's and the block's joins included (a join is never on the network). The total gap that Bryan's
    rule reads (2026-10-21: "total gap of 1000 feet or less between home and school")."""
    L = _W["L"]
    sv = [[d[1] + (d[2] if un_e[d[3]] else 0.0)] for d in bd]
    S = _tree_sums(dist, pred, lk, np.where(un_e, L, 0.0)[:, None], sv)
    return S[nd, 0] + F["c"][pi] + np.where(ue[pi], F["al"][pi], 0.0)


def _bike(safe, door, walk, extra=False):
    """Per block: bike route metres and total gap (m, _route_off) with `safe` as the all-ages network. With extra, also the
    chosen route's metres on the network and its summed rise (m, from the DEM's node elevations; NaN where no bike
    route), the inputs to the cases' on-network share and the bike curve's routed gradient."""
    L, steps, F = _W["L"], _W["steps"], _W["flat"]
    bd = [d for d in door if not steps[d[3]]] or door
    un_e = ~safe
    cand = []
    for k in GAP_K:
        w = np.where(steps, np.inf, _W["Lw"] * (1 + k * un_e) + k * _W["xpen"])
        s_len = [d[1] + d[2] for d in bd]
        s_un = [bool(un_e[d[3]]) for d in bd]
        s_cost = [d[1] * (1 + k) + d[2] * (1 + k * u) for d, u in zip(bd, s_un)]
        dist, pred, lk = _dijkstra(w, [d[0] for d in bd], s_cost)
        ln, run, mx = _tree(dist, pred, lk, s_len, [sl if u else 0.0 for sl, u in zip(s_len, s_un)],
                            [sl if u else d[1] for sl, u, d in zip(s_len, s_un, bd)], safe)
        ue = un_e[F["e"]] | steps[F["e"]]
        w_end = F["c"] * (1 + k) + F["al"] * (1 + k * ue)
        pick = _block_pick(F, dist[:-1], w_end)
        pi = np.maximum(pick, 0)
        nd = F["node"][pi]
        m = np.where(pick >= 0, ln[nd] + F["c"][pi] + F["al"][pi], np.inf)
        off = _route_off(dist, pred, lk, bd, un_e, F, pi, nd, ue)
        g = np.where(pick >= 0, off, np.inf)
        g = np.where(_broken(pred, lk, nd, F["e"][pi]), g + BREAK_FT * FT, g)
        if extra:
            rise = _W["rise"]
            sv_ = [[d[2] / max(L[d[3]], 1e-9) * rise[d[3]]] for d in bd]
            S_ = _tree_sums(dist, pred, lk, rise[:, None], sv_)
            fe = F["e"][pi]
            rs = S_[nd, 0] + F["al"][pi] / np.maximum(L[fe], 1e-9) * rise[fe]
            cand.append((m, g, np.maximum(m - off, 0.0), rs))
        else:
            cand.append((m, g))
    m0 = cand[0][0]
    best_m, best_g = m0.copy(), cand[0][1].copy()
    if extra:
        best_on, best_r = cand[0][2].copy(), cand[0][3].copy()
    for cd in cand[1:]:
        m, g = cd[0], cd[1]
        with np.errstate(invalid="ignore"):
            ok = np.isfinite(m) & (m <= DETOUR * m0 + 1e-6) & ((g < best_g - 1e-6) | ((np.abs(g - best_g) <= 1e-6) & (m < best_m)))
        best_m = np.where(ok, m, best_m)
        best_g = np.where(ok, g, best_g)
        if extra:
            best_on = np.where(ok, cd[2], best_on)
            best_r = np.where(ok, cd[3], best_r)
    nobike = ~np.isfinite(best_m)
    if extra:
        return (np.where(nobike, walk, best_m), np.where(nobike, walk, best_g), int(nobike.sum()),
                np.where(nobike, 0.0, best_on), np.where(nobike, np.nan, best_r))
    return np.where(nobike, walk, best_m), np.where(nobike, walk, best_g), int(nobike.sum())


GAP_TRACE_SCHOOLS, GAP_TRACE_BLOCKS = 3, 150   # the total-gap trace check's sample: schools, and blocks at each


def gap_trace(sch, safe=None, seed=0):
    """The total gap recomputed piece by piece for a sample of blocks: at GAP_TRACE_SCHOOLS schools, for each search
    in GAP_K, GAP_TRACE_BLOCKS blocks' routes walked node by node from the block's join back to the door, adding every
    edge off the all-ages network, the door's join and the block's own join, against _route_off's pointer-doubling sum.
    Returns {"blocks", "maxDiffFt", "meanGapFt"}; run on today's network unless safe is given."""
    rng = np.random.default_rng(seed)
    L, steps, F, n = _W["L"], _W["steps"], _W["flat"], _W["n"]
    safe = _W["safe"] if safe is None else safe
    un_e = ~safe
    diffs, gaps = [], []
    picks = rng.choice(len(sch), size=min(GAP_TRACE_SCHOOLS, len(sch)), replace=False)
    for j in sorted(int(x) for x in picks):
        door = _W["net"].ends(sch[j][2], sch[j][3])
        door = [d for d in door if _W["walkable"][d[3]]] or door
        bd = [d for d in door if not steps[d[3]]] or door
        for k in GAP_K:
            w = np.where(steps, np.inf, _W["Lw"] * (1 + k * un_e) + k * _W["xpen"])
            s_cost = [d[1] * (1 + k) + d[2] * (1 + k * bool(un_e[d[3]])) for d in bd]
            dist, pred, lk = _dijkstra(w, [d[0] for d in bd], s_cost)
            key, ref = lk
            ue = un_e[F["e"]] | steps[F["e"]]
            pick = _block_pick(F, dist[:-1], F["c"] * (1 + k) + F["al"] * (1 + k * ue))
            pi = np.maximum(pick, 0)
            nd = F["node"][pi]
            fast = _route_off(dist, pred, lk, bd, un_e, F, pi, nd, ue)
            have = np.flatnonzero(pick >= 0)
            for b in rng.choice(have, size=min(GAP_TRACE_BLOCKS, len(have)), replace=False):
                tot, v = float(F["c"][pi[b]] + (F["al"][pi[b]] if ue[pi[b]] else 0.0)), int(nd[b])
                for _ in range(n + 1):
                    r = int(ref[np.searchsorted(key, int(pred[v]) * (n + 1) + v)])
                    if r < 0:
                        d = bd[-1 - r]
                        tot += d[1] + (d[2] if un_e[d[3]] else 0.0)
                        break
                    tot += float(L[r]) if un_e[r] else 0.0
                    v = int(pred[v])
                diffs.append(abs(tot - float(fast[b])) / FT)
                gaps.append(tot / FT)
    return {"blocks": len(diffs), "maxDiffFt": round(max(diffs), 4) if diffs else None,
            "meanGapFt": round(float(np.mean(gaps)), 1) if gaps else None}


def trips_one(args):
    """One school's per-block walk metres, car minutes, and bike metres and total gap (feet) on each network variant."""
    lon, lat, cds = args
    G, net, walknet = _W["G"], _W["net"], _W["walknet"]
    L, safe, drivable = _W["L"], _W["safe"], _W["drivable"]
    F, CF = _W["flat"], _W["car_flat"]
    n = _W["n"]
    door = net.ends(lon, lat)
    door = [d for d in door if _W["walkable"][d[3]]] or door
    # walk
    sn = [d[0] for d in door]
    wdist, wpred, wlk = _dijkstra(_W["Lw"].copy(), sn, [d[1] + d[2] for d in door])
    end_w = F["c"] + F["al"]
    pick = _block_pick(F, wdist, end_w)
    walk = np.where(pick >= 0, wdist[F["node"][np.maximum(pick, 0)]] + end_w[np.maximum(pick, 0)], np.inf)
    # A block the door's network never reaches (an island of the walk network) takes the straight line
    # times FALLBACK_DETOUR, counted in noWalkPairs.
    nowalk = ~np.isfinite(walk)
    dx, dy = walknet.xy(lon, lat)
    straight = np.hypot(_W["bxy"][:, 0] - dx, _W["bxy"][:, 1] - dy)
    walk = np.where(nowalk, straight * FALLBACK_DETOUR, walk)
    # car
    dd = _drive_ends(_W["D"], L, lon, lat)
    wc = np.where(drivable, L, np.inf)
    dist, _p, _l = _dijkstra(wc, [d[0] for d in dd], [d[1] + d[2] for d in dd])
    end_c = CF["c"] + CF["al"]
    pick = _block_pick(CF, dist, end_c)
    car_m = np.where(pick >= 0, dist[CF["node"][np.maximum(pick, 0)]] + end_c[np.maximum(pick, 0)], np.inf)
    car_fallback = int((~np.isfinite(car_m)).sum())
    car_m = np.where(np.isfinite(car_m), car_m, walk)
    car_raw = car_m
    car_min = np.maximum(car_m, walk) / MI / CAR_MPH * 60 + CAR_FIXED_MIN
    # Calm Streets: every residential street edge whose midpoint is within ZONE_FT of the school's grounds,
    # measured from their edge as state law measures a school zone, calmed and so counted safe.
    eu, ev = _W["eu"], _W["ev"]
    mx_, my_ = (_W["x"][eu] + _W["x"][ev]) / 2, (_W["y"][eu] + _W["y"][ev]) / 2
    zone = _W["zone_hw"] & (grounds_ft(lon, lat, mx_, my_, ZONE_FT) <= ZONE_FT) & ~safe
    # Protected School Connector: SFMTA's School Connector, "protected where needed" (step 1's kf): the
    # shortest walk from the door to the nearest street of a safe run at least CONNECT_MIN_MI long, made safe.
    conn = np.zeros(len(L), dtype=bool)
    tgt = _W["run_ok"]
    nodes = np.unique(np.r_[eu[tgt], ev[tgt]])
    on_network = False
    if len(nodes):
        t = int(nodes[np.argmin(wdist[nodes])])
        if np.isfinite(wdist[t]):
            key, ref = wlk
            v = t
            while v != n and v >= 0:
                pv = int(wpred[v])
                if pv < 0:
                    break
                r = ref[np.searchsorted(key, pv * (n + 1) + v)]
                if r >= 0:
                    conn[r] = True
                v = pv
            conn &= ~safe
            on_network = not conn.any()
    out = {"walk": walk.astype(np.float32), "car": car_min.astype(np.float32), "carm": car_raw.astype(np.float32)}
    # The School Street block: walk edges whose midpoint lies within SS_NEAR_FT of the block's centreline.
    ss = np.zeros(len(L), dtype=bool)
    for line in _W.get("ss_lines", {}).get(cds, []):
        xy = np.array([walknet.xy(a, b) for a, b in line])
        for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
            vx, vy = x1 - x0, y1 - y0
            t = np.clip(((mx_ - x0) * vx + (my_ - y0) * vy) / max(vx * vx + vy * vy, 1e-9), 0, 1)
            ss |= np.hypot(mx_ - (x0 + t * vx), my_ - (y0 + t * vy)) <= SS_NEAR_FT * FT
    ss &= _W["walkable"] & ~safe
    nob = 0
    for name, extra in (("today", None), ("calm", zone), ("connector", conn), ("both", zone | conn)):
        sf = safe if extra is None else (safe | extra)
        bm, bg, nb_, on, rs = _bike(sf, door, walk, extra=True)
        out["bike_" + name] = bm.astype(np.float32)
        out["gap_" + name] = (bg / FT).astype(np.float32)
        out["on_" + name] = on.astype(np.float32)
        if name == "today":
            out["rise_today"] = rs.astype(np.float32)
        nob += nb_
    # The back-cast's two networks (V2): today's built one without the upcoming bikeways, and 2019's.
    for name in BACKCAST_VARIANTS:
        bm, bg, _nb, on, _rs = _bike(_W["safe_" + name], door, walk, extra=True)
        out["bike_" + name] = bm.astype(np.float32)
        out["gap_" + name] = (bg / FT).astype(np.float32)
        out["on_" + name] = on.astype(np.float32)
    for m in SEG_B:
        add = _W.get("seg_edges", {}).get(m)
        for name, extra in (("today", None), ("calm", zone), ("connector", conn), ("both", zone | conn)):
            if add is None or not len(add):
                # no stretches at this budget: the same network as the base variant, so the same answer
                for k in ("bike", "gap", "on"):
                    out["%s_%s_b%d" % (k, name, m)] = out["%s_%s" % (k, name)]
                continue
            sf = (safe if extra is None else (safe | extra)).copy()
            sf[add] = True
            bm, bg, _nb, on, _rs = _bike(sf, door, walk, extra=True)
            out["bike_%s_b%d" % (name, m)] = bm.astype(np.float32)
            out["gap_%s_b%d" % (name, m)] = (bg / FT).astype(np.float32)
            out["on_%s_b%d" % (name, m)] = on.astype(np.float32)
    # The same networks with the School Street block safe; where there is none, they equal the networks without.
    for v in ALL_VARIANTS:
        if not ss.any():
            out["bike_%s_ss" % v], out["gap_%s_ss" % v] = out["bike_" + v], out["gap_" + v]
            continue
        name, _, m = v.partition("_b")
        extra = {"today": None, "calm": zone, "connector": conn, "both": zone | conn}[name]
        add = _W.get("seg_edges", {}).get(int(m)) if m else None
        if m and (add is None or not len(add)):
            out["bike_%s_ss" % v], out["gap_%s_ss" % v] = out["bike_%s_ss" % name], out["gap_%s_ss" % name]
            continue
        sf = (safe if extra is None else (safe | extra)) | ss
        if add is not None and len(add):
            sf[add] = True
        bm, bg, _nb = _bike(sf, door, walk)
        out["bike_%s_ss" % v] = bm.astype(np.float32)
        out["gap_%s_ss" % v] = (bg / FT).astype(np.float32)
    info = {"schoolStreetFt": round(float(L[ss].sum() / FT)), "calmFt": round(float(L[zone].sum() / FT)), "connectorFt": round(float(L[conn].sum() / FT)), "connectorOnNetwork": on_network}
    # Step 1's ranked bikeway blocks, the first n added on every toggle combination's network.
    xb = {}
    tops = _W.get("top_edges", {}).get(cds)
    if tops:
        info["topBlocks"] = len(tops)
        for nb_n in BLOCK_NS[1:]:
            add = np.zeros(len(L), dtype=bool)
            for es in tops[:nb_n]:
                add[es] = True
            for name, extra in (("today", None), ("calm", zone), ("connector", conn), ("both", zone | conn)):
                sf = safe | add if extra is None else (safe | extra | add)
                bm, bg, _nb, on, _rs = _bike(sf, door, walk, extra=True)
                xb["%s_b%d" % (name, nb_n)] = (bm.astype(np.float32), (bg / FT).astype(np.float32), on.astype(np.float32))
    out["_xb"] = xb
    return out, info, car_fallback, nob, int(nowalk.sum())


def _sha_files(h, paths):
    for p in paths:
        h.update(p.encode())
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)


def _trip_job(args):
    j, lon, lat, cds = args
    return j, trips_one((lon, lat, cds))


def trips(blks, sch, workers, tops):
    """Dense (blocks x schools) walk metres, car minutes, bike metres, gap feet.

    Cached per school in .cache/school-sim/trips/, keyed by a hash over the
    shared inputs (this section's code, the walk network, the bikeway network,
    the blocks) and the school's own (its door and its ranked bikeway blocks),
    so a rerun after step 1 re-ranks one school's blocks recomputes that school
    alone. Each school's file is written as soon as it is done, so an
    interrupted run resumes where it stopped."""
    h = hashlib.sha256()
    _sha_files(h, [school_grounds.PATH])
    src = open(os.path.abspath(__file__)).read()
    h.update(src[src.index("# -- trip times on"):src.index("def minutes(")].encode())
    # The constants trips_one reads that are set above this section, so changing one recomputes the times.
    h.update(json.dumps([GAP_RULE, CAR_MPH, CAR_FIXED_MIN, DETOUR, FALLBACK_DETOUR, list(GAP_K), list(BLOCK_NS), ZONE_FT, sorted(ZONE_HW),
                         CONNECT_MIN_MI, sorted(DRIVE_HW), XING_LANES, XING_MPH, XING_SIGNAL_M, XING_PEN_M, BREAK_FT]).encode())
    _sha_files(h, [os.path.join(ROOT, "data", "osm-cache", "sf-walk.json"), DRIVE_CACHE, paths.script("school-travel-time.py"),
                   paths.script("walknet.py"), os.path.join(ROOT, "site", "data", "bike-history", "segments.json"),
                   os.path.join(ROOT, "site", "data", "bike-history", "components.json"),
                   os.path.join(ROOT, "site", "data", "bike-history", "planned.json")] + sorted(glob.glob(DEM_GLOB))
               + ([SEGMENTS] if os.path.exists(SEGMENTS) and not IGNORE_SEGMENTS else []))
    h.update(json.dumps([b["geoid"] for b in blks]).encode())
    base = h.hexdigest()
    cdir = os.path.join(CACHE, "trips")
    os.makedirs(cdir, exist_ok=True)
    _W["ss_lines"] = {c: v[0] for c, v in school_street_blocks(sch).items()}
    paths = []
    for s in sch:
        hs = hashlib.sha256(base.encode())
        hs.update(json.dumps([s[0], s[2], s[3], tops.get(s[0]), _W["ss_lines"].get(s[0])]).encode())
        paths.append(os.path.join(cdir, "%s-%s.npz" % (s[0], hs.hexdigest()[:16])))
    keep = set(os.path.basename(p) for p in paths)
    cds_set = set(s[0] for s in sch)
    for f in os.listdir(cdir):
        if f.endswith(".npz") and f not in keep and f.split("-")[0] in cds_set:
            os.remove(os.path.join(cdir, f))   # this school's stale copy
    res = [None] * len(sch)
    for j, p in enumerate(paths):
        if os.path.exists(p):
            z = np.load(p)
            m = json.loads(str(z["meta"]))
            o = {k: z[k] for k in TRIP_KEYS}
            o["_xb"] = {}
            for k in z.files:
                if k.startswith("xb:") and k.endswith("|bike"):
                    kk = k[3:-5]
                    o["_xb"][kk] = (z[k], z["xb:%s|gap" % kk], z["xb:%s|on" % kk])
            res[j] = (o, m["info"], m["carFallback"], m["noBike"], m["noWalk"], m["network"])
    todo = [j for j in range(len(sch)) if res[j] is None]
    # Every school needs its grounds before the pool starts, or the KeyError fires inside a worker.
    miss = [sch[j][1] for j in todo if school_grounds.key(sch[j][2], sch[j][3]) not in school_grounds.load()]
    assert not miss, "no grounds for %s: rerun tools/school-trips/school-grounds.py" % miss
    t0 = time.time()
    print("  trip times: %d of %d schools cached, %d to compute" % (len(sch) - len(todo), len(sch), len(todo)))
    if todo:
        info = network(blks, {sch[j][0]: tops[sch[j][0]] for j in todo if sch[j][0] in tops})
        print("  network: %d nodes, %d edges, %d on today's all-ages network (%.0fs)" % (
            info["nodes"], info["edges"], info["safeEdges"], time.time() - t0))
        jobs = [(j, sch[j][2], sch[j][3], sch[j][0]) for j in todo]

        def save(j, r):
            o, inf, cf, nb, nw = r
            meta = {"info": inf, "carFallback": cf, "noBike": nb, "noWalk": nw, "network": info}
            arr = {k: o[k] for k in TRIP_KEYS}
            for k, (bm, bg, bo) in sorted(o["_xb"].items()):
                arr["xb:%s|bike" % k] = bm
                arr["xb:%s|gap" % k] = bg
                arr["xb:%s|on" % k] = bo
            tmp = paths[j][:-4] + ".tmp.npz"
            np.savez_compressed(tmp, meta=json.dumps(meta), **arr)
            os.replace(tmp, paths[j])
            res[j] = (o, inf, cf, nb, nw, info)
        done = 0
        if workers > 1 and len(jobs) > 1:
            with multiprocessing.get_context("fork").Pool(min(workers, len(jobs))) as pool:
                for j, r in pool.imap_unordered(_trip_job, jobs, chunksize=1):
                    save(j, r)
                    done += 1
                    if done % 10 == 0 or done == len(jobs):
                        print("    %d of %d schools timed (%.0fs)" % (done, len(jobs), time.time() - t0), flush=True)
        else:
            for jb in jobs:
                save(*_trip_job(jb))
    out = {k: np.stack([r[0][k] for r in res], axis=1) for k in TRIP_KEYS}
    xb = {}
    for j, r in enumerate(res):
        for k, (bm, bg, bo) in sorted(r[0]["_xb"].items()):
            xb["%d|%s|bike" % (j, k)] = bm
            xb["%d|%s|gap" % (j, k)] = bg
            xb["%d|%s|on" % (j, k)] = bo
    out["_xb"] = xb
    meta = {"carFallbackPairs": sum(r[2] for r in res), "noBikePairs": sum(r[3] for r in res),
            "noWalkPairs": sum(r[4] for r in res), "network": res[0][5],
            "perSchool": {s[0]: r[1] for s, r in zip(sch, res)}}
    # A school on Treasure Island (Life Learning Academy) has no walk route from the mainland: the Bay Bridge's west
    # span has no path. Its pairs take the straight-line fallback, as Treasure Island's blocks already do for every
    # mainland school, and are listed rather than counted against the network-break bound.
    island = [j for j, r in enumerate(res) if r[4] > 0.5 * len(blks)]
    meta["islandSchools"] = {sch[j][1]: res[j][4] for j in island}
    mainland = meta["noWalkPairs"] - sum(res[j][4] for j in island)
    assert len(island) <= 1 and mainland <= 0.01 * len(blks) * len(sch), \
        "%d block-school pairs with no walk route; island schools %s" % (meta["noWalkPairs"], meta["islandSchools"])
    bad = [s[1] for s, r in zip(sch, res) if r[2] > 0.1 * len(blks)]
    assert not bad, "car route reaches under 90%% of blocks from %d schools: %s" % (len(bad), "; ".join(bad[:5]))
    meta.update(car_detour(out["walk"], out["carm"], [s[1] for s in sch]))
    assert meta["carDetourPct"] < CAR_DETOUR_MAX_PCT, "%.2f%% of block-school pairs %.1f mi or more apart on foot drive over %gx the walk " \
        "(floor %g%%); worst schools: %s" % (meta["carDetourPct"], CAR_DETOUR_MIN_MI, CAR_DETOUR_X, CAR_DETOUR_MAX_PCT, meta["carDetourWorst"])
    print("  trip times: %d schools x %d blocks (%.0fs)" % (len(sch), len(blks), time.time() - t0))
    return out, meta


def car_detour(walk, carm, names):
    """The car-route check's figures: among pairs CAR_DETOUR_MIN_MI or more apart on foot, the share whose drive is over
    CAR_DETOUR_X times the walk, overall and at the five worst schools."""
    far = walk >= CAR_DETOUR_MIN_MI * MI
    over = far & (carm > CAR_DETOUR_X * walk)
    per = over.sum(axis=0) / np.maximum(far.sum(axis=0), 1)
    worst = sorted(range(len(names)), key=lambda j: (-per[j], names[j]))[:5]
    return {"carDetourPct": round(100 * float(over.sum()) / max(int(far.sum()), 1), 3), "carDetourPairs": int(over.sum()),
            "carDetourOf": int(far.sum()), "carDetourWorst": ["%s %.1f%%" % (names[j], 100 * per[j]) for j in worst]}


VARIANTS = ("today", "calm", "connector", "both")
# The City view's bike network switch: the stretches the integer program chooses at each budget
# (tools/school-trips/school-segments-ip.py, written to SEGMENTS), added to every street-change variant. Without SEGMENTS they
# equal the base. The sets are nested (SEGMENTS_NESTED, on by default): each budget keeps every street of the one below.
SEG_B = (5, 10, 20, 40, 80, 100)
SEG_VARIANTS = tuple("%s_b%d" % (v, b) for b in SEG_B for v in VARIANTS)
ALL_VARIANTS = VARIANTS + SEG_VARIANTS
SEGMENTS = os.path.join(ROOT, "out", "school-sim", "segments.json")
# --segments reads none of a previous run's stretches: the ranking starts from the baseline, and its trips need only
# the base variants, so the cache key leaves SEGMENTS out and each budget variant copies its base.
IGNORE_SEGMENTS = False
# Each network with the School Street block counted as safe street too, for the safe trip figure only: the School
# Street's effect on driving is its study's, so the bike switch never reads these (Bryan, 2026-10-09: "They add
# another half block for most families -- does that do nothing?").
SS_VARIANTS = tuple(v + "_ss" for v in ALL_VARIANTS)
SS_NEAR_FT = 40.0   # a walk edge is on the School Street block when its midpoint is this close to the block's centreline
# The back-cast's networks (V2), timed with on-network metres but given no lever: built is today's without the upcoming
# bikeways, y2019 the 2019 network.
BACKCAST_VARIANTS = ("built", "y2019")
TRIP_KEYS = ("walk", "car", "carm", "rise_today") + tuple("%s_%s" % (k, v) for v in ALL_VARIANTS + SS_VARIANTS for k in ("bike", "gap")) \
    + tuple("on_" + v for v in ALL_VARIANTS) + tuple("%s_%s" % (k, v) for v in BACKCAST_VARIANTS for k in ("bike", "gap", "on"))


def grounds_ft(lon, lat, mx, my, cap_ft):
    """Feet from walk-network points (metres, walknet.xy) to the grounds of the school at (lon, lat); points more than a
    mile beyond cap_ft of its point are left at infinity, since no campus is that big."""
    walknet = _W["walknet"]
    dx, dy = walknet.xy(lon, lat)
    out = np.full(len(mx), np.inf)
    near = np.hypot(mx - dx, my - dy) <= (cap_ft + 5280) * FT
    k = math.cos(walknet.LAT0) * walknet.EARTH
    out[near] = school_grounds.dist_ft(lon, lat, np.degrees(mx[near] / k), np.degrees(my[near] / walknet.EARTH))
    return out


def minutes(T, muni, grad):
    """{mode: dense minutes} from trips(), muni_times() (one Muni array per grade band, transit_<band>), and the bike
    curve's inputs: bike_km, today's route in km, and grad, its average gradient in percent (route_gradient())."""
    walk_mi = T["walk"] / MI
    car = car_calibrated(T["car"])
    out = {"walk": walk_mi / WALK_MPH * 60, "car": car, "carpool": car + CARPOOL_EXTRA_MIN,
           "bike_km": np.minimum(T["bike_today"] / 1000.0, PCT_MAX_KM), "grad": grad}
    for b in BANDS:
        m = muni[b].astype(float)
        out["transit_" + b] = np.where(np.isfinite(m), m, NO_MUNI_MIN)
    for v in ALL_VARIANTS + SS_VARIANTS:
        out["bike_" + v] = bike_minutes(T["bike_" + v])
    out["bike"] = out["bike_today"]
    T["gap"] = T["gap_today"]
    T["bike"] = T["bike_today"]
    return out


def scaled_minutes(mins, f):
    """minutes() with every trip's distance part times f and its fixed parts kept: a school closer to home. Muni keeps
    TRANSIT_FIXED_MIN, and the bike curve's km scale too."""
    car = car_calibrated(CAR_FIXED_MIN + (car_routed(mins["car"]) - CAR_FIXED_MIN) * f)
    fixed = BIKE_GOOGLE_MIN + BIKE_FIXED_MIN
    tr = {"transit_" + b: TRANSIT_FIXED_MIN + np.maximum(mins["transit_" + b] - TRANSIT_FIXED_MIN, 0) * f for b in BANDS}
    return dict(mins, walk=mins["walk"] * f, car=car, carpool=car + CARPOOL_EXTRA_MIN, bike=fixed + (mins["bike"] - fixed) * f,
                bike_km=mins["bike_km"] * f, **tr)


def bike_minutes(metres):
    """Door-to-door bike minutes from route metres: ridden at BIKE_MPH, plus BIKE_GOOGLE_MIN and BIKE_FIXED_MIN."""
    return metres / MI / BIKE_MPH * 60 + BIKE_GOOGLE_MIN + BIKE_FIXED_MIN


def bike_miles(bike_min):
    """bike_minutes() inverted: the route's miles."""
    return np.maximum(bike_min - BIKE_FIXED_MIN - BIKE_GOOGLE_MIN, 0) * BIKE_MPH / 60.0


def car_calibrated(routed_min):
    """Door-to-door car minutes from trips()'s (routed moving minutes at CAR_MPH plus CAR_FIXED_MIN): the moving part
    re-timed by the Google fit, CAR_GOOGLE_A + CAR_GOOGLE_B x moving, with CAR_FIXED_MIN on top."""
    return CAR_FIXED_MIN + CAR_GOOGLE_A + CAR_GOOGLE_B * (routed_min - CAR_FIXED_MIN)


def car_routed(car_min):
    """car_calibrated() inverted: trips()'s routed minutes."""
    return CAR_FIXED_MIN + (car_min - CAR_FIXED_MIN - CAR_GOOGLE_A) / CAR_GOOGLE_B


def car_miles(car_min):
    """minutes()'s car minutes back to the drive's miles at CAR_MPH."""
    return np.maximum(car_routed(car_min) - CAR_FIXED_MIN, 0) * CAR_MPH / 60.0


# -- Muni times ------------------------------------------------------------------

# Scheduled door-to-door Muni minutes for every block, school and grade band, from SFMTA's GTFS feed (the copy
# tools/muni/muni-gtfs.py holds in .cache/muni-gtfs/). A reverse connection scan per school and band: arrive by the
# band's start bell less MUNI_EARLY_MIN; walk up to MUNI_ACCESS_M (straight line x FALLBACK_DETOUR at WALK_MPH) at
# each end; transfer at a stop after MUNI_TRANSFER_S, or walk up to MUNI_FOOT_M to another stop. A block's time is
# the bell less the latest departure from home that still makes it, so it includes the slack before the bell the
# timetable forces. A band with no bell takes MUNI_FALLBACK_BELL; a pair with no Muni route in the MUNI_WINDOW_S
# before the bell takes NO_MUNI_MIN. All our assumptions (notes/school-trips-2026-10/2026-10-18-step1-nested-choice.md).
MUNI_ACCESS_M, MUNI_FOOT_M, MUNI_TRANSFER_S, MUNI_EARLY_MIN = 800.0, 150.0, 60, 5
MUNI_WINDOW_S = 120 * 60
MUNI_FALLBACK_BELL = "08:00"
NO_MUNI_MIN = 180.0


def muni_times(grav, blks, sch):
    """{band: (blocks x schools) Muni minutes, NaN where no route}, meta. Cached in .cache/school-sim/ by the feed's
    SHA-256, the method's settings, the blocks, the schools and their bells."""
    mg = _load("muni_gtfs", paths.script("muni-gtfs.py"))
    zpath = mg.zip_path(ROOT)
    if not os.path.exists(zpath):
        sys.exit("school-sim: no Muni feed at %s (run tools/muni/muni-gtfs.py --update)" % os.path.relpath(zpath, ROOT))
    bell, _miss, _src = bells(grav, sch)
    params = dict(access=MUNI_ACCESS_M, foot=MUNI_FOOT_M, transfer=MUNI_TRANSFER_S, early=MUNI_EARLY_MIN,
                  window=MUNI_WINDOW_S, fallback=MUNI_FALLBACK_BELL, detour=FALLBACK_DETOUR, walk=WALK_MPH)
    h = hashlib.sha256()
    h.update(mg.sha256(zpath).encode())
    src = open(os.path.abspath(__file__)).read()
    h.update(src[src.index("# -- Muni times"):src.index("# -- assignment")].encode())
    h.update(json.dumps([params, [(b["geoid"], b["lon"], b["lat"]) for b in blks],
                         [(s[0], s[2], s[3], {k: (v or {}).get("start") for k, v in sorted(bell[s[0]].items())}) for s in sch]],
                        sort_keys=True).encode())
    path = os.path.join(CACHE, "muni-%s.npz" % h.hexdigest()[:16])
    if os.path.exists(path):
        z = np.load(path)
        return {b: z[b.replace("-", "_")] for b in BANDS}, json.loads(str(z["meta"]))
    import io
    import zipfile
    import pandas as pd
    from scipy.spatial import cKDTree
    t0 = time.time()
    lat0 = math.radians(37.76)

    def xy(lon, lat):
        return np.c_[np.radians(np.asarray(lon, float)) * math.cos(lat0) * 6371000.0, np.radians(np.asarray(lat, float)) * 6371000.0]
    zf = zipfile.ZipFile(zpath)
    day, services, first, last = mg.service_day(zf)
    trips_ = pd.read_csv(zf.open("trips.txt"), dtype=str, usecols=["trip_id", "service_id"])
    trips_ = trips_[trips_.service_id.isin(services)]
    stops = pd.read_csv(zf.open("stops.txt"), dtype={"stop_id": str})
    stops = stops[stops.stop_lat.notna()].sort_values("stop_id", kind="stable")
    st = pd.read_csv(zf.open("stop_times.txt"), dtype=str, usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"])
    st = st[st.trip_id.isin(set(trips_.trip_id))]

    def secs(s):
        p = s.str.split(":", expand=True).astype(int)
        return p[0] * 3600 + p[1] * 60 + p[2]
    st = st.assign(arr=secs(st.arrival_time), dep=secs(st.departure_time), seq=st.stop_sequence.astype(int))
    st = st.sort_values(["trip_id", "seq"], kind="stable")
    sidx = {s: i for i, s in enumerate(stops.stop_id)}
    st = st[st.stop_id.isin(sidx)]
    tidx = {t: i for i, t in enumerate(sorted(set(st.trip_id)))}
    ti = st.trip_id.map(tidx).to_numpy(np.int64)
    si = st.stop_id.map(sidx).to_numpy(np.int64)
    arr, dep = st.arr.to_numpy(np.int64), st.dep.to_numpy(np.int64)
    same = ti[1:] == ti[:-1]
    Cn = np.c_[si[:-1][same], si[1:][same], dep[:-1][same], arr[1:][same], ti[:-1][same]]
    Cn = Cn[(Cn[:, 2] >= 5 * 3600) & (Cn[:, 2] <= 10 * 3600)]
    Cn = Cn[np.lexsort((Cn[:, 4], Cn[:, 0], -Cn[:, 2]))]
    walk_ms = WALK_MPH * MI / 3600.0
    sxy = xy(stops.stop_lon.to_numpy(), stops.stop_lat.to_numpy())
    tree = cKDTree(sxy)
    nbr = [[] for _ in range(len(sxy))]
    for a, b in sorted(tree.query_pairs(MUNI_FOOT_M)):
        w = int(np.hypot(*(sxy[a] - sxy[b])) * FALLBACK_DETOUR / walk_ms)
        nbr[a].append((b, w))
        nbr[b].append((a, w))
    bxy = xy([b["lon"] for b in blks], [b["lat"] for b in blks])
    rows_, cols_, wsec = [], [], []
    for i, ss in enumerate(tree.query_ball_point(bxy, MUNI_ACCESS_M)):
        for s in sorted(ss):
            rows_.append(i)
            cols_.append(s)
            wsec.append(np.hypot(*(bxy[i] - sxy[s])) * FALLBACK_DETOUR / walk_ms)
    rows_, cols_, wsec = np.array(rows_, dtype=np.int64), np.array(cols_, dtype=np.int64), np.array(wsec)
    starts = np.searchsorted(rows_, np.arange(len(blks)))
    has = np.diff(np.r_[starts, len(rows_)]) > 0
    conns = [tuple(int(x) for x in r) for r in Cn]
    neg = -10 ** 9

    def scan(pt, deadline):
        S_ = [neg] * len(sxy)
        for s in tree.query_ball_point(pt, MUNI_ACCESS_M):
            S_[s] = deadline - int(np.hypot(*(pt - sxy[s])) * FALLBACK_DETOUR / walk_ms)
        on = bytearray(len(tidx))
        lo = deadline - MUNI_WINDOW_S
        for u, v, td, ta, k in conns:
            if td > deadline:
                continue
            if td < lo:
                break
            if on[k] or ta + MUNI_TRANSFER_S <= S_[v]:
                on[k] = 1
                if td > S_[u]:
                    S_[u] = td
                    for w, ws in nbr[u]:
                        if td - ws > S_[w]:
                            S_[w] = td - ws
        Sa = np.array(S_, float)
        val = Sa[cols_] - wsec
        val[Sa[cols_] <= neg / 2] = -np.inf
        best = np.full(len(blks), -np.inf)
        best[has] = np.maximum.reduceat(val, starts[has])
        t = (deadline - best) / 60.0
        t[~np.isfinite(t)] = np.nan
        return t

    def hm(s):
        h_, m_ = s.split(":")[:2]
        return int(h_) * 3600 + int(m_) * 60
    out = {b: np.full((len(blks), len(sch)), np.nan, dtype=np.float32) for b in BANDS}
    nobell = 0
    sch_xy = xy([s[2] for s in sch], [s[3] for s in sch])
    for j, s in enumerate(sch):
        for band, b in sorted(bell[s[0]].items()):
            nobell += b is None or not b.get("start")
            out[band][:, j] = scan(sch_xy[j], hm((b or {}).get("start") or MUNI_FALLBACK_BELL) - MUNI_EARLY_MIN * 60)
    meta = {"serviceDay": str(day), "feedFirst": str(first), "feedLast": str(last), "zipSha256": mg.sha256(zpath),
            "connections": int(len(Cn)), "noBellBands": nobell, "params": params,
            "src": "https://www.sfmta.com/reports/gtfs-transit-data"}
    os.makedirs(CACHE, exist_ok=True)
    tmp = path[:-4] + ".tmp.npz"
    np.savez_compressed(tmp, meta=json.dumps(meta), **{b.replace("-", "_"): v for b, v in out.items()})
    os.replace(tmp, path)
    print("  Muni times: %d schools, %d connections on %s (%.0fs)" % (len(sch), len(Cn), day, time.time() - t0))
    return out, meta

# -- assignment ------------------------------------------------------------------

# Each level's reach times step 1's (school-gravity.py's LEVEL_STRETCH: 1, 1.5 and 2), calibrated 2026-10-08 against
# SFUSD's dashboard counts of students by home ZIP, 2025-26 (ZIP_CSV). A grid of multipliers was run and the one with
# the largest student-weighted overlap kept per level. Elementary's 1 here is replaced in main by fit_area's choice
# alongside the attendance-area shares (4 on 2026-10-08), a weak fit: overlap moves only 75.0% to 76.5% across 0.75 to 6. Middle peaks at 2.5
# (77%); high at 10 (78%, against 73% at step 1's 1), where the modelled mean distance to a student's home ZIP also
# meets the dashboard's (2.5 against 2.55 miles). High school assignment is citywide choice, so a near-flat curve fits.
REACH_CAL = {"elementary": 1.0, "middle": 2.5, "high": 10.0}
REACH_STEP1 = {"elementary": 1.0, "middle": 1.0, "high": 1.0}
# The attendance-area mix (fit_area): elementary reach multipliers tried, and rounds of kernel adjustment.
AREA_REACH_GRID = (0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
AREA_PASSES = 4


def GRAV_XY(lon, lat):
    lat0 = math.radians(37.76)
    return (math.radians(lon) * math.cos(lat0) * 6371008.8, math.radians(lat) * 6371008.8)


def _stretches(grav, sch, cols, lvl, reach, med, rc):
    st = []
    for j in cols:
        r = (reach.get(sch[j][0], {}) or {}).get(lvl)
        st.append(grav.stretch_of(lvl, r["rps"] if r and not sch[j][4] else None, med, choice=sch[j][4]) * rc[lvl])
    return np.array(st)


def _mixed(F, O, cols, area, share):
    """Each column of F as the area mix: share k of its weight over its attendance area's blocks, 1 - k by distance.
    A column with no area keeps its distance weight (Furness rescales each column, so its norm doesn't matter)."""
    F = F.copy()
    for c, j in enumerate(cols):
        k = share.get(j, 0.0)
        if k <= 0:
            continue
        f = F[:, c] / max(float(O @ F[:, c]), 1e-300)
        A = area[j].astype(float)
        F[:, c] = (1 - k) * f + k * A / max(float(O @ A), 1e-300)
    return F


def gravity(grav, blks, sch, city, reach_cal=None, area=None):
    """Per grade: origins over blocks, school column indexes, enrolments, and T, the doubly constrained expected students per (block, school).

    area, when given, is {"mask": {school index: blocks in its attendance area}, "share": {school index: target share}}:
    at an elementary grade, that share of the school's students is meant to live in its attendance area. The kernel
    share is adjusted (AREA_PASSES rounds) until the balanced matrix meets it, since Furness moves it."""
    rps = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "requests-per-seat.json")))
    g = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "gravity.json")))
    alpha, beta = g["fit"]["alpha"], g["fit"]["beta"]
    reach, med = grav.reaches(city, rps)
    d = np.stack([grav.dist_mi(blks, s[2], s[3]) for s in sch], axis=1)
    rc = reach_cal or REACH_CAL
    out = {}
    for gr in GRADES:
        lvl = LEVEL[gr]
        cols = [j for j, s in enumerate(sch) if s[5].get(gr, 0) > 0 and not is_private(s)]   # private: private_gravity
        if not cols:
            continue   # only in a sample with no school of this grade
        D = np.array([sch[j][5][gr] for j in cols], dtype=float)
        O = origins(grav, blks, lvl)
        O *= D.sum() / O.sum()
        st = _stretches(grav, sch, cols, lvl, reach, med, rc)
        F = grav.curve(d[:, cols] / st[None, :], alpha, beta)
        tgt = {j: v for j, v in (area or {}).get("share", {}).items() if j in cols and v > 0} if lvl == "elementary" else {}
        k = dict(tgt)
        got = {}
        for _p in range(AREA_PASSES if tgt else 1):
            Tm = grav.furness(O, D, _mixed(F, O, cols, area["mask"], k) if tgt else F, iters=FURNESS_ITERS)
            if not tgt:
                break
            for c, j in enumerate(cols):
                if j in tgt:
                    got[j] = float(Tm[area["mask"][j], c].sum() / max(D[c], 1e-12))
                    k[j] = min(0.995, max(0.0, k[j] * tgt[j] / max(got[j], 1e-6)))
        out[gr] = {"O": O, "cols": np.array(cols), "D": D, "T": Tm, "areaShare": got}
    return out, {"alpha": alpha, "beta": beta, "d0": g["fit"].get("d0")}, d


def area_summary(grav_g, sch, masks, afit, miss, tag, n_areas):
    """Per school and level: the share of students the balanced model puts in the attendance area, beside the fit's
    target and the ZIP upper bound; and student-weighted shares by level (middle and high have no area)."""
    rows = {}
    num, den = {}, {}
    for gr, G in grav_g.items():
        lvl = LEVEL[gr]
        for c, j in enumerate(G["cols"]):
            j = int(j)
            n = float(G["D"][c])
            inside = float(G["T"][masks[j], c].sum()) if (lvl == "elementary" and j in masks) else 0.0
            key = (lvl, "area" if (lvl == "elementary" and j in masks) else "none")
            num[key] = num.get(key, 0.0) + inside
            den[key] = den.get(key, 0.0) + n
            if lvl == "elementary" and j in masks:
                r = rows.setdefault(sch[j][0], {"cds": sch[j][0], "name": sch[j][1], "students": 0.0, "inArea": 0.0,
                                                  "target": round(100 * afit["share"].get(j, 0.0), 1),
                                                  "zipUpperBound": round(100 * afit["upper"][j], 1) if j in afit["upper"] else None})
                r["students"] += n
                r["inArea"] += inside
    for r in rows.values():
        r["inAreaPct"] = round(100 * r["inArea"] / max(r["students"], 1e-9), 1)
        r["students"] = round(r["students"], 1)
        r["inArea"] = round(r["inArea"], 1)
    by = {}
    for (lvl, kind), dn in sorted(den.items()):
        by["%s|%s" % (lvl, kind)] = {"students": round(dn), "inAreaPct": round(100 * num[(lvl, kind)] / max(dn, 1e-9), 1)}
    sh = sorted(r["inAreaPct"] for r in rows.values())
    return {"source": {"areas": "https://data.sfgov.org/d/e6tr-sxwg", "areasTag": tag, "zips": ZIP_SRC["url"],
                       "zipsTag": ZIP_SRC["tag"], "rule": "Bryan, 2026-10-08"},
            "areas": n_areas, "matched": len(masks), "unmatched": miss, "elementaryReach": afit["elementaryReach"],
            "overlapByReach": afit["overlapByReach"], "byLevel": by,
            "areaSchools": {"n": len(sh), "median": sh[len(sh) // 2] if sh else None, "min": sh[0] if sh else None,
                            "max": sh[-1] if sh else None},
            "schools": dict(sorted(rows.items()))}


def area_masks(grav, blks, sch, ztab_match):
    """{school index: blocks in its SFUSD attendance area} for the attendance-area schools, matched by name, and the
    area names left unmatched; plus the read's tag."""
    areas, tag = grav.attendance_areas()
    ba = np.array([-1 if x is None else x for x in grav.block_areas(blks, areas)])
    masks, miss = {}, []
    for k, (nm, _ps) in enumerate(areas):
        j = ztab_match(nm, SPAN_GRADES["TK-5"])
        if j is None:
            miss.append(nm)
        else:
            masks[j] = ba == k
    return masks, miss, tag, len(areas)


def fit_area(grav, blks, sch, city, zips, ztab, cent, masks):
    """Bryan, 2026-10-08: the share of each attendance-area school's TK-5 students living in its area, and the
    distance curve for the rest, from SFUSD's dashboard counts by home ZIP.

    For each elementary reach multiplier in AREA_REACH_GRID, each attendance-area school's share is the one in
    0, 0.01, ..., 1 whose mix (that share over the area's blocks by children, the rest by the distance curve) puts
    its students across ZIPs closest to the dashboard's (largest overlap: the sum over ZIPs of the smaller share).
    A school with no area is the distance curve alone. The multiplier kept is the one with the largest
    student-weighted overlap over every elementary school. The upper bound printed beside each share is the
    dashboard's students in every ZIP that touches the area, over the school's total: a ZIP is bigger than an area,
    so it overstates, and the share is held at or under it."""
    rps = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "requests-per-seat.json")))
    g = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "gravity.json")))
    alpha, beta = g["fit"]["alpha"], g["fit"]["beta"]
    reach, med = grav.reaches(city, rps)
    zs = sorted(cent)
    zi = {z: i for i, z in enumerate(zs)}
    member = np.zeros((len(blks), len(zs)))
    for i, z in enumerate(zips):
        if z in zi:
            member[i, zi[z]] = 1.0
    O = origins(grav, blks, "elementary")
    rows = [(j, dd) for (j, span), dd in sorted(ztab.items()) if span == "TK-5"]
    # Bryan's own estimate, the dashboard's students in every ZIP touching the area over the school's total, caps
    # the share: a ZIP is bigger than an area, so more than that can't live in it.
    upper = {}
    for j, dd in rows:
        if j in masks:
            touch = set(z for z, k in zip(zips, masks[j]) if k and z)
            upper[j] = sum(n for z, n in dd["zips"].items() if z in touch) / float(max(dd["placed"], 1))
    best = None
    grid = {}
    for m in AREA_REACH_GRID:
        rc = dict(REACH_CAL, elementary=m)
        tot, wsum, sh = 0.0, 0.0, {}
        for j, dd in rows:
            st = _stretches(grav, sch, [j], "elementary", reach, med, rc)[0]
            dist = grav.dist_mi(blks, sch[j][2], sch[j][3])
            c = (O * grav.curve(dist / st, alpha, beta)) @ member
            c /= max(c.sum(), 1e-12)
            dz = np.array([dd["zips"].get(z, 0) for z in zs], dtype=float)
            if dz.sum() <= 0:
                continue
            dz /= dz.sum()
            if j in masks:
                a_ = (O * masks[j]) @ member
                a_ /= max(a_.sum(), 1e-12)
                ks = np.linspace(0, 1, 101)
                ks = ks[ks <= upper.get(j, 1.0) + 1e-9]
                ov = [float(np.minimum(k * a_ + (1 - k) * c, dz).sum()) for k in ks]
                i = int(np.argmax(ov))
                sh[j] = float(ks[i])
                o = ov[i]
            else:
                o = float(np.minimum(c, dz).sum())
            tot += o * dd["placed"]
            wsum += dd["placed"]
        grid[m] = round(100 * tot / max(wsum, 1), 2)
        if best is None or grid[m] > grid[best[0]]:
            best = (m, sh)
    m, sh = best
    return {"elementaryReach": m, "share": sh, "upper": upper, "overlapByReach": {str(k): v for k, v in grid.items()}}


def assignment_error(G):
    """Largest gap, as a share, between a grade's expected students and its block children (rows) or school enrolments (columns)."""
    T, O, D = G["T"], G["O"], G["D"]
    row = np.abs(T.sum(axis=1) - O).max() / max(O.max(), 1e-12)
    col = np.abs(T.sum(axis=0) - D).max() / max(D.max(), 1e-12)
    return float(max(row, col))


# -- mode choice -----------------------------------------------------------------

INNER = [CAR, POOL, WALK, TRANSIT, BUS]                  # the modes the inner logit splits, in MODES positions
INNER_KEY = ("car", "carpool", "walk", "transit", "bus")


def level_of(gr):
    """The PCT curve a grade takes: primary for TK-5, secondary for 6-12."""
    return "primary" if GNUM[gr] <= 5 else "secondary"


def inv_logit(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -700, 700)))


def g_pct(level, km, grad, ebike=False):
    """The PCT schools curve's logit (Goodman et al. 2019, Boxes 1 and 2) at route km and average gradient (percent,
    capped at GRAD_CAP_PCT); ebike adds the PCT's e-bike term to the gradient coefficient."""
    k = PCT_CURVE[level]
    h = np.minimum(grad, GRAD_CAP_PCT) - PCT_H0
    return k["a"] + k["d"] * km + k["d2"] * km ** 2 + k["sqrt"] * np.sqrt(km) + (k["h"] + (PCT_EBIKE_H if ebike else 0.0)) * h


def bike_logit(mins, cols, gr, ebike=False):
    """(blocks, schools of the grade) the bike curve's logit before the grade's constant."""
    return g_pct(level_of(gr), mins["bike_km"][:, cols], mins["grad"][:, cols], ebike)


def inner_utilities(mins, cols, gr, beta):
    """(blocks, schools of the grade, 5) the inner logit's utilities before the constants, in INNER order: beta x
    ln(minutes), walk closed past WALK_LIMIT_MI_K5 for TK-5, the yellow bus open only to its eligible students (TK-8,
    over 2 walking miles) at the car's time plus BUS_EXTRA_MIN."""
    walk_mi = mins["walk"][:, cols] / 60.0 * WALK_MPH
    car = mins["car"][:, cols]
    t = {"car": car, "carpool": mins["carpool"][:, cols], "walk": mins["walk"][:, cols],
         "transit": mins["transit_" + BAND_OF[gr]][:, cols], "bus": car + BUS_EXTRA_MIN}
    V = np.stack([beta[k] * np.log(np.maximum(t[k], 1.0)) for k in INNER_KEY], axis=2)
    if GNUM[gr] <= 5:
        V[..., 2] = np.where(walk_mi <= WALK_LIMIT_MI_K5, V[..., 2], -np.inf)
    yb = CHANGES["yellow_bus"]
    V[..., 4] = np.where((walk_mi > yb["over_mi"]) & (GNUM[gr] <= yb["max_grade"]), V[..., 4], -np.inf)
    return V


def softmax(V):
    V = V - V.max(axis=-1, keepdims=True)
    e = np.exp(V)
    return e / e.sum(axis=-1, keepdims=True)


def nest(pb, p_in):
    """Six-mode shares (MODES order) from P(bike) and the inner logit's five."""
    out = np.empty(p_in.shape[:-1] + (6,))
    out[..., INNER] = p_in * (1 - pb)[..., None]
    out[..., BIKE] = pb
    return out


def probs(mins, cols, gr, asc, beta):
    """(blocks, schools of the grade, 6 modes) today's choice. asc is the grade's six constants in MODES order, the
    bike's being the curve's shift c."""
    pb = inv_logit(bike_logit(mins, cols, gr) + asc[BIKE])
    return nest(pb, softmax(inner_utilities(mins, cols, gr, beta) + asc[INNER][None, None, :]))


def bus_targets(grav_g, mins):
    """Each grade's share of students on today's BUS_TODAY yellow-bus riders: the same share of every eligible student
    (TK-8, over 2 walking miles), as SFUSD's riders are spread now."""
    yb = CHANGES["yellow_bus"]
    el, tot = {}, {}
    for gr, G in grav_g.items():
        walk_mi = mins["walk"][:, G["cols"]] / 60.0 * WALK_MPH
        ok = (walk_mi > yb["over_mi"]) & (GNUM[gr] <= yb["max_grade"])
        el[gr], tot[gr] = float((G["T"] * ok).sum()), float(G["T"].sum())
    n_el = sum(el.values())
    take = min(1.0, BUS_TODAY / n_el) if n_el > 0 else 0.0
    return {gr: take * el[gr] / tot[gr] if tot[gr] > 0 else 0.0 for gr in grav_g}, take


def _fit_shift(g, W, target, iters=80):
    """The constant c with sum(W inv.logit(g + c)) / sum(W) = target, by bisection (a fixed count, so it repeats)."""
    lo, hi = -30.0, 30.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if float((inv_logit(g + mid) * W).sum()) / float(W.sum()) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def calibrate(grav_g, mins, targets, beta, iters=400):
    """Per grade, six constants in MODES order: the bike curve's shift c, fit so the bike share is the tally's, then the
    inner logit's (car fixed at 0) fit on the students left, so every mode's share is the tally's. Each tally share is
    scaled by (1 - the grade's bus share), since the tally has no bus bar and SFUSD's riders are in the choice."""
    bus, _take = bus_targets(grav_g, mins)
    asc = {}
    for gr, G in grav_g.items():
        W, cols = G["T"], G["cols"]
        tg = targets[gr]
        c = _fit_shift(bike_logit(mins, cols, gr), W, float(tg[BIKE]) * (1 - bus[gr]))
        pb = inv_logit(bike_logit(mins, cols, gr) + c)
        wt = W * (1 - pb)
        V = inner_utilities(mins, cols, gr, beta)
        tin = np.r_[tg[[CAR, POOL, WALK, TRANSIT]] * (1 - bus[gr]), bus[gr]]
        use = tin > 0
        a = np.zeros(5)
        for _ in range(iters):
            p = softmax(V + a[None, None, :])
            share = (p * wt[:, :, None]).sum(axis=(0, 1)) / W.sum()
            step = np.where(use, np.log(np.where(use, tin, 1.0) / np.maximum(share, 1e-300)), 0.0)
            a = a + step - step[0]
            if np.abs(share - tin)[use].max() < 1e-9:
                break
        x = np.zeros(6)
        x[INNER] = a
        x[BIKE] = c
        asc[gr] = x
    return asc


def bike_reference(grav_g, mins, targets):
    """The SF shift each case moves from, per PCT level: one constant fit over the level's pooled students to their
    tally bike share, leaving out TK and kindergarten, whose 6% is mostly children carried on a parent's bike (each
    grade keeps its own constant for today's match, and that extra part doesn't scale toward Dutch)."""
    bus, _take = bus_targets(grav_g, mins)
    out = {}
    for lvl in ("primary", "secondary"):
        gs, Ws, num = [], [], 0.0
        for gr, G in grav_g.items():
            if level_of(gr) != lvl or gr in ("TK", "KN"):
                continue
            gs.append(bike_logit(mins, G["cols"], gr).ravel())
            Ws.append(G["T"].ravel())
            num += float(G["T"].sum()) * float(targets[gr][BIKE]) * (1 - bus[gr])
        if gs:
            W = np.concatenate(Ws)
            out[lvl] = round(_fit_shift(np.concatenate(gs), W, num / float(W.sum())), 4)
    return out


# -- changes -----------------------------------------------------------------------

def _solve_shift(pr, n, school, ns, idx_up, target_delta, sign, hold=(POOL, BUS)):
    """Per school, one utility shift on the modes idx_up so their share moves by target_delta points (sign +1 up, -1 down).

    The modes in hold keep their share: a yellow bus seat and a carpool are programs with their own riders, so a
    School Street or a walking school bus moves students between the other modes only (Fable review 2026-10-09:
    bus riders had reached 4,826 against 4,500 seats)."""
    hold = [h for h in hold if h not in idx_up]
    free = 1.0 - pr[:, hold].sum(axis=1)
    up_abs = pr[:, idx_up].sum(axis=1)
    up = np.where(free > 0, up_abs / np.maximum(free, 1e-300), 0.0)
    N = np.bincount(school, weights=n, minlength=ns)
    now = np.bincount(school, weights=n * up_abs, minlength=ns)
    room = np.bincount(school, weights=n * free, minlength=ns)
    want = np.where(N > 0, now / np.maximum(N, 1) + sign * target_delta / 100.0, 0)
    want = np.clip(want, 0, room / np.maximum(N, 1))
    lo, hi = np.zeros(ns), np.zeros(ns)
    if sign > 0:
        hi[:] = 20.0
    else:
        lo[:] = -20.0
    for _ in range(60):
        mid = (lo + hi) / 2
        e = np.exp(mid[school])
        a = up * e / (up * e + 1 - up)
        got = np.bincount(school, weights=n * free * a, minlength=ns) / np.maximum(N, 1)
        too = got > want
        hi = np.where(too, mid, hi)
        lo = np.where(too, lo, mid)
    e = np.exp(((lo + hi) / 2)[school])
    a = up * e / (up * e + 1 - up)
    out = pr.copy()
    f_up = np.where(up > 0, a / np.maximum(up, 1e-300), 0)
    f_dn = np.where(up < 1, (1 - a) / np.maximum(1 - up, 1e-300), 0)
    mask = np.zeros(pr.shape[1], dtype=bool)
    mask[idx_up] = True
    held = np.zeros(pr.shape[1], dtype=bool)
    held[hold] = True
    out[:, mask] *= f_up[:, None]
    out[:, ~mask & ~held] *= f_dn[:, None]
    return out


# The changes that move a student onto a trip another adult supplies, and the share of those students whose own parent
# no longer makes the trip: a yellow bus at any grade; a walking school bus with one adult to about three children, as
# Seattle's buses run, so two of three are freed; a two-family carpool, where the other parent drives half the days.
# Our assumptions. Every other change frees no parent: their studies measure who switches to walking, biking or
# Muni, not whether a parent still goes along, and with Free Muni for caregivers the caregiver rides (Bryan,
# 2026-10-10: "That's a bad assumption if there's no research. Let's count switchers only").
FREE_CREDIT = {"yellow_bus": {BUS: 1.0}, "walking_bus": {WALK: 2 / 3, BIKE: 2 / 3}, "carpool": {POOL: 0.5}}


def free_share(C, pr):
    """(cells x 6) per cell and mode, the share of students on that mode whose trip needs no parent today: SOLO on
    today's network."""
    return pr * solo_ok(C, C["bike_min_today"], C["gap_today"])


def track_acc(name, pr0, pr1, acc, C):
    """(cells x 6) per cell and mode, the share of students whose trip needs no parent, after change name took pr0
    to pr1; its row sum is the cell's no-parent share. It starts at today's SOLO and moves only with the FREE_CREDIT
    changes. Students leave a mode in proportion, taking their share of its credit with them. Under a FREE_CREDIT
    change, those leaving lose their credit and those arriving on the change's adult-led mode gain its credit. Under
    any other change the credit the leavers carried moves with them to the modes that gained, so the total stays put:
    a street change or a network never makes an existing trip count, since no study shows families act on that."""
    if acc is None:
        acc = free_share(C, pr0)
    d = pr1 - pr0
    keep = np.where(pr0 > 0, np.minimum(pr1, pr0) / np.where(pr0 > 0, pr0, 1.0), 0.0)
    out = acc * keep
    lost = (acc - out).sum(axis=1)
    gain = np.maximum(d, 0.0)
    cr = FREE_CREDIT.get(name)
    if cr:
        for m, c in cr.items():
            out[:, m] += gain[:, m] * c
        return out
    g = gain.sum(axis=1)
    return out + gain * np.where(g > 0, lost / np.where(g > 0, g, 1.0), 0.0)[:, None]


def chain(names, pr, C, ns, prm, acc=None):
    """Apply the changes in order: (pr, the no-parent share per cell and mode; see track_acc)."""
    if acc is None:
        acc = free_share(C, pr)
    for ch in names:
        nxt = apply_change(ch, pr, C, ns, prm)
        acc = track_acc(ch, pr, nxt, acc, C)
        pr = nxt
    return pr, acc


def _inner_shift(pr, m, x, ok):
    """pr with mode m's odds within the inner nest times e^x where ok, the other inner modes scaled to make room."""
    out = pr.copy()
    nb = 1 - pr[ok, BIKE]
    q = np.where(nb > 0, pr[ok, m] / np.maximum(nb, 1e-300), 0.0)
    q2 = q * np.exp(x) / (1 - q + q * np.exp(x))
    f = np.where(q < 1, (1 - q2) / np.maximum(1 - q, 1e-300), 0.0)
    sub = out[ok]
    oth = [k for k in INNER if k != m]
    sub[:, oth] *= f[:, None]
    sub[:, m] = q2 * nb
    out[ok] = sub
    return out


def car_cost_tref(C):
    """The money term's reference trip: the driven students' weighted median car minutes today."""
    w = C["n"] * C["pr"][:, CAR]
    return _wmedian(C["car_min"], w)


def car_cost_shift(pr, C, usd_day, vot_usd_hr, sel=None, form=None, trips=None):
    """pr with a daily charge on the family car, on the cells in sel (all by default). The school trip pays its share
    of the day's charge, usd_day over the household's daily vehicle trips (trips, CAR_COST_TRIPS by default); a
    carpool pays half. form "money" (the default, CAR_COST_FORM) adds a linear money term, BETA_LOG's car
    coefficient over the reference trip (car_cost_tref) per minute of value of time, so a dollar weighs the same on
    every trip; "logmin" adds the dollars as minutes inside the log, which weighs a dollar more on a short drive."""
    sel = np.ones(len(pr), dtype=bool) if sel is None else sel
    form = form or CAR_COST_FORM
    usd = usd_day / (trips or CAR_COST_TRIPS)
    dm = usd / (vot_usd_hr / 60.0)
    dv = np.zeros((int(sel.sum()), 6))
    car, pool = C["car_min"][sel], C["carpool_min"][sel]
    if form == "logmin":
        dv[:, CAR] = BETA_LOG["car"] * (np.log(np.maximum(car + dm, 1.0)) - np.log(np.maximum(car, 1.0)))
        dv[:, POOL] = BETA_LOG["carpool"] * (np.log(np.maximum(pool + dm / 2, 1.0)) - np.log(np.maximum(pool, 1.0)))
    else:
        t = car_cost_tref(C)
        dv[:, CAR] = BETA_LOG["car"] / t * dm
        dv[:, POOL] = BETA_LOG["carpool"] / t * dm / 2
    sub = pr[sel]
    nb = 1 - sub[:, BIKE]
    w = sub[:, INNER] * np.exp(dv[:, INNER])
    tot = w.sum(axis=1)
    out = pr.copy()
    sub2 = sub.copy()
    sub2[:, INNER] = np.where(tot[:, None] > 0, w / np.maximum(tot, 1e-300)[:, None] * nb[:, None], sub[:, INNER])
    out[sel] = sub2
    return out


def apply_change(name, pr, C, ns, prm):
    """A change on a round's cells: pr (cells x 6 modes) in, pr out."""
    p = prm[name]
    n, sch, gnum = C["n"], C["school"], C["gnum"]
    if name == "caregiver_muni":
        ok = (C["transit_min"] - C["car_min"] <= p["within_min"]) & (gnum <= p["max_grade"])
        mv = pr[:, CAR] * p["cost_share"] * p["takeup"] * ok
        pr = pr.copy()
        pr[:, CAR] -= mv
        pr[:, TRANSIT] += mv
        return pr
    if name == "yellow_bus":
        # Denver's loop take-up: p["riders"] new riders among the students the bus already serves (TK-8, over 2 miles'
        # walk), by one shift on the bus constant solved citywide. The bus is a choice mode, so the riders leave the
        # other modes as the inner logit says; the share who leave a family car is a check against MyBus's 48%
        # (validation.json changes), not a setting.
        ok = pr[:, BUS] > 0
        lo, hi = 0.0, 10.0
        for _ in range(60):
            mid = (lo + hi) / 2
            got = float((n * (_inner_shift(pr, BUS, mid, ok)[:, BUS] - pr[:, BUS])).sum())
            lo, hi = (mid, hi) if got < p["riders"] else (lo, mid)
        return _inner_shift(pr, BUS, (lo + hi) / 2, ok)
    if name == "carpool":
        mv = pr[:, CAR] * p["share"]
        pr = pr.copy()
        pr[:, CAR] -= mv
        pr[:, POOL] += mv
        return pr
    if name == "ebike":
        # The PCT's own e-bike scenario, +PCT_EBIKE_H on the gradient coefficient, for every student at a school where
        # most students within 2 miles have a safe route on today's network (ebike_gate; Bryan, 2026-10-13). The set
        # is full strength: the page blends it down to the families who take the help.
        d = PCT_EBIKE_H * np.maximum(np.minimum(C["grad"], GRAD_CAP_PCT) - PCT_H0, 0.0) * ebike_gate(C, C["gap_total_ft"])
        return shift_bike(pr, d)
    if name == "car_cost":
        # Parking priced and a driving charge as one lever: a daily charge on the family car, turned into minutes at
        # p["vot_usd_hr"] and added to the car's minutes in the inner logit (half of it to a carpool's, shared by two
        # families). Every student, at full strength; the page scales it by the share charged.
        return car_cost_shift(pr, C, p["usd_day"]["central"], p["vot_usd_hr"]["central"])
    if name in ASSIGN:
        # Shorter trips for TK-5: the option's choice minus today's, added to pr and renormalised, so it stacks.
        sel = (gnum <= p["max_grade"]) & C["sfusd"]   # SFUSD's assignment places neither charter nor private students
        out = pr.copy()
        d = C["pr_" + name][sel] - C["pr"][sel]
        x = np.clip(pr[sel] + d, 0, None)
        tot, xs = pr[sel].sum(axis=1), x.sum(axis=1)
        out[sel] = x * np.where(xs > 0, tot / np.where(xs > 0, xs, 1), 0)[:, None]
        return out
    if name == "school_street":
        # The study's schools are primary schools, so the drop applies to a school's TK-5 students only.
        sel = gnum <= p["max_grade"]
        out = pr.copy()
        if sel.any():
            out[sel] = _solve_shift(pr[sel], n[sel], sch[sel], ns, [CAR], p["pp"], -1)
        return out
    if name in ("safer_crossings", "walking_bus"):
        sel = gnum <= p["max_grade"]
        if name == "walking_bus":
            # Johnson et al. measured grades 3-5 within a mile; TK-2 is our extension (Bryan, 2026-10-09).
            sel &= (C["walk_mi"] <= p["within_mi"]) & (gnum >= p["min_grade"])
        out = pr.copy()
        if sel.any():
            out[sel] = _solve_shift(pr[sel], n[sel], sch[sel], ns, [WALK, BIKE], p["pp"], +1)
        return out
    raise KeyError(name)


# -- the simulation ----------------------------------------------------------------

# A School Street the address match would put on the wrong block, with the block Bryan named for it
# (staging comment 8r2e1zsgvtta, 2026-10-09): {cds: (street, from street, to street)} on the centreline.
SS_BLOCK = {"38684783830031": ("PIERCE", "FELL ST", "HAYES ST")}   # Ida B. Wells High, 1099 Hayes St


def school_street_blocks(sch):
    """{cds: (lines, how)}: the centreline block in front of each school's street address, as [lon, lat] lines.
    The address is the school's in DataSF 7e7j-59qk; the block is the active centreline row in 3psu-pn9h on that
    street whose left or right address range holds the house number. SS_BLOCK overrides it by cross streets."""
    import re
    from sfdata import fetch
    from streetindex import canon
    from streetnames import SUFFIX
    addr = {r["cds_code"]: r["street_address"] for r in fetch("7e7j-59qk", select="cds_code,street_address", floor=150).rows}
    rows = fetch("3psu-pn9h", select="cnn,street,st_type,lf_fadd,lf_toadd,rt_fadd,rt_toadd,f_st,t_st,line",
                 where="active=true", floor=10000).rows
    def key(street, st_type):
        return canon(street) + "|" + canon(SUFFIX.get((st_type or "").lower(), (st_type or "").lower()))
    by_st = {}
    for r in rows:
        if r.get("line"):
            by_st.setdefault(key(r.get("street"), r.get("st_type")), []).append(r)
            by_st.setdefault(canon(r.get("street")), []).append(r)
    def num(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    def holds(r, h):
        for a, b in (("lf_fadd", "lf_toadd"), ("rt_fadd", "rt_toadd")):
            lo, hi = num(r.get(a)), num(r.get(b))
            if lo is not None and hi is not None and min(lo, hi) <= h <= max(lo, hi) and lo % 2 == h % 2:
                return True
        return False
    def lines(r):
        g = r["line"]
        parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        return [[[round(a, 5), round(b, 5)] for a, b in p] for p in parts]
    ORDINAL = {w: f"{i}{'st' if i == 1 else 'nd' if i == 2 else 'rd' if i == 3 else 'th'}" for i, w in enumerate(
        "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth".split(), 1)}
    rows = [r for r in rows if r.get("line")]
    out = {}
    for s in sch:
        cds = s[0]
        if cds in SS_BLOCK:
            st, f, t = SS_BLOCK[cds]
            hit = [r for r in by_st.get(canon(st), []) if {r.get("f_st"), r.get("t_st")} == {f, t}]
            if hit:
                out[cds] = ([l for r in hit for l in lines(r)], "named")
                continue
        m = re.match(r"\s*(\d+)[A-Za-z]?\s+([^,]+?)\.?\s*(,|$)", addr.get(cds) or "")
        if m:
            h, words = int(m.group(1)), [ORDINAL.get(w.lower(), w) for w in m.group(2).split()]
            cands = by_st.get(key(" ".join(words[:-1]), words[-1]), []) if len(words) > 1 else []
            cands = cands or by_st.get(canon(" ".join(words)), []) or by_st.get(canon(" ".join(words[:-1])), [])
            hit = [r for r in cands if holds(r, h)]
            if hit:
                out[cds] = ([l for r in hit[:1] for l in lines(r)], "address")
                continue
        # No address, or none that matches a block: the centreline block nearest the school's point.
        lon, lat = s[2], s[3]
        best = min(rows, key=lambda r: min((a - lon) ** 2 * 0.62 + (b - lat) ** 2 for p in lines(r) for a, b in p))
        out[cds] = (lines(best), "nearest")
    return out


def overlays(sch, conn_ok=None):
    """The street changes as lines for the City view's map, in site/data/school-sim/overlays.json: each school's
    School Connector, drawn exactly as trips_one builds it, its School Street block (the centreline
    block in front of its street address, school_street_blocks), and the ranked bikeway segments at each milestone. Needs network() first."""
    walknet, net, L, safe, n = _W["walknet"], _W["net"], _W["L"], _W["safe"], _W["n"]
    eu, ev, x, y = _W["eu"], _W["ev"], _W["x"], _W["y"]
    k = math.cos(walknet.LAT0) * walknet.EARTH

    def ll(i):
        return [round(math.degrees(x[i] / k), 5), round(math.degrees(y[i] / walknet.EARTH), 5)]

    def lines(mask):
        return [[ll(int(eu[e])), ll(int(ev[e]))] for e in np.flatnonzero(mask)]
    mx_, my_ = (x[eu] + x[ev]) / 2, (y[eu] + y[ev]) / 2
    ssb = school_street_blocks(sch)
    print(f"  overlays: School Street block for {len(ssb)} of {len(sch)} schools "
          f"({sum(h == 'named' for _l, h in ssb.values())} named by Bryan); nearest block, no address match, for: "
          + ", ".join(s[1] for s in sch if ssb.get(s[0], ([], ""))[1] == "nearest"), flush=True)
    out = []
    for s in sch:
        cds, lon, lat = s[0], s[2], s[3]
        door = net.ends(lon, lat)
        door = [d for d in door if _W["walkable"][d[3]]] or door
        wdist, wpred, wlk = _dijkstra(_W["Lw"].copy(), [d[0] for d in door], [d[1] + d[2] for d in door])
        zone = _W["zone_hw"] & (grounds_ft(lon, lat, mx_, my_, ZONE_FT) <= ZONE_FT) & ~safe
        conn = np.zeros(len(L), dtype=bool)
        tgt = _W["run_ok"]
        nodes = np.unique(np.r_[eu[tgt], ev[tgt]])
        if len(nodes):
            t = int(nodes[np.argmin(wdist[nodes])])
            if np.isfinite(wdist[t]):
                key, ref = wlk
                v = t
                while v != n and v >= 0:
                    pv = int(wpred[v])
                    if pv < 0:
                        break
                    r = ref[np.searchsorted(key, pv * (n + 1) + v)]
                    if r >= 0:
                        conn[r] = True
                    v = pv
                conn &= ~safe
        ssl = ssb.get(cds, ([], None))[0]
        if conn_ok is not None and not conn_ok.get(cds):
            conn[:] = False   # more than 1 block from the network: no School Connector
        # The connector's feet on the School Street block, which a School Street already makes safe, so that with both
        # switched on the block isn't built twice (Bryan, 2026-10-09). The block's edges as trips_one finds them.
        ss = np.zeros(len(L), dtype=bool)
        for line in ssl:
            xy = np.array([walknet.xy(a, b) for a, b in line])
            for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
                vx, vy = x1 - x0, y1 - y0
                t = np.clip(((mx_ - x0) * vx + (my_ - y0) * vy) / max(vx * vx + vy * vy, 1e-9), 0, 1)
                ss |= np.hypot(mx_ - (x0 + t * vx), my_ - (y0 + t * vy)) <= SS_NEAR_FT * FT
        ss &= _W["walkable"] & ~safe
        out.append({"cds": cds, "connector": lines(conn), "schoolStreet": ssl,
                    "connectorFt": round(float(L[conn].sum() / FT)), "connectorOnSchoolStreetFt": round(float(L[conn & ss].sum() / FT))})
    seg = []
    if os.path.exists(SEGMENTS):
        sg = json.load(open(SEGMENTS))
        by_id = {c["id"]: c for c in sg["chunks"]}
        at = {}
        for bk in sg["budgets"]:
            for cid in bk["chunks"]:
                at.setdefault(cid, {"budgets": [], "bridge": []})["budgets"].append(bk["budgetM"])
                if cid in bk.get("bridges", []):
                    at[cid]["bridge"].append(bk["budgetM"])
        for cid in sorted(at):
            c = by_id[cid]
            seg.append({"id": cid, "street": " ".join(w.lstrip("0").capitalize() for w in c["street"].split()), "mi": round(float(c["mi"]), 2),
                        "types": c.get("facilities", []), "budgets": at[cid]["budgets"], "bridge": at[cid]["bridge"],
                        "lines": [[[round(a, 5), round(b, 5)] for a, b in pts] for pts in c["pts"]]})
    return {"note": "Written by tools/school-trips/school-sim.py --overlays. Lines are [lon, lat] pairs. segments holds each new bikeway piece "
                    "(id, street, miles, bikeway types, lines) once, with the budgets ($M) whose chosen set holds it and the budgets at "
                    "which it is a bridge (a piece that brings nobody within a safe ride alone but sits on a chosen route).",
            "schools": out, "segments": seg}


def on_share(T, v, idx=None):
    """(blocks x schools, or idx's cells) the share of each bike route's metres on the all-ages network, on variant v:
    trips()'s on_<v> metres over the route's when the trip run carries them; otherwise 1 - the total gap
    over the route's length, which is the same share, since the total gap is the route's off-network metres (a route
    broken at a busy crossing carries BREAK_FT on its gap, so it reads lower)."""
    def pick(x):
        return x if idx is None else x[idx]
    bm = np.maximum(pick(T["bike_" + v]).astype(float), 1.0)
    if ("on_" + v) in T:
        return np.clip(pick(T["on_" + v]) / bm, 0.0, 1.0)
    return np.clip(1.0 - pick(T["gap_" + v]) * FT / bm, 0.0, 1.0)


def cells(grav_g, mins, T, asc, beta, cref):
    """Every (block, school, grade) with expected students: the count, today's choice, and the times the changes read.

    Each cell also carries the bike curve's logit g (before the grade's constant), its route km and gradient, the
    High case's full shift caseD (Go Dutch less the level's SF reference shift, cref), and its route's on-network
    share on every network variant (on_<variant>). Pairs under PRUNE of a block's students in the grade are dropped;
    the share of students they hold is returned."""
    walk_mi = T["walk"] / MI
    parts, dropped, total = [], 0.0, 0.0
    extra_v = [v for v in ("built", "y2019") if "bike_" + v in T]
    for gr in grav_g:
        G = grav_g[gr]
        Tm = G["T"]
        O = Tm.sum(axis=1)
        keep = (Tm > 0) & (Tm >= PRUNE * O[:, None])
        dropped += float(Tm[~keep].sum())
        total += float(Tm.sum())
        b, jj = np.nonzero(keep)
        j = G["cols"][jj]
        pr = probs(mins, G["cols"], gr, asc[gr], beta)[b, jj]
        pr_a = {a: probs(scaled_minutes(mins, CHANGES[a]["ratio"]), G["cols"], gr, asc[gr], beta)[b, jj] for a in ASSIGN}
        lvl = level_of(gr)
        km = mins["bike_km"][b, j]
        d0, d1 = PCT_DUTCH[lvl]
        parts.append({"b": b, "school": j, "n": Tm[b, jj], "gnum": np.full(len(b), GNUM[gr]), "grade": np.full(len(b), GRADES.index(gr)),
                      "pr": pr, **{"pr_" + a: pr_a[a] for a in ASSIGN}, "car_min": mins["car"][b, j], "bike_min": mins["bike"][b, j],
                      "transit_min": mins["transit_" + BAND_OF[gr]][b, j], "gap_total_ft": T["gap"][b, j], "walk_mi": walk_mi[b, j],
                      "walk_min": mins["walk"][b, j], "carpool_min": mins["carpool"][b, j], "bike_mi": T["bike"][b, j] / MI,
                      "g": bike_logit(mins, G["cols"], gr)[b, jj], "bike_km": km, "grad": mins["grad"][b, j],
                      "level": np.full(len(b), 0 if lvl == "primary" else 1, dtype=np.int8),
                      "caseD": d0 + d1 * km - cref[lvl],
                      **{"bike_min_" + v: mins["bike_" + v][b, j] for v in ALL_VARIANTS + SS_VARIANTS},
                      **{"gap_" + v: T["gap_" + v][b, j] for v in ALL_VARIANTS + SS_VARIANTS},
                      **{"on_" + v: on_share(T, v, (b, j)) for v in ALL_VARIANTS + tuple(extra_v)}})
    C = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    return C, dropped / total


# -- the bike's gradient -------------------------------------------------------------

def gradient_proxy(blks, sch):
    """(blocks x schools) V0's straight-line gradient proxy, percent: each street block's avg_grade
    (data/street-grades/grades.json, tools/school-trips/street-grades.py) on a 50 m grid, averaged along the straight line from
    home to school. Used where a trip run carries no routed rise, and for pairs with no bike route."""
    sg = _load("street_grades", paths.script("street-grades.py"))
    g = json.load(open(sg.OUT))["blocks"]
    rows, _r = sg.blocks()
    lat0 = math.radians(37.76)

    def xy(lon, lat):
        return np.radians(lon) * math.cos(lat0) * 6371000.0, np.radians(lat) * 6371000.0
    px, py, pg = [], [], []
    for cnn, _n, _l, _k, pts in rows:
        v = g.get(cnn)
        if v is None:
            continue
        co = np.array(pts, dtype=float)
        x, y = xy(co[:, 0], co[:, 1])
        seg = np.hypot(np.diff(x), np.diff(y))
        L = seg.sum()
        n = max(2, int(L / 10) + 1)
        t = np.linspace(0, L, n)
        cum = np.r_[0, np.cumsum(seg)]
        px.append(np.interp(t, cum, x))
        py.append(np.interp(t, cum, y))
        pg.append(np.full(n, v[0]))
    px, py, pg = np.concatenate(px), np.concatenate(py), np.concatenate(pg)
    cell = 50.0
    x0, y0 = px.min(), py.min()
    ix, iy = ((px - x0) // cell).astype(int), ((py - y0) // cell).astype(int)
    nx, ny = ix.max() + 1, iy.max() + 1
    ssum, scnt = np.zeros((nx, ny)), np.zeros((nx, ny))
    np.add.at(ssum, (ix, iy), pg)
    np.add.at(scnt, (ix, iy), 1)
    rast = np.where(scnt > 0, ssum / np.maximum(scnt, 1), np.nan)
    bx, by = xy(np.array([b["lon"] for b in blks]), np.array([b["lat"] for b in blks]))
    sx, sy = xy(np.array([s[2] for s in sch]), np.array([s[3] for s in sch]))
    out = np.full((len(blks), len(sch)), np.nan)
    tt = (np.arange(60) + 0.5) / 60
    for j in range(len(sch)):
        X = bx[:, None] + (sx[j] - bx[:, None]) * tt[None, :]
        Y = by[:, None] + (sy[j] - by[:, None]) * tt[None, :]
        vals = rast[np.clip(((X - x0) // cell).astype(int), 0, nx - 1), np.clip(((Y - y0) // cell).astype(int), 0, ny - 1)]
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # a line crossing no graded block averages nothing
            out[:, j] = np.nanmean(np.where(np.isfinite(vals), vals, np.nan), axis=1)
    return np.where(np.isfinite(out), out, float(np.nanmedian(pg)))


def route_gradient(T, blks, sch):
    """(blocks x schools) today's bike route's average gradient in percent, and how it was found: the routed figure,
    cumulative absolute rise along the route (trips()'s rise_today) over its length, when the trip run carries it;
    otherwise V0's straight-line proxy. A pair with no bike route (rise NaN) takes the proxy."""
    if "rise_today" in T:
        g = 100.0 * T["rise_today"].astype(float) / np.maximum(T["bike_today"].astype(float), 1.0)
        miss = ~np.isfinite(g)
        if miss.any():
            g = np.where(miss, gradient_proxy(blks, sch), g)
        return g, "routed (%.2f%% of pairs on the straight-line proxy)" % (100 * float(miss.mean()))
    return gradient_proxy(blks, sch), "straight-line proxy (gradient_proxy)"


# -- the three cases -----------------------------------------------------------------

# Bryan, 2026-10-18 ("Rebuild the model"): three cases replace the 10/20/30% switch. Each moves the bike curve's
# shift from SF's fitted value toward a target over the ten years, scaled by how much more of the kid's route is on
# the all-ages network than today, and nothing else carries the network: a kid with no new route gets none. The page
# reads year 10; the take-up path to it is plan step 5. Per cell the year-10 shift on network v is
#     lambda[case] x caseD x max(0, on_v - on_today),
# caseD the full Go Dutch shift less the level's SF reference (bike_reference). High is Go Dutch (lambda 1). Low is
# sized so a full network gives LOW_ANCHOR_BIKE_PCT of all students biking: Cambridge, MA's 14.3% of commutes at
# 87.1% coverage, the only US city near full coverage (ACS 2024 1-year B08301, in
# notes/school-trips-2026-10/2026-10-18-pnb-vs-mode-share.md [primary — read 2026-10-18]). That is adults; children's
# share runs 0.4 to 1.3 times adults' in the two cities with both figures, so the anchor is uncertain by a factor of
# three. Central is halfway between, our assumption.
CASES = ("low", "central", "high")
LOW_ANCHOR_BIKE_PCT = 14.3


def shift_bike(pr, d):
    """pr with each cell's bike logit moved by d and the other modes scaled in proportion (the nest's rule, the PCT's
    own: new cyclists come from every other mode alike). Cells with d == 0 are returned exactly as they were."""
    pb = pr[:, BIKE]
    move = (d != 0) & (pb > 0) & (pb < 1)
    if not move.any():
        return pr
    out = pr.copy()
    p = pb[move]
    p2 = inv_logit(np.log(p) - np.log1p(-p) + d[move])
    out[move] *= ((1 - p2) / (1 - p))[:, None]
    out[move, BIKE] = p2
    return out


def network_gain(C, v, ref="today", signed=False):
    """Per cell, the rise in the route's on-network share on variant v over ref (clipped at 0 unless signed)."""
    g = C["on_" + v] - C["on_" + ref]
    return g if signed else np.maximum(g, 0.0)


def case_shift(C, v, lam, idx=None, on=None):
    """Per cell (or idx's), the case's year-10 logit shift on variant v; on overrides the variant's on-network share."""
    D = C["caseD"] if idx is None else C["caseD"][idx]
    o0 = C["on_today"] if idx is None else C["on_today"][idx]
    o = (C["on_" + v] if idx is None else C["on_" + v][idx]) if on is None else on
    return lam * D * np.maximum(o - o0, 0.0)


def case_lambdas(C):
    """{case: lambda}: High 1; Low the lambda at which every route fully on the network gives LOW_ANCHOR_BIKE_PCT of all
    students biking (bisection, a fixed count); Central halfway. Also the year-10 bike share by level at full network
    for each case, against V0's Go Dutch ceilings, and whether the three are ordered."""
    n = C["n"]

    def bike_at(lam):
        pr = shift_bike(C["pr"], lam * C["caseD"] * np.maximum(1.0 - C["on_today"], 0.0))
        return pr

    def pct(pr, m=None):
        m = np.ones(len(n), dtype=bool) if m is None else m
        return 100 * float((n[m] * pr[m, BIKE]).sum() / n[m].sum())
    lo, hi = 0.0, 1.0
    low_above_high = pct(bike_at(1.0)) < LOW_ANCHOR_BIKE_PCT
    if not low_above_high:
        for _ in range(50):
            mid = (lo + hi) / 2
            if pct(bike_at(mid)) < LOW_ANCHOR_BIKE_PCT:
                lo = mid
            else:
                hi = mid
    lam_low = 1.0 if low_above_high else round((lo + hi) / 2, 5)
    lam = {"low": lam_low, "central": round((1 + lam_low) / 2, 5), "high": 1.0}
    full = {}
    for k, l in lam.items():
        pr = bike_at(l)
        full[k] = {"all": round(pct(pr), 2), "tk5": round(pct(pr, C["level"] == 0), 2), "g6to12": round(pct(pr, C["level"] == 1), 2)}
    today = {"all": round(pct(C["pr"]), 2), "tk5": round(pct(C["pr"], C["level"] == 0), 2), "g6to12": round(pct(C["pr"], C["level"] == 1), 2)}
    order = all(full["low"][x] <= full["central"][x] <= full["high"][x] for x in ("all", "tk5", "g6to12"))
    return lam, {"lambda": lam, "lowAnchorBikePct": LOW_ANCHOR_BIKE_PCT, "lowAboveHigh": low_above_high,
                 "bikePctTodayByLevel": today, "bikePctFullNetworkYear10": full, "ordered": order,
                 "v0GoDutchCeiling": {"tk5": 10.3, "g6to12": 36.2,
                                      "note": "V0 (notes/school-trips-2026-10/2026-10-18-v0-pct-fit.md): Go Dutch on SF's pairs at "
                                              "today's distances. The High case at full network sits above it where a grade's own "
                                              "constant is above its level's reference (TK, K), since that extra part is kept."},
                 "rule": "lambda x caseD x max(0, on_v - on_today); caseD = Go Dutch shift - the level's SF reference"}


# -- outcome metrics ----------------------------------------------------------------

BUS_EXTRA_MIN = 10.0      # a yellow bus's stops on the way: our assumption
# The tally basis (module docstring). The 2024-25 Travel Tally's overall family-car share (SF Safe Routes to School,
# 2024-25 Annual Report, pp. 40-41; data/school-car-share/inputs.json, family_car_all_grades_2024_25) and its
# respondent weights: its overall mix (car 48.6, walk 18.1, bike 2.0, carpool 3.9, transit 26.8) fit to its grade bars
# (p. 42) by non-negative least squares with the weights summing to 1, largest error 0.026 points
# (notes/school-trips-2026-10/2026-10-09-sim-calibration.md).
TALLY_CAR = 48.6
TALLY_WEIGHTS = {"K": 0.212, "5": 0.373, "6": 0.148, "9": 0.232, "mixed": 0.034}
BANDS = ("K-5", "6-8", "9-12")
_tw = TALLY_WEIGHTS["K"] + TALLY_WEIGHTS["5"] + TALLY_WEIGHTS["6"] + TALLY_WEIGHTS["9"]   # mixed spread in proportion
TALLY_BAND_W = {"K-5": round((TALLY_WEIGHTS["K"] + TALLY_WEIGHTS["5"]) / _tw, 4), "6-8": round(TALLY_WEIGHTS["6"] / _tw, 4),
                "9-12": round(TALLY_WEIGHTS["9"] / _tw, 4)}
BAND_IX = np.array([BANDS.index(BAND_OF[g]) for g in GRADES])


def tally_fit_err(tg):
    """The largest gap, in points, between the tally's overall mix and its grade bars under TALLY_WEIGHTS."""
    ov = json.load(open(os.path.join(ROOT, "data", "school-car-share", "inputs.json")))["measured"]
    want = dict(ov["other_modes_2024_25"], car=ov["family_car_all_grades_2024_25"]["value"])
    return round(max(abs(sum(w * tg[k][m] for k, w in TALLY_WEIGHTS.items()) - want[m])
                     for m in ("car", "walk", "bike", "carpool", "transit")), 3)
SOLO = {"walkGrade": 3, "bikeGrade": 3, "transitGrade": 6, "busGrade": 0, "maxMin": 15.0, "gapTotalFt": 1000.0}
CRASHES = os.path.join(ROOT, "out", "school-hour-crashes", "schools.json")


def solo_ok(C, bike_min, gap):
    """(cells x 6) whether the mode is one the student could take without a caregiver: SOLO, our assumption."""
    ok = np.zeros((len(C["n"]), 6), dtype=bool)
    near = gap <= SOLO["gapTotalFt"]
    ok[:, WALK] = (C["gnum"] >= SOLO["walkGrade"]) & (C["walk_min"] <= SOLO["maxMin"]) & near
    ok[:, BIKE] = (C["gnum"] >= SOLO["bikeGrade"]) & (bike_min <= SOLO["maxMin"]) & near
    ok[:, TRANSIT] = C["gnum"] >= SOLO["transitGrade"]
    # A yellow bus carries a child of any grade without a caregiver (Bryan, 2026-10-10: "Please fix all the issues").
    ok[:, BUS] = C["gnum"] >= SOLO["busGrade"]
    return ok


def safe_ok(C, bike_min, gap):
    """(cells x 6) whether the mode is a safe trip of at most 15 minutes: walking or biking with the bike route's
    total gap at most SOLO's gapTotalFt, or Muni door to door in at most 15 minutes (muni_times, the grade's band)."""
    ok = np.zeros((len(C["n"]), 6), dtype=bool)
    near = gap <= SOLO["gapTotalFt"]
    ok[:, WALK] = (C["walk_min"] <= SOLO["maxMin"]) & near
    ok[:, BIKE] = (bike_min <= SOLO["maxMin"]) & near
    ok[:, TRANSIT] = C["transit_min"] <= SOLO["maxMin"]
    return ok


def mode_minutes(C, bike_min):
    return np.stack([C["car_min"], C["carpool_min"], C["walk_min"], bike_min, C["transit_min"],
                     C["car_min"] + BUS_EXTRA_MIN], axis=1)


def weighted_median(group, value, weight, ng):
    """Per group, the weighted median of value."""
    o = np.lexsort((value, group))
    g, v, w = group[o], value[o], weight[o]
    cw = np.cumsum(w)
    start = np.searchsorted(g, np.arange(ng), side="left")
    end = np.searchsorted(g, np.arange(ng), side="right")
    base = np.where(start > 0, cw[np.maximum(start - 1, 0)], 0.0)
    tot = np.where(end > start, cw[np.maximum(end - 1, 0)] - base, 0.0)
    out = np.full(ng, np.nan)
    for k in np.flatnonzero(tot > 0):
        i = start[k] + int(np.searchsorted(cw[start[k]:end[k]] - base[k], tot[k] / 2.0, side="left"))
        out[k] = v[min(i, end[k] - 1)]
    return out


class Medians(object):
    """Weighted medians of fixed values (cells x modes) under changing weights: the sort is done once, so each
    case costs a cumulative sum rather than a sort of every cell."""

    def __init__(self, sch, M, ng):
        grp = np.repeat(sch, M.shape[1])
        v = M.ravel()
        # int32 orders and no kept group column: at 2.97M cells x 6 modes each int64 array is 143 MB (2026-10-18).
        self.o = np.lexsort((v, grp)).astype(np.int32)
        g = grp[self.o]
        self.v = v[self.o]
        self.start = np.searchsorted(g, np.arange(ng), side="left")
        self.end = np.searchsorted(g, np.arange(ng), side="right")
        del g
        self.oc = np.argsort(v, kind="stable").astype(np.int32)
        self.vc = v[self.oc]
        self.ng = ng

    def __call__(self, w):
        w = w.ravel()
        cw = np.cumsum(w[self.o])
        out = np.full(self.ng, np.nan)
        for k in range(self.ng):
            a, b = self.start[k], self.end[k]
            if b <= a:
                continue
            base = cw[a - 1] if a > 0 else 0.0
            tot = cw[b - 1] - base
            if tot <= 0:
                continue
            i = a + int(np.searchsorted(cw[a:b] - base, tot / 2.0, side="left"))
            out[k] = self.v[min(i, b - 1)]
        cc = np.cumsum(w[self.oc])
        i = int(np.searchsorted(cc, cc[-1] / 2.0, side="left"))
        return out, float(self.vc[min(i, len(self.vc) - 1)])


def outcomes(C, pr, ns, M, ok, sok, bike_mi, med=None, acc=None):
    """Per school (and, last, citywide): shares by mode, median trip minutes, share going without a caregiver,
    share on a safe trip of 15 minutes or less, family-car miles and walk-plus-bike miles of the expected trips."""
    n = C["n"]
    sch = C["school"]
    w = (n[:, None] * pr)
    if med is None:
        med = Medians(sch, M, ns)
    med, med_city = med(w)
    N = np.bincount(sch, weights=n, minlength=ns)
    # Students whose trip needs no parent: acc when the caller tracked it (see track_acc), else the trip they chose.
    solo = np.bincount(sch, weights=n * acc.sum(axis=1) if acc is not None else (w * ok).sum(axis=1), minlength=ns)
    car_mi = car_miles(C["car_min"])
    # A carpool carries two children, so half its miles count per child: our assumption.
    cm = np.bincount(sch, weights=n * (pr[:, CAR] + pr[:, POOL] / 2.0) * car_mi, minlength=ns)
    am = np.bincount(sch, weights=n * (pr[:, WALK] * C["walk_mi"] + pr[:, BIKE] * bike_mi), minlength=ns)
    sf = np.bincount(sch, weights=(w * sok).sum(axis=1), minlength=ns)
    by = np.stack([np.bincount(sch, weights=w[:, m], minlength=ns) for m in range(6)], axis=1)
    share = np.vstack([100 * by / np.maximum(N, 1e-12)[:, None], 100 * by.sum(axis=0) / N.sum()])
    # Family-car students by school and grade band, and the city's students per band, for the tally basis.
    bi = BAND_IX[C["grade"]]
    band_car = np.zeros((ns, len(BANDS)))
    band_n = np.zeros(len(BANDS))
    for k in range(len(BANDS)):
        m = bi == k
        band_car[:, k] = np.bincount(sch[m], weights=w[m, CAR], minlength=ns)
        band_n[k] = n[m].sum()
    return {"share": share, "bandCar": band_car, "bandN": band_n, "medianMin": np.r_[med, med_city], "soloPct": np.r_[100 * solo / N, 100 * solo.sum() / N.sum()],
            "safeTripPct": np.r_[100 * sf / N, 100 * sf.sum() / N.sum()],
            "carMiles": np.r_[cm, cm.sum()], "activeMiles": np.r_[am, am.sum()], "students": np.r_[N, N.sum()]}


def crashes_today(grav, sch):
    """Injury crashes within 600 ft of each school at its own bell hours on school days (tools/school-trips/school-hour-crashes.py)."""
    if not os.path.exists(CRASHES):
        return {}, []
    rows = json.load(open(CRASHES))
    by_name = {r["name"]: r for r in rows if not r.get("private")}
    priv_name = {r["name"]: r for r in rows if r.get("private")}
    tok = [(grav._tokens(r["name"]), r) for r in by_name.values()]
    out, miss = {}, []
    for s in sch:
        r = priv_name.get(s[1]) if is_private(s) else by_name.get(s[1])   # a private school by its exact name only
        if r is None and not is_private(s):
            want = grav._tokens(s[1])
            sc = sorted(((len(want & t) / float(max(len(want), len(t), 1)), i) for i, (t, _r) in enumerate(tok)), reverse=True)
            if sc and sc[0][0] >= 0.6 and (len(sc) == 1 or sc[1][0] < sc[0][0]):
                r = tok[sc[0][1]][1]
        if r is None:
            miss.append(s[1])
            continue
        c = r["600ft"]
        out[s[0]] = {"injuryCrashes": c["window"], "severeOrFatal": c["window_severe_fatal"], "pedOrBike": c["window_ped_or_bike_crash"],
                     "childPedBike": c["window_child_ped"] + c["window_child_bike"], "crashFileName": r["name"]}
    return out, sorted(miss)


def ebike_minutes(bike_min):
    """Door-to-door bike minutes on an e-bike: the riding part CHANGES["ebike"]["faster"] quicker, the fixed minutes kept."""
    fixed = BIKE_GOOGLE_MIN + BIKE_FIXED_MIN
    return (bike_min - fixed) * (1 - CHANGES["ebike"]["faster"]) + fixed


def switch_ok(C, bike_min, gap):
    p = CHANGES["bike_switch"]
    return (bike_min - C["car_min"] <= p["within_min"]) & (gap <= p["gap_total_ft"])


def ebike_gate(C, gap):
    """Per cell, whether its school gets e-bike help on this network: more than half of the school's students living
    within EBIKE_GATE_MI on foot have a bike route whose total gap passes the bike switch's gap test."""
    ns = int(C["school"].max()) + 1
    near = C["n"] * (C["walk_mi"] <= EBIKE_GATE_MI)
    good = near * (gap <= CHANGES["bike_switch"]["gap_total_ft"])
    a = np.bincount(C["school"], weights=good, minlength=ns)
    b = np.bincount(C["school"], weights=near, minlength=ns)
    return (a > 0.5 * np.maximum(b, 1e-9))[C["school"]]


def base_choice(C, ns, c, cache):
    """Today's choice under a combination's non-network changes: the student-level moves first (caregiver Muni,
    then the yellow bus), then School Street's per-school shift on what they leave, as "all" orders them."""
    k = (c["caregiver_muni"], c["yellow_bus"], c["school_street"])
    if k not in cache:
        cache[k], cache[("acc",) + k] = chain([nm for nm in ("caregiver_muni", "yellow_bus", "school_street") if c[nm]],
                                             C["pr"], C, ns, CHANGES)
    return cache[k]


def base_acc(c, cache):
    """The no-parent share per cell and mode for base_choice's combination (call base_choice first)."""
    return cache[("acc", c["caregiver_muni"], c["yellow_bus"], c["school_street"])]


def evaluate(C, ns, v, pr_base, lam, md=None, acc=None, bike_min=None, gap=None, on=None):
    """One network variant on cells C, after a combination's other changes (pr_base): for each case, the year-10
    outcomes. Each cell's bike logit moves by lambda[case] x caseD x the rise in its route's on-network share over
    today's (case_shift), the other modes scaled in proportion; School Street and the programs apply first. A cell with
    no new route doesn't move. bike_min, gap and on override the variant's (the ranked bikeway blocks)."""
    bike_min = C["bike_min_" + v] if bike_min is None else bike_min
    gap = C["gap_" + v] if gap is None else gap
    gain = np.maximum((C["on_" + v] if on is None else on) - C["on_today"], 0.0)
    M = mode_minutes(C, bike_min)
    ok, sok = solo_ok(C, bike_min, gap), safe_ok(C, bike_min, gap)
    bmi = bike_miles(bike_min)
    md = md or Medians(C["school"], M, ns)
    out = []
    for k in CASES:
        pr = shift_bike(pr_base, lam[k] * C["caseD"] * gain)
        out.append(outcomes(C, pr, ns, M, ok, sok, bmi, md, acc))
    return out, float((C["n"] * (gain > 0)).sum())


def crash_base(crash, sch):
    inj = np.array([float(crash.get(s[0], {}).get("injuryCrashes", np.nan)) for s in sch])
    sev = np.array([float(crash.get(s[0], {}).get("severeOrFatal", np.nan)) for s in sch])
    f = CRASH_YEARS_SHOWN / float(CRASH_YEARS_COVERED)
    return np.r_[inj, np.nansum(inj)] * f, np.r_[sev, np.nansum(sev)] * f


def measures(o, base, j):
    """The figures for one school (or the city, j = ns) from an outcomes() result, against today's (base)."""
    r = {m: round(float(o["share"][j, i]), 2) for i, m in enumerate(MODES)}
    r["medianMin"] = round(float(o["medianMin"][j]), 1)
    r["noCaregiverPct"] = round(float(o["soloPct"][j]), 2)
    r["safeTripPct"] = round(float(o["safeTripPct"][j]), 2)
    t = base["out"]
    f = float(o["carMiles"][j] / t["carMiles"][j]) if t["carMiles"][j] > 0 else 1.0
    r["carMilesChangePct"] = round(100 * (f - 1), 2)
    r["walkBikeMilesChangePct"] = round(100 * float(o["activeMiles"][j] / t["activeMiles"][j] - 1), 2) if t["activeMiles"][j] > 0 else None
    inj, sev = base["inj"][j], base["sev"][j]
    r["injuryCrashes5y"] = None if not np.isfinite(inj) else round(float(inj) * f, 2)
    r["severeOrFatal5y"] = None if not np.isfinite(sev) else round(float(sev) * f, 2)
    # The tally basis: this school's part of the citywide change, in points, each band's change in family-car students
    # over the city's students in that band (today's whole-city run, so a one-school subset uses the city's too),
    # weighted by TALLY_BAND_W. Summed over schools it is the city's change.
    ns = o["bandCar"].shape[0]
    dc = (o["bandCar"].sum(axis=0) - t["bandCar"].sum(axis=0)) if j == ns else (o["bandCar"][j] - t["bandCar"][j])
    pts = 100 * sum(TALLY_BAND_W[b] * dc[k] / t["bandN"][k] for k, b in enumerate(BANDS) if t["bandN"][k] > 0)
    r["carTallyPts"] = round(float(pts), 2 if j == ns else 5)
    if j == ns:
        r["carTally"] = round(TALLY_CAR + float(pts), 2)
        for k, key in enumerate(BAND_KEYS):
            r[key] = round(100 * float(o["bandCar"][:, k].sum() / t["bandN"][k]), 4)
    return r


MEASURES = MODES + ["medianMin", "noCaregiverPct", "safeTripPct", "carMilesChangePct", "walkBikeMilesChangePct",
                    "injuryCrashes5y", "severeOrFatal5y", "carTallyPts"]
BAND_KEYS = ("carK5", "car68", "car912")   # the city's family-car share in each grade band, for the tally-basis check
CITY_MEASURES = MEASURES + ["carTally"] + list(BAND_KEYS)


def muni_eligibility_change(C):
    """Students whose caregiver-Muni eligibility (Muni within within_min of the car, TK-8) differs between the Google-
    calibrated car times and the routed ones before calibration: only the car was re-timed, so eligibility widens."""
    p = CHANGES["caregiver_muni"]
    young = C["gnum"] <= p["max_grade"]
    now = young & (C["transit_min"] - C["car_min"] <= p["within_min"])
    before = young & (C["transit_min"] - car_routed(C["car_min"]) <= p["within_min"])
    n = C["n"]
    return {"muniEligibleStudents": round(float((n * now).sum())), "muniEligibleBeforeCalibration": round(float((n * before).sum())),
            "muniNewlyEligible": round(float((n * (now & ~before)).sum())), "muniNoLongerEligible": round(float((n * (before & ~now)).sum())),
            "muniNewlyEligibleDriven": round(float((n * C["pr"][:, CAR] * (now & ~before)).sum())),
            "note": "Transit times are scheduled Muni door-to-door times (muni_times); the K-5 Muni share by distance band "
                    "against SFCTA 2016 Fig. 3 is byDistance's transit."}


def tally_recompute_err(city):
    """The largest gap, in points, between city.json's carTally and 48.6 plus TALLY_BAND_W times each band's change
    against today, recomputed from the written band shares, over every grid cell, case and lever."""
    t = city["levers"]["today"]
    base = [t[k] for k in BAND_KEYS]

    def calc(v):
        return TALLY_CAR + sum(TALLY_BAND_W[b] * (v[k] - base[i]) for i, (b, k) in enumerate(zip(BANDS, BAND_KEYS)))
    errs = [abs(v["carTally"] - calc(v)) for v in city["levers"].values()]
    for by in city["grid"].values():
        ms = by["0"]
        errs += [abs(ms["carTally"][i] - calc({k: ms[k][i] for k in BAND_KEYS})) for i in range(len(ms["carTally"]))]
    return max(errs)


def grid(C, T, sch, crash, lam):
    """{school index or 'city': {combo key: {blocks n: {measure: [value per case, CASES order]}}}}, plus the levers."""
    ns = len(sch)
    inj, sev = crash_base(crash, sch)
    M0 = mode_minutes(C, C["bike_min_today"])
    bmi0 = bike_miles(C["bike_min_today"])
    md0 = Medians(C["school"], M0, ns)
    mds = {"today": md0}
    today = outcomes(C, C["pr"], ns, M0, solo_ok(C, C["bike_min_today"], C["gap_today"]),
                     safe_ok(C, C["bike_min_today"], C["gap_today"]), bmi0, md0)
    base = {"out": today, "inj": inj, "sev": sev}
    cache = {}
    res = {j: {} for j in list(range(ns)) + ["city"]}
    newly = {}
    for c in COMBOS:
        v = variant_of(c)
        if v not in mds:
            # one network's Medians at a time beside today's (about 430 MB each at full size); COMBOS revisits each
            # network once more with School Street on, so that costs one more sort per network
            for k in [k for k in mds if k != "today"]:
                del mds[k]
            mds[v] = Medians(C["school"], mode_minutes(C, C["bike_min_" + v]), ns)
        outs, nnew = evaluate(C, ns, v, base_choice(C, ns, c, cache), lam, mds[v], base_acc(c, cache))
        newly[combo_key(c)] = round(nnew, 1)
        for j in list(range(ns)) + ["city"]:
            jj = ns if j == "city" else j
            ms = [measures(o, base, jj) for o in outs]
            res[j].setdefault(combo_key(c), {})["0"] = {m: [x[m] for x in ms] for m in (CITY_MEASURES if j == "city" else MEASURES)}
    # The ranked bikeway blocks, at the case-study schools that have them.
    xb = T.get("_xb", {})
    for j in range(ns):
        if not any(k.startswith("%d|" % j) for k in xb):
            continue
        m = C["school"] == j
        Cj = {k: (v[m] if isinstance(v, np.ndarray) and v.shape[:1] == C["n"].shape else v) for k, v in C.items()}
        mdj = {}
        for c in COMBOS:
            v = variant_of(c)
            for nb_n in BLOCK_NS[1:]:
                kb, kg = "%d|%s_b%d|bike" % (j, v, nb_n), "%d|%s_b%d|gap" % (j, v, nb_n)
                if kb not in xb:
                    continue
                bm = bike_minutes(xb[kb])[Cj["b"]]
                gp = xb[kg][Cj["b"]]
                ko = "%d|%s_b%d|on" % (j, v, nb_n)
                bmet = np.maximum(xb[kb][Cj["b"]].astype(float), 1.0)
                on = np.clip((xb[ko][Cj["b"]] if ko in xb else bmet - gp * FT) / bmet, 0.0, 1.0)
                if (v, nb_n) not in mdj:
                    mdj[(v, nb_n)] = Medians(Cj["school"], mode_minutes(Cj, bm), ns)
                pb, ab = base_choice(C, ns, c, cache), base_acc(c, cache)
                outs, _n = evaluate(Cj, ns, v, pb[m], lam, mdj[(v, nb_n)], ab[m], bike_min=bm, gap=gp, on=on)
                ms = [measures(o, base, j) for o in outs]
                res[j][combo_key(c)][str(nb_n)] = {mm: [x[mm] for x in ms] for mm in MEASURES}
    # The other levers, alone and together, on today's network.
    lev = {j: {} for j in list(range(ns)) + ["city"]}
    for sc, chg in SCENARIOS.items():
        pr, acc = chain(chg, C["pr"], C, ns, CHANGES)
        o = outcomes(C, pr, ns, M0, solo_ok(C, C["bike_min_today"], C["gap_today"]),
                     safe_ok(C, C["bike_min_today"], C["gap_today"]), bmi0, md0, acc)
        for j in list(range(ns)) + ["city"]:
            lev[j][sc] = measures(o, base, ns if j == "city" else j)
    # Every lever together, then Calm Streets and the connector at every school under each case, citywide only:
    # the headline's "all five programs plus the streets" (the grid's toggles hold three of the five programs).
    pr_all, acc_all = chain(SCENARIOS["all"], C["pr"], C, ns, CHANGES)
    outs, _n = evaluate(C, ns, "both", pr_all, lam, mds.get("both"), acc_all)
    ms = [measures(o, base, ns) for o in outs]
    lev["city"]["_allPlusStreets"] = {m: [x[m] for x in ms] for m in CITY_MEASURES}
    err = max(float(np.abs(v.sum(axis=1) - 1).max()) for k, v in cache.items() if k[0] != "acc")
    return res, lev, newly, err


# -- validation -------------------------------------------------------------------

def by_grade(grav_g, mins, asc, beta, targets, kind):
    """Every grade's modelled car and bike shares against their targets, and the citywide car figure."""
    bus, _take = bus_targets(grav_g, mins)
    out = {}
    car = n = 0.0
    for gr in grav_g:
        G = grav_g[gr]
        pr = probs(mins, G["cols"], gr, asc[gr], beta)
        sh = (pr * G["T"][:, :, None]).sum(axis=(0, 1)) / G["T"].sum()
        tg = targets[gr]
        out[gr] = {"model": round(100 * float(sh[CAR]), 2), "target": round(100 * float(tg[CAR]) * (1 - bus[gr]), 2),
                   "tally": round(100 * float(tg[CAR]), 2), "bikeModel": round(100 * float(sh[BIKE]), 3),
                   "bikeTarget": round(100 * float(tg[BIKE]) * (1 - bus[gr]), 3), "bus": round(100 * float(sh[BUS]), 2),
                   "busTarget": round(100 * bus[gr], 2), "kind": kind[gr], "students": int(round(float(G["D"].sum()))),
                   "maxModeErrPts": round(100 * float(np.abs(sh - np.r_[tg[[CAR, POOL, WALK, BIKE, TRANSIT]] * (1 - bus[gr]), bus[gr]]).max()), 5),
                   "bikeShift": round(float(asc[gr][BIKE]), 4)}
        car += float(sh[CAR]) * float(G["D"].sum())
        n += float(G["D"].sum())
    return out, round(100 * car / n, 2)


def curve_citywide(grav_g, targets):
    """The car-share curve weighted by enrolment by grade."""
    w = {g: float(grav_g[g]["D"].sum()) for g in grav_g}
    return round(100 * sum(w[g] * float(targets[g][0]) for g in grav_g) / sum(w.values()), 2)


# The step-1 gate (notes/school-trips-2026-10/2026-10-18-step1-nested-choice.md): K-5 drive-alone share within
# BAND_GATE_PTS of SFCTA 2016 Fig. 3 in every band, and under WALK_OVER2_MAX_PCT of K-5 students over 2 miles walking.
BAND_GATE_PTS = 3.0
WALK_OVER2_MAX_PCT = 2.0


def cts_bands():
    """SFCTA 2016 Fig. 3's K-5 drive-alone and public-transit shares by band, over 2 miles weighted by Fig. 7's parents."""
    rows = json.load(open(os.path.join(ROOT, "data", "school-car-share", "inputs.json")))["measured"]["k5_driven_by_distance_2016"]["bands"]
    out = {}
    for key, band in (("under1", "under_1"), ("1to2", "1_to_2"), ("over2", "over_2")):
        rr = [r for r in rows if r["band"] == band]
        w = float(sum(r["parents_pct"] for r in rr))
        out[key] = {"car": round(sum(r["driven_pct"] * r["parents_pct"] for r in rr) / w, 1),
                    "transit": round(sum(r["transit_pct"] * r["parents_pct"] for r in rr) / w, 1)}
    return out


def by_distance(grav_g, mins, T, asc, beta):
    """K-5 (no TK) family-car and Muni shares by walking-distance band against SFCTA 2016, the share of K-5 students
    over 2 miles who walk, and whether the step-1 gate passes."""
    mix = np.zeros((3, 6))
    n = np.zeros(3)
    far_walk = far_n = 0.0
    for gr in grav_g:
        if GNUM[gr] > 5 or gr == "TK":
            continue
        G = grav_g[gr]
        pr = probs(mins, G["cols"], gr, asc[gr], beta)
        w = T["walk"][:, G["cols"]] / MI
        band = np.where(w < 1, 0, np.where(w < 2, 1, 2))
        for k in range(3):
            m = (band == k) * G["T"]
            mix[k] += (pr * m[:, :, None]).sum(axis=(0, 1))
            n[k] += float(m.sum())
        far = (w > 2) * G["T"]
        far_walk += float((pr[:, :, WALK] * far).sum())
        far_n += float(far.sum())
    keys = ("under1", "1to2", "over2")
    cts = cts_bands()
    mx = 100 * mix / np.maximum(n, 1e-12)[:, None]
    out = {k: round(float(mx[i, CAR]), 1) for i, k in enumerate(keys)}
    out["transit"] = {k: round(float(mx[i, TRANSIT]), 1) for i, k in enumerate(keys)}
    out["mix"] = {k: {m: round(float(mx[i, j]), 1) for j, m in enumerate(MODES)} for i, k in enumerate(keys)}
    out["walkOver2Pct"] = round(100 * far_walk / max(far_n, 1e-12), 2)
    out["carMaxMissPts"] = round(max(abs(out[k] - cts[k]["car"]) for k in keys), 2)
    out["transitMaxMissPts"] = round(max(abs(out["transit"][k] - cts[k]["transit"]) for k in keys), 2)
    out["gate"] = {"carWithinPts": BAND_GATE_PTS, "walkOver2MaxPct": WALK_OVER2_MAX_PCT,
                   "pass": bool(out["carMaxMissPts"] <= BAND_GATE_PTS and out["walkOver2Pct"] < WALK_OVER2_MAX_PCT)}
    out["studentsPct"] = {k: round(100 * float(n[i] / n.sum()), 1) for i, k in enumerate(keys)}
    return out


def _wmedian(x, w):
    o = np.argsort(x, kind="stable")
    cw = np.cumsum(w[o])
    return float(x[o][min(int(np.searchsorted(cw, cw[-1] / 2.0)), len(o) - 1)]) if len(o) else None


def bike_curve_check(C, how):
    """The bike curve's inputs by PCT level: student-weighted median route km and gradient, the share of students at
    the gradient cap and past the curve's fit limits (5 km primary, 10 km secondary), and where the gradient came from."""
    out = {"gradient": how, "gradCapPct": GRAD_CAP_PCT}
    for lv, name, lim in ((0, "primary", 5.0), (1, "secondary", 10.0)):
        m = C["level"] == lv
        n = C["n"][m]
        if not m.any():
            continue
        out[name] = {"students": round(float(n.sum())), "medianKm": round(_wmedian(C["bike_km"][m], n), 2),
                     "medianGradPct": round(_wmedian(C["grad"][m], n), 2),
                     "atCapPct": round(100 * float(n[C["grad"][m] >= GRAD_CAP_PCT].sum() / n.sum()), 1),
                     "pastFitLimitPct": round(100 * float(n[C["bike_km"][m] > lim].sum() / n.sum()), 1)}
    return out


# V2, the back-cast (plan, Validation): the 2019-20 tally's bike share was 1% and 2024-25's 2.0%, both rounded, so the
# measured change is 0 to 2.5 points (data/school-car-share/inputs.json) on a strict all-ages network that grew from
# 104.9 to 169.8 miles (site/data/bike-history/history.json). A case predicting more is wrong.
BACKCAST_BAND_PTS = (0.0, 2.5)


def backcast(C, lam):
    """V2: each case's year-10 change in all students' bike share, from the 2019 network (y2019) to today's built one
    (built, without the upcoming bikeways), with today's students and times; signed, so a route that loses on-network
    metres counts. Needs a trip run carrying both variants' on-network metres."""
    if "on_y2019" not in C or "on_built" not in C:
        return {"status": "not run: needs a trip run with the built and y2019 network variants", "bandPts": list(BACKCAST_BAND_PTS)}
    n = C["n"]
    out = {"bandPts": list(BACKCAST_BAND_PTS), "cases": {},
           "studentsWithGainPct": round(100 * float((n * (C["on_built"] > C["on_y2019"])).sum() / n.sum()), 1)}
    for k in CASES:
        b = shift_bike(C["pr"], lam[k] * C["caseD"] * (C["on_built"] - C["on_today"]))
        a = shift_bike(C["pr"], lam[k] * C["caseD"] * (C["on_y2019"] - C["on_today"]))
        d = 100 * float((n * (b[:, BIKE] - a[:, BIKE])).sum() / n.sum())
        out["cases"][k] = {"bikePts": round(d, 3), "pass": bool(BACKCAST_BAND_PTS[0] <= d <= BACKCAST_BAND_PTS[1])}
    return out


def car_cost_check(C, ns):
    """V4 for the car-cost lever: the citywide family-car change at each charge (central value of time) and at each
    value of time (central charge), and a test against CHILL (inputs.json london_ulez): among driven children in grades
    1 to 4 (the study's ages 6 to 9), the share the ULEZ charge moves off the family car when it falls on the
    non-compliant share of cars, beside CHILL's London-over-Luton gap and its odds ratio's range (ULEZ_GAP_PTS). The
    value of time and the trip split were set without looking at it. CHILL counts transit as active, and our figure
    counts every mode but the family car."""
    p = CHANGES["car_cost"]
    n, pr = C["n"], C["pr"]
    car0 = float((n * pr[:, CAR]).sum())
    out = {"byCharge": {}, "byValueOfTime": {}}
    for k, usd in p["usd_day"].items():
        pr1 = car_cost_shift(pr, C, usd, p["vot_usd_hr"]["central"])
        out["byCharge"][k] = {"usdDay": usd, "carPts": round(100 * (float((n * pr1[:, CAR]).sum()) - car0) / float(n.sum()), 2)}
    for k, vot in p["vot_usd_hr"].items():
        pr1 = car_cost_shift(pr, C, p["usd_day"]["central"], vot)
        out["byValueOfTime"][k] = {"votUsdHr": vot, "carPts": round(100 * (float((n * pr1[:, CAR]).sum()) - car0) / float(n.sum()), 2)}
    m = (C["gnum"] >= 1) & (C["gnum"] <= 4)
    d0 = float((n[m] * pr[m, CAR]).sum())
    vot = p["vot_usd_hr"]["central"]

    def gap(form, trips):
        pr1 = car_cost_shift(pr, C, ULEZ_USD_DAY, vot, form=form, trips=trips)
        off = 100 * (d0 - float((n[m] * pr1[m, CAR]).sum())) / max(d0, 1e-9)
        return round(ULEZ_NONCOMPLIANT * off, 1)
    rows = {"%s|%g" % (f, t): gap(f, t) for f in ("money", "logmin") for t in (1.0, CAR_COST_TRIPS, CAR_COST_TRIPS_ALT)}
    used = rows["%s|%g" % (CAR_COST_FORM, CAR_COST_TRIPS)]
    out["ulezTest"] = {"grades": "1-4", "chargeUsdDay": ULEZ_USD_DAY, "nonCompliantShare": ULEZ_NONCOMPLIANT,
                       "modelGapPts": used, "chillGapPts": list(ULEZ_GAP_PTS),
                       "pass": bool(ULEZ_GAP_PTS[0] <= used <= ULEZ_GAP_PTS[2]),
                       "byFormAndTrips": rows, "refCarMin": round(car_cost_tref(C), 1), "kind": "test",
                       "note": "points of driven grade 1-4 children leaving the family car at the ULEZ charge on the "
                               "non-compliant share of cars, against CHILL's London-over-Luton gap; keys are form|daily "
                               "vehicle trips the charge is split over (1 = the school trip pays it all)"}
    return out


def k5_lengths(grav_g, d):
    t = np.zeros(3)
    for gr in grav_g:
        if GNUM[gr] > 5 or gr == "TK":
            continue
        G = grav_g[gr]
        dd = d[:, G["cols"]]
        for k, m in enumerate((dd < 1, (dd >= 1) & (dd < 2), dd >= 2)):
            t[k] += float((G["T"] * m).sum())
    return {k: round(100 * float(t[i] / t.sum()), 1) for i, k in enumerate(("under1", "1to2", "over2"))}


def change_effects(eff, sch, ids):
    """At named schools: each change's applied effect against today, beside its study's."""
    out = {}
    ns = len(sch)
    for cid in ids:
        j = next((i for i, s in enumerate(sch) if s[6] == cid), None)
        if j is None:
            continue
        rows = {}
        for name in ORDER:
            d_car, d_act, d_tgt, elig = [], [], [], []
            for C in eff:
                m = C["school"] == j
                if not m.any():
                    continue
                pr0 = C["pr"][m]
                pr1 = apply_change(name, C["pr"], C, ns, CHANGES)[m]
                n = C["n"][m]
                N = n.sum()
                d_car.append(100 * float((n * (pr1[:, CAR] - pr0[:, CAR])).sum() / N))
                d_act.append(100 * float((n * (pr1[:, WALK] + pr1[:, BIKE] - pr0[:, WALK] - pr0[:, BIKE])).sum() / N))
                p = CHANGES[name]
                if name == "walking_bus":
                    t = (C["gnum"][m] <= p["max_grade"]) & (C["gnum"][m] >= p["min_grade"]) & (C["walk_mi"][m] <= p["within_mi"])
                elif name in ASSIGN:
                    t = (C["gnum"][m] <= p["max_grade"]) & C["sfusd"][m]
                elif name in ("safer_crossings", "school_street"):
                    t = C["gnum"][m] <= p["max_grade"]
                elif name == "bike_switch":
                    t = (C["bike_min"][m] - C["car_min"][m] <= p["within_min"]) & (C["gap_total_ft"][m] <= p["gap_total_ft"])
                elif name == "caregiver_muni":
                    t = (C["transit_min"][m] - C["car_min"][m] <= p["within_min"]) & (C["gnum"][m] <= p["max_grade"])
                elif name == "yellow_bus":
                    t = (C["walk_mi"][m] > p["over_mi"]) & (C["gnum"][m] <= p["max_grade"])
                else:
                    t = np.ones(m.sum(), dtype=bool)
                nt = n[t].sum()
                elig.append(100 * float(nt / N))
                if nt > 0:
                    if name in ("walking_bus", "safer_crossings"):
                        d_tgt.append(100 * float((n[t] * (pr1[t, WALK] + pr1[t, BIKE] - pr0[t, WALK] - pr0[t, BIKE])).sum() / nt))
                    elif name == "yellow_bus":
                        # car trips removed per new rider: the lever model's 59% is this figure
                        riders = float((n[t] * (pr1[t, BUS] - pr0[t, BUS])).sum())
                        d_tgt.append(100 * float((n[t] * (pr0[t, CAR] - pr1[t, CAR])).sum()) / max(riders, 1e-9))
                    else:
                        d_tgt.append(100 * float((n[t] * (pr1[t, CAR] - pr0[t, CAR])).sum() / nt))
            r = {"carPts": round(float(np.mean(d_car)), 2), "walkBikePts": round(float(np.mean(d_act)), 2),
                 "targetedPct": round(float(np.mean(elig)), 1), "study": CHANGES[name]["study"], "src": CHANGES[name]["src"]}
            if d_tgt:
                key = {"walking_bus": "walkBikePtsAmongTargeted", "safer_crossings": "walkBikePtsAmongTargeted",
                       "yellow_bus": "riderCarPct"}.get(name, "carPtsAmongTargeted")
                r[key] = round(float(np.mean(d_tgt)), 2)
            rows[name] = r
        out[cid] = rows
    return out


# -- the home ZIP check ----------------------------------------------------------

ZIP_CSV = os.path.join(ROOT, "data", "sfusd-residence", "zip-by-school-2025-26.csv")
ZIP_SCHOOLS_CSV = os.path.join(ROOT, "data", "sfusd-residence", "schools-2025-26.csv")
ZIP_SRC = {"url": "https://public.tableau.com/views/SFUSDPublicDataDashboard/Story1",
           "what": "SFUSD Public Data Dashboard, Enrollment Overview (2025-26), Site-Level Enrollment by SF Zip Code",
           "read": "2026-10-08", "tag": "[primary — read 2026-10-08]", "script": "tools/school-trips/sfusd-residence-zip.py"}
# SFUSD home origins, method C of notes/school-trips-2026-10/2026-10-20-private-charter-home-locations.md (section 2):
# a block's origins for a level are its census children x its tract's public share of enrolled students for the level,
# then each SFUSD-run school's students are raked to the dashboard's home-ZIP counts per grade span (rake_to_zips).
# The tract shares are ACS 5-year 2020-2024 table B14002 by tract, 244 SF tracts, as data.census.gov's table API
# returned it on 2026-10-19 (https://data.census.gov/table/ACSDT5Y2024.B14002?g=050XX00US06075$1400000; copied from
# scratch/private-schools/raw/b14002_tract_5y2024.json). SCHOOL_SIM_ORIGINS=A keeps the citywide share and no rake
# (the method before 2026-10-19), B the tract share with no rake.
ACS_TRACTS = os.path.join(ROOT, "data", "school-sim", "acs-b14002-tracts-5y2024.json")
ORIGINS = os.environ.get("SCHOOL_SIM_ORIGINS", "C").upper()
# B14002 lines (male, female) for public and private enrolment by band.
B14002_LINES = {"K": ((8, 32), (9, 33)), "1-4": ((11, 35), (12, 36)), "5-8": ((14, 38), (15, 39)), "9-12": ((17, 41), (18, 42))}
# Each sim level as ACS bands: K-5 = K + 1-4 + a quarter of 5-8; 6-8 = three quarters of 5-8; 9-12.
LEVEL_BANDS = {"elementary": (("K", 1.0), ("1-4", 1.0), ("5-8", 0.25)), "middle": (("5-8", 0.75),), "high": (("9-12", 1.0),)}
ORIGIN_SHARE = None      # {level: per-block public share}, set by main() under method B or C; None is the citywide share
# Private schools are in the default run. Bryan, 2026-10-21: "Can we give private school students a distance
# distribution that's more like city wide schools in the SFUSD system like Lowell? And then let's fold all schools into
# the same simulation." SF's private schools come from data/school-sim/private-schools.json
# (scripts/school-private-schools.py: CDE affidavit 2025-26 plus 14 schools carried from 2024-25, points from DataSF
# 7e7j-59qk). Their origins are a block's children x its tract's private share (ACS B14002). Their reach, level by
# level, is the enrolment-weighted mean reach (stretch x REACH_CAL) of SFUSD's own citywide schools at that level
# (private_reach, PRIVATE_REF): grades TK-5 the SFUSD-run elementary schools with no attendance area (the citywide K-8s
# and program schools), grades 6-8 the SFUSD-run K-8 schools, grades 9-12 every SFUSD-run high school (all citywide
# choice, Lowell among them). The check school-sim/private-distance holds private students' mean straight-line trip at
# each level to PRIVATE_DIST_TOL of those schools' mean. SCHOOL_SIM_PRIVATE=0 runs SFUSD and charter schools only and
# writes out/school-sim-public/ and .cache/school-sim-public/site/, so the default outputs stay the published ones.
PRIVATE_RUN = os.environ.get("SCHOOL_SIM_PRIVATE", "1") != "0"
PRIVATE_JSON = os.path.join(ROOT, "data", "school-sim", "private-schools.json")
PRIVATE_DIST_TOL = 0.15   # private mean trip within 15% of the reference schools' mean, level by level: our tolerance
PRIVATE_MODE_NOTE = ("Assumed: no published source gives private-school students' modes by distance (SFCTA 2016 Table 3 "
                     "pools every school type). A private student chooses by the SFUSD model at its own trip times, with each "
                     "grade's SFUSD-calibrated constants, so its mode shares are SFUSD's baseline at the same distance and "
                     "times. That includes the walk limit and the yellow-bus rule (TK-8 over 2 miles), which SFUSD runs for its "
                     "own students only.")
ZIP_SUPPRESS = 5         # the dashboard leaves out a ZIP with fewer than five students; the model's copy does the same
SPAN_GRADES = {"TK-5": ("TK", "KN", "01", "02", "03", "04", "05"), "6-8": ("06", "07", "08"), "9-12": ("09", "10", "11", "12")}
SPAN_LEVEL = {"TK-5": "elementary", "6-8": "middle", "9-12": "high"}


def _zip_tokens(grav, name):
    import re
    n = re.sub(r"\b(sf|s\.f\.)\b", " ", name.lower())
    n = re.sub(r"\b(ees|es|ms|hs|k-8|cao|alternative|traditional|academic|elementary|middle|high|jr\.?|dr)\b", " ", n)
    return grav._tokens(n)


def zip_table(grav, sch):
    """The dashboard's students by home ZIP for each SFUSD school and grade span it reports, matched to our schools:
    {(school index, span): {"zips": {zip: n}, "enrolled": n, "placed": n, "name": dashboard name}}, and the names left unmatched."""
    import csv
    if not os.path.exists(ZIP_CSV):
        return {}, ["(no %s)" % os.path.relpath(ZIP_CSV, ROOT)]
    rows = list(csv.DictReader(open(ZIP_CSV)))
    tot = {}
    if os.path.exists(ZIP_SCHOOLS_CSV):
        for r in csv.DictReader(open(ZIP_SCHOOLS_CSV)):
            tot[(r["school"], r["grade_span"])] = (int(r["enrolled"]), int(r["placed"]))
    by = {}
    for r in rows:
        if r["grade_span"] not in SPAN_GRADES:
            continue
        k = (r["school"], r["grade_span"])
        d = by.setdefault(k, {"zips": {}, "enrolled": int(r["enrolled"]), "placed": int(r["placed"])})
        d["zips"][r["zip"]] = d["zips"].get(r["zip"], 0) + int(r["students"])
    match = name_matcher(grav, sch)
    out, miss = {}, []
    for (nm, span), d in sorted(by.items()):
        j = match(nm, SPAN_GRADES[span])
        if j is None:
            miss.append("%s (%s)" % (nm, span))
        elif (j, span) not in out or d["enrolled"] > out[(j, span)]["enrolled"]:
            # Two dashboard names can match one school: Stockton (Commodore) EES (20 students) and Sloat (Commodore)
            # Elementary (386) both match Sloat. The row with more students is the school's (pipeline review, 2026-10-19).
            out[(j, span)] = dict(d, name=nm)
    return out, miss


def name_matcher(grav, sch):
    """A function from an SFUSD school name (the dashboard's, or DataSF's synergy_na) and grades to our SFUSD-run
    school with students in those grades whose name shares at least half its words, if exactly one is best."""
    cand = [(j, _zip_tokens(grav, s[1])) for j, s in enumerate(sch) if not s[4] and not is_private(s)]

    def match(nm, gs):
        want = _zip_tokens(grav, nm)
        sc = sorted(((len(want & t) / float(max(len(want), len(t), 1)), j) for j, t in cand
                     if sum(sch[j][5].get(g, 0) for g in gs) > 0), reverse=True)
        if sc and sc[0][0] >= 0.5 and (len(sc) == 1 or sc[1][0] < sc[0][0]):
            return sc[0][1]
        return None
    return match


def tract_counts():
    """{tract: {band: {"pub": n, "priv": n}}} from ACS_TRACTS (B14002, male and female lines summed)."""
    B = json.load(open(ACS_TRACTS))["response"]["data"]
    out = {}
    for row in B[1:]:
        r = dict(zip(B[0], row))
        v = lambda ns: sum(int(r["B14002_%03dE" % n]) for n in ns)  # noqa: E731
        out[r["GEO_ID"][-11:]] = {b: {"pub": v(pu), "priv": v(pv)} for b, (pu, pv) in B14002_LINES.items()}
    return out


def origin_shares(blks):
    """({level: per-block public share of enrolled students}, {level: citywide share}): each block takes its tract's
    share, or the citywide one where the tract has fewer than 10 enrolled in the level's bands."""
    tc = tract_counts()
    city = {}
    for lvl, parts in LEVEL_BANDS.items():
        p = sum(tc[t][b]["pub"] * w for t in tc for b, w in parts)
        q = sum(tc[t][b]["priv"] * w for t in tc for b, w in parts)
        city[lvl] = p / (p + q)
    by = {}
    for t, bands in tc.items():
        by[t] = {}
        for lvl, parts in LEVEL_BANDS.items():
            p = sum(bands[b]["pub"] * w for b, w in parts)
            q = sum(bands[b]["priv"] * w for b, w in parts)
            by[t][lvl] = p / (p + q) if p + q >= 10 else city[lvl]
    out = {lvl: np.array([by.get(b["geoid"][:11], city)[lvl] for b in blks]) for lvl in LEVEL_BANDS}
    return out, city


def origins(grav, blks, lvl):
    """Each block's origin weight for a level: census children, times the tract's public share under method B or C."""
    O = np.array([grav.level_kids(b, lvl) for b in blks], dtype=float)
    return O * ORIGIN_SHARE[lvl] if ORIGIN_SHARE is not None else O


def rake_to_zips(grav_g, sch, zips, ztab, iters=200):
    """Method C (scratch/private-schools/fit_sfusd.py's rake). Per grade, each SFUSD-run school's students by home ZIP
    are set to the dashboard's shares for the ZIPs it lists (the rest, enrolled less listed, keep the gravity model's
    spread over the other ZIPs). Block origins move so each ZIP holds what those targets need plus the model's students
    there at schools with no dashboard row (charters, and the two high schools the dashboard doesn't match), spread
    within the ZIP as the model has them. Then rows, school x ZIP cells and free columns are raked to those margins,
    which agree. Returns new grade dicts and the largest row and column errors, in students."""
    zs = sorted(set(z for z in zips if z))
    zix = {z: k for k, z in enumerate(zs)}
    nz = len(zs) + 1                       # last slot: blocks with no ZIP
    zi = np.array([zix[z] if z else len(zs) for z in zips])
    M = np.zeros((len(zips), nz))
    M[np.arange(len(zips)), zi] = 1.0
    span_of = {g: sp for sp, gs in SPAN_GRADES.items() for g in gs}
    out, rerr, cerr = {}, 0.0, 0.0
    for gr, G in grav_g.items():
        span = span_of[gr]
        T = G["T"].copy()
        cols = list(G["cols"])
        D = G["D"]
        byz = M.T @ T                       # ZIP x school
        Ct = np.full((nz, len(cols)), np.nan)  # target cells; nan = free
        for c, j in enumerate(cols):
            dd = ztab.get((int(j), span))
            if not dd:
                continue
            listed = np.zeros(nz, dtype=bool)
            for z, n in dd["zips"].items():
                if z in zix:
                    Ct[zix[z], c] = D[c] * n / float(dd["enrolled"])
                    listed[zix[z]] = True
            rest = max(D[c] - np.nansum(Ct[:, c]), 0.0)
            other = byz[~listed, c]
            Ct[~listed, c] = rest * other / max(other.sum(), 1e-12)
        free = np.isnan(Ct).all(axis=0)
        Oz = np.nansum(Ct, axis=1) + byz[:, free].sum(axis=1)
        Ob = G["O"] * (Oz / np.maximum(M.T @ G["O"], 1e-12))[zi]
        for _ in range(iters):
            T *= (Ob / np.maximum(T.sum(axis=1), 1e-12))[:, None]
            byz = M.T @ T
            fac = np.where(np.isnan(Ct), 1.0, Ct / np.maximum(byz, 1e-12))
            T *= fac[zi, :]
            fr = T[:, free].sum(axis=0)
            T[:, free] *= (D[free] / np.maximum(fr, 1e-12))[None, :]
        rerr = max(rerr, float(np.abs(T.sum(axis=1) - Ob).max()))
        cerr = max(cerr, float(np.abs(T.sum(axis=0) - D).max()))
        out[gr] = dict(G, T=T, O=Ob)
    return out, rerr, cerr


def sfusd_k5(grav_g, d, sch):
    """K-5 (KN-05) straight-line bands and mean over SFUSD-run schools only, as Fig. 5 and Stanford count them."""
    t = np.zeros(3)
    num = den = 0.0
    for gr, G in grav_g.items():
        if gr == "TK" or GNUM[gr] > 5:
            continue
        keep = np.array([not sch[int(j)][4] and not is_private(sch[int(j)]) for j in G["cols"]])
        TT = G["T"][:, keep]
        dd = d[:, G["cols"][keep]]
        for k, m in enumerate((dd < 1, (dd >= 1) & (dd < 2), dd >= 2)):
            t[k] += float((TT * m).sum())
        num += float((TT * dd).sum())
        den += float(TT.sum())
    if den <= 0:
        return None
    return {"under1": round(100 * t[0] / t.sum(), 1), "1to2": round(100 * t[1] / t.sum(), 1),
            "over2": round(100 * t[2] / t.sum(), 1), "meanMi": round(num / den, 3)}


def is_private(s):
    """A private school's row carries an eighth field, "private" or "parochial"; SFUSD and charter rows have seven."""
    return len(s) > 7


def private_schools():
    """The private variant's schools as sim rows: (cds, name, lon, lat, False, grades, None, "parochial" or "private")."""
    doc = json.load(open(PRIVATE_JSON))
    return [(r["cds"], r["name"], r["lon"], r["lat"], False, dict(r["grades"]), None,
             "parochial" if r["parochial"] else "private") for r in doc["schools"]], doc


def private_ref(sch, masks):
    """{level: SFUSD-run school indexes} whose distance draw the private schools take (PRIVATE_RUN's note): TK-5, the
    elementary schools with no attendance area; 6-8, the K-8 schools; 9-12, every high school."""
    def has(s, grades):
        return any(s[5].get(g, 0) > 0 for g in grades)
    sf = [j for j, s in enumerate(sch) if not s[4] and not is_private(s)]
    return {"elementary": [j for j in sf if has(sch[j], SPAN_GRADES["TK-5"]) and j not in masks],
            "middle": [j for j in sf if has(sch[j], SPAN_GRADES["TK-5"]) and has(sch[j], SPAN_GRADES["6-8"])],
            "high": [j for j in sf if has(sch[j], SPAN_GRADES["9-12"])]}


def private_reach(grav, sch, city, ref, rc):
    """{level: one reach for every private school}: the enrolment-weighted mean of the reference schools' reaches at
    that level, each its stretch x rc (REACH_CAL), as gravity() draws them."""
    rps = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "requests-per-seat.json")))
    reach, med = grav.reaches(city, rps)
    out = {}
    for lvl, cols in ref.items():
        grades = [g for g in GRADES if LEVEL[g] == lvl]
        w = np.array([sum(sch[j][5].get(g, 0) for g in grades) for j in cols], dtype=float)
        st = _stretches(grav, sch, cols, lvl, reach, med, rc)
        out[lvl] = float((w * st).sum() / w.sum())
    return out


def level_mean_mi(grav_g, d, cols_by_level):
    """{level: students' mean straight-line miles} over the given school indexes' columns at that level's grades."""
    acc = {}
    for gr, G in grav_g.items():
        lvl = LEVEL[gr]
        want = set(cols_by_level.get(lvl, ()))
        keep = np.array([int(j) in want for j in G["cols"]])
        if not keep.any():
            continue
        T, dd = G["T"][:, keep], d[:, G["cols"][keep]]
        a = acc.setdefault(lvl, [0.0, 0.0])
        a[0] += float((T * dd).sum())
        a[1] += float(T.sum())
    return {k: round(v[0] / v[1], 3) for k, v in sorted(acc.items()) if v[1] > 0}


def private_gravity(grav, blks, sch, d, priv_share, reach):
    """Per grade, the private schools' doubly constrained matrices: origins are each block's children of the level x
    its tract's private share, scaled to the grade's private enrolment; the sim's curve at private_reach's reach for the
    level, so a private school draws as SFUSD's citywide schools at that level do. Each school's grade enrolment and
    the private origins are both met."""
    g = json.load(open(os.path.join(grav.ROOT, "data", "school-case", "gravity.json")))
    alpha, beta = g["fit"]["alpha"], g["fit"]["beta"]
    out = {}
    for gr in GRADES:
        lvl = LEVEL[gr]
        cols = [j for j, s in enumerate(sch) if is_private(s) and s[5].get(gr, 0) > 0]
        if not cols:
            continue
        D = np.array([sch[j][5][gr] for j in cols], dtype=float)
        O = np.array([grav.level_kids(b, lvl) for b in blks], dtype=float) * priv_share[lvl]
        O *= D.sum() / O.sum()
        st = np.full(len(cols), reach[lvl])
        F = grav.curve(d[:, cols] / st[None, :], alpha, beta)
        out[gr] = {"O": O, "cols": np.array(cols), "D": D, "T": grav.furness(O, D, F, iters=FURNESS_ITERS), "areaShare": {}}
    return out


def merge_grades(a, b):
    """Two sets of grade matrices over the same blocks as one: columns side by side, origins summed."""
    out = {}
    for gr in GRADES:
        if gr in a and gr in b:
            out[gr] = {"O": a[gr]["O"] + b[gr]["O"], "cols": np.r_[a[gr]["cols"], b[gr]["cols"]], "D": np.r_[a[gr]["D"], b[gr]["D"]],
                       "T": np.hstack([a[gr]["T"], b[gr]["T"]]), "areaShare": a[gr].get("areaShare", {})}
        elif gr in a:
            out[gr] = a[gr]
        # a grade only b has (only in a sample) has no calibrated constants, so its students are left out
    return out


def private_lengths(grav_g, d, sch):
    """Private students' straight-line distance bands by level, and K-5 by independent and parochial."""
    acc = {}
    for gr, G in grav_g.items():
        for c, j in enumerate(G["cols"]):
            s = sch[int(j)]
            if not is_private(s):
                continue
            lvl = LEVEL[gr]
            keys = [lvl] + (["elementary|" + s[7]] if lvl == "elementary" else [])
            for k in keys:
                a = acc.setdefault(k, np.zeros(5))
                T, dd = G["T"][:, c], d[:, int(j)]
                a += [float(T[dd < 1].sum()), float(T[(dd >= 1) & (dd < 2)].sum()), float(T[dd >= 2].sum()), float((T * dd).sum()), float(T.sum())]
    return {k: {"students": round(a[4]), "under1": round(100 * a[0] / a[4], 1), "1to2": round(100 * a[1] / a[4], 1),
                "over2": round(100 * a[2] / a[4], 1), "meanMi": round(a[3] / a[4], 3)} for k, a in sorted(acc.items()) if a[4] > 0}


def zip_centroids(blks, zips, kids):
    """Each ZIP's child-weighted centre (x, y in metres), from the blocks in it."""
    xy = np.array([GRAV_XY(b["lon"], b["lat"]) for b in blks])
    out = {}
    for z in sorted(set(zips) - {None}):
        m = np.array([q == z for q in zips])
        w = kids[m]
        out[z] = (xy[m] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-9)
    return out


def zip_fit(grav, blks, sch, grav_g, zips, table, cent):
    """Per matched school and span: the model's expected students by home ZIP beside the dashboard's.

    Both sides drop ZIPs under ZIP_SUPPRESS students (the model's scaled to the
    dashboard's enrolment), and each is then taken as shares of what is left.
    overlap is the sum over ZIPs of the smaller share, 100 when they agree
    exactly; sameTop5 counts the dashboard's five largest ZIPs among the
    model's five; meanMi compares the student-weighted distance from the
    school to each ZIP's child-weighted centre."""
    zix = {}
    for i, z in enumerate(zips):
        zix.setdefault(z, []).append(i)
    zs = sorted(z for z in zix if z)
    member = np.zeros((len(blks), len(zs)))
    for k, z in enumerate(zs):
        member[zix[z], k] = 1.0
    rows = {}
    for (j, span), d in sorted(table.items()):
        col = np.zeros(len(blks))
        for g in SPAN_GRADES[span]:
            G = grav_g.get(g)
            if G is None or j not in G["cols"]:
                continue
            col += G["T"][:, int(np.flatnonzero(G["cols"] == j)[0])]
        if col.sum() <= 0:
            continue
        mz = dict(zip(zs, (col @ member) / col.sum() * d["enrolled"]))
        mz = {z: v for z, v in mz.items() if v >= ZIP_SUPPRESS}
        dz = {z: float(v) for z, v in d["zips"].items() if z in cent}
        if not mz or not dz:
            continue
        ms, ds = sum(mz.values()), sum(dz.values())
        allz = sorted(set(mz) | set(dz))
        ov = sum(min(mz.get(z, 0) / ms, dz.get(z, 0) / ds) for z in allz)
        sx, sy = GRAV_XY(sch[j][2], sch[j][3])
        dist = {z: float(np.hypot(cent[z][0] - sx, cent[z][1] - sy)) / MI for z in allz}
        top_d = [z for _v, z in sorted(((-v, z) for z, v in dz.items()))[:5]]
        top_m = [z for _v, z in sorted(((-v, z) for z, v in mz.items()))[:5]]
        rows["%s|%s" % (sch[j][0], span)] = {
            "cds": sch[j][0], "name": sch[j][1], "dashboardName": d["name"], "span": span, "level": SPAN_LEVEL[span],
            "enrolled": d["enrolled"], "placed": d["placed"], "overlapPct": round(100 * ov, 1),
            "sameTop5": len(set(top_d) & set(top_m)), "topDashboard": top_d, "topModel": top_m,
            "topZipDashboardPct": round(100 * dz[top_d[0]] / ds, 1), "topZipModelPct": round(100 * mz.get(top_d[0], 0) / ms, 1),
            "meanMiDashboard": round(sum(dz[z] * dist[z] for z in dz) / ds, 2),
            "meanMiModel": round(sum(mz[z] * dist[z] for z in mz) / ms, 2)}
    return rows


def zip_summary(rows):
    out = {}
    for lvl in ("elementary", "middle", "high", "all"):
        r = [v for v in rows.values() if lvl == "all" or v["level"] == lvl]
        if not r:
            continue
        w = np.array([v["placed"] for v in r], dtype=float)
        f = lambda k: round(float((np.array([v[k] for v in r]) * w).sum() / w.sum()), 2)  # noqa: E731
        out[lvl] = {"schools": len(r), "students": int(w.sum()), "overlapPct": f("overlapPct"), "sameTop5": f("sameTop5"),
                    "meanMiDashboard": f("meanMiDashboard"), "meanMiModel": f("meanMiModel"),
                    "worst": [(v["name"], v["span"], v["overlapPct"]) for v in sorted(r, key=lambda v: v["overlapPct"])[:3]]}
    return out


# -- outputs ----------------------------------------------------------------------

def blocks_table(blks, sch, mins, T, C, pr_ss):
    """Per block, band and likely school: odds, expected students, minutes by mode, total gap on each network,
    today's choice, the car share after a School Street, and each toggle's High-case bike logit shift (shiftX, the
    row's student-weighted mean of caseD x the rise in on-network share). A case's shift is caseLambda[case] x shiftX;
    the page moves bikePct's logit by it and scales the other modes in proportion."""
    names = ("block", "band", "school", "oddsPct", "students", "walkMin", "carMin", "transitMin",
             "bikeMin", "bikeMinCalm", "bikeMinConnector", "bikeMinBoth", "gapTotalFt", "gapTotalFtCalm", "gapTotalFtConnector", "gapTotalFtBoth",
             "shiftCalm", "shiftConnector", "shiftBoth",
             "carPct", "carpoolPct", "walkPct", "bikePct", "transitPct", "busPct", "carSchoolStreetPct")
    cols = {k: [] for k in names}
    ns, nb = len(sch), len(blks)
    band_ix = {"K-5": 0, "6-8": 1, "9-12": 2}
    cb = np.array([band_ix[BAND_OF[GRADES[g]]] for g in range(len(GRADES))])[C["grade"]]
    key = (C["b"] * 3 + cb) * ns + C["school"]
    uk, inv = np.unique(key, return_inverse=True)
    w = np.bincount(inv, weights=C["n"])
    agg = lambda x: np.bincount(inv, weights=C["n"] * x) / np.maximum(w, 1e-300)  # noqa: E731
    today = [agg(C["pr"][:, i]) for i in range(len(MODES))]   # bus included: today's yellow-bus riders are seeded
    ss = agg(pr_ss[:, CAR])
    new = {v: agg(C["caseD"] * network_gain(C, v)) for v in ("calm", "connector", "both")}
    ub, rem = np.divmod(uk, 3 * ns)
    ubd, uj = np.divmod(rem, ns)
    grp_all = ub * 3 + ubd
    Ob = np.bincount(grp_all, weights=w, minlength=nb * 3)
    odds = w / np.maximum(Ob[grp_all], 1e-300)
    order = np.lexsort((-odds, grp_all))
    grp = grp_all[order]
    first = np.r_[True, grp[1:] != grp[:-1]]
    rank = np.arange(len(order)) - np.maximum.accumulate(np.where(first, np.arange(len(order)), 0))
    keep = np.sort(order[(rank < BLOCK_TOP) & (odds[order] >= BLOCK_ODDS_MIN)])
    inv_band = {v: k for k, v in band_ix.items()}
    for i in keep:
        b, j = int(ub[i]), int(uj[i])
        cols["block"].append(b)
        cols["band"].append(inv_band[int(ubd[i])])
        cols["school"].append(j)
        cols["oddsPct"].append(round(100 * float(odds[i]), 1))
        cols["students"].append(round(float(w[i]), 2))
        for k, m in (("walkMin", "walk"), ("carMin", "car"), ("transitMin", "transit_" + inv_band[int(ubd[i])]), ("bikeMin", "bike_today"),
                     ("bikeMinCalm", "bike_calm"), ("bikeMinConnector", "bike_connector"), ("bikeMinBoth", "bike_both")):
            cols[k].append(round(float(mins[m][b, j]), 1))
        for k, v in (("gapTotalFt", "today"), ("gapTotalFtCalm", "calm"), ("gapTotalFtConnector", "connector"), ("gapTotalFtBoth", "both")):
            cols[k].append(int(round(float(T["gap_" + v][b, j]))))
        for k, v in (("shiftCalm", "calm"), ("shiftConnector", "connector"), ("shiftBoth", "both")):
            cols[k].append(round(float(new[v][i]), 3))
        for t, k in enumerate(("carPct", "carpoolPct", "walkPct", "bikePct", "transitPct", "busPct")):
            cols[k].append(round(100 * float(today[t][i]), 1))
        cols["carSchoolStreetPct"].append(round(100 * float(ss[i]), 1))
    listed = float(w[keep].sum()) / float(w.sum())
    return {"note": "One row per block, grade band and likely school (odds of at least %d%%, at most %d per block and band; "
                    "these rows hold %.1f%% of students). block indexes geoids, school indexes schools; students is the "
                    "expected count; *Pct is today's choice; shift* is the toggle's High-case bike logit shift, a case's being "
                    "caseLambda x it (tools/school-trips/school-sim.py)." % (int(100 * BLOCK_ODDS_MIN), BLOCK_TOP, 100 * listed),
            "listedPct": round(100 * listed, 2), "geoids": [b["geoid"] for b in blks], "schools": [s[0] for s in sch], "columns": cols}


# -- the City view ----------------------------------------------------------------

# The City view's switches (Bryan, 2026-10-09: one list of changes, each on or off at every school it fits). The
# programs apply in "all"'s order; the assignment option is a three-way choice; the network is one of VARIANTS.
CITY_PROGRAMS = ("caregiver_muni", "yellow_bus", "carpool", "ebike", "safer_crossings", "walking_bus", "school_street")
CITY_ASSIGN = ("", "assign_nas", "assign_ncp")
CITY_MAP_CASE = "central"


def city_key(variant, assign, on):
    """The City view's key for one switch set: network variant, assignment option, then a 0/1 per CITY_PROGRAMS."""
    return "%s|%s|%s" % (variant, assign or "today", "".join("1" if p in on else "0" for p in CITY_PROGRAMS))


def school_city(ps, sch, site):
    """Add to each school's file the School view's figures for every City view switch set, exactly, as city.json
    keeps them for the city: "city": {"mix": [6 modes] per assignment|programs key in sorted order, and per full key
    in sorted order "car", "bike" and "min" (one value per case, CASES order: family-car and bike students and total
    trip minutes) and "solo" (students whose trip needs no parent, the same in every case)}. The page reads the key
    orders from city.json's schools.car and sets."""
    ab, full = sorted(ps["mix"]), sorted(ps["car"])
    for j, s in enumerate(sch):
        f = os.path.join(site, "%s.json" % s[0])
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        d["city"] = {"mix": [ps["mix"][k][j].tolist() for k in ab], "car": [ps["car"][k][j].tolist() for k in full],
                     "bike": [ps["bike"][k][j].tolist() for k in full], "min": [ps["min"][k][j].tolist() for k in full],
                     "solo": [float(ps["solo"][k][j]) for k in full]}
        stable.write_json(f, d, separators=(",", ":"), ensure_ascii=False)


# A bikeway set's protected share: the miles of its stretches that are separated lanes, paths or car-free streets, over
# all its miles, a stretch with several facilities split evenly among them. The rest are calmed or shared streets. The
# page's injury model gives riders on the protected share Teschke et al. 2012's cycle track risk and the rest its local
# street risk (Bryan, 2026-10-18: "Use Teschke's cuts").
PROTECTED = {"Off-plan separated", "Separated", "Plan shared, upgraded to separated", "Shared-use Path", "Car-free"}


def separated_share(sg, m):
    by = {c["id"]: c for c in sg["chunks"]}
    mi = [(by[i]["mi"], by[i]["facilities"]) for i in m["chunks"] if by[i]["facilities"]]
    tot = sum(x for x, _ in mi)
    return round(sum(x * sum(f in PROTECTED for f in fs) / len(fs) for x, fs in mi) / tot, 4) if tot else 0


def check_gap_pct(m):
    """A budget's largest gap, in percent of the checked count, between the bikeway program's promised car trips and
    drivers and the full route search's checked ones. Bryan accepted 3% on 2026-10-24 after three solver rounds."""
    p = m.get("promise") or {}
    gaps = [abs(c - p[k]) / c for k, c in (("carTrips", m.get("carTripsRemoved")), ("drivers", m.get("drivers")))
            if c and p.get(k) is not None]
    return round(100 * max(gaps), 2) if gaps else None


def city_view(C, blks, sch, T, mins, lam):
    """Every City view switch set's citywide figures under each case, exactly, and the per-home-block map data.

    For every assignment option and subset of CITY_PROGRAMS (applied in "all"'s order, assignment first), and every
    network variant, the students by mode, the family-car students per tally band and the total trip minutes, one set
    per case (evaluate()'s rule: each cell's bike logit moves by lambda x caseD x its route's on-network gain, plus the
    e-bike's term at the gate's schools when e-bikes are on). The today variant's three are the same, since no route
    gains.

    The maps are per home block, summed over its schools and grades: students, the mean distance to school, the
    student-weighted mean of the total gap off the network today and with both street changes, the share with a
    safe walk or bike trip of 15 minutes or less (SOLO's rule) on each network, today's mix, the mix with every
    change on in the central case, each program's own change to the mix, and the share of students each network gives a
    better route (gainPct). A set that isn't today or all-on is drawn by adding each switched-on change's own change to
    today's mix, which is close but not exact where changes overlap."""
    ns, n = len(sch), C["n"]
    seg_meta = []
    if os.path.exists(SEGMENTS):
        sg = json.load(open(SEGMENTS))
        seg_meta = [{"budgetM": m["budgetM"], "centerlineMi": m["centerlineMi"], "costM": m["costM"], "chunks": m["nChunks"],
                     "students": m.get("students"), "drivers": m.get("drivers"), "bridges": len(m.get("bridges", [])),
                     "separatedShare": separated_share(sg, m), "checkGapPct": check_gap_pct(m)} for m in sg["budgets"]]
    bi = BAND_IX[C["grade"]]
    # Each network's cells with a route gain, and caseD x the gain there (the High case's shift).
    sv = {}
    for v in ALL_VARIANTS:
        gd = (C["caseD"] * network_gain(C, v)).astype(np.float64)
        idx = np.flatnonzero(gd > 0).astype(np.int32)
        sv[v] = (idx, gd[idx])
    # With e-bikes on, every cell at a school passing ebike_gate on that network (Bryan, 2026-10-13) also takes the
    # PCT's e-bike term.
    gate_e = {v: ebike_gate(C, C["gap_" + v]) for v in ALL_VARIANTS}
    e_term = PCT_EBIKE_H * np.maximum(np.minimum(C["grad"], GRAD_CAP_PCT) - PCT_H0, 0.0)
    band_n = [float(n[bi == k].sum()) for k in range(len(BANDS))]
    sc = C["school"]
    per_school_car = {}
    ps_mix, ps_car, ps_bike, ps_min, ps_solo = {}, {}, {}, {}, {}
    # Trip minutes by mode on each network, for the average trip time (Bryan, 2026-10-09: "I meant average trip
    # duration"). An assignment option scales its students' minutes by its distance ratio, as it scales their distance.
    car_min = mode_minutes(C, C["bike_min_today"])
    bike_of = {v: C["bike_min_" + v] for v in ALL_VARIANTS}
    sel_of = {}
    for a in CITY_ASSIGN[1:]:
        f = np.ones(len(n))
        sel = (C["gnum"] <= CHANGES[a]["max_grade"]) & C["sfusd"]
        f[sel] = CHANGES[a]["ratio"]
        sel_of[a] = f
    nob = [m for m in range(6) if m != BIKE]
    lam_v = np.array([lam[k] for k in CASES])[:, None]
    # Per network and e-bike setting, only the cells that move. 56 sets of per-cell arrays for every case, band, school
    # and mode ran to about 18 GB over 2.97M cells (2026-10-18), so agg builds each set's shift and gathers the rest
    # per call.
    move_of = {}
    for v in ALL_VARIANTS:
        idx, gd = sv[v]
        move_of[(v, False)] = idx
        move_of[(v, True)] = np.union1d(idx, np.flatnonzero(gate_e[v] & (e_term > 0))).astype(np.int32)

    def agg(pr, key_of, ebike, acc):
        """Each network's figures under each case. shift_bike's change in closed form, all cases at once: a moved
        cell's bike share goes from p to p2 = inv_logit(logit p + d), and every other mode is scaled by (1 - p2)/(1 - p)."""
        w = n[:, None] * pr
        # Students whose trip needs no parent, from track_acc: the same on every network and in every case.
        fr = n * acc.sum(axis=1)
        sfr = round(float(fr.sum()), 1)
        ps_fr = np.round(np.bincount(sc, weights=fr, minlength=ns), 1)
        modes = w.sum(axis=0)
        band = np.array([float(w[bi == k, CAR].sum()) for k in range(len(BANDS))])
        out = {}
        ab = key_of("today").split("|", 1)[1]
        per_school_car[ab] = np.round(np.bincount(sc, weights=w[:, CAR], minlength=ns), 1).tolist()
        ps_mix[ab] = np.round(np.stack([np.bincount(sc, weights=w[:, m], minlength=ns) for m in range(6)], axis=1), 1)
        a = ab.split("|")[0]
        fa = sel_of.get(a)
        fa = np.ones(len(n)) if fa is None else fa
        rest = (w[:, nob] * fa[:, None] * car_min[:, nob]).sum(axis=1)
        rest_sum, rest_s = float(rest.sum()), np.bincount(sc, weights=rest, minlength=ns)
        car_s = np.bincount(sc, weights=w[:, CAR], minlength=ns)
        bike_s = np.bincount(sc, weights=w[:, BIKE], minlength=ns)
        wbf = w[:, BIKE] * fa
        pb = pr[:, BIKE]
        ok_all = (pb > 0) & (pb < 1)
        pc_all = np.clip(pb, 1e-300, 1 - 1e-16)
        lg_all = np.log(pc_all) - np.log1p(-pc_all)
        for v in ALL_VARIANTS:
            tb = wbf * bike_of[v]
            tsum, tmin_s = rest_sum + float(tb.sum()), rest_s + np.bincount(sc, weights=tb, minlength=ns)
            ix = move_of[(v, ebike)]
            if ebike:
                idx, gd = sv[v]
                dc = np.zeros(len(ix))
                dc[np.searchsorted(ix, idx)] = gd
                D = lam_v * dc[None, :] + np.where(gate_e[v][ix], e_term[ix], 0.0)[None, :]
            else:
                D = lam_v * sv[v][1][None, :]
            bix, sci, cm = bi[ix], sc[ix], car_min[ix]
            A = w[ix]
            ok, pc = ok_all[ix], pc_all[ix]
            p2 = inv_logit(lg_all[ix][None, :] + D)
            R = np.where(ok, (pc - p2) / (1 - pc), 0.0)           # cases x cells: the other modes' relative change
            Bk = np.where(ok, n[ix] * (p2 - pc), 0.0)              # cases x cells: students onto the bike
            M = R @ A                                              # cases x modes
            M[:, BIKE] = Bk.sum(axis=1)
            Bc = np.stack([np.bincount(bix, weights=R[q] * A[:, CAR], minlength=len(BANDS))
                           for q in range(len(CASES))])            # cases x bands, the family car
            fai = fa[ix]
            Q = (A[:, nob] * cm[:, nob]).sum(axis=1) * fai
            dmin = R * Q[None, :] + Bk * (bike_of[v][ix] * fai)[None, :]
            row, cs, bs, ms = [], [], [], []
            for q in range(len(CASES)):
                row += [round(float(x), 1) for x in modes + M[q]] + [round(float(x), 1) for x in band + Bc[q]] + \
                       [round(tsum + float(dmin[q].sum()), 1)]
                cs.append(car_s + np.bincount(sci, weights=R[q] * A[:, CAR], minlength=ns))
                bs.append(bike_s + np.bincount(sci, weights=Bk[q], minlength=ns))
                ms.append(tmin_s + np.bincount(sci, weights=dmin[q], minlength=ns))
            out[v] = row + [sfr]
            ps_car[key_of(v)] = np.round(np.stack(cs, axis=1), 1)
            ps_bike[key_of(v)] = np.round(np.stack(bs, axis=1), 1)
            ps_min[key_of(v)] = np.round(np.stack(ms, axis=1), 1)
            ps_solo[key_of(v)] = ps_fr
        return out

    sets = {}
    # Free Muni's take-up is the page's to set (Bryan, 2026-10-09: "Let's drive muni off of it too"), so its sets are
    # written at take-up 1 and the page moves part of the way from the same set with Muni off.
    CH1 = dict(CHANGES, caregiver_muni=dict(CHANGES["caregiver_muni"], takeup=1.0))

    def walk(pr, i, on, assign, acc):
        if i == len(CITY_PROGRAMS):
            for v, row in agg(pr, lambda v: city_key(v, assign, on), "ebike" in on, acc).items():
                sets[city_key(v, assign, on)] = row
            return
        walk(pr, i + 1, on, assign, acc)
        # the e-bike's term depends on the network's gate, so its bit is applied per variant in agg, not to the mix
        if CITY_PROGRAMS[i] == "ebike":
            nxt, nacc = pr, acc
        else:
            nxt = apply_change(CITY_PROGRAMS[i], pr, C, ns, CH1)
            nacc = track_acc(CITY_PROGRAMS[i], pr, nxt, acc, C)
        walk(nxt, i + 1, on | {CITY_PROGRAMS[i]}, assign, nacc)

    for a in CITY_ASSIGN:
        pa = apply_change(a, C["pr"], C, ns, CHANGES) if a else C["pr"]
        # An assignment option changes trips but frees no parent, so its count starts at today's.
        walk(pa, 0, frozenset(), a, track_acc(a, C["pr"], pa, None, C) if a else free_share(C, pa))

    # The maps, per home block.
    b = C["b"]
    nb = len(blks)
    N = np.bincount(b, weights=n, minlength=nb)
    has = N > 0
    per = lambda x: np.bincount(b, weights=n * x, minlength=nb)[has] / N[has]  # noqa: E731
    mix = lambda pr: [np.round(100 * per(pr[:, m]), 1) for m in range(6)]  # noqa: E731
    pr_all = C["pr"]
    for ch in SCENARIOS["all"]:
        if ch != "ebike":
            pr_all = apply_change(ch, pr_all, C, ns, CHANGES)
    # every change on, both street changes, the central case, e-bikes at the gate's schools on that network
    pr_all = shift_bike(pr_all, lam[CITY_MAP_CASE] * C["caseD"] * network_gain(C, "both") + e_term * gate_e["both"])
    today = mix(C["pr"])
    safe15 = lambda v: (((C["walk_min"] <= SOLO["maxMin"]) | (C["bike_min_" + v] <= SOLO["maxMin"]))  # noqa: E731
                        & (C["gap_" + v] <= SOLO["gapTotalFt"])).astype(float)
    cols = {"geoid": [blks[i]["geoid"] for i in np.flatnonzero(has)],
            "lon": [round(blks[i]["lon"], 5) for i in np.flatnonzero(has)],
            "lat": [round(blks[i]["lat"], 5) for i in np.flatnonzero(has)],
            "students": np.round(N[has], 2).tolist(),
            "walkMi": np.round(per(C["walk_mi"]), 2).tolist(),
            "gapTotalFt": np.round(per(np.minimum(C["gap_today"], 1e5))).astype(int).tolist(),
            "gapTotalFtBoth": np.round(per(np.minimum(C["gap_both"], 1e5))).astype(int).tolist(),
            "safe15Pct": {v: np.round(100 * per(safe15(v)), 1).tolist() for v in ALL_VARIANTS + SS_VARIANTS},
            "gainPct": {v: np.round(100 * per((network_gain(C, v) > 0).astype(float)), 1).tolist() for v in ALL_VARIANTS if v != "today"},
            "today": [x.tolist() for x in today], "allOn": [x.tolist() for x in mix(pr_all)], "delta": {}}
    for ch in CITY_PROGRAMS + CITY_ASSIGN[1:]:
        m1 = mix(apply_change(ch, C["pr"], C, ns, CH1))
        cols["delta"][ch] = [np.round(m1[k] - today[k], 1).tolist() for k in range(6)]
    # Average home-to-school distance, by assignment option: SFUSD's TK-5 trips scaled by the option's ratio.
    def trip_mi(a):
        mi = C["walk_mi"].copy()
        if a:
            sel = (C["gnum"] <= CHANGES[a]["max_grade"]) & C["sfusd"]
            mi[sel] = mi[sel] * CHANGES[a]["ratio"]
        return mi
    trip = {(a or "today"): trip_mi(a) for a in CITY_ASSIGN}
    k5 = ((C["gnum"] <= CHANGES[CITY_ASSIGN[1]]["max_grade"]) & C["sfusd"]).astype(float)
    return {"note": "Written by tools/school-trips/school-sim.py (city_view). sets: key network|assignment|programs bits -> for "
                    "each case in cases' order, [students by mode x6, family-car students per tally band x3, total trip "
                    "minutes], then students whose trip needs no parent (SOLO, then FREE_CREDIT; the same in every case). "
                    "Year 10 of the ten-year horizon.",
            "cases": list(CASES), "caseLambda": lam, "mapCase": CITY_MAP_CASE,
            "programs": list(CITY_PROGRAMS), "assign": ["today", "assign_nas", "assign_ncp"], "variants": list(ALL_VARIANTS), "segments": seg_meta,
            "safeVariants": list(ALL_VARIANTS + SS_VARIANTS),
            "modes": MODES, "bands": list(BANDS), "bandN": [round(x, 1) for x in band_n], "students": round(float(n.sum()), 1),
            "tallyCar": TALLY_CAR, "tallyBandWeights": TALLY_BAND_W,
            "sets": sets, "blocks": cols,
            "tripMi": {a: round(float(np.dot(n, m) / n.sum()), 3) for a, m in trip.items()},
            # SFUSD's TK-5, the students the assignment options move, for the check against Stanford's figures.
            "tripMiK5": {a: round(float(np.dot(n * k5, m) / (n * k5).sum()), 3) for a, m in trip.items()},
            "calming": dict(CALMING),
            # Today's TK-5 Muni riders, every TK-5 student, for free Muni's cost: a caregiver riding with a child today
            # gets the free fare too.
            "muniK5Today": round(float((n * C["pr"][:, TRANSIT] * (bi == 0)).sum()), 1),
            "ebikeSchools": {v: int(np.unique(sc[gate_e[v]]).size) for v in ("today", "calm", "connector", "both")},
            "muniTakeup": "sets with caregiver_muni on are at take-up 1; the page scales them to free Muni's central rise (site/src/school-trips-model.mjs)",
            "schools": {"cds": [s[0] for s in sch], "students": np.round(np.bincount(sc, weights=n, minlength=ns), 1).tolist(),
                        "tripMi": {a: np.round(np.bincount(sc, weights=n * m, minlength=ns) / np.maximum(np.bincount(sc, weights=n, minlength=ns), 1e-9), 3).tolist()
                                   for a, m in trip.items()},
                        "safe15Pct": {v: np.round(100 * np.bincount(sc, weights=n * safe15(v), minlength=ns)
                                                  / np.maximum(np.bincount(sc, weights=n, minlength=ns), 1e-9), 1).tolist() for v in ALL_VARIANTS + SS_VARIANTS},
                        "car": {k: per_school_car[k] for k in sorted(per_school_car)},
                        "note": "car: assignment|programs bits -> family-car students per school on today's network; each "
                                "school's own file holds its figures per full key and case"},
            "_perSchool": {"mix": ps_mix, "car": ps_car, "bike": ps_bike, "min": ps_min, "solo": ps_solo}}


PRIORITY = os.path.join(ROOT, "out", "school-priority", "schools.csv")
SSC = os.path.join(ROOT, "out", "ssc-school-map", "compare.csv")


def _csv(path):
    import csv
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def _match_rows(grav, sch, rows, key="school"):
    by = {r[key]: r for r in rows if r.get("private") in ("False", False, None)}
    tok = [(grav._tokens(k), r) for k, r in sorted(by.items())]
    out = {}
    for s in sch:
        if is_private(s):
            out[s[0]] = None   # these tables hold SFUSD and charter schools only; a name match would be another school
            continue
        r = by.get(s[1])
        if r is None:
            want = grav._tokens(s[1])
            sc = sorted(((len(want & t) / float(max(len(want), len(t), 1)), i) for i, (t, _r) in enumerate(tok)), reverse=True)
            if sc and sc[0][0] >= 0.6 and (len(sc) == 1 or sc[1][0] < sc[0][0]):
                r = tok[sc[0][1]][1]
        out[s[0]] = r
    return out


# School Connectors go only to schools this close to today's all-ages network on foot, as scripts/ssc-school-map.py
# measures it. SFMTA's draft prioritizes schools "about a block away from the existing network" (Board slides, quoted
# in notes/safe-school-connections-2026-09/2026-10-01-sfmta-vs-our-school-counts.md), and Bryan, 2026-10-12, asked
# the model to match: "I'm pretty sure it's 1 block. If so, then update the model to use 1 block". The "1 block" band
# includes schools already on the network. A school with no match in that table gets none.
CONNECT_NEAR = ("1 block",)


def connector_ok(grav, sch):
    """{cds: True} for the schools that get a School Connector."""
    q = _match_rows(grav, sch, _csv(SSC))
    return {s[0]: bool(q.get(s[0]) and q[s[0]]["our_walk_today"] in CONNECT_NEAR) for s in sch}


def limit_connector(T, sch, ok):
    """Copy each far school's no-connector trips into its connector variants: connector takes today's, both takes
    calm's, at every bikeway budget and in the ranked-block extras. Applied after the trip cache, so the cached
    times are unchanged."""
    far = np.array([not ok[s[0]] for s in sch])
    if not far.any():
        return
    for k in ("bike", "gap", "on"):
        for v in ALL_VARIANTS + SS_VARIANTS:
            if "%s_%s" % (k, v) not in T:
                continue
            base = v.replace("connector", "today").replace("both", "calm")
            if base != v:
                T["%s_%s" % (k, v)][:, far] = T["%s_%s" % (k, base)][:, far]
    xb = T.get("_xb", {})
    for key in list(xb):
        j, v, kind = key.split("|")
        if far[int(j)] and v.split("_")[0] in ("connector", "both"):
            xb[key] = xb["%s|%s|%s" % (j, v.replace("connector", "today").replace("both", "calm"), kind)]


# Stanford's average elementary home-to-school distance per option (CHANGES' assign_* notes), checked against the
# model's SFUSD TK-5 mean in straight-line miles, the same measure as school-gravity.py's 1.40 target. Printed,
# not fatal. The tolerance is 0.1 mi because the model stays calibrated to SFCTA's bands and SFUSD's home ZIP
# figures, which both put trips longer than Stanford's (docs/decisions/school-trips.md, 2026-10-17).
STANFORD_K5_MI = {"today": 1.40, "assign_nas": 1.21, "assign_ncp": 1.06}
STANFORD_TOL_MI = 0.1


def k5_straight_mi(grav_g, d, sch):
    """SFUSD TK-5 straight-line mean trip per assignment option: today's from the gravity matrices, each option's
    scaled by its ratio, as city_view scales the walk trips."""
    charter = np.array([s[4] for s in sch], dtype=bool)
    top = CHANGES[CITY_ASSIGN[1]]["max_grade"]
    t = w = 0.0
    for gr, G in grav_g.items():
        if GNUM[gr] > top:
            continue
        keep = ~charter[G["cols"]]
        T = G["T"][:, keep]
        t += float((T * d[:, G["cols"]][:, keep]).sum())
        w += float(T.sum())
    if w <= 0:
        return {(a or "today"): None for a in CITY_ASSIGN}   # a sample with no SFUSD TK-5 school
    m = t / w
    return {(a or "today"): round(m * (CHANGES[a]["ratio"] if a else 1.0), 3) for a in CITY_ASSIGN}


def stanford_check(trip_mi_k5):
    """The modelled TK-5 mean trip per assignment option against Stanford's, pass within STANFORD_TOL_MI each."""
    rows = {k: {"model": round(float(v), 3), "stanford": STANFORD_K5_MI[k], "pass": bool(abs(v - STANFORD_K5_MI[k]) <= STANFORD_TOL_MI)}
            for k, v in trip_mi_k5.items() if k in STANFORD_K5_MI and v is not None}
    return {"tolMi": STANFORD_TOL_MI, "pass": all(r["pass"] for r in rows.values()), "miles": rows}


CALMING = {}   # limit_calm's record of what each budget reaches; city_view writes it to the page's city.json


def limit_calm(T, sch, tmeta, path=CALM_PRIORITY):
    """Calm only the schools the central budget reaches. Walks calm-priority.json's order, adding each school's
    calmed miles at CALM_PER_MI until CALM_BUDGETS_M[1] is spent. The order is strict: the walk stops at the first
    school whose miles would overrun the budget, so no lower-ranked school is calmed ahead of a higher one (Bryan,
    2026-10-13: "top injury schools ... as the priority order"). Every other school's calm variants take its
    uncalmed trips (calm takes today's, both takes connector's), at every bikeway budget, with and without
    its School Street, and in the ranked-block extras; its calmFt becomes 0. Runs after limit_connector, so a
    far school's both is already its calm and ends as today's. Records each budget's schools, miles and
    residential-street kids a year in CALMING."""
    pri = json.load(open(path))
    ps = tmeta["perSchool"]
    here = {s[0] for s in sch}
    order = [o for o in pri["order"] if o["cds"] in here and (ps.get(o["cds"]) or {}).get("calmFt", 0) > 0]
    CALMING.clear()
    CALMING.update({"source": pri["source"], "rule": pri["rule"], "perMileM": CALM_PER_MI, "zoneFt": ZONE_FT,
                    "years": pri["years"], "kidsNear": pri["kidsNear"], "residentialKids": pri["residentialKids"],
                    "budgets": {}})
    picked = {}
    for b in CALM_BUDGETS_M:
        spent, got, res, kids = 0.0, [], 0, 0
        for o in order:
            m = ps[o["cds"]]["calmFt"] / 5280.0
            if spent + m * CALM_PER_MI > b + 1e-9:
                break
            spent += m * CALM_PER_MI
            got.append(o["cds"])
            res += o["residentialKids"]
            kids += o["kids"]
        picked[b] = set(got)
        CALMING["budgets"]["%g" % b] = {"schools": len(got), "miles": round(spent / CALM_PER_MI, 1), "costM": round(spent, 2),
                                        "kidsNearPerYear": round(kids / pri["years"], 1),
                                        "residentialKidsPerYear": round(res / pri["years"], 1)}
    keep = picked[CALM_BUDGETS_M[1]]
    off = np.array([s[0] not in keep for s in sch])
    for s in sch:
        if ps.get(s[0]) is not None:
            ps[s[0]]["calmed"] = s[0] in keep
            # the full zone's feet, kept so the walk can be audited after calmFt is zeroed
            ps[s[0]]["calmFtFull"] = ps[s[0]].get("calmFt", 0)
            if s[0] not in keep:
                ps[s[0]]["calmFt"] = 0
    if not off.any():
        return
    for k in ("bike", "gap", "on"):
        for v in ALL_VARIANTS + SS_VARIANTS:
            if "%s_%s" % (k, v) not in T:
                continue
            base = v.replace("calm", "today").replace("both", "connector")
            if base != v:
                T["%s_%s" % (k, v)][:, off] = T["%s_%s" % (k, base)][:, off]
    xb = T.get("_xb", {})
    for key in list(xb):
        j, v, kind = key.split("|")
        if off[int(j)] and v.split("_")[0] in ("calm", "both"):
            xb[key] = xb["%s|%s|%s" % (j, v.replace("calm", "today").replace("both", "connector"), kind)]


def ranking(grav, sch, C, crash):
    """The city view's ordering inputs per school, read from the scripts that own them, plus the share of students
    with a safe 15-minute trip from this model."""
    pri = _match_rows(grav, sch, _csv(PRIORITY))
    ssc = _match_rows(grav, sch, _csv(SSC))
    ns = len(sch)
    near = C["gap_total_ft"] <= CHANGES["bike_switch"]["gap_total_ft"]
    safe15 = near & ((C["walk_min"] <= SOLO["maxMin"]) | (C["bike_min"] <= SOLO["maxMin"]))
    N = np.bincount(C["school"], weights=C["n"], minlength=ns)
    S = np.bincount(C["school"], weights=C["n"] * safe15, minlength=ns)
    rows = []
    for j, s in enumerate(sch):
        p, q, c = pri.get(s[0]), ssc.get(s[0]), crash.get(s[0]) or {}
        rows.append({"cds": s[0], "name": s[1], "students": int(sum(s[5].values())),
                     "bellHourInjuryCrashes600ft": c.get("injuryCrashes"), "bellHourSevereOrFatal600ft": c.get("severeOrFatal"),
                     "bellHourChildPedBike600ft": c.get("childPedBike"),
                     "blocksFromTodayNetwork": q and q["our_walk_today"], "blocksFromPlanNetwork": q and q["our_walk_plan"],
                     "safe15Pct": round(100 * float(S[j] / N[j]), 1),
                     "ejCommunity": None if p is None else p["ej_community"] == "True",
                     "ejScore": None if p is None or p["ej_score"] in ("", "None") else int(float(p["ej_score"])),
                     "sfmtaGroup": p and p["sfmta_group"], "sfmtaGroupLabel": p and p["sfmta_group_label"],
                     "highInjuryStreetWithin600ft": None if p is None else p["hin_within_600ft"] == "True",
                     "sfmtaShortlist": None if p is None else p["shortlist"] == "True"})
    return {"note": "One row per school for the city view's order. Crashes: injury crashes within 600 ft (182.88 m) of the school "
                    "at its own bell hours on school days, 2022-23 to 2025-26, the four school years tools/school-trips/school-hour-crashes.py "
                    "covers (not five), from DataSF ubvf-ztfx, nwes-mmgh and dau3-4s8f. Blocks from the networks: "
                    "out/ssc-school-map/compare.csv (tools/school-trips/ssc-school-map-compare.py), our walk from the school to today's "
                    "all-ages network and the plan's. EJ community and SFMTA's group: out/school-priority/schools.csv "
                    "(scripts/school-priority-shortlist.py, DataSF y6ci-vpnb, an EJ score of 21 to 30). safe15Pct: this model's "
                    "expected students with a walk or bike trip of at most 15 minutes whose bike route's total gap off "
                    "today's all-ages network is at most 1,000 ft.",
            "unmatched": {"priority": sorted(s[1] for s in sch if pri.get(s[0]) is None),
                          "sscMap": sorted(s[1] for s in sch if ssc.get(s[0]) is None)},
            "schools": rows}


# -- the page's copy ------------------------------------------------------------------

SITE = os.path.join(ROOT, "site", "data", "school-sim")
# The city view's rollout reads each school in four states: today, the quick changes (a School Street and the two
# programs, all doable in under three months), the street changes alone (Calm Streets and the connector), and every change.
ROLL_COMBOS = ("ss0-calm0-conn0-muni0-bus0", "ss1-calm0-conn0-muni1-bus1", "ss0-calm1-conn1-muni0-bus0", "ss1-calm1-conn1-muni1-bus1")
# The page shows these; the rest stay in out/school-sim/.
SITE_MEASURES = ("car", "carpool", "walk", "bike", "transit", "bus", "medianMin", "noCaregiverPct", "safeTripPct", "injuryCrashes5y")
HOME_MIN = 0.05          # a home block on the map holds at least this many of the school's expected students
ROLL_MEASURES = ("car", "carpool", "walk", "bike", "transit", "bus", "medianMin", "noCaregiverPct", "safeTripPct", "injuryCrashes5y",
                 "carTallyPts")   # the school's part of the citywide tally-basis change, summed by the page


def _r(x, k=1):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), k)


def _round_grid(g, keep=None):
    return {c: {nb: {m: [_r(v, 1) for v in vals] for m, vals in ms.items() if keep is None or m in keep} for nb, ms in by.items()}
            for c, by in g.items()}


def safe_options(C, T, sch):
    """Per school, network variant and number of ranked bikeway blocks: the share of its expected students with a
    walk or bike trip of at most 15 minutes whose bike route's total gap off the all-ages network is at most
    1,000 ft (as ranking.json's safe15Pct, on each improved network)."""
    ns = len(sch)
    N = np.bincount(C["school"], weights=C["n"], minlength=ns)
    gapmax = CHANGES["bike_switch"]["gap_total_ft"]
    out = {j: {} for j in range(ns)}
    xb = T.get("_xb", {})
    for v in VARIANTS:
        ok = (C["gap_" + v] <= gapmax) & ((C["walk_min"] <= SOLO["maxMin"]) | (C["bike_min_" + v] <= SOLO["maxMin"]))
        S = np.bincount(C["school"], weights=C["n"] * ok, minlength=ns)
        for j in range(ns):
            out[j].setdefault(v, {})["0"] = _r(100 * S[j] / N[j], 1) if N[j] > 0 else None
    for j in range(ns):
        m = C["school"] == j
        b = C["b"][m]
        for v in VARIANTS:
            for nb in BLOCK_NS[1:]:
                kb = "%d|%s_b%d|bike" % (j, v, nb)
                if kb not in xb:
                    continue
                bm = bike_minutes(xb[kb])[b]
                gp = xb["%d|%s_b%d|gap" % (j, v, nb)][b]
                ok = (gp <= gapmax) & ((C["walk_min"][m] <= SOLO["maxMin"]) | (bm <= SOLO["maxMin"]))
                out[j][v][str(nb)] = _r(100 * float((C["n"][m] * ok).sum()) / N[j], 1)
    return out


def today_net(SITE=SITE):
    """site/data/school-sim/today-net.json: the all-ages lines the sim counts as built today (all_ages_lines with
    brp_rule, protected only), so the page's maps draw the network the figures were computed on. The upcoming SFMTA
    bikeways are drawn separately from bike-history/planned.json."""
    stt = _load("school_travel_time", paths.script("school-travel-time.py"))
    today, _plan, _meta = stt.all_ages_lines(brp_rule=True)
    lines = [[[round(x, 5), round(y, 5)] for x, y in pts] for _k, pts in sorted(today, key=lambda kp: kp[0])]
    stable.write_json(os.path.join(SITE, "today-net.json"),
                      {"note": "Written by tools/school-trips/school-sim.py: the all-ages blocks the sim counts as built today.", "lines": lines},
                      separators=(",", ":"))


def site_data(blks, sch, mins, T, blocks, res, lev, out_s, val, model, rank, safeopt, tops, SITE=SITE):
    """site/data/school-sim/: index.json for the page (every school's summary, the citywide grid, the levers, the
    checks) and one <cds>.json per school (its grid and its likely home blocks) fetched when a school is picked."""
    os.makedirs(SITE, exist_ok=True)
    c = blocks["columns"]
    gapmax = CHANGES["bike_switch"]["gap_total_ft"]
    xb = T.get("_xb", {})
    by_school = {}
    for i in range(len(c["block"])):
        by_school.setdefault(c["school"][i], {}).setdefault(c["block"][i], []).append(i)
    rk = {r["cds"]: r for r in rank["schools"]}
    idx = []
    for j, s in enumerate(sch):
        row = out_s[j]
        g = res[j]
        nbs = sorted((int(k) for k in g[combo_key(COMBOS[0])]), key=int)
        idx.append({"cds": s[0], "name": s[1], "case": s[6], "charter": s[4], **({"private": True} if is_private(s) else {}), "lon": row["lon"], "lat": row["lat"],
                    "students": row["students"], "ranges": row["ranges"], "blocks": nbs,
                    "safeToday": safeopt[j]["today"]["0"], "safeBoth": safeopt[j]["both"]["0"],
                    "injuries5y": g[combo_key(COMBOS[0])]["0"]["injuryCrashes5y"][0],
                    "ej": rk.get(s[0], {}).get("ejCommunity"), "sfmtaGroup": rk.get(s[0], {}).get("sfmtaGroupLabel"),
                    "blocksToNetwork": rk.get(s[0], {}).get("blocksFromTodayNetwork"),
                    "blocksToPlan": rk.get(s[0], {}).get("blocksFromPlanNetwork"),
                    "sfmtaShortlist": rk.get(s[0], {}).get("sfmtaShortlist"),
                    "bellInjuries": rk.get(s[0], {}).get("bellHourInjuryCrashes600ft"),
                    "levers": {k: _r(v["car"], 2) for k, v in lev[j].items()},
                    "calmFt": row["network"].get("calmFt"), "calmFtFull": row["network"].get("calmFtFull"),
                    "calmed": row["network"].get("calmed"), "connectorFt": row["network"].get("connectorFt"),
                    "connectorOnNetwork": row["network"].get("connectorOnNetwork"),
                    "connector": rk.get(s[0], {}).get("blocksFromTodayNetwork") in CONNECT_NEAR,
                    # The city view's rollout: four states of a school in every case, on today's blocks.
                    "plan": {k: {m: [_r(x, 5 if m == "carTallyPts" else 2) for x in g[k]["0"][m]] for m in ROLL_MEASURES}
                             for k in ROLL_COMBOS}})
        # The map's home blocks: where the school's students are expected to live (at least HOME_MIN of one),
        # each with its expected students and a bit per (network, blocks added) for a safe trip of 15 minutes.
        rows = {"lon": [], "lat": [], "students": [], "safe": [], "safeV": []}
        for b, ii in sorted(by_school.get(j, {}).items()):
            w = sum(c["students"][i] for i in ii)
            if w < HOME_MIN:
                continue
            i0 = ii[0]
            bits = 0
            for vi, v in enumerate(VARIANTS):
                for ni, nb in enumerate(BLOCK_NS):
                    if nb == 0:
                        bm, gp = mins["bike_" + v][b, j], T["gap_" + v][b, j]
                    else:
                        kb = "%d|%s_b%d|bike" % (j, v, nb)
                        if kb not in xb:
                            continue
                        bm = bike_minutes(xb[kb][b])
                        gp = xb["%d|%s_b%d|gap" % (j, v, nb)][b]
                    if gp <= gapmax and (mins["walk"][b, j] <= SOLO["maxMin"] or bm <= SOLO["maxMin"]):
                        bits |= 1 << (vi * len(BLOCK_NS) + ni)
            rows["lon"].append(round(blks[b]["lon"], 5))
            rows["lat"].append(round(blks[b]["lat"], 5))
            rows["students"].append(round(w, 2))
            rows["safe"].append(bits)
            # a bit per ALL_VARIANTS network, the City view's street changes and new bikeway segments
            rows["safeV"].append(sum(1 << vi for vi, v in enumerate(ALL_VARIANTS + SS_VARIANTS)
                                     if T["gap_" + v][b, j] <= gapmax and (mins["walk"][b, j] <= SOLO["maxMin"] or mins["bike_" + v][b, j] <= SOLO["maxMin"])))
        lines = [[k, pts] for k, pts in tops.get(s[0], [])]
        stable.write_json(os.path.join(SITE, "%s.json" % s[0]),
                          {"cds": s[0], "grid": _round_grid(g, SITE_MEASURES), "safeOption": safeopt[j], "levers": lev[j], "network": row["network"],
                           "crashesToday": row["crashesToday"], "topBlocks": lines, "homes": rows},
                          separators=(",", ":"), ensure_ascii=False)
    keep = set("%s.json" % s[0] for s in sch) | {"index.json", "city.json", "overlays.json", "today-net.json"}
    today_net(SITE)
    for f in os.listdir(SITE):
        if f.endswith(".json") and f not in keep:
            os.remove(os.path.join(SITE, f))
    city_safe = None
    zc = val.get("zipCheck", {})
    stable.write_json(os.path.join(SITE, "index.json"), {
        "note": "Written by tools/school-trips/school-sim.py from out/school-sim/. One modelled city of SFUSD, charter and private school students.",
        "modes": MODES, "measures": MEASURES, "combos": model["combos"], "toggles": list(TOGGLES), "cases": list(CASES),
        "caseLambda": model["caseLambda"],
        "blockCounts": list(BLOCK_NS), "variants": list(VARIANTS), "changes": CHANGES,
        "city": {"grid": _round_grid(res["city"], SITE_MEASURES + ("carTally",)), "levers": lev["city"],
                 "students": int(sum(s["students"] for s in out_s)), "tallyCar": TALLY_CAR, "tallyBandWeights": TALLY_BAND_W},
        "schools": idx,
        "checks": {"byGrade": val["byGrade"], "citywide": val["citywide"], "byDistance": val["byDistance"],
                   "k5TripLengths": val["k5TripLengths"], "changes": val["changes"],
                   "zip": {k: zc.get(k) for k in ("source", "reachCal", "summary", "summaryStep1Reach", "unmatched")},
                   "attendanceArea": {k: val.get("attendanceArea", {}).get(k) for k in ("source", "byLevel", "areaSchools", "elementaryReach")},
                   "prunedPct": val["checks"]["prunedPct"], "listedPct": blocks["listedPct"]},
        "model": {k: model[k] for k in ("beta", "speeds", "gravity", "outcomes", "bells", "enrolment", "leftOut", "targets", "targetKind",
                                        "bike", "cases")},
    }, separators=(",", ":"), ensure_ascii=False)


# -- checks -----------------------------------------------------------------------

QUALITY_OUT = os.path.join("out", "school-sim")   # --housing points the checks at its own directory


def _rows(root, name):
    p = os.path.join(root, QUALITY_OUT, name)
    return json.load(open(p)) if os.path.exists(p) else None


def _ok(test, label):
    """quality.Each wants None for a good row, else why not: wrap a yes/no test."""
    def t(r):
        try:
            good = test(r)
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            return "%s: %s" % (label(r), exc)
        return None if good else label(r)
    return t


def _grid_ok(g, want=MEASURES):
    """Every combination present; every measure one value per case; shares sum to 100 in every case."""
    if set(g) != {combo_key(c) for c in COMBOS}:
        return False
    for _c, by_n in g.items():
        if "0" not in by_n:
            return False
        for _n, ms in by_n.items():
            if set(ms) != set(want) or any(len(ms[m]) != len(CASES) for m in want):
                return False
            for i in range(len(CASES)):
                if abs(sum(ms[m][i] for m in MODES) - 100) > 0.1:
                    return False
                if not (0 <= ms["noCaregiverPct"][i] <= 100.01 and 0 <= ms["safeTripPct"][i] <= 100.01):
                    return False
    return True


def check_specs(min_schools=100, min_blocks=5000):
    def schools_rows(root):
        d = _rows(root, "schools.json")
        return d and d["schools"]

    def city_rows(root):
        d = _rows(root, "city.json")
        return d and [d]

    def block_rows(root):
        d = _rows(root, "blocks.json")
        if not d:
            return None
        c = d["columns"]
        return [{k: c[k][i] for k in c} for i in range(len(c["block"]))]

    def block_ok(r):
        return abs(r["carPct"] + r["carpoolPct"] + r["walkPct"] + r["bikePct"] + r["transitPct"] + r.get("busPct", 0) - 100) <= 0.5 and 0 < r["oddsPct"] <= 100 \
            and all(r[k] >= 0 for k in ("shiftCalm", "shiftConnector", "shiftBoth"))

    def odds_rows(root):
        d = _rows(root, "blocks.json")
        if not d:
            return None
        c = d["columns"]
        acc = {}
        for b, band, o in zip(c["block"], c["band"], c["oddsPct"]):
            acc[(b, band)] = acc.get((b, band), 0) + o
        return [{"key": k, "odds": v} for k, v in acc.items()]

    def run_rows(root):
        d = _rows(root, "validation.json")
        return d and [d["checks"]]

    def band_rows(root):
        d = _rows(root, "validation.json")
        return d and [d["byDistance"]["model"]]

    def case_rows(root):
        d = _rows(root, "validation.json")
        return d and [d["cases"]]

    def car_rows(root):
        d = _rows(root, "validation.json")
        return d and [d["trips"]]

    def run_ok(r):
        return r["assignErr"] < 1e-4 and r["probSum"] < 1e-9 and r["choiceRowsMaxErr"] < 1e-9 and r["prunedPct"] < 2.0

    def grade_rows(root):
        d = _rows(root, "validation.json")
        return d and [dict(v, grade=k) for k, v in d["byGrade"].items()]

    def rank_rows(root):
        d = _rows(root, "ranking.json")
        return d and d["schools"]

    def point_rows(root):
        """The schools CDE lists, each with EAS's point for its street address (tools/school-trips/school-points.py)."""
        d, pts = _rows(root, "schools.json"), os.path.join(root, "data", "school-sim", "school-points.json")
        if not d or not os.path.exists(pts):
            return None
        p = json.load(open(pts))
        return [dict(cds=s["cds"], name=s["name"], lon=s["lon"], lat=s["lat"], eas=p["schools"][s["cds"]]["eas"], limit=p["limitFt"])
                for s in d["schools"] if s["cds"] in p["schools"]]

    def point_ok(r):
        e = r["eas"]
        return e is not None and math.hypot((r["lon"] - e["lon"]) * school_grounds.FT_LON, (r["lat"] - e["lat"]) * school_grounds.FT_LAT) <= r["limit"]

    def site_city_rows(root):
        """Each school's page file, with the City view's figures school_city() adds at the end of a run. A run stopped
        before that step leaves every file without them, and the School view's City switches then read nothing."""
        d = _rows(root, "schools.json")
        if not d:
            return None
        out = []
        for s in d["schools"]:
            f = os.path.join(root, "site", "data", "school-sim", "%s.json" % s["cds"])
            c = json.load(open(f)).get("city") if os.path.exists(f) else None
            out.append(dict(cds=s["cds"], city=c))
        return out

    def trace_rows(root):
        d = _rows(root, "validation.json")
        return d and [d.get("gapTrace") or {}]

    def private_rows(root):
        """private.json's distance check, one row a level; none in a SCHOOL_SIM_PRIVATE=0 or --housing run."""
        if not PRIVATE_RUN or QUALITY_OUT != os.path.join("out", "school-sim"):
            return [{"level": "none", "skip": True}]
        d = _rows(root, "private.json")
        if not d:
            return d
        dc = d.get("distanceCheck", {})
        # Every level is checked: a level missing from the file fails rather than passing unchecked.
        return [dict(dc[k], level=k) if k in dc else {"level": k} for k in ("elementary", "high", "middle")]

    def private_ok(r):
        return r.get("skip") or (len(r) > 1 and abs(r["privateMeanMi"] - r["referenceMeanMi"]) <= r["tol"] * r["referenceMeanMi"])

    return [
        Each("school-sim/gap-trace", trace_rows,
             _ok(lambda r: r["blocks"] > 0 and r["maxDiffFt"] <= 1.0, lambda r: "%s routes, largest difference %s ft" % (r.get("blocks"), r.get("maxDiffFt"))),
             "the total gap off the all-ages network, recomputed piece by piece along sampled routes, matches the run's within 1 ft"),
        Each("school-sim/private-distance", private_rows,
             _ok(private_ok, lambda r: "%s: private %s mi, SFUSD citywide %s mi" % (r.get("level"), r.get("privateMeanMi"), r.get("referenceMeanMi"))),
             "private students' mean straight-line trip within %d%% of SFUSD's citywide schools' at each level" % round(100 * PRIVATE_DIST_TOL)),
        Each("school-sim/school-city", site_city_rows,
             _ok(lambda r: bool(r["city"]) and all(r["city"].get(k) for k in ("mix", "car", "bike", "min", "solo")), lambda r: r.get("cds")),
             "every school's page file carries the City view's mix, car, bike, min and solo figures"),
        Table("school-sim/schools", schools_rows, floor=min_schools, key="cds", required=["cds", "name", "students", "grid", "levers"]),
        Each("school-sim/school-grid", schools_rows, _ok(lambda r: _grid_ok(r["grid"]), lambda r: r.get("cds")),
             "every toggle combination, one value per case, shares summing to 100"),
        Each("school-sim/school-levers", schools_rows,
             _ok(lambda r: set(r["levers"]) == set(SCENARIOS) and all(abs(sum(v[m] for m in MODES) - 100) <= 0.1 for v in r["levers"].values()),
                 lambda r: r.get("cds")), "every lever scenario present, shares summing to 100"),
        Each("school-sim/city-grid", city_rows, _ok(lambda r: _grid_ok(r["grid"], CITY_MEASURES) and set(r["levers"]) == set(SCENARIOS),
                                                    lambda r: "city"), "the citywide grid and levers are complete"),
        Each("school-sim/tally-basis", city_rows,
             _ok(lambda r: all(abs(r["grid"][combo_key(COMBOS[0])]["0"]["carTally"][i] - TALLY_CAR) <= 0.05 for i in range(len(CASES)))
                 and abs(r["levers"]["today"]["carTally"] - TALLY_CAR) <= 0.05
                 and all(v.get("carTally") is not None for v in r["levers"].values())
                 and tally_recompute_err(r) <= 0.02,
                 lambda r: "today %s" % r["grid"].get(combo_key(COMBOS[0]), {}).get("0", {}).get("carTally")),
             "the tally-basis car share today is the measured %.1f%% within 0.05 points, and every cell's carTally "
             "recomputes from the written grade-band shares within 0.02" % TALLY_CAR),
        Each("school-sim/tally-weights", run_rows, _ok(lambda r: r.get("tallyFitErr", 99) <= 0.15, lambda r: r.get("tallyFitErr")),
             "TALLY_WEIGHTS reproduce the tally's overall mix from its grade bars within 0.15 points"),
        Table("school-sim/blocks", block_rows, floor=min_blocks, key=("block", "band", "school"),
              required=["block", "band", "school", "oddsPct", "walkMin", "carMin", "carPct"]),
        Each("school-sim/block-choice", block_rows, _ok(block_ok, lambda r: (r.get("block"), r.get("band"), r.get("school"))),
             "each row's choice sums to 100, its odds are in (0, 100], its shift* at least 0"),
        Each("school-sim/block-odds", odds_rows, _ok(lambda r: r["odds"] <= 100.5, lambda r: r.get("key")),
             "a block's listed odds in a band sum to at most 100"),
        Each("school-sim/assignment", run_rows, _ok(run_ok, lambda r: json.dumps(r)),
             "every student assigned exactly once (each block's children and each school's enrolment met within 0.01%), "
             "choice probabilities sum to 1, pruning drops under 2% of students"),
        Each("school-sim/car-route", car_rows, _ok(lambda r: r["carDetourPct"] < CAR_DETOUR_MAX_PCT, lambda r: "%s%% of pairs; worst: %s" % (r.get("carDetourPct"), r.get("carDetourWorst"))),
             "under %g%% of block-school pairs %g mi or more apart on foot drive over %gx the walk" % (CAR_DETOUR_MAX_PCT, CAR_DETOUR_MIN_MI, CAR_DETOUR_X)),
        Each("school-sim/calibration", grade_rows, _ok(lambda r: abs(r["model"] - r["target"]) < 0.5 and r["maxModeErrPts"] < 0.01,
                                                       lambda r: r.get("grade")),
             "every grade's car share within 0.5 points of its target, and every mode within 0.01"),
        Each("school-sim/distance-bands", band_rows,
             _ok(lambda r: r["carMaxMissPts"] <= BAND_GATE_PTS and r["walkOver2Pct"] < WALK_OVER2_MAX_PCT,
                 lambda r: "car miss %s, walking over 2 mi %s%%" % (r.get("carMaxMissPts"), r.get("walkOver2Pct"))),
             "K-5 family-car share within %g points of SFCTA 2016 Fig. 3 in every distance band, and under %g%% of K-5 "
             "students over 2 miles walking" % (BAND_GATE_PTS, WALK_OVER2_MAX_PCT)),
        Each("school-sim/cases", case_rows, _ok(lambda r: r["ordered"] and not r["lowAboveHigh"], lambda r: json.dumps(r.get("lambda"))),
             "the low, central and high cases' year-10 bike shares are ordered at full network, and Low sits under High"),
        Table("school-sim/ranking", rank_rows, floor=min_schools, key="cds", required=["cds", "name", "students", "safe15Pct"]),
        Each("school-sim/ranking-share", rank_rows, _ok(lambda r: 0 <= r["safe15Pct"] <= 100, lambda r: r.get("cds")), "safe15Pct is a share"),
        Table("school-sim/school-points", point_rows, floor=min_schools, key="cds", required=["cds", "eas"]),
        Each("school-sim/school-points-near", point_rows, _ok(point_ok, lambda r: "%s %s" % (r.get("cds"), r.get("name"))),
             "every school's point within 500 ft of the city's address point for its CDE street address (data/school-sim/school-points.json)"),
    ]


def run_quality(root, **kw):
    res = run_checks(check_specs(**kw), root=root)
    bad = [r for r in res if not r.ok]
    for r in res:
        print("  %r" % r)
    return bad


def _good_grid(want=MEASURES):
    ms = {m: [100.0 if m == "car" else TALLY_CAR if m == "carTally" else 0.0] * len(CASES) for m in want}
    return {combo_key(c): {"0": json.loads(json.dumps(ms))} for c in COMBOS}


# The selftest's one school page file, written beside the out/ files by a path relative to them.
SITE_SAMPLE = os.path.join("..", "..", "site", "data", "school-sim", "1.json")


def selftest():
    """Each check fails on bad input: write broken copies of a tiny output set and run the checks on them."""
    import tempfile
    lev = {sc: {m: (100.0 if m == "car" else 0.0) for m in MEASURES} for sc in SCENARIOS}
    lev_city = {sc: dict(v, carTally=TALLY_CAR, **{k: 0.0 for k in BAND_KEYS}) for sc, v in lev.items()}
    good = {
        "schools.json": {"schools": [{"cds": "1", "name": "A", "students": 10, "grid": _good_grid(), "levers": lev,
                                      "lon": -122.36914, "lat": 37.82478}]},
        "city.json": {"grid": _good_grid(CITY_MEASURES), "levers": lev_city},
        "blocks.json": {"columns": {"block": [0], "band": ["K-5"], "school": [0], "oddsPct": [100.0], "students": [1.0],
                                    "walkMin": [5.0], "carMin": [4.0], "transitMin": [12.0], "carPct": [50.0], "carpoolPct": [0.0],
                                    "walkPct": [50.0], "bikePct": [0.0], "transitPct": [0.0], "shiftCalm": [0.0], "shiftConnector": [1.0],
                                    "shiftBoth": [1.0]}},
        "ranking.json": {"schools": [{"cds": "1", "name": "A", "students": 10, "safe15Pct": 50.0}]},
        SITE_SAMPLE: {"city": {"mix": [[100.0]], "car": [[1.0]], "bike": [[0.0]], "min": [[5.0]], "solo": [0.0]}},
        "validation.json": {"checks": {"assignErr": 0.0, "probSum": 0.0, "choiceRowsMaxErr": 0.0, "prunedPct": 0.1, "tallyFitErr": 0.08},
                            "byGrade": {"KN": {"model": 54.0, "target": 54.0, "maxModeErrPts": 0.0}},
                            "byDistance": {"model": {"carMaxMissPts": 1.6, "walkOver2Pct": 0.0}},
                            "cases": {"ordered": True, "lowAboveHigh": False, "lambda": {}},
                            "trips": {"carDetourPct": 0.1, "carDetourWorst": []},
                            "gapTrace": {"blocks": 450, "maxDiffFt": 0.0, "meanGapFt": 900.0}},
        "private.json": {"distanceCheck": {lvl: {"privateMeanMi": 2.6, "referenceMeanMi": 2.5, "tol": PRIVATE_DIST_TOL} for lvl in ("elementary", "high", "middle")}},
    }
    k0 = combo_key(COMBOS[0])
    breaks = {
        "school-sim/schools.rows": ("schools.json", lambda d: d.update(schools=[])),
        "school-sim/schools.unique": ("schools.json", lambda d: d["schools"].append(json.loads(json.dumps(d["schools"][0])))),
        "school-sim/school-grid": ("schools.json", lambda d: d["schools"][0]["grid"][k0]["0"]["car"].__setitem__(2, 80.0)),
        "school-sim/school-levers": ("schools.json", lambda d: d["schools"][0]["levers"].pop("all")),
        "school-sim/city-grid": ("city.json", lambda d: d["grid"].pop(k0)),
        "school-sim/tally-basis": ("city.json", lambda d: d["grid"][k0]["0"]["carTally"].__setitem__(0, 43.4)),
        "school-sim/tally-basis.each": ("city.json", lambda d: d["grid"][combo_key(COMBOS[-1])]["0"]["carK5"].__setitem__(2, 10.0)),
        "school-sim/tally-weights": ("validation.json", lambda d: d["checks"].update(tallyFitErr=1.2)),
        "school-sim/blocks.required": ("blocks.json", lambda d: d["columns"]["carPct"].__setitem__(0, None)),
        "school-sim/block-choice": ("blocks.json", lambda d: d["columns"]["walkPct"].__setitem__(0, 10.0)),
        "school-sim/block-odds": ("blocks.json", lambda d: [d["columns"][k].append(d["columns"][k][0] if k != "school" else 1)
                                                             for k in d["columns"]]),
        "school-sim/ranking.unique": ("ranking.json", lambda d: d["schools"].append(dict(d["schools"][0]))),
        "school-sim/ranking-share": ("ranking.json", lambda d: d["schools"][0].update(safe15Pct=120.0)),
        "school-sim/assignment": ("validation.json", lambda d: d["checks"].update(assignErr=0.02)),
        "school-sim/calibration": ("validation.json", lambda d: d["byGrade"]["KN"].update(model=50.0)),
        "school-sim/car-route": ("validation.json", lambda d: d["trips"].update(carDetourPct=14.9)),
        "school-sim/distance-bands": ("validation.json", lambda d: d["byDistance"]["model"].update(carMaxMissPts=10.4)),
        "school-sim/distance-bands.each": ("validation.json", lambda d: d["byDistance"]["model"].update(walkOver2Pct=14.0)),
        "school-sim/cases": ("validation.json", lambda d: d["cases"].update(ordered=False)),
        # A run stopped before school_city(): the page file has no City view figures.
        "school-sim/school-city": (SITE_SAMPLE, lambda d: d.pop("city")),
        # Life Learning Academy back at CDE's point, SoMa's 651 8th St, 22,000 ft from its Treasure Island address.
        "school-sim/school-points-near": ("schools.json", lambda d: d["schools"][0].update(lon=-122.40479, lat=37.77091)),
        # A route whose traced total gap is 40 ft off the run's.
        "school-sim/gap-trace": ("validation.json", lambda d: d["gapTrace"].update(maxDiffFt=40.0)),
        # Private high schoolers drawn from twice as far as SFUSD's citywide high schools draw.
        "school-sim/private-distance": ("private.json", lambda d: d["distanceCheck"]["high"].update(privateMeanMi=5.0)),
    }
    failed_as_expected = 0
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "out", "school-sim"))
        os.makedirs(os.path.join(tmp, "data", "school-sim"))
        os.makedirs(os.path.join(tmp, "site", "data", "school-sim"))
        json.dump({"limitFt": 500.0, "schools": {"1": {"name": "A", "eas": {"address": "651 08TH TI ST", "lon": -122.369140, "lat": 37.824784}}}},
                  open(os.path.join(tmp, "data", "school-sim", "school-points.json"), "w"))

        def write(dset):
            for f, d in dset.items():
                json.dump(d, open(os.path.join(tmp, "out", "school-sim", f), "w"))
        write(good)
        bad = [r for r in run_checks(check_specs(min_schools=1, min_blocks=1), root=tmp) if not r.ok]
        assert not bad, "the good set fails: %r" % bad
        print("  good input: every check passes")
        for check, (f, brk) in breaks.items():
            d = json.loads(json.dumps(good))
            brk(d[f])
            write(d)
            res = run_checks(check_specs(min_schools=1, min_blocks=1), root=tmp)
            hit = [r for r in res if not r.ok and r.check.startswith(check)]
            print("  %s on bad input: %s" % (check, "FAILS as it should" if hit else "still passes (BAD)"))
            failed_as_expected += bool(hit)
            write(good)
    G = {"O": np.array([2.0, 3.0]), "D": np.array([3.0, 2.0])}
    G["T"] = np.array([[1.0, 1.0], [2.0, 1.0]])
    ok_good = assignment_error(G) < 1e-4
    G["T"] = np.array([[1.0, 1.0], [1.0, 1.0]])
    ok_bad = assignment_error(G) < 1e-4
    print("  assigned-once check: balanced matrix %s, a matrix missing one student %s" % (
        "passes" if ok_good else "FAILS (BAD)", "FAILS as it should" if not ok_bad else "passes (BAD)"))
    total = len(breaks) + 1
    got = failed_as_expected + (ok_good and not ok_bad)
    print("  selftest: %d of %d checks fail on bad input" % (got, total))
    return got == total


# -- housing pipeline (--housing) -----------------------------------------------------

FMP_SEATS = os.path.join(ROOT, "data", "housing", "fmp-seats.json")   # scripts/housing-pipeline.py
FMP_GRADES = {"ES": SPAN_GRADES["TK-5"], "MS": SPAN_GRADES["6-8"], "HS": SPAN_GRADES["9-12"]}


def housing_dirs(path):
    """The housing run's own outputs, never out/school-sim or site/data/school-sim: out/school-sim-housing-<case>/, and
    its page data under .cache/school-sim-housing-<case>/site/."""
    tag = os.path.splitext(os.path.basename(path))[0].replace("pipeline-", "")
    return os.path.join(ROOT, "out", "school-sim-housing-" + tag), os.path.join(ROOT, ".cache", "school-sim-housing-" + tag)


def add_housing(grav, blks, sch, sch_all, grav_g, path):
    """The pipeline's new SFUSD students (scripts/housing-pipeline.py) added to the balanced matrices, in place.

    Each project's students go to the nearest block holding children of each level (level_kids > 0), split across
    grades in proportion to CDE enrolment by grade at every modelled school, SFUSD and charter (sch_all, so a
    sample takes the same split). In a sample, each grade's are scaled by its modelled schools' share of the city's
    enrolment in it, so the sample sees its share. They are origin-constrained only: from block i in grade g, they
    attend school j in proportion to the balanced matrix's T[i, j], the weights the model gives that block's other
    students, attendance-area mix included. A school's enrolment grows by what it receives (capacity isn't
    modelled), and G["O"] and G["D"] move with them so the assignment check still reads every student placed once.
    Returns the record housing.json carries."""
    doc = json.load(open(path))
    proj = [p for p in doc["projects"] if p["students"] > 0]
    full = {g: float(sum(s[5].get(g, 0) for s in sch_all)) for g in GRADES}
    share = {g: full[g] / sum(full.values()) for g in GRADES}
    bx = np.array([GRAV_XY(b["lon"], b["lat"]) for b in blks])
    px = np.array([GRAV_XY(p["lon"], p["lat"]) for p in proj])
    snap, near = {}, {}
    for lvl in ("elementary", "middle", "high"):
        has = np.flatnonzero(np.array([grav.level_kids(b, lvl) for b in blks]) > 0)
        k, dm = np.zeros(len(proj), dtype=int), np.zeros(len(proj))
        for c in range(0, len(proj), 200):
            d = np.hypot(px[c:c + 200, None, 0] - bx[None, has, 0], px[c:c + 200, None, 1] - bx[None, has, 1])
            k[c:c + 200] = d.argmin(axis=1)
            dm[c:c + 200] = d.min(axis=1)
        near[lvl] = has[k]
        ft = np.sort(dm / FT)
        snap[lvl] = {"medianFt": round(float(ft[len(ft) // 2])), "p95Ft": round(float(ft[int(0.95 * (len(ft) - 1))])),
                     "maxFt": round(float(ft[-1]))}
    stu = np.array([p["students"] for p in proj])
    added = np.zeros((len(sch), len(GRADES)))
    scale = {}
    for gr, G in grav_g.items():
        scale[gr] = float(G["D"].sum()) / full[gr]
        add = np.bincount(near[LEVEL[gr]], weights=stu * share[gr] * scale[gr], minlength=len(blks))
        Tm = G["T"]
        row = Tm.sum(axis=1)
        live = add > 0
        assert (row[live] > 0).all(), "%s: a housing block has no students to take weights from" % gr
        Tm[live] += (add[live] / row[live])[:, None] * Tm[live]
        added[G["cols"], GRADES.index(gr)] = Tm.sum(axis=0) - G["D"]
        G["D0"] = G["D"]
        G["O"] = G["O"] + add
        G["D"] = Tm.sum(axis=0)
    for j, s in enumerate(sch):
        for gi, gr in enumerate(GRADES):
            if added[j, gi] > 0:
                s[5][gr] = s[5][gr] + float(added[j, gi])
    fmp = json.load(open(FMP_SEATS))["schools"] if os.path.exists(FMP_SEATS) else []
    match = name_matcher(grav, sch)
    seats = {}
    for f in fmp:
        if f["program"] in FMP_GRADES:
            j = match(f["name"], FMP_GRADES[f["program"]])
            if j is not None and j not in seats:
                seats[j] = f
    rows = []
    for j, s in enumerate(sch):
        a = float(added[j].sum())
        f = seats.get(j)
        rows.append({"cds": s[0], "name": s[1], "charter": s[4], "studentsBefore": round(float(sum(s[5].values())) - a, 1),
                     "added": round(a, 2),
                     "addedByBand": {b: round(float(sum(added[j, gi] for gi, g in enumerate(GRADES) if BAND_OF[g] == b)), 2)
                                     for b in BANDS},
                     "fmp": f and {"name": f["name"], "program": f["program"], "enrolment2021": f["enrollment_2021"],
                                   "capacity2022": f["capacity_2022_23"], "spare": f["spare"],
                                   "spareAfter": round(f["spare"] - a, 1)}})
    rows.sort(key=lambda r: (-r["added"], r["cds"]))
    t = doc["totals"]
    return {"source": os.path.relpath(path, ROOT), "case": doc["case"], "rule": doc["rule"], "rates": doc["rates"],
            "input": {"projects": t["projects"], "units": t["units"], "students": t["students"]},
            "added": round(float(added.sum()), 1),
            "gradeShare": {g: round(share[g], 5) for g in GRADES}, "sampleScale": {g: round(v, 5) for g, v in scale.items()},
            "snap": snap, "fmpMatched": len(seats), "fmpSource": os.path.relpath(FMP_SEATS, ROOT),
            "note": "New students are origin-constrained: each attends schools in proportion to the balanced matrix's "
                    "weights from its block and grade. A school's enrolment grows by what it receives; capacity isn't "
                    "modelled. Mode-choice constants are today's (calibrated before the new students are added), so a "
                    "grade's modelled car share can move off its tally target. Spare seats are the FMP's 2022-23 "
                    "capacity less its October 2021 enrolment; spareAfter takes the added students off them.",
            "schools": rows}


# -- main ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--sample", type=int, default=0, help="only this many schools (the case-study ones first); writes to the cache dir")
    ap.add_argument("--check", action="store_true", help="run the quality checks on the written outputs")
    ap.add_argument("--selftest", action="store_true", help="show each check failing on bad input")
    ap.add_argument("--overlays", action="store_true", help="write the street changes as map lines (overlays.json) and stop")
    ap.add_argument("--segments", action="store_true", help="choose the new bikeway stretches per budget by integer program (tools/school-trips/school-segments-ip.py) and stop")
    ap.add_argument("--segments-greedy", action="store_true", help="the one-at-a-time ranking (tools/school-trips/school-segments.py) instead")
    ap.add_argument("--housing", metavar="PATH", help="add a housing pipeline's new students (data/housing/pipeline-*.json, "
                                                       "scripts/housing-pipeline.py); writes out/school-sim-housing-<case>/")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    global QUALITY_OUT, OUT, ORIGIN_SHARE
    if PRIVATE_RUN and a.housing:
        sys.exit("--housing adds students to SFUSD's schools only; run it with SCHOOL_SIM_PRIVATE=0")
    if not PRIVATE_RUN and not a.housing:
        if a.overlays or a.segments or a.segments_greedy:
            sys.exit("SCHOOL_SIM_PRIVATE=0 runs the simulation only, not --overlays or --segments")
        OUT = os.path.join(ROOT, "out", "school-sim-public")
        QUALITY_OUT = os.path.relpath(OUT, ROOT)
    if a.housing:
        if a.overlays or a.segments or a.segments_greedy:
            sys.exit("--housing runs the simulation only, not --overlays or --segments")
        h_out, h_cache = housing_dirs(a.housing)
        QUALITY_OUT = os.path.relpath(h_out, ROOT)
    if a.check:
        bad = run_quality(ROOT)
        sys.exit(1 if bad else 0)
    try:
        os.nice(15)
    except OSError:
        pass
    # The segments ranking may use 6 (2026-10-14, confirmed by the lead for the off-plan run: ~370 MB a worker).
    if a.segments_greedy:
        a.segments = True
    if a.segments:
        global IGNORE_SEGMENTS
        IGNORE_SEGMENTS = True
    workers = max(1, min(a.workers, SEGMENTS_MAX_WORKERS if a.segments else MAX_WORKERS))
    t0 = time.time()
    stage = {}

    def mark(name, t):
        stage[name] = round(time.time() - t, 1)
        print("  [%s: %.0fs]" % (name, stage[name]))
        return time.time()
    t = time.time()
    grav = gravity_module()
    sch, left, city = schools(grav)
    sch_all = sch
    if a.sample:
        sch = sorted(sch, key=lambda s: (s[6] is None, s[0]))[:a.sample]
    blks = grav.blocks()
    priv_doc = None
    if ORIGINS in ("B", "C") or PRIVATE_RUN:
        pub_share, pub_city = origin_shares(blks)
        if ORIGINS in ("B", "C"):
            ORIGIN_SHARE = pub_share
    if PRIVATE_RUN:
        priv, priv_doc = private_schools()
        if a.sample:
            priv = priv[:a.sample]   # a sample takes as many private schools as public ones
        sch = sch + priv
        # A private school with no outline in grounds.json is measured from its point, as grounds.json's "door" rows are.
        gr_ = school_grounds.load()
        for s_ in priv:
            gr_.setdefault(school_grounds.key(s_[2], s_[3]), {"name": s_[1], "public": False, "rings": [], "source": "door",
                                                              "doorFt": 0, "label": "", "ref": ""})
        print("  private schools: %d, %d students (%s)" % (
            len(priv), sum(sum(s_[5].values()) for s_ in priv), os.path.relpath(PRIVATE_JSON, ROOT)))
    tops = top_blocks(grav, sch)
    print("  %d schools (%d left out), %d blocks with children, %d with ranked bikeway blocks" % (len(sch), len(left), len(blks), len(tops)))
    t = mark("inputs", t)
    if a.overlays:
        network(blks, tops)
        r = overlays(sch, connector_ok(grav, sch))
        stable.write_json(os.path.join(SITE, "overlays.json"), r, separators=(",", ":"))
        print("  overlays: %d schools written to site/data/school-sim/overlays.json (%.0fs)" % (len(r["schools"]), time.time() - t0))
        return
    T, tmeta = trips(blks, sch, workers, tops)
    conn_ok = connector_ok(grav, sch)
    limit_connector(T, sch, conn_ok)
    print("  School Connectors: %d of %d schools within 1 block of the network" % (sum(conn_ok.values()), len(sch)))
    limit_calm(T, sch, tmeta)
    if "net" not in _W:
        network(blks, tops)
    gtrace = gap_trace(sch)
    print("  total gap traced piece by piece: %d routes, largest difference %s ft (mean gap %s ft)" % (
        gtrace["blocks"], gtrace["maxDiffFt"], gtrace["meanGapFt"]))
    print("  calming: " + "; ".join("$%sM reaches %d schools, %.1f mi" % (b, r["schools"], r["miles"]) for b, r in CALMING["budgets"].items()))
    muni, muni_meta = muni_times(grav, blks, sch)
    grad, grad_how = route_gradient(T, blks, sch)
    mins = minutes(T, muni, grad)
    t = mark("trip times", t)
    zips = grav.block_zips(blks)
    kids = np.array([b["a5_9"] + b["a10_14"] + b["a15_17"] for b in blks], dtype=float)
    ztab, zmiss = zip_table(grav, sch)
    zcent = zip_centroids(blks, zips, kids)
    masks, amiss, atag, n_areas = area_masks(grav, blks, sch, name_matcher(grav, sch))
    afit = fit_area(grav, blks, sch, city, zips, ztab, zcent, masks)
    REACH_CAL["elementary"] = afit["elementaryReach"]
    grav_g, gfit, d = gravity(grav, blks, sch, city, REACH_CAL, {"mask": masks, "share": afit["share"]})
    k5_before_rake = sfusd_k5(grav_g, d, sch)
    origin_out = {"method": ORIGINS, "source": None if ORIGINS == "A" else {
        "table": "https://data.census.gov/table/ACSDT5Y2024.B14002?g=050XX00US06075$1400000", "file": os.path.relpath(ACS_TRACTS, ROOT),
        "tag": "[primary — read 2026-10-19]", "publicShareCity": {k: round(v, 4) for k, v in pub_city.items()}},
        "note": {"A": "Origins are census children by level, scaled to each grade's enrolment: one citywide public share.",
                 "B": "Origins are census children x the tract's public share of enrolled students (ACS B14002), no rake.",
                 "C": "Origins are census children x the tract's public share of enrolled students (ACS B14002); each "
                      "SFUSD-run school's students by home ZIP are then raked to SFUSD's dashboard per grade span, so the "
                      "home-ZIP check below is fitted, not a test. Fig. 5 and Stanford's mean are checks the rake never sees."}[ORIGINS],
        "k5SfusdRunBeforeRake": k5_before_rake}
    if ORIGINS == "C":
        grav_g, rerr, cerr = rake_to_zips(grav_g, sch, zips, ztab)
        origin_out.update(rakeRowErrMax=round(rerr, 4), rakeColErrMax=round(cerr, 4))
    origin_out["k5SfusdRun"] = sfusd_k5(grav_g, d, sch)
    print("  origins %s: SFUSD-run K-5 straight line %s (Fig. 5 50.6 / 21.5 / 27.8; Stanford 1.40 mi)%s" % (
        ORIGINS, origin_out["k5SfusdRun"], "; rake errors row %.4f, column %.4f students" % (rerr, cerr) if ORIGINS == "C" else ""))
    area_out = area_summary(grav_g, sch, masks, afit, amiss, atag, n_areas)
    print("  attendance areas: %d of %d matched; elementary reach x%s; %s" % (
        len(masks), n_areas, afit["elementaryReach"], {k: v for k, v in area_out["byLevel"].items()}))
    zrows = zip_fit(grav, blks, sch, grav_g, zips, ztab, zcent)
    g1, _f1, _d1 = gravity(grav, blks, sch, city, REACH_STEP1)
    zcheck = {"source": ZIP_SRC, "reachCal": dict(REACH_CAL), "summary": zip_summary(zrows),
              "summaryStep1Reach": zip_summary(zip_fit(grav, blks, sch, g1, zips, ztab, zcent)),
              "unmatched": zmiss, "blocksWithNoZip": int(sum(z is None for z in zips)),
              "note": "Calibrated, not an independent test: REACH_CAL was chosen to maximise overlapPct. Both sides drop "
                      "ZIPs under 5 students, as the dashboard does; charters are not on the dashboard.",
              "schools": zrows}
    del g1
    t = mark("assignment", t)
    targets, kind, tg = tally_targets("flat")
    asc = calibrate(grav_g, mins, targets, BETA_LOG)
    cref = bike_reference(grav_g, mins, targets)
    targets_trend, _kt, _ = tally_targets("trend")
    t = mark("calibration", t)
    # After calibration, so the new students choose by today's constants rather than moving everyone's to fit the tally.
    housing = add_housing(grav, blks, sch, sch_all, grav_g, a.housing) if a.housing else None
    if housing:
        print("  housing %s: %.0f students in the file, %.1f added to %d schools; blocks snapped %s" % (
            housing["case"], housing["input"]["students"], housing["added"], sum(r["added"] > 0 for r in housing["schools"]),
            {k: v["medianFt"] for k, v in housing["snap"].items()}))
        t = mark("housing", t)
    priv_out = None
    grav_cells = grav_g
    if PRIVATE_RUN:
        # After calibration, so private students choose by SFUSD's constants and the tally fit stays SFUSD's.
        ref = private_ref(sch, masks)
        p_reach = private_reach(grav, sch, city, ref, REACH_CAL)
        priv_g = private_gravity(grav, blks, sch, d, {k: 1.0 - v for k, v in pub_share.items()}, p_reach)
        grav_cells = merge_grades(grav_g, priv_g)
        p_len = private_lengths(priv_g, d, sch)
        ref_mi = level_mean_mi(grav_g, d, ref)
        priv_out = {"source": os.path.relpath(PRIVATE_JSON, ROOT), "totals": priv_doc["totals"],
                    "reach": {k: round(v, 3) for k, v in p_reach.items()}, "reachCal": dict(REACH_CAL),
                    "reference": {lvl: {"schools": sorted(sch[j][1] for j in cols), "meanMi": ref_mi.get(lvl)} for lvl, cols in ref.items()},
                    "distanceCheck": {lvl: {"privateMeanMi": p_len[lvl]["meanMi"], "referenceMeanMi": ref_mi.get(lvl),
                                            "tol": PRIVATE_DIST_TOL} for lvl in ref if lvl in p_len},
                    "lengths": p_len, "assignErr": max(assignment_error(G) for G in priv_g.values()),
                    "modeShares": PRIVATE_MODE_NOTE,
                    "note": "Private schools' students placed by their own doubly constrained model (private_gravity) beside "
                            "the SFUSD and charter one, at the reach of SFUSD's citywide schools at each level; every "
                            "citywide figure counts them. Checks against published figures (Fig. 5, Stanford, the home ZIPs, "
                            "the tally) stay SFUSD's own."}
        print("  private: reach %s; mean trip, mi, private against SFUSD's citywide schools: %s" % (
            priv_out["reach"], {k: (v["privateMeanMi"], v["referenceMeanMi"]) for k, v in priv_out["distanceCheck"].items()}))
        del priv_g
    C, pruned = cells(grav_cells, mins, T, asc, BETA_LOG, cref)
    del grav_cells
    C["charter"] = np.array([s[4] for s in sch], dtype=bool)[C["school"]]
    C["private"] = np.array([is_private(s) for s in sch], dtype=bool)[C["school"]]
    C["sfusd"] = ~(C["charter"] | C["private"])   # the students SFUSD's assignment places
    if PRIVATE_RUN:
        # The cases' lambdas stay SFUSD's and charters' (the low anchor is a share of those students), so they match the default run.
        pub_cells = ~C["private"]
        lam, case_info = case_lambdas({k: C[k][pub_cells] for k in ("n", "pr", "caseD", "on_today", "level")})
    else:
        lam, case_info = case_lambdas(C)
    print("  cases: lambda %s; year-10 bike share at full network %s (today %s)" % (
        lam, case_info["bikePctFullNetworkYear10"], case_info["bikePctTodayByLevel"]))
    if a.segments:
        seg = _load("school_segments", paths.script("school-segments.py"))
        sys.modules["school_segments"] = seg   # so its pool jobs pickle by name
        stt = _load("school_travel_time", paths.script("school-travel-time.py"))
        os.makedirs(OUT, exist_ok=True)
        if a.segments_greedy:
            r = seg.rank(sys.modules[__name__], stt, C, T, mins, sch, blks, workers)
            path = os.path.join(OUT, "segments-offplan.json" if seg.OFFPLAN else "segments-greedy.json")
            stable.write_json(path, r, indent=1, ensure_ascii=False)
            print("  segments: %d ranked, written to %s (%.0fs)" % (len(r["ranked"]), os.path.relpath(path, ROOT), time.time() - t0))
            return
        ip = _load("school_segments_ip", paths.script("school-segments-ip.py"))
        sys.modules["school_segments_ip"] = ip
        r = ip.run(sys.modules[__name__], stt, seg, C, T, mins, sch, blks, workers)
        path = ip.OUT_PATH or SEGMENTS
        stable.write_json(path, r, indent=1, ensure_ascii=False)
        print("  segments: %d budgets, written to %s (%.0fs)" % (len(r["budgets"]), os.path.relpath(path, ROOT), time.time() - t0))
        return
    crash, crash_missing = crashes_today(grav, sch)
    res, lev, newly, prob_err = grid(C, T, sch, crash, lam)
    all_streets = lev["city"].pop("_allPlusStreets")
    t = mark("choice, toggles and cases", t)
    bell, bell_missing, bell_src = bells(grav, sch)
    checks = {"assignErr": max(assignment_error(grav_g[g]) for g in grav_g),
              "probSum": max(prob_err, float(np.abs(C["pr"].sum(axis=1) - 1).max())),
              "choiceRowsMaxErr": max(float(np.abs(probs(mins, grav_g[g]["cols"], g, asc[g], BETA_LOG).sum(axis=-1) - 1).max())
                                      for g in grav_g),
              "prunedPct": round(100 * pruned, 3), "cells": int(len(C["n"])), "tallyFitErr": tally_fit_err(tg)}
    grade_tab, city_model = by_grade(grav_g, mins, asc, BETA_LOG, targets, kind)
    val = {"byGrade": grade_tab,
           "citywide": {"model": city_model, "curveByEnrolment": curve_citywide(grav_g, targets),
                        "curveByEnrolmentTrend": curve_citywide(grav_g, targets_trend), "tally4Grades": TALLY_CAR, "goal": 30.0,
                        "tallyBasisToday": res["city"][combo_key(COMBOS[0])]["0"]["carTally"][0],
                        "tallyWeights": TALLY_WEIGHTS, "tallyBandWeights": TALLY_BAND_W,
                        "note": "The tally's 48.6% is its respondents' mix (K, 5th, 6th, 9th and mixed classes), not every "
                                "grade. The model's all-students figure weights the grade curve by CDE Census Day enrolment by "
                                "grade (data/school-case/enrolment-sf.json) at the schools modelled, with grades 10-12 held at "
                                "9th's 33%; Trend continues the 6th-9th line instead. The tally basis is 48.6 plus the modelled "
                                "change in each band's car share weighted by the tally's respondent weights."},
           "byDistance": {"beta": BETA_LOG, "model": by_distance(grav_g, mins, T, asc, BETA_LOG), "cts2016": cts_bands(), "src": CTS_SRC,
                          "sensitivity": {}},
           "cases": case_info, "bikeReference": cref,
           "bikeCurve": bike_curve_check(C, grad_how),
           "muni": muni_meta,
           "backcast": backcast(C, lam),
           "carCost": car_cost_check(C, len(sch)),
           "k5TripLengths": {"model": k5_lengths(grav_g, d), "modelSfusdRun": origin_out["k5SfusdRun"],
                             "fig5": {"under1": 50.6, "1to2": 21.5, "over2": 27.8}},
           "origins": origin_out,
           "changes": change_effects([C], sch, ["carmichael", "kipp-bayview", "burton", "balboa", "june-jordan"]),
           "newlyEligibleStudents": newly, "checks": checks, "trips": tmeta, "zipCheck": zcheck, "gapTrace": gtrace,
           "attendanceArea": area_out,
           "calibration": muni_eligibility_change(C)}
    for nm, b in BETA_LOG_ALT.items():
        asc_b = calibrate(grav_g, mins, targets, b)
        val["byDistance"]["sensitivity"][nm] = dict(by_distance(grav_g, mins, T, asc_b, b), beta=b)
    pr_ss = apply_change("school_street", C["pr"], C, len(sch), CHANGES)
    blocks = blocks_table(blks, sch, mins, T, C, pr_ss)
    rank = ranking(grav, sch, C, crash)
    out_s = []
    for j, s in enumerate(sch):
        row = {"cds": s[0], "name": s[1], "case": s[6], "charter": s[4], "lon": round(s[2], 5), "lat": round(s[3], 5),
               "students": int(round(sum(s[5].values()))), "ranges": {}, "crashesToday": crash.get(s[0]),
               "network": tmeta["perSchool"].get(s[0]), "grid": res[j], "levers": lev[j]}
        if is_private(s):
            row["private"] = s[7]
        for band in ("K-5", "6-8", "9-12"):
            n = sum(v for g, v in s[5].items() if BAND_OF.get(g) == band)
            if n > 0:
                b = bell.get(s[0], {}).get(band)
                row["ranges"][band] = {"students": int(n), "dropoff": b and b["start"], "pickup": b and b["end"],
                                       "earlyDay": b and b["earlyDay"], "earlyPickup": b and b["earlyEnd"],
                                       "bellName": b and b["sfusdName"], "bellSource": b and b["source"]}
        out_s.append(row)
    t = mark("validation and tables", t)
    val["stageSeconds"] = dict(stage)
    model = {"beta": BETA_LOG, "betaAlt": BETA_LOG_ALT, "walkLimitMiK5": WALK_LIMIT_MI_K5,
             "asc": {g: [round(float(x), 4) for x in asc[g]] for g in asc}, "ascOrder": MODES,
             "bike": {"curve": PCT_CURVE, "h0": PCT_H0, "gradCapPct": GRAD_CAP_PCT, "goDutch": PCT_DUTCH, "ebikeH": PCT_EBIKE_H,
                      "reference": cref, "gradient": grad_how},
             "cases": list(CASES), "caseLambda": lam, "lowAnchorBikePct": LOW_ANCHOR_BIKE_PCT,
             "targets": {g: [round(100 * float(x), 2) for x in targets[g]] for g in GRADES}, "targetKind": kind,
             "modes": MODES, "measures": MEASURES, "combos": [combo_key(c) for c in COMBOS],
             "blockCounts": list(BLOCK_NS), "gravity": gfit, "prune": PRUNE, "changes": CHANGES, "levers": SCENARIOS,
             "speeds": {"walkMph": WALK_MPH, "bikeMph": BIKE_MPH, "bikeFixedMin": BIKE_FIXED_MIN, "bikeGoogleMin": BIKE_GOOGLE_MIN,
                        "carMph": CAR_MPH, "carFixedMin": CAR_FIXED_MIN, "carGoogleA": CAR_GOOGLE_A, "carGoogleB": CAR_GOOGLE_B,"carpoolExtraMin": CARPOOL_EXTRA_MIN, "transitFixedMin": TRANSIT_FIXED_MIN,
                        "muni": {"accessM": MUNI_ACCESS_M, "footM": MUNI_FOOT_M, "transferS": MUNI_TRANSFER_S,
                                 "earlyMin": MUNI_EARLY_MIN, "noRouteMin": NO_MUNI_MIN},
                        "busExtraMin": BUS_EXTRA_MIN, "detour": DETOUR},
             "leftOut": dict(sorted(left.items())),
             "bells": dict(bell_src, missing=bell_missing,
                           note="Drop-off is the start bell and pickup the end bell, per grade range: SFUSD's 2025-26 page, or for a "
                                "case-study school SFUSD doesn't list, its own page's bell as data/school-case/dropoff.json records "
                                "it. Null where neither gives one: no guess is made."),
             "enrolment": {k: city[k] for k in ("year", "url") if k in city},
             "outcomes": {
                 "solo": dict(SOLO, note="Our assumption. A student can go without a caregiver on foot or by bike from walkGrade or "
                                         "bikeGrade up when the trip is at most maxMin minutes and the bike route's total gap off "
                                         "the all-ages network is at most gapTotalFt; on Muni or a yellow bus from transitGrade up."),
                 "safeTrip": {"note": "Students whose chosen trip is a safe one of at most 15 minutes: walking or biking with the "
                                      "bike route's total gap at most 1,000 ft, or Muni door to door in 15 minutes or less "
                                      "(scheduled times, muni_times)."},
                 "crashes": {"source": "out/school-hour-crashes/schools.json (tools/school-trips/school-hour-crashes.py): injury crashes within "
                                       "600 ft (182.88 m) of the school at its own bell hours on school days, 2022-23 to 2025-26",
                             "fiveYear": "a 5-year total: the four school years' count x 5/4", "missing": crash_missing,
                             "scenarioMethod": "exposure-based change only: today's count times the change in family-car miles on "
                                               "the school's expected trips; no crash modification factor"},
                 "cases": "School Street and the programs apply first; then, in each case, every cell's bike logit moves by "
                          "lambda x caseD x the rise in its route's on-network share over today's, the other modes scaled in "
                          "proportion. Year 10 of the ten-year horizon."}}
    files = {"schools.json": {"model": model, "schools": out_s},
             "city.json": {"grid": res["city"], "levers": lev["city"], "combos": model["combos"], "cases": list(CASES), "caseLambda": lam,
                           "measures": CITY_MEASURES, "tallyCar": TALLY_CAR, "tallyBandWeights": TALLY_BAND_W,
                           "allPlusStreets": all_streets},
             "blocks.json": blocks, "validation.json": val, "ranking.json": rank}
    if housing:
        files["housing.json"] = housing
    if priv_out:
        files["private.json"] = priv_out
    report(val, files["city.json"], out_s)
    if housing:
        dest = os.path.join(h_cache, "sample") if a.sample else h_out
        site_dir = os.path.join(dest, "site") if a.sample else os.path.join(h_cache, "site")
    elif not PRIVATE_RUN:
        dest = os.path.join(ROOT, ".cache", "school-sim-public", "sample") if a.sample else OUT
        site_dir = os.path.join(dest, "site") if a.sample else os.path.join(ROOT, ".cache", "school-sim-public", "site")
    else:
        dest = os.path.join(CACHE, "sample") if a.sample else OUT
        site_dir = os.path.join(dest, "site") if a.sample else SITE
    os.makedirs(dest, exist_ok=True)
    for f, obj in files.items():
        if f == "validation.json":
            old = stable.read_text(os.path.join(dest, f))
            if old:
                prev = json.loads(old)
                strip = lambda o: {k: v for k, v in o.items() if k != "stageSeconds"}  # noqa: E731
                if strip(prev) == json.loads(json.dumps(strip(obj))):
                    continue   # runtimes alone never rewrite the file
        compact = f in ("blocks.json", "schools.json", "city.json")
        stable.write_json(os.path.join(dest, f), obj, separators=(",", ":") if compact else None,
                          indent=None if compact else 1, ensure_ascii=False)
    # A sample writes its page data beside its outputs, so a test never touches site/data/.
    site_data(blks, sch, mins, T, blocks, res, lev, out_s, val, model, rank, safe_options(C, T, sch), tops, SITE=site_dir)
    tc = time.time()
    cv = city_view(C, blks, sch, T, mins, lam)
    school_city(cv.pop("_perSchool"), sch, site_dir)
    cv["tripMiK5Straight"] = k5_straight_mi(grav_g, d, sch)
    cv["stanfordCheck"] = stanford_check(cv["tripMiK5Straight"])
    stable.write_json(os.path.join(site_dir, "city.json"), cv, separators=(",", ":"), ensure_ascii=False)
    print("  city view: %d switch sets, %d home blocks (%.0fs)" % (len(cv["sets"]), len(cv["blocks"]["students"]), time.time() - tc))
    # The modelled SFUSD TK-5 straight-line mean trip under today's assignment and each option against Stanford's
    # 1.40 / 1.21 / 1.06 miles, within STANFORD_TOL_MI (recorded in city.json's stanfordCheck before the write above).
    # A miss is printed, not fatal.
    dchk = cv["stanfordCheck"]
    print("  SFUSD TK-5 mean trip, mi: " + "; ".join("%s %.2f (Stanford %.2f) %s" % (k, v["model"], v["stanford"], "PASS" if v["pass"] else "FAIL")
                                                   for k, v in dchk["miles"].items())
          + " -- within %.2f mi: %s" % (dchk["tolMi"], "PASS" if dchk["pass"] else "FAIL"))
    print("  e-bike help at schools, by network: %s" % cv["ebikeSchools"])
    print("  total %.0fs" % (time.time() - t0))
    if a.sample:
        print("  sample written to %s; checks need the full run" % dest)
        return
    bad = run_quality(ROOT)
    if bad:
        sys.exit("school-sim: %d quality checks failed" % len(bad))


def report(val, city, sch):
    print("\n  CAR SHARE BY GRADE (model vs its target from the 2024-25 Travel Tally)")
    for g, v in val["byGrade"].items():
        print("    %-3s model %5.1f%%  target %5.1f%%  %-30s %6d students" % (g, v["model"], v["target"], v["kind"], v["students"]))
    cw = val["citywide"]
    print("    all students, enrolment-weighted: model %.1f%%; the curve %.1f%% (10-12 held at 33%%), %.1f%% (10-12 on the 6th-9th trend)"
          % (cw["model"], cw["curveByEnrolment"], cw["curveByEnrolmentTrend"]))
    print("    tally basis today %.2f%% (measured %.1f%%); goal 30%%" % (cw["tallyBasisToday"], cw["tally4Grades"]))
    bd = val["byDistance"]
    bm = bd["model"]
    print("  K-5 FAMILY CAR BY WALK DISTANCE vs SFCTA 2016: under 1 mi %.1f%% (46), 1-2 mi %.1f%% (61), over 2 mi %.1f%% (59.2); "
          "Muni %s; walking over 2 mi %.2f%%; gate %s" % (bm["under1"], bm["1to2"], bm["over2"], bm["transit"], bm["walkOver2Pct"],
                                                          "PASS" if bm["gate"]["pass"] else "FAIL"))
    for b, v in bd["sensitivity"].items():
        print("    %s: %.1f / %.1f / %.1f" % (b, v["under1"], v["1to2"], v["over2"]))
    print("  CASES: %s" % json.dumps(val["cases"]["lambda"]))
    print("  BACKCAST 2019 -> today's built network: %s" % json.dumps(val["backcast"]))
    for lab, k in (("calibrated reach", "summary"), ("step 1's reach", "summaryStep1Reach")):
        print("  HOME ZIP vs SFUSD dashboard (%s): %s" % (lab, {l: (v["overlapPct"], v["sameTop5"], v["meanMiDashboard"], v["meanMiModel"])
                                                              for l, v in val["zipCheck"][k].items()}))
    kl = val["k5TripLengths"]["model"]
    print("  K-5 trip lengths (straight line) %.1f / %.1f / %.1f vs Fig. 5 50.6 / 21.5 / 27.8" % (kl["under1"], kl["1to2"], kl["over2"]))
    i25, i50, i75 = 0, 1, 2
    print("  CITYWIDE by toggles, cases low/central/high: car | median min | no caregiver | safe trip | injury crashes 5y (car-miles exposure)")
    for c, by in city["grid"].items():
        m = by["0"]
        f = lambda k: "/".join("%s" % m[k][i] for i in (i25, i50, i75))  # noqa: E731
        print("    %-22s %s | %s | %s | %s | %s" % (c, f("car"), f("medianMin"), f("noCaregiverPct"), f("safeTripPct"), f("injuryCrashes5y")))
    print("  CITYWIDE levers on today's network: car | median | no caregiver | safe trip | injuries 5y")
    for sc, m in city["levers"].items():
        print("    %-16s %s | %s | %s | %s | %s" % (sc, m["car"], m["medianMin"], m["noCaregiverPct"], m["safeTripPct"], m["injuryCrashes5y"]))
    print("  LEVERS AT CASE-STUDY SCHOOLS (applied vs study):")
    for cid, rows in val["changes"].items():
        print("    %s" % cid)
        for k, r in rows.items():
            extra = {kk: vv for kk, vv in r.items() if kk not in ("study", "src")}
            print("      %-16s %s | study: %s" % (k, extra, r["study"]))
    for s in sch:
        if s["case"] in ("carmichael", "kipp-bayview"):
            for c in ("ss0-calm0-conn0-muni0-bus0", "ss1-calm0-conn0-muni0-bus0", "ss1-calm1-conn1-muni0-bus0", "ss1-calm1-conn1-muni1-bus1"):
                for nb in sorted(s["grid"][c], key=int):
                    m = s["grid"][c][nb]
                    print("  %s %s blocks %s: car %s/%s/%s, median %s, no caregiver %s, safe %s, injuries 5y %s" % (
                        s["case"], c, nb, m["car"][i25], m["car"][i50], m["car"][i75], m["medianMin"][i50],
                        m["noCaregiverPct"][i50], m["safeTripPct"][i50], m["injuryCrashes5y"][i50]))
    print("  stage seconds: %s" % val["stageSeconds"])


if __name__ == "__main__":
    main()
