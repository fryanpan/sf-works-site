// The board doc components a site markdown page may carry, drawn at build
// time so a doc written on the board publishes with its charts and maps.
//
//   <PlotChart title="..." data={{...}} marks={[...]} options={{...}} />
//       an Observable Plot chart, drawn to static SVG by buildPlot from
//       plot-spec.mjs, the claude-workspaces copy the board itself draws with,
//       so the chart on the site is the chart on the board. Every prop is a
//       JSON literal, as the board writes them.
//   <Carousel label="...">...</Carousel>
//       the board's slide-through wrapper; here its charts stack, so the page
//       reads in full with no control touched (data-story guidelines).
//   import X from '...'
//       the doc's component import line; dropped.
//   <MapStory map="street-safety"><MapStep state={{...}}>...</MapStep></MapStory>
//       the Street Safety map pinned beside the text, stepping through each
//       step's state as the reader scrolls (src/safety-map/story.mjs).
//   ::scratch{block="<name>"}
//       the board's live figure frame. On the board it frames
//       scratch/embeds/<name>/; here it frames the site's copy of that page,
//       published at /embed/figures/<name>/ (src/doc-embeds.mjs), full width.
//       The frame takes the height the page posts as {type: "sfworks:height"}.
//
// A component the page cannot draw stops the build, naming the page.

import { parseHTML } from "linkedom";
import { Plot } from "./plot.mjs";
import { buildPlot, PLOT_DEFAULT_WIDTH } from "./plot-chart/plot-spec.mjs";
import { esc } from "./html.mjs";
import { embedPath } from "./doc-embeds.mjs";
import { mapStories } from "./safety-map/story.mjs";

const { document } = parseHTML("<!doctype html><html><body></body></html>");

// The text from `open` (a "{" or a quote) to its match, skipping braces inside
// JSON strings. Returns the index just past the closing character.
function balanced(s, i) {
  if (s[i] === '"') {
    for (let j = i + 1; j < s.length; j++) {
      if (s[j] === "\\") j++;
      else if (s[j] === '"') return j + 1;
    }
    return -1;
  }
  let depth = 0;
  let inStr = false;
  for (let j = i; j < s.length; j++) {
    const c = s[j];
    if (inStr) {
      if (c === "\\") j++;
      else if (c === '"') inStr = false;
    } else if (c === '"') inStr = true;
    else if (c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") {
      depth--;
      if (depth === 0) return j + 1;
    }
  }
  return -1;
}

/** The props of one `<PlotChart ... />`, starting just after its name. */
function readProps(s, start, owner) {
  const props = {};
  let i = start;
  for (;;) {
    while (/\s/.test(s[i] ?? "")) i++;
    if (s.startsWith("/>", i)) return { props, end: i + 2 };
    const m = /^([A-Za-z]+)=/.exec(s.slice(i, i + 40));
    if (!m) throw new Error(`${owner}: a <PlotChart> prop near "${s.slice(i, i + 30)}" is not name=value`);
    i += m[0].length;
    const close = balanced(s, i);
    if (close < 0) throw new Error(`${owner}: <PlotChart> prop ${m[1]} never closes`);
    const raw = s.slice(i, close);
    // "text" is a string; {expr} is a JSON literal inside JSX braces.
    props[m[1]] = raw.startsWith('"') ? JSON.parse(raw) : JSON.parse(raw.slice(1, -1));
    i = close;
  }
}

/** One chart as a single line of HTML, so markdown leaves it alone. */
export function plotChartHTML(props, owner) {
  const spec = { data: props.data, marks: props.marks, options: props.options, preset: props.preset };
  let fig;
  try {
    fig = buildPlot(Plot, spec, { document });
  } catch (e) {
    throw new Error(`${owner}: <PlotChart${props.title ? ` "${props.title}"` : ""}> cannot be drawn: ${e.message}`);
  }
  // A static page draws once, at the width the board doc gave the chart, so
  // the chart is never stretched past it (its labels would grow with it) and
  // keeps its proportions as a phone's column narrows below it.
  const svgs = fig.tagName.toLowerCase() === "svg" ? [fig] : [...fig.querySelectorAll("svg")];
  for (const svg of svgs) svg.style.setProperty("max-width", "100%");
  const chart = svgs.at(-1);
  if (chart) {
    chart.style.setProperty("width", "100%");
    chart.style.setProperty("max-width", `min(100%, ${props.options?.width ?? PLOT_DEFAULT_WIDTH}px)`);
    chart.style.setProperty("height", "auto");
  }
  if (props.title) fig.setAttribute?.("aria-label", props.title);
  const title = props.title ? `<figcaption class="chart-title">${esc(props.title)}</figcaption>` : "";
  const sub = props.subtitle ? `<p class="chart-sub">${esc(props.subtitle)}</p>` : "";
  const note = props.note ? `<p class="chart-note">${esc(props.note)}</p>` : "";
  return `<figure class="md-chart">${title}${sub}${fig.outerHTML}${note}</figure>`.replace(/\n+/g, " ");
}

const SCRATCH = /^::scratch\{block="([\w-]+)"\}[ \t]*$/gm;

/**
 * Draw every component in `text`. `embeds` lists the block names that exist,
 * so a misspelt one stops the build. `local`, {names, path(name)}, lists the
 * figure pages a folder page keeps in its own embeds/ folder, which win. Returns the text and the blocks framed
 * (the page then carries the script that sizes them, and the build publishes
 * those figure pages).
 */
export function mdComponents(text, owner, { embeds = [], local = null } = {}) {
  let out = text.replace(/^import\s+\w+\s+from\s+['"][^'"]+['"];?[ \t]*\n/gm, "");
  // Charts first, so a carousel holds single lines of HTML by the time
  // markdown reads it.
  let i;
  while ((i = out.indexOf("<PlotChart")) >= 0) {
    const { props, end } = readProps(out, i + "<PlotChart".length, owner);
    out = out.slice(0, i) + plotChartHTML(props, owner) + out.slice(end);
  }
  out = out
    .replace(/^<Carousel(?:\s+label="([^"]*)")?\s*>[ \t]*$/gm, (_, label) => `<div class="chart-stack"${label ? ` role="group" aria-label="${esc(label)}"` : ""}>`)
    .replace(/^<\/Carousel>[ \t]*$/gm, "</div>");
  const story = mapStories(out, owner);
  out = story.text;
  if (/<[A-Z][A-Za-z]*[\s/>]/.test(out.replace(/`[^`]*`/g, ""))) {
    const name = /<([A-Z][A-Za-z]*)[\s/>]/.exec(out)[1];
    throw new Error(`${owner}: <${name}> is a board component the site does not draw`);
  }
  const framed = [];
  out = out.replace(SCRATCH, (_, name) => {
    // A folder page's own copy, in its embeds/ folder, before the site's shared one.
    if (local?.names.includes(name)) {
      framed.push(name);
      return `<iframe class="md-embed" src="${local.path(name)}/?block=${name}" data-block="${name}" title="${esc(name)}" loading="lazy" style="height:480px"></iframe>`;
    }
    if (!embeds.includes(name)) throw new Error(`${owner}: ::scratch{block="${name}"} has no figure page at site/data/embeds/${name}.html (npm run deploy-docs copies it from scratch/embeds/${name}/)`);
    framed.push(name);
    return `<iframe class="md-embed" src="${embedPath(name)}/?block=${name}" data-block="${name}" title="${esc(name)}" loading="lazy" style="height:480px"></iframe>`;
  });
  return { text: out, framed: [...new Set(framed)], stories: story.stories };
}

// Sizes each frame to the height its page reports.
export const EMBED_SCRIPT = `<script>
window.addEventListener("message", function (e) {
  var d = e.data;
  if (!d || d.type !== "sfworks:height" || !d.block) return;
  document.querySelectorAll('iframe.md-embed[data-block="' + d.block + '"]').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = Math.ceil(d.height) + "px";
  });
});
</script>`;

export const COMPONENT_CSS = `
.md-page .md-chart { margin: 20px 0; }
.md-page .md-chart .chart-title { font-weight: 600; margin: 0 0 6px; }
.md-page .md-chart svg { display: block; }
.md-page .chart-stack .md-chart + .md-chart { margin-top: 28px; }
.md-page iframe.md-embed { display: block; width: 100%; border: 0; margin: 12px 0; }
.md-page img { max-width: 100%; height: auto; }
`;
