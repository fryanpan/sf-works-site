# crash-profiles

A first-cut crash profile analysis for San Francisco in the style of LADOT's [Los Angeles Vision Zero Safety Study](https://ladot.lacity.gov/sites/default/files/documents/la-vz-safety-study-2024.pdf) (2024). It asks which groups of crash hurt the most people, which kinds hurt people badly more often than injury crashes in general, how many people are hurt on high-stress streets, and which street contexts carry more of the people killed or seriously hurt (KSI) than their share of the network.

    python3 pipeline/crash-augment/crash-augment.py --update     # build or refresh the augmented tables first
    python3 analysis/crash-profiles/crash-profiles.py            # 2018-2025 (YEARS)
    python3 analysis/crash-profiles/crash-profiles.py --years 2020 2024

Standard library only. It runs in a few seconds and writes `out/crash-augment/profiles/results.json`. A second run with the same tables writes the same bytes. The scheduled refresh reruns it as the build step `crash-profiles` in [`pipeline/transportation-update.py`](../../pipeline/transportation-update.py) whenever the tables or the street copies change, so `results.json` follows the daily data.

## Inputs

- `out/crash-augment/tables/crashes.csv`, `parties.csv` and `victims.csv`, DataSF's [ubvf-ztfx](https://data.sfgov.org/d/ubvf-ztfx), [8gtc-pjc6](https://data.sfgov.org/d/8gtc-pjc6) and [nwes-mmgh](https://data.sfgov.org/d/nwes-mmgh) with the [crash-augment](../../pipeline/crash-augment/README.md) columns.
- The street lane's held copies of [3psu-pn9h](https://data.sfgov.org/d/3psu-pn9h) (street centerlines, for block miles and intersections by class) and [ybh5-27n2](https://data.sfgov.org/d/ybh5-27n2) (signals), read through `street_sources.held()`, so they are the copies the street columns were built from.

## Method

The script's docstring holds every rule. In short:

| Step | What it does |
| --- | --- |
| Counting | An injury crash is a ubvf-ztfx row. A KSI crash is `Fatal` or `Injury (Severe)`. A KSI person is a victims row with `Fatal Injury` or `Severe Injury`. A crash's year is the year of `collision_datetime`. |
| Level 1 grid | Each crash gets a movement group (the at-fault party's `move_pre_acc`, or the first driver's when a pedestrian is at fault), a violation group (`vz_pcf_group`; "unsafe speed" is mostly CVC 22350, too fast for conditions) and a time band. A cell with 100 or more injury crashes is tested, a rule that reads exposure and not the outcome. It is a profile when its KSI crash rate beats the citywide rate by a one-sided exact binomial test, Bonferroni-corrected over the cells tested. |
| Within mode | The same grid run separately for pedestrian, bicycle and vehicle-only crashes, each against its own rate, because pedestrian crashes are more severe and the all-crash grid mostly finds that. |
| Level 2 | Each profile split by other party movement, pedestrian action, collision type, who was involved, street class, corner type, posted limit, EPC, light and vehicle weight, with a chi-square test, Bonferroni-corrected over every split. |
| Year windows | Each profile's rate against its mode's again for the years before 2020 and from 2020 on, alone, and each mode's crashes by year and severity. Reported minor pedestrian crashes fell about a third from 2020 and did not come back, while KSI crashes held, so pooled severity rates rise after 2020. |
| Context | Each street field's share of KSI people against its share of injury crashes, and for street class, corner type and signals against the network (street miles over every active block and over surface streets alone; signals only at nodes the corner count holds). |
| Size | Every group's people hurt (any injury) and people killed or seriously hurt, whatever its rate: movement x violation x time, the same within each mode, mode x movement x violation, and mode x violation, biggest first, with people by victim role. No size floor and no test. |
| Other breakdown | What the size chart's "all other groups" row holds (group sizes; mode, movement and violation; catch-all values against named kinds), the raw codes inside violation "other" and "not stated" and movement "not stated or other", and seven regroupings compared by the share of people hurt left in a catch-all or remainder and the bars needed for 80% (`other_breakdown`). |
| Size by family | Every crash by mode x violation family (crashes whose mode is not stated make families of their own, so the families hold everyone hurt), with CVC 21703 (following too closely) named, signals split into red light and stop sign, bike and scooter rules and phone use named, and `vz_pcf_code` read when `vz_pcf_group` is blank. Each family carries its people by movement. A 14-bar chart with one remainder row (`size_families`). |
| Family stress | The ten biggest families by people hurt, split by bike level of traffic stress (high LTS 3 to 4, low 1 to 2) and street class (`family_stress`). |
| Grouping alternatives | More ways to cut everyone hurt (who was hurt by role and age, place by stress, street class and intersection, time, a crash-type and violation hybrid, supervisor district, and others), scored the same way with each one's top 12 bars (`grouping_alternatives`). |
| District mix | Each supervisor district's people hurt by mode x violation family against the citywide share: the six biggest families citywide and the district's own top three, the total variation distance from the city, the family with the largest difference, and a chi-square test of the district against the rest of the city over injury crashes (`district_mix`). The district is DataSF's `supervisor_district`, which follows today's 2022 lines in every year; a blank is "District not stated". |
| Traffic stress | Each crash's blocks looked up in SFMTA's 2023 draft Bike Comfort Index layer ([`data/extract/sfmta-bci/scores.json`](../../data/extract/sfmta-bci/scores.json)): bike level of traffic stress (1 to 4, the most stressful direction of any block the crash touches: at an intersection, every block meeting there, cross street included), the all ages and abilities line (score over 80) and the traffic category, each against its share of surface street miles. Today's layer, so it pools every year. |
| Weight | Pedestrians hurt by a single moving motor vehicle (parked cars left out), by its curb weight band, with a Mantel-Haenszel odds ratio of over 5,000 lb against under 3,500 lb stratified by street class and light, for every weighted vehicle and for model-matched ones, per pedestrian and per crash. |

## Limits

- Every figure is a correlation among police-reported injury crashes. A signal, a street class or a weight band carrying more KSI does not mean it causes them: signals go where traffic and walking are heaviest.
- Street class, corner type, lanes and BCI traffic category are today's values only (`current_state_only`), so their results pool every year. Signals, safety zones and traffic calming are dated, and the posted limit is dated only where a 20 mph change is on record.
- With about 24,000 injury crashes, every district's chi-square p-value is tiny, so it says only that the difference is not chance; the share differences and the total variation distance say how big it is.
- The primary collision factor is the officer's judgment. A pedestrian who was killed can't give their account.
- Weight comes from the make and model the officer wrote. Motorcycles, buses and heavy trucks have none, so the weight result compares light vehicles only. A body-type average restates the body type, so the weight result is also given for model-matched vehicles alone. The odds ratio adjusts for street class and light, not for speed or the violation.
- When the pedestrian is found at fault, the profile's movement is the driver's. Nearly every such crash has the driver going straight, so in those profiles the movement label adds little; the violation and the time carry them.
