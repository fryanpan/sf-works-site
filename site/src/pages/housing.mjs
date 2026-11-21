// The Housing Balance San Francisco published twice a year for a decade and
// then repealed, recomputed from open data. Built to docs/product/
// data-story-guidelines.md: finding first, one to three sourced sentences per
// section, then the graphic. Method and caveats are on /housing/about.
//
// The prose is in content/housing.html; the data is data/housing.json, written
// by scripts/collect-housing.mjs.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { Plot, plotSVG } from "../plot.mjs";

export const path = "/housing";
export const file = "housing/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Homes", line: "What share of the city's new housing was affordable, against the floor the Planning Code set." };

export const data = JSON.parse(
  fs.readFileSync(nodePath.join(import.meta.dirname, "..", "..", "data", "housing.json"), "utf8"),
);

export const n = (x) => Math.round(x).toLocaleString("en-US");
// Two significant figures, for a figure this page computes rather than quotes.
export const sf2 = (x) => Number(x.toPrecision(2));

export const LINKS = {
  s103Url: "https://sfgov.legistar.com/LegislationDetail.aspx?ID=7423230&GUID=9C3D32F7-1A6A-43E7-913C-B1ACFC59E312&FullText=1",
  repealUrl: "https://sfgov.legistar.com/LegislationDetail.aspx?ID=7423230&GUID=9C3D32F7-1A6A-43E7-913C-B1ACFC59E312",
  reportUrl: "https://sfplanning.org/sites/default/files/documents/reports/HousingBalance_20.pdf",
  sb423Url: "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240SB423",
  gc65913Url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum=65913.4",
  gc65400Url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum=65400",
};

// Full years only. The collector carries the year in progress, and nine months
// of completions read as a collapse next to full years.
export const complete = data.byYear.filter((y) => y.year <= data.period.end);
export const partial = data.byYear.find((y) => y.year > data.period.end);

// ---- Charts -----------------------------------------------------------------

// One row per year, two bars: affordable above market rate, each labelled with
// its count, the affordable share at the row's end. Horizontal so the labels
// stay readable at phone width. No legend: the caption names the two colours
// (guide 3.2).
export function yearChart() {
  const W = 400, rowH = 46, top = 26, x0 = 50, shareW = 46;
  // Room past the longest bar for its count, so "4,278" stays clear of the share column.
  const room = 40;
  const H = top + rowH * complete.length + 6;
  const max = Math.max(...complete.map((y) => Math.max(y.affordable, y.marketRate)));
  // Each row is one band of the y scale, 46 pixels tall with its centre at 23;
  // the bars and labels are placed from that centre.
  const mid = rowH / 2, base = (px, size) => px - mid - 0.32 * size;
  const bar = (key, fill, from, to) => Plot.barX(complete, { x: key, y: "year", fill, insetTop: from, insetBottom: rowH - to });
  const val = (key, at) => Plot.text(complete, { x: key, y: "year", text: (r) => n(r[key]), dx: 4, dy: base(at, 11.5), textAnchor: "start", fontSize: 11.5, fill: "var(--ink)" });
  const head = (text, anchor, dx) => Plot.text([0], { frameAnchor: anchor === "start" ? "top-left" : "top-right", text: () => text, textAnchor: anchor, dx, dy: 14 - top - 0.32 * 11, fontSize: 11, lineAnchor: "middle" });
  const first = complete[0];
  const last = complete.at(-1);
  const svg = plotSVG({
    width: W, height: H, marginLeft: x0, marginRight: shareW + 8 + room, marginTop: top, marginBottom: 6,
    x: { domain: [0, max], axis: null },
    y: { domain: complete.map((r) => r.year), padding: 0, axis: null },
    marks: [
      head("Homes completed", "start", 0),
      head("Affordable share", "end", shareW + 4 + room),
      Plot.text(complete, { y: "year", frameAnchor: "left", text: (r) => String(r.year), dx: -6, dy: base(21, 12), textAnchor: "end", fontSize: 12 }),
      bar("affordable", "var(--seq-3)", 6, 20),
      val("affordable", 17),
      bar("marketRate", "var(--seq-1)", 23, 37),
      val("marketRate", 34),
      Plot.text(complete, { y: "year", frameAnchor: "right", text: (r) => `${Math.round(r.affordableShare)}%`, dx: shareW + 4 + room, dy: base(26, 13), textAnchor: "end", fontSize: 13, fontWeight: 600, fill: "var(--ink)" }),
    ],
  }, {
    label: `Homes completed each year from ${first.year} to ${last.year}, affordable beside market rate. Affordable completions went from ${n(first.affordable)} to ${n(last.affordable)} and market-rate completions from ${n(first.marketRate)} to ${n(last.marketRate)}; the affordable share went from ${first.affordableShare}% to ${last.affordableShare}%.`,
  });
  return `<figure class="fig hb-chart">
${svg}
<figcaption class="verdict-note"><i class="hb-swatch hb-aff"></i> affordable homes and <i class="hb-swatch hb-mkt"></i> market-rate homes completed in the year, with the count beside each bar.</figcaption>
</figure>`;
}

// Distance to the state's line: the 50% the 2027 reading asks for is drawn as
// the zero line at the right and each category's bar runs left by its
// shortfall in points (guide 4.6). The two lines above each bar carry the
// category, then the count and the denominator.
export function sb423Chart(sb) {
  const W = 400, rowH = 60, top = 28;
  const H = top + rowH * sb.categories.length + 4;
  const mid = rowH / 2, base = (px, size) => px - mid - 0.32 * size;
  // x is the share permitted, so a bar runs from the category's share to the
  // line; its length is the shortfall in points.
  const svg = plotSVG({
    width: W, height: H, marginLeft: 10, marginRight: 6, marginTop: top, marginBottom: 4,
    x: { domain: [0, sb.sharePct], axis: null },
    y: { domain: sb.categories.map((c) => c.label), padding: 0, axis: null },
    marks: [
      Plot.text([0], { frameAnchor: "top-right", text: () => `${sb.sharePct}% of allocation, the ${sb.checkYear} line`, textAnchor: "end", dy: 14 - top - 0.32 * 11, fontSize: 11, lineAnchor: "middle" }),
      Plot.ruleX([sb.sharePct], { stroke: "var(--ink)", strokeWidth: 1.5, insetTop: -6, insetBottom: -2 }),
      Plot.text(sb.categories, { x: "pct", y: "label", text: "label", dy: base(12, 12), textAnchor: "start", fontSize: 12, fontWeight: 600, fill: "var(--ink)" }),
      Plot.text(sb.categories, { x: "pct", y: "label", text: (c) => `${c.pct}% permitted, ${n(c.permitted)} of ${n(c.rhna)}`, dy: base(26, 12), textAnchor: "start", fontSize: 12 }),
      Plot.barX(sb.categories, { x1: "pct", x2: sb.sharePct, y: "label", fill: "var(--seq-2)", insetTop: 31, insetBottom: rowH - 49 }),
      Plot.text(sb.categories, { x: sb.sharePct, y: "label", text: (c) => `${n(c.shortBy)} permits short`, dx: -6, dy: base(44, 11.5), textAnchor: "end", fontSize: 11.5, fontWeight: 600, fill: "var(--paper)" }),
    ],
  }, {
    label: `${sb.categories.map((c) => `${c.label}: ${c.pct}% of its allocation permitted, ${n(c.shortBy)} permits short of the ${sb.sharePct}% line`).join("; ")}.`,
  });
  return `<figure class="fig hb-chart">
${svg}
</figure>`;
}

const CSS = `<style>
.hb-chart svg { max-width: 560px; margin: 0; }
.hb-swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; vertical-align: -1px; margin-right: 2px; }
.hb-swatch.hb-aff { background: var(--seq-3); }
.hb-swatch.hb-mkt { background: var(--seq-1); }
</style>`;

export function yearTable() {
  return `<div class="scroll"><table>
  <thead><tr>
    <th>Year</th><th class="num">Affordable</th><th class="num">Market rate</th>
    <th class="num">All completions</th><th class="num">Affordable share</th>
  </tr></thead>
  <tbody>${complete
    .map(
      (y) => `<tr>
    <td>${y.year}</td>
    <td class="num">${n(y.affordable)}</td>
    <td class="num">${n(y.marketRate)}</td>
    <td class="num">${n(y.net)}</td>
    <td class="num">${y.affordableShare}%</td>
  </tr>`,
    )
    .join("")}</tbody>
</table></div>`;
}

export function districtTable() {
  return `<div class="scroll"><table>
  <thead><tr>
    <th>District</th><th class="num">Balance</th><th class="num">Affordable</th>
    <th class="num">Lost</th><th class="num">Net new</th>
  </tr></thead>
  <tbody>${data.byDistrict
    .map(
      (d) => `<tr>
    <td>D${d.district}</td>
    <td class="num"><strong>${String(d.balance).replace("-", "−")}%</strong></td>
    <td class="num">${n(d.affordable)}</td>
    <td class="num">−${n(d.lost)}</td>
    <td class="num">${n(d.net)}</td>
  </tr>`,
    )
    .join("")}</tbody>
</table></div>`;
}

export function sb423Table(sb) {
  return `<div class="scroll"><table>
  <thead><tr>
    <th>Category</th>
    <th class="num">Permits</th><th class="num">Allocation</th>
    <th class="num">So far</th>
    <th class="num">Short</th>
  </tr></thead>
  <tbody>${sb.categories
    .map(
      (c) => `<tr>
    <td>${c.label}</td>
    <td class="num">${n(c.permitted)}</td>
    <td class="num">${n(c.rhna)}</td>
    <td class="num">${c.pct}%</td>
    <td class="num">${n(c.shortBy)}</td>
  </tr>`,
    )
    .join("")}</tbody>
</table></div>`;
}

// Every number the two content files can name, in one place, so the About page
// and the overview cannot disagree.
export function vars() {
  const o = data.official;
  const r = data.recomputed;
  const he = data.housingElement;
  const sb = data.sb423;
  const above = sb.categories.at(-1);
  const peak = complete.reduce((a, b) => (b.marketRate > a.marketRate ? b : a));
  const pivot = complete[complete.indexOf(peak) + 1] ?? peak;
  const first = complete[0];
  const last = complete.at(-1);
  const totAff = complete.reduce((s, y) => s + y.affordable, 0);
  const totNet = complete.reduce((s, y) => s + y.net, 0);
  const r20 = data.report20;
  const lostBy = Object.fromEntries(data.lostByYear.map((x) => [x.year, x.lost]));
  const bmrGap = complete
    .map((y) => ({ ...y, gap: Math.abs(y.affordableByBmrYear - y.affordable) }))
    .reduce((a, b) => (b.gap > a.gap ? b : a));
  const worst = data.byDistrict.reduce((a, b) => (b.balance < a.balance ? b : a));
  const best = data.byDistrict.reduce((a, b) => (b.balance > a.balance ? b : a));
  const negative = data.byDistrict.filter((d) => d.balance < 0).length;
  return {
    r20From: r20.from,
    r20To: r20.to,
    r20Affordable: n(r20.affordableCompleted),
    r20Lost: n(r20.protectedUnitsLost),
    r20Net: n(r20.netCompleted),
    r20Balance: r20.completedOnlyBalance,
    r20Ellis: n(r20.lostByGround.ellis_act_withdrawal),
    r20Omi: n(r20.lostByGround.owner_move_in),
    r20PermittedAffordable: n(r20.affordablePermitted),
    r20PermittedNet: n(r20.netPermitted),
    r20PermittedShare: sf2((100 * r20.affordablePermitted) / r20.netPermitted),
    r20CompletedShare: sf2((100 * r20.affordableCompleted) / r20.netCompleted),
    oursAffordable: n(r20.recomputed.affordable),
    oursLost: n(r20.recomputed.lost),
    oursNet: n(r20.recomputed.net),
    oursBalance: r20.recomputed.balance,
    oursEllis: n(r20.recomputed.lostByGround.ellis_act_withdrawal),
    oursOmi: n(r20.recomputed.lostByGround.owner_move_in),
    lost2019: n(lostBy[2019] ?? 0),
    lost2020: n(lostBy[2020] ?? 0),
    lost2021: n(lostBy[2021] ?? 0),
    demolitionNotices: n(data.demolitions.notices),
    negativeNetRows: n(data.demolitions.negativeNetRows),
    negativeNetUnits: n(data.demolitions.negativeNetUnits),
    bmrGapYear: bmrGap.year,
    bmrGapCompletion: n(bmrGap.affordable),
    bmrGapBmr: n(bmrGap.affordableByBmrYear),
    worstDistrict: worst.district,
    worstBalance: String(worst.balance).replace("-", "−"),
    bestDistrict: best.district,
    bestBalance: best.balance,
    negativeDistricts: negative,
    ...LINKS,
    queriedAt: data.queriedAt,
    productionThrough: data.coverage.production.through,
    aprThrough: data.coverage.apr,
    partialYear: partial ? partial.year : "",
    floor: data.floor,
    balance: r.balance,
    periodStart: data.period.start,
    periodEnd: data.period.end,
    withoutPublicHousing: o.withoutPublicHousing,
    withPublicHousing: o.withPublicHousing,
    report: o.report,
    published: o.published,
    period: o.period,
    affordableUnits: n(r.affordableUnits),
    protectedUnitsLost: n(r.protectedUnitsLost),
    netNewUnits: n(r.netNewUnits),
    grossShare: sf2((100 * totAff) / totNet),
    affordableTotal: n(totAff),
    netTotal: n(totNet),
    firstAffordableShare: first.affordableShare,
    firstYear: first.year,
    lastAffordableShare: last.affordableShare,
    lastYear: last.year,
    firstAffordable: n(first.affordable),
    lastAffordable: n(last.affordable),
    firstMarketRate: n(first.marketRate),
    lastMarketRate: n(last.marketRate),
    shareIfAffordableOnly: sf2((100 * last.affordable) / (last.affordable + first.marketRate)),
    shareIfMarketOnly: sf2((100 * first.affordable) / (first.affordable + last.marketRate)),
    marketRatePeak: n(peak.marketRate),
    marketRatePeakYear: peak.year,
    pivotYear: pivot.year,
    pivotAffordable: n(pivot.affordable),
    pivotMarketRate: n(pivot.marketRate),
    total: n(he.total),
    endYear: he.endYear,
    affordable: n(he.affordable),
    startYear: he.startYear,
    netCompleted: n(he.netCompleted),
    shareOfTarget: he.shareOfTarget,
    affordableCompleted: n(he.affordableCompleted),
    shareOfAffordableTarget: he.shareOfAffordableTarget,
    checkYear: sb.checkYear,
    sharePct: sb.sharePct,
    abovePct: above.pct,
    aboveShortBy: n(above.shortBy),
    aboveModerateMultiple: (above.shortBy / above.permitted).toFixed(0),
  };
}

export const SOURCES = [
  {
    label: "Housing Production 2005–present (xdht-4php) — completions by project",
    href: "https://data.sf.gov/d/xdht-4php",
    read: data.queriedAt,
    through: data.coverage.production.through,
  },
  {
    label: "Eviction Notices (5cei-gny5) — protected-unit grounds",
    href: "https://data.sf.gov/d/5cei-gny5",
    read: data.queriedAt,
    through: data.coverage.evictions.through,
  },
  {
    label: `${data.official.report}, San Francisco Planning — the last official figure`,
    href: LINKS.reportUrl,
    read: `${data.official.published}, covering ${data.official.period}`,
  },
  {
    label: "Government Code §65913.4, as amended by SB 423 (Wiener, 2023) — §65913.4(m)(12)(B) names San Francisco",
    href: LINKS.gc65913Url,
    read: "2026-09-19",
  },
  {
    label: "Government Code §65400(a)(2)(H) — the annual production report the determination reads",
    href: LINKS.gc65400Url,
    read: "2026-09-19",
  },
  {
    label: "Streamlined Ministerial Approval Process Determination Methodology, California HCD — the eighth-per-year schedule for San Francisco",
    href: "https://www.hcd.ca.gov/sites/default/files/docs/planning-and-community/smap-determination-methodology.pdf",
    read: "2026-09-19",
  },
  {
    label: "6th Cycle RHNA Progress Report, California HCD — permits issued by jurisdiction and income category",
    href: "https://data.ca.gov/dataset/rhna-progress-report",
    read: data.queriedAt,
    through: data.coverage.apr,
  },
  {
    label: "Board File 250630, Planning Code §103 as repealed by Ordinance 137-26",
    href: LINKS.repealUrl,
    read: "2026-09-18",
  },
];

export function render() {
  const v = vars();
  return page({
    title: "How far San Francisco's new housing fell below its own affordable floor",
    description:
      `${v.balance}% of the net new homes San Francisco completed from ${v.periodStart} to ${v.periodEnd} were affordable, ` +
      `against the 33% floor its Planning Code set until 2026. Recomputed from open data; the city's own last reading was ${v.withoutPublicHousing}%.`,
    path,
    about: { href: "/housing/about", label: "About the Data" },
    validThrough: data.validThrough,
    body:
      CSS +
      content("housing", {
        ...v,
        yearChart: yearChart(),
        sb423Chart: sb423Chart(data.sb423),
        districtTable: districtTable(),
      }),
    sources: SOURCES,
  });
}
