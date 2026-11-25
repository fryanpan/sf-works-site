# vehicles

Adds a clean make, a clean model and an estimated curb weight to every row of DataSF's crash parties table ([8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6)) and victims table ([nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh)), and rolls the heaviest vehicle up to each crash in [ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx). Names and weights come from NHTSA's [vPIC API](https://vpic.nhtsa.dot.gov/api/).

    python3 pipeline/crash-augment/vehicles/vehicle-fields.py --update   # bring the held DataSF tables up to date, rebuild, check
    python3 pipeline/crash-augment/vehicles/vehicle-fields.py            # rebuild from the held tables
    python3 pipeline/crash-augment/vehicles/vehicle_checks.py            # run the checks on the last build
    python3 pipeline/crash-augment/vehicles/tests/vehicle-fields-test.py # tests, with a stub vPIC and no network

Standard library only. It runs as part of [`../crash-augment.py`](../crash-augment.py), daily with the scheduled refresh; the DataSF tables come from the held copy [`../crash_tables.py`](../crash_tables.py) keeps, which reads only the rows that moved.

## Why the field needs reading

The tables have one `vehicle_make` field and no model field. Before 2018 it mostly holds a make, often as a four-letter NCIC code (`TOYT`, `MERZ`). Since 2018 it usually holds the officer's make, model and colour in free text, such as `Toyota/Highlander/Silver`, `HONDA CIVIC/WH` or `TOYT/PRUIS/GRY`. The parties table holds 140,843 rows and 29,865 distinct spellings, which read down to 12,648 once colours and separators are set aside. [DataSF 8gtc-pjc6 — queried 2026-11-25]

## Files

| File | What it is | Tracked |
| --- | --- | --- |
| `vehicle-fields.py` | The build: reads the three held tables, parses every string, finds weights, writes the outputs, runs the checks | yes |
| `vehicle_parse.py` | Reads a raw string as a make and a model. Its docstring gives every rule, in order | yes |
| `vehicle_weight.py` | Assigns Transport Canada trims to models and averages their curb weights | yes |
| `vehicle_vpic.py` | The vPIC client, with an on-disk cache so a rerun makes no network call | yes |
| `vehicle_checks.py` | The quality checks that must pass before a build replaces the last one | yes |
| `make-aliases.csv` | NCIC make codes and misspellings seen in the data, each to a vPIC make | yes |
| `model-aliases.csv` | Model names officers use that vPIC spells otherwise (`MIATA` is the MX-5, `TESLA/Y` the Model Y) | yes |
| `golden.csv` | Raw strings read by hand, with the make and model each must come out as | yes |
| `make-model-lookup.csv` | Every distinct string as the parser keys it, the make and model it reads, how, and how many rows carry it. The file to review | yes, generated |
| `body-type-averages.json` | The body-type fallback weights and how many rows each averages | yes, generated |
| `match-summary.json` | Rows and distinct strings by match method | yes, generated |
| `.cache/crash-augment/vehicles/*.csv` | The augmented tables: `parties-vehicles.csv`, `victims-vehicles.csv`, `crashes-vehicles.csv` | no |
| `.cache/crash-augment/vpic/` | One JSON file per vPIC answer | no |

## Columns

Parties and victims rows keep their `unique_id`, `case_id_pkey` and `party_number_ckey` (victims also `victim_id`), so they join back to the DataSF tables one to one. A victim's columns describe the vehicle the victim was in or on.

| Column | Holds |
| --- | --- |
| `vehicle_make_clean` | vPIC's make name: `TOYOTA`, `MERCEDES-BENZ`. Empty when the string names no make vPIC lists, and for pedestrians, bicyclists and non-motor body types |
| `vehicle_model_clean` | vPIC's model name: `Highlander`, `F-150`, `Model 3`. Mercedes and Lexus codes read to their family (`C300` is `C-Class`, `RX350` is `RX`) |
| `estimated_vehicle_weight_lb` | Curb weight in pounds: empty, with fluids, no people or cargo |
| `vehicle_match_method` | How the weight was found (below) |
| `vehicle_match_reason` | Why a row fell back or has no weight |
| `vehicle_body_type_clean` | `stwd_vehicle_type` with its typos folded (`Passenge Car` is `Passenger Car`) |

The crash rollup has `motor_vehicle_parties` (moving motor vehicles only), `parked_vehicle_parties`, `vehicles_with_weight`, and the weight, make and model of the heaviest moving vehicle with a weight. Parked cars are counted apart so a parked car's weight is never credited to a crash it did not drive into.

## Match methods

| Method | Weight |
| --- | --- |
| `exact_make_model_year` | Mean curb weight of the model's trims in its model year, from vPIC's [GetCanadianVehicleSpecifications](https://vpic.nhtsa.dot.gov/api/vehicles/GetCanadianVehicleSpecifications/?Year=2020&Make=Toyota&units=US&format=json). Every trim counts once, since nothing public says how many of each were sold |
| `model_10yr_avg` | The model with no usable year: the mean over the ten model years ending at the crash year. When the year is given but has no trims, the ten model years around it |
| `body_type_avg` | No model weight: the mean of every exact weight among parties rows of the same light body type (`body-type-averages.json`) |
| `unmatched` | No weight, with the reason |
| `not_applicable` | Pedestrians, bicyclists and non-motor body types |

Transport Canada measures cars, SUVs, vans and pickups only. Motorcycles, buses and heavy trucks therefore stay `unmatched`, and there is no body-type average for them. A light-vehicle weight on a row coded as a motorcycle, or one under 3,000 lb on a row coded as a bus or tractor, is a conflict between the two fields; the row stays `unmatched` and says so. A two-digit `vehicle_year` (`15`) is not read as a model year.

Of the 140,843 parties rows, 109,978 are motor vehicles. Among those, 98% with any text get a clean make and 30% a model; before 2018 the field is mostly a make alone. 94% of rows with a model get that model's own weight. [DataSF 8gtc-pjc6 — queried 2026-11-25; NHTSA vPIC — queried 2026-11-25]

| Method | Parties rows | Share of motor-vehicle rows |
| --- | ---: | ---: |
| `exact_make_model_year` | 28,675 | 26% |
| `model_10yr_avg` | 1,509 | 1% |
| `body_type_avg` | 57,524 | 52% |
| `unmatched` | 22,270 | 20% |
| `not_applicable` | 30,865 | |

The body-type averages: Passenger Car 3,296 lb, Sport Utility Vehicle 4,004, Minivan 4,410, Police Car 4,446, Pickup or Panel Truck 4,746 (`body-type-averages.json`). Most `unmatched` rows are a make with no model on a body type with no average: Not Stated, Motorcycle or a bus. `match-summary.json` has the full counts, for victims too.

## How the strings are read

`vehicle_parse.py` reads each string in this order and stops at the first rule that is sure. Anything it is not sure of stays empty with a reason, which is the rule throughout: nothing is guessed.

1. Upper case, drop colour words and parenthesised notes, split on `/ | , ;` and ` - `.
2. Make: the leading one to three words, squashed to letters and digits, against vPIC's makes for cars, trucks, MPVs, buses and motorcycles and against `make-aliases.csv`. A misspelling is read only against a make with at least 50 rows spelled exactly, with the same first letter and one edit.
3. Model: against vPIC's model names for that make, squashed the same way (`RAV-4`, `RAV 4` and `Rav4` are one key), then model aliases, series codes, unambiguous abbreviations (`HIGHLAND`, `TOY/CAM`), and misspellings of all-letter words (`CORROLLA`, `PRUIS`).

What the rules refuse, each a case the self-check below caught: `NINJA` is a family of Kawasaki models, not the Ninja 7 that adds one character. `CHEVELLE` is not the Chevette. `SPART` is Spartan fire apparatus, not SMART. `YW125` and `CMX500` are model codes where one character is a different model. `PRE RUNNER` is a Tacoma trim, not the Previa. `VESPA/PIAGGIO` names the maker, not the Piaggio Fly. Bicycle brands that are also vPIC motorcycle makers (`TITAN`, `RIDLEY`) are not read, and a bicyclist's make is left empty.

## Data quality

Two stratified random samples of 200 distinct strings each (in each, 60 with 20 or more rows, 60 with 3 to 19 and 80 with 1 or 2) were read by hand against the parser's output. Of the 400, the parser reads 395 right and 1 wrong, and leaves 4 empty that a person could read. The wrong one is an e-scooter brand that shares its name with a vPIC motorcycle maker; the build leaves the make empty for non-motor parties. The samples informed the rules, so the rate on unseen strings may be lower. Every string read by a misspelling, abbreviation or series rule, about 1,000, was also read by hand. [inference — mine, from the samples]

The checks in `vehicle_checks.py` run after every build, on the new files, before they replace the last good build. A failing check keeps the previous build and exits 1:

- row counts against a floor and within 2% of the previous build, and exactly equal to each DataSF input
- keys unique; key fields never empty
- every victim's party is one parties row, and every party's crash is a crash row
- a victim's vehicle columns equal its party's
- per row: a known method, a weight exactly when the method gives one, a reason whenever it fell back, no model without a make, and the weight in bounds: 1,500 to 14,000 lb for light vehicles, 150 to 1,500 for motorcycles and scooters, 3,000 to 80,000 for buses and heavy trucks
- each common body type's average weight in its range (Passenger Car 2,800 to 3,800 lb, Sport Utility Vehicle 3,500 to 4,800, Pickup or Panel Truck 4,000 to 5,800, Minivan 3,800 to 4,900). The per-row bounds are wide enough to hold a light vehicle's weight in kilograms, so this is the check that catches a unit error
- match-rate floors a few points under the first full build
- `golden.csv`: 76 hand-read strings, including every error the self-check found, each of which must read as written

`tests/vehicle-fields-test.py` feeds a made-up table through the build and shows each check failing on the bad input it is for: a duplicated input row, a dropped output row, a short read, a 50,000 lb car, a weight with no method, a victim with no party, a wrong golden row, a missed rate floor and a body-type average in kilograms.

## Sources

- DataSF [Traffic Crashes Resulting in Injury: Parties Involved](https://data.sfgov.org/d/8gtc-pjc6), [Victims Involved](https://data.sfgov.org/d/nwes-mmgh) and [Traffic Crashes Resulting in Injury](https://data.sfgov.org/d/ubvf-ztfx). [DataSF 8gtc-pjc6, nwes-mmgh, ubvf-ztfx — queried 2026-11-25]
- NHTSA vPIC: [GetMakesForVehicleType](https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleType/car?format=json), [GetModelsForMake](https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMake/toyota?format=json) and [GetCanadianVehicleSpecifications](https://vpic.nhtsa.dot.gov/api/vehicles/GetCanadianVehicleSpecifications/?Year=2020&Make=Toyota&units=US&format=json), whose `CW` is curb weight. [NHTSA vPIC — queried 2026-11-25]
- The NCIC make codes in `make-aliases.csv` are read from the data itself, each checked against the models written beside it. [inference — mine]
