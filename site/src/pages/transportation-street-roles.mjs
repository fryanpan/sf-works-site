// Street Roles Map: every San Francisco street gets one job (through traffic, local trips, bikes or people on
// foot), its bike traffic stress today and with those roles and the Biking and Rolling Plan network built, and one
// stat row: SF residents' short commutes connected on streets most adults will bike, today and with the network.
//
// Bryan, approving v0 on 2026-11-27: "v0 is a citywide map of roles and LTS, plus one stat row: short commute
// trips connected at LTS 2 today and with the network." And by voice: "Build both and let me edit which streets
// get picked for local vs through traffic. Ideally don't pick BRP network segments for through traffic unless
// there's a separated bikeway in the plans." So a tap on a street opens its card with its role, the rule's reason
// and buttons to make it through or local; the change recounts the stat row in the browser with the same rules
// tools/street-roles/street-roles.py builds the defaults with (site/src/street-roles.mjs, model()). Changes live
// in the address (?t=&l=&b=, CNNs in base 36) and in localStorage, and one Reset Roles button clears them.
//
// Not listed in the site's directory (no `listing` export): the tool's name isn't settled.
//
// Controls left, map middle, figures right, on one 1366x768 screen (tool UX rule 6). A card about the tapped
// street sits beside it on the map, never over it (rule 21), and under the map on a phone.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import { SUMMARY, STREETS_FILE, COMMUTES_FILE, ROLE_COLOURS, ROLE_LABELS, ROLE_LINES, STRESS_BANDS, SOURCES, sig2, MODEL_SRC } from "../street-roles.mjs";

export const path = "/transportation/street-roles";
export const file = "transportation/street-roles/index.html";
const ABOUT = `${path}/about`;
const STREETS_PATH = `${path}/streets.json`;
const COMMUTES_PATH = `${path}/commutes.json`;
const ROOT = nodePath.resolve(import.meta.dirname, "..", "..", "..");

export const dataUpdated = SUMMARY.data_read;

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const pct = (n, d) => `${Math.round((100 * n) / d)}%`;
const S0 = SUMMARY;
const VIEWS = [["roles", "Street roles"], ["today", "How bikeable today"], ["network", "How bikeable with the network"]];

const CSS = `<style>
.sr-head, .sr { width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); }
.sr-head h1 { font-size: clamp(1.3rem, 2.3vw, 1.6rem); margin: 0 0 2px; }
.sr-head .data-updated { margin: 0 0 2px; }
.sr-head .lede { margin: 0 0 10px; max-width: 120ch; font-size: 0.93rem; }
.sr { display: grid; grid-template-columns: 210px minmax(0, 1fr) 280px; gap: 16px; height: max(520px, calc(100dvh - 200px)); }
.sr h2 { font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 5px; font-weight: 600; font-family: inherit; }
.sr-ctl { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.sr-views { display: flex; flex-direction: column; gap: 3px; }
.sr-opt { font: inherit; font-size: 0.86rem; text-align: left; border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 6px; padding: 4px 9px; cursor: pointer; line-height: 1.3; }
.sr-opt:hover:not(:disabled) { background: var(--raised); }
.sr-opt[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: #fff; font-weight: 600; }
.sr-opt:disabled { color: var(--grey-light); cursor: default; }
.sr-opt:focus-visible { outline: 2px solid var(--seq-3); outline-offset: 2px; }
.sr-edits p { margin: 0 0 6px; font-size: 0.84rem; line-height: 1.35; min-height: 2.7em; }
.sr-stage { position: relative; min-height: 0; height: 100%; }
.sr-map { height: 100%; }
.sr-out { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.sr-q { margin: 0; font-size: 0.92rem; font-weight: 600; line-height: 1.3; }
.sr-stats { display: grid; grid-template-columns: 1fr; gap: 6px; }
.sr-stat { border: 1px solid var(--rule); border-radius: 8px; padding: 6px 10px 7px; }
.sr-stat.lead { border-color: var(--ink); }
.sr-stat .when { display: block; font-size: 0.76rem; color: var(--muted); }
.sr-stat .big { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.9rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.sr-stat[data-card=today] .big { font-size: 1.3rem; }
.sr-stat .pct { margin-left: 6px; }
.sr-stat .pct { font-size: 0.84rem; color: var(--muted); }
.sr-def { margin: 0; font-size: 0.8rem; line-height: 1.4; color: var(--muted); }
.sr-key { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; font-size: 0.84rem; }
.sr-key li { display: flex; align-items: center; gap: 7px; }
.sr-key i { width: 18px; height: 4px; border-radius: 2px; flex: none; }
.sr-key li.mine i { height: 8px; background: transparent; border: 2px solid var(--ink); border-radius: 3px; }
.sr-asof { margin: auto 0 0; font-size: 0.76rem; color: var(--muted); line-height: 1.35; }
.sr-card { position: absolute; z-index: 2; width: 270px; background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.15); padding: 9px 12px 10px; font-size: 0.83rem; line-height: 1.4; }
.sr-card h3 { font-size: 0.95rem; margin: 0 22px 2px 0; }
.sr-card p { margin: 0 0 6px; }
.sr-card .sr-x { position: absolute; top: 4px; right: 6px; border: 0; background: none; font-size: 1.1rem; line-height: 1; cursor: pointer; color: var(--muted); padding: 2px 4px; }
.sr-card .sr-why { color: var(--muted); }
.sr-card .sr-pick { display: flex; gap: 4px; margin-top: 4px; }
.sr-card .sr-pick .sr-opt { flex: 1; text-align: center; padding: 4px 6px; }
.sr-stat.busy .big, .sr-stat.busy .pct { opacity: 0.35; }
@media (max-width: 760px) {
  .sr-head .lede { font-size: 0.86rem; margin-bottom: 8px; }
  .sr { grid-template-columns: minmax(0, 1fr); height: auto; gap: 10px; }
  .sr-ctl { gap: 8px; }
  .sr-ctl h2 { display: none; }
  .sr-views { flex-direction: row; flex-wrap: wrap; gap: 4px; }
  .sr-views .sr-opt { font-size: 0.78rem; padding: 3px 7px; }
  .sr-edits { display: flex; align-items: center; gap: 8px; }
  .sr-edits p { margin: 0; min-height: 0; font-size: 0.78rem; flex: 1; }
  .sr-stage { height: 46vh; order: 3; }
  .sr-ctl { order: 1; }
  .sr-out { order: 2; gap: 6px; }
  .sr-asof { display: none; }
  .sr-card { position: static; width: auto; box-shadow: none; margin-top: 8px; }
  .sr-key { flex-direction: row; flex-wrap: wrap; gap: 2px 12px; font-size: 0.78rem; }
  .sr-stat .big { font-size: 1.5rem; }
}
</style>`;

const viewBtn = ([k, l]) => `<button type="button" class="sr-opt" data-view="${k}" aria-pressed="${k === "roles"}">${esc(l)}</button>`;
const roleKey = Object.keys(ROLE_LABELS).map((r) => `<li><i style="background:${ROLE_COLOURS[r]}"></i>${ROLE_LABELS[r]}</li>`).join("");

const CONFIG = {
  colours: ROLE_COLOURS, labels: ROLE_LABELS, bands: STRESS_BANDS, total: S0.commuters_in_window,
  today: S0.connected_today, network: S0.connected_network, views: VIEWS.map((v) => v[0]),
};

const SCRIPT = `<script type="application/json" id="sr-config">${inlineJson(CONFIG)}</script>
<script>
(function () {
  var C = JSON.parse(document.getElementById("sr-config").textContent);
  var M = ${MODEL_SRC};
  var root = document.querySelector("[data-sr]"), el = document.getElementById("sr-map"), stage = root.querySelector(".sr-stage");
  var card = root.querySelector(".sr-card"), narrow = window.matchMedia("(max-width: 760px)");
  var $ = function (s) { return root.querySelector(s); }, $$ = function (s) { return Array.prototype.slice.call(root.querySelectorAll(s)); };
  var KEY = "sfworks.street-roles.edits";
  var S = null, Cm = null, map = null, runs = null, nodeBlocks = null, net = null, count = C.network, sel = [];
  var st = { view: "roles", edits: {} };
  if (!narrow.matches) {
    var top = root.getBoundingClientRect().top + window.scrollY;
    root.style.height = Math.max(520, window.innerHeight - top - 10) + "px";
  }
  function sig2(n) { if (!n) return "0"; var p = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.abs(n))) - 1)); return (Math.round(n / p) * p).toLocaleString("en-US"); }
  function pct(n) { return Math.round(100 * n / C.total) + "%"; }
  // "19TH ST" as "19th St", "MARTIN LUTHER KING JR DR" as "Martin Luther King Jr Dr".
  function title(s) { return String(s || "").toLowerCase().replace(/(^|[ \\-\\/(])([a-z])/g, function (m, a, b) { return a + b.toUpperCase(); }); }
  function h(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
  // ---- state: the view and the changed blocks, in the address and in localStorage ----
  var ROLE_Q = { t: "through", l: "local", b: "bike" };
  function parseEdits(q) {
    var e = {};
    Object.keys(ROLE_Q).forEach(function (k) {
      (q.get(k) || "").split(".").forEach(function (s) { if (s) e[parseInt(s, 36)] = ROLE_Q[k]; });
    });
    return e;
  }
  function editQuery() {
    var q = new URLSearchParams();
    Object.keys(ROLE_Q).forEach(function (k) {
      var ids = Object.keys(st.edits).filter(function (c) { return st.edits[c] === ROLE_Q[k]; }).map(Number).sort(function (a, b) { return a - b; });
      if (ids.length) q.set(k, ids.map(function (c) { return c.toString(36); }).join("."));
    });
    return q;
  }
  (function fromUrl() {
    var q = new URLSearchParams(location.search);
    if (C.views.indexOf(q.get("view")) >= 0) st.view = q.get("view");
    var e = parseEdits(q);
    if (!Object.keys(e).length) { try { e = parseEdits(new URLSearchParams(localStorage.getItem(KEY) || "")); } catch (x) { e = {}; } }
    st.edits = e;
  })();
  function setUrl() {
    var q = editQuery(), s = q.toString();
    try { if (s) localStorage.setItem(KEY, s); else localStorage.removeItem(KEY); } catch (x) {}
    if (st.view !== "roles") q.set("view", st.view);
    s = q.toString() ? "?" + q.toString() : "";
    history.replaceState(null, "", location.pathname + s + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: s }));
  }
  // ---- the model ----
  var cnnIx = null;
  function roleOf(i) { var e = st.edits[S.blocks.cnn[i]]; return e || S.roles[S.blocks.role[i]]; }
  function band(s) { return s === null ? -1 : s <= 2 ? 0 : s === 3 ? 1 : 2; }
  function stressNow(i) { return M.stress(roleOf(i), S.blocks, i); }
  function recount() {
    var B = S.blocks;
    net = B.cnn.map(function (_, i) { return stressNow(i); });
    $("[data-card=network]").classList.add("busy");
    setTimeout(function () {
      count = M.connected(S, Cm, function (i) { return net[i]; })[0];
      $("[data-card=network]").classList.remove("busy");
      figures(); controls();
    }, 20);
  }
  // ---- the page around the map ----
  function controls() {
    $$("[data-view]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.view === st.view)); });
    var n = Object.keys(st.edits).length;
    $("[data-reset]").disabled = !n;
    var d = count - C.network;
    $("[data-edits]").textContent = !n ? "Tap a street to change its role." : !S ? "Loading your changes."
      : d === 0 ? "Your changes leave the count as it was. Those streets rate the same, or no short commute depends on them."
      : "Your changes: " + (d > 0 ? sig2(d) + " more" : sig2(-d) + " fewer") + " commutes connected.";
    $$("[data-card]").forEach(function (c) { c.classList.toggle("lead", c.dataset.card === (st.view === "today" ? "today" : "network")); });
    var mine = n ? '<li class="mine"><i></i>Changed by you</li>' : "";
    $("[data-key]").innerHTML = st.view === "roles" ? ${JSON.stringify(roleKey)} + mine
      : C.bands.map(function (b) { return '<li><i style="background:' + sfMapToken(b[2]) + '"></i>' + h(b[1]) + "</li>"; }).join("") + '<li><i style="background:#c9cdd2"></i>Pedestrian street, not ridden</li>' + mine;
  }
  function sfMapToken(t) { return window.sfMap ? sfMap.token(t) : "var(" + t + ")"; }
  function figures() {
    $("[data-net]").textContent = sig2(count);
    $("[data-net-pct]").textContent = pct(count);
  }
  // ---- the map ----
  function features() {
    var B = S.blocks;
    return runs.map(function (r, i) {
      return { type: "Feature", id: i, properties: { i: i, r: S.roles.indexOf(roleOf(i)), s0: band(S.roles[B.role[i]] === "walk" ? null : B.today[i]), s1: band(net[i]), e: st.edits[B.cnn[i]] ? 1 : 0 },
        geometry: { type: "LineString", coordinates: r } };
    });
  }
  function paint() {
    if (!map || !map.getSource("sr")) return;
    map.getSource("sr").setData(sfMap.collection(features()));
    var col;
    if (st.view === "roles") col = ["match", ["get", "r"], 0, C.colours.through, 1, C.colours.local, 2, C.colours.bike, C.colours.walk];
    else col = ["match", ["get", st.view === "today" ? "s0" : "s1"], 0, sfMap.token("--seq-3"), 1, sfMap.token("--seq-2"), 2, sfMap.token("--seq-1"), "#c9cdd2"];
    map.setPaintProperty("sr-line", "line-color", col);
    map.setLayoutProperty("sr-mine", "visibility", st.view === "roles" ? "visible" : "none");
    light();
  }
  function light() {
    if (!map || !map.getSource("sr-sel")) return;
    map.getSource("sr-sel").setData(sfMap.collection(sel.map(function (i) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: runs[i] } }; })));
  }
  // A street's stretch: the blocks of the same name and role joined end to end with the tapped one.
  function stretch(i) {
    var B = S.blocks, name = B.name[i], role = roleOf(i), seen = {}, out = [], todo = [i];
    seen[i] = 1;
    while (todo.length) {
      var j = todo.pop(); out.push(j);
      [B.a[j], B.b[j]].forEach(function (n) { nodeBlocks[n].forEach(function (k) {
        if (!seen[k] && B.name[k] === name && roleOf(k) === role) { seen[k] = 1; todo.push(k); }
      }); });
    }
    return out;
  }
  function say() {
    var B = S.blocks, i = sel[0], role = roleOf(i), def = S.roles[B.role[i]], ft = 0;
    sel.forEach(function (j) { ft += B.ft[j]; });
    var len = ft < 1000 ? Math.round(ft / 10) * 10 + " ft" : (ft / 5280).toFixed(ft < 52800 ? 1 : 0) + " mi";
    var changed = !!st.edits[B.cnn[i]];
    var why = changed ? "You changed this street. Our default is " + C.labels[def].toLowerCase() + ": " + S.rules[B.why[i]].charAt(0).toLowerCase() + S.rules[B.why[i]].slice(1)
      : S.rules[B.why[i]];
    var plan = sel.some(function (j) { return B.plan[j]; });
    var picks = ["through", "local"].concat(plan ? ["bike"] : []);
    var html = '<button type="button" class="sr-x" aria-label="Close">\\u00d7</button><h3>' + h(title(B.name[i]) || "Unnamed street") + "</h3>"
      + "<p>" + len + ". <span class=\\"sr-why\\">" + h(why) + "</span></p>";
    if (def !== "walk") html += '<div class="sr-pick" role="group" aria-label="Role for this street">' + picks.map(function (r) {
      return '<button type="button" class="sr-opt" data-role="' + r + '" aria-pressed="' + (r === role) + '">' + C.labels[r] + "</button>";
    }).join("") + "</div>";
    card.innerHTML = html;
  }
  function boxOf(ids) {
    var b = sfMap.screenBox(map, ids.map(function (i) { return runs[i]; }));
    var sr = stage.getBoundingClientRect(), gr = el.getBoundingClientRect();
    return { l: b.l + gr.left - sr.left, r: b.r + gr.left - sr.left, t: b.t + gr.top - sr.top, b: b.b + gr.top - sr.top };
  }
  // The card goes on whichever side of the street has room, so it never covers it. On a phone it sits under the map.
  function place() {
    if (narrow.matches || card.hidden) { card.style.left = card.style.top = ""; return; }
    var sr = stage.getBoundingClientRect(), W = sr.width, H = el.offsetHeight, gap = 12;
    var cw = card.offsetWidth, ch = card.offsetHeight, bx = boxOf(sel);
    var room = { right: W - bx.r - gap, left: bx.l - gap, below: H - bx.b - gap, above: bx.t - gap };
    var order = ["right", "left", "below", "above"];
    var side = order.filter(function (k) { return room[k] >= (k === "right" || k === "left" ? cw : ch); })[0]
      || order.sort(function (a, z) { return room[z] / (z === "right" || z === "left" ? cw : ch) - room[a] / (a === "right" || a === "left" ? cw : ch); })[0];
    var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(v, hi)); };
    var cy = (bx.t + bx.b) / 2, cx = (bx.l + bx.r) / 2, left, top;
    if (side === "right") { left = bx.r + gap; top = cy - ch / 2; }
    else if (side === "left") { left = bx.l - gap - cw; top = cy - ch / 2; }
    else if (side === "below") { top = bx.b + gap; left = cx - cw / 2; }
    else { top = bx.t - gap - ch; left = cx - cw / 2; }
    card.style.left = clamp(left, 8, Math.max(8, W - cw - 8)) + "px";
    card.style.top = clamp(top, 8, Math.max(8, H - ch - 8)) + "px";
  }
  function pick(i) {
    if (i === null) { sel = []; card.hidden = true; light(); return; }
    sel = stretch(i); say(); card.hidden = false; light(); place();
    if (narrow.matches) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function setRole(r) {
    var B = S.blocks;
    sel.forEach(function (j) { var c = B.cnn[j]; if (S.roles[B.role[j]] === r) delete st.edits[c]; else st.edits[c] = r; });
    recount(); controls(); paint(); say(); place(); setUrl();
  }
  root.addEventListener("click", function (e) {
    var v = e.target.closest("[data-view]");
    if (v) { st.view = v.dataset.view; controls(); paint(); setUrl(); return; }
    var r = e.target.closest("[data-role]");
    if (r && S) { setRole(r.dataset.role); return; }
    if (e.target.closest(".sr-x")) { pick(null); return; }
    if (e.target.closest("[data-reset]") && S) { st.edits = {}; recount(); controls(); paint(); if (sel.length) pick(sel[0]); setUrl(); }
  });
  controls(); setUrl();

  var load = function (p) { return fetch(p).then(function (r) { if (!r.ok) throw new Error(p + " " + r.status); return r.json(); }); };
  var dataP = Promise.all([load(root.dataset.streets), load(root.dataset.commutes)]).then(function (d) {
    S = d[0]; Cm = d[1];
    runs = sfMap.decode(S.lines);
    var B = S.blocks;
    nodeBlocks = []; for (var n = 0; n < S.nodes; n++) nodeBlocks.push([]);
    for (var i = 0; i < B.cnn.length; i++) { nodeBlocks[B.a[i]].push(i); nodeBlocks[B.b[i]].push(i); }
    net = B.cnn.map(function (_, i) { return stressNow(i); });
    if (Object.keys(st.edits).length) recount();
    controls();
  });
  dataP.catch(function (e) { if (window.console) console.warn("street roles:", e && e.message); $("[data-edits]").textContent = "The street data did not load. Reload the page to try again."; });
  map = sfMap.create(el, { bounds: [[-122.515, 37.708], [-122.357, 37.812]], padding: function () { return 8; }, maxZoom: 18, onReset: function () { pick(null); } });
  if (!map) return;
  map.on("load", function () {
    dataP.then(function () {
      var before = sfMap.under(map);
      map.addSource("sr", { type: "geojson", data: sfMap.collection(features()) });
      map.addSource("sr-sel", { type: "geojson", data: sfMap.collection([]) });
      var w = ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0.8, 14, 2.4, 17, 6];
      map.addLayer({ id: "sr-selline", type: "line", source: "sr-sel", layout: { "line-cap": "butt", "line-join": "round" }, paint: { "line-color": sfMap.token("--ink"), "line-opacity": 0.2, "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 7, 14, 12, 17, 18] } }, before);
      map.addLayer({ id: "sr-mine", type: "line", source: "sr", filter: ["==", ["get", "e"], 1], layout: { "line-cap": "round" }, paint: { "line-color": sfMap.token("--ink"), "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 3, 14, 5.5, 17, 10] } }, before);
      map.addLayer({ id: "sr-line", type: "line", source: "sr", layout: { "line-cap": "round" }, paint: { "line-color": C.colours.local, "line-width": w } }, before);
      map.addLayer({ id: "sr-hit", type: "line", source: "sr", paint: { "line-color": "#000", "line-opacity": 0, "line-width": 14 } });
      paint();
      map.on("click", function (e) {
        var f = sfMap.near(map, e.point, ["sr-hit"])[0];
        pick(f ? f.properties.i : null);
      });
      map.on("mousemove", function (e) { map.getCanvas().style.cursor = sfMap.near(map, e.point, ["sr-hit"]).length ? "pointer" : ""; });
      map.on("move", function () { if (sel.length && !card.hidden) place(); });
    }).catch(function () {});
  });
})();
</script>`;

export function pages() {
  const raw = (f) => fs.readFileSync(nodePath.join(ROOT, f));
  return [
    { path: STREETS_PATH, file: STREETS_PATH.slice(1), html: raw(STREETS_FILE), sitemap: false },
    { path: COMMUTES_PATH, file: COMMUTES_PATH.slice(1), html: raw(COMMUTES_FILE), sitemap: false },
  ];
}

export function render() {
  const body = `${CSS}
<div class="sr-head">
  <h1>Street Roles Map</h1>
  <p class="lede">Each street gets one role: through traffic, local trips, bikes, or people on foot. With the network: these roles plus the full Biking and Rolling Plan.</p>
</div>
<div class="sr" data-sr data-streets="${STREETS_PATH}" data-commutes="${COMMUTES_PATH}">
  <div class="sr-ctl">
    <div><h2>Show</h2><div class="sr-views" role="group" aria-label="What the map shows">${VIEWS.map(viewBtn).join("")}</div></div>
    <div class="sr-edits"><h2>Your changes</h2><p data-edits>Tap a street to change its role.</p><button type="button" class="sr-opt" data-reset disabled>Reset Roles</button></div>
  </div>
  <div class="sr-stage">
    <div class="glmap sr-map" id="sr-map" role="region" aria-label="Map of San Francisco streets colored by their role or by bike traffic stress"></div>
    <div class="sr-card" hidden aria-live="polite"></div>
  </div>
  <div class="sr-out">
    <p class="sr-q">Of about ${sig2(S0.commuters_in_window)} SF residents with a short commute in SF, how many could bike it on streets most adults will ride?</p>
    <div class="sr-stats" aria-live="polite">
      <div class="sr-stat lead" data-card="network"><span class="when">With the network</span><span class="big" data-net>${sig2(S0.connected_network)}</span><span class="pct" data-net-pct>${pct(S0.connected_network, S0.commuters_in_window)}</span></div>
      <div class="sr-stat" data-card="today"><span class="when">Today</span><span class="big">${sig2(S0.connected_today)}</span><span class="pct">${pct(S0.connected_today, S0.commuters_in_window)}</span></div>
    </div>
    <ul class="sr-key" data-key></ul>
    <p class="sr-asof"><a href="${ABOUT}">How we measured</a></p>
  </div>
</div>
<ul class="cite" data-for="Street Roles Map" data-how="${ABOUT}">
  <li><a href="https://data.sfgov.org/d/3psu-pn9h">DataSF street centerlines</a>, the city's street classification</li>
  <li><a href="https://www.sfmta.com/media/41810/download">Biking and Rolling Plan</a>, North Star network</li>
  <li><a href="https://lehd.ces.census.gov/data/lodes/LODES8/ca/od/">Census LODES 2023</a>, where residents work</li>
</ul>
${MAP_HEAD}
${SCRIPT}`;
  return page({
    title: "Street Roles Map",
    description: "Every San Francisco street given one role, through, local, bike or walk, with its bike traffic stress today and with the network, and how many short commutes it connects.",
    path,
    body,
    sources: SOURCES,
    dataUpdated,
  });
}
