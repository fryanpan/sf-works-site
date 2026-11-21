#!/usr/bin/env python3
"""One fetch layer for DataSF, replacing five hand-rolled caches.

Piece 2 of `docs/product/city-data-tool-plan.md`, approved by Bryan on
2026-09-06.

WHY THIS EXISTS. Five scripts in this repo each grew their own Socrata cache,
and no two behave the same. The differences are not style -- three of them are
defects:

  scripts/correction-letter-join.py  keys the cache on the dataset id ALONE,
      so two different queries against the same dataset overwrite each other
      and the second one silently reads the first one's rows.
  tools/projects/street-work-list.py        stores a bare list with no date, so a
      cached run cannot say when its numbers were true. Every figure it
      produces would have to be tagged with today, which is a lie the moment
      the cache is a day old.
  Both of the above, plus permit-timing-page.py, ask for `$limit: 50000` (or
      200000) with no pagination and no check that the answer was complete.
      Socrata returns the first page and a 200. A dataset that grows past the
      limit truncates silently, and a floor set below the limit cannot see it.

This module fixes all three by construction:

  * The cache key is the dataset id AND the query. Different queries cannot
    collide.
  * Every cache entry carries the date its rows were fetched, and `Result.tag`
    builds the repo's provenance tag from THAT date -- never from today. A
    figure read out of a week-old cache is tagged a week old.
  * Fetches paginate to exhaustion with a stable `$order`, and assert the last
    page was short. A truncated read raises instead of returning.

WHAT IT DELIBERATELY DOES NOT DO. It does not decide whether a number is
right. The floor check catches an empty or truncated response; it cannot catch
a `$where` that is subtly wrong, and trap 7 in `topics/sf-civic-data.md` --
build a positive control into the same session as any null result -- is still
the caller's job.

    from sfdata import fetch, count, metadata
    r = fetch("btxj-k9uh")
    r.rows        # the rows
    r.fetched_on  # the date THESE rows were pulled
    r.tag         # "[DataSF btxj-k9uh — queried 2026-09-06]"
    r.stale       # True past the 90-day figure horizon
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

# data.sfgov.org now 301s to data.sf.gov, and a redirected request carrying a
# $select comes back 403 rather than following through — so a plain fetch kept
# working while every projection failed, which is the half of this module that
# exists to keep responses small. Canonical host, no redirect, no 403.
HOST = "data.sf.gov"
ROOT = pathlib.Path(paths.ROOT)
CACHE_ROOT = ROOT / "data" / "socrata-cache"
CATALOG = ROOT / "data" / "catalog" / "datasets.json"

# Socrata's per-request page size. Asking for more does not error -- it returns
# a page and a 200 -- which is exactly why this module paginates rather than
# trusting one large $limit.
PAGE = 50000

# The repo's expiry rule: 90 days for a figure queried out of a live dataset.
FIGURE_HORIZON_DAYS = 90

# A full pull of a dataset should come back at roughly the size the catalog
# recorded. Below this share of it, something truncated or the query is wrong.
# Loose on purpose: datasets grow and shrink, and this guards against a silent
# empty, not against drift.
FLOOR_SHARE = 0.5

_catalog = None


def catalog():
    """The dataset catalog built by scripts/catalog.py, or {} if absent."""
    global _catalog
    if _catalog is None:
        try:
            _catalog = {d["id"]: d for d in json.loads(CATALOG.read_text())["datasets"]}
        except Exception:
            _catalog = {}
    return _catalog


class Truncated(RuntimeError):
    """A paginated read did not reach the end of the result set."""


class TooFew(RuntimeError):
    """A read returned fewer rows than the floor allows."""


class Result(object):
    """Rows plus the date they were fetched, which is the whole point."""

    def __init__(self, fxf, params, rows, fetched_on, from_cache):
        self.fxf = fxf
        self.params = params
        self.rows = rows
        self.fetched_on = fetched_on
        self.from_cache = from_cache

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    @property
    def tag(self):
        """The repo's provenance tag, dated when THESE rows were fetched."""
        return "[DataSF %s — queried %s]" % (self.fxf, self.fetched_on.isoformat())

    @property
    def age_days(self):
        return (dt.date.today() - self.fetched_on).days

    @property
    def stale(self):
        """Past the figure horizon, so the tag no longer claims currency."""
        return self.age_days > FIGURE_HORIZON_DAYS

    def require_fresh(self):
        """Raise rather than let an expired figure be published as current."""
        if self.stale:
            raise RuntimeError(
                "%s was fetched %d days ago, past the %d-day figure horizon. "
                "Re-fetch it (delete the cache entry or pass max_age_days) or "
                "drop the claim to [model knowledge — verify]."
                % (self.fxf, self.age_days, FIGURE_HORIZON_DAYS))
        return self

    def __repr__(self):
        return "<Result %s %d rows fetched %s%s>" % (
            self.fxf, len(self.rows), self.fetched_on,
            " (cached)" if self.from_cache else "")


def _url(fxf, params):
    # SoQL parameters must be urlencoded. A raw "$select=count(*) as n" fails
    # with InvalidURL on every dataset at once, which looks like an outage
    # rather than a client bug.
    return "https://%s/resource/%s.json?%s" % (HOST, fxf, urllib.parse.urlencode(params))


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _key(fxf, params):
    """Cache key over the dataset AND the query.

    Keying on the dataset alone is the correction-letter-join defect: two
    different queries share a file and the second silently reads the first's
    rows.
    """
    blob = json.dumps([fxf, sorted(params.items())], sort_keys=True)
    return "%s-%s" % (fxf, hashlib.sha256(blob.encode()).hexdigest()[:12])


def default_floor(fxf, params):
    """A floor from the catalog, for a full unfiltered pull only.

    A filtered query has no knowable size, so it gets no floor from here --
    the caller passes one or accepts none.
    """
    if "$where" in params or "$select" in params or "$q" in params:
        return None
    rows = catalog().get(fxf, {}).get("rows")
    return int(rows * FLOOR_SHARE) if rows else None


def stream(fxf, select=None, where=None, order=None, limit=None,
           timeout=180, progress=False):
    """Yield pages of rows without holding the whole result in memory.

    `fetch` is the right call for anything that fits in memory, and caches.
    This one is for the two dispatch logs, which are 7.4M and 7.9M rows: a
    list that size in Python, and a cache file to match, is not a sensible
    price for a table that is about to live in DuckDB anyway. Nothing is
    cached here, so the caller owns the vintage -- `store.py` records it.
    """
    params = {}
    if select:
        params["$select"] = select
    if where:
        params["$where"] = where
    params["$order"] = order or ":id"
    seen = 0
    while True:
        page = dict(params, **{"$limit": PAGE, "$offset": seen})
        got = _get(_url(fxf, page), timeout)
        if not got:
            return
        seen += len(got)
        yield got
        if progress:
            print("  %s: %s rows" % (fxf, format(seen, ",")), file=sys.stderr, flush=True)
        if len(got) < PAGE:
            return
        if limit and seen >= limit:
            return


def fetch(fxf, select=None, where=None, order=None, limit=None,
          floor=None, max_age_days=None, refresh=False, cache_dir=None,
          timeout=180, progress=False):
    """Every row matching a query, cached by dataset AND query, with a date.

    floor        minimum acceptable row count; defaults to half the catalog's
                 recorded size for an unfiltered pull, None otherwise.
    max_age_days re-fetch if the cached entry is older than this. None keeps
                 a cache entry forever -- fine, because the entry carries its
                 own date and `Result.tag` uses it. Note that 0 means "today's
                 entry is acceptable", NOT "always refetch"; for that pass
                 refresh.
    refresh      ignore any cached entry and read from Socrata. The new rows
                 are still written to the cache, so they carry today's date.
    limit        stop after this many rows. Turns the completeness assertion
                 off, because a deliberate partial read is not a truncation.
    """
    params = {}
    if select:
        params["$select"] = select
    if where:
        params["$where"] = where
    # Pagination without a stable sort can repeat and skip rows between pages.
    # Socrata's :id is always present and always unique.
    params["$order"] = order or ":id"

    cache_dir = pathlib.Path(cache_dir) if cache_dir else CACHE_ROOT
    path = cache_dir / ("%s.json" % _key(fxf, params))

    if path.exists() and not refresh:
        try:
            blob = json.loads(path.read_text())
            fetched_on = dt.date.fromisoformat(blob["fetched_on"])
            fresh = max_age_days is None or (dt.date.today() - fetched_on).days <= max_age_days
            if fresh:
                return Result(fxf, params, blob["rows"], fetched_on, True)
        except (ValueError, KeyError):
            # A cache entry we cannot read the date off is not a cache entry.
            # The old street-work-list format -- a bare list -- lands here.
            pass

    rows = []
    while True:
        page = dict(params, **{"$limit": PAGE, "$offset": len(rows)})
        got = _get(_url(fxf, page), timeout)
        rows.extend(got)
        if progress:
            print("  %s: %d rows" % (fxf, len(rows)), file=sys.stderr, flush=True)
        if len(got) < PAGE:
            break
        if limit and len(rows) >= limit:
            break
        if len(rows) > 5_000_000:
            raise Truncated(
                "%s passed 5,000,000 rows without a short page. Either the "
                "dataset is larger than this layer should stream into memory "
                "or $order is not stabilising pagination." % fxf)
    if limit:
        rows = rows[:limit]

    if floor is None and not limit:
        floor = default_floor(fxf, params)
    if floor is not None and len(rows) < floor:
        raise TooFew(
            "%s returned %d rows, below the floor of %d. Socrata answers a "
            "malformed query with 200 and a short body, so this is what a "
            "broken query looks like -- not a small dataset. Query: %s"
            % (fxf, len(rows), floor, params))

    # A refresh that returns the rows already cached keeps the cached entry and
    # its date, so every figure and tag built from it stays byte-identical and
    # a refresh with no new data leaves git clean. When the dataset was last
    # CHECKED is recorded by pipeline/transportation-update.py, not here.
    if path.exists():
        try:
            blob = json.loads(path.read_text())
            if blob.get("rows") == rows:
                return Result(fxf, params, rows, dt.date.fromisoformat(blob["fetched_on"]), True)
        except (ValueError, KeyError):
            pass
    today = dt.date.today()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"fxf": fxf, "params": params, "fetched_on": today.isoformat(),
         "rows": rows}))
    return Result(fxf, params, rows, today, False)


def count(fxf, where=None, distinct=None, **kw):
    """count(*), or count(distinct <column>) -- the trap-2 check in one call."""
    sel = "count(distinct %s) as n" % distinct if distinct else "count(*) as n"
    r = fetch(fxf, select=sel, where=where, order="n", floor=1, **kw)
    return int(r.rows[0]["n"]), r


def metadata(fxf, timeout=120):
    """The publisher's own name, columns and last row update for a dataset."""
    m = _get("https://%s/api/views/%s.json" % (HOST, fxf), timeout)
    updated, stamp = None, None
    for key in ("rowsUpdatedAt", "viewLastModified"):
        if m.get(key):
            updated, stamp = dt.date.fromtimestamp(m[key]), m[key]
            break
    return {
        "id": fxf,
        "name": m.get("name"),
        "columns": sorted(c["fieldName"] for c in m.get("columns", []) if c.get("fieldName")),
        "rows_updated_at": updated,
        # The same moment to the second, for telling two updates on one day apart.
        "rows_updated_ts": stamp,
    }


def _selftest():
    """Exercise the three defects this layer exists to fix."""
    ok = True

    # 1. Two different queries against one dataset must not collide.
    # Both queries must return rows, or "they differ" could just be two
    # different flavours of empty.
    a = fetch("tyz3-vt28", where="submit_to_issue_cal > 10", floor=1)
    b = fetch("tyz3-vt28", where="submit_to_issue_cal > 100", floor=1)
    if len(a) == len(b):
        print("FAIL: two different queries returned identical row counts (%d); "
              "the cache key is colliding." % len(a))
        ok = False
    else:
        print("ok  distinct queries, distinct caches: %d vs %d rows" % (len(a), len(b)))

    # 2. A cached read must report the date it was fetched, not today.
    again = fetch("tyz3-vt28", where="submit_to_issue_cal > 10", floor=1)
    if not again.from_cache or again.fetched_on != a.fetched_on:
        print("FAIL: the second read did not come from cache with its own date.")
        ok = False
    else:
        print("ok  cached read carries its own date: %s" % again.tag)

    # 3. Pagination must pass a single page. ygmz-vaxd is 5,457 rows, so force
    #    the point on a dataset that genuinely exceeds PAGE.
    big = fetch("i98e-djp9", select="permit_number", limit=120000, progress=True)
    if len(big) != 120000:
        print("FAIL: paginated read returned %d rows, expected 120000." % len(big))
        ok = False
    else:
        print("ok  paginated past one page: %d rows in %d requests"
              % (len(big), -(-len(big) // PAGE)))

    # 4. The floor must fire on a query that matches nothing.
    try:
        fetch("tyz3-vt28", where="submit_to_issue_cal > 999999", floor=1)
        print("FAIL: a query matching nothing did not raise TooFew.")
        ok = False
    except TooFew:
        print("ok  a query matching nothing raises rather than returning empty")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest())
