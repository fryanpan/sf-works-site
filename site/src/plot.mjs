// Every chart on the site is drawn with Observable Plot, the library
// fryanpan.com uses, and rendered to static SVG here at build time, so a chart
// shows with no script on the page (Bryan, 2026-09-30: "Use the same charting
// library as fryanpan.com" and "please stop rolling your own when we can use
// industry standard stuff"). Plot needs a DOM to draw into; linkedom supplies
// one in Node, and the SVG's markup is what the page carries.
//
// Each chart passes explicit width, height and margins, and explicit scale
// domains, so a figure sits where the chart's own arithmetic says it should
// and a label placed in pixels (dx, dy) lands beside the mark it names.
// Colours are the --seq-* tokens from layout.mjs, passed through as CSS
// variables, which Plot writes straight onto the marks.

import * as Plot from "@observablehq/plot";
import { parseHTML } from "linkedom";

const { document } = parseHTML("<!doctype html><html><body></body></html>");

export { Plot };

/**
 * Render a Plot specification to an SVG string.
 * `className` is added beside Plot's own class; `label` is the chart's
 * aria-label, read in place of the drawing (role="img").
 */
export function plotSVG(options, { className = "", label = "" } = {}) {
  const el = Plot.plot({ ...options, document });
  if (className) el.setAttribute("class", `${el.getAttribute("class")} plot-chart ${className}`.trim());
  else el.setAttribute("class", `${el.getAttribute("class")} plot-chart`);
  el.setAttribute("role", "img");
  if (label) el.setAttribute("aria-label", label);
  return el.outerHTML;
}

/** The inverse of a linear pixel mapping, for a label whose place is worked out in pixels. */
export const invert = (px, [d0, d1], [r0, r1]) => d0 + ((px - r0) * (d1 - d0)) / (r1 - r0);

/**
 * A chart's frame: width, height and margins, with linear x and y domains,
 * and the pixel-to-data inverses for labels placed by collision arithmetic.
 */
export function frame({ width, height, left, right, top, bottom, x, y }) {
  return {
    options: {
      width, height, marginLeft: left, marginRight: right, marginTop: top, marginBottom: bottom,
      x: { domain: x, axis: null }, y: { domain: y, axis: null },
    },
    // Pixel position of a data value, as Plot will draw it.
    px: (v) => left + ((width - left - right) * (v - x[0])) / (x[1] - x[0]),
    py: (v) => height - bottom - ((height - top - bottom) * (v - y[0])) / (y[1] - y[0]),
    X: (p) => invert(p, x, [left, width - right]),
    Y: (p) => invert(p, y, [height - bottom, top]),
  };
}

/**
 * One label whose baseline sits at pixel (px, py), as an SVG <text x y> would
 * put it. Plot centres a line on its anchor and drops the baseline 0.32em
 * below, so the anchor goes 0.32em above the baseline wanted.
 */
export function label(f, px, py, text, { fontSize = 13, ...opts } = {}) {
  return Plot.text([0], { x: () => f.X(px), y: () => f.Y(py - 0.32 * fontSize), text: () => text, fontSize, ...opts });
}

/** Dashed horizontal gridlines with their values at the left, and the zero line solid. */
export function yGrid(ticks, tickFormat = (v) => v, { zero = true } = {}) {
  return [
    Plot.gridY(ticks.filter((v) => v !== 0), { stroke: "var(--rule)", strokeOpacity: 1, strokeDasharray: "2 4" }),
    zero ? Plot.ruleY([0], { stroke: "var(--rule)" }) : null,
    Plot.axisY(ticks, { tickSize: 0, tickPadding: 8, tickFormat, label: null, fontSize: 13 }),
  ];
}

/** Labels under the x axis, no tick marks. */
export function xLabels(ticks, tickFormat = (v) => v, opts = {}) {
  return Plot.axisX(ticks, { tickSize: 0, tickPadding: 9, tickFormat, label: null, fontSize: 13, ...opts });
}

/** A text halo in the page colour, so a label stays legible where it crosses a line. */
export const HALO = { stroke: "var(--paper)", strokeWidth: 3 };
