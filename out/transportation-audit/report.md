# Transportation data audit

Run 2026-10-01 by [`pipeline/transportation-audit.py`](../../pipeline/transportation-audit.py) against [pipeline/transportation-data-audit-criteria.md](../../pipeline/transportation-data-audit-criteria.md). Generated: edit the script or the data, never this file. The first run, by hand, is [research/transportation-audit-2026-09/data-quality.md](../../research/transportation-audit-2026-09/data-quality.md).

**The criteria doc's pass lines have changed since this script's were copied from them** (hash a9af3b5ce02f2a96, script has f6650990c2494d05). Check each pass line below against the doc, then update CRITERIA_PASS_HASH.

Result: 14 PASS, 11 FAIL.

| Check | Status | Measured | Denominator | Pass line |
| --- | --- | --- | --- | --- |
| [A1-SFMTA](#a1-sfmta-completeness-sfmta) Completeness: SFMTA | **FAIL** | 0 missing (0 of 60 on plan blocks, 0 of 70 bike or pedestrian); 1 of 87 listed SFMTA rows not current by the audit's own reading | 75 SFMTA street projects not marked finished: 63 on the layer (58 bike or pedestrian, 60 on plan blocks, 55 both) and 12 active bike or pedestrian pages the layer does not carry; 87 SFMTA rows on the list | Zero missing. Every active SFMTA project on the plan's blocks is listed, and so is every SFMTA project that touches bike or pedestrian infrastructure, whether or not SFMTA tags it Bike and whether or not its block is on the plan. |
| [A1-PW](#a1-pw-completeness-public-works) Completeness: Public Works | **FAIL** | 3 | 12 in-progress Public Works projects on plan blocks | No more than 5% of active on-plan projects missing, and every miss explained. |
| [A1-SFPUC](#a1-sfpuc-completeness-sfpuc) Completeness: SFPUC | **FAIL** | 2 | 13 in-progress SFPUC projects on plan blocks | No more than 5% of active on-plan projects missing, and every miss explained. |
| [A2](#a2-other-agencies) Other agencies | **FAIL** | 9 | 9 active other-agency jobs on plan blocks (56 other-agency jobs in the feed) | Each active other-agency job on plan blocks is either listed or named on About the data as out of scope. |
| [A3](#a3-duplicates) Duplicates | **PASS** | 0 | 252 listed rows: 0 extra same-name rows, 0 of 8 high-overlap pairs not shown as related, 0 of 0 cross-source pairs not merged or related | Zero same-name rows. Every high-overlap pair is either merged or shown on the page as related. (The measure's pairs are Jaccard ≥ 0.5 on blocks, and two sources' rows for the same project that were not merged.) |
| [B1](#b1-link-to-the-departments-own-page) Link to the department's own page | **PASS** | 153 | 162 jobs a department publishes pages for, of 252 listed; 7 of the rest show no closest official source | Over 90% of the listed projects a department publishes pages for, overall and within each department. That is every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. Every other job shows the closest official source, and About the data says why. |
| [B2](#b2-key-fields-present) Key fields present | **FAIL** | start 92.1%, phase 98.0%; 0 missing values not shown as not published | 252 | Start and phase on 95% of rows. Every missing value shows as “not published” on the page, never as a blank. |
| [B3](#b3-status-agrees-across-sources) Status agrees across sources | **PASS** | 0 of 24 SFMTA/Public Works pairs disagree unshown; 0 of 21 merged rows disagree unshown (10 disagree) | 24 projects both SFMTA's layer and Public Works' pages publish, and 21 merged SFMTA/feed rows | Every disagreement is printed with both values. |
| [C1](#c1-source-coverage) Source coverage | **PASS** | 7 | 7 deciding bodies | Each deciding body read from 2019 or earlier to within a month of today, with less than 5% of meetings missing, and full item titles kept. Each body has its own fetch script that mirrors meetings to disk, re-fetches drafts, and can be rerun without re-downloading what it holds. |
| [C2](#c2-mentions-per-major-project) Mentions per major project | **FAIL** | 12 | 107 major projects (outlined, or at least 1 mi of plan network, counted per direction of travel; About the data states no basis, measured from the bikeway layer and the plan's map) | Every major project with fewer than three distinct dated records from city bodies has its reason printed; the share with three or more is reported. |
| [C3a](#c3a-labels-project-page-items-under-city-decisions) Labels: project-page items under City decisions | **PASS** | 0 | 251 items under City decisions | No mislabelled kinds: nothing from a project's own page shows under “City decisions naming this project”. |
| [C3b](#c3b-records-naming-a-projects-contract-number-or-full-name) Records naming a project's contract number or full name | **PASS** | 0 | 252 listed projects, searched in their attached records and 42540 mirror items | Every item naming the project's name or contract number is counted as the project's own. |
| [C3c](#c3c-matching-accuracy-hand-checked-sample) Matching accuracy: hand-checked sample | **PASS** | 53 | 53 graded links the list still counts, of 60 graded (7 no longer counted: 0 graded wrong, 7 graded right) | Every link in a seeded random sample of at least 40 is about its project and carries the right kind label. |
| [C4](#c4-a-record-before-work-starts) A record before work starts | **FAIL** | 79 | 232 | Over 90% of listed projects with a start date have a city-body record dated before that start, or the shortfall is logged as a top issue on About the data (Bryan, 2026-09-29: "Let's just log this as a problem and add to the list of issues. That we have most projects in the shared feed that don't have a project page."). |
| [D1](#d1-missing-impossible-inconsistent-dates) Missing, impossible, inconsistent dates | **FAIL** | 4 | 252 listed rows: 0 end before start, 17 past end still listed (17 the department still lists active, 4 of them without the passed end shown; 0 it does not list active), 0 of 53 phase-date conflicts not shown | Zero end-before-start. Zero past-end rows on a “current” list, apart from work the department still lists as active, on its page, its project layer or the coordination feed, which stays listed with its passed end date shown. Every phase-date conflict shown on the page. |
| [D2](#d2-dates-are-right-hand-graded) Dates are right (hand-graded) | **FAIL** | construction end 91.3%, construction start 95.7%, consultation end 94.6%, consultation start 97.3%, other dates 100.0% | 313 graded of 313 dates on 75 listed projects | Over 95% correct on each of construction start, construction end, public consultation start and end, and over 95% on all other dates shown, over a random sample of at least 60 listed projects. The share is of dates a department page states; rows marked 'no page' or 'not on page' are left out. |
| [E1](#e1-valid-shapes) Valid shapes | **PASS** | 0 | 23980 features in 5 drawn files | Zero empty, zero-length, self-intersecting or out-of-city shapes in files the site draws. |
| [E2](#e2-lines-up-with-the-street-grid) Lines up with the street grid | **PASS** | 0 over 15 m (50 ft); 186 drawn features carry no CNN | 7182 keyed features in 3 drawn files (7368 drawn; the 186 with no CNN cannot be tested and are not in the denominator) | Zero segments more than 15 m (50 ft) from their CNN's centerline in files the site draws. |
| [E3](#e3-the-map-shows-the-whole-project) The map shows the whole project | **PASS** | 14047 of 14047 blocks drawn (100.0%); 0 maps under half, 0 short of any block | 252 project maps | Every block held is drawn, on every project. |
| [F1](#f1-units) Units | **FAIL** | 0 metric units; 1 mile basis (per direction); 0 of 656 mi figures on pages whose file disagrees with the layer and the map; 0 blocks or projects off | 1066 rendered pages | Zero metric units shown. One mile basis across every page and chart, and the About page says which. |
| [F2](#f2-denominators) Denominators | **PASS** | 2 | resident totals used as a denominator, found on 1066 rendered pages | One resident total, or each one labelled with its source where it is used. |
| [F3](#f3-freshness) Freshness | **PASS** | 0 | 35 source dates and 0 typed “as of” phrases | Every source within its horizon (90 days for a live dataset, 180 for a document), and no hard-coded “as of” text that disagrees with the data. |
| [F4](#f4-traceability) Traceability | **FAIL** | 3 typed figures the data could supply or unclassified; 2 of 17 traces fail; 2 of 3 headline figures untraced | 4 typed figures in 4 content files; 3 headline figures on the section pages | Every headline figure reaches a source row. Zero typed figures that the data could supply. |
| [F5](#f5-clean-text) Clean text | **PASS** | 0 | names and titles in site/data and on the rendered pages | Zero `?` in place of dashes, `â€`, `Ã` or U+FFFD in shown names and titles. |
| [S1](#s1-stable-project-addresses) Stable project addresses | **PASS** | 0 | 526 addresses published at HEAD, 526 in the registry (252 listed, 204 redirect, 70 notice) | Every project address published at HEAD still answers: it is in data/project-ids.json, points at the same project or names the old id in formerIds, and the site builds a page or a redirect for it. |

## Against the first run

Each difference from the hand-run numbers in the first audit, and why.

| Check | First run | This run | Why they differ |
| --- | --- | --- | --- |
| A1-SFMTA | fail: 25 active non-Bike projects on plan blocks missing, 23 Bike-tagged no-phase dropped (21 on plan), 196 sitemap pages not on the layer | FAIL: 0 missing (0 of 60 on plan blocks, 0 of 70 bike or pedestrian); 1 of 87 listed SFMTA rows not current by the audit's own reading | The first run counted non-Bike projects on plan blocks and sitemap pages of any kind. This run counts both populations the criteria set: every active layer project on plan blocks (60, 0 missing) and every bike or pedestrian project, on the plan or not (58 on the layer and 12 active sitemap pages, 0 missing). A project counts as finished when the layer says so or its own page does (read from the pages extract, whatever phase the layer gives), and a project with no bike or pedestrian scope counts only while its page shows work in the last year or to come. What each filter removed is listed under the check. |
| A1-PW | gap: 104 in-progress pages, 38 with blocks, 29 on plan, 9 cover plan blocks no listed project covers | FAIL: 3 | The first run counted plan blocks no listed project covers. This run counts in-progress Public Works pages on plan blocks that no listed row names, whatever the page's name (12 pages, 3 of them not named for street work), so a page whose blocks another project happens to cover still counts. A page's blocks are read from its Location field as the corridor between the limits it names (scripts/lib/pw_extent.py), not every block of every street it names. Pages with no block data or off the plan are listed under the check. |
| A1-SFPUC | not measured: no SFPUC project list read | FAIL: 2 | Same measure, same data. |
| A2 | gap: 9 active other-agency jobs on plan blocks, none named on About | FAIL: 9 | Same measure. The feed is read from the cached pull, and the check says whether it is the pull coordination.json was built from. |
| A3 | gap: 1 name twice; 9 pairs ≥ 50% block overlap; 3 cross-source pairs not merged | PASS: 0 | Overlap pairs are measured on every block a row holds, not only plan blocks; pairs shown as related do not count, and cross-source pairs arrive merged into one row. |
| B1 | fail: Public Works 0 of 129, SFPUC 0 of 24, SFMTA 29 of 41; 7 of the other 12 SFMTA have a page | PASS: 153 | The list now takes every SFMTA bike or pedestrian project, and rows link the page their department publishes where one matches (scripts/department-project-pages.py). The table under the check gives each department's share. |
| B2 | gap: start missing 7 of 194, end 21; scope on feed rows only; 2 with no geometry | FAIL: start 92.1%, phase 98.0%; 0 missing values not shown as not published | This run also checks whether each missing start, end or scope says "not published" on the page, which is what the pass line asks. |
| B3 | gap: 6 of 17 same-name SFMTA/Public Works projects disagree; neither page shows the other | PASS: 0 of 24 SFMTA/Public Works pairs disagree unshown; 0 of 21 merged rows disagree unshown (10 disagree) | The name rule finds 24 SFMTA/Public Works pairs, and 'shown' requires the listed page to link Public Works' page and print its status. Merged SFMTA/feed rows are a second population (0 of 21 disagree), counted apart. |
| C1 | fail: hearings from 2019-08 with 23 of 144 unread; Board bike items only; BoS 24 terms, titles; SFPUC from 2021; PW Commission, SFCTA not read | PASS: 7 | Each body is now read from its own meeting mirror (out/record-coverage/coverage.json), and a fetch script counts only when it writes through lib/mirror.py, which re-fetches drafts and skips settled meetings. |
| C2 | fail: 2 of 43 major projects have 3 or more dated city-body records | FAIL: 12 | The list has 107 major projects, and records come from every item of the deciding bodies' mirrors, matched by name, where the first run read only bike-keyword items. The independent name search covers the same mirrors, listed under the check. |
| C3a | fail: 156 of 213 items under City decisions come from the project's own page; 25 events labelled SFMTA Board | PASS: 0 | Project-page items now show in their own fold on each project page, apart from City decisions, and carry their page's label (timeline, notice, event) rather than a city body's. |
| C3b | fail: contract awards naming the job's contract number are missed (3 found) | PASS: 0 | The first run spot-checked three contract awards. This run searches every attached record and every item of the deciding bodies' meeting mirrors (42540 items) for the job's contract number or full name. |
| C3c | not run: no hand-check of a link sample | PASS: 53 | Not graded yet. The sample (data/audit/grades/c3-links.csv) draws only records a city body published. |
| C4 | not in the first run (criterion added 2026-09-28) | FAIL: 79 | New criterion (2026-09-28); no first-run number. |
| D1 | fail: 0 end-before-start; 2 past-end rows current; 44 Planning/Design with start passed; 8 start after 2032; 1 future city-body record | FAIL: 4 | Every past-end row on the list counts, split by what its own department publishes today: still active (counted until Bryan decides whether such rows belong on a current list) or not. Starts after 2032 and future-dated records are reported as information, not counted, since the pass line names only the three conflicts. |
| D2 | not in the first run (criterion added 2026-09-28) | FAIL: construction end 91.3%, construction start 95.7%, consultation end 94.6%, consultation start 97.3%, other dates 100.0% | New criterion (2026-09-28). The sample (data/audit/grades/d2-dates.csv) points each row at the department's page, or says none was found. |
| E1 | pass for drawn files (plan, bikeway, all-ages); project geometry 2 empty; raw layer 6 self-intersecting, 5 zero-length | PASS: 0 | The project geometry is a drawn file, so an empty project shape fails it. A project drawn as intersection points, or a page SFMTA publishes but does not map (which says so), is not an empty shape. The raw layer's faults are reported as information. |
| E2 | fail: 51 of 3,017 bikeway segments > 15 m, 21 > 100 m; 21 retired CNNs (+12 all-ages); 153 split-block CNNs | PASS: 0 over 15 m (50 ft); 186 drawn features carry no CNN | Bikeway rows are now keyed to the centerline block they lie on (scripts/bikeway_snap.py). Drawn features with no CNN (186) are listed and left out of the denominator, not counted as aligned. |
| E3 | fail: 2,257 of 8,414 blocks drawn (27%); 152 of 194 maps draw under half | PASS: 14047 of 14047 blocks drawn (100.0%); 0 maps under half, 0 short of any block | Each project map now draws every block and intersection it holds, from the plan's trace, the bikeway layer or the centerline; retired CNNs go to the blocks that replaced them. |
| F1 | gap: 0 metric units; 'mi' is centerline on Current Projects, per direction on Better Coordination (47.5 vs 78.3 for 91 jobs) | FAIL: 0 metric units; 1 mile basis (per direction); 0 of 656 mi figures on pages whose file disagrees with the layer and the map; 0 blocks or projects off | Every mi figure on the rendered pages (656) takes the verdict of its data file, and every file is measured against the bikeway layer and, for plan blocks, against the North Star map PDF read and measured here: which blocks the map draws and how much of each. The pipeline's trace is not read, so its share cannot pass by construction. Plan network: status.json 457.1 mi, the map 457.2 mi; 0 blocks disagree on how much, 0 plan blocks the map does not draw, 0 drawn blocks the plan network lacks. |
| F2 | gap: 830,235 (ACS) on the overview, 873,965 (2020 census) in reach; not labelled | PASS: 2 | Same measure, same data. |
| F3 | pass, 1 gap: all inside horizon; typed 'updated only through December 2025' disagrees with layer edit 2026-05-21 | PASS: 0 | The overview's layer date is now filled from the layer's own latest install month, so no typed date is left. |
| F4 | gap: 3 of 3 traced figures reach a row; 3 figures typed into prose | FAIL: 3 typed figures the data could supply or unclassified; 2 of 17 traces fail; 2 of 3 headline figures untraced | Each typed figure is classified in data/audit/typed-figures.csv; the About page's feed-job count is filled from the feed. |
| F5 | gap: 0 in site data; 2 in out/sfmta-board/meetings.json; 1 SFMTA name with â€“ | PASS: 0 | The Public Works Commission mirror carries a ? for the dash in contract-award titles, and those titles reach project pages. Debris in out/sfmta-board/meetings.json is upstream and reported as information. |
| S1 | not in the first run (criterion added 2026-09-28) | PASS: 0 | New criterion (2026-09-28). Project addresses are kept in data/project-ids.json, which also holds the 223 name-based addresses published between 2026-09-22 and 09-24. |

## A1-SFMTA. Completeness: SFMTA

**FAIL.** Measured 0 missing (0 of 60 on plan blocks, 0 of 70 bike or pedestrian); 1 of 87 listed SFMTA rows not current by the audit's own reading of 75 SFMTA street projects not marked finished: 63 on the layer (58 bike or pedestrian, 60 on plan blocks, 55 both) and 12 active bike or pedestrian pages the layer does not carry; 87 SFMTA rows on the list.

Pass line: Zero missing. Every active SFMTA project on the plan's blocks is listed, and so is every SFMTA project that touches bike or pedestrian infrastructure, whether or not SFMTA tags it Bike and whether or not its block is on the plan.

SFMTA's sitemap lists 415 /projects/ pages (https://www.sfmta.com/sitemap.xml, 2026-09-29); its project layer carries 224. 1 sitemap pages are not in the pages extract and were not read.
On plan blocks means the project's published line runs on a plan block by scripts/project-blocks.py's test (line within 15 m (50 ft)). Missing: 0 of the 60 active projects on plan blocks and 0 of the 70 bike or pedestrian ones; 0 of the missing publish no phase.

| Project | Phase | Why bike/ped | Population | Plan blocks | Source | Page |
| --- | --- | --- | --- | --- | --- | --- |

What each filter removed before counting:

| Filter | Removed | Names |
| --- | --- | --- |
| layer: phase Completed, Project Evaluation or test | 94 | 11th Street Improvement Project; 12 Folsom-Pacific Rincon Hill Extension; 14 Mission Rapid Project; 16th Street Improvement Project; 17th Street Bicycle Safety Project; 17th Street Quick-Build; 20th Avenue Neighborway Project; 30 Stockton Transit Priority Improvements; 3rd Street Quick-Build Project; 5 Fulton Rapid Project; 66 Quintara Connectivity Study; 7 Haight Noriega Rapid Project; 7th Street and 8th Street Safety Projects; 8th Avenue Neighborway Project; 9 San Bruno Rapid Project; Alemany Bikeway Project; Alemany Boulevard (Ellsworth to Justin Drive/Congdon) Quick-Build Project; Alemany Corridor Safety Project; Alemany Interchange Bike Lanes Project; Battery/Sansome Quick-Build Project; Bay Street Road Diet and Cycletrack; Bayshore Boulevard Quick-Build Project; Bayview CBTP Quick-Build Projects; Brannan Street Safety Project; Broadway Safety Improvement Project; Bryant Street Bike Network Improvement Project; Cable Car Gearbox Rehabilitation Project; California Street Safety Project; Cesar Chavez/Potrero Ave/Bayshore Blvd Intersection Improvements (The Hairball); Columbus Avenue Safety Project; Divide Feeder Circuit Carl 11; Division/13th Street Safety Project; Dogpatch Parking Management; Dr. Carlton B. Goodlett Place Quick-Build Project; Evans Avenue Quick-Build; Excelsior Neighborhood Traffic Calming Project; Folsom Street Quick-Build Project; Franklin Street Quick-Build Project; Frida Kahlo / Ocean / Geneva (F.O.G) Study; Fulton Street Safety and Transit Project; Geary Rapid Project; Geneva Avenue Traffic Signal Upgrades; Golden Gate Avenue Quick-Build; Golden Gate Park Traffic Safety Project; Great Highway Pilot Project; Guerrero Street Quick-Build Project; Hayes Valley Parking and Curb Management Plan; Howard Street Quick-Build Project; Hyde Street Quick-Build; Indiana Street Bikeway Project; Inner Sunset Streetscape Improvement Project; Islais Creek Motor Coach Facility; Jones Street Quick-Build; L Taraval Improvement Project; Lake Merced Pedestrian Safety Project; Lake Merced Quick-Build Project; Larkin Street Quick-Build; Leavenworth Quick-Build; Lincoln Way Quick-Build Project; Lower Great Highway Pedestrian Improvements Project; M Ocean View Improvements (Rossmoor Drive and Junipero Serra); Masonic Avenue Streetscape Project; Mission Bay Loop; Northbound San Jose Avenue and I-280 Off-Ramp Road Diet Pilot Project; Northwest Bernal Heights Residential Permit Parking Area; Outer Sunset Traffic Management Project; Panhandle Social Distancing and Safety Project; Parking Access Revenue Control Systems; Polk Streetscape Project; Potrero Avenue Streetscape Improvement project; Powell Street Safety and Sidewalk Improvement Pilot; Raised Bikeway Demonstration Project; Safer Taylor Street; Sansome and Battery Connections Project; Second Street Improvement Project; Sloat and Skyline Intersection Improvement; South Van Ness Avenue Quick-Build Project; Sunset Tunnel Trackway Improvement Project; Terry Francois Boulevard Quick-Build; The Embarcadero 2020 Quick-Build Projects; Townsend Corridor Improvement Project; Turk Street Safety Project; Twin Peaks Figure 8 Redesign Project; Two-Car Trains on K and T Routes; UCSF Mission Bay Platform Upgrade; Unity Plaza; Upper Clipper Street Traffic Calming Project; Upper Haight Transit Improvement and Pedestrian Realm Project; Valencia Bikeway Improvements; Van Ness Bus Rapid Transit; Vicente Street Bicycle and Pedestrian Safety Project; WalkFirst Rectangular Rapid Flashing Beacons Project; West Portal Station Safety and Community Space Improvements; Wiggle Neighborhood Green Corridor |
| layer: its own page says it is finished (a Completed phase or Project Status field, every milestone marked Completed and dated before this year, or “the project is now / was … complete”), whatever phase the layer gives | 10 | 19 Polk on 7th and 8th Streets Transit Improvements (Formerly Temporary Emergency Transit Lanes); 54 Felton Project; Anza Street Bike Lanes Project; Central Richmond Traffic Safety Project; Forest Hill Irrigation Improvement Project; Frida Kahlo Way Quick-Build Project; Lincoln and Sloat Quick-Build Connections Project; Lombard Street Vision Zero Project; Mission Street SoMa Transit Improvements (Formerly Temporary Emergency Transit Lanes); Upper Market Street Safety Project |
| layer: the construction end its page's text gives is before the plan's adoption on 2025-03-04, and no stage on its timeline is dated after that, whatever phase the page still shows | 28 | 33 Ashbury Overhead Wiring and Pole Replacement Project (2019-05-31); 4th Street Transit Improvement Project (2019-12-31); Active Beale Street (2020-12-31); Balboa Park Station Area and Plaza Improvements (2017-12-31); Bayview Hunters Point Express (2021-02-28); Beach Street Quick-Build Project (2025-02-28); District 11-Wide Traffic Calming Project (2019-07-31); Divisadero Intersection Improvements (2020-09-30); Dolores Street Median Parking (2017-05-31); Eddy Street Two-Way Conversion Project (2019-10-16); Lake Slow Street (2022-11-30); Minnesota Slow Street (2024-11-30); Muni Metro East Bus Yard and 1399 Marin Street Facility (2023-12-31); Muni Metro Escalator Rehabilitation Project (2019-10-09); Octavia Boulevard Enhancement Program (2021-12-31); Paul Avenue Bike Lane Project (2017-01-31); Sanchez Slow Street (2024-11-30); Shotwell Slow Street (2022-11-30); Shotwell/Capp Neighborway Project (2022-11-30); Third Street Bridge Rehabilitation Project (2019-05-31); Twin Peaks Tunnel Automatic Train Control System (ATCS) W1 Crossover Activation (2020-11-30); Twin Peaks Tunnel Improvements (2019-02-28); Twin Peaks Tunnel Upgrades (2024-08-31); Vermont Street Road Diet (2018-05-31); Vision Zero Signal Retiming (2024-11-30); Visitacion Valley and Portola Community Based Transportation Plan (2023-05-31); West Portal Transit Delay Reduction Pilot (2019-08-31); Western Addition Community Based Transportation Plan Implementation (2023-12-31) |
| layer: no phase on the layer or its page, every milestone on its page's timeline is dated before last year, and nothing on the page dates work since | 1 | 55 Dogpatch |
| layer: no phase on the layer, its page's phase field or its Project Status field, and the construction end its page's text gives has passed, with no schedule row on the page after today | 3 | 4th Street Pedestrian Safety Project; Chinatown Parking and Transit Improvements; Marin Facility Site Improvements |
| layer: not street work by name (studies, plans, fleets, stations, tunnels, programmes) | 17 | Bayview Community Based Transportation Plan; Buena Vista West Neighborhood Parking Plan; Candlestick Point/Hunters Point Shipyard; Castro Station Accessibility Improvements Project; Central Subway Extension; Dogpatch-Central Waterfront Area Transit Connections Study; Geneva-San Jose Intersection Study; Mobility Hub Plan - Southeastern San Francisco; Muni Elevators Modernization; Muni Subway Expansion Project; Noe Slow Street and Duboce Triangle Planning Study; Operator Convenience Facility Project; Parkmerced Project; Potrero Yard Modernization Project; Salesforce Transit Center; Treasure Island and Yerba Buena Island Project; Underground Fuel Tank Replacement at Muni Kirkland Yard |
| layer: active, but neither bike or pedestrian nor on a plan block | 3 | 1200 15th Street Renovation Project; Muni Forward 5 Fulton Rapid Proposal; Muni Metro Station Enhancements |
| layer: on plan blocks only (no bike or pedestrian scope), and its page shows no sign of work in the last year or still to come | 5 | 19 Polk Bus Stop Changes; Muni Forward 9 San Bruno Rapid Proposal; Muni Gets You to Downtown; Northeast Mission Parking and Curb Management Project; Parking Management for Northern Potrero Hill |
| sitemap page off the layer: no bike or pedestrian words in its text | 104 | 1 California; 14 Mission Customer Experience Pilot; 2022 Muni Service Network; 22nd Street Caltrain Area Parking Management; 24 Divisadero Temporary Emergency Transit Lanes; 30 Stockton Presidio Extension; 48 Quintara-24th Street Safety; 4th Street Bridge Transit Lanes (Formerly Temporary Emergency Transit Lanes); ADA35: Americans with Disabilities Act 35th Anniversary; Accessibility Strategy; All Electric Fleet Transition; Autonomous Vehicles (AVs) in San Francisco; BART/Muni Market Street Canopy Living Roofs; Bayview Transportation Resource Center; Building Progress Program; Cable Car Sheaves Upgrade Project; Central Subway Project; Citywide Parking Meter Replacement; Community History Preservation Project; Curbside Electric Vehicle Charging Permit Program; Eastern Neighborhoods Transportation Implementation Planning Study (EN TRIPS); Embarcadero Connectivity Plan; Eureka Curve Tunnel Work; Excelsior - Mission Terrace/Cayuga Parking Management; Facilities State of Good Repair; J Church Improvement Project; J Church Surface-only Route; King Substation Improvement Project; Kirkland Yard Electrification Project; Meeting the Transportation Needs of a Growing City - SFMTA Budget for Fiscal Years 2021-2022; Mission at Highland Bus Stop & Infrastructure Improvements; Modernizing San Francisco's Parking Meter Hours; Muni Art; Muni Art 2022 - Krithika Sengottaiyan Artist Page; Muni Art 2022 - Richard Louis Perri Artist Page; Muni Art 2022 - Sebastian Raphael Artist Page; Muni Art 2022 - Steffan Sanguinetti Artist Page; Muni Art 2022 - Streets of San Francisco; Muni Art 2022 - Tan Sirinumas Artist Page; Muni Art 2022 Poem - At the Golden Gate; Muni Art 2022 Poem - Populist Manifesto; Muni Art 2022 Poem - Recipe for Happiness in Khabarovsk or Anyplace; Muni Art 2022 Poem - The Changing Light; Muni Art 2022 Poem - The Changing Light (low-vision-accessible version); Muni Art 2022 Poem - from What is Poetry?; Muni Art 2023 - Alice W. Artist Page; Muni Art 2023 - Annie A. Artist Page; Muni Art 2023 - Isabel l. Artist Page; Muni Art 2023 - Natalie D. Artist Page; Muni Art 2023 - Sights of San Francisco; Muni Art 2023 - Vilma R. Artist Page; Muni Art 2023 Poem - I Like Chinatown by Jake Dominguez; Muni Art 2023 Poem - The Botanical Gardens by Maya Van Artsdalen; Muni Art 2023 Poem - The Rhythm of Baker Beach by Vanessa Rodriguez; Muni Art 2023 Poem - The Wondrous San Francisco Zoo by Jennifer Lopez; Muni Art 2023 Poem - What You Get at Bernal Heights by Abner Valencia; Muni Forward Rapid Network; Muni Funding Working Group; Muni Local Measure; Muni Metro Capacity Study; Muni Metro East Storage Site Improvements; Muni Metro Modernization; Muni Metro Rail Grinding Services - Phase 1; Muni Service Equity Strategy; Muni Stop Lighting Project; MuniSafe: Enhancing Security for Customers and Staff on Muni; N Judah Layover Pilot; Next Generation Customer Information System; On-Street Shared Vehicle Parking Permit Program; Our Community, Our Shuttle; Park Presidio Lombard Temporary HOV Lanes; Paying Your Fares Keeps Us Moving; Planning and Engineering Internship Program; Play Streets; Presidio Facility Bus Lifts Improvement Project; Private Transit Vehicle Permitting; Rail Work; Residential Parking Permit; SF Planning and CEQA; SFMTA Budget Planning - FY 2026-27 and FY 2027-28; SFMTA Budget Planning - Fiscal Years 2025 & 2026; SFMTA Joint Development Program; SFMTA Parking Facilities Elevator Upgrades; SFMTA Parking Facilities Lighting Upgrades; SFpark Pilot Program; Safety Equity Initiative; San Jose Substation Upgrade Phase I Project; Shared Electric Moped Parking Permit Program; Speed Safety Cameras; T Third Improvements; Temporary Emergency Transit Lanes; The National Transit Adaptation Strategy; Train Control Upgrade Project; Transit Delay Hot Spots Program; Transit Effectiveness Project (TEP); Transportation 2030; Transportation 2045; Twin Peaks Tunnel Inspection Project; Waterfront Transportation Assessment; West Portal LK Transfer Project; Why Replace the Potrero Yard?; Woods Battery Electric Bus Charging Station Pilot Program; Woods Division Bus Wash Replacement Project; summer-2025-muni-service-cuts |
| sitemap page off the layer: not street work by name | 27 | 20-Year Unconstrained Capital Plan; A Bigger and Better Light Rail Vehicle Fleet; Battery-Electric Bus Program; Biking and Rolling Plan; Budget for Fiscal Years 2019 and 2020: Balancing Transportation Needs of a Growing City; Climate Roadmap for a Healthier San Francisco; Commuter Shuttle Program; Curbside EV Charging Feasibility Study; District 2 Safety Study; Improving transportation connections between Candlestick Point, Executive Park, and Caltrain; Mid-Market Street Loading Evaluation; New and Improved Zero-Emission Electric Trolley Coach Fleet; Powered Scooter Share Permit Program; Preserving the Iconic Historic Streetcar Fleet; Presidio Yard Modernization Project; Proactively Maintaining our Legacy Light Rail Vehicles; Project Reports; Project Updates; SFMTA Bancroft Facility Improvement Project; SFMTA Budget Planning - Fiscal Years 2023 & 2024; School Walk Audit Program; Shared Rides Pilot; Shared Spaces; Slow Streets Mural Pilot Program; Transportation 2050; Transportation Recovery Plan |
| sitemap page off the layer: the construction end its page's text gives is before the plan's adoption on 2025-03-04, and no stage on its timeline is dated after that | 14 | 24 Divisadero Safety and Transit Project (2022-04-30); 27 Bryant Transit Reliability Project (2023-05-31); 38 Geary (2021-02-28); 43 Masonic and 44 O'Shaughnessy Transit Improvements (2021-08-31); Connected Corridor (2021-03-31); Inner Sunset Curb Management Project (2021-06-30); JFK Drive Protected Bikeway (2012-05-31); Slow Streets in Outer Mission (2021-05-31); Slow Streets in SoMa (2021-05-31); Slow Streets in the Inner Sunset (2021-05-31); Slow Streets in the Western Addition (2021-05-31); Southeast Muni Expansion (2020-11-30); Tenderloin COVID-19 Emergency Streets (2021-04-30); Third Street Bridge Bikeway Connection (2020-07-31) |
| sitemap page off the layer: no phase or Project Status field on its page, and the construction end its page's text gives has passed, with no schedule row on the page after today | 2 | Kirkham Street Neckdown Project; Speed Safety Cameras Background |
| sitemap page off the layer: no sign of work in the last year or still to come | 36 | 20th Street Slow Street; 28 19th Ave Rapid Project; Asia-Pacific Economic Cooperation (APEC) Transit and Travel Information; COVID-19 Developments & Response; Community Engagement Opportunities; Curb Management; Electric Mobility in San Francisco; Flag Stop Conversion Program; Gilman Avenue Streetscape Project; Golden Gate Avenue Safety Project; High Density Housing--Impact on Neighborhood Parking; Lake Merced Bikeway Feasibility Project; Land Use Development & Transportation Integration; Mid-Irving Parking and Curb Management; Mission Traction Power Improvement Project; Mobility Permit Harmonization; Muni Forward; Muni Forward Transit Priority Projects; Muni Forward: Enhancing Safety and Access; Northern Embarcadero Quick-Build Project; Point Lobos Quick-Build Project; Prop A: Muni Reliability and Street Safety Bond; Proposed Transit Improvements on Geary at Park Presidio; Safety Zone Program; Slow Streets; Slow Streets Program; Slow Streets in Oceanview/Parkside; Slow Streets in Vis Valley; Slow Streets in the Bayview; Smart City Challenge 2016; Telegraph Hill Blvd and Coit Tower Parking Lot Reconstruction; Tenderloin Speed Limits and No Turn on Red; Tenderloin Traffic Safety Improvements Project; Transportation Demand Management; Twin Peaks For All; What's in Proposition L? |


Every SFMTA row on the list, read by the same filters and nothing the pipeline decided (its layer phase, its own page, and the coordination feed's dates for a feed job it carries): 87 read, 1 that the filters would not call current work.

| Listed SFMTA row | Phase | The audit's reading | Page |
| --- | --- | --- | --- |
| Visitacion Valley and Portola Community Based Transportation Plan | Planning | layer: the construction end its page's text gives is before the plan's adoption on 2025-03-04, and no stage on its timeline is dated after that, whatever phase the page still shows (2023-05-31) | https://www.sfmta.com/node/24619 |


## A1-PW. Completeness: Public Works

**FAIL.** Measured 3 of 12 in-progress Public Works projects on plan blocks.

Pass line: No more than 5% of active on-plan projects missing, and every miss explained.

Public Works publishes 269 projects (sfpublicworks.org/projects, data/extract/dpw-projects/projects.json); 75 are in progress, 27 of those carry block data and 12 touch plan blocks. Every one of the 12 counts, whatever its name, unless it is out of scope as below; 3 of them are not named for street work (coordination-projects.py's work kinds, or a street, interchange, sidewalk or bridge in the name).
A project counts as missing when no listed project has the same or nearly the same name or links its page. The blocks column says how many of its plan blocks no listed project covers. Missing: 3 (25.0% of the 12 not out of scope); unexplained: 0. Out of scope: 0, each not named for street work, named on About the data as not street work, and explained below from its own page.

| Project | Plan blocks | Not covered by a listed project | Named for street work | Explanation | Page |
| --- | --- | --- | --- | --- | --- |
| Telegraph Hill Rock Slope Improvements | 4 | 4 | no | Rock-slope work on the cliff below Coit Tower, per its Public Works page; not street work. Read 2026-09-28. | https://sfpublicworks.org/index.php/telegraphhill |
| Moscone Expansion Project | 1 | 0 | no | A convention-centre building at 747 Howard Street, per its Public Works page; not street work. Read 2026-09-28. | https://sfpublicworks.org/project/moscone-expansion-project |
| San Francisco Fire Department Division of Training | 1 | 0 | no | A training building at 1200 Carroll Avenue, per its Public Works page; not street work. Read 2026-09-28. | https://sfpublicworks.org/index.php/project/san-francisco-fire-department-division-training |

What was left out before counting:

| Filter | Removed | Names |
| --- | --- | --- |
| not in progress on the department's page | 165 | (every Completed page) |
| in progress and not listed, but its page's text gives a construction end before the plan's adoption on 2025-03-04 | 29 | 9-1-1 Call Center (2024-05-31); Alemany Interchange Improvement Project (2024-08-31); District Police Stations and Infrastructure (2020-02-29); Evans Avenue Sewer Replacement and Pavement Renovation (2019-12-31); Fillmore And Haight Street Intersection, AWSS, Sewer Replacement And Pavement Renovation Project (2021-01-31); Fulton Street and Grove Street Sewer Replacement and Pavement Renovation Project (2023-02-28); Geneva Avenue Traffic Signal Project (2022-10-31); Hall of Justice Replacement Jail Project (2020-12-31); Infill Sidewalks in Bayview Project (2024-11-30); Jefferson Streetscape Improvements Project - Phase II (2021-10-01); Junipero Serra Boulevard Pavement Renovation & Sewer Replacement Project (2023-12-31); Marina Branch Library (2021-12-30); Masonic Avenue Streetscape Improvement Project (2018-05-31); Page Street Neighborway Project (2023-05-31); Richmond Residential Pavement and Sewer Replacement Project (2024-08-31); San Francisco Navigation Centers (2015-03-31); Sunset Boulevard Pavement Renovation (2025-02-28); Transbay Folsom Streetscape Improvement Project (2021-02-28); Upper Haight Transit Improvement and Pedestrian Realm Project (2021-08-31); Various Locations #31 Project (2022-04-30); Various Locations #45 (2023-12-17); Various Locations Pavement Renovation #67A (2025-01-31); Various Locations Pavement Renovation and Sewer Replacement #52 (2023-05-31); Various Locations Pavement Renovation and Sewer Replacement No. 54 (2024-08-31); Various Locations Pavement Renovation and Sewer Replacement No. 59 (2024-07-19); Various Locations Pavement Renovation and Sewer Replacement No. 8 (2022-05-31); Various Locations Pavement Renovation and Sewer Replacement Project No. 53 (2024-07-19); Various Locations Pavement Renovation and Sewer Replacement Project No. 63 (2024-11-30); Various Locations Pavement Renovations and Sewer Replacement No. 48 (2023-05-31) |
| in progress, no block data, so it cannot be placed | 48 | 2016 Public Health and Safety Bond; 3500 Trees Project; 8th St, Clay St, and Leavenworth St. Pavement Renovation and Sewer Replacement Contract #2308i; Ames and Quane Alleyway Improvement Project; Bayview Gateway Project; Bayview Transportation Improvements Project; Brannan Street Pavement Renovation and Sewer Replacement Project; Chestnut Street Renovation; Chinatown Improvement Projects; Contract No. 65 New Traffic Signals; District Police Stations and Support Facilities; Dogpatch and Northwest Potrero Hill Green Benefit District; Earthquake Safety and Emergency Response Bond; Earthquake Safety and Emergency Response Bond 2010; Earthquake Safety and Emergency Response Bond 2014; Earthquake Safety and Emergency Response Bond 2020; Earthquake Safety and Emergency Response Bond Reports; Emergency Firefighting Water System; Gough Street Water, Sewer and Paving Project; Ingleside Police Station Replacement; Justice Facilities Improvement Program; Lawton Street Sewer Renovation and Replacement; Market Octavia Living Alleys; Neighborhood Fire Stations; Neighborhood Fire Stations and Support Facilities; Road Repaving & Street Safety Bond; SoMa Under Freeway Community Space; Sunset Boulevard Master Plan; Traffic Signal Modifications Contract #36; Transbay Transit Streetscape; Various Locations (VL) #62; Various Locations Curb Ramps #17; Various Locations No. 49 Pavement Renovation; Various Locations Pavement Renovation #90 & Sewer Replacement Project; Various Locations Pavement Renovation No. 82 and Sewer Replacement; Various Locations Pavement Renovation No. 85 and Sewer Replacement; Various Locations Pavement Renovation Project #68; Various Locations Pavement Renovation and Sewer Replacement No. 55; Various Locations Pavement Renovation and Sewer Replacement No. 57; Various Locations Pavement Renovation and Sewer Replacement No. 58; Various Locations Pavement Renovation and Sewer Replacement No. 61; Various Locations Pavement Renovation and Sewer Replacement No. 64; Various Locations Pavement Renovation and Sewer Replacement No. 74; Various Locations Pavement Renovation and Sewer Replacement No. 80; Various Locations Sewer Replacement and Pavement Renovation No. 38; Various Locations Sewer Replacement and Pavement Renovation Project No. 36; Various Locations Sewer Replacement and Pavement Renovation Project No. 39; Various Locations Sewer Replacement and Pavement Renovation Project No. 43 |
| in progress, blocks off the plan | 15 | 20th Street and De Haro Street Intersection Reconstruction Project; 24th Street Pavement Renovation and Infrastructure Improvement Project; 9th Avenue & Lincoln Way Improvement Project; Chinatown Branch Library Renovation Project; Chinatown Public Health Center Renovation Project; Disaster Response Facilities; Japantown Buchanan Mall / Osaka Way; Lakeview Stairs Project; McAllister Street, 20th Street, and 24th Street Pavement Renovation and Sewer Replacement Project; Minna Natoma Streetscape Project; Mission Branch Renovation Project; Mission Street Pavement Renovation and Sewer Rehabilitation Project; Portsmouth Square Improvement Project; Transit U Improvement Project; Various Locations Curb Ramps and Sub-Sidewalk Basements |


## A1-SFPUC. Completeness: SFPUC

**FAIL.** Measured 2 of 13 in-progress SFPUC projects on plan blocks.

Pass line: No more than 5% of active on-plan projects missing, and every miss explained.

SFPUC publishes 62 projects (data/extract/sfpuc-projects/projects.json); 51 are in progress, 20 of those carry block data and 13 touch plan blocks. Every one of the 13 counts, whatever its name, unless it is out of scope as below; 2 of them are not named for street work (coordination-projects.py's work kinds, or a street, interchange, sidewalk or bridge in the name).
A project counts as missing when no listed project has the same or nearly the same name or links its page. The blocks column says how many of its plan blocks no listed project covers. Missing: 2 (15.4% of the 13 not out of scope); unexplained: 0. Out of scope: 0, each not named for street work, named on About the data as not street work, and explained below from its own page.

| Project | Plan blocks | Not covered by a listed project | Named for street work | Explanation | Page |
| --- | --- | --- | --- | --- | --- |
| Construction at the Southeast Treatment Plant | 1 | 0 | no | Work inside the Southeast Treatment Plant, which the page calls "the City’s largest wastewater treatment facility", including new staff buildings "near the northwest corner of Phelps Street and Jerrold Avenue"; not street work. Its one plan block is Evans Avenue between Rankin and Quint, a street the page names. Read 2026-09-29. | https://www.sfpuc.gov/construction-contracts/construction-projects/sepconstruction |
| Westside Pump Station Reliability Improvements Project | 1 | 0 | no | Upgrades inside the Westside Pump Station, which the page calls "an all-weather facility that pumps the sanitary and stormwater flow from the West side of the City to the Oceanside Treatment Plant"; not street work. Its plan blocks are Great Highway between Sloat and Skyline, a stretch the page names; the page says "The traffic detour will continue until the end of major construction activities". Read 2026-09-29. | https://www.sfpuc.gov/construction-contracts/construction-projects/westside-pump-station-reliability-improvements |

What was left out before counting:

| Filter | Removed | Names |
| --- | --- | --- |
| not in progress on the department's page | 7 | (every Completed page) |
| in progress and not listed, but its page's text gives a construction end before the plan's adoption on 2025-03-04 | 4 | 17th Street Water Main Replacement (2022-11-30); Bioregional Habitat Restoration (2024-05-31); Casitas Avenue and Lansdale Avenue Pipeline Replacement Project (2022-04-30); Water Conveyance Lower Cherry Aqueduct Rehabilitation (2020-04-30) |
| in progress, no block data, so it cannot be placed | 31 | AP Giannini Stormwater Schoolyard Project; Alameda Creek Watershed Center in Sunol; Biosolids Digesters Facilities; Bridge Replacement; East SOMA Sewer Improvements Project; Edgewood Trail Repair Project; Harding Park Pump Station Upgrades; Laguna Street Outfall Rehabilitation Project; Millbrae Yard Security Upgrades; Moccasin Penstock; Moccasin Powerhouse and Generator Step-Up Transformer Rehabilitation; Mountain Tunnel Improvements; Mountain Tunnel South Fork Siphon Extension Improvements; New SFPUC Water Division Campus; O’Shaughnessy Dam Access and Drainage Improvements; O’Shaughnessy Dam Outlet Works Phase 1; Regional Groundwater Storage & Recovery Phase IIB; Regional Groundwater Storage and Recovery Phase 2B; San Francisco Zoo Recycled Water Project; San Joaquin Pipeline Valve and Safe Entry Improvement; Seacliff 1 & 2 Pump Stations and Force Main Upgrades; Skyline Watershed Ridge Trail Project; Southeast Treatment Plant Maintenance Buildings; Summit Reservoir Sealant Project; Sunol Valley Water Treatment Plant Ozonation Project; Treasure Island Water Resource Recovery Facility; University Mound Reservoir North Basin Roof Coating Project; Upper Yosemite Creek Daylighting Project; Vista Grande Drainage Basin Improvement Project; Warnerville Substation Rehabilitation; Westside Enhanced Water Recycling Project |
| in progress, blocks off the plan | 7 | 21st Street Water Main Replacement Project; Coso and Precita Avenues Utility Upgrade Project; Fulton Street Water and Sewer Improvements Project; Geary Boulevard Sewer and Water Improvements Phase 2; Golden Gate Heights Water and Sewer Main Replacement Project; Irving Street and Lincoln Way Water Improvements Project - East; Water Main and Sewer Replacement on Grand View Avenue |


## A2. Other agencies

**FAIL.** Measured 9 of 9 active other-agency jobs on plan blocks (56 other-agency jobs in the feed).

Pass line: Each active other-agency job on plan blocks is either listed or named on About the data as out of scope.

Coordination feed queried 2026-09-28, the same pull site/data/coordination.json was built from. A job is active when its latest end date is today or later, or it has none.

| Agency | Job | Plan blocks | Listed, named or explained |
| --- | --- | --- | --- |
| SF Bay Ferry | SF Bay Ferry Downtown Ferry Terminal Electrification Project | 16 | — |
| Transbay | DTX - Downtown Rail Extension | 11 | — |
| PG&E - Gas (Capital Planning) | 19th Ave & Lawton St | 8 | — |
| Transbay | DTX - Mission Bay Dr At Grade Crossing | 4 | — |
| SF Port | Pier 80 Electrification | 4 | — |
| PG&E - Gas (Capital Planning) | West Sunset 6 | 3 | — |
| PG&E - Gas (Capital Planning) | 85 Bluxome St | 2 | — |
| PG&E - Gas (Capital Planning) | Taraval St & 47th Ave | 2 | — |
| PG&E - Gas (Capital Planning) | 24th Ave & Vicente St | 2 | — |


## A3. Duplicates

**PASS.** Measured 0 of 252 listed rows: 0 extra same-name rows, 0 of 8 high-overlap pairs not shown as related, 0 of 0 cross-source pairs not merged or related.

Pass line: Zero same-name rows. Every high-overlap pair is either merged or shown on the page as related. (The measure's pairs are Jaccard ≥ 0.5 on blocks, and two sources' rows for the same project that were not merged.)

Blocks are every block a row holds (its record's blocks plus a merged feed job's), not only plan blocks.

| Row | Row | Block overlap (Jaccard) | On the page |
| --- | --- | --- | --- |
| Joint - Streetscape Lead - Folsom St 10032072 | PW Folsom Streetscape Project | 0.93 | shown as related |
| Folsom Howard Streetscape Sewer Replacement | Joint - Streetscape Lead - Folsom St 10032072 | 0.77 | shown as related |
| Folsom Howard Streetscape Sewer Replacement | PW Folsom Streetscape Project | 0.75 | shown as related |
| FASIP - Western SOMA and Northern Mission District Sewer System | Western SOMA and Northern Mission Districts Sewer Replacement WW-719D | 0.67 | shown as related |
| Various Locations Sewer Replacement #21 | PW Various Locations Sewer Replacement No 21 | 0.62 | shown as related |
| M Ocean View Transit and Safety Project | PW - M & J Lines - Muni Forward Project | 0.58 | shown as related |
| WW-779 Various Locations Sewer Replacement No. 32 | Various Locations Sewer Replacement No 32 | 0.58 | shown as related |
| 14-009 8-, and 24-inch Ductile Iron Water Main Replacement on Page Street from Stanyan to Fillmore Streets | Page Slow Street | 0.54 | shown as related |

| Feed row | SFMTA layer project | SFMTA project on the list | On the page |
| --- | --- | --- | --- |


## B1. Link to the department's own page

**PASS.** Measured 153 of 162 jobs a department publishes pages for, of 252 listed; 7 of the rest show no closest official source.

Pass line: Over 90% of the listed projects a department publishes pages for, overall and within each department. That is every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. Every other job shows the closest official source, and About the data says why.

A department page is the job's own page or its contract's bid page on sfmta.com (/node or /projects), sfpublicworks.org, sfpuc.gov, Public Works' bid portal or SFPUC Bids On Line. A DataSF row, a programme page and the Public Works paving map are not one; the last two are shown as the closest official source. Counted: every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. Link status from data/audit/cache/link-status.json (2026-09-29, plus 1 new link(s) read since, the latest on 2026-10-01); a link that did not return 200, or that the cache never checked, does not count, unless a browser read of it (a browser's user agent, GET) returned 200, which is evidence the site blocks robots rather than the page being gone. A closest official source counts only when it answers and the rendered project page carries its address.

| Department | Listed | Counted | With a department page | Share of counted | Not counted; closest source shown | Not counted; no closest source | Counted, no page, a page under nearly the same name |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Public Works | 133 | 53 | 49 | 92.5% | 74 | 6 | 0 |
| SFMTA | 89 | 89 | 84 | 94.4% | 0 | 0 | 1 |
| SFPUC | 30 | 20 | 20 | 100.0% | 9 | 1 | 0 |


What each department publishes, from scripts/department-project-pages.py:
- Public Works, bidPortal: https://bidopportunities.apps.sfdpw.org/ lists only the contracts out to bid now; each has a Details page until it is awarded.
- Public Works, pavingMap: https://sfpublicworks.org/street-resurfacing embeds Public Works' paving map (https://maps.sfdpw.org/arcgis/rest/services/Capital_Projects/Paving/MapServer), which names every paving contract from planning to construction with its JO number, phase, projected fiscal year and estimated construction season. It is the closest official source for a paving job with no page, and it is a programme map, not the job's page.
- Public Works, projectMap: https://sfpublicworks.org/project-map shows the same pages as the project list. maps.sfdpw.org's Capital_Projects/PW_Projects service was last edited in 2020 and points nearly every project at the /projects list.
- Public Works, projectPages: https://sfpublicworks.org/projects lists 269 pages, and its search and /VL{n} and /{contract} aliases reach more. Paving and sewer contracts get a page only once they are in construction; none is published for the paving series in design or planning or for Sewer Replacement Nos. 19 to 40.
- SFPUC, projectPages: https://www.sfpuc.gov/sitemap.xml lists about 68 construction-project pages, the same set as the Construction Project Map on /construction-contracts/construction-projects. None is published for the WD water-main contracts in design (WD-2877, 2918, 2919, 2934, 2935, 2936, 2937, the west half of WD-2922) or for the Page Street and Diamond Street mains.
- SFPUC, sewerProgram: https://www.sfpuc.gov/construction-contracts/sewer-upgrades-renewal-replacement-program lists the sewer contracts in construction by street and WW number (WW-709, 720, 727, 729, 730 on 2026-09-28); a WW contract in design is on no SFPUC page, so this programme page is its closest official source, and the same for a Public Works sewer replacement contract in the WW series.
- SFPUC, waterMains: https://www.sfpuc.gov/construction-contracts/construction-projects/water-main-installation-process describes the water main replacement SFPUC does each year and names no contract; it is the closest official source for a water-main contract in design.

| Department | Closest official source shown | Jobs |
| --- | --- | --- |
| Public Works | Emergency Firefighting Water System | 1 |
| Public Works | Outfall Rehabilitation Projects | 1 |
| Public Works | Public Works paving map | 39 |
| Public Works | Sewer System Upgrades | 4 |
| Public Works | Sewer Upgrades: Renewal & Replacement Program | 27 |
| Public Works | Water Main Replacement Process | 1 |
| Public Works | Westside Enhanced Water Recycling Project | 1 |
| SFPUC | Sewer System Upgrades | 1 |
| SFPUC | Water Main Replacement Process | 8 |

| Department | Job with no page and no closest official source | Phase |
| --- | --- | --- |
| Public Works | Sickles Avenue Streetscape Project | Design |
| Public Works | PW Havelock Pedestrian Bridge - Sidewalk Improvements | Design |
| Public Works | PW FY21 Bike Traffic Signal Upgrade Program | Design |
| Public Works | Stormwater Trash Capture | Design |
| Public Works | Bayview Multimodal Project | Design |
| Public Works | Stormwater Trash Capture Phase 2 | Planning |
| SFPUC | Northern Waterfront Electrical Improvements (NWEI) | Planning |

| Department | Counted row with no department link | Department page under nearly the same name |
| --- | --- | --- |
| SFMTA | Great Highway Traffic Signal Upgrades | Great Highway Pilot Project |


The 7 jobs with no page and no closest official source are said on About the data (method: Dates and links.: “For 7 Public Works and SFPUC jobs, we couldn't find any official page, so they link only to their coordination feed row.”), per Bryan's decision of 2026-09-30 to log them there.

## B2. Key fields present

**FAIL.** Measured start 92.1%, phase 98.0%; 0 missing values not shown as not published of 252.

Pass line: Start and phase on 95% of rows. Every missing value shows as “not published” on the page, never as a blank.

| Field | Public Works | SFMTA | SFPUC | All |
| --- | --- | --- | --- | --- |
| name | 0 | 0 | 0 | 0 |
| department | 0 | 0 | 0 | 0 |
| phase | 0 | 5 | 0 | 5 |
| start | 2 | 18 | 0 | 20 |
| end | 4 | 32 | 0 | 36 |
| streets | 0 | 8 | 0 | 8 |
| geometry | 1 | 11 | 0 | 12 |
| scope | 46 | 66 | 0 | 112 |

Start given only as a month, season or year: 77.
Missing values the project page does not show as “not published”: start 0, end 0, scope 0.

| Project | Field shown blank |
| --- | --- |


Start is under the 95% line, and About the data's top issues carry no item for it.

## B3. Status agrees across sources

**PASS.** Measured 0 of 24 SFMTA/Public Works pairs disagree unshown; 0 of 21 merged rows disagree unshown (10 disagree) of 24 projects both SFMTA's layer and Public Works' pages publish, and 21 merged SFMTA/feed rows.

Pass line: Every disagreement is printed with both values.

A layer phase of Completed or Project Evaluation is done, none is unknown, any other is active; a Public Works page status of Completed is done, any other is active. A disagreement counts as shown when the page that carries the job prints both values: its listed project page, the notice page its address keeps after it leaves the list, or, for a job on neither, the line naming it among another listed project's neighbours, all read from the built site.

| SFMTA layer | Public Works page | SFMTA phase | Public Works status | Result |
| --- | --- | --- | --- | --- |
| 13th Street Safety Project | 13th Street Safety Improvement Project | Implementation / Construction | In progress | agree |
| 9 San Bruno Rapid Project | 9 San Bruno Muni Forward Project | Completed | Completed | agree |
| Bayview Community Based Transportation Plan | Bayview Transportation Improvements Project | Planning | In progress | agree |
| Better Market Street | Better Market Street | Current | In progress | agree |
| Contract 36 Traffic Signal Modifications | Traffic Signal Modifications Contract #36 | Implementation / Construction | In progress | agree |
| Contract 65 New Traffic Signals | Contract No. 65 New Traffic Signals | Legislated | In progress | agree |
| Inner Sunset Streetscape Improvement Project | Inner Sunset Streetscape Improvements Project and Muni Forward Project | Completed | Completed | agree |
| Polk Streetscape Project | Polk Streetscape Project | Completed | Completed | agree |
| Safer Taylor Street | Safer Taylor Street | Completed | Completed | agree |
| Second Street Improvement Project | Second Street Improvements Project | Completed | Completed | agree |
| South Van Ness Avenue Quick-Build Project | Van Ness Avenue Enhancement Project | Completed | Completed | agree |
| Transbay Howard Streetscape Improvement Project | Transbay Howard Streetscape Improvement Project | Implementation / Construction | In progress | agree |
| Transit U Improvement Project | Transit U Improvement Project | Implementation / Construction | In progress | agree |
| Wiggle Neighborhood Green Corridor | Wiggle Neighborhood Green Corridor | Completed | Completed | agree |
| 6th Street Pedestrian Safety Project | 6th Street Pedestrian Safety Project | Current | Completed | both shown |
| Lombard Street Vision Zero Project | Lombard Street Vision Zero Project | Legislated | Completed | both shown |
| Mission / Geneva Safety Project | Mission Street and Geneva Avenue Infrastructure Improvement Project | Legislated | Completed | both shown |
| San Bruno Ave Multimodal Improvement Project | San Bruno Streetscape Improvement Project | Implementation / Construction | Completed | both shown |
| Geneva Avenue Traffic Signal Upgrades | Geneva Avenue Traffic Signal Project | Completed | In progress | both shown on its notice page |
| Masonic Avenue Streetscape Project | Masonic Avenue Streetscape Improvement Project | Completed | In progress | both shown on its notice page |
| Muni Forward 9 San Bruno Rapid Proposal | 9 San Bruno Muni Forward Project | Current | Completed | both shown on its notice page |
| Third Street Bridge Rehabilitation Project | Third Street Bridge Rehabilitation Project | no phase | Completed | both shown on its notice page |
| Upper Market Street Safety Project | Upper Market Corridor Safety Improvements Project | Implementation / Construction | Completed | both shown on its notice page |
| Upper Haight Transit Improvement and Pedestrian Realm Project | Upper Haight Transit Improvement and Pedestrian Realm Project | Completed | In progress | both shown where it is a neighbour on Various Locations Sewer Replacement No 36's page |

| Merged row | SFMTA phase | Feed phase | Same stage |
| --- | --- | --- | --- |
| M Ocean View Transit and Safety Project | Quick-Build Implementation and Detailed Design | Planning | no, both shown |
| 13th Street Safety Project | Implementation / Construction | Construction | yes |
| Beach Street Quick-Build Project | Implementation / Construction | Construction | yes |
| Brotherhood-Alemany Quick-Build Project | Planning | Design | no, both shown |
| Transit U Improvement Project | Implementation / Construction | Construction | yes |
| Oak Street Quick-Build Project | Implementation (with street repaving) | Design | no, both shown |
| Brotherhood/Alemany Safety Improvements Project | Coordination and Funding Plan | Planning | yes |
| Innes Avenue Quick-Build Project | Planning | Design | no, both shown |
| J Church Safety and Accessibility Project: San Jose Avenue | Implementation / Construction | Planning | no, both shown |
| K Ingleside Rapid Project | Detailed Design | Planning | no, both shown |
| Main Street Streetscape Project | Detailed Design | Design | yes |
| Page Slow Street | Planning | Design | no, both shown |
| Contract 35 Traffic Signal Modifications | Detailed Design | Construction | no, both shown |
| Golden Gate Park Access and Safety Program | Legislated | Planning | no, both shown |
| Transbay Howard Streetscape Improvement Project | Implementation / Construction | Construction | yes |
| Cayuga Avenue Slow Street | Detailed Design | Construction | no, both shown |
| Tenderloin Traffic Signal Upgrades | Detailed Design | Design | yes |
| Contract 66 New Traffic Signals | Detailed Design | Design | yes |
| Cesar Chavez Bikeway Improvements Project | Detailed Design | Design | yes |
| Church and Market Street Intersection Improvements | Design | Design | yes |
| Lincoln Way New Traffic Signals | Detailed Design | Design | yes |


## C1. Source coverage

**PASS.** Measured 7 of 7 deciding bodies.

Pass line: Each deciding body read from 2019 or earlier to within a month of today, with less than 5% of meetings missing, and full item titles kept. Each body has its own fetch script that mirrors meetings to disk, re-fetches drafts, and can be rerun without re-downloading what it holds.

| Body | First | Last | Meetings held | Missing | Titles kept | Script | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Board of Supervisors | 2019-01-07 | 2026-09-30 | 1633 | 5 | 31690 items, from out/record-coverage/coverage.json | scripts/fetch-bos-meetings.py | PASS |
| Public Works Commission | 2022-07-28 | 2026-09-24 | 77 | 1 | 1147 items, from out/record-coverage/coverage.json; established 2022-07-01 (Board of Supervisors motion of 2021-12-14 setting the Charter §4.139(d) transition date), read from its first meeting | scripts/fetch-public-works-commission.py | PASS |
| Recreation and Park Commission | 2019-01-17 | 2026-09-17 | 95 | 0 | 2207 items, from out/record-coverage/coverage.json | scripts/fetch-rec-park-commission.py | PASS |
| SFCTA Board | 2019-01-29 | 2026-09-22 | 171 | 1 | 2201 items, from out/record-coverage/coverage.json | scripts/fetch-sfcta-board.py | PASS |
| SFMTA Board | 2019-01-15 | 2026-09-01 | 181 | 1 | 3656 items, from out/record-coverage/coverage.json | scripts/fetch-sfmta-board.py | PASS |
| SFMTA engineering hearings | 2019-08-16 | 2026-09-25 | 145 | 1 | 2099 items, from out/record-coverage/coverage.json | scripts/fetch-sfmta-hearings.py | PASS |
| SFPUC Commission | 2019-01-22 | 2026-09-08 | 177 | 1 | 4975 items, from out/record-coverage/coverage.json | scripts/fetch-sfpuc-commission.py | PASS |


## C2. Mentions per major project

**FAIL.** Measured 12 of 107 major projects (outlined, or at least 1 mi of plan network, counted per direction of travel; About the data states no basis, measured from the bikeway layer and the plan's map).

Pass line: Every major project with fewer than three distinct dated records from city bodies has its reason printed; the share with three or more is reported.

11.2% have three or more. A record counts when it comes from a city body (not the project's own page) and is graded exact, strong or probable. For each one below three, the project's name was searched in every deciding body's meeting mirror; dates found there that the matcher did not attach make it a matching miss.
Searched: every non-procedural item of the 7 deciding bodies' meeting mirrors (42540 items), the same bodies scripts/project-record.py matches against.

| Body | Mirror | Meetings its index says are mirrored | Meeting files read | Items searched | State |
| --- | --- | --- | --- | --- | --- |
| SFMTA engineering hearing | data/sfmta-hearings/meetings/ | 144 | 144 | 2099 | complete |
| SFMTA Board of Directors | data/sfmta-board/meetings/ | 180 | 180 | 2138 | complete |
| Board of Supervisors | data/bos-meetings/meetings/ | 1628 | 1628 | 31588 | complete |
| SFPUC Commission | data/sfpuc-commission/meetings/ | 176 | 176 | 3642 | complete |
| Public Works Commission | data/public-works-commission/meetings/ | 76 | 76 | 586 | complete |
| SFCTA Board | data/sfcta-board/meetings/ | 170 | 170 | 1189 | complete |
| Recreation and Park Commission | data/rec-park-commission/meetings/ | 95 | 95 | 1298 | complete |

The name search takes the project's whole name, its words in order with only articles, “project” and “program” dropped, never a street alone: “5th Street Improvement Project” is searched as “5th Street Improvement”, not “5th Street”. A contract number the name or scope carries is searched too. It reads each item's title and its own text, not the minutes' account of the discussion after it.
An item that names a longer listed project holding this one's name (“Folsom-Howard Streetscape” for “Howard Streetscape”) is that project's, and is not counted here.

Of the 95 under three: 95 real gaps, 0 partly missed and 0 matching misses by the independent name search. 53 are Public Works or SFPUC construction contracts, which reach a commission at award and at later contract changes, and 38 have not started.

| Department | Major project | City-body dates | Name found by date (body: dates) | Reading | What the record shows | Explanation |
| --- | --- | --- | --- | --- | --- | --- |
| Public Works | 11th Street Safety Improvements Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; no Public Works page for this job; closest official source: Public Works paving map | — |
| Public Works | 16th St, 17th St, and 18th St Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2033-08-30, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2033-08-30, after 2026-10-01 |
| Public Works | 18th St and Valencia St Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2032-12-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2032-12-28, after 2026-10-01 |
| Public Works | 5th St Safety Improvement Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2029-05-01, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2029-05-01, after 2026-10-01 |
| Public Works | 7th St, 8th St and Folsom St Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2030-06-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2030-06-28, after 2026-10-01 |
| Public Works | As Needed Citywide Pavement Preservation Contract 5 (General As-Needed Contract G23) | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; no Public Works page for this job; closest official source: Public Works paving map | — |
| Public Works | Battery Street Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2030-08-30, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2030-08-30, after 2026-10-01 |
| Public Works | Bay Shore Blvd and Cesar Chavez Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-11-09, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2027-11-09, after 2026-10-01 |
| Public Works | Bayview Multimodal Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-06-30, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2027-06-30, after 2026-10-01 |
| Public Works | Brotherhood Way Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2034-07-19, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2034-07-19, after 2026-10-01 |
| Public Works | Chinatown and SOMA Large Diameter Sewer Improvements | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-07-31, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer System Upgrades | NOT-DUE: work starts 2027-07-31, after 2026-10-01 |
| Public Works | Geneva Ave and Sloat Blvd Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2029-12-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2029-12-29, after 2026-10-01 |
| Public Works | Hayes St, Fell St and Van Ness Ave Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2029-03-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2029-03-28, after 2026-10-01 |
| Public Works | Holloway Ave and Lake Merced Blvd Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2032-08-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2032-08-29, after 2026-10-01 |
| Public Works | Howard Streetscape Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Joint - Streetscape Lead - Folsom St 10032072 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Market St from Octavia St to Castro St Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2031-05-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2031-05-29, after 2026-10-01 |
| Public Works | Mission District Sewer Rehabilitation (VLLD2B) | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-06-07, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer System Upgrades | NOT-DUE: work starts 2027-06-07, after 2026-10-01 |
| Public Works | Mission, 8th, 9th, Howard and Natoma Brick Sewer Rehabilitation | 1 | SFPUC Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Monterey Blvd Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2028-04-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2028-04-29, after 2026-10-01 |
| Public Works | OShaughnessy and Woodside Ave Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2031-12-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2031-12-29, after 2026-10-01 |
| Public Works | PW - M & J Lines - Muni Forward Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | PW As Needed Spot Sewer Replacement No 47 | 1 | SFPUC Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | PW StreetResurfacingPro-BBSR Pavement Prese FY 26-27 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; no Public Works page for this job; closest official source: Public Works paving map | — |
| Public Works | PW Various Locations Sewer Replacement No 17 | 1 | SFPUC Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Portola Dr Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2030-05-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2030-05-28, after 2026-10-01 |
| Public Works | San Bruno Ave Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2028-02-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2028-02-28, after 2026-10-01 |
| Public Works | Stormwater Trash Capture | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-06-28, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2027-06-28, after 2026-10-01 |
| Public Works | Stormwater Trash Capture Phase 2 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-11-29, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2027-11-29, after 2026-10-01 |
| Public Works | Street Resurfacing Program- BBSR Paving FY 26-27 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; no Public Works page for this job; closest official source: Public Works paving map | — |
| Public Works | Sutter St and Post St Large Diameter Sewer Rehabilitation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2029-08-30, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer System Upgrades | NOT-DUE: work starts 2029-08-30, after 2026-10-01 |
| Public Works | Sutter St and Post St Pavement Renovation | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2029-08-30, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2029-08-30, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 100 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2030-04-29, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2030-04-29, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 104 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2033-09-30, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2033-09-30, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 69 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Various Locations Pavement Renovation No 77 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Various Locations Pavement Renovation No 78 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Various Locations Pavement Renovation No 79 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Various Locations Pavement Renovation No 82 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2026-11-23, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2026-11-23, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 86A | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-09-04, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Public Works paving map | NOT-DUE: work starts 2027-09-04, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 89 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-01-28, so its contract award, the usual deciding record, is not due yet; when the bid page closes at award, the closest official source: Public Works paving map | NOT-DUE: work starts 2027-01-28, after 2026-10-01 |
| Public Works | Various Locations Pavement Renovation No 90 | 1 | Public Works Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| Public Works | Various Locations Sewer Replacement No 33 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2028-06-01, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer Upgrades: Renewal & Replacement Program | NOT-DUE: work starts 2028-06-01, after 2026-10-01 |
| Public Works | Various Locations Sewer Replacement No 38 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2028-04-28, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer Upgrades: Renewal & Replacement Program | NOT-DUE: work starts 2028-04-28, after 2026-10-01 |
| Public Works | Various Locations Spot Main Sewer Replacement No 2 | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2027-03-15, so its contract award, the usual deciding record, is not due yet; no Public Works page for this job; closest official source: Sewer Upgrades: Renewal & Replacement Program | NOT-DUE: work starts 2027-03-15, after 2026-10-01 |
| Public Works | Visitacion Avenue Streetscape Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the Public Works Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2026-12-28, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2026-12-28, after 2026-10-01 |
| SFMTA | 12th Avenue Slow Street | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 4 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | 23rd Avenue Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 5 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | 29 Sunset Improvement Project – Phase Two | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 6 item(s), which C2 does not count | — |
| SFMTA | 5th Street Improvement Project | 2 | SFMTA Board of Directors 1, SFMTA engineering hearing 1 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 17 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 7 item(s), which C2 does not count | — |
| SFMTA | 8 Bayshore: Visitacion Valley Stop Improvements | 2 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 3 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 2 item(s), which C2 does not count | — |
| SFMTA | Arguello Safety Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 9 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 3 item(s), which C2 does not count | — |
| SFMTA | Arlington Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name | — |
| SFMTA | Bayview Community Pathway | 2 | SFMTA Board of Directors 2 | gap | no item of the seven bodies names it beyond the dates attached; work starts 2028, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 7 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 7 item(s), which C2 does not count | NOT-DUE: work starts 2028, after 2026-10-01 |
| SFMTA | Beach Street Quick-Build Project | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 10 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 5 item(s), which C2 does not count | — |
| SFMTA | Bikeway Hardening | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 23 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | Bosworth/Monterey Connections Quick-Build Project | 0 | none | gap | no item of the seven bodies names it; work starts 2027-01, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 7 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 5 item(s), which C2 does not count | NOT-DUE: work starts 2027-01, after 2026-10-01 |
| SFMTA | Brotherhood-Alemany Quick-Build Project | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 5 item(s), which C2 does not count | — |
| SFMTA | Cabrillo Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 4 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | Central Embarcadero Safety Project | 2 | SFMTA Board of Directors 2 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 27 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 4 item(s), which C2 does not count | — |
| SFMTA | Cesar Chavez Bikeway Improvements Project | 0 | none | gap | no item of the seven bodies names it; work starts 2027, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 4 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 3 item(s), which C2 does not count | NOT-DUE: work starts 2027, after 2026-10-01 |
| SFMTA | Clarendon Quick-Build | 2 | SFMTA Board of Directors 1, SFMTA engineering hearing 1 | gap | no item of the seven bodies names it beyond the dates attached; work starts 2027-04, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 1 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 6 item(s), which C2 does not count | NOT-DUE: work starts 2027-04, after 2026-10-01 |
| SFMTA | Clay Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 4 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | Contract 35 Traffic Signal Modifications | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 4 item(s), which C2 does not count | — |
| SFMTA | Contract 36 Traffic Signal Modifications | 2 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 25 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 3 item(s), which C2 does not count | — |
| SFMTA | Contract 65 New Traffic Signals | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 17 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 3 item(s), which C2 does not count | — |
| SFMTA | Contract 66 New Traffic Signals | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; work starts 2027-10, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 17 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 6 item(s), which C2 does not count | NOT-DUE: work starts 2027-10, after 2026-10-01 |
| SFMTA | Dogpatch-Central Waterfront Area Transit Connections Study | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 19 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 4 item(s), which C2 does not count | — |
| SFMTA | Folsom-Howard Streetscape Project | 2 | SFMTA Board of Directors 1 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 21 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 22 item(s), which C2 does not count | — |
| SFMTA | Golden Gate Avenue Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 8 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists a public hearing on 2022-06-10, which no meeting mirror holds (the hearing mirror holds the biweekly engineering hearings, not a project's own virtual hearing); its own page lists 5 item(s), which C2 does not count | UNMIRRORED: its own page dates a public hearing on 2022-06-10, which no meeting mirror holds |
| SFMTA | Great Highway Traffic Signal Upgrades | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; no SFMTA page for this project (sfmta.com answers “Content Not Found”, HTTP 403: Forbidden, though its project layer still lists one); closest official source: SFMTA, Sloat Blvd Quick-Build Project | — |
| SFMTA | Hearst Avenue Slow Street | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 3 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | Innes Avenue Quick-Build Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 3 item(s), which C2 does not count | — |
| SFMTA | J Church Safety and Accessibility Project: San Jose Avenue | 2 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 3 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 5 item(s), which C2 does not count | — |
| SFMTA | Jefferson Street Quick-Build Project | 0 | none | gap | no item of the seven bodies names it; work starts 2027, so its contract award, the usual deciding record, is not due yet; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 7 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 4 item(s), which C2 does not count | NOT-DUE: work starts 2027, after 2026-10-01 |
| SFMTA | K Ingleside Rapid Project | 1 | SFMTA Board of Directors 1 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 1 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists a public hearing on 2024-01-08, which no meeting mirror holds (the hearing mirror holds the biweekly engineering hearings, not a project's own virtual hearing); its own page lists 10 item(s), which C2 does not count | UNMIRRORED: its own page dates a public hearing on 2024-01-08, which no meeting mirror holds |
| SFMTA | Laurel Heights/Jordan Park Traffic Calming Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 6 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted | — |
| SFMTA | M Ocean View Transit and Safety Project | 2 | SFMTA Board of Directors 2 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 1 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists a public hearing on 2023-08-25, which no meeting mirror holds (the hearing mirror holds the biweekly engineering hearings, not a project's own virtual hearing); its own page lists 12 item(s), which C2 does not count | UNMIRRORED: its own page dates a public hearing on 2023-08-25, which no meeting mirror holds |
| SFMTA | No Turn on Red Downtown Expansion Project | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 5 item(s), which C2 does not count | — |
| SFMTA | Oak Street Quick-Build Project | 2 | SFMTA Board of Directors 1 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 10 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 8 item(s), which C2 does not count | — |
| SFMTA | Page Slow Street | 2 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 20 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 7 item(s), which C2 does not count | — |
| SFMTA | Parkmerced Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 3 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; no SFMTA page for this project (sfmta.com answers “Content Not Found”, HTTP 403: Forbidden, though its project layer still lists one); closest official source: SF Planning, Parkmerced | NOT-DUE: no start published and the phase is Planning, so work has not started |
| SFMTA | Pay or Permit Parking Expansion Project | 1 | SFMTA Board of Directors 1 | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 7 item(s), which C2 does not count | — |
| SFMTA | San Bruno Ave Multimodal Improvement Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists a Board meeting on 2016-10-18, a public hearing on 2016-08-19, which no meeting mirror holds (the hearing mirror holds the biweekly engineering hearings, not a project's own virtual hearing); its own page lists 3 item(s), which C2 does not count | UNMIRRORED: its own page dates a Board meeting on 2016-10-18, a public hearing on 2016-08-19, which no meeting mirror holds |
| SFMTA | Sloat Blvd Quick-Build Project | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 8 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 6 item(s), which C2 does not count | — |
| SFMTA | Sutter Street Quick-Build Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 19 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 3 item(s), which C2 does not count | NOT-DUE: no start published and the phase is Planning, so work has not started |
| SFMTA | Visitacion Valley and Portola Proactive Traffic Calming Project | 0 | none | gap | no item of the seven bodies names it; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; its own page lists 3 item(s), which C2 does not count | — |
| SFMTA | Winston Drive Quick-Build Project | 1 | none | gap | no item of the seven bodies names it beyond the dates attached; the engineering hearing and the SFMTA Board itemise work by street and action, not by project name; 3 more dated item(s) on its streets are other work there (a dock, a zone, another project) or match more than one project, so they are shown and not counted; its own page lists 1 item(s), which C2 does not count | — |
| SFPUC | 14-009 8-, and 24-inch Ductile Iron Water Main Replacement on Page Street from Stanyan to Fillmore Streets | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; no SFPUC page for this job; closest official source: Water Main Replacement Process | — |
| SFPUC | Northern Waterfront Electrical Improvements (NWEI) | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| SFPUC | PEFWS Pipeline - 36- & 42-inch Welded Steel Pipe | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| SFPUC | PEFWS Pipeline Contract E - 24-inch GGP Crossing | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| SFPUC | PEFWS Pipeline Contract G - 36-Inch Water | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board; work starts 2028-10-01, so its contract award, the usual deciding record, is not due yet | NOT-DUE: work starts 2028-10-01, after 2026-10-01 |
| SFPUC | San Bruno Avenue & Blanken Avenue Water Main Replacement Project | 0 | none | gap | no item of the seven bodies names it; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |
| SFPUC | WD-2921 8- and 12-inch Ductile Iron Water Main Replacement on Palou, Quesada, and Revere Ave from 3rd St to Griffith St | 1 | SFPUC Commission 1 | gap | no item of the seven bodies names it beyond the dates attached; a construction contract reaches the SFPUC Commission at its award and at later changes to the contract, not at each stage of design the way an SFMTA project reaches the hearing and the Board | — |


## C3a. Labels: project-page items under City decisions

**PASS.** Measured 0 of 251 items under City decisions.

Pass line: No mislabelled kinds: nothing from a project's own page shows under “City decisions naming this project”.

364 project-page items are shown apart, in the page's own fold, not under City decisions: Project page timeline 235, Project page event 115, Project page notice 14.
Of those labelled as a city body, 0 are not a meeting of that body (open houses, tabling, walks, advisory committees):

| Project | Date | Label shown | Title |
| --- | --- | --- | --- |


## C3b. Records naming a project's contract number or full name

**PASS.** Measured 0 of 252 listed projects, searched in their attached records and 42540 mirror items.

Pass line: Every item naming the project's name or contract number is counted as the project's own.

An item counts when its title carries the project's contract number (WD-, WW-, CS-… read from the name or scope) or its full name (three or more distinctive words, in order), and the project shows it under anything weaker than its own record or does not attach it at all. The search covers each project's attached records and every item of the deciding bodies' meeting mirrors.
Searched: every non-procedural item of the 7 deciding bodies' meeting mirrors (42540 items), the same bodies scripts/project-record.py matches against.

| Body | Mirror | Meetings its index says are mirrored | Meeting files read | Items searched | State |
| --- | --- | --- | --- | --- | --- |
| SFMTA engineering hearing | data/sfmta-hearings/meetings/ | 144 | 144 | 2099 | complete |
| SFMTA Board of Directors | data/sfmta-board/meetings/ | 180 | 180 | 2138 | complete |
| Board of Supervisors | data/bos-meetings/meetings/ | 1628 | 1628 | 31588 | complete |
| SFPUC Commission | data/sfpuc-commission/meetings/ | 176 | 176 | 3642 | complete |
| Public Works Commission | data/public-works-commission/meetings/ | 76 | 76 | 586 | complete |
| SFCTA Board | data/sfcta-board/meetings/ | 170 | 170 | 1189 | complete |
| Recreation and Park Commission | data/rec-park-commission/meetings/ | 95 | 95 | 1298 | complete |


| Project | Date | Body | Names | Graded | Title |
| --- | --- | --- | --- | --- | --- |


## C3c. Matching accuracy: hand-checked sample

**PASS.** Measured 53 of 53 graded links the list still counts, of 60 graded (7 no longer counted: 0 graded wrong, 7 graded right).

Pass line: Every link in a seeded random sample of at least 40 is about its project and carries the right kind label.

A graded link the list no longer counts as the project's own is shown apart. When most of the sample has left the list, draw a new one: delete the grade columns' contents and run the audit.

| Project | Date | Label | About project | Label correct | Note | Now |
| --- | --- | --- | --- | --- | --- | --- |
| 5th St Safety Improvement Project | 2019-09-17 | SFMTA Board | yes | yes | SFMTA Board approves the 5th Street Improvement Project bike lanes, Market to Townsend; the same corridor project, an earlier phase than the Public Works build | no longer counted |
| Page Street Neighborway Project | 2020-12-08 | SFCTA Board | yes | yes | SFCTA approves $1 million of Central Freeway parcel revenue for the Page Street Neighborway Project | no longer counted |
| Slow Streets | 2020-09-29 | Board of Supervisors | yes | yes | Board affirms the CEQA exemption for Slow Streets Phase 3 | no longer counted |
| Slow Streets | 2022-01-11 | Board of Supervisors | yes | yes | Regraded after the label fix: a Mayor's question-time topic that names Slow Streets; filed, nothing decided; the label now says heard, no decision, which is right | no longer counted |
| 4th Street Transit Improvement Project | 2019-10-01 | SFMTA Board | yes | yes | Board adopts the 4th Street bus zone the project installs; its page lists this Board meeting | no longer counted |
| Active Beale Street | 2020-06-16 | SFMTA Board | yes | yes | Board adopts the Beale Street transit lane, Market to Natoma; its page lists this Board meeting | no longer counted |
| Frida Kahlo Way Quick-Build Project | 2024-05-07 | SFMTA Board | yes | yes | Board approves the Frida Kahlo Way and Judson Avenue bikeways and safety changes, which are this project | no longer counted |


## C4. A record before work starts

**FAIL.** Measured 79 of 232.

Pass line: Over 90% of listed projects with a start date have a city-body record dated before that start, or the shortfall is logged as a top issue on About the data (Bryan, 2026-09-29: "Let's just log this as a problem and add to the list of issues. That we have most projects in the shared feed that don't have a project page.").

34.1% have one. A record counts when it comes from a city body, is graded exact, strong or probable, and is dated before the project's start at the start's own precision. A job that has not started is usually not yet awarded, so its deciding record may not exist yet; the two are counted apart.

| Department | Started, with a record before | Not yet started, with one | All |
| --- | --- | --- | --- |
| Public Works | 33 of 49 | 4 of 82 | 37 of 131 |
| SFMTA | 30 of 57 | 6 of 14 | 36 of 71 |
| SFPUC | 5 of 21 | 1 of 9 | 6 of 30 |
| All | 68 of 127 | 11 of 105 | 79 of 232 |


Why the rest have none, by department and kind of work. “No city-body item names it” means a search of every item of the seven deciding bodies' mirrors for the project's whole name and any contract number found nothing dated before its start; for a job that has not started, the award that would decide it is not due yet.

| Department | Kind | Cause | Projects |
| --- | --- | --- | --- |
| Public Works | paving | not started; no city-body item names it yet | 39 |
| Public Works | sewer | not started; no city-body item names it yet | 31 |
| SFMTA | street design | started; no city-body item names it | 18 |
| SFPUC | water | started; no city-body item names it | 9 |
| SFMTA | street design | not started; no city-body item names it yet | 8 |
| SFPUC | water | not started; no city-body item names it yet | 8 |
| Public Works | street design | started; no city-body item names it | 5 |
| Public Works | paving | started; no city-body item names it | 4 |
| Public Works | sewer | started; no city-body item names it | 4 |
| Public Works | street design | not started; no city-body item names it yet | 4 |
| Public Works | water | not started; no city-body item names it yet | 3 |
| SFMTA | other | started; no city-body item names it | 3 |
| SFMTA | street design | started; its city-body records all date from after the start | 3 |
| SFPUC | sewer | started; no city-body item names it | 3 |
| SFMTA | other | started; its city-body records all date from after the start | 2 |
| SFPUC | other | started; no city-body item names it | 2 |
| Public Works | other | not started; no city-body item names it yet | 1 |
| Public Works | other | started before the Public Works Commission existed (2022-07); no city-body item names it | 1 |
| Public Works | sewer | started before the Public Works Commission existed (2022-07); no city-body item names it | 1 |
| Public Works | water | started; no city-body item names it | 1 |
| SFMTA | other | started before 2019, before the mirrors begin | 1 |
| SFPUC | paving | started; no city-body item names it | 1 |
| SFPUC | water | started; its city-body records all date from after the start | 1 |


42 of them are Public Works paving jobs whose only published source before work is Public Works' paving map, the five-year paving plan (the row links it as the closest official source). The criterion's record is a dated record from a city body: the plan is a department's schedule, not a body's decision, and gives no decision date, so it is not counted.

| Department | Project | Start | Started | Kind | Cause | Only the paving plan | Body that should have decided it |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Public Works | 11th Street Safety Improvements Project | 2026-06-01 | started | street design | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | 16th St, 17th St, and 18th St Pavement Renovation | 2033-08-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | 18th St and Valencia St Pavement Renovation | 2032-12-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | 5th St Safety Improvement Project | 2029-05-01 | not yet | street design | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | 7th St, 8th St and Folsom St Pavement Renovation | 2030-06-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | 8-Inch Ductile Iron Water Main Replacement on Harkness, Goettingen, Brussels, Girard Streets and Various Streets | 2026-09-01 | started | water | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Alemany Boulevard Infrastructure Improvements Project | 2019-06 | started | other | started before the Public Works Commission existed (2022-07); no city-body item names it |  | Director of Public Works (order; not published online) |
| Public Works | As Needed City-wide Pavement Preservation 6 (General As-Needed Contract G29) | 2025-04-02 | started | paving | started; no city-body item names it | yes | Public Works Commission (contract award) |
| Public Works | Battery Street Pavement Renovation | 2030-08-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Bay Shore Blvd and Cesar Chavez Pavement Renovation | 2027-11-09 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Bayview Multimodal Project | 2027-06-30 | not yet | street design | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Broad Street and Randolph Street Sewer Replacement | 2022-03-15 | started | sewer | started before the Public Works Commission existed (2022-07); no city-body item names it |  | Director of Public Works (order; not published online) |
| Public Works | Broadway, Pacific Ave and Vallejo St Pavement Renovation | 2029-05-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Brotherhood Way Pavement Renovation | 2034-07-19 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Cesar Chavez St from Hampshire St to Guerrero St Pavement Renovation | 2031-12-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Chinatown and SOMA Large Diameter Sewer Improvements | 2027-07-31 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Church St Pavement Renovation | 2032-10-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | EFWS Fort Mason Manifold Relocation | 2028-10-30 | not yet | water | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Folsom Howard Streetscape Sewer Replacement | 2024-03-11 | started | sewer | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Front St and Sansome St Pavement Renovation | 2027-02-06 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Front Street, Sansome Street, 1st Street, and Montgomery Street Pavement Renovation and Sewer Replacement | 2024-02-22 | started | paving | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Front Street, Sansome Street, 1st Street, and Montgomery Street Pavement Sewer Replacement | 2027-02-06 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Geneva Ave and Sloat Blvd Pavement Renovation | 2029-12-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Hayes St, Fell St and Van Ness Ave Pavement Renovation | 2029-03-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Holloway Ave and Lake Merced Blvd Pavement Renovation | 2032-08-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Howard Streetscape Project | 2026-07 | started | street design | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Joint - MTA Lead - Fillmore St Pavement Renovation | 2031-09-01 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Joint - MTA Lead - Fillmore St Pavement Renovation Phase 2 | 2031-10-11 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Joint - SFWD Lead - PEWS Pipe Contract D - 24-inch | 2031-01-03 | not yet | water | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Joint - Streetscape Lead - Folsom St 10032072 | 2024-05 | started | street design | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Market St from Octavia St to Castro St Pavement Renovation | 2031-05-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Mission District Sewer Rehabilitation (VLLD2B) | 2027-06-07 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Monterey Blvd Pavement Renovation | 2028-04-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Monterey Blvd Sewer Replacement | 2028-04-29 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Noriega St and Quintara St Pavement Renovation | 2032-06-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | OShaughnessy and Woodside Ave Pavement Renovation | 2031-12-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Ocean Beach Climate Adaptation Project | 2029 | not yet | other | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW - M & J Lines - Muni Forward Project | 2023-12-27 | started | street design | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | PW FY21 Bike Traffic Signal Upgrade Program | 2027-02-22 | not yet | street design | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW StreetResurfacingPro-BBSR Pavement Prese FY 26-27 | 2026-07-01 | started | paving | started; no city-body item names it | yes | Public Works Commission (contract award) |
| Public Works | PW Various Locations Sewer Replacement (JV VL PR No 89) | 2027-01-28 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW Various Locations Sewer Replacement No 19 | 2027-03-03 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW Various Locations Sewer Replacement No 20 | 2026-11-06 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW Various Locations Sewer Replacement No 21 | 2026-10-02 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | PW Various Locations Sewer Replacement No 31 | 2027-06-07 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Portola Dr Pavement Renovation | 2030-05-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | San Bruno Ave Pavement Renovation | 2028-02-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | San Bruno Sewer Replacement and Rehab | 2028-02-28 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Sickles Avenue Streetscape Project | 2026-08-10 | started | street design | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Stormwater Trash Capture | 2027-06-28 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Stormwater Trash Capture Phase 2 | 2027-11-29 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Street Resurfacing Program- BBSR Paving FY 26-27 | 2026-07-01 | started | paving | started; no city-body item names it | yes | Public Works Commission (contract award) |
| Public Works | Street Resurfacing Program-BBSR Paving FY 27-28 | 2027-07-01 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Sunset Irrigation Recycled Water | 2027-06-29 | not yet | water | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Sutter St and Post St Large Diameter Sewer Rehabilitation | 2029-08-30 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Sutter St and Post St Pavement Renovation | 2029-08-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Location Sewer Replacement No 22 | 2026-08-24 | started | sewer | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Various Locations Large Diameter Sewer Improvements No 1 | 2027-03-04 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation Concrete No 94 | 2031-02-01 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation Concrete No 97 | 2034-02-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 100 | 2030-04-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 101 | 2030-12-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 102 | 2031-04-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 104 | 2033-09-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 105 | 2033-10-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 86A | 2027-09-04 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 86B | 2030-10-30 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 87 | 2027-03-13 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 89 | 2027-01-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 92 | 2027-03-29 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation No 99 | 2030-03-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation Under Overhead Contact System No 3 | 2034-01-28 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Pavement Renovation Under Overhead Contact System No 4 | 2035-02-02 | not yet | paving | not started; no city-body item names it yet | yes | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement #21 | 2024-02-27 | started | sewer | started; no city-body item names it |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 24 | 2027-03-25 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 25 | 2027-02-25 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 26 | 2027-08-31 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 27 | 2027-02-19 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 28 | 2027-03-01 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |
| Public Works | Various Locations Sewer Replacement No 29 | 2027-06-12 | not yet | sewer | not started; no city-body item names it yet |  | Public Works Commission (contract award) |

73 more rows not shown.


Of the 153 without one, 102 are coordination-feed jobs with no project page of their own and 51 have a project page; 0 of those have a written explanation. 
Below the 90% line, and About the data's top issues carry no item saying that coordination-feed jobs have no project page and so no city-body decision found before work starts.

The misses that have a project page:

| Department | Project | Start | Explanation |
| --- | --- | --- | --- |
| SFMTA | Contract 65 New Traffic Signals | 2022-10 | none written |
| SFMTA | Sutter Street Safety Project | 2025-11 | none written |
| SFMTA | Powell Street Light Safety Project | 2025-03 | none written |
| Public Works | Folsom Howard Streetscape Sewer Replacement | 2024-03-11 | none written |
| Public Works | Joint - Streetscape Lead - Folsom St 10032072 | 2024-05 | none written |
| SFPUC | San Bruno Avenue & Blanken Avenue Water Main Replacement Project | 2025-06 | none written |
| SFPUC | West SoMa, Panhandle and Inner Sunset Large Sewer Improvements Project | 2025-10 | none written |
| SFMTA | Western Addition Traffic Signal Upgrades Phase 1 | 2022-10 | none written |
| SFPUC | PEFWS Pipeline - 36- & 42-inch Welded Steel Pipe | 2024-04-01 | none written |
| SFMTA | Jackson Square Parking and Traffic Improvements | 2026 | none written |
| SFMTA | Sunset Neighborways | 2025 | none written |
| Public Works | PW - M & J Lines - Muni Forward Project | 2023-12-27 | none written |
| SFPUC | FASIP - Western SOMA and Northern Mission District Sewer System | 2026-02-01 | none written |
| SFPUC | WD-2923 (formerly WD-2764): 24-inch Water Main Rehabilitation from University Mound Reservoir to 3rd St | 2024-12-16 | none written |
| SFMTA | Brotherhood/Alemany Safety Improvements Project | 2023-02-01 | none written |
| SFMTA | Innes Avenue Quick-Build Project | 2026-09-01 | none written |
| SFMTA | J Church and M Ocean View Transit and Safety Improvements | 2024 | none written |
| SFPUC | PEFWS Pipeline Contract B - 36-inch Welded Steel Pipe | 2024-04-01 | none written |
| SFMTA | Geary Boulevard Improvement Project | 2023-10 | none written |
| Public Works | Howard Streetscape Project | 2026-07 | none written |
| SFMTA | 29 Sunset Improvement Project – Phase Two | 2026 | none written |
| SFMTA | Howard Street Implementation | 2026 | none written |
| SFPUC | PEFWS Pipeline Contract E - 24-inch GGP Crossing | 2026-01-01 | none written |
| SFPUC | WD-2922: 8-inch Ductile Iron Water Main Replacement on Lincoln Way and Irving St from Sunset Blvd to 19th Ave and Various Side Streets | 2026-08-07 | none written |
| SFMTA | 12th Avenue Slow Street | 2021 | none written |
| SFMTA | 23rd Avenue Slow Street | 2021 | none written |
| SFMTA | 3rd Street Transit and Safety Project | 2019 | none written |
| Public Works | Alemany Boulevard Infrastructure Improvements Project | 2019-06 | none written |
| SFMTA | Arguello Safety Project | 2024-10 | none written |
| SFMTA | Arlington Slow Street | 2021 | none written |
| SFMTA | Clay Slow Street | 2021 | none written |
| SFMTA | Golden Gate Avenue Slow Street | 2020-06 | none written |
| SFMTA | Hearst Avenue Slow Street | 2021 | none written |
| SFMTA | Lombard Street Vision Zero Project | 2016-07 | none written |
| SFMTA | San Bruno Ave Multimodal Improvement Project | 2019 | none written |
| SFMTA | SoMa Slow Streets | 2021 | none written |
| SFMTA | Somerset Slow Street | 2021 | none written |
| SFMTA | Visitacion Valley and Portola Proactive Traffic Calming Project | 2023-04 | none written |
| SFMTA | Bosworth/Monterey Connections Quick-Build Project | 2027-01 | none written |
| SFMTA | Fillmore Street Transit and Safety Project | 2027-04 | none written |
| SFMTA | Tenderloin Traffic Signal Upgrades | 2027-04 | none written |
| Public Works | Western SOMA and Northern Mission Districts Sewer Replacement WW-719D | 2027-06-27 | none written |
| SFMTA | Cesar Chavez Bikeway Improvements Project | 2027 | none written |
| SFMTA | Church and Market Street Intersection Improvements | 2027 | none written |
| SFMTA | Jefferson Street Quick-Build Project | 2027 | none written |
| SFPUC | PEFWS Pipeline Contract F- 24-Inch Water | 2028-01-01 | none written |
| SFMTA | California Street Transit and Safety Project | 2028-01 | none written |
| SFPUC | PEFWS Pipeline Contract G - 36-Inch Water | 2028-10-01 | none written |
| SFMTA | N Judah Transit & Safety Project | 2028 | none written |
| SFPUC | PEFWS Pipeline Contract C - 24-inch 42nd (between Lawton & Irving) | 2029-01-01 | none written |
| Public Works | Ocean Beach Climate Adaptation Project | 2029 | none written |


## D1. Missing, impossible, inconsistent dates

**FAIL.** Measured 4 of 252 listed rows: 0 end before start, 17 past end still listed (17 the department still lists active, 4 of them without the passed end shown; 0 it does not list active), 0 of 53 phase-date conflicts not shown.

Pass line: Zero end-before-start. Zero past-end rows on a “current” list, apart from work the department still lists as active, on its page, its project layer or the coordination feed, which stays listed with its passed end date shown. Every phase-date conflict shown on the page.

| Check | Count |
| --- | --- |
| Missing start | 20 |
| Missing end | 36 |
| End before start | 0 |
| End already passed, still listed; the department still lists it active | 17 |
| … of those, the page does not show the passed end date | 4 |
| End already passed, still listed; the department does not list it active | 0 |
| Phase Planning or Design with start passed | 53 |
| … of those, not shown as a conflict on the page | 0 |
| A date more than eight years out (after 2034-10-01) | 7 |
| Start after 2032 (the first run's cut) | 7 |
| City-body record dated in the future | 0 |
| Project-page item dated in the future | 24 |
| Undated records, of 2216 | 15 |

17 rows are past their published end while their department still lists them active. They stay listed, and pass when the page shows the passed end date (Bryan, 2026-09-29).

| Past end, department still lists active | Department | End | Department's status |
| --- | --- | --- | --- |
| Better Market Street | SFMTA | 2025-04-30 | SFMTA layer: Current |
| 6th Street Pedestrian Safety Project | SFMTA | 2025-08-31 | SFMTA layer: Current; SFMTA page Project Status: Current |
| Contract 65 New Traffic Signals | SFMTA | 2025-11-30 | SFMTA layer: Legislated; SFMTA page Project Status: Implementation / Construction |
| M Ocean View Transit and Safety Project | SFMTA | 2025-11-30 | SFMTA page: Quick-Build Implementation and Detailed Design |
| Noe Slow Street and Duboce Triangle Planning Study | SFMTA | 2025-11-30 | SFMTA layer: Planning; SFMTA page Project Status: Planning |
| Powell Street Promenade Refresh | SFMTA | 2025-12-31 | SFMTA layer: Detailed Design; SFMTA page: Detailed Design |
| Sloat Blvd Quick-Build Project | SFMTA | 2025-12-31 | SFMTA layer: Detailed Design; SFMTA page Project Status: Legislated |
| Sutter Street Safety Project | SFMTA | 2025-12-31 | SFMTA layer: Planning; SFMTA page: Planning |
| Bay Corridor Transmission and Distribution Phase 4 and Water Improvements | SFPUC | 2026-02-28 | SFPUC page Project Phase: Construction |
| Powell Street Light Safety Project | SFMTA | 2026-03-31 | SFMTA page Project Status: Implementation / Construction |
| Mission / Geneva Safety Project | SFMTA | 2026-04-30 | SFMTA layer: Legislated; SFMTA page: Construction |
| Contract 36 Traffic Signal Modifications | SFMTA | 2026-05-31 | SFMTA layer: Implementation / Construction; SFMTA page Project Status: Implementation / Construction |
| Mission Bay Blvd Quick-Build Project | SFMTA | 2026-08-31 | SFMTA layer: Implementation / Construction; SFMTA page Project Status: Implementation / Construction |
| PW Various Locations Sewer Replacement (JV VL PR No 62) | Public Works | 2026-09-30 | feed row 8092 status: Active; feed row 8092 phase: Construction; Public Works page: In progress |
| Various Locations Pavement Renovation No 68 | Public Works | 2026-09-30 | feed row 31562 status: Active; feed row 31562 phase: Construction; Public Works page: In progress |
| Winston Drive Quick-Build Project | SFMTA | 2026-09-30 | SFMTA layer: Implementation / Construction; SFMTA page Project Status: Implementation / Construction |
| Visitacion Valley and Portola Community Based Transportation Plan | SFMTA | 2023-05-31 | SFMTA layer: Planning; SFMTA page Project Status: Planning |

| Phase-date conflict not shown | Phase | Start |
| --- | --- | --- |

| More than eight years out | Start | End |
| --- | --- | --- |
| 16th St, 17th St, and 18th St Pavement Renovation | 2033-08-30 | 2034-11-13 |
| Various Locations Pavement Renovation No 104 | 2033-09-30 | 2034-12-14 |
| Various Locations Pavement Renovation No 105 | 2033-10-28 | 2035-01-11 |
| Various Locations Pavement Renovation Under Overhead Contact System No 3 | 2034-01-28 | 2035-04-13 |
| Various Locations Pavement Renovation Concrete No 97 | 2034-02-28 | 2035-05-14 |
| Brotherhood Way Pavement Renovation | 2034-07-19 | 2035-10-01 |
| Various Locations Pavement Renovation Under Overhead Contact System No 4 | 2035-02-02 | 2036-04-16 |


## D2. Dates are right (hand-graded)

**FAIL.** Measured construction end 91.3%, construction start 95.7%, consultation end 94.6%, consultation start 97.3%, other dates 100.0% of 313 graded of 313 dates on 75 listed projects.

Pass line: Over 95% correct on each of construction start, construction end, public consultation start and end, and over 95% on all other dates shown, over a random sample of at least 60 listed projects. The share is of dates a department page states; rows marked 'no page' or 'not on page' are left out.

Sampled projects no longer listed, left out with their rows: 6 (Frida Kahlo Way Quick-Build Project, Lake Slow Street, Shotwell Slow Street, Shotwell/Capp Neighborway Project, Slow Streets, Third Street Bridge Rehabilitation Project).
Sampled projects with no department page to grade against (the date can only be checked against the row it was read from): Public Works 31 of 42, SFMTA 2 of 26, SFPUC 5 of 7.

| Field | Correct | Graded | Share |
| --- | --- | --- | --- |
| construction end | 21 | 23 | 91.3% |
| construction start | 22 | 23 | 95.7% |
| consultation end | 35 | 37 | 94.6% |
| consultation start | 36 | 37 | 97.3% |
| other dates | 43 | 43 | 100.0% |

Left out of the shares: 142 no page, 8 not on page (`no page`: the department publishes no page for the project; `not on page`: its page gives no date for that milestone, so the shown date came from a feed row).

## E1. Valid shapes

**PASS.** Measured 0 of 23980 features in 5 drawn files.

Pass line: Zero empty, zero-length, self-intersecting or out-of-city shapes in files the site draws.

Outside SF means a vertex outside -122.53 to -122.35, 37.7 to 37.835. Zero-length is under 1 m (3 ft). Lines over 400 segments are not tested for self-intersection.

| File | Features | empty | outside SF | zero-length | self-intersecting | Examples |
| --- | --- | --- | --- | --- | --- | --- |
| site/data/north-star/traced.geojson (plan) | 3077 | 0 | 0 | 0 | 0 |  |
| site/data/bike-history/segments.json (bikeway layer) | 3061 | 0 | 0 | 0 | 0 |  |
| site/data/bike-history/all-ages.geojson | 1230 | 0 | 0 | 0 | 0 |  |
| site/data/sf-streets.json (base map) | 16372 | 0 | 0 | 0 | 0 |  |
| site/data/coordination.json project geometry | 240 | 0 | 0 | 0 | 0 |  |
| out/sfmta-projects/projects.geojson (raw layer, not drawn) | 461 | 0 | 0 | 5 | 6 |  |


## E2. Lines up with the street grid

**PASS.** Measured 0 over 15 m (50 ft); 186 drawn features carry no CNN of 7182 keyed features in 3 drawn files (7368 drawn; the 186 with no CNN cannot be tested and are not in the denominator).

Pass line: Zero segments more than 15 m (50 ft) from their CNN's centerline in files the site draws.

Centerline: DataSF 3psu-pn9h, cache fetched 2026-09-29. The distance is the largest from any vertex to the CNN's centerline.
186 drawn features carry no CNN. They draw on the map but join to no plan block and no reach figure, so the pass line cannot test them; they are listed below rather than counted as aligned.

| File | Features | Keyed | No CNN | Over 15 m (50 ft) | Over 100 m (330 ft) | Retired CNN | CNN not in centerline |
| --- | --- | --- | --- | --- | --- | --- | --- |
| site/data/north-star/traced.geojson (plan) | 3077 | 3077 | 0 | 0 | 0 | 0 | 0 |
| site/data/bike-history/segments.json (bikeway layer) | 3061 | 2965 | 96 | 0 | 0 | 0 | 0 |
| site/data/bike-history/all-ages.geojson | 1230 | 1140 | 90 | 0 | 0 | 0 | 0 |

| File | Feature | Largest distance |
| --- | --- | --- |

| File | Drawn feature with no CNN |
| --- | --- |
| site/data/bike-history/segments.json | P:-122.50399,37.71688\|-122.50256,37.71871 |
| site/data/bike-history/segments.json | P:-122.44896,37.77167\|-122.44909,37.77220 |
| site/data/bike-history/segments.json | P:-122.44896,37.77227\|-122.44092,37.77363 |
| site/data/bike-history/segments.json | P:-122.49317,37.76708\|-122.49333,37.76473 |
| site/data/bike-history/segments.json | P:-122.50275,37.72079\|-122.50149,37.71954 |
| site/data/bike-history/segments.json | P:-122.50183,37.76773\|-122.47998,37.77034 |
| site/data/bike-history/segments.json | P:-122.50880,37.78243\|-122.50769,37.78263 |
| site/data/bike-history/segments.json | P:-122.50010,37.71808\|-122.50149,37.71954 |
| site/data/bike-history/segments.json | P:-122.42657,37.80803\|-122.42074,37.80760 |
| site/data/bike-history/segments.json | P:-122.50270,37.70797\|-122.50229,37.71177 |
| site/data/bike-history/segments.json | P:-122.42963,37.80675\|-122.43605,37.80656 |
| site/data/bike-history/segments.json | P:-122.47744,37.73736\|-122.47566,37.73462 |
| site/data/bike-history/segments.json | P:-122.50133,37.76605\|-122.50317,37.76530 |
| site/data/bike-history/segments.json | P:-122.45373,37.77010\|-122.45555,37.77046 |
| site/data/bike-history/segments.json | P:-122.51093,37.78270\|-122.50948,37.78341 |
| site/data/bike-history/segments.json | P:-122.49268,37.76917\|-122.49390,37.77023 |
| site/data/bike-history/segments.json | P:-122.49972,37.78611\|-122.50203,37.78703 |
| site/data/bike-history/segments.json | P:-122.51188,37.78251\|-122.50988,37.78063 |
| site/data/bike-history/segments.json | P:-122.47826,37.76592\|-122.47832,37.76540 |
| site/data/bike-history/segments.json | P:-122.50256,37.71871\|-122.50235,37.72055 |
| site/data/bike-history/segments.json | P:-122.44733,37.77189\|-122.44738,37.77262 |
| site/data/bike-history/segments.json | P:-122.44901,37.77224\|-122.44896,37.77227 |
| site/data/bike-history/segments.json | P:-122.45398,37.77143\|-122.44901,37.77224 |
| site/data/bike-history/segments.json | P:-122.43605,37.80656\|-122.43748,37.80653 |
| site/data/bike-history/segments.json | P:-122.47166,37.77314\|-122.47386,37.77123 |
| site/data/bike-history/segments.json | P:-122.50338,37.71285\|-122.50266,37.71287 |
| site/data/bike-history/segments.json | P:-122.50229,37.71177\|-122.50423,37.71710 |
| site/data/bike-history/segments.json | P:-122.50275,37.72079\|-122.50763,37.72809 |
| site/data/bike-history/segments.json | P:-122.50523,37.78652\|-122.51174,37.78076 |
| site/data/bike-history/segments.json | P:-122.50354,37.71871\|-122.50367,37.72118 |
| site/data/bike-history/segments.json | P:-122.48098,37.77271\|-122.47999,37.77033 |
| site/data/bike-history/segments.json | P:-122.49948,37.71249\|-122.50260,37.71261 |
| site/data/bike-history/segments.json | P:-122.50797,37.78339\|-122.50771,37.78277 |
| site/data/bike-history/segments.json | P:-122.49140,37.76953\|-122.49141,37.76953 |
| site/data/bike-history/segments.json | P:-122.43748,37.80653\|-122.44735,37.80523 |
| site/data/bike-history/segments.json | P:-122.46216,37.76611\|-122.46224,37.76689 |
| site/data/bike-history/segments.json | P:-122.47291,37.80730\|-122.46996,37.80584 |
| site/data/bike-history/segments.json | P:-122.47529,37.80813\|-122.47517,37.80823 |
| site/data/bike-history/segments.json | P:-122.47291,37.80730\|-122.47239,37.80690 |
| site/data/bike-history/segments.json | P:-122.47636,37.80833\|-122.47531,37.80842 |

146 more rows not shown.

Cross streets of the 144 re-keyed bikeway rows, no geometry used: 66 match the new blocks, 27 match on one of two, 29 match only the typed block, 19 match neither, 3 have none. Contradictions (street name and both cross streets describe the typed active block the row was moved off): 0.
Split blocks: 95 distinct CNNs across all 951 project records are not plan blocks but share a base number with one (e.g. 300000 against plan blocks 300001–300003). 71 are held by listed projects, and for 21 of those the project does not also hold the plan block, so that block drops out of its plan miles.

## E3. The map shows the whole project

**PASS.** Measured 14047 of 14047 blocks drawn (100.0%); 0 maps under half, 0 short of any block of 252 project maps.

Pass line: Every block held is drawn, on every project.

0 of 252 maps draw fewer than half their blocks. A block is drawn when the project's geometry carries a line for it, and an intersection when it carries a point.

| Project | Drawn | Held | Share |
| --- | --- | --- | --- |


## F1. Units

**FAIL.** Measured 0 metric units; 1 mile basis (per direction); 0 of 656 mi figures on pages whose file disagrees with the layer and the map; 0 blocks or projects off of 1066 rendered pages.

Pass line: Zero metric units shown. One mile basis across every page and chart, and the About page says which.

Every file a page takes miles from is measured, block for block, against the bikeway layer's own row lengths (data/extract/sfmta-bikeway/, measured here) and the street centerline where the layer has no row. Plan blocks are measured from SFMTA's North Star map PDF itself: its drawn lines, fitted here to today's street centerline (6.2 m median registration error), projected onto every block they run along within 20 m. A block is the plan's when the drawn line spans half of it and runs along half its length, and it counts the part the line spans, reaching an end within 20 m. The trace the pipeline uses is not read. A tolerance of 1% or 2 m per block, plus 40 m of block where the two measures place the line's end; two significant figures per project. Every “N mi” on a rendered page takes the verdict of its page's file. About the data explains the basis, so its own figures are not counted.
Map PDF read here: sha256 6f9f65ce4888…; the same file the pipeline's trace read.
The plan's own definition of its network: Appendix L says “The following is an index of roadway segments that appear on the North Star map (pages 68–69). If discrepancies between this index and the map occur, defer to the map.” (still printed in the appendix read here, sha256 b64a5a26347c…). So which blocks are the plan's is decided by the map. Appendix L is read here from the appendix PDF (393 rows, 332 placed on the centerline by this audit's own walk, 61 not placed), and a block it names with a facility counts where the map draws a line along it within 40 m (131 ft) instead of 20 m, since the hand-drawn line sits off some named streets: 159 of the 3077 plan blocks here come in that way. Of the 2450 blocks Appendix L names with a facility, the map draws 2363; the other 87 are left out, as the plan says.

| What | File | Compared | Disagree | Note |
| --- | --- | --- | --- | --- |
| Overview | history.json, components.json | 2850 | 0 | 473.3 mi in 2026; the layer's rows measure 472.6 mi (the rest is work SFMTA's project pages report built) |
| Plan blocks, how much of each | north-star/status.json | 3077 | 0 | the map's line stops partway along 72 blocks |
| Plan blocks the map does not draw | north-star/status.json | 3077 | 0 |  |
| Blocks the map draws that status.json lacks | north-star/status.json | 3077 | 0 |  |
| Plan network, in all | north-star/status.json | 3077 blocks | -0.1 mi | status.json 457.1 mi; the map measures 457.2 mi on 3077 blocks |
| Repave lever | repave-lever.json | 155 | 0 | repaved plan blocks since adoption |
| Current Projects | coordination.json planMiles | 235 | 0 | projects with plan blocks |

| Basis in use | mi figures |
| --- | --- |
| per direction | 656 |

About the data states the basis: no; says a block counts only its part where the plan's line stops partway: no. 3 CNN-less path rows were placed on a block by their ends.

| Better Coordination: block or project | Shown | Measured from the layer and the map |
| --- | --- | --- |

| Overview: block or project | Shown | Measured from the layer and the map |
| --- | --- | --- |


## F2. Denominators

**PASS.** Measured 2 of resident totals used as a denominator, found on 1066 rendered pages.

Pass line: One resident total, or each one labelled with its source where it is used.

Each resident total is summed here from the census extracts (data/extract/census-blocks/), and every place a rendered transportation page prints one, About the data included, must name that total's source in the same sentence.

| Total | Source (summed from the extract) | Printed | Labelled |
| --- | --- | --- | --- |
| 830,235 | 2020–2024 American Community Survey | 1 | 1 |
| counts of residents reached | 2020 census blocks | 155 | 155 |


## F3. Freshness

**PASS.** Measured 0 of 35 source dates and 0 typed “as of” phrases.

Pass line: Every source within its horizon (90 days for a live dataset, 180 for a document), and no hard-coded “as of” text that disagrees with the data.

| Source | Kind | Read | Last checked | Days old | Horizon | Result |
| --- | --- | --- | --- | --- | --- | --- |
| data/extract/bikeway-snapshots/20210325.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/bikeway-snapshots/20221209.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/bikeway-snapshots/20240331.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/bikeway-snapshots/20251208.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/bikeway-snapshots/20260215.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/bikeway-snapshots/20260405.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| data/extract/schools/cde-sf.json | dataset | 2026-09-22 | — | 9 | 90 | ok |
| Coordination feed btxj-k9uh | dataset | 2026-09-28 | 2026-09-29 | 2 | 90 | ok |
| Reach: schools | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| Reach: libraries | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| Reach: blocks | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| Bikeway layer (reach network) | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-acs/b08301-sf.json | dataset | 2026-09-24 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-blocks/2010.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-blocks/2020.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-blocks/acs5-bg.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-blocks/outlines-2010.json | dataset | 2026-09-29 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-blocks/outlines-2020.json | dataset | 2026-09-29 | 2026-09-29 | 2 | 90 | ok |
| data/extract/census-dhc/p12-blocks.json | dataset | 2026-09-29 | — | 2 | 90 | ok |
| data/extract/dpw-projects/projects.json | document | 2026-09-28 | 2026-09-29 | 2 | 180 | ok |
| data/extract/libraries/branches.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/sfmta-bci/scores.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/sfmta-bikeway/geometry.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/sfmta-bikeway/network.json | dataset | 2026-09-22 | 2026-09-29 | 2 | 90 | ok |
| data/extract/sfmta-board/since-2019-01-01.json | document | 2026-09-29 | 2026-09-29 | 2 | 180 | ok |
| data/extract/sfmta-hearings/since-2010-01-01.json | document | 2026-09-29 | 2026-09-29 | 2 | 180 | ok |
| data/extract/sfmta-pages/all.json | document | 2026-09-24 | 2026-09-29 | 2 | 180 | ok |
| data/extract/sfmta-pages/bike.json | document | 2026-09-28 | 2026-09-29 | 2 | 180 | ok |
| data/extract/sfpuc-commission/minutes.json | document | 2026-09-22 | 2026-09-29 | 2 | 180 | ok |
| data/extract/slow-streets/segments.json | dataset | 2026-09-28 | 2026-09-29 | 2 | 90 | ok |
| Centerline 3psu-pn9h (full pull) | dataset | 2026-09-29 | 2026-09-29 | 2 | 90 | ok |
| data/extract/sfmta-pages/sitemap.json | document | 2026-09-30 | 2026-09-29 | 1 | 180 | ok |
| transportation.json collector | dataset | 2026-09-30 | 2026-10-01 | 0 | 90 | ok |
| data/extract/ej-communities/blocks.json | dataset | 2026-10-01 | — | 0 | 90 | ok |
| data/extract/ej-communities/polygons.json | dataset | 2026-10-01 | — | 0 | 90 | ok |

Newer release not adopted: release:cde-schools — a CDE schools capture dated 20260122 is newer than the 2025-10-05 file in use

| Content file | Typed text | Says | Data says | Result |
| --- | --- | --- | --- | --- |

The publisher's own last-updated dates were not read (run --refresh).

## F4. Traceability

**FAIL.** Measured 3 typed figures the data could supply or unclassified; 2 of 17 traces fail; 2 of 3 headline figures untraced of 4 typed figures in 4 content files; 3 headline figures on the section pages.

Pass line: Every headline figure reaches a source row. Zero typed figures that the data could supply.

A typed figure is classified in data/audit/typed-figures.csv (file, figure, a few words of its context, verdict, note) as external (a quote of a source the data does not hold) or data (the data could supply it). Only external passes; an unclassified figure fails until someone classifies it.

| Traced figure | Page shows | Data says | Result |
| --- | --- | --- | --- |
| Current Projects count | 252 | counts.listed 252; 156 feed jobs + 87 layer projects + 5 Public Works pages + 4 SFPUC pages | reaches |
| Current Projects: Repaving | 54 | 54 list rows of kind 'repaving'; 54 coordination.json rows, 54 naming their source; counts.byKind 54 | reaches |
| Current Projects: Sewer, water or power | 82 | 82 list rows of kind 'sewer, water and power'; 82 coordination.json rows, 82 naming their source; counts.byKind 82 | reaches |
| Current Projects: Streetscape | 18 | 18 list rows of kind 'streetscape and safety'; 18 coordination.json rows, 18 naming their source; counts.byKind 18 | reaches |
| Current Projects: Bike, walk or safety | 87 | 87 list rows of kind 'SFMTA bike and safety'; 87 coordination.json rows, 87 naming their source; counts.byKind 87 | reaches |
| Current Projects: Transit or parking | 2 | 2 list rows of kind 'SFMTA transit and parking'; 2 coordination.json rows, 2 naming their source; counts.byKind 2 | reaches |
| Current Projects: Spot repairs | 9 | 9 list rows of kind 'spot repairs'; 9 coordination.json rows, 9 naming their source; counts.byKind 9 | reaches |
| Current Projects: Builds 100% of the missing plan bikeway | 2 | 2 list rows in category 'all'; 2 coordination.json rows | reaches |
| Current Projects: Builds 50 to 99% | 12 | 12 list rows in category 'most'; 12 coordination.json rows | reaches |
| Current Projects: Builds 1 to 49% | 11 | 11 list rows in category 'some'; 11 coordination.json rows | reaches |
| Current Projects: Builds 0%, or 0% in published scope | 149 | 149 list rows in category 'none'; 149 coordination.json rows | reaches |
| Current Projects: Not stated | 38 | 38 list rows in category 'not-stated'; 38 coordination.json rows | reaches |
| Current Projects: Plan bikeway already built | 23 | 23 list rows in category 'already-built'; 23 coordination.json rows | reaches |
| Current Projects: No known overlap with the plan | 17 | 17 list rows in category 'no-overlap'; 17 coordination.json rows | reaches |
| About: feed jobs | 388 | feed.jobs 388 | reaches |
| Overview: share of residents within a quarter mile, first year | not found | 63% (history.json 2015 resident_share) | FAILS |
| Overview: share of residents within a quarter mile, latest year | not found | 81% (history.json 2026 resident_share) | FAILS |

| Content file | Typed figure | Verdict | Note or context |
| --- | --- | --- | --- |
| transportation-about.md | 472 miles | UNCLASSIFIED | Miles and the All-Ages Test {#definitions} The plan counts 472 miles of network ([p. 20]), and the b |
| transportation-about.md | 2020 Blocks | UNCLASSIFIED | ents, schools and libraries in that area"] dn1[("• Census 2020 Blocks • CDE School Directory • DataS |
| transportation-about.md | 90% | external | a percentile the method names (p90); the measured figure beside it is filled from data |
| transportation-about.md | 0% | UNCLASSIFIED | el. We check built SFMTA work against the [bikeway layer]. "0% in published scope" means the scope n |

A headline figure is a number between a section page's h1 and its first subheading, list, table or chart, years and dates left out. One with no trace in f4_traces fails until a trace is written for it.

| Page | Headline figure | Context |
| --- | --- | --- |
| transportation/bike/index.html | 63% | , then in the last decade, the city has gone from 63% of residents connected to the all ages and abilit |
| transportation/bike/index.html | 81% | he all ages and abilities bike network in 2015 to 81% in 2026: |


## F5. Clean text

**PASS.** Measured 0 of names and titles in site/data and on the rendered pages.

Pass line: Zero `?` in place of dashes, `â€`, `Ã` or U+FFFD in shown names and titles.

| Where | Text |
| --- | --- |

Upstream, not shown today: 2.

| File | Text |
| --- | --- |
| out/sfmta-board/meetings.json | RESCIND ? CLASS II BIKEWAY |
| out/sfmta-board/meetings.json | ESTABLISH ? CLASS IV BIKEWAY (TWO-WAY) |


## S1. Stable project addresses

**PASS.** Measured 0 of 526 addresses published at HEAD, 526 in the registry (252 listed, 204 redirect, 70 notice).

Pass line: Every project address published at HEAD still answers: it is in data/project-ids.json, points at the same project or names the old id in formerIds, and the site builds a page or a redirect for it.

| Slug | Project | Problem |
| --- | --- | --- |


## How to read and extend this

- `scripts/transportation-audit.py --explain` prints, under each check that does not pass, the rows that count against its pass line; `results.json` carries the same rows under `failing`.
- Hand grades: `data/audit/grades/d2-dates.csv` and `c3-links.csv`. Column meanings in `data/audit/README.md`.
- Explanations for “every miss explained”: `data/audit/explanations.csv` (check, key, explanation).
- Typed-figure verdicts for F4: `data/audit/typed-figures.csv` (file, figure, verdict external or data, note).
- Network caches: `data/audit/cache/`; `--refresh` re-fetches SFMTA's sitemap, every department link's status and DataSF metadata.
- A new body's mirror flips its C1 row by writing `out/<slug>/coverage.json`.
