// The Street Safety map: one MapLibre map of every person severely injured or killed on San Francisco streets, with
// the High Injury Networks, traffic stress, bike comfort and crime views and a whole-map area, time and day filter, driven by one
// state object (src/safety-map/state.js). The dashboard (/transportation/street-safety) and the article story block
// (src/safety-map/story.mjs) both mount it.
//
// Self-contained, so it can move into the shared maps package (M7) unchanged:
//   - nothing here reads a page global; MapLibre, the basemap helpers (the site's sfMap) and the crash cards are
//     passed in, and the data comes as an object or a URL;
//   - every colour is a CSS custom property on the map's element, with the site's values as defaults (COLOURS);
//   - in a sandboxed frame with no referrer the basemap helper falls back to Positron, and the data can be passed
//     inline, so a frame that cannot fetch still draws.
//
//   var ctl = SafetyMap.create(el, { lib: maplibregl, basemap: sfMap, cards: CrashCards, state: SafetyMapState,
//     data | dataUrl, crashes | crashesUrl, initial, hash, cardHost, sheetHost, routes, onChange });
//   crashesUrl: the folder of card files; crashes: the board copy's inline { file: { case: card } }.
//   ctl.ready.then(...); ctl.getState(); ctl.setState(partial, { duration, replace }); ctl.figures(); ctl.keyHTML();
//   ctl.chart() (the corner chart's PlotChart props); ctl.drawArea() (draw an area filter with terra-draw).
//   ctl.chartHover(key) and ctl.chartPick(key) link the corner chart to the map (Bryan, 2026-11-19: "brushing on a
//   bar in the distribution chart highlights items on the map. Clicking on the distribution chart filters on only
//   those items"): hover dims everyone outside the bar, a pick sets the bar's filter, and picking it again clears it.
//
// setState flies or eases the camera (MapLibre's own flyTo and easeTo), fades layers in and out by tweening each
// layer's opacity paint property, and switches the discrete settings (filters, the crash card) at once.
(function (root) {
  // Site defaults; a page overrides any of them with the custom property on the map element or an ancestor.
  var COLOURS = {
    "--sm-ink": "#15181c", "--sm-muted": "#59626f", "--sm-severe": "#efb118", "--sm-killed": "#4269d0", "--sm-visible": "#7fbfae", "--sm-pain": "#d8cdf0", "--sm-outline": "#1b1f24",
    "--sm-hin": "#4a4f57", "--sm-hin-2022": "#9c5f3c", "--sm-hin-2017": "#c8a25e", "--sm-highlight": "#2f7d76",
    "--sm-stop": "#1b1f24",
  };
  // Crime groups are unordered, so they take Observable 10's hues (its red left out).
  var CG = ["#a463f2", "#4269d0", "#efb118", "#3ca951", "#9498a0"];
  // Cars an hour, grey under 1.5 a minute then six doubling steps from one sequential ramp (ColorBrewer GnBu).
  var RT = ["#c3c6cb", "#a8ddb5", "#7bccc4", "#4eb3d3", "#2b8cbe", "#0868ac", "#084081"];
  var RT_LAB = ["Under 1.5 a minute, or no figure", "1.5 to 3 a minute", "3 to 6", "6 to 12", "12 to 24", "24 to 48", "48 or more a minute"];
  var RT_SHORT = ["<1.5 or none", "1.5–3", "3–6", "6–12", "12–24", "24–48", "48+"];
  var HEAT = ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(253,231,37,0)", 0.01, "rgba(253,231,37,0.3)", 0.0625, "rgba(94,201,98,0.75)", 0.25, "#21918c", 0.6, "#3b528b", 1, "#440154"];
  var ICONS = ["walk-kid", "walk-adult", "walk-senior", "bike", "moto", "car", "scooter"];
  var PEOPLE_LAYERS = ["heat", "fan", "fan-lab", "hinc", "minor", "minor-fan"];
  // On and off the 2024 High Injury Network (bit 4 of `hy`, the 60 ft rule), Observable 10's two-way split.
  var HINC = [["On the 2024 network", "#4269d0"], ["Off the network", "#efb118"]];
  var ON_HIN = ["!=", ["%", ["floor", ["/", ["get", "hy"], 4]], 2], 0];
  // SFMTA's Bike Comfort Index classes (tools/street-safety/street-safety-map.py BCI_CLASSES): ordered, so one sequential ramp,
  // darkest for the least comfortable (ColorBrewer Blues, reversed, every other step so neighbouring classes differ).
  // Bike comfort diverges at SFMTA's all ages and abilities line (BCI over 80; street-safety-map.py BCI_AAA): the three
  // classes under it in amber deepening to brown as the score drops, the two over it in teal (--seq-3 the deepest), so
  // a block under the line is a different hue, not just a shade (Bryan, 2026-11-19). Lightness
  // still runs in order on each side and the hues cross on the blue-yellow axis every colour-blind type keeps; no red.
  var BCI = ["#7a4a0c", "#c47f12", "#efb118", "#7fbfb5", "#2f7d76"];
  // Through traffic: the share of a block's car trips with neither end within the slider's distance of it (half a mile by default), in ordered classes, so one
  // sequential ramp (ColorBrewer Purples), darkest for mostly through. Labels match map.json through.classes.
  var TT = ["#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"];
  var TT_LAB = ["Under 25%", "25 to 50%", "50 to 75%", "75% or more"];
  function ttColor(get) { return ["match", get, 0, TT[0], 1, TT[1], 2, TT[2], TT[3]]; }
  var DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  // Where traffic comes from: one circle per SF neighborhood and per region outside SF, its area the cars a weekday
  // (Bryan, 2026-11-20: "give one bubble per neighborhood that shows by area the number of cars"). Size carries the
  // amount, so every bubble is the one calm blue; the chosen area's own cars are a ring in the ramp's darkest step.
  var WF_FILL = "#6baed6", WF_LINE = "#2171b5", WF_OWN = "#084594", WF_OWN_BAR = "#c6dbef";
  // The time-of-day chart's two series, cars coming in and cars going out: Observable 10's two-way split.
  var WF_SERIES = ["#4269d0", "#efb118"];
  // The biggest bubble's radius in px, on a laptop and on a phone.
  var WF_R = 30, WF_R_NARROW = 21;
  // Below this zoom the city is too small on screen to hold a bubble per neighborhood: they are drawn as one, at WF_SF.
  var WF_MERGE_Z = 10, WF_SF = [-122.443, 37.758];
  // A bubble's card, how people travel: car, transit, bike, walk. An unordered set, so Observable 10's hues, without
  // its red (red isn't a category on this site). Each segment's share is also printed.
  var WF_MODES = ["#4269d0", "#efb118", "#6cc5b0", "#3ca951"];
  // Fewer person trips a weekday than this between two places and the card doesn't split them by mode: about 30
  // simulated trips at MTC's one-in-two sample.
  var WF_MODE_MIN = 60;
  // Fewer trips by car than this pass an eligibility test and the card says "Fewer than 20", with no share.
  var WF_ELIG_MIN = 20;
  // Each police level its own hue (Bryan, 2026-11-19: "use categorical colors where severly
  // injured and killed really stand out saturation or value wise"): killed in Observable 10's deep blue and severe in its
  // saturated amber, the two lower levels in pale, greyed teal and lavender, lighter for the less severe, so lightness
  // and saturation still run in the order of the levels. Neighbouring levels stay at least 20 apart in CIELAB under
  // protan, deutan and tritan simulation (Machado 2009). The values are the --sm-* properties in COLOURS.
  // Zoomed in, every level is drawn as the road-user icon, all at one size ("Keep icons the same
  // size on the map"). The light extract has the mode but no age, so a person walking is the adult figure, and "Other
  // or not stated" stays a dot.
  var LIGHT_ICON = { "Walking": "walk-adult", "Biking": "bike", "Motorcycle or moped": "moto", "Scooter or board": "scooter", "Car or truck": "car" };
  // The 2024 HIN's 10-mile groups are ordered, worst first, so their colours are sampled from one ramp, darkest for the
  // worst: the site's --seq-1 rust and --seq-2 tan (src/layout.mjs) with a darker and a lighter end.
  var GROUP_STOPS = ["#4a2410", "#9c5f3c", "#c8a25e", "#efe4c6"];
  var WORST_COL = "#2f7d76";
  function hex(c) { return [1, 3, 5].map(function (i) { return parseInt(c.slice(i, i + 2), 16); }); }
  function rampAt(t) {
    var k = Math.min(GROUP_STOPS.length - 2, Math.floor(t * (GROUP_STOPS.length - 1))), u = t * (GROUP_STOPS.length - 1) - k;
    var a = hex(GROUP_STOPS[k]), b = hex(GROUP_STOPS[k + 1]);
    return "#" + a.map(function (v, i) { return ("0" + Math.round(v + (b[i] - v) * u).toString(16)).slice(-2); }).join("");
  }
  function groupColours(n) { var out = []; for (var g = 0; g < n; g++) out.push(rampAt(n > 1 ? g / (n - 1) : 0)); return out; }
  var OPACITY = { line: ["line-opacity"], fill: ["fill-opacity"], circle: ["circle-opacity", "circle-stroke-opacity"], heatmap: ["heatmap-opacity"], symbol: ["icon-opacity", "text-opacity"] };

  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function n0(v) { return Math.round(v).toLocaleString("en-US"); }
  // A model's count to two significant figures (docs/product/tool-ux-guidelines.md, rule 30).
  function n2(v) { v = Math.round(v); if (v < 100) return String(v); var p = Math.pow(10, Math.floor(Math.log10(v)) - 1); return (Math.round(v / p) * p).toLocaleString("en-US"); }

  // An opacity value scaled by f: a number, or a zoom interpolation whose outputs are scaled.
  function scaleOpacity(v, f) {
    if (v === undefined || v === null) v = 1;
    if (typeof v === "number") return v * f;
    if (Array.isArray(v) && v[0] === "interpolate") return v.map(function (x, i) { return i >= 4 && i % 2 === 0 ? scaleOpacity(x, f) : x; });
    if (Array.isArray(v) && v[0] === "step") return v.map(function (x, i) { return i >= 2 && i % 2 === 0 ? scaleOpacity(x, f) : x; });
    return f > 0.5 ? v : 0;
  }

  // People drawn as 24 px figures on a canvas at 2x, a dark outline under the fill colour.
  // A plain dot the size of an icon's body, for a person whose mode has no icon.
  function dotSprite(col, dark) {
    var c = document.createElement("canvas"); c.width = c.height = 48;
    var g = c.getContext("2d"); g.scale(2, 2);
    g.beginPath(); g.arc(12, 12, 5, 0, 2 * Math.PI); g.fillStyle = col; g.fill(); g.lineWidth = 1.2; g.strokeStyle = dark; g.stroke();
    return c;
  }
  function sprite(kind, col, dark) {
    var c = document.createElement("canvas"); c.width = c.height = 48;
    var g = c.getContext("2d"); g.scale(2, 2); g.lineCap = "round"; g.lineJoin = "round";
    function draw(segs, heads, rings, lw, fills) {
      [[dark, lw + 2.2, 1.1], [col, lw, 0]].forEach(function (pass) {
        g.strokeStyle = pass[0]; g.fillStyle = pass[0]; g.lineWidth = pass[1];
        segs.forEach(function (s) { g.beginPath(); g.moveTo(s[0], s[1]); for (var i = 2; i < s.length; i += 2) g.lineTo(s[i], s[i + 1]); g.stroke(); });
        heads.forEach(function (h) { g.beginPath(); g.arc(h[0], h[1], h[2] + pass[2], 0, 7); g.fill(); });
        rings.forEach(function (h) { g.beginPath(); g.arc(h[0], h[1], h[2], 0, 7); g.stroke(); });
        (fills || []).forEach(function (f) { g.beginPath(); g.moveTo(f[0], f[1]); for (var i = 2; i < f.length; i += 2) g.lineTo(f[i], f[i + 1]); g.closePath(); g.fill(); if (pass[2]) g.stroke(); });
      });
    }
    if (kind === "walk-adult") draw([[12, 6.5, 11.6, 13.5], [11.6, 13.5, 8.4, 21], [11.6, 13.5, 14.8, 21], [12, 8.2, 8.6, 11.8], [12, 8.2, 15.4, 11.4]], [[12, 3.6, 2.4]], [], 2.6);
    else if (kind === "walk-kid") draw([[12, 11.3, 11.8, 16], [11.8, 16, 9.8, 21], [11.8, 16, 13.9, 21], [12, 12.5, 9.6, 15], [12, 12.5, 14.4, 14.6]], [[12, 8.4, 2.6]], [], 2.4);
    else if (kind === "walk-senior") draw([[12.8, 7, 11, 13.8], [11, 13.8, 8.6, 21], [11, 13.8, 13.6, 21], [12.6, 8.6, 16.5, 12], [16.5, 12, 17.6, 21]], [[13.4, 4.2, 2.3]], [], 2.4);
    else if (kind === "bike") draw([[5.5, 17, 10.5, 17, 15, 11, 18.5, 17], [10.5, 17, 9.5, 11, 15, 11], [10.5, 17, 12, 19.2], [9.6, 5.8, 9.5, 11], [9.6, 7.2, 14.6, 10.4]], [[9.8, 3.4, 2.1]], [[5.5, 17, 3.9], [18.5, 17, 3.9]], 1.5);
    else if (kind === "moto") draw([[10.5, 6.6, 12.5, 10.5], [11, 7.6, 17, 9.6]], [[10.2, 4.6, 2.7], [5.5, 17.2, 1.2], [18.5, 17.2, 1.2]], [[5.5, 17.2, 3.4], [18.5, 17.2, 3.4]], 2.8,
      [[3.5, 13.5, 8.5, 10.6, 17.5, 10.6, 20.5, 13.5, 16.5, 15.6, 8.5, 15.6], [9.5, 15, 14.5, 15, 14.5, 19, 9.5, 19]]);
    // Car: a convertible with the person sitting up in it (Bryan's pick, option B, 2026-11-19).
    else if (kind === "car") {
      draw([[12, 7.6, 12, 12.2], [12, 9.4, 15.8, 13.2]], [[12, 4.8, 2.5]], [], 2.6);
      draw([], [[6.4, 18.2, 2.2], [17.6, 18.2, 2.2]], [], 1.2, [[2, 17.4, 2, 14, 8, 12.6, 21, 12.8, 22.4, 14.4, 22.4, 17.4]]);
      draw([[15.4, 15.8, 16.6, 13.4]], [], [], 1.6);
    } else draw([[12, 6.4, 12, 14.5], [12, 14.5, 10.5, 19], [12, 14.5, 13.5, 19], [6, 19.8, 18, 19.8], [18, 19.8, 17, 9, 14.5, 9]], [[12, 3.6, 2.3], [7, 21.4, 1.3], [18, 21.4, 1.3]], [], 2.2);
    return c;
  }

  // The heat map's intensity at zoom z: one over the densest kernel sum, so the darkest colour always means the
  // densest place in view at that zoom.
  function weightPeak(coords, w, r, z) {
    var ws = 512 * Math.pow(2, z), P = coords.map(function (c) {
      var s = Math.sin(c[1] * Math.PI / 180);
      return [(c[0] + 180) / 360 * ws, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * ws];
    }), gr = {}, best = 0;
    P.forEach(function (p, i) { var k = Math.floor(p[0] / r) + "," + Math.floor(p[1] / r); (gr[k] = gr[k] || []).push(i); });
    P.forEach(function (p) {
      var cx = Math.floor(p[0] / r), cy = Math.floor(p[1] / r), s = 0;
      for (var dx = -1; dx <= 1; dx++) for (var dy = -1; dy <= 1; dy++) (gr[(cx + dx) + "," + (cy + dy)] || []).forEach(function (j) {
        var ex = (P[j][0] - p[0]) / r, ey = (P[j][1] - p[1]) / r, d2 = ex * ex + ey * ey;
        if (d2 < 1) s += w[j] * Math.exp(-4.5 * d2);
      });
      if (s > best) best = s;
    });
    return best * 0.3989422804014327;
  }
  // The heat map's colour scale follows what it shows (Bryan, 2026-11-19: "should be scaled to
  // what it's showing ... using whatever is best practice"). deck.gl's HeatmapLayer takes its colour domain from the
  // densest point of the data in view, recomputed as the view changes (deck.gl docs, HeatmapLayer colorDomain, "if not
  // specified, ... the maximum value of the current viewport"); MapLibre's heatmap has no domain, but its
  // heatmap-intensity multiplies heatmap-density, and heatmap-color reads density 0 to 1 (MapLibre style spec, heatmap
  // layer), so intensity = 1 / peak puts the peak on the darkest stop. The peak here is the 99th percentile of the
  // nonzero kernel sums rather than the maximum, so one hotspot doesn't flatten the rest to the palest stops. The sums
  // are taken on a grid of cells a third of the radius across, with MapLibre's own Gaussian kernel (the same one the
  // earlier weightPeak used), so a hundred thousand people cost a few thousand cells.
  function densityPeak(coords, w, r, z, pct) {
    var ws = 512 * Math.pow(2, z), cs = r / 3, cells = {}, keys = [];
    coords.forEach(function (c, i) {
      var s = Math.sin(c[1] * Math.PI / 180), x = (c[0] + 180) / 360 * ws, y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * ws;
      var k = Math.floor(x / cs) + "," + Math.floor(y / cs);
      if (!cells[k]) { cells[k] = 0; keys.push(k); }
      cells[k] += w[i];
    });
    var sums = keys.map(function (k) {
      var p = k.split(",").map(Number), s = 0;
      for (var dx = -3; dx <= 3; dx++) for (var dy = -3; dy <= 3; dy++) {
        var v = cells[(p[0] + dx) + "," + (p[1] + dy)];
        if (v) { var d2 = (dx * dx + dy * dy) / 9; if (d2 < 1) s += v * Math.exp(-4.5 * d2); }
      }
      return s;
    }).filter(function (s) { return s > 0; }).sort(function (a, b) { return a - b; });
    if (!sums.length) return 0;
    return sums[Math.min(sums.length - 1, Math.floor(pct * (sums.length - 1)))] * 0.3989422804014327;
  }
  function radiusAt(z) { return z <= 11 ? 12 : z >= 15 ? 34 : 12 + 22 * (z - 11) / 4; }
  function crimeRadius(z) { return z <= 15 ? radiusAt(z) : 34 + 12 * (Math.min(z, 17) - 15); }
  // A Muni stop: a white square with a dark outline, 16 px at 2x.
  function stopSquare(dark) {
    var c = document.createElement("canvas"); c.width = c.height = 32;
    var g = c.getContext("2d"); g.fillStyle = dark; g.fillRect(4, 4, 24, 24); g.fillStyle = "#fff"; g.fillRect(8, 8, 16, 16);
    return c;
  }

  // A ring `feet` around a point, as a closed line.
  function ring(center, feet) {
    var lat = center[1] * Math.PI / 180, dLat = feet / 364000, dLon = feet / (364000 * Math.cos(lat)), out = [];
    for (var i = 0; i <= 64; i++) { var t = 2 * Math.PI * i / 64; out.push([center[0] + dLon * Math.cos(t), center[1] + dLat * Math.sin(t)]); }
    return out;
  }

  function when(d, h) {
    var t = new Date(d + "T12:00:00"), s = t.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return h === null || h === undefined ? s : s + ", " + (h % 12 || 12) + (h < 12 ? " am" : " pm");
  }

  function create(el, opts) {
    var lib = opts.lib, B = opts.basemap, S = opts.state, CC = opts.cards;
    var css = getComputedStyle(el);
    function col(name) { return (css.getPropertyValue(name) || "").trim() || COLOURS[name]; }
    // Each police level's colour by its level number (S.SEVERITIES).
    function sevCols() { return { 0: col("--sm-killed"), 1: col("--sm-severe"), 2: col("--sm-visible"), 3: col("--sm-pain") }; }
    var cur = S.normalize(opts.initial || {});
    if (opts.hash) cur = S.merge(cur, S.fromHash(location.hash));
    var built = false, D = null, map = null, listeners = [], factor = {}, tweens = {}, raf = 0, bySpot = {}, people = [];
    // The zoom where the heat map gives way to the people's icons: 14.1, and 13.3 on a tablet (Bryan, 2026-11-20: "On
    // iPad, I should still see icons a little further out"), which is a map 700 px wide or more on a touch screen, or
    // 700 to 1,100 px wide on any screen. The heat map holds its full strength right up to that zoom and the icons
    // start at it, so there is no stretch of zoom where a fading heat map shows as blurred blobs behind the dots
    // (same message: "i start seeing fuzzy heat map blobs mid-transition").
    function iconZoom() {
      var w = el.getBoundingClientRect().width, coarse = !!(window.matchMedia && matchMedia("(pointer: coarse)").matches);
      return w >= 700 && (coarse || w <= 1100) ? 13.3 : 14.1;
    }
    var ICON_Z = iconZoom();
    function iconSize() { return ["interpolate", ["linear"], ["zoom"], ICON_Z, 0.85, 16, 1]; }
    var mapEl = document.createElement("div");
    mapEl.className = "glmap sm-canvas";
    mapEl.setAttribute("role", "img");
    // The map's name for a screen reader, following the view, the severity and the years the state shows.
    function mapLabel(st) {
      if (st.view !== "injuries") return "Map of San Francisco: " + ({ stress: "traffic on residential blocks", through: "through traffic by block", bike: "bike comfort by block", crime: "crime reports", from: "where traffic comes from" }[st.view] || "streets");
      var y = st.filter.years || [S.YEARS[0], S.NEWEST_YEAR];
      var who = { killed: "killed", severe: "severely injured or killed", visible: "killed or visibly injured", pain: "injured or killed" }[st.filter.severity];
      return "Map of San Francisco: every person " + who + " in traffic, " + (y[0] === y[1] ? y[0] : y[0] + " to " + y[1]) + ", and the streets around them";
    }
    mapEl.setAttribute("aria-label", mapLabel(cur));
    el.appendChild(mapEl);

    var inl = window.__ssInline || {}; // the board copy carries its data inline (index.mjs, inlineData)
    if (!opts.data && inl.data) opts.data = inl.data;
    var dataP = opts.data ? Promise.resolve(opts.data) : fetch(opts.dataUrl).then(function (r) { if (!r.ok) throw new Error(opts.dataUrl + " " + r.status); return r.json(); });
    // Crash cards: one file per year and 0.01 degree cell (tools/street-safety/street-safety-cards.py), named from a person's date
    // and point and fetched on the first tap in it. A failed fetch falls back to the board copy's inline cards.
    var inlineCards = opts.crashes || inl.crashes || {}, cardFiles = {};
    function cardFile(p) { return p.d.slice(0, 4) + "/" + (Math.floor(p.c[0] * 100) + 12260) + "-" + (Math.floor(p.c[1] * 100) - 3770); }
    function loadFile(k) {
      var url = String(opts.crashesUrl || "").replace(/\/?$/, "/") + k + ".json";
      return cardFiles[k] = cardFiles[k] || fetch(url).then(function (r) { if (r.status === 404) return {}; if (!r.ok) throw new Error(url + " " + r.status); return r.json(); })
        .then(function (j) { return j.cards || {}; }, function (e) { delete cardFiles[k]; if (inlineCards[k]) return inlineCards[k]; throw e; });
    }
    function loadCrashes(ps) {   // every card in the files these people fall in, as one { case: card }
      var ks = {};
      ps.forEach(function (p) { ks[cardFile(p)] = 1; });
      return Promise.all(Object.keys(ks).map(loadFile)).then(function (all) {
        var C = {};
        all.forEach(function (f) { for (var c in f) C[c] = f[c]; });
        return C;
      });
    }

    var resolveReady, rejectReady;
    var ctl = { el: el, ready: new Promise(function (a, b) { resolveReady = a; rejectReady = b; }) };
    ctl.getState = function () { return JSON.parse(JSON.stringify(cur)); };
    ctl.iconZoom = function () { return ICON_Z; };   // for street-safety-check
    ctl.on = function (fn) { listeners.push(fn); };
    // The address follows the state as the reader filters (Bryan, 2026-11-19: "The URL should also
    // change dynamically as I filter to include the filters"): replaceState, so the back button isn't filled with every
    // click, 250 ms after the last change, so dragging a slider writes once. The query (the board frame's ?cw-frame=1)
    // is kept as it is; only the fragment changes.
    var hashT = 0;
    function writeHash() {
      hashT = 0;
      var want = location.pathname + location.search + S.toHash(cur);
      if (want === location.pathname + location.search + location.hash) return;
      try { history.replaceState(history.state, "", want); } catch (e) { /* a sandboxed frame may refuse */ }
    }
    ctl.flushHash = function () { if (hashT) { clearTimeout(hashT); writeHash(); } };   // for street-safety-check
    function emit(reason) {
      if (reason !== "camera") mapEl.setAttribute("aria-label", mapLabel(cur));
      if (opts.hash) { clearTimeout(hashT); hashT = setTimeout(writeHash, 250); }
      listeners.concat(opts.onChange ? [opts.onChange] : []).forEach(function (fn) { fn(ctl.getState(), reason); });
      // The listeners redraw the page's cards (the corner chart changes size with its rows), and the where-from
      // view keeps its regions' bubbles clear of them, so they are placed again once the cards have settled.
      if (built && cur.view === "from" && reason !== "camera") { clearTimeout(placeT); placeT = setTimeout(function () { placeFrom(); setTimeout(placeFrom, 500); }, 0); }
    }
    var placeT = 0;

    // ---- Opacity tweens: each layer's factor runs from where it is to 0 or 1 over the duration. ----
    var BASE = {};
    function applyFactor(id) {
      var l = map.getLayer(id); if (!l) return;
      (OPACITY[l.type] || []).forEach(function (prop) { map.setPaintProperty(id, prop, scaleOpacity(BASE[id][prop], factor[id])); });
    }
    function fade(id, to, ms) {
      if (!map.getLayer(id)) return;
      var from = factor[id] === undefined ? (map.getLayoutProperty(id, "visibility") === "none" ? 0 : 1) : factor[id];
      if (to > 0) map.setLayoutProperty(id, "visibility", "visible");
      if (!ms || from === to) { factor[id] = to; applyFactor(id); if (to === 0) map.setLayoutProperty(id, "visibility", "none"); delete tweens[id]; return; }
      tweens[id] = { from: from, to: to, t0: performance.now(), ms: ms };
      if (!raf) raf = requestAnimationFrame(step);
    }
    function step(now) {
      raf = 0;
      Object.keys(tweens).forEach(function (id) {
        var t = tweens[id], u = Math.min(1, (now - t.t0) / t.ms), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
        factor[id] = t.from + (t.to - t.from) * e;
        applyFactor(id);
        if (u >= 1) { delete tweens[id]; if (t.to === 0) map.setLayoutProperty(id, "visibility", "none"); }
      });
      if (Object.keys(tweens).length) raf = requestAnimationFrame(step);
    }

    // ---- Popups and the crash card ----
    var pop = null;
    function narrow() { return el.getBoundingClientRect().width < 700; }
    function show(lngLat, html) {
      if (opts.sheetHost && narrow()) {
        if (pop) pop.remove();
        opts.sheetHost.innerHTML = '<button type="button" class="sm-x" aria-label="Close">×</button>' + html;
        opts.sheetHost.hidden = false;
        opts.sheetHost.querySelector(".sm-x").addEventListener("click", function () { opts.sheetHost.hidden = true; closeFromCard(); });
      } else {
        if (!pop) { pop = new lib.Popup({ closeButton: true, maxWidth: "280px", offset: 14 }); pop.on("close", function () { if (!popBusy) closeFromCard(); }); }
        popBusy = true; pop.setLngLat(lngLat).setHTML(html).addTo(map); popBusy = false;
      }
    }
    var popBusy = false;
    function clearPop() { cardKey = ""; if (pop) { popBusy = true; pop.remove(); popBusy = false; } if (opts.sheetHost) opts.sheetHost.hidden = true; }
    // A popup taller than the room above and below its point is set where it fits inside the map.
    function fitPop(lngLat) {
      if (!pop || !pop.isOpen()) return;
      for (var i = 0; i < 2; i++) {
        var mr = mapEl.getBoundingClientRect(), r = pop.getElement().getBoundingClientRect(), dy = r.top < mr.top + 4 ? mr.top + 4 - r.top : r.bottom > mr.bottom - 4 ? mr.bottom - 4 - r.bottom : 0;
        if (!dy) return;
        var q = map.project(pop.getLngLat());
        popBusy = true; pop.setLngLat(map.unproject([q.x, q.y + dy])); popBusy = false;
      }
    }
    // The where-from view's open card, kept in the state (`card`: a bubble's name, or "own") so a link reopens it.
    var cardKey = "", fromCardHtml = null;   // build() sets fromCardHtml
    function closeFromCard() {
      cardKey = ""; setFromHl("pin", null);
      if (cur.card) { cur = S.merge(cur, { card: null }); emit("card"); }
    }
    function syncFromCard() {
      var want = cur.view === "from" && cur.card ? cur.card : null;
      if (!want) { if (cardKey) { clearPop(); setFromHl("pin", null); } return; }
      if (!fromSummary().ready) return;   // the area's file is on its way; wfGet calls again
      var b = fromList.filter(function (x) { return want === "own" ? x.own : !x.own && x.name === want; })[0];
      if (!b) { clearPop(); closeFromCard(); return; }   // a name this area has no bubble for
      var f = fromFeats.filter(function (x) { return x.properties.g === b.g; })[0], at = f ? f.geometry.coordinates : b.at;
      var html = fromCardHtml ? fromCardHtml({ g: b.g }) : "", key = want + "|" + narrow() + "|" + html;
      if (!html || key === cardKey) return;
      show(at, html); fitPop(at);
      cardKey = key;
      setFromHl("pin", b.own ? null : b.top ? b.g : "rest");
    }
    // A bar and its bubble mark each other: a hovered or tapped bar outlines its bubble, and a hovered bubble or an
    // open card marks its bar. "rest" is the Everywhere else bar: every bubble with no bar of its own.
    var fromHl = { hover: null, pin: null }, fromHlNow = null;
    function setFromHl(slot, key) {
      fromHl[slot] = key;
      var now = fromHl.hover != null ? fromHl.hover : fromHl.pin;
      if (now === fromHlNow) return;
      fromHlNow = now;
      var gs = now == null ? [] : now === "rest" ? fromList.filter(function (b) { return !b.own && !b.top; }).map(function (b) { return b.g; }) : [now];
      if (map && map.getLayer("from-hl")) map.setFilter("from-hl", ["in", ["get", "g"], ["literal", gs]]);
      if (ctl.onFromHl) ctl.onFromHl(now);
    }
    ctl.fromHl = function () { return fromHlNow; };
    ctl.chartTap = function (key) { if (cur.view === "from") setFromHl("pin", fromHl.pin === key ? null : key); };
    function deathCard(p) {
      var h = '<div class="pop"><b>Killed: ' + esc(p.dl) + "</b>" + (p.loc ? "<br>" + esc(p.loc) : (p.st ? "<br>Near " + esc(p.st) : ""));
      if (p.lab) h += "<br>Cause in the police report: <b>" + esc(p.cause) + "</b>";
      h += p.lid ? '<br>Source: <a href="https://data.sfgov.org/d/dau3-4s8f" target="_blank" rel="noopener">Vision Zero fatality log</a>, record ' + esc(p.lid)
        : '<br><span class="g">Not yet in the city\'s fatality log</span>';
      if (p.nu && /^https?:\/\//.test(p.nu)) h += '<br>News: <a href="' + esc(p.nu) + '" target="_blank" rel="noopener">' + esc(p.no) + (p.nt ? ", " + esc(p.nt) : "") + "</a>";
      return h + "</div>";
    }
    var cardFor = null;
    // A person's key in the address: the SFPD case number, else the fatality log's record, else date and place, so a
    // link keeps working when the data is rebuilt.
    function keyOf(p) { return p.cs || (p.lid ? "log" + p.lid : p.c ? "d" + p.d + "@" + p.c.join(",") : ""); }
    function openCard(key) {
      var i = -1;
      for (var j = 0; j < people.length; j++) if (keyOf(people[j]) === key) { i = j; break; }
      if (!CC) return Promise.resolve();
      // A link to a crash before 2021 waits for the older years.
      var y = /^d(\d{4})/.exec(key);
      if (i < 0 && y && D && D.light && D.light.older && +y[1] <= D.light.older.to && older.state !== "loaded") {
        loadOlder(true);
        return (older.p || Promise.resolve()).then(function () { if (older.state === "loaded" && cur.crash === key) return openCard(key); });
      }
      if (i < 0) {   // a stale link: drop the crash rather than hide the figures behind a card that never opens
        cur = S.merge(cur, { crash: null }); emit("card"); return Promise.resolve();
      }
      // A dot (`mi`) has no case number: its card is the one in its file with its date and point. A figure opens its spot.
      var p0 = people[i], idx = p0.mi ? [i] : bySpot[p0.s.join(",")] || [i];
      return loadCrashes(idx.map(function (j) { return people[j]; })).then(function (C) {
        if (cur.crash !== key) return;   // closed or replaced while the cards were loading
        var items = [], at = {}, start = 0;
        if (p0.mi) {
          var x = Math.round(p0.c[0] * 1e5), yy = Math.round(p0.c[1] * 1e5);
          var hits = Object.keys(C).filter(function (c) { return C[c].dt === p0.d && (C[c].at || []).some(function (a) { return a[0] === x && a[1] === yy; }); }).sort();
          if (!hits.length) { minorPop(p0, p0.c); cur = S.merge(cur, { crash: null }); emit("card"); return; }
          hits.forEach(function (c) {
            items.push({ cr: C[c], ps: people.filter(function (p) { return p.sv <= 1 && (p.mi ? keyOf(p) === key : p.cs === c); }) });
          });
        } else {
          idx.forEach(function (j) {
            var p = people[j], k = p.cs || "p" + j;   // grouping only, within this spot
            if (!(k in at)) { at[k] = items.length; items.push({ cr: p.cs ? C[p.cs] || null : null, ps: [] }); }
            items[at[k]].ps.push(p);
            if (j === i) start = at[k];
          });
        }
        clearPop();
        cardFor = key;
        // On a phone the card covers the lower half of the map, so the crash is moved into the upper part.
        if (narrow() && !opts.story) {
          var pt = map.project(people[i].c), want = mapEl.clientHeight * 0.25;
          if (Math.abs(pt.y - want) > 20) map.panBy([pt.x - mapEl.clientWidth / 2, pt.y - want], { duration: 400 });
        }
        CC.open(items, start, mapEl, { deathCard: deathCard, host: opts.cardHost || null, noScroll: !!opts.story,
          onClose: function () { if (cardFor === key && cur.crash === key) { cardFor = null; cur = S.merge(cur, { crash: null }); emit("card"); } } });
      }).catch(function (e) {   // no cards to show: say so in the console and let the figures back
        if (window.console) console.warn("safety map: crash cards unavailable", e && e.message);
        if (cur.crash === key) { cur = S.merge(cur, { crash: null }); emit("card"); }
      });
    }
    function minorPop(p, lngLat) {   // a dot whose crash isn't in DataSF's crash table, so it has no card
      show(lngLat, '<div class="pop"><b>' + esc(S.SEVERITIES.filter(function (x) { return x[2] === p.sv; })[0][1]) + "</b><br>" + esc(p.u) + ", " + esc(p.d) +
        '<br><span class="g">No crash card: the crash isn\'t in DataSF\'s crash table.</span></div>');
    }
    function closeCard() { if (cardFor !== null) { cardFor = null; CC.close(); } }

    // ---- State to map ----
    function area() { return S.areaGeom(cur, D && D.hoods, D && D.districts); }
    // The people the filters keep under a state, without the deaths that have no police report (lg), worked out once
    // per filter and reused by the headline, the key, the chart and the heat scale, which all asked for the same list.
    // A few recent states are kept, so a chart that lifts its own filter doesn't push out the headline's.
    var shownCache = [];
    function shownFor(st, g) {
      var k = JSON.stringify([st.filter, S.groupKey(st), people.length, g ? JSON.stringify(st.filter.area) : null]);
      for (var i = 0; i < shownCache.length; i++) if (shownCache[i].k === k) return shownCache[i].rows;
      var test = S.shownTest(st, g), rows = [];
      for (var j = 0; j < people.length; j++) { var p = people[j]; if (!p.lg && test(p)) rows.push(p); }
      shownCache.unshift({ k: k, rows: rows });
      if (shownCache.length > 6) shownCache.pop();
      return rows;
    }
    // Each person's Supervisor district (DataSF cqbw-m5m3's 2022 lines, opts.districts): the first whose outline holds
    // their point, tested inside each outline's bounding box only; a point in none (a pier, or a sliver the simplified
    // outlines leave along a shared edge) takes the district with the nearest vertex, so every person counts in exactly
    // one district and the eleven add up to the city.
    // The even-odd test is S.inside's, run only over the edges that cross the point's latitude: each district's edges
    // are bucketed into 64 bands of latitude, so a point looks at a handful of edges, not all 1,750 (100,000 people in
    // about a tenth of the time).
    var distIx = null, NB = 64;
    function districtIndex() {
      return (D.districts || []).map(function (d) {
        var E = [], y0 = 90, y1 = -90, x0 = 180, x1 = -180;
        d.geom.coordinates.forEach(function (poly) { poly.forEach(function (ring) { for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          E.push([ring[i][0], ring[i][1], ring[j][0], ring[j][1]]);
          y0 = Math.min(y0, ring[i][1]); y1 = Math.max(y1, ring[i][1]); x0 = Math.min(x0, ring[i][0]); x1 = Math.max(x1, ring[i][0]); } }); });
        var h = (y1 - y0) / NB || 1, bands = []; for (var k = 0; k < NB; k++) bands.push([]);
        E.forEach(function (e) { var a = Math.max(0, Math.floor((Math.min(e[1], e[3]) - y0) / h)), b = Math.min(NB - 1, Math.floor((Math.max(e[1], e[3]) - y0) / h)); for (var k = a; k <= b; k++) bands[k].push(e); });
        return { district: d.district, box: [x0, y0, x1, y1], h: h, bands: bands };
      });
    }
    function inDistrict(c, ix) {
      var x = c[0], y = c[1], b = ix.box;
      if (x < b[0] || x > b[2] || y < b[1] || y > b[3]) return false;
      var es = ix.bands[Math.min(NB - 1, Math.floor((y - b[1]) / ix.h))], hit = false;
      for (var i = 0; i < es.length; i++) { var e = es[i]; if ((e[1] > y) !== (e[3] > y) && x < (e[2] - e[0]) * (y - e[1]) / (e[3] - e[1]) + e[0]) hit = !hit; }
      return hit;
    }
    function districtOf(c) {
      var L = D.districts || [];
      if (!L.length) return 0;
      distIx = distIx || districtIndex();
      for (var i = 0; i < distIx.length; i++) if (inDistrict(c, distIx[i])) return distIx[i].district;
      var best = 0, bd = Infinity;
      L.forEach(function (d) { d.geom.coordinates.forEach(function (poly) { poly[0].forEach(function (q) { var dx = q[0] - c[0], dy = q[1] - c[1], e = dx * dx + dy * dy; if (e < bd) { bd = e; best = d.district; } }); }); });
      return best;
    }
    function applyFilters() {
      var g = area(), f = S.peopleFilter(cur, g), m = members();
      var fig = ["<=", ["get", "sv"], 1];
      var card = ["!=", ["get", "mi"], 1];
      var base = { heat: ["!=", ["get", "lg"], 1], fan: ["all", fig, card], hinc: fig, minor: ["==", ["get", "mi"], 1], "minor-fan": ["==", ["get", "mi"], 1],
        "fan-lab": ["all", ["==", ["get", "si"], ["-", ["get", "n"], 1]], ["!=", ["get", "lab"], ""], fig, card] };
      PEOPLE_LAYERS.forEach(function (l) { if (map.getLayer(l)) map.setFilter(l, base[l] ? ["all", base[l], f] : f); });
      // While a chart bar is hovered the heat map shows only its people (a heat map can't dim part of itself).
      if (hover.expr && map.getLayer("heat")) map.setFilter("heat", ["all", base.heat, f, hover.expr]);
      // The area also scopes the street and crime layers, by the same membership the chart counts (members()).
      var only = function (set) { return set ? [["in", ["get", "i"], ["literal", set]]] : []; };
      [["stress-grey", 3], ["stress-est", 2], ["stress-mod", 1], ["stress-meas", 0]].forEach(function (x) { map.setFilter(x[0], ["all", ["==", ["get", "s"], x[1]]].concat(only(m && m.traffic))); });
      var onlyRow = m ? [["in", ["get", "r"], ["literal", m.traffic]]] : [];
      // The time-of-day filter picks the hour bin's figures: properties c and l for the whole day, c_am, l_am and so on.
      var tc = ["get", "c" + ttSuffix()], tl = ["get", "l" + ttSuffix()];
      map.setFilter("through-grey", ["all", ["<", tc, 0]].concat(onlyRow));
      map.setFilter("through", ["all", [">=", tc, 0], ["==", tl, 0]].concat(onlyRow));
      map.setFilter("through-low", ["all", [">=", tc, 0], ["==", tl, 1]].concat(onlyRow));
      ["through", "through-low"].forEach(function (l) { map.setPaintProperty(l, "line-color", ttColor(tc)); map.setLayoutProperty(l, "line-sort-key", tc); });
      // A picked comfort class (the key or the chart) leaves only its own layer drawn.
      var bp = cur.filter.bci;
      for (var k = 0; k < 5; k++) map.setFilter("bci" + k, bp.length && bp.indexOf(k) < 0 ? ["==", ["get", "i"], -1] : m ? only(m.bci[k])[0] : null);
      // The day and time choice weighs each place by its reports in that day and time (properties s and sw, set
      // in crimeData); a hovered day or time bar narrows it further.
      crimeData();
      ["crime-heat", "crime-dots"].forEach(function (l) { map.setFilter(l, ["all"].concat(m ? only(m.crime) : [], [[">", ["get", "s"], 0]])); });
      map.setPaintProperty("crime-heat", "heatmap-weight", ["get", "sw"]);
      var mask = [], edge = [];
      if (g) {
        // The world with the area cut out, so everything outside it dims.
        var holes = (g.type === "MultiPolygon" ? g.coordinates : [g.coordinates]).map(function (poly) { return poly[0]; });
        mask.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[-123, 37.5], [-121.9, 37.5], [-121.9, 38.1], [-123, 38.1], [-123, 37.5]]].concat(holes) } });
        edge.push({ type: "Feature", properties: {}, geometry: g });
      }
      map.getSource("area-mask").setData(B.collection(mask));
      map.getSource("area-edge").setData(B.collection(edge));
      applyFrom();
    }
    function applyHighlight() {
      var h = cur.highlight, area = [], blocks = [], rg = [];
      if (h && h.area) D.hoods.forEach(function (a) { if (a.name === h.area) area.push({ type: "Feature", properties: {}, geometry: a.geom }); });
      if (h && h.blocks) {
        var want = {}; h.blocks.forEach(function (c) { want[c] = 1; });
        trRuns.forEach(function (r, i) { if (want[D.traffic.cnn[i]]) blocks.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r } }); });
      }
      if (h && h.circle) rg.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: ring(h.circle.center, h.circle.feet) } });
      map.getSource("hl-area").setData(B.collection(area));
      map.getSource("hl-blocks").setData(B.collection(blocks));
      map.getSource("hl-ring").setData(B.collection(rg));
    }
    function moveCamera(ms) {
      var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduce) ms = 0;
      var c = cur.camera;
      // No camera: the chosen neighborhood, else the whole city (Bryan, 2026-11-19: "If I change area, please zoom to
      // that area").
      // The where-from view opens on the Bay Area, whatever the area.
      // On a phone the city goes in the part of the map the title, the layer card and the key leave open, so the
      // regions' bubbles, drawn at that part's edge, ring the city and don't sit on it.
      if (!c && cur.view === "from") {
        // A laptop draws a region off its frame at the frame's edge, so the city fills the frame. A smaller screen
        // draws every bubble at its own place, so once an area is picked the frame is all of them, inside the part
        // of the map the cards leave open.
        // A story frames the city on every screen: on a phone the whole Bay Area left San Francisco too small to read.
        var all = !opts.story && !edgeRegions() && cur.filter.area && WFD.units, pad = (opts.fitPadding && opts.fitPadding(all ? "all" : "")) || 16;
        if (all) {
          if (typeof pad === "number") pad = { top: pad, bottom: pad, left: pad, right: pad };
          var P = WFD.units.points, bb = P.reduce(function (a, p) { return [Math.min(a[0], p[0]), Math.min(a[1], p[1]), Math.max(a[2], p[0]), Math.max(a[3], p[1])]; }, [180, 90, -180, -90]), rm = narrow() ? 30 : WF_R_NARROW + 26;
          var box = [[bb[0], bb[1]], [bb[2], bb[3]]], pd = { top: pad.top + rm, bottom: pad.bottom + rm + (narrow() ? 52 : 0), left: pad.left + 50, right: pad.right + 50 };
          // Cards that leave no room (a layout not yet settled) fall back to a plain margin, so the frame is still every bubble.
          if (!map.cameraForBounds(box, { padding: pd })) pd = 30;
          map.fitBounds(box, { padding: pd, duration: ms, bearing: 0 });
          return;
        }
        map.fitBounds(fromBox(), { padding: (narrow() && pad) || 4, duration: ms, bearing: 0 }); return;
      }
      if (!c) { if (cur.filter.area && !cur.filter.area.polygon && area()) fitArea(ms); else map.fitBounds(D.bounds, { padding: 4, duration: ms, bearing: 0 }); return; }
      var target = { center: c.center, zoom: c.zoom, bearing: c.bearing || 0, essential: false };
      if (!ms) map.jumpTo(target);
      else if (Math.abs(map.getZoom() - c.zoom) > 1.5 || map.project(c.center).x < 0 || map.project(c.center).x > mapEl.clientWidth) map.flyTo(Object.assign(target, { duration: ms, curve: 1.3 }));
      else map.easeTo(Object.assign(target, { duration: ms }));
    }
    // The where-from view's frame: the city, where the neighborhoods' bubbles are, and on a laptop the near shore of
    // the East Bay and the top of the Peninsula too. A region whose bubble is off the frame is drawn at its edge.
    function fromBox() {
      var b = D.bounds, w = b[0][0], s0 = b[0][1], e = b[1][0], n = b[1][1];
      return narrow() ? [[w, s0], [e, n]] : [[w - 0.02, s0 - 0.07], [e + 0.13, n + 0.04]];
    }
    // Fly to a newly chosen neighborhood, unless the state names its own camera. A drawn area keeps the view it was
    // drawn in. `opts.fitPadding()` names the edges the page's own panels cover, so the area lands in the open map.
    function fitArea(ms) {
      var g = area(); if (!g || cur.camera || cur.filter.area.polygon || cur.view === "from") return;
      var b0 = [180, 90, -180, -90];
      (g.type === "MultiPolygon" ? g.coordinates : [g.coordinates]).forEach(function (poly) { poly[0].forEach(function (c) { b0 = [Math.min(b0[0], c[0]), Math.min(b0[1], c[1]), Math.max(b0[2], c[0]), Math.max(b0[3], c[1])]; }); });
      var pad = (opts.fitPadding && opts.fitPadding()) || Math.min(60, mapEl.clientWidth / 8);
      map.fitBounds([[b0[0], b0[1]], [b0[2], b0[3]]], { padding: pad, duration: ms || 0, bearing: 0 });
    }
    // The cause filter checked against the data's tree: a subcause the data no longer holds (a code that fell under 3
    // people and joined "Other") falls back to its cause, an unknown cause is dropped, and every cause chosen whole is
    // no filter at all, so the deaths with no police report, which carry no cause, aren't hidden by it.
    function fitCause(s) {
      if (!D || !D.causes || !s.filter.cause.length) return s;
      var tree = {}; D.causes.forEach(function (c) { tree[c.key] = c.subs.map(function (x) { return x.key; }); });
      var out = [];
      s.filter.cause.forEach(function (e) {
        var k = e.split("/"), c = k[0], sub = k.slice(1).join("/");
        if (!tree[c]) return;
        out.push(!sub || tree[c].indexOf(sub) >= 0 ? e : c);
      });
      if (D.causes.every(function (c) { return out.indexOf(c.key) >= 0; })) out = [];
      return S.normalize(Object.assign({}, s, { filter: Object.assign({}, s.filter, { cause: out }) }));
    }
    ctl.setState = function (partial, o) {
      o = o || {};
      var ms = o.duration || 0, next = fitCause(o.replace ? S.merge(S.DEFAULTS, partial) : S.merge(cur, partial)), prevArea = cur.filter.area;
      // Into or out of the where-from view the camera goes back to that view's own frame (the Bay Area, or the city)
      // unless the move names a camera.
      var reframe = next.view !== cur.view && (next.view === "from" || cur.view === "from") && !(partial && partial.camera);
      if (reframe) next = S.merge(next, { camera: null });
      if (!built) { cur = next; emit("set"); return ctl.ready; }   // build() draws whatever cur is by then
      var p = S.plan(cur, next);
      cur = next;
      loadCrime();
      if (cur.view === "crime") crimeData();
      if (p.params && !p.filter) applyFilters();
      var areaMoved = JSON.stringify(cur.filter.area) !== JSON.stringify(prevArea);
      if (p.filter) { loadOlder(); applyFilters(); if (areaMoved && cur.filter.area && o.fit !== false) fitArea(ms); }
      // Back to all of San Francisco, the map zooms out to the city (Bryan, 2026-11-19: "If I go
      // back to All of san francisco on area, zoom out"), unless the state names its own camera.
      if (areaMoved && prevArea && !cur.filter.area && !cur.camera && !p.camera && o.fit !== false) moveCamera(ms);
      if (p.highlight) applyHighlight();
      applyExtras();
      p.fadeOut.forEach(function (l) { fade(l, 0, ms); });
      p.fadeIn.forEach(function (l) { fade(l, 1, ms); });
      if (p.camera || reframe) moveCamera(ms);   // a camera already null doesn't change, but the frame does
      if (p.crash) { if (cur.crash) openCard(cur.crash); else closeCard(); }
      if (p.fadeOut.length || p.fadeIn.length) clearPop();
      applyFrom(); syncFromCard();
      emit("set");
      return Promise.resolve();
    };

    // ---- Key and figures ----
    var SPR = {}, SPRURL = {};
    // The key's Severity rows (sprite suffix and label by level) and Travel mode rows ([road user, icon, label]).
    var SEV_SPR = { 0: "k", 1: "s", 2: "v", 3: "p" }, SEV_KEY = { 0: "Killed", 1: "Severe injury", 2: "Other visible injury", 3: "Complaint of pain" };
    var MODE_KEY = [["Walking", "walk-adult", "Walking"], ["Biking", "bike", "Bike"], ["Motorcycle or moped", "moto", "Motorcycle"], ["Scooter or board", "scooter", "Scooter"], ["Car or truck", "car", "Car"]];
    ctl.keyHTML = function () {
      var s = cur, img = function (k) { SPRURL[k] = SPRURL[k] || SPR[k].toDataURL(); return '<img alt="" src="' + SPRURL[k] + '">'; };
      if (!built) return "";
      var g = area();
      if (s.view === "injuries" && s.color === "hin") {
        var on = 0, off = 0; shownFor(s, g).forEach(function (p) { if (p.hy & 4) on++; else off++; });
        return HINC.map(function (x, i) { return '<span><i class="dot" style="background:' + x[1] + '"></i>' + x[0] + ' <span class="n">' + n0(i ? off : on) + "</span></span>"; }).join("");
      }
      if (s.view === "injuries") {
        var lv = S.sevLevel(s.filter.severity), zoomedIn = map.getZoom() >= ICON_Z;
        var hins = [["2024", col("--sm-hin")], ["2022", col("--sm-hin-2022")], ["2017", col("--sm-hin-2017")]].filter(function (h) { return s.hin.indexOf(h[0]) >= 0; });
        // Only what is on the map now (Bryan, 2026-11-19: "Only show the legend that applies to
        // what's visible"): zoomed out, the heat map's ramp; zoomed in, the people, under a Severity header (each level
        // shown, in its colour) and a Travel mode header (each mode the filter keeps, as its icon in white), as the map
        // draws them ("show headers for each section").
        var sev = S.SEVERITIES.filter(function (x) { return x[2] <= lv; }).map(function (x) { return "<span>" + img("walk-adult-" + SEV_SPR[x[2]]) + esc(SEV_KEY[x[2]]) + "</span>"; }).join("");
        var modes = MODE_KEY.filter(function (m) { return !s.filter.user.length || s.filter.user.indexOf(m[0]) >= 0; })
          .map(function (m) { return "<span>" + img(m[1] + "-n") + esc(m[2]) + "</span>"; }).join("");
        return (zoomedIn ? '<span class="sm-key-h">Severity</span>' + sev + (modes ? '<span class="sm-key-h">Travel mode</span>' + modes : "")
          : '<span><i class="ramp"></i>Fewer to more people hurt, in this view</span>') +
          hins.map(function (h) { return '<span><i class="ln" style="' + (h[0] === "2017" ? "height:0;border-top:3px dashed " + h[1] : "background:" + h[1]) + '"></i>' + h[0] + " High Injury Network</span>"; }).join("") +
          // The groups: one ramp step per 10 miles, worst first; the corner chart names each group's miles.
          ((s.hin.indexOf("groups") >= 0 || s.hin.indexOf("groups22") >= 0) && D.hinGroups ? '<span><i class="steps">' + groupColours((s.hin.indexOf("groups22") >= 0 && D.hinGroups22 ? D.hinGroups22 : D.hinGroups).groups[s.rank].length).map(function (c) { return '<b style="background:' + c + '"></b>'; }).join("") +
            "</i>" + (s.hin.indexOf("groups22") >= 0 ? "2022" : "2024") + " High Injury Network, worst to best, 10 miles a step</span>" : "") +
          (s.worst ? '<span><i class="ln" style="background:' + WORST_COL + ';height:5px"></i>Worst 10 miles of ' + s.worst + "</span>" : "");
      }
      // Traffic stress: one row of blocks, each class its own block with its own label (Bryan, 2026-11-19, thread
      // h0p9mkzup4ww: "a heat-map like single row of blocks that shows each item separately"), then how each block's
      // figure was found under its own header ("Data Source").
      if (s.view === "stress") return '<span class="sm-key-h">Cars a minute, busiest hour</span><span class="sm-blocks">' +
        RT.map(function (c, i) { return '<span title="' + esc(RT_LAB[i]) + '"><b style="background:' + c + '"></b>' + esc(RT_SHORT[i]) + "</span>"; }).join("") + "</span>" +
        '<span class="sm-key-h">Data source</span>' +
        '<span><i class="ln" style="background:' + RT[4] + ';height:5px"></i>Measured</span><span><i class="ln" style="background:' + RT[4] + ';opacity:.75"></i>Modelled</span>' +
        '<span><i class="ln dash"></i>Estimated</span>';
      if (s.view === "through") return '<span class="sm-key-h">Car trips with neither end within ' + nearPhrase() + "</span>" +
        TT.map(function (c, i) { return '<span><i class="ln" style="background:' + c + '"></i>' + TT_LAB[i] + "</span>"; }).join("") +
        '<span><i class="ln dash" style="background:repeating-linear-gradient(90deg,' + TT[2] + ' 0 7px,transparent 7px 10px)"></i>Rough figure</span>' +
        '<span><i class="ln" style="background:' + TT[3] + ';height:5px"></i>Main street</span><span><i class="ln" style="background:' + TT[3] + ';height:2px"></i>Residential</span>';
      if (s.view === "from") return cur.filter.area ? fromKey_() : "";
      if (s.view === "bike") {
        // Most comfortable first, with the all-ages line drawn between the two sides and named.
        // Each class is a button: a click shows only that class, a second click clears it, as a chart bar does (Bryan,
        // 2026-11-19: "Make this filterable on BCI index"). SafetyOverlay wires the clicks.
        var A = D.bci.aaa, pk = s.filter.bci || [], sw = function (i) { var on = pk.indexOf(i) >= 0;
          return '<button type="button" class="sm-kbtn' + (pk.length && !on ? " off" : "") + '" data-bci="' + i + '" aria-pressed="' + on + '" title="' + (on ? "Show every class" : "Show only this class") + '"><i class="ln" style="background:' + BCI[i] + '"></i>' + esc(D.bci.labels[i]) + "</button>"; };
        var side = function (from, to) { var h = ""; for (var i = from; i >= to; i--) h += sw(i); return h; };
        // The headline already names the index, so the key starts at its two sides.
        return '<span class="sm-key-h" style="font-weight:600">Over ' + A.score + ': comfortable for most riders</span>' + side(D.bci.labels.length - 1, A.below) +
          '<span class="sm-key-h" style="font-weight:600;border-top:1px solid ' + col("--sm-muted") + ';padding-top:3px">' + A.score + ' or under: below the all ages line</span>' + side(A.below - 1, 0);
      }
      if (s.view === "crime") return '<span><i class="ramp"></i>Fewer to more SFPD reports, in this view</span>' +
        '<span><img alt="" style="width:12px;height:12px" src="' + (SPRURL["stop-square"] = SPRURL["stop-square"] || SPR["stop-square"].toDataURL()) + '">Muni stop</span>' +
        muniKey();
      return "";
    };

    // The Muni lines' key: each Metro line as its letter on SFMTA's colour, then each bus colour named by the lines it
    // carries (Rapid where every one is an R line), so the key names the line and colour is never the only cue.
    function muniKey() {
      if (!D.muni) return "";
      var badge = function (r, L) { return '<b style="display:inline-block;min-width:13px;height:13px;line-height:13px;margin-right:2px;border-radius:7px;font-size:9px;text-align:center;background:' +
        L.c + ";color:" + L.t + '">' + esc(r) + "</b>"; };
      var metro = Object.keys(D.muni).filter(function (r) { return D.muni[r].y === 0; }).sort(), bus = {};
      Object.keys(D.muni).forEach(function (r) { var L = D.muni[r]; if (L.y !== 0) (bus[L.c] = bus[L.c] || []).push(r); });
      return (metro.length ? "<span>" + metro.map(function (r) { return badge(r, D.muni[r]); }).join("") + "Muni Metro</span>" : "") +
        Object.keys(bus).sort().map(function (c) { var rapid = bus[c].every(function (r) { return /R$/.test(r); });
          return '<span><i class="ln" style="background:' + c + '"></i>' + (rapid ? "Rapid bus" : "Frequent bus") + "</span>"; }).join("");
    }

    // ---- What the area, time and day filters leave, for the headline and the chart ----
    // The midpoint of each traffic block, for the area test (a block counts when its midpoint is inside).
    // The point halfway along a run by length: tools/street-safety/street-safety-map.py midpoint(), the same rule, so a drawn area
    // counts the blocks a neighborhood would.
    function mid(run) {
      var k = Math.cos(37.76 * Math.PI / 180), seg = [], tot = 0, i;
      for (i = 0; i + 1 < run.length; i++) { seg.push(Math.hypot((run[i + 1][0] - run[i][0]) * k, run[i + 1][1] - run[i][1])); tot += seg[i]; }
      var half = tot / 2, t0 = 0;
      for (i = 0; i < seg.length; i++) {
        if (seg[i] && t0 + seg[i] >= half) { var t = (half - t0) / seg[i]; return [run[i][0] + (run[i + 1][0] - run[i][0]) * t, run[i][1] + (run[i + 1][1] - run[i][1]) * t]; }
        t0 += seg[i];
      }
      return run[0];
    }
    var trMid = null, bciMid = null, memo = { key: null, val: null };
    // Which traffic blocks, BCI runs and crime places the area holds, as index lists, or null with no area. A
    // neighborhood uses the build's index (the unthinned outlines); a drawn shape tests each block's midpoint and each
    // place's point.
    function members() {
      var a = cur.filter.area, key = JSON.stringify(a) + (CR ? "|crime" : "");
      if (memo.key === key) return memo.val;
      var val = null;
      if (a) {
        var pick;
        if (a.hood) { var hi = -1; D.hoods.forEach(function (h, i) { if (h.name === a.hood) hi = i; }); pick = function (h) { return h === hi; }; }
        var g = area(), test = function (pt, h) { return pick ? pick(h) : S.inside(pt, g); };
        trMid = trMid || trRuns.map(mid);
        bciMid = bciMid || D.bci.runs.map(function (enc) { return B.decode(enc).map(mid); });
        var keep = function (pts, hoods) { var out = []; for (var i = 0; i < hoods.length; i++) if (test(pts[i], hoods[i])) out.push(i); return out; };
        val = { traffic: keep(trMid, D.traffic.hood), bci: bciMid.map(function (ms, k) { return keep(ms, D.bci.hood[k]); }),
          crime: CR ? keep(CR.pts, CR.hood) : [] };
      }
      memo = { key: key, val: val };
      return val;
    }
    // Counts for the current filter, over the police reports (the deaths with no police report are not in them).
    // `unplaced` and `unplacedKilled` are the people counted whom the map can't draw (`np`: no place in the record).
    ctl.figures = function () {
      if (!D) return null;
      var g = area(), shown = shownFor(cur, g), np = shown.filter(function (p) { return p.np; });
      return { people: shown.length, killed: shown.filter(function (p) { return p.k; }).length,
        unplaced: np.length, unplacedKilled: np.filter(function (p) { return p.k; }).length,
        onHin: shown.filter(function (p) { return p.hy & 4; }).length, atCorner: shown.filter(function (p) { return p.at === 1; }).length,
        walking: shown.filter(function (p) { return p.u === "Walking"; }).length, total: D.meta.figures.people, later: D.meta.figures.deaths_outside_police_reports,
        rows: shown };
    };
    // The residential blocks in the area by class of cars an hour (index 0: under 1.5 a minute; -1: no figure).
    function stressMix() {
      var m = members(), inA = m ? {} : null, T = D.traffic, out = { measured: 0, n: 0, cls: [0, 0, 0, 0, 0, 0, 0] };
      if (m) m.traffic.forEach(function (i) { inA[i] = 1; });
      T.p.forEach(function (p, i) {
        if (p[10] !== 0 || p[0] < 0 || (inA && !inA[i])) return;
        out.n++; out.cls[p[0]]++;
        if (p[7] === 0 || p[7] === 1 || p[7] === 5 || p[7] === 6) out.measured++;
      });
      return out;
    }
    // Blocks with a through figure in the area, by road (0 residential, 1 main) and class, plus their street miles.
    // The class tools/street-safety/through-traffic.py set on the unrounded share (-1: too few cars to colour).
    // The model's figures are one time of day at a time, so the view takes the time filter only when it names one.
    function ttBin() { var t = cur.filter.time; return t.length === 1 && (D.through.bins || {})[t[0]] ? t[0] : null; }
    // The distance slider's choice, when the data holds it (map.json from before the slider has one distance only).
    function ttNear() { var X = D.through; return X.near && X.near[cur.near] && cur.near !== X.defaultNear ? cur.near : null; }
    function ttSuffix() { return (ttNear() ? "_n" + ttNear() : "") + (ttBin() ? "_" + ttBin() : ""); }
    // The figures for the distance and the time-of-day filter's hour bin, or the whole day's.
    function throughX() {
      var X = D.through, n = ttNear(), N = n ? X.near[n] : null, bn = ttBin(), b = bn && X.bins[bn];   // map.json from before the hour bins has none
      var src = N ? (bn ? N.bins[bn] : N) : (b || X);
      return { i: X.i, s: src.s, v: b ? b.v : X.v, l: src.l, c: src.c, minCars: b ? X.minBin : X.minCars, bin: bn, near: cur.near };
    }
    function nearPhrase() { var n = S.NEARS.filter(function (x) { return x[0] === cur.near; })[0]; return n ? n[2] : "half a mile"; }
    ctl.nearPhrase = nearPhrase;
    function throughClass(j) { return throughX().c[j]; }
    function throughMix() {
      var m = members(), inA = m ? {} : null, X = throughX(), out = { res: [0, 0, 0, 0], main: [0, 0, 0, 0], n: 0, most: 0, mostRes: 0, mostMain: 0 };
      if (m) m.traffic.forEach(function (i) { inA[i] = 1; });
      X.i.forEach(function (r, j) {
        if (inA && !inA[r]) return;
        var k = X.c[j]; if (k < 0) return;
        var main = D.traffic.p[r][10] !== 0;
        (main ? out.main : out.res)[k]++; out.n++;
        if (k >= 2) { out.most++; if (main) out.mostMain++; else out.mostRes++; }
      });
      return out;
    }
    function bciMix() {
      var m = members();
      return m ? m.bci.map(function (l) { return l.length; }) : D.bci.hood.map(function (l) { return l.length; });
    }
    // ---- Crime: every SFPD report since 2018 (crime.json), loaded the first time the crime view opens ----
    // A cell is ((year index * G + group) * 7 + weekday) * NP + period: the year index counts from S.CRIME_YEARS[0],
    // the group is an index of S.CRIME_KINDS, the weekday has Sunday 0 and the period is an index of S.TIMES, NP - 1
    // for no time (tools/street-safety/sfpd-person-crimes.py all-years.json). CR.cells[i] holds place i's as [cell, reports, ...].
    var NP = S.TIMES.length + 1, TIME_IDS = S.TIMES.map(function (x) { return x[0]; }), KIND_IDS = S.CRIME_KINDS.map(function (k) { return k[0]; });
    var CR = null, crimeLoad = { state: "none", p: null };
    ctl.crimeLoading = function () { return crimeLoad.state === "loading"; };
    ctl.crime = function () { return CR; };   // for street-safety-check
    ctl.crimeWeight = function () { return crimeSW.reduce(function (t, v) { return t + v; }, 0); };   // the heat map's total weight, for street-safety-check
    function unpackCrime(C) {
      var out = { groups: C.groups, years: C.years, from: C.from, to: C.to, G: C.groups.length, pts: [], hood: C.hood, cells: [] };
      for (var i = 0; i < C.x.length; i++) {
        out.pts.push([C.x[i] / 1e5, C.y[i] / 1e5]);
        // Each cell is stored as its gap from the place's previous cell (street-safety-map.py crime_layer).
        var g = C.cells[i], a = new Int32Array(g.length), prev = -1;
        for (var k = 0; k < g.length; k += 2) { prev += g[k]; a[k] = prev; a[k + 1] = g[k + 1]; }
        out.cells.push(a);
      }
      return out;
    }
    function loadCrime() {
      if (crimeLoad.state !== "none" || cur.view !== "crime") return;
      crimeLoad.state = "loading";
      var url = opts.crimeUrl || String(opts.dataUrl).replace(/[^/]*$/, "crime.json");
      var el = document.getElementById("ss-crime");   // the board copy carries the file inline (index.mjs, inlineData)
      crimeLoad.p = (el ? Promise.resolve().then(function () { return JSON.parse(el.textContent); })
        : fetch(url).then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); })).then(function (C) {
        CR = unpackCrime(C);
        crimeLoad.state = "loaded";
        if (built) { crimeKey = ""; heatKey = ""; setCrimeIntensity(); applyFilters(); rescaleHeat(); }
        emit("set");
      }, function (e) { crimeLoad.state = "none"; crimeLoad.p = null; console.error("crime reports:", e); emit("set"); });
      emit("set");
    }
    // The crime filters as a selection: { ys: first and last year index or null, wd: weekdays or null, per: periods or
    // null, gs: group indices or null }. `skip` lifts some of them (years, days, time, kinds), for a chart that counts
    // with its own dimension lifted or for the per-place groups.
    function crimeSel(skip) {
      skip = skip || {};
      var f = cur.filter, Y0 = S.CRIME_YEARS[0];
      var t = f.time.map(function (id) { return TIME_IDS.indexOf(id); }).filter(function (q) { return q >= 0; });
      var gs = f.crimeKinds.map(function (k) { return KIND_IDS.indexOf(k); }).filter(function (g) { return g >= 0; });
      return { ys: skip.years || !f.crimeYears ? null : [f.crimeYears[0] - Y0, f.crimeYears[1] - Y0], wd: skip.days ? null : S.weekdays(f.days),
        per: skip.time || !t.length ? null : t, gs: skip.kinds || !gs.length ? null : gs };
    }
    // Which cells a selection keeps: 1 or 0 for every cell.
    function crimeMask(sel) {
      var G = CR.G, Y = CR.years.length, m = new Uint8Array(Y * G * 7 * NP);
      for (var y = 0; y < Y; y++) {
        if (sel.ys && (y < sel.ys[0] || y > sel.ys[1])) continue;
        for (var g = 0; g < G; g++) {
          if (sel.gs && sel.gs.indexOf(g) < 0) continue;
          for (var d = 0; d < 7; d++) {
            if (sel.wd && sel.wd.indexOf(d) < 0) continue;
            for (var q = 0; q < NP; q++) if (!sel.per || sel.per.indexOf(q) >= 0) m[((y * G + g) * 7 + d) * NP + q] = 1;
          }
        }
      }
      return m;
    }
    // A crime place's reports by group in the cells `m` keeps (by default the filters but the kind).
    function placeGroups(i, m) {
      var G = CR.G, out = [], a = CR.cells[i];
      for (var j = 0; j < G; j++) out.push(0);
      m = m || crimeMask(crimeSel({ kinds: true }));
      for (var k = 0; k < a.length; k += 2) if (m[a[k]]) out[((a[k] / (7 * NP)) | 0) % G] += a[k + 1];
      return out;
    }
    // The crime source's s (reports in the choice, narrowed by a hovered bar) and sw (the heat map's weight: the same
    // less Other, unless kinds are picked, when it is the picked kinds), rewritten only when the choice or the hover moves.
    var crimeKey = "", crimeSW = [];
    function crimeData() {
      if (!CR || !map.getSource("crime")) return;
      // Off the crime view the source waits: setState fills it when the view opens.
      if (cur.view !== "crime") { crimeKey = ""; return; }
      var sel = crimeSel({ kinds: true }), gs = crimeSel().gs;
      if (hover.days) sel.wd = (sel.wd || [0, 1, 2, 3, 4, 5, 6]).filter(function (d) { return hover.days.indexOf(d) >= 0; });
      if (hover.per != null) sel.per = !sel.per || sel.per.indexOf(hover.per) >= 0 ? [hover.per] : [];
      if (hover.year != null) sel.ys = !sel.ys || (hover.year >= sel.ys[0] && hover.year <= sel.ys[1]) ? [hover.year, hover.year] : [1, 0];
      if (hover.kind != null) gs = !gs || gs.indexOf(hover.kind) >= 0 ? [hover.kind] : [];
      var key = JSON.stringify([sel, gs]);
      if (key === crimeKey) return;
      crimeKey = key;
      var G = CR.G, m = crimeMask(sel);
      map.getSource("crime").setData(B.collection(CR.pts.map(function (pt, i) {
        var g = placeGroups(i, m), n = 0, w = 0;
        for (var j = 0; j < G; j++) if (!gs || gs.indexOf(j) >= 0) { n += g[j]; if (gs || j < G - 1) w += g[j]; }
        crimeSW[i] = w;
        return { type: "Feature", properties: { i: i, s: n, sw: w }, geometry: { type: "Point", coordinates: pt } }; })));
    }
    function crimePlaces() { if (!CR) return []; var m = members(); return m ? m.crime : CR.pts.map(function (c, i) { return i; }); }
    // Reports the selection keeps in the area, summed by one dimension: "g" kind, "y" year, "d" weekday (Sunday 0) or
    // "q" period of S.TIMES and then no time.
    function crimeBy(sel, dim) {
      var G = CR.G, m = crimeMask(sel), out = [], size = { g: G, y: CR.years.length, d: 7, q: NP }[dim];
      for (var j = 0; j < size; j++) out.push(0);
      crimePlaces().forEach(function (i) {
        var a = CR.cells[i];
        for (var k = 0; k < a.length; k += 2) {
          var c = a[k]; if (!m[c]) continue;
          out[dim === "q" ? c % NP : dim === "d" ? ((c / NP) | 0) % 7 : dim === "g" ? ((c / (7 * NP)) | 0) % G : (c / (G * 7 * NP)) | 0] += a[k + 1];
        }
      });
      return out;
    }
    // The headline's count, and every kind's under the other filters (the kinds chart lifts its own filter).
    function crimeMix() {
      if (!CR) return { n: 0, groups: S.CRIME_KINDS.map(function () { return 0; }), loading: true };
      var all = crimeBy(crimeSel({ kinds: true }), "g"), gs = crimeSel().gs, n = 0;
      all.forEach(function (v, j) { if (!gs || gs.indexOf(j) >= 0) n += v; });
      return { n: n, groups: all };
    }
    function crimeByWeekday(everyDay) { return crimeBy(crimeSel({ days: everyDay }), "d"); }
    function crimeByPeriod(everyTime) { return crimeBy(crimeSel({ time: everyTime }), "q"); }
    // The crime years the filter keeps, for the headline and a place's card: "2018 to 2026 (through Nov 16)", "2024".
    ctl.crimeSpan = crimeSpan;
    function crimeSpan() {
      var y = cur.filter.crimeYears, Y = S.CRIME_YEARS, a = y ? y[0] : Y[0], b = y ? y[1] : Y[Y.length - 1];
      var out = a === b ? String(a) : a + " to " + b;
      if (CR && b === Y[Y.length - 1]) out += " (through " + new Date(CR.to + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) + ")";
      return out;
    }
    // The crime heat map's first scale, from every report but Other's at each place.
    function setCrimeIntensity() {
      if (!CR || !map || !map.getLayer("crime-heat")) return;
      var G = CR.G, w = CR.cells.map(function (a) { var v = 0; for (var k = 0; k < a.length; k += 2) if (((a[k] / (7 * NP)) | 0) % G !== G - 1) v += a[k + 1]; return v; });
      var ci = ["interpolate", ["linear"], ["zoom"]];
      for (var cz = 10; cz <= 17; cz++) ci.push(cz, 1 / weightPeak(CR.pts, w, crimeRadius(cz), cz));
      map.setPaintProperty("crime-heat", "heatmap-intensity", ci);
    }

    // ---- Where traffic comes from (tools/street-safety/where-traffic-comes-from.py) ----
    // Files beside map.json, fetched the first time the view needs them and never inlined: the units (the groups, where
    // each bubble sits, the regions), one file per neighborhood and per Supervisor district, and the street links a
    // drawn area's cordon count sums.
    var WFD = { units: null, areas: {}, modes: {}, links: null, pending: {}, failed: {} }, fromMinZoom = null, baseMinZoom = null;
    function wfUrl(f) { return (opts.whereUrl || String(opts.dataUrl).replace(/[^/]*$/, "where-from/")) + f; }
    ctl.whereUrl = wfUrl;
    function wfSlug(t) { return t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
    // A failed file stays failed for the page's life, so the re-render it triggers doesn't fetch it again.
    function wfGet(key, file, set) {
      if (WFD.pending[key] || WFD.failed[key]) return;
      WFD.pending[key] = fetch(wfUrl(file)).then(function (r) { if (!r.ok) throw new Error(file + " " + r.status); return r.json(); })
        .then(function (j) { set(j); if (built) { applyFrom(); syncFromCard(); emit("set");
          // The chart card arrives with the area's file and takes its share of the map: frame the bubbles again.
          setTimeout(function () { if (!cur.camera && cur.view === "from" && !edgeRegions()) moveCamera(0); }, 0); } }, function (e) { WFD.failed[key] = e.message; if (window.console) console.warn("where from:", e.message); emit("set"); });
    }
    // What the view needs for the state, loaded or on its way: null while it loads.
    function wfData() {
      var a = cur.filter.area;
      if (cur.view !== "from" || !a) return null;
      if (!WFD.units) wfGet("units", "units.json", function (j) {
        WFD.units = j;
        // The map zooms out as far as the nine counties and no further: past that there is nothing of the view to see.
        var nb = j.bounds, cam = map.cameraForBounds([[nb[0], nb[1]], [nb[2], nb[3]]], { padding: 0 });
        if (cam && cur.view === "from") { fromMinZoom = cam.zoom - 0.5; map.setMinZoom(fromMinZoom); }
        if (built && !cur.camera && cur.view === "from") moveCamera(0);
      });
      // A neighborhood or a Supervisor district has its own select-link file.
      if (a.hood || a.district) { var k = a.hood ? wfSlug(a.hood) : "district-" + a.district; if (!WFD.areas[k]) wfGet("a:" + k, "area-" + k + ".json", function (j) { WFD.areas[k] = j; });
        // How people travel between the area and each unit, for a bubble's card: loaded beside, never waited on.
        if (!WFD.modes[k]) wfGet("m:" + k, "modes-" + k + ".json", function (j) { WFD.modes[k] = j; });
        return WFD.units && WFD.areas[k] ? { sel: WFD.areas[k] } : null; }
      if (!WFD.links) wfGet("links", "links.json", function (j) { WFD.links = j; });
      // A drawn area: no precomputed select-link file, so a cordon count over its outline.
      return WFD.units && WFD.links && area() ? { drawn: cordon(area()) } : null;
    }
    ctl.fromLoading = function () { return cur.view === "from" && !!cur.filter.area && !wfData(); };
    ctl.fromFailed = function () { return cur.view === "from" && !!cur.filter.area && !wfData() && Object.keys(WFD.failed).length > 0; };
    // A drawn area's cordon count: the cars on every street link onto its street nodes from outside them, by where they
    // start, and off them, by where they end. At a street node of its touching a freeway or ramp, the cars its street
    // links carry away beyond those they bring in came off the ramp, so they count too; a car staying on the freeway
    // doesn't. A car counts each time it crosses, and the edge can't tell a car passing through from one arriving.
    // where-traffic-comes-from.py's cordon() is the same rule, and checks it against the select-link counts.
    var cordonMemo = { key: "", val: null };
    function cordon(g) {
      var key = JSON.stringify(g);
      if (cordonMemo.key === key) return cordonMemo.val;
      var L = WFD.links, G = WFD.units.groups.length;
      if (!L.street) {
        L.street = new Array(L.nodes.length).fill(false); L.fw = new Array(L.nodes.length).fill(false);
        L.links.forEach(function (l) { var t = l[4] ? L.fw : L.street; t[l[0]] = true; t[l[1]] = true; });
      }
      var inside = L.nodes.map(function (p, i) { return L.street[i] && S.inside(p, g); }), inG = new Array(G).fill(0), outG = new Array(G).fill(0), nIn = 0, nOut = 0;
      var net = {};   // node -> [cars out minus in by origin group, cars in minus out by destination group]
      function add(t, v, sgn) { for (var k = 0; k < v.length; k += 2) t[v[k]] += sgn * v[k + 1]; }
      L.links.forEach(function (l) {
        if (l[4]) return;
        var a = inside[l[0]], b = inside[l[1]];
        if (!a && b) { add(inG, l[2], 1); nIn++; }
        else if (a && !b) { add(outG, l[3], 1); nOut++; }
        [[l[0], 1], [l[1], -1]].forEach(function (e) {
          var n = e[0];
          if (!inside[n] || !L.fw[n]) return;
          var t = net[n] || (net[n] = [new Array(G).fill(0), new Array(G).fill(0)]);
          add(t[0], l[2], e[1]); add(t[1], l[3], -e[1]);
        });
      });
      Object.keys(net).forEach(function (n) { for (var k = 0; k < G; k++) { inG[k] += Math.max(0, net[n][0][k]); outG[k] += Math.max(0, net[n][1][k]); } nIn++; });
      cordonMemo = { key: key, val: { inG: inG, outG: outG, links: nIn + nOut } };
      return cordonMemo.val;
    }
    // The figures for the state. Every car on the area's streets is placed where it starts (Coming from), where it ends
    // (Going to) or at both ends (Both): `rows` are the neighborhoods and regions outside the area, `own` the cars
    // whose end is in the area itself, and `denom` what a share is of (every car, or every trip end under Both), so the
    // rows and `own` add to 100%. `total` is the rows' cars (the cars from or to outside the area), `lead` the
    // headline's share. A drawn area's cordon count has no `own`: it sees only the cars crossing its edge.
    function fromSummary() {
      var d = wfData(), e = cur.ends;
      if (!d) return { ready: false, area: !!cur.filter.area };
      var names = WFD.units.groups, rows = [];
      if (d.sel) {
        var A = d.sel, g = A.g, t = A.tot, users = t.arr + t.dep + t.thr + t.inside;
        // Passing through (cur.thru): only the cars with neither trip end in the area, at the group they start in,
        // end in, or both. A share is of the through cars (of their trip ends under Both), so the rows add to 100%,
        // and the headline's share is the through cars out of every car on the area's streets. No ring: none of
        // them starts or ends here.
        if (cur.thru) {
          names.forEach(function (n, i) { var v = e === "from" ? g.ft[i] : e === "to" ? g.tt[i] : g.ft[i] + g.tt[i]; if (v > 0) rows.push({ g: i, name: n, near: 0, thr: v, value: v }); });
          var tb = WFD.units.bins.map(function (x, k) { return { id: x[0], hours: x[1].length, thr: A.bins.thr[k] }; });
          return { ready: true, hood: true, thru: true, rows: rows, total: t.thr, thr: t.thr, inside: t.inside, users: users, own: 0, denom: e === "both" ? 2 * t.thr : t.thr,
            lead: users ? t.thr / users : 0, bins: tb, ends: e };
        }
        names.forEach(function (n, i) {
          var near = e === "from" ? g.fa[i] : e === "to" ? g.td[i] : g.fa[i] + g.td[i], thr = e === "from" ? g.ft[i] : e === "to" ? g.tt[i] : g.ft[i] + g.tt[i];
          if (near + thr > 0) rows.push({ g: i, name: n, near: near, thr: thr, value: near + thr });
        });
        var total = e === "from" ? t.arr + t.thr : e === "to" ? t.dep + t.thr : t.arr + t.dep + t.thr;
        var own = e === "from" ? t.dep + t.inside : e === "to" ? t.arr + t.inside : t.arr + t.dep + 2 * t.inside;
        var b = A.bins, bins = WFD.units.bins.map(function (x, k) { return { id: x[0], hours: x[1].length, from: b.arr[k] + b.thr[k], to: b.dep[k] + b.thr[k] }; });
        return { ready: true, hood: true, rows: rows, total: total, thr: t.thr, inside: t.inside, users: users, own: own, denom: e === "both" ? 2 * users : users,
          lead: users ? (e === "both" ? (t.arr + t.dep + 2 * t.thr) / (2 * users) : total / users) : 0, bins: bins, ends: e };
      }
      var c = d.drawn;
      names.forEach(function (n, i) { var v = e === "from" ? c.inG[i] : e === "to" ? c.outG[i] : c.inG[i] + c.outG[i]; if (v > 0) rows.push({ g: i, name: n, near: v, thr: 0, value: v }); });
      var sum = rows.reduce(function (a, r) { return a + r.value; }, 0);
      return { ready: true, hood: false, rows: rows, total: sum, denom: sum, own: 0, links: c.links, ends: e };
    }
    ctl.fromSummary = fromSummary;
    // Whether the view is counting through cars only: the state asks for it and the area has a through count (a
    // neighborhood or a district; a drawn area's cordon count can't tell a car passing through from one arriving).
    function fromThru() { var a = cur.filter.area; return cur.view === "from" && !!cur.thru && !!a && !!(a.hood || a.district); }
    ctl.fromThru = fromThru;
    // How people travel between the chosen area and a unit (g, or -1 for trips within the area), for the toggle's
    // direction: person trips by mode and the typical morning trip by each, from tools/street-safety/where-traffic-modes.py.
    // Null for a drawn area, while the file loads, and for a pair with no trips. `few` when the model has too few
    // trips to split: under WF_MODE_MIN a weekday, about 30 simulated trips at the model's one-in-two sample.
    function fromModes(g) {
      var a = cur.filter.area;
      if (cur.view !== "from" || !a || !(a.hood || a.district)) return null;
      var M = WFD.modes[a.hood ? wfSlug(a.hood) : "district-" + a.district];
      if (!M) return null;
      var r = g < 0 ? M.own : (M[cur.ends] || []).filter(function (x) { return x[0] === g; })[0];
      if (!r) return null;
      var car = r[1], transit = r[2] + r[3], bike = r[4], walk = r[5], n = car + transit + bike + walk;
      if (!n) return null;
      return { n: n, few: n < WF_MODE_MIN, share: [["Car", car], ["Transit", transit], ["Bike", bike], ["Walk", walk]],
        car: { min: r[6], mi: r[7] }, transit: { min: r[8], none: r[9], drive: r[10] }, bike: { min: r[11], mi: r[12], none: r[13] },
        // Bryan's eligibility line (2026-11-20): [car, transit, bike, walk] trips on the pairs passing each test, and the
        // car trips the tests are over.
        elig: r.length > 16 ? { transit: r[14], bike: r[15], of: r[16] } : null };
    }
    ctl.fromModes = fromModes;
    // A share as the map and the chart print it: whole percents, one decimal under 10%, "<0.1%" for a sliver.
    function pct(v, of) {
      if (!of) return "";
      var p = 100 * v / of;
      return p >= 9.95 ? Math.round(p) + "%" : p >= 0.05 ? p.toFixed(1) + "%" : "<0.1%";
    }
    ctl.fromPct = pct;
    // The bubbles for the state, before they are placed: one per row and one for the area's own cars. Every bubble's
    // area is its cars on one scale per chosen area, set by the biggest neighborhood or region in either direction, so
    // the toggle changes a bubble's size only as its cars change (and Both, the two directions together, is bigger).
    function fromBubbles() {
      var sm = fromSummary(), d = wfData();
      if (!sm.ready) return [];
      var U = WFD.units, top = 0, a = cur.filter.area;
      if (d.sel) U.groups.forEach(function (n, i) { top = Math.max(top, d.sel.g.fa[i] + d.sel.g.ft[i], d.sel.g.td[i] + d.sel.g.tt[i]); });
      else U.groups.forEach(function (n, i) { top = Math.max(top, d.drawn.inG[i], d.drawn.outG[i]); });
      var R = narrow() ? WF_R_NARROW : WF_R, rad = function (v) { return top ? Math.max(2, R * Math.sqrt(v / top)) : 0; };
      var verb = sm.ends === "from" ? "start" : sm.ends === "to" ? "end" : "start or end";
      var out = sm.rows.map(function (r) {
        return { g: r.g, at: U.points[r.g], region: r.g >= U.groups.length - U.regions.length, own: 0, v: r.value, near: r.near, thr: r.thr, r: rad(r.value), name: r.name,
          t1: pct(r.value, sm.denom), n: n2(r.value) };
      });
      // The names the chart's rows carry go on the map too: the ten biggest bubbles.
      out.slice().sort(function (x, y) { return y.v - x.v || x.g - y.g; }).slice(0, 10).forEach(function (b) { b.top = 1; });
      if (sm.own > 0) {
        var at = a.hood ? U.points[U.groups.indexOf(a.hood)] : a.district ? U.district_points[a.district - 1] : null;
        if (at) out.push({ g: -1, at: at, region: false, own: 1, v: sm.own, near: sm.own, thr: 0, r: rad(sm.own), name: a.hood || "District " + a.district, t1: pct(sm.own, sm.denom), n: n2(sm.own), verb: verb });
      }
      return out;
    }
    ctl.fromBubbles = fromBubbles;
    // Where each bubble is drawn. A neighborhood's sits inside it. A region's sits at the middle of its people, or, on
    // a laptop, when that is off the map as framed, on the edge of the open map toward it, so every region is on
    // screen at any zoom. A phone's cards leave too little open map for that (the edge would fall inside the city), so
    // there a region's bubble stays at its own place and the reader zooms out to it.
    var fromKey = "", fromList = [], fromFeats = [];
    // A region's bubble moves to the map's edge only where the open map is wide enough to hold the edge clear of
    // the city: a laptop. On a tablet in portrait or a phone it stays at its own place.
    function edgeRegions() { return mapEl.clientWidth >= 1000; }
    ctl.narrow = narrow;
    ctl.fromEdgeRegions = edgeRegions;
    function placeFrom() {
      if (!map.getSource("from-bubbles")) return;
      var w = mapEl.clientWidth, h = mapEl.clientHeight, pad = (opts.fitPadding && opts.fitPadding()) || 16;
      if (typeof pad === "number") pad = { top: pad, bottom: pad, left: pad, right: pad };
      var mr = mapEl.getBoundingClientRect(), kb = opts.keyBox && opts.keyBox(), key = kb ? { left: kb.left - mr.left, right: kb.right - mr.left, top: kb.top - mr.top } : null;
      // Zoomed out past the city (below WF_MERGE_Z) the neighborhoods' bubbles pile on each other, so they are drawn
      // as one, "Rest of San Francisco", and the area's own ring, which would cover the whole city, isn't drawn.
      var far = map.getZoom() < WF_MERGE_Z, list = fromList, smN = fromSummary(), denomNow = smN.ready ? smN.denom : 0;
      if (far) {
        var hoods = fromList.filter(function (b) { return !b.region && !b.own; }), sum = hoods.reduce(function (a, b) { return a + b.v; }, 0), sm0 = fromSummary();
        var big0 = fromList.reduce(function (a, b) { return !b.own && b.v > a.v ? b : a; }, { v: 0, r: 0 });
        list = fromList.filter(function (b) { return b.region; });
        if (sum > 0 && sm0.ready && big0.v) list.push({ g: -3, at: WF_SF, region: false, own: 0, merged: 1, v: sum, r: big0.r * Math.sqrt(sum / big0.v), name: "Rest of San Francisco", t1: pct(sum, sm0.denom), n: n2(sum), top: 1 });
      }
      var feats = list.map(function (b) {
        var at = b.at;
        if (b.region && edgeRegions()) {
          var m = b.r + 26, x0 = pad.left + m, x1 = w - pad.right - m, y0 = pad.top + m, y1 = h - pad.bottom - m, q = map.project(at), px = q.x, py = q.y;
          if (x1 > x0 && y1 > y0 && (q.x < x0 || q.x > x1 || q.y < y0 || q.y > y1)) {
            var cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, dx = q.x - cx, dy = q.y - cy;
            var k = Math.min(dx ? (dx > 0 ? x1 - cx : x0 - cx) / dx : Infinity, dy ? (dy > 0 ? y1 - cy : y0 - cy) / dy : Infinity);
            px = cx + dx * k; py = cy + dy * k;
          }
          // The key sits over the map's bottom left: a region's bubble that would land under it is drawn just above it.
          if (key && px - b.r < key.right + 8 && py + b.r + 22 > key.top - 8 && px + b.r > key.left - 8) py = Math.max(y0, key.top - 8 - b.r - 22);
          if (px !== q.x || py !== q.y) { var ll = map.unproject([px, py]); at = [ll.lng, ll.lat]; }
        }
        // A region's label and the area's own win any collision with a neighborhood's.
        return { type: "Feature", properties: { g: b.g, v: b.v, k: b.own ? -1e12 : -b.v, r: b.r, own: b.own, t1: b.t1, t2: b.own ? b.verb + " here" : b.name, t3: b.own ? b.verb + " here" : b.name, lab: b.own || b.top || (b.region && b.v >= 0.01 * denomNow) ? 1 : 0 },
          geometry: { type: "Point", coordinates: at } };
      });
      fromFeats = feats;
      map.getSource("from-bubbles").setData(B.collection(feats));
    }
    ctl.fromPlaced = function () { return fromFeats; };   // for scripts/street-safety-check.mjs
    function applyFrom() {
      if (!map.getSource("from-bubbles")) return;
      var d = wfData(), key = cur.view + "|" + cur.ends + "|" + !!cur.thru + "|" + JSON.stringify(cur.filter.area) + "|" + !!d + "|" + narrow();
      if (key === fromKey) return;
      fromKey = key;
      fromList = cur.view === "from" ? fromBubbles() : [];
      // The nine-county floor on zooming out holds only in this view.
      if (baseMinZoom === null) baseMinZoom = map.getMinZoom();
      var wantMin = cur.view === "from" && fromMinZoom !== null ? fromMinZoom : baseMinZoom;
      if (Math.abs(map.getMinZoom() - wantMin) > 1e-9) map.setMinZoom(wantMin);
      if (WFD.units && !map.getSource("from-regions")._set) { map.getSource("from-regions").setData(WFD.units.outlines); map.getSource("from-regions")._set = true; }
      placeFrom();
    }
    // The key: what a bubble's size means, with one bubble at a round share for scale.
    function fromKey_() {
      var sm = fromSummary(), drawn = cur.filter.area && cur.filter.area.polygon;
      var verb = cur.ends === "from" ? "start" : cur.ends === "to" ? "end" : "start or end";
      var h = '<span class="sm-key-h">A circle\'s area is its ' + (sm.thru ? "through cars" : "cars") + "</span>";
      if (!sm.ready || !fromList.length) return h;
      var big = fromList.reduce(function (a, b) { return !b.own && b.v > a.v ? b : a; }, { v: 0, r: 0 });
      var steps = [50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1], top = 100 * big.v / sm.denom, ref = steps.filter(function (x) { return x <= top; })[0];
      if (!ref) return h;
      var r = big.r * Math.sqrt(ref / top), box = Math.ceil(2 * r + 2);
      return h + '<span><svg width="' + box + '" height="' + box + '" viewBox="0 0 ' + box + " " + box + '" style="vertical-align:middle;margin-right:5px" aria-hidden="true"><circle cx="' + box / 2 + '" cy="' + box / 2 + '" r="' + r.toFixed(1) +
        '" fill="' + WF_FILL + '" fill-opacity="0.6" stroke="' + WF_LINE + '"/></svg>' + '<span style="white-space:nowrap">' + n2(sm.denom * ref / 100) + (cur.ends === "both" && !drawn ? " trip ends" : " cars") + " a weekday</span></span>";
    }
    // The corner chart: the area's own cars and the ten biggest neighborhoods and regions, then everywhere else, each
    // bar printing its share with the count after it (Bryan, 2026-11-20: "I want us to think
    // about fractions").
    function fromChart(id, title) {
      var sm = fromSummary();
      if (!sm.ready) return null;   // the headline asks for an area or says it's loading; an empty chart says nothing more
      var rows = sm.rows.slice().sort(function (a, b) { return b.value - a.value || a.g - b.g; }), top = rows.slice(0, 10), rest = rows.slice(10);
      if (rest.length) top.push({ g: "rest", name: "Everywhere else", value: rest.reduce(function (a, r) { return a + r.value; }, 0) });
      var a = cur.filter.area, inside = "Inside the area", out = "Outside it";
      // The area's own cars are the ring on the map and the other side of the headline's share, so they get no bar.
      var data = top.map(function (r) { return { y: r.name, label: r.name, key: r.g, value: r.value, kind: r.own ? inside : out, text: pct(r.value, sm.denom) + " (" + n2(r.value) + ")" }; });
      var note = !sm.hood ? "A cordon count: cars crossing the drawn edge, each time they cross." : "";
      // A phone has no key over its map: the chart says what a circle is.
      if (narrow()) note = "On the map, a circle's area is its " + (sm.ends === "both" && sm.hood ? "trip ends" : "cars") + "." + (note ? " " + note : "");
      return { id: id, title: title, note: note, data: { rows: data }, marks: [
        { mark: "barX", data: "rows", options: { y: "y", x: "value", fill: "kind", insetTop: 14, insetBottom: 1 } },
        { mark: "text", data: "rows", options: { y: "y", text: "y", frameAnchor: "left", textAnchor: "start", dy: -6 } },
        { mark: "text", data: "rows", options: { y: "y", x: "value", text: "text", textAnchor: "start", dx: 4, dy: 7, fill: "var(--sm-muted, #59626f)" } }],
        options: { height: top.length * 30 + 4, marginTop: 2, marginBottom: 2, marginLeft: 1, marginRight: 92, y: { domain: data.map(function (r) { return r.y; }), axis: null, padding: 0.08 },
          x: { axis: null, domain: [0, data.reduce(function (m, r) { return Math.max(m, r.value); }, 0) || 1] }, color: { domain: [out, inside], range: [WF_FILL, WF_OWN_BAR], legend: false } } };
    }
    // The time-of-day chart: cars an hour coming in from outside the area and going out of it, in the map's five times
    // of day (Bryan, 2026-11-20: "I want to see time of day breakdown for from / to so there's a
    // sense of morning vs evening"). The times differ in length, so the bars are cars an hour. A drawn area's cordon
    // count has no times of day.
    var WF_TIMES = { am: "6–9\nam", midday: "9 am–\n3 pm", pm: "3–7\npm", evening: "7–10\npm", night: "Night" };
    function fromTimeChart(id, title) {
      var sm = fromSummary();
      if (!sm.ready) return null;
      if (!sm.bins) return fromChart(id, title);
      // Passing through is one series: a through car comes in and goes out in the same trip.
      var S2 = sm.thru ? ["Passing through"] : ["Coming from", "Going to"], rows = [];
      sm.bins.forEach(function (b) {
        if (sm.thru) { rows.push({ t: WF_TIMES[b.id], s: S2[0], v: Math.round(b.thr / b.hours) }); return; }
        rows.push({ t: WF_TIMES[b.id], s: S2[0], v: Math.round(b.from / b.hours) });
        rows.push({ t: WF_TIMES[b.id], s: S2[1], v: Math.round(b.to / b.hours) });
      });
      rows.forEach(function (r) { r.label = r.v >= 1000 ? (r.v / 1000).toFixed(1) + "k" : String(r.v); });
      // As tall as the other chart, less the colour key's line, so the card's top edge stays put when the chart changes.
      var nrows = Math.min(10, sm.rows.length) + (sm.rows.length > 10 ? 1 : 0);
      return { id: id, title: title, note: "Night here is 10 pm to midnight and 5 to 6 am, the night hours the model has.", data: { rows: rows }, marks: [
        { mark: "barY", data: "rows", options: { fx: "t", x: "s", y: "v", fill: "s" } },
        { mark: "text", data: "rows", options: { fx: "t", x: "s", y: "v", text: "label", dy: -6, fontSize: 11 } },
        { mark: "ruleY", data: [0], options: {} }],
        options: { height: Math.max(200, nrows * 30 + 4 - 44), marginTop: 18, marginBottom: 46, marginLeft: 46, marginRight: 2, fx: { domain: sm.bins.map(function (b) { return WF_TIMES[b.id]; }), label: null, padding: 0.12 },
          x: { axis: null, domain: S2 }, y: { label: null, grid: true, ticks: 4 }, color: { domain: S2, range: WF_SERIES.slice(0, S2.length), legend: true } } };
    }
    ctl.mixes = function () { return D ? { stress: stressMix(), through: throughMix(), bci: bciMix(), crime: crimeMix(), from: cur.view === "from" ? fromSummary() : null } : null; };

    // The corner chart for the current state, as PlotChart props (src/plot-chart/plot-chart.ts): a title and a
    // barsH preset over rows of { label, value }, every figure from the map's own data under the current filters, so
    // the bars always add up to the headline. A distribution chart's rows also carry the `key` a hover or a pick acts
    // on, and `link` says which filter its bars set.
    var CHART_TITLES = { "by-year": "People hurt by year", "by-cause": "People hurt by cause", "by-user": "People hurt by how they travelled", "by-other": "People hurt by other party involved",
      "by-day": "People hurt by day of week", "by-time": "People hurt by time of day",
      "by-hin": "People hurt by High Injury Network", "by-severity": "People hurt by severity", "by-hood": "People hurt by neighborhood",
      "by-district": "People hurt by Supervisor district",
      "by-hin-group": "People hurt by 10 miles of the HIN, worst first", "worst-overlap": "Each year's worst 10 miles",
      "stress-mix": "Residential blocks by cars a minute", "through-mix": "Main streets and residential blocks", "bci-mix": "Blocks by Bike Comfort Index",
      "crime-groups": "SFPD reports by kind", "crime-by-year": "SFPD reports by year", "crime-by-day": "SFPD reports by day of week", "crime-by-time": "SFPD reports by time of day",
      "from-groups": "Share of cars by where they start", "from-time": "Cars an hour by time of day" };
    ctl.chartTitles = CHART_TITLES;
    function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
    // The cause a cause filter is all inside, or null: the chart then drills into that cause's subcauses.
    function drillCause() {
      var c = cur.filter.cause; if (!c.length || (cur.chart && cur.chart.top)) return null;
      var k = c[0].split("/")[0];
      return c.every(function (e) { return e.split("/")[0] === k; }) ? k : null;
    }
    function causeNode(k) { for (var i = 0; i < (D.causes || []).length; i++) if (D.causes[i].key === k) return D.causes[i]; return null; }
    // The place charts' leftover bar: the people with no place in the police record (`np`), who are in no district and
    // neither on the network nor off it. Not a pick, and shown only where someone is in it, so the bars still add up
    // to the headline. No feature carries `np`, so hovering it shows nobody on the map.
    var NO_PLACE = ["", "No location", function (p) { return !!p.np; }, ["==", ["get", "np"], 1], null];
    // The bars of a distribution chart: [key, label, test(person), MapLibre expression, filter it sets when picked].
    function bars(id) {
      var f = cur.filter;
      // One bar a year held: 2021 on, and 2005 to 2020 once they've loaded. Picking the chosen year again goes back to the default span.
      if (id === "by-year") return S.YEARS.filter(function (y) { return y >= S.INLINE_FROM || older.state === "loaded"; }).map(function (y) { y = String(y);
        return [y, y + (+y === S.NEWEST_YEAR ? " (partial)" : ""), function (p) { return p.d.slice(0, 4) === y; }, ["==", ["slice", ["get", "d"], 0, 4], y],
        { years: f.years && f.years[0] === +y && f.years[1] === +y ? S.DEFAULTS.filter.years : [+y, +y] }]; });
      if (id === "by-user") return S.USERS.map(function (u) { return [u, u, function (p) { return p.u === u; }, ["==", ["get", "u"], u], { user: same(f.user, [u]) ? [] : [u] }]; });
      if (id === "by-other") return S.OTHERS.map(function (o) { return [o[0], o[1], function (p) { return p.op === o[0]; }, ["==", ["get", "op"], o[0]], { other: same(f.other, [o[0]]) ? [] : [o[0]] }]; });
      if (id === "by-day") return S.DAYS.map(function (d) { return [d[0], d[1], function (p) { return d[2].indexOf(p.wd) >= 0; }, ["in", ["get", "wd"], ["literal", d[2]]], { days: same(f.days, [d[0]]) ? [] : [d[0]] }]; });
      if (id === "by-time") return S.TIMES.map(function (t) { return [t[0], t[1].split(",")[0], function (p) { return p.h != null && p.h >= 0 && S.hourIn(t, p.h); }, S.timeExpr(t), { time: same(f.time, [t[0]]) ? [] : [t[0]] }]; })
        .concat([["", "Time not stated", function (p) { return p.h == null || p.h < 0; }, ["<", ["get", "h"], 0], null]]);
      // Every filter has its chart (Bryan, 2026-11-19: "Each thing you can filter by should also
      // be in the dropdown"). Severity: a pick shows that level and every one more severe, as the slider does, and
      // picking the chosen level again goes back to the default, severe and killed.
      if (id === "by-severity") return S.SEVERITIES.map(function (x) { return [x[0], x[1], function (p) { return p.sv === x[2]; }, ["==", ["get", "sv"], x[2]],
        { severity: f.severity === x[0] ? S.DEFAULTS.filter.severity : x[0] }]; });
      // Area: one bar per neighborhood or district, a pick filters to it (and zooms there), a second clears it. Anyone
      // in none gets a bar that isn't a pick, so the bars add up to the headline.
      if (id === "by-hood") return D.hoods.map(function (h) { return [h.name, h.name, function (p) { return p.hood === h.name; }, ["==", ["get", "hood"], h.name],
        { area: f.area && f.area.hood === h.name ? null : { hood: h.name } }]; }).concat([["", "No neighborhood", function (p) { return !p.hood; }, ["==", ["get", "hood"], ""], null]]);
      if (id === "by-district") return (D.districts || []).map(function (d) { var n = d.district; return [String(n), "District " + n, function (p) { return p.dist === n; }, ["==", ["get", "dist"], n],
        { area: f.area && f.area.district === n ? null : { district: n } }]; }).concat([NO_PLACE]);
      if (id === "by-hin") {
        var onX = ON_HIN;
        // A person with no place (np) is neither on the network nor off it.
        return [["on", "On the network", function (p) { return !!(p.hy & 4); }, onX, { hin: f.hin === "on" ? "all" : "on" }],
          ["off", "Off the network", function (p) { return !p.np && !(p.hy & 4); }, ["!", onX], { hin: f.hin === "off" ? "all" : "off" }], NO_PLACE];
      }
      if (id === "by-cause") {
        var dk = drillCause(), node = dk && causeNode(dk);
        if (node) return node.subs.map(function (sb) { var key = dk + "/" + sb.key;
          return [key, sb.short || sb.label, function (p) { return S.causeIn(key, p); }, S.causeExpr(key), { cause: same(f.cause, [key]) ? [dk] : [key] }]; });
        return (D.causes || []).map(function (c) { return [c.key, c.label, function (p) { return p.ck === c.key; }, S.causeExpr(c.key), { cause: same(f.cause, [c.key]) ? [] : [c.key] }]; });
      }
      // The chosen HIN edition's 10-mile groups under the state's ranking window; a pick shows one group. The 2017
      // network has none.
      if (id === "by-hin-group") { var GD = groupData(); if (!GD) return []; var hk = S.groupKey(cur);
        return GD.groups[cur.rank].map(function (gr) { var g = gr.g;
          return [String(g), "Miles " + Math.round(gr.from) + " to " + Math.round(gr.to), function (p) { return p[hk] === g; }, ["==", ["get", hk], g], { hinGroup: same(f.hinGroup, [g]) ? [] : [g] }]; })
          // Everyone more than 60 ft from the network, so the bars add up to the headline; not a pick.
          .concat([["off", "Off the network", function (p) { return !p.np && !p[hk]; }, ["==", ["get", hk], 0], null], NO_PLACE]); }
      // Each year's worst 10 miles; a pick draws that year's.
      if (id === "worst-overlap") return D.worst ? D.worst.summary.map(function (r) { return [String(r.year), String(r.year), null, null, { state: { worst: cur.worst === r.year ? null : r.year } }]; }) : null;
      // Bike comfort: a pick shows only that class, as a click on its key entry does.
      if (id === "bci-mix") return D.bci.labels.map(function (l, i) { return [String(i), l, null, null, { bci: same(f.bci, [i]) ? [] : [i] }]; });
      if (id === "crime-groups") return S.CRIME_KINDS.map(function (k) { return [k[0], k[1].replace("Theft, burglary and fraud", "Theft, burglary, fraud").replace("Violence and weapons", "Violence, weapons"), null, null, { crimeKinds: same(f.crimeKinds, [k[0]]) ? [] : [k[0]] }]; });
      // Picking the chosen year again goes back to every year.
      if (id === "crime-by-year") return S.CRIME_YEARS.map(function (y) { return [String(y), y + (y === S.NEWEST_YEAR ? " (so far)" : ""), null, null,
        { crimeYears: f.crimeYears && f.crimeYears[0] === y && f.crimeYears[1] === y ? null : [y, y] }]; });
      if (id === "crime-by-day") return S.DAYS.map(function (d) { return [d[0], d[1], null, null, { days: same(f.days, [d[0]]) ? [] : [d[0]] }]; });
      if (id === "crime-by-time") return S.TIMES.map(function (t) { return [t[0], t[1].split(",")[0], null, null, { time: same(f.time, [t[0]]) ? [] : [t[0]] }]; })
        .concat([["", "Time not stated", null, null, null]]);
      return null;
    }
    // A bar is "on" when the filter keeps it. The chart counts with its own dimension's filter lifted (crossfilter), so
    // every bar keeps its full figure and the bars that are on add up to the headline: a pick highlights a bar rather
    // than turning the chart into a copy of the headline (ux-review, 2026-11-19).
    function isOn(id, key) {
      var f = cur.filter;
      if (id === "by-year") return !!f.years && +key >= f.years[0] && +key <= f.years[1];
      if (id === "by-user") return f.user.indexOf(key) >= 0;
      if (id === "by-other") return f.other.indexOf(key) >= 0;
      if (id === "by-day" || id === "crime-by-day") return f.days.indexOf(key) >= 0;
      if (id === "by-time" || id === "crime-by-time") return f.time.indexOf(key) >= 0;
      if (id === "by-cause") return f.cause.indexOf(key) >= 0;
      if (id === "crime-groups") return f.crimeKinds.indexOf(key) >= 0;
      if (id === "crime-by-year") return !!f.crimeYears && +key >= f.crimeYears[0] && +key <= f.crimeYears[1];
      if (id === "by-hin") return f.hin === key;
      if (id === "by-hin-group") return f.hinGroup.indexOf(+key) >= 0;
      if (id === "worst-overlap") return cur.worst === +key;
      if (id === "bci-mix") return f.bci.indexOf(+key) >= 0;
      if (id === "by-severity") return S.sevLevel(key) <= S.sevLevel(f.severity);
      if (id === "by-hood") return !!f.area && f.area.hood === key;
      if (id === "by-district") return !!f.area && f.area.district === +key;
      return false;
    }
    // The filter patch that lifts a chart's own dimension, or null where the filter isn't a set of the chart's bars (a
    // mix of whole causes and subcauses at the top level): that chart then counts under the full filter.
    function lift(id) {
      var f = cur.filter;
      if (id === "by-year") return { years: null };
      if (id === "by-user") return { user: [] };
      if (id === "by-other") return { other: [] };
      if (id === "by-hin-group") return { hinGroup: [] };
      if (id === "crime-groups") return { crimeKinds: [] };
      if (id === "crime-by-year") return { crimeYears: null };
      // Single days the day chart's bars can't make (Friday alone), so it counts under the full filter.
      if (/day/.test(id) && f.days.length && S.DAYS.every(function (d) { return d[0] !== f.days[0]; })) return null;
      if (id === "by-day" || id === "crime-by-day") return { days: [] };
      if (id === "by-time" || id === "crime-by-time") return { time: [] };
      if (id === "by-hin") return { hin: "all" };
      if (id === "by-severity") return { severity: "pain" };
      // Each area chart lifts only its own kind of area: the district chart under a neighborhood counts that
      // neighborhood's people by district, and the reverse, so the bars still sum to the headline.
      if (id === "by-hood") return f.area && f.area.hood ? { area: null } : null;
      if (id === "by-district") return f.area && f.area.district ? { area: null } : null;
      if (id === "by-cause") { var dk = drillCause();
        if (dk && causeNode(dk)) return { cause: [dk] };
        return f.cause.every(function (c) { return c.indexOf("/") < 0; }) ? { cause: [] } : null; }
      return null;
    }
    // A bar's row is 30 px, or 44 px on a tablet's touch screen, where the row is the tap target (Bryan, 2026-11-20:
    // "make all tap targets at least the recommended minimum on tablet"). The bar and its label keep their size and
    // sit in the middle of the taller row.
    function rowPad(pitch) {
      var touch = !!(window.matchMedia && matchMedia("(pointer: coarse) and (min-width: 700px)").matches);
      return touch ? (46 - pitch) / 2 : 0;
    }
    ctl.chart = function () {
      // The chart picker reads its titles from CHART_TITLES, so the where-from one follows the toggle there too.
      CHART_TITLES["from-time"] = (fromThru() ? "Through cars" : "Cars") + " an hour by time of day";
      CHART_TITLES["from-groups"] = (fromThru() ? "Through cars" : "Share of cars") + " by where they " + (cur.ends === "from" ? "start" : cur.ends === "to" ? "end" : "start or end");
      var id = S.chartFor(cur);
      if (!D || !id) return null;
      var rows = [], title = CHART_TITLES[id], note = "", sub = "", up = null, B0 = bars(id);
      if (id === "worst-overlap") {
        rows = (D.worst ? D.worst.summary : []).map(function (r) { var o = r.miles_also_in_prior_year;
          return { label: String(r.year), value: o || 0, key: String(r.year), pick: true, on: cur.worst === r.year,
            fig: o == null ? "first year" : o.toFixed(1) + " of " + r.miles.toFixed(0) + " mi also worst in " + (r.year - 1) }; });
        return barsTop({ id: id, title: title, note: "Click a year to draw its worst 10 miles.", max: 10 }, rows);
      }
      if (id === "by-hin-group") return hinGroupChart(id, title, B0);
      if (id === "from-groups") return fromChart(id, CHART_TITLES[id]);
      if (id === "from-time") return fromTimeChart(id, title);
      if (cur.view === "injuries") {
        var lp = lift(id), st = lp ? Object.assign({}, cur, { filter: Object.assign({}, cur.filter, lp) }) : cur;
        var shown = shownFor(st, S.areaGeom(st, D.hoods, D.districts));
        var full = {};
        if (id === "by-cause") (D.causes || []).forEach(function (c) { c.subs.forEach(function (sb) { full[c.key + "/" + sb.key] = sb.label; }); });
        rows = B0.map(function (b) { var n = 0; shown.forEach(function (p) { if (b[2](p)) n++; }); return { label: b[1], title: full[b[0]] || b[1], value: n, key: b[0], pick: !!b[4], on: !!lp && isOn(id, b[0]) }; });
        // The leftover bar only where someone is in it; unordered charts largest first under the current filters.
        rows = S.sortRows(id, rows.filter(function (r) { return r.key !== "" || r.value > 0 || id === "by-time"; }));
        if (id === "by-cause" && drillCause() && causeNode(drillCause())) { var nd = causeNode(drillCause()); sub = nd.label + ", by Vehicle Code section"; up = "All causes"; }
        if (rows.some(function (r) { return r.pick; })) note = rows.some(function (r) { return r.on; }) ? "Click a chosen bar again to clear it." : "Click a bar to filter the map.";
      } else if (/^crime-/.test(id) && !CR) {
        rows = [];
        note = "Loading SFPD reports.";
      } else if (id === "crime-by-day") {
        var lifted = !lift(id) ? false : true, wk = crimeByWeekday(lifted);
        rows = B0.map(function (b) { var d = S.DAYS.filter(function (x) { return x[0] === b[0]; })[0][2], n = 0; d.forEach(function (w) { n += wk[w]; }); return { label: b[1], value: n, key: b[0], pick: true, on: lifted && isOn(id, b[0]) }; });
        note = rows.some(function (r) { return r.on; }) ? "Click a chosen bar again to clear it." : "Click a bar to filter the map.";
      } else if (id === "crime-by-time") {
        var tl = !!lift(id), pq = crimeByPeriod(tl);
        rows = B0.map(function (b, q) { return { label: b[1], value: pq[q], key: b[0], pick: !!b[4], on: tl && isOn(id, b[0]) }; }).filter(function (r) { return r.key || r.value; });
        note = rows.some(function (r) { return r.on; }) ? "Click a chosen bar again to clear it." : "Click a bar to filter the map.";
      } else if (id === "stress-mix") {
        var m = stressMix();
        rows = [["Under 1.5", 0], ["1.5 to 3", 1], ["3 to 6", 2], ["6 to 12", 3], ["12 to 24", 4], ["24 to 48", 5], ["48 or more", 6]].map(function (x) { return { label: x[0], value: m.cls[x[1]] }; });
        note = "Measured, modelled or estimated.";
      } else if (id === "through-mix") {
        // Two stacked bars, main streets and residential, each split by class in the map's own colours.
        var tm = throughMix(), trows = [];
        [["Main streets", tm.main], ["Residential", tm.res]].forEach(function (r) { TT_LAB.forEach(function (l, k) { trows.push({ road: r[0], cls: l, value: r[1][k] }); }); });
        // Each bar prints its own figure: the share of its blocks that carry mostly through traffic.
        var ends = [["Main streets", tm.main], ["Residential", tm.res]].map(function (r) { var n = r[1].reduce(function (a, b) { return a + b; }, 0);
          return { road: r[0], value: n, text: n ? Math.round(100 * (r[1][2] + r[1][3]) / n) + "% mostly through" : "none" }; });
        var tx = throughX();
        return { id: id, title: title, note: "Blocks the model's network carries, over " + tx.minCars + " car trips " + (tx.bin ? "in these hours" : "a day") + ".", data: { rows: trows, ends: ends },
          marks: [{ mark: "barX", data: "rows", transform: "stackX", options: { y: "road", x: "value", fill: "cls", order: TT_LAB } },
            { mark: "text", data: "ends", options: { y: "road", x: "value", text: "text", textAnchor: "start", dx: 5 } }],
          options: { height: 100, marginTop: 4, marginBottom: 20, marginLeft: 84, marginRight: 112, color: { domain: TT_LAB, range: TT }, y: { label: null, domain: ["Main streets", "Residential"] }, x: { label: null } } };
      } else if (id === "bci-mix") {
        var bm = bciMix();
        rows = D.bci.labels.map(function (l, i) { return { label: l, value: bm[i], key: String(i), pick: true, on: isOn(id, String(i)) }; });
        note = "Over " + D.bci.aaa.score + " is SFMTA's all ages and abilities line. Lower is less comfortable." + (rows.some(function (r) { return r.on; }) ? " Click the chosen bar again to clear it." : " Click a bar to show only it.");
      } else if (id === "crime-groups" || id === "crime-by-year") {
        var cm = id === "crime-groups" ? crimeMix().groups : crimeBy(crimeSel({ years: true }), "y");
        rows = B0.map(function (b, i) { return { label: b[1], value: cm[i], key: b[0], pick: true, on: isOn(id, b[0]) }; });
        note = rows.some(function (r) { return r.on; }) ? "Click a chosen bar again to clear it." : "Click a bar to filter the map.";
      }
      // A chart whose bars split one total prints each bar's share after its count (Bryan, 2026-11-19, thread
      // ejssnxf4thic: "Show (%) on these charts where appropriate"); the years are a series, not a split.
      var out = barsTop({ id: id, title: title, subtitle: sub, note: note, up: up, pct: id !== "by-year" && id !== "crime-by-year" }, rows);
      // Each comfort class's bar in its map colour, so the bars split at the all-ages line as the streets do.
      if (id === "bci-mix") {
        out.data.rows.forEach(function (r) { if (r.fill === "kept") r.fill = r.label; });
        out.options.color = { domain: D.bci.labels.concat(["other"]), range: BCI.concat(["#c9ced6"]) };
      }
      return out;
    };
    // Bars with each name above its bar and the figure at the bar's end, so a long name (a Vehicle Code section) reads
    // in full at a phone's half width rather than squeezing the bar to nothing. Each row's `y` is its key, or its label.
    function barsTop(head, rows) {
      var PAD = rowPad(30);
      var max = head.max || rows.reduce(function (a, r) { return Math.max(a, r.value); }, 0) || 1, pct = head.pct;
      delete head.max; delete head.pct;
      if (pct) { var sh = shares(rows.map(function (r) { return r.value; })); rows.forEach(function (r, i) { if (sh[i]) r.fig = n0(r.value) + " (" + sh[i] + ")"; }); }
      // With a bar picked, the bars the filter keeps stay in the map's colour and the rest go grey.
      var any = rows.some(function (r) { return r.on; });
      rows.forEach(function (r) { r.y = r.key !== undefined ? r.key : r.label; r.fig = r.fig != null ? r.fig : n0(r.value); r.fill = !any || r.on ? "kept" : "other"; });
      return Object.assign(head, { data: { rows: rows }, marks: [
        { mark: "barX", data: "rows", options: { y: "y", x: "value", fill: "fill", insetTop: 14 + PAD, insetBottom: 1 + PAD } },
        { mark: "text", data: "rows", options: { y: "y", text: "label", frameAnchor: "left", textAnchor: "start", dy: -6, textOverflow: "ellipsis", lineWidth: 24 } },
        { mark: "text", data: "rows", options: { y: "y", x: "value", text: "fig", textAnchor: "start", dx: 4, dy: 7, fill: "var(--sm-muted, #59626f)" } }],
        options: { height: rows.length * (30 + 2 * PAD) + 4, marginTop: 2, marginBottom: 2, marginLeft: 1, marginRight: Math.max(pct ? 66 : 40, 8 + 6.4 * rows.reduce(function (a, r) { return Math.max(a, String(r.fig).length); }, 0)), y: { domain: rows.map(function (r) { return r.y; }), axis: null, padding: 0.08 },
          x: { axis: null, domain: [0, max] }, color: { domain: ["kept", "other"], range: ["#2f7d76", "#c9ced6"] } } });
    }
    // Each value's share of their total, whole percents that add to 100 (largest remainder); a bar under half a percent
    // prints "<1%" rather than 0%. Null for every bar when the total is 0.
    function shares(vals) {
      var t = vals.reduce(function (a, b) { return a + b; }, 0);
      if (!t) return vals.map(function () { return null; });
      var raw = vals.map(function (v) { return 100 * v / t; }), fl = raw.map(Math.floor), left = 100 - fl.reduce(function (a, b) { return a + b; }, 0);
      raw.map(function (r, i) { return i; }).sort(function (a, b) { return (raw[b] - fl[b]) - (raw[a] - fl[a]) || a - b; }).slice(0, left).forEach(function (i) { fl[i]++; });
      return fl.map(function (p, i) { return vals[i] > 0 && p === 0 ? "<1%" : p + "%"; });
    }
    ctl.shares = shares;   // for site/tests/safety-map-test.mjs and street-safety-check
    // The 10-mile groups chart: one bar per group, worst first, split by severity in the map's own colours, each with
    // its counts printed (Bryan, 2026-11-19: "a bar chart on the bottom right showing seriously
    // injured, killed for each 10 mile segment"). It counts under every filter but its own, so a picked group is
    // highlighted rather than left alone.
    function hinGroupChart(id, title, B0) {
      var PAD2 = rowPad(24);
      if (!groupData()) return { id: id, title: title, note: "10-mile groups aren't available for the 2017 network: its public map has no block ids.", data: { rows: [] }, marks: [], options: { height: 1 } };
      var g = area(), st = Object.assign({}, cur, { filter: Object.assign({}, cur.filter, { hinGroup: [] }) });
      var shown = shownFor(st, g);
      var lv = S.sevLevel(cur.filter.severity), sevs = S.SEVERITIES.filter(function (x) { return x[2] <= lv; });
      var colOf = sevCols();
      var rows = [], parts = [];
      B0.forEach(function (b) {
        var c = [0, 0, 0, 0];
        shown.forEach(function (p) { if (b[2](p)) c[p.sv]++; });
        var tot = c[0] + c[1] + c[2] + c[3];
        if (b[0] === "" && !tot) return;   // the leftover bar only where someone is in it
        rows.push({ y: b[0] || "none", key: b[0], label: b[1], value: tot, pick: b[4] != null, on: isOn(id, b[0]),
          fig: lv <= 1 ? (lv ? n0(c[1]) + " severe, " : "") + n0(c[0]) + " killed" : n0(tot) + " hurt, " + n0(c[0]) + " killed" });
        sevs.forEach(function (x) { parts.push({ y: b[0] || "none", sev: x[1], value: c[x[2]] }); });
      });
      var any = rows.some(function (r) { return r.on; }), on = {}, sh = shares(rows.map(function (r) { return r.value; }));
      rows.forEach(function (r, i) { on[r.y] = !any || r.on; if (sh[i]) r.fig += " (" + sh[i] + ")"; });
      parts.forEach(function (pt) { pt.fill = on[pt.y] ? pt.sev : "Not picked"; });
      var max = rows.reduce(function (a, r) { return Math.max(a, r.value); }, 0) || 1;
      var dom = sevs.map(function (x) { return x[1]; }).concat(["Not picked"]), rng = sevs.map(function (x) { return colOf[x[2]]; }).concat(["#dfe3e8"]);
      var note = (any ? "Click the chosen group again to clear it." : "Click a group to show only it.") + " Ranked on " + cur.rank.replace("-", " to ") + ".";
      return { id: id, title: title, note: note, data: { rows: rows, parts: parts }, marks: [
        { mark: "barX", data: "rows", options: { y: "y", x: "value", fill: "transparent", insetTop: 11 + PAD2, insetBottom: 1 + PAD2 } },
        { mark: "text", data: "rows", options: { y: "y", text: "label", frameAnchor: "left", textAnchor: "start", dy: -6, fontSize: 10 } },
        { mark: "barX", data: "parts", transform: "stackX", options: { y: "y", x: "value", fill: "fill", order: dom, insetTop: 11 + PAD2, insetBottom: 1 + PAD2 } },
        { mark: "text", data: "rows", options: { y: "y", x: "value", text: "fig", textAnchor: "start", dx: 4, dy: 5, fontSize: 10, fill: "var(--sm-muted, #59626f)" } }],
        options: { height: rows.length * (24 + 2 * PAD2) + 4, marginTop: 2, marginBottom: 2, marginLeft: 1, marginRight: 122, y: { domain: rows.map(function (r) { return r.y; }), axis: null, padding: 0.08 },
          x: { axis: null, domain: [0, max] }, color: { domain: dom, range: rng } } };
    }
    // Hovering a bar: everyone outside it dims on the map (the people layers), or the heat map shows only its days.
    var hover = { expr: null, days: null, per: null, kind: null, year: null };
    ctl.chartHover = function (key) {
      if (cur.view === "from") { setFromHl("hover", key == null ? null : key); return; }
      var id = S.chartFor(cur), b = key == null ? null : (bars(id) || []).filter(function (x) { return x[0] === key; })[0];
      var next = { expr: null, days: null, per: null, kind: null, year: null };
      if (b && cur.view === "injuries" && b[3]) next.expr = b[3];
      if (b && id === "crime-by-day") next.days = S.weekdays([key]);
      if (b && id === "crime-by-time" && key) next.per = S.TIMES.map(function (x) { return x[0]; }).indexOf(key);
      if (b && id === "crime-groups") next.kind = KIND_IDS.indexOf(key);
      if (b && id === "crime-by-year") next.year = +key - S.CRIME_YEARS[0];
      if (same(next, hover) || !built) return;
      hover = next;
      var e = hover.expr, dim = function (lo) { return e ? ["case", e, 1, lo] : 1; };
      [["fan", "icon-opacity", 0.15], ["fan-lab", "text-opacity", 0], ["hinc", "circle-opacity", 0.15], ["hinc", "circle-stroke-opacity", 0.15], ["minor", "circle-opacity", 0.12], ["minor", "circle-stroke-opacity", 0.12], ["minor-fan", "icon-opacity", 0.12]].forEach(function (x) {
        if (BASE[x[0]]) { BASE[x[0]][x[1]] = dim(x[2]); applyFactor(x[0]); }
      });
      applyFilters();
    };
    // Picking a bar sets its filter; picking the bar already chosen clears it. `up` leaves a drilled cause.
    ctl.chartPick = function (key) {
      var id = S.chartFor(cur);
      if (key === "up") { ctl.chartHover(null); ctl.setState({ filter: { cause: [] }, crash: null }); return; }
      var b = (bars(id) || []).filter(function (x) { return x[0] === key; })[0];
      if (!b || !b[4]) return;
      ctl.chartHover(null);
      if (b[4].state) ctl.setState(Object.assign({ crash: null }, b[4].state));
      else ctl.setState({ filter: b[4], crash: null });
    };

    // ---- Drawing an area: terra-draw's polygon mode, loaded the first time a reader asks ----
    var TD = { core: ["https://cdn.jsdelivr.net/npm/terra-draw@1.40.0/dist/terra-draw.umd.js", "sha384-3ODPOn5sOqhJjcBuMXfdJ4IPcUjLoc6dYjQuIItFywk5AH7GbkHczaQb5SZK6TlE"],
      adapter: ["https://cdn.jsdelivr.net/npm/terra-draw-maplibre-gl-adapter@1.5.0/dist/terra-draw-maplibre-gl-adapter.umd.js", "sha384-tE70KbU/wTkvNmGjc6IWlRU5lZSL/JyIw8ok1AB90T4SEjwYPgspmMzw4JWEOCCu"] };
    function load(src) {
      return new Promise(function (ok, bad) { var t = document.createElement("script"); t.src = src[0]; t.integrity = src[1]; t.crossOrigin = "anonymous"; t.onload = ok; t.onerror = function () { bad(new Error("could not load " + src[0])); }; document.head.appendChild(t); });
    }
    var drawLib = null, drawing = null;
    // Resolves with the drawn area once the reader closes the shape (a double click, or a click on the first point), or
    // null if they cancel. The area goes into the state's filter.
    ctl.drawArea = function () {
      if (!map) return Promise.resolve(null);
      drawLib = drawLib || (window.terraDraw ? Promise.resolve() : load(TD.core)).then(function () { return window.terraDrawMaplibreGlAdapter ? null : load(TD.adapter); });
      return drawLib.then(function () {
        ctl.cancelDraw();
        var T = window.terraDraw, A = window.terraDrawMaplibreGlAdapter;
        var d = new T.TerraDraw({ adapter: new A.TerraDrawMapLibreGLAdapter({ map: map }), modes: [new T.TerraDrawPolygonMode({ styles: { fillColor: col("--sm-highlight"), fillOpacity: 0.12, outlineColor: col("--sm-highlight"), outlineWidth: 2, closingPointColor: "#fff", closingPointOutlineColor: col("--sm-highlight") } })] });
        d.start(); d.setMode("polygon");
        return new Promise(function (ok) {
          drawing = { d: d, ok: ok };
          d.on("finish", function (id) {
            var f = d.getSnapshot().filter(function (x) { return x.id === id; })[0];
            var ring = f && f.geometry && f.geometry.coordinates && f.geometry.coordinates[0];
            if (drawing) drawing.ok = function () {}; // finished, not cancelled: don't resolve null first
            ctl.cancelDraw();
            if (!ring) { ok(null); return; }
            ctl.setState({ filter: { area: { polygon: ring } }, crash: null }, { duration: 400, fit: false });
            ok(ring);
          });
        });
      });
    };
    ctl.cancelDraw = function () {
      if (!drawing) return;
      var x = drawing; drawing = null;
      try { x.d.clear(); x.d.stop(); } catch (e) { /* already stopped */ }
      x.ok(null);
    };
    ctl.data = function () { return D; };
    ctl.map = function () { return map; };

    var trRuns = [];
    // The less severe injuries come as columns (map.json `minor`); each becomes a person like the rest, with `mi` set,
    // no crash card and no figure: they draw as small dots and count wherever the severity filter reaches them.
    // The people drawn without a crash card, from map.json `light` (2021 on) or the older file: columns to the same
    // person objects as the carded ones, `mi` marking them. A police death the fatality log also lists is not here:
    // it is the log's person among the carded ones, with the police row's fields (street-safety-map.py log_deaths()).
    // `np` rows have no place in the police record: no point (`c` null),
    // counted wherever no place is needed (state.js shownTest) and never drawn (features()).
    function lightPeople(M) {
      var d0 = Date.parse(M.d0 + "T00:00:00Z"), np = {}, out = [];
      (M.np || []).forEach(function (i) { np[i] = 1; });
      for (var i = 0; i < M.n; i++) {
        var c = np[i] ? null : [M.x[i] / 1e5, M.y[i] / 1e5], hd = M.hood[i], sv = M.sv[i];
        out.push({ c: c, s: c, np: np[i] ? 1 : 0, n: 1, si: 0, cs: "", k: sv === 0 ? 1 : 0, i: "", lab: "", d: new Date(d0 + M.dd[i] * 864e5).toISOString().slice(0, 10), h: M.h[i],
          u: M.users[M.u[i]], ck: M.cks[M.ck[i]], sk: M.sks[M.sk[i]], at: M.at[i], hood: hd >= 0 && D.hoods[hd] ? D.hoods[hd].name : "",
          hy: M.hy[i], hs: M.hs[i], hs22: M.hs22 ? M.hs22[i] : -1, op: M.ops ? M.ops[M.op[i]] : "", lg: 0, sv: sv, mi: 1 });
      }
      return out;
    }
    function prepPerson(p) {
      p.wd = new Date(p.d + "T12:00:00Z").getUTCDay();
      p.yr = +p.d.slice(0, 4);
      p.dist = p.np ? 0 : districtOf(p.c);
      if (p.sv == null) p.sv = p.k ? 0 : 1;
      // Each person's 10-mile group under each ranking window, from the HIN segment they're on (`hs`).
      if (D.hinGroups) D.hinGroups.windows.forEach(function (w) { p["hg:" + w] = p.hs >= 0 ? D.hinGroups.g[w][p.hs] : 0; });
      if (D.hinGroups22) D.hinGroups22.windows.forEach(function (w) { p["hg22:" + w] = p.hs22 >= 0 ? D.hinGroups22.g[w][p.hs22] : 0; });
    }
    function features(from) {
      return people.slice(from).map(function (p, j) {
        if (p.np) return null;   // no point to draw; the feature ids stay each person's index
        var i = from + j, st = Math.min(p.si || 0, 4) * 3;
        var sp = p.mi ? (LIGHT_ICON[p.u] || "dot") + (p.sv === 2 ? "-v" : "-p") : p.i + (p.k ? "-k" : "-s");
        return { type: "Feature", id: i, properties: Object.assign({}, p, { ix: i, o: [st, -st], to: [st / 10, -st / 10 + 1.75], sp: sp, h: p.h == null ? -1 : p.h, wd: p.wd }), geometry: { type: "Point", coordinates: p.c } };
      }).filter(Boolean);
    }
    // 2005 to 2020 load when the Years filter first reaches before 2021 (Bryan, 2026-11-19).
    var older = { state: "none", p: null };
    ctl.olderLoading = function () { return older.state === "loading"; };
    function needOlder() { var y = cur.filter.years; return cur.view === "injuries" && D && D.light && D.light.older && (!y || y[0] < D.light.older.to + 1); }
    function loadOlder(force) {
      if (older.state !== "none" || (!force && !needOlder())) return;
      older.state = "loading";
      var url = opts.olderUrl || String(opts.dataUrl).replace(/[^/]*$/, D.light.older.file);
      var el = document.getElementById("ss-older");   // the board copy carries the file inline (index.mjs, inlineData)
      older.p = (el ? Promise.resolve().then(function () { return JSON.parse(el.textContent); })
        : fetch(url).then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); })).then(function (M) {
        var from = people.length, add = lightPeople(M);
        add.forEach(function (p) { prepPerson(p); people.push(p); });
        older.state = "loaded";
        var all = features(0);
        map.getSource("exact").setData({ type: "FeatureCollection", features: all });
        applyFilters(); applyExtras();
        emit("set");
        return from;
      }, function (e) { older.state = "none"; console.error("older years:", e); emit("set"); });
      emit("set");
    }
    ctl.olderLoaded = function () { return older.state === "loaded" ? Promise.resolve() : older.p || Promise.resolve(); };
    // The heat maps' scale for what is shown and in view (densityPeak): the people the filters keep (deaths weigh
    // three, as heatmap-weight does) or the crime places with reports in the day and time, inside the view widened by
    // half its size, at the zooms either side of the current one. Rerun on every state change and every moveend.
    var heatKey = "", shownKey = "", shownPeople = [];
    function rescaleHeat() {
      if (!map || !D) return;
      var z = map.getZoom(), b = map.getBounds(), dx = (b.getEast() - b.getWest()) / 2, dy = (b.getNorth() - b.getSouth()) / 2;
      var W = b.getWest() - dx, E = b.getEast() + dx, S0 = b.getSouth() - dy, N = b.getNorth() + dy;
      var inView = function (c) { return c[0] >= W && c[0] <= E && c[1] >= S0 && c[1] <= N; };
      var layer, coords = [], w = [], rad, zmax;
      if (cur.view === "injuries" && map.getLayer("heat") && z < ICON_Z) {
        // The filtered set changes with the state, the view with every move, so a pan only re-runs the view test.
        var fk = JSON.stringify(cur.filter) + "|" + people.length;
        if (fk !== shownKey) { shownPeople = shownFor(cur, area()); shownKey = fk; }
        shownPeople.forEach(function (p) { if (p.c && inView(p.c)) { coords.push(p.c); w.push(p.k ? 3 : 1); } });
        layer = "heat"; rad = radiusAt; zmax = 16;
      } else if (cur.view === "crime" && map.getLayer("crime-heat")) {
        crimePlaces().forEach(function (i) { var c = CR.pts[i]; if (crimeSW[i] > 0 && inView(c)) { coords.push(c); w.push(crimeSW[i]); } });
        layer = "crime-heat"; rad = crimeRadius; zmax = 17;
      } else return;
      var z0 = Math.max(10, Math.min(zmax - 1, Math.floor(z))), z1 = z0 + 1;
      var key = layer + z0 + "|" + coords.length + "|" + w.reduce(function (a, v) { return a + v; }, 0) + "|" + [W, E, S0, N].map(function (v) { return v.toFixed(3); }).join(",");
      if (key === heatKey || !coords.length) return;
      heatKey = key;
      var p0 = densityPeak(coords, w, rad(z0), z0, 0.99), p1 = densityPeak(coords, w, rad(z1), z1, 0.99);
      if (!p0 || !p1) return;
      map.setPaintProperty(layer, "heatmap-intensity", ["interpolate", ["linear"], ["zoom"], z0, 1 / p0, z1, 1 / p1]);
    }
    ctl.heatScale = function () { return map && map.getPaintProperty(cur.view === "crime" ? "crime-heat" : "heat", "heatmap-intensity"); };   // for street-safety-check
    // The groups of the HIN edition the state picks (S.hinEdition): 2024's, 2022's, or none for 2017.
    function groupData() { var ed = S.hinEdition(cur); return ed === "2022" ? D.hinGroups22 || null : ed === "2017" ? null : D.hinGroups || null; }
    function groupFeatures() {
      var G = groupData() || D.hinGroups, g = G.g[cur.rank] || G.g[G.windows[0]];
      return B.collection(B.decode(G.runs).map(function (r, i) { return { type: "Feature", properties: { g: g[G.s[i]] }, geometry: { type: "LineString", coordinates: r } }; }));
    }
    // The extras a state sets beyond the filters: the groups' ranking window and picked groups, the worst year, and the
    // heat map's scale for the severity level.
    var extras = { rank: null, lv: null };
    function applyExtras() {
      if (!D.hinGroups || !map.getLayer("hin-groups")) return;
      var ed = S.hinEdition(cur), GD = groupData() || D.hinGroups;
      CHART_TITLES["by-hin-group"] = "People hurt by 10 miles of the " + ed + " HIN, worst first";
      if (extras.rank !== cur.rank + ed) {
        map.getSource("hin-groups").setData(groupFeatures()); extras.rank = cur.rank + ed;
        var gm = ["match", ["get", "g"]];
        groupColours(GD.groups[GD.windows[0]].length).forEach(function (c, i) { gm.push(i + 1, c); });
        map.setPaintProperty("hin-groups", "line-color", gm.concat(["#c9ced6"]));
      }
      var sel = cur.filter.hinGroup;
      BASE["hin-groups"]["line-opacity"] = sel.length ? ["case", ["in", ["get", "g"], ["literal", sel]], 0.95, 0.12] : 0.95;
      applyFactor("hin-groups");
      // With every group drawn, the heat at full strength hides the ramp, so it softens until a group is picked.
      var soft = (cur.hin.indexOf("groups") >= 0 || cur.hin.indexOf("groups22") >= 0) && !sel.length;
      if (BASE.heat && extras.soft !== soft) { BASE.heat["heatmap-opacity"] = soft ? 0.4 : 0.8; applyFactor("heat"); extras.soft = soft; }
      var k = S.WORST_YEARS.indexOf(cur.worst);
      map.setFilter("worst", ["!=", ["%", ["floor", ["/", ["get", "y"], Math.pow(2, Math.max(0, k))]], 2], 0]);
      rescaleHeat();
    }
    dataP.then(function (data) {
      D = data;
      D.districts = (opts.districts || []).map(function (d) { return { district: d.district, geom: { type: "MultiPolygon", coordinates: d.coords } }; });
      cur = fitCause(cur);
      people = D.people;
      if (D.light) people = people.concat(lightPeople(D.light));
      people.forEach(function (p, i) {
        if (!p.mi) { var k = p.s.join(","); (bySpot[k] = bySpot[k] || []).push(i); }
        prepPerson(p);
      });
      map = B.create(mapEl, { bounds: D.bounds, padding: function () { return 4; }, cooperative: opts.cooperative !== false, interactive: opts.interactive !== false,
        onReset: function () { ctl.setState({ camera: null }, { duration: 400 }); } });
      if (!map) { rejectReady(new Error("no WebGL")); return; }
      // In a story on a phone the step cards and the crash card fill the lower part, so every step's camera centres
      // the upper part of the map.
      if (opts.story && narrow()) map.setPadding({ top: 0, left: 0, right: 0, bottom: Math.round(mapEl.clientHeight * 0.45) });
      // A story's steps set the camera, so the map takes no pan or zoom gestures and a finger or wheel on it scrolls
      // the page; a tap still opens a person's card.
      if (opts.story) ["scrollZoom", "dragPan", "dragRotate", "touchZoomRotate", "touchPitch", "doubleClickZoom", "boxZoom", "keyboard"].forEach(function (h) { if (map[h] && map[h].disable) map[h].disable(); });
      map.on("load", function () { build(); });
      // A resize (a tablet turned, a window dragged narrower) can move the icon zoom; the layers' zoom ranges follow.
      map.on("resize", function () {
        var z = iconZoom();
        if (z === ICON_Z || !built) return;
        ICON_Z = z;
        map.setLayerZoomRange("heat", 0, z); map.setLayerZoomRange("minor", z - 0.7, z);
        ["fan", "minor-fan"].forEach(function (l) { map.setLayerZoomRange(l, z, 24); map.setLayoutProperty(l, "icon-size", iconSize()); });
        rescaleHeat(); emit("set");
      });
      // A resize keeps the centre, but a story's frame should keep the step's camera too.
      map.on("resize", function () { if (opts.story && cur.camera && !map.isMoving()) map.jumpTo({ center: cur.camera.center, zoom: cur.camera.zoom, bearing: cur.camera.bearing || 0 }); });
    }).catch(function (e) { if (window.console) console.warn("safety map:", e && e.message); rejectReady(e); });

    function build() {
      var DARK = col("--sm-outline");
      ICONS.forEach(function (k) { [["s", col("--sm-severe")], ["k", col("--sm-killed")]].forEach(function (v) { SPR[k + "-" + v[0]] = sprite(k, v[1], DARK); }); });
      // The lower levels' icons, in their greys with a softer outline; "dot" for a mode with no icon.
      ICONS.concat(["dot"]).forEach(function (k) { [["v", col("--sm-visible")], ["p", col("--sm-pain")]].forEach(function (v) { SPR[k + "-" + v[0]] = k === "dot" ? dotSprite(v[1], "#6b737d") : sprite(k, v[1], "#6b737d"); }); });
      Object.keys(SPR).forEach(function (k) { map.addImage(k, SPR[k].getContext("2d").getImageData(0, 0, 48, 48), { pixelRatio: 2 }); });
      // The key's Travel mode icons: white with the dark outline, so the mode reads apart from the severity colours.
      ICONS.forEach(function (k) { SPR[k + "-n"] = sprite(k, "#ffffff", DARK); });
      SPR["stop-square"] = stopSquare(DARK);
      map.addImage("stop-square", SPR["stop-square"].getContext("2d").getImageData(0, 0, 32, 32), { pixelRatio: 2 });
      if (map.style && map.style.setTransition) map.style.setTransition({ duration: 0, delay: 0 });
      var b = B.under(map), lines = function (enc) { return B.collection(B.decode(enc).map(function (r) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: r } }; })); };
      // A layer someone else added (the Muni routes), taken into the fades as if add() had made it.
      function adopt(id) { var l = map.getLayer(id); BASE[id] = {}; (OPACITY[l.type] || []).forEach(function (p) { BASE[id][p] = map.getPaintProperty(id, p); }); factor[id] = 0; map.setLayoutProperty(id, "visibility", "none"); applyFactor(id); }
      function add(layer, before) { layer.layout = Object.assign({ visibility: "none" }, layer.layout || {}); map.addLayer(layer, before); BASE[layer.id] = {}; (OPACITY[layer.type] || []).forEach(function (p) { BASE[layer.id][p] = (layer.paint || {})[p]; }); factor[layer.id] = 0; applyFactor(layer.id); }
      [["hin17", col("--sm-hin-2017"), -2.5, "2017"], ["hin22", col("--sm-hin-2022"), 2.5, "2022"]].forEach(function (o) {
        map.addSource(o[0], { type: "geojson", data: lines(D.hinOlder[o[3]]) });
        add({ id: o[0], type: "line", source: o[0], 
          paint: { "line-color": o[1], "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.2, 14, 2.2, 17, 4], "line-opacity": 0.85, "line-offset": ["interpolate", ["linear"], ["zoom"], 12, 0, 15, o[2]] }, layout: o[3] === "2017" ? { "line-cap": "butt" } : { "line-cap": "round", "line-join": "round" } }, b);
        // Each edition its own line style, so overlapping years stay readable: 2017 is dashed.
        if (o[3] === "2017") map.setPaintProperty(o[0], "line-dasharray", [2, 1.5]);
      });
      map.addSource("hin", { type: "geojson", data: lines(D.hin) });
      add({ id: "hin", type: "line", source: "hin", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": col("--sm-hin"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 14, 2, 17, 4], "line-opacity": 0.55 } }, b);
      if (D.hinGroups) {
        var GC = groupColours(D.hinGroups.groups[D.hinGroups.windows[0]].length), gm = ["match", ["get", "g"]];
        GC.forEach(function (c, i) { gm.push(i + 1, c); });
        map.addSource("hin-groups", { type: "geojson", data: groupFeatures() });
        add({ id: "hin-groups", type: "line", source: "hin-groups", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": gm.concat(["#c9ced6"]),
          "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.8, 14, 3, 17, 6], "line-opacity": 0.95 } }, b);
        extras.rank = null;
      }
      if (D.worst) {
        map.addSource("worst", { type: "geojson", data: B.collection(B.decode(D.worst.runs).map(function (r, i) { return { type: "Feature", properties: { y: D.worst.y[i] }, geometry: { type: "LineString", coordinates: r } }; })) });
        add({ id: "worst", type: "line", source: "worst", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": WORST_COL, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 14, 4, 17, 8], "line-opacity": 0.9 } }, b);
      }
      add({ id: "hin-outline", type: "line", source: "hin", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": col("--sm-muted"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 16, 1.4], "line-opacity": 0.7 } }, b);
      // Highlights sit under the data, over the basemap.
      map.addSource("hl-area", { type: "geojson", data: B.collection([]) });
      map.addSource("hl-blocks", { type: "geojson", data: B.collection([]) });
      map.addSource("hl-ring", { type: "geojson", data: B.collection([]) });
      add({ id: "hl-area-fill", type: "fill", source: "hl-area", paint: { "fill-color": col("--sm-highlight"), "fill-opacity": 0.1 } }, b);
      add({ id: "hl-area-line", type: "line", source: "hl-area", paint: { "line-color": col("--sm-highlight"), "line-width": 2.5, "line-opacity": 1 } }, b);
      add({ id: "hl-blocks", type: "line", source: "hl-blocks", layout: { "line-cap": "round" }, paint: { "line-color": col("--sm-highlight"), "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 16, 14], "line-opacity": 0.35 } }, b);
      add({ id: "hl-ring", type: "line", source: "hl-ring", paint: { "line-color": col("--sm-highlight"), "line-width": 2.5, "line-dasharray": [2, 1.5], "line-opacity": 1 } });

      var exact = { type: "FeatureCollection", features: features(0) };
      map.addSource("exact", { type: "geojson", data: exact });
      var inten = 1;
      add({ id: "heat", type: "heatmap", source: "exact", maxzoom: ICON_Z, paint: { "heatmap-weight": ["+", 1, ["*", 2, ["get", "k"]]], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 12, 15, 34],
        "heatmap-intensity": inten, "heatmap-color": HEAT, "heatmap-opacity": 0.8 } }, b);
      add({ id: "fan", type: "symbol", source: "exact", minzoom: ICON_Z, layout: { "icon-image": ["get", "sp"], "icon-offset": ["array", "number", 2, ["get", "o"]], "icon-allow-overlap": true, "icon-ignore-placement": true,
        "icon-size": iconSize(), "symbol-sort-key": ["+", ["get", "si"], ["*", 100, ["get", "k"]]] }, paint: { "icon-opacity": 1 } });
      add({ id: "fan-lab", type: "symbol", source: "exact", minzoom: 16, layout: { "text-field": ["get", "lab"], "text-font": ["Noto Sans Regular"], "text-size": 10, "text-offset": ["array", "number", 2, ["get", "to"]],
        "text-anchor": "top", "text-max-width": 9, "text-padding": 0 }, paint: { "text-color": DARK, "text-halo-color": "#fff", "text-halo-width": 1.6, "text-opacity": 1 } });
      add({ id: "hinc", type: "circle", source: "exact", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3, 16, 7], "circle-stroke-color": "#fff", "circle-stroke-width": 0.8,
        "circle-color": ["case", ON_HIN, HINC[0][1], HINC[1][1]], "circle-opacity": 1, "circle-stroke-opacity": 1 } });

      add({ id: "minor", type: "circle", source: "exact", minzoom: ICON_Z - 0.7, maxzoom: ICON_Z, paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 12.6, 1.8, 17, 4.5],
        "circle-color": ["match", ["get", "sv"], 0, col("--sm-killed"), 1, col("--sm-severe"), 2, col("--sm-visible"), col("--sm-pain")], "circle-stroke-color": "#fff", "circle-stroke-width": 0.5, "circle-opacity": 0.9, "circle-stroke-opacity": 0.9 } }, "fan");
      // From the icon zoom, where the severe and killed become icons, so do these, the same size and under them.
      add({ id: "minor-fan", type: "symbol", source: "exact", minzoom: ICON_Z, layout: { "icon-image": ["get", "sp"], "icon-allow-overlap": true, "icon-ignore-placement": true,
        "icon-size": iconSize(), "symbol-sort-key": ["-", 3, ["get", "sv"]] }, paint: { "icon-opacity": 1 } }, "fan");
      // A dot opens its crash's card too (Bryan, 2026-11-20).
      ["minor", "minor-fan"].forEach(function (l) {
        map.on("click", l, function (e) { ctl.setState({ crash: keyOf(people[e.features[0].properties.ix]) }); });
      });
      // Bike comfort: SFMTA's Bike Comfort Index in its own five classes, least comfortable drawn last, on top.
      for (var bi = 4; bi >= 0; bi--) {
        map.addSource("bci" + bi, { type: "geojson", data: B.collection(B.decode(D.bci.runs[bi]).map(function (r, i) { return { type: "Feature", properties: { i: i }, geometry: { type: "LineString", coordinates: r } }; })) });
        add({ id: "bci" + bi, type: "line", source: "bci" + bi, layout: { "line-cap": "round" }, paint: { "line-color": BCI[bi], "line-width": ["interpolate", ["linear"], ["zoom"], 11, bi < D.bci.aaa.below ? 1.6 : 1.1, 16, bi < D.bci.aaa.below ? 5 : 3.5], "line-opacity": 1 } }, b);
      }

      var TR = D.traffic;
      trRuns = B.decode(TR.runs);
      map.addSource("stress", { type: "geojson", data: B.collection(trRuns.map(function (r, i) { var p = TR.p[i]; return { type: "Feature", properties: { c: p[0], s: p[1], i: i }, geometry: { type: "LineString", coordinates: r } }; })) });
      var stCol = ["match", ["get", "c"], 1, RT[1], 2, RT[2], 3, RT[3], 4, RT[4], 5, RT[5], RT[6]];
      var zw = function (a, c, e) { return ["interpolate", ["linear"], ["zoom"], 11, a, 13, c, 16, e]; };
      add({ id: "stress-grey", type: "line", source: "stress", filter: ["==", ["get", "s"], 3], paint: { "line-color": RT[0], "line-width": zw(0.4, 0.7, 1.5), "line-opacity": 0.6 } }, b);
      // Estimated blocks (Bryan, 2026-11-19: "the dash lines need to show up more"): full colour, close to the measured
      // width, and long dashes. A dash is counted in line widths, so it grows with the zoom-scaled width;
      // zoomed out the dash is shorter, so a single short block still shows a gap.
      add({ id: "stress-est", type: "line", source: "stress", filter: ["==", ["get", "s"], 2], paint: { "line-color": stCol, "line-width": zw(2, 3.1, 5.8), "line-opacity": 1,
        "line-dasharray": ["step", ["zoom"], ["literal", [1.4, 1.1]], 13.5, ["literal", [2.4, 1.3]]] } }, b);
      add({ id: "stress-mod", type: "line", source: "stress", filter: ["==", ["get", "s"], 1], layout: { "line-cap": "round" }, paint: { "line-color": stCol, "line-width": zw(1.4, 2.2, 4), "line-opacity": 0.75 } }, b);
      add({ id: "stress-meas", type: "line", source: "stress", filter: ["==", ["get", "s"], 0], layout: { "line-cap": "round" }, paint: { "line-color": stCol, "line-width": zw(2.2, 3.4, 6.5), "line-opacity": 1 } }, b);

      // Through traffic: the same blocks, coloured by through share where the model carries them, grey where it doesn't.
      var XT = D.through, inX = {};
      XT.i.forEach(function (r, j) { inX[r] = j; });
      map.addSource("through", { type: "geojson", data: B.collection(trRuns.map(function (run, r) { var j = inX[r], none = j === undefined;
        var pr = { r: r, j: none ? -1 : j, c: none ? -1 : XT.c[j], l: none ? 0 : XT.l[j], m: TR.p[r][10] ? 1 : 0 };
        Object.keys(XT.bins || {}).forEach(function (n) { pr["c_" + n] = none ? -1 : XT.bins[n].c[j]; pr["l_" + n] = none ? 0 : XT.bins[n].l[j]; });
        // Each other distance of the slider: c_n<distance> for the day, c_n<distance>_<bin> for an hour bin.
        Object.keys(XT.near || {}).forEach(function (d) { if (d === XT.defaultNear) return; var N = XT.near[d];
          pr["c_n" + d] = none ? -1 : N.c[j]; pr["l_n" + d] = none ? 0 : N.l[j];
          Object.keys(N.bins).forEach(function (n) { pr["c_n" + d + "_" + n] = none ? -1 : N.bins[n].c[j]; pr["l_n" + d + "_" + n] = none ? 0 : N.bins[n].l[j]; }); });
        return { type: "Feature", properties: pr, geometry: { type: "LineString", coordinates: run } }; })) });
      // Width carries the street's kind and colour only the share: main streets wide, residential thin.
      var ttW = ["interpolate", ["linear"], ["zoom"], 11, ["case", ["==", ["get", "m"], 1], 2, 0.9], 13, ["case", ["==", ["get", "m"], 1], 3.2, 1.4], 16, ["case", ["==", ["get", "m"], 1], 6.5, 2.6]];
      var ttCol = ttColor(["get", "c"]);
      add({ id: "through-grey", type: "line", source: "through", filter: ["<", ["get", "c"], 0], paint: { "line-color": RT[0], "line-width": zw(0.4, 0.7, 1.5), "line-opacity": 0.6 } }, b);
      add({ id: "through-low", type: "line", source: "through", filter: ["all", [">=", ["get", "c"], 0], ["==", ["get", "l"], 1]], layout: { "line-sort-key": ["get", "c"] },
        paint: { "line-color": ttCol, "line-width": ttW, "line-opacity": 1, "line-dasharray": ["literal", [1.6, 1.1]] } }, b);
      add({ id: "through", type: "line", source: "through", filter: ["all", [">=", ["get", "c"], 0], ["==", ["get", "l"], 0]], layout: { "line-cap": "round", "line-sort-key": ["get", "c"] },
        paint: { "line-color": ttCol, "line-width": ttW, "line-opacity": 1 } }, b);

      // Where traffic comes from: the regions' outlines, a bubble per neighborhood and region, the chosen area's own
      // cars as a ring, and each bubble's share with its count under it. A bigger bubble's label wins a collision,
      // and a smaller one's shows as the reader zooms in; neighborhood names join from zoom 12.2.
      map.addSource("from-regions", { type: "geojson", data: B.collection([]) });
      map.addSource("from-bubbles", { type: "geojson", data: B.collection([]) });
      add({ id: "from-regions", type: "line", source: "from-regions", paint: { "line-color": "#7b8794", "line-width": 1, "line-opacity": 0.8, "line-dasharray": ["literal", [3, 2]] } }, b);
      add({ id: "from-own", type: "circle", source: "from-bubbles", filter: ["==", ["get", "own"], 1],
        paint: { "circle-radius": ["get", "r"], "circle-color": WF_OWN, "circle-opacity": 0.06, "circle-stroke-color": WF_OWN, "circle-stroke-width": 2, "circle-stroke-opacity": 0.9 } });
      add({ id: "from-bubbles", type: "circle", source: "from-bubbles", filter: ["==", ["get", "own"], 0], layout: { "circle-sort-key": ["-", 0, ["get", "v"]] },
        paint: { "circle-radius": ["get", "r"], "circle-color": WF_FILL, "circle-opacity": 0.6, "circle-stroke-color": WF_LINE, "circle-stroke-width": 1, "circle-stroke-opacity": 0.9 } });
      add({ id: "from-hl", type: "circle", source: "from-bubbles", filter: ["in", ["get", "g"], ["literal", []]],
        paint: { "circle-radius": ["get", "r"], "circle-color": WF_FILL, "circle-opacity": 0.25, "circle-stroke-color": "#0b2545", "circle-stroke-width": 2.5, "circle-stroke-opacity": 1 } });
      var fmt = function (k) { return ["format", ["get", "t1"], { "font-scale": 1.15 }, "\n", {}, ["get", k], { "font-scale": 0.85 }]; };
      add({ id: "from-labels", type: "symbol", source: "from-bubbles",
        layout: { "text-field": ["step", ["zoom"], ["case", ["==", ["get", "lab"], 1], fmt("t2"), ""], 12.2, fmt("t3")], "text-font": ["Noto Sans Regular"], "text-size": 11.5, "text-line-height": 1.1, "text-max-width": 9, "text-padding": 1,
          // A label that would land on a bigger bubble's moves beside its own bubble before it is dropped.
          "text-variable-anchor": ["center", "top", "bottom", "left", "right"], "text-radial-offset": 0.9, "text-justify": "auto",
          "symbol-sort-key": ["get", "k"] },
        paint: { "text-color": "#0b2545", "text-halo-color": "rgba(255,255,255,0.95)", "text-halo-width": 2, "text-opacity": 1 } });
      map.on("move", function () { if (cur.view === "from" && fromList.length) placeFrom(); });
      map.on("resize", function () { fromKey = ""; if (cur.view === "from") applyFrom(); });
      fromKey = "";
      map.addSource("crime-stops", { type: "geojson", data: B.collection(D.stops.map(function (s) { return { type: "Feature", properties: { name: s[2] }, geometry: { type: "Point", coordinates: [s[0], s[1]] } }; })) });
      // Each place's reports in the day and time choice; crimeData() fills it.
      map.addSource("crime", { type: "geojson", data: B.collection([]) });
      crimeKey = "";
      // Muni's frequent lines, drawn and numbered the way the Muni dashboard draws them (src/muni.mjs ROUTE_JS), each in
      // SFMTA's own colour from its GTFS route_color (Bryan, 2026-11-19: "color the bus lines using the standard coloring
      // that SFMTA uses on their transit line map"). Thin and part transparent so the heat underneath still reads; the
      // Metro lines a little wider and drawn over the buses.
      if (opts.routes && D.muni) {
        map.addSource("muni", { type: "geojson", data: opts.routes.feats(D.muni) });
        var metro = function (a, c) { return ["case", ["==", ["get", "y"], 0], a, c]; };
        opts.routes.add(map, "muni", b, { width: ["interpolate", ["linear"], ["zoom"], 11, metro(1.4, 0.8), 14, metro(2.6, 1.6), 17, metro(4.5, 3)] });
        map.setLayoutProperty("routes", "line-sort-key", ["-", 3, ["get", "y"]]);
        map.setPaintProperty("routes", "line-opacity", 0.65);
        adopt("routes");
      }
      // Crime stays a heat map at every zoom (Bryan, 2026-11-19: "can we keep the crime layer as a heat map?"); the
      // radius keeps growing past zoom 15 so a single intersection's reports still read at 15 to 17.
      // Its first scale is every report but Other's (setCrimeIntensity), set once crime.json is in; rescaleHeat then
      // fits it to what the filters keep in view.
      add({ id: "crime-heat", type: "heatmap", source: "crime", paint: { "heatmap-weight": ["get", "sw"], "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 12, 15, 34, 17, 58], "heatmap-intensity": 1,
        "heatmap-color": HEAT, "heatmap-opacity": 0.8 } }, b);
      // The intersections, all but unseen, so a tap still opens the count of reports there.
      add({ id: "crime-dots", type: "circle", source: "crime", minzoom: 13.4, paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 13.4, 6, 17, 14], "circle-color": "#000", "circle-opacity": 0.01, "circle-stroke-opacity": 0 } });
      setCrimeIntensity();
      // Muni stops are a different mark from the reports: a white square with a dark outline, drawn on top.
      add({ id: "crime-stops", type: "symbol", source: "crime-stops", layout: { "icon-image": "stop-square", "icon-allow-overlap": true, "icon-ignore-placement": true,
        "icon-size": ["interpolate", ["linear"], ["zoom"], 11, 0.25, 13, 0.4, 15, 0.7, 17, 1] }, paint: { "icon-opacity": 1 } });
      if (opts.routes && D.muni) { opts.routes.badges(map, "muni", undefined, { spacing: 320 }); map.setLayerZoomRange("route-badges", 12.5, 24); adopt("route-badges"); }

      // The area filter: everything outside it dims, and its edge is drawn.
      map.addSource("area-mask", { type: "geojson", data: B.collection([]) });
      map.addSource("area-edge", { type: "geojson", data: B.collection([]) });
      add({ id: "area-mask", type: "fill", source: "area-mask", paint: { "fill-color": "#fff", "fill-opacity": 0.55 } });
      add({ id: "area-edge", type: "line", source: "area-edge", paint: { "line-color": col("--sm-highlight"), "line-width": 2.5, "line-opacity": 1 } });

      function pointer(l) { map.on("mouseenter", l, function () { map.getCanvas().style.cursor = "pointer"; }); map.on("mouseleave", l, function () { map.getCanvas().style.cursor = ""; }); }
      ["fan", "hinc"].forEach(function (l) {
        // A click on a spot opens its cards on the first crash there (Bryan, 2026-11-19: "always start from #1"); a
        // link that names a later crash still opens on that one.
        map.on("click", l, function (e) {
          var p = people[e.features[0].properties.ix], spot = bySpot[p.s.join(",")];
          ctl.setState({ crash: keyOf(spot ? people[spot[0]] : p) });
        });
        pointer(l);
      });
      pointer("minor"); pointer("minor-fan");
      ["stress-meas", "stress-mod", "stress-est"].forEach(function (l) { map.on("click", l, function (e) { show(e.lngLat, stressCard(TR.p[e.features[0].properties.i], e.features[0].properties.i)); }); pointer(l); });
      ["through", "through-low"].forEach(function (l) { map.on("click", l, function (e) { show(e.lngLat, throughCard(e.features[0].properties.r, e.features[0].properties.j)); }); pointer(l); });
      // A tap on overlapping bubbles opens the smallest under it, which the bigger ones would otherwise hide.
      map.on("click", function (e) {
        if (cur.view !== "from" || drawing) return;
        var f = map.queryRenderedFeatures(e.point, { layers: ["from-bubbles", "from-own"] }).sort(function (x, y) { return x.properties.v - y.properties.v; })[0];
        var b = f ? fromList.filter(function (x) { return x.g === f.properties.g; })[0] : null;   // the merged "Rest of San Francisco" bubble has no card
        // After the popup's own close-on-click has run, so a tap on a second bubble swaps the card.
        setTimeout(function () { if (b) ctl.setState({ card: b.own ? "own" : b.name }); else if (cur.card) ctl.setState({ card: null }); }, 0);
      });
      pointer("from-bubbles");
      map.on("mousemove", "from-bubbles", function (e) {
        var f = e.features.slice().sort(function (x, y) { return x.properties.v - y.properties.v; })[0], b = f ? fromList.filter(function (x) { return x.g === f.properties.g; })[0] : null;
        setFromHl("hover", b ? (b.top ? b.g : "rest") : null);
      });
      map.on("mouseleave", "from-bubbles", function () { setFromHl("hover", null); });
      map.on("click", "crime-dots", function (e) {
        if (!CR) return;
        var i = e.features[0].properties.i, g = placeGroups(i), gs = crimeSel().gs, n = 0;
        g.forEach(function (v, j) { if (!gs || gs.indexOf(j) >= 0) n += v; });
        var w = S.whenLabel(cur.filter), when = w ? ", " + w + " only" : "";
        show(e.lngLat, '<div class="pop"><b>' + n0(n) + " SFPD report" + (n === 1 ? "" : "s") + " at this intersection</b><br>" +
          CR.groups.map(function (gn, j) { return g[j] && (!gs || gs.indexOf(j) >= 0) ? '<i class="dot" style="background:' + CG[j] + '"></i>' + esc(gn) + ": " + g[j] : ""; }).filter(Boolean).join("<br>") +
          '<br><span class="g">' + esc(crimeSpan()) + when + (gs ? "" : ", any kind of report") + "</span></div>"); });
      pointer("crime-dots");
      // Zoomed out, the people are a heat map with nothing to tap, so a tap zooms in to where each crash shows.
      map.on("click", function (e) {
        if (cur.view !== "injuries" || cur.color !== "people" || map.getZoom() >= ICON_Z || drawing) return;
        map.easeTo({ center: e.lngLat, zoom: 15.2, duration: 600 });
      });
      map.on("zoomend", function () { emit("zoom"); });

      // A reader's own pan and zoom becomes the state's camera, so the address always reopens what is on screen.
      map.on("moveend", function () { rescaleHeat(); });
      map.on("moveend", function (e) {
        // In a story the frame can change size under a flight (a crash card opening or closing below the map), so
        // the camera is put back where the step says once the move ends.
        // An interrupted flight also ends in a moveend, just before the next one starts, so the check waits a tick and
        // leaves the map alone while it is moving again.
        if (opts.story && !e.originalEvent) {
          setTimeout(function () {
            if (!cur.camera || map.isMoving()) return;
            var at = map.getCenter();
            if (Math.abs(at.lng - cur.camera.center[0]) > 1e-5 || Math.abs(at.lat - cur.camera.center[1]) > 1e-5 || Math.abs(map.getZoom() - cur.camera.zoom) > 0.01) map.jumpTo({ center: cur.camera.center, zoom: cur.camera.zoom, bearing: cur.camera.bearing || 0 });
          }, 0);
          return;
        }
        if (!e.originalEvent || opts.story) return;
        var c = map.getCenter();
        cur = S.merge(cur, { camera: { center: [c.lng, c.lat], zoom: map.getZoom(), bearing: map.getBearing() } });
        emit("camera");
      });

      applyFilters();
      applyHighlight();
      applyExtras();
      S.layersFor(cur).forEach(function (l) { fade(l, 1, 0); });
      if (cur.camera || cur.view === "from") moveCamera(0);
      else if (cur.filter.area) fitArea(0);
      if (cur.crash) openCard(cur.crash);
      fromCardHtml = fromCard; syncFromCard();
      // The bubbles' labels go above every line layer (the chosen area's outline ran over a label's first letter).
      map.moveLayer("from-labels");
      built = true;
      if (opts.hash) window.addEventListener("hashchange", function () { ctl.setState(S.fromHash(location.hash), { duration: 600, replace: true }); });
      emit("load");
      // An address or a story step that opens before 2021, or on the crime view, waits for the older years or the
      // crime reports before it counts as ready.
      loadOlder(); loadCrime();
      map.once("idle", function () { Promise.all([older.p, crimeLoad.p]).then(function () { resolveReady(ctl); }); });
      // The where-from view's files can arrive before the map is built: frame its bubbles once the page has settled.
      map.once("idle", function () { if (!cur.camera && cur.view === "from" && !edgeRegions()) moveCamera(0); });

      function fromCard(p) {
        var sm = fromSummary(), a = cur.filter.area, U = WFD.units, b = fromList.filter(function (x) { return x.g === p.g; })[0];
        if (!b || !sm.ready) return "";
        var name = a.hood ? esc(a.hood) : a.district ? "District " + a.district : "the drawn area";
        var verb = cur.ends === "from" ? "start" : cur.ends === "to" ? "end" : "start or end";
        var of = sm.thru ? (cur.ends === "both" ? "trip ends of the cars passing through " + name : "the cars passing through " + name) :
          sm.hood ? (cur.ends === "both" ? "trip ends of the cars on " + name + "'s streets" : "the cars on " + name + "'s streets") : "the cars crossing " + name + "'s edge";
        var reg = b.region ? U.regions[b.g - (U.groups.length - U.regions.length)] : null;
        var h = '<div class="pop"><b>' + (b.own ? "Inside " + name : esc(b.name)) + "</b>" + (reg ? '<br><span class="g">' + esc(reg.places.join(", ")) + "</span>" : "") +
          "";
        // The bubble and its bar already give the share and the count, so the card goes straight to how people
        // travel. Where there is nothing to say on that (a drawn area, or while the file loads) it gives the share.
        // A through car's trip isn't between here and the area, so the travel figures for that pair don't apply.
        var mh = sm.thru ? "" : modesHtml(fromModes(p.g), b.own, name);
        return h + (mh || "<br><b>" + b.t1 + "</b> of " + of + " " + verb + " here") + "</div>";
      }
      // The card's second half: how people make the trip between the unit and the area today, and what the typical
      // morning trip takes by car, transit and bike. Shares lead; the trip count is said once.
      function modesHtml(m, own, name) {
        if (!m) return "";
        var where = own ? "within " + name : cur.ends === "from" ? "from here to " + name : cur.ends === "to" ? "from " + name + " to here" : "between here and " + name;
        var h = '<div class="wfm"><span class="g">How people travel ' + where + "</span>";
        if (m.few) return h + '<br><span class="g">Too few trips in the model to split: about ' + n2(m.n) + " a weekday.</span></div>";
        h += '<div class="wfm-bar">' + m.share.map(function (x, i) { return x[1] ? '<i style="flex:' + x[1] + " 0 0;background:" + WF_MODES[i] + '"></i>' : ""; }).join("") + "</div>";
        // Whole percents: the model simulates one trip in two, so a decimal would claim more than it has.
        var whole = function (v) { var q = 100 * v / m.n; return !v ? "0%" : q < 0.5 ? "<1%" : Math.round(q) + "%"; };
        h += '<div class="wfm-key">' + m.share.map(function (x, i) { return x[1] ? '<span><i style="background:' + WF_MODES[i] + '"></i>' + x[0] + " <b>" + whole(x[1]) + "</b></span>" : ""; }).join("") + "</div>";
        h += '<span class="g">Of ' + n2(m.n) + " trips a weekday by all ways of travelling, a model estimate.</span>";
        var mins = function (v) { return Math.round(v) + " min"; }, miles = function (v) { return (v >= 10 ? Math.round(v) : v.toFixed(1)) + " mi"; }, rows = [];
        // The times rest on the car trips alone, so they need enough of those; and a mode most of these trips have
        // no path for says so, without a time for the few that do.
        var enough = m.share[0][1] >= WF_MODE_MIN;
        if (enough && m.car.min != null) rows.push(["Car", mins(m.car.min) + ", " + miles(m.car.mi)]);
        if (!enough) rows = [];
        else if (m.transit.min != null && m.transit.none < 50) rows.push(["Transit", mins(m.transit.min) + " if you walk to the stop" + (m.transit.drive != null ? ", " + mins(m.transit.drive) + " if you drive to it" : "") + (m.transit.none ? "; no stop within a walk for " + m.transit.none + "% of these trips" : "")]);
        else if (m.transit.none != null) rows.push(["Transit", "no stop within a walk for " + m.transit.none + "% of these trips"]);
        if (!enough) rows = [];
        else if (m.bike.min != null && m.bike.none < 50) rows.push(["Bike", mins(m.bike.min) + ", " + miles(m.bike.mi) + (m.bike.none ? "; no bike route under 75 miles for " + m.bike.none + "% of these trips" : "")]);
        else if (m.bike.none != null) rows.push(["Bike", "no bike route under 75 miles for " + m.bike.none + "% of these trips"]);
        if (rows.length) h += '<div class="wfm-t"><span class="g">For the trips people now drive, the typical trip door to door at the morning rush:</span>' + rows.map(function (r) { return "<div><b>" + r[0] + "</b> " + r[1] + "</div>"; }).join("") + "</div>";
        if (rows.length) h += eligHtml(m.elig);
        return h + "</div>";
      }
      // Bryan's eligibility line (2026-11-20): person trips by car that pass each test,
      // the count as the main figure, its share of trips by car smaller, and today's share of the tested mode on all
      // trips between the same places. Under WF_ELIG_MIN a count is "Fewer than 20", with no share. Method on About.
      function eligHtml(e) {
        if (!e || !e.of) return "";
        var line = function (t, test, mode, j, tail) {
          var today = t[0] + t[1] + t[2] + t[3], q = today ? 100 * t[j] / today : 0, few = t[0] < WF_ELIG_MIN;
          return "<div><b>" + test + ": " + (few ? "Fewer than " + WF_ELIG_MIN : n2(t[0])) + "</b>" +
            (few ? "" : '<small class="g">, ' + pct(t[0], e.of) + " of trips by car here." +
              (today >= WF_MODE_MIN ? " Already by " + mode + ": " + (q < 0.5 ? "<1" : Math.round(q)) + "%" + tail + "." : "") + "</small>") + "</div>";
        };
        return '<div class="wfm-t wfm-e"><span class="g">Trips by car a weekday that pass a simple test. Not a forecast.</span>' +
          line(e.transit, "Transit with a walk to the stop, at most 1.5 times the drive", "transit", 1, " of all trips between these places") +
          line(e.bike, "Bike ride of 3 miles or less", "bike", 2, "") + "</div>";
      }
      function throughCard(r, j) {
        var X = throughX(), p = TR.p[r], pct = Math.round(X.s[j] / 10);
        var h = '<div class="pop">' + (TR.names[p[8]] ? "<b>" + esc(TR.names[p[8]]) + "</b><br>" : "") + (p[10] ? "Main street" : "Residential street") + "<br>";
        var when = X.bin ? " " + esc(S.TIMES.filter(function (t) { return t[0] === X.bin; })[0][1].replace(/^[^,]*, /, "from ").toLowerCase()) : " a weekday";
        h += "<b>" + pct + "%</b> of car trips here are passing through, with neither end within " + nearPhrase() + ", of about " + n0(X.v[j]) + when + (X.v[j] < X.minCars ? ", too few to colour" : "") + ".";
        return h + '<br><span class="g">Every purpose\'s car trips in <a href="https://github.com/BayAreaMetro/modeling-website/wiki/IndividualTrip" target="_blank" rel="noopener">MTC\'s travel model</a> for 2023, sent down their fastest route on ' +
          '<a href="https://api.sfcta.org/api/" target="_blank" rel="noopener">SF-CHAMP</a>\'s network' +
          (X.l[j] ? ". A rough figure: small changes in travel time move trips on or off this block" : "") + ".</span></div>";
      }
      function stressCard(p, i) {
        var perMin = function (v) { return (Math.round(v / 6) / 10).toString(); };
        // A Slow Streets figure is a day count; its busiest hour is worked out from the day, so the card leads with the day.
        var slow = p[7] === 1 || (p[7] === 6 && p[18] === 1), sfDaily = p[7] === 5 && p[18] === 1;
        var est = p[7] === 3 || p[7] === 4, h = '<div class="pop">' + (TR.names[p[8]] ? "<b>" + esc(TR.names[p[8]]) + "</b><br>" : "") + (p[10] ? "Main street" : "Residential street") + "<br>";
        if (slow) h += "Measured: about " + n0(p[3]) + " cars a day. About " + n0(p[2]) + " at the busiest hour (" + perMin(p[2]) + " a minute), worked out from the day count";
        else h += (est ? "Estimated: about " : p[7] === 2 ? "Modelled: about " : "Measured: ") + n0(p[2]) + " cars an hour at the busiest hour (" + perMin(p[2]) + " a minute)" + (p[3] ? ", about " + n0(p[3]) + " a day" : "");
        if (est) h += ", range " + n0(p[5]) + " to " + n0(p[6]) + " an hour";
        var tel = function (i) { return '<a href="https://telraam.net/en/location/' + esc(p[i]) + '" target="_blank" rel="noopener">Telraam counter</a>'; };
        var span = function () { return "the median of " + esc(p[12]) + " Tuesday to Thursday rush hours, " + esc(p[13]) + " to " + esc(p[14]); };
        var SLOW = '<a href="https://www.sfmta.com/media/35298/download?inline" target="_blank" rel="noopener">SFMTA Slow Streets evaluation</a>, 2023, a day count';
        var g = { 0: '<a href="https://www.sfmta.com/TrafficCounts" target="_blank" rel="noopener">SFMTA traffic count</a>, ' + esc(p[4]) + (p[9] ? ", during the pandemic" : ""),
          1: SLOW,
          2: '<a href="https://api.sfcta.org/api/" target="_blank" rel="noopener">SF-CHAMP</a>, undated run of 2019 or earlier, scaled to the counts',
          3: "Carried along the street from a " + esc(p[4]) + " count, less every car the homes between could park",
          4: Math.round(TR.spill.central * 100) + "% of the parallel main street's traffic, a rough guess for the area",
          // A block with both counts uses the one hin-cut-through.py's COUNT_RULE picks (map.json traffic.rule); the
          // card gives the other beside it. Where SFMTA's side is the Slow Streets day count, the two are compared by the day.
          6: (slow ? SLOW : '<a href="https://www.sfmta.com/TrafficCounts" target="_blank" rel="noopener">SFMTA traffic count</a>, ' + esc(p[4]) + (p[9] ? ", during the pandemic" : "")) +
            ". A resident's " + tel(11) + " here reads " + (slow && p[17] ? "about " + n0(p[16]) + " a day and " : "") + n0(p[15]) + " an hour at the busiest hour, " + span(),
          5: tel(11) + " in a resident's window, " + span() +
            (sfDaily ? ". SFMTA's Slow Streets evaluation counted about " + n0(p[19]) + " a day here in 2023" : p[15] ? ". SFMTA counted about " + n0(p[15]) + " an hour here in " + esc(p[16]) : "") }[p[7]];
        // Caveats hin-cut-through.py's caveats() sets on the block (map.json traffic.cav).
        var CAV = { tel_main: function () { var ms = TR.telMainSfmta || [], m = ms[0];
            return (!ms.length ? "No Telraam counter on a main street has been checked against an SFMTA count yet"
              : ms.length === 1 ? "One Telraam counter on a main street has an SFMTA count to check it against: on " + esc(m[0]) + " it reads " + n0(m[1]) + " an hour where SFMTA counted " + n0(m[2]) + " in " + esc(m[3])
              : ms.length + " Telraam counters on main streets have an SFMTA count to check them against") + (TR.telMain && TR.telMain[0] ? ". On main streets they read a median " + Math.round(TR.telMain[0] * 100) + "% of the modelled figure on the next blocks" : ""); },
          tel_winter: function () { return "This counter only has days from November to February, so its evening rush may be counted in the dark"; },
          counts_disagree: function (c) { return "SFMTA's counts here disagree, from about " + n0(c[2]) + " to " + n0(c[3]) + " cars a day, so the map doesn't use them"; } };
        var cav = (TR.cav || []).filter(function (c) { return c[0] === i && CAV[c[1]]; }).map(function (c) { return CAV[c[1]](c); });
        return h + '<br><span class="g">' + g + (cav.length ? ". " + cav.join(". ") : "") + "</span></div>";
      }
    }
    return ctl;
  }

  root.SafetyMap = { create: create, scaleOpacity: scaleOpacity, COLOURS: COLOURS, RT: RT, RT_LAB: RT_LAB, when: when };
})(this);
