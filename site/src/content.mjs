// Read a page's prose from content/ and fill in its figures.
//
// Why this exists: every sentence used to live inside a .mjs module as a
// template literal, so changing a word meant editing JavaScript. Prose now
// lives in content/<page>.html, which carries no JavaScript, and the module
// keeps only the data and the tables.
//
// Why HTML: the prose was already written as HTML inside those template
// literals, so this moved it rather than rewriting it. The build is Astro now
// (astro.config.mjs), so a new page that wants markdown can be a .md file
// under astro/pages/ instead.
//
// Two placeholders, both written with braces so neither looks like code:
//
//   {{ shortfall }}   a value the page passes in — a number, a date, a phrase
//   {{# table }}      a block the page passes in — a table, a generated section
//
// The difference is only about escaping. A value is HTML-escaped, so a figure
// can never inject markup. A block is inserted as-is, because the page built
// it. Anything a page did not supply is a build failure, never a blank.

import fs from "node:fs";
import path from "node:path";
import { toolShown } from "./features.mjs";
import { esc } from "./html.mjs";

const CONTENT = path.join(import.meta.dirname, "..", "content");

const PLACEHOLDER = /\{\{(#?)\s*([\w.]+)\s*\}\}/g;


// "a.b.c" against the values object, so a page can pass its data through whole
// rather than flattening every figure by hand.
function lookup(values, key) {
  return key
    .split(".")
    .reduce((o, k) => (o == null ? undefined : o[k]), values);
}

/**
 * The prose of content/<name>.html with its placeholders filled.
 *
 * Throws rather than rendering a gap. A page that quietly loses a figure still
 * reads as a finished sentence — "62 of segments fell short" — and nothing
 * about it looks wrong, which is the failure this is here to prevent. The
 * message names the file and the key so the fix is obvious from the error.
 */
export function content(name, values = {}) {
  // A page's prose may be markdown instead, in content/<name>.md, so a person
  // can edit it in the workspace's document editor (which binds .md files)
  // without touching HTML. Markdown wins when both files exist.
  const mdFile = path.join(CONTENT, `${name}.md`);
  const file = path.join(CONTENT, `${name}.html`);
  let text;
  if (fs.existsSync(mdFile)) {
    text = markdown(dropHiddenTools(fs.readFileSync(mdFile, "utf8")));
  } else {
    try {
      text = fs.readFileSync(file, "utf8");
    } catch {
      throw new Error(`content: no prose file at content/${name}.html or .md`);
    }
  }

  const missing = [];
  const used = new Set();

  const html = text.replace(PLACEHOLDER, (_, block, key) => {
    used.add(key);
    const v = lookup(values, key);
    if (v === undefined || v === null || (typeof v === "number" && !isFinite(v))) {
      missing.push(key);
      return "";
    }
    return block ? String(v) : esc(v);
  });

  if (missing.length) {
    throw new Error(
      `content/${name} refers to ${missing.length} value(s) the page did ` +
        `not supply: ${[...new Set(missing)].join(", ")}`,
    );
  }

  // The other direction is a warning, not a failure: prose that stops
  // mentioning a figure is an ordinary edit, and failing the build on it would
  // mean editing JavaScript to delete a sentence — the thing this removed.
  const unused = Object.keys(values).filter((k) => !used.has(k));
  if (unused.length) {
    console.warn(
      `  note: content/${name} does not use ${unused.join(", ")}`,
    );
  }

  return html;
}

// A heading that links to a tool not yet released (src/features.mjs), and the
// paragraph under it, are left out until the tool is. This is how the home
// page lists only the tools that are live, without anyone editing its prose.
function dropHiddenTools(src) {
  const blocks = src.replace(/\r/g, "").split(/\n{2,}/);
  const out = [];
  for (let i = 0; i < blocks.length; i++) {
    const m = /^\s*<h\d><a href="\/([\w-]+)"/.exec(blocks[i]);
    if (m && !toolShown(m[1])) { i++; continue; }
    out.push(blocks[i]);
  }
  return out.join("\n\n");
}

// The small part of markdown a prose page needs, with no dependency: ATX
// headings, paragraphs, lists, links, emphasis, inline code, and lines that
// are already HTML, which pass through untouched so a class or a tag can be
// written where the markdown has no word for it. Anything more belongs in the
// page's .mjs.
//
// Three additions so an About page reads as prose in the document editor
// rather than as HTML (Bryan, 2026-09-30: "this is not readable -- it's raw
// HTML"):
//   ## Heading {#id}         a heading with an anchor
//   {#id} or {.class} Text   a paragraph, or a list item, with an anchor or class
//   {.class} on its own line as a list's first line, a class on the list
// and inside a list item, a continuation line starting "Ask:" becomes the
// item's request to the city (<span class="ask">). A list item continues on
// lines indented by two or more spaces; "  - " starts a nested list.
function inline(t) {
  return t
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\(((?:\{\{[^}]*\}\}|[^)\s])+)\)/g, '<a href="$2">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}
// A leading {#id} or {.class} as attributes, and the text after it.
function attrs(t) {
  const m = /^\{([#.])([\w-]+)\}\s*/.exec(t);
  if (!m) return ["", t];
  return [m[1] === "#" ? ` id="${m[2]}"` : ` class="${m[2]}"`, t.slice(m[0].length)];
}
const ITEM = /^(?:[-*]|\d+\.)\s+/;
function list(lines) {
  let cls = "";
  if (/^\{\.[\w-]+\}$/.test(lines[0])) cls = ` class="${lines.shift().slice(2, -1)}"`;
  const tag = /^\d+\./.test(lines[0]) ? "ol" : "ul";
  const items = [];
  for (const l of lines) {
    if (ITEM.test(l)) items.push({ text: [l.replace(ITEM, "")], ask: null, sub: [] });
    else if (/^\s{2,}[-*]\s+/.test(l)) items[items.length - 1].sub.push(l.trim());
    else if (/^\s*Ask:\s*/.test(l)) items[items.length - 1].ask = l.trim().replace(/^Ask:\s*/, "");
    else items[items.length - 1].text.push(l.trim());
  }
  const li = items.map((it) => {
    const [a, t] = attrs(it.text.join(" "));
    const ask = it.ask === null ? "" : `<span class="ask"><b>Ask:</b> ${inline(it.ask)}</span>`;
    const sub = it.sub.length ? `<ul>\n${it.sub.map((s) => `<li>${inline(s.replace(ITEM, ""))}</li>`).join("\n")}\n</ul>` : "";
    return `<li${a}>${inline(t)}${ask}${sub}</li>`;
  });
  return `<${tag}${cls}>\n${li.join("\n")}\n</${tag}>`;
}
// A Mermaid diagram, written as a fenced block so it stays editable prose:
//
//   ```mermaid
//   flowchart TD
//     layer[(MTA Bike Network Linear Features)] --> classify[Classify each street segment by year]
//   ```
//
// The block is passed through as <pre class="mermaid">, and the page loads
// Mermaid (mermaid.js.org) from a CDN to draw it in the browser. Bryan,
// 2026-09-30: use the industry-standard library rather than our own boxes.
// Drawing in the browser keeps the build dependency-free (see the note above).
function mermaidBlock(body) {
  return `<figure class="diagram"><pre class="mermaid">${esc(body)}</pre></figure>`;
}
export function markdown(src) {
  const out = [];
  // Fenced Mermaid blocks may hold blank-free lines only; lift them out first
  // so the block split below cannot break them.
  src = src.replace(/\r/g, "").replace(/^```mermaid\n([\s\S]*?)\n```$/gm, (_, body) => mermaidBlock(body));
  // The board's editor writes lists "loose", with a blank line between items
  // and before an item's Ask line, so a list is rejoined into one block: a
  // lone {.class} line joins the list under it, and a block that starts with
  // an item marker or with indentation joins the list before it.
  const blocks = [];
  const isList = (b) => b.split("\n").some((l) => ITEM.test(l));
  for (const raw of src.replace(/\r/g, "").trim().split(/\n{2,}/)) {
    const prev = blocks[blocks.length - 1];
    const joins = prev !== undefined && (
      (/^\{\.[\w-]+\}$/.test(prev) && ITEM.test(raw)) ||
      (isList(prev) && !/^#/.test(prev) && (ITEM.test(raw) || /^\s+\S/.test(raw))));
    if (joins) blocks[blocks.length - 1] = prev + "\n" + raw;
    else blocks.push(raw);
  }
  for (const block of blocks) {
    const b = block.replace(/\s+$/, "").replace(/^\n+/, "");
    if (!b.trim()) continue;
    const h = /^(#{1,6})\s+(.+?)(?:\s+\{#([\w-]+)\})?$/.exec(b);
    if (h && !b.includes("\n")) { out.push(`<h${h[1].length}${h[3] ? ` id="${h[3]}"` : ""}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^<[a-zA-Z!]/.test(b)) { out.push(b); continue; }
    // A block placeholder on its own line is a table or section the page
    // builds; wrapping it in <p> nests block elements inside a paragraph.
    if (/^\{\{#\s*[\w.]+\s*\}\}$/.test(b)) { out.push(b); continue; }
    const lines = b.split("\n");
    const first = /^\{\.[\w-]+\}$/.test(lines[0]) ? 1 : 0;
    if (lines.length > first && ITEM.test(lines[first])) { out.push(list(lines)); continue; }
    const [a, t] = attrs(b.replace(/\n/g, " "));
    out.push(`<p${a}>${inline(t)}</p>`);
  }
  return out.join("\n\n");
}
