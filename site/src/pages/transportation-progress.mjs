// The redirect from /transportation/progress, which carried the plan's
// trajectory chart until 2026-09-22. Links to the old address exist, so this
// module still renders a file there: a page that sends the reader on.
//
// It also reads site/data/bike-progress.json (tools/bike-network/bike-progress.py, from
// SFMTA's own bikeway layer) for the pages that quote it: the whole file as
// `data`, the layer's source and query date as `LAYER`, and a month label.
import { redirectPage } from "../redirect.mjs";

import fs from "node:fs";
import path from "node:path";

const DATA = path.join(import.meta.dirname, "..", "..", "data");
const d = JSON.parse(fs.readFileSync(path.join(DATA, "bike-progress.json"), "utf8"));

/** The whole of bike-progress.json, for the page that does the arithmetic. */
export const data = d;

export const path_ = "/transportation/progress";
export { path_ as path };
export const file = "transportation/progress/index.html";

/** Where the old address now points. The build keeps a redirect page out of the sitemap. */
export const redirect = "/transportation/bike";

const MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-02" as "Feb 2026". */
export const label = (ym) => `${MONTH[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;

/** The layer's source and query date, for a page that shows the chart. */
export const LAYER = d.layer;

/** The redirect page served at the old address. */
export const render = () => redirectPage(redirect, "Improving The Bike Network");
