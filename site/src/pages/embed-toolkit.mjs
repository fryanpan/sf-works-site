// The street safety toolkit table as a standalone page, /embed/toolkit/<block>/,
// for the board doc's `::sfworks{block="toolkit-table"}` line
// (src/toolkit-blocks.mjs explains the contract). Kept out of the sitemap and
// marked noindex: no reader should land on one from a search.

import { TOOLKIT_BLOCKS, embedPage } from "../toolkit-blocks.mjs";

export const path = "/embed/toolkit";
export const file = "embed/toolkit/index.html";
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
<title>Toolkit Figures for Embedding — SF Works</title>
<style>body { font-family: system-ui, sans-serif; margin: 24px 16px; background: #ffffff; color: #15181c; }</style>
</head>
<body>
<h1>Toolkit figures for embedding</h1>
<ul>
${TOOLKIT_BLOCKS.map((b) => `<li><a href="/embed/toolkit/${b}/">${b}</a></li>`).join("\n")}
</ul>
</body>
</html>
`;
}

// Each block also answers at /embed/bike/<block>/, because the board maps the
// one `sfworks` directive to a single path template, /embed/bike/{block}/
// (src/pages/embed-school.mjs), so the same line works for these blocks too.
// Their names start with "toolkit-", which no bike, school or injury block uses.
export function pages() {
  return TOOLKIT_BLOCKS.flatMap((b) => {
    const html = embedPage(b);
    return ["toolkit", "bike"].map((dir) => ({ path: `/embed/${dir}/${b}`, file: `embed/${dir}/${b}/index.html`, html, sitemap: false }));
  });
}
