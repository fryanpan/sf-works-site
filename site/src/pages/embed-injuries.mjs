// The injury page's map as a standalone page, /embed/injuries/<block>/, for
// the board doc's `::sfworks{block="injury-<x>"}` lines (src/injury-blocks.mjs
// explains the contract). Kept out of the sitemap and marked noindex: no reader
// should land on one from a search.
//
// Hidden on sf-works.org while the injury page is: "/embed/injuries" is in
// HIDDEN_PAGES (src/features.mjs), so production builds neither this index nor
// its blocks, and the dev server and staging (SITE_SHOW_HIDDEN=1) serve them.

import fs from "node:fs";
import nodePath from "node:path";
import { fileURLToPath } from "node:url";
import { INJURY_BLOCKS, embedPage } from "../injury-blocks.mjs";

// The map component package's built files (@claude-workspaces/components,
// vendored in site/vendor/), published beside the blocks so the injury map
// can load it behind its ?map=components switch (src/injury-page.mjs,
// CW_MAP_SRC). They sit under /embed/injuries/, so they are hidden from
// production with the page.
const CW_LIB = nodePath.dirname(fileURLToPath(import.meta.resolve("@claude-workspaces/components/map")));
export const CW_DIR = "embed/injuries/cw-components";
const cwFiles = () => fs.readdirSync(CW_LIB).filter((f) => f.endsWith(".js"))
  .map((f) => ({ path: `/${CW_DIR}/${f}`, file: `${CW_DIR}/${f}`, html: fs.readFileSync(nodePath.join(CW_LIB, f)), sitemap: false }));

export const path = "/embed/injuries";
export const file = "embed/injuries/index.html";
// Kept out of the sitemap by the build (scripts/site-files.mjs skips `asset`).
export const asset = true;
export const sitemap = false;

export function render() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Injury Figures for Embedding — SF Works</title>
<style>body { font-family: system-ui, sans-serif; margin: 24px 16px; background: #ffffff; color: #15181c; }</style>
</head>
<body>
<h1>Injury figures for embedding</h1>
<ul>
${INJURY_BLOCKS.map((b) => `<li><a href="/embed/injuries/${b}/">${b}</a></li>`).join("\n")}
</ul>
</body>
</html>
`;
}

// Each block also answers at /embed/bike/<block>/, because the board maps the
// one `sfworks` directive to a single path template, /embed/bike/{block}/
// (src/pages/embed-school.mjs), so the same line works for these blocks too.
// Their names start with "injury-", which no bike or school block uses.
export function pages() {
  return INJURY_BLOCKS.flatMap((b) => {
    const html = embedPage(b);
    return ["injuries", "bike"].map((dir) => ({ path: `/embed/${dir}/${b}`, file: `embed/${dir}/${b}/index.html`, html, sitemap: false }));
  }).concat(cwFiles());
}
