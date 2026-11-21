// School Trips' third tab, The Public Comment: Bryan's comment to SFMTA on the
// Safe School Connections draft, posted verbatim. Bryan, 2026-10-12: "Can we
// add a tab here for The Public Comment that's a verbatim post of the same
// content we're going to publish to fryanpan.com?"
//
// The words are site/content/ssc-public-comment.md, a copy of his draft, and
// are rendered with marked as they stand. Nothing here edits them; the one
// line above the comment is the only prose of ours on the tab.

import fs from "node:fs";
import nodePath from "node:path";
import { marked } from "marked";

const FILE = nodePath.join(import.meta.dirname, "..", "content", "ssc-public-comment.md");
const DRAFT = "https://www.sfmta.com/safe-school-connections-draft-approach-september-2026";

export const COMMENT_CSS = `<style>
.tr-comment { max-width: 65ch; margin: 8px auto 96px; padding: 0 4px; }
.tr-comment .tr-sent { color: var(--muted); font-size: 0.92rem; margin: 8px 0 24px; }
.tr-comment h1 { font-size: clamp(1.6rem, 5vw, 2.1rem); margin: 36px 0 12px; }
.tr-comment h1:first-of-type { margin-top: 0; }
.tr-comment h2 { font-size: clamp(1.2rem, 4vw, 1.4rem); margin: 32px 0 10px; }
.tr-comment ul ul { margin: 6px 0 6px; }
.tr-comment li { margin: 0 0 6px; }
.tr-comment hr { border: 0; border-top: 1px solid var(--rule); margin: 24px 0; }
/* A third tab makes the row too wide for a phone on one line, so a label may wrap there. */
@media (max-width: 860px) {
}
</style>`;

/** The Public Comment view, a section the tab switcher shows and hides like the others. */
export function commentView() {
  const html = marked.parse(fs.readFileSync(FILE, "utf8"));
  return `<section class="tr-view" id="v-comment" aria-label="The public comment">
<article class="tr-comment">
<p class="tr-sent">Submitted to SFMTA on October 12, 2026, as public comment on the <a href="${DRAFT}">Safe School Connections draft approach</a>.</p>
<p class="tr-sent">See the <a href="#city" data-tab="city">Citywide Scenarios</a>, <a href="#school" data-tab="school">Your School</a>, and <a href="/transportation/school-trips/about">About this Data</a> for more details on how we came up with realistic scenarios below, built on public data from the city, research studies from elsewhere, and existing SFCTA recommendations.</p>
${html}
</article>
</section>`;
}
