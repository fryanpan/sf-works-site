# SF High Injury Network: the 2017, 2022 and 2024 versions

**What it is.** The Vision Zero High Injury Network (HIN) is the set of street corridors where SFDPH found the most people severely injured or killed per mile. SFDPH draws it with SFMTA, and each version is redrawn from a new window of injury data. Three versions have public geometry. [primary — read 2026-11-18]

**Where it lives.**

| Version | Layer | One row is | Key | Length field |
| --- | --- | --- | --- | --- |
| 2017 | [ArcGIS `vz_hin_2017_single_line`](https://services.arcgis.com/Zs2aNLFN00jrS4gG/arcgis/rest/services/vz_hin_2017_single_line/FeatureServer/0), owner `dph.opendata_sfgov`, created 2017-07-20 | one corridor (135 rows). Despite the layer's name, some divided streets are drawn on both sides: 167.4 drawn miles against a `length` total of 128.9 | `OBJECTID` (no block id) | `length`, miles |
| 2022 | [DataSF 8vtn-qytr](https://data.sfgov.org/d/8vtn-qytr), loaded 2024-08-20. Also the ArcGIS `hin2022` layer cached in `data/extract/access/hin-2022.json` | one centerline block, repeated up to 5 times (7,988 rows, 2,388 blocks) | `cnn_sgmt_pkey` | `corrected_length_miles`, which halves each side of a dual carriageway |
| 2024 | [DataSF enwt-3u8m](https://data.sfgov.org/d/enwt-3u8m), loaded 2026-03-23. Also the ArcGIS `HIN` layer in `data/extract/access/hin-2024.json` | the same shape (5,917 rows, 1,917 blocks). 471 rows carry a dual-carriageway id in `cnn_sgmt_pkey`, not a centerline block id | `cnn_sgmt_pkey` | `corrected_length_miles` |

None of the three updates. DataSF marks both of its datasets "As needed" or "Not updated (historical only)". [DataSF 8vtn-qytr — queried 2026-11-18] [DataSF enwt-3u8m — queried 2026-11-18]

## What each version used

| | 2017 | 2022 | 2024 |
| --- | --- | --- | --- |
| Injury window | 2013 to 2015 | 2017 to 2021 | 2020 to 2024 |
| Sources | SFPD reports linked to ZSFG patients (TISS, probabilistic match with LinkSolv), ZSFG-only severe injuries, Medical Examiner deaths | The same, plus EMS records | SFPD, the ZSFG Trauma Registry and AMR and SFFD EMS records, linked by a deterministic match |
| Threshold | 7 or more severe and fatal injuries per mile on a section of about a quarter mile | 10 or more per mile | 10 or more per mile |
| Crash assignment | Only injuries whose primary street is the section's street | The same | Points that "geographically intersect" a corridor |
| Extra rules | 2015-network sections with 6 or more per mile or a 2013 to 2016 fatality kept. Manual additions for a 2016 and two 2017 fatalities. Five sections removed where one intersection drove the count | Sections driven by one intersection removed (Portola, Jamestown). The fatality rule was dropped | "Stubs" more than 500 ft past the last KSI on the street removed |

Sources: the [2017 methodology](https://web.archive.org/web/20240115012611/https://www.sfdph.org/dph/files/EHSdocs/PHES/VisionZero/Vision_Zero_High_Injury_Network_Update.pdf), pp. 1 and 18 to 21 [primary — read 2026-11-18]; the [2017 layer's own description](https://www.arcgis.com/home/item.html?id=25d06501f18e458491ca7c6d4e3813b4) [primary — read 2026-11-18]; the [2022 methodology](https://www.visionzerosf.org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf), pp. 3 and 10 [primary — read 2026-11-18]; the descriptions of [8vtn-qytr](https://data.sfgov.org/d/8vtn-qytr) and [enwt-3u8m](https://data.sfgov.org/d/enwt-3u8m) [primary — read 2026-11-18].

The 8vtn-qytr description says its data is "2017-2022" in one paragraph and "(2017-2021)" in the next. The methodology says 2017 to 2021, and we use that. [primary — read 2026-11-18]

## Published total

**Miles.** SFDPH reports 128.9 miles for 2017 (12.8% of city streets) and 121.5 miles for 2022 (12.2%). It defines city streets as excluding "freeways, The Presidio, Fort Mason, and streets closed to vehicles".^[SFDPH, [2017 Update](https://web.archive.org/web/20240115012611/https://www.sfdph.org/dph/files/EHSdocs/PHES/VisionZero/Vision_Zero_High_Injury_Network_Update.pdf), Table 1; [2022 methodology](https://www.visionzerosf.org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf), Table 1. [primary — read 2026-11-18]] For 2024, DPH's Health Commission deck gives 93 miles kept from 2022 and 39.9 added, so 132.9 miles. SFMTA gives 13% of streets.^[SFDPH, [Health Commission deck, 2026-08-17](https://media.api.sf.gov/documents/PHD-PPT-High_Injury_Network_Health_Commission_v5_2026-08-17_FINAL.pdf), slide 11; SFMTA, [HIN blog](https://www.sfmta.com/blog/new-high-injury-network-map-helps-guide-us-safer-city). [primary — read 2026-11-18]] Our sums are 128.9 miles from the 2017 layer's `length` field, 121.5 from 8vtn-qytr and 132.9 from enwt-3u8m, each deduplicated on `cnn_sgmt_pkey`. All three match to the tenth of a mile.^[[`tools/street-safety/hin-versions.py`](../../tools/street-safety/hin-versions.py). [DataSF 8vtn-qytr — queried 2026-11-18] [DataSF enwt-3u8m — queried 2026-11-18]]

**Change between versions.** The 2022 methodology gives 76.7 miles of the 2022 network overlapping the 2017 one. Our geometric match gives 77.0. The Health Commission deck gives 93 miles kept, 39.9 added and 28.6 removed from 2022 to 2024. Ours gives 93.1, 39.7 and 28.3.

```
python3 tools/street-safety/hin-versions.py   # out/hin-versions/summary.json: overlap_2017_2022, churn
```

**Share of severe and fatal injuries.** These can't be reproduced from public data. The published shares (74.6% for 2017, 68.2% for 2022, 74% for 2024) count hospital-only injuries and hospital severity, which DataSF's police reports lack. With police reports alone ([DataSF nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)) and our 60 ft rule, each version's own window gives 540 of 721 (74.9%) for 2017, 1,021 of 1,476 (69.2%) for 2022 and 1,132 of 1,476 (76.7%) for 2024. That's within 1 point of the published share for 2017 and 2022, and 2.7 points above it for 2024.^[[`tools/street-safety/hin-versions.py`](../../tools/street-safety/hin-versions.py). [DataSF nwes-mmgh — queried 2026-11-18]]

Rule adopted: miles are the agency's `corrected_length_miles` (a divided street counts once), or the 2017 layer's `length`. A person is on a version when the police report places them within 60 ft of its lines. Shares are of people with a map location. For streets kept, dropped or added between versions, a person counts on a street only when the report's primary road is that street, the HIN's own rule.

The 2017 to 2021 and 2020 to 2024 windows both hold 1,477 people severely injured or killed in police reports, one of them unplaced. That's a coincidence of the yearly counts, not a copy error.
