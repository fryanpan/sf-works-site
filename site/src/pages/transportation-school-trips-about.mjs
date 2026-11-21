// About School Trips: how the one simulation works, how each change is modelled
// and why, what kids hurt look like in the crash data, and the checks it passes.
//
// The plan's "How We Show It's Good Enough" (scratch/2026-10-08-school-tool-
// one-simulation-plan.md): calibrated to the Travel Tally by grade, tested
// against data it wasn't fit to (SFCTA's 2016 car share by distance), placed
// against SFUSD's home ZIP counts. Bryan, 2026-10-12, on this page: "I was
// expecting this to include all of the content that explains how we simulated
// each intervention and why and the evidence." So each change has its own
// short section, and its figures are computed here at build time by the same
// makeCityModel the tool runs (site/src/school-trips-model.mjs), in the sim's
// central case with its low and high, so the page and the tool can't disagree. The checks
// are read from site/data/school-sim/index.json (tools/school-trips/school-sim.py), and
// the crash charts from site/data/school-kids-hurt.json.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { PLAN_URL } from "../transportation.mjs";
// SFMTA's 2023 Draft Bike Comfort Index map, which the all-ages rule's BCI threshold reads (as transportation-about.mjs).
const BCI_MAP_URL = "https://tooledesign.maps.arcgis.com/apps/webappviewer/index.html?id=f948aa0022e246259ea899e5a4318427";
import { esc } from "../html.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import { COSTS } from "./transportation-school-trips.mjs";
import { makeCityModel, readEbikeGate } from "../school-trips-model.mjs";
import { figure } from "../figures.mjs";

export const path = "/transportation/school-trips/about";
export const file = "transportation/school-trips/about/index.html";

const DATA = nodePath.join(import.meta.dirname, "..", "..", "data");
const SIM = nodePath.join(DATA, "school-sim", "index.json");
const has = fs.existsSync(SIM);
const readIf = (p) => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : null);
const IX = has ? JSON.parse(fs.readFileSync(SIM, "utf8")) : null;
// tools/school-trips/school-sim-rules.py: each school's School Connector price and the students free Muni reaches.
const RULES = readIf(nodePath.join(DATA, "school-sim", "rules.json")) || {};
const CITY = readIf(nodePath.join(DATA, "school-sim", "city.json"));
const HURT = readIf(nodePath.join(DATA, "school-kids-hurt.json"));
const GRAV = readIf(nodePath.join(DATA, "school-gravity.json"));
// tools/school-trips/school-budget-plans.mjs: the budget plans, their table and the checks on it.
const PLANS = readIf(nodePath.join(DATA, "school-budget-plans.json"));

// The Scenarios section's plan paragraphs, with the plans' own figures. Balanced divides each goal by what that goal's
// own plan reaches at the same budget; the sentence on why not today's totals quotes the two shares at $20M.
function scenariosHtml() {
  const P = PLANS, n0 = (x) => Math.round(x).toLocaleString("en-US"), f1 = (x) => (Math.round(x * 10) / 10).toFixed(1);
  if (!P) return "<p>Today has no changes. The budget plans aren't in this build yet.</p>";
  const b = P.budgets.includes(20) ? 20 : P.budgets[0], car = P.plans[`car${b}`].at.central, saf = P.plans[`safety${b}`].at.central;
  const ec = Object.values(P.exactCheck || {}), worstGap = ec.length ? Math.max(...ec.map((x) => Math.max(0, x.gapPct))) : null;
  const rc = P.replanCheck;
  return `<p>Today has no changes. Best for Car Mode Shift, Best for Safety and Balanced are plans for one budget, $${P.budgets[0]}M to $${P.budgets[P.budgets.length - 1]}M over 4 years, that pays for the school changes and the new bikeways together. A budget a year is the yearly cost plus the one-time cost spread over 4 years.</p>
<p>Each plan starts with nothing funded and keeps adding whichever change, at whichever school, does the most per dollar until the budget runs out. Best for Car Mode Shift counts kids out of single-family cars, Best for Safety kids hurt prevented, and Balanced adds the two with equal weight, each divided by what that goal's own plan reaches at the same budget, so 1 is the best we found for that goal. A change counts only if it gets at least 1 student out of a car or prevents 0.01 kids hurt a year, so a plan that runs out of such changes spends less than its budget.</p>
<p>The new bikeways are one citywide step with ${P.budgets.length} sizes, the sets under New Bikeways below, and a plan moves to a bigger set when its gain per dollar beats the next school change's, so the plan itself splits the budget between bikeways and schools. Carpool matching and school zone speed limits are citywide steps too, at every school or none. A change only counts at a school if it takes at least one student out of a car or prevents at least a hundredth of a kid hurt a year, and a shuttle loop needs at least 25 riders. Each reach of the walking upgrades is its own choice, so a school can go straight to a quarter mile. Every reach is priced by the school's own intersections, and one near two schools is paid for at both. The plans are picked at our central estimates, in the central case. Every plan uses the Neighborhood + Citywide Programs assignment the Board adopted on 13 October 2026, as it stands in 2030-31 with 52% of TK-5 students under it. It costs nothing and on its own takes about ${n0(alone("assign_ncp52").cars[1])} kids out of single-family cars and prevents ${(alone("assign_ncp52").hurt[1]).toFixed(1)} kids hurt a year, so part of each plan's figures is the assignment. Choosing another option under Advanced Controls moves a plan's figures by the two options' own difference.</p>
<p>A plan is picked from a table of every change at every school scored on its own${worstGap == null ? "" : worstGap < 0.05 ? ", which does as well as a slower pick that rescores every move with the rest of the plan in place" : `, which comes within ${f1(worstGap)}% of a slower pick that rescores every move with the rest of the plan in place`}. Under Advanced Controls, each change has a switch for whether the plans may use it. Turning one off picks the plan again in your browser from the same table, and moves its figures by the table's difference between the two plans${rc ? `, which we checked against exact scores for all ${rc.cases} plans with one change off: within ${f1(rc.carsMaxPct)}% on kids out of cars and ${(rc.hurtMaxAbs ?? 0).toFixed(2)} kids hurt a year` : ""}.</p>`;
}

const TALLY = "https://www.sfsaferoutes.org/documents/2026/SFSRTS_Report_final_spreads_low_res.pdf";
const CTS = "https://www.sfcta.org/sites/default/files/2019-03/Child_Transportation_FINAL.pdf";
const SAP = "https://www.sfcta.org/sites/default/files/2024-07/SF_School_Access_Plan_Report_2023-05-04_FINAL.pdf";
const SSC = "https://www.sfmta.com/safe-school-connections-draft-approach-september-2026";
const AREAS = "https://data.sfgov.org/d/e6tr-sxwg";
const DASH = "https://public.tableau.com/views/SFUSDPublicDataDashboard/Story1";
const CDE = (GRAV && GRAV.inputs && GRAV.inputs.cde && GRAV.inputs.cde.url) || "https://www3.cde.ca.gov/demo-downloads/census/cdenroll2526.txt";
const STUDY2 = "https://go.boarddocs.com/ca/sfusd/Board.nsf/pfiles/DXE3RY083148/$file/School%20Reorg%20Study%20Session%20%232%20%28FINAL%2C%208.28.26%29.pdf";
const L = {
  guards: "https://www.sfmta.com/blog/prioritizing-safety-schools-citywide-update-our-crossing-guard-program",
  hampshire: "https://democracy.hants.gov.uk/documents/s116625/School%20Streets.pdf",
  monterey: "https://www.sfcta.org/sites/default/files/2025-03/Monterey%20Boulevard%20Pedestrian%20Safety%20Improvement%20ARF.pdf",
  ab43: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=VEH&sectionNum=22358.9",
  ab645: "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB645",
  kokka: "https://pmc.ncbi.nlm.nih.gov/articles/PMC11187370/",
  cmf134: "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=134",
  tester: "https://pubmed.ncbi.nlm.nih.gov/15054019/",
  nycCam: "https://a860-gpp.nyc.gov/downloads/m039k943r?locale=en",
  sfmtaCam: "https://www.sfmta.com/media/40836/download",
  bizData: "https://data.sfgov.org/d/g8m3-pdis",
  streetsData: "https://data.sfgov.org/d/3psu-pn9h",
  limitsData: "https://data.sfgov.org/d/3t7b-gebn",
  humpsData: "https://data.sfgov.org/d/abhw-ffzx",
  camData: "https://data.sfgov.org/d/d5uh-bk84",
  contraCosta: "https://ops.fhwa.dot.gov/publications/mitig_traf_cong/contra_costa_case.htm",
  ppssf: "https://www.ppssf.org/news/2025/2/19/access-at-risk-the-implications-of-cutting-school-buses-in-sfusd",
  denverRebate: "https://bikeportland.org/2023/03/06/what-we-can-learn-from-denvers-e-bike-rebate-program-371026",
  sfmta2012: "https://archives.sfmta.com/cms/apress/MayorLeeSFMTAandWalkSFAnnounceNewSaferSpeedZonesCompletedaround181SanFranciscoSchools.htm",
  boardVote: "https://sfstandard.com/2026/10/14/sfusd-board-votes-neighborhood-school-plan/",
  boardVoteML: "https://missionlocal.org/2026/10/san-francisco-school-board-new-elementary-enrollment-policy/",
  study1: "https://go.boarddocs.com/ca/sfusd/Board.nsf/pfiles/DWXUGV7C0C49/$file/School%20Reorg%20Study%20Session%20%231%20(Final%208.13.26).pdf",
  tiebreakers: "https://www.sfusd.edu/schools/enroll/student-assignment-policy/tiebreakers",
  cdeGrades: "https://dq.cde.ca.gov/dataquest/dqcensus/EnrGrdLevels.aspx?cds=3868478&agglevel=district&year=2024-25",
  patterson: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12964863/",
  johnson: "https://pmc.ncbi.nlm.nih.gov/articles/PMC11083767/",
  mendoza: "https://nutrition-evidence.com/article/160599/the-walking-school-bus-and-childrens-physical-activity-a-pilot-cluster-randomized-controlled-trial",
  mcdonald: "https://mcdonald.web.unc.edu/wp-content/uploads/sites/8583/2014/12/McDonald_etal_ImpactsSRTS_JAPA2014.pdf",
  dimaggio: "https://pmc.ncbi.nlm.nih.gov/articles/PMC3557410/",
  lpiCmf: "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=9911",
  nycdot: "https://nyc.gov/html/dot/downloads/pdf/safety-treatment-evaluation-2005-2018.pdf",
  rrfb: "https://rosap.ntl.bts.gov/view/dot/88645/dot_88645_DS1.pdf",
  boarnet: "https://escholarship.org/uc/item/3vd3g3jm",
  aldred: "https://westminsterresearch.westminster.ac.uk/item/q5890/impacts-of-an-active-travel-intervention-with-a-cycling-focus-in-a-suburban-context-one-year-findings-from-an-evaluation-of-london-s-in-progress-mini-hollands-programme",
  molenberg: "https://pmc.ncbi.nlm.nih.gov/articles/PMC6815350/",
  losgatos: "https://www.losgatosca.gov/DocumentCenter/View/22097/Student-Travel-Survey-Draft-Report-and-Appendix-A-121018",
  wales: "https://etsc.eu/wales-first-full-year-of-20-mph-default-limits-shows-early-safety-gains-and-speed-reductions/",
  elvikSpeed: "https://transport.gov.scot/media/gclirqqo/appendix-f-road-safety-accident-analysis-and-results.pdf",
  elvik: "https://doi.org/10.1016/j.ssci.2015.07.017",
  morency: "https://pmc.ncbi.nlm.nih.gov/articles/PMC5906382/",
  schoolpool: "https://cbsm.com/cases/34151-denver-s-schoolpool",
  chalkbeat: "https://www.chalkbeat.org/posts/co/2011/06/02/dps-rolling-out-success-express",
  denverite: "https://legacy.denverite.com/?p=32077",
  raleigh: "https://connect.ncdot.gov/projects/research/ResearchAnalysis/Final%20Report_TA2025-04.pdf",
  ukri: "https://www.ukri.org/news/e-cargo-bikes-can-replace-car-trips-and-reshape-family-travel/",
  ucdavis: "https://rosap.ntl.bts.gov/view/dot/66159/dot_66159_DS1.pdf",
  wow: "https://www.livingstreets.org.uk/media/ceueykb4/dch-schools-final_report_20_10_23.pdf",
  elevate: "https://eprints.whiterose.ac.uk/id/eprint/232325/1/preprints202503.0726.v1.pdf",
  dundee: "https://www.dundeecity.gov.uk/sites/default/files/publication_2420.pdf",
  bikebus: "https://bikeportland.org/wp-content/uploads/2024/01/A-global-survey-of-BikeBus-initiatives.pdf",
  biketrain: "https://pmc.ncbi.nlm.nih.gov/articles/PMC5894119/",
  crashes: "https://data.sfgov.org/d/ubvf-ztfx",
  ab382: "https://legiscan.com/CA/text/AB382/2025",
  kokka: "https://pmc.ncbi.nlm.nih.gov/articles/PMC11187370/",
  streets: "https://sph.uth.edu/research/centers/dell/resources/streets/Hoelscher-Salvo%20STREETS%20Healthier%20TX%20Summit%202025-10-02.pdf",
  barcelona: "https://road-safety-charter.ec.europa.eu/sites/default/files/good_practice/supporting_files/Perez%20-%20SRTS%20-%20ajph.2022.307216.pdf",
  cdc: "https://stacks.cdc.gov/view/cdc/43928",
  grundy: "https://europepmc.org/article/PMC/PMC2791801",
  cordoba: "https://helvia.uco.es/handle/10396/27616",
  trb: "https://www.nationalacademies.org/read/10409/chapter/2",
  contracosta: "https://ops.fhwa.dot.gov/publications/mitig_traf_cong/contra_costa_case.htm",
  pittsburgh: "https://ombonu.github.io/discounted_fares_study.pdf",
  mybus: "http://web.archive.org/web/20120215032521/http://www2.dft.gov.uk//pgr/sustainable/schooltravel/yellowschoolbus/doc/phase1.doc",
  teschke: "https://pmc.ncbi.nlm.nih.gov/articles/PMC3519333/",
  lavoie: "https://www.canada.ca/en/public-health/services/reports-publications/health-promotion-chronic-disease-prevention-canada-research-policy-practice/vol-34-no-4-2014/active-safe-transportation-elementary-school-students.html",
  victims: "https://data.sfgov.org/d/nwes-mmgh",
};
const a = (url, text) => `<a href="${url}">${text}</a>`;

const n0 = (x) => Math.round(x).toLocaleString("en-US");
const p0 = (x) => (x == null ? "n/a" : `${Math.round(x)}%`);
const h1 = (x) => (Math.abs(x) < 0.005 ? "0" : Math.abs(x) < 0.1 ? x.toFixed(2) : x.toFixed(1));
const trio = (v, f) => `${f(v[0])}, ${f(v[1])} or ${f(v[2])}`;
const money = (m) => (m >= 0.95 ? `$${m.toFixed(1)}M` : `$${n0(Math.round(m * 1000) * 1000)}`);
// A cost row's rate as a reader would say it: "$1.5M a mile", "$2,072 a rider a year".
const rate = (c) => (c.unit.startsWith("$M") ? `$${c.v}M${c.unit.slice(2)}` : c.unit.startsWith("$") ? `$${n0(c.v)}${c.unit.slice(1)}` : `${c.v} ${c.unit}`);
const GRADES = ["TK", "KN", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];
const GRADE = { TK: "TK", KN: "K", "01": "1st", "02": "2nd", "03": "3rd", "04": "4th", "05": "5th", "06": "6th", "07": "7th", "08": "8th", "09": "9th", "10": "10th", "11": "11th", "12": "12th" };

// The tool's model, run here on the same inputs, so every figure on this page is the tool's own central case.
const COST = Object.fromEntries(Object.entries(COSTS).map(([k, c]) => [k, c.v]));
const SCH0 = IX ? IX.schools.map((s) => ({ cds: s.cds, ranges: Object.fromEntries(Object.entries(s.ranges || {}).map(([k, r]) => [k, { n: r.students }])), calmFt: s.calmFt, calmed: !!s.calmed })) : [];
// figures-ok: the model's inputs and counts only (N_K5, XEFF, HB, ...); every figure comes from figures.json.
const MD = CITY && IX ? makeCityModel(CITY, {
  schools: SCH0, rules: { ...RULES, injury: HURT && HURT.model, gate: readEbikeGate(nodePath.join(DATA, "school-sim"), CITY, SCH0) }, cost: COST,
}) : null;
// Each change's figures are the registry's (site/data/figures.json, written by tools/school-trips/school-trips-figures.mjs), in
// the sim's three cases, so this page can't print a number the tool or another page computed differently. MD stays
// for the model's inputs and counts.
figure("school-trips.case");
const INJ = (HURT && HURT.model) || {};
const TODAY0 = CITY ? CITY.sets[MD.TODAY] : null;
const CAR0 = TODAY0 ? TODAY0[0] : 0, STUDENTS = CITY ? CITY.students : 0, CAR_PCT = STUDENTS ? 100 * CAR0 / STUDENTS : null;
const alone = (id) => figure(`school-trips.alone.${id}`);

// One change's results, central first in the tool's order of low, central, high.
function results(id) {
  const x = alone(id), same = x.cars[2] - x.cars[0] < 0.5;
  const cars = x.cars[2] < 0.5 ? "takes nobody out of a single-family car" : same ? `takes ${n0(x.cars[1])} kids out of single-family cars, with no range` : `takes ${trio(x.cars, n0)} kids out of single-family cars`;
  // A change can add kids hurt, when its new walkers or riders carry more risk than the car trips they leave.
  const hurt = x.hurt.some((v) => v <= -0.005)
    ? `kids hurt a year change by ${trio(x.hurt.map((v) => (v <= -0.005 ? `${h1(-v)} more` : `${h1(v)} fewer`)), String)}`
    : `there are ${trio(x.hurt, h1)} fewer kids hurt a year`;
  return `At our low, central and high, it ${cars}, and ${hurt}.`;
}
const budget = (id) => { const x = alone(id); return x.year + x.once / 4; };

const CSS = `<style>
.ta { max-width: 1000px; }
.ta h1 { font-size: clamp(1.4rem, 2.4vw, 1.8rem); margin: 0 0 6px; }
.ta h2 { font-size: 1.15rem; margin: 30px 0 4px; }
.ta h3 { font-size: 1rem; margin: 22px 0 2px; }
.ta p, .ta li { max-width: 88ch; }
.ta ul.ch { padding-left: 18px; margin: 4px 0 0; }
.ta ul.ch li { margin-bottom: 4px; }
.ta table { font-size: 0.86rem; border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; margin-top: 6px; }
.ta td, .ta th { padding: 5px 10px 5px 0; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top; }
.ta .r { text-align: right; }
.ta .scroll { overflow-x: auto; }
.ta .find { font-weight: 600; margin: 12px 0 2px; }
.ta .note { font-size: 0.8rem; color: var(--muted); margin: 0 0 8px; }
.ta .plot-chart { max-width: 560px; }
.ta .plot-chart.bars { max-width: 520px; }
</style>`;

// ---------- charts ----------

// Car share by grade: the Tally's measured grades as solid dots, the grades filled in between them hollow, and the
// grades held at a measured value (TK at K, 10th to 12th at 9th) on a dashed line.
function gradeChart(c) {
  const rows = GRADES.map((g) => ({ g: GRADE[g], v: c.byGrade[g].target, kind: c.byGrade[g].kind, n: c.byGrade[g].students }));
  const tip = (d) => `${d.g}: ${Math.round(d.v)}% of ${n0(d.n)} students, ${d.kind}`;
  const meas = rows.filter((d) => d.kind === "measured"), rest = rows.filter((d) => d.kind !== "measured");
  const line = { x: "g", y: "v", stroke: "var(--seq-3)", strokeWidth: 2 };
  return plotSVG({
    width: 500, height: 230, marginLeft: 38, marginRight: 10, marginTop: 24, marginBottom: 28,
    style: { fontSize: "13px" },
    x: { type: "point", domain: rows.map((d) => d.g), label: null, tickSize: 0, padding: 0.3 },
    y: { domain: [0, 64], ticks: [0, 20, 40, 60], tickFormat: (v) => `${v}%`, label: null, grid: true, tickSize: 0 },
    marks: [
      Plot.ruleY([0], { stroke: "var(--rule)" }),
      Plot.line(rows.slice(1, 11), line),
      Plot.line(rows.slice(0, 2), { ...line, strokeDasharray: "4 4" }),
      Plot.line(rows.slice(10), { ...line, strokeDasharray: "4 4" }),
      Plot.dot(rest, { x: "g", y: "v", r: 3.5, fill: "var(--paper)", stroke: "var(--seq-3)", strokeWidth: 1.5, title: tip }),
      Plot.dot(meas, { x: "g", y: "v", r: 5.5, fill: "var(--seq-3)", title: tip }),
      Plot.text(meas, { x: "g", y: "v", text: (d) => `${Math.round(d.v)}%`, dy: -14, fontWeight: 700, fill: "var(--ink)" }),
      Plot.text([rows[0]], { x: "g", y: "v", text: () => "held at K", dy: 16, textAnchor: "start", dx: -6, fill: "var(--muted)" }),
      Plot.text([rows[12]], { x: "g", y: "v", text: () => "held at 9th grade", dy: 18, fill: "var(--muted)" }),
    ],
  }, { label: "Single-family car share by grade, TK to 12th" });
}

// Horizontal bars, each printing its own figure, then a smaller second figure after it.
function bars(rows, { fill, big, small, label, width = 480, ml = 160, mr = 90 }) {
  const mx = Math.max(...rows.map((d) => d.v));
  return plotSVG({
    width, height: 36 * rows.length + 12, marginLeft: ml, marginRight: mr, marginTop: 6, marginBottom: 6,
    style: { fontSize: "13px" },
    x: { domain: [0, mx], axis: null },
    y: { domain: rows.map((d) => d.lab), label: null, tickSize: 0, padding: 0.22 },
    marks: [
      Plot.barX(rows, { x: "v", y: "lab", fill }),
      Plot.ruleX([0], { stroke: "var(--ink)" }),
      Plot.text(rows, { x: "v", y: "lab", text: big, dx: 6, textAnchor: "start", fontWeight: 700, fill: "var(--ink)", fontSize: 14 }),
      // The second figure sits after the first, offset by the first's printed width.
      ...rows.map((d) => Plot.text([d], { x: "v", y: "lab", text: small, dx: 12 + 8.4 * big(d).length, textAnchor: "start", fill: "var(--muted)", fontSize: 12 })),
    ],
  }, { label, className: "bars" });
}

// Kids hurt by street type and distance from the grounds, one cell per pair, shaded by its count on one teal ramp
// (Bryan, 2026-10-13: "a heat map by main street vs. residential and distance (500 ft, 1/4 mile, farther)").
function hurtGrid(D, total) {
  const cells = D.streets.flatMap((st, i) => D.bands.map((b, j) => ({ st, b, n: D.grid[i][j] })));
  const mx = Math.max(...cells.map((c) => c.n));
  return plotSVG({
    width: 480, height: 40 * D.streets.length + 34, marginLeft: 150, marginRight: 4, marginTop: 30, marginBottom: 4,
    style: { fontSize: "13px" },
    x: { domain: D.bands, axis: "top", label: null, tickSize: 0 },
    y: { domain: D.streets, label: null, tickSize: 0 },
    color: { type: "linear", domain: [0, mx], range: ["#eef5f4", "#2f7d76"] },
    marks: [
      Plot.cell(cells, { x: "b", y: "st", fill: "n", inset: 1.5 }),
      Plot.text(cells, { x: "b", y: "st", text: (c) => n0(c.n), dy: -6, fontWeight: 700, fontSize: 14, fill: (c) => (c.n > 0.55 * mx ? "#fff" : "var(--ink)") }),
      Plot.text(cells, { x: "b", y: "st", text: (c) => p0(100 * c.n / total), dy: 9, fontSize: 11, fill: (c) => (c.n > 0.55 * mx ? "#fff" : "var(--muted)") }),
    ],
  }, { label: "Kids hurt by street type and distance from the nearest school's grounds", className: "bars" });
}

function hurtCharts() {
  if (!HURT) return "";
  const D = HURT.byDistance, M = HURT.byMode, B = HURT.bellRate;
  const dT = D.rows.reduce((t, r) => t + r.n, 0), zone = D.rows[0].n, near = D.rows[0].n + D.rows[1].n;
  const mainNear = D.grid[0][0] + D.grid[0][1];
  const mT = M.rows.reduce((t, r) => t + r.n, 0), car = M.rows.find((r) => r.mode === "In a car").n;
  const bell = B.rows[0], other = B.rows[1], ratio = bell.per1000h / other.per1000h;
  const read = (HURT.source.match(/\d{4}-\d{2}-\d{2}/) || [""])[0];
  const ds = `${a(L.victims, "Traffic Crashes Resulting in Injury: Victims Involved")}, DataSF, read ${read}`;
  return `<p class="find">${n0(near)} of the ${n0(dT)} kids hurt on SF weekdays were within a quarter mile of a school's grounds, and ${n0(mainNear)} of those on a main street.</p>
<p>That's about ${n0(dT / D.years)} kids aged 5 to 18 a year. ${n0(zone)} were inside the 500 ft school zone, where the 15/20 mph limits apply.</p>
${hurtGrid(D, dT)}
<p class="note">Kids aged 5 to 18 hurt in traffic on weekdays, 6 am to 6 pm, August to May, school years 2021-22 to 2024-25. Distance runs from the crash to the nearest grounds of the tool's schools, public, charter and private, measured from the edge of the grounds as California's school-zone law measures it (Vehicle Code §22352). Main means either street is tertiary or above in OpenStreetMap. ${D.noLocation} with no location are left out. Source: ${ds}.</p>

<p class="find">${n0(car)} of the ${n0(mT)} kids hurt on SF weekdays were riding in a car.</p>
<p>A kid who leaves a car for a school bus or Muni changes their own risk as well as the traffic around them, so the shuttle loops and free Muni cut injuries beyond the cars they remove.</p>
${bars(M.rows.map((r) => ({ lab: r.mode, v: r.n })), { fill: "var(--grey-light)", big: (d) => n0(d.v), small: (d) => p0(100 * d.v / mT), label: "Kids hurt on SF weekdays by how they were travelling" })}
<p class="note">The same kids. A car includes drivers aged 16 to 18. Other includes scooters and motorcycles. Source: ${ds}.</p>

<p class="find">Near schools, kids walking and biking are hurt about ${Math.round(ratio)} times as often in bell hours as at other daytime hours.</p>
<p>The city's crashes peak in the afternoon anyway, and for kids walking and biking, the bell hours still run ${B.vsCityClock.toFixed(1)} times what that clock predicts. That's why the speed limits and walking upgrades act near schools.</p>
${bars(B.rows.map((r) => ({ lab: r.when, v: r.per1000h * 100, n: r.n })), { fill: (d) => (d.lab === "Bell hours" ? "var(--seq-3)" : "var(--grey-light)"), big: (d) => d.v.toFixed(1), small: (d) => `${n0(d.n)} kid${d.n === 1 ? "" : "s"}`, label: "Kids hurt walking or biking near schools per 100,000 hours", ml: 150, mr: 80 })}
<p class="note">Crashes hurting a child walking or biking within 600 feet of a school's grounds, per 100,000 hours, at 207 schools on school days 2022-23 to 2025-26. Bell hours run from 45 minutes before the start bell to 15 after, and from 15 minutes before the end bell to 45 after, at each school's own SFUSD bell times (8:15 am and 3:15 pm where SFUSD lists none). Other daytime is 6 am to 8 pm outside them, and bell hours with no school are the same clock times on weekdays when school is out. A crash near two schools counts at both. Source: ${a(L.crashes, "Traffic Crashes Resulting in Injury")} and ${a(L.victims, "its victims")}, DataSF.</p>
<p class="note">The maps' heat layer, off until you turn it on, shows kids 5 to 18 hurt within a quarter mile of a school's grounds on weekdays from 6 am to 6 pm, August to May, school years 2005-06 to 2024-25, one point per kid. The maps outline each school's 500 ft zone round its grounds. Source: ${ds}.</p>`;
}

// ---------- tables ----------

function distance(c) {
  const d = c.byDistance, m = d.model, t = d.cts2016;
  const row = (k, lab) => `<tr><td>${lab}</td><td class="r">${p0(t[k])}</td><td class="r">${p0(m[k])}</td><td class="r">${p0(m.studentsPct[k])}</td></tr>`;
  return `<table><thead><tr><th>Distance from home</th><th class="r">Driven, 2016 survey</th><th class="r">Driven, model</th><th class="r">Model's K-5 students at this distance</th></tr></thead><tbody>${row("under1", "Under 1 mile")}${row("1to2", "1 to 2 miles")}${row("over2", "Over 2 miles")}</tbody></table>`;
}

function costTable() {
  const rows = Object.entries(COSTS).filter(([k]) => !["ssStaff", "busRiders"].includes(k));
  return `<div class="scroll"><table><thead><tr><th>Change</th><th class="r">Cost</th><th>Where it comes from</th></tr></thead><tbody>${rows.map(([, x]) => `<tr><td>${esc(x.label)}</td><td class="r">${esc(rate(x))}</td><td>${x.src.charAt(0).toUpperCase() + x.src.slice(1)}.</td></tr>`).join("")}</tbody></table></div>`;
}

// ---------- each change ----------

function change(title, b) {
  const li = (k, v) => (v ? `<li><b>${k}:</b> ${v}</li>` : "");
  return `<h3>${title}</h3><ul class="ch">${li("What it is", b.what)}${li("Who it reaches", b.who)}${li("How we model it", b.how)}${li("Why", b.why)}${li("Evidence", b.ev)}${li("Cost", b.cost)}</ul>`;
}

function changes() {
  const cs = COSTS, nK5 = MD.N_K5, nK8 = MD.N_K8, nSigns = MD.N_SIGNS;
  const calmB = ((CITY.calming || {}).budgets || {})["10"] || {}, ssA = alone("school_street");
  const conn = alone("connector"), nConn = Object.keys(RULES.connector || {}).length;
  const segs = (CITY.segments || []).map((s) => ({ ...s, x: alone(`seg${s.budgetM}`) }));
  const muniFar = Math.round((RULES.muniFar || 0) / 100) * 100;
  const yb = alone("yellow_bus"), wb = alone("walking_bus"), cp = alone("carpool"), mu = alone("caregiver_muni");
  const ncp = alone("assign_ncp52"), ncpFull = alone("assign_ncp");
  const fr = (x) => trio(x.free, n0);
  const out = [];

  out.push(change("15/20 mph School Zone Speed Limits", {
    what: `a lower posted limit on the streets within 500 feet of each school while children are present, which ${a(L.ab382, "AB 382")} lets the city set. It's a tool in ${a(SSC, "SFMTA's draft")}.`,
    who: `all ${nSigns} schools, and the kids hurt inside those zones while the limit applies, at any grade.`,
    how: `kids hurt within 500 feet of the school grounds while the limit applies fall 10%, range 5% to 25%. That's ${n0(INJ.zoneKidsYear)} kids a year in the zone, ${p0(100 * INJ.zoneHours)} of them from 7 to 9 am or 2 to 5 pm. It moves nobody out of a car, since a lower limit doesn't make a street safe to bike. ${results("calm")}`,
    why: `speed sets how hard a car hits. Across studies of urban roads, cutting mean speed from 25 to 20 mph predicts about 23% fewer injury crashes (${a(L.elvikSpeed, "Elvik 2009, reproduced by Transport Scotland")}, Table F-1).`,
    ev: `${a(L.kokka, "Edinburgh's 20 mph limit")} cut casualties 10% on the changed streets against unchanged ones, with mean speed down 1.3 mph. In ${a(L.wales, "Wales")}, casualties fell 26.2% on roads that went to a 20 mph default, which sets our high. Both were limits on whole areas at every hour, and a school zone's limit applies only part of the day, so we apply the cut only inside the zone while it does.`,
    cost: `about 12 signs a school, one at each street entering a zone that reaches a quarter mile, at $650 a sign: ${rate(cs.calmPerSchool)}, range $2,000, the 4.4 signs a school SFMTA posted for its 2012 school zones (${a(L.sfmta2012, "SFMTA, 2012")}), to $16,000. That's ${money(alone("calm").once)} once at ${nSigns} schools. Cameras aren't priced.`,
  }));

  out.push(change("School Street Activation", {
    what: `the block in front of an elementary school closes to cars at drop-off and pickup. It's a tool in ${a(SSC, "SFMTA's draft")}.`,
    who: `TK-5 students at the ${nK5} schools with TK-5 grades, since its study covered primary schools.`,
    how: `each school's TK-5 single-family car share falls 2.7 points, range 0 to 5.3, and those trips move to the other ways of getting there in proportion. Fewer cars cut kids hurt near schools at the bells. The car-free block gets no extra credit yet, since no study has counted injuries on one. ${results("school_street")}`,
    why: `it's the one controlled study. Of its 5.40-point drop in car trips, 2.68 points were park-and-stride, where the family still drives and walks the last block or two. The Travel Tally has no answer for that, so those kids would still count as driven here, and we take the other 2.7.`,
    ev: `${a(L.patterson, "Patterson et al. 2025")} compared 166 UK primary schools, 125 of them in London, with similar schools nearby. Car share fell 5.3 points (2.5 to 8.2) in its abstract, three years before against one year after. Our TK-5 car share is about 55%, so the same points are a smaller relative drop here.`,
    cost: `${rate(cs.schoolStreet)}, range $13,500 to $60,000: two staff, one at each end of the block, 1.5 hours a day for 180 days, at the $56 an hour ${a(L.guards, "SFMTA's crossing guards")} cost. Set-up is ${rate(cs.ssSetup)}, from ${a(L.hampshire, "Hampshire's School Streets")}' £12,000 to £15,000. That's ${money(ssA.year)} a year and ${money(ssA.once)} once.`,
  }));

  // Safety upgrades' cut at each reach, by how kids travelled (tools/school-trips/school-kids-hurt.py's reach).
  const REACH = INJ.reach || {}, XE = MD.XEFF;
  const xeff = (m) => `${Math.round(100 * XE[m][1])}% (${Math.round(100 * XE[m][0])}% to ${Math.round(100 * XE[m][2])}%)`;
  const reachTable = () => {
    const rows = [[350, "1 block", "safer_crossings"], [660, "2 blocks", "xing660"], [1320, "1/4 mile", "xing1320"]].map(([f, l, id]) => {
      const m = REACH[f].modes, x = alone(id), bm = x.byMode, yr = x.year + x.once / 4;
      const kids = (k) => h1((m[k] || 0) / INJ.years);
      return `<tr><th scope="row">${l}</th><td>${kids("Walking")}</td><td>${h1(((m.Biking || 0) + (m["Scooter or other"] || 0)) / INJ.years)}</td><td>${kids("In a car")}</td>`
        + `<td>${h1(bm.Walking)}</td><td>${h1(bm.Biking + bm["Scooter or other"])}</td><td>${h1(bm["In a car"])}</td><td>${h1(x.hurt[1])}</td><td>${money(x.once)}</td></tr>`;
    }).join("");
    return `<div class="scroll"><table><thead><tr><th>Reach</th><th>Kids hurt a year, walking</th><th>Biking or scooter</th><th>In a car</th>`
      + `<th>Fewer walking</th><th>Fewer biking</th><th>Fewer in a car</th><th>Fewer in all, with calming and fewer cars</th><th>One-time cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  };
  out.push(change("Safety Upgrades for Walking", {
    what: `bulbouts, raised crosswalks and flashing beacons at the intersections near schools where at least one street is a main street, a tool in ${a(SSC, "SFMTA's draft")}. A main street is one OpenStreetMap ranks tertiary or above, the same test the crash chart sorts kids by. Corners where both streets are residential are left to calming, our addition: humps and diverters on the residential streets within 660 feet of the grounds of each school a $10M calming budget reaches.`,
    who: `TK-8 students at the ${nK8} schools with TK-8 grades, the grades its study covered. Calming reaches ${calmB.schools || 0} schools, taken in order of kids hurt within 660 feet over the last 10 school years.`,
    how: `walking and biking rise 3.3 points among each school's TK-8 students, range 0 to 6.3, at any reach, since no study measured more for a bigger package. Calmed streets count as safe to bike, so more kids at those schools bike under each case. The upgrades reach 1 block (350 feet), 2 blocks (660 feet) or a quarter mile from the school grounds, and cut kids hurt within that reach and within ${n0(INJ.xNearFt || 150)} feet of a main street intersection they treat, by how they were travelling: ${xeff("Walking")} of kids walking, ${xeff("Biking")} of kids biking or on a scooter, and ${xeff("In a car")} of kids in a car, counted at TK-8 schools. Those cuts apply in full from 7 to 9 am and 2 to 5 pm in term, the hours the studies measured, and at ${Math.round(100 * MD.XOFF)}% the rest of the school day, our judgment, since the upgrades stay in place. Kids in a car include 16 to 18 year olds driving. ${reachTable()} Calming cuts 40% (20% to 55%) of kids hurt where both streets are residential within 660 feet of a calmed school's grounds, ${h1(calmB.residentialKidsPerYear || 0)} kids a year. ${results("safer_crossings")}`,
    why: `it's the one study we found that measured walking and biking after engineering work at schools. Three studies measured the injury cut near schools, and crash studies of the treatments themselves measured kids in cars.`,
    ev: `${a(L.mcdonald, "McDonald et al. 2014")}, p. 160, found walking and biking up 3.3 points at schools with an engineering improvement, across 801 schools in four states. It printed no interval, and its p-value puts the top near 6.3. Austin's ${a(L.streets, "STREETS study")} found no gain, so the low is 0. In ${a(L.barcelona, "Barcelona")}, child pedestrian injury collisions fell to 0.57 of before within 200 m of 64 Safe Routes schools, against 1.05 at matched schools. Barcelona's program was mostly road safety teaching, so it supports the size of the cut more than the treatments. That 200 m, about two blocks, is the only reach any study states. ${a(L.dimaggio, "DiMaggio and Li 2013")} found 44% fewer pedestrian injuries in New York City tracts picked for high injuries, and an ${a(L.cdc, "18-state study")} found 23% fewer kids hurt walking and biking together. No study measured these treatments for kids biking alone, so biking's figure is our judgment from the pooled one. For kids in cars, leading pedestrian intervals carry ${a(L.lpiCmf, "0.86 of injury crashes")} for all road users, and ${a(L.nycdot, "NYC DOT")} found 10% to 13.5% fewer car occupants hurt after curb extensions and leading intervals. Flashing beacons may add rear-end crashes (${a(L.rrfb, "FHWA 2025")}), so the low is 0, and the 12% is our judgment. London's engineered 20 mph zones cut casualties 42% (${a(L.grundy, "Grundy et al. 2009")}).`,
    cost: `${rate(cs.saferCrossings)} buys every crossing within 1 block of the average TK-8 school's grounds, range $60,000 to $290,000, between SF's ~$60,000 walk audits (${a(SAP + "#page=46", "School Access Plan")}, p. 46) and the $290,000 ${a(L.monterey, "Monterey Boulevard")} corridor. That's ${n0(REACH[350].intersectionsAll || REACH[350].intersections)} intersections citywide, and the upgrades go to the ${n0(REACH[350].intersections)} of them on a main street, so a reach costs that price in proportion to its main street intersections: ${n0(REACH[350].intersections)} within 1 block, ${n0(REACH[660].intersections)} within 2 blocks and ${n0(REACH[1320].intersections)} within a quarter mile. Intersections come from OpenStreetMap, counting only named streets that cross, with a divided street's two sides counted once. A school's own price in the school view uses its own intersections. Calming is ${rate(cs.calmStreets)}, range $5M to $20M, at $0.25M a mile, about ${n0(calmB.miles || 0)} miles. With calming, that's ${money(alone("safer_crossings").once)} once at 1 block, ${money(alone("xing660").once)} at 2 blocks and ${money(alone("xing1320").once)} at a quarter mile.`,
  }));

  out.push(change("School Connector Street", {
    what: `a link from a school's door to the nearest all-ages bikeway, separated on busier streets and calmed on residential ones. It's a tool in ${a(SSC, "SFMTA's draft")}.`,
    who: `the ${nConn} schools within 2 blocks of today's all-ages network, and the driving students at every grade whose bike trip it makes safe.`,
    how: `the shortest walk from the door to a safe run at least half a mile long counts as safe. Kids whose route it puts on the all-ages network move toward biking by the three cases under What the Model Does. We count it with School Streets on, so the block in front of the school isn't built twice. A child biking on a calmed street carries about 1.5 times a car trip's risk, and few kids switch, so it changes kids hurt by almost nothing. ${results("connector")}`,
    why: `it's how SFMTA's draft describes the connector, and the cases are the same ones every new street uses.`,
    ev: `the bike shift's cases under What the Model Does. No study measures a school connector on its own.`,
    cost: `each block at its street type's rate a mile: ${rate(cs.connectorSep)} on a main street, ${rate(cs.connectorCalm)} on a residential street. That's ${money(conn.once)} once.`,
  }));

  out.push(change("New Bikeways: $5M to $100M", {
    what: `for each budget, the set of street stretches that removes the most family-car trips to school. A stretch is about a mile of one street. It can be an unbuilt all-ages bikeway from the ${a(PLAN_URL, "Biking and Rolling Plan")}, priced at its bikeway type's rate, except that on a collector or arterial a shared street the plan draws, or an existing plan bikeway that isn't all-ages, is priced and counted as a separated lane, or any other street block: a residential block priced as calming, a collector or arterial as a separated lane, with freeways and ramps left out. SFMTA's upcoming bikeways count as built in every scenario, at no cost.`,
    who: `driving students at every grade whose trip a chosen set makes safe. A budget plan buys one set out of the same budget as its school changes.`,
    how: `an off-plan block is dropped when an all-ages street, built, upcoming or on the plan, runs within 20 degrees of its direction and within 500 feet along most of its length, except a cross street that meets the plan street or a block that continues it past its end. Each budget's set comes from an integer program that picks the whole set at once to remove the most family-car trips to school in year 10, at our central case, within the budget. It values each route by how much more likely a kid on it is to bike once the set is built, then a full route search over the chosen network checks the count. ${(() => { const g = segs.map((x) => x.checkGapPct).filter((x) => x != null); return g.length ? `The program's own count of car trips and drivers comes within ${Math.ceil(Math.max(...g))}% of that check at every budget, and the figures here are the checked ones.` : ""; })()} Each budget's set holds the one below it. The solver doesn't prove every set best, so each is the best set it found. A stretch that brings nobody within a safe ride on its own but sits on a chosen route is a bridge, drawn with a dashed outline on the map. Kids move to biking by the same three cases as every new street. At our low, central and high, the kids out of single-family cars are ${segs.map((s) => `${trio(s.x.cars, n0)} at $${s.budgetM}M`).join(", ")}. Calming a set's residential blocks cuts kids hurt on them by 40% (20% to 55%), as safety upgrades' calming does, from ${a(L.grundy, "Grundy et al. 2009")}. We leave out kids hurt within 660 feet of a school, where safety upgrades' calming may reach, and on the blocks picked for speed humps, so no kid is counted twice. New riders add risk of their own: protected lanes are ${segs.length ? `${Math.round(100 * Math.min(...segs.map((s) => s.separatedShare)))}% to ${Math.round(100 * Math.max(...segs.map((s) => s.separatedShare)))}%` : "a share"} of a set's miles, and a kid biking on one carries a third of a car trip's risk, while on the calmed or shared rest it's 1.5 times. ${(() => { const small = segs.filter((s) => Math.abs(s.x.hurt[1]) < 0.15), big = segs.filter((s) => Math.abs(s.x.hurt[1]) >= 0.15), h = big.map((s) => s.x.hurt[1]); return `At our central ${small.length ? `the sets up to $${Math.max(...small.map((s) => s.budgetM))}M change kids hurt by ${Math.max(...small.map((s) => Math.abs(s.x.hurt[1]))).toFixed(2)} a year or less` : "no set changes kids hurt by less than 0.15 a year"}${big.length ? `, and the bigger sets spare ${Math.min(...h).toFixed(1)} to ${Math.max(...h).toFixed(1)} a year` : ""}.`; })()} Few kids are hurt on these blocks, ${Math.max(0, ...Object.values(INJ.bikeways || {}).map((m) => Object.values(m).reduce((t, x) => t + x, 0)))} or fewer in four years, so the figure moves when a budget swaps a few streets.`,
    why: `two stretches can be worth nothing alone and a lot together, and picking one at a time can't see that. Solving the set at once can. The solver starts from a one-at-a-time pick and keeps whichever of the two removes more family-car trips.`,
    ev: `the bike shift's cases under What the Model Does.`,
    cost: `each stretch at its street type's rate a mile, the same rates as the connectors. The chosen sets cost ${segs.map((s) => `${money(s.costM)} for ${s.centerlineMi} miles at $${s.budgetM}M`).join(", ")}, once.`,
  }));

  out.push(change("Walking School Bus", {
    what: `kids walk to school as a group, led by an adult on a set route. Our addition.`,
    who: `TK-5 students living within a mile's walk, at the ${nK5} schools with TK-5 grades.`,
    how: `walking and biking rise about 0.5 points school-wide, 0.37 of them from single-family cars, range 0 to 1 car point. That's the trial's 9.04 points among about 18 volunteers a school, spread over an SF TK-5 school of about 330. Fewer cars cut kids hurt near schools. A supervised walker counts as safe as the car trip they leave (range half a walker's extra risk to slightly safer), where a kid walking alone counts as riskier. One adult walks with about three kids, as Seattle's buses run, so two of three walkers need no parent of their own: ${fr(wb)} kids. ${results("walking_bus")}`,
    why: `it's a randomized trial. It tested grades 3 to 5 among the families who signed up, so we spread its effect over the whole school.`,
    ev: `${a(L.johnson, "Johnson et al. 2024")} randomized 22 lower-income schools in Houston and the Seattle area, 2012 to 2016. Days walked or biked rose 9.04 points (1.10 to 16.98) for grades 3 to 5 within a mile. Its Intervention section says "The WSB program was led by trained research assistants", so volunteer-led buses may do less. The same team's ${a(L.mendoza, "Houston pilot")} found walking rose from 24% to 54% with buses.`,
    cost: `${rate(cs.walkingBus)}, range $5,000 to $60,000: trained leaders on two routes every school day, as in the trial, about 540 leader-hours a year at $30 an hour, plus a part-time coordinator. Volunteer leaders set the low, and ${a(L.cordoba, "Córdoba's paid daily bus")} scaled to 180 days sets the high. That's ${money(wb.year)} a year.`,
  }));

  out.push(change("Carpool Matching", {
    what: `a city tool that matches families to share school drives. Our addition.`,
    who: `driving families at every grade, citywide.`,
    how: `0.5% of driven students move to a carpool shared by two families, range 0.2% to 1%, so half the parents are freed: ${fr(cp)} kids. Each carpooling kid takes half a car off the street and stays in a car. We count kids hurt for TK-8 pools only, since teen-driven cars carry 4.7 times the injury rate per trip (${a(L.trb, "TRB 2002")}). ${results("carpool")}`,
    why: `${a(L.contracosta, "Contra Costa's SchoolPool")} drew match requests from 0.45% of its students, about 0.8% of driven students at SF's car share, and only 27% of its pools lasted a second year. 0.5% sits between those.`,
    ev: `the one program with a stated denominator. ${a(L.schoolpool, "Denver's SchoolPool")} reports 19,000 families on 150 campuses, method not stated, so we don't use it.`,
    cost: `${rate(cs.carpool)}, the middle of the ${a(SAP + "#page=29", "School Access Plan's")} $100,000 to $250,000 for carpool coordination. Contra Costa's cost $95,000 in 2002-03 (${a(L.contraCosta, "FHWA")}).`,
  }));

  out.push(change("Free Muni for Caregivers", {
    what: `a caregiver rides free with a child going to school, extending Free Muni for Youth. Our addition.`,
    who: `the about ${n0(muniFar)} TK-8 students living over half a mile from school, in a straight line.`,
    how: `Muni's share among them rises 1 point, range 0 to 3. New riders come from single-family cars, carpools and bikes in the shares those students use today, so 88% leave a single-family car. That split is our assumption. A kid who switches to Muni sheds about 0.15 of a car trip's risk, since the walk to the stop is riskier for a child than the ride. The caregiver rides along, so no parent is freed. ${results("caregiver_muni")}`,
    why: `in ${a(L.pittsburgh, "Pittsburgh's randomized trial")}, free fares cut low-income adults' daily chance of a car trip 2.9 points, and trips with children didn't change. So 1 point is our judgment, with Pittsburgh's figure near the top.`,
    ev: `Pittsburgh's trial is the one study of car trips under free fares. In ${a(L.morency, "Montreal")}, car occupants were hurt 3.7 times as often as bus occupants per km.`,
    cost: `${rate(cs.muniPerRider)}, Muni's monthly pass for ten months, range $504 to $1,026. Every caregiver who rides with a child gets it, so today's riders count too: about ${n0(MD.MUNI_K5_TODAY)} TK-5 students ride Muni at the citywide share, our assumption. That's ${money(mu.year)} a year.`,
  }));

  out.push(change("School Shuttle Loops", {
    what: `yellow buses on fixed loops between neighborhood stops and several schools. Our addition, modelled on Denver's Success Express.`,
    who: `TK-8 students living over 2 miles' walk from school. About 6,500 students live that far, and SFUSD's general-education buses already carry about 2,000 of them (${a(SAP + "#page=42", "School Access Plan")}, p. 42). The Travel Tally has no school-bus bar, so we seed those 2,000 riders into today's mix, taken from every way of getting there in proportion.`,
    how: `640 riders, range 580 to 700, at the take-up of Denver's ${a(L.denverite, "Success Express")} loops, which carried 8.9% to 10.7% of eligible students, applied to SF's 6,500 TK-8 students over 2 miles. 48% of riders were driven before, from West Yorkshire's ${a(L.mybus, "MyBus")} (64%) weighted by SF's grades, so about 310 fewer driven kids. A bus trip carries about a fifth of a car trip's injury risk (${a(L.trb, "TRB 2002")}), and every rider needs no parent: ${fr(yb)} kids. ${results("yellow_bus")}`,
    why: `a loop shared by several schools costs less than a route per school, which is what made Denver's work.`,
    ev: `Denver's loop cost about 30% less than its regular routes, $1.05M against $1.5M (${a(L.chalkbeat, "Chalkbeat, 2011")}), and now carries almost 3,000 students to 35 schools (${a(L.denverite, "Denverite")}). SFUSD costed 1,520 more riders at $4.5M a year. A bus's lower risk is from ${a(L.morency, "Morency et al. 2018")}.`,
    cost: `${rate(cs.busPerRider)} before the state's share, from SFUSD's $2,960 a rider for its 19 new buses (${a(SAP + "#page=42", "School Access Plan")}, p. 42), range $2,050, today's fleet, to $3,400, SFUSD's 2023-24 cost (${a(L.ppssf, "PPSSF")}). The state pays about 60%, so SFUSD's net is about $1,200. That's ${money(yb.year)} a year at 640 riders.`,
  }));

  out.push(change("E-Bike Help", {
    what: `vouchers for every family at the ${MD.N_GATE} schools where most students within 2 miles have a safe bike route on today's streets. More schools pass as the network grows.`,
    how: `an e-bike makes hills count for less, by the Propensity to Cycle Tool's own e-bike scenario, so kids at those schools bike more. We count every family as taking one, since nothing tells us how many would. ${results("ebike")}`,
    ev: `${a(L.ucdavis, "UC Davis surveyed 617 rebate recipients")}: under 10% replaced a daily car trip.`,
    cost: `$${n0(cs.ebike.v)} a voucher, paid once to every family at those schools, whether or not they stop driving, above Denver's 2022 rebates of about $840 to $990 (${a(L.denverRebate, "BikePortland")}), plus $${n0(cs.ebikeProgram.v)} a year for the program.`,
  }));

  // The three speed changes on the streets near schools (tools/school-trips/school-speed-levers.py places them, and
  // tools/school-trips/school-kids-hurt.py counts the kids hurt on them).
  const SPK = INJ.speed || {}, kidsOn = (k) => Object.values((SPK[k] || {}).total || {}).reduce((t, x) => t + x, 0) / (INJ.years || 4);
  const nAt = (k) => Object.keys((SPK[k] || {}).kids || {}).length;
  const eff = (id, m) => { const e = MD.SPEED[id].eff[m]; return `${Math.round(100 * e[1])}% (${Math.round(100 * e[0])}% to ${Math.round(100 * e[2])}%)`; };
  const bd = alone("bad_district"), hp = alone("speed_humps"), hr = alone("speed_humps_rest"), cm = alone("speed_cameras");
  out.push(change("20 mph Business Districts", {
    what: `a 20 mph limit on main street blocks lined with shops and restaurants within a quarter mile of a school, which ${a(L.ab43, "Vehicle Code 22358.9")} (AB 43) lets the city declare as a business activity district.`,
    who: `${n0(MD.spUnits("bad_district"))} corridors near ${n0(Object.keys((SPK.bad || {}).corridors || {}).length)} schools, everyone on those blocks at any hour. A block counts when it's at least 150 feet long and has at least one retail or dining business address per 100 feet in ${a(L.bizData, "DataSF's registered business locations")}, on its own street, and isn't already at 20 mph or above 25 mph in ${a(L.limitsData, "DataSF's speed limits")}. One of the law's tests is half the frontage in shops, which the registry can't measure, so the floor is set where SF's own lowered blocks sit: about half the main street blocks SFMTA has posted at 20 mph since 2022 reach it. State highways and streets over 4 lanes are left out, from OpenStreetMap.`,
    how: `kids hurt on those blocks fall ${eff("bad_district", "Walking")}, at every mode, ${h1(kidsOn("bad"))} kids a year. Blocks within 500 ft of a school are already its school zone, so they're left out. It moves nobody out of a car. ${results("bad_district")}`,
    ev: `in ${a(L.kokka, "Edinburgh")}, 20 mph signs cut casualties 10% (95% CI 0% to 19%) on changed streets against streets kept at 30 mph, with no split by mode (Kokka et al. 2024). That was a 10 mph cut, and SF's is 5 mph, from 25.`,
    cost: `${rate(cs.badCorridor)}, range $14,000 to $27,000, from four SFMTA Board items. That's ${money(bd.once)} once.`,
  }));
  out.push(change("Speed Humps by Schools", {
    what: `humps on the residential blocks within 1 block (350 feet) of each school's grounds, one every 300 feet, at least one a block.`,
    who: `${n0(MD.spUnits("speed_humps"))} humps on residential blocks at ${n0(Object.keys((SPK.humps || {}).humps || {}).length)} schools, from ${a(L.streetsData, "DataSF's street file")}, leaving out blocks under 150 feet or over 1,000 feet, tunnels and ramps, and blocks that already have a hump, cushion or table in ${a(L.humpsData, "DataSF's traffic calming list")}.`,
    how: `kids hurt on those blocks where both streets are residential fall ${eff("speed_humps", "Walking")} walking and ${eff("speed_humps", "In a car")} for everyone else, ${h1(kidsOn("humps"))} kids a year. Safety upgrades' calming already humps the residential streets within 660 feet at the ${calmB.schools || 0} schools its budget reaches. So with safety upgrades on, humps go only to the other schools, where they spare ${h1(hr.hurt[1])} kids a year for ${money(hr.once)}, and nothing is counted twice. The budget plans offer humps only at those other schools too. It moves nobody out of a car. ${results("speed_humps")}`,
    ev: `${a(L.cmf134, "FHWA's CMF 134")} puts injury crashes on local streets at 0.5 after humps, standard error 0.13. In ${a(L.tester, "Oakland")}, children were 0.47 times as likely to be struck near home where there were humps (95% CI 0.24 to 0.95, Tester et al. 2004), the only study of children, so kids walking range from 5% to 76% fewer hurt.`,
    cost: `${rate(cs.speedHump)}, range $5,000 to $21,000. That's ${money(hp.once)} once at every school.`,
  }));
  out.push(change("Speed Cameras by Schools", {
    what: `a new speed camera on a main street within 500 feet of each school. This assumes the state raises the cap in ${a(L.ab645, "AB 645")}, which lets SF run 33 cameras, all in use now.`,
    who: `${n0(MD.spUnits("speed_cameras"))} schools, each with a camera on the main street with the most length inside its 500 ft zone, at the point nearest the grounds. Schools with one of SF's cameras within 500 feet, in ${a(L.camData, "DataSF's camera citations")}, are left out, and so is a camera that would sit within a quarter mile of one on the same street, or within 660 feet of another school's new one. State highways are Caltrans's and left out.`,
    how: `kids hurt on the camera's street within a quarter mile of it fall ${eff("speed_cameras", "Walking")} walking, ${eff("speed_cameras", "Biking")} biking and ${eff("speed_cameras", "In a car")} in a car, ${h1(kidsOn("cameras"))} kids a year at ${nAt("cameras")} of the cameras. Scooters get no cut, since NYC's other motorized riders were hurt more at camera and control corridors alike. It moves nobody out of a car. ${results("speed_cameras")}`,
    ev: `NYC's cameras added in 2022 against corridors without one, 2021 to 2023, within a quarter mile of the camera on the same street (${a(L.nycCam, "NYC DOT 2024 report")}, p. 20): pedestrians hurt 0.87 times the control's change, cyclists 0.79 and people in vehicles 0.86. NYC published no interval, so the low is 0 and the high is our judgment.`,
    cost: `${rate(cs.speedCamera)}, the flat fee in ${a(L.sfmtaCam, "SFMTA's camera contract")}, ${money(cm.year)} a year for all of them. Fines are expected to cover it.`,
  }));

  out.push(change("Daily Travel Tracker", {
    what: `daily class trip logs, as in WOW, at every TK-5 school, we assume.`,
    how: `car share falls 0, 1.8 or 3.5 points. ${results("travel_tracker")}`,
    ev: `self-selected ${a(L.wow, "Scottish schools")} walked 5 points more after three years, 71% kept going.`,
    cost: `$${n0(cs.travelTracker.v)} a school a year.`,
  }));

  out.push(change("E-Cargo Bike Month", {
    what: `a free e-cargo bike month for 12 families at each of ${MD.N_GATE} schools yearly.`,
    how: `3%, 10% or 20% of the 73% driving bike instead. ${results("ecargo_month")}`,
    ev: `${a(L.elevate, "ELEVATE")}: 10 of 49 households bought one within a year.`,
    cost: `$${n0(cs.ecargoTrial.v)} a family, $${n0(cs.ecargoProgram.v)} yearly.`,
  }));

  out.push(change("Bell-Time Curb Restriction", {
    what: `no stopping on the school block at the bells.`,
    how: `central case no change, high 1 TK-5 car point. ${results("curb_restriction")}`,
    ev: `${a(L.dundee, "Dundee's")} voluntary cones cut driving 2.1 points, mostly to park and stride, which SF counts as driven.`,
    cost: `$${n0(cs.curbRestriction.v)} a school, once.`,
  }));

  out.push(change("Bike Bus", {
    what: `an adult-led group ride, one route at each of ${MD.N_GATE} schools.`,
    how: `0, 0.3 or 3 car points: volunteer, $4,500 weekly or $23,000 daily paid route. ${results("bike_bus")}`,
    ev: `no car outcome measured. ${a(L.bikebus, "145 organizers")} report 10 kids a route, 60% weekly.`,
  }));

  out.push(change("SFUSD's New Assignment", {
    what: `Neighborhood + Citywide Programs, SFUSD's new elementary assignment, as it stands in 2030-31. The Board adopted it 5-2 on 13 October 2026 (${a(L.boardVote, "The Standard")}, ${a(L.boardVoteML, "Mission Local")}), and the final policy is due 13 April 2027. Every scenario but Today uses it.`,
    who: `TK-5 students under the new rules: "Families enrolling in TK or kindergarten for the first time, and families new to SFUSD entering an elementary or K-8 school", from "School year 2028-29". It leaves out "Families currently enrolled, who will not be moved" (${a(L.study1, "Study Session #1 deck")}, scope slide).`,
    how: `each TK-5 trip's distance shrinks by the option's ratio to today, and every student chooses again how to get there. We read the rollout as TK and K in 2028-29 and one more grade each year, so the new rules cover 20% of TK-5 students in 2028-29, 52% in 2030-31 and all of them in 2033-34, each grade weighted by its ${a(L.cdeGrades, "2024-25 SFUSD enrollment")}. That schedule is our reading, not SFUSD's, and sibling priority could slow it: sibling is the first tiebreaker for TK and K today (${a(L.tiebreakers, "SFUSD")}), and the 2026 decks don't say how siblings are treated. [inference — mine] The tool blends each school's mix 52% with the option and 48% without, as in 2030-31, the plans' fourth year. Then it takes ${n0(ncp.cars[1])} kids out of single-family cars, range ${n0(ncp.cars[0])} to ${n0(ncp.cars[2])}. At full effect in 2033-34, Neighborhood + Citywide Programs takes ${n0(ncpFull.cars[1])}. We put kids hurt at full effect at 0.4 a year, range 0 to 1, our estimate: kids still driven ride about 13.6% fewer car miles, and new walkers carry walking's higher risk. In 2030-31 it's 52% of that.`,
    why: `a shorter trip makes walking and biking quicker against the car.`,
    ev: `Stanford's average elementary distance in ${a(STUDY2, "SFUSD's Study Session #2")}: 1.40 miles today and 1.06 under Neighborhood + Citywide Programs, at full effect.`,
    cost: `none in the tool.`,
  }));
  return out.join("\n");
}

export function render() {
  if (!has || !MD) throw new Error("school trips about: site/data/school-sim/index.json or city.json missing; run tools/school-trips/school-sim.py");
  const c = IX.checks, cw = c.citywide, z = c.zip.summary.all, ar = c.attendanceArea;
  const listed = Object.values(c.byGrade).reduce((t, g) => t + g.students, 0);
  const pruned = listed - STUDENTS;
  const dd = c.byDistance, under = dd.model.under1 - dd.cts2016.under1, over = dd.model.over2 - dd.cts2016.over2;
  const zipRows = z.schools + (c.zip.unmatched || []).length;
  const body = `${CSS}<div class="ta">
<h1>About School Trips</h1>
<p>School Trips models every SFUSD, charter and private school student's trip to school, today and with each change. Today ${n0(CAR0)} of ${n0(STUDENTS)} students, ${CAR_PCT.toFixed(1)}%, come by single-family car, against the 30% goal in ${a(TALLY, "SF Safe Routes to School's 2024-25 report")}. That report's Travel Tally gives 48.6%, but it weights the grades by who answered, mostly kindergarten and 5th grade. We weight every grade by its ${a(CDE, "CDE Census Day 2025-26")} enrollment, and older grades drive less.</p>
<p>Every figure is our central estimate, with a low and a high beside it. The low and high are our assumption cases, not a statistical range. Private schools' students come from the CDE's ${a("https://www.cde.ca.gov/ds/si/ps/documents/privateschooldata2526.xlsx", "Private School Affidavit 2025-26")} enrollment by grade, placed so their trips run about as long as those to SFUSD's citywide schools of the same level. Kids hurt counts every child in the city.</p>

<h2 id="wedges">Citywide Goals: The Wedges</h2>
<p>Citywide Goals sorts the changes into six wedges, the way ${a("https://climatewedges.com/build.html", "Climate Wedges")} sorts climate action. Each wedge's control steps through its changes and stops where we think 2030 stops it, with what stops it named beside the control. The page opens on SFMTA's plan: the four tools in its ${a(SSC, "draft approach")} at every school, the 15/20 mph school zone signs among them, with the assignment SFUSD's Board chose in Shorter Trips, and nothing else.</p>
<p>Changes reach the same kids, so we never add up two changes' figures. Each total is the model run with every change on at once. A wedge's segment is what it adds to the wedges listed above it, so a wedge lower on the list gets a little less credit than it would alone. Kids hurt combine by multiplying, as in Scenarios. A wedge whose new walkers and bikers add more injuries than its fewer cars spare gets no segment, and the bar says how many more.</p>
<p>An idea marked Not counted yet has no lever in the model, so it adds nothing to the bars, and Driving Less Convenient has none yet at all. Three changes in Citywide Scenarios aren't in a wedge yet: E-Bike Help, the E-Cargo Bike Month and the Bell-Time Curb Restriction. Shorter Trips uses the assignment SFUSD's Board chose as it stands in 2030-31, when it covers about half of TK-5. The injury goal is ours: 30% fewer of the ${n0(MD.HB)} kids 5 to 18 hurt a year on school-year weekdays, August to May.</p>

<h2>Scenarios</h2>
${scenariosHtml()}
<p>A plan's cars come from each school's own simulation with the changes funded there, added up. Its kids hurt come from each school's own crashes: safety upgrades act on the kids hurt nearest that school within their reach, speed limits on the kids hurt in its 500 ft zone, and fewer cars cut injuries at each change's citywide rate per car. The two maps show a plan approximately, scaling each change's shift on every block by the share of its citywide effect the plan's schools carry.</p>
<p>A change with no cost shows No cost per $1M, and one that costs money but saves nothing on that measure shows n/a. Changes overlap, so their own effects don't add up to a scenario's central figure, which comes from running them together. A scenario's low moves that central figure by each change's own gap between its low and central, added up, and its high the same way. Kids hurt are multiplied instead: if one change leaves 90% of injuries and another 80%, together they leave 72%.</p>
<p>Four changes are tools in ${a(SSC, "SFMTA's Safe School Connections draft approach")} (September 2026), shown in blue in the each-change charts: School Street Activation, Safety Upgrades for Walking, 15/20 mph School Zone Speed Limits and School Connector Street. The rest are our additions, in yellow.</p>

<h2>What the Model Does</h2>
<p>Each rule below applies to every change. The ones we set ourselves are marked as our assumptions.</p>
<div class="scroll"><table><thead><tr><th>Rule</th><th>How it works</th></tr></thead><tbody>
<tr><td>Home blocks</td><td>Each census block's children (2020 census) are spread across every SFUSD and charter school by a distance curve that meets each school's ${a(CDE, "CDE Census Day 2025-26")} enrollment by grade. Private schools get their own curve, set to the reach of SFUSD's citywide schools at each level.</td></tr>
<tr><td>School assignment</td><td>At the ${ar.areaSchools.n} elementary schools with an ${a(AREAS, "attendance area")}, part of each grade comes from the area and the rest by distance. Middle, high and citywide schools go by distance alone.</td></tr>
<tr><td>Today's way to school</td><td>Each student picks by trip time, set so each grade's single-family car share matches the Travel Tally.</td></tr>
<tr><td>Speeds</td><td>Walking 2 mph. Biking 8.5 mph plus about 2 minutes to get going, fit to Google's bike times. Driving at SFCTA's 13.4 mph morning median, adjusted to Google's times at the bell, plus 3 minutes to park and walk in. Muni is a placeholder, our assumption: 10 minutes to walk to the stop and wait, then the trip's length at 8 mph.</td></tr>
<tr><td>All-ages bike network</td><td>Paths and separated lanes count wherever they are. A Slow Street counts wherever it is, on the ${a(PLAN_URL, "Biking and Rolling Plan")}'s network or off it, and so does a new calmed street built the same way with diverters. Painted lanes and signed routes don't count. That's stricter than the plan, which counts them where SFMTA's ${a(BCI_MAP_URL, "Bike Comfort Index")} is above 80, because we found no study testing that score against how stressed riders, let alone kids, feel. Paths off the plan's network still count, since the plan's map follows street blocks and leaves out trails like the Bay Trail for that reason alone.</td></tr>
<tr><td>Safe route</td><td>A walk or bike route with at most 1,000 feet in all off today's all-ages bike network, every off-network stretch between home and school added up. A bike route that crosses a street of four or more lanes, or posted at 35 mph or more, at a crossing with no signal doesn't count as safe whatever its gaps: a design rule of ours, not a measured finding, using OpenStreetMap's lanes, speed limits and crossing signals.</td></tr>
<tr><td>Safe trip</td><td>A walk or bike trip of 15 minutes or less on a safe route.</td></tr>
<tr><td>Bike shift</td><td>A kid's chance of biking follows the Propensity to Cycle Tool's school curve by distance and hills, set to match today's Travel Tally. A new street moves it in three cases, in step with how much more of the kid's route it puts on the all-ages network, and we read year 10 of ten. High is the tool's Go Dutch shift. Low is sized so a full network gets Cambridge, Massachusetts' 14.3% of commutes by bike. Central is halfway between, our assumption, and it's every headline, with Low to High as the range.</td></tr>
<tr><td>E-bike</td><td>Rides 15% faster than a bike. Our assumption.</td></tr>
<tr><td>Muni, and School Bus or Shuttle Loop</td><td>Muni is the Travel Tally's transit share. The Tally has no school bus category, so we add back today's 2,000 or so SFUSD yellow bus riders: TK-8 students living over 2 miles' walk away, each way to school giving up the same share. The district's 2024-25 Travel Tally memo says its transit share already includes yellow bus riders, so this add-back may count some of them twice, and the family car share today may read slightly low. We haven't measured by how much. School Bus or Shuttle Loop counts only the new seats the shuttle loops add.</td></tr>
<tr><td>No parent needed</td><td>Walking or biking a safe trip of 15 minutes or less from 3rd grade, Muni from 6th grade, or a school bus at any grade. A change frees a parent only when another adult runs the trip, and only the shuttle loops, the walking school bus and carpool matching do.</td></tr>
</tbody></table></div>
<p>Cambridge is adults, and kids bike at 0.4 to 1.3 times adults' rate in the two cities with both figures, so Low could be off by a factor of three either way. A kid whose route gains nothing doesn't move in any case.</p>

<h2 id="changes">How We Model Each Change</h2>
<p>Each figure below is the change alone at every school it reaches, against today. Seven changes use a study's measured effect: the speed limits, School Street Activation, Safety Upgrades for Walking, the Walking School Bus, 20 mph business districts, speed humps and speed cameras. Eight are our estimates, since no study measures them: Carpool Matching, Free Muni for Caregivers, School Shuttle Loops, E-Bike Help, the Daily Travel Tracker, the E-Cargo Bike Month, the Bell-Time Curb Restriction and the Bike Bus. The new streets, bikeways and e-bike help use the bike shift's three cases, and the assignment options use SFUSD's own distances.</p>
${changes()}

<h2 id="kids-hurt">Kids Hurt</h2>
${hurtCharts()}
<p>The model starts from ${n0(MD.HB * 4)} kids aged 5 to 18 hurt over four school years on weekdays, 6 am to 6 pm, August to May, about ${n0(MD.HB)} a year, from ${a(L.crashes, "DataSF's crash data")}. Fewer cars cut those hurt within a quarter mile of a school's grounds, ${n0(INJ.near)} of the ${n0(INJ.base)}, with the square root of traffic (${a(L.elvik, "Elvik and Bjørnskau 2017")}), with school cars at 0%, 5% or 25% of the traffic at the bell on residential streets. The low is 0 because, counting every injury crash and not only kids walking and biking, the bells show no excess: within 600 feet of a school's grounds, injury crashes at bell times were 290 against the 288 the city's clock predicts, a ratio of 1.01 (0.89 to 1.12), from our check of ${a(L.crashes, "DataSF's crash data")}. The high of 25% is the most that check allows [inference — mine]. Main streets carry far more through traffic, so there we put school cars at a tenth of that, our judgment. ${n0((INJ.nearByStreet || [0])[0])} of the ${n0(INJ.near)} were hurt on a main street. School cars are on the street only at the bells, which held ${n0(INJ.bellN)} of ${n0(INJ.bellD)} child walking and biking crashes within 600 feet of the grounds on school days, so the cut applies to that share. A kid leaving a car changes their own risk too. A school bus trip carries about a fifth of a car trip's risk (${a(L.trb, "TRB 2002")}). Per km, a child walking is hurt 4.6 times as often as one in a car and a child biking 22 times (${a(L.lavoie, "Lavoie et al. 2014")}), so we count a walking switcher at 1.5 times the car trip's risk and a biking one at 3 times, or 2 times on an e-bike voucher. A cycle track carries 0.11 of the risk of a major street with parked cars and no bike lane, and a local street 0.51 (${a(L.teschke, "Teschke et al. 2012")}), so a kid biking on a new protected bikeway counts at a third of the car trip's risk and on a calmed or shared street at 1.5 times. A bikeway set's riders split as its miles do. That leaves out the protected bikeways their trips already use, so it may count them riskier than they are, our judgment. We take our ordinary-street bike risk as that major street's [inference — mine]. The car passengers behind that risk are all of SF's 80,919 students, so we scale them to the ${n0(STUDENTS)} the tool covers. We count injuries for the whole city, not school by school.</p>

<h2>What the Changes Cost</h2>
<p>This table gives each change's rate and where it comes from. A change's total adds the rate up at every school it reaches.</p>
${costTable()}
<p>Staff counts assume ${COSTS.ssStaff.v} people a school for School Street Activation, one shuttle driver for every ${COSTS.busRiders.v} riders and half a person for carpool matching. We don't estimate street design and construction staff.</p>

<h2 id="by-grade">Set to Match: Car Share by Grade</h2>
<p class="find">Driving peaks in elementary school and falls through high school, from 56% in 5th grade to 33% in 9th.</p>
<p>These are inputs the model is set to match, and it matches every grade. The ${a(TALLY, "2024-25 Travel Tally")} measured four grades. We draw straight lines between them, hold TK at kindergarten's value, and hold 10th to 12th at 9th grade's.</p>
${gradeChart(c)}
<p class="note">Solid dots are the grades the Tally measured. Hollow dots are filled in between them. Single-family car share of SFUSD students, SF Safe Routes to School, 2024-25 school year.</p>

<h2>Tested: Car Share by Distance</h2>
<p>The model isn't tuned to these, so this is a real test, and it misses at both ends. Under a mile it has ${Math.round(Math.abs(under))} points fewer K-5 kids driven than the ${a(CTS, "2016 Child Transportation Survey")} (p. 10), and over 2 miles ${Math.round(over)} points more. So it likely understates how many nearby families drive, the ones walking changes reach, and overstates the far ones the shuttle loops reach. The survey asked K-5 parents how their child got to school and how far they live, and doesn't say how it measured distance. We use the walking distance.</p>
${distance(c)}

<h2>Placed: Where Students Live</h2>
<p>${a(DASH, "SFUSD's dashboard")} counts each school's students by home ZIP code. We matched ${z.schools} of its ${zipRows} school listings, a K-8 counting as two. For those, ${p0(z.overlapPct)} of the model's students live in the same ZIPs as the dashboard's, and ${z.sameTop5.toFixed(1)} of each school's top 5 ZIPs match. That's ${n0(z.students)} students, fewer than our ${n0(STUDENTS)}, since charter schools aren't on the dashboard and it hides ZIPs with under five students. At the ${ar.areaSchools.n} schools with an attendance area, a median ${p0(ar.areaSchools.median)} of students live in it, from ${p0(ar.areaSchools.min)} to ${p0(ar.areaSchools.max)}. These counts helped set the model, so this is a fit rather than a test.</p>

<h2>The Maps and Your Trip</h2>
<p>Each circle is a home block, sized by its students. The first map shows how students get to school, and the second the share with a safe trip. The mode map adds each change's own effect to today's, so it's close but not exact where changes overlap, while the figures beside it are exact. Your Trip routes one address on the same network and rules, in your browser, and Google sees only what you type in the box.</p>

<h2>What's Left Out</h2>
<ul>
<li>Aftercare. We count one trip a student, and 46% of K-5 families used aftercare daily in 2016 (${a(CTS, "Child Transportation Survey")}, p. 3).</li>
<li>Real Muni times. Until each trip is timed from SFMTA's schedule, a Muni trip is 10 minutes to walk to the stop and wait, then the trip's length at 8 mph.</li>
<li>${n0(pruned)} students, ${(100 * pruned / listed).toFixed(1)}%, on blocks that send almost none to a school, which is why the tool counts ${n0(STUDENTS)} of the ${n0(listed)} enrolled.</li>
</ul>
</div>`;
  return page({ title: "About School Trips", description: "How the School Trips simulation works, how each change is modelled, and the checks it passes.", path, body });
}
