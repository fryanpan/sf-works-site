// Fetch a whole Socrata dataset, or fail loudly — never a short answer.
//
// Every collector here used to fetch with a fixed `$limit` and check the result
// against a floor. A floor catches an empty or broken response and cannot catch
// the failure that actually happened: the plan-review table passed 400,000 rows,
// the fetch asked for exactly that many, and 54,438 rows were dropped with no
// error and no notice. The permits page then published a filing-year series with
// 2018 and 2019 missing — 19,460 and 21,128 rows that exist in the source — and
// nothing about the page looked wrong.
//
// So the row count is not guessed. `count(1)` is asked first, the rows are paged
// until that many have arrived, and a short result raises. A cap that nobody can
// hit by accident is the only kind worth having.
//
// Paging needs a stable sort or the pages overlap and skip. `:id` is Socrata's
// own row identifier and is the only field guaranteed to be present and unique.

const HOST = "https://data.sf.gov";
const PAGE = 50000;

async function json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

/** How many rows the dataset says it has, right now. */
export async function rowCount(id) {
  const r = await json(`${HOST}/resource/${id}.json?%24select=count(1)`);
  const n = Number(r?.[0]?.count_1);
  if (!Number.isFinite(n)) throw new Error(`${id}: no count in ${JSON.stringify(r)}`);
  return n;
}

/**
 * Every row of a dataset.
 *
 * `minRows` stays as a floor against a source that has quietly emptied — it
 * answers "is this still the dataset we think it is", which a count cannot,
 * because a count of zero is internally consistent.
 */
export async function fetchAll(id, { minRows = 1 } = {}) {
  const total = await rowCount(id);
  if (total < minRows) {
    throw new Error(`${id}: ${total} rows, below the floor of ${minRows}`);
  }

  const out = [];
  for (let offset = 0; offset < total; offset += PAGE) {
    const page = await json(
      `${HOST}/resource/${id}.json?%24order=%3Aid&%24limit=${PAGE}&%24offset=${offset}`,
    );
    out.push(...page);
    // A page shorter than asked for, before the end, means the source moved
    // under us. Stopping here would silently truncate, which is the bug.
    if (page.length === 0) break;
  }

  // The dataset can gain rows between the count and the last page; that is fine
  // and common. Losing them is not — it is the truncation this exists to catch.
  if (out.length < total) {
    throw new Error(
      `${id}: fetched ${out.length} rows but the dataset reports ${total}. ` +
        `This is the silent-truncation failure: do not publish from a short read.`,
    );
  }
  return out;
}

/**
 * `fetchAll`, re-read only when the dataset has changed.
 *
 * Keeps each dataset's rows in `cacheDir/<id>.json` beside the dataset's own
 * `rowsUpdatedAt`, read from the metadata endpoint in one small request. When
 * that marker has not moved, the cached rows are returned and nothing else is
 * fetched. When it has, the whole dataset is re-read; rows identical to the
 * cached ones keep the cached `fetchedOn`, so a figure dated by it only moves
 * when the data does. `cacheDir` is gitignored (`.cache/` at the repo root).
 *
 * Returns { rows, fetchedOn, rowsUpdatedAt, fromCache }.
 */
export async function fetchAllCached(id, { cacheDir, minRows = 1 } = {}) {
  const file = `${cacheDir}/${id}.json`;
  const fs = await import("node:fs");
  let cached = null;
  try {
    cached = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    cached = null;
  }
  const meta = await json(`${HOST}/api/views/${id}.json`);
  const marker = meta?.rowsUpdatedAt ?? null;
  if (cached && marker !== null && cached.rowsUpdatedAt === marker) {
    return { rows: cached.rows, fetchedOn: cached.fetchedOn, rowsUpdatedAt: marker, fromCache: true };
  }
  const rows = await fetchAll(id, { minRows });
  const same = cached && JSON.stringify(cached.rows) === JSON.stringify(rows);
  const fetchedOn = same ? cached.fetchedOn : new Date().toISOString().slice(0, 10);
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.writeFileSync(file + ".tmp", JSON.stringify({ id, rowsUpdatedAt: marker, fetchedOn, rows }));
  fs.renameSync(file + ".tmp", file);
  return { rows, fetchedOn, rowsUpdatedAt: marker, fromCache: false };
}
