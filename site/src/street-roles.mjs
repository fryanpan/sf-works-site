// The Street Roles Map's shared parts: its data, its words, and the model the page runs in the browser.
//
// The model is one function, `model()`, written once. The page inlines its source (MODEL_SRC), so a reader's
// change of a street's role recomputes stress and the stat row in the browser, and
// tools/street-roles/parity.mjs calls the same function to check it against the Python build
// (tools/street-roles/street-roles.py), which applies the same rules on its own.

import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));

export const SUMMARY = read("out/street-roles/summary.json");
export const STREETS_FILE = "site/data/street-roles/streets.json";
export const COMMUTES_FILE = "site/data/street-roles/commutes.json";

// The role colours: an unordered set, so Observable 10's first, second, fourth and seventh hues (CLAUDE.md,
// colour rule: observable10 for categories; its third, a coral, is left out because red is not a category).
export const ROLE_COLOURS = { through: "#4269d0", local: "#efb118", bike: "#6cc5b0", walk: "#a463f2" };
export const ROLE_LABELS = { through: "Through", local: "Local", bike: "Bike", walk: "Walk" };
export const ROLE_LINES = {
  through: "through traffic",
  local: "local trips",
  bike: "bikes",
  walk: "people on foot",
};
// Stress is ordered, so it takes the site's sequential tokens: low stress (1 or 2) the calm end.
export const STRESS_BANDS = [
  ["low", "Most adults will ride it", "--seq-3"],
  ["3", "Confident riders only", "--seq-2"],
  ["4", "Very few will ride it", "--seq-1"],
];

// Each source's read date, from the tags the build wrote into streets.json's meta ("[... — queried YYYY-MM-DD]").
const META = read(STREETS_FILE).meta;
const readOf = (tag) => (String(tag).match(/\d{4}-\d{2}-\d{2}/) || [""])[0];

export const SOURCES = [
  { label: "DataSF, street centerlines (the city's street classification)", href: "https://data.sfgov.org/d/3psu-pn9h", read: readOf(META.centerlines) },
  { label: "SFMTA and Toole Design, 2023 draft Bike Comfort Index (each block's bike level of traffic stress)", href: "https://services6.arcgis.com/bom7L4u7y1k0qkF1/arcgis/rest/services/Bike_Comfort_Index_Score/FeatureServer/4", read: readOf(META.bci) },
  { label: "SFMTA, Biking and Rolling Plan, March 2025 (the North Star network and its facility types)", href: "https://www.sfmta.com/media/41810/download", read: "2026-09-29" },
  { label: "SFMTA, traffic lanes (lanes on each block)", href: "https://services.sfmta.com/arcgis/rest/services/DataSF/master/MapServer/54", read: readOf(META.lanes) },
  { label: "DataSF, speed limits", href: "https://data.sfgov.org/d/3t7b-gebn", read: readOf(META.speed) },
  { label: "U.S. Census Bureau, LODES 8 origin-destination data, 2023 (where SF residents work)", href: "https://lehd.ces.census.gov/data/lodes/LODES8/ca/od/", read: "2026-11-06" },
  { label: "Mekuria, Furth and Nixon, Low-Stress Bicycling and Network Connectivity, Mineta Transportation Institute, 2012 (the stress and connectivity method)", href: "https://transweb.sjsu.edu/sites/default/files/1005-low-stress-bicycling-network-connectivity.pdf", read: "2026-11-27" },
];

/** Two significant figures, as the tool rules ask (tool UX rule 30). */
export function sig2(n) {
  if (!n) return "0";
  const p = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.abs(n))) - 1));
  return (Math.round(n / p) * p).toLocaleString("en-US");
}

/**
 * The model. ES5, because the page inlines its source as it stands.
 *   stress(role, B, i)                        block i's stress with the network as role; null where it isn't ridden
 *   connected(S, C, stressOf)                [commuters connected at stress 2 or lower, commuters counted]
 * S is streets.json, C commutes.json, stressOf(i) a block's stress (null: not ridden).
 */
export function model() {
  var LOW = 2, MILE = 5280, MIN_FT = 0.5 * MILE, MAX_FT = 6 * MILE, RATIO = 1.25, EXTRA = 1760;
  // Mekuria, Furth and Nixon, Table 4, mixed traffic, as tools/street-roles/street-roles.py mixed() reads it.
  function mixed(mph, total, dir, low) {
    if (mph > 30 || total >= 6) return 4;
    if (total >= 4) return mph <= 25 ? 3 : 4;
    var lower = low && total < 3, v = mph <= 25 ? (lower ? 1 : 2) : (lower ? 2 : 3);
    return dir >= 2 ? Math.max(v, 3) : v;
  }
  function stress(role, B, i) {
    var t = B.today[i], plan = B.plan[i], sep = plan === "S" || plan === "C" || plan === "P", v;
    if (role === "walk") return null;
    if (role === "through") return sep ? 1 : t;
    if (role === "bike" && plan && plan !== "U") v = sep ? 1 : plan === "H" && !B.muni[i] && B.dir[i] < 2 ? 1 : mixed(B.mph[i], B.lanes[i], B.dir[i], false);
    else v = mixed(B.mph[i], B.lanes[i], B.dir[i], true);
    return Math.min(t, v);
  }
  // The network as compressed rows, keeping only blocks keep(i) admits.
  function graph(S, keep) {
    var B = S.blocks, n = S.nodes, deg = new Int32Array(n + 1), i;
    for (i = 0; i < B.cnn.length; i++) if (keep(i)) { deg[B.a[i] + 1]++; deg[B.b[i] + 1]++; }
    for (i = 0; i < n; i++) deg[i + 1] += deg[i];
    var to = new Int32Array(deg[n]), w = new Float64Array(deg[n]), fill = deg.slice(0, n);
    for (i = 0; i < B.cnn.length; i++) if (keep(i)) {
      var a = B.a[i], b = B.b[i], ft = Math.max(1, B.ft[i]);
      to[fill[a]] = b; w[fill[a]++] = ft; to[fill[b]] = a; w[fill[b]++] = ft;
    }
    return { n: n, off: deg, to: to, w: w };
  }
  // Shortest feet from a set of sources, out to limit, with a binary heap.
  function dijkstra(G, sources, limit, dist) {
    var hk = [], hv = [], seen = new Uint8Array(G.n), i;
    for (i = 0; i < G.n; i++) dist[i] = Infinity;
    function push(k, v) {
      var j = hk.length; hk.push(k); hv.push(v);
      while (j > 0) { var p = (j - 1) >> 1; if (hk[p] <= k) break; hk[j] = hk[p]; hv[j] = hv[p]; j = p; }
      hk[j] = k; hv[j] = v;
    }
    function pop() {
      var top = hv[0], k = hk.pop(), v = hv.pop(), n = hk.length, j = 0;
      if (n) {
        while (true) {
          var l = 2 * j + 1, r = l + 1, m = j, mk = k;
          if (l < n && hk[l] < mk) { m = l; mk = hk[l]; }
          if (r < n && hk[r] < mk) { m = r; mk = hk[r]; }
          if (m === j) break;
          hk[j] = hk[m]; hv[j] = hv[m]; j = m;
        }
        hk[j] = k; hv[j] = v;
      }
      return top;
    }
    for (i = 0; i < sources.length; i++) { dist[sources[i]] = 0; push(0, sources[i]); }
    while (hk.length) {
      var d = hk[0], u = pop();
      if (seen[u]) continue;
      seen[u] = 1;
      if (d > limit) break;
      for (var e = G.off[u]; e < G.off[u + 1]; e++) {
        var v = G.to[e], nd = d + G.w[e];
        if (!seen[v] && nd < dist[v]) { dist[v] = nd; push(nd, v); }
      }
    }
    for (i = 0; i < G.n; i++) if (!seen[i]) dist[i] = Infinity;
    return dist;
  }
  function connected(S, C, stressOf) {
    var G = graph(S, function (i) { var s = stressOf(i); return s !== null && s <= LOW; });
    var dist = new Float64Array(G.n), conn = 0, tot = 0;
    for (var o = 0; o < C.pairs.length; o++) {
      var row = C.pairs[o], any = false, r;
      for (r = 0; r < row.length; r++) if (row[r][2] !== null && row[r][2] >= MIN_FT && row[r][2] <= MAX_FT) { any = true; break; }
      if (!any) continue;
      dijkstra(G, [C.home[o]], MAX_FT * RATIO + EXTRA, dist);
      for (r = 0; r < row.length; r++) {
        var l4 = row[r][2];
        if (l4 === null || l4 < MIN_FT || l4 > MAX_FT) continue;
        tot += row[r][1];
        var lk = dist[C.work[row[r][0]]];
        if (lk < RATIO * l4 || lk - l4 < EXTRA) conn += row[r][1];
      }
    }
    return [conn, tot];
  }
  return { stress: stress, connected: connected, LOW: LOW };
}

export const MODEL_SRC = `(${model.toString()})()`;
