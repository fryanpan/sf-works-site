// How Muni is running: the overview. Built to docs/product/data-story-guidelines.md
// and tool-ux-guidelines.md. Method and caveats are on /transportation/muni/about.
//
// Bryan, 2026-11-16: "break this page up into sections and have the sections show up in left
// navigation panel", in the outline Ridership, then Performance with Overview, Wait Times, Speed and Crowding. The
// Overview's figures are only what riders feel ("busses being late, slow, or too crowded"), worded as a rider meets
// them, and, from the same thread, "some way to understand the expected wait time, not just the excess". Service hours
// delivered left the figures row ("aren't really very meaningful") and its chart sits under Wait Times, where a bus
// that never ran is the "missing buses" share of the wait.
//
// Bryan, 2026-11-10: riders and satisfaction first. Bryan, 2026-11-09: "everything that explains how you computed this
// should go into an 'about this data' page".

import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import {
  data, THROUGH, CSS, PERIOD_SCRIPT, periodSwitch, forPeriod, kpi, change, changeHtml,
  versus, periodLine, SRC_RIDERS, minutes, mph, span, sig2, both, causeChart, bandChart, speedChart, deliveredChart, SRC_SFMTA, pointsChange, forView, cite, SRC_511, SRC_GTFS, SOURCES_NOTE, hourLineChart, hourBandChart, speedHourChart, levelsChart, matchVs, positionChart, satisfactionChart, SRC_SAT, SRC_RIDERS_SYS, ridersByDayChart, perPeriodText,
  crowdDays, PAGES,
  DRAFT_NOTE, DATA_READ_ISO,
} from "../muni.mjs";
import * as lines from "./transportation-muni-lines.mjs";
import * as optimizer from "./transportation-muni-optimizer.mjs";

export const path = "/transportation/muni";
export const file = "transportation/muni/index.html";
// Published as a draft, kept out of the sitemap and every list (src/muni.mjs DRAFT_NOTE).
export const sitemap = false;
export const listing = { draft: true, title: "Muni Performance Dashboard", line: "Riders, waits, late buses, speed and crowding, citywide and by line.", parent: "section", order: 3, pages: PAGES, crumb: "Muni" }; // Bryan, 2026-11-16: "Breadcrumbs should just be Muni"
// The date the lists show beside this page: the one in its Draft band (src/page-dates.mjs).
export const dataUpdated = DATA_READ_ISO;

const wDef = data.windows["365"];
// Every wait figure here covers SFMTA's frequent lines, every line but Connector and Owl (freq_rule.py; Bryan,
//   2026-11-17: "SFMTA's line types"), by TfL's excess wait, each line weighted by its weekday
//   riders (site_data.py allService); Connector and Owl lines are reported by on time, in SFMTA's window (Bryan, 2026-11-17: "Report TfL's way", and on the window, "partly I want to
//   line up with rider experience and partly I want to line up with what busses are held to").
const A = data.allService;
const aDef = A.windows["365"];

// TfL's QSI Statistics Explained, 1.6 and 1.8: five or more buses an hour is high frequency, where riders "turn up at a
// bus stop randomly and not to have consulted a timetable", and every 15 minutes or more is low frequency.
// The city's scorecard, the source for SFMTA's split: "Connector and Owl routes are not measured by headway adherence".
const SRC_SCORECARD = '<a href="https://www.sf.gov/resource--2024--transit-and-street-safety-scorecard/percentage-of-evenly-spaced-muni-arrivals/">City scorecard, evenly spaced Muni arrivals</a>';
const SRC_TFL = '<a href="https://foi.tfl.gov.uk/FOI-0143-2122/QSI%20Statistics%20Explained%20v2.0%2009.12.13.pdf">Transport for London, QSI Statistics Explained (1.6, 1.8)</a>';

/** "1 in 5", for a share of buses. */
const oneIn = (s) => (s > 0 ? `1 in ${Math.round(1 / s)}` : "None");
const thousands = (n) => `${Math.round(n / 1000).toLocaleString("en-US")},000`;

// ---- How often buses come (site_data.py frequency): weekday riders on frequent lines and on Connector and Owl lines,
// by SFMTA's line types (freq_rule.py). Bryan, 2026-11-17: two bars, count first, percent smaller.
const F = data.frequency;

function freqChart(W, F = data.frequency) {
  const narrow = W < 500;
  const rows = [["Frequent arrivals (scheduled by gap)", F.frequent], ["Infrequent arrivals (scheduled by time)", F.infrequent]]
    .map(([name, n]) => ({ name, n, count: `${thousands(n)} riders`, pct: `${Math.round((100 * n) / F.total)}%` }));
  const charW = narrow ? 6.6 : 7.1; // about the count's width a character, to set the smaller percent after it
  return plotSVG({
    width: W, height: 120, marginLeft: 0, marginRight: narrow ? 130 : 150, marginTop: 4, marginBottom: 0, style: { fontSize: 12 },
    x: { axis: null, domain: [0, Math.max(...rows.map((r) => r.n))] },
    y: { axis: null, domain: rows.map((r) => r.name), paddingInner: 0.15, paddingOuter: 0 },
    marks: [
      Plot.barX(rows, { x: "n", y: "name", insetTop: 22, fill: (r) => (r.n === F.frequent ? "#4269d0" : "#efb118") }),
      Plot.text(rows, { x: 0, y: "name", text: "name", textAnchor: "start", dy: -16, fontSize: narrow ? 12 : 13, fill: "var(--ink)" }),
      Plot.text(rows, { x: "n", y: "name", text: "count", dx: 6, dy: 11, textAnchor: "start", fontSize: narrow ? 12 : 13, fontWeight: 700, fill: "var(--ink)" }),
      ...rows.map((r) => Plot.text([r], { x: "n", y: "name", text: "pct", dx: 10 + charW * r.count.length, dy: 11, textAnchor: "start", fontSize: 11, fill: "var(--muted)" })),
    ],
  }, { label: `Weekday Muni riders on frequent lines, ${rows[0].count} (${rows[0].pct}), and on Connector and Owl lines, ${rows[1].count} (${rows[1].pct}).` });
}

// ---- Crowding: the share of buses with standing room only or fuller, at the busiest hour ----
const FULLER = ["standing_room", "crushed", "full", "not_accepting"];
const crowdPeak = (() => {
  const h = data.crowdByHour?.hours || [];
  if (!h.length) return null;
  const r = h.map((x) => ({ hour: x.hour, s: FULLER.reduce((a, k) => a + (x[k] || 0), 0) / 100 }));
  return r.reduce((a, b) => (b.s > a.s ? b : a));
})();
const clock = (h) => (h === 12 ? "noon" : h < 12 ? `${h}am` : `${h - 12}pm`);

/** The change in the on-time share, in points, where more on time is better. */
const onTimeChange = (o) => o.before && pointsChange(o.now.onTime, o.before.onTime);
const OT_TARGET = Math.round(100 * data.ontime.target);

/** The change in the wait, in seconds or minutes (the extra wait moves and the scheduled wait barely does), longer being worse. */
function minChange(now, before) {
  const c = change(now, before, true);
  return c && { ...c, text: c.cls === "same" ? "About the same" : `${now > before ? "+" : "−"}${Math.abs(now - before) < 1 ? `${Math.round(60 * Math.abs(now - before))} sec` : `${sig2(Math.abs(now - before))} min`}` };
}

/** How far actual speed runs below the timetable's, in percent: positive when slower than scheduled (Bryan, thread
 *  bb2umr8nuu4z: "Report this as percent below timetable"). Whole percent, one decimal under 1%. */
const belowTimetable = (s) => (s.now && s.timetable ? 100 * (1 - s.now / s.timetable) : null);
function belowText(p) {
  if (p == null) return "";
  const a = Math.abs(p), r = a < 1 ? Math.round(10 * a) / 10 : Math.round(a);
  return r === 0 ? "On timetable" : `${r}% ${p > 0 ? "below" : "above"} timetable`;
}

function figures(w) {
  const x = data.windows[w], a = A.windows[w], o = data.ontime.windows[w], r = data.ridership.windows[w];
  // Bryan, 2026-11-17: "All riders please — whatever is the standard ridership metric": SFMTA's average weekday boardings.
  // Bryan, 2026-11-12: no partial-year comparison at 12 months until a clean prior year exists (March 2027).
  const m = null;
  const wait = a.city.ewt + a.city.scheduled;
  const lostText = belowText(belowTimetable(x.speed));
  return `${periodLine(w)}
<div class="kpis kpis5">
${kpi({ label: "Weekday riders", value: thousands(r.now),
    chg: changeHtml(change(r.now, r.before, false), r.before ? "vs. year before" : "") })}
${crowdPeak ? kpi({ label: `Crowded buses at ${clock(crowdPeak.hour)}`, value: oneIn(crowdPeak.s), scale: "Standing room or fuller", chg: "" }) : ""}
${kpi({ label: "Frequent buses: average wait", value: minutes(wait), scale: `${minutes(a.city.ewt)} over schedule`,
    chg: changeHtml(minChange(a.city.ewt, a.cityBefore?.ewt), a.cityBefore ? versus(w) : "") })}
${o?.now ? kpi({ label: "Infrequent buses: on time %", value: `${Math.round(100 * o.now.onTime)}%`, scale: `SFMTA Target ${OT_TARGET}%`, chg: changeHtml(onTimeChange(o), versus(w)) })
    : kpi({ label: "Infrequent buses: on time %", value: "–", chg: `<span class="chg none">Too few departures in this period</span>` })}
${kpi({ label: "Average speed", value: mph(x.speed.now), scale: lostText,
    chg: m ? changeHtml(change(m.speed.now, m.speed.before, false), matchVs(w)) : changeHtml(change(x.speed.now, x.speed.before, false), versus(w)) })}
</div>
`;
}

// Every chart below the period switch follows it (Bryan, 2026-11-17: "all charts below should
// respect the date range"): a monthly trend shows the chosen period's months. SFMTA's service-hours series runs back
// to 2010, so Max shows all of it.
const inPeriod = (rows, w) => { const [a, b] = data.windows[w].months; return rows.filter((t) => t.month >= a && t.month <= b); };

const otBy = Object.fromEntries(data.ontime.trend.map((t) => [t.month, t]));
const pctOf = (v) => (v == null ? null : Math.round(1000 * v) / 10);
const otTrend = data.trend.map((t) => { const o = otBy[t.month] || {}; return { month: t.month, p10: pctOf(o.p10), p50: pctOf(o.p50), p90: pctOf(o.p90) }; });
function otHead() {
  // whether the latest 12 months' on-time share is above or below the 12 months two years before them
  const t = data.ontime.trend.filter((x) => x.onTime != null), a = t.slice(-12), b = t.slice(-36, -24);
  const avg = (xs) => xs.reduce((s, x) => s + x.onTime, 0) / xs.length;
  const d = avg(a) - avg(b);
  const y = b.at(-1).month.slice(0, 4);
  return Math.abs(d) < 0.01 ? `Buses on a timetable are on time about as often as in ${y}` : d < 0 ? `Buses on a timetable are on time a little less often than in ${y}` : `Buses on a timetable are on time a little more often than in ${y}`;
}
/** The on-time heading for a period: the trend's comparison over the long periods, the period's own share otherwise. */
function otHeadFor(w) {
  if (w === "1825" || w === "max") return otHead();
  const o = data.ontime.windows[w];
  return o?.now ? `${Math.round(100 * o.now.onTime)}% of buses on a timetable ran on time` : "Buses on a timetable: on time";
}

/** The service-delivered headline, worded as the buses a rider never sees: the latest 12 months. */
function delHead(w = "365") {
  const t = w === "max" ? data.delivered.trend : inPeriod(data.delivered.trend, w);
  if (!t.length) return "Scheduled service hours that never run";
  const now = t.slice(-12).reduce((s, x) => s + x.share, 0) / Math.min(12, t.length);
  const gone = Math.round(100 * (1 - now));
  return gone >= 1 ? `About ${gone} in 100 scheduled service hours never run` : "Nearly every scheduled bus runs";
}

/** The satisfaction headline: whether the newest survey year is the series' high, low, or neither. */
function satHead() {
  const s = data.satisfaction, last = s.at(-1), hi = Math.max(...s.map((x) => x.pct)), lo = Math.min(...s.map((x) => x.pct));
  // Bryan's wording (page edit, 2026-11-10). "All-time" is the survey series, which starts in ${s[0].year}.
  if (last.pct === hi) return `Rider satisfaction hit an all-time high in ${last.year} at ${Math.round(last.pct)}%`;
  if (last.pct === lo) return `Rider satisfaction hit a low in ${last.year}`;
  return `${Math.round(last.pct)}% of riders rate Muni good or excellent`;
}

/** The cause chart's heading: the biggest part of the latest month's extra wait. */
function causeHead(w = "365") {
  const l = inPeriod(A.trend, w).filter((t) => t.ewt != null).at(-1);
  if (!l) return "Where the extra wait comes from";
  const big = [["spacing", "Buses that bunch up cause most of the extra wait"], ["missing", "Buses that never come cause most of the extra wait"]].reduce((a, b) => ((l[b[0]] ?? 0) > (l[a[0]] ?? 0) ? b : a));
  return (l[big[0]] ?? 0) > l.ewt / 2 ? big[1] : "Where the extra wait comes from";
}

/** The by-hour heading, from the default period: where in the day the extra wait is longest. */
function hourHead(w = "365") {
  const r = A.windows[w].byHour.filter((x) => x.hour >= 6 && x.ewt != null);
  if (!r.length) return "The extra wait through the day";
  const lo = r.reduce((a, b) => (b.ewt < a.ewt ? b : a)), first = r[0], last = r.at(-1);
  if (first.ewt > lo.ewt + 0.5 && last.ewt > lo.ewt + 0.5) return "The extra wait is longest early and late in the day";
  return last.ewt > first.ewt ? "The extra wait grows through the day" : "The extra wait shrinks through the day";
}

/** The speed-by-hour heading, from the default period's slowest hour from 6am. */
function speedHead(w = "365") {
  const r = (data.windows[w].speedByHour || []).filter((x) => x.hour >= 6);
  if (!r.length) return "How fast buses go through the day";
  const h = r.reduce((a, b) => (b.mph < a.mph ? b : a)).hour;
  return h >= 15 && h <= 18 ? "Your bus is slowest in the afternoon rush" : h >= 7 && h <= 9 ? "Your bus is slowest in the morning rush" : "How fast buses go through the day";
}

// ---- The dashboard's other pages, linked under the title -------------------------
// Bryan, 2026-11-21, on publishing Upgrade a Bus Line: "make sure the front dashboard has links to the line page and
// upgrade page instead of the outline of overview it has now". The outline was the section list (Ridership, then
// Performance: Overview, Wait Times, Speed, Crowding), a column left of the text on a wide screen and a strip under the
// title on a narrow one. Each link's line is the page's own listing line (src/directory.mjs). The links carry no date of their own:
// the Draft band above them gives the dashboard's, and a second copy two lines down failed the ux-review's one place
// per fact check (2026-11-20).
const link = (m) => `<li><a href="${m.path}">${esc(m.listing.title)}</a>${m.listing.draft ? ' <span class="tag">Draft</span>' : ""}<span class="dir-line">${esc(m.listing.line)}</span></li>`;
const LINKS_HTML = `<ul class="dir-list muni-links">\n${[lines, optimizer].map(link).join("\n")}\n</ul>`;
const LINKS_CSS = `<style>
.muni-links { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 24px; margin: 0 0 8px; }
.muni-links li { margin: 0; }
.muni-links .tag { font-size: 0.75rem; vertical-align: 1px; color: var(--muted); background: var(--raised); }
@media (max-width: 520px) { .muni-links { grid-template-columns: 1fr; } }
h2[id], h3.sec { scroll-margin-top: 56px; }
h3.sec { font-size: 1.3rem; margin: 40px 0 6px; padding-top: 10px; border-top: 1px solid var(--rule); }
h2 + h3.sec { margin-top: 12px; border-top: 0; padding-top: 0; }
/* the Overview heading and the period switch on one line (Bryan, 2026-11-17) */
.sec-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin: 12px 0 8px; scroll-margin-top: 56px; }
.sec-row h3.sec { margin: 0; border-top: 0; padding-top: 0; }
@media (max-width: 520px) { .sec-row .period button { padding: 5px 7px; font-size: 0.82rem; } }
h4.sub { font-family: Archivo, "Public Sans", sans-serif; font-size: 1.05rem; line-height: 1.2; margin: 26px 0 6px; scroll-margin-top: 56px; }
/* two a row: riders and crowding, then the two wait tiles side by side, then speed (Bryan) */
.kpis5 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (max-width: 640px) { .kpis5 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>`;
export function render() {
  const body = `${CSS}${LINKS_CSS}
<h1>Muni Performance Dashboard</h1>
${DRAFT_NOTE}
<p class="asof">Data through ${esc(THROUGH)}</p>
${LINKS_HTML}

<h2 id="ridership">Ridership</h2>
<h4 class="sub" id="riders-by-day">Fewer people ride than before the pandemic</h4>
<figure class="muni-fig">${both((W) => ridersByDayChart(data.ridership.byMonth, W))}</figure>
${cite("Riders", "riders", [SRC_RIDERS_SYS, SRC_RIDERS])}

<h4 class="sub" id="satisfaction">${esc(satHead())}</h4>
<figure class="muni-fig">${both((W) => satisfactionChart(data.satisfaction, W))}</figure>
${cite("Satisfaction", "satisfaction", [SRC_SAT])}

<h2 id="performance">Performance</h2>
<div class="sec-row" id="top"><h3 class="sec" id="overview">Overview</h3>${periodSwitch()}</div>
${forPeriod(figures)}
${cite("The figures", "overview", [SRC_511, SRC_GTFS, SRC_RIDERS, SRC_TFL])}

<h3 class="sec" id="wait-times">Wait Times</h3>
<p>We follow <a href="https://www.sf.gov/resource--2024--transit-and-street-safety-scorecard/percentage-of-evenly-spaced-muni-arrivals/">SFMTA's own split</a>: Connector and Owl lines are infrequent, so we measure them against the timetable. Every other line is frequent, so we measure its wait against the scheduled gap.</p>
<h4 class="sub" id="how-often">How often your bus comes</h4>
<figure class="muni-fig">${forPeriod((w) => both((W) => freqChart(W, F.windows[w])))}</figure>
${cite("How often", "how-often", [`${SRC_RIDERS}, ${perPeriodText((w) => esc(span(F.windows[w].months)))}`, SRC_SCORECARD])}

<h4 class="sub" id="wait">${perPeriodText((w) => esc(causeHead(w)))}</h4>
<figure class="muni-fig">${forPeriod((w) => both((W) => causeChart(inPeriod(A.trend, w), W)))}</figure>
${data.trackingSteps?.length ? forPeriod((w) => (data.windows[w].months[0] < data.trackingSteps.at(-1) ? `<p class="key-line">Before ${esc(span([data.trackingSteps.at(-1), data.trackingSteps.at(-1)]))}, part of "missing buses" is buses 511 didn't track.</p>` : "")) : ""}
${cite("Excess wait", "excess-wait", [SRC_511, SRC_GTFS])}

<h4 class="sub" id="along">Waits grow along the line</h4>
<p>Excess wait at the stop by how far along its line the stop is, on frequent lines, outbound and inbound combined by their scheduled departures.</p>
<figure class="muni-fig">${forPeriod((w) => both((W) => positionChart(data.windows[w].byPosition.system.both, W, { label: "Muni, both directions" })))}</figure>
${cite("Along the line", "along", [SRC_511, SRC_GTFS])}

<h4 class="sub" id="hours">${perPeriodText((w) => esc(hourHead(w)))}</h4>
<figure class="muni-fig">${forPeriod((w) => forView(both((W) => hourLineChart(A.windows[w].byHour, W)), both((W) => hourBandChart(A.windows[w].byHour, W))))}</figure>
${cite("By hour", "hours", [SRC_511])}

<h4 class="sub" id="on-time">${perPeriodText((w) => esc(otHeadFor(w)))}</h4>
<p>On Connector and Owl lines, you plan around the timetable. A bus is on time from 1 minute early to 4 minutes late, SFMTA's standard, and its target is ${OT_TARGET}% on time (<a href="https://media.api.sf.gov/documents/N26_EN_VIP.pdf#page=160">Charter §8A.103(c)</a>).</p>
<figure class="muni-fig">${forPeriod((w) => { const ot = inPeriod(otTrend, w); return both((W) => bandChart(ot, ["p10", "p50", "p90"], W, { yLabel: "% on time", unit: "%", lowerBound: 0, upperAtLeast: 100, extraRule: { v: OT_TARGET, text: `SFMTA target ${OT_TARGET}%` }, extra: [Plot.ruleY([OT_TARGET], { stroke: "var(--ink)", strokeDasharray: "4 3", strokeOpacity: 0.6 }), Plot.text([OT_TARGET], { x: new Date(Date.UTC(+ot[0].month.slice(0, 4), +ot[0].month.slice(5, 7) - 1, 15)), y: (d) => d, text: () => `SFMTA target ${OT_TARGET}%`, dy: -7, textAnchor: "start", fontSize: 11, fill: "var(--muted)" })], label: "On-time departures each month on Connector and Owl lines, median line with the 10th to 90th percentile across lines." })); })}</figure>
${cite("On time", "on-time", [SRC_511, SRC_GTFS])}

<h4 class="sub" id="delivered">${perPeriodText((w) => esc(delHead(w)))}</h4>
<p>A bus that never runs is one of the missing buses in your wait.</p>
<figure class="muni-fig">${forPeriod((w) => both((W) => deliveredChart(w === "max" ? data.delivered.trend : inPeriod(data.delivered.trend, w), data.delivered.target, W)))}</figure>
${cite("Service hours", "delivered", [SRC_SFMTA])}

<h3 class="sec" id="speed">Speed</h3>
<h4 class="sub" id="speed-hours">${perPeriodText((w) => esc(speedHead(w)))}</h4>
<figure class="muni-fig">${forPeriod((w) => both((W) => speedHourChart(data.windows[w].speedByHour, W)))}</figure>
${cite("Speed by hour", "hours", [SRC_511])}

<h4 class="sub" id="speed-trend">Your bus runs a little slower than the timetable</h4>
<figure class="muni-fig">${forPeriod((w) => both((W) => speedChart(inPeriod(data.trend, w), W)))}</figure>
${cite("Speed", "speed", [SRC_511])}

<h3 class="sec" id="crowding">Crowding</h3>
${data.crowdByHour?.hours?.length ? `<h4 class="sub" id="crowd-hours">Buses are most crowded in the afternoon rush</h4>
<p class="key-line">SFMTA's live occupancy readings, all lines, ${crowdDays(data.crowdByHour)}.</p>
<figure class="muni-fig">${both((W) => levelsChart(data.crowdByHour.hours, W, { label: "All Muni buses" }))}</figure>
${cite("Crowding", "hours", [SRC_511])}` : `<p>No live crowding readings yet.</p>`}

${PERIOD_SCRIPT}`;
  return page({
    title: "Muni Performance Dashboard",
    description: `On frequent Muni service, riders waited ${minutes(aDef.city.ewt + aDef.city.scheduled)} at the stop in ${span(wDef.months)}, ${minutes(aDef.city.ewt)} more than the schedule, and buses averaged ${mph(wDef.speed.now)}.`,
    path,
    body,
    sourcesNote: SOURCES_NOTE,
    directory: false,
  });
}
