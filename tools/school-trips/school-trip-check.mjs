#!/usr/bin/env node
// Router-against-simulation parity for School Trips: the in-browser router (site/src/school-trip-router.mjs) must time sampled trips as school-sim does.
//
// It routes a fixed sample of the simulation's block-school rows (out/school-sim/blocks.json) from
// each block's census interior point (data/extract/census-blocks/2020.json) on site/data/school-trip-graph.json,
// and compares walk and car minutes with the simulation's. Exits 1 when the medians differ by more than the
// limits below, or when the router can't time the car, or drives over twice the walk, on more than LIMITS.untimedPct
// of the sample. The router joins a point, the simulation a block's whole frontage, so they differ a little.
//
//     node tools/school-trips/school-trip-check.mjs            # 400 rows
//     node tools/school-trips/school-trip-check.mjs --n 1000
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeRouter } from "../../site/src/school-trip-router.mjs";

import { ROOT } from "../../site/scripts/lib/repo.mjs";
const LIMITS = { walkMedianPct: 10, carMedianPct: 10, untimedPct: 1, minWalkMin: 10 };
const n = Number((process.argv.indexOf("--n") > 0 && process.argv[process.argv.indexOf("--n") + 1]) || 400);
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

const R = makeRouter(read("site/data/school-trip-graph.json"));
const B = read("out/school-sim/blocks.json"), C = B.columns;
const pts = new Map(read("data/extract/census-blocks/2020.json").records.map((r) => [r.geoid, [r.lon, r.lat]]));
// Rows at least LIMITS.minWalkMin on foot, in a fixed pseudo-random order (a linear congruential generator, seed 1).
const rows = [];
for (let i = 0; i < C.block.length; i++) if (C.walkMin[i] >= LIMITS.minWalkMin) rows.push(i);
let seed = 1;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
for (let i = rows.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [rows[i], rows[j]] = [rows[j], rows[i]]; }

const dw = [], dc = [];
let untimed = 0, done = 0, skipped = 0;
for (const i of rows.slice(0, n)) {
  const home = pts.get(B.geoids[C.block[i]]), sc = R.schools[B.schools[C.school[i]]];
  if (!home || !sc) { skipped++; continue; }
  const t = R.trip(home, sc.door, null);
  if (!t) { skipped++; continue; }
  done++;
  dw.push(Math.abs(t.walk.min - C.walkMin[i]) / C.walkMin[i]);
  if (!t.car.P || t.car.m > 2 * t.walk.m) { untimed++; continue; }
  dc.push(Math.abs(t.car.min - C.carMin[i]) / C.carMin[i]);
}
const q = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? 100 * s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN; };
const res = { rows: done, skipped, walkMedianPct: q(dw, 0.5), walkP90Pct: q(dw, 0.9), carMedianPct: q(dc, 0.5), carP90Pct: q(dc, 0.9),
  untimedPct: (100 * untimed) / Math.max(done, 1) };
console.log("  school-trip-check: %d rows (%d skipped); walk off by %s%% median, %s%% at p90; car %s%% median, %s%% at p90; car untimed or over 2x the walk %s%%",
  res.rows, res.skipped, res.walkMedianPct.toFixed(1), res.walkP90Pct.toFixed(1), res.carMedianPct.toFixed(1), res.carP90Pct.toFixed(1), res.untimedPct.toFixed(2));
const bad = [];
if (done < 0.9 * Math.min(n, rows.length)) bad.push(`only ${done} of ${Math.min(n, rows.length)} rows routed`);
if (!(res.walkMedianPct <= LIMITS.walkMedianPct)) bad.push(`walk median off by ${res.walkMedianPct.toFixed(1)}% (limit ${LIMITS.walkMedianPct}%)`);
if (!(res.carMedianPct <= LIMITS.carMedianPct)) bad.push(`car median off by ${res.carMedianPct.toFixed(1)}% (limit ${LIMITS.carMedianPct}%)`);
if (!(res.untimedPct <= LIMITS.untimedPct)) bad.push(`car untimed on ${res.untimedPct.toFixed(2)}% (limit ${LIMITS.untimedPct}%)`);
if (bad.length) { console.error("  school-trip-check: FAIL: " + bad.join("; ")); process.exit(1); }
console.log("  school-trip-check: router and simulation agree");
