// The street-arrangement carousel's markup, styles and script for the Street Safety dashboard: seven sketches of how
// the 2022 to 2024 pedestrian-violation crashes were laid out, one card at a time (arrangements.js steps it). The
// years are in the card's heading, because the map's own headline beside it follows the Years filter and these don't.
//
// The cards are a fixed snapshot in site/data/street-safety/arrangements/ (its README says where they came from):
// manifest.json gives each card's title, people, killed, verdict and reason, the legend and the verdict colours, and
// every figure and word on the card comes from it.
import fs from "node:fs";
import path from "node:path";

const HERE = import.meta.dirname;
const DIR = path.resolve(HERE, "..", "..", "data", "street-safety", "arrangements");
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/** The snapshot's manifest: { cards, legend, verdict_colors, data_read, total }. */
export function arrangements() {
  return JSON.parse(fs.readFileSync(path.join(DIR, "manifest.json"), "utf8"));
}

// A card's sketch, inline: sized by the stylesheet, hidden from screen readers (the title and reason say it), and its
// arrowhead ids prefixed with the card's id so seven sketches on one page don't share ids.
function sketch(card) {
  return fs.readFileSync(path.join(DIR, card.svg), "utf8").trim()
    .replace(/^<svg([^>]*)>/, (m, a) => `<svg${a.replace(/\s(width|height|role|aria-label)="[^"]*"/g, "")} class="ss-arr-sk" aria-hidden="true" focusable="false">`)
    .replace(/id="(h-[0-9a-f]+)"/g, `id="arr-${card.id}-$1"`).replace(/url\(#(h-[0-9a-f]+)\)/g, `url(#arr-${card.id}-$1)`);
}
const readDate = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const SWATCH = { "dashed outline": (c) => `background:#fff;border:1.5px dashed ${c}` };

/** The carousel card, hidden until the cause chart has Pedestrian violation picked. */
export function arrangementsHTML() {
  const A = arrangements(), n = A.cards.length;
  const slide = (c, i) => `<div class="ss-arr-slide${i ? "" : " on"}" data-arr-slide role="group" aria-roledescription="slide" aria-label="${i + 1} of ${n}">
      ${sketch(c)}
      <div class="ss-arr-txt"><p class="ss-arr-t">${esc(c.title)}</p>
        <p class="ss-arr-n"><b>${c.count}</b> ${c.count === 1 ? "person" : "people"}, ${c.killed ? `${c.killed} of them killed` : "none killed"}</p>
        <p class="ss-arr-v" style="--c:${esc(A.verdict_colors[c.verdict])}"><b>Daylighting: ${esc(c.verdict)}</b> ${esc(c.reason)}</p></div>
    </div>`;
  const key = A.legend.map((l) => `<span><i style="${(SWATCH[l.style] || ((c) => `background:${c}`))(esc(l.color))}"></i>${esc(l.label)}</span>`).join("");
  return `<section class="sm-ov ss-arr" data-arr hidden tabindex="0" role="group" aria-roledescription="carousel" aria-label="Street arrangements in pedestrian violation crashes">
    <div class="ss-arr-head"><p class="ss-arr-h">Street Arrangements, 2022 to 2024</p>
      <button type="button" data-arr-prev aria-label="Previous street arrangement"><wa-icon library="system" name="chevron-left" variant="solid"></wa-icon></button>
      <span class="ss-arr-pos" data-arr-pos aria-live="polite">1 of ${n}</span>
      <button type="button" data-arr-next aria-label="Next street arrangement"><wa-icon library="system" name="chevron-right" variant="solid"></wa-icon></button></div>
    <div class="ss-arr-slides">${A.cards.map(slide).join("\n")}</div>
    <p class="ss-arr-key">${key}</p>
    <p class="ss-arr-src">People killed or severely injured in crashes police blamed on a pedestrian violation. Verdicts are our inference. Data read ${readDate(A.data_read)}.</p>
  </section>`;
}

/** The card's styles. It sits left of the corner chart on a laptop and above the key and chart on a phone. */
export const ARR_CSS = `<style>
.ss .ss-arr { right: 310px; bottom: 26px; width: 380px; padding: 6px 10px 8px; z-index: 4; color: var(--sm-ink); }
.ss .ss-arr:focus-visible { outline: 2px solid var(--sm-highlight, #2f7d76); outline-offset: 1px; }
/* A crash card takes the chart's place; the carousel steps aside with it. */
.ss:has(.sm-cardslot:not(:empty)) .ss-arr { display: none; }
.ss-arr-head { display: flex; align-items: center; gap: 2px; margin: 0 0 4px; }
.ss-arr-head .ss-arr-h { flex: 1; margin: 0; font: inherit; font-weight: 600; font-size: 0.82rem; }
.ss-arr-head button { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; font: inherit; color: var(--sm-ink); background: #fff; border: 1px solid var(--rule, #dfe3e9); border-radius: 6px; cursor: pointer; }
.ss-arr-head button:hover { background: var(--raised, #f4f6f8); }
.ss-arr-head button:focus-visible { outline: 2px solid var(--sm-highlight, #2f7d76); outline-offset: 1px; }
.ss-arr-pos { flex: none; min-width: 3.6em; text-align: center; color: var(--sm-muted); font-variant-numeric: tabular-nums; }
/* Every slide in one cell: the card is as tall as its longest slide, so a step moves nothing. */
.ss-arr-slides { display: grid; touch-action: pan-y; }
.ss-arr-slide { grid-area: 1 / 1; display: grid; grid-template-columns: 168px minmax(0, 1fr); gap: 10px; align-items: start; visibility: hidden; }
.ss-arr-slide.on { visibility: visible; }
.ss-arr-sk { display: block; width: 100%; height: auto; border: 1px solid var(--rule, #dfe3e9); border-radius: 4px; }
.ss-arr-txt .ss-arr-t { margin: 0 0 2px; font: inherit; font-weight: 600; font-size: 0.84rem; line-height: 1.25; }
.ss-arr-txt p { margin: 0; }
.ss-arr-n { font-size: 0.8rem; }
.ss-arr-n b { font-family: Archivo, sans-serif; font-size: 1.05rem; }
.ss-arr-v { margin-top: 4px !important; padding: 2px 0 2px 7px; border-left: 4px solid var(--c); font-size: 0.76rem; line-height: 1.3; }
.ss-arr-v b { display: block; font-size: 0.82rem; }
.ss-arr-key { display: flex; flex-wrap: wrap; gap: 0 10px; margin: 6px 0 0; font-size: 0.7rem; line-height: 1.5; }
.ss-arr-key span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.ss-arr-key i { display: inline-block; box-sizing: border-box; width: 12px; height: 9px; border-radius: 2px; }
.ss-arr-src { margin: 3px 0 0; font-size: 0.7rem; line-height: 1.3; color: var(--sm-muted); }
/* A narrower laptop or a tablet: the card sits above the key, not beside it. */
@media (min-width: 761px) and (max-width: 1340px) { .ss .ss-arr { bottom: 104px; } }
@media (min-width: 761px) and (max-width: 1000px) { .ss .ss-arr { right: 10px; bottom: auto; top: 96px; width: 340px; } .ss-arr-slide { grid-template-columns: 130px minmax(0, 1fr); } }
@media (pointer: coarse) and (min-width: 700px) { .ss-arr-head button { width: 44px; height: 44px; } }
/* A phone: one strip across the map above the key and the chart, under a quarter of the screen. */
@media (max-width: 760px) {
  .ss .ss-arr { left: 6px; right: 6px; bottom: calc(20% + 12px); width: auto; padding: 4px 8px 6px; }
  .ss-arr-head { margin-bottom: 2px; }
  .ss-arr-head button { width: 44px; height: 44px; }
  .ss-arr-head .ss-arr-h { line-height: 1.2; }
  .ss-arr-v b { font-size: 0.76rem; }
  .ss-arr-slide { grid-template-columns: 112px minmax(0, 1fr); gap: 8px; }
  .ss-arr-txt .ss-arr-t { font-size: 0.78rem; }
  .ss-arr-n { font-size: 0.74rem; }
  .ss-arr-n b { font-size: 0.9rem; }
  .ss-arr-v { margin-top: 2px !important; font-size: 0.7rem; line-height: 1.25; }
  .ss-arr-key { margin-top: 4px; font-size: 0.64rem; gap: 0 8px; }
  .ss-arr-src { margin-top: 1px; font-size: 0.64rem; line-height: 1.25; }
}
</style>`;

/** The browser script (defines SafetyArrangements). */
export const ARR_SCRIPT = `<script>\n${fs.readFileSync(path.join(HERE, "arrangements.js"), "utf8")}\n</script>`;
