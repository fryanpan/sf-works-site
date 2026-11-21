// Shared pieces of the Grand Juries pages: the data, markdown to HTML with
// the topic's inline notes as tap-to-open sources, and the counts.
//
// The data is data/cgj.json, written by tools/grand-juries/build-cgj-site.py from the
// Civil Grand Jury research, one entry per report with its four parts (gaps
// found, key recommendations, response, followed through) as markdown.

import fs from "node:fs";
import nodePath from "node:path";
import { marked } from "marked";
import { esc } from "./html.mjs";

export const data = JSON.parse(
  fs.readFileSync(nodePath.join(import.meta.dirname, "..", "data", "cgj.json"), "utf8"),
);

export const reports = data.reports;

// The newest term has had no follow-up yet, so its recommendations can't show evidence.
export const newestTerm = data.terms[0].term;
const sum = (rs, k) => rs.reduce((t, r) => t + r.counts[k], 0);
export const newest = reports.filter((r) => r.term === newestTerm);
export const older = reports.filter((r) => r.term !== newestTerm);
export const counted = { n: sum(older, "n"), evidence: sum(older, "evidence"), newestN: sum(newest, "n") };

export const pct = (a, b) => `${Math.round((100 * a) / b)}%`;

// The research marks its own counts `[inference — mine]`; on the page that is a small tag.
// "[inference — mine]" means a count we made from the documents, so the page says "our count".
const tags = (md) =>
  md.replace(/`\[([^\]`]+)\]`/g, (_, t) => `<span class="tag">[${t === "inference — mine" ? "our count" : t}]</span>`);

/**
 * Markdown (one paragraph or one bullet) to inline HTML, each {{fn:N}} token
 * becoming a numbered button that opens note N beneath it.
 */
export function md(text, notes = []) {
  const html = marked.parseInline(tags(text));
  return html.replace(/\{\{fn:(\d+)\}\}/g, (_, n) => {
    const note = notes[Number(n) - 1];
    if (note == null) throw new Error(`grand-juries: note ${n} missing`);
    return `<button class="gj-fn" type="button" aria-expanded="false" aria-label="Source">${n}</button><span class="gj-note" hidden>${marked.parseInline(tags(note))}</span>`;
  });
}

// The tap-to-open sources, shared by both pages.
export const FN_CSS = `
.gj-fn { font: 600 0.68rem/1 "Public Sans", system-ui, sans-serif; color: var(--muted); background: var(--raised); border: 1px solid var(--rule);
  border-radius: 999px; min-width: 1.5em; padding: 2px 5px; margin-left: 3px; vertical-align: 0.15em; cursor: pointer; }
.gj-fn[aria-expanded="true"] { color: var(--ink); border-color: var(--muted); }
.gj-note { display: block; font-size: 0.8rem; line-height: 1.4; color: var(--ink); background: var(--raised); border-left: 3px solid var(--rule);
  padding: 6px 9px; margin: 4px 0 6px; }
.gj-note[hidden] { display: none; }
.gj-note .tag, .gj .tag, .gj-about .tag { font-size: 0.72rem; color: var(--muted); white-space: nowrap; }
`;

export const FN_SCRIPT = `<script>
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest(".gj-fn");
  if (!b) return;
  var note = b.nextElementSibling;
  var open = b.getAttribute("aria-expanded") === "true";
  b.setAttribute("aria-expanded", open ? "false" : "true");
  note.hidden = open;
});
</script>`;

export const SOURCES = [
  { label: "sf.gov, Civil Grand Jury — every report, press release and posted response, 2022-23 to 2025-26", href: "https://www.sf.gov/departments--civil-grand-jury", read: data.read },
  { label: "Archived Civil Grand Jury site, 2021-22 — the 2021-22 reports and responses", href: "https://civilgrandjury.archive.sf.gov/2021_2022.html", read: data.read },
  { label: "Board of Supervisors resolutions — the Board's response resolutions, 2022 to 2025, with Legistar file pages for 2026", href: "https://sfbos.org/resolutions-2025", read: data.read },
  { label: "Office of the Controller, Status of Civil Grand Jury Recommendations — December 2025 update for 2021-22 to 2023-24", href: "https://www.sf.gov/information--status-civil-grand-jury-recommendations", read: data.read },
];

export { esc };
