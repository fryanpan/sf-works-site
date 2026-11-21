// Everything the Muni pages share: the data, line names and groups, the period
// switch, the figures row, the charts and the line picker.
//
// The data is written by tools/muni/muni-ewt/site_data.py (muni.json: citywide and
// per-line figures for each period, the month-by-month trend), muni_map.py
// (muni-map.json: stops, line shapes, GTFS line names) and muni_detail.py
// (muni-lines.json: each line's points within each period). None of it is
// computed here; this module only draws it.
//
// Bryan, 2026-11-09, on what leads: excess wait for lines with a bus every 10
// minutes or better, speed second, on-time for the less frequent lines third.
// The period switch is 30, 90 or 365 days (default 365, kept in ?days=), and
// every figure compares with the period of the same length just before it.

import fs from "node:fs";
import path from "node:path";
import { esc } from "./html.mjs";
import { Plot, plotSVG as plotFull, HALO } from "./plot.mjs";

// Plot writes path coordinates to many decimals; a tenth of a pixel is plenty,
// and it halves a page that carries several hundred-point charts.
const plotSVG = (o, m) => plotFull(o, m).replace(/ (d|points|transform)="([^"]*)"/g, (_, k, v) => ` ${k}="${v.replace(/(\d+\.\d)\d+/g, "$1")}"`);

const DATA = path.join(import.meta.dirname, "..", "data");
const read = (f) => JSON.parse(fs.readFileSync(path.join(DATA, f), "utf8"));
export const data = read("muni.json");
export const map = read("muni-map.json");
export const detail = read("muni-lines.json");
export const heatCells = read("muni-heat.json"); // {period: {line: {direction: [[hour, tenth, minutes, stop-hours]], blanked}}}, site_data.py

export const BASE = "/transportation/muni";
export const ABOUT = { href: `${BASE}/about`, label: "About the Data" };
export const PERIODS = ["30", "90", "365", "1825", "max"];
export const DEFAULT = "365"; // Bryan, 2026-11-10: "default to last 12 months on the overview dash (and everywhere else)"

// ---- Dates ------------------------------------------------------------------

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const monthName = (ym) => `${MONTHS[+ym.slice(5, 7) - 1]} ${ym.slice(0, 4)}`;
const lastDay = (ym) => new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7), 0)).getUTCDate();
/** "October 2026" or "August to October 2026" or "November 2025 to October 2026". */
export function span([a, b]) {
  if (a === b) return monthName(a);
  if (a.slice(0, 4) === b.slice(0, 4)) return `${MONTHS[+a.slice(5, 7) - 1]} to ${monthName(b)}`;
  return `${monthName(a)} to ${monthName(b)}`;
}
const newest = data.windows[DEFAULT].months[1];
/** The last day the data covers, "31 October 2026". */
export const THROUGH = `${lastDay(newest)} ${monthName(newest)}`;
export const OUTAGE = ["2024-11", "2025-02"];

// Published on sf-works.org as a draft (Bryan, 2026-11-19, "Publish as draft":
// "Live tonight, marked Draft with its data date, linked from nowhere else"). DATA_READ is the date the newest data in
// muni.json was read, written there by the pipeline (tools/muni/muni-ewt/site_data.py, "read"), so it moves only when new
// data does and the daily refresh keeps it current.
const longDate = (iso) => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
if (!/^\d{4}-\d{2}-\d{2}$/.test(data.read || "")) throw new Error(`muni.json: read date missing or malformed: ${data.read}`);
export const DATA_READ = longDate(data.read);
/** The same date as YYYY-MM-DD, for the site's lists (src/page-dates.mjs). */
export const DATA_READ_ISO = data.read;
export const DRAFT_NOTE = `<p class="draft-band"><strong>Draft.</strong> Data updated ${DATA_READ}.</p>`;

// ---- Lines ------------------------------------------------------------------

const SUBS = { KBUS: "K", NBUS: "N", TBUS: "T", FBUS: "F", LBUS: "L" };
/** "38R Geary Rapid", "N Judah", "K bus" — the code and the GTFS route_long_name. */
export function lineName(code) {
  if (SUBS[code]) return `${SUBS[code]} bus`;
  const n = map.names[code];
  return n ? `${code} ${n}` : code;
}
const MODE = (l) => (["J", "K", "L", "M", "N", "T"].includes(l) ? "metro" : l === "F" ? "streetcar" : ["PH", "PM", "CA"].includes(l) ? "cable" : l.endsWith("R") ? "rapid" : "bus");
// Bryan, 2026-11-09: "show the train lines first, the bus lines, and then the cable car lines."
export const GROUPS = [
  { id: "train", label: "Trains", modes: ["metro", "streetcar"] },
  { id: "bus", label: "Buses", modes: ["rapid", "bus"] },
  { id: "cable", label: "Cable cars", modes: ["cable"] },
];
export const modeOf = MODE;
export const isRail = (l) => ["metro", "streetcar", "cable"].includes(MODE(l));
const MODE_ORDER = ["metro", "streetcar", "rapid", "bus", "cable"];
const numKey = (l) => [MODE_ORDER.indexOf(MODE(l)), parseInt(l, 10) || 0, l];
const cmp = (a, b) => { const x = numKey(a), y = numKey(b); return x[0] - y[0] || x[1] - y[1] || (x[2] < y[2] ? -1 : x[2] > y[2] ? 1 : 0); };
/** Every listed line, in the site's order: trains, then buses (Rapids first), then cable cars. */
export const LINES = Object.keys(data.lines).sort(cmp);
export const groupOf = (l) => GROUPS.find((g) => g.modes.includes(MODE(l)));
/** Rows grouped as GROUPS, each group in the order `sort` gives. */
export function grouped(rows, sort) {
  return GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => g.modes.includes(MODE(r.line))).sort(sort) })).filter((g) => g.rows.length);
}

// ---- Numbers ----------------------------------------------------------------

/** Two significant figures (Bryan, 2026-09-20: "stick to 2 significant digits throughout"). */
export const sig2 = (n) => (n == null || !isFinite(n) ? "–" : n === 0 ? "0" : String(Number(n.toPrecision(2))));
/** A target percentage to the tenth it is set at: 98.5, not sig2's 99. */
export const tgtPct = (v) => String(Math.round(10 * v) / 10);
export const minutes = (v) => `${sig2(v)} min`;
export const mph = (v) => `${sig2(v)} mph`;
/** A line's speed over a period (muni-lines.json), or null when its line figure covers under MINCOVER of the line's
 * measured bus-miles (speed_along_line.py's cover): there it measures a small, unrepresentative stretch, such as the
 * 8AX's city streets without its freeway (Fable review, 2026-11-11). */
export const MINCOVER = 0.3;
export const lineSpeed = (d) => (d?.mph != null && (d.cover == null || d.cover >= MINCOVER) ? d.mph : null);

/**
 * The change against the previous period, as a short phrase and a direction.
 * `lowerIsBetter` for excess wait; speed and on-time are better higher.
 * Under 1% either way is "about the same", so noise isn't called a trend.
 */
export function change(now, before, lowerIsBetter) {
  if (now == null || before == null || !before) return null;
  const pct = (100 * (now - before)) / before;
  if (Math.abs(pct) < 1) return { pct, cls: "same", text: `${pct < 0 ? "−" : "+"}${Math.abs(pct).toFixed(1)}%` }; // grey, but still the figure: Bryan asked for "-0.4% vs. year before"
  const better = lowerIsBetter ? pct < 0 : pct > 0;
  return { pct, cls: better ? "better" : "worse", text: `${pct > 0 ? "+" : "−"}${sig2(Math.abs(pct))}%` }; // Bryan, 2026-11-10: "Just say +4.4% vs. year before"
}
/** The change as a span the page colours: teal better, brown worse, grey the same. */
export function changeHtml(c, against) {
  if (!c) return ""; // Bryan, 2026-11-10: "Too much text everywhere"; no change, no explanation
  const vs = against && c.cls === "same" ? against.replace(/^than /, "as ") : against;
  return `<span class="chg ${c.cls}">${esc(c.text)}</span>${vs ? ` <span class="vs">${esc(vs)}</span>` : ""}`;
}
/** The change in a share, in percentage points, with the same colours. */
export function pointsChange(now, before) {
  if (now == null || before == null) return null;
  const d = 100 * (now - before);
  if (Math.abs(d) < 0.1) return { pct: d, cls: "same", text: "About the same" };
  return { pct: d, cls: d > 0 ? "better" : "worse", text: `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(1)} points` };
}
/** "than September 2026", or why there's nothing to compare with. */
export const SHORT_VS = { "30": "vs. month before", "90": "vs. 3 months before", "365": "vs. year before", "1825": "", max: "" };
export function versus(w) {
  return data.windows[w].before ? SHORT_VS[w] : "";
}
/** Why a period has no change to show: the period before is in the 511 outage, or before the data starts. */
/** The 12-month view's comparison with the same months a year earlier when the 12 months before touch the 511 outage
 * (site_data.py windows[w].match): the label names the months, "vs. year before (Mar–Oct)". */
export function matchVs(w) {
  const m = data.windows[w].match;
  if (!m) return "";
  const ab = (ym) => MONTHS[+ym.slice(5, 7) - 1].slice(0, 3);
  return `vs. year before (${ab(m.months[0])}–${ab(m.months[1])})`;
}
export function noChange(w) {
  const x = data.windows[w];
  return x.noBefore === "outage" ? "Change unavailable: the period before falls in the 511 data outage" : "No earlier period to compare with";
}
const comma = (n) => n.toLocaleString("en-US");
/** "Figures for October 2026", and for a period with months left out, the days it really covers. */
export function periodLine(w) {
  const x = data.windows[w];
  // Bryan, 2026-11-10: "Too much text everywhere". The switch names the period; only an outage gap gets a line.
  return x.gap.length ? `<p class="asof">Leaves out the ${esc(span([x.gap[0], x.gap.at(-1)]))} data outage</p>` : "";
  const gap = x.gap.length ? `, ${comma(x.days)} days with data (${span([x.gap[0], x.gap.at(-1)])} left out: 511 data outage)` : "";
  // At 30 days the period is the newest month, which the "Data through" line beside the switch already names.
  if (x.months[0] === x.months[1] && x.months[1] === newest) return "";
  return `<p class="asof">Figures for ${esc(span(x.months))}${gap}</p>`;
}

// ---- The period switch --------------------------------------------------------
//
// One control, 30, 90 or 365 days, 5 years or Max. Every figure that depends on it is drawn
// for all three at build time and shown by CSS from <html data-days>, so
// switching moves nothing and needs no chart code in the browser. The choice
// lives in ?days= and the Share button copies it.

export const LABEL = { "30": "30 days", "90": "90 days", "365": "365 days", "1825": "5 years", max: "Max" };
export function periodSwitch() {
  return `<div class="period" role="group" aria-label="Period">${PERIODS.map((w) =>
    `<button type="button" data-days="${w}" aria-pressed="${w === DEFAULT}">${LABEL[w]}</button>`).join("")}</div>`;
}
/**
 * The plain and the distribution version of a figure, for Bryan to compare
 * (2026-11-09: "Show me some versions that have the distribution"). ?view=dist
 * shows the distribution version; there's no on-page control for it.
 */
export const forView = (plain, dist) => `<div class="vv" data-v="plain">${plain}</div><div class="vv" data-v="dist">${dist}</div>`;
/** Wraps one period's version of a block; only the chosen period's shows. */
/** Inline text that changes with the period, such as a heading worded from the chosen period's data. */
export const perPeriodText = (fn) => PERIODS.map((w) => `<span class="wi" data-w="${w}">${fn(w)}</span>`).join("");
export const forPeriod = (fn) => PERIODS.map((w) => `<div class="wv" data-w="${w}">${fn(w)}</div>`).join("");
export const PERIOD_SCRIPT = `<script>
(function () {
  var root = document.documentElement, ok = { "30": 1, "90": 1, "365": 1, "1825": 1, max: 1 };
  function set(w, push) {
    if (!ok[w]) w = "${DEFAULT}";
    root.setAttribute("data-days", w);
    document.querySelectorAll(".period button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.days === w ? "true" : "false"); });
    var q = new URLSearchParams(location.search);
    if (w === "${DEFAULT}") q.delete("days"); else q.set("days", w);
    var s = q.toString() ? "?" + q.toString() : "";
    if (push) history.replaceState(null, "", location.pathname + s + location.hash);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: s }));
    window.dispatchEvent(new CustomEvent("muni:days", { detail: w }));
  }
  if (new URLSearchParams(location.search).get("view") === "dist") root.setAttribute("data-view", "dist");
  set(new URLSearchParams(location.search).get("days") || "${DEFAULT}", false);
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".period button");
    if (b) set(b.dataset.days, true);
  });
  window.muniDays = function () { return root.getAttribute("data-days") || "${DEFAULT}"; };
})();
</script>`;

// ---- The figures row ----------------------------------------------------------

/** One figure: what it is, the value, and one comparison. Nothing else in the card. */
export function kpi({ label, value, chg, note = "", cls = "", scale = "" }) {
  return `<div class="kpi ${cls}"><span class="k-label">${label}</span><b>${value}</b>${scale ? `<span class="k-scale">${scale}</span>` : ""}<span class="k-sub">${chg}${note}</span></div>`;
}
/**
 * The excess wait as a share of the timetable's own wait, so a reader can tell
 * how bad a number of minutes is. Bryan, 2026-11-09: "present this as both the
 * excess wait in terms of minutes and then your suggested metric."
 */
export const pctLonger = (ewt, swt) => (ewt != null && swt ? Math.round((100 * ewt) / swt) : null);
// The card's label already says "Excess wait", so the line under the figure doesn't repeat it (UX review, 2026-11-11);
// "% longer than expected" is Bryan's wording (on the review build) and the Lines list's unit.
export const scaleLine = (ewt, swt) => (pctLonger(ewt, swt) != null ? `${pctLonger(ewt, swt)}% longer than expected` : "");
/**
 * On time at timepoints, in SFMTA's window (1 minute early to 4 late), on SFMTA's Connector and Owl lines, with the share that left early under it (Bryan, 2026-11-09: "the
 * really annoying thing is when the bus comes early").
 */
export function onTimeCard(o, against, label = "On time (on infrequent bus lines)") {
  if (!o?.now) return kpi({ label, value: "–", chg: `<span class="chg none">Too few departures in this period</span>` });
  return kpi({ label, value: `${Math.round(100 * o.now.onTime)}%`, scale: `1 min early to 4 late, ${Math.round(100 * o.now.early)}% early`,
    chg: changeHtml(change(o.now.onTime, o.before?.onTime, false), o.before ? against : against || "") });
}

// ---- Colours ------------------------------------------------------------------
//
// Causes are an unordered pair, so Observable 10's first two (site decision,
// 2026-10-10). Excess wait on the maps is one continuous quantity, so one
// sequential ramp: the site's --seq-3 (short waits) through --seq-2 to --seq-1
// (long waits). Red stays out.
// A chart with one series (a single bar per row, one line) takes Observable 10's first colour, C.one, so the gold
// keeps its one meaning, missing buses.
export const C = { spacing: "#4269d0", missing: "#efb118", weighting: "#9498a0", one: "#4269d0" };
export const MODE_COLOR = { train: "#4269d0", bus: "#efb118", cable: "#6cc5b0" };
// The maps use a darker viridis ramp, --map-1 to --map-3, so dots stand out on the grey basemap (Bryan, 2026-11-10:
// "The color scale is really had to read -- low contrast vs. the map"). Lightness still carries the order.
export const RAMP = { domain: [0.5, 1.5, 3], tokens: ["--map-1", "--map-2", "--map-3"] };
/** Share of departures that left a timepoint more than 1 minute early (SFMTA's window): the same ramp, from rare to common. */
export const EARLY_RAMP = { domain: [0.05, 0.15, 0.3], tokens: ["--map-1", "--map-2", "--map-3"] };
/** Speed to the next stop: the same ramp turned round, so the slow stretches are the dark ones. */
export const SPEED_RAMP = { domain: [4, 8, 12], tokens: ["--map-3", "--map-2", "--map-1"] };

// ---- Charts ------------------------------------------------------------------
//
// Each chart is drawn twice, at laptop and at phone width, and CSS shows one,
// so the text in a chart is the same size on both (a 660-pixel chart shrunk to
// a phone halves its labels).

export const both = (fn) => `<div class="cw">${fn(660)}</div><div class="cn">${fn(350)}</div>`;
const pm = (ym) => new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7) - 1, 15));
// drawn only where the chart's months reach the outage, so a chart clipped to a period draws nothing outside its frame
const outageBand = (top, bottom, W, first = OUTAGE[0], last = OUTAGE[1]) => (last < OUTAGE[0] || first > OUTAGE[1] ? [] : [
  Plot.rectX([0], { x1: () => pm(OUTAGE[0]).getTime() - 15 * 864e5, x2: () => pm(OUTAGE[1]).getTime() + 15 * 864e5, y1: bottom, y2: top, fill: "var(--raised)" }),
  Plot.text([0], { x: () => pm("2024-12"), y: top, text: () => (W < 500 ? "511\ndata\noutage" : "511 data\noutage"), dy: 4, lineAnchor: "top", fontSize: 11, fill: "var(--muted)" }),
]);
/**
 * August to December 2022 were scored against a stand-in timetable: 511 carried none for those months, so they're
 * measured against SFMTA's own GTFS as the Internet Archive captured it (site_data.py's about.standin; About says
 * which). Marked on the charts whose figures use the timetable, excess wait and speed.
 */
const STANDIN = data.about.standin?.months || [];
const standinBand = (top, bottom, W, from) => (!STANDIN.length || STANDIN.at(-1) < from ? [] : [
  Plot.rectX([0], { x1: () => pm(STANDIN[0]).getTime() - 15 * 864e5, x2: () => pm(STANDIN.at(-1)).getTime() + 15 * 864e5, y1: bottom, y2: top, fill: "var(--raised)", fillOpacity: 0.7 }),
  Plot.text([0], { x: () => pm(STANDIN[Math.floor(STANDIN.length / 2)]), y: top, text: () => (W < 500 ? "Stand-\nin time-\ntable" : "Stand-in\ntimetable"), dy: 4, lineAnchor: "top", fontSize: 10.5, fill: "var(--muted)" }),
]);
const yearTicks = (from, to) => { const t = []; for (let y = +from.slice(0, 4); y <= +to.slice(0, 4) + 1; y++) t.push(new Date(Date.UTC(y, 0, 1))); return t; };
const axisStyle = { fontSize: 12 };
const nMonths = (a, b) => (+b.slice(0, 4) - +a.slice(0, 4)) * 12 + (+b.slice(5, 7) - +a.slice(5, 7)) + 1;
const addMonths = (ym, k) => { const n = +ym.slice(0, 4) * 12 + +ym.slice(5, 7) - 1 + k; return `${Math.floor(n / 12)}-${String((n % 12) + 1).padStart(2, "0")}`; };
const MON_ = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** A monthly chart's time axis from the first month to the last, so a chart clipped to the chosen period (Bryan,
 *  2026-11-17: "all charts below should respect the date range") reads at any length: years
 *  past two years (every fifth past six), months under that. */
export function monthX(first, last, narrow) {
  const n = nMonths(first, last), d0 = pm(first), d1 = pm(last);
  if (n > 24) {
    const step = n > 72 ? (narrow ? 10 : 5) : 1;
    return { type: "time", domain: [d0, d1], label: null, tickSize: 0, tickFormat: (d) => String(d.getUTCFullYear()),
      ticks: yearTicks(first, last).filter((d) => d - d0 > -31 * 864e5 && d <= d1 && d.getUTCFullYear() % step === 0) };
  }
  const step = n > 12 ? (narrow ? 6 : 3) : (narrow ? 3 : 2), ticks = [];
  for (let i = 0; i < n; i += step) ticks.push(pm(addMonths(first, i)));
  return { type: "time", domain: [d0, d1], label: null, tickSize: 0, ticks,
    tickFormat: (d, i) => `${MON_[d.getUTCMonth()]}${i === 0 || d.getUTCMonth() === 0 ? ` ${d.getUTCFullYear()}` : ""}` };
}
/** Three months or fewer can't draw as a trend, so each month is a column with its figure printed. */
// a column's band drawn about 28 px wide (20 on a phone), whatever the number of months
//   (shortChart's band scale: range W - 42, padding 0.2, so each band is (W - 42) / (n + 0.2) * 0.8 wide)
const insetFor = (n, W) => { const col = ((W - 42) / (n + 0.2)) * 0.8, w = W < 500 ? 20 : 28, i = Math.max(0, (col - w) / 2); return { insetLeft: i, insetRight: i }; };
const SHORT = 3;
const monthLabel = (ym) => `${MON_[+ym.slice(5, 7) - 1]} ${ym.slice(0, 4)}`;
function shortChart(rows, W, { keys, band = null, yLabel, lo = 0, hi, fmt = sig2, unit = "", rule = null, label }) {
  const narrow = W < 500, xs = rows.map((r) => monthLabel(r.month));
  const vals = rows.flatMap((r) => [...keys.map((k) => r[k.key]), ...(band ? [r[band[0]], r[band[1]]] : []), rule?.v]).filter((v) => v != null && isFinite(v));
  const top = hi ?? Math.ceil(Math.max(...vals) * 1.15 * 2) / 2, bottom = lo ?? Math.floor(Math.min(...vals) * 2) / 2 - 0.5;
  const off = (i) => (keys.length > 1 ? (i - (keys.length - 1) / 2) * (narrow ? 26 : 40) : 0);
  return plotSVG({
    width: W, height: narrow ? 190 : 200, marginLeft: 34, marginRight: 8, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { type: "band", domain: xs, label: null, tickSize: 0, padding: 0.2 },
    y: { domain: [bottom, top], label: bottom > 0 ? `${yLabel} (axis starts at ${bottom})` : yLabel, labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      rule ? Plot.ruleY([rule.v], { stroke: "var(--ink)", strokeDasharray: "4 3", strokeOpacity: 0.6 }) : null,
      rule ? Plot.text([rule.v], { x: () => xs[0], y: (d) => d, text: () => rule.text, dy: -7, dx: narrow ? -40 : -80, textAnchor: "start", fontSize: 11, fill: "var(--muted)" }) : null,
      band ? Plot.barY(rows, { x: (r) => monthLabel(r.month), y1: band[0], y2: band[1], fill: keys[0].color, fillOpacity: 0.16, ...insetFor(rows.length, W) }) : null,
      band ? Plot.text(rows.slice(-1), { x: (r) => monthLabel(r.month), y: band[1], text: () => "90th percentile", dy: -2, dx: narrow ? 14 : 22, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }) : null,
      band ? Plot.text(rows.slice(-1), { x: (r) => monthLabel(r.month), y: band[0], text: () => "10th percentile", dy: 2, dx: narrow ? 14 : 22, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }) : null,
      ...keys.flatMap((k, i) => [
        Plot.dot(rows.filter((r) => r[k.key] != null), { x: (r) => monthLabel(r.month), y: k.key, dx: off(i), r: 4, fill: k.color }),
        Plot.text(rows.filter((r) => r[k.key] != null), { x: (r) => monthLabel(r.month), y: k.key, dx: off(i), text: (r) => `${keys.length > 1 ? `${k.name} ` : ""}${fmt(r[k.key])}${unit}`, dy: -11, fontSize: narrow ? 10.5 : 11.5, fontWeight: 600, fill: k.ink || "var(--ink)", ...HALO }),
      ]),
    ],
  }, { label });
}

/**
 * Excess wait month by month, split into uneven spacing (buses that ran, unevenly)
 * and missing buses (scheduled buses that never showed), with what London's
 * weighting takes off drawn below zero. The black line is the total. With `band`, the
 * 10th to 90th percentile across lines (ewtP10, ewtP90) is shaded behind it (Bryan,
 * 2026-11-09: "every trend chart shows the median with a 10th to 90th percentile band").
 */
export function causeChart(trend, W, { label = "Muni", band = false } = {}) {
  // a month whose frequent hours have no tracked-trip timetable has no split
  const has = (t) => t.ewt != null && t.spacing != null;
  const pts = trend.filter(has);
  if (!pts.length) return "";
  if (trend.length <= SHORT) return causeShort(pts, W, label);
  const KS = ["Uneven spacing", "Missing buses", "Weighting"];
  const parts = trend.flatMap((t) => (!has(t)
    ? KS.map((k) => ({ m: pm(t.month), k, v: NaN }))
    : [{ m: pm(t.month), k: "Uneven spacing", v: t.spacing }, { m: pm(t.month), k: "Missing buses", v: t.missing }, { m: pm(t.month), k: "Weighting", v: t.weighting }]));
  const bandPts = band ? pts.filter((t) => t.ewtP90 != null) : [];
  const top = Math.max(2, Math.ceil(Math.max(...pts.map((t) => Math.max(t.ewt, t.spacing + Math.max(0, t.missing), t.ewtP90 ?? 0))) * 2) / 2);
  const bottom = Math.min(0, Math.floor(Math.min(...pts.map((t) => t.weighting ?? 0)) * 4) / 4);
  const last = pts.at(-1);
  const bandRows = trend.map((t) => ({ m: pm(t.month), lo: t.ewtP10 ?? NaN, hi: t.ewtP90 ?? NaN }));
  // The band is named once, above its top edge a year in, where the stack sits well below it.
  const y0 = +bandPts[0]?.month.slice(0, 4);
  const bandAt = bandPts.find((t) => t.month >= (W < 500 ? `${y0}-06` : `${y0 + 1}-03`));
  const narrow = W < 500, H = narrow ? 230 : 250, right = narrow ? 70 : 118;
  const ends = [
    { k: narrow ? "Spacing" : "Uneven spacing", v: last.spacing, y: last.spacing / 2, c: "#2b4f9e" },
    { k: narrow ? "Missing" : "Missing buses", v: last.missing, y: last.spacing + last.missing / 2, c: "#8a6300" },
  ];
  const line = trend.map((t) => ({ m: pm(t.month), v: t.ewt ?? NaN }));
  // The grey below zero is named where it's deepest, so the chart needs no note under it (About explains it).
  const deep = pts.reduce((a, b) => ((b.weighting ?? 0) < (a.weighting ?? 0) ? b : a));
  return plotSVG({
    width: W, height: H, marginLeft: 34, marginRight: right, marginTop: 22, marginBottom: 26, style: axisStyle,
    x: monthX(trend[0].month, trend.at(-1).month, W < 500),
    y: { domain: [bottom, top], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      ...outageBand(top, bottom, W, trend[0].month, trend.at(-1).month),
      ...standinBand(top, bottom, W, trend[0].month),
      bandPts.length ? Plot.areaY(bandRows, { x: "m", y1: "lo", y2: "hi", fill: "var(--ink)", fillOpacity: 0.08, curve: "step" }) : null,
      bandAt ? Plot.text([bandAt], { x: (d) => pm(d.month), y: "ewtP90", text: () => (narrow ? "10th–90th pct of lines" : "10th to 90th percentile of lines"), dy: -5, textAnchor: "start", lineAnchor: "bottom", fontSize: 10.5, fill: "var(--muted)", ...HALO }) : null,
      Plot.areaY(parts, Plot.stackY({ order: KS }, { x: "m", y: "v", z: "k", fill: (d) => (d.k === "Uneven spacing" ? C.spacing : d.k === "Missing buses" ? C.missing : C.weighting), fillOpacity: 0.4, curve: "step" })),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      // The band's edges are redrawn over the stack, where its fill is hidden.
      ...(bandPts.length ? ["lo", "hi"].map((k) => Plot.lineY(bandRows, { x: "m", y: k, stroke: "var(--muted)", strokeWidth: 0.9, strokeDasharray: "2 2", curve: "step" })) : []),
      Plot.lineY(line, { x: "m", y: "v", stroke: "var(--ink)", strokeWidth: 1.6, curve: "step" }),
      Plot.text(ends.filter((d) => Math.abs(d.v) >= 0.05), { x: () => pm(last.month), y: "y", text: (d) => `${d.k} ${sig2(d.v)}`, dx: 8, textAnchor: "start", fill: (d) => d.c, fontSize: 11.5, fontWeight: 600 }),
      deep.weighting < -0.15 ? Plot.text([deep], { x: (d) => pm(d.month), text: () => "Weighting adjustment", y: (d) => d.weighting / 2, dx: 3, lineAnchor: "middle", textAnchor: "start", fontSize: 10.5, fill: "#5d6169", ...HALO }) : null,
    ],
  }, { label: `${label}: excess wait each month from ${monthName(trend[0].month)} to ${monthName(last.month)}, ${sig2(last.ewt)} minutes in the latest month, of which ${sig2(last.spacing)} from uneven spacing and ${sig2(last.missing)} from missing buses${band && last.ewtP90 != null ? `; across lines, ${sig2(last.ewtP10)} to ${sig2(last.ewtP90)} minutes (10th to 90th percentile)` : ""}.` });
}

/** causeChart for three months or fewer: a column a month, stacked by cause, the total printed over it. */
function causeShort(pts, W, label) {
  const narrow = W < 500, xs = pts.map((t) => monthLabel(t.month));
  const parts = pts.flatMap((t) => [{ x: monthLabel(t.month), k: "Uneven spacing", v: t.spacing }, { x: monthLabel(t.month), k: "Missing buses", v: t.missing }, { x: monthLabel(t.month), k: "Weighting", v: t.weighting }]);
  const top = Math.ceil(Math.max(...pts.map((t) => Math.max(t.ewt, t.spacing + Math.max(0, t.missing)))) * 2) / 2 + 0.5;
  const bottom = Math.min(0, Math.floor(Math.min(...pts.map((t) => t.weighting ?? 0)) * 4) / 4);
  const last = pts.at(-1);
  return plotSVG({
    width: W, height: narrow ? 210 : 220, marginLeft: 34, marginRight: 8, marginTop: 22, marginBottom: 26, style: axisStyle,
    x: { type: "band", domain: xs, label: null, tickSize: 0, padding: pts.length === 1 ? 0.3 : 0.2 },
    y: { domain: [bottom, top], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.barY(parts, Plot.stackY({ order: ["Uneven spacing", "Missing buses", "Weighting"] }, { x: "x", y: "v", fill: (d) => (d.k === "Uneven spacing" ? C.spacing : d.k === "Missing buses" ? C.missing : C.weighting), fillOpacity: 0.5 })),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.text(pts, { x: (t) => monthLabel(t.month), y: (t) => t.spacing + Math.max(0, t.missing), text: (t) => `${sig2(t.ewt)} min`, dy: -8, fontSize: 11.5, fontWeight: 600, fill: "var(--ink)" }),
      // each part named inside its own segment, so the colours need no key
      Plot.text(pts, { x: (t) => monthLabel(t.month), y: (t) => t.spacing / 2, text: (t) => `${narrow && pts.length > 1 ? "Spacing" : "Uneven spacing"} ${sig2(t.spacing)}`, fontSize: narrow ? 10.5 : 11.5, fontWeight: 600, fill: "#1f3d7a" }),
      Plot.text(pts.filter((t) => t.missing >= 0.12), { x: (t) => monthLabel(t.month), y: (t) => t.spacing + t.missing / 2, text: (t) => `${narrow && pts.length > 1 ? "Missing" : "Missing buses"} ${sig2(t.missing)}`, fontSize: narrow ? 10.5 : 11.5, fontWeight: 600, fill: "#6b4c00" }),
    ],
  }, { label: `${label}: excess wait in ${pts.map((t) => `${monthName(t.month)} ${sig2(t.ewt)} minutes`).join(", ")}; in ${monthName(last.month)} ${sig2(last.spacing)} from uneven spacing and ${sig2(last.missing)} from missing buses.` });
}

/**
 * One line's excess wait by cause each day or week (rows from muni_detail.py's causes: t as YYYYMMDD, the day or the
 * week's Monday), the same stack as causeChart's months. Bryan, 2026-11-10: "Change the reporting period depending on
 * time range".
 */
export function causeChartBy(rows, W, { label = "Muni", grain = "day" } = {}) {
  const KS = ["Uneven spacing", "Missing buses", "Weighting"];
  const pts = rows.filter((t) => t.ewt != null);
  if (pts.length < 2) return `<p class="verdict-note">Too few measured ${grain}s to draw.</p>`;
  const at = (t) => parseT(t.t);
  const parts = rows.flatMap((t) => (t.ewt == null
    ? ["Uneven spacing", "Missing buses", "Weighting"].map((k) => ({ m: at(t), k, v: NaN }))
    : [{ m: at(t), k: "Uneven spacing", v: t.spacing }, { m: at(t), k: "Missing buses", v: t.missing }, { m: at(t), k: "Weighting", v: t.weighting }]));
  const top = Math.max(2, Math.ceil(Math.max(...pts.map((t) => Math.max(t.ewt, t.spacing + Math.max(0, t.missing)))) * 2) / 2);
  const bottom = Math.min(0, Math.floor(Math.min(...pts.map((t) => Math.min(t.weighting, t.spacing, t.ewt))) * 4) / 4);
  const last = pts.at(-1);
  const narrow = W < 500, right = narrow ? 70 : 118;
  const ends = [
    { k: narrow ? "Spacing" : "Uneven spacing", v: last.spacing, y: last.spacing / 2, c: "#2b4f9e" },
    { k: narrow ? "Missing" : "Missing buses", v: last.missing, y: last.spacing + last.missing / 2, c: "#8a6300" },
  ];
  const fmt = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const fmtY = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  return plotSVG({
    width: W, height: narrow ? 230 : 250, marginLeft: 34, marginRight: right, marginTop: 22, marginBottom: 26, style: axisStyle,
    x: { type: "time", domain: [at(rows[0]), at(rows.at(-1))], label: null, tickSize: 0, ticks: narrow ? 3 : 6, tickFormat: fmt },
    y: { domain: [bottom, top], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.areaY(parts, Plot.stackY({ order: KS }, { x: "m", y: "v", z: "k", fill: (d) => (d.k === "Uneven spacing" ? C.spacing : d.k === "Missing buses" ? C.missing : C.weighting), fillOpacity: 0.4, curve: "step" })),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.lineY(rows.map((t) => ({ m: at(t), v: t.ewt ?? NaN })), { x: "m", y: "v", stroke: "var(--ink)", strokeWidth: 1.6, curve: "step" }),
      Plot.text(ends, { x: () => at(last), y: "y", text: (d) => `${d.k} ${sig2(d.v)}`, dx: 8, textAnchor: "start", fill: (d) => d.c, fontSize: 11.5, fontWeight: 600 }),
    ],
  }, { label: `${label}: excess wait each ${grain} from ${fmtY(at(rows[0]))} to ${fmtY(at(last))}, ${sig2(last.ewt)} minutes in the latest ${grain}, of which ${sig2(last.spacing)} from uneven spacing and ${sig2(last.missing)} from missing buses.` });
}

/**
 * A monthly measure as its median across lines (the line) with the 10th to
 * 90th percentile across lines as a light band (Bryan, 2026-11-09: "the
 * median for the KPI and also the 10th to 90th percentile range").
 * `extra` draws more marks over it, such as the timetable's speed.
 */
export function bandChart(trend, [k10, k50, k90], W, { yLabel, color = "#4269d0", fmt = sig2, unit = "", lowerBound = 0, upperAtLeast = -Infinity, extra = [], extraRule = null, label = "" }) {
  const rows = trend.map((t) => ({ m: pm(t.month), lo: t[k10] ?? NaN, mid: t[k50] ?? NaN, hi: t[k90] ?? NaN }));
  const ok = rows.filter((r) => !isNaN(r.mid));
  if (!ok.length) return "";
  if (trend.length <= SHORT) return shortChart(trend.filter((t) => t[k50] != null), W, { keys: [{ key: k50, name: "Median", color }], band: [k10, k90], yLabel, lo: lowerBound ?? null, hi: Math.max(upperAtLeast, Math.ceil(Math.max(...ok.map((r) => r.hi)) * 2) / 2), fmt, unit,
    rule: extraRule, label: `${label} Median by month, with the 10th to 90th percentile shaded.` });
  const lo = lowerBound ?? Math.floor(Math.min(...ok.map((r) => r.lo)) * 2) / 2;
  const hi = Math.max(upperAtLeast, Math.ceil(Math.max(...ok.map((r) => r.hi)) * 2) / 2);
  const last = ok.at(-1), narrow = W < 500;
  return plotSVG({
    width: W, height: narrow ? 210 : 220, marginLeft: 34, marginRight: narrow ? 74 : 112, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: monthX(trend[0].month, trend.at(-1).month, W < 500),
    y: { domain: [lo, hi], label: lo > 0 ? `${yLabel} (axis starts at ${lo})` : yLabel, labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      ...outageBand(hi, lo, W, trend[0].month, trend.at(-1).month),
      Plot.areaY(rows, { x: "m", y1: "lo", y2: "hi", fill: color, fillOpacity: 0.16, curve: "step" }),
      Plot.lineY(rows, { x: "m", y: "mid", stroke: color, strokeWidth: 1.8, curve: "step" }),
      ...extra,
      Plot.text([last], { x: "m", y: "mid", text: () => "Median", dx: 8, textAnchor: "start", fontSize: 11.5, fontWeight: 600, fill: "var(--ink)" }),
      Plot.text([last], { x: "m", y: "hi", text: () => "90th percentile", dx: 8, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }),
      Plot.text([last], { x: "m", y: "lo", text: () => "10th percentile", dx: 8, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }),
    ],
  }, { label: `${label} Median ${fmt(last.mid)}${unit} in the latest month, with 10th to 90th percentile from ${fmt(last.lo)} to ${fmt(last.hi)}.` });
}

/**
 * Average speed month by month against the timetable's speed, with the 10th to 90th percentile across lines shaded
 * (Bryan, 2026-11-09: every trend shows the 10th to 90th percentile band). The line is the citywide average, the
 * speed figure Bryan picked on 2026-11-10, not the median across lines: the timetable line is citywide too, and the
 * median line runs above it in most months while the average runs below, so the two must be the same kind of figure.
 * Not a bar, so the axis needn't start at zero, and says where it starts.
 */
export function speedChart(trend, W) {
  const pts = trend.filter((t) => t.mph != null);
  if (!pts.length) return "";
  if (trend.length <= SHORT) return shortChart(pts, W, { keys: [{ key: "mph", name: "Actual", color: "#4269d0", ink: "#2b4f9e" }, { key: "mphTimetable", name: "Timetable", color: "#9498a0", ink: "#59626f" }], yLabel: "mph", lo: 0, hi: Math.ceil(Math.max(...pts.map((t) => Math.max(t.mph, t.mphTimetable ?? 0))) + 2), fmt: (v) => v.toFixed(1),
    label: `Average bus speed by month: ${pts.map((t) => `${monthName(t.month)} ${sig2(t.mph)} mph against ${sig2(t.mphTimetable)} on the timetable`).join(", ")}.` });
  const lo = Math.floor(Math.min(...pts.map((t) => Math.min(t.mph, t.mphTimetable, t.mphP10 ?? Infinity))) * 2) / 2 - 0.5;
  const hi = Math.ceil(Math.max(...pts.map((t) => Math.max(t.mph, t.mphTimetable, t.mphP90 ?? -Infinity))) * 2) / 2;
  const bandRows = trend.map((t) => ({ m: pm(t.month), lo: t.mphP10 ?? NaN, hi: t.mphP90 ?? NaN }));
  const lastB = [...trend].reverse().find((t) => t.mphP90 != null);
  const narrow = W < 500, last = pts.at(-1);
  const row = (k) => trend.map((t) => ({ m: pm(t.month), v: t[k] ?? NaN }));
  return plotSVG({
    width: W, height: narrow ? 200 : 210, marginLeft: 34, marginRight: narrow ? 70 : 110, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: monthX(trend[0].month, trend.at(-1).month, W < 500),
    y: { domain: [lo, hi], label: `mph (axis starts at ${lo})`, labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      ...outageBand(hi, lo, W, trend[0].month, trend.at(-1).month),
      ...standinBand(hi, lo, W, trend[0].month),
      Plot.areaY(bandRows, { x: "m", y1: "lo", y2: "hi", fill: "#4269d0", fillOpacity: 0.14, curve: "step" }),
      lastB ? Plot.text([lastB], { x: (d) => pm(d.month), y: "mphP90", text: () => "90th percentile", dx: 8, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }) : null,
      lastB ? Plot.text([lastB], { x: (d) => pm(d.month), y: "mphP10", text: () => "10th percentile", dx: 8, textAnchor: "start", fontSize: 10.5, fill: "var(--muted)" }) : null,
      Plot.lineY(row("mphTimetable"), { x: "m", y: "v", stroke: "var(--muted)", strokeDasharray: "4 3", strokeWidth: 1.2 }),
      Plot.lineY(row("mph"), { x: "m", y: "v", stroke: "#4269d0", strokeWidth: 1.8 }),
      Plot.text([last], { x: () => pm(last.month), y: () => last.mph, text: () => "Actual", dx: 8, textAnchor: "start", fontSize: 11.5, fontWeight: 600, fill: "#2b4f9e", dy: 6 }),
      Plot.text([last], { x: () => pm(last.month), y: () => last.mphTimetable, text: () => "Timetable", dx: 8, textAnchor: "start", fontSize: 11.5, fill: "var(--muted)", dy: -6 }),
    ],
  }, { label: `Average bus speed each month, ${sig2(last.mph)} mph in ${monthName(last.month)} against ${sig2(last.mphTimetable)} on the timetable${lastB ? `; across lines, ${sig2(lastB.mphP10)} to ${sig2(lastB.mphP90)} mph (10th to 90th percentile)` : ""}.` });
}

const hourLabel = (h) => (h === 12 ? "noon" : h < 12 ? `${h}am` : `${h - 12}pm`);
/**
 * SFMTA's share of scheduled service hours delivered, every month it has
 * published (quarterly before 2011), against the target in its own dataset.
 * The axis starts at 80% (Bryan, 2026-11-10: "Make the axis start at 80 and
 * note pandemic dip as an annotation instead of showing the full range"), so
 * months below it are clipped and a note names the dip and its low.
 */
export function deliveredChart(trend, target, W) {
  if (!trend.length) return `<p class="verdict-note">SFMTA hasn't published this period's service hours yet.</p>`;
  if (trend.length <= SHORT) return shortChart(trend.map((t) => ({ month: t.month, v: 100 * t.share })), W, { keys: [{ key: "v", name: "Delivered", color: C.one }], yLabel: "% of scheduled hours", lo: 0, hi: 100, fmt: (v) => sig2(v), unit: "%",
    rule: (trend.at(-1).target ?? target) ? { v: 100 * (trend.at(-1).target ?? target), text: `SFMTA target ${tgtPct(100 * (trend.at(-1).target ?? target))}%` } : null, label: `Share of scheduled Muni service hours delivered: ${trend.map((t) => `${monthName(t.month)} ${sig2(100 * t.share)}%`).join(", ")}.` });
  const pts = trend.map((t) => ({ m: pm(t.month), v: 100 * t.share }));
  const tgt = trend.filter((t) => t.target != null).map((t) => ({ m: pm(t.month), v: 100 * t.target }));
  const tv = [...new Set(tgt.map((t) => t.v))].sort((a, b) => a - b);
  const tgtText = tv.length === 1 ? `${tgtPct(tv[0])}%` : `${tgtPct(tv[0])} to ${tgtPct(tv.at(-1))}%`;
  const lo = 0, last = pts.at(-1), narrow = W < 500; // a percentage starts at 0 (Bryan, 2026-11-10)
  const low = pts.reduce((a, b) => (b.v < a.v ? b : a));
  const under = pts.filter((p) => p.v < lo);
  const dipAt = under.length ? under[Math.floor(under.length / 2)].m : null;
  return plotSVG({
    width: W, height: narrow ? 200 : 210, marginLeft: 34, marginRight: narrow ? 46 : 60, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: monthX(trend[0].month, trend.at(-1).month, narrow),
    y: { domain: [lo, 100], label: "% of scheduled hours", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      // the target each month was held to, as DataSF gives it (99% July 2025 to June 2026, 98.5% either side)
      tgt.length ? Plot.lineY(tgt, { x: "m", y: "v", curve: "step-after", stroke: "var(--muted)", strokeDasharray: "4 3" }) : null,
      tgt.length ? Plot.text([0], { x: () => tgt[0].m, y: () => tgt[0].v, text: () => `SFMTA target ${tgtText}`, dy: -4, textAnchor: "start", lineAnchor: "bottom", fontSize: 11, fill: "var(--muted)" }) : null,
      Plot.lineY(pts, { x: "m", y: "v", stroke: C.one, strokeWidth: 1.5, clip: true }),
      dipAt ? Plot.text([0], { x: () => dipAt, y: () => lo, text: () => narrow ? `Pandemic low ${sig2(low.v)}%` : `Pandemic cuts, ${monthName(trend.find((t) => 100 * t.share === low.v).month)}: ${sig2(low.v)}% (below the axis)`, dy: -6, textAnchor: narrow ? "start" : "middle", lineAnchor: "bottom", fontSize: 11, fill: "#2b4f9e" }) : null,
    ],
  }, { label: `Share of scheduled Muni service hours delivered, ${monthName(trend[0].month)} to ${monthName(trend.at(-1).month)}: ${sig2(last.v)}% in the latest month, ${sig2(low.v)}% at the low in ${monthName(trend[trend.indexOf(trend.find((t) => 100 * t.share === low.v))].month)}.` });
}

/**
 * SFMTA's average weekday boardings, every route summed, each month it has
 * published (from January 2019). The axis starts at zero, since the 2020 fall
 * is the point of the series' shape.
 */
/**
 * Average daily riders by year, one bar each for weekday, Saturday and Sunday (Bryan, 2026-11-10: "Add one more chart
 * that shows ridership by day by year"). From SFMTA's route file, settled months only; a part year names its months.
 * Day types are an unordered set, so they take Observable 10's blue, yellow and teal (its coral is skipped: red is
 * not a category here). Each point prints its figure in thousands.
 */
const DAY_COLOR = { Weekday: "#4269d0", Saturday: "#efb118", Sunday: "#6cc5b0" };
export function ridersByDayChart(rows, W) {
  // Bryan, 2026-11-10: three lines on one chart, then "Don't bother with the labels, and show month level detail here".
  // Each day type's line is named at its end, which is the only label left.
  const narrow = W < 500;
  const data = rows.map((r) => ({ ...r, m: pm(r.month) }));
  const lastM = data.reduce((a, r) => (r.m > a ? r.m : a), data[0].m), last = data.filter((r) => +r.m === +lastM);
  const top = Math.ceil(Math.max(...data.map((r) => r.riders)) / 100000) * 100000;
  return plotSVG({
    width: W, height: narrow ? 220 : 250, marginLeft: 44, marginRight: narrow ? 62 : 74, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { type: "time", label: null, tickSize: 0, ticks: narrow ? 4 : 8 },
    y: { domain: [0, top], label: "Average daily riders", labelArrow: false, grid: true, ticks: 4, tickSize: 0, tickFormat: (v) => (v ? `${v / 1000}k` : "0") },
    color: { domain: Object.keys(DAY_COLOR), range: Object.values(DAY_COLOR) },
    marks: [
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.line(data, { x: "m", y: "riders", z: "day", stroke: "day", strokeWidth: 1.8 }),
      Plot.text(last, { x: "m", y: "riders", text: "day", dx: 6, textAnchor: "start", fontSize: narrow ? 10 : 11.5, fill: "day", fontWeight: 600 }),
    ],
  }, { label: `Average daily Muni riders each month for weekdays, Saturdays and Sundays, ${rows[0].month} to ${lastM.toISOString().slice(0, 7)}.` });
}
export const DAY_KEY = Object.entries(DAY_COLOR).map(([k, c]) => `<span class="sw" style="background:${c}"></span>${k}`).join(" ");

export function ridershipChart(trend, W) {
  const pts = trend.map((t) => ({ m: pm(t.month), v: t.weekday / 1000 }));
  const last = pts.at(-1), narrow = W < 500;
  const top = Math.ceil(Math.max(...pts.map((p) => p.v)) / 200) * 200;
  // Pre-pandemic reference (Bryan, 2026-11-10: "Mark prepandemic peak as a reference line"): the 2019 weekday
  // average, the same base the section's headline compares with.
  const y19 = trend.filter((t) => t.month.startsWith("2019")).map((t) => t.weekday / 1000);
  const ref = y19.length ? y19.reduce((a, b) => a + b, 0) / y19.length : null;
  return plotSVG({
    width: W, height: narrow ? 200 : 210, marginLeft: 34, marginRight: narrow ? 46 : 60, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { type: "time", domain: [pts[0].m, last.m], ticks: yearTicks(trend[0].month, trend.at(-1).month).filter((d) => d - pts[0].m > -31 * 864e5 && d <= last.m).filter((d, i) => !narrow || i % 2 === 0), tickFormat: (d) => String(d.getUTCFullYear()), label: null, tickSize: 0 },
    y: { domain: [0, top], label: "Weekday boardings, thousands", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      ref ? Plot.ruleY([ref], { stroke: "var(--muted)", strokeDasharray: "4 3" }) : null,
      ref ? Plot.text([0], { x: () => last.m, y: () => ref, text: () => `2019 average ${Math.round(ref)},000`, dy: -6, textAnchor: "end", lineAnchor: "bottom", fontSize: 11, fill: "var(--muted)" }) : null,
      Plot.lineY(pts, { x: "m", y: "v", stroke: "#4269d0", strokeWidth: 1.5 }),
    ],
  }, { label: `Muni average weekday boardings, ${monthName(trend[0].month)} to ${monthName(trend.at(-1).month)}: ${Math.round(last.v)},000 in the latest month.` });
}

/**
 * SFMTA's Muni Rider Survey: the share of riders rating Muni service overall good or excellent, each year it ran
 * (Bryan, 2026-11-10: "is there a satisfaction trend too?"). Years with no survey break the line; every point
 * prints its value. The axis runs 0 to 100%.
 */
export function satisfactionChart(rows, W) {
  const narrow = W < 500, first = rows[0].year, last = rows.at(-1);
  const by = Object.fromEntries(rows.map((r) => [r.year, r.pct]));
  const line = []; for (let y = first; y <= last.year; y++) line.push({ y, v: by[y] ?? NaN });
  const lo = 0, hi = 100; // Bryan, 2026-11-10: "If you're showing a percentage, start from 0"
  const ticks = []; for (let y = Math.ceil(first / 5) * 5; y <= last.year; y += narrow ? 10 : 5) ticks.push(y);
  return plotSVG({
    width: W, height: narrow ? 180 : 190, marginLeft: 34, marginRight: 14, marginTop: 22, marginBottom: 26, style: axisStyle,
    x: { domain: [first - 0.5, last.year + 0.5], ticks, tickFormat: (d) => String(d), label: null, tickSize: 0 },
    y: { domain: [lo, hi], label: "% good or excellent", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.lineY(line, { x: "y", y: "v", stroke: "#4269d0", strokeWidth: 1.5 }),
      Plot.dot(rows, { x: "year", y: "pct", r: 3, fill: "#4269d0" }),
      Plot.text(rows, { x: "year", y: "pct", text: (r) => (narrow ? String(Math.round(r.pct)) : `${Math.round(r.pct)}%`), dy: -9, fontSize: narrow ? 9 : 10.5, fill: "var(--ink)", ...HALO }),
    ],
  }, { label: `Muni riders rating service good or excellent, each survey year from ${first} to ${last.year}: ${Math.round(last.pct)}% in ${last.year}.` });
}

/**
 * Excess wait by how far along the route a stop is, one bar per tenth from the first stop to the last, both
 * directions pooled (site_data.py's byPosition). Bryan, 2026-11-10: "show excess wait by distance from start along
 * each line. Show that it gets worse later on."
 */
export function positionChart(rows, W, { label = "Muni", key = "ewt" } = {}) {
  if (!rows || rows.length < 5) return `<p class="verdict-note">Too few departures in this period.</p>`;
  const narrow = W < 500, speed = key === "mph";
  const vals = rows.map((r) => r[key]);
  const top = speed ? Math.ceil(Math.max(...vals) / 2) * 2 + 1 : Math.ceil(Math.max(...vals) * 2) / 2 + 0.5;
  const bottom = speed ? 0 : Math.min(0, Math.floor(Math.min(...vals) * 2) / 2);
  const name = (t) => (t === 0 ? "First" : t === 9 ? "Last" : String(t + 1));
  return plotSVG({
    width: W, height: narrow ? 196 : 206, marginLeft: 34, marginRight: 8, marginTop: 22, marginBottom: 40, style: axisStyle,
    x: { type: "band", domain: [...Array(10).keys()], tickFormat: name, label: "Tenth of the route, first stop to last", labelAnchor: "center", labelOffset: 36, tickSize: 0, padding: 0.18 },
    y: { domain: [bottom, top], label: speed ? "Speed, stops included (mph)" : "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.barY(rows, { x: "tenth", y: key, fill: speed ? "#3ca951" : "#4269d0", fillOpacity: 0.75 }),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.text(rows, { x: "tenth", y: (r) => Math.max(0, r[key]), text: (r) => (speed ? r[key].toFixed(r[key] < 10 ? 1 : 0) : sig2(r[key])), dy: -7, fontSize: narrow ? 10 : 11, fill: "var(--ink)" }),
    ],
  }, { label: speed ? `${label}: average speed by tenth of the route, stops included, ${rows[0].mph.toFixed(1)} mph in the first tenth and ${rows.at(-1).mph.toFixed(1)} in the last.` : `${label}: excess wait by tenth of the route, ${sig2(rows[0].ewt)} minutes in the first tenth and ${sig2(rows.at(-1).ewt)} in the last.` });
}

/**
 * The along-the-line chart once per direction (Bryan, 2026-11-10: "Plot each direction separately with the
 * appropriate destination name"): side by side on a laptop, stacked on a phone, each titled with its direction and,
 * on a line's page, its destination (GTFS trip_headsign). `dirs` is { "0": rows or { direction, to, tenths }, "1": … }.
 */
export function alongCharts(dirs, { label = "Muni", key = "ewt", names = null } = {}) {
  const parts = ["0", "1"].map((d) => {
    const v = dirs?.[d];
    const rows = Array.isArray(v) ? v : v?.tenths;
    const title = names?.[d] ?? (Array.isArray(v) || !v || !v.direction ? (d === "0" ? "Outbound" : "Inbound") : `${v.direction}${v.to ? ` to ${v.to}` : ""}`);
    return { title, rows };
  });
  const one = (W) => parts.map((p) => `<div class="al-panel"><p class="al-title">${esc(p.title)}</p>${positionChart(p.rows, W, { label: `${label}, ${p.title}`, key })}</div>`).join("");
  return `<div class="cw"><div class="al-pair">${one(325)}</div></div><div class="cn">${one(350)}</div>`;
}

/** Excess wait by hour of the day over the period: spacing and missing buses stacked, the total printed on each bar. */
/** Citywide bus speed by hour of day, actual against the timetable (site_data.py speedByHour), hours from 6am as the
 * excess-wait charts beside it (Bryan, 2026-11-10: "Can you also show Average speed by time of day?"). */
export function speedHourChart(rows, W, { label = "Average bus speed" } = {}) {
  const hrs = rows.filter((r) => r.hour >= 6 && r.hour <= 22);
  if (!hrs.length) return "";
  const narrow = W < 500, last = hrs.at(-1);
  // a line's hour can lack the timetable's speed (a month with no timetable hours for it): drawn as a gap
  const both_ = hrs.flatMap((r) => [r.mph, r.mphTimetable]).filter((v) => v != null);
  const lo = Math.floor(Math.min(...both_)) - 1, hi = Math.ceil(Math.max(...both_));
  const slow = hrs.reduce((a, b) => (b.mph < a.mph ? b : a));
  return plotSVG({
    width: W, height: narrow ? 190 : 200, marginLeft: 34, marginRight: narrow ? 64 : 80, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { domain: [6, 22], ticks: narrow ? [6, 10, 14, 18, 22] : [6, 8, 10, 12, 14, 16, 18, 20, 22], tickFormat: hourLabel, label: null, tickSize: 0 },
    y: { domain: [lo, hi], label: `mph (axis starts at ${lo})`, labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.line(hrs, { x: "hour", y: (r) => r.mphTimetable ?? NaN, stroke: "var(--muted)", strokeDasharray: "4 3", strokeWidth: 1.2 }),
      Plot.line(hrs, { x: "hour", y: "mph", stroke: "#4269d0", strokeWidth: 1.8 }),
      Plot.dot([slow], { x: "hour", y: "mph", r: 3, fill: "#4269d0" }),
      Plot.text([slow], { x: "hour", y: "mph", text: (r) => `${sig2(r.mph)} mph at ${hourLabel(r.hour)}`, dy: 14, fontSize: 11, fill: "#2b4f9e" }),
      Plot.text([last], { x: "hour", y: "mph", text: () => "Actual", dx: 8, textAnchor: "start", fontSize: 11.5, fontWeight: 600, fill: "#2b4f9e", dy: last.mph < last.mphTimetable ? 6 : -6 }),
      last.mphTimetable != null ? Plot.text([last], { x: "hour", y: "mphTimetable", text: () => "Timetable", dx: 8, textAnchor: "start", fontSize: 11.5, fill: "var(--muted)", dy: last.mph < last.mphTimetable ? -6 : 6 }) : null,
    ],
  }, { label: `${label} by hour of day, slowest ${sig2(slow.mph)} mph at ${hourLabel(slow.hour)}${slow.mphTimetable != null ? ` against ${sig2(slow.mphTimetable)} on the timetable` : ""}.` });
}

/**
 * How full the buses are, as a 100% stacked area of SFMTA's live occupancy levels (Bryan, 2026-11-16, thread
 * 6a5vi2jgknnv: "Can we show the live crowding level instead as an area chart showing all four types, and use a
 * separate chart for inbound vs. outbound"). rows carry the percent at each level (site_data.py's crowdHours,
 * crowdAlong and crowdByHour) by "hour" (6am to 10pm) or by "tenth" of the route. The levels are ordered, so their
 * colours are one blue ramp, light for empty to dark for standing; every share is printed at the one point where buses
 * are most crowded, so the printed shares add to 100.
 */
// Every level SFMTA's feed can send, bottom of the stack first, darkest to lightest (Bryan, 2026-11-16, thread
// 1b9on6wr4q9i: "Please keep all of the original categories"), each with the ink its label takes inside the band.
export const LEVELS = [
  ["not_accepting", "Not accepting riders", "#0f2350", "#fff"], ["full", "Full", "#1b3470", "#fff"], ["crushed", "Crushed standing", "#24438c", "#fff"],
  ["standing_room", "Standing room", "#3a5fb0", "#fff"], ["few_seats", "Few seats", "#7d9fdf", "var(--ink)"], ["many_seats", "Many seats", "#b4c8ee", "var(--ink)"],
  ["empty", "Empty", "#e2eaf8", "var(--ink)"],
];
const swatch = ([, name, c]) => `<span class="sw" style="background:${c}"></span>${name}`;
/** Integer percents that add to 100, by largest remainder: each share floored, the points left over going to the
 * shares with the largest remainders (ties to the earlier share). */
export function roundTo100(vals) {
  const tot = vals.reduce((a, v) => a + v, 0);
  if (!tot) return vals.map(() => 0);
  const exact = vals.map((v) => (100 * v) / tot), out = exact.map(Math.floor);
  let left = 100 - out.reduce((a, v) => a + v, 0);
  for (const i of exact.map((v, i) => i).sort((a, b) => exact[b] - out[b] - (exact[a] - out[a]) || a - b)) {
    if (left-- <= 0) break;
    out[i] += 1;
  }
  return out;
}
export function levelsChart(rows, W, { by = "hour", label = "Muni" } = {}) {
  if (!rows || rows.length < 4) return `<p class="verdict-note">Too few readings to draw.</p>`;
  const narrow = W < 500, hour = by === "hour";
  const H = narrow ? 200 : 210, mT = 14, mB = hour ? 26 : 40, mL = 34, mR = 12, plotH = H - mT - mB, plotW = W - mL - mR;
  const [x0, x1] = hour ? [6, 22] : [0, 9];
  const levels = LEVELS.filter(([k]) => rows.some((r) => r[k] > 0));
  // stacked by hand, bottom first, so each band's thickness and middle are known for its label
  const bands = levels.map(([k, name, fill, ink], i) => ({ k, name, fill, ink, pts: rows.map((r) => {
    const lo = levels.slice(0, i).reduce((a, [kk]) => a + (r[kk] || 0), 0);
    return { x: r[by], lo, hi: lo + (r[k] || 0), v: r[k] || 0 };
  }) }));
  // Every band is labelled at one point, the hour (or tenth) where the crowded levels, standing room and fuller, are
  // highest, so the printed shares are one column of the stack and add to 100: they're rounded by largest remainder
  // (each share floored, the leftover points to the largest remainders). A band at least 16 pixels tall there takes its
  // label inside; thinner bands go in the key under the chart with their share at the same point.
  const px = (x) => (plotW * (x - x0)) / (x1 - x0), py = (y) => plotH * (1 - y / 100);
  const crowdedAt = (r) => ["standing_room", "crushed", "full", "not_accepting"].reduce((a, k) => a + (r[k] || 0), 0);
  const fi = rows.reduce((b, r, i) => (crowdedAt(r) > crowdedAt(rows[b]) ? i : b), 0), focus = rows[fi];
  const pct = roundTo100(bands.map((b) => b.pts[fi].v));
  const labels = [], thin = [];
  bands.forEach((b, bi) => {
    const w = b.pts[fi], text = `${b.name} ${pct[bi]}%`, tw = text.length * (narrow ? 5.8 : 6.1), at = px(w.x);
    if ((w.v / 100) * plotH < 16 || tw > plotW) { if (w.v > 0) thin.push({ ...b, at: pct[bi], raw: w.v }); return; }
    const anchor = at < tw / 2 + 4 ? "start" : plotW - at < tw / 2 + 4 ? "end" : "middle";
    labels.push({ x: w.x, y: (w.lo + w.hi) / 2, text, ink: b.ink, anchor });
  });
  const where = hour ? hourLabel(focus.hour) : `the ${["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "last"][focus.tenth]} tenth of the route`;
  const name = (t) => (t === 0 ? "First" : t === 9 ? "Last" : String(t + 1));
  const svg = plotSVG({
    width: W, height: H, marginLeft: mL, marginRight: mR, marginTop: mT, marginBottom: mB, style: axisStyle,
    x: hour ? { domain: [x0, x1], ticks: narrow ? [6, 10, 14, 18, 22] : [6, 8, 10, 12, 14, 16, 18, 20, 22], tickFormat: hourLabel, label: null, tickSize: 0 }
      : { domain: [x0, x1], ticks: [...Array(10).keys()], tickFormat: name, label: "Tenth of the route, first stop to last", labelAnchor: "center", labelOffset: 36, tickSize: 0 },
    y: { domain: [0, 100], label: null, grid: false, ticks: [0, 50, 100], tickSize: 0, tickFormat: (v) => `${v}%` },
    marks: [
      ...bands.map((b) => Plot.areaY(b.pts, { x: "x", y1: "lo", y2: "hi", fill: b.fill })),
      Plot.ruleX([focus[by]], { stroke: "#fff", strokeOpacity: 0.7, strokeWidth: 1 }),
      ...["start", "middle", "end"].map((an) => Plot.text(labels.filter((l) => l.anchor === an), { x: "x", y: "y", text: "text", fill: "ink", textAnchor: an, dx: an === "start" ? 4 : an === "end" ? -4 : 0, fontSize: narrow ? 10.5 : 11, fontWeight: 600 })),
    ],
  }, { label: `${label}: share of weekday readings at each of SFMTA's occupancy levels by ${hour ? "hour" : "tenth of the route"}; ${bands.map((b) => `${b.name.toLowerCase()} up to ${Math.round(Math.max(...b.pts.map((p) => p.v)))}%`).join(", ")}.` });
  // Bryan, 2026-11-17: asked to plot the bands too thin to see; on the zoomed chart that followed,
  //: "Not useful. Keep this as a footnote". So the fullest levels (crushed, full, not accepting)
  // get one footnote line with their shares at the most crowded point, and no chart.
  const fullest = bands.filter((b) => ["crushed", "full", "not_accepting"].includes(b.k) && b.pts.some((p) => p.v > 0));
  if (!fullest.length) return svg;
  const fmtZ = (v) => (v === 0 ? "0%" : v < 0.1 ? `${+v.toFixed(2)}%` : v < 1 ? `${+v.toFixed(1)}%` : `${Math.round(v)}%`);
  return svg + `<p class="key-line">Fullest levels at ${where}: ${fullest.slice().reverse().map((b) => `${swatch([b.k, b.name, b.fill])} ${fmtZ(b.pts[fi].v)}`).join(" &nbsp;")}</p>`;
}
/** levelsChart once per direction, side by side on a laptop and stacked on a phone, as alongCharts lays them out. */
export function levelsPair(dirs, { by = "hour", label = "Muni" } = {}) {
  const parts = Object.keys(dirs).sort().map((d) => ({ title: dirs[d].direction ? `${dirs[d].direction}${dirs[d].to ? ` to ${dirs[d].to}` : ""}` : `Direction ${d}`, rows: dirs[d][by === "hour" ? "hours" : "tenths"] }));
  const one = (W) => parts.map((p) => `<div class="al-panel"><p class="al-title">${esc(p.title)}</p>${levelsChart(p.rows, W, { by, label: `${label}, ${p.title}` })}</div>`).join("");
  return parts.length > 1 ? `<div class="cw"><div class="al-pair">${one(325)}</div></div><div class="cn">${one(350)}</div>` : both((W) => one(W));
}

/**
 * A line's monthly figures from muni.json's lines[line].trend over [from, to] (YYYY-MM), each series a stepped line
 * with its newest figure printed at the end, and SFMTA's service changes as dashed rules numbered at the top, each
 * number linked to SFMTA's announcement (Bryan, 2026-11-16: "show crowding also in the top level
 * trends, and also show the number of busses midday and during peak hours, along with links to key service changes
 * from MTA"). series: [{ key, name, color, ink }]; changes: [{ n, at (YYYY-MM-DD), url, text }].
 */
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (d) => new Date(Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, d.length > 7 ? +d.slice(8, 10) : 15));
export function monthChart(trend, series, W, { x0, x1, unit = 168, yLabel, pct = false, changes = [], label = "Muni", outage = false, empty = "No figures in this period." }) {
  // Every chart in a line's Trends section shares one time axis (Bryan, 2026-11-16: "Make sure all
  // of the horizontal axes line up in this section"): the period's own [x0, x1] and periodChart's ticks and margins.
  // Each month is a step from its first day to the next month's, clipped to the period; a month with no figure is blank.
  const mStart = (ym) => new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7) - 1, 1));
  const mEnd = (ym) => new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7), 1));
  const rows = trend.filter((t) => mEnd(t.month) > x0 && mStart(t.month) <= x1);
  const has = series.filter((s) => rows.some((t) => t[s.key] != null));
  if (!has.length) return `<p class="verdict-note">${empty}</p>`;
  const narrow = W < 500, H = narrow ? 170 : 180, mT = 22, mB = 26;
  const vals = rows.flatMap((t) => has.map((s) => t[s.key])).filter((v) => v != null);
  const top = pct ? Math.max(10, Math.ceil(Math.max(...vals) / 5) * 5 + 2) : Math.ceil(Math.max(...vals) * 1.2);
  const fmt = (v) => (pct ? `${Math.round(v)}%` : sig2(v));
  // a series' steps: two points a month, a NaN between months with no figure so the line breaks there
  const steps = (k) => rows.flatMap((t) => (t[k] == null ? [{ m: mStart(t.month), v: NaN }] : [{ m: mStart(t.month), v: t[k] }, { m: new Date(Math.min(mEnd(t.month) - 1, +x1)), v: t[k] }]));
  // each series' newest figure printed just above its last step, inside the plot; two within 12 pixels pushed apart
  const per = top / (H - mT - mB);
  const ends = has.map((s) => { const t = [...rows].reverse().find((r) => r[s.key] != null); return { s, at: new Date(Math.min(mEnd(t.month) - 1, +x1)), v: t[s.key], off: 0 }; });
  // stacked from the highest down, each at least 13 pixels under the one above
  [...ends].sort((a, b) => b.v - a.v).reduce((above, e) => { if (above != null && above - e.v < 13 * per) e.off = above - 13 * per - e.v; return e.v + e.off; }, null);
  const vis = changes.filter((c) => day(c.at) >= x0 && day(c.at) <= x1);
  return plotSVG({
    width: W, height: H, marginLeft: 34, marginRight: 10, marginTop: mT, marginBottom: mB, style: axisStyle,
    x: { type: "time", domain: [x0, x1], label: null, tickSize: 0, ticks: narrow ? 3 : 6, tickFormat: (d) => unit >= 168 ? String(d.getUTCFullYear()) : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) },
    y: { domain: [0, top], label: yLabel, labelArrow: false, grid: true, ticks: 4, tickSize: 0, tickFormat: pct ? (v) => `${v}%` : undefined },
    marks: [
      outage ? Plot.rectX([0], { x1: () => Math.max(+x0, +mStart(OUTAGE[0])), x2: () => Math.min(+x1, +mEnd(OUTAGE[1])), y1: 0, y2: top, fill: "var(--raised)", filter: () => mStart(OUTAGE[0]) < x1 && mEnd(OUTAGE[1]) > x0 }) : null,
      Plot.ruleX(vis, { x: (c) => day(c.at), stroke: "var(--muted)", strokeDasharray: "2 3", strokeWidth: 1 }),
      Plot.text(vis, { x: (c) => day(c.at), y: top, text: (c) => String(c.n), dy: -10, fontSize: 11.5, fontWeight: 700, fill: "var(--accent)", href: "url", target: "_blank", title: (c) => `${c.at}: ${c.text}` }),
      ...has.map((s) => Plot.lineY(steps(s.key), { x: "m", y: "v", stroke: s.color, strokeWidth: 1.8, strokeDasharray: s.dash, clip: true })),
      Plot.text(ends, { x: "at", y: (e) => e.v + e.off, text: (e) => `${e.s.name} ${fmt(e.v)}`, dy: -8, textAnchor: "end", fontSize: 11, fontWeight: 600, fill: (e) => e.s.ink, ...HALO }),
    ],
  }, { label: `${label}: ${ends.map((e) => `${e.s.name.toLowerCase()} ${fmt(e.v)} in ${e.at.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })}`).join(", ")}${vis.length ? `; ${vis.length} SFMTA service change${vis.length > 1 ? "s" : ""} marked` : ""}.` });
}
/** The time axis periodChart draws for a period's points, for the charts that line up under it. */
export const periodDomain = (points) => (points?.length ? [parseT(points[0].t), parseT(points.at(-1).t)] : null);
export function hourChart(rows, W, { label = "Muni" } = {}) {
  const hrs = rows.filter((r) => r.ewt != null && r.hour >= 6);
  if (!hrs.length) return "";
  // an hour with no split (no tracked-trip timetable in its frequent stop-hours) draws as one bar
  const parts = hrs.flatMap((r) => (r.spacing == null ? [{ h: r.hour, k: "Total", v: r.ewt }] : [
    { h: r.hour, k: "Uneven spacing", v: r.spacing }, { h: r.hour, k: "Missing buses", v: r.missing }, { h: r.hour, k: "Weighting", v: r.weighting }]));
  const top = Math.ceil(Math.max(...hrs.map((r) => Math.max(r.ewt, (r.spacing ?? 0) + Math.max(0, r.missing ?? 0)))) * 2) / 2 + 0.5;
  // the bottom reaches a below-zero bar (a line's hour that beat the timetable's gaps) as well as the weighting
  const bottom = Math.min(0, Math.floor(Math.min(...hrs.map((r) => Math.min(r.weighting ?? 0, r.spacing == null ? r.ewt : 0))) * 4) / 4);
  const narrow = W < 500;
  return plotSVG({
    width: W, height: narrow ? 210 : 220, marginLeft: 34, marginRight: 8, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { type: "band", domain: hrs.map((r) => r.hour), tickFormat: (h) => (narrow && h % 3 ? "" : hourLabel(h)), label: null, tickSize: 0, padding: 0.15 },
    y: { domain: [bottom, top], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.barY(parts, { x: "h", y: "v", fill: (d) => (d.k === "Uneven spacing" ? C.spacing : d.k === "Missing buses" ? C.missing : d.k === "Weighting" ? C.weighting : C.one), fillOpacity: 0.75, order: ["Uneven spacing", "Missing buses", "Weighting", "Total"] }),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.text(hrs.filter((r) => !narrow || r.hour % 2 === 0), { x: "hour", y: (r) => Math.max(0, r.ewt, (r.spacing ?? 0) + Math.max(0, r.missing ?? 0)), text: (r) => sig2(r.ewt), dy: -7, fontSize: narrow ? 9.5 : 11, fill: "var(--ink)" }),
    ],
  }, { label: `${label}: excess wait by hour of day, from ${sig2(Math.min(...hrs.map((r) => r.ewt)))} to ${sig2(Math.max(...hrs.map((r) => r.ewt)))} minutes.` });
}

/** Citywide excess wait by hour of day as one line, the figure printed at each hour (Bryan, 2026-11-17, thread
 *  60fj6jh2pwnt: "No need to split by cause here"). */
export function hourLineChart(rows, W, { label = "Muni" } = {}) {
  const hrs = rows.filter((r) => r.ewt != null && r.hour >= 6);
  if (!hrs.length) return "";
  const narrow = W < 500, hi = Math.ceil(Math.max(...hrs.map((r) => r.ewt)) * 2) / 2 + 0.5, lo = Math.min(0, Math.floor(Math.min(...hrs.map((r) => r.ewt)) * 2) / 2);
  return plotSVG({
    width: W, height: narrow ? 200 : 210, marginLeft: 34, marginRight: 12, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { domain: [6, 22], inset: narrow ? 10 : 14, label: null, tickSize: 0, ticks: narrow ? [6, 9, 12, 15, 18, 21] : [6, 8, 10, 12, 14, 16, 18, 20, 22], tickFormat: hourLabel },
    y: { domain: [lo, hi], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.lineY(hrs, { x: "hour", y: "ewt", stroke: C.one, strokeWidth: 1.8 }),
      Plot.dot(hrs, { x: "hour", y: "ewt", r: 2.5, fill: C.one }),
      Plot.text(hrs.filter((r, i) => !narrow || i % 2 === 0), { x: "hour", y: "ewt", text: (r) => sig2(r.ewt), dy: -9, fontSize: narrow ? 9.5 : 11, fill: "var(--ink)", ...HALO }),
    ],
  }, { label: `${label}: excess wait by hour of day, from ${sig2(Math.min(...hrs.map((r) => r.ewt)))} to ${sig2(Math.max(...hrs.map((r) => r.ewt)))} minutes.` });
}

/**
 * One direction of a line: excess wait by clock hour (down) and tenth of the route (across), each cell shaded on one
 * light-to-dark ramp drawn from the site's --seq colours and printing its figure to a tenth of a minute (Bryan,
 * 2026-11-17: "an inbound and outbound by time and along route heat map"). The scale is fixed,
 * 0 to 3 minutes and over, so one shade means one wait on every line and period; a wait under the timetable's takes
 * the palest shade. cells are site_data.py's heat triples, [hour, tenth, minutes].
 */
export const HEAT = { domain: [0, 1.5, 3], range: ["#f4efe6", "#c8a25e", "#9c5f3c"] };
export function heatChart(cells, W, { label = "Muni" } = {}) {
  if (!cells?.length) return `<p class="verdict-note">Too few departures in this period.</p>`;
  const narrow = W < 500, rows = cells.map(([hour, tenth, ewt]) => ({ hour, tenth, ewt }));
  const hours = [...new Set(rows.map((r) => r.hour))].sort((a, b) => a - b);
  const hrs = []; for (let h = hours[0]; h <= hours.at(-1); h++) hrs.push(h);
  const name = (t) => (t === 0 ? "First" : t === 9 ? "Last" : String(t + 1));
  const fig = (v) => { const r = Math.round(v * 10) / 10; return r === 0 ? "0" : r.toFixed(1); };
  return plotSVG({
    width: W, height: 40 + hrs.length * (narrow ? 17 : 18), marginLeft: 38, marginRight: 4, marginTop: 4, marginBottom: 36, style: { fontSize: narrow ? 10.5 : 11 },
    x: { type: "band", domain: [...Array(10).keys()], tickFormat: name, label: "Tenth of the route, first stop to last", labelAnchor: "center", labelOffset: 32, tickSize: 0, padding: 0.04 },
    y: { type: "band", domain: hrs, tickFormat: hourLabel, label: null, tickSize: 0, padding: 0.06 },
    color: { type: "linear", domain: HEAT.domain, range: HEAT.range, clamp: true },
    marks: [
      Plot.cell(rows, { x: "tenth", y: "hour", fill: "ewt", inset: 0 }),
      Plot.text(rows, { x: "tenth", y: "hour", text: (r) => fig(r.ewt), fontSize: narrow ? 9.5 : 10, fill: (r) => (r.ewt >= 2.2 ? "#fff" : "var(--ink)") }),
    ],
  }, { label: `${label}: excess wait by hour of day and tenth of the route, from ${fig(Math.min(...rows.map((r) => r.ewt)))} to ${fig(Math.max(...rows.map((r) => r.ewt)))} minutes.` });
}
/** The two directions' heat maps, side by side on a laptop and stacked on a phone, titled as alongCharts titles them. */
export function heatPair(dirs, cells, { label = "Muni" } = {}) {
  const parts = ["0", "1"].map((d) => { const v = dirs?.[d]; return { title: v?.direction ? `${v.direction}${v.to ? ` to ${v.to}` : ""}` : d === "0" ? "Outbound" : "Inbound", cells: cells?.[d] }; });
  const one = (W) => parts.map((p) => `<div class="al-panel"><p class="al-title">${esc(p.title)}</p>${heatChart(p.cells, W, { label: `${label}, ${p.title}` })}</div>`).join("");
  return `<div class="cw"><div class="al-pair">${one(325)}</div></div><div class="cn">${one(350)}</div>`;
}
export const HEAT_KEY = `Excess wait at the stop: <span class="ramp heat"></span> ${HEAT.domain[0]} to ${HEAT.domain[2]}+ min`;

/** Excess wait by hour of day as the median across lines with the 10th to 90th percentile band. */
export function hourBandChart(rows, W, { label = "Muni" } = {}) {
  const hrs = rows.filter((r) => r.p50 != null && r.hour >= 6);
  if (!hrs.length) return "";
  const hi = Math.ceil(Math.max(...hrs.map((r) => r.p90)) * 2) / 2, lo = Math.min(0, Math.floor(Math.min(...hrs.map((r) => r.p10)) * 2) / 2), narrow = W < 500;
  return plotSVG({
    width: W, height: narrow ? 210 : 220, marginLeft: 34, marginRight: 8, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { domain: [6, 22], label: null, tickSize: 0, ticks: narrow ? [6, 9, 12, 15, 18, 21] : [6, 8, 10, 12, 14, 16, 18, 20, 22], tickFormat: hourLabel },
    y: { domain: [lo, hi], label: "Excess Wait (minutes)", labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      Plot.areaY(hrs, { x: "hour", y1: "p10", y2: "p90", fill: "#4269d0", fillOpacity: 0.16 }),
      Plot.lineY(hrs, { x: "hour", y: "p50", stroke: "#4269d0", strokeWidth: 1.8 }),
      Plot.dot(hrs, { x: "hour", y: "p50", r: 2.5, fill: "#4269d0" }),
      Plot.text(hrs.filter((r, i) => !narrow || i % 2 === 0), { x: "hour", y: "p50", text: (r) => sig2(r.p50), dy: -9, fontSize: narrow ? 9.5 : 11, fill: "var(--ink)", ...HALO }),
    ],
  }, { label: `${label}: median excess wait across lines by hour of day, with the 10th to 90th percentile.` });
}

/** Excess wait by hour as a percent of the timetable's own wait (Bryan, 2026-11-09: "% longer than expected"):
 *  bars for the pooled figure, on the same hour axis as hourChart. */
export function hourPctChart(rows, W, { label = "Muni" } = {}) {
  const hrs = rows.filter((r) => r.ewt != null && r.scheduled && r.hour >= 6).map((r) => ({ hour: r.hour, pct: (100 * r.ewt) / r.scheduled }));
  if (!hrs.length) return "";
  const top = Math.ceil(Math.max(...hrs.map((r) => r.pct)) / 10) * 10 + 10, narrow = W < 500;
  const bottom = Math.min(0, Math.floor(Math.min(...hrs.map((r) => r.pct)) / 10) * 10); // a line's hour can beat the timetable
  return plotSVG({
    width: W, height: narrow ? 190 : 200, marginLeft: 34, marginRight: 8, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { type: "band", domain: hrs.map((r) => r.hour), tickFormat: (h) => (narrow && h % 3 ? "" : hourLabel(h)), label: null, tickSize: 0, padding: 0.15 },
    y: { domain: [bottom, top], label: "% longer", labelArrow: false, grid: true, ticks: 4, tickSize: 0, tickFormat: (v) => `${v}%` },
    marks: [
      Plot.barY(hrs, { x: "hour", y: "pct", fill: "var(--ink)", fillOpacity: 0.32 }),
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.text(hrs.filter((r) => !narrow || r.hour % 2 === 0), { x: "hour", y: (r) => Math.max(0, r.pct), text: (r) => `${Math.round(r.pct)}%`, dy: -7, fontSize: narrow ? 8.5 : 10.5, fill: "var(--ink)" }),
    ],
  }, { label: `${label}: waits longer than the timetable promises by hour of day, from ${Math.round(Math.min(...hrs.map((r) => r.pct)))}% to ${Math.round(Math.max(...hrs.map((r) => r.pct)))}%.` });
}

/** The same percent as the median across lines with the 10th to 90th percentile band, on hourBandChart's axis. */
export function hourPctBandChart(rows, W, { label = "Muni" } = {}) {
  const hrs = rows.filter((r) => r.q50 != null && r.hour >= 6);
  if (!hrs.length) return "";
  const hi = Math.ceil(Math.max(...hrs.map((r) => r.q90)) / 10) * 10, narrow = W < 500;
  return plotSVG({
    width: W, height: narrow ? 190 : 200, marginLeft: 34, marginRight: 8, marginTop: 26, marginBottom: 26, style: axisStyle,
    x: { domain: [6, 22], label: null, tickSize: 0, ticks: narrow ? [6, 9, 12, 15, 18, 21] : [6, 8, 10, 12, 14, 16, 18, 20, 22], tickFormat: hourLabel },
    y: { domain: [Math.min(0, Math.floor(Math.min(...hrs.map((r) => r.q10)) / 10) * 10), hi], label: "% longer", labelArrow: false, grid: true, ticks: 4, tickSize: 0, tickFormat: (v) => `${v}%` },
    marks: [
      Plot.areaY(hrs, { x: "hour", y1: "q10", y2: "q90", fill: "#4269d0", fillOpacity: 0.16 }),
      Plot.lineY(hrs, { x: "hour", y: "q50", stroke: "#4269d0", strokeWidth: 1.8 }),
      Plot.dot(hrs, { x: "hour", y: "q50", r: 2.5, fill: "#4269d0" }),
      Plot.text(hrs.filter((r, i) => !narrow || i % 2 === 0), { x: "hour", y: "q50", text: (r) => `${Math.round(r.q50)}%`, dy: -9, fontSize: narrow ? 9.5 : 11, fill: "var(--ink)", ...HALO }),
    ],
  }, { label: `${label}: median percent longer than the timetable across lines by hour of day, with the 10th to 90th percentile.` });
}

const parseT = (t) => new Date(Date.UTC(+t.slice(0, 4), +t.slice(4, 6) - 1, +t.slice(6, 8), t.length > 8 ? +t.slice(9, 11) : 12));
/** One measure over the period at the granularity muni_detail.py chose. Night hours and empty days stay gaps. */
export function periodChart(points, key, W, { unit, color = "#4269d0", yLabel, lowerBound = null, changes = [] }) {
  const [k10, k50, k90] = [`${key}_p10`, `${key}_p50`, `${key}_p90`];
  const pts = points.filter((p) => p[k50] != null);
  if (pts.length < 2) return `<p class="verdict-note">Too few measured ${unit === 24 ? "days" : "hours"} to draw.</p>`;
  // A break wherever the next point isn't the next step of the clock (nights, days with nothing measured).
  const step = unit * 3600e3;
  const rows = [];
  points.forEach((p, i) => {
    const t = parseT(p.t);
    if (i && t - parseT(points[i - 1].t) > step * 1.01) rows.push({ t: new Date(t - 1), v: NaN });
    rows.push({ t, v: p[k50] ?? NaN, lo: p[k10] ?? NaN, hi: p[k90] ?? NaN });
  });
  const vals = pts.map((p) => p[k50]);
  // lowerBound "fit" fits the axis to the data, for a measure that isn't a count (speed); a number fixes it.
  // A measure that can dip below zero (excess wait, when buses beat the timetable's gaps) gets the half-minute below
  // its lowest point, not a whole minute, so the axis doesn't read as starting at -1 (UX review, 2026-11-10).
  const lo = lowerBound === "fit" ? Math.floor(Math.min(...pts.map((p) => p[k10] ?? p[k50]))) : lowerBound ?? Math.min(0, Math.floor(Math.min(...pts.map((p) => p[k10] ?? p[k50])) * 2) / 2);
  const hi = Math.ceil(Math.max(...pts.map((p) => p[k90])) * 2) / 2;
  const narrow = W < 500;
  const first = parseT(points[0].t), last = parseT(points.at(-1).t);
  return plotSVG({
    width: W, height: narrow ? 170 : 180, marginLeft: 34, marginRight: 10, marginTop: 22, marginBottom: 26, style: axisStyle,
    x: { type: "time", domain: [first, last], label: null, tickSize: 0, ticks: narrow ? 3 : 6, tickFormat: (d) => unit >= 168 ? String(d.getUTCFullYear()) : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) },
    y: { domain: [lo, hi], label: lo > 0 ? `${yLabel} (axis starts at ${lo})` : yLabel, labelArrow: false, grid: true, ticks: 4, tickSize: 0 },
    marks: [
      lo < 0 ? Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }) : null,
      Plot.areaY(rows, { x: "t", y1: "lo", y2: "hi", fill: color, fillOpacity: 0.15 }),
      Plot.lineY(rows, { x: "t", y: "v", stroke: color, strokeWidth: unit === 1 ? 1 : 1.4 }),
      // SFMTA's service changes in the period, numbered as monthChart numbers them (the line page's list is the key)
      ...((vis) => [
        Plot.ruleX(vis, { x: (c) => day(c.at), stroke: "var(--muted)", strokeDasharray: "2 3", strokeWidth: 1 }),
        Plot.text(vis, { x: (c) => day(c.at), y: hi, text: (c) => String(c.n), dy: -10, fontSize: 11.5, fontWeight: 700, fill: "var(--accent)", href: "url", target: "_blank", title: (c) => `${c.at}: ${c.text}` }),
      ])(changes.filter((c) => day(c.at) >= first && day(c.at) <= last)),
    ],
  }, { label: `${yLabel}: median over the period from ${sig2(Math.min(...vals))} to ${sig2(Math.max(...vals))}, with the 10th to 90th percentile band.` });
}

/**
 * One of a line's monthly figures over the last two years, word-sized for a list row (Tufte's sparkline). The
 * y axis fits the line's own range rather than starting at zero, and the box is 80 by 34 so a typical month-to-month
 * step draws near 45 degrees (Cleveland's banking): across the listed lines the median step is about a fifth of the
 * range, which in 30 pixels of height over 23 steps of 3.4 pixels is close to one to one. Bryan, 2026-11-10: "Spark
 * line aspect ratio is hard to read." The dot is the latest month.
 */
// A line's sparkline covers the period chosen up top (Bryan, 2026-11-10: "This should follow the date selector up
// top"). It reads the line's own points for that period (muni-lines.json) and averages them into days for 30 days,
// weeks for 90 days and a year, and months for 5 years and Max, so each sparkline has a few dozen points.
const BUCKET = { "30": "day", "90": "week", "365": "week", "1825": "month", max: "month" };
const tDate = (t) => new Date(Date.UTC(+t.slice(0, 4), +t.slice(4, 6) - 1, +t.slice(6, 8)));
/** One line's sparkline for period w, of key "ewt" or "mph". Empty when the period has fewer than 3 buckets. */
export function sparkFor(line, key, w, label) {
  const pts = detail.lines[line]?.[w]?.points || [], by = new Map();
  for (const p of pts) {
    if (p[key] == null) continue;
    const d = tDate(p.t), b = BUCKET[w];
    const k = b === "day" ? +d : b === "month" ? Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 15) : +d - (((d.getUTCDay() + 6) % 7) * 864e5);
    const a = by.get(k) || by.set(k, [0, 0]).get(k);
    a[0] += p[key]; a[1] += 1;
  }
  const row = [...by].sort((a, b) => a[0] - b[0]).map(([k, [s, n]]) => ({ m: new Date(k), v: s / n }));
  return sparkRows(row, key, label);
}
export function spark(trend, key = "ewt", { label = "Excess wait over the last two years", months = 24 } = {}) {
  const row = (months ? trend.slice(-months) : trend).map((t) => ({ m: pm(t.month), v: t[key] ?? NaN }));
  return sparkRows(row, key, label);
}
// A monthly series ([[month, value], ...]) as a sparkline over the period, or over the newest 12 months when the period
// is shorter, ending at the period's last month. For each line's weekday riders (SFMTA's settled months) and on-time
// share (Bryan, 2026-11-16).
function sparkMonthly(all, w, key, label) {
  const end = data.windows[w].months[1], n = { "30": 12, "90": 12, "365": 12, "1825": 60 }[w] ?? Infinity;
  const ms = (all || []).filter(([m]) => m <= end).slice(-n);
  return ms.length ? sparkRows(ms.map(([m, v]) => ({ m: pm(m), v })), key, `${label} by month, ${span([ms[0][0], ms.at(-1)[0]])}`) : "";
}
export const sparkRiders = (line, w) => sparkMonthly(data.ridership.lineMonths?.[line], w, "riders", "Weekday riders");
export const sparkOnTime = (line, w) => sparkMonthly(data.ontime.lineMonths?.[line], w, "onTime", "Share on time");
// Each frequent line's excess wait, by month (site_data.py allService.lineMonths).
export const sparkWaitAll = (line, w) => sparkMonthly(data.allService?.lineMonths?.[line], w, "ewt", "Excess wait");
function sparkRows(row, key, label) {
  const ok = row.filter((r) => !isNaN(r.v));
  if (ok.length < 3) return "";
  const lo = Math.min(...ok.map((r) => r.v)), hi = Math.max(...ok.map((r) => r.v)), pad = Math.max((hi - lo) * 0.08, key === "mph" ? 0.1 : 0.05);
  return plotSVG({
    width: 80, height: 34, margin: 3, x: { type: "time", axis: null }, y: { axis: null, domain: [lo - pad, hi + pad] },
    marks: [Plot.lineY(row, { x: "m", y: "v", stroke: "var(--muted)", strokeWidth: 1.3 }), Plot.dot(ok.slice(-1), { x: "m", y: "v", r: 2.2, fill: "var(--ink)" })],
  }, { className: "spark", label: `${label}, from ${sig2(ok[0].v)} to ${sig2(ok.at(-1).v)}.` });
}

// ---- The line picker --------------------------------------------------------
//
// Bryan, 2026-11-09: a text field you can type in, matching number and name
// ("Judah" finds N), with its list grouped trains, buses, cable cars. Choosing
// a line fires "muni:line"; a page decides what that does.

export function picker({ id = "line-pick", value = "", lines = LINES, label = "Line" } = {}) {
  const items = GROUPS.map((g) => {
    const ls = lines.filter((l) => g.modes.includes(MODE(l)));
    return ls.length ? `<li class="lp-group" role="presentation">${g.label}</li>${ls.map((l) =>
      `<li role="option" data-line="${esc(l)}" data-name="${esc(lineName(l).toLowerCase())}">${esc(lineName(l))}</li>`).join("")}` : "";
  }).join("");
  return `<div class="lp" data-picker>
  <label class="lp-label" for="${id}">${esc(label)}</label>
  <input id="${id}" type="search" role="combobox" aria-expanded="false" aria-controls="${id}-list" aria-autocomplete="list" autocomplete="off" placeholder="Type a line, e.g. N or 38R" value="${esc(value)}">
  <ul id="${id}-list" class="lp-list" role="listbox" hidden>${items}</ul>
</div>`;
}
export const PICKER_SCRIPT = `<script>
document.querySelectorAll("[data-picker]").forEach(function (box) {
  var input = box.querySelector("input"), list = box.querySelector("ul"), opts = [].slice.call(list.querySelectorAll("[role=option]")), active = -1;
  function shown() { return opts.filter(function (o) { return !o.hidden; }); }
  // the box opens showing every line until the reader types (a phone tap shouldn't need clearing the chosen line)
  var typed = false;
  function filter() {
    var q = typed ? input.value.trim().toLowerCase() : "";
    opts.forEach(function (o) { o.hidden = !!q && o.dataset.line.toLowerCase().indexOf(q) !== 0 && o.dataset.name.indexOf(q) === -1; });
    [].slice.call(list.querySelectorAll(".lp-group")).forEach(function (g) {
      var n = g.nextElementSibling, any = false;
      while (n && !n.classList.contains("lp-group")) { if (!n.hidden) any = true; n = n.nextElementSibling; }
      g.hidden = !any;
    });
    // a typed line code ("14") highlights that line, so Enter takes it rather than the 14R listed beside it
    // before any typing, the line already chosen is highlighted and scrolled into view
    var exact = q ? shown().findIndex(function (o) { return o.dataset.line.toLowerCase() === q; })
      : shown().findIndex(function (o) { return o.textContent === input.value; });
    mark(exact);
    // Bryan, 2026-11-10: "Search should also filter the table". A page's list listens and hides rows that don't match.
    window.dispatchEvent(new CustomEvent("muni:query", { detail: q }));
  }
  function open() { list.hidden = false; input.setAttribute("aria-expanded", "true"); filter(); }
  function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); }
  function mark(i) { var s = shown(); active = i; opts.forEach(function (o) { o.classList.remove("on"); }); if (s[i]) { s[i].classList.add("on"); s[i].scrollIntoView({ block: "nearest" }); } }
  function choose(o) { input.value = o.textContent; typed = false; close(); input.blur(); window.dispatchEvent(new CustomEvent("muni:query", { detail: o.dataset.line.toLowerCase() })); window.dispatchEvent(new CustomEvent("muni:line", { detail: o.dataset.line })); }
  input.addEventListener("focus", function () { typed = false; open(); });
  input.addEventListener("input", function () { typed = true; open(); });
  input.addEventListener("keydown", function (e) {
    var s = shown();
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) open(); mark(Math.min(active + 1, s.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mark(Math.max(active - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (s[active] || s.length === 1) choose(s[active] || s[0]); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", function (e) { var o = e.target.closest("[role=option]"); if (o) { e.preventDefault(); choose(o); } });
  document.addEventListener("click", function (e) { if (!box.contains(e.target)) close(); });
});
</script>`;

const clock = (h) => (h === 0 || h === 24 ? "midnight" : h === 12 ? "noon" : h < 12 ? `${h}am` : `${h - 12}pm`);
/**
 * One line saying whether a line is judged by the gap between buses or by the timetable (Bryan, 2026-11-10:
 * "Show somewhere what the scheduling target is. Is it by gap or specific times?"), from site_data.py's schedule: by
 * SFMTA's line types (freq_rule.py), a Connector or Owl line by the timetable, every other line by the gap, with the
 * weekday hours its busiest stop has a bus.
 */
// Returns one sentence per paragraph, in Bryan's wording from his page edit on the 8BX page (2026-11-10, thread
// 1hhyom62onf6): "Scheduled for every 8 min between 7am–10am and 4pm–7pm on weekdays." / "At other hours, the 8BX is
// scheduled by timetable".
export function scheduleLine(s, line) {
  if (!s) return ["Not on SFMTA's current schedule."]; // a retired line (the KT): no hours to name
  if (s.type === "Connector" || s.type === "Owl") return [`The ${line} is ${s.type === "Owl" ? "an Owl" : "a Connector"} line, scheduled by timetable at all hours.`];
  if (!s.gapHours?.length) return [`The ${line} is scheduled by gap.`];
  const hrs = s.gapHours.map(([a, b]) => `${clock(a)}–${clock(b)}`).join(" and ");
  return [`Scheduled for every ${s.gap} min between ${hrs} on weekdays.`];
}

// ---- Notes under figures -------------------------------------------------------

export const SRC_511 = '<a href="https://511.org/open-data/transit">511 SF Bay historic stop observations</a>';
export const SRC_SFMTA = '<a href="https://data.sfgov.org/d/kc49-udxn">SFMTA, scheduled service hours delivered (Controller\'s scorecard, DataSF)</a>';
// The ridership chart draws SFMTA's systemwide weekday figure from the same scorecard (site_data.py, measure 428);
// the route-by-month file only checks it.
export const SRC_RIDERS_SYS = '<a href="https://data.sfgov.org/d/kc49-udxn">SFMTA, average weekday boardings (Controller\'s scorecard, DataSF)</a>';
export const SRC_RIDERS = '<a href="https://www.sfmta.com/reports/average-daily-muni-boardings-route-and-month-pre-pandemic-present">SFMTA, Muni boardings by route and month</a>';
export const SRC_SAT = '<a href="https://www.sfmta.com/reports/customer-rating-overall-customer-satisfaction-muni">SFMTA, Muni Rider Survey</a>';
// Which weekdays the live crowding figures cover, as a range with only the missing weekdays named and the full list in
//   the hover title (site_data.py day_span): "on 4 weekdays, 10 to 13 November 2026 (12 Nov missing, 511 outage)".
export function crowdDaysText(c) {
  return `on ${c.n} weekday${c.n === 1 ? "" : "s"}, ${c.days}${c.missing ? ` (${c.missing})` : ""}`;
}
export function crowdDays(c) {
  return `<span title="${esc(`The weekdays: ${c.list}`)}">${esc(crowdDaysText(c))}</span>`;
}
export const SRC_CROWD = '<a href="https://www.sfmta.com/reports/percent-daily-muni-trips-crowded-route-and-month">SFMTA, percent of daily Muni trips crowded by route and month</a>';
export const SRC_GTFS = '<a href="https://www.sfmta.com/reports/gtfs-transit-data">SFMTA GTFS schedule</a>';
// `how` names the About section for the figure. It isn't emitted as data-how: the layout would turn it into a
// "How we worked out ... is on About the Data" line, a second About link beside the breadcrumb's (UX review, 2026-11-10).
export const cite = (fors, how, items) =>
  `<ul class="cite" data-for="${fors}">${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;

// The dashboard's pages, as the last step of the breadcrumb on every Muni page (src/directory.mjs fillCrumbs reads
// them from the overview's listing). The breadcrumb is the only navigation row (Bryan, 2026-11-16: "Can we just have
// the top breadcrumbs and keep that as standard practice"), so the tab bar it replaces is gone. A line's own page,
// and the Line Detail page, sit under Lines.
export const DASH = "Muni Performance Dashboard";
export const PAGES = [[BASE, "Overview"], [`${BASE}/lines`, "Lines", [`${BASE}/line`]], [`${BASE}/optimizer`, "Upgrade a Bus Line"], [`${BASE}/about`, "About This Data"]];

/** The key to the two causes' colours, for charts that don't label them in place. */
export const CAUSE_KEY = `<span class="sw" style="background:${C.spacing}"></span>Uneven spacing <span class="sw" style="background:${C.missing}"></span>Missing buses`;

// Empty: the breadcrumb's About This Data is the one link to the method (UX review, 2026-11-10).
export const SOURCES_NOTE = "";

// ---- Styles ------------------------------------------------------------------

export const CSS = `<style>
/* Bryan, 2026-11-17: "keep the navbar at the top fixed and available as I scroll". */
.masthead { position: sticky; top: 0; z-index: 30; background: var(--paper); padding-top: 12px; }
html { scroll-padding-top: 80px; }
.wv { display: none; }
html[data-days="30"] .wv[data-w="30"],
html[data-days="90"] .wv[data-w="90"], html:not([data-days]) .wv[data-w="365"], html[data-days="365"] .wv[data-w="365"],
html[data-days="1825"] .wv[data-w="1825"], html[data-days="max"] .wv[data-w="max"] { display: block; }
.wi { display: none; }
html[data-days="30"] .wi[data-w="30"], html[data-days="90"] .wi[data-w="90"], html:not([data-days]) .wi[data-w="365"], html[data-days="365"] .wi[data-w="365"],
html[data-days="1825"] .wi[data-w="1825"], html[data-days="max"] .wi[data-w="max"] { display: inline; }
.vv[data-v="dist"], html[data-view="dist"] .vv[data-v="plain"] { display: none; }
html[data-view="dist"] .vv[data-v="dist"] { display: block; }
.cn { display: none; }
@media (max-width: 640px) { .cw { display: none; } .cn { display: block; } }
.muni-top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; margin: 4px 0 10px; }
.muni-top .asof { color: var(--muted); font-size: 0.9rem; }
.draft-band { background: var(--seq-2-soft); border-left: 3px solid var(--seq-2); padding: 6px 12px; margin: 0 0 12px; font-size: 0.9rem; }
.seg { display: inline-flex; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
.period { display: inline-flex; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
.period button, .seg button { font: inherit; font-size: 0.88rem; padding: 5px 11px; border: 0; background: var(--paper); color: var(--ink); cursor: pointer; }
.period button + button, .seg button + button { border-left: 1px solid var(--rule); }
.period button[aria-pressed="true"], .seg button[aria-pressed="true"] { background: var(--ink); color: var(--paper); font-weight: 600; }
.k-scale { display: block; font-size: 0.8rem; color: var(--ink); margin: 2px 0 2px; line-height: 1.3; }
.ontime { font-size: 0.82rem; color: var(--muted); margin: 0 0 4px; }
.kpis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 4px 0 6px; }
.kpi { padding: 10px 12px; border-radius: 6px; background: var(--raised); display: flex; flex-direction: column; gap: 2px; min-height: 100px; }
.kpi .k-label { font-size: 0.82rem; color: var(--muted); line-height: 1.25; }
.kpi b { font-family: Archivo, sans-serif; font-size: 1.9rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
.kpi.pending b { font-size: 1.05rem; font-weight: 600; color: var(--muted); padding: 6px 0 4px; }
.kpi .k-sub { font-size: 0.82rem; line-height: 1.3; }
.chg { font-weight: 600; white-space: nowrap; }
.chg.better { color: var(--seq-3); }
.chg.worse { color: var(--seq-1); }
.chg.same, .chg.none { color: var(--muted); font-weight: 400; white-space: normal; }
.vs { color: var(--muted); }
@media (max-width: 640px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) {
  .kpis { gap: 6px; }
  .kpi { padding: 7px 8px; min-height: 0; }
  .kpi b { font-size: 1.35rem; }
  .kpi .k-label, .kpi .k-sub { font-size: 0.74rem; }
  .kpi.pending b { font-size: 0.86rem; }
}
.lp { position: relative; flex: 1 1 220px; max-width: 320px; }
.lp-label { position: absolute; left: -9999px; }
.lp input { width: 100%; box-sizing: border-box; font: inherit; font-size: 0.95rem; padding: 6px 10px 6px 30px; border: 1px solid var(--muted); border-radius: 6px; background: var(--paper) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2359626f' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m21 21-4.3-4.3'/%3E%3C/svg%3E") no-repeat 9px center; }
.lp-list { position: absolute; z-index: 20; left: 0; right: 0; top: 100%; margin: 2px 0 0; padding: 4px 0; list-style: none; max-height: 300px; overflow: auto; background: var(--paper); border: 1px solid var(--rule); border-radius: 6px; box-shadow: 0 6px 18px rgba(0,0,0,0.12); }
.lp-list li { padding: 5px 12px; font-size: 0.92rem; cursor: pointer; }
@media (max-width: 700px) { .lp-list li[role=option] { padding: 12px 12px; } .lp input { min-height: 44px; } }
.lp-list li.on, .lp-list li[role=option]:hover { background: var(--raised); }
.lp-list li.on { font-weight: 600; }
.lp-list .lp-group { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); cursor: default; padding-top: 8px; }
.muni-fig { margin: 6px 0 4px; }
.al-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.al-title { font-size: 0.85rem; font-weight: 600; margin: 4px 0 0; }
.muni-fig .plot-chart { margin: 4px 0; }
.key-line { font-size: 0.85rem; color: var(--muted); margin: 2px 0 0; }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: -1px; margin: 0 3px 0 0; }
.ramp { display: inline-block; width: 90px; height: 9px; border-radius: 2px; vertical-align: -1px; margin: 0 4px; background: linear-gradient(90deg, var(--map-1), var(--map-2), var(--map-3)); }
.ramp.heat { background: linear-gradient(90deg, #f4efe6, #c8a25e, #9c5f3c); border: 1px solid var(--rule); }
:root { --map-1: #35b779; --map-2: #31688e; --map-3: #440154; }
</style>`;

// Route lines and their badges: src/muni-routes.mjs, a module of its own so a page that draws Muni's lines (the Street
// Safety map's crime view) need not load the dashboard's data.
export { ROUTE_JS } from "./muni-routes.mjs";
