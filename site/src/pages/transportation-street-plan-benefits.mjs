// Street Plan Benefits Explorer: what San Francisco gains each year as a smaller share of trips is made by car,
// with the bike network built, and who gets it. One question: as the car share falls, what is the shift worth a
// year, and how much of that depends on whether people chose to switch or were pushed?
//
// Two controls: the car share (53% today down to 15%) and the share of switchers who chose the switch (0 to 100%).
// The figure is one bar per benefit, split between the people who switch and everyone else, with the total and its
// simulated 5th to 95th percentile range. Every figure comes precomputed from site/data/street-plan-benefits.json,
// a grid of car share in 1-point steps by chosen share in 10-point steps, written by the benefits model's --grid
// option (its version and date are in the file). The browser only looks up a cell and draws it with Plot.
//
// Published as a draft and linked from nowhere else while the tool's name is undecided: a draft listing keeps it
// off every list outside its own page (src/directory.mjs), and it stays out of the sitemap, as the Muni
// optimizer does. Controls left and the figure right on one 1366x768 screen; method and caveats in About the Data
// below the tool.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { inlineJson } from "../maplibre.mjs";
import { Plot, plotSVG } from "../plot.mjs";

export const path = "/transportation/street-plan-benefits";
export const file = "transportation/street-plan-benefits/index.html";
export const sitemap = false;
export const listing = { draft: true, title: "Street Plan Benefits Explorer", line: "What fewer car trips are worth to San Francisco each year, and who gets it." };
export const dateFiles = ["data/street-plan-benefits.json"];

const TITLE = "Street Plan Benefits Explorer";
const RAW = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "..", "data", "street-plan-benefits.json"), "utf8"));
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const longDate = (d) => `${+d.slice(8, 10)} ${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;

// The rows as the chart names them, in the order it draws them, keyed by the model's row names.
const ROWS = [
  ["Health from walking and biking", "Health"],
  ["Journey quality on the bike network", "Comfort on new bike lanes"],
  ["Driving costs saved", "Driving costs saved"],
  ["Parking costs saved", "Parking costs saved"],
  ["Time for people who switch", "Time for people who switch"],
  ["Injuries", "Injuries"],
  ["Congestion for remaining drivers", "Less traffic for drivers, at most"],
  ["Climate (CO2)", "Climate"],
  ["Air quality health", "Cleaner air"],
  ["Noise", "Less noise"],
];

// Two significant figures, as the page prints every figure (tool UX rule 30).
const sig2 = (v) => (v === 0 ? 0 : Number(v.toPrecision(2)));

// What the browser needs: for each car share and chosen share, each row's [mid, 5th, 95th, to switchers, to everyone
// else] in $M, then the total's, then deaths avoided [mid, 5th, 95th], all to two significant figures.
export const D = {
  version: RAW.version,
  today: RAW.today,
  def: RAW.default,
  car: RAW.car,
  chosen: RAW.chosen,
  labels: ROWS.map(([, l]) => l),
  split: RAW.car.map((c) => RAW.split[String(c)]),
  cells: RAW.car.map((c) => RAW.chosen.map((h) => {
    const x = RAW.cells[String(c)][String(h)];
    return [...ROWS.map(([k]) => x.rows[k].map(sig2)), x.total.map(sig2), x.deaths.map(sig2)];
  })),
};

// One x domain for every state, so the axis never moves when a control changes (tool UX rule 7).
const ends = D.cells.flat().flatMap((cell) => cell.slice(0, ROWS.length).map((r) => [Math.min(0, r[3]) + Math.min(0, r[4]), Math.max(0, r[3]) + Math.max(0, r[4])]));
D.domain = [Math.floor(Math.min(...ends.flat()) / 500) * 500, Math.ceil(Math.max(...ends.flat()) / 500) * 500];

// ---- shared by the build and the browser (the browser gets these by their source) ----------------------------------

/** Dollars a year from $M, two significant figures: $1.6B, $150M, $5.9M, with a true minus sign. */
function money(m) {
  var a = Math.abs(m), s = m < 0 ? "−" : "";
  if (a === 0) return "$0";
  if (a >= 1000) return s + "$" + (a / 1000).toPrecision(2) + "B";
  return s + "$" + (a < 100 ? a.toPrecision(2) : String(Number(a.toPrecision(2)))) + "M";
}

/** The total and its likely range, as the figure's headline prints them. */
function totalText(cell, n) {
  var t = cell[n];
  return { value: money(t[0]) + " a year", range: "Model range " + money(t[1]) + " to " + money(t[2]) };
}

/** The chart's Plot options for one cell of the grid, at a given width. */
function chartSpec(Plot, D, cell, width) {
  var SW = "#4269d0", EV = "#efb118", n = D.labels.length;
  var deaths = cell[n + 1][0];
  var rows = D.labels.map(function (l, i) {
    return { label: i === 0 ? "Health: " + Number(deaths.toPrecision(2)) + " fewer deaths a year" : l, v: cell[i] };
  });
  var order = rows.map(function (r) { return r.label; });
  var segs = [];
  rows.forEach(function (r) {
    [["People who switch", r.v[3], SW], ["Everyone else", r.v[4], EV]].forEach(function (s) {
      if (s[1] !== 0) segs.push({ y: r.label, x: s[1], who: s[0], fill: s[2], title: r.label.replace(/:.*/, "") + "\n" + s[0] + ": " + money(s[1]) + "\nLikely range for the row: " + money(r.v[1]) + " to " + money(r.v[2]) });
    });
  });
  var ends = rows.map(function (r) {
    var pos = Math.max(0, r.v[3]) + Math.max(0, r.v[4]), neg = Math.min(0, r.v[3]) + Math.min(0, r.v[4]);
    return { y: r.label, x: r.v[0] < 0 ? neg : pos, text: money(r.v[0]), anchor: r.v[0] < 0 ? "end" : "start" };
  });
  var band = 42, phone = width < 560;
  var step = phone ? 2000 : 1000, ticks = [];
  for (var t = Math.ceil(D.domain[0] / step) * step; t <= D.domain[1]; t += step) ticks.push(t);
  var halo = { fill: "#15181c", stroke: "#ffffff", strokeWidth: 4, paintOrder: "stroke" };
  return {
    width: width, height: band * rows.length + 30, marginLeft: 52, marginRight: 46, marginTop: 0, marginBottom: 30,
    x: { domain: D.domain, axis: null },
    y: { domain: order, axis: null, paddingInner: 0, paddingOuter: 0 },
    style: { fontSize: "13px", fontFamily: "inherit", overflow: "visible" },
    marks: [
      Plot.gridX(ticks, { stroke: "#dfe3e9", strokeOpacity: 1, strokeDasharray: "2 4" }),
      Plot.axisX(ticks, { tickSize: 0, tickPadding: 8, tickFormat: function (v) { return v === 0 ? "$0" : (v < 0 ? "\u2212" : "") + "$" + Math.abs(v / 1000) + "B"; }, label: null, fontSize: 12, color: "#59626f" }),
      Plot.barX(segs, { x: "x", y: "y", fill: "fill", insetTop: 22, insetBottom: 6, title: "title", tip: true }),
      Plot.ruleX([0], { stroke: "#15181c", strokeWidth: 1 }),
      Plot.text(rows, Object.assign({ y: "label", frameAnchor: "left", dy: -9, text: "label", textAnchor: "start" }, halo)),
      Plot.text(ends.filter(function (e) { return e.anchor === "start"; }), Object.assign({ x: "x", y: "y", dy: 7, dx: 5, text: "text", textAnchor: "start", fontWeight: 600 }, halo)),
      Plot.text(ends.filter(function (e) { return e.anchor === "end"; }), Object.assign({ x: "x", y: "y", dy: 7, dx: -5, text: "text", textAnchor: "end", fontWeight: 600 }, halo)),
    ],
  };
}

const cellAt = (car, chosen) => D.cells[D.car.indexOf(car)][D.chosen.indexOf(chosen)];
const splitLine = (car) => {
  const s = D.split[D.car.indexOf(car)];
  return `Walk ${Math.round(s.walk)}%, transit ${Math.round(s.transit)}%, bike ${Math.round(s.bike)}%`;
};

const CSS = `<style>
.pb-head, .pb { width: min(1280px, 100vw - 32px); margin-left: calc(50% - min(640px, 50vw - 16px)); }
.pb-head h1 { font-size: clamp(1.25rem, 2.2vw, 1.55rem); margin: 0 0 2px; }
.pb-head .lede { margin: 0 0 6px; font-size: 0.95rem; }
.pb-head .draft-band { background: var(--seq-2-soft); border-left: 3px solid var(--seq-2); padding: 4px 12px; margin: 0 0 10px; font-size: 0.85rem; }
.pb { display: grid; grid-template-columns: 270px minmax(0, 1fr); gap: 24px; align-items: start; }
.pb-ctl label { display: block; font-weight: 600; font-size: 0.95rem; margin: 0 0 2px; }
.pb-ctl .val { font-family: Archivo, sans-serif; font-size: 1.35rem; font-weight: 700; margin: 0; }
.pb-ctl .sub { color: var(--muted); font-size: 0.85rem; margin: 0 0 4px; min-height: 1.3em; }
.pb-ctl input[type=range] { width: 100%; accent-color: var(--ink); margin: 4px 0 0; }
.pb-ctl .ends { display: flex; justify-content: space-between; color: var(--muted); font-size: 0.78rem; margin: 0 0 18px; }
.pb-ctl button { font: inherit; font-size: 0.85rem; border: 1px solid var(--rule); background: var(--paper); color: var(--ink); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.pb-ctl button:hover { background: var(--raised); }
.pb-total { margin: 0 0 6px; }
.pb-total .tot { font-family: Archivo, sans-serif; font-size: 1.6rem; font-weight: 700; margin-right: 10px; }
.pb-total .range { color: var(--muted); font-size: 0.95rem; display: block; }
.pb-key { display: flex; gap: 18px; font-size: 0.88rem; margin: 0 0 4px; }
.pb-key span::before { content: ""; display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; background: var(--c); }
.pb-fig { min-width: 0; }
.pb-fig svg { max-width: 100%; height: auto; display: block; }
.pb-about { margin-top: 28px; }
@media (max-width: 760px) {
  .pb { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .pb-ctl { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
  .pb-ctl .val { font-size: 1rem; white-space: nowrap; }
  .pb-ctl .ends { margin-bottom: 8px; }
  .pb-ctl .reset { grid-column: 1 / -1; margin-bottom: 6px; }
  .pb-ctl .sub { font-size: 0.78rem; min-height: 3.9em; }
}
</style>`;

// Plot's browser build needs d3 loaded first (as on the school trips page).
const PLOT_JS = `<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/dist/plot.umd.min.js" integrity="sha384-JUpn2GgRr0gxU0xOBd8D8P634jhRCwobtG8G2MMEkX1RnGJ7/FJNnuukpfT+H2w1" crossorigin="anonymous"></script>`;

const SCRIPT = `<script>
(function () {
  var D = ${inlineJson(D)};
  ${money.toString()}
  ${totalText.toString()}
  ${chartSpec.toString()}
  var root = document.querySelector("[data-pb]"), fig = root.querySelector("[data-fig]");
  var car = root.querySelector("[data-car]"), chosen = root.querySelector("[data-chosen]");
  function clampTo(list, v, d) { if (v === null || v === "") return d; v = Math.round(+v); return list.indexOf(v) >= 0 ? v : d; }
  var q = new URLSearchParams(location.search);
  car.value = clampTo(D.car, q.get("car"), D.def.car);
  chosen.value = clampTo(D.chosen, q.get("chosen"), D.def.chosen);
  function draw() {
    var c = +car.value, h = +chosen.value, ci = D.car.indexOf(c), s = D.split[ci];
    var cell = D.cells[ci][D.chosen.indexOf(h)], tt = totalText(cell, D.labels.length);
    root.querySelector("[data-car-val]").textContent = c + "% of trips by car";
    root.querySelector("[data-car-sub]").textContent = "Walk " + Math.round(s.walk) + "%, transit " + Math.round(s.transit) + "%, bike " + Math.round(s.bike) + "%";
    root.querySelector("[data-chosen-val]").textContent = h + "% chose to switch";
    root.querySelector("[data-total]").textContent = tt.value;
    root.querySelector("[data-range]").textContent = tt.range;
    root.querySelector("[data-chosen-sub]").textContent = h === 100 ? "Nobody was pushed" : (h === 0 ? "All were" : "The rest were") + " pushed by pricing or streets closed to through traffic";
    if (window.Plot) {
      var el = Plot.plot(chartSpec(Plot, D, cell, fig.clientWidth || 800));
      el.setAttribute("role", "img");
      el.setAttribute("aria-label", "Yearly benefits at " + c + "% of trips by car, with " + h + "% of switchers choosing to switch");
      fig.replaceChildren(el);
    }
    var qs = c === D.def.car && h === D.def.chosen ? "" : "?car=" + c + "&chosen=" + h;
    history.replaceState(null, "", location.pathname + qs);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: qs }));
  }
  car.addEventListener("input", draw);
  chosen.addEventListener("input", draw);
  root.querySelector("[data-reset]").addEventListener("click", function () { car.value = D.def.car; chosen.value = D.def.chosen; draw(); });
  var w = fig.clientWidth;
  window.addEventListener("resize", function () { if (Math.abs(fig.clientWidth - w) > 20) { w = fig.clientWidth; draw(); } });
  draw();
})();
</script>`;

const SOURCES = [
  { label: "WHO Europe, Health Economic Assessment Tool (HEAT) methods and user guide, 2017", href: "https://www.who.int/europe/publications/i/item/9789289052788", read: "2026-11-26" },
  { label: "U.S. Department of Transportation, Benefit-Cost Analysis Guidance for Discretionary Grant Programs, December 2025", href: "https://www.transportation.gov/mission/office-secretary/office-policy/transportation-policy/benefit-cost-analysis-guidance", read: "2026-11-26" },
  { label: "U.S. Department of Transportation, value of a statistical life guidance, 2024 base year", href: "https://www.transportation.gov/office-policy/transportation-policy/revised-departmental-guidance-on-valuation-of-a-statistical-life-in-economic-analysis", read: "2026-11-18" },
  { label: "SFMTA, Travel Decision Survey 2019", href: "https://www.sfmta.com/sites/default/files/reports-and-documents/2020/01/sfmta_travel_decision_survey_2019.pdf", read: "2026-10-20" },
  { label: "California Department of Public Health, death profiles by county, 2024", href: "https://data.chhs.ca.gov/dataset/death-profiles-by-county", read: "2026-11-26" },
  { label: "SFCTA, Congestion Management Program 2025", href: "https://www.sfcta.org/reports/congestion-management-program-2025", read: "2026-11-26" },
  { label: "AAA, Your Driving Costs 2026", href: "https://newsroom.aaa.com/2026/09/aaa-new-vehicle-ownership-costs-hit-12863-annually/", read: "2026-11-26" },
  { label: "DataSF, Traffic Crashes Resulting in Injury: Victims Involved", href: "https://data.sfgov.org/d/nwes-mmgh", read: "2026-10-21" },
];

const A = (href, text) => `<a href="${href}">${text}</a>`;
const HEAT = SOURCES[0].href, BCA = SOURCES[1].href, VSL = SOURCES[2].href, TDS = SOURCES[3].href;

function about() {
  const c = cellAt(30, 0), n = ROWS.length;
  return `<section class="pb-about">
<h2>About the Data</h2>
<p>We value a citywide shift away from car trips once SF's bike network is built, in 2024 dollars per year once the shift has settled. Today 53% of trips to, from and within SF are by car or ride-hail (${A(TDS, "Travel Decision Survey 2019")}). The lower shares are targets we set, not what any street plan is shown to deliver.</p>
<h3>Who Switches</h3>
<p>A switcher is someone who moves a trip out of a car. At 30% by car we move trips to walking 28%, transit 31% and biking 10%, and at 20% to 30%, 35% and 14%. In between and below 20%, each point of car share moves at the same rate as the nearest step.</p>
<h3>Pushed or Chosen</h3>
<p>We assume someone who chooses to switch is no worse off, so their time, driving and parking costs net to zero. Someone pushed by pricing or streets closed to through traffic loses time, at USDOT's $20.10 an hour in a car or on transit and $40.20 walking, biking or waiting (${A(BCA, "USDOT benefit-cost guidance")}, Table A-2). Our research doesn't settle the mix, so the tool opens at 50%.</p>
<h3>Health and the Value of a Life</h3>
<p>WHO's ${A(HEAT, "Health Economic Assessment Tool")} turns minutes walked and biked into fewer deaths, using SF's death rates for adults 25 to 74. USDOT values each death avoided at $13.7M (${A(VSL, "value of a statistical life")}). That's what 100,000 people would pay together, $137 each a year, to cut their own risk of dying by 1 in 100,000, so that one fewer of them dies.</p>
<p>Counted by years of life instead, at about $0.5M a year and 15 to 20 years gained per death, health at 30% by car would be about $1.0B, not ${money(cellAt(30, 50)[0][0])}. That's our rough estimate, which we haven't checked against a published source.</p>
<h3>Who Gets What</h3>
<p>Switchers get the health gain and bear their own time, driving and parking costs, gains or losses. Comfort on new bike lanes is ${A(BCA, "USDOT's")} dollars a mile ridden (Table A-9), split between new riders and today's, who gain even with no shift. Everyone else gets less traffic, cleaner air, less noise and the climate gain, per car mile cut (Table A-14), and the traffic figure is an upper bound.</p>
<p>Most of what switchers save on parking is revenue SFMTA and garage owners lose, so it's their gain but not the city's. Injuries are USDOT's costs by severity on our estimate from ${A(SOURCES[7].href, "SF's crash records")}. Switchers get the change in their own risk, which our model puts as a loss, and everyone else gets fewer people hurt by cars.</p>
<h3>Ranges</h3>
<p>Each bar shows the model with every input at its central value. The model range is the 5th to 95th percentile of 20,000 runs, with each input drawn on its own, so it assumes the inputs don't miss together. At 30% by car with every switch pushed, the total is ${money(c[n][0])} (${money(c[n][1])} to ${money(c[n][2])}).</p>
</section>`;
}

export function render() {
  const cell = cellAt(D.def.car, D.def.chosen);
  const svg = plotSVG(chartSpec(Plot, D, cell, 900), { label: `Yearly benefits at ${D.def.car}% of trips by car, with ${D.def.chosen}% of switchers choosing to switch` });
  const body = `${CSS}
<div class="pb-head">
  <h1>${esc(TITLE)}</h1>
  <p class="lede">What SF would gain each year if car trips fell to a target share with the bike network built, and who gets it. All figures are 2024 dollars.</p>
  <p class="draft-band"><strong>Draft.</strong> Model run ${longDate(D.version)}.</p>
</div>
<div class="pb" data-pb>
  <div class="pb-ctl">
    <div>
      <label for="pb-car" class="val" data-car-val>${D.def.car}% of trips by car</label>
      <p class="sub" data-car-sub>${splitLine(D.def.car)}</p>
      <input id="pb-car" type="range" min="${D.car[0]}" max="${D.car.at(-1)}" step="1" value="${D.def.car}" data-car dir="rtl">
      <div class="ends"><span>${D.today}% today</span><span>${D.car[0]}%</span></div>
    </div>
    <div>
      <label for="pb-chosen" class="val" data-chosen-val>${D.def.chosen}% chose to switch</label>
      <p class="sub" data-chosen-sub>The rest were pushed by pricing or streets closed to through traffic</p>
      <input id="pb-chosen" type="range" min="0" max="100" step="10" value="${D.def.chosen}" data-chosen>
      <div class="ends"><span>0%</span><span>100%</span></div>
    </div>
    <p class="reset"><button type="button" data-reset>Reset</button></p>
  </div>
  <div class="pb-fig">
    <p class="pb-total"><span class="tot" data-total>${esc(totalText(cell, ROWS.length).value)}</span><span class="range" data-range>${esc(totalText(cell, ROWS.length).range)}</span></p>
    <p class="pb-key"><span style="--c:#4269d0">People who switch</span><span style="--c:#efb118">Everyone else</span></p>
    <div data-fig>${svg}</div>
  </div>
</div>
${about()}
${PLOT_JS}
${SCRIPT}`;
  return page({
    title: TITLE,
    description: "What a citywide shift away from car trips is worth to San Francisco each year, in health, time, costs, injuries and cleaner air, and who gets it.",
    path,
    body,
    sources: SOURCES,
  });
}
