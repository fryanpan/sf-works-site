// What San Franciscans say matters most in getting around, one city survey at
// a time, for the board doc's `::sfworks{block="survey-priorities"}` line.
// Served at /embed/surveys/<block>/ and /embed/bike/<block>/ by
// src/pages/embed-surveys.mjs.
//
// Bryan, 2026-10-23, on his Safe Streets comment draft: "put the survey results
// below into a clean interactive diagram instead -- one where you show the
// source, question, and results cleanly and keep it concise otherwise? Sort what
// people care about by frequency and color code by convenience, accessibility,
// or safety." Then: "Only SF surveys and show them one at a time and take up less
// vertical space and make it interactive so you can go back in time." And: the
// survey's name is its link, with no separate source line.
//
// Same contract as the injury and school blocks (src/injury-blocks.mjs): one
// self-contained page, CSS, SVG and script inline, no storage or credentialed
// fetches, and a {type: "sfworks:height", block, height} message to the parent
// whenever the page's height changes.
//
// Each survey's bars are drawn with Observable Plot at build time (src/plot.mjs),
// twice: label beside the bar for a wide frame, label above the bar for a phone.
// CSS picks one by the frame's width. The script only steps between surveys.
//
// Figures were read from each survey's own report on 2026-10-23. GrowSF's poll
// published five items and only three are known here, so its panel says so.

import { CSS, FONTS } from "./layout.mjs";
import { Plot, plotSVG } from "./plot.mjs";

export const SURVEY_BLOCKS = ["survey-priorities"];

// Observable 10's first two colours and its teal, plus a grey for whatever is
// none of the three (Bryan, 2026-10-10: Observable 10 for categories).
const KIND = {
  convenience: { label: "Convenience", color: "#4269d0" },
  accessibility: { label: "Accessibility", color: "#efb118" },
  safety: { label: "Safety", color: "#6cc5b0" },
  other: { label: "Other", color: "#c9ccd3" },
};

// Newest first.
export const SURVEYS = [
  {
    name: "GrowSF Pulse poll",
    when: "May 2024",
    url: "https://growsf.org/pulse/growsf-pulse-may-2024/",
    question: "Extremely or very important to invest in",
    sample: "412 SF voters, polled by FM3. 3 of 5 items shown.",
    rows: [
      ["More frequent buses and trains", 78, "convenience"],
      ["Pedestrian safety", 70, "safety"],
      ["Protected bike lanes", 45, "safety"],
    ],
  },
  {
    name: "SFCTA School Access Plan caregiver survey",
    when: "2023",
    url: "https://www.sfcta.org/sites/default/files/2024-07/SF_School_Access_Plan_Report_2023-05-04_FINAL.pdf",
    question: "Why the school trip is stressful, among caregivers who say it often is",
    sample: "366 caregivers. Select all that apply.",
    rows: [
      ["Long trips", 53, "convenience"],
      ["Inconvenient timing", 49, "convenience"],
      ["Other reasons", 30, "other"],
      ["Safety", 25, "safety"],
      ["Cost", 21, "accessibility"],
    ],
  },
  {
    name: "SFMTA Travel Decision Survey",
    when: "2021",
    url: "https://www.sfmta.com/sites/default/files/reports-and-documents/2022/04/sfmta_td2021_rpt_v2.pdf",
    question: "Would definitely get you to ride transit more",
    sample: "756 people, 470 of them SF residents.",
    rows: [
      ["Safety onboard or waiting", 53, "safety"],
      ["Cleaner buses and trains", 50, "other"],
      ["More frequent service", 46, "convenience"],
      ["Better on time performance", 41, "convenience"],
      ["Less crowding", 41, "convenience"],
    ],
  },
  {
    name: "SFMTA citywide survey",
    when: "April 2021",
    url: "https://www.onesanfrancisco.org/sites/default/files/2021-12/Agenda%20Item%205%20-%20SFMTA%20CPC%202022%20Muni%20Reliability%20and%20Street%20Safety%20Bond%20%2810.14.2021%29%20FINAL_1.pdf",
    question: "Very or extremely important to",
    sample: "Polled by FM3. The slides don't give the sample size.",
    rows: [
      ["Quick, convenient transit to all of SF", 80, "convenience"],
      ["Repair Muni vehicles and facilities", 80, "other"],
      ["More Muni for transit dependent areas", 79, "accessibility"],
      ["Muni inclusive and accessible to all", 78, "accessibility"],
      ["Fewer Muni delays", 76, "convenience"],
      ["Street safety for walking", 68, "safety"],
      ["Less crowding on Muni", 65, "convenience"],
    ],
  },
];

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const sorted = (s) => s.rows.map(([label, pct, kind]) => ({ label, pct, kind })).sort((a, b) => b.pct - a.pct || a.label.localeCompare(b.label));

const fill = (d) => KIND[d.kind].color;
const ariaOf = (s) => `${s.name}, ${s.when}. ${sorted(s).map((d) => `${d.label} ${d.pct}%`).join(", ")}.`;

/** Label left of the bar, for a frame 560px wide or more. */
function wideSVG(s) {
  const data = sorted(s);
  const row = 24;
  return plotSVG({
    width: 640, height: data.length * row + 4, marginLeft: 262, marginRight: 40, marginTop: 2, marginBottom: 2,
    x: { domain: [0, 100], axis: null },
    y: { domain: data.map((d) => d.label), padding: 0.25, label: null, tickSize: 0 },
    style: { fontSize: "13px", fontFamily: "inherit", color: "#15181c" },
    marks: [
      Plot.axisY({ tickSize: 0, tickPadding: 8, fontSize: 13 }),
      Plot.barX(data, { x: "pct", y: "label", fill }),
      Plot.text(data, { x: "pct", y: "label", text: (d) => `${d.pct}%`, textAnchor: "start", dx: 5, fontWeight: 600 }),
    ],
  }, { className: "wide", label: ariaOf(s) });
}

/** Label above the bar, for a phone. */
function narrowSVG(s) {
  const data = sorted(s);
  const row = 36;
  return plotSVG({
    width: 360, height: data.length * row + 2, marginLeft: 0, marginRight: 36, marginTop: 2, marginBottom: 0,
    x: { domain: [0, 100], axis: null },
    y: { domain: data.map((d) => d.label), padding: 0, axis: null },
    style: { fontSize: "13px", fontFamily: "inherit", color: "#15181c" },
    marks: [
      Plot.barX(data, { x: "pct", y: "label", fill, insetTop: 19, insetBottom: 3 }),
      Plot.text(data, { x: 0, y: "label", text: "label", textAnchor: "start", dy: -8 }),
      Plot.text(data, { x: "pct", y: "label", text: (d) => `${d.pct}%`, textAnchor: "start", dx: 5, dy: 8, fontWeight: 600 }),
    ],
  }, { className: "narrow", label: ariaOf(s) });
}

const BLOCK_CSS = `
html, body { background: #ffffff; margin: 0; }
body { padding: 6px 12px 8px; }
.sv { max-width: 680px; font-size: 14px; line-height: 1.35; }
/* Controls on the left: the board puts its Tap to interact pill over the
   frame's top right corner. */
.sv-top { display: flex; flex-wrap: wrap; justify-content: flex-start; align-items: center; gap: 6px 20px; margin-bottom: 6px; }
.sv-key { display: flex; flex-wrap: wrap; gap: 2px 12px; color: var(--muted); font-size: 13px; }
.sv-key span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; background: var(--c); vertical-align: -1px; }
.sv-nav { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.sv-nav button { font: inherit; color: var(--ink); background: var(--raised); border: 1px solid var(--rule); border-radius: 6px; padding: 3px 10px; cursor: pointer; }
.sv-nav button:disabled { color: var(--grey-light); cursor: default; }
/* Every panel in one grid cell, so the frame keeps the tallest panel's height
   and the doc below it doesn't jump as the reader steps. */
.sv-panels { display: grid; }
.sv-panel { grid-area: 1 / 1; }
.sv-panel[hidden] { display: block; visibility: hidden; }
.sv-name { margin: 0; font-weight: 600; font-size: 15px; }
.sv-name a { color: var(--ink); }
.sv-name .when { font-weight: 400; color: var(--muted); }
.sv-q { margin: 2px 0 0; }
.sv-sample { margin: 1px 0 6px; color: var(--muted); font-size: 13px; }
.sv svg.plot-chart { display: block; max-width: 100%; height: auto; overflow: visible; }
.sv svg.narrow { display: none; }
@media (max-width: 559px) {
  .sv svg.wide { display: none; }
  .sv svg.narrow { display: block; }
}
`;

const SCRIPT = `<script>
(function () {
  var panels = [].slice.call(document.querySelectorAll(".sv-panel"));
  var newer = document.querySelector(".sv-newer"), older = document.querySelector(".sv-older"), count = document.querySelector(".sv-count");
  var i = 0;
  function show(n) {
    i = Math.max(0, Math.min(panels.length - 1, n));
    panels.forEach(function (p, k) { p.hidden = k !== i; });
    newer.disabled = i === 0;
    older.disabled = i === panels.length - 1;
    count.textContent = (i + 1) + " of " + panels.length;
    if (window.sfworksHeight) window.sfworksHeight();
  }
  newer.addEventListener("click", function () { show(i - 1); });
  older.addEventListener("click", function () { show(i + 1); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") show(i - 1);
    if (e.key === "ArrowRight") show(i + 1);
  });
  show(0);
})();
</script>`;

const heightScript = (name) => `<script>
(function () {
  function send() {
    try { parent.postMessage({ type: "sfworks:height", block: ${JSON.stringify(name)}, height: document.documentElement.scrollHeight }, "*"); } catch (e) {}
  }
  window.sfworksHeight = send;
  send();
  window.addEventListener("load", send);
  if (window.ResizeObserver) new ResizeObserver(send).observe(document.documentElement);
})();
</script>`;

function panel(s, k) {
  return `<section class="sv-panel"${k ? " hidden" : ""}>
<p class="sv-name"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a> <span class="when">${esc(s.when)}</span></p>
<p class="sv-q">${esc(s.question)}</p>
<p class="sv-sample">${esc(s.sample)}</p>
${wideSVG(s)}
${narrowSVG(s)}
</section>`;
}

/** The standalone page for one block. */
export function embedPage(name) {
  if (!SURVEY_BLOCKS.includes(name)) throw new Error(`survey-blocks: no block named "${name}"`);
  const key = Object.values(KIND).map((k) => `<span style="--c:${k.color}">${k.label}</span>`).join("");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>What San Franciscans Say Matters Most — SF Works</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
<style>${BLOCK_CSS}</style>
</head>
<body>
<div class="sv" data-block="${name}">
<div class="sv-top">
<div class="sv-nav"><button type="button" class="sv-newer" aria-label="Newer survey">&larr; Newer</button><span class="sv-count" aria-live="polite">1 of ${SURVEYS.length}</span><button type="button" class="sv-older" aria-label="Older survey">Older &rarr;</button></div>
<div class="sv-key">${key}</div>
</div>
<div class="sv-panels">
${SURVEYS.map(panel).join("\n")}
</div>
</div>
${SCRIPT}
${heightScript(name)}
</body>
</html>
`;
}
