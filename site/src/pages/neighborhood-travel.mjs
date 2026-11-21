// How Residents Travel: One City, Many Neighborhoods. One map of San
// Francisco by census tract, drawn as small multiples: up to four measures
// side by side at the same zoom, or one map per way of getting to work.
// Pointing at a tract (tapping on a phone) lists all of its numbers.
//
// Bryan, on the whitepaper's neighborhood maps (2026-11-17): "Make it easy for a user to
// put multiple different metrics on screen with different metrics. Or do small multiples across multiple
// categorical values in one metric like travel modes." The mode maps share one scale (Bryan, 2026-11-13, on
// the whitepaper's nhood-modes maps), so their colours compare directly.
//
// Controls left, maps middle, the tract's numbers right, on one 1366x768 screen. One control: the measure
// list. The state is in the address (?show=a,b or the default, one map per mode).

import { page } from "../layout.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import { D, MEASURES, GROUPS, UNITS, MODES, MAX_SHOWN, DEFAULT, RANGE, CITY, RAMP, NONE, READ, SOURCES } from "../neighborhood-travel.mjs";

export const path = "/transportation/how-residents-travel";
export const file = "transportation/how-residents-travel/index.html";
export const listing = {
  title: "How Residents Travel",
  line: "Tract by tract maps of how San Franciscans get to work, own cars, get hurt, wait for Muni and reach the bike network.",
  parent: "section",
  order: 3,
};
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = READ;
const ABOUT = `${path}/about`;
const TITLE = "How Residents Travel: One City, Many Neighborhoods";

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// The city's extent, from the tract outlines.
function bounds() {
  let x = 0, y = 0, w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const d = D.outline.d;
  for (let k = 0; k < d.length; k += 2) {
    x += d[k]; y += d[k + 1];
    if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y;
  }
  return [[w / 1e5, s / 1e5], [e / 1e5, n / 1e5]];
}

const CSS = `<style>
.nt-head, .nt { width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); }
.nt-head h1 { font-size: clamp(1.25rem, 2.2vw, 1.55rem); margin: 0 0 2px; }
.nt-head .lede { margin: 0 0 10px; max-width: 120ch; font-size: 0.93rem; }
.nt { display: grid; grid-template-columns: 230px minmax(0, 1fr) 270px; gap: 14px; height: max(520px, calc(100dvh - 210px)); }
.nt h2 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 14px 0 5px; font-weight: 600; font-family: inherit; }
.nt-ctl { overflow-y: auto; min-height: 0; padding-right: 4px; }
.nt-ctl h2:first-child { margin-top: 0; }
.nt-opts { display: flex; flex-wrap: wrap; gap: 4px; }
.nt-opt { font: inherit; font-size: 0.84rem; text-align: left; border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 6px; padding: 3px 9px; cursor: pointer; line-height: 1.3; }
.nt-opt:hover { background: var(--raised); }
.nt-opt[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: #fff; font-weight: 600; }
.nt-opt:focus-visible { outline: 2px solid #3a87c0; outline-offset: 2px; }
.nt-opt.modes { flex-basis: 100%; }
.nt-note { margin: 6px 0 0; font-size: 0.75rem; color: var(--muted); line-height: 1.3; }
.nt-grid { display: grid; gap: 8px; min-height: 0; height: 100%; grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr)); grid-auto-rows: minmax(0, 1fr); }
.nt-panel { display: flex; flex-direction: column; min-height: 0; min-width: 0; border: 1px solid var(--rule); border-radius: 6px; padding: 5px 6px 6px; }
.nt-panel[hidden] { display: none; }
.nt-panel h3 .u { font-weight: 400; color: var(--muted); font-size: 0.76rem; }
.nt-panel h3 { margin: 0 0 3px; font-size: 0.84rem; font-weight: 600; line-height: 1.25; font-family: inherit; min-height: 1.25em; }
.nt-panel .glmap { flex: 1 1 auto; min-height: 120px; }
.nt-src { margin: 3px 0 0; font-size: 0.7rem; color: var(--muted); line-height: 1.25; }
.nt-src a { color: inherit; }
.nt-key { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: var(--muted); margin: 0 0 4px; font-variant-numeric: tabular-nums; }
.nt-ramp { position: relative; flex: 1 1 auto; max-width: 180px; height: 9px; border-radius: 2px; }
.nt-ramp .tick { position: absolute; top: -3px; width: 2px; height: 15px; background: var(--ink); }
.nt-key .none { display: inline-block; width: 11px; height: 9px; background: ${NONE}; border-radius: 2px; margin-left: 4px; }
.nt-legend { display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 8px 10px; }
.nt-legend .nt-key { font-size: 0.8rem; }
.nt-legend .nt-ramp { max-width: none; height: 12px; }
.nt-out { display: flex; flex-direction: column; min-height: 0; }
.nt-card { font-size: 0.8rem; min-height: 0; overflow: auto; }
.nt-card .hint { color: var(--muted); margin: 0; }
.nt-card .who { margin: 0 0 4px; font-size: 0.86rem; }
.nt-card table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
.nt-card td { padding: 1px 0; border: 0; line-height: 1.25; font-size: 0.78rem; vertical-align: top; }
.nt-card td + td { text-align: right; white-space: nowrap; padding-left: 8px; }
.nt-card tr.on td { font-weight: 700; }
.nt-card tr.grp td { padding-top: 6px; color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; }
.nt-asof { margin: 8px 0 0; font-size: 0.74rem; color: var(--muted); }
.nt .nt-grid .nt-panel:not(.lead) .glmap .maplibregl-ctrl-top-right { display: none; }
.nt-panel .maplibregl-ctrl-attrib { font-size: 0.6rem; }
@media (max-width: 760px) {
  .nt-head .lede { font-size: 0.86rem; margin-bottom: 6px; }
  .nt { grid-template-columns: minmax(0, 1fr); height: auto; gap: 8px; }
  .nt-ctl { overflow: visible; padding: 0; }
  .nt-ctl h2, .nt-note { display: none; }
  .nt-ctl > div { display: contents; }
  .nt-ctl { display: flex; flex-wrap: wrap; gap: 4px; }
  .nt-opts { display: contents; }
  .nt-opt.modes { flex-basis: auto; }
  .nt-key { flex-wrap: wrap; row-gap: 2px; }
  .nt .nt-panel .glmap .maplibregl-ctrl-top-right { display: none; }
  .nt-ramp { flex-basis: 100%; order: -1; max-width: none; }
  .nt-opt { white-space: nowrap; font-size: 0.74rem; padding: 2px 7px; }
  .nt-grid { height: auto; grid-template-columns: repeat(2, minmax(0, 1fr)); grid-auto-rows: auto; }
  .nt-grid.one { grid-template-columns: minmax(0, 1fr); }
  .nt-panel .glmap { height: 190px; flex: none; }
  .nt-grid.one .nt-panel .glmap { height: 300px; }
  .nt-panel h3 { font-size: 0.78rem; min-height: 3.6em; }
  .nt-panel h3 .u { display: block; font-size: 0.7rem; }
  .nt-key { min-height: 2.6em; align-content: flex-start; }
  .nt-src { display: none; }
  .nt-legend { padding: 4px 6px; }
}
</style>`;

const MDEF = MEASURES.map(([k, title, fmt, group, src, short]) => ({ k, title: short, unit: UNITS[k] || "", fmt, group, src }));
const btn = (m) => `<button type="button" class="nt-opt" data-k="${m.k}" aria-pressed="false">${esc(m.title)}</button>`;
const groupsHtml = GROUPS.filter(([g]) => MDEF.some((m) => m.group === g)).map(([g, label]) =>
  `<div><h2>${esc(label)}</h2><div class="nt-opts">${g === "work" ? `<button type="button" class="nt-opt modes" data-k="modes" aria-pressed="true">All five, side by side</button>` : ""}${MDEF.filter((m) => m.group === g).map(btn).join("")}</div></div>`).join("");

// Six panels, made once: the five mode maps fill five and the shared legend the sixth.
const PANELS = Array.from({ length: 6 }, (_, i) =>
  `<div class="nt-panel${i === 0 ? " lead" : ""}" data-panel="${i}" hidden><h3 data-title></h3><div class="nt-key" data-key></div><div class="glmap" id="nt-map-${i}" role="region" aria-label="Map of San Francisco tracts"></div><p class="nt-src" data-src></p></div>`).join("");

const CONFIG = {
  measures: MDEF, groups: GROUPS, modes: MODES, max: MAX_SHOWN, def: DEFAULT, range: RANGE, city: CITY, ramp: RAMP, none: NONE,
  bounds: bounds(), minPop: D.min_pop,
};
// The tract data the maps colour, inlined: 241 tracts.
const DATA = { geoid: D.geoid, hood: D.hood, hoods: D.hoods, pop: D.pop, metrics: Object.fromEntries(MEASURES.map(([k]) => [k, D.metrics[k]])), outline: D.outline };

const SCRIPT = `<script type="application/json" id="nt-config">${inlineJson(CONFIG)}</script>
<script type="application/json" id="nt-data">${inlineJson(DATA)}</script>
<script>
(function () {
  var C = JSON.parse(document.getElementById("nt-config").textContent);
  var D = JSON.parse(document.getElementById("nt-data").textContent);
  var root = document.querySelector("[data-nt]");
  var $ = function (s) { return root.querySelector(s); }, $$ = function (s) { return Array.prototype.slice.call(root.querySelectorAll(s)); };
  var M = {}; C.measures.forEach(function (m) { M[m.k] = m; });
  var S = { view: C.def.view, show: C.def.show.slice(), sel: null, hover: null };
  (function fromUrl() {
    var q = new URLSearchParams(location.search).get("show");
    if (!q) return;
    var ks = q.split(",").filter(function (k, j, all) { return M[k] && all.indexOf(k) === j; }).slice(0, C.max);
    if (ks.length) { S.view = "pick"; S.show = ks; }
  })();
  if (window.matchMedia("(min-width: 761px)").matches) {
    var top = root.getBoundingClientRect().top + window.scrollY;
    root.style.height = Math.max(520, window.innerHeight - top - 10) + "px";
  }
  function sig2(v) {
    if (v === 0) return "0";
    var p = Math.pow(10, Math.floor(Math.log10(Math.abs(v))) - 1);
    var r = Math.round(v / p) * p;
    return r.toLocaleString("en-US", { maximumFractionDigits: Math.max(0, -Math.floor(Math.log10(p))) });
  }
  function fmt(k, v) {
    if (v == null) return "\\u2014";
    switch (M[k].fmt) {
      case "pct": return Math.round(100 * v) + "%";
      case "pctw": return Math.round(v) + "%";
      case "dec": return v >= 10 ? String(Math.round(v)) : v.toFixed(1);
      case "min": return Math.round(v) + " min";
      case "min1": return v.toFixed(1) + " min";
      case "ft": return v < 5280 ? sig2(v) + " ft" : sig2(v / 5280) + " mi";
    }
    return String(v);
  }
  function shown() { return S.view === "modes" ? C.modes : S.show; }
  function grad() { return "linear-gradient(to right," + C.ramp.join(",") + ")"; }
  function key(k, withNone, noCity) {
    var hi = C.range[k], c = noCity ? null : C.city[k], x = c == null ? null : Math.max(0, Math.min(1, c / hi));
    var none = withNone && D.metrics[k].some(function (v) { return v == null; });
    return '<span>' + fmt(k, 0) + '</span><span class="nt-ramp" style="background:' + grad() + '">' +
      (x == null ? "" : '<span class="tick" style="left:calc(' + (100 * x).toFixed(1) + '% - 1px)" title="San Francisco"></span>') +
      '</span><span>' + fmt(k, hi) + '+</span>' + (x == null ? "" : '<span>| SF ' + fmt(k, c) + '</span>') + (none ? '<span class="none"></span><span>no figure</span>' : "");
  }
  function setUrl() {
    var q = S.view === "modes" ? "" : "?show=" + S.show.join(",");
    history.replaceState(null, "", location.pathname + q + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: q }));
  }
  var maps = [], feats = null, sync = false;
  function colour(k) {
    var hi = C.range[k], stops = [];
    C.ramp.forEach(function (c, i) { stops.push(hi * i / (C.ramp.length - 1), c); });
    return ["case", ["==", ["get", k], null], C.none, ["interpolate", ["linear"], ["get", k]].concat(stops)];
  }
  function layout() {
    var ks = shown(), modes = S.view === "modes", n = ks.length + (modes ? 1 : 0);
    var cols = n <= 1 ? 1 : n <= 4 ? 2 : 3;
    var grid = $(".nt-grid");
    grid.style.setProperty("--cols", cols);
    grid.classList.toggle("one", n <= 1);
    $$("[data-panel]").forEach(function (p, i) {
      var k = ks[i], legend = modes && i === ks.length;
      p.hidden = !k && !legend;
      p.classList.toggle("nt-legend", !!legend);
      p.querySelector(".glmap").style.display = legend ? "none" : "";
      p.querySelector("[data-title]").innerHTML = legend ? "Share of working residents" : k ? M[k].title + ' <span class="u">' + M[k].unit + "</span>" : "";
      p.querySelector("[data-key]").innerHTML = legend ? key(C.modes[0], true, true) : k && !modes ? key(k, true) : "";
      p.querySelector("[data-src]").innerHTML = legend ? M[C.modes[0]].src : k && !modes ? M[k].src : "";
      if (legend) p.querySelector("[data-key]").style.display = "";
      var m = maps[i];
      if (m && k && m.getLayer("nt-fill")) m.setPaintProperty("nt-fill", "fill-color", colour(k));
    });
    maps.forEach(function (m) { if (m) m.resize(); });
  }
  function controls() {
    $$("[data-k]").forEach(function (b) {
      var on = b.dataset.k === "modes" ? S.view === "modes" : S.view === "pick" && S.show.indexOf(b.dataset.k) >= 0;
      b.setAttribute("aria-pressed", String(on));
    });
  }
  function card() {
    var box = $("[data-card]"), i = S.hover != null ? S.hover : S.sel;
    if (i == null) { box.innerHTML = '<p class="hint">Point at a tract, or tap one, to see all of its numbers.</p>'; return; }
    var on = shown(), rows = "";
    C.groups.forEach(function (g) {
      var ms = C.measures.filter(function (m) { return m.group === g[0]; });
      if (!ms.length) return;
      rows += '<tr class="grp"><td colspan="2">' + g[1] + "</td></tr>";
      ms.forEach(function (m) {
        rows += '<tr class="' + (on.indexOf(m.k) >= 0 ? "on" : "") + '"><td>' + m.title + "</td><td>" + fmt(m.k, D.metrics[m.k][i]) + "</td></tr>";
      });
    });
    box.innerHTML = '<p class="who"><b>' + String(D.hoods[D.hood[i]]).replace(/[&<>"]/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }) + "</b>, tract " + String(parseInt(D.geoid[i].slice(5), 10) / 100) +
      ", " + D.pop[i].toLocaleString("en-US") + " residents</p><table><tbody>" + rows + "</tbody></table>";
  }
  function highlight() {
    var i = S.hover != null ? S.hover : S.sel;
    maps.forEach(function (m) { if (m && m.getLayer("nt-sel")) m.setFilter("nt-sel", ["==", ["get", "i"], i == null ? -1 : i]); });
  }
  function render() { controls(); layout(); card(); highlight(); setUrl(); }
  root.addEventListener("click", function (e) {
    var b = e.target.closest("[data-k]");
    if (!b) return;
    var k = b.dataset.k;
    if (k === "modes") { S.view = "modes"; }
    else if (S.view === "modes") { S.view = "pick"; S.show = [k]; }
    else {
      var at = S.show.indexOf(k);
      if (at >= 0) { if (S.show.length > 1) S.show.splice(at, 1); }
      else { S.show.push(k); if (S.show.length > C.max) S.show.shift(); }
    }
    render();
  });

  function build() {
    var runs = sfMap.decode({ n: D.outline.n, d: D.outline.d }), k = 0, out = [];
    for (var i = 0; i < D.pop.length; i++) {
      var polys = D.outline.shape[i].map(function (rings) { var p = runs.slice(k, k + rings); k += rings; return p; });
      var props = { i: i };
      C.measures.forEach(function (m) { props[m.k] = D.metrics[m.k][i]; });
      out.push({ type: "Feature", properties: props, geometry: { type: "MultiPolygon", coordinates: polys } });
    }
    return out;
  }
  feats = build();
  render();
  $$("[data-panel]").forEach(function (p, idx) {
    var el = p.querySelector(".glmap");
    var m = sfMap.create(el, { bounds: C.bounds, padding: function () { return { top: 6, bottom: 24, left: 6, right: 6 }; }, maxZoom: 16, onReset: function () { S.sel = null; render(); } });
    maps[idx] = m;
    if (!m) return;
    m.on("move", function (e) {
      if (sync || !e.originalEvent) return;
      sync = true;
      var c = m.getCenter(), z = m.getZoom();
      maps.forEach(function (o) { if (o && o !== m) o.jumpTo({ center: c, zoom: z }); });
      sync = false;
    });
    // The Reset and +/- buttons move the lead map without an originalEvent; follow it too.
    if (idx === 0) m.on("moveend", function () {
      if (sync) return;
      sync = true;
      var c = m.getCenter(), z = m.getZoom();
      maps.forEach(function (o) { if (o && o !== m) o.jumpTo({ center: c, zoom: z }); });
      sync = false;
    });
    m.on("load", function () {
      var before = sfMap.under(m), ks = shown();
      m.addSource("nt", { type: "geojson", data: sfMap.collection(feats) });
      m.addLayer({ id: "nt-fill", type: "fill", source: "nt", paint: { "fill-color": colour(ks[idx] || C.measures[0].k),
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.85, 15, 0.55] } }, before);
      m.addLayer({ id: "nt-edge", type: "line", source: "nt", paint: { "line-color": "#ffffff", "line-width": 0.5, "line-opacity": 0.9 } }, before);
      m.addLayer({ id: "nt-sel", type: "line", source: "nt", filter: ["==", ["get", "i"], -1], paint: { "line-color": sfMap.token("--ink"), "line-width": 2.2 } }, before);
      layout(); highlight();
      m.on("mousemove", "nt-fill", function (e) { var f = e.features && e.features[0]; if (!f || f.properties.i === S.hover) return; S.hover = f.properties.i; card(); highlight(); m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "nt-fill", function () { S.hover = null; card(); highlight(); m.getCanvas().style.cursor = ""; });
      m.on("click", "nt-fill", function (e) { var f = e.features && e.features[0]; if (!f) return; S.sel = f.properties.i; S.hover = null; card(); highlight();
        if (window.matchMedia("(max-width: 760px)").matches) $("[data-card]").scrollIntoView({ behavior: "smooth", block: "nearest" }); });
    });
  });
})();
</script>`;

export function render() {
  const body = `${CSS}
<div class="nt-head">
  <h1>${esc(TITLE)}</h1>
  <p class="lede">Each map shades San Francisco's ${D.geoid.length} census tracts, about 3,500 residents each, by one measure, darker for more.</p>
</div>
<div class="nt" data-nt>
  <div class="nt-ctl">${groupsHtml}<p class="nt-note">Up to four at once. A fifth replaces the first.</p></div>
  <div class="nt-grid">${PANELS}</div>
  <div class="nt-out">
    <div class="nt-card" data-card><p class="hint">Point at a tract, or tap one, to see all of its numbers.</p></div>
    <p class="nt-asof"><a href="${ABOUT}">How we measured</a></p>
  </div>
</div>
${MAP_HEAD}
${SCRIPT}`;
  return page({
    title: TITLE,
    description: "Maps of every San Francisco census tract side by side: how workers get to work, cars and car miles, people hurt in traffic, Muni waits, minutes to City Hall and gaps in the all-ages bike network.",
    path,
    body,
    sources: SOURCES,
    dataUpdated,
  });
}
