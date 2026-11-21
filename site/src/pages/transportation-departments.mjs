// Work across Departments: what other departments' street work has done for
// the Biking and Rolling Plan's network. One page since 2026-09-23, when Bryan
// asked to "Combine the repaving + planned vs. built into a section on 'Work
// across Departments'". The repaving and plan-against-built figures come from
// the two modules that used to be those pages, which now only redirect here.
//
// Since 2026-10-03 the sections are the end of the overview
// (content/transportation.md); this module builds their figures.

import { redirectPage } from "../redirect.mjs";
import fs from "node:fs";
import nodePath from "node:path";
import { data, esc, block, street, METRE } from "../transportation.mjs";
import { segMap } from "../transportation-map.mjs";
import { shade, readoutFor } from "./transportation-repaving.mjs";
import { projectPath, shortDate, dept, KIND, shortFinding } from "./transportation-projects.mjs";

const COORD = JSON.parse(fs.readFileSync(nodePath.join(import.meta.dirname, "..", "..", "data", "coordination.json"), "utf8"));
const BY_SLUG = Object.fromEntries(COORD.projects.map((p) => [p.slug, p]));

// A readable title for a job from its streets. Public Works and SFPUC name jobs by contract
// ("Paving job 10040039", "Various Locations Pavement Renovation No 68"), so the popover uses the
// streets instead (Bryan, 2026-10-09). SFMTA's own project names are kept.
function streetTitle(list) {
  const u = [...new Set((list || []).filter(Boolean))];
  if (!u.length) return "";
  return u.length <= 2 ? u.join(" and ") : `${u.slice(0, 2).join(", ")} and ${u.length - 2} more ${u.length === 3 ? "street" : "streets"}`;
}
const titleOf = (p, streets) => (p && p.source === "sfmta" ? p.name : streetTitle(streets || (p && p.streets)) || (p && p.name) || "");

// What the map's popover says about one Public Works or SFPUC job.
function jobCard(slug, marks = []) {
  const p = BY_SLUG[slug];
  if (!p) return null;
  const j = O.jobs[slug] || {
    cnns: [...new Set(marks.map((m) => String(m.cnn)))],
    byCategory: marks.reduce((b, m) => ((b[m.status] = (b[m.status] || 0) + m.lengthM / METRE), b), {}),
  };
  const my = (d) => shortDate(d.slice(0, 7));
  const when = p.underWay
    ? (p.end ? `until ${my(p.end)}` : "under way")
    : p.start ? `from ${my(p.start)}` : "no start date";
  const brief = `${dept(p)} ${(KIND[p.kind] || p.kind).toLowerCase()}, ${when}. ` + shortFinding(p);
  return {
    name: titleOf(p), brief, bars: merged(j.byCategory || {}), cnns: j.cnns,
    links: [{ label: "Project page", url: projectPath(p) }, ...p.links.map((l) => ({ label: l.label, url: l.url }))],
  };
}

// Written by tools/projects/department-overlap.py: other departments' street work
// through 2028 against the plan's unbuilt blocks, and the repaving record.
const O = JSON.parse(
  fs.readFileSync(nodePath.join(import.meta.dirname, "..", "..", "data", "department-overlap.json"), "utf8"),
);

const one = (n) => (Math.round(n * 10) / 10).toFixed(1);

const shortDate10 = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

function shortDay(iso) {
  return new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

const monthYear = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });

// ---- Past, and now and next: a bar chart and a map each ---------------------
// Bryan, 2026-09-28: "Show the same categories as below, but use a bar chart";
// and "use the same technique as the maps on the overview page -- use a wider
// full width map". Each bar is one of the map's categories; a bar is also the
// button that picks out its streets on the map.

// Bryan, 2026-09-28, on the bars: blocks with no bikeway join those with less
// than the plan draws, as one "did not implement" bar and one map colour.
const CATS = ["met", "short", "already"];
const cat = (c) => (c === "none" ? "short" : c);
const PLAN_DRAWS = { Separated: "a separated lane", Shared: "a shared street", "Shared L3": "a Level 3 shared street", Undecided: "no bikeway type yet" };
const LATER_VERDICT = {
  met: "An SFMTA project on this street segment, or the job's own scope, adds the plan's bikeway.",
  already: "It already has what the plan draws.",
  short: "It has less than the plan draws, and nothing published adds more.",
  none: "It has no bikeway, and nothing published adds one.",
};

// A block's length from its drawn line, for a job the overlap file has no
// card for (its blocks are still on the map, so the popover still opens).
const lineM = (pts) => pts.slice(1).reduce((t, q, i) => {
  const p = pts[i], k = Math.PI / 180, dy = (q[1] - p[1]) * k, dx = (q[0] - p[0]) * k * Math.cos(((q[1] + p[1]) / 2) * k);
  return t + 6371008.8 * Math.hypot(dx, dy);
}, 0);

const merged = (m) => ({ met: m.met || 0, short: (m.short || 0) + (m.none || 0), already: m.already || 0 });

// Bryan, 2026-09-28: "Past should only include repaving that ended in Apr
// 2025" onward. A repave finished in the plan's own month was scheduled
// before it, so Past starts on the first of the month after adoption.
// tools/projects/department-overlap.py sets that date, and every Past figure on the
// page, the bars and the description alike, is counted from it.
const PAST_FROM = O.compare[0].from;

// SFMTA bike projects by block, so a past repave that fell short can say
// whether SFMTA has bike work coming there. The list's pedestrian-only and
// study-area SFMTA rows carry bikeScope false and are left out.
const SFMTA_ON = new Map();
for (const p of COORD.projects) if (p.kind === "SFMTA bike and safety" && p.bikeScope) for (const c of p.planCnns || []) if (!SFMTA_ON.has(String(c))) SFMTA_ON.set(String(c), p);
function sfmtaNote(s) {
  const p = SFMTA_ON.get(String(s.cnn));
  if (!p || shade(s) === "already" || shade(s) === "met") return "";
  return ` SFMTA's <a href="/transportation/bike/projects/${esc(p.slug)}/">${esc(p.name)}</a> covers this street segment (${esc(p.phase || "phase not published")}).`;
}

// Past repaves by paving job, for the map's popover (Bryan, 2026-09-29:
// "Clicking should bring up a project panel that has key details. And
// highlight all segments related to the project"). tools/projects/department-overlap.py
// takes each block's job order from its dig moratorium; a block with none
// opens a card of its own.
const PAST_JOB = new Map();
for (const [jo, j] of Object.entries(O.pastJobs || {})) for (const c of j.cnns) PAST_JOB.set(String(c), `pj-${jo}`);
const pastKey = (s) => PAST_JOB.get(String(s.cnn)) || `pb-${s.cnn}`;
const when = (a, b) => (shortDay(a) === shortDay(b) ? `in ${shortDay(a)}` : `${shortDay(a)} to ${shortDay(b)}`);
function pastCards(pastSegs) {
  const groups = new Map();
  for (const s of pastSegs) (groups.get(pastKey(s)) || groups.set(pastKey(s), []).get(pastKey(s))).push(s);
  const cards = {};
  for (const [key, segs] of groups) {
    const bars = { met: 0, short: 0, already: 0 };
    for (const s of segs) bars[cat(shade(s))] += s.lengthM / METRE;
    const j = key.startsWith("pj-") ? O.pastJobs[key.slice(3)] : null;
    if (j) {
      const p = j.slug && BY_SLUG[j.slug];
      const streets = j.streets.map((n) => street(n).replace(/&amp;/g, "&")).join(", ");
      cards[key] = {
        name: titleOf(p, j.streets.map((n) => street(n).replace(/&amp;/g, "&"))) || `Paving job ${j.jobOrder}`,
        brief: `Repaved ${when(j.from, j.to)}: ${streets}. Public Works job order ${j.jobOrder}, from the city's dig moratorium record.`,
        bars, cnns: j.cnns.map(String),
        links: [...(p ? [{ label: "Project page", url: projectPath(p) }] : []), { label: "Dig moratorium record", url: "https://data.sfgov.org/d/5wbp-dwzt" }],
      };
    } else {
      const s = segs[0];
      cards[key] = {
        name: street(s.street).replace(/&amp;/g, "&"),
        brief: (readoutFor(s) + sfmtaNote(s)).replace(/<[^>]+>/g, "").replace(/&amp;/g, "&") + " The dig moratorium record names no paving job for this repave.",
        bars, cnns: [String(s.cnn)], links: [],
      };
    }
  }
  return cards;
}

// Bryan, 2026-10-01, on the Past / Active / Future tabs: "the page is a bit
// confusing, perhaps because its' interactive. Let's split the Past, Active,
// Future into two sections. Combine Active, Future into one." So the page has
// two sections that read top to bottom, each with its own bars and map: Past
// (repaving finished since the plan) and Now and Next (work under way or
// starting through the calendar's horizon).
function stageData() {
  const pastSegs = data.segments.filter((s) => s.status !== "unrated" && s.repaved >= PAST_FROM);
  const pastMiles = Object.fromEntries(CATS.map((c) => [c, pastSegs.filter((s) => cat(shade(s)) === c).reduce((t, s) => t + s.lengthM, 0) / METRE]));
  const [rep, now, later] = O.compare;
  const laterMarks = (r, when) => r.segments.map((b) => {
    const name = street(b.street).replace(/&amp;/g, "&");
    const job = b.job ? `${b.job} (${when(b)})` : "";
    return {
      cnn: b.cnn, line: b.line, status: cat(b.cat), stage: "next", street: name, job: b.slug && (O.jobs[b.slug] || BY_SLUG[b.slug]) ? b.slug : "", block: job, lengthM: lineM(b.line), wants: b.wants, has: b.has || "nothing", repaved: "",
      readout: `<strong>${esc(name)}</strong>. ${esc(job)}. The Biking and Rolling Plan calls for ${PLAN_DRAWS[b.wants] || esc(b.wants)}. ${LATER_VERDICT[b.cat]}`,
    };
  });
  const nowMiles = merged(now.byCategory), laterMiles = merged(later.byCategory);
  return {
    past: { id: "past", when: `Repaving finished ${shortDay(PAST_FROM)} to ${shortDay(rep.to)}, from the city's pavement records`, miles: pastMiles,
      cards: pastCards(pastSegs),
      marks: pastSegs.map((s) => ({ cnn: s.cnn, job: pastKey(s), status: cat(shade(s)), stage: "past", street: street(s.street).replace(/&amp;/g, "&"),
        block: block(s.limits).replace(/&amp;/g, "&"), wants: s.wants, has: s.has.length ? [...new Set(s.has)].join(" and ") : "nothing", repaved: s.repaved, lengthM: s.lengthM, readout: readoutFor(s) + sfmtaNote(s) })) },
    next: { id: "next", when: `Work under way or starting ${later.buckets[0]} to ${later.buckets[later.buckets.length - 1]}, from the city's street-work calendar as of ${shortDate10(O.sources.feed.queried)}`,
      miles: Object.fromEntries(CATS.map((c) => [c, nowMiles[c] + laterMiles[c]])), now: nowMiles, later: laterMiles,
      marks: [...laterMarks(now, () => "under way"),
        ...laterMarks(later, (b) => (b.start ? `starts ${shortDay(b.start.length === 4 ? `${b.start}-07-01` : b.start.length === 7 ? `${b.start}-15` : b.start)}` : "no start date"))] },
  };
}

// Bryan, 2026-10-07: "The bar graph labels are hard to understand. Can you
// instead put up top 'Did we build the upgraded bikeway after repaving?' Yes /
// No / Plan's bikeway was already there", with SFMTA for "we", and for the
// second tab "Does SFMTA plan to build the upgraded bikeway after repaving?"
// So the chart asks its question once and each bar is the answer. The
// popover has no question above it, so it keeps the long names (CAT_LONG).
const CAT_Q = {
  past: "Did SFMTA build the upgraded bikeway after repaving?",
  next: "Does SFMTA plan to build the upgraded bikeway after repaving?",
};
const CAT_LABEL = {
  met: { past: "Yes", next: "Yes" },
  short: { past: "No", next: "No" },
  already: { past: "Plan's bikeway was already there", next: "Plan's bikeway was already there" },
};
const CAT_LONG = {
  met: { past: "Bikeway built with the repave", next: "Bikeway upgrade planned" },
  short: { past: "Repaved without the bikeway", next: "No bikeway upgrade planned" },
  already: { past: "Plan's bikeway already there", next: "Plan's bikeway already there" },
};

// The popover's "Gap from Biking and Rolling Plan" list (Bryan, 2026-10-02:
// "The project popovers are mostly not clear about what the bike plan called
// for on that street. Please make sure that information is there."): one row
// per street, what the plan calls for there, what it has now, and the miles,
// colored as the bars. Streets the plan draws the same way are one row.
const WANTS = { Separated: "separated lane", Shared: "shared street", "Shared L3": "Level 3 shared street", "Shared-use Path": "shared-use path", "Car-free": "car-free street", Undecided: "no bikeway type yet" };
const RANK_NOW = ["path", "separated lane", "painted lane", "sharrow"];
const hasNow = (h) => {
  const each = [...new Set(String(h || "").split(/ and |, /).filter((x) => x && x !== "nothing"))]
    .sort((a, b) => RANK_NOW.indexOf(a) - RANK_NOW.indexOf(b));
  return each.length ? each.map((x) => `a ${x}`).join(" and ") : "no bikeway";
};
function gapRows(marks) {
  const rows = new Map();
  for (const m of marks) {
    const k = [m.street, m.wants, hasNow(m.has), m.status].join("|");
    const r = rows.get(k) || rows.set(k, { street: m.street, wants: WANTS[m.wants] || m.wants, has: hasNow(m.has), cat: m.status, mi: 0 }).get(k);
    r.mi += (m.lengthM || 0) / METRE;
  }
  const order = { short: 0, met: 1, already: 2 };
  return [...rows.values()].sort((a, b) => order[a.cat] - order[b.cat] || b.mi - a.mi || a.street.localeCompare(b.street))
    .map((r) => ({ ...r, mi: Math.round(r.mi * 100) / 100 }));
}

const STAGES = stageData();
// One scale for both sections' bars, so a bar in one compares with the other.
const BAR_MAX = Math.max(...Object.values(STAGES).flatMap((st) => CATS.map((c) => st.miles[c] || 0)));

// One section's figure: the bars, the map beside them, and a popover for a
// picked job. It comes in two halves so the content file can put text
// between them; the section's heading and sentences sit above the figure, so
// they span the bars and the map (Bryan, 2026-10-01: "Move the heading and
// text above the map and bar chart").
function stageView(id) {
  const st = STAGES[id];
  const bars = `<ul class="stg-bars">${CATS.filter((c) => one(st.miles[c] || 0) !== "0.0").map((c) => {
    const v = st.miles[c] || 0;
    const label = CAT_LABEL[c][id], long = CAT_LONG[c][id];
    return `<li data-cat="${c}" data-long="${esc(long)}" tabindex="0" aria-label="Show ${esc(long)} on the map"><span class="stg-cat">${esc(label)}</span><span class="stg-row"><i class="${c}" style="width:${((100 * v) / BAR_MAX).toFixed(1)}%"></i><b>${one(v)} mi</b></span></li>`;
  }).join("")}</ul>`;
  const q = `<p class="stg-q">${esc(CAT_Q[id])}</p>`;
  const what = id === "past"
    ? "San Francisco's streets, the plan's network in grey, and the plan's street segments repaved since it was adopted, colored as the bars."
    : "San Francisco's streets, the plan's network in grey, and the plan's street segments in city street work under way or to come, colored as the bars.";
  const map = segMap(st.marks, what, { keepColour: true });
  map.html = map.html.replace('<figure class="mapbox seg-map">', `<figure class="mapbox seg-map" id="${id}-map">`);
  const slugs = [...new Set(st.marks.map((m) => m.job).filter(Boolean))];
  const cards = Object.assign(Object.fromEntries(slugs.map((sl) => [sl, jobCard(sl, st.marks.filter((m) => m.job === sl))]).filter(([, c]) => c)), st.cards || {});
  const byJob = Object.groupBy(st.marks, (m) => m.job);
  for (const [key, c] of Object.entries(cards)) c.gap = gapRows(byJob[key] || []);
  return {
    missing: map.missing,
    open: `<div class="fig wide stage-view" data-show="${id}">
<script type="application/json" data-jobs>${JSON.stringify(cards).replace(/</g, "\\u003c")}</script>
<div class="stg-side">`,
    html: `<div class="stg-chart" data-stage="${id}">
${q}
${bars}
</div>
</div>
<div class="stg-mapwrap">
${map.html}
<aside class="stg-pop" hidden role="dialog" aria-label="Project details">
<button type="button" class="stg-pop-x" aria-label="Close">×</button>
<h3 data-pop-name></h3>
<p data-pop-brief></p>
<ul class="pop-bars" data-pop-bars></ul>
<h4 class="pop-gap-h">Gap from Biking and Rolling Plan</h4>
<ul class="pop-gap" data-pop-gap></ul>
<p class="stg-pop-links" data-pop-links></p>
</aside>
</div>
</div>`,
  };
}

export const STAGE_CSS = `<style>
.stage-view { display: grid; gap: 20px; margin-top: 12px; margin-bottom: 8px; }
.stage-view .mapbox { margin: 0; }
/* The city is as tall as it is wide, so its height sets its width: no taller than the fold. */
.stage-view .seg-gl { display: block; height: min(460px, calc(100vh - 370px)); min-height: 320px; width: 100%; max-width: 100%; }
.stg-hint { font-size: 0.88rem; color: var(--muted); margin: 0 0 8px; }
.stg-mapwrap { position: relative; min-width: 0; }
.stg-pop { position: absolute; z-index: 5; width: 300px; max-height: calc(100% - 8px); overflow-y: auto; box-sizing: border-box; background: #fff; border: 1px solid var(--rule); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.18); padding: 12px 14px; font-size: 0.9rem; }
.stg-pop h3 { font-size: 1rem; margin: 0 24px 4px 0; line-height: 1.25; }
.stg-pop p { margin: 0 0 8px; }
.stg-pop dl { display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; margin: 0 0 8px; }
.stg-pop dt { color: var(--muted); font-size: 0.85rem; } .stg-pop dd { margin: 0; font-weight: 700; font-variant-numeric: tabular-nums; }
.stg-pop-links a { margin-right: 10px; }
.stg-pop-x { position: absolute; top: 6px; right: 8px; border: 0; background: none; font-size: 1.3rem; line-height: 1; cursor: pointer; color: var(--muted); }
@media (max-width: 959px) { .stg-pop { position: static; width: auto; margin-top: 8px; } }
.stg-q { font-weight: 700; font-size: 0.98rem; line-height: 1.3; margin: 0 0 10px; text-wrap: balance; }
.stg-bars { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.stg-cat { display: block; font-size: 0.92rem; margin-bottom: 2px; }
.stg-row { display: flex; align-items: center; gap: 8px; }
.stg-row i { display: block; height: 16px; min-width: 2px; border-radius: 2px; }
.stg-row b { font-size: 0.92rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
.stg-row .met { background: var(--seq-3); } .stg-row .short { background: var(--seq-2); } .stg-row .none { background: var(--seq-1); }
/* Opaque, so a block's shade is its category alone; the map draws the
   already-built blocks in the same grey (segMap's keepColour), and a picked
   block keeps its category's colour there: the job's other blocks carry the
   selection, not one block in near-black (Bryan, 2026-09-29). */
.stg-row .already { background: var(--grey-light); }
.pop-bars { list-style: none; padding: 0; margin: 0 0 10px; display: grid; gap: 6px; }
.pop-bars .stg-cat { font-size: 0.95rem; }
.pop-gap-h { font-size: 0.92rem; margin: 4px 0 6px; }
.pop-gap { list-style: none; padding: 0; margin: 0 0 10px; display: grid; gap: 6px; }
.pop-gap li { display: grid; grid-template-columns: 12px 1fr auto; gap: 2px 8px; align-items: baseline; line-height: 1.3; }
.pop-gap i { width: 10px; height: 10px; border-radius: 2px; align-self: center; }
.pop-gap i.met { background: var(--seq-3); } .pop-gap i.short { background: var(--seq-2); } .pop-gap i.already { background: var(--grey-light); }
.pop-gap span { grid-column: 2 / 4; color: var(--muted); font-size: 0.85rem; }
.pop-gap li.more { display: block; color: var(--muted); font-size: 0.85rem; }
.pop-gap em { font-style: normal; font-variant-numeric: tabular-nums; white-space: nowrap; }
.stg-bars li { cursor: pointer; border-radius: 4px; padding: 2px 4px; margin: 0 -4px; }
.stg-bars li:focus-visible { outline: 2px solid var(--seq-3); }
.stage-view[data-cat] .stg-bars li:not(.cat-on) { opacity: 0.4; }
@media (min-width: 960px) { .stage-view { grid-template-columns: 400px minmax(0, 1fr); align-items: start; } }
@media (max-width: 959px) { .stage-view .seg-gl { height: auto; aspect-ratio: 1 / 1; min-height: 0; } }
</style>`;

export const STAGE_SCRIPT = `<script>
(function () {
  document.querySelectorAll(".stage-view").forEach(function (v) {
    var jobs = JSON.parse(v.querySelector("[data-jobs]").textContent);
    var pop = v.querySelector(".stg-pop"), wrap = v.querySelector(".stg-mapwrap"), box = v.querySelector(".mapbox");
    var on = false;
    // The map (segMap) draws a picked job's blocks on top and fades the rest.
    function close() {
      on = false;
      if (box.sfSeg) box.sfSeg.job(null);
      v.classList.remove("job-mode");
      pop.hidden = true;
    }
    // Beside the highlighted streets, on whichever side has room, so the
    // popover never covers what was picked.
    function place() {
      if (pop.hidden || !on || !box.sfSeg || window.matchMedia("(max-width: 959px)").matches) return;
      var wr = wrap.getBoundingClientRect(), mr = box.querySelector(".seg-gl").getBoundingClientRect(), b = box.sfSeg.box();
      if (!b) return;
      var dx = mr.left - wr.left, dy = mr.top - wr.top;
      b = { l: b.l + dx, r: b.r + dx, t: b.t + dy, b: b.b + dy };
      var W = wr.width, H = wr.height, w = pop.offsetWidth, h = pop.offsetHeight, g = 14, x, y;
      var room = { right: W - b.r - g, left: b.l - g, below: H - b.b - g, above: b.t - g };
      var side = ["right", "left", "below", "above"].filter(function (k) { return room[k] >= ((k === "right" || k === "left") ? w : h); })[0] || "right";
      if (side === "right") { x = b.r + g; y = (b.t + b.b) / 2 - h / 2; }
      else if (side === "left") { x = b.l - g - w; y = (b.t + b.b) / 2 - h / 2; }
      else if (side === "below") { y = b.b + g; x = (b.l + b.r) / 2 - w / 2; }
      else { y = b.t - g - h; x = (b.l + b.r) / 2 - w / 2; }
      pop.style.left = Math.max(4, Math.min(x, W - w - 4)) + "px";
      pop.style.top = Math.max(4, Math.min(y, H - h - 4)) + "px";
    }
    function open(slug) {
      var j = jobs[slug]; if (!j) return close();
      close();
      if (box.sfSeg) box.sfSeg.job(j.cnns);
      on = true;
      pop.querySelector("[data-pop-name]").textContent = j.name;
      pop.querySelector("[data-pop-brief]").textContent = j.brief;
      // The stage's own bars, for this job alone: same labels, same colours.
      var list = pop.querySelector("[data-pop-bars]"); list.textContent = "";
      var cats = ["met", "short", "already"], max = Math.max.apply(null, cats.map(function (c) { return j.bars[c] || 0; })) || 1;
      // Bryan, 2026-10-01: "Don't show categories with no miles."
      cats.filter(function (c) { return (j.bars[c] || 0).toFixed(1) !== "0.0"; }).forEach(function (c) {
        var src = v.querySelector('.stg-chart[data-stage="' + v.dataset.show + '"] li[data-cat="' + c + '"] .stg-cat');
        var li = document.createElement("li"), lab = document.createElement("span"), row = document.createElement("span"), bar = document.createElement("i"), val = document.createElement("b");
        lab.className = "stg-cat"; lab.textContent = src ? src.parentNode.dataset.long : c;
        row.className = "stg-row"; bar.className = c; bar.style.width = (100 * (j.bars[c] || 0) / max).toFixed(1) + "%";
        val.textContent = (j.bars[c] || 0).toFixed(1) + " mi";
        row.appendChild(bar); row.appendChild(val); li.appendChild(lab); li.appendChild(row); list.appendChild(li);
      });
      // What the plan calls for on each street, beside what it has now.
      var gap = pop.querySelector("[data-pop-gap]"); gap.textContent = "";
      var MAX = 8, rows = j.gap || [];
      rows.slice(0, MAX).forEach(function (r) {
        var li = document.createElement("li"), sw = document.createElement("i"), name = document.createElement("b"), mi = document.createElement("em"), what = document.createElement("span");
        sw.className = r.cat; name.textContent = r.street;
        mi.textContent = r.mi >= 0.1 ? r.mi.toFixed(1) + " mi" : Math.max(10, Math.round(r.mi * 5280 / 10) * 10) + " ft";
        what.textContent = "Plan calls for a " + r.wants + ". Has " + r.has + ".";
        li.appendChild(sw); li.appendChild(name); li.appendChild(mi); li.appendChild(what); gap.appendChild(li);
      });
      if (rows.length > MAX) { var more = document.createElement("li"); more.className = "more"; more.textContent = "and " + (rows.length - MAX) + " more streets"; gap.appendChild(more); }
      pop.querySelector(".pop-gap-h").hidden = gap.hidden = !rows.length;
      v.classList.add("job-mode");
      var links = pop.querySelector("[data-pop-links]"); links.textContent = "";
      j.links.forEach(function (l) { var a = document.createElement("a"); a.href = l.url; a.textContent = l.label; links.appendChild(a); });
      pop.hidden = false;
      place();
    }
    box.addEventListener("seg-pick", function (e) {
      var hit = e.detail;
      if (hit && hit.dataset.job) open(hit.dataset.job); else close();
    });
    pop.querySelector(".stg-pop-x").addEventListener("click", close);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    if (box.sfSeg) box.sfSeg.onMove(function () { requestAnimationFrame(place); });
    // A bar shows its blocks on the map: hover or focus previews, a tap pins.
    var pinned = null;
    function showCat(c) {
      if (c) v.dataset.cat = c; else delete v.dataset.cat;
      v.querySelectorAll(".stg-bars li").forEach(function (li) { li.classList.toggle("cat-on", li.dataset.cat === c); });
    }
    v.querySelectorAll(".stg-bars li").forEach(function (li) {
      li.addEventListener("mouseenter", function () { showCat(li.dataset.cat); });
      li.addEventListener("mouseleave", function () { showCat(pinned); });
      li.addEventListener("focus", function () { showCat(li.dataset.cat); });
      li.addEventListener("blur", function () { showCat(pinned); });
      function pin() { pinned = pinned === li.dataset.cat ? null : li.dataset.cat; showCat(pinned); }
      li.addEventListener("click", pin);
      li.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pin(); } });
    });
  });
})();
</script>`;

export function overlapVars() {
  const past = stageView("past"), next = stageView("next");
  const P = STAGES.past.miles, N = STAGES.next;
  const need = (m) => m.met + m.short;
  const s = O.summary;
  return {
    ovFeedUrl: O.sources.feed.url,
    ovFeedQueried: O.sources.feed.queried,
    pastOpen: STAGE_CSS + past.open,
    pastView: past.html,
    nextOpen: next.open,
    nextView: next.html,
    pastUnmapped: past.missing,
    nextUnmapped: next.missing ? `${next.missing} street segments aren't drawn because they couldn't be matched to the plan's map. ` : "",
    pastFromLong: monthYear(PAST_FROM),
    pastToLong: monthYear(O.compare[0].to),
    pastAlready: one(P.already),
    nextNeed: Math.round(need(N.miles)),
    nextGot: Math.round(N.miles.met),
    nowNeed: one(need(N.now)),
    nowPct: Math.round((100 * N.now.met) / need(N.now)),
    laterNeed: one(need(N.later)),
    laterPct: Math.round((100 * N.later.met) / need(N.later)),
    laterFrom: O.compare[2].buckets[0],
    cmpCould: Math.round(need(P) + need(N.miles)),
    cmpGot: Math.round(P.met + N.miles.met),
    cmpRepavedStreets: O.compare[0].gotStreets.join(" and "),
    cmpHorizonYear: O.horizon.slice(0, 4),
  };
}

// The page's sections moved to the overview's end on 2026-10-03 (Bryan: "Can
// you move coordination section into the main page? I think that's a better
// way to end the story."). This address keeps answering, as a redirect.
export const path = "/transportation/bike/departments";
export const file = "transportation/bike/departments/index.html";
export const redirect = "/transportation/bike";
export const render = () => redirectPage(redirect, "Improving The Bike Network");
