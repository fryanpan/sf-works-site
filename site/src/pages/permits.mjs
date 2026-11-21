import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { esc } from "../html.mjs";

export const path = "/permits";
export const file = "permits/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Permits", line: "How long a building permit's first plan review takes, and how much of that is waiting in a queue." };

const data = JSON.parse(
  fs.readFileSync(
    nodePath.join(import.meta.dirname, "..", "..", "data", "permits.json"),
    "utf8",
  ),
);

const n = (x) => Math.round(x).toLocaleString();

function stationTable() {
  const d = data.planReview;
  const row = (s, strong) => `<tr>
    <td>${strong ? "<strong>" : ""}${esc(s.station)}${strong ? "</strong>" : ""}<br>
      <span class="verdict-note">${esc(s.department)}</span></td>
    <td class="num">${n(s.n)}</td>
    <td class="num">${s.queue.p50}</td>
    <td class="num">${s.queue.p90}</td>
    <td class="num">${s.review.p50}</td>
    <td class="num">${s.review.p90}</td>
    <td class="num">${s.overTargetPct}%</td>
  </tr>`;

  return `<div class="scroll"><table>
  <thead><tr>
    <th>Desk</th><th class="num">Reviews</th>
    <th class="num">Wait, median</th><th class="num">Wait, 1 in 10</th>
    <th class="num">Review, median</th><th class="num">Review, 1 in 10</th>
    <th class="num">Past ${d.targetDays} days</th>
  </tr></thead>
  <tbody>
    ${d.stations.map((s) => row(s)).join("")}
    ${row({ ...d.everyShownDesk, station: "Every desk above", department: "together" }, true)}
  </tbody>
</table></div>`;
}

function cohortTable() {
  const c = data.planReview.cohorts;
  return `<div class="scroll"><table>
  <thead><tr>
    <th>Filed</th>
    <th class="num">Wait, median</th><th class="num">Wait, 1 in 10</th>
    <th class="num">Review, median</th>
    <th class="num">Done in ${data.planReview.cohortWindowDays}d</th>
  </tr></thead>
  <tbody>${c
    .map(
      (y) => `<tr>
    <td>${y.year}${y.year === new Date().getUTCFullYear() ? " <span class=\"verdict-note\">part year</span>" : ""}</td>
    <td class="num">${y.queue.p50}</td>
    <td class="num">${y.queue.p90}</td>
    <td class="num">${y.review.p50}</td>
    <td class="num">${y.keptPct}%</td>
  </tr>`,
    )
    .join("")}</tbody>
</table></div>`;
}

function typeTable() {
  return `<div class="scroll"><table>
  <thead><tr>
    <th>Permit type</th><th class="num">Issued</th>
    <th class="num">Median</th><th class="num">1 in 10</th><th class="num">Slowest</th>
  </tr></thead>
  <tbody>${data.onlineSystem.types
    .map(
      (t) => `<tr>
    <td>${esc(t.type)}${
      t.targeted
        ? ` <span class="tag tag-ok">${data.onlineSystem.targetBizDays}-day target</span>`
        : ""
    }</td>
    <td class="num">${n(t.n)}</td>
    <td class="num">${t.p50}</td>
    <td class="num">${t.p90}</td>
    <td class="num">${t.max}</td>
  </tr>`,
    )
    .join("")}</tbody>
</table></div>`;
}

export function render() {
  const pr = data.planReview;
  const os = data.onlineSystem;
  const all = pr.everyShownDesk;
  const worst = pr.stations[0];
  const cohorts = pr.cohorts;
  // The current year is still filling, so the narrative compares complete years.
  // The partial year stays in the table, labelled there.
  const thisYear = new Date().getUTCFullYear();
  const last = cohorts.filter((c) => c.year < thisYear).at(-1);
  // The year the wait broke: the first cohort at or under two days.
  const turn = cohorts.find((c) => c.queue.p50 <= 2);
  // A pre-break cohort, for the completion-share comparison.
  const mid = cohorts.find((c) => c.year === turn.year - 2) ?? cohorts[0];
  // The decade before the wait started falling, which is the period the prose
  // describes as steady. Taking every cohort before the break instead would
  // fold the 2020-2023 decline into the "steady" range and make the sentence
  // after it, about the wait then falling, describe a fall already counted.
  const DECADE_END = 2020;
  const tenYears = cohorts.filter((c) => c.year < DECADE_END);
  const range = (rows, pick) => ({
    min: Math.min(...rows.map(pick)),
    max: Math.max(...rows.map(pick)),
  });
  const tens = {
    ...range(tenYears, (c) => c.queue.p50),
    p90Months: Math.round(Math.max(...tenYears.map((c) => c.queue.p90)) / 30),
    review: range(tenYears, (c) => c.review.p50),
    lastYear: tenYears.at(-1).year,
  };
  // The trough between that decade and the break, so the fall has a shape
  // rather than an adjective.
  const decline = cohorts.filter(
    (c) => c.year >= DECADE_END && c.year < turn.year,
  );

  return page({
    title: "Where a permit waits",
    description:
      `San Francisco publishes one number per permit. Split into waiting and ` +
      `reviewing, ${all.overTargetPct}% of first plan reviews run past the city's own ${pr.targetDays}-day target.`,
    path,
    validThrough: data.validThrough,
    body: content("permits", {
      allOverTargetPct: all.overTargetPct,
      all: n(all.n),
      cutoff: data.cutoff,
      targetDays: pr.targetDays,
      allQueueP50: all.queue.p50,
      allReviewP50: all.review.p50,
      allQueueP90: all.queue.p90,
      allReviewP90: all.review.p90,
      turnYear: turn.year,
      // The 2010s range, derived. It was written into the prose as "two to four
      // weeks" against a series that was missing 2018 and 2019 — the two years
      // that hold the slowest waits — so the sentence understated its own top
      // end. A derived range cannot drift away from the table under it.
      tensQueueMin: tens.min,
      tensQueueMax: tens.max,
      tensQueueP90Months: tens.p90Months,
      tensLastYear: tens.lastYear,
      tensReviewMin: tens.review.min,
      tensReviewMax: tens.review.max,
      declineEndYear: decline.at(-1).year,
      declineEndQueueP50: decline.at(-1).queue.p50,
      declineReviewMax: Math.max(...decline.map((c) => c.review.p50)),
      cohortTable: cohortTable(),
      turnQueueP50: turn.queue.p50,
      lastQueueP50: last.queue.p50,
      lastQueueP90: last.queue.p90,
      lastReviewP50: last.review.p50,
      cohortWindowDays: pr.cohortWindowDays,
      midKeptPct: mid.keptPct,
      midYear: mid.year,
      lastKeptPct: last.keptPct,
      lastYear: last.year,
      minPerStation: pr.minPerStation,
      stationTable: stationTable(),
      worstStation: esc(worst.station),
      worstOverTargetPct: worst.overTargetPct,
      worstQueueP50: worst.queue.p50,
      worstReviewP50: worst.review.p50,
      worstReviewP90: worst.review.p90,
      unfinished: n(pr.unfinished),
      targetBizDays: os.targetBizDays,
      targetedTypeCount: os.targetedTypeCount,
      allTypes: os.allTypes,
      withTargetP50: os.withTarget.p50,
      withTargetP90: os.withTarget.p90,
      withTargetOverTargetPct: os.withTarget.overTargetPct,
      typeTable: typeTable(),
      stateBenchmarkRows:
        data.stateBenchmarks
            .map(
              (b) =>
                `<tr><td>${esc(b.label)}</td><td class="num">${b.days}</td><td>${esc(b.cite)}</td></tr>`,
            )
            .join(""),
    }),
    sources: [
      {
        label: "Plan Review Details (5bat-azvb) — filing, arrival and completion per review",
        href: "https://data.sf.gov/d/5bat-azvb",
        read: data.queriedAt,
        through: data.coverage.planReview.through,
      },
      {
        label: "PermitSF Records (tyz3-vt28) — the online permitting system",
        href: "https://data.sf.gov/d/tyz3-vt28",
        read: data.queriedAt,
        through: data.coverage.permitsf.through,
      },
      {
        label: "California Government Code §65913.3, added by AB 2234 (2022)",
        href: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum=65913.3",
        read: "2026-09-04",
      },
    ],
  });
}
