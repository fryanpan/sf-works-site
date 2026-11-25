#!/usr/bin/env node
// Tests the site's markdown pages (site/src/md-pages.mjs): front matter checked against
// site/content/.workspaces/doc-metadata.schema.json, the Updated date (front matter, then git, then mtime),
// the front page's Recent Changes order, teaser rendering, drafts left out of the public build, and a
// board .mdx doc published as it is: <PlotChart>, <Carousel>, ::scratch frames, inline ^[...] notes with
// ¶ paragraph breaks, and images beside the doc.
//
//   node site/tests/md-pages-test.mjs
//
// Part of `npm run check` in site/. Each case writes its pages into a throwaway git repository
// under the OS temp directory, so the dates it checks are commits it made itself.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

import { ROOT } from "../scripts/lib/repo.mjs";
const { loadPages, renderPage, renderParts, mdPageFiles, recentChanges, lastUpdated } = await import(path.join(ROOT, "site", "src", "md-pages.mjs"));

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "md-pages-test-"));
process.on("exit", () => fs.rmSync(tmp, { recursive: true, force: true }));
let n = 0;
// A fresh content folder in its own git repository. `files` maps a path under it to its text.
function repo(files) {
  const dir = path.join(tmp, `r${n++}`);
  fs.mkdirSync(dir);
  execFileSync("git", ["init", "-q"], { cwd: dir });
  for (const [f, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true });
    fs.writeFileSync(path.join(dir, f), text);
  }
  return dir;
}
function commit(dir, files, date) {
  const env = { ...process.env, GIT_AUTHOR_DATE: date, GIT_COMMITTER_DATE: date, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@example.com", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@example.com" };
  execFileSync("git", ["add", ...files], { cwd: dir, env });
  execFileSync("git", ["commit", "-q", "-m", "x"], { cwd: dir, env });
}
const md = (front, body = "Body.\n") => `---\n${front}\n---\n\n${body}`;

// A page with front matter is published at the matching address; index.md is its folder's.
// Files with no front matter (prose a page module reads) and posts/ (fryanpan.com posts) are not pages.
{
  const dir = repo({
    "a/part-one.md": md("title: Part One\nstatus: published\nupdated: 2026-01-02"),
    "a/index.md": md("title: A\nstatus: published\nupdated: 2026-01-01"),
    "home.md": "# Home\n\nNo front matter.\n",
    "posts/p.md": md('title: "Post"\ndescription: not in the schema'),
  });
  const pages = loadPages({ dir, showDrafts: false });
  assert.deepEqual(pages.map((p) => [p.path, p.file]), [["/a", "a/index.html"], ["/a/part-one", "a/part-one/index.html"]]);
}

// Front matter that fails the schema stops the build, naming the file and every problem.
{
  const bad = {
    "missing-title.md": md("summary: no title\nstatus: published"),
    "bad-status.md": md("title: X\nstatus: live"),
    "bad-date.md": md("title: X\nstatus: published\nupdated: 12 Nov 2026"),
    "extra-field.md": md("title: X\nstatus: published\ndescription: not a schema field"),
    "bad-yaml.md": md("title: [unclosed"),
    "Bad_Name.md": md("title: X\nstatus: published"),
  };
  for (const [f, text] of Object.entries(bad)) {
    const dir = repo({ [f]: text });
    assert.throws(() => loadPages({ dir, showDrafts: true }), (e) => e.message.includes(`content/${f}`), `${f} should fail`);
  }
  // Front matter the parser might miss still counts as a page: a BOM, spaces after the fence, an
  // empty block (which then fails for lacking a title). A board .mdx doc is a page like any other.
  assert.equal(loadPages({ dir: repo({ "bom.md": "\uFEFF---  \ntitle: X\nstatus: published\n---\nhi\n" }) }).length, 1);
  assert.throws(() => loadPages({ dir: repo({ "empty.md": "---\n---\nhi\n" }) }), /content\/empty\.md: front matter must have required property 'title'/);
  assert.deepEqual(loadPages({ dir: repo({ "w/doc.mdx": md("title: X\nstatus: published") }) }).map((p) => [p.path, p.file]), [["/w/doc", "w/doc/index.html"]]);
  // Every problem in one run, not just the first.
  const dir = repo(bad);
  assert.throws(() => loadPages({ dir }), /6 invalid page\(s\)/);
  // A field left blank by the editor is the same as no field.
  const ok = repo({ "blank.md": md("title: X\nstatus: published\nupdated:\nsummary: ''") });
  assert.equal(loadPages({ dir: ok }).length, 1);
}

// Updated: the front matter's date wins; blank means the file's last commit; a file git has no
// commit for falls back to its mtime.
{
  const dir = repo({
    "dated.md": md("title: Dated\nstatus: published\nupdated: 2026-05-06"),
    "from-git.md": md("title: From Git\nstatus: published"),
  });
  commit(dir, ["dated.md", "from-git.md"], "2026-03-04T12:00:00-08:00");
  fs.writeFileSync(path.join(dir, "new.md"), md("title: New\nstatus: published"));
  const t = new Date(2026, 6, 8, 12);
  fs.utimesSync(path.join(dir, "new.md"), t, t);
  const byTitle = Object.fromEntries(loadPages({ dir }).map((p) => [p.front.title, [p.updated, p.updatedFrom]]));
  assert.deepEqual(byTitle, { Dated: ["2026-05-06", "front matter"], "From Git": ["2026-03-04", "git"], New: ["2026-07-08", "mtime"] });
  // A later commit moves the git date.
  fs.appendFileSync(path.join(dir, "from-git.md"), "More.\n");
  commit(dir, ["from-git.md"], "2026-04-01T09:00:00-07:00");
  assert.equal(lastUpdated(path.join(dir, "from-git.md")).date, "2026-04-01");
  // The date is printed under the title.
  const page = loadPages({ dir }).find((p) => p.front.title === "Dated");
  assert.match(renderPage(page), /<h1>Dated<\/h1>\n<p class="data-updated">Updated <time datetime="2026-05-06">6 May 2026<\/time><\/p>/);
}

// Recent Changes: published and teaser pages and the listed dashboards passed in, newest first, a tie broken by
// title, drafts left out, only the 30 days up to the newest change, at most n entries; nothing at all when there is
// nothing to list.
{
  const dir = repo({
    "old.md": md("title: Old\nstatus: published\nupdated: 2026-01-31\nsummary: The oldest."),
    "stale.md": md("title: Stale\nstatus: published\nupdated: 2026-01-20"),
    "new.md": md("title: Newest\nstatus: published\nupdated: 2026-03-01"),
    "tie-b.md": md("title: Bravo\nstatus: teaser\nupdated: 2026-02-01"),
    "tie-a.md": md("title: Alpha\nstatus: published\nupdated: 2026-02-01"),
    "draft.md": md("title: Draft\nstatus: draft\nupdated: 2026-12-01"),
  });
  const pages = loadPages({ dir, showDrafts: true });
  const order = (html) => [...html.matchAll(/<li><a href="[^"]+">([^<]+)<\/a>/g)].map((m) => m[1]);
  const html = recentChanges(pages);
  assert.deepEqual(order(html), ["Newest", "Alpha", "Bravo", "Old"]);
  assert.match(html, /Bravo<\/a> <span class="tag">coming soon<\/span>/);
  assert.match(html, /<span class="line">The oldest\.<\/span>/);
  assert.deepEqual(order(recentChanges(pages, 2)), ["Newest", "Alpha"]);
  // A dashboard dated by its code joins the list; one with no date is left out.
  const extra = [{ path: "/dash", title: "Dashboard", summary: "", updated: "2026-02-15" }, { path: "/undated", title: "Undated", updated: "" }];
  assert.deepEqual(order(recentChanges(pages, 12, extra)), ["Newest", "Dashboard", "Alpha", "Bravo", "Old"]);
  assert.equal(recentChanges([]), "");
}

// A teaser shows its title, summary and "Coming soon" with the two asks, and never its body.
{
  const dir = repo({ "t.md": md("title: Coming Part\nsummary: What it will cover.\nstatus: teaser\nupdated: 2026-02-01", "UNFINISHED DRAFT TEXT\n") });
  const [p] = loadPages({ dir });
  const on = renderPage(p, { feedbackOn: true });
  assert.match(on, /<p class="coming">Coming soon<\/p>\n<h1>Coming Part<\/h1>/);
  assert.match(on, /<p class="lede">What it will cover\.<\/p>/);
  assert.match(on, /data-feedback-open data-ask="next">Ask for this part next</);
  assert.match(on, /data-feedback-open data-ask="help">Offer to help</);
  assert.ok(!on.includes("UNFINISHED DRAFT TEXT"));
  // With no feedback form on this build, a marked placeholder stands in for the buttons.
  const off = renderPage(p, { feedbackOn: false });
  assert.match(off, /data-placeholder="ask">\[Placeholder:/);
  assert.ok(!off.includes("data-ask="));
}

// Drafts are not built for sf-works.org; staging and dev (showDrafts) build them under a band.
{
  const dir = repo({
    "d.md": md("title: Draft Page\nstatus: draft\nupdated: 2026-02-01"),
    "default.md": md("title: No Status\nupdated: 2026-02-01"),
  });
  assert.equal(loadPages({ dir, showDrafts: false }).length, 0);
  const shown = loadPages({ dir, showDrafts: true });
  assert.equal(shown.length, 2);
  assert.match(renderPage(shown[0]), /<p class="draft-band"><strong>Draft, not public\.<\/strong>/);
}

// A published page renders its markdown with marked, takes its <h1> from the front matter (dropping
// the body's own), and turns an ::sfworks line into that block, with credits for it at the end.
{
  const dir = repo({ "p.md": md("title: Front Title\nstatus: published\nupdated: 2026-02-01", '# Body Title\n\nSome *text*.\n\n::sfworks{block="goal-chart"}\n') });
  const html = renderPage(loadPages({ dir })[0]);
  assert.ok(!html.includes("Body Title"));
  assert.match(html, /<p>Some <em>text<\/em>\.<\/p>/);
  assert.match(html, /<div class="sfw" id="sfw-goal-chart-1" data-block="goal-chart">/);
  assert.match(html, /Photo and Data Credits/);
  const misspelt = repo({ "q.md": md("title: Q\nstatus: published", '::sfworks{block="no-such-block"}\n') });
  assert.throws(() => renderPage(loadPages({ dir: misspelt })[0]), /content\/q\.md: no block named "no-such-block"/);
}

// A board doc publishes as the board wrote it. <PlotChart> props are JSON literals, drawn to SVG with
// the board's own plot-spec.mjs; <Carousel> stacks its charts and its import line goes; ::scratch frames
// the site's copy of the figure page, which is published with the page; ^[...] notes become numbered
// footnotes, ¶ splitting a note's paragraphs; an image beside the doc is published beside the page.
{
  const chart = `<PlotChart
  title="Two Bars"
  data={{"a": [{"k": "One", "v": 1}, {"k": "Two", "v": 2}]}}
  marks={[{"mark": "barX", "data": "a", "options": {"y": "k", "x": "v"}}]}
  options={{"width": 400, "height": 120}}
/>`;
  const body = `# Board Title

Text with a note.^[First paragraph, with [a link](https://example.com) and a [primary — read 2026-11-17] tag. ¶ Second paragraph.]

${chart}

import Carousel from './components/carousel.tsx'

<Carousel label="Two charts">
${chart}
${chart}
</Carousel>

::scratch{block="intro-vmt"}

![A picture](images/pic.png)

| A | B |
| --- | --- |
| 1 | 2 |

Another note.^[Only one paragraph.]
`;
  const dir = repo({ "w/doc.mdx": md("title: Board Doc\nstatus: published\nupdated: 2026-11-17", body), "w/images/pic.png": "not really a png" });
  const page = loadPages({ dir })[0];
  const { html, assets } = renderParts(page);
  assert.ok(!html.includes("Board Title"));
  assert.equal((html.match(/<figure class="md-chart">/g) || []).length, 3);
  assert.equal((html.match(/<svg\b/g) || []).length >= 3, true);
  assert.match(html, /<div class="chart-stack" role="group" aria-label="Two charts">/);
  for (const raw of ["<PlotChart", "<Carousel", "import Carousel", "::scratch", "^[", "¶"]) assert.ok(!html.includes(raw), `raw ${raw} leaked`);
  assert.match(html, /<iframe class="md-embed" src="\/embed\/figures\/intro-vmt\/\?block=intro-vmt"/);
  assert.match(html, /<img src="\/w\/images\/pic\.png" alt="A picture">/);
  assert.match(html, /<table>/);
  assert.match(html, /<sup class="fn"><a href="#fn-inline-1" id="fnref-inline-1">1<\/a><\/sup>/);
  assert.match(html, /<sup class="fn"><a href="#fn-inline-2" id="fnref-inline-2">2<\/a><\/sup>/);
  assert.match(html, /<li id="fn-inline-1"><p>First paragraph, with <a href="https:\/\/example\.com"[^>]*>a link<\/a> and a \[primary — read 2026-11-17\] tag\.<\/p>\s*<p>Second paragraph\.<\/p>/);
  assert.deepEqual(assets.map((a) => [a.file, Buffer.isBuffer(a.html), a.sitemap]), [["embed/figures/intro-vmt/index.html", true, false], ["w/images/pic.png", true, false]]);
  // The build's list carries each figure page and image once, after the pages, out of the sitemap.
  const files = mdPageFiles([page, { ...page, path: "/w/copy", file: "w/copy/index.html" }], {});
  assert.deepEqual(files.map((f) => f.file), ["w/doc/index.html", "w/copy/index.html", "embed/figures/intro-vmt/index.html", "w/images/pic.png"]);
  // What the site cannot draw stops the build, naming the page.
  const bad = (b) => () => renderPage(loadPages({ dir: repo({ "x.mdx": md("title: X\nstatus: published", b) }) })[0]);
  assert.throws(bad('::scratch{block="no-such-figure"}\n'), /content\/x\.mdx: ::scratch\{block="no-such-figure"\} has no figure page/);
  assert.throws(bad("<Mystery foo=\"1\" />\n"), /content\/x\.mdx: <Mystery> is a board component the site does not draw/);
  assert.throws(bad('<PlotChart data={{"a": [1]}} marks={[{"mark": "nope", "data": "a"}]} />\n'), /content\/x\.mdx: <PlotChart> cannot be drawn/);
  assert.throws(bad("![](images/missing.png)\n"), /content\/x\.mdx: image images\/missing\.png is not there/);
  assert.throws(bad("A note that never closes.^[oops\n"), /never closes/);
  // Only image files beside the doc are published: not another doc's source, not a file reached through a symlink.
  assert.throws(bad("![](other.mdx)\n"), /content\/x\.mdx: other\.mdx is not an image file/);
  const linked = repo({ "w/x.mdx": md("title: X\nstatus: published", "![](images/secret.png)\n") });
  const outside = fs.mkdtempSync(path.join(tmp, "outside-"));
  fs.writeFileSync(path.join(outside, "secret.png"), "x");
  fs.symlinkSync(outside, path.join(linked, "w", "images"));
  assert.throws(() => renderPage(loadPages({ dir: linked })[0]), /image images\/secret\.png is outside content\//);
  // Board syntax inside code is an example, left as written.
  const code = renderPage(loadPages({ dir: repo({ "c.mdx": md("title: C\nstatus: published", "A regex `^[a-z]` and `<PlotChart />`.\n\n```\n::scratch{block=\"nope\"}\n<Mystery />\n```\n") }) })[0]);
  assert.match(code, /<code>\^\[a-z\]<\/code>/);
  assert.match(code, /<code>&lt;PlotChart \/&gt;<\/code>/);
  assert.match(code, /::scratch\{block=&quot;nope&quot;\}/);
  assert.ok(!code.includes('class="fn"'));
  // A figure page no built page frames is not published.
  assert.ok(!mdPageFiles(loadPages({ dir: repo({ "plain.md": md("title: P\nstatus: published") }) }), {}).some((f) => f.file.startsWith("embed/")));
  // A draft's figures and images stay out of a production build with the draft.
  const draftDir = repo({ "w/d.mdx": md("title: D\nstatus: draft", '::scratch{block="intro-vmt"}\n\n![](images/pic.png)\n'), "w/images/pic.png": "x" });
  assert.deepEqual(mdPageFiles(loadPages({ dir: draftDir, showDrafts: false }), {}), []);
}

console.log("md-pages-test: all passed");
