// Coordination across city departments: the upcoming SFMTA, Public Works and
// SFPUC projects on the Biking and Rolling Plan's network, one page each.
//
// Two panels. The list on the left is the same on every page; the detail on
// the right is one project's. Every project has its own address, so the list
// page and each project page are complete HTML files and none of it needs a
// script. On a wide screen a small script swaps the detail in place and moves
// the address with it; on a phone a row is a link to the project's own page
// and the back link at the top returns to the list.
//
// The prose is in content/transportation-projects.md. The data is
// data/coordination.json, written by the repo's
// tools/projects/coordination-projects.py from records other scripts already built.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { redirectPage } from "../redirect.mjs";
import { content } from "../content.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import { esc, ABOUT_DATA, SOURCES_NOTE, PLAN_URL, PROJECTS_DATA_READ } from "../transportation.mjs";
import { MAP_W, projectPoint, unprojectPoint, planNetwork } from "../transportation-map.mjs";
import { MAP_HEAD, encodeRuns, encodePoints, inlineJson } from "../maplibre.mjs";

export const path = "/transportation/bike/projects";
export const file = "transportation/bike/projects/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Current Repaving Projects", line: "The street projects coming up on the plan's network, and whether each one's scope mentions bikes.", order: 2 };
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = PROJECTS_DATA_READ;

const D = JSON.parse(
  fs.readFileSync(nodePath.join(import.meta.dirname, "..", "..", "data", "coordination.json"), "utf8"),
);
const P = D.projects;
const C = D.counts;

export const projectPath = (p) => `${path}/${p.slug}/`;
const n = (x) => Number(x).toLocaleString("en-US");

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// One cell of the dates grid: the date, linked to where it was read. The
// source's name is the link's tooltip, not a line in every cell, and a
// sentence quoted as the date shows as the date it gives (Bryan,
// 2026-09-29: "No need to say "project page's timeline" on every single cell").
function dateCell(d) {
  if (!d) return `<td class="np">not published</td>`;
  return `<td><a href="${esc(d.url)}" title="From ${esc(d.from)}">${esc(d.text && d.text.length <= 30 && !/^\d{4}-\d\d(-\d\d)?$/.test(d.text) ? d.text : shortDate(d.text && /^\d{4}-\d\d-\d\d$/.test(d.text) ? d.text : d.date.slice(0, 7)))}</a></td>`;
}
function dateGrid(sources) {
  const f = (name) => sources.find((d) => d.field === name);
  return `<table class="date-grid"><thead><tr><th></th><th scope="col">Start</th><th scope="col">End</th></tr></thead><tbody>
<tr><th scope="row">Public consultation</th>${dateCell(f("first public consultation"))}${dateCell(f("latest public consultation"))}</tr>
<tr><th scope="row">Construction</th>${dateCell(f("construction start"))}${dateCell(f("construction end"))}</tr>
</tbody></table>`;
}

// "2026-07-01" → "1 Jul 2026"; "2026-07" → "Jul 2026"; "2026" → "2026".
export function shortDate(s) {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  if (!m) return y;
  if (!d) return `${MONTHS[+m - 1]} ${y}`;
  return `${+d} ${MONTHS[+m - 1]} ${y}`;
}

export const dept = (p) =>
  p.partners && p.partners.length ? `${p.department} with ${p.partners.join(", ")}` : p.department;

// ---- The list ---------------------------------------------------------------

// The work each project does, as the list and its filter name it.
export const KIND = {
  repaving: "Repaving",
  "sewer, water and power": "Sewer, water or power",
  "streetscape and safety": "Streetscape",
  "spot repairs": "Spot repairs",
  "SFMTA bike and safety": "Bike, walk or safety",
  "SFMTA transit and parking": "Transit or parking",
};
const KIND_ORDER = ["repaving", "sewer, water and power", "streetscape and safety", "SFMTA bike and safety", "SFMTA transit and parking", "spot repairs"];

// The row's timing, to the month, so a row fits two lines.
function listWhen(p) {
  const my = (d) => (d ? shortDate(d.slice(0, 7)) : "");
  if (p.underWay) return p.end ? `Until ${my(p.end)}` : "Under way";
  if (p.start) return `From ${my(p.start)}`;
  return "No date";
}

function listRow(p, selected) {
  {
    // An early row names its phase in place of its kind of work.
    const when = listWhen(p);
    const meta = (p.early ? [when, p.phase, p.department] : [when, p.department, KIND[p.kind]]).filter(Boolean).join(" · ");
    const mi = p.planMiles ? `<span class="row-mi">${p.planMiles} mi of planned bikeway</span>` : "";
    const text = [p.name, ...p.streets].join(" ").toLowerCase();
    return `<li data-kind="${esc(p.kind)}" data-plan="${planCat(p)}" data-text="${esc(text)}"><a href="${projectPath(p)}"${
      p.slug === selected ? ' aria-current="true"' : ""
    }><b>${esc(p.name)}</b><span class="row-plan">${planChip(p)}${mi}</span><span class="small">${esc(meta)}</span></a></li>`;
  }
}

// Two groups (Bryan, 2026-09-29: "highlight other projects that might be early
// enough to do something about them"): projects whose department gives their
// phase as planning, design or outreach, soonest start first; then the rest
// in the list's usual order. tools/projects/coordination-projects.py sets "early".
// Within the early group: starts still ahead, soonest first; then no start published.
const startKey = (p) => (p.start ? p.start.padEnd(10, "0") : "");
const earlyRank = (p) => (!p.start ? 1 : p.underWay ? 2 : 0);
const EARLY = P.filter((p) => p.early).sort((a, b) =>
  earlyRank(a) - earlyRank(b) ||
  (earlyRank(a) === 2 ? startKey(b).localeCompare(startKey(a)) : startKey(a).localeCompare(startKey(b))) ||
  a.name.localeCompare(b.name));
const LATER = P.filter((p) => !p.early);
function listRows(selected) {
  const group = (label, note, rows) =>
    rows.length
      ? `<li class="grp"><h2 class="grp-head">${label} <span class="grp-n">${rows.length}</span></h2>${note ? `<p class="small">${note}</p>` : ""}</li>\n${rows.map((p) => listRow(p, selected)).join("\n")}`
      : "";
  return [
    group("Early enough to change", "The department lists it as planning or design, and its construction start has not passed. Soonest start first.", EARLY),
    group("Other current projects", "Under construction, legislated, past its published start, or phase not given.", LATER),
  ].join("\n");
}

// ---- Meetings coming up -----------------------------------------------------

// A published date as the page prints dates elsewhere, with the time as the
// body publishes it.
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function meetingWhen(m) {
  const d = new Date(`${m.date}T12:00:00Z`);
  return `${WEEKDAY[d.getUTCDay()]} ${shortDate(m.date)}${m.time ? `, ${m.time}` : ""}`;
}
// What the meeting has on it for this project: the agenda item, or the event.
function meetingWhat(m) {
  if (m.item) {
    return `${esc(m.body)}, item ${esc(m.item)}: <a href="${esc(m.url)}">${esc(m.title.length > 140 ? m.title.slice(0, 138) + "…" : m.title)}</a>${
      m.agenda && m.agenda !== m.url ? ` (<a href="${esc(m.agenda)}">agenda</a>)` : ""
    }`;
  }
  return `<a href="${esc(m.meetingUrl)}">${esc(m.meeting)}</a>`;
}
const U = D.upcoming || { days: 60, sources: [], agendaPending: [] };
const SOON = P.filter((p) => p.meetings && p.meetings.length).sort(
  (a, b) => a.meetings[0].date.localeCompare(b.meetings[0].date) || a.name.localeCompare(b.name),
);
const SOURCE_LINKS = {
  sfmta: ["SFMTA meetings and events", "https://www.sfmta.com/meetings-events"],
  bos: ["Board of Supervisors calendar", "https://sfgov.legistar.com/Calendar.aspx"],
  pwc: ["Public Works Commission calendar", "https://sfpublicworks.org/about/public-works-commission-calendar"],
  sfpuc: ["SFPUC Commission agendas", "https://www.sfpuc.gov/about-us/boards-commissions-committees/sfpuc-commission/agendas-minutes-resolutions-log"],
};
function soon() {
  const src = U.sources.filter((x) => SOURCE_LINKS[x.id] && x.status === "read").map((x) => `<a href="${SOURCE_LINKS[x.id][1]}">${SOURCE_LINKS[x.id][0]}</a>`);
  const failed = U.sources.filter((x) => SOURCE_LINKS[x.id] && x.status !== "read").map((x) => SOURCE_LINKS[x.id][0]);
  const rows = SOON.map(
    (p) => `<li><a class="soon-name" href="${projectPath(p)}">${esc(p.name)}</a><span class="small">${esc(meetingWhen(p.meetings[0]))}</span><span class="soon-what">${meetingWhat(p.meetings[0])}</span></li>`,
  ).join("");
  const pending = (U.agendaPending || []).map((m) => `<a href="${esc(m.url)}">${esc(m.body)}${m.special ? " special meeting" : ""}, ${esc(shortDate(m.date))}</a>`);
  return `<section class="coord-soon" aria-label="Meetings in the next ${U.days} days">
<h2 class="grp-head">Meetings and events in the next ${U.days} days <span class="grp-n">${SOON.length}</span></h2>
<p class="small">Posted agendas and events that name one of these projects.${
  failed.length ? ` Not read this time: ${failed.join(", ")}.` : ""
}</p>
<ul class="cite" data-for="Meetings" data-group="Projects and city records">${src.map((a) => `<li>${a}</li>`).join("")}</ul>
${rows ? `<ul class="soon-rows">${rows}</ul>` : `<p>No posted agenda or event names any of these projects.</p>`}
${pending.length ? `<p class="small">Agenda not yet posted, check back: ${pending.join("; ")}.</p>` : ""}
</section>`;
}

// The top of a project's page: its next meeting, or whether it is early
// enough to change and whom to ask.
function nextLine(p) {
  if (p.meetings && p.meetings.length) {
    const m = p.meetings[0];
    const more = p.meetings.length - 1;
    return `<p class="next-meeting"><b>${m.item ? "Next meeting" : "Next event"}:</b> ${esc(meetingWhen(m))}, ${meetingWhat(m)}${
      more > 0 ? ` <span class="small">${more} more in the next ${U.days} days.</span>` : ""
    }</p>`;
  }
  if (p.early) {
    const own = p.links.find((l) => l.department === p.department && !/coordination feed/i.test(l.label));
    return `<p class="next-meeting"><b>Early enough to change:</b> ${esc(p.department)} gives its phase as ${esc(p.phase)}${
      own ? `; its <a href="${esc(own.url)}">project page</a> may list a contact` : ""
    }. No meeting on it is posted for the next ${U.days} days.</p>`;
  }
  return "";
}

// How much of the plan's missing bikeway on its blocks the project builds or
// upgrades to the plan's type, 0% to 100%, or a named state (Bryan,
// 2026-09-29: "Give the project a rating from 100% to 0% for how much of the
// planned infra it builds or upgrades"). tools/projects/coordination-projects.py
// computes it (planRating) and names its source; the chip prints its label,
// and the filter offers its bands. Colours run down one ramp, teal for most
// built to brown for none; the states that are not a rating stay neutral.
const PLAN_CATS = [
  ["all", "Builds 100% of the missing plan bikeway"],
  ["most", "Builds 50 to 99%"],
  ["some", "Builds 1 to 49%"],
  ["none", "Builds 0%, or 0% in published scope"],
  ["not-stated", "Not stated"],
  ["already-built", "Plan bikeway already built"],
  ["no-overlap", "No known overlap with the plan"],
];
const PLAN_CAT = Object.fromEntries(PLAN_CATS);
const planCat = (p) => p.planRating.band;
const mi = (x) => `${x} mi`;
function planTitle(p) {
  const r = p.planRating;
  if (r.state === "percent") return `Builds or upgrades ${mi(r.builtMiles)} of the ${mi(r.baseMiles)} of its street segments on the plan that lack the plan's bikeway type, or lacked it before this project`;
  if (r.state === "scope-none") return `Its published scope names no bike work for the ${mi(r.baseMiles)} of its street segments on the plan that lack the plan's bikeway type`;
  return r.note || PLAN_CAT[r.band];
}
const planChip = (p) => `<span class="plan-chip ${planCat(p)}" title="${esc(planTitle(p))}">${esc(p.planRating.label)}</span>`;
// The project page's line beside the chip. The finding under it already says
// what the rating means for this project (Bryan, 2026-10-01: "there's a lot of
// repetition that's not useful"), so the line keeps only the detail the finding
// doesn't carry, a percent rating's note. The chip's tooltip still carries
// the full rating, and the sources
// go to the end of the page with the others.
function ratingLine(p) {
  const r = p.planRating;
  const what = r.state === "percent" ? r.note || "" : "";
  const cites = `<ul class="cite" data-for="This project's rating" data-group="Projects and city records">${r.sources.map((s) => `<li><a href="${esc(s.url)}">${esc(s.label)}</a></li>`).join("")}</ul>`;
  return (what ? ` <span class="small">${esc(what[0].toUpperCase() + what.slice(1))}</span>` : "") + cites;
}

function filters() {
  const counts = {};
  for (const p of P) counts[p.kind] = (counts[p.kind] || 0) + 1;
  const opts = KIND_ORDER.filter((k) => counts[k])
    .map((k) => `<option value="${esc(k)}">${esc(KIND[k])} (${counts[k]})</option>`)
    .join("");
  const plan = PLAN_CATS.map(([k, option]) => [k, option, P.filter((p) => planCat(p) === k).length])
    .filter(([, , n]) => n)
    .map(([k, option, n]) => `<option value="${k}">${esc(option)} (${n})</option>`).join("");
  return `<div class="coord-filter">
<input type="search" placeholder="Search for street or project" aria-label="Search for street or project" data-filter-text>
<select aria-label="Filter by type of work" data-filter-kind><option value="">All work (${P.length})</option>${opts}</select>
<select aria-label="Filter by the Biking and Rolling Plan" data-filter-plan><option value="">Bike plan: any (${P.length})</option>${plan}</select>
<p class="filter-note">Bike plan: the share of the bikeway the plan still needs on a project's streets that the project builds to the plan's standard. <a href="/transportation/bike/about#plan-rating">How it's rated</a>.</p>
<ul class="cite" data-for="Bike plan ratings" data-group="The bike network"><li><a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a></li><li><a href="https://www.sfmta.com/projects">SFMTA project pages</a></li><li>the city's <a href="https://data.sf.gov/d/btxj-k9uh">coordination feed</a>, as of ${esc(D.feed.queried)}</li></ul>
</div>`;
}

// ---- The small map --------------------------------------------------------------

// The map is MapLibre over the basemap (src/maplibre.mjs): the basemap's
// streets place the job, the plan's network is drawn over it in grey, and
// the project's street segments over that in their category's colour with a
// white edge. The callouts are an SVG laid over the map in the same frame.
//
// One run per block and one point per intersection, so the drawing holds every
// block the project does (criterion E3): pipeline/transportation-geometry-check.py
// counts the runs and points in each page's map data. A block too short to
// span a metre is a run of one point, drawn as a dot, as an intersection is.

// The plan's network under every project map, thinned to the vertices more
// than about ten metres off a straight stretch: a map 240 pixels wide cannot
// show a smaller bend, and the network is repeated once per project page.
const BASE = planNetwork(10);

// Where each block stands against the plan, as the map colours it and its
// callouts name it (Bryan, 2026-09-28: "highlight the three different
// categories ... And use labeled callouts for each color on the map, to avoid
// having to draw a legend"). Tan for a plan block short of the plan, as on
// the Departments map; teal for one that already has the plan's bikeway, the
// colour the site gives the plan's bikeway being there (the Departments map's
// light grey for it vanished against this map's grey streets); a dark
// neutral for a block off the plan, since the plan asks nothing of it. Drawn
// in this order, so the blocks that need work sit on top.
const MAP_CATS = [
  ["none", "No planned bikeway"],
  ["has", "Has planned bikeway"],
  ["needs", "Needs better bikeway"],
];

// One callout per category present: a label with a short leader to one of
// its blocks. Each label takes the nearest of a ring of spots around its
// block that stays inside the frame, clear of the labels already placed and
// of the project's own blocks. Sizes are in the frame's drawing units, worked
// from the map's width on screen (about 250px: 240 on a wide screen, the
// 260px height on a phone).
function callouts(anchors, vb, drawnPts) {
  const [x0, y0, side] = vb;
  const u = side / 250, fs = 11 * u, pad = 4 * u, gap = 12 * u, h = fs * 1.25;
  const placed = [];
  const overlap = (a, b) =>
    Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
  const out = [];
  for (const { cat, label, pt } of anchors) {
    const w = label.length * fs * 0.56;
    let best = null;
    for (const r of [1, 2, 3.5]) {
      for (const [dx, dy] of [[1, 0], [-1, 0], [1, -1], [-1, -1], [1, 1], [-1, 1], [0, -1.4], [0, 1.4]]) {
        const bx = dx > 0 ? pt[0] + gap * r : dx < 0 ? pt[0] - gap * r - w : pt[0] - w / 2;
        const by = pt[1] + dy * gap * r - h / 2;
        const box = { x: bx, y: by, w, h };
        const outside = Math.max(0, x0 + pad - bx) + Math.max(0, bx + w - (x0 + side - pad)) +
          Math.max(0, y0 + pad - by) + Math.max(0, by + h - (y0 + side - pad));
        const hitLabels = placed.reduce((t, q) => t + overlap(box, q), 0);
        const hitBlocks = drawnPts.filter((q) => q[0] > bx && q[0] < bx + w && q[1] > by && q[1] < by + h).length;
        const score = outside * 1e4 + hitLabels * 100 + hitBlocks * gap * 4 + r * gap;
        if (!best || score < best.score) best = { score, box };
      }
    }
    placed.push(best.box);
    const { x, y, w: bw } = best.box;
    // The leader meets the label's nearer end, at the middle of its line.
    const lx = pt[0] < x ? x - 2 * u : pt[0] > x + bw ? x + bw + 2 * u : x + bw / 2;
    const ly = pt[0] >= x && pt[0] <= x + bw ? (pt[1] < y ? y : y + h) : y + h / 2;
    out.push(`<path class="lead ${cat}" d="M${pt[0].toFixed(1)} ${pt[1].toFixed(1)}L${lx.toFixed(1)} ${ly.toFixed(1)}" stroke-width="${(1.5 * u).toFixed(2)}"></path>
    <circle class="tip ${cat}" cx="${pt[0].toFixed(1)}" cy="${pt[1].toFixed(1)}" r="${(3 * u).toFixed(2)}"></circle>
    <text class="call" x="${x.toFixed(1)}" y="${(y + h * 0.78).toFixed(1)}" font-size="${fs.toFixed(1)}" stroke-width="${(3 * u).toFixed(2)}">${esc(label)}</text>`);
  }
  return out.join("\n    ");
}

function map(p) {
  const gc = p.geometryCats || [], nc = p.nodeCats || [];
  const byCat = MAP_CATS.map(([cat, label]) => ({
    cat, label,
    lines: p.geometry.filter((_, i) => (gc[i] || "none") === cat),
    pts: (p.nodes || []).filter((_, i) => (nc[i] || "none") === cat),
  })).filter((c) => c.lines.length || c.pts.length);
  if (!byCat.length) return `<p class="small coord-map coord-nomap">No street segment geometry is published, so nothing is drawn.</p>`;
  // Cropped to the project's own streets with a margin, so a job of a few
  // blocks is legible (Bryan, 2026-09-29: "needs to be possible to zoom in
  // on"). The frame never shrinks below a fifth of the city's width, so the
  // streets around the job still place it. The margin is wide enough for the
  // callouts to sit beside the job rather than on it. No ring: a ring round a
  // scattered job missed its streets (Bryan, 2026-09-28: "just draw the
  // streets involved").
  const xy = byCat.flatMap((c) => [...c.lines.flat(), ...c.pts]).map(projectPoint);
  const xs = xy.map((q) => q[0]), ys = xy.map((q) => q[1]);
  const side = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), MAP_W / 5) * 1.4;
  const cx = (Math.max(...xs) + Math.min(...xs)) / 2, cy = (Math.max(...ys) + Math.min(...ys)) / 2;
  const vb = [cx - side / 2, cy - side / 2, side, side];
  const round5 = (v) => Math.round(v * 1e5) / 1e5;
  const [w, s] = unprojectPoint([vb[0], vb[1] + side]).map(round5), [e, n] = unprojectPoint([vb[0] + side, vb[1]]).map(round5);
  // Each category's callout points at the block nearest the middle of that
  // category's own blocks, traded against distance from the other
  // categories', so each callout points at a block that is plainly its colour.
  const anchors = byCat
    .map((c) => ({
      cat: c.cat, label: c.label,
      mids: [...c.lines.map((l) => projectPoint(l[Math.floor(l.length / 2)])), ...c.pts.map((q) => projectPoint(q))],
    }))
    .map((c, _, all) => {
      const mx = c.mids.reduce((t, q) => t + q[0], 0) / c.mids.length, my = c.mids.reduce((t, q) => t + q[1], 0) / c.mids.length;
      const others = all.filter((o) => o !== c).flatMap((o) => o.mids);
      const worth = (q) =>
        Math.min(side / 4, ...others.map((o) => Math.hypot(o[0] - q[0], o[1] - q[1]))) - 0.3 * Math.hypot(q[0] - mx, q[1] - my);
      const pt = c.mids.reduce((b, q) => (worth(q) > worth(b) ? q : b));
      return { cat: c.cat, label: c.label, pt };
    });
  const data = {
    bounds: [[w, s], [e, n]],
    cats: byCat.map((c) => ({ cat: c.cat, l: encodeRuns(c.lines), p: encodePoints(c.pts) })),
  };
  const present = anchors.map((a) => a.label.toLowerCase()).join(", ");
  return `<figure class="coord-map" role="img" aria-label="${esc(
    `A map of San Francisco's streets with the plan's bike network in grey and ${p.name}'s street segments marked by where they stand against the plan: ${present}.`,
  )}">
  <div class="glmap coord-gl"></div>
  <svg class="coord-calls" viewBox="${vb.map((v) => v.toFixed(1)).join(" ")}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    ${callouts(anchors, vb, xy)}
  </svg>
  <script type="application/json" class="coord-data">${inlineJson(data)}</script>
</figure>`;
}

// The project maps' script: window.sfCoordMaps(root) draws every map under
// root not yet drawn, and sfCoordMaps.remove(root) lets go of them before the
// list swaps a project's detail in place (SCRIPT below). The plan's network
// rides once, in the page's own script, since every map draws the same one.
const COORD_MAP_SCRIPT = `<script>
(function () {
  var BASE = ${inlineJson(BASE)}, base = null;
  var COL = { none: "#3d4450", has: "--seq-3", needs: "--seq-2" };
  function colour(c) { return COL[c].charAt(0) === "-" ? sfMap.token(COL[c]) : COL[c]; }
  function draw(fig) {
    if (fig.sfMap || !window.sfMap) return;
    var D = JSON.parse(fig.querySelector(".coord-data").textContent);
    // The frame is fixed: the callouts are drawn for it.
    var m = sfMap.create(fig.querySelector(".coord-gl"), { bounds: D.bounds, interactive: false });
    if (!m) return;
    fig.sfMap = m;
    base = base || sfMap.features(sfMap.decode(BASE));
    m.on("load", function () {
      var before = sfMap.under(m);
      m.addSource("plan", { type: "geojson", data: sfMap.collection(base) });
      m.addLayer({ id: "plan", type: "line", source: "plan", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#8d949d", "line-opacity": 0.6, "line-width": 1.5 } }, before);
      D.cats.forEach(function (c) {
        var f = sfMap.features(sfMap.decode(c.l)).concat(sfMap.points(c.p).map(function (q) { return { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: q } }; }));
        m.addSource(c.cat, { type: "geojson", data: sfMap.collection(f) });
        var line = { "line-cap": "round", "line-join": "round" }, isLine = ["==", ["geometry-type"], "LineString"], isDot = ["==", ["geometry-type"], "Point"];
        m.addLayer({ id: c.cat + "-halo", type: "line", source: c.cat, filter: isLine, layout: line, paint: { "line-color": "#fff", "line-width": 7 } }, before);
        m.addLayer({ id: c.cat + "-dot-halo", type: "circle", source: c.cat, filter: isDot, paint: { "circle-color": "#fff", "circle-radius": 5 } }, before);
        m.addLayer({ id: c.cat, type: "line", source: c.cat, filter: isLine, layout: line, paint: { "line-color": colour(c.cat), "line-width": 4 } }, before);
        m.addLayer({ id: c.cat + "-dot", type: "circle", source: c.cat, filter: isDot, paint: { "circle-color": colour(c.cat), "circle-radius": 3.5 } }, before);
      });
    });
  }
  function all(root) { (root || document).querySelectorAll(".coord-map").forEach(function (fig) { if (fig.querySelector(".coord-data")) draw(fig); }); }
  all.remove = function (root) { (root || document).querySelectorAll(".coord-map").forEach(function (fig) { if (fig.sfMap) { fig.sfMap.remove(); fig.sfMap = null; } }); };
  window.sfCoordMaps = all;
  all();
})();
</script>`;

// ---- One project's detail ---------------------------------------------------

// The plan's facility classes, as a phrase a sentence can carry.
const FACILITY_PHRASE = {
  Separated: "a separated bikeway",
  Shared: "a shared street",
  "Shared L3": "a Level 3 shared street",
  "Shared-use Path": "a shared-use path",
  "Car-free": "a car-free street",
  Undecided: "a bikeway of undecided type",
};
const facilityPhrase = (f) => FACILITY_PHRASE[f] || f.toLowerCase();

// The same finding cut to a map popup's width: Bryan, 2026-09-29, on the
// Departments popup, "Try to shorten this to make it easier to read."
export function shortFinding(p) {
  if (p.geometryKind === "none") return "No map published, so its planned bikeway streets are unknown.";
  if (!p.onPlan) return "Not on a planned bikeway street.";
  const n = p.planBlocks, m = p.missingBlocks || 0;
  if (!m) return `Planned bikeway already on all ${n === 1 ? "its street segment" : `${n} street segments`}.`;
  const tail = p.gap ? " Scope doesn't mention bikes." : p.source === "sfmta" ? " SFMTA lists it as a bike project." : " Scope names bike work.";
  return `Planned bikeway missing on ${m} of ${n} ${n === 1 ? "street segment" : "street segments"}.${tail}`;
}

// The one sentence the page exists to say about this project.
export function finding(p) {
  // A project with no published map has no blocks to test, so nothing can
  // be said about the plan's network there.
  if (p.geometryKind === "none") {
    return `The project publishes no map, so whether it touches the Biking and Rolling Plan's network is not known. It is listed because ${
      p.source === "sfmta" ? "SFMTA tags the project Bike" : "the project's published scope names bike work"
    }.`;
  }
  if (!p.onPlan) {
    return `None of the project's street segments is on the Biking and Rolling Plan's network. It is listed because ${
      p.source === "sfmta" ? "SFMTA tags the project Bike" : "the project's published scope names bike work"
    }.`;
  }
  const n = p.planBlocks;
  const blocks = (k) => `${k} ${k === 1 ? "street segment" : "street segments"}`;
  if (!p.missingBlocks) {
    return n === 1
      ? "The project's one street segment on a planned bikeway street already has an all-ages bikeway."
      : `All ${n} of the project's street segments on planned bikeway streets already have an all-ages bikeway.`;
  }
  const lack = `${p.missingBlocks === n ? (n === 1 ? "The project's one street segment" : `All ${n} of the project's street segments`) : `${p.missingBlocks} of the project's ${blocks(n)}`} on planned bikeway streets ${p.missingBlocks === 1 ? "lacks" : "lack"} the all-ages bikeway the Biking and Rolling Plan calls for.`;
  if (p.gap) return `<b>${lack} Its published scope does not mention bikes.</b>`;
  // An SFMTA row's plan rating says what its layer and page show it building.
  const r = p.planRating;
  if (p.source === "sfmta" && r.state === "percent") return `${lack} SFMTA's bikeway layer and project page show it building or upgrading ${r.builtMiles} mi of the plan's bikeway.`;
  if (p.source === "sfmta" && r.state === "scope-none") return `${lack} SFMTA's page for it names no bike work.`;
  if (p.source === "sfmta") return `${lack} SFMTA lists it as a bike project, but does not say whether it builds that bikeway.`;
  return `${lack} Its published scope names bike work, but does not say whether it builds that bikeway.`;
}

function planLine(p) {
  if (p.geometryKind === "none") return "Not known: no map published.";
  if (!p.onPlan) return "Nothing on these street segments.";
  return p.planFacilities
    .map((f) => {
      const name = facilityPhrase(f.facility).replace(/^an? /, "");
      return `${esc(name[0].toUpperCase() + name.slice(1))}, ${f.miles} mi on ${esc(f.streets.join(", "))}`;
    })
    .join("<br>");
}

// Walked, as on the overview (lib/walknet.py via coordination-projects.py):
// the plan's quarter mile first, then the overview's one and two blocks.
function reachParts(r, census = true) {
  const parts = [`${n(r.residents)} residents${census ? " (2020 census)" : ""}`];
  if (r.schools.length) parts.push(`${r.schools.length} school${r.schools.length === 1 ? "" : "s"}`);
  if (r.libraries.length) parts.push(`${r.libraries.length} librar${r.libraries.length === 1 ? "y" : "ies"}`);
  return parts.join(", ");
}

function reachLine(p) {
  const r = p.reach;
  const any = (x) => x && (x.residents || x.schools.length || x.libraries.length);
  const shorter = D.reach.thresholds.filter((t) => t.id !== D.reach.default && any(r?.byThreshold?.[t.id]));
  if (!any(r) && !shorter.length) return null;
  const k = p.missingBlocks;
  const head = any(r) ? `${reachParts(r)} would be newly within a quarter-mile walk` : "No one new would be within a quarter-mile walk";
  // Each shorter distance counts people with no all-ages bikeway that close
  // today, a larger group than at the quarter mile, so its figure can be larger.
  const tail = shorter
    .map((t, i) => `${reachParts(r.byThreshold[t.id], !any(r) && i === 0)} with none within ${t.short} today would have one`)
    .join("; ");
  return `${head} of an all-ages bikeway if the planned bikeway were built on the project's ${k === 1 ? "street segment" : `${k} street segments`} that lack one${tail ? `. Closer in: ${tail}` : ""}`;
}

function scopeText(p) {
  if (!p.scopeText) return "None published.";
  if (/^https?:\/\//.test(p.scopeText)) return `<a href="${esc(p.scopeText)}">On the project page</a>`;
  return `“${esc(p.scopeText)}”`;
}

// A record is the project's own when the match was exact, strong or probable
// (tools/projects/project-record.py gives strong and probable only to a named program
// or a matching contract award, never to a street alone). Everything else was
// decided on a street or block this project covers, which is a place, not the
// project (0 of 10 street-matched links checked on 2026-09-29 were about their
// project).
const OWN = new Set(["exact", "strong", "probable"]);
// A city body's own agenda, minutes or order is a decision; an item copied off
// the project's web page (a milestone, a notice, an open house) is not, and is
// listed apart so it never reads as a vote.
const isPage = (r) => r.kind === "project-page";
const ownRecords = (p) => p.records.filter((r) => OWN.has(r.grade) && !isPage(r));
const pageRecords = (p) => p.records.filter((r) => isPage(r));
const nearbyRecords = (p) => p.records.filter((r) => !OWN.has(r.grade) && !isPage(r));
const BODIES_READ =
  "SFMTA engineering hearings, the SFMTA Board, the Board of Supervisors, the SFPUC Commission, the Public Works Commission, the SFCTA Board or the Recreation and Park Commission";

const recordItem = (r) =>
  `<li><a href="${esc(r.url)}">${esc(r.title)}</a><span class="small">${esc(
    [r.when || shortDate(r.date) || "Undated", r.label, r.decision].filter(Boolean).join(" · "),
  )}</span></li>`;

function folded(label, items) {
  if (!items.length) return "";
  return `<details><summary>${label}</summary><ul class="coord-list-plain">${items.join("")}</ul></details>`;
}

// Construction dates for this project and the listed projects that share its
// blocks, as a timeline (Bryan, 2026-09-29: "it would be helpful to see a
// timeline view of when construction starts and ends for each project. And
// also identify the dates"). A project's construction start and end come
// from its dates grid, else its listed start and end. Only listed projects
// carry dates; the others are counted in the note under the chart.
const BY_ID = new Map(P.map((q) => [q.id, q]));
const ym = (s) => (s ? { y: +s.slice(0, 4), m: s.length >= 7 ? +s.slice(5, 7) : 1 } : null);
const monthsOf = (d) => d.y * 12 + d.m - 1;
function constructionDates(q) {
  const f = (name) => (q.dateSources || []).find((d) => d.field === name);
  const cs = f("construction start"), ce = f("construction end");
  return { start: (cs && cs.date) || q.start || null, end: (ce && ce.date) || q.end || null };
}
function timeline(p) {
  const rows = [{ q: p, self: true }, ...p.related.map((r) => ({ q: BY_ID.get(r.id), r })).filter((x) => x.q && x.q.slug !== p.slug)]
    .map((x) => ({ ...x, ...constructionDates(x.q) }))
    .filter((x) => x.start || x.end);
  if (rows.length < 2) return "";
  const undated = p.related.length - rows.filter((x) => !x.self).length;
  rows.sort((a, b) => (a.self ? -1 : b.self ? 1 : (a.start || a.end).localeCompare(b.start || b.end)));
  const pts = rows.flatMap((x) => [x.start, x.end]).filter(Boolean).map((d) => monthsOf(ym(d)));
  const lo = Math.floor(Math.min(...pts) / 12) * 12, hi = Math.ceil((Math.max(...pts) + 1) / 12) * 12;
  const W = 720, L = 250, R = 16, RH = 26, T = 22, H = T + rows.length * RH + 6;
  // x is months since year 0, so a bar runs from its start month to the end of its end month.
  const x = (mo) => L + ((W - L - R) * (mo - lo)) / (hi - lo);
  const mo = (px) => lo + ((px - L) * (hi - lo)) / (W - L - R);
  const years = [];
  for (let yr = lo / 12; yr <= hi / 12; yr++) years.push(yr);
  const step = years.length > 12 ? 2 : 1;
  const label = (q) => (q.name.length > 38 ? q.name.slice(0, 36) + "…" : q.name);
  const marked = rows.map((row, i) => {
    const s = row.start && monthsOf(ym(row.start)), e = row.end && monthsOf(ym(row.end));
    const both = Boolean(row.start && row.end);
    const tip = `${row.q.name}: construction ${row.start ? shortDate(row.start) : "start not published"} to ${row.end ? shortDate(row.end) : "end not published"}`;
    const txt = both ? `${shortDate(row.start)} – ${shortDate(row.end)}` : row.start ? `from ${shortDate(row.start)}` : `until ${shortDate(row.end)}`;
    // Right of the mark if it fits, else left of it clear of the names, else inside the bar.
    const tw = txt.length * 6.2, x0 = both ? x(s) : x(row.start ? s : e), x1 = both ? x(e + 1) : x0;
    const gap = both ? 6 : 9;
    let tx = x1 + gap, anchor = "start", inside = false, below = 0;
    if (tx + tw > W) {
      if (x0 - gap - tw >= L) { tx = x0 - gap; anchor = "end"; }
      else if (x1 - x0 >= tw + 8) { tx = (x0 + x1) / 2; anchor = "middle"; inside = true; }
      else { tx = W; anchor = "end"; below = RH / 2 - 2; }
    }
    // A bar is at least 3 pixels wide, so a one-month job still shows.
    return { i, self: Boolean(row.self), q: row.q, both, s, e: both ? Math.max(e + 1, mo(x(s) + 3)) : null, at: both ? null : row.start ? s : e, tip, txt, tx: mo(tx), anchor, inside, below };
  });
  // Plot's text anchor and offsets are one value per mark, so the date labels
  // are drawn in one mark per placement.
  const dateMarks = [];
  for (const anchor of ["start", "end", "middle"]) for (const inside of [false, true]) for (const below of [0, RH / 2 - 2]) {
    const sel = marked.filter((r) => r.anchor === anchor && r.inside === inside && r.below === below);
    if (sel.length) dateMarks.push(Plot.text(sel, { x: "tx", y: "i", text: "txt", dy: below, textAnchor: anchor, ...(inside ? { fill: "#fff", fontWeight: 600 } : {}) }));
  }
  const shape = (self) => [
    Plot.barX(marked.filter((r) => r.both && r.self === self), { x1: "s", x2: "e", y: "i", insetTop: RH / 2 - 6, insetBottom: RH / 2 - 6, rx: 2, fill: self ? "var(--seq-3)" : "var(--seq-2)", title: (r) => r.tip }),
    Plot.dot(marked.filter((r) => !r.both && r.self === self), { x: "at", y: "i", r: 5, fill: self ? "var(--seq-3)" : "var(--seq-2)", title: (r) => r.tip }),
  ];
  const nowMo = monthsOf(ym(D.generated || ""));
  const showNow = Number.isFinite(nowMo) && nowMo >= lo && nowMo <= hi;
  const svg = plotSVG({
    width: W, height: H, marginLeft: L, marginRight: R, marginTop: T, marginBottom: 6,
    style: { fontSize: "12px" },
    x: { domain: [lo, hi], axis: null },
    y: { domain: marked.map((r) => r.i), padding: 0, axis: null },
    marks: [
      Plot.ruleX(years.filter((_, i) => i % step === 0).map((yr) => yr * 12), { stroke: "var(--rule)", insetTop: -6, insetBottom: -2 }),
      Plot.text(years.filter((_, i) => i % step === 0), { x: (yr) => yr * 12, frameAnchor: "top", text: String, lineAnchor: "middle", dy: -10 - 0.32 * 12 }),
      showNow ? Plot.ruleX([nowMo], { stroke: "var(--muted)", strokeDasharray: "3 3", insetTop: -6, insetBottom: -2 }) : null,
      showNow ? Plot.text([nowMo], { x: (v) => v, frameAnchor: "bottom", text: () => "today", dx: 4, dy: -0.32 * 12, textAnchor: "start", lineAnchor: "middle" }) : null,
      Plot.text(marked.filter((r) => r.self), { y: "i", frameAnchor: "left", dx: -8, text: (r) => label(r.q), textAnchor: "end", fill: "var(--ink)", fontWeight: 600 }),
      Plot.text(marked.filter((r) => !r.self), { y: "i", frameAnchor: "left", dx: -8, text: (r) => label(r.q), href: (r) => projectPath(r.q), textAnchor: "end", fill: "var(--seq-3)" }),
      ...shape(false),
      ...shape(true),
      ...dateMarks,
    ],
  }, { className: "tl", label: `Construction dates for this project and ${rows.length - 1} other projects on its street segments` });
  return `<h3>Construction on these street segments</h3>
<div class="tl-wrap">${svg}</div>
<p class="small">Construction start and end as each department publishes them; a dot where only one is published.${undated > 0 ? ` ${undated} other project${undated === 1 ? "" : "s"} on these street segments publish${undated === 1 ? "es" : ""} no construction dates.` : ""}</p>`;
}

function detail(p) {
  const ends = p.end ? `, ends ${shortDate(p.end)}` : ", no end date published";
  const timing =
    p.underWay
      ? `Under way${ends}`
      : p.start
        ? `Starts ${p.startText ? esc(p.startText) : shortDate(p.start)}${ends}`
        : `No start date published${ends}`;
  const links = p.links.map((l) => `<a href="${esc(l.url)}">${esc(l.label)}</a>`).join(" · ");
  const reach = reachLine(p);
  const own = ownRecords(p);
  const facts = [
    ["Streets", esc(p.streets.join(", ")) || "None published"],
    // A department page that names no limits for its work: the row holds the
    // whole corridor street, and says so (tools/projects/coordination-projects.py).
    p.placeNote ? ["Extent", esc(p.placeNote)] : null,
    ["Planned bikeway", planLine(p)],
    reach ? ["Would reach", esc(reach)] : null,
    ["Scope", scopeText(p)],
    // Each date shown, linked to the page it was read from, in a grid of
    // public consultation, then construction, by start and end (Bryan,
    // 2026-09-29: "show a grid with one row for Construction, one row for
    // public comment and then columns for start/end"). Each date links to
    // the page it was read from (tools/projects/coordination-projects.py, dateSources).
    (p.dateSources || []).length ? ["Dates", dateGrid(p.dateSources)] : null,
    // Where the sources disagree on a date or a phase, both values, as the
    // pipeline wrote them (tools/projects/coordination-projects.py, dateNotes).
    (p.dateNotes || []).length ? ["Sources disagree", p.dateNotes.map(esc).join("<br>")] : null,
    // Other notes on the dates, each under the label the pipeline gives it
    // (tools/projects/coordination-projects.py, noteGroups): "Not yet checked" for a
    // date read by a model that no person has confirmed.
    ...(p.noteGroups || []).map((g) => [esc(g.label), g.notes.map(esc).join("<br>")]),
    ["Records", links],
  ].filter(Boolean);
  // The map comes first and sits in a fixed box at the top right, so it
  // stays put as a reader steps between projects whose names and findings
  // run to different lengths (Bryan, 2026-09-28: "Can we keep locations
  // more stable?").
  return `<p class="coord-back"><a href="${path}/">← All projects</a></p>
${map(p)}
<h2>${esc(p.name)}</h2>
<p class="plan-chip-line">${planChip(p)}${ratingLine(p)}</p>
<p class="small">${esc([dept(p), KIND[p.kind], p.phase || "phase not published"].filter(Boolean).join(" · "))} · ${timing}</p>
${nextLine(p)}
<p>${finding(p)}</p>
<div class="coord-body">
<dl class="coord-facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
</div>
<h3>City decisions naming this project</h3>
${
  own.length
    ? `<ul class="coord-list-plain">${own.slice(0, 5).map(recordItem).join("")}</ul>${folded(
        `${own.length - 5} earlier`,
        own.slice(5).map(recordItem),
      )}`
    : `<p class="small">None found in ${BODIES_READ} records read through ${esc(D.records.generated)}.</p>`
}
${folded(`${pageRecords(p).length} milestones and events from the project's own page`, pageRecords(p).map(recordItem))}
${folded(`${nearbyRecords(p).length} decisions on the same streets, not naming this project`, nearbyRecords(p).map(recordItem))}
${timeline(p)}
${folded(
  `${p.related.length} other projects on these street segments`,
  p.related.map(
    (r) =>
      `<li>${r.slug || r.url ? `<a href="${esc(r.slug ? `${path}/${r.slug}/` : r.url)}">${esc(r.name)}</a>` : `<b>${esc(r.name)}</b>`}<span class="small">${esc(
        [r.department, r.phase, `${r.sharedBlocks} shared street segment${r.sharedBlocks === 1 ? "" : "s"}`].filter(Boolean).join(" · "),
      )}</span>${r.statusNote ? `<span class="small">${esc(r.statusNote)}</span>` : ""}</li>`,
  ),
)}
${folded(`${p.documents.length} documents on the project page`, p.documents.map((d) => `<li><a href="${esc(d.url)}">${esc(d.title)}</a></li>`))}`;
}

// ---- Assembly ---------------------------------------------------------------

// Four text styles and no more (Bryan, 2026-09-23: "when you use 10 different
// font styles in one page, it becomes a meaningless jumble"): the page title,
// the project name, body text with bold for emphasis, and small muted text
// for dates, owners and labels.
const CSS = `<style>
.wrap:has(.coord) { max-width: 1400px; }
.tl-wrap { overflow-x: auto; }
.tl-wrap .tl { min-width: 560px; margin: 0; }
.tl a:hover text { text-decoration: underline; }
.page-body:has(.coord) > h1 { font-size: 1.9rem; margin-bottom: 4px; }
.coord { display: grid; gap: 24px; margin: 12px 0 24px; }
.coord > * { min-width: 0; }
.coord .small { display: block; font-size: 0.85rem; color: var(--muted); line-height: 1.4; }
.coord-filter { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; }
.coord-filter input, .coord-filter select { font: inherit; font-size: 0.85rem; padding: 6px 8px; border: 1px solid var(--rule); border-radius: 4px; background: var(--paper, #fff); color: inherit; min-width: 0; }
.coord-filter input { flex: 1 1 100%; }
.coord-filter select { flex: 1 1 0; }
.coord-filter .filter-note { flex: 1 1 100%; margin: 0; font-size: 0.75rem; line-height: 1.35; color: var(--muted); }
.coord-rows { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
.coord-rows li { border-bottom: 1px solid var(--rule); border-left: 4px solid transparent; }
/* The row's edge repeats its chip's colour, so the list scans by verdict. */
.coord-rows li[data-plan="all"], .coord-rows li[data-plan="most"] { border-left-color: var(--seq-3); }
.coord-rows li[data-plan="some"] { border-left-color: var(--seq-2); }
.coord-rows li[data-plan="none"] { border-left-color: var(--seq-1); }
.row-plan { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; margin: 3px 0 2px; }
.row-plan .plan-chip { margin: 0; }
.row-mi { font-size: 0.8rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.coord-rows li[hidden] { display: none; }
.coord-rows li.grp { border-left: 0; padding: 14px 10px 6px; background: var(--paper); }
.coord-rows li.grp:first-child { padding-top: 6px; }
.coord-rows li.grp .small { margin: 2px 0 0; }
.grp-head { font-size: 1rem; font-weight: 700; margin: 0; }
.grp-n { font-weight: 400; color: var(--muted); font-variant-numeric: tabular-nums; }
.coord-soon { margin: 0 0 14px; padding: 10px 12px; border: 1px solid var(--seq-3); border-radius: 6px; background: var(--seq-3-soft); }
.coord-soon > p { margin: 4px 0 0; }
.soon-rows { list-style: none; margin: 8px 0 0; padding: 0; max-height: 30vh; overflow-y: auto; }
.soon-rows li { padding: 6px 0; border-top: 1px solid var(--rule); }
.soon-rows .soon-name { display: block; font-weight: 600; }
.soon-rows .soon-what { display: block; font-size: 0.85rem; overflow-wrap: anywhere; }
.next-meeting { padding: 8px 10px; border-left: 4px solid var(--seq-3); background: var(--seq-3-soft); }
.coord-rows a { display: block; padding: 8px 10px; text-decoration: none; color: inherit; }
.coord-rows a:hover { background: var(--raised); }
.coord-rows a[aria-current="true"] { background: var(--raised); box-shadow: inset 3px 0 0 var(--ink); }
.coord-rows b { display: block; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
.plan-chip { display: inline-block; font-size: 0.72rem; font-weight: 600; line-height: 1.5; padding: 0 7px; margin: 3px 0 1px; border-radius: 999px; border: 1px solid var(--rule); color: var(--ink); background: var(--paper); white-space: nowrap; }
.plan-chip.all, .plan-chip.most { background: var(--seq-3-soft); border-color: var(--seq-3); }
.plan-chip.some { background: var(--seq-2-soft); border-color: var(--seq-2); }
.plan-chip.none { background: var(--seq-1-soft); border-color: var(--seq-1); }
.plan-chip.not-stated { border-style: dashed; }
.plan-chip.no-overlap, .plan-chip.already-built { color: var(--muted); }
.coord-detail .plan-chip-line { margin: 2px 0 4px; }
.coord-detail h2 { margin: 0 0 2px; font-size: 1.35rem; overflow-wrap: anywhere; }
.coord-detail > p { margin: 8px 0; }
.coord-detail h3 { font-size: 1rem; font-weight: 700; margin: 20px 0 6px; }
.coord-body { display: grid; gap: 16px; margin: 12px 0 0; }
.coord-facts { display: grid; grid-template-columns: 100px 1fr; gap: 6px 12px; margin: 0; }
.coord-facts dt { font-size: 0.85rem; color: var(--muted); padding-top: 2px; }
.coord-facts dd { margin: 0; overflow-wrap: anywhere; }
.date-grid { border-collapse: collapse; width: auto; font-size: 0.9rem; }
.date-grid th, .date-grid td { text-align: left; vertical-align: top; padding: 2px 18px 6px 0; border-bottom: 0; }
.date-grid thead th { font-weight: 600; font-size: 0.75rem; color: var(--muted); }
.date-grid tbody th { font-weight: 400; font-size: inherit; text-transform: none; letter-spacing: normal; color: inherit; }
.date-grid .np, .date-grid tbody th { white-space: nowrap; }
.date-grid .np { color: var(--muted); }
.coord-map { position: relative; width: 100%; height: 260px; display: block; background: var(--raised); border-radius: 6px; margin: 0 0 12px; overflow: hidden; }
.coord-nomap { display: flex; align-items: center; justify-content: center; text-align: center; padding: 16px; box-sizing: border-box; }
.coord-map .coord-gl { position: absolute; inset: 0; border-radius: 6px; }
.coord-map .maplibregl-ctrl-attrib { font-size: 0.58rem; }
/* The callouts, in the map's frame, over it; the attribution stays clear. */
.coord-map .coord-calls { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; fill: none; stroke-linecap: round; }
.coord-map .lead.none, .coord-map .tip.none { stroke: var(--grey-dark); fill: var(--grey-dark); }
.coord-map .lead.has, .coord-map .tip.has { stroke: var(--seq-3); fill: var(--seq-3); }
.coord-map .lead.needs, .coord-map .tip.needs { stroke: var(--seq-2); fill: var(--seq-2); }
.coord-map .tip { stroke: none; }
.coord-map .call { fill: var(--ink); font-weight: 600; stroke: #fff; stroke-linejoin: round; paint-order: stroke; }
.coord-list-plain { list-style: none; padding: 0; margin: 0; }
.coord-list-plain li { padding: 5px 0; }
.coord-detail details { margin: 12px 0 0; border: 0; border-radius: 0; }
.coord-detail details > summary { padding: 4px 0; color: inherit; font-weight: 700; }
.coord-detail details > summary:hover { background: none; text-decoration: underline; }
.coord-detail details[open] > summary { border-bottom: 0; }
@media (min-width: 960px) {
  .coord { grid-template-columns: 400px minmax(0, 1fr); align-items: start; }
  .coord-list { position: sticky; top: 12px; }
  /* The detail scrolls in its own box, so opening a folded list of
     decisions never changes the page's height or moves the list (Bryan,
     2026-09-29: "Expanding the decisions here shouldn't change the page
     layout of the section on the left"). */
  .coord-detail { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; padding-right: 8px; }
  .coord-rows { max-height: calc(100vh - 300px); min-height: 240px; overflow-y: auto; }
  .coord-detail > .coord-map { float: right; width: 240px; margin: 0 0 12px 20px; }
  .coord-back { display: none; }
}
@media (max-width: 959px) {
  .mode-list .coord-detail { display: none; }
  .mode-project .coord-list { display: none; }
  /* A project page on a phone opens on the project, with the back link in the
     usual top-left place; the title and intro belong to the list page. */
  .page-body:has(.mode-project) > h1, .page-body:has(.mode-project) > .coord-intro { display: none; }
}
</style>`;

// On a wide screen a row swaps the detail in place, and the address follows.
// The fetched page is the same file a phone would open, so there is one
// rendering of every project and nothing to keep in step. The three filters hide
// rows; with no script every row shows.
const SCRIPT = `<script>
(function () {
  var wide = window.matchMedia("(min-width: 960px)");
  var framed = false;
  try { framed = window.self !== window.top; } catch (e) { framed = true; }
  var list = document.querySelector(".coord-rows");
  var detail = document.getElementById("coord-detail");
  if (!list || !detail) return;
  var text = document.querySelector("[data-filter-text]");
  var kind = document.querySelector("[data-filter-kind]");
  var plan = document.querySelector("[data-filter-plan]");
  // The filters survive a page load, so choosing a project that loads its
  // own page keeps the list as the reader left it.
  var KEY = "coord-filters";
  function filter() {
    var q = (text.value || "").toLowerCase().trim(), k = kind.value, pl = plan.value;
    var head = null, shown = 0;
    function close() { if (head) head.hidden = !shown; }
    list.querySelectorAll("li").forEach(function (li) {
      if (li.classList.contains("grp")) { close(); head = li; shown = 0; return; }
      li.hidden = (k && li.dataset.kind !== k) || (pl && (" " + li.dataset.plan + " ").indexOf(" " + pl + " ") < 0) || (q && li.dataset.text.indexOf(q) < 0);
      if (!li.hidden) shown++;
    });
    close();
    try { sessionStorage.setItem(KEY, JSON.stringify({ q: text.value, k: k, pl: pl })); } catch (e) {}
  }
  try {
    var saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
    if (saved) { text.value = saved.q || ""; kind.value = saved.k || ""; plan.value = saved.pl || ""; filter(); }
  } catch (e) {}
  text.addEventListener("input", filter);
  kind.addEventListener("change", filter);
  plan.addEventListener("change", filter);
  function share() {
    var code = document.querySelector("[data-share-url]");
    // The canonical address, whatever prefix this copy is served under.
    var here = document.querySelector('link[rel="canonical"]');
    if (code) code.textContent = here ? here.href : "https://sf-works.org" + location.pathname;
  }
  function select(a, push) {
    fetch(a.getAttribute("href")).then(function (r) { return r.text(); }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, "text/html");
      var nd = doc.getElementById("coord-detail");
      if (!nd) { location.href = a.href; return; }
      // The project's map is drawn again for the new project (COORD_MAP_SCRIPT).
      if (window.sfCoordMaps) sfCoordMaps.remove(detail);
      detail.innerHTML = nd.innerHTML;
      var ns = doc.getElementById("sources"), os = document.getElementById("sources");
      if (ns && os) os.innerHTML = ns.innerHTML;
      if (window.sfCoordMaps) sfCoordMaps(detail);
      document.title = doc.title;
      list.querySelectorAll("a[aria-current]").forEach(function (x) { x.removeAttribute("aria-current"); });
      a.setAttribute("aria-current", "true");
      if (push) history.pushState(null, "", a.getAttribute("href"));
      share();
    });
  }
  list.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[href]") : null;
    // Inside a frame (the review board's), a swap in place would move only
    // the frame's address, and the address bar would keep the old project
    // (Bryan, 2026-09-28: "Choosing a project didn't change the URL"). There
    // the link loads the project's own page, at its registry address.
    if (!a || !wide.matches || framed || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    select(a, true);
  });
  window.addEventListener("popstate", function () {
    var a = list.querySelector('a[href="' + location.pathname + '"]') ||
      (location.pathname.replace(/\\/$/, "").endsWith(${JSON.stringify(path)}) ? list.querySelector("a[href]") : null);
    if (a && wide.matches) select(a, false);
  });
  // Bring the current row into the list's own scroll box, without moving the page.
  var cur = list.querySelector('a[aria-current="true"]');
  if (cur && cur.getBoundingClientRect) {
    var r = cur.getBoundingClientRect(), l = list.getBoundingClientRect();
    if (r.top < l.top || r.bottom > l.bottom) list.scrollTop += r.top - l.top - 8;
  }
})();
</script>`;

function panels(mode, p) {
  return `${CSS}<div class="coord mode-${mode}">
<aside class="coord-list" aria-label="Projects">
${soon()}
${filters()}
<ol class="coord-rows">
${listRows(p.slug)}
</ol>
</aside>
<section class="coord-detail" id="coord-detail" aria-live="polite">
${detail(p)}
</section>
</div>${MAP_HEAD}${COORD_MAP_SCRIPT}${SCRIPT}`;
}

// What this page drew on, exported so About the Data can list it too.
export const SOURCES = [
  {
    label: "Public Works Internal & External Projects (btxj-k9uh) — the interagency coordination feed: each job's owner, phase, dates, streets and scope",
    href: D.feed.url,
    group: "Projects and city records", read: D.feed.queried,
  },
  {
    label: "SFMTA project layer (ArcGIS Multimodal/projects) and each project's page on sfmta.com — phase, project type, scope, geometry, timeline and documents",
    href: "https://www.sfmta.com/projects",
    group: "Projects and city records", read: D.sfmtaLayer.generated,
  },
  {
    backs: "Planned bikeway", label: "SFMTA Biking and Rolling Plan (March 2025) — the North Star network, traced segment by segment, with the facility class each carries",
    href: D.plan.url,
    group: "The Biking and Rolling Plan", read: "2026-09-19",
  },
  {
    backs: "City decisions", label: "SFMTA engineering public hearings — directive orders and decisions naming a street",
    href: "https://www.sfmta.com/past-meetings-and-events/2617",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "SFMTA Board of Directors — agendas and minutes",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=55",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "Board of Supervisors and its committees (Legistar) — every agenda item since 2019",
    href: "https://sfgov.legistar.com/Calendar.aspx",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "SFPUC Commission — every agenda item since 2019, with minutes from 2021",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=22",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "Public Works Commission — every agenda item since its first meeting in 2022",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=218",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "SFCTA Board — every agenda item since 2019, including Prop K and Prop L allocations",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=24",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "City decisions", label: "Recreation and Park Commission — every agenda item since 2019",
    href: "https://sanfrancisco.granicus.com/ViewPublisher.php?view_id=91",
    group: "Projects and city records", read: D.records.generated,
  },
  {
    backs: "Meetings", label: `Posted agendas and events for the next ${U.days} days — SFMTA's meetings and events, Legistar's calendar for the Board of Supervisors and its committees, and the Public Works and SFPUC Commissions' posted agendas; a project has a meeting when a posted agenda item names it, or the event's page and the project's link each other`,
    href: "https://www.sfmta.com/meetings-events",
    group: "Projects and city records", read: U.read,
  },
  {
    backs: "Map and would reach", label: "SFMTA bikeway layer on DataSF (ygmz-vaxd) — which street segments are all-ages today, and segment geometry the plan does not draw",
    href: "https://data.sf.gov/d/ygmz-vaxd",
    group: "The bike network", read: D.reach.networkQueried,
  },
  {
    backs: "Would reach", label: "Census 2020 blocks for San Francisco (p2fw-hsrv) — population and interior point",
    href: "https://data.sf.gov/d/p2fw-hsrv",
    group: "Who it reaches", read: D.reach.sources.blocks.queried,
  },
  {
    backs: "Would reach", label: "California Department of Education public school directory — school locations and open dates",
    href: D.reach.sources.schools.url,
    group: "Who it reaches", read: D.reach.sources.schools.queried,
  },
  {
    backs: "Would reach", label: "DataSF City Facilities (nc68-ngbr) — library branch locations",
    href: "https://data.sf.gov/d/nc68-ngbr",
    group: "Who it reaches", read: D.reach.sources.libraries.queried,
  },
];

function body(mode, p) {
  return content("transportation-projects", {
    listed: C.listed,
    planUrl: PLAN_URL,
    feedQueried: D.feed.queried,
    panels: panels(mode, p),
  });
}

const DESCRIPTION =
  `${C.listed} street projects under way or coming up on San Francisco's ` +
  `Biking and Rolling Plan network, with what the plan draws on each and ` +
  `whether its published scope mentions bikes.`;

export function render() {
  return page({
    title: "Current Repaving Projects",
    description: DESCRIPTION,
    path,
    about: ABOUT_DATA,
    dataUpdated: PROJECTS_DATA_READ,
    // The list page shows the project at the top of the list.
    body: body("list", EARLY[0] || LATER[0]),
    sourcesNote: SOURCES_NOTE,
  });
}

/**
 * One page per project, at /transportation/bike/projects/<slug>/, and one for every
 * address a project has ever had (data/project-ids.json): a redirect where the
 * project continues under another address, a short notice where it has left
 * the city's records. No published address stops answering.
 */
export function pages() {
  const retired = (D.retired || []).map((r) => {
    const to = r.redirect ? `${path}/${r.redirect}/` : null;
    return {
      path: `${path}/${r.slug}/`,
      file: `transportation/bike/projects/${r.slug}/index.html`,
      sitemap: false,
      html: to
        ? redirectPage(to, esc(r.name))
        : page({
            title: `${r.name} · Current Repaving Projects`,
            description: `${r.name} is no longer on the list of current street projects.`,
            path: `${path}/${r.slug}/`,
    about: ABOUT_DATA,
            body: `<section><h1>${esc(r.name)}</h1><p>This project is no longer on the list of current street projects, which is read from SFMTA's project layer and the city's <a href="https://data.sf.gov/d/btxj-k9uh">interagency coordination feed</a>. It may have finished or been withdrawn, or it is work that is not on a street. <a href="${path}/">See the current projects</a>.</p>${
              r.statusNote ? `<p>${esc(r.statusNote)}</p>` : ""
            }</section>`,
          }),
    };
  });
  return retired.concat(P.map((p) => ({
    path: projectPath(p),
    file: `transportation/bike/projects/${p.slug}/index.html`,
    html: page({
      title: `${p.name} · Current Repaving Projects`,
      description: `${p.name}: ${dept(p)}, ${p.phase || "phase not published"}. ${
        p.gap ? "The Biking and Rolling Plan calls for a bikeway its street segments still lack, and the published scope does not mention bike work." : ""
      }`.trim(),
      path: projectPath(p),
    about: ABOUT_DATA,
      dataUpdated: PROJECTS_DATA_READ,
      body: body("project", p),
      sources: SOURCES,
    }),
  })));
}
