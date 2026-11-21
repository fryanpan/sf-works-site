#!/usr/bin/env node
// Build data/osm-compare.json: where SFMTA's bikeway record and OpenStreetMap
// disagree, block by block.
//
//   node scripts/collect-osm-compare.mjs [--from <path to compare.geojson>]
//
// Reads the join written by tools/travel/osm-sfmta-compare.py in the research repo.
// That script reaches the network; this one does not. It projects the geometry
// to SVG paths once, here, so the build stays a pure function of committed
// JSON and the page never ships 1.5 MB of coordinates to a reader.
//
// Only the disagreements are kept as individual paths. Every agreeing block is
// merged into one base path, because a reader cannot tap 2,198 of them and the
// page is not about them.

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const args = process.argv.slice(2);
const fromArg = args.indexOf("--from");
const SRC =
  fromArg >= 0
    ? args[fromArg + 1]
    : path.join(ROOT, "..", "out/osm-compare/compare.geojson");
const SUMMARY = path.join(path.dirname(SRC), "summary.json");

const W = 1000;

// The facility ladder, shared with the research script. `path` and `separated`
// tie: both put something physical between a rider and a car.
const RANK = { sharrow: 1, painted: 2, separated: 3, path: 3 };

// How far apart the two records are, which is the thing the map colours.
// A block where one record has a facility and the other has none is its own
// step, worse than any one-rung difference, because the disagreement is about
// whether there is a bikeway at all.
function gap(p) {
  if (p.verdict === "agree") return 0;
  if (p.verdict === "no-osm-record" || p.verdict === "osm-only") return 3;
  return Math.min(2, Math.abs(RANK[p.sfmta] - RANK[p.osm]));
}

const src = JSON.parse(fs.readFileSync(SRC, "utf8"));
const summary = JSON.parse(fs.readFileSync(SUMMARY, "utf8"));

let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
for (const f of src.features) {
  for (const part of f.geometry.coordinates) {
    for (const [x, y] of part) {
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
  }
}
// Equirectangular at the city's own latitude, so San Francisco is not
// stretched east to west. Good enough at city scale and needs no library.
const k = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
const scale = W / ((x1 - x0) * k);
const H = Math.round((y1 - y0) * scale);

function d(parts) {
  let out = "";
  for (const part of parts) {
    let last = null;
    for (const [lon, lat] of part) {
      const x = Math.round((lon - x0) * k * scale);
      const y = Math.round((y1 - lat) * scale);
      if (last && last[0] === x && last[1] === y) continue;
      out += `${last ? "L" : "M"}${x} ${y}`;
      last = [x, y];
    }
  }
  return out.includes("L") ? out : "";
}

const base = [];
const marks = [];
for (const f of src.features) {
  const p = f.properties;
  const s = d(f.geometry.coordinates);
  if (!s) continue;
  if (p.verdict === "agree" || p.verdict === "unmatchable") {
    base.push(s);
    continue;
  }
  marks.push({
    d: s,
    // The block's own coordinates, 5 decimals (about a metre), for the basemap
    // version of the page. Only the disagreements carry them — a few hundred
    // blocks, not 2,198 — so the page stays small.
    coords: f.geometry.coordinates.map((part) => part.map(([x, y]) => [+x.toFixed(5), +y.toFixed(5)])),
    cnn: p.cnn,
    street: p.street,
    block: p.from && p.to ? `${p.from} to ${p.to}` : "",
    sfmta: p.sfmta,
    osm: p.osm,
    verdict: p.verdict,
    gap: gap(p),
    // Which record reads higher. The map puts this on the dash pattern rather
    // than on a second hue, so shade means one thing only.
    leans: p.verdict === "osm-higher" || p.verdict === "osm-only" ? "osm" : "sfmta",
    updated: p.updated || "",
    edited: p.osmEdited || "",
    ways: p.osmWays || [],
  });
}

marks.sort((a, b) => a.street.localeCompare(b.street) || a.block.localeCompare(b.block));

const out = {
  generated: summary.generated,
  sfmtaTag: summary.sfmtaTag,
  osmDate: summary.osmDate,
  toleranceM: summary.toleranceM,
  blocks: summary.blocks,
  verdicts: summary.verdicts,
  osmOnlyWays: summary.osmOnlyWays,
  unnamedOsmWays: summary.unnamedOsmWays,
  width: W,
  height: H,
  base: base.join(""),
  marks,
};

const dest = path.join(ROOT, "data", "osm-compare.json");
fs.writeFileSync(dest, JSON.stringify(out));
console.log(
  `collect-osm-compare: ${marks.length} marks, ${base.length} agreeing blocks, ` +
    `${(fs.statSync(dest).size / 1024).toFixed(0)}KB into data/osm-compare.json`,
);
