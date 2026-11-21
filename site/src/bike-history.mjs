// The bike network since 2015, for the transportation overview: the data the
// repo's tools/bike-network/bike-network-history.py and
// tools/bike-network/bike-network-projects.py wrote under data/bike-history/, and the
// animated map.
//
// The map is MapLibre over the site's basemap (src/maplibre.mjs), with its
// data riding in the page as inert JSON; its script steps the map through the
// years.

import fs from "node:fs";
import path from "node:path";
import { streetName } from "./street-name.mjs";
import { encodeRuns, encodePoints, inlineJson } from "./maplibre.mjs";

const DATA = path.join(import.meta.dirname, "..", "data", "bike-history");
const read = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8"));
// SFMTA's planned bikeway projects, by the year each project page gives for
// finishing, written by tools/bike-network/bike-reported-work.py.
const planned = fs.existsSync(path.join(DATA, "planned.json")) ? read("planned.json") : { projects: [] };

export const history = read("history.json");
export const projects = read("projects.json");
// What each project did and why, from its SFMTA page, keyed by node.
const SUMMARIES = read("project-summaries.json").summaries;
const allAges = read("all-ages.geojson");
const reach = read("reach.json");
const segments = read("segments.json");
// Bikeway blocks that dropped out of SFMTA's layer, and the pandemic Slow
// Streets SFMTA's Board reports name as removed, written by
// scripts/bike-removals.py.
export const removed = fs.existsSync(path.join(DATA, "removed.json")) ? read("removed.json") : null;

export const rows = history.rows;
export const years = history.years;
export const first = rows[0];
export const last = rows[rows.length - 1];

// ---- Reach thresholds ---------------------------------------------------------
//
// The script computes who is within reach at four distances: the plan's
// quarter mile, one and two city blocks (440 and 880 feet, near the typical
// block pipeline/sources/sf-block-length.py measures; history.block_source carries it),
// and 1,000 feet (the ITDP Atlas's protected-bikeway distance),
// each walked along the street network (lib/walknet.py). Every reach figure, the
// reach chart and the map's lit points are rendered once per distance inside a
// .reach-var wrapper, and html[data-reach] picks which one shows, so the page
// works with no script and switches without a rebuild.
export const THRESHOLDS = history.reach_thresholds;
export const DEFAULT_REACH = history.default_reach;
export const BLOCK_SOURCE = history.block_source;
export const at = (r, id) => r.reach_by_threshold[id];
// The word for the distance as a sentence uses it: "a quarter mile", "about one block (440 feet)".
const shortOf = Object.fromEntries(THRESHOLDS.map((t) => [t.id, t.short]));

/** A display:none rule per distance, so only the chosen variant renders. */
export const REACH_CSS = `<style>
${THRESHOLDS.map((t) => `html[data-reach="${t.id}"] .reach-var:not([data-reach-for="${t.id}"]) { display: none; }`).join("\n")}
html:not([data-reach]) .reach-var:not([data-reach-for="${DEFAULT_REACH}"]) { display: none; }
</style>`;

/** Where a year's resident total comes from, in a few words: the 2020 census,
 * or the American Community Survey release it is held at. Project pages count
 * 2020 census blocks instead, so each total names its source (audit F2). */
export function popSource(r) {
  const acs = (r.population_basis.match(/ACS (\d{4}–\d{4})/) || [])[1];
  return acs ? `${acs} American Community Survey` : "2020 census";
}

// Whole miles on this page: the lengths are SFMTA's own line geometry summed
// per direction row, the plan's unit, and a decimal on a city-wide total is
// not information a reader can use. Below ten miles — a project's
// contribution — one decimal.
export const mi = (m) => (m >= 10 ? Math.round(m).toLocaleString() : (Math.round(m * 10) / 10).toFixed(1));
export const pct = (share) => Math.round(100 * share);
export const n = (v) => Math.round(v).toLocaleString();

// The years that rest on install dates alone, before the first archived copy.
export const undatedYears = rows.filter((r) => r.tier === "INSTALL_YR only").map((r) => r.year);

// The year the all-ages line jumped most, and what made it jump.
export function biggestJump() {
  let best = null;
  for (let i = 1; i < rows.length; i++) {
    const d = rows[i].all_ages_miles - rows[i - 1].all_ages_miles;
    if (!best || d > best.miles) best = { year: rows[i].year, miles: d, row: rows[i], prev: rows[i - 1] };
  }
  const ss = (r) => r.slow_street_miles_on_bikeway_blocks + r.slow_street_miles_not_in_bikeway_layer + (r.pandemic_slow_street_miles || 0);
  const slow = ss(best.row) - ss(best.prev);
  return { ...best, slow, bikeway: best.row.all_ages_bikeway_miles - best.prev.all_ages_bikeway_miles };
}

// ---- Charts -----------------------------------------------------------------
//
// Both charts share one frame: x is the year, y starts at zero. A y axis that
// started above zero would draw a 7% change in the network as a climb.

// The labels the chart carries (Bryan, 2026-09-23: "label 2-3 interesting
// points ... what was the big jump in 2020? ... in 2023-2024?"): the biggest
// one-year step, the biggest two-year step outside it, and the tail since the
// last of those. Each label's breakdown is computed from the layer's facility
// classes between its two years, so the figures cannot drift from the line.
function stepBetween(a, b) {
  const ra = rows[years.indexOf(a)], rb = rows[years.indexOf(b)];
  const d = (k) => rb[k] - ra[k];
  const gain = d("all_ages_miles");
  // The Slow Streets hkz3-itiu lists, and the pandemic ones SFMTA dropped.
  const slow = d("slow_street_miles_on_bikeway_blocks") + d("slow_street_miles_not_in_bikeway_layer") + d("pandemic_slow_street_miles");
  const sep = d("class_iv_miles");
  const path = d("class_i_miles");
  // What is left is bikeway admitted by the plan's comfort test (Class II and
  // III with BCI over 80) and the reclassification of Slow Street blocks that
  // already qualified; it is named with the separated lanes when it is a mile
  // or more.
  const other = gain - slow - sep - path;
  return { from: a, to: b, gain, slow, sep, path, other };
}
export function chartSteps() {
  const j = biggestJump();
  let two = null;
  for (let i = 2; i < rows.length; i++) {
    if (years[i] === j.year || years[i - 1] === j.year) continue;
    const s = stepBetween(years[i - 2], years[i]);
    if (!two || s.gain > two.gain) two = s;
  }
  const lastStep = Math.max(j.year, two.to);
  const tail = lastStep < years[years.length - 1] ? stepBetween(lastStep, years[years.length - 1]) : null;
  return { jump: stepBetween(j.year - 1, j.year), two, tail };
}

// ---- The animated map -------------------------------------------------------

// The map's drawing unit: a thousandth of the bikeway network's width, about
// 11 m. The labels beside the city, the line widths and the dot sizes are
// given in it, as the SVG map this replaced drew them, and the page turns it
// into pixels at the opening view.
const MW = 1000;
function projector() {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const s of segments.segments) {
    for (const [lx, ly] of s.pts) {
      if (lx < x0) x0 = lx; if (lx > x1) x1 = lx; if (ly < y0) y0 = ly; if (ly > y1) y1 = ly;
    }
  }
  const k = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
  const scale = MW / ((x1 - x0) * k);
  // Metres per drawing unit: one degree of latitude is 111,195 m on the sphere the generator uses.
  return { height: Math.round((y1 - y0) * scale), metresPerUnit: 111194.9 / scale, point: ([lx, ly]) => [Math.round((lx - x0) * k * scale), Math.round((y1 - ly) * scale)],
    // Unrounded, for the explorer, whose distances are measured in these units.
    pointF: ([lx, ly]) => [(lx - x0) * k * scale, (y1 - ly) * scale] };
}
export const P = projector();
export { MW, segments, reach };
/** The bikeway network's bounds, [[west, south], [east, north]]: the map's opening view. */
export const BOUNDS = (() => {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const sg of segments.segments) for (const [x, y] of sg.pts) { if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y; }
  return [[w, s], [e, n]];
})();
// Lines and dots ride in the page at the data's own precision, about a
// metre, each point as its offset from the one before (encodeRuns in
// maplibre.mjs), which keeps the page small.
/** A list of blocks, each a list of [lon, lat], encoded for the page. */
const D = (list) => encodeRuns(list);
// Street length of a block's line, in miles (haversine, per vertex pair).
const lineMiles = (pts) => pts.slice(1).reduce((a, [lon, lat], i) => {
  const [lon0, lat0] = pts[i], r = Math.PI / 180;
  const h = Math.sin((lat - lat0) * r / 2) ** 2 + Math.cos(lat0 * r) * Math.cos(lat * r) * Math.sin((lon - lon0) * r / 2) ** 2;
  return a + 2 * 3958.8 * Math.asin(Math.sqrt(h));
}, 0);

// ---- Removals -----------------------------------------------------------------
//
// Bryan, 2026-09-29, on the map: "How do we track and show bike
// infrastructure removals throughout this report?" A bikeway block that
// dropped out of SFMTA's layer is drawn as removed from the first year its
// archived copy lacks it. A pandemic Slow Street SFMTA dropped is drawn as an
// all-ages bikeway from the year it went in through the year before
// removed.dropped_year, and as removed in that year: SFMTA's December 2022
// report dropped them and removed some "throughout the COVID Response phase"
// and the rest "in the Winter 2023", with no date for any one street. The
// all-ages miles and reach count them over the same years
// (tools/bike-network/bike-network-history.py, from lib/slow_corridors.py).
const MONTH = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const REPORT_2022 = removed?.sources.reports.find((r) => r.url.includes("33575")) || null;
const captureUrl = (date) => (history.sources.snapshots.find((s) => s.captured === date) || {}).url || history.sources.network.url;

/** The removed bikeways, grouped by street, class and the two copies either side of the removal. */
export function removedBikeways() {
  if (!removed) return [];
  const groups = new Map();
  // Only blocks that were all-ages: this is the all-ages map, and a signed
  // route that never met the plan's test (Irving Street and Sunset Boulevard,
  // dropped from SFMTA's layer in 2025) was never on it (Bryan, 2026-09-29:
  // "What happened with Sunset and Irving? Why are these marked as removals?").
  const wasAllAges = new Set(allAges.features.map((f) => String(f.properties.cnn)));
  for (const b of removed.bikeways.filter((b) => wasAllAges.has(String(b.cnn)))) {
    const k = `${b.name}|${b.code}|${b.seen}|${b.gone_by}`;
    if (!groups.has(k)) groups.set(k, { id: `rm:${slug(k)}`, name: streetName(b.name || "Unnamed path"), facility: b.facility, seen: b.seen, goneBy: b.gone_by, year: b.gone_year, blocks: [], miles: 0 });
    const g = groups.get(k);
    g.blocks.push(b);
    g.miles += b.street_miles;
  }
  // The run's ends: the cross streets named once among its blocks' from and to.
  for (const g of groups.values()) {
    const seen = new Map();
    for (const b of g.blocks) for (const x of [b.from, b.to]) if (x) seen.set(x, (seen.get(x) || 0) + 1);
    // A divided street's two carriageways name the same pair twice.
    const once = [...seen].filter(([, c]) => c === 1);
    const ends = (once.length === 2 ? once : seen.size === 2 ? [...seen] : []).map(([x]) => streetName(x));
    g.extent = ends.length === 2 ? `from ${ends[0]} to ${ends[1]}` : "";
  }
  return [...groups.values()];
}

/** The pandemic Slow Street corridors with any block removed; a kept corridor
 * whose only non-kept blocks carry a later install date in the dataset
 * (Cabrillo Street) is a re-entry, not a removal. */
export function removedSlowStreets() {
  if (!removed) return [];
  return removed.slow_streets.filter((c) => c.blocks.some((b) => b.status === "removed")).map((c) => ({
    ...c, id: `ss:${c.id}`, name: `${streetName(c.street)}`,
    // Street length, counted once: the length an advocate and SFMTA quote.
    removedMiles: c.removed_street_miles, readoptedMiles: c.readopted_street_miles, replacedMiles: c.replaced_street_miles || 0,
  }));
}

function removalLayers() {
  if (!removed) return { lines: [], hits: [], cards: [] };
  // Removed from the year of SFMTA's December 2022 report, the year the
  // miles-added chart's callout gives (Bryan, 2026-09-29: "This is not
  // showing the dropped Slow Streets in 2022?"). While in place a pandemic
  // Slow Street is drawn as any other all-ages bikeway, and a removal shows
  // only in the year it went, labelled (Bryan, 2026-09-29: "show bikeway the
  // same as pandemic slow street. And show removed just for that year with a
  // label like "REMOVED: <project name>""), naming what went, not the street
  // ("REMOVED: ??? Slow Street so it's clear we're not removing the street").
  const by = removed.dropped_year;
  const lines = [], hits = [], cards = [];
  for (const g of removedBikeways()) {
    const runs = g.blocks.map((b) => b.pts);
    lines.push({ k: "rm", y: 0, open: g.year, closed: g.year + 1, g: D(runs) });
    hits.push({ proj: g.id, from: g.year, until: g.year + 1, g: D(runs) });
    cards.push([g.id, {
      removed: true, name: `${g.name} ${g.facility}`, page: captureUrl(g.seen), more: "SFMTA's bikeway data as archived before the removal",
      when: `Dropped from SFMTA's bikeway data between ${MONTH(g.seen)} and ${MONTH(g.goneBy)}.`,
      rows: [["Removed", `${mi(g.miles)} mi of street, ${g.facility}`], ["Where", `${g.name} ${g.extent}`.trim()]],
    }]);
  }
  for (const c of removedSlowStreets()) {
    const gone = c.blocks.filter((b) => b.status === "removed"), back = c.blocks.filter((b) => b.status === "readopted");
    if (gone.length) lines.push({ k: "aa", y: c.installed, closed: by, g: D(gone.map((b) => b.pts)) },
      { k: "rm", y: 0, open: by, closed: by + 1, g: D(gone.map((b) => b.pts)) });
    // A re-adopted block is out in the year it was dropped and drawn again
    // from its re-adoption, from all-ages.geojson like any kept Slow Street.
    for (const b of back) lines.push({ k: "aa", y: c.installed, closed: by, g: D([b.pts]) });
    hits.push({ proj: c.id, from: c.installed, until: by, g: D([...gone, ...back].map((b) => b.pts)) });
    if (gone.length) hits.push({ proj: c.id, from: by, until: by + 1, g: D(gone.map((b) => b.pts)) });
    const rows = [];
    if (c.removedMiles) rows.push(["Removed", `${mi(c.removedMiles)} mi of street`]);
    if (c.replacedMiles) rows.push(["Still all-ages as another bikeway", `${mi(c.replacedMiles)} mi of street`]);
    if (back.length) rows.push(["Back as a Slow Street", `${mi(c.readoptedMiles)} mi, from ${Math.min(...back.map((b) => b.back || by))}`]);
    cards.push([c.id, {
      removed: true, name: `${c.name} Slow Street`, page: REPORT_2022?.url || c.source, more: "SFMTA's December 2022 Board report",
      when: `A pandemic Slow Street from ${c.installed}. SFMTA ${c.fate === "kept" ? "shortened" : "dropped"} it in December 2022 and gives no date for its removal.`,
      summary: `SFMTA's ${c.installed === 2021 ? "2021" : "2020"} list: “${c.words}”`,
      rows,
    }]);
  }
  return { lines, hits, cards };
}

export { inlineJson };

// The year's largest new projects are labelled on the map as they appear
// (Bryan, 2026-09-23: "in each year, mark down the new projects on the map
// with a label"): every project that added at least LABEL_MIN miles in the
// year. The labels sit in margins left and right of the peninsula, each with
// a thin leader to its dot, stacked so none overlaps (Bryan, 2026-09-23:
// "Text labels are nice, but too big and too much emphasis. Have them show up
// to the left and right of the SF peninsula on the map and have light lines
// that point to where they are"). The page lays them out on screen, in the
// drawing units below times the map's pixels per unit, so they keep their
// size beside the city whatever the screen; the build picks and names them.
const LABEL = {
  // Wide screens: the margins beside the city are 290 units each,
  // the label 18 units tall, 30 apart, and the left column starts below the
  // residents share laid over the map's top-left corner (Bryan, 2026-09-23:
  // "Move the play controls into the top left corner of the map").
  // Quieter since Bryan, 2026-09-30, on the Google preview: the labels "get
  // cut off with … cause they're too big. Plus they take too much focus":
  // smaller type in the muted ink, the full name over two lines, thinner
  // leaders and smaller photos.
  pw: { margin: 290, font: 16, gap: 26, leftTop: 340, rightTop: 16, line2: 17.5, circle: 3.5, circleStroke: 1.2, lead: 0.7 },
  // Phones get their own set (Bryan, 2026-09-24: "On the phone at 100% I
  // don't see the labels. On phone can you zoom out a bit so SF takes out
  // less space and show labels to the left and right"): wider margins, so the
  // city draws smaller, with larger type, shorter names, no images and the
  // left column from the top, since the controls sit above the map there.
  // On a 390-pixel screen the city is about 205 pixels wide and a label about
  // 12 pixels tall (Bryan, 2026-09-29: "on mobile the map could be a bit
  // taller and more zoomed in while still leaving room for the labels").
  pp: { margin: 460, font: 42, gap: 42 * 1.45, leftTop: 54, rightTop: 54, line2: 42 * 1.1, circle: 9, circleStroke: 3.5, lead: 2.5 },
  // A project with a headline image on its SFMTA page shows it small under
  // its label, loaded from sfmta.com (Bryan, 2026-09-23: "take the headline
  // image from each project page and show it in a tiny image just below the
  // label"; he chose loading it from SFMTA over copying it in). A crowded
  // column drops the images of its smallest projects first, then tightens.
  img: { w: 52, h: 33 }, bottom: 14, offset: 18,
};

/**
 * The map, with the year's figures beside it and the controls over it. The
 * page script (MAP_SCRIPT) draws the data below on a MapLibre map: every
 * element that appears in a year carries its year, and the script sets the
 * year and restyles the layers. The page opens on the first year.
 */
export function historyMap() {
  const net = D(segments.segments.map((s) => s.pts));
  // One line group per first year, and per last year for a block that stopped
  // being all-ages, which leaves the map the year after (closed).
  const byYear = new Map();
  for (const f of allAges.features) {
    const k = `${f.properties.first}|${f.properties.until || ""}`;
    if (!byYear.has(k)) byYear.set(k, []);
    byYear.get(k).push(f.geometry.coordinates);
  }
  const lines = [...byYear].map(([k, ds]) => {
    const [y, u] = k.split("|");
    return { k: "aa", y: +y, ...(u ? { closed: +u + 1 } : {}), g: D(ds) };
  });
  const rm = removalLayers();
  // Planned work extends the slider past the last built year, drawn dashed
  // (Bryan, 2026-09-24: "Can we include planned projects for 2027 and
  // beyond? As much as MTA has available?"). Each project sits in the year
  // its SFMTA page gives for finishing, as on the yearly bar chart, so work
  // due this year shows dashed beside this year's built work.
  const planYear = (p) => p.year;
  const planKey = (p) => `plan:${p.node}:${p.year}`;
  const planYears = [...new Set(planned.projects.map(planYear))].sort((a, b) => a - b);
  const planLines = planYears.map((y) => ({ k: "planned", y, g: D(planned.projects.filter((p) => planYear(p) === y).flatMap((p) => p.blocks.map((b) => b.pts))) }));

  // Census blocks as dots, one group per first year in reach, years out of
  // reach and size step. Dot area is proportional to the block's 2020
  // population (Bryan, 2026-09-23: "Dot size should be relative to the
  // number of people"), so the diameter goes with its square root, in whole
  // drawing units from 2 up to 20 (the 99th-percentile block, 845 people, is 19).
  const size = (pop) => Math.max(2, Math.min(20, Math.round(0.66 * Math.sqrt(pop))));
  const col = Object.fromEntries(reach.blocks.columns.map((c, i) => [c, i]));
  // A block lit in its first year goes grey in any later year it is out of
  // reach (`off`), as when the only line that reached it was a pandemic Slow
  // Street SFMTA dropped, and lights again if a line comes back (Bryan,
  // 2026-09-29: "Are you sure you're updating connected residents to account
  // for the slow streets?"), so the lit dots add up to the year's residents
  // figure. Only the plan's distance is drawn: no page carries a distance
  // control.
  const groups = {};
  for (const row of reach.blocks.rows) {
    const k = `${row[col.reach]}|${(row[col.off] || []).join(" ")}|${size(row[col.pop2020])}`;
    (groups[k] ??= []).push([row[col.lon], row[col.lat]]);
  }
  const blocks = Object.entries(groups).map(([k, pts]) => {
    const [y, off, s] = k.split("|");
    return { y: +y, off: off ? ` ${off} ` : "", s: +s, d: encodePoints(pts) };
  });

  // The labels, per year and per set (wide, phone). Every project that added
  // at least LABEL_MIN miles in the year, at the mile-weighted midpoint of
  // the blocks it added; 12 in the busiest year (2020). A name longer than
  // one line of the margin (about LABEL_CHARS characters at the label size)
  // goes onto two lines split at the space that balances them, and is never
  // cut.
  const LABEL_MIN = 0.2, LABEL_CHARS = 32, PHONE_CHARS = 22;
  // A bikeway no SFMTA project record covers is named from its street, in a
  // quieter style and with no card, when the year's run on that street is at
  // least RUN_MIN miles (Bryan, 2026-09-23: "a number of major projects have
  // no label. Please reconcile"): the Bay Trail in 2018, Anza Street in 2021.
  const RUN_MIN = 0.5;
  // The name less a trailing "Project", "Improvements" and the like.
  const shortName = (n) => n.replace(/\s+(Safety |Quick-Build |Bikeway |Bicycle and Pedestrian Safety )?Projects?$/i, "").replace(/\s+Project$/i, "").replace(/\s+(Traffic Calming|Quick-Build|Improvements?|Streetscape)$/i, "");
  const wrap = (t, chars) => {
    if (t.length <= chars) return [t];
    let best = null;
    for (let i = t.indexOf(" "); i > 0; i = t.indexOf(" ", i + 1)) {
      const a = t.slice(0, i), b = t.slice(i + 1), w = Math.max(a.length, b.length);
      if (!best || w < best.w) best = { a, b, w };
    }
    return best ? [best.a, best.b] : [t];
  };
  const imageOf = Object.fromEntries(projects.projects.filter((p) => p.thumb).map((p) => [p.node, p.thumb]));
  const r5 = (v) => Math.round(v * 1e5) / 1e5;
  const candidates = (yr, { chars, images, twoLine }) => {
    // A removal names what went, not the street (Bryan, 2026-09-29:
    // "REMOVED: ??? Slow Street so it's clear we're not removing the
    // street"). Phone labels are too short for that on one line, so there
    // "REMOVED:" sits above the name.
    const removalName = (street, what) => twoLine
      ? { name: "REMOVED:", line2: shortName(`${street.replace(/ (St|Ave|Blvd|Way)$/, "")} ${what.replace("Slow Street", "Slow St")}`) }
      : { name: `REMOVED: ${shortName(`${street} ${what}`)}` };
    const cands = [];
    for (const pr of projects.projects) for (const b of pr.by_year || []) if (b.year === yr && b.miles >= LABEL_MIN) cands.push({ ...b, name: shortName(pr.name), node: pr.node });
    for (const r of projects.unnamed_runs || []) if (r.year === yr && r.miles >= RUN_MIN) cands.push({ ...r, name: shortName(r.name), node: null });
    for (const p of planned.projects) if (planYear(p) === yr) {
      const pts = p.blocks.flatMap((b) => b.pts), mid = pts[Math.floor(pts.length / 2)];
      cands.push({ miles: p.blocks.length, lon: mid[0], lat: mid[1], name: shortName(p.name), node: planKey(p), page: p.page });
    }
    for (const g of removedBikeways()) if (g.year === yr) {
      const mid = g.blocks[Math.floor(g.blocks.length / 2)].pts[0];
      cands.push({ miles: g.miles, lon: mid[0], lat: mid[1], ...removalName(`${g.name}`, g.facility), node: g.id, removal: true });
    }
    // A dropped pandemic Slow Street is labelled in the year it went in, as
    // any project is (Bryan, 2026-09-29: "How come the pandemic slow streets
    // aren't labelled and don't have photos?"). SFMTA published no project
    // page for them, so they carry no photo.
    for (const c of removedSlowStreets()) if (c.installed === yr) {
      const pts = c.blocks.filter((b) => b.status !== "kept").flatMap((b) => b.pts), mid = pts[Math.floor(pts.length / 2)];
      // Noe Street's kept stretch already has its project's label.
      const street = c.name.split(" ")[0].toLowerCase();
      if (mid && !cands.some((o) => o.name.toLowerCase().startsWith(`${street} `) && /slow/i.test(o.name))) cands.push({ miles: c.removedMiles + c.replacedMiles + (c.readoptedMiles || 0), lon: mid[0], lat: mid[1], name: shortName(`${c.name} Slow Street`), node: c.id });
    }
    if (removed) for (const c of removedSlowStreets()) if (removed.dropped_year === yr) {
      const gone = c.blocks.filter((b) => b.status === "removed"), pts = gone.flatMap((b) => b.pts), mid = pts[Math.floor(pts.length / 2)];
      if (gone.length) cands.push({ miles: c.removedMiles, lon: mid[0], lat: mid[1], ...removalName(c.name, "Slow Street"), node: c.id, removal: true });
    }
    // Two corridors on one street (20th Street, Mariposa Street) share one
    // label, the longer one's.
    const named = new Set();
    return cands.sort((a, b) => b.miles - a.miles)
      .filter((b) => !b.node || !b.node.startsWith("ss:") || (named.has(b.name) ? false : named.add(b.name)))
      .map((b) => ({
        ...(b.line2 ? { n: b.name, l2: b.line2 } : ((w) => ({ n: w[0], ...(w[1] ? { l2: w[1] } : {}) }))(wrap(b.name, chars))), c: [r5(b.lon), r5(b.lat)], mi: Math.round(b.miles * 1000) / 1000,
        ...(b.node ? { id: b.node } : {}), ...(b.page ? { pl: 1 } : {}), ...(b.removal ? { rm: 1 } : {}),
        ...(images && imageOf[b.node] ? { img: imageOf[b.node] } : {}),
      }));
  };
  const allYears = [...years, ...planYears];
  const labels = {
    pw: Object.fromEntries(allYears.map((yr) => [yr, candidates(yr, { chars: LABEL_CHARS, images: true })])),
    pp: Object.fromEntries(allYears.map((yr) => [yr, candidates(yr, { chars: PHONE_CHARS, images: false, twoLine: true })])),
  };

  // One hit area per attributed project and year, over the blocks it added,
  // so a click on the map (or on a label) opens the project's card (Bryan,
  // 2026-09-23: "let people click on the map and get a project outline (type
  // of infra, miles, photo, when it happened, 2-3 sentence description)"), and
  // a block is clickable only from the year it is drawn (Bryan, 2026-09-29:
  // "There are bugs with what is clickable or not"). Planned projects get
  // their own, keyed by node and year since one SFMTA page (Folsom-Howard)
  // plans two streets.
  const byKey = new Map(allAges.features.map((f) => [f.properties.key, f]));
  const FACILITY = { "1": "off-street path", "4": "separated lane", S: "Slow Street", "2c": "painted lane on a calm street", "2b": "painted lane", "3c": "signed route on a calm street", "3b": "signed route" };
  const hits = projects.projects.flatMap((pr) => {
    const byFirst = new Map();
    for (const f of (pr.blocks || []).map((k) => byKey.get(k)).filter(Boolean)) {
      const y = f.properties.first;
      (byFirst.get(y) || byFirst.set(y, []).get(y)).push(f.geometry.coordinates);
    }
    return [...byFirst].map(([y, list]) => ({ proj: pr.node, from: y, g: D(list) }));
  }).concat(planned.projects.filter((p) => p.blocks.length).map((p) => ({ proj: planKey(p), from: planYear(p), g: D(p.blocks.map((b) => b.pts)) })))
    .concat(rm.hits)
    .filter((h) => h.g.n.length);
  const facilityLines = (m) => Object.entries(m || {}).sort((a, b) => b[1] - a[1]).map(([c, v]) => `${mi(v)} mi ${FACILITY[c] || c}`);
  const cards = Object.fromEntries(projects.projects.map((pr) => [pr.node, {
    name: pr.name, page: pr.page, phase: pr.phase, years: pr.years, datedBy: pr.dated_by, miles: mi(pr.miles),
    facilities: Object.entries(pr.facilities || {}).sort((a, b) => b[1] - a[1]).map(([c, m]) => `${mi(m)} mi ${FACILITY[c] || c}`),
    streets: (pr.streets || []).map((st) => st.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/(\d)(St|Nd|Rd|Th)\b/g, (_, d, o) => d + o.toLowerCase())), residents: n(pr.residents), schools: pr.schools || [], libraries: pr.libraries || [],
    teaser: pr.teaser || null, standIn: !!pr.stand_in, image: pr.image || null,
    summary: SUMMARIES[pr.node] || null,
    added: facilityLines(pr.added), upgraded: facilityLines(pr.upgraded),
  }]).concat(planned.projects.map((p) => [planKey(p), {
    name: p.name, page: p.page, planned: planYear(p), quote: p.quote, conflict: p.conflict || null,
    streets: [...new Set(p.blocks.map((b) => b.street))].map((st) => st.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase())),
    blocks: p.blocks.length, miles: mi(p.blocks.reduce((a, b) => a + lineMiles(b.pts), 0)),
    facility: FACILITY[{ "CLASS I": "1", "CLASS IV": "4", "CLASS II": "2b", "CLASS III": "3b" }[p.class]] || p.class,
    directions: p.directions,
  }])).concat(rm.cards));

  const figures = inlineJson({
    default: DEFAULT_REACH, short: shortOf, cards, reach: shortOf[DEFAULT_REACH], firstYear: years[0],
    // Years past the last built one read the planned network's reach, so the
    // figure carries on as the map does (Bryan, 2026-09-28: "it's weird that
    // the percent of residents within a quarter mile disappears").
    rows: [...rows, ...(history.planned?.rows || []).filter((r) => r.year > rows[rows.length - 1].year)].map((r) => ({
      year: r.year, miles: mi(r.all_ages_miles),
      by: Object.fromEntries(THRESHOLDS.map((t) => { const b = at(r, t.id); return [t.id, { residents: pct(b.resident_share), schools: `${b.schools_within_reach} of ${r.schools_total}`, libraries: `${b.libraries_within_reach} of ${r.libraries_total}` }]; })),
    })),
  });
  const geo = inlineJson({
    bounds: BOUNDS, units: MW, net, lines: [...lines, ...rm.lines, ...planLines].filter((l) => l.g.n.length), blocks, hits, labels, label: LABEL,
    dot150: size(150),
  });
  const y0 = years[0], y1 = years[years.length - 1];
  const lastBy = at(last, DEFAULT_REACH);
  const yEnd = planYears.length ? planYears[planYears.length - 1] : y1;
  return `<figure class="hmap hero" id="year-map" data-year="${y1}" data-first="${y0}" data-last="${yEnd}" data-built="${y1}">
  <div class="hmap-stage">
  <div class="hmap-top">
    <h2 class="hmap-title">&ldquo;All Ages &amp; Abilities&rdquo; Bike Network</h2>
    <div class="hmap-controls">
      <button type="button" class="hmap-play" data-play aria-label="Play">Play</button>
      <button type="button" class="hmap-step" data-step="-1" aria-label="Previous year">&#8249;</button>
      <input type="range" min="${y0}" max="${yEnd}" step="1" value="${y1}" data-scrub aria-label="Year">
      <button type="button" class="hmap-step" data-step="1" aria-label="Next year">&#8250;</button>
      <span class="hmap-when" aria-live="polite">Planned</span>
    </div>
    <p class="hmap-hint">Tap or click a bikeway for details</p>
  </div>
  <div class="hmap-panel">
    <p class="hmap-metric"><b data-res-out>${pct(lastBy.resident_share)}%</b><span>of residents connected to the network</span></p>
  </div>
  <div class="hmap-canvas">
    <output class="hmap-yr" data-year-out>${y1}</output>
    <div class="glmap hmap-gl" role="img" aria-label="San Francisco's all-ages bikeways by the year each was built, with the census blocks within a quarter mile of one"></div>
    <svg class="hmap-labels" aria-hidden="true" data-labels></svg>
  </div>
  <aside class="proj-card" data-proj-card hidden aria-live="polite">
    <button type="button" class="proj-close" data-proj-close aria-label="Close">×</button>
    <h3 class="proj-name"><a data-proj-link href="#">Project</a></h3>
    <figure class="proj-photo" data-proj-photo hidden><img alt="" referrerpolicy="no-referrer"></figure>
    <p class="proj-when" data-proj-when></p>
    <p class="proj-summary" data-proj-summary hidden></p>
    <table class="proj-table"><tbody data-proj-rows></tbody></table>
    <p class="proj-more"><a data-proj-more href="#">Details and photos on SFMTA's project page</a></p>
  </aside>
  </div>
  <div class="map-keys">
    <div class="map-key-row"><b class="map-key-h">Bikeways</b><ul class="map-key">
      <li><i class="key aa"></i>Built, meets the plan's all-ages test</li>
      <li><i class="key aa planned"></i>Planned by SFMTA</li>
    </ul></div>
    <div class="map-key-row"><b class="map-key-h">Residents</b><ul class="map-key">
      <li><i class="key blk"></i>Connected</li>
      <li><i class="key blk off"></i>Not connected</li>
      <li><i class="key blk" data-dot100></i>Dot area is population (this size: 150, a typical block)</li>
    </ul></div>
  </div>
  <ul class="credit" data-for="Project photos on the map"><li>SFMTA, from each <a href="https://www.sfmta.com/projects">SFMTA project page</a></li></ul>
  <script type="application/json" data-hmap-figures>${figures}</script>
  <script type="application/json" data-hmap-geo>${geo}</script>
</figure>`;
}

// The hero map's own styles, over the .hmap rules in layout.mjs: the map's
// box and the label layer laid over it.
export const HMAP_CSS = `<style>
.hmap .hmap-canvas { position: relative; }
/* The year sits on the map's top-left corner, where the eye is while the slider moves, and a
   thumb on the slider doesn't cover it (Bryan, 2026-10-09). */
.hmap .hmap-yr { position: absolute; top: 8px; right: 8px; z-index: 2; padding: 2px 10px; border-radius: 6px; background: rgba(255,255,255,0.9); color: var(--ink); font-size: 28px; font-weight: 700; line-height: 1.2; font-variant-numeric: tabular-nums; pointer-events: none; }
@media (max-width: 700px) { .hmap .hmap-yr { font-size: 22px; right: auto; left: 8px; } }
/* The city is as tall as it is wide, so the map's height sets its width: as
   tall as the fold allows (Bryan, 2026-09-22). */
.hmap.hero .hmap-gl { width: 100%; aspect-ratio: 1000 / 1044; max-height: max(240px, calc(100dvh - 200px)); }
/* Phones: taller than the city needs, so the label columns beside it have
   room for every name in full (Bryan, 2026-09-30). */
@media (max-width: 700px) { .hmap.hero .hmap-gl { aspect-ratio: 1920 / 1560; } }
.hmap.hero svg.hmap-labels { position: absolute; inset: 0; width: 100%; height: 100%; max-height: none; aspect-ratio: auto; margin: 0; background: none; border-radius: 0; pointer-events: none; overflow: visible; z-index: 1; }
.hmap.hero svg.hmap-labels .plabel { pointer-events: auto; }
.hmap.hero svg.hmap-labels .plabel.unnamed { pointer-events: none; }
.hmap.hero svg.hmap-labels .plabel text { fill: var(--muted); font-weight: 400; paint-order: stroke; stroke: rgba(255,255,255,0.85); stroke-width: 3px; stroke-linejoin: round; }
.hmap.hero svg.hmap-labels .plabel.pp text { font-weight: 500; stroke-width: 8px; }
.hmap.hero svg.hmap-labels .plabel.planned text { fill: var(--seq-3); }
.hmap.hero svg.hmap-labels .plabel.removal text { font-style: italic; }
.hmap.hero svg.hmap-labels .plabel line { stroke: var(--muted); opacity: 0.4; }
.hmap.hero svg.hmap-labels .plabel circle { stroke: var(--muted); }
.hmap.hero svg.hmap-labels .plabel.picked text { fill: var(--ink); }
.hmap .hmap-gl .maplibregl-ctrl-bottom-right { z-index: 3; }
</style>`;

export const MAP_SCRIPT = `<script>
(function () {
  var box = document.querySelector(".hmap");
  if (!box || !window.sfMap) return;
  var first = +box.dataset.first, last = +box.dataset.last, built = +box.dataset.built;
  var figures = JSON.parse(box.querySelector("[data-hmap-figures]").textContent);
  var G = JSON.parse(box.querySelector("[data-hmap-geo]").textContent);
  var out = box.querySelector("[data-year-out]");
  var res = box.querySelector("[data-res-out]");
  var scrub = box.querySelector("[data-scrub]");
  var play = box.querySelector("[data-play]");
  var steps = box.querySelectorAll("[data-step]");
  var gl = box.querySelector(".hmap-gl"), overlay = box.querySelector("[data-labels]");
  // Phones get wider margins and their own, larger labels.
  var narrow = window.matchMedia("(max-width: 700px)");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var NS = "http://www.w3.org/2000/svg";
  // The city fills the map's height, with the margins either side of it
  // that hold the labels: LABEL.margin drawing units each, of a box
  // units + 2 margins wide.
  function set() { return narrow.matches ? "pp" : "pw"; }
  function padding() {
    var w = gl.clientWidth, m = G.label[set()].margin, f = m / (G.units + 2 * m);
    return { left: Math.round(w * f), right: Math.round(w * f), top: 0, bottom: 0 };
  }
  var map = sfMap.create(gl, { bounds: G.bounds, padding: padding, controls: narrow.matches ? "top-right" : "bottom-right" });
  if (!map) return;
  box.dataset.live = "1";
  var year = +box.dataset.year, picked = null, hovered = null, z0 = null, s0 = null, ready = false;

  // ---- Data, as GeoJSON ----
  var hitRuns = {};
  var lineFeats = [], hitFeats = [], blockFeats = [];
  G.lines.forEach(function (l) {
    sfMap.decode(l.g).forEach(function (r) {
      if (r.length > 1) lineFeats.push({ type: "Feature", properties: { k: l.k, y: l.y || 0, open: l.open || 0, closed: l.closed || 0 }, geometry: { type: "LineString", coordinates: r } });
    });
  });
  G.hits.forEach(function (h, i) {
    var runs = sfMap.decode(h.g).filter(function (r) { return r.length > 1; });
    (hitRuns[h.proj] = hitRuns[h.proj] || []).push({ from: h.from, until: h.until || 0, runs: runs });
    runs.forEach(function (r) { hitFeats.push({ type: "Feature", properties: { proj: h.proj, from: h.from, until: h.until || 0 }, geometry: { type: "LineString", coordinates: r } }); });
  });
  G.blocks.forEach(function (b) {
    sfMap.points(b.d).forEach(function (c) { blockFeats.push({ type: "Feature", properties: { y: b.y, off: b.off, s: b.s }, geometry: { type: "Point", coordinates: c } }); });
  });

  // ---- Styling by year ----
  // The drawing units of the SVG this map replaced, at the opening view:
  // widths and dot sizes grow as the fourth root of the zoom factor, so the
  // map's detail spreads apart rather than swelling.
  function U(v) { return sfMap.grow(v, z0, s0); }
  function inYear(openKey, closedKey) {
    return ["all", ["any", ["==", ["get", openKey], 0], ["<=", ["get", openKey], year]], ["any", ["==", ["get", closedKey], 0], [">", ["get", closedKey], year]]];
  }
  function style() {
    if (!ready) return;
    var yy = Math.min(year, built);
    var on = ["all", [">", ["get", "y"], 0], ["<=", ["get", "y"], year]];
    // The first year is the baseline, not that year's new work, so nothing
    // is emphasised on it (Bryan, 2026-09-23: "Should not look all bolded
    // and nontransparent when I go to the first year").
    var now = ["all", on, year > first, ["==", ["get", "y"], year]];
    map.setFilter("aa", ["all", ["==", ["get", "k"], "aa"], inYear("open", "closed")]);
    map.setFilter("planned", ["all", ["==", ["get", "k"], "planned"], inYear("open", "closed")]);
    map.setFilter("rm", ["all", ["==", ["get", "k"], "rm"], inYear("open", "closed")]);
    ["aa", "planned"].forEach(function (id) {
      map.setPaintProperty(id, "line-opacity", ["case", now, 1, on, 0.7, 0]);
      map.setPaintProperty(id, "line-width", U(["case", now, id === "aa" ? 9 : 6, 5]));
    });
    map.setPaintProperty("net", "line-width", U(2));
    map.setPaintProperty("rm", "line-width", U(3));
    // A dot is dark in the years after its first that it is out of reach
    // (off, a space-separated list), and emphasised again the year it
    // comes back. Planned years keep the last built year's state, since
    // their reach is not drawn per point.
    var dark = ["in", " " + yy + " ", ["get", "off"]];
    var bOn = ["all", [">", ["get", "y"], 0], ["<=", ["get", "y"], year], ["!", dark]];
    var bNow = ["all", bOn, year > first, ["any", ["==", ["get", "y"], year], yy === year ? ["in", " " + (year - 1) + " ", ["get", "off"]] : false]];
    // A block not yet within reach is drawn at its own size in grey, like one
    // never reached, so a dot changes colour and never size (Bryan, 2026-09-29).
    map.setPaintProperty("blk", "circle-color", ["case", bOn, sfMap.token("--seq-2"), sfMap.token("--muted")]);
    map.setPaintProperty("blk", "circle-opacity", ["case", bNow, 0.95, bOn, 0.5, 0.12]);
    map.setPaintProperty("blk", "circle-radius", U(["/", ["get", "s"], 2]));
    // A project's click area exists only once its bikeway is drawn, so the
    // cursor never finds a project where the map shows nothing; a removed
    // street's lasts only while it is drawn.
    var live = ["all", ["<=", ["get", "from"], year], ["any", ["==", ["get", "until"], 0], [">", ["get", "until"], year]]];
    map.setFilter("hits", live);
    map.setPaintProperty("hits", "line-width", U(12));
    map.setFilter("hit-hover", ["all", live, ["==", ["get", "proj"], hovered || ""]]);
    map.setFilter("hit-picked", ["all", live, ["==", ["get", "proj"], picked || ""]]);
    map.setPaintProperty("hit-hover", "line-width", U(9));
    map.setPaintProperty("hit-picked", "line-width", U(9));
  }
  function measure() {
    z0 = map.getZoom();
    s0 = sfMap.unitPx(map, G.bounds, G.units);
  }
  map.on("load", function () {
    measure();
    var before = sfMap.under(map), round = { "line-cap": "round", "line-join": "round" };
    map.addSource("net", { type: "geojson", data: sfMap.collection(sfMap.features(sfMap.decode(G.net)).filter(function (f) { return f.geometry.type === "LineString"; })) });
    map.addSource("blk", { type: "geojson", data: sfMap.collection(blockFeats) });
    map.addSource("lines", { type: "geojson", data: sfMap.collection(lineFeats) });
    map.addSource("hits", { type: "geojson", data: sfMap.collection(hitFeats) });
    map.addLayer({ id: "net", type: "line", source: "net", layout: round, paint: { "line-color": sfMap.token("--rule") } }, before);
    map.addLayer({ id: "blk", type: "circle", source: "blk", paint: {} }, before);
    map.addLayer({ id: "rm", type: "line", source: "lines", layout: round, paint: { "line-color": sfMap.token("--muted"), "line-opacity": 0.9, "line-dasharray": [0.34, 1.67] } }, before);
    map.addLayer({ id: "aa", type: "line", source: "lines", layout: round, paint: { "line-color": sfMap.token("--seq-3") } }, before);
    map.addLayer({ id: "planned", type: "line", source: "lines", layout: { "line-cap": "butt", "line-join": "round" }, paint: { "line-color": sfMap.token("--seq-3"), "line-dasharray": [1.2, 1] } }, before);
    map.addLayer({ id: "hits", type: "line", source: "hits", layout: round, paint: { "line-color": sfMap.token("--seq-1"), "line-opacity": 0 } });
    map.addLayer({ id: "hit-hover", type: "line", source: "hits", layout: round, paint: { "line-color": sfMap.token("--seq-1"), "line-opacity": 0.35 } });
    map.addLayer({ id: "hit-picked", type: "line", source: "hits", layout: round, paint: { "line-color": sfMap.token("--seq-1"), "line-opacity": 0.55 } });
    ready = true;
    style();
    labels();
    sizeKey();
  });

  // ---- The labels beside the city ----
  // Laid out on screen in drawing units times the pixels per unit, as the
  // SVG map placed them: two columns either side of the city, each label
  // with a leader to its project's dot, stacked so none overlaps.
  function esc(t) { return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
  function labels() {
    if (!ready) return;
    var zoomed = map.getZoom() > z0 + 0.05;
    box.classList.toggle("zoomed", zoomed);
    if (zoomed) { overlay.innerHTML = ""; return; }
    var S = set(), L = G.label[S], s = sfMap.unitPx(map, G.bounds, G.units);
    var nw = map.project([G.bounds[0][0], G.bounds[1][1]]), se = map.project([G.bounds[1][0], G.bounds[0][1]]);
    // The lowest label stays clear of the attribution and logo along the map's foot.
    var attrib = gl.querySelector(".maplibregl-ctrl-attrib"), logo = gl.querySelector(".sf-glogo");
    var foot = Math.max(attrib ? attrib.offsetHeight + 4 : 22, logo ? logo.offsetHeight + 15 : 0);
    // On a phone the map is taller than the city, and the columns run its full height.
    var tall = S === "pp", H = gl.clientHeight;
    var midX = (nw.x + se.x) / 2, bottom = tall ? H - foot : se.y - Math.max(G.label.bottom * s, foot), gap = L.gap * s, line2 = L.line2 * s, imgW = G.label.img.w * s, imgH = G.label.img.h * s;
    var picks = (G.labels[S][year] || []).map(function (b) {
      var p = map.project(b.c);
      return { b: b, px: p.x, py: p.y, side: p.x < midX ? "l" : "r", img: S === "pw" ? b.img || null : null };
    });
    ["l", "r"].forEach(function (side) {
      var col = picks.filter(function (b) { return b.side === side; }).sort(function (a, b) { return a.py - b.py; });
      var top = tall ? 8 : nw.y + (side === "l" ? L.leftTop : L.rightTop) * s;
      // On a phone the controls sit top right, so that column starts below them.
      var ctl = side === "r" && gl.querySelector(".maplibregl-ctrl-top-right");
      if (ctl && ctl.offsetHeight) top = Math.max(top, ctl.offsetTop + ctl.offsetHeight + 4);
      var room = bottom - top;
      var extra = function (b) { return (b.img ? imgH + 4 * s : 0) + (b.b.l2 ? line2 : 0); };
      var need = function () { return col.reduce(function (a, b) { return a + gap + extra(b); }, 0) - gap; };
      col.slice().sort(function (a, c) { return a.b.mi - c.b.mi; }).forEach(function (b) { if (need() > room) b.img = null; });
      // Tighter spacing only when a side has more labels than fit.
      var k = need() > room ? room / need() : 1;
      var h = function (b) { return (gap + extra(b)) * k; };
      // The type shrinks with the spacing, so two lines never overlap.
      col.forEach(function (b) { b.k = k; });
      var lastY = top, prev = null;
      col.forEach(function (b) { b.ly = Math.max(b.py, prev ? lastY + h(prev) : top); lastY = b.ly; prev = b; });
      // Anything pushed past the bottom moves back up, and pushes its
      // neighbours up with it.
      var limit = bottom - (col.length ? extra(col[col.length - 1]) * k : 0);
      for (var i = col.length - 1; i >= 0; i--) { col[i].ly = Math.min(col[i].ly, limit); if (i) limit = col[i].ly - h(col[i - 1]); }
    });
    var html = "";
    picks.forEach(function (p) {
      var k = p.k || 1, fs = L.font * s * k, l2 = line2 * k;
      var b = p.b, left = p.side === "l", tx = left ? nw.x - G.label.offset * s : se.x + G.label.offset * s;
      var cls = b.id ? "plabel " + S + " now" + (b.pl ? " planned" : "") + (b.rm ? " removal" : "") + (picked === b.id ? " picked" : "") : "plabel " + S + " now unnamed";
      html += '<g class="' + cls + '"' + (b.id ? ' data-proj="' + esc(b.id) + '"' : "") + ">" +
        '<line x1="' + p.px.toFixed(1) + '" y1="' + p.py.toFixed(1) + '" x2="' + (tx + (left ? 6 : -6) * s).toFixed(1) + '" y2="' + p.ly.toFixed(1) + '" style="stroke-width:' + (L.lead * s).toFixed(2) + 'px"/>' +
        '<circle cx="' + p.px.toFixed(1) + '" cy="' + p.py.toFixed(1) + '" style="r:' + (L.circle * s).toFixed(2) + "px;stroke-width:" + (L.circleStroke * s).toFixed(2) + 'px"/>' +
        '<text x="' + tx.toFixed(1) + '" y="' + (p.ly + fs * 0.3).toFixed(1) + '" text-anchor="' + (left ? "end" : "start") + '" style="font-size:' + fs.toFixed(2) + 'px">' + esc(b.n) +
        (b.l2 ? '<tspan x="' + tx.toFixed(1) + '" dy="' + l2.toFixed(1) + '">' + esc(b.l2) + "</tspan>" : "") + "</text>" +
        (p.img ? '<image href="' + esc(p.img) + '" x="' + (left ? tx - imgW : tx).toFixed(1) + '" y="' + (p.ly + fs * 0.7 + (b.l2 ? l2 : 0)).toFixed(1) + '" width="' + imgW.toFixed(1) + '" height="' + imgH.toFixed(1) + '" preserveAspectRatio="xMidYMid slice"/>' : "") +
        "</g>";
    });
    overlay.innerHTML = html;
    // The next year's photos are fetched now, so Play finds them ready.
    if (S === "pw") (G.labels.pw[year + 1] || []).forEach(function (b) { if (b.img) { var im = new Image(); im.referrerPolicy = "no-referrer"; im.src = b.img; } });
  }

  // The key's dot is drawn at the map's current scale, so it matches a
  // block of that many people on screen (Bryan, 2026-09-24); it shows 150,
  // near the median block (145; mean 170). Zoomed in it grows as the dots do.
  var dot100 = box.querySelector("[data-dot100]");
  function sizeKey() {
    if (!ready || !dot100) return;
    var px = G.dot150 * s0 * sfMap.growAt(map.getZoom(), z0);
    dot100.style.width = dot100.style.height = Math.max(2, px).toFixed(1) + "px";
  }
  var rz = null;
  map.on("move", function () { labels(); sizeKey(); if (!card.hidden) place(); });
  map.on("sfbasemap", function () { labels(); }); // the logo and credit line arrive with the basemap
  map.on("resize", function () {
    clearTimeout(rz);
    // A reader who has zoomed in keeps the view; otherwise the city is fitted
    // to the new box again, as the SVG scaled with its box.
    rz = setTimeout(function () { if (!ready || map.getZoom() > z0 + 0.05) return; map.fitBounds(G.bounds, { padding: padding(), duration: 0 }); measure(); style(); labels(); sizeKey(); }, 100);
  });
  if (narrow.addEventListener) narrow.addEventListener("change", function () {
    if (!ready) return;
    map.fitBounds(G.bounds, { padding: padding(), duration: 0 }); measure(); style(); labels(); sizeKey();
  });

  // The distance chosen with the control above; the plan's when none is.
  function sel() { return document.documentElement.dataset.reach || figures.default; }
  var timer = null;
  function show(y) {
    year = y;
    box.dataset.year = year;
    // "Planned" shows in a slot beside the slider that is always reserved,
    // so the title and Play button keep their place (Bryan, 2026-09-28: the
    // "(planned)" after the title "changes the layout of the title and play
    // button").
    out.textContent = year;
    box.classList.toggle("future", year > built);
    scrub.value = year;
    steps[0].disabled = year <= first; steps[1].disabled = year >= last;
    style();
    labels();
    var f = figures.rows.filter(function (r) { return r.year === year; })[0];
    if (f) { res.textContent = f.by[sel()].residents + "%"; }
    var p = new URLSearchParams(location.search);
    if (year === first) p.delete("year"); else p.set("year", year);
    var q = p.toString() ? "?" + p.toString() : "";
    history.replaceState(null, "", location.pathname + q + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: q + location.hash }));
  }
  function stop() { clearInterval(timer); timer = null; play.textContent = "Play"; play.setAttribute("aria-label", "Play"); }
  function start() {
    var y = year;
    if (y >= last) y = first - 1;
    play.textContent = "Pause"; play.setAttribute("aria-label", "Pause");
    show(Math.max(first, y + 1));
    timer = setInterval(function () {
      var n = year + 1;
      if (n > last) { stop(); return; }
      show(n);
    }, 2000); // Bryan, 2026-09-29: "Make the play speed 2s, so it feels a little faster"
  }
  play.addEventListener("click", function () { timer ? stop() : start(); });
  // Arrows step one year at a time, for a reader who wants to set the pace
  // (Bryan, 2026-09-29: "Clicking for each year, like a photo slideshow
  // kind of thing with an arrow").
  for (var k = 0; k < steps.length; k++) steps[k].addEventListener("click", function () {
    stop();
    show(Math.max(first, Math.min(last, year + +this.dataset.step)));
  });

  // A click on a project's blocks or its label opens its card as a popover
  // beside the click (Bryan, 2026-09-23: "Clicking should open a popover
  // instead of a panel below, which is hard to see").
  var card = box.querySelector("[data-proj-card]"), stage = box.querySelector(".hmap-stage");
  // The screen box of the picked project's lines on show, relative to the stage.
  function pickedBox() {
    if (!picked || !hitRuns[picked]) return null;
    var runs = [];
    hitRuns[picked].forEach(function (h) { if (h.from <= year && (!h.until || h.until > year)) runs = runs.concat(h.runs); });
    if (!runs.length) return null;
    var b = sfMap.screenBox(map, runs), sr = stage.getBoundingClientRect(), gr = gl.getBoundingClientRect();
    return { l: b.l + gr.left - sr.left, r: b.r + gr.left - sr.left, t: b.t + gr.top - sr.top, b: b.b + gr.top - sr.top };
  }
  // Bryan, 2026-09-24: "they cover the map where you're looking. Can you
  // lay them out so that they don't cover the place they're talking about?"
  // The card goes on whichever side of the project's outline has the most
  // room, and slides along that side to stay inside the map. On a phone the
  // map is too small to hold a card beside anything, so the card sits in the
  // page under the map and scrolls into view.
  var lastClick = null;
  function place(e) {
    if (e) lastClick = e;
    if (narrow.matches) { card.style.left = card.style.top = ""; if (e) card.scrollIntoView({ block: "nearest", behavior: reduced ? "auto" : "smooth" }); return; }
    e = e || lastClick;
    var sr = stage.getBoundingClientRect(), W = sr.width, H = sr.height, gap = 12;
    var cw = card.offsetWidth, ch = card.offsetHeight;
    var pb = pickedBox();
    var bx = pb && (pb.r - pb.l || pb.b - pb.t) ? pb
      : { l: (e ? e.clientX - sr.left : W / 2), r: (e ? e.clientX - sr.left : W / 2), t: (e ? e.clientY - sr.top : H / 3), b: (e ? e.clientY - sr.top : H / 3) };
    var room = { right: W - bx.r - gap, left: bx.l - gap, below: H - bx.b - gap, above: bx.t - gap };
    var fits = { right: room.right >= cw, left: room.left >= cw, below: room.below >= ch, above: room.above >= ch };
    var side = ["right", "left", "below", "above"].filter(function (k) { return fits[k]; })[0]
      || ["right", "left", "below", "above"].sort(function (a, b) { return (room[b] / (b === "right" || b === "left" ? cw : ch)) - (room[a] / (a === "right" || a === "left" ? cw : ch)); })[0];
    var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(v, hi)); };
    var cy = (bx.t + bx.b) / 2, cx = (bx.l + bx.r) / 2, left, top;
    if (side === "right") { left = bx.r + gap; top = cy - ch / 2; }
    else if (side === "left") { left = bx.l - gap - cw; top = cy - ch / 2; }
    else if (side === "below") { top = bx.b + gap; left = cx - cw / 2; }
    else { top = bx.t - gap - ch; left = cx - cw / 2; }
    card.style.left = clamp(left, 8, Math.max(8, W - cw - 8)) + "px";
    card.style.top = clamp(top, 8, Math.max(8, H - ch - 8)) + "px";
  }
  function closeCard() {
    card.hidden = true;
    picked = null; style(); labels();
  }
  function rowsInto(rows) {
    var tb = card.querySelector("[data-proj-rows]"); tb.textContent = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr"), th = document.createElement("th"), td = document.createElement("td");
      th.scope = "row"; th.textContent = r[0];
      [].concat(r[1]).forEach(function (line, i) { if (i) td.appendChild(document.createElement("br")); td.appendChild(document.createTextNode(line)); });
      tr.appendChild(th); tr.appendChild(td); tb.appendChild(tr);
    });
  }
  function openCard(node, e) {
    var c = figures.cards[node]; if (!c) return;
    picked = node; style(); labels();
    var link = card.querySelector("[data-proj-link]"); link.textContent = c.name; link.href = c.page;
    var more = card.querySelector("[data-proj-more]"); more.href = c.page;
    more.textContent = c.more || (c.standIn ? "SFMTA's Slow Streets data" : "Details and photos on SFMTA's project page");
    card.querySelector("[data-proj-photo]").hidden = true;
    var sm = card.querySelector("[data-proj-summary]");
    if (c.planned) {
      // A planned project's card: the year SFMTA's page gives, in its words,
      // and the street miles drawn, with no reach figures, since those are
      // counted for built blocks only.
      card.querySelector("[data-proj-when]").textContent = "Planned for " + c.planned + ". SFMTA's page: \\u201c" + c.quote + "\\u201d";
      sm.hidden = !c.conflict; sm.textContent = c.conflict ? "Note: " + c.conflict + "." : "";
      rowsInto([
        ["Planned bikeway", c.miles + " mi " + c.facility + ", " + (c.directions === 1 ? "one direction" : "both directions")],
        ["Streets", c.streets.join(", ") + " (" + c.blocks + " block" + (c.blocks === 1 ? "" : "s") + ")"],
      ]);
    } else if (c.removed) {
      // A removed bikeway or Slow Street: when it went, in the record's
      // words, and how much.
      card.querySelector("[data-proj-when]").textContent = c.when;
      sm.hidden = !c.summary; sm.textContent = c.summary || "";
      rowsInto(c.rows);
    } else {
      // Bryan, 2026-09-24: "the first sentence is not necessary. Instead just
      // say Built in <year>"; then the what-and-why summary from SFMTA's page,
      // then the figures as a table. A project SFMTA still lists as under way
      // built these blocks in an early phase (Bryan, 2026-09-28, on
      // Folsom-Howard: its page dates near-term changes to 2018 and 2019 and
      // construction to 2024-2029).
      var span = c.years[0] === c.years[1] ? c.years[0] : c.years[0] + "\\u2013" + c.years[1];
      var going = { "Current": "still under way", "Implementation / Construction": "under construction", "Legislated": "approved and not yet finished" }[c.phase];
      // When the project page gives no date, the year is the bikeway layer's,
      // and the card says so rather than claiming the page's authority.
      card.querySelector("[data-proj-when]").textContent = c.datedBy === "layer"
        ? "SFMTA's bikeway data dates these blocks to " + span + "."
        : going
          ? "Early work built in " + span + ". SFMTA lists the project as " + going + "."
          : "Built in " + span;
      var say = c.summary || (c.teaser ? "SFMTA: \\u201c" + c.teaser + "\\u201d" : "");
      sm.hidden = !say; sm.textContent = say;
      var rows = [];
      if (c.added.length) rows.push(["Miles added", c.added]);
      if (c.upgraded.length) rows.push(["Miles upgraded", c.upgraded]);
      rows.push(["# residents connected", [c.residents]]);
      rows.push(["# schools connected", [c.schools.length ? c.schools.length + " (" + c.schools.join(", ") + ")" : "0"]]);
      if (c.libraries.length) rows.push(["# library branches connected", [c.libraries.length + " (" + c.libraries.join(", ") + ")"]]);
      rowsInto(rows);
      var ph = card.querySelector("[data-proj-photo]"), im = ph.querySelector("img");
      ph.hidden = !c.image; if (c.image) { im.onerror = function () { ph.hidden = true; }; im.src = c.image; im.alt = "SFMTA's photo for " + c.name; }
    }
    card.hidden = false;
    place(e);
  }
  // A tap on the map: the project under it, or nothing, which closes the card.
  map.on("click", function (e) {
    if (!ready) return;
    var hit = sfMap.near(map, e.point, ["hits"])[0];
    if (hit) { stop(); openCard(hit.properties.proj, e.originalEvent); }
    else if (!card.hidden) closeCard();
  });
  map.on("mousemove", function (e) {
    if (!ready) return;
    var hit = sfMap.near(map, e.point, ["hits"])[0], h = hit ? hit.properties.proj : null;
    map.getCanvas().style.cursor = h ? "pointer" : "";
    if (h !== hovered) { hovered = h; style(); }
  });
  map.getCanvas().addEventListener("mouseleave", function () { if (hovered) { hovered = null; style(); } });
  // A label, the card's close button, or a click elsewhere on the figure.
  box.addEventListener("click", function (e) {
    if (gl.contains(e.target)) return;
    var t = e.target.closest("[data-proj]");
    if (t) { stop(); openCard(t.dataset.proj, e); return; }
    if (e.target.closest("[data-proj-close]") || (!card.hidden && !e.target.closest("[data-proj-card]"))) closeCard();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !card.hidden) closeCard(); });
  scrub.addEventListener("input", function () { stop(); show(+scrub.value); });
  // The distance control re-lights the map for the year on show.
  window.addEventListener("sfworks:reach", function () { show(year); });

  var asked = +new URLSearchParams(location.search).get("year");
  // The page lands on the first year, so Play runs forward from the start
  // (Bryan, 2026-09-28: "start at the first year rather than 2029").
  show(asked >= first && asked <= last ? asked : first);
  // ?proj=<node> opens that project's card, so a card can be linked to.
  var askedProj = new URLSearchParams(location.search).get("proj");
  if (askedProj && figures.cards[askedProj]) map.once("idle", function () { openCard(askedProj); });
})();
</script>
<script>
(function () {
  // The distance control: html[data-reach] picks which .reach-var shows, the
  // choice goes in the URL (?reach=) so it can be shared and in localStorage
  // so it is remembered, and every [data-reach-word] reads as the distance.
  var pick = document.querySelector("[data-reach-pick]");
  if (!pick) return;
  var buttons = pick.querySelectorAll("[data-reach]");
  var short = ${JSON.stringify(shortOf)}, dflt = ${JSON.stringify(DEFAULT_REACH)};
  var words = document.querySelectorAll("[data-reach-word]");
  function apply(id, fromClick) {
    document.documentElement.dataset.reach = id;
    for (var i = 0; i < buttons.length; i++) buttons[i].setAttribute("aria-checked", buttons[i].dataset.reach === id);
    for (var j = 0; j < words.length; j++) words[j].textContent = short[id];
    if (fromClick) { try { localStorage.setItem("reach", id); } catch (e) {} }
    var p = new URLSearchParams(location.search);
    if (id === dflt) p.delete("reach"); else p.set("reach", id);
    var q = p.toString() ? "?" + p.toString() : "";
    history.replaceState(null, "", location.pathname + q + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: q + location.hash }));
    window.dispatchEvent(new CustomEvent("sfworks:reach", { detail: id }));
  }
  for (var k = 0; k < buttons.length; k++) {
    buttons[k].addEventListener("click", function (e) { apply(e.currentTarget.dataset.reach, true); });
  }
  // Keyboard: arrows move between the options, as a radio group does.
  pick.addEventListener("keydown", function (e) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    var cur = pick.querySelector('[aria-checked="true"]'), i = Array.prototype.indexOf.call(buttons, cur);
    var nxt = buttons[(i + (e.key === "ArrowRight" ? 1 : buttons.length - 1)) % buttons.length];
    nxt.focus(); apply(nxt.dataset.reach, true); e.preventDefault();
  });
  apply(document.documentElement.dataset.reach || dflt, false);
})();
</script>`;
