// Survey Results on What People Want: the published survey results from four
// of San Francisco's Community-Based Transportation Plans, MTC's planning
// program for low-income communities (Equity Priority Communities).
//
// Bryan, 2026-11-17, on the whitepaper draft's section on what people in
// Equity Priority Communities care about: "let's move this content into a
// subpage on the sf-works site titled 'Survey Results on What People Want'".
//
// The prose is content/transportation-what-people-want.md. The numbers are
// data/community-plans/survey-results.json, read by hand from each plan's own
// document (the read date is in the file). Each result carries the
// subcategory and group (Safety or Convenience) we put it in; the summary
// grid is built from those, so it can't disagree with the plan charts.
//
// The page goes through the markdown page renderer (src/md-pages.mjs), so it
// reads like the site's other markdown pages, and its charts are the board's
// <PlotChart> specs drawn by src/md-components.mjs. It is a module rather than
// a page under content/ with front matter only so it can carry a `listing`.
//
// Charts are drawn narrow (420 to 450 px) because a static SVG scales down as
// a whole on a phone; at this width the labels stay about 11 px at 390 wide.

import fs from "node:fs";
import nodePath from "node:path";
import { renderPage, lastUpdated, CONTENT } from "../md-pages.mjs";
import { plotChartHTML } from "../md-components.mjs";
import { esc } from "../html.mjs";

export const path = "/transportation/what-people-want";
export const file = "transportation/what-people-want/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = {
  title: "Survey Results on What People Want",
  line: "What residents asked for in four neighborhood transportation plans' surveys: safer crossings, lighting and more Muni.",
  parent: "section",
  order: 3,
};

const TITLE = "Survey Results on What People Want";
const PROSE = "transportation-what-people-want.md";
const DATA_FILE = nodePath.join(import.meta.dirname, "..", "..", "data", "community-plans", "survey-results.json");
export const D = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));

const COLOR = { domain: ["Safety", "Convenience"], range: ["#efb118", "#4269d0"] };
const STYLE = { fontFamily: "inherit", color: "#59626f" };
const INK = "#15181c";
const groupOf = new Map(D.subcategories.map((s) => [s.k, s.g]));

/**
 * Each item's rank within its own survey: 1 + how many items did strictly
 * better, so tied items share a rank. Bayview's average rank is better when
 * lower; every other measure is better when higher.
 */
export function ranked(plan) {
  const better = plan.order === "low" ? (a, b) => a < b : (a, b) => a > b;
  return plan.items.map((it) => ({ ...it, g: groupOf.get(it.sub), rank: 1 + plan.items.filter((o) => better(o.v, it.v)).length }));
}

// The summary grid: one row per subcategory under its group's heading, one
// column per plan. A star is a subcategory with an item in that survey's top
// 3; a dot is one whose best item ranked lower.
export function gridSpec() {
  const SH = " ";
  const CH = "  ";
  const subs = D.subcategories;
  const cols = D.plans.map((p) => p.column);
  const grid = subs.flatMap((s) => cols.map((c) => ({ s: c, k: s.k })));
  const top = [];
  const ten = [];
  for (const s of subs) {
    for (const p of D.plans) {
      const items = ranked(p).filter((it) => it.sub === s.k);
      if (!items.length) continue;
      const best = Math.min(...items.map((it) => it.rank));
      const t = `${p.name}: ${items.map((it) => `${it.k} (#${it.rank})`).join("; ")}`;
      (best <= 3 ? top : ten).push({ s: p.column, k: s.k, g: s.g, t, m: best <= 3 ? "★" : "●" });
    }
  }
  const h = [{ k: SH, t: "Safety" }, { k: CH, t: "Convenience" }];
  const domain = [SH, ...subs.filter((s) => s.g === "Safety").map((s) => s.k), CH, ...subs.filter((s) => s.g === "Convenience").map((s) => s.k)];
  const left = 186;
  return {
    title: "Across Four Neighborhood Plans, Crossings, Lighting, Transit Safety and Muni Service Each Rank Top 3 Twice",
    data: { grid, top, ten, h },
    marks: [
      { mark: "cell", data: "grid", options: { x: "s", y: "k", fill: "#f1f2f4", inset: 1.5 } },
      { mark: "text", data: "top", options: { x: "s", y: "k", text: "m", fill: "g", fontSize: 20, title: "t" } },
      { mark: "text", data: "ten", options: { x: "s", y: "k", text: "m", fill: "g", fontSize: 15, title: "t" } },
      { mark: "text", data: "h", options: { y: "k", frameAnchor: "left", text: "t", dx: -left + 2, textAnchor: "start", fontSize: 13, fontWeight: 600, fill: INK } },
    ],
    options: {
      style: { ...STYLE, fontSize: "12px" },
      width: 430, height: 430, marginLeft: left, marginRight: 4, marginTop: 40, marginBottom: 4, fontSize: 12,
      color: COLOR,
      x: { axis: "top", label: null, domain: cols, tickSize: 0, padding: 0, tickPadding: 6 },
      y: { label: null, domain, tickSize: 0, padding: 0 },
    },
  };
}

// One plan's chart: bars for a share or a count, dots alone for Bayview's
// average rank (a line out from 1 would make the lowest priority the longest), each mark coloured by its group and carrying its value.
export function planSpec(plan) {
  const a = ranked(plan).map((it) => ({ k: it.k, v: it.v, g: it.g, lab: `${it.v}${plan.suffix}` }));
  const keys = a.map((r) => r.k);
  const rows = a.length;
  const height = 44 + rows * 24;
  const label = { fontSize: 12, fill: INK, textAnchor: "start" };
  const marks =
    plan.measure === "rank"
      ? [
          { mark: "dot", data: "a", options: { y: "k", x: "v", r: 5, fill: "g" } },
          { mark: "text", data: "a", options: { y: "k", x: "v", text: "lab", dx: 8, ...label } },
        ]
      : [
          { mark: "barX", data: "a", options: { y: "k", x: "v", fill: "g" } },
          { mark: "text", data: "a", options: { y: "k", x: "v", text: "lab", dx: 5, ...label } },
          { mark: "ruleX", data: "z", options: { x: "_v" } },
        ];
  return {
    title: plan.title,
    data: { a, z: [{ _v: 0 }] },
    marks,
    options: {
      style: STYLE,
      width: 450, height, marginLeft: 190, marginRight: 30, marginTop: 6, marginBottom: 36, fontSize: 12,
      color: COLOR,
      x: { label: plan.x_label, labelAnchor: "left", labelArrow: false, domain: plan.domain, ticks: plan.ticks, grid: true, tickSize: 0, ...(plan.measure === "rank" ? { tickFormat: "d" } : {}) },
      y: { label: null, domain: keys, tickSize: 0 },
    },
  };
}

const link = (href, text) => `<a href="${esc(href)}">${esc(text)}</a>`;

// The line under a plan's chart: the plan's own document, the page the
// figures are on, how many responded and when.
export function sourceLine(plan) {
  const doc = plan.survey_url
    ? `${esc(plan.agency)}, ${link(plan.survey_url, plan.survey_doc)} (${esc(plan.source_page)}) of the ${link(plan.plan_url, plan.plan)} (${esc(plan.plan_year)})`
    : `${esc(plan.agency)}, ${link(plan.plan_url, plan.plan)} (${esc(plan.plan_year)}), ${esc(plan.source_page)}`;
  const n = plan.n_note.startsWith('"') ? `${esc(plan.n_note)}` : `${plan.n.toLocaleString("en-US")} ${esc(plan.n_note)}`;
  return `<p class="chart-source">Source: ${doc}. ${n}, ${esc(plan.dates)}.</p>`;
}

const GRID_KEY = `<p class="chart-source">★ in that survey's top 3. ● ranked lower. Yellow is safety, blue is convenience. The rows are our grouping of each plan's own items. Sources are under each plan's chart below.</p>`;

const CSS = `<style>
.md-page .chart-source { font-size: 0.85rem; color: var(--muted); margin: -8px 0 20px; }
.md-page .md-chart svg text { paint-order: stroke; }
</style>`;

/** The page body: the prose with its charts filled in. */
export function body() {
  const blocks = { grid: plotChartHTML(gridSpec(), PROSE) + "\n\n" + GRID_KEY };
  for (const p of D.plans) blocks[p.id] = plotChartHTML(planSpec(p), PROSE) + "\n\n" + sourceLine(p);
  const values = { mtcUrl: D.mtc_program, vvPlanUrl: D.plans.find((p) => p.id === "visitacion-valley").plan_url };
  const text = fs.readFileSync(nodePath.join(CONTENT, PROSE), "utf8").replace(/\r/g, "");
  const missing = [];
  const out = text.replace(/\{\{(#?)\s*([\w-]+)\s*\}\}/g, (_, block, key) => {
    const v = block ? blocks[key] : values[key];
    if (v == null) missing.push(key);
    return v == null ? "" : block ? v : esc(v);
  });
  if (missing.length) throw new Error(`content/${PROSE} refers to ${missing.join(", ")}, which the page does not supply`);
  return `${out}\n${CSS}`;
}

export function render() {
  const src = nodePath.join(CONTENT, PROSE);
  const { date } = lastUpdated(src);
  return renderPage({
    root: CONTENT,
    src: PROSE,
    path,
    file,
    front: {
      title: TITLE,
      summary: "Published survey results from four San Francisco Community-Based Transportation Plans, in Visitacion Valley and Portola, Lake Merced, Bayview and the Western Addition.",
    },
    body: body(),
    status: "published",
    updated: date,
  });
}
