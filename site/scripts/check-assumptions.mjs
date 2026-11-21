#!/usr/bin/env node
// School Trips' assumptions check (retro of 2026-10-14, change 2).
//
// Reads site/data/school-trips-assumptions.json, one row per model input and causal link, and:
//   1. fails on a row with no source (a citation or "judgment"), no low or no high, a low above its value or a value
//      above its high, or no dataTest field (which may say "none");
//   2. reruns the All Changes headline (site/src/school-trips-inputs.mjs) at each row's low and high and prints its
//      share of each headline: kids hurt prevented a year, students out of single-family cars, yearly and one-time cost.
//      A share is the larger move at either end over the central headline. A row is rerun one of three ways:
//        light  makeCityModel again with the row's param at that end (P.assume, a COSTS key, or the sim's case);
//        alone  the change's own low or high from makeCityModel's alone(), put in place of its central the way the
//               model's range() combines changes: a stand-in where the input lives inside the simulation's sets;
//        sim    not rerun: it needs tools/school-trips/school-sim.py, and the row is listed as unrerun.
//   3. flags any row over the table's flagShare (a third) of a headline. A flagged row must carry a "reread" entry,
//      { date, finding }, saying its evidence was reread at that weight, or the check fails.
//
//   node site/scripts/check-assumptions.mjs           (about 10 seconds, no simulation)
//   node site/scripts/check-assumptions.mjs --quiet   (failures and flags only)

import fs from "node:fs";
import path from "node:path";

const SITE = path.resolve(import.meta.dirname, "..");
const FILE = process.env.ASSUMPTIONS_FILE || path.join(SITE, "data", "school-trips-assumptions.json");
const QUIET = process.argv.includes("--quiet");
const T = JSON.parse(fs.readFileSync(FILE, "utf8"));
const failures = [];
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const ids = new Set();

// -- 1. every row declares its source, low, high and data test --
for (const [i, r] of (T.rows || []).entries()) {
  const at = `row ${i + 1} (${r.id || "no id"})`;
  if (!r.id) failures.push(`${at}: no id`);
  else if (ids.has(r.id)) failures.push(`${at}: duplicate id`);
  ids.add(r.id);
  if (!(typeof r.source === "string" && r.source.trim())) failures.push(`${at}: no source (cite it, or write "judgment")`);
  for (const k of ["value", "low", "high"]) if (!isNum(r[k])) failures.push(`${at}: no ${k}`);
  if (isNum(r.low) && isNum(r.value) && isNum(r.high) && !(r.low <= r.value && r.value <= r.high)) failures.push(`${at}: low ${r.low}, value ${r.value}, high ${r.high} out of order`);
  if (typeof r.dataTest !== "string" || !r.dataTest.trim()) failures.push(`${at}: no dataTest (say which data test it passed, or "none")`);
  if (!["light", "alone", "sim", "none"].includes(r.rerun)) failures.push(`${at}: rerun must be light, alone, sim or none`);
  if (r.rerun === "light" && !r.param) failures.push(`${at}: a light rerun needs a param`);
  if (!["input", "causal", "cost"].includes(r.kind)) failures.push(`${at}: kind must be input, causal or cost`);
}

// -- 2. each row's share of the headline --
const { loadCityModel, headline } = await import(path.join(SITE, "src", "school-trips-inputs.mjs"));
const KEYS = [["hurt", "kids hurt prevented"], ["cars", "out of cars"], ["year", "yearly cost"], ["once", "one-time cost"]];
const base = loadCityModel(), H0 = headline(base.MD, base.CJ);
const ALONE_ID = { yellow_bus: "yellow_bus", assign: "assign_ncp52" };

function lightAt(r, v) {
  // The sim's three cases: the headline read from the sets' low or high case (0 or 2), with every other input central.
  if (r.param === "case") return headline(base.MD, base.CJ, v);
  const m = r.param.startsWith("cost.") ? loadCityModel({ cost: { [r.param.slice(5)]: v } }) : loadCityModel({ assume: { [r.param]: v } });
  return headline(m.MD, m.CJ);
}
function aloneAt(r, k) {
  const MD = base.MD, id = ALONE_ID[r.levers[0]], a = MD.alone(id);
  const ons = MD.onIds(H0.c);
  if (!ons.includes(id)) throw new Error(`${r.id}: ${id} isn't in All Changes`);
  const hurt = MD.HB * (1 - ons.reduce((t, x) => t * (1 - (x === id ? a.hurt[k] : MD.alone(x).hurt[1]) / MD.HB), 1));
  return { hurt, cars: H0.cars + a.cars[k] - a.cars[1], year: H0.year + a.yearK[k] - a.yearK[1], once: H0.once };
}
const results = [];
for (const r of T.rows || []) {
  if (!isNum(r.low) || !isNum(r.high)) continue;
  if (r.rerun !== "light" && r.rerun !== "alone") { results.push({ r, share: null }); continue; }
  let lo, hi;
  try {
    [lo, hi] = r.rerun === "light" ? [lightAt(r, r.low), lightAt(r, r.high)] : [aloneAt(r, 0), aloneAt(r, 2)];
  } catch (e) { failures.push(`${r.id}: rerun failed: ${e.message}`); continue; }
  const share = Object.fromEntries(KEYS.map(([k]) => [k, Math.abs(H0[k]) > 1e-9 ? Math.max(Math.abs(lo[k] - H0[k]), Math.abs(hi[k] - H0[k])) / Math.abs(H0[k]) : 0]));
  results.push({ r, share, lo, hi });
}

// -- 3. flags --
const FLAG = T.flagShare ?? 1 / 3;
const pct = (x) => `${Math.round(100 * x)}%`.padStart(5);
const flagged = results.filter((x) => x.share && KEYS.some(([k]) => x.share[k] > FLAG));
for (const x of flagged) {
  const over = KEYS.filter(([k]) => x.share[k] > FLAG).map(([k, l]) => `${l} ${pct(x.share[k]).trim()}`).join(", ");
  const rr = x.r.reread;
  if (!(rr && rr.date && rr.finding)) failures.push(`${x.r.id}: carries ${over} of the headline, over a third, and has no reread { date, finding }: reread its evidence at that weight and record what it showed`);
}

if (!QUIET) {
  console.log(`All Changes headline, central case: ${H0.hurt.toFixed(2)} kids hurt prevented a year, ${Math.round(H0.cars)} students out of single-family cars, $${H0.year.toFixed(2)}M a year and $${H0.once.toFixed(2)}M once`);
  console.log(`Each input's share of it, the larger move at its low or high:\n`);
  console.log(`  ${"input".padEnd(26)} ${"rerun".padEnd(6)} ${"hurt".padStart(5)} ${"cars".padStart(5)} ${"year".padStart(5)} ${"once".padStart(5)}`);
  const rank = (x) => (x.share ? Math.max(...KEYS.map(([k]) => x.share[k])) : -1);
  for (const x of results.slice().sort((a, b) => rank(b) - rank(a))) {
    const s = x.share ? KEYS.map(([k]) => pct(x.share[k])).join(" ") : "  not rerun: needs the simulation or is a measured figure";
    console.log(`  ${x.r.id.padEnd(26)} ${x.r.rerun.padEnd(6)} ${s}${x.share && KEYS.some(([k]) => x.share[k] > FLAG) ? "  << over a third: reread" : ""}`);
  }
  const unrerun = results.filter((x) => !x.share).length, judg = (T.rows || []).filter((r) => /^judgment\b/i.test(r.source)).length;
  const untested = (T.rows || []).filter((r) => /^none\b/i.test(r.dataTest || "")).length;
  console.log(`\n${(T.rows || []).length} rows: ${judg} rest on judgment, ${untested} passed no data test, ${unrerun} not rerun here.`);
}
if (failures.length) {
  console.error("\ncheck-assumptions: failed\n");
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
console.log(`check-assumptions: clean (${(T.rows || []).length} rows, ${flagged.length} over a third, each reread)`);
