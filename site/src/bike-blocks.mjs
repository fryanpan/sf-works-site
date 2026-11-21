// The bike overview's figures as blocks that stand on their own, for "one
// post, two sites" (2026-10-05): one markdown post, content/posts/
// sf-bike-network.md, publishes to sf-works.org and to fryanpan.com, and each
// `::sfworks{block="<name>"}` line in it is one of the blocks below.
//
// fryanpan.com iframes /embed/bike/<block>/ and saves a frozen copy of each
// page, so an embed page is one self-contained file that works from any
// origin: CSS, scripts and data inline, libraries from absolute CDN URLs, and
// every link or photo pointing at https://sf-works.org rather than a root path.
// The board editor shows the same pages in an iframe sandboxed without
// allow-same-origin, so nothing here may rely on storage, cookies or
// credentialed fetches (the reach control's localStorage use is already in
// try/catch).
//
// Each block is built by the same functions the overview uses, so the two
// cannot drift. A block comes apart into the pieces fryanpan.com renders
// natively (scripts/export-post.mjs writes them to export/<post>/): its
// markup, an ES module whose mount(el, data) makes it interactive, the data
// that module reads, and one stylesheet scoped under .sfw. The embed pages are
// put together from those same pieces, so there is one code path.

import { CSS, FONTS, ORIGIN, gatherNotes } from "./layout.mjs";
import { MAP_HEAD, MAP_CSS, BROWSER, CDN, JS_SRI, CSS_SRI, inlineJson } from "./maplibre.mjs";
import { PLAN_URL } from "./transportation.mjs";
import { history, historyMap, MAP_SCRIPT, REACH_CSS, HMAP_CSS } from "./bike-history.mjs";
import { explorer, goal, goalChart, paceChart, planTypes, planTypesChart, EXPLORER_CSS, EXPLORER_SCRIPT, PLAN_TYPES_CSS, NORTH_STAR_MAP, NORTH_STAR_MAP_SRC } from "./bike-explorer.mjs";
import { overlapVars, STAGE_CSS, STAGE_SCRIPT } from "./pages/transportation-departments.mjs";
import { SEG_MAP_SCRIPT } from "./transportation-map.mjs";
import { contactOfficials, CONTACT_CSS, CONTACT_SCRIPT } from "./contact-officials.mjs";
import { school, lastSurvey, schoolCarChart } from "./school-car-share.mjs";

export const BLOCKS = ["goal-chart", "pace-chart", "map", "mode-share", "north-star-map", "plan-types", "explorer", "repaving", "next-work", "street-work", "contact-officials"];

const LAYER_URL = history.sources.network.url;
const ARCHIVE = "/transportation/bike/about#years";
const cite = (forWhat, how, items) =>
  `<ul class="cite" data-for="${forWhat}"${how ? ` data-how="${how}"` : ""}>${items.map((i) => `<li>${i}</li>`).join("")}</ul>`;
const LAYER = `<a href="${LAYER_URL}">SFMTA's bikeway layer</a>`;
const ARCHIVED = `<a href="${ARCHIVE}">historical copies of the bikeway layer on Internet Archive</a>`;
const PROJECTS = `recent <a href="https://www.sfmta.com/projects">SFMTA project pages</a>`;
const PAVEMENT = `city <a href="https://data.sf.gov/d/78va-8dhi">pavement records</a>`;
const LAYER_FS = `<a href="https://services.sfmta.com/arcgis/rest/services/Bicycle/bicycle/FeatureServer/0">SFMTA's bikeway layer</a>`;

// Bryan, 2026-10-06, on the post's repaving block: "Can you merge this back
// into one chart with "Past Projects" and "Current and Future Projects" as two
// different tabs?" So street-work is the two stages, each whole (bars, map,
// popovers, note and sources), as the panels of one tab list. Past is on show
// first, since it carries the post's finding; the other panel is hidden.
// A map built in a hidden panel has no size, so the first time its panel is
// shown it is resized and fitted to the city.
const TABS_SCRIPT = `<script>
(function () {
  document.querySelectorAll("[data-stw]").forEach(function (w) {
    var tabs = [].slice.call(w.querySelectorAll('[role="tab"]'));
    var panel = function (t) { return w.querySelector("#" + t.getAttribute("aria-controls")); };
    function show(t, focus) {
      tabs.forEach(function (o) {
        var on = o === t;
        o.setAttribute("aria-selected", String(on));
        o.tabIndex = on ? 0 : -1;
        panel(o).hidden = !on;
      });
      if (focus) t.focus();
      panel(t).querySelectorAll(".seg-map").forEach(function (box) {
        var el = box.querySelector(".seg-gl"), m = el && el.sfGL;
        if (!m) return;
        m.resize();
        if (box.dataset.sized) return;
        box.dataset.sized = "1";
        var key = "map" + (box.id ? "-" + box.id : "");
        if (new URLSearchParams(location.search).get(key)) return;
        var d = JSON.parse(box.querySelector("[data-seg-data]").textContent);
        m.fitBounds(d.bounds, { padding: 8, duration: 0 });
      });
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { show(t, false); });
      t.addEventListener("keydown", function (e) {
        var j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (j === undefined) return;
        e.preventDefault();
        show(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
  });
})();
</script>`;

let ov = null;
const vars = () => (ov ||= overlapVars());

// The scripts a block needs, by name, in the order the overview loads them.
const SCRIPTS = { head: MAP_HEAD, history: MAP_SCRIPT, explorer: EXPLORER_SCRIPT, seg: SEG_MAP_SCRIPT, stage: STAGE_SCRIPT, tabs: TABS_SCRIPT, contact: CONTACT_SCRIPT };
const ORDER = Object.keys(SCRIPTS);

/** One block: its HTML, its stylesheets and the scripts it needs. */
export function block(name) {
  switch (name) {
    case "goal-chart":
      return {
        html: `<div class="fig">${goalChart()}</div>
${cite("Goal chart", "/transportation/bike/about#north-star-goal", [LAYER, ARCHIVED, PROJECTS, `the <a href="${PLAN_URL}">Biking and Rolling Plan</a>'s Appendix L network, as we traced it`])}`,
        css: [],
        scripts: [],
      };
    case "pace-chart":
      return {
        html: `<div class="fig">${paceChart()}</div>
${cite("Pace chart", "/transportation/bike/about#planned", [LAYER, ARCHIVED, PROJECTS])}`,
        css: [],
        scripts: [],
      };
    case "mode-share": {
      const { report: r, offTrack: o, goalSource: g, repeal: x } = school;
      const t = lastSurvey;
      return {
        html: `<div class="fig">${schoolCarChart()}</div>
<p class="verdict-note">SFMTA counts how students at about 95 schools get to class every two years, and each count sits at the date it was taken. SFMTA set the goal from 48% in 2018, and its own <a href="${o.url}">2023-24 report</a> says it is "${o.words}" to reach the goal. Across all trips, SFMTA's last survey (${t.year}) found ${t.privateAuto}% by car and ${t.bike}% by bike. The citywide goal of 80% of trips by walking, biking or transit was repealed in April 2026 by <a href="${x.url}">Ordinance ${x.ordinance}</a>.</p>
${cite("School trips chart", "", [`<a href="${r.url}">${r.name}</a>, pp. ${r.pages}`, `SF Safe Routes to School <a href="${o.url}">2023-24 report</a>, Fig. 1`, `<a href="${school.dates.url}">${school.dates.name}</a>`, `<a href="${g.url}">${g.name}</a>, p. ${g.page}`, `SFMTA <a href="${t.url}">Travel Decisions Survey ${t.year}</a>, p. ${t.page}`])}`,
        css: [],
        scripts: [],
      };
    }
    case "north-star-map": {
      const m = NORTH_STAR_MAP;
      return {
        html: `<figure class="fig ns-map"><a href="${NORTH_STAR_MAP_SRC}"><img src="${NORTH_STAR_MAP_SRC}" loading="lazy" decoding="async" alt="${m.alt}" width="${m.width}" height="${m.height}"></a></figure>
<p class="verdict-note">SFMTA's North Star network, from the plan. Tap the map to open it full size.</p>
${cite("North Star map", "", [`SFMTA, <a href="${PLAN_URL}">Biking and Rolling Plan</a> (March 2025), pp. ${m.pages.replace("-", "–")}`])}`,
        css: [],
        scripts: [],
      };
    }
    case "plan-types":
      return {
        html: `<div class="fig">${planTypesChart()}</div>
<p class="verdict-note">Miles count each direction of travel, as the plan does. Percentages are of the ${Math.round(planTypes().total)} miles the plan's map draws as all-ages. The plan doesn't say which of its shared streets are Slow Streets, so we count the ones that are Slow Streets today.</p>
${cite("Bikeway types", "/transportation/bike/about#trace", [`the <a href="${PLAN_URL}">Biking and Rolling Plan</a>'s North Star map, as <a href="/transportation/bike/about#trace">we traced it</a>`])}`,
        css: [PLAN_TYPES_CSS],
        scripts: [],
      };
    case "map":
      return {
        html: `<div class="fig wide">${historyMap()}</div>
${cite("Network map", "", [`<a href="https://data.sf.gov/d/p2fw-hsrv">Census Bureau 2020 census blocks</a>, with American Community Survey estimates for other years`, LAYER, PROJECTS, ARCHIVED])}`,
        css: [REACH_CSS, HMAP_CSS],
        scripts: ["head", "history"],
      };
    case "explorer":
      return {
        html: `<div class="fig">${explorer()}</div>
${cite("Explorer", "/transportation/bike/about#explorer", [`<a href="https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000">Census Bureau American Community Survey</a> population estimates`, `<a href="${history.sources.schools.url}">California Department of Education</a> public schools`, `<a href="https://data.sf.gov/d/7e7j-59qk">DataSF</a> private K-12 schools`, `<a href="https://data.sf.gov/d/nc68-ngbr">City Facilities</a> library branches`, LAYER])}`,
        css: [REACH_CSS, HMAP_CSS, EXPLORER_CSS],
        scripts: ["head", "explorer"],
      };
    case "repaving": {
      const v = vars();
      return {
        html: `${v.pastOpen.replace(STAGE_CSS, "")}
${v.pastView}
${cite("Repaving since the plan", "/transportation/bike/about#since-plan", [PAVEMENT, LAYER_FS, `<a href="https://www.sfmta.com/projects">SFMTA project pages</a>`])}`,
        css: [STAGE_CSS],
        scripts: ["head", "seg", "stage"],
      };
    }
    case "next-work": {
      const v = vars();
      return {
        html: `${v.nextOpen}
${v.nextView}
${v.nextUnmapped ? `<p class="verdict-note">${v.nextUnmapped}</p>\n` : ""}${cite(`Street work through ${v.cmpHorizonYear}`, "/transportation/bike/about#since-plan", [`the city's <a href="${v.ovFeedUrl}">street-work calendar</a>, as of ${v.ovFeedQueried}`, LAYER_FS, `<a href="https://www.sfmta.com/projects">SFMTA project pages</a>`])}`,
        css: [STAGE_CSS],
        scripts: ["head", "seg", "stage"],
      };
    }
    case "street-work": {
      const v = vars();
      const tab = (id, label, on) =>
        `<button type="button" role="tab" id="stw-tab-${id}" aria-controls="stw-panel-${id}" aria-selected="${on}" tabindex="${on ? 0 : -1}">${label}</button>`;
      const panel = (id, on, body) => `<div role="tabpanel" id="stw-panel-${id}" aria-labelledby="stw-tab-${id}"${on ? "" : " hidden"}>
${body}
</div>`;
      return {
        html: `<div class="stw" data-stw>
<div class="stw-tabs" role="tablist" aria-label="Which street work the chart and map show">${tab("past", "Past Projects", true)}${tab("next", "Current and Future Projects", false)}</div>
${panel("past", true, block("repaving").html)}
${panel("next", false, block("next-work").html)}
</div>`,
        css: [STAGE_CSS],
        scripts: ["head", "seg", "stage", "tabs"],
      };
    }
    // Bryan, 2026-10-06, on the post's closing ask: "Add this widget please".
    // No map, so its module loads no MapLibre (see moduleSource).
    case "contact-officials":
      return { html: contactOfficials(), css: [CONTACT_CSS], scripts: ["contact"] };
    default:
      throw new Error(`bike-blocks: no block named "${name}"`);
  }
}

// Bryan, 2026-10-06, on the post's blocks: "Put the photo and data credits at
// the bottom of the page and remove it from the diagrams." So a block's cite
// and credit lists (the marks layout.mjs gathers on the site's own pages) are
// lifted out of its markup, and the post's export gathers every block's into
// one section at the post's end (postCredits below). The embed pages carry
// none either; the post they sit in credits them.
const NOTE_LISTS = /<ul class="(?:cite|credit)"[^>]*>[\s\S]*?<\/ul>/g;
function liftNotes(html) {
  const notes = html.match(NOTE_LISTS) || [];
  return { html: html.replace(NOTE_LISTS, ""), notes };
}

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'", "#8209": "‑" };
const mdText = (t) => t.replace(/&(amp|lt|gt|quot|#39|#8209);/g, (_, e) => ENTITIES[e]).replace(/\s+/g, " ");
// One gathered item as markdown, its words exactly as the block marks them.
const toMarkdown = (html) =>
  mdText(absolute(html)
    .replace(/<a href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/g, (_, href, text) => `[${text.replace(/<[^>]+>/g, "")}](${href.replace(/&amp;/g, "&")})`)
    .replace(/<[^>]+>/g, "")).trim();

/**
 * The credits section for a post's end, as markdown: one list of photo
 * credits and one of data sources for every block the post uses, each line
 * naming the figures it backs, then where each method is explained.
 */
export function postCredits(names) {
  const marks = names.flatMap((n) => liftNotes(block(n).html).notes).join("\n");
  const { cites, credits } = gatherNotes(marks);
  // Items that back exactly the same figures share one line, as on the site.
  const lines = (xs) => {
    const out = [];
    for (const x of xs) {
      const k = x.fors.join("|");
      const line = out.find((l) => l.k === k);
      if (line) line.parts.push(x.html);
      else out.push({ k, fors: x.fors, parts: [x.html] });
    }
    return out.map((l) => `- ${l.fors.length ? `${joinWords(l.fors.map((f, i) => (i ? midLabel(f) : f)))}: ` : ""}${l.parts.map(toMarkdown).join("; ")}`).join("\n");
  };
  const out = ["## Photo and Data Credits", `How we built every map and chart is on sf-works.org's [About the Data](${ORIGIN}/transportation/bike/about/) page.`];
  if (credits.length) out.push("### Photos", lines(credits));
  if (cites.length) out.push("### Data Sources", lines(cites));
  return out.join("\n\n") + "\n";
}
// "Network map, explorer and pace chart": a later label is lower-cased unless
// it carries a name, as layout.mjs does.
const midLabel = (s) => (/[A-Z]/.test(s.slice(1)) ? s : s[0].toLowerCase() + s.slice(1));
const joinWords = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs.join(""));

// Every root path made absolute, in attributes and in the JSON the scripts
// read (a project card's links), so a copy served from another origin still
// reaches sf-works.org.
const absolute = (text) =>
  text
    .replace(/((?:href|src|action|poster)=\\?")\/(?!\/)/g, `$1${ORIGIN}/`)
    .replace(/url\((["']?)\/(?!\/)/g, `url($1${ORIGIN}/`)
    .replace(/("(?:url|href|src|page|path)":")\/(?!\/)/g, `$1${ORIGIN}/`);

const styleBody = (s) => [...s.matchAll(/<style>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join("\n");
const scriptBodies = (s) => [...s.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n");

// Inside an iframe or another site's column, the overview's viewport-relative
// heights would chase the frame's own height, and the wide figures would break
// out of a column that isn't ours. Fixed sizes instead, the same caps the
// overview reaches on a laptop.
const BLOCK_CSS = `
.fig.wide { width: auto; margin-left: 0; }
.ns-map img { display: block; width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 4px; }
.hmap svg, .hmap.hero .hmap-gl { max-height: 720px; }
.ex-map { height: min(640px, 90vw); }
@media (max-width: 760px) { .ex-map { height: 80vw; } }
/* The street-work map gets the room and the bars the narrow column (Bryan,
   2026-10-07: "give more space to the map and less to the bar chart"). */
@media (min-width: 960px) {
  .stage-view { grid-template-columns: 300px minmax(0, 1fr); }
  .stage-view .seg-gl { height: 560px; }
}
.stw-tabs { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--ink); border-radius: 6px; overflow: hidden; margin: 4px 0 12px; max-width: 560px; }
.stw-tabs [role="tab"] { font: inherit; font-weight: 600; padding: 8px 10px; background: #ffffff; color: var(--ink); border: 0; border-left: 1px solid var(--ink); cursor: pointer; line-height: 1.25; }
.stw-tabs [role="tab"]:first-child { border-left: 0; }
.stw-tabs [role="tab"][aria-selected="true"] { background: var(--ink); color: #ffffff; }
.stw-tabs [role="tab"]:focus-visible { outline: 3px solid var(--seq-3); outline-offset: -3px; }
.stw [role="tabpanel"][hidden] { display: none; }
`;

// ---- Scoping the site's stylesheet under .sfw --------------------------------
//
// The host page has its own styles, so every rule here applies only inside a
// .sfw element: :root and body become .sfw (the colour tokens live there,
// which is why maplibre.mjs reads them from .sfw first), html[...] and
// html:not([...]) become .sfw[...] and .sfw:not([...]), and every other
// selector gains a .sfw ancestor.
function splitTop(list) {
  const out = [];
  let depth = 0, cur = "";
  for (const ch of list) {
    if (ch === "(" || ch === "[") depth++;
    if (ch === ")" || ch === "]") depth--;
    if (ch === "," && depth === 0) { out.push(cur); cur = ""; } else cur += ch;
  }
  out.push(cur);
  return out.map((x) => x.trim()).filter(Boolean);
}
function scopeSelector(sel, scope) {
  if (sel === ":root" || sel === "html" || sel === "body") return scope;
  if (sel === "*") return `${scope}, ${scope} *`;
  // State the page keeps on <html>, such as data-reach, lives on the .sfw
  // element instead (see scoped() below), so no rule depends on the host's root.
  const html = /^(?:html|:root)((?:\[[^\]]*\]|:not\(\[[^\]]*\]\))+)\s+(.*)$/.exec(sel);
  if (html) return `${scope}${html[1]} ${html[2]}`;
  const body = /^body\s+(.*)$/.exec(sel);
  if (body) return `${scope} ${body[1]}`;
  return `${scope} ${sel}`;
}
export function scopeCss(css, scope = ".sfw") {
  css = css.replace(/\/\*[\s\S]*?\*\//g, "");
  let out = "", i = 0;
  while (i < css.length) {
    const open = css.indexOf("{", i);
    if (open === -1) { out += css.slice(i).trim() ? "" : ""; break; }
    const prelude = css.slice(i, open).trim();
    // The matching close brace.
    let depth = 1, j = open + 1;
    for (; j < css.length && depth; j++) { if (css[j] === "{") depth++; else if (css[j] === "}") depth--; }
    const inner = css.slice(open + 1, j - 1);
    if (/^@(media|supports|container|layer)\b/.test(prelude)) out += `${prelude} {\n${scopeCss(inner, scope)}}\n`;
    else if (prelude.startsWith("@")) out += `${prelude} {${inner}}\n`;
    else out += `${splitTop(prelude).map((x) => scopeSelector(x, scope)).join(", ")} {${inner.trim()}}\n`;
    i = j;
  }
  return out;
}

/** The one stylesheet every block uses, scoped under .sfw. */
export function sfwCss() {
  const css = [CSS, styleBody(MAP_CSS), styleBody(REACH_CSS), styleBody(HMAP_CSS), styleBody(EXPLORER_CSS), styleBody(PLAN_TYPES_CSS), styleBody(STAGE_CSS), styleBody(CONTACT_CSS), BLOCK_CSS].join("\n");
  return `/* SF Works blocks, scoped under .sfw. Generated from site/src by
   site/scripts/export-post.mjs; edit the source, not this file. */
@import url("${FONTS}");
${absolute(scopeCss(css))}
/* The blocks are drawn for a light page. A host page with a dark theme must
   not turn their form controls, scrollbars or canvas defaults dark. */
.sfw {color-scheme: light;}
/* Headings take the block's ink, not the host page's heading colour, which a
   dark theme sets pale. */
.sfw h1, .sfw h2, .sfw h3, .sfw h4 {color: var(--ink);}
`;
}

// The browser half of a block, as an ES module. The overview's own page
// scripts run unchanged inside run(document), where `document` answers
// queries from inside the block's element only, so two blocks on one host
// page never pick up each other's elements; everything else goes to the real
// document.
function moduleSource(name, bodies, map = true) {
  // A block with no map (contact-officials) carries none of the map loader.
  if (!map) return `// The ${name} block from sf-works.org, made interactive.
// Generated by site/scripts/export-post.mjs from the site's own page scripts;
// edit those, not this file.
//
//   import { mount } from "./${name}.js";
//   el.innerHTML = <blocks/${name}.html>; el.classList.add("sfw");
//   await mount(el, <data/${name}.json>);

function scoped(el) {
  return {
    querySelector: (s) => el.querySelector(s),
    querySelectorAll: (s) => el.querySelectorAll(s),
    createElement: (t) => document.createElement(t),
    createTextNode: (t) => document.createTextNode(t),
    addEventListener: (...a) => document.addEventListener(...a),
    removeEventListener: (...a) => document.removeEventListener(...a),
    get documentElement() { return el; },
    get body() { return document.body; },
  };
}

/** Make the block's markup inside el interactive, with the data from data/${name}.json. */
export async function mount(el, data) {
  if (!data) return;
  for (const [key, value] of Object.entries(data || {})) {
    const [attr, n] = key.split("#");
    const s = el.querySelectorAll('script[type="application/json"][' + attr + "]")[(Number(n) || 1) - 1];
    if (s) s.textContent = JSON.stringify(value);
  }
  run(scoped(el));
}

function run(document) {
${bodies}
}
`;
  return `// The ${name} block from sf-works.org/transportation/bike/, made interactive.
// Generated by site/scripts/export-post.mjs from the overview's own page
// scripts; edit those, not this file.
//
//   import { mount } from "./${name}.js";
//   el.innerHTML = <blocks/${name}.html>; el.classList.add("sfw");
//   await mount(el, <data/${name}.json>);

const MAPLIBRE = { js: ${JSON.stringify(`${CDN}/maplibre-gl.js`)}, jsSri: ${JSON.stringify(JS_SRI)}, css: ${JSON.stringify(`${CDN}/maplibre-gl.css`)}, cssSri: ${JSON.stringify(CSS_SRI)} };

function loadMapLibre() {
  if (window.maplibregl) return Promise.resolve();
  if (!document.querySelector('link[href="' + MAPLIBRE.css + '"]')) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = MAPLIBRE.css; l.integrity = MAPLIBRE.cssSri; l.crossOrigin = "anonymous";
    document.head.appendChild(l);
  }
  return (window.__sfwMapLibre ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = MAPLIBRE.js; s.integrity = MAPLIBRE.jsSri; s.crossOrigin = "anonymous";
    s.onload = ok; s.onerror = fail;
    document.head.appendChild(s);
  }));
}

// window.sfMap, the site's map helpers (src/maplibre.mjs), once per page.
function installSfMap() {
  if (window.sfMap) return;
${BROWSER}
}

function scoped(el) {
  return {
    querySelector: (s) => el.querySelector(s),
    querySelectorAll: (s) => el.querySelectorAll(s),
    createElement: (t) => document.createElement(t),
    createTextNode: (t) => document.createTextNode(t),
    addEventListener: (...a) => document.addEventListener(...a),
    removeEventListener: (...a) => document.removeEventListener(...a),
    // The block element stands in for <html>, so page state such as
    // dataset.reach stays on the block and never touches the host page.
    get documentElement() { return el; },
    get body() { return document.body; },
  };
}

/** Make the block's markup inside el interactive, with the data from data/${name}.json. */
export async function mount(el, data) {
  // No data: leave the pre-rendered markup as it is, static.
  if (!data) return;
  // A key "data-x#2" is the second data-x script in the markup.
  for (const [key, value] of Object.entries(data || {})) {
    const [attr, n] = key.split("#");
    const s = el.querySelectorAll('script[type="application/json"][' + attr + "]")[(Number(n) || 1) - 1];
    if (s) s.textContent = JSON.stringify(value);
  }
  await loadMapLibre();
  installSfMap();
  run(scoped(el));
}

function run(document) {
${bodies}
}
`;
}

/**
 * One block in pieces: the markup with its inline data lifted out, the data
 * by the attribute that marks where it sat, the module (null for a chart that
 * needs no script), and nothing else: the stylesheet is shared (sfwCss).
 */
export function parts(name) {
  const b = block(name);
  const data = {};
  const html = absolute(liftNotes(b.html).html).replace(/<script type="application\/json" (data-[\w-]+)>([\s\S]*?)<\/script>/g, (_, attr, json) => {
    // A block made of two others, such as street-work, carries each data
    // script twice; the later ones are keyed by their place, "data-x#2".
    let key = attr;
    for (let n = 2; key in data; n++) key = `${attr}#${n}`;
    data[key] = JSON.parse(json);
    return `<script type="application/json" ${attr}></script>`;
  });
  if (/<script(?![^>]*application\/json)/.test(html)) throw new Error(`bike-blocks: ${name}'s markup carries a script; move it into the module`);
  const bodies = ORDER.filter((k) => k !== "head" && b.scripts.includes(k)).map((k) => scriptBodies(SCRIPTS[k])).join("\n");
  const js = b.scripts.length ? absolute(moduleSource(name, bodies, b.scripts.includes("head"))) : null;
  return { html, data: js ? data : null, js };
}

const heightScript = (name) => `<script>
(function () {
  function send() {
    try { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: document.documentElement.scrollHeight }, "*"); } catch (e) {}
  }
  send();
  window.addEventListener("load", send);
  if (window.ResizeObserver) new ResizeObserver(send).observe(document.documentElement);
})();
</script>`;

/** The standalone page for one block, at /embed/bike/<name>/, put together from its parts. */
export function embedPage(name) {
  const p = parts(name);
  // An inline module may carry its export; the page then calls mount itself.
  const script = p.js
    ? `<script type="module">
${p.js}
mount(document.querySelector(".sfw"), ${inlineJson(p.data)});
</script>`
    : "";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${name} — SF Works</title>
<link rel="canonical" href="${ORIGIN}/transportation/bike">
<base target="_blank">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>html, body { background: #ffffff; margin: 0; } body { padding: 4px 12px 8px; }</style>
<style>${sfwCss()}</style>
</head>
<body>
<div class="sfw embed" data-block="${name}">
${p.html}
</div>
${script}
${heightScript(name)}
</body>
</html>
`;
}
