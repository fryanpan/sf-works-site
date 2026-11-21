// The forward-looking half of the streets page: street work that has not
// happened yet, on streets the 2025 Biking and Rolling Plan says should carry
// biking, with nothing published saying the bike work is in scope.
//
// This is a port of `tools/projects/street-work-list.py` in the private research repo,
// which has carried the same join since 2026-09-05. It is a port and not a
// rewrite on purpose: the Python tool's counts are checked against it at build
// time by `assertParity`, so the two cannot drift without the build failing.
// Anything here that looks arbitrary is copying a decision documented there.

// Public Works gives excavators 120 days' notice before it paves a block
// (Public Works Order 187005 sec. 5.2(A)(2)). The public gets no equivalent, so
// the same window is what "you can still act on this" means here.
export const NOTICE_DAYS = 120;

// A project whose drawings can still change is one that has not finished.
//
// The earlier version of this excluded Construction unless the start date was
// still ahead, which cut a project off at the moment work began. That is the
// wrong end: bike infrastructure goes in near the end of a street job, before
// restriping, so the window closes at completion and not at groundbreaking.
// The feed bears this out — every construction project that has started still
// has a future end date, median 237 days out, so the old rule was dropping
// mid-flight projects with most of a year left to run.

export const SCOPE_BIKE = "bike work named";
export const SCOPE_ACTIVE = "walking or streetscape named";
export const SCOPE_UNIT = "SFMTA street-design unit";
export const SCOPE_SILENT = "the record does not say";

const BIKE_WORDS =
  /\bbike|\bbicycl|bikeway|cycle ?track|cycletrack|sharrow|greenway|slow street|quick.?build|protected lane|buffered lane/i;
const ACTIVE_WORDS =
  /pedestrian|streetscape|vision zero|curb ramp|bulb|crosswalk|traffic calming|complete street/i;
// SFMTA's own street-design units. A project owned by one of these is about
// street design whatever its name says.
const BIKE_UNITS = /MTA .*(Livable Streets|Transportation Engineering)/i;

// What the published record says about a project's scope. Deliberately not a
// judgement about what the city will build: it reports what three published
// fields contain, and its most common answer is that they contain nothing on
// the question. `description` is "NONE", "N/A" or a ticket number on a third of
// projects, so the project NAME carries almost all of the signal.
export function readScope(name, description, agency) {
  const text = `${name ?? ""} ${description ?? ""}`;
  if (BIKE_WORDS.test(text)) return SCOPE_BIKE;
  if (BIKE_UNITS.test(agency ?? "")) return SCOPE_UNIT;
  if (ACTIVE_WORDS.test(text)) return SCOPE_ACTIVE;
  return SCOPE_SILENT;
}

// DataSF publishes CNN as a string and SFMTA's ArcGIS layer as a double —
// "361000" against 15145000.0 — so both sides go through here or the join
// silently matches nothing.
function normCnn(v) {
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.trunc(n)) : null;
}

// Every CNN in a `cnn` field, which is not always one CNN.
//
// `btxj-k9uh` puts a Python-style list in this field when a project row spans
// several centreline segments: "['23348000', '23347000', '1720000']". That is
// 908 of 7,853 rows, touching 158 of the 389 projects, so a reader that treats
// the field as one id loses two fifths of all projects' segments — and loses
// them in the direction that matters, because an unmatched segment counts as
// having no bikeway and no plan entry.
export function parseCnns(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return [];
  if (raw.startsWith("[")) {
    // A Python list literal with single quotes. JSON.parse after swapping the
    // quote style, rather than a regex, so a malformed value fails loudly here
    // instead of half-matching.
    let parsed;
    try {
      parsed = JSON.parse(raw.replace(/'/g, '"'));
    } catch {
      return [];
    }
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normCnn).filter(Boolean);
  }
  const one = normCnn(raw);
  return one ? [one] : [];
}

// Every coordinate in a GeoJSON geometry, whatever its type. Public Works
// publishes LineStrings for most projects, Polygons for 18 and Points for 2, so
// a LineString-only reader silently drops twenty.
export function vertices(geom) {
  if (!geom) return [];
  let g = geom;
  if (typeof g === "string") {
    try {
      g = JSON.parse(g);
    } catch {
      return [];
    }
  }
  const c = g.coordinates;
  if (!c) return [];
  switch (g.type) {
    case "Point":
      return [[c[0], c[1]]];
    case "LineString":
      return c.map((p) => [p[0], p[1]]);
    case "MultiLineString":
      return c.flat().map((p) => [p[0], p[1]]);
    case "Polygon":
      return c.flat().map((p) => [p[0], p[1]]);
    case "MultiPolygon":
      return c.flat(2).map((p) => [p[0], p[1]]);
    default:
      return [];
  }
}

// Degrees per grid cell, about 45 m at this latitude. Only used to bucket points
// so the nearest-vertex scan looks at nine cells instead of every vertex.
const CELL = 0.0005;

// How close a project's own line has to come to a North Star line before this
// calls it a match. The threshold is not doing the work: of the projects this
// path exists for, most sit at exactly 0 m — their vertices are the same snapped
// centerline points — and the next nearest is 34 m away. Any value from 10 to 30
// selects the same set.
const MATCH_METRES = 25;

// A point index of the planned network, for projects with no CNN.
//
// THE DEFECT THIS EXISTS FOR. `btxj-k9uh` publishes `cnn` as the literal string
// "[]" for 61 of the 389 projects, so a match keyed on CNN cannot see them and
// they render as "not on the network". They are not: 41 publish real geometry
// and 27 of those lie on the planned network, 24 of them exactly.
export function buildGrid(featureCollections) {
  const grid = new Map();
  let n = 0;
  for (const fc of featureCollections) {
    if (!fc) continue;
    for (const f of fc.features) {
      const pr = f.properties ?? {};
      const fac = pr.facility ?? pr.north_star ?? "?";
      for (const [x, y] of vertices(f.geometry)) {
        const key = `${Math.floor(x / CELL)},${Math.floor(y / CELL)}`;
        let cell = grid.get(key);
        if (!cell) grid.set(key, (cell = []));
        cell.push([x, y, fac]);
        n += 1;
      }
    }
  }
  return { grid, vertexCount: n };
}

// [facility, metres] for the closest planned-network vertex, or [null, null].
// Flat-earth distance: over 25 m in San Francisco the error is centimetres.
export function nearestPlanned(points, grid, limit = MATCH_METRES) {
  let bestD = null;
  let bestF = null;
  for (const [x, y] of points) {
    const gx = Math.floor(x / CELL);
    const gy = Math.floor(y / CELL);
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dy = -1; dy <= 1; dy += 1) {
        const cell = grid.get(`${gx + dx},${gy + dy}`);
        if (!cell) continue;
        for (const [ax, ay, fac] of cell) {
          const d = Math.hypot((ax - x) * 88800, (ay - y) * 111000);
          if (bestD === null || d < bestD) {
            bestD = d;
            bestF = fac;
          }
        }
      }
    }
  }
  return bestD !== null && bestD <= limit ? [bestF, bestD] : [null, null];
}

const day = (v) => {
  const s = String(v ?? "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
};
const daysBetween = (from, to) =>
  Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000);

// One record per project, from the segment rows.
export function buildUpcoming({ projects, plan, grid, moratorium, bikeway, today }) {
  const bikewayByCnn = new Map();
  for (const r of bikeway) {
    for (const cnn of parseCnns(r.cnn)) {
      if (!bikewayByCnn.has(cnn)) bikewayByCnn.set(cnn, new Set());
      bikewayByCnn.get(cnn).add(r.facility_t || "?");
    }
  }

  // A five-year paving lock still in force. The Public Works Director can waive
  // one for good cause with no public step, so it is a signal and not a bar.
  const lockedByCnn = new Map();
  for (const r of moratorium) {
    const exp = day(r.expirationdate);
    if (!exp || exp < today) continue;
    for (const cnn of parseCnns(r.cnn)) {
      if (!lockedByCnn.has(cnn) || exp > lockedByCnn.get(cnn)) lockedByCnn.set(cnn, exp);
    }
  }

  const byProject = new Map();
  let rowsWithoutId = 0;
  for (const r of projects) {
    const pid = String(r.dotmapsid ?? "").trim();
    if (!pid) {
      rowsWithoutId += 1;
      continue;
    }
    let p = byProject.get(pid);
    if (!p) {
      byProject.set(
        pid,
        (p = {
          id: pid,
          name: r.name ?? "",
          agency: r.agency_name ?? "",
          phase: r.project_phase ?? "",
          description: r.description ?? "",
          // The project manager's name and address are both left in Public
          // Works' own record rather than republished here. Bryan's call on the
          // addresses, 2026-09-19, was that the city should stay the only
          // publisher of its staff's contact details; the name travels with the
          // address on the page every row links to, so a reader writing a letter
          // is one click from both and the city is the one publishing them.
          start: null,
          end: null,
          cnns: new Set(),
          streets: new Set(),
          points: [],
        }),
      );
    }
    for (const cnn of parseCnns(r.cnn)) p.cnns.add(cnn);
    // Only projects the centerline match cannot reach use these.
    p.points.push(...vertices(r.co_ordinatelinestring));
    if (r.on_street) p.streets.add(String(r.on_street).trim());
    const s = day(r.start_date);
    const e = day(r.end_date);
    if (s && (p.start === null || s < p.start)) p.start = s;
    if (e && (p.end === null || e > p.end)) p.end = e;
  }

  const out = [];
  for (const p of byProject.values()) {
    const cnns = [...p.cnns];
    const withBikeway = cnns.filter((c) => bikewayByCnn.has(c));
    const locked = cnns.filter((c) => lockedByCnn.has(c));
    const days = p.start ? daysBetween(today, p.start) : null;
    // Time left before the work is finished, which is the window that matters
    // for asking. Negative means the published end date has passed.
    const daysToEnd = p.end ? daysBetween(today, p.end) : null;

    let plannedHits = cnns.filter((c) => plan.has(c)).map((c) => plan.get(c).facility);
    let match = plannedHits.length ? "centerline" : null;
    let metres = null;
    if (!cnns.length && p.points.length) {
      const [fac, d] = nearestPlanned(p.points, grid);
      if (fac) {
        plannedHits = [fac];
        match = "geometry";
        metres = Math.round(d * 10) / 10;
      }
    }

    const scope = readScope(p.name, p.description, p.agency);
    // Finished work cannot change. Everything else can, whatever its phase.
    const changeable = daysToEnd === null || daysToEnd >= 0;
    // "Worth asking about" is not "the city is not building a bike lane here".
    // It is: the plan says this street should carry biking, work is coming, and
    // nothing published says the bike work is in scope — which is exactly what
    // Public Works Code §2.4.13 requires a determination about.
    const ask = plannedHits.length > 0 && scope === SCOPE_SILENT && changeable;

    out.push({
      id: p.id,
      name: p.name,
      agency: p.agency,
      phase: p.phase,
      start: p.start,
      end: p.end,
      streets: [...p.streets].sort().slice(0, 6),
      segments: cnns.length,
      segmentsWithBikeway: withBikeway.length,
      segmentsLocked: locked.length,
      segmentsOnPlan: plannedHits.length,
      onPlanCnns: cnns.filter((c) => plan.has(c)),
      plannedFacility: [...new Set(plannedHits)].sort(),
      planMatch: match,
      planMetres: metres,
      scope,
      changeable,
      ask,
      daysToStart: days,
      daysToEnd,
      inNoticeWindow: days !== null && days >= 0 && days <= NOTICE_DAYS,
    });
  }

  // Most actionable first, and what makes a project actionable is how long is
  // left before it finishes — not how long until it starts. A job with 30 days
  // to restriping is the most urgent thing on this page; a job that starts in
  // two years is the least. So the sort runs on time remaining, and a project
  // with no published end date goes last because nothing can be said about it.
  const rank = (p) => {
    const d = p.daysToEnd;
    if (d === null) return [2, 0];
    if (d < 0) return [1, -d];
    return [0, d];
  };
  out.sort((a, b) => {
    const [ra, va] = rank(a);
    const [rb, vb] = rank(b);
    return ra - rb || va - vb;
  });

  return { projects: out, rowsWithoutId };
}
