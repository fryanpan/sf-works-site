#!/usr/bin/env node
// Deploy the site's markdown pages, board .mdx docs among them, the way fryanpan.com deploys its posts: build, look
// at the rendered pages, push. Bryan, 2026-11-17 (docs/decisions/site.md): "There should be a deploy script that
// deploys simply like on fryanpan.com".
//
//   npm run deploy-docs                 refresh figures, check, build, check the rendered pages
//   npm run deploy-docs -- --push       then commit the pages and figures on a branch and merge them through a PR
//
// Steps, each stopping the run on failure:
//   1. Figures. Every `::scratch{block="<name>"}` in a page this build will publish needs the site's copy of that
//      figure page, data/embeds/<name>.html (src/doc-embeds.mjs). Where the board's own copy,
//      scratch/embeds/<name>/index.html at the repo root, exists and differs, it is copied over, so the site shows
//      the figure the board shows. A block with neither copy stops the run.
//   2. npm run check, the checks `npm run deploy` runs (nothing private reached site/, figures, tests).
//   3. npm run build, as production builds: SITE_SHOW_HIDDEN, SITE_BASE_PATH and the comment widget's settings are
//      cleared first, so a shell left set up for the dev server or staging cannot put drafts or a path prefix in.
//   4. site/scripts/check-rendered-docs.mjs at the repo root: each markdown page in the build, in headless Chrome.
//   5. With --push: the changed files under content/ and data/embeds/ are committed by name on a new branch,
//      pushed, and merged through a PR (squash, auto-merge once its checks pass). The merge is the deploy:
//      .github/workflows/deploy.yml builds main with the production keys, runs the same rendered check and pushes to
//      Cloudflare. A hand `wrangler deploy` is not used, since it would ship without those keys and the next merge
//      would undo it.

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

for (const k of Object.keys(process.env)) if (k === "SITE_SHOW_HIDDEN" || k === "SITE_BASE_PATH" || k.startsWith("WIDGET_")) delete process.env[k];

const { loadPages } = await import("../src/md-pages.mjs");
const { EMBEDS } = await import("../src/doc-embeds.mjs");

const SITE = path.resolve(import.meta.dirname, "..");
const REPO = path.dirname(SITE);
const BOARD_EMBEDS = path.join(REPO, "scratch", "embeds");
const push = process.argv.includes("--push");
const run = (cmd, args, cwd = SITE) => {
  console.log(`\n$ ${cmd} ${args.join(" ")}`);
  execFileSync(cmd, args, { cwd, stdio: "inherit" });
};
const out = (cmd, args, cwd = SITE) => execFileSync(cmd, args, { cwd, encoding: "utf8" }).trim();

// 1. Figures.
const SCRATCH = /^::scratch\{block="([\w-]+)"\}[ \t]*$/gm;
const blocks = new Set();
for (const p of loadPages()) if (p.status !== "teaser") for (const m of p.body.matchAll(SCRATCH)) blocks.add(m[1]);
const missing = [];
for (const b of [...blocks].sort()) {
  const board = path.join(BOARD_EMBEDS, b, "index.html");
  const site = path.join(EMBEDS, `${b}.html`);
  if (fs.existsSync(board)) {
    const html = fs.readFileSync(board);
    if (!fs.existsSync(site) || !html.equals(fs.readFileSync(site))) {
      fs.mkdirSync(EMBEDS, { recursive: true });
      fs.writeFileSync(site, html);
      console.log(`figure ${b}: copied from the board's scratch/embeds/${b}/`);
    } else console.log(`figure ${b}: up to date`);
  } else if (fs.existsSync(site)) console.log(`figure ${b}: no board copy here, keeping data/embeds/${b}.html`);
  else missing.push(b);
}
if (missing.length) {
  console.error(`deploy-docs: no figure page for ${missing.map((b) => `::scratch{block="${b}"}`).join(", ")}; run its generator (scripts/neighborhood-maps-embed.py or scripts/intro-trends-embed.py)`);
  process.exit(1);
}

// 2 to 4.
run("npm", ["run", "check"]);
run("npm", ["run", "build"]);
run("node", [path.join(SITE, "scripts", "check-rendered-docs.mjs")], REPO);

// 5.
const changed = out("git", ["status", "--porcelain", "--untracked-files=all", "--", "content", "data/embeds"])
  .split("\n").filter(Boolean).map((l) => l.slice(3).replace(/^.* -> /, ""));
if (!changed.length) {
  console.log("\ndeploy-docs: nothing under content/ or data/embeds/ differs from the last commit; main's next deploy already carries it");
  process.exit(0);
}
if (!push) {
  console.log(`\ndeploy-docs: checks passed. To deploy, run again with --push, which merges these through a PR:\n  ${changed.join("\n  ")}`);
  process.exit(0);
}
// --porcelain paths are relative to the repository root.
const files = changed;
const branch = `deploy-docs-${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}`;
run("git", ["switch", "-c", branch], REPO);
run("git", ["add", "--", ...files], REPO);
run("git", ["commit", "-m", `Publish site pages: ${files.filter((f) => /\.mdx?$/.test(f)).map((f) => path.basename(f)).join(", ") || "figures"}`], REPO);
run("git", ["push", "-u", "origin", branch], REPO);
run("gh", ["pr", "create", "--fill", "--base", "main"], REPO);
run("gh", ["pr", "merge", "--squash", "--auto", "--delete-branch"], REPO);
console.log("\ndeploy-docs: the PR merges once its checks pass, and the merge deploys sf-works.org (.github/workflows/deploy.yml)");
