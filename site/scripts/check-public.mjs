#!/usr/bin/env node
// Refuse to build if anything private has reached the published site.
//
// The site under `site/` is what goes out to the world. Working research
// notes, topic files and proposals are not in this repo, and a page that reads
// one would carry it onto the open internet. So this runs before every build
// and deploy, walks `site/`, and exits non-zero on a reference to anything
// outside the repo. pipeline/check-public-repo.mjs runs the matching check
// over the whole repo.
//
//   node site/scripts/check-public.mjs

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const SKIP = new Set([".git", "node_modules", "dist", ".wrangler", ".astro"]);

// Paths that only exist in the private repo. A reference to one means either a
// file was copied across or a build step is reaching outside this tree.
const FORBIDDEN_PATHS = [/\btopics\//, /\bnotes\//, /\bproposals\//, /\bdigests\//];

// Any traversal out of this repo, however it is spelled.
const ESCAPES = [/\.\.\/\.\.\//, /\bsf-works\/(topics|notes|proposals|digests)\b/];

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else yield full;
  }
}

const failures = [];

for (const file of walk(ROOT)) {
  const rel = path.relative(ROOT, file);

  for (const pattern of FORBIDDEN_PATHS) {
    if (pattern.test(rel)) {
      failures.push(`${rel}: a path that belongs to the private repo exists here`);
    }
  }

  // Binary and large files are not scanned for text; nothing here should be either.
  const stat = fs.statSync(file);
  if (stat.size > 20_000_000) continue;
  let text;
  try {
    text = fs.readFileSync(file, "utf8");
  } catch {
    continue;
  }
  // A NUL byte means the file is binary. The escape keeps THIS file plain
  // text, so grep, git diff and a reviewer can all still read it.
  if (text.includes("\0")) continue;

  for (const pattern of [...FORBIDDEN_PATHS, ...ESCAPES]) {
    const match = text.match(pattern);
    if (!match) continue;
    // This file describes the rule, so naming the paths is the point.
    if (rel === "scripts/check-public.mjs") continue;
    const line = text.slice(0, match.index).split("\n").length;
    failures.push(`${rel}:${line}: reads or names ${match[0]}, which is private`);
  }
}

if (failures.length) {
  console.error("site/ is published, and something private reached it:\n");
  for (const f of failures) console.error("  " + f);
  console.error("\nMove it out of site/, or publish the fact without the source.");
  process.exit(1);
}

console.log("check-public: clean");
