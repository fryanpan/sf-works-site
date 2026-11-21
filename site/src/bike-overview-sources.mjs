// The sources behind the bike network figures, listed on About the Data.
//
// These were the old /transportation/bike overview's sources. Bryan,
// 2026-10-08: the bike post "was meant to be a replacement for the biking
// overview page", so /transportation/bike now renders the post
// (src/pages/post-sf-bike-network.mjs). Its map and charts are built from the
// same data, so About the Data keeps listing all of it.

import { history, projects } from "./bike-history.mjs";
import { PLAN_URL, APPENDIX_G_URL } from "./transportation.mjs";
import { LAYER } from "./pages/transportation-progress.mjs";

const S = history.sources;
const D = history.disagreements.published_vs_centerline;

// What the overview drew on, exported so About the Data can list it too.
const snapshots = S.snapshots.filter((s) => s.kind === "archive");
export const SOURCES = [
  { label: "SFMTA bikeway network, SFMTA's own ArcGIS copy (Bicycle/bicycle, layer 0) — the live layer, its install and update years, and every street segment's line geometry", href: S.network.url, group: "The bike network", read: S.network.queried },
  { label: `MTA Bike Network Linear Features (ygmz-vaxd), ${snapshots.length} archived copies from the Internet Archive captured ${snapshots.map((s) => s.captured).join(", ")} — what the layer said in earlier years`, href: "https://data.sf.gov/d/ygmz-vaxd", group: "The bike network", read: snapshots[0].fetched },
  { label: "Slow Streets (hkz3-itiu) — the implemented Slow Streets and their install dates", href: S.slow_streets.dataset, group: "The bike network", read: S.slow_streets.queried },
  { label: "Census 2020 blocks for San Francisco (p2fw-hsrv) — 2020 population and interior point of every block, and the dots on the map", href: S.population["2020_blocks"].dataset, group: "Who it reaches", read: S.population["2020_blocks"].queried },
  { label: "Census 2010 blocks, TIGERweb — population and interior point, for the years before 2020", href: S.population["2010_blocks"].url, group: "Who it reaches", read: S.population["2010_blocks"].queried },
  { label: "American Community Survey 5-year B01003, total population by block group, 2015 to 2024 — the population of each year", href: "https://data.census.gov/table/ACSDT5Y2024.B01003?g=050XX00US06075$1500000", group: "Who it reaches", read: S.population.acs5_block_groups.queried },
  { label: `California Department of Education public school directory, ${S.schools.source.includes("2025-10-05") ? "2025-10-05 file" : "directory"} via the Internet Archive — each public school's coordinates, opening and closing dates`, href: S.schools.url, group: "Who it reaches", read: S.schools.queried },
  { label: "DataSF Schools (7e7j-59qk) — the private elementary, high and K-12 schools, and a cross-check on the count of active public schools", href: S.schools.private.dataset, group: "Who it reaches", read: S.schools.private.queried },
  { label: "City Facilities (nc68-ngbr) — the library branches and the Main Library", href: S.libraries.dataset, group: "Who it reaches", read: S.libraries.queried },
  { label: "SFMTA project layer, live from its ArcGIS service, matched to street segments — which project's published geometry covers each segment", href: "https://www.sfmta.com/projects", group: "Projects and city records", read: projects.sources.project_geometry.generated },
  { label: "SFMTA bikeway network, SFMTA's own ArcGIS copy — the month of each install and upgrade, for the trajectory chart", href: LAYER.service, group: "The bike network", read: LAYER.queried },
  { label: "Biking and Rolling Plan (March 2025), North Star map and Appendix L — the network the trajectory chart measures against", href: "https://www.sfmta.com/projects/biking-and-rolling-plan", group: "The Biking and Rolling Plan", read: "2026-09-05" },
  { label: `2023 Draft Bike Comfort Index (Toole Design / SFMTA), ArcGIS layer — the score the plan's all-ages test applies to painted lanes and signed routes (threshold ${history.sources.bci.threshold})`, href: history.sources.bci.url, group: "The Biking and Rolling Plan", read: history.sources.bci.queried },
  { label: "Biking and Rolling Plan (March 2025), printed pp. 20 and 24 — the 472-mile network counted per direction, the all-ages test, and the 80% reach figure", href: PLAN_URL, group: "The Biking and Rolling Plan", read: "2026-09-22" },
  { label: "Biking and Rolling Plan, Appendix G, Toole Design connectivity memo of 2024-02-13 — the all-ages test as the plan's consultants applied it", href: APPENDIX_G_URL, group: "The Biking and Rolling Plan", read: "2026-09-22" },
  { label: `SFMTA, "Safety upgrades make a difference" (${D.sfmta_published.date}) — the ${D.sfmta_published.miles}-mile figure the city publishes`, href: D.sfmta_published.source, group: "The bike network", read: S.network.queried },
];
