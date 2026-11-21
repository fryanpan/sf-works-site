# SFMTA — the ArcGIS services behind the Biking and Rolling Plan

**What it is.** The plan's analysis layers, live and queryable, on two ArcGIS
servers. `sources/sfmta-biking-rolling-plan.md` said on 2026-09-05 that the plan's
data was "not published as GIS anywhere found" — that was right about the North
Star network itself and wrong about everything around it. Found 2026-09-20 by
following SFMTA's own blog post to the Active Communities Plan interactive map and
reading the web app's configuration.

**How to find them again.** The app is
`tooledesign.maps.arcgis.com/apps/webappviewer/index.html?id=f948aa0022e246259ea899e5a4318427`.
Its config is at `…/sharing/rest/content/items/<appId>/data?f=json`, which names a
web map id; that map's `data?f=json` lists 33 operational layers with their service
URLs. Nothing is authenticated. `[primary — read 2026-09-20]`

**Both servers answer anonymous queries and neither is documented as public.**
Treat them as things that can disappear. Cache what you use and date the cache.

## The layers that matter

| Layer | Service | Rows | Notes |
| --- | --- | --- | --- |
| 2023 Draft Bike Comfort Index | `services6.arcgis.com/bom7L4u7y1k0qkF1/…/Bike_Comfort_Index_Score/FeatureServer/4` | 15,280 | The BCI the plan's all-ages definition depends on |
| Pipeline Projects | `…/Pipeline_Projects/FeatureServer/0` | — | Bikeway schema plus `ACTIVE`, `INROW`, `BIKE_NTWK_` |
| MTA.bikewaynetwork | `services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0` | 5,457 | **SFMTA's own copy of the bikeway layer, with edit timestamps DataSF drops** |
| Slow Streets 2023 | `…/Slow_Streets/FeatureServer/0` | — | Also on DataSF as `hkz3-itiu` |
| 2012 Active Transportation Network | `…/2012_bike_facilities/FeatureServer/29` | — | A 2012 baseline, which no other source here has |
| Multimodal/projects | `services.sfmta.com/arcgis/rest/services/Multimodal/projects/FeatureServer/{0,1,2}` | 461 rows / 224 projects | **The live Interactive Project Map. The DataSF copies of it are twelve months stale — see below** |
| Multimodal/sfstreets_projects | `…/Multimodal/sfstreets_projects/FeatureServer/{0,1,2}` | 6,013 | Not yet read. Much larger; scope unestablished |
| Modeled Bike and Micromobility Volume | `…/Modeled_Bike_and_Micromobility_Volume/FeatureServer/19` | — | Modelled, not counted. Do not report as ridership |

Also present: street slope, high injury network 2022, crashes 2017–2021,
bike parking, bike counters, Bay Wheels docks, equity priority communities,
zero-vehicle households, bike commute mode share, parks.

## `Bike_Comfort_Index_Score` — read this before using BCI

15,280 street segments, keyed `cnn_sgmt_pkey`. **This is every street in the city,
not just bikeways** — SFMTA's bikeway layer has 2,823 blocks. `maxRecordCount` is
2,000, so it pages. `[primary — queried 2026-09-20]`

**Scale.** BCI runs 4 to 146 in the data; the plan's legend bands it 0–150. Higher
is more comfortable. Median 59, mean 61.3. It is the sum of three sub-scores, each
capped at 50: `traffic_subscore`, `context_subscore`, `bike_infra_subscore`.

**Level of Traffic Stress is an input, not an alternative.** `lts_segment_ft` and
`lts_segment_tf` carry the LTS level per direction and `lts_ft_pts` / `lts_tf_pts`
carry its contribution to the traffic sub-score. BCI wraps LTS and adds pavement
condition (`pci_pts`), land use (`land_use_pts`), parking time limits, transit
lanes, violations, a slope multiplier and the bikeway's own design points.

**BCI is much stricter than the usual LTS cut.** Only 21% of segments clear the
plan's `BCI > 80` threshold, against 65% that sit at LTS 1–2:

| LTS | segments | median BCI | clear BCI > 80 |
| --- | --- | --- | --- |
| 1 | 8,194 | 66 | 32% |
| 2 | 1,397 | 56 | 11% |
| 3 | 1,699 | 51 | 9% |
| 4 | 3,568 | 43 | 4% |

29% of LTS 1–2 segments clear BCI > 80; 6% of LTS 3–4 still do. **So the two
frameworks are not interchangeable and a figure computed on one cannot be quoted
against the other.** 422 segments have no LTS value.

**Uncertainty, and it is not small.**
1. **It is labelled "2023 Draft".** The plan (March 2025) says BCI "was updated for
   all streets in San Francisco", so a later non-draft version probably exists and
   is not published. Any all-ages figure computed from this layer is computed from
   a draft and must say so.
2. **The key is `cnn_sgmt_pkey`, not CNN.** Joining it to the bikeway layer or to
   city centrelines has not been done or tested. Until it is, BCI cannot be put
   beside a facility class.
3. **Directional.** `bci_ft` and `bci_tf` differ; `bci` is the combined figure.
   Which the plan's `BCI > 80` test means is not stated in the plan.
4. **The published alternative is a 2017 PDF.** `sfmta.com/reports/map-san-francisco-bike-network-comfort-index`
   offers one static map from 2017-01-19 and no data.

**The plan's own definition.** The plan's appendix describes BCI as "a quantitative measure of comfort on every street in San Francisco, based on the January 2023 network". It is made of three subscores: context (land use, pavement quality, reported behavioural violations, slope), traffic (Level of Traffic Stress, heavy vehicles, curbside turnover) and bike infrastructure (facility type, intersection, signals). Appendix E, appendix PDF p. 130. Appendix G's footnote gives the threshold's meaning: a score over 80 means "the facility is comfortable to ride for most users" (appendix PDF p. 155). The same footnote points to "the Bicycle Comfort Index Methodology document on the project website", which has not been found. Appendix I (appendix PDF p. 213) records that SFMTA built the index in 2014 and updated it in 2017, both times for bike-network streets only, and that Toole Design rebuilt it for every street in 2022–23. [Appendix volume](https://www.sfmta.com/media/41946/download) `[primary — read 2026-09-23]`. **Where to see it on a map:** the [Active Communities Plan interactive map](https://tooledesign.maps.arcgis.com/apps/webappviewer/index.html?id=f948aa0022e246259ea899e5a4318427) draws this layer (link checked 2026-09-23). Methodology, from Toole Design who built it with SFMTA: `tooledesign.com/insights/2023/10/expanding-our-understanding-of-bike-comfort/` `[secondary — read 2026-09-20]`

## `MTA.bikewaynetwork` — the edit clock DataSF does not republish

Same 5,457 rows as DataSF's `ygmz-vaxd`, same schema, **plus `CREATED_DATE`,
`LAST_EDITED_DATE`, `CREATED_USER` and `LAST_EDITED_USER`** as epoch milliseconds.
All 5,457 return in a single request. `[primary — queried 2026-09-20]`

What the timestamps say, **unanalysed and not yet trusted**:

- `LAST_EDITED_DATE`: 5,213 rows in 2023, 82 in 2024, 39 in 2025, 123 in 2026.
  **Nothing before 2023.**
- `CREATED_DATE` is null on 4,380 of 5,457 rows. Where present: 2015 (38),
  2016 (156), 2017 (219), 2018 (16), 2019 (370), 2020 (78), 2021 (98), 2022 (18),
  2023 (21), 2024 (45), 2026 (18).
- `LAST_EDITED_USER` is a single user on all 5,457 rows.

**The reading that has not been tested:** 5,213 rows last edited in 2023 with no
edit date before it looks like a bulk rebuild of the layer in 2023, which would
mean row-level history before 2023 does not survive in this dataset. If that
holds, every pre-2023 figure derived from `INSTALL_YR` and `UPDATE_YR` rests on
stamps a rebuild carried forward rather than on a contemporaneous record. This is
under adversarial review as of 2026-09-20; do not build on the pre-2023 series
until that comes back.

## `Multimodal/projects` — use this, not the DataSF copy

SFMTA's Interactive Project Map, the thing behind every project page on
sfmta.com. Three layers — 0 points, 1 lines, 2 polygons — carrying 461 rows
across 224 distinct projects, keyed `PROJECTNODE`, which is also the sfmta.com
path: `https://www.sfmta.com/node/<PROJECTNODE>`. 122 projects are tagged Bike.
`[primary — queried 2026-09-20]`

**DataSF mirrors this and the mirror has stopped.** Bryan, 2026-09-20: "That
project polygons dataset is woefully out of date." He is right, and it is worse
than late:

| | Rows | Last loaded | Rows stamped |
| --- | --- | --- | --- |
| [`6ibt-jpn7`](https://data.sf.gov/d/6ibt-jpn7) SFMTA Projects – Polygons | 98 | 2025-09-02 | `data_as_of` 2025-06-12 |
| [`j4dm-6zyr`](https://data.sf.gov/d/j4dm-6zyr) SFMTA Projects – Points | 246 | 2025-09-20 | — |
| `Multimodal/projects`, live | 461 | rows edited into the current week | — |

Both mirrors declare a **Weekly** publishing frequency in their own metadata and
neither has moved in twelve months. Between them they know 116 project nodes.
**95 of the 122 live bike projects have no row in either** — Arguello, the
Bayview Community Pathway, every Slow Street, most of the Quick-Builds. So the
mirror is not a late copy of the programme, it is missing most of it.

**Traps.**
- `PROJECTPHASE` is undated. "Completed" carries no completion date, so it is not
  delivery evidence on its own. Join it to the bikeway layer's `INSTALL_YR` or to
  the board record first.
- A project's geometry is its study area. A corridor polygon covers blocks the
  project may not touch.
- `GEOEVENT_LASTUPDATE` is null throughout. `LAST_EDITED_DATE` is the freshness
  field, and it is an edit to the map record, not to the project.
- The project pages are server-rendered Drupal and readable; there is no
  JSON:API (`sfmta.com/jsonapi` is 404). They carry individual staff email
  addresses, which `tools/projects/sfmta-projects.py` scrubs on the way in.

Read by `tools/projects/sfmta-projects.py` → `out/sfmta-projects/`.

## Published total

**The bikeway layer matches.** SFMTA wrote on 2026-05-28 that "Our bike network now spans 470 miles – including 50 miles of separate bikeways."^[SFMTA, [Safety Upgrades Make a Difference: Bike Ridership is on the Rise](https://www.sfmta.com/blog/safety-upgrades-make-difference-bike-ridership-rise), 2026-05-28. [primary — read 2026-10-23]] The `LENGTH_FT` of all 5,457 rows of `MTA.bikewaynetwork` adds up to 470.2 miles, 0.04% over SFMTA's 470. Class IV adds up to 52.9 miles against the post's rounded "50". The cached copy is from 2026-09-22, four months after the post.^[[data/extract/sfmta-bikeway/network.json](../../data/extract/sfmta-bikeway/network.json), fetched 2026-09-22. [primary — queried 2026-09-22]]

```python
sum(r["LENGTH_FT"] or 0 for r in json.load(open("data/extract/sfmta-bikeway/network.json"))["records"]) / 5280   # 470.2
# by FACILITY_T: Class III 202.1, Class II 129.8, Class I 85.4, Class IV 52.9
```

**Slow Streets: no current total to match.** SFMTA's most recent network-wide figure found is from the 2020 pandemic program: "a complete Slow Streets network of 34 lane miles".^[SFMTA, [The Next Phase of Slow Streets](https://www.sfmta.com/blog/next-phase-slow-streets), 2020. [primary — read 2026-10-23]] The SFMTA Board approved the permanent program on December 6, 2022, and dropped several pandemic corridors (the list is in scripts/slow-streets-extract.py), so 34 lane miles no longer describes the network. The program page gives no mileage.^[SFMTA, [Slow Streets Program](https://www.sfmta.com/projects/slow-streets-program), undated. [primary — read 2026-10-23]] DataSF's Slow Streets layer has 222 implemented rows over 16.1 miles, and 4 of those rows repeat a CNN. Dropping the repeats leaves 218 blocks, 15.7 street miles on 22 streets, which is what the map rides. The layer's rows were last updated 2024-01-18.^[[DataSF hkz3-itiu — queried 2026-10-23]]

**Rule adopted.** One row of the bikeway layer is one block of one facility, with its length in feet, counted per centreline (a two-way Class IV block counts once). The full access map's low-stress network takes only Class I, Class IV and Slow Street blocks ([lib/school-travel-time.py](../../lib/school-travel-time.py) `all_ages_lines(brp_rule=True)`), which is 52.9 + 85.4 miles of the 470 plus the Slow Streets, before overlaps.

**Checked 2026-10-23.**
