// The street safety toolkit as blocks that stand on their own, for the board
// doc's `::sfworks{block="toolkit-table"}` or `::sfworks{block="toolkit-matrix"}`
// line: the tool table, and the options matrix, a Top asks list and two
// cost-against-effect views, with every option's scorecard as a third view
// (see "The options matrix" below). Served at /embed/toolkit/<block>/ (and
// /embed/bike/<block>/) by src/pages/embed-toolkit.mjs.
//
// Bryan, on the comment doc: "Make a chart here like the Vision Zero table with
// columns for cost, effectiveness, and community opposition"; "show which tools
// are in the toolbox for safer trips to school efforts ... And which techniques
// are being considered for broader safe streets initiative"; and "For each
// technique have an info box that shows a picture on a map of a sample place in
// SF to show this is implemented, and cite sources for the key metrics on
// effectiveness, cost and community opposition. Plus explain the evidence more
// clearly for pros and cons for each user type".
//
// So the table reads with no control touched, and a click on a tool opens its
// details in a row right under it, at every width, so nothing ever covers the
// table. The details hold the SF example on an sfMap (src/maplibre.mjs), or the
// nearest example elsewhere when SF has none, each figure's source, and who the
// tool helps and hurts, by how they travel.
//
// Same contract as the school blocks (src/school-hurt-blocks.mjs): one
// self-contained page, CSS, data and script inline, no storage or credentialed
// fetches, and a {type: "sfworks:height", block, height} message to the parent
// whenever the page's height changes, so the frame fits it.
//
// The table's data is site/data/toolkit/tools.json; its `_fields` key is the
// schema. The matrix's is site/data/options/scorecard.json.
// Nothing here hard-codes a figure: every cell is read from that file at build
// time. Street segments are drawn along DataSF's street centerlines
// (site/data/sf-streets.json), routed between the two intersections the data
// names, so the map shows the street and not a straight line across blocks.

import fs from "node:fs";
import nodePath from "node:path";
import { CSS, FONTS, ORIGIN } from "./layout.mjs";
import { MAP_HEAD, inlineJson } from "./maplibre.mjs";
import { Plot, plotSVG } from "./plot.mjs";

const DATA_DIR = nodePath.join(import.meta.dirname, "..", "data");
const KIT = JSON.parse(fs.readFileSync(nodePath.join(DATA_DIR, "toolkit", "tools.json"), "utf8"));
const STREETS = JSON.parse(fs.readFileSync(nodePath.join(DATA_DIR, "sf-streets.json"), "utf8"));

export const TOOLKIT_BLOCKS = ["toolkit-table", "toolkit-matrix"];

// Opposition is ordered, so its three steps are sampled from one blue ramp,
// palest for Low, with the word printed in every cell.
const OPP = {
  Low: { fill: "#dbe4f5", ink: "#15181c" },
  Medium: { fill: "#9db3e3", ink: "#15181c" },
  High: { fill: "#4269d0", ink: "#ffffff" },
  // No SF record to grade: off the ramp, so a white chip with a dashed edge and grey word.
  Untested: { fill: "#ffffff", ink: "#59626f", edge: "1.5px dashed #9aa1ad" },
};
const DOT = "#4269d0";

const GROUPS = [
  ["spot", "Spot fixes at corners, crossings and blocks"],
  ["network", "Network tools SF mostly lacks"],
  ["programs", "Enforcement and programs"],
  ["muni", "Muni service"],
];

// A program column's mark: filled when the tool is in the plan, hollow for a
// pilot, a draft or an urging, and a short grey dash when the plan opposes or
// severely limits the tool. Grey, never red: a limit is a fact about the plan,
// not an alarm. How much SF has built is its own column, as a percent.
const MARK = {
  in: "in the plan",
  considered: "a pilot, a draft or urged",
  limits: "opposed or severely limited",
};
const DASH = "#59626f";
function markSvg(status, size, label, title) {
  const aria = label ? ` role="img" aria-label="${esc(label)}"` : ` aria-hidden="true"`;
  const tt = title ? `<title>${esc(title)}</title>` : "";
  if (status === "limits") return `<svg viewBox="0 0 14 14" width="${size}" height="${size}"${aria}>${tt}<rect x="1.5" y="5.5" width="11" height="3" rx="1" fill="${DASH}"/></svg>`;
  const full = status === "in";
  return `<svg viewBox="0 0 14 14" width="${size}" height="${size}"${aria}>${tt}<circle cx="7" cy="7" r="${full ? 6 : 5.2}" fill="${full ? DOT : "#ffffff"}" stroke="${DOT}" stroke-width="${full ? 0 : 1.6}"/></svg>`;
}

// The three program columns, in the chart's order, with the short heading and
// the one-line definition the key gives (from tools.json's programs_defs).
const PROGRAMS = [
  ["safe_school_connections", "School plan", "SFMTA's Safe School Connections draft, Sept 2026"],
  ["safe_routes", "Safe Routes", "SF Safe Routes to School"],
  ["street_safety_initiative", "Safety Initiative", "the Mayor's Street Safety Initiative"],
];
const BAR = { track: "#dbe4f5", fill: "#4269d0" };

const USERS = [
  ["walking", "Walking"],
  ["biking", "Biking"],
  ["transit", "Muni"],
  ["driving", "Driving"],
  ["kids_school_trip", "Kids on the school trip"],
];

const DESIGN = {
  controlled: ["controlled study", "compared with similar places that didn't change"],
  "before-after": ["before-after study", "counted before and after, with no comparison places"],
  "meta-analysis": ["meta-analysis", "pools many studies"],
  "cross-sectional": ["cross-sectional study", "compared streets with and without the tool at one point in time"],
  "not stated": ["study of unstated design", "the source doesn't say how it was measured"],
  "cross-section": ["cross-sectional study", "compared places with and without the tool at one point in time"],
  "before-after with citywide comparison": ["before-after study", "counted before and after, against the citywide change"],
  model: ["our model", "estimated from mode shift and injury risk per passenger mile, not measured"],
  "case-control": ["case-control study", "compared children who were hit with children who weren't"],
};

// The row's short study label, in words a parent reads without a glossary.
const ROW_DESIGN = { controlled: "vs. similar streets", "before-after": "before and after", "meta-analysis": "many studies", "cross-sectional": "streets compared", "cross-section": "streets compared", "not stated": "design not stated", "before-after with citywide comparison": "before and after", model: "our model", "case-control": "case-control" };

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// A provenance tag is for us; the reader gets the part that changes how much
// to trust the line. Opened primary sources need no note; the rest say so.
function untag(s) {
  return String(s ?? "")
    .replace(/\s*\[(primary|repo note|DataSF|Legistar|settled)[^\]]*\]/g, "")
    .replace(/\s*\[inference[^\]]*\]/g, " (our judgement)")
    .replace(/\s*\[secondary[^\]]*\]/g, " (secondary source)")
    .replace(/\s*\[web search[^\]]*\]/g, " (web search, not yet checked)")
    .replace(/\s*\[unretrieved[^\]]*\]/g, " (source not yet opened)")
    // Feet and miles only on the site. A risk ratio "per km" is the same ratio per mile.
    .replace(/\b(per|passenger) km\b/g, "$1 mile")
    .trim();
}
// A minus sign and an en dash for ranges, as the chart prints them.
const num = (s) => String(s ?? "").replace(/(^|[\s(])-(?=\d)/g, "$1−").replace(/(\d[KM%]?)-(\$?\d)/g, "$1–$2");
const link = (url, text) => (url ? `<a href="${esc(url)}">${esc(text)}</a>` : esc(text));

// ---- Street segments along the centerlines ----------------------------------

const KEY = (p) => `${p[0].toFixed(5)},${p[1].toFixed(5)}`;
const FT_LAT = 364000, FT_LON = 364000 * Math.cos((37.76 * Math.PI) / 180);
const ft = (a, b) => Math.hypot((a[0] - b[0]) * FT_LON, (a[1] - b[1]) * FT_LAT);

let graph = null;
/** The centerlines as a graph: a node per line end, an edge per line, weighted by its length in feet. */
function streetGraph() {
  if (graph) return graph;
  const adj = new Map(), nodes = new Map();
  for (const line of STREETS.lines) {
    if (line.length < 2) continue;
    const a = KEY(line[0]), b = KEY(line[line.length - 1]);
    let len = 0;
    for (let i = 1; i < line.length; i++) len += ft(line[i - 1], line[i]);
    nodes.set(a, line[0]); nodes.set(b, line[line.length - 1]);
    if (!adj.has(a)) adj.set(a, []);
    if (!adj.has(b)) adj.set(b, []);
    adj.get(a).push({ to: b, len, line });
    adj.get(b).push({ to: a, len, line: [...line].reverse() });
  }
  return (graph = { adj, nodes });
}

function nearestNode(p) {
  let best = null, d = Infinity;
  for (const [k, q] of streetGraph().nodes) {
    const e = ft(p, q);
    if (e < d) { d = e; best = k; }
  }
  return { key: best, ft: d };
}

/** The shortest path along the centerlines between two [lon, lat] points, or null when it strays from the straight line. */
function routeAlong(from, to) {
  const { adj, nodes } = streetGraph();
  const a = nearestNode(from), b = nearestNode(to);
  if (a.ft > 150 || b.ft > 150) return null;
  const dist = new Map([[a.key, 0]]), prev = new Map(), done = new Set();
  const queue = [[0, a.key]];
  while (queue.length) {
    queue.sort((x, y) => x[0] - y[0]);
    const [d, k] = queue.shift();
    if (done.has(k)) continue;
    done.add(k);
    if (k === b.key) break;
    for (const e of adj.get(k) || []) {
      const nd = d + e.len;
      if (nd < (dist.get(e.to) ?? Infinity)) { dist.set(e.to, nd); prev.set(e.to, { from: k, line: e.line }); queue.push([nd, e.to]); }
    }
  }
  if (!prev.has(b.key) && a.key !== b.key) return null;
  const parts = [];
  for (let k = b.key; k !== a.key; k = prev.get(k).from) parts.unshift(prev.get(k).line);
  const path = parts.flatMap((l, i) => (i ? l.slice(1) : l));
  // A route much longer than the crow flies has left the street the data names.
  const straight = ft(nodes.get(a.key), nodes.get(b.key));
  return dist.get(b.key) <= straight * 1.35 + 200 ? path : null;
}

/** An SF example as map data: its point, and its street when the data names a segment's two ends. */
function exampleGeo(ex) {
  const pt = [ex.lon, ex.lat];
  const ends = [...String(ex.geometry_hint || "").matchAll(/\((-?\d+\.\d+),\s*(-?\d+\.\d+)\)/g)].map((m) => [Number(m[2]), Number(m[1])]);
  let line = null;
  if (/street segment/.test(ex.geometry_hint || "") && ends.length === 2) line = routeAlong(ends[0], ends[1]);
  const all = line ? [...line, pt] : [pt];
  const lons = all.map((p) => p[0]), lats = all.map((p) => p[1]);
  // At least about 1,000 ft across, so a single corner shows its blocks.
  const padLat = Math.max(0.0014, (Math.max(...lats) - Math.min(...lats)) * 0.12), padLon = Math.max(0.0018, (Math.max(...lons) - Math.min(...lons)) * 0.12);
  const bounds = [[Math.min(...lons) - padLon, Math.min(...lats) - padLat], [Math.max(...lons) + padLon, Math.max(...lats) + padLat]];
  const r5 = (p) => [+p[0].toFixed(5), +p[1].toFixed(5)];
  return { pt: r5(pt), line: line ? line.map(r5) : null, bounds: bounds.map(r5) };
}

// ---- The table --------------------------------------------------------------

function dotCell(t, key, label) {
  const p = t.programs?.[key];
  if (!p) return `<td class="tk-p"><span class="sr">${esc(label)}: no</span></td>`;
  const what = MARK[p.status];
  if (!what) throw new Error(`toolkit: ${t.id} ${key} has status "${p.status}"`);
  if (p.status === "limits" && !p.quote) throw new Error(`toolkit: ${t.id} ${key} is "limits" with no quoted text`);
  return `<td class="tk-p">${markSvg(p.status, 14, `${label}: ${what}`, `${label}: ${untag(p.note) || what}`)}</td>`;
}

// The cost cell: the band for making the tool work across a typical SF square mile.
function perSqMi(t) {
  const q = t.cost?.per_sq_mi;
  if (!q || !q.band) throw new Error(`toolkit: ${t.id} has no cost.per_sq_mi.band`);
  if (!(q.band in KIT._bands.cutoffs) && q.band !== "revenue" && q.band !== "unknown") throw new Error(`toolkit: ${t.id} has band "${q.band}"`);
  return q;
}
const usd = (v) => (v == null ? "" : v >= 1e6 ? `$${(v / 1e6).toFixed(1).replace(/\.0$/, "")}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v)}`);
const range = (lo, hi) => (lo == null ? "" : hi != null && Math.round(hi / 1e3) !== Math.round(lo / 1e3) ? `${usd(lo)}–${usd(hi)}` : usd(lo));
/** [main, sub] for the cost cell. */
function bandText(q) {
  const yr = q.per_year ? " a year" : "";
  if (q.band === "revenue") return ["Raises money", q.total_low != null ? `${range(q.total_low, q.total_high)} net${yr}` : ""];
  if (q.band === "unknown") return ["Not found", ""];
  return [q.band, q.total_low != null ? `${range(q.total_low, q.total_high)}${yr}${q.net ? ` gross; ${q.net}` : ""}` : ""];
}

/** [main, sub] for the effect cell: the change across a square mile, with the study's own figure under it. */
function effectText(e) {
  const a = e.area;
  if (a?.pct != null) {
    // One decimal, as the working prints it, so the cell and the arithmetic under it agree (1.5% stays 1.5%).
    const v = a.pct.toFixed(Math.abs(a.pct) < 1 ? 2 : 1).replace(/\.0$/, "");
    return [esc(`${num(a.pct > 0 ? "+" + v : v)}% injuries`), a.sub || `study: ${num(e.short)}`];
  }
  if (a?.cell) return [esc(num(a.cell)), a.sub || ""];
  // No square-mile figure: the study's own line on a wide screen, two words on a phone.
  return [`<span class="tk-wide">${esc(num(e.short))}</span><span class="tk-narrow">No figure</span>`, e.pct == null ? "" : [e.where, ROW_DESIGN[e.design]].filter(Boolean).join(", ")];
}

/** The Built cell: the share of the city's places that have the tool, printed, over a light bar. */
function builtCell(t) {
  const c = t.coverage;
  if (!c || !c.label) throw new Error(`toolkit: ${t.id} has no coverage label`);
  const w = c.pct == null ? 0 : Math.max(c.pct > 0 ? 2 : 0, Math.min(100, c.pct));
  const bar = c.pct == null ? "" : `<span class="tk-bar" aria-hidden="true"><span style="width:${w}%"></span></span>`;
  // A legal block shows at every width: the full words on a wide screen, two on a phone.
  const cap = t.legal ? `<span class="tk-law"><span class="tk-wide">${esc(t.legal.cell || "capped by state law")}</span><span class="tk-narrow">state cap</span></span>` : "";
  return `<td class="tk-cov${c.pct == null ? " tk-nocount" : ""}" title="${esc(untag(c.text))}"><span class="tk-pct">${esc(c.label)}</span>${bar}${cap}</td>`;
}

function row(t) {
  const e = t.effect, o = t.opposition, c = OPP[o.grade];
  if (!c) throw new Error(`toolkit: ${t.id} has opposition grade "${o.grade}"`);
  const name = t.short_name || t.name;
  const [emain, sub] = effectText(e);
  const [bmain, bsub] = bandText(perSqMi(t));
  const cost = bsub ? `${bmain}, ${bsub}` : bmain;
  return `<tr class="tk-row" id="row-${esc(t.id)}" data-id="${esc(t.id)}">
<th scope="row" class="tk-tool"><button type="button" aria-expanded="false" aria-controls="more-${esc(t.id)}"><span class="tk-chev" aria-hidden="true"></span><span class="tk-name">${esc(name)}</span><span class="tk-cost-n">${esc(cost)}</span></button></th>
<td class="tk-cost"><span class="tk-main tk-band">${esc(bmain)}</span>${bsub ? `<span class="tk-sub">${esc(bsub)}</span>` : ""}</td>
<td class="tk-eff"><span class="tk-main">${emain}</span>${sub ? `<span class="tk-sub">${esc(sub)}</span>` : ""}</td>
<td class="tk-opp"><span class="tk-chip" style="background:${c.fill};color:${c.ink}${c.edge ? `;border:${c.edge}` : ""}">${esc(o.grade)}</span></td>
${builtCell(t)}
${PROGRAMS.map(([k, label]) => dotCell(t, k, label)).join("")}
</tr>`;
}

// ---- The details under a row -------------------------------------------------

function example(t) {
  const ex = t.sf_example;
  if (ex) {
    const cap = `${link(ex.source_url, ex.name)}${ex.year ? `, ${esc(ex.year)}` : ""}`;
    // Where SF has only a partial version, the full one elsewhere sits under it.
    const n = t.nearest_example;
    const abroad = n ? `<p class="tk-cap"><b>The full version:</b> ${link(n.url, n.name)}, ${esc(n.city)}.${[1, 2, 3].map((i) => { const k = i === 1 ? "" : i; const u = n[`rules${k}_url`]; return u ? ` ${link(u, n[`rules${k}_title`])}.` : ""; }).join("")}</p>` : "";
    // A citywide program has no one place to map.
    if (ex.lat == null || ex.lon == null) return `<p class="tk-cap tk-none"><b>In SF:</b> ${cap}.</p>${abroad}`;
    return `<div class="tk-map" data-geo="${esc(JSON.stringify(exampleGeo(ex)))}"></div>
<p class="tk-cap"><b>In SF:</b> ${cap}</p>${abroad}`;
  }
  const n = t.nearest_example;
  if (!n) throw new Error(`toolkit: ${t.id} has neither sf_example nor nearest_example`);
  return `<p class="tk-cap tk-none"><b>No SF example yet.</b> Nearest: ${link(n.url, n.name)}, ${esc(n.city)}.</p>`;
}

function users(t) {
  let blank = false;
  const rows = USERS.map(([k, label]) => {
    const u = t.by_user?.[k] || {};
    const note = untag(u.evidence_note).replace(/^\(our judgement\)$/, "");
    let ev;
    if (u.evidence_url && u.evidence_url === t.effect.source_url) ev = `Same study as the effect above`;
    else if (u.evidence_url) ev = link(u.evidence_url, note || "Source");
    else if (note && !/^no .*stud/i.test(note)) ev = esc(note);
    else { ev = ""; blank = true; }
    return `<tr><th scope="row">${esc(label)}</th><td data-h="Helps">${esc(untag(u.pros) || "None measured.")}</td><td data-h="Hurts">${esc(untag(u.cons) || "None measured.")}</td>${ev ? `<td class="tk-ev" data-h="Evidence">${ev}</td>` : `<td class="tk-ev tk-ev-none"></td>`}</tr>`;
  }).join("");
  return `<table class="tk-users">
<thead><tr><th scope="col">Who</th><th scope="col">Helps</th><th scope="col">Hurts</th><th scope="col">Evidence</th></tr></thead>
<tbody>${rows}</tbody>
</table>${blank ? `<p class="tk-note">No evidence listed: we found no study, so that line is our judgement.</p>` : ""}`;
}

/** The working behind the cost band: where the tool goes in a typical square mile, its unit cost, and
 * quantity × unit cost = total, which tools_over.py writes from the numbers and checks against the total. */
function costWorking(t) {
  const q = perSqMi(t);
  if (!q.working) throw new Error(`toolkit: ${t.id} has no cost working`);
  const srcs = (q.sources || []).filter((s) => s.url).map((s) => link(s.url, untag(s.title) || "Source")).join(", ");
  const where = `${esc(untag(q.quantity_text))}.${q.unit_cost ? ` Unit cost: ${esc(untag(q.unit_cost))}.` : ""}`;
  return `${where} <span class="tk-math"><b>The arithmetic:</b> ${esc(num(q.working))}</span>${q.assumptions ? ` ${esc(untag(q.assumptions))}` : ""}${srcs ? ` <span class="tk-src">Sources: ${srcs}</span>` : ""}`;
}

/** The working behind the effect cell: what the study found, then its effect × the share of crashes where the
 * tool goes × the share of those places treated, as tools_over.py writes it from the numbers. */
function effectWorking(t) {
  const a = t.effect.area;
  if (!a || !a.working) throw new Error(`toolkit: ${t.id} has no effect working`);
  return `${esc(num(untag(a.note || "")))} <span class="tk-math"><b>The arithmetic:</b> ${esc(num(untag(a.working)))}</span>`;
}

/** The plans that oppose or severely limit the tool, each in its own words. */
function limitsBox(t) {
  const ps = PROGRAMS.map(([k, label]) => [label, t.programs?.[k]]).filter(([, p]) => p && p.status === "limits");
  if (!ps.length) return "";
  return `<div><dt>Where a plan limits it</dt><dd>${ps.map(([label, p]) => `${esc(label)}: “${esc(p.quote)}” ${link(p.source_url, "Source")}`).join("<br>")}</dd></div>`;
}

function more(t, cols) {
  const e = t.effect, o = t.opposition, d = DESIGN[e.design];
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return "source"; } };
  const exs = (o.examples || []).filter((x) => x.url).map((x) => `<a href="${esc(x.url)}" title="${esc(untag(x.text))}">${esc(host(x.url))}</a>`).join(", ");
  return `<tr class="tk-more" id="more-${esc(t.id)}" hidden><td colspan="${cols}">
<div class="tk-box">
<p class="tk-one">${esc(t.one_line)}</p>
<div class="tk-grid">
<div class="tk-where">${example(t)}</div>
<dl class="tk-facts">
<div><dt>Cost for a typical square mile</dt><dd>${costWorking(t)}</dd></div>
<div><dt>Effect across a typical square mile</dt><dd>${effectWorking(t)}</dd></div>
<div><dt>Built today: ${esc(t.coverage.label)}</dt><dd>${esc(untag(t.coverage.text))}${t.coverage.url ? ` <span class="tk-src">${link(t.coverage.url, "Source")}</span>` : ""}</dd></div>
${t.legal ? `<div><dt>State law</dt><dd>${esc(untag(t.legal.text))} <span class="tk-src">${t.legal.sources.map((s) => link(s.url, s.title)).join("; ")}</span></dd></div>` : ""}
${limitsBox(t)}
<div><dt>How the study measured it</dt><dd>${d && e.pct != null ? `${d[1][0].toUpperCase() + d[1].slice(1)}${e.where ? `, ${esc(e.where)}` : ""}. ` : ""}${link(e.source_url, untag(e.source_title) || "Source")}</dd></div>
<div><dt>Why that opposition grade</dt><dd>${esc(untag(o.reason))}${exs ? ` <span class="tk-src">Sources: ${exs}</span>` : ""}</dd></div>
</dl>
</div>
${users(t)}
</div>
</td></tr>`;
}

// ---- The page ---------------------------------------------------------------

/** The most-cited source address for each program column, for the key's links. */
function programLinks() {
  const out = {};
  for (const [k] of PROGRAMS) {
    const n = {};
    for (const t of KIT.tools) { const u = t.programs?.[k]?.source_url; if (u) n[u] = (n[u] || 0) + 1; }
    out[k] = Object.entries(n).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] || null;
  }
  return out;
}

const TABLE_TITLE = "What each street safety tool costs, what it does, and how hard it is to win in San Francisco";

function tableBlock() {
  return page("toolkit-table", TABLE_TITLE, tableBody(), SCRIPT, { head: MAP_HEAD, css: TK_CSS });
}

/** The table's figure body, shared by the table block and the matrix block's collapsed details. */
function tableBody() {
  const title = TABLE_TITLE;
  const cols = 5 + PROGRAMS.length;
  const ids = new Set();
  for (const t of KIT.tools) {
    if (ids.has(t.id)) throw new Error(`toolkit: duplicate id ${t.id}`);
    ids.add(t.id);
    if (!GROUPS.some(([g]) => g === t.group)) throw new Error(`toolkit: ${t.id} has group "${t.group}"`);
  }
  const body = GROUPS.map(([g, label]) => `<tbody>
<tr class="tk-grp"><th scope="rowgroup" colspan="${cols}">${esc(label)}</th></tr>
${KIT.tools.filter((t) => t.group === g).map((t) => row(t) + "\n" + more(t, cols)).join("\n")}
</tbody>`).join("\n");
  const pl = programLinks();
  const key = PROGRAMS.map(([k, label, def]) => `<b>${esc(label)}</b>: ${link(pl[k], def)}`).join(". ");
  const B = KIT._bands, sq = KIT._square_mile;
  const cut = Object.entries(B.cutoffs).map(([b, c]) => `<b>${esc(b)}</b> ${esc(c.label)}`).join(", ");
  return `<h2>${esc(title)}</h2>
<p class="tk-hint">Tap a tool to see where SF has it, the sources, and who it helps.</p>
<p class="tk-key">Cost and effect are for building the tool everywhere it fits in a typical SF square mile. Cost: ${cut}. ${esc(B.note)} Effect: the change in all injury crashes across that square mile, scaled from the study's own figure, which sits under it.</p>
<p class="tk-key">${markSvg("in", 11)} in the plan &nbsp; ${markSvg("considered", 11)} a pilot, a draft or urged &nbsp; ${markSvg("limits", 11)} the plan opposes or severely limits it &nbsp; blank: absent.</p>
<table class="tk">
<colgroup><col class="c-tool"><col class="c-cost"><col class="c-eff"><col class="c-opp"><col class="c-cov">${PROGRAMS.map(() => `<col class="c-p">`).join("")}</colgroup>
<thead><tr>
<th scope="col" class="tk-tool"><span class="tk-wide">Tool</span><span class="tk-narrow">Tool and cost</span></th>
<th scope="col" class="tk-cost">Cost a square mile</th>
<th scope="col" class="tk-eff"><span class="tk-wide">Effect a square mile</span><span class="tk-narrow">Effect</span></th>
<th scope="col" class="tk-opp"><span class="tk-wide">Opposition in SF</span><span class="tk-narrow">Opposition</span></th>
<th scope="col" class="tk-cov">Built today</th>
${PROGRAMS.map(([, label]) => `<th scope="col" class="tk-p"><span>${esc(label)}</span></th>`).join("")}
</tr></thead>
${body}
</table>
<p class="tk-key">${key}. ${esc(KIT._coverage_rule)}</p>
<p class="tk-key">A typical square mile: ${esc(sq.text)} ${KIT._square_mile.sources.map((s) => link(s.url, s.title)).join(", ")}. ${esc(KIT._shares_note.replace(/^Effect is/, "The effect is"))} ${link("https://data.sfgov.org/d/ubvf-ztfx", "DataSF crashes")}.</p>
<p class="tk-key">Tools from ${KIT._lists.map((s) => link(s.url, s.title)).join(", ")}, with duplicates merged. ${esc(KIT._skipped)} Sources read ${esc(KIT._read)}.</p>`;
}

const SCRIPT = `<script>
(function () {
  var open = null, map = null;
  function close() {
    if (!open) return;
    open.row.classList.remove("on");
    open.row.querySelector("button").setAttribute("aria-expanded", "false");
    open.more.hidden = true;
    if (map) { map.remove(); map = null; }
    open = null;
  }
  function draw(el) {
    if (!el || !window.sfMap) return;
    var g = JSON.parse(el.getAttribute("data-geo"));
    map = sfMap.create(el, { bounds: g.bounds, padding: function () { return 12; }, maxZoom: 18 });
    if (!map) return;
    var m = map;
    m.on("load", function () {
      var u = sfMap.under(m);
      if (g.line) {
        m.addSource("seg", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: g.line } } });
        m.addLayer({ id: "seg-halo", type: "line", source: "seg", paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.8 }, layout: { "line-cap": "round", "line-join": "round" } }, u);
        m.addLayer({ id: "seg", type: "line", source: "seg", paint: { "line-color": "${DOT}", "line-width": 5 }, layout: { "line-cap": "round", "line-join": "round" } }, u);
      } else {
        m.addSource("pt", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: g.pt } } });
        m.addLayer({ id: "pt", type: "circle", source: "pt", paint: { "circle-color": "${DOT}", "circle-radius": 8, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 } });
      }
    });
  }
  function toggle(row) {
    var was = open && open.row === row;
    close();
    if (was) return;
    var more = document.getElementById("more-" + row.getAttribute("data-id"));
    row.classList.add("on");
    row.querySelector("button").setAttribute("aria-expanded", "true");
    more.hidden = false;
    open = { row: row, more: more };
    draw(more.querySelector(".tk-map"));
  }
  document.querySelectorAll(".tk-row").forEach(function (row) {
    row.addEventListener("click", function (e) {
      if (e.target.closest("a")) return;
      toggle(row);
    });
  });
  var h = decodeURIComponent(location.hash.slice(1));
  var start = h && document.getElementById("row-" + h);
  if (start) toggle(start);
})();
</script>`;

const TK_CSS = `
html, body { background: #ffffff; margin: 0; }
body { padding: 4px 12px 8px; }
.tkb { margin: 0; max-width: 1080px; font-size: 0.9rem; color: var(--ink); }
.tkb h2 { font-family: Archivo, sans-serif; font-size: 1.15rem; line-height: 1.3; margin: 0 0 4px; text-wrap: pretty; max-width: 48em; }
/* The site's tables print column labels in small caps; this one reads as a chart, so its labels stay in plain bold. */
:where(.tkb) th, :where(.tkb) td { text-transform: none; letter-spacing: 0; font-size: inherit; color: var(--ink); font-weight: 400; border-bottom: 0; padding: 0; }
:where(.tkb) th { font-weight: 700; }
.tkb a { color: inherit; text-decoration-color: #9aa1ad; text-underline-offset: 2px; }
.tkb a:hover { text-decoration-color: currentColor; }
.tk-hint { margin: 0 0 10px; color: var(--muted); font-size: 0.86rem; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.tk { width: 100%; border-collapse: collapse; table-layout: fixed; }
.tk col.c-tool { width: 21%; } .tk col.c-cost { width: 16%; } .tk col.c-eff { width: 18%; } .tk col.c-opp { width: 11%; } .tk col.c-cov { width: 13%; } .tk col.c-p { width: 7%; }
.tk-cov { text-align: left; }
.tk-pct { display: block; font-weight: 700; font-variant-numeric: tabular-nums; }
.tk-nocount .tk-pct { font-weight: 400; color: var(--muted); font-size: 0.8rem; }
.tk-law { display: block; color: var(--muted); font-size: 0.8rem; margin-top: 2px; line-height: 1.2; }
.tk-bar { display: block; height: 6px; margin-top: 3px; background: ${BAR.track}; border-radius: 3px; overflow: hidden; }
.tk-bar > span { display: block; height: 100%; background: ${BAR.fill}; }
.tk thead th { font-weight: 700; text-align: left; vertical-align: bottom; padding: 0 8px 6px; border-bottom: 1.5px solid #9aa1ad; line-height: 1.2; }
.tk thead th.tk-p, .tk thead th.tk-opp { text-align: center; }
.tk thead th.tk-p { font-size: 0.82rem; }
.tk-narrow, .tk-cost-n { display: none; }
.tk-grp th { text-align: left; color: ${DOT}; font-weight: 700; padding: 14px 8px 4px; font-size: 0.95rem; }
.tk-row > * { padding: 6px 8px; border-bottom: 1px solid #e3e6ea; vertical-align: middle; }
.tk-row { cursor: pointer; }
.tk-row:hover > *, .tk-row.on > * { background: #f4f6f8; }
.tk-row.on > * { border-bottom-color: transparent; }
.tk-tool { text-align: left; }
.tk-tool button { all: unset; cursor: pointer; display: grid; grid-template-columns: auto 1fr; column-gap: 8px; align-items: center; width: 100%; font-weight: 700; line-height: 1.25; }
.tk-tool button:focus-visible { outline: 2px solid ${DOT}; outline-offset: 2px; border-radius: 2px; }
.tk-name { grid-column: 2; hyphens: auto; overflow-wrap: break-word; min-width: 0; }
.tk-row { line-height: 1.3; }
.tk-chev { grid-column: 1; grid-row: 1; align-self: center; width: 7px; height: 7px; border-right: 2px solid #6b7380; border-bottom: 2px solid #6b7380; transform: rotate(-45deg); margin-left: -2px; transition: transform 0.15s; }
.tk-row.on .tk-chev { transform: rotate(45deg); }
.tk-eff .tk-main, .tk-cost .tk-main { display: block; }
.tk-band { font-weight: 700; letter-spacing: 0.04em; }
.tk-sub { display: block; color: var(--muted); font-size: 0.8rem; }
.tk-opp { text-align: center; }
.tk-chip { display: block; padding: 7px 4px; border-radius: 4px; font-weight: 700; font-size: 0.86rem; text-align: center; }
.tk-p { text-align: center; }
.tk-p svg { display: inline-block; vertical-align: middle; }
.tk-more > td { padding: 0 8px 14px; background: #f4f6f8; border-bottom: 1px solid #e3e6ea; }
.tk-box { padding-top: 2px; }
.tk-one { margin: 0 0 10px; font-size: 0.95rem; max-width: 60em; }
.tk-grid { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 16px; align-items: start; }
.tk-map { height: 230px; border: 1px solid var(--rule); border-radius: 4px; }
.tk-cap { margin: 5px 0 0; font-size: 0.82rem; color: var(--muted); }
.tk-cap b { color: var(--ink); }
.tk-none { margin: 0; padding: 10px 12px; background: #ffffff; border: 1px solid var(--rule); border-radius: 4px; font-size: 0.86rem; }
.tk-facts { margin: 0; display: grid; gap: 8px; }
.tk-facts dt { font-weight: 700; font-size: 0.82rem; }
.tk-facts dd { margin: 0; font-size: 0.86rem; line-height: 1.4; }
.tk-facts dd > a, .tk-facts li a { color: var(--muted); }
.tk-facts ul { margin: 3px 0 0; padding-left: 1.1em; }
.tk-facts li { margin: 1px 0; }
.tk-users { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.84rem; line-height: 1.35; table-layout: fixed; }
.tk-users th, .tk-users td { text-align: left; vertical-align: top; padding: 5px 8px 5px 0; border-top: 1px solid #e3e6ea; }
.tk-users thead th { border-top: 0; font-size: 0.78rem; color: var(--muted); font-weight: 700; padding-bottom: 2px; }
.tk-users thead th:first-child { width: 14%; } .tk-users thead th:nth-child(2), .tk-users thead th:nth-child(3) { width: 29%; }
.tk-users tbody th { font-weight: 700; }
.tk-ev { color: var(--muted); }
.tk-note { margin: 4px 0 0; font-size: 0.78rem; color: var(--muted); }
.tk-src { color: var(--muted); }
.tk-math { display: block; margin-top: 4px; }
.tk-src a { color: var(--muted); }
.tk-hint + .tk-key { margin: -4px 0 10px; }
.tk-ev a { color: var(--muted); }
.tk-key { margin: 8px 0 0; font-size: 0.78rem; line-height: 1.45; color: var(--muted); }
.tk-key svg { vertical-align: -1px; }
.tk-key + .tk-key { margin-top: 2px; }
@media (max-width: 760px) {
  .tkb { font-size: 0.84rem; }
  .tk col.c-tool { width: 30%; } .tk col.c-cost { width: 0; } .tk col.c-eff { width: 22%; } .tk col.c-opp { width: 17%; } .tk col.c-cov { width: 14%; } .tk col.c-p { width: 5.6%; }
  .tk-pct { font-size: 0.78rem; } .tk-nocount .tk-pct { font-size: 0.7rem; } .tk-law { font-size: 0.7rem; }
  .tk-bar { height: 4px; }
  .tk thead th.tk-opp { font-size: 0.72rem; }
  .tk .tk-cost { width: 0; padding: 0; font-size: 0; overflow: hidden; }
  .tk-wide { display: none; } .tk-narrow { display: inline; }
  .tk-cost-n { display: block; grid-column: 2; font-weight: 400; color: var(--muted); font-size: 0.78rem; margin-top: 1px; }
  .tk-chev { width: 6px; height: 6px; }
  .tk thead th { padding: 0 4px 6px; font-size: 0.8rem; }
  .tk thead th.tk-p { height: 92px; padding: 0 0 6px; }
  .tk thead th.tk-p span { display: inline-block; writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; font-size: 0.74rem; }
  .tk-row > * { padding: 6px 4px; }
  .tk-row > .tk-p { padding: 6px 0; }
  .tk-p svg { width: 11px; height: 11px; }
  .tk-chip { padding: 6px 2px; font-size: 0.74rem; }
  .tk-sub { display: none; }
  .tk-grp th { padding: 12px 4px 4px; font-size: 0.88rem; }
  .tk-more > td { padding: 0 8px 12px; }
  .tk-grid { grid-template-columns: 1fr; gap: 10px; }
  .tk-map { height: 190px; }
  .tk-users thead { display: none; }
  .tk-users, .tk-users tbody, .tk-users tr, .tk-users th, .tk-users td { display: block; width: auto; }
  .tk-users tr { border-top: 1px solid #e3e6ea; padding: 6px 0; }
  .tk-users th, .tk-users td { border: 0; padding: 1px 0; }
  .tk-users td::before { content: attr(data-h) ": "; font-weight: 700; color: var(--ink); }
  .tk-users td.tk-ev-none { display: none; }
  .tk-users td.tk-ev::before { font-weight: 400; color: var(--muted); }
}
`;

// ---- The options matrix ------------------------------------------------------
//
// Bryan, on the toolkit-matrix chart in his driving doc, 2026-11-05: "Can you
// please give us two views of this visualization, updated to match the latest
// research. Give us one view that's mode shift citywide vs. cost. And another
// one that's fewer injuries per square mile vs. cost." Then, the same day: a
// ranked "Top asks" list above the chart, "Ranked by VMT reduction per dollar
// (since that's what city cares about now). Highlight things that nobody is
// asking for." (docs/decisions/school-trips.md, 2026-11-05). Status, asks,
// opposition and money stay in the details table, never on the chart.
//
// So: one block, a switch that opens on miles cut, the list's own measure (Bryan
// ranks against convenience first, and injuries are never the default ranking),
// then mode shift, injuries and every figure as a table. Cost a year on a log x
// axis, and each change's figure on y with its low to high range. Every point is grey except the changes nobody is asking for, which get
// a hollow ring in observable10's first colour, the chart's one highlight.
//
// Every figure is read from site/data/options/scorecard.json, the site copy of
// data/options/scorecard.json (tools/toolkit/build-scorecard-site.py). A change with
// no figure for a view is left off it and counted under the chart.

const SC = JSON.parse(fs.readFileSync(nodePath.join(DATA_DIR, "options", "scorecard.json"), "utf8"));
const RING = "#4269d0"; // observable10's first colour: the one highlight
const GREY = "#9aa1ad";
const SPREAD_YEARS = SC._cost_basis.spread_years;

const sig2 = (v) => {
  if (v === 0) return "0";
  const a = Math.abs(v);
  const s = a >= 100 ? Math.round(+a.toPrecision(2)).toLocaleString("en-US") : String(+a.toPrecision(2));
  return (v < 0 ? "−" : "") + s;
};
const money = (v) => (v >= 1e9 ? `$${sig2(v / 1e9)}B` : v >= 1e6 ? `$${sig2(v / 1e6)}M` : v >= 1e3 ? `$${sig2(v / 1e3)}K` : `$${sig2(v)}`);
const geo = (lo, hi) => (lo > 0 && hi > 0 ? Math.sqrt(lo * hi) : (lo + hi) / 2);

/** Cost a year: running cost plus build cost spread over SPREAD_YEARS, low and high. Null when the research priced neither. */
function yearCost(o) {
  const c = o.cost || {};
  // A yearly cost that already pays off the build cost (a cordon's equipment, a repaint cycle) isn't added to again.
  const one = c.yearly_includes_one_time && c.yearly ? null : c.one_time, yr = c.yearly;
  if (!one && !yr) return null;
  // A trial or pilot that ends in a year counts its whole cost in that year.
  const spread = c.spread_years ?? SPREAD_YEARS;
  const lo = (yr?.low ?? 0) + (one?.low ?? 0) / spread;
  const hi = (yr?.high ?? yr?.low ?? 0) + (one?.high ?? one?.low ?? 0) / spread;
  if (!(lo > 0)) return null;
  return { lo, hi: Math.max(lo, hi), mid: geo(lo, Math.max(lo, hi)) };
}

// The third switch position is the table, so a figure is only ever on screen once.
const TABLE_VIEW = { key: "table", label: "All figures" };
const shortN = (v) => (v >= 1e6 ? `${sig2(v / 1e6)}M` : v >= 1e4 ? `${sig2(v / 1e3)}K` : sig2(v));
const VIEWS = {
  // Opens on the list's own measure, so every ranked change is on the chart beside it.
  miles: {
    label: "Miles cut",
    get: (o) => {
      const v = o.vmt_reduction || {};
      if (v.rank_on_central) return { low: v.annual_miles_central, central: v.annual_miles_central, high: v.annual_miles_central };
      return { low: v.annual_miles_low, central: v.annual_miles_central, high: v.annual_miles_high };
    },
    axis: ["Miles of driving cut a year →", "Miles cut a year →"],
    short: shortN,
    tip: (v) => `${shortN(v)} miles a year`,
  },
  mode: {
    label: "Car trips",
    get: (o) => o.mode_shift_pts,
    axis: ["Car trips, points of trip share cut →", "Car trips, points cut →"],
    short: (v) => sig2(v),
    tip: (v) => `${sig2(v)} points of car share`,
  },
  injury: {
    label: "Injuries",
    get: (o) => o.per_sq_mi && { low: o.per_sq_mi.low, central: o.per_sq_mi.value, high: o.per_sq_mi.high },
    axis: ["Injuries avoided a year, per square mile covered →", "Injuries avoided a year per sq. mile →"],
    short: (v) => sig2(v),
    tip: (v) => `${sig2(v)} injuries avoided a year per square mile`,
  },
};

/** Every option with its cost a year, and which views it can go on. */
function optionData() {
  return SC.options.map((o) => {
    const cost = yearCost(o);
    const ignored = o.status?.state === "ignored";
    if (o.status && !["done", "planned", "asked", "ignored"].includes(o.status.state)) throw new Error(`toolkit-matrix: ${o.id} has status "${o.status.state}"`);
    const vals = {};
    for (const [k, v] of Object.entries(VIEWS)) {
      const f = v.get(o);
      // A range with no central figure still goes on: its bar, with no dot.
      const top = f?.central ?? f?.high;
      vals[k] = cost && top > 0 ? { lo: f.low ?? f.central ?? 0, mid: f.central > 0 ? f.central : null, hi: f.high ?? f.central } : null;
    }
    return { o, id: o.id, name: o.name, cost, ignored, vals, miles: milesPerDollar(o, cost) };
  });
}

/**
 * Miles of driving cut a year for each dollar a year, low and high, or null without a miles figure and a cost.
 * The low sets the fewest miles against the highest cost, unless the cost is tied to the miles (more money
 * buys more miles), and then low goes with low and high with high.
 */
function milesPerDollar(o, cost) {
  const v = o.vmt_reduction || {};
  const lo = v.rank_on_central ? v.annual_miles_central : v.annual_miles_low ?? v.annual_miles_central;
  const hi = v.rank_on_central ? v.annual_miles_central : v.annual_miles_high ?? v.annual_miles_central;
  if (!cost || lo == null || hi == null || !(hi > 0)) return null;
  return o.cost?.tied_to_miles ? { lo: lo / cost.lo, hi: hi / cost.hi } : { lo: lo / cost.hi, hi: hi / cost.lo };
}

/** The Top asks: every change with miles and a cost, by the top of its miles-per-dollar range, and the unranked cheapest first. */
function topAsks(all) {
  const ranked = all.filter((d) => d.miles).sort((a, b) => b.miles.hi - a.miles.hi || a.id.localeCompare(b.id));
  const cheapest = (a, b) => (a.cost?.mid ?? Infinity) - (b.cost?.mid ?? Infinity) || a.id.localeCompare(b.id);
  return { ranked, unmeasured: all.filter((d) => !d.miles).sort(cheapest) };
}

// The chart's sizes: wide for a laptop, mid for the board's doc column, narrow for a phone.
const LAYOUTS = {
  mid: { W: 700, H: 500, L: 62, R: 12, T: 12, B: 46, fs: 12 },
  narrow: { W: 370, H: 740, L: 52, R: 8, T: 10, B: 44, fs: 11 },
};

/** A log domain from the nearest 1, 2 or 5 step at or beyond the data, so a range that ends at 1.3 doesn't stretch to 10. */
function logDomain(lo, hi) {
  const down = (v) => { const p = 10 ** Math.floor(Math.log10(v)); return [5, 2, 1].map((m) => m * p).find((x) => x <= v * 1.0001); };
  const up = (v) => { const p = 10 ** Math.floor(Math.log10(v)); return [1, 2, 5, 10].map((m) => m * p).find((x) => x >= v * 0.9999); };
  return [down(lo), up(hi)];
}
/** The powers of ten inside a domain, for ticks and grid lines. */
function powers(a, b) {
  const out = [];
  for (let k = Math.ceil(Math.log10(a) - 1e-9); k <= Math.floor(Math.log10(b) + 1e-9); k++) out.push(10 ** k);
  return out;
}

function viewSvg(view, layout, all) {
  const V = VIEWS[view], { W, H, L, R, T, B, fs } = LAYOUTS[layout];
  const pts = all.filter((d) => d.vals[view]);
  // One cost axis for every view, so a change stays put when the view switches.
  const charted = all.filter((d) => Object.values(d.vals).some(Boolean));
  const [x0, x1] = logDomain(Math.min(...charted.map((d) => d.cost.lo)), Math.max(...charted.map((d) => d.cost.hi)));
  // A low of zero has no place on a log axis, so its range runs to the bottom edge.
  const [y0, y1] = logDomain(Math.min(...pts.flatMap((d) => [d.vals[view].lo, d.vals[view].mid, d.vals[view].hi].filter((v) => v > 0))), Math.max(...pts.map((d) => d.vals[view].hi)));
  const lx = (v) => Math.log10(v);
  const px = (v) => L + ((W - L - R) * (lx(v) - lx(x0))) / (lx(x1) - lx(x0));
  const py = (v) => H - B - ((H - T - B) * (lx(v) - lx(y0))) / (lx(y1) - lx(y0));
  const r = layout === "narrow" ? 4.5 : 5.5;
  const P = pts.map((d) => {
    const v = d.vals[view];
    const name = d.o.short || d.name;
    const fig = v.mid != null ? V.short(v.mid) : `${V.short(v.lo)} to ${V.short(v.hi)}`;
    return { ...d, cx: px(d.cost.mid), cy: py(v.mid ?? v.hi), hasDot: v.mid != null, x1: px(d.cost.lo), x2: px(d.cost.hi), yLo: v.lo > 0 ? py(v.lo) : H - B, yHi: py(v.hi), r, label: `${name} ${fig}`, finding: d.ignored, bar: { y1: d.vals[view].hi > 0 ? py(d.vals[view].hi) : H - B, y2: v.lo > 0 ? py(v.lo) : H - B }, pct: -(v.mid ?? v.hi) };
  });
  placeLabels(P, { x1: L + 2, x2: W - R, y1: T, y2: H - B - 2 }, fs, P.filter((d) => d.yLo - d.yHi > 1).map((d) => ({ x1: d.cx - 1.5, x2: d.cx + 1.5, y1: d.yHi, y2: d.yLo, soft: true })));
  const xt = powers(x0, x1), yt = powers(y0, y1);
  const tip = (d) => `${d.o.name}: ${d.vals[view].mid != null ? V.tip(d.vals[view].mid) : `${V.short(d.vals[view].lo)} to ${V.tip(d.vals[view].hi)}`}, ${d.cost.hi > d.cost.lo * 1.05 ? `${money(d.cost.lo)} to ${money(d.cost.hi)}` : money(d.cost.lo)} a year.${d.ignored ? " Nobody's asking for it yet." : ""}`;
  const marks = [
    Plot.link(yt, { x1: L, x2: W - R, y1: (v) => py(v), y2: (v) => py(v), stroke: "var(--rule)", strokeDasharray: "2 4" }),
    Plot.link(xt, { x1: (v) => px(v), x2: (v) => px(v), y1: T, y2: H - B, stroke: "var(--rule)", strokeDasharray: "2 4" }),
    Plot.text(xt, { x: (v) => px(v), y: H - B + 14, text: (v) => money(v), fontSize: fs, fill: "var(--muted)" }),
    Plot.text([0], { x: (L + W - R) / 2, y: H - 10, text: () => (layout === "narrow" ? `Cost a year, build over ${SPREAD_YEARS} years (each line 10x) →` : `Cost a year, build over ${SPREAD_YEARS} years (each line is 10x) →`), fontSize: fs, fill: "var(--ink)" }),
    Plot.text(yt, { x: L - 6, y: (v) => py(v), text: (v) => V.short(v), textAnchor: "end", fontSize: fs, fill: "var(--muted)" }),
    Plot.text([0], { x: 10, y: (T + H - B) / 2, rotate: -90, text: () => V.axis[layout === "narrow" ? 1 : 0], fontSize: fs, fill: "var(--ink)" }),
    // Each change's ranges: cost across, its figure up and down, both light so the point leads.
    Plot.link(P.filter((d) => d.x2 - d.x1 > 1), { x1: "x1", x2: "x2", y1: "cy", y2: "cy", stroke: GREY, strokeOpacity: 0.5, strokeWidth: 2.5 }),
    Plot.link(P.filter((d) => d.yLo - d.yHi > 1), { x1: "cx", x2: "cx", y1: "yHi", y2: "yLo", stroke: (d) => (d.ignored && !d.hasDot ? RING : GREY), strokeOpacity: 0.75, strokeWidth: 2.5 }),
    Plot.link(P.filter((d) => d.lab.leader), { x1: (d) => d.lab.leader.x1, y1: (d) => d.lab.leader.y1, x2: (d) => d.lab.leader.x2, y2: (d) => d.lab.leader.y2, stroke: GREY, strokeWidth: 0.8 }),
    ...["start", "end", "middle"].map((a) => Plot.text(P.filter((d) => d.lab.anchor === a), { x: (d) => d.lab.x, y: (d) => d.lab.y, text: "label", textAnchor: a, fontSize: fs, fill: "#15181c", stroke: "#ffffff", strokeWidth: 3, paintOrder: "stroke", title: tip })),
    Plot.dot(P.filter((d) => !d.ignored && d.hasDot), { x: "cx", y: "cy", r: "r", fill: "#6b7380", title: tip }),
    Plot.dot(P.filter((d) => d.ignored && d.hasDot), { x: "cx", y: "cy", r: (d) => d.r + 1, fill: "#ffffff", stroke: RING, strokeWidth: 2.4, title: tip }),
  ];
  return plotSVG({ width: W, height: H, margin: 0, x: { type: "identity", axis: null }, y: { type: "identity", axis: null }, r: { type: "identity" }, style: { fontFamily: "system-ui, sans-serif" }, marks },
    { className: `mx-svg mx-${layout}`, label: `${V.label} against cost a year for ${P.length} changes. Nobody's asking yet for: ${P.filter((d) => d.ignored).map((d) => d.name).join(", ") || "none"}.` });
}

const MX_TAG = `<span class="mx-tag">Nobody's asking yet</span>`;
const STATE_WORDS = { done: "Done", planned: "In a plan" };
const NM = `<span class="mx-nm">no estimate</span>`;
/** The range where there is one, with the chart's middle figure under it, else the one figure; "no estimate" says there is none. */
function rng(f, showMiddle = true) {
  const hi = f?.high ?? f?.central;
  if (f?.low != null && hi != null && f.low !== hi) {
    const middle = showMiddle && f.central != null && f.central !== f.low && f.central !== hi ? `<span class="mx-r">Middle ${shortN(f.central)}</span>` : "";
    return `${shortN(f.low)} to ${shortN(hi)}${middle}`;
  }
  return hi != null ? shortN(hi) : NM;
}

// The table cell keeps a field's opening: a plan's name, the first whole sentence of SF's record,
// the first three opponents. The full text stays in data/options/scorecard.json.
const clip = (t, n) => (t.length > n ? t.slice(0, t.lastIndexOf(" ", n - 1)).replace(/[,;:]$/, "") + "…" : t);
const planName = (t) => clip(untag(t).split(/\s\(|: |; |, (?=[a-z])/)[0], 70);
const firstSentence = (t) => untag(t).split(/(?<=[a-z0-9)'])\. (?=[A-Z])|; /)[0].replace(/\.$/, "");
const stop = (t) => (/[….]$/.test(t) ? t : `${t}.`);
const shortName = (t) => untag(t).replace(/\s*[(\[].*$/, "").trim();

const gradeWords = (g) => { if (/not rechecked/i.test(g)) return "No grade yet"; const t = g.replace(/\bSMS\b/, "study grade"); return t[0].toUpperCase() + t.slice(1); };

/** The details table: every change, every scorecard field, sorted as the Top asks are. */
function detailsTable(all, order) {
  const rows = order.map((d) => {
    const o = d.o, s = o.status || {}, rd = o.readiness || {}, m = o.money || {};
    const inj = o.injuries_avoided_per_year;
    const vmt = o.vmt_reduction && { low: o.vmt_reduction.annual_miles_low, central: o.vmt_reduction.annual_miles_central, high: o.vmt_reduction.annual_miles_high };
    const hasMiles = vmt && (vmt.low != null || vmt.central != null);
    const hasMid = hasMiles && vmt.central != null && vmt.central !== vmt.low && vmt.central !== vmt.high;
    const evidence = [hasMid ? `Middle ${shortN(vmt.central)}` : "", hasMiles && o.vmt_reduction.grade ? esc(gradeWords(o.vmt_reduction.grade)) : ""].filter(Boolean).join(". ");
    const cost = d.cost ? `${money(d.cost.lo)}${d.cost.hi > d.cost.lo * 1.05 ? ` to ${money(d.cost.hi)}` : ""}` : NM;
    const asked = [...new Set((s.asked_by || []).map((a) => esc(a.group)))].join(", ");
    // The parenthesis stays: it says which fight this was, and without it a past fight reads as opposition to this change.
    const ob = (rd.opposed_by || []).map((x) => String(x).replace(/\s*\[[^\]]*\]/g, "").trim()).filter(Boolean);
    const opp = [rd.sf_record ? esc(stop(firstSentence(rd.sf_record))) : "", ob.length ? `<b>Opposed by:</b> ${esc(ob.slice(0, 3).join(", "))}${ob.length > 3 ? ` and ${ob.length - 3} more` : ""}.` : ""].filter(Boolean).join(" ");
    const fit = { yes: "Yes", maybe: "Maybe", no: "No" }[m.fit];
    const srcs = (m.sources || []).map((x) => esc(shortName(x.name))).slice(0, 2).join(", ") + ((m.sources || []).length > 2 ? ", more" : "");
    // The list is hidden in this view, so the row carries the tag.
    const status = d.ignored ? MX_TAG : s.state === "asked" ? `Asked by ${asked}` : `${esc(STATE_WORDS[s.state] || "")}${s.plan ? `<span class="mx-r">${esc(planName(s.plan))}</span>` : ""}${asked ? `<span class="mx-r">Asked by ${asked}</span>` : ""}`;
    return `<tr>
<th scope="row">${esc(o.name)}</th>
<td data-h="Cost a year" class="mx-n">${cost}</td>
<td data-h="Miles cut a year" class="mx-n mx-main-n">${rng(vmt, false)}</td>
<td data-h="Status">${status}</td>
<td data-h="More" class="mx-more"><details><summary>More</summary><dl>
${evidence ? `<dt>Miles evidence</dt><dd>${evidence}</dd>` : ""}
<dt>Car trips, points cut</dt><dd>${rng(o.mode_shift_pts)}</dd>
<dt>Injuries avoided a year, whole change</dt><dd>${rng(inj)}</dd>
<dt>SF record and opposition</dt><dd>${opp || NM}</dd>
<dt>Existing money</dt><dd>${fit ? `${esc(fit)}${srcs ? `<span class="mx-r">${srcs}</span>` : ""}` : `<span class="mx-nf">not found yet</span>`}</dd>
</dl></details></td>
</tr>`;
  }).join("\n");
  return `<div class="mx-scroll"><table class="mx-tbl">
<thead><tr><th scope="col">Change</th><th scope="col">Cost a year</th><th scope="col">Miles cut a year</th><th scope="col">Status</th><th scope="col">More</th></tr></thead>
<tbody>${rows}</tbody>
</table></div>`;
}

function matrixBlock() {
  const all = optionData();
  const { ranked, unmeasured } = topAsks(all);
  if (!ranked.length) throw new Error("toolkit-matrix: no change has both a VMT figure and a cost, so there are no Top asks");
  const title = "Which changes cut driving and injuries for the money";
  // Below one a mile, one digit is all the evidence supports, as in the methods table.
  const one = (v) => (v > 0 && v < 1 ? String(+v.toPrecision(1)) : sig2(v));
  const perDollar = (d) => (d.miles.lo === d.miles.hi ? one(d.miles.hi) : `${one(d.miles.lo)} to ${one(d.miles.hi)}`);
  const list = `<ol class="mx-asks">${ranked.map((d) => `<li><span class="mx-ab"><span class="mx-an">${esc(d.o.short || d.name)}</span></span><span class="mx-av">${esc(perDollar(d))}</span></li>`).join("")}</ol>`;
  const ring = `<svg viewBox="0 0 14 14" width="12" height="12" aria-hidden="true"><circle cx="7" cy="7" r="5.2" fill="#ffffff" stroke="${RING}" stroke-width="2"/></svg>`;
  // Changes nobody's asking for that the miles chart can't ring, because they have no miles figure.
  const nobody = all.filter((d) => d.ignored && !ranked.includes(d)).map((d) => d.o.short || d.name);
  const nobodyLine = `<p class="mx-nobody">${ring} A blue ring means we found no group or City plan behind it.${nobody.length ? ` Also, with no miles figure: ${esc(nobody.join("; "))}.` : ""}</p>`;
  const setup = ranked.filter((d) => d.o.cost?.no_setup_priced).map((d) => d.o.short || d.name);
  const central = ranked.filter((d) => d.o.vmt_reduction?.rank_on_central).map((d) => d.o.short || d.name);
  // Named elsewhere on the opening view, so the note counts only the rest.
  const unpriced = all.filter((d) => !d.cost && !d.ignored && (d.o.vmt_reduction?.annual_miles_central ?? d.o.vmt_reduction?.annual_miles_high) > 0);
  const listNote = `<p class="tk-key">Ranked by best case. By worst case the top two swap and the rest reorder. The charges' costs are before revenue, and we haven't priced the ${esc(setup.join(", "))}'s setup. ${unmeasured.length - nobody.length - unpriced.length} more lack miles or cost.</p>`;
  const charts = Object.keys(VIEWS).map((v, i) => `<div class="mx-chart" data-view="${v}"${i ? " hidden" : ""}>${Object.keys(LAYOUTS).map((n) => viewSvg(v, n, all)).join("")}</div>`).join("");
  const hasInjury = (d) => { const i = d.o.injuries_avoided_per_year; return i && (i.central ?? i.high) != null && !d.vals.injury; };
  const offCount = (v, off) => {
    if (off <= 0) return "";
    if (v !== "injury") return `${off} changes have no figure here.`;
    const elsewhere = all.filter((d) => d.cost && hasInjury(d)).length;
    return `${elsewhere} more are in All figures, and ${off - elsewhere} have no figure.`;
  };
  const offLine = (v) => {
    const f = (d) => VIEWS[v].get(d.o);
    const noCost = all.filter((d) => !d.cost && (f(d)?.central ?? f(d)?.high) > 0).map((d) => d.name);
    const off = all.filter((d) => !d.vals[v]).length - noCost.length;
    // The list's note already counts the changes off the miles chart.
    return [noCost.length ? `No cost yet: ${noCost.join(", ")}.` : "", v === "miles" ? "" : offCount(v, off)].filter(Boolean).join(" ");
  };
  const toggle = `<div class="mx-ctl" role="group" aria-label="View">${[...Object.entries(VIEWS), [TABLE_VIEW.key, TABLE_VIEW]].map(([k, v], i) => `<button type="button" class="mx-seg" data-view="${k}" aria-pressed="${i ? "false" : "true"}">${esc(v.label)}</button>`).join("")}</div>`;
  const key = Object.keys(VIEWS).map((v, i) => `<p class="mx-key mx-off" data-view="${v}"${i ? " hidden" : ""}>${v === "injury" ? "Compare with care: cost here is the whole program, not per square mile." : "Up and to the left gets more for the money."} Bars run low to high, and one reaching the bottom starts at zero.</p>`).join("");
  const order = [...ranked, ...unmeasured];
  return page("toolkit-matrix", title, `<h2>${esc(title)}</h2>
<p class="mx-sub">${esc(SC._intro)}</p>
<div class="mx-grid" data-view="${Object.keys(VIEWS)[0]}">
<section class="mx-list"><h3 class="mx-h3">Top asks: miles cut a year per $1 a year</h3>${list}${nobodyLine}${listNote}</section>
<div class="mx-side">${toggle}${key}</div>
<div class="mx-main"><div class="mx-charts">${charts}</div>
${Object.keys(VIEWS).map((v, i) => { const base = v === "mode" ? ` Daily trips are a model figure in ${link(SC._base.url, SC._base.title)}.` : ""; return `<p class="tk-key mx-off" data-view="${v}"${i ? " hidden" : ""}>${esc(SC._view_notes[v] || "")}${base} ${esc(offLine(v))}</p>`; }).join("")}
<div class="mx-chart" data-view="table" hidden><div class="mx-table"><p class="tk-key">In Top asks order, then the rest cheapest first.</p>${detailsTable(all, order)}
<p class="tk-key">${esc(central.join(", "))} ranks on its middle figure. Where more money buys more miles, the list pairs low miles with low cost. ${esc(SC._sources_note)}</p></div></div></div>
</div>`, MX_SCRIPT, { head: "", css: TK_CSS + MX_CSS });
}

const MX_SCRIPT = `<script>
(function () {
  var btns = document.querySelectorAll(".mx-seg");
  function show(v) {
    btns.forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === v)); });
    document.querySelector(".mx-grid").setAttribute("data-view", v);
    document.querySelectorAll(".mx-chart, .mx-off").forEach(function (c) { c.hidden = c.getAttribute("data-view") !== v; });
    if (window.sfworksHeight) sfworksHeight();
  }
  btns.forEach(function (b) { b.addEventListener("click", function () {
    show(b.getAttribute("data-view"));
    // Stacked on a phone, the switch would otherwise change something below the fold.
    if (window.innerWidth < 1100) document.querySelector(".mx-side").scrollIntoView({ block: "start" });
  }); });
})();
</script>`;

const MX_CSS = `
.tkb { max-width: none; }
.mx-sub { margin: 0 0 8px; color: var(--muted); font-size: 0.9rem; }
.mx-h3 { font-family: Archivo, sans-serif; font-size: 1rem; margin: 0 0 4px; }
.mx-grid { display: grid; gap: 10px 22px; grid-template-columns: minmax(0, 1fr); grid-template-areas: "list" "side" "main"; }
.mx-main-n { font-weight: 700; }
.mx-main-n .mx-r { font-weight: 400; }
.mx-list { grid-area: list; min-width: 0; }
.mx-grid[data-view="table"] .mx-list, .mx-grid[data-view="mode"] .mx-list, .mx-grid[data-view="injury"] .mx-list { display: none; }
.mx-side { grid-area: side; min-width: 0; }
.mx-main { grid-area: main; min-width: 0; }
.mx-asks { margin: 0 0 4px; padding: 0; list-style: none; counter-reset: ask; }
.mx-asks li { counter-increment: ask; padding: 2px 0; border-bottom: 1px solid #e3e6ea; display: flex; align-items: baseline; gap: 0 8px; font-size: 0.86rem; }
.mx-asks li::before { content: counter(ask); flex: 0 0 1.3em; text-align: right; color: #5b6573; font-variant-numeric: tabular-nums; }
.mx-ab { flex: 1 1 auto; min-width: 0; }
.mx-an { font-weight: 700; }
.mx-av { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--muted); white-space: nowrap; }
.mx-nobody { margin: 6px 0; font-size: 0.82rem; }
.mx-tag { font-size: 0.72rem; font-weight: 700; color: ${RING}; border: 1.5px solid ${RING}; border-radius: 10px; padding: 0 6px; white-space: nowrap; }
.mx-key { margin: 6px 0 0; font-size: 0.8rem; color: var(--muted); }
.mx-key svg { vertical-align: -1px; }
.mx-ctl { display: inline-flex; align-items: stretch; font-size: 0.84rem; }
.mx-seg { font: inherit; min-height: 44px; padding: 4px 10px; border: 1.5px solid #3d4450; background: #ffffff; color: #3d4450; cursor: pointer; white-space: nowrap; }
.mx-seg:first-of-type { border-radius: 18px 0 0 18px; }
.mx-seg + .mx-seg { border-left: 0; }
.mx-seg:last-of-type { border-radius: 0 18px 18px 0; }
.mx-seg[aria-pressed="true"] { background: #3d4450; color: #ffffff; font-weight: 700; }
.mx-seg:focus-visible { outline: 2px solid ${RING}; outline-offset: 2px; }
.mx-charts svg { width: 100%; height: auto; }
.mx-svg { display: none; }
.mx-mid { display: block; }
@media (max-width: 600px) { .mx-mid { display: none; } .mx-narrow { display: block; } }
/* A laptop: controls left, chart middle, figures right, on one 1366 by 768 screen. */
@media (min-width: 1100px) {
  .mx-grid { grid-template-columns: 128px minmax(0, 620px) minmax(0, 540px); grid-template-areas: "side main list"; align-items: start; }
  .mx-ctl { display: flex; flex-direction: column; }
  .mx-seg { border-radius: 0 !important; border: 1.5px solid #3d4450; text-align: left; }
  .mx-seg + .mx-seg { border-top: 0; border-left: 1.5px solid #3d4450; }
  .mx-seg:first-of-type { border-radius: 8px 8px 0 0 !important; }
  .mx-seg:last-of-type { border-radius: 0 0 8px 8px !important; }
  .mx-grid[data-view="table"] { grid-template-areas: "side main main"; }
}
.mx-table { padding: 4px 0 0; }
.mx-scroll { overflow-x: auto; }
.mx-tbl { border-collapse: collapse; font-size: 0.8rem; line-height: 1.3; width: 100%; }
.mx-tbl th, .mx-tbl td { text-align: left; vertical-align: top; padding: 5px 8px 5px 0; border-top: 1px solid #e3e6ea; }
.mx-tbl thead th { border-top: 0; color: var(--muted); font-size: 0.74rem; vertical-align: bottom; }
.mx-tbl tbody th { min-width: 110px; }
.mx-tbl td:nth-child(4) { min-width: 110px; }
.mx-tbl td.mx-n { font-variant-numeric: tabular-nums; white-space: nowrap; }
.mx-tbl td.mx-more { min-width: 240px; }
.mx-more summary { cursor: pointer; color: var(--muted); }
.mx-more dl { margin: 4px 0 0; }
.mx-more dt { font-weight: 700; margin-top: 4px; }
.mx-more dd { margin: 0; }
.mx-way, .mx-r { display: block; font-weight: 400; color: var(--muted); font-size: 0.74rem; white-space: normal; }
.mx-nm, .mx-nf { color: var(--muted); }
@media (max-width: 600px) {
  .mx-tbl { min-width: 0; width: 100%; }
  .mx-tbl thead { display: none; }
  .mx-tbl, .mx-tbl tbody, .mx-tbl tr, .mx-tbl th, .mx-tbl td { display: block; min-width: 0 !important; white-space: normal !important; }
  .mx-tbl tr { border-top: 1px solid #c9ced6; padding: 8px 0; }
  .mx-tbl th, .mx-tbl td { border: 0; padding: 1px 0; }
  .mx-tbl tbody th { font-size: 0.9rem; padding-bottom: 3px; }
  .mx-tbl td::before { content: attr(data-h) ": "; font-weight: 700; color: var(--ink); }
  .mx-tbl .mx-r { display: inline; margin-left: 4px; }
  .mx-tbl td.mx-more::before { content: none; }
  .mx-tbl td:has(> .mx-nm:only-child), .mx-tbl td:empty { display: none; }
}
`;

/** Rough label width in pixels for the label placer: system-ui runs about 0.53em a character, bold a little wider. */
const textW = (s, fs, bold) => s.length * fs * (bold ? 0.57 : 0.53);

/** Place each label beside its mark without touching another label, a mark or a cost bar; a label pushed away gets a leader line. */
function placeLabels(pts, box, fs, keepOut = []) {
  const hit = (a, b) => a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
  const obstacles = [...keepOut];
  for (const p of pts) {
    obstacles.push({ x1: p.cx - p.r - 1, x2: p.cx + p.r + 1, y1: p.cy - p.r - 1, y2: p.cy + p.r + 1 });
    if (p.x2 - p.x1 > 2 * p.r) obstacles.push({ x1: p.x1, x2: p.x2, y1: p.cy - 2, y2: p.cy + 2 });
  }
  const placed = [];
  // Dots first, then bars from the left, so a bar's label takes the line over its own cap before a bar further right reaches across it.
  const order = [...pts].sort((a, b) => (b.finding - a.finding) || (b.hasDot - a.hasDot) || (a.hasDot ? a.pct - b.pct : a.cx - b.cx) || a.id.localeCompare(b.id));
  const h = fs * 1.15;
  for (const p of order) {
    const w = textW(p.label, fs, p.finding);
    const cands = [];
    const steps = [0]; for (let k = 1; k <= 12; k++) steps.push(-k, k);
    for (const k of steps) {
      const dy = k * (h + 1);
      const gap = p.r + 4 + (Math.abs(k) > 1 ? 8 : 0);
      // Right of the cost bar's end when the bar runs past the dot, so the label never sits on the bar.
      cands.push({ k, x: Math.max(p.cx + gap, k === 0 ? p.x2 + 4 : p.cx + gap), y: p.cy + dy, anchor: "start" });
      cands.push({ k, x: Math.min(p.cx - gap, k === 0 ? p.x1 - 4 : p.cx - gap), y: p.cy + dy, anchor: "end" });
      if (k) cands.push({ k, x: p.cx, y: p.cy + dy + Math.sign(dy) * (p.r + 2), anchor: "middle" });
      // A bar with no dot has no point to sit by, so after its cap, anywhere along it is beside its mark.
      if (k === -1 && p.bar && !p.hasDot) for (let y = p.bar.y1 + h / 2; y <= Math.min(p.bar.y2, p.cy + 160) - h / 2; y += h + 1) if (Math.abs(y - p.cy) > h) {
        cands.push({ k: 0, along: true, x: p.cx + 5, y, anchor: "start" }, { k: 0, along: true, x: p.cx - 5, y, anchor: "end" });
      }
    }
    // First pass stays within three lines of the mark and off every bar; a second lets a label cross a soft bar, so it never drifts far to dodge one. A finding starts there, so it stays beside its ring.
    let best = null;
    for (const strict of p.finding ? [false] : [true, false]) for (const c of cands) {
      if (best) break;
      if (strict && Math.abs(c.k) > 3) continue;
      const x1 = c.anchor === "start" ? c.x : c.anchor === "end" ? c.x - w : c.x - w / 2;
      const b = { x1: x1 - 2, x2: x1 + w + 2, y1: c.y - h / 2, y2: c.y + h / 2 };
      if (b.x1 < box.x1 || b.x2 > box.x2 || b.y1 < box.y1 || b.y2 > box.y2) continue;
      if (placed.some((q) => hit(q, b)) || obstacles.some((q) => (strict || !q.soft) && hit(q, b))) continue;
      best = { ...c, b };
    }
    if (!best) {
      // Nowhere clear: fall back to the right of the dot and say so in the build log.
      console.warn(`toolkit-matrix: no clear place for the label "${p.label}"`);
      const x1 = p.cx + p.r + 4;
      best = { x: x1, y: p.cy, anchor: "start", b: { x1, x2: x1 + w, y1: p.cy - h / 2, y2: p.cy + h / 2 } };
    }
    placed.push(best.b);
    const far = !best.along && Math.abs(best.y - p.cy) > h * 0.5;
    p.lab = { x: best.x, y: best.y, anchor: best.anchor, leader: far ? { x1: p.cx, y1: p.cy, x2: best.anchor === "start" ? best.b.x1 + 1 : best.anchor === "end" ? best.b.x2 - 1 : best.x, y2: best.anchor === "middle" ? (best.y > p.cy ? best.b.y1 : best.b.y2) : best.y } : null };
  }
}


function page(name, title, body, script, extra) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)} — SF Works</title>
<link rel="canonical" href="${ORIGIN}/transportation/school-trips">
<base target="_blank">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
<style>${extra.css}</style>
${extra.head}
</head>
<body>
<figure class="tkb" data-block="${name}">
${body}
</figure>
${script}
<script>
(function () {
  function send() {
    try { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: document.documentElement.scrollHeight }, "*"); } catch (e) {}
  }
  window.sfworksHeight = send;
  send();
  window.addEventListener("load", send);
  if (window.ResizeObserver) new ResizeObserver(send).observe(document.documentElement);
})();
</script>
</body>
</html>
`;
}

/** The standalone page for one block, at /embed/toolkit/<name>/. */
export function embedPage(name) {
  if (name === "toolkit-table") return tableBlock();
  if (name === "toolkit-matrix") return matrixBlock();
  throw new Error(`toolkit-blocks: no block named "${name}"`);
}
