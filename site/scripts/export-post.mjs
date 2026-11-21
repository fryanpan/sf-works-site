#!/usr/bin/env node
// Write a post's export bundle for fryanpan.com: the post's markdown, and for
// each ::sfworks{block="<name>"} line in it the block's pre-rendered markup, an
// ES module that makes it interactive, and the finished data that module
// reads, with one stylesheet scoped under .sfw. fryanpan.com renders these
// natively and runs none of our pipelines (Bryan, 2026-10-05: "a markdown of
// the blog post, code for interactive elements, and some finished data").
//
//   node scripts/export-post.mjs sf-bike-network      # writes export/sf-bike-network/
//   node scripts/export-post.mjs sf-bike-network --check   # exits 1 if out of date
//
// The pieces come from src/bike-blocks.mjs, which also builds the
// /embed/bike/<block>/ pages from them, so the two cannot differ. The output
// is deterministic: no run stamps, sorted file list, and the manifest's date is
// the newest date the data was read, so a rerun with no new data changes
// nothing. content/posts/<post>.md is bound to a board doc that Bryan edits;
// this only reads it.
//
// The Google basemap key is a build secret written only into dist/, never into
// a tracked file, so it is unset here before anything reads it: the bundle's
// maps use the keyless OpenFreeMap basemap. (The key is restricted to
// sf-works.org by referrer, so it would not draw on fryanpan.com anyway.)

delete process.env.GOOGLE_MAPS_KEY;

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const args = process.argv.slice(2);
const slug = args.find((a) => !a.startsWith("--"));
const check = args.includes("--check");
if (!slug) {
  console.error("usage: node scripts/export-post.mjs <post> [--check]");
  process.exit(2);
}

const { BLOCKS, parts, postCredits, sfwCss } = await import("../src/bike-blocks.mjs");
const { history } = await import("../src/bike-history.mjs");
const { overlapVars } = await import("../src/pages/transportation-departments.mjs");
const { officialPhotos } = await import("../src/contact-officials.mjs");

const src = path.join(ROOT, "content", "posts", `${slug}.md`);
const post = fs.readFileSync(src, "utf8");
// The post's own dashboard: line wins, so a post about another tool links to that tool.
const DASHBOARD = (/^dashboard:\s*(\S+)\s*$/m.exec(post.split(/^---$/m)[1] || "") || [])[1] || "https://sf-works.org/transportation/bike/";
const title = (/^title:\s*"?(.*?)"?\s*$/m.exec(post.split(/^---$/m)[1] || "") || [])[1] || slug;

const used = [...post.matchAll(/^::sfworks\{block="([\w-]+)"\}\s*$/gm)].map((m) => m[1]);
const unknown = used.filter((b) => !BLOCKS.includes(b));
if (unknown.length) {
  console.error(`export-post: ${slug} uses blocks that don't exist: ${unknown.join(", ")}`);
  process.exit(1);
}
const blocks = [...new Set(used)];

// The newest date any of the blocks' data was read, as the sources record it.
const ov = overlapVars();
const dates = [history.sources.network.queried, ov.ovFeedQueried]
  .filter(Boolean)
  .map((d) => String(d).slice(0, 10))
  .sort();
const dataRead = dates[dates.length - 1];

// The blocks carry no credits of their own (Bryan, 2026-10-06: "Put the photo
// and data credits at the bottom of the page and remove it from the
// diagrams"), so the exported post ends with one section gathering them all.
// The post Bryan edits is left as it is; only its exported copy gains it.
// A post with no figures (the SSC comment) gets no credits section, which would only point at maps it lacks.
const files = { "post.md": `${post.replace(/\s*$/, "")}\n${blocks.length ? `\n${postCredits(blocks)}` : ""}`, "sfw.css": sfwCss() };
const NO_SNAPSHOT = new Set(["contact-officials"]);
const manifest = { post: slug, title, dashboard: DASHBOARD, dataRead, stylesheet: "sfw.css", blocks: [] };
for (const b of blocks) {
  const p = parts(b);
  const entry = { name: b, html: `blocks/${b}.html`, embed: `https://sf-works.org/embed/bike/${b}/` };
  files[entry.html] = p.html + "\n";
  if (p.js) {
    entry.module = `blocks/${b}.js`;
    entry.data = `data/${b}.json`;
    files[entry.module] = p.js;
    files[entry.data] = JSON.stringify(p.data) + "\n";
  }
  // A form has no data date, so fryanpan.com shows no "Data as of" note under it.
  if (NO_SNAPSHOT.has(b)) entry.snapshot = false;
  manifest.blocks.push(entry);
}
files["manifest.json"] = JSON.stringify(manifest, null, 2) + "\n";

// Bryan, 2026-10-07: "I want to make sure we snapshot a copy and serve it from
// fryanpan.com". The blocks point every link and photo at https://sf-works.org
// (bike-blocks.mjs), which is right for links, but a photo there would still
// load from sf-works.org. So each sf-works.org photo the bundle shows is copied
// into it and its address rewritten to fryanpan.com's copy, at
// /sfworks/<post>/, where import-sfworks.mjs puts the bundle.
const PHOTOS = new Map(officialPhotos().map((ph) => [`https://sf-works.org${ph.path}`, ph]));
const shown = new Set();
for (const [f, text] of Object.entries(files)) {
  files[f] = text.replace(/https:\/\/sf-works\.org\/photos\/[\w./-]+?\.(?:jpe?g|png|webp)/g, (u) => {
    const ph = PHOTOS.get(u);
    if (!ph) {
      console.error(`export-post: ${f} shows ${u}, which the bundle has no copy of`);
      process.exit(1);
    }
    shown.add(ph);
    return `/sfworks/${slug}/${ph.file}`;
  });
}
for (const ph of shown) files[ph.file] = ph.bytes;

// Nothing secret, and nothing that reads as a run stamp, may reach a tracked file.
for (const [f, text] of Object.entries(files)) {
  if (typeof text === "string" && /AIza[0-9A-Za-z_-]{20,}/.test(text)) {
    console.error(`export-post: ${f} carries what looks like a Google API key`);
    process.exit(1);
  }
}

const OUT = path.join(ROOT, "export", slug);
const want = new Map(Object.entries(files).map(([f, t]) => [path.join(OUT, f), t]));
const have = fs.existsSync(OUT)
  ? fs.readdirSync(OUT, { recursive: true }).map((f) => path.join(OUT, f)).filter((f) => fs.statSync(f).isFile())
  : [];
const stale = have.filter((f) => !want.has(f));
const same = (f, t) => fs.existsSync(f) && Buffer.from(t).equals(fs.readFileSync(f));
const changed = [...want].filter(([f, t]) => !same(f, t)).map(([f]) => f);

if (check) {
  if (stale.length || changed.length) {
    for (const f of [...changed, ...stale]) console.error(`export-post: out of date: ${path.relative(ROOT, f)}`);
    process.exit(1);
  }
  console.log(`export-post: export/${slug}/ is current`);
  process.exit(0);
}

for (const f of stale) fs.rmSync(f);
for (const f of changed) {
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, want.get(f));
}
const kb = (t) => (Buffer.byteLength(t) / 1024).toFixed(0);
for (const [f, t] of Object.entries(files).sort()) console.log(`  ${f}  ${kb(t)} kB`);
console.log(`export-post: ${changed.length} written, ${stale.length} removed, into export/${slug}/`);
