#!/usr/bin/env node
// Refuse a repo state that publishes something private, across every tracked
// file (site/, tools/, pipeline/, lib/, data/, out/, research/ and the rest).
// site/scripts/check-public.mjs guards the site's own boundary; this one
// guards the whole repo, since all of it is public.
//
//   node pipeline/check-public-repo.mjs          # exit 1 on any finding
//   node pipeline/check-public-repo.mjs --list   # print what is checked
//
// It fails on:
//   - a link to the private working repo (the sf-works repo on GitHub, as
//     against this one, sf-works-site);
//   - an individual city staff email address (first.last@ a city domain).
//     Institutional inboxes (SlowStreets@SFMTA.com, bos@sfgov.org) are the
//     published way to reach a body and pass; so do elected officials' own
//     published addresses and the few listed in ALLOWED_EMAILS;
//   - a path on someone's computer (a macOS home or mounted-volume folder);
//   - a private network hostname (*.ts.net, a Tailscale tailnet);
//   - a Cloud Storage bucket named in full (gs://name; gs://$VARIABLE passes);
//   - a review-board id (a task, review item, doc or board: t-, r-, d- or w-
//     and 12 random characters) or a board thread id ("thread" and 12);
//   - any name in the PRIVATE_NAMES setting (comma-separated, from the
//     environment or the gitignored local-settings.json): the cloud project,
//     bucket and server names, which this file cannot list without
//     publishing them. CI passes it as a secret;
//   - a relative markdown link to a file the repo doesn't have.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const SELF = path.relative(ROOT, import.meta.filename);
const MAX_BYTES = 40_000_000;

// Elected officials' own published addresses (Mayor and Board, sfgov.org), the
// author's own published address, and test fixtures with made-up people.
const ALLOWED_EMAILS = new Set([
  "daniel.lurie@sfgov.org",
  "board.of.supervisors@sfgov.org",
  "fryanpan@gmail.com",
  "jane.roe@sfdpw.org",
]);
const CITY_DOMAINS = /@(?:[a-z0-9-]+\.)*(?:sfgov|sfmta|sfdpw|sfwater|sfpuc|sfport|sfcta|sfusd|sfplanning|sfdph|sfpl|sfrecpark|sfenvironment|sfdbi|sfhsa|sfmayor|sftc|sfcityattorney|sfdem|sfdhr|sfgsa|sfo|sfmuni|sfhousing|sfpd|sffire)\.(?:org|com|edu|gov|net)\b/i;

function setting(key) {
  if (process.env[key]) return process.env[key];
  try {
    const v = JSON.parse(fs.readFileSync(path.join(ROOT, "local-settings.json"), "utf8"))[key];
    return Array.isArray(v) ? v.join(",") : v || "";
  } catch {
    return "";
  }
}
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// A name under 6 characters would match ordinary words, so it is ignored.
const privateNames = setting("PRIVATE_NAMES").split(",").map((s) => s.trim()).filter((s) => s.length >= 6);

const RULES = [
  ["a link to the private repo", /github\.com\/fryanpan\/sf-works(?!-site)(?![A-Za-z0-9_-])/g],
  ["a path on a computer", /(?<![A-Za-z0-9_.~-])\/(?:Users|Volumes)\/[A-Za-z0-9._-]+/g],
  ["a private network hostname", /\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b/gi],
  ["a storage bucket named in full", /\bgs:\/\/(?!\$)[a-z0-9][a-z0-9._-]{2,}/g],
  ["a review-board id", /(?<![A-Za-z0-9_-])[tdrw]-(?=[A-Za-z0-9_-]{0,11}[A-Z0-9])[A-Za-z0-9_-]{12}(?![A-Za-z0-9_-])/g],
  ["a board thread id", /\bthreads? (?=[a-z0-9]{0,11}[0-9])[a-z0-9]{12}\b/g],
  ...privateNames.map((n) => ["a private name from PRIVATE_NAMES", new RegExp(escapeRe(n), "gi")]),
];
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;

// A Markdown link or image whose target is a relative path.
const MD_LINK = /!?\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"\n]*")?\s*\)/g;

if (process.argv.includes("--list")) {
  for (const [what, re] of RULES) console.log(`${what}: ${what.includes("PRIVATE_NAMES") ? "(hidden)" : re.source}`);
  console.log(`a staff email address: first.last at ${CITY_DOMAINS.source}`);
  console.log("a relative markdown link to a missing file");
  if (!privateNames.length) console.log("PRIVATE_NAMES is not set: the private-name rule checks nothing");
  process.exit(0);
}

function trackedFiles() {
  try {
    const out = execFileSync("git", ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], {
      cwd: ROOT,
      maxBuffer: 256 * 1024 * 1024,
    });
    return out.toString("utf8").split("\0").filter(Boolean);
  } catch {
    const files = [];
    const skip = new Set([".git", "node_modules", "dist", ".astro", ".wrangler", ".cache", "scratch", "__pycache__"]);
    (function walk(dir) {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (skip.has(e.name)) continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else files.push(path.relative(ROOT, full));
      }
    })(ROOT);
    return files;
  }
}

const files = trackedFiles();
const present = new Set(files);
const failures = [];
const lineOf = (text, index) => text.slice(0, index).split("\n").length;

for (const rel of files) {
  if (rel === SELF) continue;
  const full = path.join(ROOT, rel);
  let stat;
  try {
    stat = fs.statSync(full);
  } catch {
    continue; // deleted in the working tree
  }
  if (!stat.isFile() || stat.size > MAX_BYTES) continue;
  const text = fs.readFileSync(full, "utf8");
  if (text.includes("\0")) continue; // binary

  for (const [what, re] of RULES) {
    re.lastIndex = 0;
    for (const m of text.matchAll(re)) {
      failures.push(`${rel}:${lineOf(text, m.index)}: ${what}: ${what.includes("PRIVATE_NAMES") ? "(hidden)" : m[0]}`);
    }
  }

  for (const m of text.matchAll(EMAIL)) {
    const addr = m[0].toLowerCase();
    const local = addr.split("@")[0];
    if (ALLOWED_EMAILS.has(addr) || !CITY_DOMAINS.test(addr)) continue;
    // An individual's address is first.last (or first_last); an inbox is one word.
    if (/^[a-z]+[._][a-z]+(?:[._][a-z]+)?$/.test(local)) {
      failures.push(`${rel}:${lineOf(text, m.index)}: a staff email address: ${m[0]} (link the city's own record instead)`);
    }
  }

  if (/\.mdx?$/i.test(rel)) {
    // Fenced code is not a link.
    const prose = text.replace(/^(```|~~~)[\s\S]*?^\1/gm, (block) => block.replace(/[^\n]/g, " "));
    for (const m of prose.matchAll(MD_LINK)) {
      let target = m[1];
      if (/^(?:[a-z][a-z0-9+.-]*:|#|\/|\{|<)/i.test(target)) continue; // a URL, an anchor, a site path, a template
      target = target.split("#")[0].split("?")[0];
      if (!target) continue;
      try {
        target = decodeURIComponent(target);
      } catch {}
      const resolved = path.normalize(path.join(path.dirname(rel), target)).replace(/\/$/, "");
      if (resolved.startsWith("..")) {
        failures.push(`${rel}:${lineOf(text, m.index)}: a link out of the repo: ${m[1]}`);
        continue;
      }
      const isDir = files.some((f) => f.startsWith(resolved + "/"));
      if (!present.has(resolved) && !isDir && !fs.existsSync(path.join(ROOT, resolved))) {
        failures.push(`${rel}:${lineOf(text, m.index)}: a link to a file this repo doesn't have: ${m[1]}`);
      }
    }
  }
}

if (failures.length) {
  console.error(`check-public-repo: ${failures.length} finding(s) in a repo that is public:\n`);
  for (const f of failures) console.error("  " + f);
  console.error("\nScrub it at its source (fix the generator, not the output), or move the setting to local-settings.json.");
  process.exit(1);
}
console.log(
  `check-public-repo: clean (${files.length} files${privateNames.length ? "" : "; PRIVATE_NAMES not set, so private names were not checked"})`,
);
