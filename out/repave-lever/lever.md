# Tying bike work to repaving: how many miles a year it would add

Built 2026-11-24 by `tools/bike-network/repave-lever.py`. Sources: [`78va-8dhi`](https://data.sfgov.org/d/78va-8dhi) [DataSF 78va-8dhi — queried 2026-11-19]; [`5wbp-dwzt`](https://data.sfgov.org/d/5wbp-dwzt) [DataSF 5wbp-dwzt — queried 2026-11-24]; [`btxj-k9uh`](https://data.sfgov.org/d/btxj-k9uh) [DataSF btxj-k9uh — queried 2026-11-24]; [`ygmz-vaxd`](https://data.sfgov.org/d/ygmz-vaxd) archived releases 2021-03-25 to 2026-04-04 [web.archive.org captures of DataSF ygmz-vaxd — read 2026-09-22]; SFMTA's layer [SFMTA ArcGIS Bicycle/bicycle layer 0 — queried 2026-11-10]; plan network [Biking and Rolling Plan, March 2025, North Star map — traced 2026-09-29].

## The answer

**1.4 to 7.7 miles a year.** That is the plan-network mileage San Francisco resurfaced each year and left without the facility the plan draws on it, read from [`78va-8dhi`](https://data.sfgov.org/d/78va-8dhi) [DataSF 78va-8dhi — queried 2026-11-19] against SFMTA's bikeway layer [SFMTA ArcGIS Bicycle/bicycle layer 0 — queried 2026-11-10]. Since 2010 the city has resurfaced 201 miles of the plan network; 15.5 miles got the planned facility with the repave and 123 miles are still short of it. For scale, the plan network gained 4.4 miles a year of newly-met facility between 2021-03-25 and 2026-04-04 (21.9 miles in 5.03 years) [web.archive.org captures of DataSF ygmz-vaxd — read 2026-09-22], so tying the facility to the repave would have added between a third of that and nearly twice it.

| Reading | Miles a year | Definition |
|---|---|---|
| low | **1.4** | Separated and Shared-use Path corridors, 2021–2025 |
| mid-recent | **6.4** | all rated corridors, 2021–2025 |
| mid-long | **1.7** | Separated and Shared-use Path corridors, 2010–2025 |
| high | **7.7** | all rated corridors, 2010–2025 |

The low reading counts only corridors where the plan draws a separated lane or a path, over 2021–2025. The high reading adds the Shared and Shared L3 corridors, whose calming the bikeway layer cannot see, and runs from 2010. Miles are per direction row, the plan's unit: the length of each block the traced plan covers, times the block's direction rows.

**On the 30-year assumption: it is about right.** On the plan's streets that the city maintains, a block is resurfaced about every **28 years**: 91 of the 2,525 accepted plan blocks a year over 2010–2025, and 69 a year over 2021–2025, a 37-year cycle [DataSF 78va-8dhi — queried 2026-11-19]. Over all 3,077 plan blocks, including the 552 on streets the city has not accepted for maintenance (the Embarcadero, Sloat, Lincoln, JFK and the Presidio among them), the cycle reads 33 years. Citywide, 435 of the 13,190 blocks the city has accepted for maintenance were resurfaced a year, a 30-year cycle (intersections carry their own ids, another 208 a year, and are not blocks); over the 16,378 active blocks the cycle reads 37 years and over all 17,176 centerline segments 39 [DataSF 3psu-pn9h — queried 2026-11-24]. 99% of the blocks resurfaced since 2010 are accepted blocks, so the accepted figure is the one for the streets Public Works paves. On plan blocks resurfaced at least twice since 1947, the median gap between resurfacings is 26.0 years (quartiles 19.3 to 33.6, 1,667 gaps) [DataSF 78va-8dhi — queried 2026-11-19]; from 1990 on, 21.1 years over 592 gaps. Under the widened repave definition (method, step 2) the accepted city cycle is 28 years and the plan cycle 32. So a street comes up for repaving about once in 28 to 33 years, and a plan street no more often than the average one: the lever is slow, and a block missed at its repave waits a generation.

### The assumption tested every way the data allows

Blocks resurfaced a year, and the cycle that count implies over the block set, for each cut of the record that could make repaving look more frequent [DataSF 78va-8dhi — queried 2026-11-19]. Functional class is the PCI table's own.

| Block set | Blocks | Resurfaced a year | Implied cycle, years |
|---|---|---|---|
| plan blocks, accepted streets, 2010–2025 | 2,525 | 90.8 | **28** |
| plan blocks, accepted streets, 2021–2025 | 2,525 | 68.8 | **37** |
| plan blocks, accepted streets, 2012–2018 (Road Repaving and Street Safety Bond years) | 2,525 | 107.9 | **23** |
| plan blocks, all, 2010–2025 | 3,077 | 92.1 | **33** |
| plan blocks, all, widened repave definition, 2010–2025 | 3,077 | 96.4 | **32** |
| plan blocks the plan draws Separated, accepted, 2010–2025 | 759 | 23.4 | **32** |
| plan blocks on arterials, accepted, 2010–2025 | 978 | 32.6 | **30** |
| plan blocks on collectors, accepted, 2010–2025 | 386 | 16.6 | **23** |
| plan blocks on residential streets, accepted, 2010–2025 | 1,148 | 41.6 | **28** |
| city blocks, accepted streets, 2010–2025 | 13,190 | 435.2 | **30** |
| city blocks, accepted streets, widened repave definition, 2010–2025 | 13,190 | 462.2 | **28** |
| city blocks, accepted streets, 2012–2018 | 13,190 | 487.7 | **27** |
| city arterials, accepted, 2010–2025 | 3,480 | 121.9 | **28** |
| city arterials, accepted, widened repave definition, 2010–2025 | 3,480 | 128.8 | **27** |
| city collectors, accepted, 2010–2025 | 1,391 | 52.0 | **27** |
| city residential streets, accepted, 2010–2025 | 8,094 | 261.2 | **31** |

No cut reaches a cycle much shorter than 30 years. The shortest are the plan's collectors, at 23 years, and the bond years 2012–2018, at 23 on plan blocks and 27 citywide; the plan's Separated corridors, where the lever matters most, run 32.

## Year by year

Plan-network blocks resurfaced each year, in miles of plan network, and what SFMTA's layer [SFMTA ArcGIS Bicycle/bicycle layer 0 — queried 2026-11-10] says is on them now. *Already* had the planned class before the repave (every dated row predates it); *received* meets the plan and carries an install or update year in the repave year or the next; *later* meets the plan with a date two or more years after; *undated* meets the plan and carries no year; **short** does not meet the plan today.

| Repaved | Blocks | Miles | Already | Received | Later | Undated | Short | Streets that received |
|---|---|---|---|---|---|---|---|---|
| 2010 | 111 | 12.9 | 0.7 | 0.4 | 3.2 | 0.0 | **8.6** | Battery St, Sanchez St, 3rd St |
| 2011 | 103 | 16.0 | 0.5 | 0.0 | 3.0 | 4.5 | **8.0** | — |
| 2012 | 127 | 15.8 | 3.4 | 0.7 | 3.8 | 0.1 | **7.8** | 17th St, Duboce Ave, Howard St, Lee Ave |
| 2013 | 115 | 24.2 | 3.9 | 2.0 | 2.7 | 6.4 | **9.3** | Bay Shore Blvd, Point Lobos Ave |
| 2014 | 99 | 13.7 | 4.7 | 0.5 | 2.5 | 0.0 | **6.0** | Polk St, Cesar Chavez St |
| 2015 | 112 | 15.4 | 0.8 | 3.0 | 0.2 | 0.0 | **11.4** | Ocean Ave, Bay St, Oakdale Ave |
| 2016 | 92 | 10.7 | 1.4 | 0.8 | 0.6 | 0.0 | **7.9** | Vicente St, Fell St |
| 2017 | 91 | 12.0 | 0.4 | 1.2 | 1.0 | 0.0 | **9.3** | San Jose Ave, Potrero Ave, Vicente St |
| 2018 | 101 | 13.2 | 0.3 | 2.2 | 1.9 | 0.0 | **8.8** | Polk St, Masonic Ave |
| 2019 | 81 | 15.9 | 4.8 | 1.3 | 0.9 | 0.0 | **8.8** | 2nd St, Brannan St, Clipper St |
| 2020 | 57 | 7.7 | 0.6 | 2.5 | 0.1 | 0.0 | **4.5** | 2nd St, Folsom St, Anza St, Townsend St |
| 2021 | 42 | 6.8 | 0.8 | 0.0 | 1.6 | 0.0 | **4.3** | — |
| 2022 | 69 | 8.8 | 0.0 | 0.6 | 0.0 | 0.0 | **8.2** | Evans Ave |
| 2023 | 44 | 6.4 | 1.5 | 0.0 | 0.0 | 0.0 | **5.0** | — |
| 2024 | 79 | 11.3 | 3.0 | 0.2 | 0.0 | 0.0 | **8.1** | Dr Carlton B Goodlett Pl |
| 2025 | 85 | 10.1 | 3.6 | 0.0 | 0.0 | 0.0 | **6.5** | — |
| 2026 | 74 | 8.4 | 5.2 | 0.9 | 0.0 | 0.0 | **2.3** | Folsom St, Winston Dr |

Over 2010–2025: 201 miles of plan network resurfaced, 15.5 received the planned facility with the repave, 123 are still short. 2026 is a part year.

### Why the received column looks the way it does

The years with a real received figure are single projects, not a practice: the streets column names them. A repave year with many blocks and almost nothing received is the normal case in every year of the record. Plan blocks were resurfaced at 110 a year over 2012–2018 and 69 a year over 2019–2025; city blocks at 491 and 404 [DataSF 78va-8dhi — queried 2026-11-19]. The 2011 Road Repaving and Street Safety Bond funded paving in the first window [inference — mine; confirm against Public Works' annual paving reports].

### The two ways of reading 'received' agree

For repaves dated 2021–2025, the archived captures of [`ygmz-vaxd`](https://data.sfgov.org/d/ygmz-vaxd) allow a second reading: the block's class in the last release before the repave against its class in the release loaded 2026-04-04. A release is dated by its data_loaded_at where the export carries it, and by its capture date for the 2021 and 2022 exports, which predate the column. On whether a block is short today the two readings agree on 316 blocks and disagree on 0 [web.archive.org captures of DataSF ygmz-vaxd — read 2026-09-22], so the DataSF capture and SFMTA's service carry the same class on every one of these blocks. On which blocks *received* the facility they differ in both directions: the captures show 7 blocks gaining the planned class after their repave, the layer's dates show 5. In 2021 the captures see 2 and the layer's dates 0. Where the captures see more, the block was upgraded without a new INSTALL_YR or UPDATE_YR, which is the usual case for an upgrade. Where the layer sees more, the work is newer than the last release (2026-04-04); SFMTA's layer was edited 2026-10-19. Each reading is a floor on received.

## Public Works and SFPUC openings, from the coordination feed

[`btxj-k9uh`](https://data.sfgov.org/d/btxj-k9uh) [DataSF btxj-k9uh — queried 2026-11-24] lists projects planned or under way, one row per block; finished projects drop out (5 rows read Completed), so it starts where its memory does. Blocks below are rated plan blocks a Public Works or SFPUC project has entered construction on, by the year construction started. SFPUC's sewer work is filed by Public Works' Hydraulic division, so it sits under Public Works here.

| Construction began | Agency | Plan blocks | Miles | Short today | Also resurfaced that year or next |
|---|---|---|---|---|---|
| 2017 | Public Works | 1 | 0.8 | 0.8 | 0 |
| 2023 | Public Works | 7 | 0.9 | 0.9 | 0 |
| 2024 | Public Works | 14 | 1.8 | 1.8 | 0 |
| 2025 | Public Works | 46 | 3.9 | 1.9 | 14 |
| 2026 | Public Works | 98 | 14.5 | 9.8 | 2 |

Agencies counted, by row: SF DPW IDC - Streets & Highways (128); SF DPW IDC - Hydraulic (39); SF DPW BDC - Architecture (9); SF DPW BDC - Building Project Management (1).

## Method

1. **Plan network.** The North Star map traced onto city centerlines, 3,077 blocks, 458 miles [Biking and Rolling Plan, March 2025, North Star map — traced 2026-09-29]. 191 blocks drawn Car-free or Undecided have nothing in a bikeway layer to score against and are left out of every figure. A block's miles are counted per direction of travel, which is how the plan counts its 472 miles (printed p. 20): the sum of its bikeway layer rows' own lengths where the block is in the layer (3,866 blocks), else its centerline length once where [`3psu-pn9h`](https://data.sfgov.org/d/3psu-pn9h) flags the street one-way (614) and twice otherwise (1,674), times the share of the block the plan draws (72 blocks where the plan's line stops partway, at corridor ends). That gives 458 miles. A block meets the plan when its best Caltrans class reaches what the plan's class needs: a separated lane or path for Separated, a path for Shared-use Path, anything above a sharrow for Shared and Shared L3.
2. **Repaves.** [`78va-8dhi`](https://data.sfgov.org/d/78va-8dhi) holds 307,659 PCI changes on 18,416 pavement segments (14,189 blocks and 4,227 ids with no centerline row, which are intersections), 1947-11-01 to 2026-11-17, each flagged Survey or Treatment [DataSF 78va-8dhi — queried 2026-11-19]. A repave is a Treatment that resets the score to 100: 24,871 events on 16,249 segments. The 3,743 treatments that leave the score below 100 are seals and patches and are not counted; 70 treatment rows carry no date. The table has no treatment-type column (20 columns, checked in its metadata [DataSF 78va-8dhi metadata — read 2026-11-19]), so what a Treatment was cannot be read from it. A **widened** definition adds Survey rows that read 100 after the block last read under 70 and have no Treatment 100 within 400 days — a block does not go from failing to perfect without resurfacing — which adds 1,172 events; the cycle table above carries both.
3. **Check on that definition.** [`5wbp-dwzt`](https://data.sfgov.org/d/5wbp-dwzt) locks a block against digging for five years after a repave [DataSF 5wbp-dwzt — queried 2026-11-24]. Of its 2,586 locked blocks, 2,585 carry a PCI-100 treatment within 400 days of the lock date. Inside the lock record's window (2021-11-25 to 2026-11-11), 2,575 of 2,854 PCI-100 blocks are locked and 0 of 554 lighter-treated blocks are. Of the 279 PCI-100 blocks with no lock, 8 are dated within 60 days of the record's start, and the rest cluster on Valencia St, Fillmore St, Kirkham St, Hazelwood Ave, streets with SFMTA-led street projects in the window, which would be paving filed under a project rather than a Public Works job order [inference — mine; the check is the job order numbers on those blocks]. 0 blocks carry two lock dates, so the interval cannot come from the lock record; it comes from the PCI history.
4. **Join.** By CNN, the block id every table shares. A repave and a plan segment on one CNN are co-located on the same block; this says nothing about whether the paving job and any bikeway work were one project.
5. **Received.** From SFMTA's own layer [SFMTA ArcGIS Bicycle/bicycle layer 0 — queried 2026-11-10], which carries INSTALL_YR and UPDATE_YR (the DataSF copy drops the update fields), graded as the year table's header says. Every rate uses 2010–2025; the record before 1990 holds under 200 treatments a year.
6. **Interval.** Gaps between consecutive repaves on one block, gaps under 1 year dropped as one job recorded twice (31 on plan blocks). Turnover is blocks repaved a year over a block count: 3,077 plan blocks; and from [`3psu-pn9h`](https://data.sfgov.org/d/3psu-pn9h) [DataSF 3psu-pn9h — queried 2026-11-24], 17,176 centerline segments, 16,378 of them active and 13,190 accepted for maintenance.

## Caveats

- **The gap median is censored.** It sees only blocks resurfaced twice inside the record; 2,438 of 3,077 plan blocks have any repave on record and 2,003 have one since 2000. Events missing from the early record lengthen gaps and the record's end cuts long gaps off, so the direction of the bias is not known; the median is 26.0 years over the whole record and 21.1 from 1990 on, and the turnover figures are the ones to quote.
- **Short is a floor for Shared corridors.** The plan's Shared classes ask for a calmed street, which no bikeway layer measures. A Shared block with a painted lane counts as met here and may not be; one with a sharrow counts as short and is.
- **The layer lags.** SFMTA's layer was last edited 2026-10-19; a facility built since reads as absent, so the most recent years' short figures can only fall.
- **Dates on the layer are partial.** Upgrades often keep the original INSTALL_YR and only sometimes gain an UPDATE_YR, so the received column undercounts and the already column overcounts. The short column does not depend on dates.
- **The traced plan carries registration error** (6.2 m median, 15.6 m at the 90th percentile), so a few blocks at corridor ends are on the plan here and not on SFMTA's map. The low reading drops blocks the trace overlaps by under half.
- **Intersections carry their own ids.** 4,227 of the 18,416 ids in the PCI history have no row in the centerline table [DataSF 3psu-pn9h — queried 2026-11-24]. 4,225 of them are named as an intersection in one of the PCI table's three name fields. They are left out of the block counts and cannot join a plan block.
- **The coordination feed is not a history.** Completed projects leave it, so the openings table cannot say how many blocks SFPUC or Public Works opened in earlier years, and the paving record is the only long series here.
- **A lever is not a commitment.** These miles are what repaving touched and left short; building the facility at that moment still needs design, outreach and an SFMTA hearing, and some plan corridors need more than a repave can carry.
