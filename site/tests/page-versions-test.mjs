#!/usr/bin/env node
// Tests folder pages' published versions: new-version, the /v/<n> pages, the version line and the check.
//
// Covers site/src/page-versions.mjs, site/scripts/new-version.mjs, site/scripts/check-versions.mjs and
// the folder-page half of site/src/md-pages.mjs. Builds a whitepaper folder page under the OS temp
// directory, publishes two versions of it, and shows each renders from its own copy; then deletes and
// edits a published version and shows the check fails on each.
//
//   node site/tests/page-versions-test.mjs
//
// Part of `npm run check` in site/.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { ROOT } from "../scripts/lib/repo.mjs";
const { loadPages, mdPageFiles, recentChanges } = await import(path.join(ROOT, "site", "src", "md-pages.mjs"));
const { newVersion } = await import(path.join(ROOT, "site", "scripts", "new-version.mjs"));
const { checkVersions } = await import(path.join(ROOT, "site", "scripts", "check-versions.mjs"));

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "page-versions-test-"));
process.on("exit", () => fs.rmSync(tmp, { recursive: true, force: true }));
let passed = 0;
const test = (name, fn) => {
  fn();
  passed++;
  console.log(`  ok  ${name}`);
};

const content = path.join(tmp, "content");
const folder = path.join(content, "transportation", "whitepaper");
const put = (rel, body) => {
  fs.mkdirSync(path.dirname(path.join(folder, rel)), { recursive: true });
  fs.writeFileSync(path.join(folder, rel), body);
};
const pageText = (words) => `---\ntitle: Whitepaper\nstatus: published\n---\n\n${words}\n\n![A figure](images/fig.png)\n\n::scratch{block="hin-map"}\n`;
const html = (files, p) => files.find((f) => f.path === p)?.html;

put("page.mdx", pageText("First draft."));
put("images/fig.png", Buffer.from([137, 80, 78, 71, 1]));
put("embeds/hin-map.html", "<!doctype html><p>map as of version 1</p>");

test("new-version copies the folder, minus versions/, and records it", () => {
  const v = newVersion(folder, { date: "2026-11-02", commit: "a".repeat(40) });
  assert.deepEqual({ n: v.n, date: v.date }, { n: 1, date: "2026-11-02" });
  assert.match(v.hash, /^sha256:[0-9a-f]{64}$/);
  assert.deepEqual(fs.readdirSync(path.join(folder, "versions", "1")).sort(), ["embeds", "images", "page.mdx"]);
  const json = JSON.parse(fs.readFileSync(path.join(folder, "versions", "versions.json"), "utf8"));
  assert.deepEqual(json.versions.map((x) => x.n), [1]);
});

test("the next version copies the edited folder and never the earlier copies", () => {
  put("page.mdx", pageText("Second draft, with a new paragraph."));
  put("images/fig.png", Buffer.from([137, 80, 78, 71, 2]));
  put("embeds/hin-map.html", "<!doctype html><p>map as of version 2</p>");
  const v = newVersion(folder, { date: "2026-11-18", commit: "b".repeat(40) });
  assert.equal(v.n, 2);
  assert.ok(!fs.existsSync(path.join(folder, "versions", "2", "versions")), "no nesting");
  assert.throws(() => newVersion(folder, { date: "2026-11-01", commit: "c".repeat(40) }), /before version 2's date/);
});

const pages = loadPages({ dir: content, showDrafts: false });
const files = mdPageFiles(pages, {});

test("the latest is at the folder's address, and each version at /v/<n>", () => {
  assert.deepEqual(pages.map((p) => p.path), ["/transportation/whitepaper", "/transportation/whitepaper/v/1", "/transportation/whitepaper/v/2"]);
  assert.ok(!files.some((f) => f.path.includes("/versions/1/page")), "the copies are not pages of their own");
});

test("the latest page carries the version line from versions.json", () => {
  const latest = html(files, "/transportation/whitepaper");
  assert.match(latest, /Last updated <time datetime="2026-11-18">18 November 2026<\/time>\. Version 2\. See the <a href="\/transportation\/whitepaper\/v\/">revision history<\/a>\./);
  assert.match(latest, /Second draft/);
  assert.doesNotMatch(latest, />Updated </);
});

test("an older version renders from its own copy: its text, its image, its figure page", () => {
  const v1 = html(files, "/transportation/whitepaper/v/1");
  assert.match(v1, /First draft\./);
  assert.doesNotMatch(v1, /Second draft/);
  assert.match(v1, /This is an older version\. See the <a href="\/transportation\/whitepaper">latest version<\/a>/);
  assert.match(v1, /src="\/transportation\/whitepaper\/versions\/1\/images\/fig\.png"/);
  assert.match(v1, /<iframe class="md-embed" src="\/transportation\/whitepaper\/versions\/1\/embeds\/hin-map\/\?block=hin-map"/);
  const img = files.find((f) => f.file === "transportation/whitepaper/versions/1/images/fig.png");
  assert.deepEqual([...img.html], [137, 80, 78, 71, 1]);
  const map = files.find((f) => f.file === "transportation/whitepaper/versions/1/embeds/hin-map/index.html");
  assert.match(map.html.toString(), /map as of version 1/);
  assert.match(html(files, "/transportation/whitepaper/v/2"), /This is the latest version/);
});

test("the revision history lists every version, newest first", () => {
  const h = html(files, "/transportation/whitepaper/v");
  assert.match(h, /<a href="\/transportation\/whitepaper\/v\/2">Version 2<\/a>, 18 November 2026 \(the latest[^]*<a href="\/transportation\/whitepaper\/v\/1">Version 1<\/a>, 2 November 2026/);
  assert.equal(files.find((f) => f.path === "/transportation/whitepaper/v/1").sitemap, false);
  assert.doesNotMatch(recentChanges(pages), /\/v\/1/);
});

// The built half of the check reads a dist/ folder; write the pages the build would.
const dist = path.join(tmp, "dist");
for (const f of files) {
  fs.mkdirSync(path.dirname(path.join(dist, f.file)), { recursive: true });
  fs.writeFileSync(path.join(dist, f.file), f.html);
}

test("the check passes on intact versions and a full build", () => {
  const r = checkVersions({ content, dist });
  assert.deepEqual(r.problems, []);
  assert.equal(r.count, 2);
});

test("the check fails on a deleted version folder", () => {
  const v1 = path.join(folder, "versions", "1");
  fs.renameSync(v1, `${v1}.gone`);
  assert.match(checkVersions({ content }).problems.join("\n"), /version 1 is published but versions\/1\/ is gone/);
  assert.throws(() => loadPages({ dir: content, showDrafts: false }), /version 1 is in versions\.json but versions\/1\/ has no page/);
  fs.renameSync(`${v1}.gone`, v1);
});

test("the check fails on an edited version, and on an added or removed file in one", () => {
  const f = path.join(folder, "versions", "1", "page.mdx");
  const saved = fs.readFileSync(f);
  fs.writeFileSync(f, Buffer.concat([saved, Buffer.from("A quiet fix.\n")]));
  assert.match(checkVersions({ content }).problems.join("\n"), /versions\/1\/ was edited after it was published/);
  fs.writeFileSync(f, saved);
  fs.writeFileSync(path.join(folder, "versions", "1", "extra.json"), "{}");
  assert.match(checkVersions({ content }).problems.join("\n"), /versions\/1\/ was edited/);
  fs.rmSync(path.join(folder, "versions", "1", "extra.json"));
  assert.deepEqual(checkVersions({ content }).problems, []);
});

test("the check fails on a version folder versions.json does not list, and on a missing built page", () => {
  fs.mkdirSync(path.join(folder, "versions", "3"));
  assert.match(checkVersions({ content }).problems.join("\n"), /versions\/3\/ is not in versions\.json/);
  fs.rmSync(path.join(folder, "versions", "3"), { recursive: true });
  fs.rmSync(path.join(dist, "transportation", "whitepaper", "v", "2"), { recursive: true });
  assert.match(checkVersions({ content, dist }).problems.join("\n"), /the build has no page at \/transportation\/whitepaper\/v\/2\//);
});

test("a page is dated by its latest version, and an unpublished edit is noted, not failed", () => {
  const latest = pages.find((p) => p.path === "/transportation/whitepaper");
  assert.equal(latest.updated, "2026-11-18");
  assert.match(recentChanges(pages), /Updated <time datetime="2026-11-18">Nov 18, 2026<\/time>/);
  const dist2 = checkVersions({ content });
  assert.deepEqual(dist2.notices, []);
  const f = path.join(folder, "page.mdx");
  const saved = fs.readFileSync(f);
  fs.writeFileSync(f, Buffer.concat([saved, Buffer.from("A later edit.\n")]));
  const r = checkVersions({ content });
  assert.deepEqual(r.problems, []);
  assert.match(r.notices.join("\n"), /edited since version 2; run `npm run new-version -- transportation\/whitepaper`/);
  fs.writeFileSync(f, saved);
});

test("dotfiles are never copied or hashed, so a .DS_Store cannot fail the check", () => {
  fs.writeFileSync(path.join(folder, "versions", "1", ".DS_Store"), "finder");
  assert.deepEqual(checkVersions({ content }).problems, []);
  fs.rmSync(path.join(folder, "versions", "1", ".DS_Store"));
});

test("new-version refuses a draft", () => {
  const d = path.join(content, "drafty");
  fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, "page.md"), "---\ntitle: D\nstatus: draft\n---\n\nx\n");
  assert.throws(() => newVersion(d, { commit: "e".repeat(40) }), /is a draft/);
  fs.rmSync(d, { recursive: true });
});

test("new-version never writes over a published version's folder", () => {
  const json = path.join(folder, "versions", "versions.json");
  const saved = fs.readFileSync(json);
  const v = JSON.parse(saved);
  v.versions.pop();
  fs.writeFileSync(json, JSON.stringify(v));
  assert.throws(() => newVersion(folder, { commit: "d".repeat(40) }), /versions\/2 already exists/);
  fs.writeFileSync(json, saved);
});

console.log(`page-versions-test: ${passed} passed`);
