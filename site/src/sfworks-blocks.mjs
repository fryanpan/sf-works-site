// The `::sfworks{block="<name>"}` component, shared by every markdown page the
// site builds: the bike post (src/pages/post-sf-bike-network.mjs) and the
// markdown pages under content/ (src/md-pages.mjs). fryanpan.com reads the
// same directive through scripts/export-post.mjs, so one markdown file shows
// the same chart or live map on both sites.
//
// Each directive line becomes that block, put together from the same parts as
// its /embed/bike/<name>/ page (src/bike-blocks.mjs), so the three cannot
// differ. The block's markup is collapsed onto one line so a markdown parser
// treats it as an HTML block and leaves it alone; its script, if any, is
// returned separately for the page to put after the article.

import { BLOCKS, parts } from "./bike-blocks.mjs";

// JSON inside a <script> must not close it early.
const inlineJson = (v) => JSON.stringify(v).replace(/</g, "\\u003c");

export const DIRECTIVE = /^::sfworks\{block="([\w-]+)"\}[ \t]*$/gm;

/**
 * Replace every directive in `text`. `owner` names the page in the error a
 * misspelt block raises. Returns the new text, the blocks used in order, and
 * the module scripts that mount them.
 */
export function sfworksBlocks(text, owner) {
  const used = [];
  const scripts = [];
  const out = text.replace(DIRECTIVE, (_, name) => {
    if (!BLOCKS.includes(name)) throw new Error(`${owner}: no block named "${name}"`);
    used.push(name);
    const p = parts(name);
    const id = `sfw-${name}-${used.length}`;
    if (p.js) scripts.push(`<script type="module">\n${p.js}\nmount(document.getElementById(${JSON.stringify(id)}), ${inlineJson(p.data)});\n</script>`);
    // One line, so markdown leaves the block alone, but a textarea's newlines
    // are its text (the prefilled message), so they become &#10; first.
    const html = p.html.replace(/(<textarea\b[^>]*>)([\s\S]*?)(<\/textarea>)/g, (_, a, t, b) => a + t.replace(/\n/g, "&#10;") + b);
    return `<div class="sfw" id="${id}" data-block="${name}">${html.replace(/\n+/g, " ")}</div>`;
  });
  return { text: out, used, scripts };
}
