// The redirect from /transportation/osm, where "Two maps disagree" lived until
// 2026-09-22. Its content is now a section of About the Data, because Bryan
// asked for every data discussion in the transportation section to sit on one
// page. Links to the old address exist, so this module still renders a file
// there: a page that sends the reader on. The worker also answers the old
// address with a 301, and this file is what a static host serves without it.
import { redirectPage } from "../redirect.mjs";

export const path = "/transportation/osm";
export const file = "transportation/osm/index.html";

/** Where the old address now points. The build keeps a redirect page out of the sitemap. */
export const redirect = "/transportation/bike/about";

export const render = () => redirectPage(redirect, "About the data");
