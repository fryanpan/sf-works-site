// One layout for every page on the site.
//
// The pages report what the city did against what it said it would do, so the
// design is documentary: San Francisco's own signage face for headings, the US
// government design system's face for text, and colour spent only where a number
// carries a verdict. Everything else is ink on paper.

import { pathShown } from "./features.mjs";
import { esc } from "./html.mjs";

export const SITE = "SF Works";

// The canonical origin. Link previews and the sitemap need absolute URLs, and a
// relative one silently produces a broken card rather than no card.
export const ORIGIN = "https://sf-works.org";

// Where a page's list of the pages under it goes (src/directory.mjs). The build
// fills it, or empties it on a page with nothing under it (scripts/site-files.mjs).
export const DIRECTORY_MARK = "<!--sfworks:directory-->";
// Where the breadcrumb's page steps go, filled by src/directory.mjs fillCrumbs.
// It carries the page's own path, so a family page's steps follow its address.
export const CRUMBS_MARK = /<!--sfworks:crumbs ([^ ]*)-->/;
const crumbsMark = (path) => `<!--sfworks:crumbs ${path}-->`;

// A breadcrumb step that opens a menu, of [value, label, checked, attrs] items.
export const menu = (label, items, attrs = "") => `<sl-dropdown>
        <sl-button slot="trigger" size="small" variant="text" caret><span${attrs}>${esc(label)}</span></sl-button>
        <sl-menu>${items.map(([v, l, on, a = ""]) => `<sl-menu-item type="checkbox" value="${v}"${on ? " checked" : ""}${a}>${esc(l)}</sl-menu-item>`).join("")}</sl-menu>
      </sl-dropdown>`;
// A menu step goes inside its own breadcrumb item; a link step already is one.
export const crumbItem = (x) => (x.startsWith("<sl-dropdown") ? `<sl-breadcrumb-item>${x}</sl-breadcrumb-item>` : x);

// Shoelace, the component library behind the breadcrumb, loaded from its CDN build.
const SHOELACE = "https://cdn.jsdelivr.net/npm/@shoelace-style/shoelace@2.20.1/cdn";
export const FONTS =
  "https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&" +
  "family=Public+Sans:ital,wght@0,400;0,600;1,400&display=swap";

export const CSS = `
:root {
  --paper: #ffffff;
  --raised: #f4f6f8;
  --ink: #15181c;
  --muted: #59626f;
  --rule: #dfe3e9;
  --accent: #b3202c;
  --accent-soft: #fbeced;
  --ok: #1c6b57;
  --ok-soft: #e8f3f0;
  --measure: 68ch;

  /* An ordered three-step scale, sampled from one sequential teal ramp rather
     than picked hue by hue, because the categories it colours have an order:
     the plan was built, the plan was half built, nothing was built. Darkest is
     best, so the ink follows the achievement.

     Lightness carries the order, which is what makes it readable with any of
     the common colour vision deficiencies — protanopia, deuteranopia and
     tritanopia all preserve a luminance ramp, and none of them preserves a
     red-against-green pair. Red stays for links and emphasis and is never a
     category. */
  --seq-3: #2f7d76;
  --seq-2: #c8a25e;
  --seq-1: #9c5f3c;
  --seq-3-soft: #e6f0ef;
  --seq-2-soft: #f7f0e2;
  --seq-1-soft: #f4eae3;

  /* Two greys off the ramp, for categories outside the three-step scale. */
  --grey-light: #b3b8bf;
  --grey-dark: #3d4450;
}
/* Light only. Bryan, 2026-09-23: "Don't support dark mode -- let's optimize
   for light mode only with white background. The colors in dark mode for the
   maps are unreadable." The page ignores the device setting. */

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Public Sans", ui-sans-serif, system-ui, -apple-system, sans-serif;
  font-size: 17px;
  line-height: 1.6;
  -webkit-text-size-adjust: 100%;
}

.wrap {
  max-width: var(--measure);
  margin: 0 auto;
  padding: 0 16px 96px;
}

h1, h2, h3 {
  font-family: Archivo, "Public Sans", ui-sans-serif, system-ui, sans-serif;
  font-weight: 700;
  letter-spacing: -0.015em;
  text-wrap: balance;
  line-height: 1.15;
}
h1 { font-size: clamp(2rem, 6vw, 2.75rem); margin: 0 0 12px; }
h2 { font-size: clamp(1.35rem, 4vw, 1.6rem); margin: 48px 0 12px; }
h3 { font-size: 1.1rem; margin: 32px 0 8px; }
/* Section links (anchorHeadings): the # shows on hover or focus, and faintly on touch screens. */
h2[id], h3[id] { scroll-margin-top: 16px; }
.h-anchor { margin-left: 0.3em; color: var(--muted); text-decoration: none; font-weight: 400; opacity: 0; }
h2:hover .h-anchor, h3:hover .h-anchor, .h-anchor:focus { opacity: 1; }
@media (hover: none) { .h-anchor { opacity: 0.45; } }

/* A heading that is also a link gets the accent, not an underline — the rule
   under a 1.6rem word reads as damage rather than as an affordance. */
h2 a, h3 a { text-decoration: none; color: var(--accent); }
h2 a:hover, h3 a:hover { text-decoration: underline; text-decoration-thickness: 2px; }

p, ul, ol { margin: 0 0 16px; }
a { color: inherit; text-underline-offset: 2px; text-decoration-color: var(--muted); }
a:hover { text-decoration-color: var(--accent); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }

/* Masthead: the site name, and which page you are on. */
.masthead {
  display: flex;
  gap: 16px;
  align-items: baseline;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--rule);
  padding: 20px 0 12px;
  margin-bottom: 32px;
}
.masthead a.brand {
  white-space: nowrap;
  font-family: Archivo, sans-serif;
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  text-decoration: none;
}
/* The breadcrumb, in the site's type. Until Shoelace has loaded, the menus stay hidden so their items
   don't flash as a row of text. */
.crumbs { font-size: 0.92rem; min-width: 0; }
.crumbs::part(base) { flex-wrap: wrap; row-gap: 2px; }
.crumbs sl-breadcrumb-item::part(label) { font-family: inherit; font-size: 0.92rem; color: var(--muted); }
.crumbs sl-breadcrumb-item:first-child::part(label) { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.05rem; color: var(--ink); }
.crumbs sl-breadcrumb-item:last-of-type sl-button::part(label) { color: var(--ink); font-weight: 600; }
.crumbs sl-button::part(base) { font-size: 0.92rem; color: var(--muted); padding: 0 2px; height: auto; line-height: 1.6; }
.crumbs sl-button::part(label) { padding: 0 2px; }
.crumbs sl-menu-item::part(label) { font-size: 0.92rem; }
.crumbs :not(:defined) sl-menu, sl-menu:not(:defined) { display: none; }
sl-breadcrumb.crumbs:not(:defined) { display: flex; flex-wrap: wrap; gap: 2px 8px; align-items: baseline; color: var(--muted); }
sl-breadcrumb.crumbs:not(:defined) sl-breadcrumb-item + sl-breadcrumb-item::before { content: "›"; margin-right: 8px; }
sl-breadcrumb.crumbs:not(:defined) sl-breadcrumb-item:first-child { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.05rem; color: var(--ink); }
.masthead nav { display: flex; gap: 14px; font-size: 0.92rem; color: var(--muted); }
.masthead nav a[aria-current="page"] { color: var(--ink); font-weight: 600; }

/* ---- Share button ----------------------------------------------------------
   Every page and every view of a page has an address, and the address is on
   the page rather than only in the browser bar: a reader on a phone is usually
   inside an app's web view, where there is no bar to copy from. One button at
   the top right; pressing it copies the link and opens a popover showing what
   was copied. */
.masthead .share-wrap { margin-left: auto; position: relative; align-self: center; display: flex; gap: 8px; }
/* The front page marks each tool as a prototype; the mark is quiet, not a link colour. */
h3 a .tag { color: var(--muted); background: var(--raised); margin-left: 6px; }
/* On a phone the button stays on the brand's line as an icon alone; the
   label returns where there is room for it. */
@media (max-width: 520px) {
  .masthead { flex-wrap: nowrap; align-items: center; }
  .masthead nav { flex-wrap: wrap; row-gap: 2px; }
  .share-btn .label { display: none; }
  .share-btn { padding: 6px 6px; }
  .masthead .share-wrap { gap: 4px; }
  /* The breadcrumb on one line at 390px: Shoelace's separators carry 8px either side
     (--sl-spacing-x-small), so they close up, and the steps' type steps down a little. A trail of
     four steps or more also drops its second, the section, which the brand step reaches from the
     home page: "SF Works > Muni > About This Data" fits where four steps wrapped to two lines. */
  .crumbs sl-breadcrumb-item:nth-child(2):nth-last-child(n+3) { display: none; }
  .crumbs { --sl-spacing-x-small: 3px; }
  .crumbs sl-breadcrumb-item::part(separator) { margin: 0 3px; }
  .crumbs sl-breadcrumb-item::part(label), .crumbs sl-button::part(base) { font-size: 0.86rem; }
  .crumbs sl-breadcrumb-item:first-child::part(label) { font-size: 0.98rem; }
  .crumbs sl-button::part(label) { padding: 0 1px; }
  .crumbs sl-button::part(caret) { margin-left: 0; }
}
.share-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ink);
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
}
.share-btn:hover { border-color: var(--accent); }
a.share-btn { text-decoration: none; }
.share-btn svg { width: 15px; height: 15px; display: block; }
.share-pop {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  z-index: 20;
  width: min(360px, calc(100vw - 32px));
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  font-size: 0.85rem;
  color: var(--muted);
}
.share-pop[hidden] { display: none; }
.share-pop .status { display: block; margin-bottom: 8px; font-weight: 600; color: var(--ink); }
.share-pop .status[data-done="1"] { color: var(--ok); }
.share-pop code {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85em;
  color: var(--ink);
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 6px 8px;
  overflow-wrap: anywhere;
  user-select: all;
  -webkit-user-select: all;
}

.lede { font-size: 1.15rem; color: var(--muted); margin-bottom: 8px; }

/* The one number a page is about. */
.verdict {
  font-family: Archivo, sans-serif;
  font-size: clamp(2.5rem, 11vw, 4rem);
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
  margin: 32px 0 8px;
}
.verdict-note { color: var(--muted); font-size: 0.95rem; margin-top: 4px; }

table { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
th, td {
  text-align: left;
  padding: 9px 12px 9px 0;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
th { font-weight: 600; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; padding-right: 20px; }
td:last-child, th:last-child { padding-right: 0; }
td.date, th.date { white-space: nowrap; }

/* A row-group header names the group; the uppercase column-label treatment
   makes it shout and wrap. */
th[scope="rowgroup"] {
  text-transform: none;
  letter-spacing: 0;
  font-size: 0.95rem;
  color: var(--ink);
  padding-right: 16px;
}
.scroll { overflow-x: auto; margin: 0 0 20px; }

.tag {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  padding: 2px 7px;
  border-radius: 3px;
  white-space: nowrap;
}
/* A pass, for a two-way verdict rather than a rung on the three-step scale. */
.tag-ok { background: var(--ok-soft); color: var(--ok); }

/* Where a figure came from and when it was read. Every page carries one. */
.freshness {
  border-top: 1px solid var(--rule);
  margin-top: 56px;
  padding-top: 20px;
  font-size: 0.88rem;
  color: var(--muted);
}
.freshness h2 { font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 10px; color: var(--muted); }
.freshness h3 { font-size: 0.95rem; margin: 14px 0 4px; }
.freshness ul { list-style: none; padding: 0; }
.freshness li { padding: 4px 0; }
.freshness h2 + ul, .freshness h2 + h3 { margin-top: 0; }
.freshness ul + h2 { margin-top: 22px; }
.freshness .for { color: var(--ink); }

/* The date past which the page cannot speak, stated once, near the top.
   Distinct from the query date: a dataset read today may only carry data
   through some earlier day, and that earlier day is what bounds the finding. */
.valid-through {
  border: 1px solid var(--rule);
  border-left: 3px solid var(--seq-2);
  background: var(--raised);
  padding: 12px 16px;
  margin: 0 0 24px;
  font-size: 0.93rem;
  color: var(--ink);
}
.data-updated { color: var(--muted); font-size: 0.85rem; margin: -4px 0 16px; }
/* A folder page's versions (src/page-versions.mjs): an older version says so in a band. */
.version-line.older { color: var(--ink); font-size: 0.9rem; background: var(--raised); border-left: 3px solid var(--rule); padding: 8px 12px; margin: 0 0 16px; }
ol.versions li { margin: 4px 0; }
.valid-through strong { color: var(--ink); }
.valid-through .why { color: var(--muted); display: block; margin-top: 4px; }

.caveat {
  background: var(--raised);
  border-left: 3px solid var(--rule);
  padding: 14px 16px;
  margin: 0 0 20px;
  font-size: 0.95rem;
}
.caveat p:last-child { margin-bottom: 0; }

/* A long list the page does not lead with. The default marker is a tiny
   triangle that reads as decoration rather than a control, so the summary is
   given a button's affordances: a hit area, a hover state and a focus ring. */
details {
  margin: 0 0 20px;
  border: 1px solid var(--rule);
  border-radius: 4px;
}
details > summary {
  cursor: pointer;
  padding: 12px 16px;
  font-weight: 600;
  color: var(--accent);
  list-style-position: inside;
}
details > summary:hover { background: var(--raised); }
details > summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
details[open] > summary { border-bottom: 1px solid var(--rule); }
details > .scroll { margin: 0; }
details > .scroll table { margin: 0; }

/* Statute quoted verbatim. Set apart so the reader can see where the
   quotation stops and the page starts talking again. */
blockquote {
  margin: 0 0 20px;
  padding: 14px 18px;
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
}
blockquote p { margin: 0; font-size: 1.02rem; }

/* A report's last line: the link to how it was built. */
/* The list of pages under this one (src/directory.mjs): a title link and one
   line each, in the article's own type, so it reads as part of the page. */
.dir h2 { margin-top: 40px; }
.dir-list { list-style: none; padding: 0; margin: 0 0 16px; }
.dir-list li { margin: 0 0 12px; }
.dir-list > li > a { font-weight: 600; color: var(--accent); text-decoration: none; }
.dir-list > li > a:hover { text-decoration: underline; }
.dir-line { display: block; color: var(--muted); font-size: 0.95rem; line-height: 1.45; }
/* When the page's data was read, or the page last changed (src/page-dates.mjs). */
.dir-date { display: block; color: var(--muted); font-size: 0.8rem; line-height: 1.45; }
.dir-dated { margin-top: -12px; }
.dir-list .dir-list { margin: 10px 0 0 16px; padding-left: 12px; border-left: 2px solid var(--rule); }
.dir-list .dir-list li { margin-bottom: 8px; }
/* On the home page a section's list sits under the report it belongs to. */
.dir-under { margin: -4px 0 24px; padding-left: 14px; border-left: 2px solid var(--rule); }
.dir-under > .dir-list > li > a { color: var(--ink); text-decoration: underline; }
.dir-list .dir-list a { font-weight: 600; color: var(--ink); text-decoration: underline; }
.about-link { margin: 28px 0 0; padding-top: 12px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 0.92rem; }

/* ---- Headline figures -------------------------------------------------------
   One figure per tile, coloured with a step of the sequential ramp. */
.progress-figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0 8px; }
.progress-figures div { padding: 12px 14px; border-radius: 6px; background: var(--raised); }
.progress-figures b { font-family: Archivo, sans-serif; font-size: 1.7rem; display: block; font-variant-numeric: tabular-nums; line-height: 1.1; }
.progress-figures .upgrade b { color: var(--seq-3); }
.progress-figures .new b { color: var(--seq-2); }
.progress-figures span { font-size: 0.86rem; color: var(--muted); }

/* ---- Map -----------------------------------------------------------------
   Every map is drawn by MapLibre through sfMap (src/maplibre.mjs). */
.mapbox { margin: 0 0 20px; position: relative; }
.map-readout {
  margin: 8px 0 0;
  font-size: 0.9rem;
  color: var(--muted);
  min-height: 1.6em;
}
.map-readout strong { color: var(--ink); }

.map-key {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  font-size: 0.86rem;
  color: var(--muted);
}
.map-key li { display: flex; align-items: center; gap: 7px; }
/* A legend in groups, one line each with its heading (Bryan, 2026-09-29:
   "Group the bike infra ones into one group and the resident ones into
   another group (e.g. one per line) with a heading"). */
.map-keys { display: grid; gap: 4px; margin: 10px 0 0; }
.map-key-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; }
.map-key-row .map-key, .hmap.hero .map-key-row .map-key { margin: 0; }
.map-key-h { flex: none; min-width: 5.5em; font-family: Archivo, sans-serif; font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.map-key .num { color: var(--ink); font-variant-numeric: tabular-nums; }
.map-key .key {
  width: 22px;
  height: 0;
  border-top: 3px solid var(--rule);
  flex: none;
}

/* ---- The bike network since 2015 --------------------------------------------
   Two line charts on one frame and an animated map. The network total and the
   all-ages part are two steps of the same ordered scale (all-ages is the
   better subset), so all-ages takes the darkest step and the total the middle
   one; residents, schools and branches are three unordered things, so they take
   the three steps with a dash pattern each, and lightness still separates them
   for every colour deficiency. */
.fig { margin: 0 0 8px; }
/* Every chart is drawn by Observable Plot at build time (src/plot.mjs). Its
   axes and unstyled labels take the muted text colour; each mark sets its own
   colour from the --seq-* steps above. */
.plot-chart { width: 100%; height: auto; display: block; margin: 12px 0 6px; overflow: visible; color: var(--muted); font-family: inherit; font-size: 13px; }
/* On a phone the chart is 360px wide, so an 11px label in the 520px drawing
   renders at 7px. Draw the labels larger there. */
@media (max-width: 480px) { .plot-chart .note { font-size: 15px; } }
.progress-figures .lib b { color: var(--seq-1); }

/* The year heading, the counts, the map, the controls and the key fit one
   screen at iPad sizes (Bryan, 2026-09-22): the map's height is capped by the
   viewport less the room the other four need, and the width follows from the
   drawing's aspect ratio. */
.hmap { margin: 0 0 20px; scroll-margin-top: 8px; }
.hmap svg {
  display: block; width: auto; max-width: 100%; height: auto;
  max-height: max(240px, calc(100dvh - 200px));
  aspect-ratio: 1000 / 1044;
  margin: 0 auto; background: var(--raised); border-radius: 4px;
}
/* The opening of the overview (Bryan, 2026-09-23: "start from the map ...
   more narrow vertically to fit in the fold ... at the top of the map,
   highlight the key metrics"): the map on the left, the year and the
   residents share beside it, sized so headline, lede and map fit one screen. */
/* The opening map breaks out of the text column (Bryan, 2026-09-23: "while
   the text stays in the narrow column for readability, the map can expand
   ... as wide as 1200px"). The year, the residents share, the counts and the
   Play control run in a row above it; the key sits below. The city is as tall
   as it is wide, so the map's height sets its width: as tall as the fold
   allows, and never taller than 720px. */
.fig.wide { width: min(1200px, 100vw - 48px); margin-left: calc(50% - min(600px, 50vw - 24px)); }
.hmap.hero { display: block; }
/* The title (Bryan, 2026-09-23: "Put this title into the map"), Play, the
   year slider and the residents share sit over the empty water in
   the map's top-left corner, inside the left label margin (Bryan,
   2026-09-23: "Move the play controls into the top left corner of the map
   where there's empty space. Move the 85% of residents right underneath it
   but keep it compact"). On a phone the margin is gone, so they return to the
   flow above the map. */
.hmap-stage { position: relative; }
.hmap-panel { position: absolute; left: 1.5%; top: 2%; width: 21%; min-width: 200px; display: flex; flex-direction: column; gap: 10px; }
/* Title and Play centred above the map; the headline share sits alone on the
   map, well apart from the controls (Bryan, 2026-09-24: "the 72% is floating
   and looks like it's as closely associated with the Play button as the text
   below"; "try centering the heading and the play + slider widget"). */
.hmap-top { display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; margin: 0 0 4px; }
/* Bryan, 2026-09-24: "keep this in the map", so the title and player sit over
   the map's top edge on a laptop and above it only on a phone. */
.hmap-stage > .hmap-top { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 2; width: min(480px, 60%); }
@media (max-width: 700px) { .hmap-stage > .hmap-top { position: static; transform: none; width: auto; } }
.hmap-title { font-family: Archivo, sans-serif; font-weight: 700; font-size: 1.6rem; line-height: 1.1; margin: 0; letter-spacing: -0.01em; text-wrap: balance; }
.hmap-title output { font-variant-numeric: tabular-nums; color: var(--seq-3); }
.hmap-metric { display: flex; flex-direction: column; gap: 2px; margin: 0; }
.hmap-metric b { font-family: Archivo, sans-serif; font-weight: 700; font-size: 2.4rem; line-height: 1; color: var(--seq-3); font-variant-numeric: tabular-nums; }
.hmap-metric > span { font-size: 0.92rem; color: var(--ink); line-height: 1.3; }
.hmap.hero .hmap-controls { margin: 0; width: min(460px, 100%); }
/* Bryan, 2026-09-29: "I didn't realize I could click on these." */
.hmap-hint { margin: 4px auto 0; width: fit-content; padding: 1px 6px; border-radius: 3px; font-size: 0.8rem; color: var(--muted); background: color-mix(in srgb, var(--paper) 88%, transparent); }
/* Zoomed in (bike-history.mjs sets .zoomed from the MapLibre zoom), the
   project labels beside the city are hidden. */
.hmap.zoomed svg { touch-action: none; cursor: grab; }
.hmap svg { touch-action: pan-y; }
.hmap.zoomed svg .plabel { display: none !important; }
.hmap-canvas { position: relative; }
.hmap-panel { z-index: 2; }
/* Zoomed in, the map under the title and the headline share is busy, so
   they sit on a veil of the page colour. */
@media (min-width: 701px) {
  .hmap.zoomed .hmap-stage > .hmap-top, .hmap.zoomed .hmap-panel { background: color-mix(in srgb, var(--paper) 88%, transparent); box-shadow: 0 0 0 8px color-mix(in srgb, var(--paper) 88%, transparent); border-radius: 2px; }
}
.hmap .plabel { cursor: pointer; }
.hmap .plabel.picked circle { fill: var(--seq-1); }
.proj-card { position: absolute; z-index: 5; width: min(320px, calc(100% - 16px)); max-height: calc(100% - 16px); overflow: auto; margin: 0; padding: 12px 40px 10px 14px; border: 1px solid var(--rule); border-left: 4px solid var(--seq-1); border-radius: 8px; background: var(--paper); box-shadow: 0 6px 24px rgba(31, 36, 33, 0.18); font-size: 0.88rem; line-height: 1.4; }
.proj-card[hidden] { display: none; }
@media (max-width: 700px) { .proj-card { position: static; width: auto; max-height: none; margin-top: 8px; box-shadow: none; } }
.proj-card p { margin: 4px 0; }
.proj-card .proj-name { font-family: Archivo, sans-serif; font-size: 1.05rem; margin: 0 0 4px; }
.proj-card .proj-when { color: var(--muted); font-size: 0.84rem; }
.proj-card .proj-summary { margin: 6px 0 8px; }
.proj-table { border-collapse: collapse; width: 100%; margin: 4px 0 6px; font-size: 0.84rem; }
.proj-table th, .proj-table td { text-align: left; vertical-align: top; padding: 4px 0; border-top: 1px solid var(--rule); }
.proj-card .proj-table th { width: 48%; font-family: inherit; font-size: inherit; font-weight: 600; text-transform: none; letter-spacing: 0; color: var(--ink); padding-right: 10px; }
.proj-table td { font-variant-numeric: tabular-nums; }
.proj-card .proj-more { font-size: 0.84rem; }
.proj-card .proj-photo { margin: 6px 0; }
.proj-card .proj-photo[hidden] { display: none; }
.proj-card .proj-photo img { display: block; width: 100%; aspect-ratio: 3 / 1; object-fit: cover; border-radius: 4px; background: var(--rule); }
.proj-close { position: absolute; top: 6px; right: 8px; font: inherit; font-size: 1.3rem; line-height: 1; border: 0; background: none; color: var(--muted); cursor: pointer; padding: 4px 6px; }
.hmap.hero .map-key { justify-content: flex-start; }
.hmap.hero svg { display: block; width: 100%; height: auto; margin: 0; }
.hmap.hero .map-key { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 10px 0 0; font-size: 0.8rem; line-height: 1.3; }
.hmap.hero .map-key li .key { display: inline-block; vertical-align: middle; margin-right: 7px; }
/* Block, not flex: as flex items the words around a <span> lose their spaces. */
.hmap.hero .map-key li { display: block; }
.hmap svg .plabel { opacity: 0; transition: opacity 0.3s; }
.hmap svg .plabel.now { opacity: 1; }
/* A label not on show takes no taps, so a tap on empty map opens nothing
   (Bryan, 2026-09-29: "tapping in the middle of nowhere still brings up
   projects from other years"). */
.hmap svg .plabel:not(.now) { pointer-events: none; }
.hmap svg .plabel circle { fill: var(--paper); stroke: var(--ink); stroke-width: 2; }
.hmap svg .plabel line { stroke: var(--muted); stroke-width: 1.2; opacity: 0.7; }
.hmap svg .plabel text { font-family: Archivo, sans-serif; font-weight: 500; font-size: 18px; fill: var(--ink); }
.hmap svg .plabel.pp text { font-size: 54px; font-weight: 600; }
.hmap svg .plabel.pp circle { stroke-width: 6; r: 12; }
.hmap svg .plabel.pp line { stroke-width: 4; }
.hmap svg .plabel.pp { display: none; }
@media (max-width: 700px) {
  .hmap svg .plabel.pw { display: none; }
  .hmap svg .plabel.pp { display: inline; }
  .hmap.hero svg { aspect-ratio: 1920 / 1044; }
}
@media (max-width: 700px) {
  .hmap-title { font-size: 1.45rem; }
  .hmap.hero .hmap-controls { width: 100%; }
  .hmap-panel { position: static; width: auto; min-width: 0; margin: 22px 0 10px; }
  .hmap-metric { flex-direction: row; align-items: flex-start; gap: 10px; }
  .hmap-metric b { font-size: 2.1rem; margin-top: -0.12em; }
}
.hmap .map-key { margin-top: 6px; gap: 2px 14px; font-size: 0.8rem; }
.hmap svg .plabel.planned text { fill: var(--seq-3); }
/* A label for a removal (tools/bike-network/bike-removals.py) is grey. */
.hmap svg .plabel.removal text { fill: var(--muted); }
.hmap svg .plabel.removal circle { stroke: var(--muted); }
.hmap-controls { display: flex; gap: 12px; align-items: center; margin: 8px 0 2px; }
.hmap-play {
  font: inherit; font-weight: 600; font-size: 0.9rem; min-width: 5em;
  color: var(--paper); background: var(--ink); border: 1px solid var(--ink); border-radius: 4px; padding: 6px 12px; cursor: pointer;
}
.hmap-play:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.hmap-step {
  font: inherit; font-weight: 700; font-size: 1.2rem; line-height: 1; width: 36px; height: 32px; flex: 0 0 auto;
  color: var(--ink); background: var(--paper); border: 1px solid var(--ink); border-radius: 4px; cursor: pointer;
}
.hmap-step:disabled { opacity: 0.35; cursor: default; }
.hmap-step:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.hmap-controls input[type="range"] { flex: 1; accent-color: var(--seq-3); min-width: 0; }
/* Its width is held in every year, so showing it moves nothing. */
.hmap-when { flex: 0 0 4.6em; font-size: 0.85rem; font-weight: 600; color: var(--seq-3); visibility: hidden; text-align: left; }
.hmap.future .hmap-when { visibility: visible; }
.map-key .key.aa { border-top-color: var(--seq-3); }
.map-key .key.aa.planned { border-top-style: dashed; margin-left: 4px; }
.map-key .key.blk { width: 10px; height: 10px; border: 0; border-radius: 50%; background: var(--seq-2); }
.map-key .key.blk.off { background: var(--muted); opacity: 0.3; }
.map-key .key.blk.sm { width: 5px; height: 5px; margin-right: 4px; }
.hmap svg .plabel.unnamed { cursor: default; }
.hmap svg .plabel.unnamed text { font-style: italic; fill: var(--muted); }
.hmap svg .plabel.unnamed circle { stroke: var(--muted); }
.map-key .key.sch { width: 10px; height: 10px; border: 2px solid var(--ink); border-radius: 50%; background: var(--seq-1); }
.map-key .key.lib { width: 10px; height: 10px; border: 2px solid var(--ink); border-radius: 0; background: var(--seq-1); margin-left: 4px; }
.map-key .key.off { width: 10px; height: 10px; border: 2px solid var(--muted); border-radius: 50%; background: var(--paper); }

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
`;

// The labels are the home page's section headings (content/home.md), so the
// breadcrumb and the home page call each section by one name.
// Mobility lands on the Transportation front page (Bryan, 2026-11-19: "Mobility
// should now land on a Transportation front page that outlines the top level
// goal and then links to the main reports and dashboards").
export const NAV = [
  { href: "/transportation", label: "Mobility" },
  { href: "/housing", label: "Homes" },
  { href: "/permits", label: "Permits" },
  { href: "/grand-juries", label: "Grand Juries" },
  { href: "/daily-trips", label: "Daily Trips" },
].filter((n) => pathShown(n.href));

/**
 * @param {object} o
 * @param {string} o.title     Page name, two to four words. Becomes the tab title.
 * @param {string} o.description One sentence, for search results and link previews.
 * @param {string} o.path      This page's path, so the nav can mark it current.
 * @param {string} o.body      The page's HTML.
 * @param {{label: string, href?: string, read: string, through?: string, group?: string}[]} [o.sources]
 * @param {string} [o.sourcesNote] HTML for a page whose sources are listed on another page
 *        What the page drew on and when it was read. `through` is the last date
 *        that source can speak to, which is not the same as the date it was
 *        read. Rendered at the foot of every page, because a figure with no date
 *        on it reads as current and may not be.
 * @param {{items: [string, string][], current: string}} [o.views]
 *        The views inside one page, as [id, label], shown as the breadcrumb's
 *        last step. Picking one fires "sfworks:view" with the id, and the page
 *        sets the label through [data-crumb-view] when its view changes.
 * @param {{href: string, label: string}} [o.about]
 *        The report's About page, linked as the page's last line. About pages
 *        are not in the nav (Bryan, 2026-10-12: "Move the about pages
 *        underneath each report as a link from the end of the report").
 * @param {{href: string, label: string}} [o.topLink]
 *        A link beside Share in the masthead, for a full-screen tool with no
 *        page end to carry its About link (the Street Safety Map).
 * @param {boolean} [o.directory]
 *        false leaves out the "More On" list of the pages under this one, for a
 *        tool whose breadcrumb menu already links its pages (the Muni dashboard).
 * @param {string} [o.shareState]
 *        The query string of the view being rendered, e.g. "?show=past", so
 *        the address printed on the page reproduces what is on screen.
 * @param {{date: string, limitedBy: string, why: string}} [o.validThrough]
 *        The date past which nothing on this page is evidence, set by whichever
 *        input stops first, and which input that is. Stated once near the top:
 *        a reader deciding whether to act on a page needs to know how far
 *        forward it reaches before they read any of it.
 */
// The workspace's point-and-comment widget, on the STAGING build only.
//
// The fleet rule says no widget markup in a tracked file, because the measured
// failure was a reviewer's name committed into a template on a public repo,
// and a build that failed without the tag. Neither can happen here: the tag is
// emitted only when the build is run with WIDGET_DOC_ID set, which only the
// staging job in .github/workflows/deploy.yml does; it carries no user
// attribute, so the widget resolves the reader from their own browser; and a
// build with the variable unset is byte-for-byte the production page. Bryan
// asked for this on 2026-09-22: staging carries the widget behind a Cloudflare
// Access login, production carries neither.
function widget() {
  const docId = process.env.WIDGET_DOC_ID;
  const workspaceId = process.env.WIDGET_WORKSPACE_ID;
  if (!docId || !workspaceId) return "";
  const server = (process.env.WIDGET_SERVER || "https://workspaces.fryanpan.com").replace(/\/$/, "");
  return `<claude-feedback-widget workspace-id="${workspaceId}" doc-id="${docId}"></claude-feedback-widget>
<script src="${server}/widget.iife.js"></script>`;
}

// Plausible analytics, on the PRODUCTION build only. Bryan supplied the
// snippet on 2026-09-22. The build emits it only when PLAUSIBLE_SCRIPT names
// the script URL, which only the production job in
// .github/workflows/deploy.yml sets, so staging visits by the people
// reviewing pages never count as readers. Plausible sets no cookies, so the
// page needs no consent banner for it.
// Userback feedback, on the PRODUCTION build only (Bryan, 2026-09-29), emitted
// when USERBACK_TOKEN is set, which only the production job does; staging has
// the workspace widget instead. The widget's own floating button is turned off
// (trigger_type "api"): on a phone it sat over the map and its controls. The
// reader opens it from the Feedback button beside Share, which the masthead
// already has room for at every width. Only the token is set: the site has no
// logged-in users, so no user_data.
function feedbackButton() {
  if (!process.env.USERBACK_TOKEN) return "";
  return `<button type="button" class="share-btn" data-feedback-open>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span class="label">Feedback</span>
      </button>`;
}

function feedback() {
  const token = process.env.USERBACK_TOKEN;
  if (!token) return "";
  return `<script>
  window.Userback = window.Userback || {};
  Userback.access_token = ${JSON.stringify(token)};
  Userback.widget_settings = { trigger_type: "api" };
  (function(d) {
    var s = d.createElement("script"); s.async = true; s.src = "https://static.userback.io/widget/v1.js"; (d.head || d.body).appendChild(s);
  })(document);
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-feedback-open]")) return;
    if (window.Userback && typeof Userback.open === "function") Userback.open();
  });
</script>`;
}

// Sentry error tracking, on the PRODUCTION build only (Bryan approved it on the
// board, 2026-11-24). Emitted when SENTRY_DSN is set, which only the production
// job in .github/workflows/deploy.yml does. The DSN is public by Sentry's
// design. The errors-only bundle carries no session replay and no tracing, and
// sendDefaultPii is off, so Sentry gets the error and the page's address and
// nothing that names the reader. The hash pins the exact file the CDN served.
export const SENTRY_BUNDLE = {
  src: "https://browser.sentry-cdn.com/11.17.0/bundle.min.js",
  integrity: "sha384-hDIKvXIZjqlgYU4Xw3A4xx3aRaGTz2YtgxtGBBLxy+FJ5H1+w4+X/3NfA9+jsgwx",
};

export function errorTracking(dsn = process.env.SENTRY_DSN) {
  if (!dsn) return "";
  return `<script src="${SENTRY_BUNDLE.src}" integrity="${SENTRY_BUNDLE.integrity}" crossorigin="anonymous"></script>
<script>
  if (window.Sentry) Sentry.init({ dsn: ${JSON.stringify(dsn)}, sendDefaultPii: false, environment: "production" });
</script>`;
}

function analytics() {
  const src = process.env.PLAUSIBLE_SCRIPT;
  if (!src) return "";
  return `<!-- Privacy-friendly analytics by Plausible -->
<script async src="${src}"></script>
<script>
  window.plausible=window.plausible||function(){(plausible.q=plausible.q||[]).push(arguments)},plausible.init=plausible.init||function(i){plausible.o=i||{}};
  plausible.init()
</script>`;
}

// ---- Credits and sources, gathered at the end ------------------------------
//
// Bryan, 2026-10-01: "On all pages, move the photo credits and data sources to
// the end, with one list for each. The credits really break up the article."
//
// A page marks each credit or source where the figure it belongs to is built,
// so it stays next to the code that knows what it backs, and the layout lifts
// it out of the article:
//
//   <ul class="cite" data-for="Repaving map" data-how="/transportation/bike/about#since-plan">
//     <li><a href="https://data.sf.gov/d/78va-8dhi">City pavement records</a></li>
//   </ul>
//   <ul class="credit" data-for="Off-street paths photo"><li>…</li></ul>
//
// `data-for` names the figure ("|" separates several), and the optional
// `data-how` links the method on About the Data. One source cited by three
// figures is listed once, naming all three. Items are matched by their first
// link (or their text when they have none). Two different wordings of one
// source are both kept, so no link and no qualifier is ever dropped; the build
// fails if a link in the article's marks is missing from the lists.
const NOTE_LIST = /<ul class="(cite|credit)"([^>]*)>([\s\S]*?)<\/ul>/g;
const attr = (attrs, name) => {
  const m = new RegExp(`\\b${name}="([^"]*)"`).exec(attrs);
  return m ? m[1] : "";
};
const hrefsIn = (html) => [...html.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
const textOf = (html) => html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
const normKey = (h) => h.replace("data.sfgov.org", "data.sf.gov").replace(/\/$/, "");
const itemKey = (html) => {
  const h = hrefsIn(html)[0];
  return h ? normKey(h) : textOf(html).toLowerCase();
};

function mergeInto(list, html, fors, group = "") {
  const key = itemKey(html);
  const had = list.find((x) => x.key === key);
  if (!had) {
    list.push({ key, html, fors: [...fors], group });
    return;
  }
  for (const f of fors) if (!had.fors.includes(f)) had.fors.push(f);
  const a = textOf(had.html), b = textOf(html);
  if (a === b || a.includes(b)) return;
  if (b.includes(a)) had.html = html;
  else had.html = `${had.html}; ${html}`;
}

// Every plain section heading gets an id from its text and a # link to
// itself, so a reader can link to one section (Bryan, 2026-10-22, wanting to
// send the repaving section of the bike page). Headings with a class are page
// furniture (map titles, form headings) and are left alone.
export function anchorHeadings(html) {
  const used = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));
  // Script, style and template contents are code, not headings: split them out first.
  return html.split(/(<(script|style|template)\b[\s\S]*?<\/\2>)/i).map((part, i) => (i % 3 ? part : part.replace(/<(h[23])((?:\s+id="[^"]*")?)>([\s\S]*?)<\/\1>/g, (all, tag, idAttr, inner) => {
    let id = (/id="([^"]*)"/.exec(idAttr) || [])[1];
    if (!id) {
      const base = inner.replace(/<[^>]+>/g, "").replace(/&amp;/g, " and ").replace(/&[#a-z0-9]+;|['\u2019]/gi, "")
        .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      if (!base) return all;
      id = base;
      for (let n = 2; used.has(id); n++) id = `${base}-${n}`;
      used.add(id);
    }
    return `<${tag} id="${id}">${inner}<a class="h-anchor" href="#${id}" aria-label="Link to this section">#</a></${tag}>`;
  }))).filter((part, i) => i % 3 !== 2).join("");
}

export function gatherNotes(body) {
  const cites = [], credits = [], hows = [];
  const marked = new Set();
  const stripped = body.replace(NOTE_LIST, (_, kind, attrs, inner) => {
    const fors = attr(attrs, "data-for").split("|").map((s) => s.trim()).filter(Boolean);
    const how = attr(attrs, "data-how");
    const group = attr(attrs, "data-group");
    if (how && fors.length && !hows.some((h) => h.href === how)) hows.push({ href: how, label: fors[0] });
    for (const m of inner.matchAll(/<li>([\s\S]*?)<\/li>/g)) {
      const html = m[1].trim();
      if (!html) continue;
      hrefsIn(html).forEach((h) => marked.add(h));
      mergeInto(kind === "cite" ? cites : credits, html, fors, group);
    }
    return "";
  });
  const listed = new Set([...cites, ...credits].flatMap((x) => hrefsIn(x.html)));
  const lost = [...marked].filter((h) => !listed.has(h));
  if (lost.length) throw new Error(`layout: credits or sources lost in gathering: ${lost.join(", ")}`);
  return { body: stripped, cites, credits, hows };
}

const joinWords = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs.join(""));
// "Connection map, explorer and goal chart": a later label is lower-cased
// unless it carries a name ("Housing Element table", "Slow Streets photo").
const midLabel = (s) => (/[A-Z]/.test(s.slice(1)) ? s : s[0].toLowerCase() + s.slice(1));
const forLabel = (fors) => (fors.length ? `<span class="for">${joinWords(fors.map((f, i) => (i ? midLabel(f) : f)))}:</span> ` : "");

export function page({
  title,
  description,
  path,
  body,
  sources = [],
  sourcesNote = "",
  validThrough = null,
  dataUpdated = null,
  views = null,
  about = null,
  directory = true,
  shareState = "",
  topLink = null,
}) {
  const fullTitle = title === SITE || title.startsWith(SITE + " ") ? title : `${title} — ${SITE}`;
  // A tool split across several pages keeps its masthead entry lit on every
  // one of them, so the reader can see which tool they are inside before they
  // read which part of it.
  const inSection = (href) => path === href || path.startsWith(`${href}/`);
  const nav = NAV.map(
    (n) =>
      `<a href="${n.href}"${inSection(n.href) ? ' aria-current="page"' : ""}>${n.label}</a>`,
  ).join("");

  // Inside a section the masthead is one breadcrumb, site › section › page › view, and a step with
  // siblings opens a menu of them (Bryan, 2026-10-13: "All of the nav stuff up top takes up too much room.
  // Can we bring in a component library and use breadcrumbs instead?"). Shoelace draws it. The home
  // page and posts, in no section, keep the plain nav.
  // A section is matched by its first path segment, so /transportation/muni sits in Mobility.
  // The steps between the section and the view are the pages above this one in the home page's list
  // (src/directory.mjs). Only the build knows every listing, so this leaves CRUMBS_MARK and
  // scripts/site-files.mjs fills it through fillCrumbs: one list, read by both.
  const top = (h) => h.split("/")[1];
  const section = NAV.find((n) => top(n.href) === top(path));
  const steps = section
    ? [
        NAV.length > 1
          ? menu(section.label, NAV.map((n) => [n.href, n.label, n === section]))
          : `<sl-breadcrumb-item href="${section.href}">${esc(section.label)}</sl-breadcrumb-item>`,
        crumbsMark(path),
        views && menu(
          (views.items.find(([k]) => k === views.current) || views.items[0])[1],
          views.items.map(([k, l]) => [`#${k}`, l, k === views.current, ` data-view="${k}"`]),
          " data-crumb-view",
        ),
      ].filter(Boolean).map(crumbItem)
    : null;
  const crumbs = steps
    ? `<sl-breadcrumb class="crumbs" label="Where you are"><sl-breadcrumb-item href="/">${SITE}</sl-breadcrumb-item>${steps.join("")}</sl-breadcrumb>`
    : "";
  const crumbScript = steps
    ? `<script>
document.querySelector(".crumbs").addEventListener("sl-select", function (e) {
  var v = e.detail.item.value;
  if (v.charAt(0) === "#") window.dispatchEvent(new CustomEvent("sfworks:view", { detail: v.slice(1) }));
  else if (v !== location.pathname.replace(/[/]$/, "")) location.href = v;
});
</script>`
    : "";

  // Every page and every view of a page has an address, and it is printed on
  // the page rather than left in the browser bar: a reader on a phone is
  // usually inside an app's web view, where there is no bar to copy from.
  // `shareState` is the query string for the view being rendered, so the
  // address shown is the one that reproduces what is on screen.
  const shareUrl = `${ORIGIN}${path}${shareState}`;
  const share = `<div class="share-wrap">
      ${topLink ? `<a class="share-btn" href="${topLink.href}" aria-label="${topLink.label}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg><span class="label">${topLink.label}</span></a>` : ""}
      ${feedbackButton()}
      <button type="button" class="share-btn" data-share-open aria-expanded="false" aria-controls="share-pop">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
        <span class="label">Share</span>
      </button>
      <div class="share-pop" id="share-pop" role="dialog" aria-label="Share this page" hidden>
        <span class="status" data-share-status>Link to this page</span>
        <code data-share-url>${shareUrl}</code>
      </div>
    </div>`;

  // Pressing the button copies the address and opens the popover showing it.
  // Where the clipboard is unavailable the popover still opens, says so, and
  // the address is one tap to select, which is the version that always works.
  const shareScript = `<script>
(function () {
  var code = document.querySelector("[data-share-url]");
  var btn = document.querySelector("[data-share-open]");
  var pop = document.getElementById("share-pop");
  var status = document.querySelector("[data-share-status]");
  if (!code || !btn || !pop || !status) return;
  function close() { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); }
  function open() {
    pop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    status.textContent = "Link to this page";
    delete status.dataset.done;
    if (!navigator.clipboard) { status.textContent = "Select the link to copy it"; return; }
    navigator.clipboard.writeText(code.textContent).then(function () {
      status.textContent = "Copied to your clipboard";
      status.dataset.done = "1";
    }, function () {
      status.textContent = "Select the link to copy it";
    });
  }
  btn.addEventListener("click", function () { pop.hidden ? open() : close(); });
  document.addEventListener("click", function (e) {
    if (!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) close();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  // A view selected in the page changes the address it offers, so what the
  // reader copies is always what the reader is looking at.
  window.addEventListener("sfworks:state", function (e) {
    code.textContent = ${JSON.stringify(ORIGIN + path)} + (e.detail || "");
  });
})();
</script>`;

  const longDate = (iso) =>
    new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });

  const validBand = validThrough
    ? `<p class="valid-through"><strong>${esc(validThrough.label || "Figures current through")} ${longDate(validThrough.date)}.</strong>
      <span class="why">${esc(validThrough.why)}</span></p>`
    : "";

  // The band goes after the finding, so the reader meets the numbers before
  // the caveat (guide 1.1): before the first section heading when the page has
  // one, else after the lede, else after the <h1>.
  const withBand = (html) => {
    if (!validBand) return html;
    const firstH2 = html.search(/<h2(?![^>]*\bclass=)/);
    const afterLede = html.indexOf("</p>", html.indexOf('class="lede"'));
    const cut = firstH2 !== -1
      ? firstH2
      : html.includes('class="lede"') && afterLede !== -1
        ? afterLede + 4
        : html.indexOf("</h1>") + 5;
    if (cut < 5) return validBand + html;
    return html.slice(0, cut) + "\n" + validBand + "\n" + html.slice(cut);
  };

  // The end of the page: one list of photo credits and one of data sources
  // (gatherNotes above), then where the method is explained. A page's own
  // `sources` list, grouped when its entries carry a group (Bryan,
  // 2026-09-23: "organize the data into different categories"), joins the
  // data sources; an article mark that cites one of its links names its figure
  // on that entry rather than listing the source twice.
  // pipeline/README.md, update intervals (Bryan, 2026-11-09): "each report that has data that gets updated should
  // have up top a very short blurb that just says when the data was last updated". `dataUpdated` is the date the
  // page's data was last read with a change (the newest of the dates passed), set right under the <h1>; the
  // scheduled refresh (pipeline/site-refresh/run.sh) checks it daily, and an unchanged source keeps its date.
  const updatedIso = [].concat(dataUpdated || []).filter(Boolean).map((d) => String(d).slice(0, 10)).sort().pop();
  const withUpdated = (html) => {
    if (!updatedIso) return html;
    const line = `<p class="data-updated">Data updated ${longDate(updatedIso)}</p>`;
    const h1 = html.indexOf("</h1>");
    return h1 === -1 ? line + html : html.slice(0, h1 + 5) + "\n" + line + html.slice(h1 + 5);
  };
  const notes = gatherNotes(withUpdated(withBand(anchorHeadings(body))));
  const own = sources.map((s) => ({ ...s, fors: s.backs ? [s.backs] : [] }));
  const cites = notes.cites.filter((c) => {
    const s = own.find((o) => o.href && normKey(o.href) === c.key);
    if (!s) return true;
    for (const f of c.fors) if (!s.fors.includes(f)) s.fors.push(f);
    return false;
  });
  const item = (s) => {
    const label = String(s.label), cut = label.indexOf(" — ");
    const name = cut === -1 ? label : label.slice(0, cut), use = cut === -1 ? "" : label.slice(cut + 3);
    const linked = s.href ? `<a href="${esc(s.href)}">${esc(name)}</a>` : esc(name);
    const binds = validThrough && s.through === validThrough.date;
    const through = s.through
      ? `, covers through <span class="${binds ? "binds" : ""}">${s.through}</span>${binds ? " (the limit on this page)" : ""}`
      : "";
    return `<li>${forLabel(s.fors)}${linked}, read ${s.read}${through}.${use ? ` ${esc(use[0].toUpperCase() + use.slice(1))}.` : ""}</li>`;
  };
  // Sources that back exactly the same figures share one line, so a figure
  // drawn from four datasets reads as one entry rather than four.
  const gathered = (xs) => {
    const lines = [];
    for (const x of xs) {
      const k = x.fors.join("|");
      const line = lines.find((l) => l.k === k);
      if (line) line.parts.push(x.html);
      else lines.push({ k, fors: x.fors, parts: [x.html] });
    }
    return lines.map((l) => `<li>${forLabel(l.fors)}${l.parts.join("; ")}</li>`).join("");
  };
  const groups = [...new Set(own.map((s) => s.group).filter(Boolean))];
  const joined = (g) => cites.filter((c) => c.group === g);
  const ownList = !own.length
    ? ""
    : groups.length
      ? groups.map((g) => `<h3>${g}</h3><ul>${gathered(joined(g))}${own.filter((s) => s.group === g).map(item).join("")}</ul>`).join("") +
        (own.some((s) => !s.group) ? `<h3>Other</h3><ul>${own.filter((s) => !s.group).map(item).join("")}</ul>` : "")
      : `<ul>${own.map(item).join("")}</ul>`;
  const how = notes.hows.length
    ? `<p class="how">How we worked out the ${joinWords(notes.hows.map((h) => `<a href="${h.href}">${h.label.toLowerCase()}</a>`))} is on <a href="${notes.hows[0].href.split("#")[0]}#sources">About the Data</a>.</p>`
    : sourcesNote
      ? `<p>${sourcesNote}</p>`
      : "";
  const throughNote = own.some((s) => s.through)
    ? `<p><em>Read</em> is when we last checked a source; <em>covers through</em> is the last day it has anything to say about, and that's what bounds the page.</p>`
    : "";
  const ownGroups = new Set(own.map((s) => s.group).filter(Boolean));
  const loose = cites.filter((c) => !ownGroups.has(c.group));
  const hasSources = cites.length || own.length;
  const freshness = notes.credits.length || hasSources || how
    ? `<section class="freshness" id="sources">
      ${notes.credits.length ? `<h2>Photo Credits</h2><ul class="credits">${gathered(notes.credits)}</ul>` : ""}
      ${hasSources ? `<h2>Data Sources</h2>${loose.length ? `<ul class="cites">${gathered(loose)}</ul>` : ""}${ownList}` : ""}
      ${how}
      ${throughNote}
    </section>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(fullTitle)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${ORIGIN}${path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="${SITE}">
<meta property="og:url" content="${ORIGIN}${path}">
<meta property="og:title" content="${esc(fullTitle)}">
<meta property="og:description" content="${esc(description)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="${esc(fullTitle)}">
<meta name="twitter:description" content="${esc(description)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='13' font-size='13'>&#127963;</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="${FONTS}">${crumbs ? `
<link rel="stylesheet" href="${SHOELACE}/themes/light.css">
<script type="module" src="${SHOELACE}/shoelace-autoloader.js"></script>` : ""}
<style>${CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    ${crumbs || `<a class="brand" href="/">${SITE}</a>
    <nav>${nav}</nav>`}
    ${share}
  </header>
  <main>
<div class="page-body">
${notes.body}
${directory ? DIRECTORY_MARK : ""}
${about ? `<p class="about-link">How we built this: <a href="${about.href}">${about.label}</a></p>` : ""}
</div>
  </main>
  ${freshness}
</div>
${shareScript}
${crumbScript}
${widget()}
${errorTracking()}
${analytics()}
${feedback()}
</body>
</html>
`;
}
