#!/usr/bin/env node
// Proof of the budget plans' ladder pass (site/src/school-trips-plan.mjs, planGreedy) on a small synthetic table, and
// the time one page re-plan takes on the real table.
//
//     node site/tests/school-trips-plan-test.mjs
//
// The table: one school change A ($2M, 30 students out of cars), one small change B ($1M, 1 student), and a citywide
// bikeway ladder of two sizes ($5M for 50, $10M for 115). At $10M the plain greedy takes A first (15 a $1M), then the
// $5M set, then B, for 81, and can't afford the $10M set. Held at the $10M set the greedy reaches 115, so the plan must
// take it. With the ladder switched off the plan is A and B, 31. Light: reads site/data/school-budget-plans.json only
// for the timing.
import fs from "node:fs";
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const { planGreedy, planAll, tableSum } = await import(path.join(ROOT, "site/src/school-trips-plan.mjs"));
const L = (id, cost, cars) => ({ id, cost, cars, hurt: 0, v: [] });
const T = {
  fixed: {},
  slots: [
    { cds: "s1", lever: "a", levels: [L("a", 2, 30)] },
    { cds: "s1", lever: "b", levels: [L("b", 1, 1)] },
    { cds: null, lever: "seg", levels: [L("seg5", 5, 50), L("seg10", 10, 115)] },
  ],
};
let ok = true;
const check = (name, got, want) => {
  const pass = Math.abs(got - want) < 1e-9;
  ok &&= pass;
  console.log(`  ${name}: ${got}, want ${want}${pass ? "" : "  FAIL"}`);
};
const at10 = tableSum(T, planGreedy(T, "car", 10));
check("$10M plan, students out of cars", at10.cars, 115);
check("$10M plan, cost", at10.cost, 10);
check("$10M plan with the bikeways off", tableSum(T, planGreedy(T, "car", 10, { seg: 0 })).cars, 31);
check("$4M plan (no ladder size fits)", tableSum(T, planGreedy(T, "car", 4)).cars, 31);

// One page re-plan on the real table: the page calls planAll twice (with the reader's changes and with all on).
const P = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/school-budget-plans.json"), "utf8"));
for (const b of P.budgets) {
  const t0 = performance.now();
  planAll(P.table, b, { safer_crossings: 0 });
  planAll(P.table, b);
  console.log(`  re-plan at $${b}M: ${(performance.now() - t0).toFixed(0)} ms in Node`);
}
console.log(`ladder pass: ${ok ? "pass" : "FAIL"}`);
process.exit(ok ? 0 : 1);
