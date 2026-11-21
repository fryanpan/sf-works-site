// The definition explorer on the transportation overview.
//
// Bryan, 2026-09-23: "give me a tool that lets me play with what's 'good
// enough' and play with the three biggest levers: 1) choose different
// distance threshold, 2) exclude residents if they're on an island that
// doesn't connect them to <x> (let's say GGP), 3) choose what's acceptable
// bike infra for 'all ages and abilities' using photos. And then let the
// user also see where we're at today, Biking & Rolling Plan North Star."
//
// The whole model runs in the browser. The page carries every bikeway block
// in the latest year with its row miles split by facility code, every
// populated census block with the year's population, the K-12 schools and
// library branches, and the plan's North Star blocks that do not yet carry
// what the plan draws. When the reader changes a control the script picks the
// blocks whose codes are ticked, looks up which points lie within the chosen
// walking distance, and redraws the map and the figures. The walking
// distances are precomputed per bikeway code by tools/bike-network/walk-reach.py (Bryan,
// 2026-09-29: "walkable ... instead of as the bird
// flies"); the page takes a point's nearest ticked code, which is exact. It opens on the North Star
// network built as drawn; a toggle switches to today's network (Bryan,
// 2026-09-24: "Default to showing the North Star network. Offer a toggle
// between North Star and current. Not an added layer"). The Golden Gate Park
// connection test was removed the same day: "Was fun but not needed for now". Nothing is precomputed per
// combination, so any combination is exact.
//
// The map is MapLibre over the site's basemap (src/maplibre.mjs), opening on
// the same view as the hero map; line widths and dot sizes are given in the
// hero map's drawing units (MW in bike-history.mjs) and turned into pixels at
// that view.

import fs from "node:fs";
import path from "node:path";
import { esc, PLAN_URL } from "./transportation.mjs";
import { encodeRuns, encodePoints, inlineJson } from "./maplibre.mjs";
import { Plot, plotSVG, frame, label, yGrid, xLabels, HALO } from "./plot.mjs";
import { P, MW, BOUNDS, segments, reach, rows, years, first, last, mi, THRESHOLDS, DEFAULT_REACH, history, removed } from "./bike-history.mjs";
const planned = history.planned || { rows: [], uncounted: [] };

const DATA = path.join(import.meta.dirname, "..", "data");
const read = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8"));
const components = read("bike-history/components.json");
const planStatus = read("north-star/status.json");
const traced = read("north-star/traced.geojson");
const progress = read("bike-progress.json");
const allAges = read("bike-history/all-ages.geojson");
// Per bikeway code, the first distance each census block, school and branch is
// within by walking; one character per point (tools/bike-network/walk-reach.py).
const walk = read("bike-history/walk-reach.json");
export const walkNetwork = walk.network;
// Residents' distance to a Muni stop, measured the explorer's way, as a
// yardstick for the distance control (Bryan, 2026-09-23: "Add context here
// ... 98% (check on this) are within 2 blocks of a muni stop"). Written by
// scripts/muni-stop-reach.py.
const muni = read("bike-history/muni-reach.json");
// Whole percents, except near 100, where rounding would claim everyone.
const pctM = (v) => (v >= 99 ? v.toFixed(1) : String(Math.round(v)));

export const YEAR = components.year;
const BCI = components.bci_threshold;

// The eight codes the generator splits a block's rows into, in bit order.
export const ORDER = ["1", "4", "S", "2c", "2b", "3c", "3b", "L"];
const BIT = Object.fromEntries(ORDER.map((c, i) => [c, 1 << i]));

// The six cards a reader ticks. Painted lanes and signed routes each cover
// two codes, calm and not; only the calm code counts.
export const CARDS = [
  { id: "1", codes: ["1"], name: "Off-street paths", caltrans: "Class I", plan: "counts", where: "The Panhandle" },
  { id: "4", codes: ["4"], name: "Separated lanes", caltrans: "Class IV", plan: "counts", where: "3rd Street" },
  { id: "S", codes: ["S"], name: "Slow Streets", caltrans: "no state class", plan: "counts", where: "Page Street" },
  { id: "2", codes: ["2c", "2b"], name: "Unprotected bikeways: painted lanes", caltrans: "Class II", plan: `only with a Bike Comfort Index above ${BCI}`, where: "Kirkham Street" },  // unprotected lanes its whole length, 3.3 of 4.1 km above the BCI line; Folsom was protected in SoMa (Bryan, 2026-09-29)-22nd; Bryan, 2026-09-24: "No don't use Cesar Chavez"
  { id: "3", codes: ["3c", "3b"], name: "Unprotected bikeways: signed routes", caltrans: "Class III", plan: `only with a Bike Comfort Index above ${BCI} and traffic calming`, where: "The Wiggle's side streets" },
  // The plan's Shared Level III, which it does not call all-ages, so the card
  // starts unticked (Bryan, 2026-09-29: "Maybe we could just leave a sixth
  // category here that's by default unchecked"). Only the North Star has it.
  { id: "L", codes: ["L"], name: "Traffic-calmed streets", caltrans: "no state class", plan: "not all-ages in the plan", where: "Corbett Avenue", off: true },
];

// The plan's North Star facilities, mapped to the code a finished block would
// carry. [inference — mine]: the plan defines Separated as all-ages and its
// Shared streets as calmed neighbourhood streets, the Slow Street model;
// The plan calls Shared Levels I and II "An All-Ages-and-Abilities facility"
// and says no such thing of Level III, whose lighter shading means "some
// traffic calming may happen" (pp. 68-69, 76-77; site/data/class-definitions.json).
// So Level III gets its own card, unticked by default, and never enters the
// goal. Undecided is never counted.
const PLAN_CODE = { "Separated": "4", "Car-free": "1", "Shared-use Path": "1", "Shared": "S", "Shared L3": "L" };

const DISTANCES = [
  ...THRESHOLDS.map((t) => ({ id: t.id, metres: t.metres, label: t.label, short: t.short })),
].sort((a, b) => a.metres - b.metres);

// Bryan, 2026-09-24, on the distance control: "For 1/4 mile note that this is
// the plans definition. And how many times farther than car parking and
// transit access it is. And how long it would take to walk 1/4 mile on each
// end for an average six year old." The distance is walked along the street
// network. A typical 6-year-old's pace walking in a group, 2 mph (Bryan, 2026-09-29:
// "I'd rather give a typical number. When walking in groups, it sounds like
// typical 6 year olds walk around 2 mph"). His figure, stated as a pace on
// the page; no study gives it. Whole minutes, rounded.
const CHILD_PACE = { mph: 2, mps: 2 * 1609.344 / 3600 };
const feet = (m) => Math.round(m / 0.3048 / 10) * 10;
// Small counts spelled out in prose (Bryan's edit, 2026-09-30: "about eight minutes").
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const numberWord = (n) => WORDS[Number(n)] || String(n);
function walkMinutes(m) {
  return String(Math.round(m / CHILD_PACE.mps / 60));
}
// Bryan, 2026-09-24: "Shorten this to 3 lines ... express the muni and car
// stuff in 15 words or less", and "give the muni and car parking context
// here too" for the shorter distances. The ratios are to the resident-weighted
// median distances (muni-stop-reach.py, parking-reach.py).
// Bryan, 2026-09-29: the Muni and parking comparison "is a lot of text ...
// put an icon of a car and a bus" on the choices, so each distance says why it
// is there. One block is about the walk to a parked car, two blocks the walk to
// a Muni stop; each note gives the share of residents that close
// (muni-stop-reach.py, parking-reach.py).
const ITDP_URL = "https://atlas.itdp.org/";
const PARKING_SURVEY = { source: { name: "2015 SFMTA survey", url: "https://www.sfmta.com/blog/five-things-weve-learned-we-look-improve-neighborhood-parking" } };
const DIST_WHY = {
  // Bryan, 2026-09-29: "70% of residents can park their primary car within 1
  // block of home". SFMTA's 2015 resident survey: "71 percent said they have
  // access to off-street parking (in driveway or garage)", of respondents with
  // a car; parking at home is within a block of it. Worded as the survey puts
  // it (Bryan, 2026-09-29: "Most careowners can park their car within 1
  // block. 71% had a driveway or garage (2015 SFMTA Survey)").
  block: { icon: "car", tip: () => "Most car owners can park their car within 1 block. 71% had a driveway or garage", src: PARKING_SURVEY },
  "2blocks": { icon: "bus", tip: () => `${pctM(muni.share["2blocks"])}% of residents live within 2 blocks of a Muni stop`, src: muni },
};
const ICONS = {
  car: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 11l1.6-4.2A2 2 0 0 1 8.5 5.5h7a2 2 0 0 1 1.9 1.3L19 11M4 11h16v5H4zM6.5 16v2M17.5 16v2"/><circle cx="7.5" cy="13.5" r="0.8"/><circle cx="16.5" cy="13.5" r="0.8"/></svg>',
  bus: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3.5" width="14" height="14" rx="2"/><path d="M5 10h14M8 17.5V20M16 17.5V20"/><circle cx="8.5" cy="14" r="0.8"/><circle cx="15.5" cy="14" r="0.8"/></svg>',
};
function distanceNote(t) {
  const ft = feet(t.metres);
  if (t.id === "quarter") {
    // In feet like the other two notes (Bryan, 2026-09-29, accepting the
    // writing review's edit 12).
    return `About ${ft.toLocaleString("en-US")} feet: the plan's definition of connected (<a href="${esc(PLAN_URL)}">p. 24</a>). A 6-year-old walking ${CHILD_PACE.mph} mph takes about ${numberWord(walkMinutes(t.metres))} minutes at each end of a trip to walk a quarter mile.`;
  }
  if (t.id === "1000ft") {
    // Bryan, 2026-10-06: "Can you add 1000 feet to the explorer?" The post
    // compares us with Montreal at this distance, the ITDP Atlas's 300 m.
    return `About 1,000 feet, the walk the ITDP Atlas measures. Half of Montrealers live this close to a protected bikeway (<a href="${esc(ITDP_URL)}">ITDP Atlas</a>).`;
  }
  const w = DIST_WHY[t.id];
  return `About ${ft.toLocaleString("en-US")} feet. ${w.tip()} (<a href="${esc(w.src.source.url)}">${esc(w.src.source.name)}</a>).`;
}

// A block's points at the data's precision (about a metre), repeats and
// vertices within half a metre of a straight stretch dropped, each as its
// offset from the point before (encodeRuns in maplibre.mjs), which the page
// sums back to the same numbers before it draws.
const flat = (pts) => encodeRuns([pts], { tol: 0.5 }).d;

/** The data the script works from, built once at build time. */
let payloadCache = null;
function payload() {
  return (payloadCache ??= buildPayload());
}

// The explorer's data rides in the page as inert JSON and is parsed when the
// explorer comes within 800 pixels of the screen. It is not a file fetched
// then, because the board frames the page in a sandbox whose opaque origin
// makes every fetch cross-origin, and the fetch fails.
export const explorerData = () => inlineJson(payload());

function buildPayload() {
  const yearIdx = segments.years.length - 1;
  const segs = [];
  for (const s of segments.segments) {
    if (s.y[yearIdx] === "0") continue;
    const comp = components.blocks[s.key];
    const p = flat(s.pts);
    if (p.length < 4) continue;
    let mask = 0;
    const m = {};
    if (comp) {
      for (const [code, miles] of Object.entries(comp.m)) { mask |= BIT[code]; m[code] = miles; }
      if (comp.s != null) mask |= BIT.S;
    }
    segs.push({ p, c: mask, m, ...(comp && comp.s != null ? { s: comp.s } : {}), k: s.key });
  }
  // Street names come with the basemap, so the page carries none.
  const segIndexByCnn = new Map(segs.map((s, i) => [String(s.k), i]));

  const col = Object.fromEntries(reach.blocks.columns.map((c, i) => [c, i]));
  const rd = (v) => Math.round(v * 1e5) / 1e5;
  // Census blocks as one list of offsets and one of populations; the page
  // rebuilds [lon, lat, population] for each.
  const blocks = { xy: encodePoints(reach.blocks.rows.map((r) => [r[col.lon], r[col.lat]])), pop: reach.blocks.rows.map((r) => r[col.pop_latest]) };
  const yearOf = (iso) => (iso ? Number(iso.slice(0, 4)) : null);
  const schoolOpen = (s) => !s.closed && (!s.open || yearOf(s.open) <= YEAR);
  const libOpen = (l) => !(l.closed_from && YEAR >= l.closed_from && (l.reopens == null || YEAR < l.reopens));
  const schools = reach.schools.filter(schoolOpen)
    .map((s) => [rd(s.lon), rd(s.lat), s.level]);
  const libs = reach.libraries.filter(libOpen)
    .map((l) => [rd(l.lon), rd(l.lat)]);
  // The walking levels, cut to the same points in the same order: every
  // census block row, then the open schools, then the open branches.
  const nb = reach.blocks.rows.length, ns = reach.schools.length;
  if (walk.counts.blocks !== nb || walk.counts.schools !== ns || walk.counts.libraries !== reach.libraries.length) throw new Error("walk-reach.json is out of step with reach.json; rerun tools/bike-network/walk-reach.py");
  const walkIds = walk.thresholds.map((t) => t.id).join();
  if (walkIds !== DISTANCES.map((d) => d.id).join()) throw new Error(`walk-reach.json thresholds ${walkIds} differ from the page's`);
  const keep = [...Array(nb).keys(), ...reach.schools.flatMap((s, i) => (schoolOpen(s) ? [nb + i] : [])), ...reach.libraries.flatMap((l, i) => (libOpen(l) ? [nb + ns + i] : []))];
  const cut = (str) => keep.map((i) => str[i]).join("");
  // A code whose every point is at level len(thresholds) reaches no one at any
  // distance, and is left out.
  const none = String(DISTANCES.length);
  const reachesAny = (v) => [...v].some((ch) => ch !== none);
  const walkLv = { today: Object.fromEntries(Object.entries(walk.today).filter(([, v]) => reachesAny(v)).map(([c, v]) => [c, cut(v)])),
                   plan: Object.fromEntries(Object.entries(walk.plan).filter(([, v]) => reachesAny(v)).map(([c, v]) => [c, cut(v)])) };

  // Every rated plan block, with the code a block built as drawn would carry,
  // its plan miles (per direction row), whether it already meets the plan,
  // and the index of today's bikeway block on the same street segment, so the
  // client can count one or the other and never both.
  const status = Object.fromEntries(planStatus.blocks.map((b) => [b.cnn, b]));
  const plan = [];
  for (const f of traced.features) {
    const st = status[String(f.properties.cnn)];
    if (!st) continue;
    const p = flat(f.geometry.coordinates);
    if (p.length < 4) continue;
    const k = segIndexByCnn.has(String(f.properties.cnn)) ? segIndexByCnn.get(String(f.properties.cnn)) : -1;
    plan.push({ p, code: PLAN_CODE[f.properties.facility] || null, mi: Math.round(st.m / 1.609344) / 1000, k });
  }
  for (const s of segs) delete s.k;
  return {
    order: ORDER, bounds: BOUNDS, units: MW,
    distances: DISTANCES.map((d) => ({ id: d.id, m: d.metres, short: d.short })),
    defaultDistance: DEFAULT_REACH,
    segs, blocks, schools, libs, plan, walk: walkLv,
    levels: ["elementary", "middle", "high", "k12", "other"],
    levelNames: { elementary: "elementary", middle: "middle", high: "high", k12: "K–12", other: "other" },
  };
}

// Two of SFMTA's own photographs from the Biking and Rolling Plan (March
// 2025), cut from the printed pages named; the plan has no photo of a path, a
// painted lane or a signed route. Those three are freely licensed Wikimedia
// Commons photos, cropped to 480 by 320 and credited at the page's end, chosen
// with Bryan on 2026-09-24. A CC BY-SA crop carries the same licence.
const PHOTOS = {
  "1": { card: "Off-street paths", file: "commons-path-panhandle.jpg", alt: "A paved path through the Panhandle's lawn and trees, with people walking",
         credit: { by: "Yelderberry", url: "https://commons.wikimedia.org/wiki/File:Panhandle_(San_Francisco)_2024-06-09_1.jpg", licence: "CC BY-SA 4.0", licenceUrl: "https://creativecommons.org/licenses/by-sa/4.0/" } },
  "4": { card: "Separated lanes", file: "plan-separated-3rd-street.jpg", page: 75, alt: "A green bikeway beside the sidewalk, separated from traffic by posts and a bike-share dock" },
  S: { card: "Slow Streets", file: "plan-slow-page-street.jpg", page: 77, alt: "A residential street with a Slow Streets sign at the corner" },
  // Painted lanes: the drawing stands in until Bryan's photo of a lane scoring above 80 arrives.
  "3": { card: "Signed routes", file: "commons-signed-wiggle.jpg", alt: "A street in the Lower Haight with a green Wiggle bike route sign and a rider in traffic",
         credit: { by: "Schwoagl", url: "https://commons.wikimedia.org/wiki/File:The_Wiggle.png", licence: "CC BY 3.0", licenceUrl: "https://creativecommons.org/licenses/by/3.0/" } },
};
// The photos' credits, gathered with the page's other credits at its end
// (layout.mjs, gatherNotes): SFMTA's two as one entry, each Commons photo
// with its photographer and licence.
function explorerCredits() {
  const plan = Object.values(PHOTOS).filter((ph) => ph.page);
  const sfmta = `<ul class="credit" data-for="${plan.map((ph) => ph.card).join(" and ")} photos"><li>SFMTA, <a href="${esc(PLAN_URL)}">Biking and Rolling Plan</a> (March 2025), pp. ${plan.map((ph) => ph.page).join(" and ")}</li></ul>`;
  const commons = Object.values(PHOTOS).filter((ph) => ph.credit).map((ph) =>
    `<ul class="credit" data-for="${ph.card} photo"><li><a href="${esc(ph.credit.url)}">${esc(ph.credit.by)}</a>, Wikimedia Commons (<a href="${esc(ph.credit.licenceUrl)}">${esc(ph.credit.licence)}</a>), cropped</li></ul>`);
  return [sfmta, ...commons].join("");
}
// Each photo is its own file beside the page, loaded lazily: on a phone the
// cards sit in a panel that stays closed until the reader opens it, so the
// photos are fetched only then, and elsewhere only as the explorer nears the
// screen. The overview's page module writes them.
const PHOTO_DIR = "/transportation/bike/photos";
// The plan's North Star map, pp. 68-69, cropped above the page footer, for
// the post's north-star-map block (Bryan, 2026-10-07: "Can we include a
// screenshot of the north star network"). It is written beside the photos.
export const NORTH_STAR_MAP = { file: "plan-north-star-map.jpg", pages: "68-69", width: 1600, height: 1539,
  alt: "SFMTA's North Star network map of San Francisco: car-free streets, shared-use paths, separated bikeways and shared streets, with notes on planned work" };
export const NORTH_STAR_MAP_SRC = `${PHOTO_DIR}/${NORTH_STAR_MAP.file}`;
export const explorerPhotos = () => [...Object.values(PHOTOS), NORTH_STAR_MAP].map((ph) => ({
  path: `${PHOTO_DIR}/${ph.file}`, file: `${PHOTO_DIR.slice(1)}/${ph.file}`, bytes: fs.readFileSync(path.join(DATA, "photos", ph.file)),
}));

const glyph = (id) => {
  if (PHOTOS[id]) return `<img class="ex-glyph ex-photo" src="${PHOTO_DIR}/${PHOTOS[id].file}" loading="lazy" decoding="async" alt="${esc(PHOTOS[id].alt)}" width="240" height="160">`;
  // A street seen from above, 120 by 56, as a stand-in until each card has
  // a licensed photo: grey roadway, the bikeway in the network colour, cars
  // as dark blocks, posts as dots, a sign as a diamond.
  const road = `<rect x="0" y="0" width="120" height="56" fill="var(--rule)"/>`;
  const car = (x, y) => `<rect x="${x}" y="${y}" width="16" height="8" rx="2" fill="var(--muted)"/>`;
  const lane = (y, h, dash = "") => `<rect x="0" y="${y}" width="120" height="${h}" fill="var(--seq-3-soft)"/>${dash ? `<line x1="0" x2="120" y1="${y}" y2="${y}" stroke="var(--paper)" stroke-width="2" stroke-dasharray="${dash}"/>` : ""}`;
  const bike = (x, y) => `<circle cx="${x}" cy="${y}" r="2.5" fill="var(--seq-3)"/><circle cx="${x + 7}" cy="${y}" r="2.5" fill="var(--seq-3)"/>`;
  let body = "";
  if (id === "1") body = `<rect x="0" y="0" width="120" height="56" fill="var(--seq-2-soft)"/><rect x="0" y="20" width="120" height="16" fill="var(--seq-3-soft)"/>${bike(30, 28)}${bike(80, 28)}`;
  else if (id === "4") body = `${road}${lane(36, 20)}${[10, 40, 70, 100].map((x) => `<circle cx="${x}" cy="34" r="2.5" fill="var(--paper)"/>`).join("")}${car(20, 12)}${car(70, 12)}${bike(40, 46)}${bike(90, 46)}`;
  else if (id === "S") body = `${road}<polygon points="60,6 72,18 60,30 48,18" fill="var(--seq-2)"/>${bike(20, 30)}${bike(90, 30)}${car(30, 42)}`;
  else if (id === "2") body = `${road}${lane(38, 18, "")}<line x1="0" x2="120" y1="38" y2="38" stroke="var(--paper)" stroke-width="2"/>${car(20, 12)}${car(70, 12)}${bike(40, 47)}${bike(90, 47)}`;
  else body = `${road}${car(20, 12)}${car(80, 30)}<polyline points="40,42 46,36 52,42" fill="none" stroke="var(--paper)" stroke-width="2.5"/><polyline points="40,48 46,42 52,48" fill="none" stroke="var(--paper)" stroke-width="2.5"/>${bike(100, 46)}`;
  return `<svg class="ex-glyph" viewBox="0 0 120 56" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${body}</svg>`;
};

/** The figure: live figures, the cards and switches, the map and the key. */
export function explorer() {
  const d = payload();
  const cards = CARDS.map((c) => `
      <label class="ex-card">
        <input type="checkbox" data-card="${c.id}"${c.off ? "" : " checked"}>
        ${glyph(c.id)}
        <span class="ex-card-text"><b>${esc(c.name)}</b>
        <span class="ex-card-where">${esc(c.where)}</span></span>
      </label>`).join("");
  const dists = d.distances.map((t) => `<label class="ex-pill"><input type="radio" name="ex-dist" value="${t.id}"${t.id === d.defaultDistance ? " checked" : ""}>${DIST_WHY[t.id] ? `<span class="ex-pill-icon" title="${esc(DIST_WHY[t.id].tip())}">${ICONS[DIST_WHY[t.id].icon]}</span>` : " "}${esc(DISTANCES.find((x) => x.id === t.id).label)}</label>`).join("");
  return `<figure class="explorer" id="explorer" data-explorer>
  <div class="ex-body">
    <div class="ex-controls">
      <div class="ex-tabs">
        <button type="button" data-ex-tab="net" aria-expanded="false"><small>Network</small><b data-ex-tab-val="net"></b></button>
        <button type="button" data-ex-tab="dist" aria-expanded="false"><small>Close enough</small><b data-ex-tab-val="dist"></b></button>
        <button type="button" data-ex-tab="classes" aria-expanded="false"><small>Bikeways</small><b data-ex-tab-val="classes"></b></button>
      </div>
      <fieldset class="ex-net"><legend>Choose bike network to review</legend><div class="ex-pills">
        <label class="ex-pill"><input type="radio" name="ex-net" value="plan" checked> If the plan were built</label>
        <label class="ex-pill"><input type="radio" name="ex-net" value="today"> Today</label>
      </div></fieldset>
      <fieldset class="ex-dist"><legend>What's Close Enough?</legend><div class="ex-pills">${dists}</div><div class="ex-dist-notes">${DISTANCES.map((t) => `<p data-for="${t.id}">${distanceNote(t)}</p>`).join("")}</div></fieldset>
      <fieldset class="ex-classes"><legend>What bikeway types are Good Enough?</legend>
        <div class="ex-cards">${cards}</div>
        <div class="ex-panel-foot">
          <button type="button" class="ex-reset" data-ex-reset>Reset to the Biking and Rolling Plan's criteria</button>
          <button type="button" class="ex-done" data-ex-done>Done</button>
        </div>
      </fieldset>
    </div>
    <div class="ex-map-wrap"><div class="ex-map glmap" role="img" aria-label="San Francisco's bikeways under the definition chosen, with the census blocks, schools and library branches within the chosen distance of one"></div></div>
    <div class="ex-figures" aria-live="polite">
      <h3 class="ex-figs-h" data-ex-figs-h>How good would the network be?</h3>
      <div class="ex-fig"><b data-ex-res>–</b><span>of residents connected</span></div>
      <div class="ex-fig"><b data-ex-sch>–</b><span>K-12 schools connected</span></div>
      <div class="ex-fig"><b data-ex-lib>–</b><span>library branches connected</span></div>
    </div>
  </div>
  <div class="map-keys">
    <div class="map-key-row"><b class="map-key-h">Bikeways</b><ul class="map-key"><li><i class="key aa"></i>Good enough, as chosen</li></ul></div>
    <div class="map-key-row"><b class="map-key-h">Connected</b><ul class="map-key">
      <li><i class="key blk"></i>Residents</li>
      <li><i class="key sch"></i>K-12 school</li>
      <li><i class="key lib"></i>Library branch</li>
      <li>Grey or hollow: not connected</li>
    </ul></div>
  </div>
  ${explorerCredits()}  <script type="application/json" data-ex-data>${explorerData()}</script>
</figure>`;
}

export const EXPLORER_CSS = `<style>
.explorer { margin: 0 0 12px; }
.ex-body { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr) minmax(150px, 230px); gap: 12px 22px; align-items: start; }
.ex-controls fieldset { border: 0; padding: 0; margin: 0 0 12px; min-width: 0; }
.ex-controls legend { font-family: Archivo, sans-serif; font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); padding: 0; margin: 0 0 6px; }
/* Two-column tiles, each led by its photo or drawing at a size you can see
   something in (Bryan, 2026-09-23: "Pic needs to be at least 2x as big ...
   Don't need 'Class 1' or 87mi. One example is enough"). */
.ex-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
/* A small thumbnail beside each name, two to a row, so the eight cards fit
   above the fold (Bryan, 2026-09-29: "These take up too much room now"). */
/* Photo across the card, cropped wide so three rows of cards fit beside the
   map on a laptop (Bryan, 2026-09-29: "too compact to see the photos. Make
   them bigger again. Maybe we need some other way to fit on a laptop
   screen"); the example street sits on the photo's corner. */
.ex-card { position: relative; display: grid; align-content: start; gap: 3px; padding: 3px; border: 1px solid var(--rule); border-radius: 7px; cursor: pointer; background: var(--paper); }
.ex-card .ex-glyph { width: 100%; aspect-ratio: 2 / 1; }
.ex-card .ex-card-where { position: absolute; top: 6px; right: 6px; max-width: calc(100% - 34px); padding: 0 4px; border-radius: 3px; background: color-mix(in srgb, var(--paper) 88%, transparent); color: var(--ink); font-size: 0.62rem; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ex-card:has(input:checked) { border-color: var(--seq-3); background: var(--seq-3-soft); }
.ex-card input { position: absolute; top: 6px; left: 6px; margin: 0; accent-color: var(--seq-3); }
.ex-glyph { width: 100%; height: auto; aspect-ratio: 3 / 2; display: block; border-radius: 4px; object-fit: cover; }
.ex-card-text { display: block; font-size: 0.82rem; line-height: 1.2; }
.ex-card-text b { display: block; font-weight: 600; }
.ex-card-where { display: block; color: var(--muted); font-size: 0.7rem; }
.ex-pills { display: flex; flex-wrap: wrap; gap: 5px; }
.ex-yardstick { margin: 7px 0 0; font-size: 0.78rem; line-height: 1.35; color: var(--muted); }
.ex-pill { font-size: 0.8rem; padding: 3px 10px; border: 1px solid var(--rule); border-radius: 999px; cursor: pointer; color: var(--muted); }
.ex-pill:has(input:checked) { background: var(--ink); border-color: var(--ink); color: var(--paper); font-weight: 600; }
.ex-pill input { position: absolute; opacity: 0; width: 0; height: 0; }
.ex-pill-icon { display: inline-flex; vertical-align: -3px; margin-right: 4px; }
.ex-pill-icon svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.ex-pill-icon svg circle { fill: currentColor; }
/* Every note sits in the same grid cell, so the box is as tall as the longest
   and changing the distance moves nothing below it. */
.ex-dist-notes { display: grid; margin: 6px 0 0; }
.ex-dist-notes p { grid-area: 1 / 1; margin: 0; font-size: 0.76rem; line-height: 1.35; color: var(--muted); visibility: hidden; }
${DISTANCES.map((t) => `.ex-dist:has(input[value="${t.id}"]:checked) .ex-dist-notes p[data-for="${t.id}"]`).join(",\n")} { visibility: visible; }
.ex-reset { justify-self: start; font: inherit; font-size: 0.78rem; padding: 4px 10px; border: 1px solid var(--rule); border-radius: 6px; background: var(--paper); color: var(--ink); cursor: pointer; }
.ex-reset:hover { border-color: var(--accent); }
.ex-panel-foot { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
.ex-tabs, .ex-done { display: none; }
.ex-map-wrap { min-width: 0; display: flex; justify-content: center; position: relative; }
.ex-map { display: block; height: min(calc(100dvh - 220px), 720px); min-height: 380px; width: auto; max-width: 100%; aspect-ratio: ${MW} / ${P.height}; }
.ex-figures { display: grid; gap: 16px; padding-top: 4px; }
.ex-figs-h { grid-column: 1 / -1; margin: 0; font-family: Archivo, sans-serif; font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.ex-fig b { display: block; font-family: Archivo, sans-serif; font-weight: 700; font-size: 2.1rem; line-height: 1; color: var(--seq-3); font-variant-numeric: tabular-nums; }
.ex-fig > span { display: block; font-size: 0.84rem; color: var(--ink); line-height: 1.3; margin-top: 4px; }
.ex-fig small { color: var(--muted); font-size: 0.76rem; }
.ex-compare { font-size: 0.74rem; }
.explorer .map-key { font-size: 0.8rem; }
.map-key [hidden] { display: none; }
/* Controls left, map middle, figures right, down to tablet width (Bryan,
   2026-09-24: "Should go left to right with controls on left to choose
   your scenario. Map in middle. And metrics results to the right"). */
@media (max-width: 1100px) {
  .ex-body { grid-template-columns: minmax(200px, 250px) minmax(0, 1fr) minmax(130px, 170px); gap: 10px 16px; }
  .ex-fig b { font-size: 1.7rem; }
  .ex-cards { grid-template-columns: 1fr; gap: 4px; }
  .ex-card { grid-template-columns: 72px 1fr; align-items: center; gap: 8px; }
  .ex-card .ex-glyph { width: 72px; aspect-ratio: 3 / 2; }
  .ex-card input { top: 7px; left: 7px; }
  .ex-card .ex-card-where { position: static; padding: 0; background: none; color: var(--muted); font-size: 0.7rem; white-space: normal; max-width: none; }
  .ex-map { height: auto; min-height: 0; width: 100%; }
}
/* Phones: cards three to a row and a shorter map, so the choices and the map
   fit on one screen (Bryan, 2026-09-24: "two rows of up to three so we fit
   more on screen"; "make this less tall vertically"). */
@media (max-width: 760px) {
  .ex-body { grid-template-columns: 1fr; }
  .ex-cards { grid-template-columns: repeat(3, 1fr); }
  .ex-card { grid-template-columns: 1fr; padding: 3px; gap: 2px; }
  .ex-card .ex-glyph { width: 100%; aspect-ratio: 3 / 2; }
  .ex-card input { top: 5px; left: 5px; }
  .ex-card-text { font-size: 0.7rem; }
  .ex-card-where { font-size: 0.62rem; }
  .ex-map { width: auto; max-width: 100%; height: min(80vw, 36svh); }
  .ex-controls fieldset { margin-bottom: 8px; }
  .ex-figures { grid-template-columns: repeat(2, 1fr); gap: 8px 16px; }
  /* Bryan, 2026-09-24, on phones: "condensed controls on top for the three
     major areas. Don't have them all expanded at once": three buttons, each
     opening its panel over the map; a network or distance choice closes it,
     the bikeway types wait for Done. */
  .ex-controls { position: relative; }
  .ex-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
  .ex-tabs button { font: inherit; text-align: left; padding: 5px 8px; border: 1px solid var(--rule); border-radius: 8px; background: var(--paper); color: var(--ink); cursor: pointer; min-width: 0; }
  .ex-tabs button[aria-expanded="true"] { border-color: var(--ink); box-shadow: inset 0 0 0 1px var(--ink); }
  .ex-tabs small { display: block; font-size: 0.66rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .ex-tabs b { display: block; font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .ex-tabs b::after { content: " ▾"; color: var(--muted); font-weight: 400; }
  .ex-controls > fieldset { display: none; }
  .ex-controls[data-open="net"] > .ex-net, .ex-controls[data-open="dist"] > .ex-dist, .ex-controls[data-open="classes"] > .ex-classes {
    display: block; position: absolute; left: 0; right: 0; top: calc(100% + 4px); z-index: 6; margin: 0; padding: 10px; max-height: 70svh; overflow: auto;
    background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; box-shadow: 0 8px 24px rgba(31, 36, 33, 0.18); }
  .ex-done { display: inline-block; font: inherit; font-weight: 600; font-size: 0.85rem; padding: 5px 16px; margin-left: auto; border: 0; border-radius: 6px; background: var(--ink); color: var(--paper); cursor: pointer; }
  .ex-compare { display: none; }
  .ex-fig b { font-size: 1.5rem; }
  .ex-fig > span { font-size: 0.76rem; }
}
</style>`;

export const EXPLORER_SCRIPT = `<script>
(function () {
  var box = document.querySelector("[data-explorer]");
  if (!box) return;
  // The data is parsed when the explorer is within 800 pixels of the screen
  // (see explorerData); until then the figures read "–".
  var loaded = false;
  function load() {
    if (loaded) return; loaded = true;
    start(JSON.parse(box.querySelector("[data-ex-data]").textContent));
  }
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      for (var i = 0; i < es.length; i++) if (es[i].isIntersecting) { io.disconnect(); load(); return; }
    }, { rootMargin: "800px 0px" });
    io.observe(box);
  } else load();
  // The controls work before the data arrives: the choices in the address
  // and the phone's panels need only the page.
  var cards = box.querySelectorAll("[data-card]"), nets = box.querySelectorAll('input[name="ex-net"]'), dists = box.querySelectorAll('input[name="ex-dist"]');
  // Choices in the address, if any.
  var p0 = new URLSearchParams(location.search), def0 = p0.get("def");
  if (def0) { var ids = def0.replace(/-any$/, ""); cards.forEach(function (c) { c.checked = ids.indexOf(c.dataset.card) >= 0; }); }
  // A link from before ½ mile was dropped (Bryan, 2026-09-24: "Don’t include
  // 1/2 mile it’s not useful") keeps the default.
  if (box.querySelector('input[name="ex-dist"][value="' + p0.get("dist") + '"]')) dists.forEach(function (r) { r.checked = r.value === p0.get("dist"); });
  if (p0.get("net") === "today") nets.forEach(function (r) { r.checked = r.value === "today"; });
  // Phone controls: each tab names the current choice and opens its panel.
  var ctl = box.querySelector(".ex-controls"), tabs = box.querySelectorAll("[data-ex-tab]");
  function pick(name) { var r = box.querySelector('input[name="' + name + '"]:checked'); return r ? r.parentNode.textContent.trim() : ""; }
  function labelTabs() {
    box.querySelector('[data-ex-tab-val="net"]').textContent = pick("ex-net");
    box.querySelector('[data-ex-tab-val="dist"]').textContent = pick("ex-dist");
    var on = Array.prototype.filter.call(cards, function (c) { return c.checked; }).length;
    box.querySelector('[data-ex-tab-val="classes"]').textContent = on + " of " + cards.length;
    // The figures' heading follows the network (Bryan, 2026-09-29, accepting
    // the writing review's edit 2).
    var today = box.querySelector('input[name="ex-net"]:checked');
    box.querySelector("[data-ex-figs-h]").textContent = today && today.value === "today" ? "How good is the network today?" : "How good would the network be?";
  }
  function openPanel(k) {
    ctl.dataset.open = k || "";
    tabs.forEach(function (t) { t.setAttribute("aria-expanded", String(t.dataset.exTab === k)); });
  }
  tabs.forEach(function (t) { t.addEventListener("click", function () { openPanel(ctl.dataset.open === t.dataset.exTab ? "" : t.dataset.exTab); }); });
  box.querySelector("[data-ex-done]").addEventListener("click", function () { openPanel(""); });
  box.addEventListener("change", function (e) { labelTabs(); if (e.target.name === "ex-net" || e.target.name === "ex-dist") openPanel(""); });
  box.querySelector("[data-ex-reset]").addEventListener("click", function () { labelTabs(); openPanel(""); });
  document.addEventListener("click", function (e) { if (ctl.dataset.open && !ctl.contains(e.target)) openPanel(""); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && ctl.dataset.open) openPanel(""); });
  labelTabs();
  function start(D) {
  // The geometry arrives as offsets (encodeRuns in maplibre.mjs); back to longitude and latitude.
  D.segs.forEach(function (s) { s.p = sfMap.points(s.p); });
  D.plan.forEach(function (s) { s.p = sfMap.points(s.p); });
  var bxy = sfMap.points(D.blocks.xy);
  D.blocks = D.blocks.pop.map(function (n, i) { return [bxy[i][0], bxy[i][1], n]; });
  var BIT = {}; D.order.forEach(function (c, i) { BIT[c] = 1 << i; });
  // Bryan, 2026-09-24: "Dont offer this option. Only include BCI > 80". Painted
  // lanes and signed routes always need the plan's comfort score. If this is
  // ever wired to a control, tools/bike-network/walk-reach.py must also compute 2b and 3b,
  // or reach will ignore them while the miles count them.
  var calm = { checked: true }, planKey = box.querySelectorAll("[data-plan-key]");
  var planOn = { get checked() { var v = "plan"; nets.forEach(function (r) { if (r.checked) v = r.value; }); return v === "plan"; } };
  var out = { res: box.querySelector("[data-ex-res]"), sch: box.querySelector("[data-ex-sch]"), lv: box.querySelector("[data-ex-levels]"),
              lib: box.querySelector("[data-ex-lib]"), mi: box.querySelector("[data-ex-mi]"), dist: box.querySelector("[data-ex-dist]") };
  // The palette is read once (sfMap.token): reading a computed style inside
  // the click forced a style recalculation of the whole page there. The site has one theme, so it does not change.
  var color = sfMap.token;

  function mask() {
    var m = 0;
    cards.forEach(function (c) {
      if (!c.checked) return;
      var id = c.dataset.card;
      if (id === "2" || id === "3") { m |= BIT[id + "c"]; if (!calm.checked) m |= BIT[id + "b"]; }
      else m |= BIT[id];
    });
    return m;
  }
  function distance() {
    var id = D.defaultDistance;
    dists.forEach(function (r) { if (r.checked) id = r.value; });
    for (var i = 0; i < D.distances.length; i++) if (D.distances[i].id === id) return D.distances[i];
    return D.distances[0];
  }
  function segMiles(s, m) {
    if (s.s != null && (m & BIT.S)) return s.s;
    var t = 0; for (var k in s.m) if (m & BIT[k]) t += s.m[k];
    return t;
  }
  // Walking levels of the ticked codes: for each point, the first distance
  // (index into D.distances) a ticked bikeway lies within, the smallest over
  // the codes; with the North Star added, over its codes too.
  function levels(m, planOnNow) {
    var strs = [], c;
    for (c in D.walk.today) if (m & BIT[c]) strs.push(D.walk.today[c]);
    if (planOnNow) for (c in D.walk.plan) if (m & BIT[c]) strs.push(D.walk.plan[c]);
    var n = D.blocks.length + D.schools.length + D.libs.length, lv = new Uint8Array(n).fill(D.distances.length);
    for (var k = 0; k < strs.length; k++) { var s = strs[k]; for (var i = 0; i < n; i++) { var v = s.charCodeAt(i) - 48; if (v < lv[i]) lv[i] = v; } }
    return lv;
  }
  function fmtMi(m) { return m >= 10 ? Math.round(m).toLocaleString() : (Math.round(m * 10) / 10).toFixed(1); }

  var lastState = null;
  // What a definition gives: the blocks drawn, their miles, and which census
  // blocks, schools and branches are within the distance. No DOM is touched,
  // so it can also run ahead of time to warm the click path (see warm()).
  function compute(m, di, planOnNow) {
    var active = [], miles = 0, skip = {};
    // With the plan added, a street block is counted once: at the plan's miles
    // when the facility it draws is ticked and counts for more than what is
    // there today, otherwise at today's miles.
    if (planOnNow) for (var q = 0; q < D.plan.length; q++) {
      var pl = D.plan[q], planMi = pl.code && (m & BIT[pl.code]) ? pl.mi : 0;
      var today = pl.k >= 0 && (D.segs[pl.k].c & m) ? segMiles(D.segs[pl.k], m) : 0;
      if (planMi > today + 0.001) { if (pl.k >= 0) skip[pl.k] = true; active.push({ p: pl.p, mi: planMi }); }
    }
    for (var i = 0; i < D.segs.length; i++) { var s = D.segs[i]; if (!skip[i] && (s.c & m)) { active.push({ p: s.p, mi: segMiles(s, m) }); } }
    for (var a = 0; a < active.length; a++) miles += active[a].mi;
    var walkLv = levels(m, planOnNow), nB = D.blocks.length, nS = D.schools.length;
    var pop = 0, popIn = 0, blk = new Array(nB);
    for (var b = 0; b < nB; b++) { var B = D.blocks[b]; pop += B[2]; blk[b] = walkLv[b] <= di; if (blk[b]) popIn += B[2]; }
    var lv = {}, lvIn = {}, schIn = 0, sch = new Array(nS);
    D.levels.forEach(function (l) { lv[l] = 0; lvIn[l] = 0; });
    for (var c = 0; c < nS; c++) { var S = D.schools[c]; var w = walkLv[nB + c] <= di; sch[c] = w; lv[S[2]] = (lv[S[2]] || 0) + 1; if (w) { schIn++; lvIn[S[2]] = (lvIn[S[2]] || 0) + 1; } }
    var libIn = 0, lib = new Array(D.libs.length);
    for (var e = 0; e < D.libs.length; e++) { lib[e] = walkLv[nB + nS + e] <= di; if (lib[e]) libIn++; }
    return { active: active, miles: miles, pop: pop, popIn: popIn, blk: blk, lv: lv, lvIn: lvIn, schIn: schIn, sch: sch, libIn: libIn, lib: lib };
  }
  function update() {
    var m = mask(), d = distance(), di = D.distances.indexOf(d), on = planOn.checked;
    var r = compute(m, di, on);
    planKey.forEach(function (li) { li.hidden = !on; });
    out.res.textContent = Math.round(100 * r.popIn / r.pop) + "%";
    out.sch.textContent = r.schIn + " of " + D.schools.length;
    if (out.lv) out.lv.textContent = D.levels.filter(function (l) { return r.lv[l]; }).map(function (l) { return (r.lvIn[l] || 0) + " of " + r.lv[l] + " " + D.levelNames[l]; }).join(" · ");
    out.lib.textContent = r.libIn + " of " + D.libs.length;
    if (out.mi) out.mi.textContent = fmtMi(r.miles);
    if (out.dist) out.dist.textContent = d.short;
    draw(r.active, r.blk, r.sch, r.lib);
    // The address is written once the frame is out rather than inside the
    // click: history.replaceState cost about 5 ms of a first click at a 4x CPU
    // throttle.
    clearTimeout(rememberT); rememberT = setTimeout(remember, 0);
  }
  // The address carries the choices, so a view can be shared.
  var rememberT = null;
  function remember() {
    var d = distance();
    var p = new URLSearchParams(location.search);
    var picks = []; cards.forEach(function (c) { if (c.checked) picks.push(c.dataset.card); });
    var def = picks.join("");
    if (def === "14S23") p.delete("def"); else p.set("def", def || "none");
    if (d.id === D.defaultDistance) p.delete("dist"); else p.set("dist", d.id);
    p.delete("island"); p.delete("gap"); p.delete("plan");
    if (planOn.checked) p.delete("net"); else p.set("net", "today");
    var qs = p.toString() ? "?" + p.toString() : "";
    if (qs !== lastState) { lastState = qs; history.replaceState(null, "", location.pathname + qs + location.hash); window.dispatchEvent(new CustomEvent("sfworks:state", { detail: qs + location.hash })); }
  }
  // The map: the basemap, every bikeway block faint, the census blocks, the
  // bikeways that count under the definition chosen, then the schools and
  // branches. Sizes are in the hero map's drawing units at the opening view
  // and grow as the fourth root of the zoom, so the detail spreads apart
  // rather than swelling (sfMap.grow).
  var lastDraw = null, ready = false, z0 = 0, s0 = 1;
  var el = box.querySelector(".ex-map");
  var map = sfMap.create(el, { bounds: D.bounds });
  function U(v) { return sfMap.grow(v, z0, s0); }
  function lineFeatures(list) { return list.map(function (a) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: a.p } }; }); }
  // A library branch is a square: two small images, connected and not, drawn
  // once and scaled with the zoom.
  function square(fill, stroke) {
    var n = 48, c = document.createElement("canvas"); c.width = c.height = n;
    var x = c.getContext("2d"); x.fillStyle = fill; x.strokeStyle = stroke; x.lineWidth = 8;
    x.fillRect(4, 4, n - 8, n - 8); x.strokeRect(4, 4, n - 8, n - 8);
    return x.getImageData(0, 0, n, n);
  }
  if (map) map.on("load", function () {
    z0 = map.getZoom(); s0 = sfMap.unitPx(map, D.bounds, D.units);
    var before = sfMap.under(map), round = { "line-cap": "round", "line-join": "round" };
    map.addImage("lib-on", square(color("--seq-1"), color("--ink")), { pixelRatio: 4 });
    map.addImage("lib-off", square(color("--paper"), color("--muted")), { pixelRatio: 4 });
    map.addSource("all", { type: "geojson", data: sfMap.collection(lineFeatures(D.segs)) });
    ["blk", "active", "sch", "lib"].forEach(function (id) { map.addSource(id, { type: "geojson", data: sfMap.collection([]) }); });
    // Every bikeway block, faint.
    map.addLayer({ id: "all", type: "line", source: "all", layout: round, paint: { "line-color": color("--rule"), "line-width": U(2) } }, before);
    // Census blocks, sized by population whether or not they are within reach
    // (Bryan, 2026-09-29: "when a block is not connected, it should stay the
    // same size"): within reach in the block colour, the rest faint.
    map.addLayer({ id: "blk", type: "circle", source: "blk", paint: { "circle-color": color("--seq-2"), "circle-radius": U(["get", "r"]), "circle-opacity": ["case", ["get", "on"], 0.6, 0.2] } }, before);
    // Every counted block solid, built or planned (Bryan, 2026-09-29: "Just
    // show solid green for bikeways that are good enough. No dotted lines").
    map.addLayer({ id: "active", type: "line", source: "active", layout: round, paint: { "line-color": color("--seq-3"), "line-width": U(5) } }, before);
    map.addLayer({ id: "lib", type: "symbol", source: "lib", layout: { "icon-image": ["case", ["get", "on"], "lib-on", "lib-off"], "icon-size": U(12 / 12), "icon-allow-overlap": true, "icon-ignore-placement": true } });
    map.addLayer({ id: "sch", type: "circle", source: "sch", paint: { "circle-radius": U(6), "circle-stroke-width": U(2),
      "circle-color": ["case", ["get", "on"], color("--seq-1"), color("--paper")], "circle-stroke-color": ["case", ["get", "on"], color("--ink"), color("--muted")] } });
    ready = true;
    if (lastDraw) draw.apply(null, lastDraw);
  });
  function point(c, props) { return { type: "Feature", properties: props, geometry: { type: "Point", coordinates: c } }; }
  function draw(active, blk, sch, lib) {
    lastDraw = [active, blk, sch, lib];
    if (!ready) return;
    var B = [], S = [], L = [];
    for (var b = 0; b < D.blocks.length; b++) { var k = D.blocks[b]; B.push(point([k[0], k[1]], { r: k[2] < 80 ? 2.2 : k[2] < 210 ? 3.2 : 4.4, on: !!blk[b] })); }
    for (var s = 0; s < D.schools.length; s++) S.push(point([D.schools[s][0], D.schools[s][1]], { on: !!sch[s] }));
    for (var e = 0; e < D.libs.length; e++) L.push(point(D.libs[e], { on: !!lib[e] }));
    map.getSource("blk").setData(sfMap.collection(B));
    map.getSource("active").setData(sfMap.collection(lineFeatures(active)));
    map.getSource("sch").setData(sfMap.collection(S));
    map.getSource("lib").setData(sfMap.collection(L));
  }
  // Bryan, 2026-09-24: "add a button at the end to reset to Biking and Rolling
  // Plan criteria": every bikeway type the plan counts, at the plan's quarter mile.
  box.querySelector("[data-ex-reset]").addEventListener("click", function () {
    cards.forEach(function (c) { c.checked = c.dataset.card !== "L"; });
    dists.forEach(function (r) { r.checked = r.value === "quarter"; });
    update();
    labelTabs();
  });
  box.addEventListener("change", update);
  labelTabs();
  update();
  // Warm the click path while the reader is still reading (task
  //: the first click after load took 16-21 ms at a 4x CPU
  // throttle, later ones about 5 ms). Once the browser is idle, the model runs
  // for the definitions one click away and the map is drawn again as it
  // stands, so the first real click finds the code compiled and the address
  // API loaded. Nothing on screen changes.
  var idle = window.requestIdleCallback || function (f) { return setTimeout(f, 200); };
  idle(function () {
    var m = mask(), di = D.distances.indexOf(distance());
    for (var i = 0; i < 3; i++) cards.forEach(function (c) { var id = c.dataset.card; compute(m ^ (id === "2" || id === "3" ? BIT[id + "c"] : BIT[id]), di, planOn.checked); });
    compute(m, di, !planOn.checked);
    if (lastDraw) draw.apply(null, lastDraw);
    try { history.replaceState(history.state, "", location.href); } catch (e) {}
  });
  }
})();
</script>`;

// ---- The goal chart -----------------------------------------------------------
//
// Bryan, 2026-09-23: "use the 2015 to 2026 trend in 'all ages miles' to show
// rate of progress on the all ages network. Plot out the goal for number of
// miles in the all ages network in the North star ... and show roughly how
// many years away we are from having a complete network."
//
// The goal is what the all-ages figure would read with every rated North
// Star block built as the plan draws it: the plan network's row miles
// (tools/bike-network/bike-progress.py, from Appendix L) plus today's all-ages miles on
// blocks the plan does not draw, which stay as they are. The pace is the
// average over the whole series, first year to last.

// The goal is the all-ages figure with every rated North Star block built as
// the plan draws it, where a block that already carries more all-ages miles
// than the plan draws keeps what it has, and every block the plan does not
// draw (or leaves Undecided) keeps today's all-ages miles. "Meets the plan"
// and "all-ages" are different tests (a painted lane on a Shared block meets
// the plan whatever its comfort index), so the goal is taken block by block
// from the plan's miles and today's all-ages miles, never from the plan's own
// met/unmet split.
const MILE = 1609.344;
const todayByCnn = new Map();
for (const f of allAges.features) {
  if (f.properties.until) continue;
  const k = String(f.properties.cnn);
  todayByCnn.set(k, (todayByCnn.get(k) || 0) + (f.properties.miles || 0));
}
let planMiles = 0, onPlanKept = 0, offPlanMiles = 0;
const rated = new Set();
for (const b of planStatus.blocks) {
  if (b.status === "unrated" || !PLAN_CODE[b.facility] || PLAN_CODE[b.facility] === "L") continue;
  rated.add(String(b.cnn));
  const pm = b.m / MILE, today = todayByCnn.get(String(b.cnn)) || 0;
  planMiles += pm;
  if (today > pm) onPlanKept += today - pm;
}
for (const [k, m] of todayByCnn) if (!rated.has(k)) offPlanMiles += m;
const goalMiles = planMiles + onPlanKept + offPlanMiles;
const firstArchive = rows.find((r) => r.tier !== "INSTALL_YR only");
// The pace is the average gain over the last ten full years, carried forward
// from today (Bryan, 2026-09-28: "just taking an average over the last 10
// years is probably a cleaner thing to do"). The same average as the yearly
// chart. Gains are counted from the end of PACE_FROM to the end of PACE_TO and
// labelled by the years whose gains they are, PACE_FROM + 1 to PACE_TO.
const PACE_FROM = 2015, PACE_TO = 2025;
const rowOf = (yr) => rows.find((r) => r.year === yr);
const pace = (rowOf(PACE_TO).all_ages_miles - rowOf(PACE_FROM).all_ages_miles) / (PACE_TO - PACE_FROM);
const paceArchived = (last.all_ages_miles - firstArchive.all_ages_miles) / (last.year - firstArchive.year);
const yearsToGo = (goalMiles - last.all_ages_miles) / pace;
const yearsToGoArchived = (goalMiles - last.all_ages_miles) / paceArchived;
export const goal = {
  planMiles, onPlanKept, offPlanMiles, goalMiles, pace, paceFrom: PACE_FROM + 1, paceTo: PACE_TO, paceArchived, yearsToGo, yearsToGoArchived,
  goalYear: Math.round(last.year + yearsToGo),
  goalYearArchived: Math.round(last.year + yearsToGoArchived),
  firstArchiveYear: firstArchive.year,
  planQueried: progress.generated || progress.queried || null,
  // SFMTA's planned bikeway work, counted the same way (bike-network-history.py).
  plannedAdded: planned.rows.reduce((t, r) => t + r.added_miles, 0),
  plannedTo: planned.rows.length ? planned.rows[planned.rows.length - 1].year : null,
  plannedCount: planned.rows.reduce((t, r) => t + r.projects.length, 0),
};

/** Miles of all-ages bikeway by year, the PACE_FROM–PACE_TO pace carried forward, and the North Star's finished figure. */
export function goalChart() {
  const x0 = first.year, x1 = goal.goalYear + 1;
  const top = Math.ceil(goalMiles / 100) * 100;
  const f = frame({ width: 640, height: 340, left: 56, right: 150, top: 62, bottom: 34, x: [x0, x1], y: [0, top] });
  const pts = rows.map((r) => ({ year: r.year, miles: r.all_ages_miles }));
  const decades = [];
  for (let yr = Math.ceil(x0 / 10) * 10; yr <= x1; yr += 10) decades.push(yr);
  const ticks = [x0, ...decades.filter((d) => d - x0 > 6 && Math.abs(d - goal.goalYear) > 6)];
  const gx = f.px(goal.goalYear), gy = f.py(goalMiles);
  const endX = f.px(last.year), endY = f.py(last.all_ages_miles);
  const AA = { x: "year", y: "miles", stroke: "var(--seq-3)", strokeWidth: 2.5, strokeLinejoin: "round", strokeLinecap: "round" };
  const INK = { fill: "var(--ink)" };
  const GOAL = { fill: "var(--seq-1)", fontWeight: 600, textAnchor: "start" };
  return plotSVG({
    ...f.options,
    marks: [
      ...yGrid(Array.from({ length: top / 100 + 1 }, (_, i) => i * 100), (v) => (v === top ? `${v} mi` : v)),
      Plot.ruleY([goalMiles], { stroke: "var(--seq-1)", strokeWidth: 1.5, strokeDasharray: "6 4" }),
      label(f, f.px(x1) + 8, gy - 6, "Plan's all-ages network", GOAL),
      label(f, f.px(x1) + 8, gy + 10, `${mi(goalMiles)} mi`, GOAL),
      // The pace carried forward, from today's figure to the goal.
      Plot.line([{ year: last.year, miles: last.all_ages_miles }, { year: goal.goalYear, miles: goalMiles }], { x: "year", y: "miles", stroke: "var(--seq-3)", strokeWidth: 2, strokeDasharray: "2 5", strokeOpacity: 0.8 }),
      // One solid line. The install-date-only years were dashed with a note until Bryan, 2026-10-09:
      // "doesn't really change how to read the chart that much."
      Plot.line(pts, AA),
      Plot.dot([pts[0], pts[pts.length - 1]], { x: "year", y: "miles", r: 4, fill: "var(--seq-3)" }),
      label(f, f.px(first.year) + 8, f.py(first.all_ages_miles) + 18, `${mi(first.all_ages_miles)} mi in ${first.year}`, { ...INK, fontSize: 12, textAnchor: "start" }),
      label(f, endX + 9, endY + 14, `${mi(last.all_ages_miles)} mi in ${last.year}`, { ...INK, fontWeight: 600, textAnchor: "start" }),
      Plot.dot([{ year: goal.goalYear, miles: goalMiles }], { x: "year", y: "miles", r: 5, fill: "var(--seq-1)" }),
      label(f, gx - 10, gy - 26, `${goal.goalYear} at the ${PACE_FROM + 1} to ${PACE_TO} pace, ${Math.round(pace)} mi a year`, { ...INK, ...HALO, fontSize: 11, textAnchor: "end", className: "note" }),
      xLabels(ticks, String),
      xLabels([goal.goalYear], String, { fill: "var(--seq-1)", fontWeight: 600 }),
    ],
  }, {
    className: "goal-chart",
    label: `Miles of all-ages bikeway, ${first.year} to ${last.year}, the ${PACE_FROM + 1} to ${PACE_TO} pace carried forward, and the ${mi(goalMiles)} miles the finished North Star network would total, reached in ${goal.goalYear}`,
  });
}

// Bryan, 2026-09-24: "one more section which shows the rate of improvement
// slowing down. Bar chart that shows net new miles added to all-ages network
// each year." Each bar is the year's all-ages miles less the year before's, so
// a removal shows as a smaller bar, not a separate one. The current year is
// year to date. One average, over every full year the bars show: splitting
// the years in two read as picking ranges to tell a story (Bryan, 2026-09-28:
// "the date ranges seem arbitrary").
const AVG_FROM = PACE_FROM, AVG_TO = PACE_TO, avgPace = pace;
// "2016–2025": the bars for those years, end of 2015 to end of 2025.
export const paceAverage = { from: AVG_FROM + 1, to: AVG_TO, miles: avgPace };

/** Net all-ages miles added each year, with the average over the full years. */
export function paceChart() {
  // Built bars, with SFMTA's work planned for the rest of the current year
  // stacked on its year-to-date bar, and a bar of planned work for each later
  // year SFMTA has projects for, all marked Planned (Bryan, 2026-10-09:
  // "include planned projects coming up", reversing 2026-09-29's "Don't
  // bother with 27-29"). Planned is a paler fill of the same ramp, with no outline
  // (Bryan, 2026-09-28: "I'm not sure what the borders mean"), and every bar
  // carries one total ("just show a total for every year").
  const plan = new Map(planned.rows.map((r) => [r.year, r.added_miles]));
  const bars = rows.slice(1).map((r, i) => ({ i, year: r.year, add: r.all_ages_miles - rows[i].all_ages_miles, plan: plan.get(r.year) || 0, partial: r.year === last.year }));
  for (const r of planned.rows) if (r.year > last.year) bars.push({ i: bars.length, year: r.year, add: 0, plan: r.added_miles, partial: false });
  // Ticks every ten miles. A year that lost more all-ages miles than it
  // gained draws below the axis (2022, when SFMTA dropped most pandemic Slow
  // Streets), so the scale runs below zero to the next ten.
  const STEP = 10;
  const top = Math.ceil(Math.max(...bars.map((b) => b.add + b.plan)) / STEP) * STEP;
  const lo = Math.min(0, Math.floor(Math.min(...bars.map((b) => b.add)) / STEP) * STEP);
  // x is the bar's index, so bar i is centred on i and the half-slot either
  // side is padding; each bar fills 62% of its slot.
  const W = 640, L = 96, R = 16;
  const f = frame({ width: W, height: 300, left: L, right: R, top: 34, bottom: 34, x: [-0.5, bars.length - 0.5], y: [lo, top] });
  const y = f.py;
  const slot = (W - L - R) / bars.length, bw = slot * 0.62, half = 0.31;
  const x = (i) => f.px(i) - bw / 2;
  const xi = (yr) => bars.findIndex((b) => b.year === yr);
  const pi = bars.findIndex((b) => b.plan > 0);
  const one = (v) => (Math.round(v * 10) / 10).toFixed(1);
  // A value label sits 5 above its bar (or 14 under a loss). Where that box
  // would cross the average's line, it goes just above the line instead.
  const yAvg = y(avgPace), inAvg = (b) => b.year >= AVG_FROM + 1 && b.year <= AVG_TO;
  const valY = (b) => {
    const tot = b.add + b.plan;
    if (Math.round(tot) < 0) return y(tot) + 14;
    const v = Math.min(y(tot), y(0)) - 5;
    return inAvg(b) && v - 11 <= yAvg + 1 && v + 3 >= yAvg - 1 ? yAvg - 4 : v;
  };
  // The average's label sits over the right end of its line (Bryan,
  // 2026-09-29: "Put the label right above the line"), ending where the line
  // ends and raised just clear of the value labels under it.
  const AVG_LABEL_W = 118;
  const avgX2 = x(xi(AVG_TO)) + bw + 3;
  const avgBase = Math.min(yAvg - 4, ...bars.filter((b, i) => x(i) < avgX2 && x(i) + bw > avgX2 - AVG_LABEL_W).map((b) => valY(b) - 12 - 4));
  const AVG = { fill: "var(--seq-3)", fontSize: 12, textAnchor: "end" };
  // Whole miles (Bryan, 2026-09-29: "round each label to the nearest mile"),
  // a loss with a true minus sign under its bar.
  const minus = (v) => (v < 0 ? `−${-v}` : String(v));
  // The Slow Streets: every Slow Street mile added in the year the program
  // began, kept and later dropped (history.json slow_street_all_ages_miles),
  // and the pandemic miles that left when SFMTA dropped them, each a label in
  // open space with a slanted leader to its bar (Bryan, 2026-09-29: "make the
  // callout a slanted line towards the bar"; "let's remove "pandemic" from the
  // label and just say total miles of slow streets added"; "Remove "pandemic"
  // from here too and just say "Slow Streets"").
  const callout = (i, text, tx, ty, toY) => {
    const bx = x(i) + bw + 2;
    return [
      Plot.link([0], { x1: () => f.X(tx - 3), y1: () => f.Y(ty - 4), x2: () => f.X(bx), y2: () => f.Y(toY), stroke: "var(--ink)", strokeWidth: 1, strokeDasharray: "3 2" }),
      label(f, tx, ty, text, { fill: "var(--ink)", fontSize: 12, textAnchor: "start" }),
    ];
  };
  const ak = rows.findIndex((r, k) => k && r.pandemic_slow_street_miles > 0 && !rows[k - 1].pandemic_slow_street_miles);
  const addRow = ak > 0 ? rows[ak] : null;
  const ssAdded = addRow ? addRow.slow_street_all_ages_miles - rows[ak - 1].slow_street_all_ages_miles : 0;
  const dropRow = rows.find((r) => r.pandemic_dropped_miles > 0);
  const ai = addRow ? xi(addRow.year) : -1, di = dropRow ? xi(dropRow.year) : -1;
  // Added: right of the bar, its baseline 30 below the bar's top (under the
  // bar's own value label), and raised if needed to stay clear of the value
  // labels of the bars it passes over.
  const added = ai < 0 ? [] : (() => {
    const tx = x(ai) + bw + 24, text = `Added ${Math.round(ssAdded)} mi of Slow Streets`;
    const over = bars.filter((b, i) => i > ai && x(i) < tx + 230);
    const ty = Math.min(y(bars[ai].add) + 30, ...over.map((b) => Math.min(valY(b) - 12, y(b.add + b.plan)) - 6), avgBase - 15 - 12 - 6);
    return callout(ai, text, tx, ty, Math.min(ty - 14, y(bars[ai].add) + 14));
  })();
  // Dropped: right of the loss, under the axis, where no bar reaches.
  // The figure is removed.json's, which the pipeline checks equals the bar's drop.
  const droppedMi = removed?.summary.slow_street_dropped_miles ?? dropRow?.pandemic_dropped_miles;
  const drop = di < 0 ? [] : callout(di, `Dropped ${Math.round(droppedMi)} mi of Slow Streets`,
    x(di) + bw + 24, (y(bars[di].add) + y(0)) / 2 + 22, (y(bars[di].add) + y(0)) / 2);
  const tickVals = [];
  for (let v = lo; v <= top; v += STEP) tickVals.push(v);
  return plotSVG({
    ...f.options,
    marks: [
      ...yGrid(tickVals, minus),
      // The axis title, three lines at the chart's top left.
      Plot.text([0], { frameAnchor: "top-left", dx: -L, dy: -6, text: () => "All-ages\nmiles added\neach year", textAnchor: "start", lineAnchor: "top", lineHeight: 14 / 12, fontSize: 12 }),
      Plot.ruleY([avgPace], { x1: xi(AVG_FROM + 1) - half - 3 / slot, x2: f.X(avgX2), stroke: "var(--seq-3)", strokeWidth: 2 }),
      label(f, avgX2, avgBase - 15, `${Math.round(avgPace)} mi a year`, { ...AVG, fontWeight: 600 }),
      label(f, avgX2, avgBase, `average, ${AVG_FROM + 1} to ${AVG_TO}`, AVG),
      Plot.rectY(bars.filter((b) => b.add), { x1: (b) => b.i - half, x2: (b) => b.i + half, y1: 0, y2: "add", fill: "var(--seq-2)" }),
      Plot.rectY(bars.filter((b) => b.plan), { x1: (b) => b.i - half, x2: (b) => b.i + half, y1: "add", y2: (b) => b.add + b.plan, fill: "var(--seq-2)", fillOpacity: 0.4 }),
      // Each bar's total, in whole miles.
      Plot.text(bars, { x: "i", y: (b) => f.Y(valY(b) - 0.32 * 12), text: (b) => minus(Math.round(b.add + b.plan)), fill: "var(--ink)", fontSize: 12 }),
      xLabels(bars.map((b) => b.i), (i) => (bars[i].partial ? String(bars[i].year) : `’${String(bars[i].year).slice(2)}`)),
      ...added,
      ...drop,
      // "Planned" centred over the bars that carry planned work, above their totals.
      pi < 0 ? null : label(f, f.px((pi + bars.length - 1) / 2), Math.min(...bars.slice(pi).map(valY)) - 16, "Planned", { fill: "var(--seq-3)", fontSize: 12, fontWeight: 600 }),
    ],
  }, {
    className: "pace-chart",
    label: `All-ages miles added each year, ${bars[0].year} to ${last.year}, with SFMTA's work planned through ${bars[bars.length - 1].year}: ${one(avgPace)} a year on average over ${AVG_FROM + 1} to ${AVG_TO}`,
  });
}

// Bryan, 2026-10-06, on the post's list of bikeway types: "Can we replace
// this with a bar chart with photos that shows how many miles (and what %) of
// the planned network are in each category? Bring up the content that used to
// be in the map below and put it here." And then: "Leave out the 'not all
// ages' and undecided parts -- so we don't have to explain them." So one row
// per kind of street the plan calls all-ages, most protected first, each with
// the explorer's photos and what the street is. Later the same day: "Too much
// detail. Remove the 'like the ???' and depend on having consistent labels on
// the photos", and "Just describe what the infra is", so each row and each
// photo carries the explorer card's own name and nothing names an example
// street. Then: "Split out Slow Streets. Bring back the badges (i.e. the one
// that said 3rd street, Page St)". The plan's Shared facility doesn't say
// which of its streets are Slow Streets, so a Shared block is counted as a
// Slow Street when it is one today (components.json, code S) and as an
// unprotected bikeway otherwise, including the Shared blocks with no bikeway
// yet. [inference — mine] Each photo of a real street carries that street's
// name as a badge; the painted lane is the explorer's drawing until a photo
// arrives, so it has none. Each "what" stays under ten words and one line
// (Bryan, 2026-10-07: "Under 10 words for each subtitle").
// Miles are the North Star blocks' per-direction metres (status.json, blocks
// [].m), summed by the plan's facility; the percentages are of those rows'
// total, the plan's all-ages network. Shared Level III and Undecided are left
// out of both.
export const PLAN_TYPES = [
  { id: "path", facilities: ["Shared-use Path", "Car-free"], name: "Off-street paths", photos: ["1"],
    what: "Paths and car-free streets", tone: "var(--seq-3)", text: "#ffffff" },
  { id: "sep", facilities: ["Separated"], name: "Separated lanes", photos: ["4"],
    what: "A barrier between bikes and cars", tone: "var(--seq-2)", text: "var(--ink)" },
  { id: "slow", facilities: ["Shared"], slow: true, name: "Slow Streets", photos: ["S"],
    what: "Signs that ask drivers to slow down", tone: "var(--seq-1)", text: "#ffffff" },
  { id: "shared", facilities: ["Shared"], slow: false, name: "Unprotected bikeways", photos: ["2", "3"],
    what: "Paint or signs, no barrier", tone: "var(--seq-1)", text: "#ffffff" },
];
// The street each photo shows, as its badge.
const PHOTO_STREET = { "1": "The Panhandle", "4": "3rd Street", S: "Page Street", "3": "The Wiggle" };
// A Shared block that is a Slow Street today.
const slowToday = (cnn) => { const c = components.blocks[String(cnn)]; return !!c && (c.s != null || "S" in c.m); };

export function planTypes() {
  const by = new Map();
  for (const b of planStatus.blocks) by.set(b.facility, (by.get(b.facility) || 0) + b.m / MILE);
  const rows = PLAN_TYPES.map((t) => {
    for (const f of t.facilities) if (!by.has(f)) throw new Error(`planTypes: no North Star blocks with facility "${f}"`);
    const miles = t.slow == null
      ? t.facilities.reduce((s, f) => s + by.get(f), 0)
      : planStatus.blocks.filter((b) => t.facilities.includes(b.facility) && slowToday(b.cnn) === t.slow).reduce((s, b) => s + b.m / MILE, 0);
    if (!(miles > 0)) throw new Error(`planTypes: row "${t.id}" has no miles`);
    return { ...t, miles };
  });
  const total = rows.reduce((s, r) => s + r.miles, 0);
  for (const r of rows) r.share = r.miles / total;
  const network = [...by.values()].reduce((s, m) => s + m, 0);
  return { rows, total, network };
}

/** The plan's all-ages network by kind of street: photos labelled with the explorer's card names, what each street is, and a bar with miles and share. */
export function planTypesChart() {
  const { rows, total } = planTypes();
  const max = Math.max(...rows.map((r) => r.miles));
  const pct = (s) => `${Math.round(s * 100)}%`;
  const card = (id) => CARDS.find((c) => c.id === id);
  // A row with one picture is labelled by its own name; a row with several
  // labels each picture with its card's short name. A photo of a real street
  // carries the street's name as a badge.
  const pic = (id, label) => {
    const inner = PHOTOS[id]
      ? `<img src="${PHOTO_DIR}/${PHOTOS[id].file}" loading="lazy" decoding="async" alt="${esc(PHOTOS[id].alt)}" width="240" height="160">`
      : glyph(id);
    const badge = PHOTOS[id] && PHOTO_STREET[id] ? `<span class="pt-badge">${esc(PHOTO_STREET[id])}</span>` : "";
    const name = card(id).name.replace(/^Unprotected bikeways: /, "");
    return `<figure class="pt-photo"><div class="pt-img">${inner}${badge}</div>${label ? `<figcaption>${esc(name[0].toUpperCase() + name.slice(1))}</figcaption>` : ""}</figure>`;
  };
  const row = (r) => {
    const w = (r.miles / max) * 100;
    // The figures sit on the bar when it has room for them, beside it otherwise.
    const inside = w > 34;
    const fig = `<b>${Math.round(r.miles)} mi</b> · ${pct(r.share)}`;
    return `<li class="pt-row">
    <div class="pt-photos pt-n${r.photos.length}">${r.photos.map((id) => pic(id, r.photos.length > 1)).join("")}</div>
    <div class="pt-text"><b class="pt-name">${esc(r.name)}</b><span class="pt-what">${esc(r.what)}</span></div>
    <div class="pt-track"><span class="pt-bar" style="width:${w.toFixed(1)}%;background:${r.tone};color:${r.text}">${inside ? `<span class="pt-fig">${fig}</span>` : ""}</span>${inside ? "" : `<span class="pt-fig pt-out">${fig}</span>`}</div>
  </li>`;
  };
  return `<figure class="plan-types" aria-label="${esc(`The plan's ${Math.round(total)}-mile all-ages network by kind of street: ${rows.map((r) => `${r.name}, ${Math.round(r.miles)} miles, ${pct(r.share)}`).join("; ")}`)}">
  <ol class="pt-rows">${rows.map(row).join("")}</ol>
  ${explorerCredits()}
</figure>`;
}

export const PLAN_TYPES_CSS = `<style>
.plan-types { margin: 0 0 8px; }
.pt-rows { list-style: none; margin: 0; padding: 0; }
.pt-row { display: grid; grid-template-columns: 172px minmax(170px, 240px) minmax(0, 1fr); gap: 6px 16px; align-items: center; padding: 10px 0; border-top: 1px solid var(--rule); }
.pt-row:last-child { border-bottom: 1px solid var(--rule); }
.pt-photos { display: grid; gap: 4px; grid-template-columns: repeat(2, 1fr); align-items: start; }
.pt-photos.pt-n1 { grid-template-columns: 1fr; }
.pt-photo { margin: 0; }
.pt-img { position: relative; }
.pt-badge { position: absolute; left: 4px; bottom: 4px; font-size: 0.68rem; line-height: 1.2; padding: 1px 4px; border-radius: 3px; background: rgba(255, 255, 255, 0.88); color: var(--ink); }
.pt-photo img, .pt-photo svg { display: block; width: 100%; height: 76px; object-fit: cover; border-radius: 4px; }
.pt-photo figcaption { font-size: 0.7rem; line-height: 1.2; margin-top: 3px; color: var(--ink); }
.pt-text { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.pt-name { font-size: 0.98rem; }
.pt-what { font-size: 0.86rem; color: var(--muted); }
.pt-track { display: flex; align-items: center; gap: 8px; min-width: 0; }
.pt-bar { display: flex; align-items: center; height: 34px; border-radius: 3px; flex: none; }
.pt-fig { font-size: 0.9rem; white-space: nowrap; padding: 0 10px; font-variant-numeric: tabular-nums; }
.pt-fig.pt-out { padding: 0; color: var(--ink); }
@media (max-width: 640px) {
  .pt-row { grid-template-columns: 128px minmax(0, 1fr); }
  .pt-badge { font-size: 0.6rem; white-space: nowrap; left: 2px; bottom: 2px; padding: 1px 3px; }
  .pt-photo img, .pt-photo svg { height: 64px; }
  .pt-track { grid-column: 1 / -1; }
}
</style>`;
