// About the data for How Residents Travel: what each tract measure counts, where it comes from, and what it
// can't tell you. tools/travel/neighborhood-travel.py's docstring is the long form; the figures here are read from
// the data file.

import { page } from "../layout.mjs";
import { D, MEASURES, MODES, SOURCES, month } from "../neighborhood-travel.mjs";

export const path = "/transportation/how-residents-travel/about";
export const file = "transportation/how-residents-travel/about/index.html";

const other = Math.round(100 * (1 - MODES.reduce((t, k) => t + D.city[k], 0)));
const n = (v) => Math.round(v).toLocaleString("en-US");
const has = (k) => MEASURES.some((m) => m[0] === k);
const ch = D.asof.city_hall;
const day = ch ? new Date(`${ch.departure.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }) : null;

export function render() {
  const body = `<div class="nt-about">
<h1>About the How Residents Travel Data</h1>
<p class="lede">What each map on <a href="/transportation/how-residents-travel">How Residents Travel</a> counts, and what it can't tell you.</p>

<h2>The Maps</h2>
<p>Each map shades San Francisco's ${n(D.geoid.length)} census tracts from the <a href="https://data.sfgov.org/d/sevw-6tgi">2020 Census</a>, home to ${n(D.city.pop)} people in the Census Bureau's 2020 to 2024 survey. Darker means more, and gray means no figure, not zero. Each map's scale runs from 0 to the level 95% of tracts fall under, so a few extreme tracts don't wash out the rest; tracts above it get the darkest shade, marked + on the key. The tick marks the citywide figure, or for a measure with no citywide figure, the average across residents. The five maps of how workers get to work share one scale, so their colors compare. A tract with fewer than ${n(D.min_pop)} residents gets no figure for a rate per resident or per household. That leaves out four tracts: Golden Gate Park, Lincoln Park, McLaren Park and one in Bayview Hunters Point.</p>

<h2>What Each Measure Counts</h2>
<ul>
<li><strong>How workers get to work</strong>: the usual way workers 16 and over got to work, from the <a href="https://data.census.gov/table?q=B08301&g=050XX00US06075$1400000">American Community Survey's table B08301</a>, 2020 to 2024. Driving counts driving alone and carpooling. Taxi, motorcycle and other ways (about ${other}%) aren't mapped, so the five shares don't add to 100%. The survey's margins of error are wide for a single tract, and widest for biking: in about half the tracts the margin is as large as the share itself, so read the bike map for its broad pattern, not tract by tract.</li>
<li><strong>Households without a car</strong>: households with no vehicle available, owners and renters, from <a href="https://data.census.gov/table?q=B25044&g=050XX00US06075$1400000">table B25044</a>. The tracts add up to the Census Bureau's county figure, 109,781 of 363,970 households (30%).</li>
<li><strong>Car miles per resident</strong>: the Metropolitan Transportation Commission's modeled weekday miles residents drive on trips that start or end at home, 2023 base year (<a href="https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/mtc_vmt_home_work_pba2050p/FeatureServer/0">MTC's layer</a>). It's a model estimate, not a count. A tract that spans two model zones takes each zone's rate by its share of the tract's area.</li>
<li><strong>People hurt in traffic</strong>: people injured or killed in police-reported crashes on city streets, ${month(D.asof.injuries.from)} to ${month(D.asof.injuries.to)} (<a href="https://data.sfgov.org/d/nwes-mmgh">${n(D.people_hurt)} people</a>), counted in the tract where the crash happened. Tract lines run down the middle of streets, so a crash within 40 feet of a line is split equally among the tracts it touches. We show it per year, per 1,000 residents of that tract. The people hurt often don't live there, so downtown and along busy streets the rate is high because of who passes through, not who lives there. Freeway crashes aren't in the city's data.</li>
<li><strong>Streets on the High Injury Network</strong>: the share of a tract's city streets, by length, on <a href="https://www.sfmta.com/en/node/45244">SFMTA and SFDPH's 2024 High Injury Network</a>. Freeways, ramps, private and paper streets are left out of the streets counted; park and Presidio roads are in. A street within 40 feet of a tract line counts in both tracts. We get ${Math.round(100 * D.city.hin)}% citywide. SFMTA says the network is 13% of city streets, and we haven't found which street miles it divides by, so don't compare the two figures.</li>
<li><strong>Feel unsafe walking alone at night</strong>: residents who rated their safety walking alone at night 1 or 2 of 5 in the <a href="https://data.sfgov.org/d/nufj-bfbw">2023 City Survey</a>. The survey reports neighborhoods, not tracts, so every tract in a neighborhood carries its figure, with a margin of error of about 10 points either way. Neighborhoods with fewer than 30 answers get no figure.</li>
<li><strong>Extra wait for Muni</strong>: how much longer riders waited than the schedule promised at the frequent stop nearest each block (six or more buses an hour), from ${month(D.asof.muni_wait[0])} to ${month(D.asof.muni_wait[1])} in <a href="https://511.org/open-data/transit">511's arrival records</a>. A tract's figure averages the blocks within a quarter mile of a frequent stop, weighted by how many people live on each; a tract where most residents live farther away gets no figure. It's the "excess wait time" transit agencies use for frequent service.</li>
${has("cityhall_muni") ? `<li><strong>Minutes to City Hall by Muni</strong>: the median time for trips leaving every minute from 8 to 9 AM on a weekday, from the middle of where a tract's residents live to City Hall's front door. It counts the walk to the stop and the wait, and where walking all the way is faster, we use the walk. It's Muni only, because BART isn't in <a href="https://www.sfmta.com/reports/gtfs-transit-data">SFMTA's schedule</a>. We used the schedule for ${day}, a regular weekday in the one SFMTA publishes for ${ch ? ch.gtfs_calendar.map((d) => month(d)).join(" to ") : ""}. Each tract has one starting point, so City Hall's own tract reads a minute or two.</li>
<li><strong>Minutes to City Hall on foot</strong>: the same trip, walked at 2 mph on OpenStreetMap's streets, the pace our school and daily trip maps use.</li>` : ""}
<li><strong>Walk to the nearest grocery store</strong>: minutes at 2 mph along OpenStreetMap's streets from each block's edge to the nearest supermarket or grocery mapped in OpenStreetMap. A tract's figure averages its blocks, weighted by how many people live on each. OpenStreetMap misses many small grocers.</li>
</ul>

<h2>Gaps in the All-Ages Bike Network</h2>
<p>The gap is how far the best bike route from home runs on streets that aren't part of the all-ages network: every stretch off it added up, including the ride to reach the network and from it to the destination. The network is multi-use paths, protected bike lanes and every <a href="https://data.sfgov.org/d/hkz3-itiu">Slow Street</a>, from <a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a>. Painted lanes and signed routes don't count. The best route is the one with the smallest gap we found among routes no more than 25% longer than the shortest. Routes avoid stairs. A tract's figure averages its blocks, weighted by how many people live on each.</p>
<ul>
<li>Golden Gate Park is reached at its nearest edge, the Panhandle included (<a href="https://data.sfgov.org/d/gtr9-ntp6">Recreation and Parks Properties</a>).</li>
<li>The nearest BART station is one of the nine from Embarcadero to Daly City, and the nearest Caltrain station is 4th and King, 22nd Street or Bayshore, from each agency's published schedule file. The route can end at any of them: among routes no more than 25% longer than the shortest to any station, it takes the one with the smallest gap.</li>
<li>Lung Fung Bakery is at 1823 Clement Street.</li>
</ul>

<h2>What This Doesn't Show</h2>
<ul>
<li>A tract figure is an average. Blocks inside a tract can differ a lot, especially for the bike gaps and the grocery walk.</li>
<li>Hills aren't counted in the walking or biking figures.</li>
<li>A far tract has a long gap partly because its route is long. The gap is distance off the network, not the share of the trip.</li>
<li>Treasure Island has no bike gaps or walk to City Hall: there's no route off the island on foot or by bike.</li>
</ul>
</div>`;
  return page({
    title: "About the How Residents Travel Data",
    description: "What each tract map on How Residents Travel counts: commute modes, cars, car miles, injuries, night safety, Muni waits, City Hall trips, grocery walks and bike network gaps.",
    path,
    body,
    sources: SOURCES,
  });
}
