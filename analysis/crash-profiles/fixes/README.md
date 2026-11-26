# Crash fixes: schema and counting rule

`lanes/` holds one JSON file per research lane (area, bike, crosscut, junction, pedestrian, speed), a completeness critique (`critique.json`) and a follow-up (`fill.json`) that adds fixes, adds group mappings, corrects misfits and adds costs. [`../fix-map.py`](../fix-map.py) merges them and writes `out/crash-augment/profiles/fix-map.json`:

    python3 analysis/crash-profiles/fix-map.py

Standard library only. A second run writes the same bytes.

## Schema

Each lane file is `{"lane": "...", "fixes": [...], "gaps": ["..."]}`. Each fix:

| Field | Holds |
| --- | --- |
| `id` | kebab-case, stable |
| `name`, `how_it_works` | the treatment and one sentence on how it works |
| `lever` | one of street design, signals, speed management, traffic volume and filtering, pricing, vehicles and fleets, automated enforcement, behaviour programs, transit and land use, policy and law |
| `groups` | one entry per crash group it reaches: `group` as `"<mode> \| <family>"` from `size_families` in `out/crash-augment/profiles/results.json` (or a cross-cut `place \|`, `who \|`, `time \|` group), optional `movement`, `mechanism`, `target_share` (the share of the group's people hurt it can reach, with its basis, as text) and `effect` |
| `effect` | `low`, `mid`, `high` in the study's own unit, `unit`, `applies_to` (which crashes and which severity), `source`, `tag` |
| `unit`, `cost` | the unit of treatment; `cost` is `low`, `high`, `year`, `unit`, `source`, `tag` in US dollars |
| `life_years` | service life, for a one-time cost |
| `sf_now`, `sf_evidence`, `who_decides`, `evidence_grade`, `sources` | what SF does now, SF's own result, who decides, the grade with its reason, and each source with its URL and provenance tag |

`fill.json` records also carry `fill_action`: `new`, `add_groups` (append groups to the record named in `extends`), `misfit_corrected` (replace the named groups or fields) or `cost_added` (set the cost).

## How the merge counts

- **Same treatment, one record.** `ALIASES` in the script maps duplicate ids to one canonical id (for example `congestion-pricing` and `congestion-pricing-cordon` to `area-cordon-congestion-charge`). The canonical record's fields lead and the aliases add their group mappings. Where a fix maps the same group twice, the first entry with a usable effect and share is used and the others are kept as alternates.
- **Effects in one unit.** Every effect becomes r, the fraction of the target crashes removed: `% fewer` is v/100, `% change` is -v/100, a CMF or rate ratio is 1 - v. An increase stays negative.
- **Applied only where it fits.** An effect is used only if it measures crashes or injuries (not speeding, violations, yielding, an exponent or a risk factor), only for the road user it names, and an effect on deaths or serious injuries alone counts toward KSI and not toward all people hurt.
- **Reach from the crash map, for the fixes `reach.json` places.** [`reach.json`](reach.json) maps a fix to the kind of place it goes (signalized corners, unsignalized arterial corners, two-way stops, the High Injury Network, a street class, multi-lane arterials and collectors, candidate low-traffic cells, speed camera corridors and others, or an expression over them) and to SF's count of those places. [`../fix-reach.py`](../fix-reach.py) tags every 2017 to 2024 crash with those places and writes each group's people hurt and KSI people in each, by movement, with SF's counts and their sources, to `out/crash-augment/profiles/fix-reach.json`. A placed fix's share of a group is the group's people in that place (within the entry's movement) over the group's total, and its per-unit cost is multiplied by the place count, so the cost and the reach cover the same places. Where the lane's share names a party or crash type rather than a place (driver at fault, sideswipes), `"text": "multiply"` keeps it and multiplies by the place's fraction. A record with no `life_years` takes the Caltrans Local Roadway Safety Manual's Expected Life for the nearest countermeasure, named in `reach.json`. `not_placed` there lists the fixes left out and why. Miles count a divided street once and a divided street's two crossings count as one corner (the rule in `tools/street-safety/hin-densest-stretches.py`), because SF's centerline file draws many arterials twice: arterial miles fall from 138.5 drawn to 86.4. Run `fix-reach.py` before `fix-map.py` after editing `reach.json`.
- **Sites already treated are netted out where SF has a count.** `treated` in `reach.json` takes out a fraction of both the crashes reached and the places priced (LPIs: SFMTA's 81% of signals with an LPI or no turn conflict, a ceiling; daylighting: the middle of SFMTA's 57% to 65%), or leaves treated places out of the reach (today's camera corridors, Slow Streets, blocks posted 20 mph, HIN blocks at 20 mph). A placed fix with no count of what is done says `most it could reach` on its record (`reach_treated`) and its ranking row.
- **Signal timing priced with its hardware.** For the LPI, the exclusive pedestrian phase, retiming, all-red and yellow change, `reach.json`'s `cost` replaces the lanes' labour-only price with a range from labour ($100 a signal) to engineering and hardware: $50,000 for an LPI (Vision Zero SF's band), $150,000 for an exclusive phase (FHWA PEDSAFE), $10,000 for timing changes (Vision Zero SF). A signal that needs a new cabinet or heads costs a full upgrade, $424,000 (Public Works' Contract 35 award) to $1.18M (SFCTA's allocation for the same 17 sites) a location, which is not priced.
- **Upkeep.** `upkeep` adds a yearly cost per unit: the low-traffic cells carry the record's filter upkeep per mile of cell street.
- **Low confidence on reach.** At the corners the stop sign layer calls uncontrolled, police code a working control device in 48% of crashes, and 46% to 59% at stop-controlled ones (86% at signals), so `reach_confidence` is low for the beacon, all-way stop, stop warning beacon and mini-roundabout fixes (`checks.police_control_device_by_node_class` in `fix-reach.json`).
- **SF's own results set the low end.** Where SF has tested a treatment on its own streets (20 mph blocks, road diets, quick-build corridors, painted safety zones, speed humps, speed cameras, Slow Streets), `SF_EVIDENCE` in the script sets the low to no effect when SF's 95% range includes no change, or to SF's result when it does not, wherever the lane's low is more hopeful. Each pair carries `sf_evidence` saying whether it changed.
- **Target share from the record, for every other fix.** An explicit "N% of the group" wins. Otherwise the share is "A of B" where B is the group's own total. If the text says the reachable share is not computed, unknown, or limited to some blocks, corridors or sites, the pair is not computed, because the street-class counts beside such a caveat overstate the reach.
- **Avoided a year** = group people hurt (or KSI people) 2017 to 2024 / 8 x target share x r, at low, mid and high.
- **Annual cost.** A per-year cost is used as is and a one-time cost is spread over `life_years`. A per-unit cost (per corner, mile, signal, camera) needs SF's unit count, which `UNITS` takes from the record's own text or from `results.json`. With no count, or no life for a one-time cost, the cost per injury is not computed. Dollar years are as the records give them.
- **Cost per injury avoided**: low = cost low / avoided high, mid = cost mid / avoided mid, high = cost high / avoided low. The value of injuries avoided uses the SF Budget and Legislative Analyst's 2025 crash costs (economic only, $36,949 an injury in 2019 dollars, brought to 2024 dollars by the report's own totals) and USDOT's 2026 comprehensive values weighted by SF's 2022 to 2024 grade mix, each giving a benefit-cost ratio.
- **Ranking.** Each fix is ranked on its own, by cost per person hurt avoided at mid. Fixes acting on the same group are not added together in the ranking.
- **Enablers.** A law that only allows another fix (camera-enforced filters, lifting the camera cap, civil red-light penalties) is not ranked; its benefit and cost sit with the fix it allows.

## Stacking

Each fix does a little, so the script also builds stacked packages and counts them sequentially, the rule in TRL's PPR844: within a group, each added fix acts only on the people left after the fixes before it, so remaining = product over the package of (1 - target share x r), and the package total sums across the 45 mode x family groups, which between them hold everyone hurt. An `all other families` entry is applied to each family outside the chart unless the fix maps that family itself. Cross-cut groups overlap the families and are reported but not stacked. `CONFLICTS` lists fixes that are versions of one another (a citywide 20 mph default and street-by-street limits, a camera network and today's cameras), and a stack takes only the first of each.

Sequential counting assumes the fixes' effects are independent. It is the standard conservative rule: it never credits two fixes with the same person, though it can still over-credit fixes that work through the same mechanism.

The stacks in `fix-map.json`:

- `greedy_by_people_hurt`: adds the fix with the lowest cost per person hurt avoided on what remains, until every computable fix is in. Each step records the cumulative people hurt and KSI avoided, cumulative annual cost and the share of all SF people hurt and KSI avoided, so a tool can draw share avoided against cumulative cost.
- `greedy_by_ksi`: the same, ranked by cost per KSI person avoided.
- `area_wide_only`, `corner_and_corridor_only`, `area_wide_and_corner_corridor`: the greedy stack within each kind.
- `greedy_by_people_hurt_optimistic` and `_pessimistic`: high effects with low costs, and low effects with high costs.

## Limits

- A placed fix is costed and credited at every place of its kind not yet treated (every signal, every unsignalized arterial corner, every HIN mile, less what SF has counted as done). Where SF has no count it is the most the fix could reach, not a program SF has proposed, and the cost per person hurt is the same at any fraction of those places only if the places are alike.
- Fixes still not computable mostly lack an effect size on crashes, a cost, or a countable unit; `not_computable` lists every pair and why, and `reach.not_placed` the fixes `reach.json` leaves out.
- The stacked totals are only as wide as the computable fixes, so they understate what a full package could reach.
- Effects are borrowed from studies elsewhere and applied at SF's crash counts; the evidence grade on each record says how far to trust each one.
