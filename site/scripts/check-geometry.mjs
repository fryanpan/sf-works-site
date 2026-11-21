#!/usr/bin/env node
// Fail the build when a map would draw a bad shape or leave out a project's blocks.
//
//   node scripts/check-geometry.mjs      (the build runs it first: astro.config.mjs)
//
// Two of the audit criteria in pipeline/transportation-data-audit-criteria.md,
// checked from data/ alone so the build still never reaches outside site/:
//
//   E1  no empty, zero-length, self-intersecting or out-of-city line in a file
//       the transportation pages draw, and no project with nothing to draw.
//   E3  every project map draws every block and intersection the project
//       holds: coordination.json's `geometry` plus `nodes` equals `blocks`.
//
// E2, whether a block's line lies on its CNN's centerline, needs the city's
// centerline file, which is not in site/: tools/bike-network/bike-network-history.py
// refuses to write a segment that is off it, and
// pipeline/transportation-geometry-check.py runs all three with the centerline.

import fs from "node:fs";
import path from "node:path";

const DATA = path.resolve(import.meta.dirname, "..", "data");
const LON = [-122.53, -122.35];
const LAT = [37.7, 37.835];
const KX = 111320 * Math.cos((37.76 * Math.PI) / 180);
const KY = 111320;

const read = (rel) => JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8"));
const proj = ([x, y]) => [x * KX, y * KY];
const cross = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);

function crosses(p1, p2, p3, p4) {
  const d1 = cross(p3, p4, p1), d2 = cross(p3, p4, p2), d3 = cross(p1, p2, p3), d4 = cross(p1, p2, p4);
  return d1 && d2 && d3 && d4 && d1 > 0 !== d2 > 0 && d3 > 0 !== d4 > 0;
}

function fault(pts) {
  if (!Array.isArray(pts) || pts.length < 2) return "empty";
  if (pts.some(([x, y]) => !(x >= LON[0] && x <= LON[1] && y >= LAT[0] && y <= LAT[1]))) return "outside the city";
  const q = pts.map(proj);
  let len = 0;
  for (let i = 1; i < q.length; i++) len += Math.hypot(q[i][0] - q[i - 1][0], q[i][1] - q[i - 1][1]);
  if (len < 0.1) return "zero-length";
  const closed = q.length > 3 && q[0][0] === q.at(-1)[0] && q[0][1] === q.at(-1)[1];
  for (let i = 0; i < q.length - 1; i++) {
    for (let j = i + 2; j < q.length - 1; j++) {
      if (closed && i === 0 && j === q.length - 2) continue;
      if (crosses(q[i], q[i + 1], q[j], q[j + 1])) return "self-intersecting";
    }
  }
  return null;
}

const lines = (fc) =>
  fc.features.flatMap((f) =>
    f.geometry?.type === "LineString" ? [f.geometry.coordinates] : f.geometry?.type === "MultiLineString" ? f.geometry.coordinates : [[]],
  );

export function checkGeometry() {
  const errors = [];
  const coord = read("coordination.json");
  const files = {
    "north-star/traced.geojson": lines(read("north-star/traced.geojson")),
    "north-star/segments.geojson": lines(read("north-star/segments.geojson")),
    "bike-history/segments.json": read("bike-history/segments.json").segments.map((s) => s.pts),
    "bike-history/all-ages.geojson": lines(read("bike-history/all-ages.geojson")),
    "sf-streets.json": read("sf-streets.json").lines,
    "coordination.json": coord.projects.flatMap((p) => p.geometry),
    "department-overlap.json": read("department-overlap.json").compare.flatMap((c) => (c.segments || []).map((s) => s.line)),
  };
  for (const [file, ls] of Object.entries(files)) {
    const bad = {};
    for (const l of ls) {
      const f = fault(l);
      if (f) bad[f] = (bad[f] || 0) + 1;
    }
    for (const [f, n] of Object.entries(bad)) errors.push(`E1 ${file}: ${n} ${f} line${n === 1 ? "" : "s"}`);
  }
  for (const p of coord.projects) {
    const nodes = p.nodes || [];
    for (const [x, y] of nodes) {
      if (!(x >= LON[0] && x <= LON[1] && y >= LAT[0] && y <= LAT[1])) errors.push(`E1 coordination.json: ${p.name} has an intersection outside the city`);
    }
    const drawn = p.geometry.length + nodes.length;
    // A project SFMTA publishes a page for but does not map holds no blocks
    // (geometryKind "none"); its page says no geometry is published. Any
    // other project with nothing to draw is an empty shape.
    const unmapped = p.geometryKind === "none" && p.blocks === 0;
    if (drawn === 0 && !unmapped) errors.push(`E1 coordination.json: ${p.name} has nothing to draw`);
    if (drawn !== p.blocks) errors.push(`E3 coordination.json: ${p.name} draws ${drawn} of its ${p.blocks} blocks and intersections`);
  }
  return errors;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const errors = checkGeometry();
  for (const e of errors) console.error(`check-geometry: ${e}`);
  if (errors.length) process.exit(1);
  console.log("check-geometry: E1 and E3 pass");
}
