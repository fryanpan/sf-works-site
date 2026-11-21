// About the data for the Daily Trips map: how each trip was timed, where the
// places come from, what "frequent Muni" counts, and what the T Third
// scenario assumes. The method is tools/travel/full-map.py's, whose docstring is
// the long form, and every number here is read from the data file.

import { page } from "../layout.mjs";
import { D, SERVICE_DAY, SOURCES } from "../daily-trips.mjs";

export const path = "/daily-trips/about";
export const file = "daily-trips/about/index.html";

const T3 = D.tthird_assumptions || {};
const n = (v) => v.toLocaleString("en-US");

export function render() {
  const body = `<div class="dt-about">
<h1>About the Daily Trips Data</h1>
<p class="lede">How we timed every trip on the <a href="/daily-trips">Daily Trips</a> map, and what it can't tell you.</p>

<h2>What the Colors Mean</h2>
<p>Our goal for a daily trip is 15 minutes or less, and never more than 30. Each block's color is the time to the nearest place you pick. Teal is 15 minutes or less, which meets the goal. Tan is 16 to 30 minutes, under the 30-minute limit. Brown is anything longer. We round walking, biking and driving times up to the whole minute, so a block shown at 15 is no more than 15. The trip planner gives Muni times in whole minutes rounded down, so a Muni 15 can be up to 15.9. We round counts of people to two figures, so 786,588 would show as 790,000. The map shows the ${n(D.pop.length)} blocks where someone lived in the <a href="https://data.sfgov.org/d/p2fw-hsrv">2020 Census</a>, home to ${n(D.residents)} people. Blocks with no residents are left blank.</p>

<h2>How We Timed Each Trip</h2>
<p>Every trip starts at the block's edge, where its outline meets a street or path, so a big block isn't timed from its middle.</p>
<ul>
<li><strong>Walk</strong>: 2 mph along OpenStreetMap's streets and paths, to the nearest place by walking distance. That's a child's pace for everyone, so these are kids' times, not an adult's.</li>
<li><strong>Low-stress bike</strong>: 10 mph on multi-use paths, protected bike lanes and <a href="https://data.sfgov.org/d/hkz3-itiu">Slow Streets</a>, from <a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a>. On every other street the rider walks the bike at 2 mph. A ride may go up to 25% farther than the shortest walk to stay on these routes. Painted lanes and signed routes don't count. We list rides up to 30 minutes.</li>
<li><strong>Muni or walk</strong>: the median scheduled door-to-door time for trips leaving between 8 and 9 AM on ${SERVICE_DAY}, on <a href="https://www.sfmta.com/reports/gtfs-transit-data">SFMTA's published schedule</a>, counting the walk to the stop and the wait. Where walking is faster, the walk is the time. We list trips up to 60 minutes. The trip planner is <a href="https://r5py.readthedocs.io/">r5py</a>, which runs Conveyal's R5.</li>
<li><strong>Car</strong>: the shortest drive along OpenStreetMap's streets at 13.4 mph, the median morning speed in the <a href="https://api.sfcta.org/api/inrix_rt_hourly_exp?date=eq.2026-09&amp;period=eq.8">San Francisco County Transportation Authority's September 2026 data</a>. We adjust that to match Google's drive times at school start and add 3 minutes to park and walk in. It doesn't model one-way streets or turns.</li>
</ul>

<h2>Where the Places Are</h2>
<ul>
<li><strong>Schools</strong>: open public and private schools by the grades they teach, from the <a href="https://www.cde.ca.gov/ds/si/ds/pubschls.asp">California Department of Education</a> and <a href="https://data.sfgov.org/d/7e7j-59qk">DataSF's Schools</a> list.</li>
<li><strong>Grocery stores</strong>: supermarkets, grocery stores and greengrocers mapped in OpenStreetMap. It misses many small grocers, so a grocery time may be longer than the real trip to the closest one.</li>
<li><strong>Libraries</strong>: the open San Francisco Public Library branches in <a href="https://data.sfgov.org/d/nc68-ngbr">City Facilities</a>, with Mission at its temporary site.</li>
<li><strong>Parks</strong>: <a href="https://data.sfgov.org/d/gtr9-ntp6">Recreation and Parks Properties</a>. A large park is one the department lists at 10 acres or more, leaving out the Park Presidio median.</li>
<li><strong>Commercial districts</strong>: SF Planning's neighborhood commercial districts on the <a href="https://data.sfgov.org/d/3i4a-hu95">zoning map</a>, plus the Chinatown and Downtown Retail districts. We leave out NC-1 zones, which are a corner store or a few shops.</li>
</ul>
<p>A park or district is reached at its edge, at any point on it within about 100 ft of a street or path.</p>

<h2>Frequent Muni</h2>
<p>A block has Muni every 5 minutes when a stop is within a quarter mile on foot (1,320 ft) and one route there leaves at least 24 times between 7 and 9 AM. Every 10 minutes means at least 12. We count one route, not every route at the stop added together, so two lines that each come every 10 minutes don't make a 5-minute stop. The line is sharp: many blocks sit near routes that come every 5 to 6 minutes, just short of it.</p>
<p>The nearest Muni stop in a block's card is the nearest with any service that day, which can be a stop served only by late-night Owl buses.</p>

<h2>The Faster T Third</h2>
<p>This is a what-if, not SFMTA's plan. We rewrote the schedule so the T Third comes every ${T3.headway_min ? T3.headway_min.value : 5} minutes all day in both directions, with every trip running the full line. We assume it runs Sunnydale to Chinatown in ${T3.end_to_end_min ? Math.round(T3.end_to_end_min.value) : 35} minutes. The August 26 morning schedule takes 45 to 48. Every other route keeps its published schedule. The 5 minutes and the 35 minutes are our assumptions, not SFMTA figures.</p>

<h2>What This Doesn't Show</h2>
<ul>
<li>The Muni times follow the schedule, not real arrivals, so a late or missed bus isn't in them.</li>
<li>Hills aren't counted in the walking or biking times.</li>
<li>The nearest place isn't always the one a family uses: a child's assigned school may be farther.</li>
</ul>
</div>`;
  return page({
    title: "About the Daily Trips Data",
    description: "How the Daily Trips map times walking, low-stress biking, Muni and driving trips from every San Francisco block, and what it can't tell you.",
    path,
    body,
    sources: SOURCES,
  });
}
