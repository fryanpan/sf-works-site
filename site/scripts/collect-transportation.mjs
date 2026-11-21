#!/usr/bin/env node
// Build data/transportation.json: which streets San Francisco repaved after adopting the
// Biking and Rolling Plan, and which of those carry what the plan calls for.
//
//   node scripts/collect-transportation.mjs
//
// Reaches the network, so it is a separate step from the build. The build reads
// only the JSON this writes, which is committed, so a deploy is reproducible and
// the page can state exactly when each figure was read.
//
// Three inputs:
//   5wbp-dwzt  Utility Excavation Moratorium Streets. Public Works bars excavation
//              for five years after a street is repaved, so this is the public
//              record of what was repaved and when, keyed by centerline id (CNN).
//   ygmz-vaxd  MTA Bike Network Linear Features — what is on the ground today.
//              SFMTA's own DataSF metadata states a quarterly change frequency,
//              so how far past that it has run is a fact about the layer and is
//              computed here rather than asserted.
//   hkz3-itiu  Slow Streets. The plan's facility typology defines its Shared
//              classes AS the Slow Streets family: Level I is "Slow Streets that
//              meet low motor vehicle speed + volume thresholds", and Level III
//              is "Neighborways" and "Bicycle boulevards" -- "Slow Streets with
//              somewhat higher motor vehicle speed + volume thresholds and lower
//              infrastructure investment" (March 2025, pp. 74-75). So this is the
//              city's own record of which streets carry the thing Shared asks for.
//   abhw-ffzx  Mid-Block Traffic Calming Areas, and
//   bp3t-bd4t  Intersection-Level Traffic Calming Devices. Calming that exists
//              without a Slow Streets designation.
//   btxj-k9uh  Public Works Internal & External Projects, the city's interagency
//              project coordination feed (DotMaps). Carries CNN, the owning
//              agency, a facility type and a free-text scope per project, which
//              is the only public record of WHAT a job on a street actually did.
//   data/north-star/traced.geojson — the plan's own network. SFMTA publishes it
//              as GIS nowhere, so this was reconstructed by georeferencing the
//              North Star map PDF onto city centerlines. 6.2 m median registration
//              error, 15.6 m at the 90th percentile; every count inherits it.

import fs from "node:fs";
import path from "node:path";
import { validThrough } from "./lib/coverage.mjs";
import { fetchAllCached } from "./lib/socrata.mjs";
import { buildGrid, buildUpcoming, parseCnns, NOTICE_DAYS, SCOPE_SILENT, SCOPE_BIKE, SCOPE_UNIT } from "./lib/upcoming.mjs";

const ROOT = path.resolve(import.meta.dirname, "..");
const ADOPTED = "2025-03-04"; // SFMTA Board resolution adopting the plan

// The plan's Separated class means a bikeway usable by all ages and abilities.
// Caltrans Class IV is the separated on-street form and Class I is a path.
// Class II is a painted lane and Class III a sharrow; neither separates anyone
// from traffic, so neither satisfies a Separated call.
const SEPARATED = new Set(["CLASS IV", "CLASS I"]);

// The plan's Shared classes are a standard about the STREET, not about a bike
// facility. Its own map legend (Biking and Rolling Plan, March 2025, pp. 68-69)
// defines them as "Fully calmed, shared streets with limited, slow-moving car
// traffic sharing space with cyclists and other users", and the lighter-shaded
// Level 3 class as streets where "some traffic calming may happen, but it is not
// likely that any future facility on this street will be above a Shared Street
// Level III (traffic calmed) due to street space and geography".
//
// A sharrow is paint on an uncalmed street. It is not traffic calming, so it
// cannot by itself satisfy either class, and a segment whose only bikeway is a
// sharrow is counted short of a Shared call.
//
// What this does NOT do is claim the converse. A painted lane does not satisfy
// "fully calmed" either — the plan's test is car speed and volume, which no
// bikeway dataset measures. So on Shared corridors this counts only the case the
// data can settle, and the page says the rest is unmeasurable from here.
const CALMED_CLASSES = new Set(["Shared", "Shared L3"]);

// Undecided is not scored, because there is nothing to score it against. It
// appears in the plan's legend with no definition anywhere in the document, and
// Appendix L uses it as a facility value while declining to say what facility.
// So these segments get status "unrated" and sit outside every count on the
// page: calling a street short of a facility the plan never named is the one
// criticism of this tool that would stick.
//
// Bryan decided this on 2026-09-20, choosing "Drop the 15" over leaving them in
// or relabelling them. The plan's own Upgrade and New flags travel with them, so
// their own section can say the plan commits to changing most of these streets
// without saying to what.
const UNDECIDED = "Undecided";
const UNRATED = "unrated";

const PLAIN_CLASS = {
  "CLASS I": "path",
  "CLASS II": "painted lane",
  "CLASS III": "sharrow",
  "CLASS IV": "separated lane",
};

// CNN is written with and without leading zeros across these datasets, so every
// join goes through one normaliser rather than hoping they agree.
const cnnKey = (v) => String(v ?? "").replace(/^0+/, "");
const push = (map, key, value) => {
  const cur = map.get(key);
  if (cur) cur.push(value);
  else map.set(key, [value]);
};

// Pages the whole dataset and raises on a short read. A fixed $limit here was
// one row-count away from silently truncating: the eviction table stands at
// 48,987 against the 50,000 this used to ask for, and the plan-review table had
// already passed its own cap and was dropping 54,438 rows unnoticed.
// Each dataset is re-read only when DataSF says its rows changed (the cache is
// the gitignored .cache/site-socrata/). `readOn` is the newest date any of the
// five was actually re-read with different rows: the page's "read" date and
// the day its countdowns run from, so a run with no new data writes the same
// file.
const CACHE = path.join(ROOT, "..", ".cache", "site-socrata");
const readDates = [];
const fetchDataset = async (id) => {
  const r = await fetchAllCached(id, { cacheDir: CACHE });
  readDates.push(r.fetchedOn);
  console.log(`  ${id}: ${r.rows.length} rows, ${r.fromCache ? "unchanged since" : "read"} ${r.fetchedOn}`);
  return r.rows;
};

const moratorium = await fetchDataset("5wbp-dwzt");
const projects = await fetchDataset("btxj-k9uh");
const slowStreets = await fetchDataset("hkz3-itiu");
const midBlockCalming = await fetchDataset("abhw-ffzx");
const intersectionCalming = await fetchDataset("bp3t-bd4t");
// SFMTA's own ArcGIS copy of the bikeway layer, the one the overview reads
// (tools/bike-network/bike-network-history.py fetches it to data/extract/sfmta-bikeway/).
// Its DataSF publication, ygmz-vaxd, lags it: refreshed 2026-04-17 against
// edits to 2026-05-21 in SFMTA's copy, read 2026-09-22. Bryan, 2026-09-28:
// "we don't have the extended bikeway dataset from merging together bikeway
// layer with project pages from SFMTA?" Rows are mapped to the DataSF field
// names the rest of this collector uses; the copy's last edit stands in for
// DataSF's data_as_of.
const layerCopy = JSON.parse(
  fs.readFileSync(path.join(ROOT, "..", "data/extract/sfmta-bikeway/network.json"), "utf8"),
);
const layerEdited = new Date(
  Math.max(...layerCopy.records.map((r) => r.LAST_EDITED_DATE || 0)),
).toISOString();
const bikeway = layerCopy.records.map((r) => ({
  cnn: r.CNN ? String(Math.round(r.CNN)) : null,
  facility_t: r.FACILITY_T,
  install_yr: r.INSTALL_YR ? String(r.INSTALL_YR) : null,
  data_as_of: layerEdited,
}));
const trace = JSON.parse(
  fs.readFileSync(path.join(ROOT, "data/north-star/traced.geojson"), "utf8"),
);
const georef = JSON.parse(
  fs.readFileSync(path.join(ROOT, "data/north-star/georeference.json"), "utf8"),
);
// The Appendix L index of the same network. Its geometry joins the trace's in
// the point grid below, which is the only thing it is used for: 61 projects
// publish no centerline id at all and can be placed only by where they are.
const planIndex = JSON.parse(
  fs.readFileSync(path.join(ROOT, "data/north-star/segments.geojson"), "utf8"),
);
// Each plan block's miles per direction of travel, times the share of it the
// plan's line covers, from scripts/bike-progress.py. The departments page's
// Active and Future bars count in this unit (tools/projects/department-overlap.py),
// and so must the Past bars drawn from `lengthM` below, or a block grows when
// it moves between bars. The lever counts the same metres (lib/mile_basis.py).
const blockMetres = new Map(
  JSON.parse(fs.readFileSync(path.join(ROOT, "data/north-star/status.json"), "utf8"))
    .blocks.map((b) => [String(b.cnn), b.m]),
);

// Which plan blocks were repaved since adoption, and when, is the record the
// page's bars use: tools/bike-network/repave-lever.py's blocks, dated by the pavement
// condition score resetting to 100 (DataSF 78va-8dhi), with each block's miles
// counted per direction of travel as the plan counts them (Bryan, 2026-09-28:
// "Use the biking & rolling plan's way of counting miles"). The moratorium
// list, which this read before, missed the Valencia Street repave that carried
// most of the miles the bars say got the bikeway, so the map and the bars
// disagreed. The moratorium still supplies each block's limits and job order.
// `grade` is the lever's verdict: already met before the repave, received the
// bikeway with it, or short; undated repaves are left out, as the bars do.
const lever = JSON.parse(fs.readFileSync(path.join(ROOT, "data/repave-lever.json"), "utf8"));
const repavedOn = new Map();
const leverBlock = new Map();
for (const b of lever.sinceAdoption.blocks) {
  if (b.grade === "undated") continue;
  repavedOn.set(String(b.cnn), b.date);
  leverBlock.set(String(b.cnn), b);
}

const limits = new Map();
for (const r of moratorium) {
  if (r.cnn && r.limits && !limits.has(String(r.cnn))) {
    limits.set(String(r.cnn), r.limits);
  }
}

const plan = new Map();
for (const f of trace.features) plan.set(String(f.properties.cnn), f.properties);

// Appendix L flags each corridor New or Upgrade. The trace does not carry them,
// so they come off the index the trace was built from, spread to every CNN of
// the corridor they belong to.
const planFlags = new Map();
for (const f of planIndex.features) {
  const pr = f.properties;
  for (const c of pr.cnns ?? []) {
    planFlags.set(String(c), { isNew: pr.new === "Y", isUpgrade: pr.upgrade === "Y" });
  }
}

const built = new Map();
for (const r of bikeway) {
  if (!r.cnn) continue;
  const cnn = String(r.cnn);
  if (!built.has(cnn)) built.set(cnn, []);
  built.get(cnn).push(r);
}

// Work SFMTA's project pages call built this year, which the layer has not
// caught up with (tools/bike-network/bike-reported-work.py). Without it a block repaved
// and given its bikeway in 2026, such as Winston Drive, grades as short.
const reportedPath = path.join(ROOT, "data/bike-history/reported.json");
const reported = fs.existsSync(reportedPath)
  ? JSON.parse(fs.readFileSync(reportedPath, "utf8"))
  : { projects: [] };
const reportedCnns = new Set();
for (const p of reported.projects) {
  for (const b of p.blocks) {
    const cnn = String(b.cnn);
    reportedCnns.add(cnn);
    if (!built.has(cnn)) built.set(cnn, []);
    built.get(cnn).push({ facility_t: p.class, install_yr: String(p.year), project: p.name });
  }
}

const segments = [];
for (const [cnn, repaved] of repavedOn) {
  const p = plan.get(cnn);
  if (!p) continue;
  const rows = built.get(cnn) ?? [];
  const classes = [...new Set(rows.map((r) => r.facility_t).filter(Boolean))];
  const years = [
    ...new Set(rows.map((r) => Number(r.install_yr)).filter((y) => y > 1900)),
  ];

  const onlySharrow = classes.length > 0 && classes.every((c) => c === "CLASS III");

  const status =
    p.facility === UNDECIDED
      ? UNRATED
      : rows.length === 0
        ? "none"
        : p.facility === "Separated" && !classes.some((c) => SEPARATED.has(c))
          ? "short"
          : CALMED_CLASSES.has(p.facility) && onlySharrow
            ? "short"
            : "meets";

  const flags = planFlags.get(cnn) ?? { isNew: false, isUpgrade: false };

  segments.push({
    cnn,
    street: p.street,
    limits: limits.get(cnn) ?? null,
    repaved,
    wants: p.facility,
    has: classes.map((c) => PLAIN_CLASS[c] ?? c.toLowerCase()),
    installedYears: years.sort(),
    reportedBy: rows.find((r) => r.project)?.project ?? null,
    overlapShare: p.share,
    // Per direction of travel times the plan's share of the block, as the other stages count.
    lengthM: blockMetres.get(cnn) ?? Math.round(leverBlock.get(cnn).miles * 1609.344),
    status,
    grade: leverBlock.get(cnn).grade,
    planNew: flags.isNew,
    planUpgrade: flags.isUpgrade,
  });
}

segments.sort(
  (a, b) => a.street.localeCompare(b.street) || a.repaved.localeCompare(b.repaved),
);

// Everything the page counts is computed over `scored`. The 15 Undecided
// segments stay in `segments` so the map and the project list can draw them and
// say what is on the ground, and they are reported on their own below.
const scored = segments.filter((s) => s.status !== UNRATED);
const unrated = segments.filter((s) => s.status === UNRATED);

const count = (s) => scored.filter((x) => x.status === s).length;
const metres = (rows) => rows.reduce((t, r) => t + r.lengthM, 0);
const separatedGap = scored.filter(
  (s) => s.wants === "Separated" && s.status !== "meets",
);

// The bikeway layer's own statement of when it was last refreshed. A figure from
// a stale layer reads as current, so the page says this out loud.
const out_layerAsOf_raw = bikeway
  .map((r) => r.data_as_of)
  .filter(Boolean)
  .sort()
  .at(-1);
const out_layerAsOf = out_layerAsOf_raw ? out_layerAsOf_raw.slice(0, 10) : null;

// A segment repaved BEFORE the bikeway layer was last refreshed is fully
// checkable: had a bikeway gone in with the repaving, the layer would carry its
// geometry. For those, an absent bikeway is evidence of absence rather than a
// gap in what we can see. A segment repaved after that date is not checkable
// here at all, so the page reports the two separately instead of letting the
// caveat hang over every figure.
//
// The buffers exist because a layer refresh does not guarantee construction that
// week is already recorded in it. If the shortfall held only at a zero buffer it
// would be an artifact of the cutoff; it does not, so the page can name one
// figure and the collector prints the rest.
const checkable = scored.filter((s) => s.repaved <= out_layerAsOf);
const unverifiable = scored.filter((s) => s.repaved > out_layerAsOf);
const short = (rows) => rows.filter((r) => r.status !== "meets");
const buffered = [0, 30, 90, 180].map((days) => {
  const cut = new Date(
    new Date(out_layerAsOf + "T00:00:00Z") - days * 86400000,
  )
    .toISOString()
    .slice(0, 10);
  const rows = scored.filter((s) => s.repaved <= cut);
  return { bufferDays: days, cutoff: cut, n: rows.length, shortfall: short(rows).length };
});

// ---- what the repaving project itself says it did ------------------------
//
// The moratorium record says a street was repaved and when. It does not say what
// the job included. The coordination feed does, so the two are joined on the
// centerline id and, where that fails, on the job order number — the moratorium
// carries `jobordernum` and the feed carries `peoplesoft_id`, which share an id
// space for about half these segments.
//
// Whether a project counts as bike work is decided by the feed's own
// `facility_type` and owning agency first. The keyword fallback over the project
// name and description is MINE, not the city's, and it is deliberately broad: it
// can only move a segment from "no bike component" to "included bike work", so a
// false positive weakens the finding rather than inflating it.
// The agencies whose work opens a street rather than resurfacing it: SFPUC's
// own units, and the sewer division Public Works runs for it. PG&E is a utility
// too and is left out here on purpose — it is not a city body, and the page's
// question is which city agency an advocate writes to.
const isUtility = (agency) => /^SF PUC\b/.test(agency ?? "") || agency === "SF DPW IDC - Hydraulic";
const BIKE_WORDS = /\bbike|bicycl|bikeway|cycle track|protected lane/i;
const isBikeProject = (r) =>
  (r.facility_type ?? "").toLowerCase().includes("bikeway") ||
  (r.agency_name ?? "").toLowerCase().includes("livable streets") ||
  BIKE_WORDS.test(`${r.name ?? ""} ${r.description ?? ""}`);

const baseId = (v) => String(v ?? "").split("-")[0];
const projectsByCnn = new Map();
const projectsByJobOrder = new Map();
for (const r of projects) {
  // `cnn` carries a Python-style list on 908 of these 7,853 rows, spanning 158
  // of the 389 projects. Reading it as a single id leaves those rows matching
  // nothing, and an unmatched row counts as a street with no documented scope —
  // so the error runs in the direction that inflates this page's own finding.
  for (const cnn of parseCnns(r.cnn)) push(projectsByCnn, cnn, r);
  if (r.peoplesoft_id) push(projectsByJobOrder, baseId(r.peoplesoft_id), r);
}
const jobOrdersByCnn = new Map();
for (const r of moratorium) {
  if (r.cnn && r.jobordernum) push(jobOrdersByCnn, cnnKey(r.cnn), baseId(r.jobordernum));
}

for (const s of segments) {
  const key = cnnKey(s.cnn);
  const rows = [
    ...(projectsByCnn.get(key) ?? []),
    ...(jobOrdersByCnn.get(key) ?? []).flatMap((jo) => projectsByJobOrder.get(jo) ?? []),
  ];
  s.scope = rows.some(isBikeProject)
    ? "bike"
    : rows.length
      ? "documented-no-bike"
      : "unknown";  // Who opened the street. A repaving job is Public Works' own, but the row
  // that put it on the coordination feed is often a water main or a sewer, and
  // that is the agency whose schedule an advocate has to read.
  s.agencies = [...new Set(rows.map((r) => r.agency_name).filter(Boolean))].sort();
}

const scope = (v) => scored.filter((s) => s.scope === v);
const shortOf = (rows) => rows.filter((r) => r.status !== "meets").length;

// Citywide context: the feed does record bike projects. The question is whether
// any of them land on a street the city repaved.
const bikeProjectCnns = new Set(
  projects.filter(isBikeProject).flatMap((r) => parseCnns(r.cnn)),
);
const repavedKeys = new Set([...repavedOn.keys()].map(cnnKey));
const planKeys = new Set([...plan.keys()].map(cnnKey));

// SFMTA's stated cadence for the bikeway layer, quoted from its DataSF metadata
// ("Data change frequency: Quarterly", publisher SFMTA, inventory ID MTA-0024,
// read 2026-09-19). Keeping it as a number makes "how late" arithmetic the page
// recomputes rather than a sentence that goes stale the day after it is written.
// How late the layer is depends on the day the page is built, not on the data,
// so the page computes days since refresh from bikewayLayerAsOf when it renders.
// Writing it here put the wall clock in a tracked file, and every day's run
// changed it with no new data (Architecture rule 3).
const LAYER_CADENCE_DAYS = 90;
const layerHealth = {
  statedFrequency: "Quarterly",
  cadenceDays: LAYER_CADENCE_DAYS,
};

// How much the missing GIS actually costs. The plan's network is traced from a
// map, with 6.2 m median and 15.6 m p90 registration error, so a fair question is
// whether the shortfall is an artifact of segments the trace only partly covers.
// Recomputing at rising overlap thresholds answers it: if the rate held only at
// the loosest threshold it would be an artifact, and it does not.
const overlapSensitivity = [0, 0.6, 0.7, 0.8, 0.9, 1].map((min) => {
  const rows = scored.filter((s) => s.overlapShare >= min);
  const short = rows.filter((r) => r.status !== "meets").length;
  return {
    minOverlap: min,
    segments: rows.length,
    shortfall: short,
    shortfallPct: rows.length ? Number(((100 * short) / rows.length).toFixed(0)) : 0,
  };
});

// The breakdown, grouped the way the plan groups it: one block per facility
// class, and within each the states the data can distinguish. A single "does not
// meet" row hides that the Separated and Shared tests are different questions.
const CLASS_ORDER = ["Separated", "Shared", "Shared L3"];
const STATE_LABEL = {
  Separated: {
    none: "Nothing",
    short: "Paint or sharrow only",
    meets: "Separated lane or path",
  },
  Shared: {
    none: "Nothing",
    short: "Sharrow only",
    meets: "Painted lane or better",
  },
  "Shared L3": {
    none: "Nothing",
    short: "Sharrow only",
    meets: "Painted lane or better",
  },
};

const byClass = CLASS_ORDER.filter((c) => scored.some((s) => s.wants === c)).map(
  (facility) => {
    const rows = scored.filter((s) => s.wants === facility);
    return {
      facility,
      segments: rows.length,
      metres: metres(rows),
      shortfall: rows.filter((r) => r.status !== "meets").length,
      states: ["none", "short", "meets"]
        .map((state) => {
          const cells = rows.filter((r) => r.status === state);
          return {
            state,
            label: STATE_LABEL[facility][state],
            segments: cells.length,
            metres: metres(cells),
            meets: state === "meets",
          };
        })
        .filter((c) => c.segments > 0),
    };
  },
);

// ---- is the street actually calmed? --------------------------------------
//
// The Shared test is car speed and volume, which no bikeway layer measures. The
// city does publish what it has BUILT toward those thresholds, so this reports
// designation and devices — the closest public proxy — rather than recoding the
// shortfall on it. A Slow Street is strong evidence the street is calmed. Its
// ABSENCE is weaker evidence, and weaker still because the Slow Streets file has
// not been refreshed since 2023 while the calming files run to 2026.
const slowStreetCnns = new Set(
  slowStreets.filter((r) => r.cnn && r.status === "Implemented").map((r) => cnnKey(r.cnn)),
);
const calmedCnns = new Set([
  ...midBlockCalming
    .filter((r) => r.cnn && ["Complete", "Existing"].includes(r.current_status))
    .map((r) => cnnKey(r.cnn)),
  ...intersectionCalming
    .filter((r) => r.cnn && r.current_status === "Complete")
    .map((r) => cnnKey(r.cnn)),
]);

const sharedSegments = scored.filter((s) => CALMED_CLASSES.has(s.wants));
const onSlowStreet = sharedSegments.filter((s) => slowStreetCnns.has(cnnKey(s.cnn)));
const calmedOnly = sharedSegments.filter(
  (s) => !slowStreetCnns.has(cnnKey(s.cnn)) && calmedCnns.has(cnnKey(s.cnn)),
);
const calming = {
  sharedSegments: sharedSegments.length,
  onSlowStreet: onSlowStreet.length,
  calmingOnly: calmedOnly.length,
  neither: sharedSegments.length - onSlowStreet.length - calmedOnly.length,
  slowStreetsAsOf: slowStreets
    .map((r) => r.data_as_of)
    .filter(Boolean)
    .sort()
    .at(-1)
    ?.slice(0, 10),
  calmingAsOf: midBlockCalming
    .map((r) => r.data_as_of)
    .filter(Boolean)
    .sort()
    .at(-1)
    ?.slice(0, 10),
};

// How far forward this page reaches. Not today: the finding compares what was
// repaved against what bikeway exists, and the bikeway layer is the half that
// stopped. Anything built after its last refresh is invisible to the join, so
// that refresh date — not the query date — is the page's limit.
const valid = validThrough([
  {
    label: "Bikeway network layer",
    through: out_layerAsOf,
    why:
      `SFMTA's bikeway layer was last edited on this date; work SFMTA's project ` +
      `pages call finished since then is added from those pages. A bikeway built ` +
      `since then that no project page reports does not appear.`,
  },
  {
    label: "Slow Streets",
    through: slowStreets
      ? (slowStreets
          .map((r) => String(r.data_as_of ?? "").slice(0, 10))
          .filter(Boolean)
          .sort()
          .at(-1) ?? null)
      : null,
    binding: false,
    why: "Used only as a ceiling on how many segments are calmed.",
  },
]);


// --- What is still coming -----------------------------------------------
//
// The half of this page a reader can act on. Everything above is work already
// done; this is work that has not started, on streets the plan says should
// carry biking, where nothing published says the bike work is in scope.
const today = readDates.slice().sort().at(-1);
const { grid, vertexCount } = buildGrid([trace, planIndex]);
const { projects: upcomingProjects, rowsWithoutId } = buildUpcoming({
  projects,
  plan,
  grid,
  moratorium,
  bikeway,
  today,
});

const ask = upcomingProjects.filter((p) => p.ask);
const soon = ask.filter((p) => p.inNoticeWindow);

// Guards on the join rather than on the answer. Each one names a way this has
// silently produced a wrong page before: a truncated fetch, the list-shaped
// `cnn` field read as one id, or a geometry index that loaded empty. They are
// floors well under what was observed on 2026-09-19 (389 projects, 2,870 plan
// segments, 15,498 grid vertices, 908 list-shaped rows), so live data can move
// without tripping them.
const listShapedRows = projects.filter((r) =>
  String(r.cnn ?? "").trim().startsWith("["),
).length;
const assert = (cond, msg) => {
  if (!cond) throw new Error(`collect-transportation: ${msg}`);
};
assert(upcomingProjects.length > 300, `only ${upcomingProjects.length} projects`);
assert(plan.size > 2500, `plan network has only ${plan.size} segments`);
assert(vertexCount > 12000, `plan geometry index has only ${vertexCount} vertices`);
assert(listShapedRows > 500, `only ${listShapedRows} list-shaped cnn rows — field shape changed`);
assert(
  upcomingProjects.some((p) => p.planMatch === "geometry"),
  "no project matched by geometry — the no-CNN fallback is not running",
);
assert(rowsWithoutId === 0, `${rowsWithoutId} project rows carry no project id`);

const phaseCounts = {};
for (const p of soon) phaseCounts[p.phase || "unrecorded"] = (phaseCounts[p.phase || "unrecorded"] ?? 0) + 1;

const durations = upcomingProjects
  .filter((p) => p.start && p.end && p.end > p.start)
  .map((p) => (Date.parse(p.end) - Date.parse(p.start)) / 86400000)
  .sort((a, b) => a - b);

const upcoming = {
  today,
  noticeDays: NOTICE_DAYS,
  totalProjects: upcomingProjects.length,
  projectRows: projects.length,
  onPlan: upcomingProjects.filter((p) => p.segmentsOnPlan > 0).length,
  // `ask` is the length of the list the page actually shows. It is NOT
  // `totalProjects`, and the page said it was: the mode link read "Still
  // coming (389)" over a table of 155 rows, because 389 is every project in
  // the coordination window whether or not it touches the plan's network.
  // The three numbers narrow: 389 projects in the window, 212 on the plan's
  // network, 155 of those still changeable with nothing published about bike
  // work. Only the last is a list of things worth reviewing.
  ask: ask.length,
  // On the plan's network but NOT on the list, and why — so the drop from 212
  // to 155 is legible rather than looking like rows going missing.
  onPlanNotChangeable: upcomingProjects.filter(
    (p) => p.segmentsOnPlan > 0 && p.scope === SCOPE_SILENT && !p.changeable,
  ).length,
  onPlanScopeNamed: upcomingProjects.filter(
    (p) => p.segmentsOnPlan > 0 && p.scope !== SCOPE_SILENT,
  ).length,
  soon: soon.length,
  later: ask.length - soon.length,
  soonPhases: phaseCounts,
  // How much warning a project in Design actually gives: the start date is when
  // the PROJECT starts, not when the street is opened, and the median project
  // runs well over a year. That is the good news on this page and it has to be
  // said before the dates are read.
  medianRunDays: durations.length
    ? Math.round(durations[Math.floor(durations.length / 2)])
    : null,
  // What the published record says, for the projects on the network. The point
  // is the size of the silent bucket.
  scopeCounts: (() => {
    const c = {};
    for (const p of upcomingProjects.filter((x) => x.segmentsOnPlan > 0)) {
      c[p.scope] = (c[p.scope] ?? 0) + 1;
    }
    return c;
  })(),
  silentLabel: SCOPE_SILENT,
  noCnnProjects: upcomingProjects.filter((p) => p.segments === 0).length,
  matchedByGeometry: upcomingProjects.filter((p) => p.planMatch === "geometry").length,
  listShapedRows,
  // Who is about to open the plan's streets, by agency. The utility rows —
  // SFPUC water and power, and the sewer work Public Works runs as "IDC -
  // Hydraulic" — are the openings the repaving obligation hangs off, and the
  // ones no bike scope has ever been published for. Blocks are counted once
  // each across an agency's projects, and once each in the utility total, so a
  // block two projects share is not two blocks.
  byAgency: (() => {
    const onPlan = upcomingProjects.filter((p) => p.segmentsOnPlan > 0);
    const acc = {};
    for (const p of onPlan) {
      const a = (acc[p.agency || "unrecorded"] ??= { projects: 0, blocks: new Set(), silentBlocks: new Set() });
      a.projects += 1;
      for (const c of p.onPlanCnns) {
        a.blocks.add(c);
        if (p.scope !== SCOPE_BIKE && p.scope !== SCOPE_UNIT) a.silentBlocks.add(c);
      }
    }
    return Object.entries(acc)
      .map(([agency, a]) => ({
        agency,
        utility: isUtility(agency),
        projects: a.projects,
        blocks: a.blocks.size,
        silentBlocks: a.silentBlocks.size,
      }))
      .sort((x, y) => y.blocks - x.blocks || x.agency.localeCompare(y.agency));
  })(),
  utility: (() => {
    const rows = upcomingProjects.filter((p) => p.segmentsOnPlan > 0 && isUtility(p.agency));
    const blocks = new Set(), silent = new Set();
    for (const p of rows) for (const c of p.onPlanCnns) {
      blocks.add(c);
      if (p.scope !== SCOPE_BIKE && p.scope !== SCOPE_UNIT) silent.add(c);
    }
    return { projects: rows.length, blocks: blocks.size, silentBlocks: silent.size };
  })(),
  // Every project on the plan's network, not only the ones worth asking about.
  // Publishing `ask` alone meant a project that DOES name bike work could not
  // be looked at — so the page could show the gap and never the opposite, which
  // is the reading Bryan asked for: did the plan's network generally get its
  // bikeway or not. The list views filter on `ask` themselves.
  projects: upcomingProjects.filter((p) => p.segmentsOnPlan > 0),
};

const out = {
  // Every lengthM below, as status.json and the lever count it.
  mileBasis: lever.mileBasis,
  adopted: ADOPTED,
  queriedAt: today,
  validThrough: valid,
  bikewayLayerAsOf: out_layerAsOf,
  bikewayLayer: layerHealth,
  repavedSinceAdoption: repavedOn.size,
  planSegments: plan.size,
  registration: {
    medianMetres: georef.report.median_resid_m,
    p90Metres: georef.report.p90_resid_m,
    // Which blocks are the plan's (tools/bike-network/north-star-map-trace.py): the map's
    // line within toleranceMetres, or within namedToleranceMetres of a block
    // Appendix L names; namedBlocks - namedOnMap named blocks the map does not draw.
    toleranceMetres: georef.tolerance_m,
    namedToleranceMetres: georef.named_tolerance_m,
    namedBlocks: georef.named_blocks,
    namedOnMap: georef.named_on_map,
  },
  totals: {
    onPlan: scored.length,
    none: count("none"),
    short: count("short"),
    meets: count("meets"),
    shortfall: count("none") + count("short"),
    shortfallMetres: metres(scored.filter((s) => s.status !== "meets")),
    // Split so a reader can see which part of the shortfall rests on the plan's
    // quoted Shared definition and which on its Separated classes.
    shortfallOnSeparated: scored.filter(
      (s) => s.wants === "Separated" && s.status !== "meets",
    ).length,
    shortfallOnCalmed: scored.filter(
      (s) => CALMED_CLASSES.has(s.wants) && s.status !== "meets",
    ).length,
    separatedGapSegments: separatedGap.length,
    separatedGapMetres: metres(separatedGap),
    // A low overlap could be registration error at a corridor end rather than a
    // real call for a bikeway. If this is ever above zero the page must say so.
    marginalOverlap: scored.filter(
      (s) => s.status !== "meets" && s.overlapShare < 0.5,
    ).length,
    installedSinceAdoption: scored.filter((s) =>
      s.installedYears.some((y) => y >= 2025),
    ).length,
    // Split at the layer's refresh date. See the comment above `checkable`.
    checkable: checkable.length,
    checkableShortfall: short(checkable).length,
    checkableShortfallMetres: metres(short(checkable)),
    unverifiable: unverifiable.length,
    unverifiableShortfall: short(unverifiable).length,
  },
  // Bryan's framing, 2026-09-19: of the repaving that happened, how many are
  // KNOWN to have included bike work, how many are known not to, and how many we
  // simply cannot tell because no record says.
  scopeOfWork: {
    includedBikeWork: scope("bike").length,
    includedBikeWorkShortfall: shortOf(scope("bike")),
    documentedNoBike: scope("documented-no-bike").length,
    documentedNoBikeShortfall: shortOf(scope("documented-no-bike")),
    unknown: scope("unknown").length,
    unknownShortfall: shortOf(scope("unknown")),
    citywide: {
      segmentsWithBikeProject: bikeProjectCnns.size,
      alsoOnPlan: [...bikeProjectCnns].filter((c) => planKeys.has(c)).length,
      alsoRepavedSinceAdoption: [...bikeProjectCnns].filter((c) => repavedKeys.has(c))
        .length,
    },
  },
  // The segments the plan draws without saying what to build. They are outside
  // every figure above. What is reported here is what is on the ground and what
  // the plan's own Appendix L flags say it intends, which is as far as the
  // document goes.
  undecided: {
    segments: unrated.length,
    metres: metres(unrated),
    withNothing: unrated.filter((s) => s.has.length === 0).length,
    onlySharrow: unrated.filter(
      (s) => s.has.length > 0 && s.has.every((h) => h === "sharrow"),
    ).length,
    paintedOrBetter: unrated.filter((s) =>
      s.has.some((h) => h === "painted lane" || h === "separated lane" || h === "path"),
    ).length,
    flaggedUpgrade: unrated.filter((s) => s.planUpgrade).length,
    flaggedNew: unrated.filter((s) => s.planNew).length,
    streets: [...new Set(unrated.map((s) => s.street))].sort(),
  },
  upcoming,
  shortfallByBuffer: buffered,
  overlapSensitivity,
  byClass,
  calming,
  segments,
};

const dest = path.join(ROOT, "data/transportation.json");
const text = JSON.stringify(out, null, 1);
let prev = null;
try {
  prev = fs.readFileSync(dest, "utf8");
} catch {}
if (prev !== text) fs.writeFileSync(dest, text);
console.log(
  `streets: ${out.totals.onPlan} scored segments, ${out.totals.shortfall} short ` +
    `(${out.totals.none} with nothing, ${out.totals.short} with the wrong class); ` +
    `${out.undecided.segments} Undecided set aside; ` +
    `${upcoming.ask} of ${upcoming.totalProjects} projects worth asking about, ` +
    `${upcoming.soon} inside ${NOTICE_DAYS} days ` +
    `→ ${path.relative(ROOT, dest)}`,
);
