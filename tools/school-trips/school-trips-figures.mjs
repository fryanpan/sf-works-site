#!/usr/bin/env node
// School Trips' headline figures, computed once and written to site/data/figures.json for every page to read.
//
// Computes, with the citywide model the tool runs (site/src/school-trips-model.mjs) in the sim's central case, year 10:
//   school-trips.all.*      All Changes together (site/src/school-trips-inputs.mjs, allChanges): kids hurt prevented a
//                           year, students out of single-family cars, the tally car share, kids who no longer need a
//                           caregiver on the trip, yearly and one-time cost, each central with the model's low and high
//                           where it has one.
//   school-trips.alone.<id> each change alone, the whole of makeCityModel's alone() result, which the About page prints.
//   school-trips.top.*      the change alone that prevents the most kids hurt, and the one that takes the most
//                           students out of single-family cars.
//   school-trips.wedges     the Citywide Goals view's six wedges at every combination of their steps
//                           (site/src/school-trips-wedges.mjs, wedgeTable): the stacked totals and each wedge's segment.
// The budget plans' figures are written by tools/school-trips/school-budget-plans.mjs, which computes them.
//
//     node tools/school-trips/school-trips-figures.mjs          (light: reads city.json, no simulation)
//     node tools/school-trips/school-trips-figures.mjs --check  (writes nothing; exits 1 when figures.json is stale)
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ROOT } from "../../site/scripts/lib/repo.mjs";
const { loadCityModel, headline, aloneIds } = await import(path.join(ROOT, "site/src/school-trips-inputs.mjs"));
const { writeFigures } = await import(path.join(ROOT, "site/src/figures.mjs"));
const { wedgeTable } = await import(path.join(ROOT, "site/src/school-trips-wedges.mjs"));
const BY = "tools/school-trips/school-trips-figures.mjs";

const { MD, CJ } = loadCityModel();
const H = headline(MD, CJ), R = MD.range(H.c);
const DEF = "All Changes: every change in the model at its central value, with the speed limit signs, School Connectors and "
  + "SFUSD's adopted assignment as it stands in 2030-31; no new bikeways; the sim's central case, year 10, with the low and high cases in the range";
const F = {
  "school-trips.all.kidsHurtPrevented": { value: H.hurt, low: R.hurt[0], high: R.hurt[1], unit: "kids hurt a year", def: DEF },
  "school-trips.all.kidsHurtBase": { value: MD.HB, unit: "kids hurt a year", def: "kids 5 to 18 hurt on SF weekdays, 6 am to 6 pm, August to May, the injury model's base" },
  "school-trips.all.carsOut": { value: H.cars, low: R.cars[0], high: R.cars[1], unit: "students out of single-family cars", def: DEF },
  "school-trips.all.carShare": { value: H.carShare, unit: "% of school trips by single-family car, tally basis", def: DEF },
  "school-trips.all.carShareToday": { value: CJ.tallyCar, unit: "% of school trips by single-family car, tally basis", def: "SFMTA Travel Tally, four grades" },
  "school-trips.all.noCaregiver": { value: H.noCaregiver, unit: "kids who no longer need a caregiver on the trip", def: DEF },
  "school-trips.all.yearCostM": { value: H.year, low: R.year[0], high: R.year[1], unit: "$M a year", def: DEF },
  "school-trips.all.onceCostM": { value: H.once, unit: "$M once", def: DEF },
  "school-trips.case": { value: CJ.cases[MD.CEN], unit: "sim case", def: "the sim's case every central figure here uses; low and high take the cases either side" },
};
const alone = {};
for (const id of aloneIds(MD, CJ)) {
  alone[id] = MD.alone(id);
  F[`school-trips.alone.${id}`] = { value: alone[id], unit: "makeCityModel alone(), the sim's three cases", def: `${id} alone against today` };
}
// The top change is picked among All Changes' own changes, so a wider reach of the same upgrades doesn't compete with it.
const TOP_IDS = MD.onIds(H.c).filter((id) => !id.startsWith("assign"));
const best = (f) => TOP_IDS.slice().sort((a, b) => f(alone[b]) - f(alone[a]) || (a < b ? -1 : 1))[0];
const tH = best((x) => x.hurt[1]), tC = best((x) => x.cars[1]);
F["school-trips.top.hurt"] = { value: { id: tH, hurt: alone[tH].hurt[1] }, unit: "kids hurt a year", def: "of All Changes' own changes, the one that alone prevents the most kids hurt (assignment left out)" };
F["school-trips.top.cars"] = { value: { id: tC, cars: alone[tC].cars[1] }, unit: "students out of single-family cars", def: "of All Changes' own changes, the one that alone takes the most students out of single-family cars (assignment left out)" };

F["school-trips.wedges"] = { value: wedgeTable(MD), unit: "students out of single-family cars, tally %, kids hurt a year, $M",
  def: "Citywide Goals: each combination of the six wedges' steps, the model's stacked figures, the sim's central case, year 10; a wedge's segment is what it adds to the wedges above it" };

const CHECK = process.argv.includes("--check");
const changed = writeFigures(BY, F, { dryRun: CHECK });
if (CHECK) {
  console.log(changed ? `site/data/figures.json is stale for ${BY}: run node ${BY}` : `figures.json current for ${BY}`);
  process.exit(changed ? 1 : 0);
}
console.log(`All Changes, central case: ${H.hurt.toFixed(2)} kids hurt prevented a year (${R.hurt.map((x) => x.toFixed(2)).join(" to ")}), `
  + `${Math.round(H.cars)} students out of single-family cars, car share ${H.carShare.toFixed(1)}%, ${Math.round(H.noCaregiver)} need no caregiver, `
  + `$${H.year.toFixed(2)}M a year and $${H.once.toFixed(2)}M once. Top for injuries: ${tH} (${alone[tH].hurt[1].toFixed(2)}); for cars: ${tC} (${Math.round(alone[tC].cars[1])}).`);
console.log(changed ? "wrote site/data/figures.json" : "site/data/figures.json unchanged");
