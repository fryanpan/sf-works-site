// Checks the hin-people map's view switch for change blindness: at a citywide and a neighbourhood zoom, flips through every view in headless Chrome and fails unless the camera and map frame stay exactly put and no drawn frame is blank.
//
//   node tools/street-safety/hin-map-switch-check.mjs scratch/embeds/hin-people/index.html [width, default 1366]
//
// Bryan, 2026-11-18: "when I go from injuries to traffic stress to crime, the map should not shift ... rendering
// should not introduce any blank frames in between". For each switch it records map.getCenter(), getZoom() and the
// map element's page rectangle and the page's bottom edge before and after, and reads back every frame MapLibre draws during the switch
// (gl.readPixels inside the render event, while the drawing buffer is still whole), sampling a 24 x 16 grid. A frame
// is blank when every sample is one colour. Exits 1 on any shift or blank frame; prints one JSON line per zoom.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const file = path.resolve(process.argv[2] || "scratch/embeds/hin-people/index.html");
const VIEWS = ["people", "stress", "crime", "bike", "people", "crime", "stress", "people"];
const STOPS = [{ name: "citywide", center: [-122.44, 37.76], zoom: 12 }, { name: "neighbourhood", center: [-122.414, 37.781], zoom: 15 }];
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "switch-"));
const port = 9800 + Math.floor(Math.random() * 100);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
  "--no-first-run", "--hide-scrollbars", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
let failed = false;
try {
  let t;
  for (let i = 0; i < 50 && !t; i++) { await sleep(200); try { t = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((x) => x.type === "page"); } catch {} }
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let seq = 0; const pend = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pend.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  const ev = async (expr) => { const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.error) throw new Error(JSON.stringify(r.error)); if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 300)); return r.result.result.value; };
  await send("Page.enable"); await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: +(process.argv[3] || 1366), height: 900, deviceScaleFactor: 1, mobile: +(process.argv[3] || 1366) < 500 });
  await send("Page.navigate", { url: "file://" + file });
  for (let i = 0; i < 120; i++) { await sleep(500); if (await ev("window.__ready === 2")) break; }
  await ev(`(function () {
    var map = window.__map, gl = map.getCanvas().getContext("webgl2") || map.getCanvas().getContext("webgl");
    window.__frames = [];
    map.on("render", function () {
      var W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(4), seen = {};
      for (var i = 1; i < 24; i++) for (var j = 1; j < 16; j++) { gl.readPixels(Math.floor(W * i / 24), Math.floor(H * j / 16), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); seen[px.join(",")] = 1; }
      if (window.__rec) window.__frames.push(Object.keys(seen).length);
    });
  })()`);
  for (const s of STOPS) {
    await ev(`new Promise(function (r) { window.__map.jumpTo({ center: ${JSON.stringify(s.center)}, zoom: ${s.zoom} }); window.__map.once("idle", function () { r(1); }); })`);
    await sleep(1500);
    const state = () => ev(`(function () { var m = window.__map, c = m.getCenter(), r = m.getContainer().getBoundingClientRect(); return [c.lng, c.lat, m.getZoom(), r.top, r.left, r.width, r.height, Math.round(document.body.getBoundingClientRect().bottom)].join(","); })()`);
    const base = await state(), out = { stop: s.name, zoom: s.zoom, switches: 0, shifted: [], frames: 0, blank: 0, fewest_colours: 999 };
    for (const v of VIEWS) {
      await ev("window.__frames = []; window.__rec = true; window.__view(" + JSON.stringify(v) + "); true");
      await sleep(900);
      const f = await ev("window.__rec = false; window.__frames");
      const now = await state();
      out.switches++; out.frames += f.length;
      out.blank += f.filter((n) => n <= 1).length;
      out.fewest_colours = Math.min(out.fewest_colours, ...f, 999);
      if (now !== base) out.shifted.push(v + ": " + base + " -> " + now);
    }
    if (out.shifted.length || out.blank) failed = true;
    console.log(JSON.stringify(out));
  }
  ws.close();
} catch (e) {
  console.error("switch check could not run:", e.message); failed = true;
} finally {
  chrome.kill();
  await sleep(500);
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
}
process.exit(failed ? 1 : 0);
