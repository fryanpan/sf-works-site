// School Trips' Citywide Goals view: six wedges filling two goal bars, from the wedges doc Bryan asked for on
// 2026-10-21 ("Please start making simulation page updates to match the public comment. So implement a first draft
// of wedges on the city-wide screen"). One bar runs from the Travel Tally's 48.6% of school trips by family car to
// Safe Routes' 30%, the other from none avoided to 30% fewer kids hurt a year (wedgeTable's hurtBase, the model's HB:
// kids 5 to 18 hurt on school-year weekdays, about 92 a year, so a goal of about 28). Each wedge is a group of changes
// with a control that steps through them and stops at the wedge's ceiling, named by what stops it.
//
// WEDGES is plain data. Each step is the model's switch set for that wedge, a patch onto makeCityModel's OFF, and a
// wedge's later steps keep its earlier ones. An idea the model has no lever for is listed with lever null, shown as
// not counted yet, and only those ideas are listed under a wedge, since its control's label names what is counted. A
// wedge with one step only has no lever yet and is shown as not modeled.
//
// wedgeTable runs the model (site/src/school-trips-model.mjs) for every combination of steps, and is called only by
// tools/school-trips/school-trips-figures.mjs, which writes the result to site/data/figures.json for the page to read. The levers
// inside and across wedges reach the same kids, so nothing here adds two changes' figures: each total is the model's
// own stacked figure for the whole switch set (figC for students and the tally, hurt for kids hurt, cost for cost),
// and a wedge's segment is what it adds to the wedges above it in this order, the stacked figure with it less the
// stacked figure without it.
//
// wedgeView, WEDGE_CSS and wedgeUI are the page's half. wedgeUI is shipped to the browser as source, so it uses no
// imports or outside names.

/** Observable 10's first six colours, one a wedge, since the wedges are an unordered set. */
const OBS10 = ["#4269d0", "#efb118", "#ff725c", "#6cc5b0", "#3ca951", "#ff8ab7"];
const DRAFT_URL = "https://www.sfmta.com/safe-school-connections-draft-approach-september-2026";
const TALLY_URL = "https://www.sfsaferoutes.org/documents/2026/SFSRTS_Report_final_spreads_low_res.pdf";

const PLAN = { school_street: 1, safer_crossings: 1, calm: 1, connector: 1 };
export const WEDGES = [
  {
    id: "streets", name: "Safe Streets to Walk and Bike", short: "Streets", ceiling: "How fast the city builds",
    steps: [
      ["None", {}],
      ["SFMTA's Plan", PLAN],
      ["Plan and $20M of Bikeways", { ...PLAN, seg: 20 }],
      ["Plan and $40M of Bikeways", { ...PLAN, seg: 40 }],
      ["Plan and $100M of Bikeways", { ...PLAN, seg: 100 }],
      ["Also Crossings to a Quarter Mile", { ...PLAN, seg: 100, xreach: 1320 }],
    ],
    ideas: [
      ["School Streets, closed to cars at the bells", "school_street"],
      ["Safer crossings, one block out, then a quarter mile", "safer_crossings"],
      ["15/20 mph school zone signs", "calm"],
      ["School Connector Streets", "connector"],
      ["New bikeways from the Biking and Rolling Plan, up to $100M", "seg"],
      ["Finish the last 50 High Injury Network miles", null],
      ["Calm 130 more miles of main streets", null],
    ],
  },
  {
    id: "slower", name: "Slower Cars", short: "Slower Cars", ceiling: "State law on cameras",
    steps: [
      ["None", {}],
      ["Speed Humps and 20 mph Shopping Streets", { speed_humps: 1, bad_district: 1 }],
      ["Also Speed Cameras by Schools", { speed_humps: 1, bad_district: 1, speed_cameras: 1 }],
    ],
    ideas: [
      ["Speed humps on side streets by schools", "speed_humps"],
      ["20 mph on shopping streets near schools", "bad_district"],
      ["Speed cameras by schools, if the state lifts its cap of 33", "speed_cameras"],
      ["237 more speed cameras on the High Injury Network", null],
      ["A 20 mph default speed limit", null],
      ["Low traffic neighborhoods", null],
    ],
  },
  {
    id: "driving", name: "Driving Less Convenient", short: "Driving", ceiling: "State law and political will",
    steps: [["Not Modeled Yet", {}]],
    ideas: [
      ["A circulation plan with turn bans against through driving, like Ghent's", null],
      ["An area charge like London's", null],
      ["A downtown congestion charge", null],
    ],
  },
  {
    id: "transit", name: "Better Transit", short: "Transit", ceiling: "Muni's budget gap",
    steps: [
      ["None", {}],
      ["Free Muni for Caregivers", { caregiver_muni: 1 }],
    ],
    ideas: [
      ["Free Muni for a caregiver riding with a child", "caregiver_muni"],
      ["25% more Muni at school times", null],
      ["10% more Muni citywide", null],
    ],
  },
  {
    id: "shorter", name: "Shorter Trips", short: "Shorter Trips", ceiling: "SFUSD's April 2027 vote",
    steps: [
      ["Today's Assignment", {}],
      ["SFUSD's New Assignment by 2030", { assign: "assign_ncp52" }],
    ],
    ideas: [
      ["Neighborhood + Citywide Programs, the assignment SFUSD's Board chose", "assign"],
      ["Dense housing near transit", null],
    ],
  },
  {
    id: "parent", name: "Trips Without a Parent Driving", short: "No Parent Driving", ceiling: "Bus budget and volunteers",
    steps: [
      ["None", {}],
      ["Daily Travel Tracker", { travel_tracker: 1 }],
      ["Also Walking and Bike Buses, Carpools", { travel_tracker: 1, walking_bus: 1, bike_bus: 1, carpool: 1 }],
      ["Also Yellow Bus Loops", { travel_tracker: 1, walking_bus: 1, bike_bus: 1, carpool: 1, yellow_bus: 1 }],
    ],
    ideas: [
      ["A daily travel tracker in TK-5 classrooms", "travel_tracker"],
      ["Walking school buses", "walking_bus"],
      ["Bike buses", "bike_bus"],
      ["Carpool matching", "carpool"],
      ["Yellow bus shuttle loops", "yellow_bus"],
    ],
  },
].map((w, i) => ({ ...w, color: OBS10[i] }));

/**
 * The page opens on SFMTA's plan: its four tools in the first wedge, on SFUSD's chosen assignment as every scenario but
 * Today holds it (docs/decisions/school-trips.md, 2026-10-17 and 2026-10-23), and nothing else.
 */
export const PLAN_STEPS = WEDGES.map((w) => (w.id === "streets" || w.id === "shorter" ? 1 : 0));
/** Every wedge at its ceiling. */
export const FULL_STEPS = WEDGES.map((w) => w.steps.length - 1);

/** The model's switch set for the first n wedges at the given steps (all six by default). */
export function wedgeConfig(OFF, steps, n = WEDGES.length) {
  const c = { ...OFF };
  for (let i = 0; i < n; i++) Object.assign(c, WEDGES[i].steps[steps[i]][1]);
  return c;
}

/** Every combination of steps, in mixed radix with the first wedge slowest, as the browser indexes it. */
export function combos() {
  const out = [[]];
  for (const w of WEDGES) out.splice(0, out.length, ...out.flatMap((p) => w.steps.map((_, k) => p.concat(k))));
  return out;
}

/**
 * The model's figures for every combination of steps. Per combination: the totals (students out of single-family
 * cars, the tally's car share, kids hurt a year spared, cost once and a year) and each wedge's segment of the
 * students, tally points and kids hurt, as what it adds to the wedges above it. Rounded to what the page prints, so
 * the file stays small and stable. Also each first-wedge step's students with a safe walk or bike trip of 15
 * minutes, since that's what the first wedge's streets change.
 */
export function wedgeTable(MD) {
  const T = MD.fig(MD.TODAY), memo = new Map();
  const at = (steps, n) => {
    const key = steps.slice(0, n).join("");
    if (!memo.has(key)) {
      const c = wedgeConfig(MD.OFF, steps, n), X = MD.figC(c), k = MD.cost(c);
      memo.set(key, { cars: T.modes[0] - X.modes[0], tally: X.tally, hurt: MD.hurt(c), once: k.once, year: k.year });
    }
    return memo.get(key);
  };
  const r = (x, d) => Math.round(x * 10 ** d) / 10 ** d;
  const rows = combos().map((steps) => {
    const segs = WEDGES.map((_, i) => {
      const a = at(steps, i), b = at(steps, i + 1);
      return [r(b.cars - a.cars, 2), r(a.tally - b.tally, 3), r(b.hurt - a.hurt, 3)];
    });
    const t = at(steps, WEDGES.length);
    return { s: steps.join(""), cars: r(t.cars, 2), tally: r(t.tally, 3), hurt: r(t.hurt, 3), once: r(t.once, 3), year: r(t.year, 3), segs };
  });
  const safe = WEDGES[0].steps.map(([, p]) => r(MD.safeN(MD.svar({ ...MD.OFF, ...p })).n, 0));
  return { tallyToday: r(T.tally, 3), hurtBase: r(MD.HB, 3), rows, safe, safeOf: r(MD.safeN(MD.svar(MD.OFF)).of, 0) };
}

export const WEDGE_CSS = `<style>
.wg { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); gap: 16px; height: calc(100dvh - 160px); min-height: 560px; }
.wg-ctl { overflow-y: auto; border: 1px solid var(--rule); border-radius: 8px; padding: 10px 12px; font-size: 0.84rem; }
.wg-pre { display: flex; gap: 6px; margin: 0 0 8px; }
.wg-pre button { flex: 1; border: 1px solid var(--rule); background: var(--paper); border-radius: 8px; padding: 6px 8px; font: inherit; font-size: 0.8rem; font-weight: 600; cursor: pointer; }
.wg-pre button[aria-pressed="true"] { border-color: var(--seq-3); background: var(--seq-3-soft); box-shadow: inset 3px 0 0 var(--seq-3); }
.wg-w { border-top: 1px solid var(--rule); padding: 7px 0; }
.wg-head { display: flex; align-items: center; gap: 8px; }
.wg-head i { flex: none; width: 12px; height: 12px; border-radius: 3px; background: var(--c); }
.wg-head b { font-size: 0.86rem; }
.wg-ideas { border: 0; background: none; padding: 0 2px; font: inherit; font-size: 0.72rem; color: var(--muted); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; text-decoration-color: var(--rule); }
.wg-ideas[aria-expanded="true"] { color: var(--ink); }
.wg-head output { margin-left: auto; font-size: 0.76rem; font-weight: 600; color: var(--ink); text-align: right; }
.wg-head output.wg-nm { color: var(--muted); font-style: italic; font-weight: 400; }
.wg-range { display: grid; grid-template-columns: minmax(0, 1fr) 15.5em; align-items: center; gap: 10px; margin: 4px 0 0 20px; }
.wg-range small { color: var(--muted); font-size: 0.7rem; white-space: nowrap; text-align: right; }
.wg-range small::before { content: "Limit: "; }
.wg-range input { -webkit-appearance: none; appearance: none; width: 100%; height: 18px; margin: 0; background: none; cursor: pointer; }
.wg-range input::-webkit-slider-runnable-track { height: 6px; border-radius: 3px; background: linear-gradient(90deg, var(--c) var(--f, 0%), var(--rule) var(--f, 0%)); }
.wg-range input::-moz-range-track { height: 6px; border-radius: 3px; background: var(--rule); }
.wg-range input::-moz-range-progress { height: 6px; border-radius: 3px; background: var(--c); }
.wg-range input::-webkit-slider-thumb { -webkit-appearance: none; width: 16px; height: 16px; margin-top: -5px; border-radius: 50%; background: #fff; border: 2px solid var(--c); box-shadow: 0 1px 2px rgba(0,0,0,.2); }
.wg-range input::-moz-range-thumb { width: 14px; height: 14px; border-radius: 50%; background: #fff; border: 2px solid var(--c); }
.wg-range input:focus-visible { outline: 2px solid var(--c); outline-offset: 2px; }
.wg-w ul { list-style: none; margin: 6px 0 2px 20px; padding: 0; font-size: 0.76rem; }
.wg-w ul[hidden] { display: none; }
.wg-w li { display: flex; gap: 6px; padding: 1px 0; }
.wg-w li span { flex: 1; }
.wg-w li em { font-style: normal; font-size: 0.68rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.wg-w li.wg-safe { color: var(--muted); padding-top: 3px; }
.wg-out { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.wg-card { border: 1px solid var(--rule); border-radius: 8px; padding: 10px 14px; }
.wg-card h2 { font-size: 1.05rem; margin: 0; }
.wg-big { font-size: 1.6rem; font-weight: 700; margin: 2px 0 0; font-variant-numeric: tabular-nums; }
.wg-big small { display: block; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
.wg-bar { margin-top: 6px; min-height: 120px; }
.wg-bar svg { display: block; overflow: visible; }
.wg-cost { font-size: 0.9rem; margin: 0; }
.wg-cost b { font-variant-numeric: tabular-nums; }
.wg-note { color: var(--muted); font-size: 0.74rem; margin: 0; }
@media (max-width: 860px) {
  .wg { display: flex; flex-direction: column-reverse; height: auto; min-height: 0; gap: 12px; }
  .wg-ctl { overflow: visible; }
  .wg-range { margin-left: 0; grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .wg-range small { text-align: left; }
  .wg-w ul { margin-left: 0; }
}
</style>`;

/** The view's markup. T is wedgeTable's result, from figures.json. */
export function wedgeView(T) {
  const wedges = WEDGES.map((w, i) => {
    const one = w.steps.length < 2;
    const ctl = one ? "" : `<div class="wg-range"><input type="range" min="0" max="${w.steps.length - 1}" step="1" value="0" data-wedge="${i}" aria-label="${w.name}"><small>${w.ceiling}</small></div>`;
    // The ideas the model counts are named by the control's label, so the list holds only the ones it doesn't count yet.
    const ideas = w.ideas.filter(([, lever]) => !lever).map(([name]) => `<li><span>${name}</span><em>Not counted yet</em></li>`).join("")
      + (i === 0 ? `<li class="wg-safe" data-safe></li>` : "");
    const btn = ideas ? `<button type="button" class="wg-ideas" aria-expanded="false" aria-controls="wg-ideas-${i}">Ideas</button>` : "";
    return `<div class="wg-w" data-wi="${i}" style="--c:${w.color}">
      <div class="wg-head"><i></i><b>${w.name}</b>${btn}<output data-wedge-step="${i}"${one ? ' class="wg-nm"' : ""}>${one ? "Not modeled yet" : w.steps[0][0]}</output></div>
      ${ctl}
      ${ideas ? `<ul id="wg-ideas-${i}" hidden>${ideas}</ul>` : ""}
    </div>`;
  }).join("");
  return `<section class="tr-view" id="v-goals" aria-label="Citywide goals">
<div class="wg">
  <aside class="wg-ctl" aria-label="Wedges">
    <div class="wg-pre"><button type="button" data-wpre="plan" aria-pressed="true">SFMTA's Plan</button><button type="button" data-wpre="full" aria-pressed="false">Fill Every Wedge</button></div>
    ${wedges}
  </aside>
  <div class="wg-out">
    <section class="wg-card" aria-labelledby="wg-car-h">
      <h2 id="wg-car-h">Fewer Kids in Family Cars</h2>
      <p class="wg-big" data-wg-big="car"></p>
      <div class="wg-bar" data-wg-bar="car"></div>
    </section>
    <section class="wg-card" aria-labelledby="wg-hurt-h">
      <h2 id="wg-hurt-h">Fewer Kids Hurt a Year</h2>
      <p class="wg-big" data-wg-big="hurt"></p>
      <div class="wg-bar" data-wg-bar="hurt"></div>
    </section>
    <p class="wg-cost" data-wg-cost></p>
    <p class="wg-note">The car share and its goal are from the <a href="${TALLY_URL}">Safe Routes to School report</a> on SFMTA's Travel Tally. SFMTA's plan is the four tools in its <a href="${DRAFT_URL}">Safe School Connections draft</a>, at every school, with the assignment SFUSD's Board chose. <a href="/transportation/school-trips/about#wedges">How we count the wedges</a></p>
  </div>
</div>
</section>`;
}

/**
 * The browser half: draws the bars and keeps the controls in step with the state. root is the view's section, T the
 * table, W the wedges' names, colours and step names, plan and full the two presets, and
 * onChange is called with the steps whenever a reader moves a control, and must call draw(). Returns { set(steps), get(), draw }.
 */
export function wedgeUI(root, T, W, plan, full, onChange) {
  const $$ = (s) => [...root.querySelectorAll(s)];
  const n0 = (x) => Math.round(x).toLocaleString("en-US");
  const k1 = (x) => (Math.round(x * 10) / 10).toFixed(1);
  const m3 = (x) => "$" + Number(x.toPrecision(3)) + "M";
  const radix = W.map((w) => w.steps.length), idx = (s) => s.reduce((t, k, i) => t * radix[i] + k, 0);
  // Both goals are 30%: Safe Routes' car share, and 30% fewer of the kids hurt a year today (the model's base).
  const CAR_GOAL = 30, HURT_GOAL = 0.3 * T.hurtBase;
  let steps = plan.slice();
  const same = (a, b) => a.every((x, i) => x === b[i]);
  // Each wedge's part rounded to d places so the printed parts add up to the printed total: round each, then give the
  // units left over to the parts whose rounding moved them furthest the other way (largest remainder).
  function parts(xs, total, d) {
    const u = 10 ** d, r = xs.map((x) => Math.round(x * u));
    let left = Math.round(total * u) - r.reduce((t, x) => t + x, 0);
    const dir = Math.sign(left), gap = (i) => dir * (xs[i] * u - r[i]);
    const order = xs.map((_, i) => i).filter((i) => Math.abs(xs[i]) > 1e-6).sort((a, b) => gap(b) - gap(a) || a - b);
    for (let j = 0; left !== 0 && order.length; j = (j + 1) % order.length) { r[order[j]] += dir; left -= dir; }
    return r.map((x) => x / u);
  }
  // A label's width in characters, from its longest line.
  const wide = (t) => Math.max(...t.split("\n").map((l) => l.length));
  // A stacked bar of each wedge's segment, the count and the wedge's short name printed on it, or under the bar on a
  // short line back to it when it is too narrow to hold them. Ends: today and the goal. The bar runs past the goal when the wedges do.
  function bar(el, segs, from, goal, total, fmt, ends, more) {
    if (!window.Plot) { el.textContent = "The chart needs Observable Plot, which didn't load."; return; }
    const W0 = Math.max(260, el.clientWidth || 300);
    let x = 0;
    const rows = [];
    // A wedge whose figure prints as zero gets no segment, so no mark reads "0".
    segs.forEach((s, i) => { if (s.w > 1e-6 && fmt(s.n) !== fmt(0)) { rows.push({ i, x1: x, x2: x + s.w, n: s.n }); x += s.w; } });
    const span = Math.max(Math.abs(goal - from), Math.abs(total - from), x);
    const px = (u) => (u / span) * (W0 - 8), charW = 7.2;
    rows.forEach((q) => { q.t = `${fmt(q.n)}\n${W[q.i].short}`; q.fit = px(q.x2 - q.x1) >= wide(q.t) * charW + 8; q.cx = (q.x1 + q.x2) / 2; });
    // Callouts for the narrow ones, spread so they never overlap. A wedge that moves the figure the wrong way (kids who
    // leave cars to walk or bike on ordinary streets can add injuries) has no segment, so it gets a callout at the
    // bar's end saying how much it adds.
    // A single part with nothing set against it is the headline itself, so it prints no label.
    const back = [];
    segs.forEach((s, i) => { if (s.w < 0 && fmt(-s.n) !== fmt(0)) { const x2 = back.length ? back[back.length - 1].x1 : x; back.push({ i, x1: Math.max(0, x2 + s.w), x2, n: s.n }); } });
    const solo = rows.length === 1 && !back.length;
    const call = solo ? [] : rows.filter((q) => !q.fit);
    back.forEach((q) => call.push({ i: q.i, cx: (q.x1 + q.x2) / 2, t: `${fmt(-q.n)} ${more}\n${W[q.i].short}` }));
    call.forEach((q) => { q.lx = px(q.cx); q.hw = (wide(q.t) * charW + 6) / 2; });
    for (let j = 1; j < call.length; j++) call[j].lx = Math.max(call[j].lx, call[j - 1].lx + call[j - 1].hw + call[j].hw);
    for (let j = call.length - 1; j >= 0; j--) {
      const lim = (j === call.length - 1 ? W0 - 8 : call[j + 1].lx - call[j + 1].hw) - call[j].hw;
      call[j].lx = Math.max(call[j].hw, Math.min(call[j].lx, lim));
    }
    call.forEach((q) => { q.lx = (q.lx / (W0 - 8)) * span; });
    const goalX = Math.abs(goal - from);
    el.replaceChildren(Plot.plot({
      width: W0, height: 120, marginLeft: 4, marginRight: 4, marginTop: 2, marginBottom: 2,
      x: { domain: [0, span], axis: null }, y: { domain: [0, 5], axis: null, reverse: true },
      marks: [
        Plot.rect([0], { x1: 0, x2: goalX, y1: 0.9, y2: 2.3, fill: "#f4f6f8", stroke: "#dfe3e9" }),
        Plot.rect(rows, { x1: "x1", x2: "x2", y1: 0.9, y2: 2.3, fill: (q) => W[q.i].color, stroke: "#fff", strokeWidth: 1, title: (q) => W[q.i].name }),
        Plot.rect(back, { x1: "x1", x2: "x2", y1: 0.9, y2: 2.3, fill: "#fff", fillOpacity: 0.7, stroke: (q) => W[q.i].color, strokeWidth: 2, strokeDasharray: "3,2", title: (q) => W[q.i].name }),
        Plot.text(rows.filter((q) => q.fit && !solo), { x: "cx", y: 1.6, text: "t", fill: (q) => (q.i === 0 ? "#fff" : "#15181c"), fontSize: 11, fontWeight: 600 }),
        Plot.link(call, { x1: "cx", x2: "lx", y1: 2.3, y2: 2.9, stroke: "#8a929c", strokeWidth: 1 }),
        Plot.text(call, { x: "lx", y: 2.95, text: "t", lineAnchor: "top", fill: "#15181c", fontSize: 11, fontWeight: 600, title: (q) => W[q.i].name }),
        Plot.ruleX([goalX], { y1: 0.75, y2: 2.45, stroke: "#15181c", strokeWidth: 1.5 }),
        // The axis ends, small and light so they read as the bar's scale rather than as figures beside the headline.
        Plot.text([0], { x: 0, y: 0.7, text: () => ends[0], textAnchor: "start", lineAnchor: "bottom", fill: "#737c88", fontSize: 10 }),
        Plot.text([0], { x: goalX, y: 0.7, text: () => ends[1], textAnchor: goalX > span * 0.8 ? "end" : "middle", lineAnchor: "bottom", fill: "#737c88", fontSize: 10 }),
      ],
    }));
  }
  function draw() {
    const R = T.rows[idx(steps)];
    const cars = parts(R.segs.map(([n]) => n), R.cars, 0), hurt = parts(R.segs.map(([, , h]) => h), R.hurt, 1);
    root.querySelector("[data-wg-big=car]").innerHTML = `${n0(R.cars)} students<small>${k1(R.tally)}% of school trips by family car</small>`;
    root.querySelector("[data-wg-big=hurt]").innerHTML = `${k1(R.hurt)} kids`;
    root.querySelector("[data-wg-cost]").innerHTML = `Cost: <b>${m3(R.once)}</b> once and <b>${m3(R.year)}</b> a year`;
    bar(root.querySelector("[data-wg-bar=car]"), R.segs.map(([, pts], i) => ({ n: cars[i], w: pts })), T.tallyToday, CAR_GOAL, R.tally, (n) => n0(n),
      [`${k1(T.tallyToday)}% today`, `Goal ${CAR_GOAL}%`], "more in cars");
    bar(root.querySelector("[data-wg-bar=hurt]"), R.segs.map(([, , h], i) => ({ n: hurt[i], w: h })), 0, HURT_GOAL, R.hurt, (n) => k1(n),
      ["None avoided yet", `Goal ${n0(HURT_GOAL)} of ${n0(T.hurtBase)}`], "more hurt");
    W.forEach((w, i) => {
      const inp = root.querySelector(`[data-wedge="${i}"]`);
      if (inp) { inp.value = String(steps[i]); inp.style.setProperty("--f", `${(100 * steps[i]) / (w.steps.length - 1)}%`); }
      const out = root.querySelector(`[data-wedge-step="${i}"]`);
      if (out && w.steps.length > 1) out.textContent = w.steps[steps[i]].name;
    });
    const sf = root.querySelector("[data-safe]");
    if (sf) sf.textContent = `${n0(T.safe[steps[0]])} of ${n0(T.safeOf)} students with a safe walk or bike trip of 15 minutes, ${n0(T.safe[0])} today`;
    $$("[data-wpre]").forEach((b) => b.setAttribute("aria-pressed", String(same(steps, b.dataset.wpre === "plan" ? plan : full))));
  }
  root.addEventListener("input", (e) => {
    const i = e.target.dataset && e.target.dataset.wedge;
    if (i == null) return;
    steps = steps.slice(); steps[Number(i)] = Number(e.target.value); onChange(steps);
  });
  root.addEventListener("click", (e) => {
    const t = e.target.closest(".wg-ideas");
    if (t) { const ul = root.querySelector("#" + t.getAttribute("aria-controls")), open = t.getAttribute("aria-expanded") !== "true"; t.setAttribute("aria-expanded", String(open)); ul.hidden = !open; return; }
    const b = e.target.closest("[data-wpre]");
    if (!b) return;
    steps = (b.dataset.wpre === "plan" ? plan : full).slice(); onChange(steps);
  });
  let rz = null;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (root.offsetParent) draw(); }, 120); });
  return {
    get: () => steps.slice(),
    set: (s) => { if (Array.isArray(s) && s.length === W.length && s.every((k, i) => Number.isInteger(k) && k >= 0 && k < radix[i])) steps = s.slice(); },
    draw,
  };
}

/** What the browser needs of WEDGES: names, colours and each step's name. */
export function wedgeClientData() {
  return WEDGES.map((w) => ({ name: w.name, short: w.short, color: w.color, steps: w.steps.map(([name]) => ({ name })) }));
}
