# crash-augment

This pipeline adds columns to DataSF's three injury-crash tables, which are built from SFPD's crash reports. Parties and victims get a clean vehicle make, a clean model and an estimated curb weight. Each crash gets the street it happened on as it was that day, plus the heaviest vehicle involved. Every DataSF column is kept, so the output tables replace the originals in any analysis.

    python3 pipeline/crash-augment/crash-augment.py --update   # ask every source what changed, read only that, rebuild, check
    python3 pipeline/crash-augment/crash-augment.py            # rebuild from the held copies (no DataSF read once held)
    python3 pipeline/crash-augment/crash-augment.py --check    # run every check on the current tables, build nothing
    python3 pipeline/crash-augment/tests/test_crash_augment.py # fetch and check tests, fake DataSF, no network

It needs Python 3 and the standard library only. The scheduled refresh runs it daily as the step `crash-augment` in [`pipeline/transportation-update.py`](../transportation-update.py), A first run from a clean checkout takes about half an hour: about seven minutes reading DataSF, and the rest asking vPIC, one request every 0.6 seconds. A run with nothing new takes about a minute.

## Inputs

| Table | DataSF id | One row per | Key | Rows on 2026-11-25 |
| --- | --- | --- | --- | ---: |
| Traffic Crashes Resulting in Injury | [ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx) | crash | `case_id_pkey` | 66,991 |
| Parties Involved | [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6) | driver, pedestrian, bicyclist or other party | `unique_id` | 140,843 |
| Victims Involved | [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) | person injured or killed | `unique_id` | 84,943 |

[DataSF ubvf-ztfx, 8gtc-pjc6, nwes-mmgh — queried 2026-11-25]

The vehicle columns also read NHTSA's [vPIC API](https://vpic.nhtsa.dot.gov/api/) for make and model names and Transport Canada curb weights. The street columns read eight more DataSF tables and three ArcGIS layers, which [`street/README.md`](street/README.md) lists.

## Outputs

The tables are written to `out/crash-augment/tables/`. The CSVs are gitignored, and `summary.json` is tracked.

| File | Rows | Columns |
| --- | ---: | --- |
| `crashes.csv` | one per crash | ubvf-ztfx's columns, then the street columns, then the vehicle rollup |
| `parties.csv` | one per party | 8gtc-pjc6's columns, then the six vehicle columns |
| `victims.csv` | one per victim | nwes-mmgh's columns, then the six vehicle columns. They describe the vehicle the victim was in or on |
| `summary.json` | | Row counts, the columns each table adds, and each input's DataSF marker and read date |

The DataSF columns come in DataSF's order. Four kinds are dropped because they change every night with nothing changed in the crash, or repeat another column: `data_loaded_at`, `point` (`tb_latitude` and `tb_longitude` hold it), and Socrata's `:@computed_region_*` columns. Rows are in collision-year order, and by key within a year. Join a victim to its party on `case_id_pkey` and `party_number_ckey`, and a party to its crash on `case_id_pkey`.

## Added columns

### Vehicle columns (parties and victims)

From [`vehicles/`](vehicles/README.md), which gives the parsing rules and match rates.

| Column | Holds | Source |
| --- | --- | --- |
| `vehicle_make_clean` | vPIC's make name, e.g. `TOYOTA`. Empty when unrecognised, and for pedestrians, bicyclists and non-motor body types | `vehicle_make`, read against vPIC's make list |
| `vehicle_model_clean` | vPIC's model name, e.g. `Highlander`. Empty when no model is written, as on most rows before 2018 | `vehicle_make`, read against vPIC's models for the make |
| `estimated_vehicle_weight_lb` | Curb weight in pounds. Empty when there is no source | Transport Canada trims in vPIC, or a body-type average |
| `vehicle_match_method` | `exact_make_model_year`, `model_10yr_avg`, `body_type_avg`, `unmatched` or `not_applicable` | how the weight was found |
| `vehicle_match_reason` | Why a row fell back or has no weight | |
| `vehicle_body_type_clean` | `stwd_vehicle_type` with its typos folded | `stwd_vehicle_type` |

The weight's basis is its method. `exact_make_model_year` is the model in its own model year. `model_10yr_avg` is the model averaged over ten model years when the year is missing or unmeasured. `body_type_avg` is the average exact weight of every party with the same light body type. Transport Canada weighs no motorcycles, buses or heavy trucks, so those rows stay `unmatched`.

### Vehicle rollup (crashes)

| Column | Holds |
| --- | --- |
| `motor_vehicle_parties` | The crash's parties that are motor vehicles (not `not_applicable`) |
| `vehicles_with_weight` | How many of those have a weight |
| `heaviest_vehicle_weight_lb`, `heaviest_vehicle_make_clean`, `heaviest_vehicle_model_clean` | The heaviest of those, whatever its method |

### Street columns (crashes)

From [`street/`](street/README.md), which gives the full rule for each field. Each field has a `<field>_basis` column. Its value is `dated` when the source records when the thing changed, so the value is the one in force on the crash date. It is `current_state_only` when the source holds only today's state, `unknown` when there is no value, and `definition_acs2022` or `not_applicable` where noted. The field is empty exactly when its basis is `unknown` or `not_applicable`.

| Column | Source | Basis |
| --- | --- | --- |
| `street_block_join`, `street_block_cnns` | how the crash was placed on blocks of [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h): its segment CNN, or the blocks at its intersection CNN | |
| `epc_tract`, `in_epc` | MTC Equity Priority Communities, Plan Bay Area 2050 Plus | `definition_acs2022`: one census vintage for every year |
| `posted_speed_limit_mph`, `posted_speed_limit_source` | SFMTA speed limits, [3t7b-gebn](https://data.sfgov.org/d/3t7b-gebn) | `dated` for blocks now at 20 mph with an install date; `current_state_only` otherwise |
| `street_class` | 3psu-pn9h `classcode` | `current_state_only` |
| `corner_type` | 3psu-pn9h, the two most major streets at the intersection | `current_state_only`; `not_applicable` for midblock crashes |
| `lanes`, `lanes_am`, `lanes_pm` | SFMTA traffic lanes layer | `current_state_only` |
| `bci_traffic_category` | SFMTA Bike Comfort Index, traffic of the heavier direction | `current_state_only` |
| `painted_safety_zone` | [vtn2-q8ky](https://data.sfgov.org/d/vtn2-q8ky) | `dated` |
| `speed_camera_corridor` | [d5uh-bk84](https://data.sfgov.org/d/d5uh-bk84): the site's block, the next block each way, and their intersections | `dated` |
| `traffic_calming`, `traffic_calming_types` | [abhw-ffzx](https://data.sfgov.org/d/abhw-ffzx), Complete measures | `dated`; `unknown` for an undated or obsolete measure |
| `slow_street` | [hkz3-itiu](https://data.sfgov.org/d/hkz3-itiu), Implemented rows | `dated` |
| `signal_present` | [ybh5-27n2](https://data.sfgov.org/d/ybh5-27n2) signals | `dated` by `startyear`; `current_state_only` with no usable year |

## As-of-date rules

A dated field is true or valued on a crash only if the thing was in place on or before the crash date. The 20 mph program's blocks are 25 mph before their install date and 20 from it on. A speed camera counts from its site's first day in d5uh-bk84. A signal counts from the year after its `startyear`, and the `startyear` itself is unknown. An undated Slow Street is false before the program's earliest install and unknown after it. `current_state_only` fields carry today's value for every year, so a figure that uses them should pool years or cover recent years, and say which. The vehicle weight is the vehicle's model year where one is written, and otherwise the ten model years up to the crash year.

## How each run stays incremental

1. **Fetch** ([`crash_tables.py`](crash_tables.py)). The three tables are held whole in `data/socrata-cache/crash-augment/`, one gitignored file per collision year. DataSF reloads them every night and stamps every row with the load time, so the marker used is each row's own `data_updated_at`, the day SFPD's record last changed. With `--update` the step asks for `rowsUpdatedAt` and the row count per year. When `rowsUpdatedAt` has moved, it reads only the rows whose `data_updated_at` is on or after the newest one held. It reads that newest day again, because the field is a date. A year whose count differs from DataSF's gets its keys read, and then only its missing rows. Every 90 days the whole table is read again. A refresh with nothing new reads no rows and writes no file.
2. **Vehicles** ([`vehicles/vehicle-fields.py`](vehicles/vehicle-fields.py)) asks vPIC only for makes and model years it hasn't cached (`.cache/crash-augment/vpic/`).
3. **Street** ([`street/crash-street-context.py`](street/crash-street-context.py)) asks each street source for its change marker. SFMTA's lane layer has no marker, so it is re-read whole, which takes 16 requests.
4. **Merge** ([`augment_merge.py`](augment_merge.py)) joins the lanes onto the held rows in a staging folder.
5. **Check** ([`augment_checks.py`](augment_checks.py)) runs on the staged tables. Only if every check passes do they replace the live ones. A file whose bytes are unchanged is not touched.

Both lanes run with `CRASH_TABLES_HELD=1`, so they read the copy stage 1 just checked, and every column describes the same DataSF update.

## Quality checks

Every stage's checks must pass before the next stage runs, and a failure keeps the last good outputs and exits 1. The pipeline runner also runs the merged-table checks after the step, against the snapshot it takes first, and restores the snapshot on a failure.

| Stage | Check | Guards against |
| --- | --- | --- |
| fetch | each year holds exactly DataSF's row count | a dropped, repeated or stray row; a held file cut short or edited |
| fetch | at least the floor, and no more than 2% fewer rows than the last refresh | an empty or truncated read |
| fetch | keys unique across years; key, `case_id_pkey` and `collision_datetime` present; dates from 2005 to tomorrow | a row that moved year held twice; a malformed read |
| vehicles | 34 checks ([list](vehicles/README.md#data-quality)): row counts equal to the inputs, joins, weight bounds by body type, match-rate floors, 76 hand-read strings | a parser or vPIC regression; a unit error; a lost or duplicated row |
| street | 64 checks ([list](street/README.md#checks)): one row per crash, coverage floors, allowed basis values, value ranges, no dated 20 mph before 2018 or camera before 2025 | a join that drops crashes; a source read short; a rule that dates a value it can't |
| merge | rows, key unique, required fields, dates, and at most a 2% fall or 10% rise against the last build, for each table | a truncated or fanned-out table |
| merge | every party's crash is a crash row; every victim's party is exactly one parties row | an orphan or a fan-out between tables |
| merge | every held row found its row in each lane, with none left over or repeated; every table equals its held DataSF table | a lane built on a different read |
| merge | the vehicle lane read the same DataSF update as the tables | lanes mixing two days' data |
| merge | the header is DataSF's columns and then each lane's, and every added column has a value on some row | a lane column lost or emptied |

`tests/test_crash_augment.py` shows a refresh reading nothing when nothing moved, and reading back only a row cut from the held copy. It also shows a refresh reading only the rows whose `data_updated_at` moved, and moving a row whose year changed. Then it shows each fetch and merge check failing on the bad input it guards against. The lanes have their own tests in `vehicles/tests/` and `street/tests/`.

## Known limits

- Street class, corner type, lanes and BCI traffic are `current_state_only`: today's street applied to every year.
- Speed limits are dated only for the 20 mph program. A block whose limit changed another way shows today's limit.
- The inventories record installs, not removals: signals, Slow Streets, and traffic calming except measures marked Obsolete.
- `in_epc` describes the tract, not the street, with one census vintage for every year.
- Before 2018 most `vehicle_make` entries name a make only, so 52% of motor-vehicle weights are a body-type average rather than a model weight. Motorcycles, buses and heavy trucks have no weight.
- An upstream edit that leaves `data_updated_at` alone and doesn't change a year's row count reaches the copy only at the next whole read, within 90 days.
- The camera corridor is our own definition (site block plus one block each way). SFMTA hasn't published one that we could find.
