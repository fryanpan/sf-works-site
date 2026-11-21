// The redirect from /transportation/repaving, which showed what the paving
// done since the plan was adopted delivered until 2026-09-23. Links to the old
// address exist, so this module still renders a file there that sends the
// reader to the bike front page, whose street-work map carries the repaving story.
//
// The departments module still uses this module's words for a tapped
// street (readoutFor) and its shade for a block (shade).

import { block, street } from "../transportation.mjs";
import { redirectPage } from "../redirect.mjs";
import { esc } from "../html.mjs";

export const path = "/transportation/repaving";
export const file = "transportation/repaving/index.html";

// What a tapped street says, in words a resident uses: the street, the
// block, when it was repaved, what the plan draws there and what it has now.
const PLAN_DRAWS = { Separated: "a separated lane", Shared: "a shared street", "Shared L3": "a Level 3 shared street", Undecided: "no bikeway type yet" };
const VERDICT = { met: "It got what the plan draws with the repave.", already: "It had what the plan draws before the repave.", short: "It has less than the plan draws.", none: "", unrated: "" };
export function readoutFor(s) {
  const when = new Date(s.repaved + "T12:00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  const has = s.has.length ? [...new Set(s.has)].join(" and ") : "no bikeway";
  const where = block(s.limits).replace(/&amp;/g, "&").replace(/Unnamed \d+/g, "an unnamed street");
  return `<strong>${esc(street(s.street).replace(/&amp;/g, "&"))}</strong>, ${esc(where)}. ` +
    `Repaved ${when}. The Biking and Rolling Plan calls for ${PLAN_DRAWS[s.wants] || esc(s.wants)}; the street has ${esc(has)}. ${VERDICT[shade(s)] || ""}`;
}

// A block's shade on the map says what the repave did, in the bars' terms
// (tools/bike-network/repave-lever.py): got the plan's bikeway with it, already had it,
// or still falls short, split by whether any bikeway is there.
export const shade = (s) => (s.grade === "received" ? "met" : s.grade === "already" ? "already" : s.status);

/** Where the old page now points. The build keeps a redirect page out of the sitemap. */
export const redirect = "/transportation/bike";
export const render = () => redirectPage(redirect, "Better Coordination Across City Departments");
