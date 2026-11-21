// About the housing data: the caveats ranked, the asks, and how each figure on
// /housing was made. Prose in content/housing-about.html; numbers from the
// housing page module so the two cannot disagree.

import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { SOURCES, data, vars, yearTable, sb423Table } from "./housing.mjs";

export const path = "/housing/about";
export const file = "housing/about/index.html";

const CSS = `<style>
ol.issues, ol.asks { padding-left: 1.6em; }
ol.issues li, ol.asks li { margin: 0 0 14px; }
ol.issues li::marker, ol.asks li::marker { font-weight: 700; color: var(--accent); }
ol.issues .moves { display: block; margin-top: 4px; color: var(--muted); font-size: 0.93rem; }
</style>`;

export function render() {
  return page({
    title: "About the housing data",
    description: "How each figure on the housing page was made, the biggest data issues ranked, and what we ask the city to publish.",
    path,
    validThrough: data.validThrough,
    body: CSS + content("housing-about", { ...vars(), yearTable: yearTable(), sb423Table: sb423Table(data.sb423) }),
    sources: SOURCES,
  });
}
