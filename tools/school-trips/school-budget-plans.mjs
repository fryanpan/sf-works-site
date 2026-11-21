#!/usr/bin/env node
// School Trips' budget plans: for $5M to $80M over four years, which changes go to which schools, and which new bikeway
// set citywide, to take the most students out of single-family cars, to spare the most kids hurt, or both. Writes
// site/data/school-budget-plans.json.
//
// Bryan, 2026-10-14, on the scenarios: "maximize mode shift for a given $ budget, maximize injury reduction for a given
// $ budget, and balanced - maximize both weighted equally. And then the advanced options let you enable whether
// particular tools are available for use or not. But then the determiniation is still by school (or street segment)
// whether to do an intervention or not."
//
// One budget covers the school changes and the new bikeways together. The bikeways are one citywide step with five
// levels, the $5M to $80M sets tools/school-trips/school-segments-ip.py chooses block by block; a plan moves up that ladder when
// the next set's gain per dollar beats the next school change's, so the plan picks segments and school changes in one
// greedy rather than splitting the budget ahead of time.
//
// Each school's own file (site/data/school-sim/<cds>.json, city block) holds its mode mix for every combination of
// changes, so a plan is scored exactly, school by school, and summed. Injuries use makeCityModel's rules: each change's
// cut from fewer cars is its citywide cut per car, times the cars it takes out at the funded schools; safety upgrades,
// calmed streets and speed limit signs act on the kids hurt nearest each funded school. Changes multiply as the City's
// totals do.
//
// The plan is picked from a table (site/src/school-trips-plan.mjs): every change at every school, and every citywide
// step, scored alone on the background, SFUSD's Neighborhood + Citywide Programs assignment. The greedy takes the
// move with the most gain per dollar of four-year cost (one-time plus four years of running cost) that still fits.
// Car counts students out of single-family cars, safety kids hurt spared, and balanced each goal divided by what that
// goal's own plan reaches at the same budget, weighted equally. The page runs the same greedy on the same table when
// a change is turned off. The chosen plan is then scored exactly, so the table's one simplification, that a change's
// gain doesn't depend on what else its school holds, touches which changes are picked, not the figures shown. The
// run checks the table's pick against a greedy that rescores every move exactly after each pick, with every change
// on, and prints the gap. Central estimates, in the sim's central case at year 10, pick and score the plan; its low and
// high take each change's own low and high, the sim's low and high cases for the network's bike shift.
//
//     node tools/school-trips/school-budget-plans.mjs            (PLANS_EXACT=0 skips the exact-greedy check)
//     node tools/school-trips/school-budget-plans.mjs --figures-only   (light: rewrites only its site/data/figures.json entries from
//                                                          the plans file already written; add --check to only compare)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ROOT } from "../../site/scripts/lib/repo.mjs";
const { makeCityModel, readEbikeGate } = await import(path.join(ROOT, "site/src/school-trips-model.mjs"));
const { planAll, planGreedy, tableSum, replanHurt, VKEYS } = await import(path.join(ROOT, "site/src/school-trips-plan.mjs"));
const { COSTS } = await import(path.join(ROOT, "site/src/pages/transportation-school-trips.mjs"));
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const OUT = path.join(ROOT, "site/data/school-budget-plans.json");

const BUDGETS = [5, 10, 20, 40, 80, 100];   // over 4 years, $M: Bryan's ladder for the new bikeways, 2026-10-14, and $100M (2026-10-15)
const GOALS = ["car", "safety", "balanced"];
const YEARS = 4;
// The background: Neighborhood + Citywide Programs, the Board's choice of 2026-10-13, as it stands in 2030-31, the
// plans' fourth year and Bryan's goal year. The new rules start with TK and K in 2028-29 and add a grade a year, so 52%
// of TK-5 students are under them then (topics/school-trips/assignment-options.md, Phase-in, the published table's
// share). makeCityModel's ASSIGN_PHASE blends each school's mix, 52% from the full-effect sets and 48% from today's.
// TK is in: the sim's assignment options shorten every TK-5 trip, and the table's share counts TK, weighted by its
// enrollment.
const BG = "assign_ncp52";
// What a plan can fund at one school, and citywide.
// The last four are applied on top of city.json's sets (makeCityModel's POST).
// Free Muni for Caregivers is a citywide step (city.muni), every TK-8 school or none: a fare policy can't be handed out
// school by school (Bryan, 2026-10-18: "Make it citywide").
const AT_SCHOOL = ["school_street", "walking_bus", "safer_crossings", "connector", "yellow_bus", "ebike",
  "travel_tracker", "ecargo_month", "curb_restriction", "bike_bus",
  // The three speed changes (Bryan, 2026-10-15), each its own move. They cut kids hurt only.
  "bad_district", "speed_humps", "speed_cameras"];
// A shuttle loop runs at a school only with at least half a bus of riders.
const MIN_RIDERS = 25;
const REACHES = [350, 660, 1320];
const SEGS = [5, 10, 20, 40, 80, 100];   // new bikeways by budget, $M

const CJ = read("site/data/school-sim/city.json"), RULES = read("site/data/school-sim/rules.json");
const IX = read("site/data/school-sim/index.json"), HURT = read("site/data/school-kids-hurt.json");
const COST = Object.fromEntries(Object.entries(COSTS).map(([k, c]) => [k, c.v]));
const SCH = IX.schools.map((s) => ({ cds: s.cds, name: s.name, calmFt: s.calmFt, calmed: !!s.calmed,
  ranges: Object.fromEntries(Object.entries(s.ranges || {}).map(([k, r]) => [k, { n: r.students }])) }));
const GATE = readEbikeGate(path.join(ROOT, "site/data/school-sim"), CJ, SCH);
const MD = makeCityModel(CJ, { schools: SCH, cost: COST, rules: { ...RULES, injury: HURT.model, gate: GATE } });
const FILES = Object.fromEntries(SCH.map((s) => [s.cds, read(`site/data/school-sim/${s.cds}.json`).city]));
const CONN = RULES.connector || {};

// Each change's cut in kids hurt a year per car it takes out, at low, central and high, from the citywide figures.
const perCarMemo = {};
function perCar(id) {
  const key = id;
  if (!perCarMemo[key]) {
    const a = MD.alone(id);
    perCarMemo[key] = a.cars[1] > 0 ? a.carHurt.map((h) => h / a.cars[1]) : [0, 0, 0];
    perCarMemo[key].lohi = a.cars[1] > 0 ? a.cars.map((x) => x / a.cars[1]) : [1, 1, 1];
  }
  return perCarMemo[key];
}
const eligible = (s, p) => {
  const k5 = !!s.ranges["K-5"], k8 = k5 || !!s.ranges["6-8"];
  if (p === "school_street" || p === "walking_bus" || p === "travel_tracker" || p === "curb_restriction") return k5;
  // The e-cargo month and the bike bus run only at the e-bike gate's schools on today's network.
  if (p === "ecargo_month" || p === "bike_bus") return MD.IN_GATE.has(s.cds);
  if (p === "safer_crossings" || p === "caregiver_muni") return k8;
  if (p === "connector") return !!CONN[s.cds];
  // A speed change goes where tools/school-trips/school-speed-levers.py placed one: a business corridor, a hump block or a camera.
  // Humps aren't offered where the calming budget reaches: safety upgrades there bring calming on the same streets,
  // so a plan that bought both would pay twice for one street, and the table, which scores each move alone, can't see
  // that.
  if (p === "speed_humps" && s.calmed) return false;
  if (MD.SPEED_IDS.includes(p)) return MD.spUnits(p, s.cds) > 0;
  return true;
};

// One school under its own set c (with the citywide steps in city), in the central case: its figures, the cars each
// of its changes takes out given the rest of its set, its safety cuts and its costs.
const evMemo = new Map();
function evalSchool(s, c, city) {
  const mk = `${s.cds}|${JSON.stringify(c)}|${city.seg}|${city.carpool}|${city.calm}|${city.muni}`;
  if (!evMemo.has(mk)) evMemo.set(mk, evalSchoolRaw(s, c, city));
  return { ...evMemo.get(mk) };
}
function evalSchoolRaw(s, c, city) {
  // Speed limit signs are one citywide step, every school or none, since one crash in four years shouldn't decide a
  // $3,000 sign.
  const muni = city.muni && eligible(s, "caregiver_muni") ? 1 : 0;
  const C = FILES[s.cds], full = { ...MD.OFF, ...c, assign: BG, seg: city.seg, carpool: city.carpool, calm: city.calm, caregiver_muni: muni };
  const fig = (cc) => MD.schoolFigC(C, s.cds, cc);
  const X = fig(full), memo = {};
  const without = (p) => (memo[p] = memo[p] || fig({ ...full, [p]: 0 }));
  const cost = MD.schoolCost(s, full, X, without);
  const dCars = {};
  for (const p of AT_SCHOOL) if (c[p] && !MD.SPEED_IDS.includes(p)) dCars[p === "safer_crossings" ? xid(c) : p] = without(p).modes[0] - X.modes[0];
  if (city.seg) dCars["seg" + city.seg] = fig({ ...full, seg: 0 }).modes[0] - X.modes[0];
  if (city.carpool) dCars.carpool = without("carpool").modes[0] - X.modes[0];
  if (muni) dCars.caregiver_muni = without("caregiver_muni").modes[0] - X.modes[0];
  const safety = [0, 1, 2].map((k) => MD.schoolSafety(s, full, k));
  return { X, cost, dCars, safety };
}
const xid = (c) => ((c.xreach || 350) === 350 ? "safer_crossings" : `xing${c.xreach}`);

// The plan's totals from its schools' evaluations. Kids hurt multiply across changes as makeCityModel's hurt()
// does, each change's cut summed over the schools that have it.
function totals(ev, city) {
  const T = { modes: [0, 0, 0, 0, 0, 0], min: 0, alone: 0, safe: 0, once: 0, year: 0, people: 0, N: 0, st: { ss: 0, drv: 0, pool: 0 } };
  const H = {}, carsBy = {};
  const add = (t, k, v) => { H[t] = H[t] || [0, 0, 0]; H[t][k] += v; };
  for (const e of Object.values(ev)) {
    e.X.modes.forEach((x, q) => (T.modes[q] += x));
    T.min += e.X.min || 0; T.alone += e.X.alone; T.safe += e.X.safe || 0; T.N += e.X.N;
    T.once += e.cost.once; T.year += e.cost.year; T.people += e.cost.people;
    T.st.drv += e.cost.riders / COST.busRiders; T.st.ss += e.cost.people - e.cost.riders / COST.busRiders;
    for (const [t, d] of Object.entries(e.dCars)) {
      carsBy[t] = (carsBy[t] || 0) + d;
      perCar(t).forEach((pc, k) => add(t, k, pc * d));
    }
    e.safety.forEach((sf, k) => {
      add(xidOf(e), k, sf.xing + sf.calmed); add("calm", k, sf.signs);
      add("bad_district", k, sf.bad); add("speed_humps", k, sf.humps); add("speed_cameras", k, sf.cameras);
    });
  }
  // Citywide costs: the bikeways, carpool matching, the e-bike program once any school has vouchers, and the e-cargo
  // month's staff once any school has trials.
  if (city.seg) T.once += (CJ.segments.find((m) => m.budgetM === city.seg) || {}).costM || 0;
  if (city.carpool) { T.year += COST.carpool / 1e6; T.people += 0.5; T.st.pool = 0.5; }
  if (Object.values(ev).some((e) => e.cost.ebk > 0)) T.year += COST.ebikeProgram / 1e6;
  if (Object.values(ev).some((e) => e.cost.ec)) T.year += COST.ecargoProgram / 1e6;
  // The bikeways' calmed blocks cut the kids hurt on them, a citywide figure, apart from the cars they take out.
  if (city.seg) MD.segCalm(city.seg).forEach((h, k) => add("segcalm", k, h));
  // The assignment background's own injury cut.
  MD.alone(BG).hurt.forEach((h, k) => add(BG, k, h));
  // Low and high: each type at its own fewest and most kids spared. A type's three figures aren't ordered (a change
  // whose switchers add walking and biking risk does least harm at its low reach), and the product is monotone in each.
  const comb = (pick) => MD.HB * (1 - Object.values(H).reduce((t, h) => t * (1 - pick(h) / MD.HB), 1));
  T.hurt = [comb((h) => Math.min(...h)), comb((h) => h[1]), comb((h) => Math.max(...h))];
  // Cars, low and high: each change's cars moved to its own low or high, as range() does.
  const mid = Object.values(carsBy).reduce((t, x) => t + x, 0);
  T.carsBy = carsBy;
  T.H = H;
  T.carsOut = [0, 2].map((k) => Object.entries(carsBy).reduce((t, [id, d]) => t + d * perCar(id).lohi[k], 0));
  T.carsOutMid = mid;
  return T;
}
const xidOf = (e) => e.xid || "safer_crossings";

// The bikeway sets the sim has variants for.
const SEG_OK = SEGS.filter((b) => (CJ.variants || []).includes(`today_b${b}`) && (CJ.segments || []).some((m) => m.budgetM === b));
// The check's greedy: every move rescored exactly after each pick. Like the table's (site/src/school-trips-plan.mjs),
// it is rerun with the bikeway ladder held at each size that fits, and none, and the best kept, so the two compare like
// with like.
function planExact(goal, budgetM) {
  const score = (T) => (goal === "safety" ? T.hurt[1] : -T.modes[0]);
  let best = planExactRun(goal, budgetM, null);
  for (const b of [0, ...SEG_OK]) {
    if (b === best.city.seg) continue;
    const p = planExactRun(goal, budgetM, b);
    if (p && score(p.T) > score(best.T) + 1e-9) best = p;
  }
  return best;
}
function planExactRun(goal, budgetM, fixSeg) {
  const city = { seg: fixSeg || 0, carpool: 0, calm: 0, muni: 0 };
  const sets = Object.fromEntries(SCH.map((s) => [s.cds, {}]));
  let ev = Object.fromEntries(SCH.map((s) => [s.cds, evalSchool(s, {}, city)]));
  const tag = (e, c) => ((e.xid = c.safer_crossings ? xid(c) : "safer_crossings"), e);
  const score = (T) => (goal === "safety" ? T.hurt[1] : -T.modes[0]);
  const spend = (T) => T.once + YEARS * T.year;
  let cur = totals(ev, city);
  if (spend(cur) > budgetM + 1e-9) return null;
  const picks = [];
  for (;;) {
    let best = null;
    const consider = (kind, apply) => {
      const trial = apply();
      if (!trial) return;
      const T = totals(trial.ev, trial.city), dv = score(T) - score(cur), dc = spend(T) - spend(cur);
      // A move must do something real, at least one student out of a single-family car or a hundredth of a kid hurt a
      // year spared, so a change with a sliver of effect at a school isn't funded for it.
      const real = (cur.modes[0] - T.modes[0] >= 1 || T.hurt[1] - cur.hurt[1] >= 0.01) && !(trial.minRiders && trial.minRiders < MIN_RIDERS);
      if (dv <= 1e-9 || !real || spend(T) > budgetM + 1e-9) return;
      const ratio = dc > 1e-9 ? dv / dc : Infinity;
      if (!best || ratio > best.ratio) best = { ratio, dv, dc, T, ...trial, kind };
    };
    for (const s of SCH) {
      const c = sets[s.cds];
      // Each reach is its own choice, so a school whose kids are hurt two blocks out can go straight to a quarter mile.
      const moves = AT_SCHOOL.filter((p) => !c[p] && eligible(s, p) && p !== "safer_crossings").map((p) => ({ [p]: 1 }));
      if (eligible(s, "safer_crossings")) REACHES.filter((f) => !c.safer_crossings || f > c.xreach).forEach((f) => moves.push({ safer_crossings: 1, xreach: f }));
      for (const m of moves) {
        consider(`${s.cds}:${JSON.stringify(m)}`, () => {
          const nc = { ...c, ...m };
          const e = tag(evalSchool(s, nc, city), nc);
          return { ev: { ...ev, [s.cds]: e }, city, sets: { ...sets, [s.cds]: nc }, minRiders: m.yellow_bus ? e.cost.riders : null };
        });
      }
    }
    const cityMoves = [];
    // Any larger bikeway set, as the table offers.
    if (fixSeg == null) SEG_OK.filter((b) => b > city.seg).forEach((b) => cityMoves.push({ ...city, seg: b }));
    if (!city.carpool) cityMoves.push({ ...city, carpool: 1 });
    if (!city.calm) cityMoves.push({ ...city, calm: 1 });
    if (!city.muni) cityMoves.push({ ...city, muni: 1 });
    for (const nc of cityMoves) {
      consider(`city:${JSON.stringify(nc)}`, () => ({
        ev: Object.fromEntries(SCH.map((s) => [s.cds, tag(evalSchool(s, sets[s.cds], nc), sets[s.cds])])), city: nc, sets,
      }));
    }
    if (!best) break;
    ev = best.ev; Object.assign(city, best.city); Object.assign(sets, best.sets); cur = best.T;
    picks.push({ move: best.kind, dv: +best.dv.toFixed(4), dc: +best.dc.toFixed(4) });
  }
  return { city, sets, picks, T: cur };
}

// The plan's totals, rounded for the page: at.central, the central case, with each figure's low and high (carsOut and
// hurt) beside it. Keyed by case so the page reads at.central.
const rnd = (x, d = 2) => Math.round(x * 10 ** d) / 10 ** d;
function writeOut(goal, budget, p) {
  const out = {};
  {
    const ev = Object.fromEntries(SCH.map((s) => { const e = evalSchool(s, p.sets[s.cds], p.city); e.xid = p.sets[s.cds].safer_crossings ? xid(p.sets[s.cds]) : "safer_crossings"; return [s.cds, e]; }));
    const T = totals(ev, p.city);
    out.central = { modes: T.modes.map((x) => rnd(x, 1)), min: rnd(T.min, 0), alone: rnd(T.alone, 1), safe: rnd(T.safe, 1),
      hurt: T.hurt.map((x) => rnd(x, 3)), carsOut: T.carsOut.map((x) => rnd(x, 1)), once: rnd(T.once, 3), year: rnd(T.year, 3), people: rnd(T.people, 1), st: Object.fromEntries(Object.entries(T.st).map(([k, v]) => [k, rnd(v, 1)])),
      carsBy: Object.fromEntries(Object.entries(T.carsBy).sort().map(([k, v]) => [k, rnd(v, 1)])),
      H: Object.fromEntries(Object.entries(T.H).sort().map(([k, v]) => [k, v.map((x) => rnd(x, 4))])) };
  }
  // Each school's changes, as the ids the page's alone() and labels use, and how many schools get each.
  const schools = {}, count = {};
  for (const s of SCH) {
    const c = p.sets[s.cds], ids = AT_SCHOOL.filter((q) => c[q]).map((q) => (q === "safer_crossings" ? xid(c) : q));
    if (ids.length) schools[s.cds] = ids;
    ids.forEach((id) => (count[id] = (count[id] || 0) + 1));
  }
  return { goal, budget, city: p.city, count: Object.fromEntries(Object.entries(count).sort()), schools, at: out, picks: Array.isArray(p.picks) ? p.picks.length : p.picks };
}

// Quality: the schools' files sum to the City's own totals, so a plan scored school by school is on the same base.
{
  const T = MD.fig(MD.TODAY), sum = [0, 0, 0, 0, 0, 0];
  for (const s of SCH) MD.schoolFig(FILES[s.cds], s.cds, MD.TODAY, MD.CEN, "today").modes.forEach((x, q) => (sum[q] += x));
  const off = Math.max(...T.modes.map((x, q) => Math.abs(x - sum[q]) / Math.max(1, x)));
  if (off > 0.005) throw new Error(`school-budget-plans: the schools' files sum to ${sum.map(Math.round)} against the City's ${T.modes.map(Math.round)}`);
}

const T00 = MD.fig(MD.TODAY);
// ---- the table: every move scored alone on the background ----
const spendOf = (T) => T.once + YEARS * T.year;
const vecOf = (T) => [...T.modes, T.min, T.alone, T.safe, T.once, T.year, T.people, T.st.ss, T.st.drv, T.st.pool, ...T.hurt];
const sub = (a, b) => a.map((x, q) => x - b[q]);
const r4 = (x) => Math.round(x * 1e4) / 1e4;
// A change's citywide program, charged once with its first school: the e-bike program and the e-cargo month's staff.
const FIXED = { ebike: COST.ebikeProgram / 1e6, ecargo_month: COST.ecargoProgram / 1e6 };
function buildTable() {
  const city0 = { seg: 0, carpool: 0, calm: 0, muni: 0 };
  const ev0 = Object.fromEntries(SCH.map((s) => [s.cds, evalSchool(s, {}, city0)]));
  const T0 = totals(ev0, city0), v0 = vecOf(T0), sp0 = spendOf(T0);
  const fixed = Object.fromEntries(Object.entries(FIXED).map(([k, y]) => {
    const v = VKEYS.map((q) => (q === "year" ? y : 0));
    return [k, { cost: r4(YEARS * y), v: v.map(r4) }];
  }));
  const level = (T, id, patch, lever) => {
    const fx = FIXED[lever] || 0;
    const v = sub(vecOf(T), v0);
    v[VKEYS.indexOf("year")] -= fx;
    // Each injury type's own cut, which the page recombines as totals() does.
    const h = {};
    for (const t of new Set([...Object.keys(T.H), ...Object.keys(T0.H)])) {
      const d = [0, 1, 2].map((k) => r4((T.H[t] || [0, 0, 0])[k] - (T0.H[t] || [0, 0, 0])[k]));
      if (d.some((x) => x !== 0)) h[t] = d;
    }
    return { id, patch, h, cars: r4(T0.modes[0] - T.modes[0]), hurt: r4(T.hurt[1] - T0.hurt[1]), cost: r4(spendOf(T) - sp0 - YEARS * fx), v: v.map(r4),
      by: Object.fromEntries(Object.entries(T.carsBy).map(([k, x]) => [k, r4(x)])) };
  };
  const real = (L) => L.cars >= 1 || L.hurt >= 0.01;
  const slots = [];
  for (const s of SCH) {
    const tag = (e, c) => ((e.xid = c.safer_crossings ? xid(c) : "safer_crossings"), e);
    const one = (patch) => {
      const e = tag(evalSchool(s, patch, city0), patch);
      return { T: totals({ ...ev0, [s.cds]: e }, city0), riders: e.cost.riders };
    };
    for (const p of AT_SCHOOL) {
      if (!eligible(s, p)) continue;
      const patches = p === "safer_crossings" ? REACHES.map((f) => ({ safer_crossings: 1, xreach: f })) : [{ [p]: 1 }];
      const levels = [];
      for (const patch of patches) {
        const { T, riders } = one(patch);
        const L = level(T, p === "safer_crossings" ? xid(patch) : p, patch, p);
        if (!real(L) || (p === "yellow_bus" && riders < MIN_RIDERS)) continue;
        levels.push(L);
      }
      if (levels.length) slots.push({ key: `${s.cds}:${p}`, cds: s.cds, lever: p, levels });
    }
  }
  // The citywide steps: the five bikeway sets (only those the sim has variants for), carpool matching, speed limits,
  // free Muni for caregivers.
  const cityLevel = (patch, id, lever) => {
    const c = { ...city0, ...patch };
    const ev = Object.fromEntries(SCH.map((s) => [s.cds, evalSchool(s, {}, c)]));
    return level(totals(ev, c), id, patch, lever);
  };
  const segLv = SEG_OK.map((b) => cityLevel({ seg: b }, `seg${b}`, "seg")).filter(real);
  if (segLv.length) slots.push({ key: "city:seg", lever: "seg", levels: segLv });
  for (const p of ["carpool", "calm", "muni"]) { const L = cityLevel({ [p]: 1 }, p, p); if (real(L)) slots.push({ key: `city:${p}`, lever: p, levels: [L] }); }
  return { slots, fixed, base: { car: r4(T0.modes[0]), hurt: r4(T0.hurt[1]), spend: r4(sp0) } };
}

// A table selection as a plan's sets and citywide steps.
function fromSel(TB, lvl) {
  const sets = Object.fromEntries(SCH.map((s) => [s.cds, {}])), city = { seg: 0, carpool: 0, calm: 0, muni: 0 };
  lvl.forEach((j, i) => {
    if (j < 0) return;
    const sl = TB.slots[i], L = sl.levels[j];
    if (sl.cds) Object.assign(sets[sl.cds], L.patch); else Object.assign(city, L.patch);
  });
  return { sets, city, picks: lvl.filter((j) => j >= 0) };
}

// The plans' headline figures, to site/data/figures.json (site/src/figures.mjs), from the plans file this script writes.
// Each plan in the sim's central case: kids hurt prevented a year (low, central, high), students its changes take out
// of single-family cars, one-time and yearly cost. school-trips.plan.default is the plan the page opens on.
function writePlanFigures(P) {
  const { writeFigures } = FIG;
  const F = { "school-trips.plan.default": { value: "balanced20", unit: "plan key", def: "the plan the page opens on: Balanced at $20M over 4 years" } };
  for (const [k, p] of Object.entries(P.plans)) {
    const a = p.at.central, def = `${p.goal} plan, $${p.budget}M over ${P.years} years, the sim's central case at year 10`;
    F[`school-trips.plan.${k}.kidsHurtPrevented`] = { value: a.hurt[1], low: a.hurt[0], high: a.hurt[2], unit: "kids hurt a year", def };
    F[`school-trips.plan.${k}.carsOut`] = { value: Object.values(a.carsBy).reduce((t, x) => t + x, 0), low: a.carsOut[0], high: a.carsOut[1], unit: "students out of single-family cars", def };
    F[`school-trips.plan.${k}.onceCostM`] = { value: a.once, unit: "$M once", def };
    F[`school-trips.plan.${k}.yearCostM`] = { value: a.year, unit: "$M a year", def };
  }
  const CHECK = process.argv.includes("--check"), changed = writeFigures("tools/school-trips/school-budget-plans.mjs", F, { dryRun: CHECK });
  if (CHECK) {
    console.log(changed ? "site/data/figures.json is stale for tools/school-trips/school-budget-plans.mjs: run it with --figures-only" : "figures.json current for tools/school-trips/school-budget-plans.mjs");
    process.exit(changed ? 1 : 0);
  }
  console.log(changed ? "wrote site/data/figures.json" : "site/data/figures.json unchanged");
}
const FIG = await import(path.join(ROOT, "site/src/figures.mjs"));
if (process.argv.includes("--figures-only")) {
  writePlanFigures(read("site/data/school-budget-plans.json"));
  process.exit(0);
}

const t0 = Date.now();
const TB = buildTable();
{
  const e = writeOut("car", 0, { sets: Object.fromEntries(SCH.map((x) => [x.cds, {}])), city: { seg: 0, carpool: 0, calm: 0, muni: 0 }, picks: 0 }).at.central;
  for (const a of ["assign_ncp52", "assign_ncp"]) { const x = MD.alone(a); console.log(`assignment ${a} alone, citywide model: ${x.cars.map(Math.round).join(" / ")} out of single-family cars, ${x.hurt.map((h) => h.toFixed(2)).join(" / ")} kids hurt spared`); }
  console.log(`background, the assignment alone: by car ${e.modes[0].toFixed(0)} (today ${T00.modes[0].toFixed(0)}), fewer hurt ${e.hurt.map((x) => x.toFixed(2)).join("/")}`);
}
console.log(`table: ${TB.slots.length} slots, ${TB.slots.reduce((t, s) => t + s.levels.length, 0)} levels (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
const BG_HURT = writeOut("car", 0, { sets: Object.fromEntries(SCH.map((x) => [x.cds, {}])), city: { seg: 0, carpool: 0, calm: 0, muni: 0 }, picks: 0 }).at.central.hurt[1];
const plans = {}, sels = {};
for (const b of BUDGETS) {
  const sel = planAll(TB, b);
  for (const goal of GOALS) {
    const p = fromSel(TB, sel[goal]), o = writeOut(goal, b, p);
    const at = o.at.central, spent = at.once + YEARS * at.year;
    // Quality: within budget, and no worse than doing nothing.
    if (spent > b + 0.005) throw new Error(`school-budget-plans: ${goal} $${b}M spends $${spent.toFixed(2)}M`);
    // Each plan beats doing nothing on its own goal. A car plan may raise kids hurt a little, since its new walkers and
    // riders carry their own risk.
    const ownCars = Object.values(at.carsBy).reduce((t, x) => t + x, 0);
    if ((goal !== "safety" && !(ownCars > 0)) || (goal !== "car" && !(at.hurt[1] > BG_HURT))) throw new Error(`school-budget-plans: ${goal} $${b}M has no gain (hurt ${at.hurt}, cars ${ownCars})`);
    if (goal === "balanced") o.norm = { cars: r4(sel.norm.cars), hurt: r4(sel.norm.hurt) };
    plans[`${goal}${b}`] = o;
    sels[`${goal}${b}`] = sel[goal];
    console.log(`${goal} $${b}M: spends $${spent.toFixed(1)}M (once $${at.once.toFixed(1)}M, $${at.year.toFixed(2)}M a year), ${Object.keys(o.schools).length} schools, city ${JSON.stringify(o.city)}`);
    const mid = Object.values(at.carsBy).reduce((t, x) => t + x, 0);
    console.log(`  by car ${at.modes[0].toFixed(0)} (today ${T00.modes[0].toFixed(0)}); out of cars by the plan's changes ${mid.toFixed(0)} (${at.carsOut.map((x) => x.toFixed(0)).join(" to ")}), fewer hurt ${at.hurt.map((x) => x.toFixed(2)).join("/")}, counts ${JSON.stringify(o.count)}`);
  }
}
console.log(`plans: ${((Date.now() - t0) / 1000).toFixed(0)}s`);

// The check: the table's pick against a greedy that rescores every move exactly after each pick, every change on.
// The check is slow (the car greedy at $100M takes about an hour), so it can be split over processes:
// PLANS_EXACT_KEYS=car40,safety40 runs only those and PLANS_EXACT_DUMP=<file> writes them there and stops;
// PLANS_EXACT_FROM=<file>,<file> then skips the check and, before writing, waits for and merges those files.
const exactCheck = {};
const EXACT_KEYS = process.env.PLANS_EXACT_KEYS ? new Set(process.env.PLANS_EXACT_KEYS.split(",")) : null;
const EXACT_FROM = process.env.PLANS_EXACT_FROM ? process.env.PLANS_EXACT_FROM.split(",") : null;
// A subset of the check written to the tracked file would change it with how the run was split.
if (EXACT_KEYS && !process.env.PLANS_EXACT_DUMP) throw new Error("PLANS_EXACT_KEYS needs PLANS_EXACT_DUMP");
if (process.env.PLANS_EXACT !== "0" && !EXACT_FROM) {
  for (const b of BUDGETS) for (const goal of ["car", "safety"]) {
    if (EXACT_KEYS && !EXACT_KEYS.has(`${goal}${b}`)) continue;
    const te = Date.now();
    const p = planExact(goal, b), o = writeOut(goal, b, p), a = o.at.central, t = plans[`${goal}${b}`].at.central;
    const val = (x) => (goal === "car" ? T00.modes[0] - x.modes[0] : x.hurt[1]);
    // A wall-clock time is printed, never written, so a rerun with no new data changes no file.
    exactCheck[`${goal}${b}`] = { table: r4(val(t)), exact: r4(val(a)), gapPct: r4(100 * (val(a) - val(t)) / Math.max(Math.abs(val(a)), 1e-9)) };
    console.log(`check ${goal} $${b}M: table ${val(t).toFixed(2)}, exact greedy ${val(a).toFixed(2)}, gap ${exactCheck[`${goal}${b}`].gapPct.toFixed(2)}%, exact city ${JSON.stringify(p.city)} spends $${o.at.central.once != null ? (o.at.central.once + YEARS * o.at.central.year).toFixed(1) : "?"}M (${Math.round((Date.now() - te) / 1000)}s)`);
  }
}
if (process.env.PLANS_EXACT_DUMP) {
  // Written whole and renamed, so a PLANS_EXACT_FROM run waiting on the file never reads half of it.
  fs.writeFileSync(process.env.PLANS_EXACT_DUMP + ".tmp", JSON.stringify(exactCheck) + "\n");
  fs.renameSync(process.env.PLANS_EXACT_DUMP + ".tmp", process.env.PLANS_EXACT_DUMP);
  console.log("wrote " + process.env.PLANS_EXACT_DUMP);
  process.exit(0);
}
// The page's re-plan check. With one change turned off, the page re-picks by the same greedy on the same table and
// moves the full plan's figures by the table's difference between the two picks. Here each such re-pick is also
// scored exactly, in the central case, and the largest miss is printed and kept.
const LEVERS = [...new Set(TB.slots.map((sl) => sl.lever))].sort();
const replanCheck = { cases: 0, carsMaxPct: 0, hurtMaxPct: 0, hurtMaxAbs: 0, worst: null };
for (const b of BUDGETS) {
  const full = planAll(TB, b);
  for (const lever of LEVERS) {
    const sel = planAll(TB, b, { [lever]: 0 });
    for (const goal of GOALS) {
      const P0 = plans[`${goal}${b}`].at.central, dA = tableSum(TB, sel[goal]), dB = tableSum(TB, full[goal]);
      const dv = dA.v.map((x, q) => x - dB.v[q]), V = (k) => dv[VKEYS.indexOf(k)];
      const approx = { cars: P0.modes[0] + dv[0], hurt: replanHurt(TB, P0.H, dA, dB, MD.HB)[1] };
      const ex = writeOut(goal, b, fromSel(TB, sel[goal])).at.central;
      const eC = 100 * Math.abs(approx.cars - ex.modes[0]) / Math.max(1, T00.modes[0] - ex.modes[0]);
      const eH = 100 * Math.abs(approx.hurt - ex.hurt[1]) / Math.max(0.05, Math.abs(ex.hurt[1]));
      if (process.env.PLANS_DEBUG && eH > 5) console.log("  re-plan miss", goal, b, lever, approx, ex.modes[0], ex.hurt);
      replanCheck.cases++;
      replanCheck.hurtMaxAbs = Math.max(replanCheck.hurtMaxAbs, r4(Math.abs(approx.hurt - ex.hurt[1])));
      if (eC > replanCheck.carsMaxPct) replanCheck.carsMaxPct = r4(eC);
      if (eH > replanCheck.hurtMaxPct) { replanCheck.hurtMaxPct = r4(eH); replanCheck.worst = `${goal}${b} without ${lever}`; }
    }
  }
}
console.log(`re-plan check: ${replanCheck.cases} plans with one change off; page figures miss the exact score by at most ${replanCheck.carsMaxPct.toFixed(2)}% of students out of cars, ${replanCheck.hurtMaxPct.toFixed(2)}% of kids hurt spared (worst ${replanCheck.worst}), at most ${replanCheck.hurtMaxAbs.toFixed(2)} kids hurt a year`);
if (EXACT_FROM) {
  const pause = new Int32Array(new SharedArrayBuffer(4));
  for (const f of EXACT_FROM) {
    while (!fs.existsSync(f)) Atomics.wait(pause, 0, 0, 10000);
    Object.assign(exactCheck, JSON.parse(fs.readFileSync(f, "utf8")));
  }
  const want = BUDGETS.flatMap((b) => ["car", "safety"].map((g) => `${g}${b}`));
  const missing = want.filter((k) => !(k in exactCheck));
  if (missing.length) throw new Error("PLANS_EXACT_FROM lacks " + missing.join(", "));
  // Same key order as the single-process run, so the file does not change with how the check was split.
  const merged = Object.fromEntries(want.map((k) => [k, exactCheck[k]]));
  for (const k of Object.keys(exactCheck)) delete exactCheck[k];
  Object.assign(exactCheck, merged);
}
const T0 = MD.fig(MD.TODAY);
// The table, rounded and keyed for the page: each slot's school, change and levels.
const table = { fixed: TB.fixed, vkeys: VKEYS, slots: TB.slots.map((sl) => ({ cds: sl.cds || null, lever: sl.lever,
  levels: sl.levels.map((L) => ({ id: L.id, patch: L.patch, cars: L.cars, hurt: L.hurt, cost: L.cost, v: L.v, h: L.h })) })), hb: MD.HB };
fs.writeFileSync(OUT, JSON.stringify({
  note: "Written by tools/school-trips/school-budget-plans.mjs. For each goal (car: fewest students by single-family car; safety: fewest kids hurt; "
    + "balanced: both, each over its own plan's reach at the budget) and four-year budget in $M, the changes a greedy plan funds at each school "
    + "and citywide, and its totals in the sim's central case (at.central), with low and high. Every plan holds SFUSD's Neighborhood + Citywide Programs assignment. table is "
    + "what the greedy picks from (site/src/school-trips-plan.mjs), for the page to re-plan with a change turned off; exactCheck compares its pick "
    + "with a greedy that rescores every move exactly.",
  years: YEARS, background: BG, budgets: BUDGETS, goals: GOALS, today: { car: Math.round(T0.modes[0]) }, plans, table, exactCheck, replanCheck,
}) + "\n");
console.log("wrote " + path.relative(ROOT, OUT));
writePlanFigures(read("site/data/school-budget-plans.json"));
