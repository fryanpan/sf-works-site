// Repo paths for the site's scripts and tests, the JavaScript side of lib/paths.py.
//
//   import { ROOT, SITE, script } from "./lib/repo.mjs";   (the path relative to the importing file)
//
// ROOT is the repo root and SITE is site/. script(name) finds a file by its exact name under pipeline/,
// tools/ and lib/, as paths.script() does in Python; it throws when the name matches no file or more than one.
import fs from "node:fs";
import path from "node:path";

const HERE = import.meta.dirname;

// This file sits in site/scripts/lib, three folders below the repo root.
export const ROOT = path.resolve(HERE, "..", "..", "..");
export const SITE = path.join(ROOT, "site");

const SEARCH = ["pipeline", "tools", "lib"];
const SKIP = new Set(["__pycache__", "node_modules", ".git"]);
let index = null;

function build() {
  const found = new Map();
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (SKIP.has(e.name)) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else found.set(e.name, [...(found.get(e.name) || []), full]);
    }
  };
  for (const top of SEARCH) walk(path.join(ROOT, top));
  return found;
}

export function script(name) {
  index ??= build();
  const hits = index.get(name) || [];
  if (hits.length === 0) throw new Error(`repo.script: no file named ${name} under ${SEARCH.join(", ")}`);
  if (hits.length > 1) throw new Error(`repo.script: ${name} names more than one file: ${hits.join(", ")}`);
  return hits[0];
}
