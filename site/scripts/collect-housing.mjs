#!/usr/bin/env node
// Build data/housing.json: the Housing Balance San Francisco published twice a
// year for a decade and then repealed, recomputed from the city's own data.
//
//   node scripts/collect-housing.mjs
//
// Planning Code §103 required Planning to publish this every April and October,
// and required the Mayor to submit a funding strategy to the Board whenever the
// Cumulative Housing Balance fell below 33%. Ordinance 137-26 repealed §103.
// Report No. 20, April 2025, was the last one: 24.9% without public housing,
// 33.5% with it, for 2015 Q1 through 2024 Q4.
//
// §103(c)(1) set the formula: the Housing Balance is the cumulative total of
// affordable units at or below 120% of area median income, minus protected units
// lost, divided by total net new housing units, across a ten-year period. The
// Cumulative measure counts units that have received a certificate of occupancy
// plus units that have obtained a site or building permit.
//
// WHERE THIS DIFFERS FROM PLANNING'S OWN NUMBER, and the page says so:
//
//  * THE PERMITTED HALF IS MISSING. §103 counts units that have a site or
//    building permit as well as units that are finished. The public production
//    dataset holds completions only — every one of its 6,146 records carries a
//    completion date — so what is recomputed here is the completed half alone,
//    Nothing on DataSF was found that carries the permitted half at this
//    resolution. Missing it does not by itself push the figure down: Report 20's
//    permitted half had a lower gross affordable share (13,669 / 49,366) than its
//    completed half (10,413 / 36,380). The recomputation reads lower because the
//    protected units lost are subtracted from the smaller, completed-only
//    denominator; Planning's own completed-only figure would be 21.1%.
//  * Planning's protected units lost come from the Rent Board too (Report 20,
//    Table 1A footnote 5: "This information is collected from the Rent Board"),
//    but its count differs from the public eviction-notice table: 2,722 for
//    2015 Q1–2024 Q4 (Table 8) against 3,145 notices on the same four grounds,
//    with Ellis Act 116 against 1,053. Planning probably counts units or drops
//    rescinded notices; the report does not say. Both figures are printed.
//  * Planning's completed affordable count is also higher than the dataset's on
//    a matching denominator: Table 1A 10,413 / 36,380 for 2015–2024 against
//    8,802 / 36,216 here. So the gap to 24.9% is not only the permitted half.
//  * The affordable column in the production dataset is flagged as an estimate
//    on some records. Planning used MOHCD's own figures.
//  * Planning's report was by quarter; this is by the dates in the dataset.
//
// So the recomputation is a check on direction and magnitude, not a replacement
// for the report. That is itself the finding: nobody outside Planning can now
// produce the number the ordinance used to turn on.

import fs from "node:fs";
import nodePath from "node:path";
import { coverageOf, validThrough } from "./lib/coverage.mjs";
import { fetchAll } from "./lib/socrata.mjs";

const ROOT = nodePath.resolve(import.meta.dirname, "..");

const FLOOR = 33; // §103(e)(1): the minimum the annual hearing measured against

// Housing Balance Report No. 20 (April 2025), 2015 Q1–2024 Q4, read 2026-09-22
// from sfplanning.org/sites/default/files/documents/reports/HousingBalance_20.pdf.
// Table 1A totals and Table 8 by BoS district; the same window is recomputed
// from the datasets below so the two can sit side by side.
const REPORT_20 = {
  from: 2015,
  to: 2024,
  affordableCompleted: 10413,
  affordablePermitted: 13669,
  protectedUnitsLost: 2722,
  netCompleted: 36380,
  netPermitted: 49366,
  lostByGround: { owner_move_in: 2535, ellis_act_withdrawal: 116, demolition: 68, condo_conversion: 3 },
  lostByDistrict: { 1: 357, 2: 191, 3: 131, 4: 341, 5: 225, 6: 78, 7: 149, 8: 340, 9: 376, 10: 226, 11: 308 },
};
const PERIOD_YEARS = 10;

// Housing Element 2023-2031 (RHNA 6th cycle), as adopted.
// The 6th-cycle planning period runs 2023-01-31 to 2031-01-31.
const ELEMENT = { total: 82069, affordable: 46598, startYear: 2023, endYear: 2031 };

// §103(c)(3)(C) counts protected units lost through owner move-in, condominium
// conversion, demolition or merger, and Ellis Act withdrawal.
const PROTECTED_GROUNDS = [
  "owner_move_in",
  "condo_conversion",
  "demolition",
  "ellis_act_withdrawal",
];

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const isTrue = (v) => v === true || v === "true";

// Pages the whole dataset and raises on a short read. A fixed $limit here was
// one row-count away from silently truncating: the eviction table stands at
// 48,987 against the 50,000 this used to ask for, and the plan-review table had
// already passed its own cap and was dropping 54,438 rows unnoticed.
const fetchDataset = (id) => fetchAll(id);

const production = await fetchDataset("xdht-4php");
const evictions = await fetchDataset("5cei-gny5");

// The balance period is the ten years ending at the last full calendar year in
// the data, which is how the report framed it.
const latestYear = Math.max(
  ...production
    .map((r) => Number((r.latest_completion_date ?? "").slice(0, 4)))
    .filter((y) => y > 2000),
);
const periodEnd = latestYear - 1; // the last year that is certainly complete
const periodStart = periodEnd - PERIOD_YEARS + 1;
const inPeriod = (y) => y >= periodStart && y <= periodEnd;

// Every one of the dataset's rows carries a completion date, so a record is
// credited to the year it completed. There is no permitted stage to credit.
const completionYear = (row) => Number((row.latest_completion_date ?? "").slice(0, 4));
const noticeYear = (row) => Number((row.file_date ?? "").slice(0, 4));
const onProtectedGround = (row) => PROTECTED_GROUNDS.some((g) => isTrue(row[g]));

const district = new Map();
const totals = { net: 0, affordable: 0, negativeNetRows: 0, negativeNetUnits: 0 };

for (const row of production) {
  const year = completionYear(row);
  if (!(year > 2000) || !inPeriod(year)) continue;

  const net = num(row.net_units_completed);
  const affordable = num(row.affordable_units);
  if (net === 0 && affordable === 0) continue;

  totals.net += net;
  totals.affordable += affordable;
  if (net < 0) {
    totals.negativeNetRows += 1;
    totals.negativeNetUnits += -net;
  }

  const d = row.supervisor_district || "unknown";
  const cur = district.get(d) ?? { net: 0, affordable: 0, lost: 0 };
  cur.net += net;
  cur.affordable += affordable;
  district.set(d, cur);
}

// Protected units lost: one per notice on the four grounds, in the period, and
// placed in the district the notice carries (all but a handful do).
let protectedLost = 0;
let demolitionNotices = 0;
const lostByYear = new Map();
for (const row of evictions) {
  const year = noticeYear(row);
  if (!inPeriod(year) || !onProtectedGround(row)) continue;
  protectedLost += 1;
  if (isTrue(row.demolition)) demolitionNotices += 1;
  lostByYear.set(year, (lostByYear.get(year) ?? 0) + 1);
  const d = row.supervisor_district || "unknown";
  const cur = district.get(d) ?? { net: 0, affordable: 0, lost: 0 };
  cur.lost += 1;
  district.set(d, cur);
}

// The same window Report 20 covers, from the same two tables, so the page can
// print the city's count beside this one.
const r20 = { affordable: 0, net: 0, lost: 0, lostByGround: Object.fromEntries(PROTECTED_GROUNDS.map((g) => [g, 0])) };
for (const row of production) {
  const y = completionYear(row);
  if (y >= REPORT_20.from && y <= REPORT_20.to) {
    r20.net += num(row.net_units_completed);
    r20.affordable += num(row.affordable_units);
  }
}
for (const row of evictions) {
  const y = noticeYear(row);
  if (y >= REPORT_20.from && y <= REPORT_20.to && onProtectedGround(row)) {
    r20.lost += 1;
    for (const g of PROTECTED_GROUNDS) if (isTrue(row[g])) r20.lostByGround[g] += 1;
  }
}

// The by-year chart places affordable units in the year of the project's
// latest completion date. The dataset also carries bmr_reporting_year, MOHCD's
// own year for projects that complete across years; the ten-year total is the
// same either way, but single years move, and the largest move is recorded so
// the About page can name it.
const byBmrYear = new Map();
for (const row of production) {
  const y = Number(row.bmr_reporting_year);
  if (!(y > 2000)) continue;
  byBmrYear.set(y, (byBmrYear.get(y) ?? 0) + num(row.affordable_units));
}

const balance = (aff, lost, net) => (net > 0 ? (100 * (aff - lost)) / net : 0);

// Completions by year, so the page can show what moved and what did not. The
// affordable share is the figure people quote, and it has two halves that have
// moved in opposite directions, so both go in.
const byYear = new Map();
for (const row of production) {
  const y = Number((row.latest_completion_date ?? "").slice(0, 4));
  if (!(y > 2000)) continue;
  const cur = byYear.get(y) ?? { net: 0, affordable: 0 };
  cur.net += num(row.net_units_completed);
  cur.affordable += num(row.affordable_units);
  byYear.set(y, cur);
}

const cycle = [...byYear]
  .filter(([y]) => y >= ELEMENT.startYear)
  .reduce(
    (t, [, v]) => ({ net: t.net + v.net, affordable: t.affordable + v.affordable }),
    { net: 0, affordable: 0 },
  );

// ---- SB 423: what the state actually measures, and when ----------------
//
// Gov. Code s65913.4(m)(12)(A) gives every other jurisdiction two reporting
// periods -- the first half and the last half of the RHNA cycle -- so the
// midpoint check on the 2023-2031 cycle lands in 2027. (B) carves San
// Francisco out by name: "reporting period" means ANNUALLY for the City and
// County of San Francisco. SB 423 (Wiener, 2023) wrote that subparagraph.
//
// So SF has no 2027 checkpoint. HCD's own determination methodology ratchets
// the bar an eighth per year -- 1/8 after the 2023 APRs, 2/8 after 2024, and
// so on -- and the 2027 determination is the ordinary 4/8. The measure is
// BUILDING PERMITS ISSUED, by income category, from the production report
// s65400(a)(2)(H) requires by April 1 each year. Missing it in the
// above-moderate category, or in very low OR low, forces the city to approve
// qualifying projects ministerially.
//
// The progress figures come from HCD's own file rather than the city's, for
// the same reason the page cites the ordinance and not an article about it:
// this is the series the determination is made on.
const RHNA_PROGRESS_CSV =
  "https://data.ca.gov/dataset/ff082e96-72f7-4443-9747-8b8dadc15671/" +
  "resource/1e80a9cf-724c-432d-8374-e9708a6a92dc/download/rhna_progress_6.csv";
const SMAP_FIRST_APR_YEAR = 2023; // 1/8 threshold applies after these APRs
const SMAP_CYCLE_YEARS = 8;

async function fetchRhnaProgress() {
  const res = await fetch(RHNA_PROGRESS_CSV);
  if (!res.ok) throw new Error(`RHNA progress: HTTP ${res.status}`);
  const text = await res.text();
  const lines = text.trim().split(/\r?\n/);
  const head = lines[0].split(",").map((h) => h.trim());
  const row = lines.slice(1).find((l) => l.split(",")[0].trim() === "SAN FRANCISCO");
  if (!row) throw new Error("RHNA progress: no SAN FRANCISCO row");
  const cells = row.split(",");
  if (cells.length !== head.length) {
    throw new Error(`RHNA progress: ${cells.length} cells, expected ${head.length}`);
  }
  const r = Object.fromEntries(head.map((h, i) => [h, cells[i].trim()]));
  const cat = (label, unitsKey, rhnaKey) => ({
    label,
    permitted: Number(r[unitsKey]),
    rhna: Number(r[rhnaKey]),
  });
  return {
    planningPeriod: r["Planning Period"],
    categories: [
      cat("Very low", "VLI UNITS", "RHNA VLI"),
      cat("Low", "LI UNITS", "RHNA LI"),
      cat("Moderate", "MOD UNITS", "RHNA MOD"),
      cat("Above moderate", "ABOVE MOD UNITS", "RHNA ABOVE MOD"),
    ],
  };
}

const rhna = await fetchRhnaProgress();

// The check worth running: HCD's category totals must reconcile with the
// Housing Element figures this page already carries. If they ever stop
// matching, one of the two is wrong and the page should not build.
const rhnaTotal = rhna.categories.reduce((t, c) => t + c.rhna, 0);
if (rhnaTotal !== ELEMENT.total) {
  throw new Error(`RHNA categories sum to ${rhnaTotal}, Housing Element says ${ELEMENT.total}`);
}
const lowerTotal = rhna.categories
  .filter((c) => c.label !== "Above moderate")
  .reduce((t, c) => t + c.rhna, 0);
if (lowerTotal !== ELEMENT.affordable) {
  throw new Error(`lower-income RHNA sums to ${lowerTotal}, page says ${ELEMENT.affordable}`);
}

// The 2027 determination reads the 2026 APRs, the fourth of the cycle, so the
// bar is 4/8. Derived from the APR year rather than written down, so the page
// stays right as the cycle advances.
const smapYear = 2027;
const eighths = smapYear - SMAP_FIRST_APR_YEAR;
const smapShare = eighths / SMAP_CYCLE_YEARS;

// How far forward this page reaches. Three inputs, and they stop at different
// times: the two DataSF tables reload continuously, while HCD's permit counts
// are assembled once a year out of reports filed each April. The annual file is
// the one that binds, because the SB 423 section is built on it.
const productionCoverage = coverageOf(production, {
  eventFields: ["latest_completion_date", "issued_date"],
});
const evictionCoverage = coverageOf(evictions, { eventFields: ["file_date"] });

// HCD's 6th-cycle file is built from Annual Progress Reports, which are due each
// April for the preceding calendar year. The most recent complete APR year is
// therefore the last full year before the file was published, and the counts
// cannot reach into the current one.
// This is the filing calendar, not a field in the file: HCD's CSV carries no
// APR-year column, so whether the latest year's reports are in is not checked.
const aprCoverage = `${new Date().getUTCFullYear() - 1}-12-31`;

const valid = validThrough([
  {
    label: "HCD permit counts, from Annual Progress Reports",
    through: aprCoverage,
    why:
      `The state's permit counts are assembled from reports filed each April for ` +
      `the previous calendar year, so they stop at the end of that year. A permit ` +
      `issued since then is not in the SB 423 figures, however recently the file ` +
      `was published.`,
  },
  {
    label: "Housing Production",
    through: productionCoverage.through,
    binding: false,
    why: "Completions are recorded up to here.",
  },
  {
    label: "Eviction Notices",
    through: evictionCoverage.through,
    binding: false,
    why: "Notices are recorded up to here.",
  },
]);

const out = {
  queriedAt: new Date().toISOString().slice(0, 10),
  validThrough: valid,
  coverage: { production: productionCoverage, evictions: evictionCoverage, apr: aprCoverage },
  period: { start: periodStart, end: periodEnd },
  floor: FLOOR,
  official: {
    // Planning's own last published figures, which this does not replace.
    report: "Housing Balance Report No. 20",
    published: "2025-04",
    period: "2015 Q1 – 2024 Q4",
    withoutPublicHousing: 24.9,
    withPublicHousing: 33.5,
  },
  recomputed: {
    balance: Number(balance(totals.affordable, protectedLost, totals.net).toFixed(1)),
    affordableUnits: totals.affordable,
    protectedUnitsLost: protectedLost,
    netNewUnits: totals.net,
    // Not a zero: the public dataset does not carry permitted-but-unbuilt units,
    // so this half of the ordinance's measure cannot be reconstructed at all.
    permitted: null,
    coversCompletedHalfOnly: true,
  },
  byDistrict: [...district]
    .filter(([d]) => d !== "unknown")
    .map(([d, v]) => ({
      district: Number(d),
      net: v.net,
      affordable: v.affordable,
      lost: v.lost,
      affordableShare: v.net > 0 ? Number(((100 * v.affordable) / v.net).toFixed(1)) : 0,
      balance: v.net > 0 ? Number(balance(v.affordable, v.lost, v.net).toFixed(1)) : 0,
    }))
    .sort((a, b) => a.district - b.district),
  lostByYear: [...lostByYear].sort((a, b) => a[0] - b[0]).map(([year, lost]) => ({ year, lost })),
  demolitions: { notices: demolitionNotices, negativeNetRows: totals.negativeNetRows, negativeNetUnits: totals.negativeNetUnits },
  report20: {
    ...REPORT_20,
    recomputed: {
      affordable: Math.round(r20.affordable),
      net: Math.round(r20.net),
      lost: r20.lost,
      lostByGround: r20.lostByGround,
      balance: Number(balance(r20.affordable, r20.lost, r20.net).toFixed(1)),
    },
    // Planning's own figure with only the completed half, for the like-for-like line.
    completedOnlyBalance: Number(
      balance(REPORT_20.affordableCompleted, REPORT_20.protectedUnitsLost, REPORT_20.netCompleted).toFixed(1),
    ),
  },
  byYear: [...byYear]
    .filter(([y]) => y >= 2016)
    .sort((a, b) => a[0] - b[0])
    .map(([year, v]) => ({
      year,
      net: Math.round(v.net),
      affordable: Math.round(v.affordable),
      affordableByBmrYear: Math.round(byBmrYear.get(year) ?? 0),
      marketRate: Math.round(v.net - v.affordable),
      affordableShare: v.net > 0 ? Number(((100 * v.affordable) / v.net).toFixed(1)) : 0,
    })),
  sb423: {
    planningPeriod: rhna.planningPeriod,
    checkYear: smapYear,
    eighths,
    sharePct: Number((100 * smapShare).toFixed(0)),
    // The APR year the 2027 determination reads.
    aprYear: smapYear - 1,
    categories: rhna.categories.map((c) => ({
      ...c,
      pct: Number(((100 * c.permitted) / c.rhna).toFixed(1)),
      needBy: Math.ceil(smapShare * c.rhna),
      shortBy: Math.max(0, Math.ceil(smapShare * c.rhna) - c.permitted),
    })),
    permittedTotal: rhna.categories.reduce((t, c) => t + c.permitted, 0),
    rhnaTotal,
  },
  housingElement: {
    ...ELEMENT,
    netCompleted: Math.round(cycle.net),
    affordableCompleted: Math.round(cycle.affordable),
    shareOfTarget: Number(((100 * cycle.net) / ELEMENT.total).toFixed(1)),
    shareOfAffordableTarget: Number(
      ((100 * cycle.affordable) / ELEMENT.affordable).toFixed(1),
    ),
  },
};

const dest = nodePath.join(ROOT, "data/housing.json");
fs.writeFileSync(dest, JSON.stringify(out, null, 1));
console.log(
  `housing: ${out.period.start}–${out.period.end} balance ${out.recomputed.balance}% ` +
    `against a ${FLOOR}% floor (city's last published figure ${out.official.withoutPublicHousing}%) ` +
    `→ ${nodePath.relative(ROOT, dest)}`,
);
