// The date beside each page in the site's lists: the home page (its Recent Changes too), the Mobility front page,
// and every list src/directory.mjs fills. The Muni dashboard's two links carry none: its Draft band gives the date.
//
// Bryan, 2026-11-20: "Can you update sf works so each page and dashboard shows when it was last published or
// updated in the directory pages?"
//
// One date a page, in one format ("Nov 20, 2026"):
//
//   Data updated <date>   a page whose module exports `dataUpdated`, the date (or dates, the newest wins) its
//                         data was read. It is the value the page passes to page({ dataUpdated }), so the list
//                         and the line under the page's own title agree.
//   Updated <date>        any other page: the last commit to its source files, which are its page module and
//                         whatever its `dateFiles` export adds (paths from site/, such as "content/home.md").
//
// The commit date is git's committer date (%cs), so a merged PR dates the page by its merge, and a build with
// no new commit and no new data prints the same dates. The tracked copy in data/page-dates.json stands in where
// git can't give a page's real date:
//   - the newest commit to the files is the repo's first commit (the import): this repo started from one commit
//     of a working repo's files (ADR 0002), so that commit's date is the import's, not the page's. The copy
//     carries the date each page had before the import, until a later commit to it takes over;
//   - a clone with no history for the files (a shallow clone, a tarball).
// `node scripts/page-dates.mjs --write` refreshes the copy and `--check` (part of `npm run check`) keeps it
// complete. The copy also dates the markdown pages under content/ the same way, keyed by their path from site/
// (src/md-pages.mjs, lastUpdated).
//
// A page that lists another writes dateMark(path) where the date goes, and scripts/site-files.mjs fills every
// mark from the listed pages (fillDates). A listed page with no date stops the build (checkDates).

import fs from "node:fs";
import nodePath from "node:path";
import { execFileSync } from "node:child_process";

const SITE = nodePath.resolve(import.meta.dirname, "..");
export const FALLBACK_FILE = nodePath.join(SITE, "data", "page-dates.json");

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const ISO = /^\d{4}-\d{2}-\d{2}/;

/** "2026-11-20" as "Nov 20, 2026". */
export const shortDate = (iso) => `${MONTHS[+iso.slice(5, 7) - 1]} ${+iso.slice(8, 10)}, ${iso.slice(0, 4)}`;

/** The newest of a page's data dates as YYYY-MM-DD, or "" when it has none. */
export const newestDate = (dates) =>
  [].concat(dates || []).filter((d) => ISO.test(String(d || ""))).map((d) => String(d).slice(0, 10)).sort().pop() || "";

const git = (args, cwd) => {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
};

/** The repo's first commit (the import), or "" with no repository. */
export const importCommit = (cwd = SITE) => git(["rev-list", "--max-parents=0", "HEAD"], cwd).split("\n")[0] || "";

/** The date of the last commit to any of `files` (paths under `cwd`), or "" where git can't say: no repository,
 *  no commit for the files yet, a shallow clone, whose one commit would date every page alike, or a newest
 *  commit that is the import commit, whose date is the import's. */
export function gitDate(files, cwd = SITE) {
  if (git(["rev-parse", "--is-shallow-repository"], cwd) !== "false") return "";
  const [hash, date] = git(["log", "-1", "--format=%H %cs", "--", ...files], cwd).split(" ");
  if (!hash || hash === importCommit(cwd)) return "";
  return date || "";
}

/** The tracked copy of the content dates, {path: "YYYY-MM-DD"}, or {} with no file. */
export function readFallback(file = FALLBACK_FILE) {
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
}

/** A page's source files, from site/: its module, then its `dateFiles`. */
export const sourceFiles = (moduleName, mod) => [`src/pages/${moduleName}`, ...(mod.dateFiles || [])];

/**
 * A listed page's date, as {label, date}, or null when nothing dates it.
 * `page` is {path, dataUpdated, files}; `opts.gitDate` and `opts.fallback` stand in for git and the tracked
 * copy in the tests.
 */
export function resolveDate(page, opts = {}) {
  const data = newestDate(page.dataUpdated);
  if (data) return { label: "Data updated", date: data };
  const fromGit = (opts.gitDate || gitDate)(page.files || []);
  const date = ISO.test(fromGit) ? fromGit.slice(0, 10) : (opts.fallback || readFallback())[page.path] || "";
  return ISO.test(date) ? { label: "Updated", date: date.slice(0, 10) } : null;
}

/** Throws, naming every listed page that has no date. */
export function checkDates(entries) {
  const missing = entries.filter((e) => !e.date || !ISO.test(e.date.date || "")).map((e) => e.path);
  if (missing.length) {
    throw new Error(`page-dates: ${missing.length} listed page(s) with no date: ${missing.join(", ")}. Export \`dataUpdated\` from the page's module, commit its source files, or run \`node scripts/page-dates.mjs --write\` in site/.`);
  }
}

/** The small line a list shows: "Data updated Nov 20, 2026". */
export const dateLine = (d) => `<span class="dir-date">${d.label} <time datetime="${d.date}">${shortDate(d.date)}</time></span>`;

/** Where a page that lists `path` wants that page's date; fillDates puts it there. */
export const dateMark = (path) => `<!--page-date:${path}-->`;
const MARK = /<!--page-date:([^>]*?)-->/g;

/** The HTML with every dateMark replaced by its page's date line. A mark for a page that isn't listed, or has
 *  no date, stops the build. */
export function fillDates(html, entries) {
  return html.replace(MARK, (_, path) => {
    const e = entries.find((x) => x.path === path);
    if (!e || !e.date) throw new Error(`page-dates: a list shows ${path}, which has no date`);
    return dateLine(e.date);
  });
}
