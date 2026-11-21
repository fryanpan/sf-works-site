#!/usr/bin/env node
// Look at the site's markdown pages (board .mdx docs among them) the way a reader will, in headless Chrome, before they deploy.
//
//   node site/scripts/check-rendered-docs.mjs                  every markdown page the last build wrote to site/dist/
//   node site/scripts/check-rendered-docs.mjs --fixture        the test doc in site/tests/fixtures/board-doc/, rendered to a temp folder
//   node site/scripts/check-rendered-docs.mjs --content <dir>  the pages in another content folder, rendered the same way
//   node site/scripts/check-rendered-docs.mjs --shots <dir>    also save a full-page screenshot of each page at 1366 and 390 wide
//
// `npm run deploy-docs` in site/ runs it on the build before anything is pushed (site/scripts/deploy-docs.mjs). The
// --fixture run proves the renderer on blocks copied from a real board doc; the fixture lives outside site/, so no
// build ever publishes it. For each page it fails:
//   - a <PlotChart> that did not become an SVG (the page's figure count must equal the source's <PlotChart> count)
//   - board syntax that reached the reader as text: <PlotChart, <Carousel, an import line, ::scratch, ^[ or ¶
//   - footnotes not numbered 1, 2, 3 ... in reading order, or a marker with no note under References
//   - a ::scratch frame whose figure page did not load, or an image that did not load
//   - a link to a repo file (.md or .mdx), which is a dead link once published
//   - a console error or uncaught exception on the page or in its frames, or a same-site request that failed
//   - a page wider than the phone screen at 390
// Chrome is $CHROME, else the macOS default, else google-chrome on PATH (the CI runners have it). The phone view is
// the page in a 390px iframe, since headless Chrome ignores window widths under about 500px. Exit code 1 on any failure.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, execFileSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

import { ROOT } from "./lib/repo.mjs";
const SITE = path.join(ROOT, "site");

const args = process.argv.slice(2);
const flag = (name) => { const i = args.indexOf(name); return i < 0 ? null : args.splice(i, 2)[1]; };
const shots = flag("--shots");
const content = flag("--content");
const FIXTURE = path.resolve(content ?? path.join(ROOT, "site", "tests", "fixtures", "board-doc", "content"));
const fixture = args.includes("--fixture") || Boolean(content);
const distDir = path.resolve(flag("--dist") ?? path.join(SITE, "dist"));

const { loadPages, mdPageFiles } = await import(path.join(SITE, "src", "md-pages.mjs"));

// The pages to check, as [{path, src, html file under root}], and the folder to serve.
let root;
let pages;
if (fixture) {
  root = fs.mkdtempSync(path.join(os.tmpdir(), "board-doc-"));
  process.on("exit", () => fs.rmSync(root, { recursive: true, force: true }));
  const loaded = loadPages({ dir: FIXTURE, showDrafts: true });
  for (const f of mdPageFiles(loaded, {})) {
    fs.mkdirSync(path.dirname(path.join(root, f.file)), { recursive: true });
    fs.writeFileSync(path.join(root, f.file), f.html);
  }
  pages = loaded.map((p) => ({ path: p.path, source: path.join(FIXTURE, p.src), file: p.file }));
} else {
  root = distDir;
  if (!fs.existsSync(root)) {
    console.error(`check-rendered-docs: no build at ${root}; run npm run build in site/ first`);
    process.exit(2);
  }
  // The same pages the build chose (SITE_SHOW_HIDDEN decides drafts, as it did for the build).
  pages = loadPages().filter((p) => p.status !== "teaser").map((p) => ({ path: p.path, source: path.join(SITE, "content", p.src), file: p.file }));
  const missing = pages.filter((p) => !fs.existsSync(path.join(root, p.file)));
  if (missing.length) {
    console.error(`check-rendered-docs: the build has no ${missing.map((p) => p.file).join(", ")}; rebuild first`);
    process.exit(2);
  }
}
if (!pages.length) {
  console.log("check-rendered-docs: no markdown pages with a body in this build; nothing to check");
  process.exit(0);
}

// A static server over the folder, with a phone wrapper at /__phone/?src=<path>.
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".xml": "application/xml" };
const PHONE = (src) => `<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"><style>html,body{margin:0;background:#e9ecef}iframe{display:block;width:390px;border:0;background:#fff}</style></head>
<body><iframe id="f" src="${src}" scrolling="no"></iframe></body></html>`;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/__phone/") return res.writeHead(200, { "content-type": TYPES[".html"] }).end(PHONE(url.searchParams.get("src")));
  let f = path.join(root, path.normalize(decodeURIComponent(url.pathname)));
  if (!f.startsWith(root)) return res.writeHead(403).end();
  if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, "index.html");
  if (!fs.existsSync(f)) return res.writeHead(404).end();
  res.writeHead(200, { "content-type": TYPES[path.extname(f)] ?? "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;

function chromePath() {
  if (process.env.CHROME) return process.env.CHROME;
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  if (fs.existsSync(mac)) return mac;
  for (const name of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    try { return execFileSync("which", [name], { encoding: "utf8" }).trim(); } catch {}
  }
  throw new Error("check-rendered-docs: no Chrome found; set CHROME");
}

const port = 9400 + Math.floor(Math.random() * 500);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "check-rendered-docs-chrome-"));
const chrome = spawn(chromePath(), ["--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-first-run", "--no-default-browser-check",
  "--hide-scrollbars", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
const cleanup = () => { try { chrome.kill(); } catch {} server.close(); };
process.on("exit", () => { cleanup(); try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 3 }); } catch {} });

let target;
for (let i = 0; i < 75 && !target; i++) {
  await sleep(200);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {}
}
if (!target) { console.error("check-rendered-docs: Chrome did not start"); process.exit(2); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let seq = 0;
const pending = new Map();
const listeners = [];
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } else if (m.method) for (const l of listeners) l(m);
};
const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(`in page: ${r.result.exceptionDetails.exception?.description ?? r.result.exceptionDetails.text}`);
  return r.result?.result?.value;
};
await send("Page.enable");
await send("Runtime.enable");
await send("Log.enable");
await send("Network.enable");

// Every console error, uncaught exception and failed same-site request, from the page and its same-site frames.
let problems = [];
const requests = new Map();
listeners.push((m) => {
  const p = m.params;
  if (m.method === "Runtime.consoleAPICalled" && p.type === "error") problems.push(`console error: ${p.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 300)}`);
  else if (m.method === "Runtime.exceptionThrown") problems.push(`uncaught: ${(p.exceptionDetails.exception?.description ?? p.exceptionDetails.text).split("\n")[0]}`);
  else if (m.method === "Log.entryAdded" && p.entry.level === "error" && (!p.entry.url || p.entry.url.startsWith(origin))) problems.push(`browser error: ${p.entry.text} ${p.entry.url ?? ""}`.trim());
  else if (m.method === "Network.requestWillBeSent") requests.set(p.requestId, p.request.url);
  else if (m.method === "Network.responseReceived" && p.response.url.startsWith(origin) && p.response.status >= 400) problems.push(`HTTP ${p.response.status}: ${p.response.url.slice(origin.length)}`);
  else if (m.method === "Network.loadingFailed" && (requests.get(p.requestId) ?? "").startsWith(origin) && !p.canceled) problems.push(`failed to load: ${requests.get(p.requestId).slice(origin.length)} (${p.errorText})`);
});

async function load(url, width) {
  await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false });
  const loaded = new Promise((r) => { const l = (m) => { if (m.method === "Page.loadEventFired") { listeners.splice(listeners.indexOf(l), 1); r(); } }; listeners.push(l); });
  await send("Page.navigate", { url });
  await Promise.race([loaded, sleep(30000)]);
}

// Scroll through so lazy frames load, then wait for them and their height messages.
async function settle(frameSel) {
  await ev(`(async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 600) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); } scrollTo(0, 0); })()`);
  for (let i = 0; i < 40; i++) {
    const ready = await ev(`(() => { const fs = [...document.querySelectorAll(${JSON.stringify(frameSel)})]; return fs.every((f) => { try { return f.contentDocument && f.contentDocument.readyState === "complete" && f.contentDocument.body && f.contentDocument.body.children.length > 0; } catch (e) { return false; } }); })()`);
    if (ready) break;
    await sleep(250);
  }
  await sleep(1500);
}

// The checks that run in the page. `expect` is what the source says the page must hold.
const IN_PAGE = (expect) => `(() => {
  const fails = [];
  const charts = [...document.querySelectorAll("figure.md-chart")];
  if (charts.length !== ${expect.charts}) fails.push("the source has ${expect.charts} <PlotChart>, the page " + charts.length + " charts");
  charts.forEach((c, i) => { if (!c.querySelector("svg")) fails.push("chart " + (i + 1) + " (" + (c.querySelector("figcaption")?.textContent ?? "untitled") + ") has no SVG"); });
  const text = document.body.innerText;
  for (const raw of ["<PlotChart", "<Carousel", "</Carousel", "import Carousel", "::scratch", "::sfworks", "^[", "¶"]) if (text.includes(raw)) fails.push("raw board syntax reached the reader: " + raw);
  const sups = [...document.querySelectorAll("sup.fn a")];
  sups.forEach((a, i) => {
    if (a.textContent.trim() !== String(i + 1)) fails.push("footnote marker " + (i + 1) + " reads " + a.textContent.trim());
    const note = document.getElementById(a.getAttribute("href").slice(1));
    if (!note || !note.closest("ol.fn-list")) fails.push("footnote " + (i + 1) + " has no note under References");
  });
  const notes = document.querySelectorAll("ol.fn-list > li").length;
  if (notes !== sups.length) fails.push(sups.length + " footnote markers but " + notes + " notes");
  if (sups.length < ${expect.notes}) fails.push("the source has " + ${expect.notes} + " notes, the page " + sups.length + " markers");
  const frames = [...document.querySelectorAll("iframe.md-embed")];
  if (frames.length !== ${expect.frames}) fails.push("the source has ${expect.frames} ::scratch frames, the page " + frames.length);
  frames.forEach((f) => { let ok = false; try { ok = f.contentDocument.body.children.length > 0 && !/404/.test(f.contentDocument.title); } catch (e) {} if (!ok) fails.push("frame " + f.dataset.block + " did not load"); });
  document.querySelectorAll("article img").forEach((im) => { if (!im.complete || !im.naturalWidth) fails.push("image did not load: " + im.getAttribute("src")); });
  document.querySelectorAll("article a[href]").forEach((a) => { const h = a.getAttribute("href"); if (/^(?![a-z]+:)[^#?]*\\.mdx?(?:[#?]|$)/i.test(h)) fails.push("link to a repo file, dead once published: " + h); });
  return { fails, charts: charts.length, notes: sups.length, frames: frames.length, images: document.querySelectorAll("article img").length };
})()`;

async function screenshot(file, phone) {
  if (phone) {
    // Size the wrapper's frame to the page it holds, then shoot the wrapper.
    await ev(`(() => { const f = document.getElementById("f"); f.style.height = f.contentDocument.documentElement.scrollHeight + "px"; })()`);
    await sleep(800);
  }
  const { result } = await send("Page.getLayoutMetrics");
  const w = phone ? 390 : Math.ceil(result.cssContentSize.width);
  const h = Math.min(Math.ceil(result.cssContentSize.height), 16000);
  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: w, height: h, scale: 1 } });
  fs.writeFileSync(file, Buffer.from(shot.result.data, "base64"));
  return file;
}

let failed = 0;
if (shots) fs.mkdirSync(shots, { recursive: true });
for (const p of pages) {
  const src = fs.readFileSync(p.source, "utf8");
  const expect = {
    charts: (src.match(/<PlotChart\b/g) || []).length,
    frames: (src.match(/^::scratch\{block="[\w-]+"\}[ \t]*$/gm) || []).length,
    notes: new Set([...(src.match(/\[\^[\w-]+\](?!:)/g) || [])]).size + (src.match(/\^\[/g) || []).length,
  };
  // The built file itself: board syntax escaped into the HTML is a leak even where innerText hides it.
  const html = fs.readFileSync(path.join(root, p.file), "utf8").replace(/<script\b[\s\S]*?<\/script>/g, "");
  const fails = [];
  for (const raw of ["<PlotChart", "&lt;PlotChart", "<Carousel", "&lt;Carousel", "::scratch", "^["]) if (html.includes(raw)) fails.push(`raw board syntax in the HTML: ${raw}`);

  problems = [];
  const url = `${origin}${p.path}/`;
  await load(url, 1366);
  await settle("iframe.md-embed");
  const r = await ev(IN_PAGE(expect));
  fails.push(...r.fails, ...problems);
  const slug = p.path.replace(/^\//, "").replace(/\//g, "-") || "root";
  const saved = [];
  if (shots) saved.push(await screenshot(path.join(shots, `${slug}-1366.png`), false));

  problems = [];
  await load(`${origin}/__phone/?src=${encodeURIComponent(`${p.path}/`)}`, 600);
  await ev(`new Promise((r) => { const f = document.getElementById("f"); if (f.contentDocument?.readyState === "complete") r(); else f.onload = r; })`);
  // The wrapper never scrolls its frame, so lazy figure frames below the fold would never load: load them now.
  await ev(`(() => { const d = document.getElementById("f").contentDocument; d.querySelectorAll("iframe[loading=lazy]").forEach((f) => { f.loading = "eager"; f.src = f.src; }); })()`);
  for (let i = 0; i < 40; i++) {
    const ready = await ev(`(() => [...document.getElementById("f").contentDocument.querySelectorAll("iframe.md-embed")].every((f) => { try { return f.contentDocument?.readyState === "complete" && f.contentDocument.body?.children.length > 0; } catch (e) { return false; } }))()`);
    if (ready) break;
    await sleep(250);
  }
  await sleep(2000);
  const wide = await ev(`(() => { const d = document.getElementById("f").contentDocument; return d.documentElement.scrollWidth; })()`);
  if (wide > 391) fails.push(`at 390 wide the page is ${wide}px wide, so it scrolls sideways on a phone`);
  fails.push(...problems.map((x) => `phone: ${x}`));
  if (shots) saved.push(await screenshot(path.join(shots, `${slug}-390.png`), true));

  const uniq = [...new Set(fails)];
  console.log(`${uniq.length ? "FAIL" : "PASS"} ${p.path}: ${r.charts} charts drawn as SVG, ${r.notes} footnotes, ${r.frames} frames, ${r.images} images`);
  for (const f of uniq) console.log(`  - ${f}`);
  for (const s of saved) console.log(`  screenshot ${s}`);
  if (uniq.length) failed++;
}
ws.close();
console.log(failed ? `check-rendered-docs: ${failed} of ${pages.length} page(s) failed` : `check-rendered-docs: ${pages.length} page(s) passed`);
process.exit(failed ? 1 : 0);
