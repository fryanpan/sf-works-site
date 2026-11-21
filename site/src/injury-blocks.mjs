// The injury page's figures that can't be a board <PlotChart>, as blocks that
// stand on their own, for the board doc's `::sfworks{block="injury-<name>"}`
// lines. Served at /embed/injuries/<block>/ by src/pages/embed-injuries.mjs.
//
// Bryan wants the injury page as an .mdx working doc on the board, where he
// edits the prose (2026-10-22). Its Plot charts became
// <PlotChart> blocks in the doc; the map is interactive, so it is framed from
// here instead.
//
// Same contract as the school and bike blocks (src/school-hurt-blocks.mjs,
// src/bike-blocks.mjs): one self-contained page per block, CSS, data and
// script inline, no storage or credentialed fetches, and a
// {type: "sfworks:height", block, height} message to the parent whenever the
// page's height changes, so the frame fits it.
//
// Nothing is redrawn here. Each block is cut out of the page's own body
// (content() in src/injury-page.mjs), so the embed shows
// exactly what the page shows. A board frame is sandboxed and sends no
// referrer, so Google refuses its tiles and sfMap (src/maplibre.mjs) falls
// back to OpenFreeMap's Positron there.

import { parseHTML } from "linkedom";
import { CSS, FONTS } from "./layout.mjs";
import { content } from "./injury-page.mjs";

export const INJURY_BLOCKS = ["injury-map"];

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// The map at the frame's width, not breaking out of a reading column as it does
// on the page, and no Copy link, which would copy the embed's own address.
const BLOCK_CSS = `
html, body { background: #ffffff; margin: 0; }
body { padding: 4px 12px 8px; }
.hin .mapwrap { width: auto; margin: 8px 0; }
.hin .mapwrap #map { height: 600px; }
.hin .copy-link, .hin .copy-url { display: none; }
@media (max-width: 700px) { .hin .mapwrap #map { height: 440px; } }
`;

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

// What each block keeps of the page's .hin body: the elements a selector matches,
// plus the body's scripts and the project dialog the map's popups open.
const KEEP = {
  "injury-map": (el) => /\b(school-bar|school-line|mapwrap)\b/.test(el.getAttribute("class") || "") || (el.tagName === "P" && el.previousElementSibling?.classList?.contains("mapwrap")),
};

let body = null;
/** The page's body once per build: content() reads every data file. */
function pageBody() {
  if (!body) body = content();
  return body;
}

/** The standalone page for one block, at /embed/injuries/<name>/. */
export function embedPage(name) {
  const keep = KEEP[name];
  if (!keep) throw new Error(`injury-blocks: no block named "${name}"`);
  const { document } = parseHTML(`<!doctype html><html><head></head><body>${pageBody()}</body></html>`);
  const hin = document.querySelector(".hin");
  if (!hin) throw new Error("injury-blocks: the injury page has no .hin body");
  const kept = [...hin.children].filter((el) => keep(el) || el.tagName === "SCRIPT" || el.tagName === "DIALOG");
  if (!kept.some((el) => (el.getAttribute("class") || "").includes("mapwrap"))) throw new Error("injury-blocks: no map found in the injury page");
  // The page's own style and map library sit before .hin; keep them, drop the rest of the body.
  const head = [...document.body.children].filter((el) => el !== hin && (el.tagName === "STYLE" || el.tagName === "LINK" || el.tagName === "SCRIPT")).map((el) => el.outerHTML).join("\n");
  hin.replaceChildren(...kept);
  const title = "Where people get hurt";
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)} — SF Works</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">
<style>${CSS}</style>
${head}
<style>${BLOCK_CSS}</style>
</head>
<body>
<div data-block="${name}">
${hin.outerHTML}
</div>
${heightScript(name)}
</body>
</html>
`;
}
