// Site pages written as markdown with front matter.
//
// Bryan, 2026-11-12: "have a deploy pipeline where each page on site is driven
// by a markdown page with components that deploy directly to the website ...
// Have links that tease unfinished parts, and let people ask for what to see
// next. Or help contribute. And be able to have metadata on each page that
// shows last modification time. And have on the front page a directory of
// recent changes."
//
// A markdown file anywhere under content/ that opens with YAML front matter is
// a page, published at the matching address: content/whitepaper/part-1.md is
// sf-works.org/whitepaper/part-1, and an index.md is its folder's address. A
// file with no front matter is prose a page module reads (src/content.mjs), and
// content/posts/ holds fryanpan.com posts with their own front matter
// (scripts/export-post.mjs), so neither is picked up here.
//
// The front matter is checked against the schema the board's document editor
// also reads, content/.workspaces/doc-metadata.schema.json (one schema for
// both). It sits under content/ because the editor applies the nearest
// .workspaces/ schema walking up from a doc's folder, so only site pages get
// the metadata fields, and a page that fails it stops the build. `status` decides what
// is built:
//
//   published   the page, in full
//   teaser      the title, the summary and "coming soon", with a way to ask for
//               this part next or offer to help. The body is never rendered, so
//               an unfinished draft can sit under a teaser without going out.
//   draft       (the default) not built on sf-works.org. Staging and the dev
//               server (SITE_SHOW_HIDDEN=1, src/features.mjs) build it with a
//               "not public" band, so it can be reviewed there.
//
// A folder page, content/<path>/page.mdx (or page.md) with the images and
// figure pages it uses beside it, also publishes at /<path>, and keeps every
// published version at /<path>/v/<n> with a revision history at /<path>/v/
// (src/page-versions.mjs, `npm run new-version -- <path>`).
//
// A page may be .md or .mdx, so a board doc publishes as it is written. The
// bike post's components work on both sites: `::sfworks{block="<name>"}` for a
// chart or a live map (src/sfworks-blocks.mjs), and GFM footnotes
// (src/footnotes.mjs), which also take the board's inline `^[note]` form. The
// board's own components are drawn by src/md-components.mjs: `<PlotChart>`,
// `<Carousel>` and `::scratch{block="<name>"}`. An image the doc links
// relative to itself (`![](images/x.png)`, as the board writes them) is
// published at the matching address under the page's folder. The rest is
// markdown, rendered with marked.
//
// So publishing a board doc is binding it here, with no conversion step: move
// its file under content/ (the board's move_doc_file keeps the binding), set
// its title and `status: published` in the editor's metadata fields, and run
// `npm run deploy-docs` (scripts/deploy-docs.mjs).

import fs from "node:fs";
import nodePath from "node:path";
import { execFileSync } from "node:child_process";
import yaml from "js-yaml";
import Ajv2020Module from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";
import { marked } from "marked";
import { page } from "./layout.mjs";
import { shortDate, importCommit, readFallback } from "./page-dates.mjs";
import { esc } from "./html.mjs";
import { footnotes } from "./footnotes.mjs";
import { postCredits, sfwCss } from "./bike-blocks.mjs";
import { sfworksBlocks } from "./sfworks-blocks.mjs";
import { pathShown } from "./features.mjs";
import { BIKE_DATA_READ } from "./transportation.mjs";
import { mdComponents, EMBED_SCRIPT, COMPONENT_CSS } from "./md-components.mjs";
import { embedNames, embedHTML, embedPath } from "./doc-embeds.mjs";
import { STORY_HEAD, STORY_SCRIPTS } from "./safety-map/story.mjs";
import { dataMeta } from "./safety-map/index.mjs";
import { readVersions, versionDir, pageFileIn, versionLine, olderLine, longDate } from "./page-versions.mjs";

const Ajv2020 = Ajv2020Module.default ?? Ajv2020Module;
const addFormats = addFormatsModule.default ?? addFormatsModule;

const SITE = nodePath.resolve(import.meta.dirname, "..");
export const CONTENT = nodePath.join(SITE, "content");
// The page metadata schema, shared with the board's editor. It lives beside the
// pages so the editor shows these fields on site pages and nowhere else.
export const SCHEMA_FILE = nodePath.join(CONTENT, ".workspaces", "doc-metadata.schema.json");

// A BOM, trailing spaces on the fences and an empty block are all still front matter.
const FRONT = /^\uFEFF?---[ \t]*\n(?:([\s\S]*?)\n)?---[ \t]*(?:\n([\s\S]*))?$/;
const SEGMENT = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

let validator = null;
function validate(data) {
  if (!validator) {
    const ajv = new Ajv2020({ allErrors: true });
    addFormats(ajv);
    // The editor's own annotation: blank `updated` means "use git".
    ajv.addKeyword("x-workspaces-default");
    validator = ajv.compile(JSON.parse(fs.readFileSync(SCHEMA_FILE, "utf8")));
  }
  return validator(data) ? [] : validator.errors.map((e) => `${e.instancePath || "front matter"} ${e.message}${e.params?.additionalProperty ? ` (${e.params.additionalProperty})` : ""}`);
}

// Every .md under `dir`, sorted, except posts/ and a folder page's published
// versions (versions/<n>/, which loadPages reads through versions.json).
function markdownFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { recursive: true })
    .map(String)
    .filter((f) => /\.mdx?$/.test(f) && f.split(nodePath.sep)[0] !== "posts" && !/(^|\/)versions\/\d+\//.test(f.split(nodePath.sep).join("/")))
    .sort();
}

const isShallow = (cwd) => {
  try {
    return execFileSync("git", ["rev-parse", "--is-shallow-repository"], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim() === "true";
  } catch {
    return false;
  }
};

/**
 * The date a page last changed, as YYYY-MM-DD, and where it came from: the
 * front matter's `updated` if set, else the file's last commit date (the
 * committer date, so a merged PR dates the page by its merge). When that
 * commit is the repo's first, the import, its date is the import's, so the
 * page's entry in data/page-dates.json (keyed by its path from site/, such as
 * "content/home.md") is used while it has one (src/page-dates.mjs). A file git
 * has no commit for yet, or a checkout with no git at all, falls back to the
 * file's mtime; that only happens on a working copy, since CI builds a full
 * clone (.github/workflows/deploy.yml, fetch-depth: 0). A shallow clone would
 * date every page by its one commit, so it stops the build instead.
 */
export function lastUpdated(file, front = {}) {
  if (front.updated) return { date: front.updated, from: "front matter" };
  const cwd = nodePath.dirname(file);
  let date = "";
  let hash = "";
  try {
    [hash, date = ""] = execFileSync("git", ["log", "-1", "--format=%H %cs", "--", nodePath.basename(file)], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim().split(" ");
  } catch {
    // No git, or not a repository: the mtime below is all there is.
  }
  if (date) {
    if (isShallow(cwd)) throw new Error(`md-pages: ${file} is in a shallow clone, so git cannot date it; fetch the full history (fetch-depth: 0)`);
    const key = nodePath.relative(SITE, file).split(nodePath.sep).join("/");
    const kept = readFallback()[key];
    if (kept && hash === importCommit(cwd)) return { date: kept, from: "page-dates.json" };
    return { date, from: "git" };
  }
  // The local calendar date, as git's %cs gives the committer's.
  const t = fs.statSync(file).mtime;
  const pad = (n) => String(n).padStart(2, "0");
  return { date: `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`, from: "mtime" };
}

/**
 * Every markdown page under `dir`, as [{src, path, file, front, body, status,
 * updated, updatedFrom}], with drafts left out unless `showDrafts`. Throws on
 * an invalid page, naming the file and every problem with it.
 */
export function loadPages({ dir = CONTENT, showDrafts = process.env.SITE_SHOW_HIDDEN === "1" } = {}) {
  const pages = [];
  const errors = [];
  // A page file's front matter and body, or null for prose with no front matter.
  const read = (rel) => {
    const text = fs.readFileSync(nodePath.join(dir, rel), "utf8").replace(/\r/g, "");
    const m = FRONT.exec(text);
    if (!m) return null;
    let front;
    try {
      front = yaml.load(m[1] ?? "", { schema: yaml.CORE_SCHEMA }) ?? {};
    } catch (e) {
      errors.push(`content/${rel}: front matter is not valid YAML: ${e.reason || e.message}`);
      return null;
    }
    if (typeof front !== "object" || Array.isArray(front)) {
      errors.push(`content/${rel}: front matter must be a set of fields`);
      return null;
    }
    // A field the editor left blank is the same as no field.
    for (const k of Object.keys(front)) if (front[k] === null || front[k] === "") delete front[k];
    return { front, body: m[2] ?? "" };
  };
  for (const rel of markdownFiles(dir)) {
    const src = nodePath.join(dir, rel);
    const r = read(rel);
    if (!r) continue;
    const { front } = r;
    const problems = validate(front);
    const segments = rel.replace(/\.mdx?$/, "").split(nodePath.sep);
    // content/<path>/page.mdx is a folder page: the page at /<path>, with its versions.
    const folder = segments[segments.length - 1] === "page" ? nodePath.dirname(src) : null;
    if (segments[segments.length - 1] === "index" || folder) segments.pop();
    const bad = segments.filter((s) => !SEGMENT.test(s));
    if (bad.length) problems.push(`its address needs lower-case kebab-case names, not ${bad.join(", ")}`);
    if (!segments.length) problems.push("content/index.md would replace the front page");
    if (problems.length) {
      errors.push(`content/${rel}: ${problems.join("; ")}`);
      continue;
    }
    const status = front.status || "draft";
    if (status === "draft" && !showDrafts) continue;
    const path = `/${segments.join("/")}`;
    if (!pathShown(path)) continue;
    const versions = folder ? readVersions(folder) : [];
    // A page with versions is dated by its latest, so Recent Changes and its own line agree.
    const { date, from } = versions.length ? { date: versions[versions.length - 1].date, from: "versions.json" } : lastUpdated(src, front);
    pages.push({ root: dir, src: rel, path, file: `${segments.join("/")}/index.html`, front, body: r.body, status, updated: date, updatedFrom: from, folder, versions });
    // Each published version, rendered from its own copy of the folder at /<path>/v/<n>.
    for (const v of versions) {
      const vdir = versionDir(folder, v.n);
      const name = fs.existsSync(vdir) ? pageFileIn(vdir) : null;
      if (!name) {
        errors.push(`content/${rel}: version ${v.n} is in versions.json but versions/${v.n}/ has no page.md or page.mdx`);
        continue;
      }
      const vrel = nodePath.relative(dir, nodePath.join(vdir, name));
      const vr = read(vrel);
      if (!vr) {
        errors.push(`content/${vrel}: has no front matter`);
        continue;
      }
      const vstatus = vr.front.status || "draft";
      if (vstatus === "draft" && !showDrafts) continue;
      pages.push({
        root: dir, src: vrel, path: `${path}/v/${v.n}`, file: `${segments.join("/")}/v/${v.n}/index.html`,
        front: vr.front, body: vr.body, status: vstatus, updated: v.date, updatedFrom: "versions.json",
        folder: vdir, version: { ...v, latest: versions[versions.length - 1].n, of: path },
      });
    }
  }
  if (errors.length) throw new Error(`md-pages: ${errors.length} invalid page(s):\n  ${errors.join("\n  ")}`);
  return pages;
}

let cached = null;
/** The pages under content/, loaded once per process. */
export const mdPages = () => (cached ??= loadPages());

export { longDate };

const updatedLine = (p) => `<p class="data-updated">Updated <time datetime="${p.updated}">${longDate(p.updated)}</time></p>`;
// The line under the title: an older version says which it is; a page with
// published versions gives its latest, from versions.json; any other page its
// Updated date.
const dateLine = (p) =>
  p.version
    ? olderLine(p.version.of, p.version, p.version.latest)
    : p.versions?.length
      ? versionLine(p.path, p.versions[p.versions.length - 1])
      : updatedLine(p);

// The body's own `# Title` line, if it opens with one, gives way to the front
// matter's title, so a doc written in the board editor (which keeps its title
// as an H1) does not show it twice.
const dropLeadingH1 = (body) => body.replace(/^\s*#\s+[^\n]*\n/, "");

const PAGE_CSS = `<style>
.md-page { max-width: 68ch; }
.md-page h1, .md-page h2, .md-page h3 { text-wrap: balance; }
.md-page p, .md-page li { text-wrap: pretty; }
.md-page .draft-band { background: var(--seq-2-soft); border-left: 3px solid var(--seq-2); padding: 8px 12px; margin: 0 0 16px; font-size: 0.9rem; }
.md-page .coming { display: inline-block; margin: 0 0 8px; padding: 2px 10px; border-radius: 999px; background: var(--seq-3-soft); color: var(--seq-3); font-size: 0.8rem; font-weight: 600; letter-spacing: 0.02em; }
.md-page .ask { margin: 28px 0 0; padding: 16px 18px; border: 1px solid var(--rule); border-radius: 10px; }
.md-page .ask h2 { margin-top: 0; }
.md-page .ask-buttons { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 0; }
.md-page .ask-buttons button { font: inherit; font-weight: 600; padding: 8px 16px; border-radius: 8px; border: 1px solid var(--seq-3); background: var(--paper); color: var(--seq-3); cursor: pointer; }
.md-page .ask-buttons button:first-child { background: var(--seq-3); color: var(--paper); }
${COMPONENT_CSS}
.md-page .placeholder { font-size: 0.9rem; color: var(--muted); border: 1px dashed var(--rule); padding: 8px 12px; border-radius: 8px; }
.post .sfw .fig.wide { width: min(1200px, 100vw - 48px); margin-left: calc(50% - min(600px, 50vw - 24px)); }
.post sup.fn { font-size: 0.75em; line-height: 0; }
.post sup.fn a { text-decoration: none; padding: 0 1px; }
.post .fn-list { font-size: 0.9em; }
.post .fn-list li { margin-bottom: 0.4em; }
</style>`;

// The teaser's two asks open the site's feedback form, Userback, which
// production loads (layout.mjs, feedback(); USERBACK_TOKEN). Each button tags
// the report with which ask it was and the page, where the widget offers
// setData; the click then reaches layout.mjs's handler, which opens the form.
// Without the token (staging, the dev server) there is no form, so a marked
// placeholder stands in.
function askButtons(p, feedbackOn) {
  if (!feedbackOn) {
    return `<p class="placeholder" data-placeholder="ask">[Placeholder: the request buttons open the site's feedback form, which loads only on sf-works.org.]</p>`;
  }
  return `<div class="ask-buttons">
<button type="button" data-feedback-open data-ask="next">Ask for this part next</button>
<button type="button" data-feedback-open data-ask="help">Offer to help</button>
</div>
<script>
document.addEventListener("click", function (e) {
  var b = e.target.closest("[data-ask]");
  if (b && window.Userback && typeof Userback.setData === "function") Userback.setData({ ask: b.getAttribute("data-ask"), page: ${JSON.stringify(p.path)} });
});
</script>`;
}

function teaserBody(p, feedbackOn) {
  return `<p class="coming">Coming soon</p>
<h1>${esc(p.front.title)}</h1>
${dateLine(p)}
${p.front.summary ? `<p class="lede">${esc(p.front.summary)}</p>` : ""}
<section class="ask" aria-labelledby="ask-h">
<h2 id="ask-h">Want This Part Sooner?</h2>
<p>We're still working on this part. Tell us if you'd like to see it next, or if you can help with data, a correction or your time.</p>
${askButtons(p, feedbackOn)}
</section>`;
}

// An <img> whose src is relative to the doc's own file. Each is checked to
// exist, published at its address under content/'s mirror, and pointed at
// there, so the page and the board show the same file.
const LOCAL_IMG = /(<img\b[^>]*?\ssrc=")(?![a-z][a-z0-9+.-]*:|\/|#)([^"]+)"/gi;

// Only image files, so a page cannot publish another doc's source or a schema.
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|avif|svg)$/i;

function localImages(html, p) {
  const assets = [];
  const root = fs.realpathSync(p.root ?? CONTENT);
  const out = html.replace(LOCAL_IMG, (_, head, src) => {
    const rel = src.replace(/&amp;/g, "&");
    let decoded;
    try {
      decoded = decodeURI(rel);
    } catch {
      decoded = rel;
    }
    if (!IMAGE_EXT.test(decoded)) throw new Error(`content/${p.src}: ${rel} is not an image file (png, jpg, gif, webp, avif or svg)`);
    const asked = nodePath.resolve(nodePath.dirname(nodePath.join(root, p.src)), decoded);
    if (!fs.existsSync(asked)) throw new Error(`content/${p.src}: image ${rel} is not there (looked for content/${nodePath.relative(root, asked)})`);
    // Resolved through any symlink, so a linked folder cannot reach outside content/.
    const file = fs.realpathSync(asked);
    const under = nodePath.relative(root, file);
    if (under.startsWith("..") || nodePath.isAbsolute(under)) throw new Error(`content/${p.src}: image ${rel} is outside content/`);
    const url = `/${under.split(nodePath.sep).map(encodeURIComponent).join("/")}`;
    assets.push({ path: url, file: under.split(nodePath.sep).join("/"), html: fs.readFileSync(file), sitemap: false });
    return `${head}${url}"`;
  });
  return { html: out, assets };
}

/** One page's HTML, as page() renders it. */
export const renderPage = (p, opts) => renderParts(p, opts).html;

/**
 * One page's HTML and the files it needs published with it: the figure pages
 * its `::scratch` lines frame and the images it shows, as
 * [{path, file, html: Buffer, sitemap: false}].
 */
export function renderParts(p, { feedbackOn = Boolean(process.env.USERBACK_TOKEN) } = {}) {
  let assets = [];
  const draft = p.status === "draft" ? `<p class="draft-band"><strong>Draft, not public.</strong> Shown on staging only; sf-works.org does not build it.</p>\n` : "";
  let inner;
  let scripts = [];
  let style = PAGE_CSS;
  let dataUpdated = null;
  let story = false;
  if (p.status === "teaser") {
    inner = teaserBody(p, feedbackOn);
  } else {
    // Board components (charts, frames) are drawn first, so the footnotes
    // and markdown that follow see single lines of HTML.
    // Code (fences and `spans`) is set aside first, so an example of board
    // syntax inside it stays an example.
    const code = [];
    const masked = dropLeadingH1(p.body).replace(/^(```|~~~)[^\n]*\n[\s\S]*?^\1[ \t]*$|`[^`\n]+`/gm, (m) => `\uE000${code.push(m) - 1}\uE001`);
    const unmask = (t) => t.replace(/\uE000(\d+)\uE001/g, (_, i) => code[Number(i)]);
    // A folder page frames the figure pages in its own embeds/ folder, published
    // beside it, so each version keeps the figures it was published with.
    const ownEmbeds = p.folder ? nodePath.join(p.folder, "embeds") : null;
    const ownUrl = p.folder ? `/${nodePath.relative(fs.realpathSync(p.root ?? CONTENT), fs.realpathSync(p.folder)).split(nodePath.sep).join("/")}/embeds` : null;
    const local = ownEmbeds && fs.existsSync(ownEmbeds)
      ? { names: fs.readdirSync(ownEmbeds).filter((f) => f.endsWith(".html")).map((f) => f.slice(0, -5)), path: (n) => `${ownUrl}/${n}` }
      : null;
    const drawn = mdComponents(masked, `content/${p.src}`, { embeds: embedNames(), local });
    const notes = footnotes(drawn.text.replace(/^## References[ \t]*\n/m, ""), { name: p.src });
    const refs = unmask(notes.text);
    const references = notes.references.replace(/\uE000(\d+)\uE001/g, (_, i) => esc(code[Number(i)].replace(/^`|`$/g, "")).replace(/^/, "<code>").replace(/$/, "</code>"));
    const blocks = sfworksBlocks(refs, `content/${p.src}`);
    scripts = blocks.scripts;
    if (drawn.framed.length) scripts.push(EMBED_SCRIPT);
    // A Buffer is written as it is, so the base-path rewrite leaves the
    // figure's own links alone.
    for (const b of drawn.framed) {
      const at = local?.names.includes(b) ? local.path(b) : embedPath(b);
      const html = local?.names.includes(b) ? embedHTML(b, ownEmbeds) : embedHTML(b);
      assets.push({ path: at, file: `${at.slice(1)}/index.html`, html: Buffer.from(html), sitemap: false });
    }
    const used = [...new Set(blocks.used)];
    const dates = [];
    if (used.length) {
      style = `<style>${sfwCss()}</style>\n${style}`;
      // The blocks show live bike data, so the page says when it was read
      // (pipeline/README.md, update intervals), as the bike post does.
      dates.push(...[].concat(BIKE_DATA_READ));
    }
    // A map story carries the map's scripts once, and the page says when the map's data was read.
    if (drawn.stories) {
      style = `${STORY_HEAD}\n${style}`;
      scripts.push(STORY_SCRIPTS);
      dates.push(dataMeta().read);
      story = true;
    }
    // page() prints the newest of the dates it is given.
    if (dates.length) dataUpdated = dates;
    const body = localImages(marked.parse(blocks.text), p);
    const notesHTML = localImages(references, p);
    assets = assets.concat(body.assets, notesHTML.assets);
    inner = `<h1>${esc(p.front.title)}</h1>
${story && !p.version && !p.versions?.length ? "" : dateLine(p)}
${body.html}
${used.length ? marked.parse(postCredits(used)) : ""}
${notesHTML.html}`;
  }
  const html = page({
    title: p.front.title,
    description: p.front.summary || p.front.title,
    path: p.path,
    dataUpdated,
    body: `${style}
<article class="post md-page${p.status === "teaser" ? " teaser" : ""}">
${draft}${inner}
</article>
${scripts.join("\n")}`,
  });
  return { html, assets };
}

/**
 * The pages as the build publishes them, then the figure pages and images
 * they use, each once: [{path, file, html, sitemap}], where `html` is a
 * Buffer for a file published as it is.
 */
let rendered = null;
export function mdPageFiles(pages, opts) {
  // The build's own list is rendered once; the dev server asks on every miss.
  if (!pages && !opts) return (rendered ??= mdPageFiles(mdPages(), {}));
  const files = [];
  const assets = new Map();
  for (const p of pages ?? mdPages()) {
    const r = renderParts(p, opts);
    // An older version stays out of the sitemap: the latest is the page to find.
    files.push({ path: p.path, file: p.file, html: r.html, sitemap: p.status !== "draft" && !p.version });
    for (const a of r.assets) assets.set(a.file, a);
    // The revision history, at /<path>/v/.
    if (p.versions?.length) files.push({ path: `${p.path}/v`, file: `${p.file.replace(/index\.html$/, "")}v/index.html`, html: historyPage(p), sitemap: false });
  }
  return [...files, ...[...assets.values()].sort((a, b) => a.file.localeCompare(b.file))];
}

/** A folder page's revision history: every published version, newest first. */
function historyPage(p) {
  const rows = [...p.versions].reverse().map((v, i) =>
    `<li><a href="${p.path}/v/${v.n}">Version ${v.n}</a>, ${longDate(v.date)}${i === 0 ? ` (the latest, also at <a href="${p.path}">${p.path}</a>)` : ""}</li>`);
  return page({
    title: `Revision History: ${p.front.title}`,
    description: `Every published version of ${p.front.title}.`,
    path: `${p.path}/v`,
    body: `${PAGE_CSS}
<article class="post md-page">
<h1>Revision History</h1>
<p class="lede">Every published version of <a href="${p.path}">${esc(p.front.title)}</a>. Each opens the page as it was published, with the figures and images it had then.</p>
<ol class="versions" reversed>
${rows.join("\n")}
</ol>
</article>`,
  });
}

/**
 * The front page's Recent Changes list: every published or teaser page, and
 * every listed tool or dashboard page (`extra`, as {path, title, summary,
 * updated}), changed in the 30 days up to the newest change, newest first by
 * date and then by title, at most `n`.
 *
 * Bryan, 2026-11-24: "in recent changes, please show everything that's been
 * edited lately, including dashboards. (But don't count data refreshes as an
 * update — an edit on a dashboard is change in dashboard functionality)". So
 * a dashboard is dated by the last commit to its code (scripts/site-files.mjs,
 * codeFiles), never by when its data was read. The window is measured from the
 * newest change rather than today, so a rebuild with no new commit prints the
 * same list. Empty when there are no pages, so the front page shows no empty
 * heading.
 */
export const RECENT_DAYS = 30;
/** Where the front page wants its Recent Changes list. */
export const RECENT_MARK = "<!--recent-changes-->";
export function recentChanges(pages = mdPages(), n = 12, extra = []) {
  const all = [
    ...pages.filter((p) => p.status !== "draft" && !p.version).map((p) => ({ path: p.path, title: p.front.title, summary: p.front.summary, updated: p.updated, teaser: p.status === "teaser" })),
    ...extra.filter((e) => /^\d{4}-\d{2}-\d{2}/.test(e.updated || "")),
  ];
  const newest = all.map((p) => p.updated).sort().pop();
  const from = newest ? new Date(Date.parse(newest) - RECENT_DAYS * 864e5).toISOString().slice(0, 10) : "";
  const shown = all
    .filter((p) => p.updated >= from)
    .sort((a, b) => (a.updated === b.updated ? a.title.localeCompare(b.title) : a.updated < b.updated ? 1 : -1))
    .slice(0, n);
  if (!shown.length) return "";
  const li = shown.map(
    (p) => `<li><a href="${p.path}">${esc(p.title)}</a>${p.teaser ? ' <span class="tag">coming soon</span>' : ""}<span class="when">Updated <time datetime="${p.updated}">${shortDate(p.updated)}</time></span>${p.summary ? `<span class="line">${esc(p.summary)}</span>` : ""}</li>`,
  );
  return `<section class="recent-changes" aria-labelledby="recent-h">
<h2 id="recent-h">Recent Changes</h2>
<ul class="recent">
${li.join("\n")}
</ul>
</section>
<style>
.recent-changes .recent { list-style: none; padding: 0; margin: 0 0 24px; }
.recent-changes .recent li { margin: 0 0 12px; }
.recent-changes .recent a { font-weight: 600; }
.recent-changes .when { display: block; color: var(--muted); font-size: 0.8rem; }
.recent-changes .line { display: block; color: var(--muted); font-size: 0.95rem; }
</style>`;
}
