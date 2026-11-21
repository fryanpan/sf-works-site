// The Proposition Review Meeting at /deliberation/: one voter reviews each California and San Francisco measure on
// the November 3, 2026 ballot in about five minutes, with a live AI guide.
//
// Bryan, 2026-11-10 (docs/decisions/deliberation.md): "Public SF Works.  All propositions we've researched ."
// The page and the measures' briefs are written into data/deliberation/ by the deliberation package's
// build-public.mjs, which scrubs them; this module publishes them as they are. The guide is a separate Worker at
// guide.sf-works.org with its own spend guards; while it is off, the page works without it.
//
// /deliberation/ is a site page, with the site's masthead and nav, that frames the tool. The tool itself is at
// /deliberation/app/, out of the sitemap and marked noindex, so its own stylesheet and fixed bottom band keep working
// unchanged inside the frame. The frame fills the window below the masthead, so the site page itself doesn't scroll.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";

const DIR = nodePath.join(import.meta.dirname, "..", "..", "data", "deliberation");

export const path = "/deliberation";
export const file = "deliberation/index.html";

const CSS = `<style>
.delib-head h1 { font-size: clamp(1.4rem, 4vw, 1.8rem); margin: 0 0 4px; }
.delib-head p { margin: 0 0 10px; color: var(--muted); font-size: 0.95rem; }
.delib-frame { display: block; border: 0; width: min(1100px, 100vw - 16px); margin-left: calc(50% - min(550px, 50vw - 8px));
  height: calc(100vh - var(--delib-top, 170px)); height: calc(100dvh - var(--delib-top, 170px)); min-height: 420px; background: #f7f8fa; }
.wrap:has(.delib-frame) { padding-bottom: 0; }
/* On a phone the tool needs the height: the heading is kept for screen readers only and the note shrinks to one line. */
@media (max-width: 640px) {
  .delib-head h1 { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .delib-head p { font-size: 0.8rem; margin: 0 0 6px; }
  .delib-head .long { display: none; }
}
</style>`;

// The frame's height: the window less what sits above the frame.
const SCRIPT = `<script>
(function () {
  var f = document.querySelector(".delib-frame");
  if (!f) return;
  function fit() { document.documentElement.style.setProperty("--delib-top", Math.ceil(f.getBoundingClientRect().top + window.scrollY) + "px"); }
  fit(); window.addEventListener("resize", fit);
})();
</script>`;

export function render() {
  const body = `${CSS}
<div class="delib-head">
  <h1>Proposition Review Meeting</h1>
  <p>The November 3, 2026 election is over, so this is for practice and reflection.<span class="long"> Review each measure's pros and cons and record where you stand.</span></p>
</div>
<iframe class="delib-frame" src="/deliberation/app/" title="Proposition Review Meeting"></iframe>
${SCRIPT}`;
  return page({
    title: "Proposition Review Meeting",
    description: "Review each California and San Francisco measure from the November 3, 2026 ballot in about five minutes: what it does, the strongest points on each side, and where you stand.",
    path,
    body,
  });
}

// The tool itself at /deliberation/app/, and every measure's brief and the list the picker reads at
// /deliberation/briefs/. None is a page to land on from a search.
export function pages() {
  const briefs = nodePath.join(DIR, "briefs");
  return [
    { path: `${path}/app`, file: "deliberation/app/index.html", html: fs.readFileSync(nodePath.join(DIR, "page.html"), "utf8"), sitemap: false },
    ...fs.readdirSync(briefs).filter((f) => f.endsWith(".json")).sort().map((f) => ({
      path: `${path}/briefs/${f}`,
      file: `deliberation/briefs/${f}`,
      html: fs.readFileSync(nodePath.join(briefs, f)),
      sitemap: false,
    })),
  ];
}
