// The Street Safety map's state: one plain object that says everything the map shows, so a dashboard can put it in
// the address and an article can step the map from one state to the next (Bryan, 2026-11-19: "all of the settings in
// the map can transition from one configuration to another to tell a story (e.g. location to look at, region to
// highlight, map layers to enable)").
//
//   {
//     view:      "injuries" | "stress" | "through" | "bike" | "crime" | "from" (where traffic comes from)
//     near:      the through-traffic view's distance: a trip end within it of a block is local, farther is through,
//                "quarter", "half" (half a mile, the default: Bryan, 2026-11-20, "Default to half mile"), "3q" (three
//                quarters) or "mile"
//     ends:      the where-from view's choice of trips: "from" (cars coming in from outside the area, at their start),
//                "to" (cars going out of it, at their end) or "both"; "from" is the default
//     camera:    null (all of San Francisco) or { center: [lon, lat], zoom, bearing }
//     hin:       High Injury Network editions drawn on the injuries view, any of "2024", "2022", "2017", and "groups":
//                the 2024 network coloured by 10-mile group, worst first
//     rank:      the years the 10-mile groups are ranked on, "2020-2024" (DPH's own window) or "2022-2024" (the map's)
//     worst:     null, or a year 2020 to 2025 whose worst 10 miles of street are drawn
//     color:     "people" (figures and heat) or "hin" (each person coloured by whether they're on the 2024 High Injury
//                Network, by the 60 ft rule). The crash groups' "group" is gone (Bryan, 2026-11-19, thread
//                k8f5kgtf5nur: "Remove crash groups"); an address that names it opens "people".
//     filter:    { user: [] (everyone) or road users ("Walking", "Biking", ...), cause: [] (every cause) or entries
//                  "<cause key>" or "<cause key>/<subcause key>" (map.json `causes`), years: null (all) or [from, to],
//                  severity: the least severe level shown, with everything more severe: "killed", "severe"
//                  (the default), "visible" or "pain" (SEVERITIES), hinGroup: [] (every group) or 10-mile group numbers, hin: "all" | "on" | "off" (the 2024 network, 60 ft),
//                  at: "all" | "intersection" | "midblock", time: [] (any time) or ids of TIMES,
//                  other: [] (any) or keys of OTHERS (the other party involved),
//                  days: [] (every day), ["weekday"], ["weekend"] or single days ("mon" ... "sun", WEEK), area: null, { hood: "<analysis neighborhood>" },
//                  { district: 1 to 11 } (a Supervisor district) or { polygon: [[lon, lat], ...] }, bci: [] (every class) or Bike Comfort Index class numbers 0 to 4,
//                  crimeYears: null (every year from 2018) or [from, to] (CRIME_YEARS), crimeKinds: [] (every kind) or keys of CRIME_KINDS }
//                An empty list means no filter, and so does a list holding every choice: it is stored empty.
//     highlight: null, { area: "<analysis neighborhood>" }, { blocks: [cnn, ...] } or { circle: { center, feet } }
//     crash:     null or an SFPD case number whose crash card is open
//     chart:     null (the view's own chart) or { id } naming one of CHARTS, "none" for no chart. { id: "by-cause",
//                top: true } keeps the cause chart at its top level with one whole cause picked (address `pick=<cause>`):
//                the map filtered to it and its bar highlighted, rather than drilled into its Vehicle Code sections
//   }
//
// The area, time and day filters are the whole map's (Bryan, 2026-11-19: "I think the times of day and day of week are
// an interesting filter, just to have globally"; "if I select a community and neighborhood and area, to be able to see
// all of the stats and analyses and so on, for that one area").
//
// A plain script with no imports: the site inlines it into each page (src/safety-map/index.mjs), and the tests
// (site/tests/safety-map-test.mjs) run it in a vm context. It defines SafetyMapState on whatever `this` it runs in.
(function (root) {
  var VIEWS = ["injuries", "stress", "through", "bike", "crime", "from"];
  // The through-traffic distance slider (Bryan, 2026-11-19): [id, label, phrase].
  var NEARS = [["quarter", "¼ mi", "a quarter of a mile"], ["half", "½ mi", "half a mile"], ["3q", "¾ mi", "three quarters of a mile"], ["mile", "1 mi", "a mile"]];
  // Where traffic comes from (Bryan, 2026-11-19: "let the user choose which group to include --
  // where traffic is coming from, where is it going to, and both"): [id, label].
  var ENDS = [["from", "Coming from"], ["to", "Going to"], ["both", "Both"]];
  var HINS = ["groups", "2024", "groups22", "2022", "2017"];
  // Police report levels, most severe first, in DataSF nwes-mmgh's own words: [id, label, level]. A choice shows its
  // level and every one above it (Bryan, 2026-11-19: "a range slider where you can filter to that
  // level and anything more severe").
  var SEVERITIES = [["killed", "Killed", 0], ["severe", "Severe injury", 1], ["visible", "Other visible injury", 2], ["pain", "Complaint of pain", 3]];
  var RANKS = ["2020-2024", "2022-2024"];
  var WORST_YEARS = [2020, 2021, 2022, 2023, 2024, 2025];
  // "Other": 47 light-path reports whose own party maps to none of these (tools/street-safety/street-safety-light.py).
  var USERS = ["Walking", "Biking", "Motorcycle or moped", "Scooter or board", "Car or truck", "Other"];
  // The other party involved in a person's crash, one option per person (Bryan, 2026-11-20: "add another filter on
  // other party involved. And so options would be something like 'No other vehicle', 'Car', 'Bike', 'Multiple
  // vehicles'"): [key, label]. tools/street-safety/street-safety-light.py OTHERS says what each counts and reads it from the
  // crash's other party rows; a person on foot is not a vehicle, and a parked vehicle is not a moving one. "Unknown
  // vehicle" is one other moving vehicle whose type the report doesn't give; as a leftover it is the chart's last bar.
  var OTHERS = [["none", "No other vehicle"], ["foot", "Person on foot"], ["car", "Car or truck"], ["moto", "Motorcycle or moped"], ["bike", "Bike or scooter"], ["parked", "Parked vehicle"], ["multiple", "Multiple vehicles"], ["unknown", "Unknown vehicle"]];
  // The police reports' years, 2005 (DataSF nwes-mmgh's first) to the newest, which is not yet complete. The map opens
  // on 2021 to now (Bryan, 2026-11-19: "By default, please show 2021-current day"); map.json
  // holds those years and the page loads 2005 to 2020 when the Years slider reaches back.
  var YEARS = [], NEWEST_YEAR = 2026, INLINE_FROM = 2021;
  for (var yy = 2005; yy <= NEWEST_YEAR; yy++) YEARS.push(yy);
  // The crime view's years: SFPD's incident reports (DataSF wg3w-h783) start in 2018. The view opens on every year
  // (Bryan, 2026-11-19: "Thought we would have more than 12 months?").
  var CRIME_YEARS = [];
  for (var cy = 2018; cy <= NEWEST_YEAR; cy++) CRIME_YEARS.push(cy);
  // The crime view's kinds, in the order of the data's groups (tools/street-safety/sfpd-person-crimes.py GROUPS, which
  // tools/street-safety/street-safety-map.py checks against these labels): [key, label].
  var CRIME_KINDS = [["violence", "Violence and weapons"], ["theft", "Theft, burglary and fraud"], ["vandalism", "Vandalism and arson"], ["drugs", "Drugs"], ["other", "Other"]];
  // Times of day by the report's hour: [id, label, first hour, hour after the last]. Night wraps past midnight.
  var TIMES = [["am", "Morning rush, 6 to 9 am", 6, 9], ["midday", "Midday, 9 am to 3 pm", 9, 15], ["pm", "Evening rush, 3 to 7 pm", 15, 19],
    ["evening", "Evening, 7 to 10 pm", 19, 22], ["night", "Night, 10 pm to 6 am", 22, 6]];
  // Day of week, by the weekday of the crash or report date (JavaScript's getUTCDay(): Sunday is 0). One grouping
  // for the whole map, so the filter, the chart and the address all use the same days: DAY_GROUPING picks it
  // (Bryan, 2026-11-19: Weekday / Weekend if that is a fair way to collapse the week, else the seven days).
  var DAY_SETS = {
    weekpart: [["weekday", "Weekdays", [1, 2, 3, 4, 5]], ["weekend", "Weekends", [0, 6]]],
    days: [["mon", "Mon", [1]], ["tue", "Tue", [2]], ["wed", "Wed", [3]], ["thu", "Thu", [4]], ["fri", "Fri", [5]], ["sat", "Sat", [6]], ["sun", "Sun", [0]]],
  };
  var DAY_GROUPING = "weekpart";
  var DAYS = DAY_SETS[DAY_GROUPING];
  // The day and time filters are two rows of toggles (Bryan, 2026-11-19: "two multiselect filters
  // one for Weekday vs. Weekend. Or another button for custom, to pick which days of week. And another for time of day
  // period"): days are weekdays, weekends or any set of single days (WEEK), times any set of TIMES. Friday evening is
  // Friday and the evening.
  var WEEK = DAY_SETS.days;
  // A short name for a day and time choice ("Weekdays, evening rush"), or null for any day and any time.
  function whenLabel(f) {
    var d = f.days || [], t = f.time || [];
    if (!d.length && !t.length) return null;
    var day = !d.length ? "" : d[0] === "weekday" ? "Weekdays" : d[0] === "weekend" ? "Weekends" :
      WEEK.filter(function (w) { return d.indexOf(w[0]) >= 0; }).map(function (w) { return w[1]; }).join(", ");
    var time = TIMES.filter(function (x) { return t.indexOf(x[0]) >= 0; }).map(function (x) { return x[1].split(",")[0].toLowerCase(); }).join(", ");
    return day && time ? day + ", " + time : day || time.replace(/^\w/, function (c) { return c.toUpperCase(); });
  }
  // The filters each view takes, so the panel shows a control only where it changes what the map shows (Bryan,
  // 2026-11-19, on Bike Comfort: "remove the time of day selector -- we don't support that"). A
  // filter set on another view stays in the state and is ignored here; the headline note says so for the day and time
  // (overlay.js). Through traffic takes the day for its "No weekend data" note: the model is one weekday.
  var FILTERS = { injuries: ["area", "days", "time", "user", "other", "severity", "years", "cause", "network", "hinGroup"], crime: ["area", "days", "time", "crimeKinds", "crimeYears"],
    through: ["area", "days", "time"], stress: ["area"], bike: ["area", "bci"], from: ["area"] };
  // Each view's charts, the first its default; the injuries view has one for every filter it takes (Bryan,
  // 2026-11-19: "Each thing you can filter by should also be in the dropdown"). "by-hin" splits the people on and off the 2024 network, by the same
  // 60 ft rule as the filter.
  var CHARTS = { injuries: ["by-year", "by-severity", "by-cause", "by-user", "by-other", "by-day", "by-time", "by-hood", "by-district", "by-hin", "by-hin-group", "worst-overlap"], stress: ["stress-mix"], through: ["through-mix"], bike: ["bci-mix"], from: ["from-groups", "from-time"],
    crime: ["crime-groups", "crime-by-year", "crime-by-day", "crime-by-time"] };
  // The charts whose bars have no order of their own are sorted by the count they show, largest first, under whatever
  // filters are on, with the leftover bars ("Other", "Unknown or not stated", "No neighborhood") last in their own order (Bryan, 2026-11-19:
  // "Items should be sorted by the data they show ... (except Other)"). Years, days, times of day, severity, the HIN
  // split and the 10-mile groups keep their own order.
  var SORTED_CHARTS = ["by-cause", "by-user", "by-other", "by-hood", "by-district"];
  function isLeftover(r) { return r.key === "" || /(^|\/)(other|unknown[a-z-]*)$/i.test(String(r.key)) || /^(other|unknown)\b/i.test(String(r.label)); }
  function sortRows(id, rows) {
    if (SORTED_CHARTS.indexOf(id) < 0) return rows;
    return rows.map(function (r, i) { return [r, i]; }).sort(function (a, b) {
      var la = isLeftover(a[0]), lb = isLeftover(b[0]);
      return la - lb || (la ? 0 : b[0].value - a[0].value) || a[1] - b[1];
    }).map(function (x) { return x[0]; });
  }
  var DEFAULTS = {
    view: "injuries", camera: null, near: "half", ends: "from", hin: ["2024"], color: "people", rank: "2020-2024", worst: null,
    filter: { user: [], other: [], cause: [], years: [INLINE_FROM, NEWEST_YEAR], severity: "severe", hinGroup: [], hin: "all", at: "all", time: [], days: [], area: null, bci: [], crimeYears: null, crimeKinds: [] }, highlight: null, crash: null, card: null, chart: null,
  };
  // The filters that take one value.
  var FILTER_VALUES = { severity: SEVERITIES.map(function (x) { return x[0]; }), hin: ["all", "on", "off"], at: ["all", "intersection", "midblock"] };

  // Filter names in the address: "hin" is taken by the editions and "at" by the camera.
  var HASH_KEY = { user: "user", other: "other", cause: "cause", years: "years", severity: "severity", hinGroup: "groups", hin: "on", at: "where", time: "time", days: "days", bci: "bci", crimeYears: "cyears", crimeKinds: "kinds" };

  function clone(v) { return v == null ? v : JSON.parse(JSON.stringify(v)); }
  function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }
  function round(v, k) { var f = Math.pow(10, k); return Math.round(v * f) / f; }
  function list(v) { return v == null || v === "all" || v === "" ? [] : Array.isArray(v) ? v : String(v).split(","); }

  function normArea(a) {
    if (!a) return null;
    if (typeof a.hood === "string" && a.hood) return { hood: a.hood };
    var dn = Number(a.district);
    if (a.district != null && dn >= 1 && dn <= 11 && dn === Math.round(dn)) return { district: dn };
    if (Array.isArray(a.polygon)) {
      var pts = a.polygon.filter(function (p) { return Array.isArray(p) && p.length === 2 && isFinite(Number(p[0])) && isFinite(Number(p[1])); })
        .map(function (p) { return [round(Number(p[0]), 5), round(Number(p[1]), 5)]; });
      if (pts.length > 1 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1]) pts.pop();
      if (pts.length >= 3) return { polygon: pts };
    }
    return null;
  }

  // Road users in USERS order; every one of them is no filter.
  function normUsers(v) {
    var want = list(v);
    var out = USERS.filter(function (u) { return want.indexOf(u) >= 0; });
    return out.length === USERS.length ? [] : out;
  }
  // Other parties as keys of OTHERS in their own order; every one of them is no filter.
  function normOthers(v) {
    var want = list(v), out = OTHERS.map(function (o) { return o[0]; }).filter(function (k) { return want.indexOf(k) >= 0; });
    return out.length === OTHERS.length ? [] : out;
  }
  // Days as weekdays, weekends or single days. Every older form still reads: "weekdays", "weekend", a single day ("sat",
  // "fri" from the Friday evening choice) or a list of them become the weekdays they cover, written back in the
  // shortest form: Monday to Friday is "weekday", Saturday and Sunday "weekend", every day nothing.
  var OLD_DAYS = { weekdays: [1, 2, 3, 4, 5], weekday: [1, 2, 3, 4, 5], weekend: [0, 6], weekends: [0, 6] };
  [DAY_SETS.weekpart, DAY_SETS.days].forEach(function (set) { set.forEach(function (d) { OLD_DAYS[d[0]] = OLD_DAYS[d[0]] || d[2]; }); });
  function normDays(v) {
    var wd = [];
    list(v).forEach(function (id) { (OLD_DAYS[id] || []).forEach(function (w) { if (wd.indexOf(w) < 0) wd.push(w); }); });
    var key = wd.slice().sort().join();
    if (wd.length === 7) return [];
    if (key === "1,2,3,4,5") return ["weekday"];
    if (key === "0,6") return ["weekend"];
    return WEEK.filter(function (d) { return wd.indexOf(d[2][0]) >= 0; }).map(function (d) { return d[0]; });
  }
  // Times of day as ids of TIMES in their own order; "all", or every time, is none.
  function normTimes(v) {
    var want = list(v), out = TIMES.filter(function (t) { return want.indexOf(t[0]) >= 0; }).map(function (t) { return t[0]; });
    return out.length === TIMES.length ? [] : out;
  }
  // Cause entries, sorted, with a subcause dropped where its whole cause is chosen.
  function normCause(v) {
    var ok = list(v).map(String).filter(function (e) { return /^[a-z0-9-]+(\/[A-Za-z0-9().-]+)?$/.test(e); });
    var whole = ok.filter(function (e) { return e.indexOf("/") < 0; });
    return ok.filter(function (e, i) { return ok.indexOf(e) === i && (e.indexOf("/") < 0 || whole.indexOf(e.split("/")[0]) < 0); }).sort();
  }
  // Crime kinds as keys of CRIME_KINDS in their own order; every kind is none.
  function normKinds(v) {
    var want = list(v), out = CRIME_KINDS.filter(function (k) { return want.indexOf(k[0]) >= 0; }).map(function (k) { return k[0]; });
    return out.length === CRIME_KINDS.length ? [] : out;
  }
  // A year range inside YEARS (or `range`); the whole range is no filter.
  function normYears(v, range) {
    if (typeof v === "string") v = v.split("-");
    if (!Array.isArray(v) || !v.length) return null;
    var a = Math.round(num(v[0], NaN)), b = Math.round(num(v.length > 1 ? v[1] : v[0], NaN));
    if (!isFinite(a) || !isFinite(b)) return null;
    range = range || YEARS;
    var lo = range[0], hi = range[range.length - 1];
    a = Math.max(lo, Math.min(hi, a)); b = Math.max(lo, Math.min(hi, b));
    if (a > b) { var t = a; a = b; b = t; }
    return a === lo && b === hi ? null : [a, b];
  }

  // Any object to a whole, valid state: unknown values fall back to the defaults, so a hand-edited address or a
  // story step with a typo still draws a map.
  function normalize(s) {
    s = s || {};
    var out = clone(DEFAULTS);
    if (VIEWS.indexOf(s.view) >= 0) out.view = s.view;
    if (NEARS.some(function (n) { return n[0] === s.near; })) out.near = s.near;
    if (ENDS.some(function (e) { return e[0] === s.ends; })) out.ends = s.ends;
    if (s.camera && Array.isArray(s.camera.center) && s.camera.center.length === 2) {
      out.camera = { center: [round(num(s.camera.center[0], -122.44), 5), round(num(s.camera.center[1], 37.76), 5)],
        zoom: round(Math.max(0, Math.min(19, num(s.camera.zoom, 12))), 2), bearing: round(num(s.camera.bearing, 0), 1) };
    }
    if (Array.isArray(s.hin)) out.hin = HINS.filter(function (y) { return s.hin.indexOf(y) >= 0 || s.hin.indexOf(Number(y)) >= 0; });
    if (s.color === "hin") out.color = s.color;
    if (RANKS.indexOf(s.rank) >= 0) out.rank = s.rank;
    if (WORST_YEARS.indexOf(Number(s.worst)) >= 0) out.worst = Number(s.worst);
    var f = s.filter || {};
    Object.keys(FILTER_VALUES).forEach(function (k) { if (FILTER_VALUES[k].indexOf(f[k]) >= 0) out.filter[k] = f[k]; });
    out.filter.user = normUsers(f.user);
    out.filter.other = normOthers(f.other);
    out.filter.hinGroup = list(f.hinGroup).map(Number).filter(function (g, i, a) { return g >= 1 && g <= 30 && g === Math.round(g) && a.indexOf(g) === i; }).sort(function (a, b) { return a - b; });
    out.filter.cause = normCause(f.cause);
    // No `years` at all is the default span; null (or "all" from an address) is every year.
    out.filter.years = f.years === undefined ? clone(DEFAULTS.filter.years) : f.years === "all" ? null : normYears(f.years);
    out.filter.days = normDays(f.days);
    out.filter.time = normTimes(f.time);
    out.filter.area = normArea(f.area);
    // Bike Comfort Index classes, 0 (least comfortable) to 4; all five is no filter.
    var bci = list(f.bci).map(Number).filter(function (k, i, a) { return k >= 0 && k <= 4 && k === Math.round(k) && a.indexOf(k) === i; }).sort();
    out.filter.bci = bci.length === 5 ? [] : bci;
    out.filter.crimeYears = f.crimeYears === "all" ? null : normYears(f.crimeYears, CRIME_YEARS);
    out.filter.crimeKinds = normKinds(f.crimeKinds);
    var h = s.highlight;
    if (h && typeof h.area === "string" && h.area) out.highlight = { area: h.area };
    else if (h && Array.isArray(h.blocks) && h.blocks.length) out.highlight = { blocks: h.blocks.map(Number).filter(isFinite).sort(function (a, b) { return a - b; }) };
    else if (h && h.circle && Array.isArray(h.circle.center)) out.highlight = { circle: { center: [round(num(h.circle.center[0], 0), 5), round(num(h.circle.center[1], 0), 5)], feet: Math.max(50, num(h.circle.feet, 300)) } };
    if (s.crash) out.crash = String(s.crash);
    // The where-from view's open card: a bubble's name, or "own" for the chosen area's ring.
    if (s.card && out.view === "from" && out.filter.area) out.card = String(s.card);
    var c = s.chart;
    if (c && typeof c.id === "string" && (c.id === "none" || CHARTS[out.view].indexOf(c.id) >= 0)) out.chart = { id: c.id };
    if (out.chart && c.top && c.id === "by-cause" && out.filter.cause.length === 1 && out.filter.cause[0].indexOf("/") < 0) out.chart.top = true;
    return out;
  }

  // A state with `partial` laid over it. Camera and filter merge field by field; highlight, hin and crash replace.
  function merge(base, partial) {
    var b = normalize(base), p = partial || {}, out = clone(b);
    Object.keys(p).forEach(function (k) {
      if (k === "filter") out.filter = Object.assign({}, b.filter, p.filter || {});
      else if (k === "camera") out.camera = p.camera ? Object.assign({}, b.camera || { center: [-122.44, 37.76], zoom: 12, bearing: 0 }, p.camera) : null;
      else out[k] = clone(p[k]);
    });
    return normalize(out);
  }

  // The state as an address fragment, defaults left out, so the plain dashboard has a bare address.
  function toHash(s) {
    s = normalize(s);
    var q = [];
    if (s.view !== DEFAULTS.view) q.push("view=" + s.view);
    if (s.near !== DEFAULTS.near) q.push("near=" + s.near);
    if (s.ends !== DEFAULTS.ends) q.push("ends=" + s.ends);
    if (s.camera) q.push("at=" + [s.camera.center[0].toFixed(5), s.camera.center[1].toFixed(5), s.camera.zoom.toFixed(2)].concat(s.camera.bearing ? [s.camera.bearing] : []).join(","));
    if (s.hin.join(",") !== DEFAULTS.hin.join(",")) q.push("hin=" + (s.hin.join(",") || "none"));
    if (s.color !== DEFAULTS.color) q.push("color=" + s.color);
    var top = s.chart && s.chart.top;
    if (s.rank !== DEFAULTS.rank) q.push("rank=" + s.rank);
    if (s.worst) q.push("worst=" + s.worst);
    if (s.filter.hinGroup.length) q.push("groups=" + s.filter.hinGroup.join(","));
    ["user", "other", "cause", "days", "time", "bci", "crimeKinds"].forEach(function (k) { if (s.filter[k].length && !(k === "cause" && top)) q.push(HASH_KEY[k] + "=" + s.filter[k].map(encodeURIComponent).join(",")); });
    if (JSON.stringify(s.filter.years) !== JSON.stringify(DEFAULTS.filter.years)) q.push("years=" + (s.filter.years ? s.filter.years.join("-") : "all"));
    if (s.filter.crimeYears) q.push("cyears=" + s.filter.crimeYears.join("-"));
    Object.keys(FILTER_VALUES).forEach(function (k) { if (s.filter[k] !== DEFAULTS.filter[k]) q.push(HASH_KEY[k] + "=" + encodeURIComponent(s.filter[k])); });
    var a = s.filter.area;
    if (a && a.hood) q.push("hood=" + encodeURIComponent(a.hood));
    if (a && a.district) q.push("district=" + a.district);
    if (a && a.polygon) q.push("poly=" + a.polygon.map(function (p) { return p[0].toFixed(5) + "," + p[1].toFixed(5); }).join(";"));
    var h = s.highlight;
    if (h && h.area) q.push("area=" + encodeURIComponent(h.area));
    if (h && h.blocks) q.push("blocks=" + h.blocks.join(","));
    if (h && h.circle) q.push("ring=" + h.circle.center[0].toFixed(5) + "," + h.circle.center[1].toFixed(5) + "," + Math.round(h.circle.feet));
    if (s.crash) q.push("crash=" + encodeURIComponent(s.crash));
    if (s.card) q.push("card=" + encodeURIComponent(s.card));
    if (top) q.push("pick=" + encodeURIComponent(s.filter.cause[0]));
    else if (s.chart) q.push("chart=" + s.chart.id);
    return q.length ? "#" + q.join("&") : "";
  }

  // An address fragment back to a state. The scratch map's older forms (#view=injuries, #stress) still open their view,
  // the retired High-injury areas view opens the injuries view, and the retired crash groups (#view=kind, #color=group,
  // #chart=by-group) open the injuries view as it opens by default.
  function fromHash(hash) {
    var h = String(hash || "").replace(/^#/, ""), s = {}, kv = {};
    if (!h) return normalize(s);
    h.split("&").forEach(function (part) {
      var i = part.indexOf("=");
      if (i < 0) kv.view = kv.view || part.split("-")[0];
      else {
        var k = part.slice(i + 1), dec = function (v) { try { return decodeURIComponent(v); } catch (e) { return v; /* a malformed % stays as typed */ } };
        // List filters are each item encoded and joined by commas, so a comma inside an item survives.
        kv[part.slice(0, i)] = /^(user|other|cause|days|time|bci|kinds)$/.test(part.slice(0, i)) ? k.split(",").map(dec) : dec(k);
      }
    });
    s.view = kv.view === "people" || kv.view === "kind" || kv.view === "areas" ? "injuries" : kv.view;
    if (kv.near) s.near = kv.near;
    if (kv.ends) s.ends = kv.ends;
    if (kv.at) { var c = kv.at.split(",").map(Number); s.camera = { center: [c[0], c[1]], zoom: c[2], bearing: c[3] || 0 }; }
    if (kv.hin) s.hin = kv.hin === "none" ? [] : kv.hin.split(",");
    if (kv.color) s.color = kv.color;
    if (kv.rank) s.rank = kv.rank;
    if (kv.worst) s.worst = kv.worst;
    s.filter = { user: kv.user, other: kv.other, cause: kv.cause, years: kv.years, severity: kv.severity, hinGroup: kv.groups, hin: kv.on, at: kv.where, time: kv.time, days: kv.days, bci: kv.bci, crimeYears: kv.cyears, crimeKinds: kv.kinds };
    if (kv.hood) s.filter.area = { hood: kv.hood };
    else if (kv.district) s.filter.area = { district: kv.district };
    else if (kv.poly) s.filter.area = { polygon: kv.poly.split(";").map(function (p) { return p.split(",").map(Number); }) };
    if (kv.area) s.highlight = { area: kv.area };
    else if (kv.blocks) s.highlight = { blocks: kv.blocks.split(",") };
    else if (kv.ring) { var r = kv.ring.split(",").map(Number); s.highlight = { circle: { center: [r[0], r[1]], feet: r[2] } }; }
    if (kv.crash) s.crash = kv.crash;
    if (kv.card) s.card = kv.card;
    if (kv.chart) s.chart = { id: kv.chart };
    // pick=<cause>: that cause picked on the cause chart's top level (see `chart` above).
    if (kv.pick) { s.filter.cause = [kv.pick]; s.chart = { id: "by-cause", top: true }; }
    return normalize(s);
  }

  // The chart a state shows: its own pick, else the view's first, or null for none.
  // The HIN edition the 10-mile groups follow (Bryan, 2026-11-19: "The 'By 10 miles of HIN'
  // should change depending on which HIN I choose"): 2022 for the 2022 network or its groups, 2017 for the 2017
  // network (which has no groups), else 2024. `groupKey` is the person field holding their group in that edition
  // under the state's ranking window.
  function hinEdition(s) { var h = normalize(s).hin[0]; return h === "2022" || h === "groups22" ? "2022" : h === "2017" ? "2017" : "2024"; }
  function groupKey(s) { s = normalize(s); return (hinEdition(s) === "2022" ? "hg22:" : "hg:") + s.rank; }
  function chartFor(s) {
    s = normalize(s);
    if (s.chart) return s.chart.id === "none" ? null : s.chart.id;
    return CHARTS[s.view][0];
  }

  // The map's layers each state draws. A layer shows only when its id is listed, so the map hides the rest.
  function layersFor(s) {
    s = normalize(s);
    var L = [];
    if (s.view === "injuries") {
      if (s.hin.indexOf("2017") >= 0) L.push("hin17");
      if (s.hin.indexOf("2022") >= 0) L.push("hin22");
      if (s.hin.indexOf("2024") >= 0) L.push("hin", "hin-outline");
      if (s.hin.indexOf("groups") >= 0 || s.hin.indexOf("groups22") >= 0) L.push("hin-groups");
      if (s.worst) L.push("worst");
      L.push("minor", "minor-fan");
      L = L.concat(s.color === "hin" ? ["hinc"] : ["heat", "fan", "fan-lab"]);
    } else if (s.view === "stress") L = ["stress-grey", "stress-est", "stress-mod", "stress-meas"];
    else if (s.view === "through") L = ["through-grey", "through-low", "through"];
    else if (s.view === "bike") L = ["bci0", "bci1", "bci2", "bci3", "bci4"];
    else if (s.view === "crime") L = ["routes", "route-badges", "crime-heat", "crime-dots", "crime-stops"];
    else if (s.view === "from") L = ["from-regions", "from-own", "from-bubbles", "from-hl", "from-labels"];
    // The where-from view looks at the whole Bay Area, so the area is outlined but nothing outside it dims.
    if (s.filter.area) L.push.apply(L, s.view === "from" ? ["area-edge"] : ["area-mask", "area-edge"]);
    var h = s.highlight;
    if (h && h.area) L.push("hl-area-fill", "hl-area-line");
    if (h && h.blocks) L.push("hl-blocks");
    if (h && h.circle) L.push("hl-ring");
    return L;
  }

  // What a move from one state to another does: which layers fade out and in, whether the camera flies, and which
  // discrete settings switch (filters and the crash card switch at once; nothing between "on" and "off" to tween).
  function plan(from, to) {
    var a = normalize(from), b = normalize(to), la = layersFor(a), lb = layersFor(b);
    return {
      fadeOut: la.filter(function (l) { return lb.indexOf(l) < 0; }),
      fadeIn: lb.filter(function (l) { return la.indexOf(l) < 0; }),
      keep: lb.filter(function (l) { return la.indexOf(l) >= 0; }),
      camera: JSON.stringify(a.camera) !== JSON.stringify(b.camera),
      // The through distance or the where-from choice: the same layers, recoloured.
      params: a.near !== b.near || a.ends !== b.ends || a.view !== b.view,
      filter: JSON.stringify(a.filter) !== JSON.stringify(b.filter),
      highlight: JSON.stringify(a.highlight) !== JSON.stringify(b.highlight),
      crash: a.crash !== b.crash,
      chart: chartFor(a) !== chartFor(b),
    };
  }

  // Whether a point is inside a GeoJSON Polygon or MultiPolygon (even-odd over every ring, so holes count).
  function inside(pt, geom) {
    if (!geom) return true;
    var polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates], x = pt[0], y = pt[1], hit = false;
    polys.forEach(function (poly) {
      poly.forEach(function (ring) {
        for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
          if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
        }
      });
    });
    return hit;
  }

  // An area filter as GeoJSON: a drawn polygon closes its ring; a neighborhood is looked up in `hoods` ([{name, geom}]),
  // a Supervisor district in `districts` ([{district, geom}]).
  function areaGeom(s, hoods, districts) {
    var a = normalize(s).filter.area;
    if (!a) return null;
    if (a.polygon) return { type: "Polygon", coordinates: [a.polygon.concat([a.polygon[0]])] };
    if (a.district) { for (var j = 0; j < (districts || []).length; j++) if (districts[j].district === a.district) return districts[j].geom; return null; }
    for (var i = 0; i < (hoods || []).length; i++) if (hoods[i].name === a.hood) return hoods[i].geom;
    return null;
  }

  function sevLevel(id) { for (var i = 0; i < SEVERITIES.length; i++) if (SEVERITIES[i][0] === id) return SEVERITIES[i][2]; return 1; }
  function timeOf(id) { for (var i = 0; i < TIMES.length; i++) if (TIMES[i][0] === id) return TIMES[i]; return null; }
  // The TIMES a filter's time list names, or null for any time.
  function timesOf(ids) { var out = (ids || []).map(timeOf).filter(Boolean); return out.length ? out : null; }
  function hourIn(t, h) { return t[2] < t[3] ? h >= t[2] && h < t[3] : h >= t[2] || h < t[3]; }
  // The weekdays a list of day ids (DAYS or WEEK) covers, or null for every day.
  function weekdays(ids) {
    if (!ids || !ids.length) return null;
    var out = [];
    ids.forEach(function (id) { (OLD_DAYS[id] || []).forEach(function (w) { if (out.indexOf(w) < 0) out.push(w); }); });
    return out.sort();
  }
  function dayIn(id, wd) { var w = weekdays([id]); return !w || w.indexOf(wd) >= 0; }
  // The years a filter covers, as "2022" strings, or null for every year.
  function yearList(y) { if (!y) return null; var out = []; for (var k = y[0]; k <= y[1]; k++) out.push(String(k)); return out; }

  // MapLibre expressions, one per kind of choice, over a person's properties: `h` hour (-1 unknown), `wd` weekday,
  // `u` road user, `d` date, `ck` and `sk` cause and subcause keys.
  function timeExpr(t) { var H = ["get", "h"]; return t[2] < t[3] ? ["all", [">=", H, t[2]], ["<", H, t[3]]] : ["any", [">=", H, t[2]], ["all", [">=", H, 0], ["<", H, t[3]]]]; }
  function causeExpr(e) {
    var k = e.split("/"), c = ["==", ["get", "ck"], k[0]];
    return k.length > 1 ? ["all", c, ["==", ["get", "sk"], k.slice(1).join("/")]] : c;
  }
  function causeIn(e, p) { var k = e.split("/"); return p.ck === k[0] && (k.length < 2 || p.sk === k.slice(1).join("/")); }

  // A MapLibre filter expression for the time and day filters, over a feature's `h` (hour, -1 when unknown) and `wd`.
  function whenFilter(s) {
    var f = normalize(s).filter, all = ["all"], t = timesOf(f.time), w = weekdays(f.days);
    if (t) all.push(t.length === 1 ? timeExpr(t[0]) : ["any"].concat(t.map(timeExpr)));
    if (w) all.push(["in", ["get", "wd"], ["literal", w]]);
    return all;
  }

  // A MapLibre filter expression for the people layers. `geom` is the area filter's shape (areaGeom), or null.
  function peopleFilter(s, geom) {
    var f = normalize(s).filter, all = ["all"], y = yearList(f.years);
    if (f.user.length) all.push(["in", ["get", "u"], ["literal", f.user]]);
    if (f.other.length) all.push(["in", ["get", "op"], ["literal", f.other]]);
    if (f.cause.length) all.push(["any"].concat(f.cause.map(causeExpr)));
    if (y) all.push(["in", ["slice", ["get", "d"], 0, 4], ["literal", y]]);
    all.push(["<=", ["get", "sv"], sevLevel(f.severity)]);
    if (f.hinGroup.length) all.push(["in", ["get", groupKey(s)], ["literal", f.hinGroup]]);
    if (f.hin === "on") all.push(["!=", ["%", ["floor", ["/", ["get", "hy"], 4]], 2], 0]);
    if (f.hin === "off") all.push(["==", ["%", ["floor", ["/", ["get", "hy"], 4]], 2], 0]);
    if (f.at !== "all") all.push(["==", ["get", "at"], f.at === "intersection" ? 1 : 0]);
    all = all.concat(whenFilter(s).slice(1));
    // A neighborhood by each person's own `hood` (the unthinned outlines), a district by their `dist` (set in the
    // browser from the district outlines, map.js districtOf); a drawn shape by the point.
    if (f.area && f.area.hood) all.push(["==", ["get", "hood"], f.area.hood]);
    else if (f.area && f.area.district) all.push(["==", ["get", "dist"], f.area.district]);
    else if (geom) all.push(["within", geom]);
    return all;
  }
  // The same rule in plain code, for the figures and the chart, as a test made once per state: shownTest(s, geom)
  // returns a function of a person. Everything that depends only on the state (the normalized filter, the years, the
  // weekdays, the times, the group key) is worked out here, once, not per person: per person it cost 60 ms of the
  // 120 ms a severity switch took over 100,000 people (headless Chrome profile, 2026-11-19). `p.h` is the hour or
  // null, `p.wd` the weekday.
  // A person with no place (`p.np`: the police record has no point in San Francisco for them, so `p.c` is null) counts
  // under every filter that needs no place, and under none that does: an area, the High Injury Network or its groups,
  // at an intersection or midblock. The map can't draw them, so peopleFilter never sees them.
  function shownTest(s, geom) {
    var n = normalize(s), f = n.filter, w = weekdays(f.days), t = timesOf(f.time), lv = sevLevel(f.severity), gk = groupKey(n);
    var y0 = f.years ? f.years[0] : null, y1 = f.years ? f.years[1] : null, a = f.area;
    var users = f.user.length ? f.user : null, others = f.other.length ? f.other : null, causes = f.cause.length ? f.cause : null, groups = f.hinGroup.length ? f.hinGroup : null;
    var placed = !!(groups || f.hin !== "all" || f.at !== "all" || a || geom);
    return function (p) {
      if (p.sv > lv) return false;
      if (placed && p.np) return false;
      if (y0 !== null) { var yr = p.yr || +String(p.d).slice(0, 4); if (yr < y0 || yr > y1) return false; }
      if (users && users.indexOf(p.u) < 0) return false;
      if (others && others.indexOf(p.op) < 0) return false;
      if (causes && !causes.some(function (e) { return causeIn(e, p); })) return false;
      if (groups && groups.indexOf(p[gk]) < 0) return false;
      if (f.hin === "on" && !(p.hy & 4)) return false;
      if (f.hin === "off" && (p.hy & 4)) return false;
      if (f.at === "intersection" && p.at !== 1) return false;
      if (f.at === "midblock" && p.at !== 0) return false;
      if (t && (p.h == null || p.h < 0 || !t.some(function (x) { return hourIn(x, p.h); }))) return false;
      if (w && w.indexOf(p.wd) < 0) return false;
      if (a && a.hood) return p.hood === a.hood;
      if (a && a.district) return p.dist !== undefined ? p.dist === a.district : !!geom && inside(p.c, geom);
      if (geom && !inside(p.c, geom)) return false;
      return true;
    };
  }
  function personShown(s, p, geom) { return shownTest(s, geom)(p); }

  // A short title for what the state picks out, for the folded filter card, the tab and a saved image (Bryan,
  // 2026-11-19: "automatically generate a short title for each map based on what's highlighted"). Built from the
  // subject (who, or the layer), the cause, the day and time, the network and the area, at most about `max`
  // characters: past that it drops the network, then the day and time, then the area. Null when no filter is set, so
  // the card keeps the map's own name. The years stay out: the headline under it carries them.
  // `causes` is map.json's cause tree, for the cause's label. `used`, when given, is filled with which filters the title
  // names (user, killed, cause, when, net, where), so the page can leave those out of its chips.
  var TITLE_USER = { "Walking": "People walking", "Biking": "People biking", "Motorcycle or moped": "Motorcyclists",
    "Scooter or board": "Scooter riders", "Car or truck": "People in cars" };
  var TITLE_VIEW = { injuries: "Injuries", stress: "Traffic stress", through: "Through traffic", bike: "Bike comfort", crime: "Crime", from: "Where traffic comes from" };
  var TITLE_TIME = { am: "in the morning rush", midday: "at midday", pm: "in the evening rush", evening: "in the evening", night: "at night" };
  var TITLE_DAY = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };
  var TITLE_DAYTIME = { am: "morning rushes", midday: "middays", pm: "evening rushes", evening: "evenings", night: "nights" };
  function title(s, causes, max, used) {
    s = normalize(s); max = max || 60;
    var f = s.filter, inj = s.view === "injuries", subject = "", cause = "", when = "", net = "", where = "";
    if (inj) {
      var who = f.user.length === 1 ? TITLE_USER[f.user[0]] : "";
      // The severity names itself when it isn't the default (severe and killed).
      if (f.severity === "killed") subject = who ? who + " killed" : "Deaths";
      else if (f.severity === "visible") subject = who ? who + " with a visible injury or worse" : "Visible injuries or worse";
      else if (f.severity === "pain") subject = who ? who + " hurt, any injury" : "Every reported injury";
      else subject = who;
      var tops = f.cause.map(function (e) { return e.split("/")[0]; }).filter(function (k, i, a) { return a.indexOf(k) === i; });
      if (tops.length === 1) {
        var node = (causes || []).filter(function (c) { return c.key === tops[0]; })[0];
        var lab = node ? node.label : tops[0];
        cause = (/^[A-Z]{2,}/.test(lab) ? lab : lab.toLowerCase()) + " crashes";
      }
      if (f.hin === "on") net = "on the High Injury Network";
      if (f.hin === "off") net = "off the High Injury Network";
      // The 10-mile groups, worst first: one picked group names its place in the ranking.
      var ORD = ["", "", "second ", "third ", "fourth ", "fifth "];
      if (f.hinGroup.length === 1) net = f.hinGroup[0] < ORD.length ? "on the network's " + ORD[f.hinGroup[0]] + "worst 10 miles" : "on network miles " + (f.hinGroup[0] - 1) * 10 + " to " + f.hinGroup[0] * 10;
      else if (s.hin.indexOf("groups") >= 0 && !subject && !f.cause.length) subject = "The High Injury Network, worst to best";
      else if (s.hin.indexOf("groups22") >= 0 && !subject && !f.cause.length) subject = "The 2022 High Injury Network, worst to best";
      if (s.worst && !subject && !f.cause.length) subject = "Worst 10 miles of street in " + s.worst;
    }
    // One kind of crime picked names the subject: "Drugs reports".
    if (s.view === "crime" && f.crimeKinds.length === 1) subject = CRIME_KINDS.filter(function (k) { return k[0] === f.crimeKinds[0]; })[0][1] + " reports";
    // Days: weekday, weekend, one day by its full name, or several by their short names; times joined with "and".
    var and = function (a) { return a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]; };
    var d = f.days, one = d.length === 1, group = one && (d[0] === "weekday" || d[0] === "weekend");
    var day = group ? d[0] : one ? TITLE_DAY[d[0]] : and(WEEK.filter(function (w) { return d.indexOf(w[0]) >= 0; }).map(function (w) { return w[1]; }));
    var wk = s.view === "injuries" || s.view === "crime" || s.view === "through";
    if (wk && f.time.length) when = day ? "on " + day + " " + and(f.time.map(function (x) { return TITLE_DAYTIME[x]; })) : and(f.time.map(function (x) { return TITLE_TIME[x]; }));
    else if (wk && day) when = "on " + day + (one ? "s" : "");
    var a = f.area;
    if (a) where = a.hood ? "in " + a.hood : a.district ? "in District " + a.district : "in a drawn area";
    if (!cause && !subject && !when && !net && !where) return null;
    var head = subject && cause ? subject + " in " + cause : subject || (cause ? cause.charAt(0).toUpperCase() + cause.slice(1) : TITLE_VIEW[s.view]);
    var parts = [when, net, where], drop = [1, 0, 2];
    function join() { return [head].concat(parts.filter(Boolean)).join(" "); }
    var t = join();
    for (var i = 0; t.length > max && i < drop.length; i++) { parts[drop[i]] = ""; t = join(); }
    if (used) { used.user = !!(inj && f.user.length === 1); used.killed = inj && f.severity === "killed"; used.cause = !!cause;
      used.when = !!parts[0]; used.net = !!parts[1]; used.where = !!parts[2]; }
    return t;
  }

  root.SafetyMapState = { NEARS: NEARS, ENDS: ENDS, hinEdition: hinEdition, groupKey: groupKey, NEWEST_YEAR: NEWEST_YEAR, INLINE_FROM: INLINE_FROM, SEVERITIES: SEVERITIES, RANKS: RANKS, WORST_YEARS: WORST_YEARS, sevLevel: sevLevel, VIEWS: VIEWS, HINS: HINS, USERS: USERS, OTHERS: OTHERS, YEARS: YEARS, CRIME_YEARS: CRIME_YEARS, CRIME_KINDS: CRIME_KINDS, TIMES: TIMES, DAYS: DAYS, WEEK: WEEK, FILTERS: FILTERS, whenLabel: whenLabel, DAY_GROUPING: DAY_GROUPING, CHARTS: CHARTS, DEFAULTS: DEFAULTS, FILTER_VALUES: FILTER_VALUES,
    normalize: normalize, merge: merge, toHash: toHash, fromHash: fromHash, chartFor: chartFor, layersFor: layersFor, plan: plan,
    inside: inside, areaGeom: areaGeom, hourIn: hourIn, dayIn: dayIn, weekdays: weekdays, yearList: yearList, timeOf: timeOf, timesOf: timesOf, timeExpr: timeExpr,
    causeExpr: causeExpr, causeIn: causeIn, whenFilter: whenFilter, peopleFilter: peopleFilter, personShown: personShown, shownTest: shownTest, title: title, sortRows: sortRows };
})(this);
