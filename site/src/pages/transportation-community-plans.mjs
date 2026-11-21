// Community Plans: every bikeway that earlier city, community and advocacy
// plans asked for, one colour per plan, over the 2025 Biking and Rolling
// Plan's network, with a switch to show only what that plan leaves out.
//
// Bryan, 2026-10-14: "An advocate mentioned that many of the gaps in BRP actually
// have proposed bikeways in earlier community action plans that were left out.
// Can we make a better BRP plus CAP map that fills in BRP gaps with CAP."
// And the same day, on the first version: "make it possible to see all the
// plans chronologically in a list and let me toggle plans on and off. And see
// each plan in a different color in normal mode. Or have another map where
// you just show me what's not in the BRP but in the other layers."
//
// The blocks come from site/data/community-plans/blocks.json, which
// tools/bike-network/community-plan-bikeways.py writes from the proposals read out of the
// plan PDFs (data/community-plans/bikeway-proposals.json). A plan's ask is a
// bikeway it recommends: an option it set aside, or a road diet with no bike
// lane, is not one, and shows only in a street's card. A block is "not in the
// Biking and Rolling Plan" when it has no all-ages line today and the plan's
// North Star map draws none on it (grade "gap"). Miles are centerline block
// miles, each block counted once, which About the Data says beside the method.
//
// Plans sharing a block are drawn side by side (line-offset), not stacked, so
// every plan on a street stays visible; the card lists them too. Colours are
// Observable 10's first nine hues dealt oldest plan first; the tenth, a grey,
// is left out because grey is the 2025 plan's own line here. Plans ten and up
// reuse the hues dashed, and nineteen and up dotted.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { MAP_HEAD, boundsOf, encodeRuns, inlineJson } from "../maplibre.mjs";
import { ABOUT_DATA, PLAN_URL, esc, BIKE_DATA_READ } from "../transportation.mjs";
import { streetName } from "../street-name.mjs";

export const path = "/transportation/bike/community-plans";
export const file = "transportation/bike/community-plans/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Other Bike Plans", line: "Bikeways that earlier city, community and advocacy plans asked for and the Biking and Rolling Plan leaves out.", order: 1 };
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = BIKE_DATA_READ[0];
const BLOCKS_PATH = `${path}/blocks.json`;
export const UNPLACED_HREF = "/transportation/bike/about#community-plans-unplaced";

const DATA = nodePath.join(import.meta.dirname, "..", "..", "data");
export const cap = JSON.parse(fs.readFileSync(nodePath.join(DATA, "community-plans", "blocks.json"), "utf8"));
const segments = JSON.parse(fs.readFileSync(nodePath.join(DATA, "bike-history", "segments.json"), "utf8"));

// The all-ages network drawn under the plans, picked as the school travel
// model picks it (all_ages_lines in lib/school-travel-time.py): today, the
// latest year's segments coded 1, 4, S, 2c or 3c; the plan built adds every
// rated North Star block drawn Separated, Car-free, Shared-use Path or Shared
// that isn't all-ages today. Moved here from the Getting to School page when
// that page was deleted (2026-10-15).
const TODAY_CODES = new Set(["1", "4", "S", "2c", "3c"]);
const PLAN_FACILITIES = new Set(["Separated", "Car-free", "Shared-use Path", "Shared"]);
function network() {
  const read = (...f) => JSON.parse(fs.readFileSync(nodePath.join(DATA, ...f), "utf8"));
  const components = read("bike-history", "components.json").blocks;
  const last = segments.years.length - 1;
  const today = segments.segments
    .filter((s) => s.y[last] !== "0" && s.pts.length > 1 && components[s.key])
    .filter((s) => {
      const c = components[s.key];
      return Object.keys(c.m).some((m) => TODAY_CODES.has(m)) || c.s != null;
    })
    .map((s) => s.pts);
  const status = new Map(read("north-star", "status.json").blocks.map((b) => [String(b.cnn), b]));
  const plan = read("north-star", "traced.geojson")
    .features.filter((f) => {
      const st = status.get(String(f.properties.cnn));
      return st && PLAN_FACILITIES.has(f.properties.facility) && st.m > 0 && f.geometry.coordinates.length > 1;
    })
    .map((f) => f.geometry.coordinates);
  return { today: encodeRuns(today, { tol: 2 }), plan: encodeRuns(plan, { tol: 2 }) };
}

// Observable Plot's observable10, less its grey (see the head of this file).
const HUES = ["#4269d0", "#efb118", "#ff725c", "#6cc5b0", "#3ca951", "#ff8ab7", "#a463f2", "#97bbf5", "#9c6b4e"];
const DASHES = ["solid", "dash", "dot"];

const FT_PER_MI = 5280;
const sig2 = (x) => (x === 0 ? "0" : x >= 10 ? String(Math.round(x)) : x.toPrecision(2));
const mi = (ft) => sig2(ft / FT_PER_MI);
const n = (v) => v.toLocaleString("en-US");
const longDate = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

// The plans in list order (the data file's, oldest first), each with its
// colour and line style if it has a street drawn on the map.
let dealt = 0;
export const plans = cap.plans.map((p, i) => {
  const drawn = p.feet > 0;
  const k = drawn ? dealt++ : -1;
  return { ...p, i, drawn, color: drawn ? HUES[k % HUES.length] : null, dash: drawn ? DASHES[Math.min(2, Math.floor(k / HUES.length))] : null };
});

// A block's grade letter in the fetched file. g: no all-ages line today or in
// the 2025 plan, asked for as a bikeway; k: the same, but only as an option a
// plan set aside; n: the same, asked for without a bike lane; p: in the 2025
// plan, not built; u: in the 2025 plan as Undecided; t: all-ages today.
const GRADE_KEY = { gap: "g", considered: "k", notbike: "n", plan: "p", undecided: "u", today: "t" };

const sum = (bs) => bs.reduce((t, b) => t + b.feet, 0);
const asked = (b) => b.proposals.some((k) => cap.proposals[k].recommended && cap.proposals[k].bike);
const askedBlocks = cap.blocks.filter(asked);
// With every plan on: the page's opening state and its headline.
export const totals = {
  asked: { blocks: askedBlocks.length, feet: sum(askedBlocks) },
  out: { blocks: askedBlocks.filter((b) => b.grade === "gap").length, feet: sum(askedBlocks.filter((b) => b.grade === "gap")) },
  plan: { feet: sum(askedBlocks.filter((b) => b.grade === "plan")) },
  undecided: { feet: sum(askedBlocks.filter((b) => b.grade === "undecided")) },
  today: { feet: sum(askedBlocks.filter((b) => b.grade === "today")) },
};
const networkAsOf = segments.sources.network.queried;
const firstYear = Math.min(...cap.plans.map((p) => p.year));
const drawnCount = plans.filter((p) => p.drawn).length;

const CSS = `<style>
.cp-head { width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); }
.cp-head h1 { font-size: clamp(1.35rem, 2.4vw, 1.65rem); margin: 0 0 4px; text-wrap: pretty; }
.cp-head .lede { margin: 0 0 8px; max-width: 125ch; font-size: 0.95rem; }
.cp { width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); display: grid; grid-template-columns: 375px minmax(0, 1fr) 225px; gap: 16px; align-items: start; }
.cp h2 { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 0 0 4px; font-weight: 600; font-family: inherit; }
.cp-btns { display: flex; gap: 6px; margin: 0 0 6px; }
.cp-btns button, .cp-view button { font: inherit; font-size: 0.8rem; border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 6px; padding: 3px 9px; cursor: pointer; }
.cp-btns button:hover, .cp-view button:hover { background: var(--raised); }
.cp-list { list-style: none; margin: 0; padding: 0; max-height: calc(100dvh - 300px); min-height: 260px; overflow: auto; border-top: 1px solid var(--rule); }
.cp-list li { display: grid; grid-template-columns: 18px 26px 34px minmax(0, 1fr) 56px; column-gap: 6px; align-items: center; padding: 2px 4px 2px 0; border-bottom: 1px solid var(--rule); font-size: 0.8rem; line-height: 1.3; }
.cp-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cp-list li.off .cp-name, .cp-list li.off .cp-mi, .cp-list li.off .cp-yr { color: var(--muted); }
.cp-list li.off svg { opacity: 0.35; }
.cp-list li.none { color: var(--muted); }
.cp-list li.on-sel { background: var(--raised); }
.cp-list input { margin: 0; accent-color: var(--ink); }
.cp-yr, .cp-mi { font-variant-numeric: tabular-nums; }
.cp-mi { text-align: right; white-space: nowrap; }
.cp-mi a { font-size: 0.72rem; color: var(--muted); }
.cp-name { cursor: pointer; }
.cp-name:hover { text-decoration: underline; }
.cp-list li.none .cp-name { cursor: default; text-decoration: none; }
.cp-list .cp-kind { color: var(--muted); }
.cp-listhead { display: grid; grid-template-columns: 18px 26px 34px minmax(0, 1fr) 56px; column-gap: 6px; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); padding: 0 4px 2px 0; }
.cp-listhead span:last-child { text-align: right; }
.cp-view { display: inline-flex; margin: 0 0 6px; border: 1px solid var(--rule); border-radius: 7px; overflow: hidden; }
.cp-view button { border: 0; border-radius: 0; padding: 5px 12px; font-size: 0.86rem; }
.cp-view button + button { border-left: 1px solid var(--rule); }
.cp-view button[aria-pressed="true"] { background: var(--ink); color: var(--paper); }
.cp-stage { position: relative; }
.cp-gl { height: max(380px, calc(100dvh - 330px)); max-height: 760px; }
.cp-note { font-size: 0.76rem; line-height: 1.35; color: var(--muted); margin: 4px 0 0; }
.cp-card { position: absolute; z-index: 2; width: 290px; max-height: calc(100% - 16px); overflow: auto; background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.15); padding: 9px 12px 10px; font-size: 0.83rem; line-height: 1.4; }
.cp-card h3 { font-size: 0.95rem; margin: 0 22px 2px 0; }
.cp-card .cp-grade { margin: 0 0 6px; color: var(--muted); font-size: 0.78rem; }
.cp-card ul { list-style: none; margin: 0; padding: 0; }
.cp-card li { margin: 0 0 7px; padding-left: 9px; border-left: 4px solid var(--rule); }
.cp-card li span { display: block; color: var(--muted); }
.cp-card button { position: absolute; top: 4px; right: 6px; border: 0; background: none; font-size: 1.1rem; line-height: 1; cursor: pointer; color: var(--muted); padding: 2px 4px; }
.cp-fig { display: grid; gap: 6px; }
.cp-row { display: grid; grid-template-columns: 1fr; padding: 5px 10px 6px; border: 1px solid var(--rule); border-radius: 8px; background: var(--paper); }
.cp-row b { font-family: Archivo, sans-serif; font-size: 1.35rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.cp-row b small { font-size: 0.8rem; font-weight: 600; margin-left: 3px; }
.cp-row span { font-size: 0.8rem; line-height: 1.3; color: var(--muted); }
.cp-row i { display: block; height: 6px; border-radius: 2px; background: var(--muted); margin: 4px 0 2px; max-width: 100%; }
.cp-row.lead { border-color: var(--ink); }
.cp-row.lead i { background: var(--ink); }
.cp-side p { font-size: 0.82rem; line-height: 1.4; margin: 8px 0 0; color: var(--muted); }
@media (max-width: 1180px) {
  .cp { grid-template-columns: 300px minmax(0, 1fr); }
  .cp-side { grid-column: 2; }
}
@media (max-width: 760px) {
  .cp { grid-template-columns: 1fr; gap: 12px; }
  .cp-map { order: 1; }
  .cp-side { order: 2; grid-column: auto; }
  .cp-ctl { order: 3; }
  .cp-fig { grid-template-columns: 1fr 1fr; }
  .cp-fig .cp-row:last-child { grid-column: 1 / -1; }
  .cp-row b { font-size: 1.15rem; }
  .cp-row span { font-size: 0.72rem; }
  .cp-view button { padding: 5px 9px; font-size: 0.8rem; }
  .cp-gl { height: min(105vw, 58svh); }
  .cp-list { max-height: none; min-height: 0; }
  .cp-card { position: static; width: auto; max-height: none; margin-top: 8px; box-shadow: none; }
}
</style>`;

// A line swatch in the plan's colour and style, the same one the map draws.
function swatch(p) {
  const dash = p.dash === "dash" ? ' stroke-dasharray="6 3"' : p.dash === "dot" ? ' stroke-dasharray="0.1 4.5"' : "";
  return `<svg width="24" height="8" viewBox="0 0 24 8" aria-hidden="true"><line x1="2" y1="4" x2="22" y2="4" stroke="${p.color}" stroke-width="4" stroke-linecap="${p.dash === "dot" ? "round" : "butt"}"${dash}/></svg>`;
}
const BRP_SWATCH = `<svg width="24" height="8" viewBox="0 0 24 8" aria-hidden="true"><line x1="2" y1="4" x2="22" y2="4" stroke="var(--muted)" stroke-width="2" stroke-dasharray="3 2.4"/></svg>`;

// Why a plan has no street on the map, for its row.
function none(p) {
  if (p.proposalCount && p.unplacedCount === p.proposalCount) return "No two cross streets to draw between";
  return "Only options it set aside, or no bike lane";
}

function planList() {
  const brpYear = 2025;
  const rows = [];
  let brpDone = false;
  const brp = `<li data-brp><input type="checkbox" checked aria-label="Show the Biking and Rolling Plan network"><span>${BRP_SWATCH}</span><span class="cp-yr">${brpYear}</span>` +
    `<span class="cp-name" data-brp-name><a href="${PLAN_URL}">Biking and Rolling Plan</a> <span class="cp-kind">network, in grey</span></span><span class="cp-mi" data-mi>${mi(cap.networkFeet)}</span></li>`;
  for (const p of plans) {
    if (!brpDone && p.year > brpYear) { rows.push(brp); brpDone = true; }
    const kind = p.kind === "advocacy" ? ' <span class="cp-kind">advocates</span>' : "";
    if (!p.drawn) {
      rows.push(`<li class="none" title="${esc(none(p))}"><input type="checkbox" disabled aria-label="${esc(p.name)}: nothing drawn"><span></span><span class="cp-yr">${p.year}</span>` +
        `<span class="cp-name"><a href="${esc(p.url)}" title="${esc(p.name)}">${esc(p.name)}</a>${kind}</span><span class="cp-mi"><a href="${UNPLACED_HREF}">not drawn</a></span></li>`);
      continue;
    }
    rows.push(`<li data-plan="${p.i}"><input type="checkbox" checked aria-label="Show ${esc(p.name)}"><span>${swatch(p)}</span><span class="cp-yr">${p.year}</span>` +
      `<span class="cp-name" data-name title="${esc(p.name)}">${esc(p.name)}${kind}</span><span class="cp-mi" data-mi>${mi(p.feet)}</span></li>`);
  }
  if (!brpDone) rows.push(brp);
  return rows.join("\n");
}

function figures() {
  const t = totals;
  const row = (key, ft, label, lead) => `<div class="cp-row${lead ? " lead" : ""}"><b data-fig="${key}">${mi(ft)}<small>miles</small></b>` +
    `<i data-bar="${key}" style="width:${Math.round((100 * ft) / t.asked.feet)}%"></i><span>${label}</span></div>`;
  return `<div class="cp-fig">
    ${row("out", t.out.feet, "not in the Biking and Rolling Plan, and no all-ages route today", true)}
    ${row("plan", t.plan.feet, "in the Biking and Rolling Plan, not built yet")}
    ${row("undecided", t.undecided.feet, "drawn as Undecided in the Biking and Rolling Plan")}
    ${row("today", t.today.feet, "all-ages today")}
    ${row("asked", t.asked.feet, "asked for in all, by the plans you've turned on")}
  </div>`;
}

// What the page script fetches: every block's line, encoded, with its grade,
// street, feet and proposals, and the proposals.
function blocksFile() {
  return {
    lines: encodeRuns(cap.blocks.map((b) => b.line)),
    blocks: cap.blocks.map((b) => [GRADE_KEY[b.grade], streetName(b.street), b.feet, b.proposals]),
    proposals: cap.proposals.map((q) => [q.plan, q.street, q.from, q.to, q.page, q.pdfPage || 0, q.asWritten, q.recommended ? 1 : 0, q.bike ? 1 : 0]),
  };
}

const BOUNDS = boundsOf(cap.blocks.map((b) => b.line));

const SCRIPT = `<script>
(function () {
  var box = document.querySelector("[data-cap]");
  if (!box) return;
  var D = JSON.parse(box.querySelector("[data-cap-data]").textContent);
  var el = box.querySelector(".cp-gl"), stage = box.querySelector(".cp-stage"), card = box.querySelector(".cp-card");
  var narrow = window.matchMedia("(max-width: 760px)");
  var OUT = { g: 1 };
  var GRADE = { g: "No all-ages route today or in the Biking and Rolling Plan", k: "No all-ages route today or in the Biking and Rolling Plan", n: "No all-ages route today or in the Biking and Rolling Plan",
    p: "In the Biking and Rolling Plan, not built yet", u: "In the Biking and Rolling Plan as Undecided", t: "All-ages today" };
  var rows = Array.prototype.slice.call(box.querySelectorAll("[data-plan]"));
  var brpRow = box.querySelector("[data-brp]"), brpBox = brpRow.querySelector("input");
  var brpMi = brpRow.querySelector("[data-mi]"), brpMiles = brpMi.textContent;
  var viewBtns = Array.prototype.slice.call(box.querySelectorAll("[data-view]"));
  var byId = {}; D.plans.forEach(function (p, i) { byId[p.id] = i; });
  // ---- state: the view, the plans turned off, and the 2025 network ----
  var view = "all", on = {}, brp = true;
  function defaults() { view = "all"; brp = true; on = {}; D.plans.forEach(function (p, i) { if (p.drawn) on[i] = true; }); }
  defaults();
  (function fromUrl() {
    var q = new URLSearchParams(location.search);
    if (q.get("view") === "out") view = "out";
    (q.get("off") || "").split(",").forEach(function (id) { if (id === "brp") brp = false; else if (id in byId) delete on[byId[id]]; });
  })();
  function toUrl() {
    var q = new URLSearchParams(location.search), off = [];
    D.plans.forEach(function (p, i) { if (p.drawn && !on[i]) off.push(p.id); });
    if (!brp) off.push("brp");
    if (view === "out") q.set("view", "out"); else q.delete("view");
    if (off.length) q.set("off", off.join(",")); else q.delete("off");
    var qs = q.toString() ? "?" + q.toString().replace(/%2C/g, ",") : "";
    if (qs !== location.search) {
      history.replaceState(null, "", location.pathname + qs + location.hash);
      window.dispatchEvent(new CustomEvent("sfworks:state", { detail: qs + location.hash }));
    }
  }
  function mi(ft) { var x = ft / 5280; return x === 0 ? "0" : x >= 10 ? String(Math.round(x)) : x.toPrecision(2); }
  // The controls show the state; the map and figures follow.
  function paintControls() {
    rows.forEach(function (r) {
      var i = +r.dataset.plan, p = D.plans[i];
      r.querySelector("input").checked = !!on[i];
      r.classList.toggle("off", !on[i]);
      r.querySelector("[data-mi]").textContent = mi(view === "out" ? p.outFeet : p.feet);
    });
    brpBox.checked = brp; brpRow.classList.toggle("off", !brp);
    brpMi.textContent = view === "out" ? "" : brpMiles;
    viewBtns.forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.view === view ? "true" : "false"); });
    box.querySelector("[data-mihead]").textContent = view === "out" ? "Left out" : "Miles";
  }
  var map = sfMap.create(el, { bounds: D.bounds, padding: function () { return 10; }, onReset: function () { pick(null); } });
  var B = null, runs = null, sel = [];
  box.capMap = map;                               // for the page checks that click a street
  // The on plans that ask for a bikeway on block i, oldest first.
  function asksOn(i) {
    var out = [], ps = B.blocks[i][3];
    for (var j = 0; j < ps.length; j++) {
      var q = B.proposals[ps[j]];
      if (q[7] && q[8] && on[q[0]] && out.indexOf(q[0]) < 0) out.push(q[0]);
    }
    return out.sort(function (a, z) { return a - z; });
  }
  function shown(i) { return asksOn(i).length > 0 && (view === "all" || OUT[B.blocks[i][0]]); }
  function geom(i) { var r = runs[i]; return r.length > 1 ? { type: "LineString", coordinates: r } : { type: "Point", coordinates: r[0] }; }
  function draw() {
    if (!B) return;
    var fs = [], fig = { out: 0, plan: 0, undecided: 0, today: 0, asked: 0 };
    for (var i = 0; i < B.blocks.length; i++) {
      var ps = asksOn(i), g = B.blocks[i][0];
      if (!ps.length) continue;
      fig.asked += B.blocks[i][2];
      if (g === "g") fig.out += B.blocks[i][2]; else if (g === "p") fig.plan += B.blocks[i][2]; else if (g === "u") fig.undecided += B.blocks[i][2]; else if (g === "t") fig.today += B.blocks[i][2];
      if (view === "out" && !OUT[g]) continue;
      for (var k = 0; k < ps.length; k++) {
        var p = D.plans[ps[k]];
        fs.push({ type: "Feature", properties: { i: i, c: p.color, d: p.dash, o: k - (ps.length - 1) / 2 }, geometry: geom(i) });
      }
    }
    map.getSource("cap").setData(sfMap.collection(fs));
    Object.keys(fig).forEach(function (key) {
      box.querySelector('[data-fig="' + key + '"]').firstChild.nodeValue = mi(fig[key]);
      box.querySelector('[data-bar="' + key + '"]').style.width = Math.round(100 * fig[key] / D.allFeet) + "%";
    });
    if (map.getLayer("net-plan")) map.setLayoutProperty("net-plan", "visibility", brp ? "visible" : "none");
    // A selection keeps only what is still drawn.
    if (sel.length) { var keep = sel.filter(shown); if (!keep.length) pick(null); else light(keep); }
  }
  function changed() { paintControls(); draw(); toUrl(); }
  // ---- the card and the selection ----
  function light(ids) {
    sel = ids;
    if (B) map.getSource("sel").setData(sfMap.collection(ids.map(function (i) { return { type: "Feature", properties: { n: asksOn(i).length }, geometry: geom(i) }; })));
  }
  function boxOf(ids) {
    var b = sfMap.screenBox(map, ids.map(function (i) { return runs[i]; }));
    var sr = stage.getBoundingClientRect(), gr = el.getBoundingClientRect();
    return { l: b.l + gr.left - sr.left, r: b.r + gr.left - sr.left, t: b.t + gr.top - sr.top, b: b.b + gr.top - sr.top };
  }
  // The card goes on whichever side of the selection has room, so it never
  // covers the street it describes. On a phone it sits under the map.
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
  // The proposals' own notes in brackets stay in the data file, not the card.
  function bare(s) { return String(s).replace(/\\s*\\([^)]*\\)/g, "").trim(); }
  function h(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
  function say(i) {
    var b = B.blocks[i], items = b[3].filter(function (k) { return on[B.proposals[k][0]]; }).sort(function (x, y) { return B.proposals[x][0] - B.proposals[y][0]; }).map(function (k) {
      var q = B.proposals[k], pl = D.plans[q[0]], href = pl.url + (q[5] ? "#page=" + q[5] : "");
      var why = q[7] ? (q[8] ? "" : " (no bike lane asked for)") : " (an option it set aside)";
      return '<li style="border-left-color:' + pl.color + '"><a href="' + h(href) + '">' + h(pl.name) + "</a>, " + pl.year +
        "<span>" + h(bare(q[1])) + " from " + h(bare(q[2])) + " to " + h(bare(q[3])) + "</span>" +
        "<span>" + h(q[6]) + why + ", p. " + h(bare(q[4])) + "</span></li>";
    });
    return '<button type="button" aria-label="Close">\\u00d7</button><h3>' + h(b[1]) + "</h3>" +
      '<p class="cp-grade">' + GRADE[b[0]] + "</p><ul>" + items.join("") + "</ul>";
  }
  // A click selects every drawn block of every ask on the street clicked.
  function pick(i) {
    rows.forEach(function (t) { t.classList.remove("on-sel"); });
    if (i === null) { card.hidden = true; light([]); return; }
    var mine = B.blocks[i][3].filter(function (k) { var q = B.proposals[k]; return q[7] && q[8] && on[q[0]]; }), ids = [];
    for (var j = 0; j < B.blocks.length; j++) if (shown(j) && B.blocks[j][3].some(function (k) { return mine.indexOf(k) >= 0; })) ids.push(j);
    light(ids.length ? ids : [i]);
    card.innerHTML = say(i);
    card.hidden = false;
    card.querySelector("button").addEventListener("click", function () { pick(null); });
    place();
    if (narrow.matches) card.scrollIntoView({ block: "nearest" });
  }
  // A plan's name lights its drawn blocks and fits the map to them.
  function pickPlan(pi, row) {
    if (!B) return;
    var ids = [];
    for (var j = 0; j < B.blocks.length; j++) if (shown(j) && asksOn(j).indexOf(pi) >= 0) ids.push(j);
    card.hidden = true;
    light(ids);
    rows.forEach(function (r) { r.classList.toggle("on-sel", r === row); });
    var bb = new maplibregl.LngLatBounds();
    ids.forEach(function (j) { runs[j].forEach(function (c) { bb.extend(c); }); });
    if (ids.length) map.fitBounds(bb, { padding: 60, maxZoom: 15.5, duration: 500 });
  }
  // ---- controls ----
  rows.forEach(function (r) {
    var i = +r.dataset.plan;
    r.querySelector("input").addEventListener("change", function (e) { if (e.target.checked) on[i] = true; else delete on[i]; changed(); });
    r.querySelector("[data-name]").addEventListener("click", function () { if (!on[i]) { on[i] = true; changed(); } pickPlan(i, r); });
  });
  brpBox.addEventListener("change", function () { brp = brpBox.checked; changed(); });
  viewBtns.forEach(function (b) { b.addEventListener("click", function () { view = b.dataset.view; changed(); }); });
  box.querySelector("[data-all]").addEventListener("click", function () { D.plans.forEach(function (p, i) { if (p.drawn) on[i] = true; }); changed(); });
  box.querySelector("[data-none]").addEventListener("click", function () { on = {}; changed(); });
  box.querySelector("[data-reset]").addEventListener("click", function () { defaults(); pick(null); changed(); });
  paintControls();
  if (!map) return;
  map.on("load", function () {
    var before = sfMap.under(map);
    var line = function (enc) { return sfMap.collection(sfMap.features(sfMap.decode(enc))); };
    map.addSource("net-today", { type: "geojson", data: line(D.net.today) });
    map.addSource("net-plan", { type: "geojson", data: line(D.net.plan) });
    map.addSource("cap", { type: "geojson", data: sfMap.collection([]) });
    map.addSource("sel", { type: "geojson", data: sfMap.collection([]) });
    var thin = ["interpolate", ["linear"], ["zoom"], 11, 0.9, 15, 2.2];
    // One plan's line, and the step between plans drawn side by side.
    var W = [11, 2.6, 13, 3.4, 15, 5, 17, 7];
    var width = ["interpolate", ["linear"], ["zoom"]].concat(W);
    var off = ["interpolate", ["linear"], ["zoom"]];
    for (var z = 0; z < W.length; z += 2) off.push(W[z], ["*", ["get", "o"], W[z + 1]]);
    var halo = ["interpolate", ["linear"], ["zoom"]];
    for (var z2 = 0; z2 < W.length; z2 += 2) halo.push(W[z2], ["+", 6, ["*", ["max", 1, ["get", "n"]], W[z2 + 1]]]);
    map.addLayer({ id: "net-today", type: "line", source: "net-today", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": sfMap.token("--muted"), "line-width": thin, "line-opacity": 0.45 } }, before);
    map.addLayer({ id: "net-plan", type: "line", source: "net-plan", layout: { "line-cap": "butt", "line-join": "round", visibility: brp ? "visible" : "none" }, paint: { "line-color": sfMap.token("--muted"), "line-width": thin, "line-opacity": 0.8, "line-dasharray": [1.5, 1.2] } }, before);
    map.addLayer({ id: "sel", type: "line", source: "sel", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": sfMap.token("--ink"), "line-width": halo } }, before);
    var STYLE = { solid: null, dash: [2.2, 1.2], dot: [0.1, 1.8] };
    Object.keys(STYLE).forEach(function (d) {
      var paint = { "line-color": ["get", "c"], "line-width": width, "line-offset": off };
      if (STYLE[d]) paint["line-dasharray"] = STYLE[d];
      map.addLayer({ id: "ask-" + d, type: "line", source: "cap", filter: ["==", ["get", "d"], d], layout: { "line-cap": d === "dot" ? "round" : "butt", "line-join": "round" }, paint: paint }, before);
    });
    fetch(box.dataset.src).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (data) {
      B = data; runs = sfMap.decode(B.lines);
      draw();
      box.dataset.ready = "1";
    }).catch(function (e) { if (window.console) console.warn("community plans map:", e && e.message); });
  });
  var LAYERS = ["ask-solid", "ask-dash", "ask-dot"];
  var hoverOn = window.matchMedia && window.matchMedia("(hover: hover)").matches;
  if (hoverOn) map.on("mousemove", function (e) {
    var f = B && sfMap.near(map, e.point, LAYERS)[0];
    map.getCanvas().style.cursor = f ? "pointer" : "";
  });
  map.on("click", function (e) {
    if (!B) return;
    var f = sfMap.near(map, e.point, LAYERS)[0];
    pick(f ? f.properties.i : null);
  });
  map.on("moveend", function () { if (!card.hidden) place(); });
  window.addEventListener("resize", function () { if (!card.hidden) place(); });
})();
</script>`;

export function pages() {
  return [{ path: BLOCKS_PATH, file: BLOCKS_PATH.slice(1), html: Buffer.from(JSON.stringify(blocksFile())), sitemap: false }];
}

export function render() {
  const t = totals;
  const unplaced = cap.proposalCount - cap.placedCount;
  const data = {
    bounds: BOUNDS, net: network(), allFeet: t.asked.feet,
    plans: plans.map((p) => ({ id: p.id, name: p.name, year: p.year, url: p.url, drawn: p.drawn, color: p.color, dash: p.dash, feet: p.feet, outFeet: p.outFeet })),
  };
  const body = `${CSS}
<div class="cp-head">
<h1>Other Plans Asked for ${mi(t.out.feet)} Mapped Miles of Bike Streets the Biking and Rolling Plan Leaves Out</h1>
<p class="lede">Since ${firstYear}, ${cap.plans.length} city, community and advocacy plans have asked for bike routes on San Francisco streets. We put the bikeways each plan asks for on the map in its own color or line style, beside the <a href="${PLAN_URL}">Biking and Rolling Plan</a> the San Francisco Municipal Transportation Agency adopted in 2025.</p>
</div>
<div class="cp" data-cap data-src="${BLOCKS_PATH}">
  <div class="cp-ctl">
    <h2>The Plans, Oldest First</h2>
    <div class="cp-btns"><button type="button" data-all>All On</button><button type="button" data-none>All Off</button><button type="button" data-reset>Reset</button></div>
    <div class="cp-listhead"><span></span><span></span><span>Year</span><span>Plan</span><span data-mihead>Miles</span></div>
    <ul class="cp-list">${planList()}</ul>
  </div>
  <figure class="cp-map" style="margin:0">
    <div class="cp-view" role="group" aria-label="Which streets to show"><button type="button" data-view="all" aria-pressed="true">Every Plan's Asks</button><button type="button" data-view="out" aria-pressed="false">Not in the Biking and Rolling Plan</button></div>
    <div class="cp-stage">
      <div class="glmap cp-gl" role="img" aria-label="Map of San Francisco with the streets each earlier plan asked for drawn in its own color, over today's all-ages network and the Biking and Rolling Plan's network in grey"></div>
      <div class="cp-card" hidden aria-live="polite"></div>
    </div>
    <p class="cp-note">Click a street for the plans that asked for it. Grey is today's all-ages network, by the 2025 plan's own test, dashed where that plan adds to it. Plans read ${longDate(cap.read)}, network as of ${longDate(networkAsOf)}. <b>Note:</b> <a href="${UNPLACED_HREF}">${unplaced} of ${cap.proposalCount} proposals</a> aren't drawn, since they have no two cross streets to draw between.</p>
    <ul class="cite" data-for="Community plans map|Plan list" data-how="/transportation/bike/about#community-plans">
      <li>${cap.plans.length} plan documents, ${firstYear} to ${Math.max(...cap.plans.map((p) => p.year))}, linked on each street</li>
      <li><a href="https://data.sf.gov/d/3psu-pn9h">DataSF street centerlines</a></li>
      <li><a href="${PLAN_URL}">Biking and Rolling Plan</a>, North Star network</li>
      <li><a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA bikeway layer</a>, read ${longDate(networkAsOf)}</li>
    </ul>
    <script type="application/json" data-cap-data>${inlineJson(data)}</script>
  </figure>
  <div class="cp-side">
    <h2>What the Plans You've Turned On Ask For</h2>
    ${figures()}
    <p>These totals count each block once. A block two plans ask for also shows in both plans' rows.</p>
  </div>
</div>
${MAP_HEAD}${SCRIPT}`;

  return page({
    title: "Other Bike Plans and the Biking and Rolling Plan",
    description: `${cap.plans.length} city, community and advocacy plans asked for bikeways on ${mi(t.out.feet)} miles of San Francisco street that the 2025 Biking and Rolling Plan doesn't draw as all-ages.`,
    path,
    about: ABOUT_DATA,
    // The bikeway layer's read date: the community plans' blocks are graded against today's network.
    dataUpdated,
    body,
  });
}
