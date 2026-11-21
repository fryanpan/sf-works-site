// School Trips' budget plans, picked from a table of candidates. Shared by tools/school-trips/school-budget-plans.mjs, which
// builds the table and scores each plan exactly, and the page, which re-plans in the browser when a change is turned
// off under Advanced Options. One function, so the two can't pick differently.
//
// The table (school-budget-plans.json's table) holds slots: one per school and change, and one per citywide step
// (new bikeways, carpool matching, speed limits). A slot has levels, cheapest first: one for most changes, the three
// reaches of the safety upgrades, the five budgets of new bikeways. Each level carries what it does alone on the plan's
// background (students out of single-family cars, kids hurt a year spared, its four-year cost in $M) and its change to
// each figure the page shows (v, in VKEYS' order). fixed holds a change's citywide program ({cost, v}), charged once with
// the first school that takes it.
//
// The greedy starts from nothing and keeps taking the move, a slot to a higher level, with the most gain per dollar
// that still fits the budget, and is rerun with each citywide ladder level held fixed, keeping the best. Gain is the goal's: car counts students out of single-family cars, safety kids hurt
// spared, and balanced the two each divided by what that goal's own plan reaches at the same budget, so 1 is the best
// the table finds for that goal. A move must do something for the goal: at least 1 student out of a car, or 0.01 kids
// hurt a year spared, or either for balanced. Without that floor the safety plan spent its last $11M on free Muni at
// 79 schools for 0.016 kids a year.
export const VKEYS = ["car", "carpool", "walk", "bike", "transit", "bus", "min", "alone", "safe", "once", "year", "people", "ss", "drv", "pool", "hurt0", "hurt1", "hurt2"];

export function planGreedy(T, goal, budget, avail = null, norm = null) {
  // The table files citywide caregiver Muni as lever "muni"; the page's switch is keyed by its program, caregiver_muni.
  const SWITCH = { muni: "caregiver_muni" };
  const ok = (lever) => !avail || avail[SWITCH[lever] || lever] !== 0;
  const val = (L) => (goal === "car" ? L.cars : goal === "safety" ? L.hurt : L.cars / Math.max(norm.cars, 1e-9) + L.hurt / Math.max(norm.hurt, 1e-9));
  const Z = { cars: 0, hurt: 0, cost: 0 };
  // One greedy pass; fix = [slot, level] holds a slot at that level (-1 for none) and leaves it out of the moves.
  const run = (fix) => {
    const lvl = T.slots.map(() => -1), used = new Set();
    let spent = 0;
    if (fix && fix[1] >= 0) {
      const s = T.slots[fix[0]];
      lvl[fix[0]] = fix[1];
      spent = s.levels[fix[1]].cost + (T.fixed[s.lever] ? T.fixed[s.lever].cost : 0);
      used.add(s.lever);
      if (spent > budget + 1e-9) return null;
    }
    for (;;) {
      let best = null;
      for (let i = 0; i < T.slots.length; i++) {
        const s = T.slots[i];
        if (!ok(s.lever) || (fix && fix[0] === i)) continue;
        const cur = lvl[i] >= 0 ? s.levels[lvl[i]] : Z, v0 = val(cur);
        for (let j = lvl[i] + 1; j < s.levels.length; j++) {
          const L = s.levels[j], dv = val(L) - v0, dc = L.cost - cur.cost + (used.has(s.lever) || !T.fixed[s.lever] ? 0 : T.fixed[s.lever].cost);
          const dCars = L.cars - cur.cars, dHurt = L.hurt - cur.hurt;
          const worth = goal === "car" ? dCars >= 1 : goal === "safety" ? dHurt >= 0.01 : dCars >= 1 || dHurt >= 0.01;
          if (dv <= 1e-9 || !worth || spent + dc > budget + 1e-9) continue;
          const ratio = dc > 1e-9 ? dv / dc : Infinity;
          if (!best || ratio > best.ratio + 1e-12) best = { i, j, dc, ratio };
        }
      }
      if (!best) break;
      lvl[best.i] = best.j;
      spent += best.dc;
      used.add(T.slots[best.i].lever);
    }
    return lvl;
  };
  const score = (lvl) => lvl.reduce((t, j, i) => t + (j >= 0 ? val(T.slots[i].levels[j]) : 0), 0);
  // A citywide ladder (the new bikeways' budget steps) is one big lump: the greedy can take a step early and then have
  // no room for the next, leaving money unspent (car $80M stopped at $75.1M, 2026-10-21). So each of the ladder's
  // levels, and none, is also tried held fixed with the greedy filling the rest, and the best of all is kept.
  let bestLvl = run(null), bestScore = score(bestLvl);
  T.slots.forEach((s, i) => {
    if (s.cds != null || s.levels.length < 2 || !ok(s.lever)) return;
    for (let j = -1; j < s.levels.length; j++) {
      if (j === bestLvl[i]) continue;
      const lvl = run([i, j]);
      if (!lvl) continue;
      const sc = score(lvl);
      if (sc > bestScore + 1e-9) { bestLvl = lvl; bestScore = sc; }
    }
  });
  return bestLvl;
}

// A selection's table sums: cars, hurt, cost, and each VKEYS figure.
export function tableSum(T, lvl) {
  const out = { cars: 0, hurt: 0, cost: 0, v: VKEYS.map(() => 0), carsBy: {}, h: {} };
  const used = new Set();
  lvl.forEach((j, i) => {
    if (j < 0) return;
    const s = T.slots[i], L = s.levels[j];
    out.cars += L.cars; out.hurt += L.hurt; out.cost += L.cost;
    L.v.forEach((x, q) => (out.v[q] += x));
    out.carsBy[L.id] = (out.carsBy[L.id] || 0) + L.cars;
    for (const [t, d] of Object.entries(L.h || {})) { out.h[t] = out.h[t] || [0, 0, 0]; d.forEach((x, k) => (out.h[t][k] += x)); }
    used.add(s.lever);
  });
  for (const lever of used) if (T.fixed[lever]) { out.cost += T.fixed[lever].cost; T.fixed[lever].v.forEach((x, q) => (out.v[q] += x)); }
  return out;
}

// The three goals' selections at one budget: car and safety first, then balanced on their reach.
export function planAll(T, budget, avail = null) {
  const car = planGreedy(T, "car", budget, avail), safety = planGreedy(T, "safety", budget, avail);
  const norm = { cars: tableSum(T, car).cars, hurt: tableSum(T, safety).hurt };
  return { car, safety, balanced: planGreedy(T, "balanced", budget, avail, norm), norm };
}

// Kids hurt spared, low, central and high, for a re-picked plan: the full plan's cut by each injury type (H), moved by
// the table's difference between the two picks, then combined as the build's totals() does, each type cutting what
// the others leave (hb is the base of kids hurt a year).
export function replanHurt(T, H, dA, dB, hb) {
  const types = new Set([...Object.keys(H || {}), ...Object.keys(dA.h), ...Object.keys(dB.h)]);
  // Each type's three figures moved by the table difference, then low and high taken per type (they aren't ordered).
  const xs = [...types].map((t) => [0, 1, 2].map((k) => ((H || {})[t] || [0, 0, 0])[k] + (dA.h[t] || [0, 0, 0])[k] - (dB.h[t] || [0, 0, 0])[k]));
  const comb = (pick) => hb * (1 - xs.reduce((keep, x) => keep * (1 - pick(x) / hb), 1));
  return [comb((x) => Math.min(...x)), comb((x) => x[1]), comb((x) => Math.max(...x))];
}
