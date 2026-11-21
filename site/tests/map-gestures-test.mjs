#!/usr/bin/env node
// Tests which gestures sfMap.create asks MapLibre for: one finger scrolls the page on the site, and moves the map
// in a frame a board doc draws (cw-embed=1), where the board's own "Tap to interact" already guards the scroll.
//
//   node site/tests/map-gestures-test.mjs
import assert from "node:assert/strict";
import vm from "node:vm";
import { pathToFileURL } from "node:url";
import path from "node:path";

import { SITE } from "../scripts/lib/repo.mjs";
const { BROWSER } = await import(pathToFileURL(path.join(SITE, "src/maplibre.mjs")).href);

/** The options sfMap.create hands MapLibre on a page at this query string. */
function optionsAt(search, opts = {}) {
  let seen = null;
  const el = () => ({ className: "", innerHTML: "", classList: { add() {} }, firstChild: { addEventListener() {} }, remove() {} });
  class Map {
    constructor(o) { seen = o; this.touchZoomRotate = { disableRotation() {} }; this.keyboard = { disableRotation() {} }; }
    once() {} on() {} addControl() {} remove() {} fitBounds() {}
  }
  const maplibregl = { Map, NavigationControl: class {}, supported: () => true };
  const win = { maplibregl, console: { warn() {}, info() {} } };
  const ctx = {
    window: win, maplibregl, location: { search },
    document: { querySelector: () => null, documentElement: {}, createElement: el },
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
    fetch: () => new Promise(() => {}), setTimeout, clearTimeout, console: win.console,
  };
  vm.runInNewContext(BROWSER, ctx);
  win.sfMap.create(el(), { bounds: [[-122.52, 37.7], [-122.35, 37.84]], ...opts });
  assert.ok(seen, "sfMap.create made a map");
  return seen;
}

assert.equal(optionsAt("").cooperativeGestures, true, "on the site one finger scrolls the page");
assert.equal(optionsAt("?block=x").cooperativeGestures, true, "another query leaves that alone");
assert.equal(optionsAt("?cw-embed=10").cooperativeGestures, true, "only cw-embed=1 is the board's mark");
assert.equal(optionsAt("", { cooperative: false }).cooperativeGestures, false, "a page may still turn it off");
assert.equal(optionsAt("?cw-frame=1&cw-embed=1").cooperativeGestures, false, "in a board doc's frame one finger moves the map");
assert.equal(optionsAt("?cw-embed=1&block=x", { cooperative: true }).cooperativeGestures, false, "and a page asking for it does not bring the doc scroll back");
console.log("map-gestures-test: 6 cases pass");
