#!/usr/bin/env node
// Publish the next version of a folder page (src/page-versions.mjs).
//
//   npm run new-version -- transportation/whitepaper
//   npm run new-version -- comments/x --date 2026-11-16 --commit <sha>   # version 1 of a page already live
//
// Copies content/<path>/, all of it except versions/, into
// content/<path>/versions/<n>/, where n is one more than the last, and adds
// {n, date, commit, hash} to content/<path>/versions/versions.json. The date is
// today in San Francisco and the commit HEAD unless --date and --commit give
// them (for a page already live, its last commit and that commit's date); the hash is the copy's folder hash, which scripts/check-versions.mjs
// holds it to from then on. Commit the new folder and versions.json; the
// next deploy publishes /<path>/v/<n>.

import fs from "node:fs";
import nodePath from "node:path";
import { execFileSync } from "node:child_process";
import { CONTENT } from "../src/md-pages.mjs";
import { VERSIONS_DIR, VERSIONS_FILE, folderHash, readVersions, versionDir, pageFileIn, filesUnder } from "../src/page-versions.mjs";

export function newVersion(folder, { date, commit } = {}) {
  const name = pageFileIn(folder);
  if (!name) throw new Error(`new-version: ${folder} has no page.md or page.mdx`);
  // A draft is not built on sf-works.org, so a version of one would be a permalink to nothing.
  const front = (fs.readFileSync(nodePath.join(folder, name), "utf8").match(/^﻿?---[ \t]*\n([\s\S]*?)\n---/) || [])[1] || "";
  if (!/^status:[ \t]*["']?(published|teaser)["']?[ \t]*$/m.test(front)) throw new Error(`new-version: ${name} is a draft; set status: published before publishing a version`);
  const versions = readVersions(folder);
  const n = versions.length ? versions[versions.length - 1].n + 1 : 1;
  const to = versionDir(folder, n);
  if (fs.existsSync(to)) throw new Error(`new-version: ${to} already exists; a published version is never written over`);
  if (date && versions.length && date < versions[versions.length - 1].date) throw new Error(`new-version: ${date} is before version ${n - 1}'s date`);
  for (const rel of filesUnder(folder, VERSIONS_DIR)) {
    fs.mkdirSync(nodePath.dirname(nodePath.join(to, rel)), { recursive: true });
    fs.copyFileSync(nodePath.join(folder, rel), nodePath.join(to, rel));
  }
  const entry = { n, date: date || today(), commit: commit || git(folder, "rev-parse", "HEAD"), hash: folderHash(to) };
  fs.writeFileSync(nodePath.join(folder, VERSIONS_DIR, VERSIONS_FILE), JSON.stringify({ versions: [...versions, entry] }, null, 1) + "\n");
  return entry;
}

const today = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const git = (cwd, ...args) => {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
};

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const take = (flag) => {
    const at = args.indexOf(flag);
    return at === -1 ? undefined : args.splice(at, 2)[1];
  };
  const date = take("--date");
  const commit = take("--commit");
  if (args.length !== 1 || (date !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(date))) {
    console.error("usage: npm run new-version -- <path under content/> [--date YYYY-MM-DD]");
    process.exit(2);
  }
  const folder = nodePath.join(CONTENT, args[0].replace(/^\/+|\/+$/g, ""));
  try {
    const v = newVersion(folder, { date, commit });
    console.log(`new-version: /${args[0].replace(/^\/+|\/+$/g, "")}/v/${v.n}, dated ${v.date}, ${v.hash.slice(0, 19)}…`);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}
