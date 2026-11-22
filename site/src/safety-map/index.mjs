// The Street Safety map, put together for a page: the component's three browser scripts (state.js, crash-cards.js,
// map.js) as one inline script, its stylesheet, the Web Awesome kit with the site's theme file, the published data
// files, and the date the data was read.
//
// Both the dashboard (src/pages/transportation-street-safety.mjs) and the article story block (story.mjs) read
// everything from here, so they cannot drift apart. The data is written by tools/street-safety/street-safety-map.py.

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { ROUTE_JS } from "../muni-routes.mjs";

const HERE = import.meta.dirname;
const SITE = path.resolve(HERE, "../..");
const DATA_DIR = path.join(SITE, "data", "street-safety");

/** Where the data is published. Both pages fetch the same two files, so a reader's browser fetches them once. */
export const DATA_PATH = "/transportation/street-safety/data";
// The browser fetches these from JS, which withBase (scripts/site-files.mjs)
// never rewrites, so they carry the board frame's prefix themselves. Unset on
// sf-works.org, where they stay root-relative.
const BASE = (process.env.SITE_BASE_PATH || "").replace(/\/+$/, "");
export const DATA_URL = `${BASE}${DATA_PATH}/map.json`;
// The folder of crash card files, one per year and map cell (tools/street-safety/street-safety-cards.py); map.js names the file
// a tapped crash is in and fetches only that one.
export const CRASHES_URL = `${BASE}${DATA_PATH}/cards/`;
const CARDS_DIR = path.join(DATA_DIR, "cards");

const read = (f) => fs.readFileSync(path.join(HERE, f), "utf8");
/** The component, as one classic script: defines SafetyMapState, CrashCards and SafetyMap on window. */
/** The map's state module, run here too, so a page's controls take their choices (days, road users, years) from the
 *  same definitions the map filters on. */
export const STATE = (() => { const ctx = {}; vm.createContext(ctx); vm.runInContext(read("state.js"), ctx); return JSON.parse(JSON.stringify(ctx.SafetyMapState)); })();
export const SCRIPT = `${ROUTE_JS}\n<script>\n${read("state.js")}\n${read("crash-cards.js")}\nwindow.CrashCards = CrashCards;\n${read("map.js")}\n${read("overlay.js")}\n</script>`;

// The few parts of map.json a page renders from, kept and the rest let go: the dev server re-imports this module on
// every edit, and holding the whole parsed file each time grew it by gigabytes.
let small = null;
// People by level over every year the map holds (map.json `light.by_level_year`, "level/year": count), with the newest row's date.
function lightTotals(L) {
  const t = { killed: 0, severe: 0, visible: 0, pain: 0, newest: L ? L.newest : "" };
  const key = ["killed", "severe", "visible", "pain"];
  for (const [k, n] of Object.entries(L ? L.by_level_year : {})) t[key[Number(k.split("/")[0])]] += n;
  return t;
}
function smallData() {
  if (!small) {
    const D = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "map.json"), "utf8"));
    small = { meta: D.meta, hoods: D.hoods.map((h) => h.name), causes: D.causes, bci: { source: D.bci.source, fetched_on: D.bci.fetched_on, labels: D.bci.labels, aaa: D.bci.aaa },
      through: { minCars: D.through.minCars, minBin: D.through.minBin, runs: D.through.runs, jitter: D.through.jitter, classes: D.through.classes, nears: D.through.nears || ["mile"] },
      light: lightTotals(D.light), others: D.others, othersUnknownTo2012: D.othersUnknownTo2012 };
    // crime.json's span, without its places: the About page names the years it covers.
    const C = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "crime.json"), "utf8"));
    small.crime = { from: C.from, to: C.to, years: C.years, groups: C.groups };
  }
  return small;
}
/** The `meta` block of map.json: { read, figures, sources, countRule, k }. */
export function dataMeta() {
  return smallData().meta;
}

/** The crash card files, as paths under data/ ("cards/2019/7-8.json"), from the index the card script writes. */
function cardFiles() {
  const I = JSON.parse(fs.readFileSync(path.join(CARDS_DIR, "index.json"), "utf8"));
  return ["cards/index.json", ...Object.keys(I.files).sort().map((k) => `cards/${k}.json`)];
}
/** The data files and the chart script, as pages the build publishes as they are. */
export function dataFiles() {
  // The where-from view's files (tools/street-safety/where-traffic-comes-from.py): fetched by the page only when the view needs
  // them, so they are published as they are and never inlined, even in the board copy.
  const WF = path.join(DATA_DIR, "where-from");
  const wf = fs.existsSync(WF) ? fs.readdirSync(WF).filter((f) => f.endsWith(".json")).sort().map((f) => `where-from/${f}`) : [];
  return ["map.json", "people-2005-2020.json", "crime.json", ...cardFiles(), ...wf].map((f) => ({
    path: `${DATA_PATH}/${f}`, file: `${DATA_PATH.slice(1)}/${f}`, html: fs.readFileSync(path.join(DATA_DIR, f)), sitemap: false,
  })).concat([{ path: CHART_URL, file: CHART_URL.slice(1), html: CHART_JS, sitemap: false }]);
}
/** The board copy's inline cards: those of the people map.json draws as figures (the ones with a case number), as
 *  { "<year>/<i>-<j>": { case: card } }, the file names map.js derives. A dot's card there needs its file fetched. */
function boardCards(D) {
  const out = {}, files = {};
  for (const p of D.people) {
    if (!p.cs) continue;
    const k = `${p.d.slice(0, 4)}/${Math.floor(p.c[0] * 100) + 12260}-${Math.floor(p.c[1] * 100) - 3770}`;
    if (!(k in files)) { const f = path.join(CARDS_DIR, `${k}.json`); files[k] = fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")).cards : {}; }
    if (files[k][p.cs]) (out[k] = out[k] || {})[p.cs] = files[k][p.cs];
  }
  return out;
}

// Web Awesome 3.14.0, the fleet's design kit (Team Lead's stack doc, decided 2026-11-13), with the site's theme file
// in the kit's four-part format (claude-live-feedback-plugin templates/design-kit/themes/workspaces.css).
const WA = "https://cdn.jsdelivr.net/npm/@awesome.me/webawesome@3.14.0/dist-cdn";
export const KIT_HEAD = `<link rel="stylesheet" href="${WA}/styles/themes/default.css">
<style>${read("theme.css")}</style>
<script type="module" src="${WA}/webawesome.loader.js"></script>`;

// Scrollama 3.2.0 for the story's steps, pinned with its hash (jsDelivr, read 2026-11-19).
export const SCROLLAMA = `<script src="https://cdn.jsdelivr.net/npm/scrollama@3.2.0/build/scrollama.min.js" integrity="sha384-trt5UkaI73mRdcngswspDe4cRMaS9HcWgFr+IgtdUGBbsS4/9FF7MDIX7xl+O9zI" crossorigin="anonymous"></script>`;

/** The component's own styles. Every colour is a --sm-* custom property, set by the theme file. */
export const CSS = `<style>
.sm-canvas { width: 100%; height: 100%; min-height: 240px; }
.sm-key { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 14px; font-size: 0.8rem; line-height: 1.5; }
.sm-key i, .pop i.dot { display: inline-block; vertical-align: middle; margin-right: 5px; }
.sm-key img { width: 20px; height: 20px; vertical-align: middle; margin-right: 1px; }
.sm-key .dot, .pop .dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid var(--sm-outline); }
.sm-key .ln { width: 20px; height: 4px; border-radius: 2px; }
.sm-key .ln.dash { height: 4px; border-radius: 0; background: repeating-linear-gradient(90deg, #2b8cbe 0 7px, transparent 7px 10px); }
.sm-key .sm-key-h { flex-basis: 100%; font-weight: 600; color: var(--sm-ink); }
.sm-key .steps { display: inline-flex; vertical-align: middle; margin-right: 5px; }
.sm-key .steps b { width: 9px; height: 5px; }
.sm-key .ramp { width: 64px; height: 9px; border-radius: 5px; background: linear-gradient(90deg, rgba(253,231,37,0.35), rgba(94,201,98,0.8), #21918c, #3b528b, #440154); }
.sm-key .n, .sm .n { color: var(--sm-muted); font-variant-numeric: tabular-nums; }
.pop { font-size: 0.8rem; line-height: 1.45; max-width: 260px; }
.pop .g { color: var(--sm-muted); }
/* A where-from bubble's card: how people travel between the two places. */
.pop .wfm { margin-top: 7px; padding-top: 6px; border-top: 1px solid var(--sm-outline); }
.pop .wfm-bar { display: flex; height: 10px; margin: 4px 0 3px; border-radius: 2px; overflow: hidden; }
.pop .wfm-bar i { display: block; min-width: 1px; }
.pop .wfm-key { display: flex; flex-wrap: wrap; gap: 0 9px; }
.pop .wfm-key span { white-space: nowrap; }
.pop .wfm-key i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 3px; vertical-align: baseline; }
.pop .wfm-t { margin-top: 5px; }
.pop .wfm-e small { font-size: 0.9em; }
/* Overlays on the map: the filter panel, the slim key, the corner chart and the crash card. */
.sm-stage { position: relative; overflow: hidden; }
.sm-stage > .sm-mapbox { position: absolute; inset: 0; }
.sm-ov { position: absolute; z-index: 4; box-sizing: border-box; background: rgba(255,255,255,0.96); border: 1px solid var(--rule, #dfe3e9); border-radius: 8px; box-shadow: 0 1px 8px rgba(20,30,40,0.14); font-size: 0.8rem; line-height: 1.4; }
.sm-ov[hidden] { display: none; }
.sm-legend { left: 10px; bottom: 26px; max-width: min(340px, calc(100% - 20px)); padding: 8px 10px; }
.sm-head { margin: 0 0 4px; font-size: 0.84rem; line-height: 1.35; }
.sm-head b { font-family: Archivo, sans-serif; font-size: 1.05rem; color: var(--sm-ink); }
.sm-chart { right: 10px; bottom: 26px; width: 290px; padding: 8px 10px 4px; --chart-font: "Public Sans", system-ui, sans-serif; }
/* A long chart (every year from 2005) scrolls inside its corner, clear of the zoom buttons. */
.sm-chart { max-height: calc(100% - 140px); overflow-y: auto; overscroll-behavior: contain; }
.sm-chart .plot-chart { margin: 0; }
.sm-chart .plot-chart-title { font-weight: 600; font-size: 0.82rem; margin: 0 0 2px; }
.sm-chart .plot-chart-subtitle:empty, .sm-chart .plot-chart-note:empty { display: none; }
.sm-chart .plot-chart-note { color: var(--sm-muted); font-size: 0.72rem; margin: 2px 0 2px; line-height: 1.3; }
.sm-chart svg { font-size: 11px !important; }
.sm-chart .plot-chart-subtitle { color: var(--sm-muted); font-size: 0.74rem; margin: 0 0 2px; }
.sm-chart-head { display: flex; align-items: center; gap: 6px; margin: 0 0 2px; }
.sm-chart-head.one { display: none; }
.sm-chart-pick { flex: 1; min-width: 0; font: inherit; font-weight: 600; font-size: 0.82rem; color: var(--sm-ink); border: 1px solid transparent; border-radius: 4px; background-color: transparent; padding: 1px 2px; margin-left: -3px; cursor: pointer; text-overflow: ellipsis; }
.sm-chart-pick:hover, .sm-chart-pick:focus-visible { border-color: var(--rule, #dfe3e9); background-color: #fff; }
.sm-chart-up { flex: none; font: inherit; font-size: 0.75rem; color: var(--sm-highlight, #2f7d76); background: none; border: 0; padding: 2px 4px; cursor: pointer; }
.sm-chart-up[hidden] { display: none; }
/* One button over each bar's row: hover or focus tints the row, a chosen bar is marked at its left. */
.sm-chart-hits { position: absolute; pointer-events: none; }
.sm-hit { position: absolute; left: 0; right: 0; pointer-events: auto; background: transparent; border: 0; border-radius: 3px; padding: 0; margin: 0; cursor: pointer; }
.sm-hit.look { cursor: default; }
.sm-hit:hover, .sm-hit:focus-visible { background: rgba(47, 125, 118, 0.12); }
.sm-hit:focus-visible { outline: 2px solid var(--sm-highlight, #2f7d76); outline-offset: 0; }
.sm-hit.on { box-shadow: inset 3px 0 0 var(--sm-highlight, #2f7d76); background: rgba(47, 125, 118, 0.08); }
/* A bar marked from the map (the where-from view): an outline, so the mark doesn't cover the name's first letter. */
.sm-hit.look.on { box-shadow: none; outline: 2px solid var(--sm-highlight, #2f7d76); outline-offset: -1px; background: rgba(47, 125, 118, 0.1); }
/* A chart with a colour key: no page margin on Plot's figure, no tall band under the key, and the slot as tall as both. */
.sm-chart figure { margin: 0; }
.sm-chart [class*="-swatches-wrap"] { min-height: 0; margin: 2px 0 0; }
.sm-chart .plot-chart-slot:has(figure) { height: auto !important; }
@media (hover: none) { .sm-hit:hover { background: transparent; } }
.sm-hint { top: 52px; left: 50%; transform: translateX(-50%); padding: 6px 12px; max-width: calc(100% - 24px); }
.sm-legend .sm-na, .sm-head .sm-na { display: block; color: var(--sm-muted); font-size: 0.75rem; }
/* Traffic stress: one row of blocks, each class with its own label under it. */
.sm-key .sm-blocks { flex-basis: 100%; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 2px; font-size: 0.66rem; line-height: 1.15; color: var(--sm-muted); text-align: center; }
.sm-key .sm-blocks b { display: block; height: 9px; margin-bottom: 2px; }
.sm-key .sm-key-h ~ .sm-key-h { margin-top: 3px; }
/* A key entry that filters the map (bike comfort classes): a plain row, faded while another one is picked. */
.sm-key .sm-kbtn { display: inline-flex; align-items: center; font: inherit; color: inherit; background: none; border: 0; border-radius: 3px; padding: 0 3px; margin: 0 -3px; cursor: pointer; }
.sm-key .sm-kbtn:hover, .sm-key .sm-kbtn:focus-visible { background: rgba(47, 125, 118, 0.12); }
.sm-key .sm-kbtn:focus-visible { outline: 2px solid var(--sm-highlight, #2f7d76); }
.sm-key .sm-kbtn[aria-pressed="true"] { font-weight: 600; }
.sm-key .sm-kbtn.off { opacity: 0.45; }
.sm-cardslot { right: 92px; top: 10px; width: 420px; max-height: min(620px, calc(100% - 48px)); overflow-y: auto; overscroll-behavior: contain; background: transparent; border: 0; box-shadow: none; }
.sm-cardslot:empty { display: none; }
.sm-cardslot #cc-panel { box-shadow: 0 2px 12px rgba(0,0,0,.18); }
@media (max-width: 760px) {
  .sm-legend { left: 6px; bottom: 6px; max-width: calc(50% - 6px); padding: 6px 8px; }
  .sm-head { font-size: 0.74rem; }
  .sm-head b { font-size: 0.9rem; }
  .sm-chart { right: 6px; bottom: 6px; width: calc(50% - 10px); padding: 6px 6px 2px; }
  .sm-chart .plot-chart-note { display: none; }
  /* A long chart (twelve causes) scrolls inside its corner rather than covering the map. */
  .sm-chart { max-height: 24%; overflow-y: auto; overscroll-behavior: contain; }
  .sm-cardslot { left: 0; right: 0; top: auto; bottom: 0; width: auto; max-height: 55%; }
  .sm-cardslot #cc-panel { border-radius: 10px 10px 0 0; }
}
.sm-sheet { margin: 8px 0 0; padding: 10px 12px; border: 1px solid var(--rule, #dfe3e9); border-radius: 6px; font-size: 0.85rem; background: var(--raised, #f4f6f8); }
.sm-sheet[hidden] { display: none; }
#cc-panel { box-sizing: border-box; background: #fff; border: 1px solid var(--rule, #dfe3e9); border-radius: 6px; font-size: 0.8rem; line-height: 1.45; margin: 0; }
#cc-panel.float { position: absolute; right: 8px; width: 420px; overflow-y: auto; box-shadow: 0 2px 12px rgba(0,0,0,.18); z-index: 5; }
.cc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 6px 6px 12px; border-bottom: 1px solid #eceef1; font-weight: 600; position: sticky; top: 0; background: #fff; z-index: 1; }
.cc-top .cc-btns { display: inline-flex; gap: 4px; align-items: center; }
.cc-car { --aspect-ratio: auto; --slide-gap: 12px; }
.cc-car::part(scroll-container) { align-items: flex-start; }
.cc { padding: 8px 12px 10px; }
.cc-when { color: var(--sm-muted); font-variant-numeric: tabular-nums; margin: 2px 0 4px; }
.cc-t { margin: 0 0 6px; line-height: 1.45; }
.cc-svg { display: block; width: 100%; max-width: 340px; height: auto; margin: 2px auto 0; }
.cc-road { font-size: 9px; fill: #3d4450; }
.cc-num { font-size: 9px; font-weight: 600; fill: #353b44; }
.cc-note { font-size: 8.5px; fill: var(--sm-muted); }
.cc-key { color: var(--sm-muted); font-size: 0.72rem; margin: 2px 0 6px; }
.cc-p { margin: 0 0 4px; padding-left: 18px; font-size: 0.85rem; }
.cc-p li { margin-bottom: 3px; }
.cc-inj { font-weight: 600; white-space: nowrap; }
.cc-inj i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 4px; border: 1px solid rgba(0,0,0,.25); }
.cc-none { color: var(--sm-muted); white-space: nowrap; }
.cc-k { color: var(--sm-muted); }
.cc-d { display: grid; grid-template-columns: max-content 1fr; gap: 1px 10px; margin: 0 0 6px; }
.cc-d dt { color: var(--sm-muted); }
.cc-d dd { margin: 0; }
.cc-src { font-size: 0.75rem; margin-top: 2px; }
.cc-src.g { color: var(--sm-muted); }
</style>`;

// The corner chart's script: src/plot-chart/entry.mjs bundled with esbuild, Plot from the site's own copy.
const CHART_DIR = path.join(HERE, "..", "plot-chart");
const PLOT_ESM = /^https:\/\/esm\.sh\/@observablehq\/plot@0\.6\.17$/;
// Built once per set of sources and kept on globalThis, so the dev server's re-imports reuse it; the esbuild service
// stops after each build rather than idling beside the server.
const CHART_SRC = ["entry.mjs", "plot-chart.ts", "plot-spec.mjs", "component-snapshot.ts", "component-state-rules.ts"].map((f) => fs.statSync(path.join(CHART_DIR, f)).mtimeMs).join(",");
const cache = (globalThis.__sfStreetSafetyChart ||= {});
const esbuild = cache.key === CHART_SRC ? null : await import("esbuild");
const bundled = esbuild ? await esbuild.build({
  entryPoints: [path.join(CHART_DIR, "entry.mjs")], bundle: true, write: false, format: "iife", minify: true, legalComments: "none",
  target: "es2020", logLevel: "silent",
  plugins: [{ name: "plot-from-site", setup(b) { b.onResolve({ filter: PLOT_ESM }, () => ({ path: path.join(SITE, "node_modules/@observablehq/plot/src/index.js") })); } }],
}) : null;
if (bundled) { cache.key = CHART_SRC; cache.js = bundled.outputFiles[0].text; await esbuild.stop?.(); }
/** The chart bundle's address and bytes, published beside the map's data. */
export const CHART_URL = "/transportation/street-safety/chart.js";
export const CHART_JS = cache.js;
// Under a SITE_BASE_PATH (the board's app door) the page's own files can't be
// fetched from a phone: the board frame sends no Cloudflare Access cookie, so
// Safari gets a redirect and a TypeError. There the chart code and both data
// files go inside the page. sf-works.org never sets the base and keeps the files.
const INLINE = Boolean(BASE);
const safe = (t) => t.replace(/<\/(script)/gi, "<\\/$1");
export const CHART_SCRIPT = INLINE ? `<script>${safe(cache.js || "")}</script>` : `<script defer src="${CHART_URL}"></script>`;
/** The data, inline, for the board copy; empty on sf-works.org. Read per render so a rebuilt map.json shows on reload. */
export function inlineData() {
  if (!INLINE) return "";
  const f = (n) => fs.readFileSync(path.join(DATA_DIR, n), "utf8");
  // The years before 2021 and the crime reports ride along as text, parsed only when the Years slider reaches back
  // or the crime view opens.
  const map = f("map.json");
  return `<script>window.__ssInline={data:${safe(map)},crashes:${safe(JSON.stringify(boardCards(JSON.parse(map))))}};</script>` +
    `<script type="application/json" id="ss-older">${safe(f("people-2005-2020.json"))}</script>` +
    `<script type="application/json" id="ss-crime">${safe(f("crime.json"))}</script>`;
}

/** What the About page says of the bike layer: { bci: { source, fetched_on, labels, aaa } }. */
export function mapData() {
  return { bci: smallData().bci, light: smallData().light, crime: smallData().crime, others: smallData().others, othersUnknownTo2012: smallData().othersUnknownTo2012 };
}
/** What the About page says of the through-traffic view: { minCars, runs, jitter, classes }. */
export function throughMeta() {
  return smallData().through;
}
/** The where-from view's regions outside SF, [{ name, places }] with places MTC's superdistrict names, from
 *  site/data/street-safety/where-from/units.json (tools/street-safety/where-traffic-comes-from.py). */
export function whereFromRegions() {
  const f = path.join(DATA_DIR, "where-from", "units.json");
  return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, "utf8")).regions.map((r) => ({ name: r.name, places: r.places })) : [];
}
/** The cause filter's tree: [{ key, label, n, subs: [{ key, label, n }] }], biggest first, Other and Unknown last. */
export function causeTree() {
  return smallData().causes;
}
/** The 11 Supervisor districts the area filter offers, [{ district, coords }] with coords a MultiPolygon's, from
 *  site/data/supervisor-districts.json (pipeline/sources/supervisor-districts.py: DataSF cqbw-m5m3, simplified to about 30 ft,
 *  about 35 kB). The page carries them inline, so the board copy needs no extra fetch. */
export function districtsData() {
  const d = JSON.parse(fs.readFileSync(path.join(SITE, "data", "supervisor-districts.json"), "utf8"));
  return d.districts.map((x) => ({ district: x.district, coords: x.coords })).sort((a, b) => a.district - b.district);
}
/** The analysis neighborhoods the area filter offers, in name order. */
export function hoodNames() {
  return smallData().hoods;
}
