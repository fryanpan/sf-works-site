// Daily Trips: block by block, how long it takes to reach the nearest school,
// grocery store, library, park and commercial district on foot, by low-stress
// bike, by Muni or by car, and how often Muni comes nearby.
//
// Bryan's question, from his public comment: "Has
// anyone mapped out in other parts of the city how often does muni come? How
// far away is the nearest stop? How easy is it to get to commercial district,
// nearest park, major park, grocery store, school, library by transit,
// walking, biking or driving? Are the routes low stress enough?" His goals:
// daily trips under 30 minutes and ideally under 15, and kids able to travel
// alone on low-stress routes. So the map colours each block by those two
// lines, and the one figure beside it counts the residents within 15 minutes.
//
// Rulings that shape it (docs/decisions/access-map.md): "Muni every 5
// minutes" counts one route at a stop, not every route together (2026-10-23,
// "One route"); the faster T Third is a scenario beside the base map, never in
// place of it (2026-10-23, "Add it"), so it is a switch that starts off.
//
// Controls left, map middle, figures right, on one 1366×768 screen. Three
// controls: where to, how, and the T Third. The state is in the address
// (?to=&by=&t3=1). The block data is fetched (pages() below), and the opening
// figure is rendered here from the same file, so nothing moves when it lands.

import { page } from "../layout.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import { D, PLACES, MODES, MODE_PHRASE, PLACE_PHRASE, BANDS, BAND_COLOURS, DEFAULT, sig2, pct, within, SERVICE_DAY, SOURCES } from "../daily-trips.mjs";

export const path = "/daily-trips";
export const file = "daily-trips/index.html";
export const listing = { title: "Daily Trips", line: "How long it takes from every block to the nearest school, store, library and park, and how often Muni comes." };
const DATA_PATH = `${path}/blocks.json`;
const ABOUT = `${path}/about`;

// The city's extent, from the block outlines themselves.
function bounds() {
  let x = 0, y = 0, w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const d = D.outline.d;
  for (let k = 0; k < d.length; k += 2) {
    x += d[k]; y += d[k + 1];
    if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y;
  }
  return [[w / 1e5, s / 1e5], [e / 1e5, n / 1e5]];
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// The opening figure, the same sum the page script makes.
const n0 = within(DEFAULT.to, DEFAULT.by, false, 15);
const what0 = `live within 15 minutes of ${PLACE_PHRASE[DEFAULT.to]} ${MODE_PHRASE[DEFAULT.by]}.`;
const T3 = D.tthird_assumptions || {};
const t3Line = T3.end_to_end_min && T3.headway_min
  ? `Every ${T3.headway_min.value} minutes all day, Sunnydale to Chinatown in ${Math.round(T3.end_to_end_min.value)} minutes. Our assumption, not SFMTA's plan. Turn on Muni or walk to see it.`
  : "A faster T Third (assumed)";

const CSS = `<style>
.dt-head, .dt { width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); }
.dt-head h1 { font-size: clamp(1.3rem, 2.3vw, 1.6rem); margin: 0 0 2px; }
.dt-head .lede { margin: 0 0 10px; max-width: 120ch; font-size: 0.93rem; color: var(--ink); }
.dt { display: grid; grid-template-columns: 220px minmax(0, 1fr) 280px; gap: 16px; height: max(520px, calc(100dvh - 200px)); }
.dt h2 { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 5px; font-weight: 600; font-family: inherit; }
.dt-ctl { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.dt-opts { display: flex; flex-direction: column; gap: 3px; }
.dt-modes { display: flex; flex-direction: column; gap: 3px; }
.dt-opt { font: inherit; font-size: 0.86rem; text-align: left; border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 6px; padding: 4px 9px; cursor: pointer; line-height: 1.3; }
.dt-opt:hover:not(:disabled) { background: var(--raised); }
.dt-opt[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: #fff; font-weight: 600; }
.dt-opt:disabled { color: var(--grey-light); cursor: default; }
.dt-opt:focus-visible, .dt-t3 input:focus-visible { outline: 2px solid var(--seq-3); outline-offset: 2px; }
.dt-t3 { display: grid; grid-template-columns: auto 1fr; column-gap: 8px; align-items: start; font-size: 0.86rem; cursor: pointer; }
.dt-t3 input { margin: 3px 0 0; accent-color: var(--ink); }
.dt-t3 b { font-weight: 600; }
.dt-t3 small { grid-column: 2; display: block; color: var(--muted); font-size: 0.76rem; line-height: 1.3; }
.dt-t3.off { color: var(--grey-light); cursor: default; }
.dt-t3.off small { color: var(--grey-light); }
.dt-note { margin: 5px 0 0; font-size: 0.76rem; color: var(--muted); min-height: 2.6em; line-height: 1.3; }
.dt-map { min-height: 0; height: 100%; }
.dt-out { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.dt-stat .big { display: block; font-family: Archivo, sans-serif; font-weight: 700; font-size: 2.3rem; line-height: 1; font-variant-numeric: tabular-nums; }
.dt-stat .pct { display: block; font-size: 0.9rem; color: var(--muted); margin: 3px 0 4px; }
.dt-stat .what { display: block; font-size: 0.92rem; line-height: 1.35; min-height: 3.8em; }
.dt-goal { margin: 0 0 4px; font-size: 0.8rem; font-weight: 600; }
.dt-key { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; font-size: 0.84rem; }
.dt-key li { display: flex; align-items: center; gap: 7px; }
.dt-key i { width: 16px; height: 12px; border-radius: 2px; flex: none; }
.dt-key .t3 i { background: transparent; border: 2px solid var(--ink); }
.dt-key .t3.hide { visibility: hidden; }
.dt-block { border-top: 1px solid var(--rule); padding-top: 8px; font-size: 0.84rem; min-height: 0; overflow: auto; }
.dt-block .hint { color: var(--muted); margin: 0; }
.dt-block .who { margin: 0 0 4px; }
.dt-block table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
.dt-block td { padding: 1px 0; border: 0; line-height: 1.3; font-size: 0.84rem; }
.dt-block td + td { text-align: right; white-space: nowrap; }
.dt-block tr.on td { font-weight: 700; }
.dt-block .dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-left: 6px; }
.dt-block tr.gap td { padding-top: 6px; }
.dt-asof { margin: auto 0 0; font-size: 0.74rem; color: var(--muted); line-height: 1.35; }
@media (max-width: 760px) {
  .dt-head .lede { font-size: 0.86rem; margin-bottom: 8px; }
  .dt { grid-template-columns: minmax(0, 1fr); height: auto; gap: 10px; }
  .dt-ctl { gap: 8px; }
  .dt h2 { display: none; }
  .dt-places { flex-direction: row; }
  .dt-places .dt-opt { white-space: nowrap; flex: none; }
  .dt-modes { display: grid; grid-template-columns: repeat(4, auto); }
  .dt-modes .dt-opt { text-align: center; padding: 4px 4px; font-size: 0.8rem; }
  .dt-note { min-height: 1.3em; margin-top: 3px; }
  .dt-places { flex-wrap: wrap; gap: 4px; }
  .dt-places .dt-opt, .dt-modes .dt-opt { font-size: 0.78rem; padding: 3px 7px; }
  .dt-map { height: 36vh; }
  .dt-t3 small { display: none; }
  .dt-key { flex-direction: row; flex-wrap: wrap; gap: 2px 12px; font-size: 0.78rem; }
  .dt-stat .pct { margin: 2px 0; }
  .dt-stat .what { min-height: 0; }
  .dt-out { gap: 10px; }
  .dt-stat .big { font-size: 1.9rem; }
}
</style>`;

const placeBtn = ([k, l]) => `<button type="button" class="dt-opt" data-to="${k}" aria-pressed="${k === DEFAULT.to}">${esc(l)}</button>`;
const modeBtn = ([k, l]) => `<button type="button" class="dt-opt" data-by="${k}" aria-pressed="${k === DEFAULT.by}">${esc(l)}</button>`;
const key = BANDS.time.map((l, i) => `<li><i style="background:var(${BAND_COLOURS[i]})"></i><span data-band="${i}">${l}</span></li>`).join("");

const CONFIG = {
  places: PLACES, modes: MODES, modePhrase: MODE_PHRASE, placePhrase: PLACE_PHRASE, bands: BANDS, colours: BAND_COLOURS,
  def: DEFAULT, residents: D.residents, bounds: bounds(),
};

const SCRIPT = `<script type="application/json" id="dt-config">${inlineJson(CONFIG)}</script>
<script>
(function () {
  var C = JSON.parse(document.getElementById("dt-config").textContent);
  var root = document.querySelector("[data-dt]"), el = document.getElementById("dt-map");
  var $ = function (s) { return root.querySelector(s); }, $$ = function (s) { return Array.prototype.slice.call(root.querySelectorAll(s)); };
  var LABEL = {}; C.places.forEach(function (p) { LABEL[p[0]] = p[1]; });
  var S = { to: C.def.to, by: C.def.by, t3: C.def.t3, sel: null };
  (function fromUrl() {
    var q = new URLSearchParams(location.search);
    if (LABEL[q.get("to")]) S.to = q.get("to");
    if (C.modes.some(function (m) { return m[0] === q.get("by"); })) S.by = q.get("by");
    S.t3 = q.get("t3") === "1";
  })();
  var D = null, map = null, feats = null;
  var NOTE = { walk: "At 2 mph, from the edge of the block.", bike: "Rides paths, protected lanes and Slow Streets, and walks the bike on other streets.",
    transit: "Muni with the walk and the wait, or walking if that's faster.", car: "Includes 3 minutes to park and walk in.",
    muni: "Frequent Muni is about the stop near home, so there's no way of travel to pick." };
  // On a laptop the three columns fill the screen below the title, set once so nothing moves later.
  if (window.matchMedia("(min-width: 761px)").matches) {
    var top = root.getBoundingClientRect().top + window.scrollY;
    root.style.height = Math.max(520, window.innerHeight - top - 10) + "px";
  }
  function sig2(n) { if (!n) return "0"; var p = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.abs(n))) - 1)); return (Math.round(n / p) * p).toLocaleString("en-US"); }
  function pct(n) { var v = 100 * n / C.residents; return v >= 99.5 && n < C.residents ? ">99%" : v < 1 && n > 0 ? "<1%" : Math.round(v) + "%"; }
  function t3On() { return S.t3 && S.by === "transit" && S.to !== "muni" && D && D.tthird; }
  function vals(to, t3) { return S.by === "transit" && t3 ? D.tthird[to] : D.min[to][S.by]; }
  function band(i) {
    if (S.to === "muni") { var c = D.muni[i]; return c === 5 ? 0 : c === 10 ? 1 : 2; }
    var v = vals(S.to, t3On())[i];
    return v != null && v <= 15 ? 0 : v != null && v <= 30 ? 1 : 2;
  }
  function count(t3) {
    var n = 0, i;
    if (S.to === "muni") { for (i = 0; i < D.pop.length; i++) if (D.muni[i] === 5) n += D.pop[i]; return n; }
    var v = vals(S.to, t3);
    for (i = 0; i < D.pop.length; i++) if (v[i] != null && v[i] <= 15) n += D.pop[i];
    return n;
  }
  function ft(f) {
    if (f == null) return "over 3 miles";
    if (f < 5280) return (f < 100 ? Math.round(f / 10) * 10 || 10 : Math.round(f / 50) * 50).toLocaleString("en-US") + " ft";
    var m = f / 5280; return (m >= 10 ? Math.round(m) : m.toPrecision(2)) + " mi";
  }
  function mins(v, by) {
    if (v != null) return v + " min";
    return by === "bike" ? "over 30 min" : by === "transit" ? "over 60 min" : "no route";
  }
  function setUrl() {
    var q = new URLSearchParams();
    if (S.to !== C.def.to) q.set("to", S.to);
    if (S.by !== C.def.by) q.set("by", S.by);
    if (S.t3) q.set("t3", "1");
    var s = q.toString() ? "?" + q.toString() : "";
    history.replaceState(null, "", location.pathname + s + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: s }));
  }
  function controls() {
    var muni = S.to === "muni";
    $$("[data-to]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.to === S.to)); });
    $$("[data-by]").forEach(function (b) { b.setAttribute("aria-pressed", String(!muni && b.dataset.by === S.by)); b.disabled = muni; });
    var can = !muni && S.by === "transit" && (!D || !!D.tthird), box = $("[data-t3]");
    box.disabled = !can; box.checked = S.t3 && can;
    $(".dt-t3").classList.toggle("off", !can);
    $(".dt-t3").title = can ? "" : "Works with Muni or walk";
    $("[data-note]").textContent = NOTE[muni ? "muni" : S.by];
    $("[data-asof]").style.visibility = can ? "visible" : "hidden";
  }
  function figures() {
    var muni = S.to === "muni";
    $$("[data-band]").forEach(function (s) { s.textContent = C.bands[muni ? "muni" : S.by === "car" ? "car" : "time"][+s.dataset.band]; });
    $(".dt-key .t3").classList.toggle("hide", !t3On());
    $("[data-goal]").textContent = muni ? "Our goal for Muni" : S.by === "car" ? "Driving isn't part of the goal" : "Our goal for a daily trip";
    if (!D) {
      // Before the data lands, a view other than the opening one has no figure yet.
      if (S.to !== C.def.to || S.by !== C.def.by || S.t3) { $("[data-big]").textContent = "\u2026"; $("[data-pct]").textContent = "Loading"; }
      return;
    }
    if (t3On()) {
      var fast = 0, a = D.tthird[S.to], b0 = D.min[S.to].transit;
      for (var j = 0; j < D.pop.length; j++) if (a[j] != null && (b0[j] == null || a[j] < b0[j])) fast += D.pop[j];
      $("[data-t3-key]").textContent = "Faster with the T Third: " + sig2(fast) + " residents";
    }
    var n = count(t3On());
    $("[data-big]").textContent = sig2(n);
    $("[data-pct]").textContent = pct(n) + " of residents";
    $("[data-what]").textContent = muni
      ? "live within a quarter mile of a stop where one Muni line leaves at least 24 times from 7 to 9 AM, every 5 minutes."
      : "live within 15 minutes of " + C.placePhrase[S.to] + " " + C.modePhrase[S.by] + (t3On() ? ", with a faster T Third." : ".");
  }
  function card() {
    var box = $("[data-block]");
    if (S.sel == null || !D) { box.innerHTML = '<p class="hint">Pick a block on the map to see its times to every place.</p>'; return; }
    var i = S.sel, t3 = t3On(), by = S.by;
    var rows = C.places.filter(function (p) { return p[0] !== "muni"; }).map(function (p) {
      var v = (by === "transit" && t3 ? D.tthird[p[0]] : D.min[p[0]][by])[i];
      var k = v != null && v <= 15 ? 0 : v != null && v <= 30 ? 1 : 2;
      var dot = by === "car" ? "" : '<i class="dot" style="background:var(' + C.colours[k] + ')"></i>';
      return '<tr class="' + (p[0] === S.to ? "on" : "") + '"><td>' + p[1] + "</td><td>" + mins(v, by) + dot + "</td></tr>";
    }).join("");
    box.innerHTML = '<p class="who"><b>' + D.pop[i].toLocaleString("en-US") + (D.pop[i] === 1 ? " resident</b> lives" : " residents</b> live") + " on this block. Trips from here:</p>"
      + "<table><tbody>" + rows
      + '<tr class="gap' + (S.to === "muni" ? " on" : "") + '"><td>Nearest stop with Muni every 5 min</td><td>' + ft(D.stop[i][1]) + "</td></tr>"
      + "<tr><td>Nearest Muni stop</td><td>" + ft(D.stop[i][0]) + "</td></tr>"
      + "</tbody></table>";
  }
  function paint() {
    if (!map || !feats) return;
    var t3 = t3On(), base = t3 ? D.min[S.to].transit : null, alt = t3 ? D.tthird[S.to] : null;
    for (var i = 0; i < feats.length; i++) {
      var p = feats[i].properties;
      p.b = band(i);
      p.f = t3 && alt[i] != null && (base[i] == null || alt[i] < base[i]) ? 1 : 0;
    }
    var src = map.getSource("dt"), key = S.to + S.by + t3;
    if (src && key !== paint.key) { src.setData(sfMap.collection(feats)); paint.key = key; }
    if (map.getLayer("dt-sel")) map.setFilter("dt-sel", ["==", ["get", "i"], S.sel == null ? -1 : S.sel]);
  }
  function render() { controls(); figures(); card(); paint(); setUrl(); }

  root.addEventListener("click", function (e) {
    var b = e.target.closest("[data-to], [data-by]");
    if (!b || b.disabled) return;
    if (b.dataset.to) S.to = b.dataset.to; else S.by = b.dataset.by;
    render();
  });
  $("[data-t3]").addEventListener("change", function (e) { S.t3 = e.target.checked; render(); });
  render();

  // Each block as one feature: its rings decoded from the shared offsets, grouped into polygons.
  function build(d) {
    var runs = sfMap.decode({ n: d.outline.n, d: d.outline.d }), k = 0, out = [];
    for (var i = 0; i < d.pop.length; i++) {
      var polys = d.outline.shape[i].map(function (rings) { var p = runs.slice(k, k + rings); k += rings; return p; });
      out.push({ type: "Feature", properties: { i: i, b: 2, f: 0 }, geometry: { type: "MultiPolygon", coordinates: polys } });
    }
    return out;
  }
  map = sfMap.create(el, { bounds: C.bounds, padding: function () { return 10; }, maxZoom: 17, onReset: function () { S.sel = null; render(); } });
  var dataP = fetch(root.dataset.src).then(function (r) { if (!r.ok) throw new Error("blocks.json " + r.status); return r.json(); });
  dataP.then(function (d) { D = d; feats = build(d); render(); }).catch(function (e) {
    if (window.console) console.warn("daily trips:", e && e.message);
    $("[data-block]").innerHTML = '<p class="hint">The block data did not load. Reload the page to try again.</p>';
  });
  if (!map) return;
  map.on("load", function () {
    dataP.then(function () {
      var before = sfMap.under(map), col = function (i) { return sfMap.token(C.colours[i]); };
      map.addSource("dt", { type: "geojson", data: sfMap.collection(feats) });
      map.addLayer({ id: "dt-fill", type: "fill", source: "dt", paint: {
        "fill-color": ["match", ["get", "b"], 0, col(0), 1, col(1), col(2)],
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.72, 15, 0.5] } }, before);
      map.addLayer({ id: "dt-edge", type: "line", source: "dt", minzoom: 13, paint: { "line-color": "#ffffff", "line-width": 0.6, "line-opacity": 0.8 } }, before);
      map.addLayer({ id: "dt-t3", type: "line", source: "dt", filter: ["==", ["get", "f"], 1], paint: { "line-color": sfMap.token("--ink"), "line-width": 2 } }, before);
      map.addLayer({ id: "dt-sel", type: "line", source: "dt", filter: ["==", ["get", "i"], -1], paint: { "line-color": sfMap.token("--ink"), "line-width": 3 } }, before);
      paint();
      map.on("click", "dt-fill", function (e) { var f = e.features && e.features[0]; if (!f) return; S.sel = f.properties.i; render();
        if (window.matchMedia("(max-width: 760px)").matches) $("[data-block]").scrollIntoView({ behavior: "smooth", block: "nearest" }); });
      map.on("mouseenter", "dt-fill", function () { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "dt-fill", function () { map.getCanvas().style.cursor = ""; });
    }).catch(function () {});
  });
})();
</script>`;

export function pages() {
  return [{ path: DATA_PATH, file: DATA_PATH.slice(1), html: Buffer.from(JSON.stringify(D)), sitemap: false }];
}

export function render() {
  const body = `${CSS}
<div class="dt-head">
  <h1>Daily Trips, Block by Block</h1>
  <p class="lede">Pick a place and a way to get there to see how long the trip takes from every San Francisco block.</p>
</div>
<div class="dt" data-dt data-src="${DATA_PATH}">
  <div class="dt-ctl">
    <div><h2>Going to</h2><div class="dt-opts dt-places">${PLACES.map(placeBtn).join("")}</div></div>
    <div><h2>Traveling by</h2><div class="dt-modes">${MODES.map(modeBtn).join("")}</div><p class="dt-note" data-note>Rides paths, protected lanes and Slow Streets, and walks the bike on other streets.</p></div>
    <div>
      <label class="dt-t3 off" title="Works with Muni or walk"><input type="checkbox" data-t3 disabled><b>Faster T Third</b><small>${esc(t3Line)}</small></label>
    </div>
  </div>
  <div class="dt-map glmap" id="dt-map" role="region" aria-label="Map of San Francisco blocks colored by travel time"></div>
  <div class="dt-out">
    <div class="dt-stat" aria-live="polite">
      <span class="big" data-big>${sig2(n0)}</span>
      <span class="pct" data-pct>${pct(n0, D.residents)} of residents</span>
      <span class="what" data-what>${esc(what0)}</span>
    </div>
    <div><p class="dt-goal" data-goal>Our goal for a daily trip</p><ul class="dt-key">${key}<li class="t3 hide"><i></i><span data-t3-key>Faster with the T Third</span></li></ul></div>
    <div class="dt-block" data-block><p class="hint">Pick a block on the map to see its times to every place.</p></div>
    <p class="dt-asof"><span data-asof>Muni times are for trips leaving 8 to 9 AM on ${SERVICE_DAY}.</span> <a href="${ABOUT}">How we measured</a></p>
  </div>
</div>
${MAP_HEAD}
${SCRIPT}`;
  return page({
    title: "Daily Trips",
    description: "How long it takes from every San Francisco block to the nearest school, grocery store, library, park or commercial district, and how often Muni comes nearby.",
    path,
    body,
    sources: SOURCES,
  });
}
