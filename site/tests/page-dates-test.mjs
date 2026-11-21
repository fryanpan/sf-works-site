#!/usr/bin/env node
// Tests the date beside each page in the site's lists (site/src/page-dates.mjs): the data date wins and is the
// newest of a page's dates, a page with none takes its source files' last commit, a clone git can't date falls
// back to the tracked copy, a listed page with no date stops the build, and every list prints one format.
//
//   node site/tests/page-dates-test.mjs
//
// The git cases run in a throwaway repository under the OS temp directory, so the dates are commits made here.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

import { ROOT } from "../scripts/lib/repo.mjs";
const D = await import(path.join(ROOT, "site", "src", "page-dates.mjs"));
const { fillDirectory } = await import(path.join(ROOT, "site", "src", "directory.mjs"));
const { DIRECTORY_MARK } = await import(path.join(ROOT, "site", "src", "layout.mjs"));

// ---- the format ----
assert.equal(D.shortDate("2026-11-20"), "Nov 20, 2026");
assert.equal(D.shortDate("2026-01-05"), "Jan 5, 2026");
assert.equal(D.newestDate(["2026-11-09", null, "2026-11-12T08:00:00Z", undefined]), "2026-11-12");
assert.equal(D.newestDate(null), "");
assert.equal(D.newestDate("9 November 2026"), "", "a date that isn't ISO is no date");

// ---- the resolver ----
const none = () => "";
// a data date wins over the commit date, and git isn't asked
assert.deepEqual(
  D.resolveDate({ path: "/a", dataUpdated: ["2026-11-01", "2026-11-09"], files: ["x"] }, { gitDate: () => assert.fail("git asked"), fallback: {} }),
  { label: "Data updated", date: "2026-11-09" });
// no data date: the last commit to the page's files
assert.deepEqual(D.resolveDate({ path: "/a", files: ["x"] }, { gitDate: () => "2026-10-02", fallback: { "/a": "2026-01-01" } }), { label: "Updated", date: "2026-10-02" });
// git can't say (a shallow clone): the tracked copy
assert.deepEqual(D.resolveDate({ path: "/a", files: ["x"] }, { gitDate: none, fallback: { "/a": "2026-01-01" } }), { label: "Updated", date: "2026-01-01" });
// nothing dates it
assert.equal(D.resolveDate({ path: "/a", files: ["x"] }, { gitDate: none, fallback: {} }), null);
assert.equal(D.resolveDate({ path: "/a", files: ["x"] }, { gitDate: none, fallback: { "/a": "soon" } }), null);

// ---- git: the newest commit to any of the page's files; a shallow clone gives nothing ----
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "page-dates-test-"));
process.on("exit", () => fs.rmSync(tmp, { recursive: true, force: true }));
const repo = path.join(tmp, "repo");
fs.mkdirSync(repo);
const run = (args, cwd, date) => execFileSync("git", args, { cwd, stdio: ["ignore", "pipe", "ignore"], env: { ...process.env, ...(date ? { GIT_AUTHOR_DATE: date, GIT_COMMITTER_DATE: date } : {}), GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@example.com", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@example.com" } });
run(["init", "-q"], repo);
const commit = (file, date) => { fs.writeFileSync(path.join(repo, file), date); run(["add", file], repo); run(["commit", "-q", "-m", "x"], repo, `${date}T12:00:00`); };
commit("imported.mjs", "2026-08-01");
commit("page.mjs", "2026-09-01");
commit("prose.md", "2026-10-15");
commit("other.mjs", "2026-11-02");
assert.equal(D.gitDate(["page.mjs"], repo), "2026-09-01");
assert.equal(D.gitDate(["page.mjs", "prose.md"], repo), "2026-10-15", "the newest of the page's files, not of the repository");
assert.equal(D.gitDate(["uncommitted.mjs"], repo), "", "a file with no commit has no date");
assert.equal(D.gitDate(["imported.mjs"], repo), "", "the repo's first commit is the import, whose date is not the page's");
assert.deepEqual(D.resolveDate({ path: "/i", files: ["imported.mjs"] }, { gitDate: (f) => D.gitDate(f, repo), fallback: { "/i": "2026-07-04" } }), { label: "Updated", date: "2026-07-04" });
assert.equal(D.gitDate(["page.mjs"], tmp), "", "outside a repository git has no date");
// the same answer twice: a build with no new commit prints the same date
assert.equal(D.gitDate(["page.mjs", "prose.md"], repo), D.gitDate(["page.mjs", "prose.md"], repo));
const shallow = path.join(tmp, "shallow");
run(["clone", "-q", "--depth", "1", `file://${repo}`, shallow], tmp);
assert.equal(D.gitDate(["page.mjs"], shallow), "", "a shallow clone would date every page by its one commit");
assert.deepEqual(D.resolveDate({ path: "/p", files: ["page.mjs"] }, { gitDate: (f) => D.gitDate(f, shallow), fallback: { "/p": "2026-09-01" } }), { label: "Updated", date: "2026-09-01" });

// ---- the missing-date check ----
const dated = { path: "/transportation/a", title: "A", line: "", date: { label: "Updated", date: "2026-11-02" } };
assert.doesNotThrow(() => D.checkDates([dated]));
assert.throws(() => D.checkDates([dated, { path: "/transportation/b", title: "B", line: "" }]), /1 listed page\(s\) with no date: \/transportation\/b/);
assert.throws(() => D.checkDates([{ path: "/transportation/c", date: { label: "Updated", date: "" } }]), /\/transportation\/c/);

// ---- the line and the marks ----
assert.equal(D.dateLine({ label: "Data updated", date: "2026-11-09" }), '<span class="dir-date">Data updated <time datetime="2026-11-09">Nov 9, 2026</time></span>');
assert.equal(D.fillDates(`<li>${D.dateMark("/transportation/a")}</li>`, [dated]), '<li><span class="dir-date">Updated <time datetime="2026-11-02">Nov 2, 2026</time></span></li>');
assert.throws(() => D.fillDates(D.dateMark("/transportation/zzz"), [dated]), /a list shows \/transportation\/zzz, which has no date/);
assert.equal(D.fillDates("<p>no marks</p>", []), "<p>no marks</p>");

// ---- every list item src/directory.mjs writes carries its page's date ----
const entries = [
  { path: "/transportation/bike", title: "Bike", line: "Line.", parent: "section", date: { label: "Data updated", date: "2026-11-12" } },
  { path: "/transportation/bike/projects", title: "Projects", line: "Line.", date: { label: "Updated", date: "2026-10-30" } },
];
const html = fillDirectory(`<h3><a href="/transportation">Mobility</a></h3>\n<p>About.</p>\n${DIRECTORY_MARK}`, "/", entries);
const items = html.match(/<li>/g).length;
assert.equal(items, 2);
assert.equal(html.match(/class="dir-date"/g).length, items, "one date for each listed page");
assert.ok(html.includes("Data updated <time datetime=\"2026-11-12\">Nov 12, 2026</time>"));
assert.ok(html.includes("Updated <time datetime=\"2026-10-30\">Oct 30, 2026</time>"));

console.log("page-dates-test: ok");
