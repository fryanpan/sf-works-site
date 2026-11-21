#!/usr/bin/env node
// Tests the posts' GFM footnotes (site/src/footnotes.mjs): one-line notes, notes of several paragraphs, numbering by
// first use, a missing definition, and the board editor's flush-left `## Footnotes` section.
//
//   node site/tests/footnotes-test.mjs
//
// Part of `npm run check` in site/.
import assert from "node:assert/strict";
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const { footnotes, normalizeFootnoteSection } = await import(path.join(ROOT, "site", "src", "footnotes.mjs"));

const li = (id, html) => `<li id="fn-${id}">${html} <a href="#fnref-${id}" aria-label="Back to text">↩</a></li>`;
const ref = (id, n) => `<sup class="fn"><a href="#fn-${id}" id="fnref-${id}">${n}</a></sup>`;

// A single-line note renders inline, with no <p>.
{
  const r = footnotes("Text.[^a]\n\n[^a]: One line.\n");
  assert.equal(r.text, `Text.${ref("a", 1)}\n\n\n`);
  assert.equal(r.references, `<h2 id="references">References</h2>\n<ol class="fn-list">${li("a", "One line.")}</ol>`);
}

// A two-paragraph note with a link keeps both paragraphs, each in a <p>, and its continuation leaves the body.
{
  const r = footnotes("Text.[^driving]\n\n[^driving]: Para one.\n\n    Para two with [a link](https://example.com).\n\nAfter.\n");
  assert.equal(r.text, `Text.${ref("driving", 1)}\n\n\n\nAfter.\n`);
  assert.ok(!r.text.includes("Para two"));
  assert.match(r.references, /<li id="fn-driving"><p>Para one\.<\/p>\s*<p>Para two with <a href="https:\/\/example\.com"[^>]*>a link<\/a>\.<\/p> <a href="#fnref-driving"/);
}

// Two notes defined in one order and referenced in the other are numbered by first use.
{
  const r = footnotes("First[^b] then[^a] and[^b] again.\n\n[^a]: Note A.\n[^b]: Note B.\n");
  assert.equal(r.text.split("\n")[0], `First${ref("b", 1)} then${ref("a", 2)} and${ref("b", 1)} again.`);
  assert.deepEqual(r.order, ["b", "a"]);
  assert.ok(r.references.indexOf('id="fn-b"') < r.references.indexOf('id="fn-a"'));
}

// A reference with no definition throws, naming the caller and the id.
assert.throws(() => footnotes("Text.[^nope]\n", { name: "post-x" }), /post-x: no footnote named "nope"/);

// The board editor's shape: a trailing `## Footnotes` section with flush-left continuation paragraphs.
{
  const md = "Body.[^driving] More.[^safety]\n\n## Footnotes\n\n[^driving]: Para one.\n\nPara two, flush left.\n\n[^safety]: Para one.\n\nPara two.\n";
  assert.equal(normalizeFootnoteSection(md),
    "Body.[^driving] More.[^safety]\n\n[^driving]: Para one.\n\n    Para two, flush left.\n\n[^safety]: Para one.\n\n    Para two.\n");
  const r = footnotes(md);
  assert.ok(!r.text.includes("Footnotes") && !r.text.includes("Para"));
  assert.equal(r.references,
    `<h2 id="references">References</h2>\n<ol class="fn-list">${li("driving", "<p>Para one.</p>\n\n<p>Para two, flush left.</p>")}${li("safety", "<p>Para one.</p>\n\n<p>Para two.</p>")}</ol>`);
  // A section that ends at the next heading leaves what follows alone, and text with no section is unchanged.
  assert.equal(normalizeFootnoteSection("## Footnotes\n\n[^a]: One.\n\nTwo.\n\n## Next\n\nKept.\n"), "[^a]: One.\n\n    Two.\n\n## Next\n\nKept.\n");
  assert.equal(normalizeFootnoteSection("No section.\n\n[^a]: One.\n\nTwo.\n"), "No section.\n\n[^a]: One.\n\nTwo.\n");
}

// CRLF input reads the same as LF, in the body and in the Footnotes section.
{
  const lf = "Body.[^a]\n\n## Footnotes\n\n[^a]: One.\n\nTwo.\n";
  assert.equal(footnotes(lf.replace(/\n/g, "\r\n")).references, footnotes(lf).references);
}

// Two definitions with one name throw: remark-gfm keeps the first, so the two sites would differ.
assert.throws(() => footnotes("T.[^a]\n\n[^a]: One.\n[^a]: Two.\n"), /two definitions named "a"/);

// A note's paragraphs go through markdown() together, so a blank line inside an indented list keeps one list.
{
  const r = footnotes("T.[^a]\n\n[^a]: Intro.\n\n    - one\n\n    - two\n");
  assert.equal((r.references.match(/<ul/g) || []).length, 1);
}

console.log("footnotes-test: all checks passed");
