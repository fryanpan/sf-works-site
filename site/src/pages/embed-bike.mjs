// The bike overview's figures as standalone pages, /embed/bike/<block>/, for
// fryanpan.com to iframe beside the same post (src/bike-blocks.mjs explains
// the contract). Also the post's canonical markdown, served raw at
// /content/posts/sf-bike-network.md so the other site reads the same words.
//
// None of these is a page a reader should land on from a search, so all are
// kept out of the sitemap and carry noindex. They are not feature-flagged:
// fryanpan.com needs them in production.

import fs from "node:fs";
import nodePath from "node:path";
import { BLOCKS, embedPage } from "../bike-blocks.mjs";
import { officialPhotos } from "../contact-officials.mjs";

export const path = "/embed/bike";
export const file = "embed/bike/index.html";
// Kept out of the sitemap by the build (scripts/build.mjs skips `asset`).
export const asset = true;
export const sitemap = false;

const POST = nodePath.join(import.meta.dirname, "..", "..", "content", "posts", "sf-bike-network.md");

export function render() {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Bike Network Embeds — SF Works</title>
<style>body { font-family: system-ui, sans-serif; margin: 24px 16px; background: #ffffff; color: #15181c; }</style>
</head>
<body>
<h1>Bike network figures for embedding</h1>
<ul>
${BLOCKS.map((b) => `<li><a href="/embed/bike/${b}/">${b}</a></li>`).join("\n")}
</ul>
</body>
</html>
`;
}

export function pages() {
  return [
    ...BLOCKS.map((b) => ({ path: `/embed/bike/${b}`, file: `embed/bike/${b}/index.html`, html: embedPage(b), sitemap: false })),
    // The contact-officials picker's portraits, at /photos/officials/, which the
    // block's absolute links (and so fryanpan.com's copy) point at.
    ...officialPhotos().map((ph) => ({ path: ph.path, file: ph.file, html: ph.bytes, sitemap: false })),
    // A Buffer is written as it is, so the base-path rewrite never touches the
    // post's text.
    { path: "/content/posts/sf-bike-network.md", file: "content/posts/sf-bike-network.md", html: fs.readFileSync(POST), sitemap: false },
  ];
}
