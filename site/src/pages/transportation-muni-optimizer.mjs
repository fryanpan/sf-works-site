// The Muni line optimizer answers one question for a resident: what would it take to make my bus come sooner, go
// faster and be less packed, and what would that cost? They pick a line and set three targets, expected wait at the
// stop, bus speed and share of trips crowded, each starting at today's level; the page shows the mix of fixes that
// meets all three for the least spent over ten years, what it costs to build and to run, and on each control what the
// next step would add. tools/muni/muni-ewt/optimizer_build.py evaluates, for each line, every combination of fix levels
// (site/data/muni-optimizer/<YYYY-MM>.json, one file per month of data); the browser picks the combination
// (chooseTargets below, the same rule as optimizer_build.choose_targets).
//
// Bryan, 2026-11-14 (docs/decisions/muni-dashboard.md): "They can pick multiple
// goals using real units", "Actually make it expected wait time, bus speed and
// crowding", "the thing to share is a before and after picture that
// acknowledges we already have some things implemented like weaker signal
// priority", "use SFMTA's crowding figures but mention we'll have more
// accurate ones in a few weeks", and, on a shared link, "Sender's current scenario".
// Bryan, 2026-11-15, replacing the budget buttons and per-fix level chips: "Too complicated -- I
// think let's not have people set budgets. Let's have people change the expected wait time, average bus speed, and
// overcrowding %. Default it to current levels. And depending on the user's setting, find out how much budget it would
// cost to build and run, while minimizing expenditure over 10 years, let's say. And on each control, find some way to
// express how much more expensive it is to improve."
// Bryan, 2026-11-15: "Pretty far from being ready -- please update to support goal-based
// optimiation against 3 goals rather than budget. And cut down all the explanatory text. Figure out what is the
// question residents want to answer when they look at a line?" So the main view holds only the data date, the line,
// one card per goal (the figure the mix delivers, which is also the control, today's, and the next step's cost), the
// cost, the map and its key, and the fixes the mix uses; method and caveats are on About This Data.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import { BASE, CSS, picker, PICKER_SCRIPT, lineName } from "../muni.mjs";

export const path = "/transportation/muni/optimizer";
export const file = "transportation/muni/optimizer/index.html";
// Published as a draft, kept out of the sitemap and every list outside the Muni pages, as the dashboard's other pages
// are (src/muni.mjs DRAFT_NOTE). Bryan, 2026-11-21, on whether the tool is ready for the public: "Yes but mark it
// draft and make sure the front dashboard has links to the line page and upgrade page".
export const sitemap = false;
export const listing = { draft: true, title: "Upgrade a Bus Line", line: "What it would take, and cost, to make a bus come sooner, go faster and be less packed.", order: 3 };

// One results file per month of data, so a shared link keeps its own numbers; the newest is the page's.
const DIR = process.env.OPTIMIZER_DIR || nodePath.join(import.meta.dirname, "..", "..", "data", "muni-optimizer");
const FILES = Object.fromEntries(fs.readdirSync(DIR).filter((f) => /^\d{4}-\d{2}\.json$/.test(f)).sort()
  .map((f) => [f.slice(0, 7), JSON.parse(fs.readFileSync(nodePath.join(DIR, f), "utf8"))]));
const MONTHS_HELD = Object.keys(FILES);
const NOW = MONTHS_HELD.at(-1);
const OPT = FILES[NOW];
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = OPT.dataUpdated;
// bus lines only: trains stay off the picker for now (Bryan, 2026-11-15: "Let's not include trains yet")
const LINES = Object.keys(OPT.lines).filter((l) => OPT.lines[l].kind === "bus");
const DEFAULT_LINE = LINES.includes("22") ? "22" : LINES[0];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const longDate = (d) => `${+d.slice(8, 10)} ${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
const monthSpan = ([a, b]) => `${MONTHS[+a.slice(5, 7) - 1]}${a.slice(0, 4) === b.slice(0, 4) ? "" : ` ${a.slice(0, 4)}`} to ${MONTHS[+b.slice(5, 7) - 1]} ${b.slice(0, 4)}`;
const COL = { built: "#4269d0", added: "#efb118", route: "#9498a0", removed: "#15181c" }; // Observable 10's first two for built against added; a removed stop is a hollow ink ring

// ---- the chooser: pure functions, used in the browser (by their source) and by the tests ---------------------------

/** Round each cost to the thousand so they add to the total rounded to the thousand (optimizer_build.thousands). */
export function thousands(costs) {
  var total = Math.round(costs.reduce(function (a, b) { return a + b; }, 0) / 1000) * 1000;
  var fl = costs.map(function (c) { return Math.floor(c / 1000) * 1000; });
  var rest = (total - fl.reduce(function (a, b) { return a + b; }, 0)) / 1000;
  var order = costs.map(function (c, k) { return k; }).sort(function (a, b) { return (costs[b] - fl[b]) - (costs[a] - fl[a]) || a - b; });
  for (var i = 0; i < Math.max(0, rest); i++) fl[order[i]] += 1000;
  return fl;
}
/** The figure the page shows: one decimal, half up; crowding in whole percents. */
export function r1(v) { return Math.floor(v * 10 + 0.5) / 10; }
export function shownPct(c) { return Math.floor(c * 100 + 0.5); }
/** A figure in whole tenths as the page shows it, so a target compares as an integer (optimizer_build.tenth). */
export function tenth(v) { return Math.floor(v * 10 + 0.5); }
/** The line's mixes, one per combination of fix levels, from the shipped grid, in optimizer_build.all_mixes' order
 *  (the last fix changing fastest): [ten-year cost, units, wait, mph, crowd (low, middle, high each, or null), added
 *  walk, gain, build cost, running cost a year, level]. Each fix is priced from its units with thousands(), as the
 *  build checks; the build cost is the first build, and the ten-year cost counts each fix's build once for each time
 *  it is built in the ten years (f.builds, two for paint); the level is the middle case as the controls count it, [wait and mph in tenths, crowding in points]
 *  (optimizer_build.line_mixes). */
export function expand(x) {
  if (x.mixes) return x;
  var fx = x.fixes, G = x.grid, n = G.gain.length, out = [];
  function tri(s, i) { return s ? [s[0][i], s[1][i], s[2][i]] : null; }
  function add(a) { return a.reduce(function (p, q) { return p + q; }, 0); }
  for (var i = 0; i < n; i++) {
    var u = [], r = i;
    for (var k = fx.length - 1; k >= 0; k--) { var L = fx[k].units.length; u[k] = fx[k].units[r % L]; r = Math.floor(r / L); }
    var bp = thousands(fx.map(function (f, k) { return u[k] * f.unitUp; }));
    var b = add(bp), b10 = add(bp.map(function (p, k) { return p * (fx[k].builds || 1); }));
    var rn = add(thousands(fx.map(function (f, k) { return u[k] * f.unitRun; })));
    var w = tri(G.wait, i), s = tri(G.mph, i), c = tri(G.crowd, i);
    out.push([b10 + (x.years || 10) * rn, u, w, s, c, G.walk[i], G.gain[i], b, rn, [w ? tenth(w[1]) : null, tenth(s[1]), c ? shownPct(c[1]) : null]]);
  }
  x.mixes = out;
  return x;
}
/** The mix with exactly these units (one level from each fix's list), or -1. */
export function mixIndex(x, u) {
  if (!u || u.length !== x.fixes.length) return -1;
  var i = 0;
  for (var k = 0; k < u.length; k++) { var j = x.fixes[k].units.indexOf(u[k]); if (j < 0) return -1; i = i * x.fixes[k].units.length + j; }
  return i;
}
/** Steps a level falls short of targets t = [wait, mph, crowd] (tenths, tenths, points; null for none). */
export function shortfall(lv, t) {
  var s = 0;
  if (t[0] != null && lv[0] != null) s += Math.max(0, lv[0] - t[0]);
  if (t[1] != null && lv[1] != null) s += Math.max(0, t[1] - lv[1]);
  if (t[2] != null && lv[2] != null) s += Math.max(0, lv[2] - t[2]);
  return s;
}
/** The targets' mix: every target met for the least ten-year cost (ties: more time saved, then the first); where
 *  none meets them all, the smallest shortfall first (optimizer_build.choose_targets). */
export function chooseTargets(x, t) {
  var best = -1, bs = 0;
  x.mixes.forEach(function (m, i) {
    var s = shortfall(m[9], t), b = best < 0 ? null : x.mixes[best];
    if (!b || s < bs || (s === bs && (m[0] < b[0] || (m[0] === b[0] && m[6] > b[6])))) { best = i; bs = s; }
  });
  return { k: best, met: bs === 0 };
}
/** Each control's reachable levels at least as good as today's (the no-fix mix, first), today's first. */
export function targetOptions(x) {
  var t = x.mixes[0][9];
  return [0, 1, 2].map(function (g) {
    if (t[g] == null) return [];
    var seen = {}, out = [];
    x.mixes.forEach(function (m) { var v = m[9][g]; if (v != null && !seen[v] && (g === 1 ? v >= t[g] : v <= t[g])) { seen[v] = 1; out.push(v); } });
    return out.sort(function (a, b) { return g === 1 ? a - b : b - a; });
  });
}
/** The next reachable step on control g past targets t, and what it adds over ten years: [step, cost], or null
 *  (optimizer_build.next_step). */
export function nextStep(x, t, g) {
  var nxt = targetOptions(x)[g].filter(function (v) { return g === 1 ? v > t[g] : v < t[g]; })[0], now = chooseTargets(x, t);
  if (nxt == null || !now.met) return null;
  var t2 = t.slice(); t2[g] = nxt;
  var r = chooseTargets(x, t2);
  return r.met ? [Math.abs(nxt - t[g]), x.mixes[r.k][0] - x.mixes[now.k][0]] : null;
}

// ---- the share picture's line drawing, drawn here so the browser only shows or hides its parts ------------------------


/** A small SVG of the line: route, lanes and signals built today, and every fix's place, each part tagged for toggling. */
function drawing(m, W = 260, H = 200) {
  if (!m) return "";
  const pts = m.shape.flat().concat(m.lanes.flat(), m.newLanes.flatMap((l) => l.c), m.bulbs, (m.removed || []).map((r) => r.c));
  const lon = pts.map((p) => p[0]), lat = pts.map((p) => p[1]);
  const k = Math.cos((37.76 * Math.PI) / 180);
  const x0 = Math.min(...lon), x1 = Math.max(...lon), y0 = Math.min(...lat), y1 = Math.max(...lat);
  const s = Math.min((W - 16) / ((x1 - x0) * k || 1e-6), (H - 16) / (y1 - y0 || 1e-6));
  const ox = (W - (x1 - x0) * k * s) / 2, oy = (H - (y1 - y0) * s) / 2;
  const P = ([x, y]) => [ox + (x - x0) * k * s, H - oy - (y - y0) * s];
  const d = (line) => {
    let out = "", last = null;
    for (const c of line) {
      const [px, py] = P(c).map((v) => Math.round(v * 2) / 2);
      if (last && last[0] === px && last[1] === py) continue;
      out += `${out ? "L" : "M"}${px} ${py}`;
      last = [px, py];
    }
    return out;
  };
  // signal dots get no white edge, so on a lane they don't read as the hollow ring that means a removed stop
  const dot = (c, r, fill, attrs = "", edge = true) => { const [px, py] = P(c).map((v) => v.toFixed(1)); return `<circle cx="${px}" cy="${py}" r="${r}" fill="${fill}"${edge ? ' stroke="#fff" stroke-width="0.8"' : ""}${attrs}/>`; };
  // a lane on a narrow street, in its only general lane, is dashed
  const newLanes = m.newLanes.map((l) => `<path d="${d(l.c)}" data-m0="${l.m0}" class="pic-new"${l.g ? ' stroke-dasharray="3 3"' : ""}/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
${m.shape.map((l) => `<path d="${d(l)}" stroke="${COL.route}" stroke-width="2"/>`).join("")}
<g stroke="${COL.added}" stroke-width="4.5" class="pic-after">${newLanes}</g>
<g stroke="${COL.built}" stroke-width="3">${m.lanes.map((l) => `<path d="${d(l)}"/>`).join("")}</g>
</g>
<g>${m.tsp.map((c) => dot(c, 1.8, COL.built, "", false)).join("")}</g>
<g class="pic-after pic-tsp">${m.open.map((c) => dot(c, 1.8, COL.added, "", false)).join("")}</g>
<g class="pic-after">${m.bulbs.map((c, i) => dot(c, 3, COL.added, ` data-rank="${i}" class="pic-bulb"`)).join("")}</g>
<g class="pic-after pic-stops" fill="#fff" stroke="${COL.removed}" stroke-width="1.2">${(m.removed || []).map((r) => { const [px, py] = P(r.c).map((v) => v.toFixed(1)); return `<circle cx="${px}" cy="${py}" r="2.6"/>`; }).join("")}</g>
</svg>`;
}

// ---- how the line has changed -------------------------------------------------------------------------------------

const ym = (m) => new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, 15));
const mi = (m) => +m.slice(0, 4) * 12 + +m.slice(5, 7);
const SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Small monthly charts since the earliest month we have: the line's timetable (buses in service at the busiest time,
 *  minutes between buses weekdays, evenings and weekends), its weekday riders, and its wait, speed and crowding. The
 *  line's dated service changes and projects (interventions.csv) are numbered on every chart's time axis and listed
 *  once above them. Bryan, 2026-11-16, on the 44: "update it so that it shows service increases over time ... like if
 *  there's changes to the schedule or a number of buses", then "show changes over
 *  time in number of busses serving the line, and also changes over time in scheduled frequency during daytime and off
 *  hours" and "How many people ride this line each day?" */
function historyCharts(f, x) {
  const T = x.history.trend, months = f.trendMonths;
  const d0 = ym(months[0]), d1 = ym(months.at(-1));
  const start = new Date(Date.UTC(+months[0].slice(0, 4), +months[0].slice(5, 7) - 1, 1));
  const end = new Date(Date.UTC(+months.at(-1).slice(0, 4), +months.at(-1).slice(5, 7), 0));
  const when = (p) => p.date.length > 7 ? new Date(Date.UTC(+p.date.slice(0, 4), +p.date.slice(5, 7) - 1, +p.date.slice(8, 10))) : ym(p.date);
  const changes = (x.history.projects || []).filter((p) => when(p) >= start && when(p) <= end)
    .map((p, k) => ({ ...p, n: k + 1, d: when(p) < d0 ? d0 : when(p) > d1 ? d1 : when(p) }));
  // a month with no figure, or a gap in the months we have, breaks the line rather than bridging it
  //   the timetable and riders run every month (f.allMonths), the 511 stop-record series only the usable ones
  const SCHED = { day: 1, eve: 1, wknd: 1, buses: 1, riders: 1 };
  const rowsOf = (key) => {
    const rows = [], ms = SCHED[key] && f.allMonths ? f.allMonths : months;
    ms.forEach((m, i) => {
      if (i && mi(m) - mi(ms[i - 1]) > 1) rows.push({ d: ym(ms[i - 1]), v: NaN });
      rows.push({ d: ym(m), v: T[key] && T[key][i] != null ? T[key][i] : NaN });
    });
    return rows;
  };
  // every chart has the same width, margins and time domain, so a month sits at the same x in all six (Bryan,
  //   2026-11-16: "Make sure all of the horizontal axes line up ... we want the trends to be
  //   comparable"); the right margin holds the timetable chart's line names
  // series: [[key, name, colour, dash]], a dash where one line can sit on another (weekends on weekdays); a chart of one series names nothing at its end, a chart of several names each
  //   line and prints its newest figure there (labels closer than 11px pushed apart)
  const panel = (series, label, o = {}) => {
    const all = series.map(([key, name, c, dash]) => ({ name, c, dash, rows: rowsOf(key) }));
    const vs = all.flatMap((a) => a.rows.filter((r) => Number.isFinite(r.v)).map((r) => r.v));
    if (vs.length < 2) return "";
    const lo = o.zero ? 0 : o.pct ? 0 : Math.floor(Math.min(...vs) * 0.9);
    const hi = o.pct ? Math.max(0.05, Math.ceil(Math.max(...vs) * 100 + 1) / 100) : o.zero ? Math.ceil(Math.max(...vs) * 1.15) : Math.ceil(Math.max(...vs) * 1.05);
    const H = 140, mt = 14, mb = 22, unit = (H - mt - mb) / (hi - lo || 1), many = all.length > 1;
    const ends = all.map((a) => ({ ...a, last: a.rows.filter((r) => Number.isFinite(r.v)).at(-1) })).filter((a) => a.last).sort((a, b) => b.last.v - a.last.v);
    ends.forEach((e, k) => { e.y = e.last.v; if (k && (ends[k - 1].y - e.y) * unit < 11) e.y = ends[k - 1].y - 11 / unit; });
    return `<figure class="op-hfig"><figcaption>${esc(label)}</figcaption>${plotSVG({
      width: 360, height: H, marginLeft: 38, marginRight: 80, marginTop: mt, marginBottom: mb, style: { fontSize: 11 },
      x: { type: "utc", domain: [d0, d1], ticks: 4, label: null, tickSize: 0 },
      y: { domain: [lo, hi], ticks: 3, label: null, tickSize: 0, grid: true, tickFormat: o.pct ? (v) => `${Math.round(v * 100)}%` : o.k ? (v) => (v >= 1000 ? `${v / 1000}K` : String(v)) : undefined },
      marks: [
        Plot.ruleX(changes, { x: "d", stroke: "var(--muted)", strokeOpacity: 0.55, strokeDasharray: "2 3" }),
        Plot.text(changes, { x: "d", y: hi, text: (c) => String(c.n), dy: -8, fill: "var(--muted)", fontSize: 10 }),
        ...ends.flatMap((e) => [
          Plot.line(e.rows, { x: "d", y: "v", stroke: e.c, strokeWidth: 1.6, strokeDasharray: e.dash, curve: o.step ? "step-after" : "linear" }),
          Plot.dot([e.last], { x: "d", y: "v", fill: e.c, r: 2.5 }),
          ...(many ? [Plot.text([e], { x: (q) => q.last.d, y: "y", text: (q) => `${q.name} ${o.fmt ? o.fmt(q.last.v) : q.last.v}`, fill: e.c, textAnchor: "start", dx: 6 })] : []),
        ]),
      ],
    }, { className: "op-hplot", label: `${label}, ${lineName(x.line || "")} by month, ${monthSpan([months[0], months.at(-1)])}.` })}</figure>`;
  };
  const list = changes.length ? `<ol class="op-hchanges">${changes.map((c) => `<li value="${c.n}">${SHORT[+c.date.slice(5, 7) - 1]} ${c.date.slice(0, 4)}: ${c.url ? `<a href="${esc(c.url)}">${esc(c.text)}</a>` : esc(c.text)}</li>`).join("")}</ol>` : "";
  const whole = (v) => String(Math.floor(v + 0.5));
  return list
    + panel([["buses", "Buses", "var(--seq-3)"]], "Buses in service at the busiest time, weekdays", { zero: true, step: true })
    + panel([["day", "Weekdays", "var(--seq-3)"], ["eve", "Evenings", "var(--seq-2)"], ["wknd", "Weekends", "var(--seq-1)", "4 3"]], "Minutes between buses (timetable)", { zero: true, step: true, fmt: whole })
    + panel([["riders", "Riders", "var(--seq-3)"]], "Riders a weekday (SFMTA)", { zero: true, k: true })
    + panel([["wait", "Wait", "var(--seq-3)"]], "Expected wait (min)")
    + panel([["mph", "Speed", "var(--seq-3)"]], "Speed (mph)")
    + panel([["crowd", "Crowded", "var(--seq-3)"]], "Crowded trips (SFMTA)", { pct: true });
}

/** One line's data for the page: the results, its drawing, name and charts, from one month's file. */
function lineData(month, line) {
  const f = FILES[month], x = f.lines[line];
  const { history, ...rest } = x;
  return { ...rest, line, month, years: f.years, name: lineName(line), pic: drawing(x.map), charts: historyCharts(f, { ...x, line }) };
}

// ---- page ---------------------------------------------------------------------------------------------------------

// One card per goal: the figure the chosen mix delivers, large, with steps either side that move the goal; under it
//   today's figure and what the next step better would add. better: which button improves it (wait and crowding go
//   down, speed goes up).
const TARGETS = [
  { id: "wait", label: "Expected wait", better: "dn", dn: "Shorter wait", up: "Longer wait" },
  { id: "mph", label: "Bus speed", better: "up", dn: "Slower", up: "Faster" },
  { id: "crowd", label: "Crowded trips", better: "dn", dn: "Fewer crowded trips", up: "More crowded trips" },
];

function controls() {
  const d0 = lineData(NOW, DEFAULT_LINE);
  return `<div class="op-ctl">
<div class="op-pick">${picker({ id: "op-line", value: lineName(DEFAULT_LINE), lines: LINES, label: "Your line" })}
<p class="op-sched">${esc(d0.schedule ? d0.schedule.text : "")}</p></div>
<div class="op-cards" aria-live="polite">${TARGETS.map((g, k) => `<div class="op-card" data-fig="${g.id}" data-g="${k}">
<div class="op-card-lab">${g.label}</div>
<div class="op-step">
<div class="op-side"><button type="button" class="op-btn" data-g="${k}" data-d="dn" aria-label="${g.dn}">\u2212</button><span class="op-tag" data-d="dn"></span></div>
<div class="op-mid"><output class="op-card-val"></output><span class="op-card-now"></span></div>
<div class="op-side"><button type="button" class="op-btn" data-g="${k}" data-d="up" aria-label="${g.up}">+</button><span class="op-tag" data-d="up"></span></div>
</div>
</div>`).join("")}</div>
<button type="button" class="op-reset">Reset to today</button>
<p class="op-metro" hidden>Trains get no fixes here yet; these are today's figures.</p>
</div>`;
}

function figures() {
  return `<div class="op-fig" aria-live="polite">
<p class="op-past" hidden></p>
<div class="op-fixbox">
<div class="op-total"></div>
<p class="op-reach" hidden></p>
<ul class="op-fixes"></ul>
<p class="op-left" hidden></p>
<button type="button" class="op-share-btn" aria-expanded="false">Before and after</button>
<dialog class="op-share" aria-label="Before and after picture">
<p class="op-swipe">Swipe sideways for the numbers.</p>
<div class="op-pic"></div>
<div class="op-share-acts"><button type="button" class="op-png">Download picture</button> <button type="button" class="op-copy">Copy link</button> <span class="op-copied" hidden>Link copied</span>
<input class="op-link" type="text" readonly hidden aria-label="Link to this scenario"> <button type="button" class="op-close">Close</button></div>
</dialog>
</div>
</div>`;
}

function body() {
  const d = lineData(NOW, DEFAULT_LINE);
  return `${CSS}${PAGE_CSS}
<div class="op-head"><h1>Upgrade a Bus Line <span class="tag">Draft</span></h1>
<p class="op-updated">Data updated ${esc(longDate(OPT.dataUpdated))} · <a href="${BASE}/about#optimizer">How we estimate this</a></p>
</div>
<div class="op">
${controls()}
<div class="op-mapcol">
<div class="glmap op-map" role="img" aria-label="Map of the line with its bus lanes and signal priority today and where the fixes go"></div>
<p class="key-line op-key"><span class="op-k"><i class="op-kl" style="background:${COL.built}"></i><span class="op-k-lane">Bus lane today</span></span><span class="op-k op-k-bus"><i class="op-kd" style="background:${COL.built}"></i>signal priority today</span><span class="op-k op-k-opt op-k-bb" hidden><i class="op-kb" style="background:${COL.built}"></i>bulbs today</span><span class="op-k op-k-opt op-k-bi" hidden><i class="op-kb op-ki" style="background:${COL.built}"></i>boarding islands today</span><span class="op-k op-k-bus"><i class="op-kl" style="background:${COL.added}"></i>Added: side bus lanes</span><span class="op-k op-k-bus"><i class="op-kd" style="background:${COL.added}"></i>signal priority</span><span class="op-k op-k-bus"><i class="op-kb" style="background:${COL.added}"></i>bulbs</span><span class="op-k op-k-bus"><i class="op-kr"></i>stops removed</span></p>
</div>
${figures()}
</div>
<section class="op-history">
<h2>How this line has changed</h2>
<div class="op-hcharts">${d.charts}</div>
</section>
<script type="application/json" id="op-data">${inlineJson({ defaultLine: DEFAULT_LINE, lines: LINES, month: NOW, months: MONTHS_HELD, crowdSpan: OPT.crowdMonths ? monthSpan(OPT.crowdMonths) : "", first: d, col: COL, underSfmta: (OPT.ontimeCheck || []).some((c) => c.sfmta - c.ours >= 0.01) })}</script>
${PICKER_SCRIPT}${MAP_HEAD}${SCRIPT}`;
}

const PAGE_CSS = `<style>
/* the header kept to two short rows, so the cards, cost and fixes fit one laptop screen */
.masthead { margin-bottom: 8px !important; }
.op-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 16px; margin: 0 0 8px; }
.op-updated { margin: 0; font-size: 0.85rem; color: var(--muted); }
.op-head h1 { font-size: 1.5rem; margin: 0; }
.op-head h1 .tag { font-family: "Public Sans", sans-serif; font-size: 0.75rem; vertical-align: middle; color: var(--muted); background: var(--raised); }
/* the line's basic timetable, right under the line picker (optimizer_build.schedule_text) */
.op-sched { margin: 3px 0 0; font-size: 0.85rem; line-height: 1.3; color: var(--muted); }
.op-sched:empty { display: none; }
.op { display: grid; grid-template-columns: 250px minmax(0, 1fr) 340px; gap: 16px; align-items: start;
  width: min(1320px, 100vw - 32px); margin-left: calc(50% - min(660px, 50vw - 16px)); }
.op-ctl { display: flex; flex-direction: column; gap: 3px; }
.op-ctl .lp { margin: 0 0 2px; flex: none; max-width: none; }
.op-ctl .lp input { width: 100%; box-sizing: border-box; }
.op-ctl .lp-label { position: static; font-size: 0.85rem; font-weight: 600; display: block; margin: 0 0 3px; }
.op-reset { font: inherit; font-size: 0.85rem; align-self: flex-start; margin-top: 4px; padding: 3px 10px; border: 1px solid var(--rule); border-radius: 4px; background: var(--paper); color: var(--ink); cursor: pointer; }
.op-metro { font-size: 0.85rem; color: var(--muted); margin: 10px 0 0; }
.op-metro[hidden], .op-past[hidden], .op-reach[hidden] { display: none; }
.op-map { height: max(380px, 100vh - 300px); max-height: 580px; }
.op-key { font-size: 0.82rem; margin: 6px 0 0; color: var(--muted); display: flex; flex-wrap: wrap; gap: 2px 10px; }
.op-k { white-space: nowrap; }
/* on-map callouts name each kind of fix the mix adds, beside the key (Bryan, 2026-11-16) */
.op-call { font: 600 11px/1.2 system-ui, sans-serif; color: #15181c; background: #fff; border: 1px solid #15181c; border-left: 4px solid ${COL.added}; border-radius: 3px; padding: 2px 5px; white-space: nowrap; pointer-events: none; box-shadow: 0 1px 2px rgba(0,0,0,0.2); }
.op-k[hidden] { display: inline; visibility: hidden; } /* bus-only keys keep their space on trains, so the key does not rewrap */
.op-k i { display: inline-block; vertical-align: middle; margin: 0 4px 1px 0; }
.op-kl { width: 14px; height: 5px; border-radius: 2px; }
.op-kd { width: 6px; height: 6px; border-radius: 50%; }
.op-kb { width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 0 1px #15181c inset; }
.op-ki { box-shadow: 0 0 0 2px #fff inset, 0 0 0 1px ${COL.built}; } /* an island: the built blue with a white ring */
.op-k.op-k-opt[hidden] { display: none; } /* shown only where the line has one */
.op-kr { width: 8px; height: 8px; border-radius: 50%; background: #fff; box-shadow: 0 0 0 1.5px #15181c inset; }
.op-past { margin: 0 0 6px; font-size: 0.85rem; background: var(--seq-2-soft); padding: 4px 8px; border-radius: 4px; }
/* one card per goal: the figure the mix delivers is the control, with a step either side */
.op-cards { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
.op-card { border: 1px solid var(--rule); border-radius: 6px; padding: 5px 8px 6px; }
.op-card-lab { font-size: 0.85rem; font-weight: 600; line-height: 1.25; }
/* each step button carries what it costs a year beneath it, or a mark that hovers the reason it can't go further
   (Bryan, 2026-11-16); today's figure sits beneath the value */
.op-step { display: flex; align-items: flex-start; gap: 6px; margin: 2px 0 1px; }
.op-side, .op-mid { display: flex; flex-direction: column; align-items: center; }
.op-tag { font-size: 0.72rem; color: var(--muted); line-height: 1.3; white-space: nowrap; min-height: 1.3em; }
.op-tag[hidden] { display: none; }
.op-nope { cursor: help; font-size: 0.9rem; }
.op-card-val { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.5rem; line-height: 1.2; white-space: nowrap; min-width: 4.6em; text-align: center; }
.op-btn { font: inherit; font-size: 1.2rem; line-height: 1; width: 34px; height: 34px; padding: 0; border: 1px solid var(--ink); border-radius: 50%; background: var(--paper); color: var(--ink); cursor: pointer; flex: none; }
.op-btn:disabled { border-color: var(--rule); color: var(--rule); cursor: default; }
.op-btn[hidden] { display: none; }
.op-train .op-card-val { min-width: 0; text-align: left; }
.op-card-now { font-size: 0.72rem; color: var(--muted); line-height: 1.3; white-space: nowrap; }
.op-fixbox { margin-top: 0; }
.op-fixbox[hidden] { display: none; }
.op-total p { margin: 0; }
.op-cost { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.5rem; line-height: 1.2; }
.op-cost-sub { font-size: 0.88rem; color: var(--muted); line-height: 1.35; }
.op-reach { font-size: 0.95rem; font-weight: 600; margin: 6px 0 0; line-height: 1.35; }
.op-fixes { margin: 8px 0 0; padding-left: 18px; font-size: 0.88rem; line-height: 1.35; }
.op-fixes li { margin: 0 0 4px; }
.op-fixes:empty { display: none; }
.op-left { margin: 6px 0 0; font-size: 0.78rem; color: var(--muted); line-height: 1.35; }
.op-left[hidden] { display: none; }
.op-more { font: inherit; font-size: 0.8rem; color: var(--ink); background: none; border: 0; padding: 0 2px; text-decoration: underline; text-decoration-color: var(--muted); text-underline-offset: 2px; cursor: pointer; white-space: nowrap; }
.op-fix-note { display: block; margin: 2px 0 0; font-size: 0.78rem; color: var(--muted); }
.op-fix-note[hidden] { display: none; }
.op-link[hidden] { display: none; }
.op-link { font: inherit; font-size: 0.8rem; width: 100%; box-sizing: border-box; padding: 3px 5px; border: 1px solid var(--rule); border-radius: 4px; }
.op-share-btn, .op-copy, .op-png { font: inherit; font-size: 0.9rem; padding: 6px 12px; border: 1px solid var(--ink); border-radius: 4px; background: var(--paper); color: var(--ink); cursor: pointer; }
.op-share-btn { font-weight: 600; padding: 3px 10px; font-size: 0.85rem; white-space: nowrap; margin-top: 8px; }
/* the picture opens full size in a dialog the reader asked for, so it is readable and the page doesn't scroll */
.op-share { border: 0; border-radius: 8px; padding: 12px; width: min(920px, 96vw); max-height: 94vh; box-sizing: border-box; }
.op-share::backdrop { background: rgba(21, 24, 28, 0.45); }
.op-pic svg { width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 4px; display: block; }
.op-close { font: inherit; font-size: 0.9rem; padding: 6px 12px; border: 1px solid var(--rule); border-radius: 4px; background: var(--paper); color: var(--ink); cursor: pointer; margin-left: auto; }
.op-share-acts { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.op-copied { font-size: 0.85rem; color: var(--seq-3); }
.op-swipe { display: none; font-size: 0.85rem; color: var(--muted); margin: 0 0 6px; }
.op-history { margin-top: 28px; }
.op-history h2 { font-size: 1.25rem; margin: 0 0 8px; }
.op-hcharts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.op-hfig { margin: 0; }
.op-hfig figcaption { font-size: 0.82rem; font-weight: 600; margin-bottom: 2px; }
.op-hplot { max-width: 100%; height: auto; }
/* the line's dated changes, numbered as on the buses-an-hour chart */
.op-hchanges { grid-column: 1 / -1; margin: 0; padding-left: 20px; font-size: 0.8rem; line-height: 1.35; color: var(--muted); }
.op-hchanges li { margin: 0 0 2px; }
@media (max-width: 1100px) {
  .op { grid-template-columns: 240px minmax(0, 1fr); width: auto; margin-left: 0; }
  .op-fig { grid-column: 1 / -1; }
}
@media (max-width: 700px) {
  /* phones (tool UX rule 12): the line, then a map twice as wide as tall and the cards, so the first screen holds the
     map and the controls and a scroll down holds the controls and the cost (Bryan, 2026-11-16);
     every tap target at least 44px */
  .op { display: flex; flex-direction: column; align-items: stretch; gap: 8px; }
  .op-ctl, .op-fig { display: contents; }
  .op-past { order: 0; }
  .op-pick { order: 1; }
  .op-mapcol { display: contents; }
  .op-map { order: 2; }
  .op-cards, .op-reset, .op-metro { order: 3; margin-top: 0; }
  .op-reset { min-height: 44px; }
  .op-key { order: 4; margin: 0; }
  .op-fixbox { order: 5; }
  /* a card is one row: the label and today's figure on the left, the steps and the figure on the right */
  .op-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; column-gap: 8px; padding: 4px 8px; }
  .op-card-lab { grid-column: 1; grid-row: 1; }
  .op-step { grid-column: 2; grid-row: 1; margin: 0; }
  .op-card-val { font-size: 1.35rem; min-width: 4.2em; }
  .op-btn { width: 44px; height: 44px; }
  .op-cost { font-size: 1.35rem; }
  .op-head h1 { font-size: 1.25rem; }
  .op-head { margin-bottom: 4px; }
  /* the box says "Type a line" and holds the line's name, so the label is for screen readers only here */
  .op-ctl .lp-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .op-updated, .op-sched { font-size: 0.8rem; }
  .op-more { min-height: 44px; padding: 0 6px; font-size: 0.85rem; }
  .op-map { height: auto; aspect-ratio: 2 / 1; min-height: 0; max-height: none; }
  /* a short map has no room for the zoom buttons; pinch zooms, and Reset and full screen stay */
  .op .glmap.op-map .maplibregl-ctrl-group:has(.maplibregl-ctrl-zoom-in) { display: none; }
  .op-pic { overflow-x: auto; }
  .op-swipe { display: block; }
  .op-pic > svg { width: 640px; max-width: none; } /* readable text; pan sideways */
  .op-share-btn, .op-png, .op-copy, .op-close { min-height: 44px; }
  .op .glmap.op-map .maplibregl-ctrl-group button { width: 44px; height: 44px; }
  .op .glmap.op-map .sf-reset button { width: auto; min-width: 56px; }
  /* this page only: the masthead's Share and Feedback buttons reach 44px too */
  .masthead .share-btn { min-height: 44px; min-width: 44px; }
}
</style>`;

// The browser's part: set the three targets, pick the cheapest mix over ten years that meets them, and show it.
const SCRIPT = `<script>
(function () {
  ${thousands.toString()}
  ${r1.toString()}
  ${shownPct.toString()}
  ${tenth.toString()}
  ${expand.toString()}
  ${mixIndex.toString()}
  ${shortfall.toString()}
  ${chooseTargets.toString()}
  ${targetOptions.toString()}
  ${nextStep.toString()}
  var D = JSON.parse(document.getElementById("op-data").textContent), COL = D.col, UNDER_SFMTA = D.underSfmta;
  var base = location.pathname.replace(/\\/optimizer\\/?$/, "");
  var cache = {}; cache[D.month + "/" + D.first.line] = expand(D.first);
  var FIGS = ["wait", "mph", "crowd"];
  // t: the three targets (wait and mph in tenths, crowding in points), null until the line loads (today's then);
  //   pin: an older link's fix levels, shown as they were until a target changes
  var st = { line: D.first.line, month: D.month, t: null, pin: null, budget: null };
  var MON = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  function monthName(m) { return MON[+m.slice(5, 7) - 1] + " " + m.slice(0, 4); }
  function money(n) { return n >= 1e6 ? "$" + Number((n / 1e6).toPrecision(2)) + "M" : n >= 1e3 ? "$" + Number((n / 1e3).toPrecision(2)) + "K" : "$" + n; }
  function fmt(g, v) { return v == null ? "No figure" : g === "wait" ? r1(v).toFixed(1) + " min" : g === "mph" ? r1(v).toFixed(1) + " mph" : shownPct(v) + "%"; }
  // a target as the control shows it: tenths of a minute or mph, or whole percents
  function tfmt(g, v) { return g === 2 ? v + "%" : (v / 10).toFixed(1) + (g === 0 ? " min" : " mph"); }
  function stepText(g, d) { return g === 2 ? d + (d === 1 ? " point" : " points") : (d / 10).toFixed(1) + (g === 0 ? " min" : " mph"); }
  function short(n) { return n.replace(/ (Street|Avenue|Boulevard|Drive|Way|St|Ave|Blvd|Dr)$/, ""); }
  function list(a) { var b = a.filter(function (v, i) { return a.indexOf(v) === i; }); return b.length > 1 ? b.slice(0, -1).join(", ") + " and " + b[b.length - 1] : b[0] || ""; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  // the miles that take a traffic lane, the miles that take parking and the miles that take a narrow street's only
  //   traffic lane, with their streets (pre-send R5-5; Bryan, 2026-11-15)
  function laneSplit(x, u) {
    var parts = (x.notes && x.notes.laneParts || []).filter(function (p) { return p[0] < u; }), tot = 0, by = { travel: {}, parking: {}, general: {} }, mi = { travel: 0, parking: 0, general: 0 };
    parts.forEach(function (p) { tot += p[3]; });
    if (!tot) return "";
    parts.forEach(function (p) { var v = p[3] * u / tot; mi[p[2]] += v; by[p[2]][p[1]] = (by[p[2]][p[1]] || 0) + v; });
    function streets(k) { return list(Object.keys(by[k]).sort(function (a, b) { return by[k][b] - by[k][a]; }).slice(0, 3).map(short)); }
    var out = [];
    if (mi.travel >= 0.05) out.push(mi.travel.toFixed(1) + " miles in a traffic lane on " + streets("travel"));
    if (mi.parking >= 0.05) out.push(mi.parking.toFixed(1) + " miles in place of parking on " + streets("parking"));
    if (mi.general >= 0.05) out.push(mi.general.toFixed(1) + " miles taking the only traffic lane on " + streets("general"));
    return out.join(", ");
  }
  // a fix as the list names it, with its level
  function unitsText(x, f, u) {
    if (f.id === "lane") return u + (u === 1 ? " mile" : " miles") + " of side bus lanes";
    if (f.id === "more") return u + (u === 1 ? " more bus" : " more buses");
    if (f.id === "tsp") return "Signal priority at " + f.signals + " more signals";
    if (f.id === "stops") return "Remove " + f.removed + " of " + x.built.stops + " stops";
    if (f.id === "bulb") return u + " bus bulbs or boarding islands";
    if (f.id === "hold") return "Hold buses to even out gaps at rush hour";
    if (f.id === "fill") return "Run the trips that don't run";
    return f.label;
  }
  // the stops removed, by name, so a rider can see which stops the ask includes
  function stopNames(x) {
    var seen = {}, out = [];
    (x.map && x.map.removed || []).forEach(function (r) { var n = r.n.replace(/ (St|Ave|Blvd|Way|Dr)\\b/g, ""); if (!seen[n]) { seen[n] = []; out.push(n); } seen[n].push(r.b); });
    return out.map(function (n) { return n + " (" + seen[n].join(" and ") + ")"; }).join(", ");
  }
  // where a fix goes, behind a tap: the lanes' streets and the stops removed
  function fixNote(x, f, u) {
    if (f.id === "lane") { var t = laneSplit(x, u); t = t ? t.charAt(0).toUpperCase() + t.slice(1) : ""; return t + (x.notes && x.notes.caltrans ? (t ? "; none" : "None") + " on " + list(x.notes.caltrans.map(short)) + ", which Caltrans controls" : ""); }
    if (f.id === "stops") return "Weekday boardings in early 2020: " + stopNames(x);
    return "";
  }
  var MORE = { stops: "Which stops?", lane: "Where?" }, openNote = {};
  // a shared link: ?m=2026-10&line=22&w=5.0&s=6.1&c=4&u=0,0,1,0,0,1,0 (the sender's month, targets and the mix they
  //   saw). A link from before the targets (it carries budget=) shows its u= mix, and the controls take its figures.
  var q = new URLSearchParams(location.search);
  if (q.get("line") && D.lines.indexOf(q.get("line")) !== -1) st.line = q.get("line");
  if (q.get("m") && D.months.indexOf(q.get("m")) !== -1) st.month = q.get("m");
  var qt = [q.get("w"), q.get("s"), q.get("c")].map(function (v, g) { return v == null || v === "" || !isFinite(+v) ? null : g === 2 ? Math.round(+v) : Math.round(+v * 10); });
  if (q.get("u") && (q.has("budget") || qt.every(function (v) { return v == null; }))) st.pin = q.get("u").split(",").map(Number);
  else if (q.get("budget") && +q.get("budget") > 0) st.budget = +q.get("budget");
  else if (qt.some(function (v) { return v != null; })) st.qt = qt;
  // a link from the budget page with no levels: the mix that page's rule picks, the one saving riders the most time
  //   within the budget a year (ties: cheaper, then the first), the year's cost taken as a tenth of the ten-year cost
  function budgetPick(x, budget) {
    var best = 0;
    x.mixes.forEach(function (m, i) {
      if (m[0] / x.years > budget) return;
      var b = x.mixes[best];
      if (m[6] > b[6] || (m[6] === b[6] && m[0] < b[0])) best = i;
    });
    return best;
  }
  function load(month, line) {
    var key = month + "/" + line;
    if (cache[key]) return Promise.resolve(cache[key]);
    return fetch(base + "/optimizer/" + month + "/" + encodeURIComponent(line) + ".json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (x) { cache[key] = expand(x); return cache[key]; });
  }
  // the mix shown: an older link's, else the targets' pick
  function pick(x) {
    if (st.budget) { st.pin = x.mixes[budgetPick(x, st.budget)][1].slice(); st.budget = null; }
    var k = st.pin ? mixIndex(x, st.pin) : -1;
    if (k >= 0) { st.t = x.mixes[k][9].slice(); return { k: k, met: true }; }
    st.pin = null;
    var today = x.mixes[0][9];
    if (!st.t) st.t = today.map(function (v, g) { return v == null ? null : st.qt && st.qt[g] != null ? st.qt[g] : v; });
    st.qt = null;
    var r = chooseTargets(x, st.t);
    // each goal becomes what the mix delivers, so a card never shows one figure as the goal and another as the result
    //   (one goal can force a mix that beats another). The same mix stays the cheapest for the snapped goals: any mix
    //   meeting them meets the ones asked for.
    st.t = st.t.map(function (v, g) { return v == null ? null : x.mixes[r.k][9][g]; });
    return r;
  }
  // the goal one step worse on card g: the nearest level toward today whose cheapest mix moves this card, or null
  function worse(x, t, g) {
    var o = targetOptions(x)[g].filter(function (v) { return g === 1 ? v < t[g] : v > t[g]; }).reverse();
    for (var i = 0; i < o.length; i++) {
      var t2 = t.slice(); t2[g] = o[i];
      var r = chooseTargets(x, t2);
      if (r.met && x.mixes[r.k][9][g] !== t[g]) return t2;
    }
    // no looser goal changes the mix (the other goals hold this figure where it is): relax the goal anyway, so the
    //   button always undoes a step; the card then says what holds the figure (Bryan, 2026-11-16)
    if (o.length) { var t3 = t.slice(); t3[g] = o[0]; return t3; }
    return null;
  }
  // the cards: the figure the mix delivers, today's, and what the next step better adds; trains show today's only
  function cards(x, m) {
    var today = x.mixes[0][9], train = x.kind !== "bus";
    document.querySelector(".op-metro").hidden = !train;
    document.querySelector(".op-cards").classList.toggle("op-train", train);
    // the blue is SFMTA's transit-only lanes, which a train line shares with buses
    document.querySelector(".op-k-lane").textContent = train ? "Transit lane today" : "Bus lane today";
    FIGS.forEach(function (fg, g) {
      var card = document.querySelector('.op-card[data-fig="' + fg + '"]');
      var m0 = x.mixes[0], v0 = g === 0 ? m0[2] : g === 1 ? m0[3] : m0[4], now = v0 ? v0[1] : null;
      var vals = g === 0 ? m[2] : g === 1 ? m[3] : m[4], after = vals ? vals[1] : null;
      var set = !train && today[g] != null;
      // a line with no hour every 10 minutes or better has no wait figure; riders go by the timetable, so the card shows
      //   today's on-time share instead, with no control: our measure isn't sound enough to set a target on (About)
      var ot = g === 0 && now == null && !train && x.onTime != null;
      // 511 stamps a bus's arrival at a stop, not its departure, so the card says on time, not leaves on time
      card.querySelector(".op-card-lab").textContent = g === 1 ? (train ? "Speed" : "Bus speed") : g === 0 ? (ot ? "On time" : "Expected wait") : "Crowded trips";
      card.querySelector(".op-card-val").textContent = ot ? shownPct(x.onTime) + "%" : now == null ? "No figure" : fmt(fg, after != null ? after : now);
      // our figure doesn't reproduce SFMTA's published one, so the card says so where it shows it
      // beneath the value: "Today" until a goal moves, then today's figure; the wait's timetable figure hovers
      //   (Bryan, 2026-11-16: cut the text, show clearly what today's performance is)
      var nowEl = card.querySelector(".op-card-now"), moved = !ot && now != null && after != null && fmt(fg, after) !== fmt(fg, now);
      nowEl.textContent = now == null && !ot ? "" : moved ? "Today " + fmt(fg, now) : "Today";
      // our on-time count doesn't reproduce SFMTA's published one, so the card's hover says so
      nowEl.title = ot ? "Weekdays." + (UNDER_SFMTA ? " Our count, under SFMTA's." : "") + " See About This Data."
        : g === 0 && !train && x.today && x.today.swt != null ? "If every bus kept to the timetable: " + fmt(fg, x.today.swt) : "";
      var n = set ? nextStep(x, st.t, g) : null, bad = set ? worse(x, st.t, g) : null;
      // beside a link's held mix, the step's added cost is from that mix's own ten-year cost, not the targets' cheapest
      if (n && st.pin) n = [n[0], n[1] + x.mixes[chooseTargets(x, st.t).k][0] - m[0]];
      card.querySelectorAll(".op-btn").forEach(function (bt) {
        bt.hidden = !set;
        var better = (bt.dataset.d === "dn") === (g !== 1);
        bt.disabled = better ? !n : !bad;
      });
      // a goal looser than the figure the mix gives: the other goals hold it there
      var held = set && m[9][g] != null && st.t[g] != null && (g === 1 ? m[9][g] > st.t[g] : m[9][g] < st.t[g]);
      var badCost = bad ? x.mixes[chooseTargets(x, bad).k][0] - m[0] : null;
      card.querySelectorAll(".op-tag").forEach(function (tg) {
        tg.hidden = !set;
        if (!set) return;
        var better = (tg.dataset.d === "dn") === (g !== 1);
        var c = better ? (n ? n[1] : null) : badCost;
        var why = better ? "None of the fixes we model gets this any further."
          : held ? "Your other goals keep this at " + fmt(fg, after) + "."
          : "This is today's level: there's no fix to take away.";
        if (c == null || (!better && held)) { tg.innerHTML = '<span class="op-nope" tabindex="0" role="img" aria-label="' + why + '" title="' + why + '">\u2298</span>'; return; }
        tg.textContent = c > 0 ? "+" + money(c / x.years) + "/yr" : c < 0 ? "\u2212" + money(-c / x.years) + "/yr" : "$0";
      });
    });
  }
  function share(x, m) {
    var s = new URLSearchParams(); s.set("m", st.month); s.set("line", st.line);
    // a link's mix that is held as it was carries only its levels, so a reload or a forward opens that same mix
    if (st.pin && m && m[1].length) { s.set("u", m[1].join(",")); return s.toString().replace(/%2C/g, ","); }
    ["w", "s", "c"].forEach(function (p, g) { if (st.t[g] != null) s.set(p, g === 2 ? st.t[g] : (st.t[g] / 10).toFixed(1)); });
    if (m && m[1].length) s.set("u", m[1].join(","));
    return s.toString().replace(/%2C/g, ",");
  }
  // the ten-year cost as a yearly amount, set against what the line costs to run today (Bryan, 2026-11-15: "Either
  //   annual amount or compare to current cost"); building is spread evenly over the ten years
  function costText(m, x) {
    if (!m[0]) return '<p class="op-cost">$0: no fixes needed</p>';
    var yr = m[0] / x.years, base = x.runToday;
    var vs = base ? Math.round(100 * yr / base) + "% more than the " + money(base) + " a year the " + st.line + " costs to run today" : "";
    var bld = m[7] ? (vs ? ". " : "") + "Includes " + money(m[7]) + " to build, spread over " + x.years + " years" : "";
    return '<p class="op-cost">+' + money(yr) + ' a year</p><p class="op-cost-sub">' + vs + bld + "</p>";
  }
  var map = null, mapLine = null, mapFailed = false, calls = [];
  function render() {
    var x = cache[st.month + "/" + st.line], p = pick(x), m = x.mixes[p.k], train = x.kind !== "bus", past = st.month !== D.month;
    cards(x, m);
    document.querySelector(".op-sched").textContent = x.schedule ? x.schedule.text : "";
    history.replaceState(null, "", location.pathname + "?" + share(x, m));
    // the masthead's Share offers this same scenario (layout.mjs listens for sfworks:state)
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: "?" + share(x, m) }));
    var pe = document.querySelector(".op-past"); pe.hidden = !past;
    if (past) { var tq = new URLSearchParams(share(x, m)); tq.delete("m"); tq.delete("u"); pe.innerHTML = "Numbers from " + monthName(st.month) + ", when this link was shared. <a href=\\"?" + tq.toString() + "\\">See today's numbers</a>"; }
    document.querySelectorAll(".op-k-bus").forEach(function (k) { k.hidden = train; });
    var bb = (x.map && x.map.bulbsBuilt) || [];
    document.querySelector(".op-k-bb").hidden = !bb.some(function (b) { return !b[2]; });
    document.querySelector(".op-k-bi").hidden = !bb.some(function (b) { return b[2]; });
    document.querySelector(".op-fixbox").hidden = train;
    document.querySelector(".op-total").innerHTML = costText(m, x);
    var re = document.querySelector(".op-reach");
    re.hidden = p.met; re.textContent = p.met ? "" : "These fixes can't reach all three; this is the closest.";
    var ul = document.querySelector(".op-fixes");
    ul.innerHTML = train ? "" : x.fixes.map(function (f, k) {
      var u = m[1][k]; if (!u) return "";
      var note = fixNote(x, f, u), more = MORE[f.id] && note, open = more && openNote[f.id];
      return "<li>" + esc(unitsText(x, f, u)) + (more ? ' <button type="button" class="op-more" data-f="' + f.id + '" aria-expanded="' + !!open + '" aria-controls="op-note-' + k + '">' + MORE[f.id] + "</button>"
        + '<span class="op-fix-note" id="op-note-' + k + '"' + (open ? "" : " hidden") + ">" + esc(note) + "</span>" : "") + "</li>";
    }).join("");
    // the fixes this line can't be priced for, each with its reason (optimizer_build.py notes.left)
    var LEFT = { tsp: "signal priority", lane: "bus lanes", stops: "stop removal", bulb: "bulbs", hold: "holding", fill: "running missed trips", more: "more buses" };
    var left = train ? [] : (x.notes && x.notes.left) || [], le = document.querySelector(".op-left");
    le.hidden = !left.length;
    le.textContent = left.length ? "Not offered on this line: " + left.map(function (l) { return LEFT[l[0]] + " (" + l[1] + ")"; }).join("; ") + "." : "";
    document.querySelector(".op-history h2").textContent = "How the " + x.name + " has changed";
    document.querySelector(".op-hcharts").innerHTML = x.charts;
    if (document.querySelector(".op-share").open) picture(x, m);
    // the map last, and on its own: a map that fails can't blank the figures or the fixes
    try { drawMap(x, m); } catch (err) { mapFailed = true; map = null; sfMap.fallback(document.querySelector(".op-map")); }
  }
  function setAfter(svg, x, m) {
    var ix = {}; x.fixes.forEach(function (f, k) { ix[f.id] = m[1][k]; });
    svg.querySelectorAll(".pic-new").forEach(function (p) { p.style.display = +p.dataset.m0 < (ix.lane || 0) ? "" : "none"; });
    svg.querySelectorAll(".pic-tsp").forEach(function (g) { g.style.display = ix.tsp ? "" : "none"; });
    svg.querySelectorAll(".pic-bulb").forEach(function (c) { c.style.display = +c.dataset.rank < (ix.bulb || 0) ? "" : "none"; });
    svg.querySelectorAll(".pic-stops").forEach(function (g) { g.style.display = ix.stops ? "" : "none"; });
  }
  // The share picture: before (today, with what's built) and after (with the fixes), the numbers and the month seen.
  function picture(x, m) {
    var listed = x.fixes.map(function (f, k) { return m[1][k] ? unitsText(x, f, m[1][k]) : null; }).filter(Boolean);
    var W = 900, H = Math.max(576, 440 + 22 * (listed.length + 1) + 130);
    function txt(px, py, s, size, weight, fill, anchor) { return '<text x="' + px + '" y="' + py + '" font-size="' + size + '" font-weight="' + (weight || 400) + '" fill="' + (fill || "#15181c") + '"' + (anchor ? ' text-anchor="' + anchor + '"' : "") + ' font-family="Helvetica, Arial, sans-serif">' + esc(s) + "</text>"; }
    var out = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '"><rect width="' + W + '" height="' + H + '" fill="#fff"/>';
    out += txt(28, 44, x.name, 26, 700) + txt(28, 70, "Before: today, with what's built. After: our estimate with these fixes.", 15, 400, "#59626f");
    var pic = x.pic.replace("<svg ", '<svg x="28" y="104" ').replace(/width="260" height="200"/, 'width="300" height="230"');
    var pic2 = x.pic.replace("<svg ", '<svg x="352" y="104" ').replace(/width="260" height="200"/, 'width="300" height="230"');
    out += txt(28, 104, "Before", 16, 700) + txt(352, 104, "After", 16, 700) + txt(28, 368, "The fixes", 16, 700);
    out += '<g class="pic-before">' + pic + "</g>" + '<g class="pic-afterwrap">' + pic2 + "</g>";
    out += txt(690, 118, "Before", 13, 700, "#59626f") + txt(800, 118, "After", 13, 700, "#59626f");
    var y = 124;
    FIGS.forEach(function (g) {
      var vals = g === "wait" ? m[2] : g === "mph" ? m[3] : m[4];
      out += txt(690, y + 22, ({ wait: "Expected wait", mph: x.kind === "bus" ? "Bus speed" : "Speed", crowd: "Crowded trips" })[g], 14, 400, "#59626f");
      var v0 = g === "wait" ? x.mixes[0][2] : g === "mph" ? x.mixes[0][3] : x.mixes[0][4];
      out += txt(690, y + 46, fmt(g, v0 ? v0[1] : null), 22, 700) + txt(800, y + 46, fmt(g, vals ? vals[1] : null), 22, 700, "#15181c");
      if (vals) { var e = [vals[0], vals[2]].sort(function (a, b) { return a - b; }), lo = fmt(g, e[0]), hi = fmt(g, e[1]); out += txt(800, y + 64, lo === hi ? "" : lo.replace(/ (min|mph)$/, "") + " to " + hi, 12, 400, "#59626f"); }
      y += 76;
    });
    var fy = 394;
    listed.forEach(function (f) { out += txt(28, fy, f, 14); fy += 22; });
    out += txt(28, fy, m[0] ? "+" + money(m[0] / x.years) + " a year" + (x.runToday ? ", " + Math.round(100 * m[0] / x.years / x.runToday) + "% more than the " + money(x.runToday) + " the line costs to run today" : "") : "No fixes: $0", 14, 700);
    fy += 24;
    var ix_ = {}; x.fixes.forEach(function (f, k) { ix_[f.id] = m[1][k]; });
    if (ix_.stops && x.map && x.map.removed && x.map.removed.length) {
      // wrapped at about 120 characters, so a long list stays inside the picture
      var words = ("Stops removed: " + stopNames(x).replace(/ \\([^)]*\\)/g, "")).split(" "), ln_ = "";
      words.forEach(function (wd) { if ((ln_ + " " + wd).length > 120) { out += txt(28, fy, ln_, 13, 400, "#59626f"); fy += 18; ln_ = wd; } else ln_ = ln_ ? ln_ + " " + wd : wd; });
      if (ln_) { out += txt(28, fy, ln_, 13, 400, "#59626f"); fy += 20; }
    }
    out += txt(28, fy, "The wait counts the hours with a bus every 10 minutes or better; crowding is SFMTA's, " + D.crowdSpan + ".", 12, 400, "#59626f"); fy += 18;
    out += txt(28, fy, "Ranges: weakest to strongest case. How we make these: sf-works.org" + base + "/about#optimizer", 12, 400, "#59626f");
    var kx = 28, ky = fy + 24;
    // a key that would run past the picture's edge starts a new row
    function key(mark, label) { var w = 30 + label.length * 6.2; if (kx > 28 && kx + w > W - 20) { kx = 28; ky += 20; } out += mark(kx) + txt(kx + 20, ky + 4, label, 12, 400, "#59626f"); kx += w; }
    key(function (k) { return '<rect x="' + k + '" y="' + (ky - 2) + '" width="16" height="5" rx="2" fill="' + COL.built + '"/>'; }, "Bus lane built");
    if (ix_.lane) key(function (k) { return '<rect x="' + k + '" y="' + (ky - 2) + '" width="16" height="5" rx="2" fill="' + COL.added + '"/>'; }, "Side bus lane added");
    key(function (k) { return '<circle cx="' + (k + 8) + '" cy="' + ky + '" r="2.5" fill="' + COL.built + '"/>'; }, "Signal priority today");
    if (ix_.tsp) key(function (k) { return '<circle cx="' + (k + 8) + '" cy="' + ky + '" r="2.5" fill="' + COL.added + '"/>'; }, "Signal priority added");
    if (ix_.bulb) key(function (k) { return '<circle cx="' + (k + 8) + '" cy="' + ky + '" r="4" fill="' + COL.added + '"/>'; }, "Bus bulb added");
    if (ix_.stops) key(function (k) { return '<circle cx="' + (k + 8) + '" cy="' + ky + '" r="3" fill="#fff" stroke="' + COL.removed + '" stroke-width="1.2"/>'; }, "Stop removed");
    out += txt(W - 28, H - 18, "Numbers from " + monthName(st.month) + " \\u00b7 sf-works.org" + base + "/optimizer?" + share(x, m), 11, 400, "#59626f", "end");
    out += "</svg>";
    var box = document.querySelector(".op-pic"); box.innerHTML = out; box.dataset.w = W; box.dataset.h = H;
    var svgs = box.querySelectorAll("svg svg");
    svgs[0].querySelectorAll(".pic-after").forEach(function (g) { g.style.display = "none"; });
    setAfter(svgs[1], x, m);
  }
  function current() { var x = cache[st.month + "/" + st.line]; return [x, x.mixes[pick(x).k]]; }
  var dlg = document.querySelector(".op-share"), shareBtn = document.querySelector(".op-share-btn");
  shareBtn.addEventListener("click", function () {
    var c = current(); picture(c[0], c[1]);
    document.querySelector(".op-pic").scrollLeft = 0; // a reopened picture starts at its title, not where it was left
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    shareBtn.setAttribute("aria-expanded", "true");
  });
  document.querySelector(".op-close").addEventListener("click", function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); });
  dlg.addEventListener("close", function () { shareBtn.setAttribute("aria-expanded", "false"); });
  document.querySelector(".op-copy").addEventListener("click", function () {
    var cu = current(), u = location.origin + location.pathname + "?" + share(cu[0], cu[1]), c = document.querySelector(".op-copied");
    // where the clipboard is blocked (a sandboxed frame), show the link to copy by hand rather than a prompt box
    (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(function () { c.hidden = false; setTimeout(function () { c.hidden = true; }, 2000); }, function () { var f = document.querySelector(".op-link"); f.value = u; f.hidden = false; f.focus(); f.select(); });
  });
  // a file name per scenario, so a second picture doesn't collide with the first
  function fileName() { var c = current(); return "muni-" + st.line + "-" + (c[1][1].join("") || "none") + ".png"; }
  document.querySelector(".op-png").addEventListener("click", function () {
    var svg = document.querySelector(".op-pic > svg"); if (!svg) return;
    var clone = svg.cloneNode(true);
    clone.querySelectorAll("[style]").forEach(function (el) { if (el.style.display === "none") el.remove(); });
    var data = new XMLSerializer().serializeToString(clone), img = new Image(), k = 2;
    img.onload = function () {
      var box = document.querySelector(".op-pic"), W = +box.dataset.w, H = +box.dataset.h;
      var cv = document.createElement("canvas"); cv.width = W * k; cv.height = H * k;
      var g = cv.getContext("2d"); g.scale(k, k); g.drawImage(img, 0, 0, W, H);
      // a sandboxed frame (the board) blocks downloads, so there the picture opens in a new tab to save from
      var framed = false; try { framed = window.self !== window.top; } catch (e) { framed = true; }
      if (framed) { var w = window.open(); if (w) { w.document.title = fileName(); w.document.body.style.margin = "0"; var im = w.document.createElement("img"); im.src = cv.toDataURL("image/png"); im.style.maxWidth = "100%"; w.document.body.appendChild(im); } return; }
      cv.toBlob(function (b) { var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = fileName(); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000); });
    };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(data);
  });
  // ---- map ----
  function feats(list) { return sfMap.collection(list.map(function (c) { return { type: "Feature", properties: {}, geometry: c[0] && c[0].length ? { type: "LineString", coordinates: c } : { type: "Point", coordinates: c } }; })); }
  function drawMap(x, m) {
    var M = x.map, el = document.querySelector(".op-map");
    if (mapFailed) return; // no WebGL: the fallback message stays, and the figures above still show
    if (!M) { el.style.display = "none"; return; }
    el.style.display = "";
    var ix = {}; x.fixes.forEach(function (f, k) { ix[f.id] = m[1][k]; });
    // the view fits everything drawn, not only the route: new lanes and stops past its ends stay on screen
    function bounds() { var w = 180, s = 90, e = -180, n = -90; function add(c) { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); }
      M.shape.concat(M.lanes, M.newLanes.map(function (l) { return l.c; })).forEach(function (l) { l.forEach(add); }); M.bulbs.forEach(add); (M.removed || []).forEach(function (r) { add(r.c); }); return [[w, s], [e, n]]; }
    function paint() {
      map.getSource("op-route").setData(feats(M.shape));
      map.getSource("op-lanes").setData(feats(M.lanes));
      var nl = M.newLanes.filter(function (l) { return l.m0 < (ix.lane || 0); });
      function lf(a) { return sfMap.collection(a.map(function (l) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: l.c } }; })); }
      map.getSource("op-new").setData(lf(nl.filter(function (l) { return !l.g; })));
      map.getSource("op-new-g").setData(lf(nl.filter(function (l) { return l.g; })));
      map.getSource("op-tsp").setData(feats(x.kind === "bus" ? M.tsp : []));
      map.getSource("op-open").setData(feats(x.kind === "bus" && ix.tsp ? M.open : []));
      map.getSource("op-bulb").setData(feats(M.bulbs.slice(0, ix.bulb || 0)));
      map.getSource("op-stop").setData(feats(ix.stops ? (M.removed || []).map(function (r) { return r.c; }) : []));
      // bulbs and boarding islands built today (bus_bulbs.csv), a white ring marking an island
      map.getSource("op-bb").setData(sfMap.collection((M.bulbsBuilt || []).map(function (b) { return { type: "Feature", properties: { i: b[2] }, geometry: { type: "Point", coordinates: [b[0], b[1]] } }; })));
      // one callout per kind of fix added, at the middle of what it adds: the longest new lane's midpoint, the middle
      //   signal, bulb or removed stop
      calls.forEach(function (c) { c.remove(); }); calls = [];
      function mid(a) { return a.length ? a[Math.floor(a.length / 2)] : null; }
      var longest = nl.slice().sort(function (a, b) { return b.c.length - a.c.length; })[0];
      [[longest ? mid(longest.c) : null, "Side bus lanes"],
       [x.kind === "bus" && ix.tsp ? mid(M.open) : null, "Signal priority"],
       [mid(M.bulbs.slice(0, ix.bulb || 0)), "Bus bulbs"],
       [ix.stops ? mid((M.removed || []).map(function (r) { return r.c; })) : null, "Stops removed"]].forEach(function (c, i) {
        if (!c[0]) return;
        var el = document.createElement("div"); el.className = "op-call"; el.textContent = c[1];
        // alternate sides so two callouts near each other don't stack
        calls.push(new maplibregl.Marker({ element: el, anchor: i % 2 ? "right" : "left", offset: [i % 2 ? -10 : 10, 0] }).setLngLat(c[0]).addTo(map));
      });
    }
    if (!map) {
      try { map = sfMap.create(el, { bounds: bounds(), padding: function () { return 28; }, onReset: function () { map.fitBounds(bounds(), { padding: 28, duration: 400 }); } }); } // Reset refits the view to the line
      catch (err) { map = null; sfMap.fallback(el); }
      if (!map) { mapFailed = true; return; }
      map.once("load", function () {
        var before = sfMap.under(map);
        ["op-route", "op-lanes", "op-new", "op-new-g", "op-tsp", "op-open", "op-bulb", "op-stop", "op-bb"].forEach(function (s) { map.addSource(s, { type: "geojson", data: sfMap.collection([]) }); });
        map.addLayer({ id: "op-route", type: "line", source: "op-route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": COL.route, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2, 15, 4] } }, before);
        map.addLayer({ id: "op-lanes", type: "line", source: "op-lanes", layout: { "line-cap": "round" }, paint: { "line-color": COL.built, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 8] } }, before);
        // a new lane is drawn on its side of the street, to the right of its direction, so beside a built lane the
        //   other way (Mission St's southbound lane) it sits next to the blue, not on it
        map.addLayer({ id: "op-new", type: "line", source: "op-new", layout: { "line-cap": "round" }, paint: { "line-color": COL.added, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 8], "line-offset": ["interpolate", ["linear"], ["zoom"], 11, 2, 15, 5] } }, before);
        // a lane in a narrow street's only traffic lane: the same colour, dashed
        map.addLayer({ id: "op-new-g", type: "line", source: "op-new-g", layout: { "line-cap": "butt" }, paint: { "line-color": COL.added, "line-dasharray": [1, 0.8], "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 8], "line-offset": ["interpolate", ["linear"], ["zoom"], 11, 2, 15, 5] } }, before);
        map.addLayer({ id: "op-tsp", type: "circle", source: "op-tsp", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 15, 5], "circle-color": COL.built, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } }, before);
        map.addLayer({ id: "op-open", type: "circle", source: "op-open", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 15, 5], "circle-color": COL.added, "circle-stroke-color": "#15181c", "circle-stroke-width": 0.8 } }, before);
        map.addLayer({ id: "op-stop", type: "circle", source: "op-stop", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3, 15, 6], "circle-color": "#fff", "circle-stroke-color": COL.removed, "circle-stroke-width": 1.5 } }, before);
        map.addLayer({ id: "op-bb", type: "circle", source: "op-bb", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 8], "circle-color": COL.built, "circle-stroke-color": ["case", ["==", ["get", "i"], 1], "#fff", "#15181c"], "circle-stroke-width": ["case", ["==", ["get", "i"], 1], 2, 1] } }, before);
        map.addLayer({ id: "op-bulb", type: "circle", source: "op-bulb", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 8], "circle-color": COL.added, "circle-stroke-color": "#15181c", "circle-stroke-width": 1 } }, before);
        mapLine = st.line; paint();
      });
      map.sfPaint = paint;
      return;
    }
    if (!map.sfLoaded) { map.once("load", function () { drawMap(x, m); }); return; }
    paint();
    if (mapLine !== st.line) { mapLine = st.line; map.fitBounds(bounds(), { padding: 28, duration: 0 }); }
  }
  function choose(line) {
    load(st.month, line).then(function (x) {
      st.line = line;
      var inp = document.getElementById("op-line"); if (inp && document.activeElement !== inp) inp.value = x.name;
      render();
    }).catch(function () { document.querySelector(".op-total").textContent = "This line's results didn't load. Reload the page to try again."; });
  }
  // a new line starts at today's levels, in today's numbers
  // Reset (Bryan, 2026-11-16: "Give me a way to reset"): this line, today's goals, no fixes
  document.querySelector(".op-reset").addEventListener("click", function () { st.t = null; st.pin = null; st.qt = null; st.budget = null; st.month = D.month; choose(st.line); });
  window.addEventListener("muni:line", function (e) { if (D.lines.indexOf(e.detail) !== -1) { st.t = null; st.pin = null; st.month = D.month; choose(e.detail); } });
  // a step on a card: better takes the next level the fixes reach, with the cheapest mix that meets all three; worse
  //   relaxes this goal to the nearest level that moves it. On a shared link's month it stays in that month, whose
  //   figures the cards came from; the month's notice keeps its "See today's numbers" link.
  document.querySelector(".op-cards").addEventListener("click", function (e) {
    var bt = e.target.closest(".op-btn"); if (!bt || bt.disabled) return;
    var x = cache[st.month + "/" + st.line], g = +bt.dataset.g, better = (bt.dataset.d === "dn") === (g !== 1);
    if (better) { var n = nextStep(x, st.t, g); if (!n) return; st.t[g] += g === 1 ? n[0] : -n[0]; }
    else { var t2 = worse(x, st.t, g); if (!t2) return; st.t = t2; }
    st.pin = null; render();
  });
  document.querySelector(".op-fixes").addEventListener("click", function (e) {
    var mo = e.target.closest(".op-more"); if (!mo) return;
    var op = mo.getAttribute("aria-expanded") !== "true";
    openNote[mo.dataset.f] = op; mo.setAttribute("aria-expanded", String(op));
    document.getElementById(mo.getAttribute("aria-controls")).hidden = !op;
  });
  choose(st.line);
})();
</script>`;

export function render() {
  return page({
    title: "Upgrade a Bus Line",
    description: "Set a Muni bus line's wait, speed and crowding and see the fixes that get there for the least over ten years.",
    path,
    body: body(),
    directory: false,
  });
}

// One small file per line and month, fetched when the reader picks it, so the page doesn't carry every line's results
// and a link shared in an earlier month still opens that month's numbers.
const frag = (m, l) => ({ path: `${BASE}/optimizer/${m}/${encodeURIComponent(l)}.json`, file: `transportation/muni/optimizer/${m}/${l}.json`,
  html: Buffer.from(JSON.stringify(lineData(m, l))), sitemap: false });
export function pages() {
  return MONTHS_HELD.flatMap((m) => Object.keys(FILES[m].lines).map((l) => frag(m, l)));
}
export function pageFor(f) {
  const x = /^transportation\/muni\/optimizer\/(\d{4}-\d{2})\/([^/]+)\.json$/.exec(f);
  return x && FILES[x[1]] && FILES[x[1]].lines[x[2]] ? frag(x[1], x[2]) : null;
}
