// Every map on the site is drawn by MapLibre GL JS over a vector basemap
// (Bryan, 2026-09-30: "Let's switch to MapLibre GL" and "please stop rolling
// your own when we can use industry standard stuff").
//
// The library is not a build dependency: it is
// loaded by the browser from a pinned CDN address with a subresource
// integrity hash, so a changed file at that address is refused rather than
// run. The map data rides in each page as inert JSON, in longitude and
// latitude (WGS84), and the page script turns it into GeoJSON sources.
//
// This file holds the three things every map shares:
//
//   BASEMAP      the one setting that picks the tiles under the data
//   MAP_HEAD     the library, its stylesheet and the browser helpers below
//   encodeRuns   a compact encoding for lines and points, decoded in the page
//
// The browser helpers are window.sfMap: create(el, opts) makes a map with the
// site's controls; decode(enc) gives back the lines; grow(units, z0, s0) is the
// zoom expression that keeps a line's width honest as the reader zooms in; and
// token(name) reads a colour token from the page, so the --seq-* scale in
// layout.mjs stays the one source of every map colour.

import fs from "node:fs";
import path from "node:path";

/** MapLibre GL JS, pinned. The hashes are of the files at these addresses (unpkg, 2026-09-30). */
const VERSION = "5.24.0";
export const CDN = `https://unpkg.com/maplibre-gl@${VERSION}/dist`;
export const JS_SRI = "sha384-5+cfbwT0iiub6VsQAdn6yz16nr6sDiQoHx6tm4O8OVYXHYOxcffFmCJBL0dgdvGp";
export const CSS_SRI = "sha384-uTttxo/aOKbdE5RlD/SPzSDoDmNvGlUYPjONi2MN/b7c9HPSvW07OIuyP7uL6jxK";

/**
 * The basemap: one setting, chosen at build time, and quiet either way
 * (Bryan, 2026-09-30: "The base map needs to be a lot more quiet and
 * subdued. Maybe monochrome so that the data show through. And remove all
 * neighborhood and city labels and other labels that are getting in the way.
 * Street names we need! Schools, libraries and parks yes! Otherwise, don't
 * need it.").
 *
 * "google": Google's roadmap from the Map Tiles API, restyled by
 * GOOGLE_STYLES, when the build has GOOGLE_MAPS_KEY in its environment. The
 * key is a browser key restricted by HTTP referrer to the public site, so it
 * is written into the built page (site/dist, never tracked) and never into
 * the repo. The page asks createSession for a session, then draws the 2D
 * roadmap tiles as a raster layer under the data, with the Google Maps logo
 * bottom left and the copyright line from the viewport endpoint bottom
 * right, as Google's Map Tiles policies require. If createSession fails, as
 * it does wherever the referrer list does not include the page's address,
 * the page falls back to Positron without saying so.
 *
 * "vector": OpenFreeMap's Positron, free, with no key and no account, made
 * monochrome in the page with the same keep-and-hide list (quiet() below). It
 * is the basemap when the build has no key, and the fallback when it has one.
 */
const POSITRON = "https://tiles.openfreemap.org/styles/positron";
const GOOGLE_KEY = (process.env.GOOGLE_MAPS_KEY || "").trim();
export const BASEMAP = GOOGLE_KEY ? { kind: "google", key: GOOGLE_KEY, fallback: POSITRON } : { kind: "vector", fallback: POSITRON };
const GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";
/**
 * Google's roadmap in light greys. Every label goes, then street names come
 * back in a mid grey, and schools, libraries and parks come back with their
 * icons greyed. Libraries are featureType poi.government: with every label
 * off but that one, a tile over Civic Center shows "San Francisco Main Public
 * Library" (checked 2026-09-30); the same type also names City Hall and post
 * offices. Neighbourhood, city, water and landform labels, every other point
 * of interest, transit and road shields stay off. Feature and element types
 * from the Map Tiles API style reference,
 * https://developers.google.com/maps/documentation/tile/style-reference
 * (read 2026-09-30); later entries override earlier ones.
 */
const QUIET_TEXT = "#8c8c8c";
/**
 * Schools, libraries and parks are named only from NEAR_ZOOM in, where a
 * reader is looking at a neighbourhood: at the city view Google prints its
 * large parks and campuses (Twin Peaks, McLaren Park, SF State) big enough to
 * compete with the data. Google's styles cannot vary by zoom, so the page
 * takes two sessions, one per style list, and draws each over its own range.
 * Positron's added layer starts at the same zoom.
 */
const NEAR_ZOOM = 14;
const GOOGLE_FAR = [
  { elementType: "geometry", stylers: [{ color: "#f4f4f4" }] },
  { elementType: "labels", stylers: [{ visibility: "off" }] },
  { featureType: "administrative", elementType: "geometry", stylers: [{ visibility: "off" }] },
  { featureType: "landscape.man_made", elementType: "geometry", stylers: [{ color: "#efefef" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#e4e4e4" }] },
  { featureType: "transit", elementType: "geometry", stylers: [{ color: "#e8e8e8" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#e0e0e0" }] },
  { featureType: "poi", elementType: "geometry", stylers: [{ color: "#eeeeee" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#e7ece5" }] },
  { featureType: "road", elementType: "labels.text", stylers: [{ visibility: "on" }] },
  { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: QUIET_TEXT }] },
  { featureType: "road", elementType: "labels.text.stroke", stylers: [{ color: "#ffffff" }] },
];
const GOOGLE_NEAR = [
  ...GOOGLE_FAR,
  ...["poi.school", "poi.government", "poi.park"].flatMap((featureType) => [
    { featureType, elementType: "labels", stylers: [{ visibility: "on" }] },
    { featureType, elementType: "labels.text.fill", stylers: [{ color: QUIET_TEXT }] },
    { featureType, elementType: "labels.text.stroke", stylers: [{ color: "#ffffff" }] },
    { featureType, elementType: "labels.icon", stylers: [{ saturation: -100 }, { lightness: 35 }] },
  ]),
];
/** The official Google Maps logo, outlined for a busy background (Google_Maps_Attribution_Assets.zip, read 2026-09-30). */
const GOOGLE_LOGO = GOOGLE_KEY
  ? "data:image/svg+xml;base64," + fs.readFileSync(path.join(import.meta.dirname, "google-maps-logo.svg")).toString("base64")
  : "";
/** Positron's attribution, written out for the fallback, where the page adds the style's layers itself. */
const POSITRON_CREDIT = '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">&copy; OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';

// ---- Encoding -----------------------------------------------------------------
//
// A coordinate is kept as a whole number of 1e-5 degrees, the precision the
// data files carry (about a metre), and each point is written as its offset
// from the point before, which is one or two digits for a city block where
// the absolute value is eight. The page sums the offsets back to the same
// numbers. Lossless at the precision of the data.

const STEP = 1e5;
const q = (v) => Math.round(v * STEP);

/** Douglas-Peucker on integer points, dropping only vertices within `tol` steps of a straight line. */
function simplify(run, tol) {
  if (!tol || run.length < 3) return run;
  const keep = new Uint8Array(run.length);
  keep[0] = keep[run.length - 1] = 1;
  const stack = [[0, run.length - 1]];
  while (stack.length) {
    const [i, j] = stack.pop();
    const [ax, ay] = run[i], [bx, by] = run[j], L = Math.hypot(bx - ax, by - ay);
    let far = -1, at = -1;
    for (let m = i + 1; m < j; m++) {
      const off = L ? Math.abs((bx - ax) * (ay - run[m][1]) - (ax - run[m][0]) * (by - ay)) / L : Math.hypot(run[m][0] - ax, run[m][1] - ay);
      if (off > far) { far = off; at = m; }
    }
    if (far > tol) { keep[at] = 1; stack.push([i, at], [at, j]); }
  }
  return run.filter((_, k) => keep[k]);
}

/**
 * Lines ([[lon, lat], ...] each) as {n: [points per run], d: [offsets]}.
 * Consecutive repeats are dropped; a run left with one point stays, as a
 * run of one, which the page draws as a dot (a block too short to span a
 * metre, or an intersection). `tol` thins straight stretches, in steps.
 */
export function encodeRuns(runs, { tol = 0 } = {}) {
  const n = [], d = [];
  let cx = 0, cy = 0;
  for (const run of runs) {
    const pts = [];
    for (const c of run) {
      const p = [q(c[0]), q(c[1])], l = pts[pts.length - 1];
      if (!l || l[0] !== p[0] || l[1] !== p[1]) pts.push(p);
    }
    if (!pts.length) continue;
    const kept = simplify(pts, tol);
    n.push(kept.length);
    for (const [x, y] of kept) { d.push(x - cx, y - cy); cx = x; cy = y; }
  }
  return { n, d };
}

/** Points ([lon, lat] each) as one offset list. */
export const encodePoints = (pts) => encodeRuns(pts.map((p) => [p])).d;

/** Bounds [[west, south], [east, north]] of lines. */
export function boundsOf(runs) {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const run of runs) for (const [x, y] of run) {
    if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y;
  }
  return [[w, s], [e, n]];
}

/** JSON for a <script type="application/json">: "<" escaped so nothing in it can close the element. */
export const inlineJson = (v) => JSON.stringify(v).replace(/</g, "\\u003c");

// ---- The page side --------------------------------------------------------------

export const BROWSER = `
(function () {
  var STEP = ${STEP}, BASEMAP = ${JSON.stringify(BASEMAP)}, GLYPHS = ${JSON.stringify(GLYPHS)};
  var LOGO = ${JSON.stringify(GOOGLE_LOGO)}, GSTYLES = ${JSON.stringify({ far: GOOGLE_FAR, near: GOOGLE_NEAR })}, NEAR_ZOOM = ${NEAR_ZOOM}, QUIET_TEXT = ${JSON.stringify(QUIET_TEXT)}, POSITRON_CREDIT = ${JSON.stringify(POSITRON_CREDIT)};
  // A copy of a block mounted on another site carries its colours on .sfw
  // rather than :root (scripts/export-post.mjs), so read them there first.
  var css = getComputedStyle(document.querySelector(".sfw") || document.documentElement), memo = {};
  // A token from layout.mjs, read once: the site has one theme.
  function token(name) { return memo[name] || (memo[name] = css.getPropertyValue(name).trim()); }
  var GOOGLE = BASEMAP.kind === "google";
  // A map opens on an empty style, so the page script adds its data layers
  // at once; the basemap goes in beneath them when Google's session (or
  // Positron) arrives.
  function style() { return { version: 8, glyphs: GLYPHS, sources: {}, layers: [] }; }
  // ---- Google's Map Tiles API ----
  var API = "https://tile.googleapis.com", sessions = {}, positron = null;
  function json(r) { if (!r.ok) throw new Error(r.url.split("?")[0] + " " + r.status); return r.json(); }
  // One session per page: a session serves every map on it, for two weeks.
  function googleSession(which) {
    if (sessions[which]) return sessions[which];
    var hi = (window.devicePixelRatio || 1) > 1;
    sessions[which] = fetch(API + "/v1/createSession?key=" + encodeURIComponent(BASEMAP.key), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mapType: "roadmap", language: "en-US", region: "US", scale: hi ? "scaleFactor2x" : "scaleFactor1x", highDpi: hi, styles: GSTYLES[which] }),
    }).then(json).then(function (s) { if (!s.session) throw new Error("createSession: no session"); return s; });
    return sessions[which];
  }
  function ready(map, fn) { if (map.sfGone) return; if (map.sfLoaded) fn(); else map.once("load", function () { if (!map.sfGone) fn(); }); }
  function firstLayer(map) { var ls = map.getStyle().layers || []; return ls.length ? ls[0].id : undefined; }
  function googleBase(map, credit) {
    Promise.all([googleSession("far"), googleSession("near")]).then(function (both) {
      ready(map, function () {
        var key = "&key=" + encodeURIComponent(BASEMAP.key);
        var qs = both.map(function (s) { return "session=" + encodeURIComponent(s.session) + key; });
        var first = firstLayer(map);
        map.addSource("google-far", { type: "raster", tileSize: 256, maxzoom: 22, tiles: [API + "/v1/2dtiles/{z}/{x}/{y}?" + qs[0]] });
        map.addSource("google-near", { type: "raster", tileSize: 256, maxzoom: 22, tiles: [API + "/v1/2dtiles/{z}/{x}/{y}?" + qs[1]] });
        map.addLayer({ id: "google-far", type: "raster", source: "google-far", maxzoom: NEAR_ZOOM }, first);
        map.addLayer({ id: "google-near", type: "raster", source: "google-near", minzoom: NEAR_ZOOM }, first);
        var logo = document.createElement("div");
        logo.className = "maplibregl-ctrl sf-glogo";
        logo.innerHTML = '<img src="' + LOGO + '" alt="Google Maps" height="18">';
        map.addControl({ onAdd: function () { return logo; }, onRemove: function () { logo.remove(); } }, "bottom-left");
        // The copyright line for what is in view, from the viewport endpoint,
        // asked again when the reader stops moving the map.
        var asked = 0;
        function copyright() {
          var b = map.getBounds(), n = ++asked, q = qs[map.getZoom() >= NEAR_ZOOM ? 1 : 0];
          // A 256-pixel raster tile is drawn one zoom level above the map's own.
          var z = Math.max(0, Math.min(22, Math.round(map.getZoom()) + 1));
          fetch(API + "/tile/v1/viewport?" + q + "&zoom=" + z + "&north=" + b.getNorth() + "&south=" + b.getSouth() + "&east=" + b.getEast() + "&west=" + b.getWest())
            .then(json).then(function (v) { if (n === asked) credit.textContent = v.copyright || "Map data \u00a9 Google"; })
            .catch(function () { if (n === asked && !credit.textContent) credit.textContent = "Map data \u00a9 Google"; });
        }
        copyright();
        map.fire(new maplibregl.Event("sfbasemap"));
        map.on("moveend", copyright);
      });
    }).catch(function (e) {
      if (window.console) console.info("map: Google basemap unavailable here (" + (e && e.message) + "); using Positron");
      positronBase(map, credit);
    });
  }
  // Positron in greys: each colour to its own lightness, water and parks
  // set by hand, every label but street names dropped, and a layer added
  // for schools, libraries and parks.
  var ink = null;
  function grey(c) {
    ink = ink || document.createElement("canvas").getContext("2d");
    ink.fillStyle = "#000"; ink.fillStyle = c;
    var v = ink.fillStyle, m = v.charAt(0) === "#" ? [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16), 1] : v.match(/[\\d.]+/g).map(Number);
    var y = Math.round(0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]);
    return "rgba(" + y + "," + y + "," + y + "," + (m.length > 3 ? m[3] : 1) + ")";
  }
  function mono(v) {
    if (typeof v === "string" && /^(#|rgb|hsl)/.test(v)) return grey(v);
    return Array.isArray(v) ? v.map(mono) : v;
  }
  var SET = { background: "#f4f4f4", water: "#e0e0e0", park: "#e7ece5" };
  function quiet(st) {
    var layers = st.layers.filter(function (l) { return l.type !== "symbol" || /^highway-name-/.test(l.id); }).map(function (l) {
      l = JSON.parse(JSON.stringify(l));
      Object.keys(l.paint || {}).forEach(function (k) { if (/-color$/.test(k)) l.paint[k] = mono(l.paint[k]); });
      if (SET[l.id]) l.paint[l.type === "background" ? "background-color" : "fill-color"] = SET[l.id];
      if (l.type === "symbol") l.paint["text-color"] = QUIET_TEXT;
      return l;
    });
    layers.push({ id: "poi-quiet", type: "symbol", source: "openmaptiles", "source-layer": "poi", minzoom: NEAR_ZOOM,
      // By subclass: OpenMapTiles files bookshops under class "library" and preschools under "school".
      filter: ["match", ["get", "subclass"], ["school", "college", "university", "library", "park"], true, false],
      layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Italic"], "text-size": 11, "text-max-width": 8 },
      paint: { "text-color": QUIET_TEXT, "text-halo-color": "#ffffff", "text-halo-width": 1 } });
    return { sprite: st.sprite, sources: st.sources, layers: layers };
  }
  // Positron added under the data layers by hand, its street names above them.
  function positronBase(map, credit) {
    positron = positron || fetch(BASEMAP.fallback).then(json).then(quiet);
    positron.then(function (st) {
      ready(map, function () {
        if (st.sprite && map.setSprite) map.setSprite(st.sprite);
        var first = firstLayer(map);
        Object.keys(st.sources).forEach(function (k) { if (!map.getSource(k)) map.addSource(k, st.sources[k]); });
        st.layers.forEach(function (l) { map.addLayer(l, l.type === "symbol" ? undefined : first); });
        credit.innerHTML = POSITRON_CREDIT;
        map.fire(new maplibregl.Event("sfbasemap"));
      });
    }).catch(function (e) { if (window.console) console.warn("map: no basemap", e && e.message); });
  }
  function decode(enc) {
    var out = [], x = 0, y = 0, k = 0;
    for (var r = 0; r < enc.n.length; r++) {
      var run = [];
      for (var i = 0; i < enc.n[r]; i++, k += 2) { x += enc.d[k]; y += enc.d[k + 1]; run.push([x / STEP, y / STEP]); }
      out.push(run);
    }
    return out;
  }
  function points(d) {
    var out = [], x = 0, y = 0;
    for (var i = 0; i < d.length; i += 2) { x += d[i]; y += d[i + 1]; out.push([x / STEP, y / STEP]); }
    return out;
  }
  // Runs as features: two or more points a line, one point a dot.
  function features(runs, props) {
    return runs.map(function (r) {
      return { type: "Feature", properties: props || {}, geometry: r.length > 1 ? { type: "LineString", coordinates: r } : { type: "Point", coordinates: r[0] } };
    });
  }
  function collection(f) { return { type: "FeatureCollection", features: f }; }
  // A width or radius given in the drawing's own units at the opening view
  // (s0 pixels per unit at zoom z0) that grows as the fourth root of the
  // zoom factor: zoomed in, the map's detail spreads apart rather than
  // swelling, as the SVG maps did (Bryan, 2026-09-28: zoomed in, lines
  // "shouldn't look super fat"). value may be an expression.
  function grow(value, z0, s0) {
    var lo = typeof value === "number" ? value * s0 * 0.5 : ["*", value, s0 * 0.5];
    var hi = typeof value === "number" ? value * s0 * 4 : ["*", value, s0 * 4];
    return ["interpolate", ["exponential", Math.pow(2, 0.25)], ["zoom"], z0 - 4, lo, z0 + 8, hi];
  }
  // The pixels per drawing unit a factor of 2^(zoom - z0) gives at the opening view.
  function growAt(z, z0) { return Math.pow(2, (z - z0) / 4); }
  function supported() { return !!(window.maplibregl && (!maplibregl.supported || maplibregl.supported({ failIfMajorPerformanceCaveat: false }))); }
  function fallback(el, why) {
    el.classList.add("glmap-off");
    el.innerHTML = '<p class="glmap-msg">' + (why || "This map needs a browser with WebGL. The figures beside it read the same without it.") + "</p>";
  }
  // The site's map: the basemap, a + / − / Reset group, visible attribution,
  // and the wheel left to the page unless Ctrl or Cmd is held (a trackpad
  // pinch sends Ctrl), so a reader scrolling past is not caught zooming. On a
  // phone one finger scrolls the page and two move the map.
  //
  // Not in a frame a board doc draws (the board adds cw-embed=1 to its
  // address). That frame takes no touch until the reader taps "Tap to
  // interact", and it is as tall as its page, so a drag left to the page
  // there scrolls the doc out from under the reader and never moves the map.
  function gated() { return /[?&]cw-embed=1(&|$)/.test(location.search); }
  function create(el, opts) {
    if (!supported()) { fallback(el); return null; }
    var map = new maplibregl.Map({
      container: el, style: style(), bounds: opts.bounds, fitBoundsOptions: { padding: opts.padding ? opts.padding() : 0 },
      attributionControl: false, cooperativeGestures: opts.cooperative !== false && !gated(),
      dragRotate: false, pitchWithRotate: false, touchPitch: false, maxZoom: opts.maxZoom || 18,
      interactive: opts.interactive !== false, fadeDuration: 0,
    });
    el.sfGL = map; // for a page script or a test that needs the map behind an element
    map.once("load", function () { map.sfLoaded = true; });
    var drop = map.remove; map.remove = function () { map.sfGone = true; return drop.apply(map, arguments); };
    // The credit line goes in before any other control, so it sits at the very foot.
    var att = document.createElement("div");
    att.className = "maplibregl-ctrl maplibregl-ctrl-attrib sf-gattrib";
    att.innerHTML = '<div class="maplibregl-ctrl-attrib-inner"></div>';
    map.addControl({ onAdd: function () { return att; }, onRemove: function () { att.remove(); } }, "bottom-right");
    if (GOOGLE) googleBase(map, att.firstChild); else positronBase(map, att.firstChild);
    if (map.touchZoomRotate) map.touchZoomRotate.disableRotation();
    if (map.keyboard) map.keyboard.disableRotation();
    if (opts.interactive !== false) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), opts.controls || "top-right");
      var home = function () { map.fitBounds(opts.bounds, { padding: opts.padding ? opts.padding() : 0, duration: 400 }); };
      map.addControl({
        onAdd: function () {
          var d = document.createElement("div"); d.className = "maplibregl-ctrl maplibregl-ctrl-group sf-reset";
          d.innerHTML = '<button type="button" aria-label="Show all of San Francisco">Reset</button>';
          d.firstChild.addEventListener("click", function () { home(); if (opts.onReset) opts.onReset(); });
          return d;
        }, onRemove: function () {},
      }, opts.controls || "top-right");
      map.sfHome = home;
    }
    map.on("error", function (e) { if (window.console) console.warn("map:", e && e.error && e.error.message); });
    return map;
  }
  // The first label layer of the basemap, so data draws under the street
  // names and the names stay readable over it.
  function under(map) {
    var ls = map.getStyle().layers || [];
    for (var i = 0; i < ls.length; i++) if (ls[i].type === "symbol") return ls[i].id;
    return undefined;
  }
  // Screen pixels per drawing unit at the opening view, from the bounds
  // that unit was defined against: width units across (west, east).
  function unitPx(map, bounds, widthUnits) {
    var a = map.project([bounds[0][0], (bounds[0][1] + bounds[1][1]) / 2]), b = map.project([bounds[1][0], (bounds[0][1] + bounds[1][1]) / 2]);
    return Math.abs(b.x - a.x) / widthUnits;
  }
  // Rendered features of the given layers near a point, searching outward to
  // about 12 pixels: a thin line is hard to hit with a finger.
  function near(map, pt, layers) {
    for (var r = 3; r <= 12; r += 3) {
      var f = map.queryRenderedFeatures([[pt.x - r, pt.y - r], [pt.x + r, pt.y + r]], { layers: layers });
      if (f.length) return f;
    }
    return [];
  }
  // The screen box of a set of lines, relative to the map's container.
  function screenBox(map, runs) {
    var b = null;
    runs.forEach(function (run) { run.forEach(function (c) {
      var p = map.project(c);
      b = b ? { l: Math.min(b.l, p.x), r: Math.max(b.r, p.x), t: Math.min(b.t, p.y), b: Math.max(b.b, p.y) } : { l: p.x, r: p.x, t: p.y, b: p.y };
    }); });
    return b;
  }
  window.sfMap = { create: create, decode: decode, points: points, features: features, collection: collection, grow: grow, growAt: growAt,
    token: token, under: under, unitPx: unitPx, near: near, screenBox: screenBox, fallback: fallback };
})();`;

/** The site's map controls and messages, over MapLibre's own stylesheet. */
export const MAP_CSS = `<style>
.glmap { position: relative; background: var(--raised); border-radius: 4px; overflow: hidden; }
.glmap .maplibregl-ctrl-group button { width: 32px; height: 32px; }
.glmap .sf-reset button { width: auto; padding: 0 9px; font: inherit; font-size: 0.85rem; font-weight: 600; color: var(--ink); }
.glmap .maplibregl-ctrl-attrib { font-size: 0.68rem; }
.glmap .maplibregl-cooperative-gesture-screen { font-size: 0.95rem; }
/* Phones: the + / − / Reset buttons in one small row, as the SVG maps had
   them, and the attribution on one short line, so both cover less map. */
@media (max-width: 700px) {
  .glmap .maplibregl-ctrl-top-right, .glmap .maplibregl-ctrl-bottom-right { display: flex; flex-direction: row-reverse; align-items: flex-end; }
  .glmap .maplibregl-ctrl-top-right { align-items: flex-start; }
  .glmap .maplibregl-ctrl-top-right .maplibregl-ctrl, .glmap .maplibregl-ctrl-bottom-right .maplibregl-ctrl-group { margin: 6px 6px 0 0; }
  .glmap .maplibregl-ctrl-group { display: flex; }
  .glmap .maplibregl-ctrl-group button { width: 28px; height: 28px; }
  .glmap .sf-reset button { width: auto; }
  .glmap .maplibregl-ctrl-group button + button { border-top: 0; border-left: 1px solid #ddd; }
  .glmap .maplibregl-ctrl-attrib { font-size: 0.58rem; }
  .glmap .maplibregl-ctrl-bottom-right .maplibregl-ctrl-attrib { margin: 0; }
}
/* Google's terms: the logo 16 to 19 px tall, with 10 px clear on the left,
   right and top and 5 px below, and the credit line in full. Both sit above
   anything a page lays over its map. */
.glmap .maplibregl-ctrl-bottom-left, .glmap .maplibregl-ctrl-bottom-right { z-index: 3; }
.glmap .sf-glogo { margin: 10px 10px 5px 10px !important; line-height: 0; pointer-events: none; }
.glmap .sf-glogo img { height: 18px; width: auto; display: block; }
.glmap-off { display: flex; align-items: center; justify-content: center; }
.glmap-msg { margin: 0; padding: 16px; max-width: 32em; text-align: center; color: var(--muted); font-size: 0.9rem; }
</style>`;

/** The library, its stylesheet, the site's map styles and window.sfMap. Once per page, before any map script. */
export const MAP_HEAD = `<link rel="stylesheet" href="${CDN}/maplibre-gl.css" integrity="${CSS_SRI}" crossorigin="anonymous">
${MAP_CSS}
<script src="${CDN}/maplibre-gl.js" integrity="${JS_SRI}" crossorigin="anonymous"></script>
<script>${BROWSER}</script>`;
