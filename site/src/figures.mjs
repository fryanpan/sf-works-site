// The figure registry, site/data/figures.json: each headline number is written once, by the script that computes
// it, and every page reads it from here. Retro of 2026-10-14, change 5: "The same figure came from two scripts, so
// pages disagreed with themselves."
//
// A figure is { value, by, ...extra }. `by` names the one script allowed to write it; writeFigures refuses a key
// another script owns, and drops the keys its own script no longer writes, so a figure can't outlive its computation.
// The file is sorted and stamp-free, so a rerun on the same inputs leaves it byte for byte the same.
//
// Pages call figure(key) at build time. It throws on a missing key rather than falling back to computing the number,
// which is the whole point. site/scripts/check-figures.mjs fails the build when a page computes a headline itself.

import fs from "node:fs";
import nodePath from "node:path";

export const FIGURES_PATH = nodePath.join(import.meta.dirname, "..", "data", "figures.json");

let CACHE = null;
function load() {
  if (CACHE) return CACHE;
  if (!fs.existsSync(FIGURES_PATH)) return (CACHE = { note: "", figures: {} });
  return (CACHE = JSON.parse(fs.readFileSync(FIGURES_PATH, "utf8")));
}

/** One figure's value. Throws when the registry doesn't hold it: run the script the error names. */
export function figure(key) {
  const f = load().figures[key];
  if (!f) throw new Error(`figures.json has no ${key}; run the script that owns it (site/data/figures.json lists each key's "by")`);
  return f.value;
}

/** The whole entry, value and provenance. */
export function figureEntry(key) {
  const f = load().figures[key];
  if (!f) throw new Error(`figures.json has no ${key}`);
  return f;
}

const sortDeep = (x) => (Array.isArray(x) ? x.map(sortDeep) : x && typeof x === "object"
  ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, sortDeep(x[k])])) : x);

/**
 * Write `entries` ({ key: { value, ...extra } }) as owned by `by` (a repo path such as "tools/school-trips/school-trips-figures.mjs").
 * Keys `by` owned before and doesn't write now are removed. Returns true when the file changed, or with dryRun would
 * change (the writers' --check, which site/scripts/check-figures.mjs runs to catch a stale registry).
 */
export function writeFigures(by, entries, { path = FIGURES_PATH, dryRun = false } = {}) {
  const cur = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, "utf8")) : { figures: {} };
  const figs = {};
  for (const [k, f] of Object.entries(cur.figures || {})) if (f.by !== by) figs[k] = f;
  for (const [k, f] of Object.entries(entries)) {
    if (figs[k]) throw new Error(`figures.json: ${k} belongs to ${figs[k].by}; ${by} may not write it`);
    if (!f || !("value" in f)) throw new Error(`figures.json: ${k} has no value`);
    if (typeof f.value === "number" && !Number.isFinite(f.value)) throw new Error(`figures.json: ${k} is ${f.value}`);
    figs[k] = { ...f, by };
  }
  const out = {
    note: "Each headline number, written once by the script named in its \"by\" and read by every page that prints it "
      + "(site/src/figures.mjs). Never edit by hand: rerun the script.",
    figures: sortDeep(figs),
  };
  const text = JSON.stringify(out, null, 1) + "\n";
  const old = fs.existsSync(path) ? fs.readFileSync(path, "utf8") : null;
  if (old === text) return false;
  if (dryRun) return true;
  fs.writeFileSync(path, text);
  CACHE = null;
  return true;
}
