// About the data for the Street Roles Map: the role rules with their reasons, how bike stress is rated today and
// with the network, what "short" and "connected" mean, the sources and the limits. The long form is the docstring
// of tools/street-roles/street-roles.py, and every number here is read from out/street-roles/summary.json.

import { page } from "../layout.mjs";
import { SUMMARY, SOURCES, sig2 } from "../street-roles.mjs";

export const path = "/transportation/street-roles/about";
export const file = "transportation/street-roles/about/index.html";
export const dataUpdated = SUMMARY.data_read;

const mi = (v) => sig2(v);
const R = SUMMARY.miles_by_rule, M = SUMMARY.miles_by_role;

export function render() {
  const body = `<div class="sr-about">
<h1>About the Street Roles Map</h1>
<p class="lede">How the <a href="/transportation/street-roles">Street Roles Map</a> picks each street's role, rates bike stress and counts connected commutes, and what it leaves out.</p>

<h2>The Four Roles</h2>
<p>We follow the Dutch road safety approach, <a href="https://swov.nl/en/fact/sustainable-safety-has-sustainable-safety-increased-road-safety">Sustainable Safety</a>, where each street has one job and its design follows from it. Each street block starts with a role from these rules, in this order:</p>
<ul>
<li><strong>Walk</strong>: a pedestrian street in the city's <a href="https://data.sfgov.org/d/3psu-pn9h">street centerlines</a>. ${mi(M.walk)} miles.</li>
<li><strong>Through</strong>: an arterial or major street in the city's street classification. ${mi(R.art)} miles, plus ${mi(R["art-sep"])} miles of arterials where the <a href="https://www.sfmta.com/media/41810/download">Biking and Rolling Plan</a> puts a separated bikeway, so through traffic and bikes are kept apart.</li>
<li><strong>Bike</strong>: any other block on the plan's North Star network. That includes ${mi(R["art-brp"])} miles of arterials where the plan routes bikes without a separated bikeway, so they don't carry through traffic. ${mi(M.bike)} miles in all.</li>
<li><strong>Local</strong>: every other surface street, the collectors and residential streets in the city's classification. ${mi(M.local)} miles.</li>
</ul>
<p>"Separated" is the plan's own group: "Separated facilities are those that provide some kind of vertical separation between people biking and rolling and cars" (printed pages 74 to 75). Its Separated, Car-free and Shared-use Path facilities count. Its Shared, Shared Level III and Undecided streets don't. Freeways and ramps have no role here.</p>

<h2>How Bikeable</h2>
<p>Bike level of traffic stress rates a block from 1 to 4. Level 2 is what "the mainstream adult population" will ride, in the words of <a href="https://transweb.sjsu.edu/sites/default/files/1005-low-stress-bicycling-network-connectivity.pdf">Mekuria, Furth and Nixon's 2012 report</a>, which set the method. The map's calm color is level 1 or 2.</p>
<p>Today's rating is SFMTA's <a href="https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4">2023 draft Bike Comfort Index</a>, the higher of its two directions. A block with a path, a protected lane or a Slow Street built since then is level 1. The ${sig2(SUMMARY.unrated_blocks)} blocks the index doesn't rate take the report's table for riding in traffic, which rates a block by its speed limit and lanes.</p>
<table>
<thead><tr><th>Role</th><th>Rating with the network</th></tr></thead>
<tbody>
<tr><td>Through</td><td>Today's rating, or 1 where the plan puts a separated bikeway.</td></tr>
<tr><td>Local</td><td>The table for riding in traffic, with light traffic. We assume every local street gets filters that keep through drivers off it. One lane each way at 25 mph is 1, and at 30 mph 2. Two lanes each way is 3 or more.</td></tr>
<tr><td>Bike, separated in the plan</td><td>1.</td></tr>
<tr><td>Bike, shared in the plan, off a Muni line</td><td>1, as a Slow Street with filters, when it has one lane each way. The plan calls its Level I and II shared streets "All Ages and Abilities".</td></tr>
<tr><td>Bike, other shared streets</td><td>The table for riding in traffic, without the light traffic value. That covers shared streets on a Muni line and the plan's Level III streets, which "manage motor vehicle speed not volume".</td></tr>
<tr><td>Bike, undecided in the plan</td><td>As a local street.</td></tr>
</tbody>
</table>
<p>No block is rated worse than today. When you change a street's role, the map rerates it with the same rules.</p>

<h2>Short and Connected Commutes</h2>
<p>We count jobs held by San Francisco residents in San Francisco, from the Census Bureau's <a href="https://lehd.ces.census.gov/data/lodes/LODES8/ca/od/">LODES 2023</a> data, by home and work block group. The Biking and Rolling Plan defines neither short nor connected, so we use the report's definitions. A commute is short when the shortest route on any street is half a mile to 6 miles, which covers ${sig2(SUMMARY.commuters_in_window)} of the ${sig2(SUMMARY.sf_to_sf_jobs)} jobs. It's connected when a route on level 1 and 2 streets is less than 25% longer than the shortest, or less than 1,760 feet longer. Trips run from the street corner nearest the block group's residents to the corner nearest its jobs.</p>

<h2>What This Doesn't Show</h2>
<ul>
<li>Crossings aren't rated. The report rates a crossing of a wide or fast street on its own, but SFMTA's index rates blocks. So a route that crosses a big street counts as connected, and both figures are the high end of what the method gives.</li>
<li>We route bikes both ways on every street, one-way or not. Paths off the street grid, such as in Golden Gate Park, aren't included.</li>
<li>Lane counts come from SFMTA's lane layer, read as one direction on two-way streets. A local street with two lanes each way stays high stress, since the rules don't narrow it.</li>
<li>LODES counts jobs, so someone with two jobs counts twice, and it places a job at the employer's reporting address. Only commutes are counted, not errands or school trips.</li>
<li>Hills aren't counted.</li>
<li>This map is a snapshot of the sources below, read on the dates given.</li>
</ul>
</div>`;
  return page({
    title: "About the Street Roles Map",
    description: "How the Street Roles Map picks each San Francisco street's role, rates bike traffic stress and counts connected short commutes.",
    path,
    body,
    sources: SOURCES,
    dataUpdated,
  });
}
