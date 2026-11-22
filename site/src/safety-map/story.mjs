// The map story block for a site markdown page: the Street Safety map pinned beside the text, stepping from one
// state to the next as the reader scrolls (Bryan, 2026-11-19: "the same map component in the draft dashboard can be
// embedded in an article in a way where all of the settings in the map can transition from one configuration to
// another to tell a story").
//
//   <MapStory map="street-safety">
//   <MapStep state={{"view": "injuries", "hin": ["2024"]}}>
//
//   One or two sentences of markdown for this step.
//
//   </MapStep>
//   ...
//   </MapStory>
//
// Each step is markdown plus a state object (src/safety-map/state.js); a step's state is laid over the defaults, not
// over the step before, so scrolling back up lands on exactly the same map. Scrollama fires each step as it crosses
// the middle of the screen, and the map's setState does the camera flight and the layer fades. A reader without
// JavaScript or WebGL still reads every step.
//
// The map fills the screen, pinned, and the steps scroll over it in narrow cards (Bryan, 2026-11-19: "Both the story
// and the dashboard have the map take up more of the overall space"): a column on the left on a wide screen, the
// bottom of the screen on a phone, with a full screen of map between one card and the next. The key and its headline
// sit bottom-left on a wide screen, the corner chart bottom-right, and a step may set the chart with `chart: {id}`.
//
// A page with several blocks of one map builds that map once. The first block holds the stage and the later blocks
// an empty frame; as the reader scrolls, the stage moves into the block on screen and shows its step. Five maps on
// the HIN story held 242 MB in headless Chrome against 61 MB for one (the Street Safety map review, 2026-11-19).

import { marked } from "marked";
import { esc } from "../html.mjs";
import { MAP_HEAD } from "../maplibre.mjs";
import { SCRIPT, CSS as MAP_CSS, KIT_HEAD, SCROLLAMA, DATA_URL, CRASHES_URL, CHART_SCRIPT, inlineData } from "./index.mjs";

const MAPS = { "street-safety": { data: DATA_URL, crashes: CRASHES_URL, dashboard: "/transportation/street-safety" } };

// The index just past the "{...}" or "[...]" that opens at i, skipping brackets inside JSON strings, or -1.
function balanced(s, i) {
  let depth = 0, inStr = false;
  for (let j = i; j < s.length; j++) {
    const c = s[j];
    if (inStr) { if (c === "\\") j++; else if (c === '"') inStr = false; }
    else if (c === '"') inStr = true;
    else if (c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") { depth--; if (depth === 0) return j + 1; }
  }
  return -1;
}

/** The steps of one story's inner text, as [{state, html}]. Throws, naming the page, on a step it cannot read. */
export function parseSteps(inner, owner) {
  const steps = [];
  let i = 0;
  for (;;) {
    const at = inner.indexOf("<MapStep", i);
    if (at < 0) break;
    const open = inner.indexOf("state={", at);
    if (open < 0 || open > inner.indexOf(">", at)) throw new Error(`${owner}: a <MapStep> has no state={{...}}`);
    const end = balanced(inner, open + "state=".length);
    if (end < 0) throw new Error(`${owner}: a <MapStep> state never closes`);
    let state;
    try {
      state = JSON.parse(inner.slice(open + "state={".length, end - 1));
    } catch (e) {
      throw new Error(`${owner}: a <MapStep> state is not JSON: ${e.message}`);
    }
    const bodyStart = inner.indexOf(">", end) + 1;
    const close = inner.indexOf("</MapStep>", bodyStart);
    if (close < 0) throw new Error(`${owner}: a <MapStep> never closes`);
    steps.push({ state, md: inner.slice(bodyStart, close).trim() });
    i = close + "</MapStep>".length;
  }
  if (!steps.length) throw new Error(`${owner}: a <MapStory> has no <MapStep>`);
  return steps;
}

const STORY = /^<MapStory\s+map="([\w-]+)"\s*>[ \t]*\n([\s\S]*?)^<\/MapStory>[ \t]*$/gm;

/**
 * Replace every <MapStory> in `text` with its block, one line of HTML so markdown leaves it alone. Returns the text
 * and how many stories it drew (the page then carries the map's scripts once).
 */
export function mapStories(text, owner) {
  let n = 0;
  const staged = new Set();
  const out = text.replace(STORY, (_, name, inner) => {
    const m = MAPS[name];
    if (!m) throw new Error(`${owner}: <MapStory map="${name}"> names no map (known: ${Object.keys(MAPS).join(", ")})`);
    n++;
    const steps = parseSteps(inner, owner).map((s, k) =>
      `<div class="sm-step" data-step="${k}" data-state="${esc(JSON.stringify(s.state))}"><div class="sm-step-card">${marked.parse(s.md)}</div></div>`);
    // The first block of each map carries the stage (the map, its key, chart and card); later blocks an empty frame.
    const stage = staged.has(name) ? "" : `<div class="sm-story-stage"><div class="sm-story-map"></div>` +
      `<div class="sm-ov sm-legend"><div class="sm-key sm-story-key"></div></div>` +
      `<div class="sm-ov sm-chart" data-chart hidden><div class="sm-chart-slot"></div></div><div class="sm-ov sm-cardslot sm-story-card"></div></div>`;
    staged.add(name);
    return `<div class="sm-story" data-story="${name}" data-data="${m.data}" data-crashes="${m.crashes}"><div class="sm-story-graphic sm-stage">${stage}</div>` +
      `<div class="sm-story-steps">${steps.join("")}</div></div>`.replace(/\n+/g, " ");
  });
  return { text: out, stories: n };
}

const STORY_CSS = `<style>
html:has(.sm-story) { overflow-x: clip; }
.sm-story { position: relative; width: 100vw; margin: 24px 0 24px calc(50% - 50vw); }
.sm-story-graphic { position: sticky; top: 0; height: 100vh; height: 100dvh; z-index: 0; }
/* A block's frame waits in a calm grey until the page's one map moves into it. */
.sm-story-graphic { background: var(--raised, #f4f6f8); }
.sm-story-stage, .sm-story-map { position: absolute; inset: 0; }
.sm-story-map .sm-canvas { height: 100%; border-radius: 0; }
.sm-story-steps { position: relative; z-index: 5; margin-top: -100vh; margin-top: -100dvh; padding: 20vh 0 60vh; pointer-events: none; }
.sm-step { min-height: 100vh; display: flex; align-items: center; padding: 0 0 0 max(16px, calc(50vw - 640px)); }
.sm-step:first-child { min-height: 70vh; }
.sm-step-card { pointer-events: auto; width: 340px; max-width: calc(100vw - 32px); box-sizing: border-box; padding: 14px 16px; border: 1px solid var(--rule); border-radius: 8px; background: #fff; box-shadow: 0 2px 14px rgba(20,30,40,0.16); }
/* A step that isn't active fades its text, never its box, so the map and key never show through behind the words. */
.sm-step-card > * { opacity: 0.55; transition: opacity 300ms; }
.sm-step.is-active .sm-step-card { border-color: var(--seq-3); }
.sm-step.is-active .sm-step-card > * { opacity: 1; }
.sm-step-card p { margin: 0 0 8px; }
.sm-step-card p:last-child { margin: 0; }
.sm-story .sm-legend { left: auto; right: 10px; bottom: auto; top: 10px; margin-right: 84px; max-width: 300px; }
.sm-story-graphic:has(.sm-cardslot:not(:empty)) .sm-legend { display: none; }
@media (max-width: 760px) {
  .sm-story-steps { padding: 30vh 0 40vh; }
  .sm-step { min-height: 100vh; align-items: flex-end; padding: 0 12px 16px; }
  .sm-step-card { width: 100%; max-width: none; font-size: 0.92rem; padding: 10px 12px; }
  .sm-story .sm-legend { left: 6px; right: auto; top: 6px; bottom: auto; margin-right: 0; max-width: calc(56% - 8px); }
  .sm-story .sm-legend { padding: 4px 6px; }
  .sm-story .sm-legend .sm-key { font-size: 0.7rem; gap: 0 8px; }
  .sm-story .sm-legend .sm-key img { width: 14px; height: 14px; }
  .sm-story .sm-chart { top: 44px; bottom: auto; right: 6px; width: calc(44% - 4px); }
  .sm-story .sm-cardslot { max-height: 45%; }
  /* On a phone the key and the chart ride in the step's card, under its words, so nothing sits on the map. */
  .sm-story .sm-step-card > .sm-ov { position: relative; inset: auto; width: auto; max-width: none; margin: 8px 0 0; padding: 0; border: 0; border-radius: 0; box-shadow: none; background: transparent; }
  .sm-story .sm-step-card > .sm-chart { max-height: 120px; overflow-y: auto; }
}
@media (prefers-reduced-motion: reduce) { .sm-step-card > * { transition: none; } }
</style>`;

const STORY_SCRIPT = `<script>
(function () {
  // One map per page for each map name: every block of that map shares it, and its stage (the map, key, chart and
  // card) moves into whichever block's frame fills more of the screen. The steps of all the blocks are one list, so
  // sfStep(i) and the scroll steps count across the whole page.
  var groups = {};
  document.querySelectorAll("[data-story]").forEach(function (box) { (groups[box.getAttribute("data-story")] = groups[box.getAttribute("data-story")] || []).push(box); });
  Object.keys(groups).forEach(function (name) {
    var boxes = groups[name], stage = boxes[0].querySelector(".sm-story-stage"), steps = [], boxOf = [];
    if (!stage) return;
    boxes.forEach(function (b, bi) { b.querySelectorAll(".sm-step").forEach(function (s) { steps.push(s); boxOf.push(bi); }); });
    // On a phone a step's crash card would open under the step cards and hide its own buttons, so a phone leaves the
    // card for the reader to open by tapping a person.
    var phone = window.matchMedia("(max-width: 760px)").matches;
    var stateOf = function (el) { var st = JSON.parse(el.getAttribute("data-state")); if (phone) delete st.crash; return st; };
    var ctl = SafetyMap.create(stage.querySelector(".sm-story-map"), { lib: maplibregl, basemap: sfMap, cards: CrashCards, state: SafetyMapState, routes: window.muniRoutes,
      dataUrl: boxes[0].getAttribute("data-data"), crashesUrl: boxes[0].getAttribute("data-crashes"), initial: stateOf(steps[0]), story: true, cooperative: true,
      cardHost: stage.querySelector(".sm-story-card") });
    SafetyOverlay.attach(ctl, { key: stage.querySelector(".sm-story-key"), chart: stage.querySelector("[data-chart]") });
    // On a phone the key and the corner chart leave the map for the active step's card (the map review's rank 3: the
    // chart covered the city's densest blocks); on a wider screen they stay on the map.
    var legend = stage.querySelector(".sm-legend"), chartBox = stage.querySelector("[data-chart]"), active = 0;
    function dock(i) {
      var host = window.matchMedia("(max-width: 760px)").matches ? steps[i].querySelector(".sm-step-card") : stage;
      if (legend.parentNode === host) return;
      var relay = legend.parentNode === stage || host === stage;
      host.appendChild(legend); host.appendChild(chartBox);
      if (relay) window.dispatchEvent(new Event("resize"));   // the chart lays itself out again at its new width
    }
    var here = 0;
    function moveTo(bi) {
      if (bi === here) return;
      boxes[bi].querySelector(".sm-story-graphic").appendChild(stage);
      here = bi;
      var m = ctl.map && ctl.map();
      if (m) m.resize();
    }
    function enter(i) {
      moveTo(boxOf[i]);
      active = i;
      dock(i);
      steps.forEach(function (s, k) { s.classList.toggle("is-active", k === i); });
      ctl.setState(stateOf(steps[i]), { duration: 1400, replace: true });
      // In a card the chart is short and scrolls, so it opens on the bar the step picked.
      if (chartBox.parentNode !== stage) setTimeout(function () {
        var on = chartBox.querySelector(".sm-hit.on");
        chartBox.scrollTop = on ? Math.max(0, on.getBoundingClientRect().top - chartBox.getBoundingClientRect().top + chartBox.scrollTop - 24) : 0;
      }, 300);
    }
    // Between two blocks both frames can be on screen; the map goes to the one showing more of itself, at that
    // block's nearest step, so the reader never scrolls into a block whose map shows another block's step.
    function place() {
      var best = here, most = -1, H = window.innerHeight;
      boxes.forEach(function (b, bi) {
        var r = b.querySelector(".sm-story-graphic").getBoundingClientRect(), v = Math.min(r.bottom, H) - Math.max(r.top, 0);
        if (v > most) { most = v; best = bi; }
      });
      if (best !== here && most > 0) enter(best > here ? boxOf.indexOf(best) : boxOf.lastIndexOf(best));
    }
    boxes.forEach(function (b) { b.sfStory = ctl; b.sfStep = enter; });
    if (!window.scrollama) { enter(0); return; }
    var scroller = scrollama(), raf = 0;
    scroller.setup({ step: steps, offset: window.innerWidth < 760 ? 0.8 : 0.55 }).onStepEnter(function (r) { enter(r.index); });
    if (boxes.length > 1) window.addEventListener("scroll", function () { if (!raf) raf = requestAnimationFrame(function () { raf = 0; place(); }); }, { passive: true });
    window.addEventListener("resize", function () { scroller.resize(); dock(active); });
    ctl.ready.then(function () { window.__ready = 2; }, function () { window.__ready = 2; });
  });
})();
</script>`;

/** What a page with a story carries once: the map library, the kit, Scrollama, the component, and the story's glue. */
export const STORY_HEAD = `${KIT_HEAD}\n${MAP_CSS}\n${STORY_CSS}`;
export const STORY_SCRIPTS = `${MAP_HEAD}\n${SCROLLAMA}\n${inlineData()}\n${SCRIPT}\n${CHART_SCRIPT}\n${STORY_SCRIPT}`;
