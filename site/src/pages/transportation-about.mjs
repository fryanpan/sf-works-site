// About the Data: how every figure in the transportation section was made.
//
// Three parts, at Bryan's instruction on 2026-09-23: "1) Top Issues -- limit
// to 2 sentences each, and no more than 30 words ... 2) Explain how we did the
// analyses in this tool 3) Link to sources, but please organize a *lot*
// better". The method is grouped by the page each analysis feeds. Every other
// page in the section points here rather than carrying its own data
// discussion, so a caveat is written once and cannot drift between pages.
//
// The prose is in content/transportation-about.md so a person can edit it.
// Every figure is filled in here from the same data files the other pages
// build from, so a number on this page is the number on the page it explains.
// The OpenStreetMap comparison was dropped from the page on 2026-09-30 (Bryan:
// no analysis uses it); /transportation/osm redirects here.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { data, defs, miles, esc, sig2 } from "../transportation.mjs";
import { SOURCES as STREETS_SOURCES } from "../transportation-sources.mjs";
import { history, projects, rows, years, first, last, mi, pct, n, at, BLOCK_SOURCE, popSource, removed } from "../bike-history.mjs";
import { goal, walkNetwork as walkNet } from "../bike-explorer.mjs";
import { SOURCES as OVERVIEW_SOURCES } from "../bike-overview-sources.mjs";
import { PLAN_URL, APPENDIX_G_URL, BIKE_DATA_READ } from "../transportation.mjs";
import { SOURCES as FUTURE_SOURCES } from "./transportation-future.mjs";
import { SOURCES as PROJECT_SOURCES } from "./transportation-projects.mjs";
import { LAYER, label } from "./transportation-progress.mjs";
import { pathShown } from "../features.mjs";
import * as CP from "./transportation-community-plans.mjs";

export const path = "/transportation/bike/about";
export const file = "transportation/bike/about/index.html";

const DATA = nodePath.join(import.meta.dirname, "..", "..", "data");
const coord = JSON.parse(fs.readFileSync(nodePath.join(DATA, "coordination.json"), "utf8"));
const muni = JSON.parse(fs.readFileSync(nodePath.join(DATA, "bike-history", "muni-reach.json"), "utf8"));
const overlap = JSON.parse(fs.readFileSync(nodePath.join(DATA, "department-overlap.json"), "utf8"));
const reportedWork = JSON.parse(fs.readFileSync(nodePath.join(DATA, "bike-history", "reported.json"), "utf8"));
const parking = JSON.parse(fs.readFileSync(nodePath.join(DATA, "bike-history", "parking-reach.json"), "utf8"));

const S = history.sources;
const C = history.plan_comparison_2024;
const un = projects.unattributed;
const t = data.totals;
const u = data.undecided;
const cal = data.calming;

// Jobs outside construction that link neither a department page nor a closest
// official source: listed less linked less closest-only, per department.
const noSource = (dept) => {
  const d = coord.counts.departmentPageLinks[dept];
  return d.listed - d.linked - d.closestOnly;
};

const longDate = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
  });

// ---- The plan's own words for each class -----------------------------------
//
// In the order the plan puts them: strongest class first, then the shared tiers
// counting down, then the map label the plan never defines. Every row carries
// the printed page it is on, because sfmta.com serves the plan as a download
// and a link cannot open anyone to a page inside it.
const ROWS = [
  ["Separated", "separated.statement"],
  ["Shared", "shared.statement"],
  ["Shared Level I", "shared.level-i"],
  ["Shared Level II", "shared.level-ii"],
  ["Shared Level III", "shared.level-iii"],
  ["Bike lanes", "shared.bike-lanes"],
];

function definitionsTable() {
  const body = ROWS.map(([name, key]) => {
    const d = defs.detail[key];
    return `<tr><th scope="row">${esc(name)}</th><td>${esc(d.quote)}</td><td class="num">${esc(d.printedPage)}</td></tr>`;
  });
  body.push(
    '<tr><th scope="row">Undecided</th><td><em>The plan gives no definition. It appears three times, every one a map legend label, and it is not among the facilities Action 2.7.1 promises to define.</em></td><td class="num">68–69, 80–81</td></tr>',
  );
  return `<div class="scroll"><table>
  <thead><tr><th>Class</th><th>What the plan says</th><th class="num">Printed page</th></tr></thead>
  <tbody>
    ${body.join("\n    ")}
  </tbody>
</table></div>`;
}

// ---- The archived copies the history rests on --------------------------------
const snapshots = S.snapshots;
const archives = snapshots.filter((s) => s.kind === "archive");

function snapshotsTable() {
  const body = snapshots.map((s) => {
    const loaded = s.data_loaded_at ? s.data_loaded_at.split(" ")[0] : "—";
    return `<tr><td>${s.kind === "live" ? `<a href="${s.url}">SFMTA's live layer</a>` : `<a href="${s.url}">Internet Archive</a>`}</td><td class="num">${s.captured}</td><td class="num">${loaded}</td><td class="num">${s.blocks.toLocaleString()}</td><td class="num">${s.rows.toLocaleString()}</td><td class="num">${s.row_miles}</td><td class="num">${s.centerline_miles}</td></tr>`;
  });
  return `<p class="verdict-note">Every copy of the bikeway layer the history is read from. "Loaded" is the date DataSF stamped on the export where the export carries one. "Centerline" counts each street segment once.</p>
<div class="scroll"><table class="copies">
  <thead><tr><th>Copy</th><th class="num">Captured</th><th class="num">Loaded</th><th class="num">Segments</th><th class="num">Rows</th><th class="num">Miles</th><th class="num">Centerline</th></tr></thead>
  <tbody>${body.join("")}</tbody>
</table></div>`;
}

// One row per tier rather than per year: the twelve years rest on three kinds
// of evidence, and a reader wants the three, not the same sentence twelve times.
function yearsTable() {
  const groups = [];
  for (const r of rows) {
    const g = groups[groups.length - 1];
    if (g && g.tier === r.tier) g.rows.push(r);
    else groups.push({ tier: r.tier, rows: [r] });
  }
  const acs = (r) => (r.population_basis.match(/ACS (\d{4}–\d{4})/) || [])[1];
  const body = groups.map((g) => {
    const a = g.rows[0], b = g.rows[g.rows.length - 1];
    const span = a.year === b.year ? String(a.year) : `${a.year}–${b.year}`;
    let network, population;
    if (g.tier === "INSTALL_YR only") {
      network = `Install years in the first archived copy (${archives[0].captured}). Bikeways removed earlier are missing.`;
      population = `American Community Survey (${acs(a)} to ${acs(g.rows[g.rows.length - 2])}) over 2010 blocks. 2020 uses the Census.`;
    } else if (g.tier === "current") {
      network = `The live layer as of ${S.network.queried}.`;
      population = `Latest American Community Survey (${acs(a)}) over 2020 blocks.`;
    } else {
      const caps = archives.filter((c) => c.captured >= `${a.year}` && c.captured <= `${b.year + 1}-12-31`).map((c) => c.captured);
      network = `Archived copies from ${caps[0]} to ${caps[caps.length - 1]}. Changes between copies dated by update year.`;
      population = `American Community Survey (${acs(a)} to ${acs(b)}) over 2020 blocks. ${b.year} repeats ${acs(b)}.`;
    }
    return `<tr><th scope="row">${span}</th><td>${esc(network)}</td><td>${esc(population)}</td></tr>`;
  });
  return `<p class="verdict-note">What each year's figures rest on.</p>
<div class="scroll"><table class="years">
  <thead><tr><th>Years</th><th>Bike Network</th><th>Population</th></tr></thead>
  <tbody>${body.join("")}</tbody>
</table></div>`;
}

// Every source the section draws on, once. The same dataset read for two
// different reasons keeps both lines, because the reason is what the label
// says; only an exact repeat is dropped.
const seen = new Set();
const SOURCES = [
  ...OVERVIEW_SOURCES,
  ...FUTURE_SOURCES,
  ...STREETS_SOURCES,
  ...PROJECT_SOURCES,
].filter((s) => {
  const k = `${s.href}|${s.label}`;
  if (seen.has(k)) return false;
  seen.add(k);
  return true;
});

// ---- The Sources section ----------------------------------------------------
//
// One row per source, grouped by what it records (Bryan, 2026-09-23: "Link to
// sources, but please organize a *lot* better than you do now"). The pages'
// own source lists name a dataset once per reason they read it; here each
// source is one row and one link, and its read date is the latest date any
// page read it. The asks to the city sit under each top issue, in the page text.
// SFMTA's Active Communities Plan interactive map, which draws the 2023 Draft
// Bike Comfort Index among its layers (research/sources/sfmta-arcgis.md).
const BCI_MAP_URL = "https://tooledesign.maps.arcgis.com/apps/webappviewer/index.html?id=f948aa0022e246259ea899e5a4318427";
const normHref = (h) => String(h).replace("data.sfgov.org", "data.sf.gov").replace(/\/$/, "");
function readOf(...hrefs) {
  const keys = new Set(hrefs.map(normHref));
  const dates = SOURCES.filter((s) => s.href && keys.has(normHref(s.href)))
    .map((s) => String(s.read).slice(0, 10))
    .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d));
  return dates.sort().at(-1) ?? "";
}
const src = (name, href, use, read) => ({ name, href, use, read: read || readOf(href) });
const feedHref = () => coord.feed.url;

function sourceGroupsHtml() {
  const groups = [
    {
      name: "The plan and the law",
      rows: [
        src("Biking and Rolling Plan (March 2025)", PLAN_URL, "The North Star network and Appendix L, the all-ages test (p. 24), the class descriptions (pp. 74–77) and the network's printed mileage"),
        src("Appendix G, Toole Design connectivity memo (2024-02-13)", APPENDIX_G_URL, "How the plan measures who the network reaches"),
        ...(pathShown(CP.path) ? [src(`${CP.cap.plans.length} neighborhood, community and citywide plans, ${Math.min(...CP.cap.plans.map((p) => p.year))} to ${Math.max(...CP.cap.plans.map((p) => p.year))}`, `${CP.path}`, "The bikeways each plan asked for, with page and extent (listed under Community Plans above)", CP.cap.read)] : []),
        src("2023 Draft Bike Comfort Index", S.bci.url, "The comfort score the all-ages test applies to painted lanes and signed routes", S.bci.queried),
        src("Public Works Code §2.4.13", "https://codelibrary.amlegal.com/codes/san_francisco/latest/sf_publicworks/0-0-0-4453", "What a repaving project must include"),
        src("DataSF street centerlines (3psu-pn9h) and Census 2020 blocks (p2fw-hsrv)", BLOCK_SOURCE.url, "The typical length of a city block, weighted by where people live", BLOCK_SOURCE.read),
        src("OpenStreetMap, walkable ways via Overpass", "https://www.openstreetmap.org/copyright", "The streets, stairways and paths walking distance is measured along", walkNet.fetched_on.slice(0, 10)),
      ],
    },
    {
      name: "The bike network",
      rows: [
        src("SFMTA bikeway layer, SFMTA's own copy", S.network.url, "Every bikeway street segment, its class, and its install and update years", S.network.queried),
        src("MTA Bike Network Linear Features on DataSF (ygmz-vaxd)", "https://data.sf.gov/d/ygmz-vaxd", `The repaving check, and each year's class from ${archives.length} Internet Archive copies`),
        src("Slow Streets (hkz3-itiu)", "https://data.sf.gov/d/hkz3-itiu", "Implemented Slow Streets and their install dates"),
        src("Mid-Block Traffic Calming Areas (abhw-ffzx)", "https://data.sf.gov/d/abhw-ffzx", "Calming built on Shared streets"),
        src("Intersection-Level Traffic Calming Devices (bp3t-bd4t)", "https://data.sf.gov/d/bp3t-bd4t", "Calming built on Shared streets", readOf("https://data.sf.gov/d/abhw-ffzx")),
      ],
    },
    {
      name: "Streets and street work",
      rows: [
        src("Utility Excavation Moratorium Streets (5wbp-dwzt)", "https://data.sf.gov/d/5wbp-dwzt", "Each repaved street segment's limits and job order"),
        src("Pavement condition history (78va-8dhi)", "https://data.sf.gov/d/78va-8dhi", "Every resurfacing since 1947: which street segments on the plan were repaved, and when, and the repaving rate"),
        src("Public Works Internal & External Projects (btxj-k9uh)", feedHref(), "The coordination feed: each job's owner, phase, dates, scope and street segments"),
        src("Street centerlines (3psu-pn9h)", "https://data.sf.gov/d/3psu-pn9h", "Street segment geometry, one-way streets, and the lines the plan was traced onto"),
      ],
    },
    {
      name: "Projects and city decisions",
      rows: [
        src("SFMTA project layer and project pages", "https://www.sfmta.com/projects", `Each SFMTA project's line, phase, project type and scope, and the work its pages report finished in ${years[years.length - 1]}`),
        src("SFMTA engineering public hearings", "https://www.sfmta.com/past-meetings-and-events/2617", "Directive orders naming a street"),
        src("SFMTA Board of Directors agendas and minutes", "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=55", "Board items naming a street"),
        src("Board of Supervisors legislation (Legistar)", "https://sfgov.legistar.com/Legislation.aspx", "Files naming a street, 2019–2026"),
        src("SFPUC Commission", "https://sfpuc.gov/about-us/our-commission", "Agenda items naming a street, 2021–2026"),
      ],
    },
    {
      name: "People and places",
      rows: [
        src("Census 2020 blocks (p2fw-hsrv)", "https://data.sf.gov/d/p2fw-hsrv", "Population and location of every census block"),
        src("Census 2010 blocks, TIGERweb", "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2010/MapServer/18/query", "Population for the years before 2020"),
        src("American Community Survey 5-year, table B01003", "https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000", "Population by block group, 2015 to 2024"),
        src("California Department of Education school directory", "https://web.archive.org/web/20251005140551id_/https://www.cde.ca.gov/SchoolDirectory/report?rid=dl1&tp=xlsx&ict=Y", "Public schools, their types and open dates"),
        src("DataSF Schools (7e7j-59qk)", "https://data.sf.gov/d/7e7j-59qk", "Private K-12 schools and their open dates, and a cross-check on the public school count", S.schools.private.queried),
        src("City Facilities (nc68-ngbr)", "https://data.sf.gov/d/nc68-ngbr", "Library branches and the Main Library"),
        src("Muni Stops (i28k-bkz6)", "https://data.sf.gov/d/i28k-bkz6", "Residents within reach of a Muni stop", muni.source.queried),
        src("On-Street Parking Census (9ivs-nf5y)", "https://data.sf.gov/d/9ivs-nf5y", "Residents within reach of on-street parking", parking.source.queried),
      ],
    },
  ];
  return groups.map((g) => `<h3>${g.name}</h3>
<div class="scroll"><table class="sources">
  <thead><tr><th>Source</th><th>Used for</th><th>Read</th></tr></thead>
  <tbody>${g.rows.map((r) => `<tr><td><a href="${r.href}">${esc(r.name)}</a></td><td>${esc(r.use)}</td><td class="date">${r.read}</td></tr>`).join("")}</tbody>
</table></div>`).join("\n");
}

const ft = (m) => Math.round(m * 3.28084).toLocaleString();

// The method behind the Community Plans page, shown only where that page is
// built (src/features.mjs), with the proposals it couldn't draw.
function communityPlansMethod() {
  const c = CP.cap, t = CP.totals, k = (v) => v.toLocaleString("en-US");
  const mi = (ft) => sig2(ft / 5280);
  const plans = c.plans.map((p) => `<a href="${esc(p.url)}">${esc(p.name)}</a> (${p.year})`).join(", ");
  const WHY = { end: "An end is a landmark, the map's edge, or not stated", path: "A path, bridge, trail or unnamed street with no centerline", broken: "The two ends don't meet along one street" };
  const rows = c.unplaced.rows.map((u) => `<tr><td>${esc(c.plans[u.plan].name)}</td><td>${esc(u.street)}</td><td>${esc(u.from)}</td><td>${esc(u.to)}</td><td>${esc(WHY[u.reason])}</td></tr>`).join("");
  return `<h3 id="community-plans">Community Plans</h3>
<p><a href="${CP.path}">Community Plans</a> maps the bikeways that earlier city, community and advocacy plans asked for, one color per plan, over the 2025 plan and today's all-ages network.</p>
<ul>
<li><strong>The plans.</strong> ${c.plans.length} plans: ${plans}.</li>
<li><strong>The proposals.</strong> We read each plan on ${c.read} and wrote down every street it proposed a bike improvement on, with its two ends, its page and what it proposed. That's ${k(c.proposalCount)} proposals, leaving out one row that describes lanes already built in 2007. A plan recommends a proposal unless it only listed it as an option and set it aside. For SFMTA's <a href="https://www.sfmta.com/media/41119/download">November 2024 first draft</a> of the Biking and Rolling Plan, we traced its North Star map and kept only the lines the adopted plan doesn't draw, or draws as Undecided.</li>
<li><strong>Drawing them.</strong> Each proposal runs along the city's <a href="https://data.sf.gov/d/3psu-pn9h">street centerline blocks</a> between its two cross streets, using the same matcher that <a href="#trace">traced the plan's network</a>. Where an end names two streets, like Vicente St / Sloat Blvd, we use the first, and we drop any block past either named end. We drew ${k(c.placedCount)} of them, on ${k(c.blocks.length)} blocks.</li>
<li><strong>Left out.</strong> A block a plan asks for is left out of the 2025 plan when it isn't all-ages today by <a href="#definitions">the plan's test</a> and the North Star map doesn't draw it Separated, Shared, Shared-use Path or Car-free. With every plan on, that's ${mi(t.out.feet)} of the ${mi(t.asked.feet)} miles they ask for. An ask is a bikeway a plan recommends, so an option it set aside isn't one, and neither is the Columbus Avenue study's road diet, which asks riders to share a wide lane rather than get a bike lane. Those show only in a street's card. A block the North Star map draws as Undecided isn't left out. We drop a block under 100 feet whose neighbors are all-ages, since it's an intersection jog.</li>
<li><strong>Colors.</strong> Each plan with a street on the map gets its own color, dealt oldest plan first from the <a href="https://d3js.org/d3-scale-chromatic/categorical#schemeObservable10">Observable 10</a> scheme, less its grey, which the map keeps for the 2025 plan. After nine plans the colors repeat dashed, then dotted. Plans that ask for the same block are drawn side by side.</li>
<li><strong>Miles.</strong> Each block counts once, whatever the direction of travel. The centerline file draws each side of a divided street like Geary as its own block, so we keep the longer side. Elsewhere on this site, bike network miles count each direction of travel.</li>
</ul>
<h4 id="community-plans-unplaced">Proposals We Couldn't Draw</h4>
<p>${k(c.proposalCount - c.placedCount)} proposals have no two cross streets to draw between, so the map leaves them out.</p>
<div class="scroll"><table>
  <thead><tr><th>Plan</th><th>Street</th><th>From</th><th>To</th><th>Why</th></tr></thead>
  <tbody>${rows}</tbody>
</table></div>`;
}

export function render() {
  // Corridors the 2020 and 2021 Slow Streets reports approved that the 2022
  // report neither keeps nor drops (tools/bike-network/bike-removals.py).
  const unaccounted = (removed?.unaccounted || []).map((u) => u.words.split(" from ")[0]);
  const body = content("transportation-about", {
    unaccountedCount: unaccounted.length,
    // The dropped pandemic Slow Street miles in the all-ages series, per
    // direction (tools/bike-network/bike-network-history.py).
    pandemicYear: (history.rows.find((r) => r.pandemic_dropped_miles > 0) || {}).year,
    pandemicLastYear: (history.rows.find((r) => r.pandemic_dropped_miles > 0) || { year: 1 }).year - 1,
    // removed.json's dropped miles, which the pipeline checks against the
    // history's drop that year (transportation-quality.py).
    pandemicDropped: mi(removed?.summary.slow_street_dropped_miles || 0),
    // ---- the issues
    firstYear: years[0],
    residentsTotal: n(last.residents_total),
    // The explorer's total is an ACS estimate held for the latest years, not
    // that year's population (audit F2 reads this sentence).
    residentsSource: popSource(last),
    goalMiles: mi(goal.goalMiles),
    planMiles: mi(goal.planMiles),
    offPlanMiles: mi(goal.offPlanMiles),
    paceMiles: String(Math.round(goal.pace)),
    paceFrom: goal.paceFrom,
    paceTo: goal.paceTo,
    goalYear: goal.goalYear,
    lastYear: years[years.length - 1],
    blockFt: BLOCK_SOURCE.used_ft.toLocaleString(),
    twoBlockFt: (2 * BLOCK_SOURCE.used_ft).toLocaleString(),
    walkRead: walkNet.fetched_on.slice(0, 10),
    quarterFt: ft(at(last, "quarter").metres),
    planUrl: PLAN_URL,
    appendixUrl: APPENDIX_G_URL,
    bciThreshold: S.bci.threshold,
    bciUrl: S.bci.url,
    attributedMiles: mi(projects.attributed.miles),
    attributedProjects: projects.projects.filter((p) => !p.stand_in).length,
    standInStreets: projects.projects.filter((p) => p.stand_in).length,
    muniStops: muni.source.stops.toLocaleString(),
    reportedRead: longDate(reportedWork.generated),
    reportedCount: reportedWork.projects.length,
    reportedItems: `<ul>${reportedWork.projects
      .map((r) => `<li><a href="${r.page}">${esc(r.name.replace(/ \(The Hairball\)/, ""))}</a>: “${esc(r.quote)}”</li>`)
      .join("")}</ul>`,
    bciMapUrl: BCI_MAP_URL,
    reportedMiles: (() => {
      const log = (history.sources.reported || {}).projects || [];
      return log.reduce((t, r) => t + r.row_miles_upgraded + r.row_miles_added, 0).toFixed(1);
    })(),
    parkingSpaces: parking.source.spaces.toLocaleString(),
    parkingFrom: parking.source.surveyed[0],
    parkingTo: parking.source.surveyed[1],
    unattributedMiles: mi(un.miles),
    firstArchive: archives[0].captured,
    firstArchiveUrl: archives[0].url,
    archiveCount: archives.length,
    unknownMiles: mi(first.miles_class_unknown),
    preClassIV: mi(first.class_iv_miles_with_install_before_2014),
    bikewayLayerAsOf: data.bikewayLayerAsOf,
    layerUrl: LAYER.service,
    layerLatest: label(LAYER.latestInstall),
    onPlan: t.onPlan,
    unverifiable: t.unverifiable,
    checkable: t.checkable,
    checkableShortfall: t.checkableShortfall,
    sharedSegments: cal.sharedSegments,
    onSlowStreet: cal.onSlowStreet,
    calmingOnly: cal.calmingOnly,
    neither: cal.neither,
    slowStreetsAsOf: cal.slowStreetsAsOf,
    cmpYear: C.year,
    cmpOurs: pct(C.ours_plan_definition_share),
    cmpPlan: pct(C.plan_reported_share),
    registrationMedianFt: ft(data.registration.medianMetres),
    registrationP90Ft: ft(data.registration.p90Metres),
    feedUrl: coord.feed.url,
    feedJobs: coord.feed.jobs,
    feedQueried: coord.feed.queried,
    listed: coord.counts.listed,
    ovHorizonYear: overlap.horizon.slice(0, 4),
    pastFromLong: longDate(overlap.compare[0].from),
    ovSpotMiles: overlap.summary.spot.miles.toFixed(1),
    ovLaterMiles: overlap.summary.others.laterOrUndated.toFixed(1),
    ovSfmtaMiles: overlap.summary.sfmta.miles.toFixed(1),
    ovSharedNone: overlap.summary.othersSharedNone.toFixed(1),
    ovMiles: overlap.summary.others.miles.toFixed(1),

    bciUnscoredMiles: sig2(S.bci.unscored.miles),
    netEnd: mi(last.network_miles),
    snapshotsTable: snapshotsTable(),
    yearsTable: yearsTable(),
    schoolsCde: S.schools.open_now_public,
    schoolsPrivate: S.schools.open_now_private,
    schoolsNow: S.schools.open_now_total,
    lineToleranceFt: ft(projects.sources.project_geometry.tolerances_m.line),

    // ---- after repaving and planned against built
    adoptedLong: longDate(data.adopted),
    repavedSinceAdoption: data.repavedSinceAdoption.toLocaleString(),
    definitionsTable: definitionsTable(),
    definitionsPendingQuote: defs.detail["network.definitions-pending"].quote,
    definitionsPendingPage: defs.definitionsArePending.printedPage,
    l3Ceiling: defs.detail["map.shared-l3-ceiling"].quote,
    l3CeilingPage: defs.detail["map.shared-l3-ceiling"].printedPage,
    undecidedSegments: u.segments,
    undecidedMiles: miles(u.metres),
    undecidedNothing: u.withNothing,
    undecidedOnlySharrow: u.onlySharrow,
    undecidedPaintedOrBetter: u.paintedOrBetter,

    // ---- projects
    sfmtaGenerated: coord.sfmtaLayer.generated,
    otherAgencyCount: (coord.otherAgencyOnPlan || []).length,
    sfmtaConsidered: coord.counts.sfmtaConsidered,
    sfmtaListed: coord.counts.sfmtaListed,
    pagesLinked: Object.values(coord.counts.departmentPageLinks).reduce((s, d) => s + d.linked, 0),
    noSourceJobs: noSource("Public Works") + noSource("SFPUC"),
    rankingRule: coord.ranking.rule,
    // The plan rating's bands (tools/projects/coordination-projects.py plan_rating).
    ratingBands: [
      ["all", "build 100%"],
      ["most", "build 50 to 99%"],
      ["some", "build 1 to 49%"],
      ["none", "build 0%, nearly all by a published scope that names no bike work"],
      ["not-stated", "are not stated"],
      ["already-built", "are already built"],
      ["no-overlap", "have no known overlap"],
    ]
      .map(([k, label]) => [coord.counts.planRatingByBand?.[k] ?? 0, label])
      .filter(([k]) => k)
      .map(([k, label]) => `${k} ${label}`)
      .join("; "),
    withStart: coord.counts.withStart,
    underWay: coord.counts.underWay,

    sourceGroups: sourceGroupsHtml(),
    communityPlansMethod: pathShown(CP.path) ? communityPlansMethod() : "",
    communityPlansLink: pathShown(CP.path) ? ` <a href="${CP.path}">Community Plans</a> maps the bikeways earlier neighborhood plans asked for that this network leaves out.` : "",
  });

  return page({
    title: "About the data",
    description:
      "How every figure in the transportation section was made: the top data issues, " +
      "the method behind each page, and every source grouped by what it records.",
    path,
    dataUpdated: BIKE_DATA_READ,
    body: CSS + body + MERMAID_SCRIPT,
  });
}

// Mermaid draws the ```mermaid blocks in the reader's browser (see
// content.mjs). Pinned to a major version; the theme uses the site's sans
// font and calm neutrals so the diagrams match the page.
const MERMAID_SCRIPT = `<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({ startOnLoad: true, theme: "base", flowchart: { curve: "basis", useMaxWidth: true, wrappingWidth: 340 },
  themeVariables: { fontFamily: getComputedStyle(document.body).fontFamily, fontSize: "14px",
    primaryColor: "#ffffff", primaryBorderColor: "#4a5560", primaryTextColor: "#1d2a36", lineColor: "#7a8590" } });
</script>`;

// The issues are a ranked list of short items; the sources are one table per
// group.
const CSS = `<style>
ol.issues { padding-left: 1.6em; }
ol.issues li { margin: 0 0 10px; }
ol.issues li::marker { font-weight: 700; color: var(--accent); }
h3 { font-size: 1.3rem; margin-top: 40px; }
h4 { font-size: 1.08rem; margin: 28px 0 6px; }
table.years td { font-size: 0.9rem; }
table.copies td.num, table.copies th.num { white-space: nowrap; }
table.sources td { vertical-align: top; }
table.sources td.date { white-space: nowrap; }
ol.issues .ask { display: block; margin-top: 3px; font-size: 0.9em; color: var(--muted); }
ol.issues .ask b { color: var(--ink); font-weight: 600; }
/* Mermaid diagrams (content/transportation-about.md): the source text shows
   until Mermaid draws, so it is kept small and quiet. */
figure.diagram { margin: 16px 0 24px; padding: 16px; background: var(--raised); border-radius: 6px; overflow-x: auto; }
/* Each data node lists its datasets as bullets, so they read left-aligned. */
figure.diagram g.node[id*="-dn"] .nodeLabel { display: block; text-align: left; }
figure.diagram pre.mermaid { margin: 0; text-align: center; font-size: 0.8rem; color: var(--muted); white-space: pre-wrap; }
</style>`;
