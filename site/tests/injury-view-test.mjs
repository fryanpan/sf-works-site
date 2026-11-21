#!/usr/bin/env node
// Tests that the injury map's address reopens what the reader was looking at, above all that a URL with a school
// opens that school's view (Bryan, 2026-10-21: "share a link around for what you're looking at").
//
//   node site/tests/injury-view-test.mjs                    # the view functions, the map embed body and the flag
//   node site/tests/injury-view-test.mjs --url <page url>   # also opens <url>?school=... in headless Chrome, such as /embed/injuries/injury-map/
//
// The first run is part of `npm run check` in site/. The second needs Chrome and a server, such as the dev server
// (node site/scripts/dev.mjs), and is run by hand before the page ships.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

import { ROOT } from "../scripts/lib/repo.mjs";
const SITE = path.join(ROOT, "site");
const { readView, writeView, kidLine } = await import(path.join(SITE, "src", "injury-view.mjs"));
const IDX = JSON.parse(fs.readFileSync(path.join(SITE, "data", "school-sim", "index.json"), "utf8")).schools;
const MAP = JSON.parse(fs.readFileSync(path.join(SITE, "data", "injury-map.json"), "utf8"));
const CDS = IDX.map((s) => s.cds);
const FX = ["qb", "cam", "to20", "day", "slow", "calm", "plan-qb"];
// The school with the most kids hurt nearby, so the end-to-end check has dots to find.
const SCHOOL = [...MAP.schools].sort((a, b) => b.kids.length - a.kids.length || a.cds.localeCompare(b.cds))[0];
// The school with the most kids severely hurt or killed nearby, for the severe view's count line.
const SEV = new Set(MAP.map.kidSevere);
const sevNear = (s) => s.kids.filter((i) => SEV.has(i)).length;
const SEVSCHOOL = [...MAP.schools].sort((a, b) => sevNear(b) - sevNear(a) || a.cds.localeCompare(b.cds))[0];
let n = 0;
const ok = (name, fn) => { fn(); n++; console.log("  ok  " + name); };

ok("a school in the address picks that school and the kids' view", () => {
  const v = readView(`?school=${SCHOOL.cds}`, CDS, FX);
  assert.equal(v.school, SCHOOL.cds);
  assert.equal(v.set, "kid");
  assert.deepEqual(v.fx, []);
  assert.equal(v.at, null);
});
ok("the severe kids' view reads and writes as set=kidsev, with or without a school", () => {
  assert.equal(readView(`?school=${SCHOOL.cds}&set=kidsev`, CDS, FX).set, "kidsev");
  assert.equal(readView("?set=kidsev", CDS, FX).set, "kidsev");
  assert.equal(writeView({ school: SCHOOL.cds, set: "kidsev", fx: [], at: null }, ""), `?school=${SCHOOL.cds}&set=kidsev`);
});
ok("kidSevere names kids, each once, that the victims data rated severe or fatal", () => {
  const ks = MAP.map.kidSevere;
  assert.ok(ks.length > 0 && ks.length < MAP.map.kidPoints.length);
  assert.deepEqual(ks, [...new Set(ks)].sort((a, b) => a - b));
  for (const i of ks) assert.ok(Number.isInteger(i) && i >= 0 && i < MAP.map.kidPoints.length);
  assert.ok(sevNear(SEVSCHOOL) > 0, "no school has a kid severely hurt nearby");
});
ok("the count line says how many kids were hurt, or severely hurt or killed", () => {
  assert.equal(kidLine(12, false, "A & B"), "<b>12 kids</b> were hurt within a quarter mile of A &amp; B.");
  assert.equal(kidLine(1, true, "X"), "<b>1 kid</b> was severely hurt or killed within a quarter mile of X.");
  assert.equal(kidLine(0, true, "X"), "No kids were severely hurt or killed within a quarter mile of X.");
  assert.equal(kidLine(MAP.map.kidSevere.length, true, null), `<b>${MAP.map.kidSevere.length} kids</b> were severely hurt or killed on school trips across San Francisco.`);
});
ok("an unknown school, view or layer is ignored", () => {
  const v = readView("?school=999&set=nope&fx=qb,bogus,qb", CDS, FX);
  assert.deepEqual(v, { school: null, set: "all", fx: ["qb"], at: null });
});
ok("a map position off San Francisco is ignored", () => {
  assert.equal(readView("?at=40.7,-74.0,12", CDS, FX).at, null);
  assert.deepEqual(readView("?at=37.76,-122.44,13.5", CDS, FX).at, { lat: 37.76, lon: -122.44, zoom: 13.5 });
});
ok("writing a view and reading it back gives the same view", () => {
  const v = { school: SCHOOL.cds, set: "sev", fx: ["qb", "cam"], at: { lat: 37.71234, lon: -122.45678, zoom: 15.25 } };
  const qs = writeView(v, "");
  assert.equal(qs, `?school=${SCHOOL.cds}&set=sev&fx=qb,cam&at=37.71234,-122.45678,15.25`);
  assert.deepEqual(readView(qs, CDS, FX), v);
});
ok("the default view writes no address, and another page's parameters are kept", () => {
  assert.equal(writeView({ school: null, set: "all", fx: [], at: null }, ""), "");
  assert.equal(writeView({ school: SCHOOL.cds, set: "kid", fx: [], at: null }, "?cw-frame=1&school=x"), `?cw-frame=1&school=${SCHOOL.cds}`);
});
ok("every School Trips school has rings and valid kid indices", () => {
  assert.deepEqual(MAP.schools.map((s) => s.cds), CDS);
  for (const s of MAP.schools) {
    assert.ok(s.grounds.length && s.zone.length && s.quarter.length, s.name);
    for (const i of s.kids) assert.ok(Number.isInteger(i) && i >= 0 && i < MAP.map.kidPoints.length, s.name);
  }
});

// The map's body, as the board embed builds it.
const shown = spawnSync(process.execPath, ["--input-type=module", "-e", `
  const m = await import(${JSON.stringify(path.join(SITE, "src", "injury-page.mjs"))});
  process.stdout.write(m.content());`], { cwd: SITE, env: { ...process.env, SITE_SHOW_HIDDEN: "1" }, maxBuffer: 64 << 20, encoding: "utf8" });
assert.equal(shown.status, 0, shown.stderr);
const html = shown.stdout;
ok("the page offers every school in its picker and carries the view code", () => {
  const opts = [...html.matchAll(/<option value="(\d+)">/g)].map((m) => m[1]);
  assert.deepEqual([...opts].sort(), [...CDS].sort());
  assert.ok(html.includes("function readView(") && html.includes("function writeView("));
  assert.ok(html.includes('id="copy-link"'));
});
ok("the page carries the severe kids' layer and each school's severe count to its count line", () => {
  assert.ok(html.includes('value="kidsev"><span>Kids severely hurt or killed</span>'));
  assert.ok(html.includes("function kidLine(") && html.includes("kidLine(n, sev, s && s.name)"));
  const D = JSON.parse(html.match(/<script type="application\/json" id="hin-data">(.*?)<\/script>/s)[1]);
  assert.equal(D.kidsev.length, 2 * MAP.map.kidSevere.length);
  for (const s of MAP.schools) {
    const ks = D.schools[s.cds].ks;
    assert.equal(ks.length, sevNear(s), s.name);
    for (const j of ks) assert.ok(j >= 0 && j < MAP.map.kidSevere.length && s.kids.includes(MAP.map.kidSevere[j]), s.name);
  }
});
ok("the map embed is hidden from production and shown with the flag", () => {
  const ask = (env) => spawnSync(process.execPath, ["--input-type=module", "-e",
    `const f = await import(${JSON.stringify(path.join(SITE, "src", "features.mjs"))}); process.stdout.write(String(f.pathShown("/embed/injuries")));`],
    { env, encoding: "utf8" }).stdout;
  const { SITE_SHOW_HIDDEN, ...prod } = process.env;
  assert.equal(ask(prod), "false");
  assert.equal(ask({ ...prod, SITE_SHOW_HIDDEN: "1" }), "true");
});

// End to end: open the page with a school in its address in headless Chrome, and check it opens on that school.
const at = process.argv.indexOf("--url");
if (at > 0) {
  const base = process.argv[at + 1].replace(/[?#].*$/, "");
  const url = `${base}?school=${SCHOOL.cds}`;
  const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  const port = 9400 + Math.floor(Math.random() * 400);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "injury-view-"));
  const chrome = spawn(CHROME, ["--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run",
    `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
  try {
    let target;
    for (let i = 0; i < 50 && !target; i++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r) => (ws.onopen = r));
    let seq = 0; const pending = new Map();
    ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
    const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
    const ev = async (x) => (await send("Runtime.evaluate", { expression: x, returnByValue: true, awaitPromise: true })).result?.result?.value;
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false });
    await send("Page.navigate", { url });
    let st = null;
    for (let i = 0; i < 100; i++) {
      await sleep(300);
      st = await ev(`(function(){var m=document.getElementById('map'),g=m&&m.sfGL;if(!g||!g.sfLoaded||!g.getSource('kid-near'))return null;
        var c=g.getCenter(),k=g.querySourceFeatures('kid-near').length,r=g.querySourceFeatures('sch-rings').length;
        return {pick:document.getElementById('school').value,line:document.getElementById('school-line').hidden?'':document.getElementById('school-line').textContent,
          set:(document.querySelector('input[name=set]:checked')||{}).value,lon:c.lng,lat:c.lat,zoom:g.getZoom(),kids:k,rings:r,search:location.search};})()`);
      if (st && st.kids) break;
    }
    ok(`${url} opens ${SCHOOL.name}'s view`, () => {
      assert.ok(st, "the map never loaded");
      assert.equal(st.pick, SCHOOL.cds);
      assert.equal(st.set, "kid");
      assert.ok(st.line.includes(SCHOOL.name) && st.line.includes(`${SCHOOL.kids.length} kids`), st.line);
      assert.ok(st.rings > 0, "no rings drawn");
      assert.ok(st.kids > 0, "no kids highlighted");
      const xs = SCHOOL.quarter.flat().map((p) => p[0]), ys = SCHOOL.quarter.flat().map((p) => p[1]);
      assert.ok(st.lon > Math.min(...xs) && st.lon < Math.max(...xs) && st.lat > Math.min(...ys) && st.lat < Math.max(...ys), `centre ${st.lon},${st.lat} is off the school`);
      assert.ok(st.zoom > 14, `zoom ${st.zoom}`);
      assert.ok(st.search.includes(`school=${SCHOOL.cds}`));
    });
    const link = await ev(`(function(){document.getElementById('copy-link').click();return new Promise(function(r){setTimeout(function(){
      var i=document.getElementById('copy-url');r({shown:!i.hidden,value:i.value,label:document.getElementById('copy-link').textContent});},500);});})()`);
    ok("Copy link gives this page's own address with the school in it", () => {
      assert.ok(link.value.startsWith(base) && link.value.includes(`school=${SCHOOL.cds}`), JSON.stringify(link));
      // The fit to the school is the page's own move, so the link carries no map position and fits on any screen.
      assert.ok(!link.value.includes("at="), link.value);
    });
    const reset = await ev(`(function(){document.querySelector('.sf-reset button').click();return new Promise(function(r){setTimeout(function(){
      r({pick:document.getElementById('school').value,set:(document.querySelector('input[name=set]:checked')||{}).value,search:location.search});},1200);});})()`);
    ok("Reset goes back to all of San Francisco and drops the school from the address", () => {
      assert.deepEqual(reset, { pick: "", set: "all", search: "" });
    });
    await send("Page.navigate", { url: `${base}?school=${SEVSCHOOL.cds}&set=kidsev` });
    let sv = null;
    for (let i = 0; i < 100; i++) {
      await sleep(300);
      sv = await ev(`(function(){var g=document.getElementById('map').sfGL;if(!g||!g.sfLoaded||!g.getSource('kid-near'))return null;
        return {line:document.getElementById('school-line').textContent,set:(document.querySelector('input[name=set]:checked')||{}).value,
          kids:g.querySourceFeatures('kid-near').length,heat:g.getLayoutProperty('heat-kidsev','visibility')};})()`);
      if (sv && sv.kids) break;
    }
    ok(`${SEVSCHOOL.name}'s severe view counts its kids severely hurt or killed`, () => {
      assert.ok(sv, "the map never loaded");
      const k = sevNear(SEVSCHOOL);
      assert.equal(sv.set, "kidsev");
      assert.equal(sv.heat, "visible");
      assert.ok(sv.line.startsWith(`${k} kid${k === 1 ? " was" : "s were"} severely hurt or killed within a quarter mile of ${SEVSCHOOL.name}`), sv.line);
      assert.equal(sv.kids, k);
    });
    ws.close();
  } finally {
    chrome.kill();
    setTimeout(() => fs.rmSync(profile, { recursive: true, force: true }), 500).unref();
  }
}
console.log(`injury-view-test: ${n} passed`);
