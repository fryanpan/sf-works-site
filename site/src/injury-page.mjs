// The injury map's body for the board doc's embed, /embed/injuries/injury-map/
// (src/injury-blocks.mjs cuts the map out of content()). It was the Mobility
// section's injury page until Bryan, 2026-10-23: "Drop the page on sf works and
// keep just one mdx file with charts pleases". The write-up is now a board doc,
// and only the map is built from this module. The view (the school picked, the injury view, the fix
// layers and the map's centre) lives in the address, through src/injury-view.mjs.
//
// Every figure is read from site/data/injury-map.json, written by
// tools/street-safety/injury-map.py from DataSF's police crash reports and the city's
// street, speed camera, speed limit and traffic calming data.

import fs from "node:fs";
import nodePath from "node:path";
import { MAP_HEAD, encodeRuns, encodePoints, boundsOf, inlineJson } from "./maplibre.mjs";
import { Plot, plotSVG } from "./plot.mjs";
import { readView, writeView, kidLine } from "./injury-view.mjs";
import { fnSource } from "./fn-source.mjs";

const DATA = nodePath.join(import.meta.dirname, "..", "data");
const readJson = (rel) => JSON.parse(fs.readFileSync(nodePath.join(DATA, rel), "utf8"));

// The page's own styles, scoped under .hin so they leave the site's masthead,
// breadcrumb and source list alone. Rules the site's layout already sets for
// every page (type, links, the page width) are left to it.
const RAW_CSS = `
:root { --ink: #15181c; --muted: #59626f; --raised: #f4f4f4; --line: #dde1e6; --blue: #4269d0; --gold: #efb118; --seq-3: #2f7d76; }
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: var(--ink); font: 16px/1.5 "Public Sans", ui-sans-serif, system-ui, -apple-system, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 20px 20px 40px; }
h1 { font: 700 1.6rem/1.2 Archivo, "Public Sans", ui-sans-serif, system-ui, sans-serif; margin: 0 0 6px; max-width: 30em; }
h2 { font: 700 1.15rem/1.3 Archivo, "Public Sans", ui-sans-serif, system-ui, sans-serif; margin: 28px 0 6px; }
h3 { font: 600 1rem/1.3 Archivo, "Public Sans", sans-serif; margin: 18px 0 4px; }
.sub { font-size: 1.05rem; color: var(--muted); max-width: 46em; }
p { margin: 0 0 10px; max-width: 46em; }
a { color: inherit; text-underline-offset: 2px; text-decoration-color: var(--muted); }
.tag { color: var(--muted); }
.fn { font: 600 0.7rem/1 "Public Sans", system-ui, sans-serif; color: var(--muted); background: var(--raised); border: 1px solid var(--line);
  border-radius: 8px; padding: 2px 5px; margin: 0 1px 0 2px; vertical-align: super; cursor: pointer; }
.fn[aria-expanded="true"] { color: var(--ink); border-color: var(--muted); }
.fnote { display: block; font-size: 0.82rem; line-height: 1.4; color: var(--ink); background: var(--raised); border-left: 3px solid var(--line);
  padding: 6px 10px; margin: 6px 0; max-width: 46em; font-weight: 400; }
.fnote[hidden] { display: none; }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0; max-width: 900px; }
.stat { border-top: 4px solid var(--line); padding: 8px 0 0; }
.stat.b { border-color: var(--blue); } .stat.g { border-color: var(--gold); }
.stat b { display: block; font: 700 1.7rem/1.1 Archivo, "Public Sans", sans-serif; }
.stat span { display: block; font-size: 0.85rem; color: var(--muted); line-height: 1.35; margin-top: 3px; }
.callout { border-left: 4px solid var(--seq-3); background: var(--raised); padding: 10px 14px; margin: 14px 0 18px; max-width: 46em; }
.callout p { margin: 0 0 6px; } .callout p:last-child { margin: 0; }
.bar-ctl { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 0 0 8px; }
.fxsel { font-size: 0.85rem; color: var(--muted); display: flex; align-items: center; gap: 6px; } .fxsel select { font: inherit; color: var(--ink); padding: 3px 6px; border: 1px solid var(--line); border-radius: 4px; background: white; }
.legend i.ln.dash { background: none; border-top: 2px dashed #15181c; height: 0; }
.mapwrap { width: min(100vw - 32px, 1600px); margin: 8px 0 8px calc(50% - min(50vw - 16px, 800px)); display: grid; grid-template-columns: 230px 1fr; gap: 12px; align-items: start; }
.mapwrap #map { height: 640px; }
.lyr { font-size: 0.85rem; color: var(--ink); } .lyr summary { display: none; }
.lyr fieldset { border: 0; margin: 0 0 10px; padding: 0; } .lyr legend { font-weight: 700; font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; padding: 0; margin-bottom: 4px; }
.lyr label { display: flex; align-items: center; gap: 6px; padding: 3px 0; cursor: pointer; line-height: 1.25; } .lyr input { margin: 0; flex: none; } .lyr-n { margin-left: auto; padding-left: 8px; color: var(--muted); font-variant-numeric: tabular-nums; } .lyr-all { color: var(--muted); }
.lyr i { display: inline-block; flex: none; } .lyr .ln { width: 18px; height: 4px; border-radius: 2px; } .lyr .ln.dash { background: none; border-top: 3px dashed; height: 0; border-radius: 0; }
.lyr .cam { width: 9px; height: 9px; border-radius: 50%; background: #fff; border: 2px solid var(--ink); } .lyr .sch { width: 9px; height: 9px; background: #e8eaf6; border: 2px solid #5b3fa0; border-radius: 2px; }
.lyr .ramp { width: 40px; height: 8px; border-radius: 2px; background: linear-gradient(90deg, #fde725, #5ec962, #21918c, #3b528b, #440154); }
.lyr-key { display: grid; gap: 4px; font-size: 0.8rem; color: var(--muted); border-top: 1px solid var(--line); padding-top: 8px; } .lyr-key span { display: flex; align-items: center; gap: 6px; } .lyr-key [hidden] { display: none; }
@media (max-width: 700px) {
  .mapwrap { width: auto; margin: 8px 0; display: block; } .mapwrap #map { height: 440px; }
  .lyr { border: 1px solid var(--line); border-radius: 6px; margin-bottom: 8px; background: #fff; } .lyr summary { display: block; padding: 8px 10px; cursor: pointer; font-weight: 600; } .lyr summary::after { content: " ▾"; float: right; color: var(--muted); }
  .lyr-body { padding: 0 10px 8px; display: grid; grid-template-columns: 1fr; }
}
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 0.85rem; color: var(--muted); }
.legend i { display: inline-block; vertical-align: middle; margin-right: 6px; }
.legend .ln { width: 22px; height: 4px; border-radius: 2px; }
.legend .sch { width: 10px; height: 10px; background: #e8eaf6; border: 2px solid #5b3fa0; border-radius: 2px; }
.legend .cam { width: 10px; height: 10px; border-radius: 50%; background: #fff; border: 2px solid var(--ink); }
.legend .ramp { width: 44px; height: 8px; border-radius: 2px; background: linear-gradient(90deg, #fde725, #5ec962, #21918c, #3b528b, #440154); }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.seg button { font: 0.85rem/1 "Public Sans", system-ui, sans-serif; border: 0; background: #fff; color: var(--muted); padding: 7px 11px; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--line); }
.seg button[aria-pressed="true"] { background: var(--ink); color: #fff; }
#map { height: 560px; }
.note { font-size: 0.82rem; color: var(--muted); margin: 6px 0 0; max-width: 60em; }
.chart { max-width: 900px; margin: 10px 0 4px; }
.chart .row { display: grid; grid-template-columns: 200px minmax(0, 1fr) 150px; gap: 10px; align-items: center; padding: 4px 0; font-size: 0.9rem; }
.chart .lab { text-align: right; color: var(--muted); }
.chart .lab .eg { display: block; font-size: 12px; color: var(--muted); opacity: 0.85; }
.chart .barwrap { display: flex; align-items: center; gap: 8px; height: 22px; }
.chart .bar { height: 22px; background: var(--blue); border-radius: 2px; flex: none; }
.chart .val { font-weight: 600; white-space: nowrap; font-size: 0.88rem; }
.chart .mi { color: var(--muted); font-size: 0.85rem; }
.chart .head { color: var(--muted); font-size: 0.8rem; font-weight: 600; }
.chart.split .row { grid-template-columns: 230px minmax(0, 1fr) minmax(0, 1fr); }
.chart .val small { font-weight: 400; color: var(--muted); font-size: 0.78rem; }
.chart .bar.sp { background: #b3c3ee; position: relative; overflow: hidden; }
.chart .bar.sp i { position: absolute; left: 0; top: 0; bottom: 0; background: var(--blue); }
.plotwrap { max-width: 960px; margin: 6px 0 4px; } .plotwrap svg { display: block; overflow: visible; } .plotwrap .pl-phone { display: none; }
/* The site's project card (site/src/layout.mjs .proj-card), static here: in a map popup or the details panel. */
.proj-card.pc { font-size: 0.88rem; line-height: 1.4; }
.proj-card p { margin: 4px 0; }
.proj-card .proj-name { font: 700 1.05rem/1.25 Archivo, "Public Sans", sans-serif; margin: 0 0 4px; }
.proj-card .proj-when { color: var(--muted); font-size: 0.84rem; }
.proj-table { border-collapse: collapse; width: 100%; margin: 4px 0 6px; font-size: 0.84rem; }
.proj-table th, .proj-table td { text-align: left; vertical-align: top; padding: 4px 0; border-top: 1px solid var(--line); border-bottom: 0; }
.proj-card .proj-table th { width: 44%; font-size: inherit; font-weight: 600; color: var(--ink); padding-right: 10px; }
.proj-table td { font-variant-numeric: tabular-nums; }
.proj-card .proj-more { font-size: 0.84rem; }
.proj-card .proj-photo { margin: 6px 0; }
.proj-card .proj-photo[hidden] { display: none; }
.proj-card .proj-photo img { display: block; width: 100%; aspect-ratio: 3 / 1; object-fit: cover; border-radius: 4px; background: var(--line); }
.maplibregl-popup .proj-card { width: 260px; max-height: 300px; overflow: auto; }
.fwrap { position: relative; } .fwrap svg { max-width: 100%; height: auto; display: block; }
.fhead { position: absolute; left: 2px; transform: translateY(-50%); font-size: 0.85rem; color: var(--ink); white-space: nowrap; }
.fhead .yrs { color: var(--muted); }
.info { font: 600 0.8rem/1 "Public Sans", system-ui, sans-serif; color: var(--blue); background: #fff; border: 1px solid var(--line); border-radius: 50%; width: 22px; height: 22px; padding: 0; cursor: pointer; vertical-align: middle; }
.info:hover, .info:focus-visible { border-color: var(--blue); }
table.grid td { text-align: right; font-variant-numeric: tabular-nums; } table.grid td:first-child { text-align: left; }
.ptip { position: fixed; z-index: 50; max-width: 280px; background: #15181c; color: #fff; font-size: 0.8rem; line-height: 1.35; padding: 6px 9px; border-radius: 6px; pointer-events: none; }
.ptip[hidden] { display: none; }
.progs { font-size: 0.88rem; color: var(--muted); max-width: 46em; padding-left: 1.4em; margin: 6px 0 10px; }
.progs li { margin: 2px 0; }
dialog#proj { border: 0; border-radius: 10px; padding: 0; width: min(640px, 92vw); max-height: 90vh; box-shadow: 0 10px 40px rgba(0,0,0,0.25); }
dialog#proj::backdrop { background: rgba(21,24,28,0.45); }
.dlg { padding: 14px 18px 18px; } .dlg-top { display: flex; justify-content: space-between; align-items: center; min-height: 28px; }
.dlg-top button { font: 0.9rem "Public Sans", system-ui, sans-serif; background: none; border: 0; cursor: pointer; color: var(--muted); padding: 4px 6px; }
.dlg-top .close { margin-left: auto; font-size: 1.1rem; }
.dlg h3 { margin: 2px 0 6px; font-size: 1.1rem; } .dnote { font-size: 0.9rem; margin: 0 0 8px; }
.plist { list-style: none; padding: 0; margin: 0; columns: 2; } .plist li { break-inside: avoid; }
.plist button { font: 0.9rem "Public Sans", system-ui, sans-serif; background: none; border: 0; padding: 5px 0; cursor: pointer; text-align: left; color: var(--ink); text-decoration: underline; text-decoration-color: var(--line); }
.plist button span { color: var(--muted); text-decoration: none; }
.dt { font-size: 0.88rem; margin: 4px 0 10px; } .dt th, .dt td { padding: 5px 8px 5px 0; }
.dmap { height: 300px; border-radius: 6px; overflow: hidden; } .dleg { margin-top: 6px; }
.claims { margin: 6px 0 0; padding-left: 18px; font-size: 0.88rem; max-width: 46em; } .claims li { margin: 0 0 6px; } .claims .when { font-size: inherit; } .plotwrap .pl-wide { display: flex; gap: 6px; align-items: flex-start; } .plotwrap .pl-wide.stack { flex-direction: column; }
.legend .sw { width: 14px; height: 10px; border-radius: 2px; }
.ten td { vertical-align: top; } .ten .vd { font-weight: 700; white-space: nowrap; } .ten .v-no, .ten .v-cant { font-weight: 600; color: var(--muted); }
.split-key { margin: 8px 0 0; } .split-key .sw { width: 14px; height: 10px; border-radius: 2px; } .sw.lt { background: #b3c3ee; } .sw.dk { background: var(--blue); }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; vertical-align: top; padding: 9px 10px 9px 0; border-bottom: 1px solid var(--line); }
th { font-size: 0.78rem; color: var(--muted); font-weight: 600; }
td b { font-size: 1rem; }
.fixes, details table { table-layout: fixed; }
.fixes th:nth-child(1) { width: 15%; } .fixes th:nth-child(2) { width: 21%; } .fixes td:nth-child(2) { padding-right: 16px; }
details th:nth-child(1) { width: 30%; } details th:nth-child(5) { width: 12%; } details td:nth-child(1) { padding-right: 14px; }
.when { color: var(--muted); font-size: 0.82rem; }
.ivl { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 2px 6px; font-size: 0.82rem; color: var(--muted); margin-top: 2px; }
.iv { flex: none; }
details { margin: 10px 0; } summary { cursor: pointer; font-weight: 600; font-size: 0.95rem; }
.maplibregl-popup-content { font: 0.85rem/1.35 "Public Sans", system-ui, sans-serif; padding: 6px 10px; }
@media (max-width: 760px) {
  main { padding: 14px 14px 30px; }
  h1 { font-size: 1.3rem; }
  .stats { gap: 8px; } .stat b { font-size: 1.2rem; }
  #map { height: 440px; }
  .chart .row { grid-template-columns: 1fr; gap: 2px; padding: 6px 0; } .chart .lab { text-align: left; } .chart .head.mi { display: none; }
  .plotwrap .pl-wide { display: none; } .plotwrap .pl-phone { display: block; }
  dialog#proj { width: 100vw; height: 100dvh; max-width: none; max-height: none; margin: 0; border-radius: 0; }
  .proj-table { display: table; } .proj-table tbody { display: table-row-group; } .proj-table tr { display: table-row; border: 0; padding: 0; }
  .proj-table th, .proj-table td, .proj-card .proj-table th { display: table-cell; width: auto; border-top: 1px solid var(--line); padding: 4px 8px 4px 0; }
  .dmap { height: 46vh; } .plist { columns: 1; } .fhead { font-size: 0.8rem; }
  .dt thead { display: table-header-group; } .dt, .dt tbody, .dt tr { display: revert; } .dt th, .dt td { display: table-cell; width: auto; border-bottom: 1px solid var(--line); }
  .chart.split .row { grid-template-columns: 1fr 1fr; } .chart.split .lab { grid-column: 1 / -1; color: var(--ink); font-weight: 600; }
  .chart.split .row:first-child .lab { display: none; } .chart.split .row:first-child .head { font-size: 0.75rem; }
  table, thead, tbody, tr, td { display: block; width: 100%; }
  thead { display: none; }
  tr { border-bottom: 1px solid var(--line); padding: 6px 0; }
  td, .fixes td:nth-child(n), details td:nth-child(n) { border: 0; padding: 3px 0; width: 100%; }
  .fixes, details table { table-layout: auto; }
  td[data-h]::before { content: attr(data-h) ": "; color: var(--muted); font-size: 0.8rem; display: block; } td.dk[data-h]::before { color: rgba(255,255,255,0.85); }
  .ivl { white-space: normal; }
}
`;
const SITE_OWNS = /^(:root|\*|body|main|h1|h2|h3|p|a)$/;
function scope(css, pre) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, "");
  let out = "", i = 0;
  while (i < css.length) {
    const open = css.indexOf("{", i);
    if (open < 0) break;
    const sel = css.slice(i, open).trim();
    if (sel.startsWith("@media")) {
      let depth = 1, j = open + 1;
      while (depth && j < css.length) { if (css[j] === "{") depth++; else if (css[j] === "}") depth--; j++; }
      out += `${sel} {\n${scope(css.slice(open + 1, j - 1), pre)}}\n`;
      i = j;
      continue;
    }
    const close = css.indexOf("}", open);
    const sels = sel.split(",").map((x) => x.trim()).filter((x) => !SITE_OWNS.test(x))
      .map((x) => (x.startsWith(".ptip") ? x : `${pre} ${x}`));
    if (sels.length) out += `${sels.join(", ")} ${css.slice(open, close + 1)}\n`;
    i = close + 1;
  }
  return out;
}
// The charts, tables and map are wider than the site's reading column, so they
// break out of it on a laptop, as the site's .fig.wide does.
const EXTRA_CSS = `
.hin { --line: #dde1e6; --blue: #4269d0; --gold: #efb118; --raised: #f4f4f4; }
.hin .sub { font-size: 1.05rem; color: var(--muted); }
.hin .plotwrap, .hin .wide, .hin details:has(table) { width: min(960px, 100vw - 32px); max-width: none; margin-left: calc(50% - min(480px, 50vw - 16px)); }
/* Each chart at the size it was drawn for (the site's .plot-chart stretches to the column), centred in the band. */
.hin .plotwrap .plot-chart { width: auto; max-width: 100%; margin: 0 auto; }
.hin .plotwrap .pl-wide:not(.stack) .plot-chart { margin: 0; }
.hin .plotwrap > *, .hin .plotwrap .stack > * { margin-left: auto; margin-right: auto; }
.hin .plotwrap .pl-wide:not(.stack) { justify-content: center; }
.hin .school-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 10px 0 4px; }
.hin .school-bar label { font-weight: 600; font-size: 0.9rem; }
.hin .school-bar select { font: inherit; font-size: 0.95rem; color: var(--ink); padding: 5px 8px; border: 1px solid var(--line); border-radius: 6px; background: #fff; max-width: min(420px, 100%); }
.hin .copy-link { font: 600 0.85rem/1 "Public Sans", system-ui, sans-serif; color: var(--ink); background: #fff; border: 1px solid var(--line); border-radius: 6px; padding: 7px 11px; cursor: pointer; }
.hin .copy-link:hover, .hin .copy-link:focus-visible { border-color: var(--ink); }
.hin .copy-url { font: 0.8rem ui-monospace, monospace; width: min(420px, 100%); padding: 5px 6px; border: 1px solid var(--line); border-radius: 4px; }
.hin .copy-url[hidden] { display: none; }
.hin .school-line { margin: 4px 0 6px; font-size: 0.95rem; }
.hin .school-line[hidden] { display: none; }
/* The phone's Layers toggle is a control, not a link, so it takes the ink colour rather than the site's red. */
.hin .lyr summary { color: var(--ink); }
.hin .lyr .ring { width: 18px; height: 0; border-top: 2px solid #5b3fa0; } .hin .lyr .ring.dash { border-top-style: dashed; }
.hin .lyr .kidpt { width: 8px; height: 8px; border-radius: 50%; background: #15181c; border: 1.5px solid #fff; box-shadow: 0 0 0 1px #15181c; }
@media (max-width: 760px) {
  .hin .plotwrap, .hin .wide, .hin details:has(table) { width: auto; margin-left: 0; }
}
`;
const STYLE = `<style>${scope(RAW_CSS, ".hin")}${EXTRA_CSS}</style>`;

// The body, read by src/injury-blocks.mjs, which cuts the map out of it for the board's embed.
export function content() {
const d = readJson("injury-map.json");

const W = d.where, A = W.all, SV = W.severe, CAM = d.cameras, QB = d.corridors, TL = d.daylighting;
const f0 = (x) => Math.round(x).toLocaleString("en-US");
const pct = (a, b) => Math.round((100 * a) / b) + "%";
const chg = (rr) => { const p = Math.round((rr - 1) * 100); return (p > 0 ? "+" : p < 0 ? "−" : "") + Math.abs(p) + "%"; };
const ci = (o) => `${chg(o.rr[0])} (${chg(o.rr[1])} to ${chg(o.rr[2])})`;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const mon = (iso) => { const [y, m] = iso.split("-"); return MONTHS[+m - 1] + " " + y; };
const yrs = (y) => (Math.abs(y - Math.round(y)) < 0.1 ? `${Math.round(y)} years` : `${y.toFixed(1)} years`);
const SCHOOLS = readJson("school-sim/index.json").schools;
// The kids severely hurt or killed (tools/street-safety/injury-map.py, map.kidSevere), and each kid's place in that list.
const kidSevPos = new Map(d.map.kidSevere.map((k, j) => [k, j]));
const hinPaths = d.map.hin, qbPaths = d.map.corridorPaths.flatMap((c) => c.paths), qbNames = d.map.corridorPaths.flatMap((c) => c.paths.map(() => c.label));
const data = {
  hin: encodeRuns(hinPaths), qb: encodeRuns(qbPaths), qbNames,
  all: encodePoints(d.map.allPoints), sev: encodePoints(d.map.severePoints), kid: encodePoints(d.map.kidPoints),
  kidsev: encodePoints(d.map.kidSevere.map((i) => d.map.kidPoints[i])),
  cam: encodePoints(d.map.cameraPoints.map((c) => [c[0], c[1]])), camNames: d.map.cameraPoints.map((c) => c[2]),
  // The School Trips tool's own school list (site/data/school-sim/index.json), for the kids view.
  sch: encodePoints(SCHOOLS.map((x) => [x.lon, x.lat])), schNames: SCHOOLS.map((x) => x.name), schCds: SCHOOLS.map((x) => x.cds),
  tl: d.map.tlPolygon, bounds: boundsOf(hinPaths),
  // The school picker: each school's grounds, 500 ft and quarter-mile rings, and its kids' indices into `kid`
  // (tools/street-safety/injury-map.py, school_rings).
  schools: Object.fromEntries(d.schools.map((x) => [x.cds, { name: x.name, g: encodeRuns(x.grounds), z: encodeRuns(x.zone), q: encodeRuns(x.quarter), k: x.kids, ks: x.kids.filter((i) => kidSevPos.has(i)).map((i) => kidSevPos.get(i)), b: boundsOf(x.quarter) }])),
};
if (d.schools.length !== SCHOOLS.length || d.schools.some((x, i) => x.cds !== SCHOOLS[i].cds)) {
  throw new Error("injury page: site/data/injury-map.json's schools are not School Trips' schools; rerun tools/street-safety/injury-map.py");
}
// A planned project's card takes a cost from COST when its name starts with the same street words.
function planCost(name) { const k = Object.keys(COST).find((c) => name.toLowerCase().startsWith(c.toLowerCase().replace(/ quick-build$/, ""))); return k ? COST[k] : ""; }
// "Show fixes" layers (Bryan): each layer's lines or points plus one property row per feature.
{ const F = d.map.fixes, PL = F.planned.flatMap((pr, i) => pr.paths.map(() => i));
  data.fx = {
    to20: encodeRuns(F.to20.map((r) => r.p)), to20P: F.to20.map((r) => r.date),
    slow: encodeRuns(F.slow.map((r) => r.p)), slowP: F.slow.map((r) => [r.name, r.ext, r.date, r.planned ? 1 : 0]),
    calm: encodeRuns(F.calm.map((r) => r.p)), calmP: F.calm.map((r) => [r.name, r.where, r.date, r.planned ? 1 : 0, r.status]),
    calmPts: encodePoints(F.calmPts.map((r) => r.c)), calmPtsP: F.calmPts.map((r) => [r.name, r.where, r.date, r.planned ? 1 : 0, r.status]),
    psz: encodePoints(F.psz.map((r) => r.c)), pszP: F.psz.map((r) => [r.where, r.date]),
    plan: encodeRuns(F.planned.flatMap((pr) => pr.paths)), planI: PL, planP: F.planned.map((pr) => [pr.name, pr.phase, pr.page, pr.end || "", pr.kind, ""]),
    fetched: F.fetched, camCost: "$7.4 million for the five-year pilot at all 33 locations, \"permitting, installation, operations and maintenance\" (<a href='https://www.sfmta.com/blog/one-year-speeding-down-79-speed-safety-camera-locations' target=_blank rel=noopener>SFMTA blog</a>, May 2026)",
  }; }

// Sources
const VICTIMS = "https://data.sfgov.org/d/nwes-mmgh", CENTER = "https://data.sfgov.org/d/3psu-pn9h", CAMDATA = "https://data.sfgov.org/d/d5uh-bk84";
const HIN = "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/hin2022/FeatureServer/0";
const DECK = "https://www.sfmta.com/media/44957/download?inline";
const SSEP = "https://www.sfmta.com/reports/safe-streets-evaluation-program-2024-annual-report", SSEP_STORY = "https://arcg.is/1D8PPf";
const SSEP22 = "https://www.sfcta.org/sites/default/files/2022-11/SFCTA_CAC_SFMTASafeStreetsREPORT_2022-11-30.pdf";
const TL_DAY = "https://sfmta.com/media/14930/download", TL_BLOG = "https://www.sfmta.com/node/13179";
const CAMPAGE = "https://www.sfmta.com/projects/speed-safety-cameras";
const SFDPH15 = "https://web.archive.org/web/2016/http://sf.streetsblog.org/wp-content/uploads/sites/3/2015/09/SevereInjuriesSF_2014_15_PSAC.pdf";
const SFDPH17 = "https://www.sfcta.org/sites/default/files/2019-06/Item%205%20-%20Severe-Injury-Trends_2011-2017Final.pdf";
const SFDPH18 = "https://www.sfcta.org/sites/default/files/2019-09/Item%206%20-%202018%20Severe%20Injuries%20Report.pdf";
const SOLTANI = "https://doi.org/10.1016/j.jsr.2022.08.002", SFMTA_LINK = "https://sfmta.com/media/33452/download";
const PAGES = {
  howard: "https://www.sfmta.com/projects/transbay-howard-streetscape-improvement-project", brannan: "https://www.sfmta.com/projects/brannan-street-safety-project",
  townsend: "https://www.sfmta.com/projects/townsend-corridor-improvement-project", beale: "https://www.sfmta.com/projects/active-beale-street",
  anza: "https://www.sfmta.com/projects/anza-street-bike-lanes-project", williams: "https://www.sfmta.com/williams-avenue-quick-build-project",
  svn: "https://www.sfmta.com/projects/south-van-ness-avenue-quick-build-project", jones: "https://www.sfmta.com/projects/jones-street-quick-build",
  evans: "https://www.sfmta.com/projects/evans-avenue-quick-build", franklin: "https://www.sfmta.com/projects/franklin-street-quick-build-project",
  battery: "https://www.sfmta.com/projects/batterysansome-quick-build-project", "17th": "https://www.sfmta.com/projects/17th-street-quick-build",
  bayshore: "https://www.sfmta.com/projects/bayshore-boulevard-quick-build-project", lincoln: "https://www.sfmta.com/projects/lincoln-way-quick-build-project",
  "3rd": "https://www.sfmta.com/projects/3rd-street-quick-build-project", guerrero: "https://www.sfmta.com/projects/guerrero-street-quick-build-project",
  frida: "https://www.sfmta.com/projects/frida-kahlo-way-quick-build-project", ssep2022: SSEP22, sfgov2019: "https://sf.gov/es/node/497",
};
const tag = (t) => `<span class="tag">[${t}]</span>`;
let n = 0;
// An on-demand footnote: a numbered button that opens its note in place, below the line.
const fn = (html) => { n += 1; return `<button class="fn" type="button" aria-expanded="false" aria-label="Source ${n}">${n}</button><span class="fnote" hidden>${html}</span>`; };

// A change against the rest of the city, drawn as a dot and its 95% interval on a log axis from half to double.
function cell(o, color) {
  const Wd = 150, H = 20, lo = Math.log(0.5), hi = Math.log(2), x = (r) => Math.max(0, Math.min(Wd, ((Math.log(r) - lo) / (hi - lo)) * Wd));
  const zero = x(1), a = x(o.rr[1]), b = x(o.rr[2]), m = x(o.rr[0]);
  return `<svg class="iv" width="${Wd}" height="${H}" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="${ci(o)} against the rest of the city">
<line x1="${zero}" y1="2" x2="${zero}" y2="${H - 2}" stroke="#9aa3ad" stroke-width="1"/>
<line x1="${a}" y1="${H / 2}" x2="${b}" y2="${H / 2}" stroke="${color}" stroke-width="2"/>
<circle cx="${m}" cy="${H / 2}" r="4" fill="${color}"/></svg>`;
}
const SMALL = 20;
const counts = (o) => `<b>${f0(o.before)}</b> → <b>${f0(o.after)}</b>`;
const BLUE = "#4269d0", GOLD = "#efb118";
// Bryan: the fixes as one standard forest plot, % change and whether it is clear, nothing else.
// fixRow() collects a fix's rows for forest() and returns its SFMTA claim for the list under the chart.
const FIXES = [];
// Bryan: people biking get their own rows, at the site and with two blocks.
const MEASURES = [["site", "Everyone, at the site"], ["ped", "People walking, at the site"], ["bike", "People biking, at the site"], ["near", "Everyone, site plus two blocks"], ["nearPed", "People walking, site plus two blocks"], ["nearBike", "People biking, site plus two blocks"]];
const SHORT = { "Everyone, at the site": "Everyone", "People walking, at the site": "Walking", "People biking, at the site": "Biking", "Everyone, site plus two blocks": "Two blocks", "People walking, site plus two blocks": "Walking, 2 blocks", "People biking, site plus two blocks": "Biking, 2 blocks" };
const TL4 = (r) => ["Golden", "Jones", "Leavenworth", "Taylor"].includes(r.label.split(" ")[0]);
// The year the work happened: the day before the after window opens, since a start is the day after SFMTA's stated
// completion period (hin_split.py docstring).
const workYear = (iso) => { const t = new Date(iso + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() - 1); return t.getUTCFullYear(); };
const span = (rows) => { const ys = rows.map((r) => workYear(r.start)); const a = Math.min(...ys), b = Math.max(...ys); return a === b ? `${a}` : `${a} to ${b}`; };
const POOLS = [];
// Pooled rows come from hin_split.py's pooled(): each person once per pool, a crash-resampling bootstrap range, a
// placebo one window earlier and a p for Holm. A row is a clear drop only when its range stays below zero, its placebo
// range includes zero, and it survives Holm across every plotted row (Fable skeptic review, 2026-10-20). verdicts()
// runs once all rows are in.
function fixRow(label, when, claim, pooled, extra = []) {
  const members = pooled === camP ? CAM.rows : pooled === qbP ? QB.rows : pooled === tlP ? QB.rows.filter(TL4) : [TL];
  POOLS.push({ fix: label, years: span(members), members: members.map((r) => r.label),
    note: pooled === camP ? `Warnings began between ${camP.warningFirst[0]} and ${camP.warningFirst[1]} and citations on ${CITE.start} at every location. Counted from citations instead (${yrs(CITE.years)} each side): everyone at the block ${ci(CITE.site)}, with two blocks ${ci(CITE.near)}, against the rest of the city. Cost: SFMTA puts the five-year pilot at $7.4 million, "permitting, installation, operations and maintenance".` : pooled === qbP ? `SFMTA or SFCTA publishes a cost for ${Object.keys(COST).length} of these ${QB.rows.length} projects, shown on each one's card.` : "" });
  const pick = { site: pooled.site.all, ped: pooled.site.ped, bike: pooled.site.bike, near: pooled.near.all, nearPed: pooled.near.ped, nearBike: pooled.near.bike };
  MEASURES.forEach(([k, m]) => { const o = pick[k];
    if (k === "nearPed" && !extra.includes("nearPed")) return;
    if (Math.min(o.before, o.after) < SMALL) return;      // too few to read
    const [e, lo, hi] = o.rr.map((r) => (r - 1) * 100);
    const perYear = (o.after * (1 / o.rr[0] - 1)) / pooled.years;   // expected after count minus observed, a year
    const pl = o.placebo, plOk = pl.rr[1] <= 1 && pl.rr[2] >= 1;
    FIXES.push({ fix: label, m, e, lo, hi, p: o.p, plOk, pl, perYear, o, years: pooled.years }); });
  return `<li><b>${label}</b> (${when}). ${claim}</li>`;
}
const fewer = (n) => { const r = Math.round(Math.abs(n)); return r === 0 ? "about no change a year" : `about ${r} ${n > 0 ? "fewer" : "more"} people hurt a year`; };
function verdicts() {
  const m = FIXES.length, ord = [...FIXES].sort((a, b) => a.p - b.p); let ok = true;
  ord.forEach((r, i) => { r.holm = ok && r.p * (m - i) < 0.05; if (!r.holm) ok = false; });

  // Bryan: a range wholly below zero labelled "no clear drop" read as a contradiction, so a
  // drop that fails only the placebo or only Holm says which test it failed.
  FIXES.forEach((r) => { r.verdict = r.hi >= 0 ? "no clear drop" : !r.plOk ? "followed a spike" : !r.holm ? "could be chance" : "clear drop";
    r.lab = `${chg(r.o.rr[0])}, ${r.verdict}`;
    r.tip = `${r.fix}, ${r.m.toLowerCase()}: ${f0(r.o.before)} people hurt before, ${f0(r.o.after)} after, each person counted once; ${chg(r.o.rr[0])} against the rest of the city (95% range ${chg(r.o.rr[1])} to ${chg(r.o.rr[2])}), ${fewer(r.perYear)}. Placebo one window earlier: ${chg(r.pl.rr[0])} (${chg(r.pl.rr[1])} to ${chg(r.pl.rr[2])})${r.plOk ? "" : ", a change before the fix"}. ${r.holm ? "Passes" : "Doesn't pass"} the correction for ${m} rows.`; });
  return m;
}
const VCOL = { "clear drop": "#4269d0", "clear rise": "#efb118", "no clear drop": "#9aa3ad", "followed a spike": "#9aa3ad", "could be chance": "#9aa3ad" };
function forest() {
  const M_ROWS = verdicts();
  const fixes = [...new Set(FIXES.map((r) => r.fix))];
  const lo = Math.min(-50, ...FIXES.map((r) => r.lo)), hi = Math.max(25, ...FIXES.map((r) => r.hi));
  const dom = [Math.floor(lo / 25) * 25, Math.ceil(hi / 25) * 25], ticks = d3range(dom[0], dom[1] + 1, 25);
  // One numbered line per row, a header line before each fix, top to bottom.
  let pos = 0; const heads = [], R = [];
  fixes.forEach((f) => { heads.push({ fix: f, y: pos++ }); FIXES.filter((r) => r.fix === f).forEach((r) => R.push({ ...r, y: pos++ })); pos += 0.4; });
  const svg = (width, left, right, fs, cls) => {
    const rowH = 24, top = 8, bottom = 40, height = top + bottom + rowH * pos;
    const svg_ = plotSVG({ width, height, marginLeft: left, marginRight: right, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: dom, axis: null }, y: { domain: [pos - 0.9, -0.5], axis: null },
      marks: [
        Plot.gridX(ticks, { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.ruleX([0], { stroke: "#59626f" }),
        Plot.ruleY(R, { y: "y", x1: "lo", x2: "hi", stroke: (r) => VCOL[r.verdict], strokeWidth: 2.5 }),
        Plot.dot(R, { y: "y", x: "e", fill: (r) => VCOL[r.verdict], r: 5, title: "tip" }),
        Plot.text(R, { y: "y", x: dom[1], text: "lab", dx: 8, textAnchor: "start", fontSize: fs - 1, fill: (r) => (r.verdict === "clear drop" ? "var(--ink)" : "var(--muted)"), fontWeight: (r) => (r.verdict === "clear drop" ? 600 : 400) }),
        Plot.text(R, { y: "y", x: dom[0], text: (r) => (width < 500 ? SHORT[r.m] : r.m), dx: -8, textAnchor: "end", fontSize: fs - 1 }),
        Plot.axisX(width < 500 ? ticks.filter((v) => v % 50 === 0) : ticks, { tickSize: 0, tickPadding: 6, tickFormat: (v) => (v > 0 ? "+" : v < 0 ? "\u2212" : "") + Math.abs(v) + "%", label: width < 500 ? "% change in people hurt" : "% change in people hurt, against the rest of the city", labelAnchor: "center", labelArrow: false, fontSize: fs - 1 }),
      ] }, { className: "", label: "Forest plot of the % change in people hurt after each fix, against the rest of the city, with 95% ranges" });
    // Each fix's name, years and details button sit over the chart as HTML, on the header line Plot leaves empty.
    const py = (v) => top + ((v + 0.5) / (pos - 0.9 + 0.5)) * (height - top - bottom);
    const hd = heads.map((h) => { const P = POOLS.find((q) => q.fix === h.fix), i = POOLS.indexOf(P);
      return `<div class="fhead" style="top:${((100 * py(h.y)) / height).toFixed(2)}%"><b>${h.fix}</b> <span class="yrs">(${P.years})</span> <button type="button" class="info" data-pool="${i}" aria-label="Details: ${h.fix}">ⓘ</button></div>`; }).join("");
    return `<div class="fwrap ${cls}">${svg_}${hd}</div>`;
  };
  return `<div class="plotwrap forest">${svg(900, 220, 150, 13, "pl-wide")}${svg(370, 100, 120, 12, "pl-phone")}</div>`;
}
const camP = CAM.pooled, qbP = QB.pooled, tlP = QB.tenderloinPooled;
const YR = W.yearly, Y5 = ["2021", "2022", "2023", "2024", "2025"], CITY_YR = Y5.reduce((t, y) => t + YR[y].all, 0) / Y5.length;
const WALK2 = qbP.near.ped, WALK2_YR = (WALK2.after * (1 / WALK2.rr[0] - 1)) / qbP.years;
const CITE = camP.fromCitations;
// Bryan: classes 2, 3 and 4 are one "Main roads" row, beside residential streets.
const sumK = (o, ks) => ks.reduce((t, k) => t + (o[k] || 0), 0);
const byClass = [{ k: "main", name: "Main roads", ks: ["2", "3", "4"] }, { k: "5", name: "Residential streets", ks: ["5"] }]
  .map((r) => ({ ...r, hurt: sumK(A.byClass, r.ks), sev: sumK(SV.byClass, r.ks), mi: sumK(W.milesByClass, r.ks) }));
const maxHurt = Math.max(...byClass.map((r) => r.hurt));
const restHurt = A.total - byClass.reduce((t, r) => t + r.hurt, 0);
const stName = (s) => s.toLowerCase().replace(/^0+/, "").replace(/\b([a-z])/g, (m) => m.toUpperCase()).replace(/(\d)(St|Nd|Rd|Th)\b/g, (m, n, x) => n + x.toLowerCase());
const eg = (k) => (k === "main" ? W.mainExamples : W.examplesByClass[k] || []).map(stName).join(", ");
// Main roads against residential streets, drawn with Plot like every other chart here (Bryan):
// bar length is people, read off the axis, the darker part is the people severely hurt or killed
// and each label is people first with the share in parentheses.
function classChart() {
  const R = byClass.map((r) => ({ k: r.name, eg: eg(r.k), all: r.hurt, severe: r.sev, lab: `${f0(r.hurt)} people (${pct(r.hurt, A.total)})`,
    title: `${r.name}: ${f0(r.hurt)} people hurt (${pct(r.hurt, A.total)} of everyone), ${f0(r.sev)} severely hurt or killed, on ${f0(r.mi)} street miles` }));
  const svg = (width, left, fs, cls) => {
    const rowH = 46, top = 6, bottom = 34, height = top + bottom + rowH * R.length, pw = width - left;
    const step = [2000, 2500, 5000].find((st) => maxHurt / st <= Math.max(2, Math.floor(pw / 90))) || 5000, ticks = d3range(0, maxHurt + 1, step);
    const ins = { insetTop: rowH * 0.22, insetBottom: rowH * 0.22 };
    return plotSVG({ width, height, marginLeft: left, marginRight: 4, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, maxHurt * (pw < 300 ? 1.9 : 1.5)], axis: null }, y: { domain: R.map((r) => r.k), padding: 0, axis: null },
      marks: [
        Plot.gridX(ticks, { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.barX(R, { y: "k", x1: 0, x2: "all", fill: LIGHT, title: "title", ...ins }),
        Plot.barX(R, { y: "k", x1: 0, x2: "severe", fill: DARK, title: "title", ...ins }),
        Plot.text(R, { y: "k", x: "all", text: "lab", dx: 5, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        Plot.text(R, { y: "k", x: 0, text: "k", dx: -8, dy: -7, textAnchor: "end", fontSize: fs, fill: "var(--ink)" }),
        Plot.text(R, { y: "k", x: 0, text: "eg", dx: -8, dy: 9, textAnchor: "end", fontSize: fs - 2, fill: "var(--muted)", lineWidth: 40 }),
        Plot.axisX(ticks, { tickSize: 0, tickPadding: 6, tickFormat: (v) => f0(v), label: `People hurt, ${mon(W.from)} to ${mon(W.to)}`, labelAnchor: "left", labelArrow: false, fontSize: fs - 1 }),
      ] }, { className: cls, label: "Bar chart of people hurt on main roads and on residential streets" });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:${LIGHT}"></i>People hurt</span><span><i class="sw" style="background:${DARK}"></i>Of whom severely hurt or killed</span></div>
<div class="plotwrap">${svg(760, 230, 13, "pl-wide")}${svg(370, 150, 12, "pl-phone")}</div>`;
}

// One row per group, a main-road bar above a residential bar, drawn with Observable Plot (the site's plot.mjs) to static
// SVG. Bar length is people, read off the axis; the label prints people first and the share of that kind of street in
// parentheses; the darker part of each bar is the people severely hurt or killed (same hue, so lightness carries it).
// Rendered at two widths, laptop and phone, and CSS shows one.
const SPEEDPAGE = "https://www.sfmta.com/projects/speed-safety-cameras/background";
const SIDES = [{ side: "main", name: "Main roads" }, { side: "res", name: "Residential streets" }];
const LIGHT = "#b3c3ee", DARK = "#4269d0";
// Bryan: residential is its own panel beside main roads, same colours, same rows
// in the same order, and each panel its own people axis. So two Plot.plot() calls side by side (facets share scales);
// on a laptop the right panel leans on the left one's row labels, on a phone the panels stack and each carries them.
function split(o, sort, marks = {}, aria = "", outline = []) {
  const tot = (k) => o.main.rows[k].all + o.res.rows[k].all, LAST = ["other", "unknown", "none"];
  let keys = o.order.filter((k) => tot(k) > 0);
  // Bryan: most frequent first across both kinds of street, every other cause and unknown last.
  if (sort) keys = [...keys.filter((k) => !LAST.includes(k)).sort((a, b) => tot(b) - tot(a)), ...keys.filter((k) => LAST.includes(k))];
  const name = (k) => o.names[k] + (marks[k] ? ` (${marks[k]})` : "");
  const panel = (S) => `${S.name}, ${f0(o[S.side].total)} people`;
  const rows = keys.flatMap((k) => SIDES.map((S) => { const r = o[S.side].rows[k], t = o[S.side].total;
    return { k: name(k), f: panel(S), all: r.all, severe: r.severe, lab: `${f0(r.all)} people (${r.all && r.all / t < 0.005 ? "<1%" : pct(r.all, t)})`,
      motor: outline.includes(k) ? r.motor : null,
      title: `${S.name}: ${f0(r.all)} people, ${pct(r.all, t)} of the ${f0(t)} hurt there, ${f0(r.severe)} severe or fatal${outline.includes(k) ? `, ${f0(r.motor)} in a crash with a motor vehicle` : ""}` }; }));
  const svg = (sides, width, left, rowH, fs, wrap, cls) => {
    const R = rows.filter((r) => sides.some((S) => r.f === panel(S))), max = Math.max(...R.map((r) => r.all));
    const top = 26, bottom = 34, height = top + bottom + rowH * keys.length;
    const panelW = (width - left) / sides.length;
    const step = [500, 1000, 2000, 2500, 5000, 10000].find((st) => max / st <= Math.max(2, Math.floor(panelW / 80)));
    const xmax = max * (panelW < 260 ? 1.9 : 1.6), ticks = d3range(0, max + 1, step);
    const ins = { insetTop: rowH * 0.2, insetBottom: rowH * 0.2 };
    return plotSVG({ width, height, marginLeft: left, marginRight: 4, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      fx: { domain: sides.map(panel), label: null, padding: 0.06 }, x: { domain: [0, xmax], axis: null }, y: { domain: keys.map(name), padding: 0, axis: null },
      marks: [
        Plot.gridX(ticks, { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.barX(R, { fx: "f", y: "k", x1: 0, x2: "all", fill: LIGHT, title: "title", ...ins }),
        Plot.barX(R, { fx: "f", y: "k", x1: 0, x2: "severe", fill: DARK, title: "title", ...ins }),
        // Bryan: an outline, not another fill, marks the people in a crash with a motor vehicle.
        outline.length ? Plot.barX(R.filter((r) => r.motor), { fx: "f", y: "k", x1: 0, x2: "motor", fill: "none", stroke: "#15181c", strokeWidth: 1.5, title: "title", ...ins }) : null,
        Plot.text(R, { fx: "f", y: "k", x: "all", text: "lab", dx: 5, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        Plot.axisFx({ anchor: "top", tickSize: 0, fontSize: fs, fontWeight: 600, textAnchor: "start", dx: -panelW / 2 + 4, label: null }),
        Plot.axisX(ticks, { tickSize: 0, tickPadding: 6, tickFormat: (v) => f0(v), label: "People hurt", labelAnchor: "left", labelArrow: false, fontSize: fs - 1 }),
        left > 20 ? Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs, lineWidth: wrap, label: null }) : null,
      ] }, { className: cls, label: aria });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:${LIGHT}"></i>People hurt</span><span><i class="sw" style="background:${DARK}"></i>Of whom severely hurt or killed</span>${outline.length ? `<span><i class="sw" style="background:none;border:1.5px solid #15181c;width:16px"></i>A car, truck, motorcycle or Muni was also in the crash</span>` : ""}</div>
<div class="plotwrap"><div class="pl-wide">${svg([SIDES[0]], 600, 250, 30, 13, 18, "")}${svg([SIDES[1]], 350, 10, 30, 13, 18, "")}</div><div class="pl-phone">${SIDES.map((S) => svg([S], 370, 140, 40, 12, 11, "")).join("")}</div></div>`;
}
// Everyone hurt by their own mode, citywide, one panel (Bryan), plus each mode's share of the people
// severely hurt or killed beside its share of trips in SFMTA's Travel Decision Survey 2021 (p. 5, Estimated Mode Share).
const TDS = { year: 2021, url: "https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf",
  // walk 24, bicycle 3, public transit 10; cars are SFMTA's own "Privately Owned Vehicles" 62: drive alone (which includes motorcycle) 36 + carpool 25 + TNC 2
  share: { walk: 24, bike: 3, transit: 10, drive: 62 }, daily: 4380121 };
function ownChart(o) {
  const keys = o.order.filter((k) => o.rows[k].all > 0), name = (k) => o.names[k];
  const R = keys.map((k) => ({ k: name(k), all: o.rows[k].all, severe: o.rows[k].severe, lab: `${f0(o.rows[k].all)} people (${pct(o.rows[k].all, o.total)})`,
    title: `${name(k)}: ${f0(o.rows[k].all)} people hurt, ${f0(o.rows[k].severe)} severely hurt or killed` }));
  const max = Math.max(...R.map((r) => r.all));
  const svg = (width, left, rowH, fs, wrap, cls) => {
    const top = 6, bottom = 34, height = top + bottom + rowH * keys.length, pw = width - left;
    const step = [1000, 2000, 2500, 5000, 10000].find((st) => max / st <= Math.max(2, Math.floor(pw / 90))) || 10000, ticks = d3range(0, max + 1, step);
    const ins = { insetTop: rowH * 0.2, insetBottom: rowH * 0.2 };
    return plotSVG({ width, height, marginLeft: left, marginRight: 4, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, max * (pw < 300 ? 1.9 : 1.5)], axis: null }, y: { domain: keys.map(name), padding: 0, axis: null },
      marks: [
        Plot.gridX(ticks, { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.barX(R, { y: "k", x1: 0, x2: "all", fill: LIGHT, title: "title", ...ins }),
        Plot.barX(R, { y: "k", x1: 0, x2: "severe", fill: DARK, title: "title", ...ins }),
        Plot.text(R, { y: "k", x: "all", text: "lab", dx: 5, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        Plot.axisX(ticks, { tickSize: 0, tickPadding: 6, tickFormat: (v) => f0(v), label: "People hurt", labelAnchor: "left", labelArrow: false, fontSize: fs - 1 }),
        Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs, lineWidth: wrap, label: null }),
      ] }, { className: cls, label: "Bar chart of people hurt by the mode they were using, citywide" });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:${LIGHT}"></i>People hurt</span><span><i class="sw" style="background:${DARK}"></i>Of whom severely hurt or killed</span></div>
<div class="plotwrap">${svg(760, 230, 30, 13, 18, "pl-wide")}${svg(370, 138, 36, 12, 11, "pl-phone")}</div>`;
}
// Share of trips against share of people severely hurt or killed, for the modes the survey counts.
function shareChart(o) {
  const keys = ["walk", "bike", "drive", "transit"], name = (k) => o.names[k];
  const sv = (k) => (100 * o.rows[k].severe) / o.severe;
  const R = keys.flatMap((k) => [{ k: name(k), g: "Share of trips", v: TDS.share[k] }, { k: name(k), g: "Share of people severely hurt or killed", v: sv(k) }]);
  const svg = (width, left, fs, wrap, cls) => {
    const rowH = 40, top = 6, bottom = 30, height = top + bottom + rowH * keys.length;
    return plotSVG({ width, height, marginLeft: left, marginRight: 4, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, 92], axis: null }, y: { domain: keys.map(name), padding: 0, axis: null },
      marks: [
        Plot.gridX([0, 20, 40, 60], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.barX(R.filter((r) => r.g === "Share of trips"), { y: "k", x1: 0, x2: "v", fill: "#c3c8cf", insetTop: 6, insetBottom: rowH / 2 + 1 }),
        Plot.barX(R.filter((r) => r.g !== "Share of trips"), { y: "k", x1: 0, x2: "v", fill: DARK, insetTop: rowH / 2 + 1, insetBottom: 6 }),
        Plot.text(R.filter((r) => r.g === "Share of trips"), { y: "k", x: "v", text: (r) => `${Math.round(r.v)}% of trips`, dx: 5, dy: -rowH / 4 + 2, textAnchor: "start", fontSize: fs - 1, fill: "var(--muted)" }),
        Plot.text(R.filter((r) => r.g !== "Share of trips"), { y: "k", x: "v", text: (r) => `${r.v < 1 ? "<1" : Math.round(r.v)}% of severe or fatal`, dx: 5, dy: rowH / 4 - 2, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)", fontWeight: 600 }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        Plot.axisX([0, 20, 40, 60], { tickSize: 0, tickPadding: 6, tickFormat: (v) => v + "%", label: null, fontSize: fs - 1 }),
        Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs, lineWidth: wrap, label: null }),
      ] }, { className: cls, label: "Each mode's share of trips beside its share of people severely hurt or killed" });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:#c3c8cf"></i>Share of trips, SFMTA ${TDS.year}</span><span><i class="sw" style="background:${DARK}"></i>Share of people severely hurt or killed</span></div>
<div class="plotwrap">${svg(760, 230, 13, 18, "pl-wide")}${svg(370, 144, 12, 11, "pl-phone")}</div>`;
}
// Share of trips against share of people hurt in a crash that involved each mode (Bryan).
// A crash with a car and a bike counts under both, so the injury shares add to more than 100%.
const INV = W.involved;
const INV_NAME = { drive: "Car, truck or motorcycle", transit: "Muni or other transit", bike: "Bike", scoot: "Scooter or board", walk: "Walking" };
function involvedChart() {
  const keys = ["drive", "transit", "bike", "scoot", "walk"];
  const R = keys.flatMap((k) => [{ k: INV_NAME[k], g: "t", v: TDS.share[k], key: k }, { k: INV_NAME[k], g: "i", v: (100 * INV.rows[k].all) / INV.total, n: INV.rows[k].all, s: INV.rows[k].severe, key: k }]);
  const lab = (r) => r.g === "t" ? (r.v == null ? "no survey share" : `${r.v}% of trips`) : `${f0(r.n)} people (${r.v < 1 ? "<1" : Math.round(r.v)}%)`;
  const inside = (r) => r.v != null && r.v > 55;
  const svg = (width, left, fs, wrap, cls) => {
    const rowH = 40, top = 6, bottom = 30, height = top + bottom + rowH * keys.length;
    const T = R.filter((r) => r.g === "t"), I = R.filter((r) => r.g === "i");
    const txt = (rows, dy, extra) => [
      Plot.text(rows.filter((r) => !inside(r)), { y: "k", x: (r) => r.v ?? 0, text: lab, dx: 5, dy, textAnchor: "start", fontSize: fs - 1, ...extra }),
      Plot.text(rows.filter(inside), { y: "k", x: "v", text: lab, dx: -5, dy, textAnchor: "end", fontSize: fs - 1, ...extra, fill: extra.inFill }),
    ];
    return plotSVG({ width, height, marginLeft: left, marginRight: 18, marginTop: top, marginBottom: bottom, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, 100], axis: null }, y: { domain: keys.map((k) => INV_NAME[k]), padding: 0, axis: null },
      marks: [
        Plot.gridX([0, 25, 50, 75, 100], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.barX(T.filter((r) => r.v != null), { y: "k", x1: 0, x2: "v", fill: "#c3c8cf", insetTop: 6, insetBottom: rowH / 2 + 1, title: (r) => `${r.k}: ${r.v}% of trips, SFMTA ${TDS.year}` }),
        Plot.barX(I, { y: "k", x1: 0, x2: "v", fill: DARK, insetTop: rowH / 2 + 1, insetBottom: 6, title: (r) => `${r.k}: in the crash for ${f0(r.n)} of ${f0(INV.total)} people hurt (${Math.round(r.v)}%), ${f0(r.s)} of them severely hurt or killed` }),
        ...txt(T, -rowH / 4 + 2, { fill: "var(--muted)", inFill: "#1f2937" }),
        ...txt(I, rowH / 4 - 2, { fill: "var(--ink)", fontWeight: 600, inFill: "white" }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        Plot.axisX([0, 25, 50, 75, 100], { tickSize: 0, tickPadding: 6, tickFormat: (v) => v + "%", label: null, fontSize: fs - 1 }),
        Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs, lineWidth: wrap, label: null }),
      ] }, { className: cls, label: "Each mode's share of trips beside the share of people hurt in a crash that involved it" });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:#c3c8cf"></i>Share of trips, SFMTA ${TDS.year}</span><span><i class="sw" style="background:${DARK}"></i>People hurt in a crash involving it</span></div>
<div class="plotwrap">${svg(760, 200, 13, 18, "pl-wide")}${svg(370, 144, 12, 11, "pl-phone")}</div>`;
}
// Yearly trend (Bryan): people hurt each year citywide, and severely hurt or killed on its own
// axis below, with program starts marked by number and listed under the chart. 2026 is a partial year, a hollow dot.
// PROGRAMS: [year, short name, sentence with its cite]. Program starts, not causes.
const QBSPAN = (() => { const ds = QB.rows.map((r) => r.start).sort(); const back = (iso) => { const t = new Date(iso + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() - 1); return t.toISOString().slice(0, 10); }; return [back(ds[0]), back(ds.at(-1))]; })();
const fy = (iso) => { const t = new Date(iso + "T12:00:00Z"), y = t.getUTCFullYear(); return y + (t - new Date(Date.UTC(y, 0, 1))) / (365.25 * 864e5); };
const SHORTLAB = { "Vision Zero adopted": "Vision Zero", "First High Injury Network": "High Injury Network", "Quick-builds": "Quick-builds", "20 mph streets": "20 mph law", "Speed cameras": "Speed cameras" };
// Each annotation gets its own lane above the line, and a side for its label, so none overlap at any width
// (Bryan). Point annotations sit in the lower lanes so their dashed lines cross no label.
const LANE = { "Speed cameras": [5500, "left"], "Vision Zero adopted": [5900, "left"], "First High Injury Network": [6300, "right"], "Quick-builds": [6700, "left"], "20 mph streets": [7100, "left"] };
const PROGRAMS = [
  [2014, "Vision Zero adopted", `Vision Zero adopted, a goal of no traffic deaths by 2024: the SFMTA Board on February 4 (<a href="https://www.sfmta.com/media/3961/download">calendar item 10</a>) and the Board of Supervisors on March 18 (<a href="https://sfgov.legistar.com/LegislationDetail.aspx?ID=1634176&GUID=94A42CE6-CD8A-4302-94C2-0DA45058FE9D">file 140047</a>). ${tag("primary — read 2026-10-20")}`, -0.25],
  [2015, "First High Injury Network", `First High Injury Network: "In 2015 all three corridor maps were combined and presented as the Vision Zero High Injury Network" (SFDPH, <a href="https://www.visionzerosf.org/wp-content/uploads/2023/03/2022_Vision_Zero_Network_Update_Methodology.pdf">2022 Network Update Methodology</a>). ${tag("primary — read 2026-10-20")}`, 0.25],
  [2019, "Quick-builds", `Quick-builds: Mayor Breed's challenge of March 6, 2019 and SFMTA Board legislation that June "to enable streamlined project delivery" (<a href="https://www.sfmta.com/media/26900/download">SFMTA Board slides, May 2021</a>) ${tag("primary — read 2026-10-20")}; the bar spans our ${QB.rows.length} corridors' completions, ${mon(QBSPAN[0])} to ${mon(QBSPAN[1])}.`, 0, () => QBSPAN],
  [2022, "20 mph streets", `State law AB 43 lets the city post 20 mph on more streets, from January 2022 (<a href="https://www.sfmta.com/node/25172">SFMTA, October 2021</a>) ${tag("primary — read 2026-10-20")}. The SFMTA Board posted ${f0(W.to20.blocks)} blocks at 20 mph, ${f0(W.to20.miles)} miles on ${W.to20.streets} streets, from ${mon(W.to20.first)} to ${mon(W.to20.last)}, ${f0(W.to20.byYear["2022"])} of them in 2022; the bar spans those Board dates. ${tag(`DataSF 3t7b-gebn — queried ${W.mainSpeed.fetched}`)} The data gives Board dates, not the day signs went up, and not the old limit. ${tag("inference — mine")}`, 0, () => [W.to20.first, W.to20.last]],
  [2025, "Speed cameras", `Speed cameras: "launched on March 20", warnings at every camera by June 6 and citations from August 5, 2025 (<a href="https://www.sfmta.com/projects/speed-safety-cameras">SFMTA</a>). ${tag("primary — read 2026-10-20")}`, 0],
];
function trendChart() {
  const ys = Object.keys(W.yearly).map(Number).filter((y) => y >= 2005), full = ys.filter((y) => y <= 2025), part = ys.filter((y) => y > 2025);
  const R = full.map((y) => ({ y, ...W.yearly[y] })), P = part.map((y) => ({ y, ...W.yearly[y] }));
  const marks = PROGRAMS.map((p, i) => { const sp = p[4] ? p[4]() : null;
    return { x: sp ? fy(sp[0]) : p[0] + (p[3] || 0), x2: sp ? fy(sp[1]) : null, n: String(i + 1), lab: SHORTLAB[p[1]] || p[1], lane: LANE[p[1]][0], side: LANE[p[1]][1], name: sp ? `${p[1]}, ${mon(sp[0])} to ${mon(sp[1])}` : `${p[0]}: ${p[1]}` }; });
  const pts = marks.filter((m) => m.x2 == null), spans = marks.filter((m) => m.x2 != null).map((m) => ({ ...m, y1: m.lane - 110, y2: m.lane + 110 }));
  const make = (width, fs, cls) => {
    const common = { width, marginLeft: 48, marginRight: 16, style: { fontFamily: "inherit", color: "var(--muted)" }, x: { domain: [2004.5, 2026.5], axis: null } };
    const xAxis = Plot.axisX(d3range(2005, 2027, width < 500 ? 5 : 3), { tickSize: 0, tickPadding: 6, tickFormat: (v) => String(v), label: null, fontSize: fs - 1 });
    const top = plotSVG({ ...common, height: 390, marginTop: 16, marginBottom: 26, y: { domain: [0, 7400], axis: null },
      marks: [
        Plot.gridY([0, 1000, 2000, 3000, 4000, 5000], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.rectX([0], { x1: 2019.5, x2: 2020.5, y1: 0, y2: 5000, fill: "#eef0f3" }),
        Plot.text([0], { x: 2020, y: 600, text: () => "COVID\ntraffic\ndrop", fontSize: fs - 3, fill: "var(--muted)", lineHeight: 1.1 }),
        Plot.ruleX(pts, { x: "x", y1: 0, y2: "lane", stroke: "#9aa3ad", strokeDasharray: "3,3" }),
        Plot.dot(pts, { x: "x", y: "lane", r: 3, fill: "#59626f", title: "name" }),
        Plot.rect(spans, { x1: "x", x2: "x2", y1: "y1", y2: "y2", fill: "#c3cde6", title: "name" }),
        ...["left", "right"].map((sd) => Plot.text(marks.filter((m) => m.side === sd), { x: "x", y: "lane", text: "lab", dx: sd === "left" ? -6 : 6, textAnchor: sd === "left" ? "end" : "start", fontSize: fs - 2, fontWeight: 600, fill: "var(--ink)", title: "name" })),
        Plot.rect(R, { x1: (r) => r.y - 0.5, x2: (r) => r.y + 0.5, y1: 0, y2: 5000, fill: "white", fillOpacity: 0, title: (r) => `${r.y}: ${f0(r.all)} people hurt; ${f0(r.severe)} (${pct(r.severe, r.all)}) severely hurt or killed, ${r.fatal} killed` }),
        Plot.line(R, { x: "y", y: "all", stroke: DARK, strokeWidth: 2.5 }),
        Plot.dot(R, { x: "y", y: "all", fill: DARK, r: 3, title: (r) => `${r.y}: ${f0(r.all)} people hurt, ${f0(r.severe)} of them severely hurt or killed (${r.fatal} killed)` }),
        Plot.dot(P, { x: "y", y: "all", stroke: DARK, fill: "white", r: 4, title: (r) => `${r.y}, January to ${mon(W.to).split(" ")[0]} only: ${f0(r.all)} people hurt` }),
        Plot.text(P, { x: "y", y: "all", text: () => "so far", dy: 14, fontSize: fs - 3, fill: "var(--muted)" }),
        Plot.axisY([1000, 2000, 3000, 4000, 5000], { tickSize: 0, tickPadding: 6, label: "People hurt a year", labelAnchor: "top", labelArrow: false, fontSize: fs - 1, tickFormat: (v) => f0(v) }),
        xAxis,
      ] }, { className: "", label: "Line chart of people hurt in reported traffic crashes in San Francisco each year since 2005" });
    const bot = plotSVG({ ...common, height: 170, marginTop: 22, marginBottom: 26, y: { domain: [0, 400], axis: null },
      marks: [
        Plot.gridY([0, 100, 200, 300, 400], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.rectX([0], { x1: 2019.5, x2: 2020.5, y1: 0, y2: 400, fill: "#eef0f3" }),
        Plot.ruleX(pts, { x: "x", y1: 0, y2: 400, stroke: "#9aa3ad", strokeDasharray: "3,3" }),
        Plot.rect(R, { x1: (r) => r.y - 0.5, x2: (r) => r.y + 0.5, y1: 0, y2: 400, fill: "white", fillOpacity: 0, title: (r) => `${r.y}: ${f0(r.severe)} severely hurt or killed (${pct(r.severe, r.all)} of ${f0(r.all)} hurt), ${r.fatal} killed` }),
        Plot.line(R, { x: "y", y: "severe", stroke: DARK, strokeWidth: 2.5 }),
        Plot.dot(R, { x: "y", y: "severe", fill: DARK, r: 3, title: (r) => `${r.y}: ${f0(r.severe)} people severely hurt or killed, ${r.fatal} of them killed` }),
        Plot.line(R, { x: "y", y: "fatal", stroke: "#9aa3ad", strokeWidth: 2 }),
        Plot.dot(R, { x: "y", y: "fatal", fill: "#9aa3ad", r: 2.5, title: (r) => `${r.y}: ${r.fatal} people killed` }),
        Plot.dot(P, { x: "y", y: "severe", stroke: DARK, fill: "white", r: 4, title: (r) => `${r.y}, so far: ${f0(r.severe)} severely hurt or killed` }),
        Plot.text([R[R.length - 1]], { x: "y", y: "fatal", text: () => "killed", dy: -10, fontSize: fs - 2, fill: "var(--muted)" }),
        Plot.axisY([100, 200, 300, 400], { tickSize: 0, tickPadding: 6, label: "Severely hurt or killed a year", labelAnchor: "top", labelArrow: false, fontSize: fs - 1 }),
        xAxis,
      ] }, { className: "", label: "Line chart of people severely hurt or killed each year since 2005, and of people killed" });
    return `<div class="${cls}">${top}${bot}</div>`;
  };
  return `<div class="plotwrap">${make(760, 13, "pl-wide stack")}${make(370, 12, "pl-phone")}</div>` +
    (PROGRAMS.length ? `<ol class="progs">${PROGRAMS.map((p) => `<li><b>${p[0]}</b> ${p[2]}</li>`).join("")}</ol>` : "");
}
// Why more people are severely hurt (Bryan, on the trend chart, 2026-10-21: "come up with ten different hypotheses
// then see if data confirms or denies"). Every figure is read from site/data/injury-severe-why.json, written by
// scripts/injury-severe-why.py. A verdict below is a sentence, so each one is guarded: if a refresh turns a figure
// the other way, the build stops instead of printing a verdict the data no longer gives.
const SW = readJson("injury-severe-why.json");
const SWE = SW.everyone, SWF = SW.flags, SWM = Object.fromEntries(SW.modes.map((m) => [m.k, m]));
const yrsSpan = (y) => `${y[0]} to ${y[1]}`;
const SWB = yrsSpan(SW.periods.before), SWA = yrsSpan(SW.periods.after), SWEARLY = yrsSpan(SW.periods.early);
const avgOf = (o, a, b) => { let t = 0; for (let y = a; y <= b; y++) t += o[String(y)]; return t / (b - a + 1); };
const HOSP = SW.hospital, HY = Object.keys(HOSP.zsfg).map(Number);
const ratio = (a, b) => { let p = 0, h = 0; for (let y = a; y <= b; y++) { p += HOSP.police[y]; h += HOSP.zsfg[y]; } return p / h; };
const R_PRE = ratio(2011, 2015), R_POST = ratio(2016, 2022);
const MINOR_B = avgOf(Object.fromEntries(Object.entries(SW.yearly).map(([y, o]) => [y, o.minor])), ...SW.periods.before);
const MINOR_A = avgOf(Object.fromEntries(Object.entries(SW.yearly).map(([y, o]) => [y, o.minor])), ...SW.periods.after);
const darkB = SWF.dark.fatBefore, darkA = SWF.dark.fatAfter, dayB = SWE.fatBefore - darkB, dayA = SWE.fatAfter - darkA;
// A year's lowest to highest quarter of people severely hurt or killed, for the 2015 step's footnote.
const qRange = (y) => { const v = [1, 2, 3, 4].map((k) => SW.quarters[`${y}Q${k}`].severe); return `${Math.min(...v)} to ${Math.max(...v)}`; };
// Years where the three death counts disagree, each printed with all three (the page names the one it charts).
const DEATH_DIFF = Object.keys(SW.yearly).filter((y) => { const a = SW.deaths.nwes[y], b = SW.deaths.vz[y], c = SW.deaths.fatalTable[y];
  return (b != null && b !== a) || (c != null && c !== a); }).map((y) => `${y} (${SW.deaths.nwes[y]} here, ${SW.deaths.vz[y] ?? "none"} in Vision Zero's report, ${SW.deaths.fatalTable[y] ?? "not covered"} in dau3-4s8f)`);
const VEH = SW.vehicle, dieP = (k) => (100 * VEH[k].fatal) / VEH[k].hurt;
const r0 = (x) => f0(x), r1 = (x) => (x >= 10 ? f0(x) : x.toFixed(1));
const clear = (zz) => Math.abs(zz) >= 1.96;
const guard = (ok, what) => { if (!ok) throw new Error(`injury page, severe section: "${what}" no longer holds; rerun tools/street-safety/injury-severe-why.py and rewrite that verdict`); };
// The police and hospital counts of people severely hurt (deaths left out, as SFDPH counts them), one shared axis.
function sevChart() {
  const P = Object.entries(SW.yearly).map(([y, o]) => ({ y: +y, v: o.severe - o.fatal })), H = HY.map((y) => ({ y, v: HOSP.zsfg[y] }));
  const make = (width, fs, cls) => plotSVG({ width, height: 260, marginLeft: 44, marginRight: width < 500 ? 70 : 120, marginTop: 20, marginBottom: 26, style: { fontFamily: "inherit", color: "var(--muted)" },
    x: { domain: [2004.5, 2025.5], axis: null }, y: { domain: [0, 650], axis: null },
    marks: [
      Plot.gridY([0, 200, 400, 600], { stroke: "var(--line)", strokeOpacity: 1 }),
      Plot.ruleX([2014.96], { y1: 0, y2: 650, stroke: "#9aa3ad", strokeDasharray: "3,3" }),
      Plot.text([0], { x: 2014.96, y: 640, text: () => (width < 500 ? "Head injury memo" : "Police head injury memo, Dec 2014"), textAnchor: "end", dx: -4, fontSize: fs - 2, fill: "var(--muted)" }),
      Plot.line(H, { x: "y", y: "v", stroke: GOLD, strokeWidth: 2.5 }),
      Plot.dot(H, { x: "y", y: "v", fill: GOLD, r: 3, title: (r) => `${r.y}: ${f0(r.v)} severely hurt, trauma center count` }),
      Plot.line(P, { x: "y", y: "v", stroke: BLUE, strokeWidth: 2.5 }),
      Plot.dot(P, { x: "y", y: "v", fill: BLUE, r: 3, title: (r) => `${r.y}: ${f0(r.v)} severely hurt, police reports` }),
      Plot.text([H.at(-1)], { x: "y", y: "v", text: (r) => (width < 500 ? `Hospital\n${r.v}` : `Trauma center, ${r.v}`), dx: 8, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)", fontWeight: 600 }),
      Plot.text([P.at(-1)], { x: "y", y: "v", text: (r) => (width < 500 ? `Police\n${r.v}` : `Police, ${r.v}`), dx: 8, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)", fontWeight: 600 }),
      Plot.text(P.filter((r) => r.y === 2014 || r.y === 2016), { x: "y", y: "v", text: (r) => String(r.v), dy: -10, fontSize: fs - 2, fill: "var(--ink)" }),
      Plot.axisY([200, 400, 600], { tickSize: 0, tickPadding: 6, label: "People severely hurt a year", labelAnchor: "top", labelArrow: false, fontSize: fs - 1 }),
      Plot.axisX(d3range(2005, 2026, width < 500 ? 5 : 3), { tickSize: 0, tickPadding: 6, tickFormat: (v) => String(v), label: null, fontSize: fs - 1 }),
    ] }, { className: cls, label: "Line chart of people severely hurt each year, from police reports since 2005 and from the trauma center's count from 2011 to 2022" });
  return `<div class="plotwrap">${make(760, 13, "pl-wide")}${make(370, 12, "pl-phone")}</div>`;
}
// People killed each year, after dark on the bottom and in daylight or at dusk above, each part printing its count.
function deathChart() {
  const R = Object.entries(SW.yearly).map(([y, o]) => ({ y: +y, dark: o.fatalDark, day: o.fatal - o.fatalDark, all: o.fatal }));
  const S = R.flatMap((r) => [{ y: r.y, k: "After dark", n: r.dark, y1: 0, y2: r.dark }, { y: r.y, k: "Daylight or dusk", n: r.day, y1: r.dark, y2: r.all }]);
  const col = { "After dark": BLUE, "Daylight or dusk": LIGHT };
  const make = (width, fs, cls) => plotSVG({ width, height: 250, marginLeft: 36, marginRight: 10, marginTop: 16, marginBottom: 26, style: { fontFamily: "inherit", color: "var(--muted)" },
    x: { domain: [2004.5, 2025.5], axis: null }, y: { domain: [0, Math.max(46, ...R.map((r) => r.all + 3))], axis: null },
    marks: [
      Plot.gridY([0, 10, 20, 30, 40], { stroke: "var(--line)", strokeOpacity: 1 }),
      Plot.rect(S, { x1: (r) => r.y - 0.38, x2: (r) => r.y + 0.38, y1: "y1", y2: "y2", fill: (r) => col[r.k], title: (r) => `${r.y}: ${r.n} killed ${r.k === "After dark" ? "after dark" : "in daylight or at dusk"}` }),
      Plot.text(R, { x: "y", y: "dark", text: (r) => String(r.dark), dy: 8, fontSize: fs - (width < 500 ? 4 : 3), fill: "white", fontWeight: 600 }),
      Plot.text(R, { x: "y", y: "all", text: (r) => String(r.all), dy: -7, fontSize: fs - (width < 500 ? 4 : 3), fill: "var(--ink)" }),
      Plot.axisY([10, 20, 30, 40], { tickSize: 0, tickPadding: 6, label: "People killed a year", labelAnchor: "top", labelArrow: false, fontSize: fs - 1 }),
      Plot.axisX(d3range(2005, 2026, width < 500 ? 5 : 3), { tickSize: 0, tickPadding: 6, tickFormat: (v) => String(v), label: null, fontSize: fs - 1 }),
    ] }, { className: cls, label: "Stacked bar chart of people killed each year since 2005, after dark and in daylight" });
  return `<div class="legend"><span><i class="sw" style="background:${BLUE}"></i>Killed after dark (count inside the bar)</span><span><i class="sw" style="background:${LIGHT}"></i>In daylight or at dusk (year's total on top)</span></div>
<div class="plotwrap">${make(760, 13, "pl-wide")}${make(370, 12, "pl-phone")}</div>`;
}
// The ten reasons, one row each: the verdict and the figure that decides it.
const VCLS = { Confirmed: "v-yes", Partly: "v-part", Denied: "v-no", "Can't tell": "v-cant" };
const ab = (o, key = "sev", f = r0) => `${f(o[key + "Before"])} a year to ${f(o[key + "After"])}`;
const SEVEN = (zz) => (clear(zz) ? "bigger than chance" : "could be chance");
// Deaths against the ten-year EARLY span: a rate test of a five-year count against a ten-year one.
const zEarly = (o) => { const e = o.fatEarly * 10, a = o.fatAfter * 5; return (a / 5 - e / 10) / Math.sqrt(a / 25 + e / 100); };
const SOB = SW.soberUnknownFatal, sobP = (k) => pct(SOB[k].unknown, SOB[k].drivers);
const NC = SW.deathsNoCause;
guard(R_POST > R_PRE + 0.05, "police count rose against the hospital's");
guard(!clear(SWE.fatZ) && !clear(zEarly(SWE)), "deaths overall within chance against both earlier spans");
guard(clear(SWF.dark.fatZ) && !clear(zEarly(SWF.dark)) && darkA > darkB, "after dark: clear against 2015-19 only");
guard(clear(SWF.speed.fatZ) && !clear(zEarly(SWF.speed)), "speed: deaths back to the early level");
guard(NC.after < NC.before, "fewer deaths with no cause stated");
guard(SWM.walk.shareAfter > SWM.walk.shareBefore, "a larger share of people walking severely hurt");
guard(Math.abs(SWF.older.fatAfter - SWF.older.fatBefore) < 1.5, "older people's deaths stayed");
guard(!clear(zEarly(SWE)) && !clear(zEarly(SWF.dark)), "neither rise clear against the early span");
guard(clear(SWM.scoot.z) && !clear(SWM.moto.z) && !clear(SWM.bike.z), "scooters rose, motorcycles and bikes didn't");
guard(!clear(SWF.older.z) && !clear(SWF.main.z) && !clear(SWF.hin.z) && !clear(SWF.ramp.z), "the denied rows stay unclear");
guard(!clear(SWF.unknownDriver.z) && !clear(SWF.unknownDriver.fatZ), "unidentified drivers flat");
guard(clear(SWM.walk.z) && SWM.walk.sevAfter < SWM.walk.sevBefore, "fewer people walking severely hurt");
guard(dieP("suv") > 1.5 * dieP("car"), "SUVs deadlier per person hit");
guard(SOB.after.unknown / SOB.after.drivers > 0.4, "sobriety mostly unknown in fatal crashes");
const thru = (o, f = r1) => `${f(o.fatEarly)} a year from ${SWEARLY}, ${f(o.fatBefore)} from ${SWB} and ${f(o.fatAfter)} from ${SWA}`;
const TEN = [
  ["Police changed how they rate injuries", "Confirmed", `For 2016 on. Police counted ${f0(HOSP.police["2015"])} people severely hurt in 2015 to the trauma center's ${f0(HOSP.zsfg["2015"])}, and ${f0(HOSP.police["2022"])} in 2022 to its ${f0(HOSP.zsfg["2022"])}. That's ${pct(R_PRE * 100, 100)} of the hospital's count from 2011 to 2015 and ${pct(R_POST * 100, 100)} from 2016 to 2022.`],
  ["Drivers going faster", "Partly", `Deaths in crashes police blamed on unsafe speed ran ${thru(SWF.speed)}, so they're back to where they were before the dip. Fewer deaths now have no cause stated (${NC.before} from ${SWB}, ${NC.after} from ${SWA}), which could account for some of it.`],
  ["Bigger vehicles, like SUVs and trucks", "Can't tell", `They're deadlier, but we can't see a trend. From 2022 to ${SW.periods.after[1]}, ${f0(VEH.suv.fatal)} of ${f0(VEH.suv.hurt)} people walking or biking hit by an SUV, pickup or van died (${dieP("suv").toFixed(1)}%), against ${f0(VEH.car.fatal)} of ${f0(VEH.car.hurt)} hit by a car (${dieP("car").toFixed(1)}%). Police coded ${pct(SW.suvCoded["2021"] * 100, 100)} of drivers as in an SUV in 2021 and ${pct(SW.suvCoded["2022"] * 100, 100)} in 2022, too fast to be the fleet, so earlier years can't be compared.`],
  ["Scooters, e-bikes and motorcycles", "Partly", `Scooters, yes. People on a scooter or board severely hurt or killed went from ${ab(SWM.scoot, "sev", r1)}. Motorcycles and mopeds went from ${ab(SWM.moto)}, and bikes and e-bikes from ${ab(SWM.bike)}.`],
  ["Darkness", "Partly", `Deaths after dark ran ${thru(SWF.dark)}. That's a clear rise against ${SWB} but not against ${SWEARLY}. Daytime deaths ran ${r1(SWE.fatEarly - SWF.dark.fatEarly)}, ${r1(dayB)} and ${r1(dayA)} a year over the same spans.`],
  ["Older people being hit", "Denied", `People 65 and older severely hurt or killed went from ${ab(SWF.older)}, which ${SEVEN(SWF.older.z)}. Deaths stayed at ${r1(SWF.older.fatAfter)} a year.`],
  ["More hit-and-runs", "Can't tell", `The public data has no hit-and-run field. Crashes where the report leaves the driver's age blank, our stand-in, went from ${ab(SWF.unknownDriver)} people severely hurt or killed, but blank ages are getting more common for every kind of crash.`],
  ["Where crashes happen", "Denied", `On main roads, ${ab(SWF.main)}. On the <a href="#map-section">High Injury Network</a>, the streets the city found have the most severe crashes, ${ab(SWF.hin)}. At freeway ramps, ${ab(SWF.ramp, "sev", r1)}.`],
  ["Who gets hurt: walking, biking or in a car", "Denied", `People walking severely hurt or killed fell from ${ab(SWM.walk)}, though a larger share of the people hurt walking were severely hurt (${(100 * SWM.walk.shareBefore).toFixed(0)}% to ${(100 * SWM.walk.shareAfter).toFixed(0)}%). People biking went from ${ab(SWM.bike)}, and people in cars and trucks from ${ab(SWM.car)}.`],
  ["Drunk or drugged driving", "Can't tell", `The report doesn't say whether the driver was impaired for ${f0(SOB.after.unknown)} of ${f0(SOB.after.drivers)} drivers in deadly crashes from ${SWA} (${sobP("after")}), up from ${sobP("before")} in ${SWB} and ${sobP("early")} in ${SWEARLY}.`],
];
function tenTable() {
  return `<table class="pertrip ten"><thead><tr><th>Reason</th><th>Verdict</th><th>What decides it</th></tr></thead><tbody>
${TEN.map(([h, v, f]) => `<tr><td><b>${h}</b></td><td data-h="Verdict"><span class="vd ${VCLS[v]}">${v}</span></td><td data-h="What decides it">${f}</td></tr>`).join("\n")}
</tbody></table>`;
}
// Per trip (Bryan): per million trips by mode, for someone going out that way.
const PT = W.perTrip;
const PT_MODES = [["walk", "Walking"], ["bike", "Biking"], ["drive", "Car or truck"], ["transit", "Muni or other transit"]];
const tripsOf = (k) => (TDS.share[k] == null ? null : (TDS.daily * TDS.share[k]) / 100 * 365 * PT.years);
const perM = (n, k) => { const t = tripsOf(k); return t ? (1e6 * n) / t : null; };
const sig = (x) => (x >= 9.95 ? x.toFixed(0) : x >= 0.995 ? x.toFixed(1) : x >= 0.1 ? x.toFixed(2) : x.toFixed(3));
// Muni's people hurt : the FTA National Transit Database's riders hurt in
// safety events on a vehicle, assaults and other security events left out, agency 90015, demand response excluded.
// Major events (9ivb-8ae9) transit_vehicle_rider_injuries 95, non-major (urir-txqm) customer injuries 521, September
// 2021 to June 2026 (58 months, the latest month published), scaled to the page's window. Read 2026-10-20.
const NTD = { major: 95, nonMajor: 521, months: 58, read: "2026-10-20" };
const MUNI_HURT = ((NTD.major + NTD.nonMajor) * PT.years * 12) / NTD.months;
const rate = (k, a) => (k === "transit" && a === "hurt" ? MUNI_HURT : PT[a][k] || 0);
const BIKE_CAR_SEV = perM(rate("bike", "hurtSevere"), "bike") / perM(rate("drive", "hurtSevere"), "drive");
const CAR_BIKE_OTH = perM(rate("drive", "hurtOthers"), "drive") / perM(rate("bike", "hurtOthers"), "bike");
const PT_HEAD = `A Bike Trip Is ${Math.round(BIKE_CAR_SEV)} Times as Likely as a Car Trip to End in a Severe Injury; Car Trips Are the Likeliest to Hurt Someone Else`;
const ptSent = () => `Compared with a Muni trip, a bike trip is ${fmtX(xMuni("bike", "hurt")).replace("x", " times")} as likely to get you hurt, a car trip ${fmtX(xMuni("drive", "hurt")).replace("x", " times")} and a walk ${fmtX(xMuni("walk", "hurt")).replace("x", " times")}, and a car trip is ${fmtX(xMuni("drive", "hurtOthers")).replace("x", " times")} as likely to hurt someone else.`;
// A year of commuting (Bryan): 500 trips, the chance of at least one injury, 1-(1-p)^500.
const COMMUTE = 500;
const yearOdds = (k) => { const pr = perM(rate(k, "hurt"), k) / 1e6, q = 1 - Math.pow(1 - pr, COMMUTE), n = 1 / q, d = Math.pow(10, Math.floor(Math.log10(n)) - 1); return `1 in ${f0(Math.round(n / d) * d)}`; };
const yearOddsAt = (k, share) => { const t = (TDS.daily * share) / 100 * 365 * PT.years, pr = rate(k, "hurt") / t, n = 1 / (1 - Math.pow(1 - pr, COMMUTE)), d = Math.pow(10, Math.floor(Math.log10(n)) - 1); return `1 in ${f0(Math.round(n / d) * d)}`; };
const commuteSent = () => `Commuting for a year, about ${COMMUTE} trips, the chance of being hurt is about ${yearOdds("bike")} by bike, ${yearOdds("drive")} by car and ${yearOdds("walk")} on foot.`;
// At-fault vehicle body (Bryan): people hurt outside the vehicle, by its stwd_vehicle_type group.
const BODY_ROWS = [["car", "Passenger car"], ["suv", "SUV"], ["pickup", "Pickup, van or minivan"], ["big", "Truck, bus or commercial"], ["moto", "Motorcycle or moped"]];
const BODY_HEAD = "Car, truck or motorcycle at fault, by type: people hurt outside it";
function bodyChart() {
  const B = PT.byBody, R = BODY_ROWS.map(([k, name]) => ({ name, ...B[k] }));
  const svg = (width, left, fs, wrap, cls) => plotSVG({ width, height: 44 + 30 * R.length, marginLeft: left, marginRight: 150, marginTop: 26, marginBottom: 10, style: { fontFamily: "inherit", color: "var(--muted)" },
    x: { domain: [0, Math.max(...R.map((r) => r.all))], axis: null }, y: { domain: R.map((r) => r.name), padding: 0.3, axis: null },
    marks: [
      Plot.barX(R, { y: "name", x1: 0, x2: "all", fill: LIGHT, title: (r) => `${r.name} at fault: ${f0(r.all)} people hurt outside it, ${f0(r.severe)} (${pct(r.severe, r.all)}) severely hurt or killed` }),
      Plot.text(R, { y: "name", x: "all", text: (r) => `${f0(r.all)} people`, dx: 5, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
      Plot.ruleX([0], { stroke: "#9aa3ad" }),
      Plot.text([BODY_HEAD], { frameAnchor: "top-left", dx: -left + 14, dy: -20, text: (t) => t, fontSize: fs - 1, fontWeight: 600, fill: "var(--ink)", textAnchor: "start", lineWidth: width < 500 ? 46 : 80 }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs - 1, lineWidth: wrap, label: null, tickFormat: (t) => "\u21b3 " + t }),
    ] }, { className: cls, label: "Bar chart of people hurt by the type of vehicle marked at fault" });
  return `<div class="plotwrap">${svg(620, 170, 13, 18, "pl-wide")}${svg(370, 144, 12, 11, "pl-phone")}</div>`;
}
// Who hurts whom (Bryan): single at-fault party's mode by the injured person's mode, counts,
// shaded by one quantity on a white-to-teal ramp (log of the count), every cell printing its count.
const G = PT.grid, g = (r, c) => (G[r + "|" + c] || { all: 0, severe: 0 });
const G_ROWS = [["drive", "Driving a car, truck or motorcycle"], ["transit", "Muni or other transit"], ["bikeself", "Biking, the rider hurt"], ["bike", "Biking, others hurt"], ["scoot", "Scooter or board"], ["walk", "Walking"], ["none", "No one at fault, or unknown"]];
const G_COLS = [["walk", "Walking"], ["bike", "Biking"], ["scoot", "Scooter or board"], ["veh", "In a vehicle"]];
const FC = PT.faultCodes.bike, fcN = (...ks) => ks.reduce((t, k) => t + (FC[k] || 0), 0);
const BIKE_CAUSES = [["unsafe speed", fcN("22350")], ["running a red light", fcN("21453(a)")], ["an unsafe turn or lane change", fcN("22107")], ["riding on the wrong side or against traffic", fcN("21650.1", "21650", "21657")], ["running a stop sign", fcN("22450(a)")]];
const colTot = (c) => G_ROWS.reduce((t, [r]) => t + g(r, c).all, 0), rowTot = (r) => G_COLS.reduce((t, [c]) => t + g(r, c).all, 0);
function whoGrid() {
  const max = Math.max(...Object.values(G).map((o) => o.all)), sh = (n) => Math.round(6 + 84 * Math.log(n + 1) / Math.log(max + 1));
  return `<table class="grid"><thead><tr><th>At fault</th>${G_COLS.map(([, n]) => `<th>${n} hurt</th>`).join("")}</tr></thead><tbody>
${G_ROWS.map(([r, rn]) => `<tr><td><b>${rn}</b></td>${G_COLS.map(([c, cn]) => { const o = g(r, c), p = sh(o.all);
    return `<td${p > 55 ? ' class="dk"' : ""} data-h="${cn} hurt" title="${rn} at fault, ${cn.toLowerCase()} hurt: ${f0(o.all)} people, ${f0(o.severe)} severely hurt or killed" style="background:color-mix(in srgb, var(--seq-3) ${p}%, white);color:${p > 55 ? "white" : "var(--ink)"}">${f0(o.all)}</td>`; }).join("")}</tr>`).join("\n")}
</tbody></table>`;
}
// Micromorts per trip (Bryan): deaths per million trips by own mode, exact Poisson 95% range,
// against reference activities from Wikipedia's Micromort page (read 2026-10-20), on a log scale.
const MM_REF = [["A day of living, US", 22, "all causes, US, 2010, CDC"], ["A skydiving jump", 8, "US, USPA, 2000 to 2016"],
  ["A day, non-natural, US", 1.6, "accidents, suicide and homicide, US, 2010, CDC"], ["A 1,000-mile flight", 1, "Howard: 1,000 miles by jet is one micromort"],
  ["Smoking one cigarette", 0.71, "Howard, 1979: 1.4 cigarettes is one micromort, so one is 1/1.4"],
  ["Radiation, 2,500-mile flight", 0.42, "Howard, 1979: 6,000 miles by jet is one micromort of cancer from cosmic radiation, times 2,500/6,000"],
  ["A glass of wine", 0.3, "Howard, 1979: half a liter of wine is one micromort, so a 5-ounce glass is 148/500"],
  ["A 3-mile bike ride, UK", 0.068, "GOV.UK 2024: 44 miles by bike is one micromort, times 3/44"], ["A 1-mile walk, UK", 0.033, "GOV.UK 2024: 30 miles walked is one micromort, times 1/30"],
  ["A 10-mile drive, UK", 0.027, "GOV.UK 2024: 370 miles by car is one micromort, times 10/370"],
  ["A charcoal-grilled steak", 0.01, "Howard, 1979: 100 charcoal-broiled steaks is one micromort"]];
const mmOf = (k) => { const t = tripsOf(k); return { v: (1e6 * (PT.killed[k] || 0)) / t, lo: (1e6 * PT.killedCI[k][0]) / t, hi: (1e6 * PT.killedCI[k][1]) / t, n: PT.killed[k] || 0 }; };
const MM_ALL = (1e6 * Object.values(PT.killed).reduce((a, b) => a + b, 0)) / (TDS.daily * 365 * PT.years);
const mmFmt = (x) => (x >= 10 ? f0(x) : x >= 1 ? String(+x.toPrecision(2)) : x.toPrecision(2));
function mmChart() {
  const SHORTM = { walk: "A walk", bike: "A bike trip", drive: "A car trip", transit: "A Muni trip" };
  const SF = PT_MODES.map(([k]) => ({ name: SHORTM[k], sf: true, ...mmOf(k) }));
  const RF = MM_REF.map(([name, v, src]) => ({ name, sf: false, v, src }));
  const R = [...RF, ...SF];
  const svg = (width, left, fs, wrap, cls) => plotSVG({ width, height: 30 + (width < 500 ? 36 : 28) * R.length, marginLeft: left, marginRight: 46, marginTop: 6, marginBottom: 30, style: { fontFamily: "inherit", color: "var(--muted)" },
    x: { type: "log", domain: [1e-5, 300], axis: null }, y: { domain: R.map((r) => r.name), padding: 0.4, axis: null },
    marks: [
      Plot.gridX([1e-4, 1e-3, 1e-2, 0.1, 1, 10, 100], { stroke: "var(--line)", strokeOpacity: 1 }),
      Plot.ruleY(SF, { y: "name", x1: "lo", x2: "hi", stroke: DARK, strokeWidth: 2 }),
      Plot.dot(SF, { y: "name", x: "v", r: 5, fill: DARK, title: (r) => `${r.name}: ${mmFmt(r.v)} micromorts (95% range ${mmFmt(r.lo)} to ${mmFmt(r.hi)}), ${r.n} killed in five years` }),
      Plot.dot(RF, { y: "name", x: "v", r: 5, symbol: "square", fill: "#9aa3ad", title: (r) => `${r.name}: ${r.v} micromorts (${r.src})` }),
      Plot.text(R, { y: "name", x: (r) => (r.sf ? r.hi : r.v), text: (r) => mmFmt(r.v), dx: 8, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
      Plot.axisX(width < 500 ? [1e-4, 1e-2, 1, 100] : [1e-4, 1e-3, 1e-2, 0.1, 1, 10, 100], { tickSize: 0, tickPadding: 6, tickFormat: (v) => String(v), label: null, fontSize: fs - 1 }),
      Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs - 1, lineWidth: wrap, label: null }),
    ] }, { className: cls, label: "Dot chart of micromorts per trip by mode in San Francisco against reference activities, log scale" });
  return `<div class="legend split-key"><span><i class="sw" style="background:${DARK}"></i>One trip in San Francisco, with its 95% range</span><span><i class="sw" style="background:#9aa3ad"></i>Reference activity</span><span>Micromorts, log scale</span></div>
<div class="plotwrap">${svg(760, 250, 13, 26, "pl-wide")}${svg(370, 142, 12, 13, "pl-phone")}</div>`;
}
// Bars (Bryan): three panels, a rate per million trips per mode, the darker part severe or
// killed, each bar labelled "1 in N trips".
// Muni as the 1x baseline (Bryan): a rate as a multiple of Muni's on the same measure.
const xMuni = (k, a) => perM(rate(k, a), k) / perM(rate("transit", a), "transit");
const fmtX = (x) => (x >= 10 ? f0(Math.round(x / Math.pow(10, Math.floor(Math.log10(x)) - 1)) * Math.pow(10, Math.floor(Math.log10(x)) - 1)) : x.toFixed(1).replace(/\.0$/, "")) + "x";
const per10M = (r) => { const v = r * 10; if (v < 1) return v.toFixed(1); const d = Math.pow(10, Math.floor(Math.log10(v)) - 1); return (Math.round(v / d) * d).toLocaleString("en-US", { maximumFractionDigits: 1 }); };
const oneInN = (r) => { const n = 1e6 / r, p = Math.pow(10, Math.floor(Math.log10(n)) - 1); return `1 in ${f0(Math.round(n / p) * p)}`; };
function perTripTable() {
  const PANELS = [["crashParties", null, "Be in a Crash"], ["hurt", "hurtSevere", "Get Hurt or Killed"], ["hurtOthers", "hurtOthersSevere", "Hurt Someone Else"]];
  const names = PT_MODES.map((m) => m[1]);
  const panel = ([a, sev, title], width, left, fs, wrap, showY) => {
    const R = PT_MODES.map(([k, name]) => ({ k, name, v: perM(rate(k, a), k), n: rate(k, a), s: sev ? rate(k, sev) : null, sv: sev ? perM(rate(k, sev), k) : null }));
    const max = Math.max(...R.map((r) => r.v)), rowH = 34;
    const tip = (r) => `${r.name}, ${title.toLowerCase()}: ${fmtX(xMuni(r.k, a))} a Muni trip, ${per10M(r.v)} per 10 million trips, ${f0(r.n)} in five years${r.k === "transit" && a === "hurt" ? `, from the federal transit safety data. Police reports alone: ${f0(PT.hurt.transit)} people hurt on Muni, ${per10M(perM(PT.hurt.transit, "transit"))} per 10 million trips` : r.s != null ? `. Severely hurt or killed: ${per10M(r.sv)} per 10 million trips, ${f0(r.s)} in five years` : ""}`;
    return plotSVG({ width, height: 30 + rowH * R.length, marginLeft: left, marginRight: 92, marginTop: 22, marginBottom: 8, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, max], axis: null }, y: { domain: names, padding: 0.3, axis: null },
      marks: [
        Plot.text([title], { frameAnchor: "top-left", dy: -16, text: (t) => t, fontSize: fs, fontWeight: 600, fill: "var(--ink)" }),
        Plot.barX(R, { y: "name", x1: 0, x2: "v", fill: LIGHT, title: tip }),
        Plot.text(R, { y: "name", x: "v", text: (r) => fmtX(xMuni(r.k, a)), dx: 5, textAnchor: "start", fontSize: fs - 1, fill: "var(--ink)" }),
        Plot.ruleX([0], { stroke: "#9aa3ad" }),
        showY ? Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: fs - 1, lineWidth: wrap, label: null }) : null,
      ] }, { className: "", label: `Bar chart, ${title.toLowerCase()}, per million trips by mode` });
  };
  return `<div class="legend split-key"><span><i class="sw" style="background:${LIGHT}"></i>Compared with a Muni trip (Muni = 1x)</span></div>
<div class="plotwrap"><div class="pl-wide">${PANELS.map((P, i) => panel(P, i ? 230 : 370, i ? 8 : 148, 13, 14, !i)).join("")}</div><div class="pl-phone">${PANELS.map((P) => panel(P, 370, 122, 12, 11, true)).join("")}</div></div>`;
}
// Why fewer since 2020 (Bryan): 2015-19 against 2021-25 a year, by group.
const STEP = W.step.split;
const stepCh = (k, v) => { const o = STEP[k][v]; return o.post / o.pre - 1; };
const STEP_ROWS = [["degree", [["Complaint of Pain", "Complaint of pain"], ["Other Visible Injury", "Other visible injury"], ["Severe Injury", "Severe injury"], ["Fatal Injury", "Killed"]]],
  ["tod", [["commute", "7 to 10 AM and 4 to 7 PM"], ["other", "Other daytime hours"], ["night", "10 PM to 6 AM"]]],
  ["day", [["weekday", "Weekdays"], ["weekend", "Weekends"]]],
  ["area", [["downtown", "Downtown box"], ["rest", "Rest of the city"]]],
  ["role", [["Driver", "Driving"], ["Passenger", "Passenger"], ["Pedestrian", "Walking"], ["Bicyclist", "Biking"], ["Other", "Other, mostly scooters"]]]];
function stepTable() {
  return `<table class="pertrip"><thead><tr><th>Group</th><th>2015 to 2019, a year</th><th>2021 to 2025, a year</th><th>Change</th></tr></thead><tbody>
${STEP_ROWS.flatMap(([k, rows]) => rows.map(([v, name]) => `<tr><td><b>${name}</b></td><td data-h="2015 to 2019, a year">${f0(STEP[k][v].pre)}</td><td data-h="2021 to 2025, a year">${f0(STEP[k][v].post)}</td><td data-h="Change">${chg(1 + stepCh(k, v))}</td></tr>`)).join("\n")}
</tbody></table>`;
}
// Time of day (Bryan): people hurt per day by the crash's hour, weekday and weekend lines, and
// below it the share severely hurt or killed by hour, all days together.
const TOD = W.tod;
const hourLab = (h) => (h === 0 ? "12 AM" : h < 12 ? `${h} AM` : h === 12 ? "12 PM" : `${h - 12} PM`);
function todChart() {
  const per = ["wd", "we"].flatMap((g) => TOD.hours[g].all.map((n, h) => ({ g: g === "wd" ? "Weekdays" : "Weekends", h, v: n / TOD.days[g], n })));
  const sv = TOD.hours.wd.all.map((n, h) => { const a = n + TOD.hours.we.all[h], s = TOD.hours.wd.severe[h] + TOD.hours.we.severe[h]; return { h, v: (100 * s) / a, s, a }; });
  const col = { Weekdays: "#4269d0", Weekends: "#efb118" };
  const peak = (g) => per.filter((r) => r.g === g).reduce((a, b) => (b.v > a.v ? b : a));
  const make = (width, fs, cls) => {
    const top = plotSVG({ width, height: 230, marginLeft: 44, marginRight: 14, marginTop: 22, marginBottom: 26, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [0, 23], axis: null }, y: { domain: [0, 0.95], axis: null },
      marks: [
        Plot.gridY([0, 0.25, 0.5, 0.75], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.rect(d3range(0, 24, 1), { x1: (h) => h - 0.5, x2: (h) => h + 0.5, y1: 0, y2: 0.95, fill: "white", fillOpacity: 0,
          title: (h) => { const a = per.find((r) => r.g === "Weekdays" && r.h === h), b = per.find((r) => r.g === "Weekends" && r.h === h);
            return `${hourLab(h)}: ${a.v.toFixed(2)} people hurt a weekday (${f0(a.n)} in all), ${b.v.toFixed(2)} a weekend day (${f0(b.n)}); ${f0(sv[h].s)} of ${f0(sv[h].a)} severely hurt or killed (${Math.round(sv[h].v)}%)`; } }),
        Plot.line(per, { x: "h", y: "v", z: "g", stroke: (r) => col[r.g], strokeWidth: 2.5 }),
        Plot.dot(per, { x: "h", y: "v", fill: (r) => col[r.g], r: 2.5, title: (r) => `${r.g}, ${hourLab(r.h)}: ${r.v.toFixed(2)} people hurt a day (${f0(r.n)} in all)` }),
        Plot.axisY([0.25, 0.5, 0.75], { tickSize: 0, tickPadding: 6, label: "People hurt per day of that type", labelAnchor: "top", labelArrow: false, fontSize: fs - 1, tickFormat: (v) => v.toFixed(2) }),
        Plot.axisX([0, 3, 6, 9, 12, 15, 18, 21], { tickSize: 0, tickPadding: 6, tickFormat: hourLab, label: null, fontSize: fs - 1 }),
      ] }, { className: "", label: "Line chart of people hurt per day by hour, weekdays and weekends" });
    const bot = plotSVG({ width, height: 170, marginLeft: 44, marginRight: 14, marginTop: 22, marginBottom: 26, style: { fontFamily: "inherit", color: "var(--muted)" },
      x: { domain: [-0.5, 23.5], axis: null }, y: { domain: [0, 20], axis: null },
      marks: [
        Plot.gridY([0, 5, 10, 15], { stroke: "var(--line)", strokeOpacity: 1 }),
        Plot.rectY(sv, { x1: (r) => r.h - 0.38, x2: (r) => r.h + 0.38, y1: 0, y2: "v", fill: DARK, title: (r) => `${hourLab(r.h)}: ${f0(r.s)} of ${f0(r.a)} severely hurt or killed (${Math.round(r.v)}%)` }),
        Plot.axisY([5, 10, 15], { tickSize: 0, tickPadding: 6, label: "Share severely hurt or killed, all days", labelAnchor: "top", labelArrow: false, fontSize: fs - 1, tickFormat: (v) => v + "%" }),
        Plot.axisX([0, 3, 6, 9, 12, 15, 18, 21], { tickSize: 0, tickPadding: 6, tickFormat: hourLab, label: null, fontSize: fs - 1 }),
      ] }, { className: "", label: "Bar chart of the share of people hurt who were severely hurt or killed, by hour" });
    return `<div class="${cls}">${top}${bot}</div>`;
  };
  const pk = (g) => { const r = peak(g); return `peak ${r.v.toFixed(2)} a day at ${hourLab(r.h)}`; };
  return `<div class="legend split-key"><span><i class="ln" style="background:${col.Weekdays}"></i>Weekdays, ${pk("Weekdays")}</span><span><i class="ln" style="background:${col.Weekends}"></i>Weekends, ${pk("Weekends")}</span></div>
<div class="plotwrap">${make(760, 13, "pl-wide stack")}${make(370, 12, "pl-phone")}</div>`;
}
// People hurt where they were the one marked at fault (Bryan): per window year, September to August.
const SH = W.selfHurt, BW = W.bikeWhy;
const shCode = (g, test) => SH[g].codes.reduce((t, [c, n]) => t + (test(c) ? n : 0), 0);
const SH_BIKE = [["unsafe speed", shCode("bike", (c) => c === "22350")], ["a red light", shCode("bike", (c) => c === "21453(a)")], ["an unsafe turn or lane change", shCode("bike", (c) => c === "22107")],
  ["riding against traffic or on the wrong side", shCode("bike", (c) => ["21650.1", "21650", "21657"].includes(c))], ["a stop sign", shCode("bike", (c) => c === "22450(a)")]].sort((a, b) => b[1] - a[1]);
const SH_WALK = [["crossing outside a crosswalk", shCode("walk", (c) => c.startsWith("21954"))], ["a red or don't-walk signal", shCode("walk", (c) => c.startsWith("21453(d)") || c.startsWith("21456"))],
  ["crossing between signals", shCode("walk", (c) => c.startsWith("21955"))], ["stepping suddenly into a vehicle's path", shCode("walk", (c) => c === "21950(b)")]].sort((a, b) => b[1] - a[1]);
const andList = (xs) => xs.map(([n, c]) => `${n} (${f0(c)})`).join(", ").replace(/, ([^,]*)$/, " and $1");
const wyLab = (y) => `${y}–${String(+y + 1).slice(2)}`;
function selfChart() {
  const ys = Object.keys(SH.bike.byYear);
  const G = [["Biking, with someone else", "#4269d0", (y) => SH.bike.byYear[y] - (SH.bike.soloByYear[y] || 0)], ["Biking, no one else involved", "#efb118", (y) => SH.bike.soloByYear[y] || 0], ["Walking", "#6cc5b0", (y) => SH.walk.byYear[y] || 0]];
  const R = G.flatMap(([g, c, f]) => ys.map((y) => ({ g, c, y: wyLab(y), v: f(y) })));
  const make = (width, fs, cls) => plotSVG({ width, height: 230, marginLeft: 36, marginRight: 30, marginTop: 16, marginBottom: 28, style: { fontFamily: "inherit", color: "var(--muted)" },
    x: { domain: ys.map(wyLab), type: "point", axis: null, inset: 20 }, y: { domain: [0, 200], axis: null },
    marks: [
      Plot.gridY([50, 100, 150, 200], { stroke: "var(--line)", strokeOpacity: 1 }),
      Plot.line(R, { x: "y", y: "v", z: "g", stroke: "c", strokeWidth: 2.5 }),
      Plot.dot(R, { x: "y", y: "v", fill: "c", r: 3, title: (r) => `${r.g}, September ${r.y.slice(0, 4)} to August 20${r.y.slice(-2)}: ${f0(r.v)} people hurt who were marked at fault` }),
      Plot.text(R.filter((r) => r.g !== "Walking"), { x: "y", y: "v", text: (r) => f0(r.v), dy: -9, fontSize: fs - 2, fill: "var(--ink)" }),
      Plot.text(R.filter((r) => r.g === "Walking"), { x: "y", y: "v", text: (r) => f0(r.v), dy: -9, fontSize: fs - 2, fill: "var(--ink)", filter: (r) => !R.some((q) => q.g === "Biking, with someone else" && q.y === r.y && Math.abs(q.v - r.v) < 12) }),
      Plot.text(R.filter((r) => r.g === "Walking" && R.some((q) => q.g === "Biking, with someone else" && q.y === r.y && Math.abs(q.v - r.v) < 12)), { x: "y", y: "v", text: (r) => f0(r.v), dy: 13, fontSize: fs - 2, fill: "var(--ink)" }),
      Plot.axisY([50, 100, 150], { tickSize: 0, tickPadding: 6, label: "People hurt a year, September to August", labelAnchor: "top", labelArrow: false, fontSize: fs - 1 }),
      Plot.axisX(ys.map(wyLab), { tickSize: 0, tickPadding: 6, label: null, fontSize: fs - 1 }),
    ] }, { className: cls, label: "Line chart of people hurt who were the party marked at fault, by year" });
  return `<div class="legend split-key">${G.map(([g, c]) => `<span><i class="ln" style="background:${c}"></i>${g}</span>`).join("")}</div>
<div class="plotwrap">${make(620, 13, "pl-wide")}${make(370, 12, "pl-phone")}</div>`;
}
const BW_DRIVE = BW.bike.fault.drive, BW_PARKED = BW.bike.fault.parked || 0;
const BW_PERMILE = (BW.bike.n / TDS.share.bike) / (BW.walk.n / TDS.share.walk);
const todShare = (hs) => { let s = 0, a = 0; hs.forEach((h) => { s += TOD.hours.wd.severe[h] + TOD.hours.we.severe[h]; a += TOD.hours.wd.all[h] + TOD.hours.we.all[h]; }); return { s, a, p: s / a }; };
const NIGHT = todShare([22, 23, 0, 1, 2, 3, 4, 5]), DAY = todShare([7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]);
const WDPEAK = TOD.hours.wd.all.indexOf(Math.max(...TOD.hours.wd.all));
const d3range = (a, b, st) => { const o = []; for (let v = a; v < b; v += st) o.push(v); return o; };
const CA = W.cause, PL = W.place, FA = W.fault, HB = W.fault.hitBy, OM = W.ownMode;
const oneIn = (k) => `1 in ${Math.round(OM.rows[k].all / OM.rows[k].severe)}`;
const svShare = (ks) => ks.reduce((t, k) => t + OM.rows[k].severe, 0) / OM.severe;
const fTot = (k) => FA.main.rows[k].all + FA.res.rows[k].all;
const FAULT_SHARE = (fTot("drive") + fTot("transit")) / (FA.main.total + FA.res.total);
const frac = (x) => { const q = [[3 / 4, "Three in Four"], [2 / 3, "Two in Three"], [1 / 2, "Half of"]].find(([v]) => Math.abs(x - v) < 0.025);
  return q ? q[1] : `${Math.round(x * 10)} in Ten`; };
const DC = (() => { const r = FA.driverCause.rows, ks = Object.keys(r).filter((k) => !["other", "unknown"].includes(k)).sort((a, b) => r[b] - r[a]);
  return { total: FA.driverCause.total, top: ks.length ? { name: CA.names[ks[0]], n: r[ks[0]] } : null }; })();
const capMain = CA.order.filter((k) => !["other", "unknown"].includes(k)).sort((a, b) => CA.main.rows[b].all - CA.main.rows[a].all);
const capRes = CA.order.filter((k) => !["other", "unknown"].includes(k)).sort((a, b) => CA.res.rows[b].all - CA.res.rows[a].all);
const TENS = ["None", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const ixMain = PL.main.rows.ix.all, ixRes = PL.res.rows.ix.all;
const corridorRows = QB.rows.map((r) => `<tr><td><b>${r.label}</b><br><span class="when">${r.extent}, ${r.pathMiles} mi. ${r.note}${r.claim in PAGES ? ` (<a href="${PAGES[r.claim]}">source</a>)` : ""}. After from ${mon(r.start)}, ${yrs(r.years)} each side</span></td>
<td data-h="Everyone at the site">${counts(r.site)}<br><span class="ivl">${cell(r.site, BLUE)} ${Math.min(r.site.before, r.site.after) < SMALL ? "too few to read" : ci(r.site)}</span></td>
<td data-h="People walking at the site">${counts(r.site.groups.ped)}<br><span class="ivl">${Math.min(r.site.groups.ped.before, r.site.groups.ped.after) < SMALL ? "too few to read" : cell(r.site.groups.ped, BLUE) + " " + ci(r.site.groups.ped)}</span></td>
<td data-h="Everyone, with two blocks">${counts(r.near)}<br><span class="ivl">${cell(r.near, GOLD)} ${ci(r.near)}</span></td>
<td data-h="Against the surrounding blocks instead">${Math.min(r.near.before, r.near.after) < SMALL ? "too few to read" : chg(r.near.rrRing[0])}</td></tr>`).join("\n");
const cameraRows = CAM.rows.map((r) => `<tr><td><b>${r.label}</b><br><span class="when">${r.limit} mph limit, ${r.cameraSites.length} camera${r.cameraSites.length > 1 ? "s" : ""}, ${r.note.replace("warnings from ", "warnings from ")}. ${yrs(r.years)} each side</span></td>
<td data-h="Everyone at the block">${counts(r.site)}<br><span class="ivl">${Math.min(r.site.before, r.site.after) < SMALL ? "too few to read" : cell(r.site, BLUE) + " " + ci(r.site)}</span></td>
<td data-h="People walking at the block">${counts(r.site.groups.ped)}<br><span class="ivl">too few to read</span></td>
<td data-h="Everyone, with two blocks">${counts(r.near)}<br><span class="ivl">${Math.min(r.near.before, r.near.after) < SMALL ? "too few to read" : cell(r.near, GOLD) + " " + ci(r.near)}</span></td>
<td data-h="Against the surrounding blocks instead">${Math.min(r.near.before, r.near.after) < SMALL ? "too few to read" : chg(r.near.rrRing[0])}</td></tr>`).join("\n");
const rising = QB.rows.filter((r) => r.near.rr[1] > 1).map((r) => r.label.replace(" quick-build", ""));
const soma = QB.rows.filter((r) => ["Howard", "Brannan", "Townsend", "California"].some((k) => r.label.startsWith(k)));

// Details panels (Bryan): every project's dates, SFMTA source, counts and a small map.
// Photos: the SFMTA headline image the site's own project data already carries (site/data/bike-history/projects.json),
// matched by hand to these corridor labels. A corridor with no row here shows no photo.
const BH = readJson("bike-history/projects.json").projects;
const PHOTO_OF = { "Folsom St quick-build": "Folsom Street Quick-Build Project", "Turk St safety project": "Turk Street Safety Project",
  "8th St safety project": "7th Street and 8th Street Safety Projects", "Valencia St pilot bikeway": "Valencia Bikeway Improvements",
  "Indiana St quick-build": "Indiana Street Bikeway Project", "Howard St quick-build": "Howard Street Quick-Build Project",
  "Brannan St quick-build": "Brannan Street Safety Project", "Townsend St corridor": "Townsend Corridor Improvement Project",
  "Central Embarcadero quick-build": "The Embarcadero 2020 Quick-Build Projects", "Anza St bike lanes": "Anza Street Bike Lanes Project",
  "Golden Gate Ave quick-build": "Golden Gate Avenue Quick-Build", "Jones St quick-build": "Jones Street Quick-Build",
  "Evans Ave quick-build": "Evans Avenue Quick-Build", "Battery St quick-build": "Battery/Sansome Quick-Build Project",
  "Sansome St quick-build": "Battery/Sansome Quick-Build Project", "17th St quick-build": "17th Street Quick-Build",
  "Bayshore Blvd quick-build": "Bayshore Boulevard Quick-Build Project", "3rd St quick-build": "3rd Street Quick-Build Project",
  "Frida Kahlo Way quick-build": "Frida Kahlo Way Quick-Build Project" };
const photoOf = (label) => { const b = BH.find((x) => x.name === PHOTO_OF[label]); return b && b.image ? b.image : null; };
const SRC = (claim) => (claim === "camera" ? CAMPAGE : claim === "tl_day" ? TL_DAY : PAGES[claim] || null);
const ALLROWS = [...CAM.rows, ...QB.rows, TL];
const cnt = (o) => ({ b: o.before, a: o.after, ch: Math.min(o.before, o.after) < SMALL ? null : chg(o.rr[0]), clear: o.rr[2] < 1 });
// SFMTA's or SFCTA's own published cost, where its project documents state one (read 2026-10-20 unless noted).
// Never estimated: a project with no row here shows "No published cost".
const COST = {
  "17th St quick-build": `$615,000 budget at SFMTA Board approval, 2024-03-05 (<a href="https://www.sfmta.com/media/38483/download?inline">staff report</a>) [primary — read 2026-10-20]`,
  "Frida Kahlo Way quick-build": `$866,000 budget at SFMTA Board approval, 2024-05-07 (<a href="https://www.sfmta.com/media/39409/download?inline">staff report</a>) [primary — read 2026-09-29]`,
  "Evans Ave quick-build": `$560,000 Prop K construction funding, SFMTA Board 2022-03-15 (<a href="https://www.sfmta.com/media/30639/download?inline">staff report</a>) [primary — read 2026-10-20]`,
  "Anza St bike lanes": `$220,000 Prop K request for Anza from 26th Ave to Arguello, SFCTA 2020-01 (<a href="https://www.sfcta.org/sites/default/files/2020-01/Anza_St_Bike_Lanes%20%5BNTIP%20Capital%5D.pdf">allocation request</a>) [primary — read 2026-10-20]`,
};
data.fx.planP.forEach((p) => { p[5] = planCost(p[0]); });
const PDATA = d.projects.map((p) => { const r = ALLROWS.find((x) => x.label === p.label && x.kind === p.kind);
  return { label: p.label, year: workYear(p.start), note: p.note.replace(/^SFMTA: /, ""), after: mon(p.start), url: SRC(p.claim),
    extent: r.extent || "", photo: photoOf(p.label), site: cnt(r.site), near: cnt(r.near), years: yrs(r.years),
    s: encodeRuns(p.site), n: encodeRuns(p.near), bounds: boundsOf([...p.site, ...p.near]),
    cost: COST[p.label] || "", extra: p.kind === "daylighting" ? `The site here is the whole Tenderloin, ${r.intersections} intersections and ${r.blocks} blocks, not single corners, and the before window holds a 2013 and 2014 spike. People walking: ${f0(r.site.groups.ped.before)} hurt before, ${f0(r.site.groups.ped.after)} after (${chg(TL.pooled.site.ped.rr[0])} against the city).` : "" }; });
const html = `${STYLE}
${MAP_HEAD}
<div class="hin">
<!--hin-body-->
<h1>Three in Four People Hurt in San Francisco Traffic Are Hurt on Main Roads</h1>
<p class="sub">Injuries to people walking fell ${chg(camP.near.ped.rr[0]).replace("\u2212", "")} near the speed cameras and ${chg(WALK2.rr[0]).replace("\u2212", "")} near the ${qbP.n} rebuilt corridors against the rest of the city, but neither can yet be told from chance once every row is tested, and injuries overall barely moved.</p>

<div class="stats">
  <div class="stat"><b>${f0(A.total)} people</b><span>injured or killed in reported crashes, ${mon(W.from)} to ${mon(W.to)}${fn(`Every victim in DataSF <a href="${VICTIMS}">nwes-mmgh</a> (police crash reports) whose injury is not "No Injury", with a location, from ${W.from} to ${W.to}. ${W.unsnapped} were more than 150 ft from any street and are left out. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)} Freeway crashes are excluded by the dataset itself.`)}</span></div>
  <div class="stat b"><b>${f0(A.main)} on main roads</b><span>${pct(A.main, A.total)} of everyone hurt${fn(`Main roads are the centerline layer's classes 2, 3 and 4: "Major street/Highway", "Arterial street" and "Collector Street", from DataSF <a href="${CENTER}">3psu-pn9h</a>, which says "The Class Code field is used for symbolization". ${tag("primary — read 2026-10-20")} A crash the report places at an intersection counts for the biggest street meeting there, so ${f0(A.freeway)} people at a ramp or freeway mouth take that class and are in neither count. ${tag(`DataSF 3psu-pn9h — queried ${d.source.centerlinesFetched}`)} That rule matters: 8,021 of the ${f0(A.main)} people counted on main roads were hurt at a corner a main road shares with a residential street, and giving each crash to its nearest centerline instead puts 60% on main roads. ${tag("inference — mine, a check run 2026-10-20")}`)}</span></div>
  <div class="stat g"><b>${f0(A.hin)} on the High Injury Network</b><span>${pct(A.hin, A.total)} of people hurt, on ${pct(W.hinMiles, W.streetMiles)} of street miles, and ${pct(A.mainAndHin, A.main)} of those hurt on main roads${fn(`Within 60 ft of SFMTA's <a href="${HIN}">2022 High Injury Network</a>, ${f0(W.hinMiles)} centerline miles. ${f0(A.mainAndHin)} of the ${f0(A.hin)} are also on a main road. SFMTA's own figure for the newer 2024 network is "13% of city street miles and 74% of severe and fatal injuries" (<a href="${DECK}">Vision Zero Committee deck</a>, May 2026, slide 7). ${tag("primary — read 2026-10-19")} Ours counts every injury on the 2022 network. For severe and fatal injuries alone: ${f0(SV.hin)} of ${f0(SV.total)}, ${pct(SV.hin, SV.total)}. ${tag("inference — mine")}`)}</span></div>
</div>

<div class="callout">
<p><b>These are police reports, and they miss four to six of every ten severe injuries.</b> In the year from April 2014 SFDPH counted 515 patients with severe traffic injuries at the city's trauma center against "~200 SFPD reported Severe Injuries", and its 2013 to 2015 record match found 59% in both records.${fn(`SFDPH, <a href="${SFDPH15}">Severe Traffic Injuries in San Francisco</a>, September 2015, p. 1: "515 Patients with Severe Injuries vs ~200 SFPD reported Severe Injuries", "515 Patients in 1 year". Streetsblog's report of the study gives the year as the twelve months from April 2014 and the definition as hospitalized more than 24 hours. ${tag("primary — read 2026-10-20")} The 2013 to 2015 linkage of the two records found "59% of records classified as severe appeared both in police and hospital data" (SFDPH, <a href="${SFDPH17}">Severe Traffic Injury Trends 2011-2017</a>, December 2018, p. 4). ${tag("primary — read 2026-10-20")} Nobody has measured the gap for minor injuries in San Francisco. ${tag("unretrieved — verify")}`)} The people the reports miss are "more often cyclists, male, Hispanic or Black", and "more than three in 10 non-fatal injuries with a critical ISS were missed (i.e. reported as non-severe)".${fn(`Soltani, Schwarcz, Morris, Plevin, Dicker, Juillard, Nwabuo and Wier, <a href="${SOLTANI}">What is counted counts</a>, Journal of Safety Research, 2022, as quoted on SFMTA's <a href="${SFMTA_LINK}">Vision Zero data update</a>. ${tag("primary — read 2026-10-20, the SFMTA quotation")} The paper itself was not opened. SFDPH's <a href="${SFDPH18}">2018 report</a>: "Severe injury in those reports is determined based on police officer's visual assessment of injury severity, not clinical determination." ${tag("primary — read 2026-10-20")}`)}</p>
<p>So the map shows where police wrote reports. A street where people fall off bikes alone, or crash without calling police, is drawn lighter than it should be. Severe injuries are counted more completely than minor ones, so the "Severe and fatal" view is the firmer one.${fn(`Nobody has measured the police gap for minor injuries in San Francisco, so the last sentence is an inference from the severe-injury studies above. ${tag("inference — mine")}`)}</p>
</div>

<h2>About ${f0(Math.round(CITY_YR / 50) * 50)} People a Year Are Still Hurt, ${pct(W.yearly["2025"].all, W.yearly["2005"].all)} of 2005's Level</h2>
<p>Each point is everyone reported hurt or killed that year, from police crash reports.${fn(`Every injured victim row in DataSF <a href="${VICTIMS}">nwes-mmgh</a> by the year of <code>collision_datetime</code>, with or without a location; severe is "Severe Injury" or "Fatal Injury". ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)} ${f0(W.yearly["2005"].all)} people were hurt in 2005 and ${f0(W.yearly["2025"].all)} in 2025, while the number severely hurt or killed went from ${f0(W.yearly["2005"].severe)} to ${f0(W.yearly["2025"].severe)}. The numbered lines are when the city started major programs, not proof they caused what follows, and part of the rise in severe injuries from 2015 is a change in how police record them. Since 2020 the drop is in minor injuries, most at weekday commute hours, while severe injuries held. Less driving, fewer people walking and biking, and a change in what gets reported could each explain part of it, and the data can't yet say which matters most. [inference — mine] SFCTA puts San Francisco's vehicle miles "around 10% below pre-COVID levels" in 2025.${fn(`SFCTA, <a href="https://www.sfcta.org/sites/default/files/2025-12/SFCTA_CMP_Report_2025_FINAL_2025-12-16.pdf">Congestion Management Program 2025</a>, p. E-17: "As of 2025, VMT is hovering at around 10% below pre-COVID levels"; p. E-11: mid-week traffic "reaching 92% of pre-COVID pandemic (2019) levels". ${tag("primary — read 2026-10-20")} From 2015 to 2019 against 2021 to 2025, people hurt walking fell ${chg(1 + stepCh("role", "Pedestrian"))}, biking ${chg(1 + stepCh("role", "Bicyclist"))} and driving ${chg(1 + stepCh("role", "Driver"))}, severe injuries changed ${chg(1 + stepCh("degree", "Severe Injury"))} and injuries from 10 PM to 6 AM ${chg(1 + stepCh("tod", "night"))}. Less driving fits the commute-hour drop, fewer people walking and biking fits those modes falling furthest, and fewer minor-injury reports fits severe injuries holding while minor ones fell. Counts of people hurt per mile walked, biked and driven by year would separate them, and we haven't found them. ${tag("inference — mine")} The split by injury, hour, day, place and mode is in <a href="#fewer">About the data</a>. SFDPH's hospital count of severe injuries, a separate source, was 533 in 2019 and 535 in 2022 (<a href="https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf">Severe Traffic Injury Trends 2015-2022</a>, Table 1). ${tag("primary — read 2026-10-20")}`)}${fn(`SFDPH, <a href="https://www.visionzerosf.org/wp-content/uploads/2019/09/Severe-Injury-Trends_2011-2018_final_report.pdf">Severe Traffic Injury Trends 2011-2018</a>, Appendix A: "a memo released to SFPD officers in Dec. 2014 advised head injuries be classified as severe to avoid under-reporting of traumatic brain injury. This guidance likely partially accounts for the increase in severe injuries recorded in police data from 2015 onward." ${tag("primary — read 2026-10-20")} The data also comes from three systems, any of whose seams could move a count: "SFPD's Interim Collision System for 2018 to YTD, Crossroads Software Traffic Collision Database (CR) for years 2013-2017 and the Statewide Integrated Transportation Record System (SWITRS) maintained by the California Highway Patrol for all years prior to 2013" (<a href="${VICTIMS}">nwes-mmgh</a> metadata). ${tag("primary — read 2026-10-20")}`)}</p>
${trendChart()}
<p class="note">Source: DataSF nwes-mmgh, 2005 to ${mon(W.to)}. ${W.to.slice(0, 4)} is January to ${mon(W.to).split(" ")[0]} only, drawn as a hollow dot. Hover a point for its count.</p>

<h2 id="map-section">Where people get hurt</h2>
<p>The heat map is every reported injury from ${mon(W.from)} to ${mon(W.to)}. Freeways like 101 and 280 aren't included: the city's data leaves out crashes on highways. Under it: the <a href="${HIN}">2022 High Injury Network</a> in dark gray. Tick a fix on the left, built or planned, to draw it, and click a line or point for its details and cost. Pick a school to see the kids hurt near it.${fn(`Heat map scaled to its own densest spot, so it shows where people are hurt, not how many. Camera points from DataSF <a href="${CAMDATA}">d5uh-bk84</a>. ${tag(`DataSF d5uh-bk84 — queried ${d.source.camerasFetched}`)} Network from SFMTA's ArcGIS layer. ${tag(`primary — read ${d.source.hinFetched}`)}`)}</p>
<div class="school-bar"><label for="school">School</label><select id="school"><option value="">All of San Francisco</option>${SCHOOLS.map((x) => ({ cds: x.cds, name: x.name })).sort((a, b) => a.name.localeCompare(b.name)).map((x) => `<option value="${x.cds}">${x.name.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</option>`).join("")}</select><button type="button" class="copy-link" id="copy-link">Copy link</button><input class="copy-url" id="copy-url" readonly hidden aria-label="Link to this view"></div>
<p class="school-line" id="school-line" hidden></p>
<div class="mapwrap"><link rel="cw-map-src" href="/embed/injuries/cw-components/map.js"><details class="lyr" id="lyr" open><summary>Layers: <span id="lyr-sum">All reported injuries</span></summary><div class="lyr-body"><fieldset><legend>Injuries</legend><label><input type="radio" name="set" value="all" checked><span>All reported injuries</span><span class="lyr-n">${f0(d.map.allPoints.length)}</span></label><label><input type="radio" name="set" value="sev"><span>Severe and fatal only</span><span class="lyr-n">${f0(d.map.severePoints.length)}</span></label><label><input type="radio" name="set" value="kid"><span>Kids on school trips</span><span class="lyr-n">${f0(d.map.kidPoints.length)}</span></label><label><input type="radio" name="set" value="kidsev"><span>Kids severely hurt or killed</span><span class="lyr-n">${f0(d.map.kidSevere.length)}</span></label></fieldset><fieldset><legend>Built fixes</legend><label class="lyr-all"><input type="checkbox" data-fx-all><span>Check all</span></label><label><input type="checkbox" name="fx" value="qb"><i class="ln" style="background:#efb118"></i><span>Quick-build corridors, 2018 to 2024</span></label><label><input type="checkbox" name="fx" value="cam"><i class="cam"></i><span>Speed cameras, 2025</span></label><label><input type="checkbox" name="fx" value="to20"><i class="ln" style="background:#4269d0"></i><span>20 mph streets, 2022 on</span></label><label><input type="checkbox" name="fx" value="day"><i class="cam" style="background:#ff8ab7;border-color:#ff8ab7"></i><span>Daylighting and painted safety zones</span></label><label><input type="checkbox" name="fx" value="slow"><i class="ln" style="background:#6cc5b0"></i><span>Slow Streets</span></label><label><input type="checkbox" name="fx" value="calm"><i class="ln" style="background:#a463f2"></i><span>Speed humps and other calming, 2016 on</span></label></fieldset><fieldset><legend>Planned</legend><label class="lyr-all"><input type="checkbox" data-fx-all><span>Check all</span></label><label><input type="checkbox" name="fx" value="plan-qb"><i class="ln dash" style="border-color:#efb118"></i><span>Quick-builds</span></label><label><input type="checkbox" name="fx" value="plan-safety"><i class="ln dash" style="border-color:#a463f2"></i><span>Safety and traffic calming</span></label><label><input type="checkbox" name="fx" value="plan-bike"><i class="ln dash" style="border-color:#6cc5b0"></i><span>Bike lanes and Slow Streets</span></label><label><input type="checkbox" name="fx" value="plan-sig"><i class="ln dash" style="border-color:#4269d0"></i><span>Signal work</span></label><label><input type="checkbox" name="fx" value="plan-area"><i class="ln dash" style="border-color:#9c6b4e"></i><span>Streetscapes and area plans</span></label></fieldset><div class="lyr-key"><span><i class="ln" style="background:#4a4f57"></i>High Injury Network</span><span><i class="ramp"></i>Fewer to more people hurt</span><span data-kid-only hidden><i class="sch"></i>School in the School Trips tool</span><span data-school-only hidden><i class="ring"></i>500 ft from the school grounds</span><span data-school-only hidden><i class="ring dash"></i>A quarter mile from the grounds</span><span data-school-only hidden><i class="kidpt"></i><span id="kidpt-key">A kid hurt near the school</span></span><span data-dash hidden><i class="ln dash" style="border-color:#8a8f98"></i>Dashed: planned or pending</span></div></div></details><div id="map" class="glmap" role="img" aria-label="Map of San Francisco with a heat map of reported injuries and the High Injury Network in dark gray, with a menu to draw past and planned street safety fixes"></div></div>
<p class="note">Source: DataSF nwes-mmgh, read ${d.source.victimsFetched}, crashes to ${W.to}. Not shown: ${W.unsnapped} injuries with no street within 150 ft. "Kids on school trips" is the ${f0(d.map.kidPoints.length)} people aged 5 to 18 hurt on a weekday between 6 AM and 6 PM, August to May, holidays included, and victims with no age recorded are left out. "Kids severely hurt or killed" is the ${f0(d.map.kidSevere.length)} of them the crash data records as severely injured or killed. In the kids' views the squares are the ${SCHOOLS.length} schools in our School Trips tool. A school's rings are measured from the edge of its grounds, as state law measures a school zone. Each view is scaled to its own busiest spot. The fix layers draw each fix from its own city data: quick-build corridors and speed cameras as on the fixes chart below, 20 mph streets from SFMTA's speed limit layer (<a href="https://data.sfgov.org/d/3t7b-gebn">3t7b-gebn</a>, blocks with a Board date from 2022 on), painted safety zones (<a href="https://data.sfgov.org/d/vtn2-q8ky">vtn2-q8ky</a>) with the Tenderloin daylighting area as a dashed box, Slow Streets (<a href="https://data.sfgov.org/d/hkz3-itiu">hkz3-itiu</a>), traffic calming installed from 2016 on or pending (<a href="https://data.sfgov.org/d/abhw-ffzx">abhw-ffzx</a> and <a href="https://data.sfgov.org/d/bp3t-bd4t">bp3t-bd4t</a>), and planned SFMTA projects from SFMTA's project layer. A cost shows only where SFMTA or SFCTA published one.</p>

<h3>Main Roads Account for ${pct(A.main, A.total)} of the People Hurt</h3>
${classChart()}
<p class="note">Source: DataSF nwes-mmgh and 3psu-pn9h. Not drawn: ${f0(restHurt)} people at ramps, freeway mouths and private or paper streets. Main roads are classes 2 to 4 of the city's street classification on the centerline layer.</p>

<h3>${TENS[Math.round((10 * ixMain) / PL.main.total)]} in Ten People Hurt on Main Roads Are Hurt at an Intersection</h3>
<p>The report says whether a crash was within 20 ft of an intersection, and everything else counts as midblock.${fn(`The report's <code>intersection</code> field from DataSF <a href="${VICTIMS}">nwes-mmgh</a>: "Intersection <= 20ft" is at the intersection, and "Midblock > 20ft" and "Intersection Rear End <= 150ft" are midblock. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)} On either kind of street most people hurt are hurt at an intersection, whichever street a corner crash is given to.${fn(`A crash at a corner counts toward the biggest street there. Giving it to the nearest centerline instead puts ${"66%"} of people hurt on main roads at the intersection and ${"70%"} on residential streets, against ${pct(ixMain, PL.main.total)} and ${pct(ixRes, PL.res.total)} here, so the gap between the two kinds of street depends on the rule and isn't a finding. ${tag("inference — mine, a check run 2026-10-20")}`)}</p>
${split(PL, false, {}, "Bar chart of people hurt by where on the block, main roads and residential streets")}
<p class="note">Source: DataSF nwes-mmgh, ${mon(W.from)} to ${mon(W.to)}. The share in parentheses is of the people hurt on that kind of street.</p>

<h3>If You Took One Trip by Each Mode, How Likely Would You Be To…</h3>
<p>${ptSent()}${fn(`The <code>at_fault</code> field of DataSF <a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>, Traffic Crashes Resulting in Injury: Parties Involved, one row per party, joined to each person hurt on the crash's <code>case_id_pkey</code>. ${tag(`DataSF 8gtc-pjc6 — queried ${FA.partiesFetched}`)} Mode is the party's <code>party_type</code> and <code>stwd_vehicle_type</code>. Cars and trucks leave out motorcycles and mopeds, ${f0(PT.killed.moto)} of the ${f0(PT.killed.moto + PT.killed.drive)} people killed and ${f0(PT.hurt.moto)} of the ${f0(PT.hurt.moto + PT.hurt.drive)} hurt in a motor vehicle, because the trip survey has no motorcycle trip count to divide by. Motorcycles carry ${f0(PT.hurtSevere.moto)} of the ${f0(PT.hurtSevere.moto + PT.hurtSevere.drive)} people severely hurt or killed in a motor vehicle, so leaving them out roughly halves the car rate for severe injuries, and the survey's car share still includes motorcycle trips, so the car rates read a little low. They include ${f0(FA.hitRun)} people hurt where a hit and run driver's vehicle is unknown. ${f0(FA.driverOrPassenger)} of the people under a driver were the at fault driver or a passenger in that vehicle. A parked vehicle marked at fault, mostly a door opened into traffic, counts as other (${f0(FA.parked)} people). Transit is the vehicle type "Public Transit Authority", whose makes are mostly Muni buses, light rail and cable cars. The crash table's <code>party_at_fault</code> agrees with these flags on every crash but one. No published count by at fault mode could be matched. ${tag("inference — mine, the grouping")}`)} ${commuteSent()} Each bar compares a trip by that mode with a Muni trip, using people per 10 million trips from five years of police reports, and federal transit safety reports for Muni riders hurt, against SFMTA's count of trips.${fn(`Trips: SFMTA, <a href="${TDS.url}">Travel Decision Survey ${TDS.year}</a>, p. 5: "Total Daily Trips" ${f0(TDS.daily)}, an SF-CHAMP 2015 model run grown for population, for trips into, within and out of San Francisco by Bay Area residents. Shares: walk 24%, bicycle 3% (from a 2021 survey of 756 people, so a 2% or 4% share would move the bike commute year to about ${yearOddsAt("bike", 2)} or ${yearOddsAt("bike", 4)}), public transit 10%, and the survey's Privately Owned Vehicles 62% (drive alone, which includes motorcycle, carpool and TNC). ${tag("primary — read 2026-10-20")} We multiply the daily total by each share and by 365 days and ${PT.years.toFixed(0)} years, and show people per 10 million trips. A year of commuting is ${COMMUTE} trips, 250 workdays there and back, and its chance is one minus the chance of no injury on any of them. ${tag("inference — mine")} Crashes: every party in the ${f0(PT.crashes)} injury crashes on surface streets from ${mon(W.from)} to ${mon(W.to)} (<a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>), and the people hurt (<a href="${VICTIMS}">nwes-mmgh</a>). ${tag(`DataSF 8gtc-pjc6 — queried ${FA.partiesFetched}`)} A crash party is one person walking or riding, or one vehicle with everyone in it, so a car crash counts once however many ride. "Hurting someone else" is people hurt in a crash where a party of that mode was the only one marked at fault, other than that party and its passengers. Muni is all public transit, BART included. For getting hurt, Muni's count is the FTA National Transit Database's riders hurt on a Muni vehicle in safety events, assaults and other security events left out: ${NTD.major} in major events (<a href="https://data.transportation.gov/d/9ivb-8ae9">9ivb-8ae9</a>) and ${NTD.nonMajor} in non-major ones (<a href="https://data.transportation.gov/d/urir-txqm">urir-txqm</a>), September 2021 to June 2026, scaled from those ${NTD.months} months to the page's window, because police reports miss falls on board. ${tag(`primary — read ${NTD.read}`)} ${tag("inference — mine, the scaling")} Police reports alone count ${f0(PT.hurt.transit)} people hurt on Muni, operators included. Being in a crash and hurting someone else stay on police data for every mode. The federal data counts a rider as hurt only when they were taken from the scene for medical care, a stricter bar than a police report's complaint of pain, and its count is Muni's alone while the trip share includes BART, so Muni's rate still reads low against the other modes. ${tag("model knowledge — verify, the federal definition")} Trips include the parts outside the city of trips into and out of San Francisco, and the crash data leaves out freeways. Most of those outside and freeway miles are by car, so the car rates read low and the bike-to-car ratio is an upper bound. ${tag("inference — mine, the method")}`)}</p>
${perTripTable()}
<p>Of the ${f0(BW.bike.n)} people hurt biking, a driver was at fault for ${f0(BW_DRIVE)} and a parked car, mostly an opened door, for ${f0(BW_PARKED)} more, the rider for ${f0(BW.bike.fault.self)} and no one for ${f0(BW.bike.fault.none)}. ${pct(BW.bike.toc.Broadside, BW.bike.n)} were broadside crashes and ${pct(BW.bike.toc.Sideswipe, BW.bike.n)} sideswipes.${fn(`<code>type_of_collision</code> in <a href="${VICTIMS}">nwes-mmgh</a> and the one at-fault party in <a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>, ${mon(W.from)} to ${mon(W.to)}. ${pct(BW.bike.dark, BW.bike.n)} of people hurt biking were hurt in the dark or at dusk, against ${pct(BW.walk.dark, BW.walk.n)} of people walking (the crash table's <code>lighting</code>). ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)} ${pct(BW.bike.bikeway, BW.bike.n)} were hurt on a block with a bike lane or path, not counting shared lane markings, which covers ${Math.round(100 * BW.bikewayMilesShare)}% of street miles, most likely because that's where people ride. [inference — mine]${fn(`Each person is snapped to the nearest centerline block, and a block counts when SFMTA's bikeway layer (<code>data/extract/sfmta-bikeway/network.json</code>) has any row with its CNN. ${pct(BW.bike.classIV, BW.bike.n)} were on a block with a separated bikeway, ${(100 * BW.classIVMilesShare).toFixed(0)}% of street miles. ${pct(BW.bike.hin, BW.bike.n)} were on the High Injury Network, about the same as everyone hurt (${pct(BW.allHin, BW.all)}). ${tag("inference — mine")}`)} Per mile instead of per trip, biking stays riskier than walking unless the average bike trip is more than ${BW_PERMILE.toFixed(1)} times as long as a walk, and no San Francisco trip length by mode was opened. [inference — mine]</p>
${bodyChart()}
<p class="note">Counts, not chances per trip: the trip survey doesn't count trips by vehicle type.${fn(`The at-fault driver's <code>stwd_vehicle_type</code> in <a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>, crashes with one party at fault, people hurt outside that vehicle, ${mon(W.from)} to ${mon(W.to)}. ${tag(`DataSF 8gtc-pjc6 — queried ${FA.partiesFetched}`)} The data carries make and model year but no model, so it can't tell a vehicle's weight or hood height. ${tag("inference — mine")}`)}</p>
<p class="note">Police-reported crashes only, so the real chances are higher, especially for walking and biking, where many injuries never reach a police report. Source: DataSF nwes-mmgh and 8gtc-pjc6, ${mon(W.from)} to ${mon(W.to)}, and SFMTA Travel Decision Survey ${TDS.year}.</p>

<h3>Drivers at Fault Hurt ${f0(g("drive", "walk").all)} People Walking and ${f0(g("drive", "bike").all)} People Biking</h3>
<p>Where the officer marked one party at fault, a driver was at fault for ${f0(g("drive", "walk").all)} of the ${f0(colTot("walk"))} people hurt walking and ${f0(g("drive", "bike").all)} of the ${f0(colTot("bike"))} hurt biking.${fn(`Each person hurt from ${mon(W.from)} to ${mon(W.to)} (<a href="${VICTIMS}">nwes-mmgh</a>) by their own mode, against the mode of the one party marked <code>at_fault</code> in their crash (<a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>). The at-fault person counts too: an at-fault cyclist who is hurt is in Biking, the rider hurt, whoever else was in the crash. A parked car at fault counts as driving, and a crash with no party or two parties at fault is in the last row. Police-reported crashes on surface streets only, no freeways. ${tag(`DataSF 8gtc-pjc6 — queried ${FA.partiesFetched}`)}`)} Of the ${f0(rowTot("bike") + rowTot("bikeself"))} people hurt where a cyclist was at fault, ${f0(rowTot("bikeself"))} were the rider and ${f0(g("bike", "walk").all)} were people walking. The police most often blamed ${BIKE_CAUSES.map(([n, c]) => `${n} (${f0(c)})`).join(", ").replace(/, ([^,]*)$/, " and $1")}.${fn(`People hurt in crashes with one cyclist at fault, by the crash's primary collision factor, <code>vz_pcf_code</code> in <a href="${VICTIMS}">nwes-mmgh</a>, named from the city's <code>vz_pcf_description</code> in <a href="https://data.sfgov.org/d/ubvf-ztfx">ubvf-ztfx</a>: Vehicle Code 22350, 21453(a), 22107, 21650.1 with 21650 and 21657, and 22450(a). ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)}</p>
${whoGrid()}
<p class="note">Darker cells hold more people. Hover a cell for how many were severely hurt or killed.</p>

<h3>Cyclists Blamed for Their Own Injuries Rose From ${f0(SH.bike.byYear[Object.keys(SH.bike.byYear)[0]])} to ${f0(SH.bike.byYear[Object.keys(SH.bike.byYear).at(-1)])} a Year</h3>
<p>Police marked the person hurt as the one at fault for ${f0(SH.bike.n)} people biking and ${f0(SH.walk.n)} people walking in five years. ${f0(SH.bike.solo)} of the cyclists crashed with no one else involved, while all but ${SH.walk.solo} of the walkers were hit by a vehicle.${fn(`People hurt from ${mon(W.from)} to ${mon(W.to)} (<a href="${VICTIMS}">nwes-mmgh</a>) whose own party is the only one marked <code>at_fault</code> in <a href="https://data.sfgov.org/d/8gtc-pjc6">8gtc-pjc6</a>. "No one else involved" is a crash with one party. Years run September to August. ${tag(`DataSF 8gtc-pjc6 — queried ${FA.partiesFetched}`)}`)} The causes police named most for the cyclists were ${andList(SH_BIKE)}, and for the walkers ${andList(SH_WALK)}.${fn(`The crash's <code>vz_pcf_code</code>, named from the city's <code>vz_pcf_description</code> in <a href="https://data.sfgov.org/d/ubvf-ztfx">ubvf-ztfx</a>. For the ${f0(SH.bike.solo)} cyclists alone, "unsafe speed for prevailing conditions" was the cause for ${f0(SH.bike.soloCodes[0][1])}. ${tag(`DataSF ubvf-ztfx — queried ${SH.crashFetched}`)}`)} Only ${f0(SH.bike.defect)} of the cyclists' crash reports name a road problem such as a pothole, loose material or a work zone (${f0(SH.bike.soloDefect)} of the ${f0(SH.bike.solo)} solo crashes), and police reports miss many solo bike falls.${fn(`The crash table's <code>road_cond_1</code>, filled in for all but ${f0(SH.bike.roadCond["Not Stated"] || 0)} of the ${f0(SH.bike.n)} reports ("Not Stated"): "Holes, Deep Rut" ${SH.bike.roadCond["Holes, Deep Rut"] || 0}, "Construction or Repair Zone" ${SH.bike.roadCond["Construction or Repair Zone"] || 0}, "Obstruction on Roadway" ${SH.bike.roadCond["Obstruction on Roadway"] || 0}, "Loose Material on Roadway" ${SH.bike.roadCond["Loose Material on Roadway"] || 0}, others ${(SH.bike.roadCond["Flooded"] || 0) + (SH.bike.roadCond["Reduced Roadway Width"] || 0)}; "Other" ${SH.bike.roadCond["Other"] || 0} is not counted. Wet road ${SH.bike.surface["Wet"] || 0}. ${tag(`DataSF ubvf-ztfx — queried ${SH.crashFetched}`)} SFDPH's match of hospital and police records found the people police miss are "more often cyclists" (see the note at the top). No count of solo falls missed was opened, so we give no number. ${tag("inference — mine")}`)}</p>
${selfChart()}

<h3>One Trip by Any Mode Carries a Death Risk Hundreds of Times Smaller Than a Skydiving Jump</h3>
<p>Per trip in San Francisco the chance of being killed is about ${mmFmt(mmOf("walk").v)} micromorts walking, ${mmFmt(mmOf("bike").v)} biking, ${mmFmt(mmOf("drive").v)} by car and ${mmFmt(mmOf("transit").v)} on Muni, against 8 for a skydiving jump and 22 for one ordinary day of living in the US.${fn(`A micromort is a one in a million chance of death. San Francisco: people killed by their own mode from ${mon(W.from)} to ${mon(W.to)} (<a href="${VICTIMS}">nwes-mmgh</a>, ${PT_MODES.map(([k, n]) => `${n.toLowerCase()} ${PT.killed[k] || 0}`).join(", ")}), over the same trip counts as above, with an exact Poisson 95% range. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)} Police-reported deaths on surface streets only, and trips include their legs outside the city. A car trip leaves out the ${PT.killed.moto} motorcycle and moped riders killed, because there is no trip count for them. The federal transit safety data lists no Muni rider killed in a crash or other safety event from September 2021 to June 2026, and two homicides on board, which are security events and not counted here. ${tag(`primary — read ${NTD.read}`)} References from Wikipedia, <a href="https://en.wikipedia.org/wiki/Micromort">Micromort</a>: ${MM_REF.map(([n, v, src]) => `${n.toLowerCase()} ${v} (${src})`).join(", ")}. ${tag("secondary — verify")}`)} Walking and biking carry ${Math.round(mmOf("bike").v / mmOf("drive").v)} to ${Math.round(mmOf("walk").v / mmOf("drive").v)} times the risk of a car trip, but every mode sits far below risks people accept every day, which may be part of why there is little pressure for progress. [inference — mine] Across all modes that comes to ${mmFmt(MM_ALL)} micromorts a trip, about a fifth of the US rate for 1999 to 2003, which counts freeways and rural roads.${fn(`Beck, Dellinger and O'Neil, <a href="https://academic.oup.com/aje/article/166/2/212/98939">Motor Vehicle Crash Injury Rates by Mode of Travel</a>, American Journal of Epidemiology, 2007: "The overall fatal traffic injury rate was 10.4 per 100 million person-trips", 0.104 micromorts a trip. ${tag("primary — read 2026-10-20")} Per mode, our rates match the UK's per-mile rates over ${(mmOf("walk").v * 30).toFixed(1)} miles of walking, ${(mmOf("bike").v * 44).toFixed(1)} of biking and ${(mmOf("drive").v * 370).toFixed(1)} of driving, plausible trip lengths for a dense city, though no San Francisco trip length by mode was opened. ${tag("inference — mine")}`)}</p>
${mmChart()}

<h3>${capMain[0] === "speed" && capRes[0] === "speed" ? "Unsafe Speed Is the Cause Police Name Most Often" : "The Causes Police Name, on Main Roads and Residential Streets"}</h3>
<p>As for what happened, each crash report names one primary collision factor, the vehicle code section the officer judges the at fault party broke.${fn(`The victim row's <code>vz_pcf_code</code>, "California vehicle code primary collision factor violated", one per crash and repeated on each person hurt in it, in DataSF <a href="${VICTIMS}">nwes-mmgh</a>. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)} The ${f0(CA.main.total + CA.res.total)} people here were hurt in ${f0(CA.crashes)} crashes. No published count by cause could be matched: SFMTA says only that "unsafe speed is one of the most common primary collision factors in crashes that result in injuries" (<a href="${SPEEDPAGE}">Speed Safety Cameras Background</a>). ${tag("primary — read 2026-10-20")}`)} That is the officer's judgment of the main cause, not a measured speed, and "unsafe speed" is the code's "Unsafe speed for prevailing conditions".${fn(`The grouping is ours: unsafe speed is 22350 and 22348 to 22356, red light 21453(a) to (c), crosswalk 21950(a) and (c), turning left 21801 (the left or U turn yield), stop sign 22450 alone, so 21802, right of way entering a through highway, is in every other cause. Unsafe turn or lane change is 22107, following too closely 21703, under the influence 23152 and 23153, pedestrian violation 21453(d), 21950(b) and (e), 21954(a), 21955 and 21456. Unknown is a blank code or one the city's own description calls "Unknown". ${tag("inference — mine")}`)} ${DC.top ? `Where a driver was at fault, ${DC.top.name.toLowerCase()} is still the most common of the causes we name, for ${f0(DC.top.n)} people (${pct(DC.top.n, DC.total)}).` : ""}</p>
${split(CA, true, {}, "Bar chart of people hurt by the cause police named, main roads and residential streets")}
<p class="note">Source: DataSF nwes-mmgh, ${mon(W.from)} to ${mon(W.to)}. The share in parentheses is of the people hurt on that kind of street. Main roads are classes 2 to 4 above.</p>

<h3>Injuries Peak at ${hourLab(WDPEAK)} on Weekdays${NIGHT.p / DAY.p >= 1.4 ? `; After 10 PM, One in ${Math.round(1 / NIGHT.p)} Is Severely Hurt or Killed` : ""}</h3>
<p>Each line is people hurt per weekday or per weekend day, by the hour of the crash on the report.${fn(`The hour of <code>collision_datetime</code> in DataSF <a href="${VICTIMS}">nwes-mmgh</a>, with each hour's count divided by the ${f0(TOD.days.wd)} weekdays or ${f0(TOD.days.we)} weekend days from ${mon(W.from)} to ${mon(W.to)}. The ${f0(TOD.missing)} people with no time on the report are left out. Days are calendar days, so a crash at 1 AM Saturday counts as a weekend. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)} From 10 PM to 6 AM, ${f0(NIGHT.s)} of ${f0(NIGHT.a)} people hurt (${pct(NIGHT.s, NIGHT.a)}) were severely hurt or killed, against ${f0(DAY.s)} of ${f0(DAY.a)} (${pct(DAY.s, DAY.a)}) from 7 AM to 7 PM.</p>
${todChart()}
<p class="note">Source: DataSF nwes-mmgh, ${mon(W.from)} to ${mon(W.to)}, all ${f0(A.total)} people hurt. Hover a point or bar for its count.</p>


<h2>Did the fixes work?</h2>
<p>Injuries to people walking within two blocks fell ${chg(camP.near.ped.rr[0]).replace("\u2212", "")} at the speed camera locations and ${chg(WALK2.rr[0]).replace("\u2212", "")} near the ${qbP.n} quick-build corridors against the rest of the city, with no such drop in the years before, but neither passes once we allow for testing ${"%%M_ROWS%%"} rows at once. The other fixes either can't be told apart from chance yet or followed a spike that would have fallen back anyway. Even the best of these is small next to the about ${f0(Math.round(CITY_YR / 50) * 50)} people hurt a year citywide from 2021 to 2025.${fn(`Each row compares equal windows before and after the fix, capped at ${d.windowYears} years each side, at the site and with two blocks each way, against the rest of the city. Each person counts once per row even where projects overlap: a person inside several projects' areas is split evenly among them, by place alone. The change is a Mantel-Haenszel ratio across a fix's projects, each with its own windows, and its 95% range resamples the crashes ${"2,000"} times, so a crash that hurt several people moves it as a unit; the rest of the city's counts are held fixed, which narrows the range a little. "Fewer a year" is the after count we'd expect at the city's rate minus the count we saw, per year. A row is a clear drop only when its range stays below zero, the same test one window earlier shows no change, and it passes a Holm correction across every row on the chart. A corridor starts the day after the completion period SFMTA states on its project page or in the <a href="${SSEP22}">2022 Safe Streets Evaluation summary</a>. Citywide: ${Y5.map((y) => `${y} ${f0(YR[y].all)}`).join(", ")} people hurt. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)} ${tag("inference — mine, the method")}`)} The city's own evaluations compare each project's street with itself and use no comparison streets.${fn(`SFMTA, <a href="${SSEP}">Safe Streets Evaluation Program 2024 Annual Report</a> (<a href="${SSEP_STORY}">story map</a>): "The collision analysis compares collisions up to three years prior to a project's implementation to collision data from the most recent three years at the time of this report's analysis (April 2022 through March 2025)." ${tag("primary — read 2026-10-19")} It counts collisions, not people hurt, so its percentages and ours measure different things.`)} <a href="#how-sure">How sure are we?</a></p>
${(() => { const claims = [
fixRow(`${CAM.locations} speed camera locations`, `warnings from April to June 2025 and citations from August 2025, about ${yrs(camP.years)} each side`,
  `Speeding 10 mph or more over the limit "is down nearly 80 percent across camera locations". No injury result yet.${fn(`<a href="${DECK}">Vision Zero Committee deck</a>, May 2026, slide 23: "One year after launching speed cameras in San Francisco, the share of drivers speeding 10 mph or more is down nearly 80 percent across camera locations compared to pre-implementation." Slide 28: "Evaluation of system effectiveness at 18-months (September 2026 for San Francisco)" on speed criteria only. ${tag("primary — read 2026-10-19")}`)}`, camP, ["nearPed"]),
fixRow(`${qbP.n} quick-build and near-term corridors`, `completed 2018 to 2024, ${d.windowYears} years each side where the data allows`,
  `Across 27 of its 34 projects, all collisions "fell by 2%", pedestrian collisions 32% and bike collisions 15%. We matched ${qbP.n} of the 34 to a street extent and a date.${fn(`<a href="${SSEP_STORY}">2024 report</a>, Collision Data Highlights: "overall collisions ... at project locations fell by 2%, a small reduction likely swayed by a minority of projects that reported an increase in collisions", pedestrian "-32%", bike "-15%". ${tag("primary — read 2026-10-19")} Our ${qbP.n} corridors are the 34 projects in that report less the citywide left-turn program and the Page Street neighborway, which have no corridor extent. The report does not say which 27 had crash data. ${tag("inference — mine")}`)}`, qbP, ["nearPed"]),
fixRow(`Tenderloin quick-builds`, `Golden Gate Ave, Jones, Leavenworth and Taylor, completed 2019 to 2022`,
  `Pedestrian collisions "from 35.7 to 20.1 a year", 44% fewer.${fn(`<a href="${SSEP_STORY}">2024 report</a>, Collision Analysis of Tenderloin Projects: overall "-44.0%", "the Jones Street Quick-Build saw average annual pedestrian crashes drop by 33%" and "the Golden Gate Avenue and Taylor Quick-Build Projects cut the average annual pedestrian collisions by half (52%)". ${tag("primary — read 2026-10-19")}`)}`, tlP),
fixRow(`Tenderloin daylighting`, `red zones at ${TL.intersections} intersections by March 2015, 3 years each side`,
  `"14% fewer reported collisions at intersections where daylighting treatments were implemented".${fn(`SFMTA, <a href="${TL_DAY}">Tenderloin Daylighting Project</a> sheet: "One to two parking spaces per approach on each side of the street was removed and replaced with red zones", "180 parking spaces were removed at 80 intersections", "the intersections of Jones Street at Ellis and Eddy streets experienced more collisions". No method or comparison given. ${tag("primary — read 2026-10-20")} Date from SFMTA's blog of 2015-03-20: "we recently improved 80 intersections in the Tenderloin with daylighting" (<a href="${TL_BLOG}">Daylighting Makes San Francisco Crosswalks Safer</a>). ${tag("primary — read 2026-10-20")} We count ${TL.intersections} intersections of the area's named streets inside Market, Mason, Pine and Larkin, and the ${TL.blocks} blocks of those streets between them. SFMTA's list of 80 is not published, and the 13 extra are most likely where alleys such as Olive, Willow and Cosmo meet those streets. ${tag("inference — mine")}`)}`, TL.pooled),
]; return forest() + `<details><summary>What SFMTA says about each fix, comparing each street with itself and leaving the citywide drop in</summary><ul class="claims">${claims.join("")}</ul></details>`; })()}
<p class="note">Source: DataSF nwes-mmgh to ${W.to}. The dot is the change in people hurt against the rest of the city and the line its 95% range. The daylighting rows are Tenderloin-wide, after a 2013 and 2014 spike, and injuries to people walking there didn't change (${chg(TL.pooled.site.ped.rr[0])}). Hover a dot for its before and after counts. Project photos are SFMTA's, from each <a href="https://www.sfmta.com/projects">SFMTA project page</a>. Rows with under ${SMALL} people hurt in either window are left out. People biking aren't charted: within two blocks of the corridors their injuries went from ${f0(qbP.near.bike.before)} to ${f0(qbP.near.bike.after)}, ${chg(qbP.near.bike.rr[0])} against the rest of the city (p = ${qbP.near.bike.p.toFixed(2)}), which wouldn't pass the correction for many rows. Two blocks means two steps out along the centerline from each site intersection, the next block along the street and on each cross street and then one more, so downtown, where alleys split blocks, two steps can be one real block. Measured against the surrounding blocks (three to eight blocks out) instead of the whole city, the four pooled changes move by at most ${Math.max(...[camP, qbP, tlP, TL.pooled].map((p) => Math.abs(Math.round((p.near.rrRing[0] - p.near.rr[0]) * 100)))).toFixed(0)} percentage points.</p>
<p>The camera row pools all ${CAM.locations} locations, because no single block has enough reports to read. Each location starts on its first warning day, between ${camP.warningFirst[0]} and ${camP.warningFirst[1]}; citations began ${CITE.start}, and counting from then gives ${chg(CITE.site.rr[0])} at the blocks.${fn(`First day per location in DataSF <a href="${CAMDATA}">d5uh-bk84</a>; <code>issued_citations</code> starts ${CITE.start} at every location. SFMTA says the program launched 2025-03-20 and all cameras were issuing warnings by 2025-06-06 (<a href="${CAMPAGE}">SFMTA</a>). ${tag("primary — read 2026-10-20")} Counted from citations: everyone at the block ${ci(CITE.site)}, with two blocks ${ci(CITE.near)}. ${tag("inference — mine")} Cost: "The anticipated total cost of this five-year pilot program is $7.4 million. This covers permitting, installation, operations and maintenance." (<a href="https://www.sfmta.com/blog/one-year-speeding-down-79-speed-safety-camera-locations">SFMTA blog</a>, May 2026) ${tag("primary — read 2026-10-20")}`)} Another year roughly doubles the counts and should tell a 20% drop from no change.${fn(`About ${f0(camP.needPerWindow)} people hurt in each window separate a 20% change from noise at 95%. The pooled camera blocks have ${f0(camP.site.before)} and ${f0(camP.site.after)} so far. ${tag("inference — mine")}`)} Camera sites were chosen for speeding and crashes, so some of any drop is the usual fall back toward normal after a bad stretch.${fn(`Regression to the mean: a site picked because its recent counts were high tends to fall afterwards with no treatment. The rest-of-city comparison does not remove it. A matched comparison of untreated streets with the same prior counts would. ${tag("inference — mine")}`)}</p>

<p>Two questions sit under the corridor rows. Corridors finished in 2020 read better against the whole city than against their own surrounding blocks, Howard St most of all (${chg(soma[0].site.rr[0])} against the city, ${chg(soma[0].site.rrRing[0])} against its neighborhood), most likely because downtown emptied out after 2020 more than the rest of the city did and has only partly come back. In June 2026, exits at downtown BART stations were about 46% of June 2019, and employee foot traffic downtown about 57%.${fn(`The Controller's Office, <a href="https://media.api.sf.gov/documents/Status_of_the_San_Francisco_Economy_2026Q2.pdf">Status of the San Francisco Economy, 2026 Second Quarter</a>, slide 14 (BART exits at downtown stations, as a percentage of the same month in 2019) and slide 8 (Placer.ai employee foot traffic in the Downtown SF Partnership district, same basis). Both figures are read off the charts. ${tag("primary — read 2026-10-21")} These count people, not cars, and no traffic count was opened for this page, so the drop in downtown traffic is our inference. ${tag("inference — mine")} Over the longer 2015 to 2019 against 2021 to 2025 comparison, downtown and the rest of the city fell by about the same. The surrounding blocks are the segments three to eight steps out from the site, which share the site's neighborhood traffic.`)} And three corridors rose against the city once their two blocks are counted: ${rising.join(", ")}. We don't know why, and each is a question before it is a finding.</p>
<details><summary>The ${qbP.n} corridors, one by one</summary>
<table>
<thead><tr><th>Corridor</th><th>Everyone at the site</th><th>People walking at the site</th><th>Everyone, with two blocks</th><th>Against the surrounding blocks instead</th></tr></thead>
<tbody>${corridorRows}</tbody>
</table>
<p class="note">Corridor extents from SFMTA's <a href="https://www.sfmta.com/quick-build-program">Quick-Build Program</a> page and project pages, matched to centerline segments by street name between the two cross streets, both lines of a divided street. Corridors whose after window ends before ${d.windowYears} years use the data available, shown in the row.</p>
</details>
<details><summary>The ${CAM.locations} speed camera locations, one by one</summary>
<table>
<thead><tr><th>Location</th><th>Everyone at the block</th><th>People walking at the block</th><th>Everyone, with two blocks</th><th>Against the surrounding blocks instead</th></tr></thead>
<tbody>${cameraRows}</tbody>
</table>
<p class="note">A location's block is the centerline segment nearest each camera's address, both lines where the street is divided. Every location has fewer than ${SMALL} people walking hurt in a window, so that column is counts only.</p>
</details>

<h2 id="why-severe">Severe Injuries Jumped in 2015 and 2016 as Counting Changed, and Deaths Are Back Near Their Earlier Level</h2>
<p>We tested ten reasons more people might be severely hurt or killed. Police rated about ${r0(SWE.sevEarly)} people a year severely hurt or killed from ${SWEARLY}, ${r0(SWE.sevBefore)} from ${SWB} and ${r0(SWE.sevAfter)} from ${SWA}, so the rise is one jump in 2015 and 2016 that has held since. Most of that jump came with changes in how injuries are counted, and deaths, at ${r1(SWE.fatAfter)} a year from ${SWA}, are close to the ${r1(SWE.fatEarly)} a year of ${SWEARLY} after a low of ${r1(SWE.fatBefore)} from ${SWB}.${fn(`Every injured victim row in DataSF <a href="${VICTIMS}">nwes-mmgh</a> from 2005 to ${SW.periods.after[1]}, ${f0(SW.source.victims)} people, by the calendar year of <code>collision_datetime</code>. Severely hurt or killed is "Severe Injury" or "Fatal Injury". The table compares the yearly average for ${SWB} with ${SWA}, leaving out 2020. A change is bigger than chance when the two five-year totals differ by at least 1.96 times the square root of their sum, a Poisson test. Most crashes hurt one person badly, so counting crashes instead of people changes no verdict. We ran about twenty such tests, so one could pass by chance alone. Each group's rule is in the docstring of <code>tools/street-safety/injury-severe-why.py</code>, the script that builds these figures. ${tag(`DataSF nwes-mmgh — queried ${SW.source.victimsFetched}`)} ${tag("inference — mine, the method")}`)}</p>

<h3>Police Count More Injuries as Severe Since 2016, While the Trauma Center's Count Held</h3>
<p>Both counts rose in 2015. The trauma center's rose after a 2013 rule sent the worst hurt there, and police's after a December 2014 memo told officers to rate head injuries as severe.${fn(`SFDPH, <a href="https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf">Severe Traffic Injury Trends 2015-2022</a>: "At the end of 2013, the San Francisco Emergency Medical Services Agency (SF EMSA) issued retriage guidelines to ensure the most severely injured people were treated at ZSFG" ${tag("primary — read 2026-10-21")}. SFDPH, <a href="https://www.visionzerosf.org/wp-content/uploads/2019/09/Severe-Injury-Trends_2011-2018_final_report.pdf">Severe Traffic Injury Trends 2011-2018</a>, Appendix A: "a memo released to SFPD officers in Dec. 2014 advised head injuries be classified as severe to avoid under-reporting of traumatic brain injury." ${tag("primary — read 2026-10-20")} By quarter, police reports of people severely hurt or killed ran ${qRange("2014")} a quarter in 2014, ${qRange("2015")} in 2015 and ${qRange("2016")} in 2016. ${tag(`DataSF nwes-mmgh — queried ${SW.source.victimsFetched}`)}`)} From 2016 the trauma center's count held between ${f0(Math.min(...HY.filter((y) => y >= 2016).map((y) => HOSP.zsfg[y])))} and ${f0(Math.max(...HY.filter((y) => y >= 2016).map((y) => HOSP.zsfg[y])))} a year, while police went from ${pct(R_PRE * 100, 100)} of its count in 2011 to 2015 to ${pct(R_POST * 100, 100)} in 2016 to 2022.${fn(`SFDPH, <a href="https://visionzerosf.org/wp-content/uploads/2024/12/Severe-Injury-Trends_2015-2022.pdf">Severe Traffic Injury Trends 2015-2022</a>, Figure 14, "ZSFG Severe" (critical injuries included) and "SFPD Severe", 2011 to 2022. Our police counts match its SFPD series from 2015 on. ${tag("primary — read 2026-10-21")} The hospital count includes freeway crashes, which police data leaves out. Because minor injuries fell from ${f0(MINOR_B)} a year in ${SWB} to ${f0(MINOR_A)} in ${SWA} while severe ones held, the share of people hurt who were severely hurt or killed rose from ${(100 * SWE.shareBefore).toFixed(1)}% to ${(100 * SWE.shareAfter).toFixed(1)}%. We haven't found a hospital count published after 2022. ${tag("unretrieved — verify")}`)}</p>
${sevChart()}
<p class="note">Source: DataSF nwes-mmgh, 2005 to ${SW.periods.after[1]}, and SFDPH's trauma registry, 2011 to 2022. People killed are left out of both lines, as SFDPH counts them.</p>

<h3>Deaths Fell to a Low From 2015 to 2019 and Have Come Back, Mostly After Dark</h3>
<p>We counted ${Math.round(SWE.fatAfter * 5)} deaths from ${SWA}, against ${Math.round(SWE.fatBefore * 5)} from ${SWB}, a rise too small to rule out chance. Deaths after dark went from ${r1(darkB)} a year to ${r1(darkA)}, more than chance would give, and ${r1(SWF.darkWalk.fatAfter)} a year of those were people walking. Against ${SWEARLY}, when ${r1(SWF.dark.fatEarly)} a year were killed after dark, neither rise is clear.${fn(`Deaths are "Fatal Injury" in nwes-mmgh, which takes them from the Medical Examiner's cases under the Vision Zero protocol. After dark is <code>lighting</code> "Dark - Street Lights", "Dark - No Street Lights" or "Dark - Street Lights Not Functioning". Counting by the hour instead, 7 PM to 6 AM, gives the same result. ${tag(`DataSF nwes-mmgh — queried ${SW.source.victimsFetched}`)} Vision Zero SF's own count (<a href="https://www.visionzerosf.org/wp-content/uploads/2025/08/Vision-Zero-2024-End-of-Year-Traffic-Fatality-Report.pdf">2024 End of Year Traffic Fatality Report</a>, Figure 1) ${tag("primary — read 2026-10-21")} and DataSF's fatality table <a href="https://data.sfgov.org/d/dau3-4s8f">dau3-4s8f</a> ${tag(`DataSF dau3-4s8f — queried ${SW.source.fatalFetched}`)} differ from the count we chart in ${DEATH_DIFF.length} years: ${DEATH_DIFF.join(", ")}. We don't know why after-dark deaths fell from 2015 to 2019 or came back since. More driving at night, faster driving on emptier streets and fewer daytime trips each fit, and a count of people out walking and driving at night would tell them apart. ${tag("inference — mine")}`)}</p>
${deathChart()}
<p class="note">Source: DataSF nwes-mmgh, 2005 to ${SW.periods.after[1]}. Freeway deaths aren't in the data. A death with no lighting stated counts as daylight or dusk.</p>

<h3>Scooter Injuries Rose, but Age, Place and Who Gets Hurt Didn't Explain the Rest</h3>
<p>Each row compares people severely hurt or killed a year from ${SWB} with ${SWA}, unless it says otherwise. "Could be chance" means a change this size would show up more than one time in twenty with nothing real behind it.</p>
${tenTable()}
<p class="note">Source: DataSF nwes-mmgh and 8gtc-pjc6 (parties), 2005 to ${SW.periods.after[1]}. Unsafe speed is the primary collision factor police name. Main roads and the High Injury Network follow the map's rules above. For vehicles, each person walking or biking counts under the biggest vehicle a driver was in, so a parked car doesn't count, and ${f0(VEH.none.hurt)} people had no driven vehicle of a known type in their crash. Police coded none of the drivers as in an SUV before 2013 and ${pct(SW.suvCoded["2017"] * 100, 100)} in 2017. That the 2022 jump is coding, not the fleet, is our reading. ${tag(`DataSF 8gtc-pjc6 — queried ${SW.source.partiesFetched}`)} ${tag("inference — mine")}</p>

<h2>About the data</h2>
<h3 id="fewer">Why Fewer People Are Hurt Since 2020</h3>
<p>Injuries fell in the second quarter of 2020 and have stayed lower. The drop is in minor injuries, weekday commute hours and people walking and biking, while severe injuries held and deaths rose. From 2015 to 2019 against 2021 to 2025, downtown fell ${chg(1 + stepCh("area", "downtown"))} and the rest of the city ${chg(1 + stepCh("area", "rest"))}, close to each other.${fn(`Quarterly people hurt, 2018 to 2023: ${Object.entries(W.step.quarters).map(([q, n]) => `${q} ${f0(n)}`).join(", ")}. The downtown box is east of longitude −122.425 and north of latitude 37.765. "Other" victims rose as scooters arrived. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)}</p>
${stepTable()}
<h3 id="how-sure">How Sure Are We</h3>
<p>We ran the quick-build walking row through seven checks.</p>
<details><summary>The seven checks and what each found</summary><ul class="claims">
<li><b>The years before.</b> The same comparison one window earlier, before any work: ${chg(WALK2.placebo.rr[0])} (${chg(WALK2.placebo.rr[1])} to ${chg(WALK2.placebo.rr[2])}), no drop before the fix.</li>
<li><b>Leaving out COVID.</b> Ending the after windows before the pandemic's traffic drop changed little: ${"\u2212"}13% (${"\u2212"}20% to ${"\u2212"}6%).</li>
<li><b>Moving the start date.</b> Three months earlier, ${"\u2212"}11%; three months later, ${"\u2212"}13%. Both stay below zero.</li>
<li><b>Testing many rows at once.</b> With ${"%%M_ROWS%%"} rows on the chart, one in twenty would look clear by chance. After a Holm correction this row, p = ${WALK2.p.toFixed(3)}, falls just short.</li>
<li><b>A nearer comparison.</b> Against the surrounding blocks, three to eight out, instead of the whole city: ${chg(WALK2.rrRing[0])} (${chg(WALK2.rrRing[1])} to ${chg(WALK2.rrRing[2])}), a range that reaches zero.</li>
<li><b>Splitting overlaps another way.</b> Giving a person inside two projects' areas to each project in turn, instead of half to each: ${"−"}5%. ${tag("inference — mine, a check run 2026-10-20")}</li>
<li><b>Counting crashes, not people.</b> Not yet run on this row. On the walking row at the corridors themselves it gave ${"\u2212"}14% (${"\u2212"}27% to 0%).</li>
</ul><p class="note">The COVID, start date and crash checks were run on the summed counts across projects; the others count each person once. ${tag("inference — mine, the method")}</p></details>
<p>Crash data: DataSF <a href="${VICTIMS}">Traffic Crashes Resulting in Injury: Victims Involved</a>, read ${d.source.victimsFetched}, ${f0(d.source.victims)} victims from 2005 to ${W.to}. One row is one injured person. Severe means the officer's "Severe Injury" or "Fatal Injury". The 2018 count of police-reported severe injuries, 283, matches SFDPH's published table exactly.${fn(`SFDPH, <a href="https://www.visionzerosf.org/wp-content/uploads/2019/09/Severe-Injury-Trends_2011-2018_final_report.pdf">Severe Traffic Injury Trends 2011-2018</a>, Appendix A, Table A: 283 in 2018. ${tag("primary — read 2026-10-20")} Our query: victim_degree_of_injury = 'Severe Injury' in 2018, 283 rows. ${tag(`DataSF nwes-mmgh — queried ${d.source.victimsFetched}`)}`)}</p>
<p>Streets: DataSF <a href="${CENTER}">Streets, Active and Retired</a>, active rows, read ${d.source.centerlinesFetched}. Each injury is snapped to the nearest surface centerline within 150 ft. Freeway lines are left out because the crash data excludes freeway crashes. The two blocks are every block that meets a site intersection, which is the next block along the street and the first block of each cross street, and then the following block of each of those streets. Downtown, where alleys split blocks, two of these steps can be one real block.</p>
<p>Crash reports can be filed up to 30 days after a crash, so ${mon(W.to)} may still grow at the next quarterly release. Some fixes sit inside each other's two blocks, the four Tenderloin quick-builds and the Turk St camera inside the daylighting area most of all, so a "two blocks" count there is partly another treatment.</p>
<p>Several corridors changed again inside their windows, Valencia St most of all, so a row measures the street's whole set of changes, not one design.</p>
<!--/hin-body-->
<dialog id="proj" aria-labelledby="proj-h"><div class="dlg"><div class="dlg-top"><button type="button" class="back" hidden>← All projects</button><button type="button" class="close" aria-label="Close">✕</button></div><div class="dlg-body"></div></div></dialog>
<script type="application/json" id="proj-data">${inlineJson({ projects: PDATA, pools: POOLS })}</script>
<script type="application/json" id="hin-data">${inlineJson(data)}</script>
<script>
// Hover tips for every chart (Bryan): each mark's <title> becomes an instant tip that follows the
// pointer and also opens on tap, instead of the browser's slow native tooltip.
(function () {
  var tip = document.createElement("div"); tip.className = "ptip"; tip.hidden = true; document.body.appendChild(tip);
  document.querySelectorAll("table.grid td[title]").forEach(function (td) { td.setAttribute("data-tip", td.getAttribute("title")); td.removeAttribute("title"); });
  document.querySelectorAll(".plotwrap svg title").forEach(function (t) { var p = t.parentNode; if (p && p.setAttribute) { p.setAttribute("data-tip", t.textContent); t.remove(); } });
  function show(e) { var el = e.target.closest && e.target.closest("[data-tip]"); if (!el) { tip.hidden = true; return; }
    tip.textContent = el.getAttribute("data-tip"); tip.hidden = false;
    var x = e.clientX, y = e.clientY, w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x - w / 2)) + "px";
    tip.style.top = (y - h - 12 < 6 ? y + 16 : y - h - 12) + "px"; }
  document.addEventListener("pointermove", show); document.addEventListener("pointerdown", show);
  window.addEventListener("scroll", function () { tip.hidden = true; }, { passive: true });
})();
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".fn");
    if (!b) return;
    var note = b.nextElementSibling, open = b.getAttribute("aria-expanded") === "true";
    b.setAttribute("aria-expanded", open ? "false" : "true");
    note.hidden = open;
  });
  // Project details panels: a modal on a laptop, a full-screen sheet on a phone (CSS).
  (function () {
    var D0 = JSON.parse(document.getElementById("hin-data").textContent);
    var PJ = JSON.parse(document.getElementById("proj-data").textContent), dlg = document.getElementById("proj"),
      body = dlg.querySelector(".dlg-body"), back = dlg.querySelector(".back"), pmap = null, pool = null;
    function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
    function fmt(n) { return n.toLocaleString("en-US"); }
    function dropMap() { if (pmap) { pmap.remove(); pmap = null; } }
    function row(name, c) { return "<tr><th scope=row>" + name + "</th><td>" + fmt(c.b) + "</td><td>" + fmt(c.a) + "</td><td>" + (c.ch ? c.ch + (c.clear ? ", clear drop" : ", no clear drop") : "too few to read") + "</td></tr>"; }
    // One project card, the site's .proj-card markup (site/src/bike-history.mjs): name linked to SFMTA, photo hidden
    // when there is none, when, a small table, the SFMTA link. Used in the map popup and in the details panel.
    function card(p, inPanel) {
      var tr = function (k, c) { return "<tr><th>" + k + "</th><td>" + fmt(c.b) + " \u2192 " + fmt(c.a) + ", " + (c.ch ? c.ch + (c.clear ? ", clear drop" : ", no clear drop") : "too few to read") + "</td></tr>"; };
      return "<div class='proj-card pc'>" + (inPanel ? "<h3 class=proj-name id=proj-h>" : "<h3 class=proj-name>") + (p.url ? "<a href='" + esc(p.url) + "' target=_blank rel=noopener>" + esc(p.label) + "</a>" : esc(p.label)) + "</h3>" +
        (p.photo ? "<figure class=proj-photo><img alt='SFMTA photo for " + esc(p.label) + "' referrerpolicy=no-referrer src='" + esc(p.photo) + "' onerror='this.parentNode.hidden=true'></figure>" : "") +
        "<p class=proj-when>" + (p.extent ? esc(p.extent) + ". " : "") + "Work: " + esc(p.note) + ". Counted from " + esc(p.after) + ", " + esc(p.years) + " each side.</p>" +
        (p.extra ? "<p class=proj-when>" + esc(p.extra) + "</p>" : "") +
        "<p class=proj-when>Cost: " + (p.kind === "camera" ? D0.fx.camCost : (p.cost || "No published cost found on SFMTA's project page or its documents.")) + "</p>" +
        "<table class=proj-table><tbody>" + tr("People hurt at the site", p.site) + tr("Site plus two blocks", p.near) + "</tbody></table>" +
        "<p class=proj-more>" + (p.url ? "<a href='" + esc(p.url) + "' target=_blank rel=noopener>SFMTA's project page</a>" : "No SFMTA page found") + "</p></div>";
    }
    window.projCard = function (label) { var p = PJ.projects.find(function (x) { return x.label === label; }); return p ? card(p, false) : null; };
    function showPool(i) {
      dropMap(); pool = PJ.pools[i];
      if (pool.members.length === 1) { showProject(pool.members[0], false); return; }
      back.hidden = true;
      body.innerHTML = "<h3 id=proj-h>" + esc(pool.fix) + " (" + esc(pool.years) + ")</h3><p class=dnote>" + pool.members.length + " projects. Pick one for its dates, source and map.</p>" + (pool.note ? "<p class=dnote>" + esc(pool.note) + "</p>" : "") + "<ul class=plist>" +
        pool.members.map(function (m) { var p = PJ.projects.find(function (x) { return x.label === m; });
          return "<li><button type=button data-p='" + esc(m) + "'>" + esc(m) + " <span>" + p.year + "</span></button></li>"; }).join("") + "</ul>";
    }
    function showProject(label, fromPool) {
      dropMap();
      var p = PJ.projects.find(function (x) { return x.label === label; });
      back.hidden = !fromPool;
      body.innerHTML = card(p, true) + "<div class=dmap></div><div class='legend dleg'><span><i class=ln style='background:#4269d0'></i>Site</span><span><i class=ln style='background:#a9bdf0'></i>The rest of its two blocks</span></div>";
      var el = body.querySelector(".dmap");
      pmap = sfMap.create(el, { bounds: p.bounds, padding: function () { return 30; }, maxZoom: 17 });
      if (!pmap) return;
      var m = pmap;
      m.on("load", function () {
        var b = sfMap.under(m);
        function lines(enc) { return sfMap.collection(sfMap.decode(enc).map(function (r) { return { type: "Feature", properties: {}, geometry: r.length > 1 ? { type: "LineString", coordinates: r } : { type: "Point", coordinates: r[0] } }; })); }
        m.addSource("near", { type: "geojson", data: lines(p.n) });
        m.addSource("site", { type: "geojson", data: lines(p.s) });
        m.addLayer({ id: "near", type: "line", source: "near", paint: { "line-color": "#a9bdf0", "line-width": 5 }, layout: { "line-cap": "round" } }, b);
        m.addLayer({ id: "site", type: "line", source: "site", paint: { "line-color": "#4269d0", "line-width": 6 }, layout: { "line-cap": "round" } }, b);
      });
    }
    document.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest(".info");
      if (t) { dlg.showModal(); showPool(+t.dataset.pool); return; }   // open first, so the panel's map is sized
      var q = e.target.closest && e.target.closest("[data-p]");
      if (q && dlg.contains(q)) showProject(q.dataset.p, true);
    });
    back.addEventListener("click", function () { showPool(PJ.pools.indexOf(pool)); });
    dlg.querySelector(".close").addEventListener("click", function () { dlg.close(); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener("close", dropMap);
  })();
  var D = JSON.parse(document.getElementById("hin-data").textContent), el = document.getElementById("map");
  // The view lives in the address (src/injury-view.mjs): read it once here, write it back on every change.
  ${fnSource(readView)}
  ${fnSource(writeView)}
  ${fnSource(kidLine)}
  var FXNAMES = [].slice.call(document.querySelectorAll("input[name=fx]")).map(function (x) { return x.value; });
  var V = readView(location.search, D.schCds, FXNAMES);
  var S = { set: V.set };
  document.querySelectorAll("input[name=set]").forEach(function (x) { x.checked = x.value === V.set; });
  document.querySelectorAll("input[name=fx]").forEach(function (x) { x.checked = V.fx.indexOf(x.value) >= 0; });
  var pick = document.getElementById("school"), line = document.getElementById("school-line");
  pick.value = V.school || "";
  // Reset shows all of San Francisco, so it also drops the picked school and the saved position.
  // The components map switch (stack plan M7): ?map=components draws this map with @claude-workspaces/components
  // instead of MapLibre, and the MapLibre code below sees no map. Off by default. It draws the MapLibre map's
  // layers from the same data, under the same ids, and the page's layer menu drives them through the package's
  // setVisible (cwSync below), with the package's own switches hidden. Not drawn yet: the picked school's grounds
  // and rings, the kids hurt near it, and the zoomed-in crash dots; picking a school does not move the map.
  var CW = /(?:^|[?&])map=components(?:&|$)/.test(location.search);
  var map = CW ? null : sfMap.create(el, { bounds: D.bounds, padding: function () { return 16; }, onReset: function () { pickSchool(null, true); } });
  // Its own scope, so its names cannot overwrite the page's: #529 declared var line here, which replaced
  // the school line element and hid the kids' count above the map.
  if (CW) (function () {
    // A <link> rather than a URL in the script, so a SITE_BASE_PATH build prefixes it like every other href.
    var cwSrc = document.querySelector("link[rel=cw-map-src]");
    var X = D.fx, HEATC = ["#fde725", "#5ec962", "#21918c", "#3b528b", "#440154"], DASH = [6, 5], cwMap = null;
    var cwLines = function (enc, props) { return { type: "FeatureCollection", features: sfMap.decode(enc).map(function (r, i) { return { type: "Feature", properties: props ? props(i) : {}, geometry: { type: "LineString", coordinates: r } }; }) }; };
    var cwPts = function (enc, props) { return { type: "FeatureCollection", features: sfMap.points(enc).map(function (c, i) { return { type: "Feature", properties: props ? props(i) : {}, geometry: { type: "Point", coordinates: c } }; }) }; };
    var only = function (fc, test) { return { type: "FeatureCollection", features: fc.features.filter(function (f) { return test(f.properties); }) }; };
    var heat = function (k, name) { return { type: "heatmap", id: "heat-" + k, name: name, data: cwPts(D[k]), radius: 14, intensity: 0.6, colors: HEATC, opacity: 0.9, visible: false }; };
    var line = function (id, name, data, color, o) { return Object.assign({ type: "line", id: id, name: name, data: data, color: color, width: 3, opacity: 0.9, visible: false }, o || {}); };
    var dot = function (id, name, data, fill, o) { return Object.assign({ type: "circle", id: id, name: name, data: data, fill: fill, fillOpacity: 1, stroke: "#ffffff", strokeWidth: 1, radius: 5, visible: false }, o || {}); };
    var slow = cwLines(X.slow, function (i) { var r = X.slowP[i]; return { name: r[0], date: r[2] || "date not recorded", planned: r[3] }; });
    var calm = cwLines(X.calm, function (i) { var r = X.calmP[i]; return { name: r[0], where: r[1], date: r[2] || "date not recorded", planned: r[3], status: r[4] }; });
    var calmPts = cwPts(X.calmPts, function (i) { var r = X.calmPtsP[i]; return { name: r[0], where: r[1], date: r[2] || "date not recorded", planned: r[3], status: r[4] }; });
    var plan = cwLines(X.plan, function (i) { var r = X.planP[X.planI[i]]; return { name: r[0], phase: r[1], kind: r[4] }; });
    var PLAN = [["qb", "Planned quick-builds", "#efb118"], ["safety", "Planned safety and traffic calming", "#a463f2"], ["bike", "Planned bike lanes and Slow Streets", "#6cc5b0"], ["sig", "Planned signal work", "#4269d0"], ["area", "Planned streetscapes and area plans", "#9c6b4e"]];
    var layers = [heat("all", "All reported injuries"), heat("sev", "Severe and fatal only"), heat("kid", "Kids on school trips"), heat("kidsev", "Kids severely hurt or killed"),
      line("hin", "High Injury Network", cwLines(D.hin), "#4a4f57", { width: 2, opacity: 0.85, visible: true }),
      line("qb", "Quick-build corridors, 2018 to 2024", cwLines(D.qb, function (i) { return { name: D.qbNames[i] }; }), "#efb118", { popup: "{name}" }),
      line("to20", "20 mph streets, 2022 on", cwLines(X.to20, function (i) { return { date: X.to20P[i] }; }), "#4269d0", { popup: "20 mph from {date}" }),
      line("slow", "Slow Streets", only(slow, function (p) { return !p.planned; }), "#6cc5b0", { popup: "Slow Street: {name}, {date}" }),
      line("slow-p", "Pending Slow Streets", only(slow, function (p) { return !!p.planned; }), "#6cc5b0", { dash: DASH, popup: "Pending Slow Street: {name}" }),
      line("calm", "Speed humps and other calming, 2016 on", only(calm, function (p) { return !p.planned; }), "#a463f2", { popup: "{name}, {where}, {date}" }),
      line("calm-p", "Pending calming", only(calm, function (p) { return !!p.planned; }), "#a463f2", { dash: DASH, popup: "{name}, {where}: {status}" }),
    ].concat(PLAN.map(function (k) { return line("plan-" + k[0], k[1], only(plan, function (p) { return p.kind === k[0]; }), k[2], { dash: DASH, popup: "{name}: {phase}" }); }), [
      { type: "polygon", id: "tl", name: "Tenderloin daylighting area", data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [D.tl.concat([D.tl[0]])] } }, fill: "#ff8ab7", fillOpacity: 0, outline: "#15181c", outlineWidth: 1.5, visible: false },
      dot("cam", "Speed cameras, 2025", cwPts(D.cam, function (i) { return { name: D.camNames[i] }; }), "#ffffff", { stroke: "#15181c", strokeWidth: 1.6, popup: "Speed camera: {name}" }),
      dot("psz", "Painted safety zones", cwPts(X.psz, function (i) { var r = X.pszP[i]; return { where: r[0], date: r[1] || "date not recorded" }; }), "#ff8ab7", { popup: "Painted safety zone: {where}, {date}" }),
      dot("calmPts", "Calming at a point", only(calmPts, function (p) { return !p.planned; }), "#a463f2", { popup: "{name}, {where}, {date}" }),
      dot("calmPts-p", "Pending calming at a point", only(calmPts, function (p) { return !!p.planned; }), "#ffffff", { stroke: "#a463f2", strokeWidth: 2, popup: "{name}, {where}: {status}" }),
      dot("sch", "Schools in the School Trips tool", cwPts(D.sch, function (i) { return { name: D.schNames[i] }; }), "#e8eaf6", { stroke: "#5b3fa0", strokeWidth: 2, radius: 6, popup: "{name}" }),
    ]);
    // The menu's fix boxes, each to the layers it draws: the MapLibre map's FXL, under the same ids.
    var CWFX = { qb: ["qb"], cam: ["cam"], to20: ["to20"], day: ["tl", "psz"], slow: ["slow", "slow-p"], calm: ["calm", "calm-p", "calmPts", "calmPts-p"],
      "plan-qb": ["plan-qb"], "plan-safety": ["plan-safety", "calm-p", "calmPts-p"], "plan-bike": ["plan-bike", "slow-p"], "plan-sig": ["plan-sig"], "plan-area": ["plan-area"] };
    var cwFxIds = Object.keys(CWFX).reduce(function (a, k) { CWFX[k].forEach(function (id) { if (a.indexOf(id) < 0) a.push(id); }); return a; }, []);
    var cwSync = function () {
      if (!cwMap) return;
      var set = (document.querySelector("input[name=set]:checked") || {}).value || "all";
      ["all", "sev", "kid", "kidsev"].forEach(function (k) { cwMap.setVisible("heat-" + k, set === k); });
      cwMap.setVisible("sch", set === "kid" || set === "kidsev");
      var on = [];
      document.querySelectorAll("input[name=fx]:checked").forEach(function (x) { (CWFX[x.value] || []).forEach(function (id) { if (on.indexOf(id) < 0) on.push(id); }); });
      cwFxIds.forEach(function (id) { cwMap.setVisible(id, on.indexOf(id) >= 0); });
    };
    document.querySelectorAll("input[name=set], input[name=fx]").forEach(function (x) { x.addEventListener("change", cwSync); });
    el.removeAttribute("role");
    import(cwSrc.href).then(function (cw) {
      cwMap = cw.mountWithSnapshot(el, {
        id: "injury-map",
        layers: layers,
        legend: false,
        // The MapLibre map's opening view: the High Injury Network's bounds (D.bounds), centred.
        center: [(D.bounds[0][1] + D.bounds[1][1]) / 2, (D.bounds[0][0] + D.bounds[1][0]) / 2],
        zoom: 12,
        height: el.clientHeight || 600,
      });
      cwSync();
    }).catch(function (e) { if (window.console) console.warn("components map:", e && e.message); });
  })();
  if (map) {
    if (V.at) map.jumpTo({ center: [V.at.lon, V.at.lat], zoom: V.at.zoom });
    else if (V.school) map.fitBounds(D.schools[V.school].b, { padding: 30, duration: 0 });
  }
  function save() {
    // A sandboxed frame may refuse an address change; the view still works, only the address stays put.
    try { history.replaceState(history.state, "", location.pathname + writeView(V, location.search) + location.hash); } catch (e) {}
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: writeView(V, "") }));
  }
  // The kids' views: "Kids on school trips" (every kid hurt) and "Kids severely hurt or killed".
  function kidSet() { return S.set === "kid" || S.set === "kidsev"; }
  // The one line under the picker: the kids hurt within a quarter mile of the picked school, or across the city in
  // a kids' view with no school picked, people first.
  function schoolLine() {
    var s = V.school && D.schools[V.school], sev = S.set === "kidsev";
    document.querySelectorAll("[data-school-only]").forEach(function (x) { x.hidden = !s; });
    document.getElementById("kidpt-key").textContent = sev ? "A kid severely hurt or killed near the school" : "A kid hurt near the school";
    line.hidden = !s && !kidSet();
    if (line.hidden) return;
    var n = s ? (sev ? s.ks : s.k).length : sfMap.points(sev ? D.kidsev : D.kid).length;
    // The kids' ages, hours and years are in the note under the map, so the line carries only the count and the place.
    line.innerHTML = kidLine(n, sev, s && s.name);
  }
  function drawSchool() {
    if (!map || !map.getSource("sch-rings")) return;
    var s = V.school && D.schools[V.school], f = [], k = [];
    if (s) {
      sfMap.decode(s.g).forEach(function (r) { f.push({ type: "Feature", properties: { kind: "grounds" }, geometry: { type: "Polygon", coordinates: [r] } }); });
      sfMap.decode(s.z).forEach(function (r) { f.push({ type: "Feature", properties: { kind: "zone" }, geometry: { type: "LineString", coordinates: r } }); });
      sfMap.decode(s.q).forEach(function (r) { f.push({ type: "Feature", properties: { kind: "quarter" }, geometry: { type: "LineString", coordinates: r } }); });
      var sev = S.set === "kidsev", all = sfMap.points(sev ? D.kidsev : D.kid);
      k = (sev ? s.ks : s.k).map(function (i) { return { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: all[i] } }; });
    }
    map.getSource("sch-rings").setData(sfMap.collection(f));
    map.getSource("kid-near").setData(sfMap.collection(k));
  }
  // A school opens the kids' view fitted to its quarter-mile ring; "All of San Francisco" goes back to every injury, citywide.
  // The fitted view is not saved as a position, so a shared school link fits the ring on whatever screen opens it.
  function pickSchool(cds, homed) {
    V.school = cds && D.schools[cds] ? cds : null;
    pick.value = V.school || "";
    V.at = null;
    V.set = S.set = V.school ? (S.set === "kidsev" ? "kidsev" : "kid") : "all";
    document.querySelectorAll("input[name=set]").forEach(function (x) { x.checked = x.value === V.set; });
    apply(); sumLyr();
    if (map && V.school) map.fitBounds(D.schools[V.school].b, { padding: 30, duration: 600 });
    else if (map && !homed) map.fitBounds(D.bounds, { padding: 16, duration: 400 });
    drawSchool(); schoolLine(); save();
  }
  pick.addEventListener("change", function () { pickSchool(pick.value); });
  document.querySelectorAll("input[name=fx]").forEach(function (x) { x.addEventListener("change", function () { V.fx = picked(); save(); }); });
  // Copy link: this page's own address, so it works on sf-works.org, on staging and under the board's base path.
  var cbtn = document.getElementById("copy-link"), cin = document.getElementById("copy-url");
  cbtn.addEventListener("click", function () {
    var url = location.href.split(/[?#]/)[0] + writeView(V, "");
    function done(ok) {
      cbtn.textContent = ok ? "Copied" : "Select the link to copy it";
      cin.value = url; cin.hidden = ok;
      if (!ok) { cin.focus(); cin.select(); }
      setTimeout(function () { cbtn.textContent = "Copy link"; }, 2500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(function () { done(true); }, function () { done(false); });
    else done(false);
  });
  schoolLine();
  function lines(enc, names) {
    return sfMap.collection(sfMap.decode(enc).map(function (r, i) {
      return { type: "Feature", properties: { name: names ? names[i] : "" }, geometry: { type: "LineString", coordinates: r } };
    }));
  }
  function pts(d, names) {
    return sfMap.collection(sfMap.points(d).map(function (c, i) {
      return { type: "Feature", properties: names ? { name: names[i] } : {}, geometry: { type: "Point", coordinates: c } };
    }));
  }
  // One calm sequential ramp, pale to dark teal.
  // Density runs from 0 to the densest spot at 1. The stops sit on a square-root curve (colour k at density
  // (k/4)^2), so the many low and middle values read clearly and only the busiest spot reaches the darkest.
  // Viridis, run light to dark so the faintest density sits pale on the light basemap (Bryan, 2026-10-20: one
  // color-blind-safe scale with a wider range of colors for all three views).
  var HEAT = ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(253,231,37,0)", 0.01, "rgba(253,231,37,0.25)",
    0.0625, "rgba(94,201,98,0.7)", 0.25, "#21918c", 0.6, "#3b528b", 1, "#440154"];
  // MapLibre's heat map clamps density above 1, so a fixed intensity saturates the busiest areas. Set the
  // intensity at each zoom so the densest spot reaches exactly 1: its kernel sum (the shader's
  // GAUSS_COEF * exp(-4.5 (d/r)^2), summed over points within the radius r) is measured at every point.
  var RADIUS = { sev: [12, 32], kid: [12, 32], kidsev: [12, 32], all: [12, 32] }; // one blur for every view, so switching views changes only the data
  function radiusAt(k, z) { var r = RADIUS[k]; return z <= 11 ? r[0] : z >= 15 ? r[1] : r[0] + (r[1] - r[0]) * (z - 11) / 4; }
  function peak(coords, r, z) {
    var ws = 512 * Math.pow(2, z), P = coords.map(function (c) {
      var s = Math.sin(c[1] * Math.PI / 180);
      return [(c[0] + 180) / 360 * ws, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * ws];
    }), g = {}, best = 0;
    P.forEach(function (p, i) { var key = Math.floor(p[0] / r) + "," + Math.floor(p[1] / r); (g[key] = g[key] || []).push(i); });
    P.forEach(function (p) {
      var cx = Math.floor(p[0] / r), cy = Math.floor(p[1] / r), s = 0;
      for (var dx = -1; dx <= 1; dx++) for (var dy = -1; dy <= 1; dy++) (g[(cx + dx) + "," + (cy + dy)] || []).forEach(function (j) {
        var ex = (P[j][0] - p[0]) / r, ey = (P[j][1] - p[1]) / r, d2 = ex * ex + ey * ey;
        if (d2 < 1) s += Math.exp(-4.5 * d2);
      });
      if (s > best) best = s;
    });
    return best * 0.3989422804014327;
  }
  function intensity(k, coords) {
    var e = ["interpolate", ["linear"], ["zoom"]];
    for (var z = 10; z <= 18; z++) e.push(z, 1 / peak(coords, radiusAt(k, z), z));
    return e;
  }
  function apply() {

    document.querySelectorAll("[data-kid-only]").forEach(function (x) { x.hidden = !kidSet(); });
    if (map && map.getLayer("sch")) map.setLayoutProperty("sch", "visibility", kidSet() ? "visible" : "none");
    if (!map || !map.getLayer("heat-all")) return;
    ["all", "sev", "kid", "kidsev"].forEach(function (k) {
      map.setLayoutProperty("heat-" + k, "visibility", S.set === k ? "visible" : "none");
    });
  }
  document.querySelectorAll("input[name=set]").forEach(function (b) {
    b.addEventListener("change", function () { if (b.checked) { S.set = V.set = b.value; apply(); sumLyr(); drawSchool(); schoolLine(); save(); } });
  });
  var lyr = document.getElementById("lyr"), mq = window.matchMedia("(max-width: 700px)");
  function fitLyr() { lyr.open = !mq.matches; } fitLyr(); mq.addEventListener("change", fitLyr);
  function picked() { return [].slice.call(document.querySelectorAll("input[name=fx]:checked")).map(function (x) { return x.value; }); }
  // "Check all" in each fixes group (Bryan): ticks or clears the group, and shows ticked only when every box in it is.
  function groupOf(a) { return [].slice.call(a.closest("fieldset").querySelectorAll("input[name=fx]")); }
  function syncAll() { document.querySelectorAll("[data-fx-all]").forEach(function (a) { var g = groupOf(a), n = g.filter(function (x) { return x.checked; }).length; a.checked = n === g.length; a.indeterminate = n > 0 && n < g.length; }); }
  document.querySelectorAll("[data-fx-all]").forEach(function (a) { a.addEventListener("change", function () { var g = groupOf(a); g.forEach(function (x) { x.checked = a.checked; }); g[g.length - 1].dispatchEvent(new Event("change")); }); });
  function sumLyr() { var n = picked().length, r = document.querySelector("input[name=set]:checked");
    syncAll();
    document.getElementById("lyr-sum").textContent = r.nextElementSibling.textContent + (n ? ", " + n + (n === 1 ? " fix" : " fixes") : "");
    document.querySelectorAll("[data-dash]").forEach(function (x) { x.hidden = !picked().some(function (v) { return v === "slow" || v === "calm" || v.indexOf("plan-") === 0; }); }); }
  sumLyr();
  apply();
  if (!map) return;
  map.on("load", function () {
    var b = sfMap.under(map);
    map.addSource("hin", { type: "geojson", data: lines(D.hin) });
    map.addSource("qb", { type: "geojson", data: lines(D.qb, D.qbNames) });
    map.addSource("all", { type: "geojson", data: pts(D.all) });
    map.addSource("sev", { type: "geojson", data: pts(D.sev) });
    map.addSource("kid", { type: "geojson", data: pts(D.kid) });
    map.addSource("kidsev", { type: "geojson", data: pts(D.kidsev) });
    map.addSource("cam", { type: "geojson", data: pts(D.cam, D.camNames) });
    map.addSource("tl", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [D.tl.concat([D.tl[0]])] } } });
    ["all", "sev", "kid", "kidsev"].forEach(function (k) {
      map.addLayer({ id: "heat-" + k, type: "heatmap", source: k, layout: { visibility: "none" }, paint: {
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, RADIUS[k][0], 15, RADIUS[k][1]],
        "heatmap-intensity": intensity(k, sfMap.points(D[k])),
        "heatmap-color": HEAT, "heatmap-opacity": 0.9 } }, b);
    });
    var w = ["interpolate", ["linear"], ["zoom"], 11, 1.5, 14, 3, 17, 6];
    var w2 = ["interpolate", ["linear"], ["zoom"], 11, 3, 14, 5, 17, 9];
    map.addLayer({ id: "hin", type: "line", source: "hin", paint: { "line-color": "#4a4f57", "line-width": w, "line-opacity": 0.85 }, layout: { "line-cap": "round" } }, b);
    var X = D.fx, none = { visibility: "none" };
    function fl(enc, props) { return sfMap.collection(sfMap.decode(enc).map(function (r, i) { return { type: "Feature", properties: props(i), geometry: { type: "LineString", coordinates: r } }; })); }
    function fp(enc, props) { return sfMap.collection(sfMap.points(enc).map(function (c, i) { return { type: "Feature", properties: props(i), geometry: { type: "Point", coordinates: c } }; })); }
    map.addSource("to20", { type: "geojson", data: fl(X.to20, function (i) { return { date: X.to20P[i] }; }) });
    map.addSource("slow", { type: "geojson", data: fl(X.slow, function (i) { var r = X.slowP[i]; return { name: r[0], ext: r[1], date: r[2], planned: r[3] }; }) });
    map.addSource("calm", { type: "geojson", data: fl(X.calm, function (i) { var r = X.calmP[i]; return { name: r[0], where: r[1], date: r[2], planned: r[3], status: r[4] }; }) });
    map.addSource("calmPts", { type: "geojson", data: fp(X.calmPts, function (i) { var r = X.calmPtsP[i]; return { name: r[0], where: r[1], date: r[2], planned: r[3], status: r[4] }; }) });
    map.addSource("psz", { type: "geojson", data: fp(X.psz, function (i) { var r = X.pszP[i]; return { where: r[0], date: r[1] }; }) });
    map.addSource("plan", { type: "geojson", data: fl(X.plan, function (i) { var r = X.planP[X.planI[i]]; return { name: r[0], phase: r[1], page: r[2], end: r[3], kind: r[4], cost: r[5] }; }) });
    function lineL(id, src, col, filt, dash) { var o = { id: id, type: "line", source: src, layout: Object.assign({ "line-cap": dash ? "butt" : "round" }, none), paint: { "line-color": col, "line-width": w2 } };
      if (dash) o.paint["line-dasharray"] = [1.2, 1]; if (filt) o.filter = filt; map.addLayer(o, b); }
    lineL("qb", "qb", "#efb118");
    lineL("to20", "to20", "#4269d0");
    lineL("slow", "slow", "#6cc5b0", ["==", ["get", "planned"], 0]); lineL("slow-p", "slow", "#6cc5b0", ["==", ["get", "planned"], 1], true);
    lineL("calm", "calm", "#a463f2", ["==", ["get", "planned"], 0]); lineL("calm-p", "calm", "#a463f2", ["==", ["get", "planned"], 1], true);
    var PCOL = { qb: "#efb118", safety: "#a463f2", bike: "#6cc5b0", sig: "#4269d0", area: "#9c6b4e" };
    Object.keys(PCOL).forEach(function (k) { lineL("plan-" + k, "plan", PCOL[k], ["==", ["get", "kind"], k], true); });
    map.addLayer({ id: "tl", type: "line", source: "tl", layout: none, paint: { "line-color": "#15181c", "line-width": 1.5, "line-dasharray": [2, 2] } });
    var rad = ["interpolate", ["linear"], ["zoom"], 11, 3.5, 15, 6.5];
    map.addLayer({ id: "cam", type: "circle", source: "cam", layout: none, paint: { "circle-color": "#ffffff", "circle-stroke-color": "#15181c", "circle-stroke-width": 1.6, "circle-radius": rad } });
    map.addLayer({ id: "psz", type: "circle", source: "psz", layout: none, paint: { "circle-color": "#ff8ab7", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1, "circle-radius": rad } });
    map.addLayer({ id: "calmPts", type: "circle", source: "calmPts", layout: none, filter: ["==", ["get", "planned"], 0], paint: { "circle-color": "#a463f2", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1, "circle-radius": rad } });
    map.addLayer({ id: "calmPts-p", type: "circle", source: "calmPts", layout: none, filter: ["==", ["get", "planned"], 1], paint: { "circle-color": "#ffffff", "circle-stroke-color": "#a463f2", "circle-stroke-width": 2, "circle-radius": rad } });
    var FXL = { qb: ["qb"], cam: ["cam"], to20: ["to20"], day: ["tl", "psz"], slow: ["slow", "slow-p"], calm: ["calm", "calm-p", "calmPts", "calmPts-p"],
      "plan-qb": ["plan-qb"], "plan-safety": ["plan-safety", "calm-p", "calmPts-p"], "plan-bike": ["plan-bike", "slow-p"], "plan-sig": ["plan-sig"], "plan-area": ["plan-area"] };
    var ALLFX = ["qb", "cam", "to20", "tl", "psz", "slow", "slow-p", "calm", "calm-p", "calmPts", "calmPts-p", "plan-qb", "plan-safety", "plan-bike", "plan-sig", "plan-area"];
    function onLayers() { var on = []; picked().forEach(function (v) { (FXL[v] || []).forEach(function (id) { if (on.indexOf(id) < 0) on.push(id); }); }); return on; }
    function showFx() { var on = onLayers(); ALLFX.forEach(function (id) { map.setLayoutProperty(id, "visibility", on.indexOf(id) >= 0 ? "visible" : "none"); }); sumLyr(); }
    document.querySelectorAll("input[name=fx]").forEach(function (x) { x.addEventListener("change", showFx); }); showFx();
    // Schools, kids view only: a square marker, so it can't be mistaken for a camera's white circle.
    var c = document.createElement("canvas"), px = 2, sz = 13 * px; c.width = c.height = sz;
    var g = c.getContext("2d"); g.fillStyle = "#5b3fa0"; g.fillRect(0, 0, sz, sz); g.fillStyle = "#e8eaf6"; g.fillRect(2.5 * px, 2.5 * px, sz - 5 * px, sz - 5 * px);
    map.addImage("sch-sq", g.getImageData(0, 0, sz, sz), { pixelRatio: px });
    map.addSource("sch", { type: "geojson", data: sfMap.collection(sfMap.points(D.sch).map(function (c, i) { return { type: "Feature", properties: { name: D.schNames[i], cds: D.schCds[i] }, geometry: { type: "Point", coordinates: c } }; })) });
    // The picked school: its grounds, the 500 ft and quarter-mile rings round them, and the kids hurt inside the
    // quarter mile as dots over the kids' heat map.
    map.addSource("sch-rings", { type: "geojson", data: sfMap.collection([]) });
    map.addSource("kid-near", { type: "geojson", data: sfMap.collection([]) });
    map.addLayer({ id: "sch-grounds", type: "fill", source: "sch-rings", filter: ["==", ["get", "kind"], "grounds"], paint: { "fill-color": "#e8eaf6", "fill-opacity": 0.7, "fill-outline-color": "#5b3fa0" } });
    map.addLayer({ id: "sch-zone", type: "line", source: "sch-rings", filter: ["==", ["get", "kind"], "zone"], paint: { "line-color": "#5b3fa0", "line-width": 2 } });
    map.addLayer({ id: "sch-quarter", type: "line", source: "sch-rings", filter: ["==", ["get", "kind"], "quarter"], paint: { "line-color": "#5b3fa0", "line-width": 2, "line-dasharray": [2, 1.5] } });
    map.addLayer({ id: "sch", type: "symbol", source: "sch", layout: { "icon-image": "sch-sq", "icon-allow-overlap": true, visibility: "none",
      "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.75, 15, 1.2] } });
    map.addLayer({ id: "kid-near", type: "circle", source: "kid-near", paint: { "circle-color": "#15181c", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 3.5, 16, 6] } });
    drawSchool();
    // The map's centre and zoom go in the address only when the reader moves it (a drag, a zoom, the zoom buttons).
    // Moves the page makes itself, a fit to a school, Reset or a resize, carry no originalEvent and save nothing.
    map.on("moveend", function (e) {
      if (!e.originalEvent) return;
      var c = map.getCenter(); V.at = { lat: c.lat, lon: c.lng, zoom: map.getZoom() };
      save();
    });
    var hov = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on("mousemove", "sch", function (e) { map.getCanvas().style.cursor = "pointer"; hov.setLngLat(e.features[0].geometry.coordinates).setText(e.features[0].properties.name).addTo(map); });
    map.on("mouseleave", "sch", function () { map.getCanvas().style.cursor = ""; hov.remove(); });
    map.sfReady = true;
    apply();
    var pop = new maplibregl.Popup({ closeButton: false, closeOnClick: true, offset: 6 });
    function e_(s) { return String(s == null ? "" : s).replace(/[&<>'"]/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }
    var NOCOST = "<p class=proj-when>Cost: No published cost.</p>";
    function src(id, d) { return "<p class=proj-more>Source: DataSF <a href='https://data.sfgov.org/d/" + id + "' target=_blank rel=noopener>" + id + "</a>, read " + d + ".</p>"; }
    function fxCard(id, P) {
      var h = function (t) { return "<div class='proj-card pc'><h3 class=proj-name>" + t + "</h3>"; };
      if (id === "to20") return h("Lowered to 20 mph") + "<p class=proj-when>Approved by the SFMTA Board on " + e_(P.date) + " under the 2022 state law that lets cities post 20 mph. The data has no date the signs went up.</p>" + NOCOST + src("3t7b-gebn", X.fetched.to20) + "</div>";
      if (id === "slow" || id === "slow-p") return h(e_(P.name)) + "<p class=proj-when>" + e_(P.ext) + ". " + (P.planned ? "Planned." : "In place since " + e_(P.date) + ".") + "</p>" + NOCOST + src("hkz3-itiu", X.fetched.slow) + "</div>";
      if (id.indexOf("calm") === 0) return h(e_(P.name)) + "<p class=proj-when>" + e_(P.where) + ". " + (P.planned ? e_(P.status) + "." : "Installed " + e_(P.date) + ".") + "</p>" + NOCOST + src(id.indexOf("Pts") > 0 ? "bp3t-bd4t" : "abhw-ffzx", X.fetched.calm) + "</div>";
      if (id === "psz") return h("Painted safety zone") + "<p class=proj-when>" + e_(P.where) + (P.date ? ", installed " + e_(P.date) : "") + ".</p>" + NOCOST + src("vtn2-q8ky", X.fetched.psz) + "</div>";
      if (id === "tl") return h("Tenderloin daylighting") + "<p class=proj-when>Red zones at about 80 intersections by March 2015.</p>" + NOCOST + "</div>";
      if (id.indexOf("plan-") === 0) return h(P.page ? "<a href='" + e_(P.page) + "' target=_blank rel=noopener>" + e_(P.name) + "</a>" : e_(P.name)) + "<p class=proj-when>Phase: " + e_(P.phase) + (P.end ? ", expected " + e_(P.end) : "") + ".</p>" + (P.cost ? "<p class=proj-when>Cost: " + P.cost + "</p>" : NOCOST) + "<p class=proj-more>Source: SFMTA's project layer and pages, as gathered on " + X.fetched.planned + ".</p></div>";
      return null;
    }
    map.on("click", function (e) {
      var on = onLayers().slice().reverse();
      var f = sfMap.near(map, e.point, (kidSet() ? ["sch"] : []).concat(on, ["hin"]));
      if (!f.length) { pop.remove(); return; }
      // A school square picks that school, as the picker does.
      if (f[0].layer.id === "sch") { pop.remove(); pickSchool(f[0].properties.cds); return; }
      var x = f[0], P = x.properties, t = x.layer.id === "sch" ? P.name : x.layer.id === "cam" ? "Speed camera: " + P.name : x.layer.id === "qb" ? P.name : "High Injury Network";
      var html = (x.layer.id === "qb" || x.layer.id === "cam") && window.projCard ? window.projCard(P.name) : fxCard(x.layer.id, P);
      if (html) pop.setLngLat(e.lngLat).setHTML(html).setMaxWidth("300px").addTo(map); else pop.setLngLat(e.lngLat).setText(t).setMaxWidth("240px").addTo(map);
    });
  });
})();
</script>
</div>
`;
// Spell out each agency acronym at its first use in the page text (Bryan).
const ACRO = [["SFMTA", "San Francisco Municipal Transportation Agency (SFMTA)"], ["SFDPH", "San Francisco Department of Public Health (SFDPH)"],
  ["SFCTA", "San Francisco County Transportation Authority (SFCTA)"], ["SFPD", "San Francisco Police Department (SFPD)"], ["TNC", "ride-hail (TNC)"]];
let out = html.replaceAll("%%M_ROWS%%", String(FIXES.length));
const m0 = out.indexOf("<!--hin-body-->"), m1 = out.indexOf("<!--/hin-body-->");
let main = out.slice(m0, m1);
for (const [a, full] of ACRO) {   // first use outside a quotation: an even count of quote marks before it in its text run
  let done = false;
  main = main.replace(new RegExp(`(>[^<]*?)\\b${a}\\b`, "g"), (m, pre) => { if (done || (pre.match(/"/g) || []).length % 2) return m; done = true; return pre + full; });
}
out = out.slice(0, m0) + main + out.slice(m1);
return out;
}
