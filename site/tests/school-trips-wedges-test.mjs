#!/usr/bin/env node
// Proof that School Trips' Citywide Goals view opens on SFMTA's plan with the figures we give for it, and that its wedge
// segments add back to the model's stacked totals.
//
//     node site/tests/school-trips-wedges-test.mjs
//
// SFMTA's plan is its four draft tools, School Streets, crossings and calming, speed limit signs and School
// Connectors, at every school, on the assignment SFUSD's Board chose, as every scenario but Today holds it
// (docs/decisions/school-trips.md, 2026-10-23): 2,411 students out of single-family cars, 4.4 fewer kids hurt a year
// (kids hurt on school-year weekdays, 6 am to 6 pm, August to May), $46.6M once and $4.89M a year, and the Travel
// Tally from 48.6% to 44.6%. The public comment (Safe School Connections, October 2026) gives the four tools' kids
// hurt as "about 4" and their cost as $47M. Its chart of students with a safe route gives 5,237 today, 7,352 with the
// plan's tools, 11,802 with $20M of bikeways alone and 13,670 with both. Every school is in: public, charter and
// private, 219 in all. The page prints counts whole, kids hurt and the tally to one decimal, and dollars to three
// figures, so each check is on what the page prints. Light: reads figures.json and city.json, no simulation.
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const { figure } = await import(path.join(ROOT, "site/src/figures.mjs"));
const { WEDGES, PLAN_STEPS, FULL_STEPS } = await import(path.join(ROOT, "site/src/school-trips-wedges.mjs"));
const { loadCityModel } = await import(path.join(ROOT, "site/src/school-trips-inputs.mjs"));

// The page's own formats (wedgeUI).
const n0 = (x) => Math.round(x).toLocaleString("en-US");
const k1 = (x) => (Math.round(x * 10) / 10).toFixed(1);
const m3 = (x) => "$" + Number(x.toPrecision(3)) + "M";

let ok = true;
const check = (name, pass, detail) => { ok &&= pass; console.log(`  ${name}: ${detail}${pass ? "" : "  FAIL"}`); };

const T = figure("school-trips.wedges");
const at = (steps) => T.rows.find((r) => r.s === steps.join(""));
const P = at(PLAN_STEPS);

console.log("SFMTA's plan preset:");
// The model's stack is 2,411.25, which prints 2,411. Pinned to the print, so a drift of a single student fails.
check("students out of cars", n0(P.cars) === "2,411" && Math.abs(P.cars - 2411.25) < 0.5, `${P.cars.toFixed(2)} (prints ${n0(P.cars)}), target 2,411`);
// The four tools and the assignment stacked by the model's rule, 4.445 on the August to May base, which prints 4.4.
check("fewer kids hurt a year", Math.abs(P.hurt - 4.445) < 0.001 && k1(P.hurt) === "4.4", `${P.hurt.toFixed(3)} (prints ${k1(P.hurt)}), target 4.4, comment "about 4"`);
check("cost once", m3(P.once) === "$46.6M", `${m3(P.once)}, target $46.6M, comment $47M`);
check("cost a year", m3(P.year) === "$4.89M", `${m3(P.year)}, target $4.89M`);
check("tally today", k1(T.tallyToday) === "48.6", `${k1(T.tallyToday)}%, comment 48.6%`);
check("tally with the plan", k1(P.tally) === "44.6", `${k1(P.tally)}%, target 44.6%`);
const SH = WEDGES.findIndex((w) => w.id === "shorter");
check("SFUSD's assignment in the plan", PLAN_STEPS[SH] === WEDGES[SH].steps.length - 1 && WEDGES[SH].steps[PLAN_STEPS[SH]][1].assign === "assign_ncp52", WEDGES[SH].steps[PLAN_STEPS[SH]][0]);
check("only the first wedge and Shorter Trips", P.segs.every((s, i) => i === 0 || i === SH || s.every((x) => x === 0)) && Math.abs(P.segs[0][0] + P.segs[SH][0] - P.cars) < 0.05, `segments ${JSON.stringify(P.segs[0])} and ${JSON.stringify(P.segs[SH])}`);

console.log("Students with a safe route, against the comment's chart:");
check("today", T.safe[0] === 5237, `${n0(T.safe[0])}, comment 5,237`);
check("with the plan's tools", T.safe[1] === 7352, `${n0(T.safe[1])}, comment 7,352`);
check("plan and $20M of bikeways", T.safe[2] === 13670, `${n0(T.safe[2])}, comment 13,670`);
const { MD } = loadCityModel();
const seg20 = Math.round(MD.safeN(MD.svar({ ...MD.OFF, seg: 20 })).n);
check("$20M of bikeways alone (model)", seg20 === 11802, `${n0(seg20)}, comment 11,802`);

console.log("Every combination of steps:");
const radix = WEDGES.map((w) => w.steps.length);
// The browser finds a row by mixed-radix index (wedgeUI's idx), first wedge slowest; rows must sit in that order.
const idx = (s) => s.reduce((t, k, i) => t * radix[i] + k, 0);
check("rows in the browser's order", T.rows.every((r) => T.rows[idx([...r.s].map(Number))] === r), "idx(steps) finds every row");
check("one row each", T.rows.length === radix.reduce((t, x) => t * x, 1), `${T.rows.length} rows`);
let worst = 0;
for (const r of T.rows) {
  const sum = (j) => r.segs.reduce((t, s) => t + s[j], 0);
  worst = Math.max(worst, Math.abs(sum(0) - r.cars), Math.abs(T.tallyToday - sum(1) - r.tally) * 100, Math.abs(sum(2) - r.hurt) * 100);
}
check("segments add back to the stacked totals", worst < 0.5, `worst gap ${worst.toFixed(3)} (students, or hundredths of a point or kid)`);
check("fill every wedge has a row", !!at(FULL_STEPS), FULL_STEPS.join(""));

console.log(`wedges: ${ok ? "pass" : "FAIL"}`);
process.exit(ok ? 0 : 1);
