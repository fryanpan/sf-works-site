// Route lines in SFMTA's own colours (GTFS route_color), with the route's badge repeated along each line in the
// shapes SFMTA's maps use: a Metro letter in a coloured circle, a bus or cable car number in a rounded rectangle
// (Rapid lines carry SFMTA's red). The colour says which line; the metric stays on the stop dots drawn above it.
// muniRoutes.add(map, source, before) adds the "routes" layer and muniRoutes.badges(...) the "route-badges" layer over a source whose features
// carry r (route), c (colour), t (text colour) and y (GTFS route_type); badge images are drawn on demand.
export const ROUTE_JS = `<script>
window.muniRoutes = {
  feats: function (lines) {
    var out = [];
    Object.keys(lines).forEach(function (r) { var L = lines[r]; (L.s || []).forEach(function (c) {
      out.push({ type: "Feature", properties: { r: r, c: L.c, t: L.t, y: L.y, p: L.p || "" }, geometry: { type: "LineString", coordinates: c } });
    }); });
    return sfMap.collection(out);
  },
  add: function (map, source, before, opts) {
    opts = opts || {};
    map.on("styleimagemissing", function (e) {
      if (e.id.indexOf("mb|") !== 0 || map.hasImage(e.id)) return;
      var p = e.id.split("|"), r = p[1], bg = p[2], fg = p[3], round = p[4] === "0";
      var k = 3, h = 17, w = round ? h : Math.max(h, 8 + 7 * r.length);
      var cv = document.createElement("canvas"); cv.width = w * k; cv.height = h * k;
      var g = cv.getContext("2d"); g.scale(k, k);
      g.fillStyle = bg; g.strokeStyle = "#fff"; g.lineWidth = 1.5;
      g.beginPath();
      if (round) g.arc(w / 2, h / 2, h / 2 - 1, 0, 2 * Math.PI);
      else { var x = 1, y = 1, ww = w - 2, hh = h - 2, rr = 4; g.moveTo(x + rr, y); g.arcTo(x + ww, y, x + ww, y + hh, rr); g.arcTo(x + ww, y + hh, x, y + hh, rr); g.arcTo(x, y + hh, x, y, rr); g.arcTo(x, y, x + ww, y, rr); g.closePath(); }
      g.fill(); g.stroke();
      g.fillStyle = fg; g.font = "700 11px system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(r, w / 2, h / 2 + 0.5);
      map.addImage(e.id, { width: cv.width, height: cv.height, data: g.getImageData(0, 0, cv.width, cv.height).data }, { pixelRatio: k });
    });
    map.addLayer({ id: "routes", type: "line", source: source, layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": ["get", "c"], "line-width": opts.width || ["interpolate", ["linear"], ["zoom"], 11, 1.6, 14, 3, 17, 5], "line-opacity": 0.8 } }, before);
  },
  // Badges go on last, above the stop dots, so a badge is never cut by a dot; they are sparse and skip collisions.
  badges: function (map, source, before, opts) {
    opts = opts || {};
    map.addLayer({ id: "route-badges", type: "symbol", source: source,
      layout: { "symbol-placement": "line", "symbol-spacing": opts.spacing || 220, "icon-image": ["concat", "mb|", ["get", "r"], "|", ["get", "c"], "|", ["get", "t"], "|", ["to-string", ["get", "y"]]],
        "icon-rotation-alignment": "viewport", "icon-allow-overlap": false, "icon-padding": 2 } }, before);
  },
};
</script>`;
