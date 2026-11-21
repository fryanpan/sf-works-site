// The plan's network on a MapLibre map, from the traced GeoJSON, with the
// street segments a page marks drawn over it (src/maplibre.mjs).
//
// The basemap carries the streets, parks, water and street names; the lines
// drawn over it are the same data the figures are computed from rather than a
// second copy that can drift.
//
// The trace aligns one MultiLineString part to one CNN, so a segment can be
// drawn exactly rather than by lighting up the whole corridor it sits on.

import fs from "node:fs";
import path from "node:path";
import { encodeRuns, boundsOf, inlineJson } from "./maplibre.mjs";
import { esc } from "./html.mjs";

const net = JSON.parse(
  fs.readFileSync(
    path.join(import.meta.dirname, "..", "data", "north-star", "segments.geojson"),
    "utf8",
  ),
);

const W = 1000;

// Equirectangular, scaled at the city's own latitude: a drawing unit is the
// same distance across and up. Pages use it to measure on the map (a project
// map's frame, how far apart two callouts sit); the map itself is drawn by
// MapLibre in longitude and latitude.
function projector(features) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const f of features) {
    for (const part of f.geometry.coordinates) {
      for (const [x, y] of part) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  const k = Math.cos((((y0 + y1) / 2) * Math.PI) / 180);
  const scale = W / ((x1 - x0) * k);
  const height = Math.round((y1 - y0) * scale);
  return {
    height,
    point: ([x, y]) => [(x - x0) * k * scale, (y1 - y) * scale],
    lonlat: ([px, py]) => [x0 + px / (k * scale), y1 - py / scale],
  };
}

const P = projector(net.features);

/** The network's extent, in drawing units, and the projection to and from them. */
export const MAP_W = W;
export const MAP_H = P.height;
export const projectPoint = (c) => P.point(c);
export const unprojectPoint = (p) => P.lonlat(p);

/** Every part of the traced network, as [[lon, lat], ...] lines. */
const netRuns = () => net.features.flatMap((f) => f.geometry.coordinates);

/** The whole network, encoded. `tol` thins straight stretches, in 1e-5 degree steps. */
export const planNetwork = (tol = 0) => encodeRuns(netRuns(), { tol });

/** The network's bounds, [[west, south], [east, north]]. */
export const NET_BOUNDS = boundsOf(netRuns());

/** `{cnn: [[lon, lat], ...]}` for every CNN the traced network covers. */
export function lines() {
  const out = {};
  for (const f of net.features) {
    f.properties.cnns.forEach((cnn, i) => {
      const l = f.geometry.coordinates[i];
      if (l && l.length > 1) out[cnn] = l;
    });
  }
  return out;
}

const attr = (s) => esc(s ?? "");

/**
 * A pannable, zoomable map of the network with the marked segments over it.
 * Each segment carries its street, its block and its verdict, so tapping a
 * line says what it is.
 *
 * @param {{cnn: string, status: string, street: string, block: string,
 *          wants: string, has: string, repaved: string}[]} marks
 * @param {string} label What the map shows, for a screen reader.
 * @param {{keepColour?: boolean}} opts keepColour: a picked segment keeps its
 *   category's colour rather than turning ink (the Departments page, where
 *   the job's other blocks carry the selection).
 */
export function segMap(marks, label, opts = {}) {
  const byCnn = lines();
  // A mark may carry its own centreline for a block the traced network lacks.
  for (const m of marks) if (!byCnn[m.cnn] && m.line && m.line.length > 1) byCnn[m.cnn] = m.line;
  const drawn = marks.filter((m) => byCnn[m.cnn]);

  // Drawn worst first, so a better verdict is never hidden under a worse one
  // where two segments meet.
  const order = { unrated: -1, already: -1, none: 0, short: 1, meets: 2, met: 2 };
  const sorted = [...drawn].sort((a, b) => order[a.status] - order[b.status]);
  const data = {
    bounds: NET_BOUNDS,
    base: planNetwork(),
    lines: encodeRuns(sorted.map((m) => byCnn[m.cnn])),
    keepColour: !!opts.keepColour,
    props: sorted.map((m) => {
      const p = { cnn: String(m.cnn), status: m.status === "meets" ? "met" : m.status };
      for (const k of ["street", "block", "wants", "has", "repaved", "stage", "job"]) if (m[k]) p[k] = m[k];
      if (m.readout) p.say = m.readout;
      return p;
    }),
  };

  return {
    missing: marks.length - drawn.length,
    html: `<figure class="mapbox seg-map">
  <div class="glmap seg-gl" role="img" aria-label="${attr(label)}"></div>
  <p class="map-readout" data-readout>Tap a colored street to see what it is.</p>
  <script type="application/json" data-seg-data>${inlineJson(data)}</script>
</figure>`,
  };
}

/**
 * The script for every .seg-map on a page. Each map listens to the nearest
 * element above it with data-show (the stage on show) and data-cat (the
 * category a bar has picked), so a page drives the map by setting those, and
 * exposes box.sfSeg for the rest:
 *
 *   job(cnns)   draw those segments of the stage on show on top, wider, and
 *               fade the rest; null clears it
 *   box()       the screen box of what job() drew, relative to the map
 *   onMove(fn)  called as the reader pans or zooms
 *
 * A tap on a segment shows its sentence under the map and dispatches
 * "seg-pick" on the figure, with {dataset: the segment's fields} or null.
 */
export const SEG_MAP_SCRIPT = `<script>
(function () {
  document.querySelectorAll(".seg-map").forEach(function (box) {
    var el = box.querySelector(".seg-gl"), D = JSON.parse(box.querySelector("[data-seg-data]").textContent);
    var readout = box.querySelector("[data-readout]"), host = box.closest("[data-show]");
    var runs = sfMap.decode(D.lines), base = sfMap.decode(D.base);
    // The view is part of the address. Each map on a page has its own key, so
    // a link to a zoomed-in block on one map does not move the other.
    var key = "map" + (box.id ? "-" + box.id : "");
    var asked = (new URLSearchParams(location.search).get(key) || "").split(",").map(Number);
    var map = sfMap.create(el, { bounds: D.bounds, padding: function () { return 8; } });
    if (!map) return;
    if (asked.length === 3 && asked[0] > -123 && asked[0] < -122 && asked[1] > 37 && asked[1] < 38 && asked[2] > 9 && asked[2] < 19) map.jumpTo({ center: [asked[0], asked[1]], zoom: asked[2] });
    var pending = null;
    map.on("moveend", function () {
      clearTimeout(pending);
      pending = setTimeout(function () {
        var p = new URLSearchParams(location.search), c = map.getCenter();
        var home = map.cameraForBounds(D.bounds, { padding: 8 }), hc = maplibregl.LngLat.convert(home.center);
        var atHome = Math.abs(map.getZoom() - home.zoom) < 0.02 && Math.abs(c.lng - hc.lng) < 1e-4 && Math.abs(c.lat - hc.lat) < 1e-4;
        if (atHome) p.delete(key);
        else p.set(key, [c.lng.toFixed(5), c.lat.toFixed(5), map.getZoom().toFixed(2)].join(","));
        var q = p.toString() ? "?" + p.toString() : "";
        if (q === location.search) return;
        history.replaceState(null, "", location.pathname + q + location.hash);
        window.dispatchEvent(new CustomEvent("sfworks:state", { detail: q + location.hash }));
      }, 150);
    });
    var feats = runs.map(function (r, i) {
      var props = D.props[i]; props.i = i;
      return { type: "Feature", properties: props, geometry: r.length > 1 ? { type: "LineString", coordinates: r } : { type: "Point", coordinates: r[0] } };
    });
    var state = { stage: host ? host.dataset.show || null : null, cat: host ? host.dataset.cat || null : null, job: null, picked: -1, ready: false };
    var COL = { met: "--seq-3", short: "--seq-2", none: "--seq-1" };
    function colour() {
      return ["match", ["get", "status"], "met", sfMap.token(COL.met), "short", sfMap.token(COL.short), "none", sfMap.token(COL.none),
        "already", D.keepColour ? "#b3b8bf" : sfMap.token("--muted"), sfMap.token("--muted")];
    }
    function stageFilter() { return state.stage ? ["==", ["get", "stage"], state.stage] : true; }
    function apply() {
      if (!state.ready) return;
      var f = stageFilter(), jobOn = state.job && state.job.length;
      map.setFilter("segs", ["all", ["==", ["geometry-type"], "LineString"], f]);
      map.setFilter("segs-dot", ["all", ["==", ["geometry-type"], "Point"], f]);
      map.setFilter("segs-top", ["all", f, ["in", ["get", "cnn"], ["literal", jobOn ? state.job : []]]]);
      map.setFilter("segs-on", ["==", ["get", "i"], D.keepColour ? -1 : state.picked]);
      // Unrated and already-done blocks sit back; a picked category or job
      // fades the rest.
      var op = ["case", ["in", ["get", "status"], ["literal", ["unrated"].concat(D.keepColour ? [] : ["already"])]], 0.45, 1];
      if (jobOn) op = 0.12;
      else if (state.cat) op = ["case", ["==", ["get", "status"], state.cat], 1, 0.1];
      map.setPaintProperty("segs", "line-opacity", op);
      map.setPaintProperty("segs-dot", "circle-opacity", op);
      map.setPaintProperty("segs", "line-width", state.cat && !jobOn ? ["case", ["==", ["get", "status"], state.cat], 6.5, 4.5] : 4.5);
    }
    map.on("load", function () {
      var before = sfMap.under(map);
      map.addSource("plan", { type: "geojson", data: sfMap.collection(sfMap.features(base)) });
      map.addSource("segs", { type: "geojson", data: sfMap.collection(feats) });
      map.addLayer({ id: "plan", type: "line", source: "plan", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#8d949d", "line-opacity": 0.7, "line-width": 1 } }, before);
      map.addLayer({ id: "segs", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colour(), "line-width": 4.5 } }, before);
      map.addLayer({ id: "segs-dot", type: "circle", source: "segs", paint: { "circle-color": colour(), "circle-radius": 3 } }, before);
      map.addLayer({ id: "segs-top", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colour(), "line-width": 8 } }, before);
      map.addLayer({ id: "segs-on", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": sfMap.token("--ink"), "line-width": 4.5 } }, before);
      state.ready = true; apply();
    });
    if (host && window.MutationObserver) new MutationObserver(function () {
      state.stage = host.dataset.show || null; state.cat = host.dataset.cat || null; apply();
    }).observe(host, { attributes: true, attributeFilter: ["data-show", "data-cat"] });
    function say(p) {
      // A page that has already written its own sentence for a line passes it;
      // otherwise the fields.
      return p.say ? p.say : "<strong>" + p.street + "</strong> " + p.block + " · repaved " + p.repaved + " · plan wants " + p.wants + " · on the ground: " + p.has;
    }
    map.on("click", function (e) {
      if (!state.ready) return;
      var hit = sfMap.near(map, e.point, ["segs-top", "segs", "segs-dot"])[0] || null;
      var p = hit ? D.props[hit.properties.i] : null;
      if (p && readout) { readout.innerHTML = say(p); state.picked = p.i; apply(); }
      box.dispatchEvent(new CustomEvent("seg-pick", { detail: p ? { dataset: p } : null }));
    });
    map.on("mousemove", function (e) {
      if (!state.ready) return;
      map.getCanvas().style.cursor = sfMap.near(map, e.point, ["segs-top", "segs", "segs-dot"]).length ? "pointer" : "";
    });
    var movers = [];
    map.on("move", function () { movers.forEach(function (fn) { fn(); }); });
    box.sfSeg = {
      job: function (cnns) { state.job = cnns ? cnns.map(String) : null; apply(); },
      box: function () {
        if (!state.job) return null;
        var set = {}; state.job.forEach(function (c) { set[c] = 1; });
        var sel = runs.filter(function (r, i) { var p = D.props[i]; return set[p.cnn] && (!state.stage || p.stage === state.stage); });
        return sel.length ? sfMap.screenBox(map, sel) : null;
      },
      onMove: function (fn) { movers.push(fn); },
      reset: function () { if (readout) readout.textContent = "Tap a colored street to see what it is."; state.picked = -1; apply(); },
    };
  });
})();
</script>`;
