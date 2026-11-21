#!/usr/bin/env node
// Fail the build when two pages would count a mile two ways.
//
//   node scripts/check-mile-basis.mjs      (the build runs it first: astro.config.mjs)
//
// Audit criterion F1 (pipeline/transportation-data-audit-criteria.md):
// every "mi" on the site means the same thing. The one basis is the plan's,
// miles per direction of travel (lib/mile_basis.py), converted by the
// pipeline step that makes each figure. Four checks, from data/ alone:
//
//   1. Every data file a page takes miles from declares `mileBasis`, and all
//      of them declare the same one.
//   2. The overview's miles (bike-history/history.json) are the sum of its
//      blocks (bike-history/components.json, the latest year's row miles per
//      block), so the headline figure and the per-block figure are one count.
//   3. north-star/status.json's `m` for a plan block is that block's row miles
//      in components.json times the share of the block the plan draws
//      (north-star/traced.geojson). A block counted at two rows where the
//      layer holds three, or counted whole where the plan covers part, fails.
//   4. Where two files give miles for the same plan block, they agree with
//      status.json: each project's planMiles on Current Projects, and each
//      repaved block's miles in the repave lever.
// A label cannot pass on its own: checks 2 to 4 compare the numbers.

import fs from "node:fs";
import path from "node:path";

const DATA = path.resolve(import.meta.dirname, "..", "data");
const MILE = 1609.344;
const read = (rel) => JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8"));

// Every file a transportation page or chart reads a mile figure from.
export const MILE_FILES = [
  "bike-history/history.json",
  "bike-history/segments.json",
  "bike-history/all-ages.geojson",
  "bike-history/components.json",
  "bike-history/projects.json",
  "bike-progress.json",
  "north-star/status.json",
  "repave-lever.json",
  "coordination.json",
  "department-overlap.json",
  "transportation.json",
];

const sig2 = (x) => (x === 0 ? 0 : Number(x.toPrecision(2)));

export function checkMileBasis() {
  const errors = [];
  const bases = new Map();
  for (const f of MILE_FILES) {
    let d;
    try {
      d = read(f);
    } catch (e) {
      errors.push(`F1 ${f}: cannot read (${e.message})`);
      continue;
    }
    if (!d.mileBasis) errors.push(`F1 ${f}: declares no mileBasis`);
    else bases.set(d.mileBasis, [...(bases.get(d.mileBasis) || []), f]);
  }
  if (bases.size > 1) {
    errors.push(`F1 ${bases.size} mile bases: ` + [...bases].map(([b, fs_]) => `"${b}" in ${fs_.join(", ")}`).join("; "));
  }

  const m = new Map(read("north-star/status.json").blocks.map((b) => [String(b.cnn), b.m]));

  // 2. history.json's latest network miles against its own blocks.
  const hist = read("bike-history/history.json");
  const comp = read("bike-history/components.json");
  const latest = hist.rows.find((r) => r.year === comp.year);
  const compMi = (c) => Object.values(c?.m || {}).reduce((t, x) => t + x, 0);
  const blockSum = Object.values(comp.blocks).reduce((t, c) => t + compMi(c), 0);
  if (!latest) errors.push(`F1 history.json: no row for ${comp.year}, the year components.json holds`);
  else if (Math.abs(latest.network_miles - blockSum) > 0.15) {
    errors.push(`F1 history.json: ${comp.year} network is ${latest.network_miles} mi; its blocks in components.json sum to ${blockSum.toFixed(2)}`);
  }

  // 3. status.json against the same blocks' row miles, times the plan's share.
  const traced = read("north-star/traced.geojson").features.map((f) => f.properties);
  let bad = 0, compared = 0;
  for (const p of traced) {
    const c = comp.blocks[String(p.cnn)];
    const rowMi = compMi(c);
    if (!rowMi || !m.has(String(p.cnn))) continue;
    compared++;
    const want = rowMi * MILE * (p.share ?? 1);
    const got = m.get(String(p.cnn));
    if (Math.abs(got - want) > Math.max(1.5, 0.01 * want)) {
      if (bad++ < 10) errors.push(`F1 status.json: block ${p.cnn} ${p.street} is ${got} m; its rows in components.json give ${want.toFixed(0)} m at share ${p.share}`);
    }
  }
  if (bad > 10) errors.push(`F1 status.json: ${bad - 10} more plan blocks disagree with components.json`);
  if (compared < 1000) errors.push(`F1 status.json: only ${compared} plan blocks carry rows in components.json; expected over 1,000`);

  // 4. Current Projects and the repave lever against status.json.
  const coord = read("coordination.json");
  bad = 0;
  for (const p of coord.projects) {
    if (!p.planCnns?.length) continue;
    const want = p.planCnns.reduce((t, c) => t + (m.get(String(c)) ?? NaN), 0) / MILE;
    // planMiles is rounded to two significant figures, so allow that and the
    // status file's whole-metre rounding, nothing more.
    if (!(Math.abs(p.planMiles - want) <= Math.max(0.051 * want, 0.002) || p.planMiles === sig2(want))) {
      if (bad++ < 10) errors.push(`F1 coordination.json: ${p.name} has ${p.planMiles} plan mi; status.json gives its blocks ${want.toFixed(3)}`);
    }
  }
  if (bad > 10) errors.push(`F1 coordination.json: ${bad - 10} more projects disagree with status.json`);

  bad = 0;
  for (const b of read("repave-lever.json").sinceAdoption.blocks) {
    const want = m.get(String(b.cnn));
    if (want === undefined) continue;
    if (Math.abs(b.miles * MILE - want) > 1.5) {
      if (bad++ < 10) errors.push(`F1 repave-lever.json: block ${b.cnn} ${b.street} is ${(b.miles * MILE).toFixed(0)} m; status.json gives ${want} m`);
    }
  }
  if (bad > 10) errors.push(`F1 repave-lever.json: ${bad - 10} more blocks disagree with status.json`);
  return errors;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const errors = checkMileBasis();
  for (const e of errors) console.error(`check-mile-basis: ${e}`);
  if (errors.length) process.exit(1);
  console.log(`check-mile-basis: F1 passes; ${MILE_FILES.length} files count miles one way, block for block`);
}
