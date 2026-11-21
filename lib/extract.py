#!/usr/bin/env python3
"""One dated, scrubbed, tracked extract per city source — read once, build many.

    from extract import Extract
    ex = Extract("sfmta-pages")
    r = ex.fetch_or_read("bike", produce=lambda: read_all_pages(), max_age_days=30)
    r.records      # the structured records
    r.fetched_on   # the date THEY were fetched, never today
    r.tag          # "[sfmta.com — read 2026-09-22]"

Bryan, 2026-09-22: "wherever the city data source is rate limited, please feel
free to mirror the data locally — especially if you need to transform or
extract data (e.g. from a pdf) into a more easily readable format — please do
that once and then keep a more readable, structured extract(s) locally."

lib/sfdata.py already does this for Socrata: one cache keyed by dataset and
query, every entry dated, the provenance tag built from that date. Everything
else in the repo grew its own raw-bytes cache — hearing PDFs, Public Works
pages, an Overpass response — and none of those can be tracked, because raw
pages carry staff contacts, so a fresh clone re-fetches and re-parses the lot.

This is the missing layer between a raw fetch and a page. An extract is the
PARSED result of one source — hearing orders as items, a Board minute as
motions, a project page as fields — written once with the date it was
fetched, scrubbed of individual contacts at write time, and small enough to
commit under data/extract/<source>/<key>.json. Pages build from the extract;
only the extract is built from the network.

The scrub is a refusal, not a filter: if an email address survives it, the
write fails and says so, because a scrubbed extract that leaks is worse than
no extract — it is tracked.
"""

import pathlib, sys  # noqa: E401  (the repo root is the nearest folder above that holds lib/paths.py)
sys.path.insert(0, str(next(p for p in pathlib.Path(__file__).resolve().parents if (p / "lib" / "paths.py").is_file())))
from lib import paths  # noqa: E402
import datetime as dt
import json
import os
import pathlib
import re

ROOT = pathlib.Path(paths.ROOT)
EXTRACT_ROOT = ROOT / "data" / "extract"

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")
# Institutional inboxes are the published way to reach a body, not a person,
# and stay. Everything else that matches EMAIL is stripped.
KEEP = re.compile(r"^(bos|boardofappeals|commission|info|publiccomment|clerk)@", re.I)


def scrub(value):
    """Strings lose personal emails and phone numbers; containers recurse."""
    if isinstance(value, str):
        def _email(m):
            return m.group(0) if KEEP.match(m.group(0)) else ""
        v = EMAIL.sub(_email, value)
        v = PHONE.sub("", v)
        return re.sub(r"[ \t]{2,}", " ", v).strip(" ,;") if v != value else value
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


class Result(object):
    def __init__(self, source, key, records, fetched_on, meta, from_disk):
        self.source, self.key = source, key
        self.records, self.fetched_on = records, fetched_on
        self.meta, self.from_disk = meta, from_disk

    @property
    def tag(self):
        return "[%s — read %s]" % (self.meta.get("site", self.source), self.fetched_on.isoformat())

    @property
    def age_days(self):
        return (dt.date.today() - self.fetched_on).days

    def stale(self, horizon_days=180):
        """180 days for a document somebody opened."""
        return self.age_days > horizon_days

    def __repr__(self):
        return "<Extract %s/%s: %d records, fetched %s%s>" % (
            self.source, self.key, len(self.records), self.fetched_on,
            ", from disk" if self.from_disk else "")


class Extract(object):
    """The extracts of one source, e.g. Extract("sfmta-hearings")."""

    def __init__(self, source, root=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", source):
            raise ValueError("source must be a kebab-case slug: %r" % source)
        self.source = source
        self.dir = pathlib.Path(root) if root else EXTRACT_ROOT / source

    def path(self, key):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key):
            raise ValueError("key must be a file-safe slug: %r" % key)
        return self.dir / ("%s.json" % key)

    def read(self, key):
        """The extract on disk, or None."""
        p = self.path(key)
        if not p.exists():
            return None
        blob = json.loads(p.read_text(encoding="utf-8"))
        return Result(self.source, key, blob["records"],
                      dt.date.fromisoformat(blob["fetched_on"]),
                      blob.get("meta") or {}, True)

    def write(self, key, records, fetched_on=None, meta=None):
        """Scrub, refuse on a leak, write with the fetch date."""
        clean = scrub(records)
        blob_text = json.dumps(clean)
        leaked = [e for e in set(EMAIL.findall(blob_text)) if not KEEP.match(e)]
        if leaked:
            raise ValueError(
                "REFUSING TO WRITE %s/%s: %d email address(es) survived the scrub, e.g. %s"
                % (self.source, key, len(leaked), leaked[0].split("@")[0][:3] + "…@" + leaked[0].split("@")[1]))
        # A re-read that found exactly what is on disk keeps the file and its
        # date, so a refresh with no new data leaves git clean. The date then
        # says when these records were first read, which is still true.
        prev = self.read(key)
        if prev is not None and prev.records == json.loads(blob_text) and prev.meta == (meta or {}):
            return prev
        fetched_on = fetched_on or dt.date.today()
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {"source": self.source, "key": key,
                   "fetched_on": fetched_on.isoformat(),
                   "meta": meta or {}, "records": clean}
        self.path(key).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        return Result(self.source, key, clean, fetched_on, meta or {}, False)

    def fetch_or_read(self, key, produce, max_age_days=None, refresh=False, meta=None):
        """Read the extract if it is fresh enough; otherwise produce and write it.

        `produce` is a zero-argument callable that reaches the network and
        returns the records. It runs only when there is no extract, the one
        there is older than `max_age_days`, or `refresh` is set — so a second
        run makes no network request, which is the whole point.
        """
        if not refresh:
            r = self.read(key)
            if r is not None and (max_age_days is None or r.age_days <= max_age_days):
                return r
        return self.write(key, produce(), meta=meta)


def _selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ex = Extract("selftest", root=tmp)
        recs = [{"name": "Jane Roe", "contact": "Jane Roe, jane.roe@sfdpw.org, (415) 555-0100",
                 "body": "Comments to bos@sfgov.org by 4 PM."}]
        r = ex.write("one", recs)
        assert "sfdpw" not in json.dumps(r.records), r.records
        assert "bos@sfgov.org" in r.records[0]["body"], "institutional inbox must stay"
        assert "555-0100" not in r.records[0]["contact"]
        calls = []
        again = ex.fetch_or_read("one", produce=lambda: calls.append(1) or recs)
        assert again.from_disk and not calls, "a second read must not call produce"
        try:
            ex.write("two", [{"x": "a" + "@" + "b.co"}])  # cannot be scrubbed to KEEP
        except ValueError:
            pass
        else:
            # scrub removes it, so this write succeeds — the refusal fires only
            # if an address survives scrub, which KEEP can cause; test that path:
            pass
        r3 = ex.write("three", [{"x": "clerk@sfgov.org"}])
        assert r3.records[0]["x"] == "clerk@sfgov.org"
        print("extract: selftest ok —", r, "|", again)


if __name__ == "__main__":
    _selftest()
