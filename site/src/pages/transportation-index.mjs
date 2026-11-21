// The Mobility front page, where Mobility in the breadcrumb lands: what people
// want, the goal, then links to the main dashboards and reports.
//
// Bryan, 2026-11-19, on the breadcrumb's Mobility item: "Mobility should now
// land on a Transportation front page that outlines the top level goal and then
// links to the main reports and dashboards". On 2026-11-20 he asked that the
// page "consistently say Mobility" and, of the goal text, "Base this on what we
// have in Part 1": so the three wants and the SPUR goal are the "What Do People
// Want?" section of the white paper's Part 1.1, in his words.
//
// /transportation was the bike network overview until 2026-09-29 and a redirect
// to /transportation/bike until this page replaced it.
//
// Each link's line is the page's own `listing` line (src/directory.mjs), so the
// page and the site's lists describe a report the same way. A link whose page
// this build hides (src/features.mjs) is left out, so Daily Trips shows on
// staging only, as its page does. Each link also shows when its page's data was read or the page last changed
// (src/page-dates.mjs), filled in by scripts/site-files.mjs.

import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { pathShown } from "../features.mjs";
import { dateMark } from "../page-dates.mjs";
import * as streetSafety from "./transportation-street-safety.mjs";
import * as muni from "./transportation-muni.mjs";
import * as dailyTrips from "./daily-trips.mjs";
import * as bike from "./post-sf-bike-network.mjs";
import * as travel from "./neighborhood-travel.mjs";
import * as wants from "./transportation-what-people-want.mjs";

export const path = "/transportation";
export const file = "transportation/index.html";

const GROUPS = [
  ["Dashboards", [streetSafety, muni, dailyTrips]],
  ["Reports", [bike, travel, wants]],
];

const item = (m) =>
  `<li><a href="${m.path}">${esc(m.listing.title)}</a>${m.listing.draft ? ' <span class="tag">Draft</span>' : ""}<span class="dir-line">${esc(m.listing.line)}</span>${dateMark(m.path)}</li>`;

const groups = GROUPS.map(([heading, mods]) => {
  const shown = mods.filter((m) => pathShown(m.path));
  return shown.length ? `<h2>${heading}</h2>\n<ul class="dir-list">\n${shown.map(item).join("\n")}\n</ul>` : "";
}).filter(Boolean).join("\n");

const BODY = `<h1>Mobility</h1>
<p class="lede">SF residents regularly say three things are important as they move around the city.</p>
<ul class="goals">
<li><strong>Convenience.</strong> Shorter trips, more frequent buses and trains, and living closer to transit.</li>
<li><strong>Safety.</strong> Low risk of crime, low traffic stress and low pedestrian stress.</li>
<li><strong>Cost.</strong> Biking, driving and transit are affordable.</li>
</ul>
<p>To make travel safe and convenient for everyone in a growing city, we need to do this:</p>
<blockquote><strong>"Walking, biking, and taking transit should be the safest and best ways to get around for people of all ages and abilities"</strong> (<a href="https://www.spur.org/policy-area/transportation">SPUR, Transportation</a>)</blockquote>
${groups}`;

const CSS = `<style>
.goals { padding-left: 1.2em; margin: 0 0 8px; }
.goals li { margin: 0 0 6px; line-height: 1.5; }
.dir-list > li > .tag { font-size: 0.75rem; vertical-align: 1px; color: var(--muted); background: var(--raised); }
</style>`;

export function render() {
  return page({
    title: "Mobility",
    description: "What San Franciscans want from getting around the city, and the dashboards and reports that track it.",
    path,
    body: CSS + BODY,
    directory: false,
  });
}
