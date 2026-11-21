// The list of what's on the site, shown on the home page and on every page
// that has pages under it.
//
// Bryan, 2026-10-14: "Can you update the front page and directory pages to
// show a list of what's available cause the breadcrumbs are pretty well
// hidden".
//
// There is no list to keep. A page module that should be listed exports
//
//   export const listing = { title: "Current Repaving Projects", line: "One line about it." };
//
// and scripts/site-files.mjs gathers every such export from src/pages, drops
// the pages src/features.mjs hides on this build, and fills each page's
// DIRECTORY_MARK through fillDirectory. So a hidden page is listed on staging
// (SITE_SHOW_HIDDEN=1) and absent on sf-works.org, exactly as the page itself
// is. Redirects, embeds, About pages and per-project pages carry no listing.
//
// Where a page sits comes from its path unless its listing says otherwise.
// By default its parent is the longest listed path above it, or, failing
// that, its section's front page (layout.mjs, NAV). A listing can also set
//
//   parent: "/a/listed/path"   to sit under that page instead, or
//   parent: "section"          to sit beside the section's front page, as a
//                              top item of the section's list;
//   order: 2                   its place among its siblings, lower first
//                              (unset sorts after set, then by path);
//   views: [["comment", "The Public Comment"], ...]
//                              views of the page itself, listed as its
//                              children, each linking to path#id.
//
// A section's list starts with its front page, followed by the pages set
// beside it (Bryan, 2026-10-15: "BRP Overview should be the top item. Other
// bike plans is a subtopic. Current repaving is second subtopic of BRP. And
// then Safer School trips should have three subsections."). A section whose
// front page stands alone lists the pages under the front page directly, so
// its list doesn't repeat its own heading.
//
// The breadcrumb reads the same tree (fillCrumbs), so a page's steps below its
// section are the listed pages above it, and each step's menu is the pages
// listed beside it (Bryan, 2026-10-15: "why's there a different navigation
// structure on the front page vs the breadcrumbs?").

import { NAV, DIRECTORY_MARK, CRUMBS_MARK, menu, crumbItem } from "./layout.mjs";
import { esc } from "./html.mjs";
import { dateLine } from "./page-dates.mjs";

const top = (p) => String(p).split("/")[1] || "";
const sectionOf = (p) => NAV.find((n) => top(n.href) === top(p));
// The parent of a section's top items: its front page and the pages set beside it.
const sectionKey = (s) => `section:${s.href}`;

// Each entry's parent: a listed path, a section's key for a top item, or null
// for a page in no section.
export function parentOf(entry, entries) {
  const s = sectionOf(entry.path);
  if (s && s.href === entry.path) return sectionKey(s);
  if (entry.parent === "section") return s ? sectionKey(s) : null;
  // A parent hidden on this build falls back to the path rule, so its pages stay listed.
  if (entry.parent && entries.some((e) => e.path === entry.parent)) return entry.parent;
  const above = entries
    .filter((e) => e.path !== entry.path && entry.path.startsWith(`${e.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
  if (above) return above.path;
  if (!s || !entries.some((e) => e.path === s.href)) return null;
  return s.href;
}

// A listing marked `draft: true` is published but linked from nowhere outside
// its own pages (Bryan, 2026-11-19, on the Muni dashboard: "Live tonight,
// marked Draft with its data date, linked from nowhere else"). It stays in
// the lists and breadcrumbs of a page at or under a draft listing's path, and
// is left out of every other page's.
export function shownFor(entries, pagePath) {
  const inDraft = entries.some((d) => d.draft && (pagePath === d.path || String(pagePath).startsWith(`${d.path}/`)));
  return inDraft ? entries : entries.filter((e) => !e.draft);
}

// [{path, title, line, parent?, order?, views?}] sorted by path, so every
// build lists them in the same order.
export function normalise(entries) {
  return [...entries].sort((a, b) => a.path.localeCompare(b.path));
}

// The entries under one parent, in list order: a section's front page first,
// then by `order`, then by path.
function kidsOf(parent, entries) {
  const rank = (e) => (sectionOf(e.path)?.href === e.path ? -Infinity : e.order ?? Infinity);
  return entries
    .filter((e) => parentOf(e, entries) === parent)
    .sort((a, b) => (rank(a) === rank(b) ? a.path.localeCompare(b.path) : rank(a) < rank(b) ? -1 : 1));
}

// What a section's list hangs from: its top items, or, when its front page
// stands alone, the pages under the front page.
function sectionList(s, entries) {
  const tops = kidsOf(sectionKey(s), entries);
  return tops.length === 1 && tops[0].path === s.href ? s.href : sectionKey(s);
}

// A <ul> of list items, or "" for none.
const ul = (items) => (items.length ? `<ul class="dir-list">\n${items.join("\n")}\n</ul>` : "");

// The list under `parent`; `current` is the page showing it, marked in the list.
function list(parent, entries, current) {
  return ul(kidsOf(parent, entries).map((e) => item(e, entries, current)));
}

// One page's list item: its link and line, the date its data was read or it
// last changed (src/page-dates.mjs; Bryan, 2026-11-20: "each page and dashboard
// shows when it was last published or updated in the directory pages"), then
// the pages under it and its own views.
function item(e, entries, current) {
  const under = ul([
    ...kidsOf(e.path, entries).map((k) => item(k, entries, current)),
    ...(e.views || []).map(([id, label]) => `<li><a href="${e.path}#${esc(id)}">${esc(label)}</a></li>`),
  ]);
  const here = e.path === current ? ' aria-current="page"' : "";
  return `<li><a href="${e.path}"${here}>${esc(e.title)}</a>${e.line ? `<span class="dir-line">${esc(e.line)}</span>` : ""}${e.date ? dateLine(e.date) : ""}${under}</li>`;
}

/**
 * The page's HTML with DIRECTORY_MARK replaced by the list of pages under it.
 * A section's front page lists its whole section, itself first and marked.
 *
 * On the home page each section's list goes under the heading that links to
 * the section's front page (content/home.md), after the paragraph that
 * describes it. A section whose heading isn't there gets its own heading at
 * the mark instead, so editing the home page's prose can't drop a page from it.
 */
export function fillDirectory(html, pagePath, entries) {
  if (!html.includes(DIRECTORY_MARK)) return html;
  const all = normalise(shownFor(entries, pagePath));
  if (pagePath !== "/") {
    const s = sectionOf(pagePath);
    const front = s && s.href === pagePath;
    const items = front ? list(sectionList(s, all), all, pagePath) : list(pagePath, all, pagePath);
    if (!items) return html.replace(DIRECTORY_MARK, "");
    const self = all.find((e) => e.path === pagePath);
    const heading = front ? `More In ${s.label}` : `More On ${self ? self.title : "This Page"}`;
    return html.replace(DIRECTORY_MARK, `<nav class="dir" aria-label="${esc(heading)}">
<h2>${esc(heading)}</h2>
${items}
</nav>`);
  }
  let out = html;
  const leftover = [];
  for (const s of NAV) {
    const items = list(sectionList(s, all), all);
    const front = all.find((e) => e.path === s.href);
    // The heading that links to this section, and the paragraph under it. The
    // heading carries an id for its anchor link, so it may have attributes.
    const at = new RegExp(`(<h\\d[^>]*><a href="${s.href.replace(/[/]/g, "\\/")}"[\\s\\S]*?</h\\d>\\s*<p>[\\s\\S]*?</p>)`);
    if (at.test(out)) {
      if (items) out = out.replace(at, `$1\n<nav class="dir dir-under" aria-label="${esc(s.label)}">${items}</nav>`);
      // A section whose front page is itself a listed report (Homes, Permits) is dated under its paragraph (put in after the list, so it lands above it).
      if (front && front.date) out = out.replace(at, `$1\n<p class="dir-dated">${dateLine(front.date)}</p>`);
    } else if (front || items) {
      leftover.push(`<h3><a href="${s.href}">${esc(front ? front.title : s.label)}</a></h3>
${front && front.line ? `<p>${esc(front.line)}</p>\n` : ""}${front && front.date ? `<p class="dir-dated">${dateLine(front.date)}</p>\n` : ""}${items ? `<nav class="dir" aria-label="${esc(s.label)}">${items}</nav>` : ""}`);
    }
  }
  return out.replace(DIRECTORY_MARK, leftover.join("\n"));
}

/**
 * The page's HTML with CRUMBS_MARK replaced by the breadcrumb's steps between
 * the section and the view: the listed pages from the top of the section's
 * list down to this one. A page with no listing of its own (an About page, a
 * per-project page) takes the steps of the nearest listed page above it. A
 * step with listed siblings opens a menu of them, as the section step does.
 * A section's front page is a step of its own only when the section's list
 * has other top items beside it; otherwise the section step already is it.
 */
export function fillCrumbs(html, entries) {
  const m = html.match(CRUMBS_MARK);
  if (!m) return html;
  const pagePath = m[1];
  const all = normalise(shownFor(entries, pagePath));
  const here = all
    .filter((e) => e.path === pagePath || pagePath.startsWith(`${e.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
  const chain = [];
  for (let e = here; e; ) {
    const parent = parentOf(e, all);
    const s = sectionOf(e.path);
    if (parent && s && parent === sectionKey(s)) {
      if (sectionList(s, all) === parent) chain.unshift([e, parent]);
      break;
    }
    chain.unshift([e, parent]);
    e = parent && all.find((x) => x.path === parent);
  }
  // A tool with its own pages (a listing's `pages`, as [path, label, aliases?]) ends the trail at
  // the tool, then one menu of those pages, named for the one shown. That menu is the tool's only
  // navigation row (Bryan, 2026-11-16: "Can we just have the top breadcrumbs and keep that as
  // standard practice"). A page matches its own path, an alias, or anything under either.
  const tool = chain.findIndex(([e]) => e.pages);
  let pagesStep = null;
  if (tool >= 0) {
    const { pages } = chain[tool][0];
    chain.length = tool + 1;
    const under = (p) => pagePath === p || pagePath.startsWith(`${p}/`);
    const len = ([p, , alias = []]) => Math.max(-1, ...[p, ...alias].filter(under).map((x) => x.length));
    const cur = pages.reduce((a, b) => (len(b) > len(a) ? b : a));
    pagesStep = menu(cur[1], pages.map((x) => [x[0], x[1], x === cur]));
  }
  // A listing's `crumb` is a shorter name for its own step; its menu entry keeps the title.
  const steps = chain.map(([e, parent]) => {
    const sibs = parent === null ? [e] : kidsOf(parent, all);
    return sibs.length > 1
      ? menu(e.crumb || e.title, sibs.map((x) => [x.path, x.title, x === e]))
      : `<sl-breadcrumb-item href="${e.path}">${esc(e.crumb || e.title)}</sl-breadcrumb-item>`;
  });
  if (pagesStep) steps.push(pagesStep);
  return html.replace(CRUMBS_MARK, steps.map(crumbItem).join(""));
}
