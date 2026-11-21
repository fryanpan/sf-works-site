// School Trips' citywide model, built from the files the page builds from, for the scripts that compute its headline
// figures (tools/school-trips/school-trips-figures.mjs) and rerun them at each input's low and high
// (site/scripts/check-assumptions.mjs). One loader, so the two can't build the model differently.

import fs from "node:fs";
import nodePath from "node:path";
import { makeCityModel, readEbikeGate } from "./school-trips-model.mjs";
import { COSTS } from "./pages/transportation-school-trips.mjs";

const DATA = nodePath.join(import.meta.dirname, "..", "data");
const read = (p) => JSON.parse(fs.readFileSync(nodePath.join(DATA, p), "utf8"));

// The headline figures use the sim's central case, its low and high the cases either side (city.json's cases).

let INPUTS = null;
function inputs() {
  if (INPUTS) return INPUTS;
  const CJ = read("school-sim/city.json"), RULES = read("school-sim/rules.json"), IX = read("school-sim/index.json");
  const HURT = read("school-kids-hurt.json");
  const SCH = IX.schools.map((s) => ({ cds: s.cds, name: s.name, calmFt: s.calmFt, calmed: !!s.calmed,
    ranges: Object.fromEntries(Object.entries(s.ranges || {}).map(([k, r]) => [k, { n: r.students }])) }));
  const GATE = readEbikeGate(nodePath.join(DATA, "school-sim"), CJ, SCH);
  return (INPUTS = { CJ, RULES: { ...RULES, gate: GATE }, HURT, SCH, COST: Object.fromEntries(Object.entries(COSTS).map(([k, c]) => [k, c.v])) });
}

/** The model, with `assume` (central overrides by assumption param) and `cost` (cost overrides by COSTS key). */
export function loadCityModel({ assume = {}, cost = {} } = {}) {
  const { CJ, RULES, HURT, SCH, COST } = inputs();
  const MD = makeCityModel(CJ, { schools: SCH, cost: { ...COST, ...cost }, rules: { ...RULES, injury: HURT.model }, assume });
  return { MD, CJ };
}

/**
 * All Changes: every change the model holds switched on at its central value, on today's network plus the speed limit
 * signs and School Connectors, with SFUSD's adopted assignment as it stands in 2030-31 (the plans' background).
 * No new bikeways, since those are a budget choice.
 */
export function allChanges(MD, CJ) {
  return { ...MD.OFF, ...Object.fromEntries(CJ.programs.map((p) => [p, 1])), ...Object.fromEntries(MD.POST_IDS.map((p) => [p, 1])),
    calm: 1, connector: 1, assign: "assign_ncp52" };
}

/** The All Changes headline under case q (central by default), with the changes on top at their central: kids hurt
 * prevented a year, students out of single-family cars, yearly cost. Kids hurt are each change's central cut. */
export function headline(MD, CJ, q = MD.CEN) {
  const c = allChanges(MD, CJ), X = MD.figC(c, q), T = MD.fig(MD.TODAY, q), k = MD.cost(c);
  return { c, X, T, cost: k, hurt: MD.hurt(c), cars: T.modes[0] - X.modes[0], year: k.year, once: k.once,
    carShare: X.tally, noCaregiver: (X.solo || 0) - (T.solo || 0) };
}

/** Every change id alone() takes, as the About page names them. */
export function aloneIds(MD, CJ) {
  return [...CJ.programs, "xing660", "xing1320", "calm", "connector", ...(CJ.segments || []).map((s) => `seg${s.budgetM}`),
    "assign_nas", "assign_ncp", ...Object.keys(MD.ASSIGN_PHASE), ...MD.POST_IDS, ...MD.SPEED_IDS, "speed_humps_rest"];
}
