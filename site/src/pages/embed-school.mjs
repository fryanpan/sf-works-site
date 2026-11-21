// The school-hurt maps as standalone pages, /embed/school/<block>/, for the
// board doc's `::sfworks{block="school-hurt-<x>"}` lines (src/school-hurt-blocks.mjs
// explains the contract). Kept out of the sitemap and marked noindex: no reader
// should land on one from a search.

import { HURT_BLOCKS, embedPage } from "../school-hurt-blocks.mjs";

export const path = "/embed/school";
export const file = "embed/school/index.html";
// Kept out of the sitemap by the build (scripts/build.mjs skips `asset`).
export const asset = true;
export const sitemap = false;

export function render() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>School Maps for Embedding — SF Works</title>
<style>body { font-family: system-ui, sans-serif; margin: 24px 16px; background: #ffffff; color: #15181c; }</style>
</head>
<body>
<h1>School maps for embedding</h1>
<ul>
${HURT_BLOCKS.map((b) => `<li><a href="/embed/school/${b}/">${b}</a></li>`).join("\n")}
</ul>
</body>
</html>
`;
}

// Each block also answers at /embed/bike/<block>/, because the board maps the
// one `sfworks` directive to a single path template, /embed/bike/{block}/
// (set with set_board_embeds), so the same line works for these blocks too.
// The bike blocks' names never start with "school-hurt-" or "bikeways-".
export function pages() {
  return HURT_BLOCKS.flatMap((b) => {
    const html = embedPage(b);
    return ["school", "bike"].map((dir) => ({ path: `/embed/${dir}/${b}`, file: `embed/${dir}/${b}/index.html`, html, sitemap: false }));
  });
}
