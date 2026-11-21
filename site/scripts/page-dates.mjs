#!/usr/bin/env node
// The tracked copy of each listed page's content date, data/page-dates.json, which a build reads only where git
// can't date a page's source files: no history, or a newest commit that is the repo's first, the import
// (src/page-dates.mjs). It holds each markdown page under content/ too, by its path from site/.
//
//   node scripts/page-dates.mjs --write   set every listed page's date from git; changes nothing when none moved
//   node scripts/page-dates.mjs --check   exit 1 when a listed page has no entry (part of `npm run check`)
//
// --check asks only that every listed page has an entry, not that it is the newest date: the date of a commit
// isn't known until the commit is made, so the copy may trail git by a change.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FALLBACK_FILE, readFallback, gitDate, sourceFiles } from "../src/page-dates.mjs";

// Every page module with a listing, whatever this build hides, so the copy is the same on staging and production.
process.env.SITE_SHOW_HIDDEN = "1";
const PAGES = path.resolve(import.meta.dirname, "..", "src", "pages");
const listed = [];
for (const name of fs.readdirSync(PAGES).filter((f) => f.endsWith(".mjs")).sort()) {
  const mod = await import(pathToFileURL(path.join(PAGES, name)).href);
  if (mod.listing && !mod.redirect && !mod.asset) listed.push({ path: mod.path, files: sourceFiles(name, mod) });
}

// The markdown pages under content/ (src/md-pages.mjs reads the same set), by their path from site/.
const SITE = path.resolve(import.meta.dirname, "..");
const md = fs
  .readdirSync(path.join(SITE, "content"), { recursive: true })
  .map((f) => String(f).split(path.sep).join("/"))
  .filter((f) => /\.mdx?$/.test(f) && f.split("/")[0] !== "posts" && !/(^|\/)versions\/\d+\//.test(f))
  .map((f) => `content/${f}`)
  .sort();

const have = readFallback();
if (process.argv.includes("--write")) {
  const out = {};
  for (const p of [...listed].sort((a, b) => a.path.localeCompare(b.path))) {
    const d = gitDate(p.files) || have[p.path];
    if (!d) throw new Error(`page-dates: ${p.path} has no commit yet and no entry; commit ${p.files.join(", ")} first`);
    out[p.path] = d;
  }
  // A markdown page with no commit yet is dated by its file until it has one, so it may have no entry.
  for (const f of md) {
    const d = gitDate([f]) || have[f];
    if (d) out[f] = d;
  }
  const text = JSON.stringify(out, null, 2) + "\n";
  if (!fs.existsSync(FALLBACK_FILE) || fs.readFileSync(FALLBACK_FILE, "utf8") !== text) fs.writeFileSync(FALLBACK_FILE, text);
  console.log(`page-dates: ${Object.keys(out).length} listed pages in data/page-dates.json`);
} else {
  const missing = listed.filter((p) => !have[p.path]).map((p) => p.path);
  if (missing.length) {
    console.error(`page-dates: ${missing.length} listed page(s) missing from data/page-dates.json: ${missing.join(", ")}. Run \`node scripts/page-dates.mjs --write\` in site/.`);
    process.exit(1);
  }
  console.log(`page-dates: ${listed.length} listed pages, each with a date in data/page-dates.json`);
}
