// School Trips: one modelled city of students, seen as the city and as one school.
//
// Bryan, 2026-10-08, on what the school tool is for: "1) Your own individual
// experience getting to school 2) Your school's experience 3) The city-wide
// experience from different strategies. And these should all tie together."
// The layout is the mockup he approved the same day: The City and Your School (five changes, the bikeway
// blocks, the map of where its students live). The City is every change as
// an on/off switch citywide, with no years, order or budget, and one map of
// home blocks. Bryan, 2026-10-09: "we show summary metrics on school tool.
// But then we also show a map of mode share by each travel mode current and
// with proposed interventions. Default to showing car mode share. And show a
// map of people who are within 15 minutes on safe routes. And also a distance
// map and gap size map". Its figures are exact for every switch set, from
// site/data/school-sim/city.json (school-sim.py's city_view), fetched once
// beside the page. Your Trip is a section
// below the fold of Your School, Bryan's answer on the mockup: "Merge your
// trip in as a section that goes below the fold in your school on the same
// page." A reader types an address and sees their trip to the school above by
// each way, today and with the changes set above it, on two maps and in a
// table of minutes and safe miles. The trip is routed in the browser
// (site/src/school-trip-router.mjs) on the simulation's network
// (site/data/school-trip-graph.json, tools/school-trips/school-trip-graph.py), and the
// address box suggests addresses from Google Places as the reader types
// (Bryan, 2026-10-09, on the box: "This should use the following lace finder
// like bike map from Google"), with the same browser key as the basemap. A
// build without the key, or a page whose address Google refuses, looks the
// address up in site/data/sf-addresses.json (pipeline/sources/sf-address-points.py).
//
// Every figure is read from site/data/school-sim/, written by
// tools/school-trips/school-sim.py: expected students per home block at every SFUSD and
// charter school, a mode choice fit to the 2024-25 Travel Tally, and each
// change applied in its own study's units. A school's figure is the sum of
// its blocks, the city's the sum of its schools, so the two views agree.
//
// Laid out by docs/product/tool-ux-guidelines.md: controls left, the map or
// chart in the middle with the one figure that matters on it, outcomes right,
// one 1366x768 screen. Every row is always drawn, so nothing moves when a
// control changes. Counts of students lead, the percent sits small beneath.

import fs from "node:fs";
import nodePath from "node:path";
import { page } from "../layout.mjs";
import { BASEMAP, MAP_HEAD, encodeRuns, inlineJson } from "../maplibre.mjs";
import { PLAN_URL } from "../transportation.mjs";
import { makeRouter } from "../school-trip-router.mjs";
import { makeCityModel, readEbikeGate } from "../school-trips-model.mjs";
import { VKEYS, planGreedy, tableSum, planAll, replanHurt } from "../school-trips-plan.mjs";
import { COMMENT_CSS, commentView } from "../school-trips-comment.mjs";
import { WEDGE_CSS, wedgeView, wedgeUI, wedgeClientData, PLAN_STEPS, FULL_STEPS } from "../school-trips-wedges.mjs";
import { figure } from "../figures.mjs";
import { fnSource } from "../fn-source.mjs";

export const path = "/transportation/school-trips";
export const file = "transportation/school-trips/index.html";
// How this page is listed on the home page and the page above it (src/directory.mjs).
export const listing = { title: "Safer School Trips", line: "How SF students get to school, and what each change would do at one school and citywide.", parent: "section", order: 2,
  views: [["comment", "The Public Comment"], ["goals", "Citywide Goals"], ["city", "Citywide Scenarios"], ["school", "Your School"]] };
const MODEL_PATH = "/transportation/school-trips/about";

const DATA = nodePath.join(import.meta.dirname, "..", "..", "data");
const SIM = nodePath.join(DATA, "school-sim");
const readJson = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const has = fs.existsSync(nodePath.join(SIM, "index.json"));
const IDX = has ? readJson(nodePath.join(SIM, "index.json")) : null;
const TRIP_GRAPH = nodePath.join(DATA, "school-trip-graph.json");
const ADDRESSES = nodePath.join(DATA, "sf-addresses.json");
// Each school's School Connector cost and the students free Muni reaches (tools/school-trips/school-sim-rules.py).
// Kids hurt on SF weekdays and the model's injury shares (tools/school-trips/school-kids-hurt.py).
const HURT = readJson(nodePath.join(DATA, "school-kids-hurt.json"));
// The budget plans (tools/school-trips/school-budget-plans.mjs): which changes go to which schools, and which new bikeways get
// built, for $5M to $100M over 4 years, and the table the browser re-plans from when a change is turned off.
const PLANS = fs.existsSync(nodePath.join(DATA, "school-budget-plans.json")) ? readJson(nodePath.join(DATA, "school-budget-plans.json")) : null;
const RULES = fs.existsSync(nodePath.join(SIM, "rules.json")) ? readJson(nodePath.join(SIM, "rules.json")) : null;
if (fs.existsSync(nodePath.join(SIM, "city.json")) && !RULES) throw new Error("school trips: site/data/school-sim/rules.json missing; run tools/school-trips/school-sim-rules.py");

// What the City view's changes cost and who they take, each with where it
// comes from. Street costs are data/school-budget/unit-costs.json's central
// figures per centerline mile. The rest have no published cost, so they are our
// assumptions, said so on About School Trips, which prints each src as HTML:
// plain words and inline links, never a file name.
const A_ = (url, text) => `<a href="${url}">${text}</a>`;
const SAP_URL = "https://www.sfcta.org/sites/default/files/2024-07/SF_School_Access_Plan_Report_2023-05-04_FINAL.pdf";
export const COSTS = {
  connectorSep: { v: 1.5, label: "School Connector Street, on a main street", unit: "$M a mile", src: "the median of five SFMTA quick-build bikeway budgets at Board approval (17th Street, Mid-Valencia, Winston Drive, Frida Kahlo Way and Beach Street), the same rate as new bikeways. Each block takes its street type from OpenStreetMap, and a connector under a quarter mile is priced as a quarter mile" },
  connectorCalm: { v: 0.25, label: "School Connector Street, on a residential street", unit: "$M a mile", src: `SFMTA's average of about $200,000 a mile for Slow Streets (${A_("https://www.sfmta.com/reports/12-6-22-mtab-item-14-tc-amendment-slow-streets-program", "SFMTA Board, December 6, 2022")}, p. 13), plus about 25% for prices since and the diverters a busier street needs. A piece off any street is priced halfway between this and a new shared-use path's $0.72M a mile, the average in ${A_("https://www.pedbikeinfo.org/downloads/Countermeasure%20Costs_Report_Nov2013.pdf", "FHWA's 2013 cost report")} raised 50% for prices since` },
  calmPerSchool: { v: 7500, label: "15/20 mph School Zone Speed Limits", unit: "$ a school, once", src: `SFMTA's 2012 school speed zones cost $361,700 for about 803 signs at 181 schools (${A_("https://archives.sfmta.com/cms/apress/MayorLeeSFMTAandWalkSFAnnounceNewSaferSpeedZonesCompletedaround181SanFranciscoSchools.htm", "SFMTA, May 14, 2012")}), about 4.4 signs and $2,000 a school, which sets the low. A zone reaching a quarter mile has about 12 entering streets to sign, and at $650 a sign that's about $7,500 a school, at every school. The high is $16,000, 24 signs a school. Cameras aren't priced` },
  busPerRider: { v: 3000, label: "School Shuttle Loops", unit: "$ a rider a year", src: `SFUSD's $8.6M for 19 more buses serving 1,520 more students, $2,960 a rider (${A_(SAP_URL + "#page=42", "School Access Plan")}, p. 42), rounded to $3,000. Range $2,050, today's fleet, to $3,400, SFUSD's 2023-24 cost (${A_("https://www.ppssf.org/news/2025/2/19/access-at-risk-the-implications-of-cutting-school-buses-in-sfusd", "PPSSF")}). The state pays about 60%, so SFUSD's net is about $1,200` },
  muniPerRider: { v: 860, label: "Free Muni for Caregivers", unit: "$ a rider a year", src: `Muni's $86 monthly pass for the ten school months (${A_("https://www.sfmta.com/index%2Ephp/notices/muni-fare-changes-effective-july-1-2025", "SFMTA fares from July 1, 2025")}), for every caregiver who rides with a TK-8 child, new riders and today's. Range $504 (Clipper START) to $1,026 (single fares)` },
  schoolStreet: { v: 30000, label: "School Street Activation", unit: "$ a school a year", src: `two staff, one at each end of the closed block, 1.5 hours a day for 180 days, at the $56 an hour SFMTA's crossing guards cost loaded (${A_("https://www.sfmta.com/blog/prioritizing-safety-schools-citywide-update-our-crossing-guard-program", "SFMTA, August 29, 2025")}), at every school with TK-5 students. Range $13,500 to $60,000` },
  ssSetup: { v: 17000, label: "School Street set-up", unit: "$ a school, once", src: `Hampshire's School Streets set-up of £12,000 to £15,000 a school (${A_("https://democracy.hants.gov.uk/documents/s116625/School%20Streets.pdf", "Hampshire Cabinet, February 6, 2024")}, para 18), at $1.27 a pound. Range $6,000 to $32,000. No SF set-up cost was found` },
  walkingBus: { v: 25000, label: "Walking School Bus", unit: "$ a school a year", src: `trained leaders on two routes every school day, as in the ${A_("https://pmc.ncbi.nlm.nih.gov/articles/PMC11083767/", "trial")} the effect comes from, about 540 leader-hours a year at $30 an hour, plus a part-time coordinator. Range $5,000, volunteer leaders, to $60,000, ${A_("https://helvia.uco.es/handle/10396/27616", "Córdoba's paid daily bus")} scaled to 180 days` },
  saferCrossings: { v: 200000, label: "Safety Upgrades for Walking", unit: "$ a school, once", src: `between SF's "~$60,000 per walk-audit" with about six low-cost fixes (${A_(SAP_URL + "#page=46", "School Access Plan")}, p. 46) and the $290,000 construction line of the ${A_("https://www.sfcta.org/sites/default/files/2025-03/Monterey%20Boulevard%20Pedestrian%20Safety%20Improvement%20ARF.pdf", "Monterey Boulevard")} corridor, at every TK-8 school. Range $60,000 to $290,000. That's the price of fixing every crossing within one block of the average school's grounds. The upgrades go only where at least one street is a main street, so each reach costs that price in proportion to the main street intersections inside it` },
  calmStreets: { v: 10, label: "Calming residential streets near schools", unit: "$M once, citywide", src: `Our budget: $10M, range $5M to $20M, for humps and diverters on residential streets within 660 ft of a school's grounds, at $0.25M a mile, schools taken in order of kids hurt nearby over the last 10 school years. Comes with the safety upgrades` },
  carpool: { v: 150000, label: "Carpool Matching", unit: "$ a year citywide", src: `the middle of the School Access Plan's $100,000 to $250,000 for carpool coordination (${A_(SAP_URL + "#page=29", "p. 29")}). Contra Costa's SchoolPool cost $95,000 in 2002-03 (${A_("https://ops.fhwa.dot.gov/publications/mitig_traf_cong/contra_costa_case.htm", "FHWA")})` },
  ebike: { v: 1500, label: "E-Bike Help", unit: "$ a voucher, once", src: `our estimate, range $1,000 to $2,000, above Denver's 2022 rebates of about $840 to $990 each (${A_("https://bikeportland.org/2023/03/06/what-we-can-learn-from-denvers-e-bike-rebate-program-371026", "BikePortland, March 6, 2023")}), since a bike that carries a child costs more. One voucher for every family at the schools where most students within 2 miles have a safe bike route, whether or not they stop driving` },
  ebikeProgram: { v: 150000, label: "E-Bike Help program", unit: "$ a year citywide", src: "our assumption: a part-time coordinator plus try-it and repair days at the pilot schools, on the same basis as the walking school bus coordinator. Range $100,000 to $200,000" },
  travelTracker: { v: 5000, label: "Daily Travel Tracker", unit: "$ a school a year", src: `our estimate, range $2,000 to $15,000, at every school with TK-5 students. Living Streets spent about £550,000 on 219 Scottish schools in 2022-23, about £2,500 a school (${A_("https://www.livingstreets.org.uk/media/ceueykb4/dch-schools-final_report_20_10_23.pdf", "DHC for Living Streets Scotland, 2023")}, para 5.16), without school staff time` },
  curbRestriction: { v: 5000, label: "Bell-Time Curb Restriction", unit: "$ a school, once", src: "our estimate, range $2,000 to $20,000: signs, red paint, an SFMTA engineer's time and moving the white zone off the block, at every school with TK-5 students. SFMTA's white zone fees top out at about $3,500" },
  bikeBus: { v: 4500, label: "Bike Bus", unit: "$ a route a year", src: "our estimate: a paid chaperone pair for a weekly route, one route at each school where most students within 2 miles have a safe bike route. It's paired with the effect: a volunteer route at $0 for the low, a daily paid route at $23,000 for the high" },
  ecargoTrial: { v: 400, label: "E-Cargo Bike Month", unit: "$ a family trial", src: `our estimate, range $190 to $900, a month's insured rental with accessories and a follow-up survey, for 12 families a school a year at schools where most students within 2 miles have a safe bike route. Wombi rents for $115 to $150 a month in Los Angeles and Seattle, and ${A_("https://zerocarbonmerri-bek.org.au/wp-content/uploads/2024/02/MO80_RideStride_2023Report_web_FA.pdf", "Merri-bek's trials")} ran the same design` },
  ecargoProgram: { v: 150000, label: "E-Cargo Bike Month staff", unit: "$ a year citywide", src: "our estimate, range $100,000 to $200,000, for recruiting families, handing over bikes and the follow-up survey" },
  badCorridor: { v: 19000, label: "20 mph Business Districts", unit: "$ a corridor, once", src: `signs, outreach and labor, from four SFMTA Board items lowering limits on 7 to 11 business district and safety corridors at a time: $190,000 for 7 streets in ${A_("https://www.sfmta.com/media/29332/download", "December 2021")}, and $100,000 for 7, $150,000 for 11 and $150,000 for 8 corridors (${A_("https://www.sfmta.com/media/40504/download", "SFMTA")}, ${A_("https://www.sfmta.com/media/41895/download", "SFMTA")}, ${A_("https://www.sfmta.com/media/43286/download", "SFMTA")}). Range $14,000 to $27,000 a corridor` },
  speedHump: { v: 10000, label: "Speed Humps by Schools", unit: "$ a hump, once", src: `our estimate for an asphalt hump, range $5,000 to $21,000. The high is SFMTA's 2023 request of about $4.27M for about 200 traffic calming measures over two years, design and staff included (${A_("https://www.sfcta.org/sites/default/files/2023-05/SFCTA_Board_Transportation%20Network%20Companies%20Tax%20Allocation%20Traffic%20Calming%20PRESENTATION_2023-05-09.pdf", "SFCTA, May 9, 2023")})` },
  speedCamera: { v: 3750, label: "Speed Cameras by Schools", unit: "$ a camera a month", src: `the flat monthly fee per camera location in SFMTA's camera contract with Verra Mobility, $7,425,000 for 33 cameras over 60 months (${A_("https://www.sfmta.com/media/40836/download", "SFMTA Board, 2024")}). Fines are expected to cover it` },
  ssStaff: { v: 2, label: "School Street Activation staff", unit: "people a school", src: "our assumption: two part-time staff, one at each end of the block" },
  busRiders: { v: 50, label: "School Shuttle Loops riders a driver", unit: "riders a bus", src: "our assumption" },
};

// Plot's browser build needs d3 loaded first.
const UNITS = `<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/dist/plot.umd.min.js" integrity="sha384-JUpn2GgRr0gxU0xOBd8D8P634jhRCwobtG8G2MMEkX1RnGJ7/FJNnuukpfT+H2w1" crossorigin="anonymous"></script>`;

// What the browser needs of the index: no checks or model notes, which are About the Model's.
function slim(ix) {
  return {
    variants: ix.variants, blockCounts: ix.blockCounts,
    city: { students: ix.city.students, levers: ix.city.levers, tallyCar: ix.city.tallyCar },
    schools: ix.schools.map((s) => ({
      cds: s.cds, name: s.name, case: s.case, charter: s.charter, private: !!s.private, lon: s.lon, lat: s.lat, students: s.students,
      ranges: Object.fromEntries(Object.entries(s.ranges || {}).map(([k, r]) => [k, { n: r.students, d: r.dropoff, p: r.pickup }])),
      blocks: s.blocks, safeToday: s.safeToday, safeBoth: s.safeBoth, inj: s.injuries5y, ej: !!s.ej,
      bt: s.blocksToNetwork, bp: s.blocksToPlan, grp: s.sfmtaGroup && s.sfmtaGroup.replace(/(\d+) m\b/g, (_, m) => `${Math.round((m * 3.28084) / 10) * 10} ft`), calmFt: s.calmFt, calmed: !!s.calmed, connFt: s.connectorFt,
      connOn: !!s.connectorOnNetwork, connOk: !!s.connector,
    })),
  };
}

const svg = (d) => `<svg viewBox="0 0 26 26" aria-hidden="true">${d}</svg>`;
const TOGGLES = [
  ["ss", "School Street Activation", "Closed to cars at bell times", svg('<circle cx="9" cy="6" r="2.5" fill="currentColor"/><circle cx="17" cy="8" r="2" fill="currentColor"/><path d="M9 9v8M6 22l3-5 3 5M17 11v6M15 22l2-5 2 5" stroke="currentColor" stroke-width="2" fill="none"/>')],
  ["calm", "15/20 mph School Zone Speed Limits", "Signs within 500 ft", svg('<path d="M3 18h20" stroke="currentColor" stroke-width="2"/><path d="M8 18c0-4 4-4 4 0M14 18c0-4 4-4 4 0" stroke="currentColor" stroke-width="2" fill="none"/>')],
  ["conn", "Protected School Connector Street", "A protected lane to bikeways", svg('<path d="M3 10h20M3 18h20" stroke="currentColor" stroke-width="2"/><path d="M6 14h3M12 14h3M18 14h3" stroke="currentColor" stroke-width="3"/>')],
  ["muni", "Free Muni for Caregivers", "A caregiver rides free with a child", svg('<rect x="4" y="4" width="18" height="15" rx="3" stroke="currentColor" stroke-width="2" fill="none"/><path d="M4 12h18" stroke="currentColor" stroke-width="2"/><circle cx="8.5" cy="21.5" r="1.5" fill="currentColor"/><circle cx="17.5" cy="21.5" r="1.5" fill="currentColor"/>')],
  ["bus", "Yellow Bus Seats", "A seat for students over 2 miles", svg('<rect x="2" y="7" width="22" height="11" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><path d="M6 7v5M11 7v5M16 7v5M21 7v5" stroke="currentColor" stroke-width="1.6"/><circle cx="7" cy="20" r="2" fill="currentColor"/><circle cx="19" cy="20" r="2" fill="currentColor"/>')],
];
const ICON = Object.fromEntries(TOGGLES.map((t) => [t[0], t[3]]));
// The City view's switches, in Bryan's order. The key is city.json's program name, or the
// street change's network variant (calm, connector), which school-sim.py keys the sets by.
const CITY_SW = [
  ["school_street", "School Street Activation", "Car-free block at the bells", ICON.ss],
  ["calm", "15/20 mph School Zone Speed Limits", "Signs within 500 ft", ICON.calm],
  ["connector", "School Connector Street", "A protected lane to bikeways", ICON.conn],
  ["caregiver_muni", "Free Muni for Caregivers", "A caregiver rides free", ICON.muni],
  ["yellow_bus", "School Shuttle Loops", "Yellow buses for TK-8 over 2 miles", ICON.bus],
  ["safer_crossings", "Safety Upgrades for Walking", "Safer crossings, calmed side streets", svg('<path d="M4 22L9 4M22 22L17 4" stroke="currentColor" stroke-width="2"/><path d="M8 18h10M9 13h8M10 8h6" stroke="currentColor" stroke-width="2.4"/>')],
  ["walking_bus", "Walking School Bus", "Paid leaders walk kids, TK to 5th", svg('<circle cx="7" cy="5" r="2.2" fill="currentColor"/><circle cx="15" cy="7" r="1.8" fill="currentColor"/><circle cx="21" cy="7" r="1.8" fill="currentColor"/><path d="M7 8v7M4 22l3-7 3 7M15 10v6M13 22l2-6 2 6M21 10v6M19 22l2-6 2 6" stroke="currentColor" stroke-width="1.8" fill="none"/>')],
  ["carpool", "Carpool Matching", "Driving families share trips", svg('<path d="M4 16l2-6h14l2 6v4H4z" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="8" cy="20" r="2" fill="currentColor"/><circle cx="18" cy="20" r="2" fill="currentColor"/><circle cx="10" cy="5" r="2" fill="currentColor"/><circle cx="16" cy="5" r="2" fill="currentColor"/>')],
  ["ebike", "E-Bike Help", "Help to try, rent or buy an e-bike", svg('<circle cx="6" cy="18" r="4" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="20" cy="18" r="4" stroke="currentColor" stroke-width="2" fill="none"/><path d="M6 18l5-8h6l3 8M11 10l-1-3h-2M15 4l-2 5h3l-2 5" stroke="currentColor" stroke-width="1.8" fill="none"/>')],
  // Four changes applied on top of city.json's sets (makeCityModel's POST), Bryan, 2026-10-14: "Can we add these
  // options to the tool?"
  ["travel_tracker", "Daily Travel Tracker", "Kids log their trip each day, TK-5", svg('<rect x="4" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><path d="M8 10l2 2 4-4M8 17h10" stroke="currentColor" stroke-width="2" fill="none"/>')],
  ["ecargo_month", "E-Cargo Bike Month", "A free month on a cargo e-bike", svg('<circle cx="5" cy="19" r="3" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="21" cy="19" r="3" stroke="currentColor" stroke-width="2" fill="none"/><path d="M8 19h9l4-8M5 19l3-6h9M17 13l-2-5h-2" stroke="currentColor" stroke-width="1.8" fill="none"/><rect x="8" y="9" width="7" height="4" stroke="currentColor" stroke-width="1.6" fill="none"/>')],
  ["curb_restriction", "Bell-Time Curb Restriction", "No stopping on the school block, TK-5", svg('<circle cx="13" cy="13" r="9" stroke="currentColor" stroke-width="2" fill="none"/><path d="M6.6 6.6l12.8 12.8" stroke="currentColor" stroke-width="2"/>')],
  // Three speed changes on the streets near schools, Bryan, 2026-10-15: "BAD with lower speed limit, humps separately,
  // and cameras with raised limit separately too". They cut kids hurt only.
  ["bad_district", "20 mph Business Districts", "Shopping streets near schools", svg('<path d="M4 11h18v11H4z" stroke="currentColor" stroke-width="2" fill="none"/><path d="M3 11l3-6h14l3 6" stroke="currentColor" stroke-width="2" fill="none"/><path d="M11 22v-6h4v6" stroke="currentColor" stroke-width="1.8" fill="none"/>')],
  ["speed_humps", "Speed Humps by Schools", "Side streets within a block", svg('<path d="M2 20h22" stroke="currentColor" stroke-width="2"/><path d="M7 20c2-6 10-6 12 0" stroke="currentColor" stroke-width="2" fill="none"/>')],
  ["speed_cameras", "Speed Cameras by Schools", "If the state lifts its cap of 33", svg('<rect x="3" y="8" width="15" height="10" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="10.5" cy="13" r="2.6" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M18 11l5-3v10l-5-3" stroke="currentColor" stroke-width="2" fill="none"/>')],
  ["bike_bus", "Bike Bus", "A led group ride to school", svg('<circle cx="5" cy="19" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="19" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="19" cy="19" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="5" cy="8" r="2" fill="currentColor"/><circle cx="12" cy="9" r="1.7" fill="currentColor"/><circle cx="19" cy="9" r="1.7" fill="currentColor"/>')],
];
// The four scenarios, the main control. Bryan, 2026-10-14: "the scenarios we care about might be maximize mode shift
// for a given $ budget, maximize injury reduction for a given $ budget, and balanced - maximize both weighted equally.
// And then the advanced options let you enable whether particular tools are available for use or not. But then the
// determiniation is still by school (or street segment) whether to do an intervention or not." So Today, and three
// budget plans, each picked school by school within one budget that also pays for the new bikeways.
const SCENARIOS = [["today", "Today"], ["car", "Best for Car Mode Shift"], ["safety", "Best for Safety"], ["balanced", "Balanced"]];
const BUDGETS = PLANS ? PLANS.budgets : [5, 10, 20, 40, 80, 100];
// SFUSD's assignment options as they stand in 2030-31, the budget plans' fourth year, when the new rules cover 52% of
// TK-5 students (makeCityModel's ASSIGN_PHASE). The Board chose Neighborhood + Citywide Programs on 2026-10-13.
// SFUSD's Board chose Neighborhood + Citywide Programs on 2026-10-13, so every scenario but Today holds it and the
// options it didn't choose are gone (Bryan, 2026-10-17: "Remove all the options SFUSD did not choose. And keep the one
// it did choose in all scenarios that aren't Today"). The list stays only so an old link's a= still parses.
const ASSIGN_OPTS = [["today", "Today"], ["assign_ncp52", "Neighborhood + Citywide Programs, the Board's choice"]];
// SFMTA's mode names, as the Travel Tally and our comment use them. Today's Muni riders include SFUSD's own school buses.
const CITY_MODES = [["car", "Single-Family Car"], ["carpool", "Carpool"], ["walk", "Walk"], ["bike", "Bike"], ["transit", "Muni"], ["bus", "School Bus or Shuttle Loop"]];
// The City view's school list: column key, heading and the small line under it.
// The sort for the each-change charts: one order for all of them, so a row sits at the same height in each.
// Two options, matching the Top 5 rankings (Bryan, 2026-10-12: "Just offer two options -- 'Safety' and 'Mode
// Shift'"): Safety by fewer kids hurt per $1M a year, the default, and Mode Shift by kids out of single-family cars
// per $1M a year. Each sorts largest first; a change with no figure (n/a or No cost) goes last. The address keeps
// its o= key; a value from an older sort falls back to Safety.
const BAR_SORTS = [["hurtEff", "Safety"], ["eff", "Mode Shift"]];
// The each-change charts mark a change's row label by whether it is a tool in SFMTA's Safe School Connections draft
// approach (September 2026) or our addition, Observable 10's first two colours (Bryan, 2026-10-12: "Highlight
// which are tools in SFMTA's draft and which are not", then "Highlight the item labels in the left instead of the
// bars"). The bars themselves are one neutral grey. Every other change, assignment and bikeways included, is ours.
const DRAFT_SW = ["school_street", "safer_crossings", "calm", "connector"];
const DRAFT_C = ["#efb118", "#4269d0"];
const CITY_JSON = nodePath.join(SIM, "city.json");
// The street changes as map lines (tools/school-trips/school-sim.py --overlays).
const OVERLAYS = nodePath.join(SIM, "overlays.json");
// Kids hurt near schools at school hours over 20 school years, for the heat map layer (tools/school-trips/school-injury-points.py).
const INJURIES = nodePath.join(SIM, "injuries.json");
// Each school's grounds and the 500 ft school zone round them, measured from the grounds as state law measures it
// (tools/school-trips/school-grounds.py).
const ZONES = nodePath.join(DATA, "school-zones.json");
// Each school's street intersections within a quarter mile and which reach of safety upgrades takes them in
// (tools/school-trips/school-kids-hurt.py).
const CROSSINGS = nodePath.join(DATA, "school-crossings.json");
// city.json as published. Past about 4 MB its per-school part goes in city-schools.json, fetched alongside,
// so the map and the totals don't wait on the school list. The split is made here because the sim writes one file.
let CITY_OUT = null;
function cityFiles() {
  if (CITY_OUT) return CITY_OUT;
  if (!fs.existsSync(CITY_JSON)) return (CITY_OUT = { main: null, schools: null });
  const raw = fs.readFileSync(CITY_JSON);
  if (raw.length <= 4e6) return (CITY_OUT = { main: raw, schools: null });
  const { schools, ...rest } = JSON.parse(raw);
  // makeCityModel needs the schools' student total before the list arrives, so the main file carries it.
  if (schools) rest.schoolStudents = schools.students.reduce((t, n) => t + n, 0);
  return (CITY_OUT = schools ? { main: Buffer.from(JSON.stringify(rest)), schools: Buffer.from(JSON.stringify(schools)) } : { main: raw, schools: null });
}

// The e-bike gate's schools on every network, for the browser's model: city.json doesn't list them, so they're read
// from the schools' own files at build time (site/src/school-trips-model.mjs, ebikeGate).
let GATE_RULE = null;
function gateRule(ix) {
  if (GATE_RULE || !fs.existsSync(CITY_JSON)) return GATE_RULE;
  const schools = ix.schools.map((s) => ({ cds: s.cds, ranges: Object.fromEntries(Object.entries(s.ranges || {}).map(([k, r]) => [k, { n: r.students }])) }));
  return (GATE_RULE = readEbikeGate(SIM, JSON.parse(fs.readFileSync(CITY_JSON, "utf8")), schools));
}

const CSS = `<style>
.masthead { padding: 10px 0 8px; margin-bottom: 8px; }
.tr-wide { width: min(1340px, 100vw - 32px); margin-left: calc(50% - min(670px, 50vw - 16px)); }
.tr-view { display: none; }
.tr-view.on { display: block; }
.tr-fail { margin: 0 0 10px; padding: 8px 12px; border: 1px solid var(--rule); border-left: 4px solid #3d4450; border-radius: 6px; background: #f4f6f8; font-weight: 600; }
.tr-grid { display: grid; grid-template-columns: 272px minmax(0, 1fr) 300px; height: calc(100dvh - 160px); min-height: 560px; border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
.tr-ctl, .tr-out { padding: 12px 14px; overflow-y: auto; font-size: 0.84rem; }
.tr-ctl { border-right: 1px solid var(--rule); }
.tr-out { border-left: 1px solid var(--rule); }
.tr-out h2 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 6px; }
.tr-ctl fieldset { border: 0; margin: 0 0 10px; padding: 0; min-width: 0; }
.tr-ctl legend { font-weight: 600; margin-bottom: 4px; padding: 0; font-size: 0.82rem; }
.tr-seg { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
.tr-seg button { border: 0; border-right: 1px solid var(--rule); background: var(--paper); padding: 6px 4px; font: inherit; font-size: 0.8rem; cursor: pointer; }
.tr-seg button:last-child { border-right: 0; }
.tr-seg button[aria-checked="true"] { background: var(--seq-3); color: #fff; font-weight: 600; }
.tr-seg button:disabled { color: var(--grey-light); cursor: default; }
.tr-hint { color: var(--muted); font-size: 0.74rem; margin: 3px 0 0; }
.tr-resets { display: flex; gap: 6px; margin-bottom: 8px; }
.tr-reset { border: 1px solid var(--rule); background: var(--paper); border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 0.8rem; cursor: pointer; }
.tr-ctl details, .tr-out details { border-top: 1px solid var(--rule); padding-top: 6px; margin-top: 8px; }
.tr-ctl summary, .tr-out summary { font-weight: 600; cursor: pointer; }
.tr-ctl details ul, .tr-out details ul { padding-left: 18px; margin: 6px 0 0; color: var(--muted); font-size: 0.78rem; }
.tr-ctl details li, .tr-out details li { margin-bottom: 3px; }
.tr-plan { background: var(--seq-3-soft); border-radius: 8px; padding: 6px 10px; margin-bottom: 8px; font-size: 0.78rem; }
.tr-plan b { display: block; }
.tr-pick { margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--rule); }
.tr-pick label { display: block; font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; margin-bottom: 3px; }
.tr-pick input { width: 100%; font: inherit; font-size: 0.95rem; font-weight: 700; padding: 6px 9px; border: 1.5px solid var(--ink); border-radius: 8px; background: var(--paper); box-sizing: border-box; }
.tr-type { margin: 2px 0 4px; font-size: 0.76rem; color: var(--muted); }
table.tr-bands, table.tr-facts { width: 100%; border-collapse: collapse; font-size: 0.76rem; font-variant-numeric: tabular-nums; }
table.tr-bands th { font-size: 0.68rem; font-weight: 600; color: var(--muted); text-align: right; padding: 1px 0 2px; border-bottom: 1px solid var(--rule); }
table.tr-bands td { text-align: right; padding: 2px 0; white-space: nowrap; }
table.tr-bands th:first-child, table.tr-bands td:first-child { text-align: left; font-weight: 700; }
table.tr-facts { margin-top: 4px; }
table.tr-facts tr { display: block; padding: 2px 0; }
table.tr-facts th, table.tr-facts td { display: block; text-align: left !important; white-space: normal !important; }
table.tr-facts th { text-align: left; font-weight: 400; color: var(--muted); padding: 1px 0; }
table.tr-facts td { text-align: right; font-weight: 600; padding: 1px 0; white-space: nowrap; }
.tr-togs { display: grid; gap: 4px; }
.tr-togs button { display: flex; align-items: center; gap: 8px; text-align: left; border: 1px solid var(--rule); background: var(--paper); border-radius: 8px; padding: 5px 8px; font: inherit; cursor: pointer; }
.tr-togs svg { width: 20px; height: 20px; flex: none; color: var(--muted); }
.tr-togs span { flex: 1; }
.tr-togs b { display: block; font-size: 0.82rem; }
.tr-togs .sw { flex: none; width: 30px; height: 18px; border-radius: 9px; background: var(--grey-light); position: relative; }
.tr-togs .sw::after { content: ""; position: absolute; left: 2px; top: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: left .15s; }
.tr-togs button[aria-checked="true"] { border-color: var(--seq-3); background: var(--seq-3-soft); }
.tr-togs button[aria-checked="true"] svg { color: var(--seq-3); }
.tr-togs button[aria-checked="true"] .sw { background: var(--seq-3); }
.tr-togs button[aria-checked="true"] .sw::after { left: 14px; }
.tr-sub { font-size: 0.76rem; font-weight: 600; margin: 8px 0 4px; }
.tr-mid { position: relative; background: var(--raised); overflow: hidden; }
.tr-mid > .tr-map { position: absolute; inset: 0; } /* over maplibre-gl.css, which sets the map relative */
.tr-kpi { position: absolute; left: 12px; right: 12px; top: 12px; background: rgba(255,255,255,.95); border-radius: 8px; padding: 8px 12px; box-shadow: 0 1px 3px rgba(0,0,0,.12); z-index: 2; }
.tr-kpi-map { right: 64px; }
.tr-kpi h1 { font-size: 1.05rem; line-height: 1.3; margin: 0; min-height: 2.6em; }
.tr-kpi h1 b { color: var(--seq-3); }
.tr-clr { position: relative; display: block; }
.tr-clr input { padding-right: 34px; width: 100%; box-sizing: border-box; }
.tr-x { position: absolute; right: 2px; top: 50%; transform: translateY(-50%); width: 32px; height: 32px; border: 0; background: none; font-size: 1.2rem; line-height: 1; color: var(--grey-dark); cursor: pointer; border-radius: 50%; }
.tr-x:hover, .tr-x:focus-visible { background: var(--rule); }
.tr-ac { position: absolute; left: 0; right: 0; top: 100%; z-index: 30; max-height: 300px; overflow-y: auto; margin: 4px 0 0; padding: 4px 0; list-style: none; background: #fff; border: 1px solid var(--rule); border-radius: 8px; box-shadow: 0 6px 18px rgba(21,24,28,.14); }
.tr-ac li { padding: 7px 10px; cursor: pointer; font-size: 0.88rem; line-height: 1.25; }
.tr-ac li small { display: block; color: var(--grey-dark); font-size: 0.74rem; }
.tr-ac li[aria-selected="true"], .tr-ac li:hover { background: #eef3f2; }
.tr-ac li.none { color: var(--grey-dark); cursor: default; background: none; }
.tr-ac li.tr-google { font-size: 0.7rem; text-align: right; padding: 4px 10px 2px; }
.tr-legend { position: absolute; left: 12px; bottom: 34px; background: rgba(255,255,255,.95); border-radius: 8px; padding: 6px 10px; font-size: 0.74rem; display: flex; flex-wrap: wrap; gap: 3px 12px; max-width: calc(100% - 24px); z-index: 2; }
.tr-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }
.tr-legend i.ln { width: 18px; height: 4px; border-radius: 2px; vertical-align: 2px; background: var(--c); }
.tr-legend i.xk { width: 8px; height: 8px; background: #fff; border: 2px solid #4269d0; }
.tr-legend i.ln.dot { background: repeating-linear-gradient(90deg, var(--c) 0 4px, transparent 4px 7px); border-radius: 0; }
.tr-m { padding: 0 0 6px; }
.tr-m .q { font-weight: 600; margin: 0 0 4px; font-size: 0.8rem; }
.tr-mchart svg { display: block; overflow: visible; }
.tr-out h2.tr-budget { margin-top: 16px; }
table.tr-mtab { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
table.tr-mtab th, table.tr-mtab td { padding: 5px 2px; border-bottom: 1px solid var(--rule); vertical-align: top; }
table.tr-mtab thead th { font-size: 0.68rem; color: var(--muted); font-weight: 600; text-align: right; }
table.tr-mtab th, table.tr-otab th, table.tr-bands th, table.tr-facts th { text-transform: none; letter-spacing: normal; }
table.tr-mtab th[scope=row] { text-align: left; font-weight: 600; font-size: 0.76rem; width: 46%; }
table.tr-mtab th[scope=row] em { display: block; font-style: normal; font-weight: 400; color: var(--muted); font-size: 0.68rem; }
table.tr-mtab td { text-align: right; font-size: 0.95rem; font-weight: 700; color: var(--muted); white-space: nowrap; }
table.tr-mtab td.s { color: var(--seq-3); }
table.tr-mtab td.tr-cw { font-size: 0.76rem; font-weight: 600; text-align: right; }
table.tr-mtab td small { display: block; font-size: 0.68rem; font-weight: 600; color: var(--muted); }
.tr-tog-ctl { display: none; }
.tr-city { display: grid; grid-template-columns: 296px minmax(0, 1fr); gap: 16px; align-items: start; }
.tr-cctl { position: sticky; top: 8px; max-height: calc(100dvh - 16px); border: 1px solid var(--rule); border-radius: 8px; box-sizing: border-box; background: var(--paper); }
.tr-card .tr-goal svg { max-width: 340px; margin: 2px 0 4px; }
.tr-cctl .tr-seg-3 button { overflow-wrap: normal; word-break: normal; hyphens: manual; font-size: 0.7rem; }
.tr-cmain { min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.tr-sum { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; }
/* Map in the middle, Impact and Budget on the right, both on the first laptop screen (docs/product/tool-ux-guidelines.md, rule 6). */
.tr-top3 { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 12px; height: calc(100dvh - 160px); min-height: 560px; }
.tr-mapcol { display: flex; flex-direction: column; min-height: 0; }
.tr-mapcol .tr-cmid { flex: 1; min-height: 0; }
.tr-top3 .tr-mapcol .tr-cmap { flex: 1; height: auto; min-height: 0; }
.tr-mapcol .tr-smap { flex: 1; height: auto; min-height: 0; }
.tr-side { display: flex; flex-direction: column; gap: 12px; overflow-y: auto; min-height: 0; }
.tr-side .tr-card { padding: 8px 12px; }
.tr-pre { display: grid; gap: 4px; }
.tr-pre button { text-align: left; border: 1px solid var(--rule); background: var(--paper); border-radius: 8px; padding: 4px 9px; font: inherit; cursor: pointer; }
.tr-pre button b { display: block; font-size: 0.8rem; }
.tr-pre button small { display: block; color: var(--muted); font-size: 0.68rem; line-height: 1.25; }
.tr-pre button[aria-checked="true"] { border-color: var(--seq-3); background: var(--seq-3-soft); box-shadow: inset 3px 0 0 var(--seq-3); }
.tr-pre button:disabled { cursor: default; }
/* Two lines kept for each summary, so nothing moves when the model loads and fills them. */
.tr-pre small[data-scen-line] { min-height: 2.5em; }
/* Six budgets in a 3 by 2 grid under their label, so every one shows in the 296 px panel and nothing moves. */
.tr-budget { display: grid; gap: 4px; margin-top: 8px; font-size: 0.72rem; color: var(--muted); }
.tr-budget .tr-seg { grid-auto-flow: row; grid-template-columns: repeat(3, 1fr); }
.tr-ctl details.tr-adv { margin: 0 0 8px; }
.tr-adv summary { margin-bottom: 6px; color: var(--ink); }
/* On a phone the four scenario cards become one dropdown, with the chosen one's summary under it (Bryan, 2026-10-13:
   "collapse to a scenario chooser dropdown that lets you open advanced options"). */
.tr-scen-m { display: none; }
.tr-scen-m select { width: 100%; font: inherit; font-weight: 600; padding: 7px 10px; border: 1px solid var(--seq-3); border-radius: 8px; background: var(--seq-3-soft); color: var(--ink); }
.tr-scen-m small { display: block; color: var(--muted); font-size: 0.72rem; line-height: 1.3; margin-top: 4px; min-height: 2.6em; }
.tr-scen-m small b { color: var(--seq-3); }
.tr-scope { margin: -4px 0 4px; }
.tr-pstate { font-weight: 400; color: var(--muted); margin-left: 4px; }
.tr-reset { float: right; font: inherit; font-size: 0.72rem; font-weight: 400; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; text-decoration-color: var(--muted); }
.tr-reset:disabled { color: var(--muted); text-decoration: none; cursor: default; }
.tr-rng { display: block; font-size: 0.66rem; font-weight: 400; color: var(--muted); }
table.tr-mtab tr.tr-subrow td { text-align: right; font-size: 0.72rem; font-weight: 400; color: var(--muted); padding-top: 0; white-space: normal; }
table.tr-mtab tr.tr-subrow td b { color: var(--seq-3); }
table.tr-mtab tr:has(+ tr.tr-subrow) > * { border-bottom: 0; }
.tr-blegend { margin: 4px 0 6px; }
.tr-tlegend.tr-blegend i { height: 9px; width: 9px; border-radius: 1px; vertical-align: 0; margin-right: 4px; }
.tr-card { border: 1px solid var(--rule); border-radius: 8px; padding: 10px 14px; font-size: 0.84rem; }
.tr-card h2, .tr-csec h2 { font-size: 1.05rem; margin: 0 0 6px; }
.tr-csec .tr-cmid { border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
.tr-csec .tr-cmap { height: min(560px, 70vh); flex: none; }
.tr-kline { margin: 0 0 8px; font-size: 0.95rem; }
.tr-kline:empty, .tr-tripkpi:empty { display: none; }
.tr-kline b { color: var(--seq-3); }
.tr-bars { display: grid; grid-template-columns: minmax(0, 3.4fr) minmax(0, 1.5fr) minmax(0, 0.9fr) minmax(0, 0.9fr) minmax(0, 1fr); grid-auto-flow: column; grid-template-rows: auto auto; column-gap: 6px; }
.tr-bars figure { display: contents; }
.tr-bars figure > div { min-width: 0; }
.tr-bars figcaption { font-weight: 700; font-size: 0.8rem; margin-bottom: 4px; min-height: 2.4em; }
.tr-bars figure:first-child figcaption { padding-left: 52%; }
.tr-bars svg { display: block; max-width: none; }
.tr-bsort { display: flex; align-items: center; gap: 8px; margin: 2px 0 10px; font-size: 0.8rem; font-weight: 600; }
.tr-bsort .tr-seg { grid-auto-columns: auto; }
.tr-bsort .tr-seg button { font-size: 0.76rem; padding: 5px 10px; white-space: nowrap; font-weight: 600; }
.tr-smap { position: relative; height: min(520px, 65vh); border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; background: var(--raised); }
.tr-smap > .tr-map { position: absolute; inset: 0; }
.tr-cmain .tr-trip { margin-top: 0; }
.tr-trip { display: grid; grid-template-columns: 272px minmax(0, 1fr); margin-top: 16px; border: 1px solid var(--rule); border-radius: 8px; }
.tr-trip > aside { padding: 12px 14px; border-right: 1px solid var(--rule); font-size: 0.84rem; }
.tr-trip h2 { font-size: 1.1rem; margin: 0 0 8px; }
.tr-trip label { display: block; font-weight: 600; font-size: 0.82rem; margin-bottom: 3px; }
.tr-trip input { width: 100%; box-sizing: border-box; font: inherit; font-size: 0.95rem; padding: 6px 9px; border: 1px solid var(--rule); border-radius: 8px; background: var(--paper); }
.tr-private { display: flex; gap: 5px; color: var(--muted); font-size: 0.74rem; margin: 4px 0 8px; }
.tr-private svg { flex: none; margin-top: 2px; }
.tr-tripcol { padding: 12px 16px 16px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.tr-tripkpi { font-size: 1.05rem; line-height: 1.35; margin: 0; min-height: 2.7em; }
.tr-tripkpi b { color: var(--seq-3); }
.tr-twomaps { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.tr-twomaps figure { margin: 0; min-width: 0; }
.tr-twomaps figcaption { font-weight: 700; font-size: 0.82rem; margin-bottom: 4px; }
.tr-twomaps .tr-tmap { position: relative; height: 300px; border-radius: 8px; overflow: hidden; background: var(--raised); }
.tr-twomaps .tr-tmap > .glmap { position: absolute; inset: 0; }
.tr-tlegend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 0.76rem; margin: 0; color: var(--grey-dark); }
.tr-tlegend i { display: inline-block; width: 18px; height: 4px; border-radius: 2px; vertical-align: 3px; margin-right: 5px; }
.tr-tlegend i.dash { background: repeating-linear-gradient(90deg, var(--grey-dark) 0 3px, transparent 3px 8px); }
table.tr-trip2 { width: 100%; border-collapse: collapse; font-size: 0.84rem; font-variant-numeric: tabular-nums; }
table.tr-trip2 th, table.tr-trip2 td { padding: 6px; border-bottom: 1px solid var(--rule); text-align: right; white-space: nowrap; }
table.tr-trip2 thead th { font-size: 0.72rem; color: var(--muted); font-weight: 600; text-transform: none; letter-spacing: normal; }
table.tr-trip2 th[scope=row] { text-align: left; font-weight: 600; text-transform: none; letter-spacing: normal; }
table.tr-trip2 td.s { color: var(--seq-3); font-weight: 700; }
table.tr-trip2 i { display: inline-block; width: 14px; height: 4px; border-radius: 2px; vertical-align: 3px; margin-right: 6px; }
.tr-tnote { color: var(--muted); font-size: 0.74rem; margin: 0; }
.tr-togs-c { gap: 3px; grid-template-columns: minmax(0, 1fr); }
.tr-togs-c button { padding: 2px 7px; gap: 7px; min-height: 34px; min-width: 0; }
.tr-togs-c button:disabled small { white-space: normal; }
.tr-togs-c svg { width: 18px; height: 18px; }
.tr-togs-c span { min-width: 0; }
.tr-togs-c b { font-size: 0.78rem; line-height: 1.2; }
.tr-togs-c small { display: block; color: var(--muted); font-size: 0.68rem; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tr-togs-c button:disabled { cursor: default; opacity: .6; }
.tr-ctl .tr-seg-3 { grid-auto-columns: minmax(0, 1fr); }
.tr-ctl .tr-seg-3 button { font-size: 0.72rem; line-height: 1.15; padding: 4px 3px; min-height: 40px; font-weight: 600; }
.tr-cmid { display: flex; flex-direction: column; }
.tr-heat { display: inline-flex; align-items: center; gap: 5px; font-size: 0.78rem; color: var(--grey-dark); cursor: pointer; }
.tr-heat small { color: var(--muted); font-variant-numeric: tabular-nums; }
.tr-zkey { display: inline-flex; align-items: center; gap: 5px; font-size: 0.78rem; color: var(--grey-dark); }
.tr-zkey i { width: 14px; height: 10px; border: 1.5px solid #4269d0; background: rgba(66,105,208,0.12); border-radius: 2px; }
.tr-mbar { display: flex; flex-wrap: wrap; gap: 6px 8px; padding: 8px 10px; background: var(--paper); border-bottom: 1px solid var(--rule); z-index: 3; }
.tr-mbar .tr-seg { grid-auto-columns: minmax(0, 1fr); }
.tr-mbar .tr-seg button { font-size: 0.76rem; padding: 5px 4px; white-space: nowrap; font-weight: 600; }
.tr-mbar [data-cmode] { grid-auto-columns: auto; grid-template-columns: 1.25fr 0.9fr 0.7fr 0.7fr 1.3fr 1fr; grid-auto-flow: row; }
.tr-mbar .tr-seg button[aria-checked="true"]:disabled { background: var(--raised); color: var(--grey-light); font-weight: 600; }
.tr-mbar [data-cmode] { flex: 1 1 100%; order: 3; }
.tr-cmap { position: relative; flex: 1; min-height: 0; }
.tr-cmap > .tr-map { position: absolute; inset: 0; }
.tr-cmap .tr-kpi { right: 64px; }
.tr-cmap .tr-kpi h1 { font-size: 0.98rem; }
.tr-clegend { width: 230px; flex-direction: column; gap: 2px; }
.tr-clegend b { font-size: 0.72rem; white-space: nowrap; }
.tr-clegend span { white-space: nowrap; }
.tr-clegend i { border: 1px solid rgba(21,24,28,.25); box-sizing: border-box; }
.tr-clegend small { color: var(--muted); }
.tr-clegend .tr-ramp { display: flex; height: 10px; margin: 2px 0 0; border: 1px solid rgba(21,24,28,.25); border-radius: 2px; overflow: hidden; }
.tr-clegend .tr-ramp i { flex: 1; width: auto; height: auto; border: 0; border-radius: 0; margin: 0; }
.tr-clegend .tr-ramp-t { position: relative; display: block; height: 1.3em; margin-bottom: 2px; }
.tr-clegend .tr-ramp-t em { position: absolute; top: 0; transform: translateX(-50%); font-style: normal; font-size: 0.68rem; color: var(--grey-dark); font-variant-numeric: tabular-nums; }
[data-city-res] table.tr-mtab th, [data-city-res] table.tr-mtab td { padding: 3px 2px; }
table.tr-ctab { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; margin-top: 6px; }
table.tr-ctab th, table.tr-ctab td { padding: 3px 2px; border-bottom: 1px solid var(--rule); vertical-align: top; text-transform: none; letter-spacing: normal; }
table.tr-ctab th { text-align: left; font-weight: 600; font-size: 0.76rem; }
table.tr-ctab th em { display: block; font-style: normal; font-weight: 400; color: var(--muted); font-size: 0.68rem; }
table.tr-ctab td { text-align: right; font-weight: 700; font-size: 0.92rem; color: var(--seq-3); white-space: nowrap; }
.tr-goal svg { display: block; width: 100%; height: auto; }
.tr-cnote { color: var(--muted); font-size: 0.7rem; margin: 4px 0 0; }
.tr-pop .maplibregl-popup-content { padding: 8px 10px; font-size: 0.76rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,.18); }
.tr-pop b { display: block; font-size: 0.8rem; margin-bottom: 3px; }
.tr-pop table { border-collapse: collapse; font-variant-numeric: tabular-nums; }
.tr-pop th, .tr-pop td { padding: 1px 4px 1px 0; text-align: right; font-size: 0.74rem; text-transform: none; letter-spacing: normal; border: 0; }
.tr-pop th { text-align: left; font-weight: 400; color: var(--muted); }
.tr-pop thead th { text-align: right; font-size: 0.66rem; }
.tr-pop td.s { color: var(--seq-3); font-weight: 700; }
@media (max-width: 860px) {
  .tr-grid { display: flex; flex-direction: column; height: auto; min-height: 0; }
  .tr-ctl { border-right: 0; border-bottom: 1px solid var(--rule); overflow: visible; }
  .tr-scen .tr-pre { display: none; }
  .tr-scen-m { display: block; }
  .tr-tog-ctl { display: flex; width: 100%; justify-content: space-between; border: 1px solid var(--rule); background: var(--paper); border-radius: 8px; padding: 8px 12px; font: inherit; font-weight: 600; cursor: pointer; }
  .tr-ctl-body { display: none; margin-top: 10px; }
  .tr-ctl.open .tr-ctl-body { display: block; }
  .tr-mid { height: 46vh; min-height: 320px; }
  .tr-cmid { height: auto; }
  .tr-cmap { height: 46vh; min-height: 320px; flex: none; }
  .tr-mbar { padding: 6px; }
  .tr-mbar .tr-seg button { font-size: 0.68rem; padding: 5px 2px; white-space: normal; }
  .tr-mbar [data-cmode] { flex: 1 1 100%; }
  .tr-clegend { width: auto; left: 8px; bottom: 30px; font-size: 0.68rem; }
  .tr-kpi { left: 8px; right: 8px; top: 8px; }
  .tr-kpi-map { top: 52px; right: 8px; }
.tr-kpi h1 { font-size: 0.92rem; }
  .tr-out { border-left: 0; overflow: visible; padding-bottom: 40px; }
  .tr-city { grid-template-columns: 1fr; gap: 12px; }
  /* Not sticky on a phone: pinned, the panel covered a third of the screen over the map and figures. */
  .tr-cctl { position: static; max-height: none; padding: 8px; }
  .tr-cctl.open .tr-ctl-body { max-height: 65vh; overflow-y: auto; }
  .tr-sum { grid-template-columns: 1fr; }
  .tr-bars { display: block; }
  .tr-bsort { align-items: flex-start; flex-direction: column; gap: 4px; }
  .tr-bsort .tr-seg { grid-auto-flow: row; grid-template-columns: 1fr 1fr; }
  .tr-bsort .tr-seg button { white-space: normal; border-bottom: 1px solid var(--rule); }
  .tr-bars figure { display: block; margin: 0 0 14px; }
  .tr-bars figure:first-child figcaption, .tr-bars figcaption { padding-left: 0; font-size: 0.82rem; min-height: 0; }
  .tr-top3 { display: block; height: auto; min-height: 0; }
  .tr-top3 .tr-mapcol .tr-cmap, .tr-mapcol .tr-smap { flex: none; height: 60vh; min-height: 320px; }
  .tr-side { overflow: visible; margin-top: 12px; }
  .tr-csec .tr-cmap, .tr-smap { height: 60vh; min-height: 320px; }
  .tr-cctl:not(.open) .tr-pick table, .tr-cctl:not(.open) .tr-type { display: none; }
  .tr-trip { grid-template-columns: 1fr; }
  .tr-trip > aside { border-right: 0; border-bottom: 1px solid var(--rule); }
  .tr-twomaps { grid-template-columns: 1fr; }
  .tr-twomaps .tr-tmap { height: 240px; }
  table.tr-trip2 { font-size: 0.72rem; }
  table.tr-trip2 th, table.tr-trip2 td { padding: 5px 2px; }
  table.tr-trip2 thead th { white-space: normal; }
  table.tr-trip2 i { display: none; }
}
</style>`;

// The Scenarios radio group heads both views' controls, and every detailed control sits under Advanced Controls,
// shut until opened (Bryan, 2026-10-12: "move all of the other detailed items under advanced controls"). Each
// scenario prints what it holds and its yearly budget, filled in by the browser once the model has loaded.
const scenHtml = `<fieldset class="tr-scen"><legend>Scenarios <small class="tr-pstate" data-scen-state></small><button type="button" class="tr-reset" data-reset disabled>Reset</button></legend><div class="tr-pre" role="radiogroup" aria-label="Scenarios">${SCENARIOS.map(([k, l]) => `<button type="button" role="radio" data-scen="${k}" aria-checked="false"><b>${l}</b><small data-scen-line="${k}">&nbsp;</small></button>`).join("")}</div><div class="tr-scen-m"><select data-scen-pick aria-label="Scenario">${SCENARIOS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}<option value="" disabled>Custom</option></select><small data-scen-pick-line>&nbsp;</small></div><div class="tr-budget"><span>Budget, over 4 years</span><div class="tr-seg" role="radiogroup" aria-label="Budget, over 4 years" data-budget>${BUDGETS.map((b) => `<button type="button" role="radio" data-v="${b}">$${b}M</button>`).join("")}</div></div></fieldset>`;
const advHtml = (togsHint) => `<details class="tr-adv"><summary>Advanced Controls</summary>
      <fieldset>
        <legend>Changes the Plans May Use</legend>
        <div class="tr-togs tr-togs-c">${ctogs}</div>${togsHint ? `\n        <p class="tr-hint" data-togs-hint></p>` : ""}
        <p class="tr-hint">Turn one off and the plan picks again without it. Each plan still decides school by school, and for new bikeways block by block, on or off the <a href="${PLAN_URL}">Biking and Rolling Plan</a>.</p>
      </fieldset>
      </details>
      <p class="tr-cnote"><a href="${MODEL_PATH}">About School Trips</a></p>`;
// One switch per change the plans may use, the new bikeways last.
const AVAIL_SW = CITY_SW.concat([["seg", "New Bikeways", "All Ages and Abilities blocks, $5M to $100M", svg('<path d="M3 21L11 5M23 21L15 5" stroke="currentColor" stroke-width="2"/><circle cx="9" cy="17" r="2.2" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="17" cy="17" r="2.2" stroke="currentColor" stroke-width="1.6" fill="none"/>')]]);
const ctogs = AVAIL_SW.map(([k, b, h, ic]) => `<button type="button" role="switch" data-csw="${k}" aria-checked="true">${ic}<span><b>${b}</b><small>${h}</small></span><i class="sw"></i></button>`).join("");

// The Citywide Goals view's wedges at every combination of steps, written by tools/school-trips/school-trips-figures.mjs.
const WEDGE_T = figure("school-trips.wedges");

function body(ix) {
  return `
<div class="tr-wide">
${wedgeView(WEDGE_T)}

<section class="tr-view" id="v-city" aria-label="Citywide scenarios">
<div class="tr-city">
  <aside class="tr-ctl tr-cctl">
    ${scenHtml}
    <button class="tr-tog-ctl" type="button" data-ctl-toggle><span data-ctl-sum="city">Changes</span><span>Advanced Options</span></button>
    <div class="tr-ctl-body">
      ${advHtml(false)}
    </div>
  </aside>
  <div class="tr-cmain">
    <div class="tr-top3">
    <section class="tr-csec tr-mapcol" aria-labelledby="tr-map-h">
      <h2 id="tr-map-h">Where Students Live and How They Get to School</h2>
      <p class="tr-hint tr-scope">SFUSD, charter and private school students.</p>
      <p class="tr-kline" data-city-kpi></p>
      <div class="tr-cmid">
    <div class="tr-mbar">
      <div class="tr-seg" role="radiogroup" aria-label="Way to school" data-cmode>${CITY_MODES.map(([k, l]) => `<button type="button" role="radio" data-v="${k}">${l}</button>`).join("")}</div>
      <label class="tr-heat"><input type="checkbox" data-heat> Kids hurt near schools at school hours, 20 years <small data-heat-n="city"></small></label>
      <span class="tr-zkey"><i></i>500 ft school zone, from the school grounds</span>
    </div>
        <div class="tr-cmap">
          <div class="tr-map glmap" data-city-map role="img" aria-label="Map of San Francisco's home blocks, each a circle sized by its students"></div>
          <div class="tr-legend tr-clegend" data-city-legend></div>
        </div>
      </div>
    </section>
    <div class="tr-side">
      <section class="tr-card" aria-labelledby="tr-imp-h"><h2 id="tr-imp-h">Impact Citywide</h2><div data-city-res></div></section>
      <section class="tr-card" aria-labelledby="tr-bud-h"><h2 id="tr-bud-h">Budget</h2><div data-city-budget></div></section>
    </div>
    </div>
    <section class="tr-csec" aria-labelledby="tr-safe-h">
      <h2 id="tr-safe-h">Safe Trip in 15 Minutes</h2>
      <p class="tr-kline" data-safe-kpi></p>
      <div class="tr-cmid">
        <div class="tr-cmap">
          <div class="tr-map glmap" data-safe-map role="img" aria-label="Map of San Francisco's home blocks, shaded by the share of students with a safe walk or bike trip of 15 minutes"></div>
          <div class="tr-legend tr-clegend" data-safe-legend></div>
        </div>
      </div>
    </section>
    <section class="tr-csec" aria-labelledby="tr-bars-h">
      <h2 id="tr-bars-h">What Each Change Does on Its Own</h2>
      <p class="tr-hint">Each bar is one change alone against today, with our low to high estimate in brackets. Changes overlap, so bars don't add up. A walk or bike trip on an ordinary street carries more risk than a car trip, so a change that moves kids onto those streets can add injuries.</p>
      <p class="tr-tlegend tr-blegend"><span><i style="background:${DRAFT_C[1]}"></i>In <a href="https://www.sfmta.com/safe-school-connections-draft-approach-september-2026">SFMTA's Draft</a></span><span><i style="background:${DRAFT_C[0]}"></i>Our Addition</span></p>
      <div class="tr-bsort"><span id="tr-bsort-l">Sort by</span><div class="tr-seg" role="radiogroup" aria-labelledby="tr-bsort-l" data-bsort>${BAR_SORTS.map(([k, l]) => `<button type="button" role="radio" data-v="${k}">${l}</button>`).join("")}</div></div>
      <div class="tr-bars"><figure><figcaption>Kids Out of Single-Family Cars</figcaption><div data-bars="car"></div></figure><figure><figcaption>Fewer Kids Hurt a Year</figcaption><div data-bars="hurt"></div></figure><figure><figcaption>Fewer Kids Hurt per $1M a Year</figcaption><div data-bars="hurtEff"></div></figure><figure><figcaption>Kids Out of Cars per $1M a Year</figcaption><div data-bars="eff"></div></figure><figure><figcaption>Cost a Year</figcaption><div data-bars="yr"></div></figure></div>
      <p class="tr-hint">A year's cost is the yearly cost plus the one-time cost spread over 4 years. SFUSD assignment has no cost here.</p>
    </section>
  </div>
</div>
</section>

<section class="tr-view" id="v-school" aria-label="Your school">
<div class="tr-city">
  <aside class="tr-ctl tr-cctl">
    <div class="tr-pick">
      <label for="tr-school">School</label>
      <span class="tr-clr"><input id="tr-school" type="text" data-school-pick placeholder="Search ${ix.schools.length} schools" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="tr-school-list" aria-autocomplete="list"><button type="button" class="tr-x" data-clear="tr-school" aria-label="Clear the school">&times;</button><ul class="tr-ac" id="tr-school-list" role="listbox" aria-label="Schools" hidden data-school-list></ul></span>
      <p class="tr-type" data-school-type></p>
      <table class="tr-bands"><thead><tr><th>Grades</th><th>Students</th><th>Drop-off</th><th>Pickup</th></tr></thead><tbody data-bands></tbody></table>
      <table class="tr-facts"><tbody data-facts></tbody></table>
    </div>
    ${scenHtml}
    <button class="tr-tog-ctl" type="button" data-ctl-toggle><span data-ctl-sum="school">Changes</span><span>Advanced Options</span></button>
    <div class="tr-ctl-body">
      <p class="tr-hint">The same scenario as Citywide Scenarios. A change here changes it there too.</p>
      ${advHtml(true)}
    </div>
  </aside>
  <div class="tr-cmain">
    <div class="tr-top3">
    <section class="tr-csec tr-mapcol" aria-labelledby="tr-smap-h">
      <h2 id="tr-smap-h">Where Its Students Live</h2>
      <p class="tr-kline" data-school-kpi></p>
      <div class="tr-smap">
        <div class="tr-map glmap" data-school-map role="img" aria-label="Map of where the school's students are expected to live"></div>
    <div class="tr-legend">
      <span><i style="background:var(--seq-3)"></i>Within 15 minutes on safe streets</span>
      <span><i style="background:var(--grey-light)"></i>Not yet</span>
      <span><i class="ln" style="--c:#4269d0;opacity:0.55"></i>Bikeways today</span>
      <span><i class="ln" style="--c:#4269d0"></i>New bikeways and this school's connector</span>
      <span data-x-key hidden><i class="xk"></i>Intersections safety upgrades would treat</span>
      <span data-ss-key hidden><i class="ln" style="background:var(--ink)"></i>School Street activation, closed to cars at the bells</span>
      <span class="tr-zkey"><i></i>500 ft school zone, from the school grounds</span>
      <label class="tr-heat"><input type="checkbox" data-heat> Kids hurt near schools at school hours, 20 years <small data-heat-n="school"></small></label>
    </div>
      </div>
    </section>
    <div class="tr-side">
      <section class="tr-card" aria-labelledby="tr-simp-h"><h2 id="tr-simp-h">Impact at This School</h2><div data-school-res></div></section>
      <section class="tr-card" aria-labelledby="tr-sbud-h"><h2 id="tr-sbud-h">Budget for This School</h2><div data-school-budget></div></section>
    </div>
    </div>
<section class="tr-trip" aria-labelledby="tr-trip-h">
  <aside>
    <h2 id="tr-trip-h">Your Trip</h2>
    <label for="tr-addr">Your address</label>
    <span class="tr-clr"><input id="tr-addr" type="text" autocomplete="off" placeholder="For example, 400 Monterey Blvd" data-addr role="combobox" aria-expanded="false" aria-controls="tr-addr-list" aria-autocomplete="list"><button type="button" class="tr-x" data-clear="tr-addr" aria-label="Clear the address">&times;</button><ul class="tr-ac" id="tr-addr-list" role="listbox" aria-label="Addresses" hidden data-addr-list></ul></span>
    <p class="tr-private"><svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true"><rect x="2" y="6" width="10" height="7" rx="1.5" fill="currentColor"/><path d="M4.5 6V4a2.5 2.5 0 015 0v2" stroke="currentColor" stroke-width="1.5" fill="none"/></svg><span>${BASEMAP.key ? "Address suggestions come from Google, which sees what you type. We don't record your address." : "Your address stays in your browser. We don't record it."}</span></p>
    <p class="tr-hint">Or click your home on either map. The scenario is the one set above.</p>
  </aside>
  <div class="tr-tripcol">
    <h3 class="tr-tripkpi" data-trip-kpi></h3>
    <div class="tr-twomaps">
      <figure><figcaption>Today</figcaption><div class="tr-tmap"><div class="glmap" data-trip-map="0" role="img" aria-label="Map of your routes to school today"></div></div></figure>
      <figure><figcaption data-scen-name>Balanced</figcaption><div class="tr-tmap"><div class="glmap" data-trip-map="1" role="img" aria-label="Map of your routes to school with the chosen scenario"></div></div></figure>
    </div>
    <p class="tr-tlegend"><span><i style="background:#2f7d76"></i>Walk</span><span><i style="background:#c8a25e"></i>Bike</span><span><i style="background:#3d4450"></i>Car</span><span><i class="dash"></i>Dashed where it's off safe streets</span><span><i style="background:var(--grey-dark);opacity:.45;height:2px"></i>Safe streets today</span><span><i style="background:var(--seq-2);height:6px;opacity:.6"></i>Made safe by the scenario</span><span><i style="width:10px;height:10px;border-radius:50%;background:var(--ink);vertical-align:-1px"></i>Home</span><span><i style="width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid var(--ink);box-sizing:border-box;vertical-align:-1px"></i>School</span></p>
    <div data-trip-table></div>
    <p class="tr-tnote" data-trip-note></p>
  </div>
</section>
  </div>
</div>
</section>
</section>
${commentView()}
</div>

<script type="application/json" id="tr-data">${inlineJson({ ix: slim(ix), costs: Object.fromEntries(Object.entries(COSTS).map(([k, c]) => [k, c.v])), toggles: TOGGLES.map((t) => [t[0], t[1]]), citySw: CITY_SW.map((t) => [t[0], t[1]]), draftSw: DRAFT_SW, draftC: DRAFT_C, barSorts: BAR_SORTS.map((t) => t[0]), citySplit: !!cityFiles().schools, rules: { connector: (RULES || {}).connector || {}, muniFar: (RULES || {}).muniFar || 0, injury: HURT.model, gate: gateRule(ix) }, assignOpts: ASSIGN_OPTS, cityModes: CITY_MODES, scenarios: SCENARIOS, plans: PLANS ? PLANS.plans : null, table: PLANS ? PLANS.table : null, planBg: PLANS ? PLANS.background : null, budgets: BUDGETS, avail: AVAIL_SW.map((t) => t[0]), gkey: BASEMAP.key || null, wedges: { T: WEDGE_T, W: wedgeClientData(), plan: PLAN_STEPS, full: FULL_STEPS } })}</script>
${MAP_HEAD}${UNITS}
<script>${fnSource(makeRouter)}</script>
<script>${fnSource(makeCityModel)}</script>
<script>${fnSource(wedgeUI)}</script>
<script>const VKEYS = ${JSON.stringify(VKEYS)};
${fnSource(planGreedy)}
${fnSource(tableSum)}
${fnSource(planAll)}
${fnSource(replanHurt)}</script>
<script>(${fnSource(client)})();</script>`;
}

// ---------------------------------------------------------------------------------
// The browser half. Written as a real function so it can use template strings;
// its source is copied into the page.
function client() {
  const D = JSON.parse(document.getElementById("tr-data").textContent);
  // Files beside the page, found from the page's own address so a mount under a prefix works too.
  D.base = location.pathname.replace(/\/(index\.html)?$/, "");
  const IX = D.ix, COST = D.costs, SCH = IX.schools;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const sig2 = (x) => Number(Number(x).toPrecision(2));
  // Counts print in full, not rounded (Bryan, 2026-10-09: "Can you make it not round?").
  const n2 = (x) => (x == null || !isFinite(x) ? "n/a" : Math.round(x).toLocaleString("en-US"));
  const pct = (x) => (Math.round(x * 10) / 10).toFixed(1) + "%";
  const money = (m) => "$" + (m >= 9.5 ? Math.round(m) : sig2(m)) + "M";
  const byName = Object.fromEntries(SCH.map((s) => [s.name, s]));
  const byCds = Object.fromEntries(SCH.map((s) => [s.cds, s]));

  // ---------- state, carried across the views and in the address ----------
  const DEF_SCHOOL = (SCH.find((s) => s.case === "carmichael") || SCH[0]).cds;
  // The City opens on Balanced at $20M (Bryan, 2026-10-14), with a reset back to it. c.seg holds the new bikeways'
  // budget in $M.
  const CSW = D.citySw.map((t) => t[0]), AV = D.avail;
  const CITY_OFF = { ...Object.fromEntries(CSW.map((k) => [k, 0])), assign: "today", seg: 0, xreach: 350 };
  // Today is every change off, at today's assignment. Each plan holds the Neighborhood + Citywide Programs assignment
  // the Board adopted on 2026-10-13. The plans come from tools/school-trips/school-budget-plans.mjs: for a budget over 4 years, the
  // changes at each school and the citywide steps, new bikeways among them, that take the most students out of
  // single-family cars, spare the most kids hurt, or both, picked by gain per dollar. A plan funds different changes at
  // different schools, so it can't be one set of the switches: choosing one turns on every change it funds anywhere and
  // marks the plan, and its figures come from the plan's own totals.
  // The plans are built on the Board's choice at its 2030-31 share; the assignment control can swap it.
  const PLAN_BG = D.planBg || "assign_ncp52";
  const bgC = () => ({ ...CITY_OFF, assign: S.assign });
  // The City's sets and model, loaded once (cityData below).
  // CJ and MD are set together, only once the model is built, so a failure never leaves the data without its model.
  // CJERR holds the failure, shown on the page.
  let CJ = null, CJP = null, MD = null, CJERR = null;
  const PL = D.plans || {}, TB = D.table;
  const GOAL0 = "balanced", BUDGET0 = D.budgets.includes(20) ? 20 : D.budgets[0];
  const allOn = () => AV.every((k) => S.avail[k] !== 0);
  // A plan with some changes turned off, re-picked in the browser by the same greedy on the same table the build used
  // (site/src/school-trips-plan.mjs). Its figures are the full plan's, moved by the table's difference between the two
  // picks, in the central case the table is scored in. Close, not exact; About School Trips says by how much.
  const rpMemo = {};
  function replan(goal, budget) {
    const key = goal + budget + "|" + AV.map((k) => (S.avail[k] === 0 ? 0 : 1)).join("");
    if (rpMemo[key]) return rpMemo[key];
    const P0 = PL[goal + budget];
    if (!P0 || !TB) return null;
    const sel = planAll(TB, budget, S.avail)[goal], base = planAll(TB, budget)[goal];
    const dA = tableSum(TB, sel), dB = tableSum(TB, base), dv = dA.v.map((x, q) => x - dB.v[q]);
    const schools = {}, count = {}, city = { seg: 0, carpool: 0, calm: 0, muni: 0 };
    sel.forEach((j, i) => {
      if (j < 0) return;
      const sl = TB.slots[i], L = sl.levels[j];
      if (sl.cds) { (schools[sl.cds] = schools[sl.cds] || []).push(L.id); count[L.id] = (count[L.id] || 0) + 1; }
      else Object.assign(city, L.patch);
    });
    const V = (name) => dv[VKEYS.indexOf(name)], pos = (x) => Math.max(0, x);
    const at = {};
    for (const [r, a] of Object.entries(P0.at)) {
      const carsBy = { ...a.carsBy }, hurt = replanHurt(TB, a.H, dA, dB, TB.hb);
      for (const [id, x] of Object.entries(dB.carsBy)) carsBy[id] = (carsBy[id] || 0) - x;
      for (const [id, x] of Object.entries(dA.carsBy)) carsBy[id] = (carsBy[id] || 0) + x;
      for (const id of Object.keys(carsBy)) if (carsBy[id] <= 0.05) delete carsBy[id];
      at[r] = { modes: a.modes.map((x, q) => pos(x + dv[q])), min: pos(a.min + V("min")), alone: pos(a.alone + V("alone")), safe: pos(a.safe + V("safe")),
        hurt, once: pos(a.once + V("once")), year: pos(a.year + V("year")), people: pos(a.people + V("people")),
        st: { ss: pos(a.st.ss + V("ss")), drv: pos(a.st.drv + V("drv")), pool: pos(a.st.pool + V("pool")) }, carsBy };
    }
    return (rpMemo[key] = { goal, budget, city, count, schools, at, replanned: true });
  }
  // Under another assignment, a plan's figures move by the two assignments' own difference: the cars and minutes
  // from the City's sets, the kids hurt multiplied out and back in. The assignment costs nothing.
  const abMemo = {};
  function withAssign(p) {
    if (!p || S.assign === PLAN_BG || !MD) return p;
    const key = p.goal + p.budget + (p.replanned ? "r" + AV.map((k) => (S.avail[k] === 0 ? 0 : 1)).join("") : "") + "|" + S.assign;
    if (abMemo[key]) return abMemo[key];
    const at = {};
    for (const [r, a] of Object.entries(p.at)) {
      const A = MD.figC({ ...MD.OFF, assign: S.assign }), B = MD.figC({ ...MD.OFF, assign: PLAN_BG });
      const hn = S.assign === "today" ? null : MD.alone(S.assign), hb = MD.alone(PLAN_BG);
      const hurt = a.hurt.map((h, k) => MD.HB * (1 - (1 - h / MD.HB) * (1 - (hn ? hn.hurt[k] : 0) / MD.HB) / (1 - hb.hurt[k] / MD.HB)));
      at[r] = { ...a, modes: a.modes.map((x, i) => Math.max(0, x + A.modes[i] - B.modes[i])), min: a.min + (A.min || 0) - (B.min || 0), alone: a.alone + (A.solo || 0) - (B.solo || 0), hurt };
    }
    return (abMemo[key] = { ...p, at });
  }
  const planFor = (goal, budget = S.budget) => withAssign(!goal || !PL[goal + budget] ? null : allOn() ? PL[goal + budget] : replan(goal, budget));
  const plan = () => planFor(S.city.plan);
  const ON_PLAN = (c, id) => { if (id.startsWith("xing") || id === "safer_crossings") { c.safer_crossings = 1; c.xreach = Math.max(c.xreach || 350, id === "safer_crossings" ? 350 : Number(id.slice(4))); } else c[id] = 1; };
  function planC(goal) {
    const p = planFor(goal);
    if (!p) return null;
    const c = { ...bgC(), seg: p.city.seg || 0, carpool: p.city.carpool ? 1 : 0, calm: p.city.calm ? 1 : 0, caregiver_muni: p.city.muni ? 1 : 0, xreach: 350, plan: goal };
    for (const ids of Object.values(p.schools)) ids.forEach((id) => ON_PLAN(c, id));
    return c;
  }
  // One school's own changes under the plan, with the plan's citywide steps.
  function cityFor(cds) {
    const p = plan();
    if (!p) return S.city;
    const c = { ...bgC(), seg: p.city.seg || 0, carpool: p.city.carpool ? 1 : 0, calm: p.city.calm ? 1 : 0, caregiver_muni: p.city.muni ? 1 : 0, xreach: 350, mode: S.city.mode };
    (p.schools[cds] || []).forEach((id) => { if (id === "safer_crossings" || id.startsWith("xing")) { c.safer_crossings = 1; c.xreach = id === "safer_crossings" ? 350 : Number(id.slice(4)); } else c[id] = 1; });
    return c;
  }
  const SCEN = Object.fromEntries(D.scenarios.map(([k]) => [k, k === "today" ? { c: CITY_OFF } : PL[k + D.budgets[0]] ? { plan: k } : null]));
  const pickScen = (k) => { const sc = SCEN[k]; if (sc) Object.assign(S.city, sc.plan ? planC(sc.plan) : { ...sc.c, plan: null }); };
  const SCEN_NAME = Object.fromEntries(D.scenarios);
  const SHORT = { school_street: "School Streets", calm: "speed limits", connector: "School Connectors", caregiver_muni: "free Muni",
    yellow_bus: "shuttle loops", safer_crossings: "walking upgrades", xing660: "walking upgrades to 2 blocks", xing1320: "walking upgrades to 1/4 mile", walking_bus: "walking school buses", carpool: "carpools", ebike: "e-bike help",
    travel_tracker: "travel trackers", ecargo_month: "e-cargo bike months", curb_restriction: "curb restrictions", bike_bus: "bike buses",
    bad_district: "20 mph business districts", speed_humps: "speed humps", speed_cameras: "speed cameras",
    assign_nas: "Neighborhood + All Schools", assign_ncp: "Citywide Programs assignment", assign_nas52: "Neighborhood + All Schools", assign_ncp52: "Citywide Programs assignment" };
  const ONE = { school_street: "a School Street", walking_bus: "a walking school bus", safer_crossings: "walking upgrades within 1 block",
    xing660: "walking upgrades within 2 blocks", xing1320: "walking upgrades within 1/4 mile", connector: "a School Connector",
    caregiver_muni: "free Muni for caregivers", yellow_bus: "a shuttle loop", ebike: "e-bike help", calm: "school zone speed limits",
    travel_tracker: "a daily travel tracker", ecargo_month: "an e-cargo bike month", curb_restriction: "a bell-time curb restriction", bike_bus: "a bike bus",
    bad_district: "20 mph business districts", speed_humps: "speed humps", speed_cameras: "a speed camera" };
  const andList = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
  // A plan in a line: how many schools get each change, most first, then its citywide steps.
  function planLine(p) {
    const n = {};
    for (const [id, k] of Object.entries(p.count)) { const g = id.startsWith("xing") ? "safer_crossings" : id; n[g] = (n[g] || 0) + k; }
    const parts = Object.entries(n).sort((a, b) => b[1] - a[1]).map(([id, k], i) => `${SHORT[id] || id} at ${k}${i ? "" : " schools"}`);
    if (p.city.seg) parts.push(`$${p.city.seg}M of new bikeways`);
    if (p.city.carpool) parts.push("carpool matching");
    if (p.city.calm) parts.push("speed limits at every school");
    if (p.city.muni) parts.push("free Muni for caregivers citywide");
    return parts.join(", ");
  }
  const sameAs = (p) => CSW.every((k) => !!S.city[k] === !!p[k]) && S.city.assign === p.assign && (S.city.seg || 0) === (p.seg || 0)
    && (!S.city.safer_crossings || (S.city.xreach || 350) === (p.xreach || 350));
  // The scenario the settings match: a plan, or Today.
  const scenOf = () => (plan() ? S.city.plan : sameAs(CITY_OFF) ? "today" : null);
  // The chosen scenario's name, for a column beside Today, and as a sentence's "With ..." phrase.
  const scenCol = () => { const k = scenOf(); return k ? SCEN_NAME[k] : "Custom"; };
  const withScen = (t) => (scenOf() === "today" ? "" : ` With ${scenOf() ? SCEN_NAME[scenOf()] : "your custom changes"} ${t}`);
  function scenSummary(k) {
    if (k === "today") return "No changes. How students get to school now.";
    const p = SCEN[k] && planFor(SCEN[k].plan);
    if (!p) return "\u00a0";
    const t = planLine(p);
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  const VIEW0 = { mode: "car" };
  // Every figure is the sim's central case at year 10, with its low to high range beside it; no control moves the case.
  const S = { budget: BUDGET0, assign: PLAN_BG, avail: Object.fromEntries(AV.map((k) => [k, 1])), heat: false, bsort: "hurtEff", view: "goals", city: { ...CITY_OFF, ...VIEW0 }, school: { cds: DEF_SCHOOL } };
  Object.assign(S.city, planC(GOAL0) || {});
  const atStart = () => S.city.plan === GOAL0 && S.budget === BUDGET0 && allOn() && S.assign === PLAN_BG;
  // ranking.json's distance to a network: "1 block", "2 blocks", "quarter mile" (within one) or "beyond".
  const blkLong = (b) => (b === "beyond" ? "Over a quarter mile" : b === "quarter mile" ? "Within a quarter mile" : b == null ? "n/a" : b);
  const MODES = [["Car", "car", "#b3b8bf", "#15181c"], ["Carpool", "carpool", "#d5d9de", "#15181c"], ["Walk", "walk", "#2f7d76", "#fff"], ["Bike", "bike", "#c8a25e", "#15181c"], ["Muni or\nschool bus", "transit", "#9c5f3c", "#fff"], ["New\nyellow bus", "bus", "#6f7f94", "#fff"]];

  // ---------- outcome panel, shared by both views ----------
  function metricsHtml(T, X, N, scen) {
    const data = JSON.stringify({ t: T.modes.map((v) => 100 * v / N), s: X.modes.map((v) => 100 * v / N), scen, N }).replace(/'/g, "&#39;");
    const c = (v) => (v == null ? "…" : `${n2(v)}<small>${pct(100 * v / N)}</small>`);
    const row = (q, a, b) => `<tr><th scope="row">${q}</th><td>${a}</td><td class="s">${b}</td></tr>`;
    return `<div class="tr-m"><p class="q">How students get there</p><div class="tr-mchart" data-mode='${data}'></div></div>`
      + `<table class="tr-mtab"><thead><tr><th></th><th>Today</th><th>${scen}</th></tr></thead><tbody>`
      + row("Come by single-family car<em>students</em>", c(T.modes[0]), c(X.modes[0]))
      + row("Safe trip in 15 minutes<em>students, walking or biking</em>", c(T.safe), c(X.safe))
      + row("No parent needed<em>students who get there without their own parent</em>", c(T.alone), c(X.alone))
      + `</tbody></table>`;
  }
  function drawModes(root) {
    $$("[data-mode]", root).forEach((el) => {
      const d = JSON.parse(el.dataset.mode);
      if (!window.Plot) { el.textContent = "The chart needs Observable Plot, which didn't load."; return; }
      const rows = [["Today", d.t, 0], [d.scen, d.s, 1.75]], segs = [], links = [];
      rows.forEach(([lab, v, y]) => { let x = 0; v.forEach((p, i) => { segs.push({ lab, m: MODES[i], x1: x, x2: x + p, y1: y, y2: y + 1, p, c: d.N * p / 100 }); x += p; }); });
      const top = segs.filter((q) => q.y1 === 0), bot = segs.filter((q) => q.y1 > 0);
      for (let i = 0; i < MODES.length - 1; i++) links.push({ x1: top[i].x2, x2: bot[i].x2 });
      const W = Math.max(240, el.clientWidth || 260), big = (q) => q.p >= 9, iw = W - 48;
      const k = (c) => (c >= 1000 ? (c / 1000).toFixed(c >= 10000 ? 0 : 1) + "k" : n2(c));
      // Every mode gets a label. A wide segment carries its figures inside; a narrow one gets them in a
      // callout, spread sideways so callouts never overlap, with a line back to its segment.
      const spread = (items) => {
        const px = (x) => x / 100 * iw, ux = (v) => v / iw * 100;
        items.forEach((q) => { q.w = Math.max(...q.t.split("\n").map((l) => l.length)) * 6.6 + 6; q.lx = px(q.cx); });
        for (let i = 1; i < items.length; i++) items[i].lx = Math.max(items[i].lx, items[i - 1].lx + (items[i - 1].w + items[i].w) / 2);
        const over = items.length ? items[items.length - 1].lx + items[items.length - 1].w / 2 - iw : 0;
        if (over > 0) { items[items.length - 1].lx -= over; for (let i = items.length - 2; i >= 0; i--) items[i].lx = Math.min(items[i].lx, items[i + 1].lx - (items[i].w + items[i + 1].w) / 2); }
        if (items.length && items[0].lx - items[0].w / 2 < 0) { items[0].lx = items[0].w / 2; for (let i = 1; i < items.length; i++) items[i].lx = Math.max(items[i].lx, items[i - 1].lx + (items[i - 1].w + items[i].w) / 2); }
        items.forEach((q) => { q.lx = ux(q.lx); });
        return items;
      };
      const fig = (q) => `${k(q.c)} · ${pct(q.p)}`;
      // Wide modes are named right over their segment. Narrow ones sit a tier higher, spread among themselves.
      const clamp = (q) => { const h = (Math.max(...q.t.split("\n").map((l) => l.length)) * 6.6 + 6) / 2 / iw * 100; q.lx = Math.min(100 - h, Math.max(h, q.cx)); return q; };
      const names = top.filter((q) => big(q)).map((q) => clamp({ cx: (q.x1 + q.x2) / 2, t: q.m[0] }));
      const heads = spread(top.filter((q) => q.p > 0.05 && !big(q)).map((q) => ({ cx: (q.x1 + q.x2) / 2, t: `${q.m[0]}\n${fig(q)}` })));
      // A mode missing from today's bar, like the yellow bus, is named under the second bar.
      const named = new Set(top.filter((q) => q.p > 0.05).map((q) => q.m[0]));
      const foots = spread(bot.filter((q) => q.p > 0.05 && (!big(q) || !named.has(q.m[0]))).map((q) => ({ cx: (q.x1 + q.x2) / 2, t: big(q) ? q.m[0] : `${q.m[0]}\n${fig(q)}` })));
      el.replaceChildren(Plot.plot({
        width: W, height: 222, marginLeft: 44, marginRight: 4, marginTop: 2, marginBottom: 2,
        x: { domain: [0, 100], axis: null }, y: { domain: [4.1, -1.7], axis: null },
        marks: [
          Plot.rect(segs, { x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: (q) => q.m[2], stroke: "#fff", strokeWidth: 1 }),
          Plot.link(links, { x1: "x1", x2: "x2", y1: 1, y2: 1.75, stroke: "#8a929c", strokeWidth: 1 }),
          Plot.text(segs.filter(big), { x: (q) => (q.x1 + q.x2) / 2, y: (q) => q.y1 + 0.38, text: (q) => k(q.c), fill: (q) => q.m[3], fontSize: 12, fontWeight: 700 }),
          Plot.text(segs.filter(big), { x: (q) => (q.x1 + q.x2) / 2, y: (q) => q.y1 + 0.72, text: (q) => pct(q.p), fill: (q) => q.m[3], fontSize: 10, fillOpacity: 0.85 }),
          Plot.text(names, { x: "lx", y: -0.12, text: "t", lineAnchor: "bottom", fontSize: 10.5, fontWeight: 600, fill: "#3d4450" }),
          Plot.link(heads, { x1: "lx", x2: "cx", y1: -0.86, y2: 0, stroke: "#8a929c", strokeWidth: 1 }),
          Plot.text(heads, { x: "lx", y: -0.9, text: "t", lineAnchor: "bottom", fontSize: 10.5, fontWeight: 600, fill: "#3d4450" }),
          Plot.link(foots, { x1: "cx", x2: "lx", y1: 2.75, y2: 2.97, stroke: "#8a929c", strokeWidth: 1 }),
          Plot.text(foots, { x: "lx", y: 3.0, text: "t", lineAnchor: "top", fontSize: 10.5, fill: "#3d4450" }),
          Plot.text(rows, { x: 0, y: (r) => r[2] + 0.5, text: (r) => r[0], textAnchor: "end", dx: -5, fontSize: 11, fill: "#59626f", lineWidth: 5 }),
        ],
      }));
    });
  }

  // ---------- the city ----------
  // Every figure comes from makeCityModel (site/src/school-trips-model.mjs) on city.json's sets, by the SSC
  // comment's rules: the sets hold each change at full strength under the sim's three cases, and the model scales
  // free Muni and the shuttle loops to their central sizes and reads the central case, low and high beside it.
  const svar = (c) => MD.svar(c);
  function cityData() {
    if (!CJP) CJP = fetch(`${D.base}/city.json`).then((r) => { if (!r.ok) throw new Error("city.json " + r.status); return r.json(); }).then((d) => {
      const m = window.makeCityModel(d, { schools: SCH, rules: D.rules, cost: COST });
      CJ = d; MD = m; prepCity();
      // The school list, split into its own file at build time when city.json grows large. A missing list only empties the table.
      if (D.citySplit && !CJ.schools) getJson("city-schools.json").then((x) => { CJ.schools = x; render(); }).catch(() => {});
      return d;
    });
    return CJP;
  }
  const cityKey = (c) => MD.keyOf(c);
  const todayKey = () => MD.TODAY;
  const cityFig = (key) => MD.fig(key);
  const TRANSIT = 4;
  const cityCost = (c) => MD.cost(c);
  const safeN = (v) => MD.safeN(v);
  const usd = (m) => (m >= 1 ? money(m) : m > 0 ? "$" + sig2(m * 1e3) + "K" : "None");
  // Fewer kids hurt per $1M a year: whole numbers from 10, one decimal from 0.1, two significant figures below.
  const perYr = (m) => (m >= 1 ? money(m) : m > 0 ? "$" + sig2(m * 1000) + "K" : "$0");
  const perM = (v) => (v >= 10 ? n2(v) : v >= 0.1 ? v.toFixed(1) : String(sig2(v)));
  const p1 = (v) => (Math.round(v * 10) / 10).toFixed(1) + "%";
  function goalBar(a, b) {
    const W = 272, x = (v) => 6 + Math.max(0, Math.min(100, v)) / 100 * (W - 12);
    // When today sits near the goal, the two labels part to either side of their lines instead of overlapping.
    const near = a != null && Math.abs(x(a) - x(30)) < 34, lt = a > 30;
    const anc = (isToday) => (!near ? "middle" : isToday === lt ? "start" : "end");
    const tick = (v) => `<text x="${x(v)}" y="44" text-anchor="${v === 0 ? "start" : v === 100 ? "end" : "middle"}" font-size="10" fill="#59626f">${v}%</text>`;
    return `<div class="tr-goal"><svg viewBox="0 0 ${W} 48" role="img" aria-label="Single-Family Car share today and with your changes against the 30% goal">`
      + `<rect x="6" y="14" width="${W - 12}" height="12" rx="2" fill="#eef0f3"/>`
      + (b == null ? "" : `<rect x="6" y="14" width="${x(b) - 6}" height="12" rx="2" fill="var(--seq-3)"/>`)
      + (a == null ? "" : `<line x1="${x(a)}" x2="${x(a)}" y1="10" y2="30" stroke="#15181c" stroke-width="2"/><text x="${x(a)}" y="8" text-anchor="${anc(true)}" font-size="10" font-weight="600" fill="#15181c">Today</text>`)
      + `<line x1="${x(30)}" x2="${x(30)}" y1="10" y2="30" stroke="#3d4450" stroke-dasharray="3 2" stroke-width="1.5"/><text x="${x(30)}" y="8" text-anchor="${anc(false)}" font-size="10" font-weight="600" fill="#3d4450">Goal</text>`
      + [0, 30, 100].map(tick).join("") + `</svg></div>`;
  }
  function cityResults() {
    const el = $("[data-city-res]"), bel = $("[data-city-budget]"), dash = "…";
    let T = null, X = null, k = null, N = 1, R = null, fewer = 0;
    // The single-family car count and kids hurt, central, with our low to high printed small under each: the cases
    // either side of the central for the network's bike shift, and each change's own low and high (makeCityModel's
    // range). carLo and carHi are the car counts at the most and fewest kids out of cars.
    let carLo = null, carHi = null, hurtLo = null, hurtHi = null;
    if (CJ) {
      N = CJ.students; T = cityFig(todayKey()); X = MD.figC(S.city); k = cityCost(S.city); R = MD.range(S.city); fewer = MD.hurt(S.city);
      [carLo, carHi] = [T.modes[0] - R.cars[1], T.modes[0] - R.cars[0]]; [hurtLo, hurtHi] = [MD.HB - R.hurt[1], MD.HB - R.hurt[0]];
    }
    // A budget plan's figures are its own totals, school by school, in the central case, with its own low and high.
    const P = plan();
    if (CJ && P) {
      const a = P.at.central, mid = Object.values(a.carsBy).reduce((t, x) => t + x, 0);
      X = { modes: a.modes, min: a.min, solo: a.alone }; k = { once: a.once, year: a.year, people: a.people, st: a.st }; R = { year: [a.year, a.year] }; fewer = a.hurt[1];
      [carLo, carHi] = [a.modes[0] + mid - a.carsOut[1], a.modes[0] + mid - a.carsOut[0]]; [hurtLo, hurtHi] = [MD.HB - a.hurt[2], MD.HB - a.hurt[0]];
    }
    // Our low to high estimate, printed small under the central figure.
    const rng = (t) => `<span class="tr-rng">${t}</span>`;
    const span = (lo, hi) => (lo != null && hi - lo >= 0.5 ? rng(`${n2(Math.min(lo, hi))} to ${n2(Math.max(lo, hi))}`) : "");
    // The out-of-cars and fewer-hurt lines under these rows were removed (Bryan's staging edits, 2026-10-12);
    // the bars below carry each change's range.
    const cnt = (v, of = N) => (v == null ? dash : `${n2(v)}<small>${pct(100 * v / of)}</small>`);
    const row = (q, a, b) => `<tr><th scope="row">${q}</th><td>${a}</td><td class="s">${b}</td></tr>`;
    const one = (q, v) => `<tr><th scope="row">${q}</th><td>${v}</td></tr>`;
    const mn = (F) => (F && F.min != null ? `${(F.min / N).toFixed(1)}<small>minutes</small>` : dash);
    // The safe trip count moved here from the line above the second map, so it shows once.
    const B = CJ && CJ.blocks, sum = (a) => a.reduce((t, x, i) => t + B.students[i] * x / 100, 0);
    const safeT = B ? sum(B.safe15Pct.today) : null, safeX = B ? (P ? P.at.central.safe : sum(B.safe15Pct[svar(S.city)])) : null;
    // One caregiver for each student whose trip needs one.
    const par = (F) => (F && F.solo != null ? cnt(N - F.solo) : dash);
    el.innerHTML = `<table class="tr-mtab"><thead><tr><th></th><th>Today</th><th>${scenCol()}</th></tr></thead><tbody>`
      + row("Come by single-family car<em>SFUSD, charter and private students</em>", cnt(T && T.modes[0]), cnt(X && X.modes[0]) + (scenOf() === "today" ? "" : span(carLo, carHi)))
      + `</tbody></table>` + goalBar(T && 100 * T.modes[0] / N, X && 100 * X.modes[0] / N)
      + `<table class="tr-mtab"><tbody>`
      + row("Safe trip in 15 minutes<em>students, walking or biking</em>", cnt(safeT), cnt(safeX))
      + row("Average trip<em>minutes, each student</em>", mn(T), mn(X))
      + row("Caregivers taking a child", par(T), par(X))
      + row("Kids hurt a year<em>every child 5 to 18, private schools too</em>", CJ ? n2(MD.HB) : dash, CJ ? n2(MD.HB - fewer) + (scenOf() === "today" ? "" : span(hurtLo, hurtHi)) : dash)
      + `</tbody></table>`;
    const tot = k ? k.year + k.once / 4 : 0;
    const staffLine = k ? [k.st.drv ? `${n2(k.st.drv)} drivers` : "", k.st.ss ? `${n2(k.st.ss)} part-time School Street activation staff` : "", k.st.pool ? "half a carpool lead" : ""].filter(Boolean).join(", ") : "";
    bel.innerHTML = `<table class="tr-ctab"><tbody>`
      + one("One-time cost", k ? usd(k.once) : dash)
      + one("Yearly cost", k ? usd(k.year) + (k.year > 0 && R.year[1] - R.year[0] > 1e-6 ? rng(`${usd(R.year[0])} to ${usd(R.year[1])}`) : "") : dash)
      + one("Total a year<em>yearly plus one-time costs spread over 4 years</em>", k ? usd(tot) : dash)
      + one("Fewer Kids Hurt per $1M a Year", k ? (tot > 0 && fewer > 0 ? perM(fewer / tot) : "None") : dash)
      + one(`Staff<em>${k && k.people ? staffLine : "None for these changes"}</em>`, k ? n2(k.people) : dash)
      + `</tbody></table>`;
  }
  // Each change alone against today, in the central case: the kids it takes out of single-family cars and the
  // kids hurt it spares, each with the comment's low and high, and each per $1M a year (makeCityModel's
  // alone). Rows run from most to least effective per dollar (Bryan, 2026-10-10: "sort descending by
  // effectiveness"), no-cost rows last. The order is set on the first draw and then kept, so nothing moves when a
  // control changes.
  function barRows() {
    const lab = Object.fromEntries(D.citySw.map((t) => [t[0], t[1]]));
    const one = (id, label, grp) => {
      const a = MD.alone(id), yr = a.year + a.once / 4;
      return { label, grp, yr, car: a.cars[1], carLo: a.cars[0], carHi: a.cars[2], hurt: a.hurt[1], hurtLo: Math.min(...a.hurt), hurtHi: Math.max(...a.hurt),
        eff: yr > 0 ? a.cars[1] / yr : null, hurtEff: yr > 0 && a.hurt[1] > 0 ? a.hurt[1] / yr : null };
    };
    return CSW.map((k) => ({ ...one(k, k === "safer_crossings" ? `${lab[k]}, 1 block` : lab[k], "Change"), draft: D.draftSw.includes(k) }))
      // The assignment SFUSD chose, at 2030-31 (what the plans hold) and in full in 2033-34.
      .concat([["assign_ncp52", "SFUSD's new assignment, 2030-31"],
        ["assign_ncp", "SFUSD's new assignment, 2033-34"]].map(([a, l]) => one(a, l, "Assignment")))
      .concat((CJ.segments || []).map((m) => m.budgetM).filter(Boolean).map((m) => one(`seg${m}`, `$${m}M of new bikeways`, "Bikeways")))
      // A wider reach moves the same students out of cars (the study's effect is per school), so those rows print
      // "Same as 1 block" instead of repeating the bar (Bryan, 2026-10-17: "Why do the three levels of safety
      // upgrades give same number of people out of cars?").
      .concat([["xing660", "2 blocks"], ["xing1320", "1/4 mile"]].map(([id, l]) => ({ ...one(id, `${lab.safer_crossings}, ${l}`, "Change"), car: null, sameCars: true, draft: D.draftSw.includes("safer_crossings") })));
  }
  let barOrder = null;
  function cityBars() {
    if (!CJ || !window.Plot) return;
    let rows = barRows();
    // The order is fixed when the sort is chosen, so a change of view redraws the bars in place.
    // Largest first; a change with no figure (n/a, or no cost on the cost sort) goes last, ties keep the build order.
    if (!barOrder || barOrder.k !== S.bsort) {
      const k = S.bsort, v = (d) => (d[k] == null || (k === "yr" && !(d.yr > 0)) ? -Infinity : d[k]);
      barOrder = rows.map((d, i) => [d, i]).sort(([a, i], [b, j]) => (v(b) - v(a)) || i - j).map(([d]) => d.label);
      barOrder.k = k;
    }
    rows = barOrder.map((l) => rows.find((d) => d.label === l));
    $$("[data-bars]").forEach((el) => {
      // Small multiples: one label column on the first, then the same rows in each, each on its own scale.
      // Drawn at the column's own width, so no chart is scaled and every row sits at the same height.
      // On a phone the charts stack, and each carries its own row labels.
      const narrow = window.matchMedia && matchMedia("(max-width: 860px)").matches;
      const k = el.dataset.bars, first = k === "car" || narrow, w = el.clientWidth || (first ? 300 : 150);
      const lo = k + "Lo", hi = k + "Hi", ranged = k === "car" || k === "hurt";
      // Plain bars from zero to the central estimate, each printing its own figure, with the low to high range in
      // brackets beside it (Bryan, 2026-10-12: "show bars instead of weird gant things").
      // The cost column counts one-time spending over four years plus the running cost (Bryan, 2026-10-12: "add a
      // column for $ per year"); a change that costs nothing prints "No cost" rather than a $0 bar.
      // A change that adds injuries (new walkers and riders carry more risk than the car trip they leave) gets no
      // bar and prints how many more, muted.
      const val = rows.filter((d) => d[k] != null && (k !== "yr" || d.yr > 0) && (k !== "hurt" || d.hurt > 0.05));
      const mx = Math.max(...val.map((d) => d[k]), k === "car" ? 100 : k === "hurt" ? 1 : 0.1);
      const fmt = k === "hurt" ? (v) => v.toFixed(1) : k === "hurtEff" ? perM : k === "yr" ? perYr : (v) => n2(v);
      const spans = (d) => ranged && d[hi] - d[lo] > 1e-9;
      const lab = (d) => fmt(d[k]) + (spans(d) ? ` (${fmt(d[lo])} to ${fmt(d[hi])})` : "");
      // The label column and the figure beside each bar keep at least 80 px of bar between them.
      // The right margin fits the longest printed figure, at about 6.5 px a character in 11 px bold.
      let mr = Math.max(ranged ? (k === "hurt" ? 112 : 150) : k === "yr" ? 52 : 40, ...val.map((d) => Math.ceil(lab(d).length * 6.5) + 8));
      let ml = !first ? 4 : narrow ? Math.round(Math.max(200, w * 0.5)) : Math.round(Math.min(w - 60, Math.max(236, w * 0.44)));
      if (w - ml - mr < 80) { mr = Math.max(70, w - ml - 80); ml = Math.max(first ? 150 : 4, Math.min(ml, w - mr - 80)); }
      el.replaceChildren(Plot.plot({
        width: w, height: 26 * rows.length + 30, marginLeft: ml, marginRight: mr, marginTop: 6, marginBottom: 24,
        style: { fontSize: "11px", color: "var(--ink)" },
        x: { domain: [0, mx * 1.02], grid: true, ticks: narrow || w - ml - mr < 160 ? 1 : 2, label: null, tickFormat: (v) => (k === "yr" && v > 0 ? perYr(v) : n2(v)) },
        y: { domain: rows.map((d) => d.label), label: null, tickSize: 0, axis: null },
        marks: [
          Plot.barX(val, { x: k, y: "label", fill: "var(--grey-light)", insetTop: 3, insetBottom: 3 }),
          // SFMTA's draft or our addition is marked on the row label, not the bar (Bryan, 2026-10-12: "Highlight the
          // item labels in the left instead of the bars"): a small square in the margin, labels left-aligned after it.
          first && Plot.dot(rows, { x: 0, y: "label", dx: -ml + 7, symbol: "square", r: 4.5, fill: (d) => D.draftC[d.draft ? 1 : 0] }),
          first && Plot.axisY({ tickSize: 0, textAnchor: "start", dx: -ml + 14, tickPadding: 0, label: null }),
          Plot.text(val, { x: k, y: "label", text: lab, dx: 3, textAnchor: "start", fontWeight: 700 }),
          Plot.text(rows.filter((d) => !val.includes(d)), { x: 0, y: "label", text: (d) => (k === "hurt" ? (d.hurt < -0.05 ? `${(-d.hurt).toFixed(1)} more` : "About 0")
            : k === "car" && d.sameCars ? "Same as 1 block" : !(d.yr > 0) ? "No cost" : "None"), dx: 3, textAnchor: "start", fill: "var(--muted)" }),
          Plot.ruleX([0]),
        ].filter(Boolean),
      }));
    });
  }
  const KPI_MODE = { car: "come by single-family car", carpool: "come in a carpool", walk: "walk", bike: "bike", transit: "take Muni", bus: "ride a school bus or shuttle loop" };
  function cityKpi() {
    const c = S.city;
    if (!CJ) return;
    // The travel tally has no school bus bar, so today's SFUSD yellow bus riders (about 2,000, School Access Plan p. 42)
    // sit inside its other modes, and this mode counts new riders only (Bryan, 2026-10-13: "Today over a thousand
    // students ride, but it says 0").
    // Each figure shows once (Bryan, 2026-10-17: "Cut the repeats"): the counts are in the outcome table beside the
    // maps, so the line above a map keeps only what the table doesn't say.
    $("[data-city-kpi]").innerHTML = c.mode === "bus"
      ? "Today's 2,000 or so SFUSD yellow bus riders are counted in the other ways to school, since the travel tally we start from doesn't split them out."
      : "";
    $("[data-safe-kpi]").innerHTML = "";
  }


  // The two maps: one circle a home block, sized by its students, shaded on one sequential ramp. The first shows
  // a way to school, the second the share with a safe trip in 15 minutes (Bryan, 2026-10-12: "let's split the
  // 'Safe Trip in 15 Minutes' into a second map"). Both follow the chosen scenario.
  let lpop = null, CF = null, mixMemo = { key: null, v: null };
  const CMAPS = { mode: { sel: "[data-city-map]", map: null, pop: null, at: null }, safe: { sel: "[data-safe-map]", map: null, pop: null, at: null } };
  const BRK = {};
  const CB = [[-122.515, 37.706], [-122.357, 37.812]];
  const tok = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mixc = (a, b, t) => "#" + hex(a).map((v, i) => Math.round(v + (hex(b)[i] - v) * t).toString(16).padStart(2, "0")).join("");
  // Lightness carries the order, from the pale end of --seq-3 to a darkened --seq-3.
  const RAMP = () => { const s0 = tok("--seq-3-soft"), s3 = tok("--seq-3"), k = tok("--ink"); return [mixc(s0, s3, 0.3), mixc(s0, s3, 0.6), mixc(s0, s3, 0.85), mixc(s3, k, 0.2), mixc(s3, k, 0.45), mixc(s3, k, 0.7)]; };
  function prepCity() {
    const B = CJ.blocks;
    CF = () => ({ type: "FeatureCollection", features: B.lon.map((x, i) => ({ type: "Feature", properties: { i, k: B.students[i], v: 0 }, geometry: { type: "Point", coordinates: [x, B.lat[i]] } })) });
    // Fixed breaks for each map, from today's and every change's values together, so a switch moves the
    // colours and never the legend. Six classes in even, round steps from the 2nd to the 99th student-weighted
    // percentile, so the whole range shows (the car share's steps of 5 put a break at the 30% goal).
    const quart = (cols, qs) => {
      const pts = [];
      cols.forEach((a) => a.forEach((x, i) => pts.push([x, B.students[i]])));
      pts.sort((p, q) => p[0] - q[0]);
      const tot = pts.reduce((t, p) => t + p[1], 0), out = [];
      let acc = 0, j = 0;
      for (const q of qs) { while (j < pts.length - 1 && acc + pts[j][1] < q * tot) acc += pts[j++][1]; out.push(pts[j][0]); }
      return out;
    };
    const steps = (cols) => {
      const [lo, hi] = quart(cols, [0.02, 0.99]), raw = Math.max((hi - lo) / 6, 0.1), e = Math.pow(10, Math.floor(Math.log10(raw)));
      const step = [1, 2, 2.5, 5, 10].map((m) => m * e).reduce((a, b) => (Math.abs(Math.log(b / raw)) < Math.abs(Math.log(a / raw)) ? b : a));
      const first = Math.max(step, Math.ceil(lo / step) * step);
      return [0, 1, 2, 3, 4].map((k) => Math.round((first + k * step) * 10) / 10);
    };
    CJ.modes.forEach((m, k) => { BRK["mode:" + m] = steps([B.today[k], B.allOn[k]]); });
    BRK.safe = steps([B.safe15Pct.today, B.safe15Pct.connector_s50_ss || B.safe15Pct[CJ.variants[CJ.variants.length - 1]]]);
  }
  // With the chosen changes, each block's mix of modes: today plus each switched-on change's own change, then the
  // network's own fewer family-car students in the central case, from the sets, spread over the blocks by their car
  // students the network gives a better route (city.json's gainPct), onto the bike. Close but not exact where changes
  // overlap and where a block's students move by different amounts (said on About School Trips).
  function mixWith() {
    const c = S.city, P = plan(), key = cityKey(c) + "|" + (P ? c.plan + S.budget : "");
    if (mixMemo.key === key) return mixMemo.v;
    const B = CJ.blocks, v = P ? MD.variant({ seg: P.city.seg }) : MD.variant(c);
    let out;
    if (cityKey(c) === todayKey() && !P) out = B.today;
    else {
      const on = CJ.programs.filter((p) => c[p]).concat(c.assign !== "today" ? [c.assign] : []);
      // The scaled changes (free Muni, the shuttle loops, School Streets, carpools, walking school buses) are at full
      // strength, so they scale to their central sizes.
      // A budget plan funds a change at some schools only, so each change's block shifts are scaled by the share of
      // its citywide effect the plan's schools carry, and the network is its citywide bikeways only. Close, not exact.
      const share = (p) => {
        if (!P || p.startsWith("assign")) return 1;
        const got = Object.entries(P.at.central.carsBy).filter(([q]) => q === p || (p === "safer_crossings" && q.startsWith("xing"))).reduce((t, [, x]) => t + x, 0);
        const all = MD.alone(p).cars[1];
        return all > 0 ? Math.max(0, Math.min(1, got / all)) : 0;
      };
      // Each change's weight once, not once per block and mode: share() runs the citywide model. An assignment part
      // way through its rollout is its full-effect shift at its share.
      const ws = on.map((p) => MD.W(p) * share(p) * MD.phaseOf(p)[1]), dk = on.map((p) => MD.phaseOf(p)[0]);
      out = B.today.map((col, k) => col.map((x, i) => on.reduce((t, p, j) => t + ws[j] * B.delta[dk[j]][k][i], x)));
      const gp = v !== "today" && B.gainPct[v];
      if (gp) {
        // The network's citywide fewer family-car students: the set on its network against the same set on today's.
        const rest = cityKey(c).slice(cityKey(c).indexOf("|")), k1 = v + rest, k0 = "today" + rest;
        const fewerCars = Math.max(0, MD.fig(k0).modes[0] - MD.fig(k1).modes[0]);
        const w = gp.map((g, i) => B.students[i] * g / 100 * Math.max(0, out[0][i]) / 100), tw = w.reduce((t, x) => t + x, 0);
        if (tw > 0) for (let i = 0; i < w.length; i++) {
          const m = Math.min(Math.max(0, out[0][i]), 100 * fewerCars * w[i] / tw / Math.max(B.students[i], 1e-9));
          out[0][i] -= m; out[3][i] += m;
        }
      }
      out = out.map((col) => col.map((x) => Math.max(0, Math.min(100, x))));
    }
    mixMemo = { key, v: out };
    return out;
  }
  // Each map's value per block for the chosen scenario. Today's scenario gives today's values.
  // The safe-trip map's network: a budget plan's citywide bikeways, or the switches' own.
  const safeV = () => (plan() ? MD.variant({ seg: plan().city.seg }) : svar(S.city));
  const cvals = (kind) => (kind === "mode" ? mixWith()[CJ.modes.indexOf(S.city.mode)] : CJ.blocks.safe15Pct[safeV()]);
  const brk = (kind) => (kind === "mode" ? BRK["mode:" + S.city.mode] : BRK.safe);
  const MODE_BY = { car: "By single-family car", carpool: "By carpool", walk: "Walking", bike: "Biking", transit: "By Muni", bus: "By school bus or shuttle loop" };
  function cityLegend(kind) {
    const el = $(kind === "mode" ? "[data-city-legend]" : "[data-safe-legend]"), c = S.city;
    if (!CJ) { el.innerHTML = "<b>Loading…</b>"; return; }
    const b = brk(kind), C = RAMP();
    const f = (x) => `${x}%`;
    const title = kind === "mode" ? `Share of students ${MODE_BY[c.mode].toLowerCase()}` : "Share with a safe trip in 15 min";
    // One horizontal bar, one equal step per colour, the breaks printed under the joins between steps
    // (Bryan, 2026-10-10: "a much more compact sequential legend with just one horizontal bar").
    const n = b.length + 1, ramp = `<span class="tr-ramp">${C.slice(0, n).map((col) => `<i style="background:${col}"></i>`).join("")}</span>`
      + `<span class="tr-ramp-t">${b.map((x, i) => `<em style="left:${(100 * (i + 1)) / n}%">${f(x)}</em>`).join("")}</span>`;
    const ln = (col, t, op = 1) => `<span><i class="ln" style="--c:${col.startsWith("--") ? tok(col) : col};opacity:${op}"></i>${t}</span>`;
    const lines = ln(NEW_BIKE, "Bikeways, built and planned", 0.55) + [c.seg > 0 ? ln(NEW_BIKE, `New bikeways, $${c.seg}M`, 0.95) : "", c.connector ? ln(NEW_BIKE, "School Connectors", 0.95) : "",
      c.school_street ? ln("--ink", "School Street activations", 0.7) : ""].join("");
    el.innerHTML = `<b>${title}</b>` + ramp + lines + `<small>Bigger circles, more students</small>`;
  }
  // Circle radius in pixels: the square root of the block's students, growing with the zoom.
  const R11 = (k) => Math.max(1.3, 0.55 * Math.sqrt(k)), R16 = (k) => Math.max(5, 5 * Math.sqrt(k));
  const radAt = (k, z) => { const t = (Math.pow(2, Math.max(0, Math.min(5, z - 11))) - 1) / 31; return R11(k) + (R16(k) - R11(k)) * t; };
  function cityMap(kind) {
    const M = CMAPS[kind];
    if (M.map || !window.sfMap || !CJ) return;
    const cmap = (M.map = sfMap.create($(M.sel), { bounds: CB, padding: () => ({ top: 64, bottom: 8, left: 8, right: 8 }), onReset: () => closePop(kind) }));
    if (!cmap) return;
    cmap.on("load", () => {
      // Framed once, at the container's laid-out size. After this the view moves only when the reader moves it.
      cmap.resize(); cmap.fitBounds(CB, { padding: { top: 64, bottom: 8, left: 8, right: 8 }, duration: 0 });
      const before = sfMap.under(cmap), k = ["get", "k"];
      const rad = ["interpolate", ["exponential", 2], ["zoom"], 11, ["max", 1.3, ["*", 0.55, ["sqrt", k]]], 16, ["max", 5, ["*", 5, ["sqrt", k]]]];
      M.fc = CF();
      cmap.addSource("cb", { type: "geojson", data: M.fc });
      cmap.addLayer({ id: "cb", type: "circle", source: "cb", layout: { "circle-sort-key": ["-", 0, k] }, paint: {
        "circle-radius": rad, "circle-color": tok("--grey-light"), "circle-opacity": 0.92,
        "circle-stroke-color": "#ffffff", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 11, 0.3, 15, 1] } }, before);
      cmap.addLayer({ id: "cb-sel", type: "circle", source: "cb", filter: ["==", ["get", "i"], -1], paint: { "circle-radius": rad, "circle-opacity": 0, "circle-stroke-color": tok("--ink"), "circle-stroke-width": 2.5 } });
      cmap.on("click", (e) => {
        const ln = cmap.getLayer("ovl-ss") ? sfMap.near(cmap, e.point, ["ovl-seg", "ovl-conn", "ovl-ss"]) : [];
        if (ln.length) return selectLine(kind, ln[0], e.lngLat);
        const f = sfMap.near(cmap, e.point, ["cb"]); if (f.length) selectBlock(kind, f[0].properties.i); else closePop(kind);
      });
      cmap.on("mousemove", (e) => { cmap.getCanvas().style.cursor = sfMap.near(cmap, e.point, ["cb"]).length ? "pointer" : ""; });
      cmap.sfReady = true; drawCityMap(kind);
      cityOverlays(kind);
      if (kind === "mode") { heat(cmap); zones(cmap); }
    });
  }
  // The scenario's street changes, drawn over the blocks in colours the block shading never uses: new bikeway
  // segments and School Connectors in --seq-1, School Streets in --ink. Calm zones aren't drawn (Bryan: "not sure it helps").
  // [layer, source key, colour, width at zoom 15, opacity]. Every line is solid (Bryan, 2026-10-17: "I can't see
  // bikeways on the map they need to be more clear. And don't use dashed lines"): built and planned bikeways in
  // pale blue, the switched-on new pieces in full Observable 10 blue, a hue the block ramp never uses.
  const NEW_BIKE = "#4269d0";
  const OVL = [["ovl-seg", "seg", NEW_BIKE, 5, 0.95], ["ovl-conn", "connector", NEW_BIKE, 5, 0.95], ["ovl-ss", "school_street", "--ink", 5, 0.8]];
  let OVP = null;
  const ovlData = () => OVP || (OVP = fetch(`${D.base}/overlays.json`).then((r) => { if (!r.ok) throw new Error("overlays.json " + r.status); return r.json(); }));
  function cityOverlays(kind) {
    const cmap = CMAPS[kind].map;
    ovlData().then((d) => {
      const fc = (ls, p = {}) => ({ type: "FeatureCollection", features: ls.map((c) => ({ type: "Feature", properties: p, geometry: { type: "LineString", coordinates: c } })) });
      const per = (k) => ({ type: "FeatureCollection", features: d.schools.flatMap((x) => fc(x[k], { cds: x.cds }).features) });
      // Each piece once, with the budgets whose set holds it and the budgets at which it is a bridge.
      // bs and br are "|5|10|" strings, so a budget filter is a substring test (a GeoJSON array property isn't reliably kept).
      const seg = { type: "FeatureCollection", features: (d.segments || []).flatMap((p) => fc(p.lines, { bs: `|${p.budgets.join("|")}|`, br: `|${(p.bridge || []).join("|")}|`, id: p.id, street: p.street, mi: p.mi, types: (p.types || []).join("|") }).features) };
      const src = { seg, connector: per("connector"), school_street: per("schoolStreet") };
      for (const [id, k, col, w, op] of OVL) {
        cmap.addSource(id, { type: "geojson", data: src[k] });
        cmap.addLayer({ id, type: "line", source: id, layout: { "line-cap": "round", visibility: "none" },
          paint: { "line-color": col.startsWith("--") ? tok(col) : col, "line-width": ["interpolate", ["linear"], ["zoom"], 11, w * 0.5, 15, w], "line-opacity": op } }, "cb");
      }
      Promise.all(["network.json", "planned-net.json"].map((f) => fetch(`${D.base}/${f}`).then((r) => r.json()).then((e) => sfMap.decode(e)))).then(([built, plan]) => {
        cmap.addSource("ovl-net", { type: "geojson", data: fc(built.concat(plan)) });
        cmap.addLayer({ id: "ovl-net", type: "line", source: "ovl-net", layout: { "line-cap": "round" },
          paint: { "line-color": NEW_BIKE, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.2, 15, 3.5], "line-opacity": 0.55 } }, "ovl-seg");
      }).catch(() => {});
      // A bridge piece (one that brings nobody within a safe ride on its own) gets a dark outline under its line.
      cmap.addLayer({ id: "ovl-bridge", type: "line", source: "ovl-seg", filter: ["in", "|x|", ["get", "br"]], layout: { "line-cap": "butt", visibility: "none" },
        paint: { "line-color": tok("--ink"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 15, 9], "line-opacity": 0.35 } }, "ovl-seg");
      // A clicked line is outlined whole: every piece with its id (a segment) or its school (a connector).
      cmap.addLayer({ id: "ovl-sel", type: "line", source: "ovl-seg", filter: ["==", ["get", "id"], ""], layout: { "line-cap": "round" },
        paint: { "line-color": tok("--ink"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 3, 15, 7], "line-opacity": 0.35 } });
      cmap.addLayer({ id: "ovl-csel", type: "line", source: "ovl-conn", filter: ["==", ["get", "cds"], ""], layout: { "line-cap": "round" },
        paint: { "line-color": tok("--ink"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 3, 15, 7], "line-opacity": 0.35 } });
      drawOverlays(kind);
    }).catch((e) => { if (window.console) console.info("map: no street-change lines (" + e.message + ")"); });
  }
  // Kids 5 to 18 hurt within a quarter mile of a school at school hours over 20 school years
  // (tools/school-trips/school-injury-points.py), a heat map the reader turns on (Bryan, 2026-10-13).
  let INJP = null, INJ = null;
  const injData = () => INJP || (INJP = fetch(`${D.base}/injuries.json`).then((r) => { if (!r.ok) throw new Error("injuries.json " + r.status); return r.json(); }).then((d) => (INJ = d)));
  // One sequential ramp, pale to dark, with intensity low enough that only the densest spots reach the dark end
  // (Bryan, 2026-10-13: "The heat map saturates and I don't get a real sense of the worst spots").
  const HEAT = ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(239,177,24,0)", 0.08, "rgba(246,205,120,0.5)", 0.3, "#efb118",
    0.6, "#b9770e", 1, "#4a2c04"];
  function heat(m) {
    if (!m || !m.sfReady || (!S.heat && !m.getLayer("inj"))) return;
    injData().then((d) => {
      if (!m.getSource("inj")) {
        m.addSource("inj", { type: "geojson", data: { type: "FeatureCollection", features: d.pts.map((p) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [p[0], p[1]] } })) } });
        // Zoomed in past a few blocks, the heat fades into one dot a kid (Bryan, 2026-10-13: "when I'm zoomed in enough,
        // can you just mark individual injuries instead of heat map?").
        m.addLayer({ id: "inj", type: "heatmap", source: "inj", maxzoom: 15, paint: { "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 12, 16, 45],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 11, 0.25, 16, 0.6], "heatmap-color": HEAT,
          "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0.85, 14.5, 0] } });
        m.addLayer({ id: "inj-pt", type: "circle", source: "inj", minzoom: 13.5, paint: { "circle-color": "#b9770e", "circle-stroke-color": "#fff",
          "circle-stroke-width": 1, "circle-radius": ["interpolate", ["linear"], ["zoom"], 13.5, 3, 17, 6],
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, 0.9], "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, 1] } });
      }
      ["inj", "inj-pt"].forEach((id) => m.setLayoutProperty(id, "visibility", S.heat ? "visible" : "none"));
      heatCounts();
    }).catch((e) => { if (window.console) console.info("map: no injury heat map (" + e.message + ")"); });
  }
  // The counts beside the toggle: every kid in the file citywide, and those within a quarter mile of the chosen
  // school's grounds (injuries.json's near, so a kid near two schools counts at both).
  function heatCounts() {
    if (!INJ) return;
    const c = $('[data-heat-n="city"]'); if (c) c.textContent = `${n2(INJ.n)} kids`;
    const el = $('[data-heat-n="school"]'), n = INJ.near && INJ.near[S.school.cds];
    if (el && n != null) el.textContent = `${n2(n)} within a quarter mile`;
  }
  // The 500 ft school zone round every school's grounds, always shown, under the blocks and lines. On the school
  // map the chosen school's zone is drawn heavier (Bryan, 2026-10-13: "Please show this slow zone around each school
  // in the city map and per-school map").
  let ZP = null;
  const zoneData = () => ZP || (ZP = fetch(`${D.base}/school-zones.json`).then((r) => { if (!r.ok) throw new Error("school-zones.json " + r.status); return r.json(); }));
  function zones(m) {
    if (!m || !m.sfReady) return;
    zoneData().then((d) => {
      if (!m.getSource("zones")) {
        const below = m.getLayer("cb") ? "cb" : m.getLayer("net") ? "net" : undefined;
        m.addSource("zones", { type: "geojson", data: d });
        m.addLayer({ id: "zone-fill", type: "fill", source: "zones", filter: ["==", ["get", "kind"], "zone"], paint: { "fill-color": "#4269d0", "fill-opacity": 0.08 } }, below);
        m.addLayer({ id: "zone-line", type: "line", source: "zones", filter: ["==", ["get", "kind"], "zone"],
          paint: { "line-color": "#4269d0", "line-opacity": 0.7, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 16, 1.6] } }, below);
        m.addLayer({ id: "grounds", type: "fill", source: "zones", filter: ["==", ["get", "kind"], "grounds"], paint: { "fill-color": sfMap.token("--grey-dark"), "fill-opacity": 0.22 } }, below);
        if (m === map) m.addLayer({ id: "zone-sel", type: "line", source: "zones", filter: ["all", ["==", ["get", "kind"], "zone"], ["==", ["get", "cds"], ""]],
          paint: { "line-color": "#4269d0", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.5, 16, 3] } }, below);
      }
      if (m === map && m.getLayer("zone-sel")) m.setFilter("zone-sel", ["all", ["==", ["get", "kind"], "zone"], ["==", ["get", "cds"], S.school.cds]]);
    }).catch((e) => { if (window.console) console.info("map: no school zones (" + e.message + ")"); });
  }
  function drawOverlays(kind) {
    const cmap = CMAPS[kind].map;
    if (!cmap || !cmap.getLayer("ovl-ss")) return;
    const c = S.city;
    for (const [id, k] of OVL) {
      const on = k === "seg" ? c.seg > 0 : !!c[k];
      cmap.setLayoutProperty(id, "visibility", on ? "visible" : "none");
      if (k === "seg" && on) { cmap.setFilter(id, ["in", `|${c.seg}|`, ["get", "bs"]]); cmap.setFilter("ovl-bridge", ["in", `|${c.seg}|`, ["get", "br"]]); cmap.setLayoutProperty("ovl-bridge", "visibility", "visible"); }
      else if (k === "seg") cmap.setLayoutProperty("ovl-bridge", "visibility", "none");
      // A budget plan draws School Streets and connectors at the schools it funds them at.
      else if (k !== "seg") { const P = plan(); cmap.setFilter(id, P ? ["in", ["get", "cds"], ["literal", Object.keys(P.schools).filter((x) => P.schools[x].includes(k))]] : null); }
    }
  }
  function drawCityMap(kind) {
    const M = CMAPS[kind], cmap = M.map;
    if (!cmap || !cmap.sfReady) return;
    const v = cvals(kind), b = brk(kind), C = RAMP();
    M.fc.features.forEach((f, i) => { f.properties.v = v[i]; });
    cmap.getSource("cb").setData(M.fc);
    cmap.setPaintProperty("cb", "circle-color", ["step", ["get", "v"], C[0], ...b.flatMap((x, i) => [x, C[i + 1]])]);
    drawOverlays(kind);
    if (M.at != null && M.pop) M.pop.setHTML(popHtml(kind, M.at));
  }
  // A block's popover: its students and the map's own figure, today and with the scenario.
  function popHtml(kind, i) {
    const B = CJ.blocks, c = S.city;
    const row = (q, a, b) => `<tr><th scope="row">${q}</th><td>${a}</td><td class="s">${b}</td></tr>`;
    const body = kind === "mode" ? row(MODE_BY[c.mode], pct(B.today[CJ.modes.indexOf(c.mode)][i]), pct(mixWith()[CJ.modes.indexOf(c.mode)][i]))
      : row("Safe trip in 15 min", pct(B.safe15Pct.today[i]), pct(B.safe15Pct[safeV()][i]));
    return `<b>${n2(B.students[i])} students live on this block</b><table><thead><tr><th></th><th>Today</th><th>${scenCol()}</th></tr></thead><tbody>${body}</tbody></table>`;
  }
  function selectBlock(kind, i) {
    const B = CJ.blocks, M = CMAPS[kind], cmap = M.map;
    if (lpop && lpop.isOpen()) lpop.remove();
    M.at = i; cmap.setFilter("cb-sel", ["==", ["get", "i"], i]);
    // Offset by the circle's own radius, so the popover's tip sits outside the block it points at.
    const off = radAt(B.students[i], cmap.getZoom()) + 6;
    if (!M.pop) {
      M.pop = new maplibregl.Popup({ className: "tr-pop", closeButton: true, closeOnClick: false, maxWidth: "270px", focusAfterOpen: false });
      M.pop.on("close", () => { M.at = null; if (cmap && cmap.sfReady) cmap.setFilter("cb-sel", ["==", ["get", "i"], -1]); });
    }
    M.pop.setOffset(off).setLngLat([B.lon[i], B.lat[i]]).setHTML(popHtml(kind, i));
    if (!M.pop.isOpen()) M.pop.addTo(cmap);
  }
  function closePop(kind) { (kind ? [CMAPS[kind]] : Object.values(CMAPS)).forEach((M) => { if (M.pop && M.pop.isOpen()) M.pop.remove(); }); }
  // The plan's bikeway types, as the popover names them.
  const BIKEWAY_KIND = { Separated: "separated bike lane", Shared: "shared street", "Shared-use Path": "shared-use path", "Car-free": "car-free street", "Plan shared, upgraded to separated": "separated bike lane where the plan draws a shared street" };
  // A bikeway, connector or School Street line: its name in a popover at the click.
  function selectLine(kind, f, at) {
    closePop(kind);
    const cmap = CMAPS[kind].map;
    const p = f.properties, sch = (cds) => (SCH.find((s) => s.cds === cds) || {}).name || "a school";
    const kinds = String(p.types || "").split("|").filter(Boolean).map((t) => BIKEWAY_KIND[t] || t.toLowerCase());
    const bs = String(p.bs || "").split("|").filter(Boolean), br = String(p.br || "").split("|").filter(Boolean);
    const html = f.layer.id === "ovl-seg" ? `<b>${p.street}</b><br>New ${kinds.length ? kinds.join(" and ") : "bikeway"}, ${p.mi} mi, in the ${andList(bs.map((b) => `$${b}M`))} set${br.includes(String(S.city.seg)) ? "<br>A bridge: brings nobody within a safe ride on its own" : ""}`
      : f.layer.id === "ovl-conn" ? `<b>School Connector street</b><br>To ${sch(p.cds)}` : `<b>School Street activation</b><br>At ${sch(p.cds)}`;
    cmap.setFilter("ovl-sel", ["==", ["get", "id"], f.layer.id === "ovl-seg" ? p.id : ""]);
    cmap.setFilter("ovl-csel", ["==", ["get", "cds"], f.layer.id === "ovl-conn" ? p.cds : ""]);
    if (lpop) lpop.remove();
    lpop = new maplibregl.Popup({ className: "tr-pop", closeButton: true, closeOnClick: false, maxWidth: "240px", focusAfterOpen: false, offset: 10 });
    lpop.on("close", () => { if (cmap.getLayer("ovl-sel")) { cmap.setFilter("ovl-sel", ["==", ["get", "id"], ""]); cmap.setFilter("ovl-csel", ["==", ["get", "cds"], ""]); } });
    lpop.setLngLat(at).setHTML(html).addTo(cmap);
  }
  const segSet = (sel, v, off) => $$(`${sel} button`).forEach((b) => { b.setAttribute("aria-checked", String(b.dataset.v === v)); b.disabled = !!off; });
  function renderCity() {
    const c = S.city;
    // Under a budget plan the school view's switches show that school's own changes.
    const cs = S.view === "school" ? cityFor(S.school.cds) : c;
    // The switches say which changes the plans may use, in both views.
    $$("[data-csw]").forEach((b) => b.setAttribute("aria-checked", String(S.avail[b.dataset.csw] !== 0)));
    $$("[data-reset]").forEach((b) => (b.disabled = atStart()));
    segSet("[data-assign]", c.assign); segSet("[data-cmode]", c.mode, false); segSet("[data-bsort]", S.bsort); segSet("[data-budget]", String(S.budget));
    // Each scenario with what it holds and its budget a year (the yearly cost plus the one-time cost over 4 years),
    // and which one the settings match. None matching reads as Custom.
    const now = scenOf(), costs = {};
    for (const k of Object.keys(SCEN)) {
      $$(`[data-scen="${k}"]`).forEach((b) => { b.setAttribute("aria-checked", String(k === now)); b.disabled = !SCEN[k]; });
      $$(`[data-scen-line="${k}"]`).forEach((el) => (el.textContent = scenSummary(k)));
      let cost = "\u00a0";
      if (CJ && SCEN[k] && SCEN[k].plan) { const p = planFor(SCEN[k].plan); if (p) { const a = p.at.central, sp = a.once + 4 * a.year;
        // A plan that runs out of changes worth buying says how much of its budget it spends.
        cost = `${money(a.year + a.once / 4)} a year, ${sp < p.budget - 0.5 ? `$${Math.round(sp)}M of ` : ""}$${p.budget}M over 4 years`; } }
      else if (CJ && SCEN[k]) { const p = SCEN[k].c, kk = cityCost(p), t = kk.year + kk.once / 4; cost = t > 0 ? `${money(t)} a year` : "No cost"; }
      costs[k] = cost;
    }
    $$("[data-scen-pick]").forEach((el) => { el.value = now || ""; [...el.options].forEach((o) => { if (o.value) o.disabled = !SCEN[o.value]; }); });
    $$("[data-scen-pick-line]").forEach((el) => (el.innerHTML = now ? `${scenSummary(now)} <b>${costs[now]}</b>` : "Your own mix of changes, set under Advanced Options."));
    $$("[data-scen-state]").forEach((el) => (el.textContent = now ? "" : "Custom"));
    $$("[data-scen-name]").forEach((el) => (el.textContent = scenCol()));
    const on = AV.filter((k) => S.avail[k] !== 0).length;
    $("[data-ctl-sum=city]").textContent = `${on} of ${AV.length} changes available`;
    cityResults(); cityLegend("mode"); cityLegend("safe");
    if (!CJ) {
      $("[data-city-kpi]").textContent = CJERR ? LOAD_FAIL : "Loading the city's figures…";
      if (!CJP) cityData().then(render).catch((e) => { CJERR = e; console.error("School Trips: the city's figures didn't load", e); render(); });
      return;
    }
    cityKpi(); cityBars();
    if (S.view === "city") for (const kind of Object.keys(CMAPS)) { cityMap(kind); const m = CMAPS[kind].map; if (m) { m.resize(); drawCityMap(kind); } }
  }

  // ---------- the school ----------
  const files = {};
  function load(cds) {
    if (!files[cds]) files[cds] = fetch(`${D.base}/${cds}.json`).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    return files[cds];
  }
  // The school's figures for the City's switches, exactly, from its own file's city block (school-sim.py,
  // school_city), with the changes applied on top of the sets: makeCityModel's schoolFig and schoolFigC.
  function schoolType(s) {
    const r = Object.keys(s.ranges || {});
    const t = r.length > 1 ? r.join(" and ") : r[0] === "K-5" ? "Elementary" : r[0] === "6-8" ? "Middle" : r[0] === "9-12" ? "High" : "School";
    return `${t} school, ${s.private ? "private" : s.charter ? "charter" : "SFUSD"}`;
  }
  const hm = (t) => { if (!t) return ""; const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")}${h < 12 ? "a" : "p"}`; };
  let F = null, map = null, mapFor = null, NET = null;
  function renderSchool() {
    const o = S.school, s = byCds[o.cds];
    const pk = $("[data-school-pick]"); if (document.activeElement !== pk) pk.value = s.name;
    $("[data-school-type]").textContent = schoolType(s);
    $("[data-bands]").innerHTML = Object.entries(s.ranges).map(([k, r]) => `<tr><td>${k}</td><td>${n2(r.n)}</td><td>${hm(r.d)}</td><td>${hm(r.p)}</td></tr>`).join("");
    $("[data-facts]").innerHTML = `<tr><th>Distance to today's all-ages bikeways</th><td>${blkLong(s.bt)}</td></tr><tr><th>Where SFMTA's draft map puts it</th><td>${!s.grp || /^No SFMTA icon/.test(s.grp) ? "Not on the map" : s.grp}</td></tr>${s.inj != null ? `<tr><th>Injury crashes near it at bell times, 5 years</th><td>${n2(s.inj)}</td></tr>` : ""}`;
    const k5 = !!s.ranges["K-5"], k8 = k5 || !!s.ranges["6-8"];
    // E-bike help, the e-cargo month and the bike bus run only where most students within 2 miles have a safe bike route.
    const gate = MD && MD.IN_GATE.has(s.cds) ? "" : " E-bike help, e-cargo bike months and bike buses reach schools where most students within 2 miles have a safe bike route, and this isn't one.";
    $("[data-togs-hint]").textContent = (!k8 ? "School Streets, walking upgrades, walking school buses, travel trackers, curb restrictions and shuttle loops reach younger students only." : !k5 ? "School Streets, walking school buses, travel trackers and curb restrictions reach TK-5 students only." : "") + (MD ? gate : "");
    const SC = cityFor(o.cds), on = CSW.filter((k) => SC[k]).length;
    $("[data-ctl-sum=school]").textContent = `${on} of ${CSW.length} changes on`;
    if (!F || F.cds !== o.cds) {
      $("[data-school-kpi]").textContent = `Loading ${s.name}…`;
      load(o.cds).then((f) => { F = f; if (S.school.cds === f.cds) renderSchool(); }).catch(() => { $("[data-school-kpi]").textContent = `${s.name}'s figures didn't load.`; });
      return;
    }
    if (!CJ || !F.city) { $("[data-school-kpi]").textContent = F.city ? (CJERR ? LOAD_FAIL : "Loading the city's figures…") : `${s.name}'s figures for these changes aren't in this build yet.`; return; }
    const T = MD.schoolFig(F.city, F.cds, todayKey(), MD.CEN, "today"), X = MD.schoolFigC(F.city, F.cds, SC);
    $("[data-school-kpi]").innerHTML = "";
    // Under a budget plan, what it funds at this school.
    const P = plan();
    if (P) {
      const ids = P.schools[o.cds] || [];
      $("[data-school-kpi]").innerHTML = `${SCEN_NAME[S.city.plan]} at $${P.budget}M funds ${ids.length ? andList(ids.map((id) => ONE[id] || id)) : "nothing"} here${P.city.seg || P.city.carpool || P.city.calm || P.city.muni ? `, beside its citywide ${andList([P.city.seg ? `$${P.city.seg}M of new bikeways` : "", P.city.carpool ? "carpool matching" : "", P.city.calm ? "school zone speed limits" : "", P.city.muni ? "free Muni for caregivers" : ""].filter(Boolean))}` : ""}.`;
    }
    schoolResults(s, T, X);
    drawSchoolMap(o);
  }
  // This school's figures beside the City's: single-family car, safe trip, average trip and parents taking a child,
  // then what its share of the changes costs.
  function schoolResults(s, T, X) {
    const N = T.N, c = cityFor(s.cds);
    const cnt = (v) => (v == null ? "n/a" : `${n2(v)}<small>${pct(100 * v / N)}</small>`);
    const row = (q, a, b) => `<tr><th scope="row">${q}</th><td>${a}</td><td class="s">${b}</td></tr>`;
    const mn = (F) => (F.min != null ? `${(F.min / N).toFixed(1)}<small>minutes</small>` : "n/a");
    $("[data-school-res]").innerHTML = `<table class="tr-mtab"><thead><tr><th></th><th>Today</th><th>${scenCol()}</th></tr></thead><tbody>`
      + row("Come by single-family car<em>students</em>", cnt(T.modes[0]), cnt(X.modes[0]))
      + `</tbody></table>` + goalBar(100 * T.modes[0] / N, 100 * X.modes[0] / N)
      + `<table class="tr-mtab"><tbody>`
      + row("Average trip<em>minutes, each student</em>", mn(T), mn(X))
      + row("Caregivers taking a child", cnt(N - T.alone), cnt(N - X.alone))
      + `<tr><th scope="row">Kids hurt a year</th><td colspan="2" class="tr-cw"><a href="#city" data-tab="city">Citywide only, see Citywide Scenarios</a></td></tr>`
      + `</tbody></table>`;
    // The changes that reach this school, priced as the City prices them. New bikeways and carpool matching are
    // citywide, so they aren't split by school.
    const v = MD.variant(c), k5 = !!(s.ranges && s.ranges["K-5"]), k8 = k5 || !!(s.ranges && s.ranges["6-8"]);
    const without = (p) => MD.schoolFigC(F.city, F.cds, { ...c, [p]: 0 });
    const K = MD.schoolCost(s, c, X, without), { muni, ebk, riders, conn, calmM, once, year } = K, ppl = K.people;
    const st = [c.school_street && k5 ? `${COST.ssStaff} part-time School Street activation staff` : "", riders ? `${+(riders / COST.busRiders).toFixed(1)} bus ${riders / COST.busRiders > 1.05 ? "drivers" : "driver"}` : ""].filter(Boolean);
    const m$ = (m) => (m <= 0 ? "None" : m >= 1 ? money(m) : "$" + sig2(m * 1e3) + "K");
    const one = (q, val) => `<tr><th scope="row">${q}</th><td>${val}</td></tr>`;
    $("[data-school-budget]").innerHTML = `<table class="tr-ctab"><tbody>`
      + one(`One-time cost<em>${[c.safer_crossings && k8 ? "safety upgrades for walking" : "", calmM ? "calmed streets" : "", c.calm ? "school zone speed limits" : "", conn ? "its School Connector" : "", c.school_street && k5 ? "School Street set-up" : "", ebk ? `e-bike vouchers for ${n2(ebk)}` : "", c.curb_restriction && k5 ? "curb restriction" : "", K.badN ? `20 mph signs on ${n2(K.badN)} business ${K.badN > 1 ? "corridors" : "corridor"}` : "", K.humpN ? `${n2(K.humpN)} speed ${K.humpN > 1 ? "humps" : "hump"}` : ""].filter(Boolean).join(", ") || "Nothing here"}</em>`, m$(once))
      + one(`Yearly cost<em>${[muni || K.muniToday ? `Muni for ${n2(muni + K.muniToday)} caregivers` : "", riders ? `${n2(riders)} shuttle riders` : "", c.travel_tracker && k5 ? "travel tracker" : "", K.bb ? "a bike bus route" : "", K.ec ? "12 e-cargo bike months" : "", K.camN ? "a speed camera, which fines are expected to cover" : ""].filter(Boolean).join(", ") || (year > 0 ? "Staff" : "Nothing yearly")}</em>`, m$(year))
      + one(`Staff<em>${st.join(", ") || "None for these changes"}</em>`, ppl ? (Math.round(ppl * 10) / 10).toString() : "0")
      + `</tbody></table><p class="tr-cnote">New bikeways, carpool matching and the yearly staff of the e-bike and e-cargo programs are in Citywide Scenarios' budget, not split by school.</p>`;
  }
  // A home block is shaded when a student there has a safe trip of 15 minutes on the City's network (homes.safeV, a bit per city.json variant).
  function homes() {
    const bit = 1 << Math.max(0, CJ ? (CJ.safeVariants || CJ.variants).indexOf(svar(cityFor(S.school.cds))) : 0), h = F.homes, sv = h.safeV || h.safe;
    return { type: "FeatureCollection", features: h.lon.map((x, k) => ({ type: "Feature", properties: { k: h.students[k], s: (sv[k] & bit) ? 1 : 0 }, geometry: { type: "Point", coordinates: [x, h.lat[k]] } })) };
  }
  // The City's lines that reach this map: the new bikeway segments switched on, and this school's connector and School Street.
  let OVD = null;
  let XD = null;
  const xData = () => (XD = XD || fetch(`${D.base}/crossings.json`).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  const ovData = () => (OVD = OVD || fetch(`${D.base}/overlays.json`).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }));
  function added(d, cds) {
    const c = cityFor(cds), me = d.schools.find((x) => x.cds === cds) || { connector: [], schoolStreet: [] };
    const ls = (c.connector ? me.connector : []).concat((d.segments || []).filter((p) => c.seg && p.budgets.includes(c.seg)).flatMap((p) => p.lines));
    const fc = (a) => ({ type: "FeatureCollection", features: a.map((l) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: l } })) });
    return { add: fc(ls), ss: fc(c.school_street ? me.schoolStreet : []) };
  }
  function drawSchoolMap(o) {
    const el = $("[data-school-map]"), s = byCds[o.cds];
    if (!window.sfMap) return;
    if (!map) {
      const pad = 0.025;
      map = sfMap.create(el, { bounds: [[s.lon - pad * 1.3, s.lat - pad], [s.lon + pad * 1.3, s.lat + pad]], padding: () => 20 });
      if (!map) return;
      map.on("load", () => {
        const before = sfMap.under(map);
        map.addSource("net", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("add", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("ss", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("homes", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("door", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        map.addSource("xing", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        const w = ["interpolate", ["linear"], ["zoom"], 11, 1.4, 16, 4];
        map.addLayer({ id: "net", type: "line", source: "net", layout: { "line-cap": "round" }, paint: { "line-color": "#4269d0", "line-width": w, "line-opacity": 0.55 } }, before);
        map.addLayer({ id: "add", type: "line", source: "add", layout: { "line-cap": "round" }, paint: { "line-color": "#4269d0", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 3, 16, 7] } }, before);
        map.addLayer({ id: "ss", type: "line", source: "ss", layout: { "line-cap": "round" }, paint: { "line-color": sfMap.token("--ink"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 5, 16, 12] } }, before);
        const r = ["sqrt", ["get", "k"]];
        map.addLayer({ id: "homes", type: "circle", source: "homes", layout: { "circle-sort-key": ["get", "s"] }, paint: {
          "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 11, ["max", 2, ["*", 2.6, r]], 17, ["max", 5, ["*", 16, r]]],
          "circle-color": ["match", ["get", "s"], 1, sfMap.token("--seq-3"), sfMap.token("--grey-light")], "circle-opacity": 0.85 } }, before);
        map.addLayer({ id: "xing", type: "circle", source: "xing", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 2.5, 16, 6],
          "circle-color": "#fff", "circle-stroke-color": "#4269d0", "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 12, 1.5, 16, 2.5] } });
        map.addLayer({ id: "door", type: "circle", source: "door", paint: { "circle-radius": 7, "circle-color": "#fff", "circle-stroke-color": sfMap.token("--ink"), "circle-stroke-width": 2.5 } });
        fetch(`${D.base}/network.json`).then((x) => x.json()).then((enc) => { NET = sfMap.decode(enc); map.getSource("net").setData({ type: "FeatureCollection", features: NET.map((l) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: l } })) }); }).catch(() => {});
        map.sfReady = true; drawSchoolMap(S.school); heat(map); zones(map);
      });
      return;
    }
    if (!map.sfReady) return;
    if (mapFor !== o.cds) {
      mapFor = o.cds;
      const h = F.homes; let x0 = s.lon, x1 = s.lon, y0 = s.lat, y1 = s.lat;
      // Frame the blocks holding most of the school's students, not every far block.
      const idx = h.students.map((v, k) => [v, k]).sort((a, b) => b[0] - a[0]); let acc = 0; const tot = h.students.reduce((a, b) => a + b, 0);
      for (const [v, k] of idx) { if (acc > 0.8 * tot) break; acc += v; x0 = Math.min(x0, h.lon[k]); x1 = Math.max(x1, h.lon[k]); y0 = Math.min(y0, h.lat[k]); y1 = Math.max(y1, h.lat[k]); }
      // Centred on the school, so it never sits at an edge under the legend: the frame reaches as far each way as
      // those blocks reach on their far side.
      const dx = Math.max(s.lon - x0, x1 - s.lon), dy = Math.max(s.lat - y0, y1 - s.lat);
      map.fitBounds([[s.lon - dx, s.lat - dy], [s.lon + dx, s.lat + dy]], { padding: { top: 110, bottom: 110, left: 30, right: 30 }, duration: 0 });
      map.getSource("door").setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [s.lon, s.lat] } }] });
    }
    map.getSource("homes").setData(homes());
    $("[data-ss-key]").hidden = !cityFor(S.school.cds).school_street;
    // The intersections the chosen reach of safety upgrades takes in, at a school with TK-8 grades (Bryan, 2026-10-13:
    // "in the school tool can you show which intersections might get some treatment with safer crossings").
    const SX = cityFor(s.cds), xOn = SX.safer_crossings && s.ranges && (s.ranges["K-5"] || s.ranges["6-8"]);
    $("[data-x-key]").hidden = !xOn;
    const xr = { 350: 0, 660: 1, 1320: 2 }[SX.xreach || 350];
    xData().then((d) => { if (S.school.cds !== o.cds) return; map.getSource("xing").setData({ type: "FeatureCollection",
      features: (xOn ? d.schools[o.cds] || [] : []).filter((x) => x[2] <= xr).map((x) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [x[0], x[1]] } })) }); }).catch(() => {});
    ovData().then((d) => { if (S.school.cds !== o.cds) return; const a = added(d, o.cds); map.getSource("add").setData(a.add); map.getSource("ss").setData(a.ss); }).catch(() => {});
  }

  // ---------- your trip ----------
  // The reader's trip is routed here, in the browser. Only the address box's suggestions go to Google; the address is never recorded or put in the address bar.
  const TRIP = { home: null, label: "", maps: [null, null], R: null, A: null, loading: null, res: null, key: null, fit: null, near: false, msg: "" };
  const MODE_C = { walk: "#2f7d76", bike: "#c8a25e", car: "#3d4450" };
  const getJson = (f) => fetch(`${D.base}/${f}`).then((r) => { if (!r.ok) throw new Error(f + " " + r.status); return r.json(); });
  function tripData() {
    if (!TRIP.loading) TRIP.loading = Promise.all([getJson("trip-graph.json"), getJson("addresses.json")]).then(([g, a]) => {
      TRIP.R = window.makeRouter(g); TRIP.R.rules = TRIP.R.rules || g.rules; TRIP.A = new Map(a.streets.map((x) => [x.s, x.p]));
    });
    return TRIP.loading;
  }
  let NETP = null;
  const netData = () => NETP || (NETP = getJson("network.json").then((enc) => sfMap.decode(enc)));
  const SUFFIX = { STREET: "ST", AVENUE: "AVE", AV: "AVE", BOULEVARD: "BLVD", DRIVE: "DR", ROAD: "RD", PLACE: "PL", COURT: "CT", LANE: "LN", TERRACE: "TER", ALLEY: "ALY", PLAZA: "PLZ", HIGHWAY: "HWY", CIRCLE: "CIR", PARKWAY: "PKWY", SQUARE: "SQ" };
  const title = (t) => t.toLowerCase().replace(/\b0(\d)/g, "$1").replace(/\b[a-z]/g, (c) => c.toUpperCase());
  // "400 Monterey Blvd" to the side of its hundred block, the nearest hundred block when that side isn't listed.
  function findAddress(text) {
    const t = text.toUpperCase().replace(/,.*$/, "").replace(/\b(APT|UNIT|STE|SUITE|#)\b.*$/, "").replace(/[.#]/g, " ").replace(/\s+/g, " ").trim();
    const m = t.match(/^(\d+)[A-Z]?(?:-\d+)?\s+(.+)$/);
    if (!m) return null;
    const num = Number(m[1]), w = m[2].split(" ").map((x) => (/^\d(ST|ND|RD|TH)$/.test(x) ? "0" + x : x));
    const last = w[w.length - 1];
    if (SUFFIX[last]) w[w.length - 1] = SUFFIX[last];
    let hit = w.join(" "), pts = TRIP.A.get(hit);
    if (!pts) {
      const known = new Set(Object.values(SUFFIX).concat(["ST", "WAY"]));
      const base = known.has(w[w.length - 1]) && w.length > 1 ? w.slice(0, -1).join(" ") : hit;
      const c = [...TRIP.A.keys()].filter((k) => k === base || k.startsWith(base + " "));
      if (!c.length) return null;
      c.sort((a, b) => TRIP.A.get(b).length - TRIP.A.get(a).length);
      hit = c[0]; pts = TRIP.A.get(hit);
    }
    const want = Math.floor(num / 100) * 2 + (num % 2);
    let best = null, bs = Infinity;
    for (const p of pts) { const sc = Math.abs(Math.floor(p[0] / 2) - Math.floor(want / 2)) * 2 + (p[0] % 2 !== want % 2 ? 1 : 0); if (sc < bs) { bs = sc; best = p; } }
    return { home: [best[1] / 1e5, best[2] / 1e5], label: `${num} ${title(hit)}` };
  }
  function setHome(home, label) { TRIP.home = home; TRIP.label = label || ""; TRIP.fit = null; TRIP.msg = ""; renderTrip(); }
  function changeSet(sc) {
    const c = S.city, out = new Set();
    if (c.connector) sc.connector.forEach((x) => out.add(x));
    return out;
  }
  const fc = (f) => ({ type: "FeatureCollection", features: f });
  function tripMap(i) {
    if (TRIP.maps[i] || !window.sfMap) return TRIP.maps[i];
    const s = byCds[S.school.cds], pad = 0.012;
    const m = sfMap.create($(`[data-trip-map="${i}"]`), { bounds: [[s.lon - pad * 1.3, s.lat - pad], [s.lon + pad * 1.3, s.lat + pad]], padding: () => 16 });
    if (!m) return null;
    TRIP.maps[i] = m;
    m.on("load", () => {
      const before = sfMap.under(m);
      ["net", "added", "routes", "pts"].forEach((k) => m.addSource(k, { type: "geojson", data: fc([]) }));
      m.addLayer({ id: "net", type: "line", source: "net", layout: { "line-cap": "round" }, paint: { "line-color": "#4269d0", "line-width": 3, "line-opacity": 0.55 } }, before);
      m.addLayer({ id: "added", type: "line", source: "added", layout: { "line-cap": "round" }, paint: { "line-color": "#4269d0", "line-width": 7, "line-opacity": 0.8 } }, before);
      const col = ["match", ["get", "mode"], "walk", MODE_C.walk, "bike", MODE_C.bike, MODE_C.car];
      const off = ["match", ["get", "mode"], "walk", -4, "bike", 0, 4];
      m.addLayer({ id: "r-safe", type: "line", source: "routes", filter: ["==", ["get", "safe"], 1], layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": col, "line-width": 3.5, "line-offset": off } });
      m.addLayer({ id: "r-off", type: "line", source: "routes", filter: ["==", ["get", "safe"], 0], layout: { "line-join": "round" }, paint: { "line-color": col, "line-width": 3.5, "line-offset": off, "line-dasharray": [1.2, 1.4] } });
      m.addLayer({ id: "pts", type: "circle", source: "pts", paint: { "circle-radius": 7, "circle-color": ["match", ["get", "k"], "home", sfMap.token("--ink"), "#fff"], "circle-stroke-color": sfMap.token("--ink"), "circle-stroke-width": 2.5 } });
      netData().then((N) => m.getSource("net").setData(fc(N.map((l) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: l } }))))).catch(() => {});
      m.sfReady = true; drawTrip();
    });
    m.on("click", (e) => setHome([e.lngLat.lng, e.lngLat.lat], ""));
    m.getCanvas().style.cursor = "crosshair";
    return m;
  }
  function drawTrip() {
    const s = byCds[S.school.cds], t = TRIP.res, R = TRIP.R;
    const sc = R && R.schools[s.cds], door = sc ? sc.door : [s.lon, s.lat];
    TRIP.maps.forEach((m, i) => {
      if (!m || !m.sfReady) return;
      const pts = [{ type: "Feature", properties: { k: "school" }, geometry: { type: "Point", coordinates: door } }];
      if (TRIP.home) pts.unshift({ type: "Feature", properties: { k: "home" }, geometry: { type: "Point", coordinates: TRIP.home } });
      m.getSource("pts").setData(fc(pts));
      let f = [];
      if (t) {
        const safe = R.isSafe(i ? TRIP.extra : null);
        f = R.geo(t.carOk ? t.car.P : null, "car", () => false).concat(R.geo(t.walk.P, "walk", safe), R.geo((i ? t.bike1 : t.bike0).P, "bike", safe));
      }
      m.getSource("routes").setData(fc(f));
      m.getSource("added").setData(fc(i && R && TRIP.extra ? R.chainGeo(TRIP.extra) : []));
      const fit = TRIP.key || s.cds;
      if (m.sfFit !== fit) {
        m.sfFit = fit;
        let x0 = door[0], x1 = door[0], y0 = door[1], y1 = door[1];
        const add = (p) => { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); };
        if (TRIP.home) add(TRIP.home);
        f.forEach((q) => q.geometry.coordinates.forEach(add));
        if (x1 - x0 < 0.004) { x0 -= 0.004; x1 += 0.004; }
        if (y1 - y0 < 0.003) { y0 -= 0.003; y1 += 0.003; }
        m.fitBounds([[x0, y0], [x1, y1]], { padding: 28, duration: 0 });
      }
    });
  }
  function renderTrip() {
    if (S.view !== "school") return;
    const s = byCds[S.school.cds], kpi = $("[data-trip-kpi]"), tab = $("[data-trip-table]"), note = $("[data-trip-note]");
    if (TRIP.near || TRIP.home) { tripMap(0); tripMap(1); TRIP.maps.forEach((m) => m && m.resize()); }
    if (!TRIP.home) {
      kpi.textContent = TRIP.msg || `Type your address to see your trip to ${s.name} by each way, today and with the scenario.`;
      tab.innerHTML = ""; note.textContent = ""; TRIP.res = null; TRIP.key = null; drawTrip(); return;
    }
    if (!TRIP.R) { kpi.textContent = "Loading the street network…"; tripData().then(renderTrip).catch(() => { kpi.textContent = "The street network didn't load. Try reloading the page."; }); return; }
    const sc = TRIP.R.schools[s.cds], extra = changeSet(sc);
    const key = [s.cds, TRIP.home.join(","), [...extra].sort((a, b) => a - b).join(".")].join("|");
    if (TRIP.key !== key) { TRIP.key = key; TRIP.extra = extra; TRIP.res = TRIP.R.trip(TRIP.home, sc.door, extra); }
    const t = TRIP.res, from = TRIP.label ? `from ${TRIP.label}` : "from there";
    if (!t) { kpi.textContent = `We can't find a street route ${from} to ${s.name}. Try another address, or click your home on a map.`; tab.innerHTML = ""; note.textContent = ""; drawTrip(); return; }
    const mi = (m) => m / 1609.344, f1 = (x) => (Math.round(x * 10) / 10).toFixed(1), mn = (x) => Math.round(x) + " min";
    const sm = (a, b) => `${f1(mi(a))} of ${f1(mi(b))} mi`;
    const b0 = t.bike0, b1 = t.bike1, same = Math.abs(b1.safe - b0.safe) < 1 && Math.abs(b1.m - b0.m) < 1 && Math.abs(t.walk.safe1 - t.walk.safe0) < 1;
    // The table below carries the times and safe miles, so the headline only says when the scenario misses this route.
    kpi.textContent = same ? `The scenario doesn't reach this route ${from} to ${s.name}.` : "";
    // The car is routed on OpenStreetMap's drivable streets (tools/travel/osm-drive-network.py), so it is timed
    // wherever the address and the door both reach one; school-sim's car-route check holds the rest.
    t.carOk = !!t.car.P;
    const k5to8 = !!(s.ranges["K-5"] || s.ranges["6-8"]), bus = t.carOk && S.city.yellow_bus && k5to8 && t.walkMi > TRIP.R.rules.busOverMi;
    const row = (lab, c, a, b, sa, sb) => `<tr><th scope="row"><i style="background:${c}"></i>${lab}</th><td>${a}</td><td class="s">${b}</td><td>${sa || ""}</td><td class="s">${sb || ""}</td></tr>`;
    tab.innerHTML = `<table class="tr-trip2"><thead><tr><th></th><th>Time today</th><th>${scenCol()}</th><th>Safe miles today</th><th>${scenCol()}</th></tr></thead><tbody>`
      + row("Walk", MODE_C.walk, mn(t.walk.min), mn(t.walk.min), sm(t.walk.safe0, t.walk.m), sm(t.walk.safe1, t.walk.m))
      + row("Bike", MODE_C.bike, mn(b0.min), mn(b1.min), sm(b0.safe, b0.m), sm(b1.safe, b1.m))
      + (t.carOk ? row("Car", MODE_C.car, mn(t.car.min), mn(t.car.min)) : row("Car", MODE_C.car, "Not timed", "Not timed"))
      + row("Muni", "#9c5f3c", mn(t.transit.min), mn(t.transit.min))
      + (bus ? row("Shuttle loop", "#6f7f94", "", mn(t.car.min + TRIP.R.rules.busExtraMin)) : "")
      + `</tbody></table>`;
    note.textContent = (t.carOk ? "Safe streets are the plan's all ages network plus the scenario's. Muni times are a rough estimate, not the schedule: 10 minutes to the stop, then 8 mph." : "We couldn't find a street a car can use near this address, so the car isn't timed.");
    drawTrip();
  }
  const addr = $("[data-addr]"), adl = $("[data-addr-list]");
  addr.addEventListener("focus", () => { tripData().catch(() => {}); });
  // The city's address points, for a typed address when Google's suggestions aren't available.
  function cityLookup(v) {
    $("[data-trip-kpi]").textContent = "Looking up your address…";
    tripData().then(() => {
      const a = findAddress(v);
      if (!a) { TRIP.home = null; TRIP.msg = `We couldn't find "${v}" among San Francisco's addresses. Try a number and street, like 400 Monterey Blvd, or click your home on a map.`; renderTrip(); return; }
      setHome(a.home, a.label);
    }).catch(() => { $("[data-trip-kpi]").textContent = "The address list didn't load. Try reloading the page."; });
  }
  // Suggestions as you type from Google Places (Autocomplete and Place Details, New), limited to San Francisco.
  // One session token per search, so Google bills the suggestions together with the pick
  // (developers.google.com/maps/documentation/places/web-service/session-pricing). With no key in
  // the build, or once Google refuses a request, the box falls back to the city's address points.
  const G = { off: !D.gkey, token: null, hits: [], at: -1, t: null, seq: 0 };
  const GAPI = "https://places.googleapis.com/v1/";
  const SF_BOX = { rectangle: { low: { latitude: 37.70, longitude: -122.52 }, high: { latitude: 37.84, longitude: -122.35 } } };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const gHide = () => { adl.hidden = true; addr.setAttribute("aria-expanded", "false"); addr.removeAttribute("aria-activedescendant"); };
  function gDraw() {
    adl.innerHTML = (G.hits.length ? G.hits.map((h, k) => `<li role="option" id="tr-addr-${k}" data-addr-ac="${k}" aria-selected="${k === G.at}">${esc(h.main)}<small>${esc(h.sub)}</small></li>`).join("") : '<li class="none">No San Francisco address matches</li>') + '<li class="none tr-google">Suggestions from Google</li>';
    adl.hidden = false; addr.setAttribute("aria-expanded", "true");
  }
  function gOff(e, q) {
    if (window.console) console.info("address: Google suggestions unavailable here (" + (e && e.message) + "); using the city's address points");
    G.off = true; gHide();
    if (/^\s*\d+\s+\S{3,}/.test(q)) cityLookup(q);
  }
  function gSuggest(q) {
    const n = ++G.seq;
    if (!G.token) G.token = window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + String(Math.random()).slice(2);
    fetch(GAPI + "places:autocomplete", { method: "POST", headers: { "Content-Type": "application/json", "X-Goog-Api-Key": D.gkey }, body: JSON.stringify({ input: q, sessionToken: G.token, locationRestriction: SF_BOX, includedRegionCodes: ["us"] }) })
      .then((r) => { if (!r.ok) throw new Error("autocomplete " + r.status); return r.json(); })
      .then((j) => {
        if (n !== G.seq || document.activeElement !== addr) return;
        G.hits = (j.suggestions || []).map((x) => x.placePrediction).filter(Boolean).slice(0, 5).map((p) => {
          const f = p.structuredFormat || {};
          return { id: p.placeId, main: (f.mainText && f.mainText.text) || p.text.text, sub: (f.secondaryText && f.secondaryText.text) || "" };
        });
        G.at = G.hits.length ? 0 : -1; gDraw();
      })
      .catch((e) => gOff(e, q));
  }
  function gPick(h) {
    gHide(); clearTimeout(G.t); G.seq++; addr.value = h.main; addr.blur();
    $("[data-trip-kpi]").textContent = "Looking up your address…";
    const tok = G.token; G.token = null;
    fetch(GAPI + "places/" + encodeURIComponent(h.id) + (tok ? "?sessionToken=" + encodeURIComponent(tok) : ""), { headers: { "X-Goog-Api-Key": D.gkey, "X-Goog-FieldMask": "location" } })
      .then((r) => { if (!r.ok) throw new Error("place " + r.status); return r.json(); })
      .then((p) => tripData().then(() => setHome([p.location.longitude, p.location.latitude], h.main)))
      .catch(() => cityLookup(h.main));
  }
  function gMove(k) {
    if (!G.hits.length) return;
    G.at = (k + G.hits.length) % G.hits.length;
    $$("[data-addr-ac]", adl).forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.addrAc) === G.at)));
    const li = adl.querySelector(`[data-addr-ac="${G.at}"]`); if (li) addr.setAttribute("aria-activedescendant", li.id);
  }
  // Look the address up when the reader pauses typing: Google's suggestions after a quarter second, the city's lookup after 0.7 seconds.
  addr.addEventListener("input", () => {
    clearTimeout(G.t);
    const v = addr.value.trim();
    if (!G.off) { if (v.length < 3) { G.seq++; G.hits = []; gHide(); return; } G.t = setTimeout(() => gSuggest(v), 250); return; }
    if (/^\s*\d+\s+\S{3,}/.test(addr.value)) G.t = setTimeout(() => cityLookup(v), 700);
  });
  addr.addEventListener("keydown", (e) => {
    if (G.off || adl.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); gMove(G.at + (e.key === "ArrowDown" ? 1 : -1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (G.hits[G.at]) gPick(G.hits[G.at]); }
    else if (e.key === "Escape") gHide();
  });
  adl.addEventListener("mousedown", (e) => { const li = e.target.closest("[data-addr-ac]"); if (li) { e.preventDefault(); gPick(G.hits[Number(li.dataset.addrAc)]); } });
  addr.addEventListener("blur", () => setTimeout(gHide, 120));
  // Enter or leaving the box: an empty box clears the trip, and without Google the typed address is looked up.
  addr.addEventListener("change", () => {
    const v = addr.value.trim();
    if (!v) { setHome(null, ""); return; }
    if (G.off) { clearTimeout(G.t); cityLookup(v); }
  });
  // One tap clears either search box. Clearing the address also clears the trip.
  $$("[data-clear]").forEach((b) => b.addEventListener("click", () => {
    const el = document.getElementById(b.dataset.clear); el.value = ""; el.focus();
    if (el === addr) { clearTimeout(G.t); G.seq++; G.token = null; gHide(); setHome(null, ""); }
  }));
  if (window.IntersectionObserver) new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting) && !TRIP.near) { TRIP.near = true; renderTrip(); } }, { rootMargin: "0px" }).observe($(".tr-trip"));
  else TRIP.near = true;

  // ---------- views, the address ----------
  // The Citywide Goals view, which opens on SFMTA's plan (site/src/school-trips-wedges.mjs).
  const WG = wedgeUI(document.getElementById("v-goals"), D.wedges.T, D.wedges.W, D.wedges.plan, D.wedges.full, () => render());
  // A view that fails to draw says so where its figures are, so a control never moves while the figures sit still.
  const LOAD_FAIL = "The city's figures didn't load. Try reloading the page.";
  function failed(view, e) {
    console.error(`School Trips: the ${view} view didn't draw`, e);
    const v = document.getElementById("v-" + view);
    if (!v) return;
    let el = v.querySelector("[data-fail]");
    if (!el) { el = document.createElement("p"); el.className = "tr-fail"; el.setAttribute("role", "alert"); el.dataset.fail = ""; v.prepend(el); }
    el.textContent = "These figures didn't update because of an error. Try reloading the page.";
  }
  const guard = (view, fn) => { try { fn(); $$(`#v-${view} [data-fail]`).forEach((el) => el.remove()); } catch (e) { failed(view, e); } };
  function render() {
    heatCounts(); zones(map);
    $$(".tr-view").forEach((v) => v.classList.toggle("on", v.id === "v-" + S.view));
    $$("[data-view]").forEach((m) => (m.checked = m.dataset.view === S.view));
    $$("[data-crumb-view]").forEach((el) => (el.textContent = (($(`[data-view="${S.view}"]`) || {}).textContent || "").trim()));
    // A school map first framed while its view was hidden had no size; frame it again the first time it shows.
    if (map && map.sfReady && S.view === "school" && !map.sfShown) { map.sfShown = true; map.resize(); mapFor = null; }
    guard("city", renderCity); guard("school", renderSchool);
    if (S.view === "goals") guard("goals", WG.draw);
    const o = S.school, c = S.city;
    const q = new URLSearchParams({ w: WG.get().join(""), u: AV.map((k) => (S.avail[k] === 0 ? 0 : 1)).join(""), a: c.assign, d: c.mode, o: S.bsort, s: o.cds, p: c.plan || "today", b: S.budget });
    history.replaceState(null, "", "#" + S.view + "?" + q);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: "#" + S.view + "?" + q }));
    if (map && S.view === "school") map.resize();
    if (S.view !== "city") closePop();
    renderTrip();
  }
  function fromHash() {
    const [v] = location.hash.slice(1).split("?");
    if (v === "goals" || v === "city" || v === "school" || v === "comment") S.view = v;
    const q = new URLSearchParams(location.hash.split("?")[1] || "");
    if (/^\d+$/.test(q.get("w") || "")) WG.set([...q.get("w")].map(Number));
    const ub = q.get("u"), one = (k, ok) => { if (ok.includes(q.get(k))) S.city[{ d: "mode" }[k]] = q.get(k); };
    if (q.get("a") === "today") S.assign = "today";
    // Which changes the plans may use, one bit each in AV's order.
    if (ub && /^[01]+$/.test(ub) && ub.length <= AV.length) AV.forEach((k, j) => { if (j < ub.length) S.avail[k] = Number(ub[j]); });
    one("d", D.cityModes.map((x) => x[0]));
    if (D.barSorts.includes(q.get("o"))) S.bsort = q.get("o");
    if (byCds[q.get("s")]) S.school.cds = q.get("s");
    if (D.budgets.includes(Number(q.get("b")))) S.budget = Number(q.get("b"));
    const pk = q.get("p");
    if (pk === "today") Object.assign(S.city, CITY_OFF, { plan: null, mode: S.city.mode, assign: q.get("a") && S.assign !== PLAN_BG ? S.assign : "today" });
    else if (SCEN[pk] && SCEN[pk].plan && planC(pk)) Object.assign(S.city, planC(pk), { mode: S.city.mode });
  }
  function pickSchool(cds) {
    S.school.cds = cds; F = null; mapFor = null;
  }

  // ---------- events ----------
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button, a");
    if (!b || !b.closest(".tr-wide")) return;
    const grp = b.parentElement && b.parentElement.closest("[role=radiogroup]");
    if (b.dataset.tab) { e.preventDefault(); S.view = b.dataset.tab; return render(); }
    if (b.matches("[data-ctl-toggle]")) {
      const ctl = b.closest(".tr-ctl"), adv = ctl.querySelector("details.tr-adv");
      ctl.classList.toggle("open");
      // On a phone the button already opened the controls, so Advanced Controls inside shows open too.
      if (adv && ctl.classList.contains("open")) adv.open = true;
      return;
    }
    // A switch says whether the plans may use a change; the plan on show picks again.
    const replanNow = () => { if (S.city.plan) Object.assign(S.city, planC(S.city.plan), { mode: S.city.mode }); };
    if (b.dataset.csw) { const k = b.dataset.csw; S.avail[k] = S.avail[k] === 0 ? 1 : 0; replanNow(); return render(); }
    if (grp && grp.matches("[data-assign]")) { S.assign = b.dataset.v; if (S.city.plan) replanNow(); else S.city.assign = S.assign; return render(); }
    if (b.matches("[data-reset]")) { S.avail = Object.fromEntries(AV.map((k) => [k, 1])); S.budget = BUDGET0; S.assign = PLAN_BG; Object.assign(S.city, planC(GOAL0), { mode: S.city.mode }); return render(); }
    if (grp && grp.matches("[data-budget]")) { S.budget = Number(b.dataset.v); replanNow(); return render(); }
    if (grp && grp.matches("[data-bsort]")) { S.bsort = b.dataset.v; return render(); }
    if (grp && grp.matches("[data-cmode]")) { S.city.mode = b.dataset.v; return render(); }
    if (b.dataset.scen) { if (SCEN[b.dataset.scen]) { pickScen(b.dataset.scen); return render(); } return; }
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-scen-pick]")) { if (SCEN[e.target.value]) { pickScen(e.target.value); render(); } return; }
    if (!e.target.matches("[data-heat]")) return;
    S.heat = e.target.checked; $$("[data-heat]").forEach((x) => (x.checked = S.heat));
    heat(CMAPS.mode.map); heat(map);
  });
  // The school box is a searchable dropdown: focus shows every school, typing narrows by any word in the name.
  const pick = $("[data-school-pick]"), acl = $("[data-school-list]");
  const norm = (t) => t.toLowerCase().replace(/[^a-z0-9 ]+/g, " ");
  let acHits = [], acAt = -1;
  const grades = (s) => Object.keys(s.ranges || {}).join(", ");
  function acShow(q) {
    const w = norm(q).split(/\s+/).filter(Boolean);
    acHits = SCH.filter((s) => w.every((t) => norm(s.name).includes(t))).sort((a, b) => norm(a.name).trim().localeCompare(norm(b.name).trim()));
    acAt = acHits.length ? 0 : -1;
    acl.innerHTML = acHits.length ? acHits.map((s, k) => `<li role="option" id="tr-ac-${k}" data-ac="${k}" aria-selected="${k === acAt}">${s.name}<small>${grades(s)}</small></li>`).join("") : '<li class="none">No school matches</li>';
    acl.hidden = false; pick.setAttribute("aria-expanded", "true");
  }
  function acMove(k) {
    if (!acHits.length) return;
    acAt = (k + acHits.length) % acHits.length;
    $$("[data-ac]", acl).forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.ac) === acAt)));
    const li = acl.querySelector(`[data-ac="${acAt}"]`); if (li) { li.scrollIntoView({ block: "nearest" }); pick.setAttribute("aria-activedescendant", li.id); }
  }
  const acHide = () => { acl.hidden = true; pick.setAttribute("aria-expanded", "false"); pick.removeAttribute("aria-activedescendant"); };
  const acPick = (s) => { acHide(); pick.value = s.name; pickSchool(s.cds); pick.blur(); render(); };
  pick.addEventListener("focus", () => { pick.select(); acShow(""); });
  pick.addEventListener("input", () => acShow(pick.value));
  pick.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (acl.hidden) acShow(pick.value); acMove(acAt + (e.key === "ArrowDown" ? 1 : -1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (acHits[acAt]) acPick(acHits[acAt]); }
    else if (e.key === "Escape") { acHide(); pick.value = byCds[S.school.cds].name; pick.blur(); }
  });
  acl.addEventListener("mousedown", (e) => { const li = e.target.closest("[data-ac]"); if (li) { e.preventDefault(); acPick(acHits[Number(li.dataset.ac)]); } });
  pick.addEventListener("blur", () => setTimeout(() => { if (!acl.hidden) { acHide(); pick.value = byCds[S.school.cds].name; } }, 120));
  $("[data-school-pick]").addEventListener("change", (e) => { const q = e.target.value.trim().toLowerCase(); const s = byName[e.target.value] || SCH.find((x) => x.name.toLowerCase() === q) || SCH.find((x) => x.name.toLowerCase().includes(q)); if (q && s) pickSchool(s.cds); e.target.blur(); render(); });
  window.addEventListener("hashchange", () => { fromHash(); render(); });
  window.addEventListener("sfworks:view", (e) => { S.view = e.detail; render(); });

  fromHash(); render();
}

export function pages() {
  if (!has) return [];
  const dir = file.replace("index.html", "");
  const out = IDX.schools.map((s) => ({ path: `${path}/${s.cds}.json`, file: `${dir}${s.cds}.json`, html: fs.readFileSync(nodePath.join(SIM, `${s.cds}.json`)), sitemap: false }));
  // The all-ages network the sim counts as built today (protected only), written by tools/school-trips/school-sim.py.
  const net = readJson(nodePath.join(SIM, "today-net.json")).lines;
  out.push({ path: `${path}/network.json`, file: `${dir}network.json`, html: Buffer.from(JSON.stringify(encodeRuns(net))), sitemap: false });
  // SFMTA's upcoming all-ages bikeways, which the sim counts as built (bike-history/planned.json), for the City map.
  const planned = readJson(nodePath.join(DATA, "bike-history", "planned.json")).projects.flatMap((pr) => pr.blocks.map((b) => b.pts).filter((p) => p && p.length >= 2));
  out.push({ path: `${path}/planned-net.json`, file: `${dir}planned-net.json`, html: Buffer.from(JSON.stringify(encodeRuns(planned))), sitemap: false });
  // The City view's switch sets and home blocks, fetched once.
  const cf = cityFiles();
  if (cf.main) out.push({ path: `${path}/city.json`, file: `${dir}city.json`, html: cf.main, sitemap: false });
  if (cf.schools) out.push({ path: `${path}/city-schools.json`, file: `${dir}city-schools.json`, html: cf.schools, sitemap: false });
  if (fs.existsSync(ZONES)) out.push({ path: `${path}/school-zones.json`, file: `${dir}school-zones.json`, html: fs.readFileSync(ZONES), sitemap: false });
  if (fs.existsSync(CROSSINGS)) out.push({ path: `${path}/crossings.json`, file: `${dir}crossings.json`, html: fs.readFileSync(CROSSINGS), sitemap: false });
  if (fs.existsSync(INJURIES)) out.push({ path: `${path}/injuries.json`, file: `${dir}injuries.json`, html: fs.readFileSync(INJURIES), sitemap: false });
  if (fs.existsSync(OVERLAYS)) out.push({ path: `${path}/overlays.json`, file: `${dir}overlays.json`, html: fs.readFileSync(OVERLAYS), sitemap: false });
  // Your Trip's network and address list, loaded only when a reader scrolls to it.
  if (fs.existsSync(TRIP_GRAPH)) out.push({ path: `${path}/trip-graph.json`, file: `${dir}trip-graph.json`, html: fs.readFileSync(TRIP_GRAPH), sitemap: false });
  if (fs.existsSync(ADDRESSES)) out.push({ path: `${path}/addresses.json`, file: `${dir}addresses.json`, html: fs.readFileSync(ADDRESSES), sitemap: false });
  return out;
}

export function render() {
  if (!has) throw new Error("school trips: site/data/school-sim/index.json missing; run tools/school-trips/school-sim.py");
  const city = IDX.city.levers || {};
  const car = city.today ? city.today.car : null;
  return page({
    title: "School Trips",
    description: car == null ? "How San Francisco students get to school, and what each change would do." : `About ${Math.round(car)}% of San Francisco's public school students come to school by single-family car. See what each change would do, at one school and citywide.`,
    path,
    // The three views are the breadcrumb's last step (layout.mjs) and the page's children in the lists (listing).
    views: { items: listing.views, current: "goals" },
    about: { href: MODEL_PATH, label: "About School Trips" },
    body: CSS + COMMENT_CSS + WEDGE_CSS + body(IDX),
  });
}
