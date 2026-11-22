"""Precompute the Muni line optimizer: each line's wait, speed and crowding today, what each fix does to them and costs, every combination of fix levels, and the line's history.

Bryan's rulings of 2026-11-14 and 15 set it. A resident picks a line and sets three
targets, expected wait, bus speed and crowded trips, each starting at today's level, and sees the cheapest mix of fixes
over ten years that meets all three:
  expected wait  minutes at the stop on a line SFMTA counts frequent, every line but its Connector lines, over every
                 hour the line runs from 5 am to 11 pm: the timetable's wait (half the gap between buses, as scheduled)
                 plus the wait past it (excess wait), hours weighted by riders on board, as the dashboard counts them;
  bus speed      miles an hour, the dashboard's line speed;
  crowded trips  share of trips crowded: SFMTA's own published figure by route (sfmta_crowding.py), the mean of its
                 newest CROWD_MONTHS months; a line SFMTA has no figure for in each of them gets none (null).
Targets, not budgets (Bryan, 2026-11-15: "let's not have people set budgets. Let's have people
change the expected wait time, average bus speed, and overcrowding %. Default it to current levels. And depending on the
user's setting, find out how much budget it would cost to build and run, while minimizing expenditure over 10 years"):
the file ships every combination of fix levels' figures, and the page picks the combination with the least ten-year
cost whose middle-case figures, as the page shows them (wait and speed to 0.1, crowding to the whole percent), meet
every target; ties go to the one that saves riders more time (a minute of waiting counting as two on the bus, Bryan,
2026-11-14), then the first in combination order. Where none meets them all, the one with the smallest shortfall in
steps (0.1 min, 0.1 mph, 1 point) summed, then the same order. choose_targets() here and chooseTargets() on the page.

Lines by how SFMTA runs them (Bryan, 2026-11-17, on SFMTA's line types:
"'infrequent' is connector and OWL and measured vs timetable and everything else is frequent and measured against
scheduled gap", and on weighting hours within a line by riders on board). The tool follows the dashboard's rule (freq_rule.py), the lead's
reading of those two rulings for this page: a frequent line is judged by excess wait in every hour it runs, and a
Connector line by on-time departures in SFMTA's window, 1 minute early to 4 late (Charter 8A.103(c)(1) until
Proposition A, November 2026), with no wait figure (the 2026-11-09 ruling holds the arrival model for timetabled
service). muni.json's "frequent" says which a line is, and its schedule.gapHours the weekday hours a frequent line
runs ("hours" here, "g" for an hour it runs and "c" for one it doesn't or a Connector line's). This replaces the rule
the tool was built on, 2026-11-14, which judged each hour by whether a stop had a bus every 10
minutes or better; within a line each hour now counts by its riders on board, not its scheduled departures
(monthly_waits(), load_factors()).
On time (Bryan, 2026-11-15: "Should let me set something about on time performance"): a
Connector line ships "onTime", today's share of its timepoint departures in SFMTA's window on weekdays (holidays out),
from SFMTA's 29 August 2026 timetable through the window's end (ontime_now(), from
ontime_month.py's ontime/<m>-lines.csv), and the page shows it in place of the wait card with no control. It isn't a
goal, for two reasons. The measure doesn't reproduce SFMTA's: over every line and day, 5 am to 11 pm, each trip's
first and last stops out (ontime_month.py says why), ours is 50.6% for July 2024 to June 2025 against SFMTA's published
55%, and 50.0% for July to December 2025 against 59% (ontime_check(), "ontimeCheck"; DataSF 6dpt-7w23, read
2026-11-15), and the two move apart (ours 50.7% in July to December 2024, 48.5% in October 2026); the page's card says
"Our count, under SFMTA's" while any period runs a point or more under. 511 gives one time a stop, so a bus that
reaches a timepoint early and holds can count early where SFMTA counts its departure [inference — mine, untested; the
check that would confirm it is SFMTA's own departure records for a sample month, or the early share at timepoints
against the stops between them].
And of the fixes, only signal priority has a field on-time result (studies.json udot-2024-route850-tsp-ontime, UTA
Route 850, 86.8% to 88.1%, from a summary); lanes, holding and filling missed trips have none of their own.
The August 2026 step: the 22's early share went from 32% in August to 50% in September. It isn't a feed artifact:
weekday early share on timetabled service over all lines, as counted on 2026-11-15, is flat across 29/30 August (26% to 30% a week from May to October),
and lines moved both ways. In 511's August bundle, the 22's new timetable gives it 4.5% more scheduled time between the
same timepoints in the same hours (the 25, 37, 57 and 67 also changed; every other line's is unchanged) while its
speed held (6.12 mph in August, 6.05 in September), so its buses left early more often [inference — mine; confirmed
if the 22's added minutes and its added early departures fall on the same timepoint pairs]. Lines with no timetable
change, the 19, 36, 43 and 44 among them, left early less from the week of 17 August, before the change, as they
slowed (the 43 from 10.2 mph in July to 9.7 in September) [inference — mine: school-year traffic, unchecked]. So the
on-time figure counts only days on the current timetable.

Baseline ("today"): the dashboard's newest three months (site/data/muni.json windows["90"].monthList), each frequent
line's scheduled and actual wait from data/muni-ewt/extract_freq.csv weighted as site_data.py weights them (cells
within a line by riders on board, hours 05 to 22, months kept_share >= 0.6, the months pooled by the same weights),
the parts of excess wait (uneven spacing, missing buses, weighting) and speed from muni.json's line trend. A line with
under FEW_FREQ scheduled departures a month is flagged fewGap (the page doesn't use it).
A line whose weekday timetable changed with SFMTA's 29 August 2026 timetable (changed_lines: its scheduled departures
by hour moved by over a tenth; the 5R on October 2026's window) takes its wait from the days from that date only
(since_waits(), daily/hourly-<month>.csv, the same cells and weights), so "Now" isn't built on a timetable the line no
longer runs; its parts of excess wait keep the months' shares, and "since" says so on the page.
Holidays, run on a Sunday timetable, count as Sundays, and are read from the 511 summaries' own list
(holidays_of(), diag/<month>.json), never found again here from departure counts; the build fails when a month with
Labor Day, Thanksgiving, Christmas Day or New Year's Day on a weekday lists none.
No wait figure: a Connector line (ten of the 45 bus lines on the picker: the 25, 36, 37, 39, 52, 55, 56, 57, 66 and
67) has none, as the 2026-11-09 ruling holds for timetabled service: today's wait and every mix's are null, it has no
wait goal and no holding on its menu, the page shows its on-time share in the wait card's place, and its other fixes
are judged on speed and crowding.
Today credits what's already built: speed and wait are measured, so signal priority at the signals that have it
(486 of the 1,302 signals in SFMTA's layer, signals.json preempt_pr, plus the three SFMTA named as finished by October
2024 that the layer doesn't flag, lib/muni_signals.py; SFMTA's own deck counts 545 with bus priority) and
built transit-only lanes are in them, and fixes are priced only
where they're missing. A lane counts as built when SFMTA's layer says "Existing permanent" or "Implemented TETL", or
says "Future TETL" with an IMPLEMENT date already past (stop_pair_lanes.py built_rule); the same rule draws the map's
lanes and the history's. A stop-to-stop stretch's built share is measured along the route's own path within 80 ft of a
built lane, the T Third's rail trackway left out (stop_pair_lanes.py), and a new lane is priced and drawn only on the
parts of that path outside every built lane (pair_open.json). The lane layer was last edited in March 2021, so lanes
built since are entered by hand in
data/muni-ewt/optimizer/built_overrides.csv, one stop-to-stop stretch a row with its source (16th Street Phase 2 on
the 22, outer Geary on the 38 and 38R): such a stretch counts as fully laned, is drawn as built and is never offered.
Bulbs are not offered at stops SFMTA codes BB or SI or names "/BB" or "/SI" (muni_stop_types.py), nor at a stop the
same file lists as built (16th Street Phases 1 and 2, San Bruno Avenue, Mission and Persia), nor elsewhere on 16th
Street's Phase 2, finished January 2025, whose design put bulbs at Mission and Potrero only ("nobulb" rows), nor at a
stop the stop-removal fix takes out.
Side bus lanes, curbside red transit-only lanes as on Geary (Bryan, 2026-11-15, "consider side lanes instead of BRT"; the
lever model's "Bus lane, paint"), are on every bus line's menu where open street is left. (A red-paint before-and-after on a lane already
built, such as 16th Street's, measures painting, not building a lane, so it doesn't take lanes off a menu; pre-send
R3, 2026-11-15.) A lane is offered on every block of the route with two lanes in the bus's direction, counting a parking
lane as one (lane_class(); Bryan, 2026-11-16: "bus lanes up to the length of the route, minus
places where there's only one lane and you can't have a dedicated bus lane without blocking all other traffic"): two
or more general lanes that way, a lane taken, or one and parking on the block (lane_room.py's census or OpenStreetMap
tags), the parking taken. Where lane_room.py found room by width (one row per open segment) it keeps its call, so a
two-lane street too narrow to keep both lanes and its parking beside a 10.5 ft bus lane gives up the parking; its width
test no longer sets a block aside. A segment mostly without such lanes isn't priced or drawn: one lane and no parking
(the narrow-street lanes in a street's only general lane offered on 2026-11-15 are withdrawn by the same ruling), no
lane count, freeway ramps, and stretches SFMTA decided against (lanes_src "sfmta", Mission northbound from 14th to
Cesar Chavez and 16th eastbound from Church to Bryant; decided_against.csv's stretches, California from Arguello to
Park Presidio and Fulton from Stanyan to Central among them, never reach pair_open.json). The lane fix names the
streets where it takes parking (pre-send gate round 3, 2026-11-15); the menu buys every line's stretches slowest
first; the effect and the price a mile are the paint lane's, and notes.laneParts names each mile's street and what it
takes ("travel" or "parking").
BRT is not on the menu. Center-running lanes with boarding islands, as on Van Ness, need a two-way street with two
general lanes each way or Van Ness's or Geary's width. Of the open stretches lane_room.py checks, no line has a whole
mile of two-way street with two lanes each way (the 9 and 9R on Potrero and 11th, the 5R on Fulton, the 22 on 16th, each
under half a mile). On Geary, the other street the ruling names, SFMTA set its center-running transitway between Arguello
and 28th Avenue aside in 2021 for side-running lanes (built since, built_overrides.csv), citing environmental analysis that the two "would deliver
similar transit travel time savings" for about $50 million against at least $235 million (SFCTA Board memo, Agenda Item
6, 28 October 2021, p. 3, https://www.sfcta.org/sites/default/files/2021-11/Item%206%20-%20Geary%20Phase%202%20CER%20Amendment%20MEMO.pdf
[primary — read 2026-11-15]). The lever model's BRT row (Van Ness, sfmta-2025-van-ness-brt-evaluation) measures center
lanes against mixed traffic, not against side lanes already built, so applying it on Geary would credit what SFMTA's own
analysis says isn't there.
The side lane's effect, 0% / 5% / up to 11.3% of the time on the treated mile, is checked against Geary's own results
(studies.json): side lanes alone, the 38R 2% to 4% faster on the stretch laned every block against -1% and +1% on
the next one without (TETL evaluation, May 2021, SMS 3), and Geary Rapid's bundle of lanes, stops, bulbs and signals,
the 38 3% to 11% and the 38R 4% to 18% in lighter pandemic traffic (December 2022, SMS 2). Both sit inside the range,
so the lever model's low, middle and high stand.
Stops removed are stop_walk.py's, tested against SFMTA's own stop change criteria (none on a Connector line, no
transfer point within 450 ft of another line's busy stop nor its pair the other way, no stop that is the nearest on
the line to a school, medical place, grocery or senior housing or center within 650 ft, none beside a block steeper
than 6%, no built bulb or island, no stop the line didn't serve when the boardings were counted or whose count is 0,
no gap over 1,360 ft), listed by name and drawn on the map (out/stop_walk_stops.csv); a line where none qualifies has
no stop removal on its menu.

Fixes: the lever model's own per-line costs and effects, read from data/muni-ewt/lever/out/car_miles_by_line.csv
(lever_car_miles.py), in three cases, low, middle and high. Per unit, per boarding, middle case:
  ride share   (rider_min_mid - freq_min_mid - wait part) / annual boardings / the line's ride minutes, wait part =
               wpd_mid x cost_mid; the share of the average ride the unit saves;
  bus share    cycle_cut_mid / (K x run share), the share of the bus's running time it saves (lever_roi.py docstring);
  wait share   the wait part over the lever model's own baseline part it acts on (spacing for mid-route holding,
               missing buses for filling missed trips, the timetable's wait for more trips), applied to today's part
               here, so a study's effect stays in its own units; its low and high scale by the lever model's wait
               minutes in that case (wpd), so holding's ride penalty in the low isn't read as a wait;
  riders       new_rides_mid / annual boardings;
  walk         stop removal's added walk a boarding, stop_walk.csv via the lever model.
Low and high scale a time fix's effect by the lever model's ride minutes in that case over the middle's, frequency
minutes taken out (stop removal's measured walk staying fixed), and a wait fix's by its wait minutes in that case,
and take its new riders in that case; the frequency gain then comes from each case's own K (below). Costs stay at the middle:
the cards' range is the effect's, at the price shown.
Filling missed trips is sized on the page's own three months (window_delivery): SFMTA's delivered share by mode and
the line's tracked share over them, filled in the middle up to SFMTA's current 98.5% target, so a line already at
it (every motor bus line in August to October 2026) has no fill on its menu (pre-send gate round 6, R6-1, verified 9).
Running costs (filling missed trips, more trips) are the lever model's at $305 a bus-hour, NTD 2025's motor bus and
trolley bus average for SFMTA; each line's is rescaled here to its own mode's rate, the same NTD year (npsm-38gk,
directly operated, operating expenses over vehicle revenue hours): trolley bus $283.42, motor bus $316.28
[primary — read 2026-11-14 by the pre-send verifier], blended by the line's trolley share (lever/trolley_share.csv:
the share of the line's October 2026 trips run by 57xx, 58xx or 72xx trolley buses in 511's stop observations, SFMTA's
fleet series, as the pre-send verifier counted them [primary — read 2026-11-15 by the pre-send verifier]; since
Potrero Yard closed on 14 February 2026 the 49 runs motor buses, the 14 mostly and the 30 about half, each blended
at its measured share). GTFS gives every bus
route_type 3.
Costs over ten years: a combination's build cost, counted once for each time it is built inside the ten years
(ceil(10 / life), so paint's five-year life means a second coat), plus ten times its yearly running cost, summed
plainly with no discounting (the ruling asks what the city would spend over ten years, not a present value).
Build costs: signal priority $45,000 a signal; side bus lanes $150,000 a mile each way; stop removal $6,000 a stop; a bulb
or island $300,000; each with soft costs at 30% of the total (x 1/0.7). Signal priority runs at $1,700 a signal a year
(low $580, high $3,000; the middle is SFMTA's managed-services contract with its priority vendor, $759,000 a year for
about 450 intersections, research/notes/muni-reliability-2026-11/2026-11-15-fix-upkeep-costs.md), the middle used
for choosing; lanes, stop removal and bulbs carry no upkeep, so their running cost is 0; the lives it spreads them over (15, 5, 15 and 30 years at 3.1%, lever_roi.py ann) are used
to check its yearly cost here (spreading the up-front cost reproduces it) and to count rebuilds. Holding, filling
missed trips and more trips are running costs with nothing up front. Each fix ships unitUp (build, a unit), builds
(times built in ten years) and unitRun (running, a unit a year).
Combining fixes on one line, so no second counts twice:
  - signal priority saves its share of the time left after any new lane: lanes n x r1, priority rt x (1 - n x r1);
  - stop removal and bulbs save time at stops, a different part of the ride, and add to it;
  - every mix's saved ride time must be under the line's delay: today's ride time less the ride at the line's
    fastest hour of the day (muni.json lineSpeedHours, 365 days): a mix that would save more is scaled down to it;
  - faster running becomes more frequent service as the lever model does it: the round trip falls by
    x = K x bus share x run share (run share 1 / (1 + layover share)), K the share of saved time SFMTA runs as more
    trips: 0 in the low case, as when SFMTA banks the saving as fewer buses (Fast Forward toolkit, pp. 28-29, the 49
    Van Ness/Mission's 10% shorter round trip "saving three buses"), 0.75 in the middle (the lever model's), 1 in
    the high; stated on the page beside the result;
    the timetable's wait falls by (1 - x) and by 1 / (1 + s) for s more service (more buses);
  - crowded trips scale with riders per bus, today's share x (1 + new riders) / (frequency factor), holding given no
    crowding effect (NO_CROWD) [inference — mine; across the 16 frequent bus lines, crowded share rises with riders
    per trip at about 0.8 in our 511 reads, optimizer_crowding.py];
  - time saved, the tie-break between combinations that cost the same: 2 x the wait saved + the ride minutes saved - 2 x the walk added + CROWD_W x
    today's ride minutes x the crowded share cut, on the line's own ride length; CROWD_W = 0.5, our weight
    [inference — mine]; the 2-to-1 for waiting is USDOT's ratio of the value of waiting time to riding time
    (lever_roi.py's $38.80 against $19.40 an hour).
Fixes on a bus line: signal priority (whole line), side bus lanes (every eligible stretch-mile: a mile at a time up to
LANE_FINE, then LANE_COARSE miles at a time, then the part mile left when it's at least LANE_PART_MIN), stop removal
(local lines where a stop qualifies), bulbs or islands (BULB_STEPS, then every distinct stop with none built), mid-route
holding, filling the trips that didn't run and more buses. No level stops short of what the line has (Bryan,
2026-11-16: "no restrictions on how many busses you can add", "Also for other factors, no
restrictions"); the steps coarsen at the high end so the grid of every combination stays small.
More buses: MORE_SHARES of the line's buses in service at its busiest weekday moment (peak_buses(), SFMTA's GTFS
timetable, blocks with layover under an hour), rounded to whole buses, up to the share that brings the busiest hour at
its busiest stop to STOP_CAP buses (a bus a minute, what one curbside loading area can take), and on a line with
SFMTA's crowding figure no further than the first step that takes it to 0% (more_trim()). The steps widen at the high
end to hold the grid. Each bus is priced at the lever model's 10% row over 0.1 x
peak buses, today's cost per bus hour at the line's mode rate; its wait part is the timetable's wait over (1 + s), s the
added share of service, and its new riders the row's own elasticity, (1 + s) ** e - 1. Terminal dispatch is off the menu: SFMTA already manages headways on all 16 bus lines (Title VI
2025, Appendix K), so it would count the same spacing twice. Metro lines get no menu: train regulation comes with the
Train Control Upgrade, whose subway phase begins in 2028, not a budget line, so the page shows today's figures.

Fixes left out: a bus line that can't be priced for a fix keeps the others, and notes.left names each fix it isn't
offered with the reason (every signal already has priority, no open stretch where a lane fits, no stop meets the
removal rules or the line already skips stops, a Connector line with no gap to even out, its mode already at SFMTA's delivery target).
Lines: every bus line on the picker (lib/muni_bus_lines.py, 45 lines: the 16 frequent bus lines, the Grid and
Connector lines and the 15, 8AX and 8BX expresses) and the Metro lines, from the lever model's car_miles_*_all.csv.
The 21 (not running), the 35 and the 58 (no measured speed) are left off, with their reasons in the same file. A
stop-to-stop stretch counts toward a line's built lane share and is offered a lane only when the line ran it in the
newest four quarters (stop_pair_lanes.py "Current"), so a route that moved (the 6 off Market Street in 2025, the 49's
pre-BRT North Point stops) isn't credited or offered on streets it no longer runs.
Combinations: every combination of the menu's units (at most 3,072 a line and 31,758 in all on the October 2026 data, a
file of about 2.2 MB), evaluated in all three cases, shipped as
"grid": one array per figure (wait, mph and crowd low, middle and high; walk and gain middle), each in the order
itertools.product gives the fixes' units, the last fix changing fastest, so the page finds any combination by its
index and prices it from the fixes' unit costs. The build checks every series has one value per combination.
Map: the line's shape (muni-map.json), its built transit-only lanes (within 80 ft of the line), its built bulbs and
boarding islands (bus_bulbs.csv, none of them offered again), its signals with and
without priority (within 60 ft), new lanes drawn along the route on the open parts of its slowest stop-to-stop
stretches (pair_open.json, muni-lines.json speedAlong), bulbs at its busiest distinct stops with none built
(stop_boardings_2020.csv), and the stops stop removal takes out.
History: built lanes near the line with SFMTA's IMPLEMENT date where it has one; the line's dated projects and service
changes from data/muni-ewt/interventions.csv; the count of signals with priority (SFMTA's layer has no install dates);
and month by month since the first usable month after which no gap runs over a year (January 2022), expected wait
(frequent lines), speed and SFMTA's crowding, a series blanked before a month series_steps.csv names where it isn't
measured the same way (the 49's speed before April 2022), and the line's wait range in a year series_steps.csv names
before a step we haven't explained (the 22 in 2025), which the page sets under the wait card. Beside them (Bryan,
2026-11-16, on the 44: "update it so that it shows service increases over time ... like if there's changes to the
schedule or a number of buses", and "number of busses serving the line ...
scheduled frequency during daytime and off hours", "How many people ride this line each day?"): the most buses in
service at once on a weekday and the timetable's minutes between buses weekdays, weekday evenings and weekends, each
month by the rules of peak_buses() and schedule() (timetable_month.py on 511's monthly schedules, monthly_timetable(),
checked against SFMTA's current timetable for the newest month), and SFMTA's average weekday boardings for the route up to the newest month its
systemwide figure covers (monthly_riders). The build checks the gap reproduces SFMTA's published 44 change, every 12
minutes to every 10 from 10 June 2023 (SERVICE_CHECK, "The 44 O'Shaughnessy frequency will increase from every 12
minutes to every 10 minutes", SFMTA blog, 8 June 2023).

Checks, before anything is written; a failure prints and exits 1, and the old file stays:
  three full months: the window holds three usable months and every line has wait and speed in each;
  the dashboard: every line's frequent-hour excess wait here matches muni.json's to 0.002 in every month both have;
  a cost on every fix, and its up-front cost spread over its life equals the lever model's yearly cost to 0.5%;
  no double counting, and every saved ride under the line's delay;
  one fix alone reproduces the lever model's cycle cut;
  the grid has one value per combination in every series;
  every combination's fixes add to its total; lanes drawn on the map match the laned miles counted (0.5 mi or a half);
  new lanes drawn reach 90% of the most lane miles the menu prices; every open segment has a lane room row;
  no new lane drawn lies on a built lane drawn (no added point within 30 ft of a built lane's line that serves the
  same direction as the point's own leg, 5% allowed for ends meeting); bulb markers are distinct stops; stops listed as removed match the count the fix prices;
  overrides: every row in built_overrides.csv names a stretch or stop the line data has, and has a source (kind
    "segment", a lane built since the layer's last edit along a street stretch, lower Market's centre lanes, is
    drawn and dated as built here and counted as built by stop_pair_lanes.py; "nooffer" is never offered a lane);
  crowding: SFMTA's newest CROWD_MONTHS months are present, and at least MIN_CROWD_LINES lines have a figure.
Timetable (Bryan, 2026-11-15: "Should show basic schedule here"): each line's "schedule", one line
under the page's data date, from SFMTA's GTFS timetable (calendar.txt's services M11 weekdays, 2 Saturdays, 3 Sundays):
departures at the busiest stop (the most trips that day, not counting a trip's last stop) in the busier direction (more
departures there, direction 0 on a tie), so a line whose trips start at several terminals or short-turn shows its gap
where all of them run (the 38's first stops gave 6 minutes and its busiest stop 8); the median gap, rounded half up to a
whole minute, over weekdays 7 to 19, weekday evenings 20 to 23 (our choice, SCHED_WIN), and Saturdays and Sundays 7 to 19; the span the first
and last weekday departure from a first stop either way, to the nearest quarter hour (the half hour, then the hour,
where the line would otherwise wrap on a 390-wide phone), or "all night" where no gap round the clock tops an hour; a line with no weekday departure from 10 to 15 runs at rush hours only. schedule() and
schedule_text(), e.g. the 22's "Every 6 min, 8 evenings, 8 weekends · all night", the first figure weekday daytime.
Output: one file per month of data, site/data/muni-optimizer/<YYYY-MM>.json, the waits' newest month, so a shared
link keeps its own numbers. The build writes the current month's file and never rewrites an earlier month's.
Idempotent: no run stamp; "dataUpdated" is the older of the dates the waits and SFMTA's crowding were read; keys
sorted, figures rounded. Warns (doesn't fail) when SFMTA's newest month is over STALE_MONTHS behind the waits.
Pipeline: the muni-optimizer step in pipeline/transportation-update.py, a build that fetches nothing and reruns when an
input moves; pipeline/transportation-quality.py's muni-optimizer checks run on the file it leaves, and
pipeline/refresh-freshness.py fails when the newest month it covers ended over 40 days back. The timetable is read
from .cache/muni-gtfs/feed/, which ensure_feed() unpacks from the zip the muni-gtfs step keeps whenever the zip changes.
The lever model's files under data/muni-ewt/lever/ and the hand-kept ones under data/muni-ewt/optimizer/ are tracked
inputs. Two inputs arrive monthly through steps of their own, after the stop records the dashboard is built on:
optimizer/timetable_month.csv (muni-timetable-history, on the VM) and lever/delivered_by_mode.csv
(muni-delivered-by-mode). Until both carry the dashboard's newest month the build prints WAITING, keeps the last
month's file and exits 0 (waiting_on()).
Usage: ~/.venvs/sf-works-geo/bin/python -I tools/muni/muni-ewt/optimizer_build.py
"""
import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import csv, datetime as dt, itertools, json, math, os, re, sys

import duckdb
import numpy as np

ROOT = paths.ROOT
sys.path.insert(0, paths.LIB)
from lib import muni_signals, stable  # noqa: E402
from lib.muni_bus_lines import SKIPS_STOPS  # noqa: E402

E = os.path.join(ROOT, "data", "muni-ewt")
LEV = os.path.join(E, "lever")
O = os.path.join(LEV, "out")
SITE = os.path.join(ROOT, "site", "data")
OUT_DIR = os.path.join(SITE, "muni-optimizer")

MINKEEP = 0.6          # site_data.py's usable-month rule
FEW_FREQ = 20000       # scheduled departures a month under which a frequent line is flagged fewGap (site_data.py SMALL)
CROWD_MONTHS = 3       # SFMTA's newest published months that make today's crowding
MIN_CROWD_LINES = 20
STALE_MONTHS = 4       # warn when SFMTA's newest month is more than this many months behind the waits
K_MID = 0.75           # lever_roi.py: share of saved running time the schedule turns into service, middle
# the same share in each case: none in the low (SFMTA banks the saving as fewer buses, as its toolkit says it has), all
#   of it in the high (lead ruling at the pre-send gate, round 3, 2026-11-15)
K_CASE = {"low": 0.0, "mid": K_MID, "high": 1.0}
CROWD_W = 0.5
YEARS = 10             # the ten-year cost the page minimises (Bryan, 2026-11-15)
MIN_ONTIME_N = 500     # timepoint departures a month a line's clock hours need for an on-time figure (site_data.py MINOT)
CASES = ("low", "mid", "high")
R_DISC = 0.031         # lever_roi.py R
SOFT = 1 / 0.7         # Fast Forward: soft costs "about 30%" of the total
crf = lambda life: R_DISC / (1 - (1 + R_DISC) ** -life)
# times a fix is built inside the ten years: a build fix whose life is shorter is rebuilt (paint, 5 years, twice)
builds = lambda fid: math.ceil(YEARS / CAPITAL[fid][1]) if fid in CAPITAL else 1

# Each fix: id, the lever model's name, label, unit label, and the units offered (0 first).
FIXES = {
    "bus": [
        {"id": "tsp", "lever": "Signal priority", "label": "Signal priority", "unit": "at the line's signals without it", "units": [0, 1]},
        {"id": "lane", "lever": "Bus lane, paint", "label": "Side bus lanes", "unit": "a mile of street", "units": "lane"},
        {"id": "stops", "lever": "Stop removal, net of walk", "label": "Remove lightly used stops", "unit": "on the line", "units": [0, 1]},
        {"id": "bulb", "lever": "Bulb or island", "label": "Bus bulbs or boarding islands", "unit": "a stop", "units": "bulb"},
        {"id": "hold", "lever": "Mid-route holding", "label": "Hold buses mid-route to space them out", "unit": "on the line", "units": [0, 1]},
        {"id": "fill", "lever": "Fill missed trips", "label": "Run the trips that don't run", "unit": "on the line", "units": [0, 1]},
        {"id": "more", "lever": "10% more trips", "label": "More buses", "unit": "a bus in service at the busiest hour", "units": "more"},
    ],
    "metro": [],
}
# The studies behind each fix's effect, by row id in data/evidence/studies.json (the lever model's own citations for
#   the same levers); site/scripts/check-studies.mjs fails if one has no row or names no muni-lever-* lever.
# --- STUDIES (read by site/scripts/check-studies.mjs)
# {"tsp": ["sfmta-2021-gtt-tsp-switch-off", "sfmta-2019-mission-tsp-test", "fhwa-2014-la-portland-tsp"],
#  "lane": ["gonzalez-silva-2025-santiago", "sfmta-2015-church-street-lanes", "sfmta-2017-red-lanes", "nycdot-2020-m79-sbs",
#           "sfmta-2021-geary-tetl-evaluation", "sfmta-2022-geary-rapid-evaluation"],
#  "stops": ["sfmta-2023-29-sunset-stops", "el-geneidy-2006-trimet-stops"],
#  "bulb": ["sfmta-2024-fast-forward-corridors", "sfmta-2014-tep-bulb-assumption", "tcrp-2000-webdoc19-bus-bulbs"],
#  "hold": ["rodriguez-2025-cta-holding", "soza-parra-2019-wmata-headway"],
#  "tsp_run": ["sfmta-2018-gtt-tsp-managed-services"],
#  "riders": ["handy-2013-carb-transit-service"]}
# --- end STUDIES
# Build cost a unit before soft costs, and life in years (Fast Forward toolkit, https://www.sfmta.com/media/40687/download).
#   tsp is a signal (the unit is the line's open signals), lane a mile both ways, stops a stop removed, bulb a stop.
CAPITAL = {"tsp": (45e3, 15), "lane": (2 * 150e3, 5), "stops": (6e3, 15), "bulb": (300e3, 30)}
# Yearly upkeep a unit, low / mid / high, for a build fix that has any: signal priority a signal a year, SFMTA's GTT
#   managed-services contract (Calendar Item 10.5, 2018-02-06, $759,000 a year for about 450 intersections), an
#   operating cost with no soft-cost markup. The middle is what the ten-year cost and the chooser use.
UPKEEP = {"tsp": (580.0, 1700.0, 3000.0)}
NO_CROWD = ("hold",)
WAIT_PART = {"hold": "spacing", "fill": "missing", "more": "swt"}
# side bus lanes: no cap but the line's own eligible miles (Bryan, 2026-11-16: "bus lanes up to the
#   length of the route, minus places where there's only one lane and you can't have a dedicated bus lane without
#   blocking all other traffic"); levels a whole mile apart up to LANE_FINE miles, then LANE_COARSE apart, then the top
LANE_FINE = 8
LANE_COARSE = 2
# the smallest part mile offered past the whole miles: a lane is priced and credited a mile at a time, so 2.8 open miles
#   were cut to 2 (the 22, 2026-11-15); the part mile is offered in tenths, rounded down, so no more is sold than is open
LANE_PART_MIN = 0.2
# more buses: steps as shares of the line's buses in service at its busiest weekday moment (peak_buses()), rounded to
#   whole buses, until the line's busiest stop would get more buses an hour than one loading area can take
#   (STOP_CAP), or, on a line with SFMTA's crowding figure, the first step that takes it to 0% (more_trim()). Bryan,
#   2026-11-16: "Already asked not to make arbitrary restrictions. no restrictions on how many
#   busses you can add"; the steps coarsen at the high end so the grid of every combination stays small
MORE_SHARES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
# buses an hour one curbside loading area can take, a bus a minute: TCQSM 3rd edition (TCRP Report 165, 2013),
#   Chapter 6, Equation 6-1, p. 6-15, "Loading area capacity = Seconds in an hour available for bus movement / Seconds
#   that a design bus occupies the loading area", with half the hour green at a signal (g/C 0.5), the manual's default
#   10 s to pull out and the next bus in (p. 6-71, "default of 10 s") and a 40 s dwell [inference — mine: the dwell is
#   ours]: 1,800 / (0.5 x 40 + 10) = 60. No operating margin, so this is the most a stop can take, not a design figure
STOP_CAP = 60
# bulbs or islands: up to every stop on the line that has none (Bryan, same thread: "Also for other factors, no
#   restrictions"), in steps that double past 10
BULB_STEPS = (0, 5, 10, 20, 40, 80)
GTFS = os.path.join(ROOT, ".cache", "muni-gtfs", "feed")
LAYOVER_GAP = 3600  # seconds: a block's gap under this between two trips is layover (lever_roi.py's rule)
# NTD 2025, SFMTA (90015), directly operated, operating expenses over vehicle revenue hours (datahub.transportation.gov
#   npsm-38gk): what the lever model's flat 305 becomes on each mode's lines.
LEVER_RATE = 305
RATE = {"trolley": 237435547 / 837743, "motor": 526486927 / 1664605}
# each line's trolley share (docstring, "Running costs"); a line not in the file is a motor bus line
TROLLEY_SHARE = os.path.join(LEV, "trolley_share.csv")
RUN_COST = ("fill", "more")
# a boarding's ride by mode, NTD 2025, SFMTA (90015), directly operated, passenger miles over unlinked trips
#   (npsm-38gk, queried 2026-11-15): trolley bus 68,343,750 / 48,558,132, motor bus 172,527,675 / 81,134,696; a line's
#   ride is blended by its trolley share (pre-send gate round 5, R5-12). Rail lines keep the bus average, 1.86.
RIDE_MI = {"trolley": 68343750 / 48558132, "motor": 172527675 / 81134696}
RIDE_ALL = 1.86
# OpenStreetMap's names for Park Presidio's ramps, read as the street a rider knows
RAMP = re.compile(r"\bRamp\b|\bHwy\b|\bI-\d+", re.I)


def street_name(n):
    """One name a street, as the page prints it: the city file's "04th St" and "Bay Shore Blvd" and OpenStreetMap's
    "Geneva Avenue" become "4th St", "Bayshore Blvd" and "Geneva Ave"."""
    n = " ".join(w[:1].upper() + w[1:].lower() for w in n.split())
    n = re.sub(r"\b0(\d)", r"\1", n).replace("Bay Shore", "Bayshore")
    n = re.sub(r"\bMc([a-z])", lambda m_: "Mc" + m_.group(1).upper(), n)  # "Mcallister" reads as McAllister
    for long_, short_ in (("Street", "St"), ("Avenue", "Ave"), ("Boulevard", "Blvd"), ("Drive", "Dr")):
        n = re.sub(rf"\b{long_}$", short_, n)
    return n


CT_NAME = {"Crossover Drive": "Park Presidio Boulevard", "Park Presidio Bypass Drive": "Park Presidio Boulevard"}
# SFMTA's target share of scheduled service hours delivered, 98.5% since July 2026 (muni.json delivered.target, the
#   current fiscal year's from DataSF kc49-udxn; SFMTA's service delivery page: "Achieve 98.5% service delivery in
#   accordance with City Charter", https://www.sfmta.com/reports/percentage-scheduled-muni-service-hours-delivered,
#   read 2026-11-15); the fallback if muni.json carries none
FILL_TARGET = 0.985
MIN_EB_WINDOW = 25_000  # lever_car_miles.py's MIN_EB (100,000 a year) for three months: under it a line takes the pooled share
OVERRIDES = os.path.join(E, "optimizer", "built_overrides.csv")
BUS_BULBS = os.path.join(E, "optimizer", "bus_bulbs.csv")  # bus_bulbs.py
LANE_ROOM = os.path.join(E, "optimizer", "lane_room.csv")
BUILT_STATUS = ("Existing permanent transit lanes", "Implemented TETL Corridor")
NOT_BUILT = {650, 716} | {1292, 1293, 1294, 1295, 1296, 1601}  # stop_pair_lanes.py NOT_BUILT and RAIL_TRACKWAY


def thousands(costs):
    """Round each cost to the thousand so they add up to the total rounded to the thousand (largest remainder first,
    ties to the earlier fix), so the fixes listed always sum to the total shown."""
    total = int(math.floor(sum(costs) / 1000 + 0.5)) * 1000  # half up, as the page's Math.round
    fl = [int(math.floor(c / 1000)) * 1000 for c in costs]
    rest = (total - sum(fl)) // 1000
    order = sorted(range(len(costs)), key=lambda k: (-(costs[k] - fl[k]), k))
    for k in order[:max(0, rest)]:
        fl[k] += 1000
    return fl


def r(x, nd):
    return None if x is None else round(float(x), nd)


def r1(x):
    """The page's rounding to one decimal (half up, as the browser's), the figure a goal is judged on."""
    return math.floor(x * 10 + 0.5) / 10


def shown_pct(c):
    """The crowded share as the page prints it, in whole percents, as SFMTA publishes it (pre-send round 4, R13)."""
    p = c * 100
    return math.floor(p + 0.5)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_csv(path, key=None):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {row[key]: row for row in rows} if key else rows


GTFS_ZIP = os.path.join(ROOT, ".cache", "muni-gtfs", "muni_gtfs-current.zip")  # tools/muni/muni-gtfs.py --update keeps it
GTFS_FILES = ("calendar.txt", "trips.txt", "stop_times.txt", "stops.txt")  # what this build reads


def ensure_feed(zip_path=None, feed_dir=None):
    """Unpack the zip the muni-gtfs step keeps into .cache/muni-gtfs/feed/, every file in it, whenever the zip's
    SHA-256 differs from the one the folder was unpacked from (feed/.sha256) or a file this build reads is missing, so
    the timetable here and in the lever scripts that read the same folder is the pipeline's current feed, all of it
    from one zip, and never a folder somebody unzipped by hand. The mark is removed before the first file is written
    and put back after the last, and each file is written under a name of this process's own and moved into place, so
    a run that stops part way, or two at once, can't leave a mixed folder marked current. A file in the folder the zip
    doesn't carry is left alone. Without the zip the folder is left as it is and the reads below fail on what's
    missing. Returns True when it unpacked."""
    import hashlib, zipfile
    zip_path, feed_dir = zip_path or GTFS_ZIP, feed_dir or GTFS
    if not os.path.exists(zip_path):
        return False
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    mark = os.path.join(feed_dir, ".sha256")
    held = None
    if os.path.exists(mark):
        with open(mark) as f:
            held = f.read().strip()
    if held == h.hexdigest() and all(os.path.exists(os.path.join(feed_dir, n)) for n in GTFS_FILES):
        return False
    os.makedirs(feed_dir, exist_ok=True)
    if os.path.exists(mark):
        os.remove(mark)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            n = info.filename
            if info.is_dir() or n != os.path.basename(n):  # the feed is flat; nothing is written outside the folder
                continue
            part = os.path.join(feed_dir, f".{n}.{os.getpid()}.part")
            with z.open(info) as src, open(part, "wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    dst.write(chunk)
            os.replace(part, os.path.join(feed_dir, n))
    part = f"{mark}.{os.getpid()}.part"
    with open(part, "w") as f:
        f.write(h.hexdigest() + "\n")
    os.replace(part, mark)
    return True


def public_text(t):
    """A project's description without the working notes interventions.csv keeps on how its date was read ("page says
    early 2025", "date from video title", "read via repo mirror"), which aren't for the public page."""
    t = re.sub(r"\s*\([^)]*(page says|read via|date from)[^)]*\)", "", t)
    t = re.sub(r";[^;]*(page says|read via|date from)[^;]*", "", t)
    return t.strip()


def lane_built(p, today, osm_built=frozenset()):
    """stop_pair_lanes.py built_rule for one feature's properties, against the date the data was read, plus the
    undated features OpenStreetMap shows built (lanes_osm_built.json, written by stop_pair_lanes.py)."""
    if p.get("OBJECTID") in osm_built:
        return True
    if p.get("OBJECTID") in NOT_BUILT:  # stop_pair_lanes.py NOT_BUILT: Van Ness north of Chestnut, not on the street
        return False
    if p.get("STATUS") in BUILT_STATUS:
        return True
    impl = p.get("IMPLEMENT")
    return p.get("STATUS") == "Future TETL corridor" and impl is not None and \
        dt.datetime.fromtimestamp(impl / 1000, dt.timezone.utc).date().isoformat() <= today


def lane_units(lanes_open):
    """The side bus lane's levels: every whole mile eligible up to LANE_FINE, then every LANE_COARSE miles, then the
    part mile left, in tenths rounded down, when it's at least LANE_PART_MIN past the last level (docstring, "Fixes on a
    bus line"). No other cap: the top is every eligible mile (Bryan, 2026-11-16)."""
    top = math.floor(lanes_open * 10 + 1e-6) / 10
    units = [u for u in range(0, int(top) + 1) if u <= LANE_FINE or (u - LANE_FINE) % LANE_COARSE == 0]
    if top - units[-1] >= LANE_PART_MIN - 1e-9:
        units.append(round(top, 1) if top != int(top) else int(top))
    return units


def has_parking(row):
    """lane_room.py found parking on the block: the city's parking census, or OpenStreetMap's parking tags."""
    m = re.search(r"(\d+) parking spaces in the city census", row["note"])
    return bool(m and int(m.group(1)) > 0) or "parking from OSM tags" in row["note"]


def lane_class(row):
    """What a bus lane takes on a lane_room.csv block, by lanes in the bus's direction counting a parking lane as one
    (Bryan, 2026-11-16: "bus lanes up to the length of the route, minus places where there's only
    one lane and you can't have a dedicated bus lane without blocking all other traffic"): "travel" with two or more
    general lanes that way (a lane taken), "parking" with one and parking on the block (the parking taken), "none" with
    one and no parking, no lane count, a freeway ramp (Caltrans's) or a stretch SFMTA itself decided against (lanes_src
    "sfmta"). Where lane_room.py found room by width it keeps its own call (a two-lane street too narrow to keep both
    lanes and the parking gives up the parking); its width test no longer sets a block aside."""
    if RAMP.search(row["street"]) or row["lanes_src"] == "sfmta":
        return "none"
    if row["room"] in ("travel", "parking"):
        return row["room"]
    if not row["lanes_dir"].isdigit():
        return "none"
    n = int(row["lanes_dir"])
    return "travel" if n >= 2 else "parking" if n == 1 and has_parking(row) else "none"


def narrow_ok(row):
    """A lane_room.csv row with no room for a bus lane beside a travel lane where a bus lane can still go in the one
    general lane that way (docstring, "Lanes on narrow streets"): one general lane that way, not a stretch SFMTA itself
    decided against (lanes_src "sfmta": Mission northbound from 14th to Cesar Chavez, 16th eastbound from Church to
    Bryant), not a freeway ramp. Stretches in decided_against.csv never reach pair_open.json."""
    return row["room"] == "none" and row["lanes_src"] != "sfmta" and row["lanes_dir"] == "1" and not RAMP.search(row["street"])


# ---- baseline -------------------------------------------------------------------------------------------------------

# Riders on board: the weight each hour carries within a line, the dashboard's rule (site_data.py, "Riders on board";
#   Bryan, 2026-11-17, review item dodklidq3or6: "Use occupancy readings"). Each cell of a frequent line (line, month,
#   day type, hour) counts by its scheduled departures times the average load on a bus in that line, day type (weekday,
#   or weekend for Saturday and Sunday) and hour, from SFMTA's occupancy readings (optimizer/crowding_levels_hour.csv).
#   LOAD and OCC_MINREADS are site_data.py's central map and floor, and build()'s check that every line's month
#   matches muni.json's keeps the two the same.
LOAD = {"empty": 0.05, "many_seats": 0.35, "few_seats": 0.75, "standing_room": 1.2, "crushed": 1.6, "full": 1.8, "not_accepting": 1.8}
OCC_MINREADS = 20
OCC = os.path.join(E, "optimizer", "crowding_levels_hour.csv")  # crowding_update.py, the muni-crowding step
SFMTA_CROWD = os.path.join(E, "optimizer", "sfmta_crowding.csv")   # sfmta_crowding.py, the muni-sfmta-crowding step


def load_factors():
    """[(line, "weekday" or "weekend", hour, reads, load)] from SFMTA's occupancy readings, directions pooled by reads,
    for every line, day type and hour with OCC_MINREADS reads or more; sorted."""
    occ = {}
    for row in read_csv(OCC):
        a = occ.setdefault(("L" if row["line"] == "LBUS" else row["line"], row["day_type"], int(row["hour"])), [0, 0.0])
        a[0] += int(row["reads"]); a[1] += sum(int(row[k]) * v for k, v in LOAD.items())
    return [(k[0], k[1], k[2], a[0], a[1] / a[0]) for k, a in sorted(occ.items()) if a[0] >= OCC_MINREADS]


def load_lookup(occ):
    """load(line, day type, hour): the hour's own load, else the line's average for the day type, else for any day,
    else 1 (a line with no readings pools by departures), as site_data.py's coalesce."""
    own = {(l_, t, h): lf for l_, t, h, _n, lf in occ}
    acc_t, acc_l = {}, {}
    for l_, t, _h, n, lf in occ:
        a = acc_t.setdefault((l_, t), [0.0, 0]); a[0] += lf * n; a[1] += n
        b = acc_l.setdefault(l_, [0.0, 0]); b[0] += lf * n; b[1] += n
    by_t = {k: a[0] / a[1] for k, a in acc_t.items()}
    by_l = {k: a[0] / a[1] for k, a in acc_l.items()}

    def load(line, daytype, hr):
        t = "weekday" if daytype == "weekday" else "weekend"
        return own.get((line, t, hr), by_t.get((line, t), by_l.get(line, 1.0)))
    return load


def monthly_waits(lines, months):
    """{(line, month): {"swt", "awt", "eb", "w"}} from the frequent-line extract (extract_freq.csv: every hour, 5 to 22,
    of every line but SFMTA's Connector and Owl lines), cells weighted within a line by riders on board as site_data.py
    weights them. "eb" is the month's scheduled departures and "w" its weight, which pools months as the cells would."""
    con = duckdb.connect()
    con.execute("SET threads=1")
    mk = os.path.join(E, "extract_months.csv")
    con.execute(f"CREATE TABLE mk AS SELECT * FROM read_csv('{mk}', header=true)")
    ren = "CASE route WHEN 'LBUS' THEN 'L' ELSE route END"
    con.execute("CREATE TABLE occ (route VARCHAR, dt VARCHAR, hr INTEGER, reads BIGINT, lf DOUBLE)")
    con.executemany("INSERT INTO occ VALUES (?, ?, ?, ?, ?)", load_factors())
    p = os.path.join(E, "extract_freq.csv")
    open(p, "rb").close()  # for the orchestrator's read trace
    q = f"""WITH c AS (SELECT {ren} route, month, daytype, hr, sum(swt*eb)/sum(eb) swt, sum(awt*ob)/sum(ob) awt, sum(eb) eb
            FROM read_csv('{p}', header=true)
            WHERE hr BETWEEN 5 AND 22 AND swt IS NOT NULL AND awt IS NOT NULL
              AND month IN (SELECT month FROM mk WHERE kept_share >= {MINKEEP})
            GROUP BY ALL),
        cw AS (SELECT c.*, c.eb * coalesce(o.lf, ld.lf, la.lf, 1) w FROM c
            LEFT JOIN occ o ON o.route = c.route AND o.dt = CASE WHEN c.daytype = 'weekday' THEN 'weekday' ELSE 'weekend' END AND o.hr = c.hr
            LEFT JOIN (SELECT route, dt, sum(lf*reads)/sum(reads) lf FROM occ GROUP BY ALL) ld
              ON ld.route = c.route AND ld.dt = CASE WHEN c.daytype = 'weekday' THEN 'weekday' ELSE 'weekend' END
            LEFT JOIN (SELECT route, sum(lf*reads)/sum(reads) lf FROM occ GROUP BY ALL) la ON la.route = c.route)
      SELECT route, month, sum(swt*w)/sum(w) swt, sum(awt*w)/sum(w) awt, sum(eb) eb, sum(w) w
      FROM cw WHERE month IN ({", ".join(f"'{m}'" for m in months)}) GROUP BY 1, 2 ORDER BY 1, 2"""
    out = {}
    for line, month, swt, awt, eb, w in con.execute(q).fetchall():
        if line in lines:
            out[(line, month)] = {"swt": swt, "awt": awt, "eb": eb, "w": w}
    return out


# SFMTA's published weekday gap for a line, before and after a dated change, that the timetable history must reproduce
#   to 0.75 min: "More Muni Service Changes Coming June 10" (sfmta.com/blog/more-muni-service-changes-coming-june-10,
#   interventions.csv), the 44 from every 12 minutes to every 10, weekdays
SERVICE_CHECK = (("44", "2023-05", 12), ("44", "2023-07", 10))
TIMETABLE_MONTHS = os.path.join(E, "optimizer", "timetable_month.csv")  # timetable_month.py --update, the muni-timetable-history step
RIDERS = os.path.join(E, "ridership.csv")                                # fetch_ridership.py
RIDERS_PUB = os.path.join(E, "weekday_boardings_published.csv")


def monthly_timetable(lines):
    """{(line, month): {"buses", "day", "eve", "wknd"}}: each month's timetable from 511's schedules (timetable_month.py,
    the rules of peak_buses() and schedule() applied date by date): the most buses in service at once on a weekday,
    and the median gap in minutes weekdays, weekday evenings and Saturdays (the page's "weekends", as schedule_text()
    writes Saturday's gap). None where the month has no figure."""
    out = {}
    num = lambda v, f: f(v) if v not in (None, "") else None
    for row in read_csv(TIMETABLE_MONTHS):
        ln_ = "L" if row["line"] == "LBUS" else row["line"]
        if ln_ in lines:
            out[(ln_, row["month"])] = {"buses": num(row["buses"], int), "day": num(row["day"], float),
                                        "eve": num(row["eve"], float), "wknd": num(row["sat"], float)}
    return out


def monthly_riders(lines):
    """({(line, month): weekday boardings}, newest month SFMTA's systemwide figure covers), from SFMTA's route file.

    A route's name starts with its line id ("44 O'Shaughnessy"). Months after the newest one SFMTA's own systemwide
    weekday figure (measure 428) covers are left out: the route file's newest month can move a lot once it settles
    (fetch_ridership.py)."""
    pub = max(row["month"] for row in read_csv(RIDERS_PUB))
    out = {}
    for row in read_csv(RIDERS):
        ln_ = row["route"].split(" ")[0]
        if row["day"] == "Weekday" and ln_ in lines and row["month"] <= pub:
            out[(ln_, row["month"])] = float(row["boardings"])
    return out, pub


CHANGE_DAY = "2026-08-29"  # SFMTA's timetable and 511 feed change (docstring, "Baseline")
CHANGE_SHARE = 0.10        # a line whose weekday scheduled departures by hour moved by more than this share changed


def known_holidays(month):
    """The dates in a month ("YYYY-MM") Muni runs a holiday timetable whatever the year, as YYYYMMDD: New Year's Day,
    Labor Day (September's first Monday), Thanksgiving (November's fourth Thursday) and Christmas Day, each of which
    the 511 summaries list in every year they cover (diag/2026-01, 2026-09, 2025-11 and 2025-12.json). One that falls
    on a Saturday or Sunday is left out: the summaries name a day by its trips falling under its own day type's, and a
    weekend day already runs close to a holiday's."""
    y, m = int(month[:4]), int(month[5:7])
    days = []
    if m == 1:
        days.append(dt.date(y, 1, 1))
    if m == 12:
        days.append(dt.date(y, 12, 25))
    if m == 9:
        days.append(dt.date(y, 9, 1 + (7 - dt.date(y, 9, 1).weekday()) % 7))
    if m == 11:
        days.append(dt.date(y, 11, 1 + (3 - dt.date(y, 11, 1).weekday()) % 7 + 21))
    return [d.strftime("%Y%m%d") for d in days if d.weekday() < 5]


def holidays_of(months):
    """(holidays, errors): the days in these months the dashboard counts as Sundays, from the 511 summaries' own list
    (diag/<month>.json "holidays", ewt_month.py: a weekday or Saturday whose scheduled Muni trips, every line and hour,
    are under 90% of that day type's median in the month). Read from the pipeline, not found again here by departure
    volume: the count this build used to make moved when the frequent rule did, and then found no holiday at all. A
    month with no summary fails, and so does a month with a holiday known_holidays() names that the summary lacks."""
    hol, errors = set(), []
    for m in months:
        p = os.path.join(E, "diag", f"{m}.json")
        if not os.path.exists(p) or "holidays" not in (d := load_json(p)):
            errors.append(f"holidays: no list of holidays for {m} in {os.path.relpath(p, ROOT)}")
            continue
        got = {str(x) for x in d["holidays"]}
        hol |= got
        for k in known_holidays(m):
            if k not in got:
                errors.append(f"holidays: {m} has a holiday on {k} and the 511 summary lists {sorted(got) or 'none'}")
    return hol, errors


def hourly_rows(months, holidays):
    """daily/hourly-<m>.csv rows (ewt_daily.py --by-hour: a line's date and clock hour) with a day type: weekday,
    saturday or sunday, a holiday counting as sunday as the dashboard counts it (holidays_of())."""
    out = []
    for m in months:
        p = os.path.join(E, "daily", f"hourly-{m}.csv")
        if not os.path.exists(p):
            continue
        for row in read_csv(p):
            s_ = row["sdate"]
            d = dt.date(int(s_[:4]), int(s_[4:6]), int(s_[6:]))
            dtp = "sunday" if s_ in holidays or d.weekday() == 6 else "saturday" if d.weekday() == 5 else "weekday"
            out.append({**row, "daytype": dtp, "date": d})
    return out


def changed_lines(lines, months, hrows):
    """Lines whose weekday timetable changed at CHANGE_DAY, when it falls inside the window: the scheduled departures by
    clock hour, 5 to 22, averaged over the weekdays before and from that day (daily/hourly-<m>.csv), differ by more than
    CHANGE_SHARE of the larger day's total. Holidays, run on a Sunday timetable, are left out. Such a line's "Now" is
    read from that day on (since_waits()), so it isn't built on a timetable the line no longer runs."""
    if not (months[0] <= CHANGE_DAY[:7] <= months[-1]):
        return set()
    prof, days = {}, {False: set(), True: set()}
    for row in hrows:
        if row["daytype"] != "weekday" or not 5 <= int(row["hr"]) <= 22:
            continue
        d = row["date"]
        post = d.isoformat() >= CHANGE_DAY
        days[post].add(d)
        ln_ = "L" if row["route"] == "LBUS" else row["route"]
        if ln_ in lines and row["eb"] not in ("", None):
            a = prof.setdefault(ln_, {False: {}, True: {}})[post]
            a[int(row["hr"])] = a.get(int(row["hr"]), 0.0) + float(row["eb"])
    out = set()
    for ln_, pp in prof.items():
        pre = {h: v / max(1, len(days[False])) for h, v in pp[False].items()}
        post = {h: v / max(1, len(days[True])) for h, v in pp[True].items()}
        big = max(sum(pre.values()), sum(post.values()))
        if big and sum(abs(pre.get(h, 0) - post.get(h, 0)) for h in set(pre) | set(post)) > CHANGE_SHARE * big:
            out.add(ln_)
    return out


def since_waits(line, hrows, since, load):
    """(swt, awt) for a line over the days from `since`, pooled as the dashboard pools a window: each day type and
    clock hour, 5 to 22, is a cell, its timetable wait weighted by scheduled departures and its actual wait by the
    departures seen (ewt_daily.py's eba), and the cells weighted by riders on board (scheduled departures times
    load(line, day type, hour)). None where no row since then has both waits."""
    cells = {}
    for row in hrows:
        ln_ = "L" if row["route"] == "LBUS" else row["route"]
        if ln_ != line or row["date"].isoformat() < since or not 5 <= int(row["hr"]) <= 22:
            continue
        if any(row[k] in ("", None) for k in ("eb", "eba", "swt", "awt")):
            continue
        a = cells.setdefault((row["daytype"], int(row["hr"])), [0.0, 0.0, 0.0, 0.0])
        eb, eba = float(row["eb"]), float(row["eba"])
        a[0] += eb; a[1] += float(row["swt"]) * eb; a[2] += eba; a[3] += float(row["awt"]) * eba
    num_s = num_a = den = 0.0
    for (t, h), (eb, s_eb, eba, a_eba) in sorted(cells.items()):
        if not eb or not eba:
            continue
        w = eb * load(line, t, h)
        num_s += s_eb / eb * w; num_a += a_eba / eba * w; den += w
    return (num_s / den, num_a / den) if den else None


SINCE_TOL = 0.1  # minutes since_waits() over a whole month may sit from the dashboard's month (the page shows 0.1)
RUSH = (7, 8, 16, 17, 18)  # the weekday rush hours holding is credited in (lib/muni_hold.py)


def wait_cover(lines, hrows, since):
    """{line: {"weekday": [hours], "saturday": [...], "sunday": [...]}}: the clock hours, 5 to 22, of each day type the
    line runs in, so its wait figure rests on them: those with scheduled departures on half or more of that day type's
    days, from the days since `since[line]` where the line's Now starts then. Holding is credited only in the weekday
    rush hours listed (pre-send gate round 5, R5-3)."""
    seen, ndays = {}, {}
    for row in hrows:
        ln_ = "L" if row["route"] == "LBUS" else row["route"]
        if ln_ not in lines or (since.get(ln_) and row["date"].isoformat() < since[ln_]):
            continue
        ndays.setdefault((ln_, row["daytype"]), set()).add(row["date"])
        if row["eb"] not in ("", None) and float(row["eb"]) > 0 and 5 <= int(row["hr"]) <= 22:
            seen.setdefault((ln_, row["daytype"], int(row["hr"])), set()).add(row["date"])
    out = {}
    for ln_ in lines:
        out[ln_] = {t: sorted(h for (l_, t2, h), ds in seen.items() if l_ == ln_ and t2 == t and 2 * len(ds) >= len(ndays[(ln_, t)]))
                    for t in ("weekday", "saturday", "sunday")}
    return out


def usable_months():
    return sorted(m["month"] for m in read_csv(os.path.join(E, "extract_months.csv")) if float(m["kept_share"]) >= MINKEEP)


def hour_modes(gap_hours):
    """Weekday hours 5 to 22 as a string, "g" for an hour a frequent line runs and "c" for any other, from muni.json's
    schedule.gapHours ([start, end) spans; empty for a Connector line)."""
    return "".join("g" if any(a <= h < b for a, b in gap_hours or []) else "c" for h in range(5, 23))


def ontime_now(months, holidays, since=CHANGE_DAY):
    """({line: {"onTime", "early", "late", "n"}}, errors): on-time timepoint departures in SFMTA's window, 1 minute early
    to 4 late, on weekdays (holidays out, holidays_of()) on the lines SFMTA runs to set times, its Connector and Owl
    lines (ontime/<m>-lines.csv, freq 0, freq_rule.py), from `since`, SFMTA's 29 August 2026 timetable, through the window's end. A
    line with under MIN_ONTIME_N departures a month of those days has none."""
    tot, errors, days = {}, [], set()
    s0 = since.replace("-", "")
    for m in months:
        p = os.path.join(E, "ontime", f"{m}-lines.csv")
        if not os.path.exists(p):
            if m >= since[:7]:
                errors.append(f"on time: no {os.path.relpath(p, ROOT)} (ontime_month.py writes it)")
            continue
        for row in read_csv(p):
            s_ = row["sdate"]
            if s_ < s0 or row["freq"] != "0" or s_ in holidays or dt.date(int(s_[:4]), int(s_[4:6]), int(s_[6:])).weekday() > 4:
                continue
            days.add(s_)
            a = tot.setdefault(row["route"], [0, 0, 0])
            a[0] += int(row["n"]); a[1] += int(row["early_sf"]); a[2] += int(row["late_sf"])
    floor = MIN_ONTIME_N * len(days) / 21.7  # MIN_ONTIME_N a month of weekdays, prorated to the days counted
    out = {line: {"onTime": round((n - e - l) / n, 3), "early": round(e / n, 3), "late": round(l / n, 3), "n": n}
           for line, (n, e, l) in sorted(tot.items()) if n >= floor}
    if len(days) < 30:
        errors.append(f"on time: {len(days)} weekdays since {since}, under 30")
    return out, errors


ONTIME_PUB = os.path.join(E, "optimizer", "sfmta_ontime_published.csv")


def ontime_check():
    """(rows, errors): SFMTA's published systemwide on-time share for each period in sfmta_ontime_published.csv (the
    Controller's performance measures, DataSF 6dpt-7w23, "Muni on-time performance", departures 1 minute early to 4
    late) beside ours over the same months from ontime/<m>-lines.csv, every line, hour and day. The dataset-intake
    check: ours runs under SFMTA's (research/sources/511-historic-stop-observations.md, "Published total")."""
    out, errors = [], []
    for row in read_csv(ONTIME_PUB):
        y, m_ = int(row["from"][:4]), int(row["from"][5:])
        ms = []
        while f"{y}-{m_:02d}" <= row["to"]:
            ms.append(f"{y}-{m_:02d}"); y, m_ = (y + 1, 1) if m_ == 12 else (y, m_ + 1)
        n = e = l = 0
        for m in ms:
            p = os.path.join(E, "ontime", f"{m}-lines.csv")
            if not os.path.exists(p):
                errors.append(f"on time check: no {os.path.relpath(p, ROOT)}")
                continue
            for r_ in read_csv(p):
                n += int(r_["n"]); e += int(r_["early_sf"]); l += int(r_["late_sf"])
        if n:
            out.append({"from": row["from"], "to": row["to"], "sfmta": float(row["value"]), "ours": round((n - e - l) / n, 3)})
    return out, errors


def window_delivery(months, lines, holidays=frozenset()):
    """SFMTA's delivered share by mode over the page's months (lever/delivered_by_mode.csv, the mean of the months, as
    lever_car_miles.py takes it over its year), and each bus line's tracked share of its weekday scheduled departures
    over the same months (daily/<m>.csv, ewt_daily.py: a frequent line's scheduled and seen departures by date;
    Saturdays, Sundays and holidays out), so filling missed trips is sized on the window the page's waits come from
    (pre-send gate round 6, verified 9). The daily files carry the same counts as the lever model's per-stop files
    (lever_vm.sh) summed over stops: on the 16 November data the two shares agree to 0.002 for every line in
    September and October 2026 and to 0.012 for every bus line in August. A line with under MIN_EB_WINDOW scheduled
    departures, a Connector line among them, takes the pooled bus share, as the lever model pools.
    Returns ({mode: delivered}, {line: tracked share}, errors)."""
    errors = []
    by = {}
    for row in read_csv(os.path.join(LEV, "delivered_by_mode.csv")):
        if row["month"] in months:
            by.setdefault(row["mode"], []).append(float(row["delivered"]))
    dm = {k: sum(v) / len(v) for k, v in by.items() if len(v) == len(months)}
    for k in ("trolley", "motor"):
        if k not in dm or not 0.9 < dm[k] <= 1:
            errors.append(f"fill window: SFMTA's {k} delivered share for {months} is {dm.get(k)}")
    acc, pool = {}, [0.0, 0.0]
    for m in months:
        p_ = os.path.join(E, "daily", f"{m}.csv")
        if not os.path.exists(p_):
            errors.append(f"fill window: no daily file for {m}")
            continue
        for row in read_csv(p_):
            s_ = row["sdate"]
            if row["eb"] in ("", None) or row["ob"] in ("", None) or s_ in holidays \
                    or dt.date(int(s_[:4]), int(s_[4:6]), int(s_[6:])).weekday() > 4:
                continue
            a = acc.setdefault(row["route"], [0.0, 0.0])
            a[0] += float(row["eb"]); a[1] += float(row["ob"])
    rt = {r_["route"]: r_["route_type"] for r_ in read_csv(os.path.join(E, "ref", "route_types.csv"))}
    for r_, (eb, ob_) in acc.items():
        if rt.get(r_) == "3":
            pool[0] += eb; pool[1] += ob_
    pooled = pool[1] / pool[0] if pool[0] else None
    obs = {}
    for l_ in lines:
        eb, ob_ = acc.get(l_, (0.0, 0.0))
        obs[l_] = ob_ / eb if eb >= MIN_EB_WINDOW else pooled
    return dm, obs, errors


def peak_buses(lines):
    """{line: (buses, "HH:MM")}: the most buses a line has in service at once on a weekday, from SFMTA's GTFS timetable
    (.cache/muni-gtfs/feed, the weekday service in calendar.txt). Each block (one bus's day) is on a line from a trip's
    first departure to its next trip's first departure when that comes within LAYOVER_GAP, so layover counts, else to
    the trip's last arrival; the count is taken minute by minute."""
    cal = read_csv(os.path.join(GTFS, "calendar.txt"))
    wk = [c["service_id"] for c in cal if all(c[d] == "1" for d in ("monday", "tuesday", "wednesday", "thursday", "friday"))]
    con = duckdb.connect()
    con.execute("SET threads=1")
    q = f"""WITH t AS (SELECT route_id, trip_id, block_id FROM read_csv('{os.path.join(GTFS, "trips.txt")}', header=true, all_varchar=true)
                 WHERE service_id IN ({", ".join(f"'{x}'" for x in wk)})),
            st AS (SELECT trip_id, min(departure_time) a, max(arrival_time) b
                   FROM read_csv('{os.path.join(GTFS, "stop_times.txt")}', header=true, all_varchar=true) GROUP BY 1)
            SELECT t.route_id, t.block_id, st.a, st.b, t.trip_id FROM t JOIN st USING (trip_id) ORDER BY 2, 3, 5"""
    sec = lambda x: int(x[:-6]) * 3600 + int(x[-5:-3]) * 60 + int(x[-2:])
    blocks = {}
    for rt, b, a, e, _ in con.execute(q).fetchall():
        blocks.setdefault(b, []).append((sec(a), sec(e), rt))
    cnt = {}
    for b in sorted(blocks):
        ts = blocks[b]
        for i, (a, e, rt) in enumerate(ts):
            end = ts[i + 1][0] if i + 1 < len(ts) and ts[i + 1][0] - e < LAYOVER_GAP else e
            c = cnt.setdefault(rt, np.zeros(48 * 60, dtype=int))
            c[a // 60:max(a // 60 + 1, end // 60)] += 1
    out = {}
    for ln_ in lines:
        c = cnt.get(ln_)
        if c is not None and c.max() > 0:
            k = int(c.argmax())
            out[ln_] = (int(c.max()), f"{k // 60:02d}:{k % 60:02d}")
    return out


SCHED_DAYS = {"weekday": "M11", "sat": "2", "sun": "3"}  # calendar.txt's weekday, Saturday and Sunday services
# hours each headway is taken over. Evening is 8 to 11 pm, our choice: SFMTA's 2025 Title VI Program Update sets
#   "Evening" policy headways (Tables 4 and 5) without naming its hours, and its only PM period is the crowding one,
#   "PM (4pm-7pm) peak" (p. 43, read 2026-11-15); from 7 pm the 1 still runs every 4 to 5 minutes until about 8, so a
#   7 pm start read "6 evenings" for a line that runs every 12 all evening.
SCHED_WIN = {"weekday": (7, 19), "evening": (20, 23), "sat": (7, 19), "sun": (7, 19)}
MIDDAY = (10, 15)       # a weekday with no departure in these hours, either way, runs at rush hours only (the 8AX, 8BX)
ALL_NIGHT_GAP = 3600    # seconds: a weekday whose longest gap between departures, round the clock, is at most this runs all night


def departures(lines):
    """({(line, service, direction): sorted seconds after midnight}, the same at the busiest stop) from SFMTA's GTFS
    timetable (.cache/muni-gtfs/feed), for the services in SCHED_DAYS. The first: each trip's departure from its first
    stop, for the span. The second: every departure at the direction's busiest stop, the one the most trips serve that
    day (a trip's last stop, where it only arrives, and a loop's second call at a stop not counted; on a tie the one nearest the start of its trips, then the lowest
    stop_id, so a line with one pattern keeps its first stop and a rerun picks the same stop), for the gaps: a line whose trips
    start at more than one terminal, or short-turn, has its full frequency only where its patterns overlap (the 38's
    first stops alone give 15 minutes at 6 pm where its busiest stop has a bus every 8)."""
    con = duckdb.connect()
    con.execute("SET threads=1")
    q = f"""CREATE TABLE x AS WITH t AS (SELECT route_id, service_id, direction_id, trip_id
                       FROM read_csv('{os.path.join(GTFS, "trips.txt")}', header=true, all_varchar=true)
                       WHERE service_id IN ({", ".join(f"'{x}'" for x in SCHED_DAYS.values())}))
            SELECT route_id, service_id, direction_id, trip_id, stop_id, departure_time d, CAST(stop_sequence AS INTEGER) seq,
              seq = min(seq) OVER (PARTITION BY trip_id) AS is_first, seq = max(seq) OVER (PARTITION BY trip_id) AS is_last
            FROM t JOIN read_csv('{os.path.join(GTFS, "stop_times.txt")}', header=true, all_varchar=true) USING (trip_id)
            QUALIFY row_number() OVER (PARTITION BY trip_id, stop_id ORDER BY seq) = 1"""
    con.execute(q)
    busy = """SELECT x.route_id, x.service_id, x.direction_id, x.d FROM x JOIN (SELECT route_id, service_id, direction_id, stop_id
                FROM x WHERE NOT is_last GROUP BY route_id, service_id, direction_id, stop_id QUALIFY row_number() OVER (PARTITION BY route_id, service_id, direction_id
                ORDER BY count(*) DESC, median(seq), stop_id) = 1) b USING (route_id, service_id, direction_id, stop_id) WHERE NOT x.is_last"""
    sec = lambda x: int(x[:-6]) * 3600 + int(x[-5:-3]) * 60 + int(x[-2:])
    out = ({}, {})
    for i, q_ in enumerate(("SELECT route_id, service_id, direction_id, d FROM x WHERE is_first", busy)):
        for rt, sv, d, x in con.execute(q_).fetchall():
            if rt in lines:
                out[i].setdefault((rt, sv, d), []).append(sec(x))
    return tuple({k: sorted(v) for k, v in sorted(o.items())} for o in out)


def median_gap(ts, win):
    """The median gap in minutes, rounded half up to a whole minute, between consecutive departures inside the hours
    win = (from, to), or None with under two departures there."""
    a = [t for t in ts if win[0] * 3600 <= t < win[1] * 3600]
    g = sorted(q - p for p, q in zip(a, a[1:]))
    if not g:
        return None
    m = g[len(g) // 2] if len(g) % 2 else (g[len(g) // 2 - 1] + g[len(g) // 2]) / 2
    return int(math.floor(m / 60 + 0.5))


SCHED_TEXT_MAX = 58     # characters: the longest timetable line that fits one line on a 390-wide phone (checked 2026-11-15)


def clock(t, step=15):
    """Seconds after midnight to the nearest `step` minutes, "5 am", "10:30 pm", "12 am" (shorter than "midnight", so the
    43's line fits a phone): the 36's last trip at 22:24 is "10:30 pm", not "10 pm"."""
    q = int(math.floor(t / (step * 60) + 0.5)) % (1440 // step)
    h, m = divmod(q * step, 60)
    return f"{h % 12 or 12}{f':{m:02d}' if m else ''} {'am' if h < 12 else 'pm'}"


def schedule(dep, line, at_stop=None):
    """A line's basic timetable: the median gap at the busier direction's busiest stop (at_stop, departures()'s second
    part; the direction with more departures there that day, direction 0 on a tie) over SCHED_WIN's hours for weekdays,
    weekday evenings, Saturdays and Sundays; the weekday span from its first to its last departure from a first stop
    either way (dep); and one line of text. at_stop defaults to dep. None where the timetable has no weekday trips."""
    at_stop = dep if at_stop is None else at_stop
    wk = {d: dep.get((line, SCHED_DAYS["weekday"], d), []) for d in ("0", "1")}
    if not wk["0"] and not wk["1"]:
        return None
    s = {}
    for day, sv in SCHED_DAYS.items():
        ds = [at_stop.get((line, sv, d), []) for d in ("0", "1")]
        busy = ds[0] if len(ds[0]) >= len(ds[1]) else ds[1]
        for win in (("weekday", "evening") if day == "weekday" else (day,)):
            s[win] = median_gap(busy, SCHED_WIN[win])
    both = sorted(wk["0"] + wk["1"])
    rush = not any(MIDDAY[0] * 3600 <= t < MIDDAY[1] * 3600 for t in both)
    day = sorted({t % 86400 for t in both})
    gaps = [(day[(i + 1) % len(day)] - day[i]) % 86400 or 86400 for i in range(len(day))]
    i = max(range(len(gaps)), key=lambda k: (gaps[k], -k))
    s["allNight"] = gaps[i] <= ALL_NIGHT_GAP
    s["first"], s["last"] = (None, None) if s["allNight"] else (day[(i + 1) % len(day)], day[i])
    s["rushOnly"] = rush
    s["text"] = schedule_text(s)
    return s


def schedule_text(s):
    """One short line a phone 390 wide shows whole (SCHED_TEXT_MAX), so the first figure, weekday daytime, goes unnamed beside evenings
    and weekends: "Every 6 min, 10 evenings, 8 weekends · 5 am to 1 am"."""
    wk, ev, sa, su = s["weekday"], s["evening"], s["sat"], s["sun"]
    if s["rushOnly"]:
        return f"Every {wk} min, weekday rush hours only"
    if wk is not None and ev in (None, wk) and sa == wk and su == wk:
        head = f"Every {wk} min all week"
    else:
        head = f"Every {wk} min" + (f", {ev} evenings" if ev is not None and ev != wk else "")
        if sa is None and su is None:
            head = f"Every {wk} min weekdays only" if head == f"Every {wk} min" else head + ", weekdays only"
        elif sa == su:
            head += f", {sa} weekends"
        else:
            head += "".join(f", {v} {k}" for k, v in (("Sat", sa), ("Sun", su)) if v is not None)
    if s["allNight"]:
        return head + " · all night"
    # the span to the quarter hour, or the half hour, then the hour, where the finer one would wrap on a phone
    for step in (15, 30, 60):
        text = head + f" · {clock(s['first'], step)} to {clock(s['last'], step)}"
        if len(text) <= SCHED_TEXT_MAX:
            break
    return text


def more_units(peak, per_hour=None):
    """The more-buses fix's levels: MORE_SHARES of the line's peak buses, rounded half up to whole buses, distinct, up
    to the share that brings the busiest stop's busiest hour (per_hour departures today, busier direction) to STOP_CAP,
    which is the last level."""
    top = STOP_CAP / per_hour - 1 if per_hour else MORE_SHARES[-1]
    shares = [x for x in MORE_SHARES if x < top] + [top]
    return sorted({int(math.floor(peak * x + 1e-9 if x == top else peak * x + 0.5)) for x in shares})


def busiest_hour(at_stop, line):
    """The most departures in one clock hour at the busier direction's busiest stop on a weekday (departures()'s second
    part), or None."""
    best = 0
    for d in ("0", "1"):
        ts = at_stop.get((line, SCHED_DAYS["weekday"], d), [])
        for h in range(4, 26):
            best = max(best, sum(1 for t in ts if h * 3600 <= t < (h + 1) * 3600))
    return best or None


def bulb_units(cand):
    """The bulb fix's levels: BULB_STEPS up to the line's stops with no bulb, then every one of them."""
    return sorted({u for u in BULB_STEPS if u <= cand} | ({cand} if cand > 0 else set()))


def more_trim(menu, base, ln):
    """The more-buses levels up to the first that takes the line's crowding, middle case, to 0% as the page shows it,
    every other fix at none; all of them where the line has no crowding figure or already shows 0%, where more buses
    are for the wait alone."""
    ix = [m["id"] for m in menu]
    if "more" not in ix or not base.get("crowd") or shown_pct(base["crowd"]) == 0:
        return
    k = ix.index("more")
    units = np.zeros((len(menu[k]["units"]), len(menu)))
    units[:, k] = menu[k]["units"]
    crowd = evaluate(menu, base, ln, units, "mid")["crowd"]
    zero = [i for i, c in enumerate(crowd) if shown_pct(c) == 0]
    if zero:
        menu[k]["units"] = menu[k]["units"][:zero[0] + 1]


# ---- the model --------------------------------------------------------------------------------------------------------

def fix_effects(kind, ln, levers, lanes_open, stops_on_line, line="", errors=None, bulb_cand=None, counts=None,
                skip=(), rate=1.0, peak=None, per_hour=None):
    """Per-unit effects of each fix on one line from the lever model's rows, middle case at the top level and every
    case under "case". Returns the menu list.

    A fix on the kind's menu with no lever-model row is a check failure (appended to `errors`), except stop removal on
    a Rapid (a line ending in R), which the lever model leaves out by design: a Rapid already skips local stops.

    More buses: the lever model's row is 10% more trips; a unit here is one bus at the busiest hour, peak buses being
    the line's (peak_buses()), so its cost and wait part a unit are the row's over 0.1 x peak, and its new riders follow
    the row's own elasticity, (1 + s) ** e - 1 with e = ln(1 + its riders) / ln(1.1), for s more service."""
    menu = []
    for fx in FIXES[kind]:
        if fx["id"] in skip:
            continue
        row = levers.get(fx["lever"])
        if row is None:
            if not (fx["id"] == "stops" and line.endswith("R")) and errors is not None:
                errors.append(f"line {line}: the lever model has no row for {fx['lever']}")
            continue
        cost = float(row["cost_mid"])
        ann = ln["annual"]
        wait_part = float(row["wpd_mid"] or 0) * cost  # the lever model's minutes, at its own cost
        if fx["id"] in RUN_COST:
            cost *= rate
        per = 1.0  # units of the lever model's row in one unit here
        if fx["id"] == "more":
            if not peak:
                if errors is not None:
                    errors.append(f"line {line}: no peak bus count for more buses")
                continue
            per = 1 / (0.1 * peak)
            cost *= per
            wait_part *= per
        freq = float(row["freq_min_mid"] or 0)
        ride = (float(row["rider_min_mid"]) - freq - wait_part) / ann
        units = fx["units"]
        if units == "more":
            units = more_units(peak, per_hour)
        if units == "lane":
            units = lane_units(lanes_open)
        if units == "bulb":
            units = bulb_units(stops_on_line if bulb_cand is None else min(stops_on_line, bulb_cand))
        mid = {"ride_share": ride / ln["ride_min"] if fx["id"] not in WAIT_PART else 0.0,
               "bus_share": float(row["cycle_cut_mid"] or 0) / (K_MID * ln["run_share"]),
               "riders": float(row["new_rides_mid"]) / ann * per,
               "wait_share": (wait_part / ann) / ln[WAIT_PART[fx["id"]]] if fx["id"] in WAIT_PART else 0.0}
        case = {}
        wm = float(row["wpd_mid"] or 0)
        # a time fix's low and high scale by the lever model's ride minutes in that case alone, its frequency minutes
        #   and any wait part taken out first, so the applied effect stays inside the study's own range (pre-send gate
        #   round 3, V5: scaling on rider minutes with the frequency minutes in put signal priority's high at 8.6% where
        #   its study's is 8%); the frequency gain comes from the case's own K in evaluate(). Stop removal's measured
        #   walk stays fixed.
        ride_c = lambda c: float(row[f"rider_min_{c}"]) - float(row[f"freq_min_{c}"] or 0) - wait_part
        for c in CASES:
            if fx["id"] not in WAIT_PART:
                s = ride_c(c) / ride_c("mid") if ride_c("mid") else 1.0
            elif fx["id"] in WAIT_PART:  # the wait minutes in that case: wpd at the middle cost, or at the case's own
                #   cost for filling trips, whose cost scales with the trips filled (lever_car_miles.py SCALES)
                cc = float(row[f"cost_{c}"]) / float(row["cost_mid"]) if fx["id"] == "fill" else 1.0
                s = float(row[f"wpd_{c}"] or 0) * cc / wm if wm else 1.0
            case[c] = {"ride_share": mid["ride_share"] * s, "bus_share": mid["bus_share"] * s,
                       "wait_share": mid["wait_share"] * s, "riders": float(row[f"new_rides_{c}"]) / ann * per}
            if fx["id"] == "more":
                case[c]["elast"] = math.log(1 + float(row[f"new_rides_{c}"]) / ann) / math.log(1.1)
        up = 0.0
        n = (counts or {}).get(fx["id"], 1)
        if fx["id"] in CAPITAL:
            up = cost / crf(CAPITAL[fx["id"]][1])
            want = CAPITAL[fx["id"]][0] * SOFT * n
            if counts is not None and errors is not None and abs(up - want) > 0.005 * want:
                errors.append(f"line {line}: {fx['id']} up front {up:.0f} spread over its life isn't the lever model's "
                              f"cost; Fast Forward's unit cost gives {want:.0f}")
        # each case's effect a unit, in percent of what it acts on: the ride for time fixes, its wait part otherwise
        eff = [100 * (case[c]["wait_share"] if fx["id"] in WAIT_PART else case[c]["ride_share"]) for c in CASES]
        # running cost a unit a year: the lever model's yearly cost for a fix with nothing up front; a build fix's yearly
        #   cost is its up-front cost spread over its life, so it runs at its upkeep alone (signal priority's, a signal
        #   times the line's open signals; none for the others)
        run = (UPKEEP[fx["id"]][1] * n if fx["id"] in UPKEEP else 0.0) if fx["id"] in CAPITAL else cost
        menu.append({"id": fx["id"], "label": fx["label"], "unit": fx["unit"], "units": units, "cost": cost, "up": up, "run": run, "eff": eff,
                     **mid, "cycle_cut": float(row["cycle_cut_mid"] or 0),
                     **({"step": 1 / peak, "elast": case["mid"]["elast"]} if fx["id"] == "more" else {}),
                     "walk": -wait_part / ann if fx["id"] == "stops" else 0.0, "case": case})
    return menu


def evaluate(menu, base, ln, units, case="mid"):
    """Every mix at once, in one case. units: int array (mixes x fixes). Returns dict of arrays."""
    n = len(units)
    ix = {m["id"]: i for i, m in enumerate(menu)}
    u = lambda k: units[:, ix[k]].astype(float) if k in ix else np.zeros(n)

    def one(k, f):
        if k not in ix:
            return 0.0
        m = menu[ix[k]]
        return m["case"][case][f] if "case" in m and f in m["case"][case] else m[f]
    n_lane, tsp = u("lane"), u("tsp")
    r_lane = n_lane * one("lane", "ride_share")
    r_tsp = tsp * one("tsp", "ride_share") * (1 - r_lane)
    r_stop = u("stops") * one("stops", "ride_share") + u("bulb") * one("bulb", "ride_share")
    b_lane = n_lane * one("lane", "bus_share")
    b_tsp = tsp * one("tsp", "bus_share") * (1 - b_lane)
    b_total = b_lane + b_tsp + u("stops") * one("stops", "bus_share") + u("bulb") * one("bulb", "bus_share")
    raw = r_lane + r_tsp + r_stop
    cap = np.ones(n) if base.get("ceiling") is None else np.minimum(1.0, base["ceiling"] / np.maximum(raw, 1e-12))
    b_total = b_total * cap
    x = K_CASE[case] * b_total * ln["run_share"]
    # more service as a share of today's: a unit is a bus at the busiest hour (step 1 / peak buses), or 10% in a menu
    #   that gives no step
    s_more = u("more") * (one("more", "step") if "more" in ix and "step" in menu[ix["more"]] else 0.1)
    swt = base["swt"] * (1 - x) / (1 + s_more)
    # a share can come out a hair over 1 from rounding upstream (fill's high case, 1.0000003 to 1.000005), which would
    #   make the wait part negative (Fable review of 6050fea1, finding 4)
    spacing = base["spacing"] * (1 - u("hold") * np.minimum(1.0, one("hold", "wait_share")))
    missing = base["missing"] * (1 - u("fill") * np.minimum(1.0, one("fill", "wait_share")))
    wait = swt + spacing + missing + base["weighting"]
    r_ride = raw * cap
    ride = base["ride_min"] * (1 - r_ride)
    mph = base["mph"] / (1 - r_ride)
    riders = np.ones(n)
    for i, mm in enumerate(menu):
        if mm["id"] == "more" and "elast" in mm:
            # new riders at the row's own elasticity to frequency, so twice the buses doesn't draw ten times 10%'s
            riders = riders + (1 + s_more) ** one("more", "elast") - 1
        elif mm["id"] not in NO_CROWD:
            # riders a speed fix draws scale with the share of its ride time the delay ceiling lets through, as its
            #   ride time does (Fable review of 6050fea1, finding 2); walking added by removed stops doesn't
            riders = riders + units[:, i] * one(mm["id"], "riders") * (cap if mm["id"] in ("tsp", "lane", "stops", "bulb") else 1.0)
    freq = 1 / (1 - x) * (1 + s_more) * np.where(u("fill") > 0, (ln["obs_share"] + (1 - ln["obs_share"]) * ln["fill_true"]) / ln["obs_share"], 1.0)
    crowd = np.clip(base["crowd"] * riders / freq, 0, 1)
    walk = u("stops") * one("stops", "walk")
    cost, up, up10, run = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    for i, mm in enumerate(menu):
        cost = cost + units[:, i] * mm["cost"]
        up = up + units[:, i] * mm.get("up", 0.0)
        up10 = up10 + units[:, i] * mm.get("up", 0.0) * builds(mm["id"])
        run = run + units[:, i] * mm.get("run", 0.0 if mm["id"] in CAPITAL else mm["cost"])
    gain = 2 * (base["wait"] - wait) + (base["ride_min"] - ride) - 2 * walk + CROWD_W * base["ride_min"] * (base["crowd"] - crowd)
    return {"cost": cost, "up": up, "run": run, "cost10": up10 + YEARS * run, "wait": wait, "mph": mph, "ride": ride, "crowd": crowd, "walk": walk, "gain": gain,
            "r_lane": r_lane, "r_tsp": r_tsp, "r_stop": r_stop, "r_ride": r_ride, "cap": cap, "x": x}


def double_count(line, menu, units, ev):
    """Errors if any mix credits signal priority and lanes with the same seconds.

    Lane seconds are n x r1 of the ride; priority's are its share of the time left after the lanes. So in every mix
    priority plus lanes must equal r_lane + rt x (1 - r_lane), and where both are bought, priority's credit must be
    strictly under its share on a line with no lane."""
    ids = [m["id"] for m in menu]
    if "tsp" not in ids:
        return []
    k = ids.index("tsp")
    rt = menu[k]["ride_share"]
    want = ev["r_lane"] + units[:, k] * rt * (1 - ev["r_lane"])
    errs = []
    if np.abs(ev["r_lane"] + ev["r_tsp"] - want).max() > 1e-12:
        errs.append(f"line {line}: signal priority and lane seconds don't add to their combined share")
    both = (units[:, k] > 0) & (ev["r_lane"] > 0)
    if both.any() and np.any(ev["r_tsp"][both] >= rt):
        errs.append(f"line {line}: signal priority is credited on laned miles' seconds twice")
    return errs


def all_mixes(menu):
    if not menu:
        return np.zeros((1, 0), dtype=float)
    return np.array(list(itertools.product(*[m["units"] for m in menu])), dtype=float)


def tenth(v):
    """A figure in whole tenths as the page shows it (r1), so a target compares as an integer."""
    return int(math.floor(v * 10 + 0.5))


def line_mixes(x):
    """A shipped line's combinations as the page expands them: (cost10, build, run, units, level, gain), level being
    [wait, mph] in tenths and crowding in whole percents, middle case, None where the line has no figure. Each fix's
    cost is priced from its units with thousands(), so build and running cost add to what the page shows; build is the
    first build, and cost10 counts each fix's rounded build once for each time it is built in the ten years."""
    fx, g = x["fixes"], x["grid"]
    out = []
    for i, u in enumerate(itertools.product(*[f["units"] for f in fx])):
        bp = thousands([v * f["unitUp"] for v, f in zip(u, fx)])
        b, b10 = sum(bp), sum(p * f["builds"] for p, f in zip(bp, fx))
        rn = sum(thousands([v * f["unitRun"] for v, f in zip(u, fx)]))
        lv = [tenth(g["wait"][1][i]) if g["wait"] else None, tenth(g["mph"][1][i]),
              shown_pct(g["crowd"][1][i]) if g["crowd"] else None]
        out.append((b10 + YEARS * rn, b, rn, list(u), lv, g["gain"][i]))
    return out


def shortfall(lv, t):
    """Steps a level falls short of targets t = [wait, mph, crowd] (tenths, tenths, points; None for no target)."""
    s = 0
    if t[0] is not None and lv[0] is not None:
        s += max(0, lv[0] - t[0])
    if t[1] is not None and lv[1] is not None:
        s += max(0, t[1] - lv[1])
    if t[2] is not None and lv[2] is not None:
        s += max(0, lv[2] - t[2])
    return s


def choose_targets(mixes, t):
    """The targets' pick (index, met): the combination meeting every target with the least ten-year cost (ties: the
    larger time saved, then the first); where none meets them, the smallest shortfall first. The page's chooseTargets
    (transportation-muni-optimizer.mjs) is this function over the same shipped figures."""
    k = min(range(len(mixes)), key=lambda i: (shortfall(mixes[i][4], t), mixes[i][0], -mixes[i][5], i))
    return k, shortfall(mixes[k][4], t) == 0


def target_options(mixes):
    """Each control's reachable levels at least as good as today's (the no-fix combination, first), today's first."""
    t = mixes[0][4]
    out = []
    for g, better in enumerate((lambda a, b: a <= b, lambda a, b: a >= b, lambda a, b: a <= b)):
        vs = {m[4][g] for m in mixes if m[4][g] is not None and better(m[4][g], t[g])}
        out.append(sorted(vs, reverse=(g != 1)) if t[g] is not None else [])
    return out


def next_step(mixes, t, g):
    """What the next reachable step on control g costs over ten years beyond targets t: (step, added cost), or None."""
    opts = target_options(mixes)[g]
    nxt = [v for v in opts if (v > t[g] if g == 1 else v < t[g])]
    k0, met0 = choose_targets(mixes, t)
    if not nxt or not met0:
        return None
    t2 = list(t); t2[g] = nxt[0]
    k, met = choose_targets(mixes, t2)
    return (abs(nxt[0] - t[g]), mixes[k][0] - mixes[k0][0]) if met else None


# ---- map --------------------------------------------------------------------------------------------------------------

FT_LAT = 364000.0
def to_ft(lon, lat, lat0):
    return np.c_[np.asarray(lon) * FT_LAT * math.cos(math.radians(lat0)), np.asarray(lat) * FT_LAT]


def dist_to_lines(pts, lines_ft):
    """Each point's distance in feet to the nearest segment of any polyline."""
    best = np.full(len(pts), np.inf)
    for ln in lines_ft:
        a, b = ln[:-1], ln[1:]
        ab = b - a
        L2 = (ab ** 2).sum(1)
        L2[L2 == 0] = 1e-9
        for k in range(0, len(pts), 2000):
            p = pts[k:k + 2000, None, :]
            t = np.clip(((p - a) * ab).sum(2) / L2, 0, 1)
            d = np.sqrt((((a + t[..., None] * ab) - p) ** 2).sum(2)).min(1)
            best[k:k + 2000] = np.minimum(best[k:k + 2000], d)
    return best


def line_map(line, mp, detail, signals, lanes_geo, boardings, pairs, no_bulb, open_paths=None, removed=(), open_kept=None, built_bb=None,
             gstops=None):
    """The map's parts, and the built lane features near the line (their properties and drawn feet) for the history."""
    L = mp["lines"].get(line)
    if not L or not L.get("shape"):
        return None, []
    lat0 = 37.76
    shp = [to_ft([c[0] for c in s], [c[1] for c in s], lat0) for s in L["shape"] if len(s) > 1]
    sig_xy = to_ft([s[0] for s in signals], [s[1] for s in signals], lat0)
    near = dist_to_lines(sig_xy, shp) < 60
    rd5 = lambda c: [round(c[0], 5), round(c[1], 5)]
    tsp = sorted(rd5(signals[i][:2]) for i in np.where(near)[0] if signals[i][2])
    # a signal the layer marks planned is priced with the rest: none has priority in any public source (pre-send round 5)
    open_ = sorted(rd5(signals[i][:2]) for i in np.where(near)[0] if not signals[i][2])
    # built lanes: the parts of each feature within 80 ft of the line (the feature densified every 50 ft), so a long
    #   feature the line runs on for only part of its length (Market St) is drawn and counted for that part; a run under
    #   300 ft (a cross street) isn't drawn. lane_dir keeps each drawn part's one-way direction for added_on_built.
    lanes, near_lanes, lane_dir = [], [], []
    for coords, props in lanes_geo:
        if len(coords) < 2:
            continue
        dense = []
        for a, b in zip(coords[:-1], coords[1:]):
            fa, fb = to_ft([a[0], b[0]], [a[1], b[1]], lat0)
            k = max(1, int(math.hypot(*(fb - fa)) // 50))
            dense.extend([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t] for t in np.arange(k) / k)
        dense.append(list(coords[-1]))
        xy = to_ft([c[0] for c in dense], [c[1] for c in dense], lat0)
        near_ = dist_to_lines(xy, shp) < 80
        runs, start = [], None
        for i, v in enumerate(list(near_) + [False]):
            if v and start is None:
                start = i
            elif not v and start is not None:
                runs.append((start, i)); start = None
        drawn_ft = 0.0
        for a, b in runs:
            ft = float(np.sqrt((np.diff(xy[a:b], axis=0) ** 2).sum(1)).sum())
            if ft < 300:
                continue
            lanes.append([rd5(c) for c in dense[a:b]])
            lane_dir.append((props.get("DIRECTION") or "Both").strip().lower())
            drawn_ft += ft
        if drawn_ft > 0:
            near_lanes.append((props, drawn_ft))
    stops = {s["stop"]: s for s in mp["stops"]}
    # lanes built since the layer's last edit (built_overrides.csv), drawn stop to stop as built
    ovr_ft = 0.0
    for row in pairs:
        if row.get("override") and row["s0"] in stops and row["s1"] in stops:
            a, b = stops[row["s0"]], stops[row["s1"]]
            lanes.append([rd5([a["lon"], a["lat"]]), rd5([b["lon"], b["lat"]])])
            dx, dy = (b["lon"] - a["lon"]) * math.cos(math.radians(lat0)), b["lat"] - a["lat"]
            lane_dir.append(("eastbound" if dx > 0 else "westbound") if abs(dx) > abs(dy) else ("northbound" if dy > 0 else "southbound"))
            ovr_ft += float(row["feet"])
    order_ = sorted(range(len(lanes)), key=lambda i: (lanes[i], lane_dir[i] if i < len(lane_dir) else "both"))
    lane_dir = [lane_dir[i] if i < len(lane_dir) else "both" for i in order_]
    lanes = [lanes[i] for i in order_]
    # new lanes on the slowest open stop-to-stop stretches, from the same file that counts the open miles
    #   (pair_lanes.csv, share_built_any under half), slowest first by the 90-day speed to the next stop. Stretches run
    #   each way, so a street mile with a lane both ways is two stretch-miles: the running total is half the feet.
    sa = {}
    for d in ("0", "1"):
        sa.update((detail["lines"].get(line, {}).get("90", {}).get("speedAlong") or {}).get(d, {}).get("pairs", {}))
    # each stretch's open path, along the route, outside every built lane (stop_pair_lanes.py pair_open.json); a
    #   stretch entered by hand as built (an override) has none
    cand = []
    # drawn from the open path itself, so a stretch whose stops muni-map.json doesn't carry is drawn too (pre-send gate
    #   round 3, V7: the 7 drew 0.35 of its 5 priced miles)
    for row in pairs:
        if row.get("override"):
            continue
        key = f"{line} {row['s0']} {row['s1']}"
        mph_ = (sa.get(f"{row['s0']}-{row['s1']}") or {}).get("mph")
        # a stretch's parts beside a travel lane come first, all lines' slowest first, then its parts on narrow streets,
        #   where the lane takes the only general lane (docstring, "Lanes on narrow streets")
        for nar in (False, True):
            segs = [sg for sg, n_ in (open_paths or {}).get(key, []) if n_ == nar]
            ft = float(row.get("open_feet") or 0) * (open_kept or {}).get(key, {}).get(nar, 0.0)
            if segs and ft > 0:
                cand.append((nar, mph_ is None, mph_ or 0.0, row["s0"], row["s1"], ft, segs))
    cand.sort(key=lambda c: c[:6])
    new_lanes, new_pairs, cum = [], [], 0.0
    for nar, _, _, s0, s1, ft, segs in cand:
        for seg in segs:
            new_lanes.append({"c": seg, "m0": round(cum, 3), **({"g": 1} if nar else {})})
        new_pairs.append(((f"{line} {s0} {s1}", nar), cum))
        cum += ft / 5280 / 2
    # bulb candidates: distinct stops on the line, from its stop order each way (muni-map.json "order", the current
    #   schedule) and the schedule's stop positions, not from the map's stops with a wait figure, so a line with no
    #   wait figure still gets them (pre-send gate round 5, R5-2); none built
    ids = lambda c_: int(c_[1:]) if c_[1:].isdigit() else -1
    # never a bulb at a stop the stop-removal fix takes out (pre-send gate round 3: Van Ness & Bay on the 30 and 49)
    gone = {int(x["stop_code"]) for x in removed}
    codes = sorted({c_ for d_ in (L.get("order") or {}).values() for c_ in d_})
    on_line = [c_ for c_ in codes if c_ in (gstops or {}) and ids(c_) not in no_bulb and ids(c_) not in gone]
    # the line's stops with a bulb or island built (bus_bulbs.csv), each place once: [lon, lat, 1 for an island]
    built = []
    for c_ in codes:
        b_ = (built_bb or {}).get(ids(c_))
        if b_:
            pt = [round(float(b_["lon"]), 5), round(float(b_["lat"]), 5), 1 if b_["kind"] == "island" else 0]
            if pt not in built:
                built.append(pt)
    ranked = sorted(on_line, key=lambda c_: (-boardings.get(ids(c_), 0.0), c_))
    # every stop with none built, busiest first; two codes at one spot (rounded to 5 places) are one place for a bulb
    bulbs = []
    for c_ in ranked:
        if rd5(gstops[c_]) not in bulbs:
            bulbs.append(rd5(gstops[c_]))
    # each removed stop's riders as the rule ranked it: this line's share of the stop's 2020 weekday boardings
    #   (stop_walk_stops.csv), not every line's at the stop (pre-send gate round 6, R6-2)
    rem = [{"c": [round(float(x["lon"]), 5), round(float(x["lat"]), 5)], "n": x["name"],
            "b": round(float(x["boardings"]))}
           for x in removed]
    return ({"shape": [[rd5(c) for c in s] for s in L["shape"]], "color": L.get("color"), "lanes": lanes, "tsp": tsp,
             "open": open_, "newLanes": new_lanes, "bulbs": bulbs, "removed": rem, "bulbCand": len(bulbs), "bulbsBuilt": built,
             "ovrFt": ovr_ft, "laneDir": lane_dir, "newPairs": new_pairs, "newMiles": cum,
             }, near_lanes)


ONEWAY = {"eastbound": (1, 0), "westbound": (-1, 0), "northbound": (0, 1), "southbound": (0, -1)}


def added_on_built(line, mapd):
    """Errors when a new lane is drawn on a built one: over 5% of the added lanes' points (densified every 25 ft)
    within 30 ft of a built lane's line that serves the same direction. A one-way built lane the other way (Mission
    St's southbound lane beside a new northbound one) is the street's other side, not the same lane: the page draws
    new lanes offset to their right. The direction is each leg's own, so a piece that turns a corner (the 14's
    eastbound Mission St leg beside the built westbound lane, then up Beale) is judged leg by leg (pre-send gate
    round 6: judged on the piece's overall heading, that leg read as westbound)."""
    if not mapd["newLanes"] or not mapd["lanes"]:
        return []
    lat0 = 37.76
    dirs = mapd.get("laneDir") or ["both"] * len(mapd["lanes"])
    built = [(to_ft([c[0] for c in l_], [c[1] for c in l_], lat0), d_) for l_, d_ in zip(mapd["lanes"], dirs) if len(l_) > 1]
    n = hit = 0
    for nl in mapd["newLanes"]:
        xy = to_ft([c[0] for c in nl["c"]], [c[1] for c in nl["c"]], lat0)
        for a, b in zip(xy[:-1], xy[1:]):
            hd = b - a
            same = [bb for bb, d_ in built if d_ not in ONEWAY or hd[0] * ONEWAY[d_][0] + hd[1] * ONEWAY[d_][1] > 0]
            k = max(1, int(np.hypot(*hd) // 25))
            pts = [a + hd * t for t in np.linspace(0, 1, k + 1)]
            n += len(pts)
            if same:
                hit += int((dist_to_lines(np.array(pts), same) < 30).sum())
    on = hit / n if n else 0.0
    return [f"line {line}: {on:.0%} of the new lanes drawn lie on a built lane"] if on > 0.05 else []


def lane_history(near_lanes):
    """Built lanes near the line, one row per street stretch, dated where SFMTA's layer has an IMPLEMENT date."""
    rows = {}
    for p, _ in near_lanes:
        street = (p.get("ST_NAME") or "").strip()
        if not street or street == "TETL":
            street = (p.get("CORRIDOR") or "").strip() or "Temporary emergency transit lane"
        impl = p.get("IMPLEMENT")
        date = dt.datetime.fromtimestamp(impl / 1000, dt.timezone.utc).date().isoformat() if impl is not None else None
        key = (street, (p.get("FROM_ST") or "").strip().rstrip("`"), (p.get("TO_ST") or "").strip().rstrip("`"))
        if key not in rows or (date and (rows[key] is None or date < rows[key])):
            rows[key] = date
    return sorted(({"street": k[0], "from": k[1], "to": k[2], "date": d} for k, d in rows.items()),
                  key=lambda x: (x["date"] or "9999", x["street"], x["from"], x["to"]))


# ---- build ------------------------------------------------------------------------------------------------------------

def build(evals=None):
    """(errors, the month's results). evals, a dict, receives each line's (units, evaluation in every case), so the
    tests can check what the page shows for a combination against the evaluation itself."""
    errors = []
    ensure_feed()
    muni = load_json(os.path.join(SITE, "muni.json"))
    mp = load_json(os.path.join(SITE, "muni-map.json"))
    detail = load_json(os.path.join(SITE, "muni-lines.json"))
    # every bus line on the picker and the Metro lines (lever_car_miles.py, "Lines"; lib/muni_bus_lines.py)
    LN = read_csv(os.path.join(O, "car_miles_lines_all.csv"), "line")
    SW = read_csv(os.path.join(O, "stop_walk.csv"), "line")
    BL = {}
    for row in read_csv(os.path.join(O, "car_miles_by_line_all.csv")):
        BL.setdefault(row["line"], {})[row["lever"]] = row
    base_csv = {row["baseline"]: float(row["value"]) for row in read_csv(os.path.join(O, "roi_baselines.csv"))}
    run_share = 1 / (1 + base_csv["layover share of running time, frequent bus lines"])
    sf_rows = read_csv(SFMTA_CROWD)
    crowd_months = sorted({c["month"] for c in sf_rows})[-CROWD_MONTHS:]
    sf_crowd, sf_all = {}, {}
    for c in sf_rows:
        sf_all.setdefault(c["route"], {})[c["month"]] = float(c["pct"]) / 100
        if c["month"] in crowd_months:
            sf_crowd.setdefault(c["route"], {})[c["month"]] = float(c["pct"]) / 100
    ovr = read_csv(OVERRIDES)
    lane_ovr = {(o["route"], o["s0"], o["s1"]) for o in ovr if o["kind"] == "lane"}
    bulb_ovr = {o["stop"] for o in ovr if o["kind"] in ("bulb", "nobulb")}
    for o in ovr:
        if o["kind"] not in ("lane", "bulb", "nobulb", "signal", "segment", "nooffer") or not o["source"].startswith("https://") or not o["read"]:
            errors.append(f"overrides: row {o} has no kind, source or read date")
    # stop ids compared as numbers: stop_types.csv writes 19th Ave & Holloway as 390, muni-map.json as 10390
    # built bulbs and islands (bus_bulbs.py: SFMTA's stop file plus project drawings), drawn on the map and never offered
    built_bb = {int(row["stop_id"]): row for row in read_csv(BUS_BULBS)}
    no_bulb = {int(row["stopid"]) for row in read_csv(os.path.join(E, "optimizer", "stop_types.csv"))} | {int(x) for x in bulb_ovr} | set(built_bb)
    stop_ids = {int(s["stop"][1:]) for s in mp["stops"] if s["stop"][1:].isdigit()}
    for sid in sorted(bulb_ovr):
        if int(sid) not in stop_ids:
            errors.append(f"overrides: bulb stop {sid} isn't a mapped stop")
    trolley = {row["line"]: float(row["trolley_share"]) for row in read_csv(TROLLEY_SHARE)}
    removed = {}
    for row in read_csv(os.path.join(O, "stop_walk_stops.csv")):
        removed.setdefault(row["line"], []).append(row)
    open_paths = load_json(os.path.join(LEV, "pair_open.json"))
    # room for a lane (lane_room.py): each open segment's feet by class; a segment where most of the street has no
    #   room for a bus lane and a travel lane that way is neither priced nor drawn, and the line's lane fix names the
    #   streets where the lane takes parking (pre-send gate round 3, 2026-11-15)
    room, seg_room = {}, {}
    for row in read_csv(LANE_ROOM):
        k = (f"{row['route']} {row['s0']} {row['s1']}", int(row["seg"]))
        a = seg_room.setdefault(k, {})
        # a freeway ramp is Caltrans's, as a state highway is (pre-send gate round 5, R5-1): no room for our ask
        rm = lane_class(row)
        a[rm] = a.get(rm, 0.0) + float(row["feet"])
        room.setdefault(row["route"], []).append(row)
    # open_ok: each stretch's offered segments as (path, narrow); open_kept: the share of its open feet offered, as
    #   {False: beside a travel lane, True: on a narrow street}
    open_ok, open_kept, kept_idx = {}, {}, {}
    for key, segs in open_paths.items():
        keep, tot, kept = [], 0.0, {False: 0.0, True: 0.0}
        for i_, seg in enumerate(segs):
            a = seg_room.get((key, i_))
            if a is None:
                errors.append(f"lane room: no lane_room.csv row for {key} segment {i_}")
                continue
            ft = sum(a.values())
            tot += ft
            # a stretch with no lane count and no width (unchecked) is treated as no room: the page asks for a lane
            #   only where it has checked one fits (pre-send gate round 4, R4: lower Market and Ocean Avenue were offered
            #   unchecked)
            no_room = a.get("none", 0.0) + a.get("unchecked", 0.0)
            if no_room + a.get("general", 0.0) < 0.5 * ft:
                keep.append((seg, False))
                kept_idx.setdefault(key, {})[i_] = False
                kept[False] += ft - no_room - a.get("general", 0.0)
            elif no_room < 0.5 * ft:
                # a narrow street: the lane takes the one general lane that way (docstring, "Lanes on narrow streets")
                keep.append((seg, True))
                kept_idx.setdefault(key, {})[i_] = True
                kept[True] += ft - no_room
        open_ok[key] = keep
        open_kept[key] = {k_: v / tot if tot else 0.0 for k_, v in kept.items()}
    pl, pair_rows, seen_ovr = {}, {}, set()
    for row in read_csv(os.path.join(LEV, "pair_lanes.csv")):
        if (row["route"], row["s0"], row["s1"]) in lane_ovr:
            row = {**row, "share_built_any": "1.0", "override": "1"}
            seen_ovr.add((row["route"], row["s0"], row["s1"]))
        # a pair the line no longer runs (stop_pair_lanes.py "Current": the 6 off Market Street since 2025) is neither
        #   counted nor drawn
        if row["current"] != "1":
            if row.get("override"):
                errors.append(f"overrides: lane stretch {(row['route'], row['s0'], row['s1'])} isn't run today")
            continue
        pair_rows.setdefault(row["route"], []).append(row)
        a = pl.setdefault(row["route"], [0.0, 0.0, 0.0])
        a[0] += float(row["feet"]) * float(row["share_built_any"] or 0)
        a[1] += float(row["feet"])
        a[2] += 0.0 if row.get("override") else float(row.get("open_feet") or 0) * sum(open_kept.get(f"{row['route']} {row['s0']} {row['s1']}", {}).values())
    for k in sorted(lane_ovr - seen_ovr):
        errors.append(f"overrides: lane stretch {k} isn't in pair_lanes.csv")
    sig, planned = [], 0
    xtra = muni_signals.override_cnns()
    for s in load_json(os.path.join(LEV, "signals.json")):
        if s.get("shape") and s.get("type") in ("SIGNAL", "CALTRANS"):
            c = s["shape"]["coordinates"] if isinstance(s["shape"], dict) else json.loads(s["shape"].replace("'", '"'))["coordinates"]
            on = muni_signals.has_tsp(s, xtra)
            sig.append((c[0], c[1], on, not on and "TSP-Planned" in (s.get("preempt_pr") or "")))
    want_tsp = muni_signals.LAYER_TSP + len(xtra)
    if sum(s[2] for s in sig) != want_tsp:
        errors.append(f"signals.json: {sum(s[2] for s in sig)} signals with priority, the lever model counts {want_tsp}")
    months = muni["windows"]["90"]["monthList"]
    target_dlv = muni["delivered"].get("target") or FILL_TARGET
    holidays, e_ = holidays_of(months)
    errors += e_
    dlv_w, obs_w, e_ = window_delivery(months, list(LN), holidays)
    errors += e_
    y, mo = int(months[-1][:4]), int(months[-1][5:])
    waits_through = (dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
    # the date 511's newest month in the window was read (read_511.csv, vm_local.sh writes it from each month's DONE
    #   marker; pre-send gate round 5, R5-13), never before the month closed
    reads = {row["month"]: row["read"] for row in read_csv(os.path.join(E, "read_511.csv"))}
    if months[-1] not in reads:
        errors.append(f"read_511.csv has no read date for {months[-1]}")
    waits_read = reads.get(months[-1], waits_through)
    lanes_geo = []
    osm_built = frozenset(load_json(os.path.join(LEV, "lanes_osm_built.json")))
    excluded = load_json(os.path.join(LEV, "pair_excluded.json"))
    for f in load_json(os.path.join(LEV, "lanes.geojson"))["features"]:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        if not lane_built(p, waits_through, osm_built):
            continue
        if g.get("type") == "LineString":
            lanes_geo.append((g["coordinates"], p))
        elif g.get("type") == "MultiLineString":
            lanes_geo.extend((c, p) for c in g["coordinates"])
    # a lane built since the layer's last edit, entered as a street stretch (built_overrides.csv kind "segment", the
    #   lane stop_pair_lanes.py counts as built): drawn and dated as built, its year from the row's note
    for i, o in enumerate(x for x in ovr if x["kind"] == "segment"):
        coords = [[float(v) for v in xy.split()] for xy in o["path"].split(";")]
        yr = re.search(r"in (?:early |late )?(\d{4})", o["note"])
        street, _, span = o["where"].partition(",")
        frm, _, to = span.strip().split(" (")[0].partition(" to ")
        one = re.search(r"\b(north|south|east|west)bound\b", street)  # a one-way lane names its direction
        lanes_geo.append((coords, {"OBJECTID": -1 - i, "STATUS": BUILT_STATUS[0],
                                   "DIRECTION": one.group(1).capitalize() + "bound" if one else "Both",
                                   "ST_NAME": re.split(r" both| (?:north|south|east|west)bound", street)[0], "FROM_ST": frm, "TO_ST": to,
                                   "IMPLEMENT": int(dt.datetime(int(yr.group(1)), 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000) if yr else None}))
    # each stop's position on the current schedule, by the five-digit code 511 and muni-map.json use
    gstops = {row["stop_code"]: [float(row["stop_lon"]), float(row["stop_lat"])]
              for row in read_csv(os.path.join(ROOT, ".cache", "muni-gtfs", "feed", "stops.txt")) if row["stop_code"]}
    boardings = {}
    for row in read_csv(os.path.join(LEV, "stop_boardings_2020.csv")):
        boardings[int(float(row["stopid"]))] = float(row["boardings"])
    # steps in a line's series we have looked into and can't explain, marked on its history (a step change is
    #   a question); data/muni-ewt/optimizer/series_steps.csv carries the checks run
    #   A row may blank one of the line's series before its month ("blank": "mph"), where the months before aren't
    #   measured the same way, and may name the calendar year before a step ("before_year") and the step
    #   ("before_what"), so the page can set the line's wait in that year beside today's (pre-send gate round 6)
    steps, blank, before = {}, {}, {}
    for row in read_csv(os.path.join(E, "optimizer", "series_steps.csv")):
        steps.setdefault(row["line"], []).append({"month": row["month"], "text": row["text"]})
        if row.get("blank"):
            blank.setdefault(row["line"], []).append((row["blank"], row["month"]))
        if row.get("before_year"):
            before[row["line"]] = (row["before_year"], row["before_what"])
    projects = {}
    for row in read_csv(os.path.join(E, "interventions.csv")):
        projects.setdefault(row["line"], []).append(
            {"date": row["date"], "type": row["type"], "text": public_text(row["description"]), "url": row["source_url"]})

    use = usable_months()
    if len(months) != 3 or any(m not in use for m in months):
        errors.append(f"three full months: the window is {months}")
    # the history starts at the usable month after which no gap runs over a year: September 2019, the archive's one
    #   month before 2022, would stand alone on the charts (pre-send gate round 6, verified 11)
    trend_months = [m for m in use if m <= months[-1]]
    mi = lambda m: int(m[:4]) * 12 + int(m[5:])
    cut = max([k for k in range(1, len(trend_months)) if mi(trend_months[k]) - mi(trend_months[k - 1]) > 12], default=0)
    trend_months = trend_months[cut:]
    lines = sorted(LN, key=lambda l: (LN[l]["kind"] != "bus", l))
    waits = monthly_waits(set(lines), trend_months)
    service = monthly_timetable(set(lines))
    # the timetable and riders come from SFMTA's own schedule and counts, not the 511 stop records, so they run every
    #   month of the history's span, the months the stop records are too thin for included
    y0, m0 = map(int, trend_months[0].split("-"))
    all_months = [f"{y0 + (m0 - 1 + k) // 12}-{(m0 - 1 + k) % 12 + 1:02d}" for k in range(mi(trend_months[-1]) - mi(trend_months[0]) + 1)]
    riders, riders_pub = monthly_riders(set(lines))
    for m in months:
        if not os.path.exists(os.path.join(E, "daily", f"hourly-{m}.csv")):
            errors.append(f"hourly rows: no daily/hourly-{m}.csv, so the hours each line runs and holding can't be read")
    hrows = hourly_rows(months, holidays)
    changed = changed_lines(set(lines), months, hrows)
    load = load_lookup(load_factors())
    cover = wait_cover(set(lines), hrows, {l_: CHANGE_DAY for l_ in changed})
    ontime, e_ = ontime_now(months, holidays)
    ot_check, e2_ = ontime_check()
    errors += e_ + e2_
    peaks = peak_buses(lines)
    dep = departures(set(lines))
    out_lines = {}
    for line in lines:
        row = LN[line]
        kind = row["kind"]
        if line not in muni["lines"] or "trend" not in muni["lines"][line]:
            errors.append(f"line {line}: muni.json has no trend for it")
            continue
        t = {x["month"]: x for x in muni["lines"][line]["trend"]}
        # a line SFMTA runs to set times, a Connector line, has no wait figure (docstring, "No wait figure"): the
        #   dashboard marks it (muni.json "frequent", freq_rule.py), and it must have no row in the frequent-line
        #   extract. Every other line must have a wait in each of the three months, as it must a speed.
        frequent = muni["lines"][line].get("frequent")
        if frequent is None:
            errors.append(f"line {line}: muni.json doesn't say whether SFMTA counts it frequent")
            continue
        nogap = not frequent
        if nogap and any((line, m) in waits for m in trend_months):
            errors.append(f"line {line}: the dashboard counts it infrequent, and the frequent-line extract has rows for it")
            continue
        miss = [m for m in months if ((line, m) not in waits and not nogap) or t.get(m, {}).get("mph") is None]
        if miss:
            errors.append(f"three full months: line {line} has no wait or speed in {miss}")
            continue
        wb = [] if nogap else [waits[(line, m)] for m in months]
        ebs = sum(w["w"] for w in wb)  # months pooled by their cells' weight, as the dashboard pools a window
        swt = sum(w["swt"] * w["w"] for w in wb) / ebs if ebs else 0.0
        awt = sum(w["awt"] * w["w"] for w in wb) / ebs if ebs else 0.0
        since = None
        if line in changed and not nogap:
            # its weekday timetable changed on 29 August: "Now" from the days since (docstring, "Baseline")
            sw_ = since_waits(line, hrows, CHANGE_DAY, load)
            if sw_ is None:
                errors.append(f"line {line}: no hourly rows since {CHANGE_DAY}")
                continue
            swt, awt = sw_
            since = CHANGE_DAY
            # the days' rows pooled over a whole month must give the dashboard's month, or "since" is another figure
            for m in months:
                rows_m = [row for row in hrows if row["sdate"][:6] == m.replace("-", "")]
                got = since_waits(line, rows_m, f"{m}-01", load)
                if got is None or max(abs(got[0] - waits[(line, m)]["swt"]), abs(got[1] - waits[(line, m)]["awt"])) > SINCE_TOL:
                    errors.append(f"line {line} {m}: the hourly rows give waits {got}, the dashboard's cells "
                                  f"{waits[(line, m)]['swt']:.3f} and {waits[(line, m)]['awt']:.3f}, over {SINCE_TOL} apart")
        for m in trend_months:
            w, d = waits.get((line, m)), t.get(m, {})
            if w and d.get("ewt") is not None and abs((w["awt"] - w["swt"]) - d["ewt"]) > 0.002:
                errors.append(f"line {line} {m}: excess wait {w['awt'] - w['swt']:.3f} here, {d['ewt']} on the dashboard")
        parts = {k: np.mean([t[m][k] for m in months]) if all(t[m].get(k) is not None for m in months) else None
                 for k in ("spacing", "missing", "weighting")}
        ewt = awt - swt
        if nogap:
            parts = {"spacing": 0.0, "missing": 0.0}
        elif parts["spacing"] is None or since:
            # no split on the dashboard, or a baseline from part of the window: the dashboard's shares of its months'
            #   excess wait, else the lever model's own, applied to this baseline's excess wait
            if parts["spacing"] is not None and (tw := sum(parts.values())):
                parts = {"spacing": ewt * parts["spacing"] / tw, "missing": ewt * parts["missing"] / tw}
            else:
                tot = float(row["ewt"])
                parts = {"spacing": ewt * float(row["spacing"]) / tot, "missing": ewt * float(row["missing"]) / tot}
        parts["weighting"] = ewt - parts["spacing"] - parts["missing"]  # so the parts add to this window's excess wait
        mph = float(np.mean([t[m]["mph"] for m in months]))
        hrs = [h["mph"] for h in muni["windows"]["365"]["lineSpeedHours"].get(line, []) if h.get("mph")]
        fast = max(hrs) if hrs else None
        if fast is None:
            errors.append(f"line {line}: muni.json has no speed by hour, so there's no delay ceiling")
            continue
        sc = sf_crowd.get(line, {})
        crowd = sum(sc.values()) / len(sc) if crowd_months and len(sc) == len(crowd_months) else None
        ts = trolley.get(line, 0.0)
        ride_mi = ts * RIDE_MI["trolley"] + (1 - ts) * RIDE_MI["motor"] if kind == "bus" else RIDE_ALL
        base = {"swt": swt, "ewt": ewt, "wait": swt + ewt, **parts, "mph": mph, "ride_min": ride_mi / mph * 60, "crowd": crowd or 0.0,
                "ceiling": max(0.0, 1 - mph / fast)}
        ln = {"annual": float(row["annual"]), "ride_min": float(row["ride_min"]), "run_share": run_share,
              "obs_share": float(row["obs_share"]), "spacing": float(row["spacing"]), "missing": float(row["missing"]),
              "swt": float(row["swt"]), "fill_true": float(row["fill_true"])}
        laned_share = pl[line][0] / pl[line][1] if line in pl and pl[line][1] else 0.0
        miles = float(row["oneway_miles"])
        open_pair_miles = pl[line][2] / 5280 / 2 if line in pl else 0.0
        lanes_open = min(miles * (1 - laned_share), open_pair_miles)
        mapd, near_lanes = line_map(line, mp, detail, sig, lanes_geo, boardings, pair_rows.get(line, []), no_bulb,
                                    open_ok, removed.get(line, []), open_kept, built_bb, gstops)
        sw = SW.get(line)
        stops_on_line = int(sw["stops_on_line"]) if sw else int(row["stops"])
        n_removed = int(float(sw["stops_removed"])) if sw else 0
        counts = {"tsp": int(float(row["signals_open"])) if row.get("signals_open") not in (None, "", "nan") else 1,
                  "lane": 1, "stops": n_removed, "bulb": 1}
        rate = (ts * RATE["trolley"] + (1 - ts) * RATE["motor"]) / LEVER_RATE
        # a fix the line can't be priced for is left off its menu, and the page says why (notes.left): stop removal where
        #   no stop qualifies or the line already skips stops, signal priority where every signal on it has it, holding
        #   on a Connector line, which has no gap between buses to hold to
        skip = (("stops",) if kind == "bus" and n_removed == 0 else ()) + (("hold",) if nogap else ()) + \
            (("tsp",) if kind == "bus" and counts["tsp"] == 0 else ())
        menu = fix_effects(kind, ln, BL.get(line, {}), lanes_open, stops_on_line, line, errors,
                           bulb_cand=mapd["bulbCand"] if mapd else None, counts=counts, skip=skip, rate=rate,
                           peak=peaks.get(line, (None,))[0], per_hour=busiest_hour(dep[1], line))
        # holding only in the weekday rush hours this line runs, effect and supervisors both (pre-send gate round 5,
        #   R5-3): the 9R runs in all five
        rush_f = sum(1 for h in RUSH if h in cover.get(line, {}).get("weekday", [])) / len(RUSH)
        # missed trips, sized on the page's own three months (window_delivery): of the trips 511 didn't track, the
        #   share SFMTA's delivered figure for the line's modes says didn't run (fill_true), filled in the middle only
        #   up to SFMTA's current 98.5% target (fill_phi; half that in the low), the high still every untracked trip;
        #   a line already at the target has no fill on its menu (pre-send gate round 6, R6-1 and verified 9). The
        #   lever model's row is sized on its twelve months: its middle fills (1 - its delivered share) of departures,
        #   this one (target - the window's delivered share), so cost and riders scale by their ratio, and the wait
        #   share by the ratio of the filled shares of untracked trips.
        dlv = ts * dlv_w.get("trolley", 1.0) + (1 - ts) * dlv_w.get("motor", 1.0) if kind == "bus" else float(row["delivered"])
        obs = obs_w.get(line) if kind == "bus" and obs_w.get(line) else float(row["obs_share"])
        ft_w = max(0.0, min(1.0, (1 - dlv) / (1 - obs))) if obs < 1 else 0.0
        fill_phi = max(0.0, min(1.0, (target_dlv - dlv) / (1 - dlv))) if dlv < 1 else 0.0
        ft_12, dep_12 = float(row["fill_true"]), (1 - float(row["obs_share"])) * float(row["fill_true"])
        dep_w = (1 - obs) * ft_w * fill_phi
        for m_ in menu:
            if m_["id"] == "hold":
                f_, fw = rush_f, rush_f
            elif m_["id"] == "fill":
                f_ = dep_w / dep_12 if dep_12 > 0 else 0.0
                fw = ft_w * fill_phi / ft_12 if ft_12 > 0 else 0.0
            else:
                continue
            m_["cost"] *= f_
            m_["run"] = m_["cost"]  # a running cost, sized on the window as its yearly cost is
            m_["wait_share"] *= fw
            m_["riders"] *= f_
            for c in (("low", "mid", "high") if m_["id"] == "hold" else ("low", "mid")):
                m_["case"][c]["wait_share"] *= fw
                m_["case"][c]["riders"] *= f_
            m_["eff"] = [100 * m_["case"][c]["wait_share"] for c in CASES]
        menu = [m_ for m_ in menu if m_["cost"] > 0 or m_["id"] not in ("hold", "fill")]
        if kind == "bus":
            ln["obs_share"] = obs
        ln["fill_true"] = ft_w * fill_phi  # the share of untracked trips the middle fills, for the crowding's frequency
        if mapd and kind == "bus":
            if len({tuple(b) for b in mapd["bulbs"]}) != len(mapd["bulbs"]):
                errors.append(f"line {line}: bulb markers repeat a stop")
            if any(m_["id"] == "stops" for m_ in menu) and len(mapd["removed"]) != n_removed:
                errors.append(f"line {line}: {len(mapd['removed'])} stops listed as removed, {n_removed} priced")
            errors += added_on_built(line, mapd)
        notes = {}
        if kind == "bus":
            # each fix on the bus menu this line isn't offered, with its reason, for the page (docstring, "Fixes left out")
            have = {m_["id"] for m_ in menu if max(m_["units"]) > 0}
            why = {"tsp": "every signal on the line has it already",
                   "lane": "no open stretch left where one fits",
                   "stops": "the line already skips most stops" if line in SKIPS_STOPS else "no stop meets our rules for removal",
                   "bulb": "no stop left without one",
                   "hold": "it runs to a timetable, so there's no gap between buses to even out" if nogap else
                           "it doesn't run in the weekday rush hours",
                   "fill": f"its buses already run SFMTA's target of {target_dlv:.1%} of scheduled hours",
                   "more": "no count of its buses in SFMTA's timetable"}
            notes["left"] = [[fx["id"], why[fx["id"]]] for fx in FIXES["bus"] if fx["id"] not in have]
        lane_fix = next((m_ for m_ in menu if m_["id"] == "lane"), None)
        if lane_fix and max(lane_fix["units"]) > 0 and mapd:
            # the streets the offered lanes take parking on, from the stretches drawn up to the most miles offered
            offered = {k for (k, _), m0 in mapd["newPairs"] if m0 < max(lane_fix["units"])}
            park = sorted({street_name(r_["street"]) for r_ in room.get(line, []) if lane_class(r_) == "parking"
                           and f"{line} {r_['s0']} {r_['s1']}" in offered})
            if park:
                notes["room"] = park
            # what each offered stretch's lane takes, street by street, in the order the menu buys them: [miles in
            #   before it, street, "travel", "parking" or "general", miles], so the row can say how much of the ask
            #   takes a traffic lane, how much the parking and how much a narrow street's only general lane (pre-send
            #   gate round 5, R5-5)
            m0_of = dict(mapd["newPairs"])
            parts = {}
            for r_ in room.get(line, []):
                k_ = f"{line} {r_['s0']} {r_['s1']}"
                nar = kept_idx.get(k_, {}).get(int(r_["seg"]))
                if nar is None or (k_, nar) not in m0_of or RAMP.search(r_["street"]):
                    continue
                rm_ = lane_class(r_)
                rm_ = rm_ if rm_ in ("travel", "parking") else None
                if rm_:
                    st_ = street_name(r_["street"])
                    a_ = (round(m0_of[(k_, nar)], 3), st_, rm_)
                    parts[a_] = parts.get(a_, 0.0) + float(r_["feet"]) / 5280 / 2
            notes["laneParts"] = [[m0, st_, rm, round(v, 3)] for (m0, st_, rm), v in sorted(parts.items())]
        # state highways on the line where no lane is offered, Caltrans's to decide (pre-send gate round 5, R5-1)
        ct = sorted({street_name(CT_NAME.get(n, n)) for k_, v in excluded.items() if k_.split(" ")[0] == line and v.get("state", 0) >= 200
                     for n in v["stateNames"]})
        # a street that's a state highway only in part (Mission St's south end) and offered elsewhere isn't named
        ct = [n for n in ct if n not in {p_[1] for p_ in notes.get("laneParts", [])}]
        if ct and kind == "bus":
            notes["caltrans"] = ct
            # drawn against priced (pre-send gate round 3, V7): every mile the menu sells is on the map
            drawn_mi = mapd["newMiles"]
            if drawn_mi < 0.9 * max(lane_fix["units"]):
                errors.append(f"line {line}: {drawn_mi:.2f} miles of new lane drawn, {max(lane_fix['units'])} priced")
        for m_ in menu:
            if not (math.isfinite(m_["cost"]) and m_["cost"] > 0):
                errors.append(f"line {line}: {m_['id']} has no cost ({m_['cost']})")
            if abs(K_MID * m_["bus_share"] * run_share - m_["cycle_cut"]) > 1e-9:
                errors.append(f"line {line}: {m_['id']} cycle cut {K_MID * m_['bus_share'] * run_share} against {m_['cycle_cut']}")
        more_trim(menu, base, ln)
        units = all_mixes(menu)
        ev = {c: evaluate(menu, base, ln, units, c) for c in CASES}
        errors += double_count(line, menu, units, ev["mid"])
        for c in CASES:
            if ev[c]["r_ride"].max() > base["ceiling"] + 1e-12:
                errors.append(f"line {line}: a mix saves {ev[c]['r_ride'].max():.3f} of the ride ({c}), over the line's delay")
        if evals is not None:
            evals[line] = (units, ev)
        # every combination of fix levels, one array per figure in all_mixes' order (the page indexes it by the levels
        #   chosen); the page prices each fix from its units and the whole-dollar unit cost with thousands(), as here,
        #   so they add up
        n = math.prod(len(m_["units"]) for m_ in menu)
        for i in range(len(units)):
            for key_, f_ in (("up", "up"), ("run", "run")):
                fc = thousands([float(units[i][k]) * round(menu[k][f_]) for k in range(len(menu))])
                if abs(sum(fc) - ev["mid"][key_][i]) > 500 * max(1, len(menu)):
                    errors.append(f"line {line}: a mix's {key_} costs add to {sum(fc)}, not its total {ev['mid'][key_][i]:.0f}")
        # each level rounded once, from the model's own value, to the step the page shows and judges a goal on (a tenth
        #   of a minute or mph, a whole percent), so the page's tenth() and shownPct() read it back exactly
        series = lambda f, rd: [[rd(v) for v in ev[c][f]] for c in CASES]
        grid = {"wait": None if nogap else series("wait", r1), "mph": series("mph", r1),
                "crowd": series("crowd", lambda v: shown_pct(v) / 100) if crowd is not None else None,
                "walk": [r(v, 3) for v in ev["mid"]["walk"]], "gain": [r(v, 3) for v in ev["mid"]["gain"]]}
        lens = [len(v) for k in ("wait", "mph", "crowd") if grid[k] for v in grid[k]] + [len(grid["walk"]), len(grid["gain"])]
        if len(units) != n or any(k != n for k in lens):
            errors.append(f"line {line}: the grid has {sorted(set(lens))} values a series for {n} combinations")
        # lanes drawn on the map against the laned miles counted from pair_lanes.csv
        if mapd and kind == "bus":
            drawn = (sum(ft for _, ft in near_lanes) + mapd["ovrFt"]) / 5280
            counted = miles * laned_share
            if abs(drawn - counted) > max(0.5, 0.5 * counted) and abs(drawn / 2 - counted) > max(0.5, 0.5 * counted):
                errors.append(f"line {line}: {drawn:.2f} miles of built lane drawn, {counted:.2f} counted")
        # history: month by month since the earliest usable month
        hist = {"wait": [], "mph": [], "crowd": [], "day": [], "eve": [], "wknd": [], "buses": [], "riders": []}
        gone = blank.get(line, [])
        for m in all_months:
            sv = service.get((line, m), {})
            for g in ("day", "eve", "wknd"):
                hist[g].append(r(sv.get(g), 2))
            hist["buses"].append(sv.get("buses"))
            hist["riders"].append(int(round(riders[(line, m)] / 100) * 100) if (line, m) in riders else None)
        for m in trend_months:
            w = waits.get((line, m))
            hist["wait"].append(r(w["awt"], 2) if w and not any(g == "wait" and m < b for g, b in gone) else None)
            hist["mph"].append(r(t.get(m, {}).get("mph"), 2) if not any(g == "mph" and m < b for g, b in gone) else None)
            hist["crowd"].append(r(sf_all.get(line, {}).get(m), 3))
        bef = None
        if line in before:
            yr, what = before[line]
            vs = [hist["wait"][k] for k, m in enumerate(trend_months) if m[:4] == yr and hist["wait"][k] is not None]
            if len(vs) < 6:
                errors.append(f"line {line}: under six months of wait in {yr} for the before line")
            else:
                bef = {"year": yr, "what": what, "lo": min(vs), "hi": max(vs)}
        last12 = trend_months[-12:]
        k12 = [trend_months.index(m) for m in last12]
        rng = {g: [min(v), max(v)] if (v := [hist[g][k] for k in k12 if hist[g][k] is not None]) else None for g in ("wait", "mph")}
        gap_hours = (muni["lines"][line].get("schedule") or {}).get("gapHours")
        freq_eb = np.mean([w["eb"] for w in wb]) if wb else 0.0
        built_sig = int(row["signals"]) if row.get("signals") not in (None, "", "nan") else None
        tsp_sig = int(row["signals_tsp"]) if row.get("signals_tsp") not in (None, "", "nan") else None
        out_lines[line] = {
            "kind": kind,
            "today": {"wait": None if nogap else r(base["wait"], 2), "swt": None if nogap else r(swt, 2),
                      "ewt": None if nogap else r(ewt, 2), "mph": r(mph, 2),
                      "crowd": r(crowd, 3) if crowd is not None else None},
            "since": since,
            "range12": {g: [r(v[0], 2), r(v[1], 2)] if v else None for g, v in rng.items()},
            "hours": hour_modes(gap_hours), "fewGap": bool(freq_eb < FEW_FREQ) and not nogap, "noGap": nogap,
            # today's on-time share where the line has no wait figure, shown with no control (docstring, "On time")
            "onTime": ontime[line]["onTime"] if nogap and kind == "bus" and line in ontime else None,
            "built": {"signals": built_sig, "tspSignals": tsp_sig, "miles": r(miles, 2), "laneMiles": r(miles * laned_share, 2),
                      "stops": stops_on_line},
            "fixes": [{"id": m_["id"], "label": m_["label"], "unit": m_["unit"], "units": m_["units"],
                       "unitUp": int(round(m_["up"])), "builds": builds(m_["id"]), "unitRun": int(round(m_["run"])),
                       "eff": [r(v, 3) for v in m_["eff"]],
                       **({"removed": counts["stops"]} if m_["id"] == "stops" else {}),
                       **({"signals": counts["tsp"]} if m_["id"] == "tsp" else {})} for m_ in menu],
            "notes": notes, "trolley": r(trolley.get(line, 0.0), 3) if kind == "bus" else None,
            "fillTrue": r(ln["fill_true"], 3) if kind == "bus" else None, "rushHeld": r(rush_f, 2) if kind == "bus" else None,
            "cover": None if nogap else cover.get(line), "rideMi": r(ride_mi, 2), "before": bef,
            # what running the line costs a year today: its peak buses times a bus's yearly cost, which is the "10% more
            #   trips" row's over 0.1 x peak, so a tenth of the line's yearly revenue hours ten times over at its mode's
            #   NTD rate (lever_car_miles.py hours_year)
            "runToday": next((int(round(peaks[line][0] * m_["run"])) for m_ in menu if m_["id"] == "more"), None),
            "peak": {"buses": peaks[line][0], "at": peaks[line][1]} if line in peaks else None,
            # the basic timetable under the data date (Bryan, 2026-11-15: "Should show basic
            #   schedule here"); docstring, "Timetable"
            "schedule": schedule(dep[0], line, dep[1]),
            "grid": grid,
            "map": {k: v for k, v in mapd.items() if k not in ("bulbCand", "ovrFt", "laneDir", "newPairs", "newMiles")} if mapd else None,
            "history": {"lanes": lane_history(near_lanes), "projects": sorted(projects.get(line, []), key=lambda x: (x["date"], x["text"])),
                        "trend": hist, "steps": steps.get(line, [])},
        }
    # the timetable count against SFMTA's own published change (docstring, "History"): the 44's weekday bus every 12
    #   minutes to every 10 from 10 June 2023 (SERVICE_CHECK)
    for line, m, want in SERVICE_CHECK:
        if line in out_lines:
            v = out_lines[line]["history"]["trend"]["day"][all_months.index(m)] if m in all_months else None
            if v is None or abs(v - want) > 0.75:
                errors.append(f"service: the {line}'s weekday gap in {m} is {v} min, SFMTA published {want}")
    # the newest month from 511's schedule against SFMTA's own current timetable, the same rules on two feeds: buses
    #   in service within a bus, and the weekday gap to the whole minute as the line under the picker gives it, each on
    #   nine lines in ten
    newest = trend_months[-1]
    for what, pairs in (
            ("buses in service", [(x["history"]["trend"]["buses"][-1], peaks[l_][0]) for l_, x in out_lines.items()
                                  if l_ in peaks and x["history"]["trend"]["buses"][-1] is not None]),
            ("weekday gap", [(int(math.floor(x["history"]["trend"]["day"][-1] + 0.5)), x["schedule"]["weekday"])
                             for x in out_lines.values() if x["schedule"] and x["schedule"].get("weekday") is not None
                             and x["history"]["trend"]["day"][-1] is not None])):
        ok = sum(abs(a - b) <= (1 if what == "buses in service" else 0) for a, b in pairs)
        if len(pairs) < 30 or ok < 0.9 * len(pairs):
            errors.append(f"{what}: {newest} from 511 matches SFMTA's timetable on {ok} of {len(pairs)} lines")
    for line, x in out_lines.items():
        T = x["history"]["trend"]
        if any(len(T[g]) != len(all_months) for g in ("day", "eve", "wknd", "buses", "riders")):
            errors.append(f"line {line}: a history series is not one value a month")
        if x["kind"] == "bus" and not (x["schedule"] or {}).get("rushOnly") and sum(v is not None for v in T["day"]) < len(all_months) // 2:
            errors.append(f"line {line}: a weekday timetable gap in under half the months")
    if sum(1 for x in out_lines.values() if any(v is not None for v in x["history"]["trend"]["riders"])) < 40:
        errors.append("riders: under 40 lines have SFMTA's weekday boardings")
    if crowd_months and months:
        behind = (int(months[-1][:4]) - int(crowd_months[-1][:4])) * 12 + int(months[-1][5:]) - int(crowd_months[-1][5:])
        if behind > STALE_MONTHS:
            print(f"optimizer_build: WARN SFMTA's newest crowding month {crowd_months[-1]} is {behind} months behind the "
                  f"waits ({months[-1]}), over {STALE_MONTHS}")
    # data updated: the date each source on the page was read, the older of the two. The 511 stop records are read a
    #   month at a time once the month closes, so their date is the last day of the waits' newest month; SFMTA's
    #   crowding file carries the date sfmta_crowding.py last read new content (sfmta_crowding_read.json).
    sf_read = load_json(os.path.join(E, "optimizer", "sfmta_crowding_read.json"))["read"]
    if len(crowd_months) < CROWD_MONTHS:
        errors.append(f"crowding: SFMTA's file has {len(crowd_months)} months, under {CROWD_MONTHS}")
    n_crowd = sum(1 for x in out_lines.values() if x["today"]["crowd"] is not None)
    if n_crowd < MIN_CROWD_LINES:
        errors.append(f"crowding: {n_crowd} lines have SFMTA's figure, under {MIN_CROWD_LINES}")
    # today's targets pick no fixes at no cost on every line, as the page opens
    for line, x in out_lines.items():
        mx = line_mixes(x)
        k, met = choose_targets(mx, mx[0][4])
        if not met or mx[k][0] != 0:
            errors.append(f"line {line}: today's targets pick combination {k} at {mx[k][0]}, not no fixes at $0")
    return errors, {"month": months[-1], "years": YEARS,
                    "cases": list(CASES), "months": months, "trendMonths": trend_months, "allMonths": all_months,
                    "crowdMonths": [crowd_months[0], crowd_months[-1]] if crowd_months else None,
                    "sourcesRead": {"waits": waits_read, "crowding": sf_read},
                    "studies": studies(base_csv, errors), "rates": {k: r(v, 2) for k, v in RATE.items()},
                    "delivered": {k: r(dlv_w[k], 4) for k in ("trolley", "motor") if k in dlv_w}, "fillTarget": target_dlv,
                    "dataUpdated": min(waits_read, sf_read), "ontimeCheck": ot_check, "lines": out_lines}


def studies(base_csv, errors):
    """The 29 Sunset's measured stop-removal effect as the lever model writes it (roi_baselines.csv, lever round 5):
    seconds of ride time saved for each stop removed, low, middle and high, all day and at rush, for About. A key the
    lever model no longer writes is a check failure, so About never drops the row quietly."""
    out = {}
    for p, key in (("all day", "allDay"), ("peak", "rush")):
        for lvl in CASES:
            name = f"{lvl}, stop, {p}, seconds a removed stop"
            if name not in base_csv:
                errors.append(f"studies: roi_baselines.csv has no {name!r}; About's stop-removal row reads it")
                continue
            out.setdefault(key, {})[lvl] = r(base_csv[name], 2)
    k = "applied, paint, high, all day, percent of time"
    if k not in base_csv:
        errors.append(f"studies: roi_baselines.csv has no {k!r}; About's lane row reads it")
    return {"stops": out, "laneHigh": r(base_csv.get(k, 0.0), 1)}


def month_file(out_dir=OUT_DIR):
    """The newest month's results file."""
    return os.path.join(out_dir, sorted(f for f in os.listdir(out_dir) if f.endswith(".json"))[-1])


def write_month(out_dir, out):
    """Write this month's results file; an earlier month's file is never rewritten. Returns (path, changed)."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{out['month']}.json")
    later = sorted(f[:-5] for f in os.listdir(out_dir) if f.endswith(".json") and f[:-5] > out["month"])
    if later:
        raise SystemExit(f"optimizer_build: {out_dir} already has a later month ({later[-1]}) than {out['month']}")
    return path, stable.write_json(path, out, sort_keys=True, separators=(",", ":"))


WAIT_TIMETABLE_LINES = 30  # lines with a weekday gap the newest month's timetable needs (build()'s check wants 30 pairs)


def waiting_on():
    """Why the newest month can't be built yet, as a list, empty when it can: the dashboard has moved to a month whose
    slower inputs haven't arrived. 511's timetable for the month (timetable_month.py --update, the
    muni-timetable-history step) and SFMTA's delivered share by mode for it (fetch_delivered_by_mode.py --update) each
    come a few days after the stop records the dashboard is built on. Until both are in, the last month's file stays
    as it is and the run passes; pipeline/refresh-freshness.py alarms when that file's month ended over 40 days back."""
    months = load_json(os.path.join(SITE, "muni.json"))["windows"]["90"]["monthList"]
    m, why = months[-1], []
    n = sum(1 for row in read_csv(TIMETABLE_MONTHS) if row["month"] == m and row["day"] not in ("", None))
    if n < WAIT_TIMETABLE_LINES:
        why.append(f"511's timetable for {m} ({n} lines in {os.path.relpath(TIMETABLE_MONTHS, ROOT)}; muni-timetable-history adds it on the VM)")
    days = {row["mode"]: int(row["days"]) for row in read_csv(os.path.join(LEV, "delivered_by_mode.csv")) if row["month"] == m}
    import calendar
    if min(days.get("motor", 0), days.get("trolley", 0)) < calendar.monthrange(int(m[:4]), int(m[5:7]))[1]:  # every day of it
        why.append(f"SFMTA's delivered share by mode for {m} (motor {days.get('motor', 0)} days, trolley {days.get('trolley', 0)}; muni-delivered-by-mode fetches it)")
    return m, why


def main():
    month, why = waiting_on()
    held = sorted(f[:-5] for f in os.listdir(OUT_DIR) if f.endswith(".json")) if os.path.isdir(OUT_DIR) else []
    if why and held and held[-1] < month:
        for w in why:
            print(f"optimizer_build: WAITING for {w}")
        print(f"optimizer_build: kept {os.path.relpath(os.path.join(OUT_DIR, held[-1] + '.json'), ROOT)} until {month}'s inputs are in")
        return 0
    errors, out = build()
    if errors:
        for e in errors:
            print(f"optimizer_build: FAIL {e}")
        print("optimizer_build: kept the previous results")
        return 1
    path, changed = write_month(OUT_DIR, out)
    print(f"optimizer_build: {len(out['lines'])} lines, data updated {out['dataUpdated']}; "
          f"{'wrote' if changed else 'unchanged'} {os.path.relpath(path, ROOT)} ({os.path.getsize(path) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
