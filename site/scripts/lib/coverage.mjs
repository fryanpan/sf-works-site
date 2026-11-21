// How far forward a page's findings actually reach.
//
// A page states the date it queried each source. That is not the same as the
// date the source stops being able to say anything, and the difference is where
// a reader gets misled: the bikeway layer was read this morning and was last
// refreshed in April, so a bikeway built in May is invisible and the page looks
// current anyway.
//
// So every page carries one more date — the last day past which nothing on it
// is evidence — set by whichever input stops first, and naming that input.

// Socrata publishes `data_as_of` on every row: when the extract behind this
// dataset was taken. It is an upper bound on coverage and nothing more, because
// a nightly reload of a table whose last real event was in April still reports
// today. So coverage is the EARLIER of what the publisher claims and the last
// event actually present.
export function coverageOf(rows, { asOfField = "data_as_of", eventFields = [] } = {}) {
  // City tables carry typos with four-digit years: the plan-review extract has a
  // finish date in 2201. Taking a plain max hands the page a coverage date two
  // centuries out, so anything past today is discarded rather than trusted.
  const today = new Date().toISOString().slice(0, 10);
  const day = (v) => {
    if (typeof v !== "string" || v.length < 10) return null;
    const d = v.slice(0, 10);
    return d > today ? null : d;
  };
  const maxOf = (field) => {
    let best = null;
    for (const r of rows) {
      const d = day(r[field]);
      if (d && (best === null || d > best)) best = d;
    }
    return best;
  };

  const published = asOfField ? maxOf(asOfField) : null;
  const observed = eventFields.map(maxOf).filter(Boolean).sort().at(-1) ?? null;

  // With no event field to read, the publisher's claim is all there is.
  if (!observed) return { through: published, published, observed: null };
  if (!published) return { through: observed, published: null, observed };
  return { through: observed < published ? observed : published, published, observed };
}

// The page's own limit: the earliest `through` among the sources a finding
// depends on. Sources that only colour in a detail are passed with
// `binding: false` so a stale nice-to-have cannot drag the whole page back.
export function validThrough(entries) {
  const binding = entries.filter((e) => e.binding !== false && e.through);
  if (!binding.length) return null;
  const earliest = binding.reduce((a, b) => (a.through <= b.through ? a : b));
  return {
    date: earliest.through,
    limitedBy: earliest.label,
    why: earliest.why,
    sources: entries.map(({ label, through, binding = true }) => ({ label, through, binding })),
  };
}
