"""Hold a full copy of DataSF's three injury-crash tables, and bring it up to date by reading only the rows that moved.

    import crash_tables
    crash_tables.refresh(update=True)            # ask DataSF what changed and read only that (crash-augment.py does this)
    rows = crash_tables.rows("parties", columns=["unique_id", "vehicle_make"])   # the held rows, from disk
    info = crash_tables.info("parties")          # row count, DataSF marker, the date the rows were last read

    python3 pipeline/crash-augment/crash_tables.py [--update]   # the same refresh on its own

THE TABLES. Traffic Crashes Resulting in Injury, published by DataSF from SFPD's crash reports:

  crashes  ubvf-ztfx  one row per crash, keyed case_id_pkey
  parties  8gtc-pjc6  one row per party (driver, pedestrian, bicyclist...), keyed unique_id
  victims  nwes-mmgh  one row per injured or killed person, keyed unique_id

Every column is kept as DataSF gives it except four kinds that would make a copy differ from one day to the next
with nothing in it changed, or that repeat another column: `data_loaded_at` (the time of DataSF's nightly load,
the same on every row), `point` (tb_latitude and tb_longitude hold the same location), and Socrata's
`:@computed_region_*` columns. DROPPED lists them.

THE HELD COPY lives in data/socrata-cache/crash-augment/<id>/<year>.json (gitignored), one file per collision year,
its rows sorted by key, with the date they were read. _state.json beside them records, per table, DataSF's
`rowsUpdatedAt` at the last good refresh, the newest `data_updated_at` held, when the whole table was last read,
and the row count and SHA-256 of every year file.

HOW --update READS ONLY WHAT MOVED. DataSF reloads these tables every night and stamps every row with the load time,
so Socrata's own `:updated_at` says nothing. The tables carry their own per-row `data_updated_at`, the day SFPD's
record last changed, and that is the marker. For each table:

  1. Ask DataSF for `rowsUpdatedAt` (one request) and the row count per collision year (one request).
  2. If `rowsUpdatedAt` moved since the last good refresh, read the rows whose `data_updated_at` is on or after the
     newest one held, and put each in its year in place of the held row with the same key. The newest day is read
     again because the field is a date, not a time.
  3. Any year whose held row count differs from DataSF's (a row added or deleted upstream, a row that moved year,
     or a held file cut short or edited on disk) is reconciled: its keys are read (one small request), held rows
     whose key is gone are dropped, and only the missing keys' rows are read, 150 keys a request.
  4. Once the whole table was last read more than FULL_REREAD_DAYS ago, every year is read again, so an upstream
     edit that did not move `data_updated_at` cannot live in the copy for longer than that.

Then the checks below run on the result, and only if they pass are the changed year files written and the state
saved. A refresh with nothing new reads no rows and writes no file. Without --update no request is made at all,
unless a table has no held copy, which is then read whole, a year at a time.

CHECKS (lib/quality.py's Result), each "crash-tables/<table>.<check>":

  rows_by_year   every year holds exactly DataSF's count for it, so nothing was dropped, repeated or left behind
  rows           the table holds at least FLOORS[table] rows and no more than 2% fewer than the last good refresh
  unique         every key is held once, across all years
  required       every row has its key, case_id_pkey and collision_datetime
  dates          every collision_datetime falls between 2005-01-01 and tomorrow

A failing check raises CheckFailed and the held copy stays as it was. The refresh is recorded in
data/pipeline-state/sources.json as "crash-augment:<id>" (lib/pipeline_state.py): changed or unchanged, with the
marker, or failed with the reason and the held copy kept.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import argparse
import collections
import datetime as dt
import hashlib
import json
import os

import sfdata  # noqa: E402  (lib/ is on sys.path once lib.paths is imported)
from lib import pipeline_state  # noqa: E402
from lib.quality import Result  # noqa: E402

STORE = os.environ.get("CRASH_TABLES_STORE") or os.path.join(paths.ROOT, "data", "socrata-cache", "crash-augment")
STATE = os.path.join(STORE, "_state.json")
MARKER_PREFIX = "crash-augment:"

# name -> (DataSF id, key column)
TABLES = {
    "crashes": ("ubvf-ztfx", "case_id_pkey"),
    "parties": ("8gtc-pjc6", "unique_id"),
    "victims": ("nwes-mmgh", "unique_id"),
}
DROPPED = ("data_loaded_at", "point")
DROPPED_PREFIX = ":@computed_region_"
REQUIRED = ("case_id_pkey", "collision_datetime")
# Fewest rows each table may hold. On 2026-11-25 DataSF held 66,991 crashes, 140,843 parties and 84,943 victims
# [DataSF ubvf-ztfx, 8gtc-pjc6, nwes-mmgh — queried 2026-11-25]; the floors catch an empty or truncated read.
FLOORS = {"crashes": 60000, "parties": 125000, "victims": 75000}
MAX_DROP = 0.02
FULL_REREAD_DAYS = 90
KEY_BATCH = 150
FIRST_DATE = "2005-01-01"


class CheckFailed(RuntimeError):
    """A refreshed table failed its checks; the held copy was kept."""

    def __init__(self, results):
        self.results = results
        RuntimeError.__init__(self, "; ".join(repr(r) for r in results if not r.ok))


# ---- small parts ----------------------------------------------------------------------------------------------------

def key_order(k):
    """Numeric keys in number order, anything else after them."""
    return (0, int(k), "") if str(k).isdigit() else (1, 0, str(k))


def year_of(row):
    return (row.get("collision_datetime") or "")[:4] or "none"


def clean(row):
    return {k: v for k, v in row.items() if k not in DROPPED and not k.startswith(DROPPED_PREFIX)}


def _today():
    return os.environ.get("CRASH_TABLES_TODAY") or dt.date.today().isoformat()


def _quote(v):
    return "'%s'" % str(v).replace("'", "''")


def _year_path(fxf, year):
    return os.path.join(STORE, fxf, "%s.json" % year)


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_state(state):
    os.makedirs(STORE, exist_ok=True)
    text = json.dumps(state, indent=1, sort_keys=True) + "\n"
    if os.path.exists(STATE) and open(STATE, encoding="utf-8").read() == text:
        return
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, STATE)


def _read_year(fxf, year):
    """(rows by key, read_on) from a held year file, or ({}, None) when there is none."""
    p = _year_path(fxf, year)
    if not os.path.exists(p):
        return {}, None
    blob = json.load(open(p, encoding="utf-8"))
    return {r[TABLES_BY_ID[fxf]]: r for r in blob["rows"]}, blob.get("read_on")


def _year_text(fxf, year, rows, read_on):
    ordered = [rows[k] for k in sorted(rows, key=key_order)]
    return json.dumps({"id": fxf, "year": year, "read_on": read_on, "rows": ordered}, sort_keys=True) + "\n"


TABLES_BY_ID = {fxf: key for fxf, key in TABLES.values()}


# ---- reading DataSF -------------------------------------------------------------------------------------------------

class Counter(object):
    """Requests and rows read this run, so the run can say what it fetched."""

    def __init__(self):
        self.requests, self.rows = 0, 0


def _stream(fxf, where=None, select=None, stats=None):
    out = []
    for page in sfdata.stream(fxf, select=select, where=where, order=":id"):
        out.extend(page)
        if stats:
            stats.requests += 1
    if stats and select is None:
        stats.rows += len(out)
    return out


def upstream_counts(fxf, stats=None):
    """{year: rows} as DataSF holds them now."""
    # A grouped query needs $group, which sfdata.stream does not take, so it is asked with sfdata._get directly.
    params = {"$select": "date_extract_y(collision_datetime) as y, count(*) as n", "$group": "y", "$order": "y"}
    rows = sfdata._get(sfdata._url(fxf, params), 120)
    if stats:
        stats.requests += 1
    return {(r.get("y") or "none"): int(r["n"]) for r in rows}


def _year_where(year):
    if year == "none":
        return "collision_datetime IS NULL"
    return "date_extract_y(collision_datetime) = %d" % int(year)


# ---- the refresh ----------------------------------------------------------------------------------------------------

def _refresh_one(name, update, log, stats):
    fxf, key = TABLES[name]
    state = load_state()
    st = state.get(fxf) or {}
    held_years = st.get("years") or {}
    pending = {}   # year -> {key: row}, only the years this refresh touches
    notes = []

    def held(year):
        if year not in pending:
            pending[year] = _read_year(fxf, year)[0]
        return pending[year]

    def held_count(year):
        """The row count held on disk for a year, trusting the state only while the file's bytes are unchanged."""
        if year in pending:
            return len(pending[year])
        rec = held_years.get(year)
        p = _year_path(fxf, year)
        if not os.path.exists(p):
            return 0
        if rec and _sha_file(p) == rec.get("sha"):
            return rec["rows"]
        return len(held(year))

    cold = not held_years or not all(os.path.exists(_year_path(fxf, y)) for y in held_years)
    if not update and not cold:
        return None
    if cold:
        held_years = {}
    view = sfdata._get("https://%s/api/views/%s.json" % (sfdata.HOST, fxf), 120)
    stats.requests += 1
    stamp = str(view.get("rowsUpdatedAt"))
    # DataSF's own column order, which the augmented tables keep.
    columns = [c["fieldName"] for c in view.get("columns", [])
               if c.get("fieldName") and c["fieldName"] not in DROPPED and not c["fieldName"].startswith(DROPPED_PREFIX)]
    up = upstream_counts(fxf, stats)
    full_due = cold or not st.get("full_read_on") or not st.get("updated_through") or (
        dt.date.fromisoformat(_today()) - dt.date.fromisoformat(st["full_read_on"])).days > FULL_REREAD_DAYS
    full_read_on = st.get("full_read_on")

    if full_due:
        # A whole read, a year at a time, so no more than one year's rows are parsed at once beyond what is kept.
        for year in sorted(up):
            rows = {r[key]: clean(r) for r in _stream(fxf, where=_year_where(year), stats=stats)}
            pending[year] = rows
        for year in held_years:
            pending.setdefault(year, {})
        full_read_on = _today()
        notes.append("read whole")
    else:
        if stamp != st.get("rowsUpdatedAt") or st.get("status") == "failed":
            since = st.get("updated_through")
            delta = _stream(fxf, where="data_updated_at >= %s" % _quote(since), stats=stats)
            moved = {r[key]: year_of(r) for r in delta}
            for r in delta:
                held(year_of(r))[r[key]] = clean(r)
            # A row whose collision year changed sits in its new year now; take it out of every other year.
            for year in sorted(set(held_years) - set(pending)):
                h, _ = _read_year(fxf, year)
                if any(k in moved for k in h):
                    pending[year] = h
            for year, h in pending.items():
                for k in [k for k in h if k in moved and moved[k] != year]:
                    del h[k]
            notes.append("%d rows with data_updated_at on or after %s" % (len(delta), since))
        # Reconcile every year whose count is off.
        for year in sorted(set(up) | set(held_years)):
            want = up.get(year, 0)
            if held_count(year) == want:
                continue
            h = held(year)
            if not want:
                pending[year] = {}
                notes.append("%s: dropped (no rows upstream)" % year)
                continue
            keys_up = {r[key] for r in _stream(fxf, select=key, where=_year_where(year), stats=stats)}
            gone = [k for k in h if k not in keys_up]
            for k in gone:
                del h[k]
            missing = sorted((k for k in keys_up if k not in h), key=key_order)
            for i in range(0, len(missing), KEY_BATCH):
                batch = missing[i:i + KEY_BATCH]
                where = "%s in (%s)" % (key, ",".join(_quote(k) for k in batch))
                for r in _stream(fxf, where=where, stats=stats):
                    h[r[key]] = clean(r)
            notes.append("%s: reconciled, %d read, %d dropped" % (year, len(missing), len(gone)))

    # ---- checks, before anything is written ----
    counts = {y: held_count(y) for y in sorted(set(up) | set(held_years) | set(pending))}
    counts = {y: n for y, n in counts.items() if n or y in up}
    results = _checks(name, fxf, key, up, counts, pending, st)
    if any(not r.ok for r in results):
        raise CheckFailed(results)

    # ---- write what changed ----
    today = _today()
    years_state = {}
    changed = []
    for year in sorted(set(held_years) | set(pending)):
        p = _year_path(fxf, year)
        if year in pending:
            rows = pending[year]
            if not rows:
                if os.path.exists(p):
                    os.remove(p)
                    changed.append(year)
                continue
            old_rows, old_read = _read_year(fxf, year)
            if old_rows == rows and old_read:
                text = _year_text(fxf, year, rows, old_read)
            else:
                text = _year_text(fxf, year, rows, today)
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != text:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                tmp = p + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.replace(tmp, p)
                changed.append(year)
            newest = max((r.get("data_updated_at") or "" for r in rows.values()), default="")
            years_state[year] = {"rows": len(rows), "sha": _sha_file(p), "updated_through": newest}
        elif os.path.exists(p):
            years_state[year] = held_years[year]
    through = max((v.get("updated_through") or "" for v in years_state.values()), default="")
    state = load_state()
    state[fxf] = {"name": name, "rowsUpdatedAt": stamp, "columns": columns, "updated_through": through, "full_read_on": full_read_on,
                  "status": "ok", "rows": sum(v["rows"] for v in years_state.values()), "years": years_state}
    _save_state(state)
    status = "changed" if changed else "unchanged"
    detail = "%d rows; %s" % (state[fxf]["rows"], "; ".join(notes) if notes else "nothing re-read")
    if changed:
        detail += "; years rewritten: " + ", ".join(changed)
    pipeline_state.record(MARKER_PREFIX + fxf, status, version=stamp, detail=detail)
    log("  %s %s: %s, %s" % (name, fxf, status, detail))
    return results


def _checks(name, fxf, key, up, counts, pending, st):
    n = "crash-tables/%s" % name
    out = []
    off = {y: (counts.get(y, 0), up.get(y, 0)) for y in sorted(set(up) | set(counts)) if counts.get(y, 0) != up.get(y, 0)}
    out.append(Result(n + ".rows_by_year", not off, "%d years%s" % (len(up), ("; held vs DataSF: %s" % off) if off else "")))
    total = sum(counts.values())
    prev = st.get("rows")
    ok = total >= FLOORS[name] and not (prev and total < prev * (1 - MAX_DROP))
    out.append(Result(n + ".rows", ok, "%d rows, floor %d%s" % (total, FLOORS[name], (", previously %d" % prev) if prev else "")))
    # Uniqueness and fields: every year this refresh touched, plus each held year's keys for the cross-year check.
    seen = collections.Counter()
    bad_req, bad_date = [], []
    hi = (dt.date.fromisoformat(_today()) + dt.timedelta(days=1)).isoformat()
    # Only a refresh that changed something is scanned; an untouched copy passed these when it was written.
    for year in sorted(counts) if pending else []:
        rows = pending.get(year)
        if rows is None:
            rows = _read_year(fxf, year)[0]
        for k, r in rows.items():
            seen[k] += 1
            for f in (key,) + REQUIRED:
                if not r.get(f):
                    bad_req.append((k, f))
            d = (r.get("collision_datetime") or "")[:10]
            if d and not (FIRST_DATE <= d <= hi):
                bad_date.append((k, d))
            if pending.get(year) is None and r.get(key) != k:
                bad_req.append((k, "key"))
    dup = [k for k, c in seen.items() if c > 1]
    out.append(Result(n + ".unique", not dup, "%d keys%s" % (len(seen), ("; repeated: %s" % dup[:4]) if dup else "")))
    out.append(Result(n + ".required", not bad_req, "%d rows lack a required field%s" % (len(bad_req), (": %s" % bad_req[:4]) if bad_req else "")))
    out.append(Result(n + ".dates", not bad_date, "%s..%s; %d out of range%s" % (FIRST_DATE, hi, len(bad_date), (": %s" % bad_date[:4]) if bad_date else "")))
    return out


def refresh(names=None, update=False, log=print):
    """Refresh the named tables (all three by default). Returns every check Result; raises CheckFailed on a failure.

    A read error or a failed check records the table as failed in sources.json and raises, and the held copy stays."""
    stats = Counter()
    results = []
    for name in names or list(TABLES):
        fxf = TABLES[name][0]
        try:
            got = _refresh_one(name, update, log, stats)
        except Exception as exc:  # noqa: BLE001 - recorded, then raised: the held copy stays
            pipeline_state.record(MARKER_PREFIX + fxf, "failed", detail="%s: %s; held copy kept" % (type(exc).__name__, exc))
            state = load_state()
            if fxf in state:
                state[fxf]["status"] = "failed"
                _save_state(state)
            raise
        if got is None:
            log("  %s %s: held copy, not asked (no --update)" % (name, fxf))
        else:
            results += got
    log("  DataSF: %d requests, %d rows read" % (stats.requests, stats.rows))
    return results


# ---- reading the held copy ------------------------------------------------------------------------------------------

def info(name):
    """{"id", "rows", "rowsUpdatedAt", "read_on", "full_read_on"} for a held table; read_on is the newest year file's."""
    fxf = TABLES[name][0]
    st = load_state().get(fxf) or {}
    read = []
    for year in st.get("years", {}):
        p = _year_path(fxf, year)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                head = fh.read(400)
            i = head.find('"read_on": "')
            if i >= 0:
                read.append(head[i + 12:i + 22])
    return {"id": fxf, "rows": st.get("rows"), "rowsUpdatedAt": st.get("rowsUpdatedAt"),
            "read_on": max(read) if read else None, "full_read_on": st.get("full_read_on")}


def columns(name):
    """DataSF's columns for a table, in its own order, less DROPPED; any column a held row has beyond them goes last."""
    return list((load_state().get(TABLES[name][0]) or {}).get("columns") or [])


def years(name):
    fxf = TABLES[name][0]
    return sorted((load_state().get(fxf) or {}).get("years", {}))


def iter_rows(name, columns=None):
    """Every held row of a table, year by year and in key order within a year, each a dict (only `columns` if given).

    Reads one year file at a time. A table with no held copy is read from DataSF first."""
    fxf = TABLES[name][0]
    if not years(name):
        refresh([name], update=False)
    for year in years(name):
        rows, _ = _read_year(fxf, year)
        for k in sorted(rows, key=key_order):
            r = rows[k]
            yield r if columns is None else {c: r[c] for c in columns if c in r}


def rows(name, columns=None):
    return list(iter_rows(name, columns))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="ask DataSF what changed and read only that")
    ap.add_argument("tables", nargs="*", help="any of crashes, parties, victims (default all three)")
    args = ap.parse_args()
    try:
        refresh(args.tables or None, update=args.update)
    except CheckFailed as exc:
        for r in exc.results:
            if not r.ok:
                print("   ", r)
        print("crash_tables: checks failed; the held copy is kept")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
