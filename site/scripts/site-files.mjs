// Every file the site publishes, rendered from the page modules in src/pages.
//
// Astro builds the site (astro.config.mjs). It asks this module for the list
// of files and their bytes through one catch-all endpoint,
// astro/pages/[...file].ts, so the page modules keep rendering their own HTML
// exactly as they did under the old hand-written build. A real Astro page
// (.astro or .md under astro/pages/) sits beside the catch-all and wins over it
// for its own address.
//
// A page module exports `file` (where it lands in dist), `path` (its address)
// and `render()`. Data comes from JSON under data/, written by the collectors
// in this repo, so a build never reaches the network and never reaches outside
// this tree. The page metadata schema the board's editor shares is
// content/.workspaces/doc-metadata.schema.json (src/md-pages.mjs). Every module in
// src/pages is picked up; there is no list to keep.
//
// `astro build` loads this file through Node itself, not bundled by Vite (the
// endpoint imports it with @vite-ignore), so the page modules'
// import.meta.dirname and process.env mean what they always meant. `astro dev`
// loads it through Vite's module runner (scripts/dev-render.mjs), which gives
// them the same values and lets an edit drop the loaded copy.

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { ORIGIN } from "../src/layout.mjs";
import { pathShown, archivedTo } from "../src/features.mjs";
import { redirectPage } from "../src/redirect.mjs";
import { fillDirectory, fillCrumbs } from "../src/directory.mjs";
import { mdPageFiles, mdPages, recentChanges, RECENT_MARK } from "../src/md-pages.mjs";
import { resolveDate, checkDates, fillDates, sourceFiles, gitDate, readFallback } from "../src/page-dates.mjs";

const ROOT = path.resolve(import.meta.dirname, "..");
const PAGES = path.join(ROOT, "src", "pages");

// SITE_BASE_PATH serves the whole site under a path prefix ("/x/y", no
// trailing slash) for a host that proxies it there, such as the board's
// resource frame. Every root-relative href, src, action, content and CSS url()
// in the rendered HTML gets the prefix; absolute URLs, fragments and
// protocol-relative forms do not. Unset, the output is byte-identical to a
// build with no prefix. Production at sf-works.org never sets it.
export const BASE = (process.env.SITE_BASE_PATH || "").replace(/\/+$/, "");
const ROOT_URL = /((?:href|src|action|content|poster)=")\/(?!\/)/g;
const CSS_URL = /url\((["']?)\/(?!\/)/g;
// A redirect page's <meta http-equiv="refresh" content="0; url=/..."> too.
const REFRESH_URL = /(content="\d+;\s*url=)\/(?!\/)/g;
export const withBase = (html) =>
  BASE ? html.replace(ROOT_URL, `$1${BASE}/`).replace(CSS_URL, `url($1${BASE}/`).replace(REFRESH_URL, `$1${BASE}/`) : html;

// The maps' geometry and the mile basis, checked before anything is written:
// a bad shape, a project map missing its blocks (scripts/check-geometry.mjs)
// or a page on a different mile basis (scripts/check-mile-basis.mjs) stops the
// build. Returns the error lines; empty means pass.
export async function checkSite() {
  const { checkGeometry } = await import("./check-geometry.mjs");
  const { checkMileBasis } = await import("./check-mile-basis.mjs");
  return [...checkGeometry(), ...checkMileBasis()];
}

let rendered = null;

// [{file, body}] in write order, where `file` is the path under dist/ and
// `body` a string or a Buffer. Rendered once per process.
export function siteFiles() {
  rendered ??= render();
  return rendered;
}

// The page modules' file names, sorted, so every page is found with no list
// to keep.
function moduleNames() {
  const modules = fs
    .readdirSync(PAGES)
    .filter((f) => f.endsWith(".mjs"))
    .sort();
  if (modules.length === 0) throw new Error("build: no pages under src/pages");
  return modules;
}

async function loadModule(name) {
  const mod = await import(/* @vite-ignore */ pathToFileURL(path.join(PAGES, name)).href);
  if (!mod.file || !mod.path || typeof mod.render !== "function") {
    throw new Error(`build: ${name} must export \`file\`, \`path\` and \`render()\``);
  }
  return mod;
}

// The listed pages this build shows, as [{path, title, line, parent?, order?, views?}], from each page
// module's `listing` export (src/directory.mjs). A page hidden on this build
// (src/features.mjs) is left out, so no list links to a page that isn't there.
// Each carries `date`, the date its lists show beside it (src/page-dates.mjs): when its data was read, or its
// source files' last commit. A listed page with no date stops the build.
const dates = new Map(); // a page's date, asked of git once a process
function listingsOf(mods) {
  const names = moduleNames();
  const dateOf = (m, name) => {
    if (!dates.has(m.path)) dates.set(m.path, resolveDate({ path: m.path, dataUpdated: m.dataUpdated, files: sourceFiles(name, m) }));
    return dates.get(m.path);
  };
  const listed = mods
    .map((m, i) => [m, names[i]])
    .filter(([m]) => m.listing && !m.redirect && !m.asset && pathShown(m.path))
    .map(([m, name]) => ({ ...m.listing, path: m.path, line: m.listing.line || "", date: dateOf(m, name) }));
  checkDates(listed);
  return listed;
}
// A page module's code, from site/, for dating its last change of function: the module and the local
// modules it imports directly, leaving out any that more than SHARED page modules import (layout, the
// directory, chart helpers), whose edits would date every page at once. Data files are never code, so a
// data refresh doesn't date a dashboard.
const SHARED = 3;
const importsOf = (name) => {
  const src = fs.readFileSync(path.join(PAGES, name), "utf8");
  return [...src.matchAll(/from\s+["'](\.\.?\/[^"']+\.m?js)["']/g)]
    .map((m) => path.relative(ROOT, path.resolve(PAGES, m[1])))
    .filter((f) => f.startsWith("src" + path.sep) && fs.existsSync(path.join(ROOT, f)));
};
function codeFiles(names) {
  const imports = new Map(names.map((n) => [n, importsOf(n)]));
  const uses = new Map();
  for (const list of imports.values()) for (const f of list) uses.set(f, (uses.get(f) || 0) + 1);
  return (name) => [`src/pages/${name}`, ...imports.get(name).filter((f) => uses.get(f) <= SHARED)];
}
// The listed pages Recent Changes shows beside the markdown pages, each dated by its code's last commit.
// A draft listing stays off the front page, as it stays off every list outside its own section.
let recentExtra = null;
function recentOf(mods) {
  if (recentExtra) return recentExtra;
  const names = moduleNames();
  const filesOf = codeFiles(names);
  const fallback = readFallback();
  recentExtra = mods
    .map((m, i) => [m, names[i]])
    .filter(([m]) => m.listing && !m.listing.draft && !m.redirect && !m.asset && pathShown(m.path))
    .map(([m, name]) => ({ path: m.path, title: m.listing.title, summary: m.listing.line || "", updated: gitDate(filesOf(name)) || fallback[m.path] || "" }));
  return recentExtra;
}
const withRecentChanges = (html, mods) => (html.includes(RECENT_MARK) ? html.replace(RECENT_MARK, recentChanges(mdPages(), undefined, recentOf(mods))) : html);

async function allModules() {
  const mods = [];
  for (const name of moduleNames()) mods.push(await loadModule(name));
  return mods;
}
// The redirect page left at an archived page's address (src/features.mjs ARCHIVED_PAGES).
const archivedPage = (p) => redirectPage(archivedTo(p), "Mobility");

// A page as published: its list of the pages under it, its breadcrumb and the dates of the pages it lists
// filled in, then the base path.
let currentMods = [];
const finish = (html, pagePath, listed) => withBase(fillDates(fillCrumbs(fillDirectory(withRecentChanges(html, currentMods), pagePath, listed), listed), listed));

// The dev server's one-page render (scripts/dev-render.mjs): the file under
// dist/ that `file` names, rendered exactly as the build renders it, or null.
// Only the module that owns it renders. A module's own page is found from its
// `file` export without rendering anything; a family page (`pages()`) costs
// that one family's render, kept until the next edit reloads this module.
// The sitemap renders everything, since it lists everything.
const families = new Map();
export async function renderFile(file) {
  if (file === "sitemap.xml" || file === "robots.txt") {
    return (await siteFiles()).find((f) => f.file === file) ?? null;
  }
  const all = await allModules();
  currentMods = all;
  const listed = listingsOf(all);
  if (file === "404.html") {
    return { file, body: finish((await loadModule("home.mjs")).render(), "/", listed) };
  }
  const mods = [];
  for (const [i, name] of moduleNames().entries()) {
    const mod = all[i];
    if (!pathShown(mod.path)) {
      if (mod.file === file && archivedTo(mod.path)) return { file, body: withBase(archivedPage(mod.path)) };
      continue;
    }
    if (mod.file === file) return { file, body: finish(mod.render(), mod.path, listed) };
    if (typeof mod.pages === "function") mods.push([name, mod]);
  }
  for (const [name, mod] of mods) {
    if (!families.has(name)) families.set(name, mod.pages());
    const p = families.get(name).find((x) => x.file === file);
    if (p) return { file, body: Buffer.isBuffer(p.html) ? p.html : finish(p.html, p.path, listed) };
  }
  const md = mdPageFiles().find((x) => x.file === file);
  if (md) return { file, body: Buffer.isBuffer(md.html) ? md.html : finish(md.html, md.path, listed) };
  return null;
}

async function render() {
  const modules = moduleNames();

  const files = [];
  const paths = [];

  const all = await allModules();
  currentMods = all;
  const listed = listingsOf(all);

  for (const mod of all) {
    // A tool not yet released (src/features.mjs) is not built at all, so none
    // of its pages can be reached, linked or listed.
    if (!pathShown(mod.path)) {
      // An archived page leaves a redirect page at its address, so old links land somewhere.
      if (archivedTo(mod.path)) {
        console.log(`  ${mod.file}  archived, redirects to ${archivedTo(mod.path)}`);
        files.push({ file: mod.file, body: withBase(archivedPage(mod.path)) });
      } else console.log(`  ${mod.file}  hidden`);
      continue;
    }
    // A module that exports `redirect` renders a page that only sends the
    // reader on, so it stays out of the sitemap: the address it points at is
    // already there.
    // A draft (`sitemap = false`, as the Muni dashboard's pages export) is published but kept out too.
    if (!mod.redirect && !mod.asset && mod.sitemap !== false) paths.push(mod.path);
    files.push({ file: mod.file, body: finish(mod.render(), mod.path, listed) });

    // A module may also render a family of pages — one per project, say — by
    // exporting `pages()`, which returns `{path, file, html}` for each. They
    // are published and listed in the sitemap like any other page, except one
    // marked `sitemap: false` (an old address kept only so its links still
    // land). A Buffer is a file published as it is, such as a photo a page
    // loads lazily rather than inlining (the bike overview's explorer cards).
    if (typeof mod.pages === "function") {
      for (const p of mod.pages()) {
        files.push({ file: p.file, body: Buffer.isBuffer(p.html) ? p.html : finish(p.html, p.path, listed) });
        if (p.sitemap !== false && mod.sitemap !== false) paths.push(p.path);
      }
    }
  }

  // The markdown pages under content/ (src/md-pages.mjs): a page with front
  // matter is published at its own address, drafts only where hidden pages
  // are shown, with the figure pages and images it uses. Their front matter is checked here, so a bad page stops the build.
  for (const p of mdPageFiles()) {
    // A Buffer is a figure page or image a page uses (src/md-pages.mjs),
    // published as it is and kept out of the sitemap.
    files.push({ file: p.file, body: Buffer.isBuffer(p.html) ? p.html : finish(p.html, p.path, listed) });
    if (p.sitemap) paths.push(p.path);
  }

  // A sitemap and a robots.txt, built from the pages that actually rendered,
  // so neither can list a page that no longer exists. Staging serves the same
  // files; the worker adds X-Robots-Tag: noindex there, which is what keeps it
  // unindexed.
  //
  // No <lastmod>: the only date available here is the build date, and a
  // rebuild that changed nothing would claim every page had changed. Each page
  // already carries the dates its figures were read, which is the honest version.
  files.push({
    file: "sitemap.xml",
    body: `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${paths.map((p) => `  <url><loc>${ORIGIN}${p}</loc></url>`).join("\n")}
</urlset>
`,
  });
  files.push({
    file: "robots.txt",
    body: `User-agent: *
Allow: /

Sitemap: ${ORIGIN}/sitemap.xml
`,
  });
  // A 404 that keeps the reader on the site rather than dropping them.
  files.push({
    file: "404.html",
    body: finish((await import(/* @vite-ignore */ pathToFileURL(path.join(PAGES, "home.mjs")).href)).render(), "/", listed),
  });

  const seen = new Set();
  for (const { file } of files) {
    if (seen.has(file)) throw new Error(`build: two pages write ${file}`);
    seen.add(file);
  }
  console.log(`build: ${modules.length} page modules, ${files.length} files${BASE ? ` under ${BASE}` : ""}`);
  return files;
}
