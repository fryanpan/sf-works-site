# Speed camera trial: locations needed per design — 2026-11-01

Question: how many camera locations each of three designs (corridors, several cameras per school zone, mobile cameras) needs for SF to get a statistically clear answer on injuries, and the cap this implies.

Script: [`tools/street-safety/speed-camera-sites-needed.py`](../../tools/street-safety/speed-camera-sites-needed.py). Run with `uv run --no-project --with numpy --with scipy python tools/street-safety/speed-camera-sites-needed.py`. It prints every table below and writes no file. Output is seeded and repeats exactly.

Data: per-location counts in [`data/extract/speed-cameras/camera-injuries.json`](../../data/extract/speed-cameras/camera-injuries.json), built by `scratch/hin-map/hin_split.py` from DataSF [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) (victims fetched 2026-10-20, data to 2026-08-31), plus the same cached nwes-mmgh query for crash and place rates, SFMTA's 2022 High Injury Network (`data/extract/access/hin-2022.json`) and the 113 School Trips school points (`site/data/school-sim/index.json`). Nothing was refetched. Every figure here is [inference — mine, DataSF nwes-mmgh — queried 2026-10-20 copy].

**Counting.** A location is one system under the §22425 cap. SFMTA counts its 56 cameras at 33 locations as 33 systems, and the law defines a system as "a fixed or mobile radar or laser system or any other electronic device" ([§22425(a)(6)](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=22425)). So a corridor is 4 locations, a school zone 3, and one mobile system serves 4 locations.

## Answer

SF's own cameras have cut all injuries within two blocks by 13% so far: a ratio of 0.87 (0.75 to 1.00) against the rest of the city (severe-injuries note, section 1). The 15%, 20% and 30% columns are assumed effects, not results.

Locations under the cap, including today's 33, for 80% power at two-sided alpha 0.05 with one matched control per treated unit. Each range runs from the low τ² (REML) with mobile at the full drop to the high τ² (DL) with mobile at half the drop. School zones are held to all 113 schools (56 treated, 57 controls, 168 locations); the power column is that school-zone trial's power, since corridors and mobile are sized to reach 80% on their own.

| Outcome, windows | 13% drop (SF's result) | 15% (assumed) | 20% (assumed) | 30% (assumed) |
| --- | --- | --- | --- | --- |
| All injuries, 18 months each side | 440–743, schools 0.26–0.34 | 381–602, 0.33–0.43 | 300–418, 0.55–0.68 | 167–251, 0.91–0.97 |
| All injuries, 3 years each side | 323–583, schools 0.38–0.58 | 291–481, 0.49–0.71 | 197–355, 0.75–0.93 | 104–173, 0.99–1.00 |
| All injuries, 3 years before, 18 months after | 386–663, schools 0.30–0.42 | 336–546, 0.39–0.53 | 278–387, 0.63–0.79 | 137–217, 0.95–0.99 |
| Pedestrians, 18 months each side | 1,169–1,731, schools 0.11 | 917–1,332, 0.13–0.14 | 588–818, 0.21–0.22 | 359–457, 0.43–0.46 |
| Pedestrians, 3 years each side | 687–1,073, schools 0.16–0.19 | 561–848, 0.21–0.24 | 395–553, 0.34–0.39 | 282–345, 0.69–0.75 |
| Pedestrians, 3 years before, 18 months after | 935–1,412, schools 0.13–0.14 | 746–1,098, 0.16–0.17 | 498–693, 0.25–0.27 | 327–406, 0.52–0.56 |

[inference — mine, DataSF nwes-mmgh]

What this says:

- At SF's own 13% on all injuries, a three-design trial needs about 440 to 740 locations to report at 18 months, and about 320 to 580 at 3 years. That is four to nine times the Board's 113 (33 plus 80, [Resolution 408-26](https://sfgov.legistar.com/LegislationDetail.aspx?ID=8008866&GUID=B1FBD6C3-549E-4BE9-A81A-B01ACEA90488)) [Legistar — read 2026-10-31]. At an assumed 20%, it is about 300 to 420 at 18 months and 200 to 360 at 3 years. Corridors of 2 locations instead of 4 trim each total by about 10% to 20% (see Sensitivity). [inference — mine, DataSF nwes-mmgh]
- SF has too few schools for a school-zone test of a 13% to 20% drop on all injuries. 56 treated schools give it a 26% to 58% chance of a clear answer at 13%. Only a 30% drop, or 20% over 3 years at the low τ², fits within 113 schools. Unconstrained, the school-zone rows alone would ask for 95 to 257 treated schools at 13%. [inference — mine, DataSF nwes-mmgh]
- With pedestrians as the primary outcome, every design needs about three to four times the locations, and no school-zone test reaches 80% at any effect. SF's pedestrian ratio is 0.66 (0.47 to 0.88), a 34% drop, but pedestrian injuries rose from 102 to 115 before the cameras, so part of it may be regression to the mean. [inference — mine, DataSF nwes-mmgh]
- Killed-or-severe can't be the primary test at any cap near 113: at 3 years each side it needs about 1,040 to 1,560 locations at 13% and 340 to 430 at an assumed 30%, with school zones at about 0.4 power even then. [inference — mine, DataSF nwes-mmgh]
- Mobile is a range, not a point. At 13% on all injuries over 18 months, it needs 38 systems if each served location gets the fixed-camera drop, and 158 if it gets half, the UK ratio (28% against 51% for KSI, [PA Consulting and UCL 2004](https://discovery.ucl.ac.uk/id/eprint/1338/1/2004_31.pdf)) primary — read 2026-11-01, via the [school-zone and mobile evidence note]. Both figures assume one system covers 4 locations. [inference — mine, DataSF nwes-mmgh]

## Assumptions

1. **The test.** Before-after with matched controls: the log of (treated after/before) over (control after/before), pooled over units the way the 33-location analysis pools, two-sided at 5%. Windows: 18 months each side, 3 years each side, or 3 years before and 18 months after.
2. **Units that share a random change.** A corridor is one unit of 4 locations over about 10 blocks; a school zone is one unit of 3 locations round one school; a mobile location is its own unit. Locations in one corridor or school are treated as fully correlated, which is conservative.
3. **Catchment.** A corridor of 4 locations two blocks apart counts 2.0 times one location's site-plus-two-blocks window. Shorter corridors scale as (locations + 2) / 3: 1.67 for 3 locations, 1.33 for 2. A school zone counts 1.5 times, a mobile location 1.0.
4. **Injury rate.** Today's 33 locations average 15.2 injured people, 1.26 KSI and 2.48 pedestrians per location-year within two blocks, the mean of the window before the cameras and the one before that (646/682, 57/53, 102/115, from the severe-injuries note). New places scale that by their 660 ft radius count over 2021-09-01 to 2025-03-31, which ends before the first camera. The pool for corridors and mobile is every HIN block midpoint more than 660 ft from a current camera (2,118 of 2,388); its average has 1.13 times the injuries of today's locations (1.37 for KSI, 1.21 for pedestrians). The average school has 0.42 times (0.40, 0.44).
5. **Overdispersion.** Several people hurt in one crash inflate a victim count's variance by 1.61 for all injuries and 1.15 for KSI and pedestrians (sum of n² over sum of n, by crash, same window). Beyond that, the true change varies by location by τ². For all injuries at the 33 locations, DerSimonian-Laird gives τ² = 0.035 and REML gives 0, with a 95% upper bound of 0.352. Nothing in this data chooses between them, so results are shown at both. The all-injury value is used for every outcome. The spread of true place rates (CV², from each pool's radius counts net of count noise) is 0.86 for the camera locations, 0.51 for HIN blocks and 1.41 for schools, and multiplies τ²'s effect by 1 + CV².
6. **Matched controls** have the same expected count and τ² as the treated unit. School controls come from the same 113 schools as treated ones.
7. **Effect.** The drop holds at every treated place for the whole after window. Mobile gets the full drop or half of it.
8. **No citywide trend difference** beyond what the controls absorb, and no spillover onto control streets. Spillover would bias the estimate towards zero, so controls should sit outside the treated area's ring.

## Checks

- **Model check, Poisson and φ term only.** For today's 33 locations the model gives a standard error of 0.160 on the pedestrian log ratio at τ² = 0 and 0.166 at the DL τ²; the published 0.66 (0.47 to 0.88) implies 0.160. That interval is a bootstrap over crashes, so the match checks the count-noise term, not τ². τ² has no check in this data. [inference — mine, DataSF nwes-mmgh]
- **Formula against simulation under the same model.** At the computed sizes, 4,000 simulated trials per case (gamma-distributed place rates, lumpy victim counts, normal location-level change, cluster-robust standard error) gave power of 0.79 to 0.81 in all nine cases tried. This checks the arithmetic, not the model.
- **Control streets.** The ring of blocks 3 to 8 hops out from each location shows τ² of 0 under both estimators (upper bound 0.009 for all injuries). Those areas are about ten times larger, which suggests τ² falls as units grow, so the corridor rows may be high.
- **Multiple testing.** Three designs each tested at 5% give a 14% chance that at least one shows a drop when none works; holding that to 5% (Bonferroni) multiplies every unit count by 1.33. [inference — mine]

## Sensitivity

Locations including today's 33, all injuries, mobile at full to half drop. [inference — mine, DataSF nwes-mmgh]

| Windows | τ² | Sites from | 13% drop | 20% drop | 30% drop |
| --- | --- | --- | --- | --- | --- |
| 18 months | REML | every HIN block and school, schools unconstrained | 839–924 † | 360–395 † | 167–182 |
| 18 months | DL | same | 1,226–1,346 † | 506–556 † | 229–251 |
| 18 months | DL, 95% upper (0.352) | same | 4,739–5,179 † | 1,878–2,060 † | 762–840 † |
| 3 years | REML | same | 440–482 † | 197–214 | 104–111 |
| 3 years | DL | same | 826–904 † | 350–382 † | 159–173 |
| 3 years | DL, 95% upper (0.352) | same | 4,336–4,733 † | 1,715–1,879 † | 699–769 † |
| 18 months | REML | worse half of each pool | 510–565 † | 225–248 † | 114–124 |
| 18 months | DL | worse half of each pool | 897–987 † | 378–416 † | 174–190 |

† School zones need more schools than exist (113, or 57 in the worse half).

**Corridor length.** SF's High Injury Network streets are shorter than Philadelphia's Roosevelt Boulevard, which has about one location per 1 to 1.5 miles, so corridors of 2 or 3 locations are also shown. A shorter corridor carries fewer injuries, so it takes more corridors but fewer locations in total. Totals below include today's 33, with school zones held to the pool, from REML with mobile at the full drop to DL with mobile at half. [inference — mine, DataSF nwes-mmgh]

| Outcome, windows | Locations per corridor | Corridors needed at 13% | 13% drop | 20% drop | 30% drop |
| --- | --- | --- | --- | --- | --- |
| All injuries, 18 months | 4 | 53–96 | 440–743 | 300–418 | 167–251 |
| All injuries, 18 months | 3 | 64–107 | 420–680 | 290–392 | 164–238 |
| All injuries, 18 months | 2 | 80–122 | 388–603 | 276–364 | 157–227 |
| All injuries, 3 years | 4 | 27–70 | 323–583 | 197–355 | 104–173 |
| All injuries, 3 years | 3 | 32–75 | 311–528 | 192–333 | 102–165 |
| All injuries, 3 years | 2 | 40–83 | 295–469 | 185–309 | 98–155 |
| Pedestrians, 18 months | 4 | 215–258 | 1,169–1,731 | 588–818 | 359–457 |
| Pedestrians, 18 months | 2 | 322–365 | 953–1,429 | 502–698 | 325–407 |
| Pedestrians, 3 years | 4 | 108–150 | 687–1,073 | 395–553 | 282–345 |
| Pedestrians, 3 years | 2 | 161–204 | 577–881 | 353–475 | 264–315 |

Three controls per unit cost no cameras for corridors and mobile, but the school pool can't supply them: with k = 3, school zones reach 80% for all injuries only at a 30% drop (and at 20% over 3 years at the REML τ²), and never for pedestrians. Where it fits, k = 3 brings the 18-month, 30% total to 131–141 (REML) or 169–183 (DL). Picking the worst half of places shrinks the trial but makes regression to the mean worse, which controls matched on the same before-period counts would have to absorb.

## Weakest assumption

τ², the location-to-location spread in how injuries change. REML puts it at 0 and DL at 0.035, and its 95% range runs to 0.352; at the top of that range the cap rises about fivefold. Next is the school pool, which rules out a school-zone test of any drop SF has seen. Mobile's 4-locations-per-system rotation and its per-location effect come third: together they move mobile by a factor of about four. A 3-year trial would let SF re-estimate τ² from its first 18 months before deciding whether to add sites.

## Gaps

- The 26% estimate (a 52% drop to a 13% rise) has no script path, and no script in `scripts/` or `scratch/` reproduces it. This note reuses the per-location counts and the ratio-of-ratios method of `hin_split.py`, which produced the 115 to 71 figures and the 0.66 (0.47 to 0.88) interval, and checks against that interval.
- Place rates use a 660 ft radius around a point, not the two-block street window, and only as a ratio to today's locations measured the same way.
- The HIN pool hasn't been checked for room. Up to about 240 corridors (treated plus controls, at 2 locations each) have not been laid out on the 2,118 remaining HIN segments. [unretrieved — verify]
