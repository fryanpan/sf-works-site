// The SF transport survey figure as a standalone page, /embed/surveys/<block>/,
// for the board doc's `::sfworks{block="survey-<x>"}` lines
// (src/survey-blocks.mjs explains the contract). Kept out of the sitemap and
// marked noindex: no reader should land on one from a search.

import { SURVEY_BLOCKS, embedPage } from "../survey-blocks.mjs";

export const path = "/embed/surveys";
export const file = "embed/surveys/index.html";
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
<title>Survey Figures for Embedding — SF Works</title>
<style>body { font-family: system-ui, sans-serif; margin: 24px 16px; background: #ffffff; color: #15181c; }</style>
</head>
<body>
<h1>Survey figures for embedding</h1>
<ul>
${SURVEY_BLOCKS.map((b) => `<li><a href="/embed/surveys/${b}/">${b}</a></li>`).join("\n")}
</ul>
</body>
</html>
`;
}

// Each block also answers at /embed/bike/<block>/, because the board maps the
// one `sfworks` directive to a single path template, /embed/bike/{block}/
// (src/pages/embed-school.mjs). Their names start with "survey-", which no
// other block uses.
export function pages() {
  return SURVEY_BLOCKS.flatMap((b) => {
    const html = embedPage(b);
    return ["surveys", "bike"].map((dir) => ({ path: `/embed/${dir}/${b}`, file: `embed/${dir}/${b}/index.html`, html, sitemap: false }));
  });
}
