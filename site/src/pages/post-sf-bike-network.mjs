// The bike post on sf-works.org, from the same markdown fryanpan.com reads
// (content/posts/sf-bike-network.md), so "one post, two sites" (2026-10-05)
// has both halves. Bryan, 2026-10-07: "I want to see a draft post in
// fryanpan.com ... and then in sf-works.org also."
//
// Each `::sfworks{block="<name>"}` line becomes that block, put together from
// the same parts as its /embed/bike/<name>/ page and fryanpan.com's export
// (src/bike-blocks.mjs), so the three cannot differ.
//
// It is the bike section's front page. Bryan, 2026-10-08: "this post was meant
// to be a replacement for the biking overview page". Its old address,
// /posts/sf-bike-network, sends readers here (post-sf-bike-network-moved.mjs).

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { markdown } from "../content.mjs";
import { footnotes } from "../footnotes.mjs";
import { postCredits, sfwCss } from "../bike-blocks.mjs";
import { sfworksBlocks } from "../sfworks-blocks.mjs";
import { ABOUT_DATA, BIKE_DATA_READ } from "../transportation.mjs";

export const path = "/transportation/bike";
export const file = "transportation/bike/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Improving The Bike Network", line: "How much of the Biking and Rolling Plan we've built so far, and how the city could build it faster.", parent: "section", order: 1 };
// The date the lists show beside this page, the same one its "Data updated" line gives (src/page-dates.mjs).
export const dataUpdated = BIKE_DATA_READ;

const POST = nodePath.join(import.meta.dirname, "..", "..", "content", "posts", "sf-bike-network.md");

export function render() {
  const src = fs.readFileSync(POST, "utf8");
  const [, front = "", body = src] = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/.exec(src) || [];
  const field = (k) => (new RegExp(`^${k}:\\s*"?(.*?)"?\\s*$`, "m").exec(front) || [])[1] || "";
  // GFM footnotes, as fryanpan.com writes them (src/footnotes.mjs): the
  // definitions come out of the body, each `[^id]` becomes a numbered link,
  // and the notes are listed under References after the credits.
  const { text: refs, references } = footnotes(body.replace(/^## References[ \t]*\n/m, ""), { name: "post-sf-bike-network" });
  // Each ::sfworks line becomes its block (src/sfworks-blocks.mjs).
  const { text, used, scripts } = sfworksBlocks(refs, "post-sf-bike-network");
  return page({
    title: field("title"),
    description: field("description"),
    path,
    about: ABOUT_DATA,
    dataUpdated,
    // The blocks' stylesheet keeps wide figures in the column (an embed's
    // frame is not ours to break out of). This page is, so the maps get the
    // overview's width (Bryan, 2026-10-07: "full width map format").
    body: `<style>${sfwCss()}
.post .sfw .fig.wide { width: min(1200px, 100vw - 48px); margin-left: calc(50% - min(600px, 50vw - 24px)); }
.post sup.fn { font-size: 0.75em; line-height: 0; }
.post sup.fn a { text-decoration: none; padding: 0 1px; }
.post .fn-list { font-size: 0.9em; }
.post .fn-list li { margin-bottom: 0.4em; }</style>
<article class="post">
<h1>${field("title")}</h1>
${markdown(text)}
${markdown(postCredits([...new Set(used)]))}
${references}
</article>
${scripts.join("\n")}`,
  });
}
