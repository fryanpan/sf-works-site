// Muni, line by line: every stop on the frequent lines coloured by its excess
// wait over the chosen period, beside the lines ranked worst first in their
// groups (trains, buses, cable cars). Picking a line, from the list or the
// picker, picks out its stops and route on the map. Each line has its own page
// (transportation-muni-line.mjs renders them).
//
// Bryan, 2026-11-09: "last 30 days, what is along each stop in the line,
// plotted on the whole on a map, what is the excess wait time", with a 30, 90
// and 365 day switch that drives every figure on the page.

import { page } from "../layout.mjs";
import { esc } from "../html.mjs";
import { MAP_HEAD, inlineJson } from "../maplibre.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import {
  data, map, detail, BASE, ABOUT, THROUGH, CSS, PERIOD_SCRIPT, PICKER_SCRIPT, periodSwitch, forPeriod, forView, picker, grouped,
  lineName, lineSpeed, sparkRiders, sparkWaitAll, sparkOnTime, MINCOVER, noChange, pctLonger, change, changeHtml, minutes, mph, sig2, span, sparkFor, both, hourChart, hourBandChart, cite, SRC_511, SRC_GTFS, SOURCES_NOTE, RAMP, isRail, C, ROUTE_JS, PERIODS, DEFAULT, hourPctChart, hourPctBandChart,
  crowdDaysText,
  DRAFT_NOTE, DATA_READ_ISO,
} from "../muni.mjs";

export const path = "/transportation/muni/lines";
export const file = "transportation/muni/lines/index.html";
// Published as a draft, kept out of the sitemap and every list (src/muni.mjs DRAFT_NOTE).
export const sitemap = false;
export const listing = { draft: true, title: "Lines", line: "Excess wait at every stop, on a map.", order: 1 };
// The date the lists show beside this page: the one in its Draft band (src/page-dates.mjs).
export const dataUpdated = DATA_READ_ISO;

// Each line's average weekday riders over the period, under its name (Bryan, 2026-11-16: "Can you
//   give a sense of ridership?"). SFMTA's boardings by route, settled months only (site_data.py, ridership.byLine).
function riders(line, w) {
  const v = data.ridership.byLine?.[w]?.[line];
  if (v == null) return "";
  const t = v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : `${v}`;
  return `<span class="ml-riders" title="SFMTA's average weekday boardings, ${esc(span(data.ridership.windows[w].months))}">${t}</span>`;
}

// Each line's share of weekday readings at standing room or fuller (Bryan, 2026-11-16: "Can you
//   add a column for % crowded (standing room only or full)"), from SFMTA's live occupancy readings in our 511 archive
//   (site_data.py crowdShare). A few weekdays only, so it's the same in every period and has no sparkline.
const CS = data.crowdShare || { lines: {} };
const crowdTitle = `Share of weekday readings at standing room only or fuller, SFMTA's live occupancy levels ${crowdDaysText(CS)}, the same whatever the period. The weekdays: ${CS.list}`;
const crowdCell = (line) => `<span class="ml-val"><b title="${esc(crowdTitle)}">${CS.lines[line] != null ? `${Math.round(CS.lines[line])}%` : "–"}</b></span>`;
const crowdHead = `<button type="button" data-sort="c" title="${esc(crowdTitle)}">Crowded</button>`;
// One table for every line (Bryan, 2026-11-16), one figure a line, TfL's way (Bryan, 2026-11-17,
//   : "Report TfL's way"): a frequent line shows its excess wait in the hours it runs every 10
//   minutes or better, and any other line shows how often its buses are on time, in SFMTA's window of 1 minute early
//   to 4 late (site_data.py allService, row.show).
const ewtTitle = (r) => (pctLonger(r.now, r.swt) != null ? `Excess wait, ${pctLonger(r.now, r.swt)}% longer than the scheduled wait` : "Excess wait");
const otTitle = (r) => `A Connector or Owl line, so judged on time: ${Math.round(100 * r.early)}% early, ${Math.round(100 * r.onTime)}% on time (1 minute early to 4 late), ${Math.round(100 * r.late)}% late, of ${r.otN.toLocaleString("en-US")} departures`;
// The cable cars show none (row.show "none"): 511 tracks too few of their trips for an excess wait (About, "Lines").
const waitCell = (r) => (r.show === "wait"
  ? `<span class="ml-val"><b title="${esc(ewtTitle(r))}">${esc(minutes(r.now))}</b>${changeHtml(change(r.now, r.before, true), "")}</span>`
  : r.show === "none" ? `<span class="ml-val"><b title="No wait shown: 511 tracks too few of the cable cars' trips">–</b></span>`
  : `<span class="ml-val"><b title="${esc(otTitle(r))}">${Math.round(100 * r.onTime)}%</b><span class="ml-pct">on time</span></span>`);
function list(w) {
  const x = data.allService.windows[w];
  // Excess wait sorts and shows in minutes (Bryan, 2026-11-16: "Let's sort excess wait by number of
  //   minutes"), with the percent longer than the timetable in the hover title.
  // Bryan, 2026-11-10: "Sort alphanumerically please" by default, and "Allow sort": a header click re-sorts each group.
  const groups = grouped(x.lines, (a, b) => a.line.localeCompare(b.line, "en", { numeric: true }));
  // Each header sits over its number (Bryan, 2026-11-10); the sparklines beside them cover the chosen period.
  return `<div class="ml-head"><button type="button" data-sort="i" aria-sort="ascending">Line</button><button type="button" data-sort="r" title="Average weekday riders">Riders</button><span class="ml-rs"></span><button type="button" data-sort="e" title="Excess wait for frequent lines; on time, 1 minute early to 4 late, for Connector and Owl lines">Wait / On Time</button><span class="ml-es"></span><button type="button" data-sort="s">Speed</button><span class="ml-ss"></span>${crowdHead}</div>` + groups.map((g, gi) => `<h3 class="ml-group">${g.label}</h3>
<ol class="ml-list">${g.rows.map((r, i) => {
    const sp = lineSpeed(detail.lines[r.line]?.[w]?.period), cover = detail.lines[r.line]?.[w]?.period?.cover;
    return `<li data-line="${esc(r.line)}" data-g="${gi}" data-i="${i}" data-r="${data.ridership.byLine?.[w]?.[r.line] ?? ""}" data-e="${r.now ?? ""}" data-s="${sp ?? ""}" data-c="${CS.lines[r.line] ?? ""}"><a class="ml-name" href="${BASE}/lines/${encodeURIComponent(r.line)}">${esc(lineName(r.line))}</a>
<span class="ml-val"><b>${riders(r.line, w) || "–"}</b></span>
<span class="ml-spark ml-rs">${sparkRiders(r.line, w)}</span>
${waitCell(r)}
<span class="ml-spark ml-es">${r.show === "wait" ? sparkWaitAll(r.line, w) : r.show === "none" ? "" : sparkOnTime(r.line, w)}</span>
<span class="ml-val"><b${!sp && cover != null && cover < MINCOVER ? ` title="The timetable's timepoints cover only ${Math.round(100 * cover)}% of this line's measured miles, too little for a line speed"` : ""}>${sp ? esc(mph(sp)) : "–"}</b></span>
<span class="ml-spark ml-ss">${sparkFor(r.line, "mph", w, "Average speed over the period")}</span>
${crowdCell(r.line)}
</li>`;
  }).join("")}</ol>`).join("");
}

// ---- By hour of day, one line per Muni line --------------------------------
//
// Bryan, 2026-11-10: "Add a section next that shows average speed by hour of day by line on a single line chart,
// each line shows up as one line", then "And also show excess wait by hour". Every chart follows the period switch:
// speed from muni.json's lineSpeedHours (each period's months pooled as miles over hours, site_data.py), excess wait
// from its lineHours. Hovering a line draws it bold and its <title> names it.
const hourLabel = (h) => (h === 12 ? "noon" : h < 12 ? `${h}am` : `${h - 12}pm`);
// A peak-only line is left out of both charts: its hours each cover a different part of its route, so its by-hour
// speed shows where the bus is, not when (the 8BX read 30 mph at 7pm, its freeway stretch). A line counts as all-day
// when it has a speed in at least ALL_DAY of the hours from 6am (Bryan, 2026-11-10), in the
// period shown.
const ALL_DAY = 10;
const speedHours = (w, l) => data.windows[w].lineSpeedHours?.[l] || [];
const peakOnly = (w) => data.windows[w].lines.map((r) => r.line).filter((l) => speedHours(w, l).length && speedHours(w, l).filter((h) => h.hour >= 6).length < ALL_DAY);
// Four measures by hour (Bryan, 2026-11-10): speed and end-to-end time in one column, excess
// wait and % longer than expected in the other. Speed is miles over hours from muni-lines.json's hourly points; end-to-end
// time is the route's length (muni_map.py, SFMTA's GTFS shapes, the mean of the two directions) over that hour's speed,
// an estimate; excess wait and % longer come from muni.json's lineHours (excess wait over the scheduled wait).
// Speed is muni.json's lineSpeedHours.
const KEYS = {
  mph: { y: "Average speed (mph)", head: "Average speed" },
  trip: { y: "Minutes end to end (estimated)", head: "End-to-end time (estimated)" },
  ewt: { y: "Excess Wait (minutes)", head: "Excess wait" },
  pct: { y: "% longer than expected", head: "% longer than expected" },
};
function byHourRows(key, w) {
  const out = [], skip = peakOnly(w);
  for (const r of data.windows[w].lines.filter((r) => !skip.includes(r.line))) {
    const name = lineName(r.line);
    if (key === "ewt" || key === "pct") {
      for (const h of data.windows[w].lineHours?.[r.line] || []) {
        if (h.hour < 6 || h.ewt == null) continue;
        const v = key === "ewt" ? h.ewt : h.scheduled ? (100 * h.ewt) / h.scheduled : null;
        if (v != null) out.push({ line: name, h: h.hour, v });
      }
      continue;
    }
    const miles = map.lines[r.line]?.miles, len = miles?.length ? miles.reduce((a, b) => a + b, 0) / miles.length : null;
    if (key === "trip" && !len) continue;
    for (const { hour: h, mph } of speedHours(w, r.line)) {
      if (h >= 6) out.push({ line: name, h, v: key === "mph" ? mph : (60 * len) / mph });
    }
  }
  return out;
}
function hourLines(key, W, w) {
  const rows = byHourRows(key, w);
  if (!rows.length) return "";
  const narrow = W < 400, hi = Math.max(...rows.map((r) => r.v)), lo = Math.min(0, ...rows.map((r) => r.v));
  return plotSVG({
    width: W, height: narrow ? 170 : 165, marginLeft: 38, marginRight: 10, marginTop: 20, marginBottom: 22, style: { fontSize: 11 },
    x: { domain: [6, 22], ticks: [6, 10, 14, 18, 22], tickFormat: hourLabel, label: null, tickSize: 0 },
    y: { domain: [lo, key === "pct" ? Math.ceil(hi / 10) * 10 : Math.ceil(hi)], label: KEYS[key].y, labelArrow: false, grid: true, ticks: 3, tickSize: 0 },
    marks: [
      Plot.ruleY([0], { stroke: "var(--ink)", strokeOpacity: 0.4 }),
      Plot.line(rows, { x: "h", y: "v", z: "line", stroke: C.one, strokeOpacity: 0.35, strokeWidth: 1.3, title: "line" }),
    ],
  }, { className: "hr-lines", label: `${KEYS[key].y} by hour of day for each frequent Muni line, ${span(data.windows[w].months)}.` });
}

// Hovering a line in either chart shows its badge and name at the pointer, and draws the same line bold in both charts
// (Bryan, 2026-11-10: "Show me the line icon on hover for these two charts"). Badges use SFMTA's route colours, as on
// the map: round for trains (GTFS route_type 0), rounded squares otherwise.
const HOUR_SCRIPT = () => {
  const badges = Object.fromEntries(Object.values(data.windows).flatMap((x) => x.lines).map((r) => { const m = map.lines[r.line] || {}; return [lineName(r.line), { r: r.line, c: m.color || "#666", t: m.text || "#fff", y: m.type }]; }));
  return `<script>
(function () {
  var B = ${JSON.stringify(badges).replace(/</g, "\\u003c")};
  function wire(grid) {
  if (grid.dataset.wired) return; grid.dataset.wired = 1;
  var tip = document.createElement("div"); tip.className = "hr-tip"; tip.hidden = true; grid.appendChild(tip);
  var paths = [].slice.call(grid.querySelectorAll(".hr-lines path"));
  paths.forEach(function (p) { var t = p.querySelector("title"); if (t) { p.dataset.n = t.textContent; t.remove(); } });
  function on(n) { paths.forEach(function (p) { p.classList.toggle("on", p.dataset.n === n); }); }
  paths.forEach(function (p) {
    if (!p.dataset.n) return;
    p.addEventListener("mouseenter", function () {
      var b = B[p.dataset.n] || {};
      tip.innerHTML = '<span class="hr-badge' + (b.y === 0 ? " round" : "") + '" style="background:' + b.c + ";color:" + b.t + '">' + (b.r || "") + "</span> " + p.dataset.n;
      tip.hidden = false; on(p.dataset.n);
    });
    p.addEventListener("mousemove", function (e) { var r = grid.getBoundingClientRect(); tip.style.left = (e.clientX - r.left + 12) + "px"; tip.style.top = (e.clientY - r.top - 30) + "px"; });
    p.addEventListener("mouseleave", function () { tip.hidden = true; on(null); });
    // Bryan, 2026-11-10: "Clicking on a line should also open up that line's details".
    p.addEventListener("click", function () { var b = B[p.dataset.n]; if (b) location.href = location.pathname.replace(/\\/?$/, "/") + encodeURIComponent(b.r) + "/" + location.search; });
  });
  }
  document.querySelectorAll(".hr-grid").forEach(wire);
  // Only the default period's grids are in the page; another period's are fetched from hours-<days>.json the first
  // time it is picked, as the line pages fetch their charts (the five periods' grids were 0.36 MB of the page).
  var got = {};
  function fill(w) {
    var els = document.querySelectorAll('.wv[data-w="' + w + '"][data-lazy]');
    if (got[w] || !els.length) return;
    got[w] = 1;
    fetch(location.pathname.replace(/\\/?$/, "/") + "hours-" + w + ".json").then(function (r) { if (!r.ok) throw r; return r.json(); }).then(function (f) {
      els.forEach(function (el) { el.innerHTML = f[el.dataset.lazy]; el.removeAttribute("data-lazy"); el.querySelectorAll(".hr-grid").forEach(wire); });
    }).catch(function () { got[w] = 0; els.forEach(function (el) { var p = el.querySelector(".verdict-note"); if (p) p.textContent = "This period's charts didn't load. Reload the page to try again."; }); });
  }
  fill(window.muniDays());
  window.addEventListener("muni:days", function (e) { fill(e.detail); });
})();
</script>`;
};
// Each chart's y-axis label names it, so there's no caption repeating it above (UX review, 2026-11-11).
const fourCharts = (W, w) => ["mph", "ewt", "trip", "pct"].map((k) => `<figure class="hr-cell">${hourLines(k, W, w)}</figure>`).join("");
const peakNote = (w) => { const p = peakOnly(w); return p.length ? ` Peak-only lines (${p.map(esc).join(", ")}) are left out, since each hour of theirs covers a different part of the route.` : ""; };
const hourGrids = (w) => `<div class="hr-grid cw">${fourCharts(440, w)}</div><div class="hr-grid cn">${fourCharts(350, w)}</div>`;
const lazyHours = () => PERIODS.map((w) => w === DEFAULT
  ? `<div class="wv" data-w="${w}">${hourGrids(w)}</div>`
  : `<div class="wv" data-w="${w}" data-lazy="grids"><p class="verdict-note">Loading…</p></div>`).join("");
const hourSection = () => `<h2 id="by-hour">Speed and Excess Wait by Hour of Day</h2>
${forPeriod((w) => `<p>One line per Muni line. Hover a line to see which it is, click it to open it.${peakNote(w)}</p>`)}
<div class="fig hr-wide">${lazyHours()}</div>
${cite("By hour", "by-hour", [SRC_511, SRC_GTFS])}
`;

const MAPDATA = {
  stops: map.stops.map((s) => ({ c: [s.lon, s.lat], n: s.name, l: s.lines, e: s.ewt })),
  // p: the periods that list the line, so a line listed only over 5 years or Max (the KT, the 28) isn't drawn in the others
  lines: Object.fromEntries(Object.entries(map.lines).map(([k, v]) => [k, { s: v.shape, n: lineName(k), c: v.color, t: v.text, y: v.type,
    p: ` ${Object.entries(data.windows).filter(([, x]) => x.lines.some((r) => r.line === k)).map(([w]) => w).join(" ")} ` }])),
  ramp: RAMP,
};

const SCRIPT = `<script type="application/json" id="ml-data">${inlineJson(MAPDATA)}</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById("ml-data").textContent), el = document.querySelector(".ml-map");
  var b = [[-122.52, 37.70], [-122.355, 37.815]];
  var map = sfMap.create(el, { bounds: b, padding: function () { return 8; }, onReset: function () { pick(null); } });
  if (!map) return;
  var cur = null;
  function color(w) {
    var r = D.ramp, t = r.tokens.map(sfMap.token);
    return ["interpolate", ["linear"], ["get", "e" + w], r.domain[0], t[0], r.domain[1], t[1], r.domain[2], t[2]];
  }
  function stops() {
    return sfMap.collection(D.stops.map(function (s) {
      var p = { n: s.n, l: s.l.join(" ") };
      for (var k in s.e) p["e" + k] = s.e[k];
      return { type: "Feature", properties: p, geometry: { type: "Point", coordinates: s.c } };
    }));
  }
  function paint() {
    var w = window.muniDays();
    map.setFilter("stops", ["has", "e" + w]);
    map.setPaintProperty("stops", "circle-color", color(w));
    map.setFilter("stops-on", cur ? ["all", ["has", "e" + w], ["in", " " + cur + " ", ["concat", " ", ["get", "l"], " "]]] : ["==", ["get", "l"], "__none__"]);
    map.setPaintProperty("stops-on", "circle-color", color(w));
    // a less frequent line isn't in any period's p, so it is drawn only while it is picked
    var inP = ["in", " " + w + " ", ["get", "p"]], isCur = ["==", ["get", "r"], cur || ""];
    map.setFilter("routes", cur ? ["any", inP, isCur] : inP);
    map.setFilter("route-badges", cur ? isCur : inP);
  }
  // Draws one line bold and fades the rest, or restores the map when line is empty. Used by a pick and by hover.
  function look(line) {
    var only = line ? ["==", ["get", "r"], line] : null;
    map.setPaintProperty("routes", "line-opacity", line ? ["case", only, 0.9, 0.12] : 0.8);
    map.setPaintProperty("routes", "line-width", line ? ["case", only, 4, 1.4] : ["interpolate", ["linear"], ["zoom"], 11, 1.6, 14, 3, 17, 5]);
    map.setPaintProperty("stops", "circle-opacity", line ? 0.25 : 1);
  }
  function pick(line) {
    cur = line;
  document.querySelectorAll(".ml-list li").forEach(function (li) { li.classList.toggle("on", li.dataset.line === line); });
    var L = line && D.lines[line];
    look(line);
    paint();
    var note = document.querySelector(".ml-pick");
    note.innerHTML = L ? '<a href="' + location.pathname.replace(/lines\\/?$/, "lines/") + encodeURIComponent(line) + '/' + (location.search || "") + '">Open ' + L.n + "</a>" : "";
    if (L) {
      var all = [].concat.apply([], L.s), w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
      all.forEach(function (c) { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); });
      map.fitBounds([[w, s], [e, n]], { padding: 30, duration: 500 });
    }
  }
  map.once("load", function () {
    var before = sfMap.under(map);
    map.addSource("stops", { type: "geojson", data: stops() });
    map.addSource("lines", { type: "geojson", data: muniRoutes.feats(D.lines) });
    muniRoutes.add(map, "lines", before);
    map.addLayer({ id: "stops", type: "circle", source: "stops", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 14, 4.8, 17, 8], "circle-opacity": 1, "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 14, 1.2], "circle-stroke-color": "#fff" } }, before);
    map.addLayer({ id: "stops-on", type: "circle", source: "stops", filter: ["==", ["get", "l"], "__none__"], paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3.5, 14, 6, 17, 10], "circle-stroke-width": 1.2, "circle-stroke-color": sfMap.token("--ink") } }, before);
    muniRoutes.badges(map, "lines", before);
    paint();
    var pop = new maplibregl.Popup({ closeButton: false, offset: 10, maxWidth: "240px" });
    map.on("click", function (e) {
      var f = sfMap.near(map, e.point, cur ? ["stops-on", "stops"] : ["stops"])[0];
      if (!f) { pop.remove(); return; }
      var w = window.muniDays(), p = f.properties, v = p["e" + w];
      pop.setLngLat(f.geometry.coordinates).setHTML("<b>" + p.n + "</b><br>" + (v != null ? (+v).toPrecision(2) + " min excess wait" : "") + "<br><span style=\\"color:var(--muted)\\">Lines " + p.l + "</span>").addTo(map);
    });
  });
  window.addEventListener("muni:days", function () { if (map.sfLoaded && map.getLayer("stops")) paint(); });
  window.addEventListener("muni:line", function (e) { if (map.sfLoaded) pick(e.detail); });
  var more = document.querySelector(".ml-more"), side = document.querySelector(".ml-side");
  more.addEventListener("click", function () { var o = side.classList.toggle("open"); more.textContent = o ? "Show fewer lines" : "Show all lines"; more.setAttribute("aria-expanded", o ? "true" : "false"); });
  document.querySelectorAll(".ml-list li").forEach(function (li) {
    li.addEventListener("click", function (e) { if (e.target.closest("a")) return; pick(li.dataset.line); });
    // Bryan, 2026-11-10: "On hover, highlight on the map." Leaving the row returns the map to the picked line, if any.
    li.addEventListener("mouseenter", function () { if (map.sfLoaded && map.getLayer("stops")) look(li.dataset.line); });
    li.addEventListener("mouseleave", function () { if (map.sfLoaded && map.getLayer("stops")) look(cur); });
  });
})();
</script>`;

// The lists' sort, search filter and in-place rows, in their own script so they work even when the map can't start
// (Bryan, 2026-11-10: "66 Quintara doesn't open, but has a pointer cursor").
const LIST_SCRIPT = `<script>
(function () {
  // Sort: the first click on Wait / On Time puts the longest waits first (lines judged on time after them), on Speed the
  // slowest lines first, on Crowded the most crowded first, on Line A to Z.
  // A second click on the same header reverses it. Every period's list and every group sorts together.
  var by = "i", dir = 1, first = { i: 1, r: -1, e: -1, s: 1, c: -1 };
  document.querySelectorAll(".ml-head [data-sort]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.dataset.sort;
      dir = k === by ? -dir : first[k]; by = k;
      document.querySelectorAll(".ml-head [data-sort]").forEach(function (x) {
        x.setAttribute("aria-sort", x.dataset.sort === by ? (dir > 0 ? "ascending" : "descending") : "none");
      });
      // Sorted by Excess Wait or Speed, each period's list is one ranking of every line, trains and buses together,
      // in the first group's list with the group headings hidden; sorted by Line it goes back into its groups.
      document.querySelectorAll(".ml-side > .wv").forEach(function (wv) {
        var ols = [].slice.call(wv.querySelectorAll(".ml-list")), flat = by !== "i";
        var lis = [].concat.apply([], ols.map(function (ol) { return [].slice.call(ol.children); }));
        wv.classList.toggle("ml-flat", flat);
        lis.sort(function (a, c) {
          if (!flat && a.dataset.g !== c.dataset.g) return a.dataset.g - c.dataset.g;
          var x = parseFloat(a.dataset[by]), y = parseFloat(c.dataset[by]);
          if (isNaN(x)) return 1; if (isNaN(y)) return -1;
          return dir * (x - y);
        }).forEach(function (li) { (flat ? ols[0] : ols[+li.dataset.g]).appendChild(li); });
        ols.forEach(function (ol) { ol.hidden = !ol.children.length || [].every.call(ol.children, function (li) { return li.hidden; }); });
      });
    });
  });
  // The Line box filters both lists as you type: a row stays when its code starts with, or its name contains, the
  // text. A group heading with no rows left hides with them. While filtering, the phone's "first three" cut is lifted.
  window.addEventListener("muni:query", function (e) {
    var q = e.detail || "";
    document.querySelectorAll(".ml-list li").forEach(function (li) {
      var code = li.dataset.line.toLowerCase(), name = li.firstElementChild.textContent.toLowerCase();
      li.hidden = !!q && code.indexOf(q) !== 0 && name.indexOf(q) === -1;
    });
    document.querySelectorAll(".ml-list").forEach(function (ol) {
      var h = ol.previousElementSibling, any = [].some.call(ol.children, function (li) { return !li.hidden; });
      ol.hidden = !any; if (h && h.classList.contains("ml-group")) h.hidden = !any;
    });
    var side = document.querySelector(".ml-side"); if (side) side.classList.toggle("filtering", !!q);
  });
})();
</script>`;

const PAGE_CSS = `<style>
.ml-list li[hidden], .ml-list[hidden], .ml-group[hidden] { display: none; }




/* Four charts, two columns (speed and end-to-end time left, excess wait and % longer right), full width, short enough
   that the grid fits above the fold at 1366 x 768 (Bryan, 2026-11-10). */
.hr-wide { width: calc(50% + min(600px, 50vw - 24px)); }
@media (min-width: 641px) { .hr-grid.cw { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 20px; } }
.hr-cell { margin: 0; }
.hr-cell figcaption { font-size: 0.84rem; color: var(--muted); }
.hr-grid figcaption { font-size: 0.86rem; color: var(--muted); }
.hr-lines path { pointer-events: stroke; cursor: pointer; }
.hr-lines path:hover, .hr-lines path.on { stroke-opacity: 1; stroke-width: 3; stroke: var(--ink); }
.hr-grid { position: relative; }
.hr-tip { position: absolute; z-index: 2; pointer-events: none; background: #fff; border: 1px solid var(--rule); border-radius: 4px; padding: 3px 7px; font-size: 0.82rem; white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.12); }
.hr-tip[hidden] { display: none; }
.hr-badge { display: inline-block; min-width: 18px; padding: 0 4px; border-radius: 4px; font-weight: 700; font-size: 0.74rem; line-height: 17px; text-align: center; }
.hr-badge.round { border-radius: 50%; padding: 0; width: 17px; min-width: 0; }
/* The list starts on the text column's left edge and only the map reaches out to the right, to the edge a wide
   figure uses; a centred .fig.wide pushed the list past the left margin at 1366. */
.ml-fig { width: calc(50% + min(600px, 50vw - 24px)); }
.ml-grid { display: grid; grid-template-columns: minmax(560px, 640px) minmax(0, 1fr); gap: 16px; align-items: start; }
/* On a wide screen the list and map take the window's full width, the list the larger share (Bryan, 2026-11-16: "give this table more room by going full width on wider screens"). */
@media (min-width: 1100px) {
  .ml-fig { width: calc(100vw - 48px); margin-left: calc(50% - 50vw + 24px); }
  .ml-grid { grid-template-columns: minmax(560px, 1.25fr) minmax(0, 1fr); }
  .ml-list li, .ml-head { grid-template-columns: 1fr 52px 60px 116px 60px 64px 60px 64px; gap: 2px 8px; }
}
.ml-hint { margin: 0 0 6px; font-size: 0.82rem; color: var(--muted); }
.ml-side { max-height: 540px; overflow: auto; padding-right: 4px; }
.ml-map { height: 540px; }
h3.sub { font-size: 0.95rem; margin: 14px 0 0; }
.ml-group { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin: 10px 0 2px; }
.ml-list { list-style: none; padding: 0; margin: 0; }
.ml-list li { display: grid; grid-template-columns: 1fr 50px 56px 104px 56px 54px 56px 54px; gap: 2px 6px; align-items: center; padding: 5px 4px; border-bottom: 1px solid var(--rule); cursor: pointer; font-size: 0.88rem; }
.ml-list li.on { background: var(--raised); }
.ml-name { font-weight: 600; text-decoration: none; }
.ml-name:hover { text-decoration: underline; }
.ml-val { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.2; }
.ml-val b { font-variant-numeric: tabular-nums; white-space: nowrap; }
.ml-val .chg { font-size: 0.74rem; }
.ml-pct { font-size: 0.74rem; color: var(--muted); }
.ml-speed { color: var(--muted); font-size: 0.8rem; text-align: right; }
.ml-spark svg { margin: 0; display: block; width: 100%; max-width: 64px; height: auto; }
.ml-head button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-align: left; white-space: nowrap; }
.ml-head button:nth-child(2), .ml-head button:nth-child(4), .ml-head button:nth-child(6), .ml-head button:nth-child(8) { text-align: right; }
.ml-head button:hover { color: var(--ink); text-decoration: underline; }
.ml-flat .ml-group { display: none; }
.ml-head button { text-decoration: underline dotted; text-underline-offset: 3px; }
.ml-head button:not([aria-sort=ascending]):not([aria-sort=descending])::after { content: " ↕"; opacity: 0.7; }
.ml-head [aria-sort=ascending]::after { content: " ▲"; }
.ml-head [aria-sort=descending]::after { content: " ▼"; }
.ml-head { display: grid; grid-template-columns: 1fr 50px 56px 104px 56px 54px 56px 54px; gap: 2px 6px; font-size: 0.72rem; color: var(--muted); padding: 0 4px; }
.ml-more { display: none; font: inherit; font-size: 0.85rem; margin: 4px 0 8px; padding: 4px 10px; border: 1px solid var(--rule); border-radius: 6px; background: var(--paper); color: var(--ink); cursor: pointer; }
.ml-pick { font-size: 0.88rem; margin: 6px 0 0; color: var(--muted); }
@media (max-width: 760px) {
  /* minmax(0, ...) so a row's fixed columns can't push the grid wider than the page: with a bare 1fr the name
     column's longest word set a floor, and at 390 wide the rows ran 15px past the text column. */
  .ml-grid { grid-template-columns: minmax(0, 1fr); }
  /* On a phone the list keeps its place first (Bryan: "the list comes first on a phone") but opens folded to its
     first few lines, so the map is on the first screen too; "Show all lines" unfolds it. */
  /* Folded to whole rows (the first group's first three), not a pixel height, so no row is cut in half. */
  .ml-side { max-height: none; overflow: visible; }
  .ml-side:not(.open):not(.filtering) .ml-list li:nth-child(n+4), .ml-side:not(.open):not(.filtering) .ml-list ~ .ml-group, .ml-side:not(.open):not(.filtering) .ml-list ~ .ml-list { display: none; }
  .ml-page-lede { display: none; }
  .ml-side.open { max-height: none; }
  .ml-more { display: block; }
  .ml-map { height: 340px; }
  /* On a phone the riders keep their figure and drop their sparkline, so the name keeps some room. */
  .ml-list li, .ml-head { grid-template-columns: minmax(0, 1fr) 34px 92px 54px 38px; gap: 2px 7px; }
  /* and Speed drops its sparkline for the Crowded column (Bryan, 2026-11-16), and Wait / On Time
     its sparkline */
  .ml-rs, .ml-ss, .ml-es { display: none; }
  .ml-name { overflow-wrap: anywhere; }
  .ml-spark svg { width: 48px; height: auto; }
}
/* after the base rules above, so the wide columns win on a wide screen */
@media (min-width: 1100px) { .ml-list li, .ml-head { grid-template-columns: 1fr 48px 56px 112px 56px 64px 56px 62px; gap: 2px 7px; } }
</style>`;

// Each other period's by-hour grids, fetched when that period is picked: lines/hours-<days>.json.
const frag = (w) => ({ path: `${BASE}/lines/hours-${w}.json`, file: `transportation/muni/lines/hours-${w}.json`, html: Buffer.from(JSON.stringify({ grids: hourGrids(w) })), sitemap: false });
export const pages = () => PERIODS.filter((w) => w !== DEFAULT).map(frag);
// The dev server renders only the file asked for (scripts/site-files.mjs).
export function pageFor(file) {
  const m = /^transportation\/muni\/lines\/hours-([^.]+)\.json$/.exec(file);
  return m && PERIODS.includes(m[1]) && m[1] !== DEFAULT ? frag(m[1]) : null;
}

export function render() {
  const wDef = data.windows["365"];
  const body = `${CSS}${PAGE_CSS}
<h1>Train and Bus Lines</h1>
${DRAFT_NOTE}
<div class="muni-top">${periodSwitch()}${picker()}<span class="asof">Data through ${esc(THROUGH)}</span></div>
<h2 id="by-line">Key Performance Metrics by Line</h2>
<div class="fig ml-fig"><div class="ml-grid">
<div class="ml-side">
${forPeriod(list)}
</div>
<button type="button" class="ml-more" aria-expanded="false">Show all lines</button>
<div><div class="glmap ml-map" role="img" aria-label="Map of San Francisco with every stop on Muni's frequent lines coloured by its excess wait"></div>
<p class="key-line">Excess wait at each stop: <span class="ramp"></span> ${RAMP.domain[0]} to ${RAMP.domain[2]}+ min.</p>
<p class="ml-pick"></p></div>
</div></div>
${cite("Lines and map", "lines", [SRC_511, SRC_GTFS])}

${hourSection()}


${PERIOD_SCRIPT}${HOUR_SCRIPT()}${PICKER_SCRIPT}${LIST_SCRIPT}${MAP_HEAD}${ROUTE_JS}${SCRIPT}`;
  return page({
    title: "Muni Train and Bus Lines",
    description: `Excess wait at every stop on Muni's frequent lines, ${span(wDef.months)}, with the lines ranked.`,
    path,
    body,
    sourcesNote: SOURCES_NOTE,
    directory: false,
  });
}
