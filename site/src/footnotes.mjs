// GFM footnotes for the site's posts, as fryanpan.com writes them.
//
//   const { text, references } = footnotes(body);
//
// Each `[^id]: text` definition comes out of the body together with its
// continuation paragraphs: the lines after it that are indented by 4 spaces or
// a tab, with blank lines between them. Each `[^id]` reference becomes a link
// numbered by first use, and `references` is the numbered list of notes. A
// reference with no definition throws. A note of one paragraph renders inline,
// with no <p>; a note of several keeps a <p> per paragraph.
//
// Footnotes section from the board editor. The board editor cannot keep an
// indented continuation line, so a doc edited
// there writes multi-paragraph notes in a final section, flush left:
//
//   ## Footnotes
//
//   [^driving]: Para one.
//
//   Para two, flush left.
//
// normalizeFootnoteSection() turns that into standard GFM. Inside a trailing
// `## Footnotes` section (from the heading to the next heading of level 1 or 2,
// or the end), each flush-left paragraph after a `[^id]:` definition is
// indented by 4 spaces, up to the next definition or the end of the section,
// and the heading itself is dropped. remark-gfm (fryanpan.com) and footnotes()
// here both read the result the same way. footnotes() runs it first.

import { markdown } from "./content.mjs";

const DEF = /^\[\^([\w-]+)\]:[ \t]*(.+)$/;
const INDENTED = /^(?: {4}|\t)/;

export function normalizeFootnoteSection(md) {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  const start = lines.findLastIndex((l) => /^##[ \t]+Footnotes[ \t]*$/.test(l));
  if (start < 0) return md;
  let end = lines.findIndex((l, i) => i > start && /^#{1,2}[ \t]/.test(l));
  if (end < 0) end = lines.length;
  const section = [];
  let inNote = false;
  for (const line of lines.slice(start + 1, end)) {
    if (DEF.test(line)) inNote = true;
    else if (inNote && line.trim() && !INDENTED.test(line)) { section.push("    " + line); continue; }
    section.push(line);
  }
  // Dropping the heading also drops the blank line under it.
  if (section[0] === "") section.shift();
  return [...lines.slice(0, start), ...section, ...lines.slice(end)].join("\n");
}

// Pulls the definitions out of `md`. A definition line is replaced by an empty
// line and its continuation lines are removed. Returns the remaining text and
// a Map of id to the note's dedented markdown.
export function extractFootnotes(md) {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  const notes = new Map();
  for (let i = 0; i < lines.length; i++) {
    const m = DEF.exec(lines[i]);
    if (!m) { out.push(lines[i]); continue; }
    const body = [m[2]];
    let j = i + 1;
    let last = i; // the last indented line taken
    while (j < lines.length && (INDENTED.test(lines[j]) || !lines[j].trim())) {
      if (lines[j].trim()) last = j;
      j++;
    }
    for (let k = i + 1; k <= last; k++) body.push(lines[k].replace(INDENTED, "").replace(/^[ \t]+$/, ""));
    // remark-gfm keeps the first of two same-named notes; refuse rather than differ.
    if (notes.has(m[1])) throw new Error(`footnotes: two definitions named "${m[1]}"`);
    notes.set(m[1], body.join("\n"));
    out.push("");
    i = last;
  }
  return { text: out.join("\n"), notes };
}

// One note's HTML, without the back link.
export function renderNote(note) {
  const paras = note.split(/\n[ \t]*\n/).map((p) => p.trim()).filter(Boolean);
  if (paras.length <= 1) return markdown(note).replace(/^<p>|<\/p>$/g, "");
  return markdown(note);
}

// Pandoc inline notes, as the board's docs write them: `text^[the note]`, with
// ` ¶ ` between a note's paragraphs. Each becomes a GFM reference `[^inline-N]`
// and a definition appended at the end, its later paragraphs indented, so the
// rest of footnotes() reads them as it reads any other note. Brackets inside
// the note (a link, a [primary — read] tag) are matched, not taken as its end.
export function inlineNotes(md) {
  let out = "";
  const defs = [];
  let i = 0;
  for (;;) {
    const at = md.indexOf("^[", i);
    if (at < 0) break;
    let depth = 0;
    let end = -1;
    for (let j = at + 1; j < md.length; j++) {
      if (md[j] === "\\") { j++; continue; }
      if (md[j] === "[") depth++;
      else if (md[j] === "]" && --depth === 0) { end = j; break; }
    }
    if (end < 0) throw new Error(`footnotes: an inline note ^[ never closes, near "${md.slice(at, at + 40)}"`);
    const id = `inline-${defs.length + 1}`;
    const paras = md.slice(at + 2, end).split(/\s*¶\s*/).map((p) => p.replace(/\s*\n\s*/g, " ").trim()).filter(Boolean);
    defs.push(`[^${id}]: ${paras[0] ?? ""}${paras.slice(1).map((p) => `\n\n    ${p}`).join("")}`);
    out += md.slice(i, at) + `[^${id}]`;
    i = end + 1;
  }
  if (!defs.length) return md;
  return `${out}${md.slice(i).replace(/\n*$/, "")}\n\n${defs.join("\n\n")}\n`;
}

// `name` goes in the error for a missing definition.
export function footnotes(md, { name = "footnotes" } = {}) {
  const { text: body, notes } = extractFootnotes(normalizeFootnoteSection(inlineNotes(md)));
  const order = [];
  const text = body.replace(/\[\^([\w-]+)\]/g, (_, id) => {
    if (!notes.has(id)) throw new Error(`${name}: no footnote named "${id}"`);
    if (!order.includes(id)) order.push(id);
    const n = order.indexOf(id) + 1;
    return `<sup class="fn"><a href="#fn-${id}" id="fnref-${id}">${n}</a></sup>`;
  });
  const references = order.length
    ? `<h2 id="references">References</h2>\n<ol class="fn-list">${order.map((id) => `<li id="fn-${id}">${renderNote(notes.get(id))} <a href="#fnref-${id}" aria-label="Back to text">↩</a></li>`).join("")}</ol>`
    : "";
  return { text, references, order, notes };
}
