#!/usr/bin/env node
// Fail the build when a page computes a headline number itself, or the figure registry is stale.
//
// Retro of 2026-10-14, change 5: each headline number is written once to site/data/figures.json by the script that
// computes it (site/src/figures.mjs), and pages read it from there. This check enforces that in four parts:
//
//   1. Registry: every figure names its writer in "by", that file exists and calls writeFigures.
//   2. Fresh: each School Trips writer, rerun with --check, would write the same file (both are light: no simulation).
//   3. Pages: in the code a page module runs at build time, no call that computes a figure: a model's alone, hurt,
//      range, fig, figC, schoolFig, schoolFigC, cost, schoolCost or schoolSafety (on MD, md or model), the budget
//      planner's planAll, planGreedy, tableSum or replanHurt, or a sum over a plan's carsBy. Building a model with
//      makeCityModel needs a "figures-ok: <reason>" comment on that line or the one above, since a page may need the
//      model's inputs and counts but never its figures. Browser code is not scanned: template literal text, and the
//      body of any function whose source the page ships with ${name.toString()} (the tool's client()). The ${...}
//      holes in a template run at build time and are scanned.
//   4. Keys: every figure("literal key") a page reads is in the registry.
//
// Limits, said plainly: it reads source text, not a running build, so a model method called through another name
// (const f = MD.alone; f(...)) or arithmetic on registry values gets past it; the browser's live recomputation as a
// reader moves the controls is the tool working and is out of scope; and prose with numbers typed into it (the
// verbatim public comment in site/content) is not checked against the registry.
//
//   node site/scripts/check-figures.mjs

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const SITE = path.resolve(import.meta.dirname, "..");
const REPO = path.dirname(SITE);
const FIG = path.join(SITE, "data", "figures.json");
const PAGES = path.join(SITE, "src", "pages");
const WRITERS = [["tools/school-trips/school-trips-figures.mjs", "--check"], ["tools/school-trips/school-budget-plans.mjs", "--figures-only", "--check"]];
const failures = [];

// -- 1. registry --
const REG = fs.existsSync(FIG) ? JSON.parse(fs.readFileSync(FIG, "utf8")).figures || {} : null;
if (!REG) failures.push("site/data/figures.json is missing: run node tools/school-trips/school-trips-figures.mjs");
const owners = new Set(Object.values(REG || {}).map((f) => f.by));
for (const by of owners) {
  const p = path.join(REPO, by || "");
  if (!by || !fs.existsSync(p)) failures.push(`figures.json: owner ${by} does not exist`);
  else if (!fs.readFileSync(p, "utf8").includes("writeFigures(")) failures.push(`figures.json: ${by} never calls writeFigures`);
}

// -- 2. fresh --
if (REG && !process.argv.includes("--no-fresh")) {
  for (const [script, ...args] of WRITERS) {
    const r = spawnSync(process.execPath, [path.join(REPO, script), ...args], { cwd: REPO, encoding: "utf8" });
    if (r.status !== 0) failures.push(`${script} ${args.join(" ")}: ${(r.stdout + r.stderr).trim().split("\n").pop()}`);
  }
}

// -- 3. pages: the build-time code of each page module --
/** The source with comments, string contents and template-literal text blanked to spaces (newlines kept), so only
 * code that runs when the module is imported is left, ${...} holes included. */
export function buildTimeCode(src) {
  const out = src.split("");
  const blank = (i) => { if (out[i] !== "\n") out[i] = " "; };
  const stack = []; // "tpl" for a template literal, a number for brace depth inside a ${...} hole
  let i = 0, prev = "";
  const regexOk = () => !prev || "(,=:[!&|?{};+-*%<>~^".includes(prev);
  while (i < src.length) {
    const c = src[i], top = stack[stack.length - 1];
    if (top === "tpl") {
      if (c === "\\") { blank(i); blank(i + 1); i += 2; continue; }
      if (c === "`") { stack.pop(); i++; prev = "`"; continue; }
      if (c === "$" && src[i + 1] === "{") { stack.push(0); i += 2; prev = "{"; continue; }
      blank(i); i++; continue;
    }
    if (c === "/" && src[i + 1] === "/") { while (i < src.length && src[i] !== "\n") blank(i++); continue; }
    if (c === "/" && src[i + 1] === "*") { const e = src.indexOf("*/", i + 2); const j = e < 0 ? src.length : e + 2; while (i < j) blank(i++); continue; }
    if (c === "'" || c === '"') {
      i++;
      while (i < src.length && src[i] !== c && src[i] !== "\n") { if (src[i] === "\\") blank(i++); blank(i++); }
      i++; prev = c; continue;
    }
    if (c === "/" && regexOk()) {
      let j = i + 1, cls = false;
      while (j < src.length && src[j] !== "\n") {
        if (src[j] === "\\") { j += 2; continue; }
        if (src[j] === "[") cls = true; else if (src[j] === "]") cls = false; else if (src[j] === "/" && !cls) break;
        j++;
      }
      if (src[j] === "/") { for (let k = i + 1; k < j; k++) blank(k); i = j + 1; prev = "/"; continue; }
    }
    if (c === "`") { stack.push("tpl"); i++; continue; }
    if (typeof top === "number") {
      if (c === "{") stack[stack.length - 1]++;
      else if (c === "}") { if (top === 0) { stack.pop(); i++; prev = "}"; continue; } stack[stack.length - 1]--; }
    }
    if (!/\s/.test(c)) prev = c;
    i++;
  }
  return out.join("");
}

/** Blank the bodies of the functions a page ships to the browser as source, ${name.toString()} or ${fnSource(name)}. */
export function dropShipped(src, code) {
  const names = new Set([...src.matchAll(/\$\{\s*(?:fnSource\(\s*([A-Za-z_][\w]*)\s*\)|([A-Za-z_][\w]*)\.toString\(\))\s*\}/g)].map((m) => m[1] || m[2]));
  const out = code.split("");
  for (const name of names) {
    const m = new RegExp(`\\bfunction\\s+${name}\\s*\\(`).exec(code);
    if (!m) continue;
    let depth = 0;
    for (let i = code.indexOf("{", m.index); i >= 0 && i < code.length; i++) {
      if (code[i] === "{") depth++;
      else if (code[i] === "}" && --depth === 0) break;
      if (out[i] !== "\n") out[i] = " ";
    }
  }
  return out.join("");
}

const COMPUTE = [
  [/\b(MD|md|model)\s*\.\s*(alone|hurt|range|figC|fig|schoolFigC|schoolFig|cost|schoolCost|schoolSafety)\s*\(/, "calls the model for a figure"],
  [/\b(planAll|planGreedy|tableSum|replanHurt)\s*\(/, "runs the budget planner"],
  [/carsBy\s*\)\s*\.\s*reduce\b/, "sums a plan's cars"],
];
const BUILD = [/\bmakeCityModel\s*\(/, "builds the model"];
const pageFiles = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? pageFiles(path.join(dir, e.name)) : e.name.endsWith(".mjs") ? [path.join(dir, e.name)] : []);
const literalKeys = new Set();
for (const file of pageFiles(PAGES)) {
  const src = fs.readFileSync(file, "utf8"), raw = src.split("\n"), code = dropShipped(src, buildTimeCode(src)).split("\n");
  const rel = path.relative(REPO, file);
  const ok = (n) => /figures-ok:\s*\S/.test(raw[n] || "") || /figures-ok:\s*\S/.test(raw[n - 1] || "");
  code.forEach((line, n) => {
    for (const [re, what] of COMPUTE) if (re.test(line) && !ok(n)) failures.push(`${rel}:${n + 1}: ${what} at build time; read it from figures.json (figure(key)) instead`);
    if (BUILD[0].test(line) && !ok(n)) failures.push(`${rel}:${n + 1}: ${BUILD[1]} at build time with no "figures-ok: <reason>" comment`);
  });
  for (const m of src.matchAll(/\bfigure(?:Entry)?\(\s*(["'])([^"'`]+)\1\s*\)/g)) literalKeys.add(`${rel}|${m[2]}`);
}

// -- 4. keys --
for (const k of literalKeys) {
  const [rel, key] = k.split("|");
  if (REG && !REG[key]) failures.push(`${rel}: reads figure "${key}", which figures.json doesn't hold`);
}

if (failures.length) {
  console.error("check-figures: a headline number isn't coming from site/data/figures.json:\n");
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
console.log(`check-figures: clean (${Object.keys(REG).length} figures from ${owners.size} scripts; ${literalKeys.size} literal reads)`);
