// Grand Juries: what each Civil Grand Jury report since 2021-22 found, asked
// for, heard back from the city, and whether anything was done.
//
// Bryan, 2026-10-23, on the four-part layout of the research page: "Reads
// right. Make a better UX for this please in a mock that can go on the sf
// works page under grand juries". So the same four parts and the same words,
// as a tool: the reports on the left, each with its follow-through as counts
// (Bryan's "follow-through as counts"), and the chosen report's four parts on
// the right. One control, the report list. The chosen report is in the
// address (?report=<id>), and the page opens on the newest report that has a
// published follow-up.
//
// Every figure comes from data/cgj.json (tools/grand-juries/build-cgj-site.py). The bars
// are Observable Plot, drawn at build time (src/plot.mjs).

import { page } from "../layout.mjs";
import { Plot, plotSVG } from "../plot.mjs";
import { data, reports, newestTerm, counted, pct, md, esc, FN_CSS, FN_SCRIPT, SOURCES } from "../grand-juries.mjs";

export const path = "/grand-juries";
export const file = "grand-juries/index.html";
export const listing = { title: "Grand Juries", line: "What each Civil Grand Jury report since 2021-22 asked the city to fix, and whether it was done." };

// The newest report with a published follow-up: a reader lands on a report that has an answer.
const DEFAULT = reports.find((r) => r.followed.verdict !== "Unknown") || reports[0];
const MAX_N = Math.max(...reports.map((r) => r.counts.n));

// Two categories: the recommendations with evidence they were done, and the rest.
// What the city said about each one is in the report's Response, said once.
const KEY = [
  ["evidence", "Evidence it was done", "var(--seq-3)"],
  ["rest", "No evidence yet", "var(--rule)"],
];

// One report's recommendations as one bar on a shared scale, the ones with
// evidence they were done from the left, labelled "N of M" beside it.
function bar(r) {
  const c = r.counts;
  const W = 132, H = 14;
  const segs = [
    { x1: 0, x2: c.n, fill: "var(--rule)" },
    { x1: 0, x2: c.evidence, fill: "var(--seq-3)" },
  ].filter((s) => s.x2 > s.x1);
  return plotSVG(
    {
      width: W, height: H, margin: 0,
      x: { domain: [0, MAX_N], range: [0, W], axis: null },
      y: { axis: null },
      marks: [Plot.barX(segs, { x1: "x1", x2: "x2", fill: "fill", insetTop: 1, insetBottom: 1 })],
    },
    {
      className: "gj-bar",
      label: `${c.evidence} of ${c.n} recommendations with evidence they were done`,
    },
  );
}

// The newest term's reports are too new to show evidence, so their row gives only how many were asked.
const row = (r) => `<li id="row-${r.id}"><button type="button" class="gj-row" data-id="${r.id}" aria-pressed="${r === DEFAULT}" aria-controls="gj-detail">
  <span class="gj-name" title="${esc(r.title)}">${esc(r.short)}</span>
  ${r.term === newestTerm ? `<span></span><span class="gj-count">${r.counts.n} asked</span>` : `${bar(r)}
  <span class="gj-count"><b>${r.counts.evidence}</b> of ${r.counts.n}</span>`}
</button></li>`;

const list = () =>
  data.terms
    .map((t) => {
      const rs = reports.filter((r) => r.term === t.term);
      return `<li class="gj-term"><span class="gj-term-name">${t.term} jury${t.term === newestTerm ? " · too new for a follow-up" : ""}</span><ul>${rs.map(row).join("")}</ul></li>`;
    })
    .join("");

const date = (iso) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });

const items = (xs, notes) => (xs.length ? `<ul>${xs.map((x) => `<li>${md(x, notes)}</li>`).join("")}</ul>` : "");

// The followed-through lead starts with its verdict ("Partly.", "Unknown: ..."); that word carries the colour.
const VERDICT_CLASS = { Yes: "v-yes", Partly: "v-partly", No: "v-no", Unknown: "v-unknown" };
function followedLead(r) {
  const lead = md(r.followed.lead || r.followed.verdict, r.notes);
  return lead.replace(new RegExp(`^${r.followed.verdict}`), `<b class="gj-verdict ${VERDICT_CLASS[r.followed.verdict]}">${r.followed.verdict}</b>`);
}

// The row already prints each report's total ("1 of 17"), so the Response
// doesn't repeat it: "Of 17 recommendations: 13 done" reads "13 done".
const N = (r) => String(r.counts.n);
const dropTotal = (r, x) =>
  x
    .replace(new RegExp(`\\bOf ${N(r)} recommendations, including ([^:]+): `), "Including $1: ")
    .replace(new RegExp(`\\bOf ${N(r)} recommendations: `), "")
    .replace(new RegExp(`, on ${N(r)} recommendations: `), ": ")
    .replace(new RegExp(`\\bAll ${N(r)} recommendations are`), "All recommendations are");

function detail(r) {
  const term = data.terms.find((t) => t.term === r.term);
  // A part's lead is its source button (and, for Followed through?, the verdict), placed beside the heading, not in it.
  const part = (h, lead, html) => `<section class="gj-part"><h3>${h}${lead ? `<span class="gj-lead">${lead}</span>` : ""}</h3>${html}</section>`;
  return `<article class="gj-report" data-report="${r.id}"${r === DEFAULT ? "" : " hidden"}>
  <p class="gj-meta">Released ${date(r.released)} · <a href="${esc(r.url)}">Read the report</a></p>
  <h2 class="gj-title">${esc(r.title)}</h2>
  ${r.intro ? `<p class="gj-intro">${md(r.intro, r.notes)}</p>` : ""}
  <div class="gj-parts">
    ${part("Gaps found", md(r.gaps.lead || "", r.notes), items(r.gaps.items, r.notes))}
    ${part("Key recommendations", md(r.asks.lead || "", r.notes), items(r.asks.items, r.notes))}
    ${part("Response", md(r.response.lead || "", r.notes), items(r.response.items.map((x) => dropTotal(r, x)), r.notes))}
    ${part("Followed through?", "", `<p>${followedLead(r)}</p>${items(r.followed.items, r.notes)}`)}
  </div>
  <p class="gj-back"><a href="#row-${r.id}">Back to all reports</a></p>
  <p class="gj-termnote">${md(term.intro.replace(/ These reports are [a-z]+ months old, so no follow-up has been published\./, ""), term.notes)}</p>
</article>`;
}

const CSS = `<style>
.gj { width: min(1340px, 100vw - 32px); margin-left: calc(50% - min(670px, 50vw - 16px)); }
.gj h1 { font-size: 1.75rem; margin: 6px 0 4px; }
.gj-top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 28px; margin-bottom: 10px; }
.gj-lede { margin: 0; color: var(--muted); font-size: 0.98rem; max-width: 70ch; }
.gj-grid { display: grid; grid-template-columns: 430px minmax(0, 1fr); height: calc(100dvh - 228px); min-height: 500px;
  border: 1px solid var(--rule); border-radius: 8px; overflow: hidden; }
.gj-side { border-right: 1px solid var(--rule); display: flex; flex-direction: column; min-height: 0; background: var(--paper); }
.gj-stat { padding: 10px 14px 8px; border-bottom: 1px solid var(--rule); }
.gj-stat .big { font: 700 1.6rem/1.1 Archivo, sans-serif; color: var(--seq-3); }
.gj-stat .big small { font-size: 0.95rem; color: var(--muted); font-weight: 600; margin-left: 6px; }
.gj-stat .what { display: block; font-size: 0.9rem; line-height: 1.3; }
.gj-key { display: flex; flex-wrap: wrap; gap: 2px 12px; margin: 6px 0 0; padding: 0; list-style: none; font-size: 0.76rem; color: var(--grey-dark); }
.gj-key i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
.gj-note-line { font-size: 0.74rem; color: var(--muted); margin: 4px 0 0; line-height: 1.35; }
.gj-list { list-style: none; margin: 0; padding: 4px 6px 8px; overflow-y: auto; flex: 1; position: relative; }
.gj-list ul { list-style: none; margin: 0; padding: 0; }
.gj-list li { margin: 0; padding: 0; }
.gj-term-name { display: block; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); padding: 8px 8px 2px; }
.gj-row { display: grid; grid-template-columns: minmax(0, 1fr) 132px 54px; gap: 10px; align-items: center; width: 100%;
  text-align: left; font: inherit; font-size: 0.88rem; line-height: 1.25; color: var(--ink); background: none; border: 1px solid transparent;
  border-radius: 6px; padding: 4px 8px; cursor: pointer; }
.gj-row:hover { background: var(--raised); }
.gj-row[aria-pressed="true"] { background: var(--seq-3-soft); border-color: var(--seq-3); font-weight: 600; }
.gj-row:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.gj-name { overflow-wrap: anywhere; }
.gj-count { text-align: right; font-size: 0.82rem; color: var(--muted); white-space: nowrap; font-weight: 400; }
.gj-count b { color: var(--ink); }
.gj-row .gj-bar { display: block; margin: 0; width: 132px; height: 14px; }
.gj-detail { overflow-y: auto; padding: 12px 20px 18px; min-height: 0; }
.gj-meta { font-size: 0.82rem; color: var(--muted); margin: 0; }
.gj-title { font-size: 1.25rem; margin: 4px 0 6px; }
.gj-intro, .gj-termnote { font-size: 0.86rem; color: var(--muted); margin: 0 0 8px; }
.gj-termnote { margin-top: 12px; border-top: 1px solid var(--rule); padding-top: 8px; }
.gj-parts { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 26px; }
.gj-part h3 { font-size: 0.95rem; margin: 8px 0 2px; }
.gj-detail .gj-part ul { list-style: disc; margin: 0; padding-left: 18px; }
.gj-detail .gj-part li, .gj-detail .gj-part p { font-size: 0.86rem; line-height: 1.45; margin: 0 0 4px; }
.gj-verdict { padding: 0 6px; border-radius: 4px; }
.gj-verdict.v-yes { background: var(--seq-3-soft); color: var(--seq-3); }
.gj-verdict.v-partly { background: var(--seq-2-soft); color: #7a5d22; }
.gj-verdict.v-no { background: var(--seq-1-soft); color: var(--seq-1); }
.gj-verdict.v-unknown { background: var(--raised); color: var(--grey-dark); }
.gj-back { display: none; }
${FN_CSS}
@media (max-width: 900px) {
  .gj-back { display: block; font-size: 0.86rem; margin: 10px 0 0; }
  .gj { width: auto; margin-left: 0; }
  .gj h1 { font-size: 1.4rem; }
  .gj-grid { display: block; height: auto; min-height: 0; border: 0; overflow: visible; }
  .gj-side { border-right: 0; }
  .gj-stat { padding: 8px 0; }
  .gj-list { overflow: visible; padding: 0; }
  .gj-row { grid-template-columns: minmax(0, 1fr) 96px 48px; gap: 8px; padding: 6px 4px; font-size: 0.86rem; }
  .gj-row .gj-bar { width: 96px; height: 14px; }
  .gj-detail { overflow: visible; padding: 6px 4px 14px; margin: 0 0 8px; border-bottom: 1px solid var(--rule); }
  .gj-row { scroll-margin-top: 8px; }
  .gj-parts { grid-template-columns: 1fr; }
}
</style>`;

// Picking a report shows it, keeps the list where it is, and puts it in the address.
const SCRIPT = `<script>
(function () {
  var rows = document.querySelectorAll(".gj-row");
  var panel = document.getElementById("gj-detail");
  var narrow = window.matchMedia("(max-width: 900px)");
  var grid = document.querySelector(".gj-grid");
  // On a phone the chosen report opens directly under its own row; on a laptop it sits in the right column.
  function place() {
    var on = document.querySelector('.gj-row[aria-pressed="true"]');
    if (narrow.matches && on) on.parentNode.appendChild(panel);
    else if (panel.parentNode !== grid) grid.appendChild(panel);
  }
  function show(id, fromTap) {
    var found = false;
    document.querySelectorAll(".gj-report").forEach(function (a) {
      var on = a.getAttribute("data-report") === id;
      a.hidden = !on;
      if (on) found = true;
    });
    if (!found) return false;
    rows.forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-id") === id ? "true" : "false"); });
    panel.scrollTop = 0;
    var q = "?report=" + encodeURIComponent(id);
    history.replaceState(null, "", location.pathname + q);
    window.dispatchEvent(new CustomEvent("sfworks:state", { detail: q }));
    place();
    if (fromTap && narrow.matches) document.querySelector('.gj-row[aria-pressed="true"]').scrollIntoView({ block: "start" });
    return true;
  }
  rows.forEach(function (b) { b.addEventListener("click", function () { show(b.getAttribute("data-id"), true); }); });
  var asked = new URLSearchParams(location.search).get("report");
  place();
  narrow.addEventListener("change", place);
  var shown = asked && show(asked, false);
  if (shown && narrow.matches) document.querySelector('.gj-row[aria-pressed="true"]').scrollIntoView({ block: "start" });
  if (shown && !narrow.matches) {
    // Bring a report chosen by its address into view in the list, without moving the page.
    var list = document.querySelector(".gj-list");
    var on = document.querySelector('.gj-row[aria-pressed="true"]');
    if (on) list.scrollTop += on.getBoundingClientRect().top - list.getBoundingClientRect().top - list.clientHeight / 3;
  }
})();
</script>`;

const FN1 = data.lede.paragraphs[0].indexOf("{{fn:1}}");
if (FN1 === -1) throw new Error("grand-juries: the lede's first sentence lost its source note");

export function render() {
  const L = data.lede;
  const body = `${CSS}
<div class="gj">
  <h1>Few Grand Jury Recommendations Have Evidence They Were Done</h1>
  <div class="gj-top">
    <p class="gj-lede">${md(L.paragraphs[0].slice(0, FN1 + "{{fn:1}}".length), L.notes)} Pick a report to see what its jury found, what it asked for, how the city answered, and what happened next.</p>
  </div>
  <div class="gj-grid">
    <div class="gj-side">
      <div class="gj-stat">
        <span class="big">${counted.evidence} of ${counted.n}<small>${pct(counted.evidence, counted.n)}</small></span>
        <span class="what">recommendations from ${data.terms[data.terms.length - 1].term} to ${data.terms[1].term} have evidence they were done. <a href="/grand-juries/about">How we counted</a></span>
        <ul class="gj-key">${KEY.map(([, l, c]) => `<li><i style="background:${c}"></i>${l}</li>`).join("")}</ul>
      </div>
      <ul class="gj-list" aria-label="Reports">${list()}</ul>
    </div>
    <div class="gj-detail" id="gj-detail">
      ${reports.map(detail).join("")}
    </div>
  </div>
</div>
${FN_SCRIPT}
${SCRIPT}`;
  return page({
    title: "Grand Juries",
    description: "What each San Francisco Civil Grand Jury report since 2021-22 asked the city to fix, how the city answered, and whether it was done.",
    path,
    body,
    sources: SOURCES,
    about: { href: "/grand-juries/about", label: "About the data" },
    shareState: `?report=${DEFAULT.id}`,
  });
}
