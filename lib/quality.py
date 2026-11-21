"""Declarative data quality checks, run after every source fetch; a failing one stops the pipeline.

pipeline/README.md, rule 2: every incremental fetch runs checks
right after it, covering at least row count against a floor or the previous
count, required fields present and non-null, dates in range, keys unique, and
joins that neither drop nor duplicate rows. This module is those five checks,
plus Each, a rule every row must meet that is particular to one dataset (no
Public Works page row holds 90 or more blocks). What each source's rows are,
and which checks apply to them, is declared in scripts/transportation-quality.py.

    from lib.quality import Table, Join, run
    t = Table("hearings", load=lambda root: [...], key=("date", "page"),
              required=["date", "page"], dates={"date": ("2019-01-01", "+60")},
              floor=100, max_drop=0.05)
    results = run([t], root=ROOT, prev_root=SNAPSHOT)

A `load(root)` returns the rows as a list of dicts read from under `root`, or
None when the file is not there. It is called twice: on the data after the
fetch (`root`) and on the snapshot taken before it (`prev_root`), which is
what the row-count bound compares against. A Result names its check as
"<table>.<check>", so a failure says exactly which rule and which data broke.

Date bounds are ISO dates, or "+N"/"-N" meaning N days from today. A value is
read from its first ten characters, or from epoch seconds/milliseconds.
"""

import collections
import datetime as dt
import json
import os


class Result(object):
    __slots__ = ("check", "ok", "detail")

    def __init__(self, check, ok, detail=""):
        self.check, self.ok, self.detail = check, ok, detail

    def __repr__(self):
        return "%s %s%s" % ("pass" if self.ok else "FAIL", self.check, (": " + self.detail) if self.detail else "")


def _bound(b, today):
    if b is None:
        return None
    if isinstance(b, str) and b[:1] in "+-" and b[1:].isdigit():
        return (today + dt.timedelta(days=int(b))).isoformat()
    return b


def as_date(v):
    """An ISO date string from a date-ish value, or None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        secs = v / 1000 if v > 1e11 else v
        return dt.datetime.fromtimestamp(secs, dt.timezone.utc).date().isoformat()
    s = str(v)[:10]
    try:
        return dt.date.fromisoformat(s).isoformat()
    except ValueError:
        return "invalid:" + str(v)[:30]


def _get(row, field):
    if callable(field):
        return field(row)
    if isinstance(field, (tuple, list)):
        return tuple(_get(row, f) for f in field)
    return row.get(field) if isinstance(row, dict) else None


def _name(field):
    if callable(field):
        return getattr(field, "__name__", "fn")
    if isinstance(field, (tuple, list)):
        return "+".join(_name(f) for f in field)
    return str(field)


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _sample(xs, n=4):
    xs = list(xs)
    return ", ".join(repr(x) for x in xs[:n]) + (" …" if len(xs) > n else "")


class Table(object):
    """One set of rows and the checks that apply to it.

    floor       fewest rows accepted, whatever came before
    max_drop    largest fall in row count against the previous data, as a
                share (0.05 = the new data may hold 5% fewer rows). None skips.
    max_growth  largest rise, as a share; None skips. A sudden doubling is as
                much a broken read (a join fanning out) as a halving.
    required    fields that must be present and non-null in every row; a
                (field, share) pair allows that share of rows to lack it
    key         field, tuple of fields or callable whose value is unique
    dates       {field: (lo, hi)}; an empty value passes unless required
    """

    def __init__(self, name, load, floor=1, max_drop=0.10, max_growth=None,
                 required=(), key=None, dates=None):
        self.name, self.load = name, load
        self.floor, self.max_drop, self.max_growth = floor, max_drop, max_growth
        self.required, self.key, self.dates = list(required), key, dict(dates or {})

    def check(self, rows, prev, today):
        n = self.name
        if rows is None:
            return [Result(n + ".present", False, "no data on disk")]
        out = []
        cnt = len(rows)
        ok = cnt >= (self.floor or 0)
        detail = "%d rows, floor %d" % (cnt, self.floor or 0)
        if prev is not None:
            p = len(prev)
            detail += ", previously %d" % p
            if self.max_drop is not None and cnt < p * (1 - self.max_drop):
                ok = False
                detail += " (fell more than %d%%)" % round(100 * self.max_drop)
            if self.max_growth is not None and p and cnt > p * (1 + self.max_growth) + 5:
                ok = False
                detail += " (grew more than %d%%)" % round(100 * self.max_growth)
        out.append(Result(n + ".rows", ok, detail))
        for spec in self.required:
            field, share = spec if isinstance(spec, tuple) and len(spec) == 2 and isinstance(spec[1], float) else (spec, 0.0)
            bad = [i for i, r in enumerate(rows) if _empty(_get(r, field))]
            allowed = int(share * cnt)
            out.append(Result("%s.required[%s]" % (n, _name(field)), len(bad) <= allowed,
                              "%d of %d rows lack it%s" % (len(bad), cnt, (", %d allowed" % allowed) if allowed else "")
                              + ((" (rows %s)" % _sample(bad)) if len(bad) > allowed else "")))
        if self.key is not None:
            c = collections.Counter(_get(r, self.key) for r in rows)
            dup = [k for k, v in c.items() if v > 1]
            out.append(Result("%s.unique[%s]" % (n, _name(self.key)), not dup,
                              "%d distinct of %d%s" % (len(c), cnt, ("; repeated: " + _sample(dup)) if dup else "")))
        for field, (lo, hi) in self.dates.items():
            lo_, hi_ = _bound(lo, today), _bound(hi, today)
            bad = []
            for r in rows:
                d = as_date(_get(r, field))
                if d is None:
                    continue
                if d.startswith("invalid:") or (lo_ and d < lo_) or (hi_ and d > hi_):
                    bad.append(d)
            out.append(Result("%s.dates[%s]" % (n, _name(field)), not bad,
                              "%s..%s; %d out of range%s" % (lo_ or "-", hi_ or "-", len(bad),
                                                             (": " + _sample(sorted(bad))) if bad else "")))
        return out


class Join(object):
    """A join that must neither drop nor duplicate rows.

    `left(root)` gives the keys that must each come out of the join exactly
    once; `right(root)` gives the keys that did. A key on the left missing on
    the right is a dropped row, a key on the right more than once is a
    duplicated one, and (unless `extra_ok`) a key on the right with nothing on
    the left is a row the join invented. `drop_ok` is for a join that keeps
    only some of its left rows by design (matches of a term, say), where the
    check is that nothing on the right is invented or repeated.
    """

    def __init__(self, name, left, right, extra_ok=False, drop_ok=False):
        self.name, self.left, self.right = name, left, right
        self.extra_ok, self.drop_ok = extra_ok, drop_ok

    def check(self, root):
        lk, rk = self.left(root), self.right(root)
        if lk is None or rk is None:
            return [Result(self.name + ".join", False, "no data on disk")]
        lset, rc = set(lk), collections.Counter(rk)
        dropped = [] if self.drop_ok else sorted((k for k in lset if k not in rc), key=str)
        dup = sorted((k for k, v in rc.items() if v > 1), key=str)
        extra = [] if self.extra_ok else sorted((k for k in rc if k not in lset), key=str)
        ok = not (dropped or dup or extra)
        detail = "%d in, %d out" % (len(lset), sum(rc.values()))
        if dropped:
            detail += "; dropped %d: %s" % (len(dropped), _sample(dropped))
        if dup:
            detail += "; duplicated %d: %s" % (len(dup), _sample(dup))
        if extra:
            detail += "; %d with no source row: %s" % (len(extra), _sample(extra))
        return [Result(self.name + ".join", ok, detail)]


class Each(object):
    """A rule every row of one set must meet: `test(row)` returns None when it does, else why not.

    For what the five general checks cannot say about one dataset, such as
    a ceiling on the blocks a row placed from a page's Location may hold.
    `load(root)` is a loader as for Table.
    """

    def __init__(self, name, load, test, rule):
        self.name, self.load, self.test, self.rule = name, load, test, rule

    def check(self, root):
        rows = self.load(root)
        if rows is None:
            return [Result(self.name + ".each", False, "no data on disk")]
        bad = [w for w in (self.test(r) for r in rows) if w]
        return [Result(self.name + ".each", not bad, "%s: %d of %d rows break it%s" % (
            self.rule, len(bad), len(rows), (": " + _sample(bad)) if bad else ""))]


def run(checks, root, prev_root=None, today=None):
    """Every Result of every Table and Join in `checks`."""
    today = today or dt.date.today()
    out = []
    for c in checks:
        try:
            if isinstance(c, (Join, Each)):
                out += c.check(root)
            else:
                rows = c.load(root)
                prev = c.load(prev_root) if prev_root else None
                out += c.check(rows, prev, today)
        except Exception as exc:  # noqa: BLE001 - a check that cannot read its data fails
            out.append(Result(getattr(c, "name", "?") + ".read", False, "%s: %s" % (type(exc).__name__, exc)))
    return out


# ---- loaders ------------------------------------------------------------------

def read_json(root, rel):
    p = os.path.join(root, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def json_rows(rel, *path):
    """A loader: the list at `path` inside the JSON file `rel` (keys and list indexes)."""
    def load(root):
        d = read_json(root, rel)
        if d is None:
            return None
        for k in path:
            d = d[k]
        return list(d.values()) if isinstance(d, dict) else d
    load.__name__ = rel
    return load


def _selftest():
    import tempfile
    today = dt.date(2026, 9, 28)
    good = [{"id": 1, "d": "2026-09-01"}, {"id": 2, "d": "2026-09-02"}, {"id": 3, "d": "2026-09-03"}]
    t = Table("t", load=None, floor=2, max_drop=0.1, required=["id", "d"], key="id",
              dates={"d": ("2019-01-01", "+1")})
    assert all(r.ok for r in t.check(good, good, today))
    short = good[:2]
    assert not [r for r in t.check(short, good, today) if r.check == "t.rows"][0].ok
    nullkey = good + [{"id": None, "d": "2026-09-04"}]
    assert not [r for r in t.check(nullkey, good, today) if r.check == "t.required[id]"][0].ok
    dup = good + [{"id": 3, "d": "2026-09-04"}]
    assert not [r for r in t.check(dup, good, today) if r.check == "t.unique[id]"][0].ok
    future = good + [{"id": 4, "d": "2027-01-01"}]
    assert not [r for r in t.check(future, good, today) if r.check == "t.dates[d]"][0].ok
    j = Join("j", left=lambda root: [1, 2, 3], right=lambda root: [1, 2, 2])
    r = j.check(None)[0]
    assert not r.ok and "dropped 1" in r.detail and "duplicated 1" in r.detail, r
    e = Each("e", load=lambda root: good + [{"id": 9, "d": None}], test=lambda r: None if r["d"] else "id %d" % r["id"],
             rule="every row dated")
    r = e.check(None)[0]
    assert not r.ok and "1 of 4" in r.detail, r
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "x.json"), "w") as fh:
            json.dump({"a": {"rows": good}}, fh)
        assert json_rows("x.json", "a", "rows")(tmp) == good
        assert json_rows("y.json")(tmp) is None
    print("quality.py selftest ok")


if __name__ == "__main__":
    _selftest()
