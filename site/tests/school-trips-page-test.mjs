#!/usr/bin/env node
// Proof that School Trips' browser model builds from the city.json the page ships and the goals controls move figures.
// The Citywide Goals view's sliders and presets must redraw its cards, each card's labelled parts adding up to its headline.
//
//     node site/tests/school-trips-page-test.mjs
//
// The page builds makeCityModel in the browser from city.json as published, which past 4 MB is split from its school
// list (city-schools.json, fetched after the model is built). On 2026-10-24 the model read the school list while it was
// building, so on the split file it threw, the page kept the data without its model, and every control on the goals
// view crashed before the view could redraw. This test builds the model the way the browser does, from the page's own
// inline data and the city.json the build writes, then drives wedgeUI in linkedom with a stand-in for Observable Plot
// that records each mark. Part of `npm run check` in site/. Light: renders the page once, no simulation.
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const SITE = path.join(ROOT, "site");
// linkedom is the site's dependency, so it resolves from site/.
const { parseHTML } = await import(createRequire(path.join(SITE, "package.json")).resolve("linkedom"));
const page = await import(path.join(SITE, "src/pages/transportation-school-trips.mjs"));
const { makeCityModel } = await import(path.join(SITE, "src/school-trips-model.mjs"));
const { wedgeView, wedgeUI, wedgeConfig } = await import(path.join(SITE, "src/school-trips-wedges.mjs"));

let n = 0;
const ok = (name, fn) => { fn(); n++; console.log("  ok  " + name); };

const html = page.render();
const D = JSON.parse(html.match(/<script type="application\/json" id="tr-data">([\s\S]*?)<\/script>/)[1]);
const files = page.pages();
const shipped = files.find((f) => f.path.endsWith("/city.json"));
const CJ = JSON.parse(shipped.html);
const split = files.some((f) => f.path.endsWith("/city-schools.json"));

let MD = null;
const opts = { schools: D.ix.schools, rules: D.rules, cost: D.costs };
ok(`the browser's model builds from city.json as shipped${split ? " (split from its school list)" : ""}`, () => {
  if (split) assert.equal(CJ.schools, undefined, "a split city.json carries no school list");
  MD = makeCityModel(CJ, opts);
});
// The split, forced, so the check holds whatever size city.json is: the model without the school list gives the same figures.
ok("the model gives the same figures with and without the school list", () => {
  const full = JSON.parse(fs.readFileSync(path.join(SITE, "data/school-sim/city.json"), "utf8"));
  const { schools, ...rest } = full;
  const A = makeCityModel(full, opts), B = makeCityModel({ ...rest, schoolStudents: schools.students.reduce((t, x) => t + x, 0) }, opts);
  for (const steps of [D.wedges.plan, D.wedges.full]) {
    const c = wedgeConfig(A.OFF, steps);
    assert.deepEqual([B.figC(c).modes, B.hurt(c), B.cost(c)], [A.figC(c).modes, A.hurt(c), A.cost(c)]);
  }
});
ok("the model answers the City view's first draw and both goals presets", () => {
  for (const steps of [D.wedges.plan, D.wedges.full]) {
    const c = wedgeConfig(MD.OFF, steps), k = MD.cost(c);
    assert.ok(Number.isFinite(k.once) && Number.isFinite(k.year), "cost");
    assert.ok(Number.isFinite(MD.figC(c).modes[0]), "students by car");
    assert.ok(Number.isFinite(MD.hurt(c)), "kids hurt");
  }
});

// The goals view in linkedom, with Plot replaced by a recorder of each chart's marks: the car card's bar draws first,
// then the injury card's.
const { window, document } = parseHTML(`<!doctype html><html><body>${wedgeView(D.wedges.T)}</body></html>`);
let plots = [];
const mk = (type) => (data, o = {}) => ({ type, data, o });
globalThis.window = window;
globalThis.Plot = window.Plot = {
  plot: (spec) => { plots.push(spec.marks); return document.createElement("div"); },
  rect: mk("rect"), text: mk("text"), link: mk("link"), ruleX: mk("ruleX"),
};
const root = document.getElementById("v-goals");
const WG = wedgeUI(root, D.wedges.T, D.wedges.W, D.wedges.plan, D.wedges.full, () => draw());
const draw = () => { plots = []; WG.draw(); };
const big = (k) => root.querySelector(`[data-wg-big=${k}]`).textContent;
const head = (k) => Number(big(k).match(/^-?[\d,.]+/)[0].replace(/,/g, ""));
// A bar's part labels, each its count line and its wedge's short name; a part that moves the figure the wrong way
// ("12 more in cars") counts against the headline.
const labels = (j) => plots[j].filter((m) => m.type === "text" && m.o.text === "t").flatMap((m) => m.data.map((q) => q.t));
const value = (t) => Number(t.split("\n")[0].split(" ")[0].replace(/,/g, "")) * (t.includes(" more ") ? -1 : 1);
const sum = (L, d) => Math.round(L.reduce((s, t) => s + value(t), 0) * 10 ** d) / 10 ** d;
const names = new Set(D.wedges.W.map((w) => w.short));
draw();
const planCar = big("car"), planHurt = big("hurt");

ok(`the plan preset's parts are labelled and add up to each headline (${planCar.split("students")[0].trim()}, ${planHurt})`, () => {
  for (const j of [0, 1]) {
    const L = labels(j);
    assert.ok(L.length >= 2, `parts printed: ${JSON.stringify(L)}`);
    for (const t of L) assert.ok(names.has(t.split("\n")[1]), `"${t}" names its wedge`);
  }
  assert.equal(sum(labels(0), 0), head("car"), `car parts ${JSON.stringify(labels(0))}`);
  assert.equal(sum(labels(1), 1), head("hurt"), `hurt parts ${JSON.stringify(labels(1))}`);
});
ok("Fill Every Wedge switches the figures and the pressed preset", () => {
  root.querySelector('[data-wpre="full"]').dispatchEvent(new window.Event("click", { bubbles: true }));
  assert.notEqual(big("car"), planCar);
  assert.notEqual(big("hurt"), planHurt);
  assert.equal(root.querySelector('[data-wpre="full"]').getAttribute("aria-pressed"), "true");
  assert.equal(root.querySelector('[data-wpre="plan"]').getAttribute("aria-pressed"), "false");
  console.log(`      Fill Every Wedge: ${big("car")}; ${big("hurt")}`);
});
ok("SFMTA's Plan switches back", () => {
  root.querySelector('[data-wpre="plan"]').dispatchEvent(new window.Event("click", { bubbles: true }));
  assert.equal(big("car"), planCar);
  assert.equal(big("hurt"), planHurt);
});
ok("a slider moves the figures", () => {
  const s = root.querySelector('[data-wedge="0"]');
  s.value = s.getAttribute("max");
  s.dispatchEvent(new window.Event("input", { bubbles: true }));
  assert.notEqual(big("car"), planCar);
});
ok("in every combination of steps, a bar's printed parts add up to its headline", () => {
  let tried = 0;
  for (const r of D.wedges.T.rows) {
    WG.set([...r.s].map(Number)); draw();
    const car = labels(0), hurt = labels(1);
    // A bar with one part and nothing against it prints no label (the headline is that part); otherwise every part is printed.
    if (car.length) { assert.equal(sum(car, 0), head("car"), `${r.s}: car parts ${JSON.stringify(car)}`); tried++; }
    if (hurt.length) { assert.equal(sum(hurt, 1), head("hurt"), `${r.s}: hurt parts ${JSON.stringify(hurt)}`); tried++; }
  }
  assert.ok(tried > 0);
});
ok("the phone summary row no longer repeats the headlines", () => assert.equal(root.querySelector("[data-wg-strip]"), null));
// The injury goal is 30% of the model's base, as the About page says, and its bar starts at none avoided, not at "0 today".
const ends = (j) => plots[j].filter((m) => m.type === "text" && typeof m.o.text === "function").map((m) => m.o.text());
ok("the injury bar runs from none avoided to 30% of the kids hurt a year", () => {
  draw();
  const base = D.wedges.T.hurtBase, fmt = (x) => Math.round(x).toLocaleString("en-US");
  assert.deepEqual(ends(1), ["None avoided yet", `Goal ${fmt(0.3 * base)} of ${fmt(base)}`]);
  assert.deepEqual(ends(0), [`${(Math.round(D.wedges.T.tallyToday * 10) / 10).toFixed(1)}% today`, "Goal 30%"]);
});
// A control's label names the step it is on, so its Ideas list holds only what the model doesn't count yet.
ok("no Ideas list repeats an idea its control counts", () => {
  const items = root.querySelectorAll(".wg-w li:not(.wg-safe)");
  assert.ok(items.length > 0);
  for (const li of items) assert.equal(li.querySelector("em").textContent, "Not counted yet", li.textContent);
  for (const b of root.querySelectorAll(".wg-ideas")) assert.ok(root.querySelector("#" + b.getAttribute("aria-controls")), "an Ideas button opens a list");
});

console.log(`school trips page: pass (${n} checks)`);
