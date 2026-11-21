#!/usr/bin/env node
// Check every folder page's published versions (src/page-versions.mjs).
//
//   node scripts/check-versions.mjs              # the copies under content/
//   node scripts/check-versions.mjs --dist dist  # and the built pages for them
//
// Fails when versions.json is not numbered 1, 2, 3 … in date order; when a
// listed version's folder is missing or has no page file; when its files no
// longer hash to what versions.json recorded, which means a published version
// was edited; when a versions/<n>/ folder is not listed; and, with --dist,
// when the build has no page at /<path>/v/<n>/ or no revision history at
// /<path>/v/. Part of `npm run check` and the deploy (.github/workflows/deploy.yml).

import fs from "node:fs";
import nodePath from "node:path";
import { CONTENT } from "../src/md-pages.mjs";
import { VERSIONS_DIR, VERSIONS_FILE, folderHash, readVersions, versionDir, pageFileIn } from "../src/page-versions.mjs";

/** Every folder under `root` holding versions/versions.json, as paths relative to it. */
function versionedFolders(root) {
  const out = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!e.isDirectory() || (e.name === "posts" && dir === root) || e.name.startsWith(".")) continue;
      const d = nodePath.join(dir, e.name);
      if (e.name === VERSIONS_DIR) {
        if (fs.existsSync(nodePath.join(d, VERSIONS_FILE))) out.push(nodePath.relative(root, dir));
        continue; // the copies inside are checked through versions.json, never walked as pages
      }
      walk(d);
    }
  };
  if (fs.existsSync(root)) walk(root);
  return out.sort();
}

export function checkVersions({ content = CONTENT, dist = null } = {}) {
  const problems = [];
  const notices = [];
  let count = 0;
  for (const rel of versionedFolders(content)) {
    const folder = nodePath.join(content, rel);
    const at = `content/${rel.split(nodePath.sep).join("/")}`;
    let versions;
    try {
      versions = readVersions(folder);
    } catch (e) {
      problems.push(e.message);
      continue;
    }
    if (!pageFileIn(folder)) problems.push(`${at}: has versions but no page.md or page.mdx`);
    // A page this build hides (a draft on sf-works.org, a hidden tool) has no versions built either.
    const built = Boolean(dist) && fs.existsSync(nodePath.join(dist, rel, "index.html"));
    versions.forEach((v, i) => {
      count++;
      if (v.n !== i + 1) problems.push(`${at}: versions.json lists version ${v.n} where ${i + 1} belongs`);
      if (i && v.date < versions[i - 1].date) problems.push(`${at}: version ${v.n} is dated before version ${versions[i - 1].n}`);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v.date || "") || !v.hash || !v.commit) problems.push(`${at}: version ${v.n} needs a date, a commit and a hash`);
      const dir = versionDir(folder, v.n);
      if (!fs.existsSync(dir)) return problems.push(`${at}: version ${v.n} is published but versions/${v.n}/ is gone`);
      if (!pageFileIn(dir)) problems.push(`${at}: versions/${v.n}/ has no page.md or page.mdx`);
      const now = folderHash(dir);
      if (now !== v.hash) problems.push(`${at}: versions/${v.n}/ was edited after it was published (its files hash to ${now.slice(0, 19)}…, versions.json recorded ${String(v.hash).slice(0, 19)}…)`);
      if (built) {
        const page = nodePath.join(dist, rel, "v", String(v.n), "index.html");
        if (!fs.existsSync(page)) problems.push(`${at}: the build has no page at /${rel.split(nodePath.sep).join("/")}/v/${v.n}/`);
      }
    });
    // Not a failure: an edit not yet published as a version. The page still says the latest version's number.
    if (versions.length && folderHash(folder, VERSIONS_DIR) !== versions[versions.length - 1].hash) {
      notices.push(`${at}: edited since version ${versions[versions.length - 1].n}; run \`npm run new-version -- ${rel.split(nodePath.sep).join("/")}\` to publish the edit as a version`);
    }
    const listed = new Set(versions.map((v) => String(v.n)));
    for (const d of fs.readdirSync(nodePath.join(folder, VERSIONS_DIR), { withFileTypes: true })) {
      if (d.isDirectory() && !listed.has(d.name)) problems.push(`${at}: versions/${d.name}/ is not in versions.json`);
    }
    if (built && versions.length && !fs.existsSync(nodePath.join(dist, rel, "v", "index.html"))) {
      problems.push(`${at}: the build has no revision history at /${rel.split(nodePath.sep).join("/")}/v/`);
    }
  }
  return { problems, count, notices };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const at = process.argv.indexOf("--dist");
  const dist = at === -1 ? null : nodePath.resolve(process.argv[at + 1]);
  const { problems, count, notices } = checkVersions({ dist });
  for (const n of notices) console.log(`check-versions: note: ${n}`);
  if (problems.length) {
    console.error(`check-versions: ${problems.length} problem(s):`);
    for (const p of problems) console.error(`  ${p}`);
    process.exit(1);
  }
  console.log(`check-versions: ${count} published version(s), every folder present and unchanged${dist ? ", every one built" : ""}`);
}
