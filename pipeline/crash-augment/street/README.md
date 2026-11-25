# crash-augment/street

This step gives every injury crash in DataSF's crash table ([ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx)) the street context in force on its crash date. That context is the speed limit, the street class and corner type, lanes, traffic, whether it is in an Equity Priority Community, and whether a painted safety zone, speed camera, traffic calming, Slow Street or signal was there. Each field has a `<field>_basis` column that says whether the source let us date the value.

    python3 pipeline/crash-augment/street/crash-street-context.py            # from held copies; no network once held
    python3 pipeline/crash-augment/street/crash-street-context.py --update   # ask each source whether it changed first
    python3 pipeline/crash-augment/street/street_checks.py                   # re-check the held table
    python3 pipeline/crash-augment/street/tests/test_crash_street.py         # rules and checks on made-up input

Plain Python 3, standard library only.

## Files

| File | What it does |
| --- | --- |
| `crash-street-context.py` | The build. Reads the sources, applies the rules, runs the checks and writes the outputs. |
| `street_sources.py` | Fetches each source, checking its change marker first, and holds the copies on disk. |
| `street_fields.py` | The rule for each field, as code. Its docstring repeats the rules below. |
| `street_geo.py` | Point in tract, and distance from a point to a centerline. |
| `street_checks.py` | The quality checks. |
| `street_paths.py` | Where the outputs go. |
| `tests/test_crash_street.py` | Tests of the field rules, and of each check failing on bad input. |

Outputs:

- `out/crash-augment/street/crash-street.csv` has one row per crash, keyed by `case_id_pkey` and sorted by it. It is about 19 MB and gitignored.
- `out/crash-augment/street/summary.json` is tracked. It holds the row counts, each source's read date and size, how each crash was joined to a block, where each camera site was placed, and each field's coverage and values by basis, for all crashes and for those where someone was killed or severely injured (KSI).

Neither file carries a run date, and a file whose content hasn't changed isn't rewritten.

## The basis column

| Basis | Meaning |
| --- | --- |
| `dated` | The source records when the thing changed, so the value is the one in force on the crash date |
| `current_state_only` | The source holds only today's state, so the value is today's whatever the crash date |
| `definition_acs2022` | `in_epc` only. MTC's 2050 Plus EPC definition, built on ACS 2018–2022, applied to every year |
| `not_applicable` | `corner_type` only. The crash isn't coded at an intersection |
| `unknown` | No value. Nothing joins, an undated record may or may not predate the crash, or the code isn't a value |

A value is empty exactly when its basis is `unknown` or `not_applicable`, and a check enforces this.

## Which block a crash is on

The crash row carries an intersection CNN (`cnn_intrsctn_fkey`) and, on about 45% of rows, a segment CNN (`cnn_sgmt_fkey`) [DataSF ubvf-ztfx — queried 2026-11-25]. The block fields are speed limit, street class, lanes, BCI traffic, traffic calming and Slow Street. They read the blocks named in `street_block_cnns`, chosen by `street_block_join` as follows:

| `street_block_join` | Rule |
| --- | --- |
| `segment` | The crash's own segment CNN |
| `node_primary_rd` | No segment CNN. The blocks meeting at the intersection CNN (a block's `f_node_cnn` or `t_node_cnn` in [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h)) that carry the primary road's name |
| `node_all` | As above, when no block there carries that name: every block meeting there |
| `none` | Neither CNN joins |

At a node, retired blocks are used only when no active block meets there. Freeway and ramp centerlines are left out wherever a surface street meets the same node, because Highway 1 and the Central Freeway share nodes with the streets under them, and the crash table holds surface crashes. Street names are matched without spaces or leading zeros, so "07TH ST" matches "7TH ST" and "BAY SHORE BLVD" matches "BAYSHORE BLVD".

When more than one block is read, the field takes the following value, and the basis is the least certain basis among the blocks that gave a value:

- the highest number among the blocks that have one (speed limit, lanes)
- the most major class
- the heaviest traffic
- for presence flags, true if any block has the thing

## Columns and rules

| Column | Source | Rule | Basis |
| --- | --- | --- | --- |
| `in_epc`, `epc_tract` | MTC Equity Priority Communities, PBA 2050 Plus ([ArcGIS layer](https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/draft_equity_priority_communities_pba2050plus_acs2022a/FeatureServer/0)), 242 SF tracts, `epc_2050p` [MTC EPC layer — queried 2026-11-25] | The crash point (`tb_latitude`, `tb_longitude`) falls in the tract (even-odd rule). A crash on a boundary street goes to whichever tract holds its geocoded point | `definition_acs2022` |
| `posted_speed_limit_mph`, `posted_speed_limit_source` | SFMTA Speed Limits per Street Segment, [3t7b-gebn](https://data.sfgov.org/d/3t7b-gebn) [DataSF 3t7b-gebn — queried 2026-11-25] | A 0 is the 25 mph default and 99 marks a freeway; the dataset's own summary says both. A block now at 20 mph that has an `install_date` was 25 before that date and 20 from it on. The SFMTA Board resolutions behind the 20 mph program (210119-014, 210316-037, 211207-140, 220621-052, 240917-106) give each segment's prior limit as 25 [secondary — verify]. The rule uses the install date because the layer changes at Board approval. Every other block takes today's value. A block the layer doesn't list (a CNN split since) takes the highest limit of the same street's blocks at its two ends, and `posted_speed_limit_source` is then `adjacent_block` | `dated` for blocks now at 20 with an install date, `current_state_only` otherwise, `unknown` for 99 or no row |
| `street_class` | [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h) `classcode`: 1 freeway, 2 major, 3 arterial, 4 collector, 5 residential, 6 ramp, 0 other. [DataSF 3psu-pn9h — queried 2026-11-25] | The crash block's class | `current_state_only` |
| `corner_type` | 3psu-pn9h | Only for crashes whose `intersection` begins "Intersection" (`<= 20ft` and `Rear End <= 150ft`). Each street meeting at the intersection CNN takes its most major block's class, and the two most major are named major first, e.g. `arterial_x_residential`. A node with one street gives `<class>_only` | `current_state_only`; `not_applicable` for midblock crashes |
| `lanes`, `lanes_am`, `lanes_pm` | SFMTA [MTA.CTA_trafficlanes](https://services.sfmta.com/arcgis/rest/services/DataSF/master/MapServer/54), 15,444 blocks, `LANES_OP`, `LANES_AM`, `LANES_PM` [SFMTA ArcGIS layer — queried 2026-11-25] | The raw counts. On two-way streets the count appears to be one direction, and the layer doesn't say so [inference — mine]. A 0 is kept as given | `current_state_only` |
| `bci_traffic_category` | SFMTA [Bike Comfort Index](https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4), 15,280 blocks, `traffic_category_ft` and `_tf`, last edited 2023-05-01 [SFMTA ArcGIS layer — queried 2026-11-25] | The heavier direction, as `light`, `medium` or `heavy` | `current_state_only` |
| `painted_safety_zone` | [vtn2-q8ky](https://data.sfgov.org/d/vtn2-q8ky), 286 zones at intersection CNNs, every one with `install_da` [DataSF vtn2-q8ky — queried 2026-11-25] | A zone at the crash's intersection CNN, installed on or before the crash date. A midblock crash is false, because the zones are corner treatments | `dated` |
| `speed_camera_corridor` | [d5uh-bk84](https://data.sfgov.org/d/d5uh-bk84), 56 sites, first day 2025-04-01 [DataSF d5uh-bk84 — queried 2026-11-25] | Each site goes on the nearest active block of the street in its `location`, within 400 ft. Two sites at "2300 16TH ST" sit 314 ft from 16th St. The corridor is that block, the next block of the same street at each end, and their intersections. A crash is in it if its segment CNN is a corridor block, or if it is coded at a corridor intersection (or has only an intersection CNN). The flag is true from the site's first day in the data | `dated` |
| `traffic_calming`, `traffic_calming_types` | [abhw-ffzx](https://data.sfgov.org/d/abhw-ffzx), 1,686 measures [DataSF abhw-ffzx — queried 2026-11-25] | True when a `Complete` measure on the block was installed on or before the crash date. The value is unknown in two cases: the block has a `Complete` measure with no `install_datetime` (blank or the 1900-01-01 placeholder), or it has an `Obsolete` or status-less measure that can't be placed against the crash date. Otherwise false. Pending measures don't count | `dated`; `unknown` as above |
| `slow_street` | [hkz3-itiu](https://data.sfgov.org/d/hkz3-itiu), the `Implemented` rows [DataSF hkz3-itiu — queried 2026-11-25] | An `Implemented` row on the block, installed on or before the crash date. An undated row is false before the dataset's earliest install date and unknown from then on. Removals aren't recorded, and the dataset was last edited 2024-01-18 | `dated` |
| `signal_present` | [ybh5-27n2](https://data.sfgov.org/d/ybh5-27n2), types `SIGNAL`, `SIGNAL (CONTRACTOR MAINTAINED)` and `CALTRANS` [DataSF ybh5-27n2 — queried 2026-11-25] | For a crash coded at an intersection, a signal at its intersection CNN; for a midblock crash, a signal on its segment CNN. A `startyear` before the crash year is true; the crash year itself is unknown. A `startyear` of 0 or 9999 is true for today only. Removed signals aren't in the inventory. The crash row's own `control_device` is the officer's record, and it stays in ubvf-ztfx | `dated`; `current_state_only` with no usable year |

The crash row count never changes. The build asserts it, and the `rows` check fails on any crash dropped, repeated or invented.

## Incremental fetch

`--update` asks each source for its change marker before reading it:

- **Crash table (ubvf-ztfx):** read from the held copy [`../crash_tables.py`](../crash_tables.py) keeps for every lane, which reads only the rows whose `data_updated_at` moved (see [`../README.md`](../README.md)). This step's `--update` refreshes it first unless `CRASH_TABLES_HELD` is set, as `../crash-augment.py` sets it after refreshing once.
- **Other DataSF tables:** `rowsUpdatedAt`. A held query is re-read when that marker differs from the one recorded at its last read (`data/socrata-cache/crash-augment-street/_markers.json`), or when the held rows no longer hash to what that read wrote.
- **EPC and BCI layers:** `editingInfo.dataLastEditDate` and the row count.
- **Lane layer:** it publishes no edit date and its `LAST_EDITED_DATE` is empty, so every `--update` re-reads it whole. That is attributes only, 16 requests.

A re-read is the whole query, and it replaces the held copy only when it holds at least 90% of the held rows. A failed re-read keeps the held copy and is recorded as failed under `crash-street:<source>` in `data/pipeline-state/sources.json`. Held copies live in gitignored folders: `data/socrata-cache/crash-augment-street/` and `.cache/crash-augment/street/`. Without `--update`, a build with every copy held makes no network request.

## Checks

`street_checks.py` runs on every new table before it replaces the held one. Any failure keeps the held files and exits 1.

- **Rows:** one output row per input crash, with none dropped, repeated or invented. The count is within 2% below or 10% above the previous summary's.
- **Key:** `case_id_pkey` is unique.
- **Coverage:** each field's share of crashes with a value is at or above its floor in `FLOORS`, and no more than 3 points below the previous build's share. `corner_type`'s share is over intersection crashes.
- **Basis:** every basis is an allowed value, and the value is empty exactly when the basis is `unknown` or `not_applicable`.
- **Ranges:**
  - speed limits run from 15 to 65 in steps of 5
  - lanes run from 0 to 10
  - classes and corner types come from the 3psu-pn9h codes
  - BCI traffic is `light`, `medium` or `heavy`
  - flags are `true` or `false`
  - EPC tracts are in San Francisco (06075)
- **Dated sanity:** no dated 20 mph limit before 2018, and no camera corridor flag before 2025.
- **Sources:** every input is at or above its floor, and every camera site is placed on a block.

## Known limits

- Street class, lanes and BCI traffic are today's values. Any figure that uses them should pool all years or cover recent years only, and say which.
- Speed limits are dated only for the 20 mph program. A block whose limit changed in another way (289 rows now at 25 and 218 at 30 carry an install date) shows today's limit [DataSF 3t7b-gebn — queried 2026-11-25].
- The inventories record installs, not removals. That applies to signals and Slow Streets, and to traffic calming except the measures marked `Obsolete`.
- `in_epc` describes the tract, not the street, and uses one census vintage for every year.
