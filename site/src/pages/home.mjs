import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { RECENT_MARK } from "../md-pages.mjs";

export const path = "/";
export const file = "index.html";

// The pages and dashboards that changed most recently (src/md-pages.mjs
// recentChanges), above the topics, so a returning reader sees what's new
// first. The build fills the mark (scripts/site-files.mjs), because only it
// knows every dashboard and the commits to its code.
function withRecent(html) {
  const at = html.search(/<h2[\s>]/);
  return at === -1 ? html + RECENT_MARK : html.slice(0, at) + RECENT_MARK + "\n" + html.slice(at);
}

export function render() {
  return page({
    title: "SF Works Prototype – Reports Built on Public Data",
    description:
      "Rapidly prototyped reports built on San Francisco's public data, to understand how the city is working.",
    path,
    body: withRecent(content("home")),
  });
}
