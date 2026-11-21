// Tools that are built but not yet released on sf-works.org.
//
// Bryan, 2026-09-28: "please feature flag and hide the housing and permits
// parts of the site for now -- I'd like to get the biking part out ASAP and
// refine the rest over the coming weeks."
//
// A hidden tool's pages are not rendered, it is left out of the navigation and
// the sitemap, and a home-page heading linking to it is dropped with the
// paragraph under it (src/content.mjs). Production builds hide it. Staging and the local
// dev server set SITE_SHOW_HIDDEN=1 so the tool can still be reviewed there.
// Releasing a tool is deleting its name from this list.

// Grand Juries: built 2026-10-23.
// Daily Trips: the full access map, built 2026-10-23.
export const HIDDEN_TOOLS = ["housing", "permits", "grand-juries", "daily-trips"];

// Single pages built but not yet released, hidden the same way while Bryan
// reviews them on the staging server.
//
// /embed/injuries: the injury map framed in the board doc (src/injury-blocks.mjs).
// The injury page itself was dropped on 2026-10-23 (Bryan: "Drop the page on sf
// works and keep just one mdx file with charts pleases"), and its map embed stays
// hidden from production.
export const HIDDEN_PAGES = ["/embed/injuries"];

// Pages taken off the site for good, staging included, each with where its
// address now sends the reader. Their source stays in the repo (src/pages) so
// its tests and the board docs' embeds keep working, but no build renders
// them: the build writes a redirect page at each one's address instead
// (scripts/site-files.mjs) and the worker answers the same addresses with a 301
// (src/worker.mjs).
//
// Safer School Trips, at /transportation/school-trips and its address before
// 2026-10-12: Bryan, 2026-11-08: "Remove the safer school trips section from sf
// works website for now", and 2026-11-19: "Archive and move aaay safer school
// trips pages from sf works".
export const ARCHIVED_PAGES = {
  "/transportation/school-trips": "/transportation",
  "/transportation/bike/schools/trips": "/transportation",
};

const showAll = process.env.SITE_SHOW_HIDDEN === "1";

// The tool a site path belongs to: "/housing/about" → "housing".
const toolOf = (p) => String(p).split("/").filter(Boolean)[0] || "";

export const toolShown = (tool) => showAll || !HIDDEN_TOOLS.includes(tool);
const under = (p, h) => p === h || String(p).startsWith(`${h}/`);

/** Where an archived page's address now sends the reader, or null. */
export const archivedTo = (p) => {
  const h = Object.keys(ARCHIVED_PAGES).find((a) => under(p, a));
  return h ? ARCHIVED_PAGES[h] : null;
};

export const pathShown = (p) =>
  !archivedTo(p) && toolShown(toolOf(p)) && (showAll || !HIDDEN_PAGES.some((h) => under(p, h)));
