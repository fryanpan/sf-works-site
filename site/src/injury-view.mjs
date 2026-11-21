// The injury page's view, kept in its address so a copied link reopens what
// the reader was looking at (Bryan, 2026-10-21: "make it possible to look at
// where injuries happened near a specific school, and share a link around for
// what you're looking at").
//
//   ?school=<cds>   the school picked, by its CDS code in site/data/school-sim/index.json
//   &set=all|sev|kid|kidsev  the injury view, when it isn't the default (kids with a school, all without)
//   &fx=qb,cam      the fix layers ticked
//   &at=lat,lon,z   the map's centre and zoom, once the reader has moved it
//
// The page inlines these functions with Function.prototype.toString, so they
// are plain browser JavaScript; site/tests/injury-view-test.mjs imports them here.
// Anything the address carries that isn't the page's own, such as a board
// frame's parameter, is kept by writeView when it is given the current search.

export function readView(search, schools, fixes) {
  var q = new URLSearchParams(search || "");
  var v = { school: null, set: "all", fx: [], at: null };
  var s = q.get("school");
  if (s && schools.indexOf(s) >= 0) v.school = s;
  var set = q.get("set");
  if (set === "all" || set === "sev" || set === "kid" || set === "kidsev") v.set = set;
  else if (v.school) v.set = "kid";
  (q.get("fx") || "").split(",").forEach(function (f) {
    if (fixes.indexOf(f) >= 0 && v.fx.indexOf(f) < 0) v.fx.push(f);
  });
  var at = (q.get("at") || "").split(",").map(Number);
  if (at.length === 3 && at.every(isFinite) && at[0] > 37.6 && at[0] < 37.85 && at[1] > -122.6 && at[1] < -122.3 && at[2] >= 9 && at[2] <= 18) {
    v.at = { lat: at[0], lon: at[1], zoom: at[2] };
  }
  return v;
}

export function writeView(v, search) {
  var q = new URLSearchParams(search || "");
  ["school", "set", "fx", "at"].forEach(function (k) { q.delete(k); });
  if (v.school) q.set("school", v.school);
  if (v.set !== (v.school ? "kid" : "all")) q.set("set", v.set);
  if (v.fx.length) q.set("fx", v.fx.join(","));
  if (v.at) q.set("at", [v.at.lat.toFixed(5), v.at.lon.toFixed(5), v.at.zoom.toFixed(2)].join(","));
  var s = q.toString().replace(/%2C/g, ",");
  return s ? "?" + s : "";
}

// The count line under the school picker, people first: n kids hurt (or, with sev, severely hurt or killed) within a
// quarter mile of the school named, or across the city when no school is named. The name is escaped here.
export function kidLine(n, sev, name) {
  var who = n === 0 ? "No kids" : n === 1 ? "<b>1 kid</b>" : "<b>" + n.toLocaleString("en-US") + " kids</b>";
  return who + " " + (n === 1 ? "was" : "were") + (sev ? " severely hurt or killed" : " hurt") +
    (name ? " within a quarter mile of " + name.replace(/&/g, "&amp;").replace(/</g, "&lt;") : " on school trips across San Francisco") + ".";
}
