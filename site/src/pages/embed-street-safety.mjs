// The Street Safety map as standalone figures for a board doc, one per named state: /embed/street-safety/<block>/,
// also at /embed/bike/<block>/ because the board maps its one `sfworks` directive to /embed/bike/{block}/ (see
// src/pages/embed-injuries.mjs). Each is the map with its key and corner chart and no filter panel, so it reads with
// no control touched; a reader can still click the chart's bars, and a link opens the full map in the same state.
//
// Bryan, 2026-11-19, on Part 1.2: the HIN in 10-mile groups worst
// to best, stepping through the worst four groups of 2022 to 2024 with the group chart, and each year's worst 10 miles
// from 2020 to 2025. Kept out of the sitemap and marked noindex.

import { FONTS, CSS } from "../layout.mjs";
import { MAP_HEAD } from "../maplibre.mjs";
import { SCRIPT, CSS as MAP_CSS, KIT_HEAD, DATA_URL, CRASHES_URL, CHART_SCRIPT, inlineData, STATE } from "../safety-map/index.mjs";

export const path = "/embed/street-safety";
export const file = "embed/street-safety/index.html";
export const asset = true;
export const sitemap = false;

const groups = { hin: ["groups"], rank: "2022-2024", chart: { id: "by-hin-group" }, filter: { years: [2022, 2024] } };
/** Each block's state (src/safety-map/state.js), laid over the defaults. */
export const BLOCKS = {
  "street-safety-hin-groups": { ...groups },
  ...Object.fromEntries([1, 2, 3, 4].map((g) => [`street-safety-hin-group-${g}`, { ...groups, filter: { years: [2022, 2024], hinGroup: [g] } }])),
  ...Object.fromEntries(STATE.WORST_YEARS.map((y) => [`street-safety-worst-${y}`, { hin: [], worst: y, chart: { id: "worst-overlap" } }])),
};
const DASHBOARD = "/transportation/street-safety/";

const PAGE_CSS = `<style>
html, body { margin: 0; background: #fff; }
.es { position: relative; height: 560px; }
.es .es-map { position: absolute; inset: 0; }
.es .es-map .sm-canvas { height: 100%; border-radius: 0; }
.es .sm-legend .es-open { display: block; margin-top: 4px; font-size: 0.75rem; }
/* On a phone nothing covers the map: the headline and key, then the chart, sit below it. */
@media (max-width: 760px) {
  .es { height: auto; display: flex; flex-direction: column; }
  .es .es-map { position: relative; height: 420px; }
  .es .sm-ov.sm-legend, .es .sm-ov.sm-chart { position: static; width: auto; max-width: none; max-height: none; margin: 6px 6px 0; box-shadow: none; }
  .es .sm-ov.sm-chart { order: 2; margin-bottom: 6px; }
  .es .sm-chart .plot-chart-note { display: block; }
}
</style>`;

function heightScript(name) {
  return `<script>
(function () {
  function send() { try { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: document.documentElement.scrollHeight }, "*"); } catch (e) {} }
  send(); window.addEventListener("load", send);
})();
</script>`;
}

function embedPage(name) {
  const state = BLOCKS[name];
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Street Safety Map — SF Works</title>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
${KIT_HEAD}
${MAP_CSS}
${PAGE_CSS}
</head>
<body>
<div class="es sm-stage" data-es>
  <div class="es-map"></div>
  <div class="sm-ov sm-legend"><p class="sm-head" data-headline aria-live="polite"></p><div class="sm-key" data-key></div><a class="es-open" target="_blank" rel="noopener" data-open href="${DASHBOARD}">Open the full map</a></div>
  <div class="sm-ov sm-chart" data-chart hidden><div class="sm-chart-slot"></div></div>
  <div class="sm-ov sm-cardslot" data-card></div>
</div>
${MAP_HEAD}
${inlineData()}
${SCRIPT}
${CHART_SCRIPT}
<script>
(function () {
  var root = document.querySelector("[data-es]");
  var ctl = SafetyMap.create(root.querySelector(".es-map"), { lib: maplibregl, basemap: sfMap, cards: CrashCards, state: SafetyMapState, routes: window.muniRoutes,
    dataUrl: ${JSON.stringify(DATA_URL)}, crashesUrl: ${JSON.stringify(CRASHES_URL)}, initial: ${JSON.stringify(state)}, cooperative: true, cardHost: root.querySelector("[data-card]") });
  SafetyOverlay.attach(ctl, { key: root.querySelector("[data-key]"), headline: root.querySelector("[data-headline]"), chart: root.querySelector("[data-chart]") });
  var open = root.querySelector("[data-open]");
  ctl.on(function (s) { open.href = ${JSON.stringify(DASHBOARD)} + SafetyMapState.toHash(s); });
  open.href = ${JSON.stringify(DASHBOARD)} + SafetyMapState.toHash(SafetyMapState.merge(SafetyMapState.DEFAULTS, ${JSON.stringify(state)}));
  window.__ctl = ctl;
  ctl.ready.then(function () { window.__ready = 2; }, function () { window.__ready = 2; });
})();
</script>
${heightScript(name)}
</body>
</html>
`;
}

export function render() {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex"><title>Street Safety figures for embedding — SF Works</title></head>
<body><h1>Street Safety figures for embedding</h1><ul>
${Object.keys(BLOCKS).map((b) => `<li><a href="/embed/street-safety/${b}/">${b}</a></li>`).join("\n")}
</ul></body></html>
`;
}

export function pages() {
  return Object.keys(BLOCKS).flatMap((b) => {
    const html = embedPage(b);
    return ["street-safety", "bike"].map((dir) => ({ path: `/embed/${dir}/${b}`, file: `embed/${dir}/${b}/index.html`, html, sitemap: false }));
  });
}
