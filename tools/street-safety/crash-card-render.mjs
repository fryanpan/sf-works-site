#!/usr/bin/env node
// Renders crash-card diagrams (site/src/safety-map/crash-cards.js) to PNG for a look by eye: a stratified random sample with a fixed seed, or a saved list, each card as its own PNG plus contact sheets of nine.
//
//   node tools/street-safety/crash-card-render.mjs --out DIR [--n 100] [--seed 20261119] [--cases 240573409,...] [--list FILE] [--cards FILE]
//
// The sample covers divided streets, T junctions, five-way and skewed junctions, midblock points, turns, walkers and
// compass fallbacks; --cases are always included. --list reads the case ids from a file written by an earlier run
// (DIR/sample.json), so a second run draws the same cards. Needs rsvg-convert (librsvg) on the PATH.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { ROOT } from "../../site/scripts/lib/repo.mjs";
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const OUT = arg("out"), N = +arg("n", 100), SEED = +arg("seed", 20261119);
if (!OUT) { console.error("usage: crash-card-render.mjs --out DIR [--n 100] [--seed N] [--cases a,b] [--list FILE]"); process.exit(2); }
// --cards: one JSON of { case: card }; by default every card in tools/street-safety/street-safety-cards.py's files.
const C = arg("cards") ? JSON.parse(fs.readFileSync(arg("cards"), "utf8")) : (() => {
  const dir = path.join(ROOT, "site/data/street-safety/cards"), I = JSON.parse(fs.readFileSync(path.join(dir, "index.json"), "utf8")), out = {};
  for (const k of Object.keys(I.files).sort()) Object.assign(out, JSON.parse(fs.readFileSync(path.join(dir, k + ".json"), "utf8")).cards);
  return out;
})();
const ctx = { window: {}, document: {} };
vm.runInNewContext(fs.readFileSync(path.join(ROOT, "site/src/safety-map/crash-cards.js"), "utf8") + "\nthis.CrashCards = CrashCards;", ctx);
const STYLE = "<style>text{font-family:Helvetica,Arial,sans-serif}.cc-road{font-size:9px;fill:#3d4450}.cc-num{font-size:9px;font-weight:600;fill:#353b44}.cc-note{font-size:8.5px;fill:#6b7280}</style>";

function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const diff = (a, b) => Math.abs(((a - b + 540) % 360) - 180);
// The strata a card fits. A card is claimed by the first one, in this order, that still has room.
function strata(c) {
  const g = c.g, out = [];
  if (!g.geo) return ["nogeo"];
  const L = g.geo.l, by = {};
  L.forEach((l) => (by[l[3]] = by[l[3]] || []).push(l[2]));
  if (Object.values(by).some((bs) => bs.some((a, i) => bs.some((b, j) => j > i && diff(a, b) < 50)))) out.push("divided");
  if (g.p.some((p) => p.t)) out.push("turn");
  if (L.length >= 5 || (L.length === 4 && L.some((a) => L.every((b) => a === b || Math.min(diff(a[2], b[2]) % 90, 90 - (diff(a[2], b[2]) % 90)) > 15)))) out.push("five-way or skewed");
  if (L.length === 3) out.push("T");
  if (L.length <= 2) out.push("midblock");
  if (g.p.some((p) => p.v === "walk" && p.d)) out.push("walker");
  if (g.p.some((p) => p.fb)) out.push("fallback");
  if (!out.length) out.push("four-way");
  return out;
}
const QUOTA = { divided: 28, turn: 16, "five-way or skewed": 14, T: 10, midblock: 12, walker: 10, fallback: 5, "four-way": 5 };

let picks;
if (arg("list")) picks = JSON.parse(fs.readFileSync(arg("list"), "utf8"));
else {
  const r = rng(SEED), ids = Object.keys(C).sort(), named = (arg("cases", "") || "").split(",").filter(Boolean);
  for (let i = ids.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [ids[i], ids[j]] = [ids[j], ids[i]]; }
  const left = { ...QUOTA }, total = Object.values(QUOTA).reduce((a, b) => a + b, 0);
  picks = named.map((id) => ({ id, s: "named: " + strata(C[id]).join(", ") }));
  for (const id of ids) {
    if (picks.length >= N) break;
    if (named.includes(id)) continue;
    const s = strata(C[id]).find((k) => left[k] > 0);
    if (!s) continue;
    left[s] -= 1; picks.push({ id, s });
  }
  if (N > total + named.length) console.error("quotas hold " + total + " cards");
}
picks = picks.filter((p) => C[p.id]);
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, "sample.json"), JSON.stringify(picks, null, 1));
const SC = 2, W = 260, H = 214, PER = 9, COLS = 3;
const inner = (id) => ctx.CrashCards.diagram(C[id].g).replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "");
picks.forEach((p) => {
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + " " + H + '" width="' + W * 3 + '" height="' + H * 3 + '">' + STYLE + '<rect width="100%" height="100%" fill="#fff"/>' + inner(p.id) + "</svg>";
  const f = path.join(OUT, p.id + ".svg");
  fs.writeFileSync(f, svg);
  execFileSync("rsvg-convert", [f, "-o", path.join(OUT, p.id + ".png")]);
  fs.unlinkSync(f);
});
for (let s = 0; s * PER < picks.length; s++) {
  const part = picks.slice(s * PER, s * PER + PER), rows = Math.ceil(part.length / COLS), CH = H + 30;
  let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + COLS * W * SC + '" height="' + rows * CH * SC + '" viewBox="0 0 ' + COLS * W + " " + rows * CH + '">' + STYLE + '<rect width="100%" height="100%" fill="#fff"/>';
  part.forEach((p, i) => {
    const x = (i % COLS) * W, y = Math.floor(i / COLS) * CH, c = C[p.id];
    svg += '<g transform="translate(' + x + "," + y + ')"><rect x="0.5" y="0.5" width="' + (W - 1) + '" height="' + (CH - 1) + '" fill="none" stroke="#999"/>' +
      '<text x="4" y="10" font-size="8.5" font-weight="700">' + (s * PER + i + 1) + ". " + p.id + " [" + p.s + "]</text>" +
      c.pr.slice(0, 2).map((t, k) => '<text x="4" y="' + (19 + 8 * k) + '" font-size="6.2">' + (k + 1) + ": " + t.replace(/[&<>]/g, "").slice(0, 88) + "</text>").join("") +
      '<g transform="translate(0,30)">' + inner(p.id) + "</g></g>";
  });
  const f = path.join(OUT, "sheet-" + String(s + 1).padStart(2, "0") + ".svg");
  fs.writeFileSync(f, svg + "</svg>");
  execFileSync("rsvg-convert", [f, "-o", f.replace(".svg", ".png")]);
  fs.unlinkSync(f);
}
const n = {};
picks.forEach((p) => { const k = p.s.replace(/^named: .*/, "named"); n[k] = (n[k] || 0) + 1; });
console.log(picks.length + " cards to " + OUT, JSON.stringify(n));
