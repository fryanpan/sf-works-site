// Crash cards for the Street Safety map (src/safety-map/map.js) and scripts/hin-people-map.html: a carousel of the crashes at one map spot, each slide a plain account,
// a diagram of every party with its direction of travel, and a details list. The data comes from
// tools/street-safety/hin_crash_cards.py (D.crashes, keyed by SFPD case number); this file is inlined into the site's pages by
// src/safety-map/index.mjs and into the scratch map by tools/street-safety/hin-people-map.py at __CRASH_JS__. Web Awesome 3.14.0 (wa-carousel, wa-button) draws the controls.
var CrashCards = (function () {
  var SEV = "#efb118", KIL = "#4269d0", VIS = "#7fbfae", PAIN = "#d8cdf0", DARK = "#1b1f24", GREY = "#8b929b", ARROW = "#353b44", ROAD = "#e4e7eb", KERB = "#b4bbc4";
  // Glyphs on a 24-unit box, in the map sprites' form: strokes, filled heads [x, y, r], rings [x, y, r], filled shapes.
  var GLYPH = {
    walk: [[[12, 6.5, 11.6, 13.5], [11.6, 13.5, 8.4, 21], [11.6, 13.5, 14.8, 21], [12, 8.2, 8.6, 11.8], [12, 8.2, 15.4, 11.4]], [[12, 3.6, 2.4]], [], 2.6],
    bike: [[[5.5, 17, 10.5, 17, 15, 11, 18.5, 17], [10.5, 17, 9.5, 11, 15, 11], [10.5, 17, 12, 19.2], [9.6, 5.8, 9.5, 11], [9.6, 7.2, 14.6, 10.4]], [[9.8, 3.4, 2.1]], [[5.5, 17, 3.9], [18.5, 17, 3.9]], 1.5],
    moto: [[[10.5, 6.6, 12.5, 10.5], [11, 7.6, 17, 9.6]], [[10.2, 4.6, 2.7], [5.5, 17.2, 1.2], [18.5, 17.2, 1.2]], [[5.5, 17.2, 3.4], [18.5, 17.2, 3.4]], 2.8,
      [[3.5, 13.5, 8.5, 10.6, 17.5, 10.6, 20.5, 13.5, 16.5, 15.6, 8.5, 15.6], [9.5, 15, 14.5, 15, 14.5, 19, 9.5, 19]]],
    car: [[], [[7, 17.4, 2.4], [17, 17.4, 2.4]], [], 1.4, [[2, 16, 2, 12, 6, 11, 9, 6.5, 16, 6.5, 19.5, 11, 22, 12, 22, 16]]],
    truck: [[], [[6, 18, 2.3], [18, 18, 2.3]], [], 1.4, [[1.5, 16.5, 1.5, 5, 14, 5, 14, 16.5], [14, 16.5, 14, 8.5, 19, 8.5, 22.5, 12.5, 22.5, 16.5]]],
    bus: [[], [[6, 18.4, 2.2], [18, 18.4, 2.2]], [], 1.4, [[1.5, 17, 1.5, 5.5, 22.5, 5.5, 22.5, 17]]],
    scooter: [[[12, 6.4, 12, 14.5], [12, 14.5, 10.5, 19], [12, 14.5, 13.5, 19], [6, 19.8, 18, 19.8], [18, 19.8, 17, 9, 14.5, 9]], [[12, 3.6, 2.3], [7, 21.4, 1.3], [18, 21.4, 1.3]], [], 2.2]
  };
  var uid = 0;
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function glyph(kind, col, cx, cy, s) {
    var G = GLYPH[kind] || GLYPH.car, out = '<g transform="translate(' + (cx - 12 * s).toFixed(1) + "," + (cy - 12 * s).toFixed(1) + ") scale(" + s + ')" stroke-linecap="round" stroke-linejoin="round">';
    [[DARK, G[3] + 2.2, 1.1], [col, G[3], 0]].forEach(function (pass) {
      G[0].forEach(function (q) { var d = "M" + q[0] + " " + q[1]; for (var i = 2; i < q.length; i += 2) d += "L" + q[i] + " " + q[i + 1]; out += '<path d="' + d + '" fill="none" stroke="' + pass[0] + '" stroke-width="' + pass[1] + '"/>'; });
      G[1].forEach(function (h) { out += '<circle cx="' + h[0] + '" cy="' + h[1] + '" r="' + (h[2] + pass[2]) + '" fill="' + pass[0] + '"/>'; });
      G[2].forEach(function (h) { out += '<circle cx="' + h[0] + '" cy="' + h[1] + '" r="' + h[2] + '" fill="none" stroke="' + pass[0] + '" stroke-width="' + pass[1] + '"/>'; });
      (G[4] || []).forEach(function (f) { var d = "M" + f.slice(0, 2).join(" "); for (var i = 2; i < f.length; i += 2) d += "L" + f[i] + " " + f[i + 1]; out += '<path d="' + d + 'Z" fill="' + pass[0] + '"' + (pass[2] ? ' stroke="' + DARK + '" stroke-width="2.2"' : "") + "/>"; });
    });
    return out + "</g>";
  }
  // The box a glyph drawn at scale s actually inks, dark outline included, as [x0, y0, x1, y1] px from its centre:
  // a walker is under 10 px wide and a car under 13 px tall, so a fixed square would park a number well off either.
  var EXT = {};
  function extent(kind, s) {
    var key = kind + s;
    if (EXT[key]) return EXT[key];
    var G = GLYPH[kind] || GLYPH.car, w = (G[3] + 2.2) / 2, b = [1e9, 1e9, -1e9, -1e9];
    function e(x, y, r) { b[0] = Math.min(b[0], x - r); b[1] = Math.min(b[1], y - r); b[2] = Math.max(b[2], x + r); b[3] = Math.max(b[3], y + r); }
    G[0].forEach(function (q) { for (var i = 0; i < q.length; i += 2) e(q[i], q[i + 1], w); });
    G[1].forEach(function (h) { e(h[0], h[1], h[2] + 1.1); });
    G[2].forEach(function (h) { e(h[0], h[1], h[2] + w); });
    (G[4] || []).forEach(function (f) { for (var i = 0; i < f.length; i += 2) e(f[i], f[i + 1], 1.1); });
    return (EXT[key] = b.map(function (v) { return (v - 12) * s; }));
  }
  function boxDist(p, b) { return Math.hypot(Math.max(b[0] - p[0], 0, p[0] - b[2]), Math.max(b[1] - p[1], 0, p[1] - b[3])); }
  function overlap(a, b) { return Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1])); }

  // Coordinates are drawn for a party travelling north (coming up from the bottom, in the right-hand lane), then
  // rotated to its recorded direction. y grows downward.
  var ANG = { N: 0, E: 90, S: 180, W: 270 };
  function rot(p, d) { var a = ANG[d] * Math.PI / 180, c = Math.round(Math.cos(a)), s = Math.round(Math.sin(a)); return [p[0] * c - p[1] * s, p[0] * s + p[1] * c]; }

  // Feet from the crash point to the drawing: 150 ft from the point to the top edge (hin_crash_cards.PX_FT).
  var PX_FT = 95 / 150;
  function unit(b) { var r = b * Math.PI / 180; return [Math.sin(r), -Math.cos(r)]; }
  function right(t) { return [-t[1], t[0]]; }   // the right-hand side of a heading, y down
  function add(p) { var x = p[0], y = p[1]; for (var i = 1; i < arguments.length; i += 2) { x += arguments[i][0] * arguments[i + 1]; y += arguments[i][1] * arguments[i + 1]; } return [x, y]; }
  // Liang-Barsky clip of segment a-b to the box [x0, x1] x [y0, y1]; null when outside.
  function clip(a, b, x0, y0, x1, y1) {
    var t0 = 0, t1 = 1, dx = b[0] - a[0], dy = b[1] - a[1], pq = [[-dx, a[0] - x0], [dx, x1 - a[0]], [-dy, a[1] - y0], [dy, y1 - a[1]]];
    for (var i = 0; i < 4; i++) {
      var p = pq[i][0], q = pq[i][1];
      if (p === 0) { if (q < 0) return null; continue; }
      var t = q / p;
      if (p < 0) { if (t > t0) t0 = t; } else if (t < t1) t1 = t;
      if (t0 > t1) return null;
    }
    return [[a[0] + t0 * dx, a[1] + t0 * dy], [a[0] + t1 * dx, a[1] + t1 * dy]];
  }

  // The point s px along a polyline from its start, and the unit tangent there; before the start and past the end the
  // line runs straight on.
  function at(p, s) {
    var n = p.length, i, d, u;
    for (i = 0; i + 1 < n; i++) {
      d = Math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]);
      u = [(p[i + 1][0] - p[i][0]) / d, (p[i + 1][1] - p[i][1]) / d];
      if (s <= d || i + 2 === n) return [add(p[i], u, s), u];
      s -= d;
    }
  }
  function segDist(p, a, b) {
    var dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy, t = L ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L)) : 0;
    return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
  }
  // Points along a quadratic or cubic Bezier, ends included.
  function curve(c) {
    var out = [], n = c.length - 1;
    for (var i = 0; i <= 8; i++) {
      var t = i / 8, u = 1 - t, w = n === 2 ? [u * u, 2 * u * t, t * t] : [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
      out.push([c.reduce(function (a, p, j) { return a + w[j] * p[0]; }, 0), c.reduce(function (a, p, j) { return a + w[j] * p[1]; }, 0)]);
    }
    return out;
  }
  // A polyline with a point at least every 4 px.
  function dense(pts) {
    var out = [pts[0]];
    for (var i = 1; i < pts.length; i++) {
      var a = pts[i - 1], b = pts[i], n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 4));
      for (var j = 1; j <= n; j++) out.push([a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n]);
    }
    return out;
  }

  function diagram(g, probe) {
    var W = 260, H = 214, cx = 130, cy = 98, R = g.geo ? 13 : 17, id = "cc" + (++uid), o = [], notes = [], best = {}, labAt = -1, roads = null;
    var boxes = [[W - 22 - cx, 2 - cy, W - 2 - cx, 33 - cy]];   // what a street label must not cover, px from the centre: the north arrow, then each glyph and tag
    function P(p) { return (cx + p[0]).toFixed(1) + " " + (cy + p[1]).toFixed(1); }
    function line(pts) {   // a polyline as path points, without the points on a straight run between two others
      var keep = pts.filter(function (p, i) {
        if (!i || i === pts.length - 1) return true;
        var a = pts[i - 1], b = pts[i + 1];
        return Math.abs((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) > 0.02 * Math.hypot(b[0] - a[0], b[1] - a[1]);
      });
      return keep.map(P).join("L");
    }
    function F(x, y) { return [x * PX_FT, y * PX_FT]; }   // feet from the point to px from the centre
    o.push('<svg viewBox="0 0 ' + W + " " + H + '" class="cc-svg" role="img" aria-label="Diagram of the streets at the crash, the parties and their directions of travel">');
    o.push('<defs><marker id="' + id + '" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="' + ARROW + '"/></marker>' +
      '<clipPath id="' + id + 'c"><rect x="0" y="0" width="' + W + '" height="' + (H - 18) + '"/></clipPath></defs>');
    if (g.geo) {
      // The city's centrelines within the drawing, north up, as wide strokes: kerbs first, then the roadway over them,
      // so every junction is drawn as one surface.
      roads = g.geo.r.map(function (r) { return [r[0], r[1].map(function (p) { return F(p[0], p[1]); })]; });
      var d = roads.map(function (r) { return "M" + r[1].map(P).join("L"); }).join("");
      o.push('<g clip-path="url(#' + id + 'c)" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="' + d + '" stroke="' + KERB + '" stroke-width="' + (2 * R + 2) + '"/>' +
        '<path d="' + d + '" stroke="' + ROAD + '" stroke-width="' + 2 * R + '"/></g>');
      // One label per street, on one of its visible pieces, near the piece's outer end and along it (streetLabels).
      roads.forEach(function (r) {
        var runs = [], pts = [];   // the road's pieces inside the frame; a road that leaves and re-enters makes two
        for (var i = 0; i + 1 < r[1].length; i++) {
          var c = clip(r[1][i], r[1][i + 1], 4 - cx, 4 - cy, W - 4 - cx, H - 22 - cy);
          if (!c) { if (pts.length) runs.push(pts); pts = []; continue; }
          if (pts.length && Math.hypot(pts[pts.length - 1][0] - c[0][0], pts[pts.length - 1][1] - c[0][1]) > 0.5) { runs.push(pts); pts = []; }
          if (!pts.length) pts.push(c[0]);
          if (Math.hypot(c[1][0] - pts[pts.length - 1][0], c[1][1] - pts[pts.length - 1][1]) > 0.01) pts.push(c[1]);
        }
        if (pts.length) runs.push(pts);
        runs.forEach(function (run) {
          var len = 0;
          for (var j = 0; j + 1 < run.length; j++) len += Math.hypot(run[j + 1][0] - run[j][0], run[j + 1][1] - run[j][1]);
          if (r[0] && run.length > 1 && len > 30) (best[r[0]] = best[r[0]] || []).push([run, len]);
        });
      });
      labAt = o.length;
    } else {
      var horiz = g.x || g.ax === "h", vert = g.x || g.ax === "v";
      if (horiz) o.push('<rect x="0" y="' + (cy - R) + '" width="' + W + '" height="' + 2 * R + '" fill="' + ROAD + '"/><path d="M0 ' + (cy - R) + "H" + W + "M0 " + (cy + R) + "H" + W + '" stroke="' + KERB + '"/>');
      if (vert) o.push('<rect x="' + (cx - R) + '" y="0" width="' + 2 * R + '" height="' + (H - 18) + '" fill="' + ROAD + '"/><path d="M' + (cx - R) + " 0V" + (H - 18) + "M" + (cx + R) + " 0V" + (H - 18) + '" stroke="' + KERB + '"/>');
      if (g.x) o.push('<rect x="' + (cx - R + 0.5) + '" y="' + (cy - R + 0.5) + '" width="' + (2 * R - 1) + '" height="' + (2 * R - 1) + '" fill="' + ROAD + '"/>');
      if (g.lv) o.push('<text x="' + (cx + R + 4) + '" y="12" class="cc-road">' + esc(g.lv) + "</text>");
      if (g.lh) o.push('<text x="4" y="' + (cy - R - 4) + '" class="cc-road">' + esc(g.lh) + "</text>");
      notes.push("streets not drawn here");
    }
    o.push('<circle cx="' + cx + '" cy="' + cy + '" r="7" fill="none" stroke="' + ARROW + '" stroke-width="1.4" stroke-dasharray="2.5 2"/>');

    // Where each party goes: vehicles first, on their legs; then walkers, clear of the vehicles; then the number tags,
    // clear of every glyph. A party on a leg follows that leg's centreline (its track), a lane's width to the right of
    // it on a two-way street and on it on a one-way street or one half of a divided one, so the glyph and the arrow
    // stay on the drawn road and run along it. Same-leg parties queue back from the ring: the party not marked at
    // fault nearest it, so in a rear-end crash the struck vehicle sits ahead of the one that hit it.
    var G0 = 48, GAP = 23, DASH = ' stroke-dasharray="4 3"', TAG = { l: "left turn", r: "right turn", u: "U-turn", b: "backing" };
    var starred = false, loose = [], items = [], counts = {}, seen = {}, tracks = {};
    var order = g.p.slice().sort(function (a, b) { return a.f - b.f || a.n - b.n; });
    function colour(q) { return q.h >= 3 ? KIL : q.h === 2 ? SEV : q.hl === "v" ? VIS : q.hl === "p" ? PAIN : GREY; }   // the map's level colours
    function tid(ref) { return ref.length > 3 ? ref[3] : ref.join(","); }
    function trk(ref) {
      var k = tid(ref), t = g.geo.k && g.geo.k[ref[3]];
      if (!tracks[k]) {
        var O = F(ref[0], ref[1]), far = add(O, unit(ref[2]), 200), raw = t ? t[1].map(function (c) { return F(c[0], c[1]); }) : [O, far];
        var p = [];   // without points under 4 px on from the last: a stub that short points anywhere once its ends are rounded
        raw.forEach(function (c, i) { if (!i || Math.hypot(c[0] - p[p.length - 1][0], c[1] - p[p.length - 1][1]) > 4) p.push(c); });
        if (p.length < 2) p = [O, far];
        for (var len = 0, i = 1; i < p.length; i++) len += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
        tracks[k] = { p: p, one: t ? t[0] : 0, id: k, len: len };
      }
      return tracks[k];
    }
    var noteTop = g.p.some(function (q) { return q.fb; }) ? 12 : 0;   // the asterisk note's line across the top, kept clear of glyphs
    function inFrame(p, m) { return p[0] >= m - cx && p[0] <= W - m - cx && p[1] >= m + noteTop - cy && p[1] <= H - 18 - m - cy; }
    function onRoad(p, tol) { return !roads || roads.some(function (r) { return r[1].some(function (a, i) { return i && segDist(p, r[1][i - 1], a) <= R + tol; }); }); }
    // lane: the point s px out along a track, L px to the right of travel (sg -1 heading in to the point, 1 heading out).
    function lane(tr, s, sg, L) { var a = at(tr.p, s); return add(a[0], right([a[1][0] * sg, a[1][1] * sg]), L); }
    function run(tr, s0, s1, sg, L) {
      var out = [], n = Math.max(1, Math.ceil(Math.abs(s1 - s0) / 4));
      for (var i = 0; i <= n; i++) out.push(lane(tr, s0 + (s1 - s0) * i / n, sg, L));
      return out;
    }
    // How far out a glyph still sits inside the frame and on its street (a street that ends at a T ends the track).
    function reach(tr, sg, L) { var s = 20; while (s < 140 && s + 2 <= tr.len - 4 && inFrame(lane(tr, s + 2, sg, L), 11)) s += 2; return s; }
    // A queue's k-th place, base px out and GAP apart, closed up when the leg leaves the frame before the queue ends.
    function slot(key, k, tr, sg, L, base, room) {
      var far = Math.max(Math.min(base, 20), reach(tr, sg, L) - room), n = counts[key], step = n > 1 ? Math.max(12, Math.min(GAP, (far - base) / (n - 1))) : 0;
      return Math.min(base + step * (k - 1), far);
    }
    function keyOf(q) { return !q.d ? "" : q.v === "walk" ? "w" + q.d : !g.geo ? "f" + q.d : q.t ? "i" + tid(q.t.a) : q.a ? "i" + tid(q.a) : q.e ? "o" + tid(q.e) : "f" + q.d; }
    order.forEach(function (q) { var key = keyOf(q); counts[key] = (counts[key] || 0) + 1; });
    order.forEach(function (q) {
      var col = colour(q), key = keyOf(q);
      if (!q.d) { loose.push({ q: q, col: col }); return; }
      if (q.v === "walk") return;
      var k = seen[key] = (seen[key] || 0) + 1, it = { q: q, col: col, k: k, head: true, dash: "" }, L, tr, s;
      if (q.t && g.geo) {       // a turn on the real legs: in along one, a curve where the two lanes cross, out along the other
        var A = trk(q.t.a), B = trk(q.t.b), same = A.id === B.id, La = A.one && !same ? 0 : 6, Lb = B.one && !same ? 0 : 6;
        s = slot(key, k, A, -1, La, G0, 0);
        it.gp = lane(A, s, -1, La); it.side = right([-at(A.p, s)[1][0], -at(A.p, s)[1][1]]);
        var ua = at(A.p, 0)[1], ub = at(B.p, 0)[1], A0 = lane(A, 0, -1, La), B0 = lane(B, 0, 1, Lb), den = ua[0] * ub[1] - ua[1] * ub[0], tail = s - 12;
        var al = Math.abs(den) > 0.3 ? ((B0[0] - A0[0]) * ub[1] - (B0[1] - A0[1]) * ub[0]) / den : null, be = al === null ? null : ((B0[0] - A0[0]) * ua[1] - (B0[1] - A0[1]) * ua[0]) / den;
        if (al !== null && al > -45 && al < 30 && be > -45 && be < 30) {   // the lanes cross at X, al px out along A and be along B
          var X = add(A0, ua, al), sa = Math.min(Math.max(al + 8, 16), tail - 2), sb = Math.max(be + 8, 16), inn = run(A, tail, sa, -1, La), out = run(B, sb, Math.max(sb + 14, 40), 1, Lb);
          it.d = "M" + line(inn) + "Q" + P(X) + " " + P(out[0]) + "L" + line(out);
          it.pts = inn.concat(curve([inn[inn.length - 1], X, out[0]]), out);
        } else {   // lanes that never cross (a U-turn): round from one to the other past the point
          var p1 = lane(A, 16, -1, La), p2 = lane(B, 16, 1, Lb), c1 = add(p1, ua, -14), c2 = add(p2, ub, -14), in2 = run(A, Math.max(tail, 18), 16, -1, La), out2 = run(B, 16, 40, 1, Lb);
          it.d = "M" + line(in2) + "C" + P(c1) + " " + P(c2) + " " + P(p2) + "L" + line(out2);
          it.pts = in2.concat(curve([p1, c1, c2, p2]), out2);
        }
        if (q.t.u) it.dash = DASH;
      } else if ((q.a || q.e) && g.geo) {   // straight, on the leg it comes in on (or, with none, the leg it leaves on)
        var sg = q.a ? -1 : 1;
        tr = trk(q.a || q.e); L = q.pk ? (tr.one ? 8 : 10) : tr.one ? 0 : 6;
        s = slot(key, k, tr, sg, L, q.a ? G0 : 18, q.a ? 0 : 22);   // a party leaving keeps room ahead for its arrow
        it.gp = lane(tr, s, sg, L); it.side = right([at(tr.p, s)[1][0] * sg, at(tr.p, s)[1][1] * sg]);
        if (q.a) it.pts = q.m === "x" ? run(tr, s - 12, s - 20, -1, L) : run(tr, s - 12, -12, -1, L);
        else it.pts = q.m === "x" ? run(tr, s + 12, s + 20, 1, L) : run(tr, s + 12, Math.max(s + 20, Math.min(s + 52, reach(tr, 1, L) + 8)), 1, L);
        if (q.m === "x") it.head = false; else if (q.m === "b") it.dash = DASH;
      } else {   // no leg fits: the compass placement, kept in the drawing only where it lands on a road
        // On the generic cross a long queue (a freeway pile-up) closes up, as a leg's does, and stops at the frame's edge;
        // with streets drawn, a party past the edge goes below the drawing (the check after this).
        var far = (q.d === "E" || q.d === "W" ? cx : cy) - 14, n = counts[key];
        var sh = g.geo ? GAP * (k - 1) : Math.min((n > 1 ? Math.max(12, Math.min(GAP, (far - 52) / (n - 1))) : 0) * (k - 1), Math.max(0, far - 52));
        L = q.pk ? (g.geo ? 10 : 13) : (g.geo ? 6 : 8);
        it.gp = rot([L, 52 + sh], q.d);
        it.pts = [rot([L, 40 + sh], q.d), rot([L, q.m === "x" ? 32 + sh : -12], q.d)];
        if (q.m === "x") it.head = false; else if (q.m === "b") it.dash = DASH;
        if (g.geo && !(inFrame(it.gp, 10) && onRoad(it.gp, 0) && dense(it.pts).every(function (p) { return onRoad(p, 0); }))) { loose.push({ q: q, col: col, star: 1 }); starred = true; return; }
      }
      if (q.fb) starred = true;
      if (!it.d) it.d = "M" + line(it.pts);
      items.push(it);
    });
    order.forEach(function (q) {   // walkers, beside the ring: the record names no crosswalk
      if (!q.d || q.v !== "walk") return;
      // On the side of the street they walk along that the point is on, so "5 ft east of Laguna St" draws the walker
      // east of Laguna; with no such street, or the point on its centreline, to the walker's left. A walker who would
      // stand on a vehicle starts further back.
      var key = keyOf(q), k = seen[key] = (seen[key] || 0) + 1, far = (q.d === "E" || q.d === "W" ? cx : cy) - 14;   // the furthest back a walker still stands inside the frame
      var sh = (counts[key] > 1 ? Math.min(GAP, (far - 42) / (counts[key] - 1)) : 0) * (k - 1), wx = -26, back = 0, gp = null;
      if (g.geo && g.geo.l) {
        var rt = rot([1, 0], q.d), off = 0, nOff = 0;
        g.geo.l.forEach(function (lg) {
          if (Math.abs(((lg[2] - ANG[q.d]) % 180 + 180) % 180 - 90) < 60) return;   // runs across the walker's path
          off += lg[0] * rt[0] + lg[1] * rt[1]; nOff++;
        });
        if (nOff && Math.abs(off / nOff) > 1) wx = off > 0 ? -26 : 26;
      }
      for (var i = 0; i < 3 && !gp; i++) {
        var c = rot([wx, Math.min(42 + sh + 14 * i, far)], q.d);
        if (items.every(function (o) { return Math.abs(o.gp[0] - c[0]) > 18 || Math.abs(o.gp[1] - c[1]) > 18; })) { gp = c; back = Math.min(42 + sh + 14 * i, far) - 42 - sh; }
      }
      var pts = [rot([wx, 30 + sh + back], q.d), rot([wx, -10], q.d)];
      items.push({ q: q, col: colour(q), k: k, walk: 1, head: true, dash: "", gp: gp || rot([wx, 42 + sh], q.d), pts: pts, d: "M" + line(pts) });
    });
    items.forEach(function (it) {
      o.push('<path d="' + it.d + '" fill="none" stroke="' + ARROW + '" stroke-width="' + (it.head ? 2 : 3.4) + '"' + it.dash + (it.head ? ' marker-end="url(#' + id + ')"' : "") + "/>");
    });
    var glyphs = items.map(function (it) { return [it.gp[0] - 10, it.gp[1] - 10, it.gp[0] + 10, it.gp[1] + 10]; }), tags = [];
    items.forEach(function (it) { o.push(glyph(it.q.v, it.col, cx + it.gp[0], cy + it.gp[1], 0.78)); });
    // The number tags, each touching its own glyph so it reads as that party's. Candidate spots ring the glyph's inked
    // box 1.5 px clear of it: its flanks first (on a leg, either side of the lane, alternating down a queue), then every
    // other direction nearest first. The first spot that covers no other glyph, tag, arrow, the north arrow or the
    // asterisk note, and sits nearer its own glyph than any other, wins; then the same without the arrows; then a spot
    // 7 or 14 px out with a short leader line to the glyph; then, of the spots still nearer their own glyph, the one
    // covering least.
    var inked = items.map(function (it) { var e = extent(it.q.v, 0.78); return [it.gp[0] + e[0], it.gp[1] + e[1], it.gp[0] + e[2], it.gp[1] + e[3]]; });
    var fixed = [[W - 22 - cx, 2 - cy, W - 2 - cx, 33 - cy]].concat(starred ? [[2 - cx, 1 - cy, 180 - cx, 14 - cy]] : []);
    var marks = [];
    items.forEach(function (it) { dense(it.pts).forEach(function (p) { marks.push([p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5]); }); });
    var DIRS = [];
    for (var di = 0; di < 16; di++) DIRS.push([Math.cos(di * Math.PI / 8), Math.sin(di * Math.PI / 8)]);
    items.forEach(function (it, i) {
      var q = it.q, tag = q.n + (q.fb ? "*" : "") + (TAG[q.m] && q.v !== "walk" ? " " + TAG[q.m] : ""), tw = tag.length * 5.2, nw = String(q.n).length * 5.2 + (q.fb ? 5.2 : 0), TH = 7, GAPT = 1.5;
      var gb = inked[i], gc = [(gb[0] + gb[2]) / 2, (gb[1] + gb[3]) / 2], hw = (gb[2] - gb[0]) / 2, hh = (gb[3] - gb[1]) / 2;
      var sgn = it.k % 2 ? 1 : -1, flank = it.side ? [[it.side[0] * sgn, it.side[1] * sgn], [-it.side[0] * sgn, -it.side[1] * sgn]] : [[1, 0], [-1, 0]];
      function spot(u, out) {   // the tag box touching the glyph's box in direction u, pushed out a further px
        var t = Infinity;
        if (Math.abs(u[0]) > 1e-6) t = Math.min(t, (hw + tw / 2 + GAPT + out) / Math.abs(u[0]));
        if (Math.abs(u[1]) > 1e-6) t = Math.min(t, (hh + TH / 2 + GAPT + out) / Math.abs(u[1]));
        var c = add(gc, u, t), b = [c[0] - tw / 2, c[1] - TH / 2, c[0] + tw / 2, c[1] + TH / 2];
        var nb = [b[0], b[1], b[0] + nw, b[3]], own = boxDist(it.gp, nb), other = Infinity;   // nearness by the number, not a "left turn" after it
        items.forEach(function (o2, j) { if (j !== i) other = Math.min(other, boxDist(o2.gp, nb)); });
        var cover = 0, arrows = 0;
        inked.forEach(function (x, j) { if (j !== i) cover += overlap(b, x); });
        tags.concat(fixed).forEach(function (x) { cover += 2 * overlap(b, x); });
        var fr = [b[0] + cx - 1, b[1] + cy - 1, W - 1 - b[2] - cx, H - 19 - b[3] - cy];
        fr.forEach(function (v) { if (v < 0) cover += -v * 20; });
        marks.forEach(function (x) { if (overlap(b, x) > 0) arrows++; });
        return { b: b, nb: nb, u: u, out: out, mine: other > own + 3, near: other > own, cover: cover, arrows: arrows, d: t };
      }
      var ring = DIRS.filter(function (u) { return flank.every(function (f) { return f[0] * u[0] + f[1] * u[1] < 0.98; }); });
      var first = flank.concat(ring.map(function (u) { return [u, spot(u, 0).d]; }).sort(function (a, b) { return a[1] - b[1]; }).map(function (x) { return x[0]; }));
      var c0 = first.map(function (u) { return spot(u, 0); }), c1 = [7, 14].reduce(function (a, out) { return a.concat(first.map(function (u) { return spot(u, out); })); }, []);
      var pick = c0.filter(function (c) { return c.mine && !c.cover && !c.arrows; })[0] || c0.filter(function (c) { return c.mine && !c.cover; })[0] ||
        c1.filter(function (c) { return c.mine && !c.cover; })[0];
      if (!pick) {
        var all = c0.concat(c1), pool = all.filter(function (c) { return c.near; });
        pick = (pool.length ? pool : all).reduce(function (a, c) { return c.cover < a.cover - 1e-9 ? c : a; });
      }
      tags.push(pick.b);
      if (pick.out) {   // a leader from the tag's nearest edge to the glyph's
        var tb = pick.b, pc = [Math.max(tb[0], Math.min(gc[0], tb[2])), Math.max(tb[1], Math.min(gc[1], tb[3]))], v = [gc[0] - pc[0], gc[1] - pc[1]], vl = Math.hypot(v[0], v[1]) || 1;
        var s = Infinity;
        if (Math.abs(v[0]) > 1e-6) s = Math.min(s, (Math.abs(v[0]) - hw) / Math.abs(v[0]));
        if (Math.abs(v[1]) > 1e-6) s = Math.min(s, (Math.abs(v[1]) - hh) / Math.abs(v[1]));
        var a0 = add(pc, [v[0] / vl, v[1] / vl], 1), a1 = [pc[0] + v[0] * Math.max(0, s), pc[1] + v[1] * Math.max(0, s)];
        o.push('<path d="M' + P(a0) + "L" + P(a1) + '" stroke="' + ARROW + '" stroke-width="0.8" fill="none"/>');
      }
      // Anchored on the side facing the glyph, so a tag narrower than its estimate still ends 1.5 px from it.
      var an = pick.u[0] > 0.3 ? "start" : pick.u[0] < -0.3 ? "end" : "middle", tx = an === "start" ? pick.b[0] : an === "end" ? pick.b[2] : (pick.b[0] + pick.b[2]) / 2;
      o.push('<text x="' + (cx + tx).toFixed(1) + '" y="' + (cy + pick.b[3]).toFixed(1) + '" text-anchor="' + an + '" class="cc-num" stroke="#fff" stroke-width="2.5" paint-order="stroke">' + tag + "</text>");
      it.tag = pick.nb;
    });
    boxes = boxes.concat(glyphs, tags);
    items.forEach(function (it) { dense(it.pts).forEach(function (p) { boxes.push([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3]); }); });
    // Below the drawing: parties with no recorded direction, and those whose recorded direction or street fits no leg
    // and whose compass placement would land off the road (starred, with the recorded direction as a small arrow).
    // Each number touches its icon's right edge, level with it, and the next icon starts a clear gap after the number
    // (and the arrow, for a starred party), so a number never sits nearer the next icon than its own.
    var lx = 6;
    loose.sort(function (a, b) { return (b.star || 0) - (a.star || 0); }).forEach(function (lp) {
      var e = extent(lp.q.v, 0.62), gx = lx - e[0], lab = lp.q.n + (lp.star ? "*" : ""), tx = gx + e[2] + 1.5, end = tx + String(lab).length * 5.2;
      o.push(glyph(lp.q.v, lp.col, gx, H - 9, 0.62));
      o.push('<text x="' + tx.toFixed(1) + '" y="' + (H - 9 + (e[1] + e[3]) / 2 + 3.25).toFixed(1) + '" class="cc-num">' + lab + "</text>");
      if (lp.star) {
        var c0 = [end + 7 - cx, H - 10 - cy];
        if (lp.q.m !== "x") o.push('<path d="M' + P(add(c0, rot([0, 1], lp.q.d), 5)) + "L" + P(add(c0, rot([0, -1], lp.q.d), 4)) + '" fill="none" stroke="' + ARROW + '" stroke-width="1.6" marker-end="url(#' + id + ')"/>');
        end += 13;
      }
      lx = end + 9;
    });
    if (probe) {
      probe.R = R; probe.roads = roads || null; probe.frame = [-cx, -cy, W - cx, H - 18 - cy];
      probe.items = items.map(function (it) { return { n: it.q.n, kind: it.walk ? "walk" : !g.geo ? "cross" : it.q.t ? "t" : it.q.a ? "a" : it.q.e ? "e" : "fb", m: it.q.m, gp: it.gp, pts: it.pts, tag: it.tag }; });
      probe.below = loose.map(function (lp) { return { n: lp.q.n, star: !!lp.star }; });
    }
    if (starred) boxes.push([2 - cx, 1 - cy, 180 - cx, 14 - cy]);
    if (labAt >= 0) o.splice.apply(o, [labAt, 0].concat(streetLabels()));
    if (loose.some(function (lp) { return !lp.star; })) notes.unshift("no direction recorded");
    if (starred) o.push('<text x="4" y="11" class="cc-note" stroke="#fff" stroke-width="2.5" paint-order="stroke">* recorded direction fits no street here</text>');
    if (notes.length) o.push('<text x="' + lx + '" y="' + (H - 6) + '" class="cc-note">' + esc(notes.join("; ")) + "</text>");
    // North arrow: the drawing is north up, like the map.
    o.push('<g transform="translate(' + (W - 12) + ',6)"><rect x="-9" y="-3" width="18" height="29" rx="3" fill="#fff" fill-opacity="0.85"/>' +
      '<path d="M0 0L5 11L0 8.5L-5 11Z" fill="' + ARROW + '"/><text x="0" y="23" text-anchor="middle" class="cc-num">N</text></g>');
    o.push("</svg>");
    return o.join("");
    // One label per street, beside the road and along it, on its longest visible piece that has a clear spot. It starts near the piece's outer
    // end on the right of the outward direction (the side a party leaving would use; parties coming in are drawn on the
    // other) and walks inward, trying both sides, until it sits inside the frame clear of every glyph, tag and the north
    // arrow. With no clear spot it takes the first one inside the frame that doesn't cover another street's label, and with none it is left off.
    function along(c, dir, tw) {   // points every 4 px or less along a name's line
      var out = [], n = Math.ceil(tw / 4);
      for (var i = 0; i <= n; i++) out.push(add(c, dir, tw * (i / n - 0.5)));
      return out;
    }
    function streetLabels() {
      var out = [], labs = starred ? [boxes[boxes.length - 1]] : [];   // the asterisk note, when there is one, is never covered
      Object.keys(best).sort().forEach(function (name) {
        var tw = name.length * 4.9, first = null, hit = null;
        best[name].sort(function (a, b) { return b[1] - a[1]; }).forEach(function (piece) {   // the street's visible pieces, longest first
        var pts = piece[0].slice(), len = piece[1];
        if (hit) return;
        if (Math.hypot.apply(null, pts[0]) > Math.hypot.apply(null, pts[pts.length - 1])) pts.reverse();
        for (var back = Math.min(tw / 2 + 4, len / 2); back <= Math.max(len - tw / 2, tw / 2 + 4) && !hit; back += 6) {
          var left = back, at = null, dir = null;
          for (var i = pts.length - 1; i > 0; i--) {
            var a = pts[i - 1], b = pts[i], sl = Math.hypot(b[0] - a[0], b[1] - a[1]);
            if (sl >= left || i === 1) { var f = sl ? Math.min(1, left / sl) : 0; at = [b[0] - f * (b[0] - a[0]), b[1] - f * (b[1] - a[1])]; dir = [(b[0] - a[0]) / (sl || 1), (b[1] - a[1]) / (sl || 1)]; break; }
            left -= sl;
          }
          [1, -1].forEach(function (sg) {
            if (hit) return;
            var c = add(at, right(dir), sg * (R + 6)), cand = [c, dir];
            var ok = [[-1, -1], [1, -1], [1, 1], [-1, 1]].every(function (k) {
              var x = c[0] + dir[0] * k[0] * tw / 2 - dir[1] * k[1] * 5, y = c[1] + dir[1] * k[0] * tw / 2 + dir[0] * k[1] * 5;
              return x > 2 - cx && x < W - 2 - cx && y > 2 - cy && y < H - 20 - cy;
            });
            // The name is tested along its own slanted line, not by its upright bounding box, which on a diagonal street covers half the drawing.
            var smp = along(c, dir, tw), clear = function (list) { return list.every(function (q) { return smp.every(function (p) { return p[0] < q[0] - 5 || p[0] > q[2] + 5 || p[1] < q[1] - 5 || p[1] > q[3] + 5; }); }); };
            if (ok && !first && clear(labs)) first = cand;
            if (ok && clear(boxes)) hit = cand;
          });
        }
        });
        // Too short to hold its name inside the frame: left unlabelled rather than cut off. So is a street no party
        // is on (not a leg at the point) whose name would cover a glyph, a tag or an arrow.
        if (!hit && (!first || !g.geo.l.some(function (lg) { return lg[3] === name; }))) return;
        var c = (hit || first)[0], dir = (hit || first)[1], ang = Math.atan2(dir[1], dir[0]) * 180 / Math.PI;
        if (ang > 90) ang -= 180; else if (ang <= -90) ang += 180;
        along(c, dir, tw).forEach(function (p) { var lb = [p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5]; boxes.push(lb); labs.push(lb); });
        out.push('<text transform="translate(' + P(c).replace(" ", ",") + ") rotate(" + ang.toFixed(1) + ')" text-anchor="middle" dy="3" class="cc-road" stroke="#fff" stroke-width="2.5" paint-order="stroke">' + esc(name) + "</text>");
      });
      return out;
    }
  }

  // Each party's people and how badly each was hurt, after the party's line: card.pi[i] is a list of [level] for the
  // party's own person or [level, who] for anyone else in it (a passenger), level k, s, v, p (the map's four levels,
  // in its words and colours) or n, nobody in the victims table. A parked vehicle has no entries.
  var LEVELS = { k: ["Killed", KIL], s: ["Severe injury", SEV], v: ["Other visible injury", VIS], p: ["Complaint of pain", PAIN] };
  function injuries(list) {
    return (list || []).map(function (e) {
      var lv = LEVELS[e[0]], who = e[1] ? esc(e[1]) + ": " : "";
      if (!lv) return ' <span class="cc-none">· ' + who + "no injury recorded</span>";
      // The dot stays with the level, so a line never ends on a bare separator.
      return (who ? " · " + who : " ") + '<b class="cc-inj">' + (who ? "" : "· ") + '<i style="background:' + lv[1] + '"></i>' + (who ? lv[0].toLowerCase() : lv[0]) + "</b>";
    }).join("");
  }

  function slide(cr, ps, opts) {
    // ps: the map's people hurt in this crash. opts: { deathCard }.
    // A death with no police card leads with the fatality log's own line (dl). With a police report the account comes
    // first, above the drawing (Bryan, 2026-11-20: "Is there any narrative we're not showing? If so show it before the
    // map"): the parties in the drawing's numbers, each with what the report says it was doing and how badly each of
    // its people was hurt, then who the report holds at fault and the primary collision factor. DataSF publishes no
    // officer's narrative, so these coded fields are the whole account. The conditions and the place follow the drawing.
    if (!cr || !cr.pi) {
      var lead = ps.map(function (p) { return "<b>" + (p.k ? "Killed" : "Severely injured") + "</b>, " + esc((cr ? p.u : p.dl ? p.dl.split(", ").slice(0, 2).join(", ") : p.u + ", " + p.b).toLowerCase()); }).join("<br>");
      if (!cr) return '<div class="cc"><div class="cc-lead">' + lead + "</div>" + opts.deathCard(ps[0]) + "</div>";
    }
    var h = '<div class="cc">' + (lead ? '<div class="cc-lead">' + lead + "</div>" : "") + '<div class="cc-when">' + esc(cr.hd) + "</div>";
    var why = cr.dl.filter(function (r) { return r[0] === "Primary factor"; }), rest = cr.dl.filter(function (r) { return r[0] !== "Primary factor"; });
    h += '<ol class="cc-p">' + cr.pr.map(function (r, i) { return "<li>" + esc(r) + (cr.pi ? injuries(cr.pi[i]) : "") + "</li>"; }).join("") + "</ol>";
    if (cr.t || why.length) h += '<p class="cc-t">' + (cr.t ? esc(cr.t) + " " : "") + why.map(function (r) { return '<span class="cc-k">' + esc(r[0]) + ":</span> " + esc(r[1]); }).join("") + "</p>";
    h += diagram(cr.g);
    // How the drawing is made (arrows, turns, the dashed ring) is on the map's About page, not on every card.
    h += '<dl class="cc-d">' + rest.map(function (r) { return "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>"; }).join("") + "</dl>";
    ps.forEach(function (p) {
      if (p.nu && /^https?:\/\//.test(p.nu)) h += '<div class="cc-src">News: <a href="' + esc(p.nu) + '" target="_blank" rel="noopener">' + esc(p.no) + (p.nt ? ", " + esc(p.nt) : "") + "</a></div>";
      if (p.lid) h += '<div class="cc-src">Fatality log: <a href="https://data.sfgov.org/d/dau3-4s8f" target="_blank" rel="noopener">Vision Zero fatality log</a>, record ' + esc(p.lid) + "</div>";
    });
    h += '<div class="cc-src g">SFPD crash report ' + esc(cr.src) + ' in DataSF <a href="https://data.sfgov.org/d/ubvf-ztfx" target="_blank" rel="noopener">crashes</a>, ' +
      '<a href="https://data.sfgov.org/d/8gtc-pjc6" target="_blank" rel="noopener">parties</a> and <a href="https://data.sfgov.org/d/nwes-mmgh" target="_blank" rel="noopener">victims</a>' +
      (cr.g.geo ? '; streets from DataSF <a href="https://data.sfgov.org/d/3psu-pn9h" target="_blank" rel="noopener">street centrelines</a>' : "") + ".";
    return h + "</div></div>";
  }

  var panel = null;
  var onClose = null;
  function close() {
    if (panel) { panel.remove(); panel = null; document.removeEventListener("keydown", onKey); var f = onClose; onClose = null; if (f) f(); }
  }
  function onKey(e) {
    if (!panel || e.defaultPrevented) return;
    var car = panel.querySelector("wa-carousel");
    if (e.key === "Escape") { close(); return; }
    // Arrows only while focus is inside the panel: the carousel handles its own keys, and the map keeps its panning.
    if (!panel.contains(document.activeElement) || (car && car.contains(e.target))) return;
    if (e.key === "ArrowLeft" && car && car.previous) { car.previous(); e.preventDefault(); }
    else if (e.key === "ArrowRight" && car && car.next) { car.next(); e.preventDefault(); }
  }

  // items: [{cr, ps}] in date order; start: index to open on; mapEl: the map element (the panel sits over its right
  // edge on a wide screen and below it on a phone, so it never covers the map there).
  function open(items, start, mapEl, opts) {
    close();
    onClose = (opts && opts.onClose) || null;
    panel = document.createElement("aside");
    panel.id = "cc-panel";
    panel.setAttribute("aria-label", "Crashes at this spot");
    var nP = items.reduce(function (a, it) { return a + it.ps.length; }, 0), many = items.length > 1;
    var nav = many ? '<wa-button size="s" appearance="outlined" class="cc-prev" aria-label="Previous crash">&#8249; Prev</wa-button>' +
      '<wa-button size="s" appearance="outlined" class="cc-next" aria-label="Next crash">Next &#8250;</wa-button>' : "";
    var head = '<div class="cc-top"><span class="cc-count" aria-live="polite">' + (many ? (start + 1) + " of " + items.length + " crashes here" : "1 crash here") +
      (nP > items.length ? ", " + nP + " people hurt" : "") + '</span><span class="cc-btns">' + nav + '<wa-button size="s" appearance="plain" class="cc-x" aria-label="Close">Close</wa-button></span></div>';
    // The carousel's own arrows sit beside the slide and take a third of a 420 px card, so Prev and Next live in the
    // header; the carousel keeps swipe, drag, keyboard and the pagination dots.
    var body = many ? '<wa-carousel' + (items.length <= 12 ? " pagination" : "") + ' mouse-dragging class="cc-car">' +
      items.map(function (it) { return "<wa-carousel-item>" + slide(it.cr, it.ps, opts) + "</wa-carousel-item>"; }).join("") + "</wa-carousel>"
      : '<div class="cc-one">' + slide(items[0].cr, items[0].ps, opts) + "</div>";
    panel.innerHTML = head + body;
    // A host element (the dashboard's figures column, or the space under a story's map) takes the card in place of
    // the floating panel, so the card never covers the map.
    if (opts && opts.host) { opts.host.appendChild(panel); }
    else if (window.innerWidth >= 700) {
      panel.classList.add("float");
      panel.style.top = (mapEl.offsetTop + 8) + "px";
      panel.style.maxHeight = (mapEl.offsetHeight - 16) + "px";
      document.body.appendChild(panel);
    } else mapEl.insertAdjacentElement("afterend", panel);
    panel.querySelector(".cc-x").addEventListener("click", close);
    var car = panel.querySelector("wa-carousel"), count = panel.querySelector(".cc-count");
    if (car) {
      panel.querySelector(".cc-prev").addEventListener("click", function () { car.previous(); });
      panel.querySelector(".cc-next").addEventListener("click", function () { car.next(); });
      customElements.whenDefined("wa-carousel").then(function () {
        requestAnimationFrame(function () { if (car.goToSlide) car.goToSlide(start, "instant"); });
      });
      car.addEventListener("wa-slide-change", function (e) {
        var i = e.detail && typeof e.detail.index === "number" ? e.detail.index : 0;
        count.textContent = (i + 1) + " of " + items.length + " crashes here" + (nP > items.length ? ", " + nP + " people hurt" : "");
      });
    }
    document.addEventListener("keydown", onKey);
    if (window.innerWidth < 700 && !(opts && opts.noScroll)) panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  // layout(g): where diagram(g) puts each party (px from the crash point) and the drawn roads, for the checks in
  // scripts/safety-map-test.mjs.
  function layout(g) { var probe = {}; diagram(g, probe); return probe; }
  return { open: open, close: close, diagram: diagram, slide: slide, layout: layout };
})();
