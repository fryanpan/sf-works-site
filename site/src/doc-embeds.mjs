// The figure pages a board doc frames with `::scratch{block="<name>"}`, as
// files the site can publish.
//
// On the board, `::scratch{block="nhood-vmt"}` frames scratch/embeds/nhood-vmt/
// index.html, a page one of the embed generators writes (nhood-* from
// scripts/neighborhood-maps-embed.py, intro-* from scripts/intro-trends-embed.py).
// scratch/ is gitignored and never reaches the site, so the site keeps its own
// copy of each figure page here, data/embeds/<name>.html, refreshed from
// scratch/embeds by `npm run deploy-docs` (scripts/deploy-docs.mjs) before it
// builds. A copy is published only when a built page frames it
// (src/md-pages.mjs, pageAssets), at /embed/figures/<name>/, so a figure
// waiting here for an unpublished doc goes nowhere.
//
// A map page carries the basemap setting its generator ran with. The build
// puts in the site's own (src/maplibre.mjs, BASEMAP), so the maps get the
// site's Google monochrome tiles wherever the site has its key, and no key is
// ever stored in these files.

import fs from "node:fs";
import nodePath from "node:path";
import { BASEMAP } from "./maplibre.mjs";

export const EMBEDS = nodePath.join(import.meta.dirname, "..", "data", "embeds");

/** The address a figure is published at. */
export const embedPath = (name) => `/embed/figures/${name}`;

/** The block names there are figure pages for. */
export const embedNames = () =>
  fs.existsSync(EMBEDS)
    ? fs.readdirSync(EMBEDS).filter((f) => f.endsWith(".html")).map((f) => f.slice(0, -5)).sort()
    : [];

const BASEMAP_LITERAL = /\bBASEMAP = \{[^\n]*?\}(?=, GLYPHS = )/;

/**
 * One figure page's HTML, with the site's basemap in place of the one it was
 * written with. `dir` is where it is kept: data/embeds, or a folder page's own
 * embeds/ (src/page-versions.mjs), so a published version keeps its own copy.
 */
export function embedHTML(name, dir = EMBEDS) {
  const html = fs.readFileSync(nodePath.join(dir, `${name}.html`), "utf8");
  if (!BASEMAP_LITERAL.test(html)) return html;
  return html.replace(BASEMAP_LITERAL, `BASEMAP = ${JSON.stringify(BASEMAP)}`);
}
