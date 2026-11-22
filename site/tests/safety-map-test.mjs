#!/usr/bin/env node
// Tests for the Street Safety map's state (site/src/safety-map/state.js) and the story block's steps
// (site/src/safety-map/story.mjs): an address round-trips to the same state and back, every state a story step
// names survives the trip, and each move between steps fades exactly the layers that differ.
//
//   node site/tests/safety-map-test.mjs        # exits 1 on the first failure
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";

import { ROOT, script } from "../scripts/lib/repo.mjs";
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "site/src/safety-map/state.js"), "utf8"), ctx);
const S = ctx.SafetyMapState;
const plain = (v) => JSON.parse(JSON.stringify(v));   // out of the vm's realm, for deepEqual
let n = 0;
const test = (name, fn) => { fn(); n++; console.log(`ok ${n} ${name}`); };

test("the default state has an empty address", () => {
  assert.equal(S.toHash(S.DEFAULTS), "");
  assert.deepEqual(plain(S.fromHash("")), plain(S.DEFAULTS));
});

const FULL = {
  view: "injuries", camera: { center: [-122.43605, 37.79984], zoom: 17.2, bearing: 12.5 }, hin: ["2024", "2017"], color: "hin",
  filter: { user: "Car or truck", severity: "killed", hin: "off", at: "intersection" }, highlight: { circle: { center: [-122.43605, 37.79984], feet: 120 } }, crash: "220399065",
};

test("state to address to state is the same state", () => {
  for (const s of [FULL, { view: "stress" }, { view: "crime", camera: { center: [-122.414, 37.781], zoom: 13.2 } }, { highlight: { area: "South of Market" } },
    { highlight: { blocks: [9001, 512, 77] } }, { hin: [] }, { filter: { user: "Walking", hin: "on" } }]) {
    const a = S.normalize(s);
    assert.deepEqual(plain(S.fromHash(S.toHash(a))), plain(a), JSON.stringify(s));
  }
});

test("address to state to address is the same address", () => {
  for (const h of ["#view=crime&at=-122.41400,37.78100,13.20", "#hin=2024,2022&user=Walking&on=off", "#area=South%20of%20Market&crash=220399065", "#hin=none&where=midblock",
    "#view=bike&ring=-122.43605,37.79984,120", "#color=hin&blocks=77,512,9001", "#view=bike&bci=0,2"]) {
    assert.equal(S.toHash(S.fromHash(h)), h);
  }
});

test("the scratch map's old addresses still open their view", () => {
  assert.equal(S.fromHash("#view=people").view, "injuries");
  assert.equal(S.fromHash("#stress-z13").view, "stress");
  const k = S.fromHash("#view=kind");
  assert.equal(k.view, "injuries");
  assert.equal(k.color, "people");
});

test("the retired crash groups: old links open the injuries view as it opens by default", () => {
  // Bryan, 2026-11-19: "Remove crash groups".
  assert.ok(!S.CHARTS.injuries.includes("by-group"));
  for (const h of ["#color=group", "#chart=by-group", "#color=group&chart=by-group", "#view=kind"]) {
    const s = S.fromHash(h);
    assert.equal(s.color, "people", h);
    assert.equal(s.chart, null, h);
    assert.equal(S.toHash(s), "", h);
    assert.ok(!S.layersFor(s).includes("kind"), h);
  }
  assert.equal(S.toHash(S.fromHash("#color=group&user=Walking")), "#user=Walking");
});

test("the bike comfort classes filter: any of the five, all five is none, and only on the bike view", () => {
  // Bryan, 2026-11-19: "Make this filterable on BCI index on the bike comfort map".
  assert.deepEqual(plain(S.normalize({ filter: { bci: [3, 1, 3, 9, -1, 1.5] } }).filter.bci), [1, 3]);
  assert.deepEqual(plain(S.normalize({ filter: { bci: [0, 1, 2, 3, 4] } }).filter.bci), []);
  assert.deepEqual(plain(S.fromHash("#view=bike&bci=2").filter.bci), [2]);
  assert.equal(S.toHash(S.normalize({ view: "bike", filter: { bci: [4, 0] } })), "#view=bike&bci=0,4");
  assert.ok(S.FILTERS.bike.includes("bci") && !S.FILTERS.injuries.includes("bci"));
  assert.deepEqual(plain(S.DEFAULTS.filter.bci), []);
});

test("the 10-mile groups follow the HIN edition picked", () => {
  assert.equal(S.hinEdition(S.fromHash("")), "2024");
  assert.equal(S.hinEdition(S.fromHash("#hin=2022")), "2022");
  assert.equal(S.hinEdition(S.fromHash("#hin=groups22")), "2022");
  assert.equal(S.hinEdition(S.fromHash("#hin=2017")), "2017");
  assert.equal(S.groupKey(S.fromHash("#hin=groups22&rank=2022-2024")), "hg22:2022-2024");
  assert.equal(S.groupKey(S.fromHash("#hin=groups")), "hg:2020-2024");
  assert.equal(S.toHash(S.fromHash("#hin=groups22&groups=2")), "#hin=groups22&groups=2");
  assert.ok(S.layersFor(S.fromHash("#hin=groups22")).includes("hin-groups"));
});

test("bad values fall back to the defaults rather than breaking the map", () => {
  const s = S.normalize({ view: "nope", hin: ["1999", "2022"], filter: { user: "Horse", severity: "some" }, camera: { center: ["x", 37.7], zoom: 99 }, highlight: { area: "" } });
  assert.equal(s.view, "injuries");
  assert.deepEqual(plain(s.hin), ["2022"]);
  assert.deepEqual(plain(s.filter.user), []);
  assert.equal(s.filter.severity, "severe");
  assert.equal(s.camera.zoom, 19);
  assert.equal(s.highlight, null);
});

test("merge lays a partial over a state, field by field for camera and filter", () => {
  const a = S.merge(FULL, { filter: { user: "Walking" }, camera: { zoom: 12 } });
  assert.deepEqual(plain(a.filter.user), ["Walking"]);
  assert.equal(a.filter.hin, "off");
  assert.equal(a.camera.zoom, 12);
  assert.deepEqual(plain(a.camera.center), FULL.camera.center);
  assert.equal(S.merge(FULL, { camera: null }).camera, null);
  assert.equal(S.merge(FULL, { highlight: null }).highlight, null);
});

test("a view switch fades out every layer of the old view and in every layer of the new", () => {
  const p = S.plan({ view: "injuries" }, { view: "stress" });
  assert.deepEqual(plain(p.fadeOut).sort(), ["fan", "fan-lab", "heat", "hin", "hin-outline", "minor", "minor-fan"]);
  assert.deepEqual(plain(p.fadeIn).sort(), ["stress-est", "stress-grey", "stress-meas", "stress-mod"]);
  assert.equal(p.camera, false);
});

test("an unchanged state plans nothing", () => {
  const p = S.plan(FULL, FULL);
  assert.equal(p.fadeIn.length + p.fadeOut.length, 0);
  assert.ok(!p.camera && !p.filter && !p.highlight && !p.crash);
});

test("filters, highlights and the crash card are planned as switches", () => {
  const p = S.plan({}, { filter: { hin: "off" }, highlight: { area: "Mission" }, crash: "1" });
  assert.ok(p.filter && p.highlight && p.crash);
  assert.deepEqual(plain(p.fadeIn), ["hl-area-fill", "hl-area-line"]);
});

test("the people filter keeps the same people in the map's expression and the figures' count", () => {
  const people = [{ u: "Walking", k: 1, sv: 0, hy: 4, at: 1, d: "2022-03-01", wd: 2, h: 8, ck: "red-light", sk: "21453(a)", "hg:2020-2024": 1, "hg:2022-2024": 2 },
    { u: "Walking", k: 0, sv: 1, hy: 2, at: 0, d: "2023-05-06", wd: 6, h: 23, ck: "red-light", sk: "other", "hg:2020-2024": 0, "hg:2022-2024": 0 },
    { u: "Biking", k: 0, sv: 2, hy: 6, at: 1, d: "2024-01-07", wd: 0, h: -1, ck: "dui", sk: "23152(a)", "hg:2020-2024": 3, "hg:2022-2024": 1 },
    { u: "Car or truck", k: 1, sv: 0, hy: 0, at: 0, d: "2024-12-31", wd: 2, h: 2, ck: "unsafe-speed", sk: "22350", "hg:2020-2024": 0, "hg:2022-2024": 0 },
    { u: "Car or truck", k: 0, sv: 3, hy: 4, at: 0, d: "2023-02-02", wd: 4, h: 17, ck: "unsafe-speed", sk: "22350", "hg:2020-2024": 2, "hg:2022-2024": 2 }];
  const evalExpr = (e, p) => {   // the few MapLibre expression operators peopleFilter uses
    const [op, ...a] = e;
    const v = (x) => (Array.isArray(x) ? evalExpr(x, p) : x);
    switch (op) {
      case "all": return a.every((x) => v(x));
      case "get": return p[a[0]];
      case "==": return v(a[0]) === v(a[1]);
      case "!=": return v(a[0]) !== v(a[1]);
      case "%": return v(a[0]) % v(a[1]);
      case "/": return v(a[0]) / v(a[1]);
      case "floor": return Math.floor(v(a[0]));
      case "any": return a.some((x) => v(x));
      case "literal": return a[0];
      case "in": return v(a[1]).includes(v(a[0]));
      case "slice": return String(v(a[0])).slice(v(a[1]), v(a[2]));
      case ">=": return v(a[0]) >= v(a[1]);
      case "<=": return v(a[0]) <= v(a[1]);
      case "<": return v(a[0]) < v(a[1]);
      default: throw new Error(op);
    }
  };
  for (const f of [{}, { hin: "off" }, { hin: "on" }, { user: "Walking", at: "intersection" }, { severity: "killed" }, { at: "midblock", hin: "off" },
    { user: ["Walking", "Biking"] }, { cause: ["red-light"] }, { cause: ["red-light/other", "dui"] }, { years: [2023, 2024] }, { years: [2022, 2022] },
    { days: ["weekend"] }, { days: ["weekday"], time: "night" }, { time: "am" }, { cause: ["dui/23152(a)"], days: ["weekend"], years: [2024, 2024] },
    { days: ["fri"], time: "evening" }, { time: ["am", "night"] }, { days: ["sat", "mon"], time: ["pm", "evening"] }, { days: ["weekend"], time: ["midday", "night"] },
    { severity: "visible" }, { severity: "pain" }, { severity: "pain", hinGroup: [2] }, { hinGroup: [1, 3] }]) {
    for (const rank of ["2020-2024", "2022-2024"]) {
    const s = { filter: f, rank };
    const expr = plain(S.peopleFilter(s));
    assert.deepEqual(people.map((p) => evalExpr(expr, p)), people.map((p) => S.personShown(s, p)), JSON.stringify(f) + " " + rank);
    }
  }
  // The severity choice shows its level and every level above it.
  assert.deepEqual(people.map((p) => S.personShown({ filter: { severity: "visible" } }, p)), [true, true, true, true, false]);
  assert.deepEqual(people.map((p) => S.personShown({ filter: { severity: "killed" } }, p)), [true, false, false, true, false]);
});

test("the 10-mile groups, ranking window and worst year round-trip through the address", () => {
  const s = S.normalize({ hin: ["groups"], rank: "2022-2024", worst: 2021, filter: { hinGroup: [3, 1, 3], severity: "pain" } });
  assert.deepEqual(plain(s.filter.hinGroup), [1, 3]);
  assert.deepEqual(plain(S.fromHash(S.toHash(s))), plain(s));
  assert.equal(S.toHash(S.normalize({})), "");
  assert.equal(S.normalize({ worst: 1999, rank: "1900-2000" }).worst, null);
  assert.equal(S.normalize({ filter: { severity: "all" } }).filter.severity, "severe");
  assert.ok(S.layersFor(s).includes("hin-groups") && S.layersFor(s).includes("worst"));
});

test("list filters store everything as nothing, and older addresses still read", () => {
  assert.deepEqual(plain(S.normalize({ filter: { user: S.USERS } }).filter.user), []);
  assert.deepEqual(plain(S.normalize({ filter: { days: S.DAYS.map((d) => d[0]) } }).filter.days), []);
  // The whole span is every year (null); no years at all is the opening span, 2021 to now; "all" in an address is every year.
  assert.equal(S.normalize({ filter: { years: [S.NEWEST_YEAR, 2005] } }).filter.years, null);
  assert.deepEqual(plain(S.normalize({ filter: {} }).filter.years), [S.INLINE_FROM, S.NEWEST_YEAR]);
  assert.equal(S.fromHash("#years=all").filter.years === null || S.normalize(S.fromHash("#years=all")).filter.years === null, true);
  assert.equal(S.toHash(S.normalize({ filter: { years: null } })), "#years=all");
  assert.deepEqual(plain(S.normalize({ filter: { years: [2024, 2023] } }).filter.years), [2023, 2024]);
  assert.deepEqual(plain(S.normalize({ filter: { cause: ["red-light/21453(a)", "red-light", "x y"] } }).filter.cause), ["red-light"]);
  // The old single-value forms: "weekdays", "weekend" and a single day read as the days they cover.
  const wk = S.weekdays(S.fromHash("#days=weekdays").filter.days);
  assert.deepEqual(plain(wk), [1, 2, 3, 4, 5]);
  assert.ok(S.weekdays(S.fromHash("#days=sat").filter.days).includes(6));
  assert.deepEqual(plain(S.fromHash("#user=Walking").filter.user), ["Walking"]);
  for (const h of ["#user=Walking,Biking&cause=dui%2F23152(a),red-light&days=" + S.DAYS[0][0] + "&years=2023-2024", "#cause=unknown-or-not-stated%2FUNKNOWN&time=night"]) {
    assert.equal(S.toHash(S.fromHash(h)), h);
  }
});

test("the day and time toggles: any set of days and times, written in their shortest form, and older addresses still read", () => {
  // Bryan, 2026-11-19: weekdays or weekends or picked days, and any of the times of day.
  const n = (f) => plain(S.normalize({ filter: f }).filter);
  assert.deepEqual(n({ days: ["mon", "tue", "wed", "thu", "fri"] }).days, ["weekday"]);
  assert.deepEqual(n({ days: ["sun", "sat"] }).days, ["weekend"]);
  assert.deepEqual(n({ days: ["weekday", "weekend"] }).days, []);
  assert.deepEqual(n({ days: ["sat", "fri"] }).days, ["fri", "sat"]);
  assert.deepEqual(n({ time: S.TIMES.map((t) => t[0]) }).time, []);
  assert.deepEqual(n({ time: ["night", "am"] }).time, ["am", "night"]);
  assert.deepEqual(n({ time: "all" }).time, []);
  // The old single choices: a time as a string, and the Friday evening entry as Friday and the evening.
  assert.deepEqual(plain(S.fromHash("#days=fri&time=evening").filter), plain(S.normalize({ filter: { days: ["fri"], time: ["evening"] } }).filter));
  assert.deepEqual(plain(S.fromHash("#time=night").filter.time), ["night"]);
  assert.deepEqual(plain(S.weekdays(["fri"])), [5]);
  assert.deepEqual(plain(S.weekdays(["weekday", "sat"])), [1, 2, 3, 4, 5, 6]);
  for (const h of ["#days=weekend&time=am,night", "#days=mon,fri&time=pm", "#time=evening", "#days=sat"]) assert.equal(S.toHash(S.fromHash(h)), h);
  assert.equal(S.whenLabel(S.normalize({}).filter), null);
  assert.equal(S.whenLabel(n({ days: ["weekday"], time: ["pm"] })), "Weekdays, evening rush");
  assert.equal(S.whenLabel(n({ days: ["fri"], time: ["evening"] })), "Fri, evening");
  assert.equal(S.whenLabel(n({ time: ["am", "night"] })), "Morning rush, night");
});

// The story's steps, read from the test story, each through the address and back, and each move between neighbours.
const { parseSteps } = await import(path.join(ROOT, "site/src/safety-map/story.mjs"));
const story = fs.readFileSync(path.join(ROOT, "site/content/transportation/street-safety/story-draft.md"), "utf8");
const inner = story.slice(story.indexOf("<MapStory"), story.indexOf("</MapStory>"));
const steps = parseSteps(inner, "story-draft.md");

test("every story step's state is valid and round-trips through the address", () => {
  assert.ok(steps.length >= 8, `${steps.length} steps`);
  for (const s of steps) {
    const a = S.merge(S.DEFAULTS, s.state);
    for (const k of Object.keys(s.state)) assert.deepEqual(plain(a[k]), k === "filter" ? { ...plain(S.DEFAULTS.filter), ...s.state.filter } : k === "camera" ? { bearing: 0, ...s.state.camera } : s.state[k], `step key ${k} kept as written`);
    assert.deepEqual(plain(S.fromHash(S.toHash(a))), plain(a));
  }
});

test("every step of the published HIN story keeps the chart, colour and networks it names", () => {
  const pub = fs.readFileSync(path.join(ROOT, "site/content/transportation/street-safety/story.md"), "utf8");
  for (const block of pub.split("<MapStory").slice(1)) {
    for (const s of parseSteps(block.slice(0, block.indexOf("</MapStory>")), "story.md")) {
      const a = S.merge(S.DEFAULTS, s.state);
      if (s.state.chart) assert.equal(a.chart && a.chart.id, s.state.chart.id, JSON.stringify(s.state));
      if (s.state.color) assert.equal(a.color, s.state.color, JSON.stringify(s.state));
      if (s.state.hin) assert.deepEqual(plain(a.hin), s.state.hin, JSON.stringify(s.state));
    }
  }
});

test("each step transition shows exactly the next step's layers, forward and back", () => {
  const states = steps.map((s) => S.merge(S.DEFAULTS, s.state));
  for (let i = 0; i + 1 < states.length; i++) {
    for (const [a, b] of [[states[i], states[i + 1]], [states[i + 1], states[i]]]) {
      const p = S.plan(a, b), before = new Set(S.layersFor(a));
      p.fadeOut.forEach((l) => before.delete(l));
      p.fadeIn.forEach((l) => before.add(l));
      assert.deepEqual([...before].sort(), plain(S.layersFor(b)).sort());
    }
  }
});

test("a step with a crash opens it and the next step closes it", () => {
  const i = steps.findIndex((s) => s.state.crash);
  assert.ok(i > 0, "the test story opens a crash card");
  const p = S.plan(S.merge(S.DEFAULTS, steps[i].state), S.merge(S.DEFAULTS, steps[i + 1].state));
  assert.ok(p.crash);
  assert.equal(S.merge(S.DEFAULTS, steps[i + 1].state).crash, null);
});

test("a malformed % in the address leaves the rest of the state", () => {
  const s = S.fromHash("#view=crime&area=Mission%ZZ");
  assert.equal(s.view, "crime");
  assert.equal(s.highlight.area, "Mission%ZZ");
});

// Every crash card, from the files tools/street-safety/street-safety-cards.py writes (one per year and map cell; a card whose
// people straddle a cell edge is in both, so each case is read once).
const CARDS_DIR = path.join(ROOT, "site/data/street-safety/cards");
const CARDS_INDEX = JSON.parse(fs.readFileSync(path.join(CARDS_DIR, "index.json"), "utf8"));
const CARDS = {}, CARD_FILE = {};
for (const k of Object.keys(CARDS_INDEX.files).sort()) {
  const F = JSON.parse(fs.readFileSync(path.join(CARDS_DIR, k + ".json"), "utf8")).cards;
  for (const c of Object.keys(F)) { if (!(c in CARDS)) CARDS[c] = F[c]; (CARD_FILE[c] = CARD_FILE[c] || []).push(k); }
}
// The file map.js asks for, from a person's own date and point.
const fileOf = (p) => `${p.d.slice(0, 4)}/${Math.floor(p.c[0] * 100) + 12260}-${Math.floor(p.c[1] * 100) - 3770}`;

test("every crash a story step opens has a card", () => {
  for (const s of steps) if (s.state.crash) assert.ok(CARDS[s.state.crash], `no crash card for ${s.state.crash}`);
});

test("every person on the map finds their card in the one file map.js would fetch", () => {
  const M = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const O = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/people-2005-2020.json"), "utf8"));
  const files = {}, file = (k) => (files[k] = files[k] || (CARDS_INDEX.files[k] ? JSON.parse(fs.readFileSync(path.join(CARDS_DIR, k + ".json"), "utf8")).cards : {}));
  const miss = [];
  for (const p of M.people) if (p.cs && !file(fileOf(p))[p.cs]) miss.push(p.cs);
  assert.deepEqual(miss, [], `${miss.length} figures whose card is not in their file`);
  // A dot carries no case number: its card is the one in its file with its date and its point among the card's people.
  // A person with no place (`np`) is counted and has no dot, so no card to find.
  let n = 0, found = 0;
  for (const L of [M.light, O]) {
    const d0 = Date.parse(L.d0 + "T00:00:00Z"), np = new Set(L.np);
    for (let i = 0; i < L.n; i++) {
      if (np.has(i)) continue;
      const p = { c: [L.x[i] / 1e5, L.y[i] / 1e5], d: new Date(d0 + L.dd[i] * 864e5).toISOString().slice(0, 10) };
      const F = file(fileOf(p)), x = L.x[i], y = L.y[i];
      n++;
      if (Object.values(F).some((cd) => cd.dt === p.d && cd.at.some((a) => a[0] === x && a[1] === y))) found++;
    }
  }
  assert.ok(n > 80000, `only ${n} dots`);
  // The few with none are victims whose crash is not in DataSF's crash table; the map shows them the victims table's popup.
  assert.ok(found >= 0.995 * n, `${n - found} of ${n} dots find no card`);
});

test("a malformed step stops the build with the page's name", () => {
  assert.throws(() => parseSteps('<MapStep state={{"view": }}>x</MapStep>', "bad.md"), /bad\.md: a <MapStep> state is not JSON/);
  assert.throws(() => parseSteps("nothing here", "bad.md"), /bad\.md: a <MapStory> has no <MapStep>/);
});

test("the story's figures that the map's own data computes match it", () => {
  const F = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8")).meta.figures;
  const c = (v) => v.toLocaleString("en-US");
  for (const t of [`${c(F.on_hin_2022)} of the ${c(F.people)}`, `${c(F.off_hin_2024)} of the ${c(F.people)}`, `${c(F.residential_with_figure)} residential blocks with a measured, modelled or estimated figure, ${c(F.residential_any_90_plus)} carry`,
    `other ${c(F.residential_blocks - F.residential_with_figure)} of the city's ${c(F.residential_blocks)} have no figure`, `240 of 338`, `${c(F.at_intersection)} of ${c(F.people)} people were hurt at an intersection`]) {
    assert.ok(story.includes(t), `the story should say "${t}"`);
  }
  assert.equal(F.walking_at_intersection, 240);
  assert.equal(F.walking, 338);
});

// The HIN story (story.md): every number in its text is either recomputed here from map.json, counted the way the
// map counts, or listed below as one the map's data doesn't hold, with where it comes from. A number added to the
// text fails the test until it is one or the other, so the text and the map can't drift apart again (the review of
// 2026-11-19, rank 1: the text said 922 people where the map counted 1,700).
test("every number in the HIN story's text is the map's own figure, or named as from elsewhere", () => {
  const D = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const pub = fs.readFileSync(path.join(ROOT, "site/content/transportation/street-safety/story.md"), "utf8");
  // The people as map.js builds them (lightPeople, prepPerson): the carded ones from `people`, the rest from `light`.
  const L = D.light, d0 = Date.parse(L.d0 + "T00:00:00Z"), np = new Set(L.np || []);
  const people = D.people.map((p) => ({ ...p }));
  for (let i = 0; i < L.n; i++) {
    const hd = L.hood[i];
    people.push({ c: np.has(i) ? null : [L.x[i] / 1e5, L.y[i] / 1e5], np: np.has(i) ? 1 : 0, d: new Date(d0 + L.dd[i] * 864e5).toISOString().slice(0, 10), h: L.h[i],
      u: L.users[L.u[i]], ck: L.cks[L.ck[i]], sk: L.sks[L.sk[i]], at: L.at[i], hood: hd >= 0 && D.hoods[hd] ? D.hoods[hd].name : "", hy: L.hy[i], hs: L.hs[i],
      op: L.ops ? L.ops[L.op[i]] : "", sv: L.sv[i], k: L.sv[i] === 0 ? 1 : 0, mi: 1 });
  }
  for (const p of people) {
    p.wd = new Date(p.d + "T12:00:00Z").getUTCDay();
    p.yr = +p.d.slice(0, 4);
    if (p.sv == null) p.sv = p.k ? 0 : 1;
    D.hinGroups.windows.forEach((w) => { p["hg:" + w] = p.hs >= 0 ? D.hinGroups.g[w][p.hs] : 0; });
  }
  // The text's years: "2021 to August 2026", the newest police report's month. Its steps show the same years.
  const newest = L.newest, month = new Date(newest + "T12:00:00Z").toLocaleString("en-US", { month: "long", timeZone: "UTC" });
  const YEARS = [2021, +newest.slice(0, 4)], period = `2021 to ${month} ${YEARS[1]}`;
  assert.ok(pub.includes(period), `the story should give its years as "${period}"`);
  const steps = [];
  for (const block of pub.split("<MapStory").slice(1)) {
    for (const s of parseSteps(block.slice(0, block.indexOf("</MapStory>")), "story.md")) {
      const a = S.merge(S.DEFAULTS, s.state);
      if (a.view === "injuries") assert.deepEqual(plain(a.filter.years), YEARS, `a step shows other years than the text: ${JSON.stringify(s.state)}`);
      steps.push({ a, md: s.md });
    }
  }
  // The people a state's headline, chart and key count (map.js shownFor): the deaths with no police report are drawn
  // but not counted, and the text stops at the newest police report too.
  const shown = (st, also = () => true) => { const t = S.shownTest(st); return people.filter((p) => !p.lg && p.d <= newest && t(p) && also(p)).length; };
  const count = (f, also) => shown({ filter: { years: YEARS, ...f } }, also);
  // Each figure is counted under the filters of the step that prints it, so a step can't show other people than its
  // text (the DUI step once drew 16 late-night deaths beside a sentence about 14 at any hour); its base is the same
  // step with the one filter lifted that the figure is a share of, which is what the step's own chart shows.
  const step = (words) => { const s = steps.find((x) => x.md.includes(words)); assert.ok(s, `no step says "${words}"`); return s.a; };
  const lift = (st, f) => S.merge(st, { filter: f });
  const share = (st, f) => [shown(st), shown(lift(st, f))];
  const pct = (a, b) => `${Math.round((100 * a) / b)}%`, unit = (a, b) => Math.round(b / a);
  const cause = (key, severity) => count({ cause: [key], ...(severity ? { severity } : {}) });
  const byCause = (severity) => D.causes.filter((c) => !/^(other|unknown)/.test(c.key)).map((c) => [c.key, cause(c.key, severity)]).sort((x, y) => y[1] - x[1]).map((x) => x[0]);
  assert.equal(byCause("pain")[0], "unsafe-speed", "unsafe speed should be the cause with the most injuries");
  assert.ok(byCause("killed").indexOf("unsafe-speed") < 3, "unsafe speed should be one of the top causes of death");
  const dui = step("as the main cause of"), speed = step("about 1 in"), ped = step("Pedestrian violations accounted"), red = step("running red lights");
  const worst = step("only accounted for"), off = step("happen off of the HIN"), night = step("All late-night crashes");
  const [duiN, duiBase] = share(dui, { cause: [] });
  assert.equal(dui.filter.severity, "killed", "the DUI step shows deaths");
  assert.deepEqual(plain(dui.filter.time), [], "the DUI step's figure is at any hour");
  // Late night in the text is 10 pm to 4 am (its note says the map's Night runs to 6 am).
  const late = (p) => p.h != null && p.h >= 0 && (p.h >= 22 || p.h < 4);
  const solo = count({ severity: "killed" }, (p) => late(p) && p.op === "none");
  const nightKilled = lift(night, { severity: "killed", time: [] }), nightKsi = lift(night, { time: [] });
  const offAll = lift(off, { severity: "pain" });
  const computed = [
    `What about the 1/${unit(...share(offAll, { hin: "all" }))} of people hurt off of the HIN?`,
    `only accounted for ${pct(...share(worst, { hinGroup: [] }))} of KSI from ${period}`,
    `unsafe speed accounts for the most injuries, about 1 in ${unit(...share(speed, { cause: [] }))}`,
    `Pedestrian violations accounted for ${pct(...share(lift(ped, { severity: "killed" }), { cause: [] }))} of deaths and ${pct(...share(ped, { cause: [] }))} of KSI`,
    `About ${pct(...share(red, { cause: [] }))} of KSI came from vehicles running red lights`,
    `the main cause of ${pct(duiN, duiBase)} of the deaths on streets from ${period} (${duiN} of ${duiBase}), at any hour`,
    `of the ${solo} people killed late at night in crashes with only one vehicle`,
    `more deaths (${shown(nightKilled, late)} to ${shown(lift(worst, { severity: "killed" }))}) and more KSI (${shown(nightKsi, late)} to ${shown(worst)})`,
    `about 1/${unit(...share(offAll, { hin: "all" }))} of all injuries and 1/${unit(...share(off, { hin: "all" }))} of severe injuries and deaths happen off of the HIN`,
  ];
  // Numbers the map's data doesn't hold, each with its source.
  const elsewhere = [
    "2024 HIN from March 2026", "the 2024 HIN", "4 AM",                    // DPH's network and its date; an example
    "November 17, 2026", "8.8 miles", "40 plus", "District 9", "400 plus", "1:20:56 and 2:06:21",   // the SFCTA hearing and its captions
    "40 or more people killed or severely injured per mile in 2020 to 2024", "2024 network", "worst 10 miles",   // DPH's top tier; the map's groups
    "cameras at 18 intersections only covers 4% (7 of 165)",                // SFMTA's camera list and DataSF uzmr-g2uc
    "\"not known\" for 12", "Vision Zero 2024 End of Year Report", "Appendix C",   // the sobriety field (8gtc-pjc6); the city's report
    "10 pm to 4 am", "10 pm to 6 am",                                       // the text's late night and the map's Night
    "2024 [Vision Zero report]", "20mph", "1. ", "2. ", "3. ",              // LADOT's report; the Dutch limit; list numbers
    "puts 74% of severe and fatal injuries on it",                          // SFMTA's own figure
    "more than 60 ft", "from 2021 to now",                                  // the map's rule and its default years
  ];
  let prose = pub.replace(/^---[\s\S]*?\n---\n/, "").replace(/<MapStep state=\{\{[\s\S]*?\}\}>/g, "").replace(/<\/?[A-Za-z][^>]*>/g, "").replace(/\]\([^)]*\)/g, "]");
  for (const t of computed) {
    assert.ok(prose.includes(t), `the story should say "${t}", the figure the map counts`);
    prose = prose.split(t).join(" ");
  }
  prose = prose.split(period).join(" ").replace(/\b[a-z0-9]{4}-[a-z0-9]{4}\b/g, " ");   // the checked years; DataSF ids
  for (const t of elsewhere) prose = prose.split(t).join(" ");
  const left = prose.split("\n").filter((l) => /\d/.test(l));
  assert.deepEqual(left, [], "a number in the story is neither recomputed from map.json nor listed as from elsewhere");
});

test("traffic counts: a counter that passes the override gate colours its block, and one that fails it leaves SFMTA's count", () => {
  // Bryan, 2026-11-21: "Telraam wins" for a working counter (docs/decisions/street-safety.md).
  // The rule and its gate are COUNT_RULE and overrides() in tools/street-safety/hin-cut-through.py; this reads what it wrote into
  // the extract and the map's data, and recomputes the gate from each row.
  const M = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const T = M.traffic, row = (name) => T.p.find((p) => T.names[p[8]] === name);
  const cls = (peak) => (peak < 90 ? 0 : Math.min(6, 1 + Math.floor(Math.log2(peak / 90))));
  assert.equal(T.rule.rule, "telraam");
  assert.equal(M.meta.countRule, T.rule.text);
  assert.equal(T.rule.min_season_days, 20);
  assert.equal(T.rule.max_age_days, undefined, "the gate has no test of how lately the counter counted");
  assert.match(T.rule.text, /April to September median/);
  assert.match(T.rule.text, /20 or more valid days in those months, and its card/);
  assert.match(T.rule.text, /SFMTA's count with its year/);
  assert.doesNotMatch(T.rule.text, /last 12 months|read low|60 days|last read/);
  const seg = JSON.parse(fs.readFileSync(path.join(ROOT, "data/extract/telraam/segments.json"), "utf8"));
  // The read date is the extract's own (its window ends the day it was read), never the day of the build.
  assert.equal(T.rule.read, seg.window[1]);
  const gate = (days) => days >= T.rule.min_season_days;
  // Source 5 is the counter's figure, source 6 SFMTA's with the counter beside it. Every block with both obeys the gate,
  // whichever side of it each counter is on this read. The gate looks at season days only, never at how long ago the
  // counter last counted, so an old counter that passes still colours its block.
  const both = T.p.filter((p) => p[7] === 5 && p[15]), beside = T.p.filter((p) => p[7] === 6);
  assert.ok(both.length + beside.length >= 10, `only ${both.length + beside.length} blocks with both a counter and SFMTA's count`);
  for (const p of both) {
    assert.ok(gate(p[21]), `${T.names[p[8]]}: the counter colours the block with ${p[21]} season days`);
    assert.ok(p[16] >= 2014 && p[16] <= 2023, `${T.names[p[8]]}: SFMTA's count has no year for the card`);
    assert.equal(p[0], cls(p[2]), `${T.names[p[8]]}: coloured by a figure other than the counter's`);
  }
  for (const p of beside) {
    assert.ok(!gate(p[19]), `${T.names[p[8]]}: SFMTA's count colours the block though the counter passes the gate`);
    assert.equal(p[0], cls(p[2]), `${T.names[p[8]]}: coloured by a figure other than SFMTA's`);
    assert.ok(p[12] > 0 && p[13] && p[14] && p[15] > 0, `${T.names[p[8]]}: the card has no counter days, dates or figure`);
  }
  // Known blocks, each with a counter and an SFMTA count that doesn't move (a past count). What the row must say is
  // recomputed from the counter's own record in segments.json with hin-cut-through.py's rule (telraam_fig, overrides),
  // so it holds whatever the window: the counter's April to September median where it has one, else its all-year
  // median; its season days decide the side. A counter that has left the extract or fails its checks leaves SFMTA's
  // count on the block and no counter on the row.
  const segById = new Map(seg.segments.map((s) => [s.id, s]));
  const known = (name, counter, sfmta) => {
    const p = row(name);
    assert.ok(p, `${name}: no traffic row`);
    const s = segById.get(counter);
    if (!s || !s.kept) {
      assert.ok(p[7] !== 5 && p[7] !== 6 && p.length === 11, `${name}: counter ${counter} is out of the extract but on the row`);
      assert.deepEqual([p[2], p[4]], sfmta.slice(0, 2), `${name}: SFMTA's count should colour the block`);
      return p;
    }
    const season = s.daylight_days || 0, fig = s.peak_daylight || s.peak;
    assert.ok(fig >= 5 && fig <= 3000, `${name}: counter ${counter} reads ${fig} cars an hour, not a plausible street`);
    const near = (a, b) => Math.abs(a - b) <= 1;   // the extract's half-hour medians, rounded in Python and here
    if (gate(season)) {
      assert.deepEqual([p[7], p[11], p[21], p[22]], [5, counter, season, s.last], `${name}: should take the counter's figure`);
      assert.ok(near(p[2], fig), `${name}: colours with ${p[2]}, the counter reads ${fig}`);
      assert.deepEqual([p[15], p[16]], sfmta.slice(0, 2), `${name}: SFMTA's count beside it`);
    } else {
      assert.deepEqual([p[7], p[11], p[19], p[20]], [6, counter, season, s.last], `${name}: should keep SFMTA's count`);
      assert.deepEqual([p[2], p[4]], sfmta.slice(0, 2), `${name}: SFMTA's count should colour the block`);
      assert.ok(near(p[15], fig), `${name}: the card shows ${p[15]}, the counter reads ${fig}`);
    }
    if (sfmta[2] !== undefined) assert.equal(p[18], sfmta[2], `${name}: SFMTA's figure is${sfmta[2] ? "" : " not"} the Slow Streets day count`);
    assert.equal(p[0], cls(p[2]), `${name}: coloured by a figure other than the one it shows`);
    return p;
  };
  // Lake St, 2nd to 3rd Ave, beside SFMTA's 2023 Slow Streets day count (139 an hour).
  known("Lake St, 02Nd Ave to 03Rd Ave", "9000004855", [139, 2023, 1]);
  // 9th Ave, California to Clement, and 26th St, Church to Sanchez, beside SFMTA's 2017 counts (88 and 416 an hour).
  known("09Th Ave, California St to Clement St", "9000004990", [88, 2017]);
  known("26Th St, Church St to Sanchez St", "9000006818", [416, 2017]);
  // Lake St, 7th to 8th Ave, beside SFMTA's 2021 pandemic count of 24; 15th Ave, Folsom St and 46th Ave likewise.
  const lake7 = known("Lake St, 07Th Ave to 08Th Ave", "9000005030", [24, 2021]);
  if (lake7[7] === 5) assert.equal(lake7[20], 1, "Lake St at 7th: SFMTA's count beside it is from the pandemic");
  known("15Th Ave, Cabrillo St to Fulton St", "9000009992", [193, 2021]);
  known("Folsom St, Eugenia Ave to Cortland Ave", "9000009961", [70, 2015]);
  const m46 = known("46Th Ave, Santiago St to Taraval St", "9000005311", [198, 2015]);
  // The main-street caveat lists each main-street block with both counts (hin-cut-through.py's summary), with the
  // counter's figure and SFMTA's as the rows carry them; 46th Ave is a main street, so it is listed while it has both.
  for (const [name, tel, sf, yr] of T.telMainSfmta) {
    const p = row(name);
    assert.ok(p && p[10] === 1 && (p[7] === 5 || p[7] === 6), `${name}: listed as a main street with both counts, and isn't`);
    assert.deepEqual([tel, sf, yr], p[7] === 5 ? [p[2], p[15], p[16]] : [p[15], p[2], p[4]], `${name}: the caveat's figures differ from the row's`);
  }
  if (m46[7] === 5 || m46[7] === 6) assert.ok(T.telMainSfmta.some((t) => t[0].startsWith("46Th Ave, Santiago")), "46th Ave is missing from the main-street caveat");
  const mapJs = fs.readFileSync(path.join(ROOT, "site/src/safety-map/map.js"), "utf8");
  assert.match(mapJs, /!ms\.length \? "No Telraam counter on a main street has been checked/);
  assert.match(mapJs, /One Telraam counter on a main street has an SFMTA count to check it against/);
  // Minnesota St, 18th to 19th: counter 9000005517 can't see the street. While it fails telraam-sf.py's checks the
  // block keeps SFMTA's 2023 Slow Streets figure and no counter is on its row.
  const blind = segById.get("9000005517");
  if (blind && !blind.kept) {
    assert.ok(blind.fail.length, "counter 9000005517 is dropped with no failed check named");
    const minn = row("Minnesota St, 18Th St to 19Th St");
    assert.deepEqual([minn[7], minn[4], minn.length], [1, 2023, 11]);
  }
  // The same on every block in the extract: a failed counter is on no row, and a row's figure is the count the gate picks.
  const B = JSON.parse(fs.readFileSync(path.join(ROOT, "data/extract/residential-traffic/blocks.json"), "utf8"));
  assert.equal(B.count_rule.rule, "telraam");
  const failed = new Set(seg.segments.filter((s) => !s.kept).map((s) => s.id));
  assert.ok(failed.size >= 1);
  for (const b of B.blocks) {
    if (!b.telraam) continue;
    assert.ok(!failed.has(b.telraam), `block ${b.cnn} uses failed counter ${b.telraam}`);
    const pass = gate(b.tel_season_days);
    assert.equal(b.tel_overrides, pass ? 1 : 0, `block ${b.cnn}`);
    assert.equal(b.count_choice, pass || b.sfmta_peak === undefined ? "telraam" : "sfmta", `block ${b.cnn}`);
    assert.equal(b.peak, b.count_choice === "telraam" ? b.tel_peak : b.sfmta_peak, `block ${b.cnn}`);
  }
});

test("traffic counts: a counter that sees one side of a two-way road is on no block, and Oak St's one-way counter stays", () => {
  const seg = JSON.parse(fs.readFileSync(path.join(ROOT, "data/extract/telraam/segments.json"), "utf8")).segments;
  const B = JSON.parse(fs.readFileSync(path.join(ROOT, "data/extract/residential-traffic/blocks.json"), "utf8"));
  const S = JSON.parse(fs.readFileSync(path.join(ROOT, "out/hin-cut-through/summary.json"), "utf8")).telraam;
  const one = seg.filter((s) => s.flags.includes("one side")).map((s) => s.id).sort();
  for (const s of seg) if (s.side_share !== undefined) assert.equal(s.flags.includes("one side"), s.side_share < 0.02, s.id);
  // Monterey Blvd at Plymouth (9000010661) counts 0.2% of its cars one way on a divided two-way road, Oak St (9000009987) 0.6% on a one-way street.
  assert.deepEqual(one, ["9000009987", "9000010661"]);
  assert.ok(!B.blocks.some((b) => b.telraam === "9000010661"), "the Monterey Blvd counter is still on a block");
  assert.match(S.skipped.find((k) => k.segment === "9000010661").why, /^one side: 0\.2% .* divided road$/);
  const oak = B.blocks.filter((b) => b.telraam === "9000009987");
  assert.equal(oak.length, 1);
  assert.deepEqual([oak[0].street, oak[0].count_choice, oak[0].kind], ["OAK ST", "telraam", "measured"]);
});

test("traffic counts: the gates fail on made-up bad input (tools/street-safety/telraam-gates-test.py)", () => {
  // 6 season days, 65 season days last valid 80 days ago, and a 0.2% side on a two-way and on a one-way street.
  const r = spawnSync("python3", [script("telraam-gates-test.py")], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  for (const name of ["test_six_season_days_do_not_override", "test_a_counter_last_valid_80_days_ago_with_65_season_days_overrides",
    "test_a_two_tenths_percent_side_fails_on_a_two_way_street_and_passes_on_a_one_way_street"]) {
    assert.ok(r.stdout.includes("ok  " + name), `${name} did not run`);
  }
});

test("the generated title names the filters, fits 60 characters, and is null with none", () => {
  const causes = [{ key: "dui", label: "DUI" }, { key: "red-light", label: "Red light" }];
  const T = (h, used) => S.title(S.fromHash(h), causes, 60, used);
  assert.equal(T(""), null);
  assert.equal(T("#at=-122.41925,37.77930,16.00&chart=by-cause"), null);
  assert.equal(T("#cause=dui&time=night"), "DUI crashes at night");
  assert.equal(T("#cause=red-light"), "Red light crashes");
  assert.equal(T("#view=crime&days=weekend&time=night&hood=Bayview%20Hunters%20Point"), "Crime on weekend nights in Bayview Hunters Point");
  assert.equal(T("#user=Walking&severity=killed"), "People walking killed");
  const used = {};
  const long = T("#severity=killed&cause=dui&days=weekend&time=night&hood=Bayview%20Hunters%20Point&on=on", used);
  assert.ok(long.length <= 60, long);
  assert.equal(used.net, false);
  assert.equal(used.cause, true);
});

test("the on and off network chart is an injuries chart and survives the address", () => {
  assert.ok(S.CHARTS.injuries.includes("by-hin"));
  assert.equal(S.toHash(S.fromHash("#chart=by-hin")), "#chart=by-hin");
  assert.equal(S.toHash(S.fromHash("#color=hin&chart=by-hin")), "#color=hin&chart=by-hin");
});

test("pick= keeps the cause chart at its top level with one cause picked", () => {
  const s = S.fromHash("#pick=red-light&time=night");
  assert.deepEqual(plain(s.filter.cause), ["red-light"]);
  assert.deepEqual(plain(s.chart), { id: "by-cause", top: true });
  assert.equal(S.toHash(s), "#time=night&pick=red-light");
  // Clearing the cause drops the pick; a subcause can't be picked at the top level.
  assert.deepEqual(plain(S.merge(s, { filter: { cause: [] } }).chart), { id: "by-cause" });
  assert.equal(S.normalize({ filter: { cause: ["red-light/21453(a)"] }, chart: { id: "by-cause", top: true } }).chart.top, undefined);
});

// ---- The crash cards' diagrams (site/src/safety-map/crash-cards.js): where each party is drawn against the drawn roads.
const cc = {};
vm.createContext(cc);
vm.runInContext(fs.readFileSync(path.join(ROOT, "site/src/safety-map/crash-cards.js"), "utf8") + "\nthis.CrashCards = CrashCards;", cc);
const segDist = (p, a, b) => {
  const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
};
// What is wrong with one drawing, from CrashCards.layout: a vehicle's glyph or any point of its arrow off the drawn
// road surface (further than the road's half width from every centreline) or outside the frame, and a straight
// arrow on a leg whose first few px run more than 20 degrees off every road they are on.
function drawingFaults(L) {
  const out = [], segs = (L.roads || []).flatMap((r) => r[1].slice(1).map((b, i) => [r[1][i], b]));
  const off = (p) => segs.length > 0 && !segs.some((s) => segDist(p, s[0], s[1]) <= L.R + 1);
  const outside = (p, m) => p[0] < L.frame[0] + m || p[0] > L.frame[2] - m || p[1] < L.frame[1] + m || p[1] > L.frame[3] - m;
  for (const it of L.items) {
    if (outside(it.gp, 6)) out.push(`party ${it.n}: glyph outside the frame`);
    if (it.kind === "walk") continue;   // walkers stand beside the road
    if (off(it.gp)) out.push(`party ${it.n}: glyph off the road`);
    if (it.pts.some(off)) out.push(`party ${it.n}: arrow off the road`);
    if (it.pts.some((p) => outside(p, 0))) out.push(`party ${it.n}: arrow outside the frame`);
    if ((it.kind === "a" || it.kind === "e") && it.m !== "x" && it.pts.length > 1) {
      const a = it.pts[0], b = it.pts[1], dir = Math.atan2(b[1] - a[1], b[0] - a[0]);
      const along = segs.some((s) => {
        if (segDist(a, s[0], s[1]) > L.R && segDist(b, s[0], s[1]) > L.R) return false;
        const d = Math.abs(((dir - Math.atan2(s[1][1] - s[0][1], s[1][0] - s[0][0])) * 180 / Math.PI) % 180);
        return Math.min(d, 180 - d) <= 20;
      });
      if (!along) out.push(`party ${it.n}: arrow does not run along the road`);
    }
  }
  return out;
}

// Cards the checks below know fail, from the run over every crash since 2005 (2026-11-20): listed, counted and printed
// rather than silently passed, so a new failure still stops the build. Arrows that leave the road on a bend or a short
// leg or a U-turn, and number tags that can't all sit nearest their own icon in crashes of four to sixteen parties.
// The 2005-2012 ids are parties placed on their recorded street once "Not Collected" stopped reading as a street name.
const KNOWN_DRAWING = new Set(["130045350", "140093054", "220084589", "220184963", "250233223", "250233336",
  "2116180", "2340093", "3432039", "3433893", "3474397", "3893085", "4260672", "5274435", "5303641", "6059107", "6104464",
  "6135372", "6221529"]);
const KNOWN_TAGS = new Set(["130659428", "140193002", "140249172", "140791032", "140844158", "161021963", "170201700", "170701700",
  "180153947", "200062066", "210410176", "220172827", "230791451", "230807343", "260402349",
  "2022710", "2172013", "2818033", "3603483", "3727076", "3748450", "3992622", "4490582", "4789160", "4892430", "5114026", "5427489"]);

test("the diagram check catches a vehicle off the road and an arrow across it", () => {
  const road = [["A St", [[-120, 0], [120, 0]]]], frame = [-130, -98, 130, 98];
  assert.deepEqual(drawingFaults({ R: 13, frame, roads: road, items: [{ n: 1, kind: "a", m: "s", gp: [-50, 6], pts: [[-38, 6], [12, 6]] }] }), []);
  assert.deepEqual(drawingFaults({ R: 13, frame, roads: road, items: [{ n: 1, kind: "a", m: "s", gp: [-50, 20], pts: [[-38, 6], [12, 6]] }] }), ["party 1: glyph off the road"]);
  assert.deepEqual(drawingFaults({ R: 13, frame, roads: road, items: [{ n: 1, kind: "a", m: "s", gp: [-50, 6], pts: [[-38, 12], [-20, -6], [12, -30]] }] }),
    ["party 1: arrow off the road", "party 1: arrow does not run along the road"]);
});

test("no crash card draws a vehicle off the road, out of the frame, or across its street", () => {
  const bad = [], known = [];
  let drawn = 0;
  for (const id of Object.keys(CARDS).sort()) {
    const L = cc.CrashCards.layout(CARDS[id].g);
    drawn += L.items.length;
    for (const f of drawingFaults(L)) (KNOWN_DRAWING.has(id) ? known : bad).push(`${id} ${f}`);
  }
  assert.ok(drawn > 100000, `only ${drawn} parties drawn`);
  console.log(`  ${known.length} known drawing faults in ${new Set(known.map((k) => k.split(" ")[0])).size} cards (KNOWN_DRAWING)`);
  assert.deepEqual(bad, [], `${bad.length} faults`);
});

test("every number tag on a crash card sits nearer its own party's icon than any other", () => {
  const box = (p, b) => Math.hypot(Math.max(b[0] - p[0], 0, p[0] - b[2]), Math.max(b[1] - p[1], 0, p[1] - b[3]));
  const bad = [], stacked = new Set(), knownTags = [];
  let tags = 0;
  for (const id of Object.keys(CARDS).sort()) {
    const L = cc.CrashCards.layout(CARDS[id].g);
    for (const it of L.items) {
      assert.ok(it.tag, `${id} party ${it.n}: no tag`);
      tags++;
      // Two icons drawn on the same spot (a queue closed up at the frame's edge) cannot be told apart by any tag; skipped
      // and counted.
      const same = L.items.filter((o) => o !== it && Math.hypot(o.gp[0] - it.gp[0], o.gp[1] - it.gp[1]) <= 0.5);
      if (same.length) stacked.add(id);
      const own = box(it.gp, it.tag), near = L.items.filter((o) => o !== it && Math.hypot(o.gp[0] - it.gp[0], o.gp[1] - it.gp[1]) > 0.5 && box(o.gp, it.tag) <= own);
      if (near.length) (KNOWN_TAGS.has(id) ? knownTags : bad).push(`${id} party ${it.n}: tag as near party ${near.map((o) => o.n).join(", ")}`);
    }
  }
  assert.ok(tags > 100000, `only ${tags} tags`);
  assert.deepEqual(bad, [], `${bad.length} tags nearer another icon`);
  console.log(`  ${knownTags.length} known tag faults in ${KNOWN_TAGS.size} cards (KNOWN_TAGS)`);
  console.log(`  ${stacked.size} of ${Object.keys(CARDS).length} cards draw two icons on one spot (skipped): ${[...stacked].sort().slice(0, 12).join(", ")}${stacked.size > 12 ? ", ..." : ""}`);
});

test("a party whose recorded direction fits no street is drawn below the picture, not off the road", () => {
  // One street running east and west; the record says north. The compass placement would sit south of the street.
  const g = { x: 1, ax: "h", lv: "", lh: "", geo: { r: [["A St", [[-200, 0], [200, 0]]]], l: [[0, 0, 90, "A St"], [0, 0, 270, "A St"]], k: [[0, [[0, 0], [200, 0]]], [0, [[0, 0], [-200, 0]]]] },
    p: [{ n: 1, v: "car", d: "N", m: "s", h: 0, pk: 0, f: 0, fb: 1 }, { n: 2, v: "car", d: "E", m: "s", h: 0, pk: 0, f: 0, a: [0, 0, 270, 1] }] };
  const L = cc.CrashCards.layout(g);
  assert.deepEqual(plain(L.below), [{ n: 1, star: true }]);
  assert.deepEqual(plain(L.items.map((it) => it.n)), [2]);
  assert.deepEqual(drawingFaults(L), []);
  assert.ok(L.items[0].gp[1] > 0, "an eastbound driver is south of the centreline, on the right");
});

test("the crime view takes years from 2018, kinds of crime, and the day and time", () => {
  // Bryan, 2026-11-19: "Was expecting a year selector, time of day selector, kind of crime selector".
  for (const k of ["area", "days", "time", "crimeKinds", "crimeYears"]) assert.ok(S.FILTERS.crime.includes(k), k);
  assert.ok(!S.FILTERS.injuries.includes("crimeKinds") && !S.FILTERS.injuries.includes("crimeYears"));
  assert.equal(S.CRIME_YEARS[0], 2018);
  assert.equal(S.CRIME_YEARS.at(-1), S.NEWEST_YEAR);
  assert.deepEqual(plain(S.CRIME_KINDS.map((k) => k[1])), ["Violence and weapons", "Theft, burglary and fraud", "Vandalism and arson", "Drugs", "Other"]);
  // Every year is no filter, and the default; the range clamps to 2018 and sorts.
  assert.equal(S.DEFAULTS.filter.crimeYears, null);
  assert.equal(S.normalize({ filter: { crimeYears: [2018, S.NEWEST_YEAR] } }).filter.crimeYears, null);
  assert.deepEqual(plain(S.normalize({ filter: { crimeYears: [2023, 2010] } }).filter.crimeYears), [2018, 2023]);
  // Every kind is no kind; unknown keys drop; order is CRIME_KINDS'.
  assert.deepEqual(plain(S.normalize({ filter: { crimeKinds: S.CRIME_KINDS.map((k) => k[0]) } }).filter.crimeKinds), []);
  assert.deepEqual(plain(S.normalize({ filter: { crimeKinds: ["drugs", "nope", "violence"] } }).filter.crimeKinds), ["violence", "drugs"]);
  // The address round-trips, and the crime filters don't touch the injuries' years.
  const h = "#view=crime&days=weekend&time=night&kinds=violence,drugs&cyears=2020-2022";
  assert.equal(S.toHash(S.fromHash(h)), h);
  assert.deepEqual(plain(S.fromHash(h).filter.years), [S.INLINE_FROM, S.NEWEST_YEAR]);
  assert.equal(S.toHash(S.fromHash("#view=crime&cyears=2024")), "#view=crime&cyears=2024-2024");
  // One kind names the tab title.
  assert.equal(S.title(S.fromHash("#view=crime&kinds=drugs&time=night"), [], 60), "Drugs reports at night");
  assert.ok(S.CHARTS.crime.includes("crime-by-year"));
});

test("a Supervisor district is an area: in the address, the people filter and the title", () => {
  // Bryan, 2026-11-19: "Can you also offer all the districts here as options?"
  const s = S.fromHash("#district=3&user=Walking");
  assert.deepEqual(plain(s.filter.area), { district: 3 });
  assert.equal(S.toHash(s), "#user=Walking&district=3");
  for (const bad of ["#district=12", "#district=0", "#district=2.5", "#district=x"]) assert.equal(S.fromHash(bad).filter.area, null, bad);
  const people = [{ u: "Walking", sv: 1, hy: 0, at: 0, d: "2023-01-01", wd: 0, h: 9, dist: 3 }, { u: "Walking", sv: 1, hy: 0, at: 0, d: "2023-01-01", wd: 0, h: 9, dist: 5 }];
  assert.deepEqual(people.map((p) => S.personShown(s, p)), [true, false]);
  assert.deepEqual(plain(S.peopleFilter(s)).slice(-1)[0], ["==", ["get", "dist"], 3]);
  const geom = { type: "MultiPolygon", coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]] };
  assert.deepEqual(plain(S.areaGeom(s, [], [{ district: 3, geom }])), geom);
  assert.equal(S.title(s, [], 60), "People walking in District 3");
});

test("the per-state test keeps exactly the people the old per-person rule kept", () => {
  // The rule as it stood before shownTest, everything worked out per person; areas other than a neighborhood aside.
  const oldShown = (s, p) => {
    const f = S.normalize(s).filter, y = S.yearList(f.years), w = S.weekdays(f.days);
    if (f.user.length && f.user.indexOf(p.u) < 0) return false;
    if (f.cause.length && !f.cause.some((e) => S.causeIn(e, p))) return false;
    if (y && y.indexOf(String(p.d).slice(0, 4)) < 0) return false;
    if (p.sv > S.sevLevel(f.severity)) return false;
    if (f.hinGroup.length && f.hinGroup.indexOf(p[S.groupKey(s)]) < 0) return false;
    if (f.hin === "on" && !(p.hy & 4)) return false;
    if (f.hin === "off" && (p.hy & 4)) return false;
    if (f.at === "intersection" && p.at !== 1) return false;
    if (f.at === "midblock" && p.at !== 0) return false;
    const t = S.timesOf(f.time);
    if (t && (p.h == null || p.h < 0 || !t.some((x) => S.hourIn(x, p.h)))) return false;
    if (w && w.indexOf(p.wd) < 0) return false;
    if (f.area && f.area.hood && p.hood !== f.area.hood) return false;
    if (f.area && f.area.district && p.dist !== f.area.district) return false;
    return true;
  };
  const ppl = [];
  const U = S.USERS, C = ["red-light", "dui"];
  for (let i = 0; i < 400; i++) ppl.push({ u: U[i % U.length], sv: i % 4, hy: (i * 7) % 8, at: i % 3 - 1 < 0 ? 0 : i % 2, d: `${2019 + (i % 8)}-0${1 + (i % 9)}-1${i % 10}`, wd: i % 7, h: i % 25 - 1,
    ck: C[i % 2], sk: "x", hood: i % 3 ? "Mission" : "Bayview", dist: 1 + (i % 11), "hg:2020-2024": i % 5, "hg:2022-2024": i % 4 });
  for (const f of [{}, { severity: "pain" }, { years: [2021, 2023], user: ["Walking", "Biking"] }, { cause: ["dui"], time: ["night", "am"], days: ["weekend"] },
    { hin: "on", at: "intersection", hinGroup: [1, 2] }, { area: { hood: "Mission" }, severity: "visible" }, { area: { district: 4 } }, { years: null }]) {
    const t = S.shownTest({ filter: f });
    for (const p of ppl) assert.equal(t(p), oldShown({ filter: f }, p), JSON.stringify(f));
  }
});

test("unordered charts sort largest first with the leftovers last; ordered charts keep their order", () => {
  // Bryan, 2026-11-19: "Items should be sorted by the data they show ... (except Other)".
  const rows = [{ key: "dui", label: "DUI", value: 3 }, { key: "other", label: "Other", value: 40 }, { key: "red-light", label: "Red light", value: 9 },
    { key: "unknown-or-not-stated", label: "Unknown or not stated", value: 50 }, { key: "dooring", label: "Dooring", value: 9 }];
  assert.deepEqual(S.sortRows("by-cause", rows).map((r) => r.key), ["red-light", "dooring", "dui", "other", "unknown-or-not-stated"]);
  assert.deepEqual(S.sortRows("by-cause", [{ key: "x/22350", label: "a", value: 1 }, { key: "x/other", label: "Other", value: 5 }, { key: "x/22107", label: "b", value: 4 }]).map((r) => r.key), ["x/22107", "x/22350", "x/other"]);
  assert.deepEqual(S.sortRows("by-user", [{ key: "Walking", value: 2 }, { key: "Other", label: "Other", value: 9 }, { key: "Biking", value: 5 }]).map((r) => r.key), ["Biking", "Walking", "Other"]);
  assert.deepEqual(S.sortRows("by-hood", [{ key: "", label: "No neighborhood", value: 99 }, { key: "Mission", value: 4 }, { key: "SoMa", value: 7 }]).map((r) => r.key), ["SoMa", "Mission", ""]);
  assert.deepEqual(S.sortRows("by-district", [{ key: "1", value: 2 }, { key: "6", value: 8 }]).map((r) => r.key), ["6", "1"]);
  for (const id of ["by-year", "by-time", "by-day", "by-severity", "by-hin", "by-hin-group"]) {
    const ordered = [{ key: "a", value: 1 }, { key: "b", value: 9 }, { key: "", value: 5 }];
    assert.deepEqual(S.sortRows(id, ordered).map((r) => r.key), ["a", "b", ""], id);
  }
});

test("the through-traffic distance slider: half a mile by default, a quarter, three quarters and a mile in the address", () => {
  // Bryan, 2026-11-20: the slider covers a quarter to a mile, and "Default to half mile".
  assert.equal(S.DEFAULTS.near, "half");
  assert.deepEqual(plain(S.NEARS.map((x) => x[0])), ["quarter", "half", "3q", "mile"]);
  assert.equal(S.toHash(S.fromHash("#view=through&near=mile")), "#view=through&near=mile");
  assert.equal(S.toHash(S.fromHash("#view=through&near=quarter&time=am")), "#view=through&near=quarter&time=am");
  // The default leaves the address bare, so an old link with no distance reads half a mile, and an unknown distance
  // falls back to it.
  assert.equal(S.toHash(S.fromHash("#view=through&near=half")), "#view=through");
  assert.equal(S.fromHash("#view=through").near, "half");
  assert.equal(S.fromHash("#view=through&near=2mi").near, "half");
  // A new distance recolours the same layers: no fade, but the plan says the parameters moved.
  const p = S.plan(S.fromHash("#view=through"), S.fromHash("#view=through&near=mile"));
  assert.deepEqual(plain(p.fadeIn), []);
  assert.deepEqual(plain(p.fadeOut), []);
  assert.equal(p.params, true);
});

test("the where-from view: its own layers, an area outlined but nothing dimmed, and the three-way toggle", () => {
  assert.ok(S.VIEWS.includes("from"));
  assert.equal(S.DEFAULTS.ends, "from");
  assert.deepEqual(plain(S.ENDS.map((x) => x[0])), ["from", "to", "both"]);
  assert.deepEqual(plain(S.FILTERS.from), ["area"]);
  assert.deepEqual(plain(S.CHARTS.from), ["from-groups", "from-time"]);
  const s = S.fromHash("#view=from&ends=to&hood=Bayview%20Hunters%20Point");
  assert.equal(s.view, "from");
  assert.equal(s.ends, "to");
  assert.equal(S.toHash(s), "#view=from&ends=to&hood=Bayview%20Hunters%20Point");
  assert.equal(S.toHash(S.fromHash("#view=from&ends=from")), "#view=from");
  assert.equal(S.toHash(S.fromHash("#view=from&ends=both")), "#view=from&ends=both");
  assert.equal(S.fromHash("#view=from&ends=sideways").ends, "from");
  const L = S.layersFor(s);
  for (const l of ["from-regions", "from-own", "from-bubbles", "from-labels", "area-edge"]) assert.ok(L.includes(l), l);
  assert.ok(!L.includes("area-mask"), "the Bay Area view doesn't dim outside the area");
  assert.ok(S.layersFor(S.fromHash("#view=through&hood=Bayview%20Hunters%20Point")).includes("area-mask"));
  // Each toggle position is a parameter change, not a layer change.
  const p = S.plan(s, S.merge(s, { ends: "from" }));
  assert.equal(p.params, true);
  assert.deepEqual(plain(p.fadeIn), []);
  // A drawn area survives the address on this view too.
  const d = S.fromHash("#view=from&ends=from&poly=-122.39,37.73;-122.38,37.73;-122.38,37.74");
  assert.equal(S.toHash(d), "#view=from&poly=-122.39000,37.73000;-122.38000,37.73000;-122.38000,37.74000");
  // An open bubble card is in the address, so a link reopens it; it needs the view and an area.
  const c = S.fromHash("#view=from&hood=Mission&card=Peninsula%20North");
  assert.equal(c.card, "Peninsula North");
  assert.ok(S.toHash(c).includes("card=Peninsula%20North"));
  assert.equal(S.fromHash(S.toHash(c)).card, "Peninsula North");
  assert.equal(S.fromHash("#view=from&card=Peninsula%20North").card, null);
  assert.equal(S.fromHash("#view=through&hood=Mission&card=Peninsula%20North").card, null);
  assert.ok(S.layersFor(c).includes("from-hl"));
  assert.equal(S.title(s, [], 60), "Where traffic comes from in Bayview Hunters Point");
});

test("the where-from view's passing-through toggle is in the address and is a parameter change", () => {
  assert.equal(S.DEFAULTS.thru, false);
  const s = S.fromHash("#view=from&ends=to&thru=1&hood=Sunset%2FParkside");
  assert.equal(s.thru, true);
  assert.equal(S.toHash(s), "#view=from&ends=to&thru=1&hood=Sunset%2FParkside");
  assert.equal(S.toHash(S.fromHash("#view=from&hood=Mission")), "#view=from&hood=Mission");
  assert.equal(S.fromHash("#view=from&thru=yes").thru, false);
  assert.equal(S.normalize({ thru: "1" }).thru, false);
  const p = S.plan(s, S.merge(s, { thru: false }));
  assert.equal(p.params, true);
  assert.deepEqual(plain(p.fadeIn), []);
  assert.deepEqual(plain(p.fadeOut), []);
});

test("a camera zoomed out far enough for the Bay Area survives normalising", () => {
  assert.equal(S.normalize({ camera: { center: [-122.2, 37.7], zoom: 8.4 } }).camera.zoom, 8.4);
  // A phone needs about zoom 6.5 for the nine counties; the state has no floor of its own above the map's (Bryan,
  // 2026-11-20: "Allow more zoom out on iPhone. I can't zoom out to the whole Bay Area").
  assert.equal(S.normalize({ camera: { center: [-122.2, 37.7], zoom: 5.25 } }).camera.zoom, 5.25);
  assert.equal(S.toHash(S.fromHash("#view=from&at=-122.20000,37.70000,5.25")), "#view=from&at=-122.20000,37.70000,5.25");
});

// The where-from view's files (tools/street-safety/where-traffic-comes-from.py), checked as the page reads them.
const WF_DIR = path.join(ROOT, "site/data/street-safety/where-from");
const wfRead = (f) => JSON.parse(fs.readFileSync(path.join(WF_DIR, f), "utf8"));
const wfSlug = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const sum = (a) => a.reduce((x, y) => x + y, 0);

test("where-from units: 41 neighborhoods and six regions that take each superdistrict outside SF once", () => {
  const U = wfRead("units.json");
  assert.equal(U.groups.length, 47);
  assert.equal(U.points.length, 47);
  assert.equal(U.district_points.length, 11);
  assert.deepEqual(U.regions.map((r) => r.name), U.groups.slice(41));
  assert.deepEqual(U.regions.flatMap((r) => r.superdistricts).sort((a, b) => a - b), Array.from({ length: 30 }, (_, i) => i + 5));
  assert.ok(U.regions.length >= 5 && U.regions.length <= 7);
  assert.equal(U.outlines.features.length, U.regions.length);
  assert.deepEqual(U.bins.map((b) => b[0]), plain(S.TIMES.map((t) => t[0])), "the times of day are the map's own");
  // Every bubble's point is inside the nine counties' bounds.
  const [w, s, e, n] = U.bounds;
  for (const p of U.points.concat(U.district_points)) assert.ok(p[0] >= w && p[0] <= e && p[1] >= s && p[1] <= n, String(p));
});

test("where-from bubbles add to the totals the zone-shaded view showed, per direction, for every neighborhood", () => {
  // The bubbles outside the area are g.fa + g.ft (Coming from), g.td + g.tt (Going to) and all four (Both, where a
  // car passing through sits at both of its ends). PR #534's view showed arriving + through, leaving + through and
  // arriving + leaving + through. Each group is rounded on its own, so the sum can be off by half a car a group.
  const old = JSON.parse(fs.readFileSync(path.join(ROOT, "site/tests/fixtures/where-from-totals-pr534.json"), "utf8")).totals;
  const U = wfRead("units.json"), tol = U.groups.length / 2;
  assert.equal(Object.keys(old).length, 41);
  for (const [name, [arr, dep, thr, inside]] of Object.entries(old)) {
    const A = wfRead(`area-${wfSlug(name)}.json`), g = A.g;
    // The select run writes each group's cars to a tenth, and the groups outside SF changed from counties to
    // superdistricts, so a total summed from them can move by a car.
    [[A.tot.arr, arr], [A.tot.dep, dep], [A.tot.thr, thr], [A.tot.inside, inside]].forEach(([now, was]) => assert.ok(Math.abs(now - was) <= 2, `${name}: ${now} against ${was}`));
    assert.ok(Math.abs(sum(g.fa) + sum(g.ft) - (arr + thr)) <= tol + 4, name + ": coming from");
    assert.ok(Math.abs(sum(g.td) + sum(g.tt) - (dep + thr)) <= tol + 4, name + ": going to");
    assert.ok(Math.abs(sum(g.fa) + sum(g.ft) + sum(g.td) + sum(g.tt) - (arr + dep + 2 * thr)) <= 2 * tol + 8, name + ": both, a through car at both ends");
    const own = U.groups.indexOf(name);
    assert.equal(g.fa[own] + g.ft[own] + g.td[own] + g.tt[own], 0, name + ": its own cars are the ring, not a bubble");
  }
});

test("where-from through cars sum the same by where they start and where they end, for every area", () => {
  // The passing-through bubbles are g.ft (Coming from) and g.tt (Going to). Each group is rounded on its own, so a
  // sum can be off by half a car a group. A through car has neither end in the area, so its own group holds none.
  const U = wfRead("units.json"), tol = U.groups.length / 2 + 1;
  const names = U.groups.slice(0, 41).concat(Array.from({ length: 11 }, (_, i) => `District ${i + 1}`));
  for (const name of names) {
    const A = wfRead(`area-${wfSlug(name)}.json`), g = A.g;
    assert.ok(Math.abs(sum(g.ft) - A.tot.thr) <= tol, `${name}: through cars by start ${sum(g.ft)} against ${A.tot.thr}`);
    assert.ok(Math.abs(sum(g.tt) - A.tot.thr) <= tol, `${name}: through cars by end ${sum(g.tt)} against ${A.tot.thr}`);
    assert.ok(Math.abs(sum(A.bins.thr) - A.tot.thr) <= U.bins.length, `${name}: through cars by time of day`);
    const own = U.groups.indexOf(name);
    if (own >= 0) assert.equal(g.ft[own] + g.tt[own], 0, name + ": no through car starts or ends in the area");
  }
});

test("where-from times of day add to the day, per direction, for every neighborhood and Supervisor district", () => {
  const U = wfRead("units.json"), names = U.groups.slice(0, 41).concat(Array.from({ length: 11 }, (_, i) => `District ${i + 1}`));
  for (const name of names) {
    const A = wfRead(`area-${wfSlug(name)}.json`), b = A.bins, t = A.tot;
    for (const k of ["arr", "dep", "thr", "inside"]) {
      assert.equal(b[k].length, U.bins.length, name);
      assert.ok(Math.abs(sum(b[k]) - t[k]) <= U.bins.length, `${name}: ${k} by time of day ${sum(b[k])} against ${t[k]}`);
    }
    // Coming in (arriving + through) and going out (leaving + through), the chart's two series.
    assert.ok(Math.abs(sum(b.arr) + sum(b.thr) - (t.arr + t.thr)) <= 2 * U.bins.length, name + ": coming in");
    assert.ok(Math.abs(sum(b.dep) + sum(b.thr) - (t.dep + t.thr)) <= 2 * U.bins.length, name + ": going out");
  }
});

test("where-from travel modes: a file for every neighborhood and district, directions adding up, figures in range", () => {
  // tools/street-safety/where-traffic-modes.py. A row is [unit, car, transit on foot, transit by car, bike, walk, car min, car
  // miles, transit min, % no transit path, drive-to-transit min, bike min, bike miles, % no bike path].
  const U = wfRead("units.json"), names = U.groups.slice(0, 41).concat(Array.from({ length: 11 }, (_, i) => `District ${i + 1}`));
  const trips = (r) => sum(r.slice(1, 6));
  let east = 0;
  for (const name of names) {
    const M = wfRead(`modes-${wfSlug(name)}.json`), own = U.groups.indexOf(name);
    assert.equal(M.own[0], -1, name);
    assert.ok(trips(M.own) > 0, name + ": trips within it");
    const by = (k) => new Map(M[k].map((r) => [r[0], r]));
    const f = by("from"), t = by("to"), b = by("both");
    assert.ok(b.size >= 40, name + ": nearly every unit has trips");
    assert.ok(!b.has(own), name + ": its own trips are `own`, not a unit");
    for (const [u, r] of b) {
      assert.equal(r.length, 17, name);
      assert.ok(u >= 0 && u < U.groups.length, name);
      // Both is the two directions' trips, each mode rounded on its own.
      for (let m = 1; m <= 5; m++) assert.ok(Math.abs(r[m] - ((f.get(u) || [])[m] || 0) - ((t.get(u) || [])[m] || 0)) <= 1, `${name} and ${U.groups[u]}: mode ${m}`);
      for (const k of [9, 13]) assert.ok(r[k] === null || (r[k] >= 0 && r[k] <= 100), `${name}: a share of trips`);
      if (r[6] !== null) assert.ok(r[6] > 1 && r[6] < 240 && r[7] > 0.1 && r[7] < 150, `${name} and ${U.groups[u]}: car ${r[6]} min, ${r[7]} miles`);
      // The skim's bike is 12 mph.
      if (r[11] !== null) assert.ok(Math.abs(r[11] - r[12] * 5) <= 0.5, `${name} and ${U.groups[u]}: bike ${r[11]} min for ${r[12]} miles`);
      // Only a trip toward the area from a region has a drive-to-transit time.
      assert.equal(r[10], null, name);
      // No bike path across the Bay Bridge: the East Bay's inner region has none under 75 miles for most trips (the
      // southern neighborhoods are within 75 miles of some of it the long way round).
      if (U.groups[u] === "East Bay Inner" && r[13] !== null) { assert.ok(r[13] >= 75, `${name}: ${r[13]}% of East Bay Inner trips with no bike path`); east++; }
      // The Golden Gate Bridge takes bikes both ways, so Marin isn't cut off in either direction.
      if (U.groups[u] === "Marin and Sonoma" && name !== "Treasure Island") for (const d of [f.get(u), t.get(u)]) if (d && d[13] !== null && d[1] >= 500) assert.ok(d[13] < 50, `${name}: ${d[13]}% of Marin trips with no bike path`);
    }
    for (const [u, r] of f) assert.ok(u >= 41 || r[10] === null, name + ": drive-to-transit time for regions only");
  }
  assert.ok(east >= 50, "the Bay Bridge check ran for every area");
  // The card's floor for splitting a pair's trips is the one the About page states.
  const src = fs.readFileSync(path.join(ROOT, "site/src/safety-map/map.js"), "utf8"), about = fs.readFileSync(path.join(ROOT, "site/src/pages/transportation-street-safety.mjs"), "utf8");
  assert.match(src, /var WF_MODE_MIN = 60;/);
  assert.match(about, /under 60 trips a weekday the card doesn't split them, and under 60 car trips it gives no times/);
});

test("where-from eligibility line: two tests per row, never more car trips than the row's, Sunset/Parkside's worked example", () => {
  // Bryan, 2026-11-20: "Eligibility line". A row's [14] and [15] are [car, transit, bike, walk]
  // trips on the pairs that pass the transit test (walk to the stop, at most 1.5 x the drive, each trip timed in the
  // MTC period it leaves) and the bike test (3 miles or less); [16] is the car trips tested, the row's car trips.
  // Pairs within one zone are tested in every row, `own` included.
  const U = wfRead("units.json"), names = U.groups.slice(0, 41).concat(Array.from({ length: 11 }, (_, i) => `District ${i + 1}`));
  let rows = 0, someTransit = 0;
  for (const name of names) {
    const M = wfRead(`modes-${wfSlug(name)}.json`);
    for (const r of [M.own, ...M.from, ...M.to, ...M.both]) {
      const tag = `${name}, unit ${r[0]}`;
      for (const t of [r[14], r[15]]) {
        assert.equal(t.length, 4, tag);
        assert.ok(t.every((x) => Number.isInteger(x) && x >= 0), tag + ": whole, non-negative trips");
        assert.ok(t[0] <= r[16], `${tag}: ${t[0]} eligible car trips against ${r[16]} tested`);
        // Each mode's trips on the passing pairs are a part of the row's trips by that mode.
        assert.ok(t[1] <= r[2] + r[3] + 1 && t[2] <= r[4] + 1 && t[3] <= r[5] + 1, tag + ": a part of the row's trips");
      }
      // The quality check: never more car trips tested than the row's car trips.
      assert.ok(r[16] <= r[1] + 1, `${tag}: ${r[16]} tested against ${r[1]} car trips`);
      assert.ok(Math.abs(r[16] - r[1]) <= 1, `${tag}: the tests cover all the row's car trips, as the mode bar counts them`);
      if (r[14][0] > 0) someTransit++;
      rows++;
    }
  }
  assert.ok(rows > 52 * 100 && someTransit > 100, `${rows} rows, ${someTransit} with car trips passing the transit test`);
  // Sunset/Parkside, every trip with one end outside, both directions, timed in each trip's own period. The bike test's
  // figures are the worked example posted on the thread; the transit test's are the pipeline review's recomputation
  // (1,990 with the AM skim for every trip).
  const sp = wfRead("modes-sunset-parkside.json").both, car = sum(sp.map((r) => r[1]));
  const at = (k) => [0, 1, 2, 3].map((j) => sum(sp.map((r) => r[k][j])));
  const share = (e, j) => Math.round(100 * e[j] / sum(e));
  const tr = at(14), bk = at(15);
  assert.ok(Math.abs(tr[0] - 1662) <= sp.length, `transit test ${tr[0]} car trips`);
  assert.equal((100 * tr[0] / car).toFixed(1), "1.0");
  assert.deepEqual([share(tr, 1), share(tr, 2), share(tr, 0)], [36, 12, 46]);
  assert.ok(Math.abs(bk[0] - 33554) <= sp.length, `bike test ${bk[0]} car trips`);
  assert.equal((100 * bk[0] / car).toFixed(1), "19.4");
  assert.deepEqual([share(bk, 1), share(bk, 2), share(bk, 0)], [14, 5, 67]);
  // The review's other figures: the Mission's transit test, and District 6 with East Bay Inner, where timing each trip
  // in its own period moves the most between From and To.
  const mi = wfRead("modes-mission.json").both;
  assert.ok(Math.abs(sum(mi.map((r) => r[14][0])) - 7828) <= mi.length, "Mission transit test");
  const d6 = wfRead("modes-district-6.json"), ebi = U.groups.indexOf("East Bay Inner");
  const d6r = (k) => d6[k].filter((r) => r[0] === ebi)[0][14][0];
  assert.ok(Math.abs(d6r("from") - 11148) <= 1 && Math.abs(d6r("to") - 460) <= 1, `District 6 and East Bay Inner: from ${d6r("from")}, to ${d6r("to")}`);
  // The card's words, and the About page's statement of both tests and their limits.
  const src = fs.readFileSync(path.join(ROOT, "site/src/safety-map/map.js"), "utf8"), about = fs.readFileSync(path.join(ROOT, "site/src/pages/transportation-street-safety.mjs"), "utf8");
  assert.match(src, /Trips by car a weekday that pass a simple test\. Not a forecast\./);
  assert.match(src, /Transit with a walk to the stop, at most 1\.5 times the drive/);
  assert.match(src, /Bike ride of 3 miles or less/);
  assert.match(src, /of trips by car here\./);
  assert.match(src, /var WF_ELIG_MIN = 20;/);
  assert.match(about, /It isn't a forecast of how many people would switch\./);
  assert.match(about, /The test looks only at minutes, so a trip with two transfers passes on the same minutes as one with none\./);
  assert.match(about, /The bike test is distance only\. It doesn't measure hills or how comfortable the route is\./);
  assert.match(about, /timed in the period it leaves/);
  // The script's thresholds are the card's words.
  const py = fs.readFileSync(path.join(ROOT, "tools/street-safety/where-traffic-modes.py"), "utf8");
  assert.match(py, /^TRN_RATIO = 1\.5$/m);
  assert.match(py, /^BIKE_MI = 3\.0$/m);
});

test("the other-party filter: its options, the address, the people it keeps, its chart", () => {
  // Bryan, 2026-11-20: "add another filter on other party involved. And so options would be something like 'No other
  // vehicle', 'Car', 'Bike', 'Multiple vehicles'".
  const keys = plain(S.OTHERS.map((o) => o[0]));
  assert.deepEqual(keys, ["none", "foot", "car", "moto", "bike", "parked", "multiple", "unknown"]);
  // The six keys of the first release still read from an address.
  for (const k of ["none", "car", "moto", "bike", "parked", "multiple"]) assert.deepEqual(plain(S.fromHash("#other=" + k).filter.other), [k]);
  // The generator's options are the page's, in the same order.
  const light = fs.readFileSync(path.join(ROOT, "tools/street-safety/street-safety-light.py"), "utf8");
  assert.deepEqual(JSON.parse(/^OTHERS = (\[.*\])$/m.exec(light)[1]), keys);
  assert.ok(S.FILTERS.injuries.includes("other") && !S.FILTERS.crime.includes("other"));
  assert.ok(S.CHARTS.injuries.includes("by-other"));
  assert.deepEqual(plain(S.DEFAULTS.filter.other), []);
  // The address carries it, in the options' order; every option, or an unknown one, is no filter.
  assert.equal(S.toHash(S.normalize({ filter: { other: ["bike", "none"] } })), "#other=none,bike");
  assert.equal(S.toHash(S.fromHash("#user=Walking&other=car,multiple")), "#user=Walking&other=car,multiple");
  assert.deepEqual(plain(S.fromHash("#other=parked").filter.other), ["parked"]);
  assert.equal(S.toHash(S.normalize({ filter: { other: keys } })), "");
  assert.equal(S.toHash(S.fromHash("#other=tram")), "");
  // The map's expression and the figures' test keep the same people.
  const s = S.normalize({ filter: { other: ["none", "bike"], severity: "pain", years: null } });
  assert.ok(JSON.stringify(S.peopleFilter(s, null)).includes('["in",["get","op"],["literal",["none","bike"]]]'));
  const t = S.shownTest(s), ppl = keys.map((k) => ({ op: k, sv: 1, d: "2023-05-01", u: "Walking", hy: 0, at: 1, wd: 2, h: 9 }));
  assert.deepEqual(ppl.filter(t).map((p) => p.op), ["none", "bike"]);
  assert.equal(ppl.filter(S.shownTest({ filter: { severity: "pain", years: null } })).length, keys.length);
  // A death from the fatality log has no party rows (op ""), so the filter takes it off, as the cause filter does.
  assert.equal(t({ op: "", sv: 0, d: "2025-05-01", u: "Walking", hy: 0, at: -1, wd: 2, h: 9 }), false);
  // Its chart sorts by count, largest first.
  assert.deepEqual(S.sortRows("by-other", [{ key: "none", label: "No other vehicle", value: 5 }, { key: "car", label: "Car or truck", value: 60 }, { key: "multiple", label: "Multiple vehicles", value: 7 }]).map((r) => r.key), ["car", "multiple", "none"]);
  // "Unknown vehicle" is a leftover bar, last whatever its count (Bryan, 2026-11-19: sorted by the data "(except Other)").
  assert.deepEqual(plain(S.sortRows("by-other", keys.map((k, i) => ({ key: k, label: S.OTHERS[i][1], value: k === "unknown" ? 99 : i }))).map((r) => r.key)), ["multiple", "parked", "bike", "moto", "car", "foot", "none", "unknown"]);
  assert.equal(S.plan({}, { filter: { other: ["car"] } }).filter, true);
  // map.json's count per option covers every option and adds up to the police-report people the map counts: the ones
  // it draws and the ones with no place (`np`), who take an option like anyone else. So the options partition the
  // headline's population, and the drawn people's options add to the drawn total.
  const D = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const O = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/people-2005-2020.json"), "utf8"));
  assert.deepEqual(Object.keys(D.others).sort(), keys.slice().sort());
  assert.deepEqual(plain(D.light.ops), keys);
  const counted = D.people.filter((p) => !p.lg).length + D.light.n + O.n, unplaced = D.light.np.length + O.np.length;
  assert.ok(unplaced > 0 && unplaced < 0.01 * counted, `${unplaced} of ${counted} people have no place`);
  assert.equal(Object.values(D.others).reduce((a, b) => a + b, 0), counted);
  const tally = Object.fromEntries(keys.map((k) => [k, 0])), tallyDrawn = { ...tally };
  for (const p of D.people) if (!p.lg) { tally[p.op]++; tallyDrawn[p.op]++; }
  for (const L of [D.light, O]) { const np = new Set(L.np); L.op.forEach((o, i) => { tally[L.ops[o]]++; if (!np.has(i)) tallyDrawn[L.ops[o]]++; }); }
  assert.deepEqual(tally, plain(D.others));
  assert.equal(Object.values(tallyDrawn).reduce((a, b) => a + b, 0), counted - unplaced);
  assert.ok(D.people.filter((p) => p.lg).every((p) => p.op === ""));
});

// ---- The street-arrangement carousel (site/src/safety-map/arrangements.js and .mjs).
const { arrangements, arrangementsHTML } = await import(path.join(ROOT, "site/src/safety-map/arrangements.mjs"));
test("the street-arrangement carousel shows only with Pedestrian violation picked on the cause chart", () => {
  const ac = {};
  vm.createContext(ac);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "site/src/safety-map/arrangements.js"), "utf8") + "\nthis.SafetyArrangements = SafetyArrangements;", ac);
  const shows = (h) => ac.SafetyArrangements.shows(S.fromHash(h), S);
  assert.equal(shows("#pick=pedestrian-violation"), true);
  assert.equal(shows("#chart=by-cause&cause=pedestrian-violation"), true);
  for (const h of ["", "#chart=by-cause", "#pick=red-light", "#pick=unsafe-speed", "#pick=dui&time=night", "#cause=pedestrian-violation", "#chart=by-cause&cause=pedestrian-violation,red-light",
    "#pick=pedestrian-violation&view=stress", "#pick=pedestrian-violation&view=crime"]) assert.equal(shows(h), false, h);
  // A subcause alone is a narrower set than the cards count.
  const sub = S.fromHash("#chart=by-cause"); sub.filter.cause = ["pedestrian-violation/x"];
  assert.equal(ac.SafetyArrangements.shows(sub, S), false);
});
test("the carousel's cards are the manifest's, in its order, with no figure of its own", () => {
  const A = arrangements(), html = arrangementsHTML();
  assert.equal(A.cards.length, 7);
  assert.equal(A.cards.reduce((a, c) => a + c.count, 0), A.total);
  const titles = [...html.matchAll(/<p class="ss-arr-t">([^<]*)<\/p>/g)].map((m) => m[1]);
  assert.deepEqual(titles, A.cards.map((c) => c.title.replace(/&/g, "&amp;")));
  const figs = [...html.matchAll(/<b>(\d+)<\/b> people, (?:(\d+) of them|none) killed/g)].map((m) => [Number(m[1]), Number(m[2] || 0)]);
  assert.deepEqual(figs, A.cards.map((c) => [c.count, c.killed]));
  for (const c of A.cards) assert.ok(html.includes(`style="--c:${A.verdict_colors[c.verdict]}"><b>Daylighting: ${c.verdict.replace(/'/g, "'")}</b>`), c.id);
  assert.match(html, /aria-label="Previous street arrangement"/);
  assert.match(html, /aria-label="Next street arrangement"/);
  assert.match(html, /Data read Nov 20, 2026\./);
  // The cards are a fixed 2022 to 2024 snapshot beside a headline that follows the Years filter, so the heading says so.
  assert.match(html, /<p class="ss-arr-h">Street Arrangements, 2022 to 2024<\/p>/);
  // Seven sketches on one page: no arrowhead id is shared between two of them.
  const ids = [...html.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length);
});

test("a person with no place counts under every filter that needs no place, and under none that does", () => {
  const np = { np: 1, c: null, op: "car", sv: 0, k: 1, d: "2025-08-09", yr: 2025, u: "Walking", ck: "speed", sk: "22350", hy: 0, at: -1, hood: "", dist: 0, wd: 6, h: 23 };
  const shown = (filter) => S.shownTest({ filter }, filter && filter.area && filter.area.polygon ? S.areaGeom({ filter }, [], []) : null)(np);
  // Counted: the default state, and severity, years, road user, other party, cause, day and time.
  for (const f of [{}, { severity: "killed" }, { years: [2025, 2025] }, { years: null, severity: "pain" }, { user: ["Walking"] }, { other: ["car"] }, { cause: ["speed"] }, { days: ["weekend"] }, { time: ["night"] }])
    assert.equal(shown(f), true, JSON.stringify(f));
  assert.equal(shown({ years: [2024, 2024] }), false);
  // Not counted: an area of any kind, the network on or off, its groups, at an intersection or midblock.
  for (const f of [{ area: { hood: "Mission" } }, { area: { district: 6 } }, { area: { polygon: [[-122.5, 37.7], [-122.3, 37.7], [-122.3, 37.9], [-122.5, 37.9]] } },
    { hin: "on" }, { hin: "off" }, { hinGroup: [1] }, { at: "intersection" }, { at: "midblock" }])
    assert.equal(shown(f), false, JSON.stringify(f));
  // The source's four severe or fatal people since 2021 with no point are in the map's data, counted and not drawn.
  const L = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8")).light;
  const d0 = Date.parse(L.d0 + "T00:00:00Z"), day = (i) => new Date(d0 + L.dd[i] * 864e5).toISOString().slice(0, 10);
  const ksi = L.np.filter((i) => L.sv[i] <= 1).map((i) => `${L.sv[i]} ${day(i)}`).sort();
  for (const want of ["0 2025-08-09", "1 2024-03-31", "1 2025-08-25", "1 2026-06-15"]) assert.ok(ksi.includes(want), `no unplaced person ${want}`);
  assert.ok(L.np.every((i) => L.x[i] === 0 && L.y[i] === 0 && L.hood[i] === -1 && L.at[i] === -1 && L.hy[i] === 0 && L.hs[i] === -1));
  // Deaths per year are the source's rows: 25 in 2025, SFMTA's published total.
  // A death the fatality log also lists is counted as the log's person, with its card (street-safety-map.py log_deaths()).
  const D2 = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const deaths = (y) => L.sv.filter((v, i) => v === 0 && day(i).slice(0, 4) === y).length + D2.people.filter((p) => p.k && !p.lg && p.d.slice(0, 4) === y).length;
  assert.equal(deaths("2025"), 25);
  assert.equal(L.by_level_year["0/2025"], 25);
});

test("deaths: the icons drawn and the people counted are the same under every cause and every other party", () => {
  // Bryan, 2026-11-20, with Walking, killed and one cause picked: heat-map spots with no icon. A death the fatality log
  // and the police both hold was drawn as the log's person, who had no cause, and counted as the police row, so a
  // cause filter kept the count and the heat and hid the icon. tools/street-safety/street-safety-map.py log_deaths() now makes the
  // two one person. This reads map.json the way site/src/safety-map/map.js does: the icon layers draw every severe
  // or fatal person but the light rows listed in `nd`, and the headline, the charts and the heat map count everyone
  // but `lg` (shownFor(), applyFilters()). A person with no place (`np`) is counted and can't be drawn, so is left out
  // of both sides here.
  const D = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/map.json"), "utf8"));
  const L = D.light, nd = new Set(L.nd || []), np = new Set(L.np || []), d0 = Date.parse(L.d0 + "T00:00:00Z");
  const people = D.people.filter((p) => p.k).map((p) => ({ ...p, sv: 0 }));
  for (let i = 0; i < L.n; i++) {
    if (L.sv[i] !== 0) continue;   // only the deaths: the severity filter below would drop the rest
    people.push({ d: new Date(d0 + L.dd[i] * 864e5).toISOString().slice(0, 10), h: L.h[i], u: L.users[L.u[i]], ck: L.cks[L.ck[i]], sk: L.sks[L.sk[i]],
      at: L.at[i], hy: L.hy[i], op: L.ops[L.op[i]], lg: 0, sv: L.sv[i], mi: 1, nd: nd.has(i) ? 1 : 0, np: np.has(i) ? 1 : 0 });
  }
  const tally = (filter) => {
    const t = S.shownTest(S.normalize({ filter: { severity: "killed", years: [S.INLINE_FROM, S.NEWEST_YEAR], ...filter } }));
    const kept = people.filter((p) => !p.np && t(p));
    return { icons: kept.filter((p) => p.sv <= 1 && !p.nd).length, counted: kept.filter((p) => !p.lg).length };
  };
  const bad = [];
  const each = (name, filter) => { const r = tally(filter); if (r.icons !== r.counted) bad.push(`${name}: ${r.icons} icons, ${r.counted} counted`); return r; };
  let checked = 0;
  for (const c of D.causes) {
    checked += each("cause " + c.key, { cause: [c.key] }).counted;
    for (const sub of c.subs) each("cause " + c.key + "/" + sub.key, { cause: [c.key + "/" + sub.key] });
    for (const u of S.USERS) each(u + ", cause " + c.key, { user: [u], cause: [c.key] });
  }
  for (const o of S.OTHERS) each("other party " + o[0], { other: [o[0]] });
  assert.deepEqual(bad, [], "deaths drawn and counted differ:\n  " + bad.join("\n  "));
  // With no cause or other party picked, the only icons not counted are the deaths with no police report (`lg`), and
  // every cause's deaths add up to the deaths counted.
  const all = tally({});
  assert.equal(all.icons - all.counted, D.people.filter((p) => p.lg && p.d.slice(0, 4) >= S.INLINE_FROM).length);
  assert.equal(checked, all.counted);
  assert.ok(D.people.filter((p) => p.lg).every((p) => p.ck === "" && p.op === ""));
  assert.equal(D.meta.figures.deaths_outside_police_reports, D.people.filter((p) => p.lg).length);
});

test("a crash card says how badly each party's people were hurt, above the drawing", () => {
  // Bryan, 2026-11-20, on crash 230472899: "Is there any narrative we're not showing? If so show it before the map".
  // The card said only that the scooter rider complained of pain; the walker it killed was named nowhere on it.
  const cards = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/cards/2023/19-8.json"), "utf8")).cards;
  const cr = cards["230472899"];
  assert.deepEqual(cr.pi, [[["p"]], [["k"]]]);
  const cx = { window: {}, document: {} };
  vm.runInNewContext(fs.readFileSync(path.join(ROOT, "site/src/safety-map/crash-cards.js"), "utf8") + "\nthis.CrashCards = CrashCards;", cx);
  const html = cx.CrashCards.slide(cr, [], {});
  const at = (t) => { const i = html.indexOf(t); assert.ok(i >= 0, t); return i; };
  assert.ok(at("crossing outside a crosswalk") < at("Killed") && at("Killed") < at("Primary factor") && at("Primary factor") < at("<svg"));
  assert.ok(at("Complaint of pain") < at("<svg") && at("<svg") < at("Conditions"));
  assert.equal(html.split("Primary factor").length, 2);   // said once, above the drawing, not again in the details
  // Every card: one injury list per party line, and each level one of the map's four or "n".
  let seen = 0;
  for (const y of fs.readdirSync(path.join(ROOT, "site/data/street-safety/cards")).filter((d) => /^\d{4}$/.test(d))) {
    for (const f of fs.readdirSync(path.join(ROOT, "site/data/street-safety/cards", y))) {
      const C = JSON.parse(fs.readFileSync(path.join(ROOT, "site/data/street-safety/cards", y, f), "utf8")).cards;
      for (const c in C) {
        seen++;
        assert.equal(C[c].pi.length, C[c].pr.length, c);
        assert.ok(C[c].pi.every((row) => row.every((e) => "ksvpn".includes(e[0]) && e[0].length === 1 && (e[0] !== "n" || e.length === 1))), c);
      }
    }
  }
  assert.ok(seen > 60000);
});

// One map per story page (the review of 2026-11-19, rank 2): however many <MapStory> blocks a page has, it builds
// one map, whose stage moves into the block being read. Run against a stand-in page, since no browser runs here.
const { mapStories, STORY_SCRIPTS } = await import(path.join(ROOT, "site/src/safety-map/story.mjs"));
test("a story page with several blocks draws one map, and each block's steps move it into that block", () => {
  const pub = fs.readFileSync(path.join(ROOT, "site/content/transportation/street-safety/story.md"), "utf8");
  const { text, stories } = mapStories(pub, "story.md");
  assert.ok(stories >= 2, `${stories} blocks`);
  assert.equal(text.split('class="sm-story-map"').length - 1, 1, "one map element on the page");
  assert.equal(text.split('class="sm-story-stage"').length - 1, 1, "one stage on the page");
  assert.equal(text.split('class="sm-story-graphic sm-stage"').length - 1, stories, "a frame for every block");
  // The page's glue script, run over stand-ins for the blocks: one map is created, and a step moves the stage.
  const glue = [...STORY_SCRIPTS.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).filter((t) => t.includes("sm-story-stage")).pop();
  const el = (extra = {}) => ({ children: [], appendChild(c) { if (c.parent) c.parent.children.splice(c.parent.children.indexOf(c), 1); c.parent = this; this.children.push(c); }, ...extra });
  const parts = {}, stage = el({ querySelector: (q) => (parts[q] = parts[q] || el()) });
  const boxes = [], stepsAll = [];
  for (let b = 0; b < stories; b++) {
    const graphic = el({ getBoundingClientRect: () => ({ top: 0, bottom: 0 }) });
    if (b === 0) graphic.appendChild(stage);
    const steps = [0, 1].map((k) => { const card = el(); return { card, querySelector: () => card, state: JSON.stringify({ view: "injuries", worst: 2020 + b, k }), classList: { toggle() {} }, getAttribute() { return this.state; } }; });
    stepsAll.push(...steps);
    boxes.push({ graphic, steps, getAttribute: (a) => (a === "data-story" ? "street-safety" : "/x"),
      querySelector: (q) => (q === ".sm-story-graphic" ? graphic : q === ".sm-story-stage" ? (b === 0 ? stage : null) : null), querySelectorAll: () => steps });
  }
  const made = [], states = [];
  const ctl = { setState: (s) => states.push(s), map: () => ({ resize() {} }), ready: { then() {} } };
  let narrow = false;
  const win = { matchMedia: () => ({ matches: narrow }), addEventListener() {}, dispatchEvent() {}, innerHeight: 800, innerWidth: 1366 };
  const g = { window: win, document: { querySelectorAll: () => boxes }, SafetyMap: { create: (...a) => { made.push(a); return ctl; } }, SafetyOverlay: { attach() {} },
    maplibregl: {}, sfMap: {}, CrashCards: {}, SafetyMapState: {}, Event: class {}, setTimeout: () => {} };
  vm.runInNewContext(glue, g);
  assert.equal(made.length, 1, "one map for every block");
  const last = stepsAll.length - 1;
  boxes[0].sfStep(last);
  assert.equal(stage.parent, boxes[stories - 1].graphic, "the last step's block holds the stage");
  assert.equal(JSON.parse(stepsAll[last].state).worst, states.at(-1).worst);
  boxes[0].sfStep(0);
  assert.equal(stage.parent, boxes[0].graphic);
  assert.equal(boxes.reduce((a, b) => a + b.graphic.children.length, 0), 1, "the stage is in one frame only");
  // On a wide screen the key and the chart stay on the map; on a phone they ride in the active step's card.
  assert.equal(parts[".sm-legend"].parent, stage);
  assert.equal(parts["[data-chart]"].parent, stage);
  narrow = true;
  boxes[0].sfStep(3);
  assert.equal(parts[".sm-legend"].parent, stepsAll[3].card, "on a phone the key is in the step's card");
  assert.equal(parts["[data-chart]"].parent, stepsAll[3].card, "on a phone the chart is in the step's card");
  narrow = false;
  boxes[0].sfStep(0);
  assert.equal(parts["[data-chart]"].parent, stage);
});

console.log(`safety-map-test: ${n} passed`);
