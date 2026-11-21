// One reader's trip to school by each way, routed in the browser on the school
// simulation's own network (site/data/school-trip-graph.json, written by
// tools/school-trips/school-trip-graph.py) with the simulation's rules (tools/school-trips/school-sim.py,
// trips_one and minutes): walking at 2 mph; the car on drivable streets at
// rules.carMph (13.4 mph over the Google fit's slope, 0.955) plus 4.68 minutes
// (3 for parking and the walk in, 1.68 from the Google Routes fit), never shorter than the walk; the bike at 8.5 mph plus
// 2.1 minutes (1 for the bike, 1.1 from the calibration), on the route with the smallest total gap off the safe network among
// routes at most 25% longer than the shortest; Muni as the simulation's
// placeholder. The address is routed from the street nearest it, so a figure can
// differ a little from the simulation's, which joins a whole census block.
// Walking and biking keep off the chains flagged noWalk (a street a car uses
// whose sidewalks are mapped as their own ways, and busways); the car keeps to
// the chains flagged drive.
//
// makeRouter is written without imports or outside names so its source can be
// copied into the page as it is, and run under node by the parity check in
// scripts/school-trip-check.mjs.

export function makeRouter(G) {
  const R = 6371008.8, LAT0 = (37.76 * Math.PI) / 180, KX = Math.cos(LAT0) * R * Math.PI / 180, KY = R * Math.PI / 180;
  const MI = 1609.344, FL = G.flags, RU = G.rules;
  // vertices
  const nv = G.vertices.length / 2, vx = new Float64Array(nv), vy = new Float64Array(nv), vlon = new Float64Array(nv), vlat = new Float64Array(nv);
  for (let i = 0, a = 0, b = 0; i < nv; i++) {
    a += G.vertices[2 * i]; b += G.vertices[2 * i + 1];
    vlon[i] = a / 1e5; vlat[i] = b / 1e5; vx[i] = vlon[i] * KX; vy[i] = vlat[i] * KY;
  }
  // chains: ends, length, flags, and the drawn shape with its distance along
  const C = G.chains, nc = C.dm.length;
  const cu = new Int32Array(nc), cv = new Int32Array(nc), clen = new Float64Array(nc), cfl = new Uint8Array(nc), shape = new Array(nc);
  for (let i = 0, f = 0; i < nc; i++) {
    f += C.from[i]; cu[i] = f; cv[i] = f + C.to[i]; clen[i] = C.dm[i] / 10; cfl[i] = C.flags[i];
    const pts = [[vlon[cu[i]], vlat[cu[i]]]], m = C.mid[i];
    let a = Math.round(vlon[cu[i]] * 1e5), b = Math.round(vlat[cu[i]] * 1e5);
    for (let k = 0; k < m.length; k += 2) { a += m[k]; b += m[k + 1]; pts.push([a / 1e5, b / 1e5]); }
    pts.push([vlon[cv[i]], vlat[cv[i]]]);
    shape[i] = pts;
  }
  // adjacency
  const deg = new Int32Array(nv + 1);
  for (let i = 0; i < nc; i++) { deg[cu[i] + 1]++; deg[cv[i] + 1]++; }
  for (let i = 0; i < nv; i++) deg[i + 1] += deg[i];
  const adj = new Int32Array(2 * nc), fill = deg.slice(0, nv);
  for (let i = 0; i < nc; i++) { adj[fill[cu[i]]++] = i; adj[fill[cv[i]]++] = i; }
  // a grid over the chains' segments, for snapping
  const CELL = 50, cells = new Map();
  const cellKey = (cx, cy) => cx * 100000 + cy;
  for (let i = 0; i < nc; i++) {
    const p = shape[i];
    for (let k = 0; k < p.length - 1; k++) {
      const x0 = Math.min(p[k][0], p[k + 1][0]) * KX, x1 = Math.max(p[k][0], p[k + 1][0]) * KX;
      const y0 = Math.min(p[k][1], p[k + 1][1]) * KY, y1 = Math.max(p[k][1], p[k + 1][1]) * KY;
      for (let cx = Math.floor(x0 / CELL); cx <= Math.floor(x1 / CELL); cx++)
        for (let cy = Math.floor(y0 / CELL); cy <= Math.floor(y1 / CELL); cy++) {
          const kk = cellKey(cx, cy); let l = cells.get(kk); if (!l) cells.set(kk, (l = [])); l.push(i, k);
        }
    }
  }
  // Where a point joins the network: the nearest chain that `ok` allows, and every
  // one within the simulation's slack of it, each at its nearest point.
  function snap(lon, lat, ok) {
    const px = lon * KX, py = lat * KY;
    for (let r = CELL; r <= 6400; r *= 2) {
      const best = new Map();
      for (let cx = Math.floor((px - r) / CELL); cx <= Math.floor((px + r) / CELL); cx++)
        for (let cy = Math.floor((py - r) / CELL); cy <= Math.floor((py + r) / CELL); cy++) {
          const l = cells.get(cellKey(cx, cy)); if (!l) continue;
          for (let j = 0; j < l.length; j += 2) {
            const c = l[j], k = l[j + 1]; if (ok && !ok(c)) continue;
            const p = shape[c], ax = p[k][0] * KX, ay = p[k][1] * KY, bx = p[k + 1][0] * KX, by = p[k + 1][1] * KY;
            const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
            const t = L2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2)) : 0;
            const d = Math.hypot(px - ax - t * dx, py - ay - t * dy);
            const cur = best.get(c); if (!cur || d < cur.d) best.set(c, { c, k, t, d });
          }
        }
      if (!best.size) continue;
      const all = [...best.values()], m = Math.min(...all.map((q) => q.d));
      if (m + RU.slackM > r && r < 6400) continue;
      return all.filter((q) => q.d <= m + RU.slackM).map((q) => {
        // distance along the chain, the drawn shape's share scaled to its true length
        const p = shape[q.c]; let s = 0, at = 0;
        for (let k = 0; k < p.length - 1; k++) {
          const g = Math.hypot((p[k + 1][0] - p[k][0]) * KX, (p[k + 1][1] - p[k][1]) * KY);
          if (k < q.k) at += g; else if (k === q.k) at += q.t * g;
          s += g;
        }
        const pos = s ? (at / s) * clen[q.c] : 0;
        const pt = [p[q.k][0] + q.t * (p[q.k + 1][0] - p[q.k][0]), p[q.k][1] + q.t * (p[q.k + 1][1] - p[q.k][1])];
        return { c: q.c, d: q.d, pos, k: q.k, pt };
      });
    }
    return [];
  }
  // The drawn shape of chain c between distances a and b along it (b < a runs backwards).
  function part(c, a, b) {
    const p = shape[c], seg = [];
    let s = 0; for (let k = 0; k < p.length - 1; k++) { const g = Math.hypot((p[k + 1][0] - p[k][0]) * KX, (p[k + 1][1] - p[k][1]) * KY); seg.push(g); s += g; }
    const sc = s ? s / clen[c] : 0, lo = Math.min(a, b) * sc, hi = Math.max(a, b) * sc, out = [];
    const at = (d) => { let acc = 0; for (let k = 0; k < seg.length; k++) { if (acc + seg[k] >= d || k === seg.length - 1) { const t = seg[k] ? Math.max(0, Math.min(1, (d - acc) / seg[k])) : 0; return [p[k][0] + t * (p[k + 1][0] - p[k][0]), p[k][1] + t * (p[k + 1][1] - p[k][1])]; } acc += seg[k]; } return p[p.length - 1]; };
    out.push(at(lo)); let acc = 0;
    for (let k = 0; k < seg.length; k++) { acc += seg[k]; if (acc > lo && acc < hi) out.push(p[k + 1]); }
    out.push(at(hi));
    return a <= b ? out : out.reverse();
  }
  // A binary heap of (cost, vertex).
  function Heap() { this.k = []; this.v = []; }
  Heap.prototype.push = function (k, v) { const K = this.k, V = this.v; let i = K.length; K.push(k); V.push(v); while (i > 0) { const p = (i - 1) >> 1; if (K[p] <= k) break; K[i] = K[p]; V[i] = V[p]; i = p; } K[i] = k; V[i] = v; };
  Heap.prototype.pop = function () { const K = this.k, V = this.v, top = V[0], tk = K[0], lk = K.pop(), lv = V.pop(); const n = K.length; if (n) { let i = 0; for (;;) { let c = 2 * i + 1; if (c >= n) break; if (c + 1 < n && K[c + 1] < K[c]) c++; if (K[c] >= lk) break; K[i] = K[c]; V[i] = V[c]; i = c; } K[i] = lk; V[i] = lv; } this.top = tk; return top; };
  // Least cost from a's joins to b's joins. w(c) is a chain's cost per metre (Infinity
  // to forbid it), end(c) the cost per metre of the part of a chain a join runs along,
  // and cm the cost per metre of the straight joins themselves.
  function path(A, B, w, end, cm) {
    const dist = new Float64Array(nv).fill(Infinity), via = new Int32Array(nv).fill(-1), seed = new Int32Array(nv).fill(-1);
    const H = new Heap();
    A.forEach((q, i) => {
      const e = end(q.c); if (!isFinite(e)) return;
      [[cu[q.c], q.pos], [cv[q.c], clen[q.c] - q.pos]].forEach(([v, al]) => { const k = q.d * cm + al * e; if (k < dist[v]) { dist[v] = k; seed[v] = i; via[v] = -1; H.push(k, v); } });
    });
    const tgt = new Map();
    B.forEach((q, i) => { const e = end(q.c); if (!isFinite(e)) return; [[cu[q.c], q.pos], [cv[q.c], clen[q.c] - q.pos]].forEach(([v, al]) => { const k = q.d * cm + al * e; const l = tgt.get(v) || []; l.push([k, i]); tgt.set(v, l); }); });
    let best = Infinity, bv = -1, bi = -1, direct = null;
    // home and school on the same chain
    A.forEach((qa) => B.forEach((qb, i) => { if (qa.c !== qb.c) return; const e = end(qa.c); const k = (qa.d + qb.d) * cm + Math.abs(qa.pos - qb.pos) * e; if (k < best) { best = k; direct = [qa, qb]; bv = -1; bi = i; } }));
    while (H.k.length) {
      const u = H.pop(), du = H.top;
      if (du > dist[u]) continue;
      if (du >= best) break;
      const t = tgt.get(u); if (t) for (const [k, i] of t) if (du + k < best) { best = du + k; bv = u; bi = i; direct = null; }
      for (let j = deg[u]; j < deg[u + 1]; j++) {
        const c = adj[j], x = cu[c] === u ? cv[c] : cu[c], wc = w(c); if (!isFinite(wc)) continue;
        const nd = du + clen[c] * wc; if (nd < dist[x]) { dist[x] = nd; via[x] = c; seed[x] = seed[u]; H.push(nd, x); }
      }
    }
    if (!isFinite(best)) return null;
    // pieces from home to school: [coords, metres, chain or -1 for a straight join]
    const pieces = [];
    if (direct) {
      const [qa, qb] = direct;
      pieces.push([[qa.pt0, qa.pt], qa.d, -1], [part(qa.c, qa.pos, qb.pos), Math.abs(qa.pos - qb.pos), qa.c], [[qb.pt, qb.pt0], qb.d, -1]);
      return { cost: best, pieces };
    }
    const chainSeq = []; let v = bv;
    while (via[v] >= 0) { const c = via[v]; const u = cu[c] === v ? cv[c] : cu[c]; chainSeq.push([c, u, v]); v = u; }
    chainSeq.reverse();
    const qa = A[seed[bv]], qb = B[bi];
    pieces.push([[qa.pt0, qa.pt], qa.d, -1]);
    if (v === cu[qa.c]) pieces.push([part(qa.c, qa.pos, 0), qa.pos, qa.c]); else pieces.push([part(qa.c, qa.pos, clen[qa.c]), clen[qa.c] - qa.pos, qa.c]);
    chainSeq.forEach(([c, u]) => pieces.push([u === cu[c] ? shape[c] : shape[c].slice().reverse(), clen[c], c]));
    if (bv === cu[qb.c]) pieces.push([part(qb.c, 0, qb.pos), qb.pos, qb.c]); else pieces.push([part(qb.c, clen[qb.c], qb.pos), clen[qb.c] - qb.pos, qb.c]);
    pieces.push([[qb.pt, qb.pt0], qb.d, -1]);
    return { cost: best, pieces };
  }
  const metres = (P) => P.pieces.reduce((t, p) => t + p[1], 0);
  // The total gap: every metre off the safe chains, summed; a straight join is always off them (Bryan, 2026-10-21: "total
  // gap of 1000 feet or less between home and school").
  function gap(P, safe) { return P.pieces.reduce((t, p) => t + (p[2] >= 0 && safe(p[2]) ? 0 : p[1]), 0); }
  const safeMetres = (P, safe) => P.pieces.reduce((t, p) => t + (p[2] >= 0 && safe(p[2]) ? p[1] : 0), 0);
  function joins(lon, lat, ok) { return snap(lon, lat, ok).map((q) => Object.assign(q, { pt0: [lon, lat] })); }

  // Every way from home to a school's door, with `extra` (a Set of chain ids) made safe.
  function trip(home, door, extra) {
    const isSafe0 = (c) => (cfl[c] & FL.safe) !== 0, isSafe1 = (c) => isSafe0(c) || (extra && extra.has(c));
    const foot = (c) => (cfl[c] & (FL.noWalk || 0)) === 0;
    const A = joins(home[0], home[1], foot), B = joins(door[0], door[1], foot);
    if (!A.length || !B.length) return null;
    const walk = path(A, B, (c) => (foot(c) ? 1 : Infinity), () => 1, 1);
    if (!walk) return null;
    const walkM = metres(walk);
    // car
    const drv = (c) => (cfl[c] & FL.drive) !== 0;
    const Ad = joins(home[0], home[1], drv), Bd = joins(door[0], door[1], drv);
    const car = Ad.length && Bd.length ? path(Ad, Bd, (c) => (drv(c) ? 1 : Infinity), () => 1, 1) : null;
    const carM = car ? metres(car) : walkM;
    const carMin = (Math.max(carM, walkM) / MI / RU.carMph) * 60 + RU.carFixedMin;
    // bike, on each network
    const steps = (c) => (cfl[c] & FL.steps) !== 0;
    function bike(safe) {
      let best = null, m0 = null;
      for (const k of RU.gapK) {
        const P = path(A, B.filter((q) => !steps(q.c)).length ? B.filter((q) => !steps(q.c)) : B,
          (c) => (steps(c) || !foot(c) ? Infinity : 1 + k * (safe(c) ? 0 : 1)), (c) => 1 + k * (safe(c) && !steps(c) ? 0 : 1), 1 + k);
        if (!P) continue;
        const m = metres(P), g = gap(P, safe);
        if (m0 == null) { m0 = m; best = { P, m, g }; continue; }
        if (m <= RU.detour * m0 + 1e-6 && (g < best.g - 1e-6 || (Math.abs(g - best.g) <= 1e-6 && m < best.m))) best = { P, m, g };
      }
      if (!best) return { P: walk, m: walkM, g: gap(walk, safe) };
      return best;
    }
    const b0 = bike(isSafe0), b1 = extra && extra.size ? bike(isSafe1) : b0;
    const walkMi = walkM / MI;
    const out = {
      walk: { P: walk, m: walkM, min: (walkMi / RU.walkMph) * 60, safe0: safeMetres(walk, isSafe0), safe1: safeMetres(walk, isSafe1) },
      bike0: { P: b0.P, m: b0.m, min: (b0.m / MI / RU.bikeMph) * 60 + RU.bikeFixedMin, gap: b0.g, safe: safeMetres(b0.P, isSafe0) },
      bike1: { P: b1.P, m: b1.m, min: (b1.m / MI / RU.bikeMph) * 60 + RU.bikeFixedMin, gap: b1.g, safe: safeMetres(b1.P, isSafe1) },
      car: { P: car, m: carM, min: carMin },
      transit: { min: RU.transitFixedMin + (walkMi / RU.transitMph) * 60 },
      walkMi,
    };
    return out;
  }
  // GeoJSON of a route, one feature per run of safe or unsafe pieces.
  function geo(P, mode, safe) {
    const fs = [];
    if (!P) return fs;
    let cur = null;
    for (const p of P.pieces) {
      const s = p[2] >= 0 && safe(p[2]) ? 1 : 0;
      if (!cur || cur.properties.safe !== s) { cur = { type: "Feature", properties: { mode, safe: s }, geometry: { type: "LineString", coordinates: p[0].slice() } }; fs.push(cur); }
      else cur.geometry.coordinates.push(...p[0].slice(1));
    }
    return fs;
  }
  const chainGeo = (ids) => [...ids].map((c) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: shape[c] } }));
  const isSafe = (extra) => (c) => (cfl[c] & FL.safe) !== 0 || (extra && extra.has(c));
  return { trip, geo, chainGeo, isSafe, schools: Object.fromEntries(G.schools.map((s) => [s.cds, s])) };
}
