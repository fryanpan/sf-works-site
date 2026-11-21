# Safe Streets: Injury Data Dive

It holds the full injury investigation from the injury map mockup, its source notes and the numbers behind every chart, plus the survey and budget notes, the search results on whether Vision Zero failed, and the open questions from the mockup's comment threads.

It is raw. Figures keep the source links and provenance tags the page or note gave them. The page is `scratch/hin-map/index.html`, built by `scratch/hin-map/build.mjs` from `scratch/hin-map/data.json`, rendered and read 2026-10-20. Chart tables below come from `data.json`. Footnote numbers match the page's own numbered notes, collected in [Source notes from the page](#source-notes-from-the-page) at the end.

## Goals

## Headline

**Three in Four People Hurt in San Francisco Traffic Are Hurt on Main Roads**

Injuries to people walking fell 34% near the speed cameras and 12% near the 31 rebuilt corridors against the rest of the city, but neither can yet be told from chance once every row is tested, and injuries overall barely moved.

| Stat | Figure |
|---|---|
| People injured or killed in reported crashes, September 2021 to August 2026 | 18,523[^1] |
| On main roads | 13,834, 75% of everyone hurt[^2] |
| On the High Injury Network | 11,847, 64% of people hurt, on 15% of street miles, and 76% of those hurt on main roads[^3] |

These are police reports, and they miss four to six of every ten severe injuries. In the year from April 2014 San Francisco Department of Public Health (SFDPH) counted 515 patients with severe traffic injuries at the city's trauma center against "~200 SFPD reported Severe Injuries", and its 2013 to 2015 record match found 59% in both records.[^4] The people the reports miss are "more often cyclists, male, Hispanic or Black", and "more than three in 10 non-fatal injuries with a critical ISS were missed (i.e. reported as non-severe)".[^5]

So the map shows where police wrote reports. A street where people fall off bikes alone, or crash without calling police, is drawn lighter than it should be. Severe injuries are counted more completely than minor ones, so the "Severe and fatal" view is the firmer one.[^6]

## About 3,650 People a Year Are Still Hurt, 81% of 2005's Level

Each point is everyone reported hurt or killed that year, from police crash reports.[^7] 4,458 people were hurt in 2005 and 3,604 in 2025, while the number severely hurt or killed went from 218 to 274. The numbered lines are when the city started major programs, not proof they caused what follows, and part of the rise in severe injuries from 2015 is a change in how police record them. Since 2020 the drop is in minor injuries, most at weekday commute hours, while severe injuries held. Less driving, fewer people walking and biking, and a change in what gets reported could each explain part of it, and the data can't yet say which matters most. [inference — mine] San Francisco County Transportation Authority (SFCTA) puts San Francisco's vehicle miles "around 10% below pre-COVID levels" in 2025.[^8][^9]

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), 2005 to August 2026. Severe means "Severe Injury" or "Fatal Injury".

| Year | People hurt or killed | Severely hurt or killed | Killed |
|---|---|---|---|
| 2005 | 4,458 | 218 | 27 |
| 2006 | 3,836 | 202 | 30 |
| 2007 | 3,999 | 243 | 42 |
| 2008 | 3,891 | 225 | 27 |
| 2009 | 3,733 | 235 | 31 |
| 2010 | 3,964 | 212 | 22 |
| 2011 | 3,869 | 225 | 28 |
| 2012 | 4,046 | 233 | 29 |
| 2013 | 3,884 | 231 | 34 |
| 2014 | 3,704 | 234 | 31 |
| 2015 | 3,811 | 261 | 31 |
| 2016 | 4,186 | 307 | 29 |
| 2017 | 4,273 | 281 | 20 |
| 2018 | 4,142 | 306 | 23 |
| 2019 | 4,397 | 336 | 29 |
| 2020 | 2,993 | 256 | 30 |
| 2021 | 3,517 | 298 | 27 |
| 2022 | 3,669 | 321 | 39 |
| 2023 | 3,733 | 261 | 26 |
| 2024 | 3,757 | 341 | 43 |
| 2025 | 3,604 | 274 | 25 |
| 2026 (Jan to Aug) | 2,598 | 209 | 18 |

Program dates marked on the chart:

- **2014, Vision Zero adopted**, a goal of no traffic deaths by 2024: the SFMTA Board on February 4 ([calendar item 10](https://www.sfmta.com/media/3961/download)) and the Board of Supervisors on March 18 ([file 140047](https://sfgov.legistar.com/LegislationDetail.aspx?ID=1634176&GUID=94A42CE6-CD8A-4302-94C2-0DA45058FE9D)). [primary — read 2026-10-20]
- **2015, first High Injury Network:** "In 2015 all three corridor maps were combined and presented as the Vision Zero High Injury Network" (SFDPH, [2022 Network Update Methodology](https://www.visionzerosf.org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf)). [primary — read 2026-10-20]
- **2019, quick-builds:** Mayor Breed's challenge of March 6, 2019 and SFMTA Board legislation that June "to enable streamlined project delivery" ([SFMTA Board slides, May 2021](https://www.sfmta.com/media/26900/download)). [primary — read 2026-10-20] The chart's bar spans our 31 corridors' completions, June 2018 to December 2024.
- **2022, 20 mph law:** State law AB 43 lets the city post 20 mph on more streets, from January 2022 ([SFMTA, October 2021](https://www.sfmta.com/node/25172)). [primary — read 2026-10-20] The SFMTA Board posted 588 blocks at 20 mph, 32 miles on 58 streets, from April 2022 to September 2025, 408 of them in 2022. The bar spans those Board dates. [DataSF 3t7b-gebn — queried 2026-10-16] The data gives Board dates, not the day signs went up, and not the old limit. [inference — mine]
- **2025, speed cameras:** "launched on March 20", warnings at every camera by June 6 and citations from August 5, 2025 ([SFMTA](https://www.sfmta.com/projects/speed-safety-cameras)). [primary — read 2026-10-20]

## Where people get hurt

The heat map is every reported injury from September 2021 to August 2026. Freeways like 101 and 280 aren't included, because the city's data leaves out crashes on highways. Under it sits the [2022 High Injury Network](https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/hin2022/FeatureServer/0). Fix layers can be ticked on, built or planned.[^10]

Map views and layers, as the page lists them:

| Layer | What it draws | Source |
|---|---|---|
| All reported injuries | Heat map, scaled to its own busiest spot | [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), read 2026-10-20, crashes to 2026-08-31. 17 injuries with no street within 150 ft not shown |
| Severe and fatal only | Same, severe and fatal | Same |
| Kids on school trips | The 463 people aged 5 to 17 hurt on a weekday between 6 AM and 6 PM, holidays and summer included, no-age victims left out. Squares are the 113 schools in our School Trips tool | Same |
| Quick-build corridors, 2018 to 2024 | The 31 corridors in the fixes section | SFMTA project pages |
| Speed cameras, 2025 | The 33 locations | [d5uh-bk84](https://data.sfgov.org/d/d5uh-bk84) |
| 20 mph streets, 2022 on | Blocks with a Board date from 2022 on | [3t7b-gebn](https://data.sfgov.org/d/3t7b-gebn) |
| Daylighting and painted safety zones | Tenderloin daylighting area as a dashed box | [vtn2-q8ky](https://data.sfgov.org/d/vtn2-q8ky) |
| Slow Streets | | [hkz3-itiu](https://data.sfgov.org/d/hkz3-itiu) |
| Speed humps and other calming, 2016 on | Installed from 2016 on or pending | [abhw-ffzx](https://data.sfgov.org/d/abhw-ffzx) and [bp3t-bd4t](https://data.sfgov.org/d/bp3t-bd4t) |
| Planned: quick-builds, safety and traffic calming, bike lanes and Slow Streets, signal work, streetscapes and area plans | Planned SFMTA projects. A cost shows only where SFMTA or SFCTA published one | SFMTA's project layer |

### Main Roads Account for 75% of the People Hurt

| Kind of street | Examples | People injured or killed, Sept 2021 to Aug 2026 |
|---|---|---|
| Main roads | 19th Ave, Geary Blvd, 3rd St | 13,834 (75%) |
| Residential streets | Sacramento St, Anza St | 4,588 (25%) |

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) and [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h). Not drawn: 101 people at ramps, freeway mouths and private or paper streets. Main roads are classes 2 to 4 of the city's street classification on the centerline layer.

By class, from `data.json` (main road miles 295.6 of 1,040.3 street miles, High Injury Network 159.5 miles):

| Street class | People hurt | Of whom severely hurt or killed | Street miles |
|---|---|---|---|
| Major street or highway | 1,251 | 110 | 18.0 |
| Arterial street | 6,176 | 498 | 117.0 |
| Collector street | 6,407 | 504 | 160.7 |
| Residential street | 4,588 | 372 | 744.5 |
| Freeway | 73 | 9 | 0 |
| Freeway ramp | 7 | 0 | 0.0 |
| Other (private, paper street) | 21 | 6 | 0.1 |

### Seven in Ten People Hurt on Main Roads Are Hurt at an Intersection

The report says whether a crash was within 20 ft of an intersection, and everything else counts as midblock.[^11] On either kind of street most people hurt are hurt at an intersection, whichever street a corner crash is given to.[^12]

| Kind of street | Where | People hurt (share of that street kind) | Of whom severely hurt or killed |
|---|---|---|---|
| Main roads | At the intersection, within 20 ft | 9,782 (71%) | 752 |
| Main roads | Midblock | 4,052 (29%) | 360 |
| Residential streets | At the intersection, within 20 ft | 2,660 (58%) | 188 |
| Residential streets | Midblock | 1,928 (42%) | 184 |

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), September 2021 to August 2026.

### If You Took One Trip by Each Mode, How Likely Would You Be To…

Compared with a Muni trip, a bike trip is 12 times as likely to get you hurt, a car trip 2.4 times and a walk 2.2 times, and a car trip is 41 times as likely to hurt someone else.[^13] Commuting for a year, about 500 trips, the chance of being hurt is about 1 in 210 by bike, 1 in 1,100 by car and 1 in 1,200 on foot. Each bar compares a trip by that mode with a Muni trip, using people per 10 million trips from five years of police reports, and federal transit safety reports for Muni riders hurt, against SFMTA's count of trips.[^14]

Chart values, compared with a Muni trip (Muni = 1x):

| Mode | Be in a crash | Get hurt or killed | Hurt someone else |
|---|---|---|---|
| Walking | 5.7x | 2.2x | 0.7x |
| Biking | 32x | 12x | 11x |
| Car or truck | 13x | 2.4x | 41x |
| Muni or other transit | 1x | 1x | 1x |

Counts behind it, September 2021 to August 2026, from `data.json`. Crash parties count a vehicle once however many ride. "Hurt others" is people hurt in a crash where a party of that mode was the only one at fault, other than that party and its passengers. Deaths carry an exact Poisson 95% range.

| Mode | Crash parties | People hurt | Of whom severe | Hurt others | Killed | Killed, 95% range |
|---|---|---|---|---|---|---|
| Walking | 3,374 | 3,307 | 509 | 65 | 91 | 73.3 to 111.7 |
| Biking | 2,388 | 2,271 | 262 | 126 | 9 | 4.1 to 17.1 |
| Car or truck | 19,332 | 9,417 | 286 | 9,692 | 30 | 20.2 to 42.8 |
| Motorcycle or moped | 1,800 | 1,724 | 256 | 97 | 21 | 13.0 to 32.1 |
| Muni or other transit | 248 | 191 | 1 | 38 | 1 | 0.0 to 5.6 |
| Scooter or board | 1,419 | 1,334 | 180 | 108 | 8 | 3.5 to 15.8 |

Gap: the people-per-10-million-trip rates behind the ratios are not stored in `data.json` and the page does not print them. The Muni "get hurt" count is the federal figure (95 major plus 521 non-major events, scaled from 58 months to the window), and the scaled number is not printed either.[^14]

Of the 2,271 people hurt biking, a driver was at fault for 998 and a parked car, mostly an opened door, for 40 more, the rider for 885 and no one for 282. 41% were broadside crashes and 20% sideswipes.[^15] 33% were hurt on a block with a bike lane or path, not counting shared lane markings, which covers 11% of street miles, most likely because that's where people ride. [inference — mine][^16] Per mile instead of per trip, biking stays riskier than walking unless the average bike trip is more than 5.5 times as long as a walk, and no San Francisco trip length by mode was opened. [inference — mine]

Car, truck or motorcycle at fault, by type, people hurt outside it. Counts, not chances per trip, because the trip survey doesn't count trips by vehicle type.[^17]

| At-fault vehicle | People hurt outside it | Of whom severe |
|---|---|---|
| Passenger car | 5,525 | 294 |
| SUV | 2,617 | 152 |
| Pickup, van or minivan | 873 | 54 |
| Truck, bus or commercial | 403 | 15 |
| Motorcycle or moped | 95 | 4 |

Police-reported crashes only, so the real chances are higher, especially for walking and biking, where many injuries never reach a police report. Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) and [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6), September 2021 to August 2026, and SFMTA [Travel Decision Survey 2021](https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf).

### Drivers at Fault Hurt 2,073 People Walking and 1,034 People Biking

Where the officer marked one party at fault, a driver was at fault for 2,073 of the 3,307 people hurt walking and 1,034 of the 2,271 hurt biking.[^18] Of the 1,011 people hurt where a cyclist was at fault, 885 were the rider and 65 were people walking. The police most often blamed unsafe speed (285), running a red light (167), an unsafe turn or lane change (90), riding on the wrong side or against traffic (89) and running a stop sign (53).[^19]

People hurt, with severely hurt or killed in parentheses (the page shows the severe count on hover):

| At fault | Walking hurt | Biking hurt | Scooter or board hurt | In a vehicle hurt |
|---|---|---|---|---|
| Driving a car, truck or motorcycle | 2,073 (264) | 1,034 (73) | 429 (39) | 10,394 (491) |
| Muni or other transit | 7 (1) | 4 (0) | 1 (0) | 34 (1) |
| Biking, the rider hurt | 0 (0) | 885 (140) | 0 (0) | 0 (0) |
| Biking, others hurt | 65 (10) | 23 (3) | 16 (3) | 22 (1) |
| Scooter or board | 68 (12) | 21 (1) | 692 (105) | 14 (1) |
| Walking | 821 (186) | 17 (3) | 9 (1) | 23 (2) |
| No one at fault, or unknown | 273 (36) | 287 (42) | 187 (32) | 1,124 (52) |

### Cyclists Blamed for Their Own Injuries Rose From 163 to 220 a Year

Police marked the person hurt as the one at fault for 885 people biking and 805 people walking in five years. 203 of the cyclists crashed with no one else involved, while all but 2 of the walkers were hit by a vehicle.[^20] The causes police named most for the cyclists were unsafe speed (264), a red light (140), an unsafe turn or lane change (82), riding against traffic or on the wrong side (73) and a stop sign (52). For the walkers they were crossing outside a crosswalk (317), a red or don't-walk signal (193), crossing between signals (156) and stepping suddenly into a vehicle's path (81).[^21] Only 36 of the cyclists' crash reports name a road problem such as a pothole, loose material or a work zone (23 of the 203 solo crashes), and police reports miss many solo bike falls.[^22]

People hurt a year who were themselves marked at fault, years September to August:

| Year | Biking, with someone else | Biking, no one else involved | Biking, total | Walking |
|---|---|---|---|---|
| 2021-22 | 120 | 43 | 163 | 158 |
| 2022-23 | 123 | 30 | 153 | 164 |
| 2023-24 | 140 | 26 | 166 | 164 |
| 2024-25 | 135 | 48 | 183 | 157 |
| 2025-26 | 164 | 56 | 220 | 162 |

### One Trip by Any Mode Carries a Death Risk Hundreds of Times Smaller Than a Skydiving Jump

Per trip in San Francisco the chance of being killed is about 0.047 micromorts walking, 0.038 biking, 0.0061 by car and 0.0013 on Muni, against 8 for a skydiving jump and 22 for one ordinary day of living in the US.[^23] Walking and biking carry 6 to 8 times the risk of a car trip, but every mode sits far below risks people accept every day, which may be part of why there is little pressure for progress. [inference — mine] Across all modes that comes to 0.020 micromorts a trip, about a fifth of the US rate for 1999 to 2003, which counts freeways and rural roads.[^24]

| Activity | Micromorts |
|---|---|
| A day of living, US | 22 |
| A skydiving jump | 8 |
| A day, non-natural, US | 1.6 |
| A 1,000-mile flight | 1 |
| Smoking one cigarette | 0.71 |
| Radiation, 2,500-mile flight | 0.42 |
| A glass of wine | 0.30 |
| A 3-mile bike ride, UK | 0.068 |
| A 1-mile walk, UK | 0.033 |
| A 10-mile drive, UK | 0.027 |
| A charcoal-grilled steak | 0.010 |
| **A walk, SF** | **0.047** (0.0382 to 0.0582) |
| **A bike trip, SF** | **0.038** (0.0172 to 0.0713) |
| **A car trip, SF** | **0.0061** (range not printed. Deaths 30, range 20.2 to 42.8) |
| **A Muni trip, SF** | **0.0013** (0.0000 to 0.0070) |

The SF ranges for walk, bike and Muni are from the micromort cross-check below. The page draws a range for the car trip but its value is not printed or stored, so it is a gap here.

#### Micromort cross-check

A cross-check (read 2026-10-20) checked the per-trip rates against published ones. Deaths by own mode from nwes-mmgh, September 2021 to August 2026, over Travel Decision Survey 2021 trips (4,380,121 a day times share times 365 times 5.00 years), exact Poisson 95% range.

| Mode | Killed | SF micromorts per trip (95% range) | UK per mile ([Micromort](https://en.wikipedia.org/wiki/Micromort), from GOV.UK Reported road casualties GB 2024) | Miles a trip needs to match the UK rate |
|---|---|---|---|---|
| walk | 91 | 0.0474 (0.0382 to 0.0582) | 0.0333 | 1.4 |
| bike | 9 | 0.0375 (0.0172 to 0.0713) | 0.0227 | 1.7 |
| drive | 51 | 0.0103 (0.0077 to 0.0135) | 0.0027 | 3.8 |
| transit | 1 | 0.0013 (0.0000 to 0.0070) | 0.0002 (train, as a stand-in for Muni) | 7.5 |

All modes: 160 killed over 7,992 million trips is 0.020 micromorts a trip. US, all modes, 1999 to 2003: "10.4 per 100 million person-trips", 0.104 (Beck, Dellinger and O'Neil 2007, [American Journal of Epidemiology 166(2):212](https://academic.oup.com/aje/article/166/2/212/98939), abstract). [primary — read 2026-10-20] SF is 0.19 of the US rate.

The two sources disagree on the car row. The cross-check counts 51 drive deaths, motorcycles included, for 0.0103 and a 3.8-mile match. The page drops the 21 motorcycle and moped deaths because there is no trip count for them, so it uses 30 deaths, 0.0061, and a 2.2-mile match.[^23][^24] The page figure is the one with a matching denominator. [inference — mine]

What the cross-check found [inference — mine]:

- Walk, bike, car: the per-trip rates equal the UK per-mile rate over plausible trip lengths for a dense city. No average SF trip length by mode was opened, so this is a plausibility check, not a match.
- All modes against the US: SF is about a fifth. Likeliest reasons are freeways left out of the SF data, slow dense SF streets against a national mix with rural high-speed roads, higher US death rates per mile in 1999 to 2003, and a denominator that counts the out-of-city legs of trips while the deaths are inside SF only.
- Muni: one death in five years, so the range spans more than two orders of magnitude. The train comparison is only a stand-in.
- Not found or not opened: US per-mode per-trip rates (Beck's full table, Pucher and Buehler), NHTS trip lengths.

### Unsafe Speed Is the Cause Police Name Most Often

Each crash report names one primary collision factor, the vehicle code section the officer judges the at-fault party broke.[^25] That is the officer's judgment of the main cause, not a measured speed, and "unsafe speed" is the code's "Unsafe speed for prevailing conditions".[^26] Where a driver was at fault, unsafe speed is still the most common of the causes we name, for 2,727 people (20%).

| Cause | Main roads, people hurt (share) | Main roads, severe | Residential, people hurt (share) | Residential, severe |
|---|---|---|---|---|
| Unsafe speed | 2,554 (18%) | 215 | 876 (19%) | 99 |
| Running a red light | 1,891 (14%) | 164 | 242 (5%) | 20 |
| Not yielding to a person in a crosswalk | 993 (7%) | 105 | 413 (9%) | 35 |
| Not yielding while turning left | 951 (7%) | 60 | 209 (5%) | 13 |
| Running a stop sign | 318 (2%) | 11 | 424 (9%) | 19 |
| Unsafe turn or lane change | 1,542 (11%) | 73 | 386 (8%) | 25 |
| Following too closely | 802 (6%) | 12 | 134 (3%) | 6 |
| Driving under the influence | 393 (3%) | 46 | 136 (3%) | 11 |
| Pedestrian violation | 683 (5%) | 148 | 193 (4%) | 39 |
| Every other cause | 2,984 (22%) | 192 | 1,333 (29%) | 83 |
| Unknown or not stated | 723 (5%) | 86 | 242 (5%) | 22 |

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), September 2021 to August 2026. Main roads 13,834 people, residential streets 4,588.

### Injuries Peak at 5 PM on Weekdays, and After 10 PM One in 9 Is Severely Hurt or Killed

Each line is people hurt per weekday or per weekend day, by the hour of the crash on the report.[^27] From 10 PM to 6 AM, 393 of 3,426 people hurt (11%) were severely hurt or killed, against 830 of 12,018 (7%) from 7 AM to 7 PM. Weekdays peak at 0.83 a day at 5 PM and weekends at 0.69 a day at 6 PM.

Counts by hour. Divide by 1,304 weekdays or 522 weekend days for the page's per-day rate. 10 people with no time are left out.

| Hour | Weekday, hurt | Weekday, severe | Weekend, hurt | Weekend, severe |
|---|---|---|---|---|
| 12 AM | 232 | 34 | 257 | 31 |
| 1 AM | 210 | 29 | 245 | 29 |
| 2 AM | 168 | 17 | 279 | 28 |
| 3 AM | 126 | 13 | 133 | 12 |
| 4 AM | 100 | 16 | 66 | 6 |
| 5 AM | 143 | 25 | 58 | 8 |
| 6 AM | 302 | 33 | 78 | 6 |
| 7 AM | 517 | 40 | 91 | 4 |
| 8 AM | 740 | 50 | 111 | 10 |
| 9 AM | 640 | 41 | 151 | 8 |
| 10 AM | 569 | 39 | 189 | 7 |
| 11 AM | 568 | 33 | 227 | 18 |
| 12 PM | 633 | 40 | 248 | 25 |
| 1 PM | 701 | 40 | 270 | 30 |
| 2 PM | 771 | 57 | 290 | 20 |
| 3 PM | 965 | 58 | 337 | 18 |
| 4 PM | 968 | 50 | 320 | 28 |
| 5 PM | 1085 | 76 | 343 | 29 |
| 6 PM | 925 | 79 | 359 | 30 |
| 7 PM | 670 | 61 | 301 | 17 |
| 8 PM | 581 | 49 | 290 | 24 |
| 9 PM | 589 | 65 | 258 | 19 |
| 10 PM | 526 | 54 | 255 | 18 |
| 11 PM | 402 | 50 | 226 | 23 |

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), September 2021 to August 2026, all 18,523 people hurt.

## Did the fixes work?

Injuries to people walking within two blocks fell 34% at the speed camera locations and 12% near the 31 quick-build corridors against the rest of the city, with no such drop in the years before, but neither passes once we allow for testing 14 rows at once. The other fixes either can't be told apart from chance yet or followed a spike that would have fallen back anyway. Even the best of these is small next to the about 3,650 people hurt a year citywide from 2021 to 2025.[^28] The city's own evaluations compare each project's street with itself and use no comparison streets.[^29] See [How Sure Are We](#how-sure-are-we).

The 14 chart rows, from the pooled rows in `data.json`. Change is against the rest of the city. "Years before" is the same comparison one window earlier, before any work. Every row on the page reads "no clear drop".

| Fix | Row | People hurt, before → after | Change | 95% range | p (uncorrected) | Years before, change (range) |
|---|---|---|---|---|---|---|
| 33 speed camera locations (2025) | Everyone, at the site | 167 → 139 | −18% | −39% to +10% | 0.191 | −9% (−31% to +21%) |
| 33 speed camera locations (2025) | People walking, at the site | 31 → 20 | −31% | −62% to +19% | 0.197 | +20% (−30% to +109%) |
| 33 speed camera locations (2025) | Everyone, site plus two blocks | 682 → 600 | −13% | −25% to +1% | 0.057 | +7% (−7% to +23%) |
| 33 speed camera locations (2025) | People walking, site plus two blocks | 115 → 71 | −34% | −52% to −12% | 0.007 | +12% (−17% to +50%) |
| 31 quick-build and near-term corridors (2018 to 2024) | Everyone, at the site | 1,506 → 1,407 | 0% | −9% to +9% | 0.925 | −5% (−13% to +4%) |
| 31 quick-build and near-term corridors (2018 to 2024) | People walking, at the site | 356 → 258 | −14% | −28% to +1% | 0.067 | +6% (−9% to +24%) |
| 31 quick-build and near-term corridors (2018 to 2024) | Everyone, site plus two blocks | 3,769 → 3,600 | +1% | −4% to +7% | 0.600 | −2% (−7% to +4%) |
| 31 quick-build and near-term corridors (2018 to 2024) | People walking, site plus two blocks | 864 → 651 | −12% | −20% to −2% | 0.018 | +5% (−4% to +15%) |
| Tenderloin quick-builds (2019 to 2022) | Everyone, at the site | 204 → 204 | +4% | −15% to +30% | 0.713 | −9% (−27% to +14%) |
| Tenderloin quick-builds (2019 to 2022) | People walking, at the site | 94 → 74 | −13% | −37% to +18% | 0.392 | +9% (−17% to +45%) |
| Tenderloin quick-builds (2019 to 2022) | Everyone, site plus two blocks | 638 → 591 | −4% | −15% to +8% | 0.508 | +9% (−4% to +23%) |
| Tenderloin daylighting (2015) | Everyone, at the site | 674 → 586 | −20% | −30% to −8% | 0.002 | +23% (+5% to +43%) |
| Tenderloin daylighting (2015) | People walking, at the site | 254 → 251 | −2% | −18% to +17% | 0.800 | +18% (−3% to +43%) |
| Tenderloin daylighting (2015) | Everyone, site plus two blocks | 1,191 → 1,147 | −11% | −20% to −2% | 0.026 | +6% (−5% to +18%) |

Source: DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) to 2026-08-31. The daylighting rows are Tenderloin-wide, after a 2013 and 2014 spike, and injuries to people walking there didn't change (−2%). Rows with under 20 people hurt in either window are left out. People biking aren't charted. Within two blocks of the corridors their injuries went from 613 to 475, −11% against the rest of the city (p = 0.04), which wouldn't pass the correction for many rows. Two blocks means two steps out along the centerline from each site intersection, the next block along the street and on each cross street and then one more, so downtown, where alleys split blocks, two steps can be one real block. Measured against the surrounding blocks (three to eight blocks out) instead of the whole city, the four pooled changes move by at most 6 percentage points.

### What SFMTA says about each fix

| Fix | SFMTA's claim |
|---|---|
| 33 speed camera locations (warnings April to June 2025, citations from August 2025, about 1.3 years each side) | Speeding 10 mph or more over the limit "is down nearly 80 percent across camera locations". No injury result yet.[^30] |
| 31 quick-build and near-term corridors (completed 2018 to 2024, 3 years each side where the data allows) | Across 27 of its 34 projects, all collisions "fell by 2%", pedestrian collisions 32% and bike collisions 15%. We matched 31 of the 34 to a street extent and a date.[^31] |
| Tenderloin quick-builds (Golden Gate Ave, Jones, Leavenworth and Taylor, completed 2019 to 2022) | Pedestrian collisions "from 35.7 to 20.1 a year", 44% fewer.[^32] |
| Tenderloin daylighting (red zones at 67 intersections by March 2015, 3 years each side) | "14% fewer reported collisions at intersections where daylighting treatments were implemented".[^33] |

### Cameras and corridors, what sits under the rows

The camera row pools all 33 locations, because no single block has enough reports to read. Each location starts on its first warning day, between 2025-04-01 and 2025-06-06. Citations began 2025-08-05, and counting from then gives −14% at the blocks.[^34] Another year roughly doubles the counts and should tell a 20% drop from no change.[^35] Camera sites were chosen for speeding and crashes, so some of any drop is the usual fall back toward normal after a bad stretch.[^36]

Two questions sit under the corridor rows. Corridors finished in 2020 read better against the whole city than against their own surrounding blocks, Howard St most of all (−38% against the city, −26% against its neighborhood). We have not yet found why downtown fell further than the rest of the city in the years right after 2020, though over the longer 2015 to 2019 against 2021 to 2025 comparison the two fell by about the same.[^37] And three corridors rose against the city once their two blocks are counted: Indiana St, South Van Ness Ave, Evans Ave. We don't know why, and each is a question before it is a finding.

### The 31 corridors, one by one

Each cell is people hurt before → after, then the change against the rest of the city with its 95% range.

| Corridor | Everyone at the site | People walking at the site | Everyone, with two blocks | Against the surrounding blocks instead |
|---|---|---|---|---|
| **Folsom St quick-build**. 2nd St to 5th St, 0.51 mi. SFMTA: installed 2018 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from January 2019, 3 years each side | 51 → 44 −1% (−34% to +49%) | 14 → 7 too few to read | 136 → 122 +3% (−19% to +32%) | +19% |
| **Turk St safety project**. Market St to Polk St, 0.56 mi. SFMTA: spring 2018 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from July 2018, 3 years each side | 67 → 81 +36% (−2% to +89%) | 38 → 36 +18% (−26% to +87%) | 393 → 380 +9% (−6% to +26%) | +3% |
| **8th St safety project**. Market St to Townsend St, 0.84 mi. SFMTA: May 2017 to July 2019 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from August 2019, 3 years each side | 105 → 113 +29% (−2% to +68%) | 19 → 22 too few to read | 368 → 336 +9% (−6% to +27%) | +2% |
| **Valencia St pilot bikeway**. Market St to 15th St, 0.41 mi. SFMTA: January 2019 ([source](https://sf.gov/es/node/497)). After from February 2019, 3 years each side | 65 → 51 −9% (−37% to +32%) | 5 → 7 too few to read | 221 → 221 +16% (−4% to +40%) | +18% |
| **Taylor St quick-build**. Market St to Sutter St, 0.47 mi. SFMTA: summer 2019 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from October 2019, 3 years each side | 77 → 63 −1% (−29% to +38%) | 34 → 25 +1% (−40% to +70%) | 394 → 273 −16% (−28% to −2%) | −21% |
| **6th St quick-build**. Market St to Folsom St, 0.36 mi. SFMTA: September 2019 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from October 2019, 3 years each side | 121 → 89 −11% (−32% to +17%) | 45 → 28 −14% (−46% to +39%) | 377 → 283 −9% (−22% to +6%) | −13% |
| **Indiana St quick-build**. 23rd St to Cesar Chavez St, 0.35 mi. SFMTA: October 2019 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from November 2019, 3 years each side | 6 → 1 too few to read | 1 → 0 too few to read | 21 → 33 +96% (+14% to +239%) | +80% |
| **Howard St quick-build**. 3rd St to The Embarcadero, 0.72 mi. SFMTA: winter 2020 ([source](https://www.sfmta.com/projects/transbay-howard-streetscape-improvement-project)). After from April 2020, 3 years each side | 82 → 41 −38% (−57% to −9%) | 33 → 6 too few to read | 244 → 144 −26% (−40% to −9%) | −13% |
| **Brannan St quick-build**. The Embarcadero to Division St, 1.53 mi. SFMTA: early winter 2020 ([source](https://www.sfmta.com/projects/brannan-street-safety-project)). After from April 2020, 3 years each side | 102 → 63 −23% (−44% to +6%) | 17 → 7 too few to read | 359 → 264 −8% (−22% to +8%) | −4% |
| **Fell St protected bike lane**. Baker St to Shrader St, 0.64 mi. SFMTA: early 2020 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from April 2020, 3 years each side | 33 → 24 −9% (−46% to +54%) | 3 → 0 too few to read | 118 → 68 −28% (−47% to −3%) | −21% |
| **Townsend St corridor**. 3rd St to 8th St, 0.86 mi. SFMTA: spring 2020 ([source](https://www.sfmta.com/projects/townsend-corridor-improvement-project)). After from July 2020, 3 years each side | 49 → 32 −24% (−51% to +19%) | 10 → 3 too few to read | 174 → 115 −23% (−39% to −3%) | −14% |
| **California St quick-build**. Arguello Blvd to 18th Ave, 1.01 mi. SFMTA: summer 2020 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from October 2020, 3 years each side | 41 → 24 −36% (−61% to +7%) | 3 → 3 too few to read | 154 → 100 −29% (−45% to −8%) | −27% |
| **Beale St quick-build**. Market St to Howard St, 0.24 mi. SFMTA: December 2020 ([source](https://www.sfmta.com/projects/active-beale-street)). After from January 2021, 3 years each side | 12 → 11 too few to read | 4 → 2 too few to read | 90 → 68 −20% (−42% to +9%) | −6% |
| **Central Embarcadero quick-build**. Mission St to Broadway, 0.48 mi. SFMTA: early 2021 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from April 2021, 3 years each side | 50 → 40 −19% (−47% to +23%) | 5 → 5 too few to read | 81 → 67 −16% (−39% to +16%) | +11% |
| **Anza St bike lanes**. 30th Ave to Arguello Blvd, 1.7 mi. SFMTA: June 2021 ([source](https://www.sfmta.com/projects/anza-street-bike-lanes-project)). After from July 2021, 3 years each side | 23 → 23 0% (−44% to +79%) | 2 → 6 too few to read | 246 → 234 −5% (−20% to +14%) | +4% |
| **7th St quick-build**. Folsom St to Townsend St, 0.48 mi. SFMTA: 2020 and 2021 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from January 2022, 3 years each side | 40 → 53 +30% (−14% to +96%) | 3 → 6 too few to read | 82 → 102 +22% (−9% to +63%) | +23% |
| **Golden Gate Ave quick-build**. Polk St to Market St, 0.47 mi. SFMTA: 2021 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from January 2022, 3 years each side | 54 → 46 −17% (−44% to +24%) | 24 → 15 too few to read | 357 → 357 −2% (−16% to +14%) | −9% |
| **Leavenworth St quick-build**. Mcallister St to Post St, 0.46 mi. SFMTA: 2021 ([source](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf)). After from January 2022, 3 years each side | 67 → 82 +20% (−13% to +66%) | 35 → 24 −29% (−58% to +20%) | 280 → 320 +12% (−5% to +32%) | +11% |
| **Williams Ave quick-build**. 3rd St to Phelps St, 0.4 mi. SFMTA: October 2021 ([source](https://www.sfmta.com/williams-avenue-quick-build-project)). After from November 2021, 3 years each side | 9 → 18 too few to read | 2 → 1 too few to read | 40 → 59 +48% (−1% to +121%) | +73% |
| **South Van Ness Ave quick-build**. 14th St to Cesar Chavez St, 1.4 mi. SFMTA: January 2022 ([source](https://www.sfmta.com/projects/south-van-ness-avenue-quick-build-project)). After from February 2022, 3 years each side | 122 → 130 +3% (−19% to +33%) | 19 → 13 too few to read | 326 → 406 +21% (+4% to +40%) | +25% |
| **Jones St quick-build**. Golden Gate Ave to O'Farrell St, 0.26 mi. SFMTA: summer 2022 ([source](https://www.sfmta.com/projects/jones-street-quick-build)). After from October 2022, 3 years each side | 36 → 36 −6% (−41% to +50%) | 15 → 16 too few to read | 197 → 196 −6% (−23% to +14%) | −13% |
| **Evans Ave quick-build**. Cesar Chavez St to 3rd St, 0.72 mi. SFMTA: summer to fall 2022 ([source](https://www.sfmta.com/projects/evans-avenue-quick-build)). After from January 2023, 3 years each side | 59 → 83 +30% (−7% to +82%) | 9 → 8 too few to read | 112 → 157 +29% (+1% to +65%) | +51% |
| **Franklin St quick-build**. Broadway to Lombard St, 0.39 mi. SFMTA: late 2022 ([source](https://www.sfmta.com/projects/franklin-street-quick-build-project)). After from January 2023, 3 years each side | 34 → 25 −32% (−60% to +14%) | 4 → 1 too few to read | 132 → 142 −1% (−22% to +26%) | −12% |
| **Battery St quick-build**. Market St to Vallejo St, 0.61 mi. SFMTA: January 2023 ([source](https://www.sfmta.com/projects/batterysansome-quick-build-project)). After from February 2023, 3 years each side | 34 → 31 −17% (−49% to +36%) | 8 → 2 too few to read | 104 → 106 −7% (−29% to +23%) | −9% |
| **Sansome St quick-build**. Sutter St to Broadway, 0.57 mi. SFMTA: January 2023 ([source](https://www.sfmta.com/projects/batterysansome-quick-build-project)). After from February 2023, 3 years each side | 16 → 24 too few to read | 9 → 5 too few to read | 95 → 94 −9% (−32% to +21%) | −13% |
| **17th St quick-build**. Potrero Ave to Pennsylvania Ave, 0.74 mi. SFMTA: summer to fall 2023 ([source](https://www.sfmta.com/projects/17th-street-quick-build)). After from January 2024, 2.7 years each side | 28 → 29 +4% (−38% to +74%) | 3 → 3 too few to read | 114 → 117 +3% (−21% to +33%) | −4% |
| **Bayshore Blvd quick-build**. Oakdale Ave to Silver Ave, 0.75 mi. SFMTA: construction August 2023, completed fall 2023 ([source](https://www.sfmta.com/projects/bayshore-boulevard-quick-build-project)). After from January 2024, 2.7 years each side | 68 → 73 +7% (−23% to +50%) | 10 → 10 too few to read | 126 → 134 +6% (−17% to +36%) | +12% |
| **Lincoln Way quick-build**. Great Hwy to Arguello Blvd, 2.89 mi. SFMTA: winter 2024 ([source](https://www.sfmta.com/projects/lincoln-way-quick-build-project)). After from April 2024, 2.4 years each side | 88 → 81 −9% (−33% to +23%) | 12 → 9 too few to read | 200 → 171 −16% (−31% to +3%) | −2% |
| **3rd St quick-build**. Channel St to Townsend St, 0.35 mi. SFMTA: March 2024 ([source](https://www.sfmta.com/projects/3rd-street-quick-build-project)). After from April 2024, 2.4 years each side | 19 → 33 too few to read | 3 → 1 too few to read | 81 → 84 +2% (−25% to +39%) | −16% |
| **Guerrero St quick-build**. Market St to 20th St, 0.87 mi. SFMTA: summer 2024 ([source](https://www.sfmta.com/projects/guerrero-street-quick-build-project)). After from October 2024, 2 years each side | 50 → 49 −5% (−36% to +42%) | 6 → 5 too few to read | 138 → 128 −10% (−29% to +15%) | −5% |
| **Frida Kahlo Way quick-build**. Judson Ave to Ocean Ave, 0.36 mi. SFMTA: fall 2024 ([source](https://www.sfmta.com/projects/frida-kahlo-way-quick-build-project)). After from January 2025, 1.7 years each side | 7 → 3 too few to read | 0 → 2 too few to read | 14 → 13 −5% (−56% to +102%) | too few to read |

Corridor extents from SFMTA's [Quick-Build Program](https://www.sfmta.com/quick-build-program) page and project pages, matched to centerline segments by street name between the two cross streets, both lines of a divided street. Corridors whose after window ends before 3 years use the data available, shown in the row.

### The 33 speed camera locations, one by one

| Location | Everyone at the block | People walking at the block | Everyone, with two blocks | Against the surrounding blocks instead |
|---|---|---|---|---|
| **Franklin St, 2510 block**. 25 mph limit, 1 camera, in the camera data from 2025-04-01, NB. 1.4 years each side | 3 → 1 too few to read | 1 → 1 too few to read | 10 → 24 too few to read | too few to read |
| **Columbus Ave, 841 block**. 20 mph limit, 2 cameras, in the camera data from 2025-04-01, NB and SB. 1.4 years each side | 4 → 3 too few to read | 1 → 0 too few to read | 10 → 4 too few to read | too few to read |
| **Broadway, 770 block**. 20 mph limit, 2 cameras, in the camera data from 2025-04-01, EB and WB. 1.4 years each side | 10 → 9 too few to read | 1 → 4 too few to read | 26 → 30 +15% (−32% to +95%) | −18% |
| **Turk St, 600 block**. 20 mph limit, 1 camera, in the camera data from 2025-04-01, WB. 1.4 years each side | 10 → 9 too few to read | 3 → 0 too few to read | 79 → 61 −23% (−45% to +7%) | −32% |
| **7th St, 356 block**. 25 mph limit, 1 camera, in the camera data from 2025-04-17, NB. 1.4 years each side | 7 → 7 too few to read | 2 → 2 too few to read | 15 → 23 too few to read | too few to read |
| **10th St, 349 block**. 25 mph limit, 1 camera, in the camera data from 2025-04-01, SB. 1.4 years each side | 1 → 4 too few to read | 0 → 1 too few to read | 36 → 22 −39% (−64% to +3%) | −45% |
| **King St, 353 block**. 30 mph limit, 1 camera, in the camera data from 2025-04-01, EB. 1.4 years each side | 1 → 7 too few to read | 1 → 2 too few to read | 18 → 23 too few to read | too few to read |
| **Market St, 2999 block**. 30 mph limit, 2 cameras, in the camera data from 2025-04-01, EB and WB. 1.4 years each side | 0 → 0 too few to read | 0 → 0 too few to read | 10 → 3 too few to read | too few to read |
| **3rd St, 6479 block**. 25 mph limit, 1 camera, in the camera data from 2025-04-01, NB. 1.4 years each side | 5 → 9 too few to read | 0 → 0 too few to read | 10 → 23 too few to read | too few to read |
| **San Jose Ave, 1999 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-10, NB and SB. 1.3 years each side | 3 → 0 too few to read | 1 → 0 too few to read | 7 → 4 too few to read | too few to read |
| **Geary Blvd, 4334 block**. 25 mph limit, 2 cameras, in the camera data from 2025-04-01, EB and WB. 1.4 years each side | 0 → 2 too few to read | 0 → 0 too few to read | 15 → 6 too few to read | too few to read |
| **Fulton St, 6654 block**. 25 mph limit, 2 cameras, in the camera data from 2025-04-01, EB and WB. 1.4 years each side | 1 → 0 too few to read | 1 → 0 too few to read | 2 → 6 too few to read | too few to read |
| **Fulton St, 2530 block**. 25 mph limit, 2 cameras, in the camera data from 2025-04-22, EB and WB. 1.4 years each side | 3 → 4 too few to read | 2 → 0 too few to read | 5 → 12 too few to read | too few to read |
| **Bay St, 1333 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-22, EB and WB. 1.3 years each side | 3 → 0 too few to read | 0 → 0 too few to read | 4 → 8 too few to read | too few to read |
| **The Embarcadero, 1517 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-28, NB and SB. 1.3 years each side | 7 → 8 too few to read | 0 → 1 too few to read | 42 → 45 +5% (−31% to +61%) | +3% |
| **Lincoln Way, 2699 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-16, EB and WB. 1.3 years each side | 2 → 0 too few to read | 0 → 0 too few to read | 7 → 1 too few to read | too few to read |
| **Sloat Blvd, 2155 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-15, EB and WB. 1.3 years each side | 5 → 3 too few to read | 0 → 0 too few to read | 21 → 5 too few to read | too few to read |
| **Geary Blvd, 1660 block**. 30 mph limit, 2 cameras, in the camera data from 2025-04-01, EB and WB. 1.4 years each side | 11 → 15 too few to read | 3 → 3 too few to read | 37 → 28 −25% (−54% to +23%) | −23% |
| **Mission St, 1250 block**. 20 mph limit, 2 cameras, in the camera data from 2025-05-28, EB and WB. 1.3 years each side | 9 → 10 too few to read | 2 → 1 too few to read | 57 → 63 +9% (−24% to +56%) | −10% |
| **9th St, 451 block**. 25 mph limit, 1 camera, in the camera data from 2025-05-28, NB. 1.3 years each side | 3 → 9 too few to read | 1 → 1 too few to read | 28 → 29 +2% (−40% to +71%) | +5% |
| **Harrison St, 815 block**. 25 mph limit, 1 camera, in the camera data from 2025-05-28, WB. 1.3 years each side | 19 → 9 too few to read | 2 → 1 too few to read | 36 → 33 −10% (−44% to +45%) | −11% |
| **Bryant St, 467 block**. 25 mph limit, 1 camera, in the camera data from 2025-05-17, EB. 1.3 years each side | 8 → 6 too few to read | 0 → 0 too few to read | 14 → 14 too few to read | too few to read |
| **Ocean Ave, 825 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-28, EB and WB. 1.3 years each side | 0 → 2 too few to read | 0 → 0 too few to read | 23 → 10 too few to read | too few to read |
| **Monterey Blvd, 481 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-28, EB and WB. 1.3 years each side | 2 → 0 too few to read | 1 → 0 too few to read | 8 → 1 too few to read | too few to read |
| **Guerrero St, 763 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-30, NB and SB. 1.3 years each side | 6 → 1 too few to read | 1 → 0 too few to read | 32 → 27 −17% (−51% to +38%) | −15% |
| **San Jose Ave, 765 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-07, NB and SB. 1.3 years each side | 9 → 0 too few to read | 0 → 0 too few to read | 24 → 19 too few to read | too few to read |
| **16th St, 2300 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-31, EB and WB. 1.3 years each side | 2 → 5 too few to read | 0 → 0 too few to read | 32 → 23 −30% (−59% to +20%) | −17% |
| **Cesar Chavez St, 3149 block**. 25 mph limit, 2 cameras, in the camera data from 2025-05-22, EB and WB. 1.3 years each side | 12 → 5 too few to read | 1 → 0 too few to read | 30 → 25 −19% (−52% to +39%) | −12% |
| **Cesar Chavez St, 1247 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-29, EB and WB. 1.3 years each side | 0 → 1 too few to read | 0 → 0 too few to read | 7 → 10 too few to read | too few to read |
| **Bayshore Blvd, 2066 block**. 30 mph limit, 1 camera, in the camera data from 2025-06-03, SB. 1.3 years each side | 9 → 8 too few to read | 4 → 2 too few to read | 19 → 19 too few to read | too few to read |
| **Geneva Ave, 1553 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-29, EB and WB. 1.3 years each side | 8 → 0 too few to read | 3 → 0 too few to read | 19 → 5 too few to read | too few to read |
| **Mission St, 5372 block**. 20 mph limit, 2 cameras, in the camera data from 2025-06-06, NB and SB. 1.2 years each side | 1 → 0 too few to read | 0 → 0 too few to read | 3 → 3 too few to read | too few to read |
| **Alemany Blvd, 2851 block**. 30 mph limit, 2 cameras, in the camera data from 2025-05-31, NB and SB. 1.3 years each side | 3 → 2 too few to read | 0 → 1 too few to read | 11 → 7 too few to read | too few to read |

A location's block is the centerline segment nearest each camera's address, both lines where the street is divided. Every location has fewer than 20 people walking hurt in a window, so that column is counts only.

## About the data

### Why Fewer People Are Hurt Since 2020

Injuries fell in the second quarter of 2020 and have stayed lower. The drop is in minor injuries, weekday commute hours and people walking and biking, while severe injuries held and deaths rose. From 2015 to 2019 against 2021 to 2025, downtown fell −13% and the rest of the city −11%, close to each other.[^38]

| Group | 2015 to 2019, a year | 2021 to 2025, a year | Change |
|---|---|---|---|
| Complaint of pain | 2,887 | 2,438 | −16% |
| Other visible injury | 976 | 919 | −6% |
| Severe injury | 272 | 267 | −2% |
| Killed | 26 | 32 | +21% |
| 7 to 10 AM and 4 to 7 PM | 1,479 | 1,215 | −18% |
| Other daytime hours | 2,014 | 1,778 | −12% |
| 10 PM to 6 AM | 663 | 662 | 0% |
| Weekdays | 3,033 | 2,594 | −14% |
| Weekends | 1,129 | 1,062 | −6% |
| Downtown box | 1,609 | 1,405 | −13% |
| Rest of the city | 2,532 | 2,242 | −11% |
| Driving | 1,860 | 1,665 | −10% |
| Passenger | 812 | 675 | −17% |
| Walking | 880 | 656 | −25% |
| Biking | 561 | 426 | −24% |
| Other, mostly scooters | 48 | 234 | +387% |

People hurt by quarter, 2018 to 2023 [DataSF nwes-mmgh — queried 2026-10-20]:

| Year | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| 2018 | 1,051 | 1,023 | 995 | 1,073 |
| 2019 | 953 | 1,076 | 1,129 | 1,239 |
| 2020 | 918 | 541 | 724 | 810 |
| 2021 | 756 | 881 | 953 | 927 |
| 2022 | 769 | 983 | 928 | 989 |
| 2023 | 831 | 859 | 994 | 1,049 |

The downtown box is east of longitude −122.425 and north of latitude 37.765. "Other" victims rose as scooters arrived.

### How Sure Are We

The quick-build walking row (two blocks, −12%) went through seven checks.

| Check | Result |
|---|---|
| The years before | The same comparison one window earlier, before any work: +5% (−4% to +15%), no drop before the fix |
| Leaving out COVID | Ending the after windows before the pandemic's traffic drop changed little: −13% (−20% to −6%) |
| Moving the start date | Three months earlier, −11%. Three months later, −13%. Both stay below zero |
| Testing many rows at once | With 14 rows on the chart, one in twenty would look clear by chance. After a Holm correction this row, p = 0.018, falls just short |
| A nearer comparison | Against the surrounding blocks, three to eight out, instead of the whole city: −10% (−20% to 0%), a range that reaches zero |
| Splitting overlaps another way | Giving a person inside two projects' areas to each project in turn, instead of half to each: −5%. [inference — mine, a check run 2026-10-20] |
| Counting crashes, not people | Not yet run on this row. On the walking row at the corridors themselves it gave −14% (−27% to 0%) |

The COVID, start date and crash checks were run on the summed counts across projects. The others count each person once. [inference — mine, the method]

**Crash data:** DataSF [Traffic Crashes Resulting in Injury: Victims Involved](https://data.sfgov.org/d/nwes-mmgh), read 2026-10-20, 83,820 victims from 2005 to 2026-08-31. One row is one injured person. Severe means the officer's "Severe Injury" or "Fatal Injury". The 2018 count of police-reported severe injuries, 283, matches SFDPH's published table exactly.[^39]

**Streets:** DataSF [Streets, Active and Retired](https://data.sfgov.org/d/3psu-pn9h), active rows, read 2026-10-20. Each injury is snapped to the nearest surface centerline within 150 ft. Freeway lines are left out because the crash data excludes freeway crashes.

**Late reports:** crash reports can be filed up to 30 days after a crash, so August 2026 may still grow at the next quarterly release.

**Overlaps:** some fixes sit inside each other's two blocks, the four Tenderloin quick-builds and the Turk St camera inside the daylighting area most of all, so a "two blocks" count there is partly another treatment. Several corridors changed again inside their windows, Valencia St most of all, so a row measures the street's whole set of changes, not one design.

## Do surveys show people rank safety low?

From notes/injuries-2026-10/2026-10-20-safety-priority-surveys.md, read 2026-10-20.

The answer is mixed, and the wording decides it. Safety is a minority answer when people are asked why a trip is stressful. It is a majority or top answer when people are asked what stops them biking, what a tax measure should fund, or how safe they feel.

| Survey | Result | Source |
|---|---|---|
| SFCTA School Access Plan caregivers, 2023, 366 responses | Of caregivers who find the school trip stressful (base not given): long trips 53%, timing 49%, other 30%, safety 25%, cost 21%. 52% said infrastructure safety fixes would make their trip safer | [report](https://www.sfcta.org/sites/default/files/2024-07/SF_School_Access_Plan_Report_2023-05-04_FINAL.pdf) [primary — read 2026-10-20] |
| GrowSF Pulse poll by FM3, 2024, 412 SF voters | Pedestrian safety infrastructure 70% "extremely" or "very" important, second after bus and train frequency 78%. Protected bike lanes 45%, last. 55% of would-be cyclists cite safety as the barrier | [GrowSF](https://growsf.org/pulse/growsf-pulse-may-2024/) [secondary — verify] |
| MTC regional measure survey by FM3, 2025, n=1,350 | Roads safer for walking and biking 32% "extremely important", fifth of six. Potholes 48% | [MTC report](https://es.planbayarea.org/sites/default/files/meetings/attachments/6252/12a_25_0219_2_TRM_Survey_Report.pdf) [primary — read 2026-10-20] |
| SFMTA Travel Decision Survey 2021, 756 | "Improving safety while onboard or waiting" ranks first for transit, 53% definitely. This is personal security, not traffic | [report](https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf) [primary — read 2026-10-20] |
| SFMTA Biking and Rolling Plan outreach, 2025 slides | 80% want to use the network, 23% feel comfortable | [slides](https://sfmta.com/media/39976/download) [primary — read 2026-10-20] |

The note's reading [inference — mine]: the surveys do not show people "don't care about safety". When safety is traded against time, convenience, money or potholes, it lands in the middle. Two surveys' top "safety" item is crime, not traffic, so a caregiver who says "safety" may mean either. Gaps: no Travel Decision Survey after 2021 found, Controller City Survey 2025 not opened, GrowSF wording read only through a page summary.

## How much of the budget goes to roads, safety, bikes, Muni and cars

From notes/injuries-2026-10/2026-10-20-sf-transport-budget-shares.md, read 2026-10-20. Every figure is planned, not spent. No actuals were read.

| Category | Planned dollars | Share | Source |
|---|---|---|---|
| City budget, all funds, FY26-27 | $16.9 billion a year | | [Mayor's book](https://media.api.sf.gov/documents/Mayors_June_1st_Proposed_FY27_and_FY28_Budget_Budget_Book.pdf) PDF p. 51 [primary — read 2026-10-20] |
| SFMTA operating, FY26-27 | $1,515 million (SFMTA's count) or $1,605.2 million (Mayor's book). The two disagree by about $90 million and neither says why | 9.0% or 9.5% of the city | [SFMTA budget](https://www.sfmta.com/media/45455/download?inline) p. 2, Mayor's book PDF p. 71 [primary — read 2026-10-20] |
| SFMTA five-year capital plan, FY27 to FY31 | $2,505 million. Only $379 million (15%) is city money | | [April 21, 2026 deck](https://www.sfmta.com/media/44858/download?inline) slide 25 [primary — read 2026-10-20] |
| Street infrastructure | Streets plus Signals programs $336 million over 5 years | 13.4% of SFMTA capital | Same deck |
| Safety | "Improve Street Safety" $286 million over 5 years. Operating Street Safety and Functionality about 3% of FY25-26, roughly $44 million [inference — mine, the dollars] | 11.4% of SFMTA capital | [April 7 deck](https://www.sfmta.com/media/44788/download) slide 22, [FY25-26 deck](https://www.sfmta.com/media/42571/download) slide 5 [primary — read 2026-10-20] |
| Bike infrastructure | Named bike projects $20.9 million in the two-year capital budget. Upper bound with mixed corridors $92.8 million | 1.7% to 7.7% of the $1,201 million two-year budget | [Enclosure 2](https://www.sfmta.com/media/44860/download?inline) pp. 20 to 69, the note's own sort [inference — mine] |
| Muni | Capital $1,906 million over 5 years. Operating Transit Services $890.1 million in FY26-27 | 76% of capital, 55.5% of operating | Deck slide 25, Mayor's book PDF p. 71 |
| Cars | Parking capital $3 million over 5 years. Operating Revenue Generation about 10% of FY25-26, roughly $145 million [inference — mine, the dollars] | Parking 0.1% of capital | Same |

Inside the mixed corridor items: Howard Streetscape $35.5 million and Citywide Vision Zero Quick-Build $14.7 million. The note's parse reads $138 million of Streets across two years against the published $142 million, so the bike share needs the unparsed rows read before it is quoted closely. Prop L's 30-year plan puts 18.9% ($492 million) into Streets and Freeways and has no bike line.

## Has anyone shown Vision Zero failed?

This section comes from search results posted on the mockup's thread on 2026-10-20. None of these reports has been opened yet. Each is [web search — verify].

| Source | What the search result says |
|---|---|
| Civil Grand Jury 2024-25, [Failed Vision](https://media.api.sf.gov/documents/2025_CGJ_Report_Failed_Vision.pdf) | SFMTA added safety measures, but police cut traffic enforcement sharply over the decade |
| Mayor's [August 2025 response](https://media.api.sf.gov/documents/Civil_Grand_Jury_Vision_Zero_Report_Response_Package_8.18.2025_FzkVlwG.pdf) | Agreed on enforcement. Disagreed that SFMTA plans reactively |
| Mission Local, [2024](https://missionlocal.org/2024/03/sf-vision-zero-lacks/) | Blames a piecemeal, reactive approach rather than the goal |
| Mission Local, [2025](https://missionlocal.org/2025/09/s-f-was-supposed-to-have-zero-traffic-deaths-by-now-what-happened/) | Follows up on why the 2024 zero-deaths goal was missed |
| GrowSF, [Vision Zero has failed](https://growsf.org/news/2025-06-20-vision-zero-failure/) | About 42 deaths in 2024 against a decade average of about 30 |
| GrowSF, [Street Safety Act](https://growsf.org/news/2025-09-26-street-safety-act/) | Covers the replacement law |
| [SF Examiner](https://www.sfexaminer.com/news/politics/article_de078702-2d4b-4445-ba8f-96379e88af3e.html) | Reports that the 2014 Vision Zero policy has expired |

**The gap.** None of them puts spending next to results. No one has published a Vision Zero spending total. The closest figures in the search results are SFMTA five-year capital plans, about $196M for streets and signals and about $52M for quick-builds, and a Budget and Legislative Analyst estimate of $2.5B in crash cost over five years. That last figure is the cost of crashes, not spending. These pieces count deaths only, 30 to 40 a year. Our page counts about 3,650 injuries a year and tests fixes corridor by corridor.

The two sources disagree on streets and signals capital. The search result says about $196M over five years. The budget note, from the April 2026 deck, says $336 million for FY27 to FY31. The search result does not name its plan years, so the two may be different plans. [inference — mine]

**Next step:** capital spending by year, from SFMTA budgets or a records request, set beside injuries by year and by corridor.

## Open questions and pending checks

From the open threads, read 2026-10-20, then the checks the page itself leaves open.

**Waiting on Bryan**

- Keep "falls just short of clear" for the quick-build walking row, or call it a drop with a caveat.
- Pick an injury and near-miss survey option. The options doc recommends a $200 Pollfish pilot of about 120 people, price and SF ZIP targeting unconfirmed.

**Pending work from threads**

- Cut pass: writing reviewer over the whole page, fewer words, decide whether the three big numbers stay.
- Move every chart to Observable Plot and run the data-page checklist.
- Cause chart sort: on the rendered page "Running a stop sign" (318) sits above "Driving under the influence" (393) on main roads, so the most-to-least order Bryan asked for is not fully applied.
- Google base map: board frames send referer null, so the map falls back to OpenFreeMap until the frame-host DNS step lands and the hostname is added to the Google key.
- Link this data-dive doc on the mockup threads.
- Threads answered as done but still open, which only need resolving: lrlj0az1sras (heat map scale), 97pldefjujx8 (NYC camera spillover), 6b1uzzs8uvaw (red curbs), u069o0fsv6ne (signal retiming label), 8l74o7iwvceh (quick-build definition), sb9dwvcn41gi (page reorganized), n42ejg2b9u5j (intersection class rule), w8zoafvhtxev (street examples), cc2js7a9ungm (causes chart), 1f6qrewtw8et (intersection section), zk4lfs6lxdv5 (two blocks defined), w1mrdt4t178e (forest plot), su80kpi63nkh (severe share in bars), aj4sj0x75x6z (section order), z3adfap56fa4 (axis and percents), g3672cpg76mr (people first).

**Checks the page leaves open**

- Counting crashes instead of people on the quick-build two-block walking row: not yet run.
- Why downtown fell further than the rest of the city right after 2020. No traffic count was opened.[^37]
- Why Indiana St, South Van Ness Ave and Evans Ave rose against the city once their two blocks are counted.
- A second year of camera data, to tell a 20% drop from no change.[^35]
- A matched comparison of untreated streets, to separate regression to the mean from a fix's effect.[^36]
- People hurt per mile walked, biked and driven by year, to explain the post-2020 drop.[^8]
- The police undercount for minor injuries in SF. Nobody has measured it.[^4]
- SF trip length by mode, for the per-mile comparison and the micromort cross-check.
- The federal definition of a Muni rider hurt. [model knowledge — verify][^14]
- The "What is counted counts" paper itself, quoted only through SFMTA.[^5]
- SFMTA's list of 80 daylighted intersections, against our 67.[^33]
- The bike-share parse of Enclosure 2, $138 million read against $142 million published.
- Open the Vision Zero reports in the section above and replace the search summaries with what they say.

## Source notes from the page

[^1]: Every victim in DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) (police crash reports) whose injury is not "No Injury", with a location, from 2021-09-01 to 2026-08-31. 17 were more than 150 ft from any street and are left out. [DataSF nwes-mmgh — queried 2026-10-20] Freeway crashes are excluded by the dataset itself.

[^2]: Main roads are the centerline layer's classes 2, 3 and 4: "Major street/Highway", "Arterial street" and "Collector Street", from DataSF [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h), which says "The Class Code field is used for symbolization". [primary — read 2026-10-20] A crash the report places at an intersection counts for the biggest street meeting there, so 80 people at a ramp or freeway mouth take that class and are in neither count. [DataSF 3psu-pn9h — queried 2026-10-20] That rule matters: 8,021 of the 13,834 people counted on main roads were hurt at a corner a main road shares with a residential street, and giving each crash to its nearest centerline instead puts 60% on main roads. [inference — mine, a check run 2026-10-20]

[^3]: Within 60 ft of San Francisco Municipal Transportation Agency (SFMTA)'s [2022 High Injury Network](https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/hin2022/FeatureServer/0), 160 centerline miles. 10,471 of the 11,847 are also on a main road. SFMTA's own figure for the newer 2024 network is "13% of city street miles and 74% of severe and fatal injuries" ([Vision Zero Committee deck](https://www.sfmta.com/media/44957/download?inline), May 2026, slide 7). [primary — read 2026-10-19] Ours counts every injury on the 2022 network. For severe and fatal injuries alone: 1,002 of 1,499, 67%. [inference — mine]

[^4]: SFDPH, [Severe Traffic Injuries in San Francisco](https://web.archive.org/web/2016/http://sf.streetsblog.org/wp-content/uploads/sites/3/2015/09/SevereInjuriesSF_2014_15_PSAC.pdf), September 2015, p. 1: "515 Patients with Severe Injuries vs ~200 SFPD reported Severe Injuries", "515 Patients in 1 year". Streetsblog's report of the study gives the year as the twelve months from April 2014 and the definition as hospitalized more than 24 hours. [primary — read 2026-10-20] The 2013 to 2015 linkage of the two records found "59% of records classified as severe appeared both in police and hospital data" (SFDPH, [Severe Traffic Injury Trends 2011-2017](https://www.sfcta.org/sites/default/files/2019-06/Item%205%20-%20Severe-Injury-Trends_2011-2017Final.pdf), December 2018, p. 4). [primary — read 2026-10-20] Nobody has measured the gap for minor injuries in San Francisco. [unretrieved — verify]

[^5]: Soltani, Schwarcz, Morris, Plevin, Dicker, Juillard, Nwabuo and Wier, [What is counted counts](https://doi.org/10.1016/j.jsr.2022.08.002), Journal of Safety Research, 2022, as quoted on SFMTA's [Vision Zero data update](https://sfmta.com/media/33452/download). [primary — read 2026-10-20, the SFMTA quotation] The paper itself was not opened. SFDPH's [2018 report](https://www.sfcta.org/sites/default/files/2019-09/Item%206%20-%202018%20Severe%20Injuries%20Report.pdf): "Severe injury in those reports is determined based on police officer's visual assessment of injury severity, not clinical determination." [primary — read 2026-10-20]

[^6]: Nobody has measured the police gap for minor injuries in San Francisco, so the last sentence is an inference from the severe-injury studies above. [inference — mine]

[^7]: Every injured victim row in DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) by the year of collision_datetime, with or without a location, severe is "Severe Injury" or "Fatal Injury". [DataSF nwes-mmgh — queried 2026-10-20]

[^8]: SFCTA, [Congestion Management Program 2025](https://www.sfcta.org/sites/default/files/2025-12/SFCTA_CMP_Report_2025_FINAL_2025-12-16.pdf), p. E-17: "As of 2025, VMT is hovering at around 10% below pre-COVID levels", p. E-11: mid-week traffic "reaching 92% of pre-COVID pandemic (2019) levels". [primary — read 2026-10-20] From 2015 to 2019 against 2021 to 2025, people hurt walking fell −25%, biking −24% and driving −10%, severe injuries changed −2% and injuries from 10 PM to 6 AM 0%. Less driving fits the commute-hour drop, fewer people walking and biking fits those modes falling furthest, and fewer minor-injury reports fits severe injuries holding while minor ones fell. Counts of people hurt per mile walked, biked and driven by year would separate them, and we haven't found them. [inference — mine] The split by injury, hour, day, place and mode is in [About the data](#why-fewer-people-are-hurt-since-2020). SFDPH's hospital count of severe injuries, a separate source, was 533 in 2019 and 535 in 2022 ([Severe Traffic Injury Trends 2015-2022](https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf), Table 1). [primary — read 2026-10-20]

[^9]: SFDPH, [Severe Traffic Injury Trends 2011-2018](https://www.visionzerosf.org/wp-content/uploads/2019/09/Severe-Injury-Trends_2011-2018_final_report.pdf), Appendix A: "a memo released to SFPD officers in Dec. 2014 advised head injuries be classified as severe to avoid under-reporting of traumatic brain injury. This guidance likely partially accounts for the increase in severe injuries recorded in police data from 2015 onward." [primary — read 2026-10-20] The data also comes from three systems, any of whose seams could move a count: "SFPD's Interim Collision System for 2018 to YTD, Crossroads Software Traffic Collision Database (CR) for years 2013-2017 and the Statewide Integrated Transportation Record System (SWITRS) maintained by the California Highway Patrol for all years prior to 2013" ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) metadata). [primary — read 2026-10-20]

[^10]: Heat map scaled to its own densest spot, so it shows where people are hurt, not how many. Camera points from DataSF [d5uh-bk84](https://data.sfgov.org/d/d5uh-bk84). [DataSF d5uh-bk84 — queried 2026-10-20] Network from SFMTA's ArcGIS layer. [primary — read 2026-09-30]

[^11]: The report's intersection field from DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh): "Intersection <= 20ft" is at the intersection, and "Midblock > 20ft" and "Intersection Rear End <= 150ft" are midblock. [DataSF nwes-mmgh — queried 2026-10-20]

[^12]: A crash at a corner counts toward the biggest street there. Giving it to the nearest centerline instead puts 66% of people hurt on main roads at the intersection and 70% on residential streets, against 71% and 58% here, so the gap between the two kinds of street depends on the rule and isn't a finding. [inference — mine, a check run 2026-10-20]

[^13]: The at_fault field of DataSF [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6), Traffic Crashes Resulting in Injury: Parties Involved, one row per party, joined to each person hurt on the crash's case_id_pkey. [DataSF 8gtc-pjc6 — queried 2026-10-11] Mode is the party's party_type and stwd_vehicle_type. Cars and trucks leave out motorcycles and mopeds, 21 of the 51 people killed and 1,724 of the 11,141 hurt in a motor vehicle, because the trip survey has no motorcycle trip count to divide by. Motorcycles carry 256 of the 542 people severely hurt or killed in a motor vehicle, so leaving them out roughly halves the car rate for severe injuries, and the survey's car share still includes motorcycle trips, so the car rates read a little low. They include 138 people hurt where a hit and run driver's vehicle is unknown. 4,070 of the people under a driver were the at fault driver or a passenger in that vehicle. A parked vehicle marked at fault, mostly a door opened into traffic, counts as other (66 people). Transit is the vehicle type "Public Transit Authority", whose makes are mostly Muni buses, light rail and cable cars. The crash table's party_at_fault agrees with these flags on every crash but one. No published count by at fault mode could be matched. [inference — mine, the grouping]

[^14]: Trips: SFMTA, [Travel Decision Survey 2021](https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf), p. 5: "Total Daily Trips" 4,380,121, an SF-CHAMP 2015 model run grown for population, for trips into, within and out of San Francisco by Bay Area residents. Shares: walk 24%, bicycle 3% (from a 2021 survey of 756 people, so a 2% or 4% share would move the bike commute year to about 1 in 140 or 1 in 280), public transit 10%, and the survey's Privately Owned Vehicles 62% (drive alone, which includes motorcycle, carpool and ride-hail (TNC)). [primary — read 2026-10-20] We multiply the daily total by each share and by 365 days and 5 years, and show people per 10 million trips. A year of commuting is 500 trips, 250 workdays there and back, and its chance is one minus the chance of no injury on any of them. [inference — mine] Crashes: every party in the 14,834 injury crashes on surface streets from September 2021 to August 2026 ([8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6)), and the people hurt ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)). [DataSF 8gtc-pjc6 — queried 2026-10-11] A crash party is one person walking or riding, or one vehicle with everyone in it, so a car crash counts once however many ride. "Hurting someone else" is people hurt in a crash where a party of that mode was the only one marked at fault, other than that party and its passengers. Muni is all public transit, BART included. For getting hurt, Muni's count is the FTA National Transit Database's riders hurt on a Muni vehicle in safety events, assaults and other security events left out: 95 in major events ([9ivb-8ae9](https://data.transportation.gov/d/9ivb-8ae9)) and 521 in non-major ones ([urir-txqm](https://data.transportation.gov/d/urir-txqm)), September 2021 to June 2026, scaled from those 58 months to the page's window, because police reports miss falls on board. [primary — read 2026-10-20] [inference — mine, the scaling] Police reports alone count 191 people hurt on Muni, operators included. Being in a crash and hurting someone else stay on police data for every mode. The federal data counts a rider as hurt only when they were taken from the scene for medical care, a stricter bar than a police report's complaint of pain, and its count is Muni's alone while the trip share includes BART, so Muni's rate still reads low against the other modes. [model knowledge — verify, the federal definition] Trips include the parts outside the city of trips into and out of San Francisco, and the crash data leaves out freeways. Most of those outside and freeway miles are by car, so the car rates read low and the bike-to-car ratio is an upper bound. [inference — mine, the method]

[^15]: type_of_collision in [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) and the one at-fault party in [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6), September 2021 to August 2026. 28% of people hurt biking were hurt in the dark or at dusk, against 40% of people walking (the crash table's lighting). [DataSF nwes-mmgh — queried 2026-10-20]

[^16]: Each person is snapped to the nearest centerline block, and a block counts when SFMTA's bikeway layer (data/extract/sfmta-bikeway/network.json) has any row with its CNN. 17% were on a block with a separated bikeway, 3% of street miles. 65% were on the High Injury Network, about the same as everyone hurt (64%). [inference — mine]

[^17]: The at-fault driver's stwd_vehicle_type in [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6), crashes with one party at fault, people hurt outside that vehicle, September 2021 to August 2026. [DataSF 8gtc-pjc6 — queried 2026-10-11] The data carries make and model year but no model, so it can't tell a vehicle's weight or hood height. [inference — mine]

[^18]: Each person hurt from September 2021 to August 2026 ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)) by their own mode, against the mode of the one party marked at_fault in their crash ([8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6)). The at-fault person counts too: an at-fault cyclist who is hurt is in Biking, the rider hurt, whoever else was in the crash. A parked car at fault counts as driving, and a crash with no party or two parties at fault is in the last row. Police-reported crashes on surface streets only, no freeways. [DataSF 8gtc-pjc6 — queried 2026-10-11]

[^19]: People hurt in crashes with one cyclist at fault, by the crash's primary collision factor, vz_pcf_code in [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), named from the city's vz_pcf_description in [ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx): Vehicle Code 22350, 21453(a), 22107, 21650.1 with 21650 and 21657, and 22450(a). [DataSF nwes-mmgh — queried 2026-10-20]

[^20]: People hurt from September 2021 to August 2026 ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)) whose own party is the only one marked at_fault in [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6). "No one else involved" is a crash with one party. Years run September to August. [DataSF 8gtc-pjc6 — queried 2026-10-11]

[^21]: The crash's vz_pcf_code, named from the city's vz_pcf_description in [ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx). For the 203 cyclists alone, "unsafe speed for prevailing conditions" was the cause for 152. [DataSF ubvf-ztfx — queried 2026-10-20]

[^22]: The crash table's road_cond_1, filled in for all but 34 of the 885 reports ("Not Stated"): "Holes, Deep Rut" 12, "Construction or Repair Zone" 10, "Obstruction on Roadway" 8, "Loose Material on Roadway" 4, others 2, "Other" 36 is not counted. Wet road 66. [DataSF ubvf-ztfx — queried 2026-10-20] SFDPH's match of hospital and police records found the people police miss are "more often cyclists" (see the note at the top). No count of solo falls missed was opened, so we give no number. [inference — mine]

[^23]: A micromort is a one in a million chance of death. San Francisco: people killed by their own mode from September 2021 to August 2026 ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), walking 91, biking 9, car or truck 30, muni or other transit 1), over the same trip counts as above, with an exact Poisson 95% range. [DataSF nwes-mmgh — queried 2026-10-20] Police-reported deaths on surface streets only, and trips include their legs outside the city. A car trip leaves out the 21 motorcycle and moped riders killed, because there is no trip count for them. The federal transit safety data lists no Muni rider killed in a crash or other safety event from September 2021 to June 2026, and two homicides on board, which are security events and not counted here. [primary — read 2026-10-20] References from Wikipedia, [Micromort](https://en.wikipedia.org/wiki/Micromort): a day of living, us 22 (all causes, US, 2010, CDC), a skydiving jump 8 (US, USPA, 2000 to 2016), a day, non-natural, us 1.6 (accidents, suicide and homicide, US, 2010, CDC), a 1,000-mile flight 1 (Howard: 1,000 miles by jet is one micromort), smoking one cigarette 0.71 (Howard, 1979: 1.4 cigarettes is one micromort, so one is 1/1.4), radiation, 2,500-mile flight 0.42 (Howard, 1979: 6,000 miles by jet is one micromort of cancer from cosmic radiation, times 2,500/6,000), a glass of wine 0.3 (Howard, 1979: half a liter of wine is one micromort, so a 5-ounce glass is 148/500), a 3-mile bike ride, uk 0.068 (GOV.UK 2024: 44 miles by bike is one micromort, times 3/44), a 1-mile walk, uk 0.033 (GOV.UK 2024: 30 miles walked is one micromort, times 1/30), a 10-mile drive, uk 0.027 (GOV.UK 2024: 370 miles by car is one micromort, times 10/370), a charcoal-grilled steak 0.01 (Howard, 1979: 100 charcoal-broiled steaks is one micromort). [secondary — verify]

[^24]: Beck, Dellinger and O'Neil, [Motor Vehicle Crash Injury Rates by Mode of Travel](https://academic.oup.com/aje/article/166/2/212/98939), American Journal of Epidemiology, 2007: "The overall fatal traffic injury rate was 10.4 per 100 million person-trips", 0.104 micromorts a trip. [primary — read 2026-10-20] Per mode, our rates match the UK's per-mile rates over 1.4 miles of walking, 1.7 of biking and 2.2 of driving, plausible trip lengths for a dense city, though no San Francisco trip length by mode was opened. [inference — mine]

[^25]: The victim row's vz_pcf_code, "California vehicle code primary collision factor violated", one per crash and repeated on each person hurt in it, in DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh). [DataSF nwes-mmgh — queried 2026-10-20] The 18,422 people here were hurt in 14,753 crashes. No published count by cause could be matched: SFMTA says only that "unsafe speed is one of the most common primary collision factors in crashes that result in injuries" ([Speed Safety Cameras Background](https://www.sfmta.com/projects/speed-safety-cameras/background)). [primary — read 2026-10-20]

[^26]: The grouping is ours: unsafe speed is 22350 and 22348 to 22356, red light 21453(a) to (c), crosswalk 21950(a) and (c), turning left 21801 (the left or U turn yield), stop sign 22450 alone, so 21802, right of way entering a through highway, is in every other cause. Unsafe turn or lane change is 22107, following too closely 21703, under the influence 23152 and 23153, pedestrian violation 21453(d), 21950(b) and (e), 21954(a), 21955 and 21456. Unknown is a blank code or one the city's own description calls "Unknown". [inference — mine]

[^27]: The hour of collision_datetime in DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh), with each hour's count divided by the 1,304 weekdays or 522 weekend days from September 2021 to August 2026. The 10 people with no time on the report are left out. Days are calendar days, so a crash at 1 AM Saturday counts as a weekend. [DataSF nwes-mmgh — queried 2026-10-20]

[^28]: Each row compares equal windows before and after the fix, capped at 3 years each side, at the site and with two blocks each way, against the rest of the city. Each person counts once per row even where projects overlap: a person inside several projects' areas is split evenly among them, by place alone. The change is a Mantel-Haenszel ratio across a fix's projects, each with its own windows, and its 95% range resamples the crashes 2,000 times, so a crash that hurt several people moves it as a unit, the rest of the city's counts are held fixed, which narrows the range a little. "Fewer a year" is the after count we'd expect at the city's rate minus the count we saw, per year. A row is a clear drop only when its range stays below zero, the same test one window earlier shows no change, and it passes a Holm correction across every row on the chart. A corridor starts the day after the completion period SFMTA states on its project page or in the [2022 Safe Streets Evaluation summary](https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf). Citywide: 2021 3,517, 2022 3,669, 2023 3,733, 2024 3,757, 2025 3,604 people hurt. [DataSF nwes-mmgh — queried 2026-10-20] [inference — mine, the method]

[^29]: SFMTA, [Safe Streets Evaluation Program 2024 Annual Report](https://www.sfmta.com/reports/safe-streets-evaluation-program-2024-annual-report) ([story map](https://arcg.is/1D8PPf)): "The collision analysis compares collisions up to three years prior to a project's implementation to collision data from the most recent three years at the time of this report's analysis (April 2022 through March 2025)." [primary — read 2026-10-19] It counts collisions, not people hurt, so its percentages and ours measure different things.

[^30]: [Vision Zero Committee deck](https://www.sfmta.com/media/44957/download?inline), May 2026, slide 23: "One year after launching speed cameras in San Francisco, the share of drivers speeding 10 mph or more is down nearly 80 percent across camera locations compared to pre-implementation." Slide 28: "Evaluation of system effectiveness at 18-months (September 2026 for San Francisco)" on speed criteria only. [primary — read 2026-10-19]

[^31]: [2024 report](https://arcg.is/1D8PPf), Collision Data Highlights: "overall collisions ... at project locations fell by 2%, a small reduction likely swayed by a minority of projects that reported an increase in collisions", pedestrian "-32%", bike "-15%". [primary — read 2026-10-19] Our 31 corridors are the 34 projects in that report less the citywide left-turn program and the Page Street neighborway, which have no corridor extent. The report does not say which 27 had crash data. [inference — mine]

[^32]: [2024 report](https://arcg.is/1D8PPf), Collision Analysis of Tenderloin Projects: overall "-44.0%", "the Jones Street Quick-Build saw average annual pedestrian crashes drop by 33%" and "the Golden Gate Avenue and Taylor Quick-Build Projects cut the average annual pedestrian collisions by half (52%)". [primary — read 2026-10-19]

[^33]: SFMTA, [Tenderloin Daylighting Project](https://sfmta.com/media/14930/download) sheet: "One to two parking spaces per approach on each side of the street was removed and replaced with red zones", "180 parking spaces were removed at 80 intersections", "the intersections of Jones Street at Ellis and Eddy streets experienced more collisions". No method or comparison given. [primary — read 2026-10-20] Date from SFMTA's blog of 2015-03-20: "we recently improved 80 intersections in the Tenderloin with daylighting" ([Daylighting Makes San Francisco Crosswalks Safer](https://www.sfmta.com/node/13179)). [primary — read 2026-10-20] We count 67 intersections of the area's named streets inside Market, Mason, Pine and Larkin, and the 165 blocks of those streets between them. SFMTA's list of 80 is not published, and the 13 extra are most likely where alleys such as Olive, Willow and Cosmo meet those streets. [inference — mine]

[^34]: First day per location in DataSF [d5uh-bk84](https://data.sfgov.org/d/d5uh-bk84), issued_citations starts 2025-08-05 at every location. SFMTA says the program launched 2025-03-20 and all cameras were issuing warnings by 2025-06-06 ([SFMTA](https://www.sfmta.com/projects/speed-safety-cameras)). [primary — read 2026-10-20] Counted from citations: everyone at the block −14% (−38% to +20%), with two blocks −12% (−25% to +3%). [inference — mine] Cost: "The anticipated total cost of this five-year pilot program is $7.4 million. This covers permitting, installation, operations and maintenance." ([SFMTA blog](https://www.sfmta.com/blog/one-year-speeding-down-79-speed-safety-camera-locations), May 2026) [primary — read 2026-10-20]

[^35]: About 154 people hurt in each window separate a 20% change from noise at 95%. The pooled camera blocks have 167 and 139 so far. [inference — mine]

[^36]: Regression to the mean: a site picked because its recent counts were high tends to fall afterwards with no treatment. The rest-of-city comparison does not remove it. A matched comparison of untreated streets with the same prior counts would. [inference — mine]

[^37]: The surrounding blocks are the segments three to eight steps out from the site, which share the site's neighborhood traffic. A likely cause is that downtown traffic fell more than the city's after March 2020, but no traffic count was opened for this page. [unretrieved — verify]

[^38]: Quarterly people hurt, 2018 to 2023: 2018Q1 1,051, 2018Q2 1,023, 2018Q3 995, 2018Q4 1,073, 2019Q1 953, 2019Q2 1,076, 2019Q3 1,129, 2019Q4 1,239, 2020Q1 918, 2020Q2 541, 2020Q3 724, 2020Q4 810, 2021Q1 756, 2021Q2 881, 2021Q3 953, 2021Q4 927, 2022Q1 769, 2022Q2 983, 2022Q3 928, 2022Q4 989, 2023Q1 831, 2023Q2 859, 2023Q3 994, 2023Q4 1,049. The downtown box is east of longitude −122.425 and north of latitude 37.765. "Other" victims rose as scooters arrived. [DataSF nwes-mmgh — queried 2026-10-20]

[^39]: SFDPH, [Severe Traffic Injury Trends 2011-2018](https://www.visionzerosf.org/wp-content/uploads/2019/09/Severe-Injury-Trends_2011-2018_final_report.pdf), Appendix A, Table A: 283 in 2018. [primary — read 2026-10-20] Our query: victim_degree_of_injury = 'Severe Injury' in 2018, 283 rows. [DataSF nwes-mmgh — queried 2026-10-20]

