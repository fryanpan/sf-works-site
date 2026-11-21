// The shares of SF school trips by family car, transit, walking and bike, from SFMTA's Safe Routes
// to School tallies, against its goal of 30% by 2030. Data in
// data/school-car-share.json, read from the program's reports.
//
// Bryan, 2026-10-07, on the bike post: "SFMTA has a 30% car mode share target
// that's still current", "Would prefer to have something that's for all
// trips", and "We had SFMTA say that school mode share is 48% cars." The 30%
// is the school goal, the only city mode-share target still in force after
// Ordinance 59-26 repealed the 80% all-trips goal, so this chart replaced the
// Census commute chart. It uses the 2024-25 report's figures throughout; the
// 2023-24 report printed a different series (50.3% for 2022-23), and mixing
// the two would draw a fall that is only a change of method. Later the same
// day: "add a bike share line to this graph? And make the axis regular and
// even, draw a y axis, but plot the survey dates accurately". The 2018 point
// was the goal's starting figure, not a tally, so it left the line.

import fs from "node:fs";
import path from "node:path";
import { Plot, plotSVG, frame, label, yGrid, xLabels } from "./plot.mjs";

const DATA = path.join(import.meta.dirname, "..", "data");
export const school = JSON.parse(fs.readFileSync(path.join(DATA, "school-car-share.json"), "utf8"));
// SFMTA's all-trips survey, quoted in the note under the chart.
const mode = JSON.parse(fs.readFileSync(path.join(DATA, "mode-share.json"), "utf8"));
export const lastSurvey = mode.surveys[mode.surveys.length - 1];
const S = school.series, last = S[S.length - 1], G = school.goal;
// Labels take two significant figures, so 48.6 shows as 49. Bike labels
// print the most precise figure SFMTA published for each tally (bikeText).
const pct = (v) => `${Math.round(v)}%`;

// Travel modes are an unordered set, so each takes its own hue; every line is
// also named where it ends, so colour is never the only key. Car, the share
// the goal is about, takes the darkest. Walk's figures sit under its points,
// because in 2019-20 it was one point below transit.
const MODES = [
  { key: "car", name: "Family car", tone: "var(--grey-dark)", text: (r) => pct(r.car) },
  { key: "transit", name: "Transit", tone: "#4f7cac", text: (r) => pct(r.transit) },
  { key: "walk", name: "Walk", tone: "var(--seq-3)", text: (r) => pct(r.walk), below: true },
  { key: "bike", name: "Bike", tone: "var(--seq-2)", text: (r) => r.bikeText },
];

/**
 * Shares of school trips by family car, transit, walking and bike, each tally
 * at the date it was taken on an even year axis, with the pace the 2030 goal
 * needs for family cars.
 */
export function schoolCarChart({ ask = false } = {}) {
  const x0 = 2019;
  const f = frame({ width: 480, height: 300, left: 40, right: 48, top: 44, bottom: 30, x: [x0, G.year], y: [0, 60] });
  const GOAL = { fill: "var(--seq-1)", fontWeight: 600 };
  const lines = MODES.flatMap((m) => [
    Plot.line(S, { x: "date", y: m.key, stroke: m.tone, strokeWidth: 2.5, strokeLinejoin: "round", strokeLinecap: "round" }),
    Plot.dot(S, { x: "date", y: m.key, r: 3.5, fill: m.tone }),
    Plot.text(S, { x: "date", y: m.key, text: m.text, dy: m.below ? 14 : -11, fontSize: 12, fontWeight: 600, fill: "var(--ink)" }),
    // Car's name sits under its line between the first two tallies, since the
    // goal line leaves from its last point; the others are named at their end.
    m.key === "car"
      ? label(f, f.px((S[0].date + S[1].date) / 2), f.py((S[0].car + S[1].car) / 2) + 24, m.name, { fill: m.tone, fontWeight: 600 })
      : label(f, f.px(last.date) + 12, f.py(last[m.key]) + 4, m.name, { fill: m.tone, fontWeight: 600, textAnchor: "start" }),
  ]);
  return plotSVG({
    ...f.options,
    marks: [
      ...yGrid([0, 20, 40, 60], (v) => `${v}%`),
      // The y axis line, and a tick under every year so the spacing reads as even.
      Plot.ruleX([x0], { y1: 0, y2: 60, stroke: "var(--rule)" }),
      Plot.ruleX(Array.from({ length: G.year - x0 + 1 }, (_, i) => x0 + i), { y1: 0, y2: -1.5, stroke: "var(--rule)", clip: false }),
      Plot.line([{ date: last.date, car: last.car }, { date: G.year, car: G.share }], { x: "date", y: "car", stroke: "var(--seq-1)", strokeWidth: 2, strokeDasharray: "6 4" }),
      Plot.dot([G], { x: "year", y: "share", r: 5, fill: "var(--seq-1)" }),
      // The goal is named to the right of its dot, clear of the transit and walk names.
      label(f, f.px(G.year) + 9, f.py(G.share) - 4, "Goal", { ...GOAL, textAnchor: "start" }),
      label(f, f.px(G.year) + 9, f.py(G.share) + 12, pct(G.share), { ...GOAL, textAnchor: "start" }),
      // Bryan, 2026-10-09, for the Safe School Connections comment: ask the question at the middle of the goal's path,
      // under it and to its left, clear of the car line above.
      ...(ask ? [label(f, f.px((last.date + G.year) / 2) - 4, f.py((last.car + G.share) / 2) + 18, "How do we get to the goal?", { ...GOAL, textAnchor: "end" })] : []),
      label(f, 0, 16, "Share of school trips", { fontWeight: 600, fill: "var(--ink)", textAnchor: "start", fontSize: 14 }),
      ...lines,
      xLabels([2020, 2022, 2024, 2026, 2028], String),
      xLabels([G.year], String, GOAL),
    ],
  }, {
    className: "school-car-chart",
    label: `Share of San Francisco school trips by mode, at each Travel Tally: ${S.map((r) => `${r.label} ${pct(r.car)} family car, ${pct(r.transit)} transit, ${pct(r.walk)} walk, ${r.bikeText} bike`).join("; ")}; SFMTA's goal is ${pct(G.share)} by family car by ${G.year}`,
  });
}
