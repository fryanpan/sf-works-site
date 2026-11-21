// The redirect from /transportation/future, the plan's progress page until
// 2026-09-23, when its items moved onto the overview (Bryan: move the "future"
// items onto the "Overview" page). Links to the old address exist, so this
// module still renders a file there that sends the reader on.
//
// SOURCES stays here because About the Data lists what that page drew on.
import { redirectPage } from "../redirect.mjs";

import fs from "node:fs";
import path from "node:path";
import { METRE, PLAN_URL } from "../transportation.mjs";
import { history } from "../bike-history.mjs";
import { data as d, LAYER } from "./transportation-progress.mjs";

const DATA = path.join(import.meta.dirname, "..", "..", "data");
const lever = JSON.parse(fs.readFileSync(path.join(DATA, "repave-lever.json"), "utf8"));

export const path_ = "/transportation/future";
export { path_ as path };
export const file = "transportation/future/index.html";

// What this page drew on, exported so About the Data can list it too.
export const SOURCES = [
  { label: "SFMTA bikeway network, SFMTA's own ArcGIS copy (Bicycle/bicycle, layer 0) — the install and upgrade month of each segment, and what is on every street segment of the plan today", href: LAYER.service, group: "The bike network", read: LAYER.queried },
  { label: "Biking and Rolling Plan (March 2025), North Star map and Appendix L — the network, and which corridors are New or Upgrade", href: PLAN_URL, group: "The Biking and Rolling Plan", read: "2026-09-05" },
  { label: "Street centerlines (3psu-pn9h), oneway flag — direction rows for street segments of the plan outside the bikeway layer", href: "https://data.sfgov.org/d/3psu-pn9h", group: "Street work and repaving", read: d.plan.directions.centerlines.queried },
  { label: `MTA Bike Network Linear Features (ygmz-vaxd), archived copies captured ${lever.sources.snapshots.captures.join(", ")} — the plan network's five-year rate`, href: "https://data.sf.gov/d/ygmz-vaxd", group: "The bike network", read: lever.sources.snapshots.tag.match(/read (\d{4}-\d{2}-\d{2})/)[1] },
  { label: "Pavement condition history (78va-8dhi) — every resurfacing since 1947, for the lever and the repaving cycle", href: "https://data.sfgov.org/d/78va-8dhi", group: "Street work and repaving", read: lever.sources.pci.queried },
  { label: "Street centerlines (3psu-pn9h) — the street segment counts the cycle divides by", href: "https://data.sfgov.org/d/3psu-pn9h", group: "Street work and repaving", read: lever.sources.centerlines.queried },
  { label: "SFMTA project layer, live from its ArcGIS service, matched to street segments — which project's published geometry covers each built segment", href: "https://www.sfmta.com/projects", group: "Projects and city records", read: d.generated },
  { label: "The overview's all-ages series — the eleven-year rate", href: "/transportation", group: "The bike network", read: history.sources.network.queried },
];

/** Where the old page now points. The build keeps a redirect page out of the sitemap. */
export const redirect = "/transportation/bike";

export const render = () => redirectPage(redirect, "Improving The Bike Network");
