#!/usr/bin/env node
// The uncertainty log's check (retro of 2026-10-14, change 3): fails when a School Trips lever cites a study with no
// row in data/evidence/studies.json, or a row is missing a grade.
//
// 1. Rows: each study has an id, a citation, levers, a kind (behaviour, crash or cost), a Maryland SMS level (1 to 5)
//    for a behaviour study, an FHWA CMF star rating (1 to 5, or "unrated" with the reason) for a crash effect, GRADE
//    indirectness (none, serious or very serious, with a sentence) on population, intervention, comparison and
//    outcome, a benefit-transfer size match (match, partial or mismatch), and whether its cost is from the same
//    program as its effect (true, false or "no cost"). A grade the notes can't support may be null only when the
//    row's gaps says what is missing, and a row may have no url only on the same terms.
// 2. Citations: every study id in site/data/school-trips-assumptions.json has a row, and every link a lever cites
//    is a study row's url or a listed document (an agency plan, dataset, budget or news story, which isn't graded):
//    the links in tools/school-trips/school-sim.py's CHANGES, in COSTS and in the About page's link table (L) in
//    site/src/pages/transportation-school-trips*.mjs.
//
//   node site/scripts/check-studies.mjs      (run by the site's npm run check)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ROOT, script } from "./lib/repo.mjs";
const LOG = process.env.STUDIES_FILE || path.join(ROOT, "data", "evidence", "studies.json");
const ASSUME = path.join(ROOT, "site", "data", "school-trips-assumptions.json");
const failures = [];
const D = JSON.parse(fs.readFileSync(LOG, "utf8"));
const RATING = ["none", "serious", "very serious"];
const has = (s) => typeof s === "string" && s.trim().length > 0;
const norm = (u) => u.replace(/#.*$/, "").replace(/\/$/, "").replace(/%2E/gi, ".").toLowerCase();

// -- 1. rows --
const ids = new Map(), urls = new Set();
for (const r of D.studies || []) {
  const at = r.id || "a row with no id";
  const gap = has(r.gaps);
  if (!has(r.id)) failures.push(`${at}: no id`);
  else if (ids.has(r.id)) failures.push(`${at}: duplicate id`);
  ids.set(r.id, r);
  if (!has(r.citation)) failures.push(`${at}: no citation`);
  if (has(r.url)) urls.add(norm(r.url)); else if (!gap) failures.push(`${at}: no url, and gaps doesn't say why`);
  if (!Array.isArray(r.levers) || !r.levers.length) failures.push(`${at}: names no lever`);
  if (!["behaviour", "crash", "cost"].includes(r.kind)) failures.push(`${at}: kind must be behaviour, crash or cost`);
  const q = r.quality || {};
  if (r.kind === "behaviour") {
    if (q.sms == null) { if (!gap) failures.push(`${at}: a behaviour study with no Maryland SMS level, and gaps doesn't say what's missing`); }
    else if (![1, 2, 3, 4, 5].includes(q.sms)) failures.push(`${at}: SMS must be 1 to 5`);
    if (!has(q.smsWhy)) failures.push(`${at}: no smsWhy`);
  }
  if (r.kind === "crash") {
    if (!([1, 2, 3, 4, 5].includes(q.cmfStars) || q.cmfStars === "unrated")) failures.push(`${at}: a crash effect needs CMF stars 1 to 5 or "unrated"`);
    if (!has(q.cmfWhy)) failures.push(`${at}: no cmfWhy`);
  }
  for (const k of ["population", "intervention", "comparison", "outcome"]) {
    const x = (r.indirectness || {})[k];
    if (!x || !RATING.includes(x.rating) || !has(x.why)) failures.push(`${at}: GRADE indirectness on ${k} needs a rating (${RATING.join(", ")}) and a why`);
  }
  const t = r.transfer || {};
  if (!["match", "partial", "mismatch"].includes(t.sizeMatch) || !has(t.why)) failures.push(`${at}: transfer needs sizeMatch (match, partial, mismatch) and a why`);
  if (!has(t.studyEffect) || !has(t.ourEffect)) failures.push(`${at}: transfer needs the study's effect beside ours`);
  const c = r.cost || {};
  if (!(c.sameProgram === true || c.sameProgram === false || c.sameProgram === "no cost") || !has(c.why)) failures.push(`${at}: cost.sameProgram must be true, false or "no cost", with a why`);
  if (!Array.isArray(r.gradedFrom) || !r.gradedFrom.length) failures.push(`${at}: gradedFrom names no note`);
}
const docs = new Set();
for (const d of D.documents || []) {
  if (!has(d.url) || !has(d.why)) failures.push(`document ${d.url || "(no url)"}: needs a url and why it isn't a study`);
  else docs.add(norm(d.url));
}

// -- 2. citations --
const A = JSON.parse(fs.readFileSync(ASSUME, "utf8"));
for (const r of A.rows || []) for (const s of r.studies || []) if (!ids.has(s)) failures.push(`assumptions ${r.id}: cites study ${s}, which has no row in the uncertainty log`);

const URL_RE = /https?:\/\/[^\s"'`<>]+/g;
const cited = [];
const sim = fs.readFileSync(script("school-sim.py"), "utf8");
const ch = sim.slice(sim.indexOf("\nCHANGES = {"), sim.indexOf("\n}\n", sim.indexOf("\nCHANGES = {")));
for (const u of ch.match(URL_RE) || []) cited.push(["tools/school-trips/school-sim.py CHANGES", u]);
for (const f of ["transportation-school-trips.mjs", "transportation-school-trips-about.mjs"]) {
  const src = fs.readFileSync(path.join(ROOT, "site", "src", "pages", f), "utf8");
  for (const [start, name] of [["export const COSTS = {", "COSTS"], ["const L = {", "L"]]) {
    const i = src.indexOf(start);
    if (i < 0) continue;
    const block = src.slice(i, src.indexOf("\n};", i));
    for (const u of block.match(URL_RE) || []) cited.push([`${f} ${name}`, u]);
  }
}
const missing = new Map();
for (const [where, u] of cited) {
  const n = norm(u.replace(/[.,;]+$/, ""));
  if (!urls.has(n) && !docs.has(n)) missing.set(n, where);
}
for (const [u, where] of missing) failures.push(`${where} cites ${u}, which is neither a study row nor a listed document: grade it (the grade-study skill) or list it`);

if (failures.length) {
  console.error("check-studies: the uncertainty log is incomplete\n");
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
const crash = (D.studies || []).filter((r) => r.kind === "crash"), unrated = crash.filter((r) => r.quality.cmfStars === "unrated").length;
console.log(`check-studies: clean (${ids.size} studies, ${docs.size} documents, ${cited.length} lever citations covered; ${unrated} of ${crash.length} crash effects have no CMF star rating)`);
