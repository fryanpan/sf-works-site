# The bike network by year, 2015–2026

Miles of bikeway, the miles that meet the Biking and Rolling Plan's all-ages test, and how many residents, K-12 schools (public and private) and library branches sit within a 0.25-mile walk of an all-ages segment. Generated 2026-11-20 by `scripts/bike-network-history.py`.

Every figure uses the [plan](https://www.sfmta.com/media/41810/download)'s definitions. **Miles are counted per direction row**, as SFMTA's bikeway layer holds them and as the plan's 472 miles (printed p. 20) are counted; a two-way street with a lane each way counts twice. **All-ages** is the plan's high-quality test (printed p. 24; [Appendix G](https://www.sfmta.com/media/41946/download)): Class I, Class IV and Slow Streets; Class II with Bike Comfort Index above 80; Class III with traffic calming and BCI above 80. The calming condition is in no published dataset and is not applied, so Class III rows are admitted on BCI alone; the third column is their size.

| Year | Network miles | All-ages miles | of which Class III by BCI alone | Residents within reach | K-12 schools within reach | Library branches within reach | Rests on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2015 | 440.7 | 130.0 | 5.5 | 63% (531,989 of 840,763) | 84 of 197 (43%) | 12 of 28 (43%) | INSTALL_YR only |
| 2016 | 443.6 | 135.0 | 6.7 | 66% (563,365 of 850,282) | 91 of 197 (46%) | 12 of 28 (43%) | INSTALL_YR only |
| 2017 | 447.7 | 145.0 | 8.1 | 68% (587,571 of 864,263) | 103 of 200 (52%) | 13 of 28 (46%) | INSTALL_YR only |
| 2018 | 448.1 | 154.4 | 10.9 | 70% (605,483 of 870,044) | 105 of 203 (52%) | 14 of 28 (50%) | INSTALL_YR only |
| 2019 | 454.5 | 162.5 | 11.4 | 72% (631,361 of 874,961) | 111 of 207 (54%) | 15 of 28 (54%) | INSTALL_YR only |
| 2020 | 456.7 | 210.6 | 12.1 | 81% (704,431 of 873,965) | 146 of 206 (71%) | 20 of 27 (74%) | INSTALL_YR only |
| 2021 | 463.3 | 224.8 | 12.2 | 81% (705,549 of 865,933) | 149 of 208 (72%) | 21 of 27 (78%) | archived snapshots |
| 2022 | 460.8 | 204.7 | 11.5 | 77% (659,210 of 851,036) | 138 of 209 (66%) | 19 of 27 (70%) | archived snapshots |
| 2023 | 463.3 | 216.0 | 13.1 | 79% (664,037 of 836,321) | 144 of 209 (69%) | 19 of 27 (70%) | archived snapshots |
| 2024 | 472.2 | 226.1 | 13.5 | 80% (667,445 of 830,235) | 151 of 218 (69%) | 20 of 27 (74%) | archived snapshots |
| 2025 | 471.8 | 228.3 | 14.0 | 80% (666,687 of 830,235) | 152 of 221 (69%) | 19 of 27 (70%) | archived snapshots |
| 2026 | 473.4 | 232.3 | 14.2 | 80% (664,379 of 830,235) | 153 of 221 (69%) | 19 of 27 (70%) | current |

Denominators: residents are every census block in San Francisco County; schools are K-12 schools, public ones of the counted types and private ones from DataSF, open on 09-01 of the year; libraries are SFPL branches plus the Main Library open that year.

## Reach at four distances

The table above uses the plan's quarter mile. The population-weighted average San Francisco block is 416 feet, intersection to intersection ([street centerlines](https://data.sfgov.org/d/3psu-pn9h), read 2026-11-10; [census blocks](https://data.sfgov.org/d/p2fw-hsrv); `scripts/sf-block-length.py`), so one block is taken as 440 feet and two as 880, Bryan's figures; the measured typical block is 416 feet.

| Year | Residents, Quarter mile | Residents, 1 block | Residents, 2 blocks | Residents, 1,000 feet | Schools, Quarter mile | Schools, 1 block | Schools, 2 blocks | Schools, 1,000 feet | Libraries, Quarter mile | Libraries, 1 block | Libraries, 2 blocks | Libraries, 1,000 feet |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | 63% | 31% | 50% | 55% | 84 of 197 | 29 of 197 | 59 of 197 | 65 of 197 | 12 of 28 | 1 of 28 | 10 of 28 | 10 of 28 |
| 2016 | 66% | 33% | 53% | 57% | 91 of 197 | 31 of 197 | 67 of 197 | 72 of 197 | 12 of 28 | 1 of 28 | 10 of 28 | 10 of 28 |
| 2017 | 68% | 36% | 55% | 60% | 103 of 200 | 35 of 200 | 74 of 200 | 81 of 200 | 13 of 28 | 1 of 28 | 10 of 28 | 10 of 28 |
| 2018 | 70% | 38% | 57% | 62% | 105 of 203 | 40 of 203 | 78 of 203 | 84 of 203 | 14 of 28 | 1 of 28 | 11 of 28 | 11 of 28 |
| 2019 | 72% | 40% | 60% | 65% | 111 of 207 | 43 of 207 | 81 of 207 | 87 of 207 | 15 of 28 | 1 of 28 | 12 of 28 | 12 of 28 |
| 2020 | 81% | 51% | 71% | 75% | 146 of 206 | 61 of 206 | 112 of 206 | 121 of 206 | 20 of 27 | 8 of 27 | 19 of 27 | 19 of 27 |
| 2021 | 81% | 54% | 72% | 76% | 149 of 208 | 64 of 208 | 116 of 208 | 125 of 208 | 21 of 27 | 8 of 27 | 20 of 27 | 20 of 27 |
| 2022 | 77% | 49% | 67% | 71% | 138 of 209 | 54 of 209 | 108 of 209 | 118 of 209 | 19 of 27 | 6 of 27 | 19 of 27 | 19 of 27 |
| 2023 | 79% | 52% | 69% | 73% | 144 of 209 | 59 of 209 | 113 of 209 | 122 of 209 | 19 of 27 | 6 of 27 | 19 of 27 | 19 of 27 |
| 2024 | 80% | 52% | 70% | 74% | 151 of 218 | 63 of 218 | 121 of 218 | 130 of 218 | 20 of 27 | 7 of 27 | 20 of 27 | 20 of 27 |
| 2025 | 80% | 52% | 70% | 74% | 152 of 221 | 64 of 221 | 122 of 221 | 131 of 221 | 19 of 27 | 8 of 27 | 19 of 27 | 19 of 27 |
| 2026 | 80% | 53% | 70% | 74% | 153 of 221 | 65 of 221 | 123 of 221 | 132 of 221 | 19 of 27 | 8 of 27 | 19 of 27 | 19 of 27 |

## Check against the plan's printed figures

The plan prints (p. 20, [primary — read 2026-09-22]) a network that "has grown from 302 miles in 2010 to 472 miles today", with "41 miles of protected bike lanes, 32 miles of Slow Streets, and seven miles of car-free streets"; p. 24 and Appendix G report 80% of residents within a quarter mile of a high-quality facility in early 2024. Against this table:

| Figure | Plan | This table | Note |
| --- | ---: | ---: | --- |
| Network miles | 472 | 473.4 (2026); 472.2 (2024) | live rows' geometry summed; the layer's own LENGTH column sums to 474.2 and LENGTH_FT to 470.9 |
| Protected (Class IV) miles | 41 | 50.5 (2024); 57.0 (2026) | SFMTA's blog gave 50 separated miles on 2026-05-28; counted once per block, 35.2 miles in 2024; 41.1 row miles in 2021; 3.0 miles carry no install year; 7.9 live miles are contraflow |
| Slow Street miles | 32 | 31.4 (2024) | the dataset's implemented segments sum to 15.7 centreline miles by their own geometry, counted in both directions as the plan does |
| Car-free miles | 7 | — | the bikeway layer has no car-free class; JFK Promenade and the Great Highway are Class I rows |
| Residents within a quarter mile, 2024 | 80% | 80% | the gap is taken up below |
| Residents in equity priority communities within a quarter mile, 2024 | 71% | — | not computed: no equity priority communities layer is catalogued in this repo (DataSF search 2026-09-22 found none) |

Protected miles: Counted once per block the 2024 figure falls below 41, so the unit does not explain the gap. Class IV row miles reached 41.0 at the end of 2021, the plan's figure exactly, and 42.1 in 2022, so a row sum taken from the layer as it stood in 2021 or 2022 gives the plan's number. The most consistent reading is that the plan's 41 was counted before its 2024 connectivity memo and not updated; SFMTA's May 2026 blog figure of 50 separated miles matches the layer's row sum for 2024. [inference — mine]


## Centreline miles, one length per block

For a reader who wants the network counted once per block rather than per direction row.

| Year | Network centreline miles | All-ages centreline miles | Direction rows | Blocks |
| --- | ---: | ---: | ---: | ---: |
| 2015 | 228.5 | 64.1 | 5,122 | 2,720 |
| 2016 | 230.2 | 66.9 | 5,176 | 2,749 |
| 2017 | 233.1 | 74.3 | 5,221 | 2,777 |
| 2018 | 233.6 | 80.5 | 5,227 | 2,783 |
| 2019 | 237.6 | 85.5 | 5,322 | 2,844 |
| 2020 | 239.1 | 111.4 | 5,351 | 2,863 |
| 2021 | 242.7 | 118.4 | 5,452 | 2,920 |
| 2022 | 241.5 | 108.5 | 5,444 | 2,917 |
| 2023 | 242.6 | 114.3 | 5,476 | 2,930 |
| 2024 | 245.2 | 117.9 | 5,526 | 2,946 |
| 2025 | 244.4 | 119.2 | 5,518 | 2,937 |
| 2026 | 244.5 | 120.9 | 5,558 | 2,948 |

## What each year rests on

| Year | Network figures | Population figures |
| --- | --- | --- |
| 2015 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | ACS 2011–2015 block-group totals, spread over 2010 blocks by their 2010 census shares |
| 2016 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | ACS 2012–2016 block-group totals, spread over 2010 blocks by their 2010 census shares |
| 2017 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | ACS 2013–2017 block-group totals, spread over 2010 blocks by their 2010 census shares |
| 2018 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | ACS 2014–2018 block-group totals, spread over 2010 blocks by their 2010 census shares |
| 2019 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | ACS 2015–2019 block-group totals, spread over 2010 blocks by their 2010 census shares |
| 2020 | existence from INSTALL_YR in the 2021-03-25 capture; class from that capture, moved back where UPDATE_YR says the change came later; blocks removed before 2021-03-25 are invisible | Census 2020 block counts (PL 94-171) |
| 2021 | bracketed by captures 2021-03-25 and 2022-12-09; changes inside the gap dated by UPDATE_YR where present | ACS 2017–2021 block-group totals, spread over 2020 blocks by their 2020 census shares |
| 2022 | bracketed by captures 2022-12-09 and 2024-03-31; changes inside the gap dated by UPDATE_YR where present | ACS 2018–2022 block-group totals, spread over 2020 blocks by their 2020 census shares |
| 2023 | bracketed by captures 2022-12-09 and 2024-03-31; changes inside the gap dated by UPDATE_YR where present | ACS 2019–2023 block-group totals, spread over 2020 blocks by their 2020 census shares |
| 2024 | bracketed by captures 2024-03-31 and 2025-12-08; changes inside the gap dated by UPDATE_YR where present | ACS 2020–2024 block-group totals, spread over 2020 blocks by their 2020 census shares |
| 2025 | bracketed by captures 2025-12-08 and 2026-02-15; changes inside the gap dated by UPDATE_YR where present | ACS 2020–2024 block-group totals, spread over 2020 blocks by their 2020 census shares; the 2020–2024 ACS is the latest released, so 2025 is held at it |
| 2026 | live layer as of 2026-11-10 (year to date) | ACS 2020–2024 block-group totals, spread over 2020 blocks by their 2020 census shares; the 2020–2024 ACS is the latest released, so 2026 is held at it |

Per-year notes on the network reconstruction (counts of blocks):

- 2015: class unknown before a later upgrade: 443; undated install, assumed present: 566
- 2016: class unknown before a later upgrade: 361; undated install, assumed present: 566
- 2017: class unknown before a later upgrade: 252; undated install, assumed present: 566
- 2018: class unknown before a later upgrade: 173; undated install, assumed present: 566
- 2019: class unknown before a later upgrade: 92; undated install, assumed present: 566
- 2020: class unknown before a later upgrade: 3; undated install, assumed present: 566
- 2021: INSTALL_YR predates a snapshot that lacks the block: 50; class changed between snapshots with no UPDATE_YR: 4; present earlier, gone later: counted through Y: 1; undated install, assumed present: 565
- 2022: INSTALL_YR predates a snapshot that lacks the block: 7; class changed between snapshots with no UPDATE_YR: 1; undated install, assumed present: 555
- 2023: INSTALL_YR predates a snapshot that lacks the block: 7; class changed between snapshots with no UPDATE_YR: 2; undated install, assumed present: 555
- 2024: INSTALL_YR predates a snapshot that lacks the block: 2; class changed between snapshots with no UPDATE_YR: 6; present earlier, gone later: counted through Y: 9; undated install, assumed present: 555
- 2025: class changed between snapshots with no UPDATE_YR: 1; undated install, assumed present: 555
- 2026: undated install, assumed present: 556

## All-ages miles, split

| Year | Bikeway rows all-ages | of which Class II by BCI | of which Class III by BCI | of which in the Presidio (federal land) | of which other paths with no CNN | Slow Street miles added on bikeway blocks (rows not already qualifying) | Slow Street miles not in the bikeway layer | Class I/IV and Slow Streets only (no BCI test) | Miles present but class unknown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | 130.0 | 39.2 | 5.5 | 25.5 | 27.7 | 0.0 | 0.0 | 85.3 | 54.5 |
| 2016 | 135.0 | 42.0 | 6.7 | 25.5 | 27.7 | 0.0 | 0.0 | 86.4 | 44.1 |
| 2017 | 145.0 | 44.8 | 8.1 | 25.5 | 27.7 | 0.0 | 0.0 | 92.1 | 31.4 |
| 2018 | 154.4 | 45.4 | 10.9 | 25.5 | 27.7 | 0.0 | 0.0 | 98.1 | 23.3 |
| 2019 | 162.5 | 46.2 | 11.4 | 25.5 | 27.7 | 0.0 | 0.0 | 104.9 | 13.3 |
| 2020 | 174.8 | 43.3 | 12.1 | 25.5 | 27.7 | 8.2 | 6.9 | 155.3 | 1.6 |
| 2021 | 185.4 | 46.3 | 12.2 | 25.5 | 27.7 | 8.9 | 9.2 | 166.2 | 0.0 |
| 2022 | 185.9 | 45.2 | 11.5 | 25.4 | 27.6 | 8.9 | 9.8 | 148.0 | 0.0 |
| 2023 | 192.6 | 44.5 | 13.1 | 25.4 | 27.6 | 9.0 | 14.4 | 158.4 | 0.0 |
| 2024 | 203.0 | 44.6 | 13.5 | 25.4 | 27.8 | 8.8 | 14.4 | 168.1 | 0.0 |
| 2025 | 205.4 | 44.5 | 14.0 | 25.4 | 27.8 | 8.5 | 14.4 | 169.8 | 0.0 |
| 2026 | 209.4 | 42.8 | 14.2 | 25.4 | 28.0 | 8.5 | 14.4 | 175.2 | 0.0 |

The layer carries 87 off-street paths with no street segment number (CNN): the Presidio's trails on federal land (NOTES says PRESIDIO), and paths elsewhere, named (Kirkham Path, SFSU Path, Vicente Path, Cesar Chavez St, San Jose Ave, McCoppin Stub Path) or unnamed. Both are in every figure above (INCLUDE_PRESIDIO is on); the Presidio column (every row whose NOTES says PRESIDIO, paths and signed routes alike) lets the all-ages figure be read without federal land. In 2026 the Presidio's bikeways are 50.8 of 473.4 network miles.

In 2026, 2.9 network miles lie on blocks the city's centerline has retired with no active block along the same line: Chain of Lakes Dr, Hunters Point Ex, Jamestown Ave, Terry Francois St, Twin Peaks Blvd. They keep SFMTA's line and lose the retired CNN, so no plan block can be marked built by them, and they are counted in every figure above but not in the paths column.

Network miles count the SFMTA bikeway layer only; Slow Street blocks outside that layer are added to all-ages miles and are not in the network total.

The step from 2015 to 2016, 130.0 to 135.0 all-ages miles, is 0.0 miles of Slow Streets and 5.0 miles of bikeway rows meeting the plan's test. 

The step from 2016 to 2017, 135.0 to 145.0 all-ages miles, is 0.0 miles of Slow Streets and 10.0 miles of bikeway rows meeting the plan's test. 

The step from 2017 to 2018, 145.0 to 154.4 all-ages miles, is 0.0 miles of Slow Streets and 9.4 miles of bikeway rows meeting the plan's test. 

The step from 2018 to 2019, 154.4 to 162.5 all-ages miles, is 0.0 miles of Slow Streets and 8.1 miles of bikeway rows meeting the plan's test. 

The step from 2019 to 2020, 162.5 to 210.6 all-ages miles, is 15.1 miles of Slow Streets and 12.3 miles of bikeway rows meeting the plan's test. The Slow Streets dataset dates its first segments to April 2020, the pandemic-era program, but it holds only the corridors that were kept when the SFMTA Board approved the permanent program (December 6, 2022 per [SFMTA's program page](https://www.sfmta.com/projects/slow-streets-program), read 2026-09-22; the Board record is [unretrieved — verify]). The barricade-era corridors removed before then are not in it, so the 2020 and 2021 all-ages figures are a floor. [inference — mine]

The step from 2020 to 2021, 210.6 to 224.8 all-ages miles, is 3.0 miles of Slow Streets and 10.6 miles of bikeway rows meeting the plan's test. 

The step from 2022 to 2023, 204.7 to 216.0 all-ages miles, is 4.7 miles of Slow Streets and 6.7 miles of bikeway rows meeting the plan's test. 

The step from 2023 to 2024, 216.0 to 226.1 all-ages miles, is -0.2 miles of Slow Streets and 10.4 miles of bikeway rows meeting the plan's test. 

## Where sources disagree

- The plan prints [472 miles](https://www.sfmta.com/media/41810/download) (p. 20, read 2026-09-22); SFMTA published [470 miles, 50 of them separated](https://www.sfmta.com/blog/safety-upgrades-make-difference-bike-ridership-rise) on 2026-05-28. Summing every live row's geometry gives 473.4 miles over 5,558 rows; the layer's `LENGTH` column sums to 474.2 and its `LENGTH_FT` column to 470.9, so the layer disagrees with itself by three miles. Counted once per block the network is 244.5 centreline miles over 2,948 blocks. **The table uses row miles from the geometry**, the plan's unit, and prints centreline miles beside them. [SFMTA ArcGIS — queried 2026-11-10]
- DataSF's [Schools](https://data.sf.gov/d/7e7j-59qk) lists 125 active public schools; the CDE archive gives 221 open on 2026-09-01 of the counted types. The table uses the CDE archive, because it carries closure dates; DataSF's count includes preschools, adult schools and other types the table leaves out. [DataSF 7e7j-59qk — queried 2026-11-05]

## Where the data no longer supports the analysis

- Before 2021-03-25 no archived copy of the layer exists. Years 2015–2020 rest on INSTALL_YR alone: a block installed before 2021 and removed before the first capture is invisible, a block whose class was upgraded with no UPDATE_YR is credited with its later class in every year back to its install, and 23% of the live layer's miles carry no INSTALL_YR at all and are assumed present throughout. Treat network miles in those years as a floor.
- All-ages miles before 2021 carry an uncertainty band of about ±32 miles in 2015, from two opposite errors. 54.5 miles have an unknown class in 2015 because UPDATE_YR is later and there is no earlier capture, and 31.5 of those are all-ages today, so the figure may be low by up to that much. In the other direction, 9.9 miles of CLASS IV are credited to 2015 by an INSTALL_YR of 2013 or earlier, before Caltrans defined Class IV (2014), so on those rows INSTALL_YR dates the street's first bikeway rather than the separated lane, and the figure may be high by up to that much. [inference — mine]
- Between captures a change is dated by UPDATE_YR when the row carries one; otherwise it is credited to the year before the later capture. The 2022-12-09 to 2024-03-31 and 2024-03-31 to 2025-12-08 gaps are the widest.
- Population for years other than 2020 is an ACS 5-year block-group estimate spread across blocks by census shares, so it is a five-year average, not a point count, and block-level shares are held at the nearest census. 2025 and 2026 are held at the 2020–2024 ACS, the latest released.
- The Slow Streets dataset was last loaded 2024-01-18 and carries no removal dates; the pandemic-era Slow Streets that were dropped in 2022 are not in it, and 7 segments (the SoMa streets) carry no install date and are counted from 2022. The dropped corridors are traced from SFMTA's 2020 and 2021 Board reports (scripts/lib/slow_corridors.py) and counted in the all-ages miles and the reach from their install year through 2021: 213 blocks, 21.2 all-ages miles in 2021 that no other all-ages line covered, adding 4.2 points of residents within a quarter mile in 2020. The reports give each corridor's extent as approved; where a corridor went in shorter, these years are high by the difference.
- The CDE directory is the 2025-10-05 archive capture, so schools opened or closed after that date are missing. School coordinates are CDE's; most schools closed before 2015 carry none, and the one school open in the window without one (Gateway to College, closed 2016) is left out.
- Library closures are entered by hand from SFPL's pages; only the Mission Branch's renovation closure is recorded. The system-wide COVID closure of March 2020 to May 2021 is not treated as a closure.
- The map lights a point in exactly the years it is within reach, so a point reached only through a dropped Slow Street or a removed bikeway goes grey when it went. In 2026, 246 blocks (35,369 residents at the 2020 count) and 3 branches that were within a quarter mile of an all-ages line in an earlier year are not.

## Sources

- Network: [SFMTA bikeway layer](https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0), attributes queried 2026-11-10, geometry queried 2026-11-10. Archived copies of [DataSF ygmz-vaxd](https://data.sf.gov/d/ygmz-vaxd) from the Internet Archive:
  - [2021-03-25](https://web.archive.org/web/20210325171932id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2870 blocks, 5,358 rows, 457.0 row miles (239.3 centreline)
  - [2022-12-09](https://web.archive.org/web/20221209021723id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2920 blocks, 5,454 rows, 463.8 row miles (242.7 centreline)
  - [2024-03-31](https://web.archive.org/web/20240331194201id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2944 blocks, 5,517 rows, 471.2 row miles (245.0 centreline), release loaded 03/23/2024 10:05:16 AM
  - [2025-12-08](https://web.archive.org/web/20251208144027id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2937 blocks, 5,511 rows, 471.1 row miles (244.4 centreline), release loaded 06/17/2025 01:45:07 PM
  - [2026-02-15](https://web.archive.org/web/20260215091752id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2937 blocks, 5,518 rows, 471.8 row miles (244.4 centreline), release loaded 02/14/2026 10:25:54 AM
  - [2026-04-05](https://web.archive.org/web/20260405114850id_/https://data.sfgov.org/api/views/ygmz-vaxd/rows.csv?accessType=DOWNLOAD): 2944 blocks, 5,526 rows, 472.1 row miles (244.7 centreline), release loaded 04/04/2026 10:30:27 AM
  - [2026-11-10](https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0): 2948 blocks, 5,558 rows, 473.4 row miles (244.5 centreline) (live layer)
- Slow Streets: [DataSF hkz3-itiu](https://data.sf.gov/d/hkz3-itiu), queried 2026-09-28; 218 implemented segments, 7 of them undated and counted from 2022.
- Population: 2010 blocks from [TIGERweb](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/18/query) (7,386 blocks, 805,235 people), queried 2026-09-22; 2020 blocks from [DataSF p2fw-hsrv](https://data.sf.gov/d/p2fw-hsrv) (5,986 blocks, 873,965 people), queried 2026-09-22; ACS 5-year block-group totals 2015–2024 from [data.census.gov](https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000), queried 2026-09-22 (county totals: 2015: 840,763, 2016: 850,282, 2017: 864,263, 2018: 870,044, 2019: 874,961, 2020: 874,784, 2021: 865,933, 2022: 851,036, 2023: 836,321, 2024: 830,235).
- Schools: [CDE Public Schools and Districts file](https://web.archive.org/web/20251005140551id_/https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=xlsx&ict=Y), 2025-10-05 capture from the Internet Archive (the [live download](https://www.cde.ca.gov/ds/si/ds/pubschls.asp) answers with a firewall challenge page), read 2026-09-22; 266 San Francisco rows. Counted types: Alternative Schools of Choice, Continuation High Schools, County Community, Elemen Schools In 1 School Dist. (Public), Elementary Schools (Public), High Schools (Public), Intermediate/Middle Schools (Public), Junior High Schools (Public), Juvenile Court Schools, K-12 Schools (Public), Opportunity Schools, Special Education Schools (Public). Left out by type: Adult Education Centers (7), No Data (10), Other County Or District Programs (3), Preschool (12), ROC/ROP (1), Youth Authority Facilities (1). 102 rows of a counted type lack a coordinate or an open date; 1 of those were open in the window and are left out: Gateway to College.
- Libraries: [DataSF nc68-ngbr City Facilities](https://data.sf.gov/d/nc68-ngbr), queried 2026-09-22; 28 branches including the Main Library. Not counted: SFPL Book Stop kiosks (Treasure Island, Dogpatch, Sunnydale) and the Mission temporary site. Closures: Mission Branch Library closed from 2020, not yet reopened ([SFPL](https://sfpl.org/releases/2022/06/13/san-francisco-public-library-opens-new-temporary-library-site-mission-saturday)).
- Bike Comfort Index: [2023 Draft Bike Comfort Index, Toole Design / SFMTA](https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4), 15280 segments, queried 2026-10-04; field `bci`, threshold 80. One 2023 snapshot, labelled draft; held fixed for every year. The combined `bci` is the lower of the two directional scores (`bci_ft`, `bci_tf`) on 13,192 of 15,280 segments, so it is the stricter reading; 194 live Class II/III rows (16.1 miles) would change verdict under one directional score in its place. 31 bikeway blocks with Class II/III rows carry no score (50 rows, 2.7 miles) and are counted as not qualifying.
- Direction rows: 300 live blocks (26.4 row miles) are held as one row marked two-way (DIRECT=2W): CLASS I 7, CLASS II 119, CLASS III 122, CLASS IV 52. Row counting gives each one length where a street with a lane each way gets two; it is kept because it reproduces the plan's 472.

## Method

- **definitions**: plan: The Biking and Rolling Plan's high-quality test (printed p. 24; Appendix G, Toole Design connectivity memo of 2024-02-13): Class I, Class IV and Slow Streets; Class II with Bike Comfort Index above 80; Class III with traffic calming and BCI above 80. A direction row qualifies by its own class; a Class II or III row qualifies when its block's 2023 Draft BCI (bci) clears 80. BCI is one 2023 snapshot held fixed for every year. A Class III row also needs traffic calming on its block by that year, read from DataSF abhw-ffzx (mid-block) and bp3t-bd4t (intersection devices at either end of the block); class_iii_calm_street_no_calming_miles is what that condition removes.; strict: Class I, Class IV and Slow Street rows only, no BCI test. Written as all_ages_strict_miles; no page shows it.; default: plan
- **all_ages**: A direction row is all-ages when it is CLASS I or CLASS IV, or CLASS II or CLASS III on a block whose BCI is above 80, or on an implemented Slow Street from its install year. A block is within reach of a point when any of its rows qualifies.
- **year_state**: A block's class in year Y is its class in the nearest archived copy captured after the end of Y, unless UPDATE_YR says the change came after Y, in which case it is the class in the nearest earlier copy, or unknown when there is none. A block exists in Y when INSTALL_YR is Y or earlier, or blank. A block in the earlier copy and gone from the later one is counted through Y.
- **miles**: Row miles, the plan's unit: every direction row's length, summed, so a two-way street with a lane each way counts twice. A live row is measured from its own line geometry (equirectangular projection about 37.76 N); an archived row on a block still in the layer at the live layer's mean row length for that block, since the archived exports keep no geometry for those; an archived row on a block since dropped from its own geometry. Slow Street blocks outside the bikeway layer count their length 2 times. Centreline miles, one length per block, are written beside every row-mile figure. Off-street paths with no CNN (Presidio trails, Golden Gate Park, Kirkham, SFSU and other paths) are keyed by their endpoints and counted; the Presidio's are also shown separately.
- **gap_fill**: A block present in an earlier and a later capture but missing from one between is carried through the gap with its earlier record.
- **timing**: Network state is the end of the year (or the latest capture for the current year); schools and libraries are counted as open on 09-01 of the year.
- **reach**: Walking distance along OpenStreetMap's walk network (OSMnx's walk filter plus cycle paths; see site/data/bike-history/walk-reach.json for the copy read) from the census block's interior point, the school's CDE coordinate or the branch's City Facilities coordinate to the nearest all-ages line, at most 0.25 miles by default; the point joins the network at the nearest street or path in a straight line, and a line is reached where it passes within 20 m of a walkable way (scripts/walknet.py). reach_thresholds names the shorter distances the overview also offers. The lines reached include the pandemic Slow Street blocks SFMTA dropped in December 2022, from their corridor's install year through 2021, as the miles do (reach_without_dropped_slow_streets on each row gives the figures without them).
- **reach_thresholds**: Four distances, the plan's quarter mile (402 m) by default, one and two city blocks (440 and 880 feet), and 1000 feet, about the 300 m walk to a protected bikeway the ITDP Atlas of Sustainable City Transport measures. The population-weighted average block, intersection to intersection on the street centerline over 240 tracts, is 416 feet (scripts/sf-block-length.py, https://data.sfgov.org/d/3psu-pn9h, read 2026-11-10), so one block is taken as 440 feet and two as 880, Bryan's figures; the measured typical block is 416 feet. Each row's reach_by_threshold carries the six reach figures at each.
- **population_denominator**: Every block in San Francisco County, including Treasure Island and the Farallones.
- **school_denominator**: K-12 schools: public schools of the counted types (see sources.schools) open on 09-01 of the year, by CDE OpenDate and ClosedDate, plus DataSF's active private elementary, high and K-12 schools from their open_date (a private school that closed earlier is missing). Charter schools are included (14 of the 221 open in 2026), as is the County Community school run in the county jail (1).
- **library_denominator**: SFPL branches plus the Main Library in City Facilities, minus branches closed for renovation that year.
