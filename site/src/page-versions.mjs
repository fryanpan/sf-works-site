// Published versions of a folder page (Bryan, 2026-11-18, thread on the
// whitepaper outline: "for each page in the space, have it be
// sf-works.org/transportation/whitepaper/v/3 that goes to an older version and
// the root is always the latest").
//
// A folder page is content/<path>/page.md or page.mdx with whatever it uses
// beside it: images, figure pages under embeds/. It publishes at /<path>.
//
//   content/<path>/page.mdx                 the latest, at /<path>
//   content/<path>/versions/<n>/            the whole folder as it was when version n
//                                           was published, minus versions/, at /<path>/v/<n>
//   content/<path>/versions/versions.json   {"versions": [{n, date, commit, hash}]}
//
// `npm run new-version -- <path>` (scripts/new-version.mjs) adds the next one.
// Each version renders from its own copied files, so new data or a new image in
// the live folder never changes an old version. The layout code is today's.
// scripts/check-versions.mjs fails when a listed version's folder is gone, when
// its files no longer hash to what versions.json recorded (a published version
// was edited), or when the build lacks a /<path>/v/<n>/ page.

import crypto from "node:crypto";
import fs from "node:fs";
import nodePath from "node:path";

export const VERSIONS_DIR = "versions";
export const VERSIONS_FILE = "versions.json";
/** The page file a folder holds, if any: page.mdx before page.md. */
export const pageFileIn = (dir) => ["page.mdx", "page.md"].find((f) => fs.existsSync(nodePath.join(dir, f))) || null;

/**
 * Every file under `dir`, as sorted relative paths with "/" separators. Leaves
 * out a folder named `skip` at any depth (a nested folder page's versions are
 * its own) and every dotfile, which git and the Finder make and nobody wrote
 * (.DS_Store), so a copy and its hash hold only the page's files.
 */
export function filesUnder(dir, skip = null) {
  const out = [];
  const walk = (d, rel) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.name.startsWith(".") || (e.isDirectory() && e.name === skip)) continue;
      if (e.isDirectory()) walk(nodePath.join(d, e.name), r);
      else if (e.isFile()) out.push(r);
    }
  };
  walk(dir, "");
  return out.sort();
}

/**
 * The content hash of a version's folder: SHA-256 over each file's relative
 * path and the SHA-256 of its bytes, in sorted order. Any edit, added file or
 * removed file changes it.
 */
export function folderHash(dir, skip = null) {
  const h = crypto.createHash("sha256");
  for (const rel of filesUnder(dir, skip)) {
    const bytes = fs.readFileSync(nodePath.join(dir, rel));
    h.update(`${rel}\0${crypto.createHash("sha256").update(bytes).digest("hex")}\n`);
  }
  return `sha256:${h.digest("hex")}`;
}

/** A folder page's versions.json, as [{n, date, commit, hash}], or [] if it has none. */
export function readVersions(folder) {
  const f = nodePath.join(folder, VERSIONS_DIR, VERSIONS_FILE);
  if (!fs.existsSync(f)) return [];
  const v = JSON.parse(fs.readFileSync(f, "utf8"));
  if (!Array.isArray(v.versions)) throw new Error(`${f}: needs a "versions" list`);
  return v.versions;
}

export const versionDir = (folder, n) => nodePath.join(folder, VERSIONS_DIR, String(n));

export const longDate = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

/** The line under the latest page's title. */
export const versionLine = (path, v) =>
  `<p class="data-updated version-line">Last updated <time datetime="${v.date}">${longDate(v.date)}</time>. Version ${v.n}. See the <a href="${path}/v/">revision history</a>.</p>`;

/** The line under an older version's title, which says it is one and where the latest is. */
export const olderLine = (path, v, latest) =>
  v.n === latest
    ? `<p class="version-line older">Version ${v.n}, published <time datetime="${v.date}">${longDate(v.date)}</time>. This is the latest version, also at <a href="${path}">${path}</a>. See the <a href="${path}/v/">revision history</a>.</p>`
    : `<p class="version-line older">Version ${v.n}, published <time datetime="${v.date}">${longDate(v.date)}</time>. This is an older version. See the <a href="${path}">latest version</a> or the <a href="${path}/v/">revision history</a>.</p>`;
