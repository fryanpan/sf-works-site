// The redirect from /transportation/plan-vs-built, which compared what the
// plan draws with what the paving left until 2026-09-23. Links to the old
// address exist, so this module still renders a file there that sends the
// reader to the bike front page, whose street-work map carries the repaving story.

import { redirectPage } from "../redirect.mjs";

export const path = "/transportation/plan-vs-built";
export const file = "transportation/plan-vs-built/index.html";

/** Where the old page now points. The build keeps a redirect page out of the sitemap. */
export const redirect = "/transportation/bike";
export const render = () => redirectPage(redirect, "Better Coordination Across City Departments");
