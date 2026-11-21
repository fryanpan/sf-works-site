// The school-hurt figures as blocks that stand on their own, for the board
// doc's `::sfworks{block="<name>"}` lines. Served at /embed/school/<block>/ by
// src/pages/embed-school.mjs.
//
// Bryan, 2026-10-21: "Use the maps we already have and make them nice!" The
// maps we already have are the "Main Streets Around Schools" mockup's street
// maps (OpenStreetMap streets, main streets dark, the grounds, the 500 ft zone
// and the quarter mile), so each school map here is that drawing as static SVG,
// with the kids hurt as dots coloured by how they were travelling. Static SVG
// also suits the board, whose frames are sandboxed and where Google refuses
// map tiles. And, on the ranking: "if you click on a school in the top 20 bar,
// it opens up the recent injury map from the last 10 years", since widened to
// the top 40.
//
// Same contract as the bike blocks (src/bike-blocks.mjs): one self-contained
// page per block, CSS, data and script inline, no storage or credentialed
// fetches, and a {type: "sfworks:height", block, height} message to the parent
// whenever the page's height changes, so the frame fits it.
//
// The data is site/data/school-hurt-maps.json, written by
// tools/school-trips/school-hurt-maps.py from DataSF nwes-mmgh, with the streets already
// projected into each map's viewBox.

import fs from "node:fs";
import nodePath from "node:path";
import { CSS, FONTS, ORIGIN } from "./layout.mjs";
import { MAP_HEAD, inlineJson } from "./maplibre.mjs";

const DATA = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "data", "school-hurt-maps.json"), "utf8"));
// The kids-hurt counts by distance from the nearest school, written by
// tools/school-trips/school-kids-hurt.py from the same DataSF table.
const KIDS = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "data", "school-kids-hurt.json"), "utf8"));

export const HURT_BLOCKS = [...DATA.four.map((s) => s.block), "school-hurt-four", "school-hurt-top40", "bikeways-20m", "school-zones-people"];

// How each kid was travelling. An unordered set, so Observable Plot's
// observable10 (Bryan, 2026-10-10), in the order he named them. Biking takes
// observable10's green rather than its red-orange: red is not a category.
export const MODES = [
  ["In a car", "#4269d0"],
  ["Walking", "#efb118"],
  ["Biking", "#3ca951"],
  ["Scooter or other", "#6cc5b0"],
];
const MODE_C = Object.fromEntries(MODES);

// The top 40's phases are ordered, so they take one sequential ramp, purples,
// which no travel-mode dot on the maps uses. Later is pale enough to fade into
// white, so its bars and key swatch carry a thin outline.
const PHASES = [
  ["first", "First phase", "#54278f", "one block from today's bikeways"],
  ["second", "Second phase", "#9e9ac8", "one block from the plan's network"],
  ["later", "Later", "#dadaeb", "farther"],
];
const LATER_EDGE = "#9e9ac8";
const PHASE_C = Object.fromEntries(PHASES.map(([k, , c]) => [k, c]));

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const SOURCE = `<a href="${DATA.source.url}">Traffic Crashes Resulting in Injury: Victims Involved</a>, DataSF`;
const MODEL = `<a href="${ORIGIN}/transportation/school-trips">School Trips model</a>`;

// The Main Streets mockup's palette.
const ST = { res: "#d3d8e0", main: "#5b6474", fwy: "#b9bfc9", grounds: "#9aa1ad", zone: "#4269d0", ring: "#8a93a3", label: "#3d4450" };

/** One school's map as SVG: the mockup's streets and areas, its main streets named, then one dot per kid hurt. */
function schoolSvg(m, label) {
  const V = DATA.view, u = m.ftPerUnit;
  const at = {};
  for (const r of m.rows) (at[`${r[0]},${r[1]}`] ||= []).push(r);
  // Kids hurt in one crash share a point; two or more are set a few units apart round it.
  const dots = [];
  for (const g of Object.values(at)) {
    g.forEach((r, i) => {
      const a = (2 * Math.PI * i) / g.length - Math.PI / 2, d = g.length > 1 ? 2.4 + 0.4 * g.length : 0;
      const x = V / 2 + ((r[0] - m.lon) * DATA.ftLon) / u + d * Math.cos(a), y = V / 2 - ((r[1] - m.lat) * DATA.ftLat) / u + d * Math.sin(a);
      dots.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="${MODE_C[r[2]]}"><title>${esc(r[2])}, ${r[3]}</title></circle>`);
    });
  }
  const lines = (k) => m.streets[k].map((d) => `<path d="${d}"/>`).join("");
  const names = m.labels.map((l) => `<text x="${l.x}" y="${l.y}" dy="0.35em" transform="rotate(${l.angle} ${l.x} ${l.y})">${esc(l.name)}</text>`).join("");
  return `<svg class="shm-svg" viewBox="0 0 ${V} ${V}" role="img" aria-label="${esc(label)}">
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
<path d="${m.zone}" fill="${ST.zone}" fill-opacity="0.08" stroke="${ST.zone}" stroke-opacity="0.7" stroke-width="1.1"/>
<g stroke="${ST.res}" stroke-width="1.4">${lines("res")}</g>
<g stroke="${ST.fwy}" stroke-width="4.2">${lines("fwy")}</g>
<g stroke="${ST.main}" stroke-width="4.2">${lines("main")}</g>
<path d="${m.grounds}" fill="${ST.grounds}" fill-opacity="0.6" stroke="none"/>
<path d="${m.quarter}" stroke="${ST.ring}" stroke-dasharray="4 4" stroke-width="1.2"/>
</g>
<g class="shm-names" fill="${ST.label}" stroke="#ffffff" stroke-width="2.6" stroke-linejoin="round" paint-order="stroke" text-anchor="middle" font-size="8.5" font-weight="600">${names}</g>
<g stroke="#ffffff" stroke-width="0.9">${dots.join("")}</g>
</svg>`;
}

/** The map's key, the same entries for every school: modes it has no kids for are greyed, with 0. */
function mapKey(m) {
  const byMode = m.byMode;
  return `<ul class="shm-key">${[
    ...MODES.map(([k, c]) => `<li${byMode[k] ? "" : ' class="none"'}><i class="dot" style="--c:${c}"></i>${esc(k)} <b>${byMode[k] || 0}</b></li>`),
    `<li><i class="sw" style="--c:${ST.main}"></i>Main street</li>`,
    `<li><i class="sw thin" style="--c:${ST.res}"></i>Residential street</li>`,
    `<li><i class="sw" style="--c:${ST.fwy}"></i>Freeway</li>`,
    `<li><i class="area" style="background:${ST.grounds};opacity:.6"></i>School grounds</li>`,
    `<li><i class="area" style="background:rgba(66,105,208,.1);border:1.5px solid ${ST.zone}"></i>School zone, ${DATA.zoneFt} ft</li>`,
    `<li><i class="ring"></i>Quarter mile</li>`,
  ].join("")}</ul>`;
}

const nYears = (years) => Number(years[1].slice(0, 4)) - Number(years[0].slice(0, 4)) + 1;

const hurtNote = (years) =>
  `<p class="shm-src">Kids 5 to 18 hurt on weekdays, 6 am to 6 pm, August to May, school years ${years[0]} to ${years[1]}, each counted at the nearest school's grounds. Streets from OpenStreetMap. Source: ${SOURCE}.</p>`;

const mapTitle = (name, m, years) =>
  `${name}: ${m.kids} kids hurt within a quarter mile in ${nYears(years)} school years (${years[0]} to ${years[1]})`;

const BLOCK_CSS = `
html, body { background: #ffffff; margin: 0; }
body { padding: 4px 12px 8px; }
.shm { margin: 0; }
.shm h2 { font-family: Archivo, sans-serif; font-size: 1.12rem; line-height: 1.3; margin: 0 0 8px; color: var(--ink); text-wrap: balance; max-width: 34em; }
.shm h3 { font-family: Archivo, sans-serif; font-size: 1rem; line-height: 1.3; margin: 0 0 6px; color: var(--ink); text-wrap: balance; }
.shm-svg { display: block; width: 100%; max-width: 560px; height: auto; border: 1px solid var(--rule); border-radius: 4px; background: #ffffff; }
.shm-svg .shm-names { font-family: "Public Sans", system-ui, sans-serif; }
.shm-key { list-style: none; display: flex; flex-wrap: wrap; gap: 3px 14px; margin: 8px 0 0; padding: 0; font-size: 0.84rem; color: var(--muted); max-width: 560px; }
.shm-key li { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.shm-key li.none { opacity: 0.4; }
.shm-key b { color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.shm-key .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--c); box-shadow: 0 0 0 1px #ffffff, 0 0 0 1.5px rgba(21,24,28,0.2); }
.shm-key .sw { width: 20px; height: 5px; border-radius: 3px; background: var(--c); }
.shm-key .sw.thin { height: 2.5px; }
.shm-key .area { width: 16px; height: 10px; border-radius: 2px; box-sizing: border-box; }
.shm-key .ring { width: 18px; border-top: 1.5px dashed ${ST.ring}; }
.shm-key .bar { width: 14px; height: 10px; border-radius: 2px; background: var(--c); }
.shm-src { margin: 6px 0 0; font-size: 0.78rem; line-height: 1.4; color: var(--muted); max-width: 560px; }
.shm-src a { color: inherit; }
.shm .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.shm-lede { margin: 0 0 6px; font-size: 0.9rem; color: var(--muted); max-width: 560px; }
`;

const heightScript = (name) => `<script>
(function () {
  function send() {
    try { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: document.documentElement.scrollHeight }, "*"); } catch (e) {}
  }
  window.sfworksHeight = send;
  send();
  window.addEventListener("load", send);
  if (window.ResizeObserver) new ResizeObserver(send).observe(document.documentElement);
})();
</script>`;

function page(name, title, body, script = "", extra = {}) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)} — SF Works</title>
<link rel="canonical" href="${ORIGIN}/transportation/school-trips">
<base target="_blank">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
<style>${BLOCK_CSS}${extra.css || ""}</style>
${extra.head || ""}
</head>
<body>
<figure class="shm${extra.cls ? " " + extra.cls : ""}" data-block="${name}">
${body}
</figure>
${script}
${heightScript(name)}
</body>
</html>
`;
}

function oneSchool(s) {
  const t = mapTitle(s.title, s, DATA.years4);
  return page(s.block, t, `<h2>${esc(t)}</h2>
${schoolSvg(s, `Map of the streets round ${s.title} and the ${s.kids} kids hurt within a quarter mile of its grounds`)}
${mapKey(s)}
${hurtNote(DATA.years4)}`);
}

// ---- The top 40 ------------------------------------------------------------
//
// Bryan, 2026-10-21, on the first version: "Make the whole thing more compact so
// the list fits on screen and map fits on screen. Please use the standard Google
// maps base map approach. Use a different color scheme on the map instead of
// using the same colors as on the left." So each school is one short row, and
// the one map is sfMap (src/maplibre.mjs) over Google's monochrome tiles, its
// kids in MAP_MODES rather than the list's purples. A board frame is sandboxed
// and sends no referrer, so there the map falls back to OpenFreeMap.

// How each kid was travelling, on this map: an unordered set, so observable10
// colours again, but none of its blues or purples, which the list's phases use.
const MAP_MODES = [
  ["In a car", "#efb118"],
  ["Walking", "#6cc5b0"],
  ["Biking", "#3ca951"],
  ["Scooter or other", "#9c6b4e"],
];
const MAP_ST = { zone: "#3d4450", ring: "#5b6474", grounds: "#5b6474" };

/** A map's SVG path (M, L and Z in viewBox units) back to longitude and latitude rings. */
function rings(d, m) {
  const V = DATA.view, u = m.ftPerUnit;
  return d.split("M").filter((x) => x.trim()).map((sub) => {
    const pts = sub.replace(/Z/g, "").split("L").map((xy) => xy.split(",").map(Number));
    const ring = pts.map(([x, y]) => [+(m.lon + ((x - V / 2) * u) / DATA.ftLon).toFixed(6), +(m.lat - ((y - V / 2) * u) / DATA.ftLat).toFixed(6)]);
    if (ring.length > 2) ring.push(ring[0]);
    return ring;
  });
}

/** Kids hurt in one crash share a point, so two or more are set round it, a few feet apart, as on the static maps. */
function spread(rows) {
  const at = {};
  for (const r of rows) (at[`${r[0]},${r[1]}`] ||= []).push(r);
  return Object.values(at).flatMap((g) => g.map((r, i) => {
    const a = (2 * Math.PI * i) / g.length - Math.PI / 2, ft = g.length > 1 ? 14 + 3 * g.length : 0;
    return [r, +(r[0] + (ft * Math.cos(a)) / DATA.ftLon).toFixed(6), +(r[1] - (ft * Math.sin(a)) / DATA.ftLat).toFixed(6)];
  }));
}

const TOP_CSS = `
.shm-top .shm-key { margin: 6px 0 0; }
.shm-two { margin-top: 8px; }
.shm-rows { margin: 0; padding: 0; list-style: none; }
.shm-row { display: grid; grid-template-columns: minmax(0, 1fr) 86px; align-items: center; gap: 6px; width: 100%; height: 20px; box-sizing: border-box; padding: 0 4px; margin: 0; border: 0; border-radius: 3px; background: none; text-align: left; font: inherit; font-size: 0.8rem; line-height: 20px; color: var(--ink); cursor: pointer; }
.shm-row:hover { background: var(--raised); }
.shm-row:focus-visible { outline: 2px solid var(--seq-3); outline-offset: -2px; }
.shm-row[aria-expanded="true"] { background: var(--raised); font-weight: 700; }
.shm-row .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shm-row .bar { display: flex; align-items: center; gap: 4px; font-variant-numeric: tabular-nums; font-weight: 600; }
.shm-row .bar i { display: block; height: 11px; border-radius: 2px; }
.shm-panel h3 { font-size: 0.92rem; margin: 0 0 4px; }
.shm-panel .glmap { height: 420px; border: 1px solid var(--rule); }
.shm-panel .shm-key { font-size: 0.78rem; gap: 2px 12px; }
/* A frame the width of a board doc: the list in two columns of 20, the map under it. */
@media (min-width: 560px) {
  .shm-rows { columns: 2; column-gap: 16px; }
  .shm-rows li { break-inside: avoid; }
  .shm-panel { margin-top: 10px; }
}
/* A wide frame: the two columns of 20 beside a map as tall as them. */
@media (min-width: 1000px) {
  .shm-two { display: grid; grid-template-columns: minmax(0, 620px) minmax(0, 1fr); gap: 0 24px; align-items: start; }
  .shm-panel { margin-top: 0; }
  .shm-panel .glmap { height: 400px; }
}
/* A phone: the map opens under the tapped row, and rows are a thumb's height. */
@media (max-width: 559px) {
  .shm-row { height: 32px; line-height: 32px; }
  .shm-panel { padding: 6px 0 12px; }
  .shm-panel .glmap { height: 320px; }
}
`;

const MAP_SCRIPT = `<script>
(function () {
  var T = JSON.parse(document.getElementById("shm-data").textContent);
  var q = function (s) { return [].slice.call(document.querySelectorAll(s)); };
  var rows = q("[data-pick]"), panel = document.querySelector(".shm-panel"), two = document.querySelector(".shm-two");
  var title = panel.querySelector("h3"), counts = q(".shm-panel [data-mode]");
  var narrow = window.matchMedia("(max-width: 559px)"), at = 0, map = null;
  function bbox(rs) {
    var b = [[180, 90], [-180, -90]];
    rs.forEach(function (r) { r.forEach(function (p) { b[0][0] = Math.min(b[0][0], p[0]); b[0][1] = Math.min(b[0][1], p[1]); b[1][0] = Math.max(b[1][0], p[0]); b[1][1] = Math.max(b[1][1], p[1]); }); });
    return b;
  }
  function poly(rs) { return { type: "FeatureCollection", features: rs.map(function (r) { return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [r] } }; }) }; }
  function line(rs) { return { type: "FeatureCollection", features: rs.map(function (r) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r } }; }) }; }
  function kids(s) { return { type: "FeatureCollection", features: s.k.map(function (k) { return { type: "Feature", properties: { c: T.colors[k[2]] }, geometry: { type: "Point", coordinates: [k[0], k[1]] } }; }) }; }
  function draw() {
    var s = T.schools[at];
    if (!map || !map.getSource("zone")) return;
    map.getSource("zone").setData(poly(s.z));
    map.getSource("grounds").setData(poly(s.g));
    map.getSource("quarter").setData(line(s.q));
    map.getSource("kids").setData(kids(s));
    map.fitBounds(bbox(s.q), { padding: 16, duration: 0 });
  }
  function place() {
    var row = rows[at];
    if (!T.move) { if (map) map.resize(); if (window.sfworksHeight) window.sfworksHeight(); return; }
    if (narrow.matches) { if (row.parentNode.nextElementSibling !== panel) row.parentNode.after(panel); }
    else if (panel.parentNode !== two || panel.previousElementSibling !== two.firstElementChild) two.appendChild(panel);
    if (map) map.resize();
    if (window.sfworksHeight) window.sfworksHeight();
  }
  function show(i, write) {
    at = i;
    var s = T.schools[i];
    rows.forEach(function (r, j) { r.setAttribute(T.move ? "aria-expanded" : "aria-pressed", String(j === i)); });
    title.textContent = s.t;
    counts.forEach(function (c) { var n = s.m[c.getAttribute("data-mode")] || 0; c.querySelector("b").textContent = n; c.classList.toggle("none", !n); });
    place();
    draw();
    if (write) {
      var h = "#school=" + s.cds;
      try { history.replaceState(null, "", h); } catch (e) { try { location.hash = h; } catch (e2) {} }
    }
  }
  rows.forEach(function (r, i) { r.addEventListener("click", function () { show(i, true); }); });
  if (narrow.addEventListener) narrow.addEventListener("change", place);
  var m = /school=(\\d+)/.exec(location.hash || ""), first = 0;
  if (m) T.schools.forEach(function (s, i) { if (s.cds === m[1]) first = i; });
  show(first, false);
  map = window.sfMap && sfMap.create(panel.querySelector(".glmap"), { bounds: bbox(T.schools[first].q), padding: function () { return 16; }, maxZoom: 18, onReset: draw });
  if (!map) return;
  map.on("load", function () {
    var b = sfMap.under(map);
    ["zone", "grounds", "quarter", "kids"].forEach(function (id) { map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } }); });
    map.addLayer({ id: "zone", type: "fill", source: "zone", paint: { "fill-color": T.st.zone, "fill-opacity": 0.07 } }, b);
    map.addLayer({ id: "zone-edge", type: "line", source: "zone", paint: { "line-color": T.st.zone, "line-width": 1.4 } }, b);
    map.addLayer({ id: "grounds", type: "fill", source: "grounds", paint: { "fill-color": T.st.grounds, "fill-opacity": 0.35 } }, b);
    map.addLayer({ id: "quarter", type: "line", source: "quarter", paint: { "line-color": T.st.ring, "line-width": 1.4, "line-dasharray": [3, 3] } }, b);
    map.addLayer({ id: "kids", type: "circle", source: "kids", paint: { "circle-color": ["get", "c"], "circle-radius": 5, "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.2 } });
    draw();
  });
})();
</script>`;

/** The map panel's data: per school its title, mode counts, rings in longitude and latitude, and kids. */
function mapData(list, move) {
  const modeIx = Object.fromEntries(MAP_MODES.map(([k], i) => [k, i]));
  return {
    colors: MAP_MODES.map(([, c]) => c), st: MAP_ST, move,
    schools: list.map(({ cds, t, map: m }) => ({
      cds, t, m: m.byMode,
      z: rings(m.zone, m), g: rings(m.grounds, m), q: rings(m.quarter, m),
      k: spread(m.rows).map(([k, lon, lat]) => [lon, lat, modeIx[k[2]]]),
    })),
  };
}

const MAP_KEY = `<ul class="shm-key">${[
  ...MAP_MODES.map(([k, c]) => `<li data-mode="${esc(k)}"><i class="dot" style="--c:${c}"></i>${esc(k)} <b>0</b></li>`),
  `<li><i class="area" style="background:${MAP_ST.grounds};opacity:.35"></i>School grounds</li>`,
  `<li><i class="area" style="background:rgba(61,68,80,.07);border:1.5px solid ${MAP_ST.zone}"></i>School zone, ${DATA.zoneFt} ft</li>`,
  `<li><i class="ring" style="border-top-color:${MAP_ST.ring}"></i>Quarter mile</li>`,
].join("")}</ul>`;

// ---- The four schools, one map ------------------------------------------------
//
// Bryan, 2026-10-21, on the four separate maps: "Please make these maps much
// smaller (take up half the screen on laptop or mobile, with the colors
// consistent with coloring later in the doc, and have an interactive way to
// toggle between four schools. Use Google Maps base layer so the streets are
// more readable." So one sfMap about half a screen tall, four buttons above it,
// and the top 40 map's colours.

const FOUR_CSS = `
.shm-four { max-width: 640px; }
.shm-picks { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; }
.shm-pick { min-height: 36px; padding: 4px 12px; border: 1px solid var(--rule); border-radius: 18px; background: #ffffff; font: inherit; font-size: 0.85rem; color: var(--ink); cursor: pointer; }
.shm-pick:hover { background: var(--raised); }
.shm-pick[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: #ffffff; font-weight: 600; }
.shm-pick:focus-visible { outline: 2px solid var(--seq-3); outline-offset: 2px; }
.shm-four .shm-panel h3 { font-size: 0.92rem; margin: 0 0 4px; }
.shm-four .glmap { height: 300px; border: 1px solid var(--rule); }
.shm-four .shm-key { font-size: 0.78rem; gap: 2px 12px; margin-top: 6px; }
@media (max-width: 559px) { .shm-four .glmap { height: 260px; } }
`;

// Button labels, short enough that the four fit on one row; the map title names the school in full.
const SHORT = { "Balboa High": "Balboa", "Charles Drew College Prep": "Drew", "Bessie Carmichael/FEC": "Carmichael", "KIPP Bayview Academy": "KIPP Bayview", "Abraham Lincoln High": "Lincoln", "Marshall Elementary": "Marshall" };

function fourBlock() {
  const list = DATA.four;
  const title = "Where kids get hurt near the four schools with the most";
  const picks = list.map((s) => `<button type="button" class="shm-pick" data-pick aria-pressed="false" aria-controls="shm-panel">${esc(SHORT[s.title] || s.title)}<span class="sr"> (${esc(s.title)}), ${s.kids} kids</span></button>`).join("");
  const data = mapData(list.map((s) => ({ cds: s.cds, t: mapTitle(s.title, s, DATA.years4), map: s })), false);
  return page("school-hurt-four", title, `<div class="shm-picks" role="group" aria-label="Pick a school">${picks}</div>
<div class="shm-panel" id="shm-panel" role="region" aria-live="polite" aria-label="Map of the school picked">
<h3></h3>
<div class="glmap"></div>
${MAP_KEY}
</div>
<p class="shm-src">Kids 5 to 18 hurt on weekdays, 6 am to 6 pm, August to May, school years ${DATA.years4[0]} to ${DATA.years4[1]}, each counted at the nearest school's grounds. Source: ${SOURCE}.</p>
<script type="application/json" id="shm-data">${inlineJson(data)}</script>`, MAP_SCRIPT, { head: MAP_HEAD, css: FOUR_CSS, cls: "shm-four" });
}

function topBlock() {
  const T = DATA.top40, rows = T.schools;
  const waiting = rows.filter((r) => r.phase !== "first").length;
  const title = `${waiting} of the ${rows.length} schools where the most kids get hurt wait past the first phase`;
  const key = `<ul class="shm-key">${PHASES.map(([, l, c, what]) => `<li><i class="bar" style="--c:${c}${c === PHASE_C.later ? `;box-shadow:inset 0 0 0 1px ${LATER_EDGE}` : ""}"></i>${l}: ${what}</li>`).join("")}</ul>`;
  const max = Math.max(...rows.map((r) => r.kids));
  const bar = (r) => `<span class="bar"><i style="width:${((60 * r.kids) / max).toFixed(1)}px;background:${PHASE_C[r.phase]}${r.phase === "later" ? `;box-shadow:inset 0 0 0 1px ${LATER_EDGE}` : ""}"></i>${r.kids}</span>`;
  const list = rows.map((r) => `<li><button type="button" class="shm-row" data-pick aria-expanded="false" aria-controls="shm-panel"><span class="lbl">${r.rank}. ${esc(r.name)}<span class="sr">, ${r.kids} kids, ${PHASES.find((p) => p[0] === r.phase)[1]}</span></span>${bar(r)}</button></li>`).join("\n");
  const data = mapData(rows.map((r) => ({ cds: r.cds, t: mapTitle(r.name, r.map, DATA.years10), map: r.map })), true);
  const last = rows[rows.length - 1].kids;
  return page("school-hurt-top40", title, `<h2>${esc(title)}</h2>
<p class="shm-lede">Kids hurt within a quarter mile of each school in 10 school years. Tap a school to see its map.</p>
${key}
<div class="shm-two">
<ol class="shm-rows">
${list}
</ol>
<div class="shm-panel" id="shm-panel" role="region" aria-live="polite" aria-label="Map of the school picked">
<h3></h3>
<div class="glmap"></div>
${MAP_KEY}
</div>
</div>
<p class="shm-src">Kids 5 to 18 hurt on weekdays, 6 am to 6 pm, August to May, school years ${DATA.years10[0]} to ${DATA.years10[1]}, each counted at the nearest school's grounds. Phases from our ${MODEL}.${T.tiedPast ? ` ${T.tiedPast} more schools also had ${last}; ties are listed by name.` : ""} Source: ${SOURCE}.</p>
<script type="application/json" id="shm-data">${inlineJson(data)}</script>`, MAP_SCRIPT, { head: MAP_HEAD, css: TOP_CSS, cls: "shm-top" });
}

// ---- The $20M bikeway set ----------------------------------------------------
//
// Bryan, 2026-10-21, on the static city drawing: "Map is blank". It had land
// and lines but no streets, so it moves onto the standard map like the school
// maps. tools/school-trips/school-hurt-maps.py projects the lines into a 600-wide viewBox
// over this box; they are turned back into longitude and latitude here.

const BIKE_TITLE = "$20M of bikeways: about 12,000 students with a safe route, up from about 4,600";
const BIKE_BOX = { W: -122.5155, E: -122.3555, S: 37.7065, N: 37.8335 };

function bikeBlock() {
  const B = DATA.bikeways;
  const NEW = "#4269d0", TODAY = "#7d8590";
  const k = Math.cos((37.76 * Math.PI) / 180), sc = B.width / ((BIKE_BOX.E - BIKE_BOX.W) * k);
  const ll = ([x, y]) => [+(BIKE_BOX.W + x / (k * sc)).toFixed(5), +(BIKE_BOX.N - y / sc).toFixed(5)];
  const lines = (ds) => ds.flatMap((d) => d.split("M").filter((t) => t.trim()).map((t) => t.split("L").map((xy) => ll(xy.split(",").map(Number)))));
  const data = { today: lines(B.today), picked: lines(B.picked), schools: B.schools.map(ll), c: { today: TODAY, picked: NEW } };
  const key = `<ul class="shm-key">
<li><i class="sw" style="--c:${NEW}"></i>Added for $${B.budgetM}M, <b>${B.centerlineMi}</b> miles</li>
<li><i class="sw" style="--c:${TODAY};height:3px"></i>All-ages bikeways today</li>
<li><i class="dot" style="--c:#15181c"></i>School</li>
</ul>`;
  const script = `<script>
(function () {
  var D = JSON.parse(document.getElementById("shm-bike").textContent);
  var map = window.sfMap && sfMap.create(document.querySelector(".glmap"), { bounds: [[-122.515, 37.708], [-122.357, 37.812]], padding: function () { return 6; } });
  if (!map) return;
  function fc(ls) { return { type: "FeatureCollection", features: ls.map(function (c) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: c } }; }) }; }
  map.on("load", function () {
    var u = sfMap.under(map);
    map.addSource("today", { type: "geojson", data: fc(D.today) });
    map.addSource("picked", { type: "geojson", data: fc(D.picked) });
    map.addSource("schools", { type: "geojson", data: { type: "FeatureCollection", features: D.schools.map(function (p) { return { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: p } }; }) } });
    map.addLayer({ id: "today", type: "line", source: "today", paint: { "line-color": D.c.today, "line-width": 1.6 }, layout: { "line-cap": "round" } }, u);
    map.addLayer({ id: "picked", type: "line", source: "picked", paint: { "line-color": D.c.picked, "line-width": 3 }, layout: { "line-cap": "round" } }, u);
    map.addLayer({ id: "schools", type: "circle", source: "schools", paint: { "circle-color": "#15181c", "circle-radius": 2.8, "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.8 } });
  });
})();
</script>`;
  return page("bikeways-20m", BIKE_TITLE, `<h2>${esc(BIKE_TITLE)}</h2>
<div class="glmap"></div>
${key}
<p class="shm-src">A safe route is a walk or bike trip of 15 minutes or less with at most 1,000 ft in all off all-ages streets. Stretches picked by our ${MODEL}. Bikeways today from <a href="${B.sources.network}">SFMTA's bikeway layer</a>.</p>
<script type="application/json" id="shm-bike">${inlineJson(data)}</script>`, script, { head: MAP_HEAD, css: BIKE_CSS, cls: "shm-bike" });
}

const BIKE_CSS = `
.shm-bike { max-width: 640px; }
.shm-bike .glmap { height: 420px; border: 1px solid var(--rule); }
@media (max-width: 559px) { .shm-bike .glmap { height: 340px; } }
`;

// ---- Kids hurt by distance from the school, as people ----------------------
//
// Bryan, 2026-10-21, on the bar chart "Most kids are hurt beyond the school
// zone": "A bar chart seems kind of abstract. Instead, can we use icons to
// represent people and show a simplified diagram of a school and school zones
// around it. And then show grids of how many people get injured in each zone".
// So a school inside three nested rounded rings, one child icon per
// kid hurt a year in each ring (layout below, at ZONES_CSS).
//
// The counts are byDistance.rows: four school years, so a year is n / years.
// Shares are of the kids with a location (the rows' sum, model.base); the few
// with no location (byDistance.noLocation) are in no ring, as on the chart.

// The grey kids are a mid grey, so they keep 3:1 contrast on the rings' pale fills.
const ZONE_C = "#4269d0", FAR_C = "#8a919b", FAR_EDGE = "#c9ccd3";
const ZONE_LABELS = ["School zone (500 ft), where SFMTA's plan acts", "500 ft to a quarter mile", "Farther than a quarter mile"];

// A child, not an adult: the head about a third of the height, short legs, and
// a backpack on the back (Bryan, 2026-10-21: "make also the icons look more
// like kids? they look kind like adults").
const KID = `<svg class="szp-k" viewBox="0 0 12 16" aria-hidden="true"><use href="#szp-kid"/></svg>`;
const DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="szp-kid" viewBox="0 0 12 16"><rect x="6.6" y="8.2" width="3.6" height="4.2" rx="1.3"/><circle cx="4.8" cy="3.8" r="3.6"/><path d="M2 12.6V10.4A2.3 2.3 0 0 1 4.3 8.1h1A2.3 2.3 0 0 1 7.6 10.4v2.2z"/><rect x="2.4" y="12" width="2" height="4" rx="1"/><rect x="5.2" y="12" width="2" height="4" rx="1"/></symbol>
</defs></svg>`;
const SCHOOL = `<svg class="szp-school" viewBox="0 0 64 52" role="img" aria-label="A school">
<path d="M32 2v9" stroke="#3d4450" stroke-width="1.6"/><path d="M32 2h8l-2 2.5 2 2.5h-8z" fill="${ZONE_C}"/>
<path d="M6 24L32 11l26 13z" fill="#3d4450"/>
<rect x="9" y="24" width="46" height="25" fill="#ffffff" stroke="#3d4450" stroke-width="2"/>
<rect x="28" y="34" width="8" height="15" fill="#3d4450"/>
<rect x="14" y="29" width="8" height="7" fill="#c9d4f0" stroke="#3d4450" stroke-width="1.2"/><rect x="42" y="29" width="8" height="7" fill="#c9d4f0" stroke="#3d4450" stroke-width="1.2"/>
<path d="M2 49.5h60" stroke="#3d4450" stroke-width="2"/>
</svg>`;

// Bryan, 2026-10-21: "Show simplified street grid too -- you can use the
// street grid from some high injury school in SF". So under the rings sit the
// streets round Balboa High, the school with the most kids hurt in this window,
// from the lines tools/school-trips/school-hurt-maps.py cut for its map. Each line is
// generalized to straight segments (Douglas-Peucker, GRID_TOL viewBox units)
// at build time, so the page carries a few hundred points and the same ones
// on every build. Main streets and freeways are heavier, residential lighter,
// both pale greys that sit under the kids.
const GRID_SCHOOL = "Balboa High", GRID_TOL = 2.5;

/** Douglas-Peucker: the fewest points that keep a line within tol of the original. */
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const [a, b] = [pts[0], pts[pts.length - 1]], dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
  let far = 0, at = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs(dy * pts[i][0] - dx * pts[i][1] + b[0] * a[1] - b[1] * a[0]) / len;
    if (d > far) { far = d; at = i; }
  }
  if (far <= tol) return [a, b];
  return [...simplify(pts.slice(0, at + 1), tol).slice(0, -1), ...simplify(pts.slice(at), tol)];
}

/** One school's streets of a kind as one simplified path, rounded to whole units. */
function gridPath(m, kinds) {
  return kinds.flatMap((k) => m.streets[k]).flatMap((d) => d.split("M").filter((t) => t.trim()).map((t) => t.split("L").map((xy) => xy.split(",").map(Number))))
    .map((pts) => simplify(pts, GRID_TOL).map(([x, y]) => [Math.round(x), Math.round(y)]))
    .filter((pts) => pts.length > 1 && !(pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1] && pts.length === 2))
    .map((pts) => "M" + pts.map((p) => p.join(",")).join("L")).join("");
}

function streetGrid() {
  const m = DATA.four.find((x) => x.title === GRID_SCHOOL);
  if (!m) throw new Error(`school-zones-people: no "${GRID_SCHOOL}" in school-hurt-maps.json`);
  const V = DATA.view;
  // slice fills the diagram whatever its shape and crops the rest; the school sits at the middle of the view.
  return `<svg class="szp-streets" viewBox="0 0 ${V} ${V}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
<path d="${gridPath(m, ["res"])}" stroke="#e3e6ea" stroke-width="1.4" vector-effect="non-scaling-stroke"/>
<path d="${gridPath(m, ["main", "fwy"])}" stroke="#d3d7de" stroke-width="3.5" vector-effect="non-scaling-stroke"/>
</g>
</svg>`;
}
const STREETS = streetGrid();

/** The three rings' figures, from byDistance. Throws if the data no longer says what the title says. */
export function zoneRows(d = KIDS.byDistance) {
  if (d.rows.length !== 3) throw new Error(`school-zones-people: expected 3 distance bands, got ${d.rows.length}`);
  const total = d.rows.reduce((t, r) => t + r.n, 0);
  if (KIDS.model?.base !== total) throw new Error(`school-zones-people: bands sum to ${total}, model.base is ${KIDS.model.base}`);
  const rows = d.rows.map((r, i) => ({ label: ZONE_LABELS[i], n: r.n, perYear: Math.round(r.n / d.years), pct: Math.round((100 * r.n) / total) }));
  if (rows[0].n * 2 >= total) throw new Error("school-zones-people: the school zone now holds half the kids or more, so the title is wrong");
  return { rows, total, years: d.years, noLocation: d.noLocation };
}

function zonesBlock() {
  const Z = zoneRows();
  const title = "Most kids are hurt beyond the school zone";
  const years = (KIDS.byDistance.what.match(/(\d{4}-\d{2}) to (\d{4}-\d{2})/) || []).slice(1);
  if (years.length !== 2) throw new Error("school-zones-people: no school years in byDistance.what");
  // Innermost first: each ring holds the one inside it, then its own kids as one block, label above.
  let inner = SCHOOL;
  Z.rows.forEach((r, i) => {
    const c = i === 0 ? ZONE_C : FAR_C;
    inner = `<div class="szp-ring szp-r${i}" role="group" aria-label="${esc(r.label)}: ${r.perYear} kids hurt a year, ${r.pct}%">
<div class="szp-in">${inner}</div>
<div class="szp-blk"><p class="szp-lab"><b>${r.perYear} a year</b> <span>(${r.pct}%)</span><br>${esc(r.label).replace(/(\d+) ft/g, "$1&nbsp;ft")}</p>
<span class="szp-g" style="color:${c}">${KID.repeat(r.perYear)}</span></div>
</div>`;
  });
  return page("school-zones-people", title, `<h2>${esc(title)}</h2>
${DEFS}
<div class="szp">${STREETS}${inner}</div>
<p class="shm-src">Each figure is one kid 5 to 18 hurt in traffic a year, school-year weekdays 6 am to 6 pm, ${years[0]} to ${years[1]}.</p>`, "", { css: ZONES_CSS, cls: "shm-zones" });
}

// Bryan, 2026-10-21: "arrange things so all of the people in each region are
// in one contiguous block instead of split across two sides -- that makes
// comparison hard". Wide: the school at the left, the rings nested and opening
// to the right, each ring's kids one block to the right of the ring it holds.
// Every block is ROWS kids tall, so its width is in proportion to its count.
// Narrow: the same rings stacked, the school at the top, 11 kids to a row.
const ROWS = 3;
const ZONES_CSS = `
.shm-zones { max-width: 720px; }
.szp { position: relative; width: fit-content; max-width: 100%; overflow: hidden; border-radius: 18px; font-size: 0.82rem; line-height: 1.3; color: var(--ink); }
.szp-streets { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 18px; }
.szp-ring { display: flex; align-items: center; gap: 12px; padding: 8px 12px 8px 8px; border-radius: 18px; border: 1.5px solid ${FAR_EDGE}; background: rgba(255, 255, 255, 0.5); position: relative; }
.szp-r1 { background: rgba(240, 242, 245, 0.55); }
.szp-r0 { border-color: ${ZONE_C}; background: rgba(232, 238, 250, 0.8); }
.szp-in { display: flex; align-items: center; }
/* Every block the same height, label bottom-aligned over its kids, so the three grids share their row lines. */
.szp-blk { display: grid; grid-template-rows: 5.4em auto; gap: 6px; width: min-content; }
.szp-blk .szp-lab { align-self: end; }
.szp-lab { min-width: 7em; }
.szp-lab { margin: 0; color: var(--muted); text-shadow: 0 0 3px #ffffff, 0 0 3px #ffffff, 0 0 2px #ffffff; }
.szp-lab b { color: var(--ink); font-size: 1rem; font-variant-numeric: tabular-nums; }
.szp-r0 .szp-lab b { color: ${ZONE_C}; }
.szp-g { display: grid; grid-template-rows: repeat(${ROWS}, 17px); grid-auto-flow: column; grid-auto-columns: 13px; gap: 4px 2px; justify-content: start; }
.szp-k { width: 13px; height: 17px; display: block; fill: currentColor; }
.szp-school { display: block; width: 52px; height: auto; }
@media (max-width: 699px) {
  /* One grid per ring, 11 kids to a row in every ring, so the rings compare by their rows. */
  .szp { width: auto; border-radius: 14px; }
  .szp-ring { flex-direction: column; align-items: stretch; gap: 6px; padding: 8px 8px 10px; border-radius: 14px; }
  .szp-in, .szp-r0 > .szp-in { justify-content: center; align-self: stretch; }
  .szp-blk { width: auto; grid-template-rows: auto auto; }
  .szp-lab { text-align: center; }
  .szp-g { grid-template-rows: none; grid-auto-flow: row; grid-template-columns: repeat(11, 18px); gap: 5px 4px; justify-content: center; }
  .szp-k { width: 18px; height: 24px; }
}
`;

/** The standalone page for one block, at /embed/school/<name>/. */
export function embedPage(name) {
  if (name === "school-hurt-four") return fourBlock();
  if (name === "school-hurt-top40") return topBlock();
  if (name === "bikeways-20m") return bikeBlock();
  if (name === "school-zones-people") return zonesBlock();
  const s = DATA.four.find((x) => x.block === name);
  if (!s) throw new Error(`school-hurt-blocks: no block named "${name}"`);
  return oneSchool(s);
}
