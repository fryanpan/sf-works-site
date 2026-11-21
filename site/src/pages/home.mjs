import { page } from "../layout.mjs";
import { content } from "../content.mjs";
import { recentChanges } from "../md-pages.mjs";

export const path = "/";
export const file = "index.html";

// The markdown pages that changed most recently (src/md-pages.mjs), above the
// list of reports, so a returning reader sees what's new first. The prose in
// content/home.md is bound to a board doc and is left as it is.
function withRecent(html) {
  const recent = recentChanges();
  if (!recent) return html;
  const at = html.search(/<h2[\s>]/);
  return at === -1 ? html + recent : html.slice(0, at) + recent + "\n" + html.slice(at);
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
