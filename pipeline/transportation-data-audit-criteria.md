# Transportation data audit criteria

What to check in the data behind the biking pages (`site/src/pages/transportation*.mjs`), and what counts as good enough. Written 2026-09-28 at Bryan's request: "do we actually get all projects from each department? do we tie project details together clearly with project pages? are we cleanly getting a complete record of discussions ... do we get clean dates and all key fields? do we get clean map geometry?"

Each criterion says what it is, why an advocate cares, how to measure it, and the pass line. `pipeline/transportation-audit.py` computes every measurable check and prints pass or fail against these lines. The hand-graded checks (D2, and the sample in C3) record their grades in a file the script reads. The first run of these checks is in [research/transportation-audit-2026-09/data-quality.md](../research/transportation-audit-2026-09/data-quality.md).

Each check is pass, fail, or not measured. There is no partial grade.

The current result of every check is in the [report](../out/transportation-audit/report.md).

## A. Which projects we hold

### A1. Completeness per department
- **What:** every active Public Works and SFPUC project on the Biking and Rolling Plan's network is on the Current Projects list. So is every active SFMTA project that touches bike or pedestrian infrastructure, whether or not its block is on the plan and whether or not SFMTA tags it Bike.
- **Why:** an advocate uses the list to find the job that will dig up their street. A missing job is a missed chance to ask for the bikeway.
- **Measure:** compare our list with each department's own public list: SFMTA's [sitemap of project pages](https://www.sfmta.com/sitemap.xml), Public Works' [project pages](https://sfpublicworks.org/projects), and SFPUC's own list where one exists. Count active projects on their list that touch the plan's blocks and are missing from ours, and name them. For SFMTA, also count every active project that touches bike or pedestrian infrastructure, on the plan or not.
- **Pass:** SFMTA: zero missing. Every SFMTA project that touches bike or pedestrian infrastructure is listed, whether or not SFMTA tags it Bike and whether or not its block is on the plan (Bryan, 2026-09-28: "We should never miss an SFMTA project that has something to do with biking or pedestrian infrastructure"). Other departments: no more than 5% of active on-plan projects missing, and every miss explained.

### A2. Other agencies
- **What:** work by agencies other than SFMTA, Public Works and SFPUC, such as the Port, SFCTA, Transbay, Rec and Park and PG&E, that opens a plan street is either listed or deliberately left out.
- **Why:** a Port or PG&E trench on a plan street is the same chance as a Public Works one.
- **Measure:** count jobs in the [coordination feed](https://data.sfgov.org/d/btxj-k9uh) from other agencies that are active and touch plan blocks.
- **Pass:** each one is either listed or named on About the data as out of scope.

### A3. Duplicates
- **What:** one piece of work is one row.
- **Why:** duplicate rows inflate the project count and the miles.
- **Measure:** pairs of listed projects with the same name, or with a block overlap of 50% or more (Jaccard: the blocks both rows hold, divided by the blocks either row holds), or two sources' rows for the same project that were not merged.
- **Pass:** zero same-name rows. Every high-overlap pair is either merged or shown on the page as related.

## B. Project details

### B1. Link to the department's own page
- **What:** each listed project links to its department's page for that project, not only to a dataset row.
- **Why:** the department's page has the scope, the contact and the schedule. A DataSF JSON row is not readable by an advocate.
- **Measure:** share of listed projects, per department, with a link to a department project page, and how many of the rest have a page the department publishes under the same or nearly the same name.
- **Pass:** over 90% of the listed projects a department publishes pages for, overall and within each department. That is every SFMTA project, and Public Works and SFPUC jobs in construction or with a page of their own. Every other job shows the closest official source, such as a programme page or the paving map, and the About the data page says why (Bryan, 2026-09-29).

### B2. Key fields present
- **What:** name, department, phase, start, end, streets, geometry and scope.
- **Why:** a row with no start date cannot be ranked by urgency. A row with no scope cannot show whether bike work is in it.
- **Measure:** count of missing values per field, per department.
- **Pass:** start and phase on 95% of rows. Every missing value shows as "not published" on the page, never as a blank.

### B3. Status agrees across sources
- **What:** when two departments publish the same project, their status agrees, or both are shown.
- **Why:** "In progress" on one site and "Completed" on another changes whether there is anything left to ask for.
- **Measure:** match same-name projects across SFMTA's layer and Public Works' pages, and count status disagreements.
- **Pass:** every disagreement is printed with both values.

## C. Discussion record

### C1. Source coverage
- **What:** the bodies that decide street projects are all read, over a window long enough to cover a project's life (2019 or earlier to today).
- **Why:** "no city decision found" is only a finding if we looked everywhere the decision could be.
- **Measure:** for each body (SFMTA engineering hearings, SFMTA Board, Board of Supervisors, SFPUC Commission, Public Works Commission, SFCTA Board), give the date range read, the meetings missing, and whether full text or only keyword hits are kept.
- **Pass:** each deciding body read from 2019 or earlier to within a month of today, with less than 5% of meetings missing, and full item titles kept. Engineering requirement: each body has its own fetch script that mirrors meetings to disk, re-fetches drafts, and can be rerun without re-downloading what it holds.

### C2. Mentions per major project
- **What:** a major project, one in the top 10 by reach (residents within a straight-line quarter mile of its lines who are not already that close to today's all-ages network) or miles or with at least a mile of plan network, counted per direction of travel as every mile on the site is, comes up in the record several times.
- **Why:** Bryan's expectation: "every major project to come up several times in discussion history." A major project with one record is almost certainly a matching miss.
- **Measure:** distinct dated records from city bodies (not the project's own page) per major project. For each one under three, run an independent name search across every local corpus to tell a real gap from a matching miss.
- **Pass:** every major project below three has its reason printed, and the share with three or more is reported. Most Public Works jobs never go before a city body by name, so no share line is reachable (Bryan, 2026-09-30).

### C3. Matching accuracy and labels
- **What:** a record attached to a project is about that project, and its label says what it is.
- **Why:** an open house labelled "SFMTA Board" reads as a vote that never happened.
- **Measure:** hand-check a sample of links; count project-page events shown under "City decisions"; count items that name the project's contract number or full name but are graded weaker.
- **Pass:** no mislabelled kinds. Every item naming the project's name or contract number is counted as the project's own. Every link in a seeded random sample of at least 40 is about its project.

### C4. A record before work starts

- **What:** a listed project has at least one dated record from a city body before its construction start.
- **Why:** the record before construction is where an advocate could have weighed in. A project with none either had no public decision or sits in a source we do not read.
- **Measure:** share of listed projects with a start date that have one or more city-body records dated before that start. For each one without, name the body that should have decided it.
- **Pass:** over 90% of projects (Bryan, 2026-09-28), or the shortfall is logged as a top issue on About the data. Bryan, 2026-09-29: "Let's just log this as a problem and add to the list of issues. That we have most projects in the shared feed that don't have a project page." The check reports the measured share either way, and passes below 90% only while About the data's top issues carry that gap: coordination-feed jobs with no project page, and so no city-body decision found before work starts. A deciding body we do not read is a coverage gap under C1, not an explanation.

## D. Dates

### D1. Missing, impossible, inconsistent
- **What:** dates exist, parse, and agree with each other and with the phase.
- **Why:** the list sorts by date and says "under way" or "starts". A wrong date moves a job up or down the list and gives the wrong deadline.
- **Measure:** count missing start and end dates; end before start; end already passed on a row the page calls current; phase Planning or Design with a start date already passed; dates more than eight years out; records dated in the future.
- **Pass:** zero end-before-start. Zero past-end rows on a "current" list, apart from work the department still lists as active, on its page, its project layer or the coordination feed,, which stays listed with its passed end date shown (Bryan, 2026-09-29). Every phase-date conflict shown on the page.

### D2. Dates are right

- **What:** a date we show matches the date the department's own page or record gives for that milestone.
- **Why:** a date can parse and look plausible and still be the wrong milestone, such as a project's predicted completion shown as its construction end.
- **Measure:** hand-grade a random sample of at least 60 listed projects against the department's page. Grade construction start, construction end, public consultation start and public consultation end separately. A correct "not published" counts as correct.
- **Pass:** over 95% correct on each of those four fields, and over 95% on all other dates shown (Bryan, 2026-09-28). The share is of dates a department page states; rows marked "no page" or "not on page" are left out.

## E. Geometry

### E1. Valid shapes
- **What:** no empty, zero-length, self-intersecting or out-of-city shapes.
- **Why:** a bad shape draws in the wrong place or not at all, and every reach figure is computed from these shapes.
- **Measure:** run each geometry file through the checks: plan network, bikeway layer, all-ages network, SFMTA project layer, the project geometry on the page.
- **Pass:** zero of each in files the site draws.

### E2. Lines up with the street grid
- **What:** a segment keyed by a street block (CNN) lies on that block in the city's [centerline file](https://data.sfgov.org/d/3psu-pn9h).
- **Why:** joins run on CNN. A CNN that points at a different street gives a block the wrong bikeway, the wrong plan status and the wrong reach.
- **Measure:** the largest distance from a segment's vertices to its CNN's centerline. Flag over 15 m (50 ft) and over 100 m (330 ft); count CNNs retired from the centerline.
- **Pass:** zero over 15 m (50 ft) in files the site draws.

### E3. The map shows the whole project
- **What:** a project's map draws all of its blocks.
- **Why:** a map that draws a quarter of the job understates where it digs.
- **Measure:** blocks drawn divided by blocks held, per project.
- **Pass:** every block held is drawn, on every project.

## F. Across pages

### F1. Units
- **What:** distances in feet or miles (Bryan, 2026-09-24), and one meaning per unit label.
- **Why:** "6 mi" on one page and "6 mi" on the next should be the same kind of mile.
- **Measure:** scan the rendered pages for metric units. Check each "mi" figure's basis: centerline miles, or miles per direction of travel.
- **Pass:** zero metric units shown. One mile basis across every page and chart. Every "mi" on the site means the same thing, and the About page says which.

### F2. Denominators
- **What:** "residents" means the same population wherever it is a denominator.
- **Why:** 80% of one population and 80% of another are different claims.
- **Measure:** list each page's resident total and its source.
- **Pass:** one total, or each one labelled.

### F3. Freshness
- **What:** every source is within its horizon: 90 days for a live dataset, 180 for a document.
- **Why:** a stale feed lists jobs that have finished and misses ones that have started.
- **Measure:** each source's query date against today and against the publisher's own last-updated date. Check that the page's "as of" text matches the data.
- **Pass:** all within horizon, and no hard-coded "as of" text that disagrees with the data.

### F4. Traceability
- **What:** a figure on the page can be followed to a source row.
- **Why:** an advocate quoting a number to a supervisor has to be able to show where it came from.
- **Measure:** trace three headline figures per page from rendered text to the data file to the source. Count figures typed into page prose rather than filled from data.
- **Pass:** every headline figure reaches a source row. Zero typed figures that the data could supply.

### F5. Clean text
- **What:** no encoding debris in names and titles.
- **Why:** "RESCIND ? CLASS II BIKEWAY" reads as broken.
- **Measure:** count `?` in place of dashes, `â€`, `Ã` and U+FFFD in shown names and titles.
- **Pass:** zero.
