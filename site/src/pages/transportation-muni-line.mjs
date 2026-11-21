// One Muni line: its figures for the chosen period against the period before,
// the trend within the period, excess wait stop by stop on a map, and the
// line's month-by-month and hour-of-day charts. One page per listed line at
// /transportation/muni/lines/<line>, and /transportation/muni/line, the Line
// Detail entry in the navigation, which shows the N Judah and moves to the
// line named in ?line= when there is one.
//
// Bryan, 2026-11-09: "a way to choose a single line, and then choose a time
// period ... Get the high-level metrics up top for the whole period. Then get
// the trend over time within that period", at a granularity that keeps a
// chart under about 1,000 points (tools/muni/muni-ewt/muni_detail.py), then
// "performance of each metric along different points on the line, plotted on
// a map".

import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import {
  data, map, detail, BASE, ABOUT, THROUGH, CSS, PERIOD_SCRIPT, PICKER_SCRIPT, periodSwitch, forPeriod, forView, picker, lineName, lineSpeed, MINCOVER, isRail,
  change, changeHtml, kpi, onTimeCard, versus, periodLine, minutes, mph, sig2, span, both, causeChart, periodChart, cite, SRC_511, SRC_GTFS, SOURCES_NOTE, RAMP, EARLY_RAMP, SPEED_RAMP, LINES, ROUTE_JS, PERIODS, DEFAULT, alongCharts, scheduleLine,
  monthChart, periodDomain, speedHourChart, levelsPair, SRC_CROWD, CAUSE_KEY, heatPair, HEAT_KEY, heatCells,
  crowdDays,
  DRAFT_NOTE, DATA_READ_ISO,
} from "../muni.mjs";

export const path = "/transportation/muni/line";
export const file = "transportation/muni/line/index.html";
// Published as a draft, kept out of the sitemap and every list (src/muni.mjs DRAFT_NOTE).
export const sitemap = false;
export const listing = { draft: true, title: "Line Detail", line: "One line's waits and speed, by hour and by stop.", order: 2 };
// The date the lists show beside this page: the one in its Draft band (src/page-dates.mjs).
export const dataUpdated = DATA_READ_ISO;
const DEFAULT_LINE = "N";
const UNIT = { 1: "hour", 6: "6 hours", 24: "day", 168: "week" };

// By SFMTA's line types (freq_rule.py; Bryan, 2026-11-17), a frequent line is judged by TfL's
// excess wait in every hour, with no on-time card, and a Connector or Owl line (muni.json lines[line].frequent false)
// on time in SFMTA's window: it has no excess wait at all, its page leads with on time and
// colours its stop map by early departures.
const frequent = (line) => data.lines[line]?.frequent !== false;
const allOf = (line, w) => data.allService.windows[w].lines.find((y) => y.line === line);
const allTrend = (line) => data.allService.lineTrend[line] || [];

function figures(line, w) {
  const r = allOf(line, w), d = detail.lines[line]?.[w];
  const rail = isRail(line);
  const sp = lineSpeed(d?.period), spb = d?.previous?.mph, thin = d?.period?.mph != null && sp == null;
  const against = versus(w);
  return `${periodLine(w)}
<div class="kpis">
${r?.now != null ? kpi({ label: "Excess wait at the stop", value: minutes(r.now), scale: `${minutes(r.now + r.swt)} wait in all`, chg: changeHtml(change(r.now, r.before, true), r.before != null ? against : "No earlier period to compare with") })
    : r?.show === "none" ? kpi({ label: "Excess wait at the stop", value: "–", chg: "511 tracks too few of its trips" })
    : frequent(line) ? kpi({ label: "Excess wait at the stop", value: "–", chg: "Too few departures in this period" }) : ""}
${kpi({ label: rail ? "Average train speed" : "Average bus speed", value: sp ? mph(sp) : "–", chg: thin ? `<span class="chg">Timepoints cover only ${Math.round(100 * d.period.cover)}% of the miles measured</span>` : changeHtml(change(sp, spb, false), against) })}
${frequent(line) ? "" : onTimeCard(data.ontime.windows[w].lines[line], against, "On time")}
</div>`;
}

// SFMTA's service changes on the line (muni.json lines[line].changes, site_data.py: the announcements we opened, with
// the date read), one number a date, numbered the same on every period's charts and in the list under them (Bryan,
// 2026-11-16: "links to key service changes from MTA").
function changesOf(line) {
  const by = new Map();
  for (const c of data.lines[line]?.changes || []) (by.get(c.date) || by.set(c.date, []).get(c.date)).push(c);
  return [...by.entries()].map(([at, cs], i) => ({ n: i + 1, at, url: cs[0].url, text: cs.map((c) => c.text).join("; "), items: cs }));
}
const dayLabel = (d) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
// The monthly charts share the period charts' time axis (Bryan, 2026-11-16: "Make sure all of
// the horizontal axes line up in this section -- we want the trends to be comparable"), so a 30-day period shows one
// month's figure as a flat step.
function monthly(line, w) {
  const trend = data.lines[line]?.trend;
  if (!trend) return "";
  const d = detail.lines[line]?.[w], [a, b] = data.windows[w].months;
  const [x0, x1] = periodDomain(d?.points) || [new Date(Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, 1)), new Date(Date.UTC(+b.slice(0, 4), +b.slice(5, 7), 0))];
  const unit = detail.units[w], chg = changesOf(line), veh = isRail(line) ? "Trains" : "Buses";
  const crowdLast = [...trend].reverse().find((t) => t.crowded != null);
  const crowd = both((W) => monthChart(trend, [{ key: "crowded", name: "Crowded", color: "#4269d0", ink: "#2b4f9e" }], W, { x0, x1, unit, yLabel: "% of trips", pct: true, changes: chg, label: `${lineName(line)}, SFMTA's crowded trips`, empty: "SFMTA hasn't published this period's crowding yet." }));
  // The full timetable (Bryan, 2026-11-16: "Please show the full timetable, including weekend"),
  // Observable 10's colours less its red. Saturday and Sunday are one line where their timetables match in every month shown; otherwise Sunday is dashed, so it shows where it runs on Saturday's.
  const inView = (t) => new Date(Date.UTC(+t.month.slice(0, 4), +t.month.slice(5, 7), 1)) > x0 && new Date(Date.UTC(+t.month.slice(0, 4), +t.month.slice(5, 7) - 1, 1)) <= x1;
  const sameWeekend = trend.filter(inView).every((t) => t.busesSat === t.busesSun);
  const svc = [{ key: "busesPeak", name: "Weekday busiest", color: "#4269d0", ink: "#2b4f9e" }, { key: "busesMidday", name: "Weekday midday", color: "#efb118", ink: "#8a6300" },
    { key: "busesEvening", name: "Weekday evening", color: "#a463f2", ink: "#6b37b3" },
    ...(sameWeekend ? [{ key: "busesSat", name: "Weekend midday", color: "#3ca951", ink: "#23733a" }]
      : [{ key: "busesSat", name: "Saturday midday", color: "#3ca951", ink: "#23733a" }, { key: "busesSun", name: "Sunday midday", color: "#6cc5b0", ink: "#2f7f6f", dash: "5 3" }])];
  const buses = both((W) => monthChart(trend, svc, W,
    { x0, x1, unit, yLabel: `${veh} an hour`, changes: chg, outage: true, label: `${lineName(line)}, weekday ${veh.toLowerCase()} an hour each way` }));
  const vis = chg.filter((c) => new Date(`${c.at}T12:00:00Z`) >= x0 && new Date(`${c.at}T12:00:00Z`) <= x1);
  return `${crowdLast ? `<h3 class="sub">Crowded trips, each month</h3>
<p class="key-line">SFMTA's share of the line's trips over capacity at a tenth or more of stops, published through ${esc(span([crowdLast.month, crowdLast.month]))}.</p>
${crowd}` : ""}<h3 class="sub">${veh} an hour each way, each month</h3>
<p class="key-line">From the timetable. Midday is 10am to 3pm, evening 8 to 11pm.</p>
${buses}${vis.length ? `<ol class="ln-chg">${vis.map((c) => `<li value="${c.n}"><span class="ln-n">${c.n}</span> ${esc(dayLabel(c.at))}: ${c.items.map((x) => `<a href="${esc(x.url)}" title="${esc(x.title)}">${esc(x.text)}</a>`).join("; ")} <span class="ln-read">SFMTA, read ${esc(dayLabel(c.items[0].read))}</span></li>`).join("")}</ol>` : ""}`;
}

function trends(line, w) {
  const d = detail.lines[line]?.[w];
  const months = monthly(line, w);
  if (!d) return months;
  const u = detail.units[w], chg = changesOf(line);
  // excess wait each month
  const [a, b] = data.windows[w].months, [x0, x1] = periodDomain(d.points) || [new Date(Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, 1)), new Date(Date.UTC(+b.slice(0, 4), +b.slice(5, 7), 0))];
  const ewt = allTrend(line).length ? `<h3 class="sub">Excess wait, each month</h3>
${both((W) => monthChart(allTrend(line), [{ key: "ewt", name: "Excess wait", color: "#4269d0", ink: "#2b4f9e" }], W, { x0, x1, unit: u, yLabel: "Minutes", changes: chg, label: `${lineName(line)}, excess wait` }))}
` : "";
  if (!d.points.some((p) => p.mph != null)) return `${ewt}<p class="verdict-note">No measured trips in this period.</p>${months}`;
  return `${ewt}<h3 class="sub">${isRail(line) ? "Train" : "Bus"} speed, each ${UNIT[u]}</h3>
${both((W) => periodChart(d.points, "mph", W, { unit: u, yLabel: "mph", color: "#3ca951", lowerBound: "fit", changes: chg }))}
${months}`;
}

// The heavy charts (within-period and by-hour) are drawn inline for the default period only. Each other period's
// charts are a small file per line and period, lines/<line>/p-<days>.json, fetched when that period is picked,
// so the page's first paint doesn't wait on every period's SVG (Bryan, 2026-11-09: "the line detail page took a
// while to load").
const lazy = (key, fn) => PERIODS.map((w) => w === DEFAULT
  ? `<div class="wv" data-w="${w}">${fn(w)}</div>`
  : `<div class="wv" data-w="${w}" data-lazy="${key}"><p class="verdict-note">Loading…</p></div>`).join("");
// By month, split by cause as on the overview. A 30 or 90 day period shows its last three months.
function causes(line, w) {
  const [a, b] = data.windows[w].months, all = allTrend(line).filter((m) => m.month <= b);
  const t = all.filter((m) => m.month >= a), show = t.length >= 3 ? t : all.slice(-3);
  if (show.every((m) => m.spacing == null)) return `<p class="verdict-note">No split of the wait in this period.</p>`;
  return `${both((W) => causeChart(show, W, { label: lineName(line) }))}
<p class="key-line">${CAUSE_KEY}${show.length > t.length ? `. ${esc(span([show[0].month, show.at(-1).month]))}, by month` : ""}</p>`;
}
// Excess wait by hour and along the line, one heat map a direction, replaces the by-hour excess-wait chart and the
// along-the-line excess-wait pair (Bryan, 2026-11-17: "How does this line up with what's down
// below? Perhaps it's better if we have an inbound and outbound by time and along route heat map").
const hasHeat = (line) => PERIODS.some((w) => ["0", "1"].some((d) => heatCells[w]?.[line]?.[d]?.length));
// placed by distance along the line, a tenth can hold no stop at all (the 28's Presidio Parkway), blank in every hour
const noStopTenth = (line) => PERIODS.some((w) => ["0", "1"].some((d) => { const c = heatCells[w]?.[line]?.[d]; return c?.length && new Set(c.map((x) => x[1])).size < 10; }));
const heatFor = (line) => (w) => {
  const c = heatCells[w]?.[line];
  return c && ["0", "1"].some((d) => c[d]?.length) ? heatPair(data.windows[w].byPosition.lines[line], c, { label: lineName(line) }) : `<p class="verdict-note">Too few departures in this period.</p>`;
};
const hoursFor = (line) => (w) => {
  const sp = data.windows[w].lineSpeedHours?.[line] || [];
  // Speed by hour (Bryan, 2026-11-16: "Can you also show speed and crowding by time of day?")
  const speed = sp.filter((r) => r.hour >= 6 && r.hour <= 22).length >= 4 ? `<h3 class="sub">${isRail(line) ? "Train" : "Bus"} speed</h3>
${both((W) => speedHourChart(sp, W, { label: `${lineName(line)}, average speed` }))}` : "";
  return speed || `<p class="verdict-note">No measured hours in this period.</p>`;
};
// Crowding by hour and along the line come from a few weekdays of our own 511 archive, so they're the same whatever
// period is picked; one chart per direction (Bryan, 2026-11-16).
const crowdNote = (c, where) => `<p class="key-line">SFMTA's live occupancy readings, ${crowdDays(c)}.</p>`;
function crowdHours(line) {
  const c = data.lines[line]?.crowdHours;
  if (!c || !Object.keys(c.dirs).length) return "";
  return `<h3 class="sub">How full the buses are</h3>
${crowdNote(c, "each hour")}
${levelsPair(c.dirs, { by: "hour", label: lineName(line) })}`;
}
function crowdAlong(line) {
  const c = data.lines[line]?.crowdAlong;
  if (!c || !Object.keys(c.dirs).length) return "";
  return `<h3 class="sub">How full the buses are</h3>
${crowdNote(c, "along the line")}
${levelsPair(c.dirs, { by: "tenth", label: lineName(line) })}`;
}
// Speed by tenth of the route (Bryan, 2026-11-10: "Can you show speed along the line here"), each direction.
const alongFor = (line) => (w) => {
  const bp = data.windows[w].byPosition.lines[line], sp = detail.lines[line]?.[w]?.speedAlong;
  const names = bp && Object.fromEntries(["0", "1"].map((d) => [d, bp[d]?.direction ? `${bp[d].direction}${bp[d].to ? ` to ${bp[d].to}` : ""}` : null]));
  return sp ? alongCharts({ 0: sp["0"]?.tenths, 1: sp["1"]?.tenths }, { label: lineName(line), key: "mph", names }) : `<p class="verdict-note">No measured stretches in this period.</p>`;
};
const fragment = (line, w) => Buffer.from(JSON.stringify({ trends: trends(line, w), hours: hoursFor(line)(w), along: alongFor(line)(w), heat: heatFor(line)(w) }));

function body(line) {
  const L = map.lines[line];
  const stops = Object.fromEntries(map.stops.map((s) => [s.stop, s]));
  const pts = (L?.stops || []).filter((s) => stops[s.stop]).map((s) => ({ c: [stops[s.stop].lon, stops[s.stop].lat], n: stops[s.stop].name, e: s.ewt, p: s.prev }));
  const before = Object.fromEntries(Object.entries(data.windows).map(([w, x]) => [w, x.before ? span(x.before) : null]));
  const early = (L?.early || []).map((s) => ({ c: [s.lon, s.lat], n: s.name, e: s.share }));
  // Each stop coloured by the speed to the next stop on its direction, for each period (speed_along_line.py's pairs)
  const spd = {};
  for (const [w, x] of Object.entries(detail.lines[line] || {})) {
    for (const v of Object.values(x.speedAlong || {})) {
      for (const [k, x] of Object.entries(v.pairs)) {
        const [a, b] = k.split("-");
        if (!stops[a]) continue;
        (spd[a] ||= { c: [stops[a].lon, stops[a].lat], n: stops[a].name, to: stops[b]?.name, e: {} }).e[w] = x.mph ?? x;
      }
    }
  }
  const speed = Object.keys(spd).sort().map((k) => spd[k]);
  const MAPDATA = { stops: pts, early, speed, sramp: SPEED_RAMP, shape: L?.shape || [], route: { s: L?.shape || [], c: L?.color, t: L?.text, y: L?.type }, ramp: RAMP, eramp: EARLY_RAMP, before };
  const hours = hoursFor(line), fq = frequent(line);
  return `${CSS}${PAGE_CSS}
<h1>${esc(lineName(line))}</h1>
${DRAFT_NOTE}
${scheduleLine(data.lines[line]?.schedule, line).map((t) => `<p class="ln-sched">${esc(t)}</p>`).join("")}
<div class="muni-top">${periodSwitch()}${picker()}<span class="asof">Data through ${esc(THROUGH)}</span></div>
${forPeriod((w) => figures(line, w))}

<h2 id="trend">Trends over time</h2>
<p>Median, with the 10th to 90th percentile shaded.</p>
<figure class="muni-fig">${lazy("trends", (w) => trends(line, w))}</figure>
${cite("Trends", "line-trend", [SRC_511, SRC_CROWD])}

<h2 id="stops">Stop by stop</h2>
${!L ? `<p class="verdict-note">No map: neither SFMTA's current schedule nor its September 2022 one, the two we draw lines from, carries the ${esc(line)}.</p>` : `<div class="seg ln-metric" role="group" aria-label="Map shows">${fq ? `<button type="button" data-m="ewt" aria-pressed="true">Excess wait</button>` : ""}<button type="button" data-m="early" aria-pressed="${fq ? "false" : "true"}">Left early</button>${speed.length ? `<button type="button" data-m="speed" aria-pressed="false">Speed</button>` : ""}</div>
<div class="glmap ln-map" role="img" aria-label="Map of the ${esc(lineName(line))} with each stop coloured by its ${fq ? "excess wait" : "share of departures that left early"}"></div>
${fq ? `<p class="key-line ln-key" data-m="ewt">Excess wait at each stop: <span class="ramp"></span> ${RAMP.domain[0]} to ${RAMP.domain[2]}+ min.</p>` : ""}
<p class="key-line ln-key" data-m="early"${fq ? " hidden" : ""}>Left more than 1 min early: <span class="ramp"></span> ${EARLY_RAMP.domain[0] * 100}% to ${EARLY_RAMP.domain[2] * 100}%+ of departures.</p>
<p class="key-line ln-key" data-m="speed" hidden>Speed to the next stop: <span class="ramp"></span> ${SPEED_RAMP.domain[2]} mph or more to ${SPEED_RAMP.domain[0]} or less.</p>`}
${cite("Stop map", "stops", [SRC_511, SRC_GTFS])}
${fq && hasHeat(line) ? `
<h2 id="heat">Excess wait by hour and stop</h2>
<p class="key-line">${HEAT_KEY}. Each cell is a tenth of the route, first stop to last, in one clock hour.</p>
<figure class="muni-fig">${lazy("heat", heatFor(line))}</figure>
<p class="key-line">Blank cells had too few buses tracked${noStopTenth(line) ? ", or no stop" : ""}.</p>
${cite("Excess wait by hour and stop", "along", [SRC_511, SRC_GTFS])}
` : ""}
${Object.entries(data.windows).some(([w]) => detail.lines[line]?.[w]?.speedAlong) || data.lines[line]?.crowdAlong ? `
<h2 id="along">Along the line</h2>
<figure class="muni-fig">${lazy("along", alongFor(line))}${crowdAlong(line)}</figure>
${cite("Along the line", "along", [SRC_511, SRC_GTFS])}
` : ""}
${allTrend(line).length ? `<h2 id="months">Excess wait by cause</h2>
<figure class="muni-fig">${forPeriod((w) => causes(line, w))}</figure>
${cite("Each month", "excess-wait", [SRC_511])}
` : ""}
<h2 id="hours">By hour of day</h2>
<figure class="muni-fig">${lazy("hours", hours)}${crowdHours(line)}</figure>
${cite("By hour", "hours", [SRC_511])}
<script type="application/json" id="ln-data">${inlineJson(MAPDATA)}</script>
${PERIOD_SCRIPT}${PICKER_SCRIPT}${MAP_HEAD}${ROUTE_JS}${script(line)}`;
}

const script = (line) => `<script>
(function () {
  var here = ${JSON.stringify(line)};
  var q = new URLSearchParams(location.search), want = q.get("line");
  var base = location.pathname.replace(/\\/(line|lines\\/[^/]+)\\/?$/, "");
  function go(l) { var s = new URLSearchParams(location.search); s.delete("line"); var t = s.toString(); location.href = base + "/lines/" + encodeURIComponent(l) + "/" + (t ? "?" + t : ""); }
  if (want && want !== here && ${JSON.stringify(LINES)}.indexOf(want) !== -1) { go(want); return; }
  window.addEventListener("muni:line", function (e) { if (e.detail !== here) go(e.detail); });
  var got = {};
  function fill(w) {
    if (got[w] || !document.querySelector('.wv[data-w="' + w + '"][data-lazy]')) return;
    got[w] = 1;
    fetch(base + "/lines/" + encodeURIComponent(here) + "/p-" + w + ".json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (f) {
      document.querySelectorAll('.wv[data-w="' + w + '"][data-lazy]').forEach(function (el) { el.innerHTML = f[el.dataset.lazy]; el.removeAttribute("data-lazy"); });
    }).catch(function () { got[w] = 0; document.querySelectorAll('.wv[data-w="' + w + '"][data-lazy] .verdict-note').forEach(function (p) { p.textContent = "This period's charts didn't load. Reload the page to try again."; }); });
  }
  fill(window.muniDays());
  window.addEventListener("muni:days", function (e) { fill(e.detail); });
  var D = JSON.parse(document.getElementById("ln-data").textContent), el = document.querySelector(".ln-map");
  var all = [].concat.apply([], D.shape.concat(D.stops.map(function (s) { return [s.c]; })));
  if (!el || !all.length) { if (el) el.style.display = "none"; return; }
  var w0 = Infinity, s0 = Infinity, e0 = -Infinity, n0 = -Infinity;
  all.forEach(function (c) { w0 = Math.min(w0, c[0]); e0 = Math.max(e0, c[0]); s0 = Math.min(s0, c[1]); n0 = Math.max(n0, c[1]); });
  var map = sfMap.create(el, { bounds: [[w0, s0], [e0, n0]], padding: function () { return 24; } });
  if (!map) return;
  var metric = ${JSON.stringify(frequent(line) ? "ewt" : "early")};
  function color(w) { var r = metric === "ewt" ? D.ramp : metric === "speed" ? D.sramp : D.eramp, t = r.tokens.map(sfMap.token); return ["interpolate", ["linear"], ["get", "e" + w], r.domain[0], t[0], r.domain[1], t[1], r.domain[2], t[2]]; }
  function paint() { var w = window.muniDays(); map.getSource("stops").setData(feats(metric === "ewt" ? D.stops : metric === "speed" ? D.speed : D.early)); map.setFilter("stops", ["has", "e" + w]); map.setPaintProperty("stops", "circle-color", color(w)); }
  function feats(list) { return sfMap.collection(list.map(function (s) {
      var p = { n: s.n, to: s.to }; for (var k in s.e) p["e" + k] = s.e[k]; for (var k2 in (s.p || {})) p["p" + k2] = s.p[k2];
      return { type: "Feature", properties: p, geometry: { type: "Point", coordinates: s.c } };
    })); }
  document.querySelectorAll(".ln-metric button").forEach(function (b) { b.addEventListener("click", function () {
    metric = b.dataset.m; pop.remove();
    document.querySelectorAll(".ln-metric button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
    document.querySelectorAll(".ln-key").forEach(function (k) { k.hidden = k.dataset.m !== metric; });
    if (map.sfLoaded && map.getLayer("stops")) paint();
  }); });
  var pop = { remove: function () {} };
  map.once("load", function () {
    var before = sfMap.under(map);
    var R = {}; R[here] = D.route;
    map.addSource("route", { type: "geojson", data: muniRoutes.feats(R) });
    map.addSource("stops", { type: "geojson", data: feats(metric === "ewt" ? D.stops : D.early) });
    muniRoutes.add(map, "route", before, { width: ["interpolate", ["linear"], ["zoom"], 11, 3, 14, 5, 17, 8] });
    map.addLayer({ id: "stops", type: "circle", source: "stops", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3, 14, 6, 17, 10], "circle-stroke-width": 1.2, "circle-stroke-color": "#fff" } }, before);
    muniRoutes.badges(map, "route", before, { spacing: 260 });
    paint();
    pop = new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: "240px" });
    map.on("click", function (e) {
      var f = sfMap.near(map, e.point, ["stops"])[0];
      if (!f) { pop.remove(); return; }
      var w = window.muniDays(), p = f.properties, v = p["e" + w], b = p["p" + w];
      var t = "<b>" + p.n + "</b><br>" + (metric === "ewt" ? (+v).toPrecision(2) + " min excess wait" : metric === "speed" ? (+v).toFixed(1) + " mph to " + (p.to || "the next stop") : Math.round(100 * v) + "% of departures left more than 1 min early");
      if (metric === "ewt" && b != null && D.before[w]) { var d = 100 * (v - b) / b; t += "<br>" + (Math.abs(d) < 1 ? "About the same as " : Math.abs(d).toPrecision(2) + "% " + (d < 0 ? "better" : "worse") + " than ") + D.before[w]; }
      pop.setLngLat(f.geometry.coordinates).setHTML(t).addTo(map);
    });
  });
  window.addEventListener("muni:days", function () { if (map.sfLoaded && map.getLayer("stops")) paint(); });
})();
</script>`;

const PAGE_CSS = `<style>
.ln-metric { margin: 0 0 6px; }
.ln-sched { font-size: 0.9rem; color: var(--muted); margin: -4px 0 6px; }
h3.sub { font-size: 0.95rem; margin: 14px 0 0; }
h3.sub + .key-line { margin: 0 0 2px; }
.ln-chg { list-style: none; padding: 0; margin: 8px 0 0; font-size: 0.86rem; }
.ln-chg li { margin: 3px 0; }
.ln-n { display: inline-block; min-width: 1.2em; font-weight: 700; color: var(--accent); }
.ln-read { color: var(--muted); font-size: 0.8rem; }
.ln-map { height: 460px; }
@media (max-width: 640px) { .ln-map { height: 380px; } }
</style>`;

const render1 = (line, p) => page({
  title: lineName(line),
  description: `Excess wait and speed on Muni's ${lineName(line)}, over the last 30, 90 or 365 days, 5 years or every month of data.`,
  path: p,
  body: body(line),
  sourcesNote: SOURCES_NOTE,
  directory: false,
});

export const render = () => render1(DEFAULT_LINE, path);

const frag = (l, w) => ({ path: `${BASE}/lines/${encodeURIComponent(l)}/p-${w}.json`, file: `transportation/muni/lines/${l}/p-${w}.json`, html: fragment(l, w), sitemap: false });
const frags = (l) => PERIODS.filter((w) => w !== DEFAULT).map((w) => frag(l, w));
const one = (l) => ({ path: `${BASE}/lines/${encodeURIComponent(l)}`, file: `transportation/muni/lines/${l}/index.html`, html: render1(l, `${BASE}/lines/${encodeURIComponent(l)}`) });
export function pages() {
  return LINES.flatMap((l) => [one(l), ...frags(l)]);
}
// The dev server renders only the line asked for (scripts/site-files.mjs).
export function pageFor(file) {
  const m = /^transportation\/muni\/lines\/([^/]+)\/(index\.html|p-([^.]+)\.json)$/.exec(file);
  if (!m || !LINES.includes(m[1])) return null;
  if (!m[3]) return one(m[1]);
  return PERIODS.includes(m[3]) && m[3] !== DEFAULT ? frag(m[1], m[3]) : null;
}
