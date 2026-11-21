# Transportation data quality audit, 2026-09-28

Current results are in the generated [audit report](../../out/transportation-audit/report.md). This note is the hand-run baseline; the files it measured have since been regenerated.

On 2026-09-28, before the fixes in fixes.md, the Current Projects list missed active SFMTA projects on plan streets: 25 of the 29 active SFMTA projects on plan blocks that SFMTA does not tag Bike were absent. Dates on the list were wrong on 48 of the 159 we could check against a department's own page, about three in ten; those 159 sit on 35 projects, mostly SFMTA's. "No city decision found" did not mean none was made: only 2 of 43 major projects had three or more city-body records, and the Public Works Commission, SFCTA and Rec and Park Commission were not read at all.

This is the first run of [pipeline/transportation-data-audit-criteria.md](../../pipeline/transportation-data-audit-criteria.md) against the data behind the biking pages. Everything below was measured on 2026-09-28 from the files named, unless it is marked `[inference — mine]` (a reading of the numbers).

The main files are:

- [`site/data/coordination.json`](../../site/data/coordination.json): Current Projects, 194 rows, generated 2026-09-28.
- [`out/project-record/projects.json`](../../out/project-record/projects.json): 613 project records with linked documents.
- `data/extract/*`: the dated source extracts.
- The rendered pages in `site/dist/transportation/`, built 2026-09-28 19:16 and read, not rebuilt.

Terms: **plan blocks** are the street blocks on the Biking and Rolling Plan's network; a **CNN** is the city's id for one street block; the **feed** is DataSF's [street-work coordination dataset](https://data.sfgov.org/d/btxj-k9uh); a **layer** is one of SFMTA's ArcGIS maps, of projects or of bikeways; **exact**, **strong** and **probable** are the grades our matcher gives a record's link to a project, strongest first; **Current Projects** and **Better Coordination** are two of the site's transportation pages; **reach** is the residents within a straight-line quarter mile of a project's lines who are not already that close to today's all-ages network.

## Results

| Criterion                              | Result       | Measured                                                     |
| -------------------------------------- | ------------ | ------------------------------------------------------------ |
| A1 Completeness: SFMTA                 | **fail**     | SFMTA publishes 417 project pages. Its project layer carries 224, and our list holds 41. Missing: 25 of 29 active projects that run on plan blocks but are not tagged Bike, and 23 Bike-tagged projects dropped for having no phase (21 of them on plan blocks). |
| A1 Completeness: Public Works          | **fail**     | 104 Public Works pages say "In progress". Only 38 of them carry block data, and 29 of those touch plan blocks. 9 of the 29 (31%, against a 5% line) cover 12–25 plan blocks each that no listed project covers. |
| A1 Completeness: SFPUC                 | not measured | We read no SFPUC project list. The coordination feed is the only source (24 listed). |
| A2 Other agencies                      | **fail**     | 9 active feed jobs on plan blocks from PG&E (5), Transbay DTX (2), the Port (1) and SF Bay Ferry (1) are dropped. The site does not mention them. |
| A3 Duplicates                          | **fail**     | 1 name listed twice. 9 pairs share 50% or more of their blocks; the Folsom streetscape work is 4 rows. 3 same-project pairs across sources are not merged. |
| B1 Link to department page             | **fail**     | Public Works: 0 of 129 link a Public Works page. SFPUC: 0 of 24. SFMTA: 29 of 41. 7 of the other 12 have an SFMTA page under nearly the same name. |
| B2 Key fields                          | not measured | Start is present on 187 of 194 (96%). Phase coverage, and whether each missing value shows as "not published", were not counted. End missing on 21 of 194. Scope published on feed rows only. 2 projects have no map geometry. |
| B3 Status across sources               | **fail**     | 6 of 17 projects both SFMTA and Public Works publish disagree on status. Neither page shows the other's status. |
| C1 Source coverage                     | **fail**     | Hearings read from 2019-08, with 23 of 144 hearings unread (12 of them in 2023). Board: bike-keyword items only, with outcomes only from 2022-11. Board of Supervisors: 24 search terms, titles only. Public Works Commission, SFCTA and Rec and Park are not read. |
| C2 Mentions per major project          | **fail**     | 2 of 43 major projects have 3 or more dated city-body records. For SFMTA's 14 major projects, it is 0. 23 of 41 SFMTA projects have none. |
| C3 Matching accuracy and labels        | **fail**     | 156 of 213 items under "City decisions naming this project" come from the project's own page, not a city body. 25 of those are open houses or events labelled "SFMTA Board". Contract awards that name the job's contract number are missed (3 found). |
| C3c Link sample, hand-checked          | **fail**     | 22 of 40 sampled city-body links are about their project and carry the right label. |
| C4 A record before work starts         | not measured | Not run in this audit.                                       |
| D1 Dates                               | **fail**     | 2 rows ended before today but still show as current (Better Market Street, Apr 2025). 44 rows show phase Planning or Design with a start date already past. 0 end-before-start. 0 city-body records are dated in the future; 6 project-page items are. |
| D2 Dates against the department's page | **fail**     | Correct, of 159 graded dates: construction start 20 of 26, construction end 15 of 27, consultation start 19 of 30, consultation end 19 of 30, other dates 38 of 46. The pass line is over 95% on each. |
| E1 Valid shapes                        | **fail**     | 2 empty project shapes in `coordination.json`, which the site draws. 0 empty, out-of-city, zero-length or self-intersecting shapes in the plan, bikeway and all-ages files. The raw SFMTA project layer has 6 self-intersecting and 5 zero-length shapes, which are not drawn. |
| E2 Street-grid alignment               | **fail**     | 51 of 3,017 bikeway segments sit more than 50 ft (15 m) from their CNN's centerline, and 21 of them more than 330 ft (100 m), up to 2.3 mi. 21 carry CNNs the centerline has retired. 153 project CNNs miss a plan block split into new CNNs. |
| E3 Map shows the whole project         | **fail**     | 2,257 of 8,414 project blocks drawn (27%). 152 of 194 maps draw fewer than half their blocks. |
| F1 Units                               | **fail**     | 0 metric units on rendered pages. But "mi" means centerline miles on Current Projects and miles per direction on Better Coordination: 47.5 against 78.3 for the same 91 jobs. |
| F2 Denominators                        | **fail**     | Residents: 830,235 (ACS) on the overview map, 873,965 (2020 census) in project reach. Neither is labelled. |
| F3 Freshness                           | **fail**     | A typed "as of" disagrees with the data: the overview's "updated only through December 2025" against the layer's own last edit, 2026-05-21. All sources were queried between 2026-09-04 and 2026-09-28, inside the 90- and 180-day horizons. |
| F4 Traceability                        | **fail**     | 3 of 3 traced figures reach a source row. 3 figures are typed into prose rather than filled from data. |
| F5 Clean text                          | **pass**     | 0 in shown names and titles. Upstream, not shown: 2 in `out/sfmta-board/meetings.json`, and 1 SFMTA project name with `â€“`. |

## A1. Completeness per department

**SFMTA.** SFMTA's [sitemap](https://www.sfmta.com/sitemap.xml) lists 417 `/projects/` pages (`data/extract/sfmta-pages/sitemap.json`, fetched 2026-09-28). The live [ArcGIS project layer](https://www.sfmta.com/projects) carries 224 projects, and 221 of the sitemap pages are on it. We start from the layer. [`tools/projects/coordination-projects.py`](../../tools/projects/coordination-projects.py) keeps only layer projects tagged Bike with a phase other than Completed, Project Evaluation or test. Three rules lose projects:

- **Not tagged Bike.** 67 layer projects are active and not tagged Bike. [`tools/projects/project-blocks.py`](../../tools/projects/project-blocks.py) computes no blocks for any of them: all 102 non-Bike projects have an empty `cnns`. So the plan test never runs on them. Checking their published lines against the plan network by hand, at 66 ft tolerance, 29 of the 67 run on plan blocks. Four reach the list anyway as feed rows under other names (Cayuga, J Church on San Jose Ave, Innes Avenue Quick-Build, Brotherhood-Alemany). The other 25 are absent, including:
  - 3rd Street Transit and Safety Project (Detailed Design)
  - Clarendon Quick-Build (Detailed Design)
  - California Street Transit and Safety Project (Planning)
  - Lombard Street Vision Zero Project (Legislated)
  - Geary Boulevard Improvement Project (Construction)
  - 4th Street Transit Improvement Project (Construction)
  - Transit U Improvement Project (Construction)
  - 29 Sunset Improvement Project Phase Two (Planning)
  - Monterey Boulevard Pedestrian Safety (no phase)
  - Arlington Slow Street (no phase)
- **Tagged Bike, no phase.** 23 are dropped (`counts.sfmtaBikeNoPhase`). 21 are on plan blocks, including Central Embarcadero Safety Project, Active Beale Street, Lincoln and Sloat Quick-Build Connections, 5th Street Improvement Project, Shotwell/Capp Neighborway and 12 Slow Streets. The layer gives no phase, so whether they are active is unknown.
- **Not on the layer at all.** 196 sitemap pages are not on the layer, and 79 of them use bike words. Those with 2025–26 activity: [N Judah Transit & Safety Project](https://www.sfmta.com/projects/n-judah-transit-safety-project), [Lincoln Way New Traffic Signals](https://www.sfmta.com/projects/lincoln-way-new-traffic-signals), [Embarcadero Connectivity Plan](https://www.sfmta.com/projects/embarcadero-connectivity-plan) (a Port and Army Corps project) and [Sunset Neighborways](https://www.sfmta.com/projects/sunset-neighborways), whose page says Kirkham "is expected to begin this month". None of these has layer geometry, so none can be placed on blocks.

`[inference — mine]` SFMTA's Bike tag is a poor filter. It marks the Innes and Cayuga projects as non-bike although their names say Quick-Build and Slow Street. The plan-block test that Public Works jobs get would catch most of the 25. The check: compute blocks for all 224 layer projects and rerun the selection.

**Public Works.** The list takes Public Works jobs from the [coordination feed](https://data.sfgov.org/d/btxj-k9uh) (389 jobs, queried 2026-09-21). Why each feed job is in or out:

| Reason                          | Jobs |
| ------------------------------- | ---- |
| Listed                          | 165  |
| Off the plan with no bike words | 153  |
| Other agency                    | 56   |
| Not street work by name         | 9    |
| Merged into an SFMTA row        | 5    |
| Finished                        | 1    |

Public Works' own [project pages](https://sfpublicworks.org/projects) list 269 projects (`data/extract/dpw-projects/projects.json`, read 2026-09-22), 104 of them "In progress". Only 38 of the 104 carry block data. 29 of those touch plan blocks, and 9 cover plan blocks no listed project covers:

| Public Works page                                            | Plan blocks not on our list |
| ------------------------------------------------------------ | --------------------------- |
| [Junipero Serra Boulevard Pavement Renovation & Sewer Replacement](https://sfpublicworks.org/index%2Ephp/Junipero-Serra) | 25                          |
| [Fulton Street and Grove Street Sewer Replacement and Pavement Renovation](https://sfpublicworks.org/index%2Ephp/Fulton-Grove) | 22                          |
| [Beale Street Improvement Project](https://sfpublicworks.org/index%2Ephp/BealeStreet) | 21                          |
| [Folsom Streetscape/SOMA](https://sfpublicworks.org/index%2Ephp/FolsomSOMA) | 21                          |
| [Transbay Folsom Streetscape](https://sfpublicworks.org/index%2Ephp/Folsom_Transbay) | 21                          |
| [Minna Natoma Streetscape](https://sfpublicworks.org/index%2Ephp/minna-natoma) | 17                          |
| [Alemany Boulevard Infrastructure Improvements](https://sfpublicworks.org/index%2Ephp/Alemany) | 13                          |
| [Alemany Interchange Improvement](https://sfpublicworks.org/index%2Ephp/Alemany-Interchange) | 12                          |
| [Masonic Avenue Streetscape Improvement](https://sfpublicworks.org/index%2Ephp/masonic) | 12                          |

Junipero Serra and Fulton-Grove have no feed job under those names. The two sources disagree: the Public Works page says in progress, and the feed has no such job. `[inference — mine]` Some "In progress" pages are stale: SFMTA's layer calls Masonic Completed (see B3). The other 66 in-progress pages were not checked, because they carry no blocks.

**SFPUC.** Not measured. We fetched no SFPUC project list, so the feed's 24 rows are unchecked against SFPUC's own publication.

## A2. Other agencies

56 feed jobs belong to other agencies (47 of them PG&E) and are dropped before any test. 9 are active and touch plan blocks:

| Agency       | Job                                                          | Plan blocks |
| ------------ | ------------------------------------------------------------ | ----------- |
| SF Bay Ferry | Downtown Ferry Terminal Electrification                      | 15          |
| Transbay     | DTX Downtown Rail Extension                                  | 11          |
| PG&E         | 19th Ave & Lawton St                                         | 7           |
| Port         | Pier 80 Electrification                                      | 4           |
| Transbay     | DTX Mission Bay Dr At Grade Crossing                         | 3           |
| PG&E         | 85 Bluxome St, Taraval & 47th, 24th Ave & Vicente, West Sunset 6 | 2–3 each    |

About the data does not name any of them.

## A3. Duplicates

- **Same name twice:** "Broad Street and Randolph Street Sewer Replacement" is two feed jobs.
- **Block overlap of 50% or more, 9 pairs.** The Folsom work is four rows: "Joint - Streetscape Lead - Folsom St 10032072", "PW Folsom Streetscape Project" (0.93 overlap), "Folsom Howard Streetscape Sewer Replacement" (0.75–0.77), plus SFMTA's "Folsom-Howard Streetscape Project". Two sewer contracts appear under two numbering schemes: "WW-779 … No. 32" beside "… No 32", and "#21" beside "No 21".
- **Not merged across sources.** The merge needs identical normalised names, so three pairs stay separate:
  - "Golden Gate Park Access Project" (feed) and "Golden Gate Park Access and Safety Program" (layer)
  - "Page Slow Street Upgrades" (feed) and "Page Slow Street" (layer)
  - "Cayuga Slow Street Upgrade Project" (feed) and SFMTA's "Cayuga Avenue Slow Street" (not listed)

## B1. Link to the department's page

| Department   | Listed | Link to a department page | Only link                            |
| ------------ | ------ | ------------------------- | ------------------------------------ |
| Public Works | 129    | 0                         | the DataSF JSON row                  |
| SFPUC        | 24     | 0                         | the DataSF JSON row                  |
| SFMTA        | 41     | 29                        | the DataSF JSON row for the other 12 |

SFMTA publishes a page under the same or nearly the same name for at least 7 of those 12: Oak Street Quick-Build, Brotherhood-Alemany Quick-Build, Innes Avenue Quick-Build, J Church (San Jose Ave), Golden Gate Park Access, Cayuga Avenue Slow Street and M Ocean View Transit and Safety.

`scripts/dpw-project-join.py` grades 3 feed jobs "likely same" as a Public Works page. `coordination-projects.py` does not read that file, so none of the three reaches the site. `[inference — mine]` Two of the three are wrong by name: "3rd St from Mariposa St to Palou Ave Pavement Renovation" is paired with the Bayview library page, and "Chinatown and SOMA Large Diameter Sewer Improvements" with Mid-Market SoMa Alleyways Phase 2.

## B2. Key fields

| Field                                       | Missing                                                      |
| ------------------------------------------- | ------------------------------------------------------------ |
| Start                                       | 7 of 194, all SFMTA                                          |
| End                                         | 21 of 194, all SFMTA                                         |
| Start given only as a month, season or year | 18                                                           |
| Scope text                                  | every SFMTA-only row: SFMTA's layer publishes none, and the page says "None published" |
| Geometry                                    | 2: "PW FY21 Bike Traffic Signal Upgrade Program" and "Eddy Street Two-Way Conversion Project" |

At the feed's own row level: 60 of 7,853 rows have no start and 51 no end, with 0 end-before-start.

## B3. Status across sources

17 projects appear by nearly the same name on both SFMTA's layer and Public Works' pages. 6 disagree:

| Project                                   | Public Works page | SFMTA layer |
| ----------------------------------------- | ----------------- | ----------- |
| Masonic Avenue Streetscape                | In progress       | Completed   |
| Upper Haight Transit and Pedestrian Realm | In progress       | Completed   |
| Geneva Avenue Traffic Signal              | In progress       | Completed   |
| 6th Street Pedestrian Safety              | Completed         | Current     |
| Lombard Street Vision Zero                | Completed         | Legislated  |
| Third Street Bridge Rehabilitation        | Completed         | no phase    |

Where an SFMTA layer project merged with a feed job, 4 of the 5 pairs name the same phase in different words ("Implementation / Construction" against "Construction"). One pair does differ: Cesar Chavez Bikeway is Planning on the layer and Design in the feed.

## C1. Source coverage

| Body                                                         | What we hold                                                 | Window                                  | Gaps                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------ |
| SFMTA engineering hearings                                   | full agenda and results PDFs                                 | 2019-08-16 to 2026-09-04 (144 hearings) | 18 unreachable (HTTP 403), 12 of them in 2023; 3 unparsed; 2 with no results. The script asks for "since 2010", but the [archive](https://www.sfmta.com/past-meetings-and-events/2617) starts in August 2019. |
| SFMTA Board                                                  | only items that match bike keywords (139 of about 3,200 agenda items) | agendas 2019-01-15 to 2026-09-01        | Outcomes only from 2022-11-15, where the minutes index starts: none of the 74 matches before that date has one. Full agenda text is not kept, so an item that names a project without a bike word is invisible. |
| Board of Supervisors                                         | titles returned by 24 [Legistar](https://sfgov.legistar.com/) search terms | 2019–2026                               | Matching reads titles only. The September 2026 meetings mirror (`data/legistar/meetings/`, 20 meetings, 521 items) and the sponsored-legislation mirror (read 2026-09-04) are not inputs to the project record. |
| SFPUC Commission                                             | every minutes item                                           | 2021-01-26 to 2026-07-28                | Nothing before 2021, and no August or September 2026 minutes. |
| Public Works Commission, SFCTA Board, Rec and Park Commission, Port Commission | nothing                                                      | —                                       | `[model knowledge — verify]` Each approves some street work: contract awards, Prop L allocations, Golden Gate Park roads, the Embarcadero. |

## C2. Mentions per major project

"Major" means outlined on the list (top 10 by residents or plan miles) or carrying at least 1 mile of plan network: 43 projects. Counting only records from city bodies at grades exact, strong or probable, and excluding items copied from the project's own page, all 194 listed projects fall out as below. The 43 major projects are spread across these rows.

| Department   | Projects | 0 records | 1   | 2   | 3+  |
| ------------ | -------- | --------- | --- | --- | --- |
| SFMTA        | 41       | 23        | 9   | 9   | 0   |
| Public Works | 129      | 116       | 8   | 2   | 3   |
| SFPUC        | 24       | 22        | 1   | 1   | 0   |

2 of the 43 major projects have 3 or more distinct dated records. For the 14 major SFMTA projects the number is 0. Better Market Street has 2, Folsom-Howard 0 and Slow Streets 2.

**Real gap or matching failure: both.** Each project's full name, and each SFPUC or Public Works contract number, was searched independently across every local corpus: hearing PDF text, board matches, all 193 cached Board of Supervisors search results, the sponsored mirror, the September meetings, and all 3,032 SFPUC items. The search scripts are not in the repo. `[unverified — scripts not in the repo]`

Matching failures, where the item names the project but is not counted as its own:

- **Slow Streets.** Its name appears on 14 distinct dates: 4 hearings, 6 SFMTA Board items and 4 Supervisors files. These include the Board's 2022-12-06 item "Establishing a Slow Streets program" and 2021-08-03 "Designating four corridors as Slow Streets". The listed row counts 2. Cause: the exact-name rule in [`tools/projects/project-record.py`](../../tools/projects/project-record.py) needs a core name longer than 12 characters, and "slow streets" is exactly 12. The row is also a feed job, so it never gets the SFMTA program page's records.
- **Howard Street protected bikeway.** The SFMTA Board approved it on 2024-04-16. The item is graded "ambiguous" on Transbay Howard, Folsom-Howard and Howard Streetscape alike, so it shows only under "decisions on the same blocks" on all three.
- **SFPUC contract awards.** "Award Contract No. WD-2921 …" (2026-01-13) is graded co-located on the WD-2921 job. "Award Contract No. WD-2923 …" (2026-02-24) is on no project. The grader has no contract-number rule.
- **Oak Street Quick-Build.** Named in hearings on 2024-10-18 and 2024-11-08, and not attached. The listed row is the feed job, because SFMTA's own record has no phase and is dropped.
- **Also missed:** Transbay Howard (hearing, 2024-03-08), Cayuga (hearing, 2026-06-12) and J Church (hearing, 2023-08-18).

Real gaps, where no body we read discusses the project by name:

- 116 of 129 Public Works jobs, including every "Various Locations Pavement Renovation No …" contract. `[inference — mine]` These contracts are awarded outside the bodies we read. The Public Works Commission is the likeliest place to look.
- Octavia Boulevard Enhancement, Bikeway Hardening, Arguello Safety and Cesar Chavez Bikeway: no name hit in any corpus. A Board agenda that names them without a bike word would not be kept (C1).

## C3. Matching accuracy and labels

The heading "City decisions naming this project" shows every exact, strong or probable record. Of 213 such items across the list, 156 come from the project's own SFMTA page:

- 101 timeline milestones
- 36 page "meetings" labelled "SFMTA Board"; 25 of these are open houses, tabling events, walking tours or advisory-committee meetings
- 19 labelled "Engineering hearing"

Example: "District 10 Health Fest: Bayview in Motion", dated 2026-10-17, shows as an SFMTA Board decision on Bayview Community Pathway. Once page items are excluded, only 57 items across 194 projects are city-body records.

### C3c. Hand-checked link sample (graded 2026-09-28)

22 of 40 sampled city-body links are about their project and carry the right label ([data/audit/grades/c3-links.csv](../../data/audit/grades/c3-links.csv)).

- **7 are street matches.** The record is about the same street but a different job, such as a Valencia bikeway vote attached to a Valencia repaving. The page labels these "concerns a street", so the label is honest. They still count against C3 as written.
- **10 are wrong-project matches.** Five of them are Treasure Island rows matched on the island's name alone, covering power contracts and Park Code changes. Others are a Hetch Hetchy quarterly report attached to a sewer contract, and a residential-permit item attached to Sutter Street because Sutter is its cross street.
- **1 is mislabelled.** A farmers-market tabling event from the N Judah project page is labelled "SFMTA Board".

Three of the 40 are project-page events, which the sampler is meant to leave out. That is a bug in the sampler.

## D1. Dates

| Check                                             | Count                                     | Examples                                                     |
| ------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------ |
| End before start                                  | 0                                         |                                                              |
| End already passed, row still listed as current   | 2                                         | Better Market Street: end 2025-04-30 from its page's "finish construction in early 2025", phase Current, shown first on the list as "Until Apr 2025". Mission / Geneva Safety: end 2026-04-30. |
| Start passed, phase still Planning or Design      | 44                                        | The list labels these "Under way": Northern Waterfront Electrical (Planning, start 2023-04-01), Oak Street Quick-Build (Design, 2023-08-01), PEFWS Pipeline (Design, 2024-04-01) |
| Start more than eight years out, after 2034-09-28 | 1                                         | "Various Locations Pavement Renovation Under Overhead Contact System No 4", 2035-02-02 to 2036-04-16. Seven more start in 2033–2034. |
| Record dated in the future                        | 0 city-body records, 6 project-page items | The 2026-10-17 health fest (C3), a project-page event labelled "SFMTA Board"; the other 5 are page timeline milestones |
| Undated records                                   | 5 of 1,671                                |                                                              |

`[inference — mine]` The 44 phase-date conflicts are the feed's planned start dates that passed without the phase field being updated. The check: the live feed was updated 2026-09-25 (DataSF metadata), four days after our copy. Re-pull it and see whether the phases moved.

### D2. Dates against the department's page (hand-graded 2026-09-28)

The sample is 286 dates on 60 projects ([data/audit/grades/d2-dates.csv](../../data/audit/grades/d2-dates.csv)). 120 dates sit on projects with no department page, and 7 on pages that give no date for that milestone. Those 127 are left out because no page states the date, so there is nothing to grade against. That leaves 159 dates to grade. They sit on 35 of the 60 projects, 125 of them on SFMTA pages, so the sample reaches fewer projects than the criterion's 60. 30 of the 60 projects have no department page, 28 of them Public Works or SFPUC jobs, so the 159 say little about Public Works or SFPUC dates. Every field is below the 95% line.

| Field              | Correct  | Share |
| ------------------ | -------- | ----- |
| Construction start | 20 of 26 | 76.9% |
| Construction end   | 15 of 27 | 55.6% |
| Consultation start | 19 of 30 | 63.3% |
| Consultation end   | 19 of 30 | 63.3% |
| Other dates        | 38 of 46 | 82.6% |

The 48 misses are 43 wrong dates and 5 where DataSF and the page disagree. They have six causes:

- **Consultation dates are never read.** All 22 consultation misses show "not published" while the page lists outreach rounds, open houses or a hearing comment period, for example 6th Street's outreach from Winter 2013 to Fall 2019.
- **Stated completions are missed.** Eight projects show no construction end while the page gives one, such as "substantially completed in fall 2024" (Frida Kahlo Way) or "Construction 2024-25" (Powell Promenade).
- **Ranges and seasons are misread.** "Winter-spring 2027" becomes an April 2027 start and "Early 2018 - Spring 2019" becomes April 2019. "Early spring" and "late spring" both become April, and "Winter 2025/26" becomes January 2025. Eight dates are affected.
- **DataSF and the page disagree.** There are five cases. One is Sewer Replacement No 38: its linked page describes a District 2 job finished in December 2022, but DataSF dates it 2028–2029. The page is probably an earlier contract with the same number `[inference — mine]`.
- **Board of Supervisors records carry the wrong date.** Three records show the Legistar file's final-action date, which is the Mayor's signature or the filing date. They should show the date the Board met.

- **Other, 2.** 6th Street's page gives "construction begins January 2022" and the list shows no start. Contract 35 Traffic Signal Modifications shows DataSF's start, 2026-04-02, where its page says construction started in August 2026.

## E1. Valid shapes

| File                                                         | Features | Empty | Outside SF | Zero-length | Self-intersecting |
| ------------------------------------------------------------ | -------- | ----- | ---------- | ----------- | ----------------- |
| [`site/data/north-star/traced.geojson`](../../site/data/north-star/traced.geojson) (plan) | 2,870    | 0     | 0          | 0           | 0                 |
| [`site/data/bike-history/segments.json`](../../site/data/bike-history/segments.json) (bikeway layer) | 3,017    | 0     | 0          | 0           | 0                 |
| [`site/data/bike-history/all-ages.geojson`](../../site/data/bike-history/all-ages.geojson) | 1,210    | 0     | 0          | 0           | 0                 |
| [`site/data/sf-streets.json`](../../site/data/sf-streets.json) (base map) | 16,372   | 0     | 0          | 0           | 0                 |
| project geometry in `coordination.json`                      | 194      | 2     | 0          | 0           | 0                 |
| [`out/sfmta-projects/projects.geojson`](../../out/sfmta-projects/projects.geojson) (raw layer) | 461      | 0     | 0          | 5           | 6                 |

"Outside SF" means a vertex outside −122.53 to −122.35, 37.70 to 37.835. Also found:

- 214 of 2,870 traced plan blocks matched the drawn line on less than 60% of their length. The trace's floor is 50%.
- `all-ages.geojson` repeats 75 CNNs. `[inference — mine]` These are blocks with a later `until` row, not errors.
- Of the 29 listed SFMTA projects from the layer, 4 are published only as polygons: Better Market Street (partly), Balboa Park Station, Octavia Boulevard Enhancement and Western Addition CBTP. The script's area test looks for a method called `ring`, but [`tools/projects/project-blocks.py`](../../tools/projects/project-blocks.py) writes `polygon`. So `areaProjects` is 0, and Western Addition gets a line-based reach of 261 residents from a polygon.

## E2. Street-grid alignment

Checked against DataSF's [centerline file](https://data.sfgov.org/d/3psu-pn9h) (cache fetched 2026-09-22):

- **Plan network:** 0 of 2,870 traced blocks sit more than 50 ft (15 m) from their centerline. By construction, it is snapped.
- **Bikeway layer:** 51 of 3,017 segments sit more than 50 ft (15 m) from their CNN's centerline, and 21 more than 330 ft (100 m). The worst are John F Kennedy Drive and park segments carrying Cabrillo Street CNNs, 0.7–2.3 mi away, for example CNN 3504000 at 2.3 mi. Others: a Bay Trail segment on CNN 12554201 at 1.1 mi, and a Judah Street segment at 0.65 mi.
- **Retired CNNs:** 21 bikeway segments and 12 all-ages rows carry CNNs the centerline marks retired.
- **Split blocks:** 153 distinct project CNNs miss a plan block because the block has been split. For example, 300000 against plan blocks 300001–300003. Those blocks drop out of the project's plan miles.

`[inference — mine]` The bikeway layer's CNN attribute is stale or mis-keyed for park paths. Every CNN join then gives that block the wrong street's bikeway, plan class and reach. The drawn line is right, because it comes from the layer's own geometry. The check: re-key segments by nearest centerline and compare all-ages miles.

## E3. The map shows the whole project

A project's small map draws only the blocks that are on the plan or on the bikeway layer:

- 2,257 of 8,414 held blocks are drawn (27%).
- 152 of 194 maps draw under half their blocks.
- Better Market Street draws 92 of 179, and PW As Needed Spot Sewer No 47 draws 51 of 239.

The Better Coordination map says "24 blocks are not drawn". The project maps say nothing.

## F1. Units

A scan of all 203 rendered transportation pages for m, km, metres and meters found 0. The unused `site/content/transportation-osm.html` still says "metres" twice.

"mi" means two things. Current Projects' "plan mi" is centerline miles: `planMiles` sums each block's `length_m` once. Better Coordination uses "miles per direction of travel, the plan's unit" (`department-overlap.json` `unit`). For the 91 jobs both pages show, the totals are 47.5 mi against 78.3 mi. Neither page labels the difference.

## F2. Denominators

| Where                                      | Residents | Source                                                   |
| ------------------------------------------ | --------- | -------------------------------------------------------- |
| Overview map, latest year (`history.json`) | 830,235   | ACS 5-year block groups                                  |
| Project reach (`coordination.json`)        | 873,965   | [2020 census blocks](https://data.sfgov.org/d/p2fw-hsrv) |
| Plan's printed share                       | 80%       | printed p. 24                                            |

Our 2024 figure on the plan's definition is 80.2%, and our latest 80.29% of 830,235 residents (ACS). Those agree with the plan's 80%. The two resident totals are not labelled on the pages.

## F3. Freshness

- **Coordination feed:** queried 2026-09-21. DataSF shows [btxj-k9uh](https://data.sfgov.org/d/btxj-k9uh) rows updated 2026-09-25 (metadata read 2026-09-28).
- **Bikeway layer:** queried 2026-09-22. Its last edit was 2026-05-21, according to both `transportation.json` `bikewayLayerAsOf` and `bike-progress.json` `layer.lastEdited`.
- **Two sources disagree on the layer's date.** The overview's source line, typed into `site/content/transportation.md`, says "updated only through December 2025". The layer metadata says 2026-05-21. The page text is typed, so it will not move when the data does.
- **Everything else:**
  - Hearings, SFMTA Board, SFPUC, Public Works pages, reach and centerline: 2026-09-22
  - SFMTA pages: 2026-09-24 and 2026-09-28
  - Street base map and plan direction centerlines: 2026-09-06
  - Sponsored Legistar mirror: 2026-09-04

All are inside horizon.

## F4. Traceability

| Figure                                        | Traced to                                                    | Result                                                       |
| --------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| "194 street projects"                         | `coordination.json` `counts.listed`: 165 feed jobs from btxj-k9uh (2026-09-21) + 29 layer projects | reaches source rows, but the page also calls them "under way or coming up", and 2 have ended (D1) |
| "Implemented planned bikeway 0.5 mi"          | `department-overlap.json` → [78va-8dhi](https://data.sfgov.org/d/78va-8dhi) paving record (2026-09-22) | reaches source rows                                          |
| "80% of residents now live within a 1/4 mile" | typed in `content/transportation.md`, cited to the plan. Our data gives 80.29% (ACS) | agrees, but typed                                            |

Other typed figures: "only 1 of the feed jobs … matches" a Public Works page, in `content/transportation-about.md`, where `feed-join.json` holds 3 likely matches (see B1); and "updated only through December 2025" (F3).

## F5. Clean text

- `out/sfmta-board/meetings.json`: 2025-09-02 "RESCIND ? CLASS II BIKEWAY" and "ESTABLISH ? CLASS IV BIKEWAY (TWO-WAY)".
- The SFMTA layer name "29 Sunset Improvement Project â€“ Phase Two" in `out/project-record/projects.json`.

Neither reaches the rendered pages today. 0 found in `coordination.json`.

## Step changes

| Series                              | Break                                                      | Reading                                                      |
| ----------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------ |
| SFMTA Board matches with an outcome | 0 of 74 before 2022-11-15; 57 of 65 on or after            | Measured cause: the minutes index scraped from [sfmta.com Resolutions & Legislation](https://www.sfmta.com/resolutions-legislation) starts on 2022-11-15. `[inference — mine]` The site lists no earlier minutes. The check: page back through that listing. |
| Hearing items read per year         | 339 in 2022, 174 in 2023, 265 in 2024                      | Measured cause: 12 of the 22 hearings in 2023 returned HTTP 403, so the 2023 dip is our fetch, not SFMTA's output. |
| Hearings per year                   | 8 in 2019, about 21 after                                  | Measured cause: the archive starts 2019-08-16.               |
| SFMTA Board bike items              | 11 to 26 a year in 2019–2025; 4 in 2026, all on 2026-06-16 | Total agenda items held steady (201 in 15 meetings in 2026, against 357 in 22 in 2025), so the parse still works. Hearing items routed to the Board also fell (7 in 2024, 3 in 2025, 2 in 2026). `[inference — mine]` A real drop in bike items going to the Board. The check: read the 2026 Board agendas by hand for bikeway items. |
| Hearing bike items per 100 items    | about 30 in 2019–2020, 9–10 in 2021–2022, 15–22 after      | `[inference — mine]` The 2020 Slow Streets and COVID-era legislation raised the share, and it has not returned. Unchecked: compare the item topics for 2020 against 2022. |

## Checks not run

- SFPUC's own project list (A1).
- The 66 in-progress Public Works pages with no block data (A1).
- Whether the 23 no-phase SFMTA Bike projects are active (A1).
- Whether each listed project has a city-body record dated before its construction start (C4).
- Full SFMTA Board agenda text, which is not kept locally (C1).

## What the baseline asked to fix, and where each stands in the current report

1. List every active SFMTA project that touches bike or pedestrian work, whether or not SFMTA tags it Bike (A1). Still fails: 14 of 107 active SFMTA projects missing.
2. Read consultation dates and stated completions from each department's page, and keep a range or a season as written (D2). Still fails.
3. Read the Public Works Commission, SFCTA Board and Rec and Park Commission, and keep full SFMTA Board agendas (C1, C2). Both still fail.
4. Keep project-page events out of "City decisions", and match records by contract number (C3). Labels now pass (C3a); contract-number and name matching still fails (C3b).
5. Draw every block a project holds, and use one mile basis on every page (E3, F1). E3 now passes; F1 still fails.

Fixes already made to the pipeline are in fixes.md; every check's current grade is in the [audit report](../../out/transportation-audit/report.md).
